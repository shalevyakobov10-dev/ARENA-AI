"""
PerpEngine — מנוע המסחר האוטונומי לחוזים תמידיים (Perpetual Futures) עד מינוף ×50.

מחזור דו-מעברי + ניטור מהיר לפוזיציות פתוחות:
  0. שחזור מצב מלא מ-SQLite (פוזיציות, מרג'ין, מזומן, שיא, תקופות צינון)
  1. סריקת רב-בורסות (OKX + Hyperliquid + Binance) + משיכה מקבילית (ThreadPoolExecutor) של נרות + L2 Book
  1.5. הגנת נר-כניסה (מניעת עצירה מתנועה שקדמה לרגע הכניסה), חישוב Funding שוטף, Trailing Stop ויציאות
  2. תיעדוף מועמדי כניסה (A+ -> A -> B) בכפוף ל-halt.json ומינוף דינמי עד ×50 (Isolated Margin)
"""
from __future__ import annotations

import logging
import math
import os
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import Config
from ..data.news import refresh_news_to_store
from ..data.store import Store
from ..notify import Notifier
from ..runtime import read_halt, write_halt
from .broker import PaperPerpBroker, PerpsExecutionUncertain
from .exchange import MultiPerpExchange
from .models import PerpBook, PerpCandle, PerpFill, PerpInstrument, PerpOrder, PerpPosition, PerpSignal, utcnow
from .risk import PerpRiskManager, calc_liquidation_price
from ..unified_risk import ensure_unified_day_baseline, evaluate_unified_entry, unified_entry_lock
from .signals import ProMultiRegimeEngine, assess_perps_news

log = logging.getLogger(__name__)


# The service creates a fresh PerpEngine per cycle. Keep the uncertain-execution
# latch per ledger for the lifetime of this process, even if halt-file persistence fails.
_EXECUTION_UNCERTAIN_LOCK = threading.RLock()
_EXECUTION_UNCERTAIN_DATABASES: set[str] = set()


def _execution_latch_key(db_path: str | Path) -> str:
    return str(Path(db_path).expanduser().resolve())


