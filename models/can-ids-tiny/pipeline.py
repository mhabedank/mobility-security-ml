"""can-ids-tiny: train, evaluate and export a frame-level CAN intrusion detector.

Evaluation follows the can-train-and-test protocol: for each of the four sets, train on
train_01 and test on four splits (known/unknown vehicle x known/unknown attack).

    python models/can-ids-tiny/pipeline.py evaluate   # protocol results -> artifacts/can-ids-tiny/
    python models/can-ids-tiny/pipeline.py export     # final model on all vehicles -> C header
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_recall_curve

from msml.can.features import FEATURE_NAMES, alarms, extract, to_microseconds
from msml.datasets.can_train_and_test import SETS, SPLITS, load, vehicle_of
from msml.eval.metrics import alarm_metrics, false_alarms_per_hour, frame_metrics

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "can-train-and-test"
OUT = REPO / "artifacts" / "can-ids-tiny"

# Small grid; every candidate must stay well inside an ESP32 flash/RAM budget.
GRID = [
    {"n_estimators": 10, "max_depth": 8},
    {"n_estimators": 20, "max_depth": 10},
    {"n_estimators": 30, "max_depth": 12},
]
FEATURE_SETS = {
    "full": FEATURE_NAMES,
    # Without the raw identifier the model cannot memorise vehicle-specific IDs.
    "no_can_id": [f for f in FEATURE_NAMES if f != "can_id"],
}
# Alarm aggregation grid: alarm when k flagged frames fall within window_ms (hold-off 1 s).
ALARM_GRID = [(k, w) for k in (1, 2, 3, 5, 8) for w in (50, 200, 1000)]
ALARM_HOLDOFF_MS = 1000
BENIGN_KEEP = 0.1  # share of benign frames kept for training (all attack frames are kept)
SEED = 0


def attack_type(capture: str) -> str:
    return re.sub(r"-\d+$", "", capture)


def featurize(set_name: str, split: str) -> list[dict]:
    """Return one dict per capture with features, labels and timestamps."""
    caps = []
    for name, df in load(DATA, set_name, split).items():
        caps.append({
            "name": name,
            "attack": attack_type(name),
            "X": extract(df),
            "y": df["label"].to_numpy(np.uint8),
            "ts": df["ts"].to_numpy(np.float64),
        })
    return caps


def subsample(caps: list[dict], rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    Xs, ys = [], []
    for c in caps:
        keep = (c["y"] == 1) | (rng.random(c["y"].size) < BENIGN_KEEP)
        Xs.append(c["X"][keep])
        ys.append(c["y"][keep])
    return np.concatenate(Xs), np.concatenate(ys)


def split_train_val(caps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Hold out the highest-numbered capture of each attack type for validation."""
    last = {}
    for c in caps:
        idx = int(re.search(r"-(\d+)$", c["name"]).group(1))
        if idx > last.get(c["attack"], -1):
            last[c["attack"]] = idx
    val = [c for c in caps if c["name"] == f'{c["attack"]}-{last[c["attack"]]}']
    tr = [c for c in caps if c not in val]
    return tr, val


def cols(names: list[str]) -> list[int]:
    return [FEATURE_NAMES.index(n) for n in names]


def fit(X: np.ndarray, y: np.ndarray, hp: dict) -> RandomForestClassifier:
    clf = RandomForestClassifier(min_samples_leaf=20, n_jobs=-1, random_state=SEED, **hp)
    return clf.fit(X, y)


def vote_score(clf: RandomForestClassifier, X: np.ndarray) -> np.ndarray:
    """Share of trees voting "attack".

    This is what the emlearn C code computes on the device (hard voting per tree), which
    differs from scikit-learn's averaged leaf probabilities.
    """
    votes = np.zeros(X.shape[0], dtype=np.float32)
    for tree in clf.estimators_:
        votes += tree.predict(X).astype(np.float32)
    return votes / len(clf.estimators_)


def predict(clf, caps: list[dict], idx: list[int]) -> list[np.ndarray]:
    return [vote_score(clf, c["X"][:, idx]) for c in caps]


