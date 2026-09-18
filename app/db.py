"""Warstwa trwałości (SQLite) — dziennik błędów, zadania i podejścia.

Dziennik błędów (`errors`) jest sercem aplikacji: steruje doborem kolejnych zadań
(przez `srs.py`) i zasila widok „Moje błędy".
"""

from __future__ import annotations

import functools
import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "fce.db"
DB_PATH = Path(os.environ.get("FCE_DB_PATH", str(_DEFAULT_DB)))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    type        TEXT NOT NULL,
    topic       TEXT NOT NULL,
    prompt_json TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'in_app',
    -- NULL = zadanie czeka w kolejce (wygenerowane wsadowo, jeszcze nie pokazane)
    served_at   TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id    INTEGER,
    created_at     TEXT NOT NULL,
    type           TEXT NOT NULL,
    student_answer TEXT NOT NULL,
    is_correct     INTEGER,
    grading_json   TEXT NOT NULL,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id)
);

CREATE TABLE IF NOT EXISTS errors (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    source         TEXT NOT NULL,
    exercise_type  TEXT NOT NULL,
    topic          TEXT NOT NULL,
    student_text   TEXT NOT NULL,
    correct_text   TEXT NOT NULL,
    explanation    TEXT NOT NULL,
    severity       TEXT NOT NULL DEFAULT 'minor'
);

