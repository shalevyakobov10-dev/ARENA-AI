"""Pure, read-only portfolio risk metrics shared by status and dashboard consumers."""
from __future__ import annotations

import math


def _risk_number(value: object) -> float | None:
    """Convert finite numeric values; missing or invalid values remain unknown."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _risk_utilization(used: float | None, limit: float | None) -> tuple[float | None, str]:
    if used is None or limit is None or limit <= 0:
        return None, "unknown"
    pct = used / limit * 100.0
    if pct >= 100.0:
        state = "over"
    elif pct >= 80.0:
        state = "warning"
    else:
        state = "healthy"
    return round(pct, 1), state


def build_risk_desk_metrics(data: dict) -> dict:
    """Summarize both venues and the enforced Paper guard without authorizing trades."""
    bankroll = data.get("bankroll") or {}
    perps = data.get("perps") or {}
    combined = data.get("combined") or {}
    config = data.get("config") or {}
    risk_cfg = config.get("risk") or {}
    perps_guards = perps.get("guards") or {}
    unified = data.get("unified_risk") or {}
    unified_guard = unified.get("guard") or {}

    poly_equity = _risk_number(bankroll.get("equity"))
    perps_enabled = bool(perps.get("enabled", True))
    total_equity = _risk_number(combined.get("equity"))
    poly_exposure = _risk_number(bankroll.get("exposure"))
    perps_notional = _risk_number(perps.get("notional"))
    perps_margin = _risk_number(perps.get("margin_used"))
    perps_positions = perps.get("positions") or []
    perps_has_risk = bool(perps_positions) or (
        (perps_notional is not None and perps_notional > 0)
        or (perps_margin is not None and perps_margin > 0)
    )
    perps_equity = _risk_number(perps.get("equity")) if (perps_enabled or perps_has_risk) else 0.0

    poly_cap_pct = _risk_number(risk_cfg.get("max_total_exposure_pct"))
    poly_limit = poly_equity * poly_cap_pct if poly_equity is not None and poly_cap_pct is not None and poly_cap_pct > 0 else None
    perps_cap_pct = _risk_number(perps_guards.get("max_margin_pct"))
    perps_margin_limit = perps_equity * perps_cap_pct / 100.0 if perps_equity is not None and perps_cap_pct is not None and perps_cap_pct > 0 else None
    poly_util, poly_status = _risk_utilization(poly_exposure, poly_limit)
    if not perps_enabled and not perps_has_risk:
        perps_util, perps_status = None, "disabled"
    else:
        perps_util, perps_status = _risk_utilization(perps_margin, perps_margin_limit)

    gross_known = poly_exposure is not None and perps_notional is not None
    gross_notional = poly_exposure + perps_notional if gross_known else None
    gross_pct = round(gross_notional / total_equity * 100.0, 1) if gross_notional is not None and total_equity is not None and total_equity > 0 else None
    perps_notional_pct = round(perps_notional / total_equity * 100.0, 1) if perps_notional is not None and total_equity is not None and total_equity > 0 else None
    open_positions = _risk_number(combined.get("open_positions"))
    if open_positions is None:
        open_positions = len(data.get("positions") or []) + len(perps.get("positions") or [])

    unified_capital_limit = _risk_number(unified_guard.get("capital_limit"))
    unified_committed = _risk_number(unified.get("committed_capital"))
    unified_utilization = _risk_number(unified_guard.get("capital_utilization_pct"))
    unified_daily_pnl = _risk_number(unified.get("daily_risk_pnl"))
    unified_daily_limit = _risk_number(unified_guard.get("daily_loss_limit"))
    unified_max_positions = _risk_number(unified_guard.get("max_open_positions"))
    unified_preflight = str(unified_guard.get("preflight_status") or "unknown").lower()
    unified_baseline = str(unified.get("baseline_status") or "unknown").lower()
    unified_halted = bool(unified_guard.get("halted"))
    shared_limit_configured = (
        bool(unified_guard.get("enabled"))
        and unified.get("status") == "ok"
        and unified_capital_limit is not None
        and unified_capital_limit > 0
    )
    unified_daily_breach = (
        unified_daily_pnl is not None
        and unified_daily_limit is not None
        and unified_daily_pnl <= -unified_daily_limit
    )

    if poly_status == "over" or perps_status == "over" or unified_halted or unified_daily_breach:
        overall_status = "breach"
    elif (
        not shared_limit_configured
        or unified_preflight != "clear"
        or poly_status in {"unknown", "warning"}
        or (perps_enabled and perps_status in {"unknown", "warning"})
    ):
        overall_status = "warning"
    else:
        overall_status = "healthy"

    if shared_limit_configured:
        notice = (
            "קיים שער הקצאת הון משותף שנאכף במנוע הכניסה במצב Paper: "
            "הוא מגביל את ההון המוקצה ומספר הפוזיציות ובודק הפסד יומי משולב מול UTC baseline. "
            "הנתונים כאן הם תמונת מצב לקריאה בלבד; אישור כל פקודה מחושב מחדש במנוע. "
            "חשיפה נומינלית ברוטו אינה הפסד מקסימלי ואינה מדד לסיכון חיסול."
        )
    else:
        notice = (
            "סטטוס שער הסיכון המאוחד אינו זמין בתשובת השרת הזו; לא התקבל מידע על תקציב חשיפה גלובלי אחד, "
            "ואין להסיק מכך שהמנגנון אינו קיים. מצב הסיכון הגלובלי מוצג כלא ידוע. "
            "חשיפה נומינלית ברוטו אינה הפסד מקסימלי ואינה מדד לסיכון חיסול."
        )

    return {
        "gross_notional": round(gross_notional, 2) if gross_notional is not None else None,
        "gross_exposure_pct": gross_pct,
        "poly_exposure": round(poly_exposure, 2) if poly_exposure is not None else None,
        "poly_limit": round(poly_limit, 2) if poly_limit is not None else None,
        "poly_utilization_pct": poly_util,
        "poly_status": poly_status,
        "perps_notional": round(perps_notional, 2) if perps_notional is not None else None,
        "perps_notional_pct": perps_notional_pct,
        "perps_margin": round(perps_margin, 2) if perps_margin is not None else None,
        "perps_margin_limit": round(perps_margin_limit, 2) if perps_margin_limit is not None else None,
        "perps_margin_utilization_pct": perps_util,
        "perps_status": perps_status,
        "perps_avg_leverage": _risk_number(perps.get("avg_leverage")) if (perps_enabled or perps_has_risk) else None,
        "open_positions": int(open_positions),
        "shared_limit_configured": shared_limit_configured,
        "unified_capital_limit": round(unified_capital_limit, 2) if unified_capital_limit is not None else None,
        "unified_committed_capital": round(unified_committed, 2) if unified_committed is not None else None,
        "unified_capital_utilization_pct": unified_utilization,
        "unified_daily_risk_pnl": round(unified_daily_pnl, 2) if unified_daily_pnl is not None else None,
        "unified_daily_loss_limit": round(unified_daily_limit, 2) if unified_daily_limit is not None else None,
        "unified_max_open_positions": int(unified_max_positions) if unified_max_positions is not None else None,
        "unified_preflight_status": unified_preflight,
        "unified_baseline_status": unified_baseline,
        "unified_halted": unified_halted,
        "unified_blockers": list(unified_guard.get("preflight_blockers") or []),
        "overall_status": overall_status,
        "notice": notice,
    }
