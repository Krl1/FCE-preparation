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
from datetime import datetime, timedelta
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
    """Liczba różnych błędów przerobionych dzisiaj (postęp dziennego celu)."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT error_id) AS n FROM reviews WHERE substr(created_at, 1, 10) = ?",
        (_today(),),
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


def _reviews_per_day(conn: sqlite3.Connection) -> dict[str, int]:
    """Mapa 'YYYY-MM-DD' -> liczba różnych błędów przerobionych tego dnia."""
    rows = conn.execute(
        "SELECT substr(created_at, 1, 10) AS day, COUNT(DISTINCT error_id) AS n "
        "FROM reviews GROUP BY day"
    ).fetchall()
    return {r["day"]: int(r["n"]) for r in rows}


@_synchronized
def streak(conn: sqlite3.Connection, goal: int) -> int:
    """Liczba kolejnych dni z osiągniętym celem, kończących się dziś lub wczoraj.

    Dzień jest 'zaliczony', gdy liczba różnych przerobionych błędów >= `goal`.
    Jeśli dzisiejszy cel nie jest jeszcze osiągnięty, seria nie pęka od razu —
    liczymy ciąg kończący się wczoraj (grace do końca dnia)."""
    if goal <= 0:
        return 0
    per_day = _reviews_per_day(conn)
    today = datetime.now().date()
    day = today
    if per_day.get(today.isoformat(), 0) < goal:
        day = today - timedelta(days=1)  # dzisiaj jeszcze nie zrobione → licz od wczoraj
    count = 0
    while per_day.get(day.isoformat(), 0) >= goal:
        count += 1
        day = day - timedelta(days=1)
    return count


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
