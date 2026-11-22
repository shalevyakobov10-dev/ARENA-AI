"""
שרת התוכנה והדשבורד — PMMB Command Center + JSON/Health API.

בכוונה בספרייה הסטנדרטית: אפס תלויות חיצוניות, עולה בכל מקום.
פעולות מסחר דרך ה-UI מוגבלות למצב `paper` בלבד (הגנה מפני מסחר live מדפדפן).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .backup import backup_db
from .data.store import Store
from .reconcile import reconcile_paper
from .runtime import (
    ProcessLock,
    ProcessLockError,
    check_health,
    clear_halt,
    write_halt,
)
from .status import build_command_center_data, build_status, status_html
from .ui import command_center_html

log = logging.getLogger(__name__)


def token_ok(given: str, token: str) -> bool:
    """השוואה בזמן קבוע. token ריק ⇒ אין הגנה (מקומי)."""
    if not token:
        return True
    return hmac.compare_digest(str(given or ""), token)


class _TraderManager:
    """מנהל הפעלה/עצירה נקייה של לולאת Paper מתוך התוכנה (לעולם לא live)."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._stop_ev = threading.Event()
        self._thread: threading.Thread | None = None
        self.cycles = 0
        self.last_error = ""
        self.interval_sec = 300.0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def state(self) -> dict:
        return {
            "running": self.running,
            "cycles": self.cycles,
            "last_error": self.last_error,
            "interval_sec": self.interval_sec,
        }

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
            try:
                st = eng.run_once()
                self.cycles += 1
                self.last_error = ""
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

    def start(self, interval_sec: float = 300.0) -> dict:
        if self.cfg.execution.mode != "paper":
            raise PermissionError("סוחר אוטומטי מהממשק מותר במצב paper בלבד")
        if self.running:
            return {"message": "הסוחר האוטומטי כבר פועל", **self.state()}
        self.interval_sec = max(30.0, float(interval_sec))
        self._stop_ev.clear()
        self.last_error = ""

        def _loop() -> None:
            while not self._stop_ev.is_set():
                try:
                    self.run_single_cycle()
                except Exception as exc:      # noqa: BLE001
                    self.last_error = str(exc)
                    log.warning("סוחר רקע: %s", exc)
                self._stop_ev.wait(self.interval_sec)

        self._thread = threading.Thread(target=_loop, daemon=True, name="pmmb-paper-ui")
        self._thread.start()
        return {"message": f"סוחר Paper אוטומטי הופעל (כל {self.interval_sec:.0f} שנ')", **self.state()}

    def stop(self) -> dict:
        self._stop_ev.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        return {"message": "סוחר אוטומטי נעצר", **self.state()}


def make_handler(cfg, *, max_age_sec: float, refresh_sec: int, token: str | None,
                 trader: _TraderManager | None = None):
    token = token if token is not None else os.environ.get("PMMB_STATUS_TOKEN", "")
    trader = trader or _TraderManager(cfg)

    class Handler(BaseHTTPRequestHandler):
        server_version = "pmmb-status/2"

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
                elif path == "/api/paper-cycle":
                    res = {"ok": True, **trader.run_single_cycle()}
                elif path == "/api/trader/start":
                    res = {"ok": True, **trader.start(float(body.get("interval_sec") or 300))}
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
          token: str | None = None) -> ThreadingHTTPServer:
    """מרים את השרת (חוסם). מחזיר את המופע למי שרוצה לכבות בעצמו."""
    trader = _TraderManager(cfg)
    handler = make_handler(cfg, max_age_sec=max_age_sec, refresh_sec=refresh_sec,
                           token=token, trader=trader)
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd._trader_manager = trader  # type: ignore[attr-defined]
    log.info("שרת התוכנה והמצב מאזין על http://%s:%d", host, port)
    return httpd
