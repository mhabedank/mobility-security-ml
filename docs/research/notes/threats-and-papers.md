# TinyML for Automotive and Mobility Cyber Security: Threat Landscape and Literature Review

Status: research notes, as of 2026-10-07
Scope: ML models that run on microcontrollers (ESP32-S3, STM32, nRF52/53, Cortex-M4/M7/M33, NXP S32K, RISC-V MCUs) with KB to a few MB of RAM, applied to automotive and mobility security.

## How the sources were checked

- Every reference in the bibliography (Section 9) has a status:
  - **[V]**: title, authors (or at least the author group), venue and year were confirmed by a web search in this session. A link is given.
  - **[V-partial]**: the title and link were confirmed, but authors and/or venue were not.
  - **[unverified]**: this comes from background knowledge. The 200-search budget for the session ran out before it could be checked. Before citing it, look it up in DBLP or Google Scholar.
- arXiv, ACM DL, IEEE Xplore and Semantic Scholar could not be fetched directly because the egress proxy blocked them. Checks used search-engine snippets and repository mirrors such as the NDSS and USENIX pages, institutional repositories and PMC.
- Numbers about hardware feasibility that are marked *(estimate)* are engineering estimates by the author of these notes. They are not quotes from papers.

---

## 1. Executive summary

1. **CAN intrusion detection is the most mature TinyML target.** There are now peer-reviewed deployments on real MCUs:
   - CNN IDS on an **nRF52840** (Cortex-M4F) using TFLite Micro with **20.44 kB flash and 26.44 kB RAM**, without quantization (Im & Lee, IEEE ESL 2025).
   - Image-based CNN IDSs on an **STM32F746** (Springer chapters, 2025/2026).
   - ML IDSs on a **RISC-V** embedded platform (Bonomo et al., SBESC 2024).
   - Older work maps NNs onto **automotive-grade MCUs** for CAN IDS (Crocioni et al., arXiv 2103.00201).

   At line rate, FPGA-based "IDS-ECU" designs reach about 0.24 ms per message (Khandelwal & Shreejith). SecCAN, an IDS inside the CAN controller, completely hides inference within the frame reception window.
2. **Sender identification needs different hardware, not bigger models.**
   - Clock-skew methods (CIDS) only need accurate timestamps. That is trivially MCU-feasible.
   - Voltage methods (Viden, Scission, VoltageIDS, SIMPLE) need an analog front end and a fast ADC. EASI (NDSS 2020) explicitly targets resource-constrained platforms: about 168x less memory and 142x less compute than earlier work, with classification in under 100 µs.
   - Voltage IDSs can be evaded (DUET, NDSS 2021).
3. **Dataset quality is the biggest scientific risk.**
   - The HCRL Car-Hacking dataset has collection artifacts: long silent gaps after each attack, and attacks recorded while stationary versus ambient traffic recorded while driving (Verma et al., PLOS ONE 2024).
   - Recent work shows that "train-only ID lookup" reaches ROC-AUC 0.97 to 0.99 and that timing-only random forests reach 0.995 to 0.997. The near-perfect accuracies reported in hundreds of papers are therefore largely shortcut learning.
   - Use ROAD, CAN-MIRGU, can-train-and-test, and cross-dataset protocols instead (Koltai et al. 2026; Lampe/Kidmose & Meng).
4. **Other good TinyML fits:**
   - Driver profiling and theft detection from CAN signals.
   - GNSS-spoofing plausibility checks that fuse IMU, wheel speed and GNSS.
   - EV charging (EVSE) anomaly detection. TinyML on ESP32 has already been demonstrated (Dehrouyeh et al., IEEE Access 2024).
   - Keyless-entry relay detection from RSSI or UWB channel features.
5. **Poor fits for MCU-only designs:**
   - Line-rate Automotive Ethernet IDS at 100 Mbit/s to 1 Gbit/s. This needs an FPGA, SoC or Raspberry-Pi-class device; Carmo et al. report 727 µs on a Raspberry Pi 4, and Hellemans et al. use MR-TCN on an FPGA. An MCU can still handle flow and statistics features.
   - Raw LiDAR or radar spoofing detection.
   - Side-channel trace analysis.

---

## 2. Problem overview table

Feasibility scale: **high** means it runs comfortably on a Cortex-M4/ESP32-S3 with ≤ 256 kB RAM and needs no special hardware. **med** means it needs an extra sensor or front end, a Cortex-M7-class part, or careful engineering. **low** means the raw data rate or model size points to an MPU, FPGA or SoC.

