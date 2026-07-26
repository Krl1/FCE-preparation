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
