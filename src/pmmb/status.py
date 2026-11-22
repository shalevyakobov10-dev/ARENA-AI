"""
מצב המערכת בקריאוּת אחת — לבן אדם בטלפון ולמכונה ב-JSON.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .runtime import check_health, read_heartbeat


def _day_start_ts() -> int:
    now = datetime.now(tz=timezone.utc)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def build_status(cfg, *, max_age_sec: float = 300) -> dict:
    """
    מרכיב מצב מלא: דופק, בריאות, פוזיציות פתוחות, עסקאות היום, PnL ממומש,
    אירועים אחרונים. לא נוגע ברשת — רק DB + קובץ דופק.
    """
    from .data.store import Store

    health = check_health(max_age_sec=max_age_sec)
    hb = health.heartbeat or read_heartbeat()
    out: dict = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "mode": cfg.execution.mode,
        "engine": cfg.signal.engine,
        "health": health.as_dict(),
        "heartbeat": hb.as_dict() if hb else None,
        "positions": [],
        "today": {},
        "bankroll": {},
    }

    db = Path(cfg.data.db_path)
    if not db.exists():
        out["warning"] = "מסד הנתונים לא נמצא — הבוט כנראה לא רץ עדיין"
        return out

    store = Store(db)
    try:
        day = _day_start_ts()
        pos = store.open_positions(cfg.execution.mode)
        out["positions"] = [{
            "token_id": r["token_id"][:12], "condition_id": (r["condition_id"] or "")[:12],
            "direction": r["direction"], "size": round(r["size"], 2),
            "avg_price": round(r["avg_price"], 4),
            "opened_at": r["opened_at"],
            "age_hours": round((time.time() - (r["opened_at"] or time.time())) / 3600, 1),
            "realized_pnl": round(r["realized_pnl"] or 0.0, 2),
        } for r in pos]

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
            row = c.execute("SELECT equity, cash, exposure, positions FROM equity "
                            "ORDER BY ts DESC LIMIT 1").fetchone()
        out["bankroll"] = {
            "equity": round(row["equity"], 2) if row else None,
            "cash": round(row["cash"], 2) if row else None,
            "exposure": round(row["exposure"], 2) if row else None,
            "open_positions": row["positions"] if row else None,
        }
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


def status_html(st: dict, *, refresh_sec: int = 30) -> str:
    """עמוד יחיד, RTL, כהה, בלי JS ובלי משאבים חיצוניים — עובד גם בטלפון וגם בסנדבוקס."""
    h = st.get("health") or {}
    hb = st.get("heartbeat") or {}
    bank = st.get("bankroll") or {}
    today = st.get("today") or {}
    ok = bool(h.get("healthy"))
    color = "#22c55e" if ok else "#ef4444"
    status_txt = "תקין ורץ" if ok else f"לא בריא — {h.get('reason', '')}"

    def card(title: str, value: str, sub: str = "") -> str:
        return (f"<div style='background:#151a21;border:1px solid #232b36;border-radius:12px;"
                f"padding:14px 16px;min-width:150px;flex:1'>"
                f"<div style='color:#8b98ab;font-size:12px;margin-bottom:6px'>{title}</div>"
                f"<div style='font-size:22px;font-weight:700;color:#e8eef7'>{value}</div>"
                f"<div style='color:#6b7a90;font-size:11px;margin-top:4px'>{sub}</div></div>")

    cards = "".join([
        card("הון", f"{bank.get('equity', 0) or 0:.2f}", "USDC"),
        card("מזומן", f"{bank.get('cash', 0) or 0:.2f}", "USDC"),
        card("חשיפה", f"{bank.get('exposure', 0) or 0:.2f}", "בשוק"),
        card("פוזיציות", str(bank.get("open_positions", 0) or 0), "פתוחות"),
        card("PnL היום", f"{today.get('realized_pnl', 0):+.2f}", f"{today.get('exits', 0)} יציאות"),
        card("עמלות היום", f"{today.get('fees', 0):.2f}", "USDC"),
    ])

    rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #232b36'>{p['direction']}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #232b36'>{p['size']:.1f}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #232b36'>{p['avg_price']:.3f}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #232b36'>{p['age_hours']:.1f}ש'</td>"
        f"<td style='padding:8px;border-bottom:1px solid #232b36'>{p['token_id']}</td></tr>"
        for p in (st.get("positions") or [])
    ) or "<tr><td colspan=5 style='padding:12px;color:#6b7a90'>אין פוזיציות פתוחות</td></tr>"

    ev = "".join(
        f"<li style='margin:6px 0;color:#a9b6c8'><span style='color:#6b7a90'>"
        f"{datetime.fromtimestamp(e['ts'], tz=timezone.utc).strftime('%d/%m %H:%M')}</span> "
        f"{e['msg'][:110]}</li>" for e in (st.get("events") or [])
    ) or "<li style='color:#6b7a90'>אין אירועים</li>"

    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMMB — מצב הבוט</title>
{f'<meta http-equiv="refresh" content="{refresh_sec}">' if refresh_sec else ''}
</head><body style="margin:0;background:#0b0f14;color:#e8eef7;
font-family:system-ui,-apple-system,'Segoe UI',Rubik,Arial,sans-serif;padding:18px">
<div style="max-width:940px;margin:0 auto">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
    <div style="width:11px;height:11px;border-radius:50%;background:{color};
                box-shadow:0 0 12px {color}"></div>
    <h1 style="font-size:20px;margin:0">PMMB · {st.get('mode', '')} · {st.get('engine', '')}</h1>
  </div>
  <div style="color:#8b98ab;font-size:13px;margin-bottom:18px">
    {status_txt} · מחזור #{hb.get('cycle', 0)} · עדכון אחרון
    {hb.get('age_sec', 0) if isinstance(hb.get('age_sec'), (int, float)) else ''}
    {('· ' + str(hb.get('iso', ''))[11:19]) if hb else ''}
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px">{cards}</div>
  <h2 style="font-size:15px;color:#8b98ab;margin:0 0 8px">פוזיציות פתוחות</h2>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:22px">
    <tr style="color:#6b7a90;text-align:right">
      <th style="padding:6px">כיוון</th><th style="padding:6px">גודל</th>
      <th style="padding:6px">מחיר</th><th style="padding:6px">גיל</th>
      <th style="padding:6px">טוקן</th></tr>
    {rows}
  </table>
  <h2 style="font-size:15px;color:#8b98ab;margin:0 0 8px">אירועים אחרונים</h2>
  <ul style="padding-inline-start:18px;font-size:13px;margin:0">{ev}</ul>
  <div style="margin-top:24px;color:#4d5a6d;font-size:11px">
    /status.json · /healthz · נוצר {st.get('generated_at', '')}
  </div>
</div></body></html>"""
