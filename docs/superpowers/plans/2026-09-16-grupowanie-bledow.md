# Grupowanie błędów — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać okresowe scalanie wpisów z dziennika błędów w grupy odpowiadające regułom oraz drugi tryb ćwiczeń, w którym trenuje się grupy zamiast pojedynczych błędów.

**Architecture:** Nowa tabela `error_groups` i nullowalna kolumna `errors.group_id` (jeden błąd → co najwyżej jedna grupa). Przypisania liczy model w jednym wywołaniu na porcję, a jego odpowiedź waliduje czysty moduł `app/grouping.py` (bez bazy i bez LLM), zwracając plan przypisań, który warstwa bazy wykonuje bez dalszych decyzji. Zaliczenia grup idą do osobnych tabel `group_reviews` / `group_drill_scores`, więc `reviews`, `drill_scores` i `app/streak.py` pozostają nietknięte.

**Tech Stack:** Python 3.12, FastAPI, SQLite (WAL), pytest, statyczny frontend (HTML/JS/CSS bez frameworków), smoke test frontendu w Node.

**Spec:** `docs/superpowers/specs/2026-09-16-grupowanie-bledow-design.md`

## Global Constraints

- Jeden błąd należy do **co najwyżej jednej** grupy (`errors.group_id`, `NULL` = nieprzypisany).
- Migracja jest **addytywna**: trzy nowe tabele i jedna kolumna. Żadnego przepisywania istniejących danych, żadnej przebudowy tabel.
- `reviews`, `drill_scores` i `app/streak.py` **nie są modyfikowane**. Zaliczenia grup trafiają do `group_reviews` i `group_drill_scores`.
- Przerobiona grupa daje **+1** do dziennego celu, tak samo jak pojedynczy wpis, po uzbieraniu `DRILL_CORRECT_TARGET` poprawnych ćwiczeń w danym dniu. `DRILL_CORRECT_TARGET` jest pochodną `llm_client.ITEMS_PER_EXERCISE` — nigdy nie wpisuj literału `5`.
- **Pusta grupa zostaje.** Nic nie znika samo. Usunięcie grupy jest zawsze decyzją ucznia.
- Serwer **nie ufa odpowiedzi modelu**: wymyślone `group_id` → wpis nieprzypisany; wpis pominięty → nieprzypisany; duplikaty nowych grup → scalane po znormalizowanej regule; `topic` spoza taksonomii → `tax.normalize_topic`.
- `tax.normalize_topic` jest **wrażliwe na wielkość liter i nie przycina spacji** (`'Prepositions '` → `'language'`). Zawsze podawaj `topic.strip().lower()`.
- Nowe klucze i18n trafiają do **obu** bloków w `static/app.js` (`pl` i `en`).
- Wszystkie funkcje w `app/db.py` mutujące stan są dekorowane `@_synchronized`.

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `app/grouping.py` (nowy) | czysta walidacja odpowiedzi modelu → plan przypisań; porcjowanie |
| `app/db.py` (modyfikacja) | schemat, migracja, CRUD grup, zaliczenia grup, sumowanie dwóch źródeł |
| `app/llm_client.py` (modyfikacja) | `group_errors()`; opcjonalne konteksty w `generate_drill()` |
| `app/models.py` (modyfikacja) | modele żądań dla grup i trybu grupowego |
| `app/main.py` (modyfikacja) | endpointy grup, dobór grupy do ćwiczenia, tryb w `tips` |
| `static/index.html` (modyfikacja) | przełączniki i kontenery widoku grup |
| `static/app.js` (modyfikacja) | render grup, akcje, tryb ćwiczeń, i18n |
| `static/style.css` (modyfikacja) | style listy grup |
| `tests/test_grouping.py` (nowy) | tabelka wejście-wyjście dla czystego modułu |
| `tests/test_db.py` (modyfikacja) | CRUD grup, cykl życia, sumowanie zaliczeń |
| `tests/test_api.py` (modyfikacja) | endpointy z podstawionym modelem |
| `tests/smoke_frontend.js` (modyfikacja) | przejście nowych przełączników |

---

### Task 1: Czysty moduł walidacji (`app/grouping.py`)

Najbardziej podatna na błędy część, więc idzie pierwsza i bez żadnych zależności — ani bazy, ani modelu.

**Files:**
- Create: `app/grouping.py`
- Test: `tests/test_grouping.py`

**Interfaces:**
- Consumes: `app.fce_taxonomy.normalize_topic(topic: str) -> str`
- Produces:
  - `normalize_rule(rule: str) -> str`
  - `chunks(items: list, size: int) -> list[list]`
  - `NewGroup(key: str, rule: str, explanation: str, topic: str, error_ids: tuple[int, ...])`
  - `AssignmentPlan(to_existing: dict[int, int], new_groups: tuple[NewGroup, ...], unassigned: tuple[int, ...])`
  - `plan_assignments(model_output: dict, sent_error_ids: list[int], existing_group_ids: set[int]) -> AssignmentPlan`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Utwórz `tests/test_grouping.py`:

```python
"""Walidacja odpowiedzi modelu przy grupowaniu — czysta tabelka wejście-wyjście.

Model potrafi wymyślić id, pominąć wpis, powtórzyć grupę albo zwrócić temat spoza
taksonomii. Każdy z tych przypadków ma tu swój test, bo to jedyna warstwa, która
te przekłamania wychwytuje.
"""

import pytest

from app import grouping


def test_normalize_rule_ignores_case_punctuation_and_spacing():
    assert grouping.normalize_rule("  Depend + ON!  ") == "depend + on"
    assert grouping.normalize_rule("depend on") == grouping.normalize_rule("Depend, on.")


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
```

- [ ] **Step 2: Uruchom testy i potwierdź, że padają**

Run: `python3 -m pytest tests/test_grouping.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.grouping'`

- [ ] **Step 3: Napisz moduł**

Utwórz `app/grouping.py`:

```python
"""Walidacja i normalizacja odpowiedzi modelu przy grupowaniu błędów.

Moduł jest czysty: żadnej bazy, żadnego LLM. Wejściem jest surowy słownik zwrócony
przez model, wyjściem — plan przypisań, który warstwa bazy wykonuje bez podejmowania
dalszych decyzji. Dzięki temu najbardziej podatna na przekłamania część testuje się
tabelką wejście-wyjście, tak jak reguła serii w `app/streak.py`.

Model potrafi wymyślić id grupy, pominąć wpis, zaproponować dwa razy tę samą grupę
albo zwrócić temat spoza taksonomii. Każdy z tych przypadków kończy się tutaj, a nie
wyjątkiem w trakcie żądania.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import fce_taxonomy as tax

_WS = re.compile(r"\s+")
# Zostawiamy '+', bo reguły często mają postać "depend + on".
_PUNCT = re.compile(r"[^\w\s+]", re.UNICODE)


def normalize_rule(rule: str | None) -> str:
    """Klucz deduplikacji nowych grup: bez wielkości liter, interpunkcji i nadmiarowych spacji."""
    lowered = (rule or "").strip().lower()
    return _WS.sub(" ", _PUNCT.sub(" ", lowered)).strip()


def chunks(items: list, size: int) -> list[list]:
    """Dzieli listę na porcje o zadanym rozmiarze (ostatnia bywa krótsza)."""
    if size <= 0:
        raise ValueError("size musi być dodatnie")
    return [items[i:i + size] for i in range(0, len(items), size)]


@dataclass(frozen=True)
class NewGroup:
    """Grupa do utworzenia wraz z wpisami, które mają do niej trafić."""
    key: str
    rule: str
    explanation: str
    topic: str
    error_ids: tuple[int, ...]


@dataclass(frozen=True)
class AssignmentPlan:
    """Komplet decyzji dla jednej porcji: co dopiąć, co utworzyć, co zostawić luzem."""
    to_existing: dict[int, int]
    new_groups: tuple[NewGroup, ...]
    unassigned: tuple[int, ...]


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def plan_assignments(model_output: dict | None, sent_error_ids: list[int],
                     existing_group_ids: set[int]) -> AssignmentPlan:
    """Zamienia surową odpowiedź modelu w plan przypisań.

    Każdy wpis, którego model nie obsłużył wiarygodnie, ląduje w `unassigned` —
    żądanie ma się nie wywalić tylko dlatego, że model coś zmyślił.
    """
    sent = list(dict.fromkeys(int(e) for e in sent_error_ids))
    pending = set(sent)
    to_existing: dict[int, int] = {}
    buckets: dict[str, dict] = {}

    for row in (model_output or {}).get("assignments") or []:
        if not isinstance(row, dict):
            continue
        error_id = _as_int(row.get("error_id"))
        if error_id is None or error_id not in pending:
            continue  # wymyślony wpis albo powtórzenie już rozstrzygniętego

        if row.get("group_id") is not None:
            group_id = _as_int(row.get("group_id"))
            if group_id is not None and group_id in existing_group_ids:
                to_existing[error_id] = group_id
                pending.discard(error_id)
            continue  # wymyślone id → wpis zostaje nieprzypisany

        new = row.get("new_group")
        if not isinstance(new, dict):
            continue
        rule = str(new.get("rule") or "").strip()
        key = normalize_rule(rule)
        if not key:
            continue  # grupa bez reguły jest bezużyteczna
        bucket = buckets.get(key)
        if bucket is None:
            # normalize_topic jest wrażliwe na wielkość liter i nie przycina spacji.
            raw_topic = str(new.get("topic") or "").strip().lower()
            bucket = {
                "rule": rule,
                "explanation": str(new.get("explanation") or "").strip(),
                "topic": tax.normalize_topic(raw_topic),
                "error_ids": [],
            }
            buckets[key] = bucket
        bucket["error_ids"].append(error_id)
        pending.discard(error_id)

    new_groups = tuple(
        NewGroup(key=key, rule=b["rule"], explanation=b["explanation"],
                 topic=b["topic"], error_ids=tuple(b["error_ids"]))
        for key, b in buckets.items()
    )
    return AssignmentPlan(
        to_existing=to_existing,
        new_groups=new_groups,
        unassigned=tuple(eid for eid in sent if eid in pending),
    )
```

