"""Minimal ECMA-335 metadata reader.

Written because Fedora's `monodis` aborts on this assembly (an assertion in the
string heap), and installing the dotnet SDK just to run ILSpy would have been out
of proportion. It covers enough to answer the project's question: which bytes the
application builds before calling WriteReadAsync.

No external dependencies.
"""
from __future__ import annotations

import struct

# table -> list of columns. Types: 'u8','u16','u32', 'S' string, 'G' guid,
# 'B' blob, ('T', table) simple index, ('C', name) coded index.
TABLES = {
    0x00: ("Module", [("Generation", "u16"), ("Name", "S"), ("Mvid", "G"),
                      ("EncId", "G"), ("EncBaseId", "G")]),
    0x01: ("TypeRef", [("ResolutionScope", ("C", "ResolutionScope")),
                       ("Name", "S"), ("Namespace", "S")]),
    0x02: ("TypeDef", [("Flags", "u32"), ("Name", "S"), ("Namespace", "S"),
                       ("Extends", ("C", "TypeDefOrRef")),
                       ("FieldList", ("T", 0x04)), ("MethodList", ("T", 0x06))]),
    0x04: ("Field", [("Flags", "u16"), ("Name", "S"), ("Signature", "B")]),
    0x06: ("MethodDef", [("RVA", "u32"), ("ImplFlags", "u16"), ("Flags", "u16"),
                         ("Name", "S"), ("Signature", "B"),
                         ("ParamList", ("T", 0x08))]),
    0x08: ("Param", [("Flags", "u16"), ("Sequence", "u16"), ("Name", "S")]),
    0x09: ("InterfaceImpl", [("Class", ("T", 0x02)),
                             ("Interface", ("C", "TypeDefOrRef"))]),
    0x0A: ("MemberRef", [("Class", ("C", "MemberRefParent")), ("Name", "S"),
                         ("Signature", "B")]),
    0x0B: ("Constant", [("Type", "u8"), ("Pad", "u8"),
                        ("Parent", ("C", "HasConstant")), ("Value", "B")]),
    0x0C: ("CustomAttribute", [("Parent", ("C", "HasCustomAttribute")),
                               ("Type", ("C", "CustomAttributeType")),
                               ("Value", "B")]),
    0x0D: ("FieldMarshal", [("Parent", ("C", "HasFieldMarshal")),
                            ("NativeType", "B")]),
    0x0E: ("DeclSecurity", [("Action", "u16"),
                            ("Parent", ("C", "HasDeclSecurity")),
                            ("PermissionSet", "B")]),
    0x0F: ("ClassLayout", [("PackingSize", "u16"), ("ClassSize", "u32"),
                           ("Parent", ("T", 0x02))]),
    0x10: ("FieldLayout", [("Offset", "u32"), ("Field", ("T", 0x04))]),
    0x11: ("StandAloneSig", [("Signature", "B")]),
    0x12: ("EventMap", [("Parent", ("T", 0x02)), ("EventList", ("T", 0x14))]),
    0x14: ("Event", [("EventFlags", "u16"), ("Name", "S"),
                     ("EventType", ("C", "TypeDefOrRef"))]),
    0x15: ("PropertyMap", [("Parent", ("T", 0x02)),
                           ("PropertyList", ("T", 0x17))]),
    0x17: ("Property", [("Flags", "u16"), ("Name", "S"), ("Type", "B")]),
    0x18: ("MethodSemantics", [("Semantics", "u16"), ("Method", ("T", 0x06)),
                               ("Association", ("C", "HasSemantics"))]),
    0x19: ("MethodImpl", [("Class", ("T", 0x02)),
                          ("MethodBody", ("C", "MethodDefOrRef")),
                          ("MethodDeclaration", ("C", "MethodDefOrRef"))]),
    0x1A: ("ModuleRef", [("Name", "S")]),
    0x1B: ("TypeSpec", [("Signature", "B")]),
    0x1C: ("ImplMap", [("MappingFlags", "u16"),
                       ("MemberForwarded", ("C", "MemberForwarded")),
                       ("ImportName", "S"), ("ImportScope", ("T", 0x1A))]),
    0x1D: ("FieldRVA", [("RVA", "u32"), ("Field", ("T", 0x04))]),
    0x20: ("Assembly", [("HashAlgId", "u32"), ("Major", "u16"), ("Minor", "u16"),
                        ("Build", "u16"), ("Rev", "u16"), ("Flags", "u32"),
                        ("PublicKey", "B"), ("Name", "S"), ("Culture", "S")]),
    0x23: ("AssemblyRef", [("Major", "u16"), ("Minor", "u16"), ("Build", "u16"),
                           ("Rev", "u16"), ("Flags", "u32"),
                           ("PublicKeyOrToken", "B"), ("Name", "S"),
                           ("Culture", "S"), ("HashValue", "B")]),
    0x26: ("File", [("Flags", "u32"), ("Name", "S"), ("HashValue", "B")]),
    0x27: ("ExportedType", [("Flags", "u32"), ("TypeDefId", "u32"),
                            ("Name", "S"), ("Namespace", "S"),
                            ("Implementation", ("C", "Implementation"))]),
    0x28: ("ManifestResource", [("Offset", "u32"), ("Flags", "u32"),
                                ("Name", "S"),
                                ("Implementation", ("C", "Implementation"))]),
    0x29: ("NestedClass", [("NestedClass", ("T", 0x02)),
                           ("EnclosingClass", ("T", 0x02))]),
    0x2A: ("GenericParam", [("Number", "u16"), ("Flags", "u16"),
                            ("Owner", ("C", "TypeOrMethodDef")), ("Name", "S")]),
    0x2B: ("MethodSpec", [("Method", ("C", "MethodDefOrRef")),
                          ("Instantiation", "B")]),
    0x2C: ("GenericParamConstraint", [("Owner", ("T", 0x2A)),
                                      ("Constraint", ("C", "TypeDefOrRef"))]),
}

