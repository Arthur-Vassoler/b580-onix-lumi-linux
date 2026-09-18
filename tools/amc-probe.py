#!/usr/bin/env python3
"""Sondagem do AMC da Arc B580 Onix Lumi.

Histórico: esta ferramenta é do início do projeto, de quando o protocolo ainda
era desconhecido. Para controlar o LED use tools/lumi-led.py. O que sobrou de
útil aqui é o relatório das capacidades do adaptador.

Não escreve nada no barramento (a única exceção é `--probe-cmd`, que manda um
comando fornecido pelo usuário e está desligado por padrão).

    tools/amc-probe.py              # mapa de registradores + funções do adaptador
    tools/amc-probe.py --blocks     # tenta também leituras de bloco SMBus
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amc import I2CBus, find_amc  # noqa: E402


def gpu_hwmon():
    """Sensores da GPU, para conferir que nada saiu do lugar durante a sondagem."""
    out = {}
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(os.path.join(h, "name")).read().strip() != "xe":
                continue
        except OSError:
            continue
        for f in sorted(glob.glob(os.path.join(h, "fan*_input"))
                        + glob.glob(os.path.join(h, "temp*_input"))):
            try:
                out[os.path.basename(f)] = int(open(f).read().strip())
            except (OSError, ValueError):
                pass
    return out


def dump_registers(bus, addr, hi=0x100):
    vals = {}
    for reg in range(hi):
        try:
            vals[reg] = bus.read_byte_data(addr, reg)
        except OSError as e:
            vals[reg] = f"ERR({e.errno})"
    return vals


def print_map(vals):
    print("      " + "  ".join(f"{c:x}" for c in range(16)))
    for row in range(0, len(vals), 16):
        cells = []
        for col in range(16):
            v = vals.get(row + col)
            cells.append("--" if isinstance(v, str) else f"{v:02x}")
        print(f"{row:02x}:  " + " ".join(cells))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sweep", action="store_true",
                    help="PERIGO: varre 0x00..0xff. Cada leitura escreve um byte "
                         "solto, e o AMC espera pares (registrador, valor). "
                         "256 escritas incompletas seguidas travam o barramento "
                         "até o próximo ciclo de energia. Ver docs/03-armadilhas.md.")
    ap.add_argument("--blocks", action="store_true",
                    help="tentar também leituras de bloco SMBus")
    ap.add_argument("--raw", type=int, metavar="N", default=0,
                    help="PERIGO: ler N bytes crus. Trava o AMC até o reboot.")
    args = ap.parse_args()

    bus_n, addr = find_amc()
    print(f"AMC: /dev/i2c-{bus_n} addr 0x{addr:02x}\n")

    before = gpu_hwmon()

    with I2CBus(bus_n) as bus:
        print("adaptador suporta:")
        for f in bus.funcs_str():
            print(f"  {f}")
        print()

        try:
            print(f"SMBus receive byte         -> 0x{bus.read_byte(addr):02x}")
        except OSError as e:
            print(f"SMBus receive byte         -> erro {e}")

        if args.raw:
            try:
                data = bus.raw_read(addr, args.raw, i_know_the_risk=True)
                print(f"leitura crua ({args.raw} bytes)    -> {data.hex(' ')}")
            except OSError as e:
                print(f"leitura crua               -> erro {e}")

        if args.sweep:
            print("\nmapa de registradores (SMBus read byte data, 0x00..0xff):\n")
            vals = dump_registers(bus, addr)
            print_map(vals)

            hist = Counter(v for v in vals.values() if not isinstance(v, str))
            print("\ndistribuição dos valores:")
            for v, n in hist.most_common(8):
                print(f"  0x{v:02x}  {n:3d}x  ({n * 100 // len(vals)}%)")
        else:
            print("\nvarredura de registradores não executada (use --sweep).")
            print("O AMC não tem mapa de registradores legível: ele espera pares")
            print("(registrador, valor) e a varredura manda escritas pela metade.")
            print("Ver docs/05-protocolo-led.md para o protocolo de verdade.")

        if args.blocks:
            print("\nleituras de bloco SMBus:")
            for reg in (0x00, 0x01, 0x06, 0x07, 0x0f, 0x10, 0x80):
                try:
                    data = bus.read_block_data(addr, reg)
                    print(f"  reg 0x{reg:02x} -> {len(data)} bytes: {data.hex(' ')}")
                except OSError as e:
                    print(f"  reg 0x{reg:02x} -> erro {e.errno} ({e.strerror})")

    after = gpu_hwmon()
    print("\nsensores da GPU (antes -> depois):")
    for k in sorted(before):
        a, b = before[k], after.get(k)
        flag = "" if a == b else "   <-- mudou"
        print(f"  {k:<16} {a:>7} -> {b:>7}{flag}")


if __name__ == "__main__":
    main()
