# Public Datasets for Automotive / Mobility Cyber-Security ML (TinyML focus)

Research date: 2026-10-07. Target: TinyML models (ESP32-S3, STM32) to be published on Hugging Face Hub.

## 0. Method and verification caveats (read first)

- **Network restrictions during research:** the environment's egress proxy blocked direct fetches of
  `huggingface.co`, `ocslab.hksecurity.net`, `sites.google.com`, `unb.ca`, `zenodo.org`, `ieee-dataport.org`,
  `arxiv.org`, `ncbi.nlm.nih.gov`, `data.dtu.dk`, `archive.ics.uci.edu`, `osti.gov`, `kaggle.com`, `0xsam.com`.
  Only `github.com` pages could be fetched directly. Everything else was verified through web-search result
  snippets (search engine summaries of the official pages). The web-search budget also ran out near the end.
- **Legend used below:**
  - **[V-GH]** = verified by fetching the GitHub page directly.
  - **[V-S]** = verified from search-engine snippets of the official page/paper (fairly reliable, but not read first-hand).
  - **[CONFLICT]** = sources disagree. **[UNVERIFIED]** = from memory / not confirmed, so check it before relying on it.
- **Before publishing anything on HF, open each dataset's landing page and save a copy of its license text.**
  This is especially important for HCRL, CIC, ROAD, IEEE DataPort and Mendeley entries.

### Licensing primer for "can I publish a model trained on it?"
- **CC BY 4.0 / MIT:** you can redistribute the data (with attribution) and publish derived models openly. These are the safest.
- **CC BY-NC(-SA/-ND):** non-commercial only. Whether trained weights count as "adapted material" is legally unsettled.
  The usual practice is to publish the weights under a matching NC license, state the training data, and **not** re-upload the raw data.
  With **ND**, re-hosting a modified or preprocessed version of the dataset (for example a cleaned HF mirror) is clearly not allowed.
- **Custom "academic/non-commercial" terms (HCRL, SynCAN):** treat them like NC. SynCAN also forbids field use.
- **IEEE DataPort:** "Open Access" entries are by default CC BY 4.0 **[UNVERIFIED default]**. "Standard" entries require a subscription
  and must not be redistributed.

---

## 1. Summary table

