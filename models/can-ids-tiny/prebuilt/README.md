# Prebuilt benchmark firmware

Flash with [esptool-js](https://espressif.github.io/esptool-js/) (Chrome/Edge) at address `0x0`,
then open the console at 115200 baud and press Reset. A line starting with `CAN_IDS_TINY_RESULT`
repeats every 5 seconds. No CAN transceiver is needed.

| File | Board | Built with |
|---|---|---|
| `can-ids-tiny-bench-esp32.bin` | ESP32 (DevKitC, ...) | ESP-IDF v5.5.5 |
| `can-ids-tiny-bench-esp32s3.bin` | ESP32-S3 | ESP-IDF v5.5.5 |
| `can-ids-tiny-bench-esp8266.bin` | ESP8266 (Wemos D1 mini, NodeMCU; 4 MB flash) | Arduino core 3.1.2, 160 MHz |

They contain the model and test vectors in `../c/generated/` at the commit that added them.
Rebuild after retraining; see `../README.md`.
