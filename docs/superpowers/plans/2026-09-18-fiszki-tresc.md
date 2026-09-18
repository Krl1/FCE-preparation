# Treść fiszki — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zamienić fiszkę pokazującą formę błędną na kartę uczącą produkcji — polskie zdanie do przetłumaczenia dla leksyki, angielskie zdanie z luką dla gramatyki — bez spowalniania sesji.

**Architecture:** Treść karty przestaje być renderowana ze źródła przy każdym pokazaniu i zaczyna być **generowana raz, wsadowo**, do kolumn w `cards`. Kształt karty wybiera mapa tematów w czystym `app/flashcards.py`; model może od niej odstąpić, ale musi zapisać powód, a odpowiedź niespójną serwer odrzuca w całości. Przewracanie karty nadal nie woła modelu.

**Tech Stack:** Python 3.12, FastAPI, SQLite (WAL), pytest, statyczny frontend (HTML/JS/CSS bez frameworków), smoke test frontendu w Node.

**Spec:** `docs/superpowers/specs/2026-09-18-fiszki-tresc-design.md`

## Global Constraints

- **Forma błędna (`student_text`) nie może trafić ani na przód, ani na tył karty.** To jedyny powód, dla którego ta zmiana powstaje.
- **`GET /api/cards/session` nadal nigdy nie woła modelu.** Model uruchamia wyłącznie `POST /api/cards/prepare` i `POST /api/cards/{id}/regenerate`, na wyraźne kliknięcie.
- Dwa kształty: `translate` (przód po polsku, tył po angielsku + jedno zdanie dlaczego) i `gap` (przód to angielskie zdanie z luką `______`, tył to forma wpisywana w lukę + jedno zdanie dlaczego).
- Kształt wybiera mapa tematów; **odstępstwo bez `shape_reason` jest odrzucane** — decyzja bez uzasadnienia jest nieodróżnialna od kaprysu, a wszystkie testy podstawiają model.
- **Pozycja niespójna wypada w całości**, nie jest łatana: treść ułożona dla jednego kształtu pod etykietą drugiego byłaby gorsza niż jej brak.
- **Harmonogramy przeżywają.** Przygotowanie treści nie dotyka `due_on` ani `interval_days` istniejącej karty.
- Karta bez `prepared_at` nie wchodzi do kolejki. Nowa karta = przygotowana, bez ani jednej oceny w `card_reviews`. Zaległa = z oceną i terminem na dziś lub wcześniej.
- Migracja addytywna: pięć nowych KOLUMN, więc wymagają ścieżki `_migrate` (`ALTER TABLE` nie jest idempotentne) — inaczej niż nowe tabele, które `_SCHEMA` obsługuje sam przez `executescript`.
- Komentarze i docstringi po polsku. Klucze i18n w OBU blokach `static/app.js`.
- Wszystkie funkcje mutujące w `app/db.py` dekorowane `@_synchronized`.

---

## Struktura plików

| Plik | Odpowiedzialność |
|---|---|
| `app/flashcards.py` (modyfikacja) | mapa kształtów, walidacja odpowiedzi modelu, poprawka `build_queue` |
| `app/db.py` (modyfikacja) | pięć kolumn + migracja, zapis treści, kolejka po `prepared_at` i ocenach |
| `app/llm_client.py` (modyfikacja) | `generate_cards()`; usunięcie `improve_card()` |
| `app/main.py` (modyfikacja) | `prepare`, `regenerate`; usunięcie `improve` i `grade-new`; sesja z kolumn |
| `app/models.py` (modyfikacja) | usunięcie `CardGradeNew` |
| `static/*` | przycisk „Przygotuj karty", usunięcie ulepszania, karta z kolumn |
| `tests/test_flashcards.py`, `test_db.py`, `test_api.py`, `test_llm_client.py`, `smoke_frontend.js` | rozszerzenia |
| `README.md`, `README.pl.md` | oba kształty karty w obu językach |

---

### Task 1: Mapa kształtów i walidacja odpowiedzi (`app/flashcards.py`)

**Files:**
- Modify: `app/flashcards.py`
- Test: `tests/test_flashcards.py`

**Interfaces:**
- Produces:
  - `GAP_MARK: str` = `"______"`
  - `SHAPE_TRANSLATE: str` = `"translate"`, `SHAPE_GAP: str` = `"gap"`
  - `default_shape(topic: str) -> str`
  - `make_ref(source_kind: str, source_id: int) -> str` — `"error:12"`
  - `parse_ref(ref: str) -> tuple[str, int] | None`
  - `PreparedCard(ref, source_kind, source_id, shape, front, back, shape_reason)`
  - `CardPlan(prepared: tuple[PreparedCard, ...], unprepared: tuple[str, ...])`
  - `plan_cards(model_output: dict | None, sent: list[dict]) -> CardPlan` — `sent` items are `{"ref": str, "suggested_shape": str}`
  - **zmiana:** `build_queue` czyta `card_id` także z nowych pozycji

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz na końcu `tests/test_flashcards.py`:

