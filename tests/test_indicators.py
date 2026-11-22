import math

from pmmb.signals import indicators as ind


def test_ema_matches_manual():
    vals = [1, 2, 3, 4, 5]
    k = 2 / (3 + 1)
    acc = vals[0]
    for v in vals[1:]:
        acc = v * k + acc * (1 - k)
    assert math.isclose(ind.ema(vals, 3), acc)


def test_ema_of_constant_is_constant():
    assert math.isclose(ind.ema([0.4] * 20, 9), 0.4)


def test_stdev_zero_for_constant():
    assert ind.stdev([0.5] * 10) == 0.0


def test_zscore_positive_for_spike():
    series = [0.5] * 20 + [0.6]
    assert ind.zscore(series, 10) > 1


def test_zscore_zero_when_flat():
    assert ind.zscore([0.5] * 20, 10) == 0.0


def test_breakout_up_and_down():
    up = [0.4] * 21 + [0.5]
    mag, direction = ind.breakout(up, 20)
    assert direction == 1 and mag > 0

    down = [0.6] * 21 + [0.5]
    mag, direction = ind.breakout(down, 20)
    assert direction == -1 and mag > 0


def test_breakout_none_inside_range():
    series = [0.5 + 0.01 * (i % 3 - 1) for i in range(25)]
    mag, direction = ind.breakout(series, 20)
    assert direction == 0 and mag == 0.0


def test_rsi_bounds():
    assert ind.rsi([0.5 + 0.001 * i for i in range(30)], 14) > 70
    assert ind.rsi([0.5 - 0.001 * i for i in range(30)], 14) < 30
    assert 0 <= ind.rsi([0.5] * 30, 14) <= 100


def test_slope_positive():
    assert ind.slope([0.1 * i for i in range(10)], 10) > 0


def test_realized_vol_positive():
    assert ind.realized_vol([0.4, 0.42, 0.39, 0.44, 0.41], 5) > 0
