"""Per-board exclusive locks so parallel jobs (CI runners, developers, xdist
workers) never talk to the same board at the same time."""
from __future__ import annotations

import os
import time
from pathlib import Path


class LockTimeout(TimeoutError):
    pass


class BoardLock:
    def __init__(self, lock_dir: Path, board_id: str, timeout: float = 600.0):
        self.path = Path(lock_dir) / f"{board_id}.lock"
        self.timeout = timeout
        self._fh = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+")
        deadline = time.monotonic() + self.timeout
        try:
            import fcntl
        except ImportError:  # Windows: best effort, no inter-process locking
            self._fh = fh
            return
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    fh.close()
                    raise LockTimeout(f"board lock {self.path} held by another process") from None
                time.sleep(0.5)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()}\n")
        fh.flush()
        self._fh = fh

    def release(self) -> None:
        if self._fh is not None:
            try:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
            self._fh.close()
            self._fh = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
