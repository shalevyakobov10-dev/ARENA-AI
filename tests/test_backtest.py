import pytest

from pmmb.backtest import Backtester
from pmmb.data.clob import Candle
from pmmb.signals.momentum import MomentumEngine


def _candles(prices, start=1_700_000_000, step=300):
    return [Candle(start + i * step, p) for i, p in enumerate(prices)]


def _series(start, end, n, wiggle=0.01):
    out = []
    for i in range(n):
        base = start + (end - start) * i / (n - 1)
        out.append(round(base + (wiggle if i % 3 == 0 else -wiggle / 2), 4))
    return out


class _NoNet:
    """עוקף את הבנאי כדי לא לפתוח רשת בטסט."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.engine = MomentumEngine(cfg.signal)


def test_backtest_produces_trades(cfg, market):
    bt = _NoNet(cfg)
    candles = _candles(_series(0.30, 0.70, 200))
    res = Backtester.run(bt, market, candles, label="synthetic-up", spread=0.01)
    assert res.candles == 200
    assert res.n_trades >= 0
    if res.n_trades:
        assert all(t.size > 0 for t in res.trades)
        assert res.profit_factor >= 0


def test_backtest_flat_market_no_trades(cfg, market):
    bt = _NoNet(cfg)
    candles = _candles([0.5 + (0.001 if i % 2 else -0.001) for i in range(200)])
    res = Backtester.run(bt, market, candles, label="flat", spread=0.01)
    assert res.n_trades == 0
    assert res.ending_equity == pytest.approx(res.starting_equity)


def test_backtest_summary_keys(cfg, market):
    bt = _NoNet(cfg)
    res = Backtester.run(bt, market, _candles(_series(0.4, 0.6, 150)), spread=0.01)
    s = res.summary()
    for key in ("label", "trades", "win_rate", "total_return_pct", "max_drawdown_pct", "sharpe"):
        assert key in s
    assert s["max_drawdown_pct"] >= 0


def test_backtest_never_goes_below_zero_cash(cfg, market):
    bt = _NoNet(cfg)
    res = Backtester.run(bt, market, _candles(_series(0.5, 0.1, 150)), spread=0.02,
                         starting_cash=100.0)
    assert res.ending_equity > 0


def test_backtest_charges_half_spread_on_taker(cfg, market):
    """בבקטסט טאקר משלם חצי ספרד בכניסה וחצי ספרד ביציאה (תואם PaperBroker)."""
    bt = _NoNet(cfg)
    candles = _candles(_series(0.30, 0.70, 200))
    spread = 0.04
    res = Backtester.run(bt, market, candles, label="spread-check", spread=spread)
    by_ts = {c.ts: c.price for c in candles}
    for t in res.trades:
        assert t.entry >= by_ts[t.entry_ts] + spread / 2 - 1e-6
        if t.reason != "סוף התקופה":
            assert t.exit <= by_ts[t.exit_ts] - spread / 2 + 1e-6


def test_portfolio_backtest_enforces_event_and_position_caps(cfg, market):
    """סימולציית תיק משותף אוכפת מקסימום פוזיציה אחת לכל event_id ותקרת חשיפה."""
    from pmmb.models import Market
    from pmmb.signals.meanrev import MeanReversionEngine

    px = [0.55, 0.549, 0.55, 0.56, 0.559, 0.559, 0.561, 0.553, 0.553, 0.556, 0.563, 0.553,
          0.548, 0.538, 0.545, 0.55, 0.539, 0.551, 0.562, 0.566, 0.569, 0.561, 0.549, 0.55,
          0.539, 0.532, 0.526, 0.515, 0.514, 0.513, 0.521, 0.521, 0.524, 0.524, 0.528, 0.527,
          0.522, 0.534, 0.546, 0.554, 0.559, 0.555, 0.549, 0.544, 0.534, 0.54, 0.538, 0.546,
          0.543, 0.554, 0.524, 0.484, 0.464, 0.464, 0.472, 0.48, 0.488, 0.496, 0.504, 0.512,
          0.52, 0.528, 0.536, 0.544]

    cfg.signal.engine = "meanrev"
    cfg.signal.min_edge = 0.005
    cfg.risk.max_open_positions = 5
    bt = _NoNet(cfg)
    bt.engine = MeanReversionEngine(cfg.signal)

    m1 = Market(
        condition_id="c1", question="Candidate A", slug="cand-a",
        yes_token_id="y1", no_token_id="n1", yes_price=0.5, no_price=0.5,
        spread=0.01, volume_24h=50_000, liquidity=50_000, end_date=market.end_date,
        event_id="ev-shared",
    )
    m2 = Market(
        condition_id="c2", question="Candidate B", slug="cand-b",
        yes_token_id="y2", no_token_id="n2", yes_price=0.5, no_price=0.5,
        spread=0.01, volume_24h=50_000, liquidity=50_000, end_date=market.end_date,
        event_id="ev-shared",
    )
    candles = _candles(px, step=3600)

    cfg.risk.max_positions_per_event = 1
    res_capped = Backtester.run_portfolio(bt, [(m1, candles), (m2, candles)], spread=0.01)
    assert res_capped.taker_fills >= 1

    cfg.risk.max_positions_per_event = 2
    res_uncapped = Backtester.run_portfolio(bt, [(m1, candles), (m2, candles)], spread=0.01)
    assert res_uncapped.taker_fills == res_capped.taker_fills * 2


def test_backtest_enforces_price_band(cfg, market):
    """הבקטסט אוכף price_band של היקום בכניסה בדיוק כמו המנוע החי."""
    cfg.universe.price_band = [0.20, 0.80]
    bt = _NoNet(cfg)
    # סדרה עולה בטווח 0.05..0.18 (כולה מתחת ל-price_band[0]=0.20)
    candles = _candles(_series(0.05, 0.18, 160))
    res = Backtester.run(bt, market, candles, label="below-band", spread=0.01)
    assert res.n_trades == 0



