# 03 – Datensätze

Details zu rund 40 Datensätzen mit Größen, Formaten, Kritik und Prüfstatus stehen in [notes/datasets.md](notes/datasets.md).

> ⚠️ Viele Lizenzseiten (HCRL, UNB/CIC, Zenodo, IEEE DataPort) waren während der Recherche nicht direkt
> erreichbar. Lizenzangaben mit `[CONFLICT]` oder `[UNVERIFIED]` müssen vor jeder Nutzung für veröffentlichte
> Modelle von Hand geprüft werden. Den Lizenztext dann archivieren, z. B. unter `datasets/<name>/LICENSE-snapshot.txt`.

## Lizenzen: Was dürfen wir veröffentlichen?

| Lizenztyp | Daten neu hosten? | Modelle offen veröffentlichen? |
|---|---|---|
| **CC BY 4.0 / MIT** | ja, mit Namensnennung | ja |
| **CC BY-NC(-SA)** | nein bzw. nur nicht-kommerziell | rechtlich ungeklärt; übliche Praxis: Gewichte unter einer NC-Lizenz, Trainingsdaten angeben |
| **CC BY-NC-ND** | nein, auch keine bereinigten Mirrors | wie oben |
| **Eigene akademische Bedingungen** (HCRL, SynCAN) | nein | wie NC; SynCAN verbietet zusätzlich jeden Einsatz im Feld |
| **Keine Lizenz** (TEXBAT, ECUPrint) | nein (alle Rechte vorbehalten) | nur für Forschung und Benchmarks |

**Vorgeschlagene Policy:**

1. Modelle, die wir **offen und kommerziell nutzbar** veröffentlichen, trainieren wir nur auf CC-BY- oder MIT-Daten
   oder auf **selbst aufgenommenen** Daten.
2. NC-Datensätze nutzen wir nur zum **Vergleich (Benchmark)**. Wird darauf trainiert, erscheinen die Gewichte
   unter `cc-by-nc-4.0` bzw. `other`, mit übernommener Einschränkung.
3. Rohdaten hosten wir nur neu, wenn die Lizenz es erlaubt. Sonst veröffentlichen wir Loader und Download-Skripte.

## Empfohlene Startdatensätze

| Datensatz | Domäne | Lizenz | Warum |
|---|---|---|---|
| **can-train-and-test** (Lampe & Meng, DTU) | CAN, 4 Fahrzeuge, 7,5 GB | **CC BY 4.0** [V-S] | Gezielt gegen die HCRL-Schwächen gebaut; Test-Splits auf unbekannten Fahrzeugen; Features auf Frame-Ebene |
| **CAN-MIRGU** (VehicleSec 2024) | CAN, echte Fahrt mit ADAS | **CC BY 4.0** (UCI) [V-S] | 17 h Normalfahrt, 26 physisch verifizierte Angriffe, dazu Masquerade/Suspension; candump-Format |
| **ROAD** (ORNL, PLOS ONE 2024) | CAN roh + dekodierte Signale | wahrscheinlich CC BY 4.0 (Zenodo) [CONFLICT] | Realistischste getarnte Angriffe; Signalversion für Masquerade-Modelle |
| **VeReMi / Extension / NextGen** | V2X (simuliert) | **CC BY 4.0** [V-GH] | 5 / 19 / 15 Fehlverhaltenstypen; kleine Features pro Nachricht |
| **GPS Spoofing Detection on UAS** (Aissou, Mendeley) | GNSS-Tracking-Features | **CC BY 4.0** [V-S] | 13 Features × 8 Kanäle; direkt MCU-tauglich |
| **SimulaMet Jammertest 2025** (IEEE DataPort) | GNSS-NMEA von u-blox/Quectel | [UNVERIFIED] | Low-Rate-Daten von Seriengeräten, über 2000 km Fahrt; passt genau zum MCU-Szenario |
| **comma2k19** | CAN + IMU + GNSS (ohne Angriffe) | **MIT** | Normaldaten für Plausibilitätsmodelle; liegt schon auf Hugging Face |
| **AutoHack** (VehicleSec 2026, Best Artifact) | 3 synchrone CAN-Busse, Hyundai 2023 | „free for everyone“, genaue Lizenz [UNVERIFIED] | Neuester und realistischster Datensatz; im Blick behalten |

