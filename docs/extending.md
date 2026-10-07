# Neue Hardware einbinden

Die Firmware ist so aufgeteilt, dass ein neuer SoC meist nur Konfiguration braucht:

```
benchapp (Protokoll)  ─┐
microinfer (Engine)    ├─ portables C99, kein Heap, kein FPU nötig
modelzoo (Daten)      ─┘
hal.h  ◄── hal_arduino.cpp (alle Arduino-Cores) │ hal_native.c (PC) │ eigene HAL (z. B. Zephyr, ESP-IDF)
```

## 1. PlatformIO-Umgebung (`firmware/platformio.ini`)

```ini
[env:teensy41]
platform = teensy
board = teensy41
build_flags = ${env.build_flags} -D HIL_TARGET=\"teensy41\"
```

`HIL_TARGET` muss genau dem Target-Namen in `hil/targets.yaml` entsprechen; die Bench prüft das
nach dem Flashen.

## 2. Target (`hil/targets.yaml`)

```yaml
teensy41:
  description: Teensy 4.1 - Cortex-M7 @ 600 MHz
  pio_env: teensy41
  flasher: platformio
  reset: soft
  usb_ids: ["16c0:0483"]
  chip_match: "."            # Regex auf INFO.chip
  reenumerates: true         # natives USB
```

Ableiten geht mit `extends: <anderes Target>`.

## 3. HAL (nur wenn nötig)

`firmware/src/hal_arduino.cpp` enthält Zweige pro Architektur. Ohne eigenen Zweig misst der
generische Fallback die Zeit mit `micros()` und meldet Zyklen und Heap als 0. Ein eigener
Zweig liefert zusätzlich:

* `hal_cycles()`: Zykluszähler (Cortex-M3/M4/M7/M33: DWT wird automatisch genutzt)
* `hal_free_heap()`, `hal_cpu_mhz()`
* `hal_reset()`: Software-Reset (Cortex-M: `NVIC_SystemReset()` ist schon dabei)
* `hal_chip()` / `hal_uid()`: Identifikation für die Prüfung „richtiges Board im Slot“

Für Nicht-Arduino-Umgebungen (ESP-IDF, Zephyr, STM32Cube) implementiert man `hal.h` in einer
eigenen Datei und ruft `bench_init()` sowie in der Hauptschleife `bench_poll()` auf.

## 4. Testen

```bash
hilbench build -t teensy41
hilbench discover                  # Board finden, Eintrag in hil/boards.yaml anlegen
hilbench run -b teensy41-1
```

Die CI-Matrix in `.github/workflows/ci.yml` um das neue Target ergänzen, dann baut jede
Änderung auch diese Firmware.

## Kleine Targets

Wenn RAM oder Flash nicht reichen, große Modelle ausschließen:

```ini
build_flags = ${env.build_flags} -D HIL_TARGET=\"tiny\" -D MI_EXCLUDE_KWS_DSCNN
```
```yaml
tiny:
  excluded_models: [kws_dscnn]
```

Die Arena für die Aktivierungen wird automatisch auf das größte verbliebene Modell bemessen.