```python
# --- Kształt karty i walidacja odpowiedzi modelu ------------------------------


def test_lexical_topics_default_to_translation():
    for topic in ("collocations", "prepositions", "false_friends", "phrasal_verbs"):
        assert fc.default_shape(topic) == fc.SHAPE_TRANSLATE


def test_grammar_topics_default_to_a_gap():
    for topic in ("tenses", "articles", "gerund_infinitive", "quantifiers",
                  "word_order", "reported_speech"):
        assert fc.default_shape(topic) == fc.SHAPE_GAP


def test_unknown_topic_falls_back_to_translation():
    """Karta tłumaczeniowa nie wymaga poprawnie postawionej luki, więc jest
    bezpieczniejszym domyślnym kształtem dla tematu, którego nie znamy."""
    assert fc.default_shape("zmyslony_temat") == fc.SHAPE_TRANSLATE
    assert fc.default_shape("") == fc.SHAPE_TRANSLATE


def test_ref_roundtrips():
    assert fc.make_ref("error", 12) == "error:12"
    assert fc.parse_ref("error:12") == ("error", 12)
    assert fc.parse_ref("group:3") == ("group", 3)


def test_parse_ref_rejects_rubbish():
    for bad in ("", "error", "error:", ":12", "error:abc", "wymyslony:1"):
        assert fc.parse_ref(bad) is None


def _sent(ref="error:1", shape=None):
    return [{"ref": ref, "suggested_shape": shape or fc.SHAPE_TRANSLATE}]


def test_accepts_a_card_matching_the_suggested_shape():
    out = {"cards": [{"ref": "error:1", "shape": "translate",
                      "front": "W domu jest cicho.", "back": "at home"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.unprepared == ()
    card = plan.prepared[0]
    assert (card.source_kind, card.source_id) == ("error", 1)
    assert card.shape == "translate"
    assert card.shape_reason == ""


def test_accepts_a_justified_deviation():
    out = {"cards": [{"ref": "error:1", "shape": "gap",
                      "front": "It ______ on the weather.", "back": "depends",
                      "shape_reason": "przyimek związany z czasownikiem"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.prepared[0].shape == "gap"
    assert plan.prepared[0].shape_reason == "przyimek związany z czasownikiem"


def test_rejects_an_unjustified_deviation():
    """Odstępstwo bez powodu jest nieodróżnialne od kaprysu, a testy podstawiają model."""
    out = {"cards": [{"ref": "error:1", "shape": "gap",
                      "front": "It ______ on the weather.", "back": "depends"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.prepared == ()
    assert plan.unprepared == ("error:1",)


def test_rejects_an_unknown_shape():
    out = {"cards": [{"ref": "error:1", "shape": "wymyslony",
                      "front": "f", "back": "b", "shape_reason": "bo tak"}]}
    assert fc.plan_cards(out, _sent()).unprepared == ("error:1",)


def test_rejects_a_gap_card_without_the_marker():
    out = {"cards": [{"ref": "error:1", "shape": "gap",
                      "front": "It depends on the weather.", "back": "depends on",
                      "shape_reason": "powód"}]}
    assert fc.plan_cards(out, _sent(shape=fc.SHAPE_GAP)).unprepared == ("error:1",)


def test_rejects_empty_sides():
    for front, back in (("", "b"), ("f", ""), ("   ", "b")):
        out = {"cards": [{"ref": "error:1", "shape": "translate",
                          "front": front, "back": back}]}
        assert fc.plan_cards(out, _sent()).unprepared == ("error:1",)


def test_entry_skipped_by_the_model_stays_unprepared():
    assert fc.plan_cards({"cards": []}, _sent()).unprepared == ("error:1",)
    assert fc.plan_cards(None, _sent()).unprepared == ("error:1",)


def test_card_for_something_we_did_not_send_is_ignored():
    out = {"cards": [{"ref": "error:99", "shape": "translate", "front": "f", "back": "b"}]}
    plan = fc.plan_cards(out, _sent())
    assert plan.prepared == ()
    assert plan.unprepared == ("error:1",)


def test_garbage_rows_do_not_raise():
    out = {"cards": ["śmieci", {}, {"ref": 7}, {"ref": "error:1"}]}
    assert fc.plan_cards(out, _sent()).unprepared == ("error:1",)


def test_garbage_top_level_output_does_not_raise():
    """Odpowiedź modelu nie jest nigdzie wcześniej sprawdzana pod kątem typu, więc
    `plan_cards` musi znieść dowolny kształt — i zwrócić czysty plan, nie wyjątek."""
    for bad in ("śmieci", [1, 2, 3], 42, {"cards": 42}, None):
        plan = fc.plan_cards(bad, _sent())
        assert plan.prepared == ()
        assert plan.unprepared == ("error:1",)


def test_unprepared_keeps_the_order_sent():
    sent = [{"ref": "error:3", "suggested_shape": "translate"},
            {"ref": "error:1", "suggested_shape": "translate"}]
    assert fc.plan_cards({"cards": []}, sent).unprepared == ("error:3", "error:1")

```

Zamień też trzy istniejące testy `build_queue`, które budowały nowe pozycje bez `card_id`
(`test_queue_puts_due_cards_before_new_ones`, `test_queue_caps_new_cards_at_the_limit`,
`test_zero_limit_yields_only_due_cards`, `test_group_and_error_sources_both_survive_the_queue`,
`test_negative_limit_is_treated_as_zero`): dopisz `"card_id": <n>` do każdego słownika w liście
nowych i zmień asercje, które zakładały `card_id is None`, na konkretne identyfikatory.

- [ ] **Step 2: Uruchom i potwierdź, że padają**

Run: `python3 -m pytest tests/test_flashcards.py -q`
Expected: FAIL — `AttributeError: module 'app.flashcards' has no attribute 'default_shape'`

- [ ] **Step 3: Dodaj mapę i walidację**

W `app/flashcards.py`, po `LEECH_THRESHOLD`:

