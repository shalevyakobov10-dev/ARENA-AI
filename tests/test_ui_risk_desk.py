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
