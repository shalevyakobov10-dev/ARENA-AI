"""בדיקות לברוקר החי (ללא רשת) ולמודול ה-reconcile."""
from __future__ import annotations

from pmmb.config import ExecutionConfig
from pmmb.data.store import Store
from pmmb.execution.live import LiveBroker, parse_order_response
from pmmb.models import Fill, Order, Position
from pmmb.reconcile import reconcile_live, reconcile_paper


def _order(side="BUY", price=0.40, size=50.0, fee_rate=0.05) -> Order:
    return Order(token_id="tok-1", condition_id="0xc1", side=side,
                 price=price, size=size, fee_rate=fee_rate)


def test_parse_order_response_matched_and_fees():
    resp = {"success": True, "status": "matched", "size_matched": "50", "orderID": "ord-1"}
    fill = parse_order_response(resp, _order(fee_rate=0.05), fee_mode="model")
    assert fill is not None
    assert fill.size == 50.0 and fill.price == 0.40
    assert fill.fee > 0 and fill.order_id == "ord-1"


def test_parse_order_response_resting_unfilled_returns_none():
    """הזמנה במצב live שעוד לא מולאה אסור שתירשם כ-Fill."""
    resp = {"success": True, "status": "live", "orderID": "ord-2"}
    assert parse_order_response(resp, _order()) is None
    assert parse_order_response({"success": False}, _order()) is None


def test_parse_order_response_making_taking_ratio():
    # קנייה: שולמו 20 USDC עבור 50 מניות => מחיר אפקטיבי 0.40
    resp = {"success": True, "status": "matched", "makingAmount": "20", "takingAmount": "50", "orderID": "o3"}
    fill = parse_order_response(resp, _order(side="BUY", price=0.42), fee_mode="off")
    assert fill is not None and fill.size == 50.0 and fill.price == 0.40


def test_live_broker_execute_never_raises(monkeypatch):
    monkeypatch.setenv("PMMB_PRIVATE_KEY", "0x" + "1" * 64)
    monkeypatch.setenv("PMMB_LIVE_CONFIRM", "I-UNDERSTAND-THE-RISK")
    b = LiveBroker(ExecutionConfig(mode="live"))

    class _BoomClient:
        def create_order(self, *a):
            raise RuntimeError("CLOB down")

    b._client = _BoomClient()
    assert b.execute(_order()) is None


def test_reconcile_paper_detects_and_fixes_ledger_mismatch(tmp_path):
    store = Store(tmp_path / "p.db")
    # 2 קניות של 50, אבל הפוזיציה נדרסה ל-50 במקום 100
    store.record_fill(Fill("tok-a", "c-a", "BUY", 0.40, 50.0, fee=0.5), "paper")
    store.record_fill(Fill("tok-a", "c-a", "BUY", 0.40, 50.0, fee=0.5), "paper")
    store.upsert_position(Position("tok-a", "c-a", "LONG", 50.0, 0.40), "paper")

    rep1 = reconcile_paper(store, starting_cash=1000.0, fix=False)
    assert not rep1.clean
    assert any(d.kind == "ledger_mismatch" for d in rep1.discrepancies)

    rep2 = reconcile_paper(store, starting_cash=1000.0, fix=True)
    assert rep2.fixes_applied >= 1
    rep3 = reconcile_paper(store, starting_cash=1000.0, fix=False)
    assert rep3.clean
    store.close()


def test_reconcile_live_fixes_ghosts_and_unrecorded(tmp_path):
    store = Store(tmp_path / "l.db")
    store.upsert_position(Position("tok-ghost", "c1", "LONG", 30.0, 0.5), "live")
    store.upsert_position(Position("tok-drift", "c2", "LONG", 40.0, 0.5), "live")

    class _FakeLive:
        def __init__(self):
            self.cancelled = False

        def usdc_balance(self):
            return 900.0

        def open_orders(self):
            return [{"id": "ord-9", "asset_id": "tok-drift", "side": "BUY",
                     "original_size": "10", "price": "0.5"}]

        def cancel_all(self):
            self.cancelled = True
            return 1

        def wallet_address(self):
            return "0xwallet"

        def conditional_balance(self, tid):
            return 0.0

    ex = [
        {"asset": "tok-drift", "size": 25.0, "avgPrice": 0.5, "conditionId": "c2", "title": "M2"},
        {"asset": "tok-new", "size": 60.0, "avgPrice": 0.3, "conditionId": "c3", "title": "New on exchange"},
    ]
    broker = _FakeLive()
    rep = reconcile_live(store, broker, starting_cash=1000.0, fix=True, cancel_orders=True,
                         exchange_positions=ex)
    kinds = {d.kind for d in rep.discrepancies}
    assert {"ghost_local", "size_mismatch", "unrecorded_exchange", "stale_order"} <= kinds
    assert broker.cancelled is True

    # אחרי ריסטארט, ghost נסגר, drift עודכן ל-25, והחדש נרשם
    open_map = {r["token_id"]: r["size"] for r in store.open_positions("live")}
    assert "tok-ghost" not in open_map
    assert open_map["tok-drift"] == 25.0
    assert open_map["tok-new"] == 60.0
    store.close()


def test_live_broker_validates_price_and_min_size(monkeypatch):
    monkeypatch.setenv("PMMB_PRIVATE_KEY", "0x" + "1" * 64)
    monkeypatch.setenv("PMMB_LIVE_CONFIRM", "I-UNDERSTAND-THE-RISK")
    b = LiveBroker(ExecutionConfig(mode="live"))

    called = False

    class _SpyClient:
        def create_order(self, *a):
            nonlocal called
            called = True
            return {}

    b._client = _SpyClient()
    assert b.execute(_order(price=0.0, size=20.0)) is None
    assert b.execute(_order(side="BUY", price=0.45, size=2.0)) is None
    assert called is False


def test_engine_live_entry_blocks_insufficient_usdc(monkeypatch, cfg, tmp_path):
    """במצב live בודקים usdc_balance() לפני פקודת קנייה."""
    from test_recovery import _FakeClob, _FakeGamma, _gamma_market
    from series import trending_series
    from pmmb.engine import Engine

    monkeypatch.setenv("PMMB_PRIVATE_KEY", "0x" + "1" * 64)
    monkeypatch.setenv("PMMB_LIVE_CONFIRM", "I-UNDERSTAND-THE-RISK")
    cfg.execution.mode = "live"
    cfg.signal.engine = "momentum"
    cfg.signal.min_score = 0.5
    cfg.signal.min_edge = 0.02

    class _LowBalBroker:
        mode = "live"

        def __init__(self):
            self.executed = False

        def usdc_balance(self):
            return 1.0  # כמעט אין יתרה

        def execute(self, *a, **kw):
            self.executed = True
            return None

    broker = _LowBalBroker()
    eng = Engine(
        cfg,
        store=Store(tmp_path / "live_bal.db"),
        broker=broker,
        clob=_FakeClob(trending_series(0.30, 0.80, n=140)),
        gamma=_FakeGamma([_gamma_market()]),
        state_dir=str(tmp_path / "s"),
    )
    st = eng.run_once()
    assert st.entries == 0
    assert broker.executed is False
    eng.close()
