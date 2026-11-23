"""Paper broker — סימולציה מול ספר הפקודות האמיתי, כולל החלקה ועמלות."""
from __future__ import annotations

import logging

from ..config import ExecutionConfig
from ..data.clob import Book, ClobClient
from ..fees import taker_fee
from ..models import Fill, Order, utcnow

log = logging.getLogger(__name__)


class PaperBroker:
    mode = "paper"

    def __init__(self, cfg: ExecutionConfig, clob: ClobClient) -> None:
        self.cfg = cfg
        self.clob = clob
        self.fills: list[Fill] = []

    # ------------------------------------------------------------------
    def execute(
        self,
        order: Order,
        *,
        book: Book | None = None,
        aggressive: bool = False,
        **_,
    ) -> Fill | None:
        """
        aggressive=True (יציאות): מהלכים deeper בספר ומאפשרים מילוי חלקי.
        עדיף לצאת חלקית במחיר גרוע מאשר להישאר עם פוזיציה שלא נסגרת.
        """
        book = book or self.clob.get_book(order.token_id)
        if book is None or not book.is_tradable():
            log.info("paper: אין ספר סחיר עבור %s", order.token_id[:12])
            return None

        est = self.clob.estimate_fill(
            book,
            order.side,
            order.notional,
            max_impact_pct=0.20 if aggressive else 0.05,
            allow_partial=aggressive,
        )
        if est is None:
            log.info("paper: הספר דק מדי (notional=%.2f)", order.notional)
            return None
        avg_price, fillable = est
        if not aggressive and fillable + 1e-9 < order.size * 0.95:
            log.info("paper: ביקש %.2f אבל הספר מכיל %.2f — לא ממלאים (FAK)", order.size, fillable)
            return None

        size = round(min(order.size, fillable), 2)
        if size <= 0:
            return None
        slip = self.cfg.slippage_bps / 10_000.0
        price = avg_price * (1 + slip) if order.side == "BUY" else avg_price * (1 - slip)
        price = min(0.999, max(0.001, round(price, 4)))
        notional = price * size
        # עמלת טאקר רשמית: C × rate × p × (1−p). מייקרים פטורים — לכן
        # עסקה "אגרסיבית" (חוצה את הספרד) משלמת, וביצוע פסיבי לא.
        if self.cfg.fee_mode == "off":
            fee = round(notional * self.cfg.taker_fee_bps / 10_000.0, 6)
        else:
            fee = taker_fee(size, price, order.fee_rate)

        fill = Fill(
            token_id=order.token_id,
            condition_id=order.condition_id,
            side=order.side,
            price=price,
            size=size,
            fee=fee,
            ts=utcnow(),
            order_id=f"paper-{len(self.fills) + 1}",
        )
        fill.reason = order.reason  # type: ignore[attr-defined]
        self.fills.append(fill)
        log.info(
            "📄 PAPER %s %.2f @ %.3f (≈%.2f USDC) | %s",
            order.side, size, price, notional, order.reason,
        )
        return fill
