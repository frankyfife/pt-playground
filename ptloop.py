"""Wo bin ich gerade? Ebene, Schleife und Level im laufenden Spiel.

Der Nutzer hat den Finger auf die Luecke gelegt: er weiss beim Spielen nicht,
in welcher Schleife er steckt. Ohne das ist jede Ausloeserliste Raten.

Und es ist billig zu haben -- kein Suchlauf, nur eine Zeigerkette. Aus dem
Dekompilat der beiden Lua-Bindungen:

    GetFloorLevel (0x9252d0):
        return *(int *)(*(long *)(0x1c85508 + BASE) + 0xb8) + 8)

    IsCurrentFloorName (0x9253c0) vergleicht den StrCode des Arguments gegen
        (&DAT_01c85590)[index]
    -- also eine **Tabelle von 48-Bit-Namenshashes bei VA 0x1c85590**, mit
    demselben Index. Damit ist nicht nur die Nummer, sondern der NAME der
    Schleife direkt lesbar.

Daraus:

    gc    = [0x1c85508 + BASE]
    fl    = [gc + 0xb8]                 GameFloorLevel
    index = i32[fl + 8]
    hash  = u64[0x1c85590 + BASE + index*8] & 0xffffffffffff
    Name  = strcode64-Umkehr ueber die bekannte Namensliste

`GetLoopCount` (0x925580) ist dagegen ein virtueller Aufruf `vt[8](fl)` und
liefert ein Byte -- der Zaehler steht also in einem Feld, dessen Ablage noch
nicht bekannt ist. Bis dahin wird er gesucht: ein Byte im GameFloorLevel, das
zum Index passt (siehe `loop_candidates`).

    python ptloop.py            einmal anzeigen (auch: was hinter der Tuer liegt)
    python ptloop.py --watch    im Takt mitschreiben
    python ptloop.py --probe    Kandidaten fuer den Schleifenzaehler zeigen
    python ptloop.py --set f040 die Schleife setzen (wirkt beim naechsten
                                Stagewechsel, also nach der naechsten Tuer)
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hover
import ptmem
import strcode

GC_PTR = 0x1C85508          # Zeiger auf den GameController
FL_OFF = 0xB8               # darin: GameFloorLevel
IDX_OFF = 0x08              # darin: der Ebenenindex (int)
NAME_TAB = 0x1C85590        # Tabelle der Ebenennamen-Hashes, 8 Byte je Eintrag
DS_MGR = 0x1C83318          # Verwaltung der geladenen DataSets --
                            # darueber kommt der Levelname ohne Suchlauf
MASK48 = (1 << 48) - 1

# Alle Ebenennamen, die in den fox2 vorkommen -- daraus wird die Tabelle
# zurueckuebersetzt. `ending` und `All` stehen mit drin, weil sie dort als
# floorName auftauchen.
NAMES = ['f000', 'f005', 'f010', 'f020', 'f030', 'f040', 'f050', 'f060',
         'f070', 'f080', 'f090', 'f100', 'f110', 'f120', 'f130', 'f140',
         'f150', 'f160', 'ending', 'All']
BY_HASH = {strcode.strcode64(n) & MASK48: n for n in NAMES}


class Where:
    def __init__(self, p=None, base=None):
        self.p = p or ptmem.Proc(ptmem.find_pid())
        self.base = base if base is not None else hover.find_base(self.p)
        self._level = None

    def ok(self):
        return self.base is not None

    def _u64(self, a):
        d = self.p.read(a, 8) if a else None
        return struct.unpack('<Q', d)[0] if d and len(d) == 8 else None

    def _i32(self, a):
        d = self.p.read(a, 4) if a else None
        return struct.unpack('<i', d)[0] if d and len(d) == 4 else None

    def floor_obj(self):
        gc = self._u64(GC_PTR + self.base)
        return self._u64(gc + FL_OFF) if gc else None

    def index(self):
        fl = self.floor_obj()
        return self._i32(fl + IDX_OFF) if fl else None

    def floor(self):
        """(Index, Name) der laufenden Ebene. Name None, wenn der Hash in der
        Tabelle zu keinem bekannten Namen passt -- dann ist der Index trotzdem
        brauchbar."""
        i = self.index()
        if i is None or not (0 <= i < 64):
            return None, None
        h = self._u64(NAME_TAB + self.base + i * 8)
        if h is None:
            return i, None
        return i, BY_HASH.get(h & MASK48)

    def levels(self):
        """Welche Level geladen sind -- ohne jeden Suchlauf.

        Weg: die DataSet-Verwaltung bei 0x1c83318 fuehrt die geladenen
        Gimmick-DataSets. Aus jedem laesst sich eine Entity greifen, und deren
        Namensblock traegt den vollen Namen mit Levelpraefix
        (`pt14_hallway|...`). Reine Zeigerkette, im Spiel gemessen.

        P.T. haelt zwei Stagekopien. Nennen die beiden VERSCHIEDENE Level, ist
        die zweite die vorgeladene naechste.
        """
        mgr = self._u64(DS_MGR + self.base)
        if not mgr:
            return []
        n = self._i32(mgr + 8)
        arr = self._u64(mgr + 0x10)
        if not arr or not n or not (0 < n < 64):
            return []
        out = []
        for i in range(n):
            ds = self._u64(arr + i * 8)
            if not ds:
                continue
            cnt = self._i32(ds + 0x74)
            vals = self._u64(ds + 0x98)
            if not cnt or not vals:
                continue
            for k in range(min(cnt, 40)):
                ctl = self._u64(vals + k * 0x38)
                ent = self._u64(ctl + 0x18) if ctl else None
                nb = self._u64(ent + 0x28) if ent else None
                if not nb:
                    continue
                d = self.p.read(nb + 0x1c, 160)
                if not d:
                    continue
                j = d.find(bytes([0]))
                nm = d[:j if j >= 0 else 160].decode('ascii', 'replace')
                if '|' in nm:
                    lv = nm.split('|')[0]
                    if lv not in out:
                        out.append(lv)
                    break
        return out

    def level(self, vis_rows=None):
        """Das gerade gespielte Level. `vis_rows` ist nur noch ein Rueckfall."""
        lv = self.levels()
        if lv:
            self._level = lv[0]
        elif vis_rows:
            for r in vis_rows:
                if r.get('full') and '|' in r['full']:
                    self._level = r['full'].split('|')[0]
                    break
        return self._level

    PRETTY = {'pt14_hallway': 'hallway', 'pt14_start': 'start room',
              'pt14_hallway_maze_A': 'maze A',
              'pt14_hallway_maze_B': 'maze B',
              'pt14_hallway_maze_C': 'maze C', 'ending': 'the road'}

    def text(self, vis_rows=None):
        i, name = self.floor()
        if i is None:
            return 'floor unknown - level loaded?'
        lv = self.levels()
        if not lv and vis_rows:
            self.level(vis_rows)
            lv = [self._level] if self._level else []
        here = self.PRETTY.get(lv[0], lv[0]) if lv else 'level ?'
        nxt = ('  (next: %s)' % ', '.join(self.PRETTY.get(x, x) for x in lv[1:])
               if len(lv) > 1 else '')
        return '%s - loop %s (index %d)%s' % (here, name or '?', i, nxt)

    # Die Ablaufreihenfolge, live aus der Tabelle gelesen und als Ablauf
    # bestaetigt (Index 13 -> 14 vorhergesagt und eingetroffen).
    ORDER = ['f000', 'f010', 'f005', 'f020', 'f030', 'f040', 'f060', 'f050',
             'f070', 'f080', 'f090', 'f100', 'f110', 'f120', 'f160', 'ending']

    def table(self, span=24):
        """Die Namenstabelle so, wie sie im Speicher steht."""
        out = []
        for k in range(span):
            h = self._u64(NAME_TAB + self.base + k * 8)
            if h is None:
                break
            out.append(BY_HASH.get(h & MASK48))
        return out

    def set_index(self, i):
        """Den Ebenenindex setzen. Wirkt beim NAECHSTEN Stagewechsel."""
        fl = self.floor_obj()
        if not fl or not (0 <= i < 64):
            return False
        return bool(self.p.write(fl + IDX_OFF, struct.pack('<i', int(i))))

    def set_floor(self, name):
        """Eine Schleife ueber ihren Namen setzen -- der Index kommt aus der
        Tabelle im Speicher, nicht aus einer fest verdrahteten Liste."""
        tab = self.table()
        if name not in tab:
            return False
        return self.set_index(tab.index(name))

    def next_door(self):
        """Was hinter der naechsten Tuer liegt -- Ebene und Level.

        **Ebene:** `AddFloorLevel` zaehlt den Index hoch, und die Namenstabelle
        bei 0x1c85590 steht in der Ablaufreihenfolge. Also ist der naechste
        Eintrag die naechste Schleife.

        **Level:** P.T. haelt zwei Stagekopien und laedt die naechste vor.
        Nennen die beiden DataSets verschiedene Level, ist das zweite das,
        was hinter der Tuer liegt. Nennen sie dasselbe, bleibt es dabei.

        Beides gemessen, nicht geraten -- aber die Ebenenannahme steht und
        faellt damit, dass der Index bei JEDEM Durchgang um eins waechst.
        Das ist noch nicht ueber mehrere Durchgaenge geprueft.
        """
        i, name = self.floor()
        nxt_floor = None
        if i is not None:
            h = self._u64(NAME_TAB + self.base + (i + 1) * 8)
            if h is not None:
                nxt_floor = BY_HASH.get(h & MASK48)
        lv = self.levels()
        nxt_level = lv[1] if len(lv) > 1 else (lv[0] if lv else None)
        return {'floor': name, 'next_floor': nxt_floor,
                'level': lv[0] if lv else None, 'next_level': nxt_level,
                'same_level': len(lv) < 2 or lv[0] == lv[1]}

    def next_text(self):
        """Nennen beide DataSets dasselbe Level, heisst das ZWEIERLEI: es
        kommt wirklich dasselbe, oder die naechste Stage ist noch nicht
        vorgeladen. Unterscheiden koennen wir das nicht -- also behaupten wir
        es auch nicht."""
        d = self.next_door()
        lvl = self.PRETTY.get(d['next_level'], d['next_level']) or '?'
        fl = d['next_floor'] or '?'
        tail = '  (same level, or not preloaded yet)' if d['same_level'] else ''
        return 'behind the next door: %s - loop %s%s' % (lvl, fl, tail)

    def loop_candidates(self, span=0x80):
        """Bytes im GameFloorLevel, die als Schleifenzaehler taugen koennten.

        `GetLoopCount` ist ein virtueller Aufruf und liefert ein Byte. Hier
        werden alle Bytes des Objekts mit dem Ebenenindex zusammen gezeigt --
        wer beim Tuerdurchgang gemeinsam hochzaehlt, ist der Zaehler.
        """
        fl = self.floor_obj()
        if not fl:
            return None, {}
        d = self.p.read(fl, span)
        if not d:
            return fl, {}
        return fl, {o: d[o] for o in range(span)}


def main():
    a = sys.argv[1:]
    if not ptmem.find_pid():
        sys.exit('  shadPS4 laeuft nicht')
    w = Where()
    if not w.ok():
        sys.exit('  Modulbasis nicht gefunden -- ist P.T. geladen?')
    print('  BASE 0x%x   GameFloorLevel 0x%s'
          % (w.base, '%x' % (w.floor_obj() or 0)))

    if '--probe' in a:
        fl, cur = w.loop_candidates()
        print('  GameFloorLevel 0x%x -- Bytes und Ebenenindex im Takt.' % fl)
        print('  Durch eine Tuer gehen; was mit dem Index hochzaehlt, ist der')
        print('  Schleifenzaehler. Strg+C beendet.')
        try:
            while True:
                time.sleep(0.5)
                fl2, new = w.loop_candidates()
                diff = [o for o in new if new[o] != cur.get(o)]
                if diff:
                    i, nm = w.floor()
                geaendert = ' '.join('+0x%02x:%d->%d' % (o, cur.get(o), new[o])
                                     for o in diff[:12])
                if diff:
                    print('   Ebene %s (%s)   %s' % (i, nm, geaendert))
                    cur = new
        except KeyboardInterrupt:
            print('\n  beendet')
        return

    if '--watch' in a:
        print('  Strg+C beendet')
        last = None
        try:
            while True:
                t = w.text()
                if t != last:
                    print('   %s' % t)
                    last = t
                time.sleep(0.5)
        except KeyboardInterrupt:
            print('\n  beendet')
        return

    if '--set' in a:
        want = a[a.index('--set') + 1]
        tab = w.table()
        if want not in tab:
            sys.exit('  %r steht nicht in der Tabelle: %s'
                     % (want, ', '.join(x for x in tab if x)))
        if not w.set_floor(want):
            sys.exit('  Schreiben fehlgeschlagen')
        i, name = w.floor()
        print('  gesetzt auf %s (Index %d)' % (name, i))
        print('  Wirkt beim NAECHSTEN Stagewechsel -- jetzt durch die Tuer.')
        print('  %s' % w.next_text())
        return

    i, name = w.floor()
    print('  Ebenenindex %s   Name %s' % (i, name))
    print('  %s' % w.text())
    print('  %s' % w.next_text())
    h = w._u64(NAME_TAB + w.base + (i or 0) * 8)
    print('  Hash in der Tabelle: %012x' % ((h or 0) & MASK48))
    print('  Tabelle ab 0x%x:' % (NAME_TAB + w.base))
    for k in range(20):
        hh = w._u64(NAME_TAB + w.base + k * 8)
        if hh is None:
            break
        print('     [%2d] %012x  %s' % (k, hh & MASK48,
                                        BY_HASH.get(hh & MASK48, '')))


if __name__ == '__main__':
    main()
