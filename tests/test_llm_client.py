import json

import pytest

from app import flashcards, llm_client


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


def test_review_dispute_missing_fields_default_to_upholding(monkeypatch):
    """Brak jednoznacznej odpowiedzi traktujemy jak obstawanie i brak zmian w danych —
    bezpieczniej nie ruszać dziennika ucznia."""
    monkeypatch.setattr(llm_client, "_invoke", lambda p, kind="other": json.dumps(
        {"revised_explanation": "x"}
    ))
    out = llm_client.review_dispute(
        disputed_text="d", user_comment="c", exercise_context="ctx", student_answers_text="a"
    )
    assert out["verdict"] == "rejected"
    assert out["student_was_right"] is False


def test_review_dispute_separates_wrong_explanation_from_wrong_answer(monkeypatch):
    """Najczęstszy przypadek: wyjaśnienie zmyśliło cytat, ale odpowiedź i tak była błędna.
    Zastrzeżenie musi zostać uznane, a dane pozostać nietknięte."""
    monkeypatch.setattr(llm_client, "_invoke", lambda p, kind="other": json.dumps(
        {"explanation_was_wrong": True, "student_answer_was_acceptable": False,
         "revised_explanation": "Cytat był zmyślony, ale 'gone' nadal jest błędne.",
         "reasoning": "r"}
    ))
    out = llm_client.review_dispute(
        disputed_text="d", user_comment="c", exercise_context="ctx", student_answers_text="a"
    )
    assert out["verdict"] == "upheld"          # wyjaśnienie było błędne
    assert out["student_was_right"] is False   # ale odpowiedzi nie zaliczamy


def test_review_dispute_accepts_equivalent_answer(monkeypatch):
    monkeypatch.setattr(llm_client, "_invoke", lambda p, kind="other": json.dumps(
        {"explanation_was_wrong": True, "student_answer_was_acceptable": True,
         "revised_explanation": "r", "reasoning": "r"}
    ))
    out = llm_client.review_dispute(
        disputed_text="d", user_comment="c", exercise_context="ctx", student_answers_text="a"
    )
    assert out["verdict"] == "upheld" and out["student_was_right"] is True


def test_review_dispute_prompt_contains_exercise_and_objection(monkeypatch):
    """Prompt musi zawierać dokładną treść zadania — to na jej podstawie model
    weryfikuje, czy wyjaśnienie nie powołuje się na nieistniejące fragmenty."""
    seen = {}

    def spy(prompt, kind="other"):
        seen["prompt"] = prompt
        seen["kind"] = kind
        return json.dumps({"explanation_was_wrong": True, "student_answer_was_acceptable": True,
                           "revised_explanation": "r", "reasoning": "bo tak"})

    monkeypatch.setattr(llm_client, "_invoke", spy)
    out = llm_client.review_dispute(
        disputed_text="Wyjaśnienie cytuje 'xyz'",
        user_comment="W zadaniu nie było słowa xyz",
        exercise_context="[1] I ______ done it. | poprawna odpowiedź: have",
        student_answers_text="1. has",
    )
    assert out["verdict"] == "upheld" and out["student_was_right"] is True
    assert seen["kind"] == "dispute"
    assert "I ______ done it." in seen["prompt"]
    assert "W zadaniu nie było słowa xyz" in seen["prompt"]
    assert "1. has" in seen["prompt"]
    # Prompt musi jawnie zniechęcać do ustępowania z uprzejmości i rozdzielać dwie osie.
    low = seen["prompt"].lower()
    assert "nie ustępuj" in low or "rzetelną" in low
    assert "niezależnie" in low


def test_grade_items_links_errors_to_item_numbers(monkeypatch):
    """Błąd musi wiedzieć, z której pozycji pochodzi — inaczej korekta po zastrzeżeniu
    nie wiedziałaby, który wpis w dzienniku usunąć."""
    payload = {
        "feedback": "f",
        "items": [{"number": 1, "correct": False, "comment": "c"},
                  {"number": 2, "correct": False, "comment": "c"}],
        "errors": [{"topic": "tenses", "student_text": "zle2", "correct_text": "B y",
                    "explanation": "e", "severity": "minor"}],
    }
    monkeypatch.setattr(llm_client, "_invoke", lambda p, kind="other": json.dumps(payload))
    items = [{"number": 1, "options": ["A a", "B b"], "answer": "A a"},
             {"number": 2, "options": ["A x", "B y"], "answer": "B y"}]
    result = llm_client.grade_items("uoe_part1_mcq_cloze", "tekst", items, ["A a", "zle2"])
    assert result.errors[0].item_number == 2


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


