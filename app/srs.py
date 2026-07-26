"""Prosty spaced repetition: dobór tematu kolejnego zadania ważony błędami ucznia.

Zasada: każdy temat możliwy dla danego typu ćwiczenia ma bazową wagę (eksploracja),
powiększaną o liczbę popełnionych błędów i świeżość tych błędów (świeższe ważą więcej).
Dzięki temu aplikacja częściej wraca do słabych i niedawno mylonych zagadnień,
nie porzucając zupełnie pozostałych.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Optional

BASE_WEIGHT = 1.0          # waga eksploracji (każdy temat ma szansę)
ERROR_WEIGHT = 2.0         # ile dodaje jeden zalogowany błąd
RECENCY_WINDOW_DAYS = 14.0  # w tym oknie świeżość dokłada bonus


def _parse_dt(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _recency_factor(last_seen: Optional[str], now: datetime) -> float:
    """1.0 + bonus (0..1) malejący liniowo w oknie RECENCY_WINDOW_DAYS."""
    dt = _parse_dt(last_seen) if last_seen else None
    if dt is None:
        return 1.0
    days = (now - dt).total_seconds() / 86400.0
    if days <= 0:
        return 2.0
    if days >= RECENCY_WINDOW_DAYS:
        return 1.0
    return 1.0 + (RECENCY_WINDOW_DAYS - days) / RECENCY_WINDOW_DAYS


def topic_weights(error_counts: list[dict], candidate_topics: list[str],
                  now: Optional[datetime] = None) -> dict[str, float]:
    """Zwraca wagę doboru dla każdego kandydującego tematu."""
    now = now or datetime.now(timezone.utc)
    by_topic = {row["topic"]: row for row in error_counts}
    weights: dict[str, float] = {}
    for topic in candidate_topics:
        weight = BASE_WEIGHT
        row = by_topic.get(topic)
        if row:
            count = float(row.get("count", 0))
            weight += ERROR_WEIGHT * count * _recency_factor(row.get("last_seen"), now)
        weights[topic] = weight
    return weights


def choose_topic(candidate_topics: list[str], error_counts: list[dict],
                 now: Optional[datetime] = None,
                 rng: Optional[random.Random] = None) -> Optional[str]:
    """Losuje temat proporcjonalnie do wag (świeże/częste błędy = wyższa szansa)."""
    if not candidate_topics:
        return None
    weights = topic_weights(error_counts, candidate_topics, now)
    rng = rng or random
    population = list(weights.keys())
    return rng.choices(population, weights=[weights[t] for t in population], k=1)[0]
