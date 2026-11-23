"""
שרת התוכנה והדשבורד — PMMB Command Center + שידור חי + JSON/Control API.

בכוונה בספרייה הסטנדרטית: אפס תלויות חיצוניות, עולה בכל מקום.
פעולות מסחר דרך ה-UI מוגבלות למצב `paper` בלבד (הגנה מפני מסחר live מדפדפן).
"""
from __future__ import annotations

import copy
import hmac
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .backup import backup_db
from .data.clob import ClobClient
from .data.gamma import GammaClient, MarketUniverse
from .data.http import HttpClient
from .data.news import match_market_news, refresh_news_to_store
from .data.store import Store
from .learning import _apply as _apply_learned_cfg, evaluate_live_signals, run_self_learning_cycle
from .reconcile import reconcile_paper
from .runtime import (
    ProcessLock,
    ProcessLockError,
    check_health,
    clear_halt,
    write_halt,
)
from .status import build_chart_series, build_command_center_data, build_status, status_html
from .ui import command_center_html

log = logging.getLogger(__name__)


def token_ok(given: str, token: str) -> bool:
    """השוואה בזמן קבוע. token ריק ⇒ אין הגנה (מקומי)."""
    if not token:
        return True
    return hmac.compare_digest(str(given or ""), token)


class _TraderManager:
    """
    מנהל שידור חי ולולאה רציפה ("בלי הפסקה") מתוך התוכנה:
      - הזרמת גרפים וטיקים בזמן אמת (כל 60 שנ')
      - פיד חדשות שווקים חיות (כל news.refresh_interval_sec)
      - מחזור מסחר Mean-Reversion ב-paper בלבד (כל interval_sec)
      - מחזור למידה עצמית ושיפור Walk-Forward (כל learning.interval_sec)
    """

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._learn_lock = threading.Lock()
        self._stop_ev = threading.Event()
        self._thread: threading.Thread | None = None
        self._learn_thread: threading.Thread | None = None
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
        self._seen_pos_alerts: set[str] = set()
        self.interval_sec = float(cfg.autopilot.trade_interval_sec)
        self.stream_interval_sec = float(cfg.autopilot.stream_interval_sec)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def state(self) -> dict:
        return {
            "running": self.running,
            "cycles": self.cycles,
            "stream_ticks": self.stream_ticks,
            "news_fetches": self.news_fetches,
            "learn_cycles": self.learn_cycles,
            "last_news_ts": self.last_news_ts,
            "last_stream_ts": self.last_stream_ts,
            "last_learn_ts": self.last_learn_ts,
            "last_reconcile_ts": self.last_reconcile_ts,
            "last_backup_ts": self.last_backup_ts,
            "last_reports_ts": self.last_reports_ts,
            "last_error": self.last_error,
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
            from .autopilot import run_auto_backup, run_auto_reconcile, run_auto_reports

            next_trade = 0.0
            next_stream = 0.0
            next_learn = time.time() + min(120.0, float(self.cfg.learning.interval_sec))
            next_backup = time.time() + 90.0
            next_reports = time.time() + 45.0
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

                    if self.cfg.learning.enabled and now >= next_learn:
                        self._trigger_learning_bg()
                        next_learn = time.time() + max(300.0, float(self.cfg.learning.interval_sec))

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
                    log.warning("לולאה רציפה: %s", exc)
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
    token = token if token is not None else os.environ.get("PMMB_STATUS_TOKEN", "")
    trader = trader or _TraderManager(cfg)

    class Handler(BaseHTTPRequestHandler):
        server_version = "pmmb-status/3"

        def log_message(self, fmt, *args):        # שקט — לא מציף את לוג הבוט
            log.debug("%s - %s", self.address_string(), fmt % args)

        def _authorized(self, query: dict) -> bool:
            if not token:
                return True
            given = (query.get("token", [""])[0]
                     or self.headers.get("X-Token", "")
                     or self.headers.get("Authorization", "").removeprefix("Bearer "))
            return token_ok(given, token)

        def _send(self, code: int, body: bytes, ctype: str, *, head_only: bool = False) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
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
                    finally:
                        store.close()
                    res = {"ok": True, "clean": rep.clean,
                           "message": "אפס פערים ב-DB" if rep.clean else f"נמצאו {len(rep.discrepancies)} פערים",
                           "output": rep.to_markdown()}
                elif path == "/api/news-refresh":
                    res = {"ok": True, **trader.refresh_news_and_stream(include_markets=True)}
                elif path == "/api/learn":
                    res = {"ok": True, **trader.run_learning_now(apply_changes=bool(body.get("apply", True)))}
                elif path == "/api/autopilot/maintain":
                    res = {"ok": True, **trader.run_maintenance_now()}
                elif path == "/api/paper-cycle":
                    res = {"ok": True, **trader.run_single_cycle()}
                elif path == "/api/trader/start":
                    res = {"ok": True, **trader.start(float(body.get("interval_sec") or 180))}
                elif path == "/api/trader/stop":
                    res = {"ok": True, **trader.stop()}
                else:
                    return self._send(404, b'{"error":"not found"}', "application/json; charset=utf-8")
                return self._send(200, json.dumps(res, ensure_ascii=False).encode(),
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
                    st = build_command_center_data(
                        cfg, max_age_sec=max_age_sec, trader_state=trader.state()
                    )
                    return self._send(200, json.dumps(st, ensure_ascii=False).encode(),
                                      "application/json; charset=utf-8", head_only=head_only)
                if path == "/api/chart":
                    tid = (query.get("token", [""])[0] or "").strip()
                    if not tid:
                        return self._send(400, b'{"error":"missing token"}',
                                          "application/json; charset=utf-8", head_only=head_only)
                    live_flag = query.get("live", ["0"])[0] == "1"
                    chart = _build_chart_payload(cfg, tid, live=live_flag)
                    return self._send(200, json.dumps(chart, ensure_ascii=False).encode(),
                                      "application/json; charset=utf-8", head_only=head_only)
                if path == "/lite":
                    st = build_status(cfg, max_age_sec=max_age_sec)
                    return self._send(200, status_html(st, refresh_sec=refresh_sec).encode(),
                                      "text/html; charset=utf-8", head_only=head_only)
                if path in ("/", "/index.html"):
                    st = build_command_center_data(
                        cfg, max_age_sec=max_age_sec, trader_state=trader.state()
                    )
                    html = command_center_html(st, refresh_sec=min(max(refresh_sec, 0), 15) if refresh_sec else 0)
                    return self._send(200, html.encode(), "text/html; charset=utf-8", head_only=head_only)
            except Exception as exc:              # noqa: BLE001 — השרת לא נופל על דוח
                log.exception("כשל בבניית המצב: %s", exc)
                return self._send(500, b'{"error":"status build failed"}',
                                  "application/json; charset=utf-8", head_only=head_only)

            self._send(404, b'{"error":"not found"}',
                       "application/json; charset=utf-8", head_only=head_only)

    return Handler


def serve(cfg, *, host: str = "0.0.0.0", port: int = 8787,
          max_age_sec: float = 300, refresh_sec: int = 30,
          token: str | None = None, autostart: bool = False,
          interval_sec: float = 180.0) -> ThreadingHTTPServer:
    """מרים את השרת (חוסם). אם autostart=True ובמצב paper — מפעיל לולאת מסחר+חדשות+למידה רציפה."""
    trader = _TraderManager(cfg)
    if autostart and cfg.execution.mode == "paper":
        trader.start(interval_sec=interval_sec)
    handler = make_handler(cfg, max_age_sec=max_age_sec, refresh_sec=refresh_sec,
                           token=token, trader=trader)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd._trader_manager = trader  # type: ignore[attr-defined]
    log.info("שרת התוכנה והמצב מאזין על http://%s:%d (autostart=%s)", host, port, autostart)
    return httpd