| # | Problem | Attack vector | Input signals | MCU feasibility (reasoning) | Key papers |
|---|---|---|---|---|---|
| 1 | CAN IDS, ID/timing level (DoS, fuzzing, replay, injection/spoofing, suspension) | Compromised ECU, OBD-II dongle, telematics or infotainment pivot that injects or suppresses frames | Timestamps, CAN ID, DLC, ID sequences, inter-arrival time (IAT) per ID. Classic CAN at 500 kbit/s carries ≤ ~4k frames/s | **High.** Features are cheap and models are 10 to 100 kB. Demonstrated on nRF52840 (26 kB RAM), STM32F746 and RISC-V. Per-frame budget at 500 kbit/s is about 0.25 ms, so window-based detection is easier | Song et al. ICOIN 2016; Kang & Kang PLOS ONE 2016; Seo et al. GIDS PST 2018; Song et al. VehCom 2020; Im & Lee ESL 2025; Khandelwal & Shreejith FPL 2023; Bonomo et al. SBESC 2024; Kukkala et al. INDRA TCAD 2020 |
| 2 | CAN IDS, payload/signal level (masquerade, targeted spoofing, stealthy fabrication) | Suspended legitimate ECU replaced by attacker frames that keep the correct timing | Decoded signals (needs the DBC or reverse engineering, e.g. via CAN-D or ROAD signal files), payload bytes, correlations between signals | **Med–High.** Small autoencoders or TCNs per ID group fit. Multi-scale ensembles like CANShield need trimming. Needs the signal map | Shahriar et al. CANShield IoT-J 2023; Kukkala et al. INDRA; Verma et al. ROAD PLOS ONE 2024; Hellemans et al. MR-TCN T-ITS 2025 |
| 3 | ECU fingerprinting by clock skew (sender identification) | Masquerade: a foreign ECU sends a victim's IDs | High-resolution arrival timestamps of periodic messages | **High.** CIDS uses recursive least squares (RLS) plus CUSUM, with no deep learning needed. Needs µs timestamping from the CAN peripheral. Known weakness: an attacker can emulate the skew | Cho & Shin CIDS USENIX Sec 2016 |
| 4 | ECU fingerprinting by voltage/analog signal | Masquerade, bus-off attacks, attacker identification | Analog CAN_H/CAN_L waveforms, edges, dominant/recessive levels. Needs a multi-MS/s ADC | **Med.** The compute is small: EASI classifies in under 100 µs and cut memory by 168x. The front end is the hard part. ESP32-S3 ADCs are far too slow. STM32G4/H7 ADCs (a few MS/s) or an external ADC/comparator are borderline *(estimate)*. Calibration drifts with temperature. DUET shows these can be evaded | Cho & Shin Viden CCS 2017; Choi et al. VoltageIDS TIFS 2018; Kneib & Huth Scission CCS 2018; Foruhandeh et al. SIMPLE ACSAC 2019; Kneib et al. EASI NDSS 2020; Bhatia et al. DUET NDSS 2021 |
| 5 | CAN FD anomaly detection | Same as CAN, but with up to 64-byte payloads and a 2 to 8 Mbit/s data phase | ID, timing, 64-byte payloads | **Med–High.** Timing and ID features stay cheap. Payload models grow 8x. Hide latency in the reception window as SecCAN does | HCRL CAN-FD dataset; Hellemans et al. 2025 (CAN FD traffic); Khandelwal & Shreejith SecCAN 2025 |
| 6 | Automotive Ethernet (SOME/IP, DoIP, AVTP, gPTP) | Stream injection (AVTP), SOME/IP service spoofing or MITM, DoIP/UDS diagnostic abuse, gPTP time attacks | Packet headers, flow statistics, service/method IDs, timing | **Low** at line rate on an MCU. **Med** for header or flow features on S32K3/S32G-class parts or zone controllers. Raspberry Pi 4 manages 727 µs per detection. FPGA MR-TCN | Jeong et al. VehCom 2021; Han et al. TOW-IDS TIFS 2023; Alkhatib et al. IEMCON 2021; Heo et al. IEICE 2022; Carmo et al. BRACIS 2025; Hellemans et al. T-ITS 2025 |
| 7 | LIN / FlexRay | LIN: false-response injection through error handling. FlexRay: frame spoofing in static or dynamic segments | LIN at 19.2 kbit/s with schedule tables. FlexRay at 10 Mbit/s with a TDMA schedule | **High** for LIN: the bus is tiny and the schedule deterministic, so rules plus a tiny model are enough. **Med** for FlexRay. Very little ML literature exists for either | Takahashi et al. JIP 2017 (LIN); FlexRay exploits CRISIS 2018; Fenzl et al. 2020 |
| 8 | Keyless entry / PKES relay and UWB distance attacks | Relay (amplify and forward) of LF/UHF challenge-response. UWB distance reduction (Ghost Peak) | RSSI on the LF/UHF/BLE links, RF fingerprint (IQ transients), UWB channel impulse response (CIR) and first-path metrics, IMU of the key | **Med.** RSSI or UWB-CIR features plus a small classifier fit on the key or vehicle MCU. RF fingerprinting from raw IQ (HODOR) needs an SDR-grade receiver; it is only feasible if the transceiver exposes the samples | Francillon et al. NDSS 2011; Joo et al. HODOR NDSS 2020; Ahmad et al. J. Supercomput. 2020; Leu et al. Ghost Peak USENIX Sec 2022 |
| 9 | GNSS spoofing / jamming | Spoofer or meaconer drags the position. Jammer for theft or tracking evasion | GNSS PVT at 1 to 10 Hz, C/N0, AGC, clock bias; IMU at about 100 Hz; wheel speed and steering from CAN | **High** for a plausibility model (small LSTM/MLP on IMU + odometry vs. GNSS deltas). Narain et al. show that INS checks alone can be bypassed using road-graph trajectories, so fuse several sources | Dasgupta et al. TRB 2021 (LSTM); Tomasin et al. (IMU NN); Clements et al. (carrier phase + IMU); Sensors 2018 GNSS/INS/odometer; Narain et al. S&P 2019 |
| 10 | TPMS spoofing / tracking | Spoofed 315/433 MHz TPMS packets (no authentication), tracking by static IDs | Sensor ID, RSSI, packet timing, pressure/temperature vs. wheel speed and ABS data | **High** for compute: tiny features. **Low** for literature: hardly any ML papers exist (an open niche) | Rouf et al. USENIX Sec 2010 |
| 11 | Sensor spoofing (LiDAR, radar, IMU/MEMS, wheel speed) | Laser spoofing of LiDAR points, radar spoofing/jamming, acoustic injection into MEMS, magnetic injection into ABS wheel-speed sensors | Raw point clouds (low feasibility) vs. low-rate physical invariants: wheel speed vs. IMU vs. GNSS vs. steering (high feasibility) | **Low** for raw perception data on an MCU. **High** for physics-invariant or residual-based detection of IMU and wheel-speed spoofing | Shoukry et al. CHES 2013; Trippel et al. WALNUT EuroS&P 2017; Cao et al. CCS 2019; SAVIOR USENIX Sec 2020 [unverified] |
| 12 | V2X misbehavior detection | Ghost vehicles, false position/speed in CAM/BSM, Sybil, replay, DoS | Received BSM/CAM fields (position, speed, heading, timing), RSSI, plausibility against own sensors | **Med–High.** Per-message feature models are tiny. The V2X stack usually runs on a Cortex-A or a dedicated V2X SoC, but an MCU-side co-processor is plausible | VeReMi (van der Heijden et al. 2018) [unverified]; VeReMi Extension (Kamel et al. 2020) [unverified] |
| 13 | EV charging (EVSE, OCPP, ISO 15118) | OCPP backend MITM or DoS, charger firmware abuse, ISO 15118 PLC attacks, Brokenwire-style CCS disruption, false meter data | Charger-side current, voltage and power time series, OCPP message statistics, PLC/SLAC metadata | **Med–High.** TinyML on ESP32 has been demonstrated for EVCI cyber-attack detection, including a pruning study | Dehrouyeh et al. IEEE Access 2024; Dehrouyeh et al. arXiv 2025 (pruning); NCAT dual-layer EVSE TinyML [V-partial]; Brokenwire (Köhler et al. 2022) [unverified] |
| 14 | OBD-II dongle attacks | Vulnerable Bluetooth/Wi-Fi/cellular dongles used as a remote entry point to the CAN bus | CAN traffic arriving through the OBD port, diagnostic (UDS) request patterns, dongle radio events | **High.** Handled by the gateway CAN IDS (UDS session/service anomaly detection) or by an IDS inside a security-hardened dongle (dongles are often ESP32-class) | Wen et al. Plug-N-Pwned USENIX Sec 2020 [unverified]; Foster et al. WOOT 2015 [unverified] |
| 15 | Side-channel / fault-injection detection on ECUs | Voltage or clock glitching, EM fault injection, power analysis during key operations | On-chip voltage, clock and temperature sensors, glitch detectors, execution-time or performance-counter telemetry | **Low–Med.** Analysis of raw power traces needs high sampling. Counter or telemetry anomaly models are MCU-feasible. Little automotive-specific literature | "A Novel Tiny Machine Learning Framework for Side Channel Attack Detection in Vehicular Networks" (Wiley ETT, DOI 10.1002/ett.70434) [V-partial] |
| 16 | Driver behavior / anti-theft | Theft with a cloned key or relay, or an unauthorized driver | CAN signals at 1 to 10 Hz (pedal, steering, RPM, speed, gear) | **High.** Short windows and small 1D-CNN/GRU models. Relay-attack ML papers already add driving features | Ahmad et al. 2020; Kwak et al. "Know your master" PST 2016 [unverified] |
| 17 | Micromobility (e-scooter, e-bike) | BLE app-protocol abuse (unauthenticated unlock or acceleration commands), firmware tampering, speed-limit tampering, theft | BLE GATT traffic, UART/CAN between dashboard, BMS and motor controller, IMU, GPS | **High.** These vehicles are already ESP32/STM32-class, so an on-board anomaly or theft detector fits. Academic literature is sparse | Vinayaga-Sureshkanth et al. AutoSec 2020 [unverified] |
| 18 | Telematics (TCU) | Remote exploit of the cellular TCU, then pivot to CAN (Jeep 2015) | TCU-side network flows (Linux-class), gateway view of TCU→CAN traffic | **Low** on the TCU itself, which runs on an MPU. **High** for the gateway MCU monitoring what the TCU emits on CAN | Miller & Valasek 2015 [unverified]; Checkoway et al. USENIX Sec 2011 [unverified]; Foster et al. WOOT 2015 [unverified] |

---

## 3. Problem details

### 3.1 CAN bus intrusion detection (DoS, fuzzing, spoofing, replay, masquerade, suspension)

**Attacks.** CAN has no authentication and is broadcast, with priority set by arbitration.
- **DoS** floods the bus with a high-priority ID such as 0x000.
- **Fuzzing** sends random IDs and payloads.
- **Spoofing/fabrication** injects a target ID with chosen payloads, either at a higher rate than the legitimate sender or interleaved with it.
- **Replay** re-sends captured frames.
- **Suspension** silences an ECU, for example with a bus-off attack.
- **Masquerade** combines suspension with injection at the legitimate timing, so the frequency does not change.

The taxonomy follows ROAD and CAN-MIRGU. CAN-MIRGU contains 26 physically verified injection attacks (DoS, fuzzing, replay, spoofing) on 13 IDs, plus 10 simulated masquerade and suspension attacks, and 17 h of benign driving data.

**Why ML helps.**
- Periodicity and ID sequences differ between vehicles, so learned normal models generalize better than hand-written rules.
- Payload semantics such as correlations between signals catch masquerade attacks that timing rules miss.

**Feasibility on an MCU.**
- Time budget: classic CAN at 500 kbit/s needs about 0.22 to 0.27 ms per frame, which means at most about 4k frames/s at 100 % load. Real bus load is 30 to 60 % *(estimate)*.
- Cheapest features: per-ID inter-arrival time (IAT) statistics, an ID-sequence entropy or Markov model, and a window histogram. These cost a few kB.
- Typical TinyML model: 1D-CNN or MLP on a window of 16 to 64 IDs plus IAT. Size is 10 to 100 kB of int8 weights. Inference is under 1 ms on a Cortex-M4 at 64 to 168 MHz *(estimate; consistent with Im & Lee 2025)*.
- Where it runs: a central gateway or zone-controller MCU sees several buses and is the natural place.

**Key papers.**
- Müter & Asaj IV 2011 (entropy).
- Song et al. ICOIN 2016 (time intervals).
- Kang & Kang PLOS ONE 2016 (DBN-initialized DNN).
- Taylor et al. DSAA 2016 (LSTM).
- Seo et al. GIDS PST 2018. This is the origin of the HCRL Car-Hacking dataset, together with Song et al. VehCom 2020.
- Song et al. VehCom 2020 (reduced Inception-ResNet DCNN).
- Kukkala et al. INDRA TCAD 2020 (GRU recurrent autoencoder, low memory footprint).
- CANShield IoT-J 2023 (signal level, multiple autoencoders).
- Hellemans et al. T-ITS 2025 (MR-TCN for CAN CC, CAN FD and Ethernet on an FPGA).

### 3.2 ECU fingerprinting / sender identification

**Attack.** Masquerade: a compromised ECU sends IDs that belong to another ECU. ID-level IDSs cannot attribute the frames to a sender.

