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


def test_unknown_returns_a_scheduled_card_to_one_day():
    for days in (1, 7, 90):
        assert fc.next_interval(days, "unknown") == 1


def test_unknown_keeps_a_never_recalled_card_due_today():
    """Interwał 0 znaczy „jeszcze nierozpoznana". Karta, której uczeń nie umie za
    pierwszym razem, ma wrócić DZIŚ, a nie jutro — inaczej fiszka odkłada dokładnie
    ten materiał, który jest najsłabszy."""
    assert fc.next_interval(0, "unknown") == 0
    assert fc.next_interval(0, "śmieci") == 0


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
    new = [{"source_kind": "error", "source_id": 2, "card_id": 22}]
    q = fc.build_queue(due, new, new_limit=20)
    assert [(i.source_id, i.card_id) for i in q] == [(1, 11), (2, 22)]


def test_queue_caps_new_cards_at_the_limit():
    new = [{"source_kind": "error", "source_id": n, "card_id": n * 10} for n in range(1, 11)]
    q = fc.build_queue([], new, new_limit=3)
    assert len(q) == 3
    assert [i.card_id for i in q] == [10, 20, 30]


def test_queue_never_caps_due_cards():
    """Zaległe karty to materiał, który już raz widziałeś — limit dotyczy tylko nowych."""
    due = [{"source_kind": "error", "source_id": n, "card_id": n} for n in range(1, 31)]
    q = fc.build_queue(due, [], new_limit=3)
    assert len(q) == 30


def test_zero_limit_yields_only_due_cards():
    due = [{"source_kind": "group", "source_id": 5, "card_id": 50}]
    new = [{"source_kind": "error", "source_id": 6, "card_id": 60}]
    q = fc.build_queue(due, new, new_limit=0)
    assert [i.source_id for i in q] == [5]


def test_empty_inputs_give_empty_queue():
    assert fc.build_queue([], [], new_limit=20) == ()


def test_negative_limit_is_treated_as_zero():
    assert fc.build_queue([], [{"source_kind": "error", "source_id": 1, "card_id": 10}], new_limit=-5) == ()


def test_group_and_error_sources_both_survive_the_queue():
    due = [{"source_kind": "group", "source_id": 3, "card_id": 30}]
    new = [{"source_kind": "error", "source_id": 4, "card_id": 40}]
    q = fc.build_queue(due, new, new_limit=20)
    assert [i.source_kind for i in q] == ["group", "error"]


def test_unknown_grade_string_is_treated_as_failure():
    """Serwer nie ufa klientowi: cokolwiek innego niż 'known' cofa kartę na początek."""
    assert fc.next_interval(30, "śmieci") == 1


def test_due_date_rejects_negative_interval():
    with pytest.raises(ValueError):
        fc.due_date(date(2026, 9, 17), -1)


# --- Kształt karty i walidacja odpowiedzi modelu ------------------------------


def test_lexical_topics_default_to_translation():
    for topic in ("collocations", "prepositions", "false_friends", "phrasal_verbs"):
        assert fc.default_shape(topic) == fc.SHAPE_TRANSLATE


def test_grammar_topics_default_to_a_gap():
    for topic in ("tenses", "articles", "gerund_infinitive", "quantifiers", "word_order",
                  "reported_speech"):
        assert fc.default_shape(topic) == fc.SHAPE_GAP


def test_unknown_topic_falls_back_to_translation():
    """Karta tłumaczeniowa nie wymaga poprawnie postawionej luki, więc jest
    bezpieczniejszym domyślnym kształtem dla tematu, którego nie znamy."""
    assert fc.default_shape("zmyslony_temat") == fc.SHAPE_TRANSLATE
    assert fc.default_shape("") == fc.SHAPE_TRANSLATE


def test_ref_roundtrips():
    assert fc.make_ref("error", 12) == "error:12"
    assert fc.parse_ref("error:12") == ("error", 12)
    assert fc.parse_ref("group:3") == ("group", 3)


