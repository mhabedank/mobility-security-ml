# 05 – Toolchain und Publishing

Details mit Versionsständen, Code-Beispielen und Prüfstatus stehen in [notes/toolchain-and-publishing.md](notes/toolchain-and-publishing.md).

## Stand des Ökosystems (Oktober 2026)

| Komponente | Stand | Bedeutung für uns |
|---|---|---|
| TensorFlow | 2.21; `tf.lite` soll aus dem TF-Paket ausgegliedert werden | TF für den Export pinnen; den Konverter in `ai-edge-litert` beobachten |
| **LiteRT for Microcontrollers** (ex TFLM) | aktiv; `tflite-micro`-Python-Interpreter für Host-Tests | Referenz-Runtime auf allen MCUs |
| **esp-tflite-micro + ESP-NN** | aktiv, IDF 5.1–6.0 | portable int8-Inferenz auf dem ESP32-S3 |
| **ESP-DL v3.3** + **ESP-PPQ 1.3** | aktiv; nimmt nur ONNX an; int8/int16/w8a16 | schnellste Inferenz auf S3 und P4 (SIMD) |
| ST Edge AI Core 4.0 | unterstützt STM32N6 und Stellar P3E | STM32-Pfad, inkl. `analyze`/`validate` |
| NXP eIQ (Toolkit, Neutron, Auto) | aktiv | S32K3 und MCX N |
| ExecuTorch 1.5 | Cortex-M-Backend in Beta, Ethos-U; **kein ESP32** | optional für später |
| `litert-torch` (ex `ai-edge-torch`) | 0.9 | PyTorch → `.tflite`, zweiter Pfad |
| **emlearn** 0.23 | MIT, gepflegt | **Bäume und Ensembles → C**; ideal für CAN-IDS |
| micromlgen / m2cgen | seit 2022 ohne Release | nicht verwenden |
| **microTVM** | aus TVM entfernt (zuletzt v0.18) | **nicht verwenden** |
| Edge Impulse | von Qualcomm übernommen (2025 angekündigt) | höchstens für schnelle Baselines; kein Kernpfad wegen SaaS-Lock-in |

## Empfohlene Pipeline

```text
Daten (DVC) → Features (gemeinsame Lib, zusätzlich als C-Implementierung) → Training
   ├─ klassisch: sklearn RF/ExtraTrees  → emlearn → model.h
   ├─ NN: Keras 3 (TF-Backend) → int8 .tflite   → TFLM auf ESP32 / STM32 / NXP
   └─ NN: Keras 3 → ONNX → ESP-PPQ → .espdl     → ESP-DL auf ESP32-S3
        ↓
CI-Vertragstests: tflite-micro-Interpreter == LiteRT (bit-exakt), int8- vs. fp32-Metriken,
                  Arena-Größe ≤ Budget, C-Features == Python-Features (Golden Vectors)
        ↓
Firmware (ESP-IDF-Komponente) → QEMU-Smoke-Test → Hardware-in-the-Loop-Benchmark
        ↓
Hugging-Face-Upload mit Model Card und Benchmark-JSON
```

- **Klassisches ML zuerst.** Für CAN-IDS auf Basis von Timing- und ID-Features reichen Bäume oft aus. Sie brauchen
  nur wenige kB und laufen im Bereich von Mikrosekunden. Ein neuronales Netz muss sich gegen diese Baseline beweisen.
- **Quantisierung:** standardmäßig int8 PTQ, mit einem Kalibrierset, das die **seltenen Angriffsklassen enthält**. QAT nur,
  wenn PTQ mehr als ~1 Prozentpunkt F1 kostet. `tfmot` braucht Keras 2, deshalb QAT über PyTorch/PT2E oder ESP-PPQ.
- **Feature-Skalierung ins Modell einbauen.** Dann kann die Firmware int8-Features direkt aus dem CAN-Parser übergeben.

## Benchmarking

Methodik nach **MLPerf Tiny**:

- Median-Latenz über N ≥ 10 Läufe nach Warm-up, mit fester Taktfrequenz.
- Energie mit galvanisch getrenntem DUT, gemessen mit Joulescope, LPM01A oder Nordic PPK2.
- Genauigkeit **auf dem Gerät** messen.
- Ein eigener „Mobility-Security-Tiny“-Harness mit `th_*`-API, damit Ergebnisse vergleichbar sind.

**Messgrößen auf dem ESP32-S3:**

- Latenz mit `esp_timer_get_time()`, Median und p99, inklusive Feature-Extraktion.
- RAM: Tensor-Arena plus Heap; immer angeben, ob SRAM oder PSRAM genutzt wird.
- Flash mit `idf.py size`.
- CPU-Anteil bei voller Buslast.

**CI ohne Hardware:**

- **Espressif QEMU** emuliert den ESP32-S3 **inklusive TWAI/CAN**. Damit lassen sich CAN-Traces in die Firmware einspielen.
  Ob die SIMD-Befehle emuliert werden, ist noch offen.
- **Renode** für STM32F4/H7 und i.MX RT.
- **Wokwi** als GitHub Action, mit Token.
- Emulatoren nur für funktionale Tests verwenden, nie für Latenzmessungen.

## Hugging Face

- **Ein Repository pro Modell** unter der Organisation, nach dem Vorbild des STM32 Model Zoo und von Qualcomm AI Hub.
- `library_name: litert`. Das ist der offizielle Schlüssel für `.tflite`; es gibt keinen `tflite`-Key. Zusätzlich ein
  `config.json` mit Feature-Spezifikation, Fenstergröße, Label-Map, Quantisierungsparametern und Schwellwerten. Es dient zugleich als
  Firmware-Metadatum.
