"""Tests for the cross-arm portfolio risk guard."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from pmmb.data.store import Store
from pmmb.runtime import clear_halt, read_halt
from pmmb.unified_risk import (
    build_unified_portfolio_snapshot,
    evaluate_unified_entry,
    unified_entry_lock,
)


@pytest.fixture
def shared_store(tmp_path, cfg):
    cfg.data.db_path = str(tmp_path / "shared-risk.db")
    store = Store(cfg.data.db_path)
    yield store
    store.close()


def _seed_poly_position(store: Store, token: str, *, size: float, avg_price: float) -> None:
    with store.tx() as conn:
        conn.execute(
            """INSERT INTO positions
               (token_id, condition_id, mode, direction, size, avg_price, opened_at)
               VALUES (?, ?, 'paper', 'LONG', ?, ?, ?)""",
            (token, f"condition-{token}", size, avg_price, int(time.time())),
        )


def _seed_perp_position(store: Store, symbol: str, *, margin: float) -> None:
    with store.tx() as conn:
        conn.execute(
            """INSERT INTO perp_positions
               (symbol, exchange, mode, side, size, entry_price, notional, leverage,
                margin_used, liquidation_price, stop_price, target_price,
                highest_price, lowest_price, opened_at)
               VALUES (?, 'okx', 'paper', 'LONG', 0.01, 100.0, ?, 10.0,
                       ?, 90.0, 95.0, 110.0, 100.0, 100.0, ?)""",
            (symbol, margin * 10.0, margin, int(time.time())),
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
