"""טסט אינטגרציה לאינג'ין — ללא רשת, עם דאבלים של CLOB/Gamma."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from pmmb.data.clob import Book, Candle
from pmmb.data.store import Store
from pmmb.engine import Engine
from series import trending_series


def _gamma_market(yes_price=0.5, question="Will X happen?"):
    return {
        "conditionId": "0xcond",
        "question": question,
        "slug": "will-x-happen",
        "clobTokenIds": json.dumps(["yes-token", "no-token"]),
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps([str(yes_price), str(1 - yes_price)]),
        "bestBid": yes_price - 0.01,
        "bestAsk": yes_price + 0.01,
        "endDate": (datetime.now(tz=timezone.utc) + timedelta(hours=48)).isoformat().replace("+00:00", "Z"),
        "volume24hr": "250000",
        "liquidityNum": "80000",
        "orderPriceMinTickSize": "0.01",
        "orderMinSize": "5",
        "enableOrderBook": True,
        "acceptingOrders": True,
        "closed": False,
        "archived": False,
        "negRisk": False,
        "events": [],
    }


class FakeGamma:
    def __init__(self, payload=None):
        self.payload = payload or [_gamma_market()]

    def fetch_markets(self, limit=120, min_volume_24h=0.0, only_open=True):
        return self.payload


class FakeClob:
    def __init__(self, prices, bid=None, ask=None):
        self.prices = prices
        self.bid = bid
        self.ask = ask
        self.history_calls = 0

    def get_history(self, token_id, fidelity_min=5, lookback_candles=144, **kw):
        self.history_calls += 1
        return [Candle(ts=1_700_000_000 + i * 300, price=p) for i, p in enumerate(self.prices[-lookback_candles:])]

    def get_book(self, token_id):
        mid = self.prices[-1]
        bid = self.bid if self.bid is not None else round(mid - 0.005, 4)
        ask = self.ask if self.ask is not None else round(mid + 0.005, 4)
        return Book(
            token_id=token_id, best_bid=bid, best_ask=ask,
            bid_size=1000.0, ask_size=1000.0,
            bids=[(bid, 1000.0)], asks=[(ask, 1000.0)],
        )

    def estimate_fill(self, book, side, notional_usdc, max_impact_pct=0.02,
                      allow_partial=False):
        ref = book.best_ask if side == "BUY" else book.best_bid
        return ref, notional_usdc / ref


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "test.db")
    yield s
    s.close()


def _engine(cfg, store, clob, gamma=None, engine="momentum"):
    """ברירת מחדל בטסטים: מנוע המומנטום (הדאטה כאן היא סדרת מגמה)."""
    cfg.signal.engine = engine
    return Engine(cfg, store=store, clob=clob, gamma=gamma or FakeGamma())


def test_engine_opens_position_on_strong_signal(cfg, store):
    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02
    clob = FakeClob(trending_series(0.30, 0.80, n=140))
    eng = _engine(cfg, store, clob)

    stats = eng.run_once()

    assert stats.scanned == 1
    assert stats.signalled >= 1
    assert stats.entries == 1, f"לא נכנסה פוזיציה: {stats.skipped}"
    assert len(eng.portfolio.positions) == 1
    pos = next(iter(eng.portfolio.positions.values()))
    assert pos.size > 0
    assert pos.stop_price is not None and pos.stop_price < pos.avg_price
    assert eng.portfolio.cash < cfg.execution.starting_cash
    # הסיגנל נשמר ל-DB
    rows = store._conn.execute("SELECT COUNT(*) c FROM signals").fetchone()
    assert rows["c"] >= 1


def test_engine_exits_on_stop(cfg, store):
    cfg.signal.min_score = 0.5
    clob = FakeClob(trending_series(0.30, 0.80, n=140))
    eng = _engine(cfg, store, clob)
    eng.run_once()
    assert len(eng.portfolio.positions) == 1
    entry_cash = eng.portfolio.cash

    # המחיר קורס מתחת לסטופ
    clob.prices = trending_series(0.80, 0.45, n=140)
    clob.bid = 0.44
    clob.ask = 0.45
    stats = eng.run_once()

    assert stats.exits == 1
    assert len(eng.portfolio.positions) == 0
    assert eng.portfolio.realized_pnl < 0        # יצאנו בהפסד — זה הסטופ
    assert eng.portfolio.cash != entry_cash
    closed = store.closed_trades()
    assert len(closed) == 1
    assert "סטופ" in (closed[0]["exit_reason"] or "")


def test_engine_respects_max_positions(cfg, store):
    cfg.risk.max_open_positions = 0
    clob = FakeClob(trending_series(0.30, 0.80, n=140))
    eng = _engine(cfg, store, clob)
    stats = eng.run_once()
    assert stats.entries == 0
    assert not eng.portfolio.positions


def test_engine_survives_bad_market(cfg, store):
    class ExplodingClob(FakeClob):
        def get_history(self, *a, **kw):
            raise RuntimeError("boom")

    eng = _engine(cfg, store, ExplodingClob([0.5] * 100))
    stats = eng.run_once()
    assert stats.errors == 1        # לא קורס, רק סופר שגיאה


def test_engine_saves_equity_snapshot(cfg, store):
    clob = FakeClob(trending_series(0.30, 0.80, n=140))
    eng = _engine(cfg, store, clob)
    eng.run_once()
    row = store._conn.execute("SELECT COUNT(*) c FROM equity").fetchone()
    assert row["c"] == 1


def test_engine_works_with_meanrev_engine(cfg, store):
    """אותו אינג'ין, מנוע אחר — הדאטה: יציב ואז צניחה חדה."""
    cfg.signal.meanrev.z_entry = 1.2
    cfg.signal.meanrev.reversion_ratio = 0.5
    cfg.signal.meanrev.z_max = 50.0
    cfg.signal.min_score = 0.3
    cfg.signal.min_edge = 0.0
    cfg.signal.exit.take_profit = 0.05
    cfg.signal.exit.stop_loss = 0.10

    stable = trending_series(0.60, 0.60, n=137, wiggle=0.001)
    prices = stable + [0.55, 0.50, 0.48]
    clob = FakeClob(prices)
    eng = _engine(cfg, store, clob, engine="meanrev")

    stats = eng.run_once()
    assert stats.entries == 1, f"meanrev לא נכנס: {stats.skipped}"
    pos = next(iter(eng.portfolio.positions.values()))
    assert pos.avg_price > 0


