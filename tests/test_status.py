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


def test_server_get_and_head_endpoints(tmp_path, cfg, monkeypatch):
    import threading
    import urllib.request
    from pmmb.server import serve

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "srv.db")
    Store(cfg.data.db_path).close()
    write_heartbeat(Heartbeat(ts=time.time(), cycle=1, equity=1000.0), tmp_path / "state")

    httpd = serve(cfg, host="127.0.0.1", port=0, token="")
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            assert resp.read() == b""
            assert int(resp.headers["Content-Length"]) > 100

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status.json", timeout=5) as resp:
            assert resp.status == 200
            assert b'"equity": 1000.0' in resp.read()

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:
            assert resp.status == 200

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "PMMB Command Center" in body
            assert "http://" not in body and "https://" not in body

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/lite", timeout=5) as resp:
            assert resp.status == 200

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5) as resp:
            assert resp.status == 200
            assert b'"readiness"' in resp.read()

        # POST halt + resume + backup + reconcile + news-refresh + learn
        import json as _json
        for ep, payload, expect in (
            ("/api/halt", {"reason": "ui-test"}, "עצירת חירום"),
            ("/api/resume", {}, "בוטלה"),
            ("/api/backup", {}, "גיבוי נשמר"),
            ("/api/reconcile", {}, "פערים"),
            ("/api/news-refresh", {}, "רענון שידור חי"),
            ("/api/learn", {"apply": False}, "הערכת אותות חיים"),
        ):
            preq = urllib.request.Request(
                f"http://127.0.0.1:{port}{ep}",
                data=_json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(preq, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                assert resp.status == 200 and data["ok"] is True
                assert expect in data["message"]

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/chart?token=missing", timeout=5) as resp:
            assert resp.status == 200
            ch = _json.loads(resp.read().decode("utf-8"))
            assert ch["token_id"] == "missing" and ch["ticks"] == []

        # סגירת פוזיציית Polymarket ידנית מהממשק דרך /api/positions/close
        from pmmb.execution.base import Portfolio
        from pmmb.models import Fill as _Fill
        st_p = Store(cfg.data.db_path)
        pf_p = Portfolio(1000.0, mode="paper", store=st_p)
        pf_p.apply_fill(_Fill("tok-manual-1", "cond-m1", "BUY", 0.40, 20.0, fee=0.1))
        st_p.insert_ticks([("tok-manual-1", int(time.time()), 0.48)])
        st_p.close()

        req_pm_close = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/positions/close",
            data=_json.dumps({"arm": "polymarket", "key": "tok-manual-1"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_pm_close, timeout=5) as resp:
            d_pm = _json.loads(resp.read().decode("utf-8"))
            assert d_pm["ok"] is True
            assert d_pm["closed"]["key"] == "tok-manual-1"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_blocks_paper_cycle_in_live_mode(tmp_path, cfg, monkeypatch):
    import json as _json
    import threading
    import urllib.error
    import urllib.request
    from pmmb.server import serve

    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.execution.mode = "live"
    cfg.data.db_path = str(tmp_path / "live_ui.db")
    Store(cfg.data.db_path).close()

    httpd = serve(cfg, host="127.0.0.1", port=0, token="")
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/paper-cycle",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("צריך לחסום הרצת paper במצב live")
        except urllib.error.HTTPError as err:
            assert err.code == 403
            assert "paper" in _json.loads(err.read().decode())["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_status_overall_and_recent_trades(tmp_path, cfg, monkeypatch):
    from pmmb.execution.base import Portfolio
    from pmmb.models import Fill

    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "hist.db")
    store = Store(cfg.data.db_path)
    pf = Portfolio(1000.0, mode="paper", store=store)
    f1 = Fill("t1", "c1", "BUY", 0.40, 100.0, fee=0.5)
    pf.apply_fill(f1)
    f2 = Fill("t1", "c1", "SELL", 0.55, 100.0, fee=0.5)
    f2.reason = "יעד"  # type: ignore[attr-defined]
    pf.apply_fill(f2)
    store.close()

    st = build_status(cfg)
    assert st["overall"]["exits"] == 1
    assert st["overall"]["wins"] == 1
    assert st["overall"]["win_rate_pct"] == 100.0
    assert st["overall"]["realized_pnl"] == 14.5
    assert len(st["recent_trades"]) == 1
    html = status_html(st)
    assert "עסקאות סגורות אחרונות" in html
    assert "+14.50" in html


def test_command_center_builder_and_html(tmp_path, cfg, monkeypatch):
    import json as _json
    from pmmb.execution.base import Portfolio
    from pmmb.models import Fill, Signal
    from pmmb.status import build_command_center_data
    from pmmb.ui import command_center_html

    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "cc.db")
    store = Store(cfg.data.db_path)
    pf = Portfolio(1000.0, mode="paper", store=store)
    pf.apply_fill(Fill("t1", "c1", "BUY", 0.35, 100.0, fee=0.25))
    store.record_signal(Signal(
        condition_id="c1", token_id="t1", direction="BUY",
        score=0.72, fair_price=0.39, market_price=0.35, edge=0.04,
        reason="זינוק מתחת לממוצע (z=-2.1)", features={"z": -2.1},
    ))
    now = int(time.time())
    store.insert_ticks([("t1", now - (30 - i) * 3600, 0.45 - 0.002 * i) for i in range(30)])
    store.upsert_news([{
        "id": "n1", "ts": now - 600, "title": "Market news flash",
        "source": "AP", "url": "https://example.com/news", "category": "macro",
        "sentiment": 0.2, "impact": 0.5, "matched_tokens": "t1",
    }])
    store.close()

    rep = tmp_path / "reports"
    rep.mkdir()
    (rep / "walkforward.json").write_text(_json.dumps({
        "engine": "meanrev", "oos_pnl": 284.0, "oos_trades": 73,
        "oos_win_rate": 60.3, "consistency": 1.0, "oos_pnl_ex_top": 16.94,
        "markets_count": 30, "positive_markets": 18, "folds": [],
    }), encoding="utf-8")
    bks = tmp_path / "backups"
    bks.mkdir()
    (bks / "pmmb-20261122-100000.db").write_bytes(b"sqlite")

    data = build_command_center_data(cfg, reports_dir=rep, backups_dir=bks)
    assert len(data["fills"]) == 1
    assert data["signals"][0]["z"] == -2.1
    assert data["analytics"]["walkforward"]["oos_pnl"] == 284.0
    assert data["readiness"]["checks"]
    assert data["backups"][0]["name"] == "pmmb-20261122-100000.db"
    assert data["config"]["signal"]["z_entry"] == cfg.signal.meanrev.z_entry
    assert data["config"]["signal"]["stop_mode"] == cfg.signal.exit.stop_mode
    assert len(data["news"]) == 1
    assert data["charts"]["default"]["ticks"]
    assert data["charts"]["default"]["sma"]
    assert data["telemetry"]["ticks"] == 30
    assert data["telemetry"]["news"] == 1

    for interactive in (True, False):
        html = command_center_html(data, refresh_sec=15 if interactive else 0, interactive=interactive)
        assert "PMMB Command Center" in html
        assert "http://" not in html and "https://" not in html
        assert "Walk-Forward" in html
        assert "סקירה ומסחר" in html
        assert "שווקים וגרפים" in html
        assert "חדשות ולמידה" in html
        assert "תפעול אוטונומי" in html
        assert "רדאר מודיעין שווקים חי" in html
        assert "יומן טייס אוטומטי" in html
        # וידוא עיצוב נקי ללא אימוג'ים קרטוניים
        for em in ("📡", "📊", "🛑", "📰", "🧠", "⚙️"):
            assert em not in html