- [ ] **Step 4: Uruchom testy i potwierdź, że przechodzą**

Run: `python3 -m pytest tests/test_grouping.py -q`
Expected: PASS — 14 testów

- [ ] **Step 5: Commit**

```bash
git add app/grouping.py tests/test_grouping.py
git commit -m "Czysty moduł walidacji odpowiedzi modelu przy grupowaniu"
```

---

### Task 2: Warstwa bazy — schemat, migracja, CRUD grup

**Files:**
- Modify: `app/db.py` (stała `_SCHEMA`, funkcja `_migrate`, nowa sekcja funkcji na końcu)
- Test: `tests/test_db.py` (dopisz na końcu)

**Interfaces:**
- Consumes: `app.db.get_connection`, `_synchronized`, `_now`, `_today`
- Produces:
  - `insert_group(conn, *, rule, explanation, topic) -> int`
  - `get_group(conn, group_id) -> Optional[dict]`
  - `list_groups(conn) -> list[dict]` — każdy wiersz ma `member_count`
  - `update_group(conn, group_id, *, rule, explanation) -> bool`
  - `delete_group(conn, group_id) -> bool` — członkowie wracają do `group_id = NULL`
  - `set_error_group(conn, error_id, group_id) -> bool`
  - `group_of_error(conn, error_id) -> Optional[int]`
  - `group_member_count(conn, group_id) -> int`
  - `list_group_members(conn, group_id) -> list[dict]`
  - `list_ungrouped_errors(conn, limit=2000) -> list[dict]`
  - `clear_all_groups(conn) -> None`
  - `insert_group_review(conn, group_id) -> None`
  - `insert_group_drill_score(conn, *, group_id, correct_items, total_items) -> None`
  - `group_drill_correct_today(conn, group_id) -> int`
  - `group_topic_counts(conn) -> list[dict]` — `topic`, `count`, `last_seen` dla `srs`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz na końcu `tests/test_db.py`:

```python
# --- Grupy błędów -------------------------------------------------------------

def _err(conn, topic="prepositions", student="depends from", correct="depends on"):
    return db.insert_error(conn, source="test", exercise_type="imported", topic=topic,
                           student_text=student, correct_text=correct,
                           explanation="kalka z polskiego", severity="minor")


def test_insert_and_get_group(conn):
    gid = db.insert_group(conn, rule="depend + on", explanation="zawsze 'on'",
                          topic="prepositions")
    g = db.get_group(conn, gid)
    assert g["rule"] == "depend + on"
    assert g["topic"] == "prepositions"
    assert g["created_at"] and g["updated_at"]


def test_get_missing_group_returns_none(conn):
    assert db.get_group(conn, 999) is None


def test_list_groups_carries_member_count(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.set_error_group(conn, _err(conn), gid)
    db.set_error_group(conn, _err(conn), gid)
    rows = db.list_groups(conn)
    assert len(rows) == 1
    assert rows[0]["member_count"] == 2


def test_empty_group_is_listed_with_zero_members(conn):
    db.insert_group(conn, rule="r", explanation="e", topic="articles")
    assert db.list_groups(conn)[0]["member_count"] == 0


def test_update_group_changes_rule_and_bumps_updated_at(conn):
    gid = db.insert_group(conn, rule="stara", explanation="e", topic="articles")
    before = db.get_group(conn, gid)["updated_at"]
    assert db.update_group(conn, gid, rule="nowa", explanation="e2") is True
    after = db.get_group(conn, gid)
    assert after["rule"] == "nowa"
    assert after["explanation"] == "e2"
    assert after["updated_at"] >= before


def test_update_missing_group_returns_false(conn):
    assert db.update_group(conn, 999, rule="x", explanation="y") is False


def test_delete_group_returns_members_to_ungrouped(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    assert db.delete_group(conn, gid) is True
    assert db.get_group(conn, gid) is None
    assert db.group_of_error(conn, eid) is None
    assert [e["id"] for e in db.list_ungrouped_errors(conn)] == [eid]


def test_group_reviews_survive_group_deletion(conn):
    """Usunięcie grupy nie cofa zdobytego celu — tak samo jak usunięcie błędu."""
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_group_review(conn, gid)
    assert db.reviews_done_today(conn) == 1
    db.delete_group(conn, gid)
    assert db.reviews_done_today(conn) == 1


def test_deleting_last_member_keeps_the_group(conn):
    """Pusta grupa zostaje — nic nie znika samo, o usunięciu decyduje uczeń."""
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    db.delete_error(conn, eid)
    assert db.get_group(conn, gid) is not None
    assert db.group_member_count(conn, gid) == 0


def test_set_error_group_to_none_detaches(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    assert db.set_error_group(conn, eid, None) is True
    assert db.group_of_error(conn, eid) is None
    assert db.group_member_count(conn, gid) == 0


def test_clear_all_groups_removes_groups_and_assignments(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    eid = _err(conn)
    db.set_error_group(conn, eid, gid)
    db.clear_all_groups(conn)
    assert db.list_groups(conn) == []
    assert db.group_of_error(conn, eid) is None


def test_list_ungrouped_skips_assigned_errors(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    assigned = _err(conn)
    loose = _err(conn)
    db.set_error_group(conn, assigned, gid)
    assert [e["id"] for e in db.list_ungrouped_errors(conn)] == [loose]


def test_group_drill_and_review_count_toward_the_day(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_group_drill_score(conn, group_id=gid, correct_items=3, total_items=5)
    db.insert_group_drill_score(conn, group_id=gid, correct_items=2, total_items=5)
    assert db.group_drill_correct_today(conn, gid) == 5
    db.insert_group_review(conn, gid)
    db.insert_group_review(conn, gid)  # idempotentne w obrębie dnia
    assert db.reviews_done_today(conn) == 1


def test_reviews_done_today_sums_errors_and_groups(conn):
    eid = _err(conn)
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_review(conn, eid)
    db.insert_group_review(conn, gid)
    assert db.reviews_done_today(conn) == 2


def test_reviews_per_day_sums_both_sources(conn):
    eid = _err(conn)
    gid = db.insert_group(conn, rule="r", explanation="e", topic="articles")
    db.insert_review(conn, eid)
    db.insert_group_review(conn, gid)
    per_day = db.reviews_per_day(conn)
    assert sum(per_day.values()) == 2


def test_group_topic_counts_feeds_srs(conn):
    gid = db.insert_group(conn, rule="r", explanation="e", topic="prepositions")
    db.set_error_group(conn, _err(conn), gid)
    rows = db.group_topic_counts(conn)
    assert rows[0]["topic"] == "prepositions"
    assert rows[0]["count"] == 1
    assert rows[0]["last_seen"]
```

