"""Minimal PSARC (v1.4, zlib) reader/writer for P.T. (CUSA01127) chunk1.psarc.

  python psarc.py list   <archive>
  python psarc.py extract <archive> <outdir> [glob]
  python psarc.py replace <archive> <out_archive> <vpath>=<file> [<vpath>=<file> ...]

Entry 0 is the filename manifest; entry i+1 belongs to name i.
"""
import hashlib
import struct, zlib, sys, os, fnmatch

MAGIC = b'PSAR'


class Psarc:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        hdr = self.f.read(32)
        assert hdr[:4] == MAGIC, 'not a PSARC'
        self.version = struct.unpack('>I', hdr[4:8])[0]
        self.compid = hdr[8:12]
        tocsize, self.esz, n, self.blocksize, self.flags = struct.unpack('>IIIII', hdr[12:32])
        toc = self.f.read(tocsize - 32)
        self.ents = []
        for i in range(n):
            e = toc[i * 30:(i + 1) * 30]
            self.ents.append([e[:16],
                              struct.unpack('>I', e[16:20])[0],
                              int.from_bytes(e[20:25], 'big'),
                              int.from_bytes(e[25:30], 'big')])
        rest = toc[n * 30:]
        self.bsz = 2 if self.blocksize <= 0x10000 else (3 if self.blocksize <= 0x1000000 else 4)
        self.blocks = [int.from_bytes(rest[i * self.bsz:(i + 1) * self.bsz], 'big')
                       for i in range(len(rest) // self.bsz)]
        self.names = [x for x in self.read(0).decode('utf8', 'replace')
                      .replace('\r', '').split('\n') if x.strip()]

    def read(self, i):
        """Einen Eintrag entpacken.

        Ob ein Block gepackt ist, wird am KOPF entschieden, nicht durch
        Probieren. Die alte Fassung rief erst `zlib.decompress` und nahm den
        Block bei einer Ausnahme roh -- das geht schief, sobald rohe Daten
        zufaellig wie ein gueltiger zlib-Strom aussehen.

        Gemessen am 16.09.2026 an einem selbst gebauten Archiv mit 151 MB
        eingebetteter Bilddaten: von 1639 roh abgelegten Bloecken liess sich
        GENAU EINER als zlib entpacken. Ab dieser Stelle war alles dahinter
        verschoben, und der Eintrag 350 begann nicht mehr mit "FTEX" -- ein
        Fehler, der wie ein kaputter Bau aussieht und keiner war.

        Die Regel: Blockgroesse 0 heisst roh in voller Blockgroesse. Sonst
        gepackt, wenn die Daten mit 0x78 beginnen (zlib), andernfalls roh.
        """
        _, bidx, usz, off = self.ents[i]
        self.f.seek(off)
        out = bytearray()
        b = bidx
        while len(out) < usz and b < len(self.blocks):
            bl = self.blocks[b]; b += 1
            raw = self.f.read(bl if bl else self.blocksize)
            if bl == 0 or raw[:1] != b'\x78':
                out += raw
                continue
            try:
                out += zlib.decompress(raw)
            except zlib.error:
                out += raw
        return bytes(out[:usz])

    def index_of(self, vpath):
        want = vpath.lower().lstrip('/')
        for i, nm in enumerate(self.names):
            if nm.lower().lstrip('/') == want:
                return i + 1
        raise KeyError(vpath)


def _raw_blocks(src, i):
    """Compressed block payload of entry i, copied verbatim (no recompression)."""
    _, bidx, usz, off = src.ents[i]
    src.f.seek(off)
    sizes, body, got, b = [], bytearray(), 0, bidx
    while got < usz and b < len(src.blocks):
        bl = src.blocks[b]; b += 1
        raw = src.f.read(bl if bl else src.blocksize)
        sizes.append(bl)
        body += raw
        try:
            got += len(zlib.decompress(raw))
        except zlib.error:
            got += len(raw)
    return bytes(body), sizes, usz


def _pack(data, blocksize):
    body, sizes = bytearray(), []
    for p in range(0, max(len(data), 1), blocksize):
        raw = data[p:p + blocksize]
        comp = zlib.compress(raw, 9)
        if len(comp) < len(raw):
            body += comp
            sizes.append(len(comp))
        else:
            body += raw
            sizes.append(0 if len(raw) == blocksize else len(raw))
    return bytes(body), sizes


def build(src, dstpath, overrides, neu=None):
    """overrides: {entry_index: bytes}. Untouched entries keep their original blocks.

    `neu`: [(name, bytes), ...] -- zusaetzliche Eintraege. Sie werden HINTEN
    angehaengt, und Eintrag 0 (die Namensliste) wird entsprechend neu
    geschrieben. Die Reihenfolge muss uebereinstimmen: names[i] gehoert zu
    ents[i+1].

    Das 16-Byte-Feld im Verzeichnis ist ein MD5 ueber den Namen, genau wie er
    in der Namensliste steht -- am Fix-Pack-Archiv geprueft, 400 von 400
    Treffern. Wer es falsch berechnet, legt einen Eintrag an, den der Lader
    nicht findet, und das sieht im Spiel aus wie eine fehlende Textur.
    """
    if neu:
        overrides = dict(overrides or {})
        alle = list(src.names) + [name for name, _ in neu]
        overrides[0] = ('\n'.join(alle) + '\n').encode('utf8')
    n = len(src.ents)
    blocktable, chunks, entries = [], [], []
    offset = 0
    for i in range(n):
        if i in overrides:
            body, sizes = _pack(overrides[i], src.blocksize)
            usz = len(overrides[i])
        else:
            body, sizes, usz = _raw_blocks(src, i)
        entries.append((src.ents[i][0], len(blocktable), usz, offset))
        blocktable += sizes
        chunks.append(body)
        offset += len(body)

    for name, data in (neu or []):
        body, sizes = _pack(data, src.blocksize)
        entries.append((hashlib.md5(name.encode('utf8')).digest(),
                        len(blocktable), len(data), offset))
        blocktable += sizes
        chunks.append(body)
        offset += len(body)
        n += 1

    tocsize = 32 + n * 30 + len(blocktable) * src.bsz
    with open(dstpath, 'wb') as g:
        g.write(MAGIC + struct.pack('>I', src.version) + src.compid)
        g.write(struct.pack('>IIIII', tocsize, 30, n, src.blocksize, src.flags))
        for md5, bidx, usz, off in entries:
            g.write(md5 + struct.pack('>I', bidx)
                    + usz.to_bytes(5, 'big') + (off + tocsize).to_bytes(5, 'big'))
        for b in blocktable:
            g.write(b.to_bytes(src.bsz, 'big'))
        for c in chunks:
            g.write(c)
    return dstpath


def main():
    cmd = sys.argv[1]
    a = Psarc(sys.argv[2])
    if cmd == 'list':
        for i, nm in enumerate(a.names):
            print('%5d %10d  %s' % (i + 1, a.ents[i + 1][2], nm))
    elif cmd == 'extract':
        outdir, pat = sys.argv[3], (sys.argv[4] if len(sys.argv) > 4 else '*')
        for i, nm in enumerate(a.names):
            if not fnmatch.fnmatch(nm.lower(), pat.lower()):
                continue
            dst = os.path.join(outdir, nm.lstrip('/').replace('/', os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, 'wb').write(a.read(i + 1))
            print('->', nm)
    elif cmd == 'replace':
        out = sys.argv[3]
        ov = {}
        for spec in sys.argv[4:]:
            vpath, _, fn = spec.partition('=')
            idx = a.index_of(vpath)
            ov[idx] = open(fn, 'rb').read()
            print('replacing [%d] %s  <- %s (%d bytes)' % (idx, vpath, fn, len(ov[idx])))
        build(a, out, ov)
        print('wrote', out, os.path.getsize(out), 'bytes')


if __name__ == '__main__':
    main()
