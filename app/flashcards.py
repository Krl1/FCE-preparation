"""Reguła odstępu powtórek dla fiszek i składanie kolejki na dany dzień.

Moduł jest czysty: żadnej bazy, żadnego LLM, żadnego czasu „teraz" branego z systemu —
dzień podaje wywołujący. Dzięki temu cały harmonogram testuje się tabelką wejście-wyjście,
tak jak reguła serii w `app/streak.py`.

Świadomie nie ma tu współczynnika łatwości (SM-2). Przy dwóch przyciskach oceny nie ma
z czego go liczyć, a wyliczanie go mimo to dałoby liczbę, która wygląda mądrze i nic
nie znaczy. Stała drabinka jest uczciwsza i wystarcza.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Kolejne odstępy w dniach. „Umiem" przesuwa o szczebel, „nie umiem" wraca na początek.
LADDER: tuple[int, ...] = (1, 3, 7, 14, 30, 90)

# Tyle pomyłek na jednej karcie oznacza, że samo przypominanie nie działa — czas
# na ćwiczenia w trybie „Ćwicz błędy".
LEECH_THRESHOLD = 4


def next_interval(current_days: int, grade: str) -> int:
    """Następny odstęp. Ocena inna niż 'known' liczy się jako pomyłka.

    Odstęp 0 oznacza „jeszcze nierozpoznana" — karta, której uczeń nie umiał, zanim
    choć raz odpowiedział poprawnie. Taka karta ma zostać w DZISIEJSZEJ kolejce, a nie
    zostać odłożona na jutro: fiszka nie może odkładać właśnie tego materiału, który
    jest najsłabszy. Dlatego pomyłka z odstępu 0 zostaje na 0; dopiero pomyłka na karcie,
    która już raz wspięła się po drabince, cofa ją na jej pierwszy szczebel.

    Wartość spoza drabinki (gdyby ta kiedyś się zmieniła) doczołguje się do najbliższego
    wyższego szczebla, zamiast wysypywać harmonogram."""
    if grade != "known":
        return 0 if current_days <= 0 else LADDER[0]
    for rung in LADDER:
        if rung > current_days:
            return rung
    return LADDER[-1]


def due_date(today: date, interval_days: int) -> str:
    """Termin następnej powtórki jako 'YYYY-MM-DD'."""
    if interval_days < 0:
        raise ValueError("interval_days nie może być ujemne")
    return (today + timedelta(days=interval_days)).isoformat()


def is_leech(unknown_count: int) -> bool:
    """Czy karta jest uparta — tyle pomyłek, że warto ją przerobić ćwiczeniami."""
    return unknown_count >= LEECH_THRESHOLD


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

    for row in (model_output or {}).get("cards") or []:
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


@dataclass(frozen=True)
class QueueItem:
    """Pozycja kolejki. Karta powstaje przy przygotowaniu treści, więc każda pozycja —
    zaległa i nowa — niesie własne `card_id`."""
    source_kind: str
    source_id: int
    card_id: int | None


def build_queue(due: list[dict], new_sources: list[dict], new_limit: int) -> tuple[QueueItem, ...]:
    """Kolejka na dany dzień: najpierw karty zaplanowane, potem nowe do limitu.

    Limit dotyczy WYŁĄCZNIE nowych. Zaległe to materiał, który uczeń już widział —
    ucinanie go zostawiałoby go na zawsze w tyle. Kolejność jest deterministyczna,
    żeby sesja była powtarzalna i testowalna.
    """
    items = [
        QueueItem(source_kind=str(d["source_kind"]), source_id=int(d["source_id"]),
                  card_id=int(d["card_id"]))
        for d in due
    ]
    for src in new_sources[:max(0, new_limit)]:
        # Po przeprojektowaniu treści nowa karta JUŻ istnieje w bazie (powstaje przy
        # przygotowaniu, nie przy pierwszej ocenie), więc niesie własne id. Bez niego
        # nie dałoby się jej ocenić — ścieżka „oceń źródło bez karty" znika.
        items.append(QueueItem(source_kind=str(src["source_kind"]),
                               source_id=int(src["source_id"]),
                               card_id=int(src["card_id"])))
    return tuple(items)
