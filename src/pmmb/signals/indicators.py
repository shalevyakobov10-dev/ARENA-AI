"""אינדיקטורים על סדרת מחירים — טהורים, בלי תלות ב-IO (קלים לטסטים)."""
from __future__ import annotations

import math
from collections.abc import Sequence


def ema(values: Sequence[float], period: int) -> float:
    """EMA קלאסי; מחזיר את הערך האחרון."""
    if not values or period <= 0:
        return float("nan")
    k = 2.0 / (period + 1.0)
    acc = float(values[0])
    for v in values[1:]:
        acc = v * k + acc * (1 - k)
    return acc


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if not values or period <= 0:
        return []
    k = 2.0 / (period + 1.0)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def returns(values: Sequence[float]) -> list[float]:
    """תשואות לוגריתמיות (בטוח יותר סביב 0/1 מפרוקסי לינארי)."""
    out: list[float] = []
    for prev, cur in zip(values, values[1:]):
        p = max(min(prev, 1 - 1e-6), 1e-6)
        c = max(min(cur, 1 - 1e-6), 1e-6)
        out.append(math.log(c / p))
    return out


def stdev(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(max(var, 0.0))


def zscore(values: Sequence[float], window: int) -> float:
    """z-score של הערך האחרון מול חלון."""
    if len(values) < max(window, 3):
        return 0.0
    win = values[-window:]
    sd = stdev(win[:-1])
    mean = sum(win[:-1]) / (len(win) - 1)
    if sd <= 1e-12:
        # סדרה שטוחה לגמרי: חריגה היא אירוע חריג במיוחד
        delta = win[-1] - mean
        return math.copysign(5.0, delta) if abs(delta) > 1e-12 else 0.0
    return (win[-1] - mean) / sd


def slope(values: Sequence[float], window: int) -> float:
    """שיפוע רגרסיה לינארית מנורמל (יחידות מחיר לנר)."""
    if len(values) < max(window, 3):
        return 0.0
    y = values[-window:]
    n = len(y)
    xs = list(range(n))
    mx = (n - 1) / 2
    my = sum(y) / n
    num = sum((x - mx) * (v - my) for x, v in zip(xs, y))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def rsi(values: Sequence[float], period: int = 14) -> float:
    """RSI על מחירים (0-100). שימושי כפילטר overbought/oversold."""
    if len(values) < period + 1:
        return 50.0
    gains = losses = 0.0
    for prev, cur in zip(values[-period - 1:], values[-period:]):
        diff = cur - prev
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    if losses <= 1e-12:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def breakout(values: Sequence[float], window: int) -> tuple[float, int]:
    """
    האם הערך האחרון פורץ את טווח `window` הנרות הקודמים.
    מחזיר (עוצמת_פריצה_ביחידות_סטיית_תקן, כיוון) כאשר כיוון ∈ {-1,0,1}.
    """
    if len(values) < window + 1 or window < 2:
        return 0.0, 0
    prev = values[-window - 1:-1]
    last = values[-1]
    hi, lo = max(prev), min(prev)
    sd = stdev(prev) or 1e-6
    if last > hi:
        return (last - hi) / sd, 1
    if last < lo:
        return (lo - last) / sd, -1
    return 0.0, 0


def realized_vol(values: Sequence[float], window: int) -> float:
    """סטיית תקן של תשואות — ליחידת נר."""
    rets = returns(values[-(window + 1):])
    return stdev(rets)


def tanh_norm(x: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return math.tanh(x / scale)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
