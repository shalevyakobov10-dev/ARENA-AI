"""
מצב המערכת בקריאוּת אחת — לבן אדם בטלפון ולמכונה ב-JSON.
"""
from __future__ import annotations

import html as _html
import time
from datetime import datetime, timezone
from pathlib import Path

from .runtime import check_health, read_halt, read_heartbeat


def _day_start_ts() -> int:
    now = datetime.now(tz=timezone.utc)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def _esc(s: object) -> str:
    return _html.escape(str(s or ""), quote=True)


def build_status(cfg, *, max_age_sec: float = 300) -> dict:
    """
    מרכיב מצב מלא: דופק, בריאות, פוזיציות פתוחות (כולל PnL לא ממומש וסטופ/יעד),
    עסקאות היום, PnL ממומש, אירועים אחרונים. לא נוגע ברשת — רק DB + קובץ דופק.
    """
    from .data.store import Store

    health = check_health(max_age_sec=max_age_sec)
    hb = health.heartbeat or read_heartbeat()
    halt = read_halt()
    out: dict = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": cfg.execution.mode,
        "engine": cfg.signal.engine,
        "health": health.as_dict(),
        "halt": halt.as_dict() if halt else None,
        "heartbeat": hb.as_dict() if hb else None,
        "positions": [],
        "today": {},
        "overall": {},
        "recent_trades": [],
        "bankroll": {},
        "soak": {"days": 0, "target_days": 7},
        "guards": (hb.guards if hb else {}),
        "skipped": (hb.skipped if hb else {}),
        "equity_curve": [],
    }

    db = Path(cfg.data.db_path)
    if not db.exists():
        out["warning"] = "מסד הנתונים לא נמצא — הבוט כנראה לא רץ עדיין"
        return out

    store = Store(db)
    try:
        day = _day_start_ts()
        pos = store.open_positions(cfg.execution.mode)
        marks = store.latest_marks([r["token_id"] for r in pos]) if pos else {}

        pos_list = []
        total_unrealized = 0.0
        for r in pos:
            tid = r["token_id"]
            avg = float(r["avg_price"] or 0.0)
            sz = float(r["size"] or 0.0)
            mark = marks.get(tid)
            unr = round((mark - avg) * sz, 2) if mark is not None else None
            unr_pct = round((mark - avg) / avg * 100, 1) if (mark is not None and avg > 0) else None
            if unr is not None:
                total_unrealized += unr
            pos_list.append({
                "token_id": tid[:12],
                "full_token_id": tid,
                "condition_id": (r["condition_id"] or "")[:12],
                "question": r["question"] or tid[:16],
                "direction": r["direction"],
                "size": round(sz, 2),
                "avg_price": round(avg, 4),
                "mark_price": round(mark, 4) if mark is not None else None,
                "unrealized_pnl": unr,
                "unrealized_pct": unr_pct,
                "stop_price": round(float(r["stop_price"]), 3) if r["stop_price"] is not None else None,
                "target_price": round(float(r["target_price"]), 3) if r["target_price"] is not None else None,
                "opened_at": r["opened_at"],
                "age_hours": round((time.time() - (r["opened_at"] or time.time())) / 3600, 1),
                "realized_pnl": round(r["realized_pnl"] or 0.0, 2),
            })
        out["positions"] = pos_list

        fills = store.fills_since(day, cfg.execution.mode)
        realized_today = sum(float(r["realized"] or 0.0) for r in fills)
        buys = [r for r in fills if r["side"] == "BUY"]
        sells = [r for r in fills if r["side"] == "SELL"]
        out["today"] = {
            "fills": len(fills), "entries": len(buys), "exits": len(sells),
            "realized_pnl": round(realized_today, 2),
            "fees": round(sum(float(r["fee"] or 0.0) for r in fills), 2),
            "notional": round(sum(float(r["price"]) * float(r["size"]) for r in fills), 2),
        }

        with store.tx() as c:
            all_sells = list(c.execute(
                """SELECT f.ts, f.token_id, f.price, f.size, f.realized, f.reason,
                          COALESCE(p.question, f.token_id) AS question
                   FROM fills f LEFT JOIN positions p ON p.token_id = f.token_id
                   WHERE f.side='SELL' AND f.mode=? ORDER BY f.ts DESC, f.id DESC""",
                (cfg.execution.mode,),
            ).fetchall())
            all_fees = float(c.execute(
                "SELECT COALESCE(SUM(fee),0) s FROM fills WHERE mode=?",
                (cfg.execution.mode,),
            ).fetchone()["s"] or 0.0)

        gains = sum(float(r["realized"] or 0.0) for r in all_sells if (r["realized"] or 0.0) > 0)
        losses = -sum(float(r["realized"] or 0.0) for r in all_sells if (r["realized"] or 0.0) < 0)
        n_wins = sum(1 for r in all_sells if (r["realized"] or 0.0) > 0)
        pf = round(gains / losses, 2) if losses > 0 else (None if gains == 0 else 99.9)
        out["overall"] = {
            "exits": len(all_sells),
            "wins": n_wins,
            "win_rate_pct": round(n_wins / len(all_sells) * 100, 1) if all_sells else 0.0,
            "profit_factor": pf,
            "realized_pnl": round(sum(float(r["realized"] or 0.0) for r in all_sells), 2),
            "fees": round(all_fees, 2),
        }
        out["recent_trades"] = [
            {
                "ts": int(r["ts"]),
                "question": str(r["question"] or r["token_id"])[:50],
                "size": round(float(r["size"] or 0.0), 2),
                "price": round(float(r["price"] or 0.0), 4),
                "realized": round(float(r["realized"] or 0.0), 2),
                "reason": str(r["reason"] or "")[:40],
            }
            for r in all_sells[:8]
        ]

        with store.tx() as c:
            row = c.execute(
                "SELECT equity, cash, exposure, positions FROM equity "
                "WHERE mode=? OR mode IS NULL ORDER BY ts DESC LIMIT 1",
                (cfg.execution.mode,),
            ).fetchone()
            curve = list(c.execute(
                "SELECT ts, equity FROM equity WHERE mode=? OR mode IS NULL "
                "ORDER BY ts DESC LIMIT 240",
                (cfg.execution.mode,),
            ).fetchall())
            eq_days = list(c.execute(
                "SELECT ts FROM equity WHERE mode=? OR mode IS NULL",
                (cfg.execution.mode,),
            ).fetchall())
        soak_days = len({
            datetime.fromtimestamp(r["ts"], tz=timezone.utc).strftime("%Y-%m-%d")
            for r in eq_days
        })
        out["soak"] = {"days": soak_days, "target_days": 7}
        out["bankroll"] = {
            "equity": round(row["equity"], 2) if row else (round(hb.equity, 2) if hb else None),
            "cash": round(row["cash"], 2) if row else (round(hb.cash, 2) if hb else None),
            "exposure": round(row["exposure"], 2) if row else (round(hb.exposure, 2) if hb else None),
            "open_positions": row["positions"] if row else (hb.positions if hb else None),
            "unrealized_pnl": round(total_unrealized, 2),
        }
        out["equity_curve"] = [{"ts": r["ts"], "equity": round(r["equity"], 2)}
                               for r in reversed(curve)]
        try:
            out["events"] = [
                {"ts": r["ts"], "level": r["level"], "kind": r["kind"], "msg": r["msg"]}
                for r in store.event_log(limit=15)
            ]
        except Exception:      # noqa: BLE001 — תצוגה לא מפילה דוח
            out["events"] = []
    finally:
        store.close()
    return out


