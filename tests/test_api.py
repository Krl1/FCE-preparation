"""Testy endpointów (FastAPI TestClient) — bez wywoływania prawdziwego modelu.

`llm_client._invoke` jest podstawiany, więc testy są szybkie i deterministyczne.
"""

import importlib
import json
import random
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

    # Wymyślony temat zmapowany na 'language' JUŻ W ODPOWIEDZI — uczeń zatwierdza
    # dokładnie to, co zostanie zapisane.
    assert body["errors"][0]["topic"] == "language"
    # Ocena sama NIC nie zapisuje do dziennika.
    assert main_mod.db.list_errors(main_mod.conn) == []


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


# --- Ćwicz błędy --------------------------------------------------------------------

def test_tips_progress_and_goal_roundtrip(app_ctx):
    client, main_mod = app_ctx
    assert client.get("/api/tips/progress").json() == {
        "done": 0, "goal": 5, "streak": 0,
        "required_today": 5, "overdue_days": 0, "at_risk": False,
    }
    assert client.post("/api/tips/goal", json={"goal": 2}).json()["goal"] == 2
    # Poza zakresem → przycięcie do dozwolonego przedziału.
    assert client.post("/api/tips/goal", json={"goal": 999}).json()["goal"] == 50

    assert client.post("/api/tips/complete", json={"error_id": 9999}).status_code == 404


def test_progress_reports_overdue_goal_after_a_missed_day(app_ctx):
    """Przespany dzień nie zeruje serii — dzisiejszy cel rośnie o zaległy dzień."""
    from datetime import date, timedelta
    client, main_mod = app_ctx
    client.post("/api/tips/goal", json={"goal": 2})
    today = date.today()

    # Cel osiągnięty przedwczoraj i trzy dni temu, wczoraj przerwa.
    for offset in (2, 3):
        day = (today - timedelta(days=offset)).isoformat()
        for error_id in (10 * offset, 10 * offset + 1):
            main_mod.conn.execute(
                "INSERT INTO reviews (error_id, created_at) VALUES (?, ?)",
                (error_id, day + "T12:00:00+02:00"),
            )
    main_mod.conn.commit()

    prog = client.get("/api/tips/progress").json()
    assert prog["streak"] == 2
    assert prog["required_today"] == 4      # 2 za dziś + 2 zaległe
    assert prog["overdue_days"] == 1
    assert prog["at_risk"] is True


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


def test_grade_returns_error_candidates_without_ids(app_ctx, monkeypatch):
    """Błędy z oceny to propozycje: bez `id` (bo nie ma ich w bazie), ale z numerem
    pozycji — inaczej po zatwierdzeniu nie dałoby się ich powiązać z luką."""
    client, main_mod = app_ctx
    ex_id = _graded_multi_exercise(main_mod, monkeypatch)
    body = client.post("/api/grade", json={
        "type": "uoe_part1_mcq_cloze", "exercise_id": ex_id,
        "student_answers": ["A warm", "B give"],
    }).json()
    assert body["errors"] and body["errors"][0]["id"] is None
    assert body["errors"][0]["item_number"] == 2
    assert main_mod.db.list_errors(main_mod.conn) == []


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

    assert client.delete(f"/api/errors/{drop}").json()["deleted"] == drop
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


# --- Zatwierdzanie błędów do dziennika ---------------------------------------

def test_confirming_error_stores_it_with_type_and_source_from_exercise(app_ctx, monkeypatch):
    """Typ i źródło biorą się z zapisanego zadania, nie z tego, co przyśle przeglądarka."""
    client, main_mod = app_ctx
    ex_id = _graded_multi_exercise(main_mod, monkeypatch)
    graded = client.post("/api/grade", json={
        "type": "uoe_part1_mcq_cloze", "exercise_id": ex_id,
        "student_answers": ["A warm", "B give"],
    }).json()
    candidate = graded["errors"][0]

    res = client.post("/api/errors", json={
        **{k: candidate[k] for k in ("topic", "student_text", "correct_text",
                                     "explanation", "severity")},
        "exercise_id": ex_id,
        "exercise_type": "writing_essay",   # celowo niezgodny — ma zostać zignorowany
    })
    assert res.status_code == 200
    stored = main_mod.db.list_errors(main_mod.conn)
    assert len(stored) == 1
    assert stored[0]["id"] == res.json()["id"]
    assert stored[0]["exercise_type"] == "uoe_part1_mcq_cloze"
    assert stored[0]["source"] == "in_app"


def test_confirming_error_normalizes_topic_from_client(app_ctx):
    """Klientowi nie wolno wstawić tematu spoza taksonomii — inaczej wpis nie
    wpływałby na dobór zadań i psuł statystyki."""
    client, main_mod = app_ctx
    res = client.post("/api/errors", json={
        "topic": "wymyslony_temat", "student_text": "a", "correct_text": "b",
        "explanation": "e", "severity": "major",
    }).json()
    assert res["topic"] == "language"
    stored = main_mod.db.list_errors(main_mod.conn)[0]
    assert stored["topic"] == "language"
    # Bez zadania błąd jest „z zewnątrz".
    assert stored["source"] == "external" and stored["exercise_type"] == "external"


