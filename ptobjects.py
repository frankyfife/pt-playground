"""Versteckte Objekte im Flur sichtbar machen -- an ihrem eigenen Platz.

Der Fund
--------
Jede `StaticModel`-Entity in `pt14_hallway.fox2` hat eine `flags`-Zahl, und
sie kennt genau zwei Werte:

    flags = 7    81 Objekte    Bit 0 gesetzt
    flags = 6    62 Objekte    Bit 0 fehlt

Welche wo stehen, sagt alles:

    shsb_bath001            die Badewanne          7
    shsb_bath001_mirr001    ihr Spiegel            7
    shsb_bath001_ocho001    Ocho AN der Wanne      6
    shsb_hous001_blod001    das Blut               6

Was man immer sieht, hat 7. Was man nie sieht, hat 6. Bit 0 ist also der
Schalter, mit dem P.T. seine versteckten Objekte zurueckhaelt -- kein Spawn
noetig, die Dinge stehen laengst an ihrem Platz.

ACHTUNG, das ist eine aus 143 Faellen abgeleitete Deutung, kein
Disassemblat. Bevor sie als gesichert gilt, muss ein Objekt im Spiel
sichtbar geworden sein. `--test` baut genau dafuer den kleinsten Fall
(das Blut) statt gleich alles umzustellen.

Warum nicht spawnen
-------------------
`spawn.py` kopiert ein Gimmick in den Startraum. Das ist gut, um etwas
anzusehen, aber es setzt die Dinge an einen erfundenen Ort. Hier geht es um
das Gegenteil: die Objekte dort zu zeigen, wo die Entwickler sie hingestellt
haben -- Ocho neben der Wanne, das Blut an seiner Wand.

    python ptobjects.py                 alle Objekte auflisten
    python ptobjects.py --hidden        nur die versteckten
    python ptobjects.py --grep ocho     suchen
"""
import collections
import re
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fox2build
import foxfast
import foxfpk
import gotoending as ge
import psarc
import ptpaths
import spawn as sp

FPKD = ge.FPKD
FOX2 = ge.FOX2
VISIBLE_BIT = 1

# Was erfahrungsgemaess interessiert. Reine Anzeigehilfe -- die Liste
# entscheidet nichts, sie sortiert nur nach oben, was man sucht.
NOTES = {
    'shsb_bath001_ocho001_0000': 'Ocho at the bathtub - the hidden figure',
    'shsb_hous001_ocho001_0000': 'Ocho in the hallway',
    'shsb_hous001_blod001_0000': 'blood',
    'shsb_tlph001_0000': 'telephone',
    'shsb_mntr001_0000': 'monitor',
    'shsb_clck001_2358_0000': 'clock at 23:58',
    'shsb_clck001_2359_0000': 'clock at 23:59',
    'shsb_clck001_black_0000': 'clock, black',
    'shsb_clck001_center_0000': 'clock, centre',
    'shsb_labl001_holl001_0000': 'wall text',
    'shsb_labl001_ican001_0000': 'wall text',
    'shsb_labl001_forg001_0000': 'wall text',
    'shsb_labl001_notu001_0000': 'wall text',
}


def _doc(archive):
    fp = foxfpk.Fpk(foxfast.decrypt(archive.read(archive.index_of(FPKD))))
    return fp, fox2build.Doc.load(fp.get(FOX2))


def _name(doc, e):
    try:
        return sp._text(doc, e, 'name') or ''
    except Exception:
        return ''


def _flags(e):
    p = e.get('flags')
    if p is None:
        return None
    return struct.unpack('<I', p.value())[0]


def _path(doc, e, prop):
    """Den Dateipfad einer Eigenschaft als Text, oder ''."""
    p = e.get(prop)
    if p is None:
        return ''
    try:
        return sp._text(doc, e, prop) or ''
    except Exception:
        return ''


# Der Ordner unter .../object/shsb/ ist das ausgeschriebene Wort. Das ist
# keine Deutung, sondern steht so im Assetpfad jedes StaticModel.
CAT = re.compile(r'/object/shsb/([^/]+)/')


