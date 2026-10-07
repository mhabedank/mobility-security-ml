# 01 – Bedrohungslandschaft: Was lässt sich mit TinyML angehen?

Details, Quellen und Prüfstatus stehen in [notes/threats-and-papers.md](notes/threats-and-papers.md).

## Bewertungsmaßstab „MCU-Eignung“

| Stufe | Bedeutung |
|---|---|
| **hoch** | Läuft bequem auf Cortex-M4 oder ESP32-S3 mit ≤ 256 kB RAM, ohne Spezialhardware |
| **mittel** | Braucht zusätzliche Sensorik oder ein Analog-Frontend, eine M7-Klasse-MCU oder sorgfältiges Engineering |
| **niedrig** | Die Datenrate oder Modellgröße verlangt nach MPU, FPGA oder SoC |

## Übersicht der Problemfelder

| # | Problem | Angriff | Eingangssignale | MCU-Eignung | Kernliteratur |
|---|---|---|---|---|---|
| 1 | **CAN-IDS (ID/Timing)**: DoS, Fuzzing, Replay, Spoofing, Suspension | Kompromittiertes Steuergerät, OBD-Dongle, Pivot über Telematik/Infotainment | Zeitstempel, CAN-ID, DLC, ID-Sequenzen, Inter-Arrival-Time (IAT) pro ID; bei 500 kbit/s ≤ ~4k Frames/s | **hoch**: Features billig, Modelle 10–100 kB; bereits auf nRF52840, STM32F746 und RISC-V gezeigt | Song 2016; Kang & Kang 2016; Song 2020; INDRA 2020; Im & Lee 2025 |
| 2 | **CAN-IDS (Payload/Signal)**: Masquerade, gezielte Signalfälschung | Legitimes Steuergerät wird stummgeschaltet, der Angreifer sendet mit korrektem Timing | Dekodierte Signale (DBC oder Reverse Engineering), Signal-Korrelationen | **mittel–hoch**: kleine Autoencoder/TCNs pro ID-Gruppe; braucht Signal-Mapping | CANShield 2023; INDRA; ROAD 2024; MR-TCN 2025 |
| 3 | **Senderidentifikation per Clock-Skew** | Masquerade durch ein fremdes Steuergerät | Hochaufgelöste Ankunftszeiten periodischer Nachrichten | **hoch**: RLS + CUSUM, kein Deep Learning nötig; braucht µs-genaue Hardware-Zeitstempel | CIDS (USENIX Sec 2016) |
| 4 | **Senderidentifikation per Spannung** | Masquerade, Bus-off, Angreifer-Identifikation | Analoge CAN_H/CAN_L-Flanken; ADC im MS/s-Bereich | **mittel**: Rechenaufwand gering (EASI < 100 µs), aber das Analog-Frontend ist schwer; die ESP32-ADCs sind zu langsam | Viden, VoltageIDS, Scission, SIMPLE, EASI; Angriff: DUET |
| 5 | **CAN FD** | wie CAN, mit bis zu 64-Byte-Payload | ID, Timing, 64-Byte-Payload | **mittel–hoch**: Timing bleibt billig, Payload-Modelle werden 8× größer | HCRL CAN-FD; SecCAN 2025 |
| 6 | **Automotive Ethernet** (SOME/IP, DoIP, AVTP, gPTP) | Stream-Injection, Service-Spoofing, Missbrauch der Diagnose | Header, Flow-Statistiken, Service-IDs | **niedrig** bei Line-Rate; **mittel** für Flow-Features auf Zonen-Controllern | Jeong 2021; TOW-IDS 2023; Alkhatib 2021; Carmo 2025 |
| 7 | **LIN / FlexRay** | LIN: False-Response-Injection | LIN mit 19,2 kbit/s und festem Schedule | **hoch** (LIN); kaum ML-Literatur, also **neues Feld** | Takahashi 2017 |
| 8 | **Keyless Entry / Relay, UWB** | Relay von LF/UHF, UWB-Distanzverkürzung (Ghost Peak) | RSSI, RF-Fingerprint, UWB-Kanalimpulsantwort (CIR), IMU im Schlüssel | **mittel**: hängt davon ab, ob die Funkchips Rohdaten liefern (z. B. CIR beim DW3000) | Francillon 2011; HODOR 2020; Ghost Peak 2022 |
| 9 | **GNSS-Spoofing/-Jamming** | Spoofer zieht die Position weg; Jammer gegen Diebstahl-Tracking | PVT mit 1–10 Hz, C/N0, AGC, Uhrfehler, IMU mit ~100 Hz, Raddrehzahl | **hoch**: kleines LSTM/MLP für die Plausibilität; mehrere Quellen fusionieren, weil reine INS-Checks umgangen werden können | Dasgupta 2021; Narain 2019 |
| 10 | **TPMS-Spoofing** | Gefälschte 315/433-MHz-Pakete ohne Authentifizierung | Sensor-ID, RSSI, Timing, Druck vs. Raddrehzahl | **hoch** (Rechnen); **fast keine ML-Literatur**, also neues Feld | Rouf 2010 |
| 11 | **Sensor-Spoofing** (LiDAR, Radar, IMU, Raddrehzahl) | Laser-, akustische und magnetische Injektion | Roh-Punktwolken (niedrig) vs. physikalische Invarianten wie Rad vs. IMU vs. GNSS vs. Lenkung (hoch) | **hoch** für Invarianten-Modelle, **niedrig** für Rohdaten aus der Wahrnehmung | Shoukry 2013; WALNUT 2017; Cao 2019 |
| 12 | **V2X-Misbehavior** | Geisterfahrzeuge, falsche Position/Geschwindigkeit, Sybil, Replay | Felder der empfangenen CAM/BSM, RSSI | **mittel–hoch**: Modelle pro Nachricht sind winzig; der V2X-Stack läuft aber meist auf einem SoC | VeReMi 2018; VeReMi Extension 2020 |
| 13 | **EV-Laden** (OCPP, ISO 15118) | OCPP-MITM/DoS, manipulierte Messwerte, Brokenwire | Strom/Spannung/Leistung, OCPP-Statistik | **mittel–hoch**: TinyML auf dem ESP32 bereits gezeigt | Dehrouyeh 2024/2025 |
| 14 | **OBD-II-Dongles** | Unsichere Bluetooth-/WLAN-Dongles als Einfallstor | CAN-Verkehr vom OBD-Port, UDS-Muster | **hoch**: über das Gateway-IDS oder ein IDS im Dongle selbst | Plug-N-Pwned 2020 |
| 15 | **Seitenkanal-/Fault-Injection-Erkennung** | Glitching, EM-Fault-Injection | On-Chip-Telemetrie, Fehlerzähler | **niedrig–mittel**; dünne Literatur | – |
| 16 | **Fahrerprofil / Diebstahlschutz** | Diebstahl mit geklontem Schlüssel oder Relay | CAN-Signale mit 1–10 Hz (Pedal, Lenkung, Drehzahl) | **hoch**: kleines GRU/1D-CNN < 50 kB | Ahmad 2020; „Know your master“ 2016 |
| 17 | **Micromobility** (E-Scooter/E-Bike) | Unauthentifizierte BLE-Kommandos, Tuning, Diebstahl | BLE-GATT, UART/CAN zwischen Display, BMS und Motor, IMU, GPS | **hoch**: die Geräte haben ohnehin ESP32/STM32/nRF; **keine öffentlichen Daten** | Vinayaga-Sureshkanth 2020 |
| 18 | **Telematik (TCU)** | Remote-Exploit, dann Pivot auf CAN (Jeep 2015) | TCU-Netzflüsse; Gateway-Sicht auf den CAN | **niedrig** auf der TCU; **hoch** auf dem Gateway | Miller & Valasek 2015 |

