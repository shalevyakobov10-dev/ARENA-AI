"""מצב המערכת והדשבורד — בלי רשת, על DB אמיתי זמני."""
import time
from datetime import datetime, timezone

from pmmb.data.store import Store
from pmmb.execution.base import PortfolioSnapshot
from pmmb.runtime import Heartbeat, write_heartbeat
from pmmb.status import build_status, status_html


def _seed(store: Store):
    store.snapshot_equity(PortfolioSnapshot(
        ts=datetime.now(tz=timezone.utc), cash=800.0, equity=1020.0,
        exposure=220.0, open_positions=1, realized_pnl_today=12.5, peak_equity=1050.0))
    store.event("entry", "LONG test-market")
    with store.tx() as c:
        c.execute("INSERT INTO positions(token_id, condition_id, mode, direction, size,"
                  " avg_price, opened_at, realized_pnl, closed_at) "
                  "VALUES (?,?,?,?,?,?,?,?,NULL)",
                  ("tok-123456789", "cond-1", "paper", "LONG", 50.0, 0.42,
                   int(time.time()) - 7200, 0.0))


def test_build_status_with_data(tmp_path, cfg, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "t.db")
    store = Store(tmp_path / "t.db")
    _seed(store)
    store.close()
    write_heartbeat(Heartbeat(ts=time.time(), cycle=3, equity=1020.0, positions=1))

    st = build_status(cfg)
    assert st["mode"] == "paper"
    assert st["health"]["healthy"] is True
    assert st["bankroll"]["equity"] == 1020.0
    assert len(st["positions"]) == 1
    assert st["positions"][0]["direction"] == "LONG"
    assert st["positions"][0]["age_hours"] > 1
    assert any(e["kind"] == "entry" for e in st["events"])


def test_build_status_without_db(tmp_path, cfg, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "missing.db")
    st = build_status(cfg)
    assert "warning" in st
    assert st["positions"] == []


def test_html_is_self_contained(tmp_path, cfg, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "t2.db")
    Store(tmp_path / "t2.db").close()
    write_heartbeat(Heartbeat(ts=time.time(), cycle=1))
    html = status_html(build_status(cfg), refresh_sec=15)
    assert 'dir="rtl"' in html and "<table" in html
    assert "http://" not in html and "https://" not in html   # אפס משאבים חיצוניים
    assert 'http-equiv="refresh"' in html


def test_health_reflects_stale_heartbeat(tmp_path, cfg, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "t3.db")
    Store(tmp_path / "t3.db").close()
    write_heartbeat(Heartbeat(ts=time.time() - 9999, cycle=1))
    st = build_status(cfg, max_age_sec=300)
    assert st["health"]["healthy"] is False


def test_token_check():
    from pmmb.server import token_ok

    assert token_ok("", "") is True          # אין הגנה
    assert token_ok("abc", "") is True
    assert token_ok("abc", "abc") is True
    assert token_ok("", "abc") is False
    assert token_ok("abd", "abc") is False


def test_status_html_shows_question_unrealized_and_halt_banner(tmp_path, cfg, monkeypatch):
    from pmmb.runtime import write_halt
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "t4.db")
    store = Store(tmp_path / "t4.db")
    with store.tx() as c:
        c.execute(
            "INSERT INTO positions(token_id, condition_id, mode, direction, size,"
            " avg_price, opened_at, stop_price, target_price, question, closed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
            ("tok-abc", "c-1", "paper", "LONG", 100.0, 0.40,
             int(time.time()) - 3600, 0.32, 0.45, "Will Fed cut <rates> & more?"),
        )
    store.insert_ticks([("tok-abc", int(time.time()), 0.46)])
    store.close()
    write_heartbeat(Heartbeat(ts=time.time(), cycle=9, equity=1006.0), tmp_path / "state")
    write_halt("בדיקת דגל", source="phone", state_dir=tmp_path / "state")

    st = build_status(cfg)
    assert st["positions"][0]["mark_price"] == 0.46
    assert st["positions"][0]["unrealized_pnl"] == 6.0
    assert st["health"]["healthy"] is False

    html = status_html(st)
    assert "Will Fed cut &lt;rates&gt; &amp; more?" in html
    assert "+6.00" in html
    assert "בדיקת דגל" in html
    assert "http://" not in html and "https://" not in html