def test_engine_prioritizes_higher_quality_candidate_across_markets(cfg, store):
    """כשנותר מקום פנוי אחד, האינג'ין בוחר קודם את השוק עם הציון וה-edge הגבוהים יותר ולא את הראשון ביקום."""
    cfg.signal.engine = "meanrev"
    cfg.signal.meanrev.lookback_candles = 12
    cfg.signal.meanrev.z_entry = 1.2
    cfg.signal.meanrev.z_max = 10.0
    cfg.signal.meanrev.reversion_ratio = 0.6
    cfg.signal.meanrev.rsi_max = 0.0
    cfg.signal.meanrev.max_spread_to_edge = 0.0
    cfg.signal.min_score = 0.3
    cfg.signal.min_edge = 0.005
    cfg.risk.max_open_positions = 1
    cfg.news.enabled = False

    def _raw(cid, slug, ytid, ntid, vol):
        m = _gamma_market(yes_price=0.45, question=f"Will {slug} happen?")
        m["conditionId"] = cid
        m["slug"] = slug
        m["clobTokenIds"] = json.dumps([ytid, ntid])
        m["volume24hr"] = str(vol)
        return m

    raw_a = _raw("0xA", "mkt-a-weak", "yes-a", "no-a", 500_000)   # ראשון ברשימת הנפח אבל אות חלש
    raw_b = _raw("0xB", "mkt-b-strong", "yes-b", "no-b", 100_000) # שני ברשימה אבל אות חזק בהרבה

    base = [0.55 + (0.004 if i % 2 else -0.004) for i in range(44)]
    series_a = base + [0.535, 0.525, 0.520]   # טבילה מתונה (edge קטן)
    series_b = base + [0.500, 0.460, 0.430]   # טבילה עמוקה (edge וציון גבוהים)

    class _MultiClob:
        def get_history(self, tid, **_kw):
            pxs = series_a if tid == "yes-a" else series_b
            return [Candle(ts=1_700_000_000 + i * 3600, price=p) for i, p in enumerate(pxs)]

        def get_book(self, tid):
            px = series_a[-1] if tid == "yes-a" else series_b[-1]
            bid, ask = round(px - 0.005, 4), round(px + 0.005, 4)
            return Book(token_id=tid, best_bid=bid, best_ask=ask, bid_size=1000, ask_size=1000,
                        bids=[(bid, 1000)], asks=[(ask, 1000)])

        def estimate_fill(self, bk, side, notional, **_kw):
            ref = bk.best_ask if side == "BUY" else bk.best_bid
            return ref, notional / ref

    eng = Engine(cfg, store=store, clob=_MultiClob(), gamma=FakeGamma([raw_a, raw_b]))
    stats = eng.run_once()
    assert stats.entries == 1
    assert "yes-b" in eng.portfolio.positions
    assert "yes-a" not in eng.portfolio.positions


