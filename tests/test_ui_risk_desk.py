from pmmb.ui import build_risk_desk_metrics, command_center_html


def test_risk_desk_aggregates_both_arms_without_conflating_caps():
    data = {
        "combined": {"equity": 2000.0, "open_positions": 3},
        "bankroll": {"equity": 1000.0, "exposure": 300.0},
        "perps": {
            "enabled": True,
            "equity": 1000.0,
            "notional": 1800.0,
            "margin_used": 200.0,
            "avg_leverage": 9.0,
            "guards": {"max_margin_pct": 50.0},
            "positions": [{}, {}],
        },
        "positions": [{}],
        "config": {"risk": {"max_total_exposure_pct": 0.5}},
    }

    metrics = build_risk_desk_metrics(data)

    assert metrics["gross_notional"] == 2100.0
    assert metrics["gross_exposure_pct"] == 105.0
    assert metrics["poly_limit"] == 500.0
    assert metrics["poly_utilization_pct"] == 60.0
    assert metrics["poly_status"] == "healthy"
    assert metrics["perps_margin_limit"] == 500.0
    assert metrics["perps_margin_utilization_pct"] == 40.0
    assert metrics["perps_status"] == "healthy"
    assert metrics["open_positions"] == 3
    assert metrics["shared_limit_configured"] is False
    assert metrics["overall_status"] == "warning"
    assert "אינה הפסד מקסימלי" in metrics["notice"]


def test_risk_desk_does_not_turn_missing_exposure_into_zero():
    metrics = build_risk_desk_metrics({
        "combined": {"equity": 1000.0},
        "bankroll": {"equity": 500.0},
        "perps": {"enabled": False},
        "config": {"risk": {"max_total_exposure_pct": 0.4}},
    })

    assert metrics["poly_exposure"] is None
    assert metrics["gross_notional"] is None
    assert metrics["poly_utilization_pct"] is None
    assert metrics["perps_status"] == "disabled"
    assert metrics["overall_status"] == "warning"


def test_disabled_perps_arm_still_reports_existing_positions_and_margin():
    metrics = build_risk_desk_metrics({
        "combined": {"equity": 2000.0, "open_positions": 1},
        "bankroll": {"equity": 1000.0, "exposure": 100.0},
        "perps": {
            "enabled": False,
            "equity": 1000.0,
            "notional": 800.0,
            "margin_used": 160.0,
            "avg_leverage": 5.0,
            "positions": [{"symbol": "BTC"}],
            "guards": {"max_margin_pct": 50.0},
        },
        "config": {"risk": {"max_total_exposure_pct": 0.4}},
    })

    assert metrics["gross_notional"] == 900.0
    assert metrics["perps_margin"] == 160.0
    assert metrics["perps_margin_limit"] == 500.0
    assert metrics["perps_status"] == "healthy"
    assert metrics["perps_avg_leverage"] == 5.0


def test_risk_desk_flags_exposure_or_margin_above_arm_limit():
    metrics = build_risk_desk_metrics({
        "combined": {"equity": 1000.0, "open_positions": 2},
        "bankroll": {"equity": 500.0, "exposure": 300.0},
        "perps": {
            "enabled": True, "equity": 500.0, "notional": 1000.0,
            "margin_used": 300.0, "guards": {"max_margin_pct": 50.0},
        },
        "config": {"risk": {"max_total_exposure_pct": 0.4}},
    })

    assert metrics["poly_status"] == "over"
    assert metrics["perps_status"] == "over"
    assert metrics["overall_status"] == "breach"


def test_command_center_includes_risk_desk_and_refresh_recalculation():
    html = command_center_html({
        "mode": "paper",
        "combined": {"equity": 1000.0},
        "bankroll": {"equity": 500.0, "exposure": 100.0},
        "perps": {"enabled": False},
        "config": {"risk": {"max_total_exposure_pct": 0.4}},
    })

    assert 'id="risk-desk"' in html
    assert "שולחן סיכון" in html
    assert "חשיפה נומינלית ברוטו" in html
    assert "function riskDeskMetrics(data)" in html
    assert "const m = riskDeskMetrics(DATA);" in html
    assert "מדדי החשיפה כאן מיועדים לניטור בלבד" in html


