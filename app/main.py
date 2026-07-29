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
    DisputeRequest,
    ErrorCreate,
    ExercisePublic,
    GeneratedExercise,
    GenerateRequest,
    GoalRequest,
    GradeRequest,
    GradingResult,
    TipExerciseRequest,
)

DEFAULT_DAILY_GOAL = 5
# Ile ćwiczeń do danego błędu trzeba rozwiązać POPRAWNIE, by zaliczyć go do dziennego celu.
DRILL_CORRECT_TARGET = llm_client.ITEMS_PER_EXERCISE

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
        {
            "number": it.get("number", i + 1),
            "question_text": it.get("question_text"),
            "options": it.get("options"),
            "key_word": it.get("key_word"),
            "stem": it.get("stem"),
        }
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
    """Rozstrzygnięte wejście do oceny: treść zadania, klucz odpowiedzi i odpowiedź ucznia."""

    def __init__(self, *, ex_type: str, question_text: str, topic: str = "",
                 model_answer: Optional[str] = None, key_word: Optional[str] = None,
                 options: Optional[list[str]] = None, items: Optional[list[dict]] = None,
                 student_answers: Optional[list[str]] = None, student_answer: str = ""):
        self.ex_type = ex_type
        self.question_text = question_text
        # Temat zadania — awaryjny temat propozycji błędu, gdy model go nie poda.
        self.topic = topic
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
            ex_type=req.type, question_text=req.question_text,
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
        ex_type=ex_type, question_text=prompt.get("question_text", ""), topic=stored["topic"],
        model_answer=prompt.get("answer"), key_word=prompt.get("key_word"),
        options=prompt.get("options"), items=items,
        student_answers=req.student_answers, student_answer=student_answer,
    )


def _run_grading(task: _GradingTask, lang: str) -> GradingResult:
    try:
        if task.is_multi:
            return llm_client.grade_items(
                task.ex_type, task.question_text, task.items, task.student_answers, lang=lang,
                topic=task.topic,
            )
        return llm_client.grade_answer(
            task.ex_type, task.question_text, task.student_answer,
            model_answer=task.model_answer, key_word=task.key_word,
            options=task.options, lang=lang,
        )
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _persist_grading(req: GradeRequest, task: _GradingTask, result: GradingResult) -> None:
    """Zapisuje podejście. Błędów NIE zapisuje — ocena zwraca je jako propozycje,
    a do dziennika trafiają dopiero przez `POST /api/errors`, gdy uczeń je zatwierdzi.
    Lepiej zatwierdzać pojedynczo niż szukać potem śmieci do usunięcia."""
    for err in result.errors:
        # Model potrafi wymyślić temat — sprowadzamy go do taksonomii już tutaj,
        # żeby uczeń widział prawdziwą etykietę i zatwierdzał to, co zostanie zapisane.
        err.topic = tax.normalize_topic(err.topic)
    db.insert_attempt(
        conn,
        exercise_id=req.exercise_id,
        type=task.ex_type,
        student_answer=task.student_answer,
        is_correct=result.correct,
        grading=result.model_dump(),
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
               limit: int = Query(default=2000, ge=1, le=100_000),
               lang: str = Query(default="pl")) -> list[dict]:
    rows = db.list_errors(conn, topic=topic, exercise_type=exercise_type, limit=limit)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"], lang)
    return rows