# --- Wiązanie błędów z lukami (regresja: powtarzające się odpowiedzi) ---------

FIVE_GAPS = [
    {"number": n, "answer": a}
    for n, a in [(1, "in"), (2, "the"), (3, "a"), (4, "The"), (5, "the")]
]


def _stub(monkeypatch, payload):
    monkeypatch.setattr(llm_client, "_invoke", lambda p, kind="other": json.dumps(payload))


def test_identical_student_answers_still_link_to_distinct_gaps(monkeypatch):
    """Regresja: przy czterech pustych lukach zapisanych jako '-' wiązanie po treści
    odpowiedzi sklejało wszystkie błędy w JEDNĄ pozycję. Skutek w aplikacji: przycisk
    „Dodaj do dziennika" pojawiał się tylko przy ostatniej luce, a jego kliknięcie
    zapisywało błąd zupełnie innej luki."""
    _stub(monkeypatch, {
        "feedback": "f",
        "items": [{"number": n, "comment": f"c{n}"} for n in range(1, 6)],
        # Model podaje item_number — tak jak każe mu prompt.
        "errors": [
            {"item_number": n, "topic": "articles", "student_text": "-",
             "correct_text": "x", "explanation": f"e{n}", "severity": "minor"}
            for n in (1, 2, 4, 5)
        ],
    })
    r = llm_client.grade_items("uoe_part2_open_cloze", "tekst", FIVE_GAPS,
                               ["-", "-", "a", "-", "-"], topic="articles")
    assert r.score == "1/5"          # poprawna tylko luka 3
    assert [e.item_number for e in r.errors] == [1, 2, 4, 5]
    # Treść wpisu opisuje TĘ lukę, przy której się go zatwierdza.
    assert [e.correct_text for e in r.errors] == ["in", "the", "The", "the"]
    assert all(e.student_text == "-" for e in r.errors)


def test_errors_without_item_numbers_are_spread_over_wrong_gaps(monkeypatch):
    """Gdy model nie poda numerów, rozdzielamy błędy po kolei — nadal jeden na lukę."""
    _stub(monkeypatch, {
        "feedback": "f",
        "items": [{"number": n, "comment": f"c{n}"} for n in range(1, 6)],
        "errors": [{"topic": "articles", "student_text": "-", "correct_text": "x",
                    "explanation": f"e{i}", "severity": "minor"} for i in range(4)],
    })
    r = llm_client.grade_items("uoe_part2_open_cloze", "t", FIVE_GAPS,
                               ["-", "-", "a", "-", "-"], topic="articles")
    assert [e.item_number for e in r.errors] == [1, 2, 4, 5]


def test_missing_error_for_wrong_gap_is_synthesized(monkeypatch):
    """Model pominął dwie luki — propozycje składamy z własnych danych, żeby żadna
    błędna luka nie została bez czego zatwierdzić."""
    _stub(monkeypatch, {
        "feedback": "f",
        "items": [{"number": n, "comment": f"komentarz {n}"} for n in range(1, 6)],
        "errors": [{"item_number": 1, "topic": "prepositions", "student_text": "-",
                    "correct_text": "in", "explanation": "od modelu", "severity": "major"}],
    })
    r = llm_client.grade_items("uoe_part2_open_cloze", "t", FIVE_GAPS,
                               ["-", "-", "a", "-", "-"], topic="articles")
    assert [e.item_number for e in r.errors] == [1, 2, 4, 5]
    assert r.errors[0].explanation == "od modelu" and r.errors[0].severity == "major"
    # Uzupełnione: wyjaśnienie z komentarza do luki, temat z zadania, waga domyślna.
    assert r.errors[1].explanation == "komentarz 2"
    assert r.errors[1].topic == "articles" and r.errors[1].severity == "minor"


