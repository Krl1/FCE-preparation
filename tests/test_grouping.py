"""Walidacja odpowiedzi modelu przy grupowaniu — czysta tabelka wejście-wyjście.

Model potrafi wymyślić id, pominąć wpis, powtórzyć grupę albo zwrócić temat spoza
taksonomii. Każdy z tych przypadków ma tu swój test, bo to jedyna warstwa, która
te przekłamania wychwytuje.
"""

import pytest

from app import grouping


def test_normalize_rule_ignores_case_punctuation_and_spacing():
    assert grouping.normalize_rule("  Depend + ON!  ") == "depend on"
    assert grouping.normalize_rule("depend on") == grouping.normalize_rule("Depend, on.")


def test_normalize_rule_merges_plus_notation_with_plain_spacing():
    """'+' to notacja zapisu reguły, nie jej treść — klucz ma je zrównać."""
    assert grouping.normalize_rule("depend + on") == grouping.normalize_rule("depend on")
    assert grouping.normalize_rule("make + noun") == grouping.normalize_rule("make noun")


def test_normalize_rule_of_blank_is_empty():
    assert grouping.normalize_rule("   ") == ""
    assert grouping.normalize_rule(None) == ""


def test_assigns_to_existing_group():
    out = {"assignments": [{"error_id": 1, "group_id": 7}]}
    plan = grouping.plan_assignments(out, [1], {7})
    assert plan.to_existing == {1: 7}
    assert plan.new_groups == ()
    assert plan.unassigned == ()


def test_invented_group_id_leaves_error_unassigned():
    out = {"assignments": [{"error_id": 1, "group_id": 999}]}
    plan = grouping.plan_assignments(out, [1], {7})
    assert plan.to_existing == {}
    assert plan.unassigned == (1,)


def test_error_skipped_by_model_stays_unassigned():
    out = {"assignments": [{"error_id": 1, "group_id": 7}]}
    plan = grouping.plan_assignments(out, [1, 2], {7})
    assert plan.unassigned == (2,)


def test_error_not_sent_is_ignored():
    out = {"assignments": [{"error_id": 42, "group_id": 7}]}
    plan = grouping.plan_assignments(out, [1], {7})
    assert plan.to_existing == {}
    assert plan.unassigned == (1,)


def test_duplicate_new_groups_are_merged_by_normalized_rule():
    out = {"assignments": [
        {"error_id": 1, "new_group": {"rule": "depend + on", "explanation": "a", "topic": "prepositions"}},
        {"error_id": 2, "new_group": {"rule": "Depend ON.", "explanation": "b", "topic": "prepositions"}},
    ]}
    plan = grouping.plan_assignments(out, [1, 2], set())
    assert len(plan.new_groups) == 1
    assert plan.new_groups[0].error_ids == (1, 2)
    assert plan.unassigned == ()


def test_new_group_topic_is_normalized_case_insensitively():
    out = {"assignments": [
        {"error_id": 1, "new_group": {"rule": "r", "explanation": "e", "topic": " Prepositions "},
         },
    ]}
    plan = grouping.plan_assignments(out, [1], set())
    assert plan.new_groups[0].topic == "prepositions"


def test_unknown_topic_falls_back_to_language():
    out = {"assignments": [
        {"error_id": 1, "new_group": {"rule": "r", "explanation": "e", "topic": "zmyslony"}},
    ]}
    plan = grouping.plan_assignments(out, [1], set())
    assert plan.new_groups[0].topic == "language"


def test_new_group_without_rule_leaves_error_unassigned():
    out = {"assignments": [
        {"error_id": 1, "new_group": {"rule": "  ", "explanation": "e", "topic": "articles"}},
    ]}
    plan = grouping.plan_assignments(out, [1], set())
    assert plan.new_groups == ()
    assert plan.unassigned == (1,)


def test_garbage_rows_do_not_raise():
    out = {"assignments": ["nonsense", {}, {"error_id": "x"}, {"error_id": 1, "group_id": "y"}]}
    plan = grouping.plan_assignments(out, [1], {7})
    assert plan.unassigned == (1,)


def test_missing_assignments_key_leaves_everything_unassigned():
    assert grouping.plan_assignments({}, [1, 2], set()).unassigned == (1, 2)
    assert grouping.plan_assignments(None, [1], set()).unassigned == (1,)


def test_unassigned_keeps_input_order_without_duplicates():
    plan = grouping.plan_assignments({}, [3, 1, 3, 2], set())
    assert plan.unassigned == (3, 1, 2)


def test_chunks_splits_evenly_and_keeps_remainder():
    assert grouping.chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert grouping.chunks([], 2) == []


def test_chunks_rejects_non_positive_size():
    with pytest.raises(ValueError):
        grouping.chunks([1], 0)
