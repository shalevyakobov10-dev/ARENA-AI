"""
מנוע למידה עצמית ל-PERPS — בודק תקופת 30 יום על נרות אמיתיים ומשפר פרמטרים רק אחרי 4 שערי OOS.
"""
from __future__ import annotations

import copy
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..config import DEFAULT_CONFIG, Config
from ..data.news import evaluate_news_alpha
from ..data.store import Store
from .backtest import run_perp_walkforward
from .exchange import MultiPerpExchange
from .signals import assess_perps_news

log = logging.getLogger(__name__)


def evaluate_perp_live_signals(store: Store, *, now_ts: int | None = None, limit: int = 400) -> int:
    """מעריך תוצאות אותות PERPS חיים מול נרות perp_candles (1ש', 4ש', 12ש') ומחירי intel בזמן אמת."""
    now = int(now_ts or time.time())
    pending = store.pending_perp_signals_for_outcome(min_age_hours=0.25, limit=limit, now_ts=now)
    if not pending:
        return 0
    news_rows = [dict(r) for r in store.recent_news(hours=24 * 10, limit=250)]
    live_intel = {str(r.get("symbol") or ""): r for r in store.recent_perp_intel(limit=40)}
    updated = 0
    for row in pending:
        sym = str(row["symbol"] or "")
        ts = int(row["ts"] or 0)
        entry_px = row["price"]
        direction = str(row["direction"] or "FLAT")
        if not sym or not entry_px or direction not in ("LONG", "SHORT"):
            continue
        entry_px = float(entry_px)
        p1 = store.nearest_perp_candle_price(sym, ts + 3600, window_sec=3600) if now >= ts + 3600 else None
        if p1 is None and now >= ts + 900:
            # השלמת mark-to-market חיה לאותות בני 15-59 דק' מתוך perp_intel כדי להזין למידה מוקדמת
            intel_row = live_intel.get(sym)
            intel_ts = int(intel_row.get("updated_at") or intel_row.get("ts") or 0) if intel_row else 0
            if intel_row and intel_row.get("price") and intel_ts >= ts + 600:
                p1 = float(intel_row["price"])
        p4 = store.nearest_perp_candle_price(sym, ts + 4 * 3600, window_sec=5400) if now >= ts + 4 * 3600 else None
        p12 = store.nearest_perp_candle_price(sym, ts + 12 * 3600, window_sec=5400) if now >= ts + 12 * 3600 else None
        if p1 is None and p4 is None and p12 is None:
            continue

        mult = 1.0 if direction == "LONG" else -1.0
        r1 = round((p1 - entry_px) / entry_px * 100.0 * mult, 3) if p1 is not None else None
        r4 = round((p4 - entry_px) / entry_px * 100.0 * mult, 3) if p4 is not None else None
        r12 = round((p12 - entry_px) / entry_px * 100.0 * mult, 3) if p12 is not None else None
        feats = {}
        try:
            feats = json.loads(row["features"] or "{}")
        except Exception:
            pass
        ni = float(feats.get("news_impact") or 0.0)
        if ni == 0.0 and news_rows:
            sub_n = [n for n in news_rows if ts - 4 * 3600 <= int(n.get("ts") or 0) <= ts]
            if sub_n:
                ni = assess_perps_news(sym, sub_n, window_hours=4.0).get("max_impact", 0.0)

        store.upsert_perp_signal_outcome({
            "signal_id": int(row["id"]),
            "symbol": sym,
            "ts": ts,
            "direction": direction,
            "entry_price": entry_px,
            "regime": str(row["regime"] or ""),
            "strategy": str(row["strategy"] or ""),
            "z_score": feats.get("z"),
            "score": float(row["score"] or 0.0),
            "leverage": float(row["leverage"] or 1.0),
            "news_impact": ni,
            "price_1h": p1, "price_4h": p4, "price_12h": p12,
            "realized_1h_pct": r1, "realized_4h_pct": r4, "realized_12h_pct": r12,
            "evaluated_at": now,
        })
        updated += 1
    return updated


