"""Leser fuer P.T.s .pftxs -- den Texturcontainer, den das Spiel wirklich liest.

Warum es diesen Leser braucht
-----------------------------
Am 19.08.2026 stellte sich heraus: Die Badezimmertexturen im `chunk1` unter
`sourceimages/` werden vom Spiel NICHT verwendet. Beweis durch Messung -- eine
davon knallrot eingefaerbt, im Spiel blieb alles unveraendert. Geladen wird
aus `pt14_hallway.pftxs` (28 MB), und dort stehen 74 Badtexturen, die es im
chunk1 gar nicht gibt (ce01, wa04, wa05_06, to01, bo01, cr01, ho, li01 ...).

Aufbau
------
    0x00  "PFTX"
    0x04  Version, float 1.0
    0x08  Dateigroesse            (stimmt exakt)
    0x0c  Anzahl Eintraege
    0x10  Offset des Datenbereichs
    0x14  Tabelle, je 8 Byte: (Offset des Namens, Groesse des FTEX-Kopfs)

KORREKTUR vom 15.09.2026. Bis dahin stand hier, bei 0x14 liege der Offset des
Namensbereichs und die Tabelle beginne bei 0x18 als (Groesse, Name). Beides war
falsch, und zwar auf eine Weise, die sich selbst bestaetigte: um vier Byte
verschoben liest man Groessen und Namensoffsets, die einzeln plausibel
aussehen -- nur gehoert der Name dann zur NAECHSTEN Textur.

Aufgefallen ist es erst beim Vergleich der Mipstroeme mit dem texture.qar:
704 von 705 waren "verschieden", und die Bytes von Eintrag N stimmten mit
denen von Name N-1 ueberein. Der letzte Beweis steht im Namensbereich selbst:
er beginnt mit einem voll ausgeschriebenen Pfad, den keine Tabellenzeile
nennt, und der erste Name der alten Lesart fing mit `@` an -- also
"Verzeichnis wie zuvor", ohne dass es ein Zuvor gab.

Die Namen stehen im Klartext. Ein `@` am Anfang heisst "gleiches Verzeichnis
wie beim letzten voll ausgeschriebenen Pfad" -- so spart die Datei Platz.

Im Datenbereich folgen Kopf und Mipdaten je Eintrag hintereinander. Welche
Mipstufen dabei sind, verraet die Miptabelle im Kopf: die grossen Stufen
liegen in `texture.qar` und FEHLEN hier. Beim Flur ist Mip 2 (512x512) die
hoechste vorhandene Stufe -- wer ohne qar spielt, sieht genau die.

    python pftxs.py                       Inhalt von pt14_hallway auflisten
    python pftxs.py --grep bath           filtern
    python pftxs.py --png <dir> <muster>  als PNG herausschreiben
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ftex
import psarc
import ptpaths

MAGIC = b'PFTX'


def _cstr(b, o):
    e = b.index(b'\0', o)
    return b[o:e].decode('ascii', 'replace')


class Pftxs(object):
    def __init__(self, blob):
        if blob[:4] != MAGIC:
            raise ValueError('kein PFTX')
        self.blob = blob
        (self.ver, self.size, self.count,
         self.data_off) = struct.unpack_from('<IIII', blob, 4)
        self.tab_off = 0x14
        self.ents = self._read()
        # Der Namensbereich faengt beim ersten Namen an; einen eigenen
        # Kopfeintrag dafuer gibt es nicht.
        self.name_off = min([e['name_off'] for e in self.ents] or [0])

    def _read(self):
        b = self.blob
        # Die Koepfe stehen im Datenbereich hintereinander, aber die Groesse
        # der Mipdaten dazwischen ist nicht direkt angegeben. Statt sie
        # auszurechnen (und dabei zu raten, welche Streams enthalten sind),
        # werden die FTEX-Magics gesucht -- ihre Zahl stimmt mit der Tabelle
        # ueberein, die Zuordnung ist damit eindeutig.
        pos, offs = self.data_off, []
        while True:
            i = b.find(b'FTEX', pos)
            if i < 0:
                break
            offs.append(i)
            pos = i + 4
        out, last_dir = [], ''
        for k in range(self.count):
            noff, sz = struct.unpack_from('<II', b, self.tab_off + k * 8)
            if noff >= len(b) or k >= len(offs):
                break
            roh = _cstr(b, noff)
            if roh.startswith('@'):
                nm = last_dir + roh[1:]
            else:
                nm = roh
                last_dir = roh.rsplit('/', 1)[0] + '/' if '/' in roh else ''
            out.append({'name': nm, 'roh_name': roh, 'name_off': noff,
                        'hdr_size': sz, 'off': offs[k]})
        return out

    def _header_end(self, e):
        """Ende des FTEX-Kopfs: Schluss der Miptabelle."""
        n = self.blob[e['off'] + 0x10]
        return e['off'] + ftex.MIPTAB + n * 16

    def data_start(self, e):
        """Wo die Mipdaten des Eintrags beginnen.

        BELEGT am 19.08. durch Entpacken aller sechs Stufen von
        shsb_bath001_mi02_bsm_alp: direkt hinter dem PSUB-Verzeichnis, also

            Kopfende + 8 + n * 8

        Die Offsets IM PSUB-Verzeichnis zeigen woandershin und taugen dafuer
        nicht -- bei der Maske auf 0x635470, weit hinter dem eigenen Eintrag.
        Wer ihnen folgt, liest Zufall und schreibt in fremde Texturen.
        """
        he = self._header_end(e)
        if self.blob[he:he + 4] != b'PSUB':
            return he
        n = struct.unpack_from('<I', self.blob, he + 4)[0]
        return he + 8 + n * 8

    def chunks(self, e):
        """[(Adresse des Chunkkopfs, mip, roh, csz, roh_flag), ...]

        Chunkkopf: csz, usz, coff. Ist Bit 31 in coff gesetzt, liegen die
        Daten ROH statt zlib-gepackt -- so sind die kleinsten Stufen abgelegt,
        bei denen Packen nichts brächte.
        """
        base = self.data_start(e)
        # Nur die Stroeme, die wirklich hier liegen: das PSUB-Verzeichnis
        # nennt ihre Anzahl, und es sind die mit den NIEDRIGSTEN Ids -- die
        # grossen Stufen stehen in der qar. Ohne diese Einschraenkung
        # kollidiert Mip 0 (Strom 2, Offset 0) mit Mip 6 (Strom 1, Offset 0)
        # und man entpackt Unsinn.
        he = self._header_end(e)
        have = None
        if self.blob[he:he + 4] == b'PSUB':
            n = struct.unpack_from('<I', self.blob, he + 4)[0]
            sids = sorted({m[4] for m in ftex.miptable(self.header(e))})
            have = set(sids[:n])
        out = []
        for off, raw, disk, lv, sid, nch in ftex.miptable(self.header(e)):
            if have is not None and sid not in have:
                continue
            for c in range(max(1, nch)):
                tp = base + off + c * 8
                if tp + 8 > len(self.blob):
                    break
                csz, usz, coff = struct.unpack_from('<HHI', self.blob, tp)
                out.append((tp, lv, usz, csz, bool(coff & 0x80000000),
                            coff & 0x7fffffff))
        return out

    def header(self, e):
        return self.blob[e['off']:e['off'] + e['hdr_size']]

    def streams(self, e):
        """Die Mipstroeme des Eintrags als {stream_id: bytes}.

        Hinter dem FTEX-Kopf steht KEIN roher Datenblock, sondern ein
        Unterverzeichnis:

            "PSUB"  n  dann n Paare (absoluter Offset, Groesse)

        Der erste Offset ist genau Kopfende + 8 + n*8, die Rechnung geht
        also auf. Die Teile entsprechen den Stroemen in aufsteigender Id --
        beim geprueften Eintrag 3 Teile fuer die Stroeme 1, 2 und 3; die
        groesseren Stufen liegen in der qar und fehlen hier.
        """
        hdr = self.header(e)
        want = []
        for _o, _raw, _disk, _lv, sid, _n in ftex.miptable(hdr):
            if sid not in want:
                want.append(sid)
        want.sort()

        pos = self._header_end(e)
        if self.blob[pos:pos + 4] != b'PSUB':
            # Kein Verzeichnis: dann liegen die Stroeme direkt hinter dem
            # Kopf. Das PSUB gibt es nur, wenn mehrere da sind -- geprueft
            # an shsb_bath001_mi02_bsm_alp im Flur: 7712 Byte Platz, Stream 1
            # braucht 7696 plus 16 Ausrichtung, kein PSUB weit und breit.
            i = self.ents.index(e) if e in self.ents else -1
            end = (self.ents[i + 1]['off'] if 0 <= i < len(self.ents) - 1
                   else len(self.blob))
            out = {}
            for sid in want:
                n = sum(m[2] for m in ftex.miptable(hdr) if m[4] == sid)
                if pos + n > end:
                    break          # liegt in der qar, nicht hier
                out[sid] = self.blob[pos:pos + n]
                pos += n
            return out
        n = struct.unpack_from('<I', self.blob, pos + 4)[0]
        parts = []
        for i in range(n):
            off, size = struct.unpack_from('<II', self.blob, pos + 8 + i * 8)
            if off + size <= len(self.blob):
                parts.append(self.blob[off:off + size])
        return dict(zip(want, parts))


def load(name='pt14_hallway'):
    a = psarc.Psarc(ptpaths.ORIG)
    hit = [n for n in a.names if n.endswith('/%s.pftxs' % name)]
    if not hit:
        raise SystemExit('  %s.pftxs nicht im Archiv' % name)
    return Pftxs(a.read(a.index_of(hit[0])))


def main():
    a = sys.argv[1:]
    lvl = a[a.index('--level') + 1] if '--level' in a else 'pt14_hallway'
    p = load(lvl)
    print('  %s.pftxs: %d Byte, %d Eintraege, Daten ab 0x%x'
          % (lvl, p.size, p.count, p.data_off))
    rows = p.ents
    if '--grep' in a:
        pat = a[a.index('--grep') + 1].lower()
        rows = [e for e in rows if pat in e['name'].lower()]
    print('  %d Eintraege%s' % (len(rows), ' (gefiltert)' if '--grep' in a else ''))
    print()
    for e in rows[:60]:
        h = ftex.Header(p.header(e))
        st = p.streams(e)
        print('     %-52s %4dx%-4d fmt=%d  Stroeme %s'
              % (e['name'].split('/')[-1], h.w, h.h, h.fmt,
                 sorted(st) if st else '-'))


if __name__ == '__main__':
    main()
