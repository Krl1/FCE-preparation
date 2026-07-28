import json

import pytest

from app import llm_client


def test_extract_json_plain():
    assert llm_client._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_markdown_fence():
    text = '```json\n{"a": 1, "b": "x"}\n```'
    assert llm_client._extract_json(text) == {"a": 1, "b": "x"}


def test_extract_json_from_surrounding_prose():
    text = 'Oto wynik: {"correct": true} — gotowe.'
    assert llm_client._extract_json(text) == {"correct": True}


def test_call_json_retries_once_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_invoke(prompt, kind="other") -> str:
        calls["n"] += 1
        return "to nie jest JSON" if calls["n"] == 1 else '{"ok": true}'

    monkeypatch.setattr(llm_client, "_invoke", fake_invoke)
    assert llm_client._call_json("dowolny prompt") == {"ok": True}
    assert calls["n"] == 2  # jedna nieudana + jedna udana próba


def test_call_json_raises_after_second_failure(monkeypatch):
    monkeypatch.setattr(llm_client, "_invoke", lambda prompt, kind="other": "wciąż nie JSON")
    with pytest.raises(llm_client.LLMError):
        llm_client._call_json("prompt")


def _stub_items_response(monkeypatch, feedback="ok"):
    """Zaślepia odpowiedź modelu dla grade_items (same wyjaśnienia — werdykty liczy serwer)."""
    payload = {
        "feedback": feedback,
        "items": [
            {"number": 1, "comment": "c1", "option_notes": None},
            {"number": 2, "comment": "c2",
             "option_notes": [{"option": "A x", "is_correct": False, "comment": "źle"}]},
        ],
        "errors": [],
    }
    monkeypatch.setattr(llm_client, "_invoke", lambda prompt, kind="other": json.dumps(payload))


ITEMS = [
    {"number": 1, "options": ["A warm", "B heat"], "answer": "A warm"},
    {"number": 2, "options": ["A x", "B y"], "answer": "B y"},
]


def test_grade_items_all_correct(monkeypatch):
    _stub_items_response(monkeypatch)
    r = llm_client.grade_items("uoe_part1_mcq_cloze", "tekst", ITEMS, ["A warm", "B y"])
    assert r.correct is True
    assert r.score == "2/2"
    assert [i.correct for i in r.items] == [True, True]
    # Dla poprawnych luk nie pokazujemy omówienia wariantów.
    assert all(i.option_notes is None for i in r.items)


def test_grade_items_partial_and_normalizes_option_prefix(monkeypatch):
    _stub_items_response(monkeypatch)
    # "warm" bez prefiksu "A " ma zostać uznane za poprawne; druga luka błędna.
    r = llm_client.grade_items("uoe_part1_mcq_cloze", "tekst", ITEMS, ["warm", "A x"])
    assert r.correct is False
    assert r.score == "1/2"
    assert [i.correct for i in r.items] == [True, False]
    assert r.items[1].student_option == "A x"
    assert r.items[1].correct_option == "B y"
    assert r.items[1].option_notes  # omówienie tylko dla błędnej luki


def test_grade_items_unanswered_gap_counts_as_wrong(monkeypatch):
    _stub_items_response(monkeypatch)
    r = llm_client.grade_items("uoe_part1_mcq_cloze", "tekst", ITEMS, ["A warm", ""])
    assert r.score == "1/2"
    assert r.items[1].correct is False
    assert r.items[1].student_option is None


def test_grade_answer_parses_into_model(monkeypatch):
    payload = {
        "correct": False,
        "corrected": "The film was so boring that we left.",
        "feedback": "Drobny błąd w konstrukcji.",
        "errors": [
            {
                "topic": "comparatives",
                "student_text": "such boring",
                "correct_text": "so boring",
                "explanation": "Po 'so' używamy przymiotnika bez rzeczownika.",
                "severity": "minor",
            }
        ],
    }
    monkeypatch.setattr(llm_client, "_invoke", lambda prompt, kind="other": json.dumps(payload))
    result = llm_client.grade_answer(
        "uoe_part4_key_word_transformation", "…", "The film was such boring…", key_word="SO"
    )
    assert result.correct is False
    assert len(result.errors) == 1
    assert result.errors[0].topic == "comparatives"
