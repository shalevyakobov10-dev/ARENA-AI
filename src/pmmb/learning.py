"""
מנוע הלמידה העצמית הרציף (Self-Learning & Adaptive Walk-Forward).

סוגר שלוש לולאות שיפור מתמידות בלי לשבור את חוק הברזל נגד overfit:
  1. מעקב תוצאות אותות בזמן אמת (Live Signal Outcomes — 6ש' / 24ש' / 48ש').
  2. השוואה ישירה של Baseline פעיל מול מועמדי פרמטרים ב-Walk-Forward OOS.
  3. קידום מבוקר של פרמטרים רק לאחר שעברו 4 שערי אימות קשיחים
     (ובמצב paper בלבד אלא אם אושר במפורש אחרת).
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .backtest import Backtester
from .config import DEFAULT_CONFIG, Config
from .data.clob import Candle
from .models import Market
from .sectors import classify
from .walkforward import _NoNet, _apply, _evaluate, _snapshot_cfg, run_walkforward

log = logging.getLogger(__name__)


def _extract_z(features_raw: str | None, reason: str | None) -> float | None:
    try:
        feats = json.loads(features_raw or "{}")
        if "z" in feats and feats["z"] is not None:
            return float(feats["z"])
    except Exception:
        pass
    m = re.search(r"z=([+-]?\d+(?:\.\d+)?)", reason or "")
    return float(m.group(1)) if m else None


def evaluate_live_signals(
    store,
    *,
    clob=None,
    now_ts: int | None = None,
    limit: int = 800,
) -> int:
    """
    בודק אותות עבר ב-DB מול תנועת המחיר האמיתית כעבור 6ש', 24ש' ו-48ש'.
    מחזיר כמה רשומות עודכנו.
    """
    now = int(now_ts or time.time())
    pending = store.pending_signals_for_outcome(min_age_hours=6.0, limit=limit)
    if not pending:
        return 0

    news_rows = store.recent_news(hours=24 * 14, limit=400)
    # מפה זריזה של שאלה לפי token_id אם קיימת ב-positions
    pos_q = {}
    with store.tx() as c:
        for r in c.execute("SELECT token_id, question FROM positions"):
            pos_q[r["token_id"]] = r["question"] or ""

    updated = 0
    history_cache: dict[str, list[Candle]] = {}
    clob_fetches = 0
    max_clob_fetches = 12

    def _price_at(token_id: str, target_ts: int) -> float | None:
        nonlocal clob_fetches
        px = store.nearest_tick_price(token_id, target_ts, window_sec=7200)
        if px is not None:
            return px
        if clob is None:
            return None
        if token_id not in history_cache:
            if clob_fetches >= max_clob_fetches:
                return None
            clob_fetches += 1
            try:
                history_cache[token_id] = clob.get_history(
                    token_id, fidelity_min=60, lookback_candles=168, use_cache=True
                )
            except Exception:
                history_cache[token_id] = []
        candles = history_cache[token_id]
        best = None
        best_dt = 7200
        for c in candles:
            dt = abs(int(c.ts) - target_ts)
            if dt <= best_dt:
                best_dt = dt
                best = float(c.price)
        return best

    for row in pending:
        ts = int(row["ts"])
        tid = str(row["token_id"] or "")
        entry_px = row["market_price"]
        if not tid or entry_px is None:
            continue
        entry_px = float(entry_px)
        direction = str(row["direction"] or "FLAT")

        p6 = _price_at(tid, ts + 6 * 3600) if now >= ts + 6 * 3600 else None
        p24 = _price_at(tid, ts + 24 * 3600) if now >= ts + 24 * 3600 else None
        p48 = _price_at(tid, ts + 48 * 3600) if now >= ts + 48 * 3600 else None
        if p6 is None and p24 is None and p48 is None:
            continue

        mult = -1.0 if direction == "SHORT" else 1.0
        r6 = round((p6 - entry_px) * mult, 5) if p6 is not None else None
        r24 = round((p24 - entry_px) * mult, 5) if p24 is not None else None
        r48 = round((p48 - entry_px) * mult, 5) if p48 is not None else None

        q_text = pos_q.get(tid, "")
        sec = classify(q_text, "") if q_text else "other"
        short_tid = tid[:12]
        imp = 0.0
        for nr in news_rows:
            nts = int(nr["ts"])
            if ts - 6 * 3600 <= nts <= ts and short_tid in str(nr["matched_tokens"] or ""):
                imp = max(imp, float(nr["impact"] or 0.0))

        store.upsert_signal_outcome({
            "signal_id": int(row["id"]),
            "token_id": tid,
            "ts": ts,
            "direction": direction,
            "entry_price": entry_px,
            "fair_price": row["fair_price"],
            "edge": row["edge"],
            "z_score": _extract_z(row["features"], row["reason"]),
            "sector": sec,
            "news_impact": imp,
            "price_6h": p6,
            "price_24h": p24,
            "price_48h": p48,
            "realized_6h": r6,
            "realized_24h": r24,
            "realized_48h": r48,
            "evaluated_at": now,
        })
        updated += 1
    return updated


def _eval_fixed_oos(
    cfg: Config,
    datasets: list[tuple[Market, list[Candle]]],
    *,
    folds: int = 3,
    spread: float = 0.01,
) -> tuple[float, int]:
    """מודד מה הייתה התוצאה של הקונפיגורציה הפעילה על אותם חלונות OOS בדיוק."""
    ts_all = [c.ts for _, candles in datasets for c in candles]
    t0, t1 = min(ts_all), max(ts_all)
    span = t1 - t0
    first_train = int(span * 0.4)
    fold_span = int((span - first_train) / folds)
    bt = Backtester(cfg, clob=_NoNet())
    total_pnl = 0.0
    total_trades = 0
    for k in range(folds):
        test_start = t0 + first_train + k * fold_span
        test_end = test_start + fold_span
        pnl, n = _evaluate(bt, datasets, cfg, test_start, test_end, spread)
        total_pnl += pnl
        total_trades += n
    return round(total_pnl, 2), total_trades


def _majority_params(folds) -> dict:
    """בוחר את צירוף הפרמטרים המוביל של החלון האחרון (מעודכן ביותר לשוק הנוכחי)."""
    if not folds:
        return {}
    return dict(folds[-1].best_params)


@dataclass
class LearningReport:
    ts: int
    mode: str
    signals_evaluated: int
    baseline_oos: float
    baseline_trades: int
    candidate_oos: float
    candidate_oos_ex_top: float
    candidate_trades: int
    consistency: float
    baseline_cfg: dict[str, Any]
    candidate_cfg: dict[str, Any]
    applied: bool
    summary: str
    live_stats: dict[str, Any] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "mode": self.mode,
            "signals_evaluated": self.signals_evaluated,
            "baseline_oos": self.baseline_oos,
            "baseline_trades": self.baseline_trades,
            "candidate_oos": self.candidate_oos,
            "candidate_oos_ex_top": self.candidate_oos_ex_top,
            "candidate_trades": self.candidate_trades,
            "consistency": round(self.consistency, 3),
            "baseline_cfg": self.baseline_cfg,
            "candidate_cfg": self.candidate_cfg,
            "applied": self.applied,
            "summary": self.summary,
            "live_stats": self.live_stats,
            "insights": self.insights,
        }


def _save_learned_yaml(cfg_path: Path, candidate: dict[str, Any]) -> bool:
    if not cfg_path.exists():
        return False
    raw_text = cfg_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw_text) or {}
    sig = data.setdefault("signal", {})
    mr = sig.setdefault("meanrev", {})
    ex = sig.setdefault("exit", {})

    changed = False
    for k in ("z_entry", "lookback_candles", "reversion_ratio", "trend_guard",
              "rsi_max", "max_spread_to_edge"):
        if k in candidate and mr.get(k) != candidate[k]:
            mr[k] = candidate[k]
            changed = True
    for k in ("take_profit", "stop_loss"):
        if k in candidate and ex.get(k) != candidate[k]:
            ex[k] = candidate[k]
            changed = True
    if not changed:
        return False

    cfg_path.with_suffix(".yaml.bak").write_text(raw_text, encoding="utf-8")
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return True


def _build_insights(live_stats: dict[str, Any], min_n: int = 12) -> list[str]:
    insights: list[str] = []
    act = live_stats.get("actionable") or {}
    if act.get("n", 0) >= min_n:
        insights.append(
            f"אותות חיים: {act['n']} מדודים | Hit (אופק אחרון): {act.get('hit_latest_pct')}% | ממוצע {act.get('mean_latest'):+.4f}"
        )
    for bucket, row in (live_stats.get("by_z_bucket") or {}).items():
        if row.get("n", 0) >= 5:
            insights.append(
                f"טווח z={bucket}: {row['n']} אותות | הצלחה {row.get('hit_latest_pct')}% | תשואה {row.get('mean_latest'):+.4f}"
            )
    for sec, row in (live_stats.get("by_sector") or {}).items():
        if row.get("n", 0) >= min_n and (row.get("hit_latest_pct") or 100) < 30 and (row.get("mean_latest") or 0) < -0.02:
            insights.append(f"⚠️ סקטור חלש בלייב: {sec} ({row['hit_latest_pct']}% hit על {row['n']} אותות)")
    bn = live_stats.get("by_news") or {}
    q_n = (bn.get("quiet") or {}).get("n", 0)
    c_n = (bn.get("news_catalyst") or {}).get("n", 0)
    if q_n >= 5 and c_n >= 3:
        insights.append(
            f"השוואת חדשות: שוק שקט {bn['quiet'].get('hit_latest_pct')}% hit מול גל חדשות {bn['news_catalyst'].get('hit_latest_pct')}%"
        )
    return insights


def run_self_learning_cycle(
    cfg: Config,
    store,
    *,
    gamma=None,
    clob=None,
    datasets: list[tuple[Market, list[Candle]]] | None = None,
    apply_changes: bool = True,
    config_path: str | Path | None = None,
    reports_dir: str | Path = "reports",
) -> LearningReport:
    """
    מריץ מחזור למידה עצמית מלא:
    1. הערכת תוצאות אותות קודמים ב-DB.
    2. איסוף היסטוריה עדכנית (אם לא הוזרקו datasets).
    3. השוואת Baseline מול Walk-Forward OOS.
    4. שמירת דוח + עדכון פרמטרים מבוקר (ב-paper בלבד כברירת מחדל).
    """
    now = int(time.time())
    evaluated = evaluate_live_signals(store, clob=clob, now_ts=now)
    live_stats = store.signal_outcome_stats(days=30)
    insights = _build_insights(live_stats, min_n=cfg.learning.min_live_signals_for_alert)

    if datasets is None and gamma is not None and clob is not None:
        from .data.gamma import MarketUniverse
        from .signals import build_signal_engine

        eng = build_signal_engine(cfg.signal)
        markets = MarketUniverse(gamma, cfg.universe).scan()[: cfg.learning.max_markets]
        datasets = []
        for mk in markets:
            try:
                candles = clob.get_history(
                    mk.yes_token_id, fidelity_min=60, lookback_candles=720, use_cache=True
                )
            except Exception:
                candles = []
            if len(candles) >= eng.min_candles + 120:
                datasets.append((mk, candles))

    baseline_snap = _snapshot_cfg(cfg)
    if not datasets:
        rep = LearningReport(
            ts=now, mode=cfg.execution.mode, signals_evaluated=evaluated,
            baseline_oos=0.0, baseline_trades=0, candidate_oos=0.0,
            candidate_oos_ex_top=0.0, candidate_trades=0, consistency=0.0,
            baseline_cfg=baseline_snap, candidate_cfg={}, applied=False,
            summary="הושלמה הערכת אותות חיים; לא סופקו מספיק שווקים ל-Walk-Forward",
            live_stats=live_stats, insights=insights,
        )
        store.record_learning_run(
            mode=cfg.execution.mode, baseline_oos=0.0, candidate_oos=0.0,
            consistency=0.0, oos_trades=0, baseline_cfg=baseline_snap,
            candidate_cfg={}, applied=False, summary=rep.summary,
            details=rep.as_dict(),
        )
        _write_learning_reports(rep, reports_dir)
        return rep

    base_oos, base_trades = _eval_fixed_oos(cfg, datasets, folds=3, spread=0.01)
    wf = run_walkforward(cfg, datasets, folds=3, spread=0.01)
    cand = _majority_params(wf.folds)
    cand_oos = round(wf.oos_pnl, 2)
    cand_ex_top = round(wf.oos_pnl_ex_top, 2)

    # בדיקת 4 שערי הקידום
    lr = cfg.learning
    min_req = base_oos * (1.0 + lr.min_improvement_pct) if base_oos > 0 else max(5.0, abs(base_oos) * 0.25)
    passed_gates = (
        wf.oos_trades >= lr.min_oos_trades
        and wf.consistency >= lr.min_consistency
        and cand_ex_top > 0
        and cand_oos > min_req
    )
    can_apply = (
        apply_changes
        and passed_gates
        and ((cfg.execution.mode == "paper" and lr.auto_apply_paper)
             or (cfg.execution.mode == "live" and lr.allow_auto_apply_live))
    )

    applied = False
    if can_apply and cand:
        cfg_file = Path(config_path) if config_path else DEFAULT_CONFIG
        _apply(cfg, cand)
        if cfg_file.exists():
            _save_learned_yaml(cfg_file, cand)
        applied = True
        summary = (
            f"קודמו פרמטרים משופרים: OOS {base_oos:+.2f} → {cand_oos:+.2f} "
            f"(עקביות {wf.consistency*100:.0f}%, ללא מוביל {cand_ex_top:+.2f})"
        )
        store.event("learning_promoted", summary, data={"candidate": cand, "baseline": baseline_snap})
    elif passed_gates:
        summary = (
            f"נמצא שיפור מאומת ({base_oos:+.2f} → {cand_oos:+.2f}) — ממתין לאישור במצב {cfg.execution.mode}"
        )
    else:
        summary = (
            f"הקונפיגורציה הנוכחית נשמרה ({base_oos:+.2f} OOS מול מועמד {cand_oos:+.2f}, "
            f"עקביות {wf.consistency*100:.0f}%, {wf.oos_trades} עסקאות)"
        )

    rep = LearningReport(
        ts=now, mode=cfg.execution.mode, signals_evaluated=evaluated,
        baseline_oos=base_oos, baseline_trades=base_trades,
        candidate_oos=cand_oos, candidate_oos_ex_top=cand_ex_top,
        candidate_trades=wf.oos_trades, consistency=wf.consistency,
        baseline_cfg=baseline_snap, candidate_cfg=cand,
        applied=applied, summary=summary, live_stats=live_stats, insights=insights,
    )
    store.record_learning_run(
        mode=cfg.execution.mode,
        baseline_oos=base_oos,
        candidate_oos=cand_oos,
        consistency=wf.consistency,
        oos_trades=wf.oos_trades,
        baseline_cfg=baseline_snap,
        candidate_cfg=cand,
        applied=applied,
        summary=summary,
        details=rep.as_dict(),
    )
    _write_learning_reports(rep, reports_dir)
    return rep


def _write_learning_reports(rep: LearningReport, reports_dir: str | Path) -> None:
    rdir = Path(reports_dir)
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "learning.json").write_text(
        json.dumps(rep.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# דוח למידה עצמית והתאמה מתמדת (PMMB Self-Learning)",
        "",
        f"- **סטטוס:** {rep.summary}",
        f"- **אותות חיים שהוערכו הפעם:** {rep.signals_evaluated}",
        f"- **Baseline OOS:** {rep.baseline_oos:+.2f} USDC ({rep.baseline_trades} עסקאות)",
        f"- **מועמד OOS:** {rep.candidate_oos:+.2f} USDC ({rep.candidate_trades} עסקאות · עקביות {rep.consistency*100:.0f}% · ללא מוביל {rep.candidate_oos_ex_top:+.2f})",
        f"- **יושם לקונפיג:** {'כן ✅' if rep.applied else 'לא (נשמרה הגנה)'}",
    ]
    if rep.insights:
        lines += ["", "## תובנות מזמן אמת"] + [f"- {x}" for x in rep.insights]
    (rdir / "learning.md").write_text("\n".join(lines), encoding="utf-8")
