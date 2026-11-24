"""
שרת התוכנה והדשבורד — PMMB Command Center + שידור חי + JSON/Control API.

בכוונה בספרייה הסטנדרטית: אפס תלויות חיצוניות, עולה בכל מקום.
פעולות מסחר דרך ה-UI מוגבלות למצב `paper` בלבד (הגנה מפני מסחר live מדפדפן).
"""
from __future__ import annotations

import copy
import hmac
import ipaddress
import json
import logging
import os
import re
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import yaml

from .backup import backup_db
from .data.clob import ClobClient
from .data.gamma import GammaClient, MarketUniverse
from .data.http import HttpClient
from .data.news import match_market_news, refresh_news_to_store
from .data.store import Store
from .learning import _apply as _apply_learned_cfg, evaluate_live_signals, run_self_learning_cycle
from .reconcile import reconcile_paper, reconcile_perps
from .runtime import (
    ProcessLock,
    ProcessLockError,
    check_health,
    clear_halt,
    write_halt,
)
from .status import (
    build_chart_series,
    build_command_center_data,
    build_performance_analytics,
    build_perps_chart_series,
    build_status,
    status_html,
)
from .ui import command_center_html

log = logging.getLogger(__name__)


def _is_loopback_address(address: str) -> bool:
    """Return True only for an explicit loopback address; unknown hostnames fail closed."""
    candidate = str(address or "").strip()
    if "%" in candidate:  # IPv6 zone identifier
        candidate = candidate.split("%", 1)[0]
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    mapped = getattr(parsed, "ipv4_mapped", None)
    return mapped.is_loopback if mapped is not None else parsed.is_loopback


def token_ok(given: str, token: str) -> bool:
    """Constant-time token comparison; an empty configured token never authorizes."""
    return bool(token) and hmac.compare_digest(str(given or ""), str(token))


def _redact_token_from_log(message: str) -> str:
    """Redact query-string dashboard tokens before HTTP request lines reach logs."""
    return re.sub(r"(?i)([?&]token=)[^&\\s]*", r"\\1[REDACTED]", str(message))


