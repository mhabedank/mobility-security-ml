"""Python binding for the C feature extractor in firmware/components/msml_can_features.

The shared library is compiled on first use with the host C compiler, so the features used
for training are computed by exactly the code that runs on the microcontroller.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
SRC_DIR = REPO / "firmware" / "components" / "msml_can_features"
C_FILE = SRC_DIR / "msml_can_features.c"
H_FILE = SRC_DIR / "include" / "msml_can_features.h"
ALARM_C = SRC_DIR / "msml_alarm.c"
ALARM_H = SRC_DIR / "include" / "msml_alarm.h"
SOURCES = [C_FILE, H_FILE, ALARM_C, ALARM_H]

FEATURE_NAMES = [
    "dt_id_ms",
    "dt_ratio",
    "dt_bus_ms",
    "bus_dt_ewma_ms",
    "id_count",
    "warmup",
    "new_id_rate",
    "dlc",
    "dlc_changed",
    "hamming",
    "bytes_changed",
    "ham_ratio",
    "can_id",
]
N_FEATURES = len(FEATURE_NAMES)
PAYLOAD_COLS = [f"b{i}" for i in range(8)]


@lru_cache(maxsize=1)
def _lib() -> ctypes.CDLL:
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in SOURCES)).hexdigest()[:12]
    cache = Path(os.environ.get("MSML_CACHE", REPO / "artifacts" / ".cache"))
    cache.mkdir(parents=True, exist_ok=True)
    so = cache / f"libmsml_can_features_{digest}.so"
    if not so.exists():
        cc = os.environ.get("CC", "gcc")
        cmd = [cc, "-O2", "-ffp-contract=off", "-shared", "-fPIC",
               "-I", str(H_FILE.parent), str(C_FILE), str(ALARM_C), "-o", str(so)]
        subprocess.run(cmd, check=True)
    lib = ctypes.CDLL(str(so))
    lib.msml_can_extract_batch.restype = ctypes.c_int
    lib.msml_can_extract_batch.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_void_p,
    ]
    lib.msml_alarm_batch.restype = None
    lib.msml_alarm_batch.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint,
        ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p,
    ]
    return lib


def to_microseconds(ts: np.ndarray) -> np.ndarray:
    """Seconds (absolute) -> integer microseconds relative to the first frame."""
    ts = np.asarray(ts, dtype=np.float64)
    return np.rint((ts - ts[0]) * 1e6).astype(np.int64)


def extract(frames: pd.DataFrame) -> np.ndarray:
    """Features for one capture (state starts empty, as after an ECU boot).

    frames needs the columns ts (s), can_id, dlc, b0..b7, in bus order.
    Returns a float32 array of shape (len(frames), N_FEATURES).
    """
    n = len(frames)
    out = np.empty((n, N_FEATURES), dtype=np.float32)
    if n == 0:
        return out
    ts = np.ascontiguousarray(to_microseconds(frames["ts"].to_numpy()))
    ids = np.ascontiguousarray(frames["can_id"].to_numpy(dtype=np.uint16))
    dlc = np.ascontiguousarray(frames["dlc"].to_numpy(dtype=np.uint8))
    data = np.ascontiguousarray(frames[PAYLOAD_COLS].to_numpy(dtype=np.uint8))
    rc = _lib().msml_can_extract_batch(
        ts.ctypes.data, ids.ctypes.data, dlc.ctypes.data, data.ctypes.data, n, out.ctypes.data
    )
    if rc != 0:
        raise MemoryError("msml_can_extract_batch failed")
    return out


def alarms(ts_us: np.ndarray, flagged: np.ndarray, k: int, window_ms: float,
           holdoff_ms: float = 1000.0) -> np.ndarray:
    """Alarm aggregation (C implementation, msml_alarm.c): 1 where a frame raises an alarm."""
    ts = np.ascontiguousarray(ts_us, dtype=np.int64)
    fl = np.ascontiguousarray(flagged, dtype=np.uint8)
    out = np.zeros(ts.size, dtype=np.uint8)
    _lib().msml_alarm_batch(ts.ctypes.data, fl.ctypes.data, ts.size, int(k),
                            int(window_ms * 1000), int(holdoff_ms * 1000), out.ctypes.data)
    return out
