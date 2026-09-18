import sqlite3
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


# --- Grupy błędów -------------------------------------------------------------

def _err(conn, topic="prepositions", student="depends from", correct="depends on"):
    return db.insert_error(conn, source="test", exercise_type="imported", topic=topic,
                           student_text=student, correct_text=correct,
                           explanation="kalka z polskiego", severity="minor")


def test_insert_and_get_group(conn):
    gid = db.insert_group(conn, rule="depend + on", explanation="zawsze 'on'",
                          topic="prepositions")
    g = db.get_group(conn, gid)
    assert g["rule"] == "depend + on"
    assert g["topic"] == "prepositions"
    assert g["created_at"] and g["updated_at"]


def test_get_missing_group_returns_none(conn):
    assert db.get_group(conn, 999) is None


def test_list_groups_carries_member_count(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.set_error_group(conn, _err(conn), gid)
    db.set_error_group(conn, _err(conn), gid)
    rows = db.list_groups(conn)
    assert len(rows) == 1
    assert rows[0]["member_count"] == 2


def test_empty_group_is_listed_with_zero_members(conn):
    db.insert_group(conn, rule="r", explanation="e", topic="articles")
    assert db.list_groups(conn)[0]["member_count"] == 0


def test_update_group_changes_rule_and_bumps_updated_at(conn):
    gid = db.insert_group(conn, rule="stara", explanation="e", topic="articles")
    before = db.get_group(conn, gid)["updated_at"]
    assert db.update_group(conn, gid, rule="nowa", explanation="e2") is True
    after = db.get_group(conn, gid)
    assert after["rule"] == "nowa"
    assert after["explanation"] == "e2"
    assert after["updated_at"] >= before


def test_update_missing_group_returns_false(conn):
    assert db.update_group(conn, 999, rule="x", explanation="y") is False


def test_delete_group_returns_members_to_ungrouped(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    assert db.delete_group(conn, gid) is True
    assert db.get_group(conn, gid) is None
    assert db.group_of_error(conn, eid) is None
    assert [e["id"] for e in db.list_ungrouped_errors(conn)] == [eid]


def test_group_reviews_survive_group_deletion(conn):
    """Usunięcie grupy nie cofa zdobytego celu — tak samo jak usunięcie błędu."""
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_group_review(conn, gid)
    assert db.reviews_done_today(conn) == 1
    db.delete_group(conn, gid)
    assert db.reviews_done_today(conn) == 1


def test_deleting_last_member_keeps_the_group(conn):
    """Pusta grupa zostaje — nic nie znika samo, o usunięciu decyduje uczeń."""
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    db.delete_error(conn, eid)
    assert db.get_group(conn, gid) is not None
    assert db.group_member_count(conn, gid) == 0


def test_set_error_group_to_none_detaches(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    assert db.set_error_group(conn, eid, None) is True
    assert db.group_of_error(conn, eid) is None
    assert db.group_member_count(conn, gid) == 0


def test_clear_all_groups_removes_groups_and_assignments(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    db.clear_all_groups(conn)
    assert db.list_groups(conn) == []
    assert db.group_of_error(conn, eid) is None


def test_list_ungrouped_skips_assigned_errors(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    assigned = _err(conn)
    loose = _err(conn)
    db.set_error_group(conn, assigned, gid)
    assert [e["id"] for e in db.list_ungrouped_errors(conn)] == [loose]


def test_group_drill_and_review_count_toward_the_day(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_group_drill_score(conn, group_id=gid, correct_items=3, total_items=5)
    db.insert_group_drill_score(conn, group_id=gid, correct_items=2, total_items=5)
    assert db.group_drill_correct_today(conn, gid) == 5
    db.insert_group_review(conn, gid)
    db.insert_group_review(conn, gid)  # idempotentne w obrębie dnia
    assert db.reviews_done_today(conn) == 1


def test_reviews_done_today_sums_errors_and_groups(conn):
    eid = _err(conn)
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_review(conn, eid)
    db.insert_group_review(conn, gid)
    assert db.reviews_done_today(conn) == 2


def test_reviews_per_day_sums_both_sources(conn):
    eid = _err(conn)
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_review(conn, eid)
    db.insert_group_review(conn, gid)
    per_day = db.reviews_per_day(conn)
    assert sum(per_day.values()) == 2


def test_group_topic_counts_feeds_srs(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="prepositions")
    db.set_error_group(conn, _err(conn), gid)
    rows = db.group_topic_counts(conn)
    assert rows[0]["topic"] == "prepositions"
    assert rows[0]["count"] == 1
    assert rows[0]["last_seen"]


def test_group_topic_counts_freshness_comes_from_members(conn):
    """`last_seen` ma mówić o wpisach, nie o grupie.

    Po przegrupowaniu wszystkie grupy dostają ten sam `updated_at`, więc świeżość
    liczona z grupy byłaby stałą dokładnie wtedy, gdy powinna różnicować."""
    gid = db.insert_group(conn, rule="r", explanation="e", topic="prepositions")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    # Grupa „ruszona" długo po wpisie — świeżość i tak ma pochodzić od wpisu.
    conn.execute("UPDATE error_groups SET updated_at = ? WHERE id = ?",
                 ("2099-01-01T00:00:00+00:00", gid))
    conn.commit()
    member_created = db.get_error(conn, eid)["created_at"]
    assert db.group_topic_counts(conn)[0]["last_seen"] == member_created


def test_group_topic_counts_of_empty_groups_have_no_freshness(conn):
    db.insert_group(conn, rule="r", explanation="e", topic="prepositions")
    assert db.group_topic_counts(conn)[0]["last_seen"] is None


def test_count_ungrouped_errors_matches_the_list(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.set_error_group(conn, _err(conn), gid)
    _err(conn)
    _err(conn)
    assert db.count_ungrouped_errors(conn) == 2
    assert db.count_ungrouped_errors(conn) == len(db.list_ungrouped_errors(conn))


def test_new_group_after_clearing_does_not_inherit_drill_score(conn):
    """Nowa grupa zaczyna od zera, choćby poprzednia była dziś przerobiona do celu.

    `group_drill_scores` przeżywają `clear_all_groups` (praca ma zostać policzona),
    więc gdyby identyfikatory grup były wznawiane, świeża grupa startowałaby
    z cudzym postępem i zaliczałaby się bez ani jednego ćwiczenia."""
    old_gid = db.insert_group(conn, rule="stara", explanation="e", topic="articles")
    db.insert_group_drill_score(conn, group_id=old_gid, correct_items=5, total_items=5)
    assert db.group_drill_correct_today(conn, old_gid) == 5

    db.clear_all_groups(conn)
    new_gid = db.insert_group(conn, rule="nowa", explanation="e", topic="articles")
    assert new_gid != old_gid
    assert db.group_drill_correct_today(conn, new_gid) == 0


def test_migration_adds_group_id_to_legacy_errors_table(tmp_path):
    """Migracja na ŻYWEJ bazie: kolumna dochodzi, a istniejące wpisy zostają nietknięte.

    To jedyne miejsce, w którym błąd niszczy dane nie do odzyskania z gita — sprawdzenie
    ręczne nie wystarcza, bo nie chroni przed regresją."""
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        "CREATE TABLE errors ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,"
        " source TEXT NOT NULL, exercise_type TEXT NOT NULL, topic TEXT NOT NULL,"
        " student_text TEXT NOT NULL, correct_text TEXT NOT NULL,"
        " explanation TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'minor');"
    )
    legacy.execute(
        "INSERT INTO errors (created_at, source, exercise_type, topic, student_text,"
        " correct_text, explanation, severity) VALUES"
        " ('2026-01-01T10:00:00', 'import', 'imported', 'prepositions',"
        "  'depends from', 'depends on', 'kalka', 'minor')"
    )
    legacy.commit()
    legacy.close()

    conn = db.get_connection(path)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(errors)")}
        assert "group_id" in cols
        rows = list(conn.execute("SELECT student_text, group_id FROM errors"))
        assert len(rows) == 1
        assert rows[0]["student_text"] == "depends from"
        assert rows[0]["group_id"] is None
        # Ponowne otwarcie nie może próbować dodać kolumny drugi raz.
        db.get_connection(path).close()
    finally:
        conn.close()


def test_migration_adds_content_columns_to_a_legacy_cards_table(tmp_path):
    """Migracja pięciu kolumn treści na ŻYWEJ bazie sprzed przebudowy fiszek.

    `_SCHEMA` leci przez `executescript` PRZED `_migrate` przy KAŻDYM otwarciu, a
    `CREATE TABLE IF NOT EXISTS` na tabeli, która już istnieje, jest no-opem — samo
    dopisanie kolumny do `CREATE TABLE` w `_SCHEMA` nic nie da na istniejącej bazie,
    trzeba jej dodać w `_migrate` przez `ALTER TABLE`. Fixture `conn` tego nie łapie,
    bo zawsze tworzy pusty plik, w którym `cards` powstaje już z nowym schematem —
    ścieżka `ALTER TABLE` nigdy się tam nie wykonuje. Ten test odtwarza dokładnie
    kształt tabeli `cards` sprzed tej zmiany (taki, jaki ma dziś prawdziwa baza)."""
    path = tmp_path / "legacy_cards.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        "CREATE TABLE cards ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL, source_kind TEXT NOT NULL, source_id INTEGER NOT NULL,"
        " due_on TEXT NOT NULL, interval_days INTEGER NOT NULL,"
        " front_override TEXT, back_override TEXT,"
        " UNIQUE (source_kind, source_id));"
    )
    legacy.execute(
        "INSERT INTO cards (created_at, updated_at, source_kind, source_id, due_on,"
        " interval_days) VALUES"
        " ('2026-01-01T10:00:00', '2026-01-01T10:00:00', 'error', 1, '2026-09-18', 0)"
    )
    legacy.commit()
    legacy.close()

    conn = db.get_connection(path)  # nie może rzucić OperationalError: no such column
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
        assert {"front", "back", "shape", "shape_reason", "prepared_at"} <= cols
        rows = list(conn.execute("SELECT * FROM cards WHERE source_id = 1"))
        assert len(rows) == 1  # wiersz przetrwał migrację
        assert rows[0]["prepared_at"] is None
        # Ponowne otwarcie nie może próbować dodać kolumn drugi raz.
        db.get_connection(path).close()
    finally:
        conn.close()


# --- Fiszki -------------------------------------------------------------------

def _card_err(conn, topic="prepositions", student="depends from"):
    return db.insert_error(conn, source="test", exercise_type="imported", topic=topic,
                           student_text=student, correct_text="depends on",
                           explanation="kalka z polskiego", severity="minor")


def test_create_and_get_card(conn):
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    card = db.get_card(conn, cid)
    assert card["source_kind"] == "error"
    assert card["source_id"] == eid
    assert card["due_on"] == "2026-09-17"
    assert card["front_override"] is None


def test_one_card_per_source(conn):
    """Drugie założenie karty dla tego samego źródła NIE wywraca się i NIE tworzy
    duplikatu: zwraca istniejącą kartę i zostawia jej termin w spokoju.

    „Przygotuj karty" pyta o źródła bez karty i zakłada wiersze w dwóch osobnych
    wywołaniach; dwa równoległe kliknięcia mieszczą się między nimi. Wyjątek oznaczałby
    tam błąd 500 po opłaceniu już wysłanych partii."""
    eid = _card_err(conn)
    first = db.create_card(conn, source_kind="error", source_id=eid,
                           due_on="2026-09-17", interval_days=1)
    again = db.create_card(conn, source_kind="error", source_id=eid,
                           due_on="2026-09-18", interval_days=3)
    assert again == first
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    card = db.get_card(conn, first)
    assert (card["due_on"], card["interval_days"]) == ("2026-09-17", 1)


def test_creating_a_card_for_a_second_source_still_gets_a_fresh_id(conn):
    """`INSERT OR IGNORE` nie może po cichu zwracać id z poprzedniego wstawienia."""
    a, b = _card_err(conn, student="a"), _card_err(conn, student="b")
    first = db.create_card(conn, source_kind="error", source_id=a,
                           due_on="2026-09-17", interval_days=1)
    second = db.create_card(conn, source_kind="error", source_id=b,
                            due_on="2026-09-17", interval_days=1)
    assert first != second
    assert db.get_card(conn, second)["source_id"] == b


def test_get_card_by_source(conn):
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    assert db.get_card_by_source(conn, "error", eid)["id"] == cid
    assert db.get_card_by_source(conn, "group", eid) is None


def test_update_card_schedule(conn):
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    assert db.update_card_schedule(conn, cid, due_on="2026-09-24", interval_days=7) is True
    card = db.get_card(conn, cid)
    assert card["due_on"] == "2026-09-24"
    assert card["interval_days"] == 7


def test_set_card_override(conn):
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    assert db.set_card_override(conn, cid, front="It ___ on the weather.",
                                back="depends on") is True
    card = db.get_card(conn, cid)
    assert card["front_override"] == "It ___ on the weather."
    assert card["back_override"] == "depends on"


def test_card_unknown_count_only_counts_failures(conn):
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    db.insert_card_review(conn, card_id=cid, grade="unknown")
    db.insert_card_review(conn, card_id=cid, grade="known")
    db.insert_card_review(conn, card_id=cid, grade="unknown")
    assert db.card_unknown_count(conn, cid) == 2


def test_cards_due_returns_today_and_earlier(conn):
    a, b, c = _card_err(conn, student="a"), _card_err(conn, student="b"), _card_err(conn, student="c")
    ca = db.create_card(conn, source_kind="error", source_id=a, due_on="2026-09-10", interval_days=1)
    cb = db.create_card(conn, source_kind="error", source_id=b, due_on="2026-09-17", interval_days=1)
    db.create_card(conn, source_kind="error", source_id=c, due_on="2026-09-30", interval_days=1)
    # `cards_due` widzi tylko karty przygotowane i już ocenione — bez tego para (a, b)
    # byłaby „nowa", nie „zaległa".
    for cid in (ca, cb):
        db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
        db.insert_card_review(conn, card_id=cid, grade="known")
    rows = db.cards_due(conn, "2026-09-17")
    assert [r["source_id"] for r in rows] == [a, b]
    # `card_id` musi być w wyniku pod TĄ nazwą — czyta go flashcards.build_queue.
    assert all(r["card_id"] for r in rows)


def test_cards_due_filters_by_topic(conn):
    a = _card_err(conn, topic="prepositions", student="a")
    b = _card_err(conn, topic="articles", student="b")
    for eid in (a, b):
        cid = db.create_card(conn, source_kind="error", source_id=eid,
                             due_on="2026-09-17", interval_days=1)
        db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
        db.insert_card_review(conn, card_id=cid, grade="known")
    got = [r["source_id"] for r in db.cards_due(conn, "2026-09-17", topic="articles")]
    assert got == [b]


def test_sources_without_card_skips_those_that_have_one(conn):
    a, b = _card_err(conn, student="a"), _card_err(conn, student="b")
    db.create_card(conn, source_kind="error", source_id=a,
                   due_on="2026-09-17", interval_days=1)
    got = [r["source_id"] for r in db.sources_without_card(conn)]
    assert got == [b]


def test_sources_without_card_includes_groups(conn):
    gid = db.insert_group(conn, rule="depend + on", explanation="e", topic="prepositions")
    kinds = {r["source_kind"] for r in db.sources_without_card(conn)}
    assert "group" in kinds
    assert gid in [r["source_id"] for r in db.sources_without_card(conn)
                   if r["source_kind"] == "group"]


def test_cards_done_today_counts_distinct_cards(conn):
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    db.insert_card_review(conn, card_id=cid, grade="unknown")
    db.insert_card_review(conn, card_id=cid, grade="known")
    assert db.cards_done_today(conn) == 1


def test_cards_overdue_counts_only_the_past(conn):
    a, b = _card_err(conn, student="a"), _card_err(conn, student="b")
    ca = db.create_card(conn, source_kind="error", source_id=a,
                        due_on="2026-09-10", interval_days=1)
    cb = db.create_card(conn, source_kind="error", source_id=b,
                        due_on="2026-09-17", interval_days=1)
    for cid in (ca, cb):
        db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    assert db.cards_overdue(conn, "2026-09-17") == 1


def test_cards_overdue_ignores_cards_without_content(conn):
    """Karta bez treści nie jest długiem do odrobienia.

    Wiersz karty powstaje teraz przy PRZYGOTOWANIU, z terminem na dziś, więc karta
    pominięta przez model od jutra miałaby przeterminowany `due_on` — a nie wchodzi
    ani do `cards_due`, ani do `cards_new`. Uczeń widziałby zaległość, której nie ma
    jak odrobić."""
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-10", interval_days=0)
    assert db.cards_overdue(conn, "2026-09-17") == 0
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    db.insert_card_review(conn, card_id=cid, grade="unknown")
    assert db.cards_overdue(conn, "2026-09-17") == 1


def test_count_card_sources_covers_both_kinds(conn):
    """Licznik źródeł rozstrzyga, czy pusty ekran mówi „wszystko na dziś zrobione",
    czy „nie ma z czego robić fiszek" — musi widzieć i wpisy, i grupy."""
    assert db.count_card_sources(conn) == 0
    _card_err(conn, student="a")
    assert db.count_card_sources(conn) == 1
    db.insert_group(conn, rule="depend + on", explanation="e", topic="prepositions")
    assert db.count_card_sources(conn) == 2


def test_deleting_an_error_removes_its_card_and_reviews(conn):
    """Kaskada jest RĘCZNA — PRAGMA foreign_keys jest wyłączone, więc deklaratywne
    ON DELETE CASCADE nic by nie zrobiło. Ten test pada, jeśli ktoś usunie sprzątanie."""
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    db.insert_card_review(conn, card_id=cid, grade="known")
    db.delete_error(conn, eid)
    assert db.get_card(conn, cid) is None
    assert conn.execute("SELECT COUNT(*) FROM card_reviews WHERE card_id = ?",
                        (cid,)).fetchone()[0] == 0


def test_deleting_a_group_removes_its_card_and_reviews(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    cid = db.create_card(conn, source_kind="group", source_id=gid,
                         due_on="2026-09-17", interval_days=1)
    db.insert_card_review(conn, card_id=cid, grade="known")
    db.delete_group(conn, gid)
    assert db.get_card(conn, cid) is None
    assert conn.execute("SELECT COUNT(*) FROM card_reviews WHERE card_id = ?",
                        (cid,)).fetchone()[0] == 0


def test_deleting_an_error_leaves_other_cards_alone(conn):
    a, b = _card_err(conn, student="a"), _card_err(conn, student="b")
    keep = db.create_card(conn, source_kind="error", source_id=b,
                          due_on="2026-09-17", interval_days=1)
    db.create_card(conn, source_kind="error", source_id=a,
                   due_on="2026-09-17", interval_days=1)
    db.delete_error(conn, a)
    assert db.get_card(conn, keep) is not None


def test_cards_do_not_touch_the_streak(conn):
    """Fiszki mają własny licznik; seria mierzy co innego."""
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-17", interval_days=1)
    db.insert_card_review(conn, card_id=cid, grade="known")
    assert db.reviews_done_today(conn) == 0
    assert db.reviews_per_day(conn) == {}


# --- Treść fiszki -------------------------------------------------------------

def _orphaned_cards(conn) -> int:
    """Karty, których źródło już nie istnieje — po masowym kasowaniu ma być ich zero."""
    return conn.execute(
        "SELECT COUNT(*) FROM cards c "
        "LEFT JOIN errors e ON c.source_kind = 'error' AND e.id = c.source_id "
        "LEFT JOIN error_groups g ON c.source_kind = 'group' AND g.id = c.source_id "
        "WHERE COALESCE(e.id, g.id) IS NULL"
    ).fetchone()[0]


def _prep_err(conn, topic="collocations", student="in home", correct="at home"):
    return db.insert_error(conn, source="test", exercise_type="imported", topic=topic,
                           student_text=student, correct_text=correct,
                           explanation="stały zwrot", severity="minor")


def test_new_card_starts_unprepared(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-18", interval_days=0)
    assert db.get_card(conn, cid)["prepared_at"] is None
    assert db.count_unprepared(conn) == 1


def test_set_card_content_marks_it_prepared(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-18", interval_days=0)
    assert db.set_card_content(conn, cid, front="W domu jest cicho.", back="at home",
                               shape="translate", shape_reason="") is True
    card = db.get_card(conn, cid)
    assert card["front"] == "W domu jest cicho."
    assert card["shape"] == "translate"
    assert card["prepared_at"]
    assert db.count_unprepared(conn) == 0


def test_preparing_content_does_not_touch_the_schedule(conn):
    """Harmonogram przeżywa przeprojektowanie — zmienia się to, co widać, nie kiedy."""
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-10-01", interval_days=30)
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    card = db.get_card(conn, cid)
    assert card["due_on"] == "2026-10-01"
    assert card["interval_days"] == 30


def test_cards_unprepared_carries_the_source_fields(conn):
    eid = _prep_err(conn, topic="articles", student="a free time")
    db.create_card(conn, source_kind="error", source_id=eid,
                   due_on="2026-09-18", interval_days=0)
    row = db.cards_unprepared(conn)[0]
    assert row["topic"] == "articles"
    assert row["student_text"] == "a free time"
    assert row["correct_text"] == "at home"
    assert row["explanation"] == "stały zwrot"


def test_group_source_has_no_wrong_form(conn):
    """Grupa nie ma formy błędnej — reguła nie może wyciec jako `student_text`,
    bo prompt zakazuje pokazywania tego pola."""
    gid = db.insert_group(conn, topic="articles", rule="Przedimek przed rzeczownikiem",
                          explanation="policzalne wymagają przedimka")
    db.create_card(conn, source_kind="group", source_id=gid,
                   due_on="2026-09-18", interval_days=0)
    row = [r for r in db.cards_unprepared(conn) if r["source_kind"] == "group"][0]
    assert row["student_text"] == ""
    assert row["correct_text"] == "Przedimek przed rzeczownikiem"


def test_unprepared_cards_stay_out_of_both_queues(conn):
    eid = _prep_err(conn)
    db.create_card(conn, source_kind="error", source_id=eid,
                   due_on="2026-09-01", interval_days=1)
    assert db.cards_due(conn, "2026-09-18") == []
    assert db.cards_new(conn, "2026-09-18") == []


def test_a_prepared_card_without_reviews_is_new_not_due(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-01", interval_days=1)
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    assert [r["card_id"] for r in db.cards_new(conn, "2026-09-18")] == [cid]
    assert db.cards_due(conn, "2026-09-18") == []


def test_a_reviewed_card_becomes_due_not_new(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-01", interval_days=1)
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    db.insert_card_review(conn, card_id=cid, grade="known")
    assert [r["card_id"] for r in db.cards_due(conn, "2026-09-18")] == [cid]
    assert db.cards_new(conn, "2026-09-18") == []


def test_a_card_without_a_live_source_stays_out_of_both_queues(conn):
    """BLOKER, gdy tego zabraknie: karta-widmo wchodzi do kolejki, zjada slot dziennego
    limitu nowych kart, a sesja pomija ją po cichu (brak źródła → brak treści). Nigdy
    nieoceniona, wraca nazajutrz i każdego kolejnego dnia — kolejka zostaje zatkana,
    a uczeń widzi „na dziś nic" mimo setek gotowych kart."""
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-01", interval_days=1)
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    assert [r["card_id"] for r in db.cards_new(conn, "2026-09-18")] == [cid]

    # Źródło znika BEZ kaskady (surowy DELETE) — dokładnie tak wygląda wiersz osierocony
    # przez starszą wersję kodu, który został w bazie użytkownika.
    conn.execute("DELETE FROM errors WHERE id = ?", (eid,))
    conn.commit()
    assert db.cards_new(conn, "2026-09-18") == []

    db.insert_card_review(conn, card_id=cid, grade="known")
    assert db.cards_due(conn, "2026-09-18") == []


def test_a_group_card_without_its_group_stays_out_of_both_queues(conn):
    gid = db.insert_group(conn, rule="depend + on", explanation="e", topic="prepositions")
    cid = db.create_card(conn, source_kind="group", source_id=gid,
                         due_on="2026-09-01", interval_days=1)
    db.set_card_content(conn, cid, front="f", back="b", shape="gap", shape_reason="")
    conn.execute("DELETE FROM error_groups WHERE id = ?", (gid,))
    conn.commit()
    assert db.cards_new(conn, "2026-09-18") == []
    db.insert_card_review(conn, card_id=cid, grade="known")
    assert db.cards_due(conn, "2026-09-18") == []


def test_replacing_an_import_takes_the_cards_with_it(conn):
    """Import strategią „zastąp" woła `delete_errors_by_source`. Kaskada jest RĘCZNA —
    PRAGMA foreign_keys jest wyłączone i w schemacie nie ma żadnego ON DELETE."""
    doomed = db.insert_error(conn, source="import:plik.md", exercise_type="imported",
                             topic="collocations", student_text="in home",
                             correct_text="at home", explanation="e", severity="minor")
    kept = db.insert_error(conn, source="import:inny.md", exercise_type="imported",
                           topic="collocations", student_text="on the end",
                           correct_text="in the end", explanation="e", severity="minor")
    doomed_card = db.create_card(conn, source_kind="error", source_id=doomed,
                                 due_on="2026-09-18", interval_days=0)
    kept_card = db.create_card(conn, source_kind="error", source_id=kept,
                               due_on="2026-09-18", interval_days=0)
    db.insert_card_review(conn, card_id=doomed_card, grade="known")

    db.delete_errors_by_source(conn, "import:plik.md")

    assert db.get_card(conn, doomed_card) is None
    assert conn.execute("SELECT COUNT(*) FROM card_reviews WHERE card_id = ?",
                        (doomed_card,)).fetchone()[0] == 0
    assert db.get_card(conn, kept_card) is not None
    assert _orphaned_cards(conn) == 0


def test_regrouping_everything_takes_the_group_cards_with_it(conn):
    """„Przegrupuj wszystko" woła `clear_all_groups`: znikają WSZYSTKIE grupy, więc muszą
    zniknąć wszystkie karty grupowe. Karty wpisów zostają — ich źródła nikt nie ruszał."""
    gid = db.insert_group(conn, rule="depend + on", explanation="e", topic="prepositions")
    group_card = db.create_card(conn, source_kind="group", source_id=gid,
                                due_on="2026-09-18", interval_days=0)
    db.insert_card_review(conn, card_id=group_card, grade="unknown")
    eid = _prep_err(conn)
    error_card = db.create_card(conn, source_kind="error", source_id=eid,
                                due_on="2026-09-18", interval_days=0)

    db.clear_all_groups(conn)

    assert db.get_card(conn, group_card) is None
    assert conn.execute("SELECT COUNT(*) FROM card_reviews WHERE card_id = ?",
                        (group_card,)).fetchone()[0] == 0
    assert db.get_card(conn, error_card) is not None
    assert _orphaned_cards(conn) == 0


def test_cards_new_filters_by_topic(conn):
    a = _prep_err(conn, topic="collocations", student="a")
    b = _prep_err(conn, topic="articles", student="b")
    for eid in (a, b):
        cid = db.create_card(conn, source_kind="error", source_id=eid,
                             due_on="2026-09-18", interval_days=0)
        db.set_card_content(conn, cid, front="f", back="b", shape="translate",
                            shape_reason="")
    got = [r["source_id"] for r in db.cards_new(conn, "2026-09-18", topic="articles")]
    assert got == [b]


# --- Podpowiedź do karty z luką ----------------------------------------------

def test_set_card_content_stores_the_hint(conn):
    eid = _card_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-18", interval_days=0)
    db.set_card_content(conn, cid, front="I ______ you.", back="will call",
                        shape="gap", shape_reason="", hint="zadzwonię do ciebie")
    assert db.get_card(conn, cid)["hint"] == "zadzwonię do ciebie"


def _legacy_prepared(path, rows):
    """Baza z kartami PRZYGOTOWANYMI pod starym schematem — bez kolumny `hint`."""
    legacy = sqlite3.connect(path)
    legacy.executescript(
        "CREATE TABLE cards ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL, source_kind TEXT NOT NULL, source_id INTEGER NOT NULL,"
        " due_on TEXT NOT NULL, interval_days INTEGER NOT NULL,"
        " front_override TEXT, back_override TEXT,"
        " front TEXT, back TEXT, shape TEXT, shape_reason TEXT, prepared_at TEXT,"
        " UNIQUE (source_kind, source_id));"
    )
    for sid, shape in rows:
        legacy.execute(
            "INSERT INTO cards (created_at, updated_at, source_kind, source_id, due_on,"
            " interval_days, front, back, shape, prepared_at) VALUES"
            " ('2026-01-01T10:00:00', '2026-01-01T10:00:00', 'error', ?, '2026-10-01',"
            " 30, 'Przód ______', 'Tył', ?, '2026-09-18T10:00:00')", (sid, shape))
    legacy.commit()
    legacy.close()


def test_migration_sends_hintless_gap_cards_back_for_preparation(tmp_path):
    """137 kart z luką powstało, zanim podpowiedź istniała. Zamiast osobnego przycisku
    migracja zdejmuje im `prepared_at`, przez co wracają do zwykłego obiegu: licznik
    pokaże je jako nieprzygotowane, a „Przygotuj karty" ułoży je od nowa."""
    path = tmp_path / "hintless.db"
    _legacy_prepared(path, [(1, "gap"), (2, "translate")])

    conn = db.get_connection(path)
    try:
        assert "hint" in {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
        karty = {r["source_id"]: r for r in conn.execute("SELECT * FROM cards")}
        assert karty[1]["prepared_at"] is None, "karta z luką ma wrócić do przygotowania"
        # Karta tłumaczeniowa nie potrzebuje podpowiedzi — jej przód już jest po polsku,
        # więc odsyłanie jej do ponownego ułożenia byłoby wydatkiem bez powodu.
        assert karty[2]["prepared_at"] is not None, "karta tłumaczeniowa miała zostać"
        # Harmonogram przeżywa: zmienia się to, co uczeń zobaczy, nie kiedy.
        assert karty[1]["due_on"] == "2026-10-01"
        assert karty[1]["interval_days"] == 30
    finally:
        conn.close()


def test_migration_leaves_gap_cards_that_already_have_a_hint(tmp_path):
    """Idempotencja: po przygotowaniu karty mają podpowiedzi, więc kolejne otwarcie
    bazy nie może zdejmować im `prepared_at` w kółko."""
    path = tmp_path / "hinted.db"
    _legacy_prepared(path, [(1, "gap")])
    conn = db.get_connection(path)
    cid = conn.execute("SELECT id FROM cards WHERE source_id = 1").fetchone()["id"]
    db.set_card_content(conn, cid, front="I ______ you.", back="will call",
                        shape="gap", shape_reason="", hint="zadzwonię")
    conn.close()

    znowu = db.get_connection(path)
    try:
        karta = znowu.execute("SELECT * FROM cards WHERE source_id = 1").fetchone()
        assert karta["prepared_at"] is not None
        assert karta["hint"] == "zadzwonię"
    finally:
        znowu.close()