class _TraderManager:
    """
    מנהל שידור חי ולולאה רציפה ("בלי הפסקה") מתוך התוכנה:
      - הזרמת גרפים וטיקים בזמן אמת (כל 60 שנ')
      - פיד חדשות שווקים חיות (כל news.refresh_interval_sec)
      - מחזור מסחר Mean-Reversion ב-paper בלבד (כל interval_sec)
      - מחזור למידה עצמית ושיפור Walk-Forward (כל learning.interval_sec)
    """

    def __init__(self, cfg, *, config_path: str | None = None) -> None:
        self.cfg = cfg
        self.config_path = Path(config_path) if config_path else Path("config/config.yaml")
        self._lock = threading.Lock()
        self._learn_lock = threading.Lock()
        self._perps_lock = threading.Lock()
        self._perps_learn_lock = threading.Lock()
        self._stop_ev = threading.Event()
        self._thread: threading.Thread | None = None
        self._learn_thread: threading.Thread | None = None
        self._perps_learn_thread: threading.Thread | None = None
        self.cycles = 0
        self.stream_ticks = 0
        self.news_fetches = 0
        self.learn_cycles = 0
        self.last_news_ts = 0
        self.last_stream_ts = 0
        self.last_learn_ts = 0
        self.last_reconcile_ts = 0
        self.last_backup_ts = 0
        self.last_reports_ts = 0
        self.last_error = ""
        self.started_at = int(time.time())
        self.perps_cycles = 0
        self.perps_last_ts = 0
        self.perps_last_learn_ts = 0
        self.perps_learn_cycles = 0
        self.housekeeping_cycles = 0
        self.last_housekeeping_ts = 0
        self.auto_recoveries = 0
        self.perps_last_error = ""
        self._seen_pos_alerts: set[str] = set()
        self.interval_sec = float(cfg.autopilot.trade_interval_sec)
        self.stream_interval_sec = float(cfg.autopilot.stream_interval_sec)
        self._state_lock = threading.Lock()
        self._state_cache: tuple[float, dict] | None = None
        self._perps_exchange = None

    def _get_perps_exchange(self):
        if self._perps_exchange is None:
            from .perps.exchange import MultiPerpExchange
            self._perps_exchange = MultiPerpExchange(self.cfg.perps.exchange)
        return self._perps_exchange

    def invalidate_cache(self) -> None:
        with self._state_lock:
            self._state_cache = None

    def get_state_snapshot(self, *, max_age_sec: float = 300.0, force: bool = False) -> dict:
        now = time.monotonic()
        with self._state_lock:
            if not force and self._state_cache is not None and (now - self._state_cache[0]) < 2.5:
                return self._state_cache[1]
        data = build_command_center_data(cfg=self.cfg, max_age_sec=max_age_sec, trader_state=self.state())
        with self._state_lock:
            self._state_cache = (time.monotonic(), data)
        return data

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def state(self) -> dict:
        return {
            "running": self.running,
            "uptime_sec": max(0, int(time.time()) - self.started_at),
            "cycles": self.cycles,
            "stream_ticks": self.stream_ticks,
            "news_fetches": self.news_fetches,
            "learn_cycles": self.learn_cycles,
            "perps_learn_cycles": self.perps_learn_cycles,
            "housekeeping_cycles": self.housekeeping_cycles,
            "auto_recoveries": self.auto_recoveries,
            "last_news_ts": self.last_news_ts,
            "last_stream_ts": self.last_stream_ts,
            "last_learn_ts": self.last_learn_ts,
            "last_reconcile_ts": self.last_reconcile_ts,
            "last_backup_ts": self.last_backup_ts,
            "last_reports_ts": self.last_reports_ts,
            "last_housekeeping_ts": self.last_housekeeping_ts,
            "last_error": self.last_error,
            "perps_enabled": bool(self.cfg.perps.enabled),
            "perps_cycles": self.perps_cycles,
            "perps_last_ts": self.perps_last_ts,
            "perps_last_learn_ts": self.perps_last_learn_ts,
            "perps_last_error": self.perps_last_error,
            "interval_sec": self.interval_sec,
        }

    def _build_clients(self, *, fast: bool = False) -> tuple[GammaClient, ClobClient]:
        d = self.cfg.data
        timeout = min(d.http_timeout, 8.0) if fast else d.http_timeout
        retries = 1 if fast else d.max_retries
        clob = ClobClient(
            HttpClient(d.clob_base_url, timeout, retries, d.rate_limit_rps),
            history_ttl=min(d.history_cache_ttl_sec, 60.0),
        )
        gamma = GammaClient(
            HttpClient(d.gamma_base_url, timeout, retries, d.rate_limit_rps),
        )
        return gamma, clob

    def refresh_news_and_stream(self, *, include_markets: bool = True, force_news: bool | None = None) -> dict:
        """מושך חדשות חיות (בכפוף למרווח הרענון) וטיקים/ספרי גרפים של פוזיציות פתוחות ומועמדים."""
        allow_net = os.getenv("PMMB_DISABLE_LIVE_NEWS") != "1"
        if force_news is None:
            force_news = include_markets
        store = Store(self.cfg.data.db_path)
        n_articles = 0
        n_stream = 0
        try:
            markets = []
            gamma, clob = self._build_clients(fast=True)
            if allow_net and include_markets:
                try:
                    markets = MarketUniverse(gamma, self.cfg.universe).scan()[:30]
                except Exception as exc:
                    log.debug("סריקת שווקים לרענון חדשות נכשלה: %s", exc)

            news_due = force_news or (time.time() - float(self.last_news_ts)) >= self.cfg.news.refresh_interval_sec
            if allow_net and self.cfg.news.enabled and news_due:
                arts = refresh_news_to_store(
                    store,
                    markets=markets,
                    max_market_queries=self.cfg.news.max_market_queries,
                )
                n_articles = len(arts)
                self.news_fetches += 1
                self.last_news_ts = int(time.time())

            if allow_net:
                # הזרמת ספר + טיק חי לפוזיציות פתוחות ולטוקנים המובילים
                cands = store.chart_candidates(self.cfg.execution.mode, limit=10)
                tids = [c["token_id"] for c in cands]
                if not tids and markets:
                    tids = [m.yes_token_id for m in markets[:8]]
                now_ts = int(time.time())
                tick_rows: list[tuple[str, int, float]] = []
                for tid in tids[:10]:
                    try:
                        bk = clob.get_book(tid)
                        if bk is not None:
                            store.record_book(tid, now_ts, bk)
                            px = bk.mid or bk.best_bid
                            if px is not None:
                                tick_rows.append((tid, now_ts, float(px)))
                        candles = clob.get_history(tid, fidelity_min=60, lookback_candles=72, use_cache=True)
                        if candles:
                            tick_rows.extend((tid, c.ts, c.price) for c in candles[-48:])
                        n_stream += 1
                    except Exception:
                        continue
                if tick_rows:
                    store.insert_ticks(tick_rows)
                self.stream_ticks += n_stream
                self.last_stream_ts = now_ts
        finally:
            store.close()

        # ניטור מהיר (בין מחזורים) של פוזיציות PERPS פתוחות מול SL/TP/Trailing בזמן אמת
        if allow_net and self.cfg.perps.enabled and self.cfg.perps.mode == "paper":
            try:
                from .perps.engine import PerpEngine
                with self._perps_lock:
                    peng = PerpEngine(self.cfg, exchange=self._get_perps_exchange())
                    try:
                        if peng.positions:
                            peng.monitor_open_positions()
                    finally:
                        peng.close()
            except Exception as exc:
                log.debug("ניטור מהיר ל-PERPS בשידור: %s", exc)

        return {
            "message": f"רענון שידור חי: {n_articles} כתבות חדשות | {n_stream} גרפים וספרים",
            "output": f"כתבות: {n_articles} | טוקנים שהוזרמו: {n_stream}",
            "articles": n_articles,
            "streamed": n_stream,
        }

    def run_learning_now(self, *, apply_changes: bool = True) -> dict:
        """מריץ הערכת אותות + Walk-Forward + קידום פרמטרים מבוקר."""
        allow_net = os.getenv("PMMB_DISABLE_LIVE_NEWS") != "1"
        with self._learn_lock:
            store = Store(self.cfg.data.db_path)
            try:
                gamma, clob = self._build_clients(fast=True)
                cfg_copy = copy.deepcopy(self.cfg)
                rep = run_self_learning_cycle(
                    cfg_copy,
                    store,
                    gamma=gamma if allow_net else None,
                    clob=clob if allow_net else None,
                    apply_changes=apply_changes,
                )
                if rep.applied and rep.candidate_cfg:
                    with self._lock:
                        _apply_learned_cfg(self.cfg, rep.candidate_cfg)
                self.learn_cycles += 1
                self.last_learn_ts = rep.ts
                return {
                    "message": rep.summary,
                    "output": json.dumps(rep.as_dict(), ensure_ascii=False, indent=2),
                    "report": rep.as_dict(),
                }
            finally:
                store.close()

    def _trigger_learning_bg(self) -> None:
        """מריץ את הלמידה העצמית בחוט רקע נפרד כדי שלא יחסום את לולאת המסחר והדופק."""
        if self._learn_thread is not None and self._learn_thread.is_alive():
            return

        def _bg() -> None:
            try:
                self.run_learning_now(apply_changes=True)
            except Exception as exc:  # noqa: BLE001
                log.warning("למידה עצמית ברקע נכשלה: %s", exc)

        self._learn_thread = threading.Thread(target=_bg, daemon=True, name="pmmb-learn-bg")
        self._learn_thread.start()

    def run_single_cycle(self) -> dict:
        if self.cfg.execution.mode != "paper":
            raise PermissionError("הרצה מהממשק מותרת במצב paper בלבד")
        with self._lock:
            from .engine import Engine

            try:
                plock = ProcessLock("pmmb-paper").acquire()
            except ProcessLockError as exc:
                raise RuntimeError(str(exc)) from exc
            eng = Engine(self.cfg)
            eng.cycle = self.cycles
            prev_news_ts = float(self.last_news_ts)
            eng._last_news_refresh = prev_news_ts
            eng._seen_pos_alerts.update(self._seen_pos_alerts)
            try:
                st = eng.run_once()
                self.cycles += 1
                self.last_error = ""
                if eng._last_news_refresh > prev_news_ts:
                    self.last_news_ts = int(eng._last_news_refresh)
                self._seen_pos_alerts.update(eng._seen_pos_alerts)
                self.last_stream_ts = int(time.time())
                snap = eng.portfolio.snapshot(eng._last_marks)
                return {
                    "message": f"מחזור הסתיים: כניסות {st.entries}, יציאות {st.exits}, הון {snap.equity:.2f}",
                    "output": (
                        f"נסרקו {st.scanned} שווקים | סיגנלים {st.signalled} | "
                        f"כניסות {st.entries} | יציאות {st.exits} | שגיאות {st.errors}\n"
                        f"הון {snap.equity:.2f} | מזומן {snap.cash:.2f} | חשיפה {snap.exposure:.2f} | "
                        f"פוזיציות {snap.open_positions}"
                    ),
                }
            finally:
                eng.close()
                plock.release()

    def run_perps_cycle(self) -> dict:
        if self.cfg.perps.mode != "paper":
            raise PermissionError("הרצת Perps מהממשק מותרת במצב paper בלבד")
        with self._perps_lock:
            from .perps.engine import PerpEngine

            try:
                plock = ProcessLock("pmmb-perps-paper").acquire()
            except ProcessLockError as exc:
                raise RuntimeError(str(exc)) from exc
            eng = PerpEngine(self.cfg, exchange=self._get_perps_exchange())
            try:
                st = eng.run_once()
                self.perps_cycles += 1
                self.perps_last_ts = int(time.time())
                self.perps_last_error = ""
                eq = eng._equity()
                used_m = sum(p.margin_used for p in eng.positions.values())
                return {
                    "message": f"מחזור PERPS הסתיים: כניסות {st.entries}, יציאות {st.exits}, הון {eq:.2f}",
                    "output": (
                        f"נסרקו {st.scanned} חוזים | סיגנלים {st.signalled} | "
                        f"כניסות {st.entries} | יציאות {st.exits} | שגיאות {st.errors}\n"
                        f"הון {eq:.2f} | מרג'ין {used_m:.2f} | פוזיציות {len(eng.positions)}"
                    ),
                }
            except Exception as exc:
                self.perps_last_error = str(exc)
                raise
            finally:
                eng.close()
                plock.release()

    def run_perps_learning_now(self, *, apply_changes: bool = True) -> dict:
        from .perps.learning import run_perp_self_learning_cycle

        with self._perps_learn_lock:
            store = Store(self.cfg.data.db_path)
            try:
                cfg_copy = copy.deepcopy(self.cfg)
                rep = run_perp_self_learning_cycle(
                    cfg_copy, store, apply_changes=apply_changes, config_path=self.config_path
                )
                self.perps_learn_cycles += 1
                if rep.applied:
                    with self._perps_lock:
                        for k in ("z_entry", "adx_trend_threshold"):
                            if k in rep.candidate_cfg:
                                setattr(self.cfg.perps.signal, k, float(rep.candidate_cfg[k]))
                        for k in ("sl_atr_mult", "tp_atr_mult", "trailing_trigger_atr", "trailing_dist_atr"):
                            if k in rep.candidate_cfg:
                                setattr(self.cfg.perps.risk, k, float(rep.candidate_cfg[k]))
                self.perps_last_learn_ts = rep.ts
                return {
                    "message": rep.summary,
                    "output": json.dumps(rep.candidate_cfg, ensure_ascii=False, indent=2),
                }
            finally:
                store.close()

    def evolve_and_maintain_now(self) -> dict:
        """
        הרצת אבולוציה ותחזוקה אוטונומית מלאה בלחיצה אחת:
          1. תחזוקת DB (PRAGMA optimize, WAL checkpoint, אימות פוזיציות, דוחות).
          2. גיבוי חם.
          3. למידת מכונה לשתי הזרועות (Polymarket + PERPS ×50) אם במצב paper.
        """
        from .autopilot import run_auto_backup, run_autonomous_housekeeping

        if self.cfg.execution.mode != "paper":
            raise PermissionError("אבולוציה אוטונומית מהממשק מותרת במצב paper בלבד")

        results: dict[str, str] = {}
        store = Store(self.cfg.data.db_path)
        try:
            with self._lock:
                hk = run_autonomous_housekeeping(self.cfg, store)
            self.housekeeping_cycles += 1
            self.last_housekeeping_ts = int(time.time())
            self.last_reconcile_ts = self.last_housekeeping_ts
            self.last_reports_ts = self.last_housekeeping_ts
            results["housekeeping"] = hk["summary"]

            bk = run_auto_backup(self.cfg, store)
            self.last_backup_ts = int(time.time())
            results["backup"] = bk["summary"]
        finally:
            store.close()

        if self.cfg.perps.enabled and self.cfg.perps.mode == "paper":
            pl = self.run_perps_learning_now(apply_changes=True)
            results["perps_learning"] = pl.get("message", "")
        pl_poly = self.run_learning_now(apply_changes=True)
        results["poly_learning"] = pl_poly.get("message", "")
        self.invalidate_cache()
        return {
            "message": " | ".join(v for v in results.values() if v),
            "results": results,
        }

    def close_position(self, arm: str, key: str, reason: str = "סגירה ידנית מהטרמינל") -> dict:
        """סוגר פוזיציה פתוחה ידנית ב-Polymarket או ב-PERPS (במצב paper בלבד מהדפדפן)."""
        arm_l = (arm or "").strip().lower()
        key_s = (key or "").strip()
        if not key_s:
            raise ValueError("חסר מזהה פוזיציה (key)")

        if arm_l == "perps":
            if self.cfg.perps.mode != "paper":
                raise PermissionError("סגירה ידנית של PERPS מהממשק מותרת במצב paper בלבד")
            with self._perps_lock:
                from .perps.engine import PerpEngine

                eng = PerpEngine(self.cfg)
                try:
                    info = eng.close_position_by_symbol(key_s, reason=reason)
                    return {
                        "message": f"נסגרה פוזיציה {info['label']} @ {info['price']} (נטו {info['realized']:+.2f} USDC)",
                        "output": json.dumps(info, ensure_ascii=False, indent=2),
                        "closed": info,
                    }
                finally:
                    eng.close()

        if arm_l in ("poly", "polymarket"):
            if self.cfg.execution.mode != "paper":
                raise PermissionError("סגירה ידנית של Polymarket מהממשק מותרת במצב paper בלבד")
            with self._lock:
                from .engine import Engine

                eng = Engine(self.cfg)
                try:
                    info = eng.close_position_by_token(key_s, reason=reason)
                    return {
                        "message": f"נסגרה פוזיציה {info['label']} @ {info['price']:.4f} (נטו {info['realized']:+.2f} USDC)",
                        "output": json.dumps(info, ensure_ascii=False, indent=2),
                        "closed": info,
                    }
                finally:
                    eng.close()

        raise ValueError(f"זרוע לא מוכרת: {arm}")

    def open_perps_order(self, symbol: str, side: str, margin: float, leverage: float) -> dict:
        if self.cfg.perps.mode != "paper":
            raise PermissionError("פקודה ידנית מותרת במצב paper בלבד")
        with self._perps_lock:
            from .perps.engine import PerpEngine

            eng = PerpEngine(self.cfg, exchange=self._get_perps_exchange())
            try:
                res = eng.open_manual_order(symbol, side, margin, leverage)
                return {
                    "message": f"נפתחה עסקה ידנית {res['symbol']} {res['side']} ×{res['leverage']:.1f} @ {res['price']}",
                    "order": res,
                }
            finally:
                eng.close()

    def update_position_levels(
        self, arm: str, key: str, *, stop_price: float | None = None, target_price: float | None = None
    ) -> dict:
        arm_l = (arm or "").strip().lower()
        key_s = (key or "").strip()
        if not key_s:
            raise ValueError("חסר מזהה פוזיציה (key)")
        if arm_l == "perps":
            if self.cfg.perps.mode != "paper":
                raise PermissionError("עדכון ידני של PERPS מותר במצב paper בלבד")
            with self._perps_lock:
                from .perps.engine import PerpEngine

                eng = PerpEngine(self.cfg, exchange=self._get_perps_exchange())
                try:
                    info = eng.update_position_levels(key_s, stop_price=stop_price, target_price=target_price)
                    return {"message": f"עודכנו רמות {info['symbol']}: SL={info['stop_price']} | TP={info['target_price']}", "updated": info}
                finally:
                    eng.close()
        if arm_l in ("poly", "polymarket"):
            if self.cfg.execution.mode != "paper":
                raise PermissionError("עדכון ידני של Polymarket מותר במצב paper בלבד")
            with self._lock:
                from .engine import Engine

                eng = Engine(self.cfg)
                try:
                    info = eng.update_position_levels(key_s, stop_price=stop_price, target_price=target_price)
                    return {"message": f"עודכנו רמות Polymarket: SL={info['stop_price']} | TP={info['target_price']}", "updated": info}
                finally:
                    eng.close()
        raise ValueError(f"זרוע לא מוכרת: {arm}")

    def close_all_positions(self, arm: str = "all", reason: str = "סגירת כל הפוזיציות מהטרמינל") -> dict:
        arm_l = (arm or "all").strip().lower()
        closed: list[dict] = []
        if arm_l in ("all", "perps") and self.cfg.perps.mode == "paper":
            with self._perps_lock:
                from .perps.engine import PerpEngine

                eng = PerpEngine(self.cfg, exchange=self._get_perps_exchange())
                try:
                    closed.extend(eng.close_all_positions(reason=reason))
                finally:
                    eng.close()
        if arm_l in ("all", "poly", "polymarket") and self.cfg.execution.mode == "paper":
            with self._lock:
                from .engine import Engine

                eng = Engine(self.cfg)
                try:
                    closed.extend(eng.close_all_positions(reason=reason))
                finally:
                    eng.close()
        return {"message": f"נסגרו {len(closed)} פוזיציות פתוחות", "closed": closed}

    def update_config_params(self, body: dict) -> dict:
        """עדכון פרמטרי סיכון ותדירות חיים (גם בזיכרון וגם ב-config/config.yaml)."""
        from pathlib import Path
        import yaml

        updated: list[str] = []
        with self._perps_lock:
            pr = self.cfg.perps.risk
            if "perps_enabled" in body:
                self.cfg.perps.enabled = bool(body["perps_enabled"])
                updated.append(f"perps.enabled={self.cfg.perps.enabled}")
            if "perps_risk_pct" in body:
                pr.risk_per_trade_pct = max(0.005, min(0.05, float(body["perps_risk_pct"])))
                updated.append(f"perps.risk={pr.risk_per_trade_pct*100:.1f}%")
            if "perps_max_lev" in body:
                pr.max_leverage = max(2.0, min(50.0, float(body["perps_max_lev"])))
                updated.append(f"perps.lev=×{pr.max_leverage:.0f}")
            if "perps_max_pos" in body:
                pr.max_open_positions = max(1, min(8, int(body["perps_max_pos"])))
                updated.append(f"perps.pos={pr.max_open_positions}")
            if "perps_interval_sec" in body:
                self.cfg.perps.interval_sec = max(30.0, min(600.0, float(body["perps_interval_sec"])))
                updated.append(f"perps.interval={self.cfg.perps.interval_sec:.0f}s")
        with self._lock:
            rr = self.cfg.risk
            if "poly_risk_pct" in body:
                rr.risk_per_trade_pct = max(0.005, min(0.05, float(body["poly_risk_pct"])))
                updated.append(f"poly.risk={rr.risk_per_trade_pct*100:.1f}%")
            if "poly_max_pos" in body:
                rr.max_open_positions = max(1, min(12, int(body["poly_max_pos"])))
                updated.append(f"poly.pos={rr.max_open_positions}")
            if "trade_interval_sec" in body:
                self.interval_sec = max(45.0, min(600.0, float(body["trade_interval_sec"])))
                self.cfg.autopilot.trade_interval_sec = int(self.interval_sec)
                updated.append(f"poly.interval={self.interval_sec:.0f}s")

        cfg_path = self.config_path
        if cfg_path.exists():
            try:
                raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                raw.setdefault("perps", {}).setdefault("risk", {})
                raw["perps"]["enabled"] = bool(self.cfg.perps.enabled)
                raw["perps"]["interval_sec"] = float(self.cfg.perps.interval_sec)
                raw["perps"]["risk"]["risk_per_trade_pct"] = round(self.cfg.perps.risk.risk_per_trade_pct, 4)
                raw["perps"]["risk"]["max_leverage"] = float(self.cfg.perps.risk.max_leverage)
                raw["perps"]["risk"]["max_open_positions"] = int(self.cfg.perps.risk.max_open_positions)
                raw.setdefault("risk", {})
                raw["risk"]["risk_per_trade_pct"] = round(self.cfg.risk.risk_per_trade_pct, 4)
                raw["risk"]["max_open_positions"] = int(self.cfg.risk.max_open_positions)
                raw.setdefault("autopilot", {})
                raw["autopilot"]["trade_interval_sec"] = int(self.cfg.autopilot.trade_interval_sec)
                cfg_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
            except Exception as exc:
                log.warning("שמירת config.yaml נכשלה: %s", exc)

        return {
            "message": "הגדרות עודכנו ונשמרו: " + (" · ".join(updated) if updated else "ללא שינוי"),
            "updated": updated,
        }

    def _trigger_perps_learning_bg(self) -> None:
        if self._perps_learn_thread is not None and self._perps_learn_thread.is_alive():
            return

        def _bg() -> None:
            try:
                self.run_perps_learning_now(apply_changes=True)
            except Exception as exc:  # noqa: BLE001
                log.warning("למידת Perps ברקע נכשלה: %s", exc)

        self._perps_learn_thread = threading.Thread(target=_bg, daemon=True, name="pmmb-perps-learn-bg")
        self._perps_learn_thread.start()

    def run_maintenance_now(self, *, force_backup: bool = True, force_reports: bool = True) -> dict:
        """מריץ חבילת תחזוקה מלאה של הטייס האוטומטי: אימות/תיקון DB, גיבוי חם ודוחות יומיים."""
        from .autopilot import run_auto_backup, run_auto_reconcile, run_auto_reports

        store = Store(self.cfg.data.db_path)
        results: dict[str, str] = {}
        try:
            with self._lock:
                rec = run_auto_reconcile(self.cfg, store)
            self.last_reconcile_ts = int(time.time())
            results["reconcile"] = rec["summary"]
            if force_backup:
                bk = run_auto_backup(self.cfg, store)
                self.last_backup_ts = int(time.time())
                results["backup"] = bk["summary"]
            if force_reports:
                rp = run_auto_reports(self.cfg, store)
                self.last_reports_ts = int(time.time())
                results["reports"] = rp["summary"]
        finally:
            store.close()
        return {
            "message": " | ".join(results.values()),
            "output": json.dumps(results, ensure_ascii=False, indent=2),
            **results,
        }

    def start(self, interval_sec: float = 180.0) -> dict:
        if self.cfg.execution.mode != "paper":
            raise PermissionError("סוחר אוטומטי מהממשק מותר במצב paper בלבד")
        if self.running:
            return {"message": "המערכת הרציפה כבר פועלת", **self.state()}
        self.interval_sec = max(30.0, float(interval_sec or self.cfg.autopilot.trade_interval_sec))
        self._stop_ev.clear()
        self.last_error = ""

        def _loop() -> None:
            from .autopilot import (
                run_auto_backup,
                run_auto_reconcile,
                run_auto_reports,
                run_autonomous_housekeeping,
            )
            from .data.news import evaluate_news_alpha
            from .perps.learning import evaluate_perp_live_signals

            next_trade = 0.0
            next_perps = 0.0
            next_stream = 0.0
            next_micro_learn = time.time() + 45.0
            next_learn = time.time() + min(120.0, float(self.cfg.learning.interval_sec))
            next_perps_learn = time.time() + min(180.0, float(self.cfg.perps.learn_interval_sec))
            next_backup = time.time() + 90.0
            next_reports = time.time() + 45.0
            next_housekeep = time.time() + 180.0
            reconcile_every = max(1, int(self.cfg.autopilot.reconcile_every_cycles))

            while not self._stop_ev.is_set():
                now = time.time()
                try:
                    if now >= next_trade:
                        self.run_single_cycle()
                        next_trade = time.time() + self.interval_sec
                        next_stream = time.time() + self.stream_interval_sec

                        if self.cfg.autopilot.enabled and (self.cycles == 1 or self.cycles % reconcile_every == 0):
                            st = Store(self.cfg.data.db_path)
                            try:
                                with self._lock:
                                    run_auto_reconcile(self.cfg, st)
                                self.last_reconcile_ts = int(time.time())
                            finally:
                                st.close()
                    elif now >= next_stream:
                        self.refresh_news_and_stream(include_markets=False)
                        next_stream = time.time() + self.stream_interval_sec

                    if self.cfg.perps.enabled and self.cfg.perps.mode == "paper" and now >= next_perps:
                        try:
                            self.run_perps_cycle()
                        except Exception as pexc:  # noqa: BLE001
                            self.perps_last_error = str(pexc)
                            self.auto_recoveries += 1
                            log.warning("מחזור Perps בלולאה (מתאושש אוטומטית): %s", pexc)
                        next_perps = time.time() + max(30.0, float(self.cfg.perps.interval_sec))

                    # מיקרו-למידה רציפה כל 5 דקות (מסחר דו-זרועי + חדשות מול שוק על DB מקומי ללא רשת)
                    if now >= next_micro_learn:
                        st_ml = Store(self.cfg.data.db_path)
                        try:
                            n_poly = evaluate_live_signals(st_ml, clob=None, now_ts=int(now), limit=250)
                            n_perp = evaluate_perp_live_signals(st_ml, now_ts=int(now), limit=250)
                            n_news = evaluate_news_alpha(st_ml, now_ts=int(now), limit=200)
                            if (n_poly + n_perp + n_news) > 0:
                                log.info("🧠 מיקרו-למידה רציפה: %d Polymarket | %d PERPS | %d חדשות-שוק", n_poly, n_perp, n_news)
                        finally:
                            st_ml.close()
                        next_micro_learn = time.time() + 300.0

                    if self.cfg.perps.enabled and self.cfg.perps.auto_learn and now >= next_perps_learn:
                        self._trigger_perps_learning_bg()
                        next_perps_learn = time.time() + max(600.0, float(self.cfg.perps.learn_interval_sec))

                    if self.cfg.learning.enabled and now >= next_learn:
                        self._trigger_learning_bg()
                        next_learn = time.time() + max(300.0, float(self.cfg.learning.interval_sec))

                    if self.cfg.autopilot.enabled and now >= next_housekeep:
                        st_hk = Store(self.cfg.data.db_path)
                        try:
                            with self._lock:
                                run_autonomous_housekeeping(self.cfg, st_hk)
                            self.housekeeping_cycles += 1
                            self.last_housekeeping_ts = int(time.time())
                            self.last_reconcile_ts = self.last_housekeeping_ts
                            self.last_reports_ts = self.last_housekeeping_ts
                        finally:
                            st_hk.close()
                        next_housekeep = time.time() + 1800.0

                    if self.cfg.autopilot.enabled and now >= next_backup:
                        st = Store(self.cfg.data.db_path)
                        try:
                            run_auto_backup(self.cfg, st)
                            self.last_backup_ts = int(time.time())
                        finally:
                            st.close()
                        next_backup = time.time() + max(600.0, float(self.cfg.autopilot.backup_interval_sec))

                    if self.cfg.autopilot.enabled and now >= next_reports:
                        st = Store(self.cfg.data.db_path)
                        try:
                            run_auto_reports(self.cfg, st)
                            self.last_reports_ts = int(time.time())
                        finally:
                            st.close()
                        next_reports = time.time() + max(300.0, float(self.cfg.autopilot.reports_interval_sec))
                except Exception as exc:      # noqa: BLE001
                    self.last_error = str(exc)
                    self.auto_recoveries += 1
                    log.warning("לולאה רציפה (מתאושש אוטומטית): %s", exc)
                    next_trade = max(next_trade, time.time() + 30.0)
                self._stop_ev.wait(15.0)

        self._thread = threading.Thread(target=_loop, daemon=True, name="pmmb-continuous")
        self._thread.start()
        return {
            "message": f"בוט רציף הופעל (מסחר כל {self.interval_sec:.0f}ש', אוטופיילוט מלא פעיל)",
            **self.state(),
        }

    def stop(self) -> dict:
        self._stop_ev.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.5)
        return {"message": "לולאת המסחר והשידור הרציף נעצרה", **self.state()}


