"""
שרת מצב קטן — כדי לראות מהטלפון מה הבוט עושה, בלי לפתוח מסך.

בכוונה בספרייה הסטנדרטית: אפס תלויות, אפס התקנה, עולה בכל מקום.
קריאה בלבד. אין כאן שום נתיב שנותן פקודות למסחר — זה לא API לשליטה.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .runtime import check_health
from .status import build_status, status_html

log = logging.getLogger(__name__)


def token_ok(given: str, token: str) -> bool:
    """השוואה בזמן קבוע. token ריק ⇒ אין הגנה (מקומי)."""
    if not token:
        return True
    return hmac.compare_digest(str(given or ""), token)


def make_handler(cfg, *, max_age_sec: float, refresh_sec: int, token: str | None):
    token = token if token is not None else os.environ.get("PMMB_STATUS_TOKEN", "")

    class Handler(BaseHTTPRequestHandler):
        server_version = "pmmb-status/1"

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

        def do_HEAD(self) -> None:                # noqa: N802 — חתימת הספרייה
            self._handle(head_only=True)

        def do_GET(self) -> None:                 # noqa: N802 — חתימת הספרייה
            self._handle(head_only=False)

        def _handle(self, *, head_only: bool) -> None:
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
                if path in ("/", "/index.html"):
                    st = build_status(cfg, max_age_sec=max_age_sec)
                    return self._send(200, status_html(st, refresh_sec=refresh_sec).encode(),
                                      "text/html; charset=utf-8", head_only=head_only)
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
    handler = make_handler(cfg, max_age_sec=max_age_sec, refresh_sec=refresh_sec, token=token)
    httpd = ThreadingHTTPServer((host, port), handler)
    log.info("שרת מצב מאזין על http://%s:%d (קריאה בלבד)", host, port)
    return httpd