- `pipeline_tag: tabular-classification`. Ein Anomaly-Detection-Tag existiert nicht.
- Tags: `tinyml`, `tflite`, `int8`, `esp32-s3`, `stm32`, `can-bus`, `automotive`, `intrusion-detection`, `cybersecurity`.
- **Dateien pro Repo:** `README.md` (Model Card), `config.json`, `model_fp32.onnx`, `model_int8.tflite`,
  `model_int8.espdl`, `model_data.h`, `benchmarks/<target>.json`, `eval/results.json`, `LICENSE`.
- **Upload** mit `huggingface_hub` (CLI `hf`): `create_repo`, `upload_folder`, `create_tag`. Nur aus der CI bei
  Release-Tags, mit einem fein granularen Org-Token.
- **Gating** (`extra_gated_fields`) nur für sensible Artefakte wie Angriffsgeneratoren, adversariale Trace-Sets oder
  Rohmitschnitte echter Fahrzeuge. Reine IDS-Klassifikatoren brauchen in der Regel kein Gating.

### Zusätzliche Abschnitte in der Model Card für Security-Modelle

- **Intended Use:** defensive Forschung, Labortests, Lehre. **Kein** zertifizierter Sicherheitsmechanismus und kein
  Anspruch auf ISO/SAE 21434 oder R155.
- **Out of Scope:** Einsatz im Fahrzeug auf öffentlichen Straßen ohne Validierung durch den OEM; aktive Gegenmaßnahmen; Nutzung als Angriffsorakel.
- **Threat Model:** welche Angriffe abgedeckt sind und welche nicht.
- **Operating Envelope:** Bus, Bitrate, Fahrzeug- bzw. Datensatzdomäne, **Fehlalarme pro Fahrstunde**.
- **Deployment Specs** pro Zielplattform: Latenz, RAM, Flash, Energie, Runtime-Version.
- **Quantisierungseinfluss:** fp32 vs. int8 pro Angriffsklasse.
- **Generalisierungsgrenzen:** Ergebnisse über Fahrzeuge und Datensätze hinweg.
- **Adversariale Robustheit:** oder ausdrücklich „nicht evaluiert“.
- **Dual-Use-Erklärung:** was zurückgehalten wurde und warum.
- **Datenherkunft und Lizenzvererbung.**
- Link auf `SECURITY.md` für Responsible Disclosure.

## Adversariale Robustheit

Ein ML-IDS wird von adaptiven Angreifern gezielt umgangen. Literatur: Longari/Zanero (Evasion gegen CAN-IDS),
CANEDERLI (arXiv 2404.04648), arXiv 2506.10620 und DUET für Spannungs-IDS.

**Protokoll:**

- Evasive Beispiele müssen **gültiger CAN-Verkehr** sein:
  - gültige IDs und DLC, Bytes in 0–255
  - Timing ≥ physische Framezeit
  - die Angriffswirkung bleibt erhalten
- Reine Feature-Space-Angriffe ohne Constraints (FGSM/PGD) überschätzen die Verwundbarkeit.
- **Das int8-Modell angreifen, wie es deployed wird.**
- Angriffe auf Bäume: Decision-basiert, HopSkipJump, MILP (über ART).
- Robustheitskurven über das Perturbationsbudget berichten.
- Verteidigung: **Hybrid aus Regeln und ML.** Perioden-Checks und ID-Allowlists kosten auf der MCU fast nichts und erschweren Evasion stark.

## Repo-Struktur (Vorschlag für Phase 1)

```text
mobility-security-ml/
├── pyproject.toml            # uv-Workspace
├── packages/
│   ├── msml-data/            # Dataset-Loader, Log-Parser (candump/ASC/BLF), leckfreie Splits
│   ├── msml-features/        # Feature-Extraktion (Python; Parität mit der C-Version)
│   ├── msml-export/          # tflite int8, onnx, espdl, emlearn, C-Arrays, Validierung
│   ├── msml-bench/           # HIL-Runner (th_*-API), Energiemessung, Result-Schema
│   ├── msml-adv/             # adversariale Evaluation mit CAN-Constraints
│   └── msml-hub/             # Model-Card-Rendering, HF-Upload, Lizenzprüfung
├── models/<modell-name>/     # conf/ (Hydra), train/export/evaluate, dvc.yaml, firmware/, card/
├── firmware/components/      # ESP-IDF: msml_runtime, msml_can, msml_features, msml_bench
├── datasets/                 # Download-Skripte, Dataset Cards, Lizenz-Snapshots (keine NC-Rohdaten in git)
├── docs/  SECURITY.md
└── .github/workflows/
```

Werkzeuge: **uv** (TF und PyTorch als getrennte Dependency-Groups), **Hydra**, **DVC**, **MLflow** (self-hosted),
ESP-IDF-Komponentenmanager, **pytest-embedded**.

## Regulatorische Notizen

Diese Notizen sind **nicht geprüft und keine Rechtsberatung**.

- **EU AI Act:** Ein kleiner IDS-Klassifikator ist kein General-Purpose-AI-Modell. Hochrisiko wäre er nur als Sicherheitskomponente eines
  regulierten Produkts. Offene Forschungsmodelle profitieren von Ausnahmen für Forschung und Open Source. Das Framing
  „nur Forschung, nicht für den Einsatz im Fahrzeug“ beibehalten.
- **Cyber Resilience Act:** Fahrzeuge mit Typgenehmigung sind ausgenommen, für sie gelten R155/R156. Freie Open-Source-Software
  außerhalb kommerzieller Tätigkeit fällt nicht darunter. Würden wir später Firmware oder Dongles verkaufen, greifen Pflichten wie SBOM
  und Schwachstellenmanagement. Deshalb von Anfang an `SECURITY.md` anlegen und SBOMs in der CI erzeugen.
