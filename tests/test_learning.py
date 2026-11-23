"""בדיקות למנוע הלמידה העצמית הרציף (Live Outcomes + Walk-Forward Promotion) — אפס רשת."""
from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone

from pmmb.data.clob import Candle
from pmmb.data.store import Store
from pmmb.learning import evaluate_live_signals, run_self_learning_cycle
from pmmb.models import Market, Signal


def _make_meanrev_dataset(seed: int, n_bars: int = 420) -> tuple[Market, list[Candle]]:
    base_ts = int(time.time()) - n_bars * 3600
    mk = Market(
        condition_id=f"0xm{seed}",
        question=f"Will candidate {seed} recover after dip?",
        slug=f"mkt-{seed}",
        yes_token_id=f"tok-{seed}",
        no_token_id=f"no-{seed}",
        yes_price=0.50,
        no_price=0.50,
        spread=0.01,
        volume_24h=80_000,
        liquidity=25_000,
        end_date=datetime.now(tz=timezone.utc) + timedelta(days=40),
        tick_size=0.01,
        min_order_size=5.0,
        sector="politics",
    )
    candles: list[Candle] = []
    px = 0.50
    for i in range(n_bars):
        # גל של טבילות חדות שמתקנות בחזרה לאזור 0.50
        phase = (i + seed * 5) % 36
        if phase == 20:
            px = 0.36
        elif phase in (21, 22):
            px = 0.42
        elif phase in (23, 24):
            px = 0.49
        else:
            px = 0.50 + 0.012 * math.sin((i + seed) * 0.6)
        candles.append(Candle(ts=base_ts + i * 3600, price=round(px, 4)))
    return mk, candles


def test_evaluate_live_signals_tracks_24h_48h_and_news(tmp_path):
    store = Store(tmp_path / "learn.db")
    now = int(time.time())
    t0 = now - 60 * 3600

    # אות ראשון — שוק שקט, עלה ב-24ש' ו-48ש'
    store.record_signal(Signal(
        condition_id="c1", token_id="t_good", direction="LONG",
        score=0.75, fair_price=0.46, market_price=0.38, edge=0.04,
        reason="צניחה (z=-2.4)", features={"z": -2.4},
        created_at=datetime.fromtimestamp(t0, tz=timezone.utc),
    ))
    store.insert_ticks([
        ("t_good", t0 + 6 * 3600, 0.40),
        ("t_good", t0 + 24 * 3600, 0.44),
        ("t_good", t0 + 48 * 3600, 0.46),
    ])

    # אות שני — שוק עם חדשות קטליזטור, המשיך ליפול
    store.record_signal(Signal(
        condition_id="c2", token_id="t_news_bad", direction="LONG",
        score=0.70, fair_price=0.45, market_price=0.40, edge=0.03,
        reason="צניחה (z=-3.2)", features={"z": -3.2},
        created_at=datetime.fromtimestamp(t0, tz=timezone.utc),
    ))
    store.upsert_news([{
        "id": "n1", "ts": t0 - 1800, "title": "Breaking drop out announcement",
        "source": "AP", "impact": 0.90, "sentiment": -0.8,
        "matched_tokens": "t_news_bad"[:12],
    }])
    store.insert_ticks([
        ("t_news_bad", t0 + 24 * 3600, 0.30),
        ("t_news_bad", t0 + 48 * 3600, 0.25),
    ])

    n_upd = evaluate_live_signals(store, now_ts=now)
    assert n_upd == 2

    stats = store.signal_outcome_stats(days=30)
    assert stats["actionable"]["n"] == 2
    assert stats["actionable"]["hit_48h_pct"] == 50.0
    assert stats["by_news"]["quiet"]["hit_48h_pct"] == 100.0
    assert stats["by_news"]["news_catalyst"]["hit_48h_pct"] == 0.0
    store.close()


