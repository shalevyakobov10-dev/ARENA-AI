from pmmb.signals.momentum import MomentumEngine

from series import flat_series, trending_series


def _engine(cfg):
    return MomentumEngine(cfg.signal)


def test_uptrend_gives_long(cfg, market):
    eng = _engine(cfg)
    prices = trending_series(0.30, 0.75)
    sig = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "LONG"
    assert sig.score >= cfg.signal.min_score
    assert sig.edge > 0
    assert sig.token_id == market.yes_token_id
    assert 0 < sig.fair_price < 1


def test_downtrend_gives_short_on_no_token(cfg, market):
    eng = _engine(cfg)
    prices = trending_series(0.75, 0.30)
    sig = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "SHORT"
    assert sig.token_id == market.no_token_id
    assert abs(sig.market_price - (1 - prices[-1])) < 1e-9


def test_flat_market_has_no_signal(cfg, market):
    eng = _engine(cfg)
    prices = flat_series(0.5, wiggle=0.001)
    sig = eng.evaluate(market, prices, market_price=0.5, spread=0.01)
    assert sig.direction == "FLAT"


def test_not_enough_history(cfg, market):
    sig = _engine(cfg).evaluate(market, [0.5] * 5, market_price=0.5, spread=0.01)
    assert sig.direction == "FLAT"
    assert "היסטוריה" in sig.reason


def test_wide_spread_kills_edge(cfg, market):
    eng = _engine(cfg)
    prices = trending_series(0.30, 0.75)
    tight = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    wide = eng.evaluate(market, prices, market_price=prices[-1], spread=0.30)
    assert wide.edge < tight.edge
    assert wide.direction == "FLAT"


def test_short_disabled(cfg, market):
    cfg.signal.allow_short = False
    prices = trending_series(0.75, 0.30)
    sig = _engine(cfg).evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "FLAT"


def test_trend_filter_blocks_countertrend(cfg, market):
    """מומנטום חיובי חד בתוך מגמת ירידה ארוכה — פילטר המגמה חייב לחסום."""
    cfg.signal.trend_filter = True
    cfg.signal.min_score = 0.20      # מורידים את סף העוצמה כדי לבודד את הפילטר
    cfg.signal.min_edge = 0.0
    long_down = trending_series(0.80, 0.30, n=140, wiggle=0.002)
    bounce = trending_series(0.30, 0.36, n=7, wiggle=0.001)   # זינוק קצר
    prices = long_down + bounce

    sig = _engine(cfg).evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "FLAT"
    assert "מגמה" in sig.reason

    # אותו סיגנל בדיוק, אבל בלי הפילטר — היה נכנס
    cfg.signal.trend_filter = False
    sig2 = _engine(cfg).evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig2.direction == "LONG"
