import numpy as np
import pandas as pd
import pytest

from msml.can.features import FEATURE_NAMES, extract

F = {name: i for i, name in enumerate(FEATURE_NAMES)}


def frames(rows):
    """rows: (t_seconds, can_id, payload_bytes)."""
    recs = []
    for t, cid, payload in rows:
        data = list(payload) + [0] * (8 - len(payload))
        recs.append({"ts": t, "can_id": cid, "dlc": len(payload),
                     **{f"b{i}": data[i] for i in range(8)}})
    return pd.DataFrame(recs)


def test_first_frame_uses_caps():
    x = extract(frames([(100.0, 0x123, [1, 2])]))[0]
    assert x[F["dt_id_ms"]] == 1000.0
    assert x[F["dt_ratio"]] == 1.0
    assert x[F["dt_bus_ms"]] == 1000.0
    assert x[F["id_count"]] == 0
    assert x[F["hamming"]] == 0
    assert x[F["dlc"]] == 2
    assert x[F["can_id"]] == 0x123


def test_periodic_id_and_injection():
    # ID 0x10 every 10 ms, then an injected frame 2 ms after the last legitimate one.
    rows = [(i * 0.010, 0x10, [0x00]) for i in range(10)]
    rows.append((0.092, 0x10, [0xFF]))
    x = extract(frames(rows))
    assert x[5, F["dt_id_ms"]] == pytest.approx(10.0, abs=1e-3)
    assert x[5, F["dt_ratio"]] == pytest.approx(1.0, abs=1e-3)
    inj = x[-1]
    assert inj[F["dt_id_ms"]] == pytest.approx(2.0, abs=1e-3)
    assert inj[F["dt_ratio"]] == pytest.approx(0.2, abs=1e-3)
    assert inj[F["hamming"]] == 8
    assert inj[F["bytes_changed"]] == 1
    assert inj[F["id_count"]] == 10


def test_dlc_change_and_bus_timing():
    x = extract(frames([(0.0, 0x1, [1, 2, 3]), (0.0005, 0x2, [0]), (0.001, 0x1, [1, 2])]))
    assert x[1, F["dt_bus_ms"]] == pytest.approx(0.5, abs=1e-3)
    assert x[2, F["dlc_changed"]] == 1
    assert x[2, F["bytes_changed"]] == 1  # byte 2: 3 -> 0 (zero padding)
    assert x[2, F["warmup"]] == 2


def test_new_id_rate_rises_with_unseen_ids():
    rows = [(i * 0.001, 0x100, [0]) for i in range(200)]
    rows += [(0.2 + i * 0.001, 0x200 + i, [0]) for i in range(50)]
    x = extract(frames(rows))
    assert x[199, F["new_id_rate"]] < 0.05
    assert x[-1, F["new_id_rate"]] > 0.5


def test_state_is_independent_per_call():
    df = frames([(0.0, 0x5, [1]), (0.01, 0x5, [2])])
    np.testing.assert_array_equal(extract(df), extract(df))


def test_eviction_keeps_frequent_ids():
    # A periodic ID is seen 50 times, then an ID scan sends 300 one-off IDs (more than the
    # 255 slots). The periodic ID must keep its history; early one-off IDs are evicted.
    rows = [(i * 0.010, 0x7FF, [0]) for i in range(50)]
    rows += [(0.5 + i * 0.0001, i, [0]) for i in range(300)]
    rows += [(0.6, 0x7FF, [0]), (0.601, 0, [0])]
    x = extract(frames(rows))
    assert x[-2, F["id_count"]] == 50     # periodic ID survived the scan
    assert x[-1, F["id_count"]] == 0      # one-off ID 0 was evicted
    assert x[-1, F["dt_id_ms"]] == 1000.0


def test_alarm_needs_k_flags_in_window_and_holds_off():
    from msml.can.features import alarms

    ts = np.array([0, 10_000, 20_000, 500_000, 510_000, 520_000, 530_000, 2_000_000,
                   2_001_000, 2_002_000], dtype=np.int64)
    fl = np.array([1, 0, 1, 1, 1, 1, 1, 1, 1, 1])
    a = alarms(ts, fl, k=3, window_ms=50, holdoff_ms=1000)
    # first alarm at 520 ms (3 flags within 50 ms), suppressed at 530 ms (hold-off),
    # next alarm at 2002 ms
    assert a.tolist() == [0, 0, 0, 0, 0, 1, 0, 0, 0, 1]