| Dataset | Domain | Year | Size | Labels / attacks | License | Redistributable? | TinyML suitability | URL |
|---|---|---|---|---|---|---|---|---|
| HCRL Car-Hacking | CAN (HS) | 2018 | ~0.95 GB CSV (DoS 190 MB, Fuzzy 198 MB, Gear 230 MB, RPM 239 MB, normal 87 MB) [V-GH mirror]; ~17.6 M frames | DoS, Fuzzy, Gear spoof, RPM spoof; frame-level flag T/R | Academic use + cite [V-S]; reported CC BY-NC-ND 4.0 / NC-SA [CONFLICT] | **No** (only via official site) | High (ID+DLC+8 bytes+Δt), but trivially easy, so useful only as a baseline | https://ocslab.hksecurity.net/Datasets/car-hacking-dataset |
| HCRL CAN-Intrusion (OTIDS) | CAN | 2017 | [UNVERIFIED] ~4.6 M frames | DoS, Fuzzy, Impersonation (ID 0x164), normal; uses remote frames | Academic + cite (HCRL) [V-S] | No | Medium; remote-frame timing is specific to this setup | https://ocslab.hksecurity.net/Datasets/CAN-intrusion-dataset |
| HCRL Survival Analysis | CAN, 3 cars | 2018 | [UNVERIFIED] small (25–100 s captures) | Flooding, Fuzzy, Malfunction on Sonata, Soul, Spark | Academic + cite (HCRL); IEEE DataPort copy | No | High; the only real multi-vehicle repeated-attack set from HCRL | https://ocslab.hksecurity.net/Datasets/survival-ids |
| HCRL Car Hacking: Attack & Defense Challenge 2020 | CAN | 2020/21 | 80.7 MB zip (CSV) [V-S] | Flooding, Spoofing, Replay, Fuzzing; Class + SubClass | IEEE DataPort open access (DOI 10.21227/qvr7-n418); likely CC BY 4.0 [UNVERIFIED]; HCRL academic terms may also apply | Unclear; GitHub mirror exists, but don't rely on it | High; harder than Car-Hacking (has replay) | https://ieee-dataport.org/open-access/car-hacking-attack-defense-challenge-2020-dataset |
| HCRL CAN-FD Intrusion | CAN FD | 2021 | [UNVERIFIED] | Flooding, Fuzzing, Malfunction | HCRL academic; IEEE DataPort "documents" (possibly subscriber) | No | Medium (64-byte payloads mean more input dimensions) | https://ocslab.hksecurity.net/Datasets/can-fd-intrusion-dataset |
| HCRL M-CAN / B-CAN Intrusion | CAN (multimedia / body) | ~2022 [UNVERIFIED] | [UNVERIFIED] | DoS / fuzzing types [UNVERIFIED] | HCRL academic | No | High | https://ocslab.hksecurity.net/Datasets |
| X-CANIDS dataset | CAN signals | 2023/24 | 1.11 GB parquet (signals) + 4.44 GB raw [V-S] | Benign real-road + intrusions; 688 signal columns + label | IEEE DataPort open access (DOI 10.21227/epsj-y384); licence likely CC BY 4.0 [UNVERIFIED] | Probably (if CC BY) | Low as-is (688-D); good for signal-subset models | https://ieee-dataport.org/open-access/x-canids-dataset-vehicle-signal-dataset |
| ROAD (ORNL) | CAN raw + signals | 2020/24 | 3.5 h total (33 attack captures ≈ 30 min, 12 ambient ≈ 3 h) [V-S]; size [UNVERIFIED] | Fuzzing, targeted ID fabrication, advanced (accelerator, correlated-signal, max/reverse speedometer), simulated masquerade | Zenodo 10.5281/zenodo.10462795 reportedly **CC BY 4.0** [V-S, CONFLICT with one snippet claiming NC-SA] | Yes if CC BY confirmed | High; realistic stealthy attacks; signal-translated version provided | https://zenodo.org/records/10462796 / https://0xsam.com/road/ |
| SynCAN (ETAS/Bosch) | CAN signals (synthetic) | 2019 | [UNVERIFIED] ~hundreds of MB; 4 train + 6 test zips | Plateau, Continuous, Playback, Suppress, Flooding; per-row label | ETAS custom: **non-commercial only, not for field use** [V-GH]; repository archived 2023 | No (accept terms) | High: 10 IDs, 20 signals, normalised [0,1]; ideal for small AE/LSTM | https://github.com/etas/SynCAN |
| CrySyS CAN log dataset | CAN | 2023 | 26 benign recordings > 2.5 h [V-S] | Fabrication + masquerade (1- or 2-signal variants); attack-gen code included | Data in Brief 2023; licence likely CC BY 4.0 [UNVERIFIED] | Probably | High; signal-level masquerade, so harder | Data in Brief, PMC10724224 |
| can-train-and-test (Lampe & Meng) | CAN, 4 vehicles | 2023/24 | 7.5 GB, 236 CSV, 193 M lines [V-S] | ~10+ attack types per vehicle (DoS, fuzzing, gear/RPM/speed spoof, standstill, interval, systematic, double/triple…) [partly UNVERIFIED]; 4 train/test splits incl. unseen-vehicle tests | **CC BY 4.0** [V-S] | **Yes** | High; frame-level; cross-vehicle generalisation | https://data.dtu.dk/articles/dataset/can-train-and-test/24805533 , https://bitbucket.org/brooke-lampe/can-train-and-test |
| CAN-MIRGU | CAN (moving car with ADAS) | 2024 | 17 h benign + 2 h 54 min attacks [V-S]; .log (candump) [V-GH] | 26 physically verified real attacks (DoS, fuzzing, replay, spoofing on 13 IDs) + 10 simulated masquerade/suspension | **CC BY 4.0** (UCI) [V-S] | **Yes** | High; realistic; candump format | https://github.com/sampathrajapaksha/CAN-MIRGU , https://archive.ics.uci.edu/dataset/1035/can-mirgu |
| TU/e Automotive CAN Bus Intrusion Dataset v2 | CAN (Opel Astra, Renault Clio, prototype) | 2019/20 | [UNVERIFIED] | Diagnostic, Fuzzing, Replay, Suspension, DoS | **CC BY-NC 4.0** [V-S] | NC only | High | https://doi.org/10.4121/uuid:b74b4928-c377-4585-9432-2004dfa20a5d (4TU / figshare 12696950 v2) |
| CICIoV2024 | CAN (2019 Ford) | 2024 | 1,408,219 rows (1,223,737 benign / 184,482 attack) [V-S] | DoS, spoofing (GAS, RPM, SPEED, STEERING) | CIC standard terms (redistribute with citation) vs. CC BY-NC-ND 4.0 [CONFLICT] | Unclear | Very high (ID + 8 bytes, tabular), but reportedly trivially separable | https://www.unb.ca/cic/datasets/iov-dataset-2024.html |
| AutoHack | Multi-bus CAN (C/P/B-CAN, 2023 Hyundai) | 2026 | 309.1 MB [V-S] | Fuzzing, Spoofing, Replay, DoS, UDS-based; physically verified; µs-synced buses | Zenodo, "free for everyone" [V-S]; exact licence [UNVERIFIED] | Probably | High; newest and most realistic; VehicleSec'26 Best Artifact | https://zenodo.org/records/19661007 [UNVERIFIED record id] |
| UIDS-CAN | CAN, multi-vehicle (Kia Soul ICEV, Tesla BEV 2021–2025) | 2025/26 | [UNVERIFIED] | Multiple attack types, cross-vehicle | IEEE DataPort (DOI 10.21227/wk79-ah64); licence [UNVERIFIED] | Unknown | High | https://ieee-dataport.org/documents/uids-can-multi-vehicle-can-intrusion-detection-dataset |
| GEM-CAN | CAN (GEM e6 autonomous shuttle) | 2025/26 | ~143 k frames [V-S] | DoS (ID 0x0), brake/steering-lock tampering | Data in Brief 66:112805; CC BY-NC 4.0 [V-S, may be the article licence] | NC | High; small, explicitly aimed at on-device IDS | https://zenodo.org/records/17834776 |
| CANdid | CAN, 10 vehicles, benign + GPS + video | 2025 | [UNVERIFIED] | Annotated driver actions (no attacks) | [UNVERIFIED] | Unknown | Good for benign modelling and signal reverse engineering | https://www.usenix.org/conference/vehiclesec25/presentation/howson |
| TU Darmstadt "Real-World Applicability of CAN IDS" | CAN | 2024 | [UNVERIFIED] | Real-world attacker models | [UNVERIFIED] | Unknown | Medium | https://tudatalib.ulb.tu-darmstadt.de/handle/tudatalib/5167 |
| AEID (Automotive Ethernet Intrusion Dataset) | Automotive Ethernet (100BASE-T1, AVTP) | 2021 | [UNVERIFIED] pcap | AVTP replay (36 recorded packets) during driving / non-driving | IEEE DataPort open access + HCRL/DCRL terms [CONFLICT] | Unclear | Low–medium (packet windows; CNN on bytes) | https://ieee-dataport.org/open-access/automotive-ethernet-intrusion-dataset |
| TOW-IDS | Automotive Ethernet (AVTP, gPTP, UDP-wrapped CAN) | 2023 | 197 MB zip [V-S] | Normal + 5 attack scenarios | IEEE DataPort **subscriber-only** [V-S] | **No** | Medium | https://ieee-dataport.org/documents/tow-ids-automotive-ethernet-intrusion-dataset |
| SOME/IP (Alkhatib et al.) | SOME/IP | 2021 | ~132 MB train / 130 MB test [V-S] | ~6 SOME/IP attack classes (generated) | Not clearly published [UNVERIFIED] | Unknown | Medium | arXiv 2108.08262 |
| ECUPrint | CAN voltage (physical layer) | 2022 | 229,510 voltage bits @ 500 MS/s + 8.2 M frames for clock skew [V-GH] | 54 ECUs / 10 vehicles (incl. J1939 truck) | No explicit licence; "cite the TIFS 2022 paper" [V-GH] | No (no licence) | Raw: no (500 MS/s). Extracted features (mean/max voltage, bit time) or clock skew: yes | https://github.com/LucianPopaLP/ECUPrint |
| CANMAP voltage dataset | CAN voltage | ~2023 [UNVERIFIED] | [UNVERIFIED] | Bus mapping / ECU id | IEEE DataPort [UNVERIFIED] | Unknown | Low (high-rate ADC) | https://ieee-dataport.org/documents/canmap-voltage-dataset-mapping-can-bus |
| VeReMi | V2X (BSM, simulated) | 2018 | 225 simulations, JSON logs | 5 position-falsification attacks | **CC BY 4.0** [V-GH] | **Yes** | High (pos/speed features per message) | https://veremi-dataset.github.io , Zenodo 20081895 |
| VeReMi Extension | V2X (simulated, sensor-error model) | 2020 (re-hosted 2023/2026) | 3,194,808 rows in combined CSV (~1.2 GB) [V-S] | 19 misbehaviours: constant/random position and speed, offsets, delayed messages, DoS, DoS-random, replay, disruptive, eventual stop, Sybil variants | **CC BY 4.0** [V-GH] | **Yes** | High | https://github.com/VeReMi-dataset/VeReMi-Extension , Zenodo 20090854, Mendeley k62n4z9gdz |
| VeReMi NextGen | V2X (simulated) | 2026 | 180 subsets, JSON | 15 attacks (time delay, position/speed/heading/accel, feigned braking, sudden stop, DoS, Sybil, replay) | **CC BY 4.0** [V-GH] | **Yes** | High | https://veremi-dataset.github.io , Zenodo 19665762 |
| F2MD | V2X simulation framework | 2019–20 | Code | Generate own labelled misbehaviour data | Licence not displayed; Veins/INET are GPL/LGPL [UNVERIFIED] | Code only | Data generator | https://github.com/josephkamel/F2MD |
| TEXBAT | GNSS RF IQ | 2012/2016 (v1.1) | 400 s scenarios at 25 Msps, 16-bit complex; tens of GB [V-S] | 6–8 spoofing scenarios + clean static/dynamic | Free download; no explicit licence [UNVERIFIED] | No (unclear) | Not directly (IQ); must post-process to observables with an SDR receiver | https://radionavlab.ae.utexas.edu/texbat |
| OAKBAT | GNSS RF IQ (GPS L1 C/A + Galileo E1) | 2020+ | [UNVERIFIED] | Spoofing + interference (incl. pure tones), TEXBAT-like | ORNL DOI portal, registration [V-S] | Unknown | As TEXBAT | https://doi.ccs.ornl.gov/ui/doi/100 , https://github.com/oakbat |
| FGI-JSDR (incl. Jammertest 2023) | GNSS RF IQ | 2023–24 | [UNVERIFIED] | Jamming + spoofing scenarios (e.g., Jammertest 17.1.6) | Open access [UNVERIFIED licence] | Unknown | IQ only | Finnish Geospatial Institute (research.fi) |
| SimulaMet Jammertest 2025 NMEA-derived | GNSS low-rate (NMEA; u-blox, Quectel, Sierra) | 2025 | [UNVERIFIED]; 2,000+ km mobility + stationary | Jamming, meaconing, time-spoofing; interval CSV with event types | IEEE DataPort DOI 10.21227/a7v4-xw11; licence [UNVERIFIED] | Unknown | **Very high** (1 Hz NMEA features: fix, sats, HDOP, C/N0, time offsets) | https://ieee-dataport.org/documents/simulamet-jammertest-2025-nmea-derived-dataset |
| Jammertest plan (NPRA) | Metadata | 2022–2026 | JSON/PDF | Test catalogue + transmission schedule (labels for your own recordings) | **MIT** [V-GH] | Yes | Label source for own u-blox captures | https://github.com/NPRA/jammertest-plan |
| GNSS Dataset with Interference & Spoofing (Yunnan Univ.) | GNSS u-blox raw + processed | 2024 | Parts I–V (Mendeley) | Spoofing (HackRF) + jamming (commercial jammer), irregular | Mendeley; likely CC BY 4.0 [UNVERIFIED] | Probably | **Very high** (u-blox observables: C/N0, Doppler, pseudorange, AGC-like) | https://data.mendeley.com/datasets/ccdgjcfvn5 (+ h43s4d4zfn, nxk9r22wd6, jxxcyknzwb, 94f5fzgsrh) |
| GPS Spoofing Detection on UAS (Aissou) | GNSS tracking features | 2022 | [UNVERIFIED] tens of MB | Authentic + simplistic / intermediate / sophisticated spoofing; 13 features × 8 channels | **CC BY 4.0** [V-S] | **Yes** | **Very high** | https://data.mendeley.com/datasets/z7dj3yyzt8 |
| CICEVSE2024 | EV charging (EVSE power, network, host) | 2024 | 36 GB [V-S] | Recon, DoS, backdoor, cryptojacking; idle/charging states | CIC standard (redistribute with citation) [CONFLICT/UNVERIFIED] | Probably with citation | Power-consumption traces: high. Flows: medium | https://www.unb.ca/cic/datasets/evse-dataset-2024.html |
| Federated OCPP 1.6 IDS dataset (DYNABIC) | EV charging / OCPP | 2024/25 | [UNVERIFIED] | Charging-profile manipulation, Denial of Charge, Heartbeat flooding, unauthorised access | IEEE DataPort [UNVERIFIED licence] | Unknown | Medium (message-level features) | https://ieee-dataport.org/documents/federated-ocpp-16-intrusion-detection-dataset |
| OCPP-centric hybrid testbed dataset (Coventry/Huddersfield) | EV charging / OCPP 1.6 & 2.0 | 2025 | 55+ features [V-S] | Multiple OCPP threats | [UNVERIFIED] | Unknown | Medium–high | https://pureportal.coventry.ac.uk/en/datasets/a-novel-dataset-for-ev-charging-infrastructure-security-threats-f/ |
| comma2k19 | Telemetry: CAN + IMU + raw GNSS + video | 2018 | ~100 GB (torrent); HF mirror ~16 GB [V-S] | No attack labels (benign highway) | **MIT** [V-GH] | **Yes** | High for benign models (CAN speed/steer, IMU 100 Hz [UNVERIFIED rate]) | https://github.com/commaai/comma2k19 ; https://huggingface.co/datasets/commaai/comma2k19 |
| HCRL Driving Dataset (driver ID) | CAN-derived signals | 2016/17 | 94,380 rows × 51 features, 1 Hz [V-S] | 10 drivers (A–J) | HCRL academic | No | **Very high** (51-D at 1 Hz) | https://ocslab.hksecurity.net/Datasets/driving-dataset |
| KCID (Kidmose CANid) | CAN raw, 16 drivers, 4 vehicles | 2025 | [UNVERIFIED] | Driver identity, demographics | [UNVERIFIED] | Unknown | High | arXiv 2510.25856 |
| Keyless entry / UWB relay | RF | none found | – | – | – | – | Collect your own (SDR + ESP32/UWB DW3000) | – |
| Micromobility / e-scooter | BLE/CAN | none found | – | – | – | – | Collect your own | – |

