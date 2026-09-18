#!/usr/bin/env bash
# Recover the GPU's internal I2C bus when the AMC stops responding.
# Needs root. Escalates from least to most invasive, testing after each step.
set -uo pipefail

DEV=i2c_designware.1024
DRV=/sys/bus/platform/drivers/i2c_designware
SYSDEV=/sys/bus/platform/devices/$DEV

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0"; exit 1; }

amc_bus() {
    for c in /sys/bus/i2c/devices/*-0028; do
        [ -e "$c/name" ] && [ "$(cat "$c/name")" = amc ] && { basename "$c" | cut -d- -f1; return; }
    done
}

test_amc() {
    local b; b=$(amc_bus)
    [ -n "$b" ] || { echo "  (no amc client found)"; return 1; }
    if timeout 5 i2cget -y "$b" 0x28 >/dev/null 2>&1; then
        echo "  ✔ AMC responds on /dev/i2c-$b"; return 0
    fi
    echo "  ✘ AMC does not respond on /dev/i2c-$b"; return 1
}

echo "initial state:"; test_amc && { echo "nothing to do."; exit 0; }

echo
echo "[1/3] forcing runtime PM to 'on' for the controller..."
echo on > "$SYSDEV/power/control" 2>/dev/null
sleep 1
test_amc && exit 0

echo
echo "[2/3] unbinding and rebinding the i2c_designware driver (resets the controller)..."
echo "$DEV" > "$DRV/unbind" 2>/dev/null
sleep 1
echo "$DEV" > "$DRV/bind" 2>/dev/null
sleep 2
test_amc && exit 0

echo
echo "[3/3] nothing in userspace fixed it."
echo
echo "The AMC is most likely holding the bus itself, with SDA stuck low."
echo "Only a power cycle clears that: reboot the machine."
echo "A warm reboot usually suffices; if not, shut down fully and power back on."
exit 1