def test_confirming_error_validates_input(app_ctx):
    client, _ = app_ctx
    assert client.post("/api/errors", json={
        "topic": "tenses", "student_text": "   ", "correct_text": "b"}).status_code == 400
    assert client.post("/api/errors", json={
        "topic": "tenses", "student_text": "a", "correct_text": "b",
        "exercise_id": 9999}).status_code == 404


def test_confirmed_error_feeds_weak_points_and_can_be_practised(app_ctx):
    """Dziennik napełniany zatwierdzeniami działa dalej normalnie: słabe punkty,
    fokus w „Ćwicz błędy", usuwanie."""
    client, _ = app_ctx
    assert client.get("/api/tips/focus").json()["error"] is None

    eid = client.post("/api/errors", json={
        "topic": "tenses", "student_text": "a", "correct_text": "b", "explanation": "e",
    }).json()["id"]

    assert [s["topic"] for s in client.get("/api/stats/topics").json()] == ["tenses"]
    assert client.get("/api/tips/focus").json()["error"]["id"] == eid
    assert client.delete(f"/api/errors/{eid}").status_code == 200


def test_each_wrong_gap_can_be_confirmed_separately(app_ctx, monkeypatch):
    """Regresja pełnej ścieżki: pięć luk, cztery odpowiedzi identyczne ('-').
    Każda błędna luka ma własną propozycję, a zatwierdzenie zapisuje TĘ lukę —
    wcześniej wszystkie sklejały się w jedną i do dziennika trafiał błąd innej luki."""
    client, main_mod = app_ctx
    prompt = {
        "instructions": "Uzupełnij",
        "items": [{"number": n, "question_text": f"zdanie {n} ______", "answer": a}
                  for n, a in [(1, "in"), (2, "the"), (3, "a"), (4, "The"), (5, "the")]],
    }
    _stub_llm(main_mod, monkeypatch, {
        "feedback": "f",
        "items": [{"number": n, "comment": f"c{n}"} for n in range(1, 6)],
        "errors": [{"item_number": n, "topic": "articles", "student_text": "-",
                    "correct_text": "x", "explanation": f"e{n}", "severity": "minor"}
                   for n in (1, 2, 4, 5)],
    })
    ex_id = main_mod.db.insert_exercise(main_mod.conn, type="uoe_part2_open_cloze",
                                        topic="articles", prompt=prompt)

    body = client.post("/api/grade", json={
        "type": "uoe_part2_open_cloze", "exercise_id": ex_id,
        "student_answers": ["-", "-", "a", "-", "-"],
    }).json()
    assert [e["item_number"] for e in body["errors"]] == [1, 2, 4, 5]

    # Zatwierdzamy tylko luki 2, 4 i 5 — dokładnie tak, jak chciał uczeń.
    for err in body["errors"]:
        if err["item_number"] == 1:
            continue
        client.post("/api/errors", json={
            **{k: err[k] for k in ("topic", "student_text", "correct_text",
                                   "explanation", "severity")},
            "exercise_id": ex_id,
        })

    stored = sorted(e["correct_text"] for e in main_mod.db.list_errors(main_mod.conn))
    assert stored == ["The", "the", "the"], "w dzienniku muszą wylądować luki 2, 4 i 5"


# --- Grupy błędów -------------------------------------------------------------

def _post_error(client, student="depends from", topic="prepositions"):
    res = client.post("/api/errors", json={
        "topic": topic, "student_text": student, "correct_text": "depends on",
        "explanation": "kalka z polskiego", "severity": "minor",
        "exercise_type": "imported",
    })
    assert res.status_code == 200
    return res.json()["id"]


def test_groups_endpoint_reports_ungrouped_count(app_ctx):
    client, _ = app_ctx
    _post_error(client)
    body = client.get("/api/groups").json()
    assert body["groups"] == []
    assert body["ungrouped"] == 1


def test_group_members_endpoint_lists_contexts(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "r", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]

    members = client.get(f"/api/groups/{gid}/members").json()
    assert [m["id"] for m in members] == [eid]
    assert members[0]["topic_label"]   # frontend renderuje etykietę, nie identyfikator


def test_group_members_of_missing_group_is_404(app_ctx):
    client, _ = app_ctx
    assert client.get("/api/groups/999/members").status_code == 404


def test_assign_creates_groups_from_model_output(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "group_id": None,
         "new_group": {"rule": "depend + on", "explanation": "zawsze 'on'",
                       "topic": "prepositions"}},
    ]})
    out = client.post("/api/groups/assign").json()
    assert out == {"assigned": 0, "created": 1, "unassigned": 0}
    body = client.get("/api/groups").json()
    assert body["ungrouped"] == 0
    assert body["groups"][0]["rule"] == "depend + on"
    assert body["groups"][0]["member_count"] == 1