@dataclass
class PerpLearningReport:
    ts: int
    mode: str
    baseline_oos_pct: float
    candidate_oos_pct: float
    consistency: float
    oos_trades: int
    liquidations: int
    applied: bool
    summary: str
    candidate_cfg: dict[str, Any]


def _save_perp_yaml(path: Path, cand: dict[str, Any]) -> None:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    perps = raw.setdefault("perps", {})
    sig = perps.setdefault("signal", {})
    rk = perps.setdefault("risk", {})
    for k in ("z_entry", "adx_trend_threshold"):
        if k in cand:
            sig[k] = float(cand[k])
    for k in ("sl_atr_mult", "tp_atr_mult", "trailing_trigger_atr", "trailing_dist_atr"):
        if k in cand:
            rk[k] = float(cand[k])
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(raw, fh, allow_unicode=True, sort_keys=False)


def _apply_perp_cand(cfg: Config, cand: dict[str, Any]) -> None:
    for k in ("z_entry", "adx_trend_threshold"):
        if k in cand:
            setattr(cfg.perps.signal, k, float(cand[k]))
    for k in ("sl_atr_mult", "tp_atr_mult", "trailing_trigger_atr", "trailing_dist_atr"):
        if k in cand:
            setattr(cfg.perps.risk, k, float(cand[k]))


