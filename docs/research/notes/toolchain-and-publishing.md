# TinyML Toolchain Research: Automotive / Mobility Security Models on MCUs

Research date: 2026-10-07. Targets: ESP32-S3 (primary), STM32, NXP MCUs. Publishing: Hugging Face org.

## Verification legend

- **[V]**: verified today from a primary source (PyPI JSON API, package wheel source, raw GitHub README or doc, or a fetched vendor page).
- **[S]**: taken from search-engine snippets only. Probably right, but check before relying on it.
- **[U]**: unverified or from background knowledge. Confirm before using it in docs or code.

Access limits during this research: huggingface.co, arxiv.org, docs.espressif.com, ai.google.dev, docs.pytorch.org, st.com, nxp.com, eur-lex and wokwi docs were blocked by the egress proxy. Context7 quota was exhausted, and the web-search budget ran out partway through. Claims about those sites were checked indirectly where possible: the `huggingface_hub` wheel source, `huggingface.js` and `hub-docs` on raw GitHub, and the PyPI API.

---

## 0. TL;DR recommendations

1. **Use classical ML first for CAN IDS**: decision trees, random forests and extra trees on engineered CAN features (inter-arrival time, ID frequency, payload entropy, byte deltas). Export them with **emlearn** (MIT, maintained, v0.23.2 in Apr 2026 [V]). It produces C99 code with no malloc and works on ESP32, STM32 and NXP alike. `micromlgen` (last release 2022) and `m2cgen` (last release 2022) are stale [V]. Use them only as references.
2. **Primary neural-network path, chosen for portability: Keras 3 (TensorFlow backend)**.
   - Export full-integer int8 **`.tflite`** (LiteRT flatbuffer). This is the deployment contract. TFLM runs it on ESP32-S3 (esp-tflite-micro with ESP-NN), STM32 (TFLM, or ST Edge AI Core importing the `.tflite`), and NXP (eIQ TFLM, or the Neutron NPU converter). It is also the MLPerf Tiny reference format.
   - Also export **ONNX** from the same model (`model.export(format="onnx")`, Keras 3.15 [V]). Feed it to **ESP-PPQ**, which produces a **`.espdl`** file for the fastest ESP32-S3 inference (PIE SIMD), and to ST Edge AI Core when needed.
   - Keras 3.15.1 [V] supports `model.export(format="litert", representative_dataset=..., optimizations=..., inference_input_type=...)`. The kwargs are passed through to the TFLite converter [V, from the source].
3. **Secondary path: PyTorch** (when a model needs PyTorch-only research code).
   - torch.export → ONNX → ESP-PPQ (ESP32-S3) or ST Edge AI Core (STM32).
   - For TFLM: `litert-torch` (renamed from `ai-edge-torch`, which is deprecated [V]) with PT2E static int8. Alternatively onnx2tf → full-int8 `.tflite`.
   - Check every `.tflite` produced this way against the `tflite-micro` Python interpreter in CI. The litert-torch docs only show *dynamic-range* PT2E examples [V]. Full-int8 TFLM compatibility is per-model and not guaranteed [U].
4. **Quantization**:
   - Default to int8 PTQ with a representative dataset of normal and attack traffic.
   - Use QAT only when PTQ loses more than about 1 pp F1. tfmot QAT requires `tf-keras` (Keras 2), not Keras 3 [V: `tensorflow-model-optimization` 0.8.1 requires `tf-keras>=2.14.1`].
   - Alternatives for QAT: PyTorch PT2E QAT (torchao), or ESP-PPQ TQT / mixed w8a16 [V].
5. **Test without hardware in CI**:
   - Espressif QEMU emulates **ESP32-S3**, including **TWAI/CAN** [V].
   - Renode covers STM32F4/H7, i.MX RT1064 and nRF52840 [V]. It has **no ESP32-S3 platform file** [V].
   - Wokwi CI (`wokwi/wokwi-ci-action@v1`, needs a token) covers ESP32-S3 serial-output assertions [V].
   - Emulators are for functional and bit-exact tests only. Measure latency and energy on real boards.
6. **Hugging Face**:
   - Publish each model as its own repo under the org, with `library_name: litert` for `.tflite` (the official HF library key; it counts downloads on `*.tflite` [V]).
   - Tags: `tinyml`, `tflite`, `int8`, `esp32-s3`, `can-bus`, `intrusion-detection`, `automotive-security`.
   - Include ONNX / espdl / C-header artifacts, the security-specific model-card sections (section 3.5) and a `LICENSE` that is compatible with the dataset terms.
   - Upload with `huggingface_hub` 2.1.1 (`HfApi.upload_folder`, `create_repo`, `update_repo_settings(gated=...)`). The CLI command is `hf` [V].
7. **Repo layout**:
   - uv workspace monorepo, with `models/<name>/` each holding a config, train, export, eval, firmware and model card.
   - Shared `packages/` for dataset loaders, export and benchmarking. `firmware/components/` as ESP-IDF components.
   - Hydra configs, DVC for data and artifacts, MLflow (self-hosted) for experiment tracking.

---

## 1. Training & conversion pipeline

### 1.1 Current state of the ecosystem (as of 2026-10)

