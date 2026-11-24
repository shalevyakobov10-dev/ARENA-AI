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
import math
import os
import time
from urllib.parse import urlencode

import httpx

from ..config import PerpsConfig
from .models import PerpBook, PerpFill, PerpOrder, utcnow

log = logging.getLogger(__name__)


class PerpsLiveDisabled(RuntimeError):
    pass


class PerpsExecutionUncertain(RuntimeError):
    """An exchange may have accepted an order but its actual execution is unconfirmed."""


def _positive_number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result <= 0:
        return None
    return result


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

    def _execution_uncertain(self, order: PerpOrder, detail: str) -> None:
        from ..runtime import write_halt

        reason = (
            f"PERPS execution outcome uncertain: {order.exchange} {order.symbol} "
            f"{order.action}; {detail}. Reconcile the exchange account before resuming."
        )
        try:
            write_halt(reason, source="execution_uncertain")
        except Exception as exc:  # noqa: BLE001
            log.critical("Could not persist execution-uncertain halt: %s", exc)
        log.critical(reason)
        raise PerpsExecutionUncertain(reason)

    def _confirmed_fill(
        self,
        order: PerpOrder,
        *,
        price: Any,
        size: Any,
        order_id: Any,
        taker_fee_bps: float | None,
        actual_leverage: float,
    ) -> PerpFill:
        px = _positive_number(price)
        qty = _positive_number(size)
        oid = str(order_id or "").strip()
        if px is None or qty is None or not oid:
            self._execution_uncertain(
                order, "exchange response omitted a positive filled quantity, average price, or order ID"
            )
        assert px is not None and qty is not None
        tolerance = max(1e-9, abs(float(order.size)) * 1e-6)
        if qty > float(order.size) + tolerance:
            self._execution_uncertain(
                order, f"reported fill size {qty:g} exceeds requested base size {order.size:g}"
            )
        notional = px * qty
        fee_bps = (
            float(taker_fee_bps)
            if taker_fee_bps is not None
            else float(self.cfg.taker_fee_bps)
        )
        fee = round(notional * fee_bps / 10_000.0, 8)
        return PerpFill(
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            action=order.action,
            price=px,
            size=qty,
            notional=round(notional, 8),
            leverage=float(actual_leverage),
            margin_delta=-(notional / max(1.0, float(actual_leverage))) if order.action == "OPEN" else 0.0,
            fee=fee,
            reason=order.reason,
            order_id=oid,
            ts=utcnow(),
        )

    def _okx_get_order(self, inst_id: str, order_id: str) -> dict:
        params = {"instId": inst_id, "ordId": order_id}
        path = "/api/v5/trade/order?" + urlencode(params)
        response = httpx.get(
            "https://www.okx.com" + path,
            headers=self._okx_headers("GET", path),
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("code")) != "0":
            raise RuntimeError(f"OKX order query rejected: {payload!r}")
        rows = payload.get("data") or []
        if not rows or not isinstance(rows[0], dict):
            raise RuntimeError("OKX order query returned no order details")
        return rows[0]

    def _okx_cancel_order(self, inst_id: str, order_id: str) -> None:
        path = "/api/v5/trade/cancel-order"
        body = json.dumps({"instId": inst_id, "ordId": order_id}, separators=(",", ":"))
        response = httpx.post(
            "https://www.okx.com" + path,
            content=body,
            headers=self._okx_headers("POST", path, body),
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("code")) != "0":
            raise RuntimeError(f"OKX cancel request rejected: {payload!r}")
        rows = payload.get("data") or []
        if rows and str(rows[0].get("sCode", "0")) != "0":
            raise RuntimeError(f"OKX cancel order failed: {rows[0]!r}")

    def _okx_confirm_fill(
        self,
        order: PerpOrder,
        *,
        inst_id: str,
        order_id: str,
        ct_val: float,
        taker_fee_bps: float | None,
        actual_leverage: float,
    ) -> PerpFill | None:
        terminal = {"filled", "canceled", "mmp_canceled"}
        row: dict | None = None
        for attempt in range(6):
            try:
                row = self._okx_get_order(inst_id, order_id)
            except Exception as exc:  # noqa: BLE001
                self._execution_uncertain(order, f"could not query accepted OKX order {order_id}: {exc}")
            state = str(row.get("state") or "").lower()
            if state in terminal:
                raw_contracts = row.get("accFillSz")
                if raw_contracts in (None, ""):
                    self._execution_uncertain(
                        order, f"OKX order details omitted accFillSz (order {order_id}, state={state})"
                    )
                try:
                    contracts = float(raw_contracts)
                except (TypeError, ValueError):
                    self._execution_uncertain(
                        order, f"OKX returned invalid accFillSz={raw_contracts!r} (order {order_id})"
                    )
                if not math.isfinite(contracts) or contracts < 0:
                    self._execution_uncertain(
                        order, f"OKX returned invalid accFillSz={raw_contracts!r} (order {order_id})"
                    )
                if contracts == 0:
                    if state == "filled":
                        self._execution_uncertain(
                            order, f"OKX reports state=filled but accFillSz is zero (order {order_id})"
                        )
                    return None
                avg_px = _positive_number(row.get("avgPx"))
                if avg_px is None:
                    self._execution_uncertain(
                        order, f"OKX reports {contracts:g} filled contracts but no avgPx (order {order_id})"
                    )
                return self._confirmed_fill(
                    order,
                    price=avg_px,
                    size=contracts * ct_val,
                    order_id=order_id,
                    taker_fee_bps=taker_fee_bps,
                    actual_leverage=actual_leverage,
                )
            if attempt < 5:
                time.sleep(0.2)

        # A market order must not be left resting after the bounded confirmation window.
        try:
            self._okx_cancel_order(inst_id, order_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("OKX cancellation after non-terminal market order failed (%s): %s", order_id, exc)

        for _ in range(4):
            try:
                row = self._okx_get_order(inst_id, order_id)
            except Exception as exc:  # noqa: BLE001
                self._execution_uncertain(order, f"cannot confirm final OKX state after cancel for {order_id}: {exc}")
            state = str(row.get("state") or "").lower()
            if state in terminal:
                raw_contracts = row.get("accFillSz")
                if raw_contracts in (None, ""):
                    self._execution_uncertain(
                        order, f"OKX final order details omitted accFillSz after cancellation (order {order_id})"
                    )
                try:
                    contracts = float(raw_contracts)
                except (TypeError, ValueError):
                    self._execution_uncertain(
                        order, f"OKX returned invalid final accFillSz={raw_contracts!r} (order {order_id})"
                    )
                if not math.isfinite(contracts) or contracts < 0:
                    self._execution_uncertain(
                        order, f"OKX returned invalid final accFillSz={raw_contracts!r} (order {order_id})"
                    )
                if contracts == 0:
                    return None
                avg_px = _positive_number(row.get("avgPx"))
                if avg_px is None:
                    self._execution_uncertain(
                        order, f"OKX reports {contracts:g} filled contracts but no avgPx after cancel ({order_id})"
                    )
                return self._confirmed_fill(
                    order,
                    price=avg_px,
                    size=contracts * ct_val,
                    order_id=order_id,
                    taker_fee_bps=taker_fee_bps,
                    actual_leverage=actual_leverage,
                )
            time.sleep(0.2)

        self._execution_uncertain(
            order, f"OKX order {order_id} remained non-terminal after market-order cancellation"
        )
        return None

    def execute(
        self,
        order: PerpOrder,
        *,
        ct_val: float = 1.0,
        lot_size: float = 0.001,
        tick_size: float = 0.01,
        taker_fee_bps: float | None = None,
        **_kw,
    ) -> PerpFill | None:
        if order.leverage > self.cfg.risk.max_leverage or order.leverage > 50.0:
            raise ValueError(f"חריגה מתקרת מינוף ב-Live: {order.leverage}")
        if order.size <= 0 or order.price <= 0 or ct_val <= 0 or lot_size <= 0:
            raise ValueError("גודל, מחיר, contract value וגודל lot חייבים להיות חיוביים")

        actual_leverage = float(max(1, int(order.leverage)))
        is_buy = (order.side == "LONG" and order.action == "OPEN") or (
            order.side == "SHORT" and order.action == "CLOSE"
        )

        if order.exchange == "okx" and self.has_okx:
            inst_id = f"{order.symbol.upper()}-USDT-SWAP"
            step_contracts = max(0.01, lot_size / ct_val)
            contracts = round_step(order.size / ct_val, step_contracts)
            if contracts < step_contracts:
                return None

            lev_path = "/api/v5/account/set-leverage"
            lev_body = json.dumps({
                "instId": inst_id,
                "lever": str(int(actual_leverage)),
                "mgnMode": "isolated",
            })
            try:
                lev_response = httpx.post(
                    "https://www.okx.com" + lev_path,
                    content=lev_body,
                    headers=self._okx_headers("POST", lev_path, lev_body),
                    timeout=10.0,
                )
                lev_response.raise_for_status()
                lev_payload = lev_response.json()
            except Exception as exc:  # noqa: BLE001
                log.warning("OKX leverage setup failed before order submission: %s", exc)
                return None
            if not isinstance(lev_payload, dict) or str(lev_payload.get("code")) != "0":
                log.warning("OKX leverage setup rejected: %s", lev_payload)
                return None
            lev_rows = lev_payload.get("data") or []
            if lev_rows and str(lev_rows[0].get("sCode", "0")) != "0":
                log.warning("OKX leverage setup rejected: %s", lev_rows[0])
                return None

            side = "buy" if is_buy else "sell"
            ord_path = "/api/v5/trade/order"
            ord_body = json.dumps({
                "instId": inst_id,
                "tdMode": "isolated",
                "side": side,
                "ordType": "market",
                "sz": str(contracts),
                "reduceOnly": bool(order.reduce_only),
            })
            try:
                response = httpx.post(
                    "https://www.okx.com" + ord_path,
                    content=ord_body,
                    headers=self._okx_headers("POST", ord_path, ord_body),
                    timeout=10.0,
                )
            except Exception as exc:  # noqa: BLE001 — POST may have reached OKX despite a client timeout
                self._execution_uncertain(order, f"OKX order submission transport error: {exc}")
            if response.status_code >= 500:
                self._execution_uncertain(order, f"OKX order submission returned HTTP {response.status_code}")
            try:
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    log.warning("OKX order rejected before acceptance: %s", exc)
                    return None
                self._execution_uncertain(order, f"OKX order submission HTTP error: {exc}")
            except Exception as exc:  # noqa: BLE001 — an unreadable 200 response is ambiguous
                self._execution_uncertain(order, f"cannot decode OKX order acknowledgement: {exc}")

            if not isinstance(payload, dict) or str(payload.get("code")) != "0":
                log.warning("OKX Live order rejected: %s", payload)
                return None
            rows = payload.get("data") or []
            if not rows or not isinstance(rows[0], dict):
                self._execution_uncertain(order, "OKX accepted order response did not include an order record")
            row = rows[0]
            if str(row.get("sCode", "0")) != "0":
                log.warning("OKX Live order rejected: %s", row)
                return None
            order_id = str(row.get("ordId") or "").strip()
            if not order_id:
                self._execution_uncertain(order, "OKX accepted order response omitted ordId")
            return self._okx_confirm_fill(
                order,
                inst_id=inst_id,
                order_id=order_id,
                ct_val=ct_val,
                taker_fee_bps=taker_fee_bps,
                actual_leverage=actual_leverage,
            )

        if order.exchange == "binance" and self.has_bn:
            ex_sym = f"{order.symbol.upper()}USDT"
            qty = round_step(order.size, lot_size)
            if qty < lot_size:
                return None
            hdr = {"X-MBX-APIKEY": self.bn_key}

            ts_ms = str(int(time.time() * 1000))
            margin_params = {
                "symbol": ex_sym,
                "marginType": "ISOLATED",
                "timestamp": ts_ms,
            }
            try:
                margin_response = httpx.post(
                    f"https://fapi.binance.com/fapi/v1/marginType?{self._binance_sign(margin_params)}",
                    headers=hdr,
                    timeout=10.0,
                )
                try:
                    margin_response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    try:
                        margin_data = exc.response.json()
                    except Exception:
                        raise
                    margin_code = int(margin_data.get("code", 0)) if isinstance(margin_data, dict) else 0
                    if margin_code != -4046:  # Already in isolated mode is the desired state.
                        raise
                else:
                    margin_data = margin_response.json()
                    margin_code = int(margin_data.get("code", 0)) if isinstance(margin_data, dict) else 0
                    if margin_code < 0 and margin_code != -4046:
                        log.warning("Binance isolated-margin setup rejected: %s", margin_data)
                        return None
            except Exception as exc:  # noqa: BLE001
                log.warning("Binance margin setup failed before order submission: %s", exc)
                return None

            ts_ms = str(int(time.time() * 1000))
            lev_params = {
                "symbol": ex_sym,
                "leverage": str(int(actual_leverage)),
                "timestamp": ts_ms,
            }
            try:
                lev_response = httpx.post(
                    f"https://fapi.binance.com/fapi/v1/leverage?{self._binance_sign(lev_params)}",
                    headers=hdr,
                    timeout=10.0,
                )
                lev_response.raise_for_status()
                lev_data = lev_response.json()
            except Exception as exc:  # noqa: BLE001
                log.warning("Binance leverage setup failed before order submission: %s", exc)
                return None
            lev_code = int(lev_data.get("code", 0)) if isinstance(lev_data, dict) else 0
            if lev_code < 0:
                log.warning("Binance leverage setup rejected: %s", lev_data)
                return None
            if isinstance(lev_data, dict) and lev_data.get("leverage") is not None:
                actual_leverage = float(lev_data["leverage"])

            params = {
                "symbol": ex_sym,
                "side": "BUY" if is_buy else "SELL",
                "type": "MARKET",
                "quantity": str(qty),
                "reduceOnly": "true" if order.reduce_only else "false",
                "newOrderRespType": "RESULT",
                "timestamp": str(int(time.time() * 1000)),
            }
            signed = self._binance_sign(params)
            try:
                response = httpx.post(
                    f"https://fapi.binance.com/fapi/v1/order?{signed}",
                    headers=hdr,
                    timeout=10.0,
                )
            except Exception as exc:  # noqa: BLE001 — POST outcome may be ambiguous
                self._execution_uncertain(order, f"Binance order submission transport error: {exc}")
            if response.status_code >= 500:
                self._execution_uncertain(order, f"Binance order submission returned HTTP {response.status_code}")
            try:
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    log.warning("Binance order rejected before acceptance: %s", exc)
                    return None
                self._execution_uncertain(order, f"Binance order submission HTTP error: {exc}")
            except Exception as exc:  # noqa: BLE001
                self._execution_uncertain(order, f"cannot decode Binance order result: {exc}")
            if not isinstance(data, dict):
                self._execution_uncertain(order, "Binance order result was not a JSON object")
            code = data.get("code")
            if code is not None:
                try:
                    if int(code) < 0:
                        log.warning("Binance Live order rejected: %s", data)
                        return None
                except (TypeError, ValueError):
                    self._execution_uncertain(order, "Binance order result contains an invalid code")
            status = str(data.get("status") or "").upper()
            executed = _positive_number(data.get("executedQty"))
            if executed is None:
                if status in {"CANCELED", "CANCELLED", "EXPIRED", "REJECTED"}:
                    return None
                self._execution_uncertain(
                    order, f"Binance market order has no confirmed executedQty (status={status or 'missing'})"
                )
            avg_px = _positive_number(data.get("avgPrice"))
            if avg_px is None:
                cum_quote = _positive_number(data.get("cumQuote"))
                if cum_quote is not None:
                    avg_px = cum_quote / executed
            if avg_px is None:
                self._execution_uncertain(order, "Binance reports executed quantity but no average fill price")
            if status not in {"FILLED", "PARTIALLY_FILLED", "EXPIRED", "CANCELED", "CANCELLED"}:
                self._execution_uncertain(order, f"unexpected Binance order status after fill: {status or 'missing'}")
            return self._confirmed_fill(
                order,
                price=avg_px,
                size=executed,
                order_id=data.get("orderId"),
                taker_fee_bps=taker_fee_bps,
                actual_leverage=actual_leverage,
            )

        if order.exchange == "hyperliquid" and self.has_hl:
            try:
                from hyperliquid.exchange import Exchange as HLExchange
                from eth_account import Account
            except ImportError as exc:
                raise PerpsLiveDisabled(
                    "נדרשת חבילת hyperliquid-python-sdk למסחר חי ישיר ב-Hyperliquid"
                ) from exc
            wallet = Account.from_key(self.hl_key)
            hl_ex = HLExchange(wallet)
            try:
                lev_result = hl_ex.update_leverage(int(actual_leverage), order.symbol.upper(), is_cross=False)
                if isinstance(lev_result, dict) and lev_result.get("status") not in (None, "ok"):
                    log.warning("Hyperliquid leverage setup rejected: %s", lev_result)
                    return None
                sz_hl = round_step(order.size, lot_size)
                if sz_hl < lot_size:
                    return None
                if order.action == "CLOSE" and order.reduce_only:
                    result = hl_ex.market_close(order.symbol.upper(), sz=sz_hl)
                else:
                    result = hl_ex.market_open(order.symbol.upper(), is_buy, sz_hl, px=None, slippage=0.01)
            except Exception as exc:  # noqa: BLE001 — SDK may lose response after submission
                self._execution_uncertain(order, f"Hyperliquid order transport/SDK error: {exc}")
            if not isinstance(result, dict):
                self._execution_uncertain(order, "Hyperliquid returned a non-object order result")
            if result.get("status") != "ok":
                log.warning("Hyperliquid order rejected: %s", result)
                return None
            try:
                statuses = result["response"]["data"]["statuses"]
            except (KeyError, TypeError):
                self._execution_uncertain(order, "Hyperliquid acknowledgement omitted response.data.statuses")
            if not isinstance(statuses, list) or len(statuses) != 1 or not isinstance(statuses[0], dict):
                self._execution_uncertain(order, "Hyperliquid returned an unexpected status vector")
            status_row = statuses[0]
            if "error" in status_row:
                log.warning("Hyperliquid order rejected: %s", status_row["error"])
                return None
            if "resting" in status_row:
                oid = status_row["resting"].get("oid")
                try:
                    if oid is not None:
                        hl_ex.cancel(order.symbol.upper(), int(oid))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not cancel unexpected resting Hyperliquid market order: %s", exc)
                self._execution_uncertain(
                    order, f"market order unexpectedly returned resting status (oid={oid}); cancellation requires reconciliation"
                )
            filled = status_row.get("filled")
            if not isinstance(filled, dict):
                self._execution_uncertain(order, "Hyperliquid response did not confirm a filled or rejected order")
            return self._confirmed_fill(
                order,
                price=filled.get("avgPx"),
                size=filled.get("totalSz"),
                order_id=filled.get("oid"),
                taker_fee_bps=taker_fee_bps,
                actual_leverage=actual_leverage,
            )

        raise PerpsLiveDisabled(f"לא הוגדרו מפתחות פעילים לבורסה {order.exchange}")

