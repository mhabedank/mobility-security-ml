"""Collect metrics during a run and render summaries (JSON + Markdown).

Layout of a run directory (results/<run-id>/):
  metrics/*.jsonl   one JSON object per line (one file per process / xdist worker)
  logs/<board>.log  full serial log incl. host commands
  junit.xml         from pytest
  summary.json/.md  written at the end of the session (`hilbench report` re-creates them)
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path


def new_run_dir(base: Path) -> Path:
    """Pick a fresh run directory name (created lazily on first record)."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run = base / stamp
    i = 1
    while run.exists():
        run = base / f"{stamp}-{i}"
        i += 1
    return run


class Recorder:
    def __init__(self, run_dir: Path, worker: str = "main"):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "metrics" / f"{worker}-{os.getpid()}.jsonl"

    def record(self, kind: str, board: str, **data) -> dict:
        rec = {"ts": time.time(), "kind": kind, "board": board, **data}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(rec, default=_json_default) + "\n")
        return rec


def _json_default(o):
    try:
        import numpy as np

        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:  # pragma: no cover
        pass
    return str(o)


def load_records(run_dir: Path) -> list[dict]:
    recs = []
    for p in sorted((Path(run_dir) / "metrics").glob("*.jsonl")):
        for line in p.read_text().splitlines():
            if line.strip():
                recs.append(json.loads(line))
    return sorted(recs, key=lambda r: r.get("ts", 0))


def summarize(records: list[dict]) -> dict:
    boards: dict[str, dict] = {}
    perf: dict[str, dict[str, dict]] = defaultdict(dict)
    accuracy: dict[str, dict[str, dict]] = defaultdict(dict)
    tests: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    failures = []
    for r in records:
        b = r.get("board", "?")
        kind = r["kind"]
        if kind == "board":
            boards[b] = {k: v for k, v in r.items() if k not in ("ts", "kind", "board")}
        elif kind == "bench":
            perf[b][r["model"]] = {k: r[k] for k in ("us_avg", "us_min", "us_max", "cyc_avg", "macs", "n")
                                   if k in r}
        elif kind == "accuracy":
            accuracy[b][r["model"]] = {k: v for k, v in r.items() if k not in ("ts", "kind", "board", "model")}
        elif kind == "test":
            tests[b][r["outcome"]] += 1
            if r["outcome"] == "failed":
                failures.append({"board": b, "test": r["nodeid"], "message": r.get("message", "")[:500]})
    for b in set(tests) | set(perf):
        boards.setdefault(b, {})
    return {
        "boards": boards,
        "tests": {b: dict(v) for b, v in tests.items()},
        "perf": dict(perf),
        "accuracy": dict(accuracy),
        "failures": failures,
    }


def _fmt_us(us) -> str:
    if us is None:
        return "-"
    if us >= 100000:
        return f"{us / 1000:.0f} ms"
    if us >= 1000:
        return f"{us / 1000:.2f} ms"
    return f"{us} µs"


def _fmt_kib(used, total=None) -> str:
    if not used:
        return "-"
    s = f"{used / 1024:.1f} KiB"
    return f"{s} / {total / 1024:.0f}" if total else s


def render_markdown(summary: dict, title: str = "HIL TinyML bench") -> str:
    out = [f"# {title}\n"]
    boards = summary["boards"]
    out.append("## Boards\n")
    out.append("| Board | Target | Chip | MHz | Firmware | RAM | Flash | free heap | passed | failed | skipped |")
    out.append("|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for b in sorted(boards):
        info = boards[b]
        t = summary["tests"].get(b, {})
        out.append(f"| {b} | {info.get('target', '-')} | {info.get('chip', '-')} | {info.get('cpu_mhz', '-')} | "
                   f"{info.get('build', '-')} | {_fmt_kib(info.get('ram_used'), info.get('ram_total'))} | "
                   f"{_fmt_kib(info.get('flash_used'), info.get('flash_total'))} | "
                   f"{_fmt_kib(info.get('free_heap'))} | "
                   f"{t.get('passed', 0)} | {t.get('failed', 0)} | {t.get('skipped', 0)} |")
    models = sorted({m for p in summary["perf"].values() for m in p})
    if models:
        out.append("\n## Latency (average per inference)\n")
        out.append("| Model | " + " | ".join(sorted(summary["perf"])) + " |")
        out.append("|---|" + "---:|" * len(summary["perf"]))
        for m in models:
            row = []
            for b in sorted(summary["perf"]):
                p = summary["perf"][b].get(m)
                row.append(_fmt_us(p["us_avg"]) if p else "-")
            out.append(f"| {m} | " + " | ".join(row) + " |")
        out.append("\n## Efficiency (CPU cycles per MAC)\n")
        out.append("| Model | " + " | ".join(sorted(summary["perf"])) + " |")
        out.append("|---|" + "---:|" * len(summary["perf"]))
        for m in models:
            row = []
            for b in sorted(summary["perf"]):
                p = summary["perf"][b].get(m)
                row.append(f"{p['cyc_avg'] / p['macs']:.1f}" if p and p.get("cyc_avg") and p.get("macs") else "-")
            out.append(f"| {m} | " + " | ".join(row) + " |")
    if summary["accuracy"]:
        out.append("\n## Accuracy on device (evaluation sets)\n")
        out.append("| Board | Model | samples | device | host int8 | bit-exact |")
        out.append("|---|---|---:|---:|---:|---|")
        for b in sorted(summary["accuracy"]):
            for m, a in sorted(summary["accuracy"][b].items()):
                out.append(f"| {b} | {m} | {a.get('n', '-')} | {a.get('device_metric', 0):.4f} | "
                           f"{a.get('host_metric', 0):.4f} | {'yes' if a.get('bit_exact') else 'NO'} |")
    if summary["failures"]:
        out.append("\n## Failures\n")
        for f in summary["failures"]:
            msg = f["message"].strip().splitlines()[-1] if f["message"].strip() else ""
            out.append(f"- **{f['board']}** `{f['test']}`: {msg}")
    return "\n".join(out) + "\n"


def write_summary(run_dir: Path) -> dict:
    summary = summarize(load_records(run_dir))
    summary["run"] = Path(run_dir).name
    (Path(run_dir) / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (Path(run_dir) / "summary.md").write_text(render_markdown(summary))
    return summary


def compare_to_baseline(summary: dict, baseline: dict, tolerance: float = 0.2) -> list[str]:
    """Latency regressions (avg slower than baseline by more than `tolerance`)."""
    problems = []
    for b, models in summary.get("perf", {}).items():
        for m, p in models.items():
            ref = baseline.get("perf", {}).get(b, {}).get(m)
            if ref and ref.get("us_avg") and p.get("us_avg", 0) > ref["us_avg"] * (1 + tolerance):
                problems.append(f"{b}/{m}: {p['us_avg']} µs vs baseline {ref['us_avg']} µs "
                                f"(+{(p['us_avg'] / ref['us_avg'] - 1) * 100:.0f}%)")
    return problems
