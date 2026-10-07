"""Bit-exact host reference of firmware/lib/microinfer (int8 inference).

The HIL tests compare every device output against this implementation.
"""
from __future__ import annotations

import numpy as np

from .model import QLayer, QModel
from . import quant
from .quant import trunc_div


def _requant(layer: QLayer, acc: np.ndarray) -> np.ndarray:
    """acc has the output channel as last axis."""
    mult = layer.mult.astype(np.int64)
    shift = layer.shift.astype(np.int64)
    fn = (quant.multiply_by_quantized_multiplier_single if layer.rounding == "single"
          else quant.multiply_by_quantized_multiplier)
    v = fn(acc, mult, shift) + layer.out_zp
    return np.clip(v, layer.act_min, layer.act_max).astype(np.int8)


def _patches(x: np.ndarray, layer: QLayer, fill: int) -> tuple[np.ndarray, np.ndarray]:
    """im2col: returns (patches[oh, ow, kh, kw, c], valid[oh, ow, kh, kw])."""
    ih, iw, c = layer.in_shape
    oh, ow, _ = layer.out_shape
    kh, kw = layer.kernel
    sh, sw = layer.stride
    pt, pl = layer.pad
    pad_b = max(0, (oh - 1) * sh + kh - pt - ih)
    pad_r = max(0, (ow - 1) * sw + kw - pl - iw)
    xp = np.full((ih + pt + pad_b, iw + pl + pad_r, c), fill, dtype=np.int64)
    xp[pt:pt + ih, pl:pl + iw, :] = x
    valid = np.zeros((ih + pt + pad_b, iw + pl + pad_r), dtype=bool)
    valid[pt:pt + ih, pl:pl + iw] = True
    patches = np.empty((oh, ow, kh, kw, c), dtype=np.int64)
    vmask = np.empty((oh, ow, kh, kw), dtype=bool)
    for ky in range(kh):
        for kx in range(kw):
            ys = slice(ky, ky + (oh - 1) * sh + 1, sh)
            xs = slice(kx, kx + (ow - 1) * sw + 1, sw)
            patches[:, :, ky, kx, :] = xp[ys, xs, :]
            vmask[:, :, ky, kx] = valid[ys, xs]
    return patches, vmask


def run_layer(layer: QLayer, x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.int64).reshape(layer.in_shape)
    op = layer.op
    if op == "reshape":
        return x.astype(np.int8).reshape(layer.out_shape)
    if op == "dense":
        w = layer.weights.astype(np.int64).reshape(layer.out_shape[2], -1)
        v = x.reshape(-1) - layer.in_zp
        acc = w @ v
        if layer.bias is not None:
            acc = acc + layer.bias.astype(np.int64)
        return _requant(layer, acc).reshape(layer.out_shape)
    if op == "conv2d":
        oh, ow, oc = layer.out_shape
        kh, kw = layer.kernel
        ic = layer.in_shape[2]
        # Padded pixels hold in_zp so that (x - zp) == 0, like skipping them.
        patches, _ = _patches(x, layer, fill=layer.in_zp)
        cols = (patches - layer.in_zp).reshape(oh * ow, kh * kw * ic)
        w = layer.weights.astype(np.int64).reshape(oc, kh * kw * ic)
        acc = cols @ w.T
        if layer.bias is not None:
            acc = acc + layer.bias.astype(np.int64)
        return _requant(layer, acc).reshape(layer.out_shape)
    if op == "dwconv2d":
        oh, ow, oc = layer.out_shape
        kh, kw = layer.kernel
        ic = layer.in_shape[2]
        dm = oc // ic
        patches, _ = _patches(x, layer, fill=layer.in_zp)
        patches = np.repeat(patches - layer.in_zp, dm, axis=-1)  # [oh,ow,kh,kw,oc]
        w = layer.weights.astype(np.int64).reshape(kh, kw, oc)
        acc = np.einsum("yxhwc,hwc->yxc", patches, w)
        if layer.bias is not None:
            acc = acc + layer.bias.astype(np.int64)
        return _requant(layer, acc)
    if op in ("maxpool2d", "avgpool2d"):
        patches, valid = _patches(x, layer, fill=0)
        vm = valid[..., None]
        if op == "maxpool2d":
            p = np.where(vm, patches, -128)
            out = p.max(axis=(2, 3))
            out = np.maximum(out, -128)
        else:
            s = np.where(vm, patches, 0).sum(axis=(2, 3))
            cnt = np.maximum(valid.sum(axis=(2, 3)), 1)[..., None]
            half = cnt // 2
            out = np.where(s > 0, trunc_div(s + half, cnt), trunc_div(s - half, cnt))
        return np.clip(out, layer.act_min, layer.act_max).astype(np.int8)
    raise ValueError(f"unsupported op {op}")


def run_model(model: QModel, x: np.ndarray, return_all: bool = False):
    """Run one int8 input (any shape with in_size elements)."""
    cur = np.asarray(x, dtype=np.int8).reshape(model.in_shape)
    outs = []
    for layer in model.layers:
        cur = run_layer(layer, cur)
        outs.append(cur)
    out = cur.reshape(-1).astype(np.int8)
    return (out, outs) if return_all else out


def run_batch(model: QModel, xs: np.ndarray) -> np.ndarray:
    xs = np.asarray(xs, dtype=np.int8).reshape(len(xs), -1)
    return np.stack([run_model(model, x) for x in xs]) if len(xs) else np.zeros((0, model.out_size), np.int8)
