"""Reguła odstępu i składanie kolejki — czysta tabelka wejście-wyjście.

Moduł nie dotyka bazy ani modelu, więc cała logika harmonogramu testuje się tu,
bez stawiania aplikacji. Wzorzec jak w `app/streak.py` i `app/grouping.py`.
"""

from datetime import date

import pytest

from app import flashcards as fc


def test_new_card_starts_at_first_rung():
    assert fc.next_interval(0, "known") == 1


def test_known_climbs_the_ladder():
    assert fc.next_interval(1, "known") == 3
    assert fc.next_interval(3, "known") == 7
    assert fc.next_interval(7, "known") == 14
    assert fc.next_interval(14, "known") == 30
    assert fc.next_interval(30, "known") == 90


def test_top_rung_stays_at_top():
    assert fc.next_interval(90, "known") == 90


def test_unknown_always_returns_to_one_day():
    for days in (0, 1, 7, 90):
        assert fc.next_interval(days, "unknown") == 1


def test_off_ladder_value_climbs_to_next_rung_above_it():
    """Gdyby drabinka kiedyś się zmieniła, stara wartość ma się doczołgać, nie wysypać."""
    assert fc.next_interval(5, "known") == 7


def test_due_date_adds_the_interval():
    assert fc.due_date(date(2026, 9, 17), 3) == "2026-09-20"


def test_leech_only_from_the_threshold_up():
    assert fc.is_leech(3) is False
    assert fc.is_leech(4) is True
    assert fc.is_leech(9) is True


def test_queue_puts_due_cards_before_new_ones():
    due = [{"source_kind": "error", "source_id": 1, "card_id": 11}]
    new = [{"source_kind": "error", "source_id": 2}]
    q = fc.build_queue(due, new, new_limit=20)
    assert [(i.source_id, i.card_id) for i in q] == [(1, 11), (2, None)]


def test_queue_caps_new_cards_at_the_limit():
    new = [{"source_kind": "error", "source_id": n} for n in range(1, 11)]
    q = fc.build_queue([], new, new_limit=3)
    assert len(q) == 3
    assert all(i.card_id is None for i in q)


def test_queue_never_caps_due_cards():
    """Zaległe karty to materiał, który już raz widziałeś — limit dotyczy tylko nowych."""
    due = [{"source_kind": "error", "source_id": n, "card_id": n} for n in range(1, 31)]
    q = fc.build_queue(due, [], new_limit=3)
    assert len(q) == 30


def test_zero_limit_yields_only_due_cards():
    due = [{"source_kind": "group", "source_id": 5, "card_id": 50}]
    new = [{"source_kind": "error", "source_id": 6}]
    q = fc.build_queue(due, new, new_limit=0)
    assert [i.source_id for i in q] == [5]


def test_empty_inputs_give_empty_queue():
    assert fc.build_queue([], [], new_limit=20) == ()


def test_negative_limit_is_treated_as_zero():
    assert fc.build_queue([], [{"source_kind": "error", "source_id": 1}], new_limit=-5) == ()


def test_group_and_error_sources_both_survive_the_queue():
    due = [{"source_kind": "group", "source_id": 3, "card_id": 30}]
    new = [{"source_kind": "error", "source_id": 4}]
    q = fc.build_queue(due, new, new_limit=20)
    assert [i.source_kind for i in q] == ["group", "error"]


def test_unknown_grade_string_is_treated_as_failure():
    """Serwer nie ufa klientowi: cokolwiek innego niż 'known' cofa kartę na początek."""
    assert fc.next_interval(30, "śmieci") == 1


def test_due_date_rejects_negative_interval():
    with pytest.raises(ValueError):
        fc.due_date(date(2026, 9, 17), -1)
