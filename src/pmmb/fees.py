"""
מודל העמלות של Polymarket — הדבר שהכי הרבה בוטים מתעלמים ממנו.

נוסחה רשמית (docs.polymarket.com/trading/fees):

    fee = C × feeRate × p × (1 − p)

כאשר C = מספר מניות ו-p = המחיר. המכפיל p(1−p) הוא הסיבה שהעמלה בשיאה
ב-0.50 (1.25 סנט למניה בשווקים של 0.05) ושואפת לאפס בקצוות.

שני כללים קריטיים:
  **מייקרים לא משלמים עמלה בכלל.** רק טאקרים.
  **Geopolitics פטור מעמלה לגמרי.**

המשמעות: אותה עסקה בדיוק יכולה להיות רווחית או מפסידה בהתאם לסקטור
ולשאלה אם היינו מייקר או טאקר. לכן זה לא "פרט קטן" — זה מה שקובע.
"""
from __future__ import annotations

from dataclasses import dataclass

# טבלת הקטגוריות מהדוקומנטציה הרשמית
CATEGORY_TAKER_RATES: dict[str, float] = {
    "geopolitics": 0.00,   # פטור לחלוטין
    "crypto": 0.01,        # כל הקריפטו למעט 5/15 דקות (שם 0.05)
    "politics": 0.01,      # בחירות = 0.05 — מטופל בנפרד
    "economics": 0.01,
    "macro": 0.01,
    "culture": 0.01,
    "weather": 0.01,
    "mentions": 0.01,
    "sports": 0.05,
    "finance": 0.05,
    "tech": 0.05,
    "other": 0.05,
}

ELECTION_PATTERN_RATE = 0.05   # politics שהם בחירות
CRYPTO_SHORT_RATE = 0.05       # BTC 5m/15m up-down

# סקטור שמסווג ע"י sectors.py → מפתח בטבלת העמלות
SECTOR_TO_FEE_KEY = {
    "sports": "sports",
    "crypto": "crypto",
    "macro": "economics",
    "politics": "politics",
    "geopolitics": "geopolitics",
    "tech": "tech",
    "culture": "culture",
    "other": "other",
}


@dataclass(frozen=True)
class FeeEstimate:
    rate: float
    per_share: float      # עמלה למניה (USDC)
    pct_of_notional: float
    source: str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.rate:.2%} · {self.per_share:.5f}/מניה ({self.pct_of_notional:.3%} מהנומינלי)"


def taker_fee(shares: float, price: float, rate: float) -> float:
    """הנוסחה הרשמית. מחזיר USDC."""
    if rate <= 0 or shares <= 0:
        return 0.0
    p = min(max(price, 0.0), 1.0)
    return round(shares * rate * p * (1.0 - p), 5)


def round_trip_fee_per_share(price: float, rate: float) -> float:
    """עמלת כניסה + יציאה לאותה מניה (בהנחה שהמחיר לא זז)."""
    return 2.0 * rate * price * (1.0 - price)


def rate_for(
    *,
    sector: str,
    question: str = "",
    slug: str = "",
    gamma_rate: float | None = None,
    fees_enabled: bool | None = None,
) -> FeeEstimate:
    """
    קובע את שיעור העמלה. סדר עדיפויות:
      1. מה ש-Gamma מדווח (feeSchedule.rate) — האמת מהשרת
      2. טבלת הקטגוריות הרשמית
      3. 0.05 כברירת מחדל שמרנית
    """
    if fees_enabled is False:
        return FeeEstimate(0.0, 0.0, 0.0, "fees_disabled")
    if gamma_rate is not None:
        return FeeEstimate(float(gamma_rate), 0.0, 0.0, "gamma")

    key = SECTOR_TO_FEE_KEY.get(sector, "other")
    text = f"{question} {slug}".lower()

    # חריגים בתוך politics
    if key == "politics" and any(w in text for w in (
        "election", "elect", "president", "nominee", "primary", "vote", "ballot",
    )):
        key = "election"

    # קריפטו 5/15 דקות
    if key == "crypto" and any(w in text for w in ("up or down", "5 minute", "15 minute", "up/down")):
        key = "crypto_short"

    if key == "election":
        rate = ELECTION_PATTERN_RATE
    elif key == "crypto_short":
        rate = CRYPTO_SHORT_RATE
    else:
        rate = CATEGORY_TAKER_RATES.get(key, 0.05)
    return FeeEstimate(rate, 0.0, 0.0, f"sector:{key}")


def estimate(price: float, rate: float, *, shares: float = 1.0, maker: bool = False) -> FeeEstimate:
    """אומדן עמלה למניה אחת (או למספר מניות)."""
    if maker:
        return FeeEstimate(0.0, 0.0, 0.0, "maker")
    per_share = taker_fee(shares, price, rate) / max(shares, 1e-9)
    notional = price if price > 0 else 1e-9
    return FeeEstimate(rate, per_share, per_share / notional, "taker")


def breakeven_move(price: float, rate: float, spread: float, maker: bool = False) -> float:
    """
    התנועה המינימלית בנקודות הסתברות כדי שהעסקה תצא ברווח.
    = ספרד מלא (כניסה ב-ask, יציאה ב-bid) + עמלות סבב.
    """
    fee = 0.0 if maker else round_trip_fee_per_share(price, rate)
    return spread + fee
