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

def _batch_reply(exercises: int = 3, items: int = 5) -> dict:
    """Odpowiedź modelu: `exercises` zadań, każde z `items` pozycjami (jak części 2–4)."""
    return {
        "exercises": [
            {
                "instructions": f"polecenie {e}",
                "items": [
                    {"number": n, "question_text": f"zdanie {e}.{n} ______", "answer": f"odp{n}"}
                    for n in range(1, items + 1)
                ],
            }
            for e in range(1, exercises + 1)
        ]
    }


BATCH_REPLY = _batch_reply()


def test_exercise_batches_once_then_serves_from_queue(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    calls = []
    _stub_llm(main_mod, monkeypatch, BATCH_REPLY, counter=calls)
    body = {"type": "uoe_part2_open_cloze", "topic": "tenses", "lang": "pl"}
    batch = main_mod.llm_client.batch_size("uoe_part2_open_cloze")
    assert batch >= 2, "test ma sens tylko przy generowaniu wsadowym"

    served = [client.post("/api/exercise", json=body) for _ in range(batch)]
    assert all(r.status_code == 200 for r in served)
    assert len(calls) == 1, "cały wsad pochodzi z JEDNEGO wywołania modelu"
    assert len({r.json()["id"] for r in served}) == batch, "każde żądanie wydaje inne zadanie"

    # Kolejne żądanie wyczerpuje kolejkę → nowy wsad.
    client.post("/api/exercise", json=body)
    assert len(calls) == 2

    stats = client.get("/api/stats/learning").json()
    assert stats["exercises_generated"] == batch + 1        # wydane
    assert stats["exercises_queued"] == batch - 1           # reszta z drugiego wsadu


def test_exercise_has_five_items_for_every_use_of_english_part(app_ctx, monkeypatch):
    """Każda część Use of English wydaje zadanie z pięcioma pozycjami."""
    client, main_mod = app_ctx
    expected = main_mod.llm_client.ITEMS_PER_EXERCISE
    for typ in ("uoe_part1_mcq_cloze", "uoe_part2_open_cloze",
                "uoe_part3_word_formation", "uoe_part4_key_word_transformation"):
        _stub_llm(main_mod, monkeypatch, _batch_reply(items=expected))
        body = client.post("/api/exercise", json={"type": typ, "topic": None}).json()
        assert len(body["items"]) == expected, f"{typ} ma {len(body['items'])} pozycji"


def test_short_item_list_triggers_one_retry(app_ctx, monkeypatch):
    """Gdy model zignoruje wymaganą liczbę pozycji, jest jedna ponowna próba
    z dosłownym przypomnieniem — bez niej użytkownik dostałby 1 zadanie zamiast 5."""
    client, main_mod = app_ctx
    prompts = []

    def fake_invoke(prompt, kind="other"):
        prompts.append(prompt)
        # Pierwsza odpowiedź skrócona (1 pozycja), druga poprawna (5 pozycji).
        return json.dumps(_batch_reply(items=1 if len(prompts) == 1 else 5))

    monkeypatch.setattr(main_mod.llm_client, "_invoke", fake_invoke)
    body = client.post("/api/exercise", json={"type": "uoe_part2_open_cloze", "topic": "tenses"}).json()
    assert len(prompts) == 2, "powinna nastąpić dokładnie jedna ponowna próba"
    assert "ZA MAŁO" in prompts[1], "ponowny prompt musi zawierać przypomnienie o liczbie pozycji"
    assert len(body["items"]) == 5


def test_writing_exercise_has_no_items(app_ctx, monkeypatch):
    """Writing to zadanie jednoczęściowe — kontrola liczby pozycji go nie dotyczy."""
    client, main_mod = app_ctx
    _stub_llm(main_mod, monkeypatch, {"exercises": [
        {"instructions": "Napisz", "question_text": "Temat rozprawki…"},
        {"instructions": "Napisz", "question_text": "Inny temat…"},
    ]})
    body = client.post("/api/exercise", json={"type": "writing_essay", "topic": "content"}).json()
    assert body["items"] is None
    assert body["question_text"].startswith("Temat")


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

    assert client.post("/api/tips/complete", json={"error_id": 9999}).status_code == 404


def test_drill_counts_toward_goal_only_after_five_correct(app_ctx):
    """Błąd zalicza się do dziennego celu dopiero po 5 poprawnych ćwiczeniach,
    liczonych NARASTAJĄCO w obrębie dnia (nie trzeba trafić wszystkich od razu)."""
    client, main_mod = app_ctx
    target = main_mod.DRILL_CORRECT_TARGET
    client.post("/api/tips/goal", json={"goal": 1})
    eid = main_mod.db.insert_error(
        main_mod.conn, source="s", exercise_type="t", topic="tenses",
        student_text="a", correct_text="b", explanation="c",
    )

    # Pierwsze podejście: 3 z 5 poprawnych → jeszcze nie zaliczone.
    prog = client.post("/api/tips/complete", json={
        "error_id": eid, "correct_items": 3, "total_items": target,
    }).json()
    assert prog["done"] == 0
    assert prog["drill"] == {"correct": 3, "target": target}

    # Drugie podejście dopełnia do progu → błąd zaliczony, seria ruszona.
    prog = client.post("/api/tips/complete", json={
        "error_id": eid, "correct_items": 2, "total_items": target,
    }).json()
    assert prog["done"] == 1
    assert prog["streak"] == 1
    assert prog["drill"]["correct"] == target

    # Dalsze ćwiczenia tego samego błędu nie zawyżają dziennego licznika.
    prog = client.post("/api/tips/complete", json={
        "error_id": eid, "correct_items": target, "total_items": target,
    }).json()
    assert prog["done"] == 1


def test_drill_score_is_clamped_to_total(app_ctx):
    """Zgłoszona liczba poprawnych nie może przekroczyć liczby ćwiczeń w zestawie."""
    client, main_mod = app_ctx
    eid = main_mod.db.insert_error(
        main_mod.conn, source="s", exercise_type="t", topic="tenses",
        student_text="a", correct_text="b", explanation="c",
    )
    prog = client.post("/api/tips/complete", json={
        "error_id": eid, "correct_items": 999, "total_items": 2,
    }).json()
    assert prog["drill"]["correct"] == 2


def test_tips_focus_includes_drill_progress(app_ctx):
    client, main_mod = app_ctx
    eid = main_mod.db.insert_error(
        main_mod.conn, source="s", exercise_type="t", topic="tenses",
        student_text="a", correct_text="b", explanation="c",
    )
    client.post("/api/tips/complete", json={"error_id": eid, "correct_items": 1, "total_items": 5})
    body = client.get("/api/tips/focus").json()
    assert body["error"]["id"] == eid
    assert body["progress"]["drill"]["correct"] == 1


# --- Zastrzeżenia do wyjaśnień ----------------------------------------------

def _stub_dispute(main_mod, monkeypatch, *, verdict="upheld", student_was_right=True):
    payload = {
        "explanation_was_wrong": verdict == "upheld",
        "student_answer_was_acceptable": student_was_right,
        "revised_explanation": "Poprawione wyjaśnienie.",
        "reasoning": "Wyjaśnienie cytowało słowo, którego nie było w zadaniu.",
    }
    monkeypatch.setattr(main_mod.llm_client, "_invoke",
                        lambda prompt, kind="other": json.dumps(payload))


def _graded_multi_exercise(main_mod, monkeypatch):
    """Ocenia zadanie wielopozycyjne i zwraca (exercise_id, wynik oceny)."""
    _stub_llm(main_mod, monkeypatch, GRADE_ITEMS_REPLY)
    ex_id = main_mod.db.insert_exercise(
        main_mod.conn, type="uoe_part1_mcq_cloze", topic="collocations", prompt=MCQ_PROMPT
    )
    return ex_id


def test_grade_response_carries_error_ids(app_ctx, monkeypatch):
    """Bez identyfikatorów nie dałoby się zakwestionować konkretnego wpisu na ekranie oceny."""
    client, main_mod = app_ctx
    ex_id = _graded_multi_exercise(main_mod, monkeypatch)
    body = client.post("/api/grade", json={
        "type": "uoe_part1_mcq_cloze", "exercise_id": ex_id,
        "student_answers": ["A warm", "B give"],
    }).json()
    assert body["errors"] and body["errors"][0]["id"] is not None
    assert body["errors"][0]["item_number"] == 2


def test_dispute_upheld_proposes_changes_but_changes_nothing_yet(app_ctx, monkeypatch):
    """Samo zgłoszenie zastrzeżenia NIE może ruszyć danych — dopiero zatwierdzenie."""
    client, main_mod = app_ctx
    ex_id = _graded_multi_exercise(main_mod, monkeypatch)
    graded = client.post("/api/grade", json={
        "type": "uoe_part1_mcq_cloze", "exercise_id": ex_id,
        "student_answers": ["A warm", "B give"],
    }).json()
    err_id = graded["errors"][0]["id"]
    errors_before = len(main_mod.db.list_errors(main_mod.conn))

    _stub_dispute(main_mod, monkeypatch)
    res = client.post("/api/dispute", json={
        "scope": "item", "exercise_id": ex_id, "item_number": 2, "error_id": err_id,
        "disputed_text": "Wyjaśnienie cytuje nieistniejące słowo", "comment": "tego nie było",
    }).json()

    assert res["verdict"] == "upheld"
    assert res["student_was_right"] is True
    assert res["proposed_changes"], "powinna pojawić się propozycja korekty"
    # Dane bez zmian aż do zatwierdzenia.
    assert len(main_mod.db.list_errors(main_mod.conn)) == errors_before
    assert main_mod.db.get_dispute(main_mod.conn, res["dispute_id"])["applied_at"] is None


def test_dispute_apply_removes_false_error_and_fixes_score(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    ex_id = _graded_multi_exercise(main_mod, monkeypatch)
    graded = client.post("/api/grade", json={
        "type": "uoe_part1_mcq_cloze", "exercise_id": ex_id,
        "student_answers": ["A warm", "B give"],
    }).json()
    assert graded["score"] == "1/2"
    err_id = graded["errors"][0]["id"]

    _stub_dispute(main_mod, monkeypatch)
    res = client.post("/api/dispute", json={
        "scope": "item", "exercise_id": ex_id, "item_number": 2, "error_id": err_id,
        "disputed_text": "d", "comment": "c",
    }).json()

    applied = client.post(f"/api/dispute/{res['dispute_id']}/apply").json()
    assert applied["applied"]
    # Fałszywy wpis zniknął z dziennika — nie będzie już napędzał ćwiczeń.
    assert main_mod.db.get_error(main_mod.conn, err_id) is None
    # Zapisany wynik poprawiony.
    attempt = main_mod.db.latest_attempt_for_exercise(main_mod.conn, ex_id)
    assert attempt["grading"]["score"] == "2/2"
    assert attempt["is_correct"] == 1
    assert attempt["grading"]["errors"] == []
    # Powtórne zatwierdzenie odrzucone.
    assert client.post(f"/api/dispute/{res['dispute_id']}/apply").status_code == 400


def test_dispute_rejected_offers_no_changes_and_apply_is_refused(app_ctx, monkeypatch):
    """Gdy model obstaje przy wyjaśnieniu, nie wolno pozwolić na korektę danych —
    inaczej przycisk stałby się sposobem na kasowanie prawdziwych błędów."""
    client, main_mod = app_ctx
    eid = main_mod.db.insert_error(
        main_mod.conn, source="s", exercise_type="t", topic="tenses",
        student_text="have went", correct_text="have gone", explanation="e",
    )
    _stub_dispute(main_mod, monkeypatch, verdict="rejected", student_was_right=False)
    res = client.post("/api/dispute", json={
        "scope": "error", "error_id": eid, "disputed_text": "e", "comment": "nie zgadzam się",
    }).json()

    assert res["verdict"] == "rejected"
    assert res["proposed_changes"] == []
    assert client.post(f"/api/dispute/{res['dispute_id']}/apply").status_code == 400
    assert main_mod.db.get_error(main_mod.conn, eid) is not None


def test_dispute_on_journal_entry_removes_it_after_confirmation(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = main_mod.db.insert_error(
        main_mod.conn, source="import:x", exercise_type="imported", topic="tenses",
        student_text="a", correct_text="b", explanation="bzdura",
    )
    _stub_dispute(main_mod, monkeypatch)
    res = client.post("/api/dispute", json={
        "scope": "error", "error_id": eid, "disputed_text": "bzdura", "comment": "",
    }).json()
    client.post(f"/api/dispute/{res['dispute_id']}/apply")
    assert main_mod.db.get_error(main_mod.conn, eid) is None


def test_dispute_validation_and_stats(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    assert client.post("/api/dispute", json={"scope": "cos", "disputed_text": "x"}).status_code == 400
    assert client.post("/api/dispute", json={"scope": "item", "disputed_text": "  "}).status_code == 400
    assert client.post("/api/dispute", json={
        "scope": "error", "error_id": 9999, "disputed_text": "x"}).status_code == 404
    assert client.post("/api/dispute/9999/apply").status_code == 404

    _stub_dispute(main_mod, monkeypatch)
    eid = main_mod.db.insert_error(main_mod.conn, source="s", exercise_type="t", topic="tenses",
                                  student_text="a", correct_text="b", explanation="e")
    res = client.post("/api/dispute", json={
        "scope": "error", "error_id": eid, "disputed_text": "e"}).json()
    stats = client.get("/api/stats/learning").json()["disputes"]
    assert stats["total"] == 1 and stats["upheld"] == 1 and stats["applied"] == 0
    client.post(f"/api/dispute/{res['dispute_id']}/apply")
    assert client.get("/api/stats/learning").json()["disputes"]["applied"] == 1


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


# --- Ręczne usuwanie błędów z dziennika --------------------------------------

def test_delete_error_removes_it_from_journal_and_weak_points(app_ctx):
    client, main_mod = app_ctx
    keep = main_mod.db.insert_error(main_mod.conn, source="s", exercise_type="t", topic="tenses",
                                    student_text="zostaje", correct_text="b", explanation="e")
    drop = main_mod.db.insert_error(main_mod.conn, source="s", exercise_type="t", topic="articles",
                                    student_text="do usunięcia", correct_text="b", explanation="e")

    assert client.delete(f"/api/errors/{drop}").json() == {"deleted": drop}
    ids = [e["id"] for e in client.get("/api/errors").json()]
    assert ids == [keep]
    # „Słabe punkty" liczone są z dziennika, więc temat bez błędów znika z listy.
    assert "articles" not in [s["topic"] for s in client.get("/api/stats/topics").json()]


def test_delete_error_twice_is_404(app_ctx):
    client, main_mod = app_ctx
    eid = main_mod.db.insert_error(main_mod.conn, source="s", exercise_type="t", topic="tenses",
                                   student_text="a", correct_text="b", explanation="e")
    assert client.delete(f"/api/errors/{eid}").status_code == 200
    assert client.delete(f"/api/errors/{eid}").status_code == 404


def test_deleting_error_keeps_todays_goal_progress(app_ctx):
    """Usunięcie błędu nie odbiera dziś zaliczonego celu — przerobiona praca
    pozostaje przerobiona, inaczej porządkowanie dziennika cofałoby serię."""
    client, main_mod = app_ctx
    eid = main_mod.db.insert_error(main_mod.conn, source="s", exercise_type="t", topic="tenses",
                                   student_text="a", correct_text="b", explanation="e")
    main_mod.db.insert_review(main_mod.conn, eid)
    before = client.get("/api/tips/progress").json()["done"]
    assert before == 1

    client.delete(f"/api/errors/{eid}")
    assert client.get("/api/tips/progress").json()["done"] == before