def _unified_snapshot(*, marks_fresh=True, halted=False, preflight_status=None, blockers=None):
    if preflight_status is None:
        preflight_status = "blocked" if (not marks_fresh or halted) else "clear"
    if blockers is None:
        blockers = ["fresh synchronized marks required"] if not marks_fresh else []
    return {
        "enabled": True,
        "mode": "paper",
        "paper_only": True,
        "starting_capital": 2000.0,
        "committed_capital": 200.0,
        "capital_limit": 1000.0,
        "utilization_pct": 10.0,
        "open_positions": 2,
        "max_open_positions": 8,
        "combined_risk_pnl": -25.0,
        "daily_loss_limit": 100.0,
        "marks_fresh": marks_fresh,
        "mark_failures": [] if marks_fresh else ["perps:BTC:stale-or-invalid"],
        "halted": halted,
        "halt_reason": "daily loss threshold" if halted else "",
        "preflight_status": preflight_status,
        "preflight_blockers": blockers,
        "baseline_status": "ready" if preflight_status == "clear" else "pending",
    }


def _risk_desk_payload(unified_risk):
    return {
        "mode": "paper",
        "combined": {"equity": 2000.0, "open_positions": 2},
        "bankroll": {"equity": 1000.0, "exposure": 100.0},
        "perps": {
            "enabled": True,
            "equity": 1000.0,
            "notional": 300.0,
            "margin_used": 100.0,
            "avg_leverage": 3.0,
            "guards": {"max_margin_pct": 50.0},
            "positions": [{}, {}],
        },
        "config": {
            "risk": {"max_total_exposure_pct": 0.5},
            "portfolio_risk": {
                "max_capital_utilization_pct": 0.5,
                "max_open_positions": 8,
                "max_daily_loss_pct": 0.05,
            },
        },
        "unified_risk": unified_risk,
    }


def test_risk_desk_uses_backend_enforced_shared_gate_snapshot():
    data = _risk_desk_payload(_unified_snapshot())
    metrics = build_risk_desk_metrics(data)

    assert metrics["shared_limit_configured"] is True
    assert metrics["shared_snapshot_available"] is True
    assert metrics["shared_committed_capital"] == 200.0
    assert metrics["shared_capital_limit"] == 1000.0
    assert metrics["shared_utilization_pct"] == 10.0
    assert metrics["shared_open_positions"] == 2
    assert metrics["shared_max_positions"] == 8
    assert metrics["combined_risk_pnl"] == -25.0
    assert metrics["daily_loss_limit"] == 100.0
    assert metrics["marks_fresh"] is True
    assert metrics["halted"] is False
    assert metrics["shared_paper_only"] is True
    assert metrics["preflight_status"] == "clear"
    assert metrics["baseline_status"] == "ready"
    assert metrics["overall_status"] == "healthy"

    html = command_center_html(data)
    assert "שער סיכון משותף" in html
    assert "shared_snapshot_available" in html
    assert "combined_risk_pnl" in html
    assert "marks_fresh" in html
    assert "Paper-only" in html
    assert "כניסות Live חסומות" in html


def test_risk_desk_warns_on_stale_marks_and_flags_global_halt():
    stale = build_risk_desk_metrics(_risk_desk_payload(_unified_snapshot(marks_fresh=False)))
    assert stale["shared_snapshot_available"] is True
    assert stale["marks_fresh"] is False
    assert stale["mark_failures"] == ["perps:BTC:stale-or-invalid"]
    assert stale["overall_status"] == "warning"

    halted = build_risk_desk_metrics(_risk_desk_payload(_unified_snapshot(halted=True)))
    assert halted["halted"] is True
    assert halted["halt_reason"] == "daily loss threshold"
    assert halted["overall_status"] == "breach"

    html = command_center_html(_risk_desk_payload(_unified_snapshot(halted=True)))
    assert "daily loss threshold" in html


def test_risk_desk_blocks_healthy_state_when_unified_preflight_is_blocked():
    blocked = build_risk_desk_metrics(_risk_desk_payload(_unified_snapshot(
        preflight_status="blocked",
        blockers=["UTC baseline is pending", "cross-venue marks are not synchronized"],
    )))
    assert blocked["marks_fresh"] is True
    assert blocked["preflight_status"] == "blocked"
    assert blocked["preflight_blockers"][0] == "UTC baseline is pending"
    assert blocked["overall_status"] == "warning"
    assert blocked["preflight_status"] == "blocked"
    assert blocked["baseline_status"] == "pending"

    html = command_center_html(_risk_desk_payload(_unified_snapshot(
        preflight_status="blocked",
        blockers=["UTC baseline is pending"],
    )))
    assert "כניסות חדשות חסומות" in html
    assert "UTC baseline is pending" in html
    assert "UTC baseline:" in html
