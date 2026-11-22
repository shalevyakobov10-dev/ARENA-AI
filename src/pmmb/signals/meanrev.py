"""
מנוע Mean-Reversion — "אסטרטגיה B2".

הרקע: אבחון על 2,837 דגימות מ-12 שווקים אמיתיים הראה
corr(תנועה של 12 נרות, תנועה של 24 נרות קדימה) = -0.148, כלומר
השווקים האלה **מתקנים עודף** ולא ממשיכים אותו. הדסיל של הירידות החדות
ביותר (‎-0.05‎ בממוצע) הניב ‎+0.024‎ ב-24 הנרות הבאים — יותר מכפול מהעלות
של ספרד + החלקה.

לכן המנוע הזה עושה את ההפך מהמנוע המומנטום:
  ירידה חדשה וחריגה (z שלילי) → קונים YES (הימור על תיקון)

כיול (12 שווקים, 3,788 נרות שעתיים):
  dip z>3   → תיקון ממוצע +0.0245 (62% hit, n=29)
  dip z 2-3 → +0.0206 (61%, n=51)
  dip z1.5-2→ +0.0158 (57%, n=145)
  dip z1-1.5→ +0.0131 (50%, n=1046)  ← שולי אחרי עלויות
  עלייה חדה (z חיובי)      → כבוי כברירת מחדל, כי בדאטה לא נמצאה
                              היפוך אמין בצד העולה.

המנוע טהור — מקבל סדרת מחירים ומחזיר Signal.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from ..config import SignalConfig
from ..fees import round_trip_fee_per_share
from ..models import Market, Signal
from . import indicators as ind

MAX_BOUNCE = 0.20          # תקרה לצפי התיקון בהסתברות
MIN_TYPICAL_MOVE = 0.002   # רצפה לתנודה אופיינית (בנקודות הסתברות)


class MeanReversionEngine:
    name = "meanrev"

    def __init__(self, cfg: SignalConfig) -> None:
        self.cfg = cfg
        self.mr = cfg.meanrev

    @property
    def min_candles(self) -> int:
        return max(self.mr.lookback_candles, self.cfg.vol_window) + 2

    # ------------------------------------------------------------------
    def evaluate(
        self,
        market: Market,
        prices: Sequence[float],
        *,
        market_price: float,
        spread: float,
        extra: dict | None = None,
    ) -> Signal:
        mr = self.mr
        prices = [float(p) for p in prices]
        if len(prices) < self.min_candles:
            return self._flat(market, f"אין מספיק היסטוריה ({len(prices)}/{self.min_candles})")

        n = mr.lookback_candles
        move = prices[-1] - prices[-1 - n]                 # התנועה שנמדדה (במחיר)
        p = prices[-1]
        # תנודתיות נמדדת **לפני** התנועה שאנחנו בודקים — אחרת האירוע עצמו
        # מנפח את התנודתיות ומסווה את עצמו (z יוצא קטן מדי).
        history = prices[:-n] if len(prices) > n + self.cfg.vol_window else prices
        vol = ind.realized_vol(history, self.cfg.vol_window)
        # תנודה אופיינית של n נרות, במונחי מחיר. רצפה של 0.002 —
        # שוק "מת" לא אמור לייצר z אינסופי בגלל תנודה של סנט.
        typical = max(vol * p * math.sqrt(n), MIN_TYPICAL_MOVE)
        z = move / typical                                  # כמה חריגה התנועה

        if abs(z) < mr.z_entry:
            return self._flat(market, f"אין עודף חריג (z={z:+.2f})", z=z)

        # הקשר מגמה: צניחה בתוך מגמת עלייה חזקה היא לרוב לא עודף אלא
        # היפוך מגמה. מחקר על 12 שווקים: 33% hit מול 59% בהקשר ניטרלי.
        # כבוי כברירת מחדל — מחכה ל-walk-forward שמאשר.
        trend_norm = 0.0
        if mr.trend_window < len(prices):
            trend_norm = ind.slope(prices, mr.trend_window) * mr.trend_window / typical
            if mr.trend_guard and trend_norm > mr.trend_max_norm:
                return self._flat(
                    market,
                    f"צניחה בתוך מגמת עלייה חזקה (trend={trend_norm:+.1f})",
                    z=z,
                )

        # תנועה קיצונית אינה "עודף" — היא כמעט תמיד ידיעה חדשה
        # (חוזה ספורט שהוכרע, חדשות מאקרו). תפיסת סכין נופלת עולה ביוקר.
        if abs(z) > mr.z_max:
            return self._flat(
                market,
                f"תנועה קיצונית z={z:+.2f} > {mr.z_max:g} — מידע, לא עודף",
                z=z,
            )

        if z < 0:
            direction = "LONG"
            token_id = market.yes_token_id
            side_price = market_price          # קונים YES במחיר השוק
            room = 1.0 - p
        else:
            if not mr.allow_short:
                return self._flat(market, f"עלייה חדה (z={z:+.2f}) — הצד העולה כבוי", z=z)
            direction = "SHORT"
            token_id = market.no_token_id
            side_price = 1.0 - market_price
            room = p

        # עוצמת הסיגנל: כמה חריג העודף (z=3 → 1.0)
        strength = ind.clamp(abs(z) / 3.0, 0.0, 1.0)

        # צפי התיקון: שיעור מהעודף שנמדד אמפירית (bounce/dip ≈ 0.5-0.67
        # עבור z>1.5), מוגבל במקום שנותר עד הקצה. אין כאן הכפלה בעוצמה —
        # העוצמה משמשת כשער כניסה בלבד, אחרת הצפי נשחק פעמיים.
        expected = min(mr.reversion_ratio * abs(move), MAX_BOUNCE)
        expected = min(expected, mr.max_room_pct * room)

        if direction == "LONG":
            fair_yes = ind.clamp(p + expected, 0.01, 0.99)
            fair = fair_yes
            mkt = side_price
        else:
            fair_yes = ind.clamp(p - expected, 0.01, 0.99)
            fair = 1.0 - fair_yes
            mkt = side_price

        # עלות הלוך-חזור: ספרד מלא (קונים ב-ask, מוכרים ב-bid) + עמלות סבב.
        # העמלה היא p(1−p) — כלומר יקרה באמצע הטווח וזולה בקצוות.
        fee_rate = float((extra or {}).get("fee_rate", 0.0))
        fees = round_trip_fee_per_share(p, fee_rate) if fee_rate > 0 else 0.0
        friction = spread + fees
        edge = fair - mkt - friction

        feats = {
            "z": z,
            "trend_norm": trend_norm,
            "move": move,
            "typical": typical,
            "vol": vol,
            "expected_bounce": expected,
            "rsi": ind.rsi(prices, 14),
            "fair_yes": fair_yes,
            "friction": friction,
            "fees": fees,
            "fee_rate": fee_rate,
        }
        reason = (
            f"{direction} meanrev z={z:+.2f} move={move:+.3f} "
            f"edge={edge:+.3f} (fair {fair:.3f} vs {mkt:.3f}, "
            f"bounce={expected:.3f})"
        )

        if strength < self.cfg.min_score:
            return self._flat(market, f"עוצמה {strength:.2f} < {self.cfg.min_score:.2f}", z=z, extra=feats)
        if edge < self.cfg.min_edge:
            return self._flat(market, reason + " — edge נמוך מהעלויות", z=z, extra=feats)

        return Signal(
            condition_id=market.condition_id,
            token_id=token_id,
            direction=direction,
            score=strength,
            fair_price=fair,
            market_price=mkt,
            edge=edge,
            reason=reason,
            features=feats,
        )

    # ------------------------------------------------------------------
    def _flat(self, market: Market, reason: str, *, z: float = 0.0,
              extra: dict | None = None) -> Signal:
        feats = dict(extra or {})
        feats.setdefault("z", z)
        return Signal(
            condition_id=market.condition_id,
            token_id=market.yes_token_id,
            direction="FLAT",
            score=0.0,
            fair_price=market.yes_price,
            market_price=market.yes_price,
            edge=0.0,
            reason=reason,
            features=feats,
        )