def test_assign_with_invented_group_id_leaves_error_ungrouped(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch,
              {"assignments": [{"error_id": eid, "group_id": 999}]})
    out = client.post("/api/groups/assign").json()
    assert out == {"assigned": 0, "created": 0, "unassigned": 1}
    assert client.get("/api/groups").json()["ungrouped"] == 1


def test_second_assign_attaches_to_group_created_by_the_first(app_ctx, monkeypatch):
    """Sedno porcjowania: druga porcja ma dopiąć się do grupy z pierwszej,
    zamiast tworzyć tę samą regułę po raz drugi."""
    client, main_mod = app_ctx
    first = _post_error(client, student="depends from")
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": first, "new_group": {"rule": "depend + on", "explanation": "e",
                                          "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]

    second = _post_error(client, student="it depends from weather")
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": second, "group_id": gid}]})
    out = client.post("/api/groups/assign").json()
    assert out == {"assigned": 1, "created": 0, "unassigned": 0}

    body = client.get("/api/groups").json()
    assert len(body["groups"]) == 1          # nie powstała druga, bliźniacza grupa
    assert body["groups"][0]["member_count"] == 2
    assert body["ungrouped"] == 0


def test_assign_without_ungrouped_errors_does_not_call_model(app_ctx, monkeypatch):
    client, main_mod = app_ctx

    def explode(prompt, kind="other"):
        raise AssertionError("model nie powinien być wołany")

    monkeypatch.setattr(main_mod.llm_client, "_invoke", explode)
    assert client.post("/api/groups/assign").json() == {
        "assigned": 0, "created": 0, "unassigned": 0}


