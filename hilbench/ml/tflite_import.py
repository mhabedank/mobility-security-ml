"""Import fully int8-quantized .tflite models into the bench.

    hilbench import-tflite my_model.tflite --name my_model

Supported (sequential graphs): CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED,
MAX_POOL_2D, AVERAGE_POOL_2D, RESHAPE/SQUEEZE, a leading QUANTIZE and trailing
DEQUANTIZE / SOFTMAX (dropped: the device returns the int8 logits, argmax is
unchanged). Fused NONE/RELU/RELU6 activations. Use AveragePooling2D over the
whole feature map instead of GlobalAveragePooling2D (which becomes MEAN).

Needs `pip install tflite` (pure-python flatbuffer bindings).
"""
from __future__ import annotations

import numpy as np

from .model import QLayer, QModel
from .quant import quantize_multiplier, round_half_away
from . import reference


class UnsupportedModel(ValueError):
    pass


def _tfl():
    try:
        import tflite
    except ImportError as e:  # pragma: no cover
        raise UnsupportedModel("the 'tflite' package is required: pip install tflite") from e
    return tflite


def _act_range(act: int, scale: float, zp: int, tfl) -> tuple[int, int]:
    lo, hi = -128, 127
    A = tfl.ActivationFunctionType
    if act == A.NONE:
        return lo, hi
    if act in (A.RELU, A.RELU6, A.RELU_N1_TO_1):
        q0 = zp + round_half_away(0.0 / scale)
        if act == A.RELU_N1_TO_1:
            q0 = zp + round_half_away(-1.0 / scale)
        lo = max(lo, q0)
        if act == A.RELU6:
            hi = min(hi, zp + round_half_away(6.0 / scale))
        if act == A.RELU_N1_TO_1:
            hi = min(hi, zp + round_half_away(1.0 / scale))
        return lo, hi
    raise UnsupportedModel(f"unsupported fused activation {act}")


def _hwc(shape) -> tuple[int, int, int]:
    s = [int(v) for v in shape]
    if len(s) == 4:
        return s[1], s[2], s[3]
    if len(s) == 3:
        return 1, s[1], s[2]
    if len(s) == 2:
        return 1, 1, s[1]
    if len(s) == 1:
        return 1, 1, s[0]
    raise UnsupportedModel(f"unsupported tensor rank {len(s)}")


def _pad(padding: int, in_size: int, out_size: int, k: int, s: int, tfl) -> int:
    if padding == tfl.Padding.VALID:
        return 0
    total = max((out_size - 1) * s + k - in_size, 0)
    return total // 2


