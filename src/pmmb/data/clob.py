"""גישה ל-CLOB הציבורי: ספר פקודות, midpoint, spread, היסטוריית מחירים."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .http import HttpClient

log = logging.getLogger(__name__)


@dataclass
class Book:
    token_id: str
    best_bid: float | None
    best_ask: float | None
    bid_size: float
    ask_size: float
    tick_size: float = 0.01
    min_order_size: float = 5.0
    # רמות מלאות: (price, size) — ל-walk-the-book
    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float:
        if self.best_bid is None or self.best_ask is None:
            return 1.0
        return max(0.0, self.best_ask - self.best_bid)

    def is_tradable(self) -> bool:
        return self.best_bid is not None and self.best_ask is not None and self.best_ask > self.best_bid

    def depth(self, levels: int = 5) -> tuple[float, float]:
        """סך הנפח ב-N הרמות הטובות בכל צד: (bid_depth, ask_depth)."""
        bid = sum(size for _, size in self.bids[:levels])
        ask = sum(size for _, size in self.asks[:levels])
        return bid, ask

    def imbalance(self, levels: int = 5) -> float | None:
        """
        חוסר איזון בין הביקוש להיצע: (bid − ask) / (bid + ask), בטווח ‎-1..1‎.
        חיובי = לחץ קנייה. None אם הספר ריק.
        """
        bid, ask = self.depth(levels)
        total = bid + ask
        if total <= 0:
            return None
        return (bid - ask) / total


@dataclass
class Candle:
    ts: int
    price: float


class ClobClient:
    """קריאה בלבד — לא דורש אימות."""

    def __init__(self, http: HttpClient, history_ttl: float = 120.0) -> None:
        self.http = http
        self.history_ttl = history_ttl
        self._cache: dict[str, tuple[float, list[Candle]]] = {}

    # ------------------------------------------------------------------
    def get_book(self, token_id: str) -> Book | None:
        try:
            data = self.http.get("/book", params={"token_id": token_id})
        except ConnectionError as exc:
            log.warning("book נכשל עבור %s: %s", token_id[:12], exc)
            return None
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        # ה-API מחזיר מהטוב לגרוע; ליתר ביטחון ממיינים
        best_bid = max((float(b["price"]) for b in bids), default=None)
        best_ask = min((float(a["price"]) for a in asks), default=None)
        bid_size = sum(float(b["size"]) for b in bids if float(b["price"]) == best_bid) if best_bid is not None else 0.0
        ask_size = sum(float(a["size"]) for a in asks if float(a["price"]) == best_ask) if best_ask is not None else 0.0
        return Book(
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            bid_size=bid_size,
            ask_size=ask_size,
            tick_size=float(data.get("tick_size") or 0.01),
            min_order_size=float(data.get("min_order_size") or 5.0),
            bids=sorted(((float(b["price"]), float(b["size"])) for b in bids), key=lambda x: -x[0]),
            asks=sorted(((float(a["price"]), float(a["size"])) for a in asks), key=lambda x: x[0]),
        )

    def get_resolution(self, condition_id: str, token_id: str) -> float | None:
        """מחזיר 1.0 / 0.0 אם השוק הוכרע ב-CLOB, אחרת None."""
        if not condition_id:
            return None
        try:
            data = self.http.get(f"/markets/{condition_id}")
        except ConnectionError:
            return None
        if not isinstance(data, dict) or not data.get("closed"):
            return None
        for t in data.get("tokens") or []:
            if str(t.get("token_id")) == str(token_id):
                if t.get("winner") is True:
                    return 1.0
                if t.get("winner") is False:
                    return 0.0
                px = t.get("price")
                if px in (0, 1, 0.0, 1.0):
                    return float(px)
        return None

    def get_midpoint(self, token_id: str) -> float | None:
        try:
            data = self.http.get("/midpoint", params={"token_id": token_id})
            return float(data["mid"])
        except (ConnectionError, KeyError, TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    def get_history(
        self,
        token_id: str,
        fidelity_min: int = 5,
        lookback_candles: int = 144,
        use_cache: bool = True,
        chunk_hours: int = 168,
    ) -> list[Candle]:
        """
        היסטוריית מחירים. מחזיר רשימה עולה בזמן (עד lookback_candles נרות אחרונים).

        מגבלה אמיתית של ה-API: טווח של יותר מ~7 ימים בבקשה אחת מחזיר
        "interval is too long". לכן משיכה מקוטעת (chunking) לאחור.
        """
        key = f"{token_id}:{fidelity_min}:{lookback_candles}"
        now_ts = time.time()
        if use_cache and key in self._cache:
            cached_at, candles = self._cache[key]
            if now_ts - cached_at < self.history_ttl:
                return candles

        end = int(now_ts)
        span_needed = int(lookback_candles * fidelity_min * 60)
        collected: dict[int, float] = {}
        chunk = min(chunk_hours, 168) * 3600
        max_chunks = max(2, min(12, span_needed // chunk + 1))

        for i in range(max_chunks):
            chunk_end = end - i * chunk
            chunk_start = chunk_end - chunk
            if chunk_start < 0:
                break
            try:
                data = self.http.get(
                    "/prices-history",
                    params={
                        "market": token_id,
                        "startTs": chunk_start,
                        "endTs": chunk_end,
                        "fidelity": fidelity_min,
                    },
                )
            except ConnectionError:
                log.debug("chunk %d נכשל עבור %s", i, token_id[:12])
                break
            hist = data.get("history") or []
            if not hist:
                # אין נתונים בחלון הזה — לרוב השוק נוצר אחר כך
                if collected:
                    break
                continue
            for h in hist:
                if h.get("p") is not None:
                    collected[int(h["t"])] = float(h["p"])
            if len(collected) >= lookback_candles:
                break

        candles = [Candle(ts=ts, price=collected[ts]) for ts in sorted(collected)][-lookback_candles:]
        self._cache[key] = (now_ts, candles)
        return candles

    # ------------------------------------------------------------------
    def estimate_fill(
        self,
        book: Book,
        side: str,
        notional_usdc: float,
        max_impact_pct: float = 0.02,
        allow_partial: bool = False,
    ) -> tuple[float, float] | None:
        """
        אומדן מילוי ב-walk-the-book על הרמות האמיתיות.
        מחזיר (מחיר_ממוצע, גודל_במניות) או None אם הספר דק / ההשפעה גדולה מדי.
        """
        if book is None or not book.is_tradable() or notional_usdc <= 0:
            return None

        levels = book.asks if side == "BUY" else book.bids
        if not levels:
            return None

        ref = book.best_ask if side == "BUY" else book.best_bid
        if ref is None:
            return None
        max_dev = ref * (1 + max_impact_pct) if side == "BUY" else ref * (1 - max_impact_pct)

        remaining_cash = notional_usdc
        filled = 0.0
        cost = 0.0
        for price, size in levels:
            if price <= 0:
                continue
            if (side == "BUY" and price > max_dev) or (side == "SELL" and price < max_dev):
                break
            take = min(size, remaining_cash / price)
            if take <= 0:
                break
            filled += take
            cost += take * price
            remaining_cash -= take * price
            if remaining_cash <= 1e-9:
                break

        if filled <= 0:
            return None
        # הספר לא הספיק. בפקודת FAK רגילה — מבטלים. ביציאה (allow_partial)
        # עדיף למלא חלק מהפוזיציה מאשר להיתקע עם סיכון פתוח.
        if remaining_cash > 0.05 * notional_usdc and not allow_partial:
            return None
        return cost / filled, filled
