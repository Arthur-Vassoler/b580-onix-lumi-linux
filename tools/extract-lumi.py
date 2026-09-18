#!/usr/bin/env python3
"""Extract the binaries from inside ONIX's LUMI ARGB installer.

The installer is Inno Setup 6.3, which innoextract 1.9 (the version Fedora ships)
will not open and 7-Zip does not recognise. There is no need to parse Inno's
headers though: the files sit in a single solid LZMA1 stream, marked by
`zlb\\x1a` followed by the 5 property bytes. Decompress the stream and carve the
PE files on their headers.

    tools/extract-lumi.py LUMISetupV2.1.exe -o /destino

The installer comes from https://cdn.onixsys.com/assets/downloads/LUMISetupV2.1.zip
(official page: https://onixsys.com/download-en/). It is not redistributed here.
"""
from __future__ import annotations

import argparse
import lzma
import os
import struct
import sys


def decompress(installer: bytes) -> bytes:
    off = installer.find(b"zlb\x1a")
    if off < 0:
        raise SystemExit("no 'zlb' signature found - a different installer?")
    props = installer[off + 4:off + 9]
    # LZMA1 with no size field; FORMAT_ALONE wants a 13 byte header
    header = props + (0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    try:
        return dec.decompress(header + installer[off + 9:])
    except lzma.LZMAError as exc:
        raise SystemExit(f"decompression failed: {exc}")


def pe_disk_size(blob: bytes, off: int):
    """On-disk size of the PE at `off`, or None if it is not a valid PE."""
    if blob[off:off + 2] != b"MZ" or off + 0x40 > len(blob):
        return None
    lfanew = struct.unpack_from("<I", blob, off + 0x3C)[0]
    if not 0 < lfanew < 0x1000 or off + lfanew + 24 > len(blob):
        return None
    p = off + lfanew
    if blob[p:p + 4] != b"PE\x00\x00":
        return None
    nsec = struct.unpack_from("<H", blob, p + 6)[0]
    optsz = struct.unpack_from("<H", blob, p + 20)[0]
    sect = p + 24 + optsz
    end = 0
    for i in range(nsec):
        raw_size, raw_ptr = struct.unpack_from("<II", blob, sect + i * 40 + 16)
        end = max(end, raw_ptr + raw_size)
    return end if 0 < end <= len(blob) - off else None


def pdb_name(pe: bytes) -> str | None:
    """File name taken from the PDB path in the CodeView (RSDS) record."""
    i = pe.find(b"RSDS")
    if i < 0:
        return None
    tail = pe[i + 24:i + 24 + 260].split(b"\x00")[0]
    if not tail:
        return None
    base = tail.decode("latin1").replace("\\", "/").rsplit("/", 1)[-1]
    return base[:-4] if base.lower().endswith(".pdb") else base


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("installer", help="LUMISetupV2.1.exe, unpacked from the .zip")
    ap.add_argument("-o", "--out", default="lumi-extracted", help="output directory")
    ap.add_argument("--keep-payload", action="store_true",
                    help="also write out the whole decompressed blob")
    args = ap.parse_args()

    blob = decompress(open(args.installer, "rb").read())
    print(f"decompressed payload: {len(blob) / 1048576:.1f} MiB")

    os.makedirs(args.out, exist_ok=True)
    if args.keep_payload:
        open(os.path.join(args.out, "payload.bin"), "wb").write(blob)

    found = 0
    i = 0
    used = set()
    while True:
        i = blob.find(b"MZ", i)
        if i < 0:
            break
        size = pe_disk_size(blob, i)
        if size:
            name = pdb_name(blob[i:i + size]) or f"unknown_{i:08x}"
            # distinct PEs can share a PDB name (DriverInstall, for instance)
            stem, dot, ext = name.rpartition(".")
            n, cand = 1, name
            while cand in used:
                n += 1
                cand = f"{stem}_{n}{dot}{ext}" if dot else f"{name}_{n}"
            used.add(cand)
            open(os.path.join(args.out, cand), "wb").write(blob[i:i + size])
            print(f"  0x{i:08x}  {size:>9}b  {cand}")
            found += 1
        i += 2
    print(f"\n{found} executables extracted into {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
