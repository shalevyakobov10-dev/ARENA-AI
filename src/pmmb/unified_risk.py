"""Shared portfolio admission guard for Polymarket and PERPS.

The guard compares capital already committed by both ledgers before accepting
an additional entry. Its file lock spans the admission check, broker call and
ledger persistence in each engine, preventing cross-process over-allocation.
"""
from __future__ import annotations

import fcntl
import logging
import math
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from .config import Config
from .data.store import Store
from .runtime import default_state_dir, read_halt, write_halt

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UnifiedPortfolioSnapshot:
    starting_capital: float
    polymarket_committed: float
    perps_margin_used: float
    committed_capital: float
    open_positions: int
    polymarket_realized_today: float
    perps_realized_today: float

    @property
    def realized_today(self) -> float:
        return self.polymarket_realized_today + self.perps_realized_today

    def as_dict(self) -> dict:
        return {
            "starting_capital": round(self.starting_capital, 2),
            "polymarket_committed": round(self.polymarket_committed, 2),
            "perps_margin_used": round(self.perps_margin_used, 2),
            "committed_capital": round(self.committed_capital, 2),
            "open_positions": self.open_positions,
            "polymarket_realized_today": round(self.polymarket_realized_today, 2),
            "perps_realized_today": round(self.perps_realized_today, 2),
            "realized_today": round(self.realized_today, 2),
        }


@dataclass(frozen=True)
class UnifiedRiskDecision:
    approved: bool
    reason: str
    snapshot: UnifiedPortfolioSnapshot | None = None
    proposed_capital: float = 0.0
    utilization_pct: float | None = None


@contextmanager
def unified_entry_lock(cfg: Config) -> Iterator[None]:
    """Serialize entry admission + execution + persistence across both engines.

    This is deliberately a blocking, cross-process advisory lock. If the
    process holding the lock dies, the OS releases it automatically.
    """
    limits = cfg.portfolio_risk

    state_dir = default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "unified-portfolio-entry.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def build_unified_portfolio_snapshot(
    store: Store,
    cfg: Config,
    *,
    now: datetime | None = None,
) -> UnifiedPortfolioSnapshot:
    """Build a ledger-backed snapshot. No exchange/network requests are made."""
    now = now or datetime.now(tz=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    poly_positions = store.open_positions(cfg.execution.mode)
    poly_committed = sum(
        max(0.0, float(row["size"] or 0.0)) * max(0.0, float(row["avg_price"] or 0.0))
        for row in poly_positions
    )
    poly_fills_today = store.fills_since(day_start, cfg.execution.mode)
    poly_realized_today = sum(float(row["realized"] or 0.0) for row in poly_fills_today)

    perps_positions = []
    perps_margin = 0.0
    perps_realized_today = 0.0
    if cfg.perps.enabled:
        perps_state = store.load_perp_portfolio_state(
            cfg.perps.mode,
            cfg.perps.risk.starting_cash,
            now=now,
        )
        perps_positions = list(perps_state["positions"])
        perps_margin = sum(max(0.0, float(p.margin_used)) for p in perps_positions)
        perps_realized_today = float(perps_state["realized_pnl_today"] or 0.0)

    starting_capital = float(cfg.execution.starting_cash)
    if cfg.perps.enabled:
        starting_capital += float(cfg.perps.risk.starting_cash)

    return UnifiedPortfolioSnapshot(
        starting_capital=starting_capital,
        polymarket_committed=poly_committed,
        perps_margin_used=perps_margin,
        committed_capital=poly_committed + perps_margin,
        open_positions=len(poly_positions) + len(perps_positions),
        polymarket_realized_today=poly_realized_today,
        perps_realized_today=perps_realized_today,
    )


def evaluate_unified_entry(
    store: Store,
    cfg: Config,
    *,
    arm: str,
    proposed_capital: float,
    now: datetime | None = None,
) -> UnifiedRiskDecision:
    """Fail-closed cross-arm admission check; call while holding unified_entry_lock."""
    limits = cfg.portfolio_risk

    normalized_arm = str(arm).strip().lower()
    if normalized_arm not in {"polymarket", "perps"}:
        return UnifiedRiskDecision(False, "זרוע מסחר לא מוכרת — נחסמה כניסה")

    amount = float(proposed_capital)
    if not math.isfinite(amount) or amount <= 0:
        return UnifiedRiskDecision(False, "סכום הקצאת הון לא תקין — נחסמה כניסה")

    # The unified guard is intentionally paper-only until live-mode controls,
    # venue-specific settlement and failure recovery have separate validation.
    if cfg.execution.mode != "paper":
        return UnifiedRiskDecision(False, "שער התיק המאוחד מוגבל ל-Paper; Polymarket אינו במצב Paper")
    if cfg.perps.enabled and cfg.perps.mode != "paper":
        return UnifiedRiskDecision(False, "שער התיק המאוחד מוגבל ל-Paper; PERPS אינו במצב Paper")

    existing_halt = read_halt()
    if existing_halt is not None:
        return UnifiedRiskDecision(False, f"עצירת חירום פעילה: {existing_halt.reason}")

    try:
        snapshot = build_unified_portfolio_snapshot(store, cfg, now=now)
    except Exception as exc:  # noqa: BLE001 — admission must fail closed
        log.exception("Unified portfolio snapshot failed; denying %s entry", normalized_arm)
        return UnifiedRiskDecision(False, f"לא ניתן לאמת תיק מאוחד ({type(exc).__name__})")

    if snapshot.starting_capital <= 0:
        return UnifiedRiskDecision(False, "הון התחלתי משותף אינו חיובי", snapshot, amount)

    daily_limit = snapshot.starting_capital * float(limits.max_daily_loss_pct)
    if snapshot.realized_today <= -daily_limit:
        reason = (
            f"הפסד ממומש משולב {snapshot.realized_today:.2f} עבר את תקרת היום "
            f"({-daily_limit:.2f})"
        )
        try:
            write_halt(reason, source="unified-risk")
        except Exception:  # noqa: BLE001
            log.exception("Could not persist unified daily-loss halt")
        return UnifiedRiskDecision(False, reason, snapshot, amount)

    if snapshot.open_positions >= int(limits.max_open_positions):
        return UnifiedRiskDecision(
            False,
            f"תקרת פוזיציות משותפת ({snapshot.open_positions}/{limits.max_open_positions})",
            snapshot,
            amount,
        )

    capital_limit = snapshot.starting_capital * float(limits.max_capital_utilization_pct)
    projected = snapshot.committed_capital + amount
    utilization = projected / snapshot.starting_capital * 100.0
    if projected > capital_limit + 1e-8:
        return UnifiedRiskDecision(
            False,
            (
                f"תקרת הקצאת הון משותפת: {projected:.2f} צפוי מול "
                f"{capital_limit:.2f} מותרים ({limits.max_capital_utilization_pct:.0%})"
            ),
            snapshot,
            amount,
            utilization,
        )

    return UnifiedRiskDecision(
        True,
        (
            f"אושר בשער משותף: {projected:.2f}/{capital_limit:.2f} הון מוקצה "
            f"({utilization:.1f}% מההון ההתחלתי הכולל)"
        ),
        snapshot,
        amount,
        utilization,
    )
