"""Shared portfolio admission guard for Polymarket and PERPS.

The guard compares capital already committed by both ledgers before accepting
an additional entry. Its file lock spans the admission check, broker call and
ledger persistence in each engine, preventing cross-process over-allocation.
"""
from __future__ import annotations

import json
try:  # POSIX advisory locks
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None
import logging
import math
import os
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterator

from .config import Config
from .data.store import Store
from .runtime import default_state_dir, halt_path, write_halt

log = logging.getLogger(__name__)

# The first engine cycle after 00:00 UTC must record the shared floating-PnL
# anchor. If it is missed, or marks are not synchronized, entries stay blocked
# for the rest of that UTC day rather than silently resetting the loss budget.
UNIFIED_BASELINE_CAPTURE_WINDOW_SEC = 300
UNIFIED_BASELINE_MAX_MARK_SKEW_SEC = 120
UNIFIED_BASELINE_MARK_LOOKBACK_SEC = 120


@dataclass(frozen=True)
class UnifiedPortfolioSnapshot:
    starting_capital: float
    polymarket_committed: float
    perps_margin_used: float
    committed_capital: float
    open_positions: int
    polymarket_realized_today: float
    perps_realized_today: float
    unrealized_pnl: float
    marks_fresh: bool
    mark_failures: tuple[str, ...] = ()
    mark_ts_min: int | None = None
    mark_ts_max: int | None = None
    mark_skew_sec: float = 0.0
    baseline_status: str = "unavailable"
    day_start_baseline_ts: int | None = None
    day_start_baseline_realized_pnl: float | None = None
    day_start_baseline_unrealized_pnl: float | None = None
    baseline_failures: tuple[str, ...] = ()

    @property
    def realized_today(self) -> float:
        return self.polymarket_realized_today + self.perps_realized_today

    @property
    def combined_risk_pnl(self) -> float:
        """Realized PnL plus the current floating PnL of all open positions."""
        return self.realized_today + self.unrealized_pnl

    @property
    def daily_risk_pnl(self) -> float | None:
        if (
            self.baseline_status != "ready"
            or self.day_start_baseline_realized_pnl is None
            or self.day_start_baseline_unrealized_pnl is None
        ):
            return None
        return (
            self.realized_today - self.day_start_baseline_realized_pnl
            + self.unrealized_pnl - self.day_start_baseline_unrealized_pnl
        )

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
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "combined_risk_pnl": round(self.combined_risk_pnl, 2),
            "marks_fresh": self.marks_fresh,
            "mark_failures": list(self.mark_failures),
            "mark_ts_min": self.mark_ts_min,
            "mark_ts_max": self.mark_ts_max,
            "mark_skew_sec": round(self.mark_skew_sec, 2),
            "baseline_status": self.baseline_status,
            "baseline_ts": self.day_start_baseline_ts,
            "baseline_realized_today": (
                round(self.day_start_baseline_realized_pnl, 2)
                if self.day_start_baseline_realized_pnl is not None else None
            ),
            "baseline_unrealized_pnl": (
                round(self.day_start_baseline_unrealized_pnl, 2)
                if self.day_start_baseline_unrealized_pnl is not None else None
            ),
            "daily_risk_pnl": round(self.daily_risk_pnl, 2) if self.daily_risk_pnl is not None else None,
            "baseline_failures": list(self.baseline_failures),
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
    state_dir = default_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "unified-portfolio-entry.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            def unlock():
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        else:  # Windows: lock byte zero using the standard library msvcrt API.
            import msvcrt
            import time
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write("\\0")
                lock_file.flush()
            lock_file.seek(0)
            while True:
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            def unlock():
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        try:
            yield
        finally:
            unlock()


def _global_halt_reason() -> str | None:
    """Treat a present but unreadable/corrupt halt flag as a hard stop."""
    path = halt_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"לא ניתן לאמת את קובץ עצירת החירום ({type(exc).__name__})"
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return "קובץ עצירת החירום פגום — נחסמה כניסה"
    if not isinstance(payload, dict) or not isinstance(payload.get("reason"), str):
        return "קובץ עצירת החירום אינו תקין — נחסמה כניסה"
    return f"עצירת חירום פעילה: {payload['reason'] or 'עצירה ידנית'}"


