"""
סימולטור Portfolio & 3-Fold Walk-Forward אמיתי עבור זרוע ה-PERPS עד מינוף ×50.

כולל:
  - Isolated Margin מדויק
  - חישוב Liquidation לפני SL כשצריך + הגנת Liquidation Buffer Guard
  - עמלות Taker + Slippage לכל צד
  - ATR Trailing Stop + Time Stop + Cooldown
  - חלוקת 3 חלונות Walk-Forward OOS ללא זליגת מידע
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import PerpsConfig
from .models import PerpCandle, PerpInstrument, PerpPosition
from .risk import PerpRiskManager, calc_liquidation_price
from .signals import ProMultiRegimeEngine


@dataclass
class PerpBacktestSummary:
    trades: int = 0
    wins: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    return_pct: float = 0.0
    ending_equity: float = 1000.0
    max_drawdown_pct: float = 0.0
    liquidations: int = 0
    avg_leverage: float = 0.0
    max_leverage_used: float = 0.0
    fees_paid: float = 0.0
    funding_net: float = 0.0
    by_strategy: dict[str, float] = field(default_factory=dict)
    by_side: dict[str, float] = field(default_factory=dict)


def run_perp_portfolio_backtest(
    cfg: PerpsConfig,
    datasets: dict[str, tuple[PerpInstrument, list[PerpCandle]]],
    *,
    funding_map: dict[str, dict[int, float]] | None = None,
    eval_start_ts: int | None = None,
    eval_end_ts: int | None = None,
) -> PerpBacktestSummary:
    if not datasets:
        return PerpBacktestSummary(ending_equity=cfg.risk.starting_cash)

    all_ts = sorted({c.ts for _, cs in datasets.values() for c in cs})
    if not all_ts:
        return PerpBacktestSummary(ending_equity=cfg.risk.starting_cash)
    start_ts = eval_start_ts or all_ts[min(105, len(all_ts) - 1)]
    end_ts = eval_end_ts or all_ts[-1]

    idx_map = {sym: {c.ts: i for i, c in enumerate(cs)} for sym, (_, cs) in datasets.items()}
    engine = ProMultiRegimeEngine(cfg)
    risk = PerpRiskManager(cfg)

    cash = cfg.risk.starting_cash
    peak = cash
    max_dd = 0.0
    positions: dict[str, PerpPosition] = {}
    trades: list[tuple[str, str, str, float, float]] = []
    liqs = 0
    fees_paid = 0.0
    funding_net = 0.0
    rt_cost_one = (cfg.taker_fee_bps + cfg.slippage_bps) / 10_000.0

    for ts in all_ts:
        if ts < start_ts or ts > end_ts:
            continue
        now_dt = datetime.fromtimestamp(ts, tz=timezone.utc)

        # 1. יציאות + מימון + Trailing
        for sym in list(positions.keys()):
            pos = positions[sym]
            inst, cs = datasets[sym]
            ci = idx_map[sym].get(ts)
            if ci is None:
                continue
            bar = cs[ci]
            fr = (funding_map or {}).get(sym, {}).get(ts, 0.0)
            if fr:
                f_pnl = (-pos.notional * fr) if pos.side == "LONG" else (pos.notional * fr)
                pos.accumulated_funding += f_pnl
                cash += f_pnl
                funding_net += f_pnl

            reason = risk.evaluate_exit_and_trail(
                pos, mark_price=bar.close, high_price=bar.high, low_price=bar.low, now=now_dt
            )
            if reason is None:
                continue

            is_liq = "ליקווידציה" in reason
            if is_liq:
                liqs += 1
                net_pnl = -pos.margin_used + pos.accumulated_funding
                cash += 0.0
            else:
                exit_px = (
                    pos.stop_price if "סטופ" in reason
                    else (pos.target_price if "יעד רווח" in reason else bar.close)
                )
                gross = ((exit_px - pos.entry_price) * pos.size) if pos.side == "LONG" else ((pos.entry_price - exit_px) * pos.size)
                exit_fee = (exit_px * pos.size) * rt_cost_one
                fees_paid += exit_fee
                net_pnl = max(-pos.margin_used, gross - exit_fee - pos.fees_paid + pos.accumulated_funding)
                cash += max(0.0, pos.margin_used + gross) - exit_fee

            trades.append((sym, pos.side, pos.strategy, pos.leverage, net_pnl))
            del positions[sym]
            if "סטופ" in reason or is_liq:
                risk.start_cooldown(sym, now_dt)

        # Equity
        unr = sum(
            p.unrealized_pnl(datasets[s][1][idx_map[s][ts]].close)
            for s, p in positions.items() if ts in idx_map[s]
        )
        eq = cash + sum(p.margin_used for p in positions.values()) + unr
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak if peak > 0 else 0.0)

        if len(positions) >= cfg.risk.max_open_positions or eq <= 50.0:
            continue

        btc_ci = idx_map.get("BTC", {}).get(ts)
        btc_slice = datasets["BTC"][1][: btc_ci + 1] if btc_ci is not None and "BTC" in datasets else None

        cands: list[tuple[PerpInstrument, Any]] = []
        for sym, (inst, cs) in datasets.items():
            if sym in positions or risk.in_cooldown(sym, now_dt):
                continue
            ci = idx_map[sym].get(ts)
            if ci is None or ci < engine.min_candles:
                continue
            win = cs[max(0, ci - cfg.signal.lookback_candles + 1): ci + 1]
            sig = engine.evaluate(inst, win, btc_candles=btc_slice)
            if sig.direction != "FLAT":
                cands.append((inst, sig))

        cands.sort(key=lambda x: (-x[1].score, -x[0].volume_24h_usd))
        for inst, sig in cands:
            dec = risk.evaluate_entry(
                sig, inst, equity=eq, free_cash=cash, open_positions=list(positions.values()), now=now_dt
            )
            if not dec.approved:
                continue
            entry_fee = dec.notional * rt_cost_one
            fees_paid += entry_fee
            cash -= dec.margin + entry_fee
            positions[inst.symbol] = PerpPosition(
                symbol=inst.symbol, exchange=inst.exchange, side=sig.direction,  # type: ignore[arg-type]
                size=dec.size, entry_price=sig.price, notional=dec.notional,
                leverage=dec.leverage, margin_used=dec.margin, liquidation_price=dec.liquidation_price,
                stop_price=dec.stop_price, target_price=dec.target_price,
                highest_price=sig.price, lowest_price=sig.price, atr=sig.atr,
                strategy=sig.strategy, regime=sig.regime, entry_score=sig.score,
                fees_paid=entry_fee, opened_at=now_dt, last_funding_ts=ts,
            )

    end_eq = cash + sum(p.margin_used for p in positions.values())
    n = len(trades)
    wins = sum(1 for t in trades if t[4] > 0)
    gp = sum(t[4] for t in trades if t[4] > 0)
    gl = abs(sum(t[4] for t in trades if t[4] <= 0))
    return PerpBacktestSummary(
        trades=n,
        wins=wins,
        win_rate_pct=round(wins / n * 100, 1) if n else 0.0,
        profit_factor=round(gp / gl, 2) if gl > 0 else (99.0 if gp > 0 else 0.0),
        return_pct=round((end_eq - cfg.risk.starting_cash) / cfg.risk.starting_cash * 100, 2),
        ending_equity=round(end_eq, 2),
        max_drawdown_pct=round(max_dd * 100, 2),
        liquidations=liqs,
        avg_leverage=round(sum(t[3] for t in trades) / n, 1) if n else 0.0,
        max_leverage_used=max((t[3] for t in trades), default=0.0),
        fees_paid=round(fees_paid, 2),
        funding_net=round(funding_net, 2),
        by_strategy={st: round(sum(t[4] for t in trades if t[2] == st), 2) for st in ("pullback", "meanrev")},
        by_side={sd: round(sum(t[4] for t in trades if t[1] == sd), 2) for sd in ("LONG", "SHORT")},
    )


@dataclass
class PerpWalkForwardReport:
    folds: list[PerpBacktestSummary]
    oos_return_pct: float
    consistency: float
    total_trades: int
    total_liqs: int
    best_params: dict[str, Any] = field(default_factory=dict)


def run_perp_walkforward(
    cfg: PerpsConfig,
    datasets: dict[str, tuple[PerpInstrument, list[PerpCandle]]],
    *,
    funding_map: dict[str, dict[int, float]] | None = None,
    folds: int = 3,
) -> PerpWalkForwardReport:
    all_ts = sorted({c.ts for _, cs in datasets.values() for c in cs})
    if len(all_ts) < 200:
        return PerpWalkForwardReport([], 0.0, 0.0, 0, 0)

    warmup = min(120, len(all_ts) // 4)
    usable = all_ts[warmup:]
    step = max(1, len(usable) // folds)

    fold_results: list[PerpBacktestSummary] = []
    for f in range(folds):
        a = usable[f * step]
        b = usable[min(len(usable) - 1, (f + 1) * step)]
        res = run_perp_portfolio_backtest(cfg, datasets, funding_map=funding_map, eval_start_ts=a, eval_end_ts=b)
        fold_results.append(res)

    comp = 1.0
    for r in fold_results:
        comp *= (1.0 + r.return_pct / 100.0)
    cons = sum(1 for r in fold_results if r.return_pct > 0) / max(1, len(fold_results))
    return PerpWalkForwardReport(
        folds=fold_results,
        oos_return_pct=round((comp - 1.0) * 100, 2),
        consistency=round(cons, 2),
        total_trades=sum(r.trades for r in fold_results),
        total_liqs=sum(r.liquidations for r in fold_results),
    )


def write_perp_reports(
    full_res: PerpBacktestSummary,
    wf: PerpWalkForwardReport,
    out_dir: str | Path = "reports",
) -> Path:
    od = Path(out_dir)
    od.mkdir(parents=True, exist_ok=True)
    p = od / "perps_backtest.md"
    lines = [
        "# דוח בקטסט ואימות Walk-Forward — זרוע חוזים תמידיים (PERPS ×50)",
        "",
        "## סימולציית פורטפוליו מלאה (Isolated Margin + Funding + Slippage)",
        f"- **תשואה נטו:** `{full_res.return_pct:+.2f}%` (הון סופי **{full_res.ending_equity:.2f} USDC**)",
        f"- **עסקאות:** `{full_res.trades}` | **Win Rate:** `{full_res.win_rate_pct:.1f}%` | **PF:** `{full_res.profit_factor:.2f}`",
        f"- **Max Drawdown:** `{full_res.max_drawdown_pct:.2f}%` | **ליקווידציות:** `{full_res.liquidations}`",
        f"- **מינוף ממוצע:** `{full_res.avg_leverage:.1f}x` | **מינוף שיא בשימוש:** `{full_res.max_leverage_used:.1f}x`",
        f"- **עמלות:** `{full_res.fees_paid:.2f}` USDC | **Funding נטו:** `{full_res.funding_net:+.2f}` USDC",
        f"- **פילוח אסטרטגיות:** {full_res.by_strategy} | **פילוח כיוון:** {full_res.by_side}",
        "",
        "## אימות 3 חלונות Walk-Forward (OOS)",
        f"- **תשואת OOS מצטברת:** `{wf.oos_return_pct:+.2f}%` | **עקביות:** `{wf.consistency*100:.0f}%` | **ליקווידציות:** `{wf.total_liqs}`",
        "",
    ]
    for idx, fr in enumerate(wf.folds, 1):
        lines.append(
            f"- **חלון {idx}:** תשואה `{fr.return_pct:+.2f}%` · {fr.trades} עסקאות · "
            f"WR `{fr.win_rate_pct:.1f}%` · PF `{fr.profit_factor:.2f}` · DD `{fr.max_drawdown_pct:.1f}%`"
        )
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
