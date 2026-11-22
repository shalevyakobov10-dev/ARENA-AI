"""
לולאת פקודות Telegram לטלפון — בספרייה הסטנדרטית בלבד.

אבטחה:
  - עונה **רק** ל-chat_id המורשה (PMMB_TELEGRAM_CHAT_ID). כל אחר מתעלם.
  - קריאה + עצירת חירום בלבד: /status, /positions, /guards, /readiness, /halt, /resume.
  - לעולם לא מקבל פקודות מסחר או שינוי פרמטרים מהטלפון.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .notify import Notifier
from .readiness import ICON, Thresholds, collect_facts, evaluate, summary as ready_summary
from .runtime import clear_halt, default_state_dir, write_halt
from .status import build_status

log = logging.getLogger(__name__)

UPDATES_API = "https://api.telegram.org/bot{token}/getUpdates"


class TelegramController:
    def __init__(
        self,
        cfg,
        *,
        token: str | None = None,
        chat_id: str | None = None,
        state_dir: str | Path | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self.cfg = cfg
        self.token = token if token is not None else os.environ.get("PMMB_TELEGRAM_TOKEN", "")
        self.chat_id = str(chat_id if chat_id is not None else os.environ.get("PMMB_TELEGRAM_CHAT_ID", ""))
        self.state_dir = Path(state_dir) if state_dir is not None else default_state_dir()
        self.notifier = notifier or Notifier(self.token, self.chat_id, min_interval_sec=0.0)
        self._offset = self._load_offset()

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def _offset_file(self) -> Path:
        return self.state_dir / "telegram_offset.txt"

    def _load_offset(self) -> int:
        try:
            return int(self._offset_file().read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError, OSError):
            return 0

    def _save_offset(self, offset: int) -> None:
        p = self._offset_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(offset), encoding="utf-8")

    # ------------------------------------------------------------------
    def handle_text(self, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""
        parts = raw.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/start", "/help"):
            return (
                "🤖 <b>PMMB — פקודות מהטלפון</b>\n"
                "/status — בריאות, הון ו-PnL היום\n"
                "/positions — פוזיציות פתוחות וסטופים\n"
                "/guards — מרווח הגנות (סטופ יומי / DD)\n"
                "/readiness — מוכנות למעבר ל-live\n"
                "/halt [סיבה] — עצירת חירום מיידית\n"
                "/resume — ביטול עצירה ידנית"
            )

        if cmd == "/status":
            st = build_status(self.cfg)
            h = st["health"]
            b = st["bankroll"]
            t = st["today"]
            hb = st.get("heartbeat") or {}
            icon = "🟢" if h["healthy"] else "🔴"
            eq = b.get("equity") or 0.0
            cash = b.get("cash") or 0.0
            exp = b.get("exposure") or 0.0
            unr = b.get("unrealized_pnl") or 0.0
            return (
                f"{icon} <b>PMMB [{st['mode']}]</b> — {h['reason']}\n"
                f"מחזור #{hb.get('cycle', 0)} · הון <b>{eq:.2f}</b> (מזומן {cash:.2f} · חשיפה {exp:.2f})\n"
                f"פתוחות: {b.get('open_positions', 0)} · לא ממומש: {unr:+.2f}\n"
                f"היום: {t.get('fills', 0)} מילויים · PnL {t.get('realized_pnl', 0):+.2f} · "
                f"עמלות {t.get('fees', 0):.2f}"
            )

        if cmd == "/positions":
            st = build_status(self.cfg)
            pos = st.get("positions") or []
            if not pos:
                return "📭 אין פוזיציות פתוחות כרגע."
            lines = [f"📊 <b>פוזיציות פתוחות ({len(pos)})</b>"]
            for p in pos:
                q = (p.get("question") or p["token_id"])[:42]
                mark = p.get("mark_price")
                unr = p.get("unrealized_pnl")
                mark_txt = f"{mark:.3f}" if mark is not None else "—"
                unr_txt = f"{unr:+.2f}" if unr is not None else "—"
                lines.append(
                    f"• <b>{q}</b>\n"
                    f"  {p['size']:.1f} @ {p['avg_price']:.3f} → {mark_txt} "
                    f"(<b>{unr_txt}</b>) · SL {p.get('stop_price') or '-'} / TP {p.get('target_price') or '-'}"
                )
            return "\n".join(lines)

        if cmd == "/guards":
            st = build_status(self.cfg)
            g = st.get("guards") or {}
            if not g:
                return "אין נתוני הגנות עדיין (לא רץ מחזור)."
            return (
                "🛡️ <b>מצב ההגנות</b>\n"
                f"הפסד יומי: {g.get('daily_loss_used', 0):.2f} / {g.get('daily_loss_limit', 0):.2f} USDC "
                f"(נותר {g.get('daily_room', 0):.2f})\n"
                f"drawdown: {g.get('drawdown_pct', 0):.2f}% / {g.get('drawdown_limit_pct', 0):.0f}%\n"
                f"מרווח חשיפה: {g.get('exposure_room', 0):.2f} USDC · פוזיציות פנויות: {g.get('positions_room', 0)}"
            )

        if cmd == "/readiness":
            th = Thresholds()
            checks = evaluate(collect_facts(self.cfg), th)
            lines = [f"<b>{ready_summary(checks)}</b>"]
            for c in checks:
                lines.append(f"{ICON[c.status]} {c.label}: {c.detail}")
            return "\n".join(lines)

        if cmd == "/halt":
            reason = arg or "עצירה מהטלפון"
            write_halt(reason, source="phone", state_dir=self.state_dir)
            return f"🛑 <b>עצירת חירום הופעלה:</b> {reason}\nלשחרור: /resume"

        if cmd == "/resume":
            existed = clear_halt(state_dir=self.state_dir)
            return "▶️ <b>העצירה הידנית בוטלה.</b>" if existed else "ℹ️ לא הייתה עצירה פעילה."

        return "❓ פקודה לא מוכרת. שלח /help לרשימת הפקודות."

    # ------------------------------------------------------------------
    def process_updates(self, updates: list[dict]) -> int:
        handled = 0
        max_id = self._offset - 1
        for u in updates:
            uid = int(u.get("update_id", 0))
            if uid > max_id:
                max_id = uid
            msg = u.get("message") or u.get("edited_message") or {}
            cid = str((msg.get("chat") or {}).get("id") or "")
            if not cid or cid != self.chat_id:
                if cid:
                    log.warning("הודעה משיחה לא מורשית %s — מתעלם", cid)
                continue
            reply = self.handle_text(str(msg.get("text") or ""))
            if reply:
                self.notifier.send(reply, force=True)
                handled += 1
        if max_id >= self._offset:
            self._offset = max_id + 1
            self._save_offset(self._offset)
        return handled

    def poll_once(self, *, timeout: int = 20) -> int:
        if not self.enabled:
            raise RuntimeError("חסרים PMMB_TELEGRAM_TOKEN / PMMB_TELEGRAM_CHAT_ID")
        url = f"{UPDATES_API.format(token=self.token)}?offset={self._offset}&timeout={timeout}"
        try:
            with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            log.warning("Telegram getUpdates נכשל: %s", exc)
            return 0
        if not data.get("ok"):
            log.warning("Telegram שגיאה: %s", data)
            return 0
        return self.process_updates(data.get("result") or [])

    def run_forever(self, *, timeout: int = 25) -> None:
        log.info("🤖 מאזין לפקודות Telegram (chat_id=%s)", self.chat_id)
        while True:
            try:
                self.poll_once(timeout=timeout)
            except KeyboardInterrupt:
                break
            except Exception as exc:          # noqa: BLE001
                log.warning("שגיאה בלולאת Telegram: %s", exc)
                time.sleep(5)
