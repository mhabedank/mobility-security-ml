# Roadmap

Grundlage: [Recherche](research/README.md). Stand: 2026-10-07.

## Ziel und Leitplanken (Entscheidung vom 2026-10-07)

- **Ziel:** Sichtbare Reputation in den Bereichen Mobility, ML/KI und Automotive Security. Mehrere solide, gut
  dokumentierte Modelle schnell auf Hugging Face bringen statt monatelang an einem einzigen zu feilen.
- **Lizenz:** Modelle sollen **kommerziell nutzbar** sein. Wir trainieren deshalb nur auf Daten unter CC BY oder MIT
  (oder vergleichbar). NC-Datensätze (HCRL, SynCAN, TU/e) kommen höchstens als Vergleichs-Benchmark vor.
- **Framework:** Pro Modell wählen wir, was am besten passt (sklearn/emlearn, Keras oder PyTorch). Es gibt keine feste Vorgabe.
- **Hardware:** Vorerst nur der vorhandene **ESP32** und kaum Budget. Benchmarks auf dem Gerät laufen über
  **Testvektoren per UART**, dafür braucht es keinen CAN-Bus. Ein CAN-Transceiver (SN65HVD230, ~3 €) ist optional für eine Live-Demo.
- **Keine eigenen Fahrzeugdaten** in dieser Phase. Später sind Datenmarktplätze oder Kooperationspartner denkbar.
- **Hugging-Face-Organisation** existiert bereits.

### Fast-Track-Plan

| # | Modell | Daten (Lizenz) | Status |
|---|---|---|---|
| 1 | `can-ids-tiny`: CAN-Angriffserkennung pro Frame mit Features für unbekannte Fahrzeuge, Random Forest → C (emlearn) | can-train-and-test (CC BY 4.0; über Bitbucket erreichbar) | in Arbeit |
| 2 | `v2x-misbehavior-tiny` | VeReMi Extension (CC BY 4.0) | Datenzugang klären |
| 3 | `gnss-spoofing-tiny` | Aissou GPS Spoofing (CC BY 4.0) | Datenzugang klären |

**Was die Modelle hervorheben soll:** ehrliche Evaluation (unbekannte Fahrzeuge, unbekannte Angriffe, Fehlalarme pro Stunde),
Messwerte vom echten ESP32 und Model Cards mit klarer Abgrenzung des Einsatzzwecks.

## Bewertung der Low-Hanging Fruits

Jedes Problemfeld wird nach vier Kriterien bewertet:

- **Daten:** Gibt es öffentliche, offen lizenzierte Daten?
- **MCU:** Läuft das Modell auf ESP32-S3-Klasse?
- **Hardware:** Wie viel Zusatzhardware brauchen wir?
- **Neuheit/Wert:** Ist das auf Hugging Face neu oder wissenschaftlich interessant?

