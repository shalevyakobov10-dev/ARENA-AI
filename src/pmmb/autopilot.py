"""
מנהל התפעול העצמוני (Autopilot) — אחראי שהבוט יתפעל את כל המערכת לבד:
  - בדיקה ותיקון שלמות ה-DB (Auto-Reconcile ב-paper)
  - גיבוי SQLite חם תקופתי ושמירת היסטוריה
  - הפקת דוח יומי ודוח מוכנות Live באופן אוטומטי
  - ניטור פוזיציות פתוחות מול כתבות מתפרצות בזמן אמת
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .backup import backup_db
from .daily import build_daily_report, write_daily_report
from .data.news import match_market_news
from .notify import Notifier
from .readiness import Thresholds, collect_facts, evaluate, readiness_markdown
from .reconcile import reconcile_paper, reconcile_perps

log = logging.getLogger(__name__)


def run_auto_reconcile(cfg, store) -> dict[str, Any]:
    """מאמת שלמות DB (Polymarket + PERPS) מול פוזיציות ומילויים; במצב paper מתקן אוטומטית פערים."""
    if cfg.execution.mode != "paper":
        return {"ok": True, "fixed": False, "summary": "דילוג (מצב live — דורש סנכרון מפורש)"}

    rep = reconcile_paper(store, starting_cash=cfg.execution.starting_cash, fix=False)
    perps_enabled = bool(cfg.perps.enabled and cfg.perps.mode == "paper")
    p_rep = None
    if perps_enabled:
        # Always inspect first. A zero fix count does not mean the Perps ledger is clean.
        p_rep = reconcile_perps(
            store, mode="paper", starting_cash=cfg.perps.risk.starting_cash, fix=False
        )

    perps_clean = p_rep.clean if p_rep is not None else True
    if rep.clean and perps_clean:
        store.record_autopilot_run("reconcile", "ok", "אימות DB נקי (Polymarket + PERPS) — 0 פערים")
        return {"ok": True, "fixed": False, "summary": "0 פערים"}

    if cfg.autopilot.auto_fix_paper:
        rep_fix = reconcile_paper(store, starting_cash=cfg.execution.starting_cash, fix=True)
        rep_verify = reconcile_paper(store, starting_cash=cfg.execution.starting_cash, fix=False)
        p_fixed = None
        p_verify = None
        if perps_enabled:
            p_fixed = reconcile_perps(
                store, mode="paper", starting_cash=cfg.perps.risk.starting_cash, fix=True
            )
            p_verify = reconcile_perps(
                store, mode="paper", starting_cash=cfg.perps.risk.starting_cash, fix=False
            )
        perp_fixed = p_fixed.fixes_applied if p_fixed is not None else 0
        perps_clean_after = p_verify.clean if p_verify is not None else True
        all_clean_after = rep_verify.clean and perps_clean_after
        msg = f"תוקנו אוטומטית {rep_fix.fixes_applied + perp_fixed} פערים ב-DB"
        details = {
            "discrepancies": [d.kind for d in rep_fix.discrepancies],
            "clean_after": all_clean_after,
            "perps_fixed": perp_fixed,
            "perps_clean_after": perps_clean_after,
        }
        store.record_autopilot_run("reconcile", "fixed" if all_clean_after else "warn", msg, details=details)
        store.event("autopilot_reconcile", msg, level="WARNING")
        return {"ok": all_clean_after, "fixed": bool(rep_fix.fixes_applied or perp_fixed), "summary": msg}

    total_discrepancies = len(rep.discrepancies) + (len(p_rep.discrepancies) if p_rep is not None else 0)
    msg = f"זוהו {total_discrepancies} פערים (תיקון אוטומטי כבוי)"
    store.record_autopilot_run("reconcile", "warn", msg)
    return {"ok": False, "fixed": False, "summary": msg}


def run_auto_backup(cfg, store, *, backups_dir: str | Path = "backups") -> dict[str, Any]:
    b = backup_db(cfg.data.db_path, backups_dir=backups_dir, keep=cfg.autopilot.backup_keep)
    msg = f"גיבוי אוטומטי נשמר: {b.path.name} ({b.size_bytes / 1024:.1f} KB)"
    store.record_autopilot_run("backup", "ok", msg, details={"path": str(b.path), "size_bytes": b.size_bytes})
    return {"ok": True, "path": str(b.path), "summary": msg}


def run_auto_reports(
    cfg,
    store,
    *,
    reports_dir: str | Path = "reports",
    backups_dir: str | Path = "backups",
) -> dict[str, Any]:
    rep_d = build_daily_report(
        store, hours=24.0,
        starting_cash=cfg.execution.starting_cash,
        planned_horizon_hours=cfg.signal.exit.time_stop_hours,
        mode=cfg.execution.mode,
    )
    d_path = write_daily_report(rep_d, out_dir=reports_dir)
    checks = evaluate(collect_facts(cfg, reports_dir=reports_dir, backups_dir=backups_dir))
    r_dir = Path(reports_dir)
    r_dir.mkdir(parents=True, exist_ok=True)
    r_path = r_dir / "readiness.md"
    r_path.write_text(readiness_markdown(checks, Thresholds()), encoding="utf-8")
    # סיכום זרוע PERPS משולב בדוח התקופתי
    try:
        from .status import build_perps_status

        ps = build_perps_status(cfg, store, reports_dir=reports_dir)
        (r_dir / "perps_status.md").write_text(
            f"# דוח Perps חי\n- הון: {ps['equity']:.2f} USDC | פוזיציות: {len(ps['positions'])} "
            f"| מרג'ין מנוצל: {ps['margin_used']:.2f} | מינוף ממוצע: {ps['avg_leverage']:.1f}x\n"
            f"- סה\"כ עסקאות סגורות: {ps['closed_trades']} | PnL ממומש: {ps['overall_pnl']:+.2f} | Funding: {ps['funding_net']:+.3f}\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    passed = sum(1 for c in checks if c.status == "ok")
    msg = f"דוחות עודכנו ({passed}/{len(checks)} בדיקות מוכנות עברו)"
    store.record_autopilot_run(
        "reports", "ok", msg,
        details={"daily": str(d_path), "readiness": str(r_path)},
    )
    return {"ok": True, "summary": msg, "passed": passed, "total": len(checks)}


def monitor_open_positions_news(
    positions,
    news_articles: list[dict],
    cfg,
    store,
    *,
    notifier: Notifier | None = None,
    seen_alerts: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    מנטר פוזיציות פתוחות מול כתבות מתפרצות שנולדו בזמן האחרון.
    מחזיר רשימת אזהרות (לתיעוד והתרעה, בלי לייצר ספאם כפול).
    """
    alerts: list[dict[str, Any]] = []
    if not positions or not news_articles:
        return alerts

    for pos in positions:
        q = getattr(pos, "question", "") or ""
        if not q:
            continue
        opened_ts = int(pos.opened_at.timestamp()) if getattr(pos, "opened_at", None) else 0
        # רק חדשות שנולדו אחרי הפתיחה או בשעתיים שלפניה
        recent = [a for a in news_articles if int(a.get("ts") or 0) >= max(0, opened_ts - 7200)]
        nm = match_market_news(
            q, recent,
            window_hours=max(6.0, cfg.news.spike_window_hours),
            min_articles=2,
            impact_threshold=max(0.75, cfg.news.spike_impact_threshold),
        )
        if nm.catalyst_detected and nm.avg_sentiment <= -0.35:
            key = f"{pos.token_id[:12]}:{nm.latest_title[:48]}"
            if seen_alerts is not None and key in seen_alerts:
                continue
            if seen_alerts is not None:
                seen_alerts.add(key)
            alert = {
                "token_id": pos.token_id[:12],
                "question": q[:60],
                "impact": nm.max_impact,
                "sentiment": nm.avg_sentiment,
                "title": nm.latest_title,
            }
            alerts.append(alert)
            store.event(
                "position_news_alert",
                f"חדשות שליליות על פוזיציה פתוחה ({q[:40]}): {nm.latest_title[:70]}",
                level="WARNING",
                data=alert,
            )
            if notifier is not None:
                notifier.send(f"אזהרת חדשות על פוזיציה: {q[:50]} | {nm.latest_title[:80]}")
    return alerts


