---
license: apache-2.0
pipeline_tag: tabular-classification
tags:
  - tinyml
  - microcontroller
  - esp32
  - esp32-s3
  - esp8266
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

**A CAN bus intrusion detector that fits in 10 KB of RAM and runs on a few-dollar microcontroller.**

can-ids-tiny scores every frame on a vehicle's CAN bus and raises an alarm when an attack is
likely. It is a 30-tree random forest exported to plain C, followed by a small alarm stage.

- **No ML runtime and no heap.** It runs on ESP32, ESP32-S3 and ESP8266, and any C99 target.
- **No vehicle-specific configuration.** No DBC file and no ID allow-list are needed.
- **Bit-identical on host and device.** The C code that produced every number below is the code
  that runs on the microcontroller.

| | |
|---|---|
| Task | CAN intrusion detection: per-frame score plus alarm stage |
| Input | Raw CAN frames: timestamp, 11-bit ID, DLC, payload |
| Model | Random forest, 30 trees, depth ≤ 12, 22 346 nodes, hard voting |
| Alarm stage | Alarm when 3 flagged frames fall within 200 ms, then 1 s hold-off (configurable) |
| RAM | 10.4 KB detector state (feature table for 255 IDs + alarm stage) |
| Flash (ESP32-S3) | ~90 KB code (model, features, detector) |
| Training data | [can-train-and-test](https://doi.org/10.11583/DTU.24805533), 4 vehicles, CC BY 4.0 |
| Host/device parity | Scores bit-identical on 800 000 test frames from 4 vehicles |
| Verified on | ESP32, ESP32-S3 (QEMU: 0 / 4 000 score mismatches, alarms as expected); ESP8266 build fits (hardware run pending) |

## Why this model

Most published CAN intrusion detectors report accuracies above 99 % on GPUs. Three things are
usually missing, and this model provides them:

1. **Evaluation on vehicles and attacks the model has never seen.** Every number below follows the
   four-way protocol of can-train-and-test: known or unknown vehicle × known or unknown attack.
2. **Operational metrics.** Alongside per-frame F1, the card reports attacks detected, time to
   alarm and false alarms per hour after alarm aggregation. That is the load a vehicle security
   operations centre would actually see.
3. **Proof that it fits ECU-class hardware.** Footprint and parity are measured on the target
   code, not estimated.

## How it works

1. **Features (`msml_can_features.c`).** A small C state machine computes 13 streaming features per
   frame from the frame and from what was seen *before* it on the bus. The model uses 12 of them.
   The raw CAN ID is left out on purpose, so the model cannot memorise vehicle-specific IDs.
2. **Random forest.** The share of 30 trees voting "attack" is the frame score. A frame is
   *flagged* when 17 or more trees vote attack (threshold 0.567).
3. **Alarm stage (`msml_alarm.c`).** An alarm is raised when 3 flagged frames fall within 200 ms.
   After an alarm, alarms are held off for 1 s. This is the kind of qualification an IDS manager
   such as AUTOSAR IdsM applies before reporting a security event.

| Feature | Meaning |
|---|---|
| `dt_id_ms` | Time since the previous frame with the same ID |
| `dt_ratio` | `dt_id_ms` divided by the running mean period of that ID; injected frames arrive "too early" |
| `dt_bus_ms`, `bus_dt_ewma_ms` | Time since the previous frame of any ID, and its running mean (bus load) |
| `id_count`, `warmup` | How often this ID and the bus have been seen (lets the model discount start-up) |
| `new_id_rate` | Running share of frames that carry a never-seen ID |
| `dlc`, `dlc_changed` | Payload length, and whether it differs from the previous frame of this ID |
| `hamming`, `bytes_changed`, `ham_ratio` | Payload change vs. the previous frame of this ID, absolute and relative to its usual change |

The feature table tracks up to 255 IDs at a time. The vehicles in the dataset use 51–98 IDs.
When fuzzing or ID scanning floods the bus with new IDs, the least-seen ID is evicted, so the
vehicle's periodic IDs keep their history.

## Evaluation

**Protocol.** For each of the four sets of can-train-and-test, the model is trained on `train_01`
and tested on four splits. Hyperparameters, the score threshold and the alarm rule are chosen on
held-out training captures. Each set has a different known/unknown vehicle pair: Chevrolet Impala,
Silverado, Traverse and Subaru Forester. The tables average over the four sets.

### Frame level

| Test split | F1 | F1 with raw CAN ID as feature | Recall |
|---|---|---|---|
| known vehicle, known attacks | **0.947** | 0.928 | 0.941 |
| **unknown vehicle**, known attacks | **0.861** | 0.888 | 0.895 |
| known vehicle, **unknown attacks** | **0.869** | 0.812 | 0.839 |
| **unknown vehicle, unknown attacks** | **0.812** | 0.798 | 0.785 |

### Alarms

An attack episode is a run of attack frames. A new episode starts after more than 1 s without
attack frames. An episode counts as detected if an alarm falls inside it or up to 1 s after it.
Every other alarm is a false alarm. False alarms per hour are counted over the recorded traffic.

| Test split | Alarm rule | Attacks detected | Median time to alarm | False alarms / h (median of 4 sets) | False alarms / h (mean) |
|---|---|---|---|---|---|
| known vehicle, known attacks | **3 in 200 ms** | 67 % | 10 ms | **0.5** | 3.4 |
| known vehicle, known attacks | 1 in 50 ms | 100 % | 0 ms | 3.6 | 12.0 |
| **unknown vehicle**, known attacks | **3 in 200 ms** | 62 % | 96 ms | **45.7** | 259.8 |
| **unknown vehicle**, known attacks | 1 in 50 ms | 82 % | 0 ms | 126.8 | 503.1 |
| known vehicle, **unknown attacks** | **3 in 200 ms** | 36 % | 34 ms | **8.6** | 10.7 |
| known vehicle, **unknown attacks** | 1 in 50 ms | 67 % | 0 ms | 20.4 | 41.7 |
| **unknown vehicle, unknown attacks** | **3 in 200 ms** | 71 % | 15 ms | **11.5** | 336.0 |
| **unknown vehicle, unknown attacks** | 1 in 50 ms | 79 % | 2 ms | 38.9 | 560.9 |

The default rule ("3 in 200 ms") was chosen on validation captures as the best detection rate
within a budget of 2 false alarms per hour. "1 in 50 ms" raises an alarm for every flagged frame
(at most once per second) and is shown for comparison. The alarm parameters are compile-time
constants in `can_ids_tiny_config.h`, so a deployment can choose its own trade-off.

**What the numbers say.**

- On a vehicle it was trained on, facing attack types it was trained on, the detector raises less
  than one false alarm per hour (median). It still detects two thirds of the attack episodes,
  within about 10 ms.
- On vehicles it has not seen, the per-frame classifier still works (F1 0.81–0.86), but some
  legitimate IDs of the new vehicle are flagged persistently. That produces tens of false alarms
  per hour.
- One pairing dominates the mean: trained on a Subaru Forester, tested on a Chevrolet Traverse
  (set_04). Alarm aggregation cannot remove persistent per-ID false positives. A short learning
  phase on the new vehicle is the planned fix (see Limitations).

Recall per attack type at frame level, averaged over all splits. "Seen" means the attack type was
in that set's training data.

| Attack | Seen in training | Not seen in training |
|---|---|---|
| DoS | 0.999 | 0.994 |
| interval | 0.953 | 1.000 |
| systematic (ID scan) | 0.966 | 0.334 |
| fuzzing | 0.849 | 0.445 |
| speed | 0.791 | 0.726 |
| rpm | 0.739 | 0.848 |
| standstill | 0.700 | 0.803 |
| force-neutral | 0.709 | 0.574 |
| double / triple (combined attacks) | 0.52 / 0.52 | 0.69 / 0.65 |

All 16 split results are in [`protocol_results.json`](protocol_results.json). For every split it
holds per-attack precision, the full alarm grid (k ∈ {1, 2, 3, 5, 8} × window ∈ {50, 200, 1000} ms)
and the hyperparameter search.

**The published model and its test set.** The published model is trained on `train_01` of all
four sets, so it has seen all four vehicles and all attack types. The sets' test splits overlap
with other sets' training data, so **the published model has no untouched test set of its own**.
The protocol numbers above are the honest estimate of how this recipe generalises.

## On-device verification

Benchmark firmware replays 4 000 recorded CAN frames from an unknown vehicle under an unknown
combined attack. It runs them through the full detector, checks every score and the number of
alarms against the host, and prints one JSON line. It needs no CAN transceiver. There are two
versions:
[ESP-IDF](https://github.com/mhabedank/mobility-security-ml/tree/main/models/can-ids-tiny/firmware)
for ESP32 targets and
[Arduino](https://github.com/mhabedank/mobility-security-ml/tree/main/models/can-ids-tiny/firmware-esp8266)
for ESP8266.

| Target | Score mismatches vs. host | Attack frames flagged | Alarms (expected) | Detector RAM | Environment |
|---|---|---|---|---|---|
| ESP32 | 0 / 4 000 | 732 / 738 | 2 (2) | 10.4 KB | QEMU |
| ESP32-S3 | 0 / 4 000 | 732 / 738 | 2 (2) | 10.4 KB | QEMU |
| ESP8266 (D1 mini) | – | – | – | 10.4 KB | builds; uses 55 of 80 KB RAM including the benchmark buffers |

Latency on real hardware will be added here. QEMU timings are not representative.

## Usage

```c
#include "can_ids_tiny.h"

static can_ids_tiny_t ids;
can_ids_tiny_init(&ids);

/* for every received frame, in bus order: */
float score;
if (can_ids_tiny_process(&ids, ts_us, can_id, dlc, data /* 8 bytes, zero-padded */, &score)) {
    /* raise a security event: CAN ID, timestamp, score */
}
```

The files are in [`c/`](c/):

| File | Content |
|---|---|
| `can_ids_tiny.[ch]` | API |
| `can_ids_tiny_model.h` | Generated forest |
| `can_ids_tiny_config.h` | Inputs, threshold, alarm rule |
| `msml_can_features.[ch]` | Feature extraction |
| `msml_alarm.[ch]` | Alarm stage |

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

- **Unknown vehicles raise false alarms.** Some legitimate IDs of an unseen vehicle are flagged
  persistently: median 12–46 false alarms per hour after aggregation, and up to about 1 300 per
  hour for one vehicle pair. Planned fix: a short learning phase that adapts the detector to a new
  vehicle's normal traffic.
- **Unknown attacks.** Attack types whose pattern differs from the training attacks are often
  missed. Examples: fuzzing (45 % frame recall when unseen) and systematic ID scanning (33 %).
- **Aggregation trades detection for fewer false alarms.** With the default rule, short attack
  episodes with few injected frames can go unreported.
- **Masquerade attacks.** Frames that replace a silenced ECU at its normal timing are not in the
  training data and are likely missed by timing-based features.
- **Data.** Four vehicles from two manufacturers, 11-bit IDs, classic CAN. Performance on other
  makes, on CAN FD and against real-world attack tooling is unknown.
- **No adversarial evaluation yet.** An attacker who knows the features can shape injection timing
  to evade the detector.

## Dual-use statement

The model, its features and its thresholds are public. An attacker could use them to tune
injection timing against this specific detector. We publish them anyway for three reasons: the
model is a research baseline, the feature design follows public literature, and openness makes
the detector easier to audit. Do not rely on this model as the only line of defence.

## Training details

- **Data.** `train_01` of set_01–set_04 of can-train-and-test. All attack frames and 10 % of benign
  frames are used for training. Features are reset at the start of every capture, as after an ECU
  boot.
- **Model.** scikit-learn `RandomForestClassifier(n_estimators=30, max_depth=12, min_samples_leaf=20)`,
  chosen from three sizes on held-out captures. Score threshold: 17 of 30 trees.
- **Export.** [emlearn](https://github.com/emlearn/emlearn), with split thresholds rewritten so
  that the float32 C comparison is exactly equivalent to scikit-learn's.

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
