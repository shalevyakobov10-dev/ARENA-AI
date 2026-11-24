"""Atomic shared capital-allocation guard for Polymarket and PERPS."""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SharedRiskDecision:
    approved: bool
    reason: str
    reservation_id: str | None = None
    allocated: float = 0.0
    requested: float = 0.0
    limit: float = 0.0
    open_positions: int = 0


class SharedPortfolioRisk:
    """SQLite-serialized allocation gate used by both independent engines.

    Polymarket allocation = open cost basis (size * average price).
    PERPS allocation = isolated margin in use, not leveraged gross notional.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=15.0) as conn:
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS shared_risk_reservations (
                    reservation_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    amount REAL NOT NULL,
                    created_at INTEGER NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_shared_risk_mode ON shared_risk_reservations(mode)"
            )

    def reserve(
        self, *, mode: str, venue: str, amount: float,
        poly_mode: str, perps_mode: str,
        poly_starting_cash: float, perps_starting_cash: float,
        perps_enabled: bool, enabled: bool = True,
        max_allocation_pct: float = 0.50, max_open_positions: int = 8,
    ) -> SharedRiskDecision:
        if not enabled:
            return SharedRiskDecision(True, "shared allocation guard disabled", requested=float(amount))
        if venue not in {"polymarket", "perps"}:
            return SharedRiskDecision(False, "unknown venue")
        try:
            requested = float(amount)
            cap_pct = float(max_allocation_pct)
            max_positions = int(max_open_positions)
            if requested <= 0 or not 0.0 < cap_pct <= 1.0 or max_positions < 1:
                return SharedRiskDecision(False, "invalid shared-risk limits or allocation")

            capital = 0.0
            if poly_mode == mode:
                capital += max(0.0, float(poly_starting_cash))
            if perps_enabled and perps_mode == mode:
                capital += max(0.0, float(perps_starting_cash))
            if capital <= 0:
                return SharedRiskDecision(False, "no configured capital for this execution mode")
            limit = capital * cap_pct
            reservation_id = uuid.uuid4().hex

            with sqlite3.connect(self.path, timeout=15.0, isolation_level=None) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA busy_timeout=15000")
                conn.execute("BEGIN IMMEDIATE")
                poly_alloc = 0.0
                poly_count = 0
                if poly_mode == mode:
                    row = conn.execute(
                        """SELECT COALESCE(SUM(size * avg_price), 0) AS allocated, COUNT(*) AS n
                           FROM positions WHERE mode=? AND size>0 AND closed_at IS NULL""",
                        (mode,),
                    ).fetchone()
                    poly_alloc, poly_count = float(row["allocated"]), int(row["n"])
                perp_alloc = 0.0
                perp_count = 0
                if perps_enabled and perps_mode == mode:
                    row = conn.execute(
                        """SELECT COALESCE(SUM(margin_used), 0) AS allocated, COUNT(*) AS n
                           FROM perp_positions WHERE mode=? AND size>0 AND closed_at IS NULL""",
                        (mode,),
                    ).fetchone()
                    perp_alloc, perp_count = float(row["allocated"]), int(row["n"])
                pending = conn.execute(
                    """SELECT COALESCE(SUM(amount), 0) AS allocated, COUNT(*) AS n
                       FROM shared_risk_reservations WHERE mode=?""",
                    (mode,),
                ).fetchone()
                allocated = poly_alloc + perp_alloc + float(pending["allocated"])
                open_positions = poly_count + perp_count + int(pending["n"])

                if open_positions >= max_positions:
                    conn.rollback()
                    return SharedRiskDecision(
                        False, f"combined position cap ({open_positions}/{max_positions})",
                        allocated=allocated, requested=requested, limit=limit,
                        open_positions=open_positions,
                    )
                if allocated + requested > limit + 1e-9:
                    conn.rollback()
                    return SharedRiskDecision(
                        False, f"combined allocation cap ({allocated + requested:.2f}/{limit:.2f})",
                        allocated=allocated, requested=requested, limit=limit,
                        open_positions=open_positions,
                    )
                conn.execute(
                    """INSERT INTO shared_risk_reservations
                       (reservation_id, mode, venue, amount, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (reservation_id, mode, venue, requested, int(time.time())),
                )
                conn.commit()
            return SharedRiskDecision(
                True, "shared allocation reserved", reservation_id,
                allocated=allocated, requested=requested, limit=limit,
                open_positions=open_positions,
            )
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            return SharedRiskDecision(False, f"shared risk storage unavailable: {exc}")

    def release(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return
        with sqlite3.connect(self.path, timeout=15.0) as conn:
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute(
                "DELETE FROM shared_risk_reservations WHERE reservation_id=?",
                (reservation_id,),
            )

    def reservations(self, mode: str | None = None) -> list[dict]:
        with sqlite3.connect(self.path, timeout=15.0) as conn:
            conn.row_factory = sqlite3.Row
            if mode:
                rows = conn.execute(
                    "SELECT * FROM shared_risk_reservations WHERE mode=? ORDER BY created_at",
                    (mode,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM shared_risk_reservations ORDER BY created_at"
                ).fetchall()
            return [dict(row) for row in rows]
