"""Testy reguły serii: opuszczony dzień można odrobić, płacąc zaległy cel."""

from datetime import date, timedelta

from app import streak


TODAY = date(2026, 9, 6)
GOAL = 5


def days(**by_offset: int) -> dict[str, int]:
    """Buduje mapę 'YYYY-MM-DD' -> liczba błędów; klucz `d0` to dziś, `d3` to 3 dni temu."""
    return {
        (TODAY - timedelta(days=int(key[1:]))).isoformat(): count
        for key, count in by_offset.items()
    }


def test_no_reviews_means_no_streak():
    st = streak.state({}, GOAL, TODAY)
    assert st["streak"] == 0
    assert st["required_today"] == GOAL
    assert st["overdue_days"] == 0
    assert st["at_risk"] is False


def test_goal_zero_returns_no_streak():
    assert streak.state(days(d0=9), 0, TODAY)["streak"] == 0


def test_counts_consecutive_met_days():
    st = streak.state(days(d0=GOAL, d1=GOAL, d2=GOAL + 3), GOAL, TODAY)
    assert st["streak"] == 3
    assert st["at_risk"] is False


def test_today_unfinished_keeps_yesterdays_streak_without_risk():
    """Dotychczasowy grace: dopóki trwa dziś, seria kończąca się wczoraj stoi."""
    st = streak.state(days(d1=GOAL, d2=GOAL), GOAL, TODAY)
    assert st["streak"] == 2
    assert st["required_today"] == GOAL
    assert st["overdue_days"] == 0
    assert st["at_risk"] is False


def test_missed_yesterday_puts_streak_at_risk_with_doubled_requirement():
    st = streak.state(days(d2=GOAL, d3=GOAL), GOAL, TODAY)
    assert st["streak"] == 2
    assert st["required_today"] == 2 * GOAL
    assert st["overdue_days"] == 1
    assert st["at_risk"] is True


def test_paying_the_debt_keeps_the_streak_and_adds_one_day():
    st = streak.state(days(d0=2 * GOAL, d2=GOAL, d3=GOAL), GOAL, TODAY)
    assert st["streak"] == 3          # odrobiony dzień NIE wchodzi do licznika
    assert st["at_risk"] is False


def test_two_missed_days_require_triple_goal():
    st = streak.state(days(d3=GOAL, d4=GOAL), GOAL, TODAY)
    assert st["required_today"] == 3 * GOAL
    assert st["overdue_days"] == 2
    assert st["streak"] == 2
    assert st["at_risk"] is True

    paid = streak.state(days(d0=3 * GOAL, d3=GOAL, d4=GOAL), GOAL, TODAY)
    assert paid["streak"] == 3
    assert paid["at_risk"] is False


def test_three_missed_days_break_the_streak_for_good():
    st = streak.state(days(d4=GOAL, d5=GOAL), GOAL, TODAY)
    assert st["streak"] == 0
    assert st["required_today"] == GOAL     # dług przepadł, zaczynasz od nowa
    assert st["overdue_days"] == 0
    assert st["at_risk"] is False

    # Nawet ogromny dzisiejszy wynik nie wskrzesza starej serii.
    revived = streak.state(days(d0=99, d4=GOAL, d5=GOAL), GOAL, TODAY)
    assert revived["streak"] == 1


def test_partial_payment_does_not_clear_the_debt():
    """Cel dzienny bez zaległości: seria wciąż zagrożona, bo dług jest wszystko-albo-nic."""
    st = streak.state(days(d0=GOAL, d2=GOAL, d3=GOAL), GOAL, TODAY)
    assert st["streak"] == 2
    assert st["required_today"] == 2 * GOAL
    assert st["at_risk"] is True


def test_unpaid_debt_leaves_only_the_day_that_met_the_plain_goal():
    """Nazajutrz po nieodrobionym długu stara seria przepada, zostaje sam ten dzień."""
    st = streak.state(days(d1=GOAL, d3=GOAL, d4=GOAL), GOAL, TODAY)
    assert st["streak"] == 1
    # Przepadły dług nie obciąża dzisiejszego dnia — dziś zwykły cel.
    assert st["overdue_days"] == 0
    assert st["required_today"] == GOAL


def test_repaid_gap_in_the_past_keeps_older_days_in_the_streak():
    history = days(d0=GOAL, d1=GOAL, d2=2 * GOAL, d4=GOAL, d5=GOAL)  # d3 opuszczony, d2 spłacił
    assert streak.state(history, GOAL, TODAY)["streak"] == 5


def test_streak_of_one_survives_a_missed_day():
    """Gdy przed luką nie ma nic, dzisiejszy zaliczony cel wciąż daje serię 1."""
    st = streak.state(days(d0=GOAL), GOAL, TODAY)
    assert st["streak"] == 1
