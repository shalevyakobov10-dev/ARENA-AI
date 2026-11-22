"""שליפת שווקים מ-Gamma API + סינון היקום (universe)."""
from __future__ import annotations

import logging

from ..config import UniverseConfig
from ..sectors import classify
from ..models import Market
from .http import HttpClient

log = logging.getLogger(__name__)


class GammaClient:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def fetch_markets(
        self,
        limit: int = 120,
        min_volume_24h: float = 0.0,
        only_open: bool = True,
    ) -> list[dict]:
        """מחזיר עד `limit` שווקים פתוחים, ממוינים לפי מחזור יומי."""
        out: list[dict] = []
        page_size = min(max(limit, 1), 100)
        offset = 0
        while len(out) < limit:
            params = {
                "limit": page_size,
                "offset": offset,
                "order": "volume24hr",
                "ascending": "false",
                "active": "true",
                "closed": "false",
                "archived": "false",
            }
            batch = self.http.get("/markets", params=params)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
            # עוצרים מוקדם אם כבר ירדנו מתחת לסף המחזור
            if min_volume_24h and _vol(batch[-1]) < min_volume_24h:
                break
        return out[:limit]


class MarketUniverse:
    """מסנן את השווקים ששווה להריץ עליהם את מנוע הסיגנלים."""

    def __init__(self, gamma: GammaClient, cfg: UniverseConfig) -> None:
        self.gamma = gamma
        self.cfg = cfg

    def scan(self) -> list[Market]:
        raw = self.gamma.fetch_markets(
            limit=max(self.cfg.max_markets * 10, 1200),   # סריקה עמוקה מתחת לשכבת שווקי הספורט/קריפטו
            min_volume_24h=self.cfg.min_volume_24h,
        )
        markets: list[Market] = []
        rejected: dict[str, int] = {}

        for m in raw:
            mk = Market.from_gamma(m)
            if mk is None:
                rejected["לא סחיר / סגור"] = rejected.get("לא סחיר / סגור", 0) + 1
                continue
            ok, why = self._passes(mk)
            if not ok:
                rejected[why] = rejected.get(why, 0) + 1
                continue
            markets.append(mk)
            if len(markets) >= self.cfg.max_markets:
                break

        log.info("סריקת יקום: %d שווקים עברו סינון מתוך %d בקשות", len(markets), len(raw))
        if rejected:
            log.debug("פילוח דחיות: %s", rejected)
        return markets

    # ------------------------------------------------------------------
    def _passes(self, mk: Market) -> tuple[bool, str]:
        c = self.cfg
        yes = mk.yes_price
        if c.require_order_book and mk.volume_24h <= 0:
            return False, "אין ספר פקודות"
        if mk.volume_24h < c.min_volume_24h:
            return False, "מחזור יומי נמוך"
        if mk.liquidity < c.min_liquidity:
            return False, "נזילות נמוכה"
        if mk.spread > c.max_spread:
            return False, "ספרד רחב"
        if mk.taker_fee_rate > c.max_taker_fee_rate:
            return False, "עמלת שוק גבוהה"
        lo, hi = c.price_band
        if not (lo <= yes <= hi):
            return False, "מחוץ לתחום מחיר"
        h = mk.hours_to_resolution
        if h < c.min_hours_to_resolution:
            return False, "קרוב מדי לסגירה"
        if h > c.max_hours_to_resolution:
            return False, "רחוק מדי מהסגירה"
        if c.exclude_sectors:
            sector = classify(mk.question, mk.slug)
            if sector in {s.lower() for s in c.exclude_sectors}:
                return False, f"סקטור מוחרג ({sector})"
        slug = (mk.slug or "").lower()
        if any(s.lower() in slug for s in c.exclude_slug_contains):
            return False, "slug מוחרג"
        if c.exclude_tags:
            tags = {t.lower() for t in mk.tags}
            if tags & {t.lower() for t in c.exclude_tags}:
                return False, "תגית מוחרגת"
        return True, ""


def _vol(m: dict) -> float:
    try:
        return float(m.get("volume24hr") or 0)
    except (TypeError, ValueError):
        return 0.0