def best_threshold(y: np.ndarray, score: np.ndarray) -> float:
    p, r, t = precision_recall_curve(y, score)
    f1 = 2 * p * r / np.maximum(p + r, 1e-12)
    return float(t[np.argmax(f1[:-1])])


def evaluate_caps(caps: list[dict], scores: list[np.ndarray], thr: float) -> dict:
    y = np.concatenate([c["y"] for c in caps])
    s = np.concatenate(scores)
    res = frame_metrics(y, s, thr)
    res["false_alarms_per_hour"] = false_alarms_per_hour(
        [(c["ts"], c["y"], sc) for c, sc in zip(caps, scores)], thr)
    res["per_attack"] = {}
    for att in sorted({c["attack"] for c in caps}):
        sel = [i for i, c in enumerate(caps) if c["attack"] == att]
        ya = np.concatenate([caps[i]["y"] for i in sel])
        sa = np.concatenate([scores[i] for i in sel])
        m = frame_metrics(ya, sa, thr)
        res["per_attack"][att] = {k: m[k] for k in ("recall", "precision", "f1", "fpr")}
    res["alarm"] = alarm_grid(caps, scores, thr)
    return res


def alarm_grid(caps: list[dict], scores: list[np.ndarray], thr: float) -> dict:
    """Event-level metrics for every (k, window) in ALARM_GRID."""
    ts_us = [to_microseconds(c["ts"]) for c in caps]
    out = {}
    for k, w in ALARM_GRID:
        runs = [(c["ts"], c["y"], alarms(t, sc >= thr, k, w, ALARM_HOLDOFF_MS))
                for c, t, sc in zip(caps, ts_us, scores)]
        out[f"k{k}_w{w}"] = alarm_metrics(runs)
    return out


ALARM_BUDGET_PER_HOUR = 2.0


def pick_alarm(grid: dict) -> str:
    """Highest episode recall among settings within the false-alarm budget (ties: faster alarm).

    If no setting meets the budget, take the one with the fewest false alarms.
    """
    ok = {k: m for k, m in grid.items() if m["false_alarms_per_hour"] <= ALARM_BUDGET_PER_HOUR}
    if not ok:
        return min(grid, key=lambda k: grid[k]["false_alarms_per_hour"])
    return max(ok, key=lambda k: (ok[k]["episode_recall"], -ok[k]["median_latency_ms"]))


def select(train_caps: list[dict], idx: list[int], rng) -> tuple[dict, float, list]:
    tr, val = split_train_val(train_caps)
    Xtr, ytr = subsample(tr, rng)
    yv = np.concatenate([c["y"] for c in val])
    log = []
    best = None
    for hp in GRID:
        clf = fit(Xtr[:, idx], ytr, hp)
        sv = np.concatenate(predict(clf, val, idx))
        thr = best_threshold(yv, sv)
        m = frame_metrics(yv, sv, thr)
        log.append({**hp, "threshold": thr, "val_f1": m["f1"], "val_auc_pr": m["auc_pr"]})
        if best is None or m["f1"] > best[2]:
            best = (hp, thr, m["f1"])
    return best[0], best[1], log


SCORES = OUT / "scores"


def save_scores(set_name, fs_name, split, caps, scores, n_trees) -> None:
    """Store per-frame tree votes (uint8) so alarm metrics can be recomputed without training."""
    d = SCORES / set_name / fs_name
    d.mkdir(parents=True, exist_ok=True)
    votes = {c["name"]: np.rint(sc * n_trees).astype(np.uint8) for c, sc in zip(caps, scores)}
    np.savez_compressed(d / f"{split}.npz", n_trees=n_trees, **votes)


