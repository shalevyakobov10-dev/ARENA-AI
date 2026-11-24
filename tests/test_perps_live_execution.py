"""Offline regression tests for verified PERPS live fills and partial close accounting."""
from __future__ import annotations

import sys
import types
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from pmmb.config import Config, PerpsConfig
from pmmb.data.store import Store
from pmmb.perps.broker import LivePerpBroker, PerpsExecutionUncertain
from pmmb.perps.engine import PerpEngine
from pmmb.perps.models import PerpFill, PerpInstrument, PerpPosition, utcnow
from pmmb.runtime import read_halt


class _Response:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://mock.invalid")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("mock HTTP error", request=request, response=response)

    def json(self):
        return self._payload


def _order(exchange: str, *, action: str = "OPEN", size: float = 2.0):
    from pmmb.perps.models import PerpOrder

    return PerpOrder(
        symbol="BTC",
        exchange=exchange,
        side="LONG",
        action=action,
        price=100.0,
        size=size,
        leverage=5.0,
        reduce_only=(action == "CLOSE"),
        reason="test",
    )


def _live_broker(monkeypatch, exchange: str) -> LivePerpBroker:
    cfg = PerpsConfig(mode="live")
    monkeypatch.setenv("PMMB_PERPS_LIVE_CONFIRM", "YES")
    if exchange == "okx":
        monkeypatch.setenv("OKX_API_KEY", "test-key")
        monkeypatch.setenv("OKX_API_SECRET", "test-secret")
        monkeypatch.setenv("OKX_PASSPHRASE", "test-passphrase")
    elif exchange == "binance":
        monkeypatch.setenv("BINANCE_API_KEY", "test-key")
        monkeypatch.setenv("BINANCE_API_SECRET", "test-secret")
    elif exchange == "hyperliquid":
        monkeypatch.setenv("PMMB_HL_PRIVATE_KEY", "test-private-key")
    return LivePerpBroker(cfg)


def test_okx_fill_uses_exchange_cumulative_quantity_and_average_price(monkeypatch):
    broker = _live_broker(monkeypatch, "okx")
    posts = []

    def fake_post(url, **kwargs):
        posts.append(url)
        return _Response({
            "code": "0",
            "data": [{"sCode": "0", "ordId": "okx-order-7"}],
        })

    def fake_get(url, **kwargs):
        assert "/api/v5/trade/order?" in url
        return _Response({
            "code": "0",
            "data": [{
                "state": "canceled",
                "accFillSz": "25",
                "avgPx": "101",
                "ordId": "okx-order-7",
            }],
        })

    monkeypatch.setattr("pmmb.perps.broker.httpx.post", fake_post)
    monkeypatch.setattr("pmmb.perps.broker.httpx.get", fake_get)
    fill = broker.execute(
        _order("okx", size=3.0),
        ct_val=0.1,
        lot_size=0.1,
        taker_fee_bps=3.5,
    )

    assert len(posts) == 2
    assert fill is not None
    assert fill.order_id == "okx-order-7"
    assert fill.size == pytest.approx(2.5)
    assert fill.price == pytest.approx(101.0)
    assert fill.notional == pytest.approx(252.5)


def test_okx_canceled_without_any_fill_returns_none(monkeypatch):
    broker = _live_broker(monkeypatch, "okx")
    monkeypatch.setattr(
        "pmmb.perps.broker.httpx.post",
        lambda *a, **k: _Response({"code": "0", "data": [{"sCode": "0", "ordId": "oid-0"}]}),
    )
    monkeypatch.setattr(
        "pmmb.perps.broker.httpx.get",
        lambda *a, **k: _Response({
            "code": "0",
            "data": [{"state": "canceled", "accFillSz": "0", "avgPx": "", "ordId": "oid-0"}],
        }),
    )

    assert broker.execute(_order("okx")) is None


def test_okx_unavailable_order_confirmation_sets_persistent_halt(monkeypatch, tmp_path):
    broker = _live_broker(monkeypatch, "okx")
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(
        "pmmb.perps.broker.httpx.post",
        lambda *a, **k: _Response({"code": "0", "data": [{"sCode": "0", "ordId": "oid-uncertain"}]}),
    )

    def timed_out(*_args, **_kwargs):
        raise httpx.ReadTimeout("mock read timeout")

    monkeypatch.setattr("pmmb.perps.broker.httpx.get", timed_out)
    with pytest.raises(PerpsExecutionUncertain):
        broker.execute(_order("okx"))

    halt = read_halt()
    assert halt is not None
    assert halt.source == "execution_uncertain"
    assert "oid-uncertain" in halt.reason


