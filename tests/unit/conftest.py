import shutil
from dataclasses import replace

import pytest

from hilbench.build import build_native
from hilbench.config import load_lab


@pytest.fixture(scope="session")
def sim_lab(tmp_path_factory):
    """Lab with a freshly built simulator in a temp build dir."""
    if not shutil.which("make") or not shutil.which("cc"):
        pytest.skip("needs make + a C compiler")
    lab = load_lab()
    lab = replace(lab, build_dir=tmp_path_factory.mktemp("fw"), lock_dir=tmp_path_factory.mktemp("locks"),
                  results_dir=tmp_path_factory.mktemp("results"))
    fw = build_native(lab, lab.targets["native"], 0x1234ABCD)
    return lab, fw