def cmd_alarms(args) -> None:
    """Recompute the alarm grid in protocol_results.json from stored scores."""
    path = OUT / "protocol_results.json"
    results = json.loads(path.read_text())
    for set_name, entry in results.items():
        for fs_name, fs_entry in entry.items():
            thr = fs_entry["threshold"]
            for split, r in fs_entry["splits"].items():
                saved = np.load(SCORES / set_name / fs_name / f"{split}.npz")
                n_trees = int(saved["n_trees"])
                frames = load(DATA, set_name, split)
                caps, scores = [], []
                for name, df in frames.items():
                    caps.append({"ts": df["ts"].to_numpy(np.float64),
                                 "y": df["label"].to_numpy(np.uint8)})
                    scores.append(saved[name].astype(np.float32) / np.float32(n_trees))
                r["alarm"] = alarm_grid(caps, scores, thr)
            print(set_name, fs_name, "done", flush=True)
    path.write_text(json.dumps(results, indent=2))


def cmd_evaluate(args) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for set_name in args.sets:
        t0 = time.time()
        train_caps = featurize(set_name, "train_01")
        tests = {split: featurize(set_name, split) for split in SPLITS[1:]}
        results[set_name] = {}
        for fs_name, fs in FEATURE_SETS.items():
            idx = cols(fs)
            rng = np.random.default_rng(SEED)
            hp, thr, log = select(train_caps, idx, rng)
            X, y = subsample(train_caps, rng)
            clf = fit(X[:, idx], y, hp)
            entry = {"hyperparameters": hp, "threshold": thr, "selection": log, "splits": {}}
            for split, caps in tests.items():
                scores = predict(clf, caps, idx)
                save_scores(set_name, fs_name, split, caps, scores, len(clf.estimators_))
                r = evaluate_caps(caps, scores, thr)
                r["vehicle"] = vehicle_of(set_name, split)
                entry["splits"][split] = r
                print(f"{set_name} {fs_name:9s} {split:42s} F1={r['f1']:.3f} "
                      f"P={r['precision']:.3f} R={r['recall']:.3f} AUC-PR={r['auc_pr']:.3f} "
                      f"FA/h={r['false_alarms_per_hour']:.1f}", flush=True)
            results[set_name][fs_name] = entry
        print(f"{set_name} done in {time.time() - t0:.0f}s", flush=True)
        (OUT / "protocol_results.json").write_text(json.dumps(results, indent=2))


EXPORT_FEATURES = "no_can_id"
MODEL_NAME = "can_ids_tiny_model"
C_DIR = Path(__file__).resolve().parent / "c"
FEATURES_DIR = REPO / "firmware" / "components" / "msml_can_features"
FRAME_DTYPE = np.dtype([("ts", "<i8"), ("can_id", "<u2"), ("dlc", "u1"), ("data", "u1", (8,))])
# Captures used for the C-vs-Python parity check: several vehicles and attack types.
PARITY_CAPTURES = [
    ("set_01", "test_02_unknown_vehicle_known_attack", "DoS-3"),
    ("set_02", "test_01_known_vehicle_known_attack", "fuzzing-3"),
    ("set_03", "test_03_known_vehicle_unknown_attack", "speed-1"),
    ("set_04", "test_04_unknown_vehicle_unknown_attack", "triple-1"),
]
PARITY_FRAMES = 200_000


def frames_to_bin(df) -> np.ndarray:
    from msml.can.features import PAYLOAD_COLS, to_microseconds

    rec = np.zeros(len(df), dtype=FRAME_DTYPE)
    rec["ts"] = to_microseconds(df["ts"].to_numpy())
    rec["can_id"] = df["can_id"].to_numpy()
    rec["dlc"] = df["dlc"].to_numpy()
    rec["data"] = df[PAYLOAD_COLS].to_numpy(np.uint8)
    return rec