| Component | Status / version | Notes | Verif. |
|---|---|---|---|
| TensorFlow | 2.21.0 (PyPI, 2026-03-06). The master RELEASE.md already lists 2.22 and 2.23 as in progress. | The 2.20 notes say `tf.lite` will be **removed from the TF Python package in future**. The LiteRT code base is decoupling into `google-ai-edge/LiteRT`. | [V] |
| LiteRT (formerly TFLite) | `ai-edge-litert` 2.3.0 (2026-10-06) | The wheel ships `ai_edge_litert/tflite/converter/*` and `_pywrap_litert_converter.so`, so the converter is moving out of TF. Its Python API surface was not checked [U]. The `.tflite` format and extension are unchanged. | [V] wheel contents |
| LiteRT for Microcontrollers (TFLM) | `tensorflow/tflite-micro` is active. The README still says "TensorFlow Lite for Microcontrollers", while Google docs brand it "LiteRT for Microcontrollers". The `tflite-micro` pip package publishes nightly dev builds (0.dev20261002) with a Python `Interpreter` (`from_file`, `invoke`, `print_allocations`). | The current dev wheel is cp313 only [V]. Use this interpreter for host-side bit-exact checks and arena sizing. | [V] |
| esp-tflite-micro | Espressif's TFLM port plus ESP-NN. Supports IDF v5.1–v6.0. `idf.py add-dependency "esp-tflite-micro"`. | ESP-NN gives a large speedup on S3 (README: person detection drops from 2300 ms to 54 ms). | [V] |
| ESP-IDF | v6.1 is the latest stable on the releases page, with v6.0.x and v5.5 maintained. | The dates shown by the fetch tool were garbled. | [V] version / [U] date |
| ESP-DL | v3.3.x (component). **v3.3.11 (2026-09-01) adds full w8a16 mixed quantization.** `.espdl` FlatBuffers format, static memory planner, dual-core Conv. Since Apr 2026, per-channel Conv/Gemm on P4. LSTM/GRU/Gemm/MatMul/Softmax ops listed. Requires IDF ≥ 5.3. | Takes **ONNX only**. PyTorch and TF must go through ONNX first. No `.tflite` input. Without PIE (ESP32, C3, C5, C6, S2) it falls back to slow C code. The **S3 and P4 have PIE SIMD.** | [V] |
| ESP-PPQ | `esp-ppq` 1.3.11 (2026-09-02). Renamed from `ppq` in July 2025. Supports PTQ, TQT, AutoQuant, and an "espdl-quantize" agent skill. | `pip install esp-ppq` | [V] |
| ExecuTorch | 1.5.1 (2026-09-22). The Cortex-M backend is **beta**: CMSIS-NN-based operator dialect plus `CortexMQuantizer`, validated on MLPerf Tiny and MobileNetV2. Unsupported ops stay fp32 on portable kernels. Backends also exist for Ethos-U, NXP eIQ Neutron and Cadence. | **No Espressif ESP32 / Xtensa-LX7 backend.** The Cadence backend targets HiFi/Fusion DSPs, not ESP32 [S]. Not suitable as the primary path for ESP32-S3. | [V] / [S] |
| litert-torch | 0.9.4 (2026-08-24). `ai-edge-torch` 0.7.2 is marked "DEPRECATED: renamed to litert-torch". | `litert_torch.convert(model.eval(), sample_inputs)`. PT2E quantization via `litert_torch.quantize.pt2e_quantizer.PT2EQuantizer`. Doc examples use `is_dynamic=True`. | [V] |
| Keras | 3.15.1 (2026-07-29). `model.export(format=...)` accepts `tf_saved_model`, `onnx`, `openvino`, `litert`, `torch`. | LiteRT export needs the TF or Torch backend. With the Torch backend you must give a static `input_signature`. | [V] source |
| tfmot (TF Model Optimization) | 0.8.1 (2026-05-12). **Requires `tf-keras`** (Keras 2). | Keras 3 models cannot use tfmot QAT directly. | [V] |
| onnx2tf | 2.6.9 (2026-09-14) | Community ONNX → TF / `.tflite` path, including full-int8. | [V] version |
| ST Edge AI Core | 4.0.0 (adds STM32V8 Cortex-M85, STM32U3, and the Stellar SR6 P3E automotive MCU). Imports Keras, `.tflite` (schema v2.18) and ONNX (opset ≤ 20, int8 QDQ). Imports scikit-learn models (isolation forest, SVM, k-means) via ONNX. | Replaces X-CUBE-AI as the core compiler. ST Edge AI Developer Cloud offers remote benchmarking on real boards [U]. | [S] |
| NXP eIQ | eIQ Toolkit / Portal. eIQ **Time Series Studio** (AutoML for classical ML and NN on time series). eIQ Inference with TFLM in the MCUXpresso SDK. eIQ **Neutron SDK / Neutron converter** for the NPU on MCX N and i.MX RT700. | The Neutron path takes int8 `.tflite` [U]. | [S] |
| Edge Impulse | Qualcomm announced the acquisition in March 2025. Branded "Edge Impulse, a Qualcomm company". The brand and site were retained. | Closing was not confirmed in the sources fetched [U]. It is useful for quick baselines and the EON compiler, but it is a SaaS lock-in. Do not make it the core pipeline. | [S] |
| emlearn | 0.23.2 (2026-04-02). MIT. RF, ExtraTrees, DecisionTree, MLP (sklearn/Keras), GaussianNB, EllipticEnvelope, GMM. Fixed-point for some models. Ships as an Arduino library and a Zephyr module. | No malloc; "from 2 kB flash / 50 B RAM". Best fit for CAN IDS trees. | [V] |
| micromlgen / m2cgen | 1.1.28 / 0.10.0, last released April 2022 | Stale. Avoid for new work. | [V] |
| MCUNet / TinyEngine | Last news entry 2024/03. Research code, STM32H7/OpenMV-centric. | Use for inspiration (patch-based inference, TinyNAS). Not a production toolchain. | [V] |
| NNCF | 3.4.0 | OpenVINO-centric. Not an MCU path. | [V] version |
| Brevitas | 0.13.4 | PyTorch QAT. Exports QONNX/QCDQ, which suits FPGA/QONNX flows more than MCUs. | [V] version |

### 1.2 Deployment matrix