**Approaches.**
- **Clock skew (CIDS, USENIX Security 2016).** Uses the inter-arrival times of periodic messages to estimate each ECU's clock skew, with recursive least squares, and detects shifts with CUSUM. Reported false-positive rate: 0.055 %.
- **Voltage profiles.**
  - Viden (CCS 2017) identifies the attacker ECU with a 0.2 % false identification rate, using "ACK learning".
  - VoltageIDS (IEEE TIFS 2018) was validated while driving and distinguishes errors from bus-off attacks.
  - Scission (CCS 2018) reaches 99.85 % sender identification on two production cars.
  - SIMPLE (ACSAC 2019) works from a single frame, with an equal error rate (EER) of about 0 % in the lab and 0.8985 % in the vehicle.
  - EASI (NDSS 2020) uses edge features on resource-constrained platforms: 99.98 % identification, no false positives, 168x less memory and 142x less compute, and classification in under 100 µs.
- **Attack on voltage IDSs.** DUET (NDSS 2021) uses two colluding ECUs to corrupt the fingerprint during retraining. It reached at least 90 % impersonation success against two state-of-the-art voltage IDSs.

**Why ML helps.** Each sender is a class, so a small classifier works (logistic regression, SVM, small MLP). Online adaptation to temperature and aging is necessary.

**Feasibility on an MCU.**
- Clock skew: **high**, using only timestamps.
- Voltage: **med**. Compute is small (see EASI), but sampling needs an analog front end with a differential probe and an ADC in the MS/s range. The original papers used lab-grade sampling. ESP32-S3 ADCs are not suitable. STM32G4/H7-class parts or external ADCs plus DMA are the realistic route *(estimate)*.
- Good TinyML research angle: an int8 MLP on EASI-style edge features, with on-device drift adaptation and robustness to DUET.

### 3.3 CAN FD and Automotive Ethernet (SOME/IP, DoIP, AVTP)

- **CAN FD.**
  - Payloads are up to 64 bytes and the data phase is faster.
  - The HCRL CAN-FD Intrusion Dataset is on IEEE Dataport.
  - MR-TCN (Hellemans et al. 2025) evaluates CAN FD traffic on an FPGA.
  - SecCAN (Khandelwal & Shreejith, arXiv 2505.14924) puts a quantized ML accelerator into the CAN controller's receive path. On an AMD XCZU7EV FPGA it hides IDS latency within the reception window for all packet sizes, at 73.7 µJ per message.
- **Automotive Ethernet.**
  - AVTP stream injection: Jeong et al. VehCom 2021 use a CNN (F1 ≥ 0.97, recall ≥ 0.99) on a BroadR-Reach testbed.
  - TOW-IDS (Han, Kwak, Kim, IEEE TIFS 2023) uses wavelet features on AVTP, gPTP and UDP (CAN-over-UDP). The dataset is on IEEE Dataport (DOI 10.21227/bz0w-zc12).
  - SOME/IP: Alkhatib et al. IEMCON 2021 (RNN sequential model, F1/AUC > 0.8) and Heo, Kim, Jo IEICE 2022 (header and reception-time features).
  - Low-cost deployment: Carmo et al. BRACIS 2025 use distillation and pruning, reaching 727 µs per detection on a Raspberry Pi 4 with AUC-ROC 0.989.
  - DoIP: no strong ML paper was found. Treat it as UDS-over-IP session anomaly detection.

**MCU feasibility.**
- Line-rate packet inspection at 100BASE-T1 or 1000BASE-T1 is not realistic on Cortex-M *(estimate)*.
- Feasible: per-flow and per-service statistical features computed by the switch or zone controller (S32K3/S32G-class), with a tiny classifier on top. Also feasible: an IDS for SOME/IP Service Discovery (low message rate).

### 3.4 LIN and FlexRay

- LIN: Takahashi et al. (JIP 2017) were the first LIN security evaluation. The attacker exploits error handling to suppress the legitimate response and then sends a false one, demonstrated using a vehicle microcontroller.
  - LIN runs at 19.2 kbit/s with a master-driven schedule, so a TinyML or rule-based monitor is trivial. ML literature is nearly absent, which makes this an easy and novel contribution, although its security impact is lower.
- FlexRay: "Practical security exploits of the FlexRay in-vehicle communication protocol" (CRISIS 2018) [V-partial: title and venue from search; authors unverified]. Fenzl et al. 2020, "Continuous fields: enhanced in-vehicle anomaly detection using ML models" [V-partial]. FlexRay is declining and found mostly in legacy premium chassis networks.

### 3.5 Keyless entry and relay attacks on PKES

- Attack: Francillon, Danev and Čapkun (NDSS 2011) showed relays on 10 models from 8 manufacturers. Relaying only from car to key is enough, at up to 50 m without line of sight.
- Defenses using ML:
  - HODOR (Joo, Choi, Lee, NDSS 2020) applies RF fingerprinting to key-fob signals: false positive rate 0.27 %, false negative rate 0 % on simulated attacks, and 1.32 % false positives under non-line-of-sight conditions, temperature changes and battery aging.
  - Ahmad et al. (J. Supercomputing 76(4), 2020) combine key-fob features with driving-behavior features (DT, SVM, KNN, ANN) and report 99.8 % accuracy.
- UWB is the industry answer, but HRP UWB ranging is attackable. Ghost Peak (Leu et al., USENIX Security 2022) reduced distances from 12 m to 0 m with up to 4 % success per attempt, using a $65 device against Apple U1/NXP/Qorvo chips.
- TinyML angle: a classifier on UWB channel impulse response (CIR) and first-path features or on RSSI consistency across several anchors could run on the vehicle's UWB anchor MCU or the key MCU. Feasibility: **med**. It depends on access to the CIR registers; DW3000-class chips expose them *(estimate)*.

### 3.6 GNSS spoofing detection

- Attack: GNSS signals for civilian use have no authentication. Spoofers can drag the position. Narain, Ranganathan and Noubir (IEEE S&P 2019) show that an attacker can generate road-graph trajectories that defeat INS (gyroscope and accelerometer) consistency checks.
- ML approaches:
  - Dasgupta, Rahman, Islam, Chowdhury (TRB 2021, arXiv 2010.11722) use an LSTM that predicts distance travelled from CAN, IMU and GNSS features, trained on comma2k19.
  - Tomasin et al. (Univ. Padua) train a neural network on the difference between GNSS-derived and IMU-derived velocity [V-partial: venue and year unconfirmed].
  - Clements et al. (UT Austin) use carrier phase plus IMU.
  - Sensors 18(5):1305 (2018) checks GNSS/INS/odometer consistency.
  - Adaptive DBSCAN (arXiv 2510.10766).
- MCU feasibility: **high**. Inputs are at 1 to 100 Hz and windows are short. Add receiver observables such as C/N0, AGC level and clock drift; they are cheap and hard to spoof jointly.

### 3.7 TPMS spoofing

- Rouf et al. (USENIX Security 2010): eavesdropping works at about 40 m, the IDs are static 32-bit values, there is no authentication, and the vehicle does not validate input. Spoofed warnings are therefore possible.
- ML literature: none found in this session. That makes it a small, novel TinyML target: plausibility of pressure and temperature against wheel-speed-based indirect TPMS, plus RSSI and timing consistency per sensor ID.

### 3.8 Sensor spoofing (LiDAR, radar, IMU, wheel speed)

- Wheel speed: Shoukry et al. (CHES 2013) injected magnetic fields into ABS wheel-speed sensors without any physical tampering.
- MEMS/IMU: Trippel et al. WALNUT (EuroS&P 2017). 75 % of 20 accelerometer models were vulnerable to output biasing and 65 % to output control.
- LiDAR: Cao et al. (CCS 2019) spoofed obstacles in front of the victim AV.
- Radar: no ML detection paper was verified in this session [gap].
- TinyML angle: detect *physical-invariant violations*, for example wheel-speed vs. IMU vs. GNSS vs. steering-angle vehicle dynamics. A small residual model or autoencoder can run at 100 Hz. Raw LiDAR/radar analysis belongs on the perception SoC.

### 3.9 V2X misbehavior detection

- VeReMi (van der Heijden, Lukaseder, Kargl, SecureComm 2018) and the VeReMi Extension (Kamel et al., ICC 2020) are the standard benchmarks [both unverified in this session because the search budget ran out; widely cited].
- Feature models over BSM/CAM sequences per sender are small, so MCU feasibility is **med–high**. The constraint is architectural: the stack typically runs on a V2X SoC.

### 3.10 EV charging security (OCPP, ISO 15118)

