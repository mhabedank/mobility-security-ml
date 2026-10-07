"""Bench configuration: target catalogue (hil/targets.yaml) + lab inventory (hil/boards.yaml).

* A **target** describes a kind of SoC/board: how to build, flash and reset it.
* A **board** is one physical device on the bench: which target it is and how
  to find it (USB serial number, physical USB port, explicit port...).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = REPO_ROOT / "hil" / "targets.yaml"
DEFAULT_BOARDS = REPO_ROOT / "hil" / "boards.yaml"


class ConfigError(ValueError):
    pass


@dataclass
class Target:
    name: str
    description: str = ""
    arch: str = ""
    build: str = "platformio"  # platformio | native | prebuilt
    pio_env: str | None = None
    flasher: str = "platformio"  # esptool | platformio | uf2 | command | none
    flasher_options: dict[str, Any] = field(default_factory=dict)
    esptool_chip: str | None = None
    reset: str = "none"  # esp_classic | esp_usb_jtag | dtr_pulse | command | power | soft | process | none
    transport: str = "serial"  # serial | process
    baud: int = 115200
    usb_ids: list[str] = field(default_factory=list)
    probe_match: str | None = None  # regex on esptool's "Chip is ..." line
    chip_match: str | None = None  # regex on INFO.chip reported by the firmware
    boot_timeout_s: float = 8.0
    reenumerates: bool = False  # native USB CDC: port disappears on reset
    budgets: dict[str, float] = field(default_factory=dict)  # model -> max avg latency [us]
    excluded_models: list[str] = field(default_factory=list)


@dataclass
class Board:
    id: str
    target: Target
    port: str | None = None  # explicit device/URL, or None for discovery via `match`
    match: dict[str, str] = field(default_factory=dict)
    power: dict[str, Any] = field(default_factory=dict)
    reset: str | None = None  # overrides target.reset
    reset_options: dict[str, Any] = field(default_factory=dict)
    flasher: str | None = None  # overrides target.flasher
    flasher_options: dict[str, Any] = field(default_factory=dict)
    baud: int | None = None
    tags: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)  # extra env (simulator fault injection)
    enabled: bool = True
    soft_reset: bool = True  # False: the RESET command is unreliable on this board (skip that test)
    notes: str = ""

    @property
    def reset_method(self) -> str:
        return self.reset or self.target.reset

    @property
    def flash_method(self) -> str:
        return self.flasher or self.target.flasher

    @property
    def flash_options(self) -> dict[str, Any]:
        return {**self.target.flasher_options, **self.flasher_options}

    @property
    def baudrate(self) -> int:
        return self.baud or self.target.baud


@dataclass
class Lab:
    name: str
    boards: list[Board]
    targets: dict[str, Target]
    lock_dir: Path
    results_dir: Path
    firmware_dir: Path
    build_dir: Path

    def board(self, board_id: str) -> Board:
        for b in self.boards:
            if b.id == board_id:
                return b
        raise ConfigError(f"unknown board '{board_id}' (known: {', '.join(b.id for b in self.boards)})")

    def select(self, board_ids=None, targets=None, tags=None, include_disabled=False) -> list[Board]:
        out = []
        for b in self.boards:
            if not b.enabled and not include_disabled and not board_ids:
                continue
            if board_ids and b.id not in board_ids:
                continue
            if targets and b.target.name not in targets:
                continue
            if tags and not set(tags) & set(b.tags):
                continue
            out.append(b)
        if board_ids:
            missing = set(board_ids) - {b.id for b in out}
            if missing:
                raise ConfigError(f"unknown/filtered board(s): {', '.join(sorted(missing))}")
        return out


def _read_yaml(path: Path) -> dict:
    try:
        with open(path) as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path}") from e


def _yaml_bool_keys(d: dict) -> dict:
    """YAML 1.1 reads unquoted `on:` / `off:` keys as True / False."""
    names = {True: "on", False: "off"}
    return {names.get(k, k) if isinstance(k, bool) else k: v for k, v in d.items()}


def load_targets(path: str | Path | None = None, extra: dict | None = None) -> dict[str, Target]:
    raw = _read_yaml(Path(path or DEFAULT_TARGETS))
    raw.update(extra or {})
    known = set(Target.__dataclass_fields__)
    targets = {}
    for name, spec in raw.items():
        spec = dict(spec or {})
        if "extends" in spec:
            base = raw.get(spec.pop("extends"))
            if base is None:
                raise ConfigError(f"target {name}: unknown base target")
            spec = {**{k: v for k, v in base.items() if k != "extends"}, **spec}
        unknown = set(spec) - known
        if unknown:
            raise ConfigError(f"target {name}: unknown keys {sorted(unknown)}")
        targets[name] = Target(name=name, **spec)
    return targets


def load_lab(boards_path: str | Path | None = None, targets_path: str | Path | None = None) -> Lab:
    boards_path = Path(boards_path or os.environ.get("HILBENCH_BOARDS") or DEFAULT_BOARDS)
    raw = _read_yaml(boards_path)
    lab_raw = raw.get("lab", {}) or {}
    targets = load_targets(targets_path or lab_raw.get("targets"), raw.get("targets"))
    base = boards_path.parent

    def _path(key, default):
        v = os.environ.get(f"HILBENCH_{key.upper()}") or lab_raw.get(key)
        if not v:
            return default
        p = Path(v).expanduser()
        return p if p.is_absolute() else (base / p).resolve()

    known = set(Board.__dataclass_fields__) - {"target"}
    boards = []
    seen = set()
    for spec in raw.get("boards", []) or []:
        spec = dict(spec)
        bid = spec.get("id")
        if not bid:
            raise ConfigError(f"{boards_path}: board without id")
        if bid in seen:
            raise ConfigError(f"duplicate board id {bid}")
        seen.add(bid)
        tname = spec.pop("target", None)
        if tname not in targets:
            raise ConfigError(f"board {bid}: unknown target '{tname}' (known: {', '.join(targets)})")
        unknown = set(spec) - known
        if unknown:
            raise ConfigError(f"board {bid}: unknown keys {sorted(unknown)}")
        if spec.get("port") == "auto":
            spec["port"] = None
        spec["match"] = {k: str(v) for k, v in (spec.get("match") or {}).items()}
        spec["power"] = _yaml_bool_keys(spec.get("power") or {})
        boards.append(Board(target=targets[tname], **spec))

    return Lab(
        name=lab_raw.get("name", "hil-lab"),
        boards=boards,
        targets=targets,
        lock_dir=_path("lock_dir", Path(os.environ.get("TMPDIR", "/tmp")) / "hilbench-locks"),
        results_dir=_path("results_dir", REPO_ROOT / "results"),
        firmware_dir=_path("firmware_dir", REPO_ROOT / "firmware"),
        build_dir=_path("build_dir", REPO_ROOT / "build" / "fw"),
    )
