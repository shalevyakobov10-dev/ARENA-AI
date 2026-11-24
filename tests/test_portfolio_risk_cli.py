from __future__ import annotations

import json
from types import SimpleNamespace

from pmmb.cli import build_parser, cmd_portfolio_risk


class _FakeStore:
    def __init__(self, _path):
        self.closed = False

    def close(self):
        self.closed = True


def _snapshot(**overrides):
    values = dict(
        starting_capital=2000.0,
        committed_capital=400.0,
        polymarket_committed=200.0,
        perps_margin_used=200.0,
        open_positions=2,
        marks_fresh=True,
        baseline_status="ready",
        daily_risk_pnl=-25.0,
        as_dict=lambda: {
            "starting_capital": 2000.0,
            "committed_capital": 400.0,
            "open_positions": 2,
            "marks_fresh": True,
            "baseline_status": "ready",
            "daily_risk_pnl": -25.0,
        },
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_portfolio_risk_command_is_registered_with_json_option():
    args = build_parser().parse_args(["portfolio-risk", "--json"])
    assert args.command == "portfolio-risk"
    assert args.json is True


def test_portfolio_risk_cli_reports_ready_snapshot(monkeypatch, cfg, capsys):
    import pmmb.data.store
    import pmmb.unified_risk

    monkeypatch.setattr(pmmb.data.store, "Store", _FakeStore)
    monkeypatch.setattr(pmmb.unified_risk, "build_unified_risk_status", lambda *_a, **_k: _snapshot())
    monkeypatch.setattr(pmmb.unified_risk, "_global_halt_reason", lambda: None)
    cfg.execution.mode = "paper"
    cfg.perps.enabled = True
    cfg.perps.mode = "paper"

    code = cmd_portfolio_risk(SimpleNamespace(json=True), cfg)
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert report["shared_gate_clear"] is True
    assert report["capital_utilization_pct"] == 40.0
    assert report["daily_loss_remaining"] == 75.0
    assert report["blockers"] == []


def test_portfolio_risk_cli_fails_closed_on_stale_marks(monkeypatch, cfg, capsys):
    import pmmb.data.store
    import pmmb.unified_risk

    monkeypatch.setattr(pmmb.data.store, "Store", _FakeStore)
    monkeypatch.setattr(
        pmmb.unified_risk, "build_unified_risk_status",
        lambda *_a, **_k: _snapshot(marks_fresh=False),
    )
    monkeypatch.setattr(pmmb.unified_risk, "_global_halt_reason", lambda: None)
    cfg.execution.mode = "paper"
    cfg.perps.enabled = True
    cfg.perps.mode = "paper"

    code = cmd_portfolio_risk(SimpleNamespace(json=True), cfg)
    report = json.loads(capsys.readouterr().out)

    assert code == 3
    assert report["entry_ready"] is False
    assert any("marks" in item for item in report["blockers"])


def test_portfolio_risk_cli_blocks_nonpaper_enabled_arm(monkeypatch, cfg, capsys):
    import pmmb.data.store
    import pmmb.unified_risk

    monkeypatch.setattr(pmmb.data.store, "Store", _FakeStore)
    monkeypatch.setattr(pmmb.unified_risk, "build_unified_risk_status", lambda *_a, **_k: _snapshot())
    monkeypatch.setattr(pmmb.unified_risk, "_global_halt_reason", lambda: None)
    cfg.execution.mode = "paper"
    cfg.perps.enabled = True
    cfg.perps.mode = "live"

    code = cmd_portfolio_risk(SimpleNamespace(json=True), cfg)
    report = json.loads(capsys.readouterr().out)

    assert code == 3
    assert any("PERPS" in item for item in report["blockers"])


def test_portfolio_risk_cli_blocks_daily_loss_limit(monkeypatch, cfg, capsys):
    import pmmb.data.store
    import pmmb.unified_risk

    monkeypatch.setattr(pmmb.data.store, "Store", _FakeStore)
    monkeypatch.setattr(
        pmmb.unified_risk, "build_unified_risk_status",
        lambda *_a, **_k: _snapshot(daily_risk_pnl=-120.0),
    )
    monkeypatch.setattr(pmmb.unified_risk, "_global_halt_reason", lambda: None)
    cfg.execution.mode = "paper"
    cfg.perps.enabled = True
    cfg.perps.mode = "paper"

    code = cmd_portfolio_risk(SimpleNamespace(json=True), cfg)
    report = json.loads(capsys.readouterr().out)

    assert code == 3
    assert any("daily loss" in item for item in report["blockers"])


def test_portfolio_risk_cli_fails_closed_when_store_cannot_be_opened(monkeypatch, cfg, capsys):
    import pmmb.data.store

    def _broken_store(_path):
        raise OSError("database unavailable")

    monkeypatch.setattr(pmmb.data.store, "Store", _broken_store)
    code = cmd_portfolio_risk(SimpleNamespace(json=True), cfg)
    report = json.loads(capsys.readouterr().out)

    assert code == 3
    assert report["shared_gate_clear"] is False
    assert "unable to verify" in report["blockers"][0]


def test_portfolio_risk_cli_blocks_when_allocation_headroom_is_exhausted(monkeypatch, cfg, capsys):
    import pmmb.data.store
    import pmmb.unified_risk

    monkeypatch.setattr(pmmb.data.store, "Store", _FakeStore)
    monkeypatch.setattr(
        pmmb.unified_risk, "build_unified_risk_status",
        lambda *_a, **_k: _snapshot(committed_capital=1000.0),
    )
    monkeypatch.setattr(pmmb.unified_risk, "_global_halt_reason", lambda: None)
    cfg.execution.mode = "paper"
    cfg.perps.enabled = True
    cfg.perps.mode = "paper"

    code = cmd_portfolio_risk(SimpleNamespace(json=True), cfg)
    report = json.loads(capsys.readouterr().out)

    assert code == 3
    assert report["shared_gate_clear"] is False
    assert any("headroom" in item for item in report["blockers"])


def test_portfolio_risk_cli_does_not_claim_strategy_approval(monkeypatch, cfg, capsys):
    import pmmb.data.store
    import pmmb.unified_risk

    monkeypatch.setattr(pmmb.data.store, "Store", _FakeStore)
    monkeypatch.setattr(pmmb.unified_risk, "build_unified_risk_status", lambda *_a, **_k: _snapshot())
    monkeypatch.setattr(pmmb.unified_risk, "_global_halt_reason", lambda: None)
    cfg.execution.mode = "paper"
    cfg.perps.enabled = True
    cfg.perps.mode = "paper"

    code = cmd_portfolio_risk(SimpleNamespace(json=True), cfg)
    report = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "not per-market signal approval" in report["scope"]
