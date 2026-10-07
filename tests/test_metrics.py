import numpy as np

from msml.eval.metrics import alarm_metrics, attack_episodes


def test_attack_episodes_split_on_gaps():
    ts = np.array([0.0, 1.0, 1.1, 1.2, 5.0, 5.1, 9.0])
    y = np.array([0, 1, 1, 1, 1, 1, 0])
    assert attack_episodes(ts, y) == [(1.0, 1.2), (5.0, 5.1)]


def test_alarms_during_and_shortly_after_attack_are_true():
    ts = np.arange(0, 3600, 0.5)  # one hour of frames
    y = np.zeros(ts.size, dtype=np.uint8)
    y[(ts >= 100) & (ts <= 110)] = 1
    alarm = np.zeros(ts.size, dtype=np.uint8)
    alarm[ts == 105.0] = 1    # inside the attack
    alarm[ts == 110.5] = 1    # 0.5 s after the attack: still true (grace)
    alarm[ts == 2000.0] = 1   # no attack: false alarm
    m = alarm_metrics([(ts, y, alarm)])
    assert m["episodes"] == 1
    assert m["episode_recall"] == 1.0
    assert m["median_latency_ms"] == 5000.0
    assert abs(m["false_alarms_per_hour"] - 1.0) < 0.01