def run_autonomous_housekeeping(
    cfg,
    store,
    *,
    reports_dir: str | Path = "reports",
    backups_dir: str | Path = "backups",
) -> dict[str, Any]:
    """
    מחזור תחזוקה ואופטימיזציה אוטונומית של המערכת:
      1. PRAGMA optimize + WAL passive checkpoint למניעת ניפוח ולשימור מהירות.
      2. אימות ותיקון פערים ב-DB (Polymarket + PERPS).
      3. הפקת דוחות מוכנות וסיכום יומי.
      4. שמירת דוח מצב מערכת JSON בתיקיית הדוחות.
    """
    import json
    import time

    now = int(time.time())
    db_file = Path(cfg.data.db_path)
    try:
        store._conn.execute("PRAGMA optimize")
        store._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    except Exception as exc:
        log.debug("DB optimize/checkpoint דילוג: %s", exc)

    rec = run_auto_reconcile(cfg, store)
    rep = run_auto_reports(cfg, store, reports_dir=reports_dir, backups_dir=backups_dir)
    db_size_kb = round(db_file.stat().st_size / 1024.0, 1) if db_file.exists() else 0.0

    rdir = Path(reports_dir)
    rdir.mkdir(parents=True, exist_ok=True)
    status_obj = {
        "updated_at": now,
        "db_size_kb": db_size_kb,
        "reconcile_clean": bool(rec.get("ok")),
        "reconcile_summary": rec.get("summary", ""),
        "reports_passed": rep.get("passed", 0),
        "reports_total": rep.get("total", 0),
    }
    try:
        (rdir / "autonomous_status.json").write_text(json.dumps(status_obj, indent=2), encoding="utf-8")
    except Exception:
        pass

    msg = f"תחזוקה אוטונומית הושלמה: DB {db_size_kb:.1f}KB · {rec.get('summary')} · {rep.get('passed')}/{rep.get('total')} מוכנות"
    store.record_autopilot_run("housekeeping", "ok", msg, details=status_obj)
    return {"ok": True, "summary": msg, **status_obj}