```python
# Znacznik luki w karcie typu `gap`. Ten sam ciąg trafia do promptu i do walidacji,
# więc nie może być dwoma literałami.
GAP_MARK = "______"

SHAPE_TRANSLATE = "translate"
SHAPE_GAP = "gap"

# Kształt karty zależy od materiału. Dla leksyki naturalne jest „powiedz to po angielsku";
# dla gramatyki nie ma znaczenia słownikowego do podania, więc zostaje zdanie z luką.
_GAP_TOPICS = frozenset({
    "tenses", "articles", "gerund_infinitive", "quantifiers", "conditionals",
    "relative_clauses", "modals", "passive_voice", "comparatives",
    "adverb_adjective", "word_order", "linkers", "reported_speech",
})


def default_shape(topic: str) -> str:
    """Sugerowany kształt karty dla tematu.

    Temat spoza mapy dostaje kartę tłumaczeniową: nie wymaga poprawnie postawionej luki,
    więc jest bezpieczniejszym domyślnym wyborem niż `gap`."""
    return SHAPE_GAP if topic in _GAP_TOPICS else SHAPE_TRANSLATE


def make_ref(source_kind: str, source_id: int) -> str:
    """Jednoznaczny identyfikator pozycji w partii. Samo `source_id` nie wystarcza,
    bo wpis w dzienniku i grupa mogą mieć ten sam numer."""
    return f"{source_kind}:{source_id}"


def parse_ref(ref: str) -> tuple[str, int] | None:
    parts = str(ref or "").split(":")
    if len(parts) != 2 or parts[0] not in ("error", "group"):
        return None
    try:
        return parts[0], int(parts[1])
    except ValueError:
        return None


@dataclass(frozen=True)
class PreparedCard:
    """Gotowa treść karty, zwalidowana i gotowa do zapisania."""
    ref: str
    source_kind: str
    source_id: int
    shape: str
    front: str
    back: str
    shape_reason: str


@dataclass(frozen=True)
class CardPlan:
    """Wynik jednej partii: co da się zapisać i co zostaje nieprzygotowane."""
    prepared: tuple[PreparedCard, ...]
    unprepared: tuple[str, ...]


def plan_cards(model_output: dict | None, sent: list[dict]) -> CardPlan:
    """Waliduje odpowiedź modelu na partię kart.

    Pozycja niespójna wypada W CAŁOŚCI, a nie jest łatana. Gdyby serwer podmieniał
    zły kształt na sugerowany, podałby treść ułożoną dla jednego kształtu pod etykietą
    drugiego — karta z polskim zdaniem opisana jako luka. Lepiej zostawić ją
    nieprzygotowaną: wróci przy kolejnym kliknięciu.
    """
    suggested = {str(item["ref"]): str(item["suggested_shape"]) for item in sent}
    order = [str(item["ref"]) for item in sent]
    accepted: dict[str, PreparedCard] = {}

    # `model_output` przychodzi wprost od modelu i NIE jest nigdzie wcześniej sprawdzane
    # pod kątem typu: `llm_client._extract_json` kończy się gołym `json.loads`, mimo
    # adnotacji `-> dict`. Model mógł więc zwrócić literał, liczbę albo listę, a pod
    # kluczem `cards` cokolwiek nie-listowego. Nie-słownik traktujemy jak brak odpowiedzi,
    # nie-listę pod `cards` jak listę pustą.
    if not isinstance(model_output, dict):
        model_output = {}
    cards = model_output.get("cards")
    if not isinstance(cards, list):
        cards = []

    for row in cards:
        if not isinstance(row, dict):
            continue
        ref = str(row.get("ref") or "")
        if ref not in suggested or ref in accepted:
            continue
        parsed = parse_ref(ref)
        if parsed is None:
            continue
        shape = str(row.get("shape") or "")
        if shape not in (SHAPE_TRANSLATE, SHAPE_GAP):
            continue
        reason = str(row.get("shape_reason") or "").strip()
        if shape != suggested[ref] and not reason:
            continue  # odstępstwo bez powodu
        front = str(row.get("front") or "").strip()
        back = str(row.get("back") or "").strip()
        if not front or not back:
            continue
        if shape == SHAPE_GAP and GAP_MARK not in front:
            continue
        kind, source_id = parsed
        accepted[ref] = PreparedCard(ref=ref, source_kind=kind, source_id=source_id,
                                     shape=shape, front=front, back=back,
                                     shape_reason=reason if shape != suggested[ref] else "")

    return CardPlan(
        prepared=tuple(accepted[r] for r in order if r in accepted),
        unprepared=tuple(r for r in order if r not in accepted),
    )
```

- [ ] **Step 4: Popraw `build_queue`, żeby nowe pozycje też niosły `card_id`**

W `app/flashcards.py` zamień pętlę po nowych pozycjach:

```python
    for src in new_sources[:max(0, new_limit)]:
        # Po przeprojektowaniu treści nowa karta JUŻ istnieje w bazie (powstaje przy
        # przygotowaniu, nie przy pierwszej ocenie), więc niesie własne id. Bez niego
        # nie dałoby się jej ocenić — ścieżka „oceń źródło bez karty" znika.
        items.append(QueueItem(source_kind=str(src["source_kind"]),
                               source_id=int(src["source_id"]),
                               card_id=int(src["card_id"])))
```

- [ ] **Step 5: Uruchom i potwierdź, że przechodzą**

Run: `python3 -m pytest tests/test_flashcards.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/flashcards.py tests/test_flashcards.py
git commit -m "Mapa kształtów fiszki i walidacja odpowiedzi modelu"
```

---

### Task 2: Warstwa bazy — kolumny treści, migracja, kolejka po przygotowaniu

**Files:**
- Modify: `app/db.py` (`_SCHEMA`, `_migrate`, funkcje kart)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `set_card_content(conn, card_id, *, front, back, shape, shape_reason) -> bool`
  - `cards_unprepared(conn, limit=500) -> list[dict]` — karty bez `prepared_at`, ze wszystkimi polami źródła
  - `count_unprepared(conn) -> int`
  - `cards_new(conn, today, topic=None) -> list[dict]` — przygotowane, bez ani jednej oceny
  - **zmiana:** `cards_due` zwraca tylko przygotowane karty, które mają już ocenę
  - **bez zmian:** `set_card_override` i kolumny `front_override`, `back_override` zostają —
    spec stawia ich usunięcie poza zakresem, mimo że po usunięciu `improve` nikt ich nie woła

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz na końcu `tests/test_db.py`:

