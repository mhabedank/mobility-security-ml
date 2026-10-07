"""TFLite import: bit-exact with outputs recorded from the TFLite reference
interpreter (tests/unit/data/*.expected.npz, generated with TensorFlow 2.21)."""
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from hilbench.config import REPO_ROOT
from hilbench.device import Device
from hilbench.ml.codegen import write_zoo_sources
from hilbench.ml.reference import run_batch
from hilbench.transport import ProcessTransport

pytest.importorskip("tflite")
from hilbench.ml.tflite_import import UnsupportedModel, load_tflite  # noqa: E402

DATA = Path(__file__).parent / "data"
MODELS = ["mlp", "mlp_float_io", "cnn", "cnn1d_samepool"]


@pytest.mark.parametrize("name", MODELS)
def test_import_matches_tflite_interpreter(name):
    qm = load_tflite(str(DATA / f"{name}.tflite"), name)
    exp = np.load(DATA / f"{name}.expected.npz")
    got = run_batch(qm, exp["inputs"])
    assert np.array_equal(got, exp["outputs"].astype(np.int8))


def test_import_layer_structure():
    qm = load_tflite(str(DATA / "cnn.tflite"), "cnn")
    assert [l.op for l in qm.layers] == ["conv2d", "dwconv2d", "conv2d", "maxpool2d", "conv2d",
                                        "avgpool2d", "reshape", "dense"]
    assert qm.layers[-1].rounding == "single" and qm.layers[0].rounding == "double"
    assert load_tflite(str(DATA / "mlp.tflite"), "m").meta["dropped_ops"] == ["SOFTMAX"]


def test_rejects_garbage(tmp_path):
    p = tmp_path / "x.tflite"
    p.write_bytes(b"\x00" * 64)
    with pytest.raises(UnsupportedModel, match="not a TFLite"):
        load_tflite(str(p), "x")


def test_imported_model_runs_bit_exact_in_firmware(tmp_path):
    """import -> C codegen -> firmware (simulator) -> INFER over the protocol."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler")
    qms = [load_tflite(str(DATA / f"{n}.tflite"), n) for n in ("cnn", "mlp")]
    write_zoo_sources(qms, tmp_path)
    fw = REPO_ROOT / "firmware"
    exe = tmp_path / "sim"
    srcs = [fw / "lib/microinfer/src/microinfer.c", fw / "lib/benchapp/src/benchapp.c", tmp_path / "model_zoo.c",
            fw / "native/hal_native.c", fw / "native/main.c"]
    subprocess.run([cc, "-std=c99", "-O2", "-Wall", "-Werror", f"-I{tmp_path}", f"-I{fw}/lib/microinfer/src",
                    f"-I{fw}/lib/benchapp/src", *map(str, srcs), "-o", str(exe)], check=True)
    with ProcessTransport([str(exe)]) as t:
        dev = Device(t)
        dev.wait_ready(5)
        for qm in qms:
            exp = np.load(DATA / f"{qm.name}.expected.npz")
            assert dev.selftest(qm.name)["passed"] == len(qm.test_inputs)
            for x, y in zip(exp["inputs"][:16], exp["outputs"][:16]):
                out, _ = dev.infer(qm.name, x)
                assert np.array_equal(out, y.astype(np.int8))
