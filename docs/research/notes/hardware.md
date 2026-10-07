# Hardware Survey: MCUs/Processors for TinyML Security Models in Automotive / Mobility

*Research date: 2026-10-07. Scope: on-device inference for CAN/CAN FD intrusion detection (IDS), RF/GNSS anomaly detection, BLE/UWB keyless-entry anomaly detection.*

## How to read the verification marks

| Mark | Meaning |
|---|---|
| **[V]** | Verified from a primary source: vendor page or datasheet text (seen in search results that quote the vendor domain), or vendor source code (e.g. ESP-IDF `soc_caps.h` on GitHub, read directly). |
| **[S]** | Secondary source: distributor listing, trade press or a search-engine summary of those. Probably right, but check the datasheet before you design with it. |
| **[U]** | Unverified: from background knowledge or an estimate, especially prices. Check before you rely on it. |

**Method limits (be aware):** The sandbox's egress proxy blocked direct fetches of most vendor sites (espressif.com, st.com, nxp.com, infineon.com, renesas.com, mouser, digikey…). Verification therefore used (1) web-search results that quote vendor pages, and (2) direct reads of vendor source code on GitHub (raw.githubusercontent.com). The search budget ran out before PSoC Edge tooling (DEEPCRAFT), CAN-IDS-on-MCU papers, and some prices could be checked. Those items carry [U].

---

## 1. Key findings (TL;DR)

1. **The premise "ESP32 TWAI = CAN 2.0 only" no longer holds for every chip.** ESP-IDF master `soc_caps.h` (read directly) shows **`SOC_TWAI_FD_SUPPORTED` on ESP32-C5 (2 controllers), ESP32-H4 (1) and ESP32-S31 (2)**. ESP32 classic, S2, S3, C3, C6, H2 and **P4** have classic CAN 2.0 TWAI only. ESP32-C61 has no TWAI. [V]
   - Classic TWAI controllers **treat CAN FD frames as errors**, so never attach them to a bus that carries FD traffic. ESP-IDF docs say this explicitly. [V]
2. **ST has a direct NPU path from prototype to production.** The STM32N6 (Neural-ART NPU, 600 GOPS) is the prototyping part. **Stellar P3E** is ST's first automotive MCU with a Neural-ART NPU (80+ GOPS, 4× Cortex-R52+ at 500 MHz, ASIL-D, AEC-Q100, 8× MCAN plus 2× CAN-XL, 10BASE-T1S). P3E production is planned for Q4 2026, and ST Edge AI Core already supports SR6 P3E. [V/S]
3. **NXP:** S32K3 is supported by the **eIQ Auto ML toolkit** [V]. The new **S32K5** (16 nm, MRAM, up to 800 MHz) adds an eIQ Neutron NPU, but it was sampling to lead customers from Q3 2025 and is not yet a hobbyist part. [S] MCX N947 is the cheapest NPU-plus-CAN-FD board (FRDM-MCXN947, about $23). [S]
4. **Infineon AURIX TC4x** has a **PPU (Synopsys/MIPS ARC EV71FS vector DSP)**. It is programmed with the ARC MetaWare toolkit, which includes an NN SDK, and is ASIL-D capable. Its interfaces include CAN-XL, 10BASE-T1S and 5 Gbit Ethernet. A KIT_A3G_TC4D7_LITE board is stocked at Mouser. [S/V]
5. **Toolchain landscape in 2026.** TFLite Micro is now **"LiteRT for Microcontrollers"** [S]. **microTVM has been removed from TVM main**; the last version with it is TVM v0.18 [S], so do not build on it. **ExecuTorch 1.x** has Arm Cortex-M and Ethos-U55/U65/U85 backends [V pytorch docs]. **Edge Impulse was acquired by Qualcomm (March 2025)** and still supports Nordic, Alif and Renesas boards. [S]

---

## 2. Master comparison table

Notes: "CAN" counts on-chip controllers. "Price" means the approximate 1 ku chip price and the single-unit dev-board price in USD unless stated. AEC = AEC-Q100 qualified. FuSa = ISO 26262 capability.

### 2a. Espressif

