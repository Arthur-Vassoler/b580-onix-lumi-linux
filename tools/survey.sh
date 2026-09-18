#!/usr/bin/env bash
# Inventory of the hardware relevant to the Arc B580 Onix Lumi's lighting.
# Read only. No root required.
set -uo pipefail

hdr() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }

hdr "System"
uname -a; grep '^PRETTY_NAME' /etc/os-release

hdr "GPU"
lspci -nn | grep -Ei 'vga|3d|display'
GPU=$(lspci -D -nn | grep -Ei 'vga|display' | grep -i intel | head -1 | cut -d' ' -f1)
echo "PCI: $GPU"
[ -n "${GPU:-}" ] && echo "driver: $(basename "$(readlink -f /sys/bus/pci/devices/$GPU/driver 2>/dev/null)")"

hdr "USB devices (is the lighting on USB?)"
lsusb

hdr "I2C buses"
for d in /sys/class/i2c-dev/i2c-*; do
    n=$(basename "$d")
    printf '%-8s %-38s %s\n' "$n" "$(cat "$d/name" 2>/dev/null)" \
        "$(readlink -f "$d/device" 2>/dev/null | sed 's|/sys/devices||')"
done | sort -V

hdr "I2C buses belonging to the GPU"
[ -n "${GPU:-}" ] && ls -d /sys/bus/pci/devices/$GPU/i2c-* /sys/bus/pci/devices/$GPU/i2c_designware.*/i2c-* 2>/dev/null

hdr "I2C clients already instantiated by the kernel"
for c in /sys/bus/i2c/devices/*-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]; do
    [ -e "$c" ] || continue
    drv=$([ -L "$c/driver" ] && basename "$(readlink "$c/driver")" || echo '(none)')
    printf '%-12s name=%-12s driver=%s\n' "$(basename "$c")" "$(cat "$c/name" 2>/dev/null)" "$drv"
done

hdr "Bus scan (read mode, safe)"
for d in /sys/class/i2c-dev/i2c-*; do
    n=$(basename "$d"); b=${n#i2c-}
    name=$(cat "$d/name" 2>/dev/null)
    out=$(i2cdetect -y -r "$b" 2>/dev/null | tail -n +2)
    found=$(echo "$out" | grep -oE ' (UU|[0-9a-f]{2})' | tr -d ' ' | grep -v '^--$' | tr '\n' ' ')
    printf '%-8s %-38s %s\n' "$n" "$name" "${found:-(empty)}"
done

hdr "GPU hwmon (to watch fans and temperatures during write tests)"
for h in /sys/class/hwmon/hwmon*; do
    [ "$(cat "$h/name" 2>/dev/null)" = "xe" ] || continue
    echo "$h"
    for f in "$h"/fan*_input "$h"/temp*_input "$h"/power1_input; do
        [ -e "$f" ] || continue
        printf '  %-18s %s\n' "$(basename "$f")" "$(cat "$f" 2>/dev/null)"
    done
done
