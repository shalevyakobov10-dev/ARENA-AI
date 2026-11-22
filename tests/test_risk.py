from datetime import timedelta

from pmmb.models import PortfolioSnapshot, Position, Signal, utcnow
from pmmb.risk.manager import RiskManager


def _snap(**kw) -> PortfolioSnapshot:
    base = dict(cash=1000.0, equity=1000.0, exposure=0.0, open_positions=0,
                realized_pnl_today=0.0, peak_equity=1000.0)
    base.update(kw)
    return PortfolioSnapshot(**base)


def _sig(direction="LONG", edge=0.1) -> Signal:
    return Signal(condition_id="0xabc", token_id="yes-token", direction=direction,
                  score=0.7, fair_price=0.6, market_price=0.5, edge=edge, reason="t")


def test_entry_approved(cfg, market):
    rm = RiskManager(cfg)
    d = rm.evaluate_entry(_sig(), market, _snap(), price=0.5, tick=0.01, min_order_size=5)
    assert d.approved and d.size > 0 and d.notional > 0


def test_blocked_by_max_positions(cfg, market):
    rm = RiskManager(cfg)
    cfg.risk.max_open_positions = 3
    d = rm.evaluate_entry(_sig(), market, _snap(open_positions=3), price=0.5, tick=0.01, min_order_size=5)
    assert not d.approved and "פוזיציות" in d.reason


def test_blocked_by_exposure(cfg, market):
    rm = RiskManager(cfg)
    cfg.risk.max_total_exposure_pct = 0.4
    d = rm.evaluate_entry(_sig(), market, _snap(exposure=400.0), price=0.5, tick=0.01, min_order_size=5)
    assert not d.approved and "חשיפה" in d.reason


def test_daily_loss_halts_bot(cfg, market):
    rm = RiskManager(cfg)
    cfg.risk.max_daily_loss_pct = 0.05
    d = rm.evaluate_entry(_sig(), market, _snap(realized_pnl_today=-60.0),
                          price=0.5, tick=0.01, min_order_size=5)
    assert not d.approved
    assert rm.halted and "יומי" in rm.halt_reason


def test_drawdown_halts_bot(cfg, market):
    rm = RiskManager(cfg)
    cfg.risk.max_drawdown_pct = 0.10
    d = rm.evaluate_entry(_sig(), market, _snap(equity=800.0, peak_equity=1000.0),
                          price=0.5, tick=0.01, min_order_size=5)
    assert not d.approved and rm.halted


def test_halted_blocks_everything(cfg, market):
    rm = RiskManager(cfg)
    rm.halt("בדיקה")
    d = rm.evaluate_entry(_sig(), market, _snap(), price=0.5, tick=0.01, min_order_size=5)
    assert not d.approved and "עצור" in d.reason


def test_cooldown(cfg, market):
    rm = RiskManager(cfg)
    cfg.risk.cooldown_minutes = 30
    rm.start_cooldown("0xabc")
    d = rm.evaluate_entry(_sig(), market, _snap(), price=0.5, tick=0.01, min_order_size=5)
    assert not d.approved and "cooldown" in d.reason


def test_no_cash(cfg, market):
    rm = RiskManager(cfg)
    d = rm.evaluate_entry(_sig(), market, _snap(cash=1.0, equity=1000.0),
                          price=0.5, tick=0.01, min_order_size=5)
    assert not d.approved


def _pos(price=0.5, hours_ago=0.0, stop=None, target=None) -> Position:
    return Position(token_id="yes-token", condition_id="0xabc", direction="LONG",
                    size=100, avg_price=price, opened_at=utcnow() - timedelta(hours=hours_ago),
                    stop_price=stop, target_price=target)


def test_exit_stop(cfg):
    rm = RiskManager(cfg)
    assert "סטופ" in (rm.evaluate_exit(_pos(stop=0.45), 0.44) or "")


def test_exit_target(cfg):
    rm = RiskManager(cfg)
    assert "יעד" in (rm.evaluate_exit(_pos(target=0.60), 0.61) or "")


def test_exit_time_stop(cfg):
    rm = RiskManager(cfg)
    cfg.signal.exit.time_stop_hours = 10
    assert "time stop" in (rm.evaluate_exit(_pos(hours_ago=11), 0.5) or "")


def test_exit_on_flip(cfg):
    rm = RiskManager(cfg)
    assert "התהפך" in (rm.evaluate_exit(_pos(), 0.5, signal_flipped=True) or "")


def test_no_exit_when_nothing_triggers(cfg):
    rm = RiskManager(cfg)
    assert rm.evaluate_exit(_pos(stop=0.40, target=0.70), 0.52) is None
