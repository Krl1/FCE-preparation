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


def test_get_error_returns_row_or_none(conn):
    eid = db.insert_error(conn, source="s", exercise_type="t", topic="tenses",
                          student_text="a", correct_text="b", explanation="e")
    assert db.get_error(conn, eid)["topic"] == "tenses"
    assert db.get_error(conn, 9999) is None