# coded index -> (tag bits, tables in tag order)
CODED = {
    "TypeDefOrRef": (2, [0x02, 0x01, 0x1B]),
    "HasConstant": (2, [0x04, 0x08, 0x17]),
    "HasCustomAttribute": (5, [0x06, 0x04, 0x01, 0x02, 0x08, 0x09, 0x0A, 0x11,
                               0x1A, 0x17, 0x14, 0x11, 0x14, 0x15, 0x17, 0x1A,
                               0x1B, 0x20, 0x23, 0x26, 0x27, 0x28, 0x2A]),
    "HasFieldMarshal": (1, [0x04, 0x08]),
    "HasDeclSecurity": (2, [0x02, 0x06, 0x20]),
    "MemberRefParent": (3, [0x02, 0x01, 0x1A, 0x06, 0x1B]),
    "HasSemantics": (1, [0x14, 0x17]),
    "MethodDefOrRef": (1, [0x06, 0x0A]),
    "MemberForwarded": (1, [0x04, 0x06]),
    "Implementation": (2, [0x26, 0x23, 0x27]),
    "CustomAttributeType": (3, [None, None, 0x06, 0x0A, None]),
    "ResolutionScope": (2, [0x00, 0x1A, 0x23, 0x01]),
    "TypeOrMethodDef": (1, [0x02, 0x06]),
}