def test_binance_market_fill_uses_result_execution_fields(monkeypatch):
    broker = _live_broker(monkeypatch, "binance")
    urls = []

    def fake_post(url, **kwargs):
        urls.append(url)
        if "/fapi/v1/marginType" in url:
            return _Response({"code": -4046, "msg": "No need to change margin type."})
        if "/fapi/v1/leverage" in url:
            return _Response({"leverage": 5, "symbol": "BTCUSDT"})
        return _Response({
            "status": "FILLED",
            "executedQty": "0.75",
            "avgPrice": "123.45",
            "orderId": 991,
        })

    monkeypatch.setattr("pmmb.perps.broker.httpx.post", fake_post)
    fill = broker.execute(_order("binance", size=1.0), lot_size=0.05)

    assert fill is not None
    assert fill.order_id == "991"
    assert fill.size == pytest.approx(0.75)
    assert fill.price == pytest.approx(123.45)
    order_query = parse_qs(urlparse(urls[-1]).query)
    assert order_query["newOrderRespType"] == ["RESULT"]


def test_binance_expired_market_order_with_zero_execution_is_not_a_fill(monkeypatch):
    broker = _live_broker(monkeypatch, "binance")

    def fake_post(url, **kwargs):
        if "/fapi/v1/marginType" in url:
            return _Response({"code": -4046})
        if "/fapi/v1/leverage" in url:
            return _Response({"leverage": 5})
        return _Response({
            "status": "EXPIRED",
            "executedQty": "0",
            "avgPrice": "0",
            "orderId": 992,
        })

    monkeypatch.setattr("pmmb.perps.broker.httpx.post", fake_post)
    assert broker.execute(_order("binance")) is None


def test_binance_transport_timeout_after_order_submission_halts(monkeypatch, tmp_path):
    broker = _live_broker(monkeypatch, "binance")
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))

    def fake_post(url, **kwargs):
        if "/fapi/v1/marginType" in url:
            return _Response({"code": -4046})
        if "/fapi/v1/leverage" in url:
            return _Response({"leverage": 5})
        raise httpx.ReadTimeout("mock order timeout")

    monkeypatch.setattr("pmmb.perps.broker.httpx.post", fake_post)
    with pytest.raises(PerpsExecutionUncertain):
        broker.execute(_order("binance"))

    halt = read_halt()
    assert halt is not None and halt.source == "execution_uncertain"


def _install_fake_hyperliquid(monkeypatch, result):
    exchange_calls = {}

    class FakeExchange:
        def __init__(self, wallet):
            self.wallet = wallet

        def update_leverage(self, leverage, symbol, is_cross=False):
            exchange_calls["leverage"] = (leverage, symbol, is_cross)
            return {"status": "ok"}

        def market_open(self, symbol, is_buy, size, px=None, slippage=0.01):
            exchange_calls["order"] = (symbol, is_buy, size, px, slippage)
            return result

        def market_close(self, symbol, sz=None):
            exchange_calls["order"] = (symbol, "close", sz)
            return result

        def cancel(self, symbol, oid):
            exchange_calls["cancel"] = (symbol, oid)
            return {"status": "ok"}

    exchange_module = types.ModuleType("hyperliquid.exchange")
    exchange_module.Exchange = FakeExchange
    package = types.ModuleType("hyperliquid")
    package.__path__ = []
    package.exchange = exchange_module

    eth_module = types.ModuleType("eth_account")

    class FakeAccount:
        @staticmethod
        def from_key(key):
            return {"key": key}

    eth_module.Account = FakeAccount
    monkeypatch.setitem(sys.modules, "hyperliquid", package)
    monkeypatch.setitem(sys.modules, "hyperliquid.exchange", exchange_module)
    monkeypatch.setitem(sys.modules, "eth_account", eth_module)
    return exchange_calls


def test_hyperliquid_uses_only_confirmed_filled_payload(monkeypatch):
    broker = _live_broker(monkeypatch, "hyperliquid")
    calls = _install_fake_hyperliquid(monkeypatch, {
        "status": "ok",
        "response": {"data": {"statuses": [{
            "filled": {"oid": 12345, "totalSz": "0.08", "avgPx": "99.75"}
        }]}},
    })

    fill = broker.execute(_order("hyperliquid", size=0.2), lot_size=0.01)
    assert fill is not None
    assert fill.order_id == "12345"
    assert fill.size == pytest.approx(0.08)
    assert fill.price == pytest.approx(99.75)
    assert calls["order"][2] == pytest.approx(0.2)


def test_hyperliquid_explicit_order_error_is_not_a_fill(monkeypatch):
    broker = _live_broker(monkeypatch, "hyperliquid")
    _install_fake_hyperliquid(monkeypatch, {
        "status": "ok",
        "response": {"data": {"statuses": [{"error": "MarketOrderNoLiquidity"}]}},
    })

    assert broker.execute(_order("hyperliquid")) is None


class _StubExchange:
    def __init__(self):
        self.instrument = PerpInstrument(
            symbol="BTC",
            exchange="okx",
            exchange_symbol="BTC-USDT-SWAP",
            max_leverage=50.0,
            mark_price=110.0,
        )

    def scan(self):
        return [self.instrument]

    def get_book(self, instrument, levels=8):
        return None

    def close(self):
        pass


