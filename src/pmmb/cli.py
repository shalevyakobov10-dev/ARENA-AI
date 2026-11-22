"""
ממשק שורת פקודה.

  pmmb doctor                  בדיקת חיבור וקונפיג
  pmmb scan                    סריקה חד-פעמית של היקום + הסיגנלים
  pmmb paper --cycles 5        ריצת paper (סימולציה) עם לופ
  pmmb live                    מסחר אמיתי (מוגן בסיסמה)
  pmmb backtest --top 5        בקטסט על שווקים אמיתיים
  pmmb report                  סיכום ביצועים מה-DB
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from .backtest import Backtester, write_report
from .config import Config
from .data.clob import ClobClient
from .data.http import HttpClient
from .data.store import Store
from .models import Market
from .engine import Engine
from .logging_setup import setup_logging

log = logging.getLogger("pmmb")


# ----------------------------------------------------------------------
def _build_clob(cfg: Config) -> ClobClient:
    return ClobClient(
        HttpClient(cfg.data.clob_base_url, cfg.data.http_timeout, cfg.data.max_retries,
                   cfg.data.rate_limit_rps),
        history_ttl=cfg.data.history_cache_ttl_sec,
    )


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(h) 
              for i, h in enumerate(headers)]
    sep = "  "
    out = [sep.join(str(h).ljust(widths[i]) for i, h in enumerate(headers))]
    out.append(sep.join("-" * w for w in widths))
    for r in rows:
        out.append(sep.join(str(c).ljust(widths[i]) for i, c in enumerate(r)))
    return "\n".join(out)


# ----------------------------------------------------------------------
def cmd_doctor(args, cfg: Config) -> int:
    ok = True
    print(f"קונפיג: mode={cfg.execution.mode}, cash={cfg.execution.starting_cash}, "
          f"db={cfg.data.db_path}")
    from .data.gamma import GammaClient, MarketUniverse

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    try:
        raw = gamma.fetch_markets(limit=5)
        print(f"✅ Gamma נגיש ({len(raw)} שווקים לדוגמה)")
    except Exception as exc:
        print(f"❌ Gamma לא נגיש: {exc}")
        return 1

    # בודקים CLOB על טוקן חי — לא על מזהה קבוע שיכול לפוג
    probe = None
    for m in raw:
        mk = Market.from_gamma(m)
        if mk is not None:
            probe = mk
            break
    try:
        mid = clob.get_midpoint(probe.yes_token_id) if probe else None
        book = clob.get_book(probe.yes_token_id) if probe else None
        if mid is None or book is None:
            print("⚠️  CLOB נגיש אבל לא החזיר מחיר לשוק הנבדק")
        else:
            print(f"✅ CLOB נגיש (midpoint={mid:.3f}, "
                  f"bid={book.best_bid}, ask={book.best_ask}, "
                  f"spread={book.spread:.3f})")
    except Exception as exc:
        print(f"❌ CLOB לא נגיש: {exc}")
        return 1

    uni = MarketUniverse(gamma, cfg.universe)
    markets = uni.scan()
    print(f"✅ סינון יקום: {len(markets)} שווקים עוברים את הפילטרים")
    if markets:
        rows = [[m.question[:45], f"{m.yes_price:.3f}", f"{m.spread:.3f}",
                 f"{m.volume_24h:,.0f}", f"{m.hours_to_resolution:.0f}h"] for m in markets[:5]]
        print(_table(rows, ["שוק", "YES", "ספרד", "מחזור24h", "לסגירה"]))
    return 0 if ok else 1


def cmd_scan(args, cfg: Config) -> int:
    from .signals import build_signal_engine
    from .data.gamma import GammaClient, MarketUniverse

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    engine = build_signal_engine(cfg.signal)
    markets = MarketUniverse(gamma, cfg.universe).scan()
    print(f"נסרקו {len(markets)} שווקים\n")

    rows = []
    for mk in markets:
        candles = clob.get_history(mk.yes_token_id, cfg.signal.candle_fidelity_min,
                                   cfg.signal.lookback_candles)
        book = clob.get_book(mk.yes_token_id)
        if book is None or book.mid is None:
            continue
        sig = engine.evaluate(mk, [c.price for c in candles],
                             market_price=book.mid, spread=book.spread)
        if args.all or sig.direction != "FLAT":
            rows.append([
                mk.question[:42],
                f"{book.mid:.3f}",
                f"{sig.direction}",
                f"{sig.score:.2f}",
                f"{sig.fair_price:.3f}",
                f"{sig.edge:+.3f}",
                sig.reason[:46],
            ])
    rows.sort(key=lambda r: -float(r[3]))
    if not rows:
        print("אין סיגנלים במחזור הזה (זה נורמלי — הסיגנל נדיר בכוונה).")
        return 0
    print(_table(rows, ["שוק", "מחיר", "כיוון", "score", "fair", "edge", "הסבר"]))
    n_tradeable = sum(1 for r in rows if r[2] != "FLAT")
    print(f"\nסה\"כ {len(rows)} שווקים עם נתונים, {n_tradeable} עם סיגנל פעיל.")
    return 0


def cmd_run(args, cfg: Config) -> int:
    broker = None
    if args.command == "live":
        cfg.execution.mode = "live"
        from .execution.live import LiveBroker, LiveTradingDisabled

        try:
            broker = LiveBroker(cfg.execution)
        except LiveTradingDisabled as exc:
            print(f"⛔ {exc}")
            return 2
        print("🔴 מצב LIVE — פקודות אמיתיות. Ctrl+C לעצירה.")

    engine = Engine(cfg, broker=broker)
    if broker is None:
        print(f"📄 מצב {cfg.execution.mode} — סימולציה. "
              f"הון התחלתי {cfg.execution.starting_cash:.0f} USDC")
    try:
        engine.run_forever(interval_sec=args.interval, max_cycles=args.cycles)
    except KeyboardInterrupt:
        print("\nנעצר.")
    finally:
        snap = engine.portfolio.snapshot(engine._last_marks)
        print(f"\nסיכום: הון {snap.equity:.2f} | מזומן {snap.cash:.2f} | "
              f"חשיפה {snap.exposure:.2f} | פוזיציות {snap.open_positions} | "
              f"PnL ממומש {engine.portfolio.realized_pnl:+.2f}")
        engine.close()
    return 0


def cmd_backtest(args, cfg: Config) -> int:
    from .data.gamma import GammaClient, MarketUniverse

    clob = _build_clob(cfg)
    bt = Backtester(cfg, clob)

    if args.token:
        from .models import Market

        dummy = Market(
            condition_id=args.token[:10], question=args.token[:20], slug=args.token[:20],
            yes_token_id=args.token, no_token_id=args.token,
            yes_price=0.5, no_price=0.5, spread=0.01, volume_24h=0, liquidity=0, end_date=None,
        )
        candles = bt.fetch(args.token, fidelity=args.fidelity, lookback=args.lookback)
        if not candles:
            print("❌ אין היסטוריה לטוקן הזה")
            return 1
        res = bt.run(dummy, candles, label=args.token[:16], spread=args.spread,
                     entry_style=args.entry, passive_wait=args.wait)
        print(_summary_line(res))
        write_report([res], args.out, engine=cfg.signal.engine)
        return 0

    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                  cfg.data.max_retries, cfg.data.rate_limit_rps))
    markets = MarketUniverse(gamma, cfg.universe).scan()
    if args.top:
        markets = markets[: args.top]
    print(f"בודק {len(markets)} שווקים, fidelity={args.fidelity} דק', "
          f"{args.lookback} נרות\n")

    results = []
    for mk in markets:
        candles = bt.fetch(mk.yes_token_id, fidelity=args.fidelity, lookback=args.lookback)
        if len(candles) < bt.engine.min_candles + 10:
            log.debug("מדלג על %s (היסטוריה קצרה: %d נרות)", mk.slug, len(candles))
            continue
        res = bt.run(mk, candles, label=mk.slug, spread=max(mk.spread, args.spread),
                     entry_style=args.entry, passive_wait=args.wait)
        results.append(res)
        print(_summary_line(res))

    if not results:
        print("לא נמצאו שווקים עם היסטוריה מספקת.")
        return 1
    path = write_report(results, args.out, engine=cfg.signal.engine)
    n = sum(r.n_trades for r in results)
    pnl = sum(t.pnl for r in results for t in r.trades)
    print(f"\n📄 דו\"ח נכתב ל-{path} | {n} עסקאות | PnL {pnl:+.2f} USDC")
    return 0


def cmd_analyze(args, cfg: Config) -> int:
    """אבחון כוח הניבוי של הסיגנל — לפני בקטסט, לפני כיול."""
    from .diagnostics import run_diagnostics, write_diagnostics
    from .data.gamma import GammaClient, MarketUniverse
    from .signals import build_signal_engine

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    markets = MarketUniverse(gamma, cfg.universe).scan()[: args.markets]
    engine = build_signal_engine(cfg.signal)

    datasets = []
    for mk in markets:
        candles = clob.get_history(mk.yes_token_id, fidelity_min=args.fidelity,
                                   lookback_candles=args.lookback, use_cache=False)
        if len(candles) >= engine.min_candles + max(24, args.horizon) + 5:
            datasets.append((mk, candles))
    if not datasets:
        print("אין שווקים עם היסטוריה מספקת.")
        return 1

    print(f"מאבחן {len(datasets)} שווקים, {sum(len(c) for _, c in datasets):,} נרות...\n")
    res = run_diagnostics(engine, datasets, spread=args.spread)
    print(res.to_markdown())
    path = write_diagnostics(res, args.out)
    print(f"\n📄 {path}")

    best = max(res.horizons.values(), key=lambda s: s.ic)
    if abs(best.ic) < 0.03:
        print("\n🔴 מסקנה: אין כוח ניבוי מדיד (|IC| < 0.03). הסיגנל הזה לא ישרוד עלויות.")
    elif best.ic > 0:
        print(f"\n🟢 מסקנה: יש אות חלש-חיובי באופק {best.horizon} (IC={best.ic:+.3f}). "
              "שווה להמשיך ולבדוק עלויות.")
    else:
        print(f"\n🟠 מסקנה: האות שלילי באופק {best.horizon} (IC={best.ic:+.3f}) — "
              "הפוך הכיוון או זרוק את הפיצ'ר.")
    return 0


def cmd_tune(args, cfg: Config) -> int:
    """סריקת פרמטרים גסה על שווקים אמיתיים. לכיול בלבד — לא קסמים."""
    from .backtest import run_grid, write_grid_report
    from .data.gamma import GammaClient, MarketUniverse

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    markets = MarketUniverse(gamma, cfg.universe).scan()[: args.markets]
    bt = Backtester(cfg, clob)

    datasets = []
    for mk in markets:
        candles = bt.fetch(mk.yes_token_id, fidelity=args.fidelity, lookback=args.lookback)
        if len(candles) >= bt.engine.min_candles + 20:
            datasets.append((mk, candles))
    if not datasets:
        print("אין שווקים עם היסטוריה מספקת.")
        return 1
    print(f"מריץ גריד על {len(datasets)} שווקים "
          f"({sum(len(c) for _, c in datasets):,} נרות)\n")

    grid = [
        {"min_score": ms, "min_edge": me, "take_profit": tp, "stop_loss": sl}
        for ms in (0.45, 0.55, 0.65)
        for me in (0.02, 0.05)
        for tp, sl in ((0.08, 0.05), (0.12, 0.07), (0.20, 0.10))
    ]

    def progress(i, n, row):
        print(f"[{i:2d}/{n}] score>{row['min_score']} edge>{row['min_edge']} "
              f"tp={row['take_profit']} sl={row['stop_loss']} → "
              f"{row['trades']:3d} עסקאות, win {row['win_rate']:5.1f}%, PnL {row['pnl']:+8.2f}")

    rows = run_grid(bt, datasets, grid, spread=args.spread, progress=progress)
    rows.sort(key=lambda r: -r["pnl"])
    path = write_grid_report(rows, args.out)

    print("\n🏆 5 הקונפיגורציות המובילות:")
    for r in rows[:5]:
        print(f"  score>{r['min_score']} edge>{r['min_edge']} tp={r['take_profit']} "
              f"sl={r['stop_loss']} → PnL {r['pnl']:+.2f}, {r['trades']} עסקאות, "
              f"win {r['win_rate']}%")
    print(f"\n📄 {path}")
    print("⚠️  זו סריקה על תקופה אחת — סימן לכיוון, לא הוכחה. אמת על שווקים אחרים ואז paper.")
    return 0


def cmd_collect(args, cfg: Config) -> int:
    """אוסף snapshots של ספר הפקודות — הדאטה שמאפשר למדוד imbalance."""
    import time as _time

    from .data.gamma import GammaClient, MarketUniverse

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    markets = MarketUniverse(gamma, cfg.universe).scan()
    store = Store(cfg.data.db_path)

    print(f"אוסף snapshots עבור {len(markets)} שווקים · "
          f"{args.minutes:g} דק' · כל {args.interval:g}s")
    started = _time.time()
    cycles = 0
    try:
        while (_time.time() - started) / 60 < args.minutes:
            cycles += 1
            ts = int(_time.time())
            recorded = 0
            for mk in markets:
                book = clob.get_book(mk.yes_token_id)
                if book is not None and book.mid is not None:
                    store.record_book(mk.yes_token_id, ts, book, levels=args.levels)
                    recorded += 1
            print(f"  מחזור {cycles}: {recorded} snapshots", end="\r", flush=True)
            _time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nנעצר ידנית")
    finally:
        total = store._conn.execute("SELECT COUNT(*) c FROM books").fetchone()["c"]
        store.close()
    print(f"\n✅ נאספו {total:,} snapshots בסך הכל. "
          f"הרץ: pmmb imbalance --horizon-min {args.interval * 4 / 60:.0f}")
    return 0


def cmd_imbalance(args, cfg: Config) -> int:
    """האם imbalance מנבא תנועת מחיר? (דורש דאטה מ-collect/paper)"""
    from .imbalance import analyze_imbalance, write_imbalance_report

    store = Store(cfg.data.db_path)
    rep = analyze_imbalance(store, horizon_min=args.horizon_min, levels=args.levels,
                            tolerance_min=args.tolerance)
    store.close()
    if rep.snapshots == 0:
        print("אין snapshots של ספר הפקודות ב-DB.")
        print("הרץ קודם:  pmmb collect --minutes 30 --interval 20")
        return 1
    print(rep.to_markdown())
    path = write_imbalance_report(rep, args.out)
    print(f"\n📄 {path}")
    return 0


def cmd_sectors(args, cfg: Config) -> int:
    """איפה האות עובד: פילוח לפי סקטור שוק."""
    from .diagnostics import run_sector_analysis, sectors_markdown
    from .data.gamma import GammaClient, MarketUniverse
    from .signals import build_signal_engine
    from pathlib import Path

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    # לוקחים יקום רחב — לא רק המובילים — כדי שיהיו מספיק סקטורים
    saved = cfg.universe.max_markets
    cfg.universe.max_markets = max(saved, args.markets)
    markets = MarketUniverse(gamma, cfg.universe).scan()[: args.markets]
    cfg.universe.max_markets = saved

    engine = build_signal_engine(cfg.signal)
    datasets = []
    for mk in markets:
        candles = clob.get_history(mk.yes_token_id, fidelity_min=args.fidelity,
                                   lookback_candles=args.lookback, use_cache=False)
        need = engine.min_candles + int(args.horizon * 60 / args.fidelity) + 5
        if len(candles) >= need:
            datasets.append((mk, candles))
    if not datasets:
        print("אין שווקים עם היסטוריה מספקת.")
        return 1

    print(f"מנתח {len(datasets)} שווקים, אופק {args.horizon:g}ש'...\n")
    rows = run_sector_analysis(engine, datasets, fidelity_min=args.fidelity,
                               horizon_hours=args.horizon, spread=args.spread)
    md = sectors_markdown(rows, args.horizon)
    print(md)
    out = Path(args.out) / "sectors.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    import json as _json

    (Path(args.out) / "sectors.json").write_text(_json.dumps({
        "horizon_hours": args.horizon, "spread": args.spread,
        "rows": [{
            "sector": r.sector, "n": r.n, "hit_rate": round(r.hit_rate, 3),
            "mean_realized": round(r.mean_realized, 4), "mean_fee": round(r.mean_fee, 4),
            "net_of_cost": round(r.net_of_cost, 4),
        } for r in rows],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📄 {out} + sectors.json")

    bad = [s.sector for s in rows if s.n >= 20 and s.net_of_cost < 0]
    if bad:
        print(f"\n🟠 סקטורים עם נטו שלילי (מועמדים להחרגה): {', '.join(bad)}")
        print("   הוסף ל-universe.exclude_sectors ואמת ב-walkforward.")
    else:
        print("\n🟢 אין סקטור מובהק עם נטו שלילי במדגם הזה.")
    return 0


def cmd_calibrate(args, cfg: Config) -> int:
    """האם הצפי של המנוע תואם את המציאות? המבחן הנקי ביותר שלנו."""
    from .diagnostics import run_calibration
    from .data.gamma import GammaClient, MarketUniverse
    from .signals import build_signal_engine

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    markets = MarketUniverse(gamma, cfg.universe).scan()[: args.markets]
    engine = build_signal_engine(cfg.signal)

    datasets = []
    for mk in markets:
        candles = clob.get_history(mk.yes_token_id, fidelity_min=args.fidelity,
                                   lookback_candles=args.lookback, use_cache=False)
        if len(candles) >= engine.min_candles + 50:
            datasets.append((mk, candles))
    if not datasets:
        print("אין שווקים עם היסטוריה מספקת.")
        return 1

    res = run_calibration(engine, datasets, fidelity_min=args.fidelity,
                          horizon_hours=args.horizon, spread=args.spread)
    print(res.to_markdown())

    if not res.rows:
        print("\nאין מספיק סיגנלים לכיול — הדק את הספים או הגדל את המדגם.")
        return 0
    total = next((r for r in res.rows if r.label == "כל הסיגנלים"), None)
    if total and total.bias_ratio > 1.5:
        print(f"\n🟠 המנוע מבטיח פי {total.bias_ratio:.1f} ממה שמתממש. "
              f"יחס מומלץ: {res.suggested_ratio:.2f} (במקום {res.current_ratio:g}).")
    elif total and total.bias_ratio < 0.7:
        print(f"\n🔵 המנוע שמרני מדי (פי {total.bias_ratio:.1f}) — אפשר להעלות את היחס.")
    else:
        print("\n🟢 הצפי מכויל בסטייה של פחות מ-50%.")
    return 0


def cmd_walkforward(args, cfg: Config) -> int:
    """כיול על חלון אחד, מבחן על החלון שאחריו — שלא נרמה את עצמנו."""
    from .walkforward import run_walkforward, write_walkforward
    from .data.gamma import GammaClient, MarketUniverse
    from .signals import build_signal_engine

    clob = _build_clob(cfg)
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url, cfg.data.http_timeout,
                                   cfg.data.max_retries, cfg.data.rate_limit_rps))
    markets = MarketUniverse(gamma, cfg.universe).scan()[: args.markets]
    engine = build_signal_engine(cfg.signal)

    datasets = []
    for mk in markets:
        candles = clob.get_history(mk.yes_token_id, fidelity_min=args.fidelity,
                                   lookback_candles=args.lookback, use_cache=False)
        if len(candles) >= engine.min_candles + args.folds * 40:
            datasets.append((mk, candles))
    if not datasets:
        print("אין שווקים עם היסטוריה מספקת ל-walk-forward.")
        return 1
    print(f"walk-forward על {len(datasets)} שווקים · מנוע={cfg.signal.engine} · "
          f"{args.folds} חלונות\n")

    res = run_walkforward(cfg, datasets, folds=args.folds, spread=args.spread,
                          progress=lambda m: print("·", m))
    print()
    print(res.to_markdown())
    path = write_walkforward(res, args.out)
    print(f"\n📄 {path}")

    if res.oos_trades == 0:
        print("\n⚠️  אין עסקאות מחוץ למדגם — הפרמטרים שנבחרו בכיול מדכאים מסחר. "
              "אין ממה להסיק.")
    elif res.consistency >= 0.66 and res.oos_pnl > 0:
        print("\n🟢 ה-OOS חיובי ברוב החלונות — יש כאן משהו שווה בדיקה נוספת "
              "(ואז paper, לא live).")
    else:
        print("\n🔴 ה-OOS לא מחזיק. הכיול הוא התאמה לרעש — לא לסמוך על הפרמטרים האלה.")
    return 0


def _summary_line(r) -> str:
    s = r.summary()
    pf = "—" if s["profit_factor"] is None else f"{s['profit_factor']:.2f}"
    return (f"{s['label'][:38]:38s} | {s['trades']:3d} עסקאות | win {s['win_rate']:5.1f}% | "
            f"PF {pf:>5s} | תשואה {s['total_return_pct']:+7.2f}% | DD {s['max_drawdown_pct']:5.2f}%")


def cmd_daily(args, cfg: Config) -> int:
    """דוח יומי מה-DB — להרצה אוטומטית (cron), לא דורש שהבוט ירוץ."""
    from .daily import build_daily_report, write_daily_report

    store = Store(cfg.data.db_path)
    rep = build_daily_report(store, hours=args.hours, starting_cash=cfg.execution.starting_cash,
                             planned_horizon_hours=cfg.signal.exit.time_stop_hours)
    store.close()
    print(rep.to_markdown())
    if not args.no_write:
        path = write_daily_report(rep, args.out)
        print(f"\n📄 {path}")
    return 0


def cmd_status(args, cfg: Config) -> int:
    """מצב המערכת — JSON למכונה, טבלה לבן אדם."""
    import json

    from .status import build_status

    st = build_status(cfg, max_age_sec=args.max_age)
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0 if st["health"]["healthy"] else 3

    h = st["health"]
    hb = st.get("heartbeat") or {}
    bank = st.get("bankroll") or {}
    today = st.get("today") or {}
    icon = "🟢" if h["healthy"] else "🔴"
    print(f"\n{icon} {h['reason']}")
    if hb:
        print(f"   מחזור #{hb.get('cycle')} · {hb.get('mode')} · {hb.get('engine')} · "
              f"גיל {hb.get('age_sec', 0):.0f}ש' · pid {hb.get('pid')}")
    if bank:
        print(f"   הון {bank.get('equity')} · מזומן {bank.get('cash')} · "
              f"חשיפה {bank.get('exposure')} · פוזיציות {bank.get('open_positions')}")
    if today:
        print(f"   היום: {today.get('fills')} מילואים · PnL {today.get('realized_pnl'):+.2f} · "
              f"עמלות {today.get('fees'):.2f}")
    for p in st.get("positions") or []:
        print(f"   · {p['direction']} {p['size']:.1f} @ {p['avg_price']:.3f} "
              f"({p['age_hours']:.1f}ש') {p['token_id']}")
    return 0 if h["healthy"] else 3


def cmd_serve(args, cfg: Config) -> int:
    """מרים את שרת המצב (לרוב מהטלפון)."""
    from .server import serve

    httpd = serve(cfg, host=args.host, port=args.port,
                  max_age_sec=args.max_age, refresh_sec=args.refresh,
                  token=args.token)
    print(f"🌐 http://{args.host}:{args.port}  (Ctrl+C לעצירה)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nנעצר")
    finally:
        httpd.server_close()
    return 0


def cmd_notify_test(args, cfg: Config) -> int:
    """בודק שהתראות Telegram עובדות — לפני שמסתמכים עליהן."""
    from .notify import Notifier, fmt_daily

    n = Notifier()
    if not n.enabled:
        print("⚪️ לא הוגדר: PMMB_TELEGRAM_TOKEN / PMMB_TELEGRAM_CHAT_ID")
        return 1
    ok = n.send(fmt_daily(cfg.execution.mode, 1000.0, 0.0, 0), force=True)
    print("✅ נשלחה הודעת בדיקה" if ok else "❌ השליחה נכשלה — בדוק טוקן/chat_id")
    return 0 if ok else 1


def cmd_fees(args, cfg: Config) -> int:
    from .feeview import fee_table, write_fee_report

    from pathlib import Path
    import json as _json

    measured = {}
    sec = Path(args.out) / "sectors.json"
    if sec.exists():
        try:
            measured = {r["sector"]: r["mean_realized"]
                        for r in _json.loads(sec.read_text(encoding="utf-8"))["rows"]}
        except Exception:      # noqa: BLE001 — קובץ פגום לא אמור לעצור כלי דיאגנוסטי
            measured = {}
    rows = fee_table(spread=args.spread, edge=args.edge, price=args.price,
                     measured_edges=measured)
    print()
    print(f"{'סקטור':12s} {'עמלה':>6s} {'סבב':>7s} {'עובי':>7s} {'נדרש':>7s} {'נטו':>8s}  פסק דין")
    print("-" * 72)
    for r in rows:
        print(f"{r.sector:12s} {r.rate:6.1%} {r.rt_fee:7.4f} {r.edge:7.4f} {r.breakeven:7.4f} "
              f"{r.net_at_edge:+8.4f}  {r.verdict}")
    print("\n(עובי = מהמדידה בפועל אם reports/sectors.json קיים, אחרת ברירת מחדל)")
    out = write_fee_report(f"{args.out}/fees.md", rows, spread=args.spread,
                           edge=args.edge, price=args.price)
    print(f"\n📄 {out}")
    return 0


def cmd_report(args, cfg: Config) -> int:
    store = Store(cfg.data.db_path)
    trades = store.closed_trades()
    if not trades:
        print("אין עסקאות סגורות ב-DB עדיין.")
        return 0
    wins = [t for t in trades if (t["realized_pnl"] or 0) > 0]
    total = sum((t["realized_pnl"] or 0) for t in trades)
    rows = []
    for t in trades[-args.limit:]:
        ts = datetime.fromtimestamp(t["closed_at"], tz=timezone.utc).strftime("%m-%d %H:%M")
        rows.append([ts, (t["question"] or t["token_id"])[:34], t["direction"],
                     f"{t['avg_price']:.3f}", f"{t['realized_pnl']:+.2f}", t["exit_reason"] or ""])
    print(_table(rows, ["נסגר", "שוק", "כיוון", "כניסה", "PnL", "סיבה"]))
    print(f"\nסה\"כ {len(trades)} עסקאות | win rate {len(wins) / len(trades) * 100:.1f}% | "
          f"PnL ממומש {total:+.2f} USDC")
    store.close()
    return 0


# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pmmb", description="Polymarket Momentum Bot (אסטרטגיה B)")
    p.add_argument("--config", default=None, help="נתיב ל-config.yaml")
    p.add_argument("--log-level", default=None)
    p.add_argument("--engine", default=None, choices=["momentum", "meanrev"],
                   help="עקיפת מנוע הסיגנל (ברירת מחדל: config)")

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="בדיקת חיבור וקונפיג")

    s = sub.add_parser("scan", help="סריקה חד-פעמית והצגת סיגנלים")
    s.add_argument("--all", action="store_true", help="הצג גם שווקים ללא סיגנל")

    for name, hlp in (("paper", "הרצת סימולציה"), ("live", "מסחר אמיתי (מוגן)")):
        r = sub.add_parser(name, help=hlp)
        r.add_argument("--cycles", type=int, default=None, help="מספר מחזורים ואז עצור")
        r.add_argument("--interval", type=float, default=60.0, help="שניות בין מחזורים")

    b = sub.add_parser("backtest", help="בקטסט היסטורי")
    b.add_argument("--top", type=int, default=5, help="כמה שווקים מהרשימה המובילה")
    b.add_argument("--token", default=None, help="token id ספציפי לבדיקה")
    b.add_argument("--fidelity", type=int, default=60, help="רזולוציית נרות (דקות)")
    b.add_argument("--lookback", type=int, default=720, help="מספר נרות היסטוריים")
    b.add_argument("--spread", type=float, default=0.01, help="ספרד קבוע להנחה")
    b.add_argument("--entry", choices=["taker", "passive"], default="taker",
                   help="taker = חוצים את הספרד ומשלמים עמלה · passive = מגבלה על ה-bid (מייקר, פטור מעמלה)")
    b.add_argument("--wait", type=int, default=3,
                   help="כמה נרות להמתין למילוי פסיבי לפני מעבר לטאקר")
    b.add_argument("--out", default="reports")

    a = sub.add_parser("analyze", help="אבחון כוח ניבוי הסיגנל (IC / hit rate)")
    a.add_argument("--markets", type=int, default=8)
    a.add_argument("--fidelity", type=int, default=60)
    a.add_argument("--lookback", type=int, default=720)
    a.add_argument("--horizon", type=int, default=24)
    a.add_argument("--spread", type=float, default=0.01)
    a.add_argument("--out", default="reports")

    t = sub.add_parser("tune", help="סריקת פרמטרים על דאטה אמיתי (לכיול)")
    t.add_argument("--markets", type=int, default=4)
    t.add_argument("--fidelity", type=int, default=60)
    t.add_argument("--lookback", type=int, default=500)
    t.add_argument("--spread", type=float, default=0.01)
    t.add_argument("--out", default="reports")

    co = sub.add_parser("collect", help="איסוף snapshots של ספר הפקודות")
    co.add_argument("--minutes", type=float, default=30)
    co.add_argument("--interval", type=float, default=20)
    co.add_argument("--levels", type=int, default=5)

    im = sub.add_parser("imbalance", help="ניתוח כוח הניבוי של imbalance")
    im.add_argument("--horizon-min", type=float, default=60)
    im.add_argument("--tolerance", type=float, default=20)
    im.add_argument("--levels", type=int, default=5)
    im.add_argument("--out", default="reports")

    sec = sub.add_parser("sectors", help="פילוח האות לפי סקטור שוק")
    sec.add_argument("--markets", type=int, default=40)
    sec.add_argument("--fidelity", type=int, default=60)
    sec.add_argument("--lookback", type=int, default=1440)
    sec.add_argument("--horizon", type=float, default=48)
    sec.add_argument("--spread", type=float, default=0.01)
    sec.add_argument("--out", default="reports")

    cal = sub.add_parser("calibrate", help="האם הצפי תואם את המציאות")
    cal.add_argument("--markets", type=int, default=12)
    cal.add_argument("--fidelity", type=int, default=60)
    cal.add_argument("--lookback", type=int, default=1440)
    cal.add_argument("--horizon", type=float, default=24, help="אופק מדידה בשעות")
    cal.add_argument("--spread", type=float, default=0.01)

    wf = sub.add_parser("walkforward", help="כיול וחילוץ OOS על חלונות זמן")
    wf.add_argument("--markets", type=int, default=12)
    wf.add_argument("--folds", type=int, default=3)
    wf.add_argument("--fidelity", type=int, default=60)
    wf.add_argument("--lookback", type=int, default=1440)
    wf.add_argument("--spread", type=float, default=0.01)
    wf.add_argument("--out", default="reports")

    dl = sub.add_parser("daily", help="דוח יומי מה-DB (ל-cron)")
    dl.add_argument("--hours", type=int, default=24)
    dl.add_argument("--out", default="reports")
    dl.add_argument("--no-write", action="store_true", help="לא לכתוב קובץ")

    stt = sub.add_parser("status", help="מצב המערכת (בריאות, הון, פוזיציות, היום)")
    stt.add_argument("--json", action="store_true", help="פלט JSON למכונה")
    stt.add_argument("--max-age", type=float, default=300, help="גיל דופק מקסימלי (שניות)")

    srv = sub.add_parser("serve", help="שרת מצב לקריאה מהטלפון")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=8787)
    srv.add_argument("--max-age", type=float, default=300)
    srv.add_argument("--refresh", type=int, default=30, help="רענון אוטומטי בעמוד (0=כבוי)")
    srv.add_argument("--token", default=None, help="אם מוגדר — נדרש ?token= בקריאה")

    sub.add_parser("notify-test", help="בדיקת התראות Telegram")

    pf = sub.add_parser("fees", help="כלכלת העמלות לפי סקטור (מה בכלל כדאי לסחור)")
    pf.add_argument("--spread", type=float, default=0.01)
    pf.add_argument("--edge", type=float, default=0.025, help="עובי סיגנל טיפוסי (נק' הסתברות)")
    pf.add_argument("--price", type=float, default=0.50)
    pf.add_argument("--out", default="reports")

    rp = sub.add_parser("report", help="סיכום ביצועים מה-DB")
    rp.add_argument("--limit", type=int, default=20)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load(args.config)
    if getattr(args, "engine", None):
        cfg.signal.engine = args.engine
    if args.log_level:
        cfg.logging.level = args.log_level
    setup_logging(cfg.logging, quiet=args.command in {"scan", "backtest", "report", "doctor"})

    handlers = {
        "doctor": cmd_doctor,
        "scan": cmd_scan,
        "paper": cmd_run,
        "live": cmd_run,
        "backtest": cmd_backtest,
        "tune": cmd_tune,
        "analyze": cmd_analyze,
        "walkforward": cmd_walkforward,
        "calibrate": cmd_calibrate,
        "sectors": cmd_sectors,
        "collect": cmd_collect,
        "imbalance": cmd_imbalance,
        "report": cmd_report,
        "daily": cmd_daily,
        "fees": cmd_fees,
        "status": cmd_status,
        "serve": cmd_serve,
        "notify-test": cmd_notify_test,
    }
    return handlers[args.command](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