| Rang | Kandidat | Daten | MCU | Hardware | Neuheit/Wert | Gesamt |
|---|---|---|---|---|---|---|
| **1** | **CAN-IDS auf ID-/Timing-Ebene** | ✅ CC BY (can-train-and-test, CAN-MIRGU) | ✅ | gering (ESP32-S3 + Transceiver) | mittel: Thema bekannt, aber **ehrliche Evaluation und MCU-Messungen** fehlen fast überall | ⭐⭐⭐⭐⭐ |
| **2** | **GNSS-Jamming-/Spoofing-Detektor** (u-blox-Messwerte: C/N0, AGC, Uhrdrift, Positionssprünge) | ✅ CC BY (Aissou), Jammertest 2025 (Lizenz offen) | ✅ 1–10 Hz | gering (u-blox-Modul) | hoch: auf Hugging Face nichts vorhanden; auch für Micromobility und Telematik relevant | ⭐⭐⭐⭐ |
| **3** | **V2X-Misbehavior-Detektor** | ✅ CC BY (VeReMi-Familie) | ✅ | keine | mittel: realistisch eher auf einem V2X-SoC | ⭐⭐⭐⭐ |
| **4** | **Masquerade-Erkennung auf Signalebene** (kleiner Autoencoder pro ID-Gruppe) | ◐ ROAD (Lizenz bestätigen), SynCAN (nur NC) | ✅ | gering | hoch: schließt die Lücke reiner Timing-IDS | ⭐⭐⭐⭐ |
| 5 | Clock-Skew-Senderidentifikation | ◐ eigene Daten (ECUPrint ohne Lizenz) | ✅ | MCP2518FD für Hardware-Zeitstempel | hoch | ⭐⭐⭐ |
| 6 | Fahrerprofil / Diebstahlschutz | ◐ nur NC (HCRL Driving), KCID offen | ✅ | keine | mittel | ⭐⭐⭐ |
| 7 | EVSE-Anomalie (Leistungskurven) | ◐ CICEVSE2024 (Lizenz-Konflikt) | ✅ | keine | mittel; ESP32-Vorarbeit existiert | ⭐⭐⭐ |
| 8 | Keyless/UWB-Relay, E-Scooter-BLE, TPMS, LIN | ❌ eigene Datenerhebung | ✅ | mittel (UWB, SDR, Scooter) | **sehr hoch: noch keine Datensätze vorhanden** | ⭐⭐ (später, dann als eigene Datensatz-Veröffentlichung) |

## Phasen

### Phase 0 – Recherche ✅

- Bedrohungslandschaft, Literatur, Datensätze, Hardware, Toolchain (dieses PR)

### Phase 1 – Fundament

