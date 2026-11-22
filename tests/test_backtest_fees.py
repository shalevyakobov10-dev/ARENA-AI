"""העמלות בבקטסט: נגבות, מכבות סיגנלים חלשים, ולא נספרות פעמיים."""
from datetime import datetime, timedelta, timezone

from pmmb.backtest import Backtester
from pmmb.data.clob import Candle
from pmmb.fees import taker_fee
from pmmb.models import Market

# סדרה דטרמיניסטית: שוק נורמלי, צניחה של 9 סנט, התאוששות.
# 8 סיגנלים ללא עמלה, 3 בלבד כשהעמלה 5% — בדיוק ההשפעה שרוצים למדוד.
PX = [0.55, 0.549, 0.55, 0.56, 0.559, 0.559, 0.561, 0.553, 0.553, 0.556, 0.563, 0.553,
      0.548, 0.538, 0.545, 0.55, 0.539, 0.551, 0.562, 0.566, 0.569, 0.561, 0.549, 0.55,
      0.539, 0.532, 0.526, 0.515, 0.514, 0.513, 0.521, 0.521, 0.524, 0.524, 0.528, 0.527,
      0.522, 0.534, 0.546, 0.554, 0.559, 0.555, 0.549, 0.544, 0.534, 0.54, 0.538, 0.546,
      0.543, 0.554, 0.524, 0.484, 0.464, 0.464, 0.472, 0.48, 0.488, 0.496, 0.504, 0.512,
      0.52, 0.528, 0.536, 0.544]


class _BT(Backtester):
    """מנוע meanrev עם סף edge ריאלי (ה-fixture הגלובלי מיועד ל-momentum)."""

    def __init__(self, cfg):
        self.cfg = cfg
        cfg.signal.min_edge = 0.005
        from pmmb.signals import build_signal_engine
        self.engine = build_signal_engine(cfg.signal)


def _mk(fee_rate: float) -> Market:
    now = datetime.now(tz=timezone.utc)
    return Market(
        condition_id="c1", question="Will X happen?", slug="x",
        yes_token_id="y", no_token_id="n", yes_price=0.5, no_price=0.5,
        spread=0.01, volume_24h=50_000, liquidity=50_000,
        end_date=now + timedelta(days=30), taker_fee_rate=fee_rate,
    )


def _candles(prices, start=1_700_000_000, step=3600):
    return [Candle(start + i * step, p) for i, p in enumerate(prices)]


def _run(cfg, fee_rate):
    return _BT(cfg).run(_mk(fee_rate), _candles(PX), label="synthetic", spread=0.01)


def test_free_market_pays_nothing(cfg):
    assert _run(cfg, 0.0).fees_paid == 0.0


def test_fee_paying_market_is_charged(cfg):
    res = _run(cfg, 0.05)
    assert res.n_trades >= 1
    assert res.fees_paid > 0


def test_fees_suppress_marginal_signals(cfg):
    """עמלת 5% מייקרת פי ~2 סנט למניה ורוב הסיגנלים כבר לא משתלמים."""
    free, paid = _run(cfg, 0.0), _run(cfg, 0.05)
    assert paid.n_trades < free.n_trades


def test_fee_accounting_is_exact(cfg):
    """pnl = (יציאה−כניסה)×גודל − עמלת כניסה − עמלת יציאה, בלי כפל."""
    res = _run(cfg, 0.05)
    t = res.trades[0]
    entry_fee = taker_fee(t.size, t.entry, 0.05)
    exit_fee = taker_fee(t.size, t.exit, 0.05)
    expected = (t.exit - t.entry) * t.size - entry_fee - exit_fee
    assert abs(t.pnl - expected) < 1e-3
    # העסקה היחידה/ראשונה: סך העמלות = כניסה + יציאה שלה
    assert res.fees_paid >= entry_fee + exit_fee - 1e-3


def test_fee_curvature_peaks_at_half(cfg):
    assert taker_fee(100, 0.50, 0.05) > taker_fee(100, 0.90, 0.05)
    assert taker_fee(100, 0.50, 0.05) > taker_fee(100, 0.10, 0.05)
