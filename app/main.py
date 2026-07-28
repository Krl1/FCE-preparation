"""FastAPI: API aplikacji FCE + serwowanie frontendu.

Uruchomienie:  uvicorn app.main:app --reload
Następnie:     http://localhost:8000
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import db
from . import fce_taxonomy as tax
from . import llm_client, pricing, srs
from .models import (
    CompleteRequest,
    ExercisePublic,
    GeneratedExercise,
    GenerateRequest,
    GoalRequest,
    GradeRequest,
    GradingResult,
    TipExerciseRequest,
)

DEFAULT_DAILY_GOAL = 5

app = FastAPI(title="FCE Preparation")
conn = db.get_connection()

# Rejestruj zużycie Claude (tokeny/koszt) z każdego wywołania do bazy.
llm_client.set_usage_recorder(lambda rec: db.insert_usage_event(conn, **rec))

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.middleware("http")
async def no_cache(request, call_next):
    """Wymusza rewalidację zasobów statycznych — zapobiega serwowaniu starego
    app.js/index.html z pamięci podręcznej przeglądarki po aktualizacji aplikacji."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@app.get("/api/taxonomy")
def get_taxonomy() -> dict:
    return tax.taxonomy_payload()


# --- Zadania -----------------------------------------------------------------

def _public_exercise(exercise_id: int, ex_type: str, topic: str, prompt: dict) -> ExercisePublic:
    """Buduje odpowiedź dla klienta z zapisanego zadania.

    JEDYNE miejsce budujące `ExercisePublic` — dzięki temu reguła „`answer`/`answer_notes`
    nigdy nie wychodzą do klienta" jest pilnowana w jednym punkcie."""
    items = [
        {"number": it.get("number", i + 1), "options": it.get("options", [])}
        for i, it in enumerate(prompt.get("items") or [])
    ]
    return ExercisePublic(
        id=exercise_id,
        type=ex_type,
        topic=topic,
        instructions=prompt.get("instructions", ""),
        question_text=prompt.get("question_text", ""),
        options=prompt.get("options"),
        items=items or None,
        key_word=prompt.get("key_word"),
    )


def _store_and_publish(ex_type: str, topic: str, generated: GeneratedExercise,
                       source: str) -> ExercisePublic:
    prompt = generated.model_dump()
    exercise_id = db.insert_exercise(conn, type=ex_type, topic=topic, prompt=prompt, source=source)
    return _public_exercise(exercise_id, ex_type, topic, prompt)


@app.post("/api/exercise", response_model=ExercisePublic)
def create_exercise(req: GenerateRequest) -> ExercisePublic:
    """Wydaje zadanie: najpierw z kolejki (natychmiast, bez kosztu), a gdy kolejka pusta —
    generuje wsadowo kilka zadań jednym wywołaniem modelu i wydaje pierwsze z nich."""
    if req.type not in tax.EXERCISE_TYPES:
        raise HTTPException(status_code=400, detail=f"Nieznany typ ćwiczenia: {req.type}")

    counts = db.topic_error_counts(conn)
    candidates = tax.topics_for_type(req.type)
    topic = req.topic or srs.choose_topic(candidates, counts) or (
        candidates[0] if candidates else "general"
    )

    queued = db.take_queued_exercise(conn, type=req.type, topic=topic)
    if queued is not None:
        return _public_exercise(queued["id"], queued["type"], queued["topic"], queued["prompt"])

    weak_points = [row["topic"] for row in counts[:5]]
    try:
        generated = llm_client.generate_exercises(
            req.type, topic, weak_points, lang=req.lang, count=llm_client.batch_size(req.type)
        )
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Pierwsze wydajemy od razu, resztę odkładamy do kolejki na kolejne kliknięcia.
    for extra in generated[1:]:
        db.insert_exercise(conn, type=req.type, topic=topic, prompt=extra.model_dump(),
                           source="in_app", served=False)
    return _store_and_publish(req.type, topic, generated[0], "in_app")


# --- Ocena -------------------------------------------------------------------

