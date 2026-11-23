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
from ..data.store import Store
from .backtest import run_perp_walkforward
from .exchange import MultiPerpExchange

log = logging.getLogger(__name__)


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
    for k in ("sl_atr_mult", "tp_atr_mult"):
        if k in cand:
            rk[k] = float(cand[k])
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(raw, fh, allow_unicode=True, sort_keys=False)


def _apply_perp_cand(cfg: Config, cand: dict[str, Any]) -> None:
    for k in ("z_entry", "adx_trend_threshold"):
        if k in cand:
            setattr(cfg.perps.signal, k, float(cand[k]))
    for k in ("sl_atr_mult", "tp_atr_mult"):
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
    }

    grid = [
        {"z_entry": 1.8, "adx_trend_threshold": 25.0, "sl_atr_mult": 1.7, "tp_atr_mult": 3.0},
        {"z_entry": 1.8, "adx_trend_threshold": 25.0, "sl_atr_mult": 1.5, "tp_atr_mult": 2.6},
        {"z_entry": 1.9, "adx_trend_threshold": 24.0, "sl_atr_mult": 1.7, "tp_atr_mult": 3.0},
        {"z_entry": 1.7, "adx_trend_threshold": 26.0, "sl_atr_mult": 1.8, "tp_atr_mult": 3.2},
    ]

    best_wf = base_wf
    best_cand: dict[str, Any] = dict(base_snap)
    for cand in grid:
        pc_test = copy.deepcopy(cfg.perps)
        pc_test.signal.z_entry = cand["z_entry"]
        pc_test.signal.adx_trend_threshold = cand["adx_trend_threshold"]
        pc_test.risk.sl_atr_mult = cand["sl_atr_mult"]
        pc_test.risk.tp_atr_mult = cand["tp_atr_mult"]
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
