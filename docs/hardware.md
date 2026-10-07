# Hardware-Aufbau der HIL-Bench

## Der Host

Jeder Linux-Rechner funktioniert als HIL-Host, ein Raspberry Pi 4/5 genügt. Dazu kommen:

* **aktiver USB-Hub**, idealerweise mit **schaltbarer Stromversorgung pro Port** (Per-Port
  Power Switching, PPPS). Dann kann die Bench auch ein völlig festgefahrenes Board per
  Power-Cycle zurückholen. Kompatible Hubs: `uhubctl` ohne Argumente listet sie,
  siehe auch <https://github.com/mvp/uhubctl#compatible-usb-hubs>. Alternativ geht ein
  Relais-Board oder eine schaltbare Steckdose mit `power: {type: command, on: …, off: …}`.
* **gute USB-Kabel** (Datenkabel!). Für Boards mit WLAN/BLE-Spitzenströmen sollte der Hub ein
  eigenes Netzteil haben.

Einmalig einrichten:

```bash
sudo ./hil/setup-host.sh     # dialout-Gruppe, udev-Regeln, uhubctl
```

## Boards eindeutig zuordnen

`hilbench discover` listet für jeden Port `serial_number`, `location` (physischer USB-Pfad),
`vid_pid` und den `/dev/serial/by-id`-Namen. In `hil/boards.yaml`:

| Situation | `match:` |
|---|---|
| Adapter mit eindeutiger Seriennummer (FTDI, CP2102 mit Serial, native USB von ESP32-S3/C3, RP2040, nRF52) | `{serial_number: "…"}` |
| Billige CH340-Boards (keine oder identische Seriennummern) | `{location: "1-1.4"}`: Board dann **immer am selben Hub-Port** lassen |
| genau ein Board dieses Typs am Host | `{vid_pid: "1a86:7523"}` |
| Board an einem anderen Rechner (ser2net / RFC2217) | `port: rfc2217://raspi:4000` |

Nach dem Flashen fragt die Bench ab, welches Target und welcher Chip antwortet und welche
Build-ID läuft. Ein vertauschtes Board oder ein fehlgeschlagener Flash-Vorgang fällt dadurch
sofort auf.

## ESP8266MOD / ESP-12E/F

### Auf einem Dev-Board (NodeMCU, Wemos D1 mini, …)

Diese Boards haben einen USB-UART (CH340/CP2102) und die übliche Auto-Reset-Schaltung
(DTR→GPIO0, RTS→EN über zwei Transistoren). Es ist nichts weiter nötig:

```yaml
- id: esp8266-1
  target: esp8266            # oder esp8266_160mhz für 160-MHz-Benchmarks
  match: {location: "1-1.2"}
```

Hinweise:
* Der ROM-Bootloader schreibt nach jedem Reset Text mit 74880 Baud. Die Bench ignoriert dieses
  Rauschen und sucht nur nach `@{…}`-Frames.
* Die Firmware legt Gewichte per `PROGMEM` in den Flash, damit sie die ~80 KiB DRAM nicht
  belegen. Der freie Heap wird bei jedem Lauf gemessen und berichtet.

### Nacktes Modul mit USB-UART-Adapter (3,3 V!)

| ESP-12 Pin | Anschluss |
|---|---|
| VCC | 3,3 V (≥ 300 mA, 470 µF Elko nahe am Modul) |
| GND | GND |
| TX / RX | RX / TX des Adapters |
| EN (CH_PD) | 10 kΩ nach 3,3 V **und** RTS des Adapters (über NPN-Auto-Reset-Schaltung oder direkt) |
| GPIO0 | 10 kΩ nach 3,3 V **und** DTR des Adapters (über Auto-Reset-Schaltung) |
| GPIO2 | 10 kΩ nach 3,3 V |
| GPIO15 | 10 kΩ nach GND |
| RST | 10 kΩ nach 3,3 V |

Ohne Auto-Reset-Schaltung muss vor jedem Flashen GPIO0 von Hand auf GND gelegt werden. Für eine
automatisierte Bench sollte die Schaltung (2× BC547 + 2× 10 kΩ, wie auf dem NodeMCU) deshalb
vorhanden sein.

## ESP32 / ESP32-S3 / ESP32-C3

* DevKits mit UART-Bridge: `target: esp32 | esp32s3 | esp32c3`, Reset über DTR/RTS.
  Manche ESP32-Boards brauchen 1–10 µF zwischen EN und GND, sonst klappt der Auto-Reset nicht
  zuverlässig.
* Nativer USB-Port (USB-Serial/JTAG, `303a:1001`): `target: esp32s3_usb | esp32c3_usb`. Der
  Port verschwindet beim Reset kurz; die Bench wartet darauf und verbindet sich neu.

## Raspberry Pi Pico / Pico 2 (RP2040 / RP2350)

* Serielle Verbindung über natives USB-CDC. Geflasht wird mit PlatformIO (`picotool`) oder mit
  `flasher: uf2`: 1200-Baud-Touch, dann `firmware.uf2` auf das gemountete Laufwerk `RPI-RP2`
  kopieren (Auto-Mount erforderlich, sonst `flasher_options: {mount_globs: [...]}` setzen).
* Einen Hardware-Reset über serielle Leitungen gibt es nicht. Ein Power-Cycle über einen
  schaltbaren Hub-Port (`power: uhubctl`) ist deshalb dringend empfohlen. Optional kann ein GPIO
  eines anderen Boards den RUN-Pin ziehen (`reset: command`).

## STM32 Nucleo (z. B. NUCLEO-F446RE)

* Serielle Verbindung über den virtuellen COM-Port des ST-LINK (`0483:374b`).
* Flashen: PlatformIO (OpenOCD) oder schneller per Befehl:
  ```yaml
  flasher: command
  flasher_options: {command: "st-flash --reset write {bin} 0x08000000"}
  reset: command
  reset_options: {command: "st-flash reset"}
  ```

## Arduino Nano 33 BLE (nRF52840)

* Natives USB-CDC, geflasht wird über PlatformIO (bossac, 1200-Baud-Touch).
* Reset per RESET-Befehl. Wenn die Firmware hängt: Power-Cycle über den Hub, oder Doppelklick
  auf den Reset-Taster startet den Bootloader.

## Boards an einem anderen Rechner

Empfohlen: Auf dem Rechner, an dem die Boards hängen (z. B. ein Raspberry Pi), läuft selbst
`hilbench` bzw. der self-hosted CI-Runner ([ci.md](ci.md)). Der Pi ist dann ein
vollständiger HIL-Host.

Nur zum Testen bereits geflashter Boards genügt auch eine RFC2217-Freigabe per `ser2net`:

```yaml
- id: esp32-remote
  target: esp32
  port: rfc2217://raspi.local:4001
```

```bash
hilbench run -b esp32-remote --no-flash
```

Inferenz, Benchmarks und der DTR/RTS-Reset funktionieren über das Netzwerk. Zum Flashen
lässt sich `flasher: command` mit einem eigenen Skript nutzen (Platzhalter `{bin}`, `{elf}`,
`{dir}`, `{port}`), das die Datei z. B. per `scp` überträgt und auf dem Pi esptool aufruft.
