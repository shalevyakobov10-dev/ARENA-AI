"""פיקסצ'רים משותפים לטסטים — ללא רשת."""
from __future__ import annotations

import pytest

from pmmb.config import Config, ExecutionConfig, RiskConfig, SignalConfig
from pmmb.data.clob import Book
from pmmb.models import Market


@pytest.fixture
def cfg() -> Config:
    c = Config()
    c.execution = ExecutionConfig(mode="paper", starting_cash=1000.0, slippage_bps=10)
    c.signal = SignalConfig(
        candle_fidelity_min=5, lookback_candles=144, ema_fast=9, ema_slow=26,
        breakout_window=20, momentum_window=12, vol_window=30,
        min_score=0.5, min_edge=0.02, confirm_candles=2,
        trend_filter=True, allow_short=True,
    )
    c.signal.exit.take_profit = 0.12
    c.signal.exit.stop_loss = 0.07
    c.signal.exit.time_stop_hours = 48
    c.risk = RiskConfig()
    return c


@pytest.fixture
def market() -> Market:
    return Market(
        condition_id="0xabc",
        question="Will X happen?",
        slug="will-x-happen",
        yes_token_id="yes-token",
        no_token_id="no-token",
        yes_price=0.5,
        no_price=0.5,
        spread=0.01,
        volume_24h=100_000,
        liquidity=50_000,
        end_date=None,
        tick_size=0.01,
        min_order_size=5.0,
    )


@pytest.fixture
def book() -> Book:
    return Book(
        token_id="yes-token",
        best_bid=0.49,
        best_ask=0.50,
        bid_size=500.0,
        ask_size=500.0,
        bids=[(0.49, 400.0), (0.48, 500.0)],
        asks=[(0.50, 400.0), (0.52, 500.0)],
    )


@pytest.fixture
def cfg_market(cfg, market):
    """(הקונפיג, השוק) — נוחות לטסטים שמקבלים את שניהם."""
    return cfg, market


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """מבחנים לעולם לא דורסים את state/heartbeat.json של ההרצה האמיתית."""
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "pmmb-state"))