def write_config_header(path: Path, idx: list[int], threshold: float, alarm: dict) -> None:
    names = [FEATURE_NAMES[i] for i in idx]
    lines = [
        "/* Generated by models/can-ids-tiny/pipeline.py export. Do not edit. */",
        "#ifndef CAN_IDS_TINY_CONFIG_H",
        "#define CAN_IDS_TINY_CONFIG_H",
        "",
        f"#define CAN_IDS_TINY_N_INPUTS {len(idx)}",
        f"#define CAN_IDS_TINY_THRESHOLD {threshold:.9g}f",
        "",
        "/* Alarm when ALARM_K flagged frames fall within ALARM_WINDOW_US; then hold off. */",
        f"#define CAN_IDS_TINY_ALARM_K {alarm['k']}",
        f"#define CAN_IDS_TINY_ALARM_WINDOW_US {alarm['window_ms'] * 1000}",
        f"#define CAN_IDS_TINY_ALARM_HOLDOFF_US {alarm['holdoff_ms'] * 1000}",
        "",
        "/* Model input i = feature can_ids_tiny_input_index[i] of msml_can_update(). */",
        "static const int can_ids_tiny_input_index[CAN_IDS_TINY_N_INPUTS] = {",
        *[f"    {i}, /* {n} */" for i, n in zip(idx, names)],
        "};",
        "",
        "#endif /* CAN_IDS_TINY_CONFIG_H */",
        "",
    ]
    path.write_text("\n".join(lines))


def build_host_scorer(export_dir: Path) -> Path:
    import subprocess

    exe = export_dir / "host_score"
    subprocess.run([
        "gcc", "-std=c99", "-O2", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror",
        "-Wno-unused-parameter",  # emlearn-generated trees ignore features_length
        "-I", str(export_dir), "-I", str(C_DIR), "-I", str(FEATURES_DIR / "include"),
        str(C_DIR / "host_score.c"), str(C_DIR / "can_ids_tiny.c"),
        str(FEATURES_DIR / "msml_can_features.c"), str(FEATURES_DIR / "msml_alarm.c"),
        "-o", str(exe),
    ], check=True)
    return exe


def parity_check(clf, idx: list[int], export_dir: Path) -> dict:
    """Score frames with the C code and with Python; the scores must agree."""
    import subprocess

    exe = build_host_scorer(export_dir)
    report = {}
    for set_name, split, cap in PARITY_CAPTURES:
        df = load(DATA, set_name, split)[cap].iloc[:PARITY_FRAMES]
        fin, fout = export_dir / "parity_frames.bin", export_dir / "parity_scores.bin"
        frames_to_bin(df).tofile(fin)
        subprocess.run([str(exe), str(fin), str(fout)], check=True)
        c_scores = np.fromfile(fout, dtype=np.float32)
        py_scores = vote_score(clf, extract(df)[:, idx])
        report[f"{set_name}/{split}/{cap}"] = {
            "frames": len(df),
            "identical": float(np.mean(c_scores == py_scores)),
            "max_abs_diff": float(np.max(np.abs(c_scores - py_scores))),
        }
        fin.unlink()
        fout.unlink()
    return report


def float32_split_literal(threshold: float) -> str:
    """C literal t such that, for every float32 x, (x < t) == (x <= threshold).

    scikit-learn sends x left when x <= threshold (threshold in float64); the emlearn
    generated code tests x < t with a float literal. Using the next float32 above the largest
    float32 <= threshold makes both tests agree exactly.
    """
    with np.errstate(all="ignore"):
        a = np.float32(threshold)
        if float(a) > threshold:
            a = np.nextafter(a, np.float32(-np.inf))
        t = np.nextafter(a, np.float32(np.inf))
    # Avoid subnormal literals (some FPUs flush them to zero). All features are >= 0 and never
    # subnormal, so "x < smallest normal" still means exactly "x <= threshold" here.
    tiny = np.finfo(np.float32).tiny
    if 0 < t < tiny:
        t = tiny
    return np.format_float_scientific(t, unique=True) + "f"


def to_c(clf, idx: list[int], thr: float, alarm: dict, export_dir: Path) -> None:
    import emlearn
    import emlearn.cgen

    original = emlearn.cgen.constant

    def exact_constant(val, dtype="float"):
        return float32_split_literal(float(val)) if dtype == "float" else original(val, dtype)

    emlearn.cgen.constant = exact_constant
    try:
        cmodel = emlearn.convert(clf, method="inline", dtype="float")
        cmodel.save(file=str(export_dir / f"{MODEL_NAME}.h"), name=MODEL_NAME)
    finally:
        emlearn.cgen.constant = original
    write_config_header(export_dir / "can_ids_tiny_config.h", idx, thr, alarm)