```python
# --- Treść fiszki -------------------------------------------------------------

def _prep_err(conn, topic="collocations", student="in home", correct="at home"):
    return db.insert_error(conn, source="test", exercise_type="imported", topic=topic,
                           student_text=student, correct_text=correct,
                           explanation="stały zwrot", severity="minor")


def test_new_card_starts_unprepared(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-18", interval_days=0)
    assert db.get_card(conn, cid)["prepared_at"] is None
    assert db.count_unprepared(conn) == 1


def test_set_card_content_marks_it_prepared(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-18", interval_days=0)
    assert db.set_card_content(conn, cid, front="W domu jest cicho.", back="at home",
                               shape="translate", shape_reason="") is True
    card = db.get_card(conn, cid)
    assert card["front"] == "W domu jest cicho."
    assert card["shape"] == "translate"
    assert card["prepared_at"]
    assert db.count_unprepared(conn) == 0


def test_preparing_content_does_not_touch_the_schedule(conn):
    """Harmonogram przeżywa przeprojektowanie — zmienia się to, co widać, nie kiedy."""
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-10-01", interval_days=30)
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    card = db.get_card(conn, cid)
    assert card["due_on"] == "2026-10-01"
    assert card["interval_days"] == 30


def test_cards_unprepared_carries_the_source_fields(conn):
    eid = _prep_err(conn, topic="articles", student="a free time")
    db.create_card(conn, source_kind="error", source_id=eid,
                   due_on="2026-09-18", interval_days=0)
    row = db.cards_unprepared(conn)[0]
    assert row["topic"] == "articles"
    assert row["student_text"] == "a free time"
    assert row["correct_text"] == "at home"
    assert row["explanation"] == "stały zwrot"


def test_group_source_has_no_wrong_form(conn):
    """Grupa nie ma formy błędnej — reguła nie może wyciec jako `student_text`,
    bo prompt zakazuje pokazywania tego pola."""
    gid = db.insert_group(conn, topic="articles", rule="Przedimek przed rzeczownikiem",
                          explanation="policzalne wymagają przedimka")
    db.create_card(conn, source_kind="group", source_id=gid,
                   due_on="2026-09-18", interval_days=0)
    row = [r for r in db.cards_unprepared(conn) if r["source_kind"] == "group"][0]
    assert row["student_text"] == ""
    assert row["correct_text"] == "Przedimek przed rzeczownikiem"


def test_unprepared_cards_stay_out_of_both_queues(conn):
    eid = _prep_err(conn)
    db.create_card(conn, source_kind="error", source_id=eid,
                   due_on="2026-09-01", interval_days=1)
    assert db.cards_due(conn, "2026-09-18") == []
    assert db.cards_new(conn, "2026-09-18") == []


def test_a_prepared_card_without_reviews_is_new_not_due(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-01", interval_days=1)
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    assert [r["card_id"] for r in db.cards_new(conn, "2026-09-18")] == [cid]
    assert db.cards_due(conn, "2026-09-18") == []


def test_a_reviewed_card_becomes_due_not_new(conn):
    eid = _prep_err(conn)
    cid = db.create_card(conn, source_kind="error", source_id=eid,
                         due_on="2026-09-01", interval_days=1)
    db.set_card_content(conn, cid, front="f", back="b", shape="translate", shape_reason="")
    db.insert_card_review(conn, card_id=cid, grade="known")
    assert [r["card_id"] for r in db.cards_due(conn, "2026-09-18")] == [cid]
    assert db.cards_new(conn, "2026-09-18") == []


def test_cards_new_filters_by_topic(conn):
    a = _prep_err(conn, topic="collocations", student="a")
    b = _prep_err(conn, topic="articles", student="b")
    for eid in (a, b):
        cid = db.create_card(conn, source_kind="error", source_id=eid,
                             due_on="2026-09-18", interval_days=0)
        db.set_card_content(conn, cid, front="f", back="b", shape="translate",
                            shape_reason="")
    got = [r["source_id"] for r in db.cards_new(conn, "2026-09-18", topic="articles")]
    assert got == [b]
```

- [ ] **Step 2: Uruchom i potwierdź, że padają**

Run: `python3 -m pytest tests/test_db.py -q`
Expected: FAIL — `KeyError: 'prepared_at'`

- [ ] **Step 3: Dodaj kolumny do `_SCHEMA` i migrację**

W `app/db.py`, w definicji `CREATE TABLE IF NOT EXISTS cards`, dopisz przed zamykającym nawiasem:

```sql
    front          TEXT,
    back           TEXT,
    shape          TEXT,
    shape_reason   TEXT,
    prepared_at    TEXT,
```

**Indeksu NIE dodawaj do `_SCHEMA`.** `_SCHEMA` leci przez `executescript` przy każdym
połączeniu i PRZED `_migrate`. Dla bazy, która ma już tabelę `cards`, `CREATE TABLE IF NOT
EXISTS` jest no-opem, więc kolumny `prepared_at` jeszcze nie ma, gdy wykonywałby się indeks —
i aplikacja wywala się przy starcie na `no such column: prepared_at`. Zweryfikowane na
prawdziwej bazie. Wzorcem jest `idx_errors_group`, który siedzi wyłącznie w `_migrate`.

W `_migrate`, przed `conn.commit()`:

```python
    # Pięć kolumn treści karty. KOLUMNY wymagają tej ścieżki, w odróżnieniu od nowych
    # TABEL: `_SCHEMA` idzie przez executescript przy każdym połączeniu, więc
    # `CREATE TABLE IF NOT EXISTS` obsługuje istniejące bazy sam, ale `ALTER TABLE
    # ADD COLUMN` nie jest idempotentne i wywaliłby się przy drugim otwarciu.
    card_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
    for col in ("front", "back", "shape", "shape_reason", "prepared_at"):
        if col not in card_cols:
            conn.execute(f"ALTER TABLE cards ADD COLUMN {col} TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_prepared ON cards(prepared_at)")
```

- [ ] **Step 4: Dodaj i zmień funkcje**

Na końcu sekcji fiszek w `app/db.py`:

```python
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
```

**Nie ruszaj** `set_card_override` ani kolumn `front_override` / `back_override`. Po usunięciu
`improve` nikt ich już nie woła, ale spec stawia ich usunięcie poza zakresem: usuwanie kolumn
z działającej bazy to osobne ryzyko, niepotrzebne do naprawienia treści karty. Zostaw też jej
test — martwy kod z testem jest mniej szkodliwy niż migracja, o którą nikt nie prosił.

Zamień warunek w `cards_due`, dopisując do jego `WHERE`:

```python
        "WHERE c.due_on <= ? AND c.prepared_at IS NOT NULL "
        "  AND EXISTS (SELECT 1 FROM card_reviews r WHERE r.card_id = c.id)"
