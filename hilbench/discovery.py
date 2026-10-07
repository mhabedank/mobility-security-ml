"""Find boards on USB: map inventory entries to serial ports and guess targets.

Matching keys for boards.yaml `match:` (all given keys must match):
  serial_number  USB iSerial (best: unique per adapter - FTDI, CP210x, native USB)
  location       physical USB path, e.g. "1-1.4" or "1-1.4:1.0" (use for CH340
                 clones that all report the same/no serial number)
  vid_pid        "1a86:7523"
  description    substring of the port description
  by_id          substring of the /dev/serial/by-id symlink name
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

from .config import Board, Target


@dataclass
class PortInfo:
    device: str
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    location: str | None = None
    description: str = ""
    manufacturer: str | None = None
    product: str | None = None
    by_id: str | None = None

    @property
    def vid_pid(self) -> str | None:
        if self.vid is None or self.pid is None:
            return None
        return f"{self.vid:04x}:{self.pid:04x}"

    def as_dict(self) -> dict:
        return {
            "device": self.device, "vid_pid": self.vid_pid, "serial_number": self.serial_number,
            "location": self.location, "description": self.description, "by_id": self.by_id,
        }


class DiscoveryError(LookupError):
    pass


def _by_id_links() -> dict[str, str]:
    base = "/dev/serial/by-id"
    links = {}
    if os.path.isdir(base):
        for name in os.listdir(base):
            links[os.path.realpath(os.path.join(base, name))] = name
    return links


def list_ports() -> list[PortInfo]:
    from serial.tools import list_ports as lp

    links = _by_id_links()
    out = []
    for p in lp.comports():
        if p.vid is None and not p.device.startswith(("/dev/ttyACM", "/dev/ttyUSB", "COM", "/dev/cu.")):
            continue  # skip legacy on-board UARTs (ttyS*)
        out.append(PortInfo(
            device=p.device, vid=p.vid, pid=p.pid, serial_number=p.serial_number,
            location=p.location, description=p.description or "", manufacturer=p.manufacturer,
            product=p.product, by_id=links.get(os.path.realpath(p.device))))
    return sorted(out, key=lambda p: p.device)


def _matches(port: PortInfo, match: dict[str, str]) -> bool:
    for key, want in match.items():
        if key == "vid_pid":
            if (port.vid_pid or "").lower() != want.lower():
                return False
        elif key == "serial_number":
            if (port.serial_number or "") != want:
                return False
        elif key == "location":
            loc = port.location or ""
            # "1-1.4" should match "1-1.4:1.0" (interface suffix)
            if loc != want and loc.split(":")[0] != want:
                return False
        elif key == "description":
            if want.lower() not in (port.description or "").lower():
                return False
        elif key == "by_id":
            if want not in (port.by_id or ""):
                return False
        else:
            raise DiscoveryError(f"unknown match key '{key}'")
    return True


def resolve_port(board: Board, ports: list[PortInfo] | None = None) -> str:
    """Return the serial device/URL for a board or raise DiscoveryError."""
    if board.port:
        return board.port
    if not board.match:
        raise DiscoveryError(f"{board.id}: neither `port` nor `match` configured")
    ports = list_ports() if ports is None else ports
    hits = [p for p in ports if _matches(p, board.match)]
    if not hits:
        raise DiscoveryError(f"{board.id}: no connected port matches {board.match}")
    # Composite devices (e.g. some debug probes) expose several interfaces;
    # prefer the lowest interface number.
    if len(hits) > 1:
        devices = {p.device for p in hits}
        if len(devices) > 1:
            raise DiscoveryError(
                f"{board.id}: {len(hits)} ports match {board.match}: {', '.join(sorted(devices))} "
                "- add serial_number or location")
    return hits[0].device


def guess_targets(port: PortInfo, targets: dict[str, Target]) -> list[str]:
    vp = port.vid_pid
    if not vp:
        return []
    return [t.name for t in targets.values() if vp in [u.lower() for u in t.usb_ids]]


def esptool_probe(port: str, timeout: float = 20.0) -> str | None:
    """Ask the ROM bootloader which ESP chip is attached. Returns e.g. 'ESP32-S3 (QFN56)'."""
    from .flash import esptool_cmd

    try:
        res = subprocess.run(esptool_cmd("--port", port, "chip_id"),
                             capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return parse_esptool_chip(res.stdout)


def parse_esptool_chip(output: str) -> str | None:
    # esptool v4: "Chip is ESP32-D0WD-V3 (revision v3.1)"
    # esptool v5: "Chip type:          ESP32-D0WD-V3 (revision v3.1)"
    found = re.findall(r"(?:Chip is|Chip type:)\s*([^\n]+)", output)
    if found:
        return found[-1].strip()
    m = re.search(r"Detecting chip type\.\.\.\s*([^\n]+)", output)
    return m.group(1).strip() if m else None


def match_probe(chip: str, targets: dict[str, Target]) -> list[str]:
    return [t.name for t in targets.values() if t.probe_match and re.search(t.probe_match, chip)]