def _execution_latched(db_key: str) -> bool:
    with _EXECUTION_UNCERTAIN_LOCK:
        return db_key in _EXECUTION_UNCERTAIN_DATABASES


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
        self._execution_latch_key = _execution_latch_key(cfg.data.db_path)

        self.cash: float = self.pcfg.risk.starting_cash
        self.realized_pnl: float = 0.0
        self.realized_pnl_today: float = 0.0
        self.positions: dict[str, PerpPosition] = {}
        self._last_marks: dict[str, float] = {}
        self._last_day = utcnow().date()
        self._news_articles: list[dict[str, Any]] = []
        # Shared by every PerpEngine instance that uses this ledger in this process.
        self._execution_uncertain = _execution_latched(self._execution_latch_key)
        existing_halt = read_halt()
        if existing_halt and existing_halt.source == "execution_uncertain":
            with _EXECUTION_UNCERTAIN_LOCK:
                _EXECUTION_UNCERTAIN_DATABASES.add(self._execution_latch_key)
            self._execution_uncertain = True
        self._restore_state()

    def _mark_execution_uncertain(self, reason: str) -> None:
        """Latch this ledger for all engine instances in the process, then persist if possible."""
        self._execution_uncertain = True
        with _EXECUTION_UNCERTAIN_LOCK:
            _EXECUTION_UNCERTAIN_DATABASES.add(self._execution_latch_key)
        try:
            write_halt(reason, source="execution_uncertain")
        except Exception as exc:  # noqa: BLE001 — memory latch is the last-resort in-process stop.
            log.critical("Could not persist PERPS execution-uncertain halt: %s", exc)
        try:
            self.store.event("perp_execution_uncertain", reason, data={"ledger": self._execution_latch_key})
        except Exception as exc:  # noqa: BLE001
            log.critical("Could not persist PERPS uncertainty event: %s", exc)

    def _execution_blocked(self) -> bool:
        if self._execution_uncertain or _execution_latched(self._execution_latch_key):
            return True
        halt = read_halt()
        if halt and halt.source == "execution_uncertain":
            self._mark_execution_uncertain(halt.reason)
            return True
        return False

    def _execute_broker_order(self, order: PerpOrder, **kwargs):
        if self._execution_blocked():
            raise PerpsExecutionUncertain(
                "PERPS execution is latched as uncertain; reconcile the venue before any new order"
            )
        try:
            return self.broker.execute(order, **kwargs)
        except PerpsExecutionUncertain as exc:
            self._mark_execution_uncertain(str(exc))
            raise

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
            arts = [dict(r) for r in self.store.recent_news(hours=12.0, limit=140)]
            if (
                self.cfg.news.enabled
                and os.getenv("PMMB_DISABLE_LIVE_NEWS") != "1"
                and (not arts or (time.time() - max(int(a.get("ts") or 0) for a in arts)) > self.cfg.news.refresh_interval_sec)
            ):
                refresh_news_to_store(self.store, markets=[], max_market_queries=0)
                arts = [dict(r) for r in self.store.recent_news(hours=12.0, limit=140)]
            self._news_articles = arts
        except Exception:
            self._news_articles = []

    def monitor_open_positions(self) -> PerpCycleStats:
        """ניטור מהיר (Sub-second) רק לפוזיציות פתוחות — לעצירת SL/TP/Trailing בין מחזורים."""
        stats = PerpCycleStats()
        if self._execution_blocked():
            stats.skip("תוצאת ביצוע לא ודאית — נדרש Reconcile")
            return stats
        if not self.positions:
            return stats
        self._load_news()
        try:
            uni = self.exchange.scan()
            imap = {i.symbol: i for i in uni}
        except Exception:
            imap = {}

        for sym in list(self.positions.keys()):
            pos = self.positions[sym]
            inst = imap.get(sym) or PerpInstrument(
                symbol=sym, exchange=pos.exchange,
                exchange_symbol=f"{sym}-USDT-SWAP" if pos.exchange == "okx" else sym,
                max_leverage=pos.leverage, mark_price=self._last_marks.get(sym, pos.entry_price),
            )
            bk = self.exchange.get_book(inst, levels=8)
            mark = (bk.mid if bk and bk.mid else inst.mark_price)
            self._last_marks[sym] = mark
            try:
                self._process_position(pos, inst, None, bk, mark, stats)
            except PerpsExecutionUncertain as exc:
                self._mark_execution_uncertain(str(exc))
                stats.errors += 1
                log.critical(
                    "PERPS monitor stopped after uncertain execution for %s: %s",
                    sym, exc, exc_info=True,
                )
                break

        used_margin = sum(p.margin_used for p in self.positions.values())
        tot_notional = sum(p.notional for p in self.positions.values())
        avg_lev = (tot_notional / used_margin) if used_margin > 0 else 0.0
        self.store.snapshot_perp_equity(
            self.pcfg.mode, self._equity(), self.cash, used_margin, tot_notional, len(self.positions), avg_lev
        )
        return stats

    def run_once(self) -> PerpCycleStats:
        stats = PerpCycleStats()
        if self._execution_blocked():
            stats.skip("תוצאת ביצוע לא ודאית — נדרש Reconcile")
            return stats
        self._roll_day_if_needed()
        # Capture the UTC-day anchor before any PERPS position can be closed.
        with unified_entry_lock(self.cfg):
            ensure_unified_day_baseline(self.store, self.cfg)
        self._load_news()

        try:
            instruments = self.exchange.scan()
        except Exception as exc:
            log.error("Perps scan נכשל: %s", exc)
            stats.errors += 1
            return stats

        stats.scanned = len(instruments)
        inst_map = {i.symbol: i for i in instruments}

        # משיכה מקבילית של נרות + L2 Book לכל החוזים (מקצר מחזור מ-~10 שנ' ל-~1.8 שנ')
        tf = self.pcfg.signal.timeframe
        lb = self.pcfg.signal.lookback_candles

        def _fetch_one(inst: PerpInstrument) -> tuple[str, list[PerpCandle], PerpBook | None]:
            cs = self.exchange.get_candles(inst, interval=tf, lookback=lb)
            bk = self.exchange.get_book(inst)
            return inst.symbol, cs, bk

        fetched: dict[str, tuple[list[PerpCandle], PerpBook | None]] = {}
        if instruments:
            workers = min(8, len(instruments))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for sym, cs, bk in pool.map(_fetch_one, instruments):
                    fetched[sym] = (cs, bk)

        btc_candles: list[PerpCandle] = fetched.get("BTC", ([], None))[0]
        if not btc_candles and "BTC" not in fetched:
            btc_stub = PerpInstrument(symbol="BTC", exchange="okx", exchange_symbol="BTC-USDT-SWAP", max_leverage=50.0, mark_price=1.0)
            btc_candles = self.exchange.get_candles(btc_stub, interval=tf, lookback=lb)

        intel_rows: list[dict[str, Any]] = []
        pending_entries: list[tuple[PerpInstrument, PerpSignal, PerpBook | None, dict[str, Any]]] = []

        for inst in instruments:
            try:
                candles, book = fetched.get(inst.symbol, ([], None))
                if candles:
                    self.store.insert_perp_candles(
                        inst.symbol, inst.exchange, tf,
                        [(c.ts, c.open, c.high, c.low, c.close, c.volume) for c in candles[-120:]],
                    )
                mark = (book.mid if book and book.mid else (candles[-1].close if candles else inst.mark_price))
                self._last_marks[inst.symbol] = mark

                if inst.symbol in self.positions:
                    with unified_entry_lock(self.cfg):
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
            except PerpsExecutionUncertain as exc:
                self._mark_execution_uncertain(str(exc))
                stats.errors += 1
                log.critical(
                    "PERPS stopped after uncertain execution for %s: %s",
                    inst.symbol,
                    exc,
                    exc_info=True,
                )
                break
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
                try:
                    with unified_entry_lock(self.cfg):
                        self._process_position(pos, inst_stub, None, bk, mk_px, stats)
                except PerpsExecutionUncertain as exc:
                    self._mark_execution_uncertain(str(exc))
                    stats.errors += 1
                    log.critical(
                        "PERPS stopped after uncertain orphan-position execution for %s: %s",
                        sym,
                        exc,
                        exc_info=True,
                    )
                    break

        # בדיקת Kill Switch גלובלי ועצירת חירום (halt.json) לפני כניסות חדשות
        self.risk.check_global_kill(self._equity(), self.realized_pnl_today)
        halted = read_halt()
        if self._execution_blocked():
            stats.skip("תוצאת ביצוע לא ודאית — נדרש Reconcile")
        elif halted:
            stats.skip(f"עצירת חירום פעילה ({halted.reason})")
        else:
            pending_entries.sort(key=lambda item: (-float(item[1].score), -float(item[0].volume_24h_usd)))
            for inst, sig, book, row in pending_entries:
                if self._execution_blocked():
                    stats.skip("תוצאת ביצוע לא ודאית — נדרש Reconcile")
                    break
                try:
                    self._handle_entry(inst, sig, book, row, stats)
                except PerpsExecutionUncertain as exc:
                    self._mark_execution_uncertain(str(exc))
                    stats.errors += 1
                    stats.skip("תוצאת ביצוע לא ודאית — נדרש Reconcile")
                    break

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

    def _apply_close_fill(
        self,
        pos: PerpPosition,
        fill: PerpFill,
        reason: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Apply only confirmed close quantity; keep the residual position open on partial fills."""
        now = now or utcnow()
        if (
            not math.isfinite(float(fill.size))
            or not math.isfinite(float(fill.price))
            or fill.size <= 0
            or fill.price <= 0
            or pos.size <= 0
        ):
            reason_text = f"Invalid confirmed close fill for {pos.exchange} {pos.symbol}"
            self._mark_execution_uncertain(reason_text)
            raise PerpsExecutionUncertain(reason_text)

        tolerance = max(1e-9, abs(pos.size) * 1e-6)
        if fill.size > pos.size + tolerance:
            reason_text = (
                f"Close fill exceeds local position for {pos.exchange} {pos.symbol}: "
                f"filled={fill.size:g}, local={pos.size:g}"
            )
            self._mark_execution_uncertain(reason_text)
            raise PerpsExecutionUncertain(reason_text)

        closed_size = min(float(fill.size), float(pos.size))
        fraction = min(1.0, closed_size / float(pos.size))
        allocated_margin = float(pos.margin_used) * fraction
        allocated_open_fee = float(pos.fees_paid) * fraction
        allocated_funding = float(pos.accumulated_funding) * fraction

        gross_pnl = (
            (float(fill.price) - pos.entry_price) * closed_size
            if pos.side == "LONG"
            else (pos.entry_price - float(fill.price)) * closed_size
        )
        net_pnl = max(
            -allocated_margin,
            gross_pnl - float(fill.fee) - allocated_open_fee + allocated_funding,
        )
        margin_back = max(0.0, allocated_margin + gross_pnl)

        # Persist exactly the confirmed exchange fill, not the requested close quantity.
        fill.size = closed_size
        fill.notional = round(float(fill.price) * closed_size, 8)
        fill.margin_delta = round(margin_back, 8)
        fill.realized = round(net_pnl, 8)
        fill.funding = round(allocated_funding, 8)

        self.cash += margin_back - float(fill.fee)
        self.realized_pnl += net_pnl
        self.realized_pnl_today += net_pnl
        self.store.record_perp_fill(fill, self.pcfg.mode)

        remaining = max(0.0, float(pos.size) - closed_size)
        fully_closed = remaining <= tolerance
        if fully_closed:
            self.store.close_perp_position(pos.symbol, reason, net_pnl)
            self.positions.pop(pos.symbol, None)
            self.risk.start_cooldown(pos.symbol, now)
            remaining = 0.0
        else:
            pos.size = remaining
            pos.notional = round(pos.entry_price * remaining, 8)
            pos.margin_used = max(0.0, float(pos.margin_used) - allocated_margin)
            pos.fees_paid = max(0.0, float(pos.fees_paid) - allocated_open_fee)
            pos.accumulated_funding = float(pos.accumulated_funding) - allocated_funding
            self.store.upsert_perp_position(pos, self.pcfg.mode)

        return {
            "closed_size": closed_size,
            "remaining_size": remaining,
            "realized": net_pnl,
            "fully_closed": fully_closed,
            "margin_returned": margin_back,
        }

    def _process_position(
        self,
        pos: PerpPosition,
        inst: PerpInstrument,
        last_candle: PerpCandle | None,
        book: PerpBook | None,
        mark: float,
        stats: PerpCycleStats,
    ) -> None:
        if self._execution_blocked():
            # The last live order outcome is unresolved. Do not issue another close/order
            # until an operator reconciles the exchange account and clears the halt.
            return
        now = utcnow()
        now_ts = int(now.timestamp())
        elapsed_h = max(0.0, (now_ts - pos.last_funding_ts) / 3600.0)
        if elapsed_h >= 1.0 and inst.funding_1h != 0.0:
            hours = int(elapsed_h)
            f_pnl = (-pos.notional * inst.funding_1h * hours) if pos.side == "LONG" else (pos.notional * inst.funding_1h * hours)
            pos.accumulated_funding += f_pnl
            self.cash += f_pnl
            pos.last_funding_ts += hours * 3600
            stats.funding_net += f_pnl

        # הגנת נר-כניסה: אם הפוזיציה נפתחה בתוך הנר השעתי האחרון, High/Low שלו יכולים לכלול תנועת טרום-כניסה!
        if last_candle is not None and int(pos.opened_at.timestamp()) < last_candle.ts:
            hi = last_candle.high
            lo = last_candle.low
        else:
            hi = mark
            lo = mark
        exit_reason = self.risk.evaluate_exit_and_trail(pos, mark_price=mark, high_price=hi, low_price=lo, now=now)

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
        fill = self._execute_broker_order(
            order, book=book, taker_fee_bps=inst.taker_fee_bps,
            ct_val=inst.contract_val, lot_size=inst.lot_size, tick_size=inst.tick_size,
        )
        if fill is None:
            return

        applied = self._apply_close_fill(pos, fill, exit_reason, now=now)
        stats.exits += 1

        if applied["fully_closed"]:
            exit_label = "יציאה"
        else:
            exit_label = f"יציאה חלקית {applied['closed_size']:.6g}/{applied['closed_size'] + applied['remaining_size']:.6g} · נותרו {applied['remaining_size']:.6g}"
        msg = (
            f"⚡ {exit_label} PERPS {pos.symbol} {pos.side} ×{pos.leverage:.0f} ({pos.exchange.upper()}) | "
            f"{exit_reason} | נטו {applied['realized']:+.2f} USDC"
        )
        log.info(msg)
        self._notify(msg)
        self.store.event("perp_exit", msg, data={
            "symbol": pos.symbol,
            "realized": applied["realized"],
            "leverage": pos.leverage,
            "closed_size": applied["closed_size"],
            "remaining_size": applied["remaining_size"],
            "partial": not applied["fully_closed"],
        })

    def _handle_entry(
        self,
        inst: PerpInstrument,
        sig: PerpSignal,
        book: PerpBook | None,
        row: dict[str, Any],
        stats: PerpCycleStats,
    ) -> None:
        # Keep the shared admission check locked through broker execution and DB persistence.
        with unified_entry_lock(self.cfg):
            return self._handle_entry_locked(inst, sig, book, row, stats)

    def _handle_entry_locked(
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

        # Reserve for entry slippage and taker fees before the fill is persisted.
        margin_buffer = (self.pcfg.slippage_bps + self.pcfg.taker_fee_bps) / 10_000.0
        shared = evaluate_unified_entry(
            self.store, self.cfg, arm="perps",
            proposed_capital=dec.margin * (1.0 + margin_buffer),
        )
        if not shared.approved:
            stats.skip(f"סיכון תיק מאוחד: {shared.reason}")
            row["reason"] = f"נדחה בשער תיק מאוחד: {shared.reason}"
            log.info("⛔ Shared portfolio guard blocked PERPS %s: %s", inst.symbol, shared.reason)
            return

        order = PerpOrder(
            symbol=inst.symbol, exchange=inst.exchange, side=sig.direction,  # type: ignore[arg-type]
            action="OPEN", price=sig.price, size=dec.size, leverage=dec.leverage,
            reduce_only=False, reason=f"{sig.tier} {sig.strategy} | {sig.reason}",
        )
        fill = self._execute_broker_order(
            order, book=book, taker_fee_bps=inst.taker_fee_bps,
            ct_val=inst.contract_val, lot_size=inst.lot_size, tick_size=inst.tick_size,
        )
        if fill is None:
            stats.skip("מילוי Perps נכשל")
            return

        actual_leverage = float(fill.leverage or dec.leverage)
        margin_used = round(fill.notional / actual_leverage, 4)
        fill.margin_delta = -margin_used
        self.cash -= margin_used + fill.fee

        liq_px = calc_liquidation_price(sig.direction, fill.price, actual_leverage, inst.mmr or self.pcfg.risk.default_mmr)
        pos = PerpPosition(
            symbol=inst.symbol, exchange=inst.exchange, side=sig.direction,  # type: ignore[arg-type]
            size=fill.size, entry_price=fill.price, notional=fill.notional,
            leverage=actual_leverage, margin_used=margin_used, liquidation_price=round(liq_px, 6),
            stop_price=dec.stop_price, target_price=dec.target_price,
            highest_price=fill.price, lowest_price=fill.price, atr=sig.atr,
            strategy=sig.strategy, regime=sig.regime, entry_score=sig.score,
            fees_paid=fill.fee, opened_at=fill.ts, last_funding_ts=int(fill.ts.timestamp()),
        )
        self.positions[inst.symbol] = pos
        self.store.record_perp_fill(fill, self.pcfg.mode)
        self.store.upsert_perp_position(pos, self.pcfg.mode)
        row["status"] = "OPEN"
        row["reason"] = f"כניסה {sig.direction} ×{actual_leverage:.0f} ({sig.tier}) @ {fill.price:.4f}"
        stats.entries += 1

        msg = (
            f"🚀 כניסה PERPS {inst.symbol} {sig.direction} ×{actual_leverage:.0f} [{sig.tier}] "
            f"@ {fill.price:.4f} | מרג'ין {margin_used:.2f}$ | נומינלי {fill.notional:.0f}$ | "
            f"SL={dec.stop_price:.4f} TP={dec.target_price:.4f} LIQ={pos.liquidation_price:.4f}"
        )
        log.info(msg)
        self._notify(msg)
        self.store.event("perp_entry", msg, data={"symbol": inst.symbol, "leverage": actual_leverage, "margin": margin_used})

    def close_position_by_symbol(self, symbol: str, reason: str = "סגירה ידנית מהטרמינל") -> dict[str, Any]:
        """סוגר פוזיציית PERPS תחת הנעילה המאוחדת."""
        with unified_entry_lock(self.cfg):
            ensure_unified_day_baseline(self.store, self.cfg)
            return self._close_position_by_symbol_locked(symbol, reason)

    def _close_position_by_symbol_locked(self, symbol: str, reason: str) -> dict[str, Any]:
        """סגירת PERPS ידנית; caller מחזיק unified_entry_lock."""
        if self._execution_blocked():
            raise PerpsExecutionUncertain("PERPS execution is latched as uncertain; reconcile before manual close")
        sym = symbol.strip().upper()
        pos = self.positions.get(sym)
        if pos is None:
            raise KeyError(f"אין פוזיציית PERPS פתוחה עבור {sym}")

        now = utcnow()
        inst = next((x for x in self.exchange.scan() if x.symbol == sym), None)
        if inst is None:
            inst = PerpInstrument(
                symbol=pos.symbol,
                exchange=pos.exchange,
                exchange_symbol=f"{pos.symbol}-USDT-SWAP",
                max_leverage=max(50.0, pos.leverage),
                mark_price=self._last_marks.get(sym, pos.entry_price),
            )
        book = self.exchange.get_book(inst, levels=8)
        mark = (
            (book.best_bid if pos.side == "LONG" else book.best_ask)
            if book is not None
            else None
        ) or inst.mark_price or self._last_marks.get(sym, pos.entry_price)

        order = PerpOrder(
            symbol=pos.symbol,
            exchange=pos.exchange,
            side=pos.side,
            action="CLOSE",
            price=float(mark),
            size=pos.size,
            leverage=pos.leverage,
            reduce_only=True,
            reason=reason,
        )
        fill = self._execute_broker_order(
            order,
            book=book,
            taker_fee_bps=inst.taker_fee_bps,
            ct_val=inst.contract_val,
            lot_size=inst.lot_size,
            tick_size=inst.tick_size,
        )
        if fill is None:
            raise RuntimeError(
                f"סגירת {sym} לא מולאה בבורסה; הפוזיציה נשארה פתוחה ולא נרשם מילוי מדומה"
            )

        applied = self._apply_close_fill(pos, fill, reason, now=now)

        snap_eq = self._equity()
        used_margin = sum(p.margin_used for p in self.positions.values())
        notional_tot = sum(p.notional for p in self.positions.values())
        avg_lev = (notional_tot / used_margin) if used_margin > 0 else 0.0
        self.risk.update_peak(snap_eq)
        self.store.snapshot_perp_equity(
            self.pcfg.mode,
            snap_eq,
            self.cash,
            used_margin,
            notional_tot,
            len(self.positions),
            avg_lev,
        )

        msg = (
            f"⚡ סגירה ידנית PERPS {pos.symbol} {pos.side} ×{pos.leverage:.0f} | "
            f"{reason} | כמות {applied['closed_size']:.6g} | "
            f"נותרה {applied['remaining_size']:.6g} | נטו {applied['realized']:+.2f} USDC"
        )
        log.info(msg)
        self._notify(msg)
        self.store.event("perp_exit", msg, data={
            "symbol": pos.symbol,
            "realized": applied["realized"],
            "manual": True,
            "closed_size": applied["closed_size"],
            "remaining_size": applied["remaining_size"],
            "partial": not applied["fully_closed"],
        })
        return {
            "arm": "perps",
            "key": sym,
            "label": f"{pos.symbol} {pos.side} ×{pos.leverage:.0f}",
            "price": round(fill.price, 6),
            "size": round(applied["closed_size"], 6),
            "remaining_size": round(applied["remaining_size"], 6),
            "partial": not applied["fully_closed"],
            "realized": round(applied["realized"], 2),
        }

    def open_manual_order(
        self,
        symbol: str,
        side: str,
        margin_usd: float,
        leverage: float,
        *,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> dict[str, Any]:
        """פתיחת עסקת PERPS ידנית (במצב paper בלבד) עם שמירת הגנת ניזול ו-SL/TP אוטומטיים."""
        with unified_entry_lock(self.cfg):
            return self._open_manual_order_locked(
                symbol, side, margin_usd, leverage,
                stop_price=stop_price, target_price=target_price,
            )

    def _open_manual_order_locked(
        self,
        symbol: str,
        side: str,
        margin_usd: float,
        leverage: float,
        *,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> dict[str, Any]:
        if self.pcfg.mode != "paper":
            raise PermissionError("פקודה ידנית מהממשק מותרת במצב paper בלבד")
        sym = symbol.strip().upper()
        dir_u = side.strip().upper()
        if dir_u not in ("LONG", "SHORT"):
            raise ValueError("כיוון חייב להיות LONG או SHORT")
        if sym in self.positions:
            raise ValueError(f"כבר קיימת פוזיציה פתוחה עבור {sym} — סגור אותה קודם")
        margin = float(margin_usd)
        if margin < 5.0:
            raise ValueError("מרג'ין מינימלי לעסקה הוא 5 USDC")
        if margin > self.cash * 0.96:
            raise ValueError(f"אין מספיק מזומן פנוי ב-PERPS ({self.cash:.2f} USDC)")

        req_lev = max(2.0, min(float(self.pcfg.risk.max_leverage), float(leverage)))
        inst = next((x for x in self.exchange.scan() if x.symbol == sym), None)
        if inst is None:
            intel = {r["symbol"]: r for r in self.store.recent_perp_intel(limit=40)}
            r = intel.get(sym) or {}
            inst = PerpInstrument(
                symbol=sym,
                exchange=str(r.get("exchange") or "okx"),
                exchange_symbol=f"{sym}-USDT-SWAP",
                max_leverage=float(r.get("max_leverage") or 50.0),
                mark_price=float(r.get("price") or 0.0),
            )
        candles = self.exchange.get_candles(inst, interval=self.pcfg.signal.timeframe, lookback=60)
        book = self.exchange.get_book(inst, levels=8)
        px = (
            (book.best_ask if dir_u == "LONG" else book.best_bid)
            if book is not None
            else None
        ) or (candles[-1].close if candles else None) or inst.mark_price
        if not px or px <= 0:
            raise ValueError(f"לא נמצא מחיר שוק חי עבור {sym}")

        from .signals import calc_atr

        atr = calc_atr(candles, 14) if len(candles) >= 15 else px * 0.012
        atr = max(atr, px * 0.004)
        rk = self.pcfg.risk
        if stop_price is None:
            sl_dist = rk.sl_atr_mult * atr
            stop_px = round(px - sl_dist, 6) if dir_u == "LONG" else round(px + sl_dist, 6)
        else:
            stop_px = float(stop_price)
        if target_price is None:
            tp_dist = rk.tp_atr_mult * atr
            tp_px = round(px + tp_dist, 6) if dir_u == "LONG" else round(px - tp_dist, 6)
        else:
            tp_px = float(target_price)

        # הגנה קשיחה: SL חייב להישאר לפני נקודת הליקווידציה (כפוף ל-liquidation_buffer_mult)
        mmr = inst.mmr or rk.default_mmr
        stop_dist_pct = abs(px - stop_px) / px
        rt_cost = 2.0 * (self.pcfg.taker_fee_bps + self.pcfg.slippage_bps) / 10_000.0
        safe_lev_cap = max(2.0, (1.0 - mmr) / max(1e-4, stop_dist_pct * 1.35 + rt_cost))
        lev = round(min(req_lev, inst.max_leverage, safe_lev_cap), 1)
        notional = round(margin * lev, 2)
        size = round(notional / px, 6)

        margin_buffer = (self.pcfg.slippage_bps + self.pcfg.taker_fee_bps) / 10_000.0
        shared = evaluate_unified_entry(
            self.store, self.cfg, arm="perps",
            proposed_capital=margin * (1.0 + margin_buffer),
        )
        if not shared.approved:
            raise PermissionError(f"שער תיק מאוחד חסם פקודה ידנית: {shared.reason}")

        order = PerpOrder(
            symbol=sym, exchange=inst.exchange, side=dir_u,  # type: ignore[arg-type]
            action="OPEN", price=float(px), size=size, leverage=lev,
            reduce_only=False, reason=f"פקודה ידנית ({dir_u} ×{lev:.1f})",
        )
        fill = self._execute_broker_order(
            order, book=book, taker_fee_bps=inst.taker_fee_bps,
            ct_val=inst.contract_val, lot_size=inst.lot_size, tick_size=inst.tick_size,
        )
        if fill is None:
            raise RuntimeError("ביצוע הפקודה הידנית נדחה")

        margin_used = round(fill.notional / lev, 4)
        fill.margin_delta = -margin_used
        self.cash -= margin_used + fill.fee
        liq_px = calc_liquidation_price(dir_u, fill.price, lev, mmr)
        pos = PerpPosition(
            symbol=sym, exchange=inst.exchange, side=dir_u,  # type: ignore[arg-type]
            size=fill.size, entry_price=fill.price, notional=fill.notional,
            leverage=lev, margin_used=margin_used, liquidation_price=round(liq_px, 6),
            stop_price=stop_px, target_price=tp_px,
            highest_price=fill.price, lowest_price=fill.price, atr=atr,
            strategy="manual", regime="MANUAL", entry_score=1.0,
            fees_paid=fill.fee, opened_at=fill.ts, last_funding_ts=int(fill.ts.timestamp()),
        )
        self.positions[sym] = pos
        self._last_marks[sym] = fill.price
        self.store.record_perp_fill(fill, self.pcfg.mode)
        self.store.upsert_perp_position(pos, self.pcfg.mode)

        eq = self._equity()
        used_m = sum(p.margin_used for p in self.positions.values())
        tot_not = sum(p.notional for p in self.positions.values())
        avg_l = (tot_not / used_m) if used_m > 0 else 0.0
        self.store.snapshot_perp_equity(self.pcfg.mode, eq, self.cash, used_m, tot_not, len(self.positions), avg_l)
        msg = f"🎯 פקודה ידנית PERPS {sym} {dir_u} ×{lev:.1f} @ {fill.price:.4f} | מרג'ין {margin_used:.2f}$"
        log.info(msg)
        self.store.event("perp_entry", msg, data={"symbol": sym, "manual": True, "leverage": lev})
        return {
            "symbol": sym, "side": dir_u, "leverage": lev, "price": round(fill.price, 6),
            "margin": round(margin_used, 2), "notional": round(fill.notional, 2),
            "stop_price": stop_px, "target_price": tp_px, "liquidation_price": round(liq_px, 6),
        }

    def update_position_levels(
        self,
        symbol: str,
        *,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> dict[str, Any]:
        """מעדכן Stop-Loss ו/או Take-Profit של פוזיציית PERPS פתוחה."""
        sym = symbol.strip().upper()
        pos = self.positions.get(sym)
        if pos is None:
            raise KeyError(f"אין פוזיציית PERPS פתוחה עבור {sym}")

        new_sl = float(stop_price) if stop_price is not None else pos.stop_price
        new_tp = float(target_price) if target_price is not None else pos.target_price
        if pos.side == "LONG":
            if new_sl <= pos.liquidation_price:
                raise ValueError(f"SL ({new_sl:.4f}) חייב להיות גבוה מנקודת הליקווידציה ({pos.liquidation_price:.4f})")
            if new_tp <= pos.entry_price * 0.5:
                raise ValueError("יעד רווח לא תקין")
        else:
            if new_sl >= pos.liquidation_price:
                raise ValueError(f"SL ({new_sl:.4f}) חייב להיות נמוך מנקודת הליקווידציה ({pos.liquidation_price:.4f})")

        pos.stop_price = round(new_sl, 6)
        pos.target_price = round(new_tp, 6)
        self.store.upsert_perp_position(pos, self.pcfg.mode)
        self.store.event("perp_update", f"עדכון SL/TP {sym}: SL={pos.stop_price:.4f} TP={pos.target_price:.4f}")
        return {"symbol": sym, "stop_price": pos.stop_price, "target_price": pos.target_price}

    def close_all_positions(self, reason: str = "סגירת כל הפוזיציות מהטרמינל") -> list[dict[str, Any]]:
        """סוגר את כל פוזיציות ה-PERPS הפתוחות בזרוע זו."""
        closed: list[dict[str, Any]] = []
        for sym in list(self.positions.keys()):
            closed.append(self.close_position_by_symbol(sym, reason=reason))
        return closed

    def close(self) -> None:
        self.store.close()
