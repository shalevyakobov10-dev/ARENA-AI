from pmmb.risk.sizing import (
    floor_to_tick,
    kelly_fraction,
    round_to_tick,
    size_for_trade,
    stop_and_target,
)


def test_kelly_bounds():
    assert kelly_fraction(0.6, 0.5) > 0
    assert kelly_fraction(0.4, 0.5) == 0.0
    assert kelly_fraction(0.9, 0.1) <= 1.0


def test_round_to_tick():
    assert round_to_tick(0.5034, 0.01) == 0.50
    assert round_to_tick(0.5060, 0.01) == 0.51
    assert floor_to_tick(0.5099, 0.01) == 0.50


def test_size_capped_by_position_limit(cfg):
    cfg.risk.max_position_pct = 0.10
    cfg.risk.kelly_fraction = 0.0
    shares, why = size_for_trade(
        equity=1000, price=0.5, fair_price=0.9, stop_price=0.4,
        cfg=cfg.risk, min_order_size=5,
    )
    # תקרת 10% = 100 USDC → 200 מניות
    assert shares == 200
    assert "תקרת" in why or "סיכון" in why
    assert shares * 0.5 <= 100 + 1e-6


def test_risk_based_sizing(cfg):
    cfg.risk.risk_per_trade_pct = 0.02   # 20 USDC
    cfg.risk.kelly_fraction = 0.0
    cfg.risk.max_position_pct = 1.0
    shares, why = size_for_trade(
        equity=1000, price=0.5, fair_price=0.9, stop_price=0.45,
        cfg=cfg.risk, min_order_size=5,
    )
    # מרחק לסטופ 0.05 → 20/0.05 = 400 מניות
    assert abs(shares - 400) < 1
    assert "סיכון" in why


def test_min_order_bump(cfg):
    cfg.risk.max_position_pct = 0.10
    cfg.risk.kelly_fraction = 0
    shares, why = size_for_trade(
        equity=1000, price=0.9, fair_price=0.95, stop_price=0.85,
        cfg=cfg.risk, min_order_size=5, lot_size=0.01,
    )
    # פוזיציה קטנה מדי → מקסימום תקרה או אפס, לא זבל
    assert shares >= 0
    if shares > 0:
        assert shares * 0.9 >= 5


def test_zero_equity_returns_zero(cfg):
    shares, _ = size_for_trade(equity=0, price=0.5, fair_price=0.6, stop_price=0.4,
                               cfg=cfg.risk, min_order_size=5)
    assert shares == 0


def test_stop_and_target_long():
    stop, target = stop_and_target(0.50, "LONG", 0.10, 0.20, 0.01)
    assert stop < 0.50 < target
    assert stop == 0.45 and target == 0.60


def test_stop_target_never_collapse_onto_entry():
    """מחיר נמוך + טיק גס: אסור שסטופ או יעד יהיו שווים למחיר הכניסה."""
    for price in (0.09, 0.10, 0.11, 0.50, 0.93):
        for tick in (0.01, 0.001):
            stop, target = stop_and_target(price, "LONG", 0.10, 0.05, tick)
            assert stop < price, f"stop {stop} !< price {price} (tick {tick})"
            assert target > price, f"target {target} !> price {price} (tick {tick})"
