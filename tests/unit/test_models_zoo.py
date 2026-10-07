import numpy as np
import pytest

from hilbench.config import REPO_ROOT
from hilbench.ml.codegen import zoo_sources
from hilbench.ml.quant import dequantize, quantize
from hilbench.ml.reference import run_batch
from hilbench.ml.zoo import load_eval, load_zoo

ZOO = load_zoo()


def test_firmware_sources_match_zoo():
    """firmware/lib/modelzoo is generated from models/zoo - regenerate with `hilbench zoo --codegen-only`."""
    h, c = zoo_sources(list(ZOO.values()))
    d = REPO_ROOT / "firmware" / "lib" / "modelzoo" / "src"
    assert (d / "model_zoo.h").read_text() == h
    assert (d / "model_zoo.c").read_text() == c


@pytest.mark.parametrize("name", list(ZOO))
def test_golden_vectors_reproducible(name):
    m = ZOO[name]
    assert np.array_equal(run_batch(m, m.test_inputs), m.test_outputs)


@pytest.mark.parametrize("name", list(ZOO))
def test_model_roundtrip(tmp_path, name):
    m = ZOO[name]
    m.save(tmp_path / "m.npz")
    m2 = type(m).load(tmp_path / "m.npz")
    assert m2.crc32() == m.crc32()
    assert m2.summary() == m.summary()


def test_can_ids_accuracy_on_eval_set():
    m = ZOO["can_ids_mlp"]
    ev = load_eval("can_ids_mlp")
    acc = (run_batch(m, ev["inputs"]).argmax(1) == ev["labels"]).mean()
    assert acc > 0.97


def test_int8_close_to_float_for_autoencoder():
    m = ZOO["sensor_ae"]
    ev = load_eval("sensor_ae")
    x = ev["targets"][:64]
    out = dequantize(run_batch(m, quantize(x, m.input_scale, m.input_zp)), m.output_scale, m.output_zp)
    assert np.abs(out - x).mean() < 0.1
