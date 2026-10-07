"""Build firmware for targets and collect the artifacts in build/fw/<target>/.

Every build gets a fresh 32-bit build id which is compiled into the image and
reported by INFO, so the bench can prove that flashing actually worked.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import zlib
from pathlib import Path

from .config import REPO_ROOT, Lab, Target
from .flash import Firmware, FlashError, pio_cmd


class BuildError(RuntimeError):
    pass


def git_revision() -> str:
    try:
        rev = subprocess.run(["git", "-C", str(REPO_ROOT), "describe", "--always", "--dirty"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        return rev or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def new_build_id(rev: str | None = None) -> int:
    seed = f"{rev or git_revision()}:{time.time_ns()}:{os.getpid()}".encode()
    return zlib.crc32(seed) & 0xFFFFFFFF or 1


def _zoo_manifest() -> dict:
    p = REPO_ROOT / "models" / "zoo" / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {"models": []}


def _write_manifest(out: Path, target: Target, build_id: int, files: dict, extra: dict) -> Firmware:
    manifest = {
        "target": target.name,
        "build_id": f"0x{build_id:08x}",
        "git": git_revision(),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "files": files,
        "models": {m["name"]: m["crc32"] for m in _zoo_manifest()["models"]
                   if m["name"] not in target.excluded_models},
        **extra,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return Firmware(target=target.name, dir=out, manifest=manifest)


def build_native(lab: Lab, target: Target, build_id: int, verbose: bool = False) -> Firmware:
    out = lab.build_dir / target.name
    out.mkdir(parents=True, exist_ok=True)
    cc = os.environ.get("CC", "cc")
    argv = ["make", "-B", "-C", str(lab.firmware_dir / "native"), f"OUT={out}", f"CC={cc}",
            f"HIL_BUILD_ID=0x{build_id:08x}u"]
    res = subprocess.run(argv, capture_output=not verbose, text=True)
    if res.returncode != 0:
        raise BuildError(f"native build failed:\n{res.stdout}\n{res.stderr}")
    return _write_manifest(out, target, build_id, {"exe": "hilbench-sim"}, {})


def parse_pio_sizes(output: str) -> dict:
    """Extract "RAM: [==  ] 41.0% (used 33560 bytes from 81920 bytes)" style lines."""
    sizes = {}
    for kind in ("RAM", "Flash"):
        m = re.search(rf"{kind}:\s*\[[^\]]*\]\s*[\d.]+%\s*\(used (\d+) bytes from (\d+) bytes\)", output)
        if m:
            sizes[f"{kind.lower()}_used"] = int(m.group(1))
            sizes[f"{kind.lower()}_total"] = int(m.group(2))
    return sizes


def build_platformio(lab: Lab, target: Target, build_id: int, verbose: bool = False) -> Firmware:
    if not target.pio_env:
        raise BuildError(f"target {target.name} has no pio_env")
    env = {**os.environ, "HIL_BUILD_ID": f"0x{build_id:08x}"}
    argv = pio_cmd() + ["run", "-d", str(lab.firmware_dir), "-e", target.pio_env]
    res = subprocess.run(argv, env=env, capture_output=True, text=True)
    output = (res.stdout or "") + (res.stderr or "")
    if verbose:
        print(output)
    if res.returncode != 0:
        tail = "\n".join(output.strip().splitlines()[-40:])
        raise BuildError(f"PlatformIO build of {target.pio_env} failed:\n{tail}")

    pio_build = lab.firmware_dir / ".pio" / "build" / target.pio_env
    out = lab.build_dir / target.name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = {}
    for ext in ("bin", "elf", "hex", "uf2"):
        src = pio_build / f"firmware.{ext}"
        if src.exists():
            shutil.copy2(src, out / src.name)
            files[ext] = src.name
    extra: dict = {"pio_env": target.pio_env, **parse_pio_sizes(output)}
    hm = pio_build / "hil_manifest.json"
    if hm.exists():
        pio_manifest = json.loads(hm.read_text())
        images = []
        for img in pio_manifest.get("flash_images", []):
            src = Path(img["path"])
            if not src.exists():
                raise BuildError(f"flash image missing: {src}")
            name = src.name if src.name not in {i["file"] for i in images} else f"{img['offset']}_{src.name}"
            shutil.copy2(src, out / name)
            images.append({"offset": img["offset"], "file": name})
        extra.update(flash_images=images, **{k: pio_manifest[k] for k in ("flash_mode", "flash_freq", "mcu")
                                              if k in pio_manifest})
    return _write_manifest(out, target, build_id, files, extra)


def build(lab: Lab, target: Target, build_id: int | None = None, verbose: bool = False) -> Firmware:
    build_id = build_id or new_build_id()
    if target.build == "native":
        return build_native(lab, target, build_id, verbose)
    if target.build == "platformio":
        return build_platformio(lab, target, build_id, verbose)
    if target.build == "prebuilt":
        try:
            return Firmware.load(lab, target.name)
        except FlashError as e:
            raise BuildError(str(e)) from e
    raise BuildError(f"unknown build type '{target.build}'")
