"""
מתאם רב-בורסות לחוזים תמידיים (OKX SWAP + Hyperliquid DEX + Binance Futures).

שתי הבורסות הראשיות (OKX עד 100x ו-Hyperliquid DEX עד 40x) פתוחות בזמן אמת
ומצטלבות לחישוב Funding Divergence, נזילות, L2 Orderbook והיסטוריית OHLCV.
Binance Futures מוכנה באופן מלא לסביבות ללא חסימה אזורית, עם גיבוי אוטומטי ב-451/403.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from ..config import PerpsExchangeConfig
from .models import PerpBook, PerpCandle, PerpInstrument

log = logging.getLogger(__name__)

_OKX_BAR_MAP = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
}


class HyperliquidPerpClient:
    BASE = "https://api.hyperliquid.xyz/info"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self._meta_cache: tuple[float, list[dict[str, Any]], list[dict[str, Any]]] | None = None
        self._candle_cache: dict[tuple[str, str, int], tuple[float, list[PerpCandle]]] = {}

    def _post(self, payload: dict[str, Any]) -> Any:
        r = httpx.post(self.BASE, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def fetch_universe(self) -> dict[str, PerpInstrument]:
        now = time.time()
        if self._meta_cache and now - self._meta_cache[0] < 30.0:
            uni, ctxs = self._meta_cache[1], self._meta_cache[2]
        else:
            raw = self._post({"type": "metaAndAssetCtxs"})
            uni, ctxs = raw[0]["universe"], raw[1]
            self._meta_cache = (now, uni, ctxs)

        out: dict[str, PerpInstrument] = {}
        for u, c in zip(uni, ctxs):
            name = str(u.get("name") or "").upper()
            if not name or u.get("isDelisted"):
                continue
            mark = float(c.get("markPx") or c.get("midPx") or 0.0)
            if mark <= 0:
                continue
            mid = float(c.get("midPx") or mark)
            vol = float(c.get("dayNtlVlm") or 0.0)
            oi_base = float(c.get("openInterest") or 0.0)
            funding = float(c.get("funding") or 0.0)
            sz_dec = int(u.get("szDecimals") or 3)
            out[name] = PerpInstrument(
                symbol=name,
                exchange="hyperliquid",
                exchange_symbol=name,
                max_leverage=float(u.get("maxLeverage") or 10.0),
                mark_price=mark,
                index_price=float(c.get("oraclePx") or mark),
                best_bid=mid * 0.9999,
                best_ask=mid * 1.0001,
                volume_24h_usd=vol,
                open_interest_usd=oi_base * mark,
                funding_1h=funding,
                hl_funding_1h=funding,
                tick_size=max(1e-6, round(mark * 1e-4, 6)),
                lot_size=10.0 ** (-sz_dec),
                contract_val=1.0,
                taker_fee_bps=3.5,
                maker_fee_bps=1.0,
                mmr=max(0.004, 0.5 / max(1.0, float(u.get("maxLeverage") or 10.0))),
                funding_interval_hours=1.0,
            )
        return out

    def get_book(self, coin: str, levels: int = 12) -> PerpBook | None:
        try:
            data = self._post({"type": "l2Book", "coin": coin})
            lvls = data.get("levels") or [[], []]
            bids = [(float(b["px"]), float(b["sz"])) for b in (lvls[0] or [])[:levels]]
            asks = [(float(a["px"]), float(a["sz"])) for a in (lvls[1] or [])[:levels]]
            best_bid = bids[0][0] if bids else None
            best_ask = asks[0][0] if asks else None
            return PerpBook(symbol=coin, exchange="hyperliquid", best_bid=best_bid, best_ask=best_ask, bids=bids, asks=asks)
        except Exception as exc:
            log.debug("HL book נכשל (%s): %s", coin, exc)
            return None

    def get_candles(self, coin: str, interval: str = "1h", lookback: int = 160) -> list[PerpCandle]:
        key = (coin, interval, lookback)
        now = time.time()
        cached = self._candle_cache.get(key)
        if cached and now - cached[0] < 90.0:
            return cached[1]
        sec_per = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}.get(interval, 3600)
        end_ms = int(now * 1000)
        start_ms = end_ms - int((lookback + 10) * sec_per * 1000)
        try:
            raw = self._post({
                "type": "candleSnapshot",
                "req": {"coin": coin, "interval": interval, "startTime": start_ms, "endTime": end_ms},
            })
            candles = [
                PerpCandle(
                    ts=int(c["t"]) // 1000,
                    open=float(c["o"]),
                    high=float(c["h"]),
                    low=float(c["l"]),
                    close=float(c["c"]),
                    volume=float(c["v"]),
                )
                for c in (raw or [])
            ]
            candles.sort(key=lambda x: x.ts)
            candles = candles[-lookback:]
            self._candle_cache[key] = (now, candles)
            return candles
        except Exception as exc:
            log.debug("HL candles נכשל (%s): %s", coin, exc)
            return []

    def get_funding_history(self, coin: str, days: int = 30) -> dict[int, float]:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - days * 86400 * 1000
        try:
            raw = self._post({"type": "fundingHistory", "coin": coin, "startTime": start_ms})
            return {int(x["time"]) // 1000: float(x["fundingRate"]) for x in (raw or [])}
        except Exception:
            return {}


class OKXPerpClient:
    BASE = "https://www.okx.com/api/v5"

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout
        self._inst_cache: tuple[float, dict[str, dict[str, Any]]] | None = None
        self._candle_cache: dict[tuple[str, str, int], tuple[float, list[PerpCandle]]] = {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        r = httpx.get(f"{self.BASE}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        payload = r.json()
        if str(payload.get("code")) != "0":
            raise ConnectionError(f"OKX {path}: {payload.get('msg')}")
        return list(payload.get("data") or [])

    def _instruments(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        if self._inst_cache and now - self._inst_cache[0] < 300.0:
            return self._inst_cache[1]
        rows = self._get("/public/instruments", {"instType": "SWAP"})
        mapping: dict[str, dict[str, Any]] = {}
        for d in rows:
            if d.get("settleCcy") == "USDT" and d.get("state") == "live":
                inst_id = str(d.get("instId") or "")
                sym = inst_id.replace("-USDT-SWAP", "").upper()
                mapping[sym] = d
        self._inst_cache = (now, mapping)
        return mapping

    def fetch_universe(self) -> dict[str, PerpInstrument]:
        insts = self._instruments()
        tickers = self._get("/market/tickers", {"instType": "SWAP"})
        out: dict[str, PerpInstrument] = {}
        for t in tickers:
            inst_id = str(t.get("instId") or "")
            if not inst_id.endswith("-USDT-SWAP"):
                continue
            sym = inst_id.replace("-USDT-SWAP", "").upper()
            meta = insts.get(sym)
            if not meta:
                continue
            last = float(t.get("last") or 0.0)
            if last <= 0:
                continue
            bid = float(t.get("bidPx") or last * 0.9998)
            ask = float(t.get("askPx") or last * 1.0002)
            # volCcy24h הוא כמות נכס הבסיס ב-24 שעות -> מכפילים ב-last לנפח דולרי
            vol_base = float(t.get("volCcy24h") or 0.0)
            vol_usd = vol_base * last
            ct_val = float(meta.get("ctVal") or 1.0)
            max_lev = float(meta.get("lever") or 20.0)
            out[sym] = PerpInstrument(
                symbol=sym,
                exchange="okx",
                exchange_symbol=inst_id,
                max_leverage=max_lev,
                mark_price=last,
                index_price=last,
                best_bid=bid,
                best_ask=ask,
                volume_24h_usd=vol_usd,
                open_interest_usd=0.0,
                funding_1h=0.0,
                okx_funding_1h=None,
                tick_size=float(meta.get("tickSz") or 0.01),
                lot_size=float(meta.get("lotSz") or 0.01) * ct_val,
                contract_val=ct_val,
                taker_fee_bps=5.0,
                maker_fee_bps=2.0,
                mmr=max(0.004, 0.4 / max(1.0, max_lev)),
                funding_interval_hours=8.0,
            )
        return out

    def enrich_funding_and_oi(self, inst: PerpInstrument) -> None:
        try:
            fr_rows = self._get("/public/funding-rate", {"instId": inst.exchange_symbol})
            if fr_rows:
                fr8 = float(fr_rows[0].get("fundingRate") or 0.0)
                fr1 = fr8 / 8.0
                inst.funding_1h = fr1
                inst.okx_funding_1h = fr1
        except Exception:
            pass
        try:
            oi_rows = self._get("/public/open-interest", {"instType": "SWAP", "instId": inst.exchange_symbol})
            if oi_rows:
                inst.open_interest_usd = float(oi_rows[0].get("oiUsd") or 0.0)
        except Exception:
            pass

    def get_book(self, inst_id: str, ct_val: float = 1.0, levels: int = 12) -> PerpBook | None:
        sym = inst_id.replace("-USDT-SWAP", "").upper()
        try:
            rows = self._get("/market/books", {"instId": inst_id, "sz": levels})
            if not rows:
                return None
            r = rows[0]
            bids = [(float(b[0]), float(b[1]) * ct_val) for b in (r.get("bids") or [])[:levels]]
            asks = [(float(a[0]), float(a[1]) * ct_val) for a in (r.get("asks") or [])[:levels]]
            return PerpBook(
                symbol=sym, exchange="okx",
                best_bid=bids[0][0] if bids else None,
                best_ask=asks[0][0] if asks else None,
                bids=bids, asks=asks,
            )
        except Exception as exc:
            log.debug("OKX book נכשל (%s): %s", inst_id, exc)
            return None

    def get_candles(self, inst_id: str, interval: str = "1h", lookback: int = 160) -> list[PerpCandle]:
        key = (inst_id, interval, lookback)
        now = time.time()
        cached = self._candle_cache.get(key)
        if cached and now - cached[0] < 90.0:
            return cached[1]
        bar = _OKX_BAR_MAP.get(interval, "1H")
        try:
            raw = self._get("/market/candles", {"instId": inst_id, "bar": bar, "limit": min(300, lookback)})
            candles = [
                PerpCandle(
                    ts=int(c[0]) // 1000,
                    open=float(c[1]),
                    high=float(c[2]),
                    low=float(c[3]),
                    close=float(c[4]),
                    volume=float(c[6] or c[5]),
                )
                for c in raw
            ]
            candles.sort(key=lambda x: x.ts)
            candles = candles[-lookback:]
            self._candle_cache[key] = (now, candles)
            return candles
        except Exception as exc:
            log.debug("OKX candles נכשל (%s): %s", inst_id, exc)
            return []


_BINANCE_BLOCKED_UNTIL: float = 0.0


class BinancePerpClient:
    BASE = "https://fapi.binance.com"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self.blocked = time.time() < _BINANCE_BLOCKED_UNTIL

    def fetch_universe(self) -> dict[str, PerpInstrument]:
        global _BINANCE_BLOCKED_UNTIL
        if self.blocked or time.time() < _BINANCE_BLOCKED_UNTIL:
            self.blocked = True
            return {}
        try:
            r = httpx.get(f"{self.BASE}/fapi/v1/ticker/24hr", timeout=self.timeout)
            if r.status_code in (403, 451):
                self.blocked = True
                if time.time() >= _BINANCE_BLOCKED_UNTIL:
                    log.info("Binance Futures חסום אזורית (%s) — ממשיך עם OKX + Hyperliquid", r.status_code)
                _BINANCE_BLOCKED_UNTIL = time.time() + 7200.0
                return {}
            r.raise_for_status()
            pr = httpx.get(f"{self.BASE}/fapi/v1/premiumIndex", timeout=self.timeout)
            prem = {p["symbol"]: p for p in (pr.json() if pr.status_code == 200 else [])}
            out: dict[str, PerpInstrument] = {}
            for row in r.json():
                ex_sym = str(row.get("symbol") or "")
                if not ex_sym.endswith("USDT"):
                    continue
                sym = ex_sym[:-4].upper()
                px = float(row.get("lastPrice") or 0.0)
                if px <= 0:
                    continue
                pinfo = prem.get(ex_sym, {})
                fr8 = float(pinfo.get("lastFundingRate") or 0.0)
                out[sym] = PerpInstrument(
                    symbol=sym, exchange="binance", exchange_symbol=ex_sym,
                    max_leverage=50.0, mark_price=float(pinfo.get("markPrice") or px),
                    index_price=float(pinfo.get("indexPrice") or px),
                    best_bid=float(row.get("bidPrice") or px * 0.9998),
                    best_ask=float(row.get("askPrice") or px * 1.0002),
                    volume_24h_usd=float(row.get("quoteVolume") or 0.0),
                    funding_1h=fr8 / 8.0, taker_fee_bps=4.0, maker_fee_bps=2.0,
                    mmr=0.004, funding_interval_hours=8.0,
                )
            return out
        except Exception as exc:
            log.debug("Binance universe לא זמין: %s", exc)
            return {}

    def get_candles(self, ex_sym: str, interval: str = "1h", lookback: int = 160) -> list[PerpCandle]:
        if self.blocked:
            return []
        try:
            r = httpx.get(
                f"{self.BASE}/fapi/v1/klines",
                params={"symbol": ex_sym, "interval": interval, "limit": min(500, lookback)},
                timeout=self.timeout,
            )
            if r.status_code in (403, 451):
                self.blocked = True
                return []
            r.raise_for_status()
            return [
                PerpCandle(
                    ts=int(c[0]) // 1000, open=float(c[1]), high=float(c[2]),
                    low=float(c[3]), close=float(c[4]), volume=float(c[5]),
                )
                for c in r.json()
            ]
        except Exception:
            return []


class MultiPerpExchange:
    """
    מאחד זירות Perps בזמן אמת:
      - משלב מטא-דאטה של OKX (עד 50x-100x), Hyperliquid (DEX נזיל + 235 מטבעות) ו-Binance (אם זמין)
      - מאחד נתוני Funding בין בורסות (okx_funding_1h vs hl_funding_1h)
      - מסנן לפי נפח, Open Interest וספרד, ובוחר לכל מטבע את זירת הביצוע המיטבית
    """

    def __init__(
        self,
        cfg: PerpsExchangeConfig,
        *,
        hl: HyperliquidPerpClient | None = None,
        okx: OKXPerpClient | None = None,
        binance: BinancePerpClient | None = None,
    ) -> None:
        self.cfg = cfg
        self.hl = hl or HyperliquidPerpClient(timeout=cfg.http_timeout)
        self.okx = okx or OKXPerpClient(timeout=cfg.http_timeout)
        self.binance = binance or BinancePerpClient(timeout=cfg.http_timeout)
        self._instruments: dict[str, PerpInstrument] = {}

    def scan(self) -> list[PerpInstrument]:
        enabled = set(self.cfg.enabled_exchanges)
        hl_map: dict[str, PerpInstrument] = {}
        okx_map: dict[str, PerpInstrument] = {}
        bn_map: dict[str, PerpInstrument] = {}

        if "hyperliquid" in enabled:
            try:
                hl_map = self.hl.fetch_universe()
            except Exception as exc:
                log.warning("Hyperliquid scan נכשל: %s", exc)
        if "okx" in enabled:
            try:
                okx_map = self.okx.fetch_universe()
            except Exception as exc:
                log.warning("OKX scan נכשל: %s", exc)
        if "binance" in enabled:
            bn_map = self.binance.fetch_universe()

        all_syms = set(hl_map) | set(okx_map) | set(bn_map)
        if self.cfg.symbols:
            allow = {s.upper() for s in self.cfg.symbols}
            all_syms &= allow

        merged: list[PerpInstrument] = []
        pref = self.cfg.preferred_exchange
        for sym in all_syms:
            cand_okx = okx_map.get(sym)
            cand_hl = hl_map.get(sym)
            cand_bn = bn_map.get(sym)

            chosen: PerpInstrument | None = None
            if pref == "okx" and cand_okx:
                chosen = cand_okx
            elif pref == "hyperliquid" and cand_hl:
                chosen = cand_hl
            elif pref == "binance" and cand_bn:
                chosen = cand_bn
            else:
                # Auto routing: מעדיף זירה שתומכת במינוף >= 50x ובעלת נפח ונזילות חזקים
                pool = [x for x in (cand_okx, cand_bn, cand_hl) if x is not None]
                if pool:
                    pool.sort(key=lambda x: (1 if x.max_leverage >= 50 else 0, x.volume_24h_usd), reverse=True)
                    chosen = pool[0]

            if chosen is None:
                continue

            # סינון מניות/Pre-IPO עם שעות מסחר סגורות: נכס קריפטו 24/7 נדרש להופיע גם ב-HL או Binance כששתיהן פעילות
            if self.cfg.cross_exchange_crypto_only and hl_map and (cand_hl is None and cand_bn is None):
                continue

            # מיזוג נתוני הצלבה בין זירות (HL Funding + OI, OKX Funding)
            if cand_hl is not None:
                chosen.hl_funding_1h = cand_hl.funding_1h
                if chosen.open_interest_usd <= 0:
                    chosen.open_interest_usd = cand_hl.open_interest_usd
                if chosen.funding_1h == 0.0:
                    chosen.funding_1h = cand_hl.funding_1h
            if cand_okx is not None and cand_okx.okx_funding_1h is not None:
                chosen.okx_funding_1h = cand_okx.okx_funding_1h

            if chosen.volume_24h_usd < self.cfg.min_volume_24h_usd:
                continue
            if chosen.open_interest_usd > 0 and chosen.open_interest_usd < self.cfg.min_open_interest_usd:
                continue
            if chosen.spread_bps > self.cfg.max_spread_bps:
                continue
            merged.append(chosen)

        merged.sort(key=lambda x: -x.volume_24h_usd)
        selected = merged[: self.cfg.max_assets]

        # העשרת Funding ו-OI עדכניים מ-OKX במקביל עבור הנכסים המובילים
        okx_selected = [inst for inst in selected if inst.exchange == "okx"]
        if okx_selected:
            with ThreadPoolExecutor(max_workers=min(8, len(okx_selected))) as pool:
                list(pool.map(self.okx.enrich_funding_and_oi, okx_selected))
        for inst in selected:
            self._instruments[inst.symbol] = inst
        return selected

    def get_book(self, inst: PerpInstrument, levels: int = 12) -> PerpBook | None:
        if inst.exchange == "okx":
            bk = self.okx.get_book(inst.exchange_symbol, ct_val=inst.contract_val, levels=levels)
            if bk is not None:
                return bk
        if inst.exchange == "hyperliquid" or inst.hl_funding_1h is not None:
            return self.hl.get_book(inst.symbol, levels=levels)
        return None

    def get_candles(self, inst: PerpInstrument, interval: str = "1h", lookback: int = 160) -> list[PerpCandle]:
        candles: list[PerpCandle] = []
        if lookback > 300 and inst.hl_funding_1h is not None:
            candles = self.hl.get_candles(inst.symbol, interval=interval, lookback=lookback)
            if len(candles) >= min(lookback, 320):
                return candles
        if inst.exchange == "okx":
            candles = self.okx.get_candles(inst.exchange_symbol, interval=interval, lookback=lookback)
        elif inst.exchange == "binance":
            candles = self.binance.get_candles(inst.exchange_symbol, interval=interval, lookback=lookback)
        if not candles:
            candles = self.hl.get_candles(inst.symbol, interval=interval, lookback=lookback)
        return candles
