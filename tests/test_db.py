import threading

import pytest

from app import db


@pytest.fixture()
def conn(tmp_path):
    connection = db.get_connection(tmp_path / "test.db")
    yield connection
    connection.close()


def test_insert_and_get_exercise_roundtrips_prompt(conn):
    prompt = {"instructions": "…", "question_text": "gap ___", "answer": "was"}
    ex_id = db.insert_exercise(conn, type="uoe_part2_open_cloze", topic="tenses", prompt=prompt)
    stored = db.get_exercise(conn, ex_id)
    assert stored["type"] == "uoe_part2_open_cloze"
    assert stored["prompt"]["answer"] == "was"


def test_get_missing_exercise_returns_none(conn):
    assert db.get_exercise(conn, 999) is None


def test_insert_attempt(conn):
    aid = db.insert_attempt(
        conn, exercise_id=None, type="uoe_part1_mcq_cloze",
        student_answer="A", is_correct=True, grading={"correct": True, "feedback": "ok", "errors": []},
    )
    assert aid > 0


def test_errors_insert_list_and_counts(conn):
    db.insert_error(conn, source="in_app", exercise_type="uoe_part2_open_cloze", topic="tenses",
                    student_text="have went", correct_text="have gone",
                    explanation="Present perfect", severity="major")
    db.insert_error(conn, source="external", exercise_type="uoe_part2_open_cloze", topic="tenses",
                    student_text="did", correct_text="have done",
                    explanation="…", severity="minor")
    db.insert_error(conn, source="in_app", exercise_type="uoe_part1_mcq_cloze", topic="collocations",
                    student_text="make a photo", correct_text="take a photo",
                    explanation="…")

    assert len(db.list_errors(conn)) == 3
    assert len(db.list_errors(conn, topic="tenses")) == 2
    assert len(db.list_errors(conn, exercise_type="uoe_part1_mcq_cloze")) == 1

    counts = {row["topic"]: row["count"] for row in db.topic_error_counts(conn)}
    assert counts["tenses"] == 2
    assert counts["collocations"] == 1


def test_settings_default_and_roundtrip(conn):
    assert db.get_setting(conn, "daily_goal", "5") == "5"  # brak → default
    db.set_setting(conn, "daily_goal", "8")
    assert db.get_setting(conn, "daily_goal", "5") == "8"
    db.set_setting(conn, "daily_goal", "3")  # nadpisanie
    assert db.get_setting(conn, "daily_goal", "5") == "3"


def test_reviews_count_distinct_and_idempotent_per_day(conn):
    assert db.reviews_done_today(conn) == 0
    db.insert_review(conn, 1)
    db.insert_review(conn, 1)  # ten sam błąd tego samego dnia — bez podwójnego liczenia
    assert db.reviews_done_today(conn) == 1
    db.insert_review(conn, 2)
    assert db.reviews_done_today(conn) == 2
    assert db.reviewed_today(conn, 1) is True
    assert db.reviewed_today(conn, 99) is False


def test_reviews_per_day_counts_distinct_errors_per_day(conn):
    """Mapa dla reguły serii: klucz to dzień lokalny, wartość to liczba RÓŻNYCH błędów."""
    from datetime import date, timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)

    def add(day, error_id):
        conn.execute("INSERT INTO reviews (error_id, created_at) VALUES (?, ?)",
                     (error_id, day.isoformat() + "T12:00:00+02:00"))

    add(today, 1)
    add(today, 2)
    add(today, 2)  # ten sam błąd tego samego dnia — liczony raz
    add(yesterday, 7)
    conn.commit()

    per_day = db.reviews_per_day(conn)
    assert per_day == {today.isoformat(): 2, yesterday.isoformat(): 1}


def test_get_error_returns_row_or_none(conn):
    eid = db.insert_error(conn, source="s", exercise_type="t", topic="tenses",
                          student_text="a", correct_text="b", explanation="e")
    assert db.get_error(conn, eid)["topic"] == "tenses"
    assert db.get_error(conn, 9999) is None


def test_usage_stats_aggregates_tokens_and_cost(conn):
    db.insert_usage_event(conn, kind="generate", model="claude-opus-4-8", input_tokens=10,
                          output_tokens=100, cache_creation_input_tokens=500,
                          cache_read_input_tokens=1000, cost_usd=0.05, duration_ms=3000)
    db.insert_usage_event(conn, kind="grade", model="claude-opus-4-8", input_tokens=5,
                          output_tokens=50, cache_creation_input_tokens=0,
                          cache_read_input_tokens=2000, cost_usd=0.03, duration_ms=2000)
    stats = db.usage_stats(conn)
    assert stats["total"]["calls"] == 2
    assert stats["total"]["output_tokens"] == 150
    assert abs(stats["total"]["cost_usd"] - 0.08) < 1e-9
    kinds = {r["kind"]: r for r in stats["by_kind"]}
    assert kinds["generate"]["calls"] == 1 and kinds["grade"]["calls"] == 1