CREATE INDEX IF NOT EXISTS idx_errors_topic ON errors(topic);
CREATE INDEX IF NOT EXISTS idx_errors_created ON errors(created_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    error_id   INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_created ON reviews(created_at);

-- Wyniki ćwiczeń do konkretnego błędu (zakładka „Ćwicz błędy"). Dzienny cel zalicza błąd
-- dopiero po uzbieraniu wymaganej liczby POPRAWNYCH ćwiczeń w danym dniu.
CREATE TABLE IF NOT EXISTS drill_scores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    error_id      INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    correct_items INTEGER NOT NULL,
    total_items   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drill_error ON drill_scores(error_id, created_at);

CREATE TABLE IF NOT EXISTS usage_events (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at                  TEXT NOT NULL,
    kind                        TEXT NOT NULL,
    model                       TEXT NOT NULL DEFAULT '',
    input_tokens                INTEGER NOT NULL DEFAULT 0,
    output_tokens               INTEGER NOT NULL DEFAULT 0,
    cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_input_tokens     INTEGER NOT NULL DEFAULT 0,
    est_input_tokens            INTEGER NOT NULL DEFAULT 0,
    cost_usd                    REAL NOT NULL DEFAULT 0,
    duration_ms                 INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_events(created_at);

-- Zastrzeżenia do wyjaśnień modelu. Uczeń kwestionuje wyjaśnienie, model je weryfikuje,
-- a ewentualna korekta danych (usunięcie fałszywego błędu z dziennika) następuje dopiero
-- po zatwierdzeniu przez ucznia — stąd osobne `applied_at`.
CREATE TABLE IF NOT EXISTS disputes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    scope         TEXT NOT NULL,              -- 'item' (pozycja zadania) | 'error' (wpis w dzienniku)
    exercise_id   INTEGER,
    item_number   INTEGER,
    error_id      INTEGER,
    disputed_text TEXT NOT NULL,
    user_comment  TEXT NOT NULL DEFAULT '',
    verdict       TEXT,                       -- 'upheld' (uczeń miał rację) | 'rejected'
    revised_text  TEXT,
    student_was_right INTEGER NOT NULL DEFAULT 0,
    applied_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_disputes_created ON disputes(created_at);

-- Grupy błędów: jedna reguła wraz z kontekstami, w których została złamana.
-- Grupa jest dodatkowym widokiem nad dziennikiem — nie zastępuje wpisów i niczego nie kasuje.
CREATE TABLE IF NOT EXISTS error_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    rule        TEXT NOT NULL,
    explanation TEXT NOT NULL,
    topic       TEXT NOT NULL
);

-- Zaliczenia grup są w osobnych tabelach zamiast w `reviews`/`drill_scores`, bo
-- `reviews.error_id` jest NOT NULL, a zdjęcie tego w SQLite wymaga przebudowy tabeli.
-- Na żywej bazie z realną historią serii to ryzyko bez pokrycia.
CREATE TABLE IF NOT EXISTS group_reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_group_reviews_created ON group_reviews(created_at);

CREATE TABLE IF NOT EXISTS group_drill_scores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id      INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    correct_items INTEGER NOT NULL,
    total_items   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_group_drill ON group_drill_scores(group_id, created_at);

-- Fiszki. Treść (`front`/`back`/`shape`/`shape_reason`) powstaje RAZ, wsadowo, z modelu
-- i leży w tabeli — karta nie jest już renderowana ze źródła przy każdym pokazaniu.
-- `prepared_at IS NULL` oznacza kartę czekającą w kolejce przygotowania (patrz
-- `cards_unprepared`); dopóki nie ma treści, karta nie trafia ani do `cards_new`,
-- ani do `cards_due`. `front_override`/`back_override` to relikt poprzedniego
-- podejścia (treść ulepszona ręcznie nad renderowanym źródłem) — zostają nietknięte,
-- bo przebudowa żywej bazy z historią ocen to osobne ryzyko.
-- Świadomie bez kolumn `ease`, `reps` i `lapses`: przy stałej drabince odstępów `ease`
-- nie miałoby czytelnika, a powtórki i pomyłki wyliczają się z `card_reviews`.
CREATE TABLE IF NOT EXISTS cards (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    source_kind    TEXT NOT NULL,      -- 'error' | 'group'
    source_id      INTEGER NOT NULL,
    due_on         TEXT NOT NULL,      -- 'YYYY-MM-DD'
    interval_days  INTEGER NOT NULL,
    front_override TEXT,
    back_override  TEXT,
    front          TEXT,
    back           TEXT,
    shape          TEXT,
    shape_reason   TEXT,
    prepared_at    TEXT,
    UNIQUE (source_kind, source_id)
);

CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due_on);
CREATE INDEX IF NOT EXISTS idx_cards_prepared ON cards(prepared_at);

CREATE TABLE IF NOT EXISTS card_reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    grade      TEXT NOT NULL           -- 'known' | 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_card_reviews_card ON card_reviews(card_id, created_at);
CREATE INDEX IF NOT EXISTS idx_card_reviews_created ON card_reviews(created_at);
"""


# Aplikacja używa JEDNEGO połączenia sqlite3 (tworzonego w main.py), a synchroniczne
# endpointy FastAPI wykonują się w wielu wątkach threadpoola. Jedno połączenie nie jest
# bezpieczne wątkowo: równoległe wywołania gubią zapisy i rzucają "bad parameter or other
# API misuse". Dlatego KAŻDA publiczna funkcja tego modułu jest serializowana blokadą.
# Blokada obejmuje całe ciało funkcji (nie samo `execute`), bo kursor jest konsumowany
# przez `fetchall`/`fetchone` już po wykonaniu zapytania.
_LOCK = threading.RLock()


def _synchronized(fn):
    """Serializuje dostęp do współdzielonego połączenia (RLock — wywołania mogą się zagnieżdżać)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _LOCK:
            return fn(*args, **kwargs)
    return wrapper


# Znaczniki czasu zapisujemy w czasie LOKALNYM (z offsetem), bo dzienny cel i seria
# odnoszą się do dnia użytkownika — w UTC powtórki między 00:00 a 02:00 wpadałyby
# do poprzedniego dnia.
def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _today() -> str:
    return datetime.now().date().isoformat()


def get_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Zwraca połączenie z zainicjalizowanym schematem. `check_same_thread=False`
    w połączeniu z blokadą `_LOCK` (patrz `_synchronized`) daje bezpieczny dostęp
    z wielu wątków; WAL pozwala czytać bazę z innego procesu (np. skryptu importu)."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Lekkie migracje dla istniejących baz (dodawanie brakujących kolumn)."""
    usage_cols = {r["name"] for r in conn.execute("PRAGMA table_info(usage_events)")}
    if "est_input_tokens" not in usage_cols:
        conn.execute("ALTER TABLE usage_events ADD COLUMN est_input_tokens INTEGER NOT NULL DEFAULT 0")
    ex_cols = {r["name"] for r in conn.execute("PRAGMA table_info(exercises)")}
    if "served_at" not in ex_cols:
        # Kolejka zadań: zadania wygenerowane wsadowo czekają z served_at = NULL.
        conn.execute("ALTER TABLE exercises ADD COLUMN served_at TEXT")

    # Uzupełnienie zadań sprzed wprowadzenia kolejki: wszystkie były już pokazane,
    # więc muszą mieć served_at — inaczej wypadłyby ze statystyk i zostałyby wydane
    # po raz drugi jako „nowe". Sterujemy znacznikiem, a nie faktem dodania kolumny:
    # kolumna mogła powstać wcześniej, w wersji bez uzupełniania danych.
    done = conn.execute(
        "SELECT 1 FROM settings WHERE key = 'served_at_backfilled'"
    ).fetchone()
    if done is None:
        conn.execute("UPDATE exercises SET served_at = created_at WHERE served_at IS NULL")
        conn.execute("INSERT INTO settings (key, value) VALUES ('served_at_backfilled', '1')")

    err_cols = {r["name"] for r in conn.execute("PRAGMA table_info(errors)")}
    if "group_id" not in err_cols:
        # NULL = wpis nieprzypisany (przyszedł po ostatnim przebiegu grupowania).
        conn.execute("ALTER TABLE errors ADD COLUMN group_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_errors_group ON errors(group_id)")

    # Pięć kolumn treści karty. KOLUMNY wymagają tej ścieżki, w odróżnieniu od nowych
    # TABEL: `_SCHEMA` idzie przez executescript przy każdym połączeniu, więc
    # `CREATE TABLE IF NOT EXISTS` obsługuje istniejące bazy sam, ale `ALTER TABLE
    # ADD COLUMN` nie jest idempotentne i wywaliłby się przy drugim otwarciu.
    card_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
    for col in ("front", "back", "shape", "shape_reason", "prepared_at"):
        if col not in card_cols:
            conn.execute(f"ALTER TABLE cards ADD COLUMN {col} TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_prepared ON cards(prepared_at)")
    conn.commit()


# --- Exercises ---------------------------------------------------------------

def _row_to_exercise(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["prompt"] = json.loads(data.pop("prompt_json"))
    return data


@_synchronized
def insert_exercise(conn: sqlite3.Connection, *, type: str, topic: str, prompt: dict,
                    source: str = "in_app", served: bool = True) -> int:
    """Zapisuje zadanie. `served=False` odkłada je do kolejki (wygenerowane wsadowo,
    jeszcze nie pokazane) — takie zadania nie liczą się do statystyk nauki."""
    cur = conn.execute(
        "INSERT INTO exercises (created_at, type, topic, prompt_json, source, served_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), type, topic, json.dumps(prompt, ensure_ascii=False), source,
         _now() if served else None),
    )
    conn.commit()
    return int(cur.lastrowid)


@_synchronized
def get_exercise(conn: sqlite3.Connection, exercise_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    return _row_to_exercise(row) if row else None


@_synchronized
def take_queued_exercise(conn: sqlite3.Connection, *, type: str, topic: str) -> Optional[dict]:
    """Wyjmuje z kolejki najstarsze niewydane zadanie danego typu i tematu, oznaczając je
    jako wydane. Zwraca None, gdy kolejka dla tej pary jest pusta."""
    row = conn.execute(
        "SELECT * FROM exercises WHERE served_at IS NULL AND type = ? AND topic = ? "
        "ORDER BY id LIMIT 1",
        (type, topic),
    ).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE exercises SET served_at = ? WHERE id = ?", (_now(), row["id"]))
    conn.commit()
    return _row_to_exercise(row)


@_synchronized
def count_queued_exercises(conn: sqlite3.Connection) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) AS n FROM exercises WHERE served_at IS NULL"
    ).fetchone()["n"])


