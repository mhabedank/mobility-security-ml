"""Fixed-point helpers with TFLite (gemmlowp, double rounding) semantics.

Everything here is mirrored 1:1 in firmware/lib/microinfer/src/microinfer.c.
"""
from __future__ import annotations

import math

import numpy as np

INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1


def round_half_away(x: float) -> int:
    """std::round semantics (Python's round() is banker's rounding)."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def quantize_multiplier(real: float) -> tuple[int, int]:
    """Split a positive real multiplier into (int32 q31 multiplier, shift).

    Same algorithm as tflite::QuantizeMultiplier.
    """
    if real < 0:
        raise ValueError("multiplier must be non-negative")
    if real == 0.0:
        return 0, 0
    q, shift = math.frexp(real)
    q_fixed = round_half_away(q * (1 << 31))
    if q_fixed == (1 << 31):
        q_fixed //= 2
        shift += 1
    if shift < -31:
        shift, q_fixed = 0, 0
    if shift > 30:
        raise ValueError(f"multiplier {real} too large")
    return q_fixed, shift


def _wrap_int32(x: np.ndarray) -> np.ndarray:
    return ((x + (1 << 31)) & 0xFFFFFFFF) - (1 << 31)


def multiply_by_quantized_multiplier(x, mult, shift) -> np.ndarray:
    """Vectorised tflite::MultiplyByQuantizedMultiplier (int64 math)."""
    x = np.asarray(x, dtype=np.int64)
    mult = np.asarray(mult, dtype=np.int64)
    shift = np.asarray(shift, dtype=np.int64)
    left = np.maximum(shift, 0)
    right = np.maximum(-shift, 0)

    a = _wrap_int32(np.left_shift(x, left))
    ab = a * mult
    nudge = np.where(ab >= 0, 1 << 30, 1 - (1 << 30))
    v = ab + nudge
    # Truncating division by 2^31 (toward zero), like C integer division.
    high = np.where(v >= 0, v >> 31, -((-v) >> 31))
    sat = (a == INT32_MIN) & (mult == INT32_MIN)
    high = np.where(sat, INT32_MAX, high)

    mask = np.left_shift(np.int64(1), right) - 1
    remainder = high & mask
    threshold = (mask >> 1) + (high < 0).astype(np.int64)
    return (high >> right) + (remainder > threshold).astype(np.int64)


def trunc_div(a: np.ndarray, b) -> np.ndarray:
    """C-style integer division (truncate toward zero)."""
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    q = np.abs(a) // np.abs(b)
    return np.where((a < 0) ^ (b < 0), -q, q)


def choose_qparams(vmin: float, vmax: float) -> tuple[float, int]:
    """Asymmetric int8 quantization parameters covering [vmin, vmax] and 0."""
    vmin = min(float(vmin), 0.0)
    vmax = max(float(vmax), 0.0)
    if vmax - vmin < 1e-8:
        vmax = vmin + 1e-8
    scale = (vmax - vmin) / 255.0
    zp = round_half_away(-128 - vmin / scale)
    zp = int(np.clip(zp, -128, 127))
    return scale, zp


def quantize(x: np.ndarray, scale: float, zp: int) -> np.ndarray:
    q = np.floor(np.asarray(x, dtype=np.float64) / scale + 0.5) + zp
    return np.clip(q, -128, 127).astype(np.int8)


def dequantize(q: np.ndarray, scale: float, zp: int) -> np.ndarray:
    return (np.asarray(q, dtype=np.float64) - zp) * scale


def crc32_update(crc: int, data: bytes) -> int:
    import zlib

    return zlib.crc32(data, crc) & 0xFFFFFFFF
