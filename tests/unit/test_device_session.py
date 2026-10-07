"""Harness behaviour against the simulator, including injected faults."""
import json
from dataclasses import replace

import numpy as np
import pytest

from hilbench.device import Device, DeviceError, DeviceResetDetected, DeviceTimeout
from hilbench.flash import Firmware
from hilbench.ml.reference import run_model
from hilbench.ml.zoo import load_zoo
from hilbench.results import Recorder, compare_to_baseline, render_markdown, summarize, write_summary
from hilbench.session import BoardSession, SessionError
from hilbench.transport import Transport


class FakeTransport(Transport):
    def __init__(self, script):
        self.script = list(script)  # list of bytes to deliver, one chunk per read
        self.sent = []

    def open(self):
        pass

    def close(self):
        pass

    @property
    def is_open(self):
        return True

    def write(self, data):
        self.sent.append(data)

    def read(self, timeout):
        return self.script.pop(0) if self.script else b""


def test_device_parses_noise_and_frames():
    t = FakeTransport([b"\xff\x00garbage\r\n", b'junk@{"id":1,"ok":true,"pong":tr', b'ue}\n'])
    d = Device(t, timeout=0.5)
    assert d.ping()["pong"] is True
    assert t.sent == [b"#1 PING\n"]
    assert any("garbage" in line for line in d.log_tail)


def test_device_detects_reboot():
    t = FakeTransport([b"Exception (28):\r\nepc1=0x4020\r\n", b'@{"evt":"boot","reset_reason":"Exception"}\n'])
    d = Device(t, timeout=0.5)
    with pytest.raises(DeviceResetDetected) as ei:
        d.info()
    assert ei.value.boot_event["reset_reason"] == "Exception"
    assert any("epc1" in line for line in ei.value.log_tail)


def test_device_error_and_timeout():
    d = Device(FakeTransport([b'@{"id":1,"ok":false,"err":"unknown model"}\n']), timeout=0.3)
    with pytest.raises(DeviceError, match="unknown model"):
        d.selftest("nope")
    with pytest.raises(DeviceTimeout):
        Device(FakeTransport([]), timeout=0.2).ping()


def test_infer_checks_input_crc():
    d = Device(FakeTransport([b'@{"id":1,"ok":true,"out":"00","us":1,"cycles":0,"in_crc":"00000000"}\n']))
    with pytest.raises(DeviceError, match="corrupted"):
        d.infer("m", np.zeros(4, np.int8))


def _session(sim_lab, env=None, **kw):
    lab, fw = sim_lab
    board = replace(lab.board("sim"), env=env or {})
    return BoardSession(lab, board, fw, **kw)


def test_session_bringup_and_inference(sim_lab, tmp_path):
    zoo = load_zoo()
    with _session(sim_lab, log_dir=tmp_path) as s:
        assert s.info["build"] == "1234abcd"
        x = np.arange(32, dtype=np.int8)
        out, _ = s.device.infer("can_ids_mlp", x)
        assert np.array_equal(out, run_model(zoo["can_ids_mlp"], x))
    assert "INFER can_ids_mlp" in (tmp_path / "sim.log").read_text()


def test_session_detects_wrong_build(sim_lab):
    lab, fw = sim_lab
    other = Firmware(fw.target, fw.dir, {**fw.manifest, "build_id": "0xdeadbeef"})
    s = BoardSession(lab, lab.board("sim"), other)
    with pytest.raises(SessionError, match="running build 1234abcd != expected deadbeef"):
        s.__enter__()
    s.close()


def test_session_detects_wrong_target(sim_lab):
    lab, fw = sim_lab
    board = replace(lab.board("sim"), target=replace(lab.targets["native"], name="esp32"))
    with pytest.raises(SessionError, match="wrong board"):
        BoardSession(lab, board, fw).__enter__()


def test_crash_is_reported_with_serial_log(sim_lab):
    with _session(sim_lab, env={"HIL_SIM_CRASH_AFTER_LINES": "4"}) as s:  # PING+INFO used by bring-up
        s.device.ping()
        with pytest.raises(DeviceResetDetected) as ei:
            s.device.selftest("kws_dscnn")
        assert ei.value.boot_event["reset_reason"] == "watchdog"
        assert any("Soft WDT reset" in line for line in ei.value.log_tail)
        assert s.device.ping()["pong"]  # rebooted firmware answers again


def test_hang_is_recovered_by_reset(sim_lab):
    with _session(sim_lab, env={"HIL_SIM_HANG_AFTER_LINES": "3"}) as s:
        s.device.timeout = 0.5
        with pytest.raises(DeviceTimeout):
            s.device.ping()
        s.recover("test hang")
        assert s.device.ping()["pong"]
        assert any("recovered by reset" in e for e in s.events)


def test_soft_and_process_reset(sim_lab):
    with _session(sim_lab) as s:
        boot = s.reset("soft")
        assert boot["reset_reason"] == "software"
        s.reset("process")
        assert s.device.info()["inferences"] == 0


def test_results_summary_and_baseline(tmp_path):
    rec = Recorder(tmp_path)
    rec.record("board", "b1", target="esp32", chip="ESP32-D0WD", cpu_mhz=240, build="01")
    rec.record("bench", "b1", model="m", us_avg=100, us_min=90, us_max=110, cyc_avg=24000, macs=1000, n=5)
    rec.record("test", "b1", nodeid="t::a", outcome="passed")
    rec.record("test", "b1", nodeid="t::b", outcome="failed", message="AssertionError: boom")
    s = write_summary(tmp_path)
    assert s["tests"]["b1"] == {"passed": 1, "failed": 1}
    md = render_markdown(s)
    assert "| m | 100 µs |" in md and "24.0" in md and "boom" in md
    base = json.loads((tmp_path / "summary.json").read_text())
    base["perf"]["b1"]["m"]["us_avg"] = 50
    regressions = compare_to_baseline(summarize([{"kind": "bench", "board": "b1", "model": "m", "us_avg": 100}]),
                                      base, 0.25)
    assert regressions == ["b1/m: 100 µs vs baseline 50 µs (+100%)"]
    assert not compare_to_baseline(s, s, 0.0)


def test_power_cycle_reset_reconnects(sim_lab):
    """A power cycle drops the link (USB serial, QEMU socket): the session must reconnect."""
    lab, fw = sim_lab
    board = replace(lab.board("sim"), power={"type": "command", "on": "true", "off": "true", "off_s": 0,
                                             "settle_s": 0})
    with BoardSession(lab, board, fw) as s:
        old = s.transport
        s.reset("power")
        assert s.transport is not old
        assert s.device.ping()["pong"]
        assert s.device.info()["inferences"] == 0
