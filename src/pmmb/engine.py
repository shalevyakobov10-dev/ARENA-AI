"""
האינג'ין — הלב של הבוט.

מחזור אחד:
  סריקת יקום → לכל שוק: היסטוריה → סיגנל → (יציאה אם יש פוזיציה) → (כניסה אם אין)
  → רישום ל-DB → snapshot להון → בדיקות kill switch.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import Config
from .data.clob import Book, ClobClient
from .data.gamma import GammaClient, MarketUniverse
from .data.http import HttpClient
from .data.store import Store
from .execution.base import Portfolio
from .execution.paper import PaperBroker
from .models import Fill, Market, Order, Position, Signal, utcnow
from .risk.manager import RiskManager
from .notify import Notifier, fmt_entry, fmt_exit, fmt_halt
from .runtime import Heartbeat, write_heartbeat
from .signals import build_signal_engine

log = logging.getLogger(__name__)


# סיבת דחייה → קטגוריה קריאה. בלי זה כל z שונה יוצר מפתח חדש והסטטיסטיקה חסרת תועלת.
_SKIP_BUCKETS: tuple[tuple[str, str], ...] = (
    ("אין עודף", "אין עודף חריג"),
    ("תנועה קיצונית", "תנועה קיצונית (מעל z_max)"),
    ("עלייה חדה", "עלייה חדה — לא קונים"),
    ("עוצמה", "עוצמה מתחת לסף"),
    ("edge", "edge לא מכסה עלויות"),
    ("היסטוריה", "אין מספיק היסטוריה"),
    ("ספר", "ספר פקודות דק או חסר"),
    ("מילוי", "מילוי לא מומש"),
    ("cooldown", "קירור אחרי יציאה"),
    ("פוזיציה", "כבר יש פוזיציה"),
)


def normalize_skip(reason: str) -> str:
    low = reason.lower()
    for needle, label in _SKIP_BUCKETS:
        if needle.lower() in low:
            return label
    return reason.split("(")[0].strip()[:32]


@dataclass
class CycleStats:
    scanned: int = 0
    signalled: int = 0
    entries: int = 0
    exits: int = 0
    errors: int = 0
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[normalize_skip(reason)] = self.skipped.get(normalize_skip(reason), 0) + 1


class Engine:
    def __init__(
        self,
        cfg: Config,
        *,
        store: Store | None = None,
        broker=None,
        clob: ClobClient | None = None,
        gamma: GammaClient | None = None,
        engine_signals=None,
    ) -> None:
        self.cfg = cfg
        self.store = store or Store(cfg.data.db_path)
        self.clob = clob or ClobClient(
            HttpClient(
                cfg.data.clob_base_url,
                cfg.data.http_timeout,
                cfg.data.max_retries,
                cfg.data.rate_limit_rps,
            ),
            history_ttl=cfg.data.history_cache_ttl_sec,
        )
        self.gamma = gamma or GammaClient(
            HttpClient(
                cfg.data.gamma_base_url,
                cfg.data.http_timeout,
                cfg.data.max_retries,
                cfg.data.rate_limit_rps,
            )
        )
        self.universe = MarketUniverse(self.gamma, cfg.universe)
        self.signals = engine_signals or build_signal_engine(cfg.signal)
        self.risk = RiskManager(cfg)
        self.broker = broker or PaperBroker(cfg.execution, self.clob)
        self.portfolio = Portfolio(cfg.execution.starting_cash, mode=cfg.execution.mode, store=self.store)
        self.markets: dict[str, Market] = {}
        self._last_marks: dict[str, float] = {}

    # ==================================================================
    #  מחזור
    # ==================================================================
    cycle: int = 0
    notifier: Notifier | None = None

    def _notify(self, text: str) -> None:
        if self.notifier is None:
            self.notifier = Notifier()
        self.notifier.send(text)

    def run_once(self) -> CycleStats:
        self.cycle += 1
        stats = CycleStats()
        self.portfolio.roll_day_if_needed()
        self._check_global_risk()

        try:
            markets = self.universe.scan()
        except ConnectionError as exc:
            log.error("סריקת היקום נכשלה: %s", exc)
            stats.errors += 1
            return stats

        stats.scanned = len(markets)
        self.markets = {m.condition_id: m for m in markets}

        for mk in markets:
            try:
                self._process_market(mk, stats)
            except Exception as exc:  # לא מפילים את כל המחזור בגלל שוק אחד
                stats.errors += 1
                log.exception("שגיאה בעיבוד %s: %s", mk.slug, exc)

        # --- סגירת פוזיציות שאין להן יותר שוק פעיל ---
        self._close_orphans()

        marks = self._last_marks
        snap = self.portfolio.snapshot(marks)
        self.risk.update_peak(snap.equity)
        self.store.snapshot_equity(snap)
        log.info(
            "📊 מחזור: נסרקו %d | סיגנלים %d | כניסות %d | יציאות %d | שגיאות %d | "
            "הון %.2f | מזומן %.2f | חשיפה %.2f | פוזיציות %d",
            stats.scanned, stats.signalled, stats.entries, stats.exits, stats.errors,
            snap.equity, snap.cash, snap.exposure, snap.open_positions,
        )
        if stats.skipped:
            log.debug("דחיות: %s", stats.skipped)

        # --- דופק: הקובץ שמאפשר ל-watchdog ולטלפון לדעת שאנחנו חיים ---
        try:
            write_heartbeat(Heartbeat(
                ts=snap.ts.timestamp(), cycle=self.cycle,
                mode=self.cfg.execution.mode, engine=self.cfg.signal.engine,
                equity=snap.equity, cash=snap.cash, exposure=snap.exposure,
                positions=snap.open_positions,
                scanned=stats.scanned, signalled=stats.signalled,
                entries=stats.entries, exits=stats.exits, errors=stats.errors,
                halted=self.risk.halted, halt_reason=self.risk.halt_reason or "",
                pid=os.getpid(),
                skipped=dict(stats.skipped),
                guards=self._guard_state(snap),
            ))
        except Exception as exc:          # noqa: BLE001 — דופק לא מפיל מחזור
            log.warning("כתיבת דופק נכשלה: %s", exc)
        return stats

    def run_forever(self, interval_sec: float = 60.0, max_cycles: int | None = None) -> None:
        cycle = 0
        while max_cycles is None or cycle < max_cycles:
            cycle += 1
            log.info("─── מחזור #%d (%s) ───", cycle, datetime.now(tz=timezone.utc).strftime("%H:%M:%S"))
            try:
                self.run_once()
            except KeyboardInterrupt:
                log.warning("נעצר ע\"י המשתמש")
                break
            except Exception as exc:
                log.exception("מחזור נכשל: %s", exc)
            if self.risk.halted:
                log.error("הבוט עצור (%s) — מפסיק לרוץ", self.risk.halt_reason)
                break
            if max_cycles is not None and cycle >= max_cycles:
                break
            time.sleep(interval_sec)

    # ==================================================================
    #  שוק בודד
    # ==================================================================
    def _process_market(self, mk: Market, stats: CycleStats) -> None:
        cfg = self.cfg

        # --- ספר הפקודות קודם: הוא נדרש גם לסיגנל וגם לאיסוף הדאטה ---
        yes_book = self.clob.get_book(mk.yes_token_id)
        if yes_book is None:
            stats.skip("אין ספר פקודות")
            return
        if cfg.data.record_books:
            self.store.record_book(mk.yes_token_id, int(utcnow().timestamp()), yes_book)

        market_price = yes_book.mid or mk.yes_price
        if yes_book.mid is not None:
            self._last_marks[mk.yes_token_id] = yes_book.mid
            self._last_marks[mk.no_token_id] = 1.0 - yes_book.mid

        # --- היסטוריה ---
        candles = self.clob.get_history(
            mk.yes_token_id,
            fidelity_min=cfg.signal.candle_fidelity_min,
            lookback_candles=cfg.signal.lookback_candles,
        )
        if len(candles) < self.signals.min_candles:
            stats.skip("אין מספיק היסטוריה")
            return

        prices = [c.price for c in candles]
        self.store.insert_ticks([(mk.yes_token_id, c.ts, c.price) for c in candles])

        signal = self.signals.evaluate(
            mk, prices, market_price=market_price, spread=yes_book.spread,
            extra={"fee_rate": mk.taker_fee_rate},
        )
        if signal.direction != "FLAT":
            stats.signalled += 1
        self.store.record_signal(signal)

        # ---------- יציאות קודם ----------
        self._handle_exit(mk, signal, yes_book, stats)

        # ---------- כניסות ----------
        if signal.direction == "FLAT":
            stats.skip(f"סיגנל: {signal.reason}")
            return
        self._handle_entry(mk, signal, yes_book, stats)

    # ------------------------------------------------------------------
    def _handle_entry(self, mk: Market, signal: Signal, yes_book: Book, stats: CycleStats) -> None:
        if any(p.condition_id == mk.condition_id for p in self.portfolio.positions.values()):
            stats.skip("כבר בפוזיציה")
            return

        token_id = signal.token_id
        book = yes_book if signal.direction == "LONG" else self.clob.get_book(token_id)
        if book is None or not book.is_tradable():
            stats.skip("ספר לא סחיר")
            return

        price = book.best_ask
        if price is None or price <= 0:
            stats.skip("אין ask")
            return

        snap = self.portfolio.snapshot(self._last_marks)
        decision = self.risk.evaluate_entry(
            signal, mk, snap,
            price=price,
            tick=book.tick_size or mk.tick_size,
            min_order_size=max(book.min_order_size, self.cfg.risk.min_order_size),
        )
        if not decision.approved:
            stats.skip(f"סיכון: {decision.reason}")
            log.debug("⛔ %s | %s", mk.question[:60], decision.reason)
            return

        order = Order(
            token_id=token_id,
            side="BUY",
            price=price,
            size=decision.size,
            fee_rate=mk.taker_fee_rate,
            condition_id=mk.condition_id,
            reason=f"כניסה {signal.direction} | {signal.reason} | {decision.reason}",
        )
        fill = self.broker.execute(order, book=book)
        if fill is None:
            stats.skip("מילוי נכשל")
            return

        self.portfolio.apply_fill(fill)
        pos = self.portfolio.position_for(token_id)
        if pos is not None:
            pos.condition_id = mk.condition_id
            pos.direction = signal.direction
            pos.entry_score = signal.score
            pos.question = mk.question
            pos.stop_price = round(max(0.01, fill.price * (1 - self.cfg.signal.exit.stop_loss)), 4)
            pos.target_price = round(min(0.99, fill.price * (1 + self.cfg.signal.exit.take_profit)), 4)
            self.store.upsert_position(pos, self.cfg.execution.mode)

        stats.entries += 1
        self._notify(fmt_entry(self.cfg.execution.mode, mk.question, fill.price,
                               fill.size, signal.score, signal.edge))
        self.store.event(
            "entry", f"{signal.direction} {mk.slug}", data={
                "price": fill.price, "size": fill.size, "edge": signal.edge,
                "score": signal.score, "reason": order.reason,
            },
        )

    # ------------------------------------------------------------------
    def _handle_exit(self, mk: Market, signal: Signal, yes_book: Book, stats: CycleStats) -> None:
        for token_id, pos in list(self.portfolio.positions.items()):
            if pos.condition_id and pos.condition_id != mk.condition_id:
                continue

            book = yes_book if token_id == mk.yes_token_id else self.clob.get_book(token_id)
            if book is None or book.best_bid is None:
                continue
            mark = book.best_bid
            self._last_marks[token_id] = mark

            flipped = (
                signal.direction != "FLAT"
                and signal.token_id != token_id
            )
            reason = self.risk.evaluate_exit(pos, mark, signal_flipped=flipped)
            if reason is None:
                continue

            order = Order(
                token_id=token_id,
                side="SELL",
                price=mark,
                size=pos.size,
                fee_rate=mk.taker_fee_rate,
                condition_id=pos.condition_id,
                reason=f"יציאה: {reason}",
            )
            fill = self.broker.execute(order, book=book, aggressive=True)
            if fill is None:
                log.warning("יציאה לא מומשה עבור %s (%s) — ננסה שוב במחזור הבא",
                            mk.slug, reason)
                continue

            realized = self.portfolio.apply_fill(fill)
            self.risk.start_cooldown(mk.condition_id)
            stats.exits += 1
            log.info(
                "🚪 יציאה %s | %s | מחיר %.3f | רווח ממומש %+.2f",
                mk.question[:60], reason, fill.price, realized,
            )
            self._notify(fmt_exit(self.cfg.execution.mode, mk.question, fill.price,
                                  realized, reason))
            self.store.event(
                "exit", f"{mk.slug} — {reason}",
                data={"price": fill.price, "size": fill.size, "realized": realized},
            )

    # ------------------------------------------------------------------
    def _close_orphans(self) -> None:
        """פוזיציה בשוק שכבר לא בסריקה — סוגרים לפי midpoint אחרון."""
        for token_id, pos in list(self.portfolio.positions.items()):
            if pos.condition_id in self.markets:
                continue
            book = self.clob.get_book(token_id)
            if book is None or book.best_bid is None:
                continue
            order = Order(
                token_id=token_id, side="SELL", price=book.best_bid, size=pos.size,
                condition_id=pos.condition_id, reason="יציאה: השוק יצא מהיקום",
            )
            fill = self.broker.execute(order, book=book, aggressive=True)
            if fill:
                realized = self.portfolio.apply_fill(fill)
                log.info("🧹 סגירת יתומה %s | %+.2f", token_id[:10], realized)

    # ------------------------------------------------------------------
    def _guard_state(self, snap) -> dict:
        """מצב ההגנות כפי שהוא — כדי שהטלפון יראה כמה "מרווח" נשאר."""
        r = self.cfg.risk
        daily_limit = snap.equity * r.max_daily_loss_pct
        dd_limit = snap.equity * r.max_drawdown_pct
        return {
            "daily_loss_limit": round(daily_limit, 2),
            "daily_loss_used": round(max(0.0, -snap.realized_pnl_today), 2),
            "daily_room": round(daily_limit + snap.realized_pnl_today, 2),
            "drawdown_pct": round(snap.drawdown_pct * 100, 2),
            "drawdown_limit_pct": round(r.max_drawdown_pct * 100, 1),
            "exposure_room": round(snap.equity * r.max_total_exposure_pct - snap.exposure, 2),
            "positions_room": max(0, r.max_open_positions - snap.open_positions),
        }

    def _check_global_risk(self) -> None:
        snap = self.portfolio.snapshot(self._last_marks)
        self.risk.update_peak(snap.equity)
        if snap.drawdown_pct >= self.cfg.risk.max_drawdown_pct:
            self.risk.halt(f"drawdown {snap.drawdown_pct:.1%}")
            self._notify(fmt_halt(self.cfg.execution.mode, self.risk.halt_reason, snap.equity))
        if snap.realized_pnl_today <= -snap.equity * self.cfg.risk.max_daily_loss_pct:
            self.risk.halt(f"הפסד יומי {snap.realized_pnl_today:.2f}")
            self._notify(fmt_halt(self.cfg.execution.mode, self.risk.halt_reason, snap.equity))

    def close(self) -> None:
        self.store.close()
