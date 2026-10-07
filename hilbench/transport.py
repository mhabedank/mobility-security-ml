"""Byte transports between the HIL host and a device under test.

* SerialTransport  - local serial port or any pyserial URL (rfc2217://, socket://)
                     so boards can also hang off a remote Raspberry Pi / ser2net.
* ProcessTransport - the host simulator (firmware built for the PC) on pipes.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time


class TransportError(IOError):
    pass


class Transport:
    name = "transport"

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def read(self, timeout: float) -> bytes:
        """Return available bytes, waiting up to `timeout` for the first one."""
        raise NotImplementedError

    def set_lines(self, dtr: bool | None = None, rts: bool | None = None) -> None:
        """Drive modem control lines (used for ESP auto-reset). No-op by default."""

    @property
    def is_open(self) -> bool:
        raise NotImplementedError

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


class SerialTransport(Transport):
    def __init__(self, port: str, baud: int = 115200, dtr: bool = False, rts: bool = False,
                 open_retry_s: float = 0.0):
        self.port = port
        self.baud = baud
        self._dtr = dtr
        self._rts = rts
        self.open_retry_s = open_retry_s
        self._ser = None
        self.name = port

    def open(self) -> None:
        import serial

        deadline = time.monotonic() + self.open_retry_s
        while True:
            try:
                ser = serial.serial_for_url(self.port, do_not_open=True)
                ser.baudrate = self.baud
                ser.timeout = 0
                ser.write_timeout = 5
                # Set the lines *before* opening: on ESP boards DTR/RTS drive
                # EN/GPIO0 and the default (asserted) can hold the chip in reset.
                try:
                    ser.dtr = self._dtr
                    ser.rts = self._rts
                except (AttributeError, ValueError, OSError):
                    pass
                ser.open()
                self._ser = ser
                return
            except (OSError, ValueError) as e:  # serial.SerialException is an OSError
                if time.monotonic() >= deadline:
                    raise TransportError(f"cannot open {self.port}: {e}") from e
                time.sleep(0.2)

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def write(self, data: bytes) -> None:
        if not self.is_open:
            raise TransportError(f"{self.port} not open")
        try:
            self._ser.write(data)
            self._ser.flush()
        except OSError as e:
            raise TransportError(f"write to {self.port} failed: {e}") from e

    def read(self, timeout: float) -> bytes:
        if not self.is_open:
            raise TransportError(f"{self.port} not open")
        deadline = time.monotonic() + max(timeout, 0)
        try:
            while True:
                n = self._ser.in_waiting
                if n:
                    return self._ser.read(n)
                if time.monotonic() >= deadline:
                    return b""
                time.sleep(0.002)
        except OSError as e:
            raise TransportError(f"read from {self.port} failed: {e}") from e

    def set_lines(self, dtr: bool | None = None, rts: bool | None = None) -> None:
        if dtr is not None:
            self._dtr = dtr
        if rts is not None:
            self._rts = rts
        if self.is_open:
            if dtr is not None:
                self._ser.dtr = dtr
            if rts is not None:
                self._ser.rts = rts

    def set_baud(self, baud: int) -> None:
        self.baud = baud
        if self.is_open:
            self._ser.baudrate = baud


class ProcessTransport(Transport):
    """Runs the simulator binary; stdout/stdin act like the UART."""

    def __init__(self, argv: list[str], env: dict[str, str] | None = None):
        self.argv = argv
        self.env = env or {}
        self.name = f"process:{os.path.basename(argv[0])}"
        self._proc: subprocess.Popen | None = None
        self._buf = bytearray()
        self._cv = threading.Condition()
        self._reader: threading.Thread | None = None

    def open(self) -> None:
        if not os.path.exists(self.argv[0]):
            raise TransportError(f"simulator binary not found: {self.argv[0]} (run `hilbench build -t native`)")
        env = {**os.environ, **self.env}
        self._proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, env=env, bufsize=0)
        self._reader = threading.Thread(target=self._pump, args=(self._proc,), daemon=True)
        self._reader.start()

    def _pump(self, proc: subprocess.Popen) -> None:
        fd = proc.stdout.fileno()
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                chunk = b""
            if not chunk:
                break
            with self._cv:
                self._buf.extend(chunk)
                self._cv.notify_all()

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if self._reader:
            self._reader.join(timeout=2)
        with self._cv:
            self._buf.clear()

    @property
    def is_open(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def returncode(self) -> int | None:
        return None if self._proc is None else self._proc.poll()

    def write(self, data: bytes) -> None:
        if not self.is_open:
            raise TransportError("simulator not running")
        try:
            self._proc.stdin.write(data)
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise TransportError(f"simulator write failed: {e}") from e

    def read(self, timeout: float) -> bytes:
        with self._cv:
            if not self._buf:
                self._cv.wait(timeout=max(timeout, 0))
            data = bytes(self._buf)
            self._buf.clear()
        return data

    def restart(self) -> None:
        """Equivalent of a power cycle."""
        self.close()
        self.open()