@app.post("/api/errors")
def add_error(req: ErrorCreate, lang: str = Query(default="pl")) -> dict:
    """Dopisuje do dziennika błąd zatwierdzony przez ucznia (ocena sama nic nie zapisuje).

    Typ i źródło ustalamy z zapisanego zadania, gdy jest znane — dane o pochodzeniu
    błędu nie mogą zależeć od tego, co przyśle przeglądarka."""
    if not req.student_text.strip():
        raise HTTPException(status_code=400, detail="Brak treści błędu do zapisania.")

    exercise_type, source = req.exercise_type or "external", "external"
    if req.exercise_id is not None:
        stored = db.get_exercise(conn, req.exercise_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono zadania o tym id.")
        exercise_type, source = stored["type"], "in_app"

    topic = tax.normalize_topic(req.topic)
    error_id = db.insert_error(
        conn, source=source, exercise_type=exercise_type, topic=topic,
        student_text=req.student_text, correct_text=req.correct_text,
        explanation=req.explanation, severity=req.severity,
    )
    return {"id": error_id, "topic": topic, "topic_label": tax.topic_label(topic, lang)}


@app.delete("/api/errors/{error_id}")
def remove_error(error_id: int) -> dict:
    """Usuwa wpis z dziennika (np. gdy błąd jest opanowany albo zapisany omyłkowo).

    Zapisane powtórki zostają — dzienny postęp i seria opierają się na tym, co
    naprawdę przerobiłeś, więc usunięcie błędu nie cofa dziś zdobytego celu.
    """
    if not db.delete_error(conn, error_id):
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    return {"deleted": error_id}


@app.get("/api/stats/topics")
def get_topic_stats(lang: str = Query(default="pl")) -> list[dict]:
    """Liczba błędów per temat — „słabe punkty" w zakładce Moje błędy."""
    rows = db.topic_error_counts(conn)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"], lang)
    return rows


# --- Zakładka „Ćwicz błędy" (tryb skupienia na pojedynczym błędzie) -------------------

def _progress(error_id: int | None = None) -> dict:
    """Postęp dziennego celu. Z `error_id` dołącza też postęp ćwiczeń do tego błędu."""
    goal = db.get_int_setting(conn, "daily_goal", DEFAULT_DAILY_GOAL)
    out = {"done": db.reviews_done_today(conn), "goal": goal, "streak": db.streak(conn, goal)}
    if error_id is not None:
        out["drill"] = {
            "correct": db.drill_correct_today(conn, error_id),
            "target": DRILL_CORRECT_TARGET,
        }
    return out


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
    return {"error": err, "progress": _progress(err["id"])}


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
    """Zapisuje wynik zestawu ćwiczeń do błędu. Błąd liczy się do dziennego celu
    dopiero po uzbieraniu `DRILL_CORRECT_TARGET` poprawnych ćwiczeń w danym dniu
    (narastająco — nie trzeba trafić wszystkich w jednym podejściu)."""
    if db.get_error(conn, req.error_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")

    total = max(0, req.total_items)
    correct = max(0, min(req.correct_items, total))
    if total:
        db.insert_drill_score(conn, error_id=req.error_id,
                              correct_items=correct, total_items=total)

    if db.drill_correct_today(conn, req.error_id) >= DRILL_CORRECT_TARGET:
        db.insert_review(conn, req.error_id)  # idempotentne w obrębie dnia
    return _progress(req.error_id)


@app.get("/api/tips/progress")
def tips_progress() -> dict:
    return _progress()


@app.post("/api/tips/goal")
def tips_goal(req: GoalRequest) -> dict:
    goal = max(1, min(50, req.goal))
    db.set_setting(conn, "daily_goal", str(goal))
    return _progress()


# --- Zastrzeżenia do wyjaśnień ------------------------------------------------

def _exercise_context(prompt: dict) -> str:
    """Renderuje pełną, dokładną treść zadania wraz z kluczem odpowiedzi.

    To materiał dowodowy dla weryfikacji zastrzeżenia: model ma porównać każdą formę
    przytoczoną w kwestionowanym wyjaśnieniu z tym, co RZECZYWIŚCIE było w zadaniu."""
    parts = []
    if prompt.get("question_text"):
        parts.append(prompt["question_text"])
    for idx, item in enumerate(prompt.get("items") or []):
        number = item.get("number", idx + 1)
        line = f"[{number}]"
        if item.get("question_text"):
            line += f" {item['question_text']}"
        if item.get("stem"):
            line += f" | wyraz podstawowy: {item['stem']}"
        if item.get("key_word"):
            line += f" | słowo-klucz: {item['key_word']}"
        if item.get("options"):
            line += f" | warianty: {item['options']}"
        line += f" | poprawna odpowiedź: {item.get('answer')}"
        parts.append(line)
    if not prompt.get("items"):
        if prompt.get("options"):
            parts.append(f"warianty: {prompt['options']}")
        if prompt.get("key_word"):
            parts.append(f"słowo-klucz: {prompt['key_word']}")
        if prompt.get("answer"):
            parts.append(f"poprawna odpowiedź: {prompt['answer']}")
    return "\n".join(parts)


@app.post("/api/dispute")
def create_dispute(req: DisputeRequest) -> dict:
    """Weryfikuje zastrzeżenie do wyjaśnienia. NIE zmienia jeszcze żadnych danych —
    ewentualną korektę stosuje dopiero `/api/dispute/{id}/apply` po zatwierdzeniu."""
    if req.scope not in ("item", "error"):
        raise HTTPException(status_code=400, detail=f"Nieznany zakres zastrzeżenia: {req.scope}")
    if not req.disputed_text.strip():
        raise HTTPException(status_code=400, detail="Brak treści kwestionowanego wyjaśnienia.")

    context, answers_text = "", ""
    if req.exercise_id is not None:
        stored = db.get_exercise(conn, req.exercise_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono zadania o tym id.")
        context = _exercise_context(stored["prompt"])
        attempt = db.latest_attempt_for_exercise(conn, req.exercise_id)
        if attempt:
            answers_text = attempt["student_answer"]

    if req.error_id is not None:
        err = db.get_error(conn, req.error_id)
        if err is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
        context = (context + "\n" if context else "") + (
            f"Wpis w dzienniku błędów: „{err['student_text']}\" → „{err['correct_text']}\" "
            f"(temat: {err['topic']})"
        )
        answers_text = answers_text or err["student_text"]

    try:
        review = llm_client.review_dispute(
            disputed_text=req.disputed_text,
            user_comment=req.comment,
            exercise_context=context,
            student_answers_text=answers_text,
            lang=req.lang,
        )
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    dispute_id = db.insert_dispute(
        conn, scope=req.scope, disputed_text=req.disputed_text, user_comment=req.comment,
        exercise_id=req.exercise_id, item_number=req.item_number, error_id=req.error_id,
        verdict=review["verdict"], revised_text=review["revised_explanation"],
        student_was_right=review["student_was_right"],
    )

    # Co dokładnie zmieni zatwierdzenie korekty — pokazujemy to uczniowi wprost,
    # zamiast po cichu modyfikować dziennik.
    changes: list[str] = []
    if review["student_was_right"]:
        if req.error_id is not None:
            changes.append("usunięcie tego wpisu z dziennika błędów")
        if req.exercise_id is not None and req.item_number is not None:
            changes.append("zaliczenie tej pozycji jako poprawnej w zapisanym wyniku")

    return {
        "dispute_id": dispute_id,
        "verdict": review["verdict"],
        "revised_explanation": review["revised_explanation"],
        "reasoning": review["reasoning"],
        "student_was_right": review["student_was_right"],
        "proposed_changes": changes,
    }


@app.post("/api/dispute/{dispute_id}/apply")
def apply_dispute(dispute_id: int) -> dict:
    """Stosuje korektę danych po zatwierdzeniu przez ucznia."""
    dispute = db.get_dispute(conn, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono zastrzeżenia o tym id.")
    if dispute["applied_at"]:
        raise HTTPException(status_code=400, detail="Ta korekta została już zastosowana.")
    if not dispute["student_was_right"]:
        raise HTTPException(
            status_code=400,
            detail="Nie ma czego poprawiać — model nie uznał odpowiedzi za poprawną.",
        )

    applied: list[str] = []

    if dispute["error_id"] is not None and db.delete_error(conn, dispute["error_id"]):
        applied.append("usunięto wpis z dziennika błędów")

    # Zapisany wynik: pozycja zostaje zaliczona, a ocena i wynik punktowy przeliczone.
    if dispute["exercise_id"] is not None and dispute["item_number"] is not None:
        attempt = db.latest_attempt_for_exercise(conn, dispute["exercise_id"])
        if attempt:
            grading = attempt["grading"]
            items = grading.get("items") or []
            changed = False
            for item in items:
                if item.get("number") == dispute["item_number"] and not item.get("correct"):
                    item["correct"] = True
                    item["comment"] = dispute["revised_text"] or item.get("comment", "")
                    item["option_notes"] = None
                    changed = True
            if changed:
                correct_count = sum(1 for i in items if i.get("correct"))
                grading["score"] = f"{correct_count}/{len(items)}"
                grading["correct"] = correct_count == len(items)
                grading["errors"] = [
                    e for e in (grading.get("errors") or [])
                    if e.get("item_number") != dispute["item_number"]
                ]
                db.update_attempt_grading(
                    conn, attempt["id"], grading=grading, is_correct=grading["correct"]
                )
                applied.append(f"poprawiono zapisany wynik na {grading['score']}")

    db.mark_dispute_applied(conn, dispute_id)
    return {"applied": applied or ["brak zmian do wprowadzenia"]}


# --- Statystyki (nauka + zużycie Claude) -------------------------------------

@app.get("/api/stats/learning")
def stats_learning(lang: str = Query(default="pl")) -> dict:
    data = db.learning_stats(conn)
    data["disputes"] = db.dispute_stats(conn)
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
