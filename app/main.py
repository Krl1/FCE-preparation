"""FastAPI: API aplikacji FCE + serwowanie frontendu.

Uruchomienie:  uvicorn app.main:app --reload
Następnie:     http://localhost:8000
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import db
from . import fce_taxonomy as tax
from . import flashcards, grouping, llm_client, pricing, srs, streak
from .models import (
    CardGrade,
    CardGradeNew,
    CardSettings,
    CompleteRequest,
    DisputeRequest,
    ErrorCreate,
    ErrorGroupUpdate,
    ExercisePublic,
    GeneratedExercise,
    GenerateRequest,
    GoalRequest,
    GradeRequest,
    GradingResult,
    GroupUpdate,
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


def _emptied_group(previous: int | None, new_group_id: int | None = None) -> tuple:
    """Grupa, która właśnie została bez wpisów: `(id, rule)` albo `(None, None)`.

    Wspólne dla `remove_error` i `patch_error_group` — obie ścieżki kończą się tym
    samym pytaniem w interfejsie, więc muszą zgłaszać osierocenie identycznie.
    Nazwa reguły leci razem z id, żeby frontend mógł zapytać „usunąć grupę X?"
    bez dodatkowego zapytania o listę grup.
    """
    if previous is None or previous == new_group_id:
        return None, None
    if db.group_member_count(conn, previous) != 0:
        return None, None
    grp = db.get_group(conn, previous)
    return previous, (grp["rule"] if grp else None)


@app.delete("/api/errors/{error_id}")
def remove_error(error_id: int) -> dict:
    """Usuwa wpis z dziennika (np. gdy błąd jest opanowany albo zapisany omyłkowo).

    Zapisane powtórki zostają — dzienny postęp i seria opierają się na tym, co
    naprawdę przerobiłeś, więc usunięcie błędu nie cofa dziś zdobytego celu.

    `emptied_group_id` niesie informację, że po tym usunięciu grupa została pusta.
    Grupa ZOSTAJE — frontend tylko pyta, czy usunąć ją razem z wpisem.
    """
    previous = db.group_of_error(conn, error_id)
    if not db.delete_error(conn, error_id):
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    emptied, emptied_rule = _emptied_group(previous)
    return {"deleted": error_id, "emptied_group_id": emptied,
            "emptied_group_rule": emptied_rule}


@app.get("/api/stats/topics")
def get_topic_stats(lang: str = Query(default="pl")) -> list[dict]:
    """Liczba błędów per temat — „słabe punkty" w zakładce Moje błędy."""
    rows = db.topic_error_counts(conn)
    for row in rows:
        row["topic_label"] = tax.topic_label(row["topic"], lang)
    return rows


# --- Zakładka „Ćwicz błędy" (tryb skupienia na pojedynczym błędzie) -------------------