def load_tflite(path: str, name: str, description: str = "", n_tests: int = 8,
                seed: int = 0, fc_rounding: str = "single") -> QModel:
    tfl = _tfl()
    buf = open(path, "rb").read()
    if len(buf) < 8 or buf[4:8] != b"TFL3":
        raise UnsupportedModel(f"{path} is not a TFLite flatbuffer (missing TFL3 identifier)")
    model = tfl.Model.GetRootAsModel(buf, 0)
    if model.SubgraphsLength() != 1:
        raise UnsupportedModel("only single-subgraph models are supported")
    sg = model.Subgraphs(0)

    def tensor(i):
        return sg.Tensors(int(i))

    def qparams(t):
        q = t.Quantization()
        if q is None or q.ScaleLength() == 0:
            raise UnsupportedModel(f"tensor {t.Name().decode()} is not quantized")
        return q.ScaleAsNumpy().astype(np.float64), q.ZeroPointAsNumpy().astype(np.int64)

    def data(t, dtype):
        b = model.Buffers(t.Buffer()).DataAsNumpy()
        if isinstance(b, int) or b is None or len(b) == 0:
            raise UnsupportedModel(f"tensor {t.Name().decode()} has no constant data")
        return np.frombuffer(b.tobytes(), dtype=dtype).reshape([int(v) for v in t.ShapeAsNumpy()])

    def opname(op):
        oc = model.OperatorCodes(op.OpcodeIndex())
        code = max(oc.BuiltinCode(), oc.DeprecatedBuiltinCode())
        for k, v in vars(tfl.BuiltinOperator).items():
            if v == code and not k.startswith("_"):
                return k
        return str(code)

    def options(op, cls):
        o = cls()
        t = op.BuiltinOptions()
        o.Init(t.Bytes, t.Pos)
        return o

    T = tfl.TensorType
    layers: list[QLayer] = []
    cur = int(sg.Inputs(0))
    input_scale = input_zp = None
    dropped = []
    n_ops = sg.OperatorsLength()
    for i in range(n_ops):
        op = sg.Operators(i)
        kind = opname(op)
        ins = [int(v) for v in op.InputsAsNumpy()]
        out = int(op.OutputsAsNumpy()[0])
        if tensor(out).Type() == T.INT32:
            continue  # shape arithmetic (Keras Flatten -> SHAPE/STRIDED_SLICE/PACK), not on the data path
        if ins[0] != cur:
            raise UnsupportedModel(f"op {i} ({kind}) does not consume the previous output: graph is not sequential")
        tin, tout = tensor(ins[0]), tensor(out)

        if kind == "QUANTIZE" and i == 0:
            if tout.Type() != T.INT8:
                raise UnsupportedModel("input QUANTIZE must produce int8")
            cur = out
            continue
        if kind in ("DEQUANTIZE", "SOFTMAX") and i >= n_ops - 2:
            dropped.append(kind)
            cur = out
            continue
        if tin.Type() != T.INT8 or tout.Type() != T.INT8:
            raise UnsupportedModel(f"op {i} ({kind}) is not int8 (full-integer quantization required)")
        s_in, z_in = qparams(tin)
        s_out, z_out = qparams(tout)
        if input_scale is None:
            input_scale, input_zp = float(s_in[0]), int(z_in[0])
        in_shape, out_shape = _hwc(tin.ShapeAsNumpy()), _hwc(tout.ShapeAsNumpy())
        common = dict(in_shape=in_shape, out_shape=out_shape, in_zp=int(z_in[0]), out_zp=int(z_out[0]),
                      in_scale=float(s_in[0]), out_scale=float(s_out[0]))

        if kind in ("CONV_2D", "DEPTHWISE_CONV_2D", "FULLY_CONNECTED"):
            tw = tensor(ins[1])
            w = data(tw, np.int8)
            s_w, z_w = qparams(tw)
            if np.any(z_w != 0):
                raise UnsupportedModel("weights must be symmetric (zero point 0)")
            bias = data(tensor(ins[2]), np.int32).reshape(-1) if len(ins) > 2 and ins[2] >= 0 else None
            mults, shifts = zip(*(quantize_multiplier(float(s_in[0] * sw / s_out[0])) for sw in s_w))
            if kind == "FULLY_CONNECTED":
                o = options(op, tfl.FullyConnectedOptions)
                act = o.FusedActivationFunction()
                # TFLite's FULLY_CONNECTED requantizes with single rounding
                # (verified bit-exact against the reference interpreter).
                q = QLayer(op="dense", weights=w.reshape(-1), rounding=fc_rounding, **common)
            elif kind == "CONV_2D":
                o = options(op, tfl.Conv2DOptions)
                if o.DilationHFactor() != 1 or o.DilationWFactor() != 1:
                    raise UnsupportedModel("dilated convolutions are not supported")
                act = o.FusedActivationFunction()
                kh, kw = int(w.shape[1]), int(w.shape[2])
                sh, sw_ = o.StrideH(), o.StrideW()
                q = QLayer(op="conv2d", kernel=(kh, kw), stride=(sh, sw_),
                           pad=(_pad(o.Padding(), in_shape[0], out_shape[0], kh, sh, tfl),
                                _pad(o.Padding(), in_shape[1], out_shape[1], kw, sw_, tfl)),
                           weights=w.reshape(-1), **common)
            else:
                o = options(op, tfl.DepthwiseConv2DOptions)
                if o.DilationHFactor() != 1 or o.DilationWFactor() != 1:
                    raise UnsupportedModel("dilated convolutions are not supported")
                act = o.FusedActivationFunction()
                kh, kw = int(w.shape[1]), int(w.shape[2])
                sh, sw_ = o.StrideH(), o.StrideW()
                q = QLayer(op="dwconv2d", kernel=(kh, kw), stride=(sh, sw_),
                           pad=(_pad(o.Padding(), in_shape[0], out_shape[0], kh, sh, tfl),
                                _pad(o.Padding(), in_shape[1], out_shape[1], kw, sw_, tfl)),
                           weights=w.reshape(-1), **common)
            q.bias = bias
            q.mult = np.array(mults, dtype=np.int32)
            q.shift = np.array(shifts, dtype=np.int8)
            q.act_min, q.act_max = _act_range(act, float(s_out[0]), int(z_out[0]), tfl)
            layers.append(q)
        elif kind in ("MAX_POOL_2D", "AVERAGE_POOL_2D"):
            if not (np.allclose(s_in, s_out) and np.array_equal(z_in, z_out)):
                raise UnsupportedModel("pooling with different input/output quantization")
            o = options(op, tfl.Pool2DOptions)
            kh, kw, sh, sw_ = o.FilterHeight(), o.FilterWidth(), o.StrideH(), o.StrideW()
            amin, amax = _act_range(o.FusedActivationFunction(), float(s_out[0]), int(z_out[0]), tfl)
            layers.append(QLayer(op="maxpool2d" if kind == "MAX_POOL_2D" else "avgpool2d", kernel=(kh, kw),
                                 stride=(sh, sw_),
                                 pad=(_pad(o.Padding(), in_shape[0], out_shape[0], kh, sh, tfl),
                                      _pad(o.Padding(), in_shape[1], out_shape[1], kw, sw_, tfl)),
                                 act_min=amin, act_max=amax, **common))
        elif kind in ("RESHAPE", "SQUEEZE"):
            if not (np.allclose(s_in, s_out) and np.array_equal(z_in, z_out)):
                raise UnsupportedModel("reshape with requantization")
            layers.append(QLayer(op="reshape", **common))
        else:
            raise UnsupportedModel(f"operator {kind} is not supported (op {i})")
        cur = out

    if not layers:
        raise UnsupportedModel("no supported layers found")
    last = layers[-1]
    qm = QModel(name=name, layers=layers, input_scale=input_scale, input_zp=input_zp,
                output_scale=last.out_scale, output_zp=last.out_zp,
                description=description or f"imported from {path}",
                meta={"source": "tflite", "dropped_ops": dropped})
    rng = np.random.default_rng(seed)
    qm.test_inputs = rng.integers(-128, 128, (n_tests, qm.in_size), dtype=np.int16).astype(np.int8)
    qm.test_outputs = reference.run_batch(qm, qm.test_inputs)
    return qm


