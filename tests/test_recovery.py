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