| Target | Best runtime | Input artifact | Quantization | Notes |
|---|---|---|---|---|
| ESP32-S3 (fastest) | **ESP-DL v3** | `.espdl` from ESP-PPQ (from ONNX) | int8 / int16 / w8a16, symmetric per-tensor (per-channel on P4) | PIE SIMD, LUT activations, memory planner. |
| ESP32-S3 (portable) | **esp-tflite-micro + ESP-NN** | int8 `.tflite` | int8 full-integer | Same artifact as STM32 and NXP. Simpler to keep consistent. |
| ESP32-S3 (classical) | **emlearn** | generated C header | float or fixed-point | Trees run in microseconds. |
| STM32 | **ST Edge AI Core** (or plain TFLM + CMSIS-NN) | `.tflite` int8 or ONNX QDQ; sklearn via ONNX | int8 | Use ST Edge AI's `analyze`/`validate` for RAM/flash/MACC reports. |
| NXP MCX N / i.MX RT | **eIQ TFLM** (+ Neutron NPU) | int8 `.tflite` | int8 | Also ExecuTorch Neutron backend [S]. |
| Cortex-M (alt) | ExecuTorch Cortex-M backend (beta) | `.pte` | int8 via CortexMQuantizer | Optional future path. |

### 1.3 Recommended primary pipeline

```text
data (DVC) -> features (shared lib) -> train (Keras 3, TF backend; or sklearn)
   |-> sklearn trees -> emlearn.convert(...).save(file="model.h")      [classical]
   |-> NN fp32 -> model.export(format="litert", representative_dataset=..., 
   |              optimizations=[tf.lite.Optimize.DEFAULT],
   |              target_spec={"supported_ops":[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]},
   |              inference_input_type=tf.int8, inference_output_type=tf.int8) -> model_int8.tflite
   |-> NN fp32 -> model.export(format="onnx") -> esp-ppq (PTQ/TQT, calib set) -> model.espdl
   |-> (optional) ONNX -> onnxruntime static QDQ int8 -> ST Edge AI Core
   v
contract tests (CI): tflite-micro Python interpreter == LiteRT interpreter (bit-exact int8),
                     espdl test vectors, F1/recall delta vs fp32 <= threshold,
                     arena size (print_allocations) <= budget
   v
firmware build (ESP-IDF component embedding model) -> QEMU/Wokwi smoke test -> HIL benchmark
   v
HF publish (huggingface_hub.upload_folder) with model card + metrics
```

How the Keras export call works [V from Keras source]: `export_litert` uses `setattr(converter, attr, value)` for each kwarg and handles nested `target_spec` dicts. Attribute names like `inference_input_type` therefore pass straight through to the TFLite converter. The TFLite converter behaviour itself is [U] for TF ≥ 2.22, given the planned removal of `tf.lite`. Pin TF 2.21 and track `ai-edge-litert`'s converter.

Why Keras 3 is primary rather than PyTorch:

- The TF/LiteRT converter is still the most mature producer of full-integer TFLM-compatible flatbuffers.
- That `.tflite` is the one artifact all three vendor toolchains ingest: ST Edge AI, NXP eIQ / Neutron, and esp-tflite-micro.
- The Keras ONNX export covers ESP-DL.
- If the team strongly prefers PyTorch, swap the trainer and keep the same artifact contract (int8 `.tflite` + ONNX). Expect more per-model conversion debugging (onnx2tf or litert-torch).

Notes on quantization:

- **Inputs**: Quantize inputs as int8 (with a feature-scaling layer baked into the model) so the firmware can feed integer features directly from the CAN frame parser.
- **Calibration set**: Use a stratified sample, a few hundred to 1–2k windows, that includes rare attack classes. Without the attack classes the activation ranges get clipped and recall drops.
- **What to report**: fp32 vs int8 metrics (F1, recall at a fixed false-positive rate, latency), plus the per-class delta.
- **int16 activations**: ESP-PPQ (w16a16 / w8a16) and TFLite int16x8 are options for sensitive regression or anomaly-score heads.

### 1.4 Classical ML (often the best fit for CAN IDS)

- **emlearn**: `emlearn.convert(estimator, method='inline')` → `.save(file='model.h', name='model')` [U on exact API names; the README confirms conversion to C]. It supports RF, ExtraTrees and DecisionTree, plus Elliptic Envelope and GMM for unsupervised anomaly detection, which suits one-class training on normal traffic. That matters for SynCAN-style unsupervised setups.
- **Alternatives**:
  - `skl2onnx` 1.20.0 → ST Edge AI Core, which supports some sklearn models via ONNX [S].
  - NXP eIQ Time Series Studio, which generates classical models for NXP MCUs [S].
  - m2cgen / micromlgen: stale since 2022 [V].
- **Typical CAN IDS features**: per-ID inter-arrival time deviation, ID frequency in a sliding window, payload Hamming distance to the previous frame of the same ID, byte entropy, DLC anomalies, and an unknown-ID flag.
- **Typical cost**: tree ensembles with ≤ 50 trees and depth ≤ 10 usually fit in under 50 kB flash and run in tens of microseconds on an S3 [U, measure it].

---

## 2. Benchmarking

### 2.1 MLPerf Tiny methodology (adopt it as the pattern)

- **Suite**: KWS (DS-CNN), VWW (MobileNet), IC (ResNet on CIFAR-10), AD (deep autoencoder on ToyADMOS), plus a v1.3 streaming wake word (1D DS-CNN) [V repo / S v1.3]. v1.3 results were published 2025-09-17 [S].
- **Divisions**:
  - Closed: a fixed pre-trained model, with PTQ allowed.
  - Open: anything goes, but the accuracy is still reported.
  - All runs are single-stream. Accuracy is **measured on the device**, and closed-division results must stay within a threshold of the reference [V].