---

## 2. Per-dataset notes

### 2.1 CAN (classic)

**HCRL Car-Hacking (Song, Woo, Kim; Vehicular Communications 2020)**: Korea University HCRL.
- Hyundai YF Sonata, logged via OBD-II. Columns: `Timestamp, CAN ID, DLC, DATA[0..7], Flag(T/R)`; normal data has no flag [V-GH mirror].
- Injection rates: DoS (ID 0x000) every 0.3 ms, Fuzzy every 0.5 ms, Gear/RPM spoof every 1 ms. Each dataset has 300 intrusions of 3–5 s, 30–40 min per file [V-S].
- Licence: HCRL says "released for academic purposes, cite our paper" [V-S]. Third-party papers quote CC BY-NC-ND 4.0, others CC BY-NC-SA [CONFLICT]. Treat it as **non-commercial and not redistributable**.
- Unofficial mirrors exist on GitHub (JehadAlyateem/Car-Hacking-Dataset) and Kaggle. Do not use these as a legal source.
- **Critiques:**
  - can-sleuth (Lampe & Meng, 2024/25) and the ROAD guide (Verma et al., PLoS ONE 2024) report that the attacks are trivially detectable: DoS uses ID 0x000 and fuzzing uses random IDs, so models hit ≈100% accuracy.
  - DLC/padding artefacts in some rows. Some models learn timestamps.
  - Normal file lacks labels. Gear/RPM spoofing is simply ID-based.