- [ ] **Step 2: Uruchom testy i potwierdź, że padają**

Run: `python3 -m pytest tests/test_db.py -q`
Expected: FAIL — `AttributeError: module 'app.db' has no attribute 'insert_group'`

- [ ] **Step 3: Dopisz schemat i migrację**

W `app/db.py`, na końcu stałej `_SCHEMA` (przed zamykającym `"""`), dodaj:

```sql
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
```

W funkcji `_migrate`, przed `conn.commit()`, dodaj:

```python
    err_cols = {r["name"] for r in conn.execute("PRAGMA table_info(errors)")}
    if "group_id" not in err_cols:
        # NULL = wpis nieprzypisany (przyszedł po ostatnim przebiegu grupowania).
        conn.execute("ALTER TABLE errors ADD COLUMN group_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_errors_group ON errors(group_id)")
```

- [ ] **Step 4: Dopisz funkcje warstwy bazy**

Na końcu `app/db.py` dodaj sekcję:

```python
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
    `group_reviews` zostają — usunięcie nie cofa zdobytego celu ani serii."""
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
    """Materiał dla `srs.choose_topic` w trybie grupowym: ile grup na temat i jak świeże."""
    rows = conn.execute(
        "SELECT topic, COUNT(*) AS count, MAX(updated_at) AS last_seen "
        "FROM error_groups GROUP BY topic ORDER BY count DESC"
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Zsumuj oba źródła zaliczeń**

Zamień ciała `reviews_done_today` i `reviews_per_day` w `app/db.py`:

```python
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
```

- [ ] **Step 6: Uruchom całość i potwierdź, że przechodzi**

Run: `python3 -m pytest -q`
Expected: PASS — dotychczasowe 88 testów plus 14 z Taska 1 plus 16 nowych

- [ ] **Step 7: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "Warstwa bazy dla grup błędów; zaliczenia z dwóch źródeł"
```

---

### Task 3: Wywołanie modelu (`llm_client.group_errors`)

**Files:**
- Modify: `app/llm_client.py` (nowa sekcja po `extract_errors_from_text`)
- Test: `tests/test_llm_client.py` (dopisz na końcu)

**Interfaces:**
- Consumes: `_call_json(prompt, kind)`, `tax.topic_label`
- Produces: `group_errors(errors: list[dict], existing_groups: list[dict], lang: str = "pl") -> dict`
  — zwraca surowy słownik z kluczem `assignments`; walidacja należy do `app/grouping.py`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz na końcu `tests/test_llm_client.py`:

```python
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
```

- [ ] **Step 2: Uruchom testy i potwierdź, że padają**

Run: `python3 -m pytest tests/test_llm_client.py -q`
Expected: FAIL — `AttributeError: module 'app.llm_client' has no attribute 'group_errors'`

- [ ] **Step 3: Dodaj funkcję**

W `app/llm_client.py`, po `extract_errors_from_text`, dodaj:

```python
# --- Grupowanie błędów w reguły ----------------------------------------------

def _group_line(err: dict) -> str:
    explanation = str(err.get("explanation") or "")[:200]
    return (f"- id={err['id']} | temat={err.get('topic', '')} | "
            f"błędnie: {err.get('student_text', '')} | poprawnie: {err.get('correct_text', '')} | "
            f"uwaga: {explanation}")


def group_errors(errors: list[dict], existing_groups: list[dict], lang: str = "pl") -> dict:
    """Przypisuje błędy do grup-reguł. Jedno wywołanie na porcję.

    Zwraca SUROWY słownik od modelu — walidacja (wymyślone id, duplikaty, pominięcia)
    należy do `app/grouping.py`, żeby dało się ją testować bez wywoływania modelu.
    Pusta lista wejściowa nie woła modelu w ogóle: to najczęstszy przypadek przy
    przyrostowym scalaniu i nie ma powodu płacić za nic.
    """
    if not errors:
        return {"assignments": []}

    lang_name = _lang_name(lang)
    known = "\n".join(
        f"- id={g['id']} | reguła: {g['rule']} | temat={g.get('topic', '')}"
        for g in existing_groups
    ) or "(brak — wszystkie grupy trzeba dopiero utworzyć)"
    items = "\n".join(_group_line(e) for e in errors)
    shape = ('{"assignments": [{"error_id": int, "group_id": int|null, '
             '"new_group": {"rule": str, "explanation": str, "topic": str}|null}]}')

    prompt = (
        f"{_EXAMINER_SYSTEM}\n\n"
        "Grupujesz błędy ucznia w REGUŁY. Jedna reguła to jedno zagadnienie językowe, "
        "które uczeń łamie — ta sama reguła może wystąpić w wielu różnych zdaniach.\n\n"
        f"ISTNIEJĄCE GRUPY:\n{known}\n\n"
        f"BŁĘDY DO PRZYPISANIA:\n{items}\n\n"
        "Dla KAŻDEGO błędu z listy zwróć dokładnie jeden wpis:\n"
        "- jeśli pasuje do istniejącej grupy → podaj jej 'group_id' i 'new_group': null,\n"
        "- jeśli nie pasuje do żadnej → 'group_id': null i opisz 'new_group'.\n"
        "Nie wymyślaj identyfikatorów spoza listy istniejących grup. "
        "Nie twórz grupy na jeden błąd, jeśli pasuje on do istniejącej. "
        "Grupa może łączyć błędy z różnych tematów, jeśli łamią tę samą regułę.\n"
        f"'rule' to krótka nazwa reguły (do 60 znaków), np. \"depend + on\". "
        f"'explanation' to jedno zdanie po {lang_name}. "
        f"'topic' to identyfikator tematu z taksonomii FCE, małymi literami.\n\n"
        f"Zwróć WYŁĄCZNIE JSON w kształcie: {shape}"
    )
    return _call_json(prompt, kind="group")
```

- [ ] **Step 4: Uruchom testy i potwierdź, że przechodzą**

Run: `python3 -m pytest tests/test_llm_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/llm_client.py tests/test_llm_client.py
git commit -m "Wywołanie modelu grupujące błędy w reguły"
```

---

### Task 4: Endpointy grup

**Files:**
- Modify: `app/models.py` (modele żądań), `app/main.py` (nowa sekcja endpointów; zmiana `remove_error`)
- Test: `tests/test_api.py` (dopisz na końcu)

**Interfaces:**
- Consumes: `db.*` z Taska 2, `grouping.plan_assignments`, `grouping.chunks`, `llm_client.group_errors`
- Produces:
  - `GET /api/groups` → `{"groups": [...], "ungrouped": int}`
  - `POST /api/groups/assign` → `{"assigned": int, "created": int, "unassigned": int}`
  - `POST /api/groups/regroup` → jak wyżej
  - `PATCH /api/groups/{group_id}` → `{"updated": group_id}`
  - `DELETE /api/groups/{group_id}` → `{"deleted": group_id}`
  - `PATCH /api/errors/{error_id}/group` → `{"error_id": int, "group_id": int|null, "emptied_group_id": int|null}`
  - `DELETE /api/errors/{error_id}` → `{"deleted": int, "emptied_group_id": int|null}`
  - Stała `GROUP_CHUNK_SIZE = 60`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz na końcu `tests/test_api.py`:

