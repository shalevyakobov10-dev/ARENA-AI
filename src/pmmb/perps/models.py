"""מודלי דאטה למסחר בחוזים תמידיים (Perpetual Futures) עד מינוף ×50."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class PerpInstrument:
    symbol: str                     # נורמלי: BTC, ETH, SOL...
    exchange: str                   # okx | hyperliquid | binance
    exchange_symbol: str            # BTC-USDT-SWAP | BTC | BTCUSDT
    max_leverage: float
    mark_price: float
    index_price: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    volume_24h_usd: float = 0.0
    open_interest_usd: float = 0.0
    funding_1h: float = 0.0         # מנורמל לשעה (OKX 8h / 8, HL 1h)
    okx_funding_1h: float | None = None
    hl_funding_1h: float | None = None
    tick_size: float = 0.01
    lot_size: float = 0.001
    contract_val: float = 1.0       # OKX ctVal; 1.0 ב-HL/Binance
    taker_fee_bps: float = 3.5
    maker_fee_bps: float = 1.0
    mmr: float = 0.005              # Maintenance Margin Rate (~0.5%)
    funding_interval_hours: float = 1.0

    @property
    def mid_price(self) -> float:
        if self.best_bid > 0 and self.best_ask > 0:
            return (self.best_bid + self.best_ask) / 2.0
        return self.mark_price

    @property
    def spread_bps(self) -> float:
        mid = self.mid_price
        if self.best_bid <= 0 or self.best_ask <= 0 or mid <= 0:
            return 0.0
        return max(0.0, (self.best_ask - self.best_bid) / mid * 10_000.0)


@dataclass
class PerpCandle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    funding_rate: float = 0.0


@dataclass
class PerpBook:
    symbol: str
    exchange: str
    best_bid: float | None
    best_ask: float | None
    bids: list[tuple[float, float]] = field(default_factory=list)   # (price, base_qty)
    asks: list[tuple[float, float]] = field(default_factory=list)   # (price, base_qty)

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread_bps(self) -> float:
        m = self.mid
        if not m or self.best_bid is None or self.best_ask is None:
            return 9999.0
        return max(0.0, (self.best_ask - self.best_bid) / m * 10_000.0)

    def is_tradable(self) -> bool:
        return bool(self.best_bid and self.best_ask and self.best_ask > self.best_bid)

    def depth_usd(self, levels: int = 8) -> tuple[float, float]:
        bid_u = sum(px * qty for px, qty in self.bids[:levels])
        ask_u = sum(px * qty for px, qty in self.asks[:levels])
        return bid_u, ask_u

    def imbalance(self, levels: int = 8) -> float | None:
        bid_u, ask_u = self.depth_usd(levels)
        tot = bid_u + ask_u
        if tot <= 0:
            return None
        return (bid_u - ask_u) / tot


@dataclass
class PerpSignal:
    symbol: str
    exchange: str
    direction: Literal["LONG", "SHORT", "FLAT"]
    regime: str                     # TREND_UP | TREND_DOWN | RANGE | SHOCK
    strategy: str                   # pullback | meanrev | none
    score: float
    tier: str                       # A+ | A | B
    price: float
    atr: float
    stop_price: float | None
    take_profit_price: float | None
    recommended_leverage: float
    reason: str
    features: dict[str, float | str] = field(default_factory=dict)
    ts: datetime = field(default_factory=utcnow)


@dataclass
class PerpOrder:
    symbol: str
    exchange: str
    side: Literal["LONG", "SHORT"]
    action: Literal["OPEN", "CLOSE"]
    price: float
    size: float                     # בכמות נכס בסיס (BTC, ETH...)
    leverage: float
    reduce_only: bool = False
    reason: str = ""


@dataclass
class PerpFill:
    symbol: str
    exchange: str
    side: Literal["LONG", "SHORT"]
    action: Literal["OPEN", "CLOSE", "LIQUIDATION"]
    price: float
    size: float
    notional: float
    leverage: float
    margin_delta: float
    fee: float = 0.0
    funding: float = 0.0
    realized: float = 0.0
    reason: str = ""
    order_id: str = ""
    ts: datetime = field(default_factory=utcnow)


@dataclass
class PerpPosition:
    symbol: str
    exchange: str
    side: Literal["LONG", "SHORT"]
    size: float
    entry_price: float
    notional: float
    leverage: float
    margin_used: float
    liquidation_price: float
    stop_price: float
    target_price: float
    highest_price: float
    lowest_price: float
    atr: float = 0.0
    strategy: str = ""
    regime: str = ""
    entry_score: float = 0.0
    accumulated_funding: float = 0.0
    fees_paid: float = 0.0
    opened_at: datetime = field(default_factory=utcnow)
    last_funding_ts: int = 0

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.side == "LONG":
            return (mark_price - self.entry_price) * self.size
        return (self.entry_price - mark_price) * self.size

    def roe_pct(self, mark_price: float) -> float:
        if self.margin_used <= 0:
            return 0.0
        return self.unrealized_pnl(mark_price) / self.margin_used * 100.0
