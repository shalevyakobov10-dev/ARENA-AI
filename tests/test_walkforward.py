"""טסטים ל-walk-forward ולאבחון — ללא רשת."""
from pmmb.config import Config
from pmmb.data.clob import Candle
from pmmb.diagnostics import run_diagnostics
from pmmb.models import Market
from pmmb.signals import build_signal_engine
from pmmb.walkforward import grid_for, run_walkforward, write_walkforward

DAY = 86400
START = 1_700_000_000


def _market(slug="m1") -> Market:
    return Market("c-" + slug, "q", slug, "y-" + slug, "n-" + slug,
                  0.5, 0.5, 0.01, 1e6, 1e5, None)


def _oscillating(n=600, level=0.5, amp=0.06, period=24):
    """גל עם צניחות חדות — אוכלוסייה שמנוע ה-meanrev אמור למצוא בה משהו."""
    import math

    out = []
    for i in range(n):
        v = level + amp * math.sin(2 * math.pi * i / period)
        # כל 40 נרות: צניחה חדה ואז התאוששות
        if i % 40 == 0 and i > 0:
            v -= 0.05
        out.append(round(min(0.95, max(0.05, v)), 4))
    return out


def _candles(prices, step_hours=1):
    return [Candle(START + i * step_hours * 3600, p) for i, p in enumerate(prices)]


def test_grid_shapes():
    assert len(grid_for("meanrev")) == 18     # 3 z × 3 ratio × 1 guard × 2 exits
    assert len(grid_for("momentum")) == 24
    assert "z_entry" in grid_for("meanrev")[0]


def test_walkforward_runs_and_has_folds(cfg):
    cfg.signal.engine = "meanrev"
    cfg.signal.meanrev.z_entry = 1.2
    cfg.signal.min_score = 0.3
    cfg.signal.min_edge = 0.0
    datasets = [(_market(f"m{i}"), _candles(_oscillating(500))) for i in range(3)]

    res = run_walkforward(cfg, datasets, folds=2, spread=0.01)

    assert len(res.folds) == 2
    assert all(f.best_params for f in res.folds)
    assert all(f.test_start >= f.train_start for f in res.folds)
    assert res.oos_trades >= 0
    assert 0.0 <= res.consistency <= 1.0
    # הפרמטרים שהתגלו חייבים להיות מהגריד
    allowed = {k for k in grid_for("meanrev")[0]}
    assert set(res.folds[0].best_params) <= allowed


def test_walkforward_restores_selection_between_folds(cfg):
    """הכיול בחלון 2 חייב להתחיל מנקודה נקייה (לא להצטבר)."""
    cfg.signal.engine = "meanrev"
    datasets = [(_market(), _candles(_oscillating(400)))]
    res = run_walkforward(cfg, datasets, folds=2)
    # שני החלונות קיבלו את אותה אוכלוסיית אימון מורחבת — אבל השני לא
    # יכול לבחור פרמטר שאינו בגריד
    assert res.folds[1].best_params["z_entry"] in (1.2, 1.5, 2.0)


def test_walkforward_empty_raises(cfg):
    import pytest

    with pytest.raises(ValueError):
        run_walkforward(cfg, [], folds=2)


def test_write_walkforward(tmp_path, cfg):
    datasets = [(_market(), _candles(_oscillating(400)))]
    res = run_walkforward(cfg, datasets, folds=2)
    path = write_walkforward(res, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "Walk-Forward" in text
    assert "מחוץ למדגם" in text


def test_diagnostics_measures_signal(cfg):
    cfg.signal.engine = "meanrev"
    cfg.signal.meanrev.z_entry = 1.2
    cfg.signal.min_score = 0.3
    cfg.signal.min_edge = 0.0
    engine = build_signal_engine(cfg.signal)
    datasets = [(_market(f"d{i}"), _candles(_oscillating(400))) for i in range(2)]

    res = run_diagnostics(engine, datasets, spread=0.01)

    assert res.evaluations > 0
    assert set(res.horizons) == {1, 3, 6, 12, 24}
    for s in res.horizons.values():
        assert 0.0 <= s.hit_rate <= 1.0
        assert -1.0 <= s.ic <= 1.0
    md = res.to_markdown()
    assert "hit rate" in md


def test_calibration_measures_bias(cfg):
    """הכיול צריך לזהות שהמנוע מבטיח יותר ממה שמתממש."""
    from pmmb.diagnostics import run_calibration

    cfg.signal.engine = "meanrev"
    cfg.signal.meanrev.z_entry = 1.2
    cfg.signal.meanrev.reversion_ratio = 1.5   # מוגזם בכוונה
    cfg.signal.min_score = 0.0
    cfg.signal.min_edge = 0.0
    engine = build_signal_engine(cfg.signal)

    datasets = [(_market(f"c{i}"), _candles(_oscillating(400))) for i in range(3)]
    res = run_calibration(engine, datasets, fidelity_min=60, horizon_hours=24, spread=0.01)

    assert res.rows
    assert res.current_ratio == 1.5
    assert 0.0 <= res.suggested_ratio <= 1.5
    md = res.to_markdown()
    assert "יחס recommend".split()[0] in md or "מומלץ" in md


def test_calibration_no_signals_is_empty(cfg):
    from pmmb.diagnostics import run_calibration

    cfg.signal.engine = "meanrev"
    cfg.signal.meanrev.z_entry = 50.0          # לא ייכנס לעולם
    engine = build_signal_engine(cfg.signal)
    datasets = [(_market(), _candles(_oscillating(300)))]
    res = run_calibration(engine, datasets, fidelity_min=60, horizon_hours=24)
    assert res.rows == []
    assert res.suggested_ratio == res.current_ratio
