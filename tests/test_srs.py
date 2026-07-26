import random
from datetime import datetime, timedelta, timezone

from app import srs


NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def test_base_weight_for_topics_without_errors():
    weights = srs.topic_weights([], ["tenses", "modals"], now=NOW)
    assert weights["tenses"] == srs.BASE_WEIGHT
    assert weights["modals"] == srs.BASE_WEIGHT


def test_errors_increase_weight():
    counts = [{"topic": "tenses", "count": 3, "last_seen": NOW.isoformat()}]
    weights = srs.topic_weights(counts, ["tenses", "modals"], now=NOW)
    assert weights["tenses"] > weights["modals"]


def test_recent_errors_weigh_more_than_old():
    recent = [{"topic": "tenses", "count": 2, "last_seen": NOW.isoformat()}]
    old_dt = NOW - timedelta(days=30)
    old = [{"topic": "tenses", "count": 2, "last_seen": old_dt.isoformat()}]
    w_recent = srs.topic_weights(recent, ["tenses"], now=NOW)["tenses"]
    w_old = srs.topic_weights(old, ["tenses"], now=NOW)["tenses"]
    assert w_recent > w_old


def test_choose_topic_returns_a_candidate():
    counts = [{"topic": "tenses", "count": 5, "last_seen": NOW.isoformat()}]
    rng = random.Random(42)
    chosen = srs.choose_topic(["tenses", "modals"], counts, now=NOW, rng=rng)
    assert chosen in {"tenses", "modals"}


def test_choose_topic_favours_error_heavy_topic_over_many_draws():
    counts = [{"topic": "tenses", "count": 10, "last_seen": NOW.isoformat()}]
    rng = random.Random(0)
    draws = [srs.choose_topic(["tenses", "modals"], counts, now=NOW, rng=rng) for _ in range(200)]
    assert draws.count("tenses") > draws.count("modals")


def test_choose_topic_empty_candidates_returns_none():
    assert srs.choose_topic([], [], now=NOW) is None
