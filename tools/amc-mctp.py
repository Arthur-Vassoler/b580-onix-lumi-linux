#!/usr/bin/env python3
"""Fala MCTP sobre SMBus com o AMC da Arc B580.

O formato dos pacotes vem de `drivers/gpu/drm/xe/xe_amc.c` — ver docs/02-protocolo-amc.md.

    tools/amc-mctp.py --self-test        # valida o empacotamento, não toca no hardware
    tools/amc-mctp.py discover           # descoberta MCTP padrão, somente leitura
    tools/amc-mctp.py alert-reason       # o único comando Intel documentado
    tools/amc-mctp.py raw 7e:8086:01     # mensagem vendor-defined arbitrária

Toda transação é escrita + espera de 20 ms + leitura. Nunca faça uma leitura solta:
ela trava o barramento até o próximo boot (docs/03-armadilhas.md).

AVISO — NUNCA FOI EXECUTADO NO HARDWARE. O empacotamento confere byte a byte com
o driver da Intel (--self-test), mas nenhuma das transações abaixo chegou a ser
enviada de verdade: o caminho do LED acabou sendo outro (docs/05-protocolo-led.md)
e este código ficou sem uso. `discover` lê 32 bytes de uma vez, que é exatamente o
padrão que travou o barramento uma vez. Trate como experimento, não como ferramenta.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amc import I2CBus, find_amc  # noqa: E402

# --- constantes do cabeçalho, de xe_amc.c ---------------------------------
SMBUS_MCTP_COMMAND = 0x0F   # command code de MCTP sobre SMBus
HOST_SLAVE_ADDR    = 0x8F   # AMC_GPU_I2C_ADDR
MCTP_VERSION       = 0x01
DEST_EID           = 12     # AMC_DESTINATION_ID
SRC_EID            = 8      # AMC_SOURCE_ID
FLAGS_SOM_EOM_TO   = 0xC8   # SOM|EOM, seq 0, TO=1, tag 0

RESPONSE_DELAY_S   = 0.020  # "AMC needs 20ms to generate the response"

MSG_TYPE_CONTROL   = 0x00
MSG_TYPE_VENDOR_PCI = 0x7E

VENDOR_INTEL = 0x8086
VENDOR_ONIX  = 0x207E

ALERT_REASON = {
    0: "desconhecido", 1: "Firmware Download", 2: "Thermal Trip",
    3: "OOB Request", 4: "OOB Reset", 5: "Catastrophic",
}

# MCTP control (DSP0236)
CTRL_CMDS = {
    0x02: "Get Endpoint ID",
    0x03: "Get Endpoint UUID",
    0x04: "Get MCTP Version Support",
    0x05: "Get Message Type Support",
    0x06: "Get Vendor Defined Message Support",
}

COMPLETION_CODES = {
    0x00: "SUCCESS", 0x01: "ERROR", 0x02: "ERROR_INVALID_DATA",
    0x03: "ERROR_INVALID_LENGTH", 0x04: "ERROR_NOT_READY",
    0x05: "ERROR_UNSUPPORTED_CMD",
}


def frame(body: bytes, pad_to: int = 0) -> bytes:
    """Envelopa um corpo de mensagem MCTP no transporte SMBus."""
    if pad_to and len(body) < pad_to:
        body = body + bytes(pad_to - len(body))
    header = bytes([HOST_SLAVE_ADDR, MCTP_VERSION, DEST_EID, SRC_EID, FLAGS_SOM_EOM_TO])
    return bytes([SMBUS_MCTP_COMMAND, len(header) + len(body)]) + header + body


def ctrl_body(command: int, data: bytes = b"", iid: int = 0) -> bytes:
    """Mensagem de controle MCTP: Rq=1, D=0, instance id."""
    return bytes([MSG_TYPE_CONTROL, 0x80 | (iid & 0x1F), command]) + data


def vendor_body(vendor: int, command: int, data: bytes = b"") -> bytes:
    return bytes([MSG_TYPE_VENDOR_PCI, (vendor >> 8) & 0xFF, vendor & 0xFF,
                  command]) + data


class Response:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.ok = len(raw) >= 8 and raw[0] == SMBUS_MCTP_COMMAND
        self.byte_count = raw[1] if len(raw) > 1 else 0
        self.src_addr = raw[2] if len(raw) > 2 else 0
        self.version = raw[3] if len(raw) > 3 else 0
        self.dest_eid = raw[4] if len(raw) > 4 else 0
        self.src_eid = raw[5] if len(raw) > 5 else 0
        self.flags = raw[6] if len(raw) > 6 else 0
        # o corpo tem byte_count - 5 bytes (os 5 do cabeçalho MCTP)
        end = 2 + self.byte_count
        self.body = raw[7:end] if self.ok and end <= len(raw) else raw[7:]

    def __str__(self):
        if not self.ok:
            return f"resposta inválida ({len(self.raw)}b): {self.raw.hex(' ')}"
        msg_type = self.body[0] if self.body else None
        lines = [f"framing: cmd=0x{self.raw[0]:02x} len={self.byte_count} "
                 f"src_addr=0x{self.src_addr:02x} ver=0x{self.version:02x} "
                 f"eid {self.src_eid}->{self.dest_eid} flags=0x{self.flags:02x}"]
        lines.append(f"corpo ({len(self.body)}b): {self.body.hex(' ')}")
        if msg_type == MSG_TYPE_CONTROL and len(self.body) >= 4:
            cc = self.body[3]
            lines.append(f"  controle MCTP: cmd=0x{self.body[2]:02x} "
                         f"completion=0x{cc:02x} "
                         f"({COMPLETION_CODES.get(cc, '?')})")
            if len(self.body) > 4:
                lines.append(f"  dados: {self.body[4:].hex(' ')}")
        elif msg_type == MSG_TYPE_VENDOR_PCI and len(self.body) >= 4:
            vendor = (self.body[1] << 8) | self.body[2]
            lines.append(f"  vendor-defined: vendor=0x{vendor:04x} "
                         f"cmd=0x{self.body[3]:02x}")
            if len(self.body) > 4:
                lines.append(f"  dados: {self.body[4:].hex(' ')}")
        return "\n".join(lines)


def transact(bus: I2CBus, addr: int, body: bytes, read_len: int = 32,
             pad_to: int = 0, verbose: bool = True) -> Response:
    req = frame(body, pad_to)
    if verbose:
        print(f"  -> {req.hex(' ')}")
    bus.raw_write(addr, req)
    time.sleep(RESPONSE_DELAY_S)
    raw = bus.raw_read(addr, read_len, i_know_the_risk=True)
    if verbose:
        print(f"  <- {raw.hex(' ')}")
    return Response(raw)


# -------------------------------------------------------------------------

def self_test():
    """Confere byte a byte contra o pacote que o kernel monta em xe_amc.c."""
    got = frame(vendor_body(VENDOR_INTEL, 0x01), pad_to=8)
    want = bytes([0x0F, 0x0D, 0x8F, 0x01, 0x0C, 0x08, 0xC8,
                  0x7E, 0x80, 0x86, 0x01, 0x00, 0x00, 0x00, 0x00])
    print(f"  montado pelo tool: {got.hex(' ')}")
    print(f"  esperado (kernel): {want.hex(' ')}")
    if got == want:
        print("  ✔ idêntico ao AMC_GET_ALERT_REASON do xe_amc.c")
        return 0
    print("  ✘ DIVERGE")
    return 1


def cmd_discover(bus, addr, read_len):
    print("Descoberta MCTP (mensagens de controle, somente leitura)\n")
    probes = [
        (0x02, b"",         "Get Endpoint ID"),
        (0x04, bytes([0xFF]), "Get MCTP Version Support (base)"),
        (0x05, b"",         "Get Message Type Support"),
        (0x06, bytes([0x00]), "Get Vendor Defined Message Support (set 0)"),
        (0x03, b"",         "Get Endpoint UUID"),
    ]
    for iid, (cmd, data, label) in enumerate(probes):
        print(f"[0x{cmd:02x}] {label}")
        try:
            r = transact(bus, addr, ctrl_body(cmd, data, iid), read_len)
            print("  " + str(r).replace("\n", "\n  "))
        except OSError as e:
            print(f"  erro: {e}")
        print()


def cmd_alert_reason(bus, addr, read_len):
    print("Intel vendor-defined 0x01 — Get Alert Reason\n")
    r = transact(bus, addr, vendor_body(VENDOR_INTEL, 0x01), read_len, pad_to=8)
    print(str(r))
    # layout de amc_response: header(7) message(4) error(1) value(1)
    if len(r.body) >= 6 and r.body[0] == MSG_TYPE_VENDOR_PCI:
        err, val = r.body[4], r.body[5]
        print(f"\n  error = 0x{err:02x}"
              f"{'  (comando aceito)' if err == 0 else '  (REJEITADO)'}")
        print(f"  value = 0x{val:02x}  -> {ALERT_REASON.get(val, '?')}")


def parse_raw(spec: str) -> bytes:
    """'7e:8086:01' ou '7e:8086:01:aabbcc' -> corpo da mensagem."""
    parts = spec.split(":")
    if parts[0].lower() != "7e":
        raise ValueError("só mensagens vendor-defined (7e) por aqui")
    vendor = int(parts[1], 16)
    command = int(parts[2], 16)
    data = bytes.fromhex(parts[3]) if len(parts) > 3 else b""
    return vendor_body(vendor, command, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", choices=["discover", "alert-reason", "raw"])
    ap.add_argument("spec", nargs="?", help="para 'raw': 7e:VENDOR:CMD[:DADOS_HEX]")
    ap.add_argument("--self-test", action="store_true",
                    help="valida o empacotamento sem tocar no hardware")
    ap.add_argument("--len", type=int, default=32, dest="read_len",
                    help="bytes a ler na resposta (padrão 32; o kernel usa 13)")
    ap.add_argument("--pad", type=int, default=0,
                    help="preenche o corpo com zeros até N bytes")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.action and not os.environ.get("AMC_MCTP_EXPERIMENTAL"):
        print("Esta ferramenta nunca rodou no hardware e pode travar o barramento\n"
              "até o próximo ciclo de energia. Se entende o risco:\n"
              "  AMC_MCTP_EXPERIMENTAL=1 tools/amc-mctp.py " + args.action)
        return 2
    if not args.action:
        ap.print_help()
        return 2

    bus_n, addr = find_amc()
    print(f"AMC: /dev/i2c-{bus_n} addr 0x{addr:02x}\n")
    with I2CBus(bus_n) as bus:
        if args.action == "discover":
            cmd_discover(bus, addr, args.read_len)
        elif args.action == "alert-reason":
            cmd_alert_reason(bus, addr, args.read_len)
        elif args.action == "raw":
            if not args.spec:
                print("falta a spec, ex: raw 7e:8086:01")
                return 2
            r = transact(bus, addr, parse_raw(args.spec), args.read_len, args.pad)
            print(str(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
