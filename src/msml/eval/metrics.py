"""Metrics for frame-level intrusion detection, including operational false-alarm rates."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score


def alarm_events(ts: np.ndarray, flagged: np.ndarray, merge_s: float = 1.0) -> int:
    """Count alarm events: flagged frames closer than merge_s seconds count as one event."""
    t = ts[flagged.astype(bool)]
    if t.size == 0:
        return 0
    return int(1 + np.count_nonzero(np.diff(t) > merge_s))


def frame_metrics(y: np.ndarray, score: np.ndarray, threshold: float = 0.5) -> dict:
    pred = score >= threshold
    out = {
        "frames": int(y.size),
        "attack_frames": int(y.sum()),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "fpr": float(np.mean(pred[y == 0])) if np.any(y == 0) else float("nan"),
    }
    out["auc_pr"] = float(average_precision_score(y, score)) if 0 < y.sum() < y.size else float("nan")
    return out


def false_alarms_per_hour(captures: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
                          threshold: float = 0.5, merge_s: float = 1.0) -> float:
    """False alarm events per hour over benign frames.

    captures: list of (ts_seconds, y, score). Only benign frames are considered; a false alarm
    event is a cluster of benign frames flagged within merge_s seconds.
    """
    events, seconds = 0, 0.0
    for ts, y, score in captures:
        benign = y == 0
        events += alarm_events(ts[benign], score[benign] >= threshold, merge_s)
        seconds += float(ts[-1] - ts[0]) if ts.size > 1 else 0.0
    return events / (seconds / 3600.0) if seconds > 0 else float("nan")


def attack_episodes(ts: np.ndarray, y: np.ndarray, gap_s: float = 1.0) -> list[tuple[float, float]]:
    """Group attack frames into episodes; a gap longer than gap_s starts a new episode."""
    t = ts[y == 1]
    if t.size == 0:
        return []
    cut = np.flatnonzero(np.diff(t) > gap_s)
    starts = np.r_[t[0], t[cut + 1]]
    ends = np.r_[t[cut], t[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def alarm_metrics(captures: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
                  window_s: float) -> dict:
    """Event-level metrics for alarms.

    captures: list of (ts_seconds, y, alarm). An alarm is true if an attack frame occurred within
    window_s before it (inclusive); otherwise it is a false alarm. An attack episode is detected
    if a true alarm falls inside [start, end + window_s].
    """
    false_alarms, seconds, episodes, detected, latencies = 0, 0.0, 0, 0, []
    for ts, y, alarm in captures:
        seconds += float(ts[-1] - ts[0]) if ts.size > 1 else 0.0
        t_alarm = ts[alarm.astype(bool)]
        t_attack = ts[y == 1]
        if t_attack.size:
            i = np.searchsorted(t_attack, t_alarm, side="right") - 1
            ok = (i >= 0) & (t_alarm - t_attack[np.clip(i, 0, None)] <= window_s)
        else:
            ok = np.zeros(t_alarm.size, dtype=bool)
        false_alarms += int(np.count_nonzero(~ok))
        true_alarms = t_alarm[ok]
        for start, end in attack_episodes(ts, y):
            episodes += 1
            hit = true_alarms[(true_alarms >= start) & (true_alarms <= end + window_s)]
            if hit.size:
                detected += 1
                latencies.append(float(hit[0] - start))
    hours = seconds / 3600.0
    return {
        "episodes": episodes,
        "episode_recall": detected / episodes if episodes else float("nan"),
        "median_latency_ms": float(np.median(latencies) * 1000) if latencies else float("nan"),
        "false_alarms_per_hour": false_alarms / hours if hours > 0 else float("nan"),
    }
