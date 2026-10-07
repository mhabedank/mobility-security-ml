# mobility-security-ml – HIL-Testbench für TinyML auf Mikrocontrollern

Automatisierte **Hardware-in-the-Loop (HIL) Testbench**, die dieselben TinyML-Modelle auf
vielen gängigen SoCs baut, flasht, ausführt und prüft – vom **ESP8266 (ESP8266MOD)** über
**ESP32 / ESP32-S3 / ESP32-C3** bis **RP2040 / RP2350, STM32 und nRF52840**.

Für jedes angeschlossene Board liefert ein Lauf:

* **Korrektheit**: Jede Inferenz auf dem Chip wird **bit-exakt** mit einer Python-Referenz
  verglichen (Zufalls- und Grenzwert-Eingaben, Golden Vectors, Evaluationsdatensätze).
  Für importierte Modelle ist die Referenz zusätzlich bit-exakt zum TFLite-Interpreter.
* **Performance**: Latenz (min/avg/max), CPU-Zyklen pro MAC, Latenzbudgets, Regressionen
  gegenüber einer Baseline.
* **Speicher**: RAM-/Flash-Verbrauch der Firmware, freier Heap, Heap-Lecks.
* **Robustheit**: Soft- und Hardware-Reset, Watchdog- oder Exception-Neustarts im Dauerlauf
  (inklusive Crash-Log), automatische Wiederherstellung (Reset → Power-Cycle → Neu-Flashen).

Ergebnisse landen als `summary.md` / `summary.json` / JUnit-XML in `results/<zeitstempel>/`
und in GitHub Actions direkt in der Job-Zusammenfassung.

```
                ┌───────────────────────── HIL-Host (PC / Raspberry Pi / CI-Runner) ──────────────────────────┐
 hil/boards.yaml│  hilbench run ──► build (PlatformIO / make) ──► flash (esptool / PIO / UF2 / Befehl)        │
 hil/targets.yaml  pytest + Plugin: 1 Testlauf pro Board, parallel (xdist), Board-Locks, Recovery             │
                │        │ USB-Serial  "#12 INFER kws_dscnn <hex>"  ◄──►  "@{"id":12,"out":"…","us":…}"       │
                └────────┼──────────────────────────────────────────────────────────────────────────────────┘
          ┌──────────────┼──────────────┬───────────────┬───────────────┬───────────────┐
      ESP8266MOD      ESP32(-S3/-C3)   RP2040/RP2350   STM32 Nucleo    nRF52840      Simulator (PC)
          └── gleiche Firmware: benchapp (Protokoll) + microinfer (int8-Engine) + modelzoo ──┘
```

## Schnellstart ohne Hardware (Simulator)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[hw,dev]"          # hw = esptool, platformio, pytest-xdist
hilbench run -b sim                 # baut die Firmware für den PC und führt alle HIL-Tests aus
```

Das Board `sim` ist die echte Bench-Firmware, kompiliert für den PC. Damit lassen sich Tests
entwickeln und in CI ausführen. Mit `sim-noisy` und Umgebungsvariablen lassen sich
Bootloader-Rauschen, Watchdog-Crashes und Hänger simulieren.

### Virtuelle ESP32-Boards (QEMU)

Die echte ESP32-, ESP32-S3- und ESP32-C3-Firmware läuft auch im
[Espressif-QEMU](https://github.com/espressif/qemu/releases). `hil/qemu-boards.yaml` bindet die
Emulatoren als normale Boards ein: Der Flasher startet QEMU, die UART liegt auf
`socket://127.0.0.1:555x`. CI führt so die HIL-Suite auf allen drei Chips aus.

```bash
hilbench --boards hil/qemu-boards.yaml run -b esp32-qemu --quick
```

## Schnellstart mit dem ESP8266MOD