```python
# --- Grupy błędów -------------------------------------------------------------

def _post_error(client, student="depends from", topic="prepositions"):
    res = client.post("/api/errors", json={
        "topic": topic, "student_text": student, "correct_text": "depends on",
        "explanation": "kalka z polskiego", "severity": "minor",
        "exercise_type": "imported",
    })
    assert res.status_code == 200
    return res.json()["id"]


def test_groups_endpoint_reports_ungrouped_count(app_ctx):
    client, _ = app_ctx
    _post_error(client)
    body = client.get("/api/groups").json()
    assert body["groups"] == []
    assert body["ungrouped"] == 1


def test_assign_creates_groups_from_model_output(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "group_id": None,
         "new_group": {"rule": "depend + on", "explanation": "zawsze 'on'",
                       "topic": "prepositions"}},
    ]})
    out = client.post("/api/groups/assign").json()
    assert out == {"assigned": 0, "created": 1, "unassigned": 0}
    body = client.get("/api/groups").json()
    assert body["ungrouped"] == 0
    assert body["groups"][0]["rule"] == "depend + on"
    assert body["groups"][0]["member_count"] == 1


def test_assign_with_invented_group_id_leaves_error_ungrouped(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch,
              {"assignments": [{"error_id": eid, "group_id": 999}]})
    out = client.post("/api/groups/assign").json()
    assert out == {"assigned": 0, "created": 0, "unassigned": 1}
    assert client.get("/api/groups").json()["ungrouped"] == 1


def test_assign_without_ungrouped_errors_does_not_call_model(app_ctx, monkeypatch):
    client, main_mod = app_ctx

    def explode(prompt, kind="other"):
        raise AssertionError("model nie powinien być wołany")

    monkeypatch.setattr(main_mod.llm_client, "_invoke", explode)
    assert client.post("/api/groups/assign").json() == {
        "assigned": 0, "created": 0, "unassigned": 0}


def test_patch_group_renames_rule(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "stara", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    assert client.patch(f"/api/groups/{gid}",
                        json={"rule": "nowa", "explanation": "e2"}).status_code == 200
    assert client.get("/api/groups").json()["groups"][0]["rule"] == "nowa"


def test_patch_missing_group_is_404(app_ctx):
    client, _ = app_ctx
    assert client.patch("/api/groups/999", json={"rule": "a", "explanation": "b"}
                        ).status_code == 404


def test_delete_group_returns_members_to_ungrouped(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "r", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    assert client.delete(f"/api/groups/{gid}").status_code == 200
    body = client.get("/api/groups").json()
    assert body["groups"] == []
    assert body["ungrouped"] == 1


def test_deleting_last_member_keeps_group_and_reports_it(app_ctx, monkeypatch):
    """Pusta grupa zostaje; endpoint tylko sygnalizuje, że osierociała."""
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "r", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    out = client.delete(f"/api/errors/{eid}").json()
    assert out["emptied_group_id"] == gid
    groups = client.get("/api/groups").json()["groups"]
    assert len(groups) == 1
    assert groups[0]["member_count"] == 0


def test_deleting_error_without_group_reports_no_orphan(app_ctx):
    client, _ = app_ctx
    eid = _post_error(client)
    assert client.delete(f"/api/errors/{eid}").json()["emptied_group_id"] is None


def test_patch_error_group_detaches_and_reports_orphan(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "r", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    gid = client.get("/api/groups").json()["groups"][0]["id"]
    out = client.patch(f"/api/errors/{eid}/group", json={"group_id": None}).json()
    assert out["group_id"] is None
    assert out["emptied_group_id"] == gid


def test_regroup_rebuilds_from_scratch(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "pierwsza", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": "druga", "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/regroup")
    groups = client.get("/api/groups").json()["groups"]
    assert len(groups) == 1
    assert groups[0]["rule"] == "druga"
```

- [ ] **Step 2: Uruchom testy i potwierdź, że padają**

Run: `python3 -m pytest tests/test_api.py -q`
Expected: FAIL — 404 na `/api/groups`

- [ ] **Step 3: Dodaj modele żądań**

W `app/models.py`, w sekcji „Żądania API", dodaj:

```python
class GroupUpdate(BaseModel):
    """Ręczna poprawka grupy — zmiana nazwy reguły lub jej wyjaśnienia."""
    rule: str
    explanation: str = ""


class ErrorGroupUpdate(BaseModel):
    """Przepięcie wpisu do innej grupy (`group_id`) albo odpięcie (`None`)."""
    group_id: Optional[int] = None
```

- [ ] **Step 4: Dodaj endpointy**

W `app/main.py` dopisz `grouping` do importu w linii 18
(`from . import llm_client, pricing, srs, streak` → `from . import grouping, llm_client, pricing, srs, streak`).
`tax` jest już zaimportowane w linii 17. Następnie dodaj nową sekcję przed sekcją zastrzeżeń:

```python
# --- Grupy błędów -------------------------------------------------------------

# Porcja jednego wywołania modelu. 196 wpisów w jednym żądaniu grozi obcięciem
# odpowiedzi przy FCE_LLM_TIMEOUT = 180 s, więc pierwszy przebieg idzie porcjami.
GROUP_CHUNK_SIZE = 60


def _run_grouping(lang: str) -> dict:
    """Przypisuje wszystkie nieprzypisane wpisy, porcjami. Każda porcja widzi grupy
    utworzone przez poprzednie, więc druga porcja może dopiąć się do świeżej reguły."""
    pending = db.list_ungrouped_errors(conn)
    assigned = created = unassigned = 0

    for chunk in grouping.chunks(pending, GROUP_CHUNK_SIZE):
        existing = db.list_groups(conn)
        try:
            raw = llm_client.group_errors(
                errors=chunk,
                existing_groups=[{"id": g["id"], "rule": g["rule"], "topic": g["topic"]}
                                 for g in existing],
                lang=lang,
            )
        except llm_client.LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        plan = grouping.plan_assignments(
            raw, [e["id"] for e in chunk], {g["id"] for g in existing}
        )
        for error_id, group_id in plan.to_existing.items():
            db.set_error_group(conn, error_id, group_id)
            assigned += 1
        for new in plan.new_groups:
            group_id = db.insert_group(conn, rule=new.rule, explanation=new.explanation,
                                       topic=new.topic)
            created += 1
            for error_id in new.error_ids:
                db.set_error_group(conn, error_id, group_id)
        unassigned += len(plan.unassigned)

    return {"assigned": assigned, "created": created, "unassigned": unassigned}


@app.get("/api/groups")
def get_groups(lang: str = Query(default="pl")) -> dict:
    groups = db.list_groups(conn)
    for g in groups:
        g["topic_label"] = tax.topic_label(g["topic"], lang)
    return {"groups": groups, "ungrouped": len(db.list_ungrouped_errors(conn))}


@app.get("/api/groups/{group_id}/members")
def get_group_members(group_id: int, lang: str = Query(default="pl")) -> list[dict]:
    if db.get_group(conn, group_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
    members = db.list_group_members(conn, group_id)
    for m in members:
        m["topic_label"] = tax.topic_label(m["topic"], lang)
    return members


@app.post("/api/groups/assign")
def assign_groups(lang: str = Query(default="pl")) -> dict:
    """Przyrostowe scalanie: bierze tylko wpisy bez grupy."""
    return _run_grouping(lang)


@app.post("/api/groups/regroup")
def regroup_all(lang: str = Query(default="pl")) -> dict:
    """Pełne przeliczenie od zera. KASUJE ręczne poprawki i puste grupy — frontend
    pyta o potwierdzenie, zanim tu trafi."""
    db.clear_all_groups(conn)
    return _run_grouping(lang)


@app.patch("/api/groups/{group_id}")
def patch_group(group_id: int, req: GroupUpdate) -> dict:
    if not db.update_group(conn, group_id, rule=req.rule, explanation=req.explanation):
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
    return {"updated": group_id}


@app.delete("/api/groups/{group_id}")
def remove_group(group_id: int) -> dict:
    """Usuwa grupę; jej wpisy wracają do nieprzypisanych. Zaliczenia zostają."""
    if not db.delete_group(conn, group_id):
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
    return {"deleted": group_id}


@app.patch("/api/errors/{error_id}/group")
def patch_error_group(error_id: int, req: ErrorGroupUpdate) -> dict:
    """Przepina wpis do innej grupy albo go odpina.

    `emptied_group_id` mówi frontendowi, że stara grupa właśnie osierociała — pusta
    grupa ZOSTAJE, a o jej usunięciu decyduje uczeń."""
    if db.get_error(conn, error_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    if req.group_id is not None and db.get_group(conn, req.group_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")

    previous = db.group_of_error(conn, error_id)
    db.set_error_group(conn, error_id, req.group_id)
    emptied = previous if (previous is not None and previous != req.group_id
                           and db.group_member_count(conn, previous) == 0) else None
    return {"error_id": error_id, "group_id": req.group_id, "emptied_group_id": emptied}
```

Dopisz `GroupUpdate, ErrorGroupUpdate` do importu modeli w `app/main.py` oraz `tax` jeśli
nie jest jeszcze zaimportowane pod tą nazwą (sprawdź istniejący import
`from . import fce_taxonomy as tax`).