## Einordnung in Regulierung und Architektur

Die Angaben zu den Standards in diesem Abschnitt sind **nicht gegen die Originaltexte geprüft**.

- **UNECE R155** (Cyber Security Management System) verlangt, dass Angriffe im Feld erkannt werden und darauf reagiert wird.
  Ein On-Board-IDS ist die übliche technische Maßnahme dafür. ML schreibt R155 nicht vor.
- **UNECE R156** (Software Update Management System) regelt den Weg für Modell-Updates.
- **ISO/SAE 21434:** Ein ML-IDS ist eine Cybersecurity-Control. Sein Fehlalarmverhalten und der Update-Pfad müssen
  im Cybersecurity Case begründet werden.
- **AUTOSAR IdsM:** Ein TinyML-Detektor ist ein **Security-Sensor**. Er meldet kompakte *Security Events*
  (Event-ID, CAN-ID, Score) an IdsM, keine Rohdaten. Das Rate-Limiting übernimmt IdsM. Die Events laufen
  weiter über das Security Event Memory und IdsR zum Vehicle SOC des OEM.
- **SecOC** ergänzt das IDS, ersetzt es aber nicht. DoS, kompromittierte Steuergeräte mit gültigem Schlüssel, Timing-
  und Suspension-Anomalien sowie Busse ohne SecOC fallen weiterhin dem IDS zu.

**Was das für uns heißt:** Wir berichten immer **False Positives pro Fahrstunde**, nicht nur pro Frame. Ein Beispiel für
die Größenordnung in der Flotte: Bei 1 Fehlalarm pro 1000 h und 10⁶ Fahrzeugen entstehen etwa 1000 Fehlalarme pro Stunde im SOC.

## Fazit

| Kategorie | Problemfelder |
|---|---|
| **Sofort machbar** (Daten vorhanden, MCU-tauglich) | 1, 2, 9, 12, 16 (Daten nur nicht-kommerziell), 13 (Lizenz unklar) |
| **Machbar mit eigener Hardware/Datenerhebung** | 3, 7, 8, 10, 14, 17 |
| **Mittelfristig / mit Spezialhardware** | 4, 5, 6 (nur Flow-Features), 11 (nur Invarianten) |
| **Kein TinyML-Ziel** | Line-Rate-Ethernet-DPI, rohe LiDAR-/Radar-Daten, rohe Seitenkanal-Traces |
