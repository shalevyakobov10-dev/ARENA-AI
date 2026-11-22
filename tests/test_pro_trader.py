"""בדיקות לטכניקות מסחר מקצועיות, דופק חדשות גלובלי ויציאת הגנה יזומה."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta, timezone

from pmmb.data.clob import Book, Candle
from pmmb.data.news import NewsArticle, compute_global_pulse, match_market_news
from pmmb.engine import Engine
from pmmb.models import Fill, Market, PortfolioSnapshot, Signal
from pmmb.risk.manager import RiskManager
from pmmb.signals.meanrev import MeanReversionEngine


def _market_fixture() -> Market:
    return Market(
        condition_id="cid-pro",
        question="Will ACME launch next year?",
        slug="acme-launch",
        yes_token_id="tok-yes",
        no_token_id="tok-no",
        yes_price=0.46,
        no_price=0.54,
        spread=0.01,
        volume_24h=120_000.0,
        liquidity=50_000.0,
        end_date=datetime.now(tz=timezone.utc) + timedelta(days=10),
    )


def test_meanrev_rsi_confluence_and_spread_to_edge_filter(cfg):
    cfg.signal.engine = "meanrev"
    cfg.signal.meanrev.lookback_candles = 24
    cfg.signal.meanrev.z_entry = 1.8
    cfg.signal.meanrev.z_max = 10.0
    cfg.signal.meanrev.reversion_ratio = 0.55
    cfg.signal.meanrev.rsi_max = 45.0
    cfg.signal.meanrev.max_spread_to_edge = 1.1
    cfg.signal.min_score = 0.55
    cfg.signal.min_edge = 0.005

    mk = _market_fixture()
    eng = MeanReversionEngine(cfg.signal)

    # 1. תבנית צניחה מובהקת עם RSI נמוך ו-Spread צר -> סטאפ A / A+ מאושר
    prices = [0.55 + 0.014 * math.sin(i * 0.9) for i in range(54)] + [0.51, 0.48, 0.46]
    sig_ok = eng.evaluate(mk, prices, market_price=0.46, spread=0.01)
    assert sig_ok.direction == "LONG", sig_ok.reason
    assert sig_ok.features["setup_tier"] in ("A", "A+")
    assert sig_ok.features["rsi"] <= 45.0

    # 2. ספרד יקר יחסית ל-edge -> נדחה ("ספרד יקר יחסית ל-edge")
    sig_sp = eng.evaluate(mk, prices, market_price=0.46, spread=0.045)
    assert sig_sp.direction == "FLAT"
    assert "edge" in sig_sp.reason


def test_risk_manager_drawdown_throttling(cfg):
    cfg.risk.drawdown_throttle_pct = 0.05
    cfg.risk.max_drawdown_pct = 0.25
    cfg.risk.kelly_fraction = 0.50
    cfg.risk.max_position_pct = 0.20
    cfg.risk.risk_per_trade_pct = 0.04
    cfg.signal.exit.stop_mode = "abs"
    cfg.signal.exit.take_profit = 0.05
    cfg.signal.exit.stop_loss = 0.08

    mk = _market_fixture()
    sig = Signal(
        condition_id=mk.condition_id, token_id=mk.yes_token_id,
        direction="LONG", score=0.8, fair_price=0.58, market_price=0.46,
        edge=0.08, reason="test",
    )
    rm = RiskManager(cfg)

    snap_ok = PortfolioSnapshot(
        cash=1000.0, equity=1000.0, exposure=0.0,
        open_positions=0, realized_pnl_today=0.0, peak_equity=1010.0,
    )
    dec_full = rm.evaluate_entry(sig, mk, snap_ok, price=0.46, tick=0.01, min_order_size=5.0)

    snap_dd = PortfolioSnapshot(
        cash=930.0, equity=930.0, exposure=0.0,
        open_positions=0, realized_pnl_today=0.0, peak_equity=1000.0,  # drawdown = 7% -> throttle 0.65x
    )
    dec_th = rm.evaluate_entry(sig, mk, snap_dd, price=0.46, tick=0.01, min_order_size=5.0)

    assert dec_full.approved and dec_th.approved
    assert dec_th.size < dec_full.size
    assert "DD throttle" in dec_th.reason


def test_active_news_emergency_exit_closes_open_position(tmp_path, cfg, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    cfg.data.db_path = str(tmp_path / "emg.db")
    cfg.news.enabled = True
    cfg.news.emergency_exit_impact = 0.80
    cfg.news.emergency_exit_sentiment = -0.50

    now = int(time.time())
    raw_mk = {
        "conditionId": "c_emg",
        "question": "Will NovaTech close merger this quarter?",
        "slug": "novatech-merger",
        "clobTokenIds": json.dumps(["y_emg", "n_emg"]),
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.50", "0.50"]),
        "bestBid": 0.49,
        "bestAsk": 0.51,
        "volume24hr": "90000",
        "liquidityNum": "30000",
        "endDate": (datetime.now(tz=timezone.utc) + timedelta(days=12)).isoformat().replace("+00:00", "Z"),
        "orderPriceMinTickSize": "0.01",
        "orderMinSize": "5",
        "enableOrderBook": True,
        "acceptingOrders": True,
        "closed": False,
        "archived": False,
        "negRisk": False,
        "events": [],
    }
    prices = [0.50] * 40
    candles = [Candle(ts=now - (40 - i) * 3600, price=p) for i, p in enumerate(prices)]
    book = Book(token_id="y_emg", best_bid=0.49, best_ask=0.51, bid_size=300.0, ask_size=300.0,
                bids=[(0.49, 300.0)], asks=[(0.51, 300.0)])

    class _Gamma:
        def fetch_markets(self, **_kw):
            return [raw_mk]

    class _Clob:
        def get_book(self, _t):
            return book

        def get_history(self, _t, **_kw):
            return candles

        def estimate_fill(self, bk, side, notional, **_kw):
            px = bk.best_bid if side == "SELL" else bk.best_ask
            return px, notional / max(px, 0.01)

        def get_resolution(self, _c):
            return None

    class _ShockNews:
        def fetch_live(self, *_a, **_kw):
            return [NewsArticle(
                id="shock1", ts=now - 120,
                title="Breaking: Regulators block NovaTech merger amid antitrust probe",
                source="CNBC", category="markets", sentiment=-0.85, impact=0.92,
            )]

    eng = Engine(cfg, gamma=_Gamma(), clob=_Clob(), news_client=_ShockNews())
    eng.portfolio.apply_fill(Fill("y_emg", "c_emg", "BUY", 0.50, 40.0, fee=0.05))
    pos = eng.portfolio.position_for("y_emg")
    pos.condition_id = "c_emg"
    pos.question = raw_mk["question"]
    pos.stop_price, pos.target_price = 0.42, 0.55   # המחיר (0.49) עוד לא נגע בסטופ!
    eng.store.upsert_position(pos, "paper")

    st = eng.run_once()
    remaining = len(eng.portfolio.positions)
    eng.close()

    assert st.exits == 1
    assert remaining == 0


def test_global_pulse_aggregation():
    arts = [
        {"sentiment": -0.6, "impact": 0.9, "source": "BBC World", "category": "geopolitics"},
        {"sentiment": -0.4, "impact": 0.6, "source": "Al Jazeera", "category": "geopolitics"},
        {"sentiment": 0.2, "impact": 0.2, "source": "CNBC", "category": "markets"},
    ]
    pulse = compute_global_pulse(arts)
    assert pulse["total"] == 3
    assert pulse["sources"] == 3
    assert pulse["catalysts"] == 2
    assert pulse["regime"] == "סערה שלילית"
    assert pulse["by_category"]["geopolitics"] == 2


def test_news_matching_rejects_generic_false_positives():
    now = int(time.time())
    arts = [
        NewsArticle(
            id="il1", ts=now - 60,
            title="Israel Election 2026 Live Updates: Netanyahu race to build government",
            impact=0.80, sentiment=0.1,
        ),
        NewsArticle(
            id="tw1", ts=now - 60,
            title="Taiwan DPP rallies ahead of municipal vote in Taipei",
            impact=0.60, sentiment=0.2,
        ),
    ]
    m = match_market_news(
        "Will the Democratic Progressive Party (DPP) win the most head of local government elections in the 2026 Taiwan local elections?",
        arts, now_ts=now, window_hours=24.0, min_articles=1, impact_threshold=0.5,
    )
    assert m.article_count == 1
    assert "Taiwan" in m.latest_title