- [ ] **Step 5: Rozszerz istniejące usuwanie błędu**

Zamień ciało `remove_error` w `app/main.py`:

```python
@app.delete("/api/errors/{error_id}")
def remove_error(error_id: int) -> dict:
    """Usuwa wpis z dziennika (np. gdy błąd jest opanowany albo zapisany omyłkowo).

    Zapisane powtórki zostają — dzienny postęp i seria opierają się na tym, co
    naprawdę przerobiłeś, więc usunięcie błędu nie cofa dziś zdobytego celu.

    `emptied_group_id` niesie informację, że po tym usunięciu grupa została pusta.
    Grupa ZOSTAJE — frontend tylko pyta, czy usunąć ją razem z wpisem.
    """
    previous = db.group_of_error(conn, error_id)
    if not db.delete_error(conn, error_id):
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    emptied = previous if (previous is not None
                           and db.group_member_count(conn, previous) == 0) else None
    # Nazwa reguły leci razem z id, żeby frontend mógł zapytać "usunąć grupę X?"
    # bez dodatkowego zapytania o listę grup.
    emptied_rule = None
    if emptied is not None:
        grp = db.get_group(conn, emptied)
        emptied_rule = grp["rule"] if grp else None
    return {"deleted": error_id, "emptied_group_id": emptied,
            "emptied_group_rule": emptied_rule}
```

- [ ] **Step 6: Uruchom całość i potwierdź, że przechodzi**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/models.py tests/test_api.py
git commit -m "Endpointy grup błędów; osierocona grupa jest zgłaszana, nie kasowana"
```

---

### Task 5: Tryb grupowy w ćwiczeniach

**Files:**
- Modify: `app/llm_client.py` (`generate_drill` — opcjonalne konteksty), `app/models.py`, `app/main.py`
- Test: `tests/test_api.py`, `tests/test_llm_client.py`

**Interfaces:**
- Consumes: `db.group_topic_counts`, `db.list_group_members`, `db.insert_group_drill_score`, `db.group_drill_correct_today`, `db.insert_group_review`
- Produces:
  - `llm_client.generate_drill(topic, student_text, correct_text, explanation, lang="pl", contexts=None)`
  - `GET /api/tips/focus?mode=error|group&exclude=<id>` → `{"error": {...}|null, "group": {...}|null, "progress": {...}}`
  - `TipExerciseRequest.group_id: Optional[int]`, `CompleteRequest.group_id: Optional[int]`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz do `tests/test_llm_client.py`:

```python
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
```

Dopisz do `tests/test_api.py`:

```python
def _make_group(client, main_mod, monkeypatch, rule="depend + on"):
    eid = _post_error(client)
    _stub_llm(main_mod, monkeypatch, {"assignments": [
        {"error_id": eid, "new_group": {"rule": rule, "explanation": "e",
                                        "topic": "prepositions"}}]})
    client.post("/api/groups/assign")
    return client.get("/api/groups").json()["groups"][0]["id"], eid