def write_export_config(clf, idx, thr, alarm, hp, selection, parity, export_dir: Path) -> dict:
    config = {
        "model": "can-ids-tiny",
        "task": "frame-level CAN intrusion detection (binary: benign / attack)",
        "algorithm": "random forest, hard voting, exported to C with emlearn (float)",
        "hyperparameters": {**hp, "min_samples_leaf": 20},
        "inputs": [FEATURE_NAMES[i] for i in idx],
        "input_index": idx,
        "threshold": thr,
        "score": "share of trees voting attack",
        "alarm": alarm,
        "tree_nodes": int(sum(e.tree_.node_count for e in clf.estimators_)),
        "training_data": {
            "dataset": "can-train-and-test (Lampe & Meng)",
            "doi": "10.11583/DTU.24805533",
            "license": "CC BY 4.0",
            "subsets": "train_01 of set_01..set_04 (4 vehicles)",
            "benign_frames_kept": BENIGN_KEEP,
        },
        "selection": selection,
        "parity_c_vs_python": parity,
    }
    (export_dir / "config.json").write_text(json.dumps(config, indent=2))
    return config


def convert_and_check(export_dir: Path) -> None:
    saved = joblib.load(export_dir / "model.joblib")
    clf, thr, idx = saved["model"], saved["threshold"], saved["input_index"]
    alarm = saved["alarm"]
    to_c(clf, idx, thr, alarm, export_dir)
    parity = parity_check(clf, idx, export_dir)
    hp = {"n_estimators": clf.n_estimators, "max_depth": clf.max_depth}
    config = write_export_config(clf, idx, thr, alarm, hp, saved["selection"], parity,
                                 export_dir)
    print(json.dumps({k: config[k] for k in ("hyperparameters", "threshold", "tree_nodes",
                                             "parity_c_vs_python")}, indent=2))
    bad = {k: v for k, v in parity.items() if v["identical"] < 1.0}
    if bad:
        raise SystemExit(f"C and Python scores differ: {bad}")


def cmd_export(args) -> None:
    export_dir = OUT / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    idx = cols(FEATURE_SETS[EXPORT_FEATURES])
    tr, val = [], []
    for set_name in SETS:
        t, v = split_train_val(featurize(set_name, "train_01"))
        tr += t
        val += v
    rng = np.random.default_rng(SEED)
    Xtr, ytr = subsample(tr, rng)
    yv = np.concatenate([c["y"] for c in val])
    selection, best = [], None
    for hp in GRID:
        val_scores = predict(fit(Xtr[:, idx], ytr, hp), val, idx)
        sv = np.concatenate(val_scores)
        thr = best_threshold(yv, sv)
        m = frame_metrics(yv, sv, thr)
        selection.append({**hp, "threshold": thr, "val_f1": m["f1"], "val_auc_pr": m["auc_pr"]})
        print(selection[-1], flush=True)
        if best is None or m["f1"] > best[2]:
            best = (hp, thr, m["f1"], val_scores)
    hp, thr, _, best_val_scores = best
    grid = alarm_grid(val, best_val_scores, thr)
    key = pick_alarm(grid)
    k, w = (int(v[1:]) for v in key.split("_"))
    alarm = {"k": k, "window_ms": w, "holdoff_ms": ALARM_HOLDOFF_MS,
             "selected_on": "validation captures", "validation": grid[key],
             "validation_grid": grid}
    print("alarm", key, grid[key], flush=True)
    X, y = subsample(tr + val, rng)
    clf = fit(X[:, idx], y, hp)
    joblib.dump({"model": clf, "threshold": thr, "input_index": idx, "selection": selection,
                 "alarm": alarm},
                export_dir / "model.joblib")
    convert_and_check(export_dir)


def cmd_convert(args) -> None:
    """Re-run C conversion and the parity check on the saved model (no retraining)."""
    convert_and_check(OUT / "export")


TV_CAPTURE = ("set_04", "test_04_unknown_vehicle_unknown_attack", "triple-1")
TV_FRAMES = 4000


