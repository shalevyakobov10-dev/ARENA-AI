"""
Live broker — פקודות אמיתיות ב-CLOB דרך py-clob-client.

⚠️  מוגן בשלוש שכבות:
    1. execution.mode חייב להיות live
    2. PMMB_PRIVATE_KEY חייב להיות מוגדר
    3. PMMB_LIVE_CONFIRM חייב להכיל את המחרוזת המדויקת "I-UNDERSTAND-THE-RISK"
"""
from __future__ import annotations

import logging
import os
from typing import Any

from ..config import ExecutionConfig
from ..fees import taker_fee
from ..models import Fill, Order, utcnow

log = logging.getLogger(__name__)

CONFIRM_PHRASE = "I-UNDERSTAND-THE-RISK"


class LiveTradingDisabled(RuntimeError):
    pass


def _f(val: Any) -> float | None:
    try:
        if val in (None, ""):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_order_response(resp: Any, order: Order, *, fee_mode: str = "model") -> Fill | None:
    """
    מפרש תשובת post_order של Polymarket CLOB בצורה בטוחה.
    עיקרון: אם ההזמנה במצב live/unmatched ולא התמלאה — לא משקרים ומחזירים None.
    """
    if not isinstance(resp, dict) or not resp.get("success", False):
        return None

    status = str(resp.get("status") or "").strip().lower()
    matched = _f(resp.get("size_matched"))
    making = _f(resp.get("makingAmount"))
    taking = _f(resp.get("takingAmount"))

    size = 0.0
    price = order.price

    if matched is not None and matched > 0:
        size = matched
    elif making and taking and making > 0 and taking > 0:
        if order.side == "BUY":
            implied = making / taking
            if 0.001 <= implied <= 0.999 and 0.4 * order.price <= implied <= 2.5 * order.price:
                size = taking
                price = implied
            else:
                size = order.size
        else:
            implied = taking / making
            if 0.001 <= implied <= 0.999 and 0.4 * order.price <= implied <= 2.5 * order.price:
                size = making
                price = implied
            else:
                size = order.size
    elif status in {"live", "delayed", "unmatched", "canceled", "cancelled"}:
        # הזמנה עומדת או לא מולאה — אין מילוי בפועל
        return None
    else:
        size = order.size

    if size <= 0:
        return None

    fee_resp = _f(resp.get("fee"))
    if fee_resp is not None:
        fee = fee_resp
    elif fee_mode == "model" and order.fee_rate > 0:
        fee = taker_fee(size, price, order.fee_rate)
    else:
        fee = 0.0

    fill = Fill(
        token_id=order.token_id,
        condition_id=order.condition_id,
        side=order.side,
        price=round(price, 4),
        size=round(size, 4),
        fee=fee,
        ts=utcnow(),
        order_id=str(resp.get("orderID") or resp.get("orderId") or ""),
    )
    fill.reason = order.reason  # type: ignore[attr-defined]
    return fill


