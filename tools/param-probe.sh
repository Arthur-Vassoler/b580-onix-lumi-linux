#!/usr/bin/env bash
# Set up one Rainbow parameter combination for characterisation testing.
# See docs/07-effect-parameters.md for the protocol.
#
#   tools/param-probe.sh <response> <spread>
#   tools/param-probe.sh 2 5          # the vendor defaults
set -euo pipefail

cd "$(dirname "$0")/.."

RESPONSE=${1:?usage: param-probe.sh <response 0x18> <spread 0x19>}
SPREAD=${2:?usage: param-probe.sh <response 0x18> <spread 0x19>}

hex() { printf '%02x' "$1"; }

# Rainbow, full strip, default brightness, one register per transaction.
./tools/lumi-led.py --no-read raw "10:00" >/dev/null
sleep 0.1
./tools/lumi-led.py --no-read raw "3e:88" >/dev/null
sleep 0.1
./tools/lumi-led.py --no-read raw "27:0e" >/dev/null
sleep 0.1
./tools/lumi-led.py --no-read raw "18:$(hex "$RESPONSE")" >/dev/null
sleep 0.1
./tools/lumi-led.py --no-read raw "19:$(hex "$SPREAD")" >/dev/null

cat <<MSG

  Rainbow running with:   0x18 (response) = $RESPONSE
                          0x19 (spread)   = $SPREAD

  Record two numbers:
    BANDS  how many distinct colour bands you can count across the 14 LEDs
    CYCLE  seconds for the pattern to repeat (watch one LED: time between
           two consecutive moments it shows the same colour)

MSG