def _progress(error_id: int | None = None, group_id: int | None = None) -> dict:
    """Postęp dziennego celu. Z `error_id` lub `group_id` dołącza też postęp ćwiczeń
    do tej jednostki — próg jest wspólny, bo grupa liczy się jak jeden błąd."""
    goal = db.get_int_setting(conn, "daily_goal", DEFAULT_DAILY_GOAL)
    out = {"done": db.reviews_done_today(conn), "goal": goal,
           **streak.state(db.reviews_per_day(conn), goal)}
    if error_id is not None:
        out["drill"] = {
            "correct": db.drill_correct_today(conn, error_id),
            "target": DRILL_CORRECT_TARGET,
        }
    elif group_id is not None:
        out["drill"] = {
            "correct": db.group_drill_correct_today(conn, group_id),
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


def _pick_group(groups: list[dict]) -> dict:
    """Losuje grupę ważoną LICZBĄ jej wpisów — reguła złamana sześć razy ma wracać
    częściej niż jednorazowe potknięcie (spec: „waga z liczby wpisów w grupie").
    Baza 1.0 to ta sama eksploracja co `srs.BASE_WEIGHT`: pusta grupa nadal daje się
    wylosować, bo pustą grupę nadal da się ćwiczyć."""
    weights = [1.0 + float(g.get("member_count") or 0) for g in groups]
    return random.choices(groups, weights=weights, k=1)[0]


def _choose_focus_group(exclude_id: int | None = None) -> dict | None:
    """Losuje grupę ważoną częstością tematów (srs) + liczbą wpisów w obrębie tematu.

    Ta sama mechanika co `_choose_focus_error`, tylko materiałem są grupy, a w obrębie
    tematu losowanie nie jest równomierne (patrz `_pick_group`)."""
    counts = db.group_topic_counts(conn)
    if not counts:
        return None
    candidates = [c["topic"] for c in counts]
    topic = srs.choose_topic(candidates, counts) or candidates[0]
    groups = [g for g in db.list_groups(conn) if g["topic"] == topic]
    if exclude_id is not None:
        remaining = [g for g in groups if g["id"] != exclude_id]
        groups = remaining or [g for g in db.list_groups(conn) if g["id"] != exclude_id] or groups
    return _pick_group(groups) if groups else None


@app.get("/api/tips/focus")
def tips_focus(lang: str = Query(default="pl"),
               mode: str = Query(default="error"),
               exclude: int | None = Query(default=None)) -> dict:
    if mode == "group":
        grp = _choose_focus_group(exclude)
        if grp is None:
            return {"error": None, "group": None, "progress": _progress()}
        grp["topic_label"] = tax.topic_label(grp["topic"], lang)
        return {"error": None, "group": grp,
                "progress": _progress(group_id=grp["id"])}

    err = _choose_focus_error(exclude)
    if err is None:
        return {"error": None, "group": None, "progress": _progress()}
    err["topic_label"] = tax.topic_label(err["topic"], lang)
    return {"error": err, "group": None, "progress": _progress(err["id"])}


@app.post("/api/tips/exercise", response_model=ExercisePublic)
def tips_exercise(req: TipExerciseRequest) -> ExercisePublic:
    if req.group_id is not None:
        grp = db.get_group(conn, req.group_id)
        if grp is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
        members = db.list_group_members(conn, req.group_id)
        # Pusta grupa też daje się ćwiczyć — konteksty są dodatkiem, nie warunkiem.
        contexts = [f"{m['student_text']} → {m['correct_text']}" for m in members]
        try:
            ex_type, generated = llm_client.generate_drill(
                grp["topic"], "", "", grp["explanation"],
                lang=req.lang, contexts=contexts, rule=grp["rule"],
            )
        except llm_client.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _store_and_publish(ex_type, grp["topic"], generated, "drill")

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
    """Zapisuje wynik zestawu ćwiczeń do jednostki (błędu albo grupy). Jednostka liczy
    się do dziennego celu po uzbieraniu `DRILL_CORRECT_TARGET` poprawnych ćwiczeń
    w danym dniu — narastająco, i tak samo dla obu trybów."""
    total = max(0, req.total_items)
    correct = max(0, min(req.correct_items, total))

    if req.group_id is not None:
        if db.get_group(conn, req.group_id) is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
        if total:
            db.insert_group_drill_score(conn, group_id=req.group_id,
                                        correct_items=correct, total_items=total)
        if db.group_drill_correct_today(conn, req.group_id) >= DRILL_CORRECT_TARGET:
            db.insert_group_review(conn, req.group_id)
        return _progress(group_id=req.group_id)

    if db.get_error(conn, req.error_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
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


# --- Grupy błędów -------------------------------------------------------------

# Porcja jednego wywołania modelu. 196 wpisów w jednym żądaniu grozi obcięciem
# odpowiedzi przy FCE_LLM_TIMEOUT = 180 s, więc pierwszy przebieg idzie porcjami.
GROUP_CHUNK_SIZE = 60


def _run_grouping(lang: str) -> dict:
    """Przypisuje wszystkie nieprzypisane wpisy, porcjami. Każda porcja widzi grupy
    utworzone przez poprzednie, więc druga porcja może dopiąć się do świeżej reguły."""
    pending = db.list_ungrouped_errors(conn)
    assigned = created = unassigned = 0

    for chunk in grouping.chunks(pending, GROUP_CHUNK_SIZE):
        existing = db.list_groups(conn)
        try:
            raw = llm_client.group_errors(
                errors=chunk,
                existing_groups=[{"id": g["id"], "rule": g["rule"], "topic": g["topic"]}
                                 for g in existing],
                lang=lang,
            )
        except llm_client.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        plan = grouping.plan_assignments(
            raw, [e["id"] for e in chunk], {g["id"] for g in existing}
        )
        for error_id, group_id in plan.to_existing.items():
            db.set_error_group(conn, error_id, group_id)
            assigned += 1
        for new in plan.new_groups:
            group_id = db.insert_group(conn, rule=new.rule, explanation=new.explanation,
                                       topic=new.topic)
            created += 1
            for error_id in new.error_ids:
                db.set_error_group(conn, error_id, group_id)
        unassigned += len(plan.unassigned)

    return {"assigned": assigned, "created": created, "unassigned": unassigned}


@app.get("/api/groups")
def get_groups(lang: str = Query(default="pl")) -> dict:
    groups = db.list_groups(conn)
    for g in groups:
        g["topic_label"] = tax.topic_label(g["topic"], lang)
    return {"groups": groups, "ungrouped": db.count_ungrouped_errors(conn)}


@app.get("/api/groups/{group_id}/members")
def get_group_members(group_id: int, lang: str = Query(default="pl")) -> list[dict]:
    if db.get_group(conn, group_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
    members = db.list_group_members(conn, group_id)
    for m in members:
        m["topic_label"] = tax.topic_label(m["topic"], lang)
    return members


@app.post("/api/groups/assign")
def assign_groups(lang: str = Query(default="pl")) -> dict:
    """Przyrostowe scalanie: bierze tylko wpisy bez grupy."""
    return _run_grouping(lang)


@app.post("/api/groups/regroup")
def regroup_all(lang: str = Query(default="pl")) -> dict:
    """Pełne przeliczenie od zera. KASUJE ręczne poprawki i puste grupy — frontend
    pyta o potwierdzenie, zanim tu trafi."""
    db.clear_all_groups(conn)
    return _run_grouping(lang)


@app.patch("/api/groups/{group_id}")
def patch_group(group_id: int, req: GroupUpdate) -> dict:
    if not db.update_group(conn, group_id, rule=req.rule, explanation=req.explanation):
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
    return {"updated": group_id}


@app.delete("/api/groups/{group_id}")
def remove_group(group_id: int) -> dict:
    """Usuwa grupę; jej wpisy wracają do nieprzypisanych. Zaliczenia zostają."""
    if not db.delete_group(conn, group_id):
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
    return {"deleted": group_id}


@app.patch("/api/errors/{error_id}/group")
def patch_error_group(error_id: int, req: ErrorGroupUpdate) -> dict:
    """Przepina wpis do innej grupy albo go odpina.

    `emptied_group_id` mówi frontendowi, że stara grupa właśnie osierociała — pusta
    grupa ZOSTAJE, a o jej usunięciu decyduje uczeń."""
    if db.get_error(conn, error_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    if req.group_id is not None and db.get_group(conn, req.group_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")

    previous = db.group_of_error(conn, error_id)
    db.set_error_group(conn, error_id, req.group_id)
    emptied, emptied_rule = _emptied_group(previous, req.group_id)
    return {"error_id": error_id, "group_id": req.group_id,
            "emptied_group_id": emptied, "emptied_group_rule": emptied_rule}


# --- Fiszki -------------------------------------------------------------------

DEFAULT_NEW_CARDS_PER_DAY = 20


def _today_str() -> str:
    return date.today().isoformat()


def _render_card(source_kind: str, source: dict, card: dict | None, lang: str) -> dict:
    """Treść karty. Renderujemy ze ŹRÓDŁA, więc poprawione w dzienniku wyjaśnienie
    widać natychmiast; `*_override` (jeśli jest) wygrywa, bo to treść ulepszona modelem."""
    if card and card.get("front_override") and card.get("back_override"):
        return {"front": card["front_override"], "back": card["back_override"]}
    if source_kind == "group":
        members = db.list_group_members(conn, source["id"])
        contexts = [f"{m['student_text']} → {m['correct_text']}" for m in members[:5]]
        back = source["explanation"]
        if contexts:
            back += "\n\n" + "\n".join(contexts)
        return {"front": source["rule"], "back": back}
    return {"front": source["student_text"],
            "back": f"{source['correct_text']}\n\n{source['explanation']}"}


def _load_source(source_kind: str, source_id: int) -> dict | None:
    return (db.get_group(conn, source_id) if source_kind == "group"
            else db.get_error(conn, source_id))


def _cards_progress() -> dict:
    today = _today_str()
    return {
        "done_today": db.cards_done_today(conn),
        "overdue": db.cards_overdue(conn, today),
        "due_now": len(db.cards_due(conn, today)),
        "new_limit": db.get_int_setting(conn, "cards_new_per_day", DEFAULT_NEW_CARDS_PER_DAY),
        # Rozróżnia „wszystko na dziś zrobione" od „nie ma z czego robić fiszek".
        # Bez tego pusty ekran mówiłby to samo w obu przypadkach.
        "total_sources": db.count_card_sources(conn),
    }


@app.get("/api/cards/session")
def cards_session(lang: str = Query(default="pl"),
                  topic: str | None = Query(default=None)) -> dict:
    """Kolejka na dziś. NIE wywołuje modelu — cała wartość fiszek to natychmiastowość."""
    today = _today_str()
    limit = db.get_int_setting(conn, "cards_new_per_day", DEFAULT_NEW_CARDS_PER_DAY)
    queue = flashcards.build_queue(
        db.cards_due(conn, today, topic=topic),
        db.sources_without_card(conn, topic=topic),
        limit,
    )
    out = []
    for item in queue:
        source = _load_source(item.source_kind, item.source_id)
        if source is None:
            continue  # źródło zniknęło między zapytaniami — pomijamy, nie wywalamy sesji
        card = db.get_card(conn, item.card_id) if item.card_id else None
        rendered = _render_card(item.source_kind, source, card, lang)
        # Pełne źródło leci w odpowiedzi, bo przycisk przy karcie upartej skacze do
        # „Ćwicz błędy" z TĄ jednostką — a setFocus/setFocusGroup czytają nazwane pola.
        # Grupie trzeba jeszcze dołożyć member_count: get_group go nie zwraca, a
        # setFocusGroup renderuje z niego licznik kontekstów.
        source_payload = dict(source)
        source_payload["topic_label"] = tax.topic_label(source["topic"], lang)
        if item.source_kind == "group":
            source_payload["member_count"] = db.group_member_count(conn, source["id"])
        out.append({
            "card_id": item.card_id,
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "topic": source["topic"],
            "topic_label": tax.topic_label(source["topic"], lang),
            "source": source_payload,
            "leech": flashcards.is_leech(
                db.card_unknown_count(conn, item.card_id)) if item.card_id else False,
            **rendered,
        })
    return {"cards": out, "progress": _cards_progress()}


def _apply_grade(card: dict, grade: str, *, is_new: bool = False) -> dict:
    # Świeżo utworzona karta oceniona jako „nie umiem" zostaje w DZISIEJSZEJ kolejce —
    # dopiero pierwsze „umiem" rusza drabinkę. Bez tego wyjątku next_interval() cofnąłby
    # ją od razu na jutro (LADDER[0]=1 niezależnie od current_days), a karta zniknęłaby
    # z sesji, zanim uczeń zdążyłby ją poprawić (np. przyciskiem „ulepsz").
    if is_new and grade != "known":
        interval = 0
    else:
        interval = flashcards.next_interval(int(card["interval_days"]), grade)
    db.update_card_schedule(conn, card["id"], interval_days=interval,
                            due_on=flashcards.due_date(date.today(), interval))
    db.insert_card_review(conn, card_id=card["id"], grade=grade)
    return {
        "card_id": card["id"],
        "interval_days": interval,
        "due_on": flashcards.due_date(date.today(), interval),
        "leech": flashcards.is_leech(db.card_unknown_count(conn, card["id"])),
        "progress": _cards_progress(),
    }


@app.post("/api/cards/{card_id}/grade")
def grade_card(card_id: int, req: CardGrade) -> dict:
    card = db.get_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono fiszki o tym id.")
    return _apply_grade(card, req.grade)


@app.post("/api/cards/grade-new")
def grade_new_card(req: CardGradeNew) -> dict:
    """Pierwsza ocena źródła: wiersz karty powstaje dopiero tutaj."""
    if _load_source(req.source_kind, req.source_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono źródła tej fiszki.")
    existing = db.get_card_by_source(conn, req.source_kind, req.source_id)
    is_new = existing is None
    if existing is None:
        card_id = db.create_card(conn, source_kind=req.source_kind, source_id=req.source_id,
                                 due_on=_today_str(), interval_days=0)
        existing = db.get_card(conn, card_id)
    return _apply_grade(existing, req.grade, is_new=is_new)


@app.post("/api/cards/{card_id}/improve")
def improve_card(card_id: int, lang: str = Query(default="pl")) -> dict:
    """Jedyne miejsce w fiszkach, które kosztuje wywołanie modelu — i tylko na kliknięcie."""
    card = db.get_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono fiszki o tym id.")
    source = _load_source(card["source_kind"], card["source_id"])
    if source is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono źródła tej fiszki.")
    if card["source_kind"] == "group":
        student, correct = source["rule"], source["rule"]
    else:
        student, correct = source["student_text"], source["correct_text"]
    try:
        front, back = llm_client.improve_card(student, correct, source["explanation"], lang=lang)
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.set_card_override(conn, card_id, front=front, back=back)
    return {"front": front, "back": back}


@app.get("/api/cards/progress")
def cards_progress() -> dict:
    return _cards_progress()


@app.post("/api/cards/settings")
def cards_settings(req: CardSettings) -> dict:
    db.set_setting(conn, "cards_new_per_day", str(max(0, min(200, req.new_per_day))))
    return _cards_progress()


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