def category(model_file):
    """'bath' aus .../object/shsb/bath/shsb_bath001/scenes/shsb_bath001.fmdl"""
    m = CAT.search(model_file or '')
    return m.group(1) if m else ''


def scan(archive=None):
    """Alle StaticModel als Liste von dicts.

    Felder: full, short, layer, flags, visible, note, group.
    `group` fasst zusammen, was offensichtlich Varianten desselben Dings
    sind -- gleiche Objektkennung, nur anderes Suffix (shsb_clck001_2358 und
    _2359). Die Gruppierung ist eine Lesehilfe, keine Aussage der Engine.
    """
    a = archive or psarc.Psarc(ptpaths.ORIG)
    _, doc = _doc(a)
    out = []
    for e in doc.of_class('StaticModel'):
        full = _name(doc, e)
        if not full:
            continue
        parts = full.split('|')
        short = parts[-1]
        layer = parts[1] if len(parts) > 2 else ''
        m = re.match(r'(shsb_[a-z]+\d+)', short)
        model = _path(doc, e, 'modelFile')
        geom = _path(doc, e, 'geomFile')
        cat = category(model)
        out.append({
            'full': full,
            'short': short,
            'layer': layer.replace('pt14_hallway_', ''),
            'flags': _flags(e),
            'visible': bool((_flags(e) or 0) & VISIBLE_BIT),
            # Von Hand geschriebene Beschreibung, falls es eine gibt --
            # sonst die Kategorie aus dem Assetpfad. Damit hat JEDES Objekt
            # eine Angabe, statt 130 von 143 leer zu lassen.
            'note': NOTES.get(short, '') or cat,
            'cat': cat,
            'model': model,
            'geom': geom,
            'group': m.group(1) if m else short,
        })
    out.sort(key=lambda d: (d['group'], d['short']))
    return out


def overrides(archive, wanted, log=print):
    """`wanted`: {kurzname: True/False}. Gibt das Override-Dict fuer psarc.

    Nur Objekte, die es wirklich gibt, werden angefasst; ein unbekannter
    Name bricht ab, statt still nichts zu tun -- ein falsch geschriebener
    Name waere sonst ein stumm verlorener Bauvorgang.
    """
    fp, doc = _doc(archive)
    by_short = {}
    for e in doc.of_class('StaticModel'):
        n = _name(doc, e).split('|')[-1]
        by_short.setdefault(n, []).append(e)

    unknown = [k for k in wanted if k not in by_short]
    if unknown:
        sys.exit('  unbekannte Objekte: %s' % ', '.join(sorted(unknown)))

    n = 0
    for short, on in wanted.items():
        for e in by_short[short]:
            p = e.get('flags')
            if p is None:
                continue
            cur = struct.unpack('<I', p.value())[0]
            new = (cur | VISIBLE_BIT) if on else (cur & ~VISIBLE_BIT)
            if new == cur:
                continue
            p.set_value(0, struct.pack('<I', new))
            n += 1
            log('  %-42s flags %d -> %d  (%s)'
                % (short, cur, new, 'sichtbar' if on else 'aus'))
    if not n:
        log('  nichts zu aendern -- alle Objekte stehen schon so')
        return {}
    fp.replace(FOX2, doc.build())
    return {archive.index_of(FPKD): foxfast.encrypt(fp.build())}


def main():
    a = sys.argv[1:]
    rows = scan()
    if '--grep' in a:
        pat = a[a.index('--grep') + 1].lower()
        rows = [r for r in rows if pat in r['short'].lower()
                or pat in r['note'].lower()]
    if '--hidden' in a:
        rows = [r for r in rows if not r['visible']]
    vis = sum(1 for r in rows if r['visible'])
    print('  %d Objekte  (%d sichtbar, %d versteckt)'
          % (len(rows), vis, len(rows) - vis))
    print()
    grp = collections.OrderedDict()
    for r in rows:
        grp.setdefault(r['group'], []).append(r)
    for g, items in grp.items():
        if len(items) > 1:
            print('  %s   (%d Zustaende)' % (g, len(items)))
        for r in items:
            print('     %-3s %-42s %-10s %s'
                  % ('ON ' if r['visible'] else 'off', r['short'],
                     r['layer'], r['note']))


if __name__ == '__main__':
    main()