def _build_perps_chart_payload(cfg, symbol: str, *, live: bool = False) -> dict:
    store = Store(cfg.data.db_path)
    try:
        if live and os.getenv("PMMB_DISABLE_LIVE_NEWS") != "1":
            try:
                from .perps.exchange import MultiPerpExchange
                from .perps.models import PerpInstrument

                ex = MultiPerpExchange(cfg.perps.exchange)
                inst = PerpInstrument(
                    symbol=symbol.upper(), exchange=cfg.perps.exchange.preferred_exchange if cfg.perps.exchange.preferred_exchange != "auto" else "okx",
                    exchange_symbol=f"{symbol.upper()}-USDT-SWAP", max_leverage=50.0, mark_price=1.0,
                )
                cs = ex.get_candles(inst, interval=cfg.perps.signal.timeframe, lookback=160)
                if cs:
                    store.insert_perp_candles(
                        symbol.upper(), inst.exchange, cfg.perps.signal.timeframe,
                        [(c.ts, c.open, c.high, c.low, c.close, c.volume) for c in cs],
                    )
            except Exception as exc:
                log.debug("רענון גרף Perps חי נכשל (%s): %s", symbol, exc)
        return build_perps_chart_series(store, cfg, symbol, limit=160)
    finally:
        store.close()


