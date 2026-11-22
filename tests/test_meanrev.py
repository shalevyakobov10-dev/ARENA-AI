"""טסטים למנוע ה-mean-reversion ולמפעל המנועים."""
import pytest

from pmmb.config import Config, SignalConfig
from pmmb.signals import ENGINES, build_signal_engine
from pmmb.signals.meanrev import MeanReversionEngine
from series import flat_series, trending_series


def _move_series(level=0.60, delta=-0.12, n=120, tail=3):
    """
    מחיר יציב ואז מהלך חד בסוף הסדרה.
    delta שלילי = צניחה (dip), חיובי = זינוק (rally).
    """
    base = flat_series(level, n - tail, wiggle=0.002)
    return base + [round(level + (delta / tail) * (i + 1), 4) for i in range(tail)]


def _dip_series(n=120, level=0.60, dip=0.12, tail=3):
    return _move_series(level, -dip, n, tail)


def _strong_dip(cfg, z_max: float = 50.0):
    """רגישות גבוהה לטסטים מכניים; תקרת ה-z נבדקת בטסט נפרד."""
    cfg.signal.meanrev.z_entry = 1.2
    cfg.signal.meanrev.reversion_ratio = 0.5
    cfg.signal.meanrev.z_max = z_max
    cfg.signal.min_score = 0.3
    cfg.signal.min_edge = 0.0
    return cfg


def test_factory_returns_requested_engine(cfg):
    cfg.signal.engine = "momentum"
    assert isinstance(build_signal_engine(cfg.signal), ENGINES["momentum"])
    cfg.signal.engine = "meanrev"
    assert isinstance(build_signal_engine(cfg.signal), MeanReversionEngine)


def test_factory_rejects_unknown(cfg):
    cfg.signal.engine = "nope"
    with pytest.raises(ValueError):
        build_signal_engine(cfg.signal)


def test_config_validates_engine_name():
    c = SignalConfig()
    c.engine = "bogus"
    with pytest.raises(Exception):
        c.validate()


def test_sharp_dip_gives_long_on_yes(cfg_market):
    cfg, market = cfg_market
    _strong_dip(cfg)
    eng = MeanReversionEngine(cfg.signal)
    prices = _dip_series()
    sig = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "LONG"
    assert sig.token_id == market.yes_token_id
    assert sig.fair_price > sig.market_price      # מצפים לתיקון כלפי מעלה
    assert sig.edge > 0


def test_flat_market_no_signal(cfg_market):
    cfg, market = cfg_market
    _strong_dip(cfg)
    eng = MeanReversionEngine(cfg.signal)
    prices = flat_series(0.5, wiggle=0.001)
    sig = eng.evaluate(market, prices, market_price=0.5, spread=0.01)
    assert sig.direction == "FLAT"
    assert "עודף" in sig.reason


def test_sharp_rally_ignored_by_default(cfg_market):
    cfg, market = cfg_market
    _strong_dip(cfg)
    eng = MeanReversionEngine(cfg.signal)
    rally = _move_series(level=0.40, delta=+0.12)    # זינוק חד בסוף
    sig = eng.evaluate(market, rally, market_price=rally[-1], spread=0.01)
    assert sig.direction == "FLAT"
    assert "כבוי" in sig.reason


def test_short_allowed_when_enabled(cfg_market):
    cfg, market = cfg_market
    _strong_dip(cfg)
    cfg.signal.meanrev.allow_short = True
    eng = MeanReversionEngine(cfg.signal)
    rally = _move_series(level=0.40, delta=+0.12)
    sig = eng.evaluate(market, rally, market_price=rally[-1], spread=0.01)
    assert sig.direction == "SHORT"
    assert sig.token_id == market.no_token_id


def test_wide_spread_kills_edge(cfg_market):
    cfg, market = cfg_market
    _strong_dip(cfg)
    eng = MeanReversionEngine(cfg.signal)
    prices = _dip_series()
    tight = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    wide = eng.evaluate(market, prices, market_price=prices[-1], spread=0.40)
    assert wide.edge < tight.edge
    assert wide.direction == "FLAT"


def test_expected_bounce_capped_by_remaining_room(cfg_market):
    cfg, market = cfg_market
    _strong_dip(cfg)
    cfg.signal.meanrev.max_room_pct = 0.5
    eng = MeanReversionEngine(cfg.signal)
    # מחיר גבוה מאוד — מקום קטן עד 1
    prices = _move_series(level=0.95, delta=-0.06)
    sig = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    if sig.direction != "FLAT":
        assert sig.fair_price <= 0.95 + 0.5 * (1 - 0.95) + 1e-9


