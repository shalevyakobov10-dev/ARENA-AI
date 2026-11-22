"""
סיווג שווקים לסקטורים — כדי לדעת איפה האות עובד ואיפה לא.

הסיווג מבוסס מילות מפתח בשאלה/ב-slug (הנתונים האלה קיימים ב-Gamma).
הוא גס בכוונה: המטרה היא לא טסונומיה מושלמת אלא לבדוק אם יש הבדל
מובהק בין סוגי שווקים — ואם כן, לצמצם את היקום.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# סדר חשוב: הראשון שמתאים קובע
RULES: list[tuple[str, str]] = [
    ("sports", r"\b(nba|nfl|nhl|mlb|wnba|atp|wta|ufc|f1|nascar|cs2|counter-strike|"
               r"dota|valorant|lol|league of legends|premier league|la liga|serie a|"
               r"bundesliga|ligue 1|champions league|europa league|vs\.?\s|"
               r"spread:|moneyline|over/under|handicap|bo3|bo5|match)\b"),
    ("crypto", r"\b(bitcoin|btc|ethereum|eth|solana|sol|xrp|doge|cardano|crypto|"
               r"binance|coinbase)\b"),
    ("macro", r"\b(fed|fomc|interest rate|cpi|inflation|gdp|unemployment|recession|"
              r"treasury|ecb|rate cut|rate hike|tariff)\b"),
    ("politics", r"\b(election|president|prime minister|senate|congress|parliament|"
                 r"mayor|governor|nominee|impeach|shutdown|veto|minister)\b"),
    ("geopolitics", r"\b(iran|israel|russia|ukraine|china|taiwan|ceasefire|war|"
                    r"strike|nato|sanctions|airspace|hostage)\b"),
    ("tech", r"\b(openai|gpt|nvidia|apple|google|tesla|spacex|meta|microsoft|ai\b|"
             r"model|launch|iphone|starship)\b"),
    ("culture", r"\b(tweet|elon|kanye|taylor swift|album|movie|box office|oscar|"
                r"grammy|celebrity|affair|arrest|resign)\b"),
]


def classify(question: str, slug: str = "") -> str:
    text = f"{question} {slug}".lower()
    for name, pattern in RULES:
        if re.search(pattern, text):
            return name
    return "other"


@dataclass
class SectorStats:
    sector: str
    n: int = 0
    predicted: float = 0.0
    realized: float = 0.0
    hits: int = 0
    fees: float = 0.0        # סכום עמלות סבב (לפי הנוסחה הרשמית)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.n if self.n else 0.0

    @property
    def mean_predicted(self) -> float:
        return self.predicted / self.n if self.n else 0.0

    @property
    def mean_realized(self) -> float:
        return self.realized / self.n if self.n else 0.0

    @property
    def mean_fee(self) -> float:
        return self.fees / self.n if self.n else 0.0

    @property
    def net_of_cost(self) -> float:
        """רווח ממוצע לעסקה אחרי ספרד (~0.01) ואחרי עמלות סבב בפועל."""
        return self.mean_realized - 0.01 - self.mean_fee

    @property
    def bias(self) -> float:
        return (self.mean_predicted / self.mean_realized) if abs(self.mean_realized) > 1e-9 else float("inf")
