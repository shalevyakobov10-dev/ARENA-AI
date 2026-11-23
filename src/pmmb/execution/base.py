"""חשבון הפוזיציות (משותף ל-paper ול-live) + ממשק Broker."""
from __future__ import annotations

import logging
from typing import Protocol

from ..data.store import Store
from ..models import (
    Direction,
    Fill,
    Order,
    PortfolioSnapshot,
    Position,
    utcnow,
)

log = logging.getLogger(__name__)


class Broker(Protocol):
    mode: str

    def execute(self, order: Order, **kwargs) -> Fill | None: ...


class Portfolio:
    """
    הנהלת חשבונות: מזומן, פוזיציות, רווח ממומש.
    אין כאן IO למעט רישום ל-Store (אופציונלי) — קל לבדוק ב-unit tests.
    """

    def __init__(self, cash: float, mode: str = "paper", store: Store | None = None) -> None:
        self.starting_cash = cash
        self.cash = cash
        self.mode = mode
        self.store = store
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.realized_pnl_today = 0.0
        self.peak_equity = cash
        self._day = utcnow().date()

    # ------------------------------------------------------------------
    def roll_day_if_needed(self) -> None:
        today = utcnow().date()
        if today != self._day:
            self._day = today
            self.realized_pnl_today = 0.0

    # ------------------------------------------------------------------
    def apply_fill(self, fill: Fill) -> float:
        """מעדכן את החשבון ומחזיר רווח/הפסד ממומש מהמילוי הזה."""
        self.roll_day_if_needed()
        realized = 0.0

        if fill.side == "BUY":
            self.cash -= fill.price * fill.size + fill.fee
            pos = self.positions.get(fill.token_id)
            if pos is None:
                self.positions[fill.token_id] = Position(
                    token_id=fill.token_id,
                    condition_id=fill.condition_id,
                    direction="LONG",
                    size=fill.size,
                    avg_price=fill.price,
                    entry_score=0.0,
                    question=getattr(fill, "question", ""),
                )
            else:
                total = pos.size + fill.size
                pos.avg_price = (pos.avg_price * pos.size + fill.price * fill.size) / total
                pos.size = total
        else:
            self.cash += fill.price * fill.size - fill.fee
            pos = self.positions.get(fill.token_id)
            if pos is None:
                log.warning("מכירה ללא פוזיציה עבור %s — מתעלמים מהרווח הממומש",
                            fill.token_id[:12])
            else:
                closed = min(pos.size, fill.size)
                realized = (fill.price - pos.avg_price) * closed - fill.fee
                pos.size -= closed
                self.realized_pnl += realized
                self.realized_pnl_today += realized
                if pos.size <= 1e-9:
                    self.positions.pop(fill.token_id, None)

        if self.store:
            self.store.record_fill(fill, self.mode, realized=realized)
            if fill.token_id in self.positions:
                self.store.upsert_position(self.positions[fill.token_id], self.mode)
            elif fill.side == "SELL":
                self.store.close_position(fill.token_id, getattr(fill, "reason", ""), realized)

        return realized

    # ------------------------------------------------------------------
    def exposure(self, marks: dict[str, float] | None = None) -> float:
        total = 0.0
        for tid, pos in self.positions.items():
            mark = (marks or {}).get(tid, pos.avg_price)
            total += pos.size * mark
        return round(total, 6)

    def equity(self, marks: dict[str, float] | None = None) -> float:
        return round(self.cash + self.exposure(marks), 6)

    def snapshot(self, marks: dict[str, float] | None = None) -> PortfolioSnapshot:
        eq = self.equity(marks)
        self.peak_equity = max(self.peak_equity, eq)
        return PortfolioSnapshot(
            cash=round(self.cash, 6),
            equity=eq,
            exposure=self.exposure(marks),
            open_positions=len(self.positions),
            realized_pnl_today=round(self.realized_pnl_today, 6),
            peak_equity=self.peak_equity,
        )

    # ------------------------------------------------------------------
    def position_for(self, token_id: str) -> Position | None:
        return self.positions.get(token_id)

    def restore(self, positions: list[Position], cash: float) -> None:
        self.positions = {p.token_id: p for p in positions}
        self.cash = cash


def direction_to_token(direction: Direction) -> str:
    return {"LONG": "YES", "SHORT": "NO", "FLAT": "-"}[direction]