- [ ] Entscheidungen treffen (siehe [Offene Entscheidungen](#offene-entscheidungen))
- [ ] Repo-Grundgerüst: uv-Workspace, `packages/msml-data`, `msml-features`, `msml-export`, CI (Lint und Tests)
- [ ] **Lizenzen der Startdatensätze von Hand prüfen** und Snapshots unter `datasets/<name>/` ablegen
  (can-train-and-test, CAN-MIRGU, ROAD, VeReMi, Aissou)
- [ ] Dataset-Loader mit **leckfreien Splits** (zeitlich, pro Aufnahme, pro Fahrzeug)
- [ ] Gemeinsames **Evaluationsprotokoll** als Code: AUC-PR, F1, Recall bei fester FPR, FP pro Stunde, Erkennungslatenz
- [ ] Model-Card-Vorlage für Security-Modelle (`tools/hf/`)
- [ ] `SECURITY.md`
- [ ] Hardware bestellen (siehe [Einkaufsliste](research/04-hardware.md#einkaufsliste-für-den-start-vorschlag))

### Phase 2 – Modell 1: `can-ids-timing-tiny`

**Ziel:** fensterbasierter CAN-IDS auf einem ESP32-S3 am klassischen CAN-Bus.

- **Features** pro Fenster aus N Frames bzw. T ms:
  - IAT-Abweichung pro ID
  - ID-Häufigkeiten
  - unbekannte IDs
  - Payload-Hamming-Distanz zum Vorgänger derselben ID
  - Byte-Entropie
  - DLC-Anomalien
- **Modelle:**
  - Baseline: Regeln (Perioden-Check, ID-Allowlist)
  - Random Forest / Extra Trees mit emlearn
  - kleines int8-MLP oder 1D-CNN mit TFLM und ESP-DL
- **Daten:**
  - Training und Test auf can-train-and-test, inkl. Splits mit unbekannten Fahrzeugen
  - Kreuztest auf CAN-MIRGU und ROAD
  - Car-Hacking nur als Plausibilitätscheck
- **Firmware:**
  - ESP-IDF-Komponente: TWAI-Capture, Ringpuffer, Features in C mit Paritätstest gegen Python
  - Inferenz mit festem Takt
  - Ausgabe als Security Event im IdsM-Stil
- **Messung:**
  - Latenz inkl. Features
  - RAM/Flash
  - CPU-Last bei 100 % Buslast (Replay über CANable)
  - Energie
- **Veröffentlichung:** erstes Modell auf Hugging Face mit vollständiger Model Card und Benchmark-JSON, dazu
  Parquet-Mirrors der CC-BY-Datensätze, sofern die Lizenz das erlaubt.

### Phase 3 – Modelle 2–4 (parallelisierbar)

- **`gnss-interference-tiny`:**
  - Jamming- und Spoofing-Erkennung aus UBX/NMEA-Messwerten auf ESP32-S3 mit u-blox-Modul
  - Daten: Aissou, Yunnan University, Jammertest 2025
  - optional eigene Aufnahmen, gelabelt über den `jammertest-plan`
- **`v2x-misbehavior-tiny`:** Plausibilitäts- und Fehlverhaltensklassifikator pro Nachricht auf VeReMi Extension und NextGen.
- **`can-masquerade-ae-tiny`:** Autoencoder auf Signalebene pro ID-Gruppe auf ROAD-Signalen.
  Eine Variante auf SynCAN-Basis erscheint nur unter einer NC-Lizenz.
- Adversariale Evaluation (`msml-adv`) für Modell 1 nachziehen.

### Phase 4 – Produktionsnahe Ziele und eigene Datensätze

- Port auf **S32K344** (eIQ/TFLM, CMSIS-NN) und **STM32N6** (NPU). Vergleich in einer
  Benchmark-Tabelle über alle Zielplattformen.
- CAN FD (MCP2518FD bzw. ESP32-C5/S31), Clock-Skew-Fingerprinting mit Hardware-Zeitstempeln.
- **Eigene Datensätze** in den Lücken: UWB/Keyless-Relay, E-Scooter-BLE/UART, LIN, TPMS. Veröffentlichung
  unter CC BY 4.0 auf Hugging Face, möglichst mit begleitendem Paper.

## Offene Entscheidungen

1. **Name der Hugging-Face-Organisation** und wer Schreibrechte bekommt.
2. **Lizenz-Policy für Modelle:** Nur offen (CC BY und eigene Daten), oder zusätzlich NC-Modelle auf Basis von HCRL und SynCAN?
3. **Framework:** Ist Keras 3 als Haupt-NN-Pfad gesetzt, oder bevorzugt das Team PyTorch? Mit PyTorch gibt es mehr
   Konvertierungsaufwand Richtung `.tflite`, der Weg über ONNX zu ESP-DL bleibt gleich.
4. **Budget für Hardware:** nur die Starter-Kit-Liste, oder gleich NUCLEO-N6, S32K344-EVB und ein Energiemessgerät?
5. **Zugang zu Fahrzeugen**, um passiv Normaldaten mitzuschneiden. Das ist wichtig für die Generalisierung über Fahrzeuge hinweg.
6. **Veröffentlichungsstrategie:** Nur Hugging Face, oder auch Papers (z. B. VehicleSec, escar, AutoSec)?

## Offene Prüfaufgaben aus der Recherche

- Lizenzen: ROAD (CC BY vs. NC-SA), CICIoV2024/CICEVSE2024, AutoHack, Jammertest 2025, X-CANIDS.
- Literatur: alle Einträge mit `[unverified]` in [notes/threats-and-papers.md](research/notes/threats-and-papers.md),
  vor allem VeReMi, SAVIOR, Plug-N-Pwned, Brokenwire, CANet sowie die Autoren der STM32-Kapitel.
- Exakte MCU-Zahlen aus den Volltexten (TPI-/PIB-IDS, INDRA, Crocioni et al.).
- Toolchain: Kommt der statische int8-Pfad über `litert-torch` in TFLM an? Emuliert QEMU die S3-SIMD-Befehle?
- Standards: Aussagen zu R155/R156, ISO/SAE 21434 und AUTOSAR IdsM gegen die Originaltexte prüfen.
