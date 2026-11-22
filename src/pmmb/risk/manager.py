"""ניהול סיכון: שערים לפני כניסה, זיהוי יציאות, ו-kill switch."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..config import Config
from ..models import Market, PortfolioSnapshot, Position, RiskDecision, Signal
from .sizing import size_for_trade, stop_and_target

log = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.risk = cfg.risk
        self._cooldown_until: dict[str, datetime] = {}
        self.halted = False
        self.halt_reason = ""
        # מעקב אחרי שיא ההון — מתעדכן בכל snapshot
        self._peak_equity = 0.0

    # ------------------------------------------------------------------
    #  שער כניסה
    # ------------------------------------------------------------------
    def evaluate_entry(
        self,
        signal: Signal,
        market: Market,
        portfolio: PortfolioSnapshot,
        *,
        price: float,
        tick: float,
        min_order_size: float,
    ) -> RiskDecision:
        r = self.risk

        if self.halted:
            return RiskDecision(False, reason=f"הבוט עצור: {self.halt_reason}")

        if signal.direction == "FLAT":
            return RiskDecision(False, reason="אין סיגנל")

        # --- מדדים תיקיים ---
        if portfolio.open_positions >= r.max_open_positions:
            return RiskDecision(False, reason=f"הגענו ל-{r.max_open_positions} פוזיציות פתוחות")

        if portfolio.equity <= 0:
            return RiskDecision(False, reason="הון אפס")

        exposure_room = portfolio.equity * r.max_total_exposure_pct - portfolio.exposure
        if exposure_room <= 0:
            return RiskDecision(
                False, reason=f"חשיפה מלאה ({portfolio.exposure:.0f}/{portfolio.equity * r.max_total_exposure_pct:.0f})"
            )

        if portfolio.realized_pnl_today <= -portfolio.equity * r.max_daily_loss_pct:
            self.halt(f"הפסד יומי עבר {r.max_daily_loss_pct:.0%}")
            return RiskDecision(False, reason=self.halt_reason)

        if portfolio.drawdown_pct >= r.max_drawdown_pct:
            self.halt(f"drawdown {portfolio.drawdown_pct:.1%} עבר את התקרה")
            return RiskDecision(False, reason=self.halt_reason)

        # --- cooldown אחרי יציאה מאותו שוק ---
        cd = self._cooldown_until.get(signal.condition_id)
        if cd and datetime.now(tz=timezone.utc) < cd:
            mins = (cd - datetime.now(tz=timezone.utc)).total_seconds() / 60
            return RiskDecision(False, reason=f"cooldown ({mins:.0f} דק')")

        # --- חישוב גודל ---
        stop, target = stop_and_target(
            price,
            "LONG",
            self.cfg.signal.exit.stop_loss,
            self.cfg.signal.exit.take_profit,
            tick,
        )
        shares, why = size_for_trade(
            equity=portfolio.equity,
            price=price,
            fair_price=max(signal.fair_price, price),
            stop_price=stop,
            cfg=r,
            min_order_size=min_order_size,
        )
        if shares <= 0:
            return RiskDecision(False, reason=f"גודל אפס ({why})")

        notional = shares * price
        if notional > exposure_room:
            scaled = max(0.0, exposure_room / price)
            scaled = round(int(scaled * 100) / 100, 2)
            if scaled * price < min_order_size:
                return RiskDecision(False, reason="אין מקום בחשיפה (גם לא למינימום)")
            shares, notional = scaled, scaled * price
            why += " → הוקטן לחשיפה פנויה"

        if notional > portfolio.cash:
            return RiskDecision(False, reason=f"אין מזומן ({portfolio.cash:.1f} < {notional:.1f})")

        return RiskDecision(True, size=shares, notional=round(notional, 4),
                            reason=f"{why}; stop={stop:.3f} target={target:.3f}")

    # ------------------------------------------------------------------
    #  שער יציאה
    # ------------------------------------------------------------------
    def evaluate_exit(
        self,
        position: Position,
        mark_price: float,
        *,
        now: datetime | None = None,
        signal_flipped: bool = False,
    ) -> str | None:
        """מחזיר סיבת יציאה או None. הפוזיציה תמיד 'לונג' על הטוקן שנקנה."""
        now = now or datetime.now(tz=timezone.utc)
        ex = self.cfg.signal.exit

        if position.stop_price is not None and mark_price <= position.stop_price:
            return f"סטופ ({mark_price:.3f} ≤ {position.stop_price:.3f})"
        if position.target_price is not None and mark_price >= position.target_price:
            return f"יעד ({mark_price:.3f} ≥ {position.target_price:.3f})"

        held_h = (now - position.opened_at).total_seconds() / 3600.0
        if held_h >= ex.time_stop_hours:
            return f"time stop ({held_h:.1f}ש')"

        if ex.exit_on_flip and signal_flipped:
            return "הסיגנל התהפך"

        # יציאה קרובה לפדיון — לא נושאים סיכון resolution
        return None

    # ------------------------------------------------------------------
    def start_cooldown(self, condition_id: str) -> None:
        self._cooldown_until[condition_id] = datetime.now(tz=timezone.utc) + timedelta(
            minutes=self.risk.cooldown_minutes
        )

    def halt(self, reason: str) -> None:
        if not self.halted:
            self.halted = True
            self.halt_reason = reason
            log.error("⛔ KILL SWITCH: %s", reason)

    def resume(self) -> None:
        self.halted = False
        self.halt_reason = ""
        log.warning("הבוט הופעל מחדש ידנית")

    def update_peak(self, equity: float) -> None:
        self._peak_equity = max(self._peak_equity, equity)