```

- [ ] **Step 5: Uruchom całość**

Run: `python3 -m pytest -q`
Expected: PASS — istniejące testy `cards_due` mogą wymagać dopisania `set_card_content` i jednej oceny; popraw je, nie obchodź warunku.

- [ ] **Step 6: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "Kolumny treści fiszki; kolejka po przygotowaniu i ocenach"
```

---

### Task 3: Generowanie treści (`llm_client.generate_cards`)

**Files:**
- Modify: `app/llm_client.py` (dodanie `generate_cards`, usunięcie `improve_card` i `_CARD_GAP`)
- Test: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: `_call_json(prompt, kind)`, `_lang_name(lang)`, `_EXAMINER_SYSTEM`, `flashcards.GAP_MARK`
- Produces: `generate_cards(items: list[dict], lang: str = "pl") -> dict` — surowy słownik z kluczem `cards`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

W `tests/test_llm_client.py` usuń pięć testów `improve_card` i dopisz:

```python
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
```

Dopisz `from app import flashcards` do importów w `tests/test_llm_client.py`.

- [ ] **Step 2: Uruchom i potwierdź, że padają**

Run: `python3 -m pytest tests/test_llm_client.py -q`
Expected: FAIL — `AttributeError: module 'app.llm_client' has no attribute 'generate_cards'`

- [ ] **Step 3: Zastąp `improve_card` przez `generate_cards`**

Usuń z `app/llm_client.py` całą sekcję `# --- Ulepszanie fiszki ---` (stałą `_CARD_GAP`
i funkcję `improve_card`) i wstaw w jej miejsce:

```python
# --- Generowanie treści fiszek ------------------------------------------------

def _card_line(item: dict) -> str:
    """Jeden wiersz materiału. Zakaz dopisujemy TYLKO wtedy, gdy jest co zakazywać:
    grupa nie ma formy błędnej, a pusty zakaz podpowiadałby modelowi, że czegoś mu
    brakuje."""
    wrong = str(item.get("student_text") or "").strip()
    line = (f"- ref={item['ref']} | temat={item.get('topic_label', item.get('topic', ''))} "
            f"| sugerowany kształt: {item['suggested_shape']} "
            f"| poprawnie: {item.get('correct_text', '')}")
    if wrong:
        line += f" | NIE POKAZUJ: {wrong}"
    return line + f" | uwaga: {str(item.get('explanation') or '')[:180]}"


def generate_cards(items: list[dict], lang: str = "pl") -> dict:
    """Układa treść fiszek dla partii wpisów. Jedno wywołanie na partię.

    Zwraca SUROWY słownik od modelu — walidacja (nieznany ref, zły kształt, odstępstwo
    bez powodu, brak luki) należy do `app/flashcards.py`, żeby dała się testować bez
    wołania modelu.
    """
    if not items:
        return {"cards": []}

    lang_name = _lang_name(lang)
    listing = "\n".join(_card_line(i) for i in items)
    shape = ('{"cards": [{"ref": str, "shape": "translate"|"gap", "front": str, '
             '"back": str, "shape_reason": str}]}')
    prompt = (
        f"{_EXAMINER_SYSTEM}\n\n"
        "Układasz fiszki dla ucznia przygotowującego się do FCE. Fiszka ma go UCZYĆ "
        "poprawnej formy, a nie sprawdzać, czy rozpozna swoją pomyłkę.\n\n"
        f"MATERIAŁ:\n{listing}\n\n"
        "Dla KAŻDEJ pozycji zwróć dokładnie jedną kartę w jednym z dwóch kształtów:\n"
        f"- 'translate' — 'front' to naturalne zdanie po {lang_name}, które uczeń ma "
        "powiedzieć po angielsku; 'back' to angielska wersja.\n"
        f"- 'gap' — 'front' to krótkie angielskie zdanie z luką zapisaną jako "
        f"{flashcards.GAP_MARK}; 'back' to sama forma wpisywana w lukę.\n"
        f"W obu kształtach dopisz na końcu 'back' jedno krótkie zdanie po {lang_name} "
        "wyjaśniające, dlaczego tak.\n\n"
        "Użyj sugerowanego kształtu. Jeśli materiał wyraźnie do niego nie pasuje, możesz "
        "wybrać drugi, ale MUSISZ wtedy wypełnić 'shape_reason' jednym zdaniem; "
        "odstępstwo bez uzasadnienia zostanie odrzucone.\n\n"
        # Zakaz dopisujemy tylko wtedy, gdy w materiale jest co zakazywać — ten sam
        # warunek co w `_card_line`. Partia złożona wyłącznie z grup nie niesie żadnej
        # formy błędnej, a wspominanie zakazu bez treści do zakazania myli model.
        + ("\nNIE WOLNO umieszczać formy z pola 'NIE POKAZUJ' ani na przodzie, ani na "
           "tyle karty — ani w cudzysłowie, ani jako przykład błędu. Uczeń ma nie widzieć "
           "swojej pomyłki; ma wyprodukować formę poprawną.\n\n"
           if "NIE POKAZUJ" in listing else "")
        +
        f"'ref' przepisz dokładnie z listy. Zwróć WYŁĄCZNIE JSON w kształcie: {shape}"
    )
    return _call_json(prompt, kind="cards")
```

Dopisz `from . import flashcards` do importów na górze `app/llm_client.py`.

- [ ] **Step 4: Uruchom i potwierdź, że przechodzą**

Run: `python3 -m pytest tests/test_llm_client.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/llm_client.py tests/test_llm_client.py
git commit -m "Generowanie treści fiszek zamiast ulepszania pojedynczej karty"
```

---

### Task 4: Endpointy — przygotowanie, przegenerowanie, sesja z kolumn

**Files:**
- Modify: `app/main.py`, `app/models.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces:
  - `POST /api/cards/prepare` → `{"prepared": int, "unprepared": int, "remaining": int}`
  - `POST /api/cards/{card_id}/regenerate` → `{"front", "back", "shape"}`
  - `GET /api/cards/session` — serwuje wyłącznie przygotowane, treść z kolumn
  - `GET /api/cards/progress` — dochodzi `unprepared`
  - Stałe `CARD_BATCH_SIZE = 40`, `CARD_PREPARE_MAX = 400`
  - **usunięte:** `POST /api/cards/{id}/improve`, `POST /api/cards/grade-new`, model `CardGradeNew`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

W `tests/test_api.py` usuń testy `grade-new` i `improve`, dopisz:

```python
# --- Treść fiszki -------------------------------------------------------------