- Dehrouyeh, Yang, Badrkhani Ajaei, Shami (IEEE Access 12:108703–108730, 2024) is a TinyML survey plus a case study on an ESP32 (PlatformIO). They compare delay and memory with traditional ML.
- Dehrouyeh, Shaer, Nikan, Badrkhani Ajaei, Shami (arXiv 2503.14799, 2025) apply pruning-based TinyML optimization to anomaly detection in EVCI.
- A NCAT group has "Dual-layer intrusion detection for EVSE networks: a TinyML-driven …" [V-partial: title from profile URL only]. A search snippet also reported an INT8 MLP on an ESP32 with 0.19 ms latency and 14.77 µJ per inference in TinyML EV/EVSE work. Which paper it belongs to is unclear, so check before citing.
- Threats: OCPP MITM/DoS, false meter values, ISO 15118 PLC/SLAC attacks, and Brokenwire, which disrupts CCS charging wirelessly (USENIX Security 2022) [unverified].
- The CICEVSE2024 dataset (Canadian Institute for Cybersecurity) [unverified] is a candidate benchmark.

### 3.11 OBD-II dongles and telematics

- Dongles: Wen et al., "Plug-N-Pwned" (USENIX Security 2020) [unverified] analyzed 77 dongles [unverified count]. Foster et al. (WOOT 2015) [unverified] attacked telematics dongles over SMS.
- TCUs: Miller & Valasek's 2015 Jeep remote exploit [unverified] and Checkoway et al. 2011 [unverified] are the canonical remote-to-CAN pivots.
- TinyML angle: a gateway IDS for UDS/diagnostic service sequences arriving through the OBD port (rare and structured, so very learnable). A hardened dongle can also run a self-IDS for its radio interface.

### 3.12 Side-channel and fault-injection detection

- Mostly addressed with hardware countermeasures (glitch or voltage detectors). The ML literature specific to automotive is thin. One paper was found: "A Novel Tiny Machine Learning Framework for Side Channel Attack Detection in Vehicular Networks" (Wiley Trans. Emerging Telecom. Tech., DOI 10.1002/ett.70434) [V-partial: authors and year not confirmed].
- MCU feasibility: **low–med**. It is realistic for anomaly detection over on-chip telemetry (supply monitor, clock monitor, retry and error counters, execution timing). It is unrealistic for analyzing raw power or EM traces.

### 3.13 Driver behavior and theft detection

- Driver profiling uses CAN signals. The HCRL "Driving dataset" and "Know your master" (Kwak, Woo, Kim, PST 2016) are [unverified].
- Ahmad et al. (2020, verified) combine driver features with key-fob features against relay theft.
- MCU feasibility: **high**. Signals are 1 to 10 Hz and 10 to 50 features, so a small GRU or 1D-CNN fits in under 50 kB *(estimate)*.

### 3.14 Micromobility (e-scooters, e-bikes)

- Known issue classes: unauthenticated BLE commands (lock/unlock, acceleration), firmware or speed-limit tampering, GPS/IoT-module abuse in sharing fleets, and theft. Academic coverage is sparse. Vinayaga-Sureshkanth et al., "Security and Privacy Challenges in Upcoming Intelligent Urban Micromobility Transportation Systems" (AutoSec 2020) [unverified].
- These vehicles already use ESP32/STM32/nRF MCUs and BLE, so on-device TinyML is a natural fit: BLE command-sequence anomaly detection, IMU-based theft or tamper detection, and plausibility of motor-controller UART/CAN telemetry. Publication opportunity: high. Benchmark data: none; it must be collected.

---

## 4. ML IDS deployed on MCUs and embedded/ECU-class hardware

| Work | Platform | Model | Reported resources and performance | Status |
|---|---|---|---|---|
| Im & Lee, "TinyML-Based IDS for In-Vehicle Network Using CNN on Embedded Devices", IEEE Embedded Syst. Lett. 17(2):67–70, 2025 | **nRF52840** (Cortex-M4F, 256 kB RAM), TFLite Micro | Dual-branch CNN (CAN-ID sequence + data field), feature fusion | **20.44 kB flash, 26.44 kB RAM** without quantization. Lower compute load than baselines, higher detection performance | [V] |
| Crocioni, Gruosso, Pau, Denaro, Zambrano, di Giore, "Characterization of NNs Automatically Mapped on Automotive-grade MCUs", arXiv 2103.00201 (2021) | Automotive-grade MCU family (ST; exact part [unverified]) | NN mapped automatically; case studies are a CAN IDS and Li-ion residual capacity | See paper | [V] title/authors |
| "Temporal Pattern Image-Based Approach for Automotive Intrusion Detection on STM32 Embedded Platform" (TPI-IDS), Springer LNCS/LNNS chapter, DOI 10.1007/978-3-031-98167-8_24 (2025) | **STM32** | IAT → grayscale temporal image → quantized CNN | F1 > 0.99 on all evaluated datasets | [V-partial] (authors unknown) |
| "Payload Image-Based Model for Automotive Intrusion Detection on STM32 Platform" (PIB-IDS), Springer chapter, DOI 10.1007/978-3-032-10209-6_30 (2026) | **STM32F746 Discovery** (Cortex-M7) | CAN ID + payload → image → lightweight quantized CNN | Real-time feasibility shown | [V-partial] |
| Bonomo, Volpato, de Carvalho, Gracioli, "ML-Based Intrusion Detection for Automotive CAN Networks on Embedded Platforms", SBESC 2024, pp. 127–132 | **RISC-V** embedded platform | 5 classical ML models; DoS and impersonation; public and real-vehicle data | Up to 100 % F1; execution times compatible with real time | [V] |
| Althunayyan (Cardiff PhD thesis, ORCA eprint 184547) | MCU (TinyML) | Fully connected TinyML model plus Tiny Online Learning, per CAN ID | F1 0.993, 0.984 and 0.975 on three CAN IDs | [V-partial] |
| Khandelwal & Shreejith, "Exploring Highly Quantised Neural Networks for Intrusion Detection in Automotive CAN", FPL 2023 (arXiv 2401.11030) | FPGA (Zynq-class IDS-ECU) | **2-bit** custom-quantized MLP (CQMLP) | 99.9 % accuracy on DoS, fuzzing and spoofing | [V] |
| Khandelwal & Shreejith, "A Lightweight FPGA-based IDS-ECU Architecture for Automotive CAN" (arXiv 2401.12234, 2022) | FPGA ECU | Quantized MLP | **0.24 ms** per-message latency, 2.3x faster than prior work | [V] (venue unconfirmed) |
| Khandelwal, Wadhwa, Shreejith, "Deep Learning-based Embedded IDS for Automotive CAN" (arXiv 2401.10674) | Hybrid FPGA ECU (accelerator) | Deep CNN | > 99 % accuracy; 94 % less energy and 51.8 % lower latency vs. GPU | [V] (venue unconfirmed) |
| Khandelwal & Shreejith, "Real-Time Zero-Day IDS for Automotive CAN on FPGAs" (arXiv 2401.10724) | FPGA | Unsupervised (autoencoder-type) | About 0.42 ms and 1.1 mJ per inference (from search snippet) | [V-partial] |
| Khandelwal & Shreejith, "SecCAN: An Extended CAN Controller with Embedded Intrusion Detection" (arXiv 2505.14924, 2025) | AMD XCZU7EV FPGA, IDS inside the CAN controller | Custom-quantized ML accelerator | IDS latency fully hidden in the reception window; **73.7 µJ per message**; no software overhead on the ECU | [V] |
| Kukkala, Thiruloga, Pasricha, "INDRA", IEEE TCAD 39(11):3698–3710, 2020 | ECU-class embedded (ARM) | GRU recurrent autoencoder plus intrusion score | Low memory footprint, fast detection (see paper for numbers) | [V] |
| Hellemans, Le Jeune, Rabbani, Preneel, Mentens, "Toward a Real-Time IDS for Modern In-Vehicle Networks", IEEE T-ITS 26(11):18665–18679, 2025 | FPGA | MR-TCN | Real time on CAN CC, CAN FD and Automotive Ethernet | [V] |
| Carmo, de Moura, de Oliveira Filho, Sadok, Zanchettin, BRACIS 2025 (arXiv 2507.01208) | **Raspberry Pi 4** (comparison class) | Distilled and pruned DL for Automotive Ethernet | **727 µs** per detection, AUC-ROC 0.989 | [V] |
| Kneib, Schell, Huth, "EASI", NDSS 2020 | Resource-constrained ECU-class platform | Edge-feature sender identification | < 100 µs classification, 99.98 % identification, 168x memory and 142x compute reduction | [V] |
| Dehrouyeh et al., IEEE Access 2024 | **ESP32** (PlatformIO) | TinyML IDS for EV charging | Lower delay and memory than traditional ML | [V] |
| exorev07/TinyML-Based-Intrusion-Detection-System (GitHub) | ESP32 | CAN IDS, no cloud | Hobby/engineering reference, not peer reviewed | [V] (exists) |
| "NAS-Optimized tinyML intrusion detection for ultralow-power IoT edge devices", Internet of Things (Elsevier) 2026, PII S2542660526001642 | Cortex-M (TFLite Micro, QAT) | NAS + int8 | 2.48 ms, < 20 kB RAM, 0.39 mJ per inference (search snippet). **Generic IoT, not CAN**, but useful as a methodology reference | [V-partial] |