class _GradingTask:
    """Rozstrzygnięte wejście do oceny: skąd wzięło się zadanie i czym jest odpowiedź."""

    def __init__(self, *, ex_type: str, question_text: str, source: str,
                 model_answer: Optional[str] = None, key_word: Optional[str] = None,
                 options: Optional[list[str]] = None, items: Optional[list[dict]] = None,
                 student_answers: Optional[list[str]] = None, student_answer: str = ""):
        self.ex_type = ex_type
        self.question_text = question_text
        self.source = source
        self.model_answer = model_answer
        self.key_word = key_word
        self.options = options
        self.items = items
        self.student_answers = student_answers
        self.student_answer = student_answer

    @property
    def is_multi(self) -> bool:
        return bool(self.items) and self.student_answers is not None


def _resolve_grading_task(req: GradeRequest) -> _GradingTask:
    """Ustala treść zadania i klucz odpowiedzi — z bazy (zadanie z aplikacji)
    albo z żądania (zadanie wklejone z zewnątrz)."""
    if req.exercise_id is None:
        if req.type not in tax.EXERCISE_TYPES:
            raise HTTPException(status_code=400, detail=f"Nieznany typ ćwiczenia: {req.type}")
        if not req.question_text:
            raise HTTPException(status_code=400, detail="Brak treści zadania do oceny.")
        return _GradingTask(
            ex_type=req.type, question_text=req.question_text, source="external",
            key_word=req.key_word, student_answer=req.student_answer,
        )

    stored = db.get_exercise(conn, req.exercise_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania o tym id.")
    prompt = stored["prompt"]
    items = prompt.get("items")
    # Typ bierzemy z bazy — jest źródłem prawdy; `req.type` może być niespójne.
    ex_type = stored["type"]

    if items and req.student_answers is None:
        raise HTTPException(
            status_code=400,
            detail="To zadanie ma wiele luk — wyślij odpowiedzi w polu 'student_answers'.",
        )

    student_answer = req.student_answer
    if items:
        # Czytelny zapis do dziennika podejść: "1. B carry out; 2. A take; ..."
        student_answer = "; ".join(
            f"{items[i].get('number', i + 1)}. {a or '(brak)'}"
            for i, a in enumerate(req.student_answers[: len(items)])
        )

    return _GradingTask(
        ex_type=ex_type, question_text=prompt.get("question_text", ""), source="in_app",
        model_answer=prompt.get("answer"), key_word=prompt.get("key_word"),
        options=prompt.get("options"), items=items,
        student_answers=req.student_answers, student_answer=student_answer,
    )


def _run_grading(task: _GradingTask, lang: str) -> GradingResult:
    try:
        if task.is_multi:
            return llm_client.grade_items(
                task.ex_type, task.question_text, task.items, task.student_answers, lang=lang,
            )
        return llm_client.grade_answer(
            task.ex_type, task.question_text, task.student_answer,
            model_answer=task.model_answer, key_word=task.key_word,
            options=task.options, lang=lang,
        )
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _persist_grading(req: GradeRequest, task: _GradingTask, result: GradingResult) -> None:
    db.insert_attempt(
        conn,
        exercise_id=req.exercise_id,
        type=task.ex_type,
        student_answer=task.student_answer,
        is_correct=result.correct,
        grading=result.model_dump(),
    )
    for err in result.errors:
        db.insert_error(
            conn,
            source=task.source,
            exercise_type=task.ex_type,
            # Model potrafi wymyślić temat — sprowadzamy go do taksonomii,
            # inaczej błąd nie wpływałby na dobór zadań i psuł statystyki.
            topic=tax.normalize_topic(err.topic),
            student_text=err.student_text,
            correct_text=err.correct_text,
            explanation=err.explanation,
            severity=err.severity,
        )


@app.post("/api/grade")
def grade(req: GradeRequest) -> dict:
    task = _resolve_grading_task(req)
    result = _run_grading(task, req.lang)
    _persist_grading(req, task, result)
    return result.model_dump()


# --- Błędy -------------------------------------------------------------------

@app.get("/api/errors")
def get_errors(topic: str | None = Query(default=None),
               exercise_type: str | None = Query(default=None, alias="type"),
               lang: str = Query(default="pl")) -> list[dict]:
    rows = db.list_errors(conn, topic=topic, exercise_type=exercise_type)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"], lang)
    return rows


@app.get("/api/stats/topics")
def get_topic_stats(lang: str = Query(default="pl")) -> list[dict]:
    """Liczba błędów per temat — „słabe punkty" w zakładce Moje błędy."""
    rows = db.topic_error_counts(conn)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"], lang)
    return rows


# --- Zakładka Tipy (tryb skupienia na pojedynczym błędzie) -------------------

def _progress() -> dict:
    goal = db.get_int_setting(conn, "daily_goal", DEFAULT_DAILY_GOAL)
    return {"done": db.reviews_done_today(conn), "goal": goal, "streak": db.streak(conn, goal)}


def _choose_focus_error(exclude_id: int | None = None) -> dict | None:
    """Losuje błąd ważony częstością tematów (srs) + losowość w obrębie tematu."""
    counts = db.topic_error_counts(conn)
    if not counts:
        return None
    candidates = [c["topic"] for c in counts]
    topic = srs.choose_topic(candidates, counts) or candidates[0]
    errs = db.list_errors(conn, topic=topic, limit=500)
    if exclude_id is not None:
        remaining = [e for e in errs if e["id"] != exclude_id]
        if remaining:
            errs = remaining
        else:
            # Wylosowany temat miał tylko ten jeden błąd — sięgnij po dowolny inny,
            # żeby „Inny błąd" faktycznie zmieniało błąd.
            errs = [e for e in db.list_errors(conn, limit=2000) if e["id"] != exclude_id] or errs
    return random.choice(errs) if errs else None


@app.get("/api/tips/focus")
def tips_focus(lang: str = Query(default="pl"),
               exclude: int | None = Query(default=None)) -> dict:
    err = _choose_focus_error(exclude)
    if err is None:
        return {"error": None, "progress": _progress()}
    err["topic_label"] = tax.topic_label(err["topic"], lang)
    return {"error": err, "progress": _progress()}


@app.post("/api/tips/exercise", response_model=ExercisePublic)
def tips_exercise(req: TipExerciseRequest) -> ExercisePublic:
    err = db.get_error(conn, req.error_id)
    if err is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    try:
        ex_type, generated = llm_client.generate_drill(
            err["topic"], err["student_text"], err["correct_text"], err["explanation"], lang=req.lang
        )
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _store_and_publish(ex_type, err["topic"], generated, "drill")


@app.post("/api/tips/complete")
def tips_complete(req: CompleteRequest) -> dict:
    if db.get_error(conn, req.error_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    db.insert_review(conn, req.error_id)
    return _progress()


@app.get("/api/tips/progress")
def tips_progress() -> dict:
    return _progress()


@app.post("/api/tips/goal")
def tips_goal(req: GoalRequest) -> dict:
    goal = max(1, min(50, req.goal))
    db.set_setting(conn, "daily_goal", str(goal))
    return _progress()


# --- Statystyki (nauka + zużycie Claude) -------------------------------------

@app.get("/api/stats/learning")
def stats_learning(lang: str = Query(default="pl")) -> dict:
    data = db.learning_stats(conn)
    for row in data["by_type"]:
        meta = tax.EXERCISE_TYPES.get(row["type"], {})
        row["label"] = (meta.get("label_en") if lang == "en" else meta.get("label")) or row["type"]
    return data


@app.get("/api/stats/usage")
def stats_usage() -> dict:
    """Zużycie Claude + szacunek kosztu na API (bez narzutu trybu headless)."""
    data = db.usage_stats(conn)
    by_model = data.get("by_model", [])
    used_cost, assumed = pricing.lean_cost(by_model)
    sonnet_cost, _ = pricing.lean_cost(by_model, rate_override=pricing.sonnet_rate())
    data["lean"] = {
        "used_model": used_cost,
        "sonnet": sonnet_cost,
        # Modele bez potwierdzonej stawki — interfejs oznacza taki szacunek jako założony.
        "assumed_models": assumed,
    }
    return data


# Frontend statyczny — montowany na końcu, po trasach /api/*.
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
