---
license: apache-2.0
pipeline_tag: tabular-classification
tags:
  - tinyml
  - microcontroller
  - esp32
  - esp32-s3
  - emlearn
  - random-forest
  - can-bus
  - automotive
  - automotive-security
  - intrusion-detection
  - anomaly-detection
  - cybersecurity
metrics:
  - f1
  - precision
  - recall
  - average_precision
---

# can-ids-tiny

**A CAN bus intrusion detector that runs on a few-dollar microcontroller.**

can-ids-tiny classifies every frame on a vehicle's CAN bus as *benign* or *attack*. It is a
20-tree random forest exported to plain C. Feature extraction and the model need about
**50 KB of flash and 64 KB of RAM**. It runs on an ESP32 or ESP32-S3 with no ML runtime, no
heap allocation and no vehicle-specific configuration: no DBC file and no ID allow-list.

| | |
|---|---|
| Task | Frame-level CAN intrusion detection (binary) |
| Input | Raw CAN frames: timestamp, 11-bit ID, DLC, payload |
| Model | Random forest, 20 trees, depth ≤ 10, 11 244 nodes, hard voting |
| Footprint (ESP32-S3) | ~50 KB flash code, 64 KB RAM state (2048 IDs × 32 B) |
| Training data | [can-train-and-test](https://doi.org/10.11583/DTU.24805533), 4 vehicles (CC BY 4.0) |
| Host/device parity | C and Python scores are **bit-identical** on 800 000 test frames |
| Verified on | ESP32 and ESP32-S3 (QEMU; 0 mismatches on 4 000 replayed frames) |

## Why this model

Most published CAN intrusion detectors report accuracies above 99 % on GPUs. Two things are
usually missing:

1. **Evaluation on vehicles and attacks the model has never seen.** Here every number below
   comes from the four-way protocol of can-train-and-test (known/unknown vehicle × known/unknown
   attack).
2. **Proof that the detector fits the ECU-class hardware it is meant for.** Here the exact C code
   that produced the evaluation scores is the code that runs on the microcontroller.

## How it works

For each frame a small C state machine (`msml_can_features.c`) computes 13 streaming features
from the frame and from what was seen *before* it on the bus. The published model uses 12 of
them. The raw CAN ID is left out on purpose, so the model cannot memorise vehicle-specific IDs.

| Feature | Meaning |
|---|---|
| `dt_id_ms` | Time since the previous frame with the same ID |
| `dt_ratio` | `dt_id_ms` divided by the running mean period of that ID; injected frames arrive "too early" |
| `dt_bus_ms`, `bus_dt_ewma_ms` | Time since the previous frame of any ID, and its running mean (bus load) |
| `id_count`, `warmup` | How often this ID and the bus have been seen (lets the model discount start-up) |
| `new_id_rate` | Running share of frames that carry a never-seen ID |
| `dlc`, `dlc_changed` | Payload length, and whether it differs from the previous frame of this ID |
| `hamming`, `bytes_changed`, `ham_ratio` | Payload change vs. the previous frame of this ID, absolute and relative to its usual change |

## Evaluation

Protocol: for each of the four sets of can-train-and-test, train on `train_01` and test on four
splits. Hyperparameters and the decision threshold are chosen on held-out training captures.
The table shows the mean over the four sets (each set has a different known/unknown vehicle pair:
Chevrolet Impala, Silverado, Traverse and Subaru Forester).

| Test split | F1 (published features) | F1 (with raw CAN ID) | Recall | False alarms / h |
|---|---|---|---|---|
| known vehicle, known attacks | **0.907** | 0.893 | 0.877 | 39.4 |
| **unknown vehicle**, known attacks | **0.675** | 0.773 | 0.741 | 60.8 |
| known vehicle, **unknown attacks** | **0.849** | 0.739 | 0.801 | 33.8 |
| **unknown vehicle, unknown attacks** | **0.697** | 0.617 | 0.658 | 52.2 |

Recall per attack type (mean over all splits; "seen" means the attack type was in that set's
training data):

| Attack | Seen in training | Not seen in training |
|---|---|---|
| DoS | 0.985 | 0.997 |
| interval | 0.954 | 0.964 |
| speed | 0.844 | 0.626 |
| systematic | 0.838 | 0.289 |
| rpm | 0.742 | 0.709 |
| standstill | 0.698 | 0.673 |
| fuzzing | 0.623 | 0.211 |
| force-neutral | 0.588 | 0.573 |
| double / triple (combined attacks) | 0.34 / 0.37 | 0.70 / 0.66 |

All 16 split results, per-attack precision and the hyperparameter search are in
[`protocol_results.json`](protocol_results.json).

**How to read the false-alarm rate.** A false alarm is a cluster of benign frames flagged within
one second. The rate is computed on the benign traffic inside the test captures, per hour of
recorded traffic. At 30–60 alarms per hour, the raw per-frame output is **not** ready to feed a
vehicle SOC directly. It needs an aggregation stage, for example "k flagged frames of the same ID
within T ms", as AUTOSAR IdsM provides. Measuring that stage is the next step (see Limitations).

The published model is trained on `train_01` of all four sets, so it has seen all four vehicles
and all attack types. Because the sets' test splits overlap with other sets' training data,
**the published model has no untouched test set of its own**. The protocol numbers above are the
honest estimate of how this recipe generalises.

## On-device verification

The benchmark firmware in [`firmware/`](https://github.com/mhabedank/mobility-security-ml/tree/main/models/can-ids-tiny/firmware)
replays 4 000 recorded CAN frames (unknown vehicle, unknown combined attack) through the full
detector. It checks every score against the host result and prints one JSON line. It needs no CAN
transceiver.

| Target | Score mismatches vs. host | Attack frames detected | State RAM | Environment |
|---|---|---|---|---|
| ESP32 | 0 / 4 000 | 730 / 738 | 64 KB | QEMU |
| ESP32-S3 | 0 / 4 000 | 730 / 738 | 64 KB | QEMU |

Latency on real hardware will be added here. QEMU timings are not representative.

## Usage

```c
#include "can_ids_tiny.h"

static can_ids_tiny_t ids;
can_ids_tiny_init(&ids);

/* for every received frame, in bus order: */
float score = can_ids_tiny_score(&ids, ts_us, can_id, dlc, data /* 8 bytes, zero-padded */);
if (score >= can_ids_tiny_threshold()) {
    /* report a security event: CAN ID, timestamp, score */
}
```

Files in [`c/`](c/): `can_ids_tiny.[ch]` (API), `can_ids_tiny_model.h` (generated forest),
`can_ids_tiny_config.h` (inputs and threshold) and `msml_can_features.[ch]` (feature extraction).
Compile with `-ffp-contract=off` to keep results bit-identical to the reference.

## Intended use

- Research, teaching and bench testing of in-vehicle intrusion detection.
- A baseline for TinyML intrusion detection on microcontrollers.
- A starting point for a security sensor that reports events to an IDS manager.

## Out of scope

- Deployment in vehicles on public roads. This model is **not** a validated or certified safety
  or security mechanism and makes no ISO/SAE 21434 or UNECE R155 claim.
- Active countermeasures (blocking or injecting frames) based on its output.

## Limitations

- **False alarms.** The per-frame output raises 30–60 alarm clusters per hour of benign traffic.
  It needs alarm aggregation before operational use.
- **Unknown vehicles.** F1 drops from about 0.9 to about 0.7 on vehicles not seen in training. On
  one pairing (set_04: trained on a Subaru Forester, tested on a Chevrolet Traverse) precision
  falls to 0.13.
- **Unknown attacks.** Attacks whose pattern differs from the training attacks are often missed,
  for example fuzzing (21 % recall when unseen) and systematic ID scanning (29 %).
- **Masquerade attacks.** Frames that replace a silenced ECU at its normal timing are not in the
  training data and are likely missed by timing-based features.
- **Data.** Four vehicles from two manufacturers, 11-bit IDs, classic CAN. Performance on other
  makes, on CAN FD and on real-world attack tooling is unknown.
- **No adversarial evaluation yet.** An attacker who knows the features can shape injection timing
  to evade it.

## Dual-use statement

The model, its features and its threshold are public. An attacker could use them to tune
injection timing against this specific detector. We publish them anyway because the model is a
research baseline, the feature design follows public literature, and openness makes the detector
easier to audit. Do not rely on this model as the only line of defence.

## Training details

- Data: `train_01` of set_01–set_04 of can-train-and-test. All attack frames and 10 % of benign
  frames are used for training. Features are reset at the start of every capture, as after an ECU
  boot.
- Model: scikit-learn `RandomForestClassifier(n_estimators=20, max_depth=10, min_samples_leaf=20)`,
  chosen from three sizes on held-out captures. Decision threshold: 13 of 20 trees (0.65).
- Export: [emlearn](https://github.com/emlearn/emlearn), with split thresholds rewritten so that
  the float32 C comparison is exactly equivalent to scikit-learn's.

Reproduce with:

```bash
git clone https://github.com/mhabedank/mobility-security-ml && cd mobility-security-ml
uv sync
uv run python -m msml.datasets.can_train_and_test         # download (~7.5 GB CSV)
uv run python models/can-ids-tiny/pipeline.py evaluate    # protocol results
uv run python models/can-ids-tiny/pipeline.py export      # final model + parity check
```

## Data attribution

Trained on **can-train-and-test** by Brooke Lampe (Kidmose) and Weizhi Meng, licensed under
CC BY 4.0: B. Lampe and W. Meng, "can-train-and-test: A Curated CAN Dataset for Automotive
Intrusion Detection", [arXiv:2308.04972](https://arxiv.org/abs/2308.04972). Dataset DOI:
[10.11583/DTU.24805533](https://doi.org/10.11583/DTU.24805533).

## License

Code and model: Apache-2.0. The training data is CC BY 4.0 and requires the attribution above.