- **TinyML:** frame features (ID, DLC, 8 bytes, inter-arrival Δt) give 10–11 dimensions, or windows of N frames. Good as a sanity benchmark, but not representative.

**OTIDS / CAN-Intrusion (Lee, Jeong, Kim, PST 2017)**
- KIA Soul. DoS, fuzzy and impersonation (ID 0x164 removed and re-injected). Remote-frame response timing is used for detection.
- Attacks start after 250 s for fuzzy and impersonation [V-S]. HCRL academic terms apply.

**HCRL Survival Analysis (Han, Kwak, Kim 2018)**
- Hyundai Sonata, Kia Soul and Chevrolet Spark. Flooding, fuzzy and malfunction attacks. Captures are 25–100 s long with 1–4 five-second injection windows.
- The ROAD guide calls it the only HCRL set with real attacks repeated on several vehicles [V-S]. Also on IEEE DataPort.
- Critique (can-sleuth): attacks are simple and the captures are very short.

**Car Hacking: Attack & Defense Challenge 2020** (Kang et al., DOI 10.21227/qvr7-n418)
- Hyundai Avante CN7. CSV columns `Timestamp, Arbitration_ID, DLC, Data, Class, SubClass`. 80.69 MB (rev. 20 Mar 2021).
- Pre-split into train and test with a final-round submission set [UNVERIFIED].
- Harder than Car-Hacking because it includes replay. Listed as "open access" on IEEE DataPort, so likely CC BY 4.0, but this is [UNVERIFIED]. Confirm on the page.

**HCRL CAN-FD Intrusion (2021)**: CAN FD traffic from 2021 production cars. Flooding, fuzzing and malfunction attacks. Payloads up to 64 bytes. Access [UNVERIFIED]: IEEE DataPort "documents" may be subscriber-only, while the HCRL page offers it free for academia.

**X-CANIDS (Jeong, Kang, Kim, IEEE TVT 2024)**
- Benign real-road driving plus intrusion data, decoded with `hyundai_ccan_2015.dbc` into 688 signal columns. Files: 1.11 GB parquet signals and 4.44 GB raw.
- IEEE DataPort open access. Valuable for signal-level IDS, but you must select a few relevant signals for an MCU.

**ROAD (Verma et al., PLoS ONE 19(1) 2024; ORNL)**
- One undisclosed vehicle on a dynamometer: 12 ambient captures (~3 h) and 33 attack captures (~30 min).
- Attacks:
  - Real: fuzzing, targeted-ID fabrication, and "advanced" attacks (correlated-signal, max-speedometer, reverse-light, max-engine-coolant…).
  - Simulated: masquerade attacks, made by removing the original ID frames.
- Signal-translated (CAN-D) versions exist for 17 attack captures and all ambient captures.
- Licence: a search snippet attributes **CC BY 4.0** to Zenodo 10.5281/zenodo.10462795 (record 10462796). Another snippet claimed NC-SA [CONFLICT]. The PLoS article itself is CC BY. Verify on Zenodo.
- Known issue: the masquerade attacks are simulated, and some advanced captures have imperfect labels. The authors document the injection intervals in metadata JSON [UNVERIFIED].
- Widely regarded as the most realistic CAN IDS benchmark before 2024.