def test_learning_stats_accuracy_and_totals(conn):
    db.insert_exercise(conn, type="uoe_part2_open_cloze", topic="tenses", prompt={})
    db.insert_attempt(conn, exercise_id=None, type="uoe_part2_open_cloze",
                      student_answer="x", is_correct=True, grading={})
    db.insert_attempt(conn, exercise_id=None, type="uoe_part2_open_cloze",
                      student_answer="y", is_correct=False, grading={})
    stats = db.learning_stats(conn)
    assert stats["exercises_generated"] == 1
    assert stats["attempts_total"] == 2
    assert stats["attempts_graded"] == 2
    assert stats["attempts_correct"] == 1
    assert abs(stats["accuracy"] - 0.5) < 1e-9


def test_learning_stats_accuracy_none_when_no_graded(conn):
    assert db.learning_stats(conn)["accuracy"] is None


def test_learning_stats_counts_only_served_exercises(conn):
    db.insert_exercise(conn, type="t", topic="tenses", prompt={}, served=True)
    db.insert_exercise(conn, type="t", topic="tenses", prompt={}, served=False)
    stats = db.learning_stats(conn)
    assert stats["exercises_generated"] == 1
    assert stats["exercises_queued"] == 1


def test_queue_serves_fifo_then_empties(conn):
    first = db.insert_exercise(conn, type="t", topic="tenses", prompt={"n": 1}, served=False)
    second = db.insert_exercise(conn, type="t", topic="tenses", prompt={"n": 2}, served=False)
    db.insert_exercise(conn, type="t", topic="inny", prompt={"n": 3}, served=False)

    assert db.take_queued_exercise(conn, type="t", topic="tenses")["id"] == first
    assert db.take_queued_exercise(conn, type="t", topic="tenses")["id"] == second
    assert db.take_queued_exercise(conn, type="t", topic="tenses") is None  # kolejka wyczerpana
    # Wydane zadania nie wracają do kolejki.
    assert db.count_queued_exercises(conn) == 1  # zostało to z innym tematem


def test_migration_backfills_legacy_exercises_even_if_column_existed(tmp_path):
    """Regresja: kolumna `served_at` mogła powstać w wersji bez uzupełniania danych.
    Wtedy zadania sprzed kolejki miałyby served_at = NULL i zostałyby wydane po raz
    drugi jako „nowe" oraz wypadłyby ze statystyk."""
    path = tmp_path / "legacy.db"
    first = db.get_connection(path)
    db.insert_exercise(first, type="t", topic="tenses", prompt={}, served=True)
    # Odtwórz stan „kolumna jest, uzupełnienia nie było".
    first.execute("UPDATE exercises SET served_at = NULL")
    first.execute("DELETE FROM settings WHERE key = 'served_at_backfilled'")
    first.commit()
    first.close()

    reopened = db.get_connection(path)
    assert db.count_queued_exercises(reopened) == 0, "stare zadanie musi zostać oznaczone jako wydane"
    assert db.learning_stats(reopened)["exercises_generated"] == 1
    reopened.close()


def test_migration_does_not_touch_real_queue(tmp_path):
    """Po wykonanym uzupełnieniu ponowne otwarcie bazy nie może „wydać" kolejki."""
    path = tmp_path / "queue.db"
    first = db.get_connection(path)
    db.insert_exercise(first, type="t", topic="tenses", prompt={}, served=False)
    first.close()

    reopened = db.get_connection(path)
    assert db.count_queued_exercises(reopened) == 1
    reopened.close()


def test_concurrent_access_does_not_lose_writes(conn):
    """Regresja: jedno połączenie sqlite3 używane z wielu wątków threadpoola FastAPI.
    Bez blokady w db.py ten test gubi zapisy i rzuca 'bad parameter or other API misuse'."""
    threads, ops = 4, 60
    failures = []

    def worker(tid):
        for i in range(ops):
            try:
                db.insert_error(conn, source="race", exercise_type="t", topic="tenses",
                                student_text=f"s{tid}-{i}", correct_text="c", explanation="e")
                db.list_errors(conn, limit=20)
                db.topic_error_counts(conn)
            except Exception as exc:  # noqa: BLE001 - zbieramy dowolny błąd współbieżności
                failures.append(repr(exc))

    workers = [threading.Thread(target=worker, args=(t,)) for t in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    assert failures == []
    assert len(db.list_errors(conn, limit=10_000)) == threads * ops
