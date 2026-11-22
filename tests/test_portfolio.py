import pytest

from pmmb.execution.base import Portfolio
from pmmb.models import Fill


def test_buy_opens_position_and_reduces_cash():
    pf = Portfolio(1000.0)
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="BUY", price=0.5, size=100, fee=0.1))
    assert abs(pf.cash - (1000 - 50 - 0.1)) < 1e-9
    assert pf.positions["t1"].size == 100
    assert pf.positions["t1"].avg_price == 0.5


def test_average_price_on_scale_in():
    pf = Portfolio(1000.0)
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="BUY", price=0.50, size=100))
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="BUY", price=0.60, size=100))
    assert abs(pf.positions["t1"].avg_price - 0.55) < 1e-9
    assert pf.positions["t1"].size == 200


def test_sell_realizes_pnl_and_closes():
    pf = Portfolio(1000.0)
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="BUY", price=0.50, size=100))
    realized = pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="SELL", price=0.60, size=100))
    assert abs(realized - 10.0) < 1e-9
    assert "t1" not in pf.positions
    assert pf.realized_pnl == pytest.approx(10.0)
    assert pf.cash == pytest.approx(1000.0 + 10.0)


def test_partial_sell_keeps_position():
    pf = Portfolio(1000.0)
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="BUY", price=0.50, size=100))
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="SELL", price=0.55, size=40))
    assert pf.positions["t1"].size == 60
    assert pf.realized_pnl == pytest.approx(2.0)


def test_equity_uses_marks():
    pf = Portfolio(1000.0)
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="BUY", price=0.50, size=100))
    assert pf.equity({"t1": 0.70}) == pytest.approx(pf.cash + 70)
    snap = pf.snapshot({"t1": 0.70})
    assert snap.open_positions == 1
    assert snap.exposure == pytest.approx(70.0)


def test_sell_without_position_is_safe():
    pf = Portfolio(1000.0)
    realized = pf.apply_fill(Fill(token_id="ghost", condition_id="c", side="SELL", price=0.5, size=10))
    assert realized == 0.0
    assert pf.cash > 1000.0  # המזומן מתעדכן, אין קריסה


def test_drawdown_calculation():
    pf = Portfolio(1000.0)
    pf.apply_fill(Fill(token_id="t1", condition_id="c1", side="BUY", price=0.5, size=100))
    snap = pf.snapshot({"t1": 0.2})
    assert snap.drawdown_pct > 0
    assert 0 <= snap.drawdown_pct <= 1
