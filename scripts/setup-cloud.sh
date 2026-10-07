#!/usr/bin/env bash
# Prepare a fresh (cloud) Linux machine for this repository.
#
#   bash scripts/setup-cloud.sh              # Python env + system libraries (about 1 minute)
#   bash scripts/setup-cloud.sh --firmware   # also ESP-IDF 5.5 + QEMU and the ESP8266 Arduino core
#
# Safe to run more than once: installed parts are skipped. Datasets are not downloaded here;
# use `uv run python -m msml.datasets.can_train_and_test` when needed (~7.5 GB).
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
FIRMWARE=0
[[ "${1:-}" == "--firmware" ]] && FIRMWARE=1

ESP_ROOT=${ESP_ROOT:-/opt/esp}
IDF_VERSION=v5.5.5
ARDUINO_ROOT=${ARDUINO_ROOT:-/opt/arduino}
ARDUINO_CLI_VERSION=1.5.1
ESP8266_CORE_VERSION=3.1.2

log() { printf '\n==> %s\n' "$*"; }

apt_install() {
    local missing=()
    for p in "$@"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
    if ((${#missing[@]})); then
        apt-get update -qq && apt-get install -y -qq "${missing[@]}" >/dev/null
    fi
}

log "Python environment (uv)"
command -v uv >/dev/null || pip install -q uv
(cd "$REPO" && uv sync -q)

if ((FIRMWARE == 0)); then
    log "Done (run with --firmware for the microcontroller toolchains)"
    exit 0
fi

log "System libraries (QEMU runtime, ctags for arduino-cli)"
apt_install libslirp0 libsdl2-2.0-0 exuberant-ctags

log "ESP-IDF $IDF_VERSION, Xtensa toolchains and QEMU in $ESP_ROOT"
export IDF_TOOLS_PATH=$ESP_ROOT/tools
if [[ ! -d $ESP_ROOT/esp-idf ]]; then
    mkdir -p "$ESP_ROOT"
    git clone -q --depth 1 --branch "$IDF_VERSION" --recurse-submodules --shallow-submodules \
        https://github.com/espressif/esp-idf.git "$ESP_ROOT/esp-idf"
fi
(cd "$ESP_ROOT/esp-idf" &&
    python3 tools/idf_tools.py --non-interactive install --targets esp32,esp32s3 required >/dev/null &&
    python3 tools/idf_tools.py --non-interactive install qemu-xtensa >/dev/null &&
    # The constraints file lives on dl.espressif.com, which restricted networks may block.
    python3 tools/idf_tools.py install-python-env --no-constraints >/dev/null)

log "arduino-cli $ARDUINO_CLI_VERSION and ESP8266 core $ESP8266_CORE_VERSION in $ARDUINO_ROOT"
mkdir -p "$ARDUINO_ROOT/bin" "$ARDUINO_ROOT/sketchbook/hardware/esp8266com" "$ARDUINO_ROOT/data"
if [[ ! -x $ARDUINO_ROOT/bin/arduino-cli ]]; then
    curl -sSL "https://github.com/arduino/arduino-cli/releases/download/v${ARDUINO_CLI_VERSION}/arduino-cli_${ARDUINO_CLI_VERSION}_Linux_64bit.tar.gz" |
        tar -xz -C "$ARDUINO_ROOT/bin" arduino-cli
fi
CORE=$ARDUINO_ROOT/sketchbook/hardware/esp8266com/esp8266
if [[ ! -d $CORE ]]; then
    git clone -q --depth 1 --branch "$ESP8266_CORE_VERSION" https://github.com/esp8266/Arduino.git "$CORE"
    (cd "$CORE" && git submodule update --init --depth 1 -q && cd tools && python3 get.py >/dev/null)
fi
# arduino-cli expects its "builtin" discovery tools; fetch them from GitHub releases.
for tool in serial-discovery:v1.5.2 mdns-discovery:v1.1.0; do
    name=${tool%%:*}
    ver=${tool##*:}
    dir=$ARDUINO_ROOT/data/packages/builtin/tools/$name/${ver#v}
    if [[ ! -x $dir/$name ]]; then
        mkdir -p "$dir"
        curl -sSL "https://github.com/arduino/$name/releases/download/$ver/${name}_${ver}_Linux_64bit.tar.gz" |
            tar -xz -C "$dir" --strip-components=1
    fi
done
[[ -f $ARDUINO_ROOT/data/library_index.json ]] || echo '{"libraries":[]}' >"$ARDUINO_ROOT/data/library_index.json"
[[ -f $ARDUINO_ROOT/data/package_index.json ]] || echo '{"packages":[]}' >"$ARDUINO_ROOT/data/package_index.json"

cat <<EOF

==> Done. In a new shell:

  # ESP32 / ESP32-S3 (ESP-IDF)
  export IDF_TOOLS_PATH=$ESP_ROOT/tools IDF_PYTHON_CHECK_CONSTRAINTS=no
  . $ESP_ROOT/esp-idf/export.sh

  # ESP8266 (Arduino); FQBN vendor is "esp8266com" for this manual core install
  export PATH=$ARDUINO_ROOT/bin:\$PATH ARDUINO_DIRECTORIES_USER=$ARDUINO_ROOT/sketchbook \\
         ARDUINO_DIRECTORIES_DATA=$ARDUINO_ROOT/data
  FQBN=esp8266com:esp8266:d1_mini:xtal=160 CTAGS_DIR=/usr/bin models/can-ids-tiny/firmware-esp8266/build.sh
EOF
