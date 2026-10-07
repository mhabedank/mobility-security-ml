# 02 – Literatur

Die vollständige Bibliografie mit 92 Einträgen, Links und Prüfstatus steht in
[notes/threats-and-papers.md § 9](notes/threats-and-papers.md#9-bibliography). Hier stehen nur die wichtigsten Arbeiten.
Einträge mit `[unverified]` müssen vor dem Zitieren in DBLP oder Google Scholar geprüft werden.

## ML-IDS, die tatsächlich auf MCU- oder Embedded-Hardware laufen

| Arbeit | Plattform | Modell | Ergebnis | Status |
|---|---|---|---|---|
| Im & Lee, IEEE Embedded Systems Letters 17(2), 2025 | **nRF52840** (Cortex-M4F), TFLite Micro | Dual-Branch-CNN (ID-Sequenz + Payload) | **20,44 kB Flash, 26,44 kB RAM**, ohne Quantisierung | [V] |
| TPI-IDS, Springer 2025 (DOI 10.1007/978-3-031-98167-8_24) | **STM32** | IAT → Graustufenbild → quantisiertes CNN | F1 > 0,99 | [V-partial] |
| PIB-IDS, Springer 2026 (DOI 10.1007/978-3-032-10209-6_30) | **STM32F746** | Payload-Bild → quantisiertes CNN | echtzeitfähig | [V-partial] |
| Bonomo et al., SBESC 2024 | **RISC-V** | 5 klassische ML-Modelle | bis F1 = 1,0, echtzeitfähig | [V] |
| Crocioni et al., arXiv 2103.00201 | Automotive-MCUs (ST) | automatisch gemapptes NN | Charakterisierung | [V] |
| Althunayyan, PhD-Thesis Cardiff | MCU | TinyML + Tiny Online Learning pro CAN-ID | F1 0,975–0,993 | [V-partial] |
| Kneib et al., EASI, NDSS 2020 | ressourcenschwache ECU | flankenbasierte Senderidentifikation | < 100 µs, 168× weniger Speicher | [V] |
| Dehrouyeh et al., IEEE Access 2024 | **ESP32** | TinyML-IDS für EV-Ladeinfrastruktur | weniger Latenz und Speicher als klassisches ML | [V] |
| Khandelwal & Shreejith, FPL 2023 / SecCAN 2025 | FPGA / im CAN-Controller | 2-Bit-MLP | 0,24 ms pro Nachricht; SecCAN: Latenz komplett im Empfangsfenster, 73,7 µJ pro Nachricht | [V] |
| Carmo et al., BRACIS 2025 | Raspberry Pi 4 (Vergleichsklasse) | destilliertes DL für Automotive Ethernet | 727 µs, AUC 0,989 | [V] |

**Erkenntnis:** Speicher ist bei CAN-IDS kein Problem, es geht um zehn Kilobyte. Der harte Punkt ist die
**Latenz bei voller Buslast** auf einem Single-Core-ECU, auf dem nebenbei AUTOSAR läuft. Realistisch sind
**fensterbasierte Erkennung** (Inferenz alle N Frames oder T ms) und billige Feature-Updates pro Frame im ISR/DMA-Pfad.

## Fundamentale Angriffs-Papers

Diese Arbeiten zeigen, dass es die Angriffe gibt, gegen die wir Modelle bauen:

- Koscher et al., S&P 2010; Checkoway et al., USENIX Sec 2011; Miller & Valasek, Black Hat 2015 [unverified]
- Francillon, Danev, Čapkun: *Relay Attacks on PKES*, NDSS 2011 [V]
- Rouf et al.: *TPMS Case Study*, USENIX Sec 2010 [V]
- Shoukry et al.: *Non-invasive Spoofing Attacks for ABS*, CHES 2013 [V]
- Trippel et al.: *WALNUT*, EuroS&P 2017 [V]
- Cao et al.: *Adversarial Sensor Attack on LiDAR*, CCS 2019 [V]
- Narain et al.: *Security of GPS/INS based On-road Location Tracking*, S&P 2019 [V]
- Leu et al.: *Ghost Peak (UWB)*, USENIX Sec 2022 [V]
- Takahashi et al.: *Automotive Attacks on LIN-Bus*, JIP 2017 [V]

## CAN-IDS-Klassiker

- Müter & Asaj, IV 2011 (Entropie) [V]
- Song, Kim, Kim, ICOIN 2016 (Zeitintervalle) [V]
- Kang & Kang, PLOS ONE 2016 (DNN) [V]
- Taylor et al., DSAA 2016 (LSTM) [V]
- Seo et al., GIDS, PST 2018 [V]
- Song, Woo, Kim, Vehicular Communications 2020 (DCNN, Ursprung von Car-Hacking) [V]
- Kukkala et al., INDRA, IEEE TCAD 2020 (GRU-Autoencoder) [V]
- Shahriar et al., CANShield, IEEE IoT-J 2023 (Signalebene) [V]
- Hellemans et al., MR-TCN, IEEE T-ITS 2025 [V]

## ECU-Fingerprinting

- Cho & Shin: CIDS, USENIX Sec 2016 (Clock-Skew) [V]; Viden, CCS 2017 [V]
- Choi et al.: VoltageIDS, TIFS 2018 [V]
- Kneib & Huth: Scission, CCS 2018 [V]
- Foruhandeh et al.: SIMPLE, ACSAC 2019 [V]
- Kneib et al.: EASI, NDSS 2020 [V]
- **Gegenangriff:** Bhatia et al., *Evading Voltage-Based IDS* (DUET), NDSS 2021 [V]

## Fallstricke und Kritik

Diese Arbeiten sind **Pflichtlektüre vor dem ersten Modell**:

1. **Verma et al.**, *A comprehensive guide to CAN IDS data and introduction of the ROAD dataset*, PLOS ONE 2024 [V]:
   dokumentiert die Artefakte in Car-Hacking.
2. **Kidmose, Kidmose, Meng**, *can-sleuth*, IJIS 2025 [V]: evaluiert 16 IDS auf 6 Datensätzen und findet Abhängigkeiten zwischen Training und Test.
3. **Koltai, Ács, Gazdag**, *CAN We Trust Your Results? A Cross-Dataset Study*, arXiv 2606.30430, 2026 [V]:
   große Leistungsschwankungen zwischen Datensätzen.
4. *Shortcut learning … in frame-level CAN intrusion detection*, Elsevier 2026 [V-partial]: ein reiner
   ID-Lookup erreicht ROC-AUC 0,97–0,99, Random Forests nur auf Timing 0,995.
5. **Blevins et al.**, *Time-Based CAN Intrusion Detection Benchmark*, AutoSec 2021 [V]
6. **Lazeski et al.**, *On the Real-World Applicability of Automotive CAN IDS*, VehicleSec 2026 [V]
7. **Arp et al.**, *Dos and Don'ts of Machine Learning in Computer Security*, USENIX Sec 2022 [V]:
   Sampling Bias, Data Snooping, falsche Metriken, Evaluation nur im Labor.

### Daraus folgendes Evaluationsprotokoll für dieses Repo

- Daten **zeitlich und pro Aufnahme splitten**, nie zufällig pro Frame.
- **Fahrzeug- und datensatzübergreifend** testen. can-train-and-test hat dafür fertige Splits mit unbekannten Fahrzeugen.
- Car-Hacking (HCRL) nur als Plausibilitätscheck verwenden, nie als Hauptergebnis.
- Metriken: **AUC-PR, F1, Recall bei fester FPR, False Positives pro Stunde, Erkennungslatenz** sowie RAM, Flash,
  Latenz und Energie **auf dem Gerät**, inklusive Feature-Extraktion.
- **Masquerade-Angriffe** immer mit evaluieren, denn reine Timing-Detektoren versagen dort.
- Robustheit gegen **adaptive Angreifer** prüfen, mit Evasion-Angriffen, die auf gültigen CAN-Verkehr beschränkt sind.
  Siehe [05 – Toolchain](05-toolchain-und-publishing.md#adversariale-robustheit).

## Surveys für den Related-Work-Teil

- Lampe & Meng, *A survey of deep learning-based intrusion detection in automotive applications*, ESWA 2023 [V]
- *A Survey of Learning-Based IDS for In-Vehicle Network*, arXiv 2505.11551 [V-partial]
- *A Survey of Anomaly Detection in In-Vehicle Networks*, arXiv 2409.07505 [V-partial]
- Dehrouyeh et al., *On TinyML and Cybersecurity: EV Charging Infrastructure Use Case*, IEEE Access 2024 [V]
