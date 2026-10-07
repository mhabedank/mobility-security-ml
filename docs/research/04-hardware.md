# 04 – Hardware: Prozessoren, Boards, Laboraufbau

Die vollständigen Vergleichstabellen für rund 40 Bausteine, die Toolchain-Matrix und alle Quellen stehen in
[notes/hardware.md](notes/hardware.md). Preise sind meist **ungeprüft** `[U]`.

## Empfehlung

| Rolle | Wahl | Begründung |
|---|---|---|
| **(a) Prototyping, Hauptziel** | **ESP32-S3** (DevKitC-1 N16R8 oder **LilyGO T-2CAN** mit 2 isolierten CAN-Bussen) | Board 12–35 $, 512 KB SRAM plus PSRAM, 128-Bit-SIMD; **ESP-NN** bringt in Espressifs Benchmark ein Person-Detection-Modell von 2300 ms auf 54 ms; **ESP-DL v3**; WLAN/BLE für Telemetrie, OTA und BLE-Experimente |
| **(b) Produktionsnah (Automotive)** | **NXP S32K344** (S32K3X4EVB-T172) | AEC-Q100, **ASIL-D-Lockstep-M7**, HSE-B, **6× CAN FD**, Ethernet TSN; **eIQ Auto** unterstützt S32K3 offiziell; TFLM, CMSIS-NN und emlearn laufen ohne Änderungen |
| **(b′) Budget-Alternative** | **Infineon AURIX TC375 Lite Kit** (~95 €) | ASIL-D, HSM, CAN FD; TriCore ist aber nicht Arm, also kein CMSIS-NN, Export über emlearn bzw. reines C |
| **(c) High-End mit NPU** | **STM32N6** (NUCLEO-N657X0-Q) | Neural-ART-NPU mit 600 GOPS, M55 mit 800 MHz, 4,2 MB RAM, **3× FDCAN**, GbE/TSN; **dieselbe Toolchain (ST Edge AI Core)** zielt auf den automotive-tauglichen **Stellar P3E** (ASIL-D, NPU, 8× CAN FD + 2× CAN XL, Produktion geplant für Q4 2026) |
| **(c′) Günstige NPU-Alternative** | **NXP FRDM-MCXN947** (~23 $) | Neutron-NPU plus CAN-FD-Transceiver auf dem Board |

## Wichtige Erkenntnisse

- **ESP32 und CAN FD:** Laut ESP-IDF `soc_caps.h` [V] gilt:

  | Chips | TWAI-Controller |
  |---|---|
  | ESP32, S2, S3, C3, H2 | 1× **nur CAN 2.0** |
  | C6 | 2× **nur CAN 2.0** |
  | P4 | 3× **nur CAN 2.0** |
  | **C5** | 2× **mit CAN FD** |
  | **H4** | 1× **mit CAN FD** |
  | **S31** | 2× **mit CAN FD** |

  Der neue **ESP32-S31** kombiniert SIMD, 2× TWAI-FD und Gigabit-Ethernet. Er ist ein Kandidat für die nächste Prototyping-Generation.
- **Achtung:** Klassische TWAI-Controller werten CAN-FD-Frames als Fehler. Einen ESP32-S3 deshalb **nie direkt an einen
  CAN-FD-Bus** hängen. Für FD-Busse den S3 mit **MCP2518FD + MCP2562FD** über SPI kombinieren oder einen ESP32-C5 nehmen.
- **Zeitstempel:** Für Timing- und Clock-Skew-Features sind Hardware-Zeitstempel wichtig. Der MCP2518FD hat einen 32-Bit-Zeitstempel,
  FDCAN und FlexCAN haben Timestamp-Counter. Der ESP32-TWAI-Treiber stempelt dagegen in Software, mit mehr Jitter, vor allem
  bei aktivem WLAN.
- **Automotive-Qualifikation:** Nur NXP S32K3/S32K5/S32G, Infineon AURIX, ST SPC5/Stellar und Renesas RH850 sind
  AEC-Q100-qualifiziert und haben ASIL-D sowie ein HSM. ESP32, STM32 (Standard), RA8, Alif, PSoC Edge, Nordic und MAX78000
  eignen sich nur für Prototypen.
- **Upgrade-Pfade:** AURIX TC4x mit PPU-Vektor-DSP und NN-SDK; NXP S32K5 mit Neutron-NPU, bisher nur Muster für
  Lead-Kunden; S32G3 als zentrales Gateway-IDS mit Linux und 20× CAN FD.

## Nicht empfohlen als Hauptpfad

