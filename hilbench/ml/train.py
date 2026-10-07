"""Tiny numpy trainer for dense-only FloatNets (MLP classifiers, autoencoders).

Just enough to produce meaningful reference models without TensorFlow.
"""
from __future__ import annotations

import numpy as np

from .floatnet import FloatNet


def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def train_dense(net: FloatNet, x: np.ndarray, y: np.ndarray, loss: str = "ce", epochs: int = 20,
                lr: float = 3e-3, batch: int = 128, seed: int = 0, l2: float = 1e-5,
                class_weight: np.ndarray | None = None) -> list[float]:
    """Adam on mini-batches. loss='ce' (y = int labels) or 'mse' (y = targets)."""
    layers = [l for l in net.layers if l.op != "reshape"]
    if any(l.op != "dense" for l in layers):
        raise ValueError("train_dense only supports dense layers")
    rng = np.random.default_rng(seed)
    x = x.reshape(len(x), -1).astype(np.float64)
    params = [(l, "w") for l in layers] + [(l, "b") for l in layers]
    m = {id(getattr(l, k)): np.zeros_like(getattr(l, k)) for l, k in params}
    v = {id(getattr(l, k)): np.zeros_like(getattr(l, k)) for l, k in params}
    keys = [(l, k, id(getattr(l, k))) for l, k in params]
    b1, b2, eps, t = 0.9, 0.999, 1e-8, 0
    history = []
    for _ in range(epochs):
        order = rng.permutation(len(x))
        total = 0.0
        for start in range(0, len(x), batch):
            idx = order[start:start + batch]
            a = x[idx]
            acts, pre = [a], []
            for l in layers:
                z = a @ l.w.T + l.b
                pre.append(z)
                a = np.maximum(z, 0) if l.act == "relu" else (np.clip(z, 0, 6) if l.act == "relu6" else z)
                acts.append(a)
            n = len(idx)
            if loss == "ce":
                p = _softmax(acts[-1])
                yi = y[idx].astype(int)
                wgt = class_weight[yi] if class_weight is not None else np.ones(n)
                total += float(-(wgt * np.log(p[np.arange(n), yi] + 1e-12)).sum())
                grad = p.copy()
                grad[np.arange(n), yi] -= 1
                grad *= wgt[:, None] / n
            else:
                diff = acts[-1] - y[idx].reshape(n, -1)
                total += float((diff ** 2).sum())
                grad = 2 * diff / n
            grads = {}
            for li in range(len(layers) - 1, -1, -1):
                l = layers[li]
                if l.act == "relu":
                    grad = grad * (pre[li] > 0)
                elif l.act == "relu6":
                    grad = grad * ((pre[li] > 0) & (pre[li] < 6))
                grads[(id(l), "w")] = grad.T @ acts[li] + l2 * l.w
                grads[(id(l), "b")] = grad.sum(axis=0)
                grad = grad @ l.w
            t += 1
            for l, k, pid in keys:
                g = grads[(id(l), k)]
                m[pid] = b1 * m[pid] + (1 - b1) * g
                v[pid] = b2 * v[pid] + (1 - b2) * g * g
                mh = m[pid] / (1 - b1 ** t)
                vh = v[pid] / (1 - b2 ** t)
                # Moment buffers stay keyed by the id of the *initial* array.
                setattr(l, k, getattr(l, k) - lr * mh / (np.sqrt(vh) + eps))
        history.append(total / len(x))
    return history