def _build_chart_payload(cfg, token_id: str, *, live: bool = False) -> dict:
    store = Store(cfg.data.db_path)
    live_levels = None
    try:
        if live and os.getenv("PMMB_DISABLE_LIVE_NEWS") != "1":
            try:
                clob = ClobClient(
                    HttpClient(cfg.data.clob_base_url, cfg.data.http_timeout, 1, cfg.data.rate_limit_rps),
                    history_ttl=30.0,
                )
                candles = clob.get_history(token_id, fidelity_min=60, lookback_candles=120, use_cache=True)
                if candles:
                    store.insert_ticks([(token_id, c.ts, c.price) for c in candles])
                bk = clob.get_book(token_id)
                if bk is not None:
                    store.record_book(token_id, int(time.time()), bk)
                    live_levels = {
                        "bids": [[round(float(p), 4), round(float(s), 1)] for p, s in (bk.bids or [])[:6]],
                        "asks": [[round(float(p), 4), round(float(s), 1)] for p, s in (bk.asks or [])[:6]],
                    }
            except Exception as exc:
                log.debug("רענון גרף חי נכשל (%s): %s", token_id[:12], exc)

        series = build_chart_series(store, cfg, token_id, limit=160)
        if live_levels is not None:
            series["book_levels"] = live_levels
        return series
    finally:
        store.close()