class _FixedBroker:
    mode = "paper"

    def __init__(self, fill):
        self.fill = fill
        self.calls = 0

    def execute(self, order, **kwargs):
        self.calls += 1
        return self.fill


def _position() -> PerpPosition:
    return PerpPosition(
        symbol="BTC",
        exchange="okx",
        side="LONG",
        size=2.0,
        entry_price=100.0,
        notional=200.0,
        leverage=5.0,
        margin_used=40.0,
        liquidation_price=80.0,
        stop_price=90.0,
        target_price=120.0,
        highest_price=100.0,
        lowest_price=100.0,
        atr=2.0,
        fees_paid=1.0,
        accumulated_funding=0.5,
        opened_at=utcnow() - timedelta(hours=2),
        last_funding_ts=int(utcnow().timestamp()),
    )


def _engine(tmp_path, broker):
    cfg = Config()
    cfg.perps.mode = "paper"
    cfg.data.db_path = str(tmp_path / "perps.db")
    store = Store(cfg.data.db_path)
    eng = PerpEngine(cfg, store=store, exchange=_StubExchange(), broker=broker)
    position = _position()
    eng.positions[position.symbol] = position
    eng.store.upsert_perp_position(position, cfg.perps.mode)
    eng.cash = 900.0
    return eng, position


def test_partial_manual_close_keeps_unfilled_position_open(tmp_path):
    fill = PerpFill(
        symbol="BTC",
        exchange="okx",
        side="LONG",
        action="CLOSE",
        price=110.0,
        size=0.5,
        notional=55.0,
        leverage=5.0,
        margin_delta=0.0,
        fee=0.1,
        reason="partial test",
        order_id="partial-close-1",
    )
    eng, position = _engine(tmp_path, _FixedBroker(fill))
    try:
        result = eng.close_position_by_symbol("BTC", "partial test")
        assert result["partial"] is True
        assert result["size"] == pytest.approx(0.5)
        assert result["remaining_size"] == pytest.approx(1.5)
        assert position.size == pytest.approx(1.5)
        assert position.margin_used == pytest.approx(30.0)
        assert position.fees_paid == pytest.approx(0.75)
        assert position.accumulated_funding == pytest.approx(0.375)
        row = eng.store._conn.execute(
            "SELECT size, margin_used, closed_at FROM perp_positions WHERE symbol='BTC'"
        ).fetchone()
        assert row["size"] == pytest.approx(1.5)
        assert row["margin_used"] == pytest.approx(30.0)
        assert row["closed_at"] is None
        fill_row = eng.store._conn.execute(
            "SELECT size, price, order_id FROM perp_fills WHERE symbol='BTC' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert fill_row["size"] == pytest.approx(0.5)
        assert fill_row["price"] == pytest.approx(110.0)
        assert fill_row["order_id"] == "partial-close-1"
    finally:
        eng.close()


def test_failed_manual_close_does_not_create_synthetic_fill_or_close_position(tmp_path):
    eng, position = _engine(tmp_path, _FixedBroker(None))
    try:
        with pytest.raises(RuntimeError, match="נשארה פתוחה"):
            eng.close_position_by_symbol("BTC", "no fill")
        assert eng.positions["BTC"] is position
        row = eng.store._conn.execute(
            "SELECT size, closed_at FROM perp_positions WHERE symbol='BTC'"
        ).fetchone()
        assert row["size"] == pytest.approx(2.0)
        assert row["closed_at"] is None
        n_fills = eng.store._conn.execute(
            "SELECT COUNT(*) FROM perp_fills WHERE symbol='BTC'"
        ).fetchone()[0]
        assert n_fills == 0
    finally:
        eng.close()


def test_oversized_close_fill_sets_halt_without_mutating_position(tmp_path, monkeypatch):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    oversized = PerpFill(
        symbol="BTC",
        exchange="okx",
        side="LONG",
        action="CLOSE",
        price=110.0,
        size=2.5,
        notional=275.0,
        leverage=5.0,
        margin_delta=0.0,
        fee=0.2,
        reason="bad fill",
        order_id="oversize-1",
    )
    eng, position = _engine(tmp_path, _FixedBroker(oversized))
    try:
        with pytest.raises(PerpsExecutionUncertain):
            eng.close_position_by_symbol("BTC", "oversize")
        assert position.size == pytest.approx(2.0)
        halt = read_halt()
        assert halt is not None and halt.source == "execution_uncertain"
    finally:
        eng.close()


def test_uncertain_execution_halt_blocks_automatic_close_attempt(tmp_path, monkeypatch):
    from pmmb.perps.engine import PerpCycleStats
    from pmmb.runtime import write_halt

    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "state"))
    eng, position = _engine(tmp_path, _FixedBroker(None))
    try:
        write_halt("unresolved live order", source="execution_uncertain")
        stats = PerpCycleStats()
        eng._process_position(position, eng.exchange.instrument, None, None, 110.0, stats)
        assert eng.broker.calls == 0
        assert eng.positions["BTC"] is position
    finally:
        eng.close()