def test_patch_group_renames_rule(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "stara", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    assert client.patch(f"/api/groups/{gid}",
                        json={"rule": "nowa", "explanation": "e2"}).status_code == 200
    assert client.get("/api/groups").json()["groups"][0]["rule"] == "nowa"


def test_patch_missing_group_is_404(app_ctx):
    client, _ = app_ctx
    assert client.patch("/api/groups/999", json={"rule": "a", "explanation": "b"}
                        ).status_code == 404


def test_delete_group_returns_members_to_ungrouped(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "r", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    assert client.delete(f"/api/groups/{gid}").status_code == 200
    body = client.get("/api/groups").json()
    assert body["groups"] == []
    assert body["ungrouped"] == 1


def test_deleting_last_member_keeps_group_and_reports_it(app_ctx, monkeypatch):
    """Pusta grupa zostaje; endpoint tylko sygnalizuje, że osierociała."""
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "r", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    out = client.delete(f"/api/errors/{eid}").json()
    assert out["emptied_group_id"] == gid
    assert out["emptied_group_rule"] == "r"
    groups = client.get("/api/groups").json()["groups"]
    assert len(groups) == 1
    assert groups[0]["member_count"] == 0


def test_deleting_error_without_group_reports_no_orphan(app_ctx):
    client, _ = app_ctx
    eid = _post_error(client)
    assert client.delete(f"/api/errors/{eid}").json()["emptied_group_id"] is None


def test_patch_error_group_detaches_and_reports_orphan(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "r", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    out = client.patch(f"/api/errors/{eid}/group", json={"group_id": None}).json()
    assert out["group_id"] is None
    assert out["emptied_group_id"] == gid
    # Nazwa reguły leci tak samo jak przy DELETE /api/errors/{id} — frontend ma tam
    # jedno wspólne pytanie „usunąć grupę X?" i nie może zostać z pustym cudzysłowem.
    assert out["emptied_group_rule"] == "r"


def test_patch_error_group_without_orphan_reports_no_rule(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    kept = _post_error(client)
    moved = _post_error(client, student="discuss about")
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": kept, "new_group": {"rule": "r", "explanation": "e",
                                         "topic": "prepositions"}},
        {"error_id": moved, "new_group": {"rule": "r", "explanation": "e",
                                          "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    out = client.patch(f"/api/errors/{moved}/group", json={"group_id": None}).json()
    assert out["emptied_group_id"] is None
    assert out["emptied_group_rule"] is None
    assert client.get("/api/groups").json()["groups"][0]["id"] == gid


def test_patch_error_group_to_missing_group_is_404(app_ctx):
    client, _ = app_ctx
    eid = _post_error(client)
    assert client.patch(f"/api/errors/{eid}/group",
                        json={"group_id": 999}).status_code == 404


def test_regroup_rebuilds_from_scratch(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "pierwsza", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "druga", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/regroup")
    groups = client.get("/api/groups").json()["groups"]
    assert len(groups) == 1
    assert groups[0]["rule"] == "druga"


# --- Tryb grupowy w „Ćwicz błędy" ---------------------------------------------

def _make_group(client, main_mod, monkeypatch, rule="depend + on"):
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": rule, "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    return client.get("/api/groups").json()["groups"][0]["id"], eid


def test_focus_group_mode_returns_a_group(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    gid, _ = _make_group(client, main_mod, monkeypatch)
    body = client.get("/api/tips/focus?mode=group").json()
    assert body["group"]["id"] == gid
    assert body["error"] is None


def test_focus_group_mode_prefers_the_group_with_more_members(app_ctx):
    """Spec: „waga z liczby wpisów w grupie". Reguła złamana pięć razy ma wracać
    częściej niż jednorazowe potknięcie — równomierne losowanie to gubiło."""
    client, main_mod = app_ctx
    conn = main_mod.conn
    big = main_mod.db.insert_group(conn, rule="duża", explanation="e", topic="prepositions")
    small = main_mod.db.insert_group(conn, rule="mała", explanation="e", topic="prepositions")
    for i in range(5):
        main_mod.db.set_error_group(conn, _post_error(client, student=f"zdanie {i}"), big)
    main_mod.db.set_error_group(conn, _post_error(client, student="raz"), small)

    random.seed(20260916)
    picks = [client.get("/api/tips/focus?mode=group").json()["group"]["id"]
             for _ in range(60)]
    # Wagi 6:2 — przy równomiernym losowaniu (30:30) ten próg nie przechodzi.
    assert picks.count(big) >= 2 * picks.count(small)
    assert picks.count(small) > 0, "pojedyncze potknięcie nadal musi mieć szansę"


def test_focus_group_mode_can_still_draw_an_empty_group(app_ctx):
    """Pusta grupa to reguła przerobiona do czysta, a nie śmieć — nadal daje się ćwiczyć."""
    client, main_mod = app_ctx
    gid = main_mod.db.insert_group(main_mod.conn, rule="pusta", explanation="e",
                                   topic="prepositions")
    body = client.get("/api/tips/focus?mode=group").json()
    assert body["group"]["id"] == gid


def test_focus_group_mode_with_no_groups_returns_null(app_ctx):
    client, _ = app_ctx
    body = client.get("/api/tips/focus?mode=group").json()
    assert body["group"] is None


def test_focus_default_mode_is_unchanged(app_ctx):
    client, _ = app_ctx
    _post_error(client)
    body = client.get("/api/tips/focus").json()
    assert body["error"] is not None
    assert body["group"] is None


def test_completing_a_group_counts_one_toward_the_goal(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    gid, _ = _make_group(client, main_mod, monkeypatch)
    target = main_mod.DRILL_CORRECT_TARGET
    out = client.post("/api/tips/complete",
                      json={"group_id": gid, "correct_items": target,
                            "total_items": target}).json()
    assert out["done"] == 1


def test_partial_group_drill_does_not_count_yet(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    gid, _ = _make_group(client, main_mod, monkeypatch)
    target = main_mod.DRILL_CORRECT_TARGET
    out = client.post("/api/tips/complete",
                      json={"group_id": gid, "correct_items": 1, "total_items": target}).json()
    assert out["done"] == 0


def test_complete_requires_exactly_one_unit(app_ctx):
    client, _ = app_ctx
    assert client.post("/api/tips/complete",
                       json={"correct_items": 1, "total_items": 1}).status_code == 422


def test_group_exercise_uses_rule_framing_not_a_fake_wrong_version(app_ctx, monkeypatch):
    """Grupa to reguła — prompt nie może podawać 'wersji błędnej' równej 'poprawnej'."""
    client, main_mod = app_ctx
    gid, _ = _make_group(client, main_mod, monkeypatch)
    seen = {}

    def fake_invoke(prompt, kind="other"):
        seen["prompt"] = prompt
        return json.dumps({
            "exercise_type": "uoe_part2_open_cloze", "instructions": "i",
            "items": [{"number": n, "question_text": "q ______", "options": None,
                       "key_word": None, "stem": None, "answer": "a",
                       "answer_notes": "n"} for n in range(1, 6)],
        })

    monkeypatch.setattr(main_mod.llm_client, "_invoke", fake_invoke)
    assert client.post("/api/tips/exercise", json={"group_id": gid}).status_code == 200
    assert "Reguła:" in seen["prompt"]
    assert "Wersja błędna" not in seen["prompt"]


def test_empty_group_can_still_be_drilled(app_ctx, monkeypatch):
    """Grupa bez wpisów to reguła przerobiona do czysta — nadal ma się dać ćwiczyć."""
    client, main_mod = app_ctx
    gid, eid = _make_group(client, main_mod, monkeypatch)
    client.delete(f"/api/errors/{eid}")
    assert client.get("/api/groups").json()["groups"][0]["member_count"] == 0

    monkeypatch.setattr(main_mod.llm_client, "_invoke", lambda prompt, kind="other": json.dumps({
        "exercise_type": "uoe_part2_open_cloze", "instructions": "i",
        "items": [{"number": n, "question_text": "q ______", "options": None,
                   "key_word": None, "stem": None, "answer": "a",
                   "answer_notes": "n"} for n in range(1, 6)],
    }))
    assert client.post("/api/tips/exercise", json={"group_id": gid}).status_code == 200


def test_exercise_requires_exactly_one_unit(app_ctx):
    client, _ = app_ctx
    assert client.post("/api/tips/exercise", json={"lang": "pl"}).status_code == 422
    assert client.post("/api/tips/exercise",
                       json={"error_id": 1, "group_id": 1}).status_code == 422


# --- Fiszki -------------------------------------------------------------------

def _card_error(client, student="depends from", topic="prepositions"):
    res = client.post("/api/errors", json={
        "topic": topic, "student_text": student, "correct_text": "depends on",
        "explanation": "kalka z polskiego", "severity": "minor",
        "exercise_type": "imported",
    })
    assert res.status_code == 200
    return res.json()["id"]


def _cards_payload(refs, shape="translate"):
    return {"cards": [{"ref": r, "shape": shape, "front": f"Przód {r}",
                       "back": f"Tył {r}"} for r in refs]}


def _prepared_card(client, main_mod, monkeypatch, student="depends from",
                   topic="prepositions"):
    """Wpis w dzienniku wraz z gotową kartą. Zwraca (error_id, card_id).

    Karta musi mieć TREŚĆ, żeby w ogóle wejść do kolejki, więc każdy test oceniania
    zaczyna się od przygotowania — pierwsza ocena nie zakłada już wiersza karty."""
    eid = _card_error(client, student=student, topic=topic)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    assert client.post("/api/cards/prepare").json()["prepared"] == 1
    return eid, main_mod.db.get_card_by_source(main_mod.conn, "error", eid)["id"]


def test_session_renders_cards_from_the_journal(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid, cid = _prepared_card(client, main_mod, monkeypatch)
    body = client.get("/api/cards/session").json()
    assert len(body["cards"]) == 1
    card = body["cards"][0]
    assert card["source_kind"] == "error"
    assert card["source_id"] == eid
    assert card["card_id"] == cid       # karta istnieje, zanim uczeń ją zobaczy
    assert card["front"] == f"Przód error:{eid}"
    # Pełne źródło leci obok treści — przycisk „Ćwicz błędy" przy karcie go czyta.
    assert card["source"]["correct_text"] == "depends on"
    assert card["topic_label"] == "Przyimki"


def test_session_never_calls_the_model(app_ctx, monkeypatch):
    """Cała wartość fiszek to natychmiastowość — kolejka musi być darmowa.

    Wpis bez przygotowanej karty nie może wywołać modelu „po drodze": kolejka ma go
    pominąć, a nie douczyć w locie."""
    client, main_mod = app_ctx
    _card_error(client)

    def explode(prompt, kind="other"):
        raise AssertionError("kolejka fiszek nie może wołać modelu")

    monkeypatch.setattr(main_mod.llm_client, "_invoke", explode)
    assert client.get("/api/cards/session").status_code == 200


def test_session_respects_the_new_card_limit(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    refs = [f"error:{_card_error(client, student=f'błąd {n}')}" for n in range(5)]
    _stub_llm(main_mod, monkeypatch, _cards_payload(refs))
    assert client.post("/api/cards/prepare").json()["prepared"] == 5
    client.post("/api/cards/settings", json={"new_per_day": 2})
    assert len(client.get("/api/cards/session").json()["cards"]) == 2


def test_session_filters_by_topic(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    aid = _card_error(client, student="a", topic="prepositions")
    bid = _card_error(client, student="b", topic="collocations")
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{aid}", f"error:{bid}"]))
    assert client.post("/api/cards/prepare").json()["prepared"] == 2
    body = client.get("/api/cards/session?topic=collocations").json()
    assert [c["source_id"] for c in body["cards"]] == [bid]


def test_grading_a_prepared_card_schedules_it(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _, cid = _prepared_card(client, main_mod, monkeypatch)
    out = client.post(f"/api/cards/{cid}/grade", json={"grade": "known"}).json()
    assert out["interval_days"] == 1
    assert out["leech"] is False
    assert out["progress"]["done_today"] == 1


def test_known_climbs_and_unknown_resets(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _, cid = _prepared_card(client, main_mod, monkeypatch)
    first = client.post(f"/api/cards/{cid}/grade", json={"grade": "known"}).json()
    assert first["interval_days"] == 1
    second = client.post(f"/api/cards/{cid}/grade", json={"grade": "known"}).json()
    assert second["interval_days"] == 3
    third = client.post(f"/api/cards/{cid}/grade", json={"grade": "unknown"}).json()
    assert third["interval_days"] == 1


def test_card_becomes_a_leech_after_four_failures(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _, cid = _prepared_card(client, main_mod, monkeypatch)
    for _ in range(3):
        out = client.post(f"/api/cards/{cid}/grade", json={"grade": "unknown"}).json()
    assert out["leech"] is False
    out = client.post(f"/api/cards/{cid}/grade", json={"grade": "unknown"}).json()
    assert out["leech"] is True


def test_grading_a_missing_card_is_404(app_ctx):
    client, _ = app_ctx
    assert client.post("/api/cards/999/grade", json={"grade": "known"}).status_code == 404


def test_progress_reports_counters_without_touching_the_streak(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _, cid = _prepared_card(client, main_mod, monkeypatch)
    client.post(f"/api/cards/{cid}/grade", json={"grade": "known"})
    prog = client.get("/api/cards/progress").json()
    assert prog["done_today"] == 1
    assert prog["new_limit"] == main_mod.DEFAULT_NEW_CARDS_PER_DAY
    assert prog["unprepared"] == 0
    assert client.get("/api/tips/progress").json()["done"] == 0


def test_deleting_the_error_removes_it_from_the_session(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid, _ = _prepared_card(client, main_mod, monkeypatch)
    client.delete(f"/api/errors/{eid}")
    assert client.get("/api/cards/session").json()["cards"] == []


# --- Treść fiszki -------------------------------------------------------------

def test_unprepared_cards_stay_out_of_the_session(app_ctx):
    client, _ = app_ctx
    _card_error(client)
    body = client.get("/api/cards/session").json()
    assert body["cards"] == []
    assert body["progress"]["unprepared"] >= 1


def test_prepare_fills_content_and_the_session_serves_it(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    out = client.post("/api/cards/prepare").json()
    assert out == {"prepared": 1, "unprepared": 0, "remaining": 0}
    card = client.get("/api/cards/session").json()["cards"][0]
    assert card["front"] == f"Przód error:{eid}"
    assert card["shape"] == "translate"


def test_prepared_card_never_shows_the_wrong_form(app_ctx, monkeypatch):
    """Wyrazisty fixture, nie ogólne sprawdzenie podciągu: 35 z 219 wpisów ma formę
    błędną krótszą niż pięć znaków (`in`, `at`, `-`), więc ogólny test padałby na
    niemal każdym poprawnym angielskim zdaniu."""
    client, main_mod = app_ctx
    eid = _card_error(client, student="in home")
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    card = client.get("/api/cards/session").json()["cards"][0]
    assert "in home" not in card["front"].lower()
    assert "in home" not in card["back"].lower()


def test_prepare_without_candidates_does_not_call_the_model(app_ctx, monkeypatch):
    client, main_mod = app_ctx

    def explode(prompt, kind="other"):
        raise AssertionError("nie ma czego przygotowywać")

    monkeypatch.setattr(main_mod.llm_client, "_invoke", explode)
    assert client.post("/api/cards/prepare").json() == {
        "prepared": 0, "unprepared": 0, "remaining": 0}


def test_session_still_never_calls_the_model(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")

    def explode(prompt, kind="other"):
        raise AssertionError("kolejka fiszek nie może wołać modelu")

    monkeypatch.setattr(main_mod.llm_client, "_invoke", explode)
    assert client.get("/api/cards/session").status_code == 200


def test_rejected_entry_stays_unprepared_and_retries(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, {"cards": [
        {"ref": f"error:{eid}", "shape": "gap", "front": "bez luki", "back": "b",
         "shape_reason": "powód"}]})
    assert client.post("/api/cards/prepare").json() == {
        "prepared": 0, "unprepared": 1, "remaining": 1}
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    assert client.post("/api/cards/prepare").json() == {
        "prepared": 1, "unprepared": 0, "remaining": 0}


def test_regenerate_replaces_the_content(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    cid = client.get("/api/cards/session").json()["cards"][0]["card_id"]
    _stub_llm(main_mod, monkeypatch, {"cards": [
        {"ref": f"error:{eid}", "shape": "translate", "front": "Nowy przód",
         "back": "Nowy tył"}]})
    assert client.post(f"/api/cards/{cid}/regenerate").json()["front"] == "Nowy przód"
    assert client.get("/api/cards/session").json()["cards"][0]["front"] == "Nowy przód"


def test_preparing_does_not_disturb_an_existing_schedule(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    cid = client.get("/api/cards/session").json()["cards"][0]["card_id"]
    graded = client.post(f"/api/cards/{cid}/grade", json={"grade": "known"}).json()
    due_before = graded["due_on"]
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post(f"/api/cards/{cid}/regenerate")
    assert main_mod.db.get_card(main_mod.conn, cid)["due_on"] == due_before


def test_remaining_and_the_progress_counter_agree(app_ctx, monkeypatch):
    """`remaining` z przygotowania i `unprepared` z postępu to ta sama liczba.

    Przy bazie większej niż limit zapytania `sources_without_card` jedno kliknięcie nie
    zakłada wierszy dla wszystkich źródeł — część czeka bez wiersza karty. Gdyby każdy
    licznik miał własny wzór, zakładka pokazałaby obok siebie dwie różne odpowiedzi na
    to samo pytanie „ile jeszcze zostało"."""
    client, main_mod = app_ctx
    eid = _card_error(client, student="a")
    _card_error(client, student="b")
    # Ucięcie listy źródeł udaje limit zapytania przy bazie większej, niż mieści się
    # w jednym przebiegu — bez tego każdy wzór dałby tę samą liczbę i test nic nie mierzy.
    real = main_mod.db.sources_without_card
    monkeypatch.setattr(main_mod.db, "sources_without_card",
                        lambda conn, *a, **kw: real(conn, *a, **kw)[:1])
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    out = client.post("/api/cards/prepare").json()
    assert out["prepared"] == 1
    assert out["remaining"] == 1
    assert client.get("/api/cards/progress").json()["unprepared"] == out["remaining"]


def test_regenerating_a_group_card_sends_no_wrong_form(app_ctx, monkeypatch):
    """Grupa nie ma formy błędnej: `student_text` leci do modelu PUSTY, a materiałem
    jest reguła. Reguła w polu „NIE POKAZUJ" zakazałaby modelowi jedynej treści, jaką
    grupa niesie — a `regenerate` składa wiersz materiału własnym kodem, osobną ścieżką
    niż wsadowe `cards_unprepared`, więc reguła musi być sprawdzona także tutaj."""
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "depend + on", "explanation": "zawsze 'on'",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    _stub_llm(main_mod, monkeypatch,
              _cards_payload([f"error:{eid}", f"group:{gid}"]))
    client.post("/api/cards/prepare")
    cid = main_mod.db.get_card_by_source(main_mod.conn, "group", gid)["id"]

    sent = []

    def spy(items, lang="pl"):
        sent.extend(items)
        return {"cards": [{"ref": i["ref"], "shape": i["suggested_shape"],
                           "front": "Przód ______", "back": "Tył"} for i in items]}

    monkeypatch.setattr(main_mod.llm_client, "generate_cards", spy)
    assert client.post(f"/api/cards/{cid}/regenerate").status_code == 200
    assert len(sent) == 1
    assert sent[0]["student_text"] == ""
    assert sent[0]["correct_text"] == "depend + on"
    assert sent[0]["explanation"] == "zawsze 'on'"


# --- Uwagi do przegenerowania karty ------------------------------------------

def _material_spy(main_mod, monkeypatch):
    """Przechwytuje materiał lecący do modelu, zamiast go wołać."""
    sent = []

    def spy(items, lang="pl"):
        sent.extend(items)
        return {"cards": [{"ref": i["ref"], "shape": i["suggested_shape"],
                           "front": "Przód ______", "back": "Tył"} for i in items]}

    monkeypatch.setattr(main_mod.llm_client, "generate_cards", spy)
    return sent


def test_regenerate_passes_the_notes_and_the_card_being_replaced(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _eid, cid = _prepared_card(client, main_mod, monkeypatch)
    przed = client.get("/api/cards/session").json()["cards"][0]
    sent = _material_spy(main_mod, monkeypatch)
    res = client.post(f"/api/cards/{cid}/regenerate",
                      json={"notes": "za długie zdanie"})
    assert res.status_code == 200
    assert sent[0]["notes"] == "za długie zdanie"
    assert sent[0]["current_front"] == przed["front"]
    assert sent[0]["current_back"] == przed["back"]


def test_regenerate_without_a_body_behaves_exactly_as_before(app_ctx, monkeypatch):
    """Obietnica złożona przy projektowaniu: puste uwagi to dokładnie dzisiejsze
    zachowanie — ślepe ułożenie od nowa, bez podpowiedzi i bez poprzedniej wersji."""
    client, main_mod = app_ctx
    _eid, cid = _prepared_card(client, main_mod, monkeypatch)
    sent = _material_spy(main_mod, monkeypatch)
    assert client.post(f"/api/cards/{cid}/regenerate").status_code == 200
    assert sent[0]["notes"] == ""
    assert sent[0]["current_front"] == ""
    assert sent[0]["current_back"] == ""


def test_blank_notes_count_as_no_notes(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    _eid, cid = _prepared_card(client, main_mod, monkeypatch)
    sent = _material_spy(main_mod, monkeypatch)
    client.post(f"/api/cards/{cid}/regenerate", json={"notes": "   "})
    assert sent[0]["notes"] == ""
    assert sent[0]["current_front"] == ""


def test_overlong_notes_are_capped(app_ctx, monkeypatch):
    """Uwagi idą wprost do promptu, więc muszą mieć sufit — inaczej tekst wklejony
    przez przypadek rozdmuchuje żądanie i jego koszt."""
    client, main_mod = app_ctx
    _eid, cid = _prepared_card(client, main_mod, monkeypatch)
    sent = _material_spy(main_mod, monkeypatch)
    client.post(f"/api/cards/{cid}/regenerate", json={"notes": "x" * 900})
    assert len(sent[0]["notes"]) == 500


def test_batch_preparation_sends_no_notes(app_ctx, monkeypatch):
    """Wsadowe przygotowanie nie ma czego doradzać. Ta ścieżka obsługuje setki kart
    naraz i przeszła pełny przegląd — uwagi nie mogą jej po cichu zmienić."""
    client, main_mod = app_ctx
    _card_error(client)
    sent = _material_spy(main_mod, monkeypatch)
    client.post("/api/cards/prepare")
    assert sent[0]["notes"] == ""
    assert sent[0]["current_front"] == ""
    assert sent[0]["current_back"] == ""


# --- Podpowiedź do karty z luką ----------------------------------------------

def _gap_payload(refs, hint="zadzwonię do ciebie"):
    return {"cards": [{"ref": r, "shape": "gap", "front": "I ______ you tomorrow.",
                       "back": "will call", "hint": hint} for r in refs]}


def test_session_serves_the_hint(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client, topic="tenses")
    _stub_llm(main_mod, monkeypatch, _gap_payload([f"error:{eid}"]))
    assert client.post("/api/cards/prepare").json()["prepared"] == 1
    karta = client.get("/api/cards/session").json()["cards"][0]
    assert karta["shape"] == "gap"
    assert karta["hint"] == "zadzwonię do ciebie"


def test_gap_card_without_a_hint_stays_unprepared(app_ctx, monkeypatch):
    """Serwer odrzuca całą pozycję, więc karta zostaje nieprzygotowana i wraca przy
    kolejnym kliknięciu — zamiast trafić do sesji w postaci, na którą uczeń narzekał."""
    client, main_mod = app_ctx
    eid = _card_error(client, topic="tenses")
    _stub_llm(main_mod, monkeypatch, _gap_payload([f"error:{eid}"], hint=""))
    out = client.post("/api/cards/prepare").json()
    assert out == {"prepared": 0, "unprepared": 1, "remaining": 1}
    assert client.get("/api/cards/session").json()["cards"] == []


def test_translate_card_has_an_empty_hint(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    assert client.get("/api/cards/session").json()["cards"][0]["hint"] == ""


def test_regenerate_returns_the_hint(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client, topic="tenses")
    _stub_llm(main_mod, monkeypatch, _gap_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    cid = client.get("/api/cards/session").json()["cards"][0]["card_id"]
    _stub_llm(main_mod, monkeypatch, _gap_payload([f"error:{eid}"], hint="nowa podpowiedź"))
    assert client.post(f"/api/cards/{cid}/regenerate").json()["hint"] == "nowa podpowiedź"


# --- Cztery tryby startu sesji ------------------------------------------------

def _session_ids(client, mode=None):
    q = f"?mode={mode}" if mode else ""
    return [c["card_id"] for c in client.get(f"/api/cards/session{q}").json()["cards"]]


def _three_kinds_of_card(client, main_mod, monkeypatch):
    """Trzy karty w trzech stanach: zaległa, przerobiona z terminem w przyszłości, nowa.

    Zwraca (zaległa, przyszła, nowa) — na nich rozróżniają się wszystkie cztery tryby."""
    ids = {}
    for nazwa, student in (("zalegla", "a"), ("przyszla", "b"), ("nowa", "c")):
        eid = _card_error(client, student=student)
        _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
        client.post("/api/cards/prepare")
        ids[nazwa] = main_mod.db.get_card_by_source(main_mod.conn, "error", eid)["id"]
    # Ocena robi z karty „przerobioną"; bez niej zostaje nowa.
    for nazwa, due in (("zalegla", "2026-09-01"), ("przyszla", "2026-12-31")):
        main_mod.db.insert_card_review(main_mod.conn, card_id=ids[nazwa], grade="known")
        main_mod.db.update_card_schedule(main_mod.conn, ids[nazwa],
                                         interval_days=7, due_on=due)
    return ids["zalegla"], ids["przyszla"], ids["nowa"]


def test_mode_both_is_the_default(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    zalegla, przyszla, nowa = _three_kinds_of_card(client, main_mod, monkeypatch)
    assert _session_ids(client) == _session_ids(client, "both")
    assert sorted(_session_ids(client, "both")) == sorted([zalegla, nowa])
    assert przyszla not in _session_ids(client, "both")


def test_mode_due_skips_new_cards(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    zalegla, _przyszla, nowa = _three_kinds_of_card(client, main_mod, monkeypatch)
    assert _session_ids(client, "due") == [zalegla]
    assert nowa not in _session_ids(client, "due")


def test_mode_new_skips_repetitions(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    zalegla, _przyszla, nowa = _three_kinds_of_card(client, main_mod, monkeypatch)
    assert _session_ids(client, "new") == [nowa]
    assert zalegla not in _session_ids(client, "new")


def test_mode_all_takes_every_card_already_practised(app_ctx, monkeypatch):
    """„Powtórz wszystko" ignoruje termin, ale NIE wciąga kart nigdy nieocenionych —
    te są nowe, a nie przerobione."""
    client, main_mod = app_ctx
    zalegla, przyszla, nowa = _three_kinds_of_card(client, main_mod, monkeypatch)
    wszystkie = _session_ids(client, "all")
    assert sorted(wszystkie) == sorted([zalegla, przyszla])
    assert nowa not in wszystkie


def test_unknown_mode_is_rejected(app_ctx, monkeypatch):
    """Serwer nie ufa klientowi — tak samo jak przy ocenie karty."""
    client, _ = app_ctx
    assert client.get("/api/cards/session?mode=wymyslony").status_code == 422


def test_session_echoes_the_mode(app_ctx, monkeypatch):
    """Frontend dobiera komunikat pustego ekranu do trybu, więc musi go dostać z powrotem."""
    client, _ = app_ctx
    assert client.get("/api/cards/session").json()["mode"] == "both"
    assert client.get("/api/cards/session?mode=all").json()["mode"] == "all"
