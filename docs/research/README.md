# Recherche: TinyML für Automotive- und Mobility-Security

Stand: 2026-10-07

## Aufbau

- **Deutsche Zusammenfassungen** (`01`–`05`) für Entscheidungen und Planung.
- **Englische Rohnotizen** unter [`notes/`](notes/) mit allen Details, Quellen und dem Prüfstatus jeder Aussage:
  - [notes/threats-and-papers.md](notes/threats-and-papers.md): 18 Problemfelder, 92 Referenzen
  - [notes/datasets.md](notes/datasets.md): rund 40 Datensätze inkl. Lizenzen
  - [notes/hardware.md](notes/hardware.md): rund 40 MCUs/SoCs, CAN-Hardware, Laboraufbau
  - [notes/toolchain-and-publishing.md](notes/toolchain-and-publishing.md): Training, Konvertierung, Benchmarking, Hugging Face, Repo-Struktur

### Prüfstatus und Einschränkungen

Bei der Recherche hat ein Proxy viele Primärquellen blockiert: arXiv, IEEE, ACM, huggingface.co, Zenodo,
die HCRL-Seiten, UNB/CIC und die meisten Herstellerseiten. Geprüft wurde deshalb über Suchergebnisse und
direkt lesbare GitHub-Quellen, zum Beispiel ESP-IDF `soc_caps.h`, PyPI und den `huggingface_hub`-Quellcode.
Die Rohnotizen markieren jede Aussage:

| Markierung | Bedeutung |
|---|---|
| `[V]` | geprüft (Primärquelle, GitHub-Code oder Suchergebnis mit Quellzitat) |
| `[V-partial]` / `[S]` | teilweise geprüft oder nur Sekundärquelle |
| `[U]` / `[unverified]` | nicht geprüft, aus Hintergrundwissen; **vor Verwendung prüfen** |

**Vor jeder Veröffentlichung auf Hugging Face** müssen die Lizenzseiten der verwendeten Datensätze von Hand
geprüft und archiviert werden.

## Kernergebnisse

1. **CAN-Intrusion-Detection ist das reifste TinyML-Ziel.** Es gibt bereits begutachtete Arbeiten mit Modellen,
   die tatsächlich auf MCUs laufen. Beispiel: ein CNN-IDS auf einem nRF52840 mit **20 kB Flash / 26 kB RAM**
   (Im & Lee, IEEE ESL 2025). Weitere gibt es auf STM32F746 und RISC-V. Rechenleistung ist kein Engpass, ein ESP32-S3 hat
   mehr als genug.
2. **Das größte wissenschaftliche Risiko sind die Daten, nicht die Modelle.** Der populäre HCRL-Car-Hacking-Datensatz
   hat Aufnahmeartefakte: Pausen nach Angriffen, Angriffe im Stand aufgenommen, Normalverkehr während der Fahrt.
   Ein einfacher ID-Lookup erreicht darauf eine ROC-AUC von 0,97–0,99. Viele publizierte Ergebnisse von „99,9 %“ sind
   daher Shortcut-Learning. **Unser Mehrwert entsteht durch ehrliche Evaluation**: datensatzübergreifend,
   fahrzeugübergreifend, False Positives pro Stunde, Messungen auf dem Gerät.
3. **Es gibt offen lizenzierte, realistische Datensätze.** Unter **CC BY 4.0**, also mit offener Veröffentlichung der Modelle:
   can-train-and-test (4 Fahrzeuge), CAN-MIRGU (echte Fahrt, 26 physisch verifizierte Angriffe),
   die VeReMi-Familie (V2X) und der GPS-Spoofing-Datensatz von Aissou. ROAD ist wahrscheinlich ebenfalls CC BY 4.0,
   die Lizenz muss noch bestätigt werden. HCRL, SynCAN und TU Eindhoven sind **nur nicht-kommerziell** nutzbar.
4. **Auf Hugging Face ist die Nische frei.** Es wurde kein TFLite-Micro-, ESP32- oder STM32-Security-Modell für
   Automotive gefunden. Der nächste Vorläufer ist `asana17/ai_can_anomaly_detection_runs`.
5. **Hardware:** Für das Prototyping empfiehlt sich der **ESP32-S3**. Er ist billig, hat SIMD (ESP-NN/ESP-DL), einen
   CAN-Controller (TWAI, nur CAN 2.0) sowie WLAN und BLE.
   - **Produktionsnah:** **NXP S32K344** (AEC-Q100, ASIL-D, HSE, 6× CAN FD).
   - **High-End mit NPU:** **STM32N6** (NPU mit 600 GOPS, 3× FDCAN). Dieselbe Toolchain zielt auf den automotive-tauglichen **Stellar P3E**.
   - **Neu:** ESP32-C5 und ESP32-S31 haben CAN FD direkt auf dem Chip.
6. **Toolchain:**
   - Klassisches ML (Random Forest, Extra Trees) wird mit **emlearn** nach C exportiert. Das ist für CAN-IDS oft das beste Werkzeug.
   - Neuronale Netze: Keras 3 → **int8 `.tflite`**. Diese Datei läuft auf ESP32, STM32 und NXP, plus ONNX → ESP-PPQ → `.espdl`
     für maximale Geschwindigkeit auf dem ESP32-S3.
   - **microTVM ist tot**, wir verwenden es nicht.
7. **Low-Hanging Fruits:**
   1. CAN-IDS auf ID- und Timing-Ebene
   2. GNSS-Jamming- und Spoofing-Detektor auf Basis der u-blox-Messwerte
   3. V2X-Misbehavior-Detektor
   4. Masquerade-Erkennung auf Signalebene

   Details in der [Roadmap](../roadmap.md).

## Lücken, die sich für eigene Beiträge eignen

Für folgende Themen wurden **keine öffentlichen Datensätze** und kaum ML-Literatur gefunden:

- Keyless-Entry-/UWB-Relay-Angriffe
- E-Scooter-/Micromobility-Sicherheit (BLE, UART-Bus)
- TPMS-Spoofing
- LIN-Bus
- reale SOME/IP-Daten
- ISO 15118 (Laden)

Das sind Kandidaten für eigene Datensätze und damit für eigene Veröffentlichungen, sowohl Papers als auch Datensätze auf Hugging Face.
