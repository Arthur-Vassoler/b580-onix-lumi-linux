import struct, sys

class PE:
    def __init__(self, path):
        self.b = open(path, 'rb').read()
        b = self.b
        e = struct.unpack_from('<I', b, 0x3c)[0]
        self.peoff = e
        self.nsec = struct.unpack_from('<H', b, e + 6)[0]
        self.optsz = struct.unpack_from('<H', b, e + 20)[0]
        opt = e + 24
        self.magic = struct.unpack_from('<H', b, opt)[0]
        self.dd = opt + (112 if self.magic == 0x20b else 96)
        st = opt + self.optsz
        self.secs = []
        for i in range(self.nsec):
            nm = b[st + i*40: st + i*40 + 8].rstrip(b'\x00').decode('latin1')
            vs, va, rs, rp = struct.unpack_from('<IIII', b, st + i*40 + 8)
            self.secs.append((nm, va, vs, rp, rs))

    def dir(self, idx):
        return struct.unpack_from('<II', self.b, self.dd + idx*8)

    def r2o(self, rva):
        for nm, va, vs, rp, rs in self.secs:
            if va <= rva < va + max(vs, rs):
                return rp + (rva - va)
        return None

    def cstr(self, off):
        end = self.b.find(b'\x00', off)
        return self.b[off:end].decode('latin1')

    def exports(self):
        rva, size = self.dir(0)
        if not rva: return None, []
        o = self.r2o(rva)
        (_, _, _, _, name_rva, base, nfunc, nname,
         af, an, ao) = struct.unpack_from('<IIHHIIIIIII', self.b, o)
        dll = self.cstr(self.r2o(name_rva))
        out = []
        for i in range(nname):
            nr = struct.unpack_from('<I', self.b, self.r2o(an) + i*4)[0]
            nm = self.cstr(self.r2o(nr))
            ordn = struct.unpack_from('<H', self.b, self.r2o(ao) + i*2)[0]
            fr = struct.unpack_from('<I', self.b, self.r2o(af) + ordn*4)[0]
            out.append((nm, base + ordn, fr))
        return dll, out

    def imports(self):
        rva, size = self.dir(1)
        if not rva: return []
        o = self.r2o(rva); res = []
        while True:
            oft, ts, fc, name_rva, first = struct.unpack_from('<IIIII', self.b, o)
            if not name_rva: break
            dll = self.cstr(self.r2o(name_rva))
            funcs = []
            t = self.r2o(oft or first)
            if t:
                while True:
                    v = struct.unpack_from('<Q' if self.magic == 0x20b else '<I', self.b, t)[0]
                    if not v: break
                    if not (v >> (63 if self.magic == 0x20b else 31)):
                        off = self.r2o(v & 0x7fffffff)
                        if off: funcs.append(self.cstr(off + 2))
                    t += 8 if self.magic == 0x20b else 4
            res.append((dll, funcs)); o += 20
        return res

if __name__ == '__main__':
    p = PE(sys.argv[1])
    dll, exps = p.exports()
    print(f"== {sys.argv[1]} ==")
    print("seções:", ", ".join(f"{n}(0x{va:x},{vs}b)" for n, va, vs, rp, rs in p.secs))
    if exports := exps:
        print(f"\nexports de {dll} ({len(exports)}):")
        for nm, ordn, fr in exports:
            print(f"  {nm:<32} ord={ordn:<4} rva=0x{fr:x}")
    print("\nimports:")
    for d, fs in p.imports():
        print(f"  {d}: {', '.join(fs[:18])}{' ...' if len(fs) > 18 else ''}")