def run_perp_self_learning_cycle(
    cfg: Config,
    store: Store,
    *,
    exchange: MultiPerpExchange | None = None,
    datasets=None,
    funding_map=None,
    apply_changes: bool = True,
    config_path: str | Path | None = None,
    reports_dir: str | Path = "reports",
) -> PerpLearningReport:
    now = int(time.time())
    evaluate_perp_live_signals(store, now_ts=now)
    evaluate_news_alpha(store, now_ts=now)
    if datasets is None:
        ex = exchange or MultiPerpExchange(cfg.perps.exchange)
        insts = ex.scan()[:16]
        datasets = {}
        funding_map = {}
        for inst in insts:
            cs = ex.get_candles(inst, interval=cfg.perps.signal.timeframe, lookback=720)
            if len(cs) >= 360:
                datasets[inst.symbol] = (inst, cs)
                if inst.hl_funding_1h is not None:
                    funding_map[inst.symbol] = ex.hl.get_funding_history(inst.symbol, days=30)

    if not datasets:
        rep = PerpLearningReport(
            ts=now, mode=cfg.perps.mode, baseline_oos_pct=0.0, candidate_oos_pct=0.0,
            consistency=0.0, oos_trades=0, liquidations=0, applied=False,
            summary="לא נאספו מספיק נרות Perps לכיול Walk-Forward", candidate_cfg={},
        )
        return rep

    base_wf = run_perp_walkforward(cfg.perps, datasets, funding_map=funding_map, folds=3)
    base_snap = {
        "z_entry": cfg.perps.signal.z_entry,
        "adx_trend_threshold": cfg.perps.signal.adx_trend_threshold,
        "sl_atr_mult": cfg.perps.risk.sl_atr_mult,
        "tp_atr_mult": cfg.perps.risk.tp_atr_mult,
        "trailing_trigger_atr": cfg.perps.risk.trailing_trigger_atr,
        "trailing_dist_atr": cfg.perps.risk.trailing_dist_atr,
    }

    grid = [
        {"z_entry": 1.8, "adx_trend_threshold": 25.0, "sl_atr_mult": 1.5, "tp_atr_mult": 2.6, "trailing_trigger_atr": 1.4, "trailing_dist_atr": 0.95},
        {"z_entry": 1.8, "adx_trend_threshold": 25.0, "sl_atr_mult": 1.5, "tp_atr_mult": 2.6, "trailing_trigger_atr": 1.4, "trailing_dist_atr": 1.0},
        {"z_entry": 1.8, "adx_trend_threshold": 25.0, "sl_atr_mult": 1.5, "tp_atr_mult": 2.6, "trailing_trigger_atr": 1.2, "trailing_dist_atr": 1.0},
        {"z_entry": 1.8, "adx_trend_threshold": 25.0, "sl_atr_mult": 1.7, "tp_atr_mult": 3.0, "trailing_trigger_atr": 1.4, "trailing_dist_atr": 0.95},
        {"z_entry": 1.9, "adx_trend_threshold": 24.0, "sl_atr_mult": 1.5, "tp_atr_mult": 2.6, "trailing_trigger_atr": 1.4, "trailing_dist_atr": 0.95},
    ]

    best_wf = base_wf
    best_cand: dict[str, Any] = dict(base_snap)
    for cand in grid:
        pc_test = copy.deepcopy(cfg.perps)
        pc_test.signal.z_entry = cand["z_entry"]
        pc_test.signal.adx_trend_threshold = cand["adx_trend_threshold"]
        pc_test.risk.sl_atr_mult = cand["sl_atr_mult"]
        pc_test.risk.tp_atr_mult = cand["tp_atr_mult"]
        pc_test.risk.trailing_trigger_atr = cand["trailing_trigger_atr"]
        pc_test.risk.trailing_dist_atr = cand["trailing_dist_atr"]
        wf = run_perp_walkforward(pc_test, datasets, funding_map=funding_map, folds=3)
        if (
            wf.total_liqs == 0
            and wf.consistency >= 0.66
            and wf.total_trades >= 20
            and wf.oos_return_pct > best_wf.oos_return_pct
        ):
            best_wf = wf
            best_cand = cand

    improved = (
        best_cand != base_snap
        and best_wf.total_liqs == 0
        and best_wf.consistency >= 0.66
        and best_wf.oos_return_pct > max(base_wf.oos_return_pct * 1.10, base_wf.oos_return_pct + 2.0)
    )
    applied = False
    if apply_changes and improved and cfg.perps.mode == "paper":
        _apply_perp_cand(cfg, best_cand)
        _save_perp_yaml(Path(config_path) if config_path else DEFAULT_CONFIG, best_cand)
        applied = True
        summary = f"קודמו פרמטרי Perps: OOS {base_wf.oos_return_pct:+.2f}% → {best_wf.oos_return_pct:+.2f}% (0 ליקווידציות)"
    else:
        summary = (
            f"קונפיג Perps מכויל נשמר ({base_wf.oos_return_pct:+.2f}% OOS · "
            f"עקביות {base_wf.consistency*100:.0f}% · {base_wf.total_trades} עסקאות · {base_wf.total_liqs} ליקווידציות)"
        )

    store.record_perp_learning_run(
        mode=cfg.perps.mode,
        baseline_oos=base_wf.oos_return_pct,
        candidate_oos=best_wf.oos_return_pct,
        consistency=best_wf.consistency,
        oos_trades=best_wf.total_trades,
        baseline_cfg=base_snap,
        candidate_cfg=best_cand,
        applied=applied,
        summary=summary,
        details={"liquidations": best_wf.total_liqs},
    )
    rdir = Path(reports_dir)
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "perps_learning.md").write_text(
        f"# דוח למידה עצמית PERPS ×50\n\n- **סטטוס:** {summary}\n"
        f"- **Baseline OOS:** {base_wf.oos_return_pct:+.2f}% ({base_wf.total_trades} עסקאות, {base_wf.total_liqs} ליקווידציות)\n"
        f"- **מועמד OOS:** {best_wf.oos_return_pct:+.2f}% ({best_wf.total_trades} עסקאות, עקביות {best_wf.consistency*100:.0f}%)\n",
        encoding="utf-8",
    )
    return PerpLearningReport(
        ts=now, mode=cfg.perps.mode,
        baseline_oos_pct=base_wf.oos_return_pct, candidate_oos_pct=best_wf.oos_return_pct,
        consistency=best_wf.consistency, oos_trades=best_wf.total_trades,
        liquidations=best_wf.total_liqs, applied=applied, summary=summary, candidate_cfg=best_cand,
    )