def test_error_pointing_at_a_correct_gap_is_dropped(monkeypatch):
    """Błąd przy luce zaliczonej jako poprawna nie może trafić do propozycji."""
    _stub(monkeypatch, {
        "feedback": "f",
        "items": [{"number": n, "comment": "c"} for n in range(1, 6)],
        "errors": [{"item_number": 3, "topic": "articles", "student_text": "a",
                    "correct_text": "a", "explanation": "zmyślone", "severity": "minor"}],
    })
    r = llm_client.grade_items("uoe_part2_open_cloze", "t", FIVE_GAPS,
                               ["in", "the", "a", "The", "the"], topic="articles")
    assert r.score == "5/5"
    assert r.errors == []


def test_grade_items_prompt_demands_item_number(monkeypatch):
    seen = {}

    def spy(prompt, kind="other"):
        seen["prompt"] = prompt
        return json.dumps({"feedback": "f", "items": [], "errors": []})

    monkeypatch.setattr(llm_client, "_invoke", spy)
    llm_client.grade_items("uoe_part2_open_cloze", "t", FIVE_GAPS, ["-"] * 5)
    assert "item_number" in seen["prompt"]


# --- Grupowanie ---------------------------------------------------------------

def test_group_errors_passes_errors_and_groups_into_prompt(monkeypatch):
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"] = prompt
        seen["kind"] = kind
        return {"assignments": [{"error_id": 1, "group_id": 7}]}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    out = llm_client.group_errors(
        errors=[{"id": 1, "topic": "prepositions", "student_text": "depends from",
                 "correct_text": "depends on", "explanation": "kalka"}],
        existing_groups=[{"id": 7, "rule": "depend + on", "topic": "prepositions"}],
    )
    assert out == {"assignments": [{"error_id": 1, "group_id": 7}]}
    assert seen["kind"] == "group"
    assert "depends from" in seen["prompt"]
    assert "depend + on" in seen["prompt"]
    assert "7" in seen["prompt"]


def test_group_errors_without_existing_groups_still_builds_prompt(monkeypatch):
    monkeypatch.setattr(llm_client, "_call_json",
                        lambda prompt, kind="other": {"assignments": []})
    assert llm_client.group_errors(errors=[{"id": 1, "topic": "articles",
                                            "student_text": "a", "correct_text": "b",
                                            "explanation": "c"}],
                                   existing_groups=[]) == {"assignments": []}


def test_group_errors_with_no_errors_skips_the_model(monkeypatch):
    def explode(prompt, kind="other"):
        raise AssertionError("model nie powinien być wołany dla pustej listy")

    monkeypatch.setattr(llm_client, "_call_json", explode)
    assert llm_client.group_errors(errors=[], existing_groups=[]) == {"assignments": []}


def test_group_errors_prompt_allows_one_new_group_for_several_errors(monkeypatch):
    """Pierwsza porcja nie widzi żadnych grup, więc bez tego zdania każdy błąd zakłada
    własną — na 192 wpisach dałoby to setki grup-singletonów („za drobno" ze spisu ryzyk).
    Scalanie po `normalize_rule` działa tylko, gdy model powtórzy TĘ SAMĄ nazwę reguły."""
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"] = prompt
        return {"assignments": []}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    llm_client.group_errors(
        errors=[{"id": 1, "topic": "prepositions", "student_text": "depends from",
                 "correct_text": "depends on", "explanation": "c"},
                {"id": 2, "topic": "prepositions", "student_text": "depend from it",
                 "correct_text": "depend on it", "explanation": "c"}],
        existing_groups=[],
    )
    assert "JEDNEJ nowej grupy" in seen["prompt"]
    assert "dokładnie tej samej nazwy 'rule'" in seen["prompt"]
    assert "inny błąd z listy łamie tę samą regułę" in seen["prompt"]