def test_parse_ref_rejects_rubbish():
    for bad in ("", "error", "error:", ":12", "error:abc", "wymyslony:1"):
        assert fc.parse_ref(bad) is None


def _sent(ref="error:1", shape=None):
    return [{"ref": ref, "suggested_shape": shape or fc.SHAPE_TRANSLATE}]


def test_accepts_a_card_matching_the_suggested_shape():
    out = {"cards": [{"ref": "error:1", "shape": "translate",
                      "front": "W domu jest cicho.", "back": "at home"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.unprepared == ()
    card = plan.prepared[0]
    assert (card.source_kind, card.source_id) == ("error", 1)
    assert card.shape == "translate"
    assert card.shape_reason == ""


def test_accepts_a_justified_deviation():
    out = {"cards": [{"ref": "error:1", "shape": "gap",
                      "front": "It ______ on the weather.", "back": "depends",
                      "shape_reason": "przyimek związany z czasownikiem"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.prepared[0].shape == "gap"
    assert plan.prepared[0].shape_reason == "przyimek związany z czasownikiem"


def test_rejects_an_unjustified_deviation():
    """Odstępstwo bez powodu jest nieodróżnialne od kaprysu, a testy podstawiają model."""
    out = {"cards": [{"ref": "error:1", "shape": "gap",
                      "front": "It ______ on the weather.", "back": "depends"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.prepared == ()
    assert plan.unprepared == ("error:1",)


def test_rejects_an_unknown_shape():
    out = {"cards": [{"ref": "error:1", "shape": "wymyslony",
                      "front": "f", "back": "b", "shape_reason": "bo tak"}]}
    assert fc.plan_cards(out, _sent()).unprepared == ("error:1",)


def test_rejects_a_gap_card_without_the_marker():
    out = {"cards": [{"ref": "error:1", "shape": "gap",
                      "front": "It depends on the weather.", "back": "depends on",
                      "shape_reason": "powód"}]}
    assert fc.plan_cards(out, _sent(shape=fc.SHAPE_GAP)).unprepared == ("error:1",)


def test_rejects_empty_sides():
    for front, back in (("", "b"), ("f", ""), ("   ", "b")):
        out = {"cards": [{"ref": "error:1", "shape": "translate",
                          "front": front, "back": back}]}
        assert fc.plan_cards(out, _sent()).unprepared == ("error:1",)


def test_entry_skipped_by_the_model_stays_unprepared():
    assert fc.plan_cards({"cards": []}, _sent()).unprepared == ("error:1",)
    assert fc.plan_cards(None, _sent()).unprepared == ("error:1",)


def test_card_for_something_we_did_not_send_is_ignored():
    out = {"cards": [{"ref": "error:99", "shape": "translate", "front": "f", "back": "b"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.prepared == ()
    assert plan.unprepared == ("error:1",)


def test_garbage_rows_do_not_raise():
    out = {"cards": ["śmieci", {}, {"ref": 7}, {"ref": "error:1"}]}
    assert fc.plan_cards(out, _sent()).unprepared == ("error:1",)


def test_garbage_top_level_output_does_not_raise():
    """`model_output` przychodzi wprost od modelu i nie jest nigdzie wcześniej sprawdzane
    pod kątem typu (`_extract_json` w app/llm_client.py robi gołe `json.loads`, mimo
    adnotacji `-> dict`) — model mógł więc zwrócić cokolwiek, nie tylko zły wiersz
    wewnątrz `cards`, ale i zły kształt na samej górze albo pod kluczem `cards`."""
    for bad in ("śmieci", [1, 2, 3], 42, {"cards": 42}):
        plan = fc.plan_cards(bad, _sent())
        assert plan.prepared == ()
        assert plan.unprepared == ("error:1",)


def test_unprepared_keeps_the_order_sent():
    sent = [{"ref": "error:3", "suggested_shape": "translate"},
            {"ref": "error:1", "suggested_shape": "translate"}]
    assert fc.plan_cards({"cards": []}, sent).unprepared == ("error:3", "error:1")
