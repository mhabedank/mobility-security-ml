"""Feature extraction / labelling used by the real-data training (no TensorFlow needed)."""
import numpy as np

from hilbench.ml.features import mfcc
from hilbench.ml.train_real import _road_labels, can_features, parse_candump, mimii_windows, roc_auc


def _log(tmp_path):
    lines = []
    for i in range(200):
        lines.append(f"({1000 + i * 0.01:.6f}) can0 0C8#{i % 256:02X}00000000000000")
        lines.append(f"({1000 + i * 0.01 + 0.005:.6f}) can0 1A0#11223344")
    p = tmp_path / "x.log"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_candump_parsing_and_features(tmp_path):
    f = parse_candump(_log(tmp_path))
    assert len(f["t"]) == 400 and set(f["id"].tolist()) == {0xC8, 0x1A0}
    assert f["dlc"].tolist()[:2] == [8, 4]
    x = can_features(f, {0xC8})
    assert x.shape == (400, 32)
    assert np.allclose(x[0, 0:11], [(0xC8 >> b) & 1 for b in range(11)])
    assert x[2, 31] == 1.0 and x[3, 31] == 0.0  # known-ID flag
    assert abs(x[2, 22] - 1 / 64) < 1e-6  # counter byte changed one bit
    assert abs(x[4, 21] - 0.5) < 1e-6  # periodic: same inter-arrival time


def test_road_labels_interval_and_id(tmp_path):
    f = parse_candump(_log(tmp_path))
    y = _road_labels(f, {"injection_interval": [0.5, 1.0], "injection_id": "0x1A0"})
    assert y.sum() == 50 and set(f["id"][y == 1].tolist()) == {0x1A0}
    y = _road_labels(f, {"injection_interval": [0.5, 1.0], "injection_id": "XXX"})  # fuzzing
    assert y.sum() == 101


def test_mfcc_shape():
    x = np.sin(np.linspace(0, 2000 * np.pi, 16000)).astype(np.float32)
    assert mfcc(x).shape == (49, 10)


def test_roc_auc_and_partial_auc():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    assert roc_auc(np.arange(8.0), y) == 1.0
    assert roc_auc(-np.arange(8.0), y) == 0.0
    assert roc_auc(np.ones(8), y) == 0.5  # ties
    assert abs(roc_auc(np.array([0, 1, 2, 5, 3, 4, 6, 7.0]), y) - 14 / 16) < 1e-9
    assert roc_auc(np.arange(8.0), y, max_fpr=0.1) == 1.0


def test_mimii_windows_stack_context():
    lm = np.arange(311 * 40, dtype=np.float32).reshape(311, 40)
    w = mimii_windows(lm)
    assert w.shape == (307, 200)
    assert np.array_equal(w[1], lm[1:6].reshape(-1))
    assert mimii_windows(lm, stride=8).shape == (39, 200)
