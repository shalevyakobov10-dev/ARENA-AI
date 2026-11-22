"""בדיקות אוטופיילוט (תפעול עצמוני מלא), מודיעין שווקים מורחב וזיהוי קפיצות נפח."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from pmmb.autopilot import (
    monitor_open_positions_news,
    run_auto_backup,
    run_auto_reconcile,
    run_auto_reports,
)
from pmmb.data.clob import Book, Candle
from pmmb.data.store import Store
from pmmb.engine import Engine
from pmmb.models import Fill, Market, Position
from pmmb.server import make_handler


class _Gamma:
    def __init__(self, raw_markets):
        self._raw = raw_markets

    def fetch_markets(self, **_kw):
        return list(self._raw)


class _FakeClob:
    def __init__(self, books, histories):
        self._books = books
        self._histories = histories

    def get_book(self, tid):
        return self._books.get(tid)

    def get_history(self, tid, **_kw):
        return self._histories.get(tid, [])

    def get_resolution(self, _cid):
        return None


def test_market_volume_ratio_from_gamma():
    m = Market.from_gamma({
        "conditionId": "c1",
        "question": "Will X happen?",
        "clobTokenIds": ["y1", "n1"],
        "outcomePrices": ["0.5", "0.5"],
        "volume24hr": 140_000.0,
        "volume1wk": 140_000.0,   # ממוצע יומי שבועי = 20,000 => יחס 7.0x
        "liquidityNum": 50_000.0,
    })
    assert m.volume_1wk == 140_000.0
    assert m.volume_ratio == 7.0


def test_engine_populates_market_intel_and_blocks_volume_spike(tmp_path, cfg, monkeypatch):
    import math as _math

    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "eng.db")
    cfg.news.volume_spike_ratio = 6.0

    # שוק עם קפיצת נפח פי 7 מהממוצע השבועי וירידת מחיר חדה (z ≈ -2.6) -> אמור להיחסם ב-CATALYST_BLOCK
    raw_mk = {
        "conditionId": "c_spike",
        "question": "Will CPI surprise this week?",
        "slug": "cpi-surprise",
        "clobTokenIds": json.dumps(["y_spike", "n_spike"]),
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.46", "0.54"]),
        "bestBid": 0.455,
        "bestAsk": 0.465,
        "volume24hr": "140000",
        "volume1wk": "140000",
        "liquidityNum": "60000",
        "endDate": (datetime.now(tz=timezone.utc) + timedelta(days=5)).isoformat().replace("+00:00", "Z"),
        "orderPriceMinTickSize": "0.01",
        "orderMinSize": "5",
        "enableOrderBook": True,
        "acceptingOrders": True,
        "closed": False,
        "archived": False,
        "negRisk": False,
        "events": [],
    }
    now = int(time.time())
    prices = [0.55 + 0.014 * _math.sin(i * 0.9) for i in range(44)] + [0.51, 0.48, 0.46]
    candles = [Candle(ts=now - (len(prices) - i) * 3600, price=round(p, 4)) for i, p in enumerate(prices)]
    book = Book(
        token_id="y_spike", best_bid=0.455, best_ask=0.465,
        bid_size=300.0, ask_size=300.0,
        bids=[(0.455, 300.0)], asks=[(0.465, 300.0)],
    )

    eng = Engine(cfg, gamma=_Gamma([raw_mk]), clob=_FakeClob({"y_spike": book}, {"y_spike": candles}))
    st = eng.run_once()
    intel = eng.store.recent_market_intel()
    eng.close()

    assert st.entries == 0
    assert st.skipped.get("חדשות: תזוזה מונעת ידיעה") == 1
    assert len(intel) == 1
    assert intel[0]["volume_ratio"] == 7.0
    assert intel[0]["status"] == "CATALYST_BLOCK"
    assert intel[0]["bid_depth"] > 0


def test_autopilot_reconcile_backup_reports_and_position_news(tmp_path, cfg, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "ap.db")
    store = Store(cfg.data.db_path)

    # יצירת פער מלאכותי ב-DB (מילוי בלי עדכון position) ווידוא תיקון אוטומטי
    store.record_fill(Fill("t1", "c1", "BUY", 0.50, 20.0, fee=0.05), "paper")
    res_rec = run_auto_reconcile(cfg, store)
    assert res_rec["ok"] and res_rec["fixed"]

    res_bk = run_auto_backup(cfg, store, backups_dir=tmp_path / "backups")
    assert res_bk["ok"]
    assert (tmp_path / "backups").exists()

    res_rep = run_auto_reports(cfg, store, reports_dir=tmp_path / "reports", backups_dir=tmp_path / "backups")
    assert res_rep["ok"]
    assert (tmp_path / "reports" / "readiness.md").exists()

    # בדיקת ניטור חדשות לפוזיציה פתוחה ללא ספאם כפול
    now = int(time.time())
    pos = Position(
        token_id="t_pos", condition_id="c_pos", direction="LONG",
        size=30.0, avg_price=0.50, opened_at=datetime.now(tz=timezone.utc) - timedelta(hours=3),
        question="Will ACME Airlines declare bankruptcy?",
    )
    arts = [
        {"ts": now - 600, "title": "ACME Airlines faces emergency bankruptcy filing after crash", "sentiment": -0.7, "impact": 0.9},
        {"ts": now - 300, "title": "Trading halted as ACME Airlines bankruptcy deepens", "sentiment": -0.8, "impact": 0.85},
    ]
    seen: set[str] = set()
    alerts1 = monitor_open_positions_news([pos], arts, cfg, store, seen_alerts=seen)
    alerts2 = monitor_open_positions_news([pos], arts, cfg, store, seen_alerts=seen)
    runs = store.recent_autopilot_runs(limit=10)
    store.close()

    assert len(alerts1) == 1
    assert len(alerts2) == 0
    assert {r["task"] for r in runs} >= {"reconcile", "backup", "reports"}


def test_server_autopilot_maintain_endpoint(tmp_path, cfg, monkeypatch):
    import http.client
    import threading
    from http.server import ThreadingHTTPServer

    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "srv.db")
    Store(cfg.data.db_path).close()

    handler = make_handler(cfg, max_age_sec=300, refresh_sec=15, token="")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/api/autopilot/maintain", body="{}", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["ok"] is True
        assert "reconcile" in body
        assert "backup" in body
        assert "reports" in body
    finally:
        httpd.shutdown()
        httpd.server_close()
