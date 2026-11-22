"""שער ה-live: כל בדיקה יכולה לחסום, ואף אחת לא משקרת."""
from pmmb.readiness import (FAIL, OK, WARN, Thresholds, Check, collect_facts,
                            evaluate, is_ready, readiness_markdown, summary)


def _facts(cfg, **over):
    f = {
        "cfg": cfg,
        "walkforward": {"oos_pnl": 204.22, "oos_trades": 75, "consistency": 1.0},
        "backtest": {"trades": 139, "fees_paid": 127.09},
        "soak": {"days": 8, "max_gap_min": 5.0, "errors": 0},
        "health": {"healthy": True, "reason": "תקין"},
        "telegram": True,
        "live_keys": True,
        "backup_age_days": 1.0,
    }
    f.update(over)
    return f


def _by_id(checks, cid) -> Check:
    return next(c for c in checks if c.id == cid)


def test_all_good_is_ready(cfg):
    checks = evaluate(_facts(cfg))
    assert is_ready(checks)
    assert all(c.status in (OK, WARN) for c in checks)


def test_fees_not_in_model_blocks(cfg):
    cfg.execution.fee_mode = "off"
    assert _by_id(evaluate(_facts(cfg)), "fees").status == FAIL


def test_backtest_without_fees_blocks(cfg):
    checks = evaluate(_facts(cfg, backtest={"trades": 100, "fees_paid": 0.0}))
    assert _by_id(checks, "fees").status == FAIL


def test_negative_walkforward_blocks(cfg):
    checks = evaluate(_facts(cfg, walkforward={"oos_pnl": -12.0, "oos_trades": 20,
                                               "consistency": 0.33}))
    assert _by_id(checks, "walkforward").status == FAIL


def test_low_consistency_blocks_even_if_profitable(cfg):
    checks = evaluate(_facts(cfg, walkforward={"oos_pnl": 50.0, "oos_trades": 20,
                                               "consistency": 0.66 - 0.01}))
    assert _by_id(checks, "walkforward").status == FAIL


def test_short_soak_blocks(cfg):
    checks = evaluate(_facts(cfg, soak={"days": 2, "max_gap_min": 5.0, "errors": 0}))
    assert _by_id(checks, "soak").status == FAIL
    assert is_ready(checks) is False


def test_too_many_errors_blocks(cfg):
    checks = evaluate(_facts(cfg, soak={"days": 8, "max_gap_min": 5.0, "errors": 40}),
                      Thresholds(max_errors=3))
    assert _by_id(checks, "errors").status == FAIL


def test_gaps_warn_but_do_not_block(cfg):
    checks = evaluate(_facts(cfg, soak={"days": 8, "max_gap_min": 300.0, "errors": 0}))
    assert _by_id(checks, "gaps").status == WARN
    assert is_ready(checks)


def test_reckless_risk_limits_block(cfg):
    cfg.risk.max_daily_loss_pct = 0.5
    cfg.risk.max_drawdown_pct = 0.8
    checks = evaluate(_facts(cfg))
    assert _by_id(checks, "risk_limits").status == FAIL


def test_missing_telegram_is_only_warning(cfg):
    checks = evaluate(_facts(cfg, telegram=False))
    assert _by_id(checks, "telegram").status == WARN
    assert is_ready(checks)


def test_summary_and_markdown(cfg):
    ok = evaluate(_facts(cfg))
    assert "מוכן" in summary(ok)
    assert "לא מוכן" in readiness_markdown(evaluate(_facts(cfg, soak={
        "days": 0, "max_gap_min": 0, "errors": 0})), Thresholds())
    md = readiness_markdown(ok, Thresholds())
    assert md.startswith("# שער המעבר ל-live") and md.count("|") > 6


def test_collect_facts_without_reports(cfg, tmp_path):
    cfg.data.db_path = str(tmp_path / "none.db")
    f = collect_facts(cfg, reports_dir=tmp_path / "r", backups_dir=tmp_path / "b")
    assert f["walkforward"] is None and f["backtest"] is None
    assert f["soak"]["days"] == 0
    checks = evaluate(f)
    assert _by_id(checks, "walkforward").status == FAIL
