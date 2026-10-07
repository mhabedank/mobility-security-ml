"""Minimal float network (numpy) + post-training int8 quantization.

Used to build the reference model zoo without a TensorFlow dependency. The
quantization scheme matches TFLite full-integer PTQ: asymmetric int8
activations (calibrated min/max), symmetric per-channel int8 weights, int32
bias with scale in_scale * w_scale.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import QLayer, QModel
from .quant import choose_qparams, quantize, quantize_multiplier, round_half_away
from . import reference


def same_padding(in_size: int, k: int, s: int) -> tuple[int, int]:
    """TFLite SAME padding -> (out_size, pad_before)."""
    out = -(-in_size // s)
    total = max((out - 1) * s + k - in_size, 0)
    return out, total // 2


@dataclass
class FLayer:
    op: str  # dense|conv2d|dwconv2d|maxpool2d|avgpool2d|reshape
    out_c: int = 0
    kernel: tuple[int, int] = (1, 1)
    stride: tuple[int, int] = (1, 1)
    padding: str = "valid"  # valid|same
    act: str | None = None  # None|relu|relu6
    depth_multiplier: int = 1
    w: np.ndarray | None = None
    b: np.ndarray | None = None
    # filled by build()
    in_shape: tuple[int, int, int] = (0, 0, 0)
    out_shape: tuple[int, int, int] = (0, 0, 0)
    pad: tuple[int, int] = (0, 0)


@dataclass
class FloatNet:
    in_shape: tuple[int, int, int]
    layers: list[FLayer] = field(default_factory=list)

    def build(self, rng: np.random.Generator | None = None) -> "FloatNet":
        """Infer shapes; initialise missing weights (He init)."""
        rng = rng or np.random.default_rng(0)
        shape = tuple(self.in_shape)
        for l in self.layers:
            l.in_shape = shape
            h, w, c = shape
            if l.op == "dense":
                l.out_shape = (1, 1, l.out_c)
                fan_in = h * w * c
                if l.w is None:
                    l.w = rng.normal(0, np.sqrt(2.0 / fan_in), (l.out_c, fan_in))
                    l.b = rng.normal(0, 0.05, l.out_c)
            elif l.op == "reshape":
                l.out_shape = (1, 1, h * w * c)
            else:
                kh, kw = l.kernel
                sh, sw = l.stride
                if l.padding == "same":
                    oh, pt = same_padding(h, kh, sh)
                    ow, pl = same_padding(w, kw, sw)
                else:
                    oh, ow, pt, pl = (h - kh) // sh + 1, (w - kw) // sw + 1, 0, 0
                l.pad = (pt, pl)
                if l.op == "conv2d":
                    l.out_shape = (oh, ow, l.out_c)
                    if l.w is None:
                        l.w = rng.normal(0, np.sqrt(2.0 / (kh * kw * c)), (l.out_c, kh, kw, c))
                        l.b = rng.normal(0, 0.05, l.out_c)
                elif l.op == "dwconv2d":
                    oc = c * l.depth_multiplier
                    l.out_c = oc
                    l.out_shape = (oh, ow, oc)
                    if l.w is None:
                        l.w = rng.normal(0, np.sqrt(2.0 / (kh * kw)), (kh, kw, oc))
                        l.b = rng.normal(0, 0.05, oc)
                elif l.op in ("maxpool2d", "avgpool2d"):
                    l.out_shape = (oh, ow, c)
                else:
                    raise ValueError(l.op)
            shape = l.out_shape
        return self

    # ---- float forward ---------------------------------------------------
    @staticmethod
    def _act(x, act):
        if act == "relu":
            return np.maximum(x, 0)
        if act == "relu6":
            return np.clip(x, 0, 6)
        return x

    def _patches(self, x, l: FLayer, fill):
        n = x.shape[0]
        h, w, c = l.in_shape
        oh, ow, _ = l.out_shape
        kh, kw = l.kernel
        sh, sw = l.stride
        pt, pl = l.pad
        pb = max(0, (oh - 1) * sh + kh - pt - h)
        pr = max(0, (ow - 1) * sw + kw - pl - w)
        xp = np.full((n, h + pt + pb, w + pl + pr, c), fill, dtype=np.float64)
        xp[:, pt:pt + h, pl:pl + w] = x
        valid = np.zeros((h + pt + pb, w + pl + pr), bool)
        valid[pt:pt + h, pl:pl + w] = True
        p = np.empty((n, oh, ow, kh, kw, c))
        vm = np.empty((oh, ow, kh, kw), bool)
        for ky in range(kh):
            for kx in range(kw):
                ys = slice(ky, ky + (oh - 1) * sh + 1, sh)
                xs = slice(kx, kx + (ow - 1) * sw + 1, sw)
                p[:, :, :, ky, kx] = xp[:, ys, xs]
                vm[:, :, ky, kx] = valid[ys, xs]
        return p, vm

    def forward(self, x: np.ndarray, return_all: bool = False):
        x = np.asarray(x, dtype=np.float64).reshape((-1,) + tuple(self.in_shape))
        outs = []
        for l in self.layers:
            n = x.shape[0]
            if l.op == "dense":
                x = self._act(x.reshape(n, -1) @ l.w.T + l.b, l.act).reshape((n,) + l.out_shape)
            elif l.op == "reshape":
                x = x.reshape((n,) + l.out_shape)
            elif l.op == "conv2d":
                p, _ = self._patches(x, l, 0.0)
                oh, ow, oc = l.out_shape
                cols = p.reshape(n, oh, ow, -1)
                x = self._act(cols @ l.w.reshape(oc, -1).T + l.b, l.act)
            elif l.op == "dwconv2d":
                p, _ = self._patches(x, l, 0.0)
                p = np.repeat(p, l.depth_multiplier, axis=-1)
                x = self._act(np.einsum("nyxhwc,hwc->nyxc", p, l.w) + l.b, l.act)
            elif l.op == "maxpool2d":
                p, vm = self._patches(x, l, -np.inf)
                x = np.where(vm[None, ..., None], p, -np.inf).max(axis=(3, 4))
            elif l.op == "avgpool2d":
                p, vm = self._patches(x, l, 0.0)
                cnt = np.maximum(vm.sum(axis=(2, 3)), 1)[None, ..., None]
                x = np.where(vm[None, ..., None], p, 0).sum(axis=(3, 4)) / cnt
            outs.append(x)
        return (x, outs) if return_all else x

    # ---- quantization ----------------------------------------------------
    def quantize(self, name: str, calib: np.ndarray, description: str = "",
                 n_tests: int = 8, test_data: np.ndarray | None = None) -> QModel:
        calib = np.asarray(calib, dtype=np.float64).reshape((-1,) + tuple(self.in_shape))
        _, outs = self.forward(calib, return_all=True)
        in_scale, in_zp = choose_qparams(calib.min(), calib.max())

        layers: list[QLayer] = []
        s_in, zp_in = in_scale, in_zp
        for l, o in zip(self.layers, outs):
            if l.op in ("reshape", "maxpool2d", "avgpool2d"):
                # TFLite requires identical in/out quantization for these.
                layers.append(QLayer(
                    op=l.op, in_shape=l.in_shape, out_shape=l.out_shape, kernel=l.kernel,
                    stride=l.stride, pad=l.pad, in_zp=zp_in, out_zp=zp_in,
                    in_scale=s_in, out_scale=s_in))
                continue

            s_out, zp_out = choose_qparams(o.min(), o.max())
            if l.op == "dense":
                w = l.w  # [oc, ic]
                axis_w = w.reshape(w.shape[0], -1)
            elif l.op == "conv2d":
                axis_w = l.w.reshape(l.w.shape[0], -1)
            else:  # dwconv2d: channel is the last axis
                axis_w = l.w.reshape(-1, l.w.shape[-1]).T
            w_absmax = np.maximum(np.abs(axis_w).max(axis=1), 1e-8)
            w_scale = w_absmax / 127.0
            if l.op == "dwconv2d":
                wq = np.clip(np.floor(l.w / w_scale + 0.5), -127, 127).astype(np.int8)
            else:
                shp = (-1,) + (1,) * (l.w.ndim - 1)
                wq = np.clip(np.floor(l.w / w_scale.reshape(shp) + 0.5), -127, 127).astype(np.int8)
            bias = np.array([round_half_away(b / (s_in * ws)) for b, ws in zip(l.b, w_scale)], dtype=np.int64)
            bias = np.clip(bias, -(1 << 31), (1 << 31) - 1).astype(np.int32)
            mults, shifts = zip(*(quantize_multiplier(s_in * ws / s_out) for ws in w_scale))

            act_min, act_max = -128, 127
            if l.act in ("relu", "relu6"):
                act_min = max(act_min, int(quantize(np.array([0.0]), s_out, zp_out)[0]))
            if l.act == "relu6":
                act_max = min(act_max, int(quantize(np.array([6.0]), s_out, zp_out)[0]))

            layers.append(QLayer(
                op=l.op, in_shape=l.in_shape, out_shape=l.out_shape, kernel=l.kernel,
                stride=l.stride, pad=l.pad, in_zp=zp_in, out_zp=zp_out, act_min=act_min,
                act_max=act_max, weights=wq.reshape(-1), bias=bias,
                mult=np.array(mults, dtype=np.int32), shift=np.array(shifts, dtype=np.int8),
                in_scale=s_in, out_scale=s_out))
            s_in, zp_in = s_out, zp_out

        model = QModel(name=name, layers=layers, input_scale=in_scale, input_zp=in_zp,
                       output_scale=s_in, output_zp=zp_in, description=description)
        src = calib if test_data is None else np.asarray(test_data).reshape((-1,) + tuple(self.in_shape))
        tin = quantize(src[:n_tests].reshape(min(n_tests, len(src)), -1), in_scale, in_zp)
        model.test_inputs = tin
        model.test_outputs = reference.run_batch(model, tin)
        return model