def test_self_learning_promotes_only_when_safe_and_never_auto_applies_live(tmp_path, cfg):
    cfg.signal.engine = "meanrev"
    cfg.signal.exit.stop_mode = "abs"
    cfg.signal.exit.take_profit = 0.05
    cfg.signal.exit.stop_loss = 0.08
    cfg.signal.meanrev.lookback_candles = 24
    cfg.signal.meanrev.z_entry = 1.8
    cfg.learning.min_oos_trades = 5
    cfg.learning.min_consistency = 0.50
    cfg.learning.min_improvement_pct = 0.01

    cfg_yaml = tmp_path / "config.yaml"
    cfg_yaml.write_text(
        "signal:\n  engine: meanrev\n  meanrev:\n    lookback_candles: 24\n    z_entry: 1.8\n"
        "  exit:\n    stop_mode: abs\n    take_profit: 0.05\n    stop_loss: 0.08\n",
        encoding="utf-8",
    )

    datasets = [_make_meanrev_dataset(i, n_bars=420) for i in range(4)]

    # מצב live לעולם לא מיישם שינוי אוטומטית (גם כשעובר את כל השערים)
    cfg.execution.mode = "live"
    store_live = Store(tmp_path / "live.db")
    rep_live = run_self_learning_cycle(
        cfg, store_live, datasets=datasets, apply_changes=True,
        config_path=cfg_yaml, reports_dir=tmp_path / "rep_live",
    )
    assert rep_live.applied is False
    assert (tmp_path / "rep_live" / "learning.json").exists()
    assert len(store_live.recent_learning_runs()) == 1
    store_live.close()

    # מצב paper יכול לרוץ, להעריך ולתעד (ורק עם שיפור מובהק מעדכן YAML)
    cfg.execution.mode = "paper"
    cfg.signal.meanrev.z_entry = 4.9   # פרמטר מוחלש מדי (0 עסקאות baseline -> שוק שיפור מובהק!)
    store_paper = Store(tmp_path / "paper.db")
    rep_paper = run_self_learning_cycle(
        cfg, store_paper, datasets=datasets, apply_changes=True,
        config_path=cfg_yaml, reports_dir=tmp_path / "rep_paper",
    )
    assert rep_paper.candidate_oos > rep_paper.baseline_oos
    assert rep_paper.applied is True
    assert cfg.signal.meanrev.z_entry < 4.9
    assert (tmp_path / "config.yaml.bak").exists()
    store_paper.close()


def test_evaluate_live_signals_resolves_sector_from_market_intel(tmp_path):
    """אותות ללא פוזיציה פתוחה מסווגים לסקטור האמיתי מתוך market_intel ולא נזרקים ל-other."""
    store = Store(tmp_path / "mi_sec.db")
    now = int(time.time())
    t0 = now - 25 * 3600
    store.upsert_market_intel([
        {"condition_id": "c_fed", "token_id": "t_fed", "question": "Fed interest rate cut?", "sector": "macro", "updated_at": now}
    ])
    store.record_signal(Signal(
        "c_fed", "t_fed", "LONG", 0.7, 0.55, 0.50, 0.05, "dip z=-2.2", features={"z": -2.2},
        created_at=datetime.fromtimestamp(t0, tz=timezone.utc),
    ))
    store.insert_ticks([("t_fed", t0 + 24 * 3600, 0.54)])
    n = evaluate_live_signals(store, now_ts=now)
    assert n == 1
    with store.tx() as c:
        row = c.execute("SELECT sector FROM signal_outcomes WHERE token_id='t_fed'").fetchone()
    assert row is not None and row["sector"] == "macro"
    store.close()


def test_signal_outcome_stats_deduplicates_same_hour_repeats(tmp_path):
    """הבוט שומר אותות כל 3 דק'; הסטטיסטיקה מאחדת דגימות חוזרות באותה שעה כדי לא לנפח שוק בודד."""
    store = Store(tmp_path / "dedup.db")
    now = int(time.time())
    hour_base = (now // 3600 - 12) * 3600
    for offset in (60, 240, 420):
        store.record_signal(Signal(
            "c1", "tok-rep", "LONG", 0.8, 0.55, 0.45, 0.05, "dip z=-2.5",
            features={"z": -2.5},
            created_at=datetime.fromtimestamp(hour_base + offset, tz=timezone.utc),
        ))
    store.insert_ticks([("tok-rep", hour_base + 7 * 3600, 0.50)])
    n_upd = evaluate_live_signals(store, now_ts=now)
    assert n_upd == 3
    stats = store.signal_outcome_stats(days=30)
    assert stats["raw_evaluated"] == 3
    assert stats["total_evaluated"] == 1
    assert stats["actionable"]["n"] == 1
    store.close()


