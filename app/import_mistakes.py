"""Import wcześniejszych błędów do dziennika aplikacji.

Obsługuje dwa rodzaje źródeł:
1. Uporządkowany TSV (`english_mistakes.tsv`) — kolumny: date, wrong, correct, category, note, source.
   Import deterministyczny z mapowaniem kategorii na taksonomię FCE.
2. Nieuporządkowane pliki tekstowe (`writing_mistakes.txt`, `other_mistakes.txt`) — informacja
   zwrotna z ocen / notatki. Ekstrakcja błędów przez Claude (llm_client.extract_errors_from_text).

Uruchomienie:  python3 -m app.import_mistakes

Import jest IDEMPOTENTNY strategią „zastąp według pliku": każde źródło zapisuje błędy z etykietą
`source = "import:<nazwa_pliku>"`, a ponowny import najpierw usuwa poprzednie wpisy z tego pliku
i wstawia świeże. Dzięki temu powtórne uruchomienie (nawet przy niedeterministycznej ekstrakcji LLM)
nie mnoży duplikatów i odzwierciedla edycje plików.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import db
from . import fce_taxonomy as tax
from . import llm_client

_ROOT = Path(__file__).resolve().parent.parent
TSV_PATH = _ROOT / "english_mistakes.tsv"
# Nieuporządkowane pliki → (ścieżka, exercise_type nadawany zaimportowanym błędom)
TEXT_SOURCES: list[tuple[Path, str]] = [
    (_ROOT / "writing_mistakes.txt", "writing"),
    (_ROOT / "other_mistakes.txt", "imported"),
]

# Mapowanie kategorii z pliku TSV na identyfikatory tematów z taksonomii FCE.
CATEGORY_MAP: dict[str, str] = {
    "false_friend": "false_friends",
    "verb_pattern": "gerund_infinitive",
    "spelling": "spelling",
    "collocation": "collocations",
    "verb_form": "tenses",
    "compound_noun": "compound_nouns",
    "word_order": "word_order",
    "question_inversion": "word_order",
    "fixed_phrase": "collocations",
    "false_word": "word_formation",
    "articles_countability": "articles",
    "tense": "tenses",
    "relative_clause": "relative_clauses",
    "preposition": "prepositions",
    "adverb_adjective": "adverb_adjective",
}


def _source_tag(path: Path) -> str:
    return f"import:{path.name}"


def import_tsv(conn, path: Path) -> tuple[int, int]:
    """Import uporządkowanego TSV. Zwraca (zaimportowane, usunięte_przy_zastąpieniu)."""
    tag = _source_tag(path)
    deleted = db.delete_errors_by_source(conn, tag)
    imported = 0
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            wrong = (row.get("wrong") or "").strip()
            correct = (row.get("correct") or "").strip()
            if not wrong or not correct:
                continue
            category = (row.get("category") or "").strip()
            topic = CATEGORY_MAP.get(category, category or "language")
            db.insert_error(
                conn,
                source=tag,
                exercise_type="imported",
                topic=topic,
                student_text=wrong,
                correct_text=correct,
                explanation=(row.get("note") or "").strip(),
                severity="minor",
                created_at=(row.get("date") or "").strip() or None,
            )
            imported += 1
    return imported, deleted


def import_unstructured(conn, path: Path, exercise_type: str) -> tuple[int, int]:
    """Ekstrakcja błędów z nieuporządkowanego tekstu przez LLM.
    Zwraca (zaimportowane, usunięte_przy_zastąpieniu)."""
    tag = _source_tag(path)
    deleted = db.delete_errors_by_source(conn, tag)
    errors = llm_client.extract_errors_from_text(path.read_text(encoding="utf-8"))
    imported = 0
    for err in errors:
        topic = tax.normalize_topic(err.topic)
        db.insert_error(
            conn,
            source=tag,
            exercise_type=exercise_type,
            topic=topic,
            student_text=err.student_text,
            correct_text=err.correct_text,
            explanation=err.explanation,
            severity=err.severity,
        )
        imported += 1
    return imported, deleted


def main() -> None:
    conn = db.get_connection()

    if TSV_PATH.exists():
        imp, deleted = import_tsv(conn, TSV_PATH)
        note = f" (zastąpiono {deleted})" if deleted else ""
        print(f"[TSV]  {TSV_PATH.name}: zaimportowano {imp}{note}")
    else:
        print(f"[TSV]  pominięto — brak pliku {TSV_PATH.name}")

    for path, ex_type in TEXT_SOURCES:
        if not path.exists():
            print(f"[Text] pominięto — brak pliku {path.name}")
            continue
        print(f"[Text] {path.name}: ekstrakcja przez Claude…")
        try:
            imp, deleted = import_unstructured(conn, path, ex_type)
            note = f" (zastąpiono {deleted})" if deleted else ""
            print(f"[Text] {path.name}: zaimportowano {imp}{note}")
        except llm_client.LLMError as exc:
            print(f"[Text] BŁĄD ekstrakcji dla {path.name}: {exc}", file=sys.stderr)

    total = len(db.list_errors(conn, limit=100000))
    print(f"Dziennik zawiera teraz {total} błędów.")


if __name__ == "__main__":
    main()
