# can-ids-tiny

Frame-level CAN bus intrusion detector for microcontrollers (ESP32, ESP32-S3, any C99 target).
The model card with all results is in [MODEL_CARD.md](MODEL_CARD.md). It is published on Hugging Face as `README.md`.

## Layout

| Path | Content |
|---|---|
| `pipeline.py` | `evaluate` (4-set protocol), `export` (final model, C code, parity check), `convert`, `testvectors` |
| `publish.py` | `tables` (Markdown tables from the results), `build [--repo ORG/NAME --upload]` (Hugging Face folder) |
| `c/` | Detector API `can_ids_tiny.[ch]`, host harness, `generated/` (model, config, test vectors) |
| `firmware/` | ESP-IDF benchmark app: replays recorded frames, checks scores, measures latency |
| `results/` | Protocol results, export config, benchmark results |

The feature extractor is shared: `firmware/components/msml_can_features/`.

## Run the benchmark on your board

No CAN transceiver is needed; the board only needs USB.

**Without installing anything (Chrome or Edge):** open
[esptool-js](https://espressif.github.io/esptool-js/), click *Connect* and pick the board's
serial port. The log shows the chip type. Flash `can-ids-tiny-bench-<chip>.bin` at address `0x0`
and click *Program*. Then switch to the *Console*, connect at 115200 baud and press *Reset*. The
result line repeats every 5 seconds.

**With ESP-IDF v5.5:**

```bash
cd models/can-ids-tiny/firmware
idf.py set-target esp32s3      # or esp32, esp32c3, ...
idf.py build flash monitor
```

The board prints a line (repeated every 5 s) that starts with `CAN_IDS_TINY_RESULT`, followed by JSON with
latency (median, p99, max in µs), score mismatches against the host (should be 0) and detected
attack frames. Save it as `results/benchmarks/<board>.json`.

## Reproduce training

```bash
uv sync
uv run python -m msml.datasets.can_train_and_test
uv run python models/can-ids-tiny/pipeline.py evaluate
uv run python models/can-ids-tiny/pipeline.py export
uv run python models/can-ids-tiny/pipeline.py testvectors
```
