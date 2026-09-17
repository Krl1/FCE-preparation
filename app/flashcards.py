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

    Wartość spoza drabinki (gdyby ta kiedyś się zmieniła) doczołguje się do najbliższego
    wyższego szczebla, zamiast wysypywać harmonogram."""
    if grade != "known":
        return LADDER[0]
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


@dataclass(frozen=True)
class QueueItem:
    """Pozycja kolejki. `card_id is None` oznacza kartę, która jeszcze nie istnieje
    w bazie — wiersz powstanie dopiero przy jej pierwszym pokazaniu."""
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
        items.append(QueueItem(source_kind=str(src["source_kind"]),
                               source_id=int(src["source_id"]), card_id=None))
    return tuple(items)
