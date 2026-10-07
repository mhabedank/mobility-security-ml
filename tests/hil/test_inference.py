"""On-device inference must be bit-exact with the host reference for any input."""
import numpy as np
import pytest

from hilbench.ml.quant import dequantize
from hilbench.ml.reference import run_batch, run_model
from hilbench.ml.zoo import load_eval, load_zoo

ZOO = load_zoo()


def _compare(dut, model, inputs):
    mismatches = []
    us = []
    for i, x in enumerate(inputs):
        out, r = dut.device.infer(model.name, x)
        ref = run_model(model, x)
        us.append(r["us"])
        if not np.array_equal(out, ref):
            mismatches.append((i, out.tolist(), ref.tolist()))
    return mismatches, us


def test_random_inputs_bit_exact(dut, model_name):
    dut.require_model(model_name)
    model = ZOO[model_name]
    rng = np.random.default_rng(1234)
    n = 5 if dut.quick else 30
    inputs = rng.integers(-128, 128, (n, model.in_size), dtype=np.int16).astype(np.int8)
    mismatches, us = _compare(dut, model, inputs)
    assert not mismatches, f"{len(mismatches)}/{n} outputs differ, first: {mismatches[0]}"


def test_edge_case_inputs_bit_exact(dut, model_name):
    dut.require_model(model_name)
    model = ZOO[model_name]
    size = model.in_size
    inputs = np.stack([
        np.full(size, -128), np.full(size, 127), np.zeros(size), np.full(size, model.input_zp),
        np.tile([-128, 127], size // 2 + 1)[:size],
    ]).astype(np.int8)
    mismatches, _ = _compare(dut, model, inputs)
    assert not mismatches, f"saturation/rounding differs: {mismatches[0]}"


@pytest.mark.parametrize("name", [n for n in ZOO if load_eval(n) is not None])
def test_evaluation_set_on_device(dut, name):
    """Run the labelled evaluation set on the device and report the task metric."""
    dut.require_model(name)
    model = ZOO[name]
    ev = load_eval(name)
    n = 64 if dut.quick else len(ev["inputs"])
    xs, ys = ev["inputs"][:n], ev["labels"][:n]
    outs = np.stack([dut.device.infer(name, x)[0] for x in xs])
    host = run_batch(model, xs)
    bit_exact = bool(np.array_equal(outs, host))

    if model.meta.get("task") == "classification":
        dev_metric = float((outs.argmax(1) == ys).mean())
        host_metric = float((host.argmax(1) == ys).mean())
        expected = model.meta.get("int8_accuracy")
        if expected is not None and n >= 256:
            assert dev_metric >= expected - 0.05, f"device accuracy {dev_metric:.3f} vs trained {expected:.3f}"
    else:  # anomaly detection via reconstruction error
        targets = ev["targets"][:n]
        thr = model.meta["threshold"]

        def detect(o):
            rec = dequantize(o, model.output_scale, model.output_zp)
            return ((rec - targets) ** 2).mean(1) > thr

        dev_metric = float((detect(outs) == ys.astype(bool)).mean())
        host_metric = float((detect(host) == ys.astype(bool)).mean())
    dut.record("accuracy", model=name, n=n, device_metric=dev_metric, host_metric=host_metric,
               bit_exact=bit_exact)
    assert bit_exact, "device and host int8 results differ on the evaluation set"