def _prior_day_entry_fees_realized_today(store: Store, mode: str, day_start: int, now_ts: int) -> float:
    """Return prior-UTC-day opening fees allocated into today's PERPS close PnL.

    PERPS lifetime realized PnL allocates original entry fees to each partial
    close. Those fees were paid on the opening date, so adding them back here
    prevents a close today from counting yesterday's fee a second time as
    today's loss.
    """
    rows = store._conn.execute(
        """SELECT ts, symbol, action, size, fee
           FROM perp_fills
           WHERE mode=? AND ts<=? AND action IN ('OPEN','CLOSE','LIQUIDATION')
           ORDER BY ts, id""",
        (mode, int(now_ts)),
    ).fetchall()
    active: dict[str, dict[str, float | int]] = {}
    adjustment = 0.0
    for row in rows:
        symbol = str(row["symbol"])
        ts = int(row["ts"])
        action = str(row["action"]).upper()
        size = max(0.0, float(row["size"] or 0.0))
        fee = max(0.0, float(row["fee"] or 0.0))
        if action == "OPEN":
            if size > 0:
                # One active position per symbol is enforced by the engine.
                active[symbol] = {
                    "opened_at": ts,
                    "original_size": size,
                    "remaining_size": size,
                    "entry_fee": fee,
                }
            continue

        position = active.get(symbol)
        if position is None or size <= 0:
            continue
        remaining = max(0.0, float(position["remaining_size"]))
        original = max(0.0, float(position["original_size"]))
        closed = min(size, remaining)
        if (
            ts >= day_start
            and int(position["opened_at"]) < day_start
            and original > 0
        ):
            adjustment += float(position["entry_fee"]) * (closed / original)
        remaining -= closed
        if remaining <= max(1e-9, original * 1e-6):
            active.pop(symbol, None)
        else:
            position["remaining_size"] = remaining
    return round(adjustment, 8)


