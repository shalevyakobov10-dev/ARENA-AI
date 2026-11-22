"""
התראות לטלפון דרך Telegram — בלי תלות בספרייה חיצונית.

עיקרון: התראה שנכשלה לא מפילה את הבוט. לעולם. לכן כל קריאה עטופה,
יש המתנה מינימלית בין הודעות, וזהות כפולה לא נשלחת פעמיים.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class Notifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None,
                 *, min_interval_sec: float = 3.0, timeout: float = 8.0) -> None:
        self.token = token if token is not None else os.environ.get("PMMB_TELEGRAM_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.environ.get("PMMB_TELEGRAM_CHAT_ID", "")
        self.min_interval = min_interval_sec
        self.timeout = timeout
        self._last_sent = 0.0
        self._last_text = ""
        self.sent = 0
        self.failed = 0

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str, *, force: bool = False) -> bool:
        """מחזיר True אם נשלח. לעולם לא זורק חריגה."""
        if not self.enabled:
            log.debug("Telegram לא מוגדר — מדלג על התראה")
            return False
        now = time.time()
        if not force:
            if text == self._last_text:
                return False                     # כפילות — לא מציף
            if now - self._last_sent < self.min_interval:
                return False
        body = json.dumps({
            "chat_id": self.chat_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            TELEGRAM_API.format(token=self.token), data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
            self.sent += 1
            self._last_sent, self._last_text = now, text
            return True
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.failed += 1
            log.warning("התראת Telegram נכשלה: %s", exc)
            return False


# ---------------------------------------------------------------- תבניות
def fmt_entry(mode: str, question: str, price: float, size: float, score: float,
              edge: float) -> str:
    return (f"🟢 <b>כניסה</b> [{mode}]\n{question[:90]}\n"
            f"מחיר {price:.3f} · {size:.1f} מניות · score {score:.2f} · edge {edge:+.3f}")


def fmt_exit(mode: str, question: str, price: float, pnl: float, reason: str) -> str:
    icon = "✅" if pnl >= 0 else "🔻"
    return (f"{icon} <b>יציאה</b> [{mode}]\n{question[:90]}\n"
            f"מחיר {price:.3f} · PnL {pnl:+.2f} · {reason}")


def fmt_halt(mode: str, reason: str, equity: float) -> str:
    return (f"🛑 <b>הבוט עצר את עצמו</b> [{mode}]\n{reason}\nהון {equity:.2f}")


def fmt_daily(mode: str, equity: float, pnl_day: float, trades: int) -> str:
    icon = "📈" if pnl_day >= 0 else "📉"
    return (f"{icon} <b>סיכום יומי</b> [{mode}]\nהון {equity:.2f} · "
            f"PnL {pnl_day:+.2f} · {trades} עסקאות")
