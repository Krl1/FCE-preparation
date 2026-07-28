"""Testy importu wcześniejszych błędów (app/import_mistakes.py).

Import z TSV jest deterministyczny, więc testujemy go bez modelu. Idempotencja
(strategia „zastąp według pliku") jest obietnicą z docstringu — tu jest weryfikowana.
"""

import pytest

from app import db, import_mistakes as im

TSV = """date\twrong\tcorrect\tcategory\tnote\tsource
2026-06-16\tin home\tat home\tfixed_phrase\tstały zwrot\tksiążka
2026-06-16\ta free time\tfree time\tarticles_countability\tniepoliczalne\tksiążka
2026-06-16\tDepends from\tDepends on\tpreposition\tzawsze 'on'\tkorepetytor
2026-06-16\t\tbrak wrong\ttense\tpomijany wiersz\tksiążka
2026-06-16\tnieznana kat\tunknown cat\tcos_dziwnego\tfallback\tksiążka
"""


@pytest.fixture()
def conn(tmp_path):
    connection = db.get_connection(tmp_path / "import.db")
    yield connection
    connection.close()


@pytest.fixture()
def tsv_file(tmp_path):
    path = tmp_path / "english_mistakes.tsv"
    path.write_text(TSV, encoding="utf-8")
    return path


def test_import_tsv_maps_categories_and_skips_incomplete_rows(conn, tsv_file):
    imported, deleted = im.import_tsv(conn, tsv_file)
    assert (imported, deleted) == (4, 0)  # wiersz bez 'wrong' pominięty

    by_text = {e["student_text"]: e for e in db.list_errors(conn)}
    assert by_text["in home"]["topic"] == "collocations"          # fixed_phrase -> collocations
    assert by_text["a free time"]["topic"] == "articles"          # articles_countability -> articles
    assert by_text["Depends from"]["topic"] == "prepositions"     # preposition -> prepositions
    assert by_text["nieznana kat"]["topic"] == "cos_dziwnego"     # nieznana kategoria zachowana
    # Data z kolumny 'date', nie czas importu.
    assert by_text["in home"]["created_at"].startswith("2026-06-16")
    # Źródło oznaczone nazwą pliku (klucz strategii „zastąp według pliku").
    assert by_text["in home"]["source"] == "import:english_mistakes.tsv"


def test_import_tsv_is_idempotent(conn, tsv_file):
    im.import_tsv(conn, tsv_file)
    first_count = len(db.list_errors(conn, limit=10_000))

    imported, deleted = im.import_tsv(conn, tsv_file)
    assert (imported, deleted) == (4, 4)  # zastąpione, nie dopisane
    assert len(db.list_errors(conn, limit=10_000)) == first_count


def test_import_tsv_replaces_only_its_own_source(conn, tsv_file):
    im.import_tsv(conn, tsv_file)
    # Błąd z innego źródła (np. z aplikacji) musi przetrwać ponowny import.
    db.insert_error(conn, source="in_app", exercise_type="uoe_part2_open_cloze",
                    topic="tenses", student_text="have went", correct_text="have gone",
                    explanation="e")
    im.import_tsv(conn, tsv_file)

    sources = [e["source"] for e in db.list_errors(conn, limit=10_000)]
    assert sources.count("in_app") == 1
    assert sources.count("import:english_mistakes.tsv") == 4


def test_import_unstructured_uses_llm_and_normalizes_topic(conn, tmp_path, monkeypatch):
    path = tmp_path / "writing_mistakes.txt"
    path.write_text("Feedback: 'they extinct' should be 'they will become extinct'.", encoding="utf-8")

    from app.models import ErrorItem

    def fake_extract(text):
        return [
            ErrorItem(topic="tenses", student_text="they extinct",
                      correct_text="they will become extinct", explanation="e", severity="major"),
            # Temat wymyślony przez model — musi wpaść na 'language'.
            ErrorItem(topic="wymyslony_temat", student_text="a", correct_text="b",
                      explanation="e", severity="minor"),
        ]

    monkeypatch.setattr(im.llm_client, "extract_errors_from_text", fake_extract)

    imported, deleted = im.import_unstructured(conn, path, "writing")
    assert (imported, deleted) == (2, 0)
    topics = sorted(e["topic"] for e in db.list_errors(conn))
    assert topics == ["language", "tenses"]

    # Ponowny import zastępuje, nie dubluje — mimo niedeterministycznej ekstrakcji.
    imported, deleted = im.import_unstructured(conn, path, "writing")
    assert (imported, deleted) == (2, 2)
    assert len(db.list_errors(conn, limit=10_000)) == 2
