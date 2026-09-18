#!/usr/bin/env python3
"""List and disassemble the methods of a .NET assembly.

    tools/dotnet-il.py LUMI.exe --list
    tools/dotnet-il.py LUMI.exe --dump 'SetLed.*Mode'
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotnet_meta import Assembly  # noqa: E402

# opcode -> (name, operand kind)
#   '' none | 'i1','u1','i2','i4','i8','r4','r8' immediate
#   'T' token | 'br1','br4' branch | 'sw' switch | 'var1','var2' variable
OPS = {
    0x00: ("nop", ""), 0x01: ("break", ""),
    0x02: ("ldarg.0", ""), 0x03: ("ldarg.1", ""), 0x04: ("ldarg.2", ""),
    0x05: ("ldarg.3", ""), 0x06: ("ldloc.0", ""), 0x07: ("ldloc.1", ""),
    0x08: ("ldloc.2", ""), 0x09: ("ldloc.3", ""), 0x0A: ("stloc.0", ""),
    0x0B: ("stloc.1", ""), 0x0C: ("stloc.2", ""), 0x0D: ("stloc.3", ""),
    0x0E: ("ldarg.s", "var1"), 0x0F: ("ldarga.s", "var1"),
    0x10: ("starg.s", "var1"), 0x11: ("ldloc.s", "var1"),
    0x12: ("ldloca.s", "var1"), 0x13: ("stloc.s", "var1"),
    0x14: ("ldnull", ""), 0x15: ("ldc.i4.m1", ""),
    **{0x16 + n: (f"ldc.i4.{n}", "") for n in range(9)},
    0x1F: ("ldc.i4.s", "i1"), 0x20: ("ldc.i4", "i4"), 0x21: ("ldc.i8", "i8"),
    0x22: ("ldc.r4", "r4"), 0x23: ("ldc.r8", "r8"),
    0x25: ("dup", ""), 0x26: ("pop", ""),
    0x27: ("jmp", "T"), 0x28: ("call", "T"), 0x29: ("calli", "T"),
    0x2A: ("ret", ""),
    0x2B: ("br.s", "br1"), 0x2C: ("brfalse.s", "br1"), 0x2D: ("brtrue.s", "br1"),
    0x2E: ("beq.s", "br1"), 0x2F: ("bge.s", "br1"), 0x30: ("bgt.s", "br1"),
    0x31: ("ble.s", "br1"), 0x32: ("blt.s", "br1"), 0x33: ("bne.un.s", "br1"),
    0x34: ("bge.un.s", "br1"), 0x35: ("bgt.un.s", "br1"),
    0x36: ("ble.un.s", "br1"), 0x37: ("blt.un.s", "br1"),
    0x38: ("br", "br4"), 0x39: ("brfalse", "br4"), 0x3A: ("brtrue", "br4"),
    0x3B: ("beq", "br4"), 0x3C: ("bge", "br4"), 0x3D: ("bgt", "br4"),
    0x3E: ("ble", "br4"), 0x3F: ("blt", "br4"), 0x40: ("bne.un", "br4"),
    0x41: ("bge.un", "br4"), 0x42: ("bgt.un", "br4"), 0x43: ("ble.un", "br4"),
    0x44: ("blt.un", "br4"), 0x45: ("switch", "sw"),
    0x46: ("ldind.i1", ""), 0x47: ("ldind.u1", ""), 0x48: ("ldind.i2", ""),
    0x49: ("ldind.u2", ""), 0x4A: ("ldind.i4", ""), 0x4B: ("ldind.u4", ""),
    0x4C: ("ldind.i8", ""), 0x4D: ("ldind.i", ""), 0x4E: ("ldind.r4", ""),
    0x4F: ("ldind.r8", ""), 0x50: ("ldind.ref", ""),
    0x51: ("stind.ref", ""), 0x52: ("stind.i1", ""), 0x53: ("stind.i2", ""),
    0x54: ("stind.i4", ""), 0x55: ("stind.i8", ""), 0x56: ("stind.r4", ""),
    0x57: ("stind.r8", ""),
    0x58: ("add", ""), 0x59: ("sub", ""), 0x5A: ("mul", ""), 0x5B: ("div", ""),
    0x5C: ("div.un", ""), 0x5D: ("rem", ""), 0x5E: ("rem.un", ""),
    0x5F: ("and", ""), 0x60: ("or", ""), 0x61: ("xor", ""),
    0x62: ("shl", ""), 0x63: ("shr", ""), 0x64: ("shr.un", ""),
    0x65: ("neg", ""), 0x66: ("not", ""),
    0x67: ("conv.i1", ""), 0x68: ("conv.i2", ""), 0x69: ("conv.i4", ""),
    0x6A: ("conv.i8", ""), 0x6B: ("conv.r4", ""), 0x6C: ("conv.r8", ""),
    0x6D: ("conv.u4", ""), 0x6E: ("conv.u8", ""),
    0x6F: ("callvirt", "T"), 0x70: ("cpobj", "T"), 0x71: ("ldobj", "T"),
    0x72: ("ldstr", "T"), 0x73: ("newobj", "T"), 0x74: ("castclass", "T"),
    0x75: ("isinst", "T"), 0x76: ("conv.r.un", ""),
    0x79: ("unbox", "T"), 0x7A: ("throw", ""), 0x7B: ("ldfld", "T"),
    0x7C: ("ldflda", "T"), 0x7D: ("stfld", "T"), 0x7E: ("ldsfld", "T"),
    0x7F: ("ldsflda", "T"), 0x80: ("stsfld", "T"), 0x81: ("stobj", "T"),
    0x8C: ("box", "T"), 0x8D: ("newarr", "T"), 0x8E: ("ldlen", ""),
    0x8F: ("ldelema", "T"), 0x90: ("ldelem.i1", ""), 0x91: ("ldelem.u1", ""),
    0x92: ("ldelem.i2", ""), 0x93: ("ldelem.u2", ""), 0x94: ("ldelem.i4", ""),
    0x95: ("ldelem.u4", ""), 0x96: ("ldelem.i8", ""), 0x98: ("ldelem.r4", ""),
    0x99: ("ldelem.r8", ""), 0x9A: ("ldelem.ref", ""),
    0x9C: ("stelem.i1", ""), 0x9D: ("stelem.i2", ""), 0x9E: ("stelem.i4", ""),
    0x9F: ("stelem.i8", ""), 0xA0: ("stelem.r4", ""), 0xA1: ("stelem.r8", ""),
    0xA2: ("stelem.ref", ""), 0xA3: ("ldelem", "T"), 0xA4: ("stelem", "T"),
    0xA5: ("unbox.any", "T"),
    0xC2: ("refanyval", "T"), 0xC6: ("mkrefany", "T"), 0xD0: ("ldtoken", "T"),
    0xD1: ("conv.u2", ""), 0xD2: ("conv.u1", ""), 0xD3: ("conv.i", ""),
    0xDD: ("leave", "br4"), 0xDE: ("leave.s", "br1"),
    0xE0: ("conv.u", ""),
}
OPS_FE = {
    0x01: ("ceq", ""), 0x02: ("cgt", ""), 0x03: ("cgt.un", ""),
    0x04: ("clt", ""), 0x05: ("clt.un", ""), 0x06: ("ldftn", "T"),
    0x07: ("ldvirtftn", "T"), 0x09: ("ldarg", "var2"), 0x0B: ("starg", "var2"),
    0x0C: ("ldloc", "var2"), 0x0D: ("ldloca", "var2"), 0x0E: ("stloc", "var2"),
    0x0F: ("localloc", ""), 0x11: ("endfilter", ""), 0x12: ("unaligned.", "u1"),
    0x13: ("volatile.", ""), 0x14: ("tail.", ""), 0x15: ("initobj", "T"),
    0x16: ("constrained.", "T"), 0x17: ("cpblk", ""), 0x18: ("initblk", ""),
    0x1A: ("rethrow", ""), 0x1C: ("sizeof", "T"), 0x1D: ("refanytype", ""),
}


def disasm(asm: Assembly, il: bytes) -> list[str]:
    out, i = [], 0
    while i < len(il):
        start = i
        op = il[i]
        i += 1
        if op == 0xFE:
            name, kind = OPS_FE.get(il[i], (f"fe{il[i]:02x}", ""))
            i += 1
        else:
            name, kind = OPS.get(op, (f".byte 0x{op:02x}", ""))
        arg = ""
        if kind == "i1":
            arg = str(struct.unpack_from("<b", il, i)[0]); i += 1
        elif kind in ("u1", "var1"):
            arg = str(il[i]); i += 1
        elif kind == "var2":
            arg = str(struct.unpack_from("<H", il, i)[0]); i += 2
        elif kind == "i4":
            v = struct.unpack_from("<i", il, i)[0]
            arg = f"{v} (0x{v & 0xFFFFFFFF:x})"; i += 4
        elif kind == "i8":
            arg = str(struct.unpack_from("<q", il, i)[0]); i += 8
        elif kind == "r4":
            arg = str(struct.unpack_from("<f", il, i)[0]); i += 4
        elif kind == "r8":
            arg = str(struct.unpack_from("<d", il, i)[0]); i += 8
        elif kind == "T":
            tok = struct.unpack_from("<I", il, i)[0]; i += 4
            arg = asm.token_name(tok)
        elif kind == "br1":
            d = struct.unpack_from("<b", il, i)[0]; i += 1
            arg = f"IL_{i + d:04x}"
        elif kind == "br4":
            d = struct.unpack_from("<i", il, i)[0]; i += 4
            arg = f"IL_{i + d:04x}"
        elif kind == "sw":
            n = struct.unpack_from("<I", il, i)[0]; i += 4
            tgts = []
            for _ in range(n):
                d = struct.unpack_from("<i", il, i)[0]; i += 4
                tgts.append(d)
            base = i
            arg = ", ".join(f"IL_{base + d:04x}" for d in tgts)
        out.append(f"  IL_{start:04x}:  {name:<14} {arg}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("assembly")
    ap.add_argument("--list", action="store_true", help="list the methods")
    ap.add_argument("--dump", metavar="REGEX", help="disassemble matching methods")
    ap.add_argument("--type", metavar="REGEX", help="restrict to matching types")
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from peinfo import PE  # noqa: E402  (sits next to this file)

    asm = Assembly(PE(args.assembly))
    tre = re.compile(args.type, re.I) if args.type else None

    for idx, typ, name, rva in asm.methods():
        if tre and not tre.search(typ):
            continue
        if args.list:
            print(f"{typ}::{name}  rva=0x{rva:x}")
        if args.dump and re.search(args.dump, name, re.I):
            il, _ = asm.method_body(rva)
            print(f"\n=== {typ}::{name}  ({len(il)} bytes of IL) ===")
            print("\n".join(disasm(asm, il)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