# --- Attempts ----------------------------------------------------------------

@_synchronized
def insert_attempt(conn: sqlite3.Connection, *, exercise_id: Optional[int], type: str,
                   student_answer: str, is_correct: Optional[bool], grading: dict) -> int:
    cur = conn.execute(
        "INSERT INTO attempts (exercise_id, created_at, type, student_answer, is_correct, grading_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            exercise_id,
            _now(),
            type,
            student_answer,
            None if is_correct is None else int(is_correct),
            json.dumps(grading, ensure_ascii=False),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


# --- Errors ------------------------------------------------------------------

@_synchronized
def insert_error(conn: sqlite3.Connection, *, source: str, exercise_type: str, topic: str,
                 student_text: str, correct_text: str, explanation: str,
                 severity: str = "minor", created_at: Optional[str] = None) -> int:
    cur = conn.execute(
        "INSERT INTO errors (created_at, source, exercise_type, topic, student_text, "
        "correct_text, explanation, severity) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (created_at or _now(), source, exercise_type, topic, student_text,
         correct_text, explanation, severity),
    )
    conn.commit()
    return int(cur.lastrowid)


@_synchronized
def delete_errors_by_source(conn: sqlite3.Connection, source: str) -> int:
    """Usuwa wszystkie błędy o danym źródle. Zwraca liczbę usuniętych wierszy.
    Używane do idempotentnego importu strategią 'zastąp' (source = 'import:<plik>')."""
    cur = conn.execute("DELETE FROM errors WHERE source = ?", (source,))
    conn.commit()
    return cur.rowcount


@_synchronized
def list_errors(conn: sqlite3.Connection, *, topic: Optional[str] = None,
                exercise_type: Optional[str] = None, limit: int = 2000) -> list[dict]:
    query = "SELECT * FROM errors"
    clauses, params = [], []
    if topic:
        clauses.append("topic = ?")
        params.append(topic)
    if exercise_type:
        clauses.append("exercise_type = ?")
        params.append(exercise_type)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(query, params).fetchall()]