def cmd_testvectors(args) -> None:
    """Copy the exported headers next to the C sources and write on-device test vectors.

    Expected scores come from the host build of the same C code, which the export step has
    checked against Python.
    """
    import shutil
    import subprocess

    export_dir = OUT / "export"
    gen = C_DIR / "generated"
    gen.mkdir(exist_ok=True)
    for name in (f"{MODEL_NAME}.h", "can_ids_tiny_config.h"):
        shutil.copy(export_dir / name, gen / name)

    set_name, split, cap = TV_CAPTURE
    df = load(DATA, set_name, split)[cap]
    first_attack = int(np.argmax(df["label"].to_numpy() == 1))
    start = max(0, first_attack - TV_FRAMES // 4)
    df = df.iloc[start:start + TV_FRAMES]
    rec = frames_to_bin(df)
    exe = build_host_scorer(export_dir)
    fin, fout = export_dir / "tv_frames.bin", export_dir / "tv_scores.bin"
    rec.tofile(fin)
    subprocess.run([str(exe), str(fin), str(fout)], check=True)
    scores = np.fromfile(fout, dtype=np.float32)
    labels = df["label"].to_numpy()
    cfg = json.loads((export_dir / "config.json").read_text())
    thr, alarm = cfg["threshold"], cfg["alarm"]
    n_alarms = int(alarms(rec["ts"], scores >= np.float32(thr), alarm["k"], alarm["window_ms"],
                          alarm["holdoff_ms"]).sum())

    lines = [
        "/* Generated by models/can-ids-tiny/pipeline.py testvectors. Do not edit.",
        f" * Source: can-train-and-test (CC BY 4.0), {set_name}/{split}/{cap}.csv,",
        f" * frames {start}..{start + len(df) - 1}. Expected scores from the host build. */",
        "#ifndef CAN_IDS_TINY_TEST_VECTORS_H",
        "#define CAN_IDS_TINY_TEST_VECTORS_H",
        "#include <stdint.h>",
        "",
        "/* Define TV_STORAGE as PROGMEM on targets that copy const data to RAM (ESP8266, AVR). */",
        "#ifndef TV_STORAGE",
        "#define TV_STORAGE",
        "#endif",
        "",
        "typedef struct {",
        "    int64_t ts_us;",
        "    uint16_t can_id;",
        "    uint8_t dlc;",
        "    uint8_t label;",
        "    uint8_t data[8];",
        "} tv_frame_t;",
        "",
        f"#define TV_N_FRAMES {len(df)}",
        f"#define TV_EXPECTED_ALARMS {n_alarms}",
        "",
        "static const tv_frame_t tv_frames[TV_N_FRAMES] TV_STORAGE = {",
    ]
    for r, lab in zip(rec, labels):
        data = ",".join(f"0x{b:02X}" for b in r["data"])
        lines.append(f"    {{{r['ts']}, 0x{r['can_id']:03X}, {r['dlc']}, {lab}, {{{data}}}}},")
    lines += ["};", "", "static const float tv_expected_score[TV_N_FRAMES] TV_STORAGE = {"]
    lines += [f"    {s!r}f," for s in scores.tolist()]
    lines += ["};", "", "#endif /* CAN_IDS_TINY_TEST_VECTORS_H */", ""]
    (gen / "test_vectors.h").write_text("\n".join(lines))
    fin.unlink()
    fout.unlink()
    print(f"{len(df)} frames, {int(labels.sum())} attack frames, "
          f"{int(((scores >= thr) & (labels == 1)).sum())} detected, {n_alarms} alarms on host")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--sets", nargs="+", default=list(SETS))
    ev.set_defaults(func=cmd_evaluate)
    ex = sub.add_parser("export")
    ex.set_defaults(func=cmd_export)
    al = sub.add_parser("alarms")
    al.set_defaults(func=cmd_alarms)
    cv = sub.add_parser("convert")
    cv.set_defaults(func=cmd_convert)
    tv = sub.add_parser("testvectors")
    tv.set_defaults(func=cmd_testvectors)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
