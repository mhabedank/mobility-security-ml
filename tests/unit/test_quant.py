import numpy as np
import pytest

from hilbench.ml.quant import (choose_qparams, multiply_by_quantized_multiplier, quantize_multiplier,
                               round_half_away, trunc_div)


def _ref_mbqm(x: int, m: int, shift: int) -> int:
    """Scalar transcription of gemmlowp/TFLite with Python ints."""
    left = max(shift, 0)
    right = max(-shift, 0)
    a = x * (1 << left)
    ab = a * m
    nudge = (1 << 30) if ab >= 0 else 1 - (1 << 30)
    v = ab + nudge
    high = abs(v) // (1 << 31) * (1 if v >= 0 else -1)
    mask = (1 << right) - 1
    rem = high & mask
    thr = (mask >> 1) + (1 if high < 0 else 0)
    return (high >> right) + (1 if rem > thr else 0)


@pytest.mark.parametrize("real,expected", [
    (0.5, (1 << 30, 0)), (1.0, (1 << 30, 1)), (0.25, (1 << 30, -1)), (0.0, (0, 0)),
    (0.75, (1610612736, 0)),
])
def test_quantize_multiplier_known_values(real, expected):
    assert quantize_multiplier(real) == expected


def test_quantize_multiplier_reconstructs():
    rng = np.random.default_rng(0)
    for real in rng.uniform(1e-6, 0.99, 200):
        q, s = quantize_multiplier(float(real))
        assert (1 << 30) <= q < (1 << 31)
        assert abs(q * 2.0 ** (s - 31) - real) / real < 1e-9


def test_mbqm_matches_scalar_reference():
    rng = np.random.default_rng(1)
    xs = rng.integers(-(1 << 24), 1 << 24, 2000)
    ms = rng.integers(1 << 30, (1 << 31) - 1, 2000)
    ss = rng.integers(-20, 2, 2000)
    got = multiply_by_quantized_multiplier(xs, ms, ss)
    want = [_ref_mbqm(int(x), int(m), int(s)) for x, m, s in zip(xs, ms, ss)]
    assert got.tolist() == want


def test_round_half_away_and_trunc_div():
    assert [round_half_away(v) for v in (0.5, 1.5, -0.5, -1.5, 2.4)] == [1, 2, -1, -2, 2]
    assert trunc_div(np.array([7, -7, 7, -7]), np.array([2, 2, -2, -2])).tolist() == [3, -3, -3, 3]


def test_choose_qparams_contains_zero():
    scale, zp = choose_qparams(0.5, 2.0)
    assert -128 <= zp <= 127
    assert abs((-128 - zp) * scale) < 1e-6  # 0.0 maps exactly to an integer
