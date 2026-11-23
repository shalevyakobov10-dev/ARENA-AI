"""
ניהול סיכונים ומינוף דינמי לחוזים תמידיים עד ×50 (Isolated Margin).

כללי הברזל להגנה על הון תחת מינוף גבוה:
  1. Isolated Margin בלבד — פוזיציה מפסידה לא גוררת את שאר התיק.
  2. Liquidation Buffer Guard — אסור שהליקווידציה תהיה קרובה מ-`liquidation_buffer_mult * SL`.
     אם התנודתיות רחבה, המינוף מתכווץ אוטומטית; כשהתנודתיות הדוקה ואיכות A+, עולה עד ×50!
  3. Risk-Based Sizing — גודל הפוזיציה (`notional`) נקבע לפי מרחק ה-SL (`risk_usd / stop_dist`).
  4. Trailing Stop מבוסס ATR + Time Stop + Daily/Drawdown Kill Switch + Cooldown.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..config import PerpsConfig
from .models import PerpInstrument, PerpPosition, PerpSignal, utcnow


def calc_liquidation_price(side: str, entry: float, leverage: float, mmr: float = 0.005) -> float:
    """מחיר ליקווידציה מדויק ל-Isolated Margin."""
    lev = max(1.0, float(leverage))
    if side == "LONG":
        return max(0.0, entry * (1.0 - (1.0 / lev) + mmr))
    return entry * (1.0 + (1.0 / lev) - mmr)


@dataclass
class PerpRiskDecision:
    approved: bool
    reason: str
    leverage: float = 1.0
    size: float = 0.0
    notional: float = 0.0
    margin: float = 0.0
    liquidation_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0


class PerpRiskManager:
    def __init__(self, cfg: PerpsConfig) -> None:
        self.cfg = cfg
        self.halted: bool = False
        self.halt_reason: str = ""
        self.peak_equity: float = cfg.risk.starting_cash
        self._cooldown_until: dict[str, datetime] = {}

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason

    def update_peak(self, equity: float) -> None:
        if equity > self.peak_equity:
            self.peak_equity = equity

    def start_cooldown(self, symbol: str, now: datetime | None = None) -> None:
        now = now or utcnow()
        hours = float(self.cfg.risk.cooldown_bars)
        if hours > 0:
            self._cooldown_until[symbol] = now + timedelta(hours=hours)

    def in_cooldown(self, symbol: str, now: datetime | None = None) -> bool:
        until = self._cooldown_until.get(symbol)
        if until is None:
            return False
        now = now or utcnow()
        if now >= until:
            del self._cooldown_until[symbol]
            return False
        return True

    def check_global_kill(self, equity: float, realized_today: float) -> bool:
        self.update_peak(equity)
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        if dd >= self.cfg.risk.max_drawdown_pct:
            self.halt(f"Perps Max Drawdown ({dd:.1%})")
            return True
        if realized_today <= -equity * self.cfg.risk.max_daily_loss_pct:
            self.halt(f"Perps Daily Loss ({realized_today:+.2f} USDC)")
            return True
        return False

    def evaluate_entry(
        self,
        signal: PerpSignal,
        inst: PerpInstrument,
        *,
        equity: float,
        free_cash: float,
        open_positions: list[PerpPosition],
        now: datetime | None = None,
    ) -> PerpRiskDecision:
        now = now or utcnow()
        rk = self.cfg.risk

        if self.halted:
            return PerpRiskDecision(False, f"מערכת Perps עצורה: {self.halt_reason}")
        if signal.direction == "FLAT" or signal.stop_price is None or signal.take_profit_price is None:
            return PerpRiskDecision(False, "אות FLAT")
        if any(p.symbol == signal.symbol for p in open_positions):
            return PerpRiskDecision(False, f"כבר יש פוזיציה פתוחה ב-{signal.symbol}")
        if self.in_cooldown(signal.symbol, now):
            return PerpRiskDecision(False, f"{signal.symbol} בתקופת צינון אחרי יציאה")
        if len(open_positions) >= rk.max_open_positions:
            return PerpRiskDecision(False, f"הגעת לתקרת פוזיציות ({rk.max_open_positions})")
        same_dir = sum(1 for p in open_positions if p.side == signal.direction)
        if same_dir >= rk.max_positions_per_direction:
            return PerpRiskDecision(False, f"תקרת קורלציה בכיוון {signal.direction} ({same_dir})")

        used_margin = sum(p.margin_used for p in open_positions)
        if equity <= 0 or used_margin >= equity * rk.max_total_margin_pct:
            return PerpRiskDecision(False, "תקרת ניצול Margin בתיק")

        px = signal.price
        stop_dist = abs(px - signal.stop_price) / px if px > 0 else 0.0
        if stop_dist <= 1e-4:
            return PerpRiskDecision(False, "מרחק סטופ זניח")

        # חישוב מינוף בטוח (עד 50x) שמונע ליקווידציה לפני פגיעת SL
        rt_cost = 2.0 * (self.cfg.taker_fee_bps + self.cfg.slippage_bps) / 10_000.0
        mmr = inst.mmr or rk.default_mmr
        safe_lev_cap = max(1.0, (1.0 - mmr) / max(1e-4, stop_dist * rk.liquidation_buffer_mult + rt_cost))
        lev = round(min(rk.max_leverage, inst.max_leverage, signal.recommended_leverage, safe_lev_cap), 1)
        lev = max(2.0, lev)

        # סייזינג מבוסס סיכון מדורג לפי איכות הסטאפ (A+ מקבל עדיפות הון, B מרוסן)
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        dd_mult = 0.65 if dd >= 0.06 else 1.0
        tier_mult = 1.30 if signal.tier == "A+" else (1.10 if signal.tier == "A" else 0.85)
        risk_usd = equity * rk.risk_per_trade_pct * dd_mult * tier_mult
        notional = risk_usd / stop_dist
        margin = notional / lev

        max_pos_margin = min(
            equity * rk.max_margin_per_position_pct,
            equity * rk.max_total_margin_pct - used_margin,
            free_cash * 0.90,
        )
        if margin > max_pos_margin:
            margin = max_pos_margin
            notional = margin * lev
        if margin < 5.0 or notional < 10.0:
            return PerpRiskDecision(False, f"Margin פנוי קטן מדי ({margin:.2f} USDC)")

        size = notional / px
        liq_px = calc_liquidation_price(signal.direction, px, lev, mmr)
        return PerpRiskDecision(
            approved=True,
            reason=f"מאושר {signal.tier} | ×{lev:.1f} | Margin {margin:.2f} | Risk {risk_usd:.2f}",
            leverage=lev,
            size=round(size, 6),
            notional=round(notional, 2),
            margin=round(margin, 2),
            liquidation_price=round(liq_px, 6),
            stop_price=signal.stop_price,
            target_price=signal.take_profit_price,
        )

    def evaluate_exit_and_trail(
        self,
        pos: PerpPosition,
        *,
        mark_price: float,
        high_price: float | None = None,
        low_price: float | None = None,
        now: datetime | None = None,
    ) -> str | None:
        """בודק ליקווידציה, Stop Loss, Take Profit, Time Stop ומעדכן ATR Trailing Stop."""
        now = now or utcnow()
        rk = self.cfg.risk
        hi = max(mark_price, high_price or mark_price)
        lo = min(mark_price, low_price or mark_price)

        if pos.side == "LONG":
            pos.highest_price = max(pos.highest_price, hi)
            if pos.stop_price > pos.liquidation_price:
                if lo <= pos.stop_price:
                    return f"סטופ/Trailing ({lo:.4f} <= {pos.stop_price:.4f})"
                if hi >= pos.target_price:
                    return f"יעד רווח ({hi:.4f} >= {pos.target_price:.4f})"
            else:
                if lo <= pos.liquidation_price:
                    return f"ליקווידציה ({lo:.4f} <= {pos.liquidation_price:.4f})"
                if lo <= pos.stop_price:
                    return f"סטופ ({lo:.4f} <= {pos.stop_price:.4f})"
                if hi >= pos.target_price:
                    return f"יעד רווח ({hi:.4f} >= {pos.target_price:.4f})"
            if rk.trailing_enabled and pos.atr > 0:
                if (pos.highest_price - pos.entry_price) >= rk.trailing_trigger_atr * pos.atr:
                    new_sl = pos.highest_price - rk.trailing_dist_atr * pos.atr
                    if new_sl > pos.stop_price:
                        pos.stop_price = round(new_sl, 6)
        else:
            pos.lowest_price = min(pos.lowest_price, lo)
            if pos.stop_price < pos.liquidation_price:
                if hi >= pos.stop_price:
                    return f"סטופ/Trailing ({hi:.4f} >= {pos.stop_price:.4f})"
                if lo <= pos.target_price:
                    return f"יעד רווח ({lo:.4f} <= {pos.target_price:.4f})"
            else:
                if hi >= pos.liquidation_price:
                    return f"ליקווידציה ({hi:.4f} >= {pos.liquidation_price:.4f})"
                if hi >= pos.stop_price:
                    return f"סטופ ({hi:.4f} >= {pos.stop_price:.4f})"
                if lo <= pos.target_price:
                    return f"יעד רווח ({lo:.4f} <= {pos.target_price:.4f})"
            if rk.trailing_enabled and pos.atr > 0:
                if (pos.entry_price - pos.lowest_price) >= rk.trailing_trigger_atr * pos.atr:
                    new_sl = pos.lowest_price + rk.trailing_dist_atr * pos.atr
                    if new_sl < pos.stop_price:
                        pos.stop_price = round(new_sl, 6)

        age_h = (now - pos.opened_at).total_seconds() / 3600.0
        if age_h >= rk.time_stop_hours:
            return f"Time Stop ({age_h:.1f}h >= {rk.time_stop_hours:.0f}h)"
        return None
