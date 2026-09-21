"""P.T.s Ereignisgraph im Klartext -- wer loest was aus, in welcher Schleife.

Warum das geht
--------------
`pt14_hallway.fox2` enthaelt nicht nur die Objekte, sondern die ganze
Choreografie. 5362 Entities, und die entscheidenden Klassen sind:

    GeoTrap                     84   das Ausloeservolumen
    GeoModuleCondition         158   eine Regel daran
    ShTrapCheckIsPlayer...     135   Bedingung: ist es der Spieler
    GeoTrapScriptCallback...   111   Aktion: dieses Lua ausfuehren
    ShTrapExecNazoCallback...   15   Aktion: Raetselschritt
    ShTrapCheckIsInView...      14   Bedingung: schaut er hin
    ShTrapCheckPlayerInput...    9   Bedingung: Eingaberichtung
    ShDemoScript                47   die Inszenierungen
    ShGimmickLocatorParameter    4   Baby, Ocho, Freezer, CeilLamp
    NazoManageData               1   die Raetselverwaltung

Der Aufbau: ein `GeoTrap` zeigt ueber `conditionArray` auf
`GeoModuleCondition`-Regeln. An jeder Regel haengen DataElements, die
zurueck auf sie zeigen (`owner`) -- die einen pruefen, die anderen fuehren
aus. Ein `ShDemoScript` haengt an `demoId` + `messageName` + `floorNames`
und nennt in `targetData` das betroffene Objekt.

EntityLink (Typ 22) -- empirisch aufgeschluesselt
-------------------------------------------------
32 Byte, vier 64-Bit-Werte, jeweils 48 Bit Hash:

    +0x00  packPath      meist leer
    +0x08  archivePath   /Assets/sh/level/promotion/pt_2014/hallway/pt14_hallway.fox2
    +0x10  nameInArchive pt14_hallway|pt14_hallway_environ|shsb_clck001_2359_0000
    +0x18  0

Belegt daran, dass `strcode64("")` = b8a0bf169f98 genau der Wert in +0x00
ist und +0x08 auf den Dateinamen der fox2 selbst aufloest.

Die Schleifen heissen `f005 f010 f020 f030 f040 f050 f060 f070 f080 f090
f160` -- das sind die `floorNames`, die `GameFloorLevel.SetFloorLevel`
erwartet (dieselbe Sorte Name wie das `"ending"`, das die Endsequenz nimmt).

    python ptlogic.py --floors            Schleifen und was in ihnen passiert
    python ptlogic.py --demos             alle Inszenierungen
    python ptlogic.py --demos f050        nur die einer Schleife
    python ptlogic.py --traps             Ausloeser mit Regeln und Aktionen
    python ptlogic.py --grep ocho         alles zu einem Namen
    python ptlogic.py --obj shsb_clck001  wer dieses Objekt anfasst
    python ptlogic.py --class ShDemoScript
    python ptlogic.py --levels           alle fuenf Level im Vergleich
    python ptlogic.py --level maze_A --traps
    python ptlogic.py --trace ocho       wer schaltet das, in welcher Ebene
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psarc
import ptobjects
import ptpaths

MASK48 = (1 << 48) - 1
EMPTY = 0xB8A0BF169F98            # strcode64("")

# Eigenschaftstypen, soweit sie hier vorkommen
T_INT = 4
T_UINT = 5
T_FLOAT = 8
T_BOOL = 10
T_STRING = 11
T_ENTITYPTR = 13
T_VEC = 16
T_COLOR = 19
T_FILEPTR = 20
T_ENTITYHANDLE = 21
T_ENTITYLINK = 22

# beim Auflisten uninteressant -- Geruest, nicht Inhalt
BORING = ('dataSet', 'shearTransform', 'pivotTransform', 'children', 'flags',
          'parent', 'inheritTransform')


# Es gibt FUENF Level, nicht eines. Der Flur, drei Labyrinthvarianten und
# der Startraum -- plus die Ending-Stage. Jedes bringt seine eigenen
# Objekte, Ausloeser und Inszenierungen mit.
LEVELS = {
    'hallway': ('/as/sh/level/promotion/pt_2014/hallway/pt14_hallway.fpkd',
                '/Assets/sh/level/promotion/pt_2014/hallway/pt14_hallway.fox2'),
    'maze_A': ('/as/sh/level/promotion/pt_2014/hallway_maze_A/'
               'pt14_hallway_maze_A.fpkd',
               '/Assets/sh/level/promotion/pt_2014/hallway_maze_A/'
               'pt14_hallway_maze_A.fox2'),
    'maze_B': ('/as/sh/level/promotion/pt_2014/hallway_maze_B/'
               'pt14_hallway_maze_B.fpkd',
               '/Assets/sh/level/promotion/pt_2014/hallway_maze_B/'
               'pt14_hallway_maze_B.fox2'),
    'maze_C': ('/as/sh/level/promotion/pt_2014/hallway_maze_C/'
               'pt14_hallway_maze_C.fpkd',
               '/Assets/sh/level/promotion/pt_2014/hallway_maze_C/'
               'pt14_hallway_maze_C.fox2'),
    'start': ('/as/sh/level/promotion/pt_2014/start/pt14_start.fpkd',
              '/Assets/sh/level/promotion/pt_2014/start/pt14_start.fox2'),
    'ending': ('/as/sh/level/promotion/pt_2014/ending/ending.fpkd',
               '/Assets/sh/level/promotion/pt_2014/ending/ending.fox2'),
}


class Graph:
    def __init__(self, archive=None, level='hallway'):
        import foxfast
        import foxfpk
        a = archive or psarc.Psarc(ptpaths.ORIG)
        self.level = level
        fpkd, fox2 = LEVELS[level]
        self.fpk = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(fpkd))))
        import fox2build
        self.doc = fox2build.Doc.load(self.fpk.get(fox2))
        self.names = self.doc.strings
        self.by_addr = {e.addr: e for e in self.doc.ents}
        self.by_name = {}
        self.by_short = {}
        import strcode
        for e in self.doc.ents:
            h = self._name_hash(e)
            if h:
                self.by_name.setdefault(h & MASK48, e)
                short = self.s(h).split('|')[-1]
                if short:
                    self.by_short.setdefault(
                        strcode.strcode64(short) & MASK48, e)
        # owner -> DataElements, die auf ihn zeigen
        self.children = collections.defaultdict(list)
        for e in self.doc.ents:
            p = e.get('owner')
            if p and p.count:
                t = self._q(p.value(0))
                if t:
                    self.children[t].append(e)

    # --- Kleinteile --------------------------------------------------------
    @staticmethod
    def _q(raw, off=0):
        return (struct.unpack_from('<Q', raw, off)[0]
                if len(raw) >= off + 8 else None)

    def s(self, h):
        """Hash -> Text. Unbekanntes bleibt als Hash stehen, statt zu
        verschwinden -- sonst sieht man nicht, dass da etwas war."""
        if h is None:
            return ''
        h &= MASK48
        if h in (0, EMPTY):
            return ''
        return self.names.get(h, '#%012x' % h)

    def cls(self, e):
        return self.s(e.chash) or '#%012x' % e.chash

    def _name_hash(self, e):
        p = e.get('name')
        if p and p.count:
            return self._q(p.value(0))
        return None

    def name(self, e, short=False):
        n = self.s(self._name_hash(e))
        return n.split('|')[-1] if short and n else n

    def link(self, raw):
        """EntityLink -> (archiv, name). Nur der Name interessiert meist."""
        return self.s(self._q(raw, 8)), self.s(self._q(raw, 0x10))

    def resolve(self, raw):
        """EntityLink -> Entity. Erst ueber den vollen Namen, dann ueber den
        kurzen: die Links nennen den kurzen, die Entities tragen den vollen.

        Der Archivpfad im Link zeigt noch auf die Editordatei
        (`.../f005/f005_demo.las`), die gar nicht mitgeliefert wird -- beim
        Bauen sind die Regeln in die fox2 gewandert. Nach Archiv zu suchen
        fuehrt also ins Leere, nach Namen nicht.
        """
        h = self._q(raw, 0x10)
        if h is None:
            return None
        h &= MASK48
        return self.by_name.get(h) or self.by_short.get(h)

    def conditions_of(self, trap):
        p = trap.get('conditionArray')
        out = []
        for i in range(p.count if p else 0):
            raw = p.value(i)
            out.append((self.link(raw)[1], self.resolve(raw)))
        return out

    def trace(self, pat):
        """Wer schaltet dieses Objekt, in welcher Schleife.

        Der Weg: Objektname -> Regel (GeoModuleCondition), die ihn in einer
        Eigenschaft nennt -> Ausloeser (GeoTrap), der die Regel fuehrt ->
        Ebene aus dem Trap-Namen (`..._demo|f040_demo|...`).
        """
        import strcode
        hits = [e for e in self.doc.ents
                if pat.lower() in (self.name(e, short=True) or '').lower()]
        out = []
        for obj in hits:
            oh = self._name_hash(obj)
            if oh is None:
                continue
            oh &= MASK48
            rules = []
            for e in self.doc.ents:
                if e.addr == obj.addr or self.cls(e) == 'DataSet':
                    continue        # dataList fuehrt ALLES -- kein Hinweis
                for pr in e.props:
                    if self.s(pr.hash) in ('name', 'dataList'):
                        continue
                    d = bytes(pr.data)
                    if any(struct.unpack_from('<Q', d, o)[0] & MASK48 == oh
                           for o in range(0, len(d) - 7, 8)):
                        rules.append((e, self.s(pr.hash)))
                        break
            traps = []
            for r, _ in rules:
                rn = self.name(r, short=True)
                rh = strcode.strcode64(rn) & MASK48 if rn else None
                for t in self.doc.of_class('GeoTrap'):
                    for nm, c in self.conditions_of(t):
                        if nm == rn or (c is not None and c.addr == r.addr):
                            traps.append((t, r))
                            break
            out.append((obj, rules, traps))
        return out

    def val(self, p):
        """Alle Werte einer Eigenschaft, menschenlesbar."""
        out = []
        for i in range(max(1, p.count)):
            try:
                raw = p.value(i)
            except Exception:
                break
            out.append(self._one(p.type, raw))
        return out

    def _one(self, t, raw):
        try:
            if t in (T_STRING, T_FILEPTR):
                return self.s(self._q(raw))
            if t == T_UINT:
                return struct.unpack_from('<I', raw)[0]
            if t == T_INT:
                return struct.unpack_from('<i', raw)[0]
            if t == T_FLOAT:
                return round(struct.unpack_from('<f', raw)[0], 3)
            if t == T_BOOL:
                return bool(raw[0])
            if t in (T_ENTITYPTR, T_ENTITYHANDLE):
                a = self._q(raw)
                tgt = self.by_addr.get(a) if a else None
                if not tgt:
                    return '' if not a else '->@%x' % a
                nm = self.name(tgt, short=True)
                return '->%s%s' % (self.cls(tgt), '(%s)' % nm if nm else '')
            if t == T_ENTITYLINK:
                arc, nm = self.link(raw)
                return nm or arc
            if t in (T_VEC, T_COLOR):
                return tuple(round(v, 3)
                             for v in struct.unpack_from('<4f', raw))
        except Exception as ex:
            return '<%s>' % ex
        return raw[:16].hex()

    def fields(self, e, skip=BORING):
        """Nur die Eigenschaften, die wirklich etwas sagen."""
        out = []
        for p in e.props:
            n = self.s(p.hash) or '#%012x' % p.hash
            if n in skip or n == 'name':
                continue
            v = [x for x in self.val(p) if x not in ('', 0, 0.0, False)]
            if not v:
                continue
            out.append((n, v[0] if len(v) == 1 else v))
        return out

    # --- Sichten ----------------------------------------------------------
    def show(self, e, indent='  ', deep=True, seen=None):
        seen = seen if seen is not None else set()
        if e.addr in seen:
            return
        seen.add(e.addr)
        nm = self.name(e)
        print('%s%s%s' % (indent, self.cls(e),
                          '   %s' % nm.split('|')[-1] if nm else ''))
        if nm and '|' in nm:
            print('%s  (%s)' % (indent, nm))
        for n, v in self.fields(e):
            print('%s  %-26s %s' % (indent, n, v))
        if not deep:
            return
        for c in self.children.get(e.addr, ()):
            self.show(c, indent + '    ', deep, seen)

    def demos(self):
        return self.doc.of_class('ShDemoScript')

    def floors(self):
        """Schleife -> Liste der Inszenierungen, die darin laufen."""
        out = collections.defaultdict(list)
        for e in self.demos():
            p = e.get('floorNames')
            fl = [x for x in (self.val(p) if p else []) if x]
            for f in (fl or ['(alle)']):
                out[f].append(e)
        return out

    def touching(self, pat):
        """Jede Entity, deren Name oder irgendein Textwert das enthaelt."""
        pat = pat.lower()
        hits = []
        for e in self.doc.ents:
            if pat in (self.name(e) or '').lower():
                hits.append(e)
                continue
            for _, v in self.fields(e):
                s = (v if isinstance(v, str)
                     else ' '.join(map(str, v))
                     if isinstance(v, (list, tuple)) else str(v))
                if pat in s.lower():
                    hits.append(e)
                    break
        return hits


def main():
    a = sys.argv[1:]
    lvl = a[a.index('--level') + 1] if '--level' in a else 'hallway'
    if '--levels' in a:
        for name in LEVELS:
            try:
                gg = Graph(level=name)
            except Exception as ex:
                print('  %-10s nicht lesbar: %s' % (name, ex))
                continue
            import collections as _c
            c = _c.Counter(gg.cls(e) for e in gg.doc.ents)
            och = [gg.name(e) for e in gg.doc.ents
                   if 'ocho' in (gg.name(e) or '').lower()]
            print('\n=== %-8s %d Entities   StaticModel=%d GeoTrap=%d '
                  'ShDemoScript=%d Gimmick=%d'
                  % (name, len(gg.doc.ents), c.get('StaticModel', 0),
                     c.get('GeoTrap', 0), c.get('ShDemoScript', 0),
                     c.get('ShGimmickLocatorParameter', 0)))
            for o in och:
                print('      Ocho: %s' % o)
            gim = [gg.val(e.get('partsType'))[0]
                   for e in gg.doc.of_class('ShGimmickLocatorParameter')
                   if e.get('partsType')]
            if gim:
                print('      Gimmicks: %s' % ', '.join(gim))
        return
    g = Graph(level=lvl)
    print('  Level %s: %d Entities, %d Strings'
          % (lvl, len(g.doc.ents), len(g.names)))

    def arg(flag):
        i = a.index(flag)
        return a[i + 1] if len(a) > i + 1 else None

    if '--floors' in a:
        fl = g.floors()
        order = ['f005', 'f010', 'f020', 'f030', 'f040', 'f050', 'f060',
                 'f070', 'f080', 'f090', 'f160']
        keys = [k for k in order if k in fl] + [k for k in sorted(fl)
                                                if k not in order]
        for f in keys:
            print('\n=== %s   %d Inszenierung(en)' % (f, len(fl[f])))
            for e in fl[f]:
                d = dict(g.fields(e))
                print('   %-14s %-14s %-44s %s'
                      % (d.get('demoId', '?'), d.get('messageName', '?'),
                         str(d.get('targetData', ''))[:44],
                         os.path.basename(str(d.get('scriptFile', '')))))
        return

    if '--demos' in a:
        want = arg('--demos')
        for e in g.demos():
            d = dict(g.fields(e))
            fl = d.get('floorNames')
            fl = [fl] if isinstance(fl, str) else (fl or [])
            if want and want not in fl:
                continue
            g.show(e)
            print()
        return

    if '--traps' in a:
        for t in g.doc.of_class('GeoTrap'):
            print('\n=== GeoTrap  %s' % g.name(t))
            for nm, c in g.conditions_of(t):
                if c is None:
                    print('   -> %s  (nicht aufloesbar)' % nm)
                    continue
                g.show(c, indent='   ')
        return

    if '--trace' in a:
        pat = arg('--trace')
        for obj, rules, traps in g.trace(pat):
            print('\n=== %s   %s' % (g.cls(obj), g.name(obj)))
            if not rules:
                print('   von NIEMANDEM verwiesen -- im Spiel nie geschaltet')
                continue
            for r, field in rules:
                print('   Regel   %-26s .%s' % (g.name(r, short=True), field))
                for n, v in g.fields(r):
                    print('             %-24s %s' % (n, v))
                for kid in g.children.get(r.addr, ()):
                    print('             + %s' % g.cls(kid))
                    for n, v in g.fields(kid):
                        if n == 'owner':
                            continue
                        print('                 %-20s %s' % (n, v))
            for t, r in traps:
                full = g.name(t)
                floor = [x for x in full.split('|') if x.endswith('_demo')
                         and x != 'common_demo' and x != 'pt14_hallway_demo']
                print('   Ausloeser %-42s Ebene %s'
                      % (g.name(t, short=True),
                         floor[0].replace('_demo', '') if floor else '?'))
        return

    if '--class' in a:
        for e in g.doc.of_class(arg('--class')):
            g.show(e)
            print()
        return

    pat = arg('--grep') or arg('--obj')
    if pat:
        hits = g.touching(pat)
        print('  %d Entities beruehren %r\n' % (len(hits), pat))
        for e in hits:
            g.show(e, deep=False)
            print()
        return

    print(__doc__)


if __name__ == '__main__':
    main()
