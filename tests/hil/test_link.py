"""Serial link and protocol basics - the first thing to check on a new board."""
import time

import numpy as np
import pytest

import hilbench
from hilbench.device import DeviceError


def test_ping(dut):
    r = dut.device.ping()
    assert r["pong"] is True


def test_info_identity(dut):
    info = dut.device.info()
    assert info["target"] == dut.target.name
    assert info["proto"] == 1
    assert info["fw"] == hilbench.__version__, "firmware and host bench versions differ"
    assert info["models"] >= 1
    assert info["engine"].startswith("microinfer")
    if dut.target.transport != "process":
        assert info["cpu_mhz"] > 0, "firmware could not determine the CPU clock"


@pytest.mark.parametrize("size", [1, 16, 128, 400])
def test_echo_payload_integrity(dut, size):
    rng = np.random.default_rng(size)
    info = dut.info
    size = min(size, (info["line_max"] - 32) // 2)
    data = rng.integers(0, 256, size, dtype=np.uint8).tobytes()
    r = dut.device.echo(data)
    assert r["len"] == len(data)


def test_unknown_command_is_rejected(dut):
    with pytest.raises(DeviceError, match="unknown command"):
        dut.device.request("DEFINITELY_NOT_A_COMMAND")
    dut.device.ping()  # still alive


def test_overlong_line_is_rejected(dut):
    too_long = "ECHO " + "00" * dut.info["line_max"]
    dut.device.transport.write((too_long + "\n").encode())
    # The id is never parsed from an overlong line, so the error carries id 0.
    frame = dut.device.expect(lambda f: f.get("id") == 0, timeout=5)
    assert frame["ok"] is False and frame["err"] == "line too long"
    dut.device.ping()


def test_round_trip_latency(dut):
    n = 20 if dut.quick else 100
    t0 = time.perf_counter()
    for _ in range(n):
        dut.device.ping()
    rtt_ms = (time.perf_counter() - t0) / n * 1000
    dut.record("link", rtt_ms=round(rtt_ms, 3))
    assert rtt_ms < 250
