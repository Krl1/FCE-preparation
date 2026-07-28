"""Testy endpointów (FastAPI TestClient) — bez wywoływania prawdziwego modelu.

`llm_client._invoke` jest podstawiany, więc testy są szybkie i deterministyczne.
"""

import importlib
import json
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_ctx(tmp_path, monkeypatch):
    """Świeża baza + świeżo zaimportowana aplikacja (połączenie powstaje przy imporcie).

    Uwaga: usunięcie modułu z `sys.modules` NIE wystarcza — pakiet `app` trzyma
    referencję w atrybucie (`app.main`), więc `import` zwróciłby stary moduł
    ze starym połączeniem i stan wyciekałby między testami.
    """
    monkeypatch.setenv("FCE_DB_PATH", str(tmp_path / "api.db"))
    import app as app_pkg

    for name in ("main", "db"):
        sys.modules.pop(f"app.{name}", None)
        if hasattr(app_pkg, name):
            delattr(app_pkg, name)

    main_mod = importlib.import_module("app.main")
    with TestClient(main_mod.app) as client:
        yield client, main_mod


def _stub_llm(main_mod, monkeypatch, payload, counter=None):
    def fake_invoke(prompt, kind="other"):
        if counter is not None:
            counter.append(kind)
        return json.dumps(payload)

    monkeypatch.setattr(main_mod.llm_client, "_invoke", fake_invoke)


# --- /api/grade: ścieżka wieloczęściowa --------------------------------------

MCQ_PROMPT = {
    "instructions": "Wybierz",
    "question_text": "Tekst (1) ______ i (2) ______.",
    "items": [
        {"number": 1, "options": ["A warm", "B heat"], "answer": "A warm"},
        {"number": 2, "options": ["A pay", "B give"], "answer": "A pay"},
    ],
}

GRADE_ITEMS_REPLY = {
    "feedback": "Wynik 1/2.",
    "items": [
        {"number": 1, "comment": "ok", "option_notes": None},
        {"number": 2, "comment": "źle", "option_notes": [
            {"option": "A pay", "is_correct": True, "comment": "pasuje"},
            {"option": "B give", "is_correct": False, "comment": "nie pasuje"},
        ]},
    ],
    # Celowo wymyślony temat — serwer musi go sprowadzić do taksonomii.
    "errors": [{"topic": "past_simple", "student_text": "B give", "correct_text": "A pay",
                "explanation": "e", "severity": "major"}],
}