| Part | Core / clock | SRAM / flash | AI acceleration | CAN | Ethernet | Auto / FuSa / HSM | Chip / board price | TinyML toolchain |
|---|---|---|---|---|---|---|---|---|
| **ESP32 (classic)** | 2× Xtensa LX6, 240 MHz [S] | 520 KB SRAM [U]; external SPI flash (module 4–16 MB) | None (ESP-NN generic C opt.) [V] | **1× TWAI, CAN 2.0 only** [V] | 10/100 EMAC (RMII) [V] | No AEC-Q100 found [S: none found]; no FuSa; secure boot + flash encryption only | ~$2 / DevKitC ~$8–10 [U] | TFLM (esp-tflite-micro + ESP-NN), ESP-DL (older), Edge Impulse, emlearn [V/S] |
| **ESP32-S3** | 2× Xtensa LX7, 240 MHz, **128-bit SIMD (PIE)** [S] | 512 KB SRAM [S]; up to 8–16 MB PSRAM, 16–32 MB flash on modules | Vector instructions; **ESP-NN asm kernels, ESP-DL** [V] | **1× TWAI, CAN 2.0 only** [V] | None (no EMAC) [V] | Consumer/industrial only [U] | ~$2.5–3.5 / DevKitC-1 ~$12–15 [S] | TFLM + ESP-NN (S3-optimised), **ESP-DL v3 (+ESP-PPQ)**, Edge Impulse, emlearn [V] |
| **ESP32-C3** | 1× RISC-V, 160 MHz [S] | 400 KB SRAM [U] | None (ESP-NN generic) [V] | **1× TWAI, classic** [V] | None | Consumer [U] | ~$1.5 / ~$6–8 [U] | TFLM + ESP-NN generic, emlearn |
| **ESP32-C6** | RISC-V HP 160 MHz + LP core [U] | 512 KB SRAM [U] | None | **2× TWAI, classic** [V] | None | Consumer [U] | ~$2 / ~$8–10 [U] | TFLM (no ESP-NN opt. listed), emlearn |
| **ESP32-H2** | RISC-V 96 MHz [U] | 320 KB SRAM [U] | None | **1× TWAI, classic** [V] | None (BLE + 802.15.4 only) | Consumer [U] | ~$1.5 / ~$8 [U] | TFLM, emlearn |
| **ESP32-C5** | RISC-V 240 MHz [S]; dual-band Wi-Fi 6 | 384 KB SRAM [S] | None (ESP-NN not listed → ANSI C) [V] | **2× TWAI with CAN FD** (ISO 11898-1:2015; TX/RX classic + FD) [V] | None | Consumer [U] | ~$2–3 [U] / DevKitC-1 ~$15–25 [S] | TFLM (reference kernels), emlearn; ESP-DL support not confirmed [U] |
| **ESP32-H4** (new) | 2 cores [V] | [U] | — | **1× TWAI with CAN FD** [V] | None | [U] | [U] | TFLM [U] |
| **ESP32-P4 / P4X** | 2× RISC-V HP **400 MHz (rev v3.x)**; 360 MHz on rev v1.x [S] + LP core | 768 KB SRAM + 8 KB TCM; up to 32 MB in-package PSRAM [S] | **AI/SIMD instruction extensions (PIE/QACC)**, ESP-NN + ESP-DL optimised [V]; Person detect 73 ms @360 MHz [V] | **3× TWAI, classic only** [V] | **EMAC with IEEE 1588** [V] | Consumer [U]; no radio (pair with C6) | ~$5–7 [U] / Function-EV-Board ~$55 [S] | ESP-DL (main target), TFLM + ESP-NN, Edge Impulse [V/S] |
| **ESP32-S31** (mass production announced 2026) | 2× RISC-V 320 MHz; **128-bit SIMD on one core** [S/V] | 512 KB SRAM; DDR PSRAM up to 250 MHz [S] | PIE SIMD (shares P4 ESP-NN kernels) [V] | **2× TWAI with CAN FD** [V] | **Gigabit EMAC** with IEEE 1588 [V] | Consumer [U]; Wi-Fi 6 + BT 5.4 + 802.15.4 | [U] (new) | ESP-NN, TFLM; ESP-DL likely [U] |

### 2b. STMicroelectronics

| Part | Core / clock | SRAM / flash | AI accel | CAN | Ethernet | Auto / FuSa / HSM | Chip / board price | Toolchain |
|---|---|---|---|---|---|---|---|---|
| **STM32F4** (e.g. F446) | M4F 180 MHz [U] | 128 KB / 512 KB [U] | None (CMSIS-NN) | 2× bxCAN, classic [U] | Some (F407/F429) [U] | Industrial; no AEC (ST "automotive" variants are SPC5/Stellar) [U] | ~$4–8 / Nucleo ~$15 [U] | ST Edge AI Core / X-CUBE-AI, TFLM + CMSIS-NN, Edge Impulse, emlearn |
| **STM32G4** (G474) | M4F 170 MHz [S] | 128 KB / 512 KB [S] | None (CORDIC/FMAC math accel) | **3× FDCAN** [U: count; FDCAN presence S] | None | Industrial (ST has AEC-Q100 STM32 variants for some lines) [U] | ~$4–6 / NUCLEO-G474RE ~$20 [S] | Same as above |
| **STM32H7** (H723/H725) | M7 550 MHz [S] | 564 KB RAM / 1 MB flash [S] | None (CMSIS-NN, M7 DSP) | **3× FDCAN** (H72x) [U] | 10/100 MAC [S] | Industrial | ~$8–12 / Nucleo ~$30 [U] | Same; note comma **panda runs on STM32H725** (CAN + CAN FD) [V] |
| **STM32U5** (U585) | M33 160 MHz [S] | 786 KB / 2 MB [S] | None | 1× FDCAN [S/U] | None | Industrial; TrustZone, PSA L3/SESIP3 [U] | ~$7–10 / B-U585I-IOT02A ~$65 [U] | Same |
| **STM32N6** (N657) | **Cortex-M55 800 MHz (Helium)** [V] | **4.2 MB RAM**; flashless (ext. xSPI) [V] | **Neural-ART NPU, ~300 MACs, 600 GOPS, ~3 TOPS/W** [V] | **3× FDCAN** [S] | **GbE with TSN** [S] | Industrial/consumer; not automotive [U] | ~$11–15 (1 ku) [S] / NUCLEO-N657X0-Q ~$45–60 [U] (has CAN FD header + RJ45 [S]); STM32N6570-DK ~£172 [S] | **ST Edge AI Core** (Neural-ART compiler), STM32 model zoo, TFLM, Edge Impulse [V/S] |
| **SPC5 (SPC58)** | e200 PowerPC, up to 3 cores [U] | up to 6 MB flash [U] | None | Many M_CAN (CAN FD) [U] | Yes on high-end [U] | **AEC-Q100, ASIL-B/D, HSM** [U] | NDA / eval boards ~$300+ [U] | Plain C (emlearn, hand-ported TFLM) [U] |
| **Stellar SR5 (E1)** | Cortex-M7 (electrification) [V] | [U] | None | CAN FD [U] | [U] | AEC-Q100, ASIL-D, HSM [U] | [U] | **ST Edge AI Core supports Stellar** [V] |
| **Stellar SR6 P3E** | **4× Cortex-R52+ 500 MHz** [V] | **19.5 MB PCM "xMemory"**, up to 1792 KB SRAM [V] | **Neural-ART NPU, 80+ GOPS** (int-quantised) [V] | **8× MCAN (CAN/CAN FD) + 2× XS_CAN (CAN XL)** [V] | 1× 10/100/1000 MAC, AVB, **10BASE-T1S (OA 3-pin)** [V] | **AEC-Q100, ASIL-D, 2nd-gen HSM (EVITA-full), ISO/SAE 21434** [V] | Production planned **Q4 2026** [V]; Mouser "coming soon" [S] | **ST Edge AI Core + Stellar Studio** [V] |

### 2c. NXP

