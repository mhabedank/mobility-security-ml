#!/bin/sh
# Prepare a Linux machine (PC, Raspberry Pi, CI runner) as HIL host.
#   sudo ./hil/setup-host.sh [user]
set -eu
USER_NAME="${1:-${SUDO_USER:-$(id -un)}}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root: sudo $0 [user]" >&2
    exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq python3-venv python3-pip uhubctl git make gcc
fi

usermod -aG dialout "$USER_NAME"
install -m 0644 "$HERE/99-hilbench.rules" /etc/udev/rules.d/99-hilbench.rules
udevadm control --reload-rules
udevadm trigger

# brltty grabs CH340 adapters on some desktop distributions
if systemctl list-unit-files 2>/dev/null | grep -q '^brltty'; then
    echo "note: brltty is installed and may steal CH340 serial ports (apt remove brltty)"
fi

mkdir -p /var/lock/hilbench
chgrp dialout /var/lock/hilbench
chmod 2775 /var/lock/hilbench

echo "done - log out and in again so that '$USER_NAME' gets the dialout group."
echo "next: python3 -m venv .venv && .venv/bin/pip install -e '.[hw]' && .venv/bin/hilbench discover"
