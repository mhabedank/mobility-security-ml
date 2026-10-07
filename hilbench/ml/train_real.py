"""Train the bench models on real, openly licensed datasets.

    pip install -e ".[train]"
    hilbench data download speech-commands
    python -m hilbench.ml.train_real kws [--epochs 20] [--version 0.2.0]

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
    pred_float = task.model.predict(task.x_test, verbose=0).argmax(-1)
    metrics = {
        "float_accuracy": float((pred_float == task.y_test).mean()),
        "int8_accuracy": float((out.argmax(1) == task.y_test).mean()),
        "test_samples": int(len(task.y_test)),
        "tflite_interpreter_mismatches": int(mismatches),
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
    provenance = [{
        "id": SOURCES[d].id, "title": SOURCES[d].title, "license": SOURCES[d].license,
        "attribution": SOURCES[d].attribution, "citation": SOURCES[d].citation,
        "homepage": SOURCES[d].homepage,
        "retrieved": json.loads((dataset_dir(d) / "SOURCE.json").read_text()).get("retrieved_at")
        if (dataset_dir(d) / "SOURCE.json").exists() else None,
    } for d in task.datasets]
    qm.meta.update(task="classification", classes=task.labels, version=version, datasets=provenance,
                   preprocess=task.preprocess,
                   trained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **metrics)
    qm.save(ZOO_DIR / f"{task.name}.npz")

    derived = data_root() / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    keep = np.random.default_rng(seed).permutation(len(xq))[:1024]
    np.savez_compressed(derived / f"{task.name}.eval.npz", inputs=xq[keep], labels=task.y_test[keep].astype(np.int32))

    report = {"name": task.name, "version": version, "description": task.description, "labels": task.labels,
              "summary": qm.summary(), **metrics, "datasets": provenance}
    (ARTIFACTS / f"{task.name}.report.json").write_text(json.dumps(report, indent=2) + "\n")
    _update_manifest(qm, version)
    return report


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
    m.compile(optimizer=tf.keras.optimizers.Adam(lr), loss="sparse_categorical_crossentropy",
              metrics=["accuracy"])
    m.fit(task.x_train, task.y_train, validation_data=(task.x_val, task.y_val), epochs=epochs,
          batch_size=128, verbose=2, **task.fit_kwargs)


# ------------------------------------------------------------------ KWS --

KWS_WORDS = ["yes", "no", "up", "down", "left", "right", "on", "off", "stop", "go"]
KWS_LABELS = ["_silence_", "_unknown_"] + KWS_WORDS


def _kws_features(args):
    from .features import mfcc, read_wav

    path, noise, shift, vol = args
    x = read_wav(path) if path else np.zeros(16000, np.float32)
    if shift:
        x = np.roll(x, shift)
        if shift > 0:
            x[:shift] = 0
        else:
            x[shift:] = 0
    if noise is not None:
        x = x + vol * noise
    return mfcc(x)


def load_kws(seed: int = 0, unknown_ratio: float = 0.1, silence_ratio: float = 0.1, workers: int = 4):
    from multiprocessing import Pool

    from .features import read_wav

    root = dataset_dir("speech-commands") / "extracted"
    if not (root / "testing_list.txt").exists():
        raise SystemExit("speech-commands not downloaded: hilbench data download speech-commands")
    rng = np.random.default_rng(seed)
    test = set((root / "testing_list.txt").read_text().split())
    val = set((root / "validation_list.txt").read_text().split())
    noises = [read_wav(p, length=0) for p in sorted((root / "_background_noise_").glob("*.wav"))]

    splits = {"train": [], "val": [], "test": []}
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for f in sorted(d.glob("*.wav")):
            rel = f"{d.name}/{f.name}"
            split = "test" if rel in test else "val" if rel in val else "train"
            label = KWS_LABELS.index(d.name) if d.name in KWS_WORDS else 1
            splits[split].append((str(f), label))

    def noise_clip():
        n = noises[rng.integers(len(noises))]
        s = rng.integers(0, len(n) - 16000)
        return n[s:s + 16000]

    out = {}
    for split, items in splits.items():
        known = [it for it in items if it[1] != 1]
        unknown = [it for it in items if it[1] == 1]
        n_unk = int(len(known) * unknown_ratio / (1 - unknown_ratio - silence_ratio))
        n_sil = int(len(known) * silence_ratio / (1 - unknown_ratio - silence_ratio))
        pick = [unknown[i] for i in rng.permutation(len(unknown))[:n_unk]]
        jobs = []
        for path, _label in known + pick:
            aug = split == "train"
            jobs.append((path, noise_clip() if aug and rng.random() < 0.8 else None,
                         int(rng.integers(-1600, 1601)) if aug else 0, float(rng.uniform(0, 0.1))))
        labels = [lab for _, lab in known + pick]
        for _ in range(n_sil):  # silence = background noise only
            jobs.append((None, noise_clip(), 0, float(rng.uniform(0, 1.0))))
            labels.append(0)
        with Pool(workers) as pool:
            feats = pool.map(_kws_features, jobs, chunksize=256)
        x = np.stack(feats)[..., None].astype(np.float32)
        y = np.array(labels, dtype=np.int64)
        perm = rng.permutation(len(y))
        out[split] = (x[perm], y[perm])
        print(f"kws {split}: {len(y)} samples", flush=True)
    return out


def kws_model(filters: int = 32, blocks: int = 4):
    tf = _tf()
    L = tf.keras.layers
    x = inp = L.Input((49, 10, 1))
    x = L.Conv2D(filters, (10, 4), strides=(2, 2), padding="same", use_bias=False)(x)
    x = L.BatchNormalization()(x)
    x = L.ReLU()(x)
    for _ in range(blocks):
        x = L.DepthwiseConv2D((3, 3), padding="same", use_bias=False)(x)
        x = L.BatchNormalization()(x)
        x = L.ReLU()(x)
        x = L.Conv2D(filters, 1, use_bias=False)(x)
        x = L.BatchNormalization()(x)
        x = L.ReLU()(x)
    x = L.AveragePooling2D((25, 5))(x)  # global average pool microinfer can run
    x = L.Flatten()(x)
    x = L.Dropout(0.2)(x)
    x = L.Dense(len(KWS_LABELS))(x)
    x = L.Softmax()(x)
    return tf.keras.Model(inp, x)


def task_kws(seed: int) -> Task:
    d = load_kws(seed)
    return Task(
        name="kws_dscnn", model=kws_model(),
        x_train=d["train"][0], y_train=d["train"][1], x_val=d["val"][0], y_val=d["val"][1],
        x_test=d["test"][0], y_test=d["test"][1], datasets=["speech-commands"], labels=KWS_LABELS,
        description="Keyword spotting DS-CNN (12 classes, 49x10 MFCC), trained on Speech Commands v0.02")


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


TASKS = {"kws": task_kws, "har": task_har, "can": task_can}
TASK_DATASETS = {"kws": ["speech-commands"], "har": ["uci-har"], "can": ["road"]}


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
