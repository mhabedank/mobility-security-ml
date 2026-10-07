"""BoardSession: everything needed to get one physical board into a known,
tested state - lock, power, flash, connect, identify, recover.

    with BoardSession(lab, board, firmware) as s:
        s.device.info()
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .config import Board, Lab
from .device import Device, DeviceTimeout
from .discovery import DiscoveryError, resolve_port
from .flash import Firmware, make_flasher
from .lock import BoardLock
from .power import hardware_reset, make_power
from .transport import ProcessTransport, SerialTransport, Transport, TransportError


class SessionError(RuntimeError):
    pass


class BoardSession:
    def __init__(self, lab: Lab, board: Board, firmware: Firmware | None = None, flash: bool = True,
                 log_dir: Path | None = None, lock_timeout: float = 600.0):
        self.lab = lab
        self.board = board
        self.target = board.target
        self.firmware = firmware
        self.do_flash = flash and firmware is not None
        self.power = make_power(board.power)
        self.lock = BoardLock(lab.lock_dir, board.id, lock_timeout)
        self.transport: Transport | None = None
        self.device: Device | None = None
        self.port: str | None = None
        self.info: dict = {}
        self.events: list[str] = []  # human readable history (flash, resets, recoveries)
        self._log_fh = None
        if log_dir:
            log_dir.mkdir(parents=True, exist_ok=True)
            self._log_fh = open(log_dir / f"{board.id}.log", "a", buffering=1)

    # ---- logging ---------------------------------------------------------
    def log(self, line: str) -> None:
        if self._log_fh:
            self._log_fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")

    def note(self, msg: str) -> None:
        self.events.append(msg)
        self.log(f"### {msg}")

    # ---- lifecycle -------------------------------------------------------
    def __enter__(self) -> "BoardSession":
        self.lock.acquire()
        try:
            self.start()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        self.power.on()
        if self.do_flash:
            self.flash()
        self.connect()
        self.identify()

    def close(self) -> None:
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                pass
            self.transport = None
        self.lock.release()
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None

    # ---- steps -----------------------------------------------------------
    def _resolve_port(self, wait_s: float = 0.0) -> str | None:
        if self.target.transport == "process":
            return None
        deadline = time.monotonic() + wait_s
        while True:
            try:
                return resolve_port(self.board)
            except DiscoveryError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)

    def _make_transport(self) -> Transport:
        if self.target.transport == "process":
            if self.firmware is None:
                raise SessionError(f"{self.board.id}: simulator needs a native firmware build")
            exe = self.firmware.dir / self.firmware.manifest["files"]["exe"]
            return ProcessTransport([str(exe)], env=self.board.env)
        retry = 5.0 if self.target.reenumerates else 1.0
        return SerialTransport(self.port, self.board.baudrate, open_retry_s=retry)

    def connect(self, wait_port_s: float = 0.0) -> None:
        if self.transport is not None:
            self.transport.close()
        self.port = self._resolve_port(wait_port_s or (10.0 if self.target.reenumerates else 0.0))
        self.transport = self._make_transport()
        self.transport.open()
        self.device = Device(self.transport, log=self.log)
        try:
            self.device.wait_ready(self.target.boot_timeout_s)
        except (DeviceTimeout, TransportError) as e:
            self.recover(f"not responding after connect: {e}")

    def flash(self) -> None:
        if self.transport is not None:  # free the port for the flasher
            self.transport.close()
            self.transport = None
        port = self._resolve_port(10.0 if self.target.reenumerates else 0.0)
        flasher = make_flasher(self.board, self.lab)
        t0 = time.monotonic()
        out = flasher.flash(port, self.firmware)
        self.log(out[-4000:] if out else "")
        self.note(f"flashed {self.firmware.target} build {self.firmware.build_id:08x} "
                  f"via {self.board.flash_method} in {time.monotonic() - t0:.1f}s")

    def identify(self) -> dict:
        info = self.device.info()
        self.info = info
        if info.get("target") != self.target.name:
            raise SessionError(f"{self.board.id}: firmware reports target '{info.get('target')}', "
                               f"expected '{self.target.name}' - wrong board on this port?")
        if self.target.chip_match and not re.search(self.target.chip_match, info.get("chip", "")):
            raise SessionError(f"{self.board.id}: chip '{info.get('chip')}' does not match "
                               f"/{self.target.chip_match}/ - wrong board on this port?")
        if self.firmware is not None:
            running = int(info.get("build", "0"), 16)
            if running != self.firmware.build_id:
                raise SessionError(
                    f"{self.board.id}: running build {running:08x} != expected {self.firmware.build_id:08x}"
                    + (" (flashing failed?)" if self.do_flash else " (use flashing or --hil-no-build-check)"))
        return info

    # ---- resets & recovery ----------------------------------------------
    def reset(self, method: str | None = None, timeout: float | None = None) -> dict:
        """Reset the board and wait until it answers again. Returns the boot event (may be {})."""
        method = method or self.board.reset_method
        dev = self.device
        n_boot = len(dev.boot_events)
        if method == "soft":
            dev.soft_reset()
        elif not hardware_reset(method, self.transport, self.power, self.board.reset_options):
            raise SessionError(f"{self.board.id}: reset method '{method}' not available")
        self.note(f"reset ({method})")
        # A power cycle drops USB serial devices (and QEMU sockets); native USB
        # devices re-enumerate on any reset.
        if method == "power" or (self.target.reenumerates and method != "process"):
            time.sleep(0.5)
            self.connect(wait_port_s=10.0)
        else:
            self.device.wait_ready(timeout or self.target.boot_timeout_s)
        dev = self.device
        return dev.boot_events[-1] if len(dev.boot_events) > n_boot else {}

    def recover(self, reason: str) -> None:
        """Escalate: hardware reset -> power cycle -> reflash. Raise if all fail."""
        self.note(f"recovering: {reason}")
        steps = []
        if self.board.reset_method not in ("soft", "none"):
            steps.append(("reset", lambda: hardware_reset(self.board.reset_method, self.transport, self.power,
                                                          self.board.reset_options)))
        if self.power.available:
            steps.append(("power-cycle", lambda: (self.power.cycle(), True)[1]))
        if self.firmware is not None and self.board.flash_method != "none":
            steps.append(("reflash", lambda: (self.flash(), True)[1]))
        for name, action in steps:
            try:
                if not action():
                    continue
                if (self.transport is None or self.target.reenumerates
                        or name in ("power-cycle", "reflash")):
                    if self.transport is not None:
                        self.transport.close()
                    self.port = self._resolve_port(10.0 if self.target.reenumerates else 5.0)
                    self.transport = self._make_transport()
                    self.transport.open()
                    self.device = Device(self.transport, log=self.log)
                self.device.wait_ready(self.target.boot_timeout_s)
                self.note(f"recovered by {name}")
                return
            except Exception as e:  # keep escalating
                self.note(f"{name} did not help: {e}")
        raise SessionError(f"{self.board.id}: unresponsive ({reason}); tried {[s[0] for s in steps] or 'nothing'}")
