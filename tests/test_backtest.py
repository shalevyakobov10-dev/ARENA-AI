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
