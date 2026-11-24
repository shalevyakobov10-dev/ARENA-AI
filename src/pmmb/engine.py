"""
האינג'ין — הלב של הבוט.

מחזור אחד:
  סריקת יקום → לכל שוק: היסטוריה → סיגנל → (יציאה אם יש פוזיציה) → (כניסה אם אין)
  → רישום ל-DB → snapshot להון → בדיקות kill switch.
"""
from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import Config
from .data.clob import Book, ClobClient
from .data.gamma import GammaClient, MarketUniverse
from .data.http import HttpClient
from .data.store import Store
from .execution.base import Portfolio
from .execution.paper import PaperBroker
from .models import Fill, Market, Order, Position, Signal, utcnow
from .risk.manager import RiskManager
from .risk.sizing import stop_and_target
from .notify import Notifier, fmt_entry, fmt_exit, fmt_halt
from .runtime import Heartbeat, read_halt, write_heartbeat
from .signals import build_signal_engine
from .unified_risk import evaluate_unified_entry, unified_entry_lock

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
    ("לפדיון", "קרוב מדי לפדיון"),
    ("באירוע", "כבר חשוף לאירוע"),
    ("סקטור", "תקרת סקטור"),
    ("פוזיציה", "כבר יש פוזיציה"),
    ("חדשות", "חדשות: תזוזה מונעת ידיעה"),
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
        state_dir: str | None = None,
        news_client=None,
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
        self.state_dir = state_dir
        self._news_client = news_client
        self._news_articles: list[dict] = []
        self._last_news_refresh: float = 0.0
        self._intel_rows: list[dict] = []
        self._seen_pos_alerts: set[str] = set()
        self.portfolio = Portfolio(cfg.execution.starting_cash, mode=cfg.execution.mode, store=self.store)
        self.markets: dict[str, Market] = {}
        self._last_marks: dict[str, float] = {}
        self._restore_state()

    def _restore_state(self) -> None:
        """שחזור פוזיציות, מזומן, רווח יומי, שיא, תקופות צינון (cooldown) והתראות עבר מ-SQLite."""
        st = self.store.load_portfolio_state(self.cfg.execution.mode, self.cfg.execution.starting_cash)
        if st["positions"] or st["cash"] != self.cfg.execution.starting_cash or st["realized_pnl"]:
            self.portfolio.restore(st["positions"], st["cash"])
            self.portfolio.realized_pnl = st["realized_pnl"]
            self.portfolio.realized_pnl_today = st["realized_pnl_today"]
            self.portfolio.peak_equity = st["peak_equity"]
            self.risk.update_peak(st["peak_equity"])
            if st["positions"]:
                self._last_marks.update(
                    self.store.latest_marks([p.token_id for p in st["positions"]])
                )
            log.info(
                "♻️  שוחזר תיק: %d פוזיציות פתוחות | מזומן %.2f | שיא %.2f | PnL היום %+.2f",
                len(st["positions"]), st["cash"], st["peak_equity"], st["realized_pnl_today"],
            )

        now = utcnow()
        cd_min = int(self.cfg.risk.cooldown_minutes or 0)
        if cd_min > 0:
            cutoff_ts = int((now - timedelta(minutes=cd_min)).timestamp())
            restored_cd = 0
            for cid, sell_ts in self.store.recent_exits(self.cfg.execution.mode, cutoff_ts).items():
                until = datetime.fromtimestamp(sell_ts, tz=timezone.utc) + timedelta(minutes=cd_min)
                if until > now:
                    self.risk._cooldown_until[cid] = until
                    restored_cd += 1
            if restored_cd:
                log.info("♻️  שוחזרו %d תקופות צינון פעילות מ-fills (%dm)", restored_cd, cd_min)

        alert_cutoff = int((now - timedelta(hours=12)).timestamp())
        for d in self.store.recent_event_data("position_news_alert", alert_cutoff):
            tid = str(d.get("token_id") or "")
            title = str(d.get("title") or "")
            if tid and title:
                self._seen_pos_alerts.add(f"{tid[:12]}:{title[:48]}")

    # ==================================================================
    #  מחזור
    # ==================================================================
    cycle: int = 0
    notifier: Notifier | None = None
    _stop_requested: bool = False

    def request_stop(self) -> None:
        """עצירה נקייה בסיום המחזור הנוכחי (לדוגמה על SIGTERM)."""
        self._stop_requested = True

    def _notify(self, text: str) -> None:
        if self.notifier is None:
            self.notifier = Notifier()
        self.notifier.send(text)

    def _write_heartbeat(self, snap=None, stats: CycleStats | None = None) -> None:
        try:
            if snap is None:
                snap = self.portfolio.snapshot(self._last_marks)
            st = stats or CycleStats()
            write_heartbeat(Heartbeat(
                ts=snap.ts.timestamp(), cycle=self.cycle,
                mode=self.cfg.execution.mode, engine=self.cfg.signal.engine,
                equity=snap.equity, cash=snap.cash, exposure=snap.exposure,
                positions=snap.open_positions,
                scanned=st.scanned, signalled=st.signalled,
                entries=st.entries, exits=st.exits, errors=st.errors,
                halted=self.risk.halted, halt_reason=self.risk.halt_reason or "",
                pid=os.getpid(),
                skipped=dict(st.skipped),
                guards=self._guard_state(snap),
            ), state_dir=self.state_dir)
        except Exception as exc:          # noqa: BLE001 — דופק לא מפיל מחזור
            log.warning("כתיבת דופק נכשלה: %s", exc)

    def run_once(self) -> CycleStats:
        self.cycle += 1
        stats = CycleStats()
        self.portfolio.roll_day_if_needed()
        halt_flag = read_halt(self.state_dir)
        if halt_flag is not None:
            self.risk.halt(f"עצירה חיצונית ({halt_flag.source}): {halt_flag.reason}")
        self._check_global_risk()
        self._write_heartbeat(stats=stats)

        try:
            markets = self.universe.scan()
        except ConnectionError as exc:
            log.error("סריקת היקום נכשלה: %s", exc)
            stats.errors += 1
            self._write_heartbeat(stats=stats)
            return stats

        stats.scanned = len(markets)
        self.markets = {m.condition_id: m for m in markets}
        self._intel_rows = []
        self._refresh_news_if_due(markets)

        prefetched: dict[str, tuple[Book | None, list]] = {}
        if len(markets) >= 8 and type(self.clob) is ClobClient:
            from concurrent.futures import ThreadPoolExecutor

            def _fetch_mkt(mk: Market) -> tuple[str, Book | None, list]:
                try:
                    bk = self.clob.get_book(mk.yes_token_id)
                except Exception:
                    bk = None
                if bk is None:
                    return mk.condition_id, None, []
                try:
                    cs = self.clob.get_history(
                        mk.yes_token_id,
                        fidelity_min=self.cfg.signal.candle_fidelity_min,
                        lookback_candles=self.cfg.signal.lookback_candles,
                    )
                except Exception:
                    cs = []
                return mk.condition_id, bk, cs

            with ThreadPoolExecutor(max_workers=8) as pool:
                for cid, bk, cs in pool.map(_fetch_mkt, markets):
                    prefetched[cid] = (bk, cs)

        pending_entries: list[tuple[Market, Signal, Book, dict]] = []
        for mk in markets:
            try:
                pre_bk, pre_cs = prefetched.get(mk.condition_id, (None, None))
                prep = self._prepare_market(mk, stats, prefetched_book=pre_bk, prefetched_candles=pre_cs)
                if prep is not None:
                    pending_entries.append(prep)
            except Exception as exc:  # לא מפילים את כל המחזור בגלל שוק אחד
                stats.errors += 1
                log.exception("שגיאה בעיבוד %s: %s", mk.slug, exc)

        # --- שלב 1.5: מעקב / סגירה מבוקרת לפוזיציות שיצאו מרשימת היקום (מפנה מקום לפני כניסות) ---
        self._close_orphans(stats)

        # --- שלב 2: כניסות מתועדפות לפי איכות סטאפ (score, edge, מחזור) ---
        pending_entries.sort(
            key=lambda item: (-float(item[1].score), -float(item[1].edge), -float(item[0].volume_24h))
        )
        for mk, signal, yes_book, intel_row in pending_entries:
            try:
                entry_outcome = self._handle_entry(mk, signal, yes_book, stats)
                intel_row["status"] = entry_outcome[0]
                intel_row["reason"] = entry_outcome[1]
            except Exception as exc:
                stats.errors += 1
                log.exception("שגיאה בכניסה ל-%s: %s", mk.slug, exc)

        if self._intel_rows:
            try:
                self.store.upsert_market_intel(self._intel_rows)
            except Exception as exc:      # noqa: BLE001
                log.debug("שמירת market_intel נכשלה: %s", exc)

        # סגירת לולאת הלמידה המקומית על אותות עבר + ניטור חדשות לפוזיציות פתוחות
        try:
            from .learning import evaluate_live_signals

            evaluate_live_signals(self.store)
        except Exception as exc:          # noqa: BLE001
            log.debug("הערכת אותות חיים דולגה: %s", exc)

        try:
            from .autopilot import monitor_open_positions_news

            monitor_open_positions_news(
                list(self.portfolio.positions.values()),
                self._news_articles,
                self.cfg,
                self.store,
                notifier=self.notifier,
                seen_alerts=self._seen_pos_alerts,
            )
        except Exception as exc:          # noqa: BLE001
            log.debug("ניטור פוזיציות מול חדשות דולג: %s", exc)

        marks = self._last_marks
        snap = self.portfolio.snapshot(marks)
        self.risk.update_peak(snap.equity)
        self.store.snapshot_equity(snap, mode=self.cfg.execution.mode)
        log.info(
            "📊 מחזור: נסרקו %d | סיגנלים %d | כניסות %d | יציאות %d | שגיאות %d | "
            "הון %.2f | מזומן %.2f | חשיפה %.2f | פוזיציות %d",
            stats.scanned, stats.signalled, stats.entries, stats.exits, stats.errors,
            snap.equity, snap.cash, snap.exposure, snap.open_positions,
        )
        if stats.skipped:
            log.debug("דחיות: %s", stats.skipped)

        # --- דופק: הקובץ שמאפשר ל-watchdog ולטלפון לדעת שאנחנו חיים ---
        self._write_heartbeat(snap=snap, stats=stats)
        return stats

    def run_forever(self, interval_sec: float = 60.0, max_cycles: int | None = None) -> None:
        import signal as _signal

        self._stop_requested = False
        prev_term = None
        installed = False
        try:
            def _on_sigterm(_signum, _frame):
                log.warning("התקבל SIGTERM — עוצר נקי בסוף המחזור הנוכחי")
                self._stop_requested = True

            prev_term = _signal.getsignal(_signal.SIGTERM)
            _signal.signal(_signal.SIGTERM, _on_sigterm)
            installed = True
        except (ValueError, OSError, AttributeError):
            pass

        cycle = 0
        try:
            while (max_cycles is None or cycle < max_cycles) and not self._stop_requested:
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
                if self._stop_requested:
                    log.info("עצירה נקייה הושלמה בסוף מחזור #%d", cycle)
                    break
                if max_cycles is not None and cycle >= max_cycles:
                    break
                time.sleep(interval_sec)
        finally:
            if installed and prev_term is not None:
                try:
                    _signal.signal(_signal.SIGTERM, prev_term)
                except (ValueError, OSError):
                    pass

    # ==================================================================
    #  שוק בודד (שלב 1: הערכה + יציאות; שלב 2: כניסות מתועדפות)
    # ==================================================================
    def _prepare_market(
        self, mk: Market, stats: CycleStats,
        *,
        prefetched_book: Book | None = None,
        prefetched_candles: list | None = None,
    ) -> tuple[Market, Signal, Book, dict] | None:
        cfg = self.cfg

        # --- ספר הפקודות קודם: הוא נדרש גם לסיגנל וגם לאיסוף הדאטה ---
        yes_book = prefetched_book if prefetched_book is not None else self.clob.get_book(mk.yes_token_id)
        if yes_book is None:
            stats.skip("אין ספר פקודות")
            return None
        if cfg.data.record_books:
            self.store.record_book(mk.yes_token_id, int(utcnow().timestamp()), yes_book)

        market_price = yes_book.mid or mk.yes_price
        if yes_book.mid is not None:
            self._last_marks[mk.yes_token_id] = yes_book.mid
            self._last_marks[mk.no_token_id] = 1.0 - yes_book.mid

        # --- היסטוריה ---
        candles = prefetched_candles if prefetched_candles is not None else self.clob.get_history(
            mk.yes_token_id,
            fidelity_min=cfg.signal.candle_fidelity_min,
            lookback_candles=cfg.signal.lookback_candles,
        )
        if len(candles) < self.signals.min_candles:
            stats.skip("אין מספיק היסטוריה")
            return None

        prices = [c.price for c in candles]
        self.store.insert_ticks([(mk.yes_token_id, c.ts, c.price) for c in candles])

        bid_depth, ask_depth = yes_book.depth(5)
        imb = yes_book.imbalance(5)
        microprice = None
        if yes_book.best_bid and yes_book.best_ask:
            b_sz = float(getattr(yes_book, "bid_size", 0.0) or 0.0) or bid_depth
            a_sz = float(getattr(yes_book, "ask_size", 0.0) or 0.0) or ask_depth
            if b_sz + a_sz > 0:
                microprice = round((yes_book.best_bid * a_sz + yes_book.best_ask * b_sz) / (b_sz + a_sz), 4)

        signal = self.signals.evaluate(
            mk, prices, market_price=market_price, spread=yes_book.spread,
            extra={"fee_rate": mk.taker_fee_rate, "imbalance": imb, "microprice": microprice},
        )
        if signal.direction != "FLAT":
            stats.signalled += 1
        self.store.record_signal(signal)

        # ---------- יציאות קודם ----------
        self._handle_exit(mk, signal, yes_book, stats)

        # ---------- הכנת רשומת מודיעין (תעודכן אם תבוצע כניסה בשלב 2) ----------
        entry_outcome = ("WATCH", signal.reason)
        if signal.direction == "FLAT":
            stats.skip(f"סיגנל: {signal.reason}")
            if any(p.condition_id == mk.condition_id for p in self.portfolio.positions.values()):
                entry_outcome = ("OPEN", "פוזיציה פתוחה במעקב")
        elif any(p.condition_id == mk.condition_id for p in self.portfolio.positions.values()):
            entry_outcome = ("OPEN", "פוזיציה פתוחה במעקב")

        chg_1h = round(prices[-1] - prices[-2], 4) if len(prices) >= 2 else None
        chg_6h = round(prices[-1] - prices[-7], 4) if len(prices) >= 7 else None
        chg_24h = round(prices[-1] - prices[-25], 4) if len(prices) >= 25 else None
        z_val = signal.features.get("z") if signal.features else None
        rsi_val = signal.features.get("rsi") if signal.features else None
        tier_val = (signal.features.get("setup_tier") if signal.features else None) or "B"

        # סימון חכם לשוק שמתבשל לקראת איתות כניסה (WATCH -> NEAR)
        if entry_outcome[0] == "WATCH" and z_val is not None:
            if (-self.cfg.signal.meanrev.z_max <= float(z_val) <= -1.20) and (
                rsi_val is None or float(rsi_val) <= 44.0
            ):
                entry_outcome = ("NEAR", entry_outcome[1])

        n_cnt, n_imp = 0, 0.0
        if self._news_articles:
            from .data.news import match_market_news

            nm_info = match_market_news(
                mk.question, self._news_articles,
                window_hours=max(12.0, cfg.news.spike_window_hours),
                min_articles=1, impact_threshold=0.0,
            )
            n_cnt, n_imp = nm_info.article_count, nm_info.max_impact

        intel_row = {
            "condition_id": mk.condition_id,
            "token_id": mk.yes_token_id,
            "question": mk.question,
            "sector": mk.sector,
            "price": round(float(market_price or 0.0), 4),
            "spread": round(float(yes_book.spread), 4),
            "bid_depth": round(float(bid_depth), 1),
            "ask_depth": round(float(ask_depth), 1),
            "imbalance": round(float(imb), 3) if imb is not None else None,
            "volume_24h": round(float(mk.volume_24h), 1),
            "volume_ratio": float(mk.volume_ratio),
            "chg_1h": chg_1h,
            "chg_6h": chg_6h,
            "chg_24h": chg_24h,
            "z_score": round(float(z_val), 2) if z_val is not None else None,
            "edge_net": round(float(signal.edge), 4),
            "rsi": round(float(rsi_val), 1) if rsi_val is not None else None,
            "setup_tier": str(tier_val),
            "microprice": microprice,
            "news_count": n_cnt,
            "news_impact": n_imp,
            "hours_left": round(mk.hours_to_resolution, 1) if mk.hours_to_resolution != float("inf") else None,
            "status": entry_outcome[0],
            "reason": entry_outcome[1],
            "updated_at": int(utcnow().timestamp()),
        }
        self._intel_rows.append(intel_row)

        if signal.direction == "FLAT":
            return None
        return (mk, signal, yes_book, intel_row)

    def _process_market(self, mk: Market, stats: CycleStats) -> None:
        prep = self._prepare_market(mk, stats)
        if prep is not None:
            mk_i, sig, y_book, intel_row = prep
            entry_outcome = self._handle_entry(mk_i, sig, y_book, stats)
            intel_row["status"] = entry_outcome[0]
            intel_row["reason"] = entry_outcome[1]

    # ------------------------------------------------------------------
    def _handle_entry(self, mk: Market, signal: Signal, yes_book: Book, stats: CycleStats) -> tuple[str, str]:
        # Keep the shared admission check locked through broker execution and DB persistence.
        with unified_entry_lock(self.cfg):
            return self._handle_entry_locked(mk, signal, yes_book, stats)

    def _handle_entry_locked(self, mk: Market, signal: Signal, yes_book: Book, stats: CycleStats) -> tuple[str, str]:
        if any(p.condition_id == mk.condition_id for p in self.portfolio.positions.values()):
            stats.skip("כבר בפוזיציה")
            return ("OPEN", "פוזיציה פתוחה במעקב")

        token_id = signal.token_id
        book = yes_book if signal.direction == "LONG" else self.clob.get_book(token_id)
        if book is None or not book.is_tradable():
            stats.skip("ספר לא סחיר")
            return ("SKIP", "ספר לא סחיר")

        if book.spread > self.cfg.universe.max_spread:
            stats.skip("ספרד חי רחב מדי")
            return ("SKIP", f"ספרד רחב מדי ({book.spread:.3f})")
        price = book.best_ask
        lo, hi = self.cfg.universe.price_band
        if price is None or not (lo <= price <= hi):
            stats.skip("אין ask בתחום")
            return ("SKIP", "מחיר מחוץ לטווח")

        # בדיקת חדשות שווקים + תאוצת נפח חריגה — מניעת קניית "סכין נופלת"
        if self.cfg.news.enabled and self.cfg.news.block_on_catalyst:
            if self._news_articles:
                from .data.news import match_market_news

                nm = match_market_news(
                    mk.question,
                    self._news_articles,
                    window_hours=self.cfg.news.spike_window_hours,
                    min_articles=self.cfg.news.min_spike_articles,
                    impact_threshold=self.cfg.news.spike_impact_threshold,
                )
                if nm.catalyst_detected:
                    stats.skip("חדשות: תזוזה מונעת ידיעה")
                    log.info(
                        "📰 דילוג על %s — זוהה קטליזטור חדשותי (%d כתבות, impact=%.2f): %s",
                        mk.slug, nm.article_count, nm.max_impact, nm.latest_title[:80],
                    )
                    return ("CATALYST_BLOCK", f"קטליזטור חדשותי: {nm.latest_title[:55]}")
            if mk.volume_1wk > 0 and mk.volume_ratio >= self.cfg.news.volume_spike_ratio:
                stats.skip("חדשות: תזוזה מונעת ידיעה")
                log.info(
                    "📰 דילוג על %s — תאוצת נפח חריגה (%.1fx מהממוצע השבועי)",
                    mk.slug, mk.volume_ratio,
                )
                return ("CATALYST_BLOCK", f"זינוק נפח חריג ({mk.volume_ratio:.1f}x מהשבוע)")

        open_events: dict[str, int] = {}
        open_sectors: dict[str, int] = {}
        from .sectors import classify
        for p in self.portfolio.positions.values():
            ev = p.event_id or (self.markets[p.condition_id].event_id if p.condition_id in self.markets else "")
            if ev:
                open_events[ev] = open_events.get(ev, 0) + 1
            sec = (self.markets[p.condition_id].sector if p.condition_id in self.markets
                   else classify(p.question, ""))
            if sec:
                open_sectors[sec] = open_sectors.get(sec, 0) + 1

        snap = self.portfolio.snapshot(self._last_marks)
        decision = self.risk.evaluate_entry(
            signal, mk, snap,
            price=price,
            tick=book.tick_size or mk.tick_size,
            min_order_size=max(book.min_order_size, self.cfg.risk.min_order_size),
            open_events=open_events,
            open_sectors=open_sectors,
        )
        if not decision.approved:
            stats.skip(f"סיכון: {decision.reason}")
            log.debug("⛔ %s | %s", mk.question[:60], decision.reason)
            return ("CANDIDATE", f"נדחה בסיכון: {decision.reason}")

        # Hold a small pre-trade buffer for slippage before capital is committed.
        slippage_buffer = max(
            self.cfg.risk.max_price_impact_pct,
            self.cfg.execution.max_slippage_bps / 10_000.0,
        )
        shared = evaluate_unified_entry(
            self.store, self.cfg, arm="polymarket",
            proposed_capital=decision.notional * (1.0 + slippage_buffer),
        )
        if not shared.approved:
            stats.skip(f"סיכון תיק מאוחד: {shared.reason}")
            log.info("⛔ Shared portfolio guard blocked %s: %s", mk.slug, shared.reason)
            return ("CANDIDATE", f"נדחה בשער תיק מאוחד: {shared.reason}")

        # בדיקת עומק ספר הפקודות לפני שליחת הוראה: מוודאים שהליכת הספר לא בולעת את ה-edge
        est_fn = getattr(self.clob, "estimate_fill", None)
        if callable(est_fn) and book.asks:
            est = est_fn(book, "BUY", decision.notional,
                         max_impact_pct=max(self.cfg.risk.max_price_impact_pct, 0.05),
                         allow_partial=False)
            if est is None:
                stats.skip("ספר פקודות דק או חסר")
                return ("CANDIDATE", "ספר פקודות דק מדי")
            est_px, _ = est
            if est_px - price > self.cfg.risk.max_price_impact_pct * max(price, 0.01):
                stats.skip("ספר פקודות דק או חסר")
                return ("CANDIDATE", "השפעת מחיר גבוהה מדי")
            fees_rt = float(signal.features.get("fees", 0.0))
            if est_px + fees_rt >= signal.fair_price:
                stats.skip("edge לא מכסה עלויות")
                return ("CANDIDATE", "edge אחרי ספרד/עמלה שלילי")

        # בדיקת יתרה חיה בבורסה לפני שליחת הוראה אמיתית (מונע דחיות/עודף סיכון)
        if self.cfg.execution.mode == "live":
            bal_fn = getattr(self.broker, "usdc_balance", None)
            if callable(bal_fn):
                live_usdc = bal_fn()
                if live_usdc is not None and live_usdc < decision.notional * 1.02:
                    stats.skip("יתרת USDC בבורסה אינה מספיקה")
                    return ("CANDIDATE", f"יתרת USDC נמוכה ({live_usdc:.2f} < {decision.notional:.2f})")

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
            return ("CANDIDATE", "מילוי נכשל")

        self.portfolio.apply_fill(fill)
        pos = self.portfolio.position_for(token_id)
        if pos is not None:
            pos.condition_id = mk.condition_id
            pos.direction = signal.direction
            pos.entry_score = signal.score
            pos.question = mk.question
            pos.event_id = mk.event_id
            ex = self.cfg.signal.exit
            pos.stop_price, pos.target_price = stop_and_target(
                fill.price, "LONG", ex.stop_loss, ex.take_profit,
                book.tick_size or mk.tick_size, mode=ex.stop_mode,
            )
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
        return ("BUY", f"בוצעה כניסה @ {fill.price:.3f}")

    def _effective_sell_size(self, token_id: str, size: float) -> float:
        """במצב live מאמת יתרת טוקנים אמיתית כדי למנוע דחיית מכירה על פער עיגול של 0.01."""
        if self.cfg.execution.mode != "live":
            return size
        bal_fn = getattr(self.broker, "conditional_balance", None)
        if not callable(bal_fn):
            return size
        live_bal = bal_fn(token_id)
        if live_bal is None or live_bal >= size:
            return size
        if live_bal < 0.01:
            return 0.0
        return round(min(size, math.floor(live_bal * 100.0) / 100.0), 4)

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
            reason = self.risk.evaluate_exit(pos, mark, signal_flipped=flipped, hours_to_resolution=mk.hours_to_resolution)
            if reason is None and self.cfg.news.enabled and self._news_articles:
                from .data.news import match_market_news

                opened_ts = int(pos.opened_at.timestamp()) if pos.opened_at else 0
                fresh_news = [a for a in self._news_articles if int(a.get("ts") or 0) >= max(0, opened_ts - 1800)]
                if fresh_news:
                    nm_ex = match_market_news(
                        mk.question,
                        fresh_news,
                        window_hours=max(4.0, self.cfg.news.spike_window_hours),
                        min_articles=1,
                        impact_threshold=self.cfg.news.emergency_exit_impact,
                    )
                    if (
                        nm_ex.catalyst_detected
                        and nm_ex.max_impact >= self.cfg.news.emergency_exit_impact
                        and nm_ex.avg_sentiment <= self.cfg.news.emergency_exit_sentiment
                    ):
                        reason = f"הגנת חדשות (impact={nm_ex.max_impact:.2f}): {nm_ex.latest_title[:42]}"
            if reason is None:
                continue

            sell_size = self._effective_sell_size(token_id, pos.size)
            if sell_size <= 0:
                log.warning("יתרת הטוקן בבורסה זניחה עבור %s — מדלג על מכירה", mk.slug)
                continue

            order = Order(
                token_id=token_id,
                side="SELL",
                price=mark,
                size=sell_size,
                fee_rate=mk.taker_fee_rate,
                condition_id=pos.condition_id,
                reason=f"יציאה: {reason}",
            )
            fill = self.broker.execute(order, book=book, aggressive=True)
            if fill is None:
                if pos.size * mark < 1.0:
                    log.warning("שארית זעירה (dust) מתחת למינימום עבור %s (%.2f מניות ≈ %.2f$) — מדלג",
                                mk.slug, pos.size, pos.size * mark)
                else:
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
    def _close_orphans(self, stats: CycleStats | None = None) -> None:
        """
        ניהול פוזיציות שהשוק שלהן יצא מסריקת ה-Top-N / היקום הנוכחי:
          1. אם קיים ספר חי — מעדכנים mark וממשיכים לנטר רגיל לפי כללי TP / SL / Time-Stop / חדשות חירום
             (לעולם לא מחסלים בהפסד רק כי השוק ירד זמנית מה-Top-N).
          2. אם הספר נעלם (404) — בודקים הכרעה/סליקה ב-CLOB.
        """
        if not self.markets:
            return
        for token_id, pos in list(self.portfolio.positions.items()):
            if pos.condition_id in self.markets:
                continue
            orphan_hours: float | None = None
            orphan_closed = False
            orphan_fee_rate = 0.02
            gamma_http = getattr(self.gamma, "http", None)
            if pos.condition_id and gamma_http is not None:
                try:
                    res = gamma_http.get("/markets", params={"condition_ids": pos.condition_id})
                    raw_mk = res[0] if isinstance(res, list) and res else None
                    if isinstance(raw_mk, dict):
                        orphan_closed = bool(raw_mk.get("closed"))
                        parsed = Market.from_gamma(raw_mk)
                        if parsed is not None:
                            orphan_hours = parsed.hours_to_resolution
                            orphan_fee_rate = parsed.taker_fee_rate
                except Exception:  # noqa: BLE001
                    pass

            book = None if orphan_closed else self.clob.get_book(token_id)
            if book is not None and book.best_bid is not None:
                mark = book.best_bid
                self._last_marks[token_id] = mark
                reason = self.risk.evaluate_exit(pos, mark, hours_to_resolution=orphan_hours)
                if reason is None and self.cfg.news.enabled and self._news_articles and pos.question:
                    from .data.news import match_market_news

                    opened_ts = int(pos.opened_at.timestamp()) if pos.opened_at else 0
                    fresh_news = [
                        a for a in self._news_articles
                        if int(a.get("ts") or 0) >= max(0, opened_ts - 1800)
                    ]
                    if fresh_news:
                        nm_ex = match_market_news(
                            pos.question,
                            fresh_news,
                            window_hours=max(4.0, self.cfg.news.spike_window_hours),
                            min_articles=1,
                            impact_threshold=self.cfg.news.emergency_exit_impact,
                        )
                        if (
                            nm_ex.catalyst_detected
                            and nm_ex.max_impact >= self.cfg.news.emergency_exit_impact
                            and nm_ex.avg_sentiment <= self.cfg.news.emergency_exit_sentiment
                        ):
                            reason = f"הגנת חדשות (impact={nm_ex.max_impact:.2f}): {nm_ex.latest_title[:42]}"
                if reason is None:
                    log.debug("👁️  מעקב עצמאי אחרי פוזיציה מחוץ לסריקה %s @ %.3f (TP=%.3f SL=%.3f)",
                              (pos.question or token_id)[:32], mark, pos.target_price or 0, pos.stop_price or 0)
                    continue

                sell_size = self._effective_sell_size(token_id, pos.size)
                if sell_size <= 0:
                    continue

                order = Order(
                    token_id=token_id, side="SELL", price=mark, size=sell_size,
                    fee_rate=orphan_fee_rate,
                    condition_id=pos.condition_id, reason=f"יציאה: {reason}",
                )
                fill = self.broker.execute(order, book=book, aggressive=True)
                if fill:
                    realized = self.portfolio.apply_fill(fill)
                    self.risk.start_cooldown(pos.condition_id)
                    if stats is not None:
                        stats.exits += 1
                    log.info("🚪 יציאה (מעקב עצמאי) %s | %s | %+.2f",
                             (pos.question or token_id)[:36], reason, realized)
                    self._notify(fmt_exit(self.cfg.execution.mode, pos.question or token_id[:14],
                                          fill.price, realized, reason))
                    self.store.event("exit", f"{pos.question or token_id[:14]} — {reason}",
                                     data={"price": fill.price, "size": fill.size, "realized": realized})
                continue

            # ספר הפקודות נעלם (404) — בודקים אם השוק כבר הוכרע
            resolver = getattr(self.clob, "get_resolution", None)
            res_px = resolver(pos.condition_id, token_id) if callable(resolver) else None
            if res_px is None:
                continue
            if self.cfg.execution.mode == "live" and res_px > 0:
                log.warning("🏆 פוזיציה %s זכתה (%.2f) — נדרש redeem on-chain ב-Polymarket",
                            pos.question or token_id[:12], res_px)
                self._notify(f"🏆 פוזיציה הוכרעה כזוכה — יש לבצע Redeem: {pos.question[:60]}")
                continue
            fill = Fill(
                token_id=token_id, condition_id=pos.condition_id, side="SELL",
                price=res_px, size=pos.size, fee=0.0, ts=utcnow(), order_id="settlement",
            )
            fill.reason = "סליקה: השוק הוכרע"  # type: ignore[attr-defined]
            realized = self.portfolio.apply_fill(fill)
            log.info("🏁 סליקת שוק מוכרע %s @ %.2f | %+.2f",
                     (pos.question or token_id)[:40], res_px, realized)
            self._notify(fmt_exit(self.cfg.execution.mode, pos.question or token_id[:14],
                                  res_px, realized, "השוק הוכרע"))
            self.store.event("settlement", f"{pos.question or token_id[:14]}",
                             data={"price": res_px, "size": pos.size, "realized": realized})

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

    def _refresh_news_if_due(self, markets: list[Market]) -> None:
        if not self.cfg.news.enabled:
            return
        now = time.time()
        allow_live = self._news_client is not None or os.getenv("PMMB_DISABLE_LIVE_NEWS") != "1"
        due = (now - self._last_news_refresh) >= self.cfg.news.refresh_interval_sec
        if allow_live and due:
            try:
                from .data.news import refresh_news_to_store

                # עדיפות לשאילתות על פוזיציות פתוחות ושווקים בעלי מחזור גבוה
                open_cids = {p.condition_id for p in self.portfolio.positions.values()}
                ordered = sorted(
                    markets,
                    key=lambda m: (0 if m.condition_id in open_cids else 1, -m.volume_24h),
                )
                refresh_news_to_store(
                    self.store,
                    markets=ordered,
                    news_client=self._news_client,
                    max_market_queries=self.cfg.news.max_market_queries,
                )
                self._last_news_refresh = now
            except Exception as exc:      # noqa: BLE001
                log.warning("רענון חדשות נכשל: %s", exc)
        try:
            self._news_articles = [
                dict(r) for r in self.store.recent_news(hours=max(12.0, self.cfg.news.spike_window_hours * 2), limit=120)
            ]
        except Exception:
            self._news_articles = []

    def close_position_by_token(self, token_id: str, reason: str = "סגירה ידנית מהטרמינל") -> dict:
        """סוגר פוזיציית Polymarket פתוחה לפי token_id (או prefix) במחיר השוק."""
        resolved_tid = (
            token_id
            if token_id in self.portfolio.positions
            else next((tid for tid in self.portfolio.positions if tid.startswith(token_id)), "")
        )
        pos = self.portfolio.positions.get(resolved_tid)
        if pos is None:
            raise KeyError(f"אין פוזיציה פתוחה עבור {token_id}")
        token_id = resolved_tid
        book = self.clob.get_book(token_id)
        mark = (
            book.best_bid
            if (book is not None and book.best_bid is not None)
            else self._last_marks.get(token_id, pos.avg_price)
        )
        sell_size = self._effective_sell_size(token_id, pos.size)
        if sell_size <= 0:
            raise RuntimeError(f"כמות סגירה אפס עבור {token_id}")
        order = Order(
            token_id=token_id,
            side="SELL",
            price=float(mark),
            size=sell_size,
            fee_rate=0.02,
            condition_id=pos.condition_id,
            reason=f"יציאה: {reason}",
        )
        fill = self.broker.execute(order, book=book, aggressive=True)
        if fill is None:
            if book is None or book.best_bid is None:
                from .models import Fill as _Fill
                fill = _Fill(
                    token_id=token_id,
                    condition_id=pos.condition_id,
                    side="SELL",
                    price=float(mark),
                    size=sell_size,
                    fee=round(sell_size * float(mark) * 0.002, 4),
                    ts=utcnow(),
                    order_id="manual-close",
                )
                fill.reason = f"יציאה: {reason}"  # type: ignore[attr-defined]
            else:
                raise RuntimeError(f"סגירה נדחתה בברוקר עבור {token_id}")
        realized = self.portfolio.apply_fill(fill)
        self.risk.start_cooldown(pos.condition_id)
        label = (pos.question or token_id)[:48]
        self._notify(fmt_exit(self.cfg.execution.mode, label, fill.price, realized, reason))
        self.store.event(
            "exit",
            f"סגירה ידנית: {label} — {reason}",
            data={"price": fill.price, "size": fill.size, "realized": realized, "manual": True},
        )
        return {
            "arm": "polymarket",
            "key": token_id,
            "label": label,
            "price": round(fill.price, 4),
            "size": round(fill.size, 2),
            "realized": round(realized, 2),
        }

    def update_position_levels(
        self,
        token_id: str,
        *,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> dict:
        """מעדכן Stop-Loss / Take-Profit של פוזיציית Polymarket פתוחה."""
        resolved_tid = (
            token_id
            if token_id in self.portfolio.positions
            else next((tid for tid in self.portfolio.positions if tid.startswith(token_id)), "")
        )
        pos = self.portfolio.positions.get(resolved_tid)
        if pos is None:
            raise KeyError(f"אין פוזיציה פתוחה עבור {token_id}")
        if stop_price is not None:
            sp = float(stop_price)
            if not (0.01 <= sp <= 0.99):
                raise ValueError("Stop Loss ב-Polymarket חייב להיות בין 0.01 ל-0.99")
            pos.stop_price = round(sp, 4)
        if target_price is not None:
            tp = float(target_price)
            if not (0.01 <= tp <= 0.99):
                raise ValueError("יעד רווח ב-Polymarket חייב להיות בין 0.01 ל-0.99")
            pos.target_price = round(tp, 4)
        self.store.upsert_position(pos, self.cfg.execution.mode)
        self.store.event("position_update", f"עדכון SL/TP {(pos.question or resolved_tid)[:36]}")
        return {
            "token_id": resolved_tid,
            "stop_price": pos.stop_price,
            "target_price": pos.target_price,
        }

    def close_all_positions(self, reason: str = "סגירת כל הפוזיציות מהטרמינל") -> list[dict]:
        """סוגר את כל פוזיציות ה-Polymarket הפתוחות."""
        closed: list[dict] = []
        for tid in list(self.portfolio.positions.keys()):
            closed.append(self.close_position_by_token(tid, reason=reason))
        return closed

    def close(self) -> None:
        self.store.close()
