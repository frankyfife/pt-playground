"""Texturen im chunk1 einfaerben oder durchsichtig machen -- zum Suchen.

Wozu
----
Im Bad verdeckt eine Textur die Spiegelreflexion (in der das vollstaendige
Spielermodell steht). Welche es ist, laesst sich nicht ansehen: die
exportierte `shsb_bath001_dc_bsm_alp` sieht der Verdeckung zum Verwechseln
aehnlich -- rot eingefaerbt blieb das Bild im Spiel aber unveraendert. Sie
ist es also nicht.

Statt weiter zu vergleichen, wird gesucht wie bei der Taschenlampe: alle
Kandidaten auffaellig einfaerben, im Spiel nachsehen, per Halbierung
eingrenzen.

Blockformate
------------
Das Format steht im FTEX-Kopf und entscheidet, wo die Farbe liegt:

    fmt 2 = BC1   8 Byte je Block: color0, color1, dann 4 Byte Indizes
    fmt 4 = BC3  16 Byte je Block: 2 Byte Alpha-Stuetzwerte, 6 Byte
                 Alpha-Indizes, dann color0, color1, 4 Byte Indizes

Beide Farben gleich zu setzen ergibt eine einfarbige Flaeche, unabhaengig
von den Indizes. Bei BC3 macht Alpha 0 in beiden Stuetzwerten den Block
vollstaendig durchsichtig.

Warum die Datei dabei nicht waechst: gleichfoermige Daten komprimieren
besser als das Original, die neuen zlib-Bloecke sind kleiner und passen an
dieselbe Stelle. Nur die Groesse in der Chunk-Tabelle wird nachgezogen.
Passt einer doch nicht, wird er ABGELEHNT statt ueberschrieben.

    python texpatch.py --list bath        Kandidaten zeigen
    python texpatch.py --check <name>     einen durchrechnen
"""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ftex
import psarc
import ptpaths

SRC = '/as/sh/environ/object/shsb/bath/shsb_bath001/sourceimages/'
CHUNK = ftex.CHUNK

# RGB565
RED = 0xF800
GREEN = 0x07E0
BLUE = 0x001F
MAGENTA = 0xF81F


def _blocksize(fmt):
    return 8 if fmt == 2 else 16


def _paint(data, fmt, colour=None, clear_alpha=False):
    """Bloecke einfaerben und/oder durchsichtig machen.

    BC3 (fmt 4): Byte 0/1 sind die Alpha-Stuetzwerte -- beide auf 0 macht den
    Block vollstaendig durchsichtig. Farbe liegt bei Byte 8..11.

    BC1 (fmt 2): kennt nur 1-Bit-Alpha, und zwar ueber eine Konvention --
    ist color0 <= color1, schaltet der Block in den Alphamodus, und Index 3
    bedeutet dann "durchsichtig". Beide Farben auf 0 und alle Indizes auf 3
    (0xFF in jedem Indexbyte) macht ihn also komplett durchsichtig. Ohne
    diese Konvention waere ein BC1-Block gar nicht transparent zu bekommen.
    """
    bs = _blocksize(fmt)
    coff = 0 if bs == 8 else 8
    b = bytearray(data)
    for i in range(0, len(b) - bs + 1, bs):
        if clear_alpha:
            if bs == 16:
                b[i] = 0
                b[i + 1] = 0
            else:
                struct.pack_into('<HH', b, i, 0, 0)
                b[i + 4:i + 8] = bytes([0xff] * 4)
                continue
        if colour is not None:
            struct.pack_into('<HH', b, i + coff, colour, colour)
    return bytes(b)


def _patch_stream(blob, mips, fmt, colour, clear_alpha, rep):
    out = bytearray(blob)
    for off, raw, disk, lv, sid, _ in mips:
        for c in range((raw + CHUNK - 1) // CHUNK):
            pos = off + c * 8
            if pos + 8 > len(out):
                rep.append((lv, c, 'Tabelle zu kurz'))
                continue
            csz, usz, coff = struct.unpack_from('<HHI', out, pos)
            # Bit 31 ist ein FLAG, kein Offset -- die kleinsten Mipstufen
            # tragen es, ihre Daten liegen nicht in diesem Strom.
            if coff & 0x80000000 or off + coff + csz > len(out):
                rep.append((lv, c, 'ausserhalb'))
                continue
            src = bytes(out[off + coff:off + coff + csz])
            try:
                plain, packed = zlib.decompress(src), True
            except zlib.error:
                plain, packed = src, False
            fixed = _paint(plain, fmt, colour, clear_alpha)
            new = zlib.compress(fixed, 9) if packed else fixed
            if len(new) > csz:
                rep.append((lv, c, 'zu gross %d>%d' % (len(new), csz)))
                continue
            out[off + coff:off + coff + len(new)] = new
            if len(new) < csz:
                out[off + coff + len(new):off + coff + csz] = \
                    b'\0' * (csz - len(new))
            struct.pack_into('<H', out, pos, len(new))
            rep.append((lv, c, 'ok'))
    if len(out) != len(blob):
        rep.append((-1, -1, 'LAENGE VERAENDERT -- verworfen'))
        return blob
    return bytes(out)


def overrides(archive, names, colour=None, clear_alpha=False, log=print):
    """`names`: kurze Texturnamen ohne Pfad und Endung."""
    out = {}
    for name in names:
        try:
            hi = archive.index_of(SRC + name + '.ftex')
        except Exception:
            log('  %s: nicht im Archiv' % name)
            continue
        hdr = archive.read(hi)
        h = ftex.Header(hdr)
        ents = ftex.miptable(hdr)
        bysid = {}
        for e in ents:
            bysid.setdefault(e[4], []).append(e)
        rep = []
        for sid, mips in sorted(bysid.items()):
            try:
                i = archive.index_of('%s%s.%d.ftexs' % (SRC, name, sid))
            except Exception:
                continue
            out[i] = _patch_stream(archive.read(i), mips, h.fmt, colour,
                                   clear_alpha, rep)
        ok = sum(1 for r in rep if r[2] == 'ok')
        log('  %-28s fmt=%d  %d Bloecke, %d uebersprungen'
            % (name, h.fmt, ok, len(rep) - ok))
    return out


def bath_names(archive, only_bsm=True):
    """Die Badtexturen aus dem chunk1. `only_bsm` laesst Normalen- und
    Specularkarten weg -- sichtbar faerben laesst sich nur die Basisfarbe."""
    out = []
    for n in archive.names:
        if not n.startswith(SRC) or not n.endswith('.ftex'):
            continue
        short = n[len(SRC):-5]
        if only_bsm and '_bsm' not in short:
            continue
        out.append(short)
    return sorted(out)


def main():
    a = sys.argv[1:]
    ar = psarc.Psarc(ptpaths.ORIG)
    if '--list' in a:
        for n in bath_names(ar, only_bsm=False):
            print('  %s' % n)
        return
    if '--check' in a:
        name = a[a.index('--check') + 1]
        overrides(ar, [name], colour=RED)
        return
    print('  --list zeigt die Texturen, --check <name> rechnet eine durch.')


if __name__ == '__main__':
    main()
