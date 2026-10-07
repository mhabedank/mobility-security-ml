"""Reference model zoo for the HIL bench.

    python -m hilbench.ml.zoo            # rebuild models/zoo + firmware C sources

Every model is stored as ``models/zoo/<name>.npz`` (QModel) and optionally
``<name>.eval.npz`` (quantized evaluation set with labels). The firmware gets
the very same parameters through hilbench.ml.codegen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import datasets
from .codegen import write_zoo_sources
from .floatnet import FLayer, FloatNet
from .model import QModel
from .quant import quantize
from .reference import run_batch
from .train import train_dense

REPO_ROOT = Path(__file__).resolve().parents[2]
ZOO_DIR = REPO_ROOT / "models" / "zoo"
CUSTOM_DIR = REPO_ROOT / "models" / "custom"  # your own models (hilbench import-tflite)
FW_ZOO_DIR = REPO_ROOT / "firmware" / "lib" / "modelzoo" / "src"


def _save_eval(path: Path, model: QModel, x: np.ndarray, y: np.ndarray, **extra):
    xq = quantize(x.reshape(len(x), -1), model.input_scale, model.input_zp)
    np.savez_compressed(path, inputs=xq, labels=y.astype(np.int32), **extra)


def build_can_ids(out: Path) -> QModel:
    x, y, kinds = datasets.can_bus_frames(30000, seed=0)
    rng = np.random.default_rng(10)
    idx = rng.permutation(len(x))
    split = int(0.8 * len(x))
    tr, te = idx[:split], idx[split:]
    net = FloatNet((1, 1, datasets.CAN_FEATURES), [
        FLayer("dense", 32, act="relu"),
        FLayer("dense", 16, act="relu"),
        FLayer("dense", 2),
    ]).build(np.random.default_rng(0))
    cw = np.array([1.0, (y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1)])
    train_dense(net, x[tr], y[tr], loss="ce", epochs=25, lr=3e-3, class_weight=cw)
    acc_f = float((net.forward(x[te]).reshape(len(te), -1).argmax(1) == y[te]).mean())
    model = net.quantize("can_ids_mlp", x[tr][:2000],
                         description="CAN bus intrusion detection MLP (DoS/fuzzing/spoofing), 32-32-16-2",
                         test_data=x[te])
    pq = run_batch(model, quantize(x[te].reshape(len(te), -1), model.input_scale, model.input_zp))
    acc_q = float((pq.argmax(1) == y[te]).mean())
    model.meta.update(task="classification", classes=["normal", "attack"],
                      float_accuracy=acc_f, int8_accuracy=acc_q)
    ev = te[:512]
    _save_eval(out / "can_ids_mlp.eval.npz", model, x[ev], y[ev])
    return model


def build_sensor_ae(out: Path) -> QModel:
    x, _ = datasets.sensor_windows(4000, seed=1)
    net = FloatNet((1, 1, 64), [
        FLayer("dense", 64, act="relu"),
        FLayer("dense", 16),  # linear bottleneck: no dead units
        FLayer("dense", 64, act="relu"),
        FLayer("dense", 64),
    ]).build(np.random.default_rng(1))
    train_dense(net, x, x, loss="mse", epochs=400, lr=2e-3, batch=64)
    xe, ye = datasets.sensor_windows(512, seed=11, anomaly_ratio=0.3)
    model = net.quantize("sensor_ae", x[:2000],
                         description="Wheel-speed sensor anomaly autoencoder 64-64-16-64-64", test_data=xe)
    xq = quantize(xe.reshape(len(xe), -1), model.input_scale, model.input_zp)
    rec = (run_batch(model, xq).astype(np.float64) - model.output_zp) * model.output_scale
    err = ((rec - xe.reshape(len(xe), -1)) ** 2).mean(1)
    thr = float(np.percentile(err[ye == 0], 99))
    model.meta.update(task="anomaly", threshold=thr,
                      int8_detection_rate=float((err[ye == 1] > thr).mean()),
                      int8_false_positive_rate=float((err[ye == 0] > thr).mean()))
    _save_eval(out / "sensor_ae.eval.npz", model, xe, ye, targets=xe.reshape(len(xe), -1))
    return model


def build_imu_gnss_cnn(out: Path) -> QModel:
    x = datasets.imu_gnss_windows(512, seed=2)
    net = FloatNet((1, 64, 6), [
        FLayer("conv2d", 16, kernel=(1, 5), padding="same", act="relu"),
        FLayer("maxpool2d", kernel=(1, 2), stride=(1, 2)),
        FLayer("conv2d", 32, kernel=(1, 5), padding="same", act="relu"),
        FLayer("maxpool2d", kernel=(1, 2), stride=(1, 2)),
        FLayer("conv2d", 32, kernel=(1, 3), padding="same", act="relu6"),
        FLayer("avgpool2d", kernel=(1, 16), stride=(1, 16)),
        FLayer("reshape"),
        FLayer("dense", 2),
    ]).build(np.random.default_rng(2))
    return net.quantize("imu_gnss_cnn1d", x,
                        description="GNSS spoofing detector, 1D-CNN over IMU+GNSS window (benchmark weights)")


BUILDERS = [build_can_ids, build_sensor_ae, build_imu_gnss_cnn]


def load_zoo(zoo_dir: str | Path = ZOO_DIR, custom_dir: str | Path | None = CUSTOM_DIR) -> dict[str, QModel]:
    """Built-in reference models followed by custom models (models/custom/*.npz)."""
    zoo_dir = Path(zoo_dir)
    manifest = json.loads((zoo_dir / "manifest.json").read_text())
    models = {m["name"]: QModel.load(zoo_dir / f"{m['name']}.npz") for m in manifest["models"]}
    if custom_dir is not None and Path(custom_dir).is_dir():
        for p in sorted(Path(custom_dir).glob("*.npz")):
            if p.name.endswith(".eval.npz"):
                continue
            m = QModel.load(p)
            if m.name in models:
                raise ValueError(f"custom model {p} clashes with built-in model {m.name}")
            models[m.name] = m
    return models


def load_eval(name: str, zoo_dir: str | Path = ZOO_DIR) -> dict | None:
    from ..data.download import data_root

    p = Path(zoo_dir) / f"{name}.eval.npz"
    if not p.exists():
        p = CUSTOM_DIR / f"{name}.eval.npz"
    if not p.exists():  # held-out features of real datasets live outside the repo
        p = data_root() / "derived" / f"{name}.eval.npz"
    if not p.exists():
        return None
    with np.load(p) as z:
        return {k: z[k] for k in z.files}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ZOO_DIR))
    ap.add_argument("--fw-out", default=str(FW_ZOO_DIR))
    ap.add_argument("--codegen-only", action="store_true", help="only regenerate C from existing .npz files")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if not args.codegen_only:
        built = []
        for b in BUILDERS:
            m = b(out)
            m.save(out / f"{m.name}.npz")
            built.append(m)
            print(json.dumps({**m.summary(), **{k: v for k, v in m.meta.items() if k != "classes"}}))
        manifest = {"format": "hilbench-zoo/1", "models": [m.summary() for m in built]}
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    models = list(load_zoo(out).values())  # built-in + models/custom
    write_zoo_sources(models, Path(args.fw_out))
    print(f"wrote {len(models)} models to {out} and C sources to {args.fw_out}")


if __name__ == "__main__":
    main()
