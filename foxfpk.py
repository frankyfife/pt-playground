"""Fox Engine FPK / FPKD container reader + writer (P.T. / CUSA01127, PS4).

The container itself is wrapped in the usual Fox LCG crypto (magic 0xA0F8EFE6),
so decrypt with foxlua/foxfast first -- load()/save() below do that for you.

Layout (little endian):
  0x00 char[10] "foxfpk"|"foxfpkd" + "ps4"
  0x0a u32      total file size
  0x20 u32      version (2)
  0x24 u32      entry count
  0x28 u32      reference count      (0 in every P.T. container)
  0x2c u32      reference table off  (0 in every P.T. container)
  0x30 ...      entry table, 48 bytes each:
                  +0x00 u64 data offset
                  +0x08 u64 data size
                  +0x10 u64 path offset
                  +0x18 u64 path length (excluding the NUL terminator)
                  +0x20 md5[16]  -- MD5 of the *path*, not of the data
  then           NUL-terminated path strings, padded to 16
  then           entry payloads, each padded to 16

Because the hash covers the path only, payloads may be replaced with data of a
different length; just rebuild with save().

  python foxfpk.py list    <file.fpkd> [substring]
  python foxfpk.py extract <file.fpkd> <outdir>
  python foxfpk.py replace <in.fpkd> <out.fpkd> <vpath>=<file> [...]
"""
import struct, hashlib, sys, os

HDR = 0x30
ENT = 48


def _align(n, a=16):
    return (n + a - 1) & ~(a - 1)


class Fpk:
    def __init__(self, blob):
        assert blob[:6] == b'foxfpk', 'not an FPK (decrypt first?)'
        self.magic = blob[:10]
        self.kind = 'fpkd' if blob[6:7] == b'd' else 'fpk'
        self.total = struct.unpack_from('<I', blob, 0x0a)[0]
        self.ver, self.count, self.refcount, self.refoff = \
            struct.unpack_from('<IIII', blob, 0x20)
        self.head = blob[:HDR]
        self.blob = blob
        self.ents = []
        for i in range(self.count):
            o = HDR + i * ENT
            doff, dsz, poff, plen = struct.unpack_from('<QQQQ', blob, o)
            self.ents.append({
                'path': blob[poff:poff + plen].decode('utf8'),
                'data': blob[doff:doff + dsz],
                'md5': blob[o + 0x20:o + 0x30],
            })

    def index_of(self, vpath):
        for i, e in enumerate(self.ents):
            if e['path'].lower() == vpath.lower():
                return i
        raise KeyError(vpath)

    def get(self, vpath):
        return self.ents[self.index_of(vpath)]['data']

    def replace(self, vpath, data):
        self.ents[self.index_of(vpath)]['data'] = data

    def add(self, vpath, data):
        self.ents.append({'path': vpath, 'data': data,
                          'md5': hashlib.md5(vpath.encode()).digest()})

    def by_name(self, sub):
        return [e for e in self.ents if sub.lower() in e['path'].lower()]

    def build(self):
        n = len(self.ents)
        paths = bytearray()
        poffs = []
        base = HDR + n * ENT
        for e in self.ents:
            poffs.append(base + len(paths))
            paths += e['path'].encode() + b'\0'
        pad = _align(base + len(paths)) - (base + len(paths))
        paths += b'\0' * pad
        doff = base + len(paths)
        table, body = bytearray(), bytearray()
        for e, po in zip(self.ents, poffs):
            d = e['data']
            table += struct.pack('<QQQQ', doff + len(body), len(d), po,
                                 len(e['path'].encode()))
            table += hashlib.md5(e['path'].encode()).digest()
            body += d + b'\0' * (_align(len(d)) - len(d))
        total = doff + len(body)
        head = bytearray(self.head)
        struct.pack_into('<I', head, 0x0a, total)
        struct.pack_into('<IIII', head, 0x20, self.ver, n, self.refcount, self.refoff)
        return bytes(head) + bytes(table) + bytes(paths) + bytes(body)


def load(path):
    import foxfast
    return Fpk(foxfast.decrypt(open(path, 'rb').read()))


def loadblob(blob):
    import foxfast
    return Fpk(foxfast.decrypt(blob))


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    cmd = sys.argv[1]
    a = load(sys.argv[2])
    if cmd == 'list':
        pat = sys.argv[3].lower() if len(sys.argv) > 3 else ''
        print('%s  entries=%d  total=%d' % (a.kind, a.count, a.total))
        for i, e in enumerate(a.ents):
            if pat and pat not in e['path'].lower():
                continue
            print('%4d %9d  %s' % (i, len(e['data']), e['path']))
    elif cmd == 'extract':
        out = sys.argv[3]
        import foxfast
        for e in a.ents:
            dst = os.path.join(out, e['path'].lstrip('/').replace('/', os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(foxfast.decrypt(e['data']))
        print('extracted', len(a.ents), '->', out)
    elif cmd == 'replace':
        import foxfast
        for spec in sys.argv[4:]:
            vp, _, fn = spec.partition('=')
            a.replace(vp, open(fn, 'rb').read())
            print('replaced', vp)
        open(sys.argv[3], 'wb').write(foxfast.encrypt(a.build()))
        print('wrote', sys.argv[3])