What these deployments show:
- A CAN-ID/payload CNN needs only **tens of kB** of RAM and flash, which is well within ESP32-S3 (512 kB SRAM plus PSRAM) and STM32F4/F7/H7 budgets.
- The hard constraint is **per-frame latency at line rate** in a single-core ECU that also runs AUTOSAR tasks. That is why the Trinity College Dublin group moves inference into FPGA or CAN-controller logic.
- For a TinyML repo, window-level detection with a duty-cycled inference task is the realistic design. Run inference every N frames or every T ms, and keep cheap per-frame feature updates in the ISR or DMA path.

---

## 5. Standards and regulation context

Items in this section come from background knowledge and were not re-verified in this session [unverified]. Check against the official texts.

- **UNECE R155 (Cyber Security Management System, CSMS)** and **UNECE R156 (Software Update Management System, SUMS)** were adopted in June 2020 under WP.29 (1958 Agreement). In the EU they became mandatory for new vehicle types from July 2022 and for all newly registered vehicles from July 2024.
  - R155 requires the manufacturer to detect and respond to cyber attacks on vehicles in the field, provide monitoring and data-forensic capability, and address the threats listed in Annex 5. Annex 5 includes CAN message spoofing, relay attacks on keyless entry, OBD and external-interface threats, and sensor manipulation.
  - An on-board IDS is the usual technical measure behind the "detect" requirement. R155 does not prescribe ML.
- **ISO/SAE 21434:2021** covers cybersecurity engineering for road vehicles across the lifecycle. Relevant clauses:
  - TARA (threat analysis and risk assessment), which derives the need for detection controls.
  - Continual cybersecurity activities: monitoring, event evaluation, vulnerability management.
  - Production and operations, and incident response.
  An ML IDS is a cybersecurity control. Its false-positive and false-negative behavior and its update path must be argued in the cybersecurity case.
- **AUTOSAR IdsM (Intrusion Detection System Manager)** was introduced around R20-11 for Classic and Adaptive Platform.
  - Security sensors (any software component: CAN IDS, SecOC MAC-failure counters, diagnostic access monitors) report *Security Events* to IdsM.
  - IdsM filters and qualifies them (sampling, aggregation, thresholds).
  - IdsM forwards them to the **Security Event Memory (SEM)** for on-board storage and forensics.
  - The **IdsR (IDS Reporter)** sends Qualified Security Events (QSEv) to the backend.
  - A TinyML CAN detector fits as a *security sensor*. It should emit compact events (event ID, context data such as CAN ID, window statistics and score), **not** raw data, and should leave rate limiting to IdsM.
- **Vehicle Security Operations Center (VSOC).** QSEvs flow over telematics to the OEM VSOC, where fleet-level correlation, triage, and R155 monitoring and reporting happen.
  - Architecture: lightweight on-device detection (TinyML, high recall, rate-limited) → IdsM/SEM → IdsR → VSOC with heavier analytics. Model updates are shipped through the R156 SUMS process.
  - Implication for the repo: report detector false-positive rates per hour of driving, not just per frame. VSOC alert budgets are fleet-scale. For example, 1 FP/1000 h across 10^6 vehicles is about 1000 FP/h.
- **SecOC (AUTOSAR Secure Onboard Communication)** adds a MAC and freshness value to CAN/CAN FD PDUs. It complements an IDS, which still covers DoS, compromised key-holding ECUs, timing and suspension anomalies, and buses without SecOC.

---

## 6. Known pitfalls in the literature

1. **Car-Hacking (HCRL) dataset artifacts.**
   - Verma et al. (PLOS ONE 2024, ROAD paper) document a prolonged period with no messages right after each attack in all four attack captures.
   - Attacks were recorded while the vehicle was stationary, but the ambient traffic was recorded while driving. This distribution shift cannot be fixed afterwards.
   - The attacks are also trivial: DoS uses ID 0x000 at high rate, fuzzing uses random IDs, and spoofing (RPM/gear) uses fixed payloads.
2. **Shortcut learning and leakage.**
   - A 2026 article (Elsevier, PII S2590005626004352) [V-partial] reports that train-only ID lookup reaches ROC-AUC 0.970 (CAR) and 0.986 (Survival), and that timing-only random forests reach 0.995 to 0.997.
   - Frame-level random splits leak information. Neighboring frames from the same attack window end up in both train and test.
   - Use time-blocked splits, per-capture splits and cross-vehicle splits.
3. **Simulated vs. physically verified attacks.**
   - Many datasets create attacks by editing logs in post-processing. That ignores arbitration and timing effects.
   - ROAD and CAN-MIRGU provide real, physically verified attacks, and both add masquerade and suspension variants.
   - Blevins et al. (AutoSec 2021) benchmark time-based IDSs on ROAD and find that distribution-agnostic methods beat distribution-based ones by at least 55 % AUC-PR.
