"""
בקטסט — הרצת אותה אסטרטגיה על היסטוריית מחירים אמיתית מ-CLOB.

המטרה: לא "לנצח" בפינת אופטימיזציה, אלא לבדוק שהמנוע לא מפסיד בגלל
עלויות/רעש, ולקבל תמונה על התפלגות העסקאות. כללי המשחק זהים לאינג'ין:
אותו מנוע סיגנלים, אותם סטופ/יעד/time-stop, אותה החלקה ועמלה.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import Config
from .data.clob import Candle, ClobClient
from .data.http import HttpClient
from .models import Market, Signal
from .fees import taker_fee
from .risk.sizing import size_for_trade, stop_and_target
from .signals import build_signal_engine

log = logging.getLogger(__name__)


@dataclass
class BTrade:
    entry_ts: int
    exit_ts: int
    direction: str
    entry: float
    exit: float
    size: float
    pnl: float
    pnl_pct: float
    reason: str
    score: float


@dataclass
class BacktestResult:
    label: str
    candles: int
    start_ts: int
    end_ts: int
    starting_equity: float
    ending_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    trades: list[BTrade] = field(default_factory=list)
    fees_paid: float = 0.0        # סך העמלות שנגבו (שקיפות מחיר העמלה)
    passive_fills: int = 0        # כניסות שמולאו כמייקר (ללא עמלה)
    taker_fills: int = 0          # כניסות שחצו את הספרד (בתשלום עמלה)

    # --- מטריקות נגזרות ---
    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t.pnl > 0) / len(self.trades)

    @property
    def profit_factor(self) -> float:
        gains = sum(t.pnl for t in self.trades if t.pnl > 0)
        losses = -sum(t.pnl for t in self.trades if t.pnl < 0)
        if losses <= 0:
            return float("inf") if gains > 0 else 0.0
        return gains / losses

    @property
    def avg_pnl(self) -> float:
        return sum(t.pnl for t in self.trades) / len(self.trades) if self.trades else 0.0

    def summary(self) -> dict:
        return {
            "label": self.label,
            "candles": self.candles,
            "duration_days": round((self.end_ts - self.start_ts) / 86400, 2),
            "starting_equity": round(self.starting_equity, 2),
            "ending_equity": round(self.ending_equity, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe": round(self.sharpe, 2),
            "trades": self.n_trades,
            "win_rate": round(self.win_rate * 100, 1),
            "profit_factor": round(self.profit_factor, 2) if math.isfinite(self.profit_factor) else None,
            "avg_pnl_per_trade": round(self.avg_pnl, 2),
            "fees_paid": round(self.fees_paid, 2),
            "passive_fills": self.passive_fills,
            "taker_fills": self.taker_fills,
            "fee_drag_pct": round(self.fees_paid / max(abs(self.ending_equity - self.starting_equity), 1e-9) * 100, 1) if self.fees_paid else 0.0,
        }


class Backtester:
    def __init__(self, cfg: Config, clob: ClobClient | None = None) -> None:
        self.cfg = cfg
        self.clob = clob or ClobClient(
            HttpClient(cfg.data.clob_base_url, cfg.data.http_timeout, cfg.data.max_retries,
                       cfg.data.rate_limit_rps)
        )
        self.engine = build_signal_engine(cfg.signal)

    # ------------------------------------------------------------------
    def fetch(self, token_id: str, fidelity: int = 60, lookback: int = 720) -> list[Candle]:
        """מושך היסטוריה אמיתית מ-CLOB (עם chunking פנימי של ה-API)."""
        return self.clob.get_history(
            token_id, fidelity_min=fidelity, lookback_candles=lookback, use_cache=False
        )

    # ------------------------------------------------------------------
    def run(
        self,
        market: Market,
        candles: list[Candle],
        *,
        label: str = "",
        spread: float = 0.01,
        starting_cash: float | None = None,
        entry_style: str = "taker",
        passive_wait: int = 3,
        passive_fallback: bool = True,
    ) -> BacktestResult:
        cfg = self.cfg
        prices = [c.price for c in candles]
        n = len(prices)
        cash = starting_cash if starting_cash is not None else cfg.execution.starting_cash
        fees_total = 0.0
        start_equity = cash
        peak = cash
        max_dd = 0.0
        curve: list[tuple[int, float]] = []

        slip = cfg.execution.slippage_bps / 10_000.0
        fee_bps = cfg.execution.taker_fee_bps / 10_000.0
        half_spread = spread / 2.0

        pos: dict | None = None
        pending: dict | None = None
        trades: list[BTrade] = []
        passive_fills = 0
        taker_fills = 0
        cooldown_until = 0

        def _try_open(entry_px: float, sig, ts_now: int, *, maker: bool) -> bool:
            """
            פותח פוזיציה במחיר נתון. maker=True ⇒ ללא החלקה וללא עמלה,
            כי הזמנה מגבלה שמולאה לא שילמה עמלת טאקר.
            """
            nonlocal cash, fees_total, pos, passive_fills, taker_fills
            lo, hi = cfg.universe.price_band
            if not (max(0.01, lo) <= entry_px <= min(0.99, hi)):
                return False
            stop, target = stop_and_target(
                entry_px, "LONG", cfg.signal.exit.stop_loss,
                cfg.signal.exit.take_profit, 0.001,
                mode=cfg.signal.exit.stop_mode,
            )
            shares, _ = size_for_trade(
                equity=cash, price=entry_px, fair_price=max(sig.fair_price, entry_px),
                stop_price=stop, cfg=cfg.risk,
                min_order_size=cfg.risk.min_order_size,
            )
            fee = 0.0 if maker else taker_fee(shares, entry_px, market.taker_fee_rate)
            if shares <= 0 or shares * entry_px + fee > cash:
                return False
            cash -= shares * entry_px + fee
            fees_total += fee
            pos = {
                "direction": sig.direction, "entry": entry_px, "size": shares,
                "entry_ts": ts_now, "stop": stop, "target": target,
                "score": sig.score, "cost": shares * entry_px, "entry_fee": fee,
            }
            if maker:
                passive_fills += 1
            else:
                taker_fills += 1
            return True

        for i in range(self.engine.min_candles, n):
            ts = candles[i].ts
            price = prices[i]
            window = prices[: i + 1]

            # ---- הזמנה פסיבית ממתינה: ממלאים אם המחיר יורד אלינו ----
            if pending is not None and pos is None:
                pending["candles"] += 1
                if price <= pending["limit"]:
                    if _try_open(pending["limit"], pending["signal"], ts, maker=True):
                        pending = None
                elif pending["candles"] >= passive_wait:
                    if passive_fallback:
                        ask_fb = min(0.999, price + half_spread)
                        taker_px = min(0.999, ask_fb * (1 + slip) + ask_fb * fee_bps)
                        if _try_open(taker_px, pending["signal"], ts, maker=False):
                            pending = None
                    else:
                        pending = None
            if pos is not None:
                pending = None

            signal = self.engine.evaluate(market, window, market_price=price, spread=spread,
                                          extra={"fee_rate": market.taker_fee_rate})

            # ---------- יציאה ----------
            if pos is not None:
                mark = price if pos["direction"] == "LONG" else 1.0 - price
                bid = max(0.001, mark - half_spread)
                hit = None
                if bid <= pos["stop"]:
                    hit = "סטופ"
                elif bid >= pos["target"]:
                    hit = "יעד"
                elif (ts - pos["entry_ts"]) / 3600 >= cfg.signal.exit.time_stop_hours:
                    hit = "time stop"
                elif cfg.signal.exit.exit_on_flip and signal.direction != "FLAT" \
                        and signal.direction != pos["direction"]:
                    hit = "היפוך סיגנל"

                if hit:
                    exit_px = max(0.001, bid * (1 - slip) - bid * fee_bps)
                    exit_fee = taker_fee(pos["size"], exit_px, market.taker_fee_rate)
                    net = (exit_px - pos["entry"]) * pos["size"] - pos["entry_fee"] - exit_fee
                    cash += pos["size"] * exit_px - exit_fee
                    fees_total += exit_fee
                    trades.append(
                        BTrade(
                            entry_ts=pos["entry_ts"], exit_ts=ts, direction=pos["direction"],
                            entry=round(pos["entry"], 4), exit=round(exit_px, 4),
                            size=pos["size"], pnl=round(net, 4),
                            pnl_pct=round(net / max(pos["cost"], 1e-9) * 100, 2),
                            reason=hit, score=round(pos["score"], 3),
                        )
                    )
                    pos = None
                    cooldown_until = ts + int(cfg.risk.cooldown_minutes) * 60

            # ---------- כניסה ----------
            if pos is None and pending is None and signal.direction != "FLAT" and ts >= cooldown_until:
                if entry_style == "passive":
                    # מגבלה על ה-bid: לא חוצים את הספרד, לא משלמים עמלה,
                    # ומרוויחים חצי ספרד אם מישהו מוכר לנו.
                    limit = max(0.01, round(price - spread / 2.0, 2))
                    pending = {"limit": limit, "candles": 0, "signal": signal}
                else:
                    ask = min(0.999, signal.market_price + half_spread)
                    _try_open(min(0.999, ask * (1 + slip) + ask * fee_bps),
                              signal, ts, maker=False)

            equity = cash + (pos["size"] * (price if pos["direction"] == "LONG" else 1 - price) if pos else 0.0)
            curve.append((ts, equity))
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)

        # סגירת פוזיציה פתוחה בסוף
        if pos is not None:
            mark = prices[-1] if pos["direction"] == "LONG" else 1 - prices[-1]
            bid = max(0.001, mark - half_spread)
            exit_px = max(0.001, bid * (1 - slip) - bid * fee_bps)
            exit_fee = taker_fee(pos["size"], exit_px, market.taker_fee_rate)
            net = (exit_px - pos["entry"]) * pos["size"] - pos["entry_fee"] - exit_fee
            cash += pos["size"] * exit_px - exit_fee
            fees_total += exit_fee
            trades.append(
                BTrade(
                    entry_ts=pos["entry_ts"], exit_ts=candles[-1].ts, direction=pos["direction"],
                    entry=round(pos["entry"], 4), exit=round(exit_px, 4), size=pos["size"],
                    pnl=round(net, 4), pnl_pct=round(net / max(pos["cost"], 1e-9) * 100, 2),
                    reason="סוף התקופה", score=round(pos["score"], 3),
                )
            )

        ending = cash

        # ---- Sharpe על בסיס יומי (ולא לפי נרות) כדי שיהיה בר-השוואה ----
        daily: dict[int, float] = {}
        for (ts, eq) in curve:
            day = ts // 86400
            daily[day] = eq          # הערך האחרון בכל יום
        daily_vals = [daily[k] for k in sorted(daily)]
        rets = [
            (daily_vals[i] - daily_vals[i - 1]) / daily_vals[i - 1]
            for i in range(1, len(daily_vals))
            if daily_vals[i - 1] > 0
        ]
        sharpe = 0.0
        if len(rets) > 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            sd = math.sqrt(var)
            if sd > 0:
                sharpe = (mean / sd) * math.sqrt(365)

        return BacktestResult(
            fees_paid=round(fees_total, 4),
            passive_fills=passive_fills,
            taker_fills=taker_fills,
            label=label or market.slug,
            candles=n,
            start_ts=candles[0].ts if candles else 0,
            end_ts=candles[-1].ts if candles else 0,
            starting_equity=round(start_equity, 2),
            ending_equity=round(ending, 2),
            total_return_pct=(ending / start_equity - 1) * 100 if start_equity else 0.0,
            max_drawdown_pct=max_dd * 100,
            sharpe=sharpe,
            trades=trades,
        )

    # ------------------------------------------------------------------
    def run_portfolio(
        self,
        datasets: list[tuple[Market, list[Candle]]],
        *,
        spread: float = 0.01,
        starting_cash: float | None = None,
    ) -> BacktestResult:
        """
        סימולציית תיק משותף אמיתי על ציר זמן מאוחד:
        בנקרול אחד, תקרת פוזיציות, תקרת חשיפה, מניעת כפילות באירוע/סקטור,
        cooldown, הפסד יומי, drawdown kill, ספרד מלא ועמלות פולימרקט.
        """
        from datetime import datetime, timezone
        from .execution.base import Portfolio
        from .models import Fill
        from .risk.manager import RiskManager

        if not datasets:
            raise ValueError("אין דאטה לסימולציית תיק")

        cfg = self.cfg
        cash0 = starting_cash if starting_cash is not None else cfg.execution.starting_cash
        port = Portfolio(cash0, mode="sim")
        rm = RiskManager(cfg)
        slip = cfg.execution.slippage_bps / 10_000.0
        fee_bps = cfg.execution.taker_fee_bps / 10_000.0

        by_ts: dict[int, list[tuple[Market, int]]] = {}
        series: dict[str, list[float]] = {}
        candles_map: dict[str, list[Candle]] = {}
        for mk, cs in datasets:
            series[mk.condition_id] = [c.price for c in cs]
            candles_map[mk.condition_id] = cs
            for i, c in enumerate(cs):
                if i >= self.engine.min_candles:
                    by_ts.setdefault(c.ts, []).append((mk, i))

        if not by_ts:
            raise ValueError("אין מספיק נרות לסימולציית תיק")

        marks: dict[str, float] = {}
        meta: dict[str, dict] = {}
        trades: list[BTrade] = []
        fees_total = 0.0
        taker_fills = 0
        peak = cash0
        max_dd = 0.0
        curve: list[tuple[int, float]] = []
        last_day = None

        for ts in sorted(by_ts):
            now = datetime.fromtimestamp(ts, tz=timezone.utc)
            day = now.date()
            if last_day is not None and day != last_day:
                port.realized_pnl_today = 0.0
            last_day = day

            pending_entries: list[tuple[Signal, Market, float, float]] = []

            # שלב 1: הערכת אותות וביצוע יציאות תחילה (לפינוי סלוטים ומזומן לפני כניסות)
            for mk, idx in by_ts[ts]:
                prices = series[mk.condition_id]
                p = prices[idx]
                marks[mk.yes_token_id] = p
                sp = max(mk.spread, spread)
                hs = sp / 2.0
                sig = self.engine.evaluate(mk, prices[: idx + 1], market_price=p, spread=sp,
                                           extra={"fee_rate": mk.taker_fee_rate})

                # --- יציאה ---
                pos = port.position_for(mk.yes_token_id)
                if pos is not None:
                    bid = max(0.001, p - hs)
                    flipped = sig.direction != "FLAT" and sig.token_id != pos.token_id
                    reason = rm.evaluate_exit(pos, bid, now=now, signal_flipped=flipped)
                    if reason:
                        epx = max(0.001, bid * (1 - slip) - bid * fee_bps)
                        ef = taker_fee(pos.size, epx, mk.taker_fee_rate)
                        info = meta.pop(mk.yes_token_id, {})
                        entry_fee = float(info.get("entry_fee", 0.0))
                        entry_px = pos.avg_price
                        sz = pos.size
                        port.apply_fill(Fill(mk.yes_token_id, mk.condition_id, "SELL",
                                             epx, sz, fee=ef, ts=now))
                        net = (epx - entry_px) * sz - entry_fee - ef
                        rm._cooldown_until[mk.condition_id] = now + __import__("datetime").timedelta(
                            minutes=cfg.risk.cooldown_minutes
                        )
                        fees_total += ef
                        trades.append(BTrade(
                            entry_ts=int(pos.opened_at.timestamp()), exit_ts=ts,
                            direction=pos.direction, entry=round(entry_px, 4),
                            exit=round(epx, 4), size=sz, pnl=round(net, 4),
                            pnl_pct=round(net / max(sz * entry_px, 1e-9) * 100, 2),
                            reason=f"{mk.slug[:20]}: {reason}", score=round(pos.entry_score, 3),
                        ))
                elif sig.direction != "FLAT":
                    pending_entries.append((sig, mk, p, hs))

            # שלב 2: כניסות מתועדפות לפי איכות אות (ציון ו-edge) תואם Engine.run_once
            pending_entries.sort(key=lambda item: (-float(item[0].score), -float(item[0].edge), -float(item[1].volume_24h)))
            for sig, mk, p, hs in pending_entries:
                if any(x.condition_id == mk.condition_id for x in port.positions.values()):
                    continue
                if rm._cooldown_until.get(mk.condition_id) and now < rm._cooldown_until[mk.condition_id]:
                    continue
                ask = min(0.999, p + hs)
                epx = min(0.999, ask * (1 + slip) + ask * fee_bps)
                lo, hi = cfg.universe.price_band
                if not (max(0.01, lo) <= epx <= min(0.99, hi)):
                    continue
                snap = port.snapshot(marks)
                open_events: dict[str, int] = {}
                open_sectors: dict[str, int] = {}
                for op in port.positions.values():
                    if op.event_id:
                        open_events[op.event_id] = open_events.get(op.event_id, 0) + 1
                    sec = meta.get(op.token_id, {}).get("sector")
                    if sec:
                        open_sectors[sec] = open_sectors.get(sec, 0) + 1
                dec = rm.evaluate_entry(
                    sig, mk, snap, price=epx, tick=0.001,
                    min_order_size=cfg.risk.min_order_size,
                    open_events=open_events, open_sectors=open_sectors,
                )
                if dec.approved:
                    ef = taker_fee(dec.size, epx, mk.taker_fee_rate)
                    if dec.size * epx + ef <= port.cash:
                        port.apply_fill(Fill(mk.yes_token_id, mk.condition_id, "BUY",
                                             epx, dec.size, fee=ef, ts=now))
                        pos = port.position_for(mk.yes_token_id)
                        if pos is not None:
                            pos.opened_at = now
                            pos.entry_score = sig.score
                            pos.event_id = mk.event_id
                            pos.question = mk.question
                            pos.stop_price, pos.target_price = stop_and_target(
                                epx, "LONG", cfg.signal.exit.stop_loss,
                                cfg.signal.exit.take_profit, 0.001,
                                mode=cfg.signal.exit.stop_mode,
                            )
                        meta[mk.yes_token_id] = {
                            "entry_fee": ef, "sector": mk.sector,
                            "fee_rate": mk.taker_fee_rate,
                        }
                        fees_total += ef
                        taker_fills += 1

            snap = port.snapshot(marks)
            rm.update_peak(snap.equity)
            peak = max(peak, snap.equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - snap.equity) / peak)
            curve.append((ts, snap.equity))

        # --- סגירת פוזיציות פתוחות בסוף התקופה ---
        last_ts = max(by_ts)
        last_now = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        for tid, pos in list(port.positions.items()):
            p = marks.get(tid, pos.avg_price)
            hs = spread / 2.0
            bid = max(0.001, p - hs)
            epx = max(0.001, bid * (1 - slip) - bid * fee_bps)
            info = meta.pop(tid, {})
            ef = taker_fee(pos.size, epx, float(info.get("fee_rate", 0.0)))
            entry_fee = float(info.get("entry_fee", 0.0))
            entry_px, sz = pos.avg_price, pos.size
            port.apply_fill(Fill(tid, pos.condition_id, "SELL", epx, sz, fee=ef, ts=last_now))
            net = (epx - entry_px) * sz - entry_fee - ef
            fees_total += ef
            trades.append(BTrade(
                entry_ts=int(pos.opened_at.timestamp()), exit_ts=last_ts,
                direction=pos.direction, entry=round(entry_px, 4),
                exit=round(epx, 4), size=sz, pnl=round(net, 4),
                pnl_pct=round(net / max(sz * entry_px, 1e-9) * 100, 2),
                reason="סוף התקופה", score=round(pos.entry_score, 3),
            ))

        ending = port.equity(marks)
        daily: dict[int, float] = {}
        for ts_i, eq in curve:
            daily[ts_i // 86400] = eq
        dvals = [daily[k] for k in sorted(daily)]
        rets = [(dvals[i] - dvals[i - 1]) / dvals[i - 1]
                for i in range(1, len(dvals)) if dvals[i - 1] > 0]
        sharpe = 0.0
        if len(rets) > 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            sd = math.sqrt(var)
            if sd > 0:
                sharpe = (mean / sd) * math.sqrt(365)

        return BacktestResult(
            label=f"portfolio ({len(datasets)} mkts)",
            candles=sum(len(cs) for _, cs in datasets),
            start_ts=min(by_ts),
            end_ts=last_ts,
            starting_equity=round(cash0, 2),
            ending_equity=round(ending, 2),
            total_return_pct=(ending / cash0 - 1) * 100 if cash0 else 0.0,
            max_drawdown_pct=max_dd * 100,
            sharpe=sharpe,
            trades=trades,
            fees_paid=round(fees_total, 4),
            taker_fills=taker_fills,
        )


def write_portfolio_report(res: BacktestResult, out_dir: str | Path = "reports",
                           engine: str = "—") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    s = res.summary()
    pf = "—" if s["profit_factor"] is None else f"{s['profit_factor']:.2f}"
    lines = [
        f"# סימולציית תיק משותף — מנוע `{engine}`",
        "",
        f"- הון התחלתי: **{s['starting_equity']:.2f}** → סופי: **{s['ending_equity']:.2f} USDC** "
        f"(**{s['total_return_pct']:+.2f}%**)",
        f"- עסקאות סגורות: **{s['trades']}** · win rate: **{s['win_rate']}%** · PF: **{pf}**",
        f"- Max Drawdown: **{s['max_drawdown_pct']:.2f}%** · Sharpe: **{s['sharpe']:.2f}** · "
        f"עמלות ששולמו: **{s['fees_paid']:.2f} USDC**",
        "",
        "| כניסה | יציאה | גודל | PnL | סיבה |",
        "|---|---|---|---|---|",
    ]
    for t in res.trades:
        lines.append(
            f"| {t.entry:.3f} | {t.exit:.3f} | {t.size:.1f} | {t.pnl:+.2f} | {t.reason} |"
        )
    path = out / "portfolio_backtest.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ----------------------------------------------------------------------
def write_report(results: list[BacktestResult], out_dir: str | Path = "reports",
                 engine: str = "—") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "engine": engine,
        "results": [r.summary() for r in results],
        "trades": {r.label: [asdict(t) for t in r.trades] for r in results},
    }
    js = out / "backtest.json"
    js.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# דו\"ח בקטסט — מנוע `{engine}`", ""]
    lines.append("| שוק | עסקאות | win % | PF | תשואה % | maxDD % | Sharpe |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        s = r.summary()
        pf = "—" if s["profit_factor"] is None else f"{s['profit_factor']:.2f}"
        lines.append(
            f"| {r.label[:40]} | {s['trades']} | {s['win_rate']} | {pf} | "
            f"{s['total_return_pct']:+.2f} | {s['max_drawdown_pct']:.2f} | {s['sharpe']:.2f} |"
        )
    if results:
        n = sum(r.n_trades for r in results)
        tot_pnl = sum(t.pnl for r in results for t in r.trades)
        wins = sum(1 for r in results for t in r.trades if t.pnl > 0)
        lines += [
            "",
            f"**סה\"כ:** {n} עסקאות, {wins} מנצחות "
            f"({wins / n * 100:.1f}%), PnL ממומש {tot_pnl:+.2f} USDC",
            "",
            "> הערה: הבקטסט מחייב ספרד מלא (חצי בכניסה, חצי ביציאה), החלקה ועמלות פולימרקט.",
            "> תוצאות היסטוריות הן אינדיקציה בלבד — לאימות חי הרץ paper.",
        ]
    md = out / "backtest.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


# ----------------------------------------------------------------------
def run_grid(
    bt: "Backtester",
    datasets: list[tuple[Market, list[Candle]]],
    grid: list[dict],
    *,
    spread: float = 0.01,
    progress=None,
) -> list[dict]:
    """
    סריקת פרמטרים גסה. ⚠️ כלי עזר לכיול בלבד — לא לאופטימיזציה עיוורת:
    יותר מדי אופטימיזציה על אותה תקופה = overfitting. תמיד לאמת
    את הפרמטרים שנבחרו על שווקים/תקופה אחרים, ואז ב-paper.
    """
    out: list[dict] = []
    sig = bt.cfg.signal
    base = {
        "min_score": sig.min_score, "min_edge": sig.min_edge,
        "take_profit": sig.exit.take_profit, "stop_loss": sig.exit.stop_loss,
        "trend_filter": sig.trend_filter,
    }
    try:
        for i, params in enumerate(grid, 1):
            sig.min_score = params["min_score"]
            sig.min_edge = params["min_edge"]
            sig.exit.take_profit = params["take_profit"]
            sig.exit.stop_loss = params["stop_loss"]
            sig.trend_filter = params.get("trend_filter", True)

            results = [bt.run(mk, candles, label=mk.slug, spread=spread) for mk, candles in datasets]
            trades = [t for r in results for t in r.trades]
            wins = sum(1 for t in trades if t.pnl > 0)
            pnl = sum(t.pnl for t in trades)
            ret = sum(r.total_return_pct for r in results)
            dd = max((r.max_drawdown_pct for r in results), default=0.0)
            out.append({
                **params,
                "trades": len(trades),
                "win_rate": round(wins / len(trades) * 100, 1) if trades else 0.0,
                "pnl": round(pnl, 2),
                "avg_return_pct": round(ret / len(results), 2) if results else 0.0,
                "max_dd_pct": round(dd, 2),
            })
            if progress:
                progress(i, len(grid), out[-1])
    finally:
        for k, v in base.items():
            if k in ("take_profit", "stop_loss"):
                setattr(sig.exit, k, v)
            else:
                setattr(sig, k, v)
    return out


def write_grid_report(rows: list[dict], out_dir: str | Path = "reports") -> Path:
    import csv

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "tune.csv"
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path