def make_handler(cfg, *, max_age_sec: float, refresh_sec: int, token: str | None,
                 trader: _TraderManager | None = None):
    token = str(token or os.environ.get("PMMB_STATUS_TOKEN", "")).strip()
    trader = trader or _TraderManager(cfg)

    class Handler(BaseHTTPRequestHandler):
        server_version = "pmmb-status/3"

        def log_message(self, fmt, *args):        # שקט — לא מציף את לוג הבוט
            message = _redact_token_from_log(fmt % args)
            log.debug("%s - %s", self.address_string(), message)

        def _authorized(self, query: dict) -> bool:
            if not token:
                # No configured secret is acceptable only for loopback clients.
                return _is_loopback_address(self.client_address[0])
            given = (query.get("token", [""])[0]
                     or self.headers.get("X-Token", "")
                     or self.headers.get("Authorization", "").removeprefix("Bearer "))
            return token_ok(given, token)

        def _send(self, code: int, body: bytes, ctype: str, *, head_only: bool = False,
                  headers: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for hk, hv in (headers or {}).items():
                self.send_header(hk, hv)
            self.end_headers()
            if head_only:
                return
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _read_json(self) -> dict:
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 16384)
            except ValueError:
                return {}
            if n <= 0:
                return {}
            raw = self.rfile.read(n)
            try:
                val = json.loads(raw.decode("utf-8"))
                return val if isinstance(val, dict) else {}
            except Exception:
                return {}

        def do_HEAD(self) -> None:                # noqa: N802 — חתימת הספרייה
            self._handle_get(head_only=True)

        def do_GET(self) -> None:                 # noqa: N802 — חתימת הספרייה
            self._handle_get(head_only=False)

        def do_POST(self) -> None:                # noqa: N802 — חתימת הספרייה
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path.rstrip("/") or "/"
            if not self._authorized(query):
                return self._send(401, b'{"error":"unauthorized"}', "application/json; charset=utf-8")

            body = self._read_json()
            try:
                if path == "/api/halt":
                    reason = str(body.get("reason") or "עצירה ידנית מהתוכנה")
                    p = write_halt(reason, source="ui")
                    res = {"ok": True, "message": f"הופעלה עצירת חירום: {reason}", "output": str(p)}
                elif path == "/api/resume":
                    cleared = clear_halt()
                    res = {"ok": True, "message": "עצירת החירום בוטלה" if cleared else "לא הייתה עצירה פעילה",
                           "output": f"cleared={cleared}"}
                elif path == "/api/backup":
                    b = backup_db(cfg.data.db_path)
                    res = {"ok": True, "message": f"גיבוי נשמר: {b.path.name} ({b.size_bytes/1024:.1f} KB)",
                           "output": f"{b.path} ({b.size_bytes/1024:.1f} KB)"}
                elif path == "/api/reconcile":
                    store = Store(cfg.data.db_path)
                    try:
                        rep = reconcile_paper(store, starting_cash=cfg.execution.starting_cash, fix=bool(body.get("fix")))
                        perp_rep = reconcile_perps(
                            store, mode=cfg.perps.mode, starting_cash=cfg.perps.risk.starting_cash, fix=bool(body.get("fix"))
                        ) if cfg.perps.enabled else None
                    finally:
                        store.close()
                    both_clean = rep.clean and (perp_rep is None or perp_rep.clean)
                    n_disc = len(rep.discrepancies) + (len(perp_rep.discrepancies) if perp_rep else 0)
                    out_md = rep.to_markdown() + ("\n\n" + perp_rep.to_markdown() if perp_rep else "")
                    res = {"ok": True, "clean": both_clean,
                           "message": "אפס פערים ב-DB (Polymarket + PERPS)" if both_clean else f"נמצאו {n_disc} פערים",
                           "output": out_md}
                elif path == "/api/news-refresh":
                    res = {"ok": True, **trader.refresh_news_and_stream(include_markets=True)}
                elif path == "/api/learn":
                    res = {"ok": True, **trader.run_learning_now(apply_changes=bool(body.get("apply", True)))}
                elif path == "/api/autopilot/maintain":
                    res = {"ok": True, **trader.run_maintenance_now()}
                elif path == "/api/autonomous/evolve":
                    res = {"ok": True, **trader.evolve_and_maintain_now()}
                elif path == "/api/paper-cycle":
                    res = {"ok": True, **trader.run_single_cycle()}
                elif path == "/api/perps/cycle":
                    res = {"ok": True, **trader.run_perps_cycle()}
                elif path == "/api/perps/learn":
                    res = {"ok": True, **trader.run_perps_learning_now(apply_changes=bool(body.get("apply", True)))}
                elif path == "/api/perps/simulate":
                    from .perps.backtest import run_perp_portfolio_backtest
                    from .perps.models import PerpCandle, PerpInstrument

                    sim_cfg = copy.deepcopy(cfg.perps)
                    if "max_leverage" in body:
                        sim_cfg.risk.max_leverage = max(2.0, min(50.0, float(body["max_leverage"])))
                    if "sl_atr_mult" in body:
                        sim_cfg.risk.sl_atr_mult = max(0.8, min(4.0, float(body["sl_atr_mult"])))
                    if "tp_atr_mult" in body:
                        sim_cfg.risk.tp_atr_mult = max(1.2, min(6.0, float(body["tp_atr_mult"])))
                    if "trailing_trigger_atr" in body:
                        sim_cfg.risk.trailing_trigger_atr = max(0.6, min(3.0, float(body["trailing_trigger_atr"])))
                    if "trailing_dist_atr" in body:
                        sim_cfg.risk.trailing_dist_atr = max(0.4, min(2.0, float(body["trailing_dist_atr"])))

                    st = Store(cfg.data.db_path)
                    try:
                        intel = {r["symbol"]: r for r in st.recent_perp_intel(limit=24)}
                        ds = {}
                        for sym in list(intel.keys())[:16]:
                            crows = st.get_perp_candles(sym, cfg.perps.signal.timeframe, limit=300)
                            if len(crows) >= 120:
                                r = intel[sym]
                                inst = PerpInstrument(
                                    symbol=sym, exchange=str(r.get("exchange") or "okx"),
                                    exchange_symbol=f"{sym}-USDT-SWAP",
                                    max_leverage=float(r.get("max_leverage") or 50.0),
                                    mark_price=float(r.get("price") or crows[-1]["close"]),
                                    funding_1h=float(r.get("funding_1h") or 0.0),
                                )
                                cs = [PerpCandle(ts=int(c["ts"]), open=float(c["open"]), high=float(c["high"]),
                                                 low=float(c["low"]), close=float(c["close"]), volume=float(c["volume"]))
                                      for c in crows]
                                ds[sym] = (inst, cs)
                    finally:
                        st.close()
                    if not ds:
                        res = {"ok": True, "message": "נדרשים נרות PERPS שמורים בסימולטור — הרץ מחזור PERPS קודם"}
                    else:
                        bt = run_perp_portfolio_backtest(sim_cfg, ds)
                        res = {
                            "ok": True,
                            "message": f"סימולציית What-If ({len(ds)} חוזים): תשואה {bt.return_pct:+.2f}% | PF {bt.profit_factor:.2f} | WR {bt.win_rate_pct:.0f}% | ליקווידציות {bt.liquidations}",
                            "result": {
                                "assets": len(ds), "return_pct": bt.return_pct, "final_equity": bt.ending_equity,
                                "trades": bt.trades, "win_rate_pct": bt.win_rate_pct,
                                "profit_factor": bt.profit_factor, "max_drawdown_pct": bt.max_drawdown_pct,
                                "liquidations": bt.liquidations, "avg_leverage": bt.avg_leverage,
                                "max_leverage": bt.max_leverage_used,
                            },
                        }
                elif path == "/api/positions/close":
                    arm = str(body.get("arm") or "")
                    key = str(body.get("key") or "")
                    reason = str(body.get("reason") or "סגירה ידנית מהטרמינל")
                    res = {"ok": True, **trader.close_position(arm, key, reason=reason)}
                elif path == "/api/positions/update":
                    arm = str(body.get("arm") or "")
                    key = str(body.get("key") or "")
                    sp = float(body["stop_price"]) if body.get("stop_price") not in (None, "") else None
                    tp = float(body["target_price"]) if body.get("target_price") not in (None, "") else None
                    res = {"ok": True, **trader.update_position_levels(arm, key, stop_price=sp, target_price=tp)}
                elif path == "/api/positions/close-all":
                    arm = str(body.get("arm") or "all")
                    reason = str(body.get("reason") or "סגירת כל הפוזיציות מהטרמינל")
                    res = {"ok": True, **trader.close_all_positions(arm=arm, reason=reason)}
                elif path == "/api/perps/order":
                    sym = str(body.get("symbol") or "")
                    side = str(body.get("side") or "LONG")
                    margin = float(body.get("margin") or 20.0)
                    lev = float(body.get("leverage") or 10.0)
                    res = {"ok": True, **trader.open_perps_order(sym, side, margin, lev)}
                elif path == "/api/config/update":
                    res = {"ok": True, **trader.update_config_params(body)}
                elif path == "/api/perps/toggle":
                    cfg.perps.enabled = bool(body.get("enabled", not cfg.perps.enabled))
                    res = {"ok": True, "enabled": cfg.perps.enabled,
                           "message": f"זרוע PERPS {'הופעלה' if cfg.perps.enabled else 'הושהתה'}"}
                elif path == "/api/trader/start":
                    res = {"ok": True, **trader.start(float(body.get("interval_sec") or 180))}
                elif path == "/api/trader/stop":
                    res = {"ok": True, **trader.stop()}
                else:
                    return self._send(404, b'{"error":"not found"}', "application/json; charset=utf-8")
                trader.invalidate_cache()
                return self._send(200, json.dumps(res, ensure_ascii=False).encode(),
                                  "application/json; charset=utf-8")
            except KeyError as exc:
                return self._send(404, json.dumps({"error": str(exc)}, ensure_ascii=False).encode(),
                                  "application/json; charset=utf-8")
            except ValueError as exc:
                return self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode(),
                                  "application/json; charset=utf-8")
            except PermissionError as exc:
                return self._send(403, json.dumps({"error": str(exc)}, ensure_ascii=False).encode(),
                                  "application/json; charset=utf-8")
            except Exception as exc:              # noqa: BLE001
                log.exception("כשל בפעולת API %s: %s", path, exc)
                return self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False).encode(),
                                  "application/json; charset=utf-8")

        def _handle_get(self, *, head_only: bool) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path.rstrip("/") or "/"

            if path == "/healthz":
                health = check_health(max_age_sec=max_age_sec)
                body = json.dumps(health.as_dict(), ensure_ascii=False).encode()
                return self._send(200 if health.healthy else 503, body,
                                  "application/json; charset=utf-8", head_only=head_only)

            if not self._authorized(query):
                return self._send(401, b'{"error":"unauthorized"}',
                                  "application/json; charset=utf-8", head_only=head_only)

            try:
                if path == "/status.json":
                    st = build_status(cfg, max_age_sec=max_age_sec)
                    return self._send(200, json.dumps(st, ensure_ascii=False, indent=2).encode(),
                                      "application/json; charset=utf-8", head_only=head_only)
                if path == "/api/state":
                    st = trader.get_state_snapshot(max_age_sec=max_age_sec)
                    return self._send(200, json.dumps(st, ensure_ascii=False).encode(),
                                      "application/json; charset=utf-8", head_only=head_only)
                if path == "/api/analytics/performance":
                    store = Store(cfg.data.db_path)
                    try:
                        perf = build_performance_analytics(cfg, store)
                    finally:
                        store.close()
                    return self._send(
                        200,
                        json.dumps({"performance": perf, "autonomous": trader.state()}, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8",
                        head_only=head_only,
                    )
                if path == "/api/export/trades.csv":
                    import csv
                    import io
                    from datetime import datetime, timezone

                    st = trader.get_state_snapshot(max_age_sec=max_age_sec)
                    buf = io.StringIO()
                    w = csv.writer(buf)
                    w.writerow(["זמן", "זרוע", "נכס / שוק", "כיוון", "מחיר", "נומינלי ($)", "עמלה ($)", "רווח נטו ($)", "סיבה"])
                    for t in ((st.get("perps") or {}).get("recent_trades") or []):
                        ts_iso = datetime.fromtimestamp(int(t.get("ts") or 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                        w.writerow([ts_iso, "PERPS", t.get("symbol"), t.get("side"), t.get("price"),
                                    t.get("notional"), t.get("fee"), t.get("realized"), t.get("reason")])
                    for f in (st.get("fills") or []):
                        ts_iso = datetime.fromtimestamp(int(f.get("ts") or 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                        w.writerow([ts_iso, "Polymarket", f.get("question"), f.get("side"), f.get("price"),
                                    f.get("notional"), f.get("fee"), f.get("realized"), f.get("reason")])
                    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
                    return self._send(
                        200, csv_bytes, "text/csv; charset=utf-8", head_only=head_only,
                        headers={"Content-Disposition": 'attachment; filename="pmmb_trades.csv"'},
                    )
                if path == "/api/chart":
                    tid = (query.get("token", [""])[0] or "").strip()
                    if not tid:
                        return self._send(400, b'{"error":"missing token"}',
                                          "application/json; charset=utf-8", head_only=head_only)
                    live_flag = query.get("live", ["0"])[0] == "1"
                    chart = _build_chart_payload(cfg, tid, live=live_flag)
                    return self._send(200, json.dumps(chart, ensure_ascii=False).encode(),
                                      "application/json; charset=utf-8", head_only=head_only)
                if path == "/api/perps/chart":
                    sym = (query.get("symbol", ["BTC"])[0] or "BTC").strip().upper()
                    live_flag = query.get("live", ["0"])[0] == "1"
                    pchart = _build_perps_chart_payload(cfg, sym, live=live_flag)
                    return self._send(200, json.dumps(pchart, ensure_ascii=False).encode(),
                                      "application/json; charset=utf-8", head_only=head_only)
                if path == "/api/perps/book":
                    sym = (query.get("symbol", ["BTC"])[0] or "BTC").strip().upper()
                    from .perps.models import PerpInstrument

                    ex = trader._get_perps_exchange()
                    inst = next((x for x in ex.scan() if x.symbol == sym), None)
                    if inst is None:
                        inst = PerpInstrument(symbol=sym, exchange="okx", exchange_symbol=f"{sym}-USDT-SWAP", max_leverage=50.0, mark_price=1.0)
                    bk = ex.get_book(inst, levels=8)
                    payload_bk = {
                        "symbol": sym,
                        "exchange": inst.exchange,
                        "spread_bps": round(bk.spread_bps, 2) if bk else 0.0,
                        "imbalance": round(bk.imbalance(8), 3) if bk else 0.0,
                        "bids": [[round(float(p), 6), round(float(s), 4)] for p, s in (bk.bids[:8] if bk else [])],
                        "asks": [[round(float(p), 6), round(float(s), 4)] for p, s in (bk.asks[:8] if bk else [])],
                    }
                    return self._send(200, json.dumps(payload_bk, ensure_ascii=False).encode(),
                                      "application/json; charset=utf-8", head_only=head_only)
                if path == "/lite":
                    st = build_status(cfg, max_age_sec=max_age_sec)
                    return self._send(200, status_html(st, refresh_sec=refresh_sec).encode(),
                                      "text/html; charset=utf-8", head_only=head_only)
                if path in ("/", "/index.html"):
                    st = trader.get_state_snapshot(max_age_sec=max_age_sec)
                    html = command_center_html(st, refresh_sec=min(max(refresh_sec, 0), 15) if refresh_sec else 0)
                    return self._send(200, html.encode(), "text/html; charset=utf-8", head_only=head_only)
            except Exception as exc:              # noqa: BLE001 — השרת לא נופל על דוח
                log.exception("כשל בבניית המצב: %s", exc)
                return self._send(500, b'{"error":"status build failed"}',
                                  "application/json; charset=utf-8", head_only=head_only)

            self._send(404, b'{"error":"not found"}',
                       "application/json; charset=utf-8", head_only=head_only)

    return Handler


def serve(cfg, *, host: str = "127.0.0.1", port: int = 8787,
          max_age_sec: float = 300, refresh_sec: int = 30,
          token: str | None = None, autostart: bool = False,
          interval_sec: float = 180.0) -> ThreadingHTTPServer:
    """Run the dashboard. Non-loopback binds require PMMB_STATUS_TOKEN."""
    effective_token = str(token or os.environ.get("PMMB_STATUS_TOKEN", "")).strip()
    if not effective_token and not _is_loopback_address(host):
        raise ValueError(
            "Refusing non-loopback dashboard bind without authentication. "
            "Set PMMB_STATUS_TOKEN or bind to 127.0.0.1."
        )
    trader = _TraderManager(cfg)
    if autostart and cfg.execution.mode == "paper":
        trader.start(interval_sec=interval_sec)
    handler = make_handler(cfg, max_age_sec=max_age_sec, refresh_sec=refresh_sec,
                           token=effective_token, trader=trader)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd._trader_manager = trader  # type: ignore[attr-defined]
    log.info("שרת התוכנה והמצב מאזין על http://%s:%d (autostart=%s)", host, port, autostart)
    return httpd