## Nur als Benchmark (nicht-kommerziell oder unklar)

| Datensatz | Lizenz | Hinweis |
|---|---|---|
| HCRL Car-Hacking, OTIDS, Survival, CAN-FD, Driving Dataset | akademisch/NC [CONFLICT] | Car-Hacking ist **trivial lösbar** und hat Artefakte; nur als Plausibilitätscheck |
| SynCAN (ETAS) | NC, **nicht im Feld** | Sehr gut für Signal-Autoencoder; nicht für Produkte |
| TU Eindhoven CAN v2 | CC BY-NC 4.0 | – |
| CICIoV2024, CICEVSE2024 (UNB CIC) | [CONFLICT]: CIC-Standard vs. CC BY-NC-ND | CICIoV gilt als trivial trennbar |
| X-CANIDS (IEEE DataPort) | vermutlich CC BY [UNVERIFIED] | 688 Signale; Teilmengen für MCU auswählen |
| GEM-CAN (autonomer Shuttle) | CC BY-NC [V-S] | Explizit für On-Device-IDS |
| TOW-IDS (Automotive Ethernet) | nur für Abonnenten | nicht neu hostbar |
| TEXBAT / OAKBAT (GNSS-IQ) | keine Lizenz / Registrierung | Nur IQ-Rohdaten; brauchen einen Software-Empfänger für Low-Rate-Features |
| ECUPrint (CAN-Spannung, 500 MS/s) | keine Lizenz | Der Clock-Skew-Teil ist für TinyML nutzbar |

**Nicht verwenden:** `Thi-Thu-Huong/Multi-CAN-Datasets` auf Hugging Face. Dieser Datensatz bündelt offenbar HCRL- und SynCAN-Daten entgegen deren Bedingungen.

## Hilfsmittel zur Signaldekodierung

- **opendbc** (comma.ai, MIT): über 70 DBC-Dateien für viele Hersteller
- **cantools** (Python, DBC/ARXML), **canmatrix**, **cabana**
- **CAN-D** (ORNL; damit wurden die ROAD-Signale erzeugt), **READ**, **LibreCAN** (Reverse Engineering ohne DBC)

## Lücken: hier fehlen öffentliche Daten

| Domäne | Status | Idee für eigene Erhebung |
|---|---|---|
| Keyless/UWB-Relay | keine Daten | ESP32 + DW3000-UWB: CIR, First-Path, ToF und RSSI unter Relay-Angriffen aufnehmen |
| E-Scooter/Micromobility | keine Daten | BLE- und UART-Mitschnitte (z. B. Ninebot/Xiaomi) mit Angriffsszenarien |
| SOME/IP (echtes Fahrzeug) | keine Daten | vsomeip plus Angriffs-Injector |
| ISO 15118 / PLC | keine Daten | – |
| CAN-Spannung (Scission u. ä.) | nur ECUPrint, ohne Lizenz | eigenes Analog-Frontend |
| LIN, TPMS | kaum Daten | SDR (433 MHz) bzw. LIN-Bus-Mitschnitt im Labor |

Eigene Datensätze unter CC BY 4.0 wären **zitierfähige Beiträge** und könnten zuerst auf Hugging Face erscheinen.

## Was schon auf Hugging Face existiert

- `commaai/comma2k19` (MIT, Normaldaten)
- `asana17/ai_can_anomaly_detection_data` / `_runs`: J1939-LKW, quantisierte Modelle plus C-Code. Das ist der **nächste Vorläufer**.
- `keyvan-ai/SecIDS-v2`: TCN-CAN-IDS für Jetson Nano, nicht MCU-Klasse.
- `buckeyeguy/GraphIDS`: nur Evaluationsartefakte.
- **Nicht gefunden:** TFLite-Micro- oder ESP32/STM32-Modelle für CAN-, V2X- oder GNSS-Security. Auch ROAD,
  can-train-and-test, CAN-MIRGU und VeReMi liegen dort nicht. Wir könnten sie als saubere Parquet-Mirrors
  bereitstellen, mit Namensnennung und nur, wo die Lizenz es erlaubt.