4. **No generalization across vehicles or datasets.**
   - can-train-and-test (Lampe & Meng) provides four vehicles from two OEMs with known and unknown vehicle × attack test splits.
   - can-sleuth (Kidmose, Kidmose, Meng, IJIS 2025) evaluates 16 ML IDSs on 6 datasets: HCRL Car Hacking, HCRL Survival, can-train-and-test v1.5, and UNIMORE Bus-Off, DAGA and Ventus. It also shows train-test interdependence in the UNIMORE sets.
   - Koltai, Ács, Gazdag ("CAN We Trust Your Results?", arXiv 2606.30430, accepted at the ACSW'26 automotive cybersecurity workshop) unify 7 datasets and show large performance swings across datasets.
   - Lazeski, Zohner, Hamborg, Krauß (VehicleSec 2026, WIP) study real-world applicability.
5. **Accuracy on imbalanced data.** Use AUC-PR, false positives per hour, detection latency in ms or frames, and time-to-detect per attack instance. See Arp et al., "Dos and Don'ts of ML in Computer Security" (USENIX Security 2022): sampling bias, label inaccuracy, data snooping, inappropriate baselines, inappropriate metrics, lab-only evaluation.
6. **Ignoring adaptive attackers.**
   - DUET evades voltage IDSs.
   - Masquerade attacks at legitimate timing defeat IAT-only detectors.
   - Adversarial manipulation of ML IDSs is studied in "Assessing the Resilience of Automotive IDS to Adversarial Manipulation" (arXiv 2506.10620) [V-partial].
7. **Unrealistic deployment claims.**
   - "Lightweight" often means "fewer parameters on a GPU". Only a minority of papers measure on an MCU (Section 4).
   - Measure on target: flash, RAM (tensor arena), latency including feature extraction, and CPU share at worst-case bus load.
8. **Surveys to anchor the related-work section.**
   - Lampe & Meng, "A survey of deep learning-based intrusion detection in automotive applications", Expert Systems with Applications 2023 [V].
   - "A Survey of Learning-Based IDS for In-Vehicle Network" (arXiv 2505.11551) [V-partial].
   - "A Survey of Anomaly Detection in In-Vehicle Networks" (arXiv 2409.07505) [V-partial].
   - "In-vehicle network IDS: a systematic survey of deep learning-based approaches" (PeerJ CS 2023, PMC10703033) [V-partial].

Recommended evaluation protocol for this repo:
- Train on ROAD and/or CAN-MIRGU benign data, test on their held-out captures, and include can-train-and-test cross-vehicle splits.
- Report results on Car-Hacking only as a sanity check.
- Always split by time and by capture.
- Report F1/AUC-PR, false positives per hour, detection delay, and on-device RAM, flash and latency.

---

## 7. Datasets (quick reference)

| Dataset | Content | Link | Status |
|---|---|---|---|
| HCRL Car-Hacking | Hyundai YF Sonata; DoS, fuzzing, RPM and gear spoofing; via OBD-II | https://ocslab.hksecurity.net/Datasets (origin: GIDS / Song et al.) | [V] via citing papers; has artifacts |
| HCRL Survival Analysis | 3 vehicles (Spark, Sonata, Soul); flooding, fuzzing, malfunction | HCRL | [V] via can-sleuth |
| HCRL CAN-FD Intrusion | CAN FD attacks | https://ieee-dataport.org/documents/can-fd-intrusion-detection-dataset | [V] |
| ROAD | 3.5 h, one vehicle, real fuzzing/fabrication/advanced attacks plus simulated masquerade; signal-translated version | https://doi.org/10.1371/journal.pone.0296879 ; https://zenodo.org/records/10462796 | [V] |
| CAN-MIRGU | 17 h benign, 26 real attacks on 13 IDs plus 10 masquerade/suspension; moving vehicle with ADAS | https://archive.ics.uci.edu/dataset/1035/can-mirgu | [V] |
| can-train-and-test | 4 vehicles (Chevrolet, Subaru), 9 attacks, known/unknown splits, 7.5 GB | https://data.dtu.dk/articles/dataset/can-train-and-test/24805533/1 | [V] |
| TOW-IDS | Automotive Ethernet: AVTP, gPTP, UDP; 5 attack scenarios | https://ieee-dataport.org/documents/tow-ids-automotive-ethernet-intrusion-dataset | [V] |
| UIDS-CAN | Multi-vehicle CAN IDS dataset | https://ieee-dataport.org/documents/uids-can-multi-vehicle-can-intrusion-detection-dataset | [V-partial] |
| Lazeski et al. dataset | Real-world applicability study (TU Darmstadt) | https://tudatalib.ulb.tu-darmstadt.de/handle/tudatalib/5167 | [V-partial] |
| comma2k19 | Driving logs (CAN, GNSS, IMU), used for GNSS spoofing | (used by Dasgupta et al.) | [V] via citing paper |
| VeReMi / VeReMi Extension | V2X misbehavior | (search budget exhausted) | [unverified] |
| CICEVSE2024 | EV charging attacks | (search budget exhausted) | [unverified] |

---

## 8. Ranking: low-hanging fruit for TinyML

1. **CAN ID/timing window IDS on a gateway-class MCU** (STM32F4/H7, ESP32-S3 with a TWAI transceiver, nRF52840).
   - Peer-reviewed MCU baselines exist: 26 kB RAM (Im & Lee 2025) and STM32F746 (PIB-IDS).
   - Public datasets are good (ROAD, CAN-MIRGU).
   - Novelty must come from honest evaluation (cross-dataset, false positives per hour, masquerade) and from on-device latency at worst-case bus load.
2. **Clock-skew sender fingerprinting plus a tiny classifier** (CIDS-style RLS features feeding an int8 MLP). Needs only µs timestamps and adds attribution, which a VSOC values.
3. **Signal-level masquerade detection with a small autoencoder per ID group.** A distilled version of CANShield or INDRA using ROAD signal files.
4. **Driver profiling and anti-theft from CAN signals.** Low data rate and small models, and it pairs with relay-attack detection.
5. **GNSS spoofing plausibility** from IMU, wheel speed, steering and GNSS observables. Small LSTM/TCN; comma2k19 is available.
6. **EVSE-side TinyML anomaly detection.** ESP32 prior art exists. Strong research gap: ISO 15118/OCPP protocol-aware features on the charger MCU.
7. **Niche "first paper" opportunities** with little prior ML work: LIN-bus monitor, TPMS spoofing plausibility, e-scooter BLE and motor-controller anomaly detection.

Medium effort:
- Voltage fingerprinting (needs an analog front end and a fast ADC; EASI shows the compute is small).
- UWB-CIR relay detection.
- V2X misbehavior on a co-processor.

Not a TinyML target:
- Line-rate Automotive Ethernet deep inspection.
- Raw LiDAR or radar spoofing detection.
- Analysis of raw side-channel traces.

---

## 9. Bibliography

Legend: [V] confirmed in this session (title, authors, venue, year). [V-partial] title and link confirmed, some metadata missing. [unverified] from background knowledge, not confirmed because the search budget was exhausted.

### Foundational attacks
1. [unverified] K. Koscher et al., "Experimental Security Analysis of a Modern Automobile," IEEE S&P 2010.
2. [unverified] S. Checkoway et al., "Comprehensive Experimental Analyses of Automotive Attack Surfaces," USENIX Security 2011.
3. [unverified] C. Miller, C. Valasek, "Remote Exploitation of an Unaltered Passenger Vehicle," Black Hat USA 2015 (white paper).
4. [unverified] K.-T. Cho, K. G. Shin, "Error Handling of In-vehicle Networks Makes Them Vulnerable," ACM CCS 2016 (bus-off attack).
5. [V] A. Francillon, B. Danev, S. Čapkun, "Relay Attacks on Passive Keyless Entry and Start Systems in Modern Cars," NDSS 2011. https://www.ndss-symposium.org/ndss2011/relay-attacks-on-passive-keyless-entry-and-start-systems-in-modern-cars/ ; ePrint https://eprint.iacr.org/2010/332
6. [V] I. Rouf, R. Miller, H. Mustafa, T. Taylor, S. Oh, W. Xu, M. Gruteser, W. Trappe, I. Seskar, "Security and Privacy Vulnerabilities of In-Car Wireless Networks: A Tire Pressure Monitoring System Case Study," USENIX Security 2010. https://www.usenix.org/conference/usenixsecurity10/security-and-privacy-vulnerabilities-car-wireless-networks-tire-pressure
7. [V] Y. Shoukry, P. Martin, P. Tabuada, M. Srivastava, "Non-invasive Spoofing Attacks for Anti-lock Braking Systems," CHES 2013. https://doi.org/10.1007/978-3-642-40349-1_4
8. [V] T. Trippel, O. Weisse, W. Xu, P. Honeyman, K. Fu, "WALNUT: Waging Doubt on the Integrity of MEMS Accelerometers with Acoustic Injection Attacks," IEEE EuroS&P 2017. https://www.ieee-security.org/TC/EuroSP2017/accepted.php
9. [V] Y. Cao, C. Xiao, B. Cyr, Y. Zhou, W. Park, S. Rampazzi, Q. A. Chen, K. Fu, Z. M. Mao, "Adversarial Sensor Attack on LiDAR-based Perception in Autonomous Driving," ACM CCS 2019. https://doi.org/10.1145/3319535.3339815 ; arXiv:1907.06826
10. [V] S. Narain, A. Ranganathan, G. Noubir, "Security of GPS/INS based On-road Location Tracking Systems," IEEE S&P 2019. arXiv:1808.03515 https://arxiv.org/abs/1808.03515
11. [V] P. Leu, G. Camurati, A. Heinrich, M. Roeschlin, C. Anliker, M. Hollick, S. Čapkun, J. Classen, "Ghost Peak: Practical Distance Reduction Attacks Against HRP UWB Ranging," USENIX Security 2022. https://www.usenix.org/conference/usenixsecurity22/presentation/leu ; arXiv:2111.05313 (author list from background knowledge; title, venue and ETH/TU Darmstadt affiliation verified)
12. [V] J. Takahashi et al., "Automotive Attacks and Countermeasures on LIN-Bus," Journal of Information Processing 25:220–228, 2017. https://www.jstage.jst.go.jp/article/ipsjjip/25/0/25_220/_article
13. [V-partial] "Practical security exploits of the FlexRay in-vehicle communication protocol," CRISIS 2018 (authors not verified).
14. [unverified] H. Wen, Q. A. Chen, Z. Lin, "Plug-N-Pwned: Comprehensive Vulnerability Analysis of OBD-II Dongles as A New Over-the-Air Attack Surface in Automotive IoT," USENIX Security 2020.
15. [unverified] I. Foster, A. Prudhomme, K. Koscher, S. Savage, "Fast and Vulnerable: A Story of Telematic Failures," USENIX WOOT 2015.
16. [unverified] S. Köhler, R. Baker, M. Strohmeier, I. Martinovic, "Brokenwire: Wireless Disruption of CCS Electric Vehicle Charging," NDSS 2023 (venue uncertain: NDSS 2023 vs. USENIX Security 2022).
17. [unverified] B. Vinayaga-Sureshkanth et al., "Security and Privacy Challenges in Upcoming Intelligent Urban Micromobility Transportation Systems," ACM AutoSec 2020.

### CAN IDS (classic and DL)
18. [V] M. Müter, N. Asaj, "Entropy-based anomaly detection for in-vehicle networks," IEEE Intelligent Vehicles Symposium (IV) 2011, Baden-Baden.
19. [V] H. M. Song, H. R. Kim, H. K. Kim, "Intrusion detection system based on the analysis of time intervals of CAN messages for in-vehicle network," ICOIN 2016, pp. 63–68. https://pure.korea.ac.kr/en/publications/intrusion-detection-system-based-on-the-analysis-of-time-interval/
20. [V] M.-J. Kang, J.-W. Kang, "Intrusion Detection System Using Deep Neural Network for In-Vehicle Network Security," PLOS ONE 11(6):e0155781, 2016. https://doi.org/10.1371/journal.pone.0155781
21. [V] A. Taylor, S. Leblanc, N. Japkowicz, "Anomaly Detection in Automobile Control Network Data with Long Short-Term Memory Networks," IEEE DSAA 2016. https://ieeexplore.ieee.org/document/7796898
22. [V] E. Seo, H. M. Song, H. K. Kim, "GIDS: GAN based Intrusion Detection System for In-Vehicle Network," PST 2018. arXiv:1907.07377 https://arxiv.org/abs/1907.07377
23. [V] H. M. Song, J. Woo, H. K. Kim, "In-vehicle network intrusion detection using deep convolutional neural network," Vehicular Communications 21:100198, 2020. https://pure.korea.ac.kr/en/publications/in-vehicle-network-intrusion-detection-using-deep-convolutional-n/
24. [V] V. K. Kukkala, S. V. Thiruloga, S. Pasricha, "INDRA: Intrusion Detection using Recurrent Autoencoders in Automotive Embedded Systems," IEEE TCAD 39(11):3698–3710, 2020. arXiv:2007.08795 https://arxiv.org/abs/2007.08795
25. [V] M. H. Shahriar, Y. Xiao, P. Moriano, W. Lou, Y. T. Hou, "CANShield: Deep-Learning-Based Intrusion Detection Framework for Controller Area Networks at the Signal Level," IEEE Internet of Things Journal, Dec. 2023. arXiv:2205.01306 https://arxiv.org/abs/2205.01306
26. [unverified] M. Hanselmann, T. Strauss, K. Dormann, H. Ulmer, "CANet: An Unsupervised Intrusion Detection System for High Dimensional CAN Bus Data," IEEE Access 2020.
27. [V] P. Cheng, M. Han, A. Li, F. Zhang, "STC-IDS: Spatial-Temporal Correlation Feature Analyzing based Intrusion Detection System for Intelligent Connected Vehicles," arXiv:2204.10990, 2022.
28. [V] W. Hellemans, L. Le Jeune, M. M. Rabbani, B. Preneel, N. Mentens, "Toward a Real-Time Intrusion Detection System for Modern In-Vehicle Networks," IEEE T-ITS 26(11):18665–18679, 2025. https://research.chalmers.se/en/publication/547769
29. [V] M. Althunayyan et al., "A Robust Multi-Stage Intrusion Detection System for In-Vehicle Network Security using Hierarchical Federated Learning," Vehicular Communications 2024. arXiv:2408.08433
30. [V-partial] "ATHENA: An In-vehicle CAN Intrusion Detection Framework Based on Physical Characteristics of Vehicle Systems," arXiv:2503.17067, 2025.
31. [V-partial] "Lightweight CNN-Based Intrusion Detection for Automotive CAN Bus in Light Commercial Vehicles," 2025, https://acikerisim.btu.edu.tr/items/1d32be14-39a6-42c5-8714-14b104c93795

### ECU fingerprinting
32. [V] K.-T. Cho, K. G. Shin, "Fingerprinting Electronic Control Units for Vehicle Intrusion Detection," USENIX Security 2016. https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/cho
33. [V] K.-T. Cho, K. G. Shin, "Viden: Attacker Identification on In-Vehicle Networks," ACM CCS 2017, pp. 1109–1123. arXiv:1708.08414 https://arxiv.org/abs/1708.08414
34. [V] W. Choi, K. Joo, H. J. Jo, M. C. Park, D. H. Lee, "VoltageIDS: Low-Level Communication Characteristics for Automotive Intrusion Detection System," IEEE TIFS 13(8):2114–2129, 2018. https://doi.org/10.1109/TIFS.2018.2812149
35. [V] M. Kneib, C. Huth, "Scission: Signal Characteristic-Based Sender Identification and Intrusion Detection in Automotive Networks," ACM CCS 2018.
36. [V] M. Foruhandeh, Y. Man, R. Gerdes, M. Li, T. Chantem, "SIMPLE: Single-Frame based Physical Layer Identification for Intrusion Detection and Prevention on In-Vehicle Networks," ACSAC 2019. https://par.nsf.gov/biblio/10189767
37. [V] M. Kneib, O. Schell, C. Huth, "EASI: Edge-Based Sender Identification on Resource-Constrained Platforms for Automotive Networks," NDSS 2020. https://www.ndss-symposium.org/ndss-paper/easi-edge-based-sender-identification-on-resource-constrained-platforms-for-automotive-networks/
38. [V] R. Bhatia, V. Kumar, K. Serag, Z. B. Celik, M. Payer, D. Xu, "Evading Voltage-Based Intrusion Detection on Automotive CAN," NDSS 2021. https://www.ndss-symposium.org/ndss-paper/evading-voltage-based-intrusion-detection-on-automotive-can/

### MCU / embedded / FPGA deployments
39. [V] H. Im, S. Lee, "TinyML-Based Intrusion Detection System for In-Vehicle Network Using Convolutional Neural Network on Embedded Devices," IEEE Embedded Systems Letters 17(2):67–70, 2025. https://doi.org/10.1109/LES.2024.3475470 ; https://ieeexplore.ieee.org/document/10706824/
40. [V] G. Crocioni, G. Gruosso, D. Pau, D. Denaro, L. Zambrano, G. di Giore, "Characterization of Neural Networks Automatically Mapped on Automotive-grade Microcontrollers," arXiv:2103.00201, 2021. https://arxiv.org/abs/2103.00201
41. [V-partial] "Temporal Pattern Image-Based Approach for Automotive Intrusion Detection on STM32 Embedded Platform," Springer, 2025. https://link.springer.com/chapter/10.1007/978-3-031-98167-8_24
42. [V-partial] "Payload Image-Based Model for Automotive Intrusion Detection on STM32 Platform," Springer, 2026 (STM32F746). https://link.springer.com/chapter/10.1007/978-3-032-10209-6_30
43. [V] J. P. A. Bonomo, J. V. Volpato, R. S. de Carvalho, G. Gracioli, "Machine Learning-Based Intrusion Detection for Automotive CAN Networks on Embedded Platforms," SBESC 2024, pp. 127–132. https://sol.sbc.org.br/index.php/sbesc/article/view/32278
44. [V] S. Khandelwal, S. Shreejith, "Exploring Highly Quantised Neural Networks for Intrusion Detection in Automotive CAN," FPL 2023. arXiv:2401.11030 https://arxiv.org/abs/2401.11030
45. [V] S. Khandelwal, S. Shreejith, "A Lightweight FPGA-based IDS-ECU Architecture for Automotive CAN," arXiv:2401.12234 (orig. 2022; venue not confirmed). https://arxiv.org/abs/2401.12234
46. [V] S. Khandelwal, E. Wadhwa, S. Shreejith, "Deep Learning-based Embedded Intrusion Detection System for Automotive CAN," arXiv:2401.10674 (venue not confirmed). https://arxiv.org/abs/2401.10674
47. [V-partial] S. Khandelwal, S. Shreejith, "Real-Time Zero-Day Intrusion Detection System for Automotive Controller Area Network on FPGAs," arXiv:2401.10724. https://arxiv.org/abs/2401.10724
48. [V] S. Khandelwal, S. Shreejith, "SecCAN: An Extended CAN Controller with Embedded Intrusion Detection," arXiv:2505.14924, 2025. https://arxiv.org/abs/2505.14924
49. [V] P. R. X. Carmo, I. de Moura, A. T. de Oliveira Filho, D. Sadok, C. Zanchettin, "Deep Learning-Based Intrusion Detection for Automotive Ethernet: Evaluating & Optimizing Fast Inference Techniques for Deployment on Low-Cost Platform," BRACIS 2025, pp. 229–244. arXiv:2507.01208 https://sol.sbc.org.br/index.php/bracis/article/view/40888
50. [V-partial] M. Althunayyan, PhD thesis, Cardiff University (TinyML and Tiny Online Learning for CAN). https://orca.cardiff.ac.uk/id/eprint/184547
51. [V-partial] "NAS-Optimized tinyML intrusion detection for ultralow-power IoT edge devices," Internet of Things (Elsevier), 2026. https://www.sciencedirect.com/science/article/pii/S2542660526001642 (generic IoT)
52. [V-partial] "Deep Defence on Wheels: A Dual Intrusion Detection System Architecture for Comprehensive In-Vehicle Network Security," arXiv:2610.07489, 2026 (content not reviewed).
53. [V] GitHub: exorev07/TinyML-Based-Intrusion-Detection-System (ESP32 CAN IDS, not peer reviewed). https://github.com/exorev07/TinyML-Based-Intrusion-Detection-System

### Automotive Ethernet
54. [V] S. Jeong, B. Jeon, B. Chung, H. K. Kim, "Convolutional neural network-based intrusion detection system for AVTP streams in automotive Ethernet-based networks," Vehicular Communications 29:100338, 2021. https://doi.org/10.1016/j.vehcom.2021.100338 ; arXiv:2102.03546
55. [V] M. L. Han, B. I. Kwak, H. K. Kim, "TOW-IDS: Intrusion Detection System based on Three Overlapped Wavelets for Automotive Ethernet," IEEE TIFS 2023. Dataset: https://doi.org/10.21227/bz0w-zc12
56. [V] N. Alkhatib, H. Ghauch, J.-L. Danger, "SOME/IP Intrusion Detection using Deep Learning-based Sequential Models in Automotive Ethernet Networks," IEEE IEMCON 2021. arXiv:2108.08262 https://arxiv.org/abs/2108.08262
57. [V] J. Heo, H. Kim, H. J. Jo, "SOME/IP Intrusion Detection System Using Machine Learning," IEICE Trans. Inf. & Syst., Nov. 2022. https://global.ieice.org/en_transactions/information/10.1587/transinf.2022NGL0007/_p

### Keyless entry, GNSS, V2X, EV charging, other
58. [V] K. Joo, W. Choi, D. H. Lee, "Hold the Door! Fingerprinting Your Car Key to Prevent Keyless Entry Car Theft," NDSS 2020. https://www.ndss-symposium.org/ndss-paper/hold-the-door-fingerprinting-your-car-key-to-prevent-keyless-entry-car-theft/ ; arXiv:2003.13251
59. [V] U. Ahmad, H. Song, A. Bilal, M. Alazab, A. Jolfaei, "Securing smart vehicles from relay attacks using machine learning," Journal of Supercomputing 76(4):2665–2682, 2020. https://doi.org/10.1007/s11227-019-03049-4
60. [V] S. Dasgupta, M. Rahman, M. Islam, M. Chowdhury, "Prediction-Based GNSS Spoofing Attack Detection for Autonomous Vehicles," TRB 100th Annual Meeting 2021. arXiv:2010.11722 https://arxiv.org/abs/2010.11722
61. [V-partial] S. Tomasin et al., "GNSS Spoofing Attack Detection By IMU Measurements Through A Neural Network" (Univ. Padua; IEEE conf., ~2022). https://ieeexplore.ieee.org/document/9847562/
62. [V-partial] Clements et al., "Carrier-phase and IMU based GNSS Spoofing Detection for Ground Vehicles" (UT Austin Radionavigation Lab). https://radionavlab.ae.utexas.edu/wp-content/uploads/2023/01/clements-carrier-phase-imu-spoofing-detection.pdf
63. [V-partial] "Spoofing Detection Using GNSS/INS/Odometer Coupling for Vehicular Navigation," Sensors 18(5):1305, 2018. https://doi.org/10.3390/s18051305
64. [V-partial] "GPS Spoofing Attack Detection in Autonomous Vehicles Using Adaptive DBSCAN," arXiv:2510.10766, 2025.
65. [unverified] R. W. van der Heijden, T. Lukaseder, F. Kargl, "VeReMi: A Dataset for Comparable Evaluation of Misbehavior Detection in VANETs," SecureComm 2018. arXiv:1804.06701 (arXiv id from memory)
66. [unverified] J. Kamel, M. Wolf, R. W. van der Heijden, A. Kaiser, P. Urien, F. Kargl, "VeReMi Extension: A Dataset for Comparable Evaluation of Misbehavior Detection in VANETs," IEEE ICC 2020.
67. [V] F. Dehrouyeh, L. Yang, F. Badrkhani Ajaei, A. Shami, "On TinyML and Cybersecurity: Electric Vehicle Charging Infrastructure Use Case," IEEE Access 12:108703–108730, 2024. https://doi.org/10.1109/ACCESS.2024.3437192 ; arXiv:2404.16894
68. [V] F. Dehrouyeh, I. Shaer, S. Nikan, F. Badrkhani Ajaei, A. Shami, "Pruning-Based TinyML Optimization of Machine Learning Models for Anomaly Detection in Electric Vehicle Charging Infrastructure," arXiv:2503.14799, 2025. https://arxiv.org/abs/2503.14799
69. [V-partial] NCAT, "Dual-layer intrusion detection for EVSE networks: a TinyML-driven …" https://profiles.ncat.edu/en/publications/dual-layer-intrusion-detection-for-evse-networks-a-tinyml-driven-/
70. [V-partial] "A Novel Tiny Machine Learning Framework for Side Channel Attack Detection in Vehicular Networks," Trans. Emerging Telecommunications Technologies (Wiley). https://doi.org/10.1002/ett.70434
71. [unverified] B. I. Kwak, J. Woo, H. K. Kim, "Know your master: Driver profiling-based anti-theft method," PST 2016.
72. [unverified] R. Quinonez, J. Giraldo, L. Salazar, E. Bauman, A. Cardenas, Z. Lin, "SAVIOR: Securing Autonomous Vehicles with Robust Physical Invariants," USENIX Security 2020.
73. [V-partial] A. Fenzl et al., "Continuous fields: Enhanced in-vehicle anomaly detection using machine learning models," 2020. https://www.athene-center.de/forschung/publikationen/continuous-fields-enhanced-in-vehicle-anomaly-dete-3527

### Datasets, benchmarks, critiques, surveys
74. [V] M. E. Verma, R. A. Bridges, M. D. Iannacone, S. C. Hollifield, P. Moriano, S. C. Hespeler, B. Kay, F. L. Combs, "A comprehensive guide to CAN IDS data and introduction of the ROAD dataset," PLOS ONE 19(1):e0296879, 2024. https://doi.org/10.1371/journal.pone.0296879 ; arXiv:2012.14600 (full author list from background knowledge; first author, title, venue and year verified)
75. [V] D. H. Blevins, P. Moriano, R. A. Bridges, M. E. Verma, M. D. Iannacone, S. C. Hollifield, "Time-Based CAN Intrusion Detection Benchmark," NDSS AutoSec Workshop 2021. arXiv:2101.05781 https://arxiv.org/abs/2101.05781
76. [V] S. Rajapaksha, G. Madzudzo, H. Kalutarage, A. Petrovski, M. O. Al-Kadri, "CAN-MIRGU: A Comprehensive CAN Bus Attack Dataset from Moving Vehicles for Intrusion Detection System Evaluation," NDSS VehicleSec 2024. https://www.ndss-symposium.org/ndss2024/co-located-events/vehiclesec/accepted-demo-papers-and-posters/ ; dataset https://archive.ics.uci.edu/dataset/1035/can-mirgu
77. [V] B. Lampe, W. Meng, "can-train-and-test: A Curated CAN Dataset for Automotive Intrusion Detection," arXiv:2308.04972 (later journal version; venue not confirmed). https://arxiv.org/abs/2308.04972
78. [V] B. Kidmose (née Lampe), A. Kidmose, W. Meng, "can-sleuth: Investigating and Evaluating Automotive Intrusion Detection Datasets," International Journal of Information Security, 2025. https://doi.org/10.1007/s10207-025-01038-8 ; arXiv:2408.17235
79. [V] B. Lampe, W. Meng, "A survey of deep learning-based intrusion detection in automotive applications," Expert Systems with Applications, 2023.
80. [V] B. Koltai, G. Ács, A. Gazdag, "CAN We Trust Your Results? A Cross-Dataset Study of Automotive IDS Evaluation," arXiv:2606.30430, 2026 (accepted, ACSW'26 Workshop on Automotive Cyber Security). https://arxiv.org/abs/2606.30430
81. [V] K. Lazeski, M. Zohner, J. Hamborg, C. Krauß, "WIP: On the Real-World Applicability of Automotive CAN Intrusion Detection Systems," USENIX VehicleSec 2026, pp. 135–145. https://www.athene-center.de/en/research/publications/wip-on-the-real-world-applicability-of-automotive-5602
82. [V-partial] "Shortcut learning and identifier/composition stress testing in frame-level CAN intrusion detection," Elsevier journal, 2026. https://www.sciencedirect.com/science/article/pii/S2590005626004352
83. [V] D. Arp, E. Quiring, F. Pendlebury, A. Warnecke, F. Pierazzi, C. Wressnegger, L. Cavallaro, K. Rieck, "Dos and Don'ts of Machine Learning in Computer Security," USENIX Security 2022. https://www.usenix.org/conference/usenixsecurity22/presentation/arp
84. [V-partial] "A Survey of Learning-Based Intrusion Detection Systems for In-Vehicle Network," arXiv:2505.11551, 2025.
85. [V-partial] "A Survey of Anomaly Detection in In-Vehicle Networks," arXiv:2409.07505, 2024.
86. [V-partial] "In-vehicle network intrusion detection systems: a systematic survey of deep learning-based approaches," PeerJ Computer Science, 2023. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10703033/
87. [V-partial] "Assessing the Resilience of Automotive Intrusion Detection Systems to Adversarial Manipulation," arXiv:2506.10620, 2025.

### Standards (all [unverified] in this session; use official sources)
88. UNECE Regulation No. 155: Cyber security and cyber security management system. https://unece.org/transport/documents/2021/03/standards/un-regulation-no-155-cyber-security-and-cyber-security
89. UNECE Regulation No. 156: Software update and software update management system.
90. ISO/SAE 21434:2021, Road vehicles: Cybersecurity engineering.
91. AUTOSAR, "Specification of Intrusion Detection System Manager" (Classic Platform, from R20-11), "Requirements on Intrusion Detection System", Security Event Memory and IdsR specifications. https://www.autosar.org
92. NXP eIQ Auto ML toolkit (vendor page, [V] exists): https://www.nxp.com/products/processors-and-microcontrollers/s32-automotive-platform/eiq-auto-machine-learning-ml-toolkit:eIQ-AUTO-ML-TOOLKIT

---

### Open verification to-dos
- Confirm authors and venues for the items marked [V-partial] and [unverified], especially VeReMi, SAVIOR, Plug-N-Pwned, Brokenwire (venue), CANet, "Know your master", and the STM32 TPI/PIB-IDS chapter authors.
- Extract exact MCU numbers (latency, RAM) for TPI-IDS and PIB-IDS, INDRA and Crocioni et al. from the full texts. Direct arXiv, IEEE and ACM access was blocked in this environment.
- Look for ML papers on radar spoofing, TPMS and micromobility. None were found or verified before the search budget ran out.
