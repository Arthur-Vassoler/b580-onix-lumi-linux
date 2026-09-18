#!/usr/bin/env python3
"""Extrai os binários de dentro do instalador LUMI ARGB da ONIX.

O instalador é Inno Setup 6.3, que o innoextract 1.9 (o do Fedora) não abre e o
7-Zip não reconhece. Mas não é preciso interpretar os cabeçalhos do Inno: os
arquivos estão num único stream LZMA1 sólido, marcado por `zlb\\x1a` seguido das
5 propriedades. Descomprime o stream e recorta os PEs pelo cabeçalho.

    tools/extract-lumi.py LUMISetupV2.1.exe -o /destino

O instalador vem de https://cdn.onixsys.com/assets/downloads/LUMISetupV2.1.zip
(página oficial: https://onixsys.com/download-en/). Não é redistribuído aqui.
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
        raise SystemExit("assinatura 'zlb' não encontrada — instalador diferente?")
    props = installer[off + 4:off + 9]
    # LZMA1 sem campo de tamanho; FORMAT_ALONE quer 13 bytes de cabeçalho
    header = props + (0xFFFFFFFFFFFFFFFF).to_bytes(8, "little")
    dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
    try:
        return dec.decompress(header + installer[off + 9:])
    except lzma.LZMAError as exc:
        raise SystemExit(f"falha ao descomprimir: {exc}")


def pe_disk_size(blob: bytes, off: int):
    """Tamanho em disco de um PE em `off`, ou None se não for um PE válido."""
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
    """Nome do arquivo a partir do caminho do PDB no CodeView (RSDS)."""
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
    ap.add_argument("installer", help="LUMISetupV2.1.exe (descompactado do .zip)")
    ap.add_argument("-o", "--out", default="lumi-extracted", help="diretório de saída")
    ap.add_argument("--keep-payload", action="store_true",
                    help="grava também o blob descomprimido inteiro")
    args = ap.parse_args()

    blob = decompress(open(args.installer, "rb").read())
    print(f"payload descomprimido: {len(blob) / 1048576:.1f} MiB")

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
            # PEs distintos podem compartilhar nome de PDB (ex.: DriverInstall)
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
    print(f"\n{found} executáveis extraídos em {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