def test_grade_multi_persists_attempt_and_normalizes_topic(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _stub_llm(main_mod, monkeypatch, GRADE_ITEMS_REPLY)
    ex_id = main_mod.db.insert_exercise(
        main_mod.conn, type="uoe_part1_mcq_cloze", topic="collocations", prompt=MCQ_PROMPT
    )

    res = client.post("/api/grade", json={
        # Celowo NIEZGODNY typ — serwer ma użyć typu z bazy.
        "type": "writing_essay",
        "exercise_id": ex_id,
        "student_answers": ["A warm", "B give"],
        "lang": "pl",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["score"] == "1/2"
    assert body["correct"] is False
    assert [i["correct"] for i in body["items"]] == [True, False]

    # Podejście zapisane z typem Z BAZY, nie z żądania.
    attempts = main_mod.conn.execute("SELECT type, is_correct, student_answer FROM attempts").fetchall()
    assert len(attempts) == 1
    assert attempts[0]["type"] == "uoe_part1_mcq_cloze"
    assert attempts[0]["is_correct"] == 0
    assert "2. B give" in attempts[0]["student_answer"]

    # Wymyślony temat zmapowany na 'language'.
    errors = main_mod.db.list_errors(main_mod.conn)
    assert len(errors) == 1
    assert errors[0]["topic"] == "language"
    assert errors[0]["exercise_type"] == "uoe_part1_mcq_cloze"


def test_grade_multi_without_student_answers_is_rejected(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _stub_llm(main_mod, monkeypatch, {"feedback": "x", "items": [], "errors": []})
    ex_id = main_mod.db.insert_exercise(
        main_mod.conn, type="uoe_part1_mcq_cloze", topic="collocations", prompt=MCQ_PROMPT
    )
    res = client.post("/api/grade", json={
        "type": "uoe_part1_mcq_cloze", "exercise_id": ex_id, "student_answer": "A warm",
    })
    assert res.status_code == 400
    assert "student_answers" in res.json()["detail"]
    # Nic nie zostało zapisane.
    assert main_mod.conn.execute("SELECT COUNT(*) n FROM attempts").fetchone()["n"] == 0


def test_grade_external_requires_question_text(app_ctx):
    client, _ = app_ctx
    res = client.post("/api/grade", json={"type": "uoe_part2_open_cloze", "student_answer": "x"})
    assert res.status_code == 400


# --- /api/exercise: kolejka i generowanie wsadowe ----------------------------

BATCH_REPLY = {
    "exercises": [
        {"instructions": "i1", "question_text": "q1 ______", "answer": "a1"},
        {"instructions": "i2", "question_text": "q2 ______", "answer": "a2"},
        {"instructions": "i3", "question_text": "q3 ______", "answer": "a3"},
    ]
}


def test_exercise_batches_once_then_serves_from_queue(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    calls = []
    _stub_llm(main_mod, monkeypatch, BATCH_REPLY, counter=calls)
    body = {"type": "uoe_part2_open_cloze", "topic": "tenses", "lang": "pl"}

    first = client.post("/api/exercise", json=body)
    assert first.status_code == 200
    assert len(calls) == 1, "pierwsze żądanie generuje wsad"

    second = client.post("/api/exercise", json=body)
    third = client.post("/api/exercise", json=body)
    assert second.status_code == third.status_code == 200
    assert len(calls) == 1, "kolejne żądania mają iść z kolejki, bez wywołania modelu"

    ids = {first.json()["id"], second.json()["id"], third.json()["id"]}
    assert len(ids) == 3, "każde żądanie wydaje inne zadanie"

    # Czwarte żądanie wyczerpuje kolejkę → nowy wsad.
    client.post("/api/exercise", json=body)
    assert len(calls) == 2

    stats = client.get("/api/stats/learning").json()
    assert stats["exercises_generated"] == 4  # wydane
    assert stats["exercises_queued"] == 2     # reszta z drugiego wsadu


def test_exercise_never_leaks_model_answer(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _stub_llm(main_mod, monkeypatch, BATCH_REPLY)
    body = client.post("/api/exercise", json={"type": "uoe_part2_open_cloze", "topic": "tenses"}).json()
    assert "answer" not in body and "answer_notes" not in body


def test_unknown_exercise_type_rejected(app_ctx):
    client, _ = app_ctx
    assert client.post("/api/exercise", json={"type": "nie_ma_takiego"}).status_code == 400


# --- /api/stats/usage: szacunek kosztu --------------------------------------

def test_usage_lean_cost_flags_assumed_model(app_ctx):
    client, main_mod = app_ctx
    # Model o potwierdzonej stawce (Haiku 4.5: 1/5 USD za 1M).
    main_mod.db.insert_usage_event(
        main_mod.conn, kind="generate", model="claude-haiku-4-5", input_tokens=0,
        output_tokens=1_000_000, cache_creation_input_tokens=0, cache_read_input_tokens=0,
        cost_usd=1.0, duration_ms=100, est_input_tokens=1_000_000,
    )
    data = client.get("/api/stats/usage").json()
    # 1M wejścia * $1 + 1M wyjścia * $5 = $6
    assert data["lean"]["used_model"] == pytest.approx(6.0)
    assert data["lean"]["assumed_models"] == []

    # Model bez potwierdzonej stawki — musi zostać oznaczony.
    main_mod.db.insert_usage_event(
        main_mod.conn, kind="grade", model="claude-opus-5", input_tokens=0, output_tokens=0,
        cache_creation_input_tokens=0, cache_read_input_tokens=0, cost_usd=0.2,
        duration_ms=100, est_input_tokens=0,
    )
    data = client.get("/api/stats/usage").json()
    assert data["lean"]["assumed_models"] == ["claude-opus-5"]


# --- Tipy --------------------------------------------------------------------

def test_tips_progress_and_goal_roundtrip(app_ctx):
    client, main_mod = app_ctx
    assert client.get("/api/tips/progress").json() == {"done": 0, "goal": 5, "streak": 0}
    assert client.post("/api/tips/goal", json={"goal": 2}).json()["goal"] == 2
    # Poza zakresem → przycięcie do dozwolonego przedziału.
    assert client.post("/api/tips/goal", json={"goal": 999}).json()["goal"] == 50

    eid = main_mod.db.insert_error(
        main_mod.conn, source="s", exercise_type="t", topic="tenses",
        student_text="a", correct_text="b", explanation="c",
    )
    client.post("/api/tips/goal", json={"goal": 1})
    prog = client.post("/api/tips/complete", json={"error_id": eid}).json()
    assert prog["done"] == 1 and prog["streak"] == 1
    # Powtórne zaliczenie tego samego błędu nie zawyża licznika.
    assert client.post("/api/tips/complete", json={"error_id": eid}).json()["done"] == 1
    assert client.post("/api/tips/complete", json={"error_id": 9999}).status_code == 404


def test_tips_focus_empty_when_no_errors(app_ctx):
    client, _ = app_ctx
    body = client.get("/api/tips/focus").json()
    assert body["error"] is None


def test_tips_focus_exclude_returns_different_error(app_ctx):
    client, main_mod = app_ctx
    ids = [
        main_mod.db.insert_error(main_mod.conn, source="s", exercise_type="t", topic="tenses",
                                student_text=f"a{i}", correct_text="b", explanation="c")
        for i in range(3)
    ]
    first = client.get("/api/tips/focus").json()["error"]["id"]
    other = client.get(f"/api/tips/focus?exclude={first}").json()["error"]["id"]
    assert other != first and other in ids
