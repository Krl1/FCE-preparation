"""Cennik API Anthropic — do szacowania kosztu przejścia z trybu headless na klucz API.

Stawki w USD za 1 mln tokenów jako para `(wejście, wyjście)`.

Uczciwość szacunku: stawki potwierdzone w cenniku trzymamy w `PRICES`, a te, których
w nim nie ma (a które raportuje Claude Code), w `ASSUMED` — przybliżone najbliższym
poziomem. Szacunek policzony z użyciem stawki założonej jest oznaczany w odpowiedzi API,
żeby interfejs mógł to zakomunikować, zamiast podawać liczbę jako pewnik.
"""

from __future__ import annotations

from datetime import date

# Stawki potwierdzone w cenniku (stan na 2026-06-24).
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Brak potwierdzonej stawki — przybliżenie najbliższym poziomem cenowym.
ASSUMED: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),  # jak Opus 4.8 (poziom Opus)
}

# Nieznany model — zakładamy poziom Opus, żeby nie zaniżać szacunku.
FALLBACK: tuple[float, float] = (5.0, 25.0)

# Sonnet 5 — cena wprowadzająca obowiązuje do 31.08.2026, potem stawka standardowa.
SONNET_MODEL = "claude-sonnet-5"
_SONNET_INTRO_UNTIL = date(2026, 8, 31)
_SONNET_INTRO: tuple[float, float] = (2.0, 10.0)
_SONNET_STANDARD: tuple[float, float] = (3.0, 15.0)


def sonnet_rate(today: date | None = None) -> tuple[float, float]:
    """Stawka Sonnet 5 z uwzględnieniem ceny wprowadzającej."""
    return _SONNET_INTRO if (today or date.today()) <= _SONNET_INTRO_UNTIL else _SONNET_STANDARD


def rate_for(model: str, today: date | None = None) -> tuple[tuple[float, float], bool]:
    """Zwraca `(stawka, czy_założona)` dla modelu."""
    if model == SONNET_MODEL:
        return sonnet_rate(today), False
    if model in PRICES:
        return PRICES[model], False
    if model in ASSUMED:
        return ASSUMED[model], True
    return FALLBACK, True


def lean_cost(by_model: list[dict], rate_override: tuple[float, float] | None = None,
              today: date | None = None) -> tuple[float, list[str]]:
    """Koszt na API liczony TYLKO z realnego promptu i odpowiedzi (bez narzutu Claude Code).

    `by_model` to wiersze z `db.usage_stats()['by_model']`.
    Zwraca `(koszt_usd, modele_o_niepotwierdzonej_stawce)`.
    """
    total = 0.0
    assumed: list[str] = []
    for row in by_model:
        model = row.get("model") or ""
        if rate_override is not None:
            rate = rate_override
        else:
            rate, is_assumed = rate_for(model, today)
            if is_assumed and model not in assumed:
                assumed.append(model)
        total += row.get("est_input_tokens", 0) / 1e6 * rate[0]
        total += row.get("output_tokens", 0) / 1e6 * rate[1]
    return total, assumed
