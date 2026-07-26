"""Ustrukturyzowana taksonomia egzaminu Cambridge B2 First (FCE).

Zakres v1: Use of English (gramatyka + słownictwo) oraz Writing.
Ta taksonomia jest kotwicą dla generowania zadań i klasyfikowania błędów —
każdy błąd zapisywany w dzienniku odwołuje się do jednego `topic` z tej listy.

Etykiety są dwujęzyczne (`label` = PL, `label_en` = EN) na potrzeby przełącznika języka.
"""

from __future__ import annotations

# --- Typy ćwiczeń ------------------------------------------------------------
# Każdy typ ma stały identyfikator (używany w API i bazie) oraz etykiety PL/EN.

EXERCISE_TYPES: dict[str, dict] = {
    "uoe_part1_mcq_cloze": {
        "label": "Use of English – Part 1: multiple-choice cloze",
        "label_en": "Use of English – Part 1: multiple-choice cloze",
        "area": "use_of_english",
        "description": "Luki w tekście, wybór 1 z 4 słów (słownictwo, kolokacje, phrasal verbs, linkery).",
    },
    "uoe_part2_open_cloze": {
        "label": "Use of English – Part 2: open cloze",
        "label_en": "Use of English – Part 2: open cloze",
        "area": "use_of_english",
        "description": "Luki w tekście uzupełniane jednym słowem (gramatyka).",
    },
    "uoe_part3_word_formation": {
        "label": "Use of English – Part 3: word formation",
        "label_en": "Use of English – Part 3: word formation",
        "area": "use_of_english",
        "description": "Tworzenie właściwej formy słowa od podanego rdzenia (afiksy).",
    },
    "uoe_part4_key_word_transformation": {
        "label": "Use of English – Part 4: key word transformation",
        "label_en": "Use of English – Part 4: key word transformation",
        "area": "use_of_english",
        "description": "Przekształcenie zdania z użyciem słowa-klucza (2–5 słów).",
    },
    "writing_essay": {
        "label": "Writing – rozprawka (essay)",
        "label_en": "Writing – essay",
        "area": "writing",
        "description": "Rozprawka na zadany temat z dwoma punktami do omówienia.",
    },
    "writing_email": {
        "label": "Writing – e-mail / list (formalny lub nieformalny)",
        "label_en": "Writing – email / letter (formal or informal)",
        "area": "writing",
        "description": "E-mail lub list z uwzględnieniem rejestru.",
    },
    "writing_review": {
        "label": "Writing – recenzja (review)",
        "label_en": "Writing – review",
        "area": "writing",
        "description": "Recenzja (film, książka, produkt, miejsce).",
    },
    "writing_article": {
        "label": "Writing – artykuł (article)",
        "label_en": "Writing – article",
        "area": "writing",
        "description": "Artykuł angażujący czytelnika na zadany temat.",
    },
    "writing_report": {
        "label": "Writing – raport (report)",
        "label_en": "Writing – report",
        "area": "writing",
        "description": "Raport z podziałem na sekcje i rekomendacjami.",
    },
}

# --- Tematy gramatyczne i leksykalne -----------------------------------------
# Do klasyfikacji błędów i ukierunkowanego generowania zadań.

TOPICS: dict[str, dict] = {
    # Gramatyka
    "tenses": {"label": "Czasy gramatyczne", "label_en": "Tenses", "category": "grammar"},
    "conditionals": {"label": "Tryby warunkowe", "label_en": "Conditionals", "category": "grammar"},
    "reported_speech": {"label": "Mowa zależna", "label_en": "Reported speech", "category": "grammar"},
    "passive_voice": {"label": "Strona bierna", "label_en": "Passive voice", "category": "grammar"},
    "modals": {"label": "Czasowniki modalne", "label_en": "Modal verbs", "category": "grammar"},
    "relative_clauses": {"label": "Zdania względne", "label_en": "Relative clauses", "category": "grammar"},
    "gerund_infinitive": {"label": "Gerund / bezokolicznik", "label_en": "Gerund / infinitive", "category": "grammar"},
    "articles": {"label": "Przedimki (a/an/the)", "label_en": "Articles (a/an/the)", "category": "grammar"},
    "comparatives": {"label": "Stopniowanie przymiotników", "label_en": "Comparatives", "category": "grammar"},
    "quantifiers": {"label": "Kwantyfikatory", "label_en": "Quantifiers", "category": "grammar"},
    "linkers": {"label": "Linkery / spójniki", "label_en": "Linkers / connectors", "category": "grammar"},
    "word_order": {"label": "Szyk zdania", "label_en": "Word order", "category": "grammar"},
    "adverb_adjective": {"label": "Przysłówek vs przymiotnik", "label_en": "Adverb vs adjective", "category": "grammar"},
    # Słownictwo
    "collocations": {"label": "Kolokacje", "label_en": "Collocations", "category": "vocabulary"},
    "phrasal_verbs": {"label": "Phrasal verbs", "label_en": "Phrasal verbs", "category": "vocabulary"},
    "prepositions": {"label": "Przyimki", "label_en": "Prepositions", "category": "vocabulary"},
    "word_formation": {"label": "Word formation (afiksy)", "label_en": "Word formation (affixes)", "category": "vocabulary"},
    "register": {"label": "Rejestr (formalny/nieformalny)", "label_en": "Register (formal/informal)", "category": "vocabulary"},
    "spelling": {"label": "Pisownia", "label_en": "Spelling", "category": "vocabulary"},
    "false_friends": {"label": "False friends / mylone słowa", "label_en": "False friends / confused words", "category": "vocabulary"},
    "compound_nouns": {"label": "Rzeczowniki złożone", "label_en": "Compound nouns", "category": "vocabulary"},
    # Writing (kryteria oceny FCE)
    "content": {"label": "Content (realizacja treści)", "label_en": "Content", "category": "writing"},
    "communicative_achievement": {
        "label": "Communicative achievement (rejestr, styl, format)",
        "label_en": "Communicative achievement",
        "category": "writing",
    },
    "organisation": {"label": "Organisation (spójność, struktura)", "label_en": "Organisation", "category": "writing"},
    "language": {"label": "Language (zakres i poprawność językowa)", "label_en": "Language", "category": "writing"},
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


def topic_label(topic: str, lang: str = "pl") -> str:
    """Czytelna etykieta tematu w danym języku (fallback: sam identyfikator)."""
    meta = TOPICS.get(topic, {})
    key = "label_en" if lang == "en" else "label"
    return meta.get(key) or meta.get("label") or topic


def taxonomy_payload() -> dict:
    """Kompletna taksonomia (obie wersje językowe) dla frontendu (GET /api/taxonomy)."""
    return {
        "exercise_types": [
            {
                "id": tid,
                "label": meta["label"],
                "label_en": meta.get("label_en", meta["label"]),
                "area": meta["area"],
                "topics": topics_for_type(tid),
            }
            for tid, meta in EXERCISE_TYPES.items()
        ],
        "topics": [
            {
                "id": t,
                "label": meta["label"],
                "label_en": meta.get("label_en", meta["label"]),
                "category": meta["category"],
            }
            for t, meta in TOPICS.items()
        ],
    }
