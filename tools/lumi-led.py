#!/usr/bin/env python3
"""Control the ARGB lighting of an Intel Arc B580 Onix Lumi on Linux.

Talks to the AMC on /dev/i2c-15, address 0x28, using the same protocol as ONIX's
own utility - (register, value) pairs. See docs/05-led-protocol.md.

    tools/lumi-led.py init                    # the app's init sequence
    tools/lumi-led.py color ff0000            # Custom mode, red
    tools/lumi-led.py brightness 136
    tools/lumi-led.py mode rainbow --speed 5
    tools/lumi-led.py off
    tools/lumi-led.py raw 3e:88 --dry-run     # show the bytes without writing

No root needed: systemd-logind grants the local session user an ACL on /dev/i2c-*.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amc import I2CBus, find_amc  # noqa: E402

# register -> label. Only these are written without --force: they are the ones
# ONIX's app uses. The AMC also drives the fans and the voltage regulator, and
# registers outside this list were never observed and may not be lighting at all.
REGS = {
    0x0F: "bypass",
    0x10: "mode",
    0x11: "runway.response", 0x12: "runway.interval", 0x29: "runway.chaser",
    0x13: "onecolor.response",
    0x14: "direction",
    0x16: "serial.response", 0x17: "serial.speed",
    0x18: "rainbow.response", 0x19: "rainbow.speed",
    0x1A: "custom.R", 0x1B: "custom.G", 0x1C: "custom.B",
    0x20: "stacking.speed",
    0x27: "strip.length",
    0x3E: "brightness",
    0xC8: "breathing.tempo",
    0xC9: "breathing.R", 0xCA: "breathing.G", 0xCB: "breathing.B",
}

MODES = {
    "rainbow": 0x00, "custom": 0x01, "breathing": 0x02, "serial": 0x03,
    "runway": 0x04, "onecolor": 0x05, "stacking": 0x06,
}

# per-mode parameters: argument name -> (register, factory default)
MODE_PARAMS = {
    "rainbow":  {"response": (0x18, 2),  "speed": (0x19, 5)},
    "runway":   {"response": (0x11, 10), "interval": (0x12, 1),
                 "chaser": (0x29, 1)},
    "onecolor": {"response": (0x13, 10)},
    "serial":   {"response": (0x16, 2),  "speed": (0x17, 16)},
    "stacking": {"speed": (0x20, 10)},
    "breathing": {"tempo": (0xC8, 6)},
    "custom":   {},
}

DEFAULT_BRIGHTNESS = 0x88


def gpu_sensors():
    out = {}
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(os.path.join(h, "name")).read().strip() != "xe":
                continue
        except OSError:
            continue
        for f in sorted(glob.glob(os.path.join(h, "fan*_input"))):
            try:
                out[os.path.basename(f)] = int(open(f).read().strip())
            except (OSError, ValueError):
                pass
        temps = []
        for f in glob.glob(os.path.join(h, "temp*_input")):
            try:
                temps.append(int(open(f).read().strip()))
            except (OSError, ValueError):
                pass
        if temps:
            out["temp_max"] = max(temps)
    return out


class Lumi:
    def __init__(self, dry_run=False, read_status=True, verbose=True):
        self.dry_run = dry_run
        self.read_status = read_status
        self.verbose = verbose
        self.bus_n, self.addr = find_amc()
        self.bus = None if dry_run else I2CBus(self.bus_n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.bus:
            self.bus.close()

    def send_many(self, txs, delay=0.05):
        """Send each logical operation in its OWN transaction.

        This is not fussiness: batching a mode change together with colour and
        brightness turns the lighting off. The official app never batches - each
        of its methods writes a single command. See docs/06-hardware-validation.md.
        """
        out = []
        for i, pairs in enumerate(txs):
            if i:
                time.sleep(delay)
            out.append(self.send(pairs))
        return out

    def send(self, pairs: list[tuple[int, int]]):
        """Write a sequence of (register, value) pairs in one transaction."""
        payload = bytearray()
        for reg, val in pairs:
            payload += bytes([reg & 0xFF, val & 0xFF])
        if self.verbose:
            desc = "  ".join(f"{REGS.get(r, '?')}=0x{v:02x}" for r, v in pairs)
            print(f"  -> {bytes(payload).hex(' ')}    [{desc}]")
        if self.dry_run:
            return None
        self.bus.raw_write(self.addr, bytes(payload))
        if not self.read_status:
            return None
        time.sleep(0.005)
        # reading right after the write is what ONIX's app does. A bare read,
        # with no write before it, wedges the bus - see docs/03-pitfalls.md.
        status = self.bus.raw_read(self.addr, 1, i_know_the_risk=True)
        if self.verbose:
            print(f"  <- {status.hex()}")
        return status


def parse_color(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("colour must be RRGGBB in hex")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def check_regs(pairs, force):
    unknown = [r for r, _ in pairs if r not in REGS]
    if unknown and not force:
        raise SystemExit(
            "register(s) outside the known list: "
            + ", ".join(f"0x{r:02x}" for r in unknown)
            + "\nThe AMC also drives the fans and the voltage regulator. "
              "Use --force if you are sure.")


def build_transactions(args) -> list[list[tuple[int, int]]]:
    """Turn parsed arguments into a list of I2C transactions.

    Each element is one transaction, and the split matters: a mode change must
    never share a transaction with anything else (docs/06-hardware-validation.md).
    """
    txs: list[list[tuple[int, int]]] = []
    if args.cmd == "init":
        txs = [[(0x3E, DEFAULT_BRIGHTNESS), (0x0F, 0x00), (0x27, 0x0E)]]
    elif args.cmd == "off":
        txs = [[(0x3E, 0x00)]]
    elif args.cmd == "on":
        txs = [[(0x3E, args.brightness)]]
    elif args.cmd == "brightness":
        txs = [[(0x3E, args.value)]]
    elif args.cmd == "bypass":
        txs = [[(0x0F, 1 if args.state == "on" else 0)]]
    elif args.cmd == "color":
        r, g, b = args.rgb
        bright = DEFAULT_BRIGHTNESS if args.brightness is None else args.brightness
        # order validated on hardware: mode, brightness, colour - each on its own
        txs = [[(0x10, MODES["custom"])], [(0x3E, bright)],
               [(0x1A, r), (0x1B, g), (0x1C, b)]]
    elif args.cmd == "breathing":
        r, g, b = args.rgb
        bright = DEFAULT_BRIGHTNESS if args.brightness is None else args.brightness
        txs = [[(0x10, MODES["breathing"])], [(0x3E, bright)],
               [(0xC9, r), (0xCA, g), (0xCB, b)]]
        if args.tempo is not None:
            txs.append([(0xC8, args.tempo)])
    elif args.cmd == "mode":
        txs = [[(0x10, MODES[args.name])]]
        bright = DEFAULT_BRIGHTNESS if args.brightness is None else args.brightness
        txs.append([(0x3E, bright)])
        # effect parameters are always written: without "response" the mode
        # lights up but never animates (docs/06-hardware-validation.md)
        for pname, (reg, default) in MODE_PARAMS[args.name].items():
            val = getattr(args, pname, None)
            txs.append([(reg, default if val is None else val)])
    elif args.cmd == "raw":
        pairs = []
        for item in args.pairs.replace(",", " ").split():
            reg, _, val = item.partition(":")
            if not val:
                raise SystemExit(f"invalid pair: {item!r} (use reg:val)")
            pairs.append((int(reg, 16), int(val, 16)))
        txs = [pairs]

    return txs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show the bytes, do not write")
    ap.add_argument("--no-read", action="store_true",
                    help="do not read the status byte after writing")
    ap.add_argument("--delay", type=float, default=0.05,
                    help="pause between transactions, in seconds (default 0.05)")
    ap.add_argument("--force", action="store_true",
                    help="allow registers outside the known list")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="the official app\'s init sequence")
    sub.add_parser("off", help="brightness 0")
    p = sub.add_parser("on", help="default brightness (0x88)")
    p.add_argument("--brightness", type=int, default=DEFAULT_BRIGHTNESS)

    p = sub.add_parser("brightness", help="set the brightness")
    p.add_argument("value", type=int)

    p = sub.add_parser("color", help="Custom mode with a fixed colour")
    p.add_argument("rgb", type=parse_color, metavar="RRGGBB")
    p.add_argument("--brightness", type=int)

    p = sub.add_parser("breathing", help="Breathing mode with a colour")
    p.add_argument("rgb", type=parse_color, metavar="RRGGBB")
    p.add_argument("--tempo", type=int)
    p.add_argument("--brightness", type=int)

    p = sub.add_parser("mode", help="select an effect mode")
    p.add_argument("name", choices=sorted(MODES))
    p.add_argument("--speed", type=int)
    p.add_argument("--response", type=int)
    p.add_argument("--interval", type=int)
    p.add_argument("--chaser", type=int)
    p.add_argument("--tempo", type=int)
    p.add_argument("--brightness", type=int)

    p = sub.add_parser("bypass", help="turn bypass on or off")
    p.add_argument("state", choices=["on", "off"])

    p = sub.add_parser("raw", help="raw reg:val pairs, e.g. 3e:88,10:01")
    p.add_argument("pairs")

    args = ap.parse_args()

    txs = build_transactions(args)

    check_regs([p for tx in txs for p in tx], args.force)

    before = gpu_sensors()
    with Lumi(dry_run=args.dry_run, read_status=not args.no_read) as lumi:
        print(f"AMC: /dev/i2c-{lumi.bus_n} addr 0x{lumi.addr:02x}"
              f"{'  [dry-run]' if args.dry_run else ''}")
        lumi.send_many(txs, delay=args.delay)
    if not args.dry_run:
        after = gpu_sensors()
        changed = {k: (before.get(k), after[k]) for k in after
                   if before.get(k) != after[k]}
        if changed:
            print("GPU sensors:", ", ".join(
                f"{k} {a}->{b}" for k, (a, b) in changed.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
