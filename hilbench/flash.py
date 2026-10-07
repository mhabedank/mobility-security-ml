"""Flash firmware images onto boards.

Flashers (target `flasher:` / board `flasher:`):
  esptool     ESP8266/ESP32 family, straight from the build artifacts (no PlatformIO needed)
  platformio  `pio run -t nobuild -t upload` (RP2040, STM32, nRF52, ... anything PIO supports)
  uf2         RP2040/RP2350: 1200-baud touch -> BOOTSEL drive -> copy firmware.uf2
  command     custom command template, e.g.
                "st-flash --reset write {bin} 0x08000000"
                "pyocd flash -t stm32f446re {hex}"
                "openocd -f board/st_nucleo_f4.cfg -c 'program {elf} verify reset exit'"
              placeholders: {port} {bin} {elf} {hex} {uf2} {dir} {python}
  none        nothing to flash (simulator)
"""
from __future__ import annotations

import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Board, Lab


class FlashError(RuntimeError):
    pass


@dataclass
class Firmware:
    target: str
    dir: Path
    manifest: dict = field(default_factory=dict)

    @property
    def build_id(self) -> int:
        return int(str(self.manifest.get("build_id", "0")), 0)

    def file(self, ext: str) -> Path | None:
        name = self.manifest.get("files", {}).get(ext)
        return self.dir / name if name else None

    @classmethod
    def load(cls, lab: Lab, target: str) -> "Firmware":
        d = lab.build_dir / target
        mf = d / "manifest.json"
        if not mf.exists():
            raise FlashError(f"no firmware built for {target} ({mf} missing) - run `hilbench build -t {target}`")
        return cls(target=target, dir=d, manifest=json.loads(mf.read_text()))


def _esptool_major() -> int:
    try:
        import esptool  # noqa: F401

        return int(str(getattr(esptool, "__version__", "4")).split(".")[0])
    except Exception:
        return 4


_V5_TOKENS = {"chip_id", "write_flash", "merge_bin", "read_mac", "erase_flash", "default_reset", "hard_reset",
              "no_reset", "usb_reset", "--flash_mode", "--flash_freq", "--flash_size"}


def esptool_cmd(*args: str) -> list[str]:
    """Build an esptool command line that works with esptool v4 and v5."""
    major = _esptool_major()
    out = [sys.executable, "-m", "esptool"]
    for a in args:
        a = str(a)
        out.append(a.replace("_", "-") if major >= 5 and a in _V5_TOKENS else a)
    return out


def pio_cmd() -> list[str]:
    exe = shutil.which("pio") or shutil.which("platformio")
    if exe:
        return [exe]
    return [sys.executable, "-m", "platformio"]


def _run(argv: list[str], timeout: float, what: str) -> str:
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise FlashError(f"{what}: command not found: {argv[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise FlashError(f"{what}: timed out after {timeout:.0f}s") from e
    out = (res.stdout or "") + (res.stderr or "")
    if res.returncode != 0:
        tail = "\n".join(out.strip().splitlines()[-25:])
        raise FlashError(f"{what} failed (exit {res.returncode}):\n{tail}")
    return out


class Flasher:
    def __init__(self, board: Board, lab: Lab):
        self.board = board
        self.lab = lab
        self.options: dict[str, Any] = board.flash_options

    def command(self, port: str | None, fw: Firmware) -> list[str] | None:
        """The command line that would be executed (for dry-runs/tests)."""
        return None

    def flash(self, port: str | None, fw: Firmware) -> str:
        argv = self.command(port, fw)
        if argv is None:
            return ""
        return _run(argv, float(self.options.get("timeout_s", 180)), f"flashing {self.board.id}")


class NoFlasher(Flasher):
    pass


class EsptoolFlasher(Flasher):
    def command(self, port, fw):
        chip = self.board.target.esptool_chip or "auto"
        images = fw.manifest.get("flash_images") or []
        if not images:
            raise FlashError(f"{fw.target}: manifest has no flash_images (not an ESP build?)")
        argv = ["--chip", chip, "--port", port, "--baud", str(self.options.get("baud", 460800)),
                "--before", "default_reset", "--after", "hard_reset", "write_flash", "-z"]
        if fw.manifest.get("flash_mode"):
            argv += ["--flash_mode", fw.manifest["flash_mode"]]
        if fw.manifest.get("flash_freq"):
            argv += ["--flash_freq", fw.manifest["flash_freq"]]
        for img in images:
            argv += [img["offset"], str(fw.dir / img["file"])]
        return esptool_cmd(*argv)


class PlatformioFlasher(Flasher):
    def command(self, port, fw):
        env = self.board.target.pio_env
        if not env:
            raise FlashError(f"target {self.board.target.name} has no pio_env")
        argv = pio_cmd() + ["run", "-d", str(self.lab.firmware_dir), "-e", env, "-t", "nobuild", "-t", "upload"]
        if port:
            argv += ["--upload-port", port]
        return argv


class CommandFlasher(Flasher):
    def command(self, port, fw):
        tmpl = self.options.get("command")
        if not tmpl:
            raise FlashError(f"{self.board.id}: flasher 'command' needs flasher_options.command")
        files = {ext: str(fw.file(ext) or "") for ext in ("bin", "elf", "hex", "uf2")}
        return shlex.split(tmpl.format(port=port or "", dir=str(fw.dir), python=sys.executable, **files))


class Uf2Flasher(Flasher):
    """RP2040/RP2350 without picotool: reboot into BOOTSEL and copy the UF2."""

    DEFAULT_GLOBS = ["/media/*/RPI-RP2*", "/media/*/RP2350*", "/run/media/*/RPI-RP2*",
                     "/run/media/*/RP2350*", "/Volumes/RPI-RP2*", "/Volumes/RP2350*", "/mnt/RPI-RP2*"]

    def _find_drive(self) -> str | None:
        patterns = self.options.get("mount_globs") or self.DEFAULT_GLOBS
        for pat in patterns:
            for d in glob.glob(pat):
                if os.path.exists(os.path.join(d, "INFO_UF2.TXT")):
                    return d
        return None

    def flash(self, port, fw):
        uf2 = fw.file("uf2")
        if not uf2 or not uf2.exists():
            raise FlashError(f"{fw.target}: no .uf2 in build artifacts")
        drive = self._find_drive()
        if drive is None and port:
            import serial

            try:  # the arduino-pico core reboots into BOOTSEL on a 1200 baud open/close
                serial.Serial(port, 1200).close()
            except (OSError, ValueError):
                pass
            deadline = time.monotonic() + float(self.options.get("mount_timeout_s", 20))
            while drive is None and time.monotonic() < deadline:
                time.sleep(0.5)
                drive = self._find_drive()
        if drive is None:
            raise FlashError("UF2 drive (RPI-RP2/RP2350) not found - is it auto-mounted? "
                             "set flasher_options.mount_globs")
        shutil.copyfile(uf2, os.path.join(drive, uf2.name))
        try:
            os.sync()
        except AttributeError:
            pass
        return f"copied {uf2.name} to {drive}"


FLASHERS = {
    "none": NoFlasher,
    "esptool": EsptoolFlasher,
    "platformio": PlatformioFlasher,
    "command": CommandFlasher,
    "uf2": Uf2Flasher,
}


def make_flasher(board: Board, lab: Lab) -> Flasher:
    try:
        return FLASHERS[board.flash_method](board, lab)
    except KeyError as e:
        raise FlashError(f"{board.id}: unknown flasher '{board.flash_method}'") from e