def test_focus_group_mode_returns_a_group(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    gid, _ = _make_group(client, main_mod, monkeypatch)
    body = client.get("/api/tips/focus?mode=group").json()
    assert body["group"]["id"] == gid
    assert body["error"] is None


def test_focus_group_mode_with_no_groups_returns_null(app_ctx):
    client, _ = app_ctx
    body = client.get("/api/tips/focus?mode=group").json()
    assert body["group"] is None


def test_focus_default_mode_is_unchanged(app_ctx):
    client, _ = app_ctx
    _post_error(client)
    body = client.get("/api/tips/focus").json()
    assert body["error"] is not None
    assert body["group"] is None


def test_completing_a_group_counts_one_toward_the_goal(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    gid, _ = _make_group(client, main_mod, monkeypatch)
    target = main_mod.DRILL_CORRECT_TARGET
    out = client.post("/api/tips/complete",
                      json={"group_id": gid, "correct_items": target,
                            "total_items": target}).json()
    assert out["done"] == 1


def test_partial_group_drill_does_not_count_yet(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    gid, _ = _make_group(client, main_mod, monkeypatch)
    out = client.post("/api/tips/complete",
                      json={"group_id": gid, "correct_items": 1, "total_items": 5}).json()
    assert out["done"] == 0


def test_complete_requires_exactly_one_unit(app_ctx):
    client, _ = app_ctx
    assert client.post("/api/tips/complete",
                       json={"correct_items": 1, "total_items": 1}).status_code == 422
```

- [ ] **Step 2: Uruchom i potwierdź, że padają**

Run: `python3 -m pytest tests/test_api.py tests/test_llm_client.py -q`
Expected: FAIL — `TypeError: generate_drill() got an unexpected keyword argument 'contexts'` oraz brak klucza `group`

- [ ] **Step 3: Rozszerz `generate_drill` o konteksty**

W `app/llm_client.py` zmień sygnaturę i dodaj blok kontekstów do promptu:

```python
def generate_drill(topic: str, student_text: str, correct_text: str, explanation: str,
                   lang: str = "pl", contexts: list[str] | None = None) -> tuple[str, GeneratedExercise]:
    """Generuje zestaw ćwiczeń celowanych w KONKRETNY błąd ucznia (jedno wywołanie modelu).

    `contexts` to dodatkowe zdania, w których uczeń złamał tę samą regułę — podawane
    w trybie grupowym. Są dodatkiem podnoszącym jakość zadań, nie warunkiem: grupa bez
    wpisów nadal daje się ćwiczyć z samej reguły i wyjaśnienia.
    """
```

W treści promptu, tuż po fragmencie opisującym błąd, wstaw:

```python
    extra = ""
    if contexts:
        joined = "\n".join(f"- {c}" for c in contexts[:8])
        extra = ("\nTa sama reguła została złamana także w tych zdaniach — użyj ich jako "
                 f"materiału na konteksty, ale NIE powtarzaj ich dosłownie:\n{joined}\n")
```

i dołącz `extra` do składanego promptu bezpośrednio przed instrukcją o kształcie JSON.

- [ ] **Step 4: Rozszerz modele żądań**

W `app/models.py` zamień `TipExerciseRequest` i `CompleteRequest`:

```python
class TipExerciseRequest(BaseModel):
    """Ćwiczenie do jednostki: pojedynczego błędu ALBO grupy. Dokładnie jedno z pól."""
    error_id: Optional[int] = None
    group_id: Optional[int] = None
    lang: str = "pl"

    @model_validator(mode="after")
    def exactly_one_unit(self):
        if (self.error_id is None) == (self.group_id is None):
            raise ValueError("Podaj dokładnie jedno: error_id albo group_id.")
        return self


class CompleteRequest(BaseModel):
    """Wynik zestawu ćwiczeń do jednostki: pojedynczego błędu ALBO grupy."""
    error_id: Optional[int] = None
    group_id: Optional[int] = None
    # Ile ćwiczeń z zestawu uczeń rozwiązał poprawnie (i ile ich było).
    correct_items: int = 1
    total_items: int = 1

    @model_validator(mode="after")
    def exactly_one_unit(self):
        if (self.error_id is None) == (self.group_id is None):
            raise ValueError("Podaj dokładnie jedno: error_id albo group_id.")
        return self
```

Dopisz `model_validator` do importu z `pydantic` na górze `app/models.py`.

- [ ] **Step 5: Dodaj tryb grupowy do endpointów `tips`**

W `app/main.py` dodaj dobór grupy i przerób trzy endpointy:

```python
def _choose_focus_group(exclude_id: int | None = None) -> dict | None:
    """Losuje grupę ważoną częstością tematów (srs) + losowość w obrębie tematu.

    Ta sama mechanika co `_choose_focus_error`, tylko materiałem są grupy."""
    counts = db.group_topic_counts(conn)
    if not counts:
        return None
    candidates = [c["topic"] for c in counts]
    topic = srs.choose_topic(candidates, counts) or candidates[0]
    groups = [g for g in db.list_groups(conn) if g["topic"] == topic]
    if exclude_id is not None:
        remaining = [g for g in groups if g["id"] != exclude_id]
        groups = remaining or [g for g in db.list_groups(conn) if g["id"] != exclude_id] or groups
    return random.choice(groups) if groups else None
```

Zamień `tips_focus`:

```python
@app.get("/api/tips/focus")
def tips_focus(lang: str = Query(default="pl"),
               mode: str = Query(default="error"),
               exclude: int | None = Query(default=None)) -> dict:
    if mode == "group":
        grp = _choose_focus_group(exclude)
        if grp is None:
            return {"error": None, "group": None, "progress": _progress()}
        grp["topic_label"] = tax.topic_label(grp["topic"], lang)
        return {"error": None, "group": grp,
                "progress": _progress(group_id=grp["id"])}

    err = _choose_focus_error(exclude)
    if err is None:
        return {"error": None, "group": None, "progress": _progress()}
    err["topic_label"] = tax.topic_label(err["topic"], lang)
    return {"error": err, "group": None, "progress": _progress(err["id"])}
```

Zamień `_progress`, żeby przyjmował obie jednostki:

```python
def _progress(error_id: int | None = None, group_id: int | None = None) -> dict:
    """Postęp dziennego celu. Z `error_id` lub `group_id` dołącza też postęp ćwiczeń
    do tej jednostki — próg jest wspólny, bo grupa liczy się jak jeden błąd."""
    goal = db.get_int_setting(conn, "daily_goal", DEFAULT_DAILY_GOAL)
    out = {"done": db.reviews_done_today(conn), "goal": goal,
           **streak.state(db.reviews_per_day(conn), goal)}
    if error_id is not None:
        out["drill"] = {"correct": db.drill_correct_today(conn, error_id),
                        "target": DRILL_CORRECT_TARGET}
    elif group_id is not None:
        out["drill"] = {"correct": db.group_drill_correct_today(conn, group_id),
                        "target": DRILL_CORRECT_TARGET}
    return out
```

Zamień `tips_exercise` i `tips_complete`:

```python
@app.post("/api/tips/exercise", response_model=ExercisePublic)
def tips_exercise(req: TipExerciseRequest) -> ExercisePublic:
    if req.group_id is not None:
        grp = db.get_group(conn, req.group_id)
        if grp is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
        members = db.list_group_members(conn, req.group_id)
        # Pusta grupa też daje się ćwiczyć — konteksty są dodatkiem, nie warunkiem.
        contexts = [f"{m['student_text']} → {m['correct_text']}" for m in members]
        topic, student_text = grp["topic"], grp["rule"]
        correct_text, explanation = grp["rule"], grp["explanation"]
    else:
        err = db.get_error(conn, req.error_id)
        if err is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
        contexts = None
        topic, student_text = err["topic"], err["student_text"]
        correct_text, explanation = err["correct_text"], err["explanation"]

    try:
        ex_type, generated = llm_client.generate_drill(
            topic, student_text, correct_text, explanation, lang=req.lang, contexts=contexts
        )
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _store_and_publish(ex_type, topic, generated, "drill")


@app.post("/api/tips/complete")
def tips_complete(req: CompleteRequest) -> dict:
    """Zapisuje wynik zestawu ćwiczeń do jednostki (błędu albo grupy). Jednostka liczy
    się do dziennego celu po uzbieraniu `DRILL_CORRECT_TARGET` poprawnych ćwiczeń
    w danym dniu — narastająco, i tak samo dla obu trybów."""
    total = max(0, req.total_items)
    correct = max(0, min(req.correct_items, total))

    if req.group_id is not None:
        if db.get_group(conn, req.group_id) is None:
            raise HTTPException(status_code=404, detail="Nie znaleziono grupy o tym id.")
        if total:
            db.insert_group_drill_score(conn, group_id=req.group_id,
                                        correct_items=correct, total_items=total)
        if db.group_drill_correct_today(conn, req.group_id) >= DRILL_CORRECT_TARGET:
            db.insert_group_review(conn, req.group_id)
        return _progress(group_id=req.group_id)

    if db.get_error(conn, req.error_id) is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono błędu o tym id.")
    if total:
        db.insert_drill_score(conn, error_id=req.error_id,
                              correct_items=correct, total_items=total)
    if db.drill_correct_today(conn, req.error_id) >= DRILL_CORRECT_TARGET:
        db.insert_review(conn, req.error_id)
    return _progress(req.error_id)
```

- [ ] **Step 6: Uruchom całość i potwierdź, że przechodzi**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/llm_client.py app/models.py app/main.py tests/
git commit -m "Tryb grupowy w ćwiczeniach: dobór, drill z kontekstami, zaliczanie"
```

---

### Task 6: Widok grup w zakładce „Moje błędy"

**Files:**
- Modify: `static/index.html` (sekcja `#view-errors`), `static/app.js`, `static/style.css`

**Interfaces:**
- Consumes: `GET /api/groups`, `GET /api/groups/{id}/members`, `POST /api/groups/assign`, `POST /api/groups/regroup`, `PATCH /api/groups/{id}`, `DELETE /api/groups/{id}`, `DELETE /api/errors/{id}` (pole `emptied_group_id`)
- Produces: funkcje `loadGroups()`, `renderGroupsList(body)`, `groupItemEl(group)`; klucze i18n z prefiksem `groups.`

- [ ] **Step 1: Dodaj markup przełącznika**

W `static/index.html` zamień drugą kartę sekcji `#view-errors`:

```html
      <div class="card">
        <div class="row">
          <h2 data-i18n="errors.journal">Dziennik błędów</h2>
          <div class="mode-switch">
            <button id="errors-mode-items" class="mode is-active"
                    data-i18n="groups.modeItems">Wpisy</button>
            <button id="errors-mode-groups" class="mode"
                    data-i18n="groups.modeGroups">Grupy</button>
          </div>
          <button id="btn-refresh-errors" data-i18n="btn.refresh">Odśwież</button>
        </div>
        <div id="errors-list"></div>
        <div id="groups-pane" class="hidden">
          <div class="row groups-actions">
            <button id="btn-group-assign" data-i18n="groups.assign">Scal nowe</button>
            <button id="btn-group-regroup" data-i18n="groups.regroup">Przegrupuj wszystko</button>
            <span id="groups-ungrouped" class="muted"></span>
          </div>
          <div id="groups-list"></div>
        </div>
      </div>
```

- [ ] **Step 2: Dodaj klucze i18n do OBU bloków**

W `static/app.js`, w bloku `pl`:

```javascript
    "groups.modeItems": "Wpisy",
    "groups.modeGroups": "Grupy",
    "groups.assign": "Scal nowe",
    "groups.regroup": "Przegrupuj wszystko",
    "groups.regroupConfirm": "Przegrupowanie liczy wszystko od nowa i kasuje ręczne poprawki oraz puste grupy. Na pewno?",
    "groups.ungrouped": "Nieprzypisane wpisy: {n}",
    "groups.members": "{n} wpisów",
    "groups.empty": "Brak grup — użyj „Scal nowe\", żeby je utworzyć.",
    "groups.emptyGroup": "Grupa bez wpisów",
    "groups.rename": "Zmień nazwę",
    "groups.renameSave": "Zapisz",
    "groups.delete": "Usuń grupę",
    "groups.detach": "Odepnij",
    "groups.practiceThis": "Ćwicz tę grupę",
    "groups.orphaned": "Grupa „{rule}\" została bez wpisów. Usunąć ją także?",
    "groups.orphanKeep": "Zostaw",
    "groups.orphanDelete": "Usuń grupę",
    "groups.assigned": "Dopięto: {assigned}, nowych grup: {created}, bez przypisania: {unassigned}",
```

W bloku `en` te same klucze:

```javascript
    "groups.modeItems": "Entries",
    "groups.modeGroups": "Groups",
    "groups.assign": "Merge new",
    "groups.regroup": "Regroup everything",
    "groups.regroupConfirm": "Regrouping recomputes from scratch and discards manual edits and empty groups. Are you sure?",
    "groups.ungrouped": "Unassigned entries: {n}",
    "groups.members": "{n} entries",
    "groups.empty": "No groups yet — use \"Merge new\" to create them.",
    "groups.emptyGroup": "Group with no entries",
    "groups.rename": "Rename",
    "groups.renameSave": "Save",
    "groups.delete": "Delete group",
    "groups.detach": "Detach",
    "groups.practiceThis": "Practise this group",
    "groups.orphaned": "Group \"{rule}\" is now empty. Delete it as well?",
    "groups.orphanKeep": "Keep",
    "groups.orphanDelete": "Delete group",
    "groups.assigned": "Attached: {assigned}, new groups: {created}, unassigned: {unassigned}",
```

- [ ] **Step 3: Dodaj render i akcje**

W `static/app.js`, po `renderErrorsList`, dodaj:

```javascript
// --- Grupy błędów -------------------------------------------------------------

function loadGroups() {
  return withBusy("loader.loading", null, async () => {
    try {
      renderGroupsList(await api("/api/groups?lang=" + LANG));
    } catch (e) {
      showError("#groups-list", e.message);
    }
  });
}

function renderGroupsList(body) {
  $("#groups-ungrouped").textContent =
    t("groups.ungrouped").replace("{n}", body.ungrouped);
  const box = $("#groups-list");
  box.innerHTML = "";
  if (!body.groups.length) {
    box.appendChild(elem("p", "stat-empty", t("groups.empty")));
    return;
  }
  body.groups.forEach((g) => box.appendChild(groupItemEl(g)));
}

function groupItemEl(group) {
  const count = group.member_count === 0
    ? t("groups.emptyGroup")
    : t("groups.members").replace("{n}", group.member_count);
  const item = elHtml("div", "group-item",
    `<div class="topic">${esc(group.topic_label || topicLabel(group.topic))}` +
    `<span class="badge minor">${esc(count)}</span></div>` +
    `<div class="rule">${esc(group.rule)}</div>` +
    `<div class="why">${esc(group.explanation)}</div>`);

  const row = elem("div", "err-actions");

  // Przycisk "Ćwicz tę grupę" dochodzi w Tasku 7 — `focusOnGroup` powstaje razem
  // z trybem grupowym w zakładce "Ćwicz błędy" i wcześniej nie miałby czego wywołać.

  const rename = elem("button", "", t("groups.rename"));
  rename.addEventListener("click", () => {
    const input = elem("input", "rule-input");
    input.value = group.rule;
    const save = elem("button", "", t("groups.renameSave"));
    save.addEventListener("click", () => withBusy("loader.saving", save, async () => {
      await api(`/api/groups/${group.id}`, {
        method: "PATCH",
        body: JSON.stringify({ rule: input.value, explanation: group.explanation }),
      });
      loadGroups();
    }));
    rename.replaceWith(input, save);
  });
  row.appendChild(rename);

  const del = elem("button", "danger", t("groups.delete"));
  del.addEventListener("click", () => withBusy("loader.deleting", del, async () => {
    await api(`/api/groups/${group.id}`, { method: "DELETE" });
    loadGroups();
  }));
  row.appendChild(del);

  item.appendChild(row);
  return item;
}

// Pusta grupa ZOSTAJE — pytamy, zamiast kasować po cichu.
function offerOrphanCleanup(groupId, rule) {
  if (groupId === null || groupId === undefined) return Promise.resolve();
  const box = $("#groups-list");
  return new Promise((resolve) => {
    const ask = elem("div", "orphan-ask");
    ask.appendChild(elem("span", "", t("groups.orphaned").replace("{rule}", rule || "")));
    const keep = elem("button", "", t("groups.orphanKeep"));
    const drop = elem("button", "danger", t("groups.orphanDelete"));
    keep.addEventListener("click", () => { ask.remove(); resolve(); });
    drop.addEventListener("click", () => withBusy("loader.deleting", drop, async () => {
      await api(`/api/groups/${groupId}`, { method: "DELETE" });
      ask.remove();
      resolve();
    }));
    ask.appendChild(keep);
    ask.appendChild(drop);
    box.prepend(ask);
  });
}

$("#btn-group-assign").addEventListener("click", () =>
  withBusy("loader.loading", $("#btn-group-assign"), async () => {
    const out = await api("/api/groups/assign?lang=" + LANG, { method: "POST" });
    await loadGroups();
    $("#groups-ungrouped").textContent = t("groups.assigned")
      .replace("{assigned}", out.assigned)
      .replace("{created}", out.created)
      .replace("{unassigned}", out.unassigned);
  }));

$("#btn-group-regroup").addEventListener("click", () => {
  if (!window.confirm(t("groups.regroupConfirm"))) return;
  return withBusy("loader.loading", $("#btn-group-regroup"), async () => {
    await api("/api/groups/regroup?lang=" + LANG, { method: "POST" });
    await loadGroups();
  });
});

function setErrorsMode(mode) {
  const groups = mode === "groups";
  $("#errors-list").classList.toggle("hidden", groups);
  $("#groups-pane").classList.toggle("hidden", !groups);
  $("#errors-mode-items").classList.toggle("is-active", !groups);
  $("#errors-mode-groups").classList.toggle("is-active", groups);
  if (groups) loadGroups();
}

$("#errors-mode-items").addEventListener("click", () => setErrorsMode("items"));
$("#errors-mode-groups").addEventListener("click", () => setErrorsMode("groups"));
```

- [ ] **Step 4: Podepnij sprzątanie osieroconej grupy pod usuwanie wpisu**

W `deleteErrorWidget` w `static/app.js` zamień ciało handlera `yes`, żeby wykorzystał
`emptied_group_id` z odpowiedzi:

```javascript
  yes.addEventListener("click", () => withBusy("loader.deleting", yes, async () => {
    const out = await api(`/api/errors/${errorId}`, { method: "DELETE" });
    await offerOrphanCleanup(out.emptied_group_id, out.emptied_group_rule);
    if (onDone) onDone();
  }));
```

`emptied_group_rule` pochodzi z rozszerzonego `remove_error` (Task 4, krok 5) — tutaj
tylko je konsumujemy.

- [ ] **Step 5: Dodaj style**

W `static/style.css` dopisz:

```css
.mode-switch { display: flex; gap: 0; }
.mode-switch .mode { border-radius: 0; }
.mode-switch .mode:first-child { border-radius: 6px 0 0 6px; }
.mode-switch .mode:last-child { border-radius: 0 6px 6px 0; }
.mode-switch .mode.is-active { background: var(--accent, #2b6cb0); color: #fff; }
.group-item { border: 1px solid #e2e8f0; border-radius: 8px; padding: .75rem; margin: .5rem 0; }
.group-item .rule { font-weight: 600; margin: .25rem 0; }
.groups-actions { gap: .5rem; align-items: center; }
.orphan-ask { display: flex; gap: .5rem; align-items: center;
              background: #fffbea; border: 1px solid #f6e05e;
              border-radius: 8px; padding: .5rem; margin-bottom: .5rem; }
.rule-input { flex: 1; min-width: 12rem; }
```

- [ ] **Step 6: Sprawdź ręcznie**

```bash
python3 -m uvicorn app.main:app --reload
```

Otwórz http://localhost:8000, wejdź w *Moje błędy*, przełącz na *Grupy*, kliknij *Scal nowe*.
Expected: pojawia się lista grup z licznikami; *Przegrupuj wszystko* pyta o potwierdzenie.
Przycisku *Ćwicz tę grupę* jeszcze nie ma — dochodzi w Tasku 7.

- [ ] **Step 7: Commit**

```bash
git add static/ app/main.py
git commit -m "Widok grup w zakładce Moje błędy"
```

---

### Task 7: Tryb grupowy w zakładce „Ćwicz błędy" + smoke test

**Files:**
- Modify: `static/index.html` (sekcja `#view-tips`), `static/app.js`, `tests/smoke_frontend.js`

**Interfaces:**
- Consumes: `GET /api/tips/focus?mode=group`, `POST /api/tips/exercise` z `group_id`, `POST /api/tips/complete` z `group_id`
- Produces: `focusOnGroup(group)`, zmienna stanu `tipsMode`

- [ ] **Step 1: Dodaj przełącznik trybu**

W `static/index.html`, w sekcji `#view-tips`, bezpośrednio nad paskiem celu:

```html
        <div class="mode-switch">
          <button id="tips-mode-errors" class="mode is-active"
                  data-i18n="groups.drillErrors">Pojedyncze błędy</button>
          <button id="tips-mode-groups" class="mode"
                  data-i18n="groups.drillGroups">Grupy</button>
        </div>
```

- [ ] **Step 2: Dodaj klucze i18n do OBU bloków**

`pl`: `"groups.drillErrors": "Pojedyncze błędy", "groups.drillGroups": "Grupy",`
`en`: `"groups.drillErrors": "Individual mistakes", "groups.drillGroups": "Groups",`

- [ ] **Step 3: Przełącz `loadTips` na tryby**

W `static/app.js` dodaj stan i przełącznik oraz rozszerz `loadTips`:

```javascript
let tipsMode = "error";   // "error" | "group"
let tipsGroup = null;

function setTipsMode(mode) {
  tipsMode = mode;
  tipsError = null;
  tipsGroup = null;
  $("#tips-mode-errors").classList.toggle("is-active", mode === "error");
  $("#tips-mode-groups").classList.toggle("is-active", mode === "group");
  loadTips();
}

$("#tips-mode-errors").addEventListener("click", () => setTipsMode("error"));
$("#tips-mode-groups").addEventListener("click", () => setTipsMode("group"));

async function focusOnGroup(group) {
  tipsMode = "group";
  $("#tips-mode-errors").classList.remove("is-active");
  $("#tips-mode-groups").classList.add("is-active");
  activateTab("tips");
  tipsGroup = group;
  tipsError = null;
  setFocusGroup(group);
  await refreshProgress();
}
```

W `loadTips` dodaj `mode` do zapytania i obsłuż odpowiedź grupową. W miejscu, gdzie
dziś czytany jest `body.error`, dodaj gałąź:

```javascript
    const qs = `/api/tips/focus?lang=${LANG}&mode=${tipsMode}` +
      (exclude ? `&exclude=${exclude}` : "");
    const body = await api(qs);
    if (tipsMode === "group") {
      tipsGroup = body.group;
      tipsError = null;
      setFocusGroup(body.group);
    } else {
      tipsError = body.error;
      tipsGroup = null;
      setFocus(body.error);
    }
    renderGoal(body.progress);
```

Dodaj `setFocusGroup` obok istniejącego `setFocus`:

`#tips-focus` to gotowa karta w `index.html` ze stałymi slotami (`#tips-topic`, `#tips-from`,
`#tips-to`, `#tips-why`, `#tips-feedback`), więc `setFocusGroup` je WYPEŁNIA — nie podmienia
`innerHTML`, inaczej zagnieździłby `.focus-card` w `.focus-card` i zgubił przyciski:

```javascript
function setFocusGroup(group) {
  tipsGroup = group;
  tipsExercise = null;
  $("#tips-exercise-area").classList.add("hidden");
  $("#tips-result").classList.add("hidden");
  $("#tips-generate").textContent = t("tips.generate");
  if (!group) {
    $("#tips-focus").classList.add("hidden");
    $("#tips-empty").classList.remove("hidden");
    return;
  }
  $("#tips-empty").classList.add("hidden");
  $("#tips-topic").textContent = group.topic_label || topicLabel(group.topic);
  // Grupa to reguła, nie para "błędnie → poprawnie": w polu docelowym pokazujemy,
  // ile kontekstów ma grupa, a pusta grupa mówi o tym wprost.
  $("#tips-from").textContent = group.rule;
  $("#tips-to").textContent = group.member_count === 0
    ? t("groups.emptyGroup")
    : t("groups.members").replace("{n}", group.member_count);
  $("#tips-why").textContent = group.explanation || "";
  // Zastrzeżenia dotyczą wpisów w dzienniku, nie grup — slot zostaje pusty.
  $("#tips-feedback").innerHTML = "";
  $("#tips-focus").classList.remove("hidden");
}
```

Dopisz też przycisk *Ćwicz tę grupę* do `groupItemEl` z Taska 6 (teraz `focusOnGroup` już istnieje):

```javascript
  const practise = elem("button", "practice-btn", t("groups.practiceThis"));
  practise.addEventListener("click", () => focusOnGroup(group));
  row.insertBefore(practise, row.firstChild);
```

W handlerach `#tips-generate` i wysyłce wyniku podmień payload na zależny od trybu:

```javascript
function tipsUnitBody() {
  return tipsMode === "group" ? { group_id: tipsGroup && tipsGroup.id }
                              : { error_id: tipsError && tipsError.id };
}
```

i użyj `{ ...tipsUnitBody(), lang: LANG }` przy `/api/tips/exercise`
oraz `{ ...tipsUnitBody(), correct_items: c, total_items: n }` przy `/api/tips/complete`.

- [ ] **Step 4: Rozszerz smoke test**

W `tests/smoke_frontend.js` dodaj do atrapy `fetch` odpowiedzi dla nowych ścieżek:

```javascript
    "/api/groups": { groups: [{ id: 1, rule: "depend + on", explanation: "e",
                                topic: "prepositions", topic_label: "Przyimki",
                                member_count: 2 }], ungrouped: 3 },
    "/api/groups/1/members": [],
    "/api/groups/assign": { assigned: 1, created: 1, unassigned: 0 },
    "/api/groups/regroup": { assigned: 0, created: 1, unassigned: 0 },
```

i dopisz przejście obu przełączników po istniejącym obchodzie zakładek:

```javascript
  click("#errors-mode-groups");
  click("#errors-mode-items");
  click("#tips-mode-groups");
  click("#tips-mode-errors");
```

- [ ] **Step 5: Uruchom oba zestawy testów**

Run: `python3 -m pytest -q && node tests/smoke_frontend.js`
Expected: PASS w obu; smoke kończy się `SMOKE TEST: OK`

- [ ] **Step 6: Commit**

```bash
git add static/ tests/smoke_frontend.js
git commit -m "Tryb grupowy w zakładce Ćwicz błędy"
```

---

### Task 8: Dokumentacja

**Files:**
- Modify: `README.md`, `README.pl.md`

- [ ] **Step 1: Opisz grupy w obu wersjach README**

W `README.pl.md`, w sekcji *Użycie*, w punkcie **Moje błędy**, dopisz akapit:

```markdown
  Przełącznik **Wpisy / Grupy** pokazuje ten sam dziennik w dwóch ujęciach. Grupa to jedna
  reguła wraz z kontekstami, w których ją złamałeś — **Scal nowe** przypisuje wpisy, które
  jeszcze nie mają grupy, a **Przegrupuj wszystko** liczy podział od zera (kasuje ręczne
  poprawki, więc pyta o potwierdzenie). Grupy mogą łączyć wpisy z różnych tematów, jeśli
  łamią tę samą regułę. **Pusta grupa zostaje** — gdy usuniesz z niej ostatni wpis,
  aplikacja zapyta, czy usunąć też samą grupę; reguła bez wpisów nadal daje się ćwiczyć.
```

W punkcie **Ćwicz błędy** dopisz:

```markdown
  Przełącznik **Pojedyncze błędy / Grupy** decyduje, co dostajesz do przerobienia. Tryb
  grupowy pozwala szybciej przejść przez wiele powiązanych pomyłek: zamiast jednego zdania
  model widzi regułę i kilka kontekstów, w których ją złamałeś. Do dziennego celu grupa
  liczy się **jak jeden błąd**, więc seria 🔥 pozostaje porównywalna między trybami.
```

W `README.md` te same akapity po angielsku:

```markdown
  The **Entries / Groups** switch shows the same log in two views. A group is one rule
  together with the contexts you broke it in — **Merge new** assigns entries that have no
  group yet, and **Regroup everything** recomputes the split from scratch (it discards
  manual edits, so it asks for confirmation). Groups may span topics when the entries break
  the same rule. **An empty group stays** — when you remove its last entry the app asks
  whether to delete the group too; a rule with no entries can still be practised.
```

```markdown
  The **Individual mistakes / Groups** switch decides what you get to work on. Group mode
  lets you move faster through many related slips: instead of a single sentence the model
  sees the rule and several contexts you broke it in. A group counts as **one mistake**
  toward the daily goal, so the 🔥 streak stays comparable between modes.
```

- [ ] **Step 2: Sprawdź parytet nagłówków**

Run: `diff <(grep -c '^#' README.md) <(grep -c '^#' README.pl.md)`
Expected: brak różnicy (oba pliki mają tyle samo nagłówków)

- [ ] **Step 3: Commit**

```bash
git add README.md README.pl.md
git commit -m "README: grupowanie błędów i tryb grupowy w obu wersjach językowych"
```

---

## Kolejność i zależności

Taski 1–5 idą po kolei (każdy korzysta z poprzedniego). Task 6 wymaga 4, Task 7 wymaga 5 i 6.
Task 8 na końcu. Po Tasku 5 backend jest kompletny i przetestowany — front można robić osobno.
