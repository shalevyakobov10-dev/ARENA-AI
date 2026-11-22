"""מודלים עסקיים — אובייקטים טיפשים, בלי לוגיקה של IO."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Side = Literal["BUY", "SELL"]
Direction = Literal["LONG", "SHORT", "FLAT"]  # LONG = קניית YES, SHORT = קניית NO


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def to_ts(dt: datetime) -> int:
    return int(dt.timestamp())


# --------------------------------------------------------------------------
#  שווקים
# --------------------------------------------------------------------------
@dataclass
class Market:
    """שוק בינארי בודד מפורק לשני טוקנים (YES / NO)."""

    condition_id: str
    question: str
    slug: str
    yes_token_id: str
    no_token_id: str
    yes_price: float
    no_price: float
    spread: float
    volume_24h: float
    liquidity: float
    end_date: datetime | None
    tick_size: float = 0.01
    min_order_size: float = 5.0
    neg_risk: bool = False
    tags: list[str] = field(default_factory=list)
    taker_fee_rate: float = 0.0     # שיעור העמלה לטאקר (0 = פטור)
    fees_enabled: bool = False
    sector: str = "other"
    event_id: str = ""              # מזהה אירוע אב (מונע ריכוז כפול באותו אירוע)

    # --- עזר ---
    @property
    def hours_to_resolution(self) -> float:
        if self.end_date is None:
            return float("inf")
        return (self.end_date - utcnow()).total_seconds() / 3600.0

    def token_for(self, direction: Direction) -> str:
        return self.yes_token_id if direction == "LONG" else self.no_token_id

    def price_for(self, direction: Direction) -> float:
        return self.yes_price if direction == "LONG" else self.no_price

    @classmethod
    def from_gamma(cls, m: dict) -> "Market | None":
        """ממיר אובייקט Gamma API ל-Market. מחזיר None אם השוק לא סחיר."""
        try:
            if not m.get("enableOrderBook", True) or m.get("closed") or m.get("archived"):
                return None
            if not m.get("acceptingOrders", True):
                return None
            tokens = m.get("clobTokenIds")
            outcomes = m.get("outcomes")
            prices = m.get("outcomePrices")
            tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
            outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
            prices = json.loads(prices) if isinstance(prices, str) else prices
            if not tokens or len(tokens) < 2 or not prices or len(prices) < 2:
                return None

            # מוודאים שמיפוי YES/NO נכון (יש שווקים שהסדר שלהם הפוך)
            labels = [str(o).strip().lower() for o in (outcomes or [])]
            yes_idx, no_idx = 0, 1
            if len(labels) >= 2:
                if labels[1] == "yes":
                    yes_idx, no_idx = 1, 0
                elif labels[0] == "no":
                    yes_idx, no_idx = 1, 0

            end = m.get("endDate") or m.get("endDateIso")
            end_dt = None
            if end:
                try:
                    end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                except ValueError:
                    end_dt = None

            bid, ask = _f(m.get("bestBid")), _f(m.get("bestAsk"))
            yes_p = _f(prices[yes_idx])
            no_p = _f(prices[no_idx])
            spread = (ask - bid) if (bid is not None and ask is not None and ask >= bid) else abs(1.0 - yes_p - no_p) or 0.02

            from .fees import rate_for
            from .sectors import classify

            sector = classify(m.get("question", ""), m.get("slug", ""))
            schedule = m.get("feeSchedule") or {}
            gamma_rate = schedule.get("rate")
            fees_enabled = m.get("feesEnabled")
            fee = rate_for(
                sector=sector,
                question=m.get("question", ""),
                slug=m.get("slug", ""),
                gamma_rate=float(gamma_rate) if gamma_rate is not None else None,
                fees_enabled=fees_enabled,
            )

            events = m.get("events") or []
            ev0 = events[0] if events and isinstance(events[0], dict) else {}
            ev_id = str(ev0.get("id") or ev0.get("slug") or "")

            return cls(
                condition_id=m.get("conditionId", ""),
                question=m.get("question", ""),
                slug=m.get("slug", ""),
                yes_token_id=str(tokens[yes_idx]),
                no_token_id=str(tokens[no_idx]),
                yes_price=yes_p,
                no_price=no_p,
                spread=max(spread, 0.0),
                volume_24h=_f(m.get("volume24hr")) or 0.0,
                liquidity=_f(m.get("liquidityNum") or m.get("liquidity")) or 0.0,
                end_date=end_dt,
                tick_size=_f(m.get("orderPriceMinTickSize")) or 0.01,
                min_order_size=_f(m.get("orderMinSize")) or 5.0,
                neg_risk=bool(m.get("negRisk")),
                taker_fee_rate=fee.rate,
                fees_enabled=bool(fees_enabled),
                sector=sector,
                event_id=ev_id,
                tags=[t.get("label", "") for t in ev0.get("tags", [])] if ev0 else [],
            )
        except (TypeError, ValueError, KeyError, IndexError, AttributeError):
            return None


def _f(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
#  סיגנלים
# --------------------------------------------------------------------------
@dataclass
class Signal:
    """פלט מנוע הסיגנלים עבור שוק אחד."""

    condition_id: str
    token_id: str
    direction: Direction
    score: float              # 0..1 עוצמת הסיגנל
    fair_price: float         # ההסתברות שהמנוע מעריך
    market_price: float
    edge: float               # fair - market (בנקודות הסתברות)
    reason: str               # הסבר קריא ללוג
    features: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    @property
    def is_tradeable(self) -> bool:
        return self.direction != "FLAT" and self.edge > 0


# --------------------------------------------------------------------------
#  פקודות ומסחר
# --------------------------------------------------------------------------
@dataclass
class Order:
    token_id: str
    side: Side
    price: float
    size: float                    # במניות (shares) ולא ב-USDC
    condition_id: str = ""
    reason: str = ""
    client_id: str = ""
    fee_rate: float = 0.0          # שיעור עמלת הטאקר של השוק

    @property
    def notional(self) -> float:
        return round(self.price * self.size, 6)


@dataclass
class Fill:
    token_id: str
    condition_id: str
    side: Side
    price: float
    size: float
    fee: float = 0.0
    ts: datetime = field(default_factory=utcnow)
    order_id: str = ""

    @property
    def notional(self) -> float:
        return round(self.price * self.size, 6)

    @property
    def cash_delta(self) -> float:
        """תנועת מזומן: קנייה מוציאה כסף, מכירה מכניסה."""
        sign = -1.0 if self.side == "BUY" else 1.0
        return round(sign * self.notional - self.fee, 6)


@dataclass
class Position:
    token_id: str
    condition_id: str
    direction: Direction
    size: float
    avg_price: float
    opened_at: datetime = field(default_factory=utcnow)
    entry_score: float = 0.0
    stop_price: float | None = None
    target_price: float | None = None
    question: str = ""
    event_id: str = ""

    @property
    def notional_at_cost(self) -> float:
        return round(self.size * self.avg_price, 6)

    def pnl(self, mark_price: float) -> float:
        return round((mark_price - self.avg_price) * self.size, 6)

    def pnl_pct(self, mark_price: float) -> float:
        if self.avg_price <= 0:
            return 0.0
        return (mark_price - self.avg_price) / self.avg_price


@dataclass
class RiskDecision:
    approved: bool
    size: float = 0.0
    notional: float = 0.0
    reason: str = ""


@dataclass
class PortfolioSnapshot:
    cash: float
    equity: float
    exposure: float
    open_positions: int
    realized_pnl_today: float
    peak_equity: float
    ts: datetime = field(default_factory=utcnow)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)
