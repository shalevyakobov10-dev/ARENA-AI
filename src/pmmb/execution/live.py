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

from ..config import ExecutionConfig
from ..models import Fill, Order, utcnow

log = logging.getLogger(__name__)

CONFIRM_PHRASE = "I-UNDERSTAND-THE-RISK"


class LiveTradingDisabled(RuntimeError):
    pass


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
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        side = BUY if order.side == "BUY" else SELL
        order_type = OrderType.FAK if self.cfg.order_type.upper() == "FAK" else OrderType.GTC

        args = OrderArgs(
            price=order.price,
            size=order.size,
            side=side,
            token_id=order.token_id,
        )
        signed = self.client.create_order(args)
        resp = self.client.post_order(signed, order_type)

        if not isinstance(resp, dict) or not resp.get("success", False):
            log.error("פקודה נכשלה: %s", resp)
            return None

        # בפקודת FAK ייתכן מילוי חלקי. ה-API מחזיר כמויות ביחידות USDC/מניות —
        # לכן קוראים את הפוזיציה האמיתית מה-Store/בלוקצ'יין ולא סומכים על התשובה.
        # כאן: משתמשים בגודל שהתקבל אם קיים, אחרת בגודל שנשלח. המחיר = מחיר הפקודה
        # (FAK ממלא במחיר הזה או טוב יותר, ולכן שמרני לתמחור).
        matched = float(resp.get("size_matched") or resp.get("takingAmount") or 0)
        price = order.price
        size = matched if matched > 0 else order.size

        fill = Fill(
            token_id=order.token_id,
            condition_id=order.condition_id,
            side=order.side,
            price=price,
            size=size,
            fee=0.0,
            ts=utcnow(),
            order_id=str(resp.get("orderID") or resp.get("orderId") or ""),
        )
        fill.reason = order.reason  # type: ignore[attr-defined]
        log.warning("🔴 LIVE %s %.2f @ %.3f | id=%s", order.side, size, price, fill.order_id)
        return fill

    # ------------------------------------------------------------------
    def usdc_balance(self) -> float | None:
        try:
            resp = self.client.get_balance_allowance(params={"asset_type": "COLLATERAL"})
            return float(resp["balance"]) / 1e6
        except Exception as exc:  # pragma: no cover
            log.warning("לא הצלחתי לקרוא יתרת USDC: %s", exc)
            return None
