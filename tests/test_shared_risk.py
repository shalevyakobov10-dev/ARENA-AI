from __future__ import annotations

from pmmb.data.store import Store
from pmmb.shared_risk import SharedPortfolioRisk


def _guard(tmp_path):
    path = tmp_path / "shared-risk.db"
    store = Store(path)
    store.close()
    return path, SharedPortfolioRisk(path)


def _reserve(guard, venue, amount, **overrides):
    args = dict(
        mode="paper", venue=venue, amount=amount,
        poly_mode="paper", perps_mode="paper",
        poly_starting_cash=1000.0, perps_starting_cash=1000.0,
        perps_enabled=True, enabled=True,
        max_allocation_pct=0.50, max_open_positions=8,
    )
    args.update(overrides)
    return guard.reserve(**args)


def test_allocation_is_shared_across_venues_and_reservations(tmp_path):
    _, guard = _guard(tmp_path)
    poly = _reserve(guard, "polymarket", 600.0)
    assert poly.approved
    perps = _reserve(guard, "perps", 450.0)
    assert not perps.approved
    assert "allocation cap" in perps.reason
    guard.release(poly.reservation_id)
    perps = _reserve(guard, "perps", 450.0)
    assert perps.approved
    guard.release(perps.reservation_id)


def test_pending_reservations_count_toward_shared_position_cap(tmp_path):
    _, guard = _guard(tmp_path)
    first = _reserve(guard, "polymarket", 100.0, max_open_positions=1)
    assert first.approved
    second = _reserve(guard, "perps", 100.0, max_open_positions=1)
    assert not second.approved
    assert "position cap" in second.reason
    guard.release(first.reservation_id)


def test_existing_polymarket_cost_basis_reduces_combined_budget(tmp_path):
    path, guard = _guard(tmp_path)
    store = Store(path)
    store._conn.execute(
        """INSERT INTO positions
           (token_id, condition_id, mode, direction, size, avg_price, opened_at)
           VALUES ('token', 'condition', 'paper', 'LONG', 1000, 0.5, 1)"""
    )
    store._conn.commit()
    store.close()
    decision = _reserve(guard, "perps", 101.0, max_allocation_pct=0.30)
    assert not decision.approved
    assert "allocation cap" in decision.reason


def test_existing_perps_margin_reduces_combined_budget(tmp_path):
    path, guard = _guard(tmp_path)
    store = Store(path)
    store._conn.execute(
        """INSERT INTO perp_positions
           (symbol, exchange, mode, side, size, entry_price, notional, leverage,
            margin_used, liquidation_price, stop_price, target_price,
            highest_price, lowest_price, opened_at)
           VALUES ('BTC', 'okx', 'paper', 'LONG', 1, 50000, 50000, 10,
                   500, 45000, 48000, 55000, 50000, 50000, 1)"""
    )
    store._conn.commit()
    store.close()
    decision = _reserve(guard, "polymarket", 101.0, max_allocation_pct=0.30)
    assert not decision.approved
    assert "allocation cap" in decision.reason


def test_paper_and_live_budgets_are_isolated(tmp_path):
    _, guard = _guard(tmp_path)
    live = _reserve(
        guard, "polymarket", 500.0,
        mode="live", poly_mode="live", perps_mode="paper",
        max_allocation_pct=0.50,
    )
    paper = _reserve(guard, "perps", 500.0)
    assert live.approved and paper.approved
    guard.release(live.reservation_id)
    guard.release(paper.reservation_id)


def test_reservation_storage_failure_fails_closed(tmp_path):
    _, guard = _guard(tmp_path)
    guard.path = tmp_path / "missing" / "unwritable.db"
    decision = _reserve(guard, "polymarket", 10.0)
    assert not decision.approved
    assert "storage unavailable" in decision.reason
