"""בדיקות לגיבוי ה-DB וללולאת פקודות ה-Telegram (ללא רשת)."""
from __future__ import annotations

import time
from pathlib import Path

from pmmb.backup import backup_db
from pmmb.data.store import Store
from pmmb.notify import Notifier
from pmmb.runtime import Heartbeat, read_halt, write_heartbeat
from pmmb.telegram_bot import TelegramController


def test_backup_creates_valid_copy_and_rotates(tmp_path):
    db = tmp_path / "pmmb.db"
    s = Store(db)
    s.event("test", "hello")
    s.close()

    bdir = tmp_path / "backups"
    r1 = backup_db(db, bdir, keep=2)
    assert r1.ok and r1.path.exists() and r1.size_bytes > 0

    # יוצרים עוד גיבויים עם שמות שונים כדי לוודא שמירה של keep=2
    (bdir / "pmmb-20260101-000001.db").write_bytes(r1.path.read_bytes())
    (bdir / "pmmb-20260101-000002.db").write_bytes(r1.path.read_bytes())
    time.sleep(1.05)
    r2 = backup_db(db, bdir, keep=2)
    assert r2.ok and r2.removed >= 1
    assert len(list(bdir.glob("pmmb-*.db"))) == 2


def test_telegram_controller_auth_and_commands(tmp_path, cfg, monkeypatch):
    state_dir = tmp_path / "state"
    monkeypatch.setenv("PMMB_STATE_DIR", str(state_dir))
    cfg.data.db_path = str(tmp_path / "tg.db")
    Store(cfg.data.db_path).close()
    write_heartbeat(Heartbeat(ts=time.time(), cycle=4, equity=1025.0, cash=900.0,
                              exposure=125.0, positions=1), state_dir=state_dir)

    sent: list[str] = []
    notifier = Notifier(token="T", chat_id="12345", min_interval_sec=0)
    notifier.send = lambda txt, force=False: sent.append(txt) or True

    bot = TelegramController(cfg, token="T", chat_id="12345", state_dir=state_dir, notifier=notifier)

    updates = [
        {"update_id": 10, "message": {"chat": {"id": 99999}, "text": "/halt hacker"}},  # לא מורשה!
        {"update_id": 11, "message": {"chat": {"id": 12345}, "text": "/status"}},
        {"update_id": 12, "message": {"chat": {"id": 12345}, "text": "/halt מהטלפון"}},
        {"update_id": 13, "message": {"chat": {"id": 12345}, "text": "/readiness"}},
    ]
    n = bot.process_updates(updates)
    assert n == 3
    assert "1025.00" in sent[0]
    assert "עצירת חירום" in sent[1]
    assert read_halt(state_dir).reason == "מהטלפון"
    assert "קריטריונים" in sent[2] or "מוכן" in sent[2]

    # offset נשמר כדי שלא נעבד שוב אחרי ריסטארט
    bot2 = TelegramController(cfg, token="T", chat_id="12345", state_dir=state_dir, notifier=notifier)
    assert bot2._offset == 14
    assert "בוטלה" in bot2.handle_text("/resume")
    assert read_halt(state_dir) is None
