"""דוח יומי: ספירות, PnL, פוזיציות תקועות והתראות."""
from datetime import datetime, timedelta, timezone

import pytest

from pmmb.daily import build_daily_report, write_daily_report
from pmmb.data.store import Store
from pmmb.models import Fill, PortfolioSnapshot, Position

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "daily.db")
    yield s
    s.close()


def _fill_cfg(store, ts_off_h, side, price, size, token="t1", cond="c1"):
    f = Fill(token_id=token, condition_id=cond, side=side, price=price, size=size,
             ts=NOW - timedelta(hours=ts_off_h))
    store.record_fill(f, "paper")
    return f


def test_empty_report(store):
    rep = build_daily_report(store, now=NOW, starting_cash=1000.0)
    assert rep.signals == 0 and rep.entries == 0 and rep.exits == 0
    assert rep.equity_start == 1000.0
    assert "אין סיגנלים" in rep.warnings[0]
    assert "דוח יומי" in rep.to_markdown()


def test_counts_and_pnl(store):
    store.upsert_position(Position(
        token_id="t1", condition_id="c1", direction="LONG", size=100, avg_price=0.50,
        opened_at=NOW - timedelta(hours=2), question="Will X happen?",
    ), "paper")
    _fill_cfg(store, 2, "BUY", 0.50, 100)
    _fill_cfg(store, 1, "SELL", 0.60, 100)
    store.record_fill(Fill(token_id="t1", condition_id="c1", side="SELL", price=0.60,
                           size=100, ts=NOW - timedelta(hours=1)), "paper", realized=10.0)
    store.close_position("t1", "יעד", realized_pnl=10.0)
    # הזזת closed_at לחלון
    store._conn.execute("UPDATE positions SET closed_at=?, question=? WHERE token_id='t1'",
                        (int((NOW - timedelta(hours=1)).timestamp()), "Will X happen?"))
    store.snapshot_equity(PortfolioSnapshot(cash=1010, equity=1010, exposure=0,
                                            open_positions=0, realized_pnl_today=10,
                                            peak_equity=1010, ts=NOW))

    rep = build_daily_report(store, now=NOW, hours=24)
    assert rep.entries == 1
    assert rep.exits == 2          # מכירה מלאה + רישום הרווח הממומש
    assert abs(rep.realized_pnl - 10.0) < 1e-9
    assert rep.wins == 1 and rep.losses == 0
    assert rep.win_rate == 100.0
    assert "Will X happen?" in rep.best_market
    assert abs(rep.equity_change_pct) < 100


def test_open_and_stale_positions(store):
    store.upsert_position(Position(
        token_id="t1", condition_id="c1", direction="LONG", size=100, avg_price=0.5,
        opened_at=NOW - timedelta(hours=10), question="fresh",
    ), "paper")
    store.upsert_position(Position(
        token_id="t2", condition_id="c2", direction="LONG", size=50, avg_price=0.4,
        opened_at=NOW - timedelta(hours=120), question="stale",
    ), "paper")

    rep = build_daily_report(store, now=NOW, planned_horizon_hours=48)
    assert len(rep.open_positions) == 2
    assert len(rep.stale_positions) == 1
    assert rep.stale_positions[0]["token_id"] == "t2"
    assert any("תקועות" in w or "אופק" in w for w in rep.warnings)


def test_equity_drop_warning(store):
    store.snapshot_equity(PortfolioSnapshot(cash=900, equity=900, exposure=0, open_positions=0,
                                            realized_pnl_today=-100, peak_equity=1000,
                                            ts=NOW - timedelta(hours=20)))
    store.snapshot_equity(PortfolioSnapshot(cash=800, equity=800, exposure=0, open_positions=0,
                                            realized_pnl_today=-200, peak_equity=1000, ts=NOW))
    rep = build_daily_report(store, now=NOW, hours=24)
    assert rep.equity_start == 900
    assert rep.equity_end == 800
    assert rep.equity_change_pct < -5
    assert any("ירד" in w for w in rep.warnings)


def test_write_daily_report(store, tmp_path):
    rep = build_daily_report(store, now=NOW)
    path = write_daily_report(rep, tmp_path)
    assert path.name == "daily-20261113.md"
    assert "דוח יומי" in path.read_text(encoding="utf-8")


def test_partial_exit_realized_is_not_lost(store):
    """רווח ממומש מיציאה חלקית חייב להיכנס ל-DB ולדוח."""
    from pmmb.execution.base import Portfolio
    from pmmb.models import Fill as F

    pf = Portfolio(cash=1000.0, mode="paper", store=store)
    pf.apply_fill(F(token_id="t9", condition_id="c9", side="BUY", price=0.50, size=100))
    pf.apply_fill(F(token_id="t9", condition_id="c9", side="SELL", price=0.60, size=40))

    row = store._conn.execute(
        "SELECT realized_pnl, size, closed_at FROM positions WHERE token_id='t9'"
    ).fetchone()
    assert row["size"] == 60            # עדיין פתוחה
    assert row["closed_at"] is None
    assert abs(row["realized_pnl"] - 4.0) < 1e-9   # 40 × 0.10

    rep = build_daily_report(store, now=datetime.now(tz=timezone.utc), hours=1)
    assert abs(rep.realized_pnl - 4.0) < 1e-9
