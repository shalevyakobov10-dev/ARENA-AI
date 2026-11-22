"""
Walk-forward — הכיול היחיד ששווה משהו.

הרעיון: מחלקים את ציר הזמן לחלונות. על חלון N מכיילים פרמטרים
(בדיוק כמו `tune`), ואז מריצים אותם על חלון N+1 **שלא נראה בכיול**.
מה שמעניין הוא לא הביצועים בתוך הכיול (שם תמיד טוב) אלא מה קורה בחוץ.

אם פרמטרים שנבחרו בחלון 1 לא מחזיקים בחלון 2 — אין edge, יש רעש.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .backtest import Backtester, BacktestResult
from .config import Config
from .data.clob import Candle
from .models import Market

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
def grid_for(engine_name: str, stop_mode: str = "pct") -> list[dict]:
    """גריד לכל מנוע. קטן בכוונה — כל פרמטר נוסף = עוד סיכוי ל-overfit."""
    if engine_name == "meanrev":
        if stop_mode == "abs":
            return [
                {"z_entry": z, "rsi_max": rsi, "lookback_candles": lb,
                 "reversion_ratio": 0.55, "min_score": 0.55, "trend_guard": False,
                 "take_profit": tp, "stop_loss": sl}
                for z in (1.7, 1.8, 2.0)
                for lb in (12, 24)
                for rsi in (40.0, 45.0)
                for tp, sl in ((0.05, 0.07), (0.05, 0.08))
            ]
        return [
            {"z_entry": z, "reversion_ratio": r, "min_score": ms,
             "trend_guard": tg, "take_profit": tp, "stop_loss": sl}
            for z in (1.2, 1.5, 2.0)
            for r in (0.4, 0.55, 0.7)
            for ms in (0.55,)
            for tg in (False,)
            for tp, sl in ((0.06, 0.10), (0.10, 0.12))
        ]
    return [
        {"min_score": ms, "min_edge": me, "trend_filter": tf,
         "take_profit": tp, "stop_loss": sl}
        for ms in (0.45, 0.55, 0.65)
        for me in (0.02, 0.05)
        for tf in (True, False)
        for tp, sl in ((0.08, 0.05), (0.12, 0.07))
    ]


def _snapshot_cfg(cfg: Config) -> dict:
    sig = cfg.signal
    return {
        "min_score": sig.min_score,
        "min_edge": sig.min_edge,
        "trend_filter": sig.trend_filter,
        "z_entry": sig.meanrev.z_entry,
        "reversion_ratio": sig.meanrev.reversion_ratio,
        "trend_guard": sig.meanrev.trend_guard,
        "lookback_candles": sig.meanrev.lookback_candles,
        "rsi_max": sig.meanrev.rsi_max,
        "max_spread_to_edge": sig.meanrev.max_spread_to_edge,
        "take_profit": sig.exit.take_profit,
        "stop_loss": sig.exit.stop_loss,
    }


def _apply(cfg: Config, params: dict) -> None:
    sig = cfg.signal
    for key in ("min_score", "min_edge", "trend_filter"):
        if key in params:
            setattr(sig, key, params[key])
    for key in ("z_entry", "reversion_ratio", "trend_guard", "lookback_candles",
                "rsi_max", "max_spread_to_edge"):
        if key in params:
            setattr(sig.meanrev, key, params[key])
    if "take_profit" in params:
        sig.exit.take_profit = params["take_profit"]
    if "stop_loss" in params:
        sig.exit.stop_loss = params["stop_loss"]


# ----------------------------------------------------------------------
@dataclass
class Fold:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    best_params: dict = field(default_factory=dict)
    train_pnl: float = 0.0
    train_trades: int = 0
    oos_pnl: float = 0.0
    oos_trades: int = 0
    oos_wins: int = 0
    oos_pnl_ex_top: float = 0.0

    @property
    def oos_win_rate(self) -> float:
        return self.oos_wins / self.oos_trades * 100 if self.oos_trades else 0.0


@dataclass
class WalkForwardResult:
    engine: str
    folds: list[Fold]
    starting_cash_per_market: float
    stop_mode: str = "pct"
    oos_by_market: dict[str, float] = field(default_factory=dict)

    @property
    def oos_pnl(self) -> float:
        return sum(f.oos_pnl for f in self.folds)

    @property
    def oos_pnl_ex_top(self) -> float:
        if not self.oos_by_market:
            return self.oos_pnl
        top = max(self.oos_by_market.values(), default=0.0)
        return self.oos_pnl - max(0.0, top)

    @property
    def positive_markets(self) -> tuple[int, int]:
        pos = sum(1 for v in self.oos_by_market.values() if v > 0)
        return pos, len(self.oos_by_market)

    @property
    def oos_trades(self) -> int:
        return sum(f.oos_trades for f in self.folds)

    @property
    def consistency(self) -> float:
        """שיעור החלונות שבהם ה-OOS היה חיובי — המדד החשוב ביותר."""
        return sum(1 for f in self.folds if f.oos_pnl > 0) / len(self.folds) if self.folds else 0.0

    def to_markdown(self) -> str:
        lines = [
            f"# Walk-Forward — מנוע `{self.engine}` (stop_mode={self.stop_mode})",
            "",
            "| חלון | אימון | מבחן | פרמטרים שנבחרו | PnL באימון | PnL מחוץ למדגם | ללא מוביל | עסקאות | win % |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for f in self.folds:
            p_str = ", ".join(f"{k}={v}" for k, v in f.best_params.items())
            lines.append(
                f"| {f.index} | {_d(f.train_start)}→{_d(f.train_end)} | "
                f"{_d(f.test_start)}→{_d(f.test_end)} | {p_str} | "
                f"{f.train_pnl:+.2f} ({f.train_trades}) | "
                f"**{f.oos_pnl:+.2f}** | {f.oos_pnl_ex_top:+.2f} | "
                f"{f.oos_trades} | {f.oos_win_rate:.0f}% |"
            )
        pos_m, tot_m = self.positive_markets
        lines += [
            "",
            f"**סה\"כ מחוץ למדגם: {self.oos_pnl:+.2f} USDC על {self.oos_trades} עסקאות** "
            f"(ללא השוק המוביל: **{self.oos_pnl_ex_top:+.2f}**, {pos_m}/{tot_m} שווקים חיוביים).",
            f"**עקביות: {self.consistency * 100:.0f}% מהחלונות היו חיוביים.**",
            "",
            "> פרשנות: אם ה-OOS אפסי/שלילי למרות PnL חיובי באימון — הכיול הוא",
            "> התאמה לרעש. אם ה-OOS חיובי ברוב החלונות וגם ללא שוק יחיד — יש edge רחב.",
        ]
        return "\n".join(lines)


def _d(ts: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d")


# ----------------------------------------------------------------------
def run_walkforward(
    cfg: Config,
    datasets: list[tuple[Market, list[Candle]]],
    *,
    folds: int = 3,
    spread: float = 0.01,
    progress=None,
) -> WalkForwardResult:
    """
    datasets: רשימת (שוק, נרות) — כולם על אותו ציר זמן (פחות או יותר).
    משחזר את cfg בסיום — לא משאיר שינויים לוואי.
    """
    if not datasets:
        raise ValueError("אין דאטה להרצה")

    ts_all = [c.ts for _, candles in datasets for c in candles]
    t0, t1 = min(ts_all), max(ts_all)
    span = t1 - t0
    first_train = int(span * 0.4)
    fold_span = int((span - first_train) / folds)

    bt = Backtester(cfg, clob=_NoNet())
    stop_mode = cfg.signal.exit.stop_mode
    grid = grid_for(cfg.signal.engine, stop_mode=stop_mode)
    result = WalkForwardResult(cfg.signal.engine, [], cfg.execution.starting_cash, stop_mode=stop_mode)
    saved = _snapshot_cfg(cfg)

    try:
        for k in range(folds):
            train_start = t0
            train_end = t0 + first_train + k * fold_span
            test_start = train_end
            test_end = test_start + fold_span
            fold = Fold(k + 1, train_start, train_end, test_start, test_end)

            # --- כיול על חלון האימון ---
            scored = []
            for params in grid:
                _apply(cfg, params)
                pnl, n = _evaluate(bt, datasets, cfg, train_start, train_end, spread)
                scored.append((pnl, n, params))
            if progress:
                progress(f"חלון {k + 1}: כוילו {len(grid)} קונפיגורציות על האימון")
            scored.sort(key=lambda x: -x[0])
            best_pnl, best_n, best = scored[0]
            fold.best_params, fold.train_pnl, fold.train_trades = best, best_pnl, best_n

            # --- מבחן מחוץ למדגם, עם הפרמטרים שנבחרו ---
            _apply(cfg, best)
            oos_pnl, oos_n, oos_wins, by_mk = _evaluate(
                bt, datasets, cfg, test_start, test_end, spread, want_detail=True
            )
            top_mk = max(by_mk.values(), default=0.0)
            fold.oos_pnl = oos_pnl
            fold.oos_trades = oos_n
            fold.oos_wins = oos_wins
            fold.oos_pnl_ex_top = oos_pnl - max(0.0, top_mk)
            for slug, v in by_mk.items():
                result.oos_by_market[slug] = result.oos_by_market.get(slug, 0.0) + v
            result.folds.append(fold)

            log.info(
                "חלון %d | אימון %+.2f (%d עסקאות) | OOS %+.2f (%d עסקאות, ex-top %+.2f)",
                k + 1, best_pnl, best_n, oos_pnl, oos_n, fold.oos_pnl_ex_top,
            )
    finally:
        _apply(cfg, saved)
    return result


class _NoNet:
    """Backtester לא צריך רשת כשהוא מקבל נרות מוכנים."""


def _evaluate(
    bt: Backtester,
    datasets: list[tuple[Market, list[Candle]]],
    cfg: Config,
    start_ts: int,
    end_ts: int,
    spread: float,
    *,
    want_detail: bool = False,
):
    total = 0.0
    n_trades = 0
    wins = 0
    by_market: dict[str, float] = {}
    warmup = bt.engine.min_candles + 5
    for market, candles in datasets:
        window = [c for c in candles if start_ts - warmup * 3600 <= c.ts <= end_ts]
        if len(window) < bt.engine.min_candles + 5:
            continue
        sp = max(getattr(market, "spread", 0.0) or 0.0, spread)
        res: BacktestResult = bt.run(market, window, label=market.slug, spread=sp)
        for t in res.trades:
            # שתי הבדיקות הכרחיות: כניסה ויציאה בתוך החלון — אפס זליגה מחלון החימום
            if start_ts <= t.entry_ts and start_ts <= t.exit_ts <= end_ts:
                total += t.pnl
                n_trades += 1
                wins += 1 if t.pnl > 0 else 0
                by_market[market.slug] = by_market.get(market.slug, 0.0) + t.pnl
    if want_detail:
        return total, n_trades, wins, by_market
    return total, n_trades


def write_walkforward(result: WalkForwardResult, out_dir: str | Path = "reports") -> Path:
    """כותב גם Markdown לבן אדם וגם JSON למכונה (שער ה-readiness קורא אותו)."""
    import json
    from datetime import datetime, timezone

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "walkforward.md"
    path.write_text(result.to_markdown(), encoding="utf-8")
    pos_m, tot_m = result.positive_markets
    (out / "walkforward.json").write_text(json.dumps({
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "engine": result.engine,
        "stop_mode": result.stop_mode,
        "oos_pnl": round(result.oos_pnl, 2),
        "oos_pnl_ex_top": round(result.oos_pnl_ex_top, 2),
        "positive_markets": pos_m,
        "traded_markets": tot_m,
        "oos_trades": result.oos_trades,
        "consistency": round(result.consistency, 3),
        "folds": [{
            "index": f.index, "oos_pnl": round(f.oos_pnl, 2),
            "oos_pnl_ex_top": round(f.oos_pnl_ex_top, 2),
            "oos_trades": f.oos_trades, "oos_win_rate": round(f.oos_win_rate, 1),
            "best_params": f.best_params,
        } for f in result.folds],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
