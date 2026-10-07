"""The C fixed-point code must equal the Python reference for all inputs."""
import shutil
import subprocess

import numpy as np
import pytest

from hilbench.config import REPO_ROOT
from hilbench.ml.quant import multiply_by_quantized_multiplier

HARNESS = r"""
#include <stdio.h>
#include "microinfer.h"
int main(void) {
    long x, m; int s;
    while (scanf("%ld %ld %d", &x, &m, &s) == 3)
        printf("%ld\n", (long)mi_multiply_by_quantized_multiplier((int32_t)x, (int32_t)m, s));
    return 0;
}
"""


@pytest.fixture(scope="module")
def mbqm_exe(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cc:
        pytest.skip("no C compiler")
    d = tmp_path_factory.mktemp("c")
    (d / "h.c").write_text(HARNESS)
    exe = d / "h"
    src = REPO_ROOT / "firmware" / "lib" / "microinfer" / "src"
    subprocess.run([cc, "-std=c99", "-O2", "-Wall", "-Werror", f"-I{src}", str(d / "h.c"),
                    str(src / "microinfer.c"), "-o", str(exe)], check=True)
    return exe


def test_c_requantization_matches_python(mbqm_exe):
    rng = np.random.default_rng(42)
    n = 5000
    xs = np.concatenate([rng.integers(-(1 << 31), (1 << 31) - 1, n // 2),
                         rng.integers(-5000, 5000, n // 2), [0, -1, 1, (1 << 31) - 1, -(1 << 31)]])
    ms = rng.integers(1 << 30, (1 << 31) - 1, len(xs))
    ss = rng.integers(-31, 1, len(xs))
    inp = "\n".join(f"{x} {m} {s}" for x, m, s in zip(xs, ms, ss))
    out = subprocess.run([str(mbqm_exe)], input=inp, capture_output=True, text=True, check=True).stdout
    got = [int(v) for v in out.split()]
    assert got == multiply_by_quantized_multiplier(xs, ms, ss).tolist()


SINGLE = HARNESS.replace("mi_multiply_by_quantized_multiplier(", "mi_multiply_by_quantized_multiplier_single(")


def test_c_single_rounding_matches_python(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler")
    from hilbench.ml.quant import multiply_by_quantized_multiplier_single

    (tmp_path / "s.c").write_text(SINGLE)
    src = REPO_ROOT / "firmware" / "lib" / "microinfer" / "src"
    subprocess.run([cc, "-std=c99", "-O2", f"-I{src}", str(tmp_path / "s.c"), str(src / "microinfer.c"),
                    "-o", str(tmp_path / "s")], check=True)
    rng = np.random.default_rng(3)
    xs = rng.integers(-(1 << 31), (1 << 31) - 1, 3000)
    ms = rng.integers(1 << 30, (1 << 31) - 1, 3000)
    ss = rng.integers(-31, 1, 3000)
    out = subprocess.run([str(tmp_path / "s")], input="\n".join(f"{a} {b} {c}" for a, b, c in zip(xs, ms, ss)),
                         capture_output=True, text=True, check=True).stdout
    assert [int(v) for v in out.split()] == multiply_by_quantized_multiplier_single(xs, ms, ss).tolist()
