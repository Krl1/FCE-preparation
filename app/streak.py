"""Reguła serii (🔥) — kolejne dni z osiągniętym dziennym celem, z odrabianiem zaległości.

Dzień jest „zaliczony", gdy liczba różnych przerobionych błędów tego dnia >= cel.
Przespanie do `GRACE_DAYS` dni nie zrywa serii od razu: pierwszy dzień po luce musi
pokryć cel za siebie i za każdy opuszczony dzień — czyli `(k + 1) * cel` różnych
błędów — inaczej ciąg pęka na luce. Rozliczenie jest wszystko-albo-nic w obrębie dnia:
połowa długu nie zmniejsza go na jutro. Odrobione dni NIE wchodzą do licznika, więc
seria pokazuje dni, w których naprawdę ćwiczyłeś.

Moduł jest czysty (żadnej bazy): liczy wyłącznie na mapie 'YYYY-MM-DD' -> liczba
różnych błędów, którą dostarcza `db.reviews_per_day()`.
"""

from __future__ import annotations

from datetime import date, timedelta

GRACE_DAYS = 2  # ile dni pod rząd można opuścić i wciąż mieć prawo do spłaty


def _done(per_day: dict[str, int], day: date) -> int:
    return int(per_day.get(day.isoformat(), 0))


def _gap_length(per_day: dict[str, int], goal: int, last_missed: date) -> int:
    """Długość ciągu niezaliczonych dni kończącego się `last_missed`.

    Liczymy najwyżej do `GRACE_DAYS + 1` — dłuższej przerwy i tak nie da się odrobić,
    a bez tego limitu pusta historia oznaczałaby pętlę bez końca."""
    gap = 0
    while gap <= GRACE_DAYS and _done(per_day, last_missed - timedelta(days=gap)) < goal:
        gap += 1
    return gap


def _chain(per_day: dict[str, int], goal: int, last_day: date) -> int:
    """Liczba zaliczonych dni w ciągu kończącym się `last_day` (wliczając odrobione luki)."""
    count = 0
    day = last_day
    while True:
        if _done(per_day, day) >= goal:
            count += 1
            day -= timedelta(days=1)
            continue
        gap = _gap_length(per_day, goal, day)
        if gap > GRACE_DAYS:
            return count
        payer = day + timedelta(days=1)  # dzień zaraz po luce miał ją spłacić
        if _done(per_day, payer) < (gap + 1) * goal:
            return count
        day = day - timedelta(days=gap)  # luka odrobiona — licz dalej przed nią


def state(per_day: dict[str, int], goal: int, today: date | None = None) -> dict:
    """Stan serii: `streak`, `required_today`, `overdue_days`, `at_risk`.

    `required_today` to dzisiejszy cel razem z zaległościami, `overdue_days` to liczba
    opuszczonych dni, które jeszcze da się dziś spłacić, a `at_risk` mówi, że seria
    przepadnie, jeśli ten dług nie zostanie dziś rozliczony."""
    today = today or date.today()
    if goal <= 0:
        return {"streak": 0, "required_today": 0, "overdue_days": 0, "at_risk": False}

    overdue = _gap_length(per_day, goal, today - timedelta(days=1))
    done_today = _done(per_day, today)

    if overdue > GRACE_DAYS:
        # Przerwa dłuższa niż grace — stara seria przepadła, dziś zaczynasz od nowa.
        return {"streak": 1 if done_today >= goal else 0, "required_today": goal,
                "overdue_days": 0, "at_risk": False}

    required = (overdue + 1) * goal
    before_gap = _chain(per_day, goal, today - timedelta(days=overdue + 1))
    if done_today >= required:
        return {"streak": before_gap + 1, "required_today": required,
                "overdue_days": overdue, "at_risk": False}

    # Dziś jeszcze nierozliczone — pokazujemy serię sprzed luki, bo wciąż da się ją
    # uratować. `overdue <= GRACE_DAYS` znaczy, że dzień przed luką był zaliczony,
    # więc `before_gap` jest tu zawsze >= 1 i nie ma czego dodatkowo zabezpieczać.
    return {"streak": before_gap, "required_today": required,
            "overdue_days": overdue, "at_risk": overdue > 0}