def test_not_enough_history(cfg, market):
    eng = MeanReversionEngine(cfg.signal)
    sig = eng.evaluate(market, [0.5] * 5, market_price=0.5, spread=0.01)
    assert sig.direction == "FLAT"
    assert "היסטוריה" in sig.reason


def test_dip_in_uptrend_still_requires_z(cfg_market):
    """במגמת עלייה מתונה ירידה קטנה אינה עודף חריג."""
    cfg, market = cfg_market
    _strong_dip(cfg)
    cfg.signal.meanrev.z_entry = 3.0
    eng = MeanReversionEngine(cfg.signal)
    prices = trending_series(0.30, 0.70, n=120, wiggle=0.002)
    sig = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "FLAT"


def test_extreme_move_is_rejected_as_news(cfg_market):
    """z קיצוני = ידיעה חדשה, לא עודף. לא תופסים סכין נופלת."""
    cfg, market = cfg_market
    _strong_dip(cfg, z_max=5.0)
    cfg.signal.min_score = 0.3
    cfg.signal.min_edge = 0.0
    eng = MeanReversionEngine(cfg.signal)
    prices = _move_series(level=0.36, delta=-0.28)     # קריסה של 28 סנט
    sig = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "FLAT"
    assert "קיצונית" in sig.reason


def test_trend_guard_blocks_dip_in_uptrend(cfg_market):
    """מסנן הקשר-מגמה: צניחה בתוך מגמת עלייה חזקה — מדלגים."""
    cfg, market = cfg_market
    _strong_dip(cfg)
    cfg.signal.meanrev.trend_guard = True
    cfg.signal.meanrev.trend_window = 40
    cfg.signal.meanrev.trend_max_norm = 3.0
    eng = MeanReversionEngine(cfg.signal)

    # מגמת עלייה ארוכה ואז צניחה קטנה בסוף
    up = trending_series(0.30, 0.70, n=117, wiggle=0.001)
    prices = up + [0.66, 0.64, 0.63]
    sig = eng.evaluate(market, prices, market_price=prices[-1], spread=0.01)
    assert sig.direction == "FLAT"
    assert "מגמת עלייה" in sig.reason

    # בלי המסנן — אותה סדרה כן מייצרת סיגנל
    cfg.signal.meanrev.trend_guard = False
    sig2 = MeanReversionEngine(cfg.signal).evaluate(
        market, prices, market_price=prices[-1], spread=0.01)
    assert sig2.direction == "LONG"


def test_trend_guard_default_off(cfg):
    assert cfg.signal.meanrev.trend_guard is False


# --- סיווג סקטורים + החרגה מהיקום ---
def test_sector_classification():
    from pmmb.sectors import classify

    assert classify("Will Bitcoin dip to $67,500 in November?") == "crypto"
    assert classify("NBA: Lakers vs. Celtics") == "sports"
    assert classify("Will the Fed decrease interest rates by 25 bps") == "macro"
    assert classify("Israel x Iran ceasefire continues through December?") == "geopolitics"
    assert classify("Will Pedro Sánchez be the next Prime Minister?") == "politics"
    assert classify("Something nobody classified") == "other"


def test_universe_excludes_sectors(cfg):
    import json

    from pmmb.data.gamma import MarketUniverse

    from datetime import datetime, timedelta, timezone

    end = (datetime.now(tz=timezone.utc) + timedelta(hours=48)).isoformat().replace("+00:00", "Z")

    class FakeGamma:
        def fetch_markets(self, **kw):
            def mk(question, slug):
                return {
                    "conditionId": slug, "question": question, "slug": slug,
                    "clobTokenIds": json.dumps([f"y-{slug}", f"n-{slug}"]),
                    "outcomes": json.dumps(["Yes", "No"]),
                    "outcomePrices": json.dumps(["0.5", "0.5"]),
                    "bestBid": 0.49, "bestAsk": 0.51,
                    "endDate": end,
                    "volume24hr": "100000", "liquidityNum": "50000",
                    "orderPriceMinTickSize": "0.01", "orderMinSize": "5",
                    "enableOrderBook": True, "acceptingOrders": True,
                    "closed": False, "archived": False, "events": [],
                }
            return [mk("Will Bitcoin reach $100k?", "btc-100k"),
                    mk("NBA: Lakers vs. Celtics", "nba-lal-bos")]

    cfg.universe.exclude_sectors = ["crypto"]
    uni = MarketUniverse(FakeGamma(), cfg.universe)
    markets = uni.scan()
    assert len(markets) == 1
    assert "Lakers" in markets[0].question
