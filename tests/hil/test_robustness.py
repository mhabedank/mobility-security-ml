"""Resets, recovery and long-running stability."""
import time

import numpy as np
import pytest

from hilbench.ml.reference import run_model
from hilbench.ml.zoo import load_zoo


@pytest.mark.destructive
def test_soft_reset_and_recover(dut):
    boot = dut.session.reset("soft")
    info = dut.device.info()
    assert info["uptime_ms"] < 60000
    if boot:
        assert boot["target"] == dut.target.name
    dut.session.identify()


@pytest.mark.destructive
def test_hardware_reset(dut):
    method = dut.board.reset_method
    if method in ("soft", "none"):
        pytest.skip(f"no hardware reset configured (reset: {method})")
    dut.session.reset(method)
    assert dut.device.info()["uptime_ms"] < 60000
    dut.session.identify()


@pytest.mark.slow
def test_soak_no_unexpected_reboot(dut):
    """Hammer the device with inferences; any watchdog/exception reboot fails the test."""
    duration = 10 if dut.quick else 60
    zoo = load_zoo()
    names = [n for n in dut.models() if n in zoo]
    rng = np.random.default_rng(7)
    uptime0 = dut.device.ping()["uptime_ms"]
    t_end = time.monotonic() + duration
    count = 0
    while time.monotonic() < t_end:
        name = names[count % len(names)]
        x = rng.integers(-128, 128, zoo[name].in_size, dtype=np.int16).astype(np.int8)
        out, _ = dut.device.infer(name, x)  # raises DeviceResetDetected on a reboot
        assert np.array_equal(out, run_model(zoo[name], x))
        count += 1
    uptime1 = dut.device.ping()["uptime_ms"]
    assert uptime1 > uptime0, "uptime went backwards: silent reboot"
    dut.record("soak", inferences=count, seconds=duration)
