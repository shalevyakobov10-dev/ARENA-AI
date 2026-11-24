"""Tests for the PMMB Command Center operations view."""
from __future__ import annotations

from pmmb.ui import command_center_html


def test_command_center_renders_operations_tab_and_panels() -> None:
    html = command_center_html(
        {
            "mode": "paper",
            "health": {"healthy": True},
            "heartbeat": {"ts": 1_800_000_000, "halted": False},
            "trader": {"running": True},
            "combined": {"equity": 1200.0},
            "telemetry": {"ticks": 10},
            "readiness": {"ready": False, "checks": []},
            "events": [],
        },
        refresh_sec=10,
    )

    assert 'data-tab="ops"' in html
    assert 'id="tab-ops"' in html
    assert 'id="ops-overview-grid"' in html
    assert 'id="ops-risk-grid"' in html
    assert 'id="ops-freshness-grid"' in html
    assert 'id="ops-telemetry-grid"' in html
    assert 'id="ops-gates-body"' in html
    assert 'id="ops-event-body"' in html
    assert "function renderOpsTab()" in html
    assert "renderOpsTab();" in html


def test_command_center_escapes_script_terminators_in_initial_data() -> None:
    payload = {"events": [{"msg": "</script><script>alert(1)</script>"}]}
    html = command_center_html(payload, refresh_sec=0)

    assert "</script><script>alert(1)</script>" not in html
    assert "<\\/script>" in html

def test_operations_scan_controls_are_gated_by_each_venue_mode() -> None:
    html = command_center_html(
        {
            "mode": "paper",
            "perps": {"enabled": True, "mode": "live"},
        },
        refresh_sec=10,
    )

    assert 'data-ops-paper-only="poly"' in html
    assert 'data-ops-paper-only="perps"' in html
    assert 'const perpsPaper = !!perpsCfg.enabled && String(perpsCfg.mode || "").toLowerCase() === "paper";' in html
    assert 'const enabled = arm === "perps" ? perpsPaper : isPaper;' in html


def test_command_center_exposes_connection_and_freshness_state() -> None:
    html = command_center_html({"mode": "paper"}, refresh_sec=10)

    assert 'id="conn-pill"' in html
    assert 'id="conn-last"' in html
    assert 'aria-live="polite"' in html
    assert "function renderConnectionState()" in html
    assert "LAST_REFRESH_ERROR" in html
    assert 'document.addEventListener("visibilitychange"' in html
