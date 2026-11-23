"""
PerpEngine — מנוע המסחר האוטונומי לחוזים תמידיים (Perpetual Futures) עד מינוף ×50.

מחזור דו-מעברי:
  0. שחזור מצב מלא מ-SQLite (פוזיציות, מרג'ין, מזומן, שיא, תקופות צינון)
  1. סריקת רב-בורסות (OKX + Hyperliquid + Binance) -> נרות + L2 Book + Funding + חדשות גלובליות
  1.5. חישוב Funding שוטף, עדכון Trailing Stop וביצוע יציאות (TP / SL / Liq / Time / News Exit)
  2. תיעדוף מועמדי כניסה (A+ -> A -> B) ומינוף דינמי עד ×50 (Isolated Margin)
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import Config
from ..data.store import Store
from ..notify import Notifier
from .broker import PaperPerpBroker
from .exchange import MultiPerpExchange
from .models import PerpBook, PerpCandle, PerpFill, PerpInstrument, PerpOrder, PerpPosition, PerpSignal, utcnow
from .risk import PerpRiskManager
from .signals import ProMultiRegimeEngine, assess_perps_news

log = logging.getLogger(__name__)


@dataclass
class PerpCycleStats:
    scanned: int = 0
    signalled: int = 0
    entries: int = 0
    exits: int = 0
    errors: int = 0
    funding_net: float = 0.0
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        key = reason.split("(")[0].strip()[:36]
        self.skipped[key] = self.skipped.get(key, 0) + 1


class PerpEngine:
    def __init__(
        self,
        cfg: Config,
        *,
        store: Store | None = None,
        exchange: MultiPerpExchange | None = None,
        broker=None,
        notifier: Notifier | None = None,
    ) -> None:
        self.cfg = cfg
        self.pcfg = cfg.perps
        self.store = store or Store(cfg.data.db_path)
        self.exchange = exchange or MultiPerpExchange(self.pcfg.exchange)
        self.signals = ProMultiRegimeEngine(self.pcfg)
        self.risk = PerpRiskManager(self.pcfg)
        self.broker = broker or PaperPerpBroker(self.pcfg)
        self.notifier = notifier

        self.cash: float = self.pcfg.risk.starting_cash
        self.realized_pnl: float = 0.0
        self.realized_pnl_today: float = 0.0
        self.positions: dict[str, PerpPosition] = {}
        self._last_marks: dict[str, float] = {}
        self._last_day = utcnow().date()
        self._news_articles: list[dict[str, Any]] = []
        self._restore_state()

    def _restore_state(self) -> None:
        st = self.store.load_perp_portfolio_state(self.pcfg.mode, self.pcfg.risk.starting_cash)
        self.cash = st["cash"]
        self.realized_pnl = st["realized_pnl"]
        self.realized_pnl_today = st["realized_pnl_today"]
        self.risk.update_peak(st["peak_equity"])
        self.positions = {p.symbol: p for p in st["positions"]}
        for p in st["positions"]:
            self._last_marks[p.symbol] = p.entry_price

        cd_h = int(self.pcfg.risk.cooldown_bars or 0)
        if cd_h > 0:
            now = utcnow()
            cutoff = int((now - timedelta(hours=cd_h)).timestamp())
            for sym, sell_ts in self.store.recent_perp_exits(self.pcfg.mode, cutoff).items():
                until = datetime.fromtimestamp(sell_ts, tz=timezone.utc) + timedelta(hours=cd_h)
                if until > now:
                    self.risk._cooldown_until[sym] = until

        if self.positions:
            log.info(
                "⚡ שוחזר תיק Perps: %d פוזיציות | מזומן %.2f | מרג'ין %.2f | שיא %.2f",
                len(self.positions), self.cash,
                sum(p.margin_used for p in self.positions.values()), self.risk.peak_equity,
            )

    def _equity(self) -> float:
        used_margin = sum(p.margin_used for p in self.positions.values())
        unr = sum(p.unrealized_pnl(self._last_marks.get(s, p.entry_price)) for s, p in self.positions.items())
        return round(self.cash + used_margin + unr, 4)

    def _roll_day_if_needed(self) -> None:
        today = utcnow().date()
        if today != self._last_day:
            self.realized_pnl_today = 0.0
            self._last_day = today

    def _notify(self, text: str) -> None:
        if self.notifier is not None:
            self.notifier.send(text)

    def _load_news(self) -> None:
        if not self.pcfg.use_news_filter:
            self._news_articles = []
            return
        try:
            self._news_articles = [dict(r) for r in self.store.recent_news(hours=12.0, limit=140)]
        except Exception:
            self._news_articles = []

    def run_once(self) -> PerpCycleStats:
        stats = PerpCycleStats()
        self._roll_day_if_needed()
        self._load_news()

        try:
            instruments = self.exchange.scan()
        except Exception as exc:
            log.error("Perps scan נכשל: %s", exc)
            stats.errors += 1
            return stats

        stats.scanned = len(instruments)
        inst_map = {i.symbol: i for i in instruments}

        # שליפת BTC כסמן מאקרו ל-HTF Bias
        btc_inst = inst_map.get("BTC")
        btc_candles: list[PerpCandle] = []
        if btc_inst is not None:
            btc_candles = self.exchange.get_candles(
                btc_inst, interval=self.pcfg.signal.timeframe, lookback=self.pcfg.signal.lookback_candles
            )

        intel_rows: list[dict[str, Any]] = []
        pending_entries: list[tuple[PerpInstrument, PerpSignal, PerpBook | None, dict[str, Any]]] = []

        for inst in instruments:
            try:
                candles = (
                    btc_candles
                    if inst.symbol == "BTC" and btc_candles
                    else self.exchange.get_candles(
                        inst, interval=self.pcfg.signal.timeframe, lookback=self.pcfg.signal.lookback_candles
                    )
                )
                book = self.exchange.get_book(inst)
                if candles:
                    self.store.insert_perp_candles(
                        inst.symbol, inst.exchange, self.pcfg.signal.timeframe,
                        [(c.ts, c.open, c.high, c.low, c.close, c.volume) for c in candles[-120:]],
                    )
                mark = (book.mid if book and book.mid else (candles[-1].close if candles else inst.mark_price))
                self._last_marks[inst.symbol] = mark

                # עדכון פוזיציה פתוחה על המטבע + Funding + יציאות
                if inst.symbol in self.positions:
                    self._process_position(
                        self.positions[inst.symbol], inst, candles[-1] if candles else None, book, mark, stats
                    )

                sig = self.signals.evaluate(
                    inst, candles, book=book, btc_candles=btc_candles, news_articles=self._news_articles
                )
                if sig.direction != "FLAT":
                    stats.signalled += 1
                    self.store.record_perp_signal(sig)

                bid_u, ask_u = book.depth_usd(8) if book else (0.0, 0.0)
                imb = book.imbalance(8) if book else 0.0
                status = "OPEN" if inst.symbol in self.positions else ("WATCH" if sig.direction == "FLAT" else "CANDIDATE")
                if status == "WATCH":
                    z_v = float(sig.features.get("z") or 0.0)
                    if abs(z_v) >= 1.3 or sig.regime in ("TREND_UP", "TREND_DOWN"):
                        status = "NEAR"

                row = {
                    "symbol": inst.symbol,
                    "exchange": inst.exchange,
                    "price": round(float(mark), 6),
                    "mark_price": round(float(inst.mark_price), 6),
                    "spread_bps": round(float(book.spread_bps if book else inst.spread_bps), 2),
                    "bid_depth_usd": round(float(bid_u), 1),
                    "ask_depth_usd": round(float(ask_u), 1),
                    "imbalance": round(float(imb), 3) if imb is not None else 0.0,
                    "volume_24h_usd": round(float(inst.volume_24h_usd), 1),
                    "open_interest_usd": round(float(inst.open_interest_usd), 1),
                    "funding_1h": inst.funding_1h,
                    "okx_funding_1h": inst.okx_funding_1h,
                    "hl_funding_1h": inst.hl_funding_1h,
                    "max_leverage": inst.max_leverage,
                    "rec_leverage": sig.recommended_leverage,
                    "regime": sig.regime,
                    "strategy": sig.strategy,
                    "adx": sig.features.get("adx"),
                    "er": sig.features.get("er"),
                    "rsi": sig.features.get("rsi"),
                    "z_score": sig.features.get("z"),
                    "atr_pct": sig.features.get("atr_pct"),
                    "score": sig.score,
                    "setup_tier": sig.tier,
                    "news_impact": sig.features.get("news_impact", 0.0),
                    "status": status,
                    "reason": sig.reason,
                    "updated_at": int(utcnow().timestamp()),
                }
                intel_rows.append(row)

                if sig.direction != "FLAT" and inst.symbol not in self.positions:
                    pending_entries.append((inst, sig, book, row))
                elif sig.direction == "FLAT":
                    stats.skip(sig.reason)
            except Exception as exc:
                stats.errors += 1
                log.exception("Perps שגיאה בעיבוד %s: %s", inst.symbol, exc)

        # מעקב פוזיציות יתומות שלא היו ב-Top-N של הסריקה
        for sym in list(self.positions.keys()):
            if sym not in inst_map:
                pos = self.positions[sym]
                inst_stub = PerpInstrument(
                    symbol=sym, exchange=pos.exchange,
                    exchange_symbol=f"{sym}-USDT-SWAP" if pos.exchange == "okx" else sym,
                    max_leverage=pos.leverage, mark_price=self._last_marks.get(sym, pos.entry_price),
                )
                bk = self.exchange.get_book(inst_stub)
                mk_px = bk.mid if bk and bk.mid else self._last_marks.get(sym, pos.entry_price)
                self._last_marks[sym] = mk_px
                self._process_position(pos, inst_stub, None, bk, mk_px, stats)

        # בדיקת Kill Switch גלובלי לפני כניסות חדשות
        self.risk.check_global_kill(self._equity(), self.realized_pnl_today)

        # מעבר 2: דירוג כניסות לפי איכות [A+/A/B], ציון ומינוף בטוח
        pending_entries.sort(key=lambda item: (-float(item[1].score), -float(item[0].volume_24h_usd)))
        for inst, sig, book, row in pending_entries:
            self._handle_entry(inst, sig, book, row, stats)

        if intel_rows:
            self.store.upsert_perp_intel(intel_rows)

        used_margin = sum(p.margin_used for p in self.positions.values())
        tot_notional = sum(p.notional for p in self.positions.values())
        avg_lev = (tot_notional / used_margin) if used_margin > 0 else 0.0
        eq = self._equity()
        self.risk.update_peak(eq)
        self.store.snapshot_perp_equity(
            self.pcfg.mode, eq, self.cash, used_margin, tot_notional, len(self.positions), avg_lev
        )
        log.info(
            "⚡ PERPS מחזור: נסרקו %d | סיגנלים %d | כניסות %d | יציאות %d | הון %.2f | מרג'ין %.2f | מינוף ממוצע %.1fx | פוזיציות %d",
            stats.scanned, stats.signalled, stats.entries, stats.exits,
            eq, used_margin, avg_lev, len(self.positions),
        )
        return stats

    def _process_position(
        self,
        pos: PerpPosition,
        inst: PerpInstrument,
        last_candle: PerpCandle | None,
        book: PerpBook | None,
        mark: float,
        stats: PerpCycleStats,
    ) -> None:
        now = utcnow()
        now_ts = int(now.timestamp())
        # חישוב Funding מצטבר על כל שעה מלאה שחלפה
        elapsed_h = max(0.0, (now_ts - pos.last_funding_ts) / 3600.0)
        if elapsed_h >= 1.0 and inst.funding_1h != 0.0:
            hours = int(elapsed_h)
            f_pnl = (-pos.notional * inst.funding_1h * hours) if pos.side == "LONG" else (pos.notional * inst.funding_1h * hours)
            pos.accumulated_funding += f_pnl
            self.cash += f_pnl
            pos.last_funding_ts += hours * 3600
            stats.funding_net += f_pnl

        hi = last_candle.high if last_candle else mark
        lo = last_candle.low if last_candle else mark
        exit_reason = self.risk.evaluate_exit_and_trail(pos, mark_price=mark, high_price=hi, low_price=lo, now=now)

        # הגנת חדשות שובר-שוק (Macro/Crypto Shock Exit)
        if exit_reason is None and self.pcfg.use_news_filter and self._news_articles:
            ni = assess_perps_news(pos.symbol, self._news_articles, window_hours=4.0)
            if (
                pos.side == "LONG"
                and ni["max_impact"] >= self.pcfg.news_exit_impact
                and ni["avg_sentiment"] <= self.pcfg.news_exit_sentiment
            ):
                exit_reason = f"יציאת חירום חדשות ({ni['max_impact']:.2f}): {ni['headline'][:36]}"
            elif (
                pos.side == "SHORT"
                and ni["max_impact"] >= self.pcfg.news_exit_impact
                and ni["avg_sentiment"] >= abs(self.pcfg.news_exit_sentiment)
            ):
                exit_reason = f"יציאת חירום חדשות לשורט ({ni['max_impact']:.2f}): {ni['headline'][:36]}"

        if exit_reason is None:
            # שמירת עדכון Trailing Stop ו-Funding ל-DB
            self.store.upsert_perp_position(pos, self.pcfg.mode)
            return

        is_liq = "ליקווידציה" in exit_reason
        if is_liq:
            realized = -pos.margin_used + pos.accumulated_funding
            fill = PerpFill(
                symbol=pos.symbol, exchange=pos.exchange, side=pos.side, action="LIQUIDATION",
                price=pos.liquidation_price, size=pos.size, notional=pos.notional, leverage=pos.leverage,
                margin_delta=0.0, fee=0.0, funding=pos.accumulated_funding,
                realized=round(realized, 4), reason=exit_reason, order_id=f"liq-{now_ts}", ts=now,
            )
            self.store.record_perp_fill(fill, self.pcfg.mode)
            self.store.close_perp_position(pos.symbol, exit_reason, realized)
            self.realized_pnl += realized
            self.realized_pnl_today += realized
            del self.positions[pos.symbol]
            self.risk.start_cooldown(pos.symbol, now)
            stats.exits += 1
            return

        order = PerpOrder(
            symbol=pos.symbol, exchange=pos.exchange, side=pos.side, action="CLOSE",
            price=mark, size=pos.size, leverage=pos.leverage, reduce_only=True, reason=exit_reason,
        )
        fill = self.broker.execute(order, book=book, taker_fee_bps=inst.taker_fee_bps, ct_val=inst.contract_val)
        if fill is None:
            return

        gross_pnl = ((fill.price - pos.entry_price) * pos.size) if pos.side == "LONG" else ((pos.entry_price - fill.price) * pos.size)
        net_pnl = max(-pos.margin_used, gross_pnl - fill.fee - pos.fees_paid + pos.accumulated_funding)
        margin_back = max(0.0, pos.margin_used + gross_pnl)
        fill.margin_delta = round(margin_back, 4)
        fill.realized = round(net_pnl, 4)
        fill.funding = round(pos.accumulated_funding, 4)

        self.cash += margin_back - fill.fee
        self.realized_pnl += net_pnl
        self.realized_pnl_today += net_pnl
        self.store.record_perp_fill(fill, self.pcfg.mode)
        self.store.close_perp_position(pos.symbol, exit_reason, net_pnl)
        del self.positions[pos.symbol]
        self.risk.start_cooldown(pos.symbol, now)
        stats.exits += 1

        msg = (
            f"⚡ יציאה PERPS {pos.symbol} {pos.side} ×{pos.leverage:.0f} ({pos.exchange.upper()}) | "
            f"{exit_reason} | נטו {net_pnl:+.2f} USDC"
        )
        log.info(msg)
        self._notify(msg)
        self.store.event("perp_exit", msg, data={"symbol": pos.symbol, "realized": net_pnl, "leverage": pos.leverage})

    def _handle_entry(
        self,
        inst: PerpInstrument,
        sig: PerpSignal,
        book: PerpBook | None,
        row: dict[str, Any],
        stats: PerpCycleStats,
    ) -> None:
        dec = self.risk.evaluate_entry(
            sig, inst, equity=self._equity(), free_cash=self.cash, open_positions=list(self.positions.values())
        )
        if not dec.approved:
            stats.skip(dec.reason)
            row["reason"] = f"נדחה בסיכון: {dec.reason}"
            return

        order = PerpOrder(
            symbol=inst.symbol, exchange=inst.exchange, side=sig.direction,  # type: ignore[arg-type]
            action="OPEN", price=sig.price, size=dec.size, leverage=dec.leverage,
            reduce_only=False, reason=f"{sig.tier} {sig.strategy} | {sig.reason}",
        )
        fill = self.broker.execute(order, book=book, taker_fee_bps=inst.taker_fee_bps, ct_val=inst.contract_val)
        if fill is None:
            stats.skip("מילוי Perps נכשל")
            return

        margin_used = round(fill.notional / dec.leverage, 4)
        fill.margin_delta = -margin_used
        self.cash -= margin_used + fill.fee

        from .risk import calc_liquidation_price
        liq_px = calc_liquidation_price(sig.direction, fill.price, dec.leverage, inst.mmr or self.pcfg.risk.default_mmr)
        pos = PerpPosition(
            symbol=inst.symbol, exchange=inst.exchange, side=sig.direction,  # type: ignore[arg-type]
            size=fill.size, entry_price=fill.price, notional=fill.notional,
            leverage=dec.leverage, margin_used=margin_used, liquidation_price=round(liq_px, 6),
            stop_price=dec.stop_price, target_price=dec.target_price,
            highest_price=fill.price, lowest_price=fill.price, atr=sig.atr,
            strategy=sig.strategy, regime=sig.regime, entry_score=sig.score,
            fees_paid=fill.fee, opened_at=fill.ts, last_funding_ts=int(fill.ts.timestamp()),
        )
        self.positions[inst.symbol] = pos
        self.store.record_perp_fill(fill, self.pcfg.mode)
        self.store.upsert_perp_position(pos, self.pcfg.mode)
        row["status"] = "OPEN"
        row["reason"] = f"כניסה {sig.direction} ×{dec.leverage:.0f} ({sig.tier}) @ {fill.price:.4f}"
        stats.entries += 1

        msg = (
            f"🚀 כניסה PERPS {inst.symbol} {sig.direction} ×{dec.leverage:.0f} [{sig.tier}] "
            f"@ {fill.price:.4f} | מרג'ין {margin_used:.2f}$ | נומינלי {fill.notional:.0f}$ | "
            f"SL={dec.stop_price:.4f} TP={dec.target_price:.4f} LIQ={pos.liquidation_price:.4f}"
        )
        log.info(msg)
        self._notify(msg)
        self.store.event("perp_entry", msg, data={"symbol": inst.symbol, "leverage": dec.leverage, "margin": margin_used})

    def close(self) -> None:
        self.store.close()
