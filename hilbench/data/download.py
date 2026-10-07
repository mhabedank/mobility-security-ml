"""Download, verify and unpack registered datasets outside the repository.

    hilbench data list
    hilbench data verify [ID ...]       # license declared by the publisher == registry?
    hilbench data download ID [...]     # into $HILBENCH_DATA (default ~/.cache/hilbench/datasets)
    hilbench data tree ID               # show what was unpacked (useful for new parsers)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
import zlib
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
            if src.zenodo_files and not any(name.startswith(p) for p in src.zenodo_files):
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


# ------------------------------------------------ partial (range) zip reads --

def _range_get(url: str, start: int, end: int, retries: int = 4) -> bytes:
    """Bytes [start, end] (inclusive) of a remote file; the server must honour Range."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status != 206:
                    raise DataError(f"{url}: server ignores Range requests")
                return resp.read()
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only view of a remote file via HTTP Range requests. zipfile uses it
    to read the central directory of multi-GB archives without downloading them."""

    def __init__(self, url: str, size: int, block: int = 1 << 20):
        self.url, self.size, self.block, self.pos = url, size, block, 0
        self._cache: dict[int, bytes] = {}

    def _get_block(self, idx: int) -> bytes:
        if idx not in self._cache:
            start = idx * self.block
            self._cache[idx] = _range_get(self.url, start, min(start + self.block, self.size) - 1)
            if len(self._cache) > 64:  # bound memory
                self._cache.pop(next(iter(self._cache)))
        return self._cache[idx]

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        self.pos = {io.SEEK_SET: offset, io.SEEK_CUR: self.pos + offset, io.SEEK_END: self.size + offset}[whence]
        return self.pos

    def readinto(self, b):
        n = min(len(b), max(self.size - self.pos, 0))
        out = bytearray()
        while len(out) < n:
            idx, off = divmod(self.pos + len(out), self.block)
            chunk = self._get_block(idx)[off:off + n - len(out)]
            if not chunk:
                break
            out += chunk
        b[:len(out)] = out
        self.pos += len(out)
        return len(out)


_LOCAL_HEADER = struct.Struct("<4s5HLLLHH")  # zip local file header (30 bytes)


def _read_member(url: str, info: zipfile.ZipInfo) -> bytes:
    """One member of a remote zip with a single Range request (plus one more if the
    local extra field is larger than guessed); CRC-checked."""
    guess = _LOCAL_HEADER.size + len(info.orig_filename.encode()) + len(info.extra) + 64
    raw = _range_get(url, info.header_offset, info.header_offset + guess + info.compress_size - 1)
    sig, *_, n_name, n_extra = _LOCAL_HEADER.unpack_from(raw)
    if sig != b"PK\x03\x04":
        raise DataError(f"{info.filename}: bad local header")
    begin = _LOCAL_HEADER.size + n_name + n_extra
    if begin + info.compress_size > len(raw):
        raw += _range_get(url, info.header_offset + len(raw), info.header_offset + begin + info.compress_size - 1)
    data = raw[begin:begin + info.compress_size]
    if info.compress_type == zipfile.ZIP_DEFLATED:
        data = zlib.decompressobj(-15).decompress(data)
    elif info.compress_type != zipfile.ZIP_STORED:
        raise DataError(f"{info.filename}: unsupported compression {info.compress_type}")
    if zlib.crc32(data) != info.CRC or len(data) != info.file_size:
        raise DataError(f"{info.filename}: CRC/size mismatch")
    return data


def select_members(names: list[str], select: tuple[tuple[str, int], ...], seed: int = 0) -> list[str]:
    """Deterministic random sample of up to `limit` names per glob pattern."""
    import fnmatch
    import random

    rng = random.Random(seed)
    chosen: list[str] = []
    for pattern, limit in select:
        hits = sorted(n for n in names if fnmatch.fnmatch(n, pattern) and n not in chosen)
        rng.shuffle(hits)
        chosen += sorted(hits[:limit])
        print(f"  {pattern}: {min(len(hits), limit)} of {len(hits)} members", flush=True)
    return chosen


def fetch_zip_members(f: RemoteFile, target: Path, select: tuple[tuple[str, int], ...], seed: int = 0,
                      workers: int = 8) -> int:
    """Extract only members matching (glob, max count) pairs from a remote zip:
    the central directory is read via ranges, then each member with one request."""
    from concurrent.futures import ThreadPoolExecutor

    size = f.size or int(urllib.request.urlopen(urllib.request.Request(
        f.url, method="HEAD", headers={"User-Agent": USER_AGENT}), timeout=60).headers["Content-Length"])
    with zipfile.ZipFile(io.BufferedReader(HttpRangeFile(f.url, size), buffer_size=1 << 20)) as z:
        infos = {i.filename: i for i in z.infolist() if not i.is_dir() and "__MACOSX" not in i.filename}
    root = target.resolve()
    todo = []
    for name in select_members(list(infos), select, seed):
        dest = (target / name).resolve()
        if not dest.is_relative_to(root):
            raise DataError(f"unsafe path in {f.name}: {name}")
        if not dest.exists():
            todo.append((infos[name], dest))

    def one(item):
        info, dest = item
        data = _read_member(f.url, info)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)

    t0 = time.monotonic()
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(one, todo), 1):
            if i % 100 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} members ({time.monotonic() - t0:.0f} s)", flush=True)
    return len(todo)


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


_MAGIC = [(b"PK\x03\x04", ".zip"), (b"\x1f\x8b", ".tar.gz"), (b"BZh", ".tar.bz2"), (b"\xfd7zXZ", ".tar.xz"),
          (b"7z\xbc\xaf\x27\x1c", ".7z"), (b"Rar!", ".rar")]


def _sniff(head: bytes) -> str | None:
    if len(head) > 262 and head[257:262] == b"ustar":
        return ".tar"
    return next((ext for magic, ext in _MAGIC if head.startswith(magic)), None)


def _signature_scan(path: Path, limit: int = 5) -> dict:
    """First offsets of archive signatures anywhere in a file (diagnostics for broken downloads)."""
    sigs = {"zip-local": b"PK\x03\x04", "zip-central": b"PK\x01\x02", "zip-end": b"PK\x05\x06",
            "zip64-end": b"PK\x06\x06", "7z": b"7z\xbc\xaf\x27\x1c", "rar": b"Rar!\x1a", "xz": b"\xfd7zXZ"}
    found: dict[str, list[int]] = {k: [] for k in sigs}
    zero = 0
    with open(path, "rb") as fh:
        pos, tail = 0, b""
        while True:
            block = fh.read(1 << 22)
            if not block:
                break
            zero += block.count(0)
            buf = tail + block
            for k, sig in sigs.items():
                i = buf.find(sig)
                while i >= 0 and len(found[k]) < limit:
                    off = pos - len(tail) + i
                    if off not in found[k]:
                        found[k].append(off)
                    i = buf.find(sig, i + 1)
            tail, pos = buf[-8:], pos + len(block)
    return {"size": pos, "zero_bytes": zero, **{k: v for k, v in found.items() if v}}


def _embedded_payload(archive: Path) -> Path | None:
    """Some UCI downloads are an *empty* zip (bare end-of-central-directory record)
    followed by the real archive. Split that payload off into its own file."""
    with open(archive, "rb") as fh:
        head = fh.read(22)
        if len(head) < 22 or not head.startswith(b"PK\x05\x06") or archive.stat().st_size < 1024:
            return None
        start = 22 + struct.unpack_from("<H", head, 20)[0]  # skip the zip comment
        fh.seek(start)
        while True:  # skip zero padding
            block = fh.read(1 << 20)
            nz = len(block) - len(block.lstrip(b"\0"))
            if nz < len(block):
                start += nz
                break
            if not block:
                raise DataError(f"{archive.name}: the publisher served an empty zip followed only by zero "
                                f"bytes ({archive.stat().st_size} bytes) - the download is broken at the source")
            start += len(block)
        fh.seek(start)
        ext = _sniff(fh.read(512))
        if ext is None:
            fh.seek(start)
            raise DataError(f"{archive.name}: empty zip followed by unknown data at offset {start}: "
                            f"{fh.read(32).hex()}; signatures in file: {_signature_scan(archive)}")
        out = archive.with_name(archive.name[:-4] + ".payload" + ext)
        if not out.exists():
            fh.seek(start)
            with open(out, "wb") as dst:
                shutil.copyfileobj(fh, dst, 1 << 20)
    return out


def _extract(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    payload = _embedded_payload(archive) if name.endswith(".zip") else None
    if payload is not None:
        print(f"  {archive.name}: empty zip wrapper, extracting embedded {payload.name}", flush=True)
        _extract(payload, target)
    elif name.endswith((".7z", ".rar")):
        tool = shutil.which("7z")
        if not tool:
            raise DataError(f"{archive.name}: install 7z (p7zip-full)")
        res = subprocess.run([tool, "x", "-y", f"-o{target}", str(archive)], capture_output=True, text=True)
        if res.returncode != 0:
            raise DataError(f"{archive.name}: 7z failed: {res.stderr[-500:]}")
    elif name.endswith(".zip"):
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
    for junk in list(target.rglob("__MACOSX")):  # macOS resource forks
        shutil.rmtree(junk, ignore_errors=True)
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
    if src.zip_members:  # only a subset of a huge archive, read via HTTP ranges
        for f in files:
            n = fetch_zip_members(f, d / "extracted", src.zip_members)
            record.append({"name": f.name, "url": f.url, "archive_bytes": f.size, "checksum": f.checksum,
                           "members_extracted": n, "selection": [list(s) for s in src.zip_members]})
        files = []
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