@_synchronized
def get_error(conn: sqlite3.Connection, error_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM errors WHERE id = ?", (error_id,)).fetchone()
    return dict(row) if row else None


# --- Settings (klucz-wartość) ------------------------------------------------

@_synchronized
def get_setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


@_synchronized
def get_int_setting(conn: sqlite3.Connection, key: str, default: int) -> int:
    """Jak `get_setting`, ale odporne na nieliczbową wartość w bazie (zwraca default)."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    try:
        return int(row["value"]) if row else default
    except (TypeError, ValueError):
        return default


@_synchronized
def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


# --- Reviews (dziennik powtórek do dziennego celu) ---------------------------

@_synchronized
def reviewed_today(conn: sqlite3.Connection, error_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM reviews WHERE error_id = ? AND substr(created_at, 1, 10) = ? LIMIT 1",
        (error_id, _today()),
    ).fetchone()
    return row is not None


@_synchronized
def insert_review(conn: sqlite3.Connection, error_id: int) -> None:
    """Zapisuje przerobienie błędu. Idempotentne w obrębie dnia (jeden wpis na błąd/dzień)."""
    if reviewed_today(conn, error_id):
        return
    conn.execute("INSERT INTO reviews (error_id, created_at) VALUES (?, ?)", (error_id, _now()))
    conn.commit()


@_synchronized
def insert_drill_score(conn: sqlite3.Connection, *, error_id: int,
                       correct_items: int, total_items: int) -> None:
    """Zapisuje wynik jednego zestawu ćwiczeń do danego błędu (zakładka „Ćwicz błędy")."""
    conn.execute(
        "INSERT INTO drill_scores (error_id, created_at, correct_items, total_items) "
        "VALUES (?, ?, ?, ?)",
        (error_id, _now(), max(0, int(correct_items)), max(0, int(total_items))),
    )
    conn.commit()


@_synchronized
def drill_correct_today(conn: sqlite3.Connection, error_id: int) -> int:
    """Liczba poprawnych ćwiczeń do danego błędu uzbierana DZISIAJ (narastająco)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(correct_items), 0) AS n FROM drill_scores "
        "WHERE error_id = ? AND substr(created_at, 1, 10) = ?",
        (error_id, _today()),
    ).fetchone()
    return int(row["n"])


@_synchronized
def reviews_done_today(conn: sqlite3.Connection) -> int:
    """Ile różnych jednostek przerobiono dziś — wpisów ORAZ grup.

    Grupa liczy się jak jeden błąd, więc oba źródła po prostu się sumują."""
    row = conn.execute(
        "SELECT (SELECT COUNT(DISTINCT error_id) FROM reviews "
        "        WHERE substr(created_at, 1, 10) = ?) "
        "     + (SELECT COUNT(DISTINCT group_id) FROM group_reviews "
        "        WHERE substr(created_at, 1, 10) = ?) AS n",
        (_today(), _today()),
    ).fetchone()
    return int(row["n"])


@_synchronized
def insert_dispute(conn: sqlite3.Connection, *, scope: str, disputed_text: str,
                   user_comment: str = "", exercise_id: Optional[int] = None,
                   item_number: Optional[int] = None, error_id: Optional[int] = None,
                   verdict: Optional[str] = None, revised_text: Optional[str] = None,
                   student_was_right: bool = False) -> int:
    cur = conn.execute(
        "INSERT INTO disputes (created_at, scope, exercise_id, item_number, error_id, "
        "disputed_text, user_comment, verdict, revised_text, student_was_right) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (_now(), scope, exercise_id, item_number, error_id, disputed_text, user_comment,
         verdict, revised_text, int(student_was_right)),
    )
    conn.commit()
    return int(cur.lastrowid)


@_synchronized
def get_dispute(conn: sqlite3.Connection, dispute_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM disputes WHERE id = ?", (dispute_id,)).fetchone()
    return dict(row) if row else None


@_synchronized
def mark_dispute_applied(conn: sqlite3.Connection, dispute_id: int) -> None:
    conn.execute("UPDATE disputes SET applied_at = ? WHERE id = ?", (_now(), dispute_id))
    conn.commit()


@_synchronized
def delete_error(conn: sqlite3.Connection, error_id: int) -> bool:
    # Karta jest widokiem na ten wpis — bez źródła nie ma czego pokazać. Sprzątamy
    # ręcznie, bo PRAGMA foreign_keys jest wyłączone i kaskada deklaratywna nic by nie dała.
    conn.execute("DELETE FROM card_reviews WHERE card_id IN ("
                 "  SELECT id FROM cards WHERE source_kind = 'error' AND source_id = ?)",
                 (error_id,))
    conn.execute("DELETE FROM cards WHERE source_kind = 'error' AND source_id = ?", (error_id,))
    cur = conn.execute("DELETE FROM errors WHERE id = ?", (error_id,))
    conn.commit()
    return cur.rowcount > 0


@_synchronized
def latest_attempt_for_exercise(conn: sqlite3.Connection, exercise_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM attempts WHERE exercise_id = ? ORDER BY id DESC LIMIT 1", (exercise_id,)
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["grading"] = json.loads(data.pop("grading_json"))
    return data


@_synchronized
def update_attempt_grading(conn: sqlite3.Connection, attempt_id: int, *,
                           grading: dict, is_correct: Optional[bool]) -> None:
    conn.execute(
        "UPDATE attempts SET grading_json = ?, is_correct = ? WHERE id = ?",
        (json.dumps(grading, ensure_ascii=False),
         None if is_correct is None else int(is_correct), attempt_id),
    )
    conn.commit()


@_synchronized
def dispute_stats(conn: sqlite3.Connection) -> dict:
    """Ile zastrzeżeń zgłoszono i w ilu model przyznał rację (sygnał jakości ocen)."""
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN verdict = 'upheld' THEN 1 ELSE 0 END), 0) AS upheld, "
        "COALESCE(SUM(CASE WHEN applied_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS applied "
        "FROM disputes"
    ).fetchone()
    return dict(row)


@_synchronized
def reviews_per_day(conn: sqlite3.Connection) -> dict[str, int]:
    """Mapa 'YYYY-MM-DD' -> liczba różnych jednostek przerobionych tego dnia.

    Sumuje wpisy i grupy. Materiał dla `streak.state()` — sama reguła serii siedzi
    w `app/streak.py` i nie wie nic o tym podziale."""
    rows = conn.execute(
        "SELECT day, SUM(n) AS n FROM ("
        "  SELECT substr(created_at, 1, 10) AS day, COUNT(DISTINCT error_id) AS n "
        "  FROM reviews GROUP BY day "
        "  UNION ALL "
        "  SELECT substr(created_at, 1, 10) AS day, COUNT(DISTINCT group_id) AS n "
        "  FROM group_reviews GROUP BY day"
        ") GROUP BY day"
    ).fetchall()
    return {r["day"]: int(r["n"]) for r in rows}


@_synchronized
def topic_error_counts(conn: sqlite3.Connection) -> list[dict]:
    """Zagregowana liczba błędów na temat + data ostatniego wystąpienia (do statystyk i SRS)."""
    rows = conn.execute(
        "SELECT topic, COUNT(*) AS count, MAX(created_at) AS last_seen "
        "FROM errors GROUP BY topic ORDER BY count DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# --- Statystyki użycia Claude (tokeny / koszt) -------------------------------

@_synchronized
def insert_usage_event(conn: sqlite3.Connection, *, kind: str, model: str,
                       input_tokens: int, output_tokens: int,
                       cache_creation_input_tokens: int, cache_read_input_tokens: int,
                       cost_usd: float, duration_ms: int, est_input_tokens: int = 0) -> None:
    conn.execute(
        "INSERT INTO usage_events (created_at, kind, model, input_tokens, output_tokens, "
        "cache_creation_input_tokens, cache_read_input_tokens, est_input_tokens, cost_usd, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (_now(), kind, model, input_tokens, output_tokens,
         cache_creation_input_tokens, cache_read_input_tokens, est_input_tokens, cost_usd, duration_ms),
    )
    conn.commit()


@_synchronized
def usage_stats(conn: sqlite3.Connection) -> dict:
    """Sumaryczne zużycie Claude: tokeny, koszt (wg stawek API), podział wg rodzaju i dnia."""
    total = conn.execute(
        "SELECT COUNT(*) AS calls, "
        "COALESCE(SUM(input_tokens),0) AS input_tokens, "
        "COALESCE(SUM(output_tokens),0) AS output_tokens, "
        "COALESCE(SUM(cache_creation_input_tokens),0) AS cache_creation_input_tokens, "
        "COALESCE(SUM(cache_read_input_tokens),0) AS cache_read_input_tokens, "
        "COALESCE(SUM(est_input_tokens),0) AS est_input_tokens, "
        "COALESCE(SUM(cost_usd),0) AS cost_usd, "
        "COALESCE(AVG(duration_ms),0) AS avg_duration_ms FROM usage_events"
    ).fetchone()
    by_kind = conn.execute(
        "SELECT kind, COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens, "
        "COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(cost_usd),0) AS cost_usd "
        "FROM usage_events GROUP BY kind ORDER BY cost_usd DESC"
    ).fetchall()
    by_model = conn.execute(
        "SELECT model, COUNT(*) AS calls, "
        "COALESCE(SUM(est_input_tokens),0) AS est_input_tokens, "
        "COALESCE(SUM(output_tokens),0) AS output_tokens "
        "FROM usage_events GROUP BY model"
    ).fetchall()
    by_day = conn.execute(
        "SELECT substr(created_at,1,10) AS day, COUNT(*) AS calls, "
        "COALESCE(SUM(cost_usd),0) AS cost_usd FROM usage_events "
        "GROUP BY day ORDER BY day DESC LIMIT 30"
    ).fetchall()
    return {"total": dict(total), "by_kind": [dict(r) for r in by_kind],
            "by_model": [dict(r) for r in by_model], "by_day": [dict(r) for r in by_day]}


# --- Statystyki nauki --------------------------------------------------------

@_synchronized
def learning_stats(conn: sqlite3.Connection) -> dict:
    """Statystyki korzystania/nauki: ćwiczenia, skuteczność, powtórki, aktywność dzienna."""
    # Liczymy tylko zadania faktycznie pokazane — te czekające w kolejce jeszcze się nie liczą.
    ex_generated = conn.execute(
        "SELECT COUNT(*) AS n FROM exercises WHERE served_at IS NOT NULL"
    ).fetchone()["n"]
    ex_queued = conn.execute(
        "SELECT COUNT(*) AS n FROM exercises WHERE served_at IS NULL"
    ).fetchone()["n"]
    att = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN is_correct IS NOT NULL THEN 1 ELSE 0 END),0) AS graded, "
        "COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END),0) AS correct FROM attempts"
    ).fetchone()
    by_type = conn.execute(
        "SELECT type, COUNT(*) AS attempts, "
        "COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END),0) AS correct "
        "FROM attempts GROUP BY type ORDER BY attempts DESC"
    ).fetchall()
    by_day = conn.execute(
        "SELECT substr(created_at,1,10) AS day, COUNT(*) AS attempts FROM attempts "
        "GROUP BY day ORDER BY day DESC LIMIT 30"
    ).fetchall()
    reviews_total = conn.execute("SELECT COUNT(*) AS n FROM reviews").fetchone()["n"]
    errors_logged = conn.execute("SELECT COUNT(*) AS n FROM errors").fetchone()["n"]
    graded = int(att["graded"])
    correct = int(att["correct"])
    return {
        "exercises_generated": int(ex_generated),
        "exercises_queued": int(ex_queued),
        "attempts_total": int(att["total"]),
        "attempts_graded": graded,
        "attempts_correct": correct,
        "accuracy": (correct / graded) if graded else None,
        "by_type": [dict(r) for r in by_type],
        "by_day": [dict(r) for r in by_day],
        "reviews_total": int(reviews_total),
        "errors_logged": int(errors_logged),
    }


# --- Grupy błędów -------------------------------------------------------------

@_synchronized
def insert_group(conn: sqlite3.Connection, *, rule: str, explanation: str, topic: str) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO error_groups (created_at, updated_at, rule, explanation, topic) "
        "VALUES (?, ?, ?, ?, ?)",
        (now, now, rule, explanation, topic),
    )
    conn.commit()
    return int(cur.lastrowid)


@_synchronized
def get_group(conn: sqlite3.Connection, group_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM error_groups WHERE id = ?", (group_id,)).fetchone()
    return dict(row) if row else None


@_synchronized
def list_groups(conn: sqlite3.Connection) -> list[dict]:
    """Grupy z licznikiem wpisów. Pusta grupa (`member_count = 0`) też jest zwracana —
    zostaje w widoku, dopóki uczeń sam jej nie usunie."""
    rows = conn.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM errors e WHERE e.group_id = g.id) AS member_count "
        "FROM error_groups g ORDER BY g.updated_at DESC, g.id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@_synchronized
def update_group(conn: sqlite3.Connection, group_id: int, *, rule: str, explanation: str) -> bool:
    cur = conn.execute(
        "UPDATE error_groups SET rule = ?, explanation = ?, updated_at = ? WHERE id = ?",
        (rule, explanation, _now(), group_id),
    )
    conn.commit()
    return cur.rowcount > 0


@_synchronized
def delete_group(conn: sqlite3.Connection, group_id: int) -> bool:
    """Usuwa grupę; jej wpisy wracają do puli nieprzypisanych. Zaliczenia w
    `group_reviews` zostają — usunięcie nie cofa zdobytego celu ani serii.
    Karta grupy znika razem z grupą: jest widokiem na nią, nie bytem obok niej."""
    conn.execute("DELETE FROM card_reviews WHERE card_id IN ("
                 "  SELECT id FROM cards WHERE source_kind = 'group' AND source_id = ?)",
                 (group_id,))
    conn.execute("DELETE FROM cards WHERE source_kind = 'group' AND source_id = ?", (group_id,))
    conn.execute("UPDATE errors SET group_id = NULL WHERE group_id = ?", (group_id,))
    cur = conn.execute("DELETE FROM error_groups WHERE id = ?", (group_id,))
    conn.commit()
    return cur.rowcount > 0


@_synchronized
def set_error_group(conn: sqlite3.Connection, error_id: int, group_id: Optional[int]) -> bool:
    cur = conn.execute("UPDATE errors SET group_id = ? WHERE id = ?", (group_id, error_id))
    conn.commit()
    return cur.rowcount > 0


@_synchronized
def group_of_error(conn: sqlite3.Connection, error_id: int) -> Optional[int]:
    row = conn.execute("SELECT group_id FROM errors WHERE id = ?", (error_id,)).fetchone()
    if row is None or row["group_id"] is None:
        return None
    return int(row["group_id"])


@_synchronized
def group_member_count(conn: sqlite3.Connection, group_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM errors WHERE group_id = ?", (group_id,)
    ).fetchone()
    return int(row["n"])


@_synchronized
def list_group_members(conn: sqlite3.Connection, group_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM errors WHERE group_id = ? ORDER BY created_at DESC, id DESC",
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@_synchronized
def list_ungrouped_errors(conn: sqlite3.Connection, limit: int = 2000) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM errors WHERE group_id IS NULL ORDER BY id LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


@_synchronized
def count_ungrouped_errors(conn: sqlite3.Connection) -> int:
    """Sama LICZBA nieprzypisanych wpisów. Widok grup potrzebuje liczby, nie rekordów,
    a `list_ungrouped_errors` ściągnęłoby dla niej do 2000 wierszy."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM errors WHERE group_id IS NULL"
    ).fetchone()
    return int(row["n"])


@_synchronized
def clear_all_groups(conn: sqlite3.Connection) -> None:
    """Czyści grupy i przypisania przed pełnym przegrupowaniem. Zaliczenia zostają."""
    conn.execute("UPDATE errors SET group_id = NULL")
    conn.execute("DELETE FROM error_groups")
    conn.commit()


@_synchronized
def group_reviewed_today(conn: sqlite3.Connection, group_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM group_reviews WHERE group_id = ? AND substr(created_at, 1, 10) = ?",
        (group_id, _today()),
    ).fetchone()
    return row is not None


@_synchronized
def insert_group_review(conn: sqlite3.Connection, group_id: int) -> None:
    """Idempotentne w obrębie dnia — dokładnie jak `insert_review` dla pojedynczego błędu."""
    if group_reviewed_today(conn, group_id):
        return
    conn.execute("INSERT INTO group_reviews (group_id, created_at) VALUES (?, ?)",
                 (group_id, _now()))
    conn.commit()


@_synchronized
def insert_group_drill_score(conn: sqlite3.Connection, *, group_id: int,
                             correct_items: int, total_items: int) -> None:
    conn.execute(
        "INSERT INTO group_drill_scores (group_id, created_at, correct_items, total_items) "
        "VALUES (?, ?, ?, ?)",
        (group_id, _now(), correct_items, total_items),
    )
    conn.commit()


@_synchronized
def group_drill_correct_today(conn: sqlite3.Connection, group_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(correct_items), 0) AS n FROM group_drill_scores "
        "WHERE group_id = ? AND substr(created_at, 1, 10) = ?",
        (group_id, _today()),
    ).fetchone()
    return int(row["n"])