def _cards_payload(refs, shape="translate"):
    return {"cards": [{"ref": r, "shape": shape, "front": f"Przód {r}",
                       "back": f"Tył {r}"} for r in refs]}


def test_unprepared_cards_stay_out_of_the_session(app_ctx):
    client, _ = app_ctx
    _card_error(client)
    body = client.get("/api/cards/session").json()
    assert body["cards"] == []
    assert body["progress"]["unprepared"] >= 1


def test_prepare_fills_content_and_the_session_serves_it(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    out = client.post("/api/cards/prepare").json()
    assert out == {"prepared": 1, "unprepared": 0, "remaining": 0}
    card = client.get("/api/cards/session").json()["cards"][0]
    assert card["front"] == f"Przód error:{eid}"
    assert card["shape"] == "translate"


def test_prepared_card_never_shows_the_wrong_form(app_ctx, monkeypatch):
    """Wyrazisty fixture, nie ogólne sprawdzenie podciągu: 35 z 219 wpisów ma formę
    błędną krótszą niż pięć znaków (`in`, `at`, `-`), więc ogólny test padałby na
    niemal każdym poprawnym angielskim zdaniu."""
    client, main_mod = app_ctx
    eid = _card_error(client, student="in home")
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    card = client.get("/api/cards/session").json()["cards"][0]
    assert "in home" not in card["front"].lower()
    assert "in home" not in card["back"].lower()


def test_prepare_without_candidates_does_not_call_the_model(app_ctx, monkeypatch):
    client, main_mod = app_ctx

    def explode(prompt, kind="other"):
        raise AssertionError("nie ma czego przygotowywać")

    monkeypatch.setattr(main_mod.llm_client, "_invoke", explode)
    assert client.post("/api/cards/prepare").json() == {
        "prepared": 0, "unprepared": 0, "remaining": 0}


def test_session_still_never_calls_the_model(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")

    def explode(prompt, kind="other"):
        raise AssertionError("kolejka fiszek nie może wołać modelu")

    monkeypatch.setattr(main_mod.llm_client, "_invoke", explode)
    assert client.get("/api/cards/session").status_code == 200


def test_rejected_entry_stays_unprepared_and_retries(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, {"cards": [
        {"ref": f"error:{eid}", "shape": "gap", "front": "bez luki", "back": "b",
         "shape_reason": "powód"}]})
    assert client.post("/api/cards/prepare").json() == {
        "prepared": 0, "unprepared": 1, "remaining": 1}
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    assert client.post("/api/cards/prepare").json() == {
        "prepared": 1, "unprepared": 0, "remaining": 0}


def test_regenerate_replaces_the_content(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    cid = client.get("/api/cards/session").json()["cards"][0]["card_id"]
    _stub_llm(main_mod, monkeypatch, {"cards": [
        {"ref": f"error:{eid}", "shape": "translate", "front": "Nowy przód",
         "back": "Nowy tył"}]})
    assert client.post(f"/api/cards/{cid}/regenerate").json()["front"] == "Nowy przód"
    assert client.get("/api/cards/session").json()["cards"][0]["front"] == "Nowy przód"


def test_preparing_does_not_disturb_an_existing_schedule(app_ctx, monkeypatch):
    client, main_mod = app_ctx
    eid = _card_error(client)
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post("/api/cards/prepare")
    cid = client.get("/api/cards/session").json()["cards"][0]["card_id"]
    graded = client.post(f"/api/cards/{cid}/grade", json={"grade": "known"}).json()
    due_before = graded["due_on"]
    _stub_llm(main_mod, monkeypatch, _cards_payload([f"error:{eid}"]))
    client.post(f"/api/cards/{cid}/regenerate")
    assert main_mod.db.get_card(main_mod.conn, cid)["due_on"] == due_before
```

- [ ] **Step 2: Uruchom i potwierdź, że padają**

Run: `python3 -m pytest tests/test_api.py -q`
Expected: FAIL — 404 na `/api/cards/prepare`

- [ ] **Step 3: Usuń martwe rzeczy**

W `app/models.py` usuń klasę `CardGradeNew`. W `app/main.py` usuń endpointy
`POST /api/cards/grade-new` i `POST /api/cards/{card_id}/improve` oraz import `CardGradeNew`.

- [ ] **Step 4: Przebuduj renderowanie i dodaj przygotowanie**

W `app/main.py` zamień `_render_card` na czytanie z kolumn i dodaj sekcję przygotowania:

```python
CARD_BATCH_SIZE = 40

# Bezpiecznik na patologiczną bazę, nie zwykły tryb pracy: spec zakłada ~285 kart i ~8
# wywołań na JEDNO kliknięcie, więc próg musi być wyraźnie wyżej, żeby nie zmuszać do
# drugiego kliknięcia tam, gdzie obiecaliśmy jedno. Reszta, jeśli kiedyś powstanie, czeka
# na kolejne kliknięcie, a `remaining` mówi wprost, ile zostało.
CARD_PREPARE_MAX = 400


def _card_content(card: dict) -> dict:
    """Treść karty bierze się teraz z KOLUMN, nie z renderowania ze źródła.

    Renderowanie ze źródła pokazywało na przodzie `student_text`, czyli formę błędną —
    uczyło rozpoznawania własnej pomyłki zamiast produkcji formy poprawnej. Cena tej
    zmiany: poprawka wyjaśnienia w dzienniku nie dociera już sama do karty; od tego
    jest „Przegeneruj"."""
    return {"front": card["front"], "back": card["back"], "shape": card["shape"]}


def _prepare_batch(rows: list[dict], lang: str) -> tuple[int, int]:
    """Przygotowuje jedną partię. Zwraca (przygotowane, nieprzygotowane)."""
    items = [{
        "ref": flashcards.make_ref(r["source_kind"], r["source_id"]),
        "topic": r["topic"],
        "topic_label": tax.topic_label(r["topic"], lang),
        "student_text": r["student_text"],
        "correct_text": r["correct_text"],
        "explanation": r["explanation"],
        "suggested_shape": flashcards.default_shape(r["topic"]),
    } for r in rows]
    by_ref = {i["ref"]: r for i, r in zip(items, rows)}

    try:
        raw = llm_client.generate_cards(items, lang=lang)
    except llm_client.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    plan = flashcards.plan_cards(raw, items)
    for card in plan.prepared:
        db.set_card_content(conn, by_ref[card.ref]["card_id"], front=card.front,
                            back=card.back, shape=card.shape,
                            shape_reason=card.shape_reason)
    return len(plan.prepared), len(plan.unprepared)


@app.post("/api/cards/prepare")
def prepare_cards(lang: str = Query(default="pl")) -> dict:
    """Wsadowo układa treść kart. Jedyne — obok przegenerowania — miejsce, które kosztuje.

    Najpierw zakłada wiersze dla źródeł bez karty, potem przerabia wszystkie karty
    bez treści: i te świeże, i te powstałe pod poprzednim projektem."""
    today = _today_str()
    for src in db.sources_without_card(conn):
        db.create_card(conn, source_kind=src["source_kind"], source_id=src["source_id"],
                       due_on=today, interval_days=0)

    prepared = unprepared = 0
    for chunk in grouping.chunks(db.cards_unprepared(conn, CARD_PREPARE_MAX),
                                 CARD_BATCH_SIZE):
        p, u = _prepare_batch(chunk, lang)
        prepared += p
        unprepared += u
    return {"prepared": prepared, "unprepared": unprepared,
            "remaining": db.count_unprepared(conn)}


@app.post("/api/cards/{card_id}/regenerate")
def regenerate_card(card_id: int, lang: str = Query(default="pl")) -> dict:
    """Układa treść tej jednej karty od nowa — gdy wyszła słabo."""
    card = db.get_card(conn, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono fiszki o tym id.")
    source = _load_source(card["source_kind"], card["source_id"])
    if source is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono źródła tej fiszki.")
    row = {
        "card_id": card_id, "source_kind": card["source_kind"],
        "source_id": card["source_id"], "topic": source["topic"],
        # Grupa nie ma formy błędnej — puste pole, nie reguła. Patrz `_card_line`.
        "student_text": source.get("student_text") or "",
        "correct_text": source.get("correct_text") or source.get("rule", ""),
        "explanation": source.get("explanation", ""),
    }
    prepared, _ = _prepare_batch([row], lang)
    if not prepared:
        raise HTTPException(status_code=502,
                            detail="Model nie zwrócił użytecznej treści karty.")
    return _card_content(db.get_card(conn, card_id))
```

Przebuduj `cards_session` — zmieniają się trzy rzeczy: skąd biorą się nowe pozycje,
skąd bierze się treść, i że `card` nie jest już opcjonalny:

```python
@app.get("/api/cards/session")
def cards_session(lang: str = Query(default="pl"),
                  topic: str | None = Query(default=None)) -> dict:
    """Kolejka na dziś. NIE wywołuje modelu — cała wartość fiszek to natychmiastowość.

    Nowe pozycje biorą się teraz z `cards_new` (karty przygotowane, bez ani jednej oceny),
    a nie z `sources_without_card`: pod nowym projektem karta istnieje, zanim uczeń ją
    zobaczy, bo najpierw musi dostać treść."""
    today = _today_str()
    limit = db.get_int_setting(conn, "cards_new_per_day", DEFAULT_NEW_CARDS_PER_DAY)
    queue = flashcards.build_queue(
        db.cards_due(conn, today, topic=topic),
        db.cards_new(conn, today, topic=topic),
        limit,
    )
    out = []
    for item in queue:
        source = _load_source(item.source_kind, item.source_id)
        card = db.get_card(conn, item.card_id)
        if source is None or card is None:
            continue  # źródło lub karta zniknęły między zapytaniami — pomijamy sesję, nie psujemy
        # Pełne źródło leci w odpowiedzi, bo przycisk przy karcie upartej skacze do
        # „Ćwicz błędy" z TĄ jednostką — a setFocus/setFocusGroup czytają nazwane pola.
        # Grupie trzeba jeszcze dołożyć member_count: get_group go nie zwraca, a
        # setFocusGroup renderuje z niego licznik kontekstów.
        source_payload = dict(source)
        source_payload["topic_label"] = tax.topic_label(source["topic"], lang)
        if item.source_kind == "group":
            source_payload["member_count"] = db.group_member_count(conn, source["id"])
        out.append({
            "card_id": item.card_id,
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "topic": source["topic"],
            "topic_label": tax.topic_label(source["topic"], lang),
            "source": source_payload,
            "leech": flashcards.is_leech(db.card_unknown_count(conn, item.card_id)),
            **_card_content(card),
        })
    return {"cards": out, "progress": _cards_progress()}
```

Zwróć uwagę, co znika: wołanie `_render_card`, gałąź `if item.card_id else None/False`
(każda pozycja ma teraz kartę) oraz pole `improved`.

W `_cards_progress` dopisz jeden wiersz, po `total_sources`:

```python
        # Odróżnia „nie ma z czego robić fiszek" od „są, ale czekają na treść" —
        # bez tego uczeń z pełnym dziennikiem i zerem przygotowanych kart widziałby
        # pusty ekran bez wskazówki, co kliknąć.
        "unprepared": db.count_unprepared(conn),
```

- [ ] **Step 5: Uruchom całość**

Run: `python3 -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/models.py tests/test_api.py
git commit -m "Endpointy przygotowania i przegenerowania; sesja czyta treść z kolumn"
```

---

### Task 5: Frontend — przycisk przygotowania, koniec ulepszania

**Files:**
- Modify: `static/index.html`, `static/app.js`, `tests/smoke_frontend.js`

- [ ] **Step 1: Markup**

W `static/index.html`, w wierszu akcji zakładki Fiszki, dodaj przed `#cards-start`:

```html
          <button id="cards-prepare" data-i18n="cards.prepare">Przygotuj karty</button>
```

Zmień przycisk `#cards-improve` na:

```html
          <button id="cards-regenerate" class="hidden" data-i18n="cards.regenerate">Przegeneruj</button>
```

- [ ] **Step 2: Klucze i18n w OBU blokach**

Usuń `cards.improve` z obu bloków. Dodaj do `pl`:

```javascript
    "cards.prepare": "Przygotuj karty",
    "cards.regenerate": "Przegeneruj",
    "cards.unprepared": "Nieprzygotowanych: {n}",
    "cards.prepared": "Przygotowano: {n}, nieudanych: {u}, zostało: {r}",
    "cards.needPrepare": "Żadna karta nie ma jeszcze treści — kliknij „Przygotuj karty”.",
```

i do `en`:

```javascript
    "cards.prepare": "Prepare cards",
    "cards.regenerate": "Regenerate",
    "cards.unprepared": "Unprepared: {n}",
    "cards.prepared": "Prepared: {n}, failed: {u}, left: {r}",
    "cards.needPrepare": "No card has content yet — click \"Prepare cards\".",
```

- [ ] **Step 3: Logika**

W `static/app.js` zamień handler `#cards-improve` na:

```javascript
$("#cards-regenerate").addEventListener("click", () =>
  withBusy("loader.loading", $("#cards-regenerate"), async () => {
    const card = cardsQueue[cardsIndex];
    if (!card || !card.card_id) return;
    try {
      const out = await api(`/api/cards/${card.card_id}/regenerate?lang=${LANG}`,
                            { method: "POST" });
      card.front = out.front;
      card.back = out.back;
      $("#cards-front").textContent = out.front;
      $("#cards-back").textContent = out.back;
    } catch (e) {
      showError("#cards-error", e.message);
    }
  }));

$("#cards-prepare").addEventListener("click", () =>
  withBusy("loader.loading", $("#cards-prepare"), async () => {
    try {
      const out = await api(`/api/cards/prepare?lang=${LANG}`, { method: "POST" });
      $("#cards-counter").textContent = t("cards.prepared")
        .replace("{n}", out.prepared).replace("{u}", out.unprepared)
        .replace("{r}", out.remaining);
      await loadCardsProgress();
    } catch (e) {
      showError("#cards-error", e.message);
    }
  }));
```

W `renderCardsCounter` dopisz liczbę nieprzygotowanych do komunikatu, a w `showCard()`
zamień warunek pustego ekranu tak, by przy `cardsTotalSources > 0` i braku przygotowanych
kart pokazywał `t("cards.needPrepare")`. W `revealCard` zamień pokazywanie `#cards-improve` na `#cards-regenerate`. Warunek się
upraszcza — pole `improved` znika z odpowiedzi, a przegenerować można też kartę grupy:

```javascript
  if (card.card_id) {
    $("#cards-regenerate").classList.remove("hidden");
  }
```

Usuń przy tym przypisanie `card.improved = true` (dawny `static/app.js:1869`) — nie ma już
czego oznaczać, bo przegenerowanie wolno powtórzyć.

W `gradeCard` usuń gałąź `grade-new` — każda karta w kolejce ma teraz `card_id`:

```javascript
      const out = await api(`/api/cards/${card.card_id}/grade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ grade }),
      });