class Assembly:
    def __init__(self, pe):
        self.pe = pe
        b = pe.b
        rva, _ = pe.dir(14)
        if not rva:
            raise ValueError("not a .NET assembly")
        o = pe.r2o(rva)
        md_rva, md_sz = struct.unpack_from("<II", b, o + 8)
        self.md = pe.r2o(md_rva)
        self._read_streams()
        self._read_tables()

    def _read_streams(self):
        b, md = self.pe.b, self.md
        vlen = struct.unpack_from("<I", b, md + 12)[0]
        q = md + 16 + vlen
        nstreams = struct.unpack_from("<H", b, q + 2)[0]
        q += 4
        self.streams = {}
        for _ in range(nstreams):
            off, size = struct.unpack_from("<II", b, q)
            q += 8
            name = b[q:b.find(b"\x00", q)].decode("latin1")
            q += (len(name) // 4 + 1) * 4
            self.streams[name] = (md + off, size)

    def _read_tables(self):
        b = self.pe.b
        t, _ = self.streams["#~"]
        heaps = b[t + 6]
        self.s_sz = 4 if heaps & 1 else 2
        self.g_sz = 4 if heaps & 2 else 2
        self.b_sz = 4 if heaps & 4 else 2
        valid = struct.unpack_from("<Q", b, t + 8)[0]
        present = [i for i in range(64) if valid >> i & 1]
        q = t + 24
        self.counts = {}
        for i in present:
            self.counts[i] = struct.unpack_from("<I", b, q)[0]
            q += 4
        # column widths depend on the row counts, so resolve them now
        self.rows = {}
        for i in present:
            if i not in TABLES:
                raise ValueError(f"unknown table 0x{i:02x}")
            name, cols = TABLES[i]
            widths = [self._col_size(c) for _, c in cols]
            self.rows[i] = (name, cols, widths, sum(widths), q)
            q += sum(widths) * self.counts[i]

    def _col_size(self, spec):
        if spec in ("u8",): return 1
        if spec in ("u16",): return 2
        if spec in ("u32",): return 4
        if spec == "S": return self.s_sz
        if spec == "G": return self.g_sz
        if spec == "B": return self.b_sz
        kind, arg = spec
        if kind == "T":
            return 4 if self.counts.get(arg, 0) >= 0x10000 else 2
        bits, tabs = CODED[arg]
        biggest = max((self.counts.get(t, 0) for t in tabs if t is not None),
                      default=0)
        return 4 if biggest >= (1 << (16 - bits)) else 2

    # -- acesso ------------------------------------------------------------

    def row(self, table, idx):
        """One 1-based row of the table, as a dict."""
        name, cols, widths, rowsz, base = self.rows[table]
        o = base + (idx - 1) * rowsz
        out = {}
        for (cname, spec), w in zip(cols, widths):
            v = int.from_bytes(self.pe.b[o:o + w], "little")
            out[cname] = v
            o += w
        return out

    def count(self, table):
        return self.counts.get(table, 0)

    def string(self, idx):
        base, size = self.streams["#Strings"]
        if idx >= size: return f"<str:0x{idx:x}!>"
        e = self.pe.b.find(b"\x00", base + idx)
        return self.pe.b[base + idx:e].decode("utf-8", "replace")

    def blob(self, idx):
        base, _ = self.streams["#Blob"]
        o = base + idx
        b = self.pe.b
        n = b[o]
        if n & 0x80 == 0: o += 1
        elif n & 0xC0 == 0x80:
            n = ((n & 0x3F) << 8) | b[o + 1]; o += 2
        else:
            n = ((n & 0x1F) << 24) | (b[o+1] << 16) | (b[o+2] << 8) | b[o+3]; o += 4
        return b[o:o + n]

    def userstring(self, idx):
        base, size = self.streams.get("#US", (0, 0))
        if not base or idx >= size: return None
        o = base + idx
        b = self.pe.b
        n = b[o]
        if n & 0x80 == 0: o += 1
        elif n & 0xC0 == 0x80:
            n = ((n & 0x3F) << 8) | b[o + 1]; o += 2
        else:
            n = ((n & 0x1F) << 24) | (b[o+1] << 16) | (b[o+2] << 8) | b[o+3]; o += 4
        return b[o:o + n - 1].decode("utf-16-le", "replace")

    # -- conveniences ------------------------------------------------------

    def type_of_method(self, method_idx):
        """Name of the type containing the MethodDef (1-based)."""
        best = None
        for i in range(1, self.count(0x02) + 1):
            td = self.row(0x02, i)
            if td["MethodList"] <= method_idx:
                best = td
            else:
                break
        if not best: return "?"
        ns = self.string(best["Namespace"])
        nm = self.string(best["Name"])
        return f"{ns}.{nm}" if ns else nm

    def methods(self):
        for i in range(1, self.count(0x06) + 1):
            m = self.row(0x06, i)
            yield i, self.type_of_method(i), self.string(m["Name"]), m["RVA"]

    def token_name(self, token):
        """Readable name for a metadata token (MethodDef/MemberRef/Field/...)."""
        tbl, idx = token >> 24, token & 0xFFFFFF
        if idx == 0: return f"token:0x{token:08x}"
        try:
            if tbl == 0x06:
                m = self.row(0x06, idx)
                return f"{self.type_of_method(idx)}::{self.string(m['Name'])}"
            if tbl == 0x0A:
                mr = self.row(0x0A, idx)
                return f"{self.string(mr['Name'])}"
            if tbl == 0x04:
                return f"field {self.string(self.row(0x04, idx)['Name'])}"
            if tbl == 0x01:
                tr = self.row(0x01, idx)
                ns, nm = self.string(tr["Namespace"]), self.string(tr["Name"])
                return f"{ns}.{nm}" if ns else nm
            if tbl == 0x02:
                td = self.row(0x02, idx)
                ns, nm = self.string(td["Namespace"]), self.string(td["Name"])
                return f"{ns}.{nm}" if ns else nm
            if tbl == 0x70:
                s = self.userstring(idx)
                return f'"{s}"' if s is not None else f"str:0x{idx:x}"
        except Exception:
            pass
        return f"token:0x{token:08x}"

    def method_body(self, rva):
        """(IL bytes, max stack) for the method at the given RVA."""
        if not rva: return b"", 0
        o = self.pe.r2o(rva)
        if o is None or o >= len(self.pe.b):
            return b"", 0
        b = self.pe.b
        fmt = b[o] & 3
        if fmt == 2:                      # tiny
            return b[o + 1:o + 1 + (b[o] >> 2)], 8
        flags, maxstack, codesize = struct.unpack_from("<HHI", b, o)
        hdrsize = (flags >> 12) * 4
        return b[o + hdrsize:o + hdrsize + codesize], maxstack
