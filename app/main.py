"""FastAPI: API aplikacji FCE + serwowanie frontendu.

Uruchomienie:  uvicorn app.main:app --reload
Następnie:     http://localhost:8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import db
from . import fce_taxonomy as tax
from . import llm_client, srs
from .models import ExercisePublic, GenerateRequest, GradeRequest

app = FastAPI(title="FCE Preparation")
conn = db.get_connection()

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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
        generated = llm_client.generate_exercise(req.type, topic, weak_points)
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
    source = "external"

    if req.exercise_id is not None:
        stored = db.get_exercise(conn, req.exercise_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono zadania o tym id.")
        prompt = stored["prompt"]
        question_text = prompt.get("question_text", question_text)
        model_answer = prompt.get("answer")
        key_word = prompt.get("key_word", key_word)
        source = "in_app"

    if not question_text:
        raise HTTPException(status_code=400, detail="Brak treści zadania do oceny.")

    try:
        result = llm_client.grade_answer(
            req.type, question_text, req.student_answer,
            model_answer=model_answer, key_word=key_word,
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
               type: str | None = Query(default=None)) -> list[dict]:
    rows = db.list_errors(conn, topic=topic, exercise_type=type)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"])
    return rows


@app.get("/api/stats")
def get_stats() -> list[dict]:
    rows = db.topic_error_counts(conn)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"])
    return rows


# Frontend statyczny — montowany na końcu, po trasach /api/*.
app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