```

- [ ] **Step 4: Smoke**

W `tests/smoke_frontend.js` dodaj trasę `"/api/cards/prepare": { prepared: 2, unprepared: 0, remaining: 0 }`,
dopisz `front`, `back`, `shape` i `card_id` do fixture'ów sesji (żadna karta bez `card_id`),
usuń trasę `improve`, i dodaj scenariusz klikający `#cards-prepare` oraz asertujący, że
żądanie poleciało.

- [ ] **Step 5: Sprawdź**

Run: `python3 -m pytest -q && node tests/smoke_frontend.js`
Expected: oba zielone. Uruchom też aplikację na porcie 8010 i przejdź: przygotuj → sesja → ocena.

- [ ] **Step 6: Commit**

```bash
git add static/ tests/smoke_frontend.js
git commit -m "Zakładka Fiszki: przygotowanie treści zamiast ulepszania karty"
```

---

### Task 6: Dokumentacja

**Files:**
- Modify: `README.md`, `README.pl.md`

- [ ] **Step 1: Popraw opis fiszek w obu językach**

W `README.pl.md` zamień zdanie opisujące treść karty na:

```markdown
  Karta nie pokazuje Twojej błędnej formy. Zależnie od materiału ma jeden z dwóch
  kształtów: przy słownictwie i kolokacjach na przodzie jest polskie zdanie, które masz
  powiedzieć po angielsku, a przy gramatyce — angielskie zdanie z luką. Na odwrocie
  poprawna forma i jedno zdanie, dlaczego tak. Treść powstaje raz, po kliknięciu
  **Przygotuj karty**; potem przewracanie jest natychmiastowe i nic nie kosztuje.
  Gdy któraś karta wyjdzie słabo, **Przegeneruj** układa ją od nowa.
```

W `README.md` to samo po angielsku:

```markdown
  A card never shows your wrong form. Depending on the material it takes one of two
  shapes: for vocabulary and collocations the front is a Polish sentence you have to say
  in English, and for grammar it is an English sentence with a gap. The back carries the
  correct form and one sentence on why. Content is generated once, when you click
  **Prepare cards**; after that flipping is instant and costs nothing. If a card comes
  out weak, **Regenerate** rebuilds it.
```

Usuń z obu plików zdania opisujące „Ulepsz tę kartę" / „Improve this card".

- [ ] **Step 2: Sprawdź parytet**

Run: `grep -c '^#' README.md README.pl.md`
Expected: obie liczby identyczne. Przeczytaj wypisany wynik, nie zakładaj go.

- [ ] **Step 3: Commit**

```bash
git add README.md README.pl.md
git commit -m "README: dwa kształty fiszki, koniec pokazywania błędnej formy"
```

---

## Kolejność i zależności

Taski 1–4 po kolei. Task 5 wymaga 4. Task 6 na końcu. Po Tasku 4 backend jest kompletny
i przetestowany, więc front da się robić osobno.
