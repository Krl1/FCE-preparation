"""Warstwa trwałości (SQLite) — dziennik błędów, zadania i podejścia.

Dziennik błędów (`errors`) jest sercem aplikacji: steruje doborem kolejnych zadań
(przez `srs.py`) i zasila widok „Moje błędy".
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
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
    source      TEXT NOT NULL DEFAULT 'in_app'
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
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Zwraca połączenie z zainicjalizowanym schematem. `check_same_thread=False`
    dla współpracy z serwerem ASGI (dostęp serializowany na poziomie zapytań)."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# --- Exercises ---------------------------------------------------------------

def insert_exercise(conn: sqlite3.Connection, *, type: str, topic: str,
                    prompt: dict, source: str = "in_app") -> int:
    cur = conn.execute(
        "INSERT INTO exercises (created_at, type, topic, prompt_json, source) VALUES (?, ?, ?, ?, ?)",
        (_now(), type, topic, json.dumps(prompt, ensure_ascii=False), source),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_exercise(conn: sqlite3.Connection, exercise_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["prompt"] = json.loads(data.pop("prompt_json"))
    return data


# --- Attempts ----------------------------------------------------------------

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


def delete_errors_by_source(conn: sqlite3.Connection, source: str) -> int:
    """Usuwa wszystkie błędy o danym źródle. Zwraca liczbę usuniętych wierszy.
    Używane do idempotentnego importu strategią 'zastąp' (source = 'import:<plik>')."""
    cur = conn.execute("DELETE FROM errors WHERE source = ?", (source,))
    conn.commit()
    return cur.rowcount


def list_errors(conn: sqlite3.Connection, *, topic: Optional[str] = None,
                exercise_type: Optional[str] = None, limit: int = 200) -> list[dict]:
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


def get_error(conn: sqlite3.Connection, error_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM errors WHERE id = ?", (error_id,)).fetchone()
    return dict(row) if row else None


# --- Settings (klucz-wartość) ------------------------------------------------

def get_setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


# --- Reviews (dziennik powtórek do dziennego celu) ---------------------------

def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def reviewed_today(conn: sqlite3.Connection, error_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM reviews WHERE error_id = ? AND substr(created_at, 1, 10) = ? LIMIT 1",
        (error_id, _today()),
    ).fetchone()
    return row is not None


def insert_review(conn: sqlite3.Connection, error_id: int) -> None:
    """Zapisuje przerobienie błędu. Idempotentne w obrębie dnia (jeden wpis na błąd/dzień)."""
    if reviewed_today(conn, error_id):
        return
    conn.execute("INSERT INTO reviews (error_id, created_at) VALUES (?, ?)", (error_id, _now()))
    conn.commit()


def reviews_done_today(conn: sqlite3.Connection) -> int:
    """Liczba różnych błędów przerobionych dzisiaj (postęp dziennego celu)."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT error_id) AS n FROM reviews WHERE substr(created_at, 1, 10) = ?",
        (_today(),),
    ).fetchone()
    return int(row["n"])


def topic_error_counts(conn: sqlite3.Connection) -> list[dict]:
    """Zagregowana liczba błędów na temat + data ostatniego wystąpienia (do statystyk i SRS)."""
    rows = conn.execute(
        "SELECT topic, COUNT(*) AS count, MAX(created_at) AS last_seen "
        "FROM errors GROUP BY topic ORDER BY count DESC"
    ).fetchall()
    return [dict(r) for r in rows]
