"""FTEX lesen -- P.T.s Texturkoepfe aufschluesseln und Nutzdaten herausholen.

Woher die Feldlage stammt
-------------------------
Empirisch an **allen 1061 Texturen** aus texture.qar bestimmt, nicht geraten:
die Kopffelder wurden gegen die tatsaechlichen Maße, Mip-Zahlen und
Streamgroessen gegengerechnet.

    0x00  char[4]  'FTEX'
    0x04  float    Version (durchgaengig 2.03)
    0x08  u8       Pixelformat   2 -> ~0.5 Byte/Pixel (BC1-artig)
                                 4 -> ~1.0 Byte/Pixel (BC3/BC5-artig)
                                 0 -> unkomprimiert (nur 3 Stueck, Tiefe 16)
    0x0a  u16      Breite
    0x0c  u16      Hoehe
    0x0e  u16      Tiefe         (1, ausser 2 Cubemaps mit 16)
    0x10  u8       Mip-Anzahl    (6..11 typisch)
    0x20  u8       Anzahl der zugehoerigen .ftexs  <- 1061/1061 bestaetigt

Das Feld 0x20 ist das wichtigste: wer Mip-Streams weglaesst und es stehen
laesst, hinterlaesst Verweise ins Leere. `qarbuild.py` zieht es deshalb mit.

Die Nutzdaten sind **zlib-blockweise komprimiert, NICHT GPU-gekachelt** --
Aufbau der Mip- und Blocktabellen weiter unten. Nach dem Entpacken ist es
schlichtes BC1/BC3, das sich direkt als DDS an PIL uebergeben laesst.

Stream 1 haelt die KLEINSTEN Stufen, der hoechste Stream Mip 0.

    python ftex.py --list [n]        Inventar aus dem qar (mit Namen, wo bekannt)
    python ftex.py --stats           Verteilung nach Format und Groesse
    python ftex.py --dump <dir> [n]  Koepfe + Streams roh herausschreiben
    python ftex.py --png <dir> [n]   als PNG ausgeben (--mip N fuer kleinere Stufe)

Quelle ist die Sicherung `bak\\texture.qar`, sonst das aktive Archiv.
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths
import qarread
from foxpath import ext_code, path_code

M50 = (1 << 50) - 1
FMT_HINT = {0: 'unkomprimiert', 2: 'BC1-artig (~0.5 B/px)',
            4: 'BC3/BC5-artig (~1.0 B/px)'}


class Header:
    SIZE = 0x24

    def __init__(self, b):
        self.ok = len(b) >= self.SIZE and b[:4] == b'FTEX'
        if not self.ok:
            return
        self.version = struct.unpack_from('<f', b, 4)[0]
        self.fmt = b[8]
        self.w, self.h, self.depth = struct.unpack_from('<3H', b, 0xa)
        self.mips = b[0x10]
        self.nstreams = b[0x20]

    def __str__(self):
        return ('%dx%d%s  Format %d %-24s %2d Mips  %d Streams'
                % (self.w, self.h, '' if self.depth == 1 else 'x%d' % self.depth,
                   self.fmt, '(%s)' % FMT_HINT.get(self.fmt, '?'),
                   self.mips, self.nstreams))


def source():
    bak = os.path.join(os.path.dirname(qarread.QAR), 'bak', 'texture.qar')
    return bak if os.path.exists(bak) else qarread.QAR


def textures(q):
    """{pfadhash: {mipindex: (offset, groesse)}} -- 0 ist der .ftex-Kopf."""
    lvl = {ext_code('ftex'): 0}
    for i in range(1, 7):
        lvl[ext_code('%d.ftexs' % i)] = i
    out = collections.defaultdict(dict)
    for h, o, s in q.ents:
        i = lvl.get(h >> 51)
        if i is not None:
            out[h & M50][i] = (o, s)
    return out


# Wortliste echter Fox-Pfade aus dem "File Monolith"-Werkzeugsatz. Damit
# lassen sich ALLE 1061 Texturen benennen (100 %, nachgerechnet) -- aus dem
# psarc allein waren es nur 264. Fehlt die Datei, faellt names() auf das psarc
# zurueck.
# Standardmaessig neben den Skripten gesucht; ein anderer Ort laesst sich
# in playground.json eintragen (Schluessel "qar_dictionary").
DICT = ptpaths.QAR_DICT


def names(full=False):
    """Pfadhash -> Name. Mit dem Woerterbuch vollstaendig, sonst nur psarc."""
    from foxpath import raw_path_hash_code
    out = {}
    if os.path.exists(DICT):
        with open(DICT, encoding='utf8', errors='replace') as fh:
            for line in fh:
                q = line.strip()
                if not q:
                    continue
                # /Assets/... entspricht der Archivform as/...; gehasht wird
                # der Pfad OHNE Praefix und ohne Endung.
                base = q[len('/Assets/'):] if q.startswith('/Assets/')                     else q.lstrip('/')
                out[raw_path_hash_code(base) & M50] = q if full                     else q.split('/')[-1]
    if out:
        return out
    try:
        import psarc
        a = psarc.Psarc(os.path.join(os.path.dirname(qarread.QAR),
                                     'chunk1.orig.psarc'))
    except Exception:
        return {}
    for n in a.names:
        if n.lower().endswith('.ftex'):
            for uf in (False, True):
                out[path_code(n, uf) & M50] = n.split('/')[-1]
    return out


def head_of(q, tex, key):
    o, s = tex[key][0]
    q.f.seek(o)
    return Header(q.f.read(min(s, Header.SIZE)))


def main():
    a = sys.argv[1:]
    q = qarread.Qar(source())
    tex = textures(q)
    print('  %s' % q.path)
    print('  %d Eintraege -> %d Texturen\n' % (len(q.ents), len(tex)))

    if '--png' in a:
        cmd_png(q, tex, a)
        return

    if '--dump' in a:
        out = a[a.index('--dump') + 1]
        lim = int(a[-1]) if a[-1].isdigit() else 25
        os.makedirs(out, exist_ok=True)
        nm = names()
        for i, (k, v) in enumerate(sorted(tex.items())):
            if i >= lim:
                break
            base = nm.get(k, '%013x' % k).replace('.ftex', '')
            for lv, (o, s) in sorted(v.items()):
                q.f.seek(o)
                suf = 'ftex' if lv == 0 else '%d.ftexs' % lv
                with open(os.path.join(out, '%s.%s' % (base, suf)), 'wb') as fh:
                    fh.write(q.f.read(s))
        print('  %d Texturen nach %s geschrieben' % (min(lim, len(tex)), out))
        return

    if '--stats' in a:
        byfmt = collections.Counter()
        bydim = collections.Counter()
        bytes_ = collections.Counter()
        for k, v in tex.items():
            hd = head_of(q, tex, k)
            if not hd.ok:
                continue
            byfmt[hd.fmt] += 1
            bydim[(hd.w, hd.h)] += 1
            bytes_[hd.fmt] += sum(s for i, (_, s) in v.items() if i)
        print('  Format                        Anzahl        MB')
        for f, n in byfmt.most_common():
            print('    %-4d %-22s %5d  %8.1f' % (f, FMT_HINT.get(f, '?'), n,
                                                 bytes_[f] / 2**20))
        print('\n  haeufigste Maße:')
        for (w, h), n in bydim.most_common(8):
            print('    %5dx%-5d %4d' % (w, h, n))
        return

    lim = int(a[a.index('--list') + 1]) if '--list' in a and len(a) > 1 \
        and a[-1].isdigit() else 20
    nm = names()
    print('  %-42s %s' % ('Name (soweit bekannt)', 'Kopf'))
    for i, (k, v) in enumerate(sorted(tex.items())):
        if i >= lim:
            break
        hd = head_of(q, tex, k)
        streams = ','.join(str(x) for x in sorted(x for x in v if x))
        print('  %-42s %s  [%s]'
              % (nm.get(k, '(%013x)' % k), hd if hd.ok else 'kein FTEX', streams))
    print('\n  %d von %d Texturen namentlich bekannt (Rest nur als Hash)'
          % (sum(1 for k in tex if k in nm), len(tex)))



# ---------------------------------------------------------------- Bilder
#
# Aufbau, am 18.08.2026 vollstaendig aufgeklaert und an echten Daten belegt.
#
# Mip-Tabelle ab 0x40 im .ftex, 16 Byte je Stufe:
#     +0x00 u32  Offset im Stream
#     +0x04 u32  Rohgroesse    (exakt die BC-Mipkette der Maße)
#     +0x08 u32  Groesse auf Platte
#     +0x0c u8   Mip-Nummer
#     +0x0d u8   in welcher .ftexs die Stufe liegt (1..n)
#     +0x0e u8   Anzahl Bloecke
#
# Jeder Stream beginnt mit einer Blocktabelle, 8 Byte je Block:
#     u16 komprimiert · u16 roh (16384) · u32 Offset
# Die Bloecke sind **zlib**. Belegt: die 78-9c-Koepfe liegen exakt auf den
# genannten Offsets, die Kette geht lueckenlos auf, und Mip 0 der Baumtextur
# entpackt sich auf exakt 524288 Byte = 1024x1024 BC1.
#
# **Die Daten sind NICHT GPU-gekachelt.** Nach dem Entpacken ist es schlichtes
# BC1/BC3 -- das dekodierte Bild zeigt einen Baum mit Blaettern.

MIPTAB = 0x40
CHUNK = 16384          # Rohgroesse je Block
FOURCC = {2: b'DXT1', 4: b'DXT5'}


def miptable(hdr):
    """[(offset, rohgroesse, plattengroesse, mip, stream, bloecke), ...]"""
    n = hdr[0x10]
    out = []
    for i in range(n):
        o = MIPTAB + i * 16
        if o + 16 > len(hdr):
            break
        off, raw, disk = struct.unpack_from('<3I', hdr, o)
        out.append((off, raw, disk, hdr[o + 0xc], hdr[o + 0xd], hdr[o + 0xe]))
    return out


def unpack_mip(streams, ent):
    """Eine Mip-Stufe aus ihrem Stream holen und entpacken."""
    import zlib
    off, raw, disk, mip, sid, nch = ent
    b = streams.get(sid)
    if b is None:
        return None
    # Die Blockanzahl im Kopf ist ein EINZELNES BYTE und laeuft bei 256 ueber:
    # Mip 0 einer 2048x2048-BC3-Textur braucht 4194304/16384 = 256 Bloecke und
    # steht dort als 0. Deshalb aus der Rohgroesse rechnen; an allen Stufen
    # gegengeprueft, wo das Byte stimmt (1, 4, 16, 64 ...).
    nch = (raw + CHUNK - 1) // CHUNK
    out = bytearray()
    for c in range(nch):
        if off + c * 8 + 8 > len(b):
            return None
        csz, usz, coff = struct.unpack_from('<HHI', b, off + c * 8)
        # BIT 31 DES VERSATZES HEISST "unkomprimiert gespeichert". Wer es
        # nicht abstreift, liest bei 0x80000008 ins Leere und bekommt eine
        # LEERE Stufe zurueck -- das sieht wie fehlende Daten aus, ist aber
        # ein Lesefehler. Am Mod ausgezaehlt: 611 von 28240 Bloecken liegen
        # so, fast alle auf den kleinsten Stufen.
        roh = bool(coff & 0x80000000)
        coff &= 0x7fffffff
        blob = b[off + coff:off + coff + csz]
        if roh:
            out += blob
        else:
            try:
                out += zlib.decompress(blob)
            except Exception:
                out += blob      # sicherheitshalber: doch roh gespeichert
    return bytes(out)


def dds_wrap(data, w, h, fourcc):
    x = bytearray(128)
    x[0:4] = b'DDS '
    struct.pack_into('<I', x, 4, 124)
    struct.pack_into('<I', x, 8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000)
    struct.pack_into('<I', x, 12, h)
    struct.pack_into('<I', x, 16, w)
    struct.pack_into('<I', x, 20, len(data))
    struct.pack_into('<I', x, 28, 1)
    struct.pack_into('<I', x, 76, 32)
    struct.pack_into('<I', x, 80, 0x4)
    x[84:88] = fourcc
    struct.pack_into('<I', x, 108, 0x1000)
    return bytes(x) + data


def to_png(q, tex, key, outdir, name, mip=0, fourcc=None):
    """Eine Mip-Stufe entpacken und als PNG ablegen. Gibt den Pfad zurueck."""
    import io
    from PIL import Image
    o, s = tex[key][0]
    q.f.seek(o)
    hdr = q.f.read(s)
    h = Header(hdr)
    if not h.ok:
        return None
    ents = miptable(hdr)
    if mip >= len(ents):
        return None
    streams = {}
    for lv, (oo, ss) in tex[key].items():
        if lv:
            q.f.seek(oo)
            streams[lv] = q.f.read(ss)
    data = unpack_mip(streams, ents[mip])
    if not data:
        return None
    w, hh = max(1, h.w >> mip), max(1, h.h >> mip)
    fc = fourcc or FOURCC.get(h.fmt)
    if fc is None:
        return None
    try:
        im = Image.open(io.BytesIO(dds_wrap(data, w, hh, fc)))
        im.load()
    except Exception:
        return None
    p = os.path.join(outdir, '%s_%dx%d.png' % (name, w, hh))
    if os.path.exists(p):
        # Namensgleichheit. GEMESSEN am 19.08.: von 1054 geschriebenen PNG
        # blieben nur 1035 auf der Platte -- 19 Texturen teilen sich Name
        # und Groesse mit einer anderen und ueberschrieben sich still.
        # Der Hash macht sie wieder unterscheidbar.
        p = os.path.join(outdir, '%s_%dx%d_%013x.png' % (name, w, hh, key))
    # Alpha behalten, wo es welches gibt. Texturen auf `_alp` tragen ihre
    # eigentliche Aussage im Alphakanal -- eine Overlay-Schicht sieht als
    # RGB nur nach grauem Rauschen aus, erst das Alpha zeigt, WO sie deckt.
    im.save(p) if im.mode in ('RGBA', 'LA') else im.convert('RGB').save(p)
    return p


def cmd_png(q, tex, a):
    outdir = a[a.index('--png') + 1]
    lim = int(a[-1]) if a[-1].isdigit() else 20
    mip = int(a[a.index('--mip') + 1]) if '--mip' in a else 0
    os.makedirs(outdir, exist_ok=True)
    nm = names()
    done = fail = 0
    for k, v in sorted(tex.items()):
        if done + fail >= lim:
            break
        base = nm.get(k, '%013x' % k).replace('.ftex', '')
        p = to_png(q, tex, k, outdir, base, mip)
        if p:
            done += 1
            print('  %s' % os.path.basename(p))
        else:
            fail += 1
    have = len([f for f in os.listdir(outdir) if f.lower().endswith('.png')])
    print('')
    print('  %d PNG geschrieben, %d uebersprungen, %d Dateien im'
          ' Ordner -> %s' % (done, fail, have, outdir))


if __name__ == '__main__':
    main()