**SynCAN (Hanselmann et al., IEEE Access 2020 "CANet"; ETAS)**
- Synthetic signal-level CSV with columns `Label, ID, Time, Signal1..4`. 10 IDs, with (2,3,2,1,2,2,2,1,1,4) signals per ID.
- Attacks: plateau, continuous, playback, suppress and flooding [V-GH].
- Licence: ETAS terms allow only "non-commercial purposes such as academic research, teaching, scientific publications, or personal experimentation simulations", and "not in the field". The repository was archived on 2023-07-17 [V-GH/V-S].
- **Risk:** publishing weights is research use and probably OK under an NC model licence. Do not re-upload the data. A commercial product built on SynCAN-trained models is prohibited.
- **TinyML:** excellent (20 normalised signals). Used by CANShield (signal-level CNN-AE; GitHub shahriar0651/CANShield, no licence file shown [V-GH]).

**CrySyS CAN dataset (Gazdag, Ferenc, Buttyán; Data in Brief 2023)**
- 26 benign recordings (>2.5 h). Fabrication and masquerade attacks modifying one or two signals. Attack-generation source code is included [V-S].
- Data in Brief datasets are typically on Mendeley Data under CC BY 4.0 [UNVERIFIED].
- The same group published "CAN We Trust Your Results? A Cross-Dataset Study of Automotive IDS Evaluation" (arXiv 2606.30430, ACSW'26). It is a benchmarking framework over 7 public CAN datasets and is a good evaluation reference.

**can-train-and-test (Lampe & Meng; Computers & Security 2024)**
- 2017 Subaru Forester, 2016 Chevrolet Silverado, 2011 Chevrolet Traverse and 2011 Chevrolet Impala.
- 236 CSV files, 193 M lines, 7.5 GB. Four train/test subsets, including test sets on vehicles unseen in training [V-S].
- Licence **CC BY 4.0** on DTU Data [V-S]. Also on Bitbucket. Companion "can-ml" and "can-dataset" records exist on DTU Data.
- Created specifically to fix the flaws of the HCRL datasets (see can-sleuth). **Best licensed CAN frame-level corpus for open HF publishing.**

**CAN-MIRGU (Rajapaksha et al., VehicleSec 2024)**
- Modern car with ADAS. 17 h benign over 6 days. 26 physically verified real attacks (DoS, fuzzing, replay, spoofing on 13 IDs) and 10 simulated masquerade/suspension attacks (2 h 54 min).
- candump `.log` files plus a metadata file, hosted on Google Drive [V-GH].
- Licence: **CC BY 4.0** on UCI [V-S]. The GitHub README shows no licence [V-GH]. **Redistributable.**

**TU Eindhoven "Automotive CAN Bus Intrusion Dataset v2" (Dupont, Lekidis, den Hartog, Etalle; 4TU)**
- Opel Astra, Renault Clio and a lab prototype. Diagnostic, fuzzing, replay, suspension and DoS attacks.
- **CC BY-NC 4.0** [V-S]. Earlier v1 is from 2019.
- Known issue: short captures, and some attacks only on the prototype [UNVERIFIED].

**CICIoV2024 (Neto et al., Internet of Things 2024; UNB CIC)**
- 2019 Ford. 1,408,219 rows (1,223,737 benign, 184,482 attack). DoS and spoofing (GAS, RPM, SPEED, STEERING_WHEEL).
- Columns: ID plus 8 data bytes, in decimal and binary versions [UNVERIFIED].
- Licence [CONFLICT]: CIC generally says "you may redistribute, republish, and mirror … must cite", while one snippet says CC BY-NC-ND 4.0 (possibly the article licence). Check the footer of the dataset page.
- Critique: the classes are almost perfectly separable, since the DoS ID is fixed and spoofed values are constant [UNVERIFIED but widely reported]. Already mirrored on HF inside `Thi-Thu-Huong/Multi-CAN-Datasets`.

**New datasets, 2024–2026**
- **AutoHack** (Korea Univ. HCRL + Kookmin Univ.; USENIX VehicleSec 2026, Best Artifact Award): 2023 Hyundai. Synchronised C-CAN, P-CAN and B-CAN. Fuzzing, spoofing, replay, DoS and UDS-based attacks with physically verified effects (engine stall, eCall). 309.1 MB on Zenodo, "free to everyone" [V-S]. Licence [UNVERIFIED]. Strong candidate.
- **UIDS-CAN** (Soonchunhyang Univ., Kangbin Yim; IEEE DataPort 10.21227/wk79-ah64): multi-vehicle (Kia Soul, Tesla 2021–2025) for cross-vehicle "universal" IDS. Licence and access [UNVERIFIED].
- **GEM-CAN** (Data in Brief vol. 66, 112805): autonomous GEM e6. ~143 k frames (100 k nominal, 41 k DoS, 1.3 k brake/steering tampering). Explicitly targets lightweight on-device IDS. Zenodo 17834776. CC BY-NC 4.0 [V-S; may be the article licence].
- **CANdid** (Univ. Adelaide, VehicleSec'25): 10 vehicles. Benign CAN with GPS and video-annotated driver actions. Useful for benign modelling and signal reverse engineering. Licence [UNVERIFIED].
- **TU Darmstadt "On the Real-World Applicability of Automotive CAN IDS – Dataset"** (tudatalib 5167, 2024). Licence [UNVERIFIED].
- **KCID** (Kidmose CANid, arXiv 2510.25856, 2025): driver authentication with 16 drivers and 4 vehicles. It also reviews driver-ID datasets.
- **University of Turku J1939 truck dataset** (Renault Euro VI, normal traffic only): already turned into an HF dataset by `asana17` (see §4) [UNVERIFIED original licence].
- **Multi-Fuzzer-CAN 2025**: appears only inside the HF `Multi-CAN-Datasets` bundle. Origin [UNVERIFIED].

### 2.2 CAN FD / Automotive Ethernet / SOME/IP
- **AEID** (Jeong, Jeon, Chung, Kim; HCRL / DCRL 2021): port-mirrored 100BASE-T1 AVTP video-stream traffic from a vehicle camera, in driving and non-driving scenarios. The replay attack is built from 36 recorded packets. Detection uses a CNN on packet windows (arXiv 2102.03546). Hosted on IEEE DataPort open access and the DCRL Google Site.
- **TOW-IDS** (Han, Kwak, Kim; IEEE TVT 2023): AVTP, gPTP and UDP (CAN-over-Ethernet). Normal driving plus 5 attack scenarios. 197 MB zip. **IEEE DataPort subscriber-only**, so it is not redistributable.
- **SOME/IP:** no recognised real-vehicle public dataset. Alkhatib et al. (2021) generated a labelled SOME/IP set (~274 train / ~300 test attacks) whose public availability is unclear [UNVERIFIED]. Most later work uses CANoe or Prescan simulations. **Gap: generate your own data, e.g. with vsomeip and an attack injector.**
- **RTPS/DDS attack dataset (HCRL):** CC BY-NC [V-S]. Relevant to ROS2/DDS vehicles.

### 2.3 Voltage / physical layer
- **ECUPrint** (Popa, Groza et al., IEEE TIFS 2022; Politehnica Univ. Timișoara): 10 vehicles (incl. a J1939 tractor), 54 ECUs, 432 IDs. 229,510 voltage bits sampled at 500 MS/s (2 ns) with a PicoScope 5000, plus 8.2 M frames for clock-skew analysis. Includes environmental variation (cold/warm engine, static/dynamic). Hosted on the university site and OneDrive.
  - **No formal licence**, only a citation request [V-GH], so do not redistribute.
  - TinyML: raw 500 MS/s is far beyond the ESP32/STM32 ADC. Use the clock-skew part (frame timestamps only) or precomputed per-bit features (mean/max voltage, bit time, plateau time) with an external fast ADC or comparator front-end.
- **CANMAP** (IEEE DataPort, W. Yao et al.): a CAN voltage dataset for bus mapping. Details [UNVERIFIED].
- Scission, VoltageIDS and Viden: their original voltage data was **not** found publicly released [UNVERIFIED]. ECUPrint is the de-facto public reference.

### 2.4 V2X misbehaviour
- **VeReMi** (van der Heijden, Lukaseder, Kargl; SecureComm 2018): LuST/Veins simulation. 225 simulations covering 5 position-falsification attacks × 3 attacker densities × 3 traffic densities × 5 seeds. JSON per-vehicle logs (GPS ground truth + received BSMs). **CC BY 4.0** [V-GH]. Now archived on Zenodo record 20081895.
- **VeReMi Extension** (Kamel et al., ICC 2020): adds a sensor-error model and 19 misbehaviour types (incl. DoS, Sybil variants, replay, eventual stop). The combined CSV has 3,194,808 rows (Kaggle mirror ~1.21 GB). **CC BY 4.0** [V-GH]. Zenodo 20090854; Mendeley k62n4z9gdz (2023).
  - Critique: simulated LuST traffic only. Some attacks (e.g., constant position) are trivially caught by plausibility checks, so report per-attack metrics.
- **VeReMi NextGen** (2026, VNC'26): 15 attacks including heading, acceleration and feigned braking. 180 subsets with train/val/test splits and driver profiles. **CC BY 4.0** [V-GH]. Zenodo 19665762.
- **F2MD** (Kamel): Veins/OMNeT++ framework to generate further data, with plausibility checks and ITS-G5/C-V2X support. Licence not displayed on GitHub [V-GH]. Underlying INET/Veins are GPL [UNVERIFIED].
- **TinyML:** per-message features (Δposition vs. speed·Δt, heading consistency, RSSI, beacon interval) give ~10–20 dimensions. Fits easily on an MCU.

### 2.5 GNSS spoofing / jamming
- **TEXBAT** (UT Austin RNL): 8 scenarios (ds1–ds8), 400 s each, with the first 100 s clean. 25 Msps, 16-bit complex IQ. Clean static and dynamic recordings. Free download from rnl-data.ae.utexas.edu.
  - No explicit licence found [UNVERIFIED], so do not re-host.
  - Needs a software receiver (e.g. GNSS-SDR) to derive low-rate observables (C/N0, correlator outputs, AGC proxy) that an MCU could use.
- **OAKBAT** (ORNL): TEXBAT-like but fully reproducible, with GPS L1 C/A and Galileo E1, detailed metadata and interference ("pure tones"). Access via the ORNL DOI portal with registration [V-S]. GitHub "oakbat" holds only metadata.
- **FGI-JSDR** (Finnish Geospatial Institute): open raw IQ jamming and spoofing datasets, including Jammertest 2023 scenario 17.1.6 [V-S]. Licence [UNVERIFIED].
- **Jammertest** (Andøya, Norway, run yearly by NPRA/Nkom/FFI/Justervesenet): the official repo `NPRA/jammertest-plan` holds the test catalogue and timed transmission plans (JSON, MIT) [V-GH]. That makes it an exact **label source** if you record your own u-blox data at Jammertest. 2026 dates were 14–18 September.
- **SimulaMet Jammertest 2025 NMEA-derived dataset** (IEEE DataPort 10.21227/a7v4-xw11): low-rate NMEA logs from commodity IoT GNSS modules (u-blox, Quectel, Sierra). Covers over 2,000 km of driving, tunnels, ferries and **EV charging**, plus stationary runs, with event-interval labels (jamming, meaconing, time spoofing).
  - **Best match for MCU-side GNSS anomaly detection.** Licence [UNVERIFIED].
- **GNSS Dataset with Interference and Spoofing** (Yunnan Univ.; Data in Brief Jun 2024; Mendeley Parts I–V): u-blox receiver. Raw UBX plus processed observables (C/N0, Doppler, pseudorange, carrier phase, az/el, position). 5 constellations, 8 bands. Spoofing via HackRF and a commercial jammer, emitted irregularly.
  - Mendeley licence likely CC BY 4.0 [UNVERIFIED].
  - Caveat: a static rooftop antenna and HackRF spoofing are less realistic than Jammertest.
- **GPS Spoofing Detection on UAS** (Aissou et al., Mendeley z7dj3yyzt8 v3, 2022): 13 tracking features (PRN, Doppler, pseudorange, C/N0, TCD, PQP…) across 8 channels. Authentic data plus simplistic, intermediate and sophisticated simulated spoofing. **CC BY 4.0** [V-S]. A companion "autonomous vehicles" variant exists on IEEE DataPort.
  - Caveat: the spoofing is simulated.
- **comma2k19:** contains raw GNSS (u-blox + Qualcomm) for benign baselines. MIT.

### 2.6 Keyless entry / RF / UWB relay
- No public labelled relay-attack dataset (LF/UHF PKES or UWB ranging) was found. The literature covers attack papers only (Francillon et al. 2011, NDSS 2020 keyless-entry, UWBAD 2024 jamming on COTS UWB).
- **Gap and opportunity:** record ESP32/DW3000 UWB ranging (CIR, first-path power, ToF, RSSI) under relay and distance-reduction attacks yourself. TinyML features are low-dimensional.

### 2.7 EV charging
- **CICEVSE2024** (UNB CIC, 2024): two EVSEs (EVSE-A and EVSE-B). Covers power consumption, network traffic (flow- and packet-level) and host events (EVSE-B only). 36 GB.
  - Attacks: reconnaissance, DoS, backdoor and cryptojacking, in idle and charging states.
  - Licence [CONFLICT/UNVERIFIED]: CIC standard terms allow redistribution with citation.
  - TinyML: power-consumption time series give a nice low-rate side-channel task.
- **Federated OCPP 1.6 IDS dataset** (EU DYNABIC; Kingston Univ.; IEEE DataPort): charging-profile manipulation, Denial of Charge, heartbeat flooding and unauthorised access.
- **OCPP-centric hybrid testbed dataset** (Coventry / Huddersfield, Oct 2025): real OCPP chargers, EVSE testers and simulated EVs. 55+ features (message semantics, FSM transitions, timing, payload, network).
- No public ISO 15118 / PLC (HomePlug Green PHY) attack dataset was found [UNVERIFIED].

### 2.8 Sensor / telemetry / driver behaviour
- **comma2k19** (MIT): 33 h of I-280 commute in 2019 one-minute segments. Includes CAN (speed, steering, wheel speeds, radar), IMU, GNSS and video. The official HF mirror is `commaai/comma2k19` [V-S]. Useful for benign baselines and sensor-plausibility models (e.g., wheel-speed vs. IMU vs. GNSS consistency, to detect spoofed CAN signals).
- **HCRL Driving Dataset** (Kwak, Woo, Kim 2016): KIA Soul, 10 drivers, ~23 h. 51 OBD-II features at 1 Hz, 94,380 rows. Driver identification and anti-theft use. HCRL academic terms. **TinyML-ideal.**
- **KCID** and **CANdid** (above): newer driver-ID and benign multi-vehicle data.
- **RX-ADS** (EV CAN data, arXiv 2209.02052): data availability [UNVERIFIED].

### 2.9 Micromobility / telematics
- No public labelled e-scooter, e-bike or telematics security dataset was found. The literature covers vulnerability studies only (e.g., Xiaomi M365/ES3 BLE assessments, arXiv 2411.17184).
- **Gap:** an open BLE + UART (e.g., Ninebot/Xiaomi serial bus) attack dataset would be novel.

### 2.10 DBC / signal-decoding resources
- **opendbc** (comma.ai): **MIT** [V-GH]. 70+ DBCs (Toyota, Honda, Hyundai/Kia, VW MQB/MLB/PQ, GM, Ford, Tesla, BMW, Mazda, Volvo, Rivian, BYD, MG, …) [V-GH]. Use it to decode can-train-and-test, CAN-MIRGU and CANdid where the vehicles match.
- **cantools** (Python DBC/KCD/ARXML parser; MIT [UNVERIFIED]), **canmatrix** (format conversion), **cabana** (comma's DBC maker, now in openpilot tools). Listed in awesome-canbus [V-GH].
- **CAN-D** (Verma et al., ORNL, 2020): a 4-step DBC-free signal-decoding pipeline, used to produce ROAD's signal-translated data. Public code release [UNVERIFIED].
- **READ** (Marchetti & Stabili 2019) and **LibreCAN** (Pesé et al., CCS 2019): reverse-engineering algorithms. No official public code found [UNVERIFIED]; you would need to reimplement them.
- **CAN_Reverse_Engineering** (Brent Stone, AFIT): automated payload reverse-engineering pipeline (lexical + semantic analysis). **GPL-3.0** [V-GH].
- **awesome-automotive-can-id** (iDoka): crowd-sourced CAN-ID lists.

---

## 3. TinyML suitability notes (cross-cutting)
- **Frame-level CAN IDS** (ID, DLC, payload bytes, Δt per ID, frequency counters): 10–40 features. Decision trees, small MLPs or 1D-CNNs fit in under 50 kB.
  - Best data: can-train-and-test, CAN-MIRGU, ROAD, AutoHack.
  - Classic HS-CAN at 500 kbit/s carries up to ~4,000 frames/s at full load, so per-frame inference needs to run in under ~250 µs on the MCU. Otherwise use windowed or ID-specific models.
- **Signal-level IDS** (SynCAN, ROAD-signals, X-CANIDS subsets): needs DBC decoding on the MCU. Autoencoders over 10–20 signals are feasible (CANShield-style models scaled down).
- **Timing / clock-skew** (ECUPrint frame part, OTIDS): very cheap features and well suited to an ESP32 TWAI or STM32 FDCAN with hardware timestamps.
- **V2X** (VeReMi family): per-message plausibility features. Good fit.
- **GNSS** (u-blox UBX-NAV-SAT / MON-RF / NMEA): 1–10 Hz, ~10–30 features (C/N0 statistics, AGC, jamming indicator, clock bias/drift, position jumps). Ideal for ESP32-S3.
- **EVSE power traces** (CICEVSE2024): low-rate current/power series fit a 1D-CNN.

---

## 4. Hugging Face Hub status (as found via web search; HF itself was not reachable directly)

**Datasets already on HF**
| Repo | Content | Licence (as shown) | Notes |
|---|---|---|---|
| `Thi-Thu-Huong/Multi-CAN-Datasets` | Bundle of CANFD 2021 (HCRL), CICIoV2024, Multi-Fuzzer-CAN 2025, SynCAN 2025 | [UNVERIFIED] | **Licence risk:** it redistributes HCRL and SynCAN data whose terms do not permit this. Don't depend on it. |
| `buckeyeguy/GraphIDS` | Evaluation artefacts (metrics, UMAP embeddings, CKA) for KD-GAT on hcrl_sa, hcrl_ch and can-train-and-test set_01–04 | cc-by-4.0 [V-S] | Not raw data |
| `asana17/ai_can_anomaly_detection_data` | Built from the Univ. of Turku J1939 truck dataset (Renault Euro VI, normal traffic) | [UNVERIFIED] | Closest existing TinyML-oriented CAN project |
| `swrao/CAN_Values` | Hex CAN ID/data values | [UNVERIFIED] | Unknown provenance |
| `commaai/comma2k19` | Official comma2k19 mirror (~16 GB, 14 tar shards) | MIT | Benign telemetry |
| `bencorn/CICIDS2017`, `bencorn/CICIDS2018` | Generic IT network IDS (not automotive) | – | Shows CIC data is mirrored on HF in practice |

**Not found on HF** (via search): HCRL Car-Hacking (official), ROAD, can-train-and-test, CAN-MIRGU, VeReMi / VeReMi-Extension, CICEVSE2024, TEXBAT/OAKBAT, any GNSS spoofing set.
- **Opportunity:** CC BY 4.0 sets (can-train-and-test, CAN-MIRGU, VeReMi family, Aissou GPS, possibly ROAD) can be legally mirrored as clean Parquet with proper attribution.

**Models on HF**
- `keyvan-ai/SecIDS-v2`: TCN-based CAN IDS, 98.2% accuracy, 4.2 ms on Jetson Nano [V-S]. Licence and training data [UNVERIFIED]. Not MCU-sized.
- `asana17/ai_can_anomaly_detection_runs`: detector comparisons, **quantized models and generated C code for embedded boards** [V-S]. This is the nearest precedent for your project.
- HF paper page "ECoLAD: Deployment-Oriented Evaluation for Automotive Time-Series Anomaly Detection" (2603.10926) is a relevant evaluation methodology.
- **No TFLite-Micro or ESP32/STM32 CAN, V2X or GNSS security model was found on HF.** The niche is open.

---

## 5. Licensing risk summary
1. **HCRL family** (Car-Hacking, OTIDS, Survival, Challenge 2020, CAN-FD, driving dataset):
   - Academic / non-commercial terms. Exact CC variant [CONFLICT].
   - Do not re-host the data. Publish derived weights only with an NC licence and a clear "trained on" statement, or use HCRL sets only for benchmarking.
2. **SynCAN:** custom non-commercial licence, plus "not in the field". Same handling as HCRL.
3. **TU/e v2 (CC BY-NC), GEM-CAN (CC BY-NC?), RTPS (CC BY-NC):** non-commercial only.
4. **CICIoV2024 / CICEVSE2024:** CIC usually allows mirroring with citation, but one source says CC BY-NC-ND [CONFLICT]. Confirm on the dataset page before mirroring.
5. **IEEE DataPort:** open-access entries are probably CC BY. Standard / subscriber entries (TOW-IDS, possibly CAN-FD, UIDS-CAN, OCPP) are **not redistributable**.
6. **TEXBAT, ECUPrint:** no explicit licence, so all rights are reserved by default. Use for research but don't re-host.
7. **Safe for open HF publication (data + models):** can-train-and-test (CC BY 4.0), CAN-MIRGU (CC BY 4.0), VeReMi / Extension / NextGen (CC BY 4.0), Aissou UAS GPS spoofing (CC BY 4.0), comma2k19 (MIT), opendbc (MIT), jammertest-plan (MIT).
   - ROAD is likely in this group (CC BY 4.0 on Zenodo), but verify first.

---

## 6. Key sources consulted
- ROAD guide: Verma et al., PLoS ONE 2024, https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0296879 ; arXiv 2012.14600
- can-sleuth: https://link.springer.com/article/10.1007/s10207-025-01038-8 ; can-train-and-test: arXiv 2308.04972
- CAN-MIRGU: https://www.ndss-symposium.org/wp-content/uploads/vehiclesec2024-43-paper.pdf
- SynCAN: https://github.com/etas/SynCAN ; CANShield: https://github.com/shahriar0651/CANShield
- AutoHack: https://www.usenix.org/conference/vehiclesec26/presentation/song ; https://tlo.korea.ac.kr/en/news/988
- Cross-dataset study: arXiv 2606.30430
- VeReMi: https://github.com/VeReMi-dataset/VeReMi-dataset.github.io
- ECUPrint: https://github.com/LucianPopaLP/ECUPrint
- OAKBAT: https://www.ornl.gov/publication/tool-furthering-gnss-security-research-oak-ridge-spoofing-and-interference-test-battery
- TEXBAT: https://radionavlab.ae.utexas.edu/texbat
- Jammertest: https://github.com/NPRA/jammertest-plan
- CICEVSE2024: https://www.unb.ca/cic/datasets/evse-dataset-2024.html ; CICIoV2024: https://www.unb.ca/cic/datasets/iov-dataset-2024.html
- comma2k19: https://github.com/commaai/comma2k19 ; opendbc: https://github.com/commaai/opendbc