def test_empty_book_imbalance_none_and_live_sell_size_clamp(cfg, store, monkeypatch):
    """ספר ללא רמות עומק (imbalance=None) אינו מפיל את הסריקה, ומכירה ב-live מתאימה עצמה ליתרת הטוקן."""
    from pmmb.engine import CycleStats
    from pmmb.models import Fill, Market, Position, Signal, utcnow

    cfg.news.enabled = False

    class _EmptyDepthClob:
        def get_history(self, tid, **_kw):
            base = [0.50 + (0.002 if i % 2 else -0.002) for i in range(44)]
            return [Candle(ts=1_700_000_000 + i * 3600, price=p) for i, p in enumerate(base)]

        def get_book(self, tid):
            # best_bid/ask קיימים אבל אין רמות bids/asks -> imbalance() == None
            return Book(token_id=tid, best_bid=0.49, best_ask=0.51, bid_size=100, ask_size=100, bids=[], asks=[])

    eng = Engine(cfg, store=store, clob=_EmptyDepthClob(), gamma=FakeGamma([_gamma_market(yes_price=0.50)]))
    stats = eng.run_once()
    assert stats.errors == 0
    rows = store.recent_market_intel(limit=5)
    assert len(rows) == 1

    # כעת בודקים הקטנת גודל SELL ב-live כאשר conditional_balance נמוך במעט מ-pos.size
    cfg.execution.mode = "live"
    captured_orders = []

    class _LiveStubBroker:
        mode = "live"

        def conditional_balance(self, _tid):
            return 39.974

        def execute(self, order, **_kw):
            captured_orders.append(order)
            return Fill(order.token_id, order.condition_id, order.side, order.price, order.size)

    eng_live = Engine(cfg, store=store, clob=_EmptyDepthClob(), broker=_LiveStubBroker(),
                      gamma=FakeGamma([_gamma_market(yes_price=0.50)]))
    pos = Position(
        token_id="yes-tok", condition_id="0xcond", direction="LONG",
        size=40.0, avg_price=0.40, stop_price=0.30, target_price=0.45,
        opened_at=utcnow(), question="Live sell clamp?",
    )
    eng_live.portfolio.restore([pos], 500.0)
    mk = Market.from_gamma(_gamma_market(yes_price=0.49))
    assert mk is not None
    bk = Book(token_id="yes-tok", best_bid=0.46, best_ask=0.47, bid_size=100, ask_size=100,
              bids=[(0.46, 100)], asks=[(0.47, 100)])
    eng_live._handle_exit(mk, Signal("0xcond", "yes-tok", "FLAT", 0.0, 0.5, 0.46, 0.0, ""), bk, CycleStats())
    assert len(captured_orders) == 1
    assert captured_orders[0].size == 39.97


def test_server_manager_throttles_rss_refresh_on_stream_ticks(cfg, tmp_path, monkeypatch):
    """לולאת השידור החי (60s) אינה שולפת RSS מחדש אם טרם חלף refresh_interval_sec, אך רענון ידני כן."""
    from pmmb.server import _TraderManager
    import pmmb.server as srv_mod

    cfg.data.db_path = str(tmp_path / "srv.db")
    monkeypatch.setenv("PMMB_DISABLE_LIVE_NEWS", "0")
    calls = []

    def _fake_refresh(_store, **_kw):
        calls.append(1)
        return []

    class _QuietHttp:
        def get(self, *_a, **_kw):
            return []

    class _QuietClob:
        def get_book(self, _tid):
            return None

        def get_history(self, _tid, **_kw):
            return []

    monkeypatch.setattr(srv_mod, "refresh_news_to_store", _fake_refresh)
    mgr = _TraderManager(cfg)
    monkeypatch.setattr(mgr, "_build_clients", lambda **_kw: (_QuietHttp(), _QuietClob()))
    mgr.last_news_ts = int(srv_mod.time.time())

    # קריאת stream שוטפת (include_markets=False) לא מושכת RSS מחדש לפני שעבר המרווח
    mgr.refresh_news_and_stream(include_markets=False)
    assert len(calls) == 0

    # קריאה ידנית (include_markets=True) כן מרעננת מיד
    mgr.refresh_news_and_stream(include_markets=True)
    assert len(calls) == 1



def test_engine_denies_entry_when_shared_portfolio_gate_rejects(monkeypatch, cfg, store):
    from types import SimpleNamespace

    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02
    cfg.news.enabled = False
    calls = []

    def _deny(_store, _cfg, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(approved=False, reason="blocked by test shared budget")

    monkeypatch.setattr("pmmb.engine.evaluate_unified_entry", _deny)
    clob = FakeClob(trending_series(0.30, 0.80, n=140))
    eng = _engine(cfg, store, clob)
    stats = eng.run_once()

    assert calls and calls[0]["arm"] == "polymarket"
    assert stats.entries == 0
    assert not eng.portfolio.positions
    assert any("תיק מאוחד" in reason or "shared" in reason.lower() for reason in stats.skipped)
