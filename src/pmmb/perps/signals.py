"""
מנוע הסיגנלים המקצועי לחוזים תמידיים (Perps Multi-Regime Engine).

משלב 4 שכבות החלטה של סוחר מוסדי:
  1. סיווג משטר שוק (Regime): ADX(14) + Kaufman Efficiency Ratio + EMA(20/50/100)
     - TREND_UP / TREND_DOWN: מזהה Pullbacks חזקים עם מגמה ראשית ו-BTC HTF Bias
     - RANGE: מזהה קיצוניות סטטיסטית (Z-Score + RSI(14) + אישור היפוך נר)
  2. הצלבת זרימת הזמנות ו-Funding: L2 Imbalance + Cross-Exchange Funding Crowding
  3. ניתוח חדשות ומאקרו מ-19 רשתות גלובליות (`news.py`): זיהוי הלם מאקרו/SEC/Fed/Hack
  4. דירוג A+ / A / B ומינוף מומלץ דינמי עד ×50 בכפוף למרחק SL מול ATR
"""
from __future__ import annotations

import statistics
from typing import Any

from ..config import PerpsConfig
from .models import PerpBook, PerpCandle, PerpInstrument, PerpSignal, utcnow


# ----------------------------------------------------------------------
#  אינדיקטורים טהורים על OHLCV
# ----------------------------------------------------------------------
def calc_atr(candles: list[PerpCandle], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs: list[float] = []
    start = max(1, len(candles) - period)
    for k in range(start, len(candles)):
        h, l = candles[k].high, candles[k].low
        pc = candles[k - 1].close
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def calc_ema_series(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for x in values[1:]:
        out.append(x * k + out[-1] * (1.0 - k))
    return out


def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = losses = 0.0
    for k in range(len(closes) - period, len(closes)):
        d = closes[k] - closes[k - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    if losses <= 1e-12:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def calc_adx(candles: list[PerpCandle], period: int = 14) -> tuple[float, float, float]:
    """מחזיר (ADX, +DI, -DI)."""
    n = len(candles)
    if n < period * 2 + 1:
        return 20.0, 0.0, 0.0
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    trs: list[float] = []
    for k in range(n - period * 2, n):
        up = candles[k].high - candles[k - 1].high
        dn = candles[k - 1].low - candles[k].low
        plus_dm.append(up if up > dn and up > 0 else 0.0)
        minus_dm.append(dn if dn > up and dn > 0 else 0.0)
        pc = candles[k - 1].close
        trs.append(max(candles[k].high - candles[k].low, abs(candles[k].high - pc), abs(candles[k].low - pc)))

    dxs: list[float] = []
    pdi_last = mdi_last = 0.0
    for off in range(period):
        end = len(trs) - off
        st = max(0, end - period)
        tr_s = sum(trs[st:end]) or 1e-12
        pdi = 100.0 * sum(plus_dm[st:end]) / tr_s
        mdi = 100.0 * sum(minus_dm[st:end]) / tr_s
        if off == 0:
            pdi_last, mdi_last = pdi, mdi
        denom = pdi + mdi
        dxs.append(100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0)
    return (sum(dxs) / len(dxs) if dxs else 20.0), pdi_last, mdi_last


def calc_efficiency_ratio(closes: list[float], period: int = 20) -> float:
    """Kaufman Efficiency Ratio (0..1): 1 = מגמה חלקה, 0 = רעש דשדוש."""
    if len(closes) <= period:
        return 0.0
    net = abs(closes[-1] - closes[-1 - period])
    path = sum(abs(closes[k] - closes[k - 1]) for k in range(len(closes) - period, len(closes)))
    return net / path if path > 1e-12 else 0.0


# ----------------------------------------------------------------------
#  חדשות ומאקרו גלובלי עבור שוק ה-Perps
# ----------------------------------------------------------------------
_CRYPTO_SYMBOL_ALIASES: dict[str, tuple[str, ...]] = {
    "BTC": ("bitcoin", "btc", "spot etf", "microstrategy", "satoshi"),
    "ETH": ("ethereum", "eth ", "ether", "vitalik"),
    "SOL": ("solana", "sol "),
    "XRP": ("ripple", "xrp", "sec"),
    "DOGE": ("dogecoin", "doge"),
    "BNB": ("binance", "bnb", "cz"),
    "AVAX": ("avalanche", "avax"),
    "LINK": ("chainlink",),
    "AAVE": ("aave",),
    "SUI": ("sui ",),
    "ARB": ("arbitrum",),
    "NEAR": ("near protocol", "near "),
    "HYPE": ("hyperliquid", "hype "),
    "WLD": ("worldcoin", "sam altman"),
    "ENA": ("ethena", "usde"),
    "UNI": ("uniswap",),
    "ZEC": ("zcash",),
    "ADA": ("cardano",),
    "TRUMP": ("trump",),
}
_MACRO_CRYPTO_TERMS = (
    "federal reserve", "fed ", "fomc", "powell", "cpi", "inflation", "interest rate",
    "rate cut", "rate hike", "crypto", "bitcoin", "etf", "sec ", "hack", "exploit",
    "bankruptcy", "tariff", "sanction", "war", "recession", "liquidation",
)


def assess_perps_news(symbol: str, articles: list[dict[str, Any]], window_hours: float = 6.0) -> dict[str, Any]:
    """בודק חדשות ייעודיות למטבע + דופק מאקרו גלובלי מרשת 19 הסוכנויות."""
    if not articles:
        return {"count": 0, "max_impact": 0.0, "avg_sentiment": 0.0, "macro_shock": False, "headline": ""}

    now_ts = max(int(a.get("ts") or 0) for a in articles)
    cutoff = now_ts - int(window_hours * 3600)
    sym_u = symbol.upper()
    aliases = _CRYPTO_SYMBOL_ALIASES.get(sym_u, (sym_u.lower(),))

    matched_coin: list[dict[str, Any]] = []
    macro_hits: list[dict[str, Any]] = []
    for a in articles:
        if int(a.get("ts") or 0) < cutoff:
            continue
        title = str(a.get("title") or "").lower()
        imp = float(a.get("impact") or 0.0)
        if any(al in title for al in aliases):
            matched_coin.append(a)
        elif imp >= 0.65 and any(t in title for t in _MACRO_CRYPTO_TERMS):
            macro_hits.append(a)

    pool = matched_coin or macro_hits
    if not pool:
        return {"count": 0, "max_impact": 0.0, "avg_sentiment": 0.0, "macro_shock": False, "headline": ""}

    max_imp = max(float(a.get("impact") or 0.0) for a in pool)
    avg_sent = sum(float(a.get("sentiment") or 0.0) for a in pool) / len(pool)
    top = max(pool, key=lambda a: float(a.get("impact") or 0.0))
    macro_shock = max_imp >= 0.85 and avg_sent <= -0.55
    return {
        "count": len(pool),
        "max_impact": round(max_imp, 3),
        "avg_sentiment": round(avg_sent, 3),
        "macro_shock": macro_shock,
        "headline": str(top.get("title") or "")[:90],
    }


# ----------------------------------------------------------------------
#  מנוע האסטרטגיה הרב-מצבי (ProMultiRegimeEngine)
# ----------------------------------------------------------------------
class ProMultiRegimeEngine:
    min_candles: int = 105

    def __init__(self, cfg: PerpsConfig) -> None:
        self.cfg = cfg

    def evaluate(
        self,
        inst: PerpInstrument,
        candles: list[PerpCandle],
        *,
        book: PerpBook | None = None,
        btc_candles: list[PerpCandle] | None = None,
        news_articles: list[dict[str, Any]] | None = None,
    ) -> PerpSignal:
        sc = self.cfg.signal
        rk = self.cfg.risk

        if len(candles) < self.min_candles:
            return PerpSignal(
                symbol=inst.symbol, exchange=inst.exchange, direction="FLAT",
                regime="UNKNOWN", strategy="none", score=0.0, tier="B",
                price=inst.mark_price, atr=0.0, stop_price=None, take_profit_price=None,
                recommended_leverage=1.0, reason=f"היסטוריה קצרה ({len(candles)} < {self.min_candles})",
            )

        closes = [c.close for c in candles]
        px = closes[-1]
        atr = calc_atr(candles, 14)
        atr_pct = atr / px if px > 0 else 0.0
        if not (0.0025 <= atr_pct <= 0.05):
            return PerpSignal(
                symbol=inst.symbol, exchange=inst.exchange, direction="FLAT",
                regime="SHOCK" if atr_pct > 0.05 else "FLAT_VOL", strategy="none",
                score=0.0, tier="B", price=px, atr=atr, stop_price=None, take_profit_price=None,
                recommended_leverage=1.0,
                reason=f"תנודתיות ATR מחוץ לתחום ({atr_pct*100:.2f}%)",
                features={"atr_pct": round(atr_pct * 100, 3)},
            )

        adx, pdi, mdi = calc_adx(candles, 14)
        er = calc_efficiency_ratio(closes, 20)
        rsi = calc_rsi(closes, 14)
        e20 = calc_ema_series(closes, 20)[-1]
        e50 = calc_ema_series(closes, 50)[-1]
        e100 = calc_ema_series(closes, 100)[-1]

        win24 = closes[-25:-1]
        mu24 = sum(win24) / len(win24)
        sd24 = statistics.stdev(win24) if len(win24) > 1 else 1e-9
        z = (px - mu24) / (sd24 or 1e-9)

        # זיהוי משטר השוק
        if adx >= sc.adx_trend_threshold and er >= sc.er_trend_threshold:
            regime = "TREND_UP" if (e20 > e50 and pdi >= mdi) else ("TREND_DOWN" if (e20 < e50 and mdi > pdi) else "RANGE")
        else:
            regime = "RANGE"

        # BTC HTF Bias מאקרו
        btc_bull = btc_bear = True
        if sc.htf_macro_bias and btc_candles and len(btc_candles) >= 100:
            bc = [c.close for c in btc_candles]
            be50 = calc_ema_series(bc, 50)[-1]
            be100 = calc_ema_series(bc, 100)[-1]
            bpx = bc[-1]
            btc_bull = (bpx >= be100 * 0.992) or (be50 >= be100 * 0.995)
            btc_bear = (bpx <= be100 * 1.008) or (be50 <= be100 * 1.005)

        news_info = assess_perps_news(inst.symbol, news_articles or [])
        imb = book.imbalance(8) if book is not None else None
        spread_bps = book.spread_bps if book is not None else inst.spread_bps
        fr = inst.funding_1h

        direction: str = "FLAT"
        strategy = "none"
        score = 0.0
        reason = "ממתין לסטאפ בעל יחס סיכוי/סיכון"
        last = candles[-1]

        # 1) אסטרטגיית Trend Pullback במשטר מגמתי מאומת
        if adx >= sc.adx_trend_threshold and er >= sc.er_trend_threshold:
            if (
                e20 > e50 > e100
                and pdi > mdi
                and last.low <= e20 * 1.004
                and px > e20
                and last.close > last.open
                and rsi <= 62.0
                and btc_bull
            ):
                direction, strategy = "LONG", "pullback"
                score = 0.58 + (adx - sc.adx_trend_threshold) / 40.0 + er * 0.25
                reason = f"Pullback מגמתי עולה (ADX={adx:.1f}, ER={er:.2f}, RSI={rsi:.0f})"
            elif (
                sc.allow_short
                and e20 < e50 < e100
                and mdi > pdi
                and last.high >= e20 * 0.996
                and px < e20
                and last.close < last.open
                and rsi >= 38.0
                and btc_bear
            ):
                direction, strategy = "SHORT", "pullback"
                score = 0.58 + (adx - sc.adx_trend_threshold) / 40.0 + er * 0.25
                reason = f"Pullback מגמתי יורד (ADX={adx:.1f}, ER={er:.2f}, RSI={rsi:.0f})"

        # 2) אסטרטגיית Mean-Reversion בקצות Z+RSI + סינון Funding
        if direction == "FLAT" and adx < (sc.adx_trend_threshold + 6.0):
            if (
                -sc.z_max <= z <= -sc.z_entry
                and rsi <= sc.rsi_oversold
                and last.close > last.open
                and fr <= sc.max_funding_hourly_against
            ):
                if not sc.htf_macro_bias or px > e100 * 0.97 or z <= -(sc.z_entry + 0.5):
                    direction, strategy = "LONG", "meanrev"
                    score = 0.58 + (abs(z) - sc.z_entry) * 0.12 + (sc.rsi_oversold - rsi) * 0.01
                    if fr < -0.0001:
                        score += 0.08
                    reason = f"היפוך מתיחת יתר למטה (z={z:.2f}, RSI={rsi:.0f}, fund={fr*100:+.4f}%/h)"
            elif (
                sc.allow_short
                and sc.z_entry <= z <= sc.z_max
                and rsi >= sc.rsi_overbought
                and last.close < last.open
                and fr >= -sc.max_funding_hourly_against
            ):
                if not sc.htf_macro_bias or px < e100 * 1.03 or z >= (sc.z_entry + 0.5):
                    direction, strategy = "SHORT", "meanrev"
                    score = 0.58 + (abs(z) - sc.z_entry) * 0.12 + (rsi - sc.rsi_overbought) * 0.01
                    if fr > 0.0001:
                        score += 0.08
                    reason = f"היפוך מתיחת יתר למעלה (z={z:.2f}, RSI={rsi:.0f}, fund={fr*100:+.4f}%/h)"

        # 3) אסטרטגיית Trend Breakout (תופסת ראלי/קריסות חזקות שלא חוזרות ל-EMA20)
        if direction == "FLAT" and adx >= 30.0 and er >= 0.38 and 0.003 <= atr_pct <= 0.042:
            hi16 = max(c.high for c in candles[-17:-1])
            lo16 = min(c.low for c in candles[-17:-1])
            avg_vol = sum(c.volume for c in candles[-21:-1]) / 20.0
            vol_ok = avg_vol <= 0 or last.volume >= avg_vol * 1.10
            if vol_ok:
                if (
                    e20 > e50
                    and pdi > mdi
                    and px > hi16
                    and last.close > last.open
                    and 52.0 <= rsi <= 70.0
                    and btc_bull
                ):
                    direction, strategy = "LONG", "breakout"
                    score = min(0.84, 0.62 + (adx - 30.0) / 50.0 + er * 0.18)
                    reason = f"פריצת מגמה עולה (ADX={adx:.1f}, ER={er:.2f}, RSI={rsi:.0f})"
                elif (
                    sc.allow_short
                    and e20 < e50
                    and mdi > pdi
                    and px < lo16
                    and last.close < last.open
                    and 30.0 <= rsi <= 48.0
                    and btc_bear
                ):
                    direction, strategy = "SHORT", "breakout"
                    score = min(0.84, 0.62 + (adx - 30.0) / 50.0 + er * 0.18)
                    reason = f"פריצת מגמה יורדת (ADX={adx:.1f}, ER={er:.2f}, RSI={rsi:.0f})"

        # שילוב זרימת L2 Orderbook וחדשות גלובליות
        if direction != "FLAT":
            if imb is not None:
                if (direction == "LONG" and imb >= 0.15) or (direction == "SHORT" and imb <= -0.15):
                    score += 0.06
                elif (direction == "LONG" and imb <= -0.45) or (direction == "SHORT" and imb >= 0.45):
                    score -= 0.08
            if spread_bps > 12.0:
                score -= 0.08
            if self.cfg.use_news_filter and news_info["max_impact"] >= self.cfg.news_block_impact:
                if direction == "LONG" and news_info["avg_sentiment"] <= -0.35:
                    direction = "FLAT"
                    strategy = "none"
                    reason = f"נבלם ע\"י חדשות מאקרו/מטבע שליליות: {news_info['headline'][:45]}"
                elif direction == "SHORT" and news_info["avg_sentiment"] >= 0.45:
                    direction = "FLAT"
                    strategy = "none"
                    reason = f"נבלם ע\"י חדשות חיוביות מתפרצות: {news_info['headline'][:45]}"
            elif self.cfg.use_news_filter and news_info["max_impact"] >= 0.45:
                # Confluence חיזוק ציון כשכותרות השוק תואמות את כיוון העסקה
                if (direction == "LONG" and news_info["avg_sentiment"] >= 0.25) or (
                    direction == "SHORT" and news_info["avg_sentiment"] <= -0.25
                ):
                    score += 0.03

            # פער Funding בין OKX ל-Hyperliquid
            if inst.okx_funding_1h is not None and inst.hl_funding_1h is not None:
                f_spread = inst.okx_funding_1h - inst.hl_funding_1h
                if direction == "LONG" and f_spread < -0.0001:
                    score += 0.02
                elif direction == "SHORT" and f_spread > 0.0001:
                    score += 0.02

        score = max(0.0, min(1.0, round(score, 4)))
        if direction != "FLAT" and score < sc.min_score:
            direction = "FLAT"
            strategy = "none"
            reason = f"ציון איכות מתחת לסף ({score:.2f} < {sc.min_score:.2f})"

        tier = "A+" if score >= 0.78 else ("A" if score >= 0.68 else "B")

        # חישוב Stop/TP מבוססי ATR והמלצת מינוף דינמי עד 50x (כפוף למרחק ליקווידציה)
        stop_dist_pct = rk.sl_atr_mult * atr_pct
        rt_cost = 2.0 * (self.cfg.taker_fee_bps + self.cfg.slippage_bps) / 10_000.0
        safe_lev = (1.0 - inst.mmr) / max(1e-4, stop_dist_pct * rk.liquidation_buffer_mult + rt_cost)
        tier_cap = 50.0 if tier == "A+" else (25.0 if tier == "A" else 12.0)
        if not rk.dynamic_leverage:
            tier_cap = rk.max_leverage
        rec_lev = max(2.0, round(min(rk.max_leverage, inst.max_leverage, safe_lev, tier_cap), 1))

        stop_px = tp_px = None
        if direction == "LONG":
            stop_px = round(px * (1.0 - stop_dist_pct), 6)
            tp_px = round(px * (1.0 + rk.tp_atr_mult * atr_pct), 6)
        elif direction == "SHORT":
            stop_px = round(px * (1.0 + stop_dist_pct), 6)
            tp_px = round(px * (1.0 - rk.tp_atr_mult * atr_pct), 6)

        return PerpSignal(
            symbol=inst.symbol,
            exchange=inst.exchange,
            direction=direction,  # type: ignore[arg-type]
            regime=regime,
            strategy=strategy,
            score=score,
            tier=tier,
            price=px,
            atr=atr,
            stop_price=stop_px,
            take_profit_price=tp_px,
            recommended_leverage=rec_lev,
            reason=reason,
            features={
                "adx": round(adx, 2),
                "er": round(er, 3),
                "rsi": round(rsi, 1),
                "z": round(z, 2),
                "atr_pct": round(atr_pct * 100, 3),
                "funding_1h": round(fr * 100, 5),
                "imbalance": round(imb, 3) if imb is not None else 0.0,
                "spread_bps": round(spread_bps, 2),
                "news_impact": news_info["max_impact"],
            },
        )
