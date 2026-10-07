"""Train the bench models on real, openly licensed datasets.

    pip install -e ".[train]"
    hilbench data download road
    python -m hilbench.ml.train_real can [--epochs 20] [--version 0.2.0]

Pipeline per task: features -> Keras model -> full-integer int8 TFLite ->
hilbench.ml.tflite_import (bit-exact with the TFLite reference kernels) ->
evaluation of the *device arithmetic* on the held-out test split.

Outputs
  models/zoo/<name>.npz           quantized model (parameters only, no data)
  models/zoo/<name>.tflite        int8 TFLite flatbuffer (for Hugging Face / other runtimes)
  models/zoo/<name>.report.json   metrics, dataset provenance, license
  $HILBENCH_DATA/derived/<name>.eval.npz   held-out features for HIL accuracy tests
Training data is never written into the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import zlib
from dataclasses import dataclass, field

import numpy as np

from ..config import REPO_ROOT
from ..data.download import data_root, dataset_dir
from ..data.registry import SOURCES

ZOO_DIR = REPO_ROOT / "models" / "zoo"
ARTIFACTS = ZOO_DIR


@dataclass
class Task:
    name: str
    model: object  # keras.Model (float, may end with softmax)
    x_train: np.ndarray
    y_train: np.ndarray
    x_val: np.ndarray
    y_val: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    datasets: list[str]
    description: str
    labels: list[str] = field(default_factory=list)
    metric: str = "accuracy"
    fit_kwargs: dict = field(default_factory=dict)
    preprocess: dict = field(default_factory=dict)  # host-side feature normalisation
    kind: str = "classification"  # or "anomaly" (autoencoder, score = reconstruction MSE)
    # anomaly tasks: clip id per test window (scores are averaged per clip) and named
    # subsets of the test windows (e.g. per machine) that get their own AUC
    test_groups: np.ndarray | None = None
    test_subsets: dict = field(default_factory=dict)


def _tf():
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf

    return tf


# --------------------------------------------------------------- export --

def to_int8_tflite(model, rep: np.ndarray) -> bytes:
    tf = _tf()

    def gen():
        for i in range(min(len(rep), 500)):
            yield [rep[i:i + 1].astype(np.float32)]

    conv = tf.lite.TFLiteConverter.from_keras_model(model)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = gen
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.int8
    conv.inference_output_type = tf.int8
    return conv.convert()


def export(task: Task, version: str, seed: int = 0) -> dict:
    from .quant import quantize
    from .reference import run_batch
    from .tflite_import import load_tflite, verify_with_interpreter

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tfl_path = ARTIFACTS / f"{task.name}.tflite"
    tfl_path.write_bytes(to_int8_tflite(task.model, task.x_train))

    qm = load_tflite(str(tfl_path), task.name, task.description, seed=seed)
    mismatches = verify_with_interpreter(str(tfl_path), qm, n=32)

    xq = quantize(task.x_test.reshape(len(task.x_test), -1), qm.input_scale, qm.input_zp)
    out = run_batch(qm, xq)
    extra_meta: dict = {}
    targets = None
    if task.kind == "anomaly":
        metrics, extra_meta = _anomaly_metrics(task, qm, out)
        targets = task.x_test.reshape(len(task.x_test), -1).astype(np.float32)
    else:
        metrics = _classification_metrics(task, out)
    metrics["tflite_interpreter_mismatches"] = int(mismatches)
    provenance = [{
        "id": SOURCES[d].id, "title": SOURCES[d].title, "license": SOURCES[d].license,
        "attribution": SOURCES[d].attribution, "citation": SOURCES[d].citation,
        "homepage": SOURCES[d].homepage,
        "retrieved": json.loads((dataset_dir(d) / "SOURCE.json").read_text()).get("retrieved_at")
        if (dataset_dir(d) / "SOURCE.json").exists() else None,
    } for d in task.datasets]
    qm.meta.update(task=task.kind, classes=task.labels, version=version, datasets=provenance,
                   preprocess=task.preprocess,
                   trained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **metrics, **extra_meta)
    qm.save(ZOO_DIR / f"{task.name}.npz")

    derived = data_root() / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    keep = np.random.default_rng(seed).permutation(len(xq))[:1024]
    ev = {"inputs": xq[keep], "labels": task.y_test[keep].astype(np.int32)}
    if targets is not None:
        ev["targets"] = targets[keep]
    np.savez_compressed(derived / f"{task.name}.eval.npz", **ev)

    report = {"name": task.name, "version": version, "description": task.description, "labels": task.labels,
              "summary": qm.summary(), **metrics, "datasets": provenance}
    (ARTIFACTS / f"{task.name}.report.json").write_text(json.dumps(report, indent=2) + "\n")
    _update_manifest(qm, version)
    return report


def _classification_metrics(task: Task, out: np.ndarray) -> dict:
    pred_float = task.model.predict(task.x_test, verbose=0).argmax(-1)
    metrics = {
        "float_accuracy": float((pred_float == task.y_test).mean()),
        "int8_accuracy": float((out.argmax(1) == task.y_test).mean()),
        "test_samples": int(len(task.y_test)),
    }
    if len(task.labels) == 2:  # detection tasks: report recall/precision of the positive class
        pred = out.argmax(1)
        tp = int(((pred == 1) & (task.y_test == 1)).sum())
        fp = int(((pred == 1) & (task.y_test == 0)).sum())
        fn = int(((pred == 0) & (task.y_test == 1)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        metrics.update(int8_precision=prec, int8_recall=rec,
                       int8_f1=2 * prec * rec / max(prec + rec, 1e-9),
                       int8_false_positive_rate=fp / max(int((task.y_test == 0).sum()), 1))
    return metrics


def roc_auc(scores: np.ndarray, labels: np.ndarray, max_fpr: float = 1.0) -> float:
    """Area under the ROC curve (labels 1 = anomaly); with max_fpr < 1 the partial
    AUC normalised to [0, 1] as in DCASE (pAUC)."""
    order = np.argsort(-scores, kind="mergesort")
    s, y = scores[order], labels[order].astype(bool)
    distinct = np.r_[np.nonzero(np.diff(s))[0], len(s) - 1]
    tpr = np.r_[0.0, np.cumsum(y)[distinct] / max(y.sum(), 1)]
    fpr = np.r_[0.0, np.cumsum(~y)[distinct] / max((~y).sum(), 1)]
    if max_fpr < 1.0:
        stop = np.searchsorted(fpr, max_fpr, side="right")
        tpr = np.r_[tpr[:stop], np.interp(max_fpr, fpr, tpr)]
        fpr = np.r_[fpr[:stop], max_fpr]
    return float(np.sum(np.diff(fpr) * (tpr[1:] + tpr[:-1]) / 2) / max_fpr)


def _anomaly_metrics(task: Task, qm, out: np.ndarray) -> tuple[dict, dict]:
    """Scores = mean squared reconstruction error per window, averaged per clip.
    Thresholds come from the *validation* normals, never from the test set."""
    from .quant import dequantize, quantize
    from .reference import run_batch

    def errors(x, o):
        rec = dequantize(o, qm.output_scale, qm.output_zp)
        return ((rec - x.reshape(len(x), -1)) ** 2).mean(1)

    xv = task.x_val
    err_val = errors(xv, run_batch(qm, quantize(xv.reshape(len(xv), -1), qm.input_scale, qm.input_zp)))
    err = errors(task.x_test, out)
    err_float = ((task.model.predict(task.x_test, verbose=0).reshape(len(err), -1)
                  - task.x_test.reshape(len(err), -1)) ** 2).mean(1)
    groups = task.test_groups if task.test_groups is not None else np.arange(len(err))
    uniq, inv = np.unique(groups, return_inverse=True)
    clip = lambda e: np.bincount(inv, e) / np.bincount(inv)  # noqa: E731
    clip_y = np.zeros(len(uniq), np.int64)
    clip_y[inv] = task.y_test
    window_thr = float(np.percentile(err_val, 95))
    metrics = {
        "float_auc": roc_auc(clip(err_float), clip_y),
        "int8_auc": roc_auc(clip(err), clip_y),
        "int8_pauc": roc_auc(clip(err), clip_y, max_fpr=0.1),
        "int8_window_auc": roc_auc(err, task.y_test),
        "int8_window_detection_rate": float((err[task.y_test == 1] > window_thr).mean()),
        "int8_window_false_positive_rate": float((err[task.y_test == 0] > window_thr).mean()),
        "test_clips": int(len(uniq)),
        "test_samples": int(len(err)),
    }
    for name, mask in task.test_subsets.items():
        g = np.unique(inv[mask])
        metrics[f"int8_auc_{name}"] = roc_auc(clip(err)[g], clip_y[g])
    # per-window threshold (95th percentile of validation normals), used by the HIL test
    return metrics, {"threshold": window_thr}


def _update_manifest(qm, version: str) -> None:
    mf_path = ZOO_DIR / "manifest.json"
    mf = json.loads(mf_path.read_text())
    entry = {**qm.summary(), "version": version, "source": "real-data"}
    mf["models"] = [m for m in mf["models"] if m["name"] != qm.name] + [entry]
    mf_path.write_text(json.dumps(mf, indent=2) + "\n")


def fit(task: Task, epochs: int) -> None:
    tf = _tf()
    m = task.model
    lr = tf.keras.optimizers.schedules.CosineDecay(
        2e-3, decay_steps=max(1, epochs * int(np.ceil(len(task.x_train) / 128))))
    if task.kind == "anomaly":  # autoencoder on normal data only
        m.compile(optimizer=tf.keras.optimizers.Adam(lr), loss="mse")
        m.fit(task.x_train, task.x_train, validation_data=(task.x_val, task.x_val), epochs=epochs,
              batch_size=128, verbose=2, **task.fit_kwargs)
        return
    m.compile(optimizer=tf.keras.optimizers.Adam(lr), loss="sparse_categorical_crossentropy",
              metrics=["accuracy"])
    m.fit(task.x_train, task.y_train, validation_data=(task.x_val, task.y_val), epochs=epochs,
          batch_size=128, verbose=2, **task.fit_kwargs)


# ------------------------------------------------------------------ HAR --

HAR_LABELS = ["walking", "walking_upstairs", "walking_downstairs", "sitting", "standing", "laying"]
HAR_SIGNALS = ["body_acc_x", "body_acc_y", "body_acc_z", "body_gyro_x", "body_gyro_y", "body_gyro_z",
               "total_acc_x", "total_acc_y", "total_acc_z"]


def load_har():
    root = dataset_dir("uci-har") / "extracted"
    hits = sorted(root.rglob("train/Inertial Signals"))
    if not hits:
        raise SystemExit("uci-har not downloaded: hilbench data download uci-har")
    base = hits[0].parent.parent

    def split(name):
        x = np.stack([np.loadtxt(base / name / "Inertial Signals" / f"{sig}_{name}.txt", dtype=np.float32)
                      for sig in HAR_SIGNALS], axis=-1)  # (n, 128, 9)
        y = np.loadtxt(base / name / f"y_{name}.txt", dtype=np.int64) - 1
        return x, y

    return split("train"), split("test")


def har_model():
    tf = _tf()
    L = tf.keras.layers
    x = inp = L.Input((1, 128, 9))
    for filters, k in ((16, 5), (32, 5)):
        x = L.Conv2D(filters, (1, k), padding="same", use_bias=False)(x)
        x = L.BatchNormalization()(x)
        x = L.ReLU()(x)
        x = L.MaxPooling2D((1, 2))(x)
    x = L.Conv2D(32, (1, 3), padding="same", use_bias=False)(x)
    x = L.BatchNormalization()(x)
    x = L.ReLU()(x)
    x = L.AveragePooling2D((1, 32))(x)
    x = L.Flatten()(x)
    x = L.Dropout(0.3)(x)
    x = L.Dense(len(HAR_LABELS))(x)
    x = L.Softmax()(x)
    return tf.keras.Model(inp, x)


def task_har(seed: int) -> Task:
    (xtr, ytr), (xte, yte) = load_har()
    mean = xtr.reshape(-1, 9).mean(0)
    std = xtr.reshape(-1, 9).std(0) + 1e-6
    norm = lambda a: ((a - mean) / std)[:, None, :, :].astype(np.float32)  # noqa: E731
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(ytr))
    n_val = len(ytr) // 7
    val, tr = perm[:n_val], perm[n_val:]
    task = Task(
        name="har_cnn1d", model=har_model(),
        x_train=norm(xtr[tr]), y_train=ytr[tr], x_val=norm(xtr[val]), y_val=ytr[val],
        x_test=norm(xte), y_test=yte, datasets=["uci-har"], labels=HAR_LABELS,
        description="Human activity recognition 1D-CNN over 2.56 s of accelerometer + gyroscope "
                    "(9 x 128 @50 Hz), trained on UCI HAR")
    task.preprocess = {"channels": HAR_SIGNALS, "mean": mean.tolist(), "std": std.tolist()}
    return task


# ------------------------------------------------------------------ CAN --

CAN_LINE = None  # compiled lazily


def parse_candump(path) -> dict:
    """candump log "(ts) iface ID#DATA" -> arrays t, can_id, dlc, data[n, 8]."""
    import re

    global CAN_LINE
    if CAN_LINE is None:
        CAN_LINE = re.compile(rb"\(\s*([0-9.]+)\)\s+\S+\s+([0-9A-Fa-f]{1,8})#([0-9A-Fa-f]*)")
    ts, ids, dlc, data = [], [], [], []
    with open(path, "rb") as fh:
        for m in CAN_LINE.finditer(fh.read()):
            payload = bytes.fromhex(m.group(3).decode()[:16])
            ts.append(float(m.group(1)))
            ids.append(int(m.group(2), 16))
            dlc.append(len(payload))
            data.append(payload.ljust(8, b"\0"))
    return {"t": np.array(ts), "id": np.array(ids, dtype=np.int64), "dlc": np.array(dlc, dtype=np.int64),
            "data": np.frombuffer(b"".join(data), dtype=np.uint8).reshape(-1, 8)}


CAN_FEATURES = 32


def can_features(f: dict, known_ids: set) -> np.ndarray:
    """Per-frame features a CAN gateway can compute with O(#IDs) state:
    11 ID bits, DLC, 8 payload bytes, log inter-arrival time of this ID, ratio to
    the previous inter-arrival time, payload Hamming distance and per-byte deltas
    to the previous frame of the same ID, known-ID flag."""
    n = len(f["t"])
    order = np.lexsort((f["t"], f["id"]))  # group by ID, then time
    same = np.zeros(n, bool)
    same[1:] = f["id"][order][1:] == f["id"][order][:-1]
    prev = np.where(same, np.roll(order, 1), -1)  # previous frame of the same ID (sorted space)
    prev_idx = np.full(n, -1)
    prev_idx[order] = prev
    has = prev_idx >= 0
    p = np.where(has, prev_idx, 0)
    dt = np.where(has, f["t"] - f["t"][p], 1.0)
    pp = np.where(has, prev_idx[p], -1)
    dt_prev = np.where(pp >= 0, f["t"][p] - f["t"][np.maximum(pp, 0)], dt)
    d = f["data"].astype(np.int64)
    dprev = np.where(has[:, None], d[p], d)
    x = np.zeros((n, CAN_FEATURES), np.float32)
    x[:, 0:11] = (f["id"][:, None] >> np.arange(11)) & 1
    x[:, 11] = f["dlc"] / 8.0
    x[:, 12:20] = d / 255.0
    x[:, 20] = np.clip((np.log10(np.maximum(dt, 1e-6)) + 6) / 6, 0, 1.5)
    x[:, 21] = np.clip(np.log2(np.maximum(dt, 1e-6) / np.maximum(dt_prev, 1e-6)) / 8 + 0.5, 0, 1)
    x[:, 22] = np.unpackbits((d ^ dprev).astype(np.uint8), axis=1).sum(1) / 64.0
    x[:, 23:31] = np.abs(d - dprev) / 255.0
    x[:, 31] = np.isin(f["id"], list(known_ids)).astype(np.float32)
    return x


def _road_root():
    root = dataset_dir("road") / "extracted"
    hits = [p for p in root.rglob("attacks") if p.is_dir() and (p / "capture_metadata.json").exists()]
    if not hits:
        raise SystemExit("road not downloaded: hilbench data download road")
    return hits[0].parent


def _road_labels(f: dict, meta: dict) -> np.ndarray:
    """Frames inside the injection interval that carry the injected ID (or any
    ID for fuzzing) are attacks."""
    y = np.zeros(len(f["t"]), np.int64)
    interval = meta.get("injection_interval") or meta.get("injection_time") or meta.get("interval")
    if not interval:
        return y
    t0 = f["t"][0] if len(f["t"]) else 0.0
    start, end = float(interval[0]), float(interval[1])
    rel = f["t"] - t0 if start < 1e6 else f["t"]  # relative or absolute timestamps
    inside = (rel >= start) & (rel <= end)
    inj = meta.get("injection_id")
    if inj in (None, "", "XXX", "random"):
        y[inside] = 1
    else:
        ids = inj if isinstance(inj, list) else [inj]
        ids = [int(str(i), 16) if isinstance(i, str) else int(i) for i in ids]
        y[inside & np.isin(f["id"], ids)] = 1
    return y


def load_can(seed: int = 0):
    root = _road_root()
    ameta = json.loads((root / "attacks" / "capture_metadata.json").read_text())
    print("road attack metadata keys:", list(ameta)[:5], "->", json.dumps(ameta[next(iter(ameta))])[:300],
          flush=True)
    ambient = sorted((root / "ambient").glob("*.log"))
    ambient = [p for p in ambient if p.stat().st_size < 120e6]  # keep CI time/RAM bounded
    known = set()
    amb = []
    for p in ambient:
        f = parse_candump(p)
        known |= set(np.unique(f["id"]).tolist())
        amb.append((p.name, f))
    rng = np.random.default_rng(seed)
    parts = {"train": [], "test": []}
    for name, f in amb:  # ambient: hold out every 4th capture
        split = "test" if zlib.crc32(name.encode()) % 4 == 0 else "train"  # deterministic
        keep = rng.random(len(f["t"])) < 0.15  # subsample long benign captures
        parts[split].append((can_features(f, known)[keep], np.zeros(keep.sum(), np.int64)))
    for p in sorted((root / "attacks").glob("*.log")):
        key = p.stem
        meta = ameta.get(key) or ameta.get(p.name) or {}
        f = parse_candump(p)
        y = _road_labels(f, meta)
        split = "test" if key.removesuffix("_masquerade").endswith("_2") else "train"
        parts[split].append((can_features(f, known), y))
        print(f"road {key}: {len(y)} frames, {y.sum()} attack, {split}", flush=True)
    out = {}
    for split, items in parts.items():
        x = np.concatenate([a for a, _ in items])
        y = np.concatenate([b for _, b in items])
        perm = rng.permutation(len(y))
        out[split] = (x[perm], y[perm])
        print(f"can {split}: {len(y)} frames, {y.mean() * 100:.2f}% attack", flush=True)
    return out


def can_model():
    tf = _tf()
    L = tf.keras.layers
    x = inp = L.Input((CAN_FEATURES,))
    x = L.Dense(64, activation="relu")(x)
    x = L.Dense(32, activation="relu")(x)
    x = L.Dense(2)(x)
    x = L.Softmax()(x)
    return tf.keras.Model(inp, x)


def task_can(seed: int) -> Task:
    d = load_can(seed)
    xtr, ytr = d["train"]
    n_val = len(ytr) // 10
    pos = max(ytr.mean(), 1e-4)
    return Task(
        name="can_ids_road", model=can_model(),
        x_train=xtr[n_val:], y_train=ytr[n_val:], x_val=xtr[:n_val], y_val=ytr[:n_val],
        x_test=d["test"][0], y_test=d["test"][1], datasets=["road"], labels=["normal", "attack"],
        description="CAN bus intrusion detection MLP (32-64-32-2) on per-frame features, trained on the "
                    "ROAD dataset (real vehicle; fuzzing, fabrication, masquerade attacks)",
        fit_kwargs={"class_weight": {0: 1.0, 1: float(min(0.5 / pos, 50.0))}})


# ---------------------------------------------------------------- MIMII --

MIMII_MELS = 40
MIMII_FRAMES = 5  # context of 5 x 64 ms -> 200 inputs
MIMII_FFT = 1024  # 64 ms @16 kHz
MIMII_HOP = 512


def _mimii_logmel(path: str) -> np.ndarray:
    from .features import SR, log_mel, read_wav

    # channel 0 only: a deployed sensor has a single microphone
    x = read_wav(path, length=10 * SR, channel=0)
    return log_mel(x, n_mels=MIMII_MELS, win=MIMII_FFT, hop=MIMII_HOP, nfft=MIMII_FFT, fmax=SR / 2)


def mimii_windows(lm: np.ndarray, stride: int = 1) -> np.ndarray:
    """(frames, mels) log-mel -> (n, MIMII_FRAMES * mels) stacked context windows."""
    n = (len(lm) - MIMII_FRAMES) // stride + 1
    idx = np.arange(MIMII_FRAMES)[None, :] + stride * np.arange(n)[:, None]
    return lm[idx].reshape(n, -1)


def load_mimii(seed: int = 0, workers: int = 4):
    """Clips per machine id; per id as many normal clips as abnormal ones are held out
    for testing (DCASE protocol), the rest of the normals train the autoencoder."""
    from multiprocessing import Pool

    root = dataset_dir("mimii") / "extracted"
    clips = sorted(root.rglob("*.wav"))
    if not clips:
        raise SystemExit("mimii not downloaded: hilbench data download mimii")
    rng = np.random.default_rng(seed)
    by_id: dict[str, dict[str, list[str]]] = {}
    for c in clips:
        by_id.setdefault(c.parent.parent.name, {}).setdefault(c.parent.name, []).append(str(c))
    train, test = [], []  # (path, label, machine)
    for mid, d in sorted(by_id.items()):
        normal = [d["normal"][i] for i in rng.permutation(len(d.get("normal", [])))]
        abnormal = d.get("abnormal", [])
        n_hold = min(len(abnormal), len(normal) // 2)
        test += [(c, 0, mid) for c in normal[:n_hold]] + [(c, 1, mid) for c in abnormal]
        train += [(c, 0, mid) for c in normal[n_hold:]]
        print(f"mimii {mid}: {len(normal) - n_hold} train normal, {n_hold} test normal, "
              f"{len(abnormal)} test abnormal", flush=True)
    with Pool(workers) as pool:
        lm_train = pool.map(_mimii_logmel, [c for c, _, _ in train], chunksize=8)
        lm_test = pool.map(_mimii_logmel, [c for c, _, _ in test], chunksize=8)
    return train, lm_train, test, lm_test


def mimii_model(n_in: int = MIMII_MELS * MIMII_FRAMES, hidden: int = 64, code: int = 8):
    tf = _tf()
    L = tf.keras.layers
    x = inp = L.Input((n_in,))
    for units in (hidden, hidden):
        x = L.Dense(units, activation="relu")(x)
    x = L.Dense(code)(x)  # linear bottleneck
    for units in (hidden, hidden):
        x = L.Dense(units, activation="relu")(x)
    x = L.Dense(n_in)(x)
    return tf.keras.Model(inp, x)


def task_mimii(seed: int) -> Task:
    train, lm_train, test, lm_test = load_mimii(seed)
    stacked = np.concatenate(lm_train)
    mean, std = stacked.mean(0), stacked.std(0) + 1e-6
    norm = lambda w: ((w.reshape(len(w), MIMII_FRAMES, MIMII_MELS) - mean) / std  # noqa: E731
                      ).reshape(len(w), -1).astype(np.float32)
    rng = np.random.default_rng(seed)
    # validation = whole clips, so the threshold is not tuned on frames of training clips
    order = rng.permutation(len(train))
    n_val = max(1, len(train) // 10)
    xs = {k: norm(np.concatenate([mimii_windows(lm_train[i], stride=4) for i in idx]))
          for k, idx in (("val", order[:n_val]), ("train", order[n_val:]))}
    xs["train"] = xs["train"][rng.permutation(len(xs["train"]))]
    wins = [mimii_windows(lm, stride=8) for lm in lm_test]
    x_test = norm(np.concatenate(wins))
    groups = np.concatenate([np.full(len(w), i) for i, w in enumerate(wins)])
    y_test = np.concatenate([np.full(len(w), lab) for w, (_, lab, _) in zip(wins, test)])
    machine = np.concatenate([np.full(len(w), mid) for w, (_, _, mid) in zip(wins, test)])
    print(f"mimii windows: train {len(xs['train'])}, val {len(xs['val'])}, test {len(x_test)}", flush=True)
    return Task(
        name="mimii_fan_ae", model=mimii_model(), kind="anomaly",
        x_train=xs["train"], y_train=np.zeros(len(xs["train"]), np.int64),
        x_val=xs["val"], y_val=np.zeros(len(xs["val"]), np.int64),
        x_test=x_test, y_test=y_test, test_groups=groups,
        test_subsets={m: machine == m for m in sorted(set(machine))},
        datasets=["mimii"], labels=["normal", "anomaly"],
        description=f"Machine-sound anomaly detection autoencoder ({MIMII_FRAMES} x {MIMII_MELS} log-mel "
                    "-> 64-64-8-64-64), trained on normal fan recordings of MIMII (6 dB SNR); anomaly "
                    "score = reconstruction MSE averaged over a 10 s clip",
        preprocess={"sample_rate": 16000, "channel": 0, "n_fft": MIMII_FFT, "hop": MIMII_HOP,
                    "n_mels": MIMII_MELS, "fmin": 20.0, "fmax": 8000.0, "frames": MIMII_FRAMES,
                    "log": "natural log of mel power + 1e-6", "mean": mean.tolist(), "std": std.tolist()})


TASKS = {"har": task_har, "can": task_can, "mimii": task_mimii}
TASK_DATASETS = {"har": ["uci-har"], "can": ["road"], "mimii": ["mimii"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="+", choices=sorted(TASKS))
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--version", default="0.2.0")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--download", action="store_true", help="download the datasets first")
    args = ap.parse_args(argv)
    if args.download:
        from ..data.download import download

        for name in args.tasks:
            for ds in TASK_DATASETS.get(name, []):
                download(ds)
    tf = _tf()
    tf.keras.utils.set_random_seed(args.seed)
    reports = []
    for name in args.tasks:
        task = TASKS[name](args.seed)
        fit(task, args.epochs)
        rep = export(task, args.version, args.seed)
        print(json.dumps({k: v for k, v in rep.items() if k != "datasets"}, indent=2), flush=True)
        reports.append(rep)
    # regenerate firmware sources with all zoo models
    from .codegen import write_zoo_sources
    from .zoo import FW_ZOO_DIR, load_zoo

    write_zoo_sources(list(load_zoo().values()), FW_ZOO_DIR)
    return reports


if __name__ == "__main__":
    main()