def test_group_errors_prompt_enumerates_valid_topics(monkeypatch):
    """Bez zamkniętej listy model wymyśla tematy, a normalize_topic cicho zrzuca je do 'language'."""
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"] = prompt
        return {"assignments": []}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    llm_client.group_errors(
        errors=[{"id": 1, "topic": "articles", "student_text": "a",
                 "correct_text": "b", "explanation": "c"}],
        existing_groups=[],
    )
    assert "prepositions" in seen["prompt"]
    assert "false_friends" in seen["prompt"]
    assert "error_id" in seen["prompt"]


def test_generate_drill_includes_group_contexts(monkeypatch):
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"] = prompt
        return {"exercise_type": "uoe_part2_open_cloze", "instructions": "i",
                "items": [{"number": n, "question_text": "q", "options": None,
                           "key_word": None, "stem": None, "answer": "a",
                           "answer_notes": "n"} for n in range(1, 6)]}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    llm_client.generate_drill("prepositions", "depends from", "depends on", "kalka",
                              contexts=["it depends from weather", "depends from him"])
    assert "it depends from weather" in seen["prompt"]
    assert "depends from him" in seen["prompt"]


def test_generate_drill_without_contexts_keeps_old_prompt_shape(monkeypatch):
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"] = prompt
        return {"exercise_type": "uoe_part2_open_cloze", "instructions": "i",
                "items": [{"number": n, "question_text": "q", "options": None,
                           "key_word": None, "stem": None, "answer": "a",
                           "answer_notes": "n"} for n in range(1, 6)]}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    llm_client.generate_drill("prepositions", "depends from", "depends on", "kalka")
    assert "depends from" in seen["prompt"]


# --- Generowanie treści fiszek ------------------------------------------------

def _card_item(ref="error:1", topic="collocations", shape="translate"):
    return {"ref": ref, "topic": topic, "topic_label": "Kolokacje",
            "student_text": "in home", "correct_text": "at home",
            "explanation": "stały zwrot", "suggested_shape": shape}


def test_generate_cards_passes_the_material_and_the_suggestion(monkeypatch):
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"], seen["kind"] = prompt, kind
        return {"cards": []}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    llm_client.generate_cards([_card_item()])
    assert seen["kind"] == "cards"
    assert "at home" in seen["prompt"]
    assert "error:1" in seen["prompt"]
    assert "translate" in seen["prompt"]


def test_generate_cards_forbids_showing_the_wrong_form(monkeypatch):
    """Cały powód tej zmiany: forma błędna nie może trafić na kartę, a model ma ją
    w danych wejściowych, więc zakaz musi być w prompcie wprost."""
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"] = prompt
        return {"cards": []}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    llm_client.generate_cards([_card_item()])
    assert "NIE WOLNO" in seen["prompt"]
    assert "in home" in seen["prompt"]          # podana jako forma do unikania


def test_generate_cards_explains_the_gap_marker(monkeypatch):
    seen = {}
    monkeypatch.setattr(llm_client, "_call_json",
                        lambda prompt, kind="other": seen.setdefault("p", prompt) and {} or {"cards": []})
    llm_client.generate_cards([_card_item(shape="gap")])
    assert flashcards.GAP_MARK in seen["p"]


def test_group_material_carries_no_forbidden_form(monkeypatch):
    """Grupa nie ma formy błędnej, więc w jej wierszu nie ma czego zakazywać."""
    seen = {}

    def fake_call(prompt, kind="other"):
        seen["prompt"] = prompt
        return {"cards": []}

    monkeypatch.setattr(llm_client, "_call_json", fake_call)
    llm_client.generate_cards([{"ref": "group:4", "topic": "articles",
                                "topic_label": "Przedimki", "student_text": "",
                                "correct_text": "Przedimek przed rzeczownikiem",
                                "explanation": "policzalne wymagają przedimka",
                                "suggested_shape": "gap"}])
    assert "NIE POKAZUJ" not in seen["prompt"]
    assert "Przedimek przed rzeczownikiem" in seen["prompt"]


def test_generate_cards_with_no_items_skips_the_model(monkeypatch):
    def explode(prompt, kind="other"):
        raise AssertionError("pusta partia nie może wołać modelu")

    monkeypatch.setattr(llm_client, "_call_json", explode)
    assert llm_client.generate_cards([]) == {"cards": []}
