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
from .reconcile import reconcile_paper

log = logging.getLogger(__name__)


def run_auto_reconcile(cfg, store) -> dict[str, Any]:
    """מאמת שלמות DB מול פוזיציות ומילויים; במצב paper מתקן אוטומטית פערים."""
    if cfg.execution.mode != "paper":
        return {"ok": True, "fixed": False, "summary": "דילוג (מצב live — דורש סנכרון מפורש)"}

    rep = reconcile_paper(store, starting_cash=cfg.execution.starting_cash, fix=False)
    if rep.clean:
        store.record_autopilot_run("reconcile", "ok", "אימות DB נקי — 0 פערים")
        return {"ok": True, "fixed": False, "summary": "0 פערים"}

    if cfg.autopilot.auto_fix_paper:
        rep_fix = reconcile_paper(store, starting_cash=cfg.execution.starting_cash, fix=True)
        rep_verify = reconcile_paper(store, starting_cash=cfg.execution.starting_cash, fix=False)
        msg = f"תוקנו אוטומטית {rep_fix.fixes_applied} פערים ב-DB"
        store.record_autopilot_run(
            "reconcile", "fixed", msg,
            details={"discrepancies": [d.kind for d in rep_fix.discrepancies], "clean_after": rep_verify.clean},
        )
        store.event("autopilot_reconcile", msg, level="WARNING")
        return {"ok": rep_verify.clean, "fixed": True, "summary": msg}

    msg = f"זוהו {len(rep.discrepancies)} פערים (תיקון אוטומטי כבוי)"
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