- **RP2040/RP2350:** kein Hardware-CAN; `can2040` emuliert CAN 2.0 per PIO.
- **MAX78000, Syntiant, GAP9, K210:** kein CAN, herstellerspezifische CNN-Toolchains, ausgelegt auf Audio und Vision.

## CAN-Anbindung für Prototypen

| Komponente | CAN FD? | Einsatz |
|---|---|---|
| SN65HVD230 (TI) | nein | billiger 3,3-V-Transceiver für klassisches CAN |
| TJA1051T/3 (NXP) | ja, 5 Mbit/s | Standard-FD-Transceiver für 3,3-V-MCUs |
| MCP2562FD (Microchip) | ja, 8 Mbit/s | passt zum MCP2518FD |
| MCP2515 (SPI) | nein | CAN 2.0B, sehr verbreitet |
| **MCP2518FD (SPI)** | ja | bevorzugter CAN-FD-Controller für jede MCU, mit Hardware-Zeitstempel |

| Board | MCU | CAN | ca. Preis |
|---|---|---|---|
| LilyGO T-CAN485 | ESP32 | 1× TWAI | ~12 $ |
| **LilyGO T-2CAN** | ESP32-S3 | 2× isoliert (TWAI + MCP2515) | ~25–35 $ |
| Macchina A0 | ESP32 | 1×, im OBD-Stecker-Format | ~90 $ |
| **CANable 2.0** | STM32G431 | 1× CAN FD, native SocketCAN | ~35 $ |
| comma panda (CAN-FD-Kit) | STM32H725 | CAN + CAN FD | 99–450 $ |
| FRDM-MCXN947 | MCX N947 (NPU) | CAN-FD-Transceiver | ~23 $ |
| NUCLEO-N657X0-Q | STM32N6 (NPU) | CAN-FD-Header | ~50 $ [U] |
| KIT_A2G_TC375_LITE | AURIX TC375 | CAN + Ethernet | ~95 € |

## Laboraufbau

```
 [Linux-PC: SocketCAN, can-utils, python-can, cantools]
        │ USB
   [CANable 2.0]───────┐
                       │  Twisted Pair, 120 Ω an beiden Enden
 [OBD-II-Breakout]─────┼─────────────┬──────────────────┐
                       │             │                  │
                       │      [DUT 1: ESP32-S3 +   [DUT 2: S32K344-EVB /
                       │       SN65HVD230 oder      NUCLEO-N657 / TC375]
                       │       MCP2518FD]
         [optional: ECU-Simulator oder 2. CANable, der Logs abspielt]
```

1. **Zuerst nur Software:** `vcan0` aufsetzen, Logs aus öffentlichen Datensätzen mit `canplayer` abspielen und
   die Feature-Extraktion ohne Hardware entwickeln.
2. **Physischer Bus:** `ip link set can0 type can bitrate 500000` (bei CAN FD zusätzlich `dbitrate 2000000 fd on`).
3. **Mitschnitt und Replay:** `candump -l`, `canplayer`, `cansniffer`, `canbusload`.
4. **Angriffe für gelabelte Daten:** `cangen -I 000` (DoS), `cangen -I r -L r` (Fuzzing); Spoofing und Replay mit python-can-Skripten;
   Labels über Zeitfenster.
5. **Echte Fahrzeuglogs** (nur passiv mitschneiden) mit comma panda oder CANable. **Nie in ein fahrendes Fahrzeug
   injizieren.** Angriffe nur auf dem Labortisch oder mit Steuergeräten vom Schrottplatz.
6. **GNSS:** u-blox M9/F9, die Jamming-Indikator, C/N0 und AGC über UBX liefern. Ein SDR **nur in geschirmter Umgebung oder mit
   GNSS-Simulator** betreiben, denn das Aussenden von GNSS-Signalen ist illegal.
7. **BLE/Keyless:** nRF54L15 DK (BLE Channel Sounding) bzw. DW3000-UWB-Module.

## Einkaufsliste für den Start (Vorschlag)

| Teil | Zweck | ca. Preis |
|---|---|---|
| 2× ESP32-S3-DevKitC-1 N16R8 **oder** 1× LilyGO T-2CAN | DUT | 25–35 $ |
| 2× SN65HVD230-Modul | CAN-Transceiver | < 10 $ |
| CANable 2.0 | PC-Schnittstelle, Replay | ~35 $ |
| OBD-II-Breakout-Box, 120-Ω-Widerstände, 12-V-Labornetzteil | Bus | 50–100 $ |
| *später:* MCP2518FD-Modul, NUCLEO-N657X0-Q, S32K344-EVB, Joulescope oder Nordic PPK2 | CAN FD, NPU, Automotive, Energiemessung | – |
