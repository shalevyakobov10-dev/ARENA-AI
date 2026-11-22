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