- **Performance mode**: the DUT talks directly to the host over UART. `th_timestamp` is an MCU counter at ≥ 1 kHz. It reports throughput (inferences/s) and accuracy [V].
- **Energy mode**:
  - The DUT is electrically isolated and powered by an energy monitor: ST **LPM01A**, **Joulescope JS110/JS220**, or **Keysight N6705** [V].
  - The timestamp is a GPIO falling edge with ≥ 1 µs hold time, and the result is joules per inference [V].
  - Only one supply may power the DUT. Cut or remove extra circuitry such as LEDs, regulators and USB bridges [V].
- **Tooling**:
  - EEMBC EnergyRunner 3.0.10 (click-through binary) [V].
  - Newer **open Python runner** in `mlcommons/tiny/benchmark/runner`, configured with `devices.yaml` and `tests.yaml`. It supports JS220 (via `joulescope` 1.6.0 on PyPI) and LPM01A [V].
- **Adapting it to this repo**:
  - Define a "Mobility-Security Tiny" harness with the same API style (`th_load_tensor`, `th_infer`, `th_results`, `th_timestamp`) so results are comparable.
  - Report the **median latency over N ≥ 10 runs** after warm-up, at a fixed CPU clock (240 MHz on S3), with the cache state stated.

### 2.2 Measuring on device (ESP32-S3)

| Metric | How | Verif. |
|---|---|---|
| Latency | `esp_timer_get_time()` around `invoke()`. For cycles, `esp_cpu_get_cycle_count()`. Run N=100, report median and p99. Pin to a core and disable Wi-Fi/BT. | [U] API names are standard ESP-IDF |
| Per-op profile | TFLM `MicroProfiler`. ESP-DL has built-in profiling (the "how to load test profile model" tutorial) [V tutorial exists]. | [V]/[U] |
| Tensor arena / RAM | TFLM `interpreter.arena_used_bytes()`. Host-side `tflite_micro.Interpreter.print_allocations()` [V]. System RAM: `heap_caps_get_minimum_free_size()` and `uxTaskGetStackHighWaterMark()`. State SRAM vs PSRAM placement explicitly; PSRAM is much slower. | [V]/[U] |
| Flash | `idf.py size`, `idf.py size-components`. Model blob size from the `.tflite` / `.espdl` / `.h`. | [U] |
| Energy | ESP32-S3 dev boards include a USB-UART bridge, LEDs and an LDO. Measure on a module or board with jumpers removed, using a Joulescope JS220, Nordic PPK2 (`ppk2-api` is stale, 2023 [V]) or ST LPM01A. Toggle a GPIO around inference and integrate the current. Subtract idle. Report µJ/inference and average power at the detection duty cycle (e.g. per CAN window). | [U] |
| STM32 | ST Edge AI Core `analyze` (static RAM/flash/MACC) and `validate` (on target) [S]. ST Edge AI Developer Cloud benchmarks on real ST boards [U]. | |
| NXP | eIQ / MCUXpresso profiling. TFLM profiler. | [U] |

### 2.3 Build systems & emulation for CI

- **Build system**:
  - Use **ESP-IDF** natively (v5.5 / v6.x) with the component manager (`idf_component.yml` depending on `espressif/esp-dl` or `espressif/esp-tflite-micro`) [V].
  - **PlatformIO** 6.2.0 [V] works, but the official platform-espressif32 has lagged on IDF versions [U]. Prefer native IDF for ESP-DL and S3 PIE.
- **pytest-embedded** 2.9.3 [V]: Espressif's pytest plugin. It drives targets (real board via serial, or QEMU) and parses output. It is the natural test harness for both HIL and emulation [U on the exact QEMU service flag names].
- **Espressif QEMU** (fork):
  - Targets **ESP32, ESP32-S3 and ESP32-C3**. On S3 it emulates dual core, UART, flash, PSRAM (QPI/OPI), GDMA, SHA/AES/RSA/HMAC, SysTimer and **TWAI/CAN** [V]. CAN is the key feature here: you can replay CAN traces into the firmware IDS in CI.
  - Not emulated: Wi-Fi, BT, USB, I2C, SPI, RMT. Not cycle-accurate, so do not use it for latency.
  - Whether S3 PIE SIMD instructions are emulated is **unverified**. Test ESP-DL / ESP-NN kernels in QEMU early and fall back to the C kernels if needed [U].
  - Espressif "does not provide support for QEMU" [V].
- **Renode**:
  - Platform files exist for `stm32f4`, `stm32h7`, `stm32h753`, `imxrt1064`, `nrf52840` and a generic Xtensa sample controller. There are **none for esp32/esp32s3** [V: raw GitHub probe of `platforms/cpus/*.repl`].
  - The TFLM team has used Renode CI since 2020 [S]. Robot Framework tests are available.
  - Use it for STM32 and NXP functional CI.
- **Wokwi**:
  - GitHub Action `wokwi/wokwi-ci-action@v1`. Needs a `WOKWI_CLI_TOKEN` secret, `wokwi.toml` and `diagram.json`.
  - Supports `expect_text`, `fail_text` and scenario YAML [V].
  - Supports ESP32-S3 [U on CAN/TWAI peripheral simulation, likely absent]. Paid tiers apply above the free CI minutes [U].
- **Host-side "golden" tests**:
  - Run the `.tflite` in the `tflite-micro` Python interpreter and in the LiteRT interpreter, and assert identical int8 outputs.
  - For ESP-DL, ESP-PPQ exports test vectors. Assert on-device (or QEMU) outputs match.

Recommended CI tiers:

1. Python unit tests and contract tests on every PR.
2. Firmware build matrix (S3 / STM32 / NXP) on every PR.
3. QEMU-S3 + Renode-STM32 functional tests replaying CAN traces, on every PR.
4. Self-hosted HIL runner with an S3 board, Joulescope and CAN interface (e.g. a second S3 or a USB-CAN adapter). Runs nightly and on release, and produces the benchmark JSON that feeds the model card.

