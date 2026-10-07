"""Host side of the bench protocol (see docs/protocol.md)."""
from __future__ import annotations

import json
import time
import zlib
from typing import Callable

import numpy as np

from .transport import Transport


class DeviceError(RuntimeError):
    """The device answered with ok=false."""


class DeviceTimeout(TimeoutError):
    pass


class DeviceResetDetected(RuntimeError):
    """A boot event arrived while waiting for a response: the DUT crashed or
    was reset (watchdog, exception, brown-out...)."""

    def __init__(self, msg: str, boot_event: dict, log_tail: list[str]):
        super().__init__(msg)
        self.boot_event = boot_event
        self.log_tail = log_tail


class Device:
    def __init__(self, transport: Transport, timeout: float = 10.0,
                 log: Callable[[str], None] | None = None):
        self.transport = transport
        self.timeout = timeout
        self._log = log or (lambda line: None)
        self._buf = bytearray()
        self._next_id = 1
        self.boot_events: list[dict] = []
        self.log_tail: list[str] = []
        self.unexpected_resets = 0

    # ---- low level -------------------------------------------------------
    def _lines(self, deadline: float):
        """Yield complete text lines until the deadline."""
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                raw = bytes(self._buf[:nl])
                del self._buf[:nl + 1]
                yield raw.decode("latin-1").rstrip("\r")
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self._buf.extend(self.transport.read(min(remaining, 0.25)))

    def _handle_line(self, line: str) -> dict | None:
        idx = line.find("@{")
        if idx < 0:
            if line.strip():
                self._log(line)
                self.log_tail = (self.log_tail + [line])[-40:]
            return None
        if idx > 0:
            self._log(line[:idx])  # boot noise glued in front of the frame
        try:
            obj = json.loads(line[idx + 1:])
        except json.JSONDecodeError:
            self._log(f"[corrupt frame] {line}")
            self.log_tail = (self.log_tail + [line])[-40:]
            return None
        self._log(line[idx:])
        if obj.get("evt") == "boot":
            self.boot_events.append(obj)
        return obj

    def flush_input(self, quiet_s: float = 0.05) -> None:
        deadline = time.monotonic() + quiet_s
        for line in self._lines(deadline):
            self._handle_line(line)

    def expect(self, predicate: Callable[[dict], bool], timeout: float = 5.0) -> dict:
        """Wait for an unsolicited frame (event, id-less error...) matching `predicate`."""
        deadline = time.monotonic() + timeout
        for text in self._lines(deadline):
            obj = self._handle_line(text)
            if obj is not None and predicate(obj):
                return obj
        raise DeviceTimeout(f"expected frame not received within {timeout:.1f}s")

    def request(self, command: str, *args, timeout: float | None = None,
                allow_reset: bool = False) -> dict:
        rid = self._next_id
        self._next_id += 1
        line = f"#{rid} {command}" + "".join(f" {a}" for a in args)
        self._log(">> " + (line if len(line) <= 120 else line[:117] + "..."))
        self.transport.write((line + "\n").encode())
        deadline = time.monotonic() + (timeout or self.timeout)
        for text in self._lines(deadline):
            obj = self._handle_line(text)
            if obj is None:
                continue
            if obj.get("evt") == "boot" and not allow_reset:
                self.unexpected_resets += 1
                raise DeviceResetDetected(
                    f"device rebooted while executing {command} "
                    f"(reset_reason={obj.get('reset_reason')})", obj, list(self.log_tail))
            if obj.get("id") == rid:
                if not obj.get("ok"):
                    raise DeviceError(f"{command}: {obj.get('err', 'error')}")
                return obj
        raise DeviceTimeout(f"no response to {command} within {timeout or self.timeout:.1f}s")

    # ---- lifecycle -------------------------------------------------------
    def wait_ready(self, timeout: float = 8.0, poll: float = 0.4) -> dict:
        """Poll PING until the firmware answers (works even if the boot banner
        was lost, e.g. on native USB where the port opens late)."""
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self.request("PING", timeout=min(poll, max(deadline - time.monotonic(), 0.05)),
                                    allow_reset=True)
            except (DeviceTimeout, DeviceError) as e:
                last = e
            # discard partial garbage between attempts
        raise DeviceTimeout(f"device not ready after {timeout:.1f}s ({last})")

    # ---- commands --------------------------------------------------------
    def ping(self) -> dict:
        return self.request("PING")

    def info(self) -> dict:
        return self.request("INFO")

    def models(self) -> list[dict]:
        return self.request("MODELS")["models"]

    def infer(self, model: str | int, data: np.ndarray | bytes, timeout: float | None = None):
        raw = bytes(np.asarray(data, dtype=np.int8).tobytes()) if not isinstance(data, bytes) else data
        r = self.request("INFER", model, raw.hex(), timeout=timeout)
        expected_crc = zlib.crc32(raw) & 0xFFFFFFFF
        if int(r["in_crc"], 16) != expected_crc:
            raise DeviceError(f"input corrupted on the link (crc {r['in_crc']} != {expected_crc:08x})")
        out = np.frombuffer(bytes.fromhex(r["out"]), dtype=np.int8)
        return out, r

    def bench(self, model: str | int, n: int = 10, warmup: int = 1, timeout: float | None = None) -> dict:
        return self.request("BENCH", model, n, warmup, timeout=timeout or max(self.timeout, 60.0))

    def selftest(self, model: str | int, timeout: float | None = None) -> dict:
        return self.request("SELFTEST", model, timeout=timeout or max(self.timeout, 60.0))

    def verify(self, model: str | int) -> dict:
        return self.request("VERIFY", model, timeout=max(self.timeout, 20.0))

    def mem(self) -> dict:
        return self.request("MEM")

    def echo(self, data: bytes) -> dict:
        r = self.request("ECHO", data.hex())
        if bytes.fromhex(r["data"]) != data:
            raise DeviceError("echo mismatch")
        return r

    def soft_reset(self) -> None:
        self.request("RESET", allow_reset=True)
