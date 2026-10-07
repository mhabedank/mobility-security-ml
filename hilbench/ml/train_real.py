"""Train the bench models on real, openly licensed datasets.

    pip install -e ".[train]"
    hilbench data download speech-commands
    python -m hilbench.ml.train_real kws [--epochs 20] [--version 0.2.0]

Pipeline per task: features -> Keras model -> full-integer int8 TFLite ->
hilbench.ml.tflite_import (bit-exact with the TFLite reference kernels) ->
evaluation of the *device arithmetic* on the held-out test split.

Outputs
  models/zoo/<name>.npz           quantized model (parameters only, no data)
  build/models/<name>.tflite      TFLite flatbuffer (for Hugging Face / other runtimes)
  build/models/<name>.json        metrics, dataset provenance, license
  $HILBENCH_DATA/derived/<name>.eval.npz   held-out features for HIL accuracy tests
Training data is never written into the repository.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field

import numpy as np

from ..config import REPO_ROOT
from ..data.download import data_root, dataset_dir
from ..data.registry import SOURCES

ZOO_DIR = REPO_ROOT / "models" / "zoo"
ARTIFACTS = REPO_ROOT / "build" / "models"


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
    provenance = [{
        "id": SOURCES[d].id, "title": SOURCES[d].title, "license": SOURCES[d].license,
        "attribution": SOURCES[d].attribution, "citation": SOURCES[d].citation,
        "homepage": SOURCES[d].homepage,
        "retrieved": json.loads((dataset_dir(d) / "SOURCE.json").read_text()).get("retrieved_at")
        if (dataset_dir(d) / "SOURCE.json").exists() else None,
    } for d in task.datasets]
    qm.meta.update(task="classification", classes=task.labels, version=version, datasets=provenance,
                   trained_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **metrics)
    qm.save(ZOO_DIR / f"{task.name}.npz")

    derived = data_root() / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    keep = np.random.default_rng(seed).permutation(len(xq))[:1024]
    np.savez_compressed(derived / f"{task.name}.eval.npz", inputs=xq[keep], labels=task.y_test[keep].astype(np.int32))

    report = {"name": task.name, "version": version, "description": task.description, "labels": task.labels,
              "summary": qm.summary(), **metrics, "datasets": provenance}
    (ARTIFACTS / f"{task.name}.json").write_text(json.dumps(report, indent=2) + "\n")
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


TASKS = {"kws": task_kws}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="+", choices=sorted(TASKS))
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--version", default="0.2.0")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
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
