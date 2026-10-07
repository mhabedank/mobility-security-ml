"""Publish the model zoo (and mirror permitted datasets) to the Hugging Face Hub.

    export HF_TOKEN=hf_...                       # write token of the org/user
    hilbench hub publish --org my-org --version 0.1.0          # private repos
    hilbench hub publish --org my-org --version 0.1.0 --dry-run # only render cards
    hilbench hub mirror-dataset uci-har --org my-org            # only CC BY / CC BY-SA data

Each model becomes its own (private by default) model repo
`<org>/hilbench-<model-name>` with
  README.md            model card: task, metrics, quantization, training data + license
  <name>.npz           quantized model for hilbench (QModel)
  <name>.h             C source for microinfer
  <name>.tflite        int8 TFLite (when the model was trained with TensorFlow)
  metadata.json        machine-readable summary
and a git tag `v<version>`. All repos are collected in the collection
"hilbench TinyML zoo".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .config import REPO_ROOT
from .ml.codegen import model_to_c
from .ml.model import QModel
from .ml.zoo import load_zoo

ARTIFACTS = REPO_ROOT / "models" / "zoo"
COLLECTION_TITLE = "hilbench TinyML zoo"
CARD_METRICS = ("float_accuracy", "int8_accuracy", "int8_precision", "int8_recall", "int8_f1",
                "int8_false_positive_rate", "float_auc", "int8_auc", "int8_pauc", "int8_window_auc",
                "int8_detection_rate", "threshold", "test_samples", "test_clips")
TARGETS = ["ESP8266", "ESP32", "ESP32-S3", "ESP32-C3", "RP2040", "RP2350", "STM32F4", "nRF52840"]


def repo_name(model_name: str) -> str:
    return "hilbench-" + model_name.replace("_", "-")


def model_license(m: QModel) -> str:
    """Weights trained on CC BY-SA data inherit share-alike; everything else is Apache-2.0."""
    for d in m.meta.get("datasets", []):
        if "SA" in d.get("license", "").upper().split("-"):
            return "cc-by-sa-4.0"
    return "apache-2.0"


def render_card(m: QModel, version: str) -> str:
    s = m.summary()
    meta = m.meta
    datasets = meta.get("datasets", [])
    lic = model_license(m)
    audio = any(d.get("id") == "mimii" for d in datasets)
    front = ["---", f"license: {lic}", "library_name: hilbench", "pipeline_tag: "
             + ("audio-classification" if audio else "tabular-classification"),
             "tags:", "- tinyml", "- int8", "- microcontroller", "- embedded", "- hardware-in-the-loop"]
    front += [f"- {t.lower()}" for t in ("esp32", "esp8266", "rp2040", "stm32")]
    if datasets:
        front.append("datasets:")
        front += [f"- {d['id']}" for d in datasets]
    metrics = {k: v for k, v in meta.items() if k in CARD_METRICS or k.startswith("int8_auc_")}
    front += ["---", ""]
    body = [
        f"# {m.name} (v{version})", "",
        m.description or "", "",
        "Part of the **hilbench TinyML zoo**: int8 models that are tested bit-exact on real "
        "microcontrollers by the [hardware-in-the-loop bench]"
        "(https://github.com/mhabedank/mobility-security-ml).", "",
        "## Model", "",
        "| | |", "|---|---|",
        f"| input | int8 {tuple(s['in_shape'])} (scale {m.input_scale:.6g}, zero point {m.input_zp}) |",
        f"| output | int8 {tuple(s['out_shape'])} (scale {m.output_scale:.6g}, zero point {m.output_zp}) |",
        f"| layers | {s['layers']} ({', '.join(sorted({l.op for l in m.layers}))}) |",
        f"| MACs / inference | {s['macs']:,} |",
        f"| parameters | {s['param_bytes']:,} bytes |",
        f"| activation arena | {s['arena_size']:,} bytes |",
        f"| CRC32 of parameters | `{s['crc32']}` |", "",
        "Arithmetic: TFLite-compatible int8 (asymmetric activations, symmetric per-channel weights). "
        "Runs on the portable `microinfer` engine (C99, no heap, no FPU) on " + ", ".join(TARGETS) + ".", "",
    ]
    if meta.get("classes"):
        body += ["Classes: " + ", ".join(f"`{c}`" for c in meta["classes"]), ""]
    if metrics:
        body += ["## Evaluation", "", "| metric | value |", "|---|---|"]
        body += [f"| {k} | {v:.4f} |" if isinstance(v, float) else f"| {k} | {v} |" for k, v in metrics.items()]
        body += ["", "int8 numbers are computed with the bit-exact host reference of the device engine."]
        if meta.get("task") == "anomaly":
            body += ["Anomaly score = mean squared reconstruction error of the dequantized output; "
                     "AUC/pAUC (max FPR 0.1) are computed per clip, `threshold` is the 95th percentile "
                     "of validation normals per window."]
        body += [""]
    body += ["## Training data", ""]
    if datasets:
        for d in datasets:
            body += [f"- **{d['title']}** - {d['license']} - {d['attribution']}. {d['citation']}. "
                     f"Source: {d['homepage']}"]
        body += ["", "The training data is not part of this repository; it is downloaded by "
                 "`hilbench data download` from the original publisher."]
    else:
        body += ["Synthetic data generated by `hilbench.ml.datasets` (no third-party data). "
                 "This is a **bench reference model**: use it to measure latency and correctness on "
                 "hardware, not for production decisions."]
    body += ["", "## Usage", "", "```bash",
             "git clone https://github.com/mhabedank/mobility-security-ml && cd mobility-security-ml",
             "pip install -e '.[hw]'",
             f"huggingface-cli download <org>/{repo_name(m.name)} {m.name}.npz --local-dir models/custom/",
             "hilbench zoo --codegen-only        # compile it into the bench firmware",
             "hilbench run --parallel            # flash + test on every connected board", "```", "",
             f"Other runtimes: `{m.name}.tflite` (when present) runs on TFLite Micro; `{m.name}.h` is "
             "standalone C for microinfer.", ""]
    body += ["## License", "", f"Model weights: `{lic}`."
             + (" Trained on CC BY-SA data, therefore share-alike." if lic == "cc-by-sa-4.0" else ""),
             "Attribution of the training data (above) must be retained when redistributing."]
    return "\n".join(front + body) + "\n"


def stage_model(m: QModel, version: str, out: Path) -> Path:
    d = out / repo_name(m.name)
    d.mkdir(parents=True, exist_ok=True)
    m.save(d / f"{m.name}.npz")
    (d / f"{m.name}.h").write_text("/* hilbench microinfer model - include after microinfer.h */\n"
                                   "#include \"microinfer.h\"\n\n" + model_to_c(m))
    tfl = ARTIFACTS / f"{m.name}.tflite"
    if tfl.exists() and m.meta.get("version") == version:
        (d / tfl.name).write_bytes(tfl.read_bytes())
    (d / "README.md").write_text(render_card(m, version))
    (d / "metadata.json").write_text(json.dumps({**m.summary(), "version": version,
                                                 "license": model_license(m), "meta": m.meta},
                                                indent=2, default=str) + "\n")
    return d


def select_models(version: str, names: list[str] | None, exclude: list[str] | None = None) -> list[QModel]:
    zoo = load_zoo()
    models = [m for n, m in zoo.items() if (not names or n in names) and n not in (exclude or [])]
    if not names:  # publish the models that belong to this version
        models = [m for m in models if m.meta.get("version", "0.1.0") == version]
    return models


def publish(org: str, version: str, private: bool = True, names: list[str] | None = None,
            dry_run: bool = False, out: Path | None = None, exclude: list[str] | None = None) -> list[str]:
    out = out or Path(tempfile.mkdtemp(prefix="hilbench-hub-"))
    models = select_models(version, names, exclude)
    if not models:
        raise SystemExit(f"no models with version {version} in the zoo")
    staged = [stage_model(m, version, out) for m in models]
    if dry_run:
        for d in staged:
            print(f"[dry-run] would publish {org}/{d.name} (private={private}) from {d}")
        return [f"{org}/{d.name}" for d in staged]

    from huggingface_hub import HfApi

    api = HfApi(token=os.environ.get("HF_TOKEN"))
    who = api.whoami()
    org = org or who["name"]
    repos = []
    for d in staged:
        repo_id = f"{org}/{d.name}"
        api.create_repo(repo_id, private=private, exist_ok=True, repo_type="model")
        commit = api.upload_folder(repo_id=repo_id, folder_path=str(d), commit_message=f"hilbench zoo v{version}")
        api.create_tag(repo_id, tag=f"v{version}", revision=commit.oid, exist_ok=True)
        print(f"published {repo_id} @ v{version}", flush=True)
        repos.append(repo_id)
    try:
        coll = next((c for c in api.list_collections(owner=org) if c.title == COLLECTION_TITLE), None)
        if coll is None:
            coll = api.create_collection(COLLECTION_TITLE, namespace=org, private=private,
                                         description="int8 TinyML models tested on real MCUs with hilbench")
        for r in repos:
            api.add_collection_item(coll.slug, item_id=r, item_type="model", exists_ok=True)
    except Exception as e:  # collections are a convenience only
        print(f"note: collection not updated: {e}", file=sys.stderr)
    return repos


def mirror_dataset(ds_id: str, org: str, private: bool = True) -> str:
    """Mirror a dataset that the registry marks as re-hostable, with full attribution."""
    from huggingface_hub import HfApi

    from .data.download import download
    from .data.registry import SOURCES

    src = SOURCES[ds_id]
    if not src.hf_rehost.startswith("yes"):
        raise SystemExit(f"{ds_id}: license does not allow re-hosting ({src.hf_rehost})")
    d = download(ds_id, extract=False)
    lic = src.license.lower()
    card = "\n".join([
        "---", f"license: {lic}", "tags:", "- tinyml", "- hilbench", "---", "",
        f"# {src.title} (mirror)", "",
        f"Unmodified mirror of **{src.title}** for the hilbench TinyML bench.", "",
        f"- Original: {src.homepage}", f"- License: [{src.license}]({src.license_url})",
        f"- Attribution: {src.attribution}", f"- Cite: {src.citation}", "",
        "No changes were made to the files. All rights remain with the original authors; "
        "this mirror is provided under the same license.",
    ]) + "\n"
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    repo_id = f"{org}/hilbench-data-{ds_id}"
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)
    api.upload_file(path_or_fileobj=card.encode(), path_in_repo="README.md", repo_id=repo_id, repo_type="dataset")
    api.upload_folder(repo_id=repo_id, repo_type="dataset", folder_path=str(d / "raw"), path_in_repo="raw")
    api.upload_file(path_or_fileobj=str(d / "SOURCE.json"), path_in_repo="SOURCE.json", repo_id=repo_id,
                    repo_type="dataset")
    return repo_id


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--org", default=os.environ.get("HF_ORG", ""))
    p.add_argument("--version", required=True)
    p.add_argument("--public", action="store_true", help="create public repos (default: private)")
    p.add_argument("--model", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[], help="model name to leave out (repeatable)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", type=Path)
    p = sub.add_parser("mirror-dataset")
    p.add_argument("dataset")
    p.add_argument("--org", default=os.environ.get("HF_ORG", ""))
    p.add_argument("--public", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "publish":
        publish(args.org, args.version, private=not args.public, names=args.model or None,
                dry_run=args.dry_run, out=args.out, exclude=args.exclude)
    else:
        print(mirror_dataset(args.dataset, args.org, private=not args.public))
    return 0


if __name__ == "__main__":
    sys.exit(main())