class LiveBroker:
    mode = "live"

    def __init__(self, cfg: ExecutionConfig) -> None:
        self.cfg = cfg
        self._client = None
        self._guard()

    # ------------------------------------------------------------------
    def _guard(self) -> None:
        if self.cfg.mode != "live":
            raise LiveTradingDisabled(f"mode={self.cfg.mode} — לא מאפשרים פקודות אמיתיות")
        if not os.getenv("PMMB_PRIVATE_KEY"):
            raise LiveTradingDisabled("חסר PMMB_PRIVATE_KEY ב-.env")
        if os.getenv(self.cfg.live_confirm_env, "") != CONFIRM_PHRASE:
            raise LiveTradingDisabled(
                f"חסר אישור מפורש: {self.cfg.live_confirm_env}={CONFIRM_PHRASE}"
            )

    # ------------------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self):
        try:
            from py_clob_client.client import ClobClient
        except ImportError as exc:  # pragma: no cover
            raise LiveTradingDisabled(
                "py-clob-client לא מותקן. הרץ: pip install -r requirements-live.txt"
            ) from exc

        host = "https://clob.polymarket.com"
        key = os.environ["PMMB_PRIVATE_KEY"]
        funder = os.getenv("PMMB_FUNDER_ADDRESS") or None
        sig_type = int(os.getenv("PMMB_SIGNATURE_TYPE", "0"))

        client = ClobClient(host, key=key, chain_id=137, signature_type=sig_type, funder=funder)

        api_key = os.getenv("PMMB_API_KEY")
        if api_key:
            from py_clob_client.clob_types import ApiCreds

            client.set_api_creds(
                ApiCreds(
                    api_key=api_key,
                    api_secret=os.environ["PMMB_API_SECRET"],
                    api_passphrase=os.environ["PMMB_API_PASSPHRASE"],
                )
            )
        else:
            log.warning("אין API creds — מייצר/גוזר מהמפתח הפרטי")
            client.set_api_creds(client.create_or_derive_api_creds())
        return client

    # ------------------------------------------------------------------
    def execute(self, order: Order, **_) -> Fill | None:
        """שולח פקודה ל-CLOB. מחזיר Fill או None — אף פעם לא זורק (חוזה Broker)."""
        if not (0.001 <= order.price <= 0.999) or order.size <= 0:
            log.warning("פרמטרי פקודה לא תקינים לפני שליחה: side=%s px=%.4f sz=%.4f",
                        order.side, order.price, order.size)
            return None
        if order.side == "BUY" and order.size < 5.0:
            log.warning("גודל פקודת BUY קטן ממינימום Polymarket (%.2f < 5.0)", order.size)
            return None
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL

            side = BUY if order.side == "BUY" else SELL
            order_type = OrderType.FAK if self.cfg.order_type.upper() == "FAK" else OrderType.GTC

            args = OrderArgs(
                price=round(float(order.price), 4),
                size=round(float(order.size), 2),
                side=side,
                token_id=order.token_id,
            )
            signed = self.client.create_order(args)
            resp = self.client.post_order(signed, order_type)
        except Exception as exc:          # noqa: BLE001 — חוזה Broker: לא זורקים
            log.error("שגיאה בשליחת פקודת LIVE (%s %s): %s",
                      order.side, order.token_id[:12], exc)
            return None

        fill = parse_order_response(resp, order, fee_mode=self.cfg.fee_mode)
        if fill is None:
            log.error("פקודה לא מולאה: %s", resp)
            return None

        log.warning("🔴 LIVE %s %.2f @ %.3f (עמלה %.3f) | id=%s",
                    order.side, fill.size, fill.price, fill.fee, fill.order_id)
        return fill

    # ------------------------------------------------------------------
    def wallet_address(self) -> str | None:
        funder = os.getenv("PMMB_FUNDER_ADDRESS")
        if funder:
            return funder
        try:
            return self.client.get_address()
        except Exception:  # pragma: no cover
            return None

    def usdc_balance(self) -> float | None:
        try:
            resp = self.client.get_balance_allowance(params={"asset_type": "COLLATERAL"})
            return float(resp["balance"]) / 1e6
        except Exception as exc:  # pragma: no cover
            log.warning("לא הצלחתי לקרוא יתרת USDC: %s", exc)
            return None

    def conditional_balance(self, token_id: str) -> float | None:
        try:
            resp = self.client.get_balance_allowance(
                params={"asset_type": "CONDITIONAL", "token_id": token_id}
            )
            return float(resp["balance"]) / 1e6
        except Exception as exc:  # pragma: no cover
            log.warning("לא הצלחתי לקרוא יתרת טוקן %s: %s", token_id[:12], exc)
            return None

    def open_orders(self) -> list[dict]:
        try:
            resp = self.client.get_orders()
            return list(resp) if isinstance(resp, list) else []
        except Exception as exc:  # pragma: no cover
            log.warning("לא הצלחתי לקרוא פקודות פתוחות: %s", exc)
            return []

    def cancel_all(self) -> int:
        try:
            resp = self.client.cancel_all()
            if isinstance(resp, dict):
                return len(resp.get("canceled") or [])
            return 0
        except Exception as exc:  # pragma: no cover
            log.warning("ביטול פקודות פתוחות נכשל: %s", exc)
            return 0
