"""Ustrukturyzowana taksonomia egzaminu Cambridge B2 First (FCE).

Zakres v1: Use of English (gramatyka + słownictwo) oraz Writing.
Ta taksonomia jest kotwicą dla generowania zadań i klasyfikowania błędów —
każdy błąd zapisywany w dzienniku odwołuje się do jednego `topic` z tej listy.
"""

from __future__ import annotations

# --- Typy ćwiczeń ------------------------------------------------------------
# Każdy typ ma stały identyfikator (używany w API i bazie) oraz etykietę PL.

EXERCISE_TYPES: dict[str, dict] = {
    "uoe_part1_mcq_cloze": {
        "label": "Use of English – Part 1: multiple-choice cloze",
        "area": "use_of_english",
        "description": "Luki w tekście, wybór 1 z 4 słów (słownictwo, kolokacje, phrasal verbs, linkery).",
    },
    "uoe_part2_open_cloze": {
        "label": "Use of English – Part 2: open cloze",
        "area": "use_of_english",
        "description": "Luki w tekście uzupełniane jednym słowem (gramatyka).",
    },
    "uoe_part3_word_formation": {
        "label": "Use of English – Part 3: word formation",
        "area": "use_of_english",
        "description": "Tworzenie właściwej formy słowa od podanego rdzenia (afiksy).",
    },
    "uoe_part4_key_word_transformation": {
        "label": "Use of English – Part 4: key word transformation",
        "area": "use_of_english",
        "description": "Przekształcenie zdania z użyciem słowa-klucza (2–5 słów).",
    },
    "writing_essay": {
        "label": "Writing – essay",
        "area": "writing",
        "description": "Rozprawka na zadany temat z dwoma punktami do omówienia.",
    },
    "writing_email": {
        "label": "Writing – e-mail / list (formalny lub nieformalny)",
        "area": "writing",
        "description": "E-mail lub list z uwzględnieniem rejestru.",
    },
    "writing_review": {
        "label": "Writing – review",
        "area": "writing",
        "description": "Recenzja (film, książka, produkt, miejsce).",
    },
    "writing_article": {
        "label": "Writing – article",
        "area": "writing",
        "description": "Artykuł angażujący czytelnika na zadany temat.",
    },
    "writing_report": {
        "label": "Writing – report",
        "area": "writing",
        "description": "Raport z podziałem na sekcje i rekomendacjami.",
    },
}

# --- Tematy gramatyczne i leksykalne -----------------------------------------
# Do klasyfikacji błędów i ukierunkowanego generowania zadań.

TOPICS: dict[str, dict] = {
    # Gramatyka
    "tenses": {"label": "Czasy gramatyczne", "category": "grammar"},
    "conditionals": {"label": "Tryby warunkowe", "category": "grammar"},
    "reported_speech": {"label": "Mowa zależna", "category": "grammar"},
    "passive_voice": {"label": "Strona bierna", "category": "grammar"},
    "modals": {"label": "Czasowniki modalne", "category": "grammar"},
    "relative_clauses": {"label": "Zdania względne", "category": "grammar"},
    "gerund_infinitive": {"label": "Gerund / bezokolicznik", "category": "grammar"},
    "articles": {"label": "Przedimki (a/an/the)", "category": "grammar"},
    "comparatives": {"label": "Stopniowanie przymiotników", "category": "grammar"},
    "quantifiers": {"label": "Kwantyfikatory", "category": "grammar"},
    "linkers": {"label": "Linkery / spójniki", "category": "grammar"},
    "word_order": {"label": "Szyk zdania", "category": "grammar"},
    "adverb_adjective": {"label": "Przysłówek vs przymiotnik", "category": "grammar"},
    # Słownictwo
    "collocations": {"label": "Kolokacje", "category": "vocabulary"},
    "phrasal_verbs": {"label": "Phrasal verbs", "category": "vocabulary"},
    "prepositions": {"label": "Przyimki", "category": "vocabulary"},
    "word_formation": {"label": "Word formation (afiksy)", "category": "vocabulary"},
    "register": {"label": "Rejestr (formalny/nieformalny)", "category": "vocabulary"},
    "spelling": {"label": "Pisownia", "category": "vocabulary"},
    "false_friends": {"label": "False friends / mylone słowa", "category": "vocabulary"},
    "compound_nouns": {"label": "Rzeczowniki złożone", "category": "vocabulary"},
    # Writing (kryteria oceny FCE)
    "content": {"label": "Content (realizacja treści)", "category": "writing"},
    "communicative_achievement": {
        "label": "Communicative achievement (rejestr, styl, format)",
        "category": "writing",
    },
    "organisation": {"label": "Organisation (spójność, struktura)", "category": "writing"},
    "language": {"label": "Language (zakres i poprawność językowa)", "category": "writing"},
}

# Które tematy pasują do danego typu ćwiczenia (do ukierunkowanego generowania).
TYPE_TOPICS: dict[str, list[str]] = {
    "uoe_part1_mcq_cloze": ["collocations", "phrasal_verbs", "prepositions", "linkers", "register"],
    "uoe_part2_open_cloze": [
        "tenses", "conditionals", "passive_voice", "modals", "relative_clauses",
        "articles", "quantifiers", "linkers", "prepositions", "word_order",
    ],
    "uoe_part3_word_formation": ["word_formation"],
    "uoe_part4_key_word_transformation": [
        "tenses", "conditionals", "reported_speech", "passive_voice", "modals",
        "comparatives", "gerund_infinitive", "phrasal_verbs", "collocations",
    ],
    "writing_essay": ["content", "communicative_achievement", "organisation", "language"],
    "writing_email": ["content", "communicative_achievement", "organisation", "language"],
    "writing_review": ["content", "communicative_achievement", "organisation", "language"],
    "writing_article": ["content", "communicative_achievement", "organisation", "language"],
    "writing_report": ["content", "communicative_achievement", "organisation", "language"],
}


def is_writing(exercise_type: str) -> bool:
    """Czy dany typ ćwiczenia należy do części Writing."""
    return EXERCISE_TYPES.get(exercise_type, {}).get("area") == "writing"


def topics_for_type(exercise_type: str) -> list[str]:
    """Lista identyfikatorów tematów właściwych dla danego typu ćwiczenia."""
    return TYPE_TOPICS.get(exercise_type, [])


def topic_label(topic: str) -> str:
    """Czytelna etykieta tematu (fallback: sam identyfikator)."""
    return TOPICS.get(topic, {}).get("label", topic)


def taxonomy_payload() -> dict:
    """Kompletna taksonomia w formie serializowalnej dla frontendu (GET /api/taxonomy)."""
    return {
        "exercise_types": [
            {"id": tid, **meta, "topics": topics_for_type(tid)}
            for tid, meta in EXERCISE_TYPES.items()
        ],
        "topics": [{"id": t, **meta} for t, meta in TOPICS.items()],
    }
