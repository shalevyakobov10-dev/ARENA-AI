"""מודל העמלות: הנוסחה, טבלת הקטגוריות, ונקודת האיזון."""
import pytest

from pmmb.fees import (breakeven_move, estimate, rate_for, round_trip_fee_per_share,
                       taker_fee)


def test_matches_official_table():
    """הטבלה הרשמית: 100 מניות ב-0.50 @0.05 ⇒ 1.25 USDC; ב-0.10 ⇒ 0.45."""
    assert taker_fee(100, 0.50, 0.05) == pytest.approx(1.25)
    assert taker_fee(100, 0.10, 0.05) == pytest.approx(0.45)
    assert taker_fee(100, 0.99, 0.05) == pytest.approx(0.05, abs=0.01)


def test_symmetric_around_half():
    assert taker_fee(100, 0.30, 0.05) == pytest.approx(taker_fee(100, 0.70, 0.05))


def test_zero_rate_or_zero_shares():
    assert taker_fee(100, 0.5, 0.0) == 0.0
    assert taker_fee(0, 0.5, 0.05) == 0.0


def test_geopolitics_is_free():
    assert rate_for(sector="geopolitics", question="Will Israel and Iran sign a ceasefire?").rate == 0.0


def test_sports_and_elections_are_expensive():
    assert rate_for(sector="sports", question="Lakers vs Celtics").rate == pytest.approx(0.05)
    assert rate_for(sector="politics", question="Who will win the 2028 presidential election?").rate == pytest.approx(0.05)


def test_ordinary_politics_is_cheap():
    assert rate_for(sector="politics", question="Will the Senate pass the bill?").rate == pytest.approx(0.01)


def test_gamma_schedule_wins_over_table():
    """אם השרת מדווח rate — הוא האמת, לא הטבלה שלנו."""
    e = rate_for(sector="sports", question="x", gamma_rate=0.0, fees_enabled=True)
    assert e.rate == 0.0 and e.source == "gamma"


def test_fees_disabled_flag():
    assert rate_for(sector="sports", question="x", gamma_rate=0.05, fees_enabled=False).rate == 0.0


def test_maker_pays_nothing():
    assert estimate(0.5, rate=0.05, maker=True).per_share == 0.0


def test_breakeven_includes_spread_and_fees():
    free = breakeven_move(0.5, 0.0, spread=0.01)
    costly = breakeven_move(0.5, 0.05, spread=0.01)
    assert free == pytest.approx(0.01)
    assert costly == pytest.approx(0.01 + round_trip_fee_per_share(0.5, 0.05))
    assert costly > 3 * free          # עמלת 5% באמצע הטווח מייקרת פי 3.5


def test_fee_vs_edge_ordering():
    """סדר העדיפויות הכלכלי: geopolitics < crypto/macro < sports/elections."""
    g = breakeven_move(0.5, rate_for(sector="geopolitics").rate, 0.01)
    c = breakeven_move(0.5, rate_for(sector="crypto").rate, 0.01)
    s = breakeven_move(0.5, rate_for(sector="sports").rate, 0.01)
    assert g < c < s
