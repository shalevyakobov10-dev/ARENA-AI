"""ממשק מנוע סיגנלים — כדי שיהיה אפשר להחליף אסטרטגיה בלי לגעת באינג'ין."""
from __future__ import annotations

from typing import Protocol, Sequence

from ..models import Market, Signal


class SignalEngine(Protocol):
    name: str

    def evaluate(
        self,
        market: Market,
        prices: Sequence[float],
        *,
        market_price: float,
        spread: float,
        extra: dict | None = None,
    ) -> Signal:
        """מחזיר Signal (direction='FLAT' אם אין סיגנל)."""
        ...
