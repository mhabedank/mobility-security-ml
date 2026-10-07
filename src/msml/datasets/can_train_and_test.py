"""Download and parse the can-train-and-test dataset (Lampe & Meng).

Source:  https://bitbucket.org/brooke-lampe/can-train-and-test
DOI:     https://doi.org/10.11583/DTU.24805533 (DTU Data, CC BY 4.0)

Each CSV has the columns ``timestamp,arbitration_id,data_field,attack``. We convert every
file into a Parquet file with typed columns:

    ts (float64, s) | can_id (uint16) | dlc (uint8) | b0..b7 (uint8, zero-padded) | label (uint8)

Usage::

    python -m msml.datasets.can_train_and_test --out data/can-train-and-test
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

API = "https://api.bitbucket.org/2.0/repositories/brooke-lampe/can-train-and-test/src/HEAD/"
RAW = "https://bitbucket.org/brooke-lampe/can-train-and-test/raw/HEAD/"
SETS = ("set_01", "set_02", "set_03", "set_04")
SPLITS = (
    "train_01",
    "test_01_known_vehicle_known_attack",
    "test_02_unknown_vehicle_known_attack",
    "test_03_known_vehicle_unknown_attack",
    "test_04_unknown_vehicle_unknown_attack",
)
# Known/unknown vehicle per set, from the dataset README.
VEHICLES = {
    "set_01": {"known": "chevrolet_impala", "unknown": "chevrolet_silverado"},
    "set_02": {"known": "chevrolet_traverse", "unknown": "subaru_forester"},
    "set_03": {"known": "chevrolet_silverado", "unknown": "subaru_forester"},
    "set_04": {"known": "subaru_forester", "unknown": "chevrolet_traverse"},
}


def vehicle_of(set_name: str, split: str) -> str:
    return VEHICLES[set_name]["unknown" if "unknown_vehicle" in split else "known"]


def _list(path: str) -> list[dict]:
    url, out = API + path + "?pagelen=100", []
    while url:
        with urllib.request.urlopen(url, timeout=60) as r:
            page = json.load(r)
        out += page["values"]
        url = page.get("next")
    return out


def list_files() -> list[str]:
    files = []
    for s in SETS:
        for split in SPLITS:
            files += [v["path"] for v in _list(f"{s}/{split}/") if v["type"] == "commit_file"]
    return files


def parse_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), dtype={"arbitration_id": str, "data_field": str})
    data = df["data_field"].fillna("").str.strip()
    dlc = (data.str.len() // 2).clip(upper=8).astype(np.uint8)
    padded = data.str.slice(0, 16).str.ljust(16, "0")
    hexbytes = np.frombuffer(bytes.fromhex("".join(padded.tolist())), dtype=np.uint8)
    out = pd.DataFrame(
        {
            "ts": df["timestamp"].astype(np.float64),
            "can_id": df["arbitration_id"].map(lambda x: int(x, 16)).astype(np.uint16),
            "dlc": dlc,
        }
    )
    payload = hexbytes.reshape(-1, 8)
    for i in range(8):
        out[f"b{i}"] = payload[:, i]
    out["label"] = df["attack"].astype(np.uint8)
    return out


def fetch(path: str, out_dir: Path) -> Path:
    dst = out_dir / path.replace(".csv", ".parquet")
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(RAW + path, timeout=600) as r:
        raw = r.read()
    tmp = dst.with_suffix(".tmp")
    parse_csv(raw).to_parquet(tmp, index=False)
    tmp.rename(dst)
    return dst


def load(out_dir: Path, set_name: str, split: str) -> dict[str, pd.DataFrame]:
    """Return {capture_name: frames} for one split, e.g. ``{"DoS-1": df, ...}``."""
    d = Path(out_dir) / set_name / split
    return {p.stem: pd.read_parquet(p) for p in sorted(d.glob("*.parquet"))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data/can-train-and-test"))
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    files = list_files()
    print(f"{len(files)} files")
    with ThreadPoolExecutor(args.workers) as ex:
        for i, p in enumerate(ex.map(lambda f: fetch(f, args.out), files), 1):
            print(f"[{i}/{len(files)}] {p}", flush=True)


if __name__ == "__main__":
    main()
