from __future__ import annotations

from pmmb.risk_desk import build_risk_desk_metrics


def test_shared_paper_gate_is_reported_from_authoritative_status_payload():
    data = {
        "combined": {"equity": 2000.0, "open_positions": 3},
        "bankroll": {"equity": 1000.0, "exposure": 250.0},
        "perps": {
            "enabled": True,
            "equity": 1000.0,
            "notional": 1000.0,
            "margin_used": 150.0,
            "avg_leverage": 6.7,
            "guards": {"max_margin_pct": 50.0},
            "positions": [{}, {}],
        },
        "config": {"risk": {"max_total_exposure_pct": 0.5}},
        "unified_risk": {
            "status": "ok",
            "starting_capital": 2000.0,
            "committed_capital": 400.0,
            "daily_risk_pnl": -20.0,
            "baseline_status": "ready",
            "guard": {
                "enabled": True,
                "capital_limit": 1000.0,
                "capital_utilization_pct": 20.0,
                "daily_loss_limit": 100.0,
                "max_open_positions": 8,
                "preflight_status": "clear",
                "preflight_blockers": [],
                "halted": False,
            },
        },
    }
    metrics = build_risk_desk_metrics(data)
    assert metrics["shared_limit_configured"] is True
    assert metrics["unified_capital_limit"] == 1000.0
    assert metrics["unified_committed_capital"] == 400.0
    assert metrics["unified_daily_risk_pnl"] == -20.0
    assert metrics["unified_preflight_status"] == "clear"
    assert metrics["overall_status"] == "healthy"


def test_missing_unified_guard_stays_unknown_not_healthy():
    metrics = build_risk_desk_metrics({
        "combined": {"equity": 1000.0},
        "bankroll": {"equity": 500.0, "exposure": 100.0},
        "perps": {"enabled": False},
        "config": {"risk": {"max_total_exposure_pct": 0.4}},
    })
    assert metrics["shared_limit_configured"] is False
    assert metrics["overall_status"] == "warning"
    assert "תקציב חשיפה גלובלי אחד" in metrics["notice"]


def test_daily_loss_or_global_halt_is_breach():
    data = {
        "unified_risk": {
            "status": "ok",
            "committed_capital": 0.0,
            "guard": {
                "enabled": True,
                "capital_limit": 1000.0,
                "halted": True,
                "daily_loss_limit": 100.0,
                "preflight_status": "blocked",
            },
        }
    }
    metrics = build_risk_desk_metrics(data)
    assert metrics["overall_status"] == "breach"