def verify_with_interpreter(path: str, qm: QModel, n: int = 32, seed: int = 1) -> int:
    """Compare against the TFLite interpreter (needs tensorflow or ai-edge-litert).
    Returns the number of mismatching outputs. Compares before a dropped SOFTMAX."""
    try:
        from ai_edge_litert.interpreter import Interpreter, OpResolverType
    except ImportError:
        import tensorflow as tf

        Interpreter = tf.lite.Interpreter
        OpResolverType = tf.lite.experimental.OpResolverType
    # Reference kernels = what TFLite-Micro runs on microcontrollers (no XNNPACK).
    interp = Interpreter(model_path=path, experimental_preserve_all_tensors=True,
                         experimental_op_resolver_type=OpResolverType.BUILTIN_REF)
    interp.allocate_tensors()
    inp = interp.get_input_details()[0]
    # Find the int8 tensor that corresponds to our last layer: the output of the
    # last non-dropped op.
    ops = interp._get_ops_details()
    keep = [o for o in ops if o["op_name"] not in ("DEQUANTIZE", "SOFTMAX")]
    out_idx = keep[-1]["outputs"][0]
    rng = np.random.default_rng(seed)
    bad = 0
    for _ in range(n):
        x = rng.integers(-128, 128, qm.in_size, dtype=np.int16).astype(np.int8)
        if inp["dtype"] == np.int8:
            feed = x.reshape(inp["shape"])
        else:  # float input with QUANTIZE op
            feed = ((x.astype(np.float32) - qm.input_zp) * qm.input_scale).reshape(inp["shape"]).astype(np.float32)
        interp.set_tensor(inp["index"], feed)
        interp.invoke()
        want = interp.get_tensor(out_idx).reshape(-1)
        got = reference.run_model(qm, x)
        bad += int(not np.array_equal(got, want))
    return bad