---

## 3. Hugging Face publishing

### 3.1 Library, tags, file formats

- **`library_name: litert`** is the official HF library key for LiteRT. Its `countDownloads` is `path_extension:"tflite"` [V: `huggingface.js/packages/tasks/src/model-libraries.ts`].
  - There is **no `tflite` or `onnx` library key**. ONNX is treated as a file format and appears in many libraries' download filters [V].
  - Without a library, downloads are counted only on `config.json`, `config.yaml`, `hyperparams.yaml`, `params.json` or `meta.yaml` [V: `hub-docs/models-download-stats.md`].
  - So either set `library_name: litert`, or ship a small `config.json` (input shape, feature spec, quant params, label map). Doing both is best. The `config.json` doubles as firmware metadata.
- Other relevant keys: `keras` (counts `config.json` / `*.keras`), `tf-keras`, `sklearn` (counts `sklearn_model.joblib`) [V].
- **pipeline_tag**: `tabular-classification` or `time-series-forecasting` exist [V]. There is no anomaly-detection or IDS pipeline tag [V: `pipelines.ts`]. Use `tabular-classification` for frame/window classifiers and describe the task in tags.
- **Suggested tags**: `tinyml`, `tflite`, `litert`, `int8`, `onnx`, `esp-dl`, `esp32-s3`, `stm32`, `microcontroller`, `edge`, `can-bus`, `automotive`, `intrusion-detection`, `anomaly-detection`, `cybersecurity`.
- **Existing examples**:
  - **STMicroelectronics** publishes every STM32 Model Zoo model as an HF model card under `huggingface.co/STMicroelectronics`, plus a model-zoo dashboard Space [V: stm32ai-modelzoo README].
  - Others, not verified this session [U]: Qualcomm AI Hub (`huggingface.co/qualcomm`, per-model repos with TFLite/ONNX/QNN assets and per-device latency tables); Google `litert-community` (LiteRT models, mostly mobile LLMs); Arm and Edge Impulse community repos.
  - Mirror the Qualcomm and ST pattern: one repo per model, a per-device performance table in the card, and an assets folder per format.
- **Proposed repo file layout on HF**:

```text
README.md                # model card (YAML + sections below)
config.json              # feature spec, window size, label map, quant scale/zero-point, thresholds
model_fp32.onnx
model_int8.tflite        # TFLM-ready
model_int8.espdl         # ESP-DL
model_data.h / .cc       # C array (xxd) for TFLM
emlearn_model.h          # for tree models
benchmarks/esp32s3.json  # latency/arena/flash/energy from HIL runner
eval/results.json        # per-dataset, per-attack metrics
LICENSE
```

### 3.2 Model card metadata (from `huggingface_hub` 2.1.1 `ModelCardData`) [V]

`ModelCardData` fields: `base_model`, `datasets`, `eval_results` (model-index), `language`, `library_name`, `license`, `license_name`, `license_link`, `metrics`, `model_name`, `pipeline_tag`, `tags`. Extra kwargs (for example `extra_gated_*`) are passed through to the YAML.

Example YAML:

```yaml
---
library_name: litert
pipeline_tag: tabular-classification
license: other            # or apache-2.0 when data terms allow
license_name: syncan-noncommercial-derived
license_link: LICENSE
tags: [tinyml, tflite, int8, onnx, esp-dl, esp32-s3, stm32, can-bus, automotive, intrusion-detection, cybersecurity]
datasets: [<org>/can-ids-<name>]   # if you mirror a dataset (only if license allows)
metrics: [f1, recall, precision, roc_auc]
model-index:
- name: can-ids-rf-tiny
  results:
  - task: {type: tabular-classification, name: CAN intrusion detection}
    dataset: {name: SynCAN, type: <org>/syncan}
    metrics:
    - {type: f1, value: 0.97, name: F1 (int8, on-device)}
---
```

### 3.3 Gating & licensing

- **Gating** [V, `hub-docs/models-gated.md`]:
  - YAML keys: `extra_gated_prompt`, `extra_gated_heading`, `extra_gated_description`, `extra_gated_button_content`, and `extra_gated_fields` (types `text`, `checkbox`, `date_picker`, `country`, `select`). `extra_gated_eu_disallowed` blocks EU users by IP.
  - Approval is automatic or manual. Gated repos remain publicly visible; only the files are gated.
  - Programmatically: `HfApi().update_repo_settings(repo_id, gated="auto"|"manual"|False)` [V]. Datasets support the same gating [U on the separate doc; the mechanism is shared].
  - Use gating with a checkbox ("I will use this for defensive research / testing on vehicles I own or am authorized to test") for attack-generation tools, adversarial-example sets, or raw captures from real vehicles. Plain IDS classifiers usually do not need gating.
- **Licenses** [V `hub-docs/repositories-licenses.md`]: `apache-2.0`, `mit`, `cc-by-4.0`, `cc-by-nc-4.0`, `cc-by-nc-sa-4.0`, `openrail`, and `other` (with `license_name` + `license_link` + a LICENSE file).
- **Training on non-commercial datasets**:
  - **SynCAN** (ETAS/Bosch, Hanselmann et al., IEEE Access 2020): "freely available ... for **non-commercial** purposes ... but **not in the field**". Its own license terms file applies [V: README].
  - Other common CAN datasets: HCRL Car-Hacking / Survival / CAN-FD (research-only terms), ROAD (ORNL), can-train-and-test, CrySyS. Each has its own terms; re-check them all [U].
  - Whether model weights are "derivative works" of training data is legally unsettled [U]. Conservative policy:
    1. Do not redistribute raw data unless permitted. Publish loaders and download scripts instead.
    2. License weights trained on NC data as `cc-by-nc-4.0` or `other` with the dataset's restriction carried over ("research/non-commercial; not for in-field/vehicle deployment").
    3. Keep code under the repo's Apache-2.0 (the current repo LICENSE is Apache-2.0 [V]).
    4. Record the dataset license in the model card and in `config.json`.
  - For commercially usable models, train on self-recorded or synthetic traffic (e.g. a CAN simulator or bench ECUs) and license those as Apache-2.0.

