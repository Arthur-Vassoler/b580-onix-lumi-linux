#!/usr/bin/env python3
"""Controla o LED ARGB da Intel Arc B580 Onix Lumi no Linux.

Fala com o AMC em /dev/i2c-15, endereço 0x28, usando o mesmo protocolo do
utilitário oficial da ONIX — pares (registrador, valor). Ver docs/05-protocolo-led.md.

    tools/lumi-led.py init                    # sequência de inicialização do app
    tools/lumi-led.py color ff0000            # modo Custom, vermelho
    tools/lumi-led.py brightness 136
    tools/lumi-led.py mode rainbow --speed 5
    tools/lumi-led.py off
    tools/lumi-led.py raw 3e:88 --dry-run     # mostra sem escrever

Não precisa de root: o systemd-logind dá ACL de /dev/i2c-* ao usuário da sessão local.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amc import I2CBus, find_amc  # noqa: E402

# registrador -> rótulo. Só estes são escritos sem --force: são os que o app da
# ONIX usa. O AMC também controla ventoinha e VRM; registradores fora desta lista
# não foram observados e podem não ser de iluminação.
REGS = {
    0x0F: "bypass",
    0x10: "modo",
    0x11: "runway.response", 0x12: "runway.interval", 0x29: "runway.chaser",
    0x13: "onecolor.response",
    0x14: "direcao",
    0x16: "serial.response", 0x17: "serial.speed",
    0x18: "rainbow.response", 0x19: "rainbow.speed",
    0x1A: "custom.R", 0x1B: "custom.G", 0x1C: "custom.B",
    0x20: "stacking.speed",
    0x27: "init.desconhecido",
    0x3E: "brilho",
    0xC8: "breathing.tempo",
    0xC9: "breathing.R", 0xCA: "breathing.G", 0xCB: "breathing.B",
}

MODES = {
    "rainbow": 0x00, "custom": 0x01, "breathing": 0x02, "serial": 0x03,
    "runway": 0x04, "onecolor": 0x05, "stacking": 0x06,
}

# parâmetros por modo: nome do argumento -> (registrador, padrão de fábrica)
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
        """Envia cada operação lógica em sua PRÓPRIA transação.

        Isto não é preciosismo: empacotar uma troca de modo junto com cor e brilho
        faz o LED apagar. O app oficial nunca agrupa — cada método dele escreve um
        comando só. Ver docs/06-validacao-hardware.md.
        """
        out = []
        for i, pairs in enumerate(txs):
            if i:
                time.sleep(delay)
            out.append(self.send(pairs))
        return out

    def send(self, pairs: list[tuple[int, int]]):
        """Escreve uma sequência de pares (registrador, valor) numa transação."""
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
        # leitura logo após a escrita: é o que o app da ONIX faz. Leitura solta,
        # sem escrita antes, trava o barramento — ver docs/03-armadilhas.md.
        status = self.bus.raw_read(self.addr, 1, i_know_the_risk=True)
        if self.verbose:
            print(f"  <- {status.hex()}")
        return status


def parse_color(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("cor deve ser RRGGBB em hex")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def check_regs(pairs, force):
    unknown = [r for r, _ in pairs if r not in REGS]
    if unknown and not force:
        raise SystemExit(
            "registrador(es) fora da lista conhecida: "
            + ", ".join(f"0x{r:02x}" for r in unknown)
            + "\nO AMC também controla ventoinha e VRM. Use --force se tem certeza.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="mostra os bytes, não escreve")
    ap.add_argument("--no-read", action="store_true",
                    help="não lê o byte de status depois da escrita")
    ap.add_argument("--delay", type=float, default=0.05,
                    help="pausa entre transações, em segundos (padrão 0.05)")
    ap.add_argument("--force", action="store_true",
                    help="permite registradores fora da lista conhecida")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="sequência de inicialização do app oficial")
    sub.add_parser("off", help="brilho 0")
    p = sub.add_parser("on", help="brilho padrão (0x88)")
    p.add_argument("--brightness", type=int, default=DEFAULT_BRIGHTNESS)

    p = sub.add_parser("brightness", help="define o brilho")
    p.add_argument("value", type=int)

    p = sub.add_parser("color", help="modo Custom com cor fixa")
    p.add_argument("rgb", type=parse_color, metavar="RRGGBB")
    p.add_argument("--brightness", type=int)

    p = sub.add_parser("breathing", help="modo Breathing com cor")
    p.add_argument("rgb", type=parse_color, metavar="RRGGBB")
    p.add_argument("--tempo", type=int)
    p.add_argument("--brightness", type=int)

    p = sub.add_parser("mode", help="seleciona um modo de efeito")
    p.add_argument("name", choices=sorted(MODES))
    p.add_argument("--speed", type=int)
    p.add_argument("--response", type=int)
    p.add_argument("--interval", type=int)
    p.add_argument("--chaser", type=int)
    p.add_argument("--tempo", type=int)
    p.add_argument("--brightness", type=int)

    p = sub.add_parser("bypass", help="liga/desliga o bypass")
    p.add_argument("state", choices=["on", "off"])

    p = sub.add_parser("raw", help="pares reg:val crus, ex: 3e:88,10:01")
    p.add_argument("pairs")

    args = ap.parse_args()

    # cada elemento de txs é uma transação I2C separada
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
        # ordem validada no hardware: modo, brilho, cor — cada um por si
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
        for pname, (reg, _default) in MODE_PARAMS[args.name].items():
            val = getattr(args, pname, None)
            if val is not None:
                txs.append([(reg, val)])
    elif args.cmd == "raw":
        pairs = []
        for item in args.pairs.replace(",", " ").split():
            reg, _, val = item.partition(":")
            if not val:
                raise SystemExit(f"par inválido: {item!r} (use reg:val)")
            pairs.append((int(reg, 16), int(val, 16)))
        txs = [pairs]

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
            print("sensores da GPU:", ", ".join(
                f"{k} {a}->{b}" for k, (a, b) in changed.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
