#!/usr/bin/env bash
# Build the ESP8266 benchmark with arduino-cli and the esp8266 Arduino core (3.1.x).
#   FQBN=esp8266:esp8266:nodemcuv2:xtal=160 ./build.sh    (default: Wemos D1 mini at 160 MHz)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
SKETCH="$HERE/can_ids_tiny_bench"
mkdir -p "$SKETCH/src"
cp "$REPO/firmware/components/msml_can_features/msml_can_features.c" \
   "$REPO/firmware/components/msml_can_features/include/msml_can_features.h" \
   "$REPO/models/can-ids-tiny/c/can_ids_tiny.c" "$REPO/models/can-ids-tiny/c/can_ids_tiny.h" \
   "$REPO"/models/can-ids-tiny/c/generated/*.h "$SKETCH/src/"
EXTRA=()
if [[ -n "${CTAGS_DIR:-}" ]]; then  # only needed when the Arduino ctags tool is not installed
    EXTRA+=(--build-property "runtime.tools.ctags.path=$CTAGS_DIR")
fi
arduino-cli compile --fqbn "${FQBN:-esp8266:esp8266:d1_mini:xtal=160}" \
    --output-dir "${OUT:-$HERE/build}" "${EXTRA[@]}" "$SKETCH"