def build_unified_portfolio_snapshot(
    store: Store,
    cfg: Config,
    *,
    now: datetime | None = None,
) -> UnifiedPortfolioSnapshot:
    """Build a ledger + fresh-mark snapshot. Never performs network requests."""
    now = now or datetime.now(tz=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    now_ts = int(now.timestamp())
    day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    poly_positions = store.open_positions(cfg.execution.mode)
    poly_committed = sum(
        max(0.0, float(row["size"] or 0.0)) * max(0.0, float(row["avg_price"] or 0.0))
        for row in poly_positions
    )
    active_poly_tokens = {str(row["token_id"]) for row in poly_positions}
    poly_fills_today = store.fills_since(day_start, cfg.execution.mode)
    # SELL realized includes its exit fee. BUY fees for still-open tokens are
    # applied to their floating PnL below; BUY fees for tokens closed today
    # are deducted here.
    poly_realized_today = sum(float(row["realized"] or 0.0) for row in poly_fills_today)
    poly_realized_today -= sum(
        max(0.0, float(row["fee"] or 0.0))
        for row in poly_fills_today
        if str(row["side"]).upper() == "BUY"
        and str(row["token_id"]) not in active_poly_tokens
    )

    unrealized_pnl = 0.0
    mark_failures: list[str] = []
    mark_timestamps: list[int] = []
    poly_max_age = max(180, int(float(cfg.autopilot.stream_interval_sec) * 4))
    for position in poly_positions:
        token = str(position["token_id"])
        candidates: list[tuple[int, float]] = []
        book = store._conn.execute(
            "SELECT ts, best_bid, mid FROM books WHERE token_id=? ORDER BY ts DESC LIMIT 1",
            (token,),
        ).fetchone()
        if book is not None:
            book_price = book["best_bid"] if book["best_bid"] is not None and float(book["best_bid"]) > 0 else book["mid"]
            if book_price is not None:
                candidates.append((int(book["ts"]), float(book_price)))
        tick = store._conn.execute(
            "SELECT ts, price FROM ticks WHERE token_id=? ORDER BY ts DESC LIMIT 1",
            (token,),
        ).fetchone()
        if tick is not None:
            candidates.append((int(tick["ts"]), float(tick["price"])))

        if not candidates:
            mark_failures.append(f"polymarket:{token[:12]}:missing")
            continue
        mark_ts, mark = max(candidates, key=lambda item: item[0])
        age = now_ts - mark_ts
        size = float(position["size"] or 0.0)
        avg = float(position["avg_price"] or 0.0)
        if age < -5 or age > poly_max_age or not math.isfinite(mark) or not 0.0 < mark < 1.0 or size <= 0 or avg <= 0:
            mark_failures.append(f"polymarket:{token[:12]}:stale-or-invalid")
            continue

        mark_timestamps.append(mark_ts)
        unrealized_pnl += (mark - avg) * size
        # Fees from today's entries into an open token are not realized until
        # exit, so include them exactly once in the floating component.
        open_entry_fees = store._conn.execute(
            """SELECT COALESCE(SUM(fee),0) AS fees FROM fills
               WHERE mode=? AND token_id=? AND side='BUY' AND ts>=?""",
            (cfg.execution.mode, token, day_start),
        ).fetchone()
        unrealized_pnl -= max(0.0, float(open_entry_fees["fees"] or 0.0))

    # A disabled engine can still have open PERPS positions. Keep them in the
    # budget and in the mark-to-market loss calculation.
    perps_state = store.load_perp_portfolio_state(
        cfg.perps.mode,
        cfg.perps.risk.starting_cash,
        now=now,
    )
    perps_positions = list(perps_state["positions"])
    perps_margin = sum(max(0.0, float(p.margin_used)) for p in perps_positions)
    perps_realized_today = float(perps_state["realized_pnl_today"] or 0.0)
    # Opening fees for positions still open today are not in realized PnL yet.
    perps_realized_today -= sum(
        max(0.0, float(p.fees_paid or 0.0))
        for p in perps_positions
        if int(p.opened_at.timestamp()) >= day_start
    )
    # If a position opened before UTC midnight was closed/partially closed
    # today, its close-fill realized amount includes allocated historical entry
    # fees. Add those fees back: they were paid before this UTC risk day.
    perps_realized_today += _prior_day_entry_fees_realized_today(
        store, cfg.perps.mode, day_start, now_ts
    )
    perps_max_age = max(180, int(float(cfg.perps.interval_sec) * 4))

    for position in perps_positions:
        row = store._conn.execute(
            """SELECT price, mark_price, updated_at FROM perp_intel
               WHERE symbol=? LIMIT 1""",
            (position.symbol,),
        ).fetchone()
        if row is None:
            mark_failures.append(f"perps:{position.symbol}:missing")
            continue
        mark_raw = row["mark_price"] if row["mark_price"] is not None and float(row["mark_price"]) > 0 else row["price"]
        if mark_raw is None:
            mark_failures.append(f"perps:{position.symbol}:missing")
            continue
        mark = float(mark_raw)
        mark_ts = int(row["updated_at"] or 0)
        age = now_ts - mark_ts
        if age < -5 or age > perps_max_age or not math.isfinite(mark) or mark <= 0:
            mark_failures.append(f"perps:{position.symbol}:stale-or-invalid")
            continue

        mark_timestamps.append(mark_ts)
        entry_fee_today = store._conn.execute(
            """SELECT COALESCE(SUM(fee),0) AS fees FROM perp_fills
               WHERE mode=? AND symbol=? AND action='OPEN' AND ts>=?""",
            (cfg.perps.mode, position.symbol, day_start),
        ).fetchone()
        # If the position predates today, today's added entry fees belong in
        # its floating component. For positions opened today they were already
        # included in perps_realized_today above.
        fee_to_charge = (
            0.0 if int(position.opened_at.timestamp()) >= day_start
            else max(0.0, float(entry_fee_today["fees"] or 0.0))
        )
        unrealized_pnl += (
            position.unrealized_pnl(mark)
            + float(position.accumulated_funding or 0.0)
            - fee_to_charge
        )

    # Both configured balances belong to the combined account even while
    # one engine is paused; disabling it does not remove its existing capital.
    starting_capital = (
        float(cfg.execution.starting_cash) + float(cfg.perps.risk.starting_cash)
    )
    return UnifiedPortfolioSnapshot(
        starting_capital=starting_capital,
        polymarket_committed=poly_committed,
        perps_margin_used=perps_margin,
        committed_capital=poly_committed + perps_margin,
        open_positions=len(poly_positions) + len(perps_positions),
        polymarket_realized_today=poly_realized_today,
        perps_realized_today=perps_realized_today,
        unrealized_pnl=round(unrealized_pnl, 6),
        marks_fresh=not mark_failures,
        mark_failures=tuple(mark_failures),
        mark_ts_min=min(mark_timestamps) if mark_timestamps else None,
        mark_ts_max=max(mark_timestamps) if mark_timestamps else None,
        mark_skew_sec=(max(mark_timestamps) - min(mark_timestamps)) if mark_timestamps else 0.0,
    )

def ensure_unified_day_baseline(
    store: Store,
    cfg: Config,
    *,
    now: datetime | None = None,
) -> dict:
    """Capture one immutable synchronized floating-PnL baseline per UTC date.

    Both engines call this at cycle start while holding unified_entry_lock,
    before any automated exits or entries. SQLite INSERT OR IGNORE makes the
    winning capture idempotent across separate processes and restarts.
    """
    current = now or datetime.now(tz=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    now_ts = int(current.timestamp())
    day_start = int(current.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    utc_day = current.date().isoformat()

    try:
        latest = store.latest_unified_day_baseline()
        if latest and str(latest["utc_day"]) > utc_day:
            return {
                "utc_day": utc_day, "status": "clock_skew", "baseline_ts": None,
                "failures": ["system UTC clock moved behind a previously stored day baseline"],
            }

        existing = store.get_unified_day_baseline(utc_day)
        if existing is not None:
            return existing

        delay = now_ts - day_start
        if delay < 0:
            return {
                "utc_day": utc_day, "status": "clock_skew", "baseline_ts": None,
                "failures": ["system UTC clock is before the requested UTC day"],
            }

        if delay > UNIFIED_BASELINE_CAPTURE_WINDOW_SEC:
            return store.save_unified_day_baseline(
                utc_day=utc_day, status="expired", recorded_at=now_ts,
                baseline_ts=None, baseline_realized_pnl=None, baseline_unrealized_pnl=None,
                open_positions=0, mark_ts_min=None, mark_ts_max=None, mark_skew_sec=None,
                failures=[f"no synchronized baseline captured within {UNIFIED_BASELINE_CAPTURE_WINDOW_SEC}s of UTC midnight"],
            )

        snapshot = build_unified_portfolio_snapshot(store, cfg, now=current)
        failures = list(snapshot.mark_failures)
        if snapshot.open_positions and not snapshot.marks_fresh:
            failures.append("one or more open-position marks are missing, stale, or invalid")
        if snapshot.mark_skew_sec > UNIFIED_BASELINE_MAX_MARK_SKEW_SEC:
            failures.append(
                f"cross-venue mark timestamp skew {snapshot.mark_skew_sec:.1f}s exceeds "
                f"{UNIFIED_BASELINE_MAX_MARK_SKEW_SEC}s"
            )
        if (
            snapshot.mark_ts_min is not None
            and snapshot.mark_ts_min < day_start - UNIFIED_BASELINE_MARK_LOOKBACK_SEC
        ):
            failures.append(
                f"oldest position mark predates UTC midnight by more than "
                f"{UNIFIED_BASELINE_MARK_LOOKBACK_SEC}s"
            )

        # A non-zero realized figure means something closed before the first
        # cycle could capture the day-start anchor. Do not reset its daily loss.
        if abs(snapshot.realized_today) > 1e-8:
            failures.append("realized activity occurred before the first UTC baseline capture")

        if failures:
            if delay >= UNIFIED_BASELINE_CAPTURE_WINDOW_SEC:
                return store.save_unified_day_baseline(
                    utc_day=utc_day, status="expired", recorded_at=now_ts,
                    baseline_ts=None, baseline_realized_pnl=None, baseline_unrealized_pnl=None,
                    open_positions=snapshot.open_positions,
                    mark_ts_min=snapshot.mark_ts_min, mark_ts_max=snapshot.mark_ts_max,
                    mark_skew_sec=snapshot.mark_skew_sec, failures=failures,
                )
            return {
                "utc_day": utc_day, "status": "pending", "baseline_ts": None,
                "baseline_realized_pnl": None, "baseline_unrealized_pnl": None,
                "open_positions": snapshot.open_positions,
                "mark_ts_min": snapshot.mark_ts_min, "mark_ts_max": snapshot.mark_ts_max,
                "mark_skew_sec": snapshot.mark_skew_sec, "failures": failures,
            }

        return store.save_unified_day_baseline(
            utc_day=utc_day, status="ready", recorded_at=now_ts,
            baseline_ts=now_ts, baseline_realized_pnl=snapshot.realized_today,
            baseline_unrealized_pnl=snapshot.unrealized_pnl,
            open_positions=snapshot.open_positions,
            mark_ts_min=snapshot.mark_ts_min, mark_ts_max=snapshot.mark_ts_max,
            mark_skew_sec=snapshot.mark_skew_sec, failures=(),
        )
    except Exception as exc:  # noqa: BLE001 — a missing baseline must never allow entry.
        log.exception("Could not create/read the unified UTC day-start baseline")
        return {
            "utc_day": utc_day, "status": "error", "baseline_ts": None,
            "failures": [f"baseline persistence/read failed: {type(exc).__name__}"],
        }


def build_unified_risk_status(
    store: Store,
    cfg: Config,
    *,
    now: datetime | None = None,
) -> UnifiedPortfolioSnapshot:
    """Return the same ledger, mark, and baseline snapshot used by admission."""
    current = now or datetime.now(tz=timezone.utc)
    snapshot = build_unified_portfolio_snapshot(store, cfg, now=current)
    baseline = ensure_unified_day_baseline(store, cfg, now=current)
    return replace(
        snapshot,
        baseline_status=str(baseline.get("status") or "error"),
        day_start_baseline_ts=baseline.get("baseline_ts"),
        day_start_baseline_realized_pnl=baseline.get("baseline_realized_pnl"),
        day_start_baseline_unrealized_pnl=baseline.get("baseline_unrealized_pnl"),
        baseline_failures=tuple(baseline.get("failures") or ()),
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

    try:
        amount = float(proposed_capital)
    except (TypeError, ValueError, OverflowError):
        return UnifiedRiskDecision(False, "סכום הקצאת הון לא תקין — נחסמה כניסה")
    if not math.isfinite(amount) or amount <= 0:
        return UnifiedRiskDecision(False, "סכום הקצאת הון לא תקין — נחסמה כניסה")

    # The unified guard is intentionally paper-only until live-mode controls,
    # venue-specific settlement and failure recovery have separate validation.
    if cfg.execution.mode != "paper":
        return UnifiedRiskDecision(False, "שער התיק המאוחד מוגבל ל-Paper; Polymarket אינו במצב Paper")
    if normalized_arm == "perps" and not cfg.perps.enabled:
        return UnifiedRiskDecision(False, "זרוע PERPS מושבתת בקונפיגורציה — נחסמה כניסה")
    if cfg.perps.enabled and cfg.perps.mode != "paper":
        return UnifiedRiskDecision(False, "שער התיק המאוחד מוגבל ל-Paper; PERPS אינו במצב Paper")

    halt_reason = _global_halt_reason()
    if halt_reason:
        return UnifiedRiskDecision(False, halt_reason)

    try:
        snapshot = build_unified_risk_status(store, cfg, now=now)
    except Exception as exc:  # noqa: BLE001 — admission must fail closed
        log.exception("Unified portfolio snapshot failed; denying %s entry", normalized_arm)
        return UnifiedRiskDecision(False, f"לא ניתן לאמת תיק מאוחד ({type(exc).__name__})")

    if snapshot.starting_capital <= 0:
        return UnifiedRiskDecision(False, "הון התחלתי משותף אינו חיובי", snapshot, amount)

    if snapshot.baseline_status != "ready":
        failures = ", ".join(snapshot.baseline_failures[:2])
        if snapshot.baseline_status == "expired":
            reason = f"לא נשמר baseline סיכון מאוחד בתחילת יום UTC — הכניסות חסומות להיום ({failures})"
        elif snapshot.baseline_status == "clock_skew":
            reason = "זוהתה נסיגה בשעון UTC ביחס ל-baseline קודם — הכניסות חסומות"
        else:
            reason = f"baseline סיכון מאוחד ממתין לנתוני מחיר מסונכרנים ({failures})"
        return UnifiedRiskDecision(False, reason, snapshot, amount)

    daily_limit = snapshot.starting_capital * float(limits.max_daily_loss_pct)
    daily_pnl = snapshot.daily_risk_pnl
    if daily_pnl is None:
        return UnifiedRiskDecision(False, "PnL יומי מאומת אינו זמין — נחסמה כניסה", snapshot, amount)

    if snapshot.open_positions and not snapshot.marks_fresh:
        failures = ", ".join(snapshot.mark_failures[:3])
        return UnifiedRiskDecision(
            False,
            f"לא ניתן לאמת Mark-to-Market של כל הפוזיציות ({failures}) — נחסמה כניסה",
            snapshot,
            amount,
        )

    if daily_pnl <= -daily_limit:
        reason = (
            f"הפסד יומי משולב מאז baseline UTC {daily_pnl:.2f} עבר את תקרת ההפסד "
            f"({-daily_limit:.2f}); עצירת חירום הופעלה"
        )
        try:
            write_halt(reason, source="unified-risk")
        except Exception:  # noqa: BLE001
            log.exception("Could not persist unified UTC daily-loss halt")
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
