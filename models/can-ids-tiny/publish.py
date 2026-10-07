"""Assemble the Hugging Face repository folder for can-ids-tiny and optionally upload it.

    python models/can-ids-tiny/publish.py                       # build artifacts/can-ids-tiny/hf/
    python models/can-ids-tiny/publish.py --repo ORG/can-ids-tiny --upload   # needs HF_TOKEN

The model card is models/can-ids-tiny/MODEL_CARD.md; the evaluation tables in it are generated
from results/protocol_results.json by `tables`.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ART = REPO / "artifacts" / "can-ids-tiny"
RESULTS = HERE / "results"  # versioned copies of protocol results, export config, benchmarks
HF_DIR = ART / "hf"
SPLIT_LABELS = {
    "test_01_known_vehicle_known_attack": "known vehicle, known attacks",
    "test_02_unknown_vehicle_known_attack": "**unknown vehicle**, known attacks",
    "test_03_known_vehicle_unknown_attack": "known vehicle, **unknown attacks**",
    "test_04_unknown_vehicle_unknown_attack": "**unknown vehicle, unknown attacks**",
}


def protocol_table(results: dict, feature_set: str = "no_can_id") -> str:
    rows = ["| Set | Test split | Vehicle | F1 | Precision | Recall | AUC-PR | False alarms / h |",
            "|---|---|---|---|---|---|---|---|"]
    for set_name, entry in results.items():
        for split, r in entry[feature_set]["splits"].items():
            rows.append(
                f"| {set_name} | {SPLIT_LABELS[split]} | {r['vehicle'].replace('_', ' ')} "
                f"| {r['f1']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} "
                f"| {r['auc_pr']:.3f} | {r['false_alarms_per_hour']:.1f} |")
    return "\n".join(rows)


def summary_table(results: dict) -> str:
    """Mean over the four sets per split type, with and without the raw CAN ID feature."""
    rows = ["| Test split | F1 (no CAN ID, published) | F1 (with CAN ID) | Recall | False alarms / h |",
            "|---|---|---|---|---|"]
    def mean(split, fs, key):
        vals = [results[s][fs]["splits"][split][key] for s in results]
        return sum(vals) / len(vals)

    for split, label in SPLIT_LABELS.items():
        rows.append(f"| {label} | {mean(split, 'no_can_id', 'f1'):.3f} "
                    f"| {mean(split, 'full', 'f1'):.3f} "
                    f"| {mean(split, 'no_can_id', 'recall'):.3f} "
                    f"| {mean(split, 'no_can_id', 'false_alarms_per_hour'):.1f} |")
    return "\n".join(rows)


def per_attack_table(results: dict, feature_set: str = "no_can_id") -> str:
    """Recall per attack type, split by whether the attack type was in the training set."""
    seen, unseen = {}, {}
    for entry in results.values():
        for split, r in entry[feature_set]["splits"].items():
            target = unseen if "unknown_attack" in split else seen
            for att, m in r["per_attack"].items():
                target.setdefault(att, []).append(m["recall"])
    attacks = sorted(set(seen) | set(unseen))
    rows = ["| Attack | Recall when seen in training | Recall when not seen in training |",
            "|---|---|---|"]
    def fmt(d, a):
        return f"{sum(d[a]) / len(d[a]):.3f}" if a in d else "–"

    for a in attacks:
        rows.append(f"| {a} | {fmt(seen, a)} | {fmt(unseen, a)} |")
    return "\n".join(rows)


def cmd_tables(_args) -> None:
    results = json.loads((RESULTS / "protocol_results.json").read_text())
    print("## Summary\n")
    print(summary_table(results))
    print("\n## Per attack\n")
    print(per_attack_table(results))
    print("\n## All splits\n")
    print(protocol_table(results))


def build() -> Path:
    if HF_DIR.exists():
        shutil.rmtree(HF_DIR)
    (HF_DIR / "c").mkdir(parents=True)
    shutil.copy(HERE / "MODEL_CARD.md", HF_DIR / "README.md")
    shutil.copy(RESULTS / "config.json", HF_DIR / "config.json")
    shutil.copy(RESULTS / "protocol_results.json", HF_DIR / "protocol_results.json")
    for p in (HERE / "c").glob("*.[ch]"):
        if p.name != "host_score.c":
            shutil.copy(p, HF_DIR / "c" / p.name)
    for p in (HERE / "c" / "generated").glob("*.h"):
        shutil.copy(p, HF_DIR / "c" / p.name)
    feat = REPO / "firmware" / "components" / "msml_can_features"
    shutil.copy(feat / "msml_can_features.c", HF_DIR / "c")
    shutil.copy(feat / "include" / "msml_can_features.h", HF_DIR / "c")
    bench = RESULTS / "benchmarks"
    if bench.exists():
        shutil.copytree(bench, HF_DIR / "benchmarks")
    shutil.copy(REPO / "LICENSE", HF_DIR / "LICENSE")
    return HF_DIR


def cmd_build(args) -> None:
    out = build()
    print(f"built {out}")
    if args.upload:
        from huggingface_hub import HfApi  # optional dependency

        api = HfApi()
        api.create_repo(args.repo, repo_type="model", private=args.private, exist_ok=True)
        api.upload_folder(repo_id=args.repo, folder_path=str(out),
                          commit_message=args.message)
        print(f"uploaded to https://huggingface.co/{args.repo}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    t = sub.add_parser("tables")
    t.set_defaults(func=cmd_tables)
    b = sub.add_parser("build")
    b.add_argument("--repo")
    b.add_argument("--upload", action="store_true")
    b.add_argument("--private", action="store_true")
    b.add_argument("--message", default="Upload can-ids-tiny")
    b.set_defaults(func=cmd_build)
    args = ap.parse_args()
    if args.cmd is None:
        ap.print_help()
        return
    if getattr(args, "upload", False) and not args.repo:
        ap.error("--upload needs --repo")
    args.func(args)


if __name__ == "__main__":
    main()
