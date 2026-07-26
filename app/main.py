"""FastAPI: API aplikacji FCE + serwowanie frontendu.

Uruchomienie:  uvicorn app.main:app --reload
Następnie:     http://localhost:8000
"""

from __future__ import annotations

import random
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import db
from . import fce_taxonomy as tax
from . import llm_client, srs
from .models import (
    CompleteRequest,
    ExercisePublic,
    GenerateRequest,
    GoalRequest,
    GradeRequest,
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


@app.post("/api/exercise", response_model=ExercisePublic)
def create_exercise(req: GenerateRequest) -> ExercisePublic:
    if req.type not in tax.EXERCISE_TYPES:
        raise HTTPException(status_code=400, detail=f"Nieznany typ ćwiczenia: {req.type}")

    candidates = tax.topics_for_type(req.type)
    topic = req.topic or srs.choose_topic(candidates, db.topic_error_counts(conn)) or (
        candidates[0] if candidates else "general"
    )

    # Słabe punkty = tematy z największą liczbą błędów (do delikatnego wplecenia).
    weak_points = [row["topic"] for row in db.topic_error_counts(conn)[:5]]

    try:
        generated = llm_client.generate_exercise(req.type, topic, weak_points, lang=req.lang)
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    exercise_id = db.insert_exercise(
        conn, type=req.type, topic=topic, prompt=generated.model_dump(), source="in_app"
    )
    return ExercisePublic(
        id=exercise_id,
        type=req.type,
        topic=topic,
        instructions=generated.instructions,
        question_text=generated.question_text,
        options=generated.options,
        key_word=generated.key_word,
    )


@app.post("/api/grade")
def grade(req: GradeRequest) -> dict:
    if req.type not in tax.EXERCISE_TYPES:
        raise HTTPException(status_code=400, detail=f"Nieznany typ ćwiczenia: {req.type}")

    model_answer = None
    key_word = req.key_word
    question_text = req.question_text
    options = None
    source = "external"

    if req.exercise_id is not None:
        stored = db.get_exercise(conn, req.exercise_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono zadania o tym id.")
        prompt = stored["prompt"]
        question_text = prompt.get("question_text", question_text)
        model_answer = prompt.get("answer")
        key_word = prompt.get("key_word", key_word)
        options = prompt.get("options")
        source = "in_app"

    if not question_text:
        raise HTTPException(status_code=400, detail="Brak treści zadania do oceny.")

    try:
        result = llm_client.grade_answer(
            req.type, question_text, req.student_answer,
            model_answer=model_answer, key_word=key_word, options=options, lang=req.lang,
        )
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Zapisz podejście i błędy do dziennika.
    db.insert_attempt(
        conn,
        exercise_id=req.exercise_id,
        type=req.type,
        student_answer=req.student_answer,
        is_correct=result.correct,
        grading=result.model_dump(),
    )
    for err in result.errors:
        db.insert_error(
            conn,
            source=source,
            exercise_type=req.type,
            topic=err.topic,
            student_text=err.student_text,
            correct_text=err.correct_text,
            explanation=err.explanation,
            severity=err.severity,
        )

    return result.model_dump()


@app.get("/api/errors")
def get_errors(topic: str | None = Query(default=None),
               type: str | None = Query(default=None),
               lang: str = Query(default="pl")) -> list[dict]:
    rows = db.list_errors(conn, topic=topic, exercise_type=type)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"], lang)
    return rows


@app.get("/api/stats")
def get_stats(lang: str = Query(default="pl")) -> list[dict]:
    rows = db.topic_error_counts(conn)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"], lang)
    return rows


# --- Zakładka Tipy (tryb skupienia na pojedynczym błędzie) -------------------

def _progress() -> dict:
    goal = int(db.get_setting(conn, "daily_goal", str(DEFAULT_DAILY_GOAL)))
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
        errs = [e for e in errs if e["id"] != exclude_id] or errs
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

    exercise_id = db.insert_exercise(
        conn, type=ex_type, topic=err["topic"], prompt=generated.model_dump(), source="drill"
    )
    return ExercisePublic(
        id=exercise_id,
        type=ex_type,
        topic=err["topic"],
        instructions=generated.instructions,
        question_text=generated.question_text,
        options=generated.options,
        key_word=generated.key_word,
    )


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
    return db.usage_stats(conn)


# Frontend statyczny — montowany na końcu, po trasach /api/*.
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
