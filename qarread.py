"""Leser fuer P.T.s texture.qar -- Format aus benanntem Code abgelesen.

Woher das Format stammt
-----------------------
Nicht geraten, sondern aus `?LoadHeader@QarFile@fs@fox@@` (0x140044a90) im
MGSV-TPP-Prototyp vom 04.08.2015 disassembliert -- der bringt eine Linker-Map
mit 242 338 benannten Symbolen mit, siehe pedis.py. P.T. laeuft auf demselben
Fox-Engine-Stand, und die Funktion beschreibt exakt unsere Datei.

Der Kniff, an dem jede eigene Suche scheitert: **der Index steht am DATEIENDE**,
nicht am Anfang. Byte 0 ist bereits Bilddaten (BC1), ein Kopf existiert dort
nicht. Deshalb findet man auch kein `SQAR`-Magic -- das gehoert zum ANDEREN
Fox-Container (`SecureQarFile`, so sind MGSVs chunk*.dat gebaut).

Aufbau
------
    Trailer: die letzten 0x24 Bytes
        +0x10  u32  Anzahl Eintraege
        +0x16  u16  Magic 0x7161 == "aq"     <- die Pruefung im Original
        +0x18  u32  Indexbeginn in 16-Byte-Bloecken (also *16)

    Index: <Anzahl> Eintraege a 16 Byte, direkt vor dem Trailer
        +0x00  u64  Pfad-Hash (51 Bit Pfad | 13 Bit Endungscode)
        +0x08  u32  Datenbeginn in 16-Byte-Bloecken (also *16)
        +0x0c  u32  Groesse in Bytes

Gegengeprueft an P.T.s texture.qar (851 MB):
  * Dateigroesse - Indexbeginn == Anzahl*16 + 36   (exakt)
  * offset[i+1] == offset[i] + size[i]             (Kette geht lueckenlos auf)
  * Endungscode 5720 kommt 1061-mal vor == unabhaengig gezaehlte FTEX-Magics
  * Eintrag 3 liegt bei 164 000 == Fundstelle des ersten FTEX

    python qarread.py --list [n]        Eintraege zeigen
    python qarread.py --stats           Endungscodes und Groessen
    python qarread.py --check           die drei Gegenproben fahren
    python qarread.py --extract <dir>   alles herausschreiben (Hash als Name)

Die Pfadnamen stecken NICHT im Archiv -- nur Hashes. Ein Hash->Name-Woerterbuch
waere aus den Fox-Build-Protokollen zu bauen, fuer das Herausschreiben und
Neupacken braucht man es aber nicht.
"""
import os
import struct
import sys

import ptpaths                 # zentrale Pfade, siehe ptpaths.py
QAR = ptpaths.QAR
TRAILER = 0x24
MAGIC = 0x7161          # "aq"


class Qar:
    def __init__(self, path=QAR):
        self.path = path
        self.size = os.path.getsize(path)
        self.f = open(path, 'rb')
        self.f.seek(-TRAILER, os.SEEK_END)
        t = self.f.read(TRAILER)
        magic = struct.unpack_from('<H', t, 0x16)[0]
        if magic != MAGIC:
            raise ValueError('kein Fox-QAR: Magic 0x%04x statt 0x%04x am Ende'
                             % (magic, MAGIC))
        self.count = struct.unpack_from('<I', t, 0x10)[0]
        self.index = struct.unpack_from('<I', t, 0x18)[0] * 16
        self.f.seek(self.index)
        blob = self.f.read(self.count * 16)
        self.ents = []
        for i in range(self.count):
            h, off, sz = struct.unpack_from('<QII', blob, i * 16)
            self.ents.append((h, off * 16, sz))

    def data(self, i):
        _, off, sz = self.ents[i]
        self.f.seek(off)
        return self.f.read(sz)

    @staticmethod
    def split(h):
        """Fox-Pfadhash: unten 51 Bit Pfad, oben 13 Bit Endungscode."""
        return h & ((1 << 51) - 1), h >> 51


def check(q):
    """Die drei Gegenproben, die das Format belegen."""
    ok = True
    want = q.count * 16 + TRAILER
    got = q.size - q.index
    print('  Schwanz  : %d Bytes, erwartet %d  %s'
          % (got, want, 'OK' if got == want else 'FEHLT'))
    ok &= got == want

    # Offsets stehen in 16-Byte-Bloecken, jeder Eintrag wird also auf die
    # naechste 16er-Grenze aufgefuellt. Ohne dieses Aufrunden meldet die Kette
    # scheinbare Luecken, obwohl sie lueckenlos ist.
    def up16(n):
        return (n + 15) & ~15
    gaps = sum(1 for i in range(len(q.ents) - 1)
               if up16(q.ents[i][1] + q.ents[i][2]) != q.ents[i + 1][1])
    print('  Kette    : %d Lücken von %d Uebergaengen (16-Byte-Ausrichtung '
          'beruecksichtigt)  %s'
          % (gaps, len(q.ents) - 1, 'OK' if gaps == 0 else 'PRUEFEN'))
    ok &= gaps == 0

    # Zaehlt der haeufigste Endungscode so oft wie es FTEX-Magics gibt?
    n = 0
    for i, (h, off, sz) in enumerate(q.ents):
        if sz >= 4:
            q.f.seek(off)
            if q.f.read(4) == b'FTEX':
                n += 1
    import collections
    c = collections.Counter(q.split(h)[1] for h, _, _ in q.ents)
    top, topn = c.most_common(1)[0]
    print('  FTEX     : %d Eintraege beginnen mit FTEX; haeufigster Endungscode '
          '%d kommt %dx vor  %s' % (n, top, topn, 'OK' if n == topn else 'PRUEFEN'))
    return ok


def main():
    a = sys.argv[1:]
    q = Qar(a[a.index('--qar') + 1] if '--qar' in a else QAR)
    print('  %s' % q.path)
    print('  %.1f MB, %d Eintraege, Index @ %d\n' % (q.size / 2**20, q.count, q.index))

    if '--check' in a:
        check(q)
    elif '--stats' in a:
        import collections
        c = collections.Counter(q.split(h)[1] for h, _, _ in q.ents)
        tot = sum(s for _, _, s in q.ents)
        print('  Nutzdaten %.1f MB in %d Eintraegen' % (tot / 2**20, q.count))
        print('  %d Endungscodes:' % len(c))
        for code, n in c.most_common():
            b = sum(s for h, _, s in q.ents if q.split(h)[1] == code)
            print('     Code %-6d %5d Eintraege  %8.1f MB' % (code, n, b / 2**20))
    elif '--extract' in a:
        out = a[a.index('--extract') + 1]
        os.makedirs(out, exist_ok=True)
        for i, (h, off, sz) in enumerate(q.ents):
            lo, ext = q.split(h)
            with open(os.path.join(out, '%013x_%04d.bin' % (lo, ext)), 'wb') as fh:
                fh.write(q.data(i))
            if (i + 1) % 500 == 0:
                print('  %d/%d' % (i + 1, q.count))
        print('  %d Dateien nach %s' % (q.count, out))
    else:
        n = int(a[a.index('--list') + 1]) if '--list' in a and len(a) > 1 \
            and a[-1].isdigit() else 15
        print('  %-16s %-6s %12s %10s  %s' % ('Hash', 'Endg', 'Offset', 'Groesse', 'Magic'))
        for h, off, sz in q.ents[:n]:
            lo, ext = q.split(h)
            q.f.seek(off)
            print('  %016x %-6d %12d %10d  %r' % (h, ext, off, sz, q.f.read(4)))


if __name__ == '__main__':
    main()
