"""בדיקות מלאות לזרוע החוזים התמידיים (PERPS ×50) והשילוב ב-Command Center."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from pmmb.config import Config, PerpsConfig
from pmmb.data.store import Store
from pmmb.perps.backtest import run_perp_portfolio_backtest, run_perp_walkforward
from pmmb.perps.broker import LivePerpBroker, PaperPerpBroker, PerpsLiveDisabled
from pmmb.perps.engine import PerpEngine
from pmmb.perps.learning import run_perp_self_learning_cycle
from pmmb.perps.models import PerpBook, PerpCandle, PerpInstrument, PerpOrder, PerpSignal
from pmmb.perps.risk import PerpRiskManager, calc_liquidation_price
from pmmb.perps.signals import ProMultiRegimeEngine, assess_perps_news
from pmmb.server import _TraderManager, make_handler
from pmmb.status import build_command_center_data, build_perps_status
from pmmb.ui import command_center_html


def _mk_candles(n: int = 160, *, base: float = 100.0, mode: str = "mr_long") -> list[PerpCandle]:
    cs: list[PerpCandle] = []
    t0 = 1_760_000_000
    px = base
    for i in range(n):
        ts = t0 + i * 3600
        if mode == "mr_long":
            # שוק מדשדש ואז ירידה חדה + נר היפוך ירוק בסוף
            if i < n - 6:
                px = base + 0.5 * math.sin(i * 0.4)
                o, c = px - 0.1, px + 0.1
                h, l = max(o, c) + 0.25, min(o, c) - 0.25
            elif i < n - 1:
                px -= 0.7
                o, c = px + 0.4, px
                h, l = o + 0.1, c - 0.1
            else:
                o = px - 0.1
                c = px + 0.45
                px = c
                h, l = c + 0.12, o - 0.12
        elif mode == "trend_up":
            px = base + i * 0.4
            o, c = px - 0.25, px + 0.25
            if i == n - 1:
                # Pullback חזרה קרוב ל-EMA20 וסגירה ירוקה
                l = px - 2.6
                o = px - 0.8
                c = px + 0.35
                h = c + 0.15
            else:
                h, l = c + 0.2, o - 0.2
        else:
            px = base + 0.3 * math.sin(i * 0.3)
            o, c = px - 0.1, px + 0.1
            h, l = c + 0.15, o - 0.15
        cs.append(PerpCandle(ts=ts, open=round(o, 4), high=round(h, 4), low=round(l, 4), close=round(c, 4), volume=1000.0))
    return cs


def test_perps_config_defaults():
    cfg = Config.load()
    assert cfg.perps.risk.max_leverage == 50.0
    assert cfg.perps.risk.liquidation_buffer_mult == 2.2
    assert cfg.perps.risk.sl_atr_mult == 1.5
    assert cfg.perps.risk.tp_atr_mult == 2.6
    assert cfg.perps.risk.max_positions_per_direction == 4
    assert cfg.perps.exchange.max_assets == 16
    assert "okx" in cfg.perps.exchange.enabled_exchanges
    assert "hyperliquid" in cfg.perps.exchange.enabled_exchanges


def test_dynamic_leverage_50x_and_liquidation_guard():
    pc = PerpsConfig()
    rm = PerpRiskManager(pc)
    inst_100x = PerpInstrument(
        symbol="BTC", exchange="okx", exchange_symbol="BTC-USDT-SWAP",
        max_leverage=100.0, mark_price=90000.0, mmr=0.004,
    )
    # תרחיש 1: ATR הדוק (0.35% => SL=0.595%) וציון A+ -> צריך לאשר עד 50x וה-SL לפני ה-LIQ
    sig_tight = PerpSignal(
        symbol="BTC", exchange="okx", direction="LONG", regime="RANGE", strategy="meanrev",
        score=0.85, tier="A+", price=90000.0, atr=315.0,
        stop_price=90000.0 * (1 - 0.00595), take_profit_price=90000.0 * (1 + 0.0105),
        recommended_leverage=50.0, reason="A+ tight",
    )
    dec = rm.evaluate_entry(sig_tight, inst_100x, equity=1000.0, free_cash=1000.0, open_positions=[])
    assert dec.approved
    assert 35.0 <= dec.leverage <= 50.0
    # חובת בטיחות קריטית: מחיר Stop Loss חייב להישאר מעל מחיר הליקווידציה (ל-LONG)
    assert dec.stop_price > dec.liquidation_price

    # תרחיש 2: תנודתיות גבוהה (ATR=2.5% => SL=4.25%) -> המינוף חייב להתכווץ אוטומטית כדי שה-SL יהיה לפני ה-LIQ!
    sig_wide = PerpSignal(
        symbol="SOL", exchange="okx", direction="LONG", regime="RANGE", strategy="meanrev",
        score=0.82, tier="A+", price=200.0, atr=5.0,
        stop_price=200.0 * (1 - 0.0425), take_profit_price=200.0 * (1 + 0.075),
        recommended_leverage=10.5, reason="wide vol",
    )
    dec_w = rm.evaluate_entry(sig_wide, inst_100x, equity=1000.0, free_cash=1000.0, open_positions=[])
    assert dec_w.approved
    assert dec_w.leverage <= 12.0
    assert dec_w.stop_price > dec_w.liquidation_price

    # SHORT liquidation formula
    liq_s = calc_liquidation_price("SHORT", 100.0, 20.0, mmr=0.005)
    assert round(liq_s, 2) == 104.50


def test_signal_engine_meanrev_and_news_block():
    pc = PerpsConfig()
    eng = ProMultiRegimeEngine(pc)
    inst = PerpInstrument(
        symbol="BTC", exchange="okx", exchange_symbol="BTC-USDT-SWAP",
        max_leverage=100.0, mark_price=96.0, funding_1h=-0.0002,
    )
    candles = _mk_candles(140, base=100.0, mode="mr_long")
    inst.mark_price = candles[-1].close
    book = PerpBook(
        symbol="BTC", exchange="okx", best_bid=candles[-1].close * 0.9999,
        best_ask=candles[-1].close * 1.0001,
        bids=[(candles[-1].close * 0.9999, 50.0)],
        asks=[(candles[-1].close * 1.0001, 20.0)],
    )
    sig = eng.evaluate(inst, candles, book=book)
    assert sig.direction == "LONG"
    assert sig.strategy == "meanrev"
    assert sig.recommended_leverage >= 2.0

    # בדיקת חסימת חדשות מאקרו קשות
    bad_news = [{
        "ts": candles[-1].ts,
        "title": "Bitcoin major exchange hack and SEC emergency freeze",
        "impact": 0.95,
        "sentiment": -0.80,
    }]
    sig_blocked = eng.evaluate(inst, candles, book=book, news_articles=bad_news)
    assert sig_blocked.direction == "FLAT"
    assert "חדשות" in sig_blocked.reason


def test_live_broker_guards(monkeypatch):
    pc = PerpsConfig(mode="paper")
    try:
        LivePerpBroker(pc)
        assert False, "צריך לדרוש mode=live"
    except PerpsLiveDisabled:
        pass
    pc.mode = "live"
    monkeypatch.delenv("PMMB_PERPS_LIVE_CONFIRM", raising=False)
    try:
        LivePerpBroker(pc)
        assert False, "צריך לדרוש אישור סביבה"
    except PerpsLiveDisabled:
        pass


class _FakePerpExchange:
    def __init__(self, candles: list[PerpCandle]) -> None:
        self.candles = candles

    def scan(self) -> list[PerpInstrument]:
        px = self.candles[-1].close
        return [PerpInstrument(
            symbol="BTC", exchange="okx", exchange_symbol="BTC-USDT-SWAP",
            max_leverage=100.0, mark_price=px, best_bid=px * 0.9999, best_ask=px * 1.0001,
            volume_24h_usd=500_000_000.0, open_interest_usd=200_000_000.0, funding_1h=-0.0001,
        )]

    def get_candles(self, inst, interval="1h", lookback=160):
        return self.candles[-lookback:]

    def get_book(self, inst, levels=12):
        px = self.candles[-1].close
        return PerpBook(
            symbol=inst.symbol, exchange=inst.exchange,
            best_bid=px * 0.9999, best_ask=px * 1.0001,
            bids=[(px * 0.9999, 10.0)], asks=[(px * 1.0001, 5.0)],
        )


def test_perp_engine_cycle_persistence_and_ui(tmp_path):
    cfg = Config.load()
    cfg.data.db_path = str(tmp_path / "perps.db")
    cfg.perps.mode = "paper"

    cs = _mk_candles(140, base=100.0, mode="mr_long")
    ex = _FakePerpExchange(cs)
    eng = PerpEngine(cfg, exchange=ex)
    st = eng.run_once()
    assert st.scanned == 1
    assert st.entries == 1
    assert "BTC" in eng.positions
    pos = eng.positions["BTC"]
    assert 2.0 <= pos.leverage <= 50.0
    assert pos.stop_price > pos.liquidation_price
    eng.close()

    # שחזור מ-DB ושמירת נתונים
    eng2 = PerpEngine(cfg, exchange=ex)
    assert "BTC" in eng2.positions
    assert eng2.positions["BTC"].margin_used == pos.margin_used
    eng2.close()

    # Command Center Payload + HTML
    store = Store(cfg.data.db_path)
    try:
        ps = build_perps_status(cfg, store)
        assert len(ps["positions"]) == 1
        assert ps["avg_leverage"] == pos.leverage
    finally:
        store.close()

    cc = build_command_center_data(cfg)
    assert "perps" in cc
    assert len(cc["perps"]["positions"]) == 1
    html = command_center_html(cc)
    assert "PERPS ×50" in html
    assert "tab-perps" in html


def test_perps_server_api_endpoints(tmp_path):
    import io
    import threading
    from http.server import ThreadingHTTPServer
    import urllib.request

    cfg = Config.load()
    cfg.data.db_path = str(tmp_path / "srv.db")
    cfg.perps.mode = "paper"
    trader = _TraderManager(cfg)
    handler = make_handler(cfg, max_age_sec=300, refresh_sec=0, token="", trader=trader)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/perps/toggle",
            data=json.dumps({"enabled": False}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode())
            assert d["ok"] is True
            assert d["enabled"] is False
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/perps/chart?symbol=BTC", timeout=5) as resp:
            ch = json.loads(resp.read().decode())
            assert ch["symbol"] == "BTC"
    finally:
        srv.shutdown()
        srv.server_close()


def test_perps_global_halt_and_entry_candle_protection(tmp_path, monkeypatch):
    from pmmb.runtime import clear_halt, write_halt

    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PMMB_DISABLE_LIVE_NEWS", "1")
    cfg = Config.load()
    cfg.data.db_path = str(tmp_path / "halt.db")
    cfg.perps.mode = "paper"

    cs = _mk_candles(140, base=100.0, mode="mr_long")
    ex = _FakePerpExchange(cs)

    write_halt("בדיקת חירום", source="test", state_dir=tmp_path / "state")
    try:
        eng = PerpEngine(cfg, exchange=ex)
        st = eng.run_once()
        assert st.entries == 0
        assert len(eng.positions) == 0
        eng.close()
    finally:
        clear_halt(state_dir=tmp_path / "state")

    # כניסה רגילה, ואז בנר פתוח חדש עם wick עמוק (70) אבל מחיר נוכחי תקין (97) -> הפוזיציה שורדת!
    eng2 = PerpEngine(cfg, exchange=ex)
    st2 = eng2.run_once()
    assert st2.entries == 1
    pos = eng2.positions["BTC"]
    # מקבע את זמן הפתיחה בתוך חלון הנר האחרון (כמו במציאות!) עם wick של 70.0 שהיה לפני הכניסה
    future_ts = int(pos.opened_at.timestamp()) - 300
    cs[-1] = PerpCandle(ts=future_ts, open=97.0, high=101.0, low=70.0, close=pos.entry_price, volume=1000.0)
    st3 = eng2.run_once()
    assert st3.exits == 0
    assert "BTC" in eng2.positions
    eng2.close()


def test_reconcile_perps_telegram_and_round_step(tmp_path):
    from pmmb.perps.broker import round_step
    from pmmb.reconcile import reconcile_perps
    from pmmb.telegram_bot import TelegramController

    assert round_step(1.23999, 0.01) == 1.23
    assert round_step(0.0567, 0.001) == 0.056

    cfg = Config.load()
    cfg.data.db_path = str(tmp_path / "rec.db")
    cfg.perps.mode = "paper"

    cs = _mk_candles(140, base=100.0, mode="mr_long")
    eng = PerpEngine(cfg, exchange=_FakePerpExchange(cs))
    eng.run_once()
    eng.close()

    store = Store(cfg.data.db_path)
    try:
        rep = reconcile_perps(store, mode="paper", starting_cash=1000.0, fix=False)
        assert rep.clean
        # כופה פער במזומן ה-snapshot ובודק תיקון אוטומטי
        store._conn.execute("UPDATE perp_equity SET cash = 500.0")
        store._conn.commit()
        rep_bad = reconcile_perps(store, mode="paper", starting_cash=1000.0, fix=False)
        assert not rep_bad.clean
        rep_fix = reconcile_perps(store, mode="paper", starting_cash=1000.0, fix=True)
        assert rep_fix.fixes_applied >= 1
        assert reconcile_perps(store, mode="paper", starting_cash=1000.0, fix=False).clean
    finally:
        store.close()

    tg = TelegramController(cfg, token="t", chat_id="1", state_dir=tmp_path / "st")
    out_p = tg.handle_text("/perps")
    assert "PERPS" in out_p
    assert "BTC" in out_p
    out_s = tg.handle_text("/status")
    assert "PERPS" in out_s


def test_continuous_news_alpha_and_perp_signal_learning(tmp_path):
    from pmmb.data.news import evaluate_news_alpha
    from pmmb.perps.learning import evaluate_perp_live_signals
    from pmmb.perps.models import PerpSignal

    db = tmp_path / "learn_cont.db"
    store = Store(db)
    now = int(datetime.now(tz=timezone.utc).timestamp())
    t0 = now - 6 * 3600
    try:
        # נרות BTC שעתיים עם עלייה חדה של +4% אחרי חדשה חיובית + אות LONG
        candles = []
        for i in range(10):
            ts_c = t0 + i * 3600
            px = 60000.0 if i <= 1 else 62400.0
            candles.append((ts_c, px, px + 50, px - 50, px, 1000.0))
        store.insert_perp_candles("BTC", "okx", "1h", candles)

        sig = PerpSignal(
            symbol="BTC", exchange="okx", direction="LONG", strategy="pullback",
            regime="TREND_UP", score=0.82, tier="A+", price=60000.0,
            stop_price=59100.0, take_profit_price=61560.0,
            atr=600.0, recommended_leverage=25.0,
            reason="pullback", features={"z": -1.9, "news_impact": 0.7},
            ts=datetime.fromtimestamp(t0, tz=timezone.utc),
        )
        store.record_perp_signal(sig)
        # 5 כתבות CoinDesk חיוביות ב-t0 -> בודק שמדידת News Alpha לומדת ויוצרת מכפיל אמינות
        arts = [
            {
                "id": f"art-{i}", "ts": t0, "source": "CoinDesk", "category": "crypto",
                "title": f"Bitcoin spot ETF inflow rally #{i}", "url": f"https://ex/{i}",
                "sentiment": 0.75, "impact": 0.65, "matched_tokens": "",
            }
            for i in range(5)
        ]
        store.upsert_news(arts)

        n_perp = evaluate_perp_live_signals(store, now_ts=now)
        n_news = evaluate_news_alpha(store, now_ts=now)
        assert n_perp >= 1
        assert n_news == 5

        ps_stats = store.perp_signal_outcome_stats()
        assert ps_stats["total_evaluated"] >= 1
        assert ps_stats["overall"]["hit_pct"] == 100.0

        na_stats = store.news_alpha_stats()
        assert na_stats["total_measured"] == 5
        assert na_stats["directional_hit_pct"] == 100.0
        rel = store.news_source_reliability(min_samples=4)
        assert rel["CoinDesk"] > 1.0
    finally:
        store.close()


def test_perp_backtest_walkforward_and_learning(tmp_path):
    pc = PerpsConfig()
    cs = _mk_candles(360, base=100.0, mode="mr_long")
    inst = PerpInstrument(
        symbol="ETH", exchange="okx", exchange_symbol="ETH-USDT-SWAP",
        max_leverage=50.0, mark_price=cs[-1].close, volume_24h_usd=300_000_000.0,
    )
    ds = {"ETH": (inst, cs)}
    bt = run_perp_portfolio_backtest(pc, ds)
    assert bt.liquidations == 0

    wf = run_perp_walkforward(pc, ds, folds=3)
    assert len(wf.folds) == 3

    cfg = Config.load()
    cfg.data.db_path = str(tmp_path / "lr.db")
    store = Store(cfg.data.db_path)
    try:
        rep = run_perp_self_learning_cycle(
            cfg, store, datasets=ds, apply_changes=False, reports_dir=tmp_path / "rep"
        )
        assert rep.liquidations == 0
        assert len(store.recent_perp_learning_runs()) == 1
    finally:
        store.close()


def test_combined_hero_spotlight_early_eval_and_simulator(tmp_path):
    import threading
    from http.server import ThreadingHTTPServer
    import urllib.request
    from pmmb.perps.learning import evaluate_perp_live_signals
    from pmmb.perps.models import PerpSignal

    cfg = Config.load()
    cfg.data.db_path = str(tmp_path / "sim.db")
    cfg.perps.mode = "paper"
    store = Store(cfg.data.db_path)
    now = int(datetime.now(tz=timezone.utc).timestamp())
    try:
        # 1) הערכת ביניים לאות צעיר בן 25 דקות דרך perp_intel
        sig = PerpSignal(
            symbol="SOL", exchange="okx", direction="LONG", strategy="meanrev",
            regime="RANGE", score=0.75, tier="A", price=200.0,
            stop_price=196.0, take_profit_price=206.0, atr=2.5, recommended_leverage=15.0,
            reason="meanrev", features={"z": -1.9},
            ts=datetime.fromtimestamp(now - 1500, tz=timezone.utc),
        )
        store.record_perp_signal(sig)
        store.upsert_perp_intel([{
            "updated_at": now - 60, "symbol": "SOL", "exchange": "okx", "price": 204.0,
            "regime": "RANGE", "strategy": "meanrev", "adx": 18.0, "er": 0.25, "rsi": 55.0,
            "z_score": -0.5, "atr_pct": 1.2, "funding_1h": 0.0, "spread_bps": 2.0,
            "imbalance": 0.1, "bid_depth_usd": 50000.0, "ask_depth_usd": 45000.0,
            "max_leverage": 50.0, "rec_leverage": 15.0, "score": 0.75,
            "setup_tier": "A", "status": "ENTRY", "reason": "test",
        }])
        n_early = evaluate_perp_live_signals(store, now_ts=now)
        assert n_early == 1
        stats = store.perp_signal_outcome_stats()
        assert stats["overall"]["hit_pct"] == 100.0
        assert stats["overall"]["mean_pct"] == 2.0

        # 2) הכנסת נרות SOL לבדיקת /api/perps/simulate
        cs = _mk_candles(160, base=200.0, mode="mr_long")
        store.insert_perp_candles(
            "SOL", "okx", "1h",
            [(c.ts, c.open, c.high, c.low, c.close, c.volume) for c in cs],
        )
    finally:
        store.close()

    cc = build_command_center_data(cfg)
    assert "combined" in cc
    assert cc["combined"]["equity"] > 0
    html = command_center_html(cc)
    for token in ("combined-hero", "spot-overlay", "perps-thesis-box", "perps-sim-res"):
        assert token in html

    trader = _TraderManager(cfg)
    handler = make_handler(cfg, max_age_sec=300, refresh_sec=0, token="", trader=trader)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/perps/simulate",
            data=json.dumps({"max_leverage": 30, "sl_atr_mult": 1.5, "tp_atr_mult": 2.6, "trailing_trigger_atr": 1.4}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read().decode())
            assert d["ok"] is True
            assert d["result"]["assets"] == 1
            assert d["result"]["liquidations"] == 0
    finally:
        srv.shutdown()
        srv.server_close()

