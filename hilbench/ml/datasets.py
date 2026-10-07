"""Synthetic mobility-security datasets used to train the reference models.

They are small and deterministic so that the zoo can be rebuilt anywhere.
"""
from __future__ import annotations

import numpy as np

CAN_FEATURES = 32


def can_bus_frames(n_frames: int = 30000, seed: int = 0, attack_ratio: float = 0.25):
    """Simulate a CAN bus with periodic ECUs plus DoS, fuzzing and spoofing.

    Returns (features [n, 32] float32, labels [n] int, attack_type [n] str).
    """
    rng = np.random.default_rng(seed)
    n_ids = 24
    ids = np.sort(rng.choice(np.arange(0x080, 0x700), n_ids, replace=False))
    periods = rng.choice([0.010, 0.020, 0.050, 0.100, 0.200, 0.500], n_ids)
    signal = rng.uniform(0, 255, (n_ids, 8))
    counters = np.zeros(n_ids, dtype=int)

    # Normal schedule.
    events = []
    horizon = n_frames * (1 - attack_ratio) / np.sum(1.0 / periods)
    for i, per in enumerate(periods):
        t = rng.uniform(0, per)
        while t < horizon:
            events.append((t, "normal", i))
            t += per * rng.normal(1.0, 0.02)

    # Attack windows.
    n_attack = int(n_frames * attack_ratio)
    kinds = ["dos", "fuzzing", "spoofing"]
    per_kind = n_attack // len(kinds)
    for kind in kinds:
        t0 = rng.uniform(0.1, 0.8) * horizon
        rate = {"dos": 0.0003, "fuzzing": 0.0010, "spoofing": 0.0}[kind]
        target = int(rng.integers(n_ids))
        for k in range(per_kind):
            if kind == "spoofing":
                t = t0 + k * periods[target] / 3
            else:
                t = t0 + k * rate
            events.append((t, kind, target))
    events.sort(key=lambda e: e[0])

    known = {int(c): j for j, c in enumerate(ids)}
    last_t_id: dict[int, float] = {}
    last_payload: dict[int, np.ndarray] = {}
    recent_t: list[float] = []
    recent_ids: list[int] = []
    prev_t = 0.0
    feats, labels, types = [], [], []
    for t, kind, i in events:
        if kind == "normal":
            cid = int(ids[i])
            counters[i] = (counters[i] + 1) % 256
            signal[i, 2:] = np.clip(signal[i, 2:] + rng.normal(0, 2, 6), 0, 255)
            payload = np.concatenate([[counters[i], (counters[i] * 7 + cid) % 256], signal[i, 2:]])
        elif kind == "dos":
            cid = 0x000
            payload = np.zeros(8)
        elif kind == "fuzzing":
            cid = int(rng.integers(0, 0x800))
            payload = rng.integers(0, 256, 8).astype(float)
        else:  # spoofing: valid ID, frozen attacker payload
            cid = int(ids[i])
            payload = np.array([counters[i], 0x00, 0xFF, 0xFF, 0x00, 0x7F, 0x00, 0xFF], dtype=float)

        f = np.zeros(CAN_FEATURES, dtype=np.float32)
        f[0:11] = [(cid >> b) & 1 for b in range(11)]
        f[11] = 1.0
        f[12:20] = payload / 255.0
        dt_id = t - last_t_id.get(cid, t - 1.0)
        f[20] = np.clip((np.log10(dt_id + 1e-4) + 4) / 4, 0, 1.5)
        j = known.get(cid)
        f[21] = np.clip(dt_id / periods[j], 0, 4) / 4 if j is not None else 0.0
        f[22] = 1.0 if j is not None else 0.0
        prev = last_payload.get(cid)
        if prev is not None:
            hd = np.unpackbits(np.bitwise_xor(prev.astype(np.uint8), payload.astype(np.uint8))).sum()
            f[23] = hd / 64.0
            f[24] = 1.0 if (int(payload[0]) - int(prev[0])) % 256 == 1 else 0.0
            f[28:32] = np.abs(payload[2:6] - prev[2:6]) / 255.0
        while recent_t and recent_t[0] < t - 0.010:
            recent_t.pop(0)
            recent_ids.pop(0)
        f[25] = min(len(recent_t) / 20.0, 2.0)
        f[26] = np.clip((np.log10(t - prev_t + 1e-5) + 5) / 5, 0, 1.5)
        f[27] = recent_ids.count(cid) / max(len(recent_ids), 1)
        recent_t.append(t)
        recent_ids.append(cid)
        last_t_id[cid] = t
        last_payload[cid] = payload
        prev_t = t
        feats.append(f)
        labels.append(0 if kind == "normal" else 1)
        types.append(kind)
    return np.array(feats), np.array(labels), np.array(types)


def sensor_windows(n: int = 4000, length: int = 64, seed: int = 1, anomaly_ratio: float = 0.0):
    """Wheel-speed-like sensor windows (normalised). Anomalies: spikes, stuck-at, drift."""
    rng = np.random.default_rng(seed)
    t = np.arange(length) / length
    base = rng.uniform(0.2, 0.8, (n, 1))
    f1 = rng.uniform(0.5, 3.0, (n, 1))
    a1 = rng.uniform(0.05, 0.2, (n, 1))
    ph = rng.uniform(0, 2 * np.pi, (n, 1))
    x = base + a1 * np.sin(2 * np.pi * f1 * t + ph) + rng.normal(0, 0.01, (n, length))
    labels = np.zeros(n, dtype=int)
    n_anom = int(n * anomaly_ratio)
    for k in rng.choice(n, n_anom, replace=False):
        kind = k % 3
        if kind == 0:
            x[k, rng.integers(length)] += rng.choice([-1, 1]) * rng.uniform(0.4, 0.8)
        elif kind == 1:
            s = rng.integers(length // 2)
            x[k, s:] = x[k, s]
        else:
            x[k] += np.linspace(0, rng.uniform(0.3, 0.6), length)
        labels[k] = 1
    return np.clip(x, 0, 1.5).astype(np.float32), labels


def imu_gnss_windows(n: int = 512, length: int = 64, channels: int = 6, seed: int = 2):
    """IMU (acc xyz) + GNSS (speed, heading rate, hdop) windows for spoof detection."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, length)
    x = rng.normal(0, 0.3, (n, length, channels))
    x[:, :, 3] += np.cumsum(rng.normal(0, 0.05, (n, length)), axis=1)
    x[:, :, 4] += np.sin(2 * np.pi * rng.uniform(0.2, 2, (n, 1)) * t)
    return x.reshape(n, 1, length, channels).astype(np.float32)