1. Board per USB anschließen (NodeMCU / Wemos D1 mini mit CH340 oder CP2102).
   Bei einem nackten ESP-12-Modul siehe [docs/hardware.md](docs/hardware.md#esp8266mod--esp-12ef).
2. Erkennen lassen:
   ```bash
   hilbench discover --probe
   ```
   Das Kommando zeigt Port, USB-Seriennummer und physischen USB-Pfad, fragt per esptool den
   Chip ab und schlägt einen Eintrag für `hil/boards.yaml` vor.
3. Den Eintrag `esp8266-1` in `hil/boards.yaml` anpassen (`match:` mit Seriennummer oder
   `location`), dann:
   ```bash
   hilbench doctor                  # prüft Tools, Rechte und welche Boards verbunden sind
   hilbench run -b esp8266-1        # bauen, flashen, testen
   ```
4. Ergebnis ansehen: `results/<zeitstempel>/summary.md`, serielles Log in
   `results/<zeitstempel>/logs/esp8266-1.log`.

## Weitere Boards integrieren (ESP32, Pico, Nucleo, …)

Jedes neue Board ist **ein Eintrag in `hil/boards.yaml`**:

```yaml
boards:
  - id: esp32-1
    target: esp32                     # Typ aus hil/targets.yaml
    match: {serial_number: "0001"}    # oder {location: "1-1.3"} oder port: /dev/serial/by-id/...
    power: {type: uhubctl, hub: "1-1", port: 2}   # optional: Strom per USB-Hub schalten
```

Danach testet `hilbench run --parallel` alle verbundenen Boards gleichzeitig, ein Worker pro
Board. Boards, die gerade nicht angeschlossen sind, werden übersprungen
(`--require-all` macht daraus einen Fehler, z. B. für den nächtlichen CI-Lauf).

| Target | SoC / Board | Flash-Methode | Reset |
|---|---|---|---|
| `esp8266`, `esp8266_160mhz` | ESP8266 / ESP8266MOD (ESP-12E/F) | esptool | DTR/RTS |
| `esp32` | ESP32 DevKit | esptool | DTR/RTS |
| `esp32s3`, `esp32s3_usb` | ESP32-S3 (UART- bzw. nativer USB-Port) | esptool | DTR/RTS bzw. USB-JTAG |
| `esp32c3`, `esp32c3_usb` | ESP32-C3 (DevKitM bzw. SuperMini) | esptool | DTR/RTS bzw. USB-JTAG |
| `rp2040`, `rp2350` | Raspberry Pi Pico / Pico 2 | PlatformIO oder UF2 | Soft-Reset |
| `stm32f446` | NUCLEO-F446RE | PlatformIO (ST-LINK) oder `st-flash`/`pyocd` | Soft-Reset |
| `nrf52840` | Arduino Nano 33 BLE (Sense) | PlatformIO (bossac) | Soft-Reset |
| `native` | Simulator auf dem Host | – | Prozess-Neustart |

Ein **neuer Chip-Typ** braucht drei Dinge (Details: [docs/extending.md](docs/extending.md)):
eine PlatformIO-Umgebung in `firmware/platformio.ini`, einen Eintrag in `hil/targets.yaml` und
höchstens ein paar Zeilen in `firmware/src/hal_arduino.cpp`. Ohne eigene Zeilen greift der
generische Fallback, dann misst das Board nur Zeiten und keine Zyklen.

## Eigene TinyML-Modelle

```bash
# Keras -> TFLite (full integer int8), dann:
pip install tflite
hilbench import-tflite mein_modell.tflite --name mein_modell [--verify]
hilbench run --parallel             # landet automatisch in der Firmware aller Boards
```

Unterstützt werden sequentielle Graphen mit Conv2D, DepthwiseConv2D, Dense,
Max-/AveragePooling, Flatten/Reshape und ReLU/ReLU6. QUANTIZE/DEQUANTIZE/Softmax an den Rändern
werden entfernt. `--verify` vergleicht mit dem TFLite-Referenz-Interpreter (benötigt
TensorFlow). Modelle, die auf ein kleines Target nicht passen, können per
`-D MI_EXCLUDE_<NAME>` in `platformio.ini` und `excluded_models` in `targets.yaml`
ausgeschlossen werden.

Mitgelieferte Referenzmodelle (`models/zoo`, Neubau mit `hilbench zoo`):

| Modell | Aufgabe | MACs | Parameter | Arena |
|---|---|---:|---:|---:|
| `can_ids_mlp` | CAN-Bus-Intrusion-Detection (DoS, Fuzzing, Spoofing), trainiert | 1,6 k | 2,0 KB | 64 B |
| `sensor_ae` | Anomalieerkennung Raddrehzahlsensor (Autoencoder), trainiert | 10 k | 12 KB | 128 B |
| `imu_gnss_cnn1d` | GNSS-Spoofing-Detektor, 1D-CNN über IMU+GNSS (Benchmark-Gewichte) | 162 k | 6,9 KB | 2 KB |
| `kws_dscnn` | Keyword Spotting DS-CNN à la MLPerf Tiny (Benchmark-Gewichte) | 488 k | 5,8 KB | 7,8 KB |

## Kommandos

| Kommando | Zweck |
|---|---|
| `hilbench discover [--probe]` | USB-Geräte finden, Target raten, Inventar-Einträge vorschlagen |
| `hilbench doctor` | Host prüfen: Tools, Rechte, verbundene Boards, gebaute Firmware |
| `hilbench list` / `targets` | Inventar mit Verbindungsstatus / bekannte Targets |
| `hilbench build [-t T] [--all]` | Firmware bauen (`build/fw/<target>/` inkl. Manifest) |
| `hilbench flash -b B` / `info -b B` | Board flashen / INFO + Modelle anzeigen |
| `hilbench console -b B` | Interaktive Protokollkonsole (`PING`, `BENCH kws_dscnn 10`, …) |
| `hilbench reset -b B [--method M]`, `power -b B on/off/cycle` | Reset / Stromversorgung |
| `hilbench run [-b B] [-t T] [--tag X] [--parallel] [--quick] [--slow] [--baseline S] [-- pytest-Args]` | Kompletter HIL-Lauf |
| `hilbench report RUN [--baseline S]` | Bericht neu erzeugen / Regressionen prüfen |
| `hilbench import-tflite M.tflite`, `hilbench zoo` | Modelle importieren / Zoo neu bauen |

`pytest tests/hil --hil-board esp32-1 -k inference -n 4 --dist loadgroup` funktioniert genauso,
das Plugin wird über `conftest.py` geladen.

## Testsuiten (`tests/hil`)

| Datei | Prüft |
|---|---|
| `test_link.py` | PING/INFO, Identität (Target, Version), ECHO-Integrität, Fehlerbehandlung, Round-Trip-Zeit |
| `test_models.py` | Modellkatalog = Host-Modelle (CRC), Gewichte im Flash intakt, Golden Vectors |
| `test_inference.py` | Zufalls- und Grenzwert-Eingaben bit-exakt, Genauigkeit auf Evaluationssets |
| `test_performance.py` | Benchmarks (Latenz, Zyklen/MAC, Stabilität), Budgets, Baseline, Heap-Lecks |
| `test_robustness.py` | Soft-/Hardware-Reset + Wiederanlauf, Dauerlauf ohne unerwarteten Neustart (`--slow`) |

Beim Hochfahren prüft die Bench jedes Board: Läuft die gerade gebaute Firmware (Build-ID)?
Passt der gemeldete Chip zum Target? So fällt ein vertauschtes Kabel sofort auf.

## CI

* `.github/workflows/ci.yml`: Unit-Tests, die komplette HIL-Suite gegen simulierte Boards, die
  HIL-Suite auf ESP32/ESP32-S3/ESP32-C3 im QEMU und Firmware-Builds für alle 11 Targets mit
  RAM-/Flash-Übersicht.
* `.github/workflows/hil.yml`: läuft nächtlich oder manuell auf einem **self-hosted Runner**,
  an dem die echten Boards hängen. Einrichtung: [docs/ci.md](docs/ci.md).

## Aufbau des Repos

```
firmware/            Bench-Firmware (PlatformIO) + Host-Simulator (firmware/native)
  lib/microinfer/    portable int8-Inferenz-Engine (C99, TFLite-kompatible Arithmetik)
  lib/benchapp/      serielles Testprotokoll + HAL-Schnittstelle
  lib/modelzoo/      generierte Modelldaten (nicht von Hand ändern)
  src/hal_arduino.cpp  HAL für ESP8266/ESP32/RP2040/STM32/nRF52
hilbench/            Host-Seite: CLI, Discovery, Flashen, Reset/Power, Sessions, pytest-Plugin, Reports
hilbench/ml/         Quantisierung, Python-Referenz, Training, Codegen, TFLite-Import
hil/                 targets.yaml (Chip-Katalog), boards.yaml (dein Laborinventar), udev/Host-Setup
models/zoo|custom    Referenzmodelle / eigene importierte Modelle
tests/hil, tests/unit  HIL-Suiten / Host-Tests
docs/                hardware.md, protocol.md, ci.md, extending.md
```
