"""בדיקות עמידות: שחזור אחרי הפעלה מחדש, עצירה מתמדת, סליקת שווקים וסטופ אבסולוטי."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pmmb.data.clob import Book, Candle
from pmmb.data.store import Store
from pmmb.engine import Engine
from pmmb.models import Market, Position, utcnow
from pmmb.risk.manager import RiskManager
from pmmb.risk.sizing import stop_and_target
from pmmb.runtime import check_health, clear_halt, read_halt, write_halt
from series import trending_series


def _gamma_market(cid="0xcond", slug="will-x-happen", question="Will X happen?", hours=48):
    import json
    return {
        "conditionId": cid,
        "question": question,
        "slug": slug,
        "clobTokenIds": json.dumps(["yes-token", "no-token"]),
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps(["0.5", "0.5"]),
        "bestBid": 0.495,
        "bestAsk": 0.505,
        "endDate": (datetime.now(tz=timezone.utc) + timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
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


class _FakeGamma:
    def __init__(self, payload):
        self.payload = payload

    def fetch_markets(self, limit=120, min_volume_24h=0.0, only_open=True):
        return self.payload


class _FakeClob:
    def __init__(self, prices, book_present=True, resolution=None):
        self.prices = prices
        self.book_present = book_present
        self.resolution = resolution

    def get_history(self, token_id, fidelity_min=5, lookback_candles=144, **kw):
        return [Candle(ts=1_700_000_000 + i * 300, price=p)
                for i, p in enumerate(self.prices[-lookback_candles:])]

    def get_book(self, token_id):
        if not self.book_present:
            return None
        mid = self.prices[-1]
        bid = round(mid - 0.005, 4)
        ask = round(mid + 0.005, 4)
        return Book(token_id=token_id, best_bid=bid, best_ask=ask,
                    bid_size=1000.0, ask_size=1000.0,
                    bids=[(bid, 1000.0)], asks=[(ask, 1000.0)])

    def get_resolution(self, condition_id, token_id):
        return self.resolution

    def estimate_fill(self, book, side, notional_usdc, max_impact_pct=0.02, allow_partial=False):
        ref = book.best_ask if side == "BUY" else book.best_bid
        return ref, notional_usdc / ref


def test_engine_restores_positions_and_prevents_double_buy(cfg, tmp_path):
    cfg.signal.engine = "momentum"
    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02
    db_path = tmp_path / "bot.db"
    state_dir = tmp_path / "state"
    clob = _FakeClob(trending_series(0.30, 0.80, n=140))
    gamma = _FakeGamma([_gamma_market()])

    eng1 = Engine(cfg, store=Store(db_path), clob=clob, gamma=gamma, state_dir=str(state_dir))
    st1 = eng1.run_once()
    assert st1.entries == 1
    cash_after_1 = eng1.portfolio.cash
    pos_size_1 = eng1.portfolio.positions["yes-token"].size
    eng1.close()

    # מפעילים מופע חדש לגמרי על אותו DB — אסור לקנות שוב ואסור לשכוח מזומן
    eng2 = Engine(cfg, store=Store(db_path), clob=clob, gamma=gamma, state_dir=str(state_dir))
    assert len(eng2.portfolio.positions) == 1
    assert abs(eng2.portfolio.cash - cash_after_1) < 1e-6
    assert abs(eng2.portfolio.positions["yes-token"].size - pos_size_1) < 1e-6

    st2 = eng2.run_once()
    assert st2.entries == 0
    assert len(eng2.portfolio.positions) == 1
    eng2.close()


def test_persistent_halt_blocks_entries_across_restarts(cfg, tmp_path):
    cfg.signal.engine = "momentum"
    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02
    db_path = tmp_path / "halt.db"
    state_dir = tmp_path / "state"
    write_halt("בדיקת חירום", source="phone", state_dir=state_dir)

    assert read_halt(state_dir) is not None
    assert not check_health(state_dir=state_dir).healthy

    clob = _FakeClob(trending_series(0.30, 0.80, n=140))
    eng = Engine(cfg, store=Store(db_path), clob=clob, gamma=_FakeGamma([_gamma_market()]),
                 state_dir=str(state_dir))
    st = eng.run_once()
    assert eng.risk.halted is True
    assert st.entries == 0
    assert check_health(state_dir=state_dir).healthy is False
    eng.close()

    assert clear_halt(state_dir) is True
    assert read_halt(state_dir) is None


def test_orphan_settlement_closes_resolved_market(cfg, tmp_path):
    cfg.signal.engine = "momentum"
    db_path = tmp_path / "settle.db"
    state_dir = tmp_path / "state"
    store = Store(db_path)
    store.upsert_position(Position(
        token_id="yes-old", condition_id="0xold", direction="LONG",
        size=100.0, avg_price=0.40, question="Resolved match?",
    ), "paper")
    from pmmb.models import Fill
    store.record_fill(Fill("yes-old", "0xold", "BUY", 0.40, 100.0), "paper")

    # השוק יצא מהיקום (יש שוק אחר פעיל), והספר שלו 404, אבל CLOB מחזיר זכייה=1.0
    class _SettleClob(_FakeClob):
        def get_book(self, token_id):
            if token_id == "yes-old":
                return None
            return super().get_book(token_id)

        def get_resolution(self, condition_id, token_id):
            return 1.0 if condition_id == "0xold" else None

    clob = _SettleClob([0.5] * 140)
    eng = Engine(cfg, store=store, clob=clob, gamma=_FakeGamma([_gamma_market("0xother", "other")]),
                 state_dir=str(state_dir))
    eng.run_once()
    assert "yes-old" not in eng.portfolio.positions
    assert eng.portfolio.realized_pnl == 60.0        # (1.00 - 0.40) * 100
    eng.close()


def test_empty_universe_does_not_liquidate_positions(cfg, tmp_path):
    cfg.signal.engine = "momentum"
    store = Store(tmp_path / "empty_uni.db")
    store.upsert_position(Position(
        token_id="yes-keep", condition_id="0xkeep", direction="LONG",
        size=50.0, avg_price=0.50,
    ), "paper")
    eng = Engine(cfg, store=store, clob=_FakeClob([0.5] * 140),
                 gamma=_FakeGamma([]), state_dir=str(tmp_path / "s"))
    eng.run_once()
    assert "yes-keep" in eng.portfolio.positions
    eng.close()


def test_near_resolution_triggers_exit(cfg):
    cfg.universe.min_hours_to_resolution = 6.0
    rm = RiskManager(cfg)
    pos = Position(token_id="y", condition_id="c", direction="LONG", size=10, avg_price=0.5,
                   opened_at=utcnow(), stop_price=0.3, target_price=0.8)
    assert rm.evaluate_exit(pos, 0.52, hours_to_resolution=10.0) is None
    reason = rm.evaluate_exit(pos, 0.52, hours_to_resolution=4.0)
    assert reason is not None and "פדיון" in reason


def test_abs_stop_and_target():
    stop, target = stop_and_target(0.15, "LONG", 0.08, 0.05, 0.001, mode="abs")
    assert stop == 0.07 and target == 0.20
    # במחיר נמוך הסטופ לא קורס מתחת לאפס
    stop2, target2 = stop_and_target(0.05, "LONG", 0.08, 0.05, 0.001, mode="abs")
    assert stop2 == 0.01 and target2 == 0.10


def test_event_id_dedup_survives_restart(cfg, tmp_path):
    """שני שווקים תחת אותו event_id — נכנסים רק לאחד, וגם אחרי ריסטארט השני חסום."""
    cfg.signal.engine = "momentum"
    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02
    cfg.risk.max_positions_per_event = 1
    db_path = tmp_path / "ev.db"
    state_dir = tmp_path / "state"

    def _ev_mk(cid, tok, slug, q):
        import json
        m = _gamma_market(cid=cid, slug=slug, question=q)
        m["clobTokenIds"] = json.dumps([tok, tok + "-no"])
        m["events"] = [{"id": "ev-999", "slug": "election-999", "tags": []}]
        return m

    m1 = _ev_mk("0xc1", "tok-1", "cand-1", "Will A win?")
    m2 = _ev_mk("0xc2", "tok-2", "cand-2", "Will B win?")
    clob = _FakeClob(trending_series(0.30, 0.80, n=140))

    eng1 = Engine(cfg, store=Store(db_path), clob=clob, gamma=_FakeGamma([m1]), state_dir=str(state_dir))
    assert eng1.run_once().entries == 1
    assert eng1.portfolio.positions["tok-1"].event_id == "ev-999"
    eng1.close()

    # אחרי ריסטארט מופיע שוק שני מאותו אירוע — חובה לחסום אותו
    eng2 = Engine(cfg, store=Store(db_path), clob=clob, gamma=_FakeGamma([m1, m2]), state_dir=str(state_dir))
    st2 = eng2.run_once()
    assert st2.entries == 0
    assert "tok-2" not in eng2.portfolio.positions
    eng2.close()


def test_thin_book_depth_blocks_entry_before_broker(cfg, tmp_path):
    """אם הליכת הספר (estimate_fill) עוברת את max_price_impact_pct — מדלגים מראש."""
    cfg.signal.engine = "momentum"
    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02
    cfg.risk.max_price_impact_pct = 0.02

    class _ThinClob(_FakeClob):
        def estimate_fill(self, book, side, notional_usdc, max_impact_pct=0.02, allow_partial=False):
            # מחזיר מחיר מילוי יקר ב-10% מה-best_ask
            return round(book.best_ask * 1.10, 4), notional_usdc / book.best_ask

    eng = Engine(cfg, store=Store(tmp_path / "thin.db"),
                 clob=_ThinClob(trending_series(0.30, 0.80, n=140)),
                 gamma=_FakeGamma([_gamma_market()]), state_dir=str(tmp_path / "s"))
    st = eng.run_once()
    assert st.entries == 0
    assert st.skipped.get("ספר פקודות דק או חסר", 0) >= 1
    eng.close()


def test_min_entry_hours_blocks_near_resolution_entries(cfg, tmp_path):
    """שוק שנותרו לו 10 שעות לסגירה לא נפתח (min_entry_hours=24), גם אם > 6."""
    cfg.signal.engine = "momentum"
    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02
    cfg.universe.min_hours_to_resolution = 6
    cfg.universe.min_entry_hours_to_resolution = 24

    eng = Engine(cfg, store=Store(tmp_path / "near.db"),
                 clob=_FakeClob(trending_series(0.30, 0.80, n=140)),
                 gamma=_FakeGamma([_gamma_market(hours=10)]), state_dir=str(tmp_path / "s"))
    st = eng.run_once()
    assert st.entries == 0
    eng.close()


def test_engine_graceful_stop_exits_after_current_cycle(cfg, tmp_path):
    """request_stop() מסיים את המחזור הנוכחי ויוצא מ-run_forever בלי להמתין interval."""
    import time

    cfg.signal.engine = "momentum"
    eng = Engine(cfg, store=Store(tmp_path / "stop.db"),
                 clob=_FakeClob(trending_series(0.30, 0.80, n=140)),
                 gamma=_FakeGamma([_gamma_market()]), state_dir=str(tmp_path / "s"))
    orig = eng.run_once

    def _run_and_stop():
        st = orig()
        eng.request_stop()
        return st

    eng.run_once = _run_and_stop  # type: ignore[method-assign]
    t0 = time.monotonic()
    eng.run_forever(interval_sec=60.0, max_cycles=5)
    assert time.monotonic() - t0 < 2.0
    assert eng.cycle == 1
    eng.close()


def test_orphan_position_stays_open_while_within_limits(cfg, tmp_path):
    """פוזיציה שיצאה מה-Top-N (לא בסריקה) נשארת פתוחה כל עוד לא פגעה ב-SL/TP/TimeStop."""
    from pmmb.models import Fill

    cfg.signal.engine = "momentum"
    store = Store(tmp_path / "orphan_hold.db")
    store.upsert_position(Position(
        token_id="yes-hold", condition_id="0xold", direction="LONG",
        size=40.0, avg_price=0.50, stop_price=0.40, target_price=0.60,
        opened_at=utcnow(), question="Hold outside universe?",
    ), "paper")
    store.record_fill(Fill("yes-hold", "0xold", "BUY", 0.50, 40.0), "paper")

    # היקום החי מחזיר שוק אחר לגמרי, ולטוקן הפוזיציה יש ספר עם bid=0.48 (בתוך הגבולות)
    class _LiveOrphanClob(_FakeClob):
        def get_book(self, token_id):
            if token_id == "yes-hold":
                from pmmb.data.clob import Book
                return Book(token_id="yes-hold", best_bid=0.48, best_ask=0.50,
                            bid_size=100.0, ask_size=100.0,
                            bids=[(0.48, 100.0)], asks=[(0.50, 100.0)])
            return super().get_book(token_id)

    eng = Engine(cfg, store=store, clob=_LiveOrphanClob([0.5] * 140),
                 gamma=_FakeGamma([_gamma_market("0xother", "other")]),
                 state_dir=str(tmp_path / "s"))
    st = eng.run_once()
    assert st.exits == 0
    assert "yes-hold" in eng.portfolio.positions
    assert eng._last_marks.get("yes-hold") == 0.48
    eng.close()


def test_orphan_position_exits_on_target_or_stop(cfg, tmp_path):
    """פוזיציה מחוץ לסריקה כן יוצאת בצורה מבוקרת כשהספר מגיע ל-TP (או SL/TimeStop)."""
    from pmmb.models import Fill

    cfg.signal.engine = "momentum"
    store = Store(tmp_path / "orphan_tp.db")
    store.upsert_position(Position(
        token_id="yes-tp", condition_id="0xold2", direction="LONG",
        size=40.0, avg_price=0.50, stop_price=0.40, target_price=0.56,
        opened_at=utcnow(), question="Hit TP outside universe?",
    ), "paper")
    store.record_fill(Fill("yes-tp", "0xold2", "BUY", 0.50, 40.0), "paper")

    class _TpOrphanClob(_FakeClob):
        def get_book(self, token_id):
            if token_id == "yes-tp":
                from pmmb.data.clob import Book
                return Book(token_id="yes-tp", best_bid=0.57, best_ask=0.58,
                            bid_size=200.0, ask_size=200.0,
                            bids=[(0.57, 200.0)], asks=[(0.58, 200.0)])
            return super().get_book(token_id)

    eng = Engine(cfg, store=store, clob=_TpOrphanClob([0.5] * 140),
                 gamma=_FakeGamma([_gamma_market("0xother", "other")]),
                 state_dir=str(tmp_path / "s"))
    st = eng.run_once()
    assert st.exits == 1
    assert "yes-tp" not in eng.portfolio.positions
    assert eng.portfolio.realized_pnl > 0
    eng.close()


def test_orphan_position_exits_before_resolution(cfg, tmp_path):
    """פוזיציה מחוץ לסריקה יוצאת לפני פדיון (< min_hours_to_resolution) גם ללא פגיעת SL/TP."""
    from pmmb.models import Fill

    cfg.signal.engine = "momentum"
    cfg.universe.min_hours_to_resolution = 6
    store = Store(tmp_path / "orphan_exp.db")
    store.upsert_position(Position(
        token_id="yes-exp", condition_id="0xexp", direction="LONG",
        size=40.0, avg_price=0.50, stop_price=0.40, target_price=0.60,
        opened_at=utcnow(), question="Near resolution outside universe?",
    ), "paper")
    store.record_fill(Fill("yes-exp", "0xexp", "BUY", 0.50, 40.0), "paper")

    class _ExpOrphanClob(_FakeClob):
        def get_book(self, token_id):
            if token_id == "yes-exp":
                from pmmb.data.clob import Book
                return Book(token_id="yes-exp", best_bid=0.49, best_ask=0.51,
                            bid_size=200.0, ask_size=200.0,
                            bids=[(0.49, 200.0)], asks=[(0.51, 200.0)])
            return super().get_book(token_id)

    class _ExpOrphanGamma(_FakeGamma):
        def __init__(self, markets):
            super().__init__(markets)
            exp_mk = _gamma_market("0xexp", "exp", hours=3)

            class _FakeHttp:
                def get(self, path, params=None):
                    if params and params.get("condition_ids") == "0xexp":
                        return [exp_mk]
                    return []

            self.http = _FakeHttp()

    eng = Engine(cfg, store=store, clob=_ExpOrphanClob([0.5] * 140),
                 gamma=_ExpOrphanGamma([_gamma_market("0xother", "other")]),
                 state_dir=str(tmp_path / "s"))
    st = eng.run_once()
    assert st.exits == 1
    assert "yes-exp" not in eng.portfolio.positions
    eng.close()




