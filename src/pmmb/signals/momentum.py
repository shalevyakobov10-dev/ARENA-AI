"""
מנוע הסיגנל המרכזי (אסטרטגיה B — מומנטום).

רעיון: שוק בינארי נותן מחיר = הסתברות. אם המחיר "מתעקש" לנוע בכיוון אחד
(EMA, מומנטום, פריצת טווח ו-z-score) — יש סבירות שהשוק מתמחר לאט מדי
אינפורמציה חדשה. המנוע ממיר את העוצמה לפער הסתברות (edge) מול המחיר הנוכחי,
והאינג'ין סוחר רק כשה-edge גדול מהעלויות (ספרד + עמלה).

המנוע טהור: מקבל סדרת מחירים ומחזיר Signal. אין כאן קריאות רשת.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from ..config import SignalConfig
from ..models import Market, Signal
from . import indicators as ind

WEIGHTS = {"trend": 0.35, "momentum": 0.25, "breakout": 0.25, "zscore": 0.15}

# תקרה לצפי תנודה בהסתברות — מונעת edge דמיוני משיפועים קיצוניים
MAX_EXPECTED_MOVE = 0.15


class MomentumEngine:
    name = "momentum"

    def __init__(self, cfg: SignalConfig) -> None:
        self.cfg = cfg

    # ------------------------------------------------------------------
    @property
    def min_candles(self) -> int:
        c = self.cfg
        return max(c.ema_slow, c.breakout_window, c.vol_window, c.momentum_window) + c.confirm_candles + 1

    def evaluate(
        self,
        market: Market,
        prices: Sequence[float],
        *,
        market_price: float,
        spread: float,
        extra: dict | None = None,
    ) -> Signal:
        c = self.cfg
        prices = [float(p) for p in prices]

        if len(prices) < self.min_candles:
            return self._flat(market, f"אין מספיק היסטוריה ({len(prices)}/{self.min_candles})")

        score, feats = self._score(prices)
        strength = abs(score)
        direction_sign = 1 if score > 0 else -1

        # --- פילטר מגמה: לא הולכים נגד ה-EMA האיטי ---
        trend = feats["trend"]
        if c.trend_filter and trend != 0 and math.copysign(1, trend) != direction_sign:
            return self._flat(market, "הסיגנל נגד כיוון המגמה", score=score, feats=feats)

        # --- אישור על פני N נרות ---
        if not self._confirmed(prices, direction_sign):
            return self._flat(market, "הסיגנל טרי מדי (חסר אישור)", score=score, feats=feats)

        if strength < c.min_score:
            return self._flat(market,
                              f"עוצמת סיגנל {strength:.2f} מתחת לסף {c.min_score:.2f}",
                              score=score, feats=feats)

        # --- תרגום עוצמה לפער הסתברות ---
        # תנודה צפויה על אופק האחזקה, בשתי ספרות הסתברות:
        #   (א) דריפט — המשך השיפוע שנמדד לאחרונה לאורך האופק
        #   (ב) תנודתיות — מה שהשוק "עשוי לעשות" גם בלי דריפט
        # העוצמה (strength) מקטינה את הצפי, כי סיגנל חלש = ודאות נמוכה.
        horizon_candles = min(
            max(c.exit.time_stop_hours * 60.0 / max(c.candle_fidelity_min, 1) / 2.0, 3.0),
            120.0,
        )
        vol = max(feats["vol"], 0.002)
        slope = ind.slope(prices, max(c.momentum_window, 8))
        drift_move = abs(slope) * horizon_candles
        vol_move = vol * math.sqrt(horizon_candles)
        # מחיקת קצוות: מחירי הסתברות לא זזים ליניארית — ליד 0/1 התנודה קטנה
        edge_damping = 4.0 * prices[-1] * (1.0 - prices[-1])
        expected_move = (
            strength * min(drift_move + 0.5 * vol_move, MAX_EXPECTED_MOVE) * edge_damping
        )
        fair_yes = ind.clamp(prices[-1] + direction_sign * expected_move, 0.01, 0.99)

        friction = spread / 2.0  # חצי ספרד נאכל בכל כניסה

        if direction_sign > 0:
            direction = "LONG"
            token_id = market.yes_token_id
            mkt = market_price
            fair = fair_yes
        else:
            if not c.allow_short:
                return self._flat(market, "שורט כבוי בקונפיג", score=score, feats=feats)
            direction = "SHORT"
            token_id = market.no_token_id
            mkt = 1.0 - market_price
            fair = 1.0 - fair_yes

        edge = fair - mkt - friction
        feats.update(
            {
                "score_signed": score,
                "slope": slope,
                "drift_move": drift_move,
                "expected_move": expected_move,
                "fair_yes": fair_yes,
                "friction": friction,
                "horizon_candles": horizon_candles,
            }
        )

        reason = (
            f"{direction} score={strength:.2f} edge={edge:+.3f} "
            f"(fair {fair:.3f} vs {mkt:.3f}, vol={vol:.4f}, "
            f"trend={feats['trend']:+.3f}, mom={feats['momentum']:+.3f}, "
            f"breakout={feats['breakout']:+.2f})"
        )

        if edge < c.min_edge:
            return self._flat(market, reason, score=score, feats=feats)

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
    def _score(self, prices: Sequence[float]) -> tuple[float, dict[str, float]]:
        c = self.cfg
        fast = ind.ema(prices[-c.ema_slow * 3:], c.ema_fast)
        slow = ind.ema(prices[-c.ema_slow * 3:], c.ema_slow)
        trend = fast - slow

        mom = prices[-1] - prices[-1 - c.momentum_window]
        bo_mag, bo_dir = ind.breakout(prices, c.breakout_window)
        z = ind.zscore(prices, c.vol_window)
        vol = ind.realized_vol(prices, c.vol_window)

        # סקיילים: תנודה אופיינית על פני החלון — כדי שהציון יהיה חסין לרמת מחיר
        base = max(prices[-1], 0.02)
        trend_scale = max(vol * math.sqrt(c.ema_slow) * base, 0.01)
        mom_scale = max(vol * math.sqrt(c.momentum_window) * base, 0.01)

        s_trend = ind.tanh_norm(trend, trend_scale)
        s_mom = ind.tanh_norm(mom, mom_scale)
        s_bo = ind.clamp(bo_mag, 0.0, 1.0) * bo_dir
        s_z = ind.tanh_norm(z, 2.0)

        score = (
            WEIGHTS["trend"] * s_trend
            + WEIGHTS["momentum"] * s_mom
            + WEIGHTS["breakout"] * s_bo
            + WEIGHTS["zscore"] * s_z
        )
        feats = {
            "fast": fast,
            "slow": slow,
            "trend": trend,
            "momentum": mom,
            "breakout": s_bo,
            "zscore": z,
            "vol": vol,
            "rsi": ind.rsi(prices, 14),
        }
        return max(-1.0, min(1.0, score)), feats

    def _confirmed(self, prices: Sequence[float], sign: int) -> bool:
        """הסיגנל צריך להופיע ב-N הנרות האחרונים, לא רק בנר הנוכחי."""
        n = self.cfg.confirm_candles
        if n <= 1:
            return True
        for k in range(n):
            sub = prices[: len(prices) - k] if k else prices
            if len(sub) < self.min_candles - k:
                continue
            sc, _ = self._score(sub)
            if sc * sign <= 0:
                return False
        return True

    # ------------------------------------------------------------------
    def _flat(self, market: Market, reason: str, *, score: float = 0.0,
              feats: dict[str, float] | None = None) -> Signal:
        return Signal(
            condition_id=market.condition_id,
            token_id=market.yes_token_id,
            direction="FLAT",
            score=abs(score),
            fair_price=market.yes_price,
            market_price=market.yes_price,
            edge=0.0,
            reason=reason,
            features=feats or {},
        )