| Part | Core / clock | SRAM / flash | AI accel | CAN | Ethernet | Auto / FuSa / HSM | Price | Toolchain |
|---|---|---|---|---|---|---|---|---|
| **S32K344** | **Cortex-M7 160 MHz, lockstep** [S] | 512 KB / 4 MB [S] | None (M7 + CMSIS-NN) | **6× FlexCAN-FD** [S] | 100 Mbps/1 G **Ethernet TSN/AVB** [S] | **AEC-Q100 Grade 1/2, ASIL-D, HSE-B** [S/V] | ~$10–15 [U] / S32K3X4EVB-T172 ~$150–230 [S] | **eIQ Auto ML toolkit** (automotive-qualified runtime, S32K3 supported) [V]; TFLM + CMSIS-NN; RTD/AUTOSAR MCAL [S] |
| **S32K5** | Cortex cores up to 800 MHz, 16 nm FinFET, **MRAM** [V] | [U] | **eIQ Neutron NPU** [V] | CAN FD (count not found) [U] | Integrated Ethernet switch [V] | ASIL-D isolation [V] | Sampling with lead customers Q3 2025 [V]; not broadly available [U] | eIQ Auto [U] |
| **i.MX RT1170** | M7 1 GHz + M4 400 MHz [V] | 2 MB SRAM, no int. flash [V] | None (M7 + CMSIS-NN) | **3× CAN FD** [V] | **2× GbE (AVB/TSN) + 1× 10/100** [V] | Consumer/industrial/**automotive** grades exist [V]; EdgeLock 400A [V]; no ASIL [U] | ~$15–20 [U] / EVKB ~$200–260 [U] | **eIQ (TFLM, Glow)**, MCUXpresso, Edge Impulse [S] |
| **MCX N947** | 2× M33 150 MHz [V] | 512 KB / 2 MB [S] | **eIQ Neutron NPU** (NXP: up to 42× vs CPU; ~4.8 GOPS [U]) [V] | FlexCAN with CAN FD [S] (count [U]) | 10/100 MAC [S] | Industrial; EdgeLock Secure Enclave [V] | ~$6–9 [U] / **FRDM-MCXN947 ~$23** (board has a CAN-FD transceiver) [S] | **eIQ Neutron SDK / eIQ Toolkit, TFLM**, Edge Impulse [S] |
| **S32G3** (gateway) | up to 8× A53 + 4× M7 lockstep pairs [V] | up to 20 MB SRAM [V] | None on-chip (A53 NEON; LLCE/PFE network accelerators) | **20× CAN/CAN FD** via LLCE [V] | **4× GbE**, PFE, PCIe Gen3 [V] | **ASIL-D, HSE** [V] | $40–80+ chip [U]; GoldBox/RDB3 ~$1–2.5k [U] | Linux (BSP): TFLite/ONNX Runtime/eIQ on A53; the best place for a **central** IDS [U] |

### 2d. Infineon

| Part | Core / clock | SRAM / flash | AI accel | CAN | Ethernet | Auto / FuSa / HSM | Price | Toolchain |
|---|---|---|---|---|---|---|---|---|
| **AURIX TC3xx** (TC375 / TC397) | TriCore 1.6.2, up to 6 cores (4 lockstep), 300 MHz [S] | up to 6.9 MB SRAM / 16 MB flash [S] | None | TC397: **12× CAN FD** [S]; TC375: [U, ~12] | 10/100/1000 [U]; lite kit has 10/100 PHY [S] | **AEC-Q100, ASIL-D, HSM (EVITA-full)** [S] | TC375 ~$15–25 [U] / **KIT_A2G_TC375_LITE ~€92–100** (CAN transceiver + Ethernet PHY on board) [S] | No CMSIS-NN (not Arm): use emlearn / plain-C codegen / hand-ported TFLM with HighTec or Tasking compilers [U] |
| **AURIX TC4x** (TC4D7…) | TriCore 1.8, up to 6 cores, 500 MHz, 28 nm [S] | up to 25 MB flash [S] | **PPU = ARC EV71(FS) SIMD vector DSP (+ CNN MAC)** [S] | CAN FD + **CAN-XL** [S] | up to **5 Gbit Ethernet, 10BASE-T1S**, PCIe [S] | **ASIL-D (incl. AI-based FuSa on PPU), ISO 21434, HSM** [S] | KIT_A3G_TC4D7_LITE in stock at Mouser 2026 [S]; price [U ~€150–300] | **ARC MetaWare for AURIX TC4x: MetaWare compiler, NN SDK (NN compiler), DSP/linear algebra libraries** [S]; HighTec partnership [S] |
| **PSoC Edge E84** | **Cortex-M55 (Helium) 320–400 MHz** (sources conflict) + M33 LP [S] | up to 5 MB system SRAM + 1 MB (M33) + 512 KB TCM; 512 KB RRAM; ext. octal flash [S] | **Ethos-U55 (128 MAC/cycle)** + **NNLite** on M33 [S] | **CAN FD** [S] (count [U]) | 10/100 MAC [S] | Consumer (−20…70 °C) / industrial; **not automotive** [S] | ~$10–12 [S] / **E84 AI Kit ~$91**, Eval Kit ~$373 [S] | ModusToolbox ML, **DEEPCRAFT Studio** (ex-Imagimob) [U], TFLM + Ethos-U Vela, ExecuTorch (Ethos-U) [U] |

### 2e. Renesas

| Part | Core / clock | SRAM / flash | AI accel | CAN | Ethernet | Auto / FuSa / HSM | Price | Toolchain |
|---|---|---|---|---|---|---|---|---|
| **RA8M1 / RA8D1** | **Cortex-M85 480 MHz, Helium** [V] | 1 MB SRAM / 2 MB flash [V] | Helium MVE only | **2× CAN FD** [V] | 10/100 MAC [V] | Industrial, not AEC [U]; TrustZone, RSIP-E51A [U] | ~$8–12 [U] / EK-RA8D1 ~$100 [U] | FSP, **RUHMI / e-AI** [U], TFLM + CMSIS-NN, Edge Impulse (EK-RA8D1 listed) [S] |
| **RA8P1** | **M85 1 GHz + M33 250 MHz** [V] | 2 MB SRAM (+1.6 MB? [S]); MRAM [U] | **Ethos-U55, 256 GOPS @500 MHz** [V] | CAN FD [U count] | **Ethernet switch (ESWM)** [V] | −40…105 °C option [S]; not AEC [U] | [U] / EK-RA8P1 ~£162 [S] | RUHMI (Vela-based) [U], TFLM, ExecuTorch Ethos-U |
| **RH850** (U2A/U2B/F1K) | G4MH / G3KH, up to 400 MHz multi-core [U] | up to 16+ MB flash [U] | None | Many RS-CANFD channels [S/U] | Yes on U2x [U] | **AEC-Q100, ASIL-D, ICU-S/ICU-M HSM (SHE/EVITA)** [V for P1L-C ICU-S] | NDA [U] | Plain C codegen / emlearn [U] |
| **R-Car X5H** (SoC, out of MCU scope) | up to 32× A720AE + 6× R52, 3 nm [S] | — | NPU + UCIe chiplets (>1000 TOPS) [S] | — | — | ASIL-B/D [S] | — | — |

### 2f. Arm-NPU MCUs, wireless and alternative accelerators

| Part | Core / clock | SRAM / NVM | AI accel | CAN | Ethernet | Auto | Price | Toolchain |
|---|---|---|---|---|---|---|---|---|
| **Alif Ensemble E3** | M55 HP 400 MHz + M55 HE 160 MHz [S] | up to ~13.5 MB SRAM, ~5.5 MB MRAM [U] | **2× Ethos-U55 (256 + 128 MAC), ~250 GOPS** [S] | CAN FD [S] | Yes [S] | No [U] | ~$8–15 [U] / DevKit ~$200+ [U] | TFLM + Vela, **ExecuTorch Ethos-U**, Edge Impulse [V/S] |
| **Alif Ensemble E7** | + 2× Cortex-A32 800 MHz [S] | as E3 | 2× Ethos-U55 [S] | CAN FD [S] | Yes [S] | No | DK-E7 [U] | Linux on A32 + same |
| **RP2040 / RP2350** | 2× M0+ 133 MHz / **2× M33 or Hazard3 RISC-V 150 MHz** [S] | 264 KB / **520 KB** SRAM; ext. flash [S] | None | **None in hardware.** `can2040` PIO software CAN 2.0B up to 1 Mbit/s [V] | None | No | ~$0.8–1.1 [U] / **Pico 2 $5** [S] | TFLM (pico-tflmicro), CMSIS-NN (M33), Edge Impulse, emlearn |
| **Nordic nRF54L15 / nRF54LM20B** | M33 128 MHz + RISC-V coprocessor [V] | L15: 1.5 MB RRAM / 256 KB [U]; **LM20B: 2 MB NVM / 512 KB RAM** [V] | **LM20B: Axon NPU (up to 15× vs CPU)** [V] | None | None | No (consumer); BLE **Channel Sounding** for relay-attack-resistant ranging [V] | ~$2–4 [U] / DK ~$40–60 [U] | Nordic Edge AI Lab, Neuton models, **Edge Impulse (nRF54LM20 DK)** [V] |
| **Ambiq Apollo4 / Apollo510** | Apollo510: **M55 250 MHz Helium** [S] | 3.75 MB SRAM/TCM, 4 MB NVM [S] | Helium only | None | None | No | ~$5–10 [U] / EVB ~$100+ [U] | neuralSPOT, TFLM, Edge Impulse [U] |
| **ADI MAX78000** | M4F 100 MHz + RISC-V 60 MHz [S] | 128 KB SRAM / 512 KB flash; **442 KB CNN weight memory** [S] | **CNN accelerator** (1/2/4/8-bit weights) [S] | None | None | No | **$8.5 (1 ku)–$12** [S] / FTHR ~$35 [U] | ADI ai8x-training / ai8x-synthesis (PyTorch → C) [U] |
| **ADI MAX78002** | M4F 120 MHz [S] | 384 KB / 2.5 MB; **2 M weights, 1.3 MB CNN data** [S] | CNN accel [S] | None | None | No | ~$37–43 (1 ku) [S] | as above |
| **Syntiant NDP120 / NDP250** | NDP250: Core 3 [S] | [U] | **NDP250 30 GOPS** [S] | None | None | No | [U] | Syntiant TDK / Edge Impulse [U]. Audio/sensor co-processor; needs a host MCU |
| **GreenWaves GAP9** | 10 RISC-V cores (1 FC + 9 cluster) + **NE16** [S] | 128 KB L1, 1.6 MB L2 [S] | ~50 GOPS @ 50 mW [S] | None | None | No | [U] | GAP SDK / NNTool [U]; hearables-focused |
| **Kendryte K210** (baseline) | 2× RV64 400 MHz [S] | 6 MB + 2 MB KPU SRAM [S] | **KPU ~0.25–0.5 TOPS** (vendor claims vary) [S] | None | None | No | Sipeed M1 module ~$6–11 [S] | nncase, MaixPy; ageing/legacy [U] |

---

## 3. TinyML toolchain support matrix

| Toolchain | ESP32 family | STM32 (F4/G4/H7/U5) | STM32N6 / Stellar | NXP S32K3 / RT / MCX | AURIX | PSoC Edge / Alif / RA8P1 (Ethos-U) | Notes |
|---|---|---|---|---|---|---|---|
| **LiteRT for Microcontrollers (ex-TFLM)** | ✔ esp-tflite-micro + ESP-NN [V] | ✔ + CMSIS-NN | ✔ (CPU fallback); NPU via ST Edge AI | ✔ (eIQ ships TFLM) | ◐ portable C++, no optimised kernels [U] | ✔ + Ethos-U delegate (Vela) | Renamed Sept 2024 [S] |
| **ESP-DL v3** (+ESP-PPQ) | ✔ S3, P4 (main); ONNX/PyTorch → .espdl, int8/int16/mixed [V] | – | – | – | – | – | Very active (2026 releases) [V] |
| **ST Edge AI Core / STM32Cube.AI / Developer Cloud** | – | ✔ | ✔ **Neural-ART + Stellar SR5/SR6 P3E** [V] | – | – | – | Also covers smart sensors (ISPU/MLC) [V] |
| **NXP eIQ** (Toolkit, Neutron, Auto ML) | – | – | – | ✔ RT/MCX (Neutron NPU); **eIQ Auto ML for S32K3/S32G** [V] | – | – | eIQ Auto is the automotive-qualified runtime [V] |
| **Edge Impulse** (Qualcomm since 2025) | ✔ ESP32, ESP32-S3 [S] | ✔ | ◐ N6 [U] | ✔ RT1170 [U] | – | ✔ Alif, RA8D1 [S] | Also nRF54L15/LM20 [V] |
| **CMSIS-NN** | – (ESP-NN instead) | ✔ | ✔ (M55 Helium) | ✔ (M7/M33) | – | ✔ | Arm-only |
| **ExecuTorch 1.x** | ◐ portable CPU [U] | ◐ Cortex-M backend [V] | ◐ (M55 CPU; not Neural-ART) [U] | ◐ Cortex-M [V] | – | ✔ **Ethos-U55/U65/U85 backend** [V] | Good if the training stack is PyTorch |
| **Apache TVM / microTVM** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **microTVM removed from TVM main; last in v0.18** [S]. Avoid for new work |
| **emlearn** (sklearn/Keras → C) | ✔ | ✔ | ✔ | ✔ | ✔ **(the practical choice for TriCore/RH850/PowerPC)** [U] | ✔ | Best for tree ensembles, kNN and small MLPs, which suit CAN IDS work well [U] |
| **ARC MetaWare NN SDK** | – | – | – | – | ✔ **TC4x PPU** [S] | – | Licensed toolkit (Synopsys/MIPS) [S] |
| **ADI ai8x / Syntiant TDK / GAP NNTool / nncase** | Each is vendor-specific to its accelerator | | | | | | Lock-in; weak fit for CAN data pipelines [U] |

---

## 4. Automotive considerations

- **AEC-Q100 and ISO 26262.** In this survey only the automotive families are AEC-Q100 qualified with ASIL-D support and an HSM: **NXP S32K3/S32K5/S32G, Infineon AURIX TC3xx/TC4x, ST SPC5/Stellar, and Renesas RH850**. The i.MX RT1170 has automotive-grade parts but no ASIL claim found. ESP32, STM32 (non-automotive lines), RA8, Alif, PSoC Edge, Nordic, Ambiq and MAX78000 are **prototyping/consumer/industrial only**.
- **HSM.** NXP **HSE-B** (S32K3), Infineon **HSM** (AURIX), ST **HSM gen2** (Stellar P3E, EVITA-full), Renesas **ICU-S/ICU-M** (RH850). The HSM matters for SecOC (AUTOSAR Secure Onboard Communication), so plan the IDS alongside it: the HSM authenticates frames, and the IDS detects anomalies in timing, sequence and payload semantics.
- **Interfaces.**
  - **CAN FD** is standard on all automotive MCUs and on STM32G4/H7/N6/U5, RA8, MCX N, RT1170, PSoC Edge and Alif.
  - **CAN XL** is on AURIX TC4x and Stellar P3E.
  - **10BASE-T1S** is native on TC4x and P3E. For prototyping, use the **Microchip LAN8650/8651 SPI MAC-PHY**, which has an ESP-IDF `lan865x` component and works with ESP32-S/C/H [V], or the **Arduino UNO SPE shield (LAN8651)** [S], or the **EVB-LAN8670-USB** USB adapter with a Linux driver [S].
  - **100BASE-T1** needs an external PHY or a media converter (e.g. NXP TJA1101/TJA1103 EVBs, Technica Engineering converters) [U].
- **Hardware timestamps matter for CAN IDS features** (inter-arrival time and jitter).
  - The MCP2517FD/2518FD have a **32-bit timestamp** [V].
  - FDCAN/FlexCAN/M_CAN have timestamp counters [U].
  - ESP32 TWAI timestamps are taken in software in the ISR/driver [U], so expect tens of µs of jitter, especially with Wi-Fi active [U].

---

## 5. CAN interfacing for prototyping

### 5a. Transceivers

| Part | CAN FD | Max data rate | Logic supply | Notes |
|---|---|---|---|---|
| **TI SN65HVD230** (/231/232) | **No** | 1 Mbit/s [V] | 3.3 V only [V] | The usual cheap "blue board" with ESP32. Classic CAN only |
| **NXP TJA1051T/3** (VIO variant) | **Yes** | 5 Mbit/s in the FD data phase [V] | VIO 3–5 V [V] | Good default for 3.3 V MCUs on CAN FD |
| **Microchip MCP2562FD** | **Yes** | 8 Mbit/s [S] | VIO 1.8–5.5 V [S] | Pairs naturally with MCP2518FD |
| Infineon TLE9251V | Yes [U] | 5 Mbit/s [U] | VIO [U] | On the AURIX TC375 lite kit [S] |

### 5b. SPI CAN controllers (adds CAN or CAN FD to any MCU)

| Part | Protocol | SPI clock | Notes |
|---|---|---|---|
| **MCP2515** | CAN 2.0B, 1 Mbit/s [S] | 10 MHz [U] | Cheap, ubiquitous; used on LilyGO T-2CAN as the second bus [S] |
| **MCP2517FD** | CAN FD, 1 Mbit/s arbitration, 8 Mbit/s data, ISO 11898-1:2015 [V] | 17 MHz [V] | 31 FIFOs, 32 filters, 32-bit timestamp [V] |
| **MCP2518FD** | as above [V] | **20 MHz** [V] | Preferred; Linux `mcp251xfd` driver, ESP32/Arduino `ACAN2517FD` library [U] |

**ESP32 + CAN FD options, from simplest to most work:**
1. **ESP32-C5 (or ESP32-S31) with native TWAI FD + TJA1051T/3 or MCP2562FD.** This is the newest route; check that your ESP-IDF version (≥ v5.5/v6.x) supports FD in the `esp_twai` driver [U].
2. **ESP32-S3 + MCP2518FD over SPI.** Proven, and keeps the S3 SIMD for inference. SPI throughput is enough for one bus at 2–5 Mbit/s data rate [U].
3. **ESP32 classic, S3 or P4 TWAI for classic-CAN buses only.** Most OBD-II diagnostic CAN in pre-2020 cars is classic 500 kbit/s. Several newer platforms (e.g. GM Global B) use CAN FD [U].

### 5c. Ready-made boards

| Board | MCU | CAN | Price | Notes |
|---|---|---|---|---|
| **LilyGO T-CAN485** | ESP32 | 1× TWAI (SN65HVD231) + RS485 | ~$12 [S] | Cheapest ESP32+CAN |
| **LilyGO T-2CAN** | ESP32-S3 (16 MB flash / 8 MB PSRAM) | **2 isolated buses**: TWAI + MCP2515 (classic only) [S] | ~$25–35 [U] | Good IDS gateway/MITM prototype (two-bus bridging) |
| **Macchina A0** | ESP32 | 1× CAN, OBD-II plug form factor [S] | ~$90 [S] | Plugs straight into the OBD port |
| **Macchina M2** | SAM3X (Arduino Due class) | 2× CAN, LIN, SWCAN [U] | ~$80–150 [U] | Older; no ML acceleration |
| **comma panda (CAN FD panda kit)** | **STM32H725** | CAN **and CAN FD** (3 buses [U]) [V] | **$450 kit; basic panda $99** [S] | Python lib; opendbc safety model [V]. Ideal for capturing real-vehicle logs |
| **CANable 2.0** | STM32G431 | 1× **CAN FD**, candleLight (gs_usb) → **native SocketCAN** [S] | ~$35 [S] | Recommended PC-side adapter |
| **Longan CANBed RP2040** | RP2040 | MCP2515 (classic) [S] | ~$20 [U] | — |
| **Longan CANBed Dual** | RP2040 | 2 independent buses, CAN 2.0 + **CAN FD** [S] (FD controller part: sources conflict [U]) | ~$25 [S] | — |
| **FRDM-MCXN947** | MCX N947 (NPU) | CAN-FD transceiver on board [S] | ~$23 [S] | Cheapest NPU + CAN FD dev board |
| **NUCLEO-N657X0-Q** | STM32N657 (NPU) | CAN FD header + Ethernet RJ45 [S] | [U ~$50] | High-end NPU + CAN FD |
| **KIT_A2G_TC375_LITE** | AURIX TC375 | TLE9251V CAN + 10/100 Ethernet [S] | ~€92–100 [S] | Cheapest real automotive MCU kit |

### 5d. Recommended bench setup

```
 [Linux PC: SocketCAN, can-utils, python-can, cantools]
        │ USB
   [CANable 2.0 (gs_usb)]──┐
                           │  twisted pair, 120 Ω at each end
 [OBD-II breakout box]─────┼──────────────┬───────────────┐
 (16-pin female, banana    │              │               │
  jacks, CAN-H pin 6,      │       [DUT: ESP32-S3 +   [DUT 2: S32K344 EVB /
  CAN-L pin 14, 12 V       │        SN65HVD230 or      NUCLEO-N657 /
  pin 16, GND 4/5)         │        MCP2518FD]         TC375 lite]
                           │
           [Optional: ECU simulator / real ECU on bench PSU 12 V,
            or 2nd CANable replaying traffic]
```

1. **Pure software first:** `sudo modprobe vcan && sudo ip link add dev vcan0 type vcan && sudo ip link set vcan0 up`. Run **ICSim** (virtual instrument cluster) [U] or `canplayer` on vcan0 to develop feature extraction without hardware.
2. **Physical bus:**
   - Classic CAN: `sudo ip link set can0 type can bitrate 500000 && sudo ip link set can0 up`.
   - CAN FD: `sudo ip link set can0 type can bitrate 500000 dbitrate 2000000 fd on`.
3. **Capture and replay:** `candump -l can0` writes a log; `canplayer -I candump-*.log can0=vcan0` replays it, and the `canX=canY` mapping redirects the interface. `cansniffer`, `canbusload` and `isotpdump` help with inspection.
4. **Attack synthesis for labelled data:**
   - `cangen can0 -I 000 -g 0.1` floods ID 0x000 (DoS).
   - `cangen can0 -I r -L r -g 1` generates random IDs and lengths (fuzzing).
   - For spoofing and replay, inject a known ID with altered payloads using python-can scripts.
   - Label attacks by timestamp window.
5. **Public datasets for pre-training before bench data:** HCRL Car-Hacking (DoS/fuzzy/spoofing), ORNL **ROAD** (stealthier masquerade attacks), can-train-and-test [U: check licences]. Use DBCs from **opendbc** [V: referenced by panda] with `cantools` for signal decoding.
6. **Hardware:**
   - **OBD-II breakout box** with banana jacks and LED status (~$20–40) [U].
   - **CAN ECU simulator**, e.g. OBD Solutions ECUsim 2000 (~$200–300) or Freematics OBD-II emulator (~$100–200) [U]. A cheaper option is a second CANable replaying a real log.
   - 12 V bench PSU with a current limit.
   - Logic analyser or scope with CAN decode (e.g. Saleae).
   - **Never inject into a moving vehicle.** Use a bench harness or junkyard ECUs.
7. **RF/GNSS anomaly side:**
   - A GNSS receiver that exposes raw and jamming/spoofing indicators, e.g. u-blox M9/F9 via UBX-MON-RF/NAV-SIG for jamming indicator, C/N0 and AGC [U].
   - An SDR (RTL-SDR, HackRF) **only in a shielded enclosure or with a GNSS simulator**, because GNSS transmission is illegal over the air.
   - Use recorded datasets such as TEXBAT [U].
8. **BLE keyless:** nRF54L15 DK for Channel Sounding ranging to detect relay attacks [V for CS support].

---

## 6. Recommendations

### (a) Primary prototyping target: **ESP32-S3** (with ESP32-C5 as the CAN FD companion)

**Pick:**
- **ESP32-S3-DevKitC-1 (N16R8)** or **LilyGO T-2CAN** (S3, two isolated CAN buses).
- **SN65HVD230** for classic CAN, or **MCP2518FD + MCP2562FD** when the bus is CAN FD.
- Optionally an **ESP32-C5-DevKitC-1 + TJA1051T/3** to evaluate native TWAI-FD.

**Why:**
- **Best price/performance and tooling for fast iteration.** Boards cost about $12–35. The S3 has SIMD-optimised **ESP-NN** kernels inside **esp-tflite-micro**, plus **ESP-DL v3** (ONNX/PyTorch → int8/int16) [V].
- ESP-NN cut person-detect latency on the S3 from 2300 ms to 54 ms [V]. That is orders of magnitude more compute than a CAN-IDS MLP/1D-CNN/GRU on frame features needs.
- **Wi-Fi/BLE** allows telemetry, model OTA updates and BLE-keyless experiments on the same chip.
- **Two buses (T-2CAN)** let you build an inline gateway/IDS (bridge plus filter), which is the realistic deployment topology.
- **Caveats:**
  - The S3 TWAI is **classic only** [V], so use the MCP2518FD for FD buses.
  - It has no AEC-Q100, FuSa or HSM, and software timestamps are jittery, so capture timing features with care (or use the MCP2518FD's hardware timestamp).
  - Watch the **ESP32-S31**: SIMD, 2× TWAI-FD and Gigabit Ethernet in one chip [V]. Once dev boards mature, it could replace the S3 + MCP2518FD combination.

### (b) "Production-like" automotive target: **NXP S32K344** (S32K3X4EVB-T172)

**Why:**
- **AEC-Q100 Grade 1, ASIL-D lockstep Cortex-M7, HSE-B secure engine, 6× CAN FD, Ethernet TSN** [S/V]. This is the class of MCU found in real body, zonal and gateway ECUs.
- **NXP eIQ Auto ML toolkit** officially targets S32K3 with an automotive-qualified inference runtime [V]. Being an Arm M7, it also runs TFLM + CMSIS-NN and emlearn unchanged, so models move from the ESP32 workflow with little rework.
- Real-Time Drivers/AUTOSAR MCAL support lets you demonstrate IDS integration next to SecOC/HSE.
- **Budget alternative:** **Infineon AURIX TC375 lite kit (~€95)**. It has ASIL-D, HSM, CAN FD and Ethernet on an Arduino form factor, but TriCore has no CMSIS-NN, so use emlearn or plain-C model export.
- **Upgrade paths:** **AURIX TC4x** (PPU vector DSP via the MetaWare NN SDK) and **NXP S32K5** (Neutron NPU, once available). For a **central/vehicle-wide IDS**, look at the **S32G3** gateway (20× CAN FD, Linux on A53).

### (c) High-end TinyML target with NPU: **STM32N6 (NUCLEO-N657X0-Q / STM32N6570-DK)**

**Why:**
- **Neural-ART NPU (600 GOPS) + Cortex-M55 800 MHz Helium + 4.2 MB on-chip RAM** [V] together with **3× FDCAN and GbE/TSN** [S]. Most NPU MCUs lack automotive-style I/O; this one has both, and the Nucleo exposes a CAN FD header and RJ45 [S].
- This headroom fits heavier models: GRU/transformer-lite over CAN sequences, multi-bus fusion, RF/GNSS spectrogram CNNs.
- **Its strongest argument is the toolchain continuity to an automotive NPU part.** The same **ST Edge AI Core** targets **Stellar SR6 P3E** [V]: automotive, ASIL-D, HSM gen2, Neural-ART 80+ GOPS, 8× CAN FD + 2× CAN XL, 10BASE-T1S, production planned Q4 2026 [V].
- **Alternatives:**
  - **NXP MCX N947** (FRDM ~$23, Neutron NPU + CAN FD, eIQ) is the cheapest NPU + CAN FD option.
  - **Alif Ensemble E3/E7** or **Infineon PSoC Edge E84** (Ethos-U55) are the choice if you want the **ExecuTorch/Vela Ethos-U** ecosystem.
  - **Renesas RA8P1** (1 GHz M85 + Ethos-U55 256 GOPS).
  - None of these alternatives is automotive-qualified.

### Not recommended as the main path
- **RP2040/RP2350**: no hardware CAN; can2040 is classic CAN only and uses PIO [V].
- **MAX78000, Syntiant, GAP9, K210**: no CAN, vendor-locked CNN toolchains, aimed at audio/vision. They are only interesting as an RF-spectrogram side-channel accelerator, and K210 only as a cost baseline.
- **Anything built on microTVM**: deprecated [S].

---

## 7. Sources (primary/secondary, as seen during research)

- ESP-IDF `soc_caps.h` (master) for esp32, s2, s3, c3, c5, c6, c61, h2, h4, p4 and s31 — https://github.com/espressif/esp-idf/tree/master/components/soc (read directly) [V]
- ESP-IDF TWAI docs (C5 FD-capable; classic TWAI treats FD frames as errors) — https://docs.espressif.com/projects/esp-idf/en/latest/esp32c5/api-reference/peripherals/twai.html ; https://docs.espressif.com/projects/esp-idf/en/stable/api-reference/peripherals/twai.html
- ESP32-C5 datasheet — https://documentation.espressif.com/esp32-c5_datasheet_en.pdf
- ESP-NN README (S3/P4/S31 optimisations, benchmarks) — https://github.com/espressif/esp-nn ; ESP-DL README — https://github.com/espressif/esp-dl ; esp-tflite-micro — https://github.com/espressif/esp-tflite-micro
- ESP32-P4 v3.x upgrade — https://www.espressif.com/zh-hans/news/ESP32_P4_v3.x_Upgrade ; P4 Function EV board — https://cnx-software.com/2024/08/07/esp32-p4-function-ev-board-development-board-launched-for-55-with-7-inch-display-and-camera-module/
- ESP32-S31 — https://www.espressif.com/en/news/ESP32_S31_Mass_Production ; https://hackaday.com/tag/esp32-s31
- STM32N6 — https://blog.st.com/stm32n6/ ; https://st.com/resource/en/datasheet/stm32n647x0.pdf ; NUCLEO-N657X0-Q — https://st.com/resource/en/data_brief/nucleo-n657x0-q.pdf
- Stellar P3E — https://blog.st.com/stellar-p3e/ ; https://www.st.com/resource/en/data_brief/sr6p3ec4.pdf
- ST Edge AI Core — https://www.st.com/en/development-tools/stedgeai-core.html ; https://stm32ai-cs.st.com/assets/embedded-docs/release_note.html
- NXP eIQ Auto ML toolkit — https://www.nxp.com/design/software/eiq-auto-ml-sw-environment/eiq-auto-machine-learning-ml-toolkit:eIQ-AUTO-ML-TOOLKIT
- S32K344 — https://www.digikey.com/en/products/detail/nxp-usa-inc/S32K344EHT1MPBST/18711609 ; https://www.farnell.com/datasheets/3812085.pdf
- S32K5 — https://www.nasdaq.com/press-release/new-s32k5-microcontroller-family-advances-zonal-sdv-architectures-and-extends-nxp
- S32G3 — https://www.mouser.co.uk/nxp-s32g3-vehicle-network-processors
- i.MX RT1170 — https://cn.nxp.com/docs/en/fact-sheet/i.MX-RT1170-FS.pdf
- MCX N — https://www.nxp.com/docs/en/fact-sheet/MCXNFS.pdf ; FRDM-MCXN947 pricing — element14/Future Electronics listings
- AURIX TC4x — https://infineon.com/cms/en/product/promopages/aurixnextgeneration ; https://emmtrix.com/wiki/Infineon_AURIX_TC4x ; MetaWare for AURIX — https://mips.com/processor-solutions/sw-metaware-aurix/
- AURIX TC375 lite kit — https://infineon.com/cms/en/product/evaluation-boards/kit_a2g_tc375_lite ; TC4D7 lite kit — https://www.mouser.in/infineon-kit-a3g-tc4d7-lite-kit
- PSoC Edge E8x datasheet — https://www.infineon.com/assets/row/public/documents/30/49/infineon-psoc-edge-e8x-consumer-datasheet-datasheet-en.pdf
- Renesas RA8P1 — https://www.renesas.com/en/about/newsroom/renesas-sets-new-mcu-performance-bar-1-ghz-ra8p1-devices-ai-acceleration ; RA8M1 — https://www.renesas.com/en/document/dst/ra8m1-group-datasheet ; R-Car X5H — https://www.eenewseurope.com/en/first-3nm-multi-domain-controller-has-38-cores-ai-chiplets/
- Alif Ensemble — https://www.cnx-software.com/?p=107517
- RP2350/Pico 2 — https://www.guru3d.com/story/raspberry-pi-pico-2-release-specifications-and-pricing-just ; can2040 — https://github.com/KevinOConnor/can2040
- Nordic nRF54LM20B — https://www.nordicsemi.com/Products/nRF54LM20B ; Edge Impulse nRF54LM20 DK — https://docs.edgeimpulse.com/hardware/boards/nordic-semi-nrf54LM20-dk
- Ambiq Apollo510 — https://contentportal.ambiq.com/documents/20123/2877485/Apollo510-SoC-Datasheet.pdf
- MAX78000/78002 — https://www.analog.com/en/products/max78002 ; https://www.cnx-software.com/2020/10/08/max78000-risc-v-cortex-m4f-mcu-enables-iot-artificial-intelligence-in-battery-powered-devices/
- GAP9 — https://www.eenewseurope.com/en/gap9-why-9-cores-are-better-than-8/ ; Syntiant NDP250 — https://www.electronicsworld.co.uk/syntiant-unveils-ndp250-neural-decision-processor-with-next-gen-core-3-architecture/36386/ ; K210 — https://hackaday.com/2018/10/08/new-part-day-the-risc-v-chip-with-built-in-neural-networks/
- LiteRT rename — https://developers.googleblog.com/en/tensorflow-lite-is-now-litert/ ; microTVM status — https://discuss.tvm.apache.org/t/questions-regarding-the-future-development-of-microtvm/17926 ; ExecuTorch Ethos-U — https://docs.pytorch.org/executorch/stable/backends-section.html
- Edge Impulse acquisition — https://www.edgeir.com/qualcomm-acquires-edge-impulse-accelerating-ai-and-iot-expansion-at-the-edge-20250317
- MCP2517FD vs MCP2518FD — https://microchip.com/en-us/product-comparison.mcp2517fd.mcp2518fd ; TJA1051 — https://nxp.com/products/interfaces/can-transceivers/can-with-flexible-data-rate/high-speed-can-transceiver:TJA1051 ; SN65HVD230 — https://www.ti.com/product/SN65HVD230 ; MCP2562FD — https://uk.rs-online.com/web/p/can-interface-ics/1771916
- LilyGO T-CAN485 — https://lilygo.cc/en-ca/products/t-can485 ; T-2CAN — https://github.com/Xinyuan-LilyGO/T-2Can
- comma panda — https://github.com/commaai/panda ; https://www.comma.ai/shop/can-fd-panda-kit
- CANable — https://canable.io/ ; CANBed — https://core-electronics.com.au/canbed-dual-rp2040-chip-based-arduino-can-bus-dev-board-with-2-independent-can-bus-interfacescan20-can-fd.html
- Macchina A0 — https://www.sparkfun.com/macchina-a0-obd-ii-development-module.html
- LAN865x ESP-IDF component — https://components.espressif.com/components/espressif/lan865x ; EVB-LAN8670-USB — https://www.mouser.in/new/microchip/microchip-evb-lan8670-usb-d-eval-board/
