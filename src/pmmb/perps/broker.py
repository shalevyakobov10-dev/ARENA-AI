"""
ברוקרים לביצוע PERPS:
  - PaperPerpBroker: מדמה ביצוע מול L2 Book אמיתי (החלקת Slippage, עמלות Taker, Isolated Margin)
  - LivePerpBroker: מוגן 3 שכבות (PerpsConfig.mode='live' + PMMB_PERPS_LIVE_CONFIRM=YES + מפתח בורסה)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from urllib.parse import urlencode

import httpx

from ..config import PerpsConfig
from .models import PerpBook, PerpFill, PerpOrder, utcnow

log = logging.getLogger(__name__)


class PerpsLiveDisabled(RuntimeError):
    pass


def estimate_book_fill(book: PerpBook, is_buy: bool, notional_usd: float) -> tuple[float, float] | None:
    """מחלץ מחיר מילוי ממוצע וכמות זמינה ב-L2 Book."""
    levels = book.asks if is_buy else book.bids
    if not levels:
        ref = book.best_ask if is_buy else book.best_bid
        if ref is None or ref <= 0:
            return None
        return ref, notional_usd / ref

    rem_usd = notional_usd
    filled_qty = 0.0
    spent_usd = 0.0
    for px, qty in levels:
        lvl_usd = px * qty
        take_usd = min(rem_usd, lvl_usd)
        filled_qty += take_usd / px
        spent_usd += take_usd
        rem_usd -= take_usd
        if rem_usd <= 1e-6:
            break
    if filled_qty <= 0:
        return None
    return spent_usd / filled_qty, filled_qty


def round_step(val: float, step: float) -> float:
    """חיתוך מדויק לפי גודל לוט/טיק של הבורסה למניעת דחיית Precision."""
    if step <= 0:
        return round(val, 6)
    import math
    n = math.floor(val / step + 1e-9)
    dec = max(0, min(8, -int(math.floor(math.log10(step))) if step < 1 else 0))
    return round(n * step, dec)


class PaperPerpBroker:
    mode = "paper"

    def __init__(self, cfg: PerpsConfig) -> None:
        self.cfg = cfg
        self._seq = 0

    def execute(
        self,
        order: PerpOrder,
        *,
        book: PerpBook | None = None,
        taker_fee_bps: float | None = None,
        **_kw,
    ) -> PerpFill | None:
        is_buy = (order.side == "LONG" and order.action == "OPEN") or (
            order.side == "SHORT" and order.action == "CLOSE"
        )
        ref_px = order.price
        if book is not None and book.is_tradable():
            est = estimate_book_fill(book, is_buy, order.price * order.size)
            if est is not None:
                ref_px = est[0]

        slip = self.cfg.slippage_bps / 10_000.0
        fill_px = ref_px * (1.0 + slip) if is_buy else ref_px * (1.0 - slip)
        fill_px = max(1e-6, round(fill_px, 6))
        notional = fill_px * order.size
        fee_bps = taker_fee_bps if taker_fee_bps is not None else self.cfg.taker_fee_bps
        fee = round(notional * fee_bps / 10_000.0, 6)
        margin_delta = -(notional / max(1.0, order.leverage)) if order.action == "OPEN" else 0.0

        self._seq += 1
        return PerpFill(
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            action=order.action,
            price=fill_px,
            size=order.size,
            notional=round(notional, 4),
            leverage=order.leverage,
            margin_delta=round(margin_delta, 4),
            fee=fee,
            reason=order.reason,
            order_id=f"perp-paper-{self._seq}",
            ts=utcnow(),
        )


class LivePerpBroker:
    """שכבת Live לחוזים תמידיים (OKX / Binance Isolated Margin) — דורשת אישור כפול + מפתחות בורסה."""
    mode = "live"

    def __init__(self, cfg: PerpsConfig) -> None:
        if cfg.mode != "live":
            raise PerpsLiveDisabled("perps.mode אינו live")
        if os.getenv("PMMB_PERPS_LIVE_CONFIRM", "").strip().upper() != "YES":
            raise PerpsLiveDisabled("נדרש PMMB_PERPS_LIVE_CONFIRM=YES להרצת Perps Live")
        self.okx_key = os.getenv("OKX_API_KEY", "")
        self.okx_secret = os.getenv("OKX_API_SECRET", "")
        self.okx_pass = os.getenv("OKX_PASSPHRASE", "")
        self.bn_key = os.getenv("BINANCE_API_KEY", "")
        self.bn_secret = os.getenv("BINANCE_API_SECRET", "")
        self.hl_key = os.getenv("PMMB_HL_PRIVATE_KEY", "")
        self.has_okx = bool(self.okx_key and self.okx_secret and self.okx_pass)
        self.has_bn = bool(self.bn_key and self.bn_secret)
        self.has_hl = bool(self.hl_key)
        if not (self.has_okx or self.has_bn or self.has_hl):
            raise PerpsLiveDisabled("חסרים מפתחות API לבורסה (OKX / Binance / Hyperliquid)")
        self.cfg = cfg

    def _okx_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        ts = utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        msg = f"{ts}{method.upper()}{path}{body}"
        sig = base64.b64encode(
            hmac.new(self.okx_secret.encode(), msg.encode(), hashlib.sha256).digest()
        ).decode()
        return {
            "OK-ACCESS-KEY": self.okx_key,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.okx_pass,
            "Content-Type": "application/json",
        }

    def _binance_sign(self, params: dict[str, str]) -> str:
        qs = urlencode(params)
        sig = hmac.new(self.bn_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        return f"{qs}&signature={sig}"

    def execute(self, order: PerpOrder, *, ct_val: float = 1.0, lot_size: float = 0.001, tick_size: float = 0.01, **_kw) -> PerpFill | None:
        if order.leverage > self.cfg.risk.max_leverage or order.leverage > 50.0:
            raise ValueError(f"חריגה מתקרת מינוף ב-Live: {order.leverage}")
        if order.exchange == "okx" and self.has_okx:
            inst_id = f"{order.symbol.upper()}-USDT-SWAP"
            lev_body = json.dumps({"instId": inst_id, "lever": str(int(order.leverage)), "mgnMode": "isolated"})
            httpx.post(
                "https://www.okx.com/api/v5/account/set-leverage",
                content=lev_body,
                headers=self._okx_headers("POST", "/api/v5/account/set-leverage", lev_body),
                timeout=10.0,
            ).raise_for_status()
            side = "buy" if ((order.side == "LONG" and order.action == "OPEN") or (order.side == "SHORT" and order.action == "CLOSE")) else "sell"
            step_c = max(0.01, lot_size / max(1e-9, ct_val))
            sz_contracts = max(step_c, round_step(order.size / max(1e-9, ct_val), step_c))
            ord_body = json.dumps({
                "instId": inst_id,
                "tdMode": "isolated",
                "side": side,
                "ordType": "market",
                "sz": str(sz_contracts),
                "reduceOnly": bool(order.reduce_only),
            })
            resp = httpx.post(
                "https://www.okx.com/api/v5/trade/order",
                content=ord_body,
                headers=self._okx_headers("POST", "/api/v5/trade/order", ord_body),
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if str(data.get("code")) != "0":
                log.warning("OKX Live order rejected: %s", data)
                return None
            oid = str((data.get("data") or [{}])[0].get("ordId") or "okx-live")
            exec_sz = round(sz_contracts * ct_val, 6)
            notional = order.price * exec_sz
            fee = round(notional * self.cfg.taker_fee_bps / 10_000.0, 6)
            return PerpFill(
                symbol=order.symbol, exchange="okx", side=order.side, action=order.action,
                price=order.price, size=exec_sz, notional=notional, leverage=order.leverage,
                margin_delta=-(notional / order.leverage) if order.action == "OPEN" else 0.0,
                fee=fee, reason=order.reason, order_id=oid, ts=utcnow(),
            )

        if order.exchange == "binance" and self.has_bn:
            ex_sym = f"{order.symbol.upper()}USDT"
            ts_ms = str(int(time.time() * 1000))
            hdr = {"X-MBX-APIKEY": self.bn_key}
            httpx.post(
                f"https://fapi.binance.com/fapi/v1/marginType?{self._binance_sign({'symbol': ex_sym, 'marginType': 'ISOLATED', 'timestamp': ts_ms})}",
                headers=hdr, timeout=10.0,
            )
            httpx.post(
                f"https://fapi.binance.com/fapi/v1/leverage?{self._binance_sign({'symbol': ex_sym, 'leverage': str(int(order.leverage)), 'timestamp': ts_ms})}",
                headers=hdr, timeout=10.0,
            ).raise_for_status()
            side = "BUY" if ((order.side == "LONG" and order.action == "OPEN") or (order.side == "SHORT" and order.action == "CLOSE")) else "SELL"
            qty_str = str(max(lot_size, round_step(order.size, lot_size)))
            q = self._binance_sign({
                "symbol": ex_sym, "side": side, "type": "MARKET",
                "quantity": qty_str,
                "reduceOnly": "true" if order.reduce_only else "false",
                "timestamp": str(int(time.time() * 1000)),
            })
            resp = httpx.post(f"https://fapi.binance.com/fapi/v1/order?{q}", headers=hdr, timeout=10.0)
            resp.raise_for_status()
            d = resp.json()
            px = float(d.get("avgPrice") or order.price)
            qty = float(d.get("executedQty") or qty_str)
            notional = px * qty
            return PerpFill(
                symbol=order.symbol, exchange="binance", side=order.side, action=order.action,
                price=px, size=qty, notional=notional, leverage=order.leverage,
                margin_delta=-(notional / order.leverage) if order.action == "OPEN" else 0.0,
                fee=round(notional * self.cfg.taker_fee_bps / 10_000.0, 6),
                reason=order.reason, order_id=str(d.get("orderId") or "bn-live"), ts=utcnow(),
            )

        if order.exchange == "hyperliquid" and self.has_hl:
            try:
                from hyperliquid.exchange import Exchange as HLExchange
                from eth_account import Account
            except ImportError as exc:
                raise PerpsLiveDisabled("נדרשת חבילת hyperliquid-python-sdk למסחר חי ישיר ב-Hyperliquid (או הגדר מפתחות OKX/Binance)") from exc
            wallet = Account.from_key(self.hl_key)
            hl_ex = HLExchange(wallet)
            hl_ex.update_leverage(int(order.leverage), order.symbol.upper(), is_cross=False)
            is_buy = (order.side == "LONG" and order.action == "OPEN") or (order.side == "SHORT" and order.action == "CLOSE")
            sz_hl = max(lot_size, round_step(order.size, lot_size))
            res = hl_ex.market_open(order.symbol.upper(), is_buy, sz_hl, px=None, slippage=0.01) if not order.reduce_only else hl_ex.market_close(order.symbol.upper(), sz=sz_hl)
            notional = order.price * sz_hl
            return PerpFill(
                symbol=order.symbol, exchange="hyperliquid", side=order.side, action=order.action,
                price=order.price, size=sz_hl, notional=notional, leverage=order.leverage,
                margin_delta=-(notional / order.leverage) if order.action == "OPEN" else 0.0,
                fee=round(notional * self.cfg.taker_fee_bps / 10_000.0, 6),
                reason=order.reason, order_id=str(res.get("status") or "hl-live"), ts=utcnow(),
            )

        raise PerpsLiveDisabled(f"לא הוגדרו מפתחות פעילים לבורסה {order.exchange}")