### 3.4 Upload API (`huggingface_hub` 2.1.1, CLI `hf`) [V signatures]

```python
from huggingface_hub import HfApi, ModelCard, ModelCardData
api = HfApi()  # token from HF_TOKEN env / `hf auth login`
repo = "<org>/can-ids-rf-tiny"
api.create_repo(repo, repo_type="model", private=True, exist_ok=True)
card = ModelCard.from_template(ModelCardData(library_name="litert", license="other", tags=[...]),
                               template_path="tools/hf/modelcard_security_template.md", **sections)
card.save("dist/can-ids-rf-tiny/README.md")
api.upload_folder(repo_id=repo, folder_path="dist/can-ids-rf-tiny",
                  commit_message="v0.3.0: int8 tflite + espdl + benchmarks",
                  delete_patterns=["*.tflite", "*.espdl"])   # replace stale artifacts
api.create_tag(repo, tag="v0.3.0")
api.update_repo_settings(repo, private=False)   # publish after review
```

Notes:

- Deps include `hf-xet` (Xet storage backend) and `httpx`-based HTTP. `huggingface-cli` is gone; the entry point is `hf` [V].
- Use git tags or revisions to pin model versions that firmware builds reference.
- Publish from CI only on release tags, and use a fine-grained org token that has write access to that org only.

### 3.5 Model card sections for security models

Start from the HF template (`huggingface_hub/templates/modelcard_template.md` [V]): Model Details, Uses (Direct / Downstream / Out-of-Scope), Bias, Risks & Limitations, Recommendations, Training Details, Evaluation, Environmental Impact, Technical Specs. Extend it with:

- **Intended use**: defensive IDS research, on-bench evaluation, education. **Not** a certified safety or security mechanism. No ISO/SAE 21434 or UNECE R155 claim.
- **Out-of-scope**: in-vehicle deployment on public roads without OEM validation, active countermeasures that inject frames, use as an attack oracle.
- **Threat model**: the attacks covered (DoS, fuzzing, spoofing / masquerade, replay, suspension) and those not covered.
- **Operating envelope**: bus (CAN 2.0 / CAN FD), bit rate, vehicle or dataset domain, window size, expected false-positive rate per hour of driving. Translate FPR into alarms per hour; it is the operationally relevant number.
- **Deployment specs**: per target, give latency (median / p99), arena RAM, flash, energy/inference, clock, runtime version, and quantization scheme.
- **Quantization impact**: fp32 vs int8 per attack class.
- **Generalization limits**: cross-vehicle and cross-dataset results. Known leakage problems in public CAN datasets (e.g. trivially separable injected IDs in Car-Hacking) [U, well-documented in the literature].
- **Adversarial robustness**: the evaluated attack (section 5), threat-model knowledge level, and robust accuracy at each perturbation budget. State plainly if none was evaluated.
- **Dual-use statement**: the model and its decision thresholds could help attackers craft evasive traffic. Explain what was withheld, for example adversarial generators or exact thresholds for specific vehicles, and why.
- **Responsible disclosure contact**: a `SECURITY.md` link.
- **Data provenance and license inheritance.**

### 3.6 EU regulatory notes (brief; all [U]; not legal advice)

- **EU AI Act** (Reg. 2024/1689):
  - Timeline: in force 2024-08-01; prohibitions applied 2025-02-02; GPAI obligations 2025-08-02; most other obligations 2026-08-02. A "Digital Omnibus" proposal (Nov 2025) aimed to delay high-risk obligations; check whether it was adopted.
  - A small IDS classifier is not GPAI. It is likely high-risk only as a **safety component** of a product under Annex I harmonisation legislation. Vehicle type-approval (Reg. 2018/858, 2019/2144) is handled through sector acts rather than directly.
  - Publishing research models openly (free and open-source, not placed on the market) benefits from the open-source and research exemptions. Keep the "research only, not for in-vehicle deployment" framing.
- **Cyber Resilience Act** (Reg. 2024/2847):
  - Timeline: in force 2024-12-10; vulnerability and incident **reporting obligations from 2026-09-11** (now in effect); full application 2027-12-11.
  - Products covered by vehicle type-approval Reg. 2019/2144 are **excluded**. Vehicles fall under UNECE R155/R156 and ISO/SAE 21434 instead.
  - Free and open-source software made available outside a commercial activity is out of scope. Monetized or support-contracted OSS may bring obligations, and the "open-source software steward" regime applies to foundations.
  - If the org later sells firmware, an aftermarket dongle or an IDS product, CRA obligations apply: SBOM, vulnerability handling, 5-year support period, and so on. Keep a `SECURITY.md`, a CVD policy and SBOM generation in CI from the start.

---

## 4. Monorepo structure

