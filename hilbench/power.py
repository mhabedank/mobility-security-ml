"""Power switching and reset strategies for boards on the bench.

Power control (boards.yaml -> `power:`):
  {type: none}
  {type: uhubctl, hub: "1-1", port: 3, off_s: 1.5}      per-port USB power (PPPS hubs)
  {type: command, on: "...", off: "...", off_s: 1.0}     relay board, smart plug, lab PSU...

Reset methods (targets.yaml / boards.yaml -> `reset:`):
  esp_classic   RTS pulse on EN through the usual 2-transistor auto-reset circuit
  esp_usb_jtag  same via the ESP32-S3/C3 USB-Serial/JTAG peripheral (port re-enumerates)
  dtr_pulse     pulse DTR (boards wiring DTR to RESET, e.g. via a 100 nF cap)
  soft          RESET command over the protocol
  power         power-cycle through the power control
  command       run `reset_options.command` (openocd, st-flash reset, nrfjprog...)
  process       restart the simulator process
  none          no reset possible
"""
from __future__ import annotations

import shlex
import subprocess
import time
from typing import Any

from .transport import ProcessTransport, Transport


class PowerError(RuntimeError):
    pass


class PowerControl:
    available = False

    def on(self) -> None:
        pass

    def off(self) -> None:
        pass

    def cycle(self) -> None:
        raise PowerError("no power control configured for this board")


class NoPower(PowerControl):
    pass


def _run(cmd: list[str] | str, timeout: float = 30.0) -> None:
    argv = shlex.split(cmd) if isinstance(cmd, str) else cmd
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise PowerError(f"command not found: {argv[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise PowerError(f"command timed out: {' '.join(argv)}") from e
    if res.returncode != 0:
        raise PowerError(f"`{' '.join(argv)}` failed ({res.returncode}): {res.stderr.strip() or res.stdout.strip()}")


class UhubctlPower(PowerControl):
    available = True

    def __init__(self, hub: str, port: int | str, off_s: float = 1.5, settle_s: float = 0.5,
                 uhubctl: str = "uhubctl", sudo: bool = False):
        self.hub, self.port, self.off_s, self.settle_s = str(hub), str(port), off_s, settle_s
        self.base = (["sudo", "-n"] if sudo else []) + [uhubctl, "-l", self.hub, "-p", self.port]

    def on(self) -> None:
        _run(self.base + ["-a", "on"])
        time.sleep(self.settle_s)

    def off(self) -> None:
        _run(self.base + ["-a", "off"])

    def cycle(self) -> None:
        self.off()
        time.sleep(self.off_s)
        self.on()


class CommandPower(PowerControl):
    available = True

    def __init__(self, on: str, off: str, off_s: float = 1.0, settle_s: float = 0.5):
        self.on_cmd, self.off_cmd, self.off_s, self.settle_s = on, off, off_s, settle_s

    def on(self) -> None:
        _run(self.on_cmd)
        time.sleep(self.settle_s)

    def off(self) -> None:
        _run(self.off_cmd)

    def cycle(self) -> None:
        self.off()
        time.sleep(self.off_s)
        self.on()


def make_power(spec: dict[str, Any] | None) -> PowerControl:
    spec = dict(spec or {})
    kind = spec.pop("type", "none")
    if kind == "none":
        return NoPower()
    if kind == "uhubctl":
        return UhubctlPower(**spec)
    if kind == "command":
        return CommandPower(**spec)
    raise PowerError(f"unknown power type '{kind}'")


def hardware_reset(method: str, transport: Transport, power: PowerControl,
                   options: dict[str, Any] | None = None) -> bool:
    """Reset without help from the firmware. Returns False if `method` needs the
    firmware (soft) or is not possible."""
    options = options or {}
    if method == "esp_classic":
        # DTR deasserted keeps GPIO0 high (normal boot); RTS asserted pulls EN low.
        transport.set_lines(dtr=False, rts=True)
        time.sleep(options.get("pulse_s", 0.1))
        transport.set_lines(rts=False)
        return True
    if method == "esp_usb_jtag":
        transport.set_lines(dtr=False, rts=True)
        time.sleep(options.get("pulse_s", 0.2))
        transport.set_lines(rts=False)
        time.sleep(0.2)
        return True
    if method == "dtr_pulse":
        transport.set_lines(dtr=True)
        time.sleep(options.get("pulse_s", 0.1))
        transport.set_lines(dtr=False)
        return True
    if method == "process":
        if isinstance(transport, ProcessTransport):
            transport.restart()
            return True
        return False
    if method == "power":
        if not power.available:
            return False
        power.cycle()
        return True
    if method == "command":
        cmd = options.get("command")
        if not cmd:
            raise PowerError("reset: command requires reset_options.command")
        _run(cmd)
        return True
    return False