@_synchronized
def group_topic_counts(conn: sqlite3.Connection) -> list[dict]:
    """Materiał dla `srs.choose_topic` w trybie grupowym: ile grup na temat i jak świeże.

    `last_seen` to data NAJNOWSZEGO WPISU w grupach tego tematu, a nie `updated_at`
    samej grupy: po przegrupowaniu wszystkie grupy mają ten sam znacznik i świeżość
    spłaszczyłaby się do stałej dokładnie wtedy, gdy ma najwięcej do powiedzenia.
    Temat złożony z samych pustych grup ma `last_seen` NULL — `srs` traktuje go
    wtedy jak najstarszy, czyli bez premii za świeżość."""
    rows = conn.execute(
        "SELECT g.topic AS topic, COUNT(*) AS count, "
        "       MAX((SELECT MAX(e.created_at) FROM errors e WHERE e.group_id = g.id)) "
        "         AS last_seen "
        "FROM error_groups g GROUP BY g.topic ORDER BY count DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# --- Fiszki -------------------------------------------------------------------

@_synchronized
def create_card(conn: sqlite3.Connection, *, source_kind: str, source_id: int,
                due_on: str, interval_days: int) -> int:
    now = _now()
    cur = conn.execute(
        "INSERT INTO cards (created_at, updated_at, source_kind, source_id, due_on, interval_days) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (now, now, source_kind, source_id, due_on, interval_days),
    )
    conn.commit()
    return int(cur.lastrowid)


@_synchronized
def get_card(conn: sqlite3.Connection, card_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    return dict(row) if row else None


@_synchronized
def get_card_by_source(conn: sqlite3.Connection, source_kind: str,
                       source_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM cards WHERE source_kind = ? AND source_id = ?",
        (source_kind, source_id),
    ).fetchone()
    return dict(row) if row else None


@_synchronized
def update_card_schedule(conn: sqlite3.Connection, card_id: int, *,
                         due_on: str, interval_days: int) -> bool:
    cur = conn.execute(
        "UPDATE cards SET due_on = ?, interval_days = ?, updated_at = ? WHERE id = ?",
        (due_on, interval_days, _now(), card_id),
    )
    conn.commit()
    return cur.rowcount > 0


@_synchronized
def set_card_override(conn: sqlite3.Connection, card_id: int, *,
                      front: str, back: str) -> bool:
    """Zapisuje treść ulepszoną przez model. Od tej chwili front i rewers biorą się
    z zapisanego tekstu zamiast z renderowania ze źródła."""
    cur = conn.execute(
        "UPDATE cards SET front_override = ?, back_override = ?, updated_at = ? WHERE id = ?",
        (front, back, _now(), card_id),
    )
    conn.commit()
    return cur.rowcount > 0


@_synchronized
def set_card_content(conn: sqlite3.Connection, card_id: int, *, front: str, back: str,
                     shape: str, shape_reason: str) -> bool:
    """Zapisuje wygenerowaną treść i oznacza kartę jako przygotowaną.

    NIE dotyka `due_on` ani `interval_days`: przeprojektowanie treści zmienia to,
    co uczeń widzi, nie to, kiedy to widzi."""
    now = _now()
    cur = conn.execute(
        "UPDATE cards SET front = ?, back = ?, shape = ?, shape_reason = ?, "
        "prepared_at = ?, updated_at = ? WHERE id = ?",
        (front, back, shape, shape_reason, now, now, card_id),
    )
    conn.commit()
    return cur.rowcount > 0


_UNPREPARED_SQL = (
    "SELECT c.id AS card_id, c.source_kind, c.source_id, "
    "       COALESCE(e.topic, g.topic) AS topic, "
    "       COALESCE(e.student_text, '') AS student_text, "
    "       COALESCE(e.correct_text, g.rule) AS correct_text, "
    "       COALESCE(e.explanation, g.explanation) AS explanation "
    "FROM cards c "
    "LEFT JOIN errors e ON c.source_kind = 'error' AND e.id = c.source_id "
    "LEFT JOIN error_groups g ON c.source_kind = 'group' AND g.id = c.source_id "
    "WHERE c.prepared_at IS NULL AND COALESCE(e.id, g.id) IS NOT NULL"
)


@_synchronized
def cards_unprepared(conn: sqlite3.Connection, limit: int = 500) -> list[dict]:
    """Karty czekające na treść, wraz z polami źródła potrzebnymi do jej ułożenia.

    Warunek `COALESCE(e.id, g.id) IS NOT NULL` pomija karty osierocone — źródło mogło
    zniknąć — żeby nie wysyłać modelowi pozycji bez treści do pracy.

    `student_text` grupy jest PUSTY, nie równy regule. Grupa nie ma formy błędnej: jej
    materiałem jest reguła i wyjaśnienie. Gdyby reguła wyciekła tu jako `student_text`,
    prompt zakazałby modelowi użycia jedynej sensownej treści, jaką grupa niesie."""
    rows = conn.execute(f"{_UNPREPARED_SQL} ORDER BY c.id LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@_synchronized
def count_unprepared(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM ({_UNPREPARED_SQL})"
    ).fetchone()
    return int(row["n"])


@_synchronized
def cards_new(conn: sqlite3.Connection, today: str,
              topic: Optional[str] = None) -> list[dict]:
    """Karty przygotowane, których uczeń nie widział ani razu.

    `today` nie filtruje nowych kart — przyjmujemy go dla symetrii z `cards_due`
    i żeby wywołujący nie musiał pamiętać, która z dwóch funkcji go potrzebuje."""
    sql = (
        "SELECT c.*, c.id AS card_id, COALESCE(e.topic, g.topic) AS topic "
        "FROM cards c "
        "LEFT JOIN errors e ON c.source_kind = 'error' AND e.id = c.source_id "
        "LEFT JOIN error_groups g ON c.source_kind = 'group' AND g.id = c.source_id "
        "WHERE c.prepared_at IS NOT NULL "
        "  AND NOT EXISTS (SELECT 1 FROM card_reviews r WHERE r.card_id = c.id)"
    )
    params: list = []
    if topic:
        sql += " AND COALESCE(e.topic, g.topic) = ?"
        params.append(topic)
    sql += " ORDER BY c.id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


@_synchronized
def insert_card_review(conn: sqlite3.Connection, *, card_id: int, grade: str) -> None:
    """Log ocen. NIE jest idempotentny w obrębie dnia — w sesji ta sama karta może
    wrócić, a każde podejście ma zostać zapisane."""
    conn.execute("INSERT INTO card_reviews (card_id, created_at, grade) VALUES (?, ?, ?)",
                 (card_id, _now(), grade))
    conn.commit()


@_synchronized
def card_unknown_count(conn: sqlite3.Connection, card_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM card_reviews WHERE card_id = ? AND grade = 'unknown'",
        (card_id,),
    ).fetchone()
    return int(row["n"])


@_synchronized
def cards_due(conn: sqlite3.Connection, today: str,
              topic: Optional[str] = None) -> list[dict]:
    """Karty zaplanowane na dziś lub wcześniej, z tematem ze źródła.

    Temat karty to temat jej źródła, dlatego zapytanie łączy się z obiema tabelami
    źródłowymi — wpis w dzienniku ma temat w `errors.topic`, grupa w `error_groups.topic`.

    Zwraca tylko karty PRZYGOTOWANE (mają już treść) i już OCENIONE choć raz —
    karta bez oceny jest „nowa" i należy do `cards_new`, nie do tej kolejki."""
    # `c.id AS card_id`, bo `flashcards.build_queue` czyta właśnie ten klucz —
    # gołe `c.*` dałoby kolumnę `id` i wysypało składanie kolejki na KeyError.
    sql = (
        "SELECT c.*, c.id AS card_id, COALESCE(e.topic, g.topic) AS topic "
        "FROM cards c "
        "LEFT JOIN errors e ON c.source_kind = 'error' AND e.id = c.source_id "
        "LEFT JOIN error_groups g ON c.source_kind = 'group' AND g.id = c.source_id "
        "WHERE c.due_on <= ? AND c.prepared_at IS NOT NULL "
        "  AND EXISTS (SELECT 1 FROM card_reviews r WHERE r.card_id = c.id)"
    )
    params: list = [today]
    if topic:
        sql += " AND COALESCE(e.topic, g.topic) = ?"
        params.append(topic)
    sql += " ORDER BY c.due_on, c.id"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


@_synchronized
def sources_without_card(conn: sqlite3.Connection, topic: Optional[str] = None,
                         limit: int = 500) -> list[dict]:
    """Źródła, które nie mają jeszcze karty — kandydaci na nowe pozycje w kolejce."""
    err_sql = (
        "SELECT 'error' AS source_kind, e.id AS source_id, e.topic AS topic, e.created_at "
        "FROM errors e WHERE NOT EXISTS ("
        "  SELECT 1 FROM cards c WHERE c.source_kind = 'error' AND c.source_id = e.id)"
    )
    grp_sql = (
        "SELECT 'group' AS source_kind, g.id AS source_id, g.topic AS topic, g.created_at "
        "FROM error_groups g WHERE NOT EXISTS ("
        "  SELECT 1 FROM cards c WHERE c.source_kind = 'group' AND c.source_id = g.id)"
    )
    params: list = []
    if topic:
        err_sql += " AND e.topic = ?"
        grp_sql += " AND g.topic = ?"
        params = [topic, topic]
    sql = f"{err_sql} UNION ALL {grp_sql} ORDER BY created_at, source_id LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


@_synchronized
def cards_done_today(conn: sqlite3.Connection) -> int:
    """Ile RÓŻNYCH kart przerobiono dziś. Osobny licznik — seria 🔥 go nie widzi."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT card_id) AS n FROM card_reviews "
        "WHERE substr(created_at, 1, 10) = ?",
        (_today(),),
    ).fetchone()
    return int(row["n"])


@_synchronized
def cards_overdue(conn: sqlite3.Connection, today: str) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM cards WHERE due_on < ?", (today,)).fetchone()
    return int(row["n"])


@_synchronized
def count_card_sources(conn: sqlite3.Connection) -> int:
    """Ile jest w ogóle źródeł, z których da się zrobić fiszkę (wpisy + grupy).

    Pozwala odróżnić „wszystko na dziś zrobione" od „nie ma z czego robić fiszek" —
    milczący pusty ekran nie rozróżnia tych dwóch rzeczy."""
    row = conn.execute(
        "SELECT (SELECT COUNT(*) FROM errors) + (SELECT COUNT(*) FROM error_groups) AS n"
    ).fetchone()
    return int(row["n"])