```text
mobility-security-ml/
├── pyproject.toml              # uv workspace root (tool.uv.workspace members = ["packages/*", "models/*"])
├── uv.lock
├── .python-version             # 3.12 (TF 2.21 supports 3.10–3.13 [U]; tflite-micro dev wheel is cp313 [V])
├── packages/
│   ├── msml-data/              # dataset loaders (SynCAN, HCRL, ROAD, can-train-and-test), CAN log parsers (candump/ASC/BLF via python-can), windowing, splits by vehicle/capture (no leakage)
│   ├── msml-features/          # feature extractors — ALSO implemented in C (firmware/components/msml_features) with golden-vector parity tests
│   ├── msml-export/            # keras->tflite int8, onnx, esp-ppq->espdl, emlearn, xxd C arrays, tflite-micro validation
│   ├── msml-bench/             # host + HIL runner (serial protocol à la MLPerf Tiny th_* API), Joulescope integration, result JSON schema
│   ├── msml-adv/               # adversarial evaluation (constraints-aware attacks for CAN)
│   └── msml-hub/               # model card rendering (Jinja template), HF upload, license checks
├── models/
│   └── can-ids-rf-tiny/
│       ├── pyproject.toml      # model-specific deps (optional)
│       ├── conf/               # Hydra: config.yaml, data/, model/, export/, target/{esp32s3,stm32h7,mcxn947}.yaml
│       ├── train.py  export.py  evaluate.py  attack_eval.py
│       ├── dvc.yaml            # stages: prepare -> train -> export -> eval -> bench (params from conf/)
│       ├── firmware/           # ESP-IDF app (main/, idf_component.yml, sdkconfig.defaults.esp32s3), STM32/NXP app stubs
│       ├── card/               # model card fragments (intended use, limitations, threat model)
│       └── README.md
├── firmware/
│   ├── components/             # reusable ESP-IDF components: msml_runtime (TFLM/ESP-DL/emlearn abstraction), msml_can (TWAI capture + windowing), msml_features, msml_bench (th_* harness)
│   ├── boards/                 # board configs (S3 DevKitC-1, STM32 Nucleo-H7, FRDM-MCXN947)
│   └── ci/                     # qemu/, renode/ (*.robot, *.resc), wokwi/ (wokwi.toml, diagram.json, scenarios)
├── datasets/                   # DVC-tracked pointers + download scripts + dataset cards (NO raw NC data in git)
├── tools/hf/modelcard_security_template.md
├── docs/  SECURITY.md  CODEOWNERS
└── .github/workflows/          # python.yml, firmware-matrix.yml, emu-tests.yml, hil-bench.yml (self-hosted), release-hf.yml
```

Tooling choices:

- **uv** workspaces for Python; one lockfile.
  - TF and PyTorch in one env is heavy. Put them in separate workspace members or dependency groups (`--group tf`, `--group torch`), or give model packages their own envs.
  - ESP-PPQ pulls in torch [V: README installs torch].
- **Hydra** (`hydra-core` 1.3.7, Sept 2026 [V]): compose configs for data, model, export and target. `--multirun` handles sweeps.
- **DVC** 3.67.1 [V]: data and artifact versioning, plus `dvc.yaml` pipelines. Point the remote at S3-compatible or institutional storage. Use DVC params from the Hydra-resolved config.
- **Experiment tracking**: **MLflow** 3.17.0 [V], self-hosted, so no licensing or data-residency concerns for automotive data. Log device benchmark JSON as artifacts. **W&B** 0.30.0 [V] is fine if SaaS is acceptable. DVC experiments (`dvc exp`) are a lightweight alternative.
- **Firmware**: ESP-IDF component manager. Models are embedded via `target_add_binary_data` / EMBED_FILES, or as an `xxd` C array. A single `msml_runtime` C API (`init`, `infer`, `get_scores`) hides TFLM, ESP-DL and emlearn, so CAN capture code is backend-agnostic.
- **Results schema**: one `benchmarks/<target>.json` per model/target (runtime, versions, clock, latency stats, arena, flash, energy). The model card table is generated from it.

---

## 5. Adversarial robustness of ML CAN IDS

### 5.1 Pointers (titles and venues partly unverified; arXiv and NDSS could not be fetched)

- **Longari, Zanero et al.**, "On the Feasibility of Evasion Attacks against CAN-based Automotive Intrusion Detection Systems" (Politecnico di Milano). Studies white/grey/black-box evasion under time-dependency and online-attack constraints. PDF: https://re.public.polimi.it/retrieve/a9eb3ac8-98aa-438e-9872-f6a488226632/On_the_Feasibility_of_Evasion_Attacks_against_CAN_based_Automotive_Intrusion_Detection_Systems.pdf [S; venue U]
- **CANEDERLI** (CAN Evasion Detection ResiLIence): adversarial training and transferability for CAN IDS. arXiv:2404.04648 (Marchiori & Conti, 2024 [U authors]). https://arxiv.org/abs/2404.04648 [S]
- Gradient-based evasion algorithms evaluated against six CAN IDSs. arXiv:2506.10620 (2025) [S; exact title U]. https://arxiv.org/abs/2506.10620
- NDSS VehicleSec 2024 paper #56 on adversarial evaluation of CAN IDS [S; title U]: https://www.ndss-symposium.org/wp-content/uploads/vehiclesec2024-56-paper.pdf
- "Evaluating False Alarm and Missing Attacks in CAN IDS" [S]: https://www.themoonlight.io/review/evaluating-false-alarm-and-missing-attacks-in-can-ids
- Datasets and baselines: SynCAN / CANet (Hanselmann et al., IEEE Access 2020) [V]; ROAD (Verma et al., 2022/2024, realistic masquerade attacks) [U]; can-train-and-test (Lampe & Meng) [U]; HCRL Car-Hacking (Song, Woo, Kim 2020) [U].

### 5.2 How to evaluate (practical protocol)

1. **Threat model matrix**:
   - Knowledge: white-box (gradients), grey-box (features and architecture known, surrogate trained), black-box (query or transfer).
   - Capability: inject-only (compromised ECU or OBD dongle) vs suppress-and-replace (bus-off plus masquerade).
   - Goal: evade detection while still achieving the attack effect, e.g. a target signal value or a DoS rate.