def build_chart_series(store, cfg, token_id: str, limit: int = 160) -> dict:
    """מחזיר סדרת גרף מלאה + SMA + רצועת Z + RSI + חדשות תואמות עבור טוקן."""
    from .data.news import match_market_news
    from .signals import indicators as ind

    series = store.token_chart_series(token_id, limit=limit)
    ticks = series["ticks"]
    lb = max(6, int(cfg.signal.meanrev.lookback_candles))
    z_ent = float(cfg.signal.meanrev.z_entry)
    sma: list[float | None] = []
    lower_band: list[float | None] = []
    rsi_series: list[float | None] = []
    prices = [t["price"] for t in ticks]
    for i in range(len(prices)):
        rsi_series.append(round(ind.rsi(prices[: i + 1], 14), 1) if i >= 14 else None)
        if i + 1 < lb:
            sma.append(None)
            lower_band.append(None)
            continue
        win = prices[i + 1 - lb:i + 1]
        mu = sum(win) / len(win)
        var = sum((x - mu) ** 2 for x in win) / max(len(win) - 1, 1)
        sd = var ** 0.5
        sma.append(round(mu, 4))
        lower_band.append(round(max(0.01, mu - z_ent * max(sd, 0.002)), 4))

    q_txt = (series.get("position") or {}).get("question") or series.get("question") or ""
    matched_news: list[str] = []
    if q_txt:
        arts = [dict(r) for r in store.recent_news(hours=72, limit=120)]
        nm = match_market_news(q_txt, arts, window_hours=72, min_articles=1, impact_threshold=0.0)
        matched_news = nm.matched_titles or []

    series["sma"] = sma
    series["lower_band"] = lower_band
    series["rsi"] = rsi_series
    series["matched_news"] = matched_news
    return series


def build_performance_analytics(cfg, store: Store) -> dict:
    """חישוב ביצועים אמיתי ממאגר העסקאות (לפי אסטרטגיה, לפי נכס, לפי יום ו-Profit Factor חי)."""
    c = store._conn
    pmode = cfg.execution.mode
    perps_mode = cfg.perps.mode
    daily: dict[str, dict] = {}
    strat_agg: dict[str, dict] = {}
    sym_agg: dict[str, dict] = {}
    gross_win = 0.0
    gross_loss = 0.0
    wins = 0
    losses = 0

    def _add(day_s: str, arm: str, strat: str, sym: str, pnl: float, fee: float) -> None:
        nonlocal gross_win, gross_loss, wins, losses
        d = daily.setdefault(day_s, {"day": day_s, "poly": 0.0, "perps": 0.0, "total": 0.0, "trades": 0})
        if arm == "poly":
            d["poly"] += pnl
        else:
            d["perps"] += pnl
        d["total"] += pnl
        d["trades"] += 1

        st = strat_agg.setdefault(strat, {"strategy": strat, "arm": arm, "trades": 0, "wins": 0, "pnl": 0.0, "fees": 0.0})
        st["trades"] += 1
        if pnl > 0:
            st["wins"] += 1
            gross_win += pnl
            wins += 1
        elif pnl < 0:
            gross_loss += abs(pnl)
            losses += 1
        st["pnl"] += pnl
        st["fees"] += fee

        sy = sym_agg.setdefault(sym, {"symbol": sym, "arm": arm, "trades": 0, "wins": 0, "pnl": 0.0})
        sy["trades"] += 1
        if pnl > 0:
            sy["wins"] += 1
        sy["pnl"] += pnl

    # עסקאות Polymarket סגורות (SELL)
    poly_rows = c.execute(
        """SELECT f.ts, f.realized, f.fee, f.reason, f.token_id,
                  COALESCE(NULLIF(p.question, ''), mi.question, f.token_id) AS question
           FROM fills f
           LEFT JOIN positions p ON p.token_id = f.token_id
           LEFT JOIN market_intel mi ON mi.token_id = f.token_id
           WHERE f.mode=? AND f.side='SELL'""",
        (pmode,),
    ).fetchall()
    for r in poly_rows:
        ts_i = int(r["ts"] or 0)
        day_s = datetime.fromtimestamp(ts_i, tz=timezone.utc).strftime("%Y-%m-%d")
        pnl = float(r["realized"] or 0.0)
        fee = float(r["fee"] or 0.0)
        q = str(r["question"] or r["token_id"])[:28]
        _add(day_s, "poly", "Polymarket", q, pnl, fee)

    # עסקאות PERPS סגורות
    perp_rows = c.execute(
        """SELECT ts, symbol, side, realized, fee, reason
           FROM perp_fills WHERE mode=? AND action IN ('CLOSE','LIQUIDATION')""",
        (perps_mode,),
    ).fetchall()
    for r in perp_rows:
        ts_i = int(r["ts"] or 0)
        day_s = datetime.fromtimestamp(ts_i, tz=timezone.utc).strftime("%Y-%m-%d")
        pnl = float(r["realized"] or 0.0)
        fee = float(r["fee"] or 0.0)
        rsn = str(r["reason"] or "").lower()
        if "ידנית" in rsn or "manual" in rsn:
            strat = "PERPS ידני"
        elif "פריצ" in rsn or "breakout" in rsn:
            strat = "PERPS Breakout"
        elif "pullback" in rsn or "מגמת" in rsn:
            strat = "PERPS Pullback"
        elif "meanrev" in rsn or "היפוך" in rsn:
            strat = "PERPS MeanRev"
        else:
            strat = "PERPS ×50"
        _add(day_s, "perps", strat, str(r["symbol"] or "?"), pnl, fee)

    daily_list = [
        {
            "day": d["day"],
            "poly": round(d["poly"], 2),
            "perps": round(d["perps"], 2),
            "total": round(d["total"], 2),
            "trades": d["trades"],
        }
        for d in sorted(daily.values(), key=lambda x: x["day"])[-30:]
    ]
    strat_list = [
        {
            "strategy": s["strategy"],
            "arm": s["arm"],
            "trades": s["trades"],
            "win_rate_pct": round(s["wins"] / s["trades"] * 100.0, 1) if s["trades"] else 0.0,
            "pnl": round(s["pnl"], 2),
            "fees": round(s["fees"], 2),
        }
        for s in sorted(strat_agg.values(), key=lambda x: -x["pnl"])
    ]
    top_syms = [
        {
            "symbol": s["symbol"],
            "arm": s["arm"],
            "trades": s["trades"],
            "win_rate_pct": round(s["wins"] / s["trades"] * 100.0, 1) if s["trades"] else 0.0,
            "pnl": round(s["pnl"], 2),
        }
        for s in sorted(sym_agg.values(), key=lambda x: -abs(x["pnl"]))[:10]
    ]
    tot_t = wins + losses
    live_pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    return {
        "daily_pnl": daily_list,
        "by_strategy": strat_list,
        "top_symbols": top_syms,
        "total_trades": tot_t,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / tot_t * 100.0, 1) if tot_t else 0.0,
        "live_pf": live_pf,
        "avg_win": round(gross_win / wins, 2) if wins else 0.0,
        "avg_loss": round(gross_loss / losses, 2) if losses else 0.0,
    }


