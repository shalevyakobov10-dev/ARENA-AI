"""
שער המעבר ל-live — צ'קליסט שנבדק ע"י מכונה, לא ע"י תחושה.

המטרה: שאף אחד לא יעביר כסף אמיתי לבוט שלא עמד בקריטריונים.
כל בדיקה מחזירה ok / warn / fail, ורק fail חוסם.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"
ICON = {OK: "✅", WARN: "⚠️", FAIL: "❌"}


@dataclass
class Check:
    id: str
    label: str
    status: str
    detail: str

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "status": self.status,
                "detail": self.detail}


@dataclass
class Thresholds:
    soak_days: int = 7
    max_gap_min: float = 30.0
    min_consistency: float = 0.66
    max_errors: int = 3
    max_daily_loss_pct: float = 0.10
    max_drawdown_pct: float = 0.30
    max_exposure_pct: float = 0.60
    max_risk_per_trade_pct: float = 0.05


# ---------------------------------------------------------------- איסוף עובדות
def collect_facts(cfg, *, reports_dir: str | Path = "reports",
                  backups_dir: str | Path = "backups") -> dict:
    from .data.store import Store
    from .runtime import check_health

    facts: dict = {"cfg": cfg}

    # --- walkforward ---
    wf = Path(reports_dir) / "walkforward.json"
    try:
        facts["walkforward"] = json.loads(wf.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        facts["walkforward"] = None

    # --- בקטסט (הוכחת חיוב עמלות) ---
    bt = Path(reports_dir) / "backtest.json"
    try:
        raw = json.loads(bt.read_text(encoding="utf-8"))
        res = raw.get("results", [])
        facts["backtest"] = {
            "trades": sum(r.get("trades", 0) for r in res),
            "fees_paid": round(sum(r.get("fees_paid", 0) for r in res), 2),
        }
    except (FileNotFoundError, json.JSONDecodeError):
        facts["backtest"] = None

    # --- שהות ב-paper: מה-DB ---
    db = Path(cfg.data.db_path)
    days: set[str] = set()
    max_gap = 0.0
    errors = 0
    if db.exists():
        store = Store(db)
        try:
            with store.tx() as c:
                rows = list(c.execute("SELECT ts FROM equity ORDER BY ts"))
                errs = c.execute("SELECT COUNT(*) AS n FROM events WHERE level='ERROR'").fetchone()
                errors = int(errs["n"] or 0)
            stamps = [r["ts"] for r in rows]
            for ts in stamps:
                from datetime import datetime, timezone
                days.add(datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"))
            max_gap = max((b - a for a, b in zip(stamps, stamps[1:])), default=0) / 60.0
        finally:
            store.close()
    facts["soak"] = {"days": len(days), "max_gap_min": round(max_gap, 1), "errors": errors}

    # --- בריאות נוכחית ---
    h = check_health()
    facts["health"] = h.as_dict()

    # --- סודות ותשתית ---
    facts["telegram"] = bool(os.environ.get("PMMB_TELEGRAM_TOKEN")
                             and os.environ.get("PMMB_TELEGRAM_CHAT_ID"))
    facts["live_keys"] = bool(os.environ.get("PMMB_PRIVATE_KEY"))
    backup_dir = Path(backups_dir)
    newest = max((p.stat().st_mtime for p in backup_dir.glob("*")), default=0) if backup_dir.exists() else 0
    import time
    facts["backup_age_days"] = round((time.time() - newest) / 86400, 1) if newest else None
    return facts


# ---------------------------------------------------------------- הערכה
def evaluate(facts: dict, th: Thresholds | None = None) -> list[Check]:
    th = th or Thresholds()
    cfg = facts["cfg"]
    out: list[Check] = []

    # 1. עמלות במודל
    bt = facts.get("backtest")
    if cfg.execution.fee_mode != "model":
        out.append(Check("fees", "עמלות במודל", FAIL,
                         f"fee_mode={cfg.execution.fee_mode} — העמלה לא מתומחרת"))
    elif not bt:
        out.append(Check("fees", "עמלות במודל", WARN, "אין reports/backtest.json — לא הוכח שנגבו עמלות"))
    elif bt["fees_paid"] > 0:
        out.append(Check("fees", "עמלות במודל", OK,
                         f"נגבו {bt['fees_paid']} USDC על {bt['trades']} עסקאות בבקטסט"))
    else:
        out.append(Check("fees", "עמלות במודל", FAIL, "הבקטסט לא גבה עמלות — המודל לא מחובר"))

    # 2. walk-forward
    wf = facts.get("walkforward")
    if not wf:
        out.append(Check("walkforward", "אימות מחוץ למדגם", FAIL, "אין reports/walkforward.json"))
    elif wf["consistency"] >= th.min_consistency and wf["oos_pnl"] > 0:
        out.append(Check("walkforward", "אימות מחוץ למדגם", OK,
                         f"OOS {wf['oos_pnl']:+.2f} על {wf['oos_trades']} עסקאות · "
                         f"עקביות {wf['consistency']:.0%}"))
    else:
        out.append(Check("walkforward", "אימות מחוץ למדגם", FAIL,
                         f"OOS {wf['oos_pnl']:+.2f} · עקביות {wf['consistency']:.0%} "
                         f"(נדרש ≥{th.min_consistency:.0%} וחיובי)"))

    # 3. שהות ב-paper
    soak = facts.get("soak") or {"days": 0, "max_gap_min": 0, "errors": 0}
    if soak["days"] >= th.soak_days:
        out.append(Check("soak", "שבוע paper נקי", OK,
                         f"{soak['days']} ימים עם דופק · פער מרבי {soak['max_gap_min']:.0f} דק'"))
    else:
        out.append(Check("soak", "שבוע paper נקי", FAIL,
                         f"רק {soak['days']} ימים מתוך {th.soak_days} — המשך להריץ paper"))

    # 4. פערים בהרצה
    if soak["max_gap_min"] > th.max_gap_min:
        out.append(Check("gaps", "רציפות הרצה", WARN,
                         f"פער מרבי {soak['max_gap_min']:.0f} דק' — הבוט נעצר או נתקע"))
    else:
        out.append(Check("gaps", "רציפות הרצה", OK, "אין פערים חריגים"))

    # 5. שגיאות
    if soak["errors"] > th.max_errors:
        out.append(Check("errors", "שגיאות בלוג", FAIL,
                         f"{soak['errors']} שגיאות ERROR — לבדוק לפני live"))
    elif soak["errors"]:
        out.append(Check("errors", "שגיאות בלוג", WARN, f"{soak['errors']} שגיאות ERROR"))
    else:
        out.append(Check("errors", "שגיאות בלוג", OK, "אפס שגיאות ERROR"))

    # 6. הגבלות סיכון שפויות
    r = cfg.risk
    problems = []
    if r.max_daily_loss_pct > th.max_daily_loss_pct:
        problems.append(f"סטופ יומי {r.max_daily_loss_pct:.0%}")
    if r.max_drawdown_pct > th.max_drawdown_pct:
        problems.append(f"drawdown {r.max_drawdown_pct:.0%}")
    if r.max_total_exposure_pct > th.max_exposure_pct:
        problems.append(f"חשיפה {r.max_total_exposure_pct:.0%}")
    if r.risk_per_trade_pct > th.max_risk_per_trade_pct:
        problems.append(f"סיכון לעסקה {r.risk_per_trade_pct:.0%}")
    out.append(Check("risk_limits", "גבולות סיכון", FAIL if problems else OK,
                     "; ".join(problems) if problems else
                     f"יומי {r.max_daily_loss_pct:.0%} · DD {r.max_drawdown_pct:.0%} · "
                     f"חשיפה {r.max_total_exposure_pct:.0%} · {r.max_open_positions} פוזיציות"))

    # 7. התראות
    out.append(Check("telegram", "התראות לטלפון",
                     OK if facts.get("telegram") else WARN,
                     "מוגדר" if facts.get("telegram") else "לא הוגדר — תפספס עצירות"))

    # 8. דופק עכשיו
    h = facts.get("health") or {}
    out.append(Check("heartbeat", "הבוט רץ כעת",
                     OK if h.get("healthy") else WARN, h.get("reason", "לא ידוע")))

    # 9. מפתחות live
    has_keys = bool(facts.get("live_keys"))
    out.append(Check("live_keys", "מפתח פרטי ל-live",
                     OK if has_keys else (FAIL if cfg.execution.mode == "live" else WARN),
                     "מוגדר בסביבה" if has_keys else "PMMB_PRIVATE_KEY אינו מוגדר (נדרש להרצת live)"))

    # 10. גיבוי
    age = facts.get("backup_age_days")
    if age is None:
        out.append(Check("backup", "גיבוי DB", WARN, "אין גיבוי — הקם cron ל-backups/"))
    elif age <= 7:
        out.append(Check("backup", "גיבוי DB", OK, f"גיבוי בן {age:.1f} ימים"))
    else:
        out.append(Check("backup", "גיבוי DB", WARN, f"הגיבוי האחרון בן {age:.0f} ימים"))

    return out


def is_ready(checks: list[Check]) -> bool:
    return all(c.status != FAIL for c in checks)


def summary(checks: list[Check]) -> str:
    fails = [c for c in checks if c.status == FAIL]
    warns = [c for c in checks if c.status == WARN]
    if not fails:
        tail = f" · {len(warns)} אזהרות" if warns else ""
        return f"🟢 מוכן ל-live{tail}"
    return f"🔴 לא מוכן — {len(fails)} קריטריונים נכשלו: " + ", ".join(c.id for c in fails)


def readiness_markdown(checks: list[Check], th: Thresholds) -> str:
    lines = ["# שער המעבר ל-live", "",
             f"קריטריונים: {th.soak_days} ימי paper · עקביות ≥{th.min_consistency:.0%} · "
             f"עד {th.max_errors} שגיאות · סטופ יומי ≤{th.max_daily_loss_pct:.0%}", "",
             "| | בדיקה | פירוט |", "|---|---|---|"]
    for c in checks:
        lines.append(f"| {ICON[c.status]} | {c.label} | {c.detail} |")
    lines += ["", f"**{summary(checks)}**"]
    return "\n".join(lines)