2. **Domain constraints**: an evasive sample must be a **valid CAN sequence**. That means a valid ID set and DLC, payload bytes in [0, 255], timing ≥ physical frame time at the bit rate, the attack payload preserved (otherwise "evasion" is meaningless), and no modification of other ECUs' frames unless the attacker has that capability. Use problem-space attacks or constraint projection. Unconstrained feature-space FGSM/PGD alone **overstates** vulnerability.
3. **Attacks to run**:
   - Feature-space PGD/C&W with projection, as an upper bound.
   - Timing-shaping attacks: inject at the legitimate period with jitter matching, mimicry of a benign payload distribution.
   - For trees: decision-based or black-box attacks (HopSkipJump, boundary) and tree-specific exact attacks (Kantchelian MILP, as in ART).
   - Transfer from a surrogate model trained on a different capture.
   - **Quantization-aware evaluation**: attack the int8 model as deployed, since int8 rounding changes decision boundaries.
4. **Metrics**:
   - Detection rate on adversarial traffic vs perturbation budget (timing ms, bytes changed, frames injected).
   - Attack success = evasion AND attack goal achieved.
   - Query count for black-box attacks; FPR change under adversarial training.
   - Report as robustness curves, not single numbers.
5. **Defenses to compare**: adversarial training (CANEDERLI-style), ensembles mixing rule-based (period / ID allow-list) and ML detectors, feature squashing, and monotone or bounded-input constraints. Hybrid rules plus ML make evasion much harder on MCUs at negligible cost.
6. **Tooling**: IBM **Adversarial Robustness Toolbox (ART)** covers trees (decision tree / RF attacks), sklearn and Keras/PyTorch [U on current version]. Extend it with a custom `CANConstraintProjector` in `packages/msml-adv`. Use `python-can` for trace replay. Re-validate evasive traces end-to-end by replaying them in **QEMU-S3 TWAI** or on a HIL bus against the firmware IDS. This closes the gap between the Python and on-device detectors.
7. **Publishing**: put the robustness results in the model card. Consider gating released adversarial trace sets (section 3.3).

---

## 6. Key links

| Topic | Link | Verif. |
|---|---|---|
| litert-torch (PyTorch→LiteRT) | https://github.com/google-ai-edge/litert-torch · https://pypi.org/project/litert-torch/ | [V] |
| LiteRT repo | https://github.com/google-ai-edge/LiteRT | [V] (referenced by TF RELEASE.md and HF) |
| TFLite→LiteRT rename blog | https://developers.googleblog.com/en/tensorflow-lite-is-now-litert/ | [S] |
| TFLM | https://github.com/tensorflow/tflite-micro | [V] |
| esp-tflite-micro | https://github.com/espressif/esp-tflite-micro | [V] |
| ESP-DL | https://github.com/espressif/esp-dl · operator list: https://github.com/espressif/esp-dl/blob/master/operator_support_state.md | [V] |
| ESP-PPQ | https://pypi.org/project/esp-ppq/ | [V] |
| ESP-IDF releases | https://github.com/espressif/esp-idf/releases | [V] |
| Espressif QEMU | https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/README.md | [V] |
| ExecuTorch Cortex-M | https://github.com/pytorch/executorch/tree/main/backends/cortex_m | [V] |
| emlearn | https://github.com/emlearn/emlearn | [V] |
| ST Edge AI Core | https://www.st.com/en/development-tools/stedgeai-core.html | [S] |
| STM32 model zoo (+HF org) | https://github.com/STMicroelectronics/stm32ai-modelzoo · https://huggingface.co/STMicroelectronics | [V] |
| NXP eIQ TFLM | https://www.nxp.com/design/design-center/software/eiq-ai-development-environment/eiq-inference-with-tensorflow-lite-micro:EIQ-TFLITE-MICRO | [S] |
| MLPerf Tiny | https://github.com/mlcommons/tiny · runner: https://github.com/mlcommons/tiny/tree/master/benchmark/runner | [V] |
| MLPerf Tiny v1.3 results | https://www.globenewswire.com/news-release/2025/09/17/3151817/0/en/MLCommons-New-MLPerf-Tiny-v1-3-Benchmark-Results-Released.html | [S] |
| EnergyRunner | https://github.com/eembc/energyrunner | [V] |
| Renode | https://github.com/renode/renode | [V] |
| Wokwi CI action | https://github.com/wokwi/wokwi-ci-action | [V] |
| HF library registry | https://github.com/huggingface/huggingface.js/blob/main/packages/tasks/src/model-libraries.ts | [V] |
| HF gated models | https://huggingface.co/docs/hub/models-gated (source: hub-docs/docs/hub/models-gated.md) | [V] |
| HF licenses | https://huggingface.co/docs/hub/repositories-licenses | [V] |
| HF download stats | https://huggingface.co/docs/hub/models-download-stats | [V] |
| HF model card template | https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/templates/modelcard_template.md | [V] |
| SynCAN (license terms) | https://github.com/etas/SynCAN | [V] |
| Edge Impulse / Qualcomm | https://siliconangle.com/2025/03/10/qualcomm-acquires-edge-impulse-to-enhance-ai-capabilities/ | [S] |

## 7. Open items to verify next

- litert-torch **static** full-int8 PT2E output with int8 I/O running in TFLM, for a small 1D-CNN or GRU.
- Whether Espressif QEMU emulates ESP32-S3 PIE instructions, which decides whether ESP-DL / ESP-NN kernels can run in CI.
- The API of the converter inside `ai-edge-litert` 2.x, and TF's timeline for removing `tf.lite`.
- ST Edge AI Core 4.0 release date and its sklearn/ONNX-ML support list. Whether eIQ Neutron accepts ONNX.
- Current license terms of the HCRL, ROAD and can-train-and-test datasets.
- EU AI Act Digital Omnibus adoption status. CRA implementing acts.
- HF examples of tinyml-tagged repos: `huggingface.co/models?other=tinyml`, plus the Qualcomm and litert-community card formats. huggingface.co was blocked during this research.