def build_command_center_data(
    cfg,
    *,
    max_age_sec: float = 300,
    reports_dir: str | Path = "reports",
    backups_dir: str | Path = "backups",
    trader_state: dict | None = None,
) -> dict:
    """אוסף נתונים מלא לתוכנת הבקרה (ללא רשת — DB + reports + state + backups)."""
    import json
    import re
    from .data.store import Store
    from .readiness import collect_facts, evaluate, is_ready, summary

    out = build_status(cfg, max_age_sec=max_age_sec)
    out["fills"] = []
    out["signals"] = []
    out["backups"] = []
    out["analytics"] = {}
    out["news"] = []
    out["charts"] = {"candidates": [], "default": None}
    out["learning"] = {"stats": {}, "runs": [], "insights": []}
    out["market_intel"] = []
    out["autopilot"] = []
    out["world_pulse"] = {"total": 0, "avg_sentiment": 0.0, "catalysts": 0, "regime": "שקט", "sources": 0, "by_category": {}}
    out["telemetry"] = {"ticks": 0, "books": 0, "signals": 0, "news": 0, "intel": 0}
    out["combined_equity_curve"] = []
    out["performance"] = {
        "daily_pnl": [], "by_strategy": [], "top_symbols": [],
        "total_trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
        "live_pf": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
    }
    out["unified_risk"] = {"status": "unavailable", "baseline_status": "unavailable"}
    ts_map = trader_state or {}
    out["autonomous"] = {
        "db_size_kb": round(Path(cfg.data.db_path).stat().st_size / 1024.0, 1) if Path(cfg.data.db_path).exists() else 0.0,
        "uptime_sec": int(ts_map.get("uptime_sec") or 0),
        "perps_learn_cycles": int(ts_map.get("perps_learn_cycles") or 0),
        "housekeeping_cycles": int(ts_map.get("housekeeping_cycles") or 0),
        "auto_recoveries": int(ts_map.get("auto_recoveries") or 0),
        "last_housekeeping_ts": int(ts_map.get("last_housekeeping_ts") or 0),
    }
    out["trader"] = trader_state or {
        "running": False, "cycles": 0, "last_error": "", "interval_sec": 180,
        "stream_ticks": 0, "news_fetches": 0, "learn_cycles": 0,
        "last_news_ts": 0, "last_stream_ts": 0, "last_learn_ts": 0,
        "last_reconcile_ts": 0, "last_backup_ts": 0, "last_reports_ts": 0,
    }

    db = Path(cfg.data.db_path)
    if db.exists():
        store = Store(db)
        try:
            with store.tx() as c:
                fill_rows = list(c.execute(
                    """SELECT f.ts, f.side, f.price, f.size, f.fee, f.notional,
                              f.realized, f.reason, f.token_id,
                              COALESCE(NULLIF(p.question, ''), mi.question, f.token_id) AS question
                       FROM fills f
                       LEFT JOIN positions p ON p.token_id = f.token_id
                       LEFT JOIN market_intel mi ON mi.token_id = f.token_id
                       WHERE f.mode=? ORDER BY f.ts DESC, f.id DESC LIMIT 60""",
                    (cfg.execution.mode,),
                ).fetchall())
                sig_rows = list(c.execute(
                    """SELECT s.ts, s.token_id, s.direction, s.score, s.fair_price,
                              s.market_price, s.edge, s.reason, s.features,
                              COALESCE(NULLIF(p.question, ''), mi.question, '') AS question
                       FROM signals s
                       LEFT JOIN positions p ON p.token_id = s.token_id
                       LEFT JOIN market_intel mi ON mi.token_id = s.token_id
                       ORDER BY s.id DESC LIMIT 50""",
                ).fetchall())
                out["telemetry"] = {
                    "ticks": int(c.execute("SELECT COUNT(*) n FROM ticks").fetchone()["n"]),
                    "books": int(c.execute("SELECT COUNT(*) n FROM books").fetchone()["n"]),
                    "signals": int(c.execute("SELECT COUNT(*) n FROM signals").fetchone()["n"]),
                    "news": int(c.execute("SELECT COUNT(*) n FROM news_items").fetchone()["n"]),
                    "intel": int(c.execute("SELECT COUNT(*) n FROM market_intel").fetchone()["n"]),
                }

            out["fills"] = [
                {
                    "ts": int(r["ts"]),
                    "side": r["side"],
                    "price": round(float(r["price"] or 0.0), 4),
                    "size": round(float(r["size"] or 0.0), 2),
                    "fee": round(float(r["fee"] or 0.0), 3),
                    "notional": round(float(r["notional"] or 0.0), 2),
                    "realized": round(float(r["realized"] or 0.0), 2),
                    "reason": str(r["reason"] or "")[:70],
                    "question": str(r["question"] or r["token_id"])[:55],
                }
                for r in fill_rows
            ]
            sigs = []
            for r in sig_rows:
                z = None
                rsi_s = None
                tier_s = None
                try:
                    feats = json.loads(r["features"] or "{}")
                    if "z" in feats and feats["z"] is not None:
                        z = round(float(feats["z"]), 2)
                    if "rsi" in feats and feats["rsi"] is not None:
                        rsi_s = round(float(feats["rsi"]), 1)
                    if "setup_tier" in feats:
                        tier_s = str(feats["setup_tier"])
                except Exception:
                    pass
                sigs.append({
                    "ts": int(r["ts"]),
                    "token_id": str(r["token_id"] or "")[:12],
                    "question": str(r["question"] or "")[:44],
                    "direction": r["direction"],
                    "score": round(float(r["score"] or 0.0), 2),
                    "fair_price": round(float(r["fair_price"] or 0.0), 3),
                    "market_price": round(float(r["market_price"] or 0.0), 3),
                    "edge": round(float(r["edge"] or 0.0), 4),
                    "z": z,
                    "rsi": rsi_s,
                    "setup_tier": tier_s,
                    "reason": str(r["reason"] or "")[:72],
                })
            out["signals"] = sigs

            # חדשות שווקים מכל העולם + מדד מצב גלובלי + אזור גיאוגרפי
            from .data.news import compute_global_pulse, infer_region

            out["news"] = [
                {
                    "id": str(r["id"]),
                    "ts": int(r["ts"]),
                    "title": str(r["title"]),
                    "source": str(r["source"] or ""),
                    "category": str(r["category"] or "macro"),
                    "region": infer_region(str(r["source"] or ""), str(r["category"] or ""), str(r["title"] or "")),
                    "sentiment": round(float(r["sentiment"] or 0.0), 2),
                    "impact": round(float(r["impact"] or 0.0), 2),
                    "matched_tokens": str(r["matched_tokens"] or ""),
                }
                for r in store.recent_news(hours=72, limit=180)
            ]
            out["world_pulse"] = compute_global_pulse(out["news"])

            # גרפים חיים — מועמדים + גרף ברירת מחדל מוכן כולל SMA ורצועת Z
            cands = store.chart_candidates(cfg.execution.mode, limit=18)
            default_chart = build_chart_series(store, cfg, cands[0]["token_id"]) if cands else None
            out["charts"] = {"candidates": cands, "default": default_chart}

            # למידה עצמית רציפה (Polymarket + PERPS + תוצאות חדשות)
            l_stats = store.signal_outcome_stats(days=30)
            l_runs = store.recent_learning_runs(limit=15)
            n_alpha = store.news_alpha_stats(days=14)
            out["learning"] = {
                "stats": l_stats,
                "runs": l_runs,
                "insights": (l_runs[0].get("details") or {}).get("insights", []) if l_runs else [],
                "news_alpha": n_alpha,
            }
            out["news_alpha"] = n_alpha
            out["market_intel"] = store.recent_market_intel(limit=60)
            out["autopilot"] = store.recent_autopilot_runs(limit=25)
            out["perps"] = build_perps_status(cfg, store, reports_dir=reports_dir)

            # Read-only unified risk snapshot for the Command Center.
            # Deliberately do not call ensure_unified_day_baseline() here:
            # dashboard GET requests must never create or rebase a risk baseline.
            try:
                from .unified_risk import (
                    UNIFIED_MAX_MARK_SKEW_SEC,
                    _global_halt_reason,
                    build_unified_risk_status,
                )

                risk_snapshot = build_unified_risk_status(store, cfg)
                risk_payload = risk_snapshot.as_dict()
                risk_limits = cfg.portfolio_risk
                capital_limit = risk_snapshot.starting_capital * risk_limits.max_capital_utilization_pct
                daily_loss_limit = risk_snapshot.starting_capital * risk_limits.max_daily_loss_pct
                mark_sync_ok = (
                    risk_snapshot.open_positions == 0
                    or (
                        risk_snapshot.marks_fresh
                        and risk_snapshot.mark_skew_sec <= UNIFIED_MAX_MARK_SKEW_SEC
                    )
                )
                halt_reason = _global_halt_reason()
                blockers: list[str] = []
                if cfg.execution.mode != "paper":
                    blockers.append("Polymarket אינו מוגדר במצב Paper")
                if cfg.perps.enabled and cfg.perps.mode != "paper":
                    blockers.append("PERPS מופעל אך אינו מוגדר במצב Paper")
                if risk_snapshot.baseline_status != "ready":
                    blockers.append(
                        "נקודת הבסיס היומית אינה מוכנה: "
                        + risk_snapshot.baseline_status
                    )
                if risk_snapshot.open_positions and not risk_snapshot.marks_fresh:
                    blockers.append("חסר מחיר עדכני ותקין לאחת הפוזיציות הפתוחות")
                if (
                    risk_snapshot.open_positions
                    and risk_snapshot.mark_skew_sec > UNIFIED_MAX_MARK_SKEW_SEC
                ):
                    blockers.append(
                        f"פער זמנים בין מחירי הזירות גדול מ-{UNIFIED_MAX_MARK_SKEW_SEC} שניות"
                    )
                if (
                    risk_snapshot.daily_risk_pnl is not None
                    and risk_snapshot.daily_risk_pnl <= -daily_loss_limit
                ):
                    blockers.append("הפסד יומי משולב הגיע לתקרה")
                if halt_reason:
                    blockers.append(halt_reason)
                if risk_snapshot.starting_capital <= 0:
                    blockers.append("ההון ההתחלתי המשותף אינו תקין")

                risk_payload["status"] = "ok"
                risk_payload["guard"] = {
                    "mode": "paper-only",
                    "enabled": True,
                    "max_capital_utilization_pct": round(
                        risk_limits.max_capital_utilization_pct * 100.0, 2
                    ),
                    "capital_limit": round(capital_limit, 2),
                    "capital_utilization_pct": (
                        round(
                            risk_snapshot.committed_capital
                            / risk_snapshot.starting_capital * 100.0,
                            2,
                        )
                        if risk_snapshot.starting_capital > 0 else None
                    ),
                    "max_open_positions": int(risk_limits.max_open_positions),
                    "max_daily_loss_pct": round(risk_limits.max_daily_loss_pct * 100.0, 2),
                    "daily_loss_limit": round(daily_loss_limit, 2),
                    "marks_synchronized": bool(mark_sync_ok),
                    "mark_skew_limit_sec": UNIFIED_MAX_MARK_SKEW_SEC,
                    "halted": halt_reason is not None,
                    "halt_reason": halt_reason or "",
                    "preflight_status": "blocked" if blockers else "clear",
                    "preflight_blockers": blockers,
                    "scope_note": (
                        "בדיקת תצוגה לקריאות בלבד: החלטת הכניסה הסופית בודקת שוב "
                        "את סכום ההקצאה ואת מספר הפוזיציות בזמן שליחת כל פקודה."
                    ),
                }
                out["unified_risk"] = risk_payload
            except Exception as exc:  # noqa: BLE001 — show unknown, never invent zero.
                log.exception("Unified risk status unavailable for Command Center")
                out["unified_risk"] = {
                    "status": "error",
                    "error": type(exc).__name__,
                    "baseline_status": "error",
                    "guard": {
                        "mode": "paper-only",
                        "enabled": True,
                        "preflight_status": "unknown",
                        "preflight_blockers": ["לא ניתן לקרוא את מצב הסיכון המאוחד"],
                    },
                }

            # סיכום תיק מאוחד משתי הזרועות (Polymarket + PERPS ×50)
            poly_eq = float((out.get("bankroll") or {}).get("equity") or cfg.execution.starting_cash)
            perp_eq = float((out["perps"] or {}).get("equity") or cfg.perps.risk.starting_cash) if cfg.perps.enabled else 0.0
            start_comb = float(cfg.execution.starting_cash) + (float(cfg.perps.risk.starting_cash) if cfg.perps.enabled else 0.0)
            comb_eq = round(poly_eq + perp_eq, 2)
            comb_pnl = round(comb_eq - start_comb, 2)
            out["combined"] = {
                "equity": comb_eq,
                "starting_cash": round(start_comb, 2),
                "pnl": comb_pnl,
                "return_pct": round(comb_pnl / start_comb * 100.0, 2) if start_comb > 0 else 0.0,
                "poly_equity": round(poly_eq, 2),
                "perps_equity": round(perp_eq, 2),
                "open_positions": int((out.get("bankroll") or {}).get("open_positions") or 0) + len((out["perps"] or {}).get("positions") or []),
                "closed_trades": int((out.get("overall") or {}).get("exits") or 0) + int((out["perps"] or {}).get("closed_trades") or 0),
                "fees_paid": round(float((out.get("overall") or {}).get("fees") or 0.0) + float((out["perps"] or {}).get("fees_paid") or 0.0), 2),
            }
            poly_pts = out.get("equity_curve") or []
            perp_pts = (out["perps"] or {}).get("equity_curve") or []
            if poly_pts or perp_pts:
                all_ts = sorted({int(p["ts"]) for p in poly_pts} | {int(p["ts"]) for p in perp_pts})
                cur_poly = float(cfg.execution.starting_cash)
                cur_perp = float(cfg.perps.risk.starting_cash) if cfg.perps.enabled else 0.0
                p_idx = q_idx = 0
                comb_curve = []
                for ts_i in all_ts:
                    while p_idx < len(poly_pts) and int(poly_pts[p_idx]["ts"]) <= ts_i:
                        cur_poly = float(poly_pts[p_idx]["equity"])
                        p_idx += 1
                    while q_idx < len(perp_pts) and int(perp_pts[q_idx]["ts"]) <= ts_i:
                        cur_perp = float(perp_pts[q_idx]["equity"])
                        q_idx += 1
                    comb_curve.append({
                        "ts": ts_i,
                        "equity": round(cur_poly + cur_perp, 2),
                        "poly": round(cur_poly, 2),
                        "perps": round(cur_perp, 2),
                    })
                out["combined_equity_curve"] = comb_curve[-140:]
            out["performance"] = build_performance_analytics(cfg, store)
        finally:
            store.close()

    # --- מוכנות ל-Live ---
    try:
        checks = evaluate(collect_facts(cfg, reports_dir=reports_dir, backups_dir=backups_dir))
        out["readiness"] = {
            "ready": is_ready(checks),
            "summary": summary(checks),
            "checks": [c.as_dict() for c in checks],
        }
    except Exception as exc:      # noqa: BLE001
        out["readiness"] = {"ready": False, "summary": str(exc), "checks": []}

    # --- דוחות מחקר ובקטסט ---
    rdir = Path(reports_dir)
    analytics: dict = {}
    for key, fname in (("walkforward", "walkforward.json"),
                       ("perp_walkforward", "perp_walkforward.json"),
                       ("sectors", "sectors.json"),
                       ("backtest", "backtest.json"),
                       ("learning", "learning.json")):
        fpath = rdir / fname
        if fpath.exists():
            try:
                analytics[key] = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                pass
    for md_key, md_name in (("portfolio_md", "portfolio_backtest.md"),
                            ("imbalance_md", "imbalance.md")):
        mpath = rdir / md_name
        if mpath.exists():
            try:
                analytics[md_key] = mpath.read_text(encoding="utf-8")[:6000]
            except Exception:
                pass
    # חילוץ מדדים מובנים מתוך דוח תיק הפורטפוליו להצגה נקייה ללא Markdown גולמי
    pmd = analytics.get("portfolio_md", "")
    if pmd:
        def _rx(pat: str) -> str:
            m = re.search(pat, pmd, flags=re.IGNORECASE)
            return m.group(1) if m else ""

        analytics["portfolio_summary"] = {
            "final_equity": _rx(r"סופי[:\s*]+([\d.]+)"),
            "return_pct": _rx(r"\*\*([+\-\d.]+%)\*\*"),
            "trades": _rx(r"עסקאות סגורות[:\s*]+(\d+)"),
            "win_rate": _rx(r"win rate[:\s*]+([\d.]+%)"),
            "profit_factor": _rx(r"(?:profit factor|PF)[:\s*]+([\d.]+)"),
            "max_dd": _rx(r"Max Drawdown[:\s*]+([\d.]+%)"),
            "sharpe": _rx(r"Sharpe[:\s*]+([+\-\d.]+)"),
            "fees": _rx(r"עמלות ששולמו[:\s*]+([\d.]+)"),
        }
    out["analytics"] = analytics

    # --- גיבויים ---
    bdir = Path(backups_dir)
    if bdir.exists():
        bfiles = sorted(bdir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        out["backups"] = [
            {
                "name": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "ts": int(p.stat().st_mtime),
            }
            for p in bfiles[:10]
        ]

    # --- קונפיג פעיל ---
    out["config"] = {
        "execution": {
            "mode": cfg.execution.mode,
            "starting_cash": cfg.execution.starting_cash,
            "slippage_bps": cfg.execution.slippage_bps,
            "fee_mode": cfg.execution.fee_mode,
            "order_type": cfg.execution.order_type,
        },
        "universe": {
            "max_markets": cfg.universe.max_markets,
            "min_volume_24h": cfg.universe.min_volume_24h,
            "min_liquidity": cfg.universe.min_liquidity,
            "max_spread": cfg.universe.max_spread,
            "price_band": list(cfg.universe.price_band),
            "min_hours_to_resolution": cfg.universe.min_hours_to_resolution,
            "min_entry_hours_to_resolution": cfg.universe.min_entry_hours_to_resolution,
            "exclude_sectors": list(cfg.universe.exclude_sectors),
        },
        "signal": {
            "engine": cfg.signal.engine,
            "candle_fidelity_min": cfg.signal.candle_fidelity_min,
            "min_score": cfg.signal.min_score,
            "min_edge": cfg.signal.min_edge,
            "lookback_candles": cfg.signal.meanrev.lookback_candles,
            "z_entry": cfg.signal.meanrev.z_entry,
            "z_max": cfg.signal.meanrev.z_max,
            "reversion_ratio": cfg.signal.meanrev.reversion_ratio,
            "rsi_max": cfg.signal.meanrev.rsi_max,
            "max_spread_to_edge": cfg.signal.meanrev.max_spread_to_edge,
            "stop_mode": cfg.signal.exit.stop_mode,
            "take_profit": cfg.signal.exit.take_profit,
            "stop_loss": cfg.signal.exit.stop_loss,
            "time_stop_hours": cfg.signal.exit.time_stop_hours,
        },
        "risk": {
            "risk_per_trade_pct": cfg.risk.risk_per_trade_pct,
            "kelly_fraction": cfg.risk.kelly_fraction,
            "max_position_pct": cfg.risk.max_position_pct,
            "max_total_exposure_pct": cfg.risk.max_total_exposure_pct,
            "max_open_positions": cfg.risk.max_open_positions,
            "max_positions_per_event": cfg.risk.max_positions_per_event,
            "max_positions_per_sector": cfg.risk.max_positions_per_sector,
            "max_daily_loss_pct": cfg.risk.max_daily_loss_pct,
            "max_drawdown_pct": cfg.risk.max_drawdown_pct,
            "drawdown_throttle_pct": cfg.risk.drawdown_throttle_pct,
            "cooldown_minutes": cfg.risk.cooldown_minutes,
        },
        "news": {
            "enabled": cfg.news.enabled,
            "refresh_interval_sec": cfg.news.refresh_interval_sec,
            "block_on_catalyst": cfg.news.block_on_catalyst,
            "spike_window_hours": cfg.news.spike_window_hours,
            "min_spike_articles": cfg.news.min_spike_articles,
            "spike_impact_threshold": cfg.news.spike_impact_threshold,
            "volume_spike_ratio": cfg.news.volume_spike_ratio,
        },
        "learning": {
            "enabled": cfg.learning.enabled,
            "auto_apply_paper": cfg.learning.auto_apply_paper,
            "allow_auto_apply_live": cfg.learning.allow_auto_apply_live,
            "interval_sec": cfg.learning.interval_sec,
            "min_oos_trades": cfg.learning.min_oos_trades,
            "min_consistency": cfg.learning.min_consistency,
            "min_improvement_pct": cfg.learning.min_improvement_pct,
        },
        "autopilot": {
            "enabled": cfg.autopilot.enabled,
            "trade_interval_sec": cfg.autopilot.trade_interval_sec,
            "stream_interval_sec": cfg.autopilot.stream_interval_sec,
            "reconcile_every_cycles": cfg.autopilot.reconcile_every_cycles,
            "auto_fix_paper": cfg.autopilot.auto_fix_paper,
            "backup_interval_sec": cfg.autopilot.backup_interval_sec,
            "backup_keep": cfg.autopilot.backup_keep,
            "reports_interval_sec": cfg.autopilot.reports_interval_sec,
        },
        "perps": {
            "enabled": cfg.perps.enabled,
            "interval_sec": cfg.perps.interval_sec,
            "max_leverage": cfg.perps.risk.max_leverage,
            "risk_per_trade_pct": cfg.perps.risk.risk_per_trade_pct,
            "max_open_positions": cfg.perps.risk.max_open_positions,
            "max_total_margin_pct": cfg.perps.risk.max_total_margin_pct,
            "sl_atr_mult": cfg.perps.risk.sl_atr_mult,
            "tp_atr_mult": cfg.perps.risk.tp_atr_mult,
        },
    }

    # /api/state returns this builder's dictionary directly. Calculate the
    # same pure Risk Desk metrics here so the initial HTML and every automatic
    # state refresh carry identical risk fields (rather than HTML-only fields).
    try:
        from .risk_desk import build_risk_desk_metrics

        out["risk_desk"] = build_risk_desk_metrics(out)
    except Exception as exc:  # noqa: BLE001 — missing metrics must remain visibly unknown.
        out["risk_desk"] = {
            "overall_status": "warning",
            "shared_limit_configured": False,
            "notice": f"מדדי Risk Desk אינם זמינים ({type(exc).__name__}); מצב הסיכון הגלובלי אינו ידוע.",
        }

    return out


def build_perps_chart_series(store: Store, cfg, symbol: str, limit: int = 160) -> dict:
    """גרף Perps חי + קווי SL / TP / Liquidation / Entry."""
    tf = cfg.perps.signal.timeframe
    candles = store.get_perp_candles(symbol.upper(), timeframe=tf, limit=limit)
    pos = store._conn.execute(
        "SELECT * FROM perp_positions WHERE symbol=? AND mode=? AND size > 0 AND closed_at IS NULL",
        (symbol.upper(), cfg.perps.mode),
    ).fetchone()
    intel = store._conn.execute("SELECT * FROM perp_intel WHERE symbol=?", (symbol.upper(),)).fetchone()
    overlays: dict = {}
    if pos:
        overlays = {
            "side": pos["side"],
            "leverage": float(pos["leverage"]),
            "entry": float(pos["entry_price"]),
            "stop": float(pos["stop_price"]),
            "target": float(pos["target_price"]),
            "liq": float(pos["liquidation_price"]),
            "strategy": str(pos["strategy"] or ""),
        }
    return {
        "symbol": symbol.upper(),
        "timeframe": tf,
        "candles": candles,
        "overlays": overlays,
        "intel": dict(intel) if intel else {},
    }


def build_perps_status(cfg, store: Store, *, reports_dir: str | Path = "reports") -> dict:
    """בונה תמונת מצב שלמה לזרוע החוזים התמידיים (PERPS עד ×50)."""
    pc = cfg.perps
    mode = pc.mode
    now = datetime.now(tz=timezone.utc)
    day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    st_state = store.load_perp_portfolio_state(mode, pc.risk.starting_cash, now=now)
    intel_rows = store.recent_perp_intel(limit=40)
    mark_map = {str(r["symbol"]): float(r["price"]) for r in intel_rows if r.get("price")}

    open_positions = []
    unr_total = 0.0
    used_margin = 0.0
    tot_notional = 0.0
    for p in st_state["positions"]:
        mk = mark_map.get(p.symbol, p.entry_price)
        unr = p.unrealized_pnl(mk)
        roe = p.roe_pct(mk)
        liq_dist = ((mk - p.liquidation_price) / mk * 100.0) if p.side == "LONG" else ((p.liquidation_price - mk) / mk * 100.0)
        unr_total += unr
        used_margin += p.margin_used
        tot_notional += p.notional
        open_positions.append({
            "symbol": p.symbol,
            "exchange": p.exchange,
            "side": p.side,
            "size": round(p.size, 6),
            "entry_price": round(p.entry_price, 6),
            "mark_price": round(mk, 6),
            "notional": round(p.notional, 2),
            "leverage": round(p.leverage, 1),
            "margin_used": round(p.margin_used, 2),
            "liquidation_price": round(p.liquidation_price, 6),
            "liq_distance_pct": round(liq_dist, 2),
            "stop_price": round(p.stop_price, 6),
            "target_price": round(p.target_price, 6),
            "unrealized_pnl": round(unr, 2),
            "roe_pct": round(roe, 1),
            "strategy": p.strategy,
            "regime": p.regime,
            "funding": round(p.accumulated_funding, 4),
            "age_hours": round((now - p.opened_at).total_seconds() / 3600.0, 1),
        })

    equity = round(st_state["cash"] + used_margin + unr_total, 2)
    avg_lev = round(tot_notional / used_margin, 1) if used_margin > 0 else 0.0
    max_lev_open = max((p["leverage"] for p in open_positions), default=0.0)

    c = store._conn
    closes = c.execute(
        """SELECT ts, symbol, exchange, side, price, notional, leverage, realized, funding, fee, reason
           FROM perp_fills WHERE mode=? AND action IN ('CLOSE','LIQUIDATION')
           ORDER BY ts DESC, id DESC LIMIT 40""",
        (mode,),
    ).fetchall()
    all_closes = c.execute(
        "SELECT ts, realized, funding, fee FROM perp_fills WHERE mode=? AND action IN ('CLOSE','LIQUIDATION')",
        (mode,),
    ).fetchall()
    all_fees = float((c.execute("SELECT COALESCE(SUM(fee),0) s FROM perp_fills WHERE mode=?", (mode,)).fetchone()["s"]) or 0.0)
    all_fund = float((c.execute("SELECT COALESCE(SUM(funding),0) s FROM perp_fills WHERE mode=?", (mode,)).fetchone()["s"]) or 0.0)

    wins = sum(1 for r in all_closes if float(r["realized"] or 0.0) > 0)
    gp = sum(float(r["realized"] or 0.0) for r in all_closes if float(r["realized"] or 0.0) > 0)
    gl = abs(sum(float(r["realized"] or 0.0) for r in all_closes if float(r["realized"] or 0.0) <= 0))
    pf = round(gp / gl, 2) if gl > 0 else (99.0 if gp > 0 else 0.0)

    eq_rows = list(reversed(c.execute(
        "SELECT ts, equity, margin_used, avg_lev FROM perp_equity WHERE mode=? ORDER BY ts DESC LIMIT 120",
        (mode,),
    ).fetchall()))
    eq_curve = [{"ts": int(r["ts"]), "equity": float(r["equity"]), "margin": float(r["margin_used"]), "lev": float(r["avg_lev"])} for r in eq_rows]

    pk = max(st_state["peak_equity"], equity)
    dd_pct = round((pk - equity) / pk * 100.0, 2) if pk > 0 else 0.0

    bt_md = ""
    for fn in ("perps_backtest.md", "perps_learning.md"):
        p_md = Path(reports_dir) / fn
        if p_md.exists():
            try:
                bt_md += p_md.read_text(encoding="utf-8")[:2500] + "\n"
            except Exception:
                pass

    default_sym = open_positions[0]["symbol"] if open_positions else (intel_rows[0]["symbol"] if intel_rows else "BTC")
    return {
        "enabled": pc.enabled,
        "mode": mode,
        "timeframe": pc.signal.timeframe,
        "max_leverage": pc.risk.max_leverage,
        "dynamic_leverage": pc.risk.dynamic_leverage,
        "exchanges": list(pc.exchange.enabled_exchanges),
        "equity": equity,
        "cash": round(st_state["cash"], 2),
        "margin_used": round(used_margin, 2),
        "notional": round(tot_notional, 2),
        "avg_leverage": avg_lev,
        "max_leverage_open": max_lev_open,
        "unrealized_pnl": round(unr_total, 2),
        "today_pnl": round(st_state["realized_pnl_today"], 2),
        "overall_pnl": round(st_state["realized_pnl"], 2),
        "drawdown_pct": dd_pct,
        "closed_trades": len(all_closes),
        "win_rate_pct": round(wins / len(all_closes) * 100.0, 1) if all_closes else 0.0,
        "profit_factor": pf,
        "fees_paid": round(all_fees, 2),
        "funding_net": round(all_fund, 3),
        "positions": open_positions,
        "recent_trades": [dict(r) for r in closes],
        "intel": intel_rows,
        "equity_curve": eq_curve,
        "learning_runs": store.recent_perp_learning_runs(limit=10),
        "signal_stats": store.perp_signal_outcome_stats(days=30),
        "default_chart": build_perps_chart_series(store, cfg, default_sym),
        "reports_md": bt_md,
        "guards": {
            "max_margin_pct": round(pc.risk.max_total_margin_pct * 100, 0),
            "used_margin_pct": round(used_margin / equity * 100, 1) if equity > 0 else 0.0,
            "daily_loss_limit": round(equity * pc.risk.max_daily_loss_pct, 2),
            "dd_limit_pct": round(pc.risk.max_drawdown_pct * 100, 1),
            "liq_buffer_mult": pc.risk.liquidation_buffer_mult,
            "sl_atr_mult": pc.risk.sl_atr_mult,
            "tp_atr_mult": pc.risk.tp_atr_mult,
            "positions_room": max(0, pc.risk.max_open_positions - len(open_positions)),
        },
    }


def sparkline(points: list[dict], *, w: int = 260, h: int = 56) -> str:
    """
    גרף הון כ-SVG טהור — בלי JS ובלי ספריות. עובד גם ברשת איטית בטלפון.
    """
    vals = [p["equity"] for p in points if isinstance(p.get("equity"), (int, float))]
    if len(vals) < 2:
        return ("<div style='color:#4d5a6d;font-size:12px'>אין עדיין עקומת הון "
                "(צריך לפחות שני snapshots)</div>")
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{h - (v - lo) / span * (h - 6) - 3:.1f}"
                   for i, v in enumerate(vals))
    up = vals[-1] >= vals[0]
    color = "#22c55e" if up else "#ef4444"
    delta = vals[-1] - vals[0]
    return (
        f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' "
        f"style='display:block;overflow:visible'>"
        f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2' "
        f"stroke-linejoin='round' stroke-linecap='round'/></svg>"
        f"<div style='color:#6b7a90;font-size:11px'>מ-{vals[0]:.2f} ל-{vals[-1]:.2f} "
        f"({delta:+.2f})</div>"
    )


