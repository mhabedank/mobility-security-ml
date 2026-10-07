"""Quantized model representation shared by the reference engine, the C code
generator, the TFLite importer and the HIL tests.

A QModel is stored as a single ``.npz`` file (JSON header + arrays) so that the
host side of the bench can always recompute the expected device output.
"""
from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

OPS = {"dense": 1, "conv2d": 2, "dwconv2d": 3, "maxpool2d": 4, "avgpool2d": 5, "reshape": 6}
PARAM_OPS = ("dense", "conv2d", "dwconv2d")


@dataclass
class QLayer:
    op: str
    in_shape: tuple[int, int, int]
    out_shape: tuple[int, int, int]
    kernel: tuple[int, int] = (1, 1)
    stride: tuple[int, int] = (1, 1)
    pad: tuple[int, int] = (0, 0)  # (top, left); bottom/right are implied
    in_zp: int = 0
    out_zp: int = 0
    act_min: int = -128
    act_max: int = 127
    weights: np.ndarray | None = None  # int8, C layout (see microinfer.h)
    bias: np.ndarray | None = None  # int32 [out_c]
    mult: np.ndarray | None = None  # int32 [1 or out_c]
    shift: np.ndarray | None = None  # int8  [1 or out_c]
    in_scale: float = 1.0
    out_scale: float = 1.0

    @property
    def has_params(self) -> bool:
        return self.op in PARAM_OPS

    def macs(self) -> int:
        oh, ow, oc = self.out_shape
        ih, iw, ic = self.in_shape
        kh, kw = self.kernel
        if self.op == "dense":
            return ic * oc
        if self.op == "conv2d":
            return oh * ow * oc * kh * kw * ic
        if self.op == "dwconv2d":
            return oh * ow * oc * kh * kw
        return 0

    def param_bytes(self) -> int:
        if not self.has_params:
            return 0
        n = self.weights.size + self.mult.size * 4 + self.shift.size
        if self.bias is not None:
            n += self.bias.size * 4
        return n


@dataclass
class QModel:
    name: str
    layers: list[QLayer]
    input_scale: float
    input_zp: int
    output_scale: float
    output_zp: int
    description: str = ""
    test_inputs: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), np.int8))
    test_outputs: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), np.int8))
    meta: dict = field(default_factory=dict)

    @property
    def in_shape(self) -> tuple[int, int, int]:
        return self.layers[0].in_shape

    @property
    def out_shape(self) -> tuple[int, int, int]:
        return self.layers[-1].out_shape

    @property
    def in_size(self) -> int:
        return int(np.prod(self.in_shape))

    @property
    def out_size(self) -> int:
        return int(np.prod(self.out_shape))

    def arena_size(self) -> int:
        """Two ping-pong buffers, each big enough for the largest tensor."""
        biggest = max(max(int(np.prod(l.in_shape)), int(np.prod(l.out_shape))) for l in self.layers)
        half = (biggest + 3) & ~3
        return 2 * half

    def macs(self) -> int:
        return sum(l.macs() for l in self.layers)

    def param_bytes(self) -> int:
        return sum(l.param_bytes() for l in self.layers)

    def crc32(self) -> int:
        """Must match mi_model_crc32() in microinfer.c."""
        crc = 0
        for l in self.layers:
            if not l.has_params:
                continue
            crc = zlib.crc32(l.weights.astype(np.int8).tobytes(), crc)
            if l.bias is not None:
                crc = zlib.crc32(l.bias.astype("<i4").tobytes(), crc)
            crc = zlib.crc32(l.mult.astype("<i4").tobytes(), crc)
            crc = zlib.crc32(l.shift.astype(np.int8).tobytes(), crc)
        return crc & 0xFFFFFFFF

    # ---- persistence -----------------------------------------------------
    def save(self, path: str | Path) -> None:
        arrays: dict[str, np.ndarray] = {
            "test_inputs": self.test_inputs.astype(np.int8),
            "test_outputs": self.test_outputs.astype(np.int8),
        }
        layer_meta = []
        for i, l in enumerate(self.layers):
            meta = {
                k: getattr(l, k)
                for k in (
                    "op", "in_shape", "out_shape", "kernel", "stride", "pad", "in_zp",
                    "out_zp", "act_min", "act_max", "in_scale", "out_scale",
                )
            }
            for k in ("weights", "bias", "mult", "shift"):
                v = getattr(l, k)
                if v is not None:
                    arrays[f"l{i}_{k}"] = v
            layer_meta.append(meta)
        header = {
            "format": "hilbench-qmodel/1",
            "name": self.name,
            "description": self.description,
            "input_scale": self.input_scale,
            "input_zp": self.input_zp,
            "output_scale": self.output_scale,
            "output_zp": self.output_zp,
            "layers": layer_meta,
            "meta": self.meta,
        }
        arrays["header"] = np.frombuffer(json.dumps(header).encode(), dtype=np.uint8)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            np.savez_compressed(fh, **arrays)

    @classmethod
    def load(cls, path: str | Path) -> "QModel":
        with np.load(path, allow_pickle=False) as z:
            header = json.loads(bytes(z["header"]).decode())
            layers = []
            for i, m in enumerate(header["layers"]):
                kw = dict(m)
                for k in ("in_shape", "out_shape", "kernel", "stride", "pad"):
                    kw[k] = tuple(kw[k])
                for k in ("weights", "bias", "mult", "shift"):
                    key = f"l{i}_{k}"
                    kw[k] = z[key] if key in z.files else None
                layers.append(QLayer(**kw))
            return cls(
                name=header["name"],
                description=header.get("description", ""),
                layers=layers,
                input_scale=header["input_scale"],
                input_zp=header["input_zp"],
                output_scale=header["output_scale"],
                output_zp=header["output_zp"],
                test_inputs=z["test_inputs"],
                test_outputs=z["test_outputs"],
                meta=header.get("meta", {}),
            )

    def summary(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "in_shape": list(self.in_shape),
            "out_shape": list(self.out_shape),
            "layers": len(self.layers),
            "macs": self.macs(),
            "param_bytes": self.param_bytes(),
            "arena_size": self.arena_size(),
            "crc32": f"{self.crc32():08x}",
            "n_tests": int(self.test_inputs.shape[0]),
        }
