"""Run ESP32 firmware (ESP32-S3/-C3 with ESP-IDF >= 5) in Espressif's QEMU as a virtual bench board.

The emulator's UART is exposed on a TCP port, so the board is just
`port: socket://localhost:5555` in boards.yaml and the normal harness works:

    python -m hilbench.qemu start build/fw/esp32 --port 5555   # "flash" + power on
    python -m hilbench.qemu stop --port 5555                   # power off

Get QEMU from https://github.com/espressif/qemu/releases (qemu-system-xtensa for
ESP32/S3, qemu-system-riscv32 for ESP32-C3) and put it on PATH or set
$HILBENCH_QEMU_XTENSA / $HILBENCH_QEMU_RISCV32.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .flash import esptool_cmd

MACHINES = {
    "esp32": ("xtensa", "esp32"),
    "esp32s3": ("xtensa", "esp32s3"),
    "esp32c3": ("riscv32", "esp32c3"),
}


def _pidfile(port: int) -> Path:
    return Path(tempfile.gettempdir()) / f"hilbench-qemu-{port}.pid"


def merge_flash(fw_dir: Path, size: str | None = None) -> Path:
    manifest = json.loads((fw_dir / "manifest.json").read_text())
    # QEMU needs an image of exactly the size the bootloader header announces.
    size = size or manifest.get("flash_size") or "4MB"
    chip = manifest.get("mcu") or "esp32"
    out = fw_dir / "qemu_flash.bin"
    args = ["--chip", chip, "merge_bin", "--fill-flash-size", size, "-o", str(out)]
    for img in manifest["flash_images"]:
        args += [img["offset"], str(fw_dir / img["file"])]
    res = subprocess.run(esptool_cmd(*args), capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"esptool merge_bin failed:\n{res.stdout}\n{res.stderr}")
    return out


def stop(port: int) -> None:
    pf = _pidfile(port)
    if not pf.exists():
        return
    try:
        pid = int(pf.read_text())
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            os.kill(pid, 0)
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, ValueError):
        pass
    finally:
        pf.unlink(missing_ok=True)


def start(fw_dir: Path, port: int = 5555, timeout: float = 20.0) -> int:
    stop(port)
    manifest = json.loads((fw_dir / "manifest.json").read_text())
    chip = manifest.get("mcu") or "esp32"
    if chip not in MACHINES:
        raise SystemExit(f"QEMU does not support {chip} (supported: {', '.join(MACHINES)})")
    arch, machine = MACHINES[chip]
    image = merge_flash(fw_dir)
    exe = os.environ.get(f"HILBENCH_QEMU_{arch.upper()}", f"qemu-system-{arch}")
    log = open(fw_dir / "qemu.log", "ab")
    proc = subprocess.Popen(
        [exe, "-nographic", "-machine", machine, "-display", "none",
         "-drive", f"file={image},if=mtd,format=raw",
         "-serial", f"tcp:127.0.0.1:{port},server,nowait"],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    _pidfile(port).write_text(str(proc.pid))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"QEMU exited with {proc.returncode}, see {fw_dir / 'qemu.log'}")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return proc.pid
        except OSError:
            time.sleep(0.2)
    raise SystemExit(f"QEMU did not open port {port} within {timeout:.0f}s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("fw_dir", type=Path)
    p.add_argument("--port", type=int, default=5555)
    p = sub.add_parser("stop")
    p.add_argument("--port", type=int, default=5555)
    args = ap.parse_args(argv)
    if args.cmd == "start":
        pid = start(args.fw_dir, args.port)
        print(f"QEMU running (pid {pid}), UART on socket://localhost:{args.port}")
    else:
        stop(args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
