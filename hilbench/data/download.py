"""Download, verify and unpack registered datasets outside the repository.

    hilbench data list
    hilbench data verify [ID ...]       # license declared by the publisher == registry?
    hilbench data download ID [...]     # into $HILBENCH_DATA (default ~/.cache/hilbench/datasets)
    hilbench data tree ID               # show what was unpacked (useful for new parsers)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .registry import SOURCES, Source

USER_AGENT = "hilbench-dataset-downloader/0.1 (+https://github.com/mhabedank/mobility-security-ml)"


class DataError(RuntimeError):
    pass


@dataclass
class RemoteFile:
    url: str
    name: str
    size: int | None = None
    checksum: str | None = None  # "md5:..." or "sha256:..."


def data_root() -> Path:
    root = os.environ.get("HILBENCH_DATA")
    return Path(root).expanduser() if root else Path.home() / ".cache" / "hilbench" / "datasets"


def dataset_dir(ds_id: str) -> Path:
    return data_root() / ds_id


def _get_json(url: str, timeout: float = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _norm_license(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("international", ""))


# ---------------------------------------------------------------- remote --

def zenodo_record(record: str) -> dict:
    return _get_json(f"https://zenodo.org/api/records/{record}")


def uci_record(uci_id: int) -> dict:
    return _get_json(f"https://archive.ics.uci.edu/api/dataset?id={uci_id}")


def declared_license(src: Source) -> str | None:
    """License as published by the data host right now."""
    if src.zenodo_record:
        meta = zenodo_record(src.zenodo_record).get("metadata", {})
        lic = meta.get("license") or {}
        return lic.get("id") if isinstance(lic, dict) else str(lic)
    if src.uci_id:
        # The UCI API has no license field; the dataset pages state CC BY 4.0 for
        # all donated datasets since 2023. Report what the API offers for audit.
        data = uci_record(src.uci_id).get("data", {})
        return data.get("license") or data.get("licence")
    return None  # direct URLs: license is documented by the publisher, see homepage


def remote_files(src: Source) -> list[RemoteFile]:
    if src.zenodo_record:
        rec = zenodo_record(src.zenodo_record)
        files = []
        for f in rec.get("files", []):
            name = f.get("key") or f.get("filename")
            if src.zenodo_files and not any(p in name for p in src.zenodo_files):
                continue
            url = (f.get("links") or {}).get("self") or f"https://zenodo.org/records/{src.zenodo_record}/files/{name}"
            files.append(RemoteFile(url=url, name=name, size=f.get("size"), checksum=f.get("checksum")))
        if not files:
            raise DataError(f"{src.id}: no files matched {src.zenodo_files} in Zenodo record {src.zenodo_record}")
        return files
    if src.uci_id:
        data = uci_record(src.uci_id).get("data", {})
        slug = (data.get("name") or src.id).lower().replace(" ", "+")
        url = f"https://archive.ics.uci.edu/static/public/{src.uci_id}/{slug}.zip"
        return [RemoteFile(url=url, name=f"{src.id}.zip")]
    return [RemoteFile(url=u, name=u.rsplit("/", 1)[-1]) for u in src.urls]


# -------------------------------------------------------------- download --

def _hash_file(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(f: RemoteFile, dest: Path, retries: int = 4) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        have = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            req = urllib.request.Request(f.url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                mode = "ab" if have and resp.status == 206 else "wb"
                total = int(resp.headers.get("Content-Length") or 0) + (have if mode == "ab" else 0)
                done = have if mode == "ab" else 0
                last = time.monotonic()
                with open(part, mode) as out:
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        if time.monotonic() - last > 10:
                            pct = f"{done / total * 100:.0f}%" if total else f"{done >> 20} MiB"
                            print(f"    {f.name}: {pct}", flush=True)
                            last = time.monotonic()
            part.rename(dest)
            return
        except OSError as e:
            if attempt == retries - 1:
                raise DataError(f"download of {f.url} failed: {e}") from e
            time.sleep(2 ** (attempt + 1))


def _verify_checksum(path: Path, checksum: str | None) -> None:
    if not checksum or ":" not in checksum:
        return
    algo, want = checksum.split(":", 1)
    got = _hash_file(path, algo)
    if got != want:
        path.unlink()
        raise DataError(f"{path.name}: {algo} mismatch ({got} != {want}) - file deleted, retry")


def _extract(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        try:
            with zipfile.ZipFile(archive) as z:
                for m in z.infolist():  # zip-slip protection
                    p = (target / m.filename).resolve()
                    if not str(p).startswith(str(target.resolve())):
                        raise DataError(f"unsafe path in {archive.name}: {m.filename}")
                z.extractall(target)
        except (zipfile.BadZipFile, NotImplementedError) as e:
            # Some archives (e.g. Google-Drive exports, deflate64) trip Python's zipfile.
            tool = shutil.which("7z") or shutil.which("unzip")
            if not tool:
                raise DataError(f"{archive.name}: {e}; install unzip or 7z") from e
            cmd = [tool, "x", "-y", f"-o{target}", str(archive)] if tool.endswith("7z") else \
                [tool, "-o", "-q", str(archive), "-d", str(target)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode not in (0, 1):  # unzip: 1 = warnings
                raise DataError(f"{archive.name}: {e}; {Path(tool).name} failed: {res.stderr[-500:]}") from e
    elif name.endswith((".tar.gz", ".tgz", ".tar", ".tar.xz", ".tar.bz2")):
        with tarfile.open(archive) as t:
            kwargs = {"filter": "data"} if sys.version_info >= (3, 12) else {}
            for m in t.getmembers():
                p = (target / m.name).resolve()
                if not str(p).startswith(str(target.resolve())):
                    raise DataError(f"unsafe path in {archive.name}: {m.name}")
            t.extractall(target, **kwargs)
    # nested archives (UCI zips often contain another zip)
    for inner in list(target.rglob("*.zip")):
        sub = inner.with_suffix("")
        if not sub.exists():
            _extract(inner, sub)


def download(ds_id: str, extract: bool = True, force: bool = False, check_license: bool = True) -> Path:
    src = SOURCES.get(ds_id)
    if src is None:
        raise DataError(f"unknown dataset '{ds_id}' (known: {', '.join(SOURCES)})")
    d = dataset_dir(ds_id)
    marker = d / "SOURCE.json"
    if marker.exists() and not force:
        return d
    d.mkdir(parents=True, exist_ok=True)
    if check_license:
        ok, declared = verify(src)
        if not ok:
            raise DataError(f"{ds_id}: publisher now declares license '{declared}', registry says "
                            f"'{src.license}' - review before use")
    print(f"{ds_id}: {src.title}\n  license: {src.license} - {src.attribution}", flush=True)
    files = remote_files(src)
    raw = d / "raw"
    raw.mkdir(exist_ok=True)
    record = []
    for f in files:
        dest = raw / f.name
        if not dest.exists():
            size = f" ({f.size / 1e6:.0f} MB)" if f.size else ""
            print(f"  downloading {f.name}{size}", flush=True)
            _fetch(f, dest)
            _verify_checksum(dest, f.checksum)
        record.append({"name": f.name, "url": f.url, "sha256": _hash_file(dest, "sha256"),
                       "bytes": dest.stat().st_size})
        if extract:
            _extract(dest, d / "extracted")
    marker.write_text(json.dumps({
        "id": src.id, "title": src.title, "license": src.license, "license_url": src.license_url,
        "attribution": src.attribution, "citation": src.citation, "homepage": src.homepage,
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": record,
    }, indent=2) + "\n")
    return d


def verify(src: Source) -> tuple[bool, str | None]:
    declared = declared_license(src)
    if declared is None:
        return True, None
    return _norm_license(declared) == _norm_license(src.license), declared


def tree(ds_id: str, max_entries: int = 60) -> str:
    d = dataset_dir(ds_id) / "extracted"
    if not d.exists():
        raise DataError(f"{ds_id} is not downloaded")
    lines = []
    for p in sorted(d.rglob("*"))[:max_entries]:
        rel = p.relative_to(d)
        lines.append(f"{rel}{'/' if p.is_dir() else f'  ({p.stat().st_size} B)'}")
    total = sum(1 for _ in d.rglob("*"))
    if total > max_entries:
        lines.append(f"... {total - max_entries} more")
    return "\n".join(lines)


def remove(ds_id: str) -> None:
    shutil.rmtree(dataset_dir(ds_id), ignore_errors=True)