def status_html(st: dict, *, refresh_sec: int = 30) -> str:
    """עמוד יחיד, RTL, כהה, בלי JS ובלי משאבים חיצוניים — עובד גם בטלפון וגם בסנדבוקס."""
    h = st.get("health") or {}
    hb = st.get("heartbeat") or {}
    halt = st.get("halt")
    bank = st.get("bankroll") or {}
    today = st.get("today") or {}
    overall = st.get("overall") or {}
    soak = st.get("soak") or {"days": 0, "target_days": 7}
    ok = bool(h.get("healthy"))
    color = "#22c55e" if ok else "#ef4444"
    status_txt = "תקין ורץ" if ok else f"לא בריא — {_esc(h.get('reason', ''))}"

    halt_banner = ""
    if halt or (hb and hb.get("halted")):
        reason = _esc((halt or {}).get("reason") or (hb or {}).get("halt_reason") or "עצירה פעילה")
        src = _esc((halt or {}).get("source") or "risk")
        halt_banner = (
            f"<div style='background:#3b1116;border:1px solid #ef4444;border-radius:10px;"
            f"padding:12px 14px;margin-bottom:16px;color:#fecaca;font-size:13px'>"
            f"🛑 <b>עצירת מסחר פעילה ({src}):</b> {reason}</div>"
        )

    def card(title: str, value: str, sub: str = "") -> str:
        return (f"<div style='background:#151a21;border:1px solid #232b36;border-radius:12px;"
                f"padding:14px 16px;min-width:140px;flex:1'>"
                f"<div style='color:#8b98ab;font-size:12px;margin-bottom:6px'>{title}</div>"
                f"<div style='font-size:22px;font-weight:700;color:#e8eef7'>{value}</div>"
                f"<div style='color:#6b7a90;font-size:11px;margin-top:4px'>{sub}</div></div>")

    unr_total = bank.get("unrealized_pnl") or 0.0
    pf_val = overall.get("profit_factor")
    pf_str = f"PF {pf_val}" if pf_val is not None else "PF —"
    cards = "".join([
        card("הון", f"{bank.get('equity', 0) or 0:.2f}", f"לא ממומש {unr_total:+.2f}"),
        card("מזומן", f"{bank.get('cash', 0) or 0:.2f}", "USDC"),
        card("חשיפה", f"{bank.get('exposure', 0) or 0:.2f}", "בשוק"),
        card("פוזיציות", str(bank.get("open_positions", 0) or 0), "פתוחות"),
        card("PnL היום", f"{today.get('realized_pnl', 0):+.2f}", f"{today.get('exits', 0)} יציאות"),
        card("מצטבר", f"{overall.get('realized_pnl', 0) or 0:+.2f}",
             f"{overall.get('exits', 0)} סגורות · {overall.get('win_rate_pct', 0):.0f}% · {pf_str}"),
        card("עמלות", f"{overall.get('fees', today.get('fees', 0)) or 0:.2f}",
             f"היום {today.get('fees', 0):.2f} USDC"),
        card("שבוע paper", f"{soak.get('days', 0)}/{soak.get('target_days', 7)}",
             "מוכן ל-live" if soak.get("days", 0) >= soak.get("target_days", 7) else "צובר ימים"),
    ])

    def _pos_row(p: dict) -> str:
        mark = p.get("mark_price")
        unr = p.get("unrealized_pnl")
        unr_pct = p.get("unrealized_pct")
        mark_txt = f"{mark:.3f}" if mark is not None else "—"
        if unr is not None:
            uc = "#22c55e" if unr >= 0 else "#ef4444"
            unr_txt = f"<span style='color:{uc}'>{unr:+.2f} ({unr_pct:+.1f}%)</span>"
        else:
            unr_txt = "—"
        sl = f"{p['stop_price']:.2f}" if p.get("stop_price") else "—"
        tp = f"{p['target_price']:.2f}" if p.get("target_price") else "—"
        q = _esc((p.get("question") or p["token_id"])[:42])
        return (
            f"<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36;color:#e8eef7'>{q}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36'>{_esc(p['direction'])}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36'>{p['size']:.1f}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36'>{p['avg_price']:.3f}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36'>{mark_txt}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36'>{unr_txt}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36;color:#8b98ab'>{sl} / {tp}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #232b36'>{p['age_hours']:.1f}ש'</td>"
            f"</tr>"
        )

    rows = "".join(_pos_row(p) for p in (st.get("positions") or [])) or (
        "<tr><td colspan=8 style='padding:12px;color:#6b7a90'>אין פוזיציות פתוחות</td></tr>"
    )

    def _trade_row(t: dict) -> str:
        rz = t.get("realized", 0.0)
        rc = "#22c55e" if rz >= 0 else "#ef4444"
        ts_txt = datetime.fromtimestamp(t["ts"], tz=timezone.utc).strftime("%d/%m %H:%M")
        return (
            f"<tr>"
            f"<td style='padding:7px;border-bottom:1px solid #232b36;color:#6b7a90'>{ts_txt}</td>"
            f"<td style='padding:7px;border-bottom:1px solid #232b36;color:#e8eef7'>{_esc(t['question'])}</td>"
            f"<td style='padding:7px;border-bottom:1px solid #232b36'>{t['size']:.1f}</td>"
            f"<td style='padding:7px;border-bottom:1px solid #232b36'>{t['price']:.3f}</td>"
            f"<td style='padding:7px;border-bottom:1px solid #232b36;color:{rc};font-weight:600'>{rz:+.2f}</td>"
            f"<td style='padding:7px;border-bottom:1px solid #232b36;color:#8b98ab'>{_esc(t['reason'])}</td>"
            f"</tr>"
        )

    trade_rows = "".join(_trade_row(t) for t in (st.get("recent_trades") or [])) or (
        "<tr><td colspan=6 style='padding:12px;color:#6b7a90'>אין עסקאות סגורות עדיין</td></tr>"
    )

    g = st.get("guards") or {}
    guard_rows = "".join([
        f"<tr><td style='padding:7px;border-bottom:1px solid #232b36'>הפסד יומי</td>"
        f"<td style='padding:7px;border-bottom:1px solid #232b36;color:#e8eef7'>"
        f"{g.get('daily_loss_used', 0):.2f} / {g.get('daily_loss_limit', 0):.2f}</td></tr>",
        f"<tr><td style='padding:7px;border-bottom:1px solid #232b36'>drawdown</td>"
        f"<td style='padding:7px;border-bottom:1px solid #232b36;color:#e8eef7'>"
        f"{g.get('drawdown_pct', 0):.2f}% / {g.get('drawdown_limit_pct', 0):.0f}%</td></tr>",
        f"<tr><td style='padding:7px;border-bottom:1px solid #232b36'>מרווח חשיפה</td>"
        f"<td style='padding:7px;border-bottom:1px solid #232b36;color:#e8eef7'>"
        f"{g.get('exposure_room', 0):.2f} USDC</td></tr>",
        f"<tr><td style='padding:7px;border-bottom:1px solid #232b36'>פוזיציות פנויות</td>"
        f"<td style='padding:7px;border-bottom:1px solid #232b36;color:#e8eef7'>"
        f"{g.get('positions_room', 0)}</td></tr>",
    ]) or "<tr><td colspan=2 style='padding:10px;color:#6b7a90'>אין נתוני הגנות עדיין</td></tr>"

    skipped = st.get("skipped") or {}
    total_skipped = sum(skipped.values()) or 1
    skip_rows = "".join(
        f"<div style='display:flex;align-items:center;gap:8px;margin:5px 0'>"
        f"<div style='flex:0 0 190px;color:#a9b6c8;font-size:12px'>{_esc(k)}</div>"
        f"<div style='flex:1;background:#1b2330;border-radius:5px;height:8px'>"
        f"<div style='width:{v / total_skipped * 100:.0f}%;background:#3b82f6;height:8px;"
        f"border-radius:5px'></div></div>"
        f"<div style='flex:0 0 34px;text-align:left;color:#6b7a90;font-size:11px'>{v}</div></div>"
        for k, v in sorted(skipped.items(), key=lambda kv: -kv[1])
    ) or "<div style='color:#6b7a90;font-size:12px'>אין דחיות מתועדות</div>"

    ev = "".join(
        f"<li style='margin:6px 0;color:#a9b6c8'><span style='color:#6b7a90'>"
        f"{datetime.fromtimestamp(e['ts'], tz=timezone.utc).strftime('%d/%m %H:%M')}</span> "
        f"{_esc(str(e['msg'])[:110])}</li>" for e in (st.get("events") or [])
    ) or "<li style='color:#6b7a90'>אין אירועים</li>"

    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMMB — מצב הבוט</title>
{f'<meta http-equiv="refresh" content="{refresh_sec}">' if refresh_sec else ''}
</head><body style="margin:0;background:#0b0f14;color:#e8eef7;
font-family:system-ui,-apple-system,'Segoe UI',Rubik,Arial,sans-serif;padding:18px">
<div style="max-width:980px;margin:0 auto">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
    <div style="width:11px;height:11px;border-radius:50%;background:{color};
                box-shadow:0 0 12px {color}"></div>
    <h1 style="font-size:20px;margin:0">PMMB · {_esc(st.get('mode', ''))} · {_esc(st.get('engine', ''))}</h1>
  </div>
  <div style="color:#8b98ab;font-size:13px;margin-bottom:16px">
    {status_txt} · מחזור #{hb.get('cycle', 0)} · עדכון אחרון
    {hb.get('age_sec', 0) if isinstance(hb.get('age_sec'), (int, float)) else ''}
    {('· ' + _esc(str(hb.get('iso', ''))[11:19])) if hb else ''}
  </div>
  {halt_banner}
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px">{cards}</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px">
    <div style="background:#151a21;border:1px solid #232b36;border-radius:12px;
                padding:14px 16px;flex:2;min-width:260px">
      <div style="color:#8b98ab;font-size:12px;margin-bottom:8px">עקומת הון</div>
      {sparkline(st.get("equity_curve") or [])}
    </div>
    <div style="background:#151a21;border:1px solid #232b36;border-radius:12px;
                padding:14px 16px;flex:2;min-width:260px">
      <div style="color:#8b98ab;font-size:12px;margin-bottom:8px">למה לא נסחר (מחזור אחרון)</div>
      {skip_rows}
    </div>
    <div style="background:#151a21;border:1px solid #232b36;border-radius:12px;
                padding:14px 16px;flex:1;min-width:190px">
      <div style="color:#8b98ab;font-size:12px;margin-bottom:6px">הגנות</div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">{guard_rows}</table>
    </div>
  </div>
  <h2 style="font-size:15px;color:#8b98ab;margin:0 0 8px">פוזיציות פתוחות</h2>
  <div style="overflow-x:auto;margin-bottom:22px">
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="color:#6b7a90;text-align:right">
      <th style="padding:6px">שוק</th><th style="padding:6px">כיוון</th>
      <th style="padding:6px">גודל</th><th style="padding:6px">כניסה</th>
      <th style="padding:6px">נוכחי</th><th style="padding:6px">לא ממומש</th>
      <th style="padding:6px">SL / TP</th><th style="padding:6px">גיל</th></tr>
    {rows}
  </table>
  </div>
  <h2 style="font-size:15px;color:#8b98ab;margin:0 0 8px">עסקאות סגורות אחרונות</h2>
  <div style="overflow-x:auto;margin-bottom:22px">
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="color:#6b7a90;text-align:right">
      <th style="padding:6px">זמן</th><th style="padding:6px">שוק</th>
      <th style="padding:6px">גודל</th><th style="padding:6px">יציאה</th>
      <th style="padding:6px">PnL</th><th style="padding:6px">סיבה</th></tr>
    {trade_rows}
  </table>
  </div>
  <h2 style="font-size:15px;color:#8b98ab;margin:0 0 8px">אירועים אחרונים</h2>
  <ul style="padding-inline-start:18px;font-size:13px;margin:0">{ev}</ul>
  <div style="margin-top:24px;color:#4d5a6d;font-size:11px">
    /status.json · /healthz · נוצר {_esc(st.get('generated_at', ''))}
  </div>
</div></body></html>"""
