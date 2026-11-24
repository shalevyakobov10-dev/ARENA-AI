"""Tests for the cross-arm portfolio risk guard."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from pmmb.config import Config
from pmmb.data.store import Store
from pmmb.runtime import clear_halt, read_halt
from pmmb.unified_risk import (
    build_unified_portfolio_snapshot,
    evaluate_unified_entry,
    unified_entry_lock,
)


@pytest.fixture
def shared_store(tmp_path, cfg, monkeypatch):
    cfg.data.db_path = str(tmp_path / "shared-risk.db")
    # Each test gets an isolated runtime state directory so a deliberate
    # daily-loss halt cannot leak into unrelated engine tests.
    state_dir = tmp_path / "runtime-state"
    monkeypatch.setenv("PMMB_STATE_DIR", str(state_dir))
    store = Store(cfg.data.db_path)
    yield store
    store.close()


def _seed_poly_position(store: Store, token: str, *, size: float, avg_price: float) -> None:
    ts = int(time.time())
    with store.tx() as conn:
        conn.execute(
            """INSERT INTO positions
               (token_id, condition_id, mode, direction, size, avg_price, opened_at)
               VALUES (?, ?, 'paper', 'LONG', ?, ?, ?)""",
            (token, f"condition-{token}", size, avg_price, ts),
        )
        conn.execute(
            "INSERT INTO books(token_id, ts, mid, best_bid) VALUES (?, ?, ?, ?)",
            (token, ts, avg_price, avg_price),
        )


def _seed_perp_position(store: Store, symbol: str, *, margin: float) -> None:
    ts = int(time.time())
    with store.tx() as conn:
        conn.execute(
            """INSERT INTO perp_positions
               (symbol, exchange, mode, side, size, entry_price, notional, leverage,
                margin_used, liquidation_price, stop_price, target_price,
                highest_price, lowest_price, fees_paid, opened_at)
               VALUES (?, 'okx', 'paper', 'LONG', 0.01, 100.0, ?, 10.0,
                       ?, 90.0, 95.0, 110.0, 100.0, 100.0, 0, ?)""",
            (symbol, margin * 10.0, margin, ts),
        )
        conn.execute(
            """INSERT INTO perp_intel(symbol, exchange, price, mark_price, updated_at)
               VALUES (?, 'okx', 100.0, 100.0, ?)""",
            (symbol, ts),
        )


def test_snapshot_aggregates_polymarket_cost_basis_and_perps_margin(shared_store, cfg):
    _seed_poly_position(shared_store, "poly-a", size=100.0, avg_price=0.5)
    _seed_perp_position(shared_store, "BTC", margin=200.0)

    snapshot = build_unified_portfolio_snapshot(shared_store, cfg)

    assert snapshot.starting_capital == pytest.approx(2000.0)
    assert snapshot.polymarket_committed == pytest.approx(50.0)
    assert snapshot.perps_margin_used == pytest.approx(200.0)
    assert snapshot.committed_capital == pytest.approx(250.0)
    assert snapshot.open_positions == 2


def test_shared_capital_gate_combines_both_arms(shared_store, cfg):
    cfg.portfolio_risk.max_capital_utilization_pct = 0.50
    _seed_poly_position(shared_store, "poly-a", size=1400.0, avg_price=0.5)  # $700
    _seed_perp_position(shared_store, "BTC", margin=200.0)

    denied = evaluate_unified_entry(
        shared_store, cfg, arm="perps", proposed_capital=101.0
    )
    allowed = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=100.0
    )

    assert denied.approved is False
    assert "תקרת הקצאת הון משותפת" in denied.reason
    assert denied.snapshot.committed_capital == pytest.approx(900.0)
    assert allowed.approved is True
    assert allowed.snapshot.committed_capital + allowed.proposed_capital == pytest.approx(1000.0)


def test_shared_open_position_limit_counts_both_arms(shared_store, cfg):
    cfg.portfolio_risk.max_open_positions = 3
    _seed_poly_position(shared_store, "poly-a", size=10.0, avg_price=0.5)
    _seed_poly_position(shared_store, "poly-b", size=10.0, avg_price=0.5)
    _seed_perp_position(shared_store, "BTC", margin=10.0)

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="perps", proposed_capital=5.0
    )

    assert not decision.approved
    assert "תקרת פוזיציות משותפת" in decision.reason
    assert decision.snapshot.open_positions == 3


def test_combined_daily_realized_loss_persists_global_halt(shared_store, cfg):
    clear_halt()
    now = datetime.now(tz=timezone.utc)
    ts = int(now.timestamp())
    with shared_store.tx() as conn:
        conn.execute(
            """INSERT INTO fills
               (ts, mode, token_id, condition_id, side, price, size, fee, realized)
               VALUES (?, 'paper', 'poly-token', 'poly-condition', 'SELL', 0.4, 10, 0, -55)""",
            (ts,),
        )
        conn.execute(
            """INSERT INTO perp_fills
               (ts, mode, symbol, exchange, side, action, price, size, notional,
                leverage, margin_delta, fee, funding, realized)
               VALUES (?, 'paper', 'BTC', 'okx', 'LONG', 'CLOSE', 100, 0.01,
                       1, 10, 0, 0, 0, -50)""",
            (ts,),
        )

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=10.0, now=now
    )

    assert not decision.approved
    assert "הפסד ממומש משולב" in decision.reason
    flag = read_halt()
    assert flag is not None
    assert flag.source == "unified-risk"


def test_shared_guard_fails_closed_when_any_enabled_arm_is_not_paper(shared_store, cfg):
    cfg.perps.mode = "live"

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="perps", proposed_capital=10.0
    )

    assert not decision.approved
    assert "מוגבל ל-Paper" in decision.reason


def test_shared_entry_lock_serializes_threads(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    first_inside = threading.Event()
    release_first = threading.Event()
    second_inside = threading.Event()

    def first_worker():
        with unified_entry_lock(cfg):
            first_inside.set()
            assert release_first.wait(2.0)

    def second_worker():
        with unified_entry_lock(cfg):
            second_inside.set()

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    assert first_inside.wait(1.0)
    second.start()
    time.sleep(0.08)
    assert not second_inside.is_set()
    release_first.set()
    assert second_inside.wait(1.0)
    first.join(timeout=1.0)
    second.join(timeout=1.0)
    assert not first.is_alive()
    assert not second.is_alive()

def test_portfolio_risk_limits_reject_unsafe_values(cfg):
    from pmmb.config import ConfigError

    cfg.portfolio_risk.max_capital_utilization_pct = 1.0
    with pytest.raises(ConfigError):
        cfg.portfolio_risk.validate()


def test_disabled_perps_arm_still_counts_existing_paper_positions(shared_store, cfg):
    cfg.perps.enabled = False
    _seed_perp_position(shared_store, "BTC", margin=200.0)

    snapshot = build_unified_portfolio_snapshot(shared_store, cfg)

    assert snapshot.starting_capital == pytest.approx(2000.0)
    assert snapshot.perps_margin_used == pytest.approx(200.0)
    assert snapshot.open_positions == 1

    cfg.portfolio_risk.max_open_positions = 1
    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=10.0
    )
    assert not decision.approved
    assert "תקרת פוזיציות משותפת" in decision.reason


def test_daily_realized_snapshot_includes_unbooked_poly_and_open_perps_entry_fees(
    shared_store, cfg
):
    now = datetime.now(tz=timezone.utc)
    ts = int(now.timestamp())
    with shared_store.tx() as conn:
        conn.execute(
            """INSERT INTO fills
               (ts, mode, token_id, condition_id, side, price, size, fee, realized)
               VALUES (?, 'paper', 'poly-buy', 'poly-condition', 'BUY', 0.5, 10, 2.0, 0)""",
            (ts,),
        )
        conn.execute(
            """INSERT INTO perp_positions
               (symbol, exchange, mode, side, size, entry_price, notional, leverage,
                margin_used, liquidation_price, stop_price, target_price,
                highest_price, lowest_price, fees_paid, opened_at)
               VALUES ('ETH', 'okx', 'paper', 'LONG', 1, 100, 1000, 10,
                       100, 90, 95, 110, 100, 100, 3.0, ?)""",
            (ts,),
        )
        conn.execute(
            """INSERT INTO perp_fills
               (ts, mode, symbol, exchange, side, action, price, size, notional,
                leverage, margin_delta, fee, funding, realized)
               VALUES (?, 'paper', 'ETH', 'okx', 'LONG', 'OPEN', 100, 1,
                       1000, 10, -100, 3.0, 0, 0)""",
            (ts,),
        )

    snapshot = build_unified_portfolio_snapshot(shared_store, cfg, now=now)

    assert snapshot.polymarket_realized_today == pytest.approx(-2.0)
    assert snapshot.perps_realized_today == pytest.approx(-3.0)
    assert snapshot.realized_today == pytest.approx(-5.0)


def test_corrupt_global_halt_file_fails_closed(shared_store, cfg, tmp_path, monkeypatch):
    import os

    state_dir = tmp_path / "state-corrupt"
    state_dir.mkdir()
    (state_dir / "halt.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("PMMB_STATE_DIR", str(state_dir))

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=10.0
    )

    assert not decision.approved
    assert "קובץ עצירת החירום" in decision.reason


def test_invalid_capital_value_fails_closed(shared_store, cfg):
    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital="not-a-number"
    )
    assert not decision.approved
    assert "סכום הקצאת הון לא תקין" in decision.reason


def _process_lock_worker(state_dir, entered, release):
    import os
    os.environ["PMMB_STATE_DIR"] = str(state_dir)
    with unified_entry_lock(Config()):
        entered.set()
        release.wait(5.0)


def test_shared_entry_lock_serializes_separate_processes(cfg, tmp_path, monkeypatch):
    import multiprocessing

    state_dir = tmp_path / "state-process"
    monkeypatch.setenv("PMMB_STATE_DIR", str(state_dir))
    ctx = multiprocessing.get_context("spawn")
    child_entered = ctx.Event()
    release_child = ctx.Event()

    with unified_entry_lock(cfg):
        child = ctx.Process(
            target=_process_lock_worker,
            args=(str(state_dir), child_entered, release_child),
        )
        child.start()
        time.sleep(0.15)
        assert not child_entered.is_set()

    assert child_entered.wait(2.0)
    release_child.set()
    child.join(timeout=2.0)
    assert child.exitcode == 0


def test_disabled_perps_arm_cannot_open_new_positions(shared_store, cfg):
    cfg.perps.enabled = False

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="perps", proposed_capital=10.0
    )

    assert not decision.approved
    assert "PERPS מושבתת" in decision.reason


def test_missing_global_halt_file_does_not_block(shared_store, cfg, tmp_path, monkeypatch):
    state_dir = tmp_path / "state-no-halt"
    state_dir.mkdir()
    monkeypatch.setenv("PMMB_STATE_DIR", str(state_dir))

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=10.0
    )

    assert decision.approved


def test_snapshot_marks_open_positions_across_both_arms(shared_store, cfg):
    _seed_poly_position(shared_store, "poly-mtm", size=100.0, avg_price=0.5)
    _seed_perp_position(shared_store, "BTC", margin=100.0)
    now_ts = int(time.time())
    with shared_store.tx() as conn:
        conn.execute(
            "UPDATE books SET mid=0.4, best_bid=0.4, ts=? WHERE token_id='poly-mtm'",
            (now_ts,),
        )
        conn.execute(
            "UPDATE perp_intel SET price=90.0, mark_price=90.0, updated_at=? WHERE symbol='BTC'",
            (now_ts,),
        )

    snapshot = build_unified_portfolio_snapshot(shared_store, cfg)

    assert snapshot.marks_fresh is True
    assert snapshot.mark_failures == ()
    assert snapshot.unrealized_pnl == pytest.approx(-10.1)
    assert snapshot.combined_risk_pnl == pytest.approx(-10.1)


def test_combined_mark_to_market_loss_persists_global_halt(shared_store, cfg):
    clear_halt()
    cfg.portfolio_risk.max_daily_loss_pct = 0.05
    _seed_poly_position(shared_store, "poly-drawdown", size=250.0, avg_price=0.7)
    now_ts = int(time.time())
    with shared_store.tx() as conn:
        conn.execute(
            "UPDATE books SET mid=0.3, best_bid=0.3, ts=? WHERE token_id='poly-drawdown'",
            (now_ts,),
        )
        conn.execute(
            """INSERT INTO fills
               (ts, mode, token_id, condition_id, side, price, size, fee, realized)
               VALUES (?, 'paper', 'closed-token', 'closed-condition', 'SELL', 0.4, 1, 0, -10)""",
            (now_ts,),
        )

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=10.0
    )

    assert not decision.approved
    assert "הפסד מסומן משולב" in decision.reason
    flag = read_halt()
    assert flag is not None
    assert flag.source == "unified-risk"


def test_stale_open_position_mark_fails_closed_without_setting_halt(
    shared_store, cfg
):
    clear_halt()
    _seed_poly_position(shared_store, "poly-stale", size=20.0, avg_price=0.5)
    stale_ts = int(time.time()) - 900
    with shared_store.tx() as conn:
        conn.execute(
            "UPDATE books SET ts=? WHERE token_id='poly-stale'",
            (stale_ts,),
        )

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=10.0
    )

    assert not decision.approved
    assert "Mark-to-Market" in decision.reason
    assert read_halt() is None

 
 
def test_disabled_nonpaper_perps_arm_does_not_block_polymarket_paper(shared_store, cfg):
    cfg.perps.enabled = False
    cfg.perps.mode = "live"

    decision = evaluate_unified_entry(
        shared_store, cfg, arm="polymarket", proposed_capital=10.0
    )

    assert decision.approved
