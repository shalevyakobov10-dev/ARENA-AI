"""חישוב גודל פוזיציה: סיכון קבוע לפוזיציה, תקרת Kelly ועגינה לכללי השוק."""
from __future__ import annotations

import math

from ..config import RiskConfig


def kelly_fraction(prob: float, price: float) -> float:
    """
    שבר Kelly להימור בינארי: קנייה ב-price שמשלמת 1 אם מנצח.
    f* = (p - price) / (1 - price), חתוך ל-[0,1].
    """
    if not (0 < price < 1):
        return 0.0
    f = (prob - price) / (1.0 - price)
    return max(0.0, min(1.0, f))


def round_to_tick(price: float, tick: float) -> float:
    if tick <= 0:
        return round(price, 4)
    return round(round(price / tick) * tick, 10)


def floor_to_tick(price: float, tick: float) -> float:
    """עיגול למטה — לסטופים ולמחירי מכירה שמרניים."""
    if tick <= 0:
        return math.floor(price * 10000) / 10000
    return math.floor(price / tick) * tick


def size_for_trade(
    *,
    equity: float,
    price: float,
    fair_price: float,
    stop_price: float | None,
    cfg: RiskConfig,
    min_order_size: float,
    lot_size: float = 0.01,
) -> tuple[float, str]:
    """
    מחזיר (size_in_shares, הסבר). 0 = לא נכנסים.

    שלוש תקרות, לוקחים את המינימלית:
      1. סיכון קבוע: (equity * risk_per_trade_pct) / מרחק לסטופ
      2. שבר Kelly מוקטן
      3. תקרת פוזיציה בודדת (max_position_pct)
    """
    if price <= 0 or price >= 1 or equity <= 0:
        return 0.0, "מחיר/הון לא חוקיים"

    risk_budget = equity * cfg.risk_per_trade_pct
    caps: list[tuple[str, float]] = []

    # 1) סיכון לפי סטופ
    if stop_price is not None and 0 < stop_price < price:
        per_share_risk = price - stop_price
        caps.append((f"סיכון {cfg.risk_per_trade_pct:.1%}", risk_budget / per_share_risk))
    else:
        # בלי סטופ — מסתמכים על Kelly + תקרות בלבד
        caps.append(("ללא סטופ", float("inf")))

    # 2) Kelly
    if cfg.kelly_fraction > 0:
        k = kelly_fraction(fair_price, price) * cfg.kelly_fraction
        caps.append((f"Kelly×{cfg.kelly_fraction:g}", (k * equity) / price))

    # 3) תקרת פוזיציה
    caps.append((f"תקרת פוזיציה {cfg.max_position_pct:.0%}", (cfg.max_position_pct * equity) / price))

    label, shares = min(caps, key=lambda kv: kv[1])
    if not math.isfinite(shares) or shares <= 0:
        return 0.0, "אין סיכון פנוי"

    # עגינה ל-lot (0.01 מניה) ולמינימום של פולימרקט
    shares = math.floor(shares / lot_size) * lot_size
    shares = round(shares, 2)
    if shares <= 0:
        return 0.0, "הפוזיציה קטנה מדי"

    notional = shares * price
    if notional < min_order_size:
        # אם אפשר להעמיד בדיוק את המינימום — עושים, אחרת מוותרים
        min_shares = round(min_order_size / price, 2)
        if min_shares * price <= cfg.max_position_pct * equity:
            return min_shares, f"{label} (הועלה למינימום {min_order_size:.0f} USDC)"
        return 0.0, f"notional {notional:.1f} < מינימום {min_order_size:.0f}"

    return shares, label


def stop_and_target(price: float, side: str, stop_loss_pct: float, take_profit_pct: float,
                    tick: float, *, mode: str = "pct") -> tuple[float, float]:
    """
    מחירי סטופ ויעד עבור LONG או SHORT.
    mode="pct": אחוז ממחיר הכניסה.
    mode="abs": נקודות הסתברות קבועות (מתאים לשווקי ‎[0,1]‎ עם ספרד קבוע).
    """
    if mode == "abs":
        if side in ("BUY", "LONG"):
            stop = max(0.01, price - stop_loss_pct)
            target = min(0.99, price + take_profit_pct)
        else:
            stop = min(0.99, price + stop_loss_pct)
            target = max(0.01, price - take_profit_pct)
    else:
        if side in ("BUY", "LONG"):
            stop = max(0.01, price * (1 - stop_loss_pct))
            target = min(0.99, price * (1 + take_profit_pct))
        else:
            stop = min(0.99, price * (1 + stop_loss_pct))
            target = max(0.01, price * (1 - take_profit_pct))

    stop = round_to_tick(stop, tick)
    target = round_to_tick(target, tick)

    # עיגול לטיק יכול "לשטח" סטופ/יעד אל מחיר הכניסה (למשל מחיר 0.09 עם
    # טיק 0.01). זה יוצר יציאה מיידית עם פתיחת הפוזיציה — אסור שיקרה.
    t = tick if tick > 0 else 0.001
    if stop >= price:
        stop = round_to_tick(price - t, t)
    if target <= price:
        target = round_to_tick(price + t, t)
    stop = max(0.001, stop)
    target = min(0.999, target)
    return stop, target
