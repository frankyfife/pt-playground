"""Das Drehbuch: welche Ausloeser sind scharf -- lesen und selbst setzen.

Die Idee
--------
P.T. treibt seinen Fortschritt, indem es Ausloeser **scharf schaltet**: die
Regeln mit `setEnable` schalten andere Traps und DemoScripts ein
(`condition_enable_demo_all`, `condition_enable_trap_all`, ...). Ein Trap, der
nicht scharf ist, feuert nicht, auch wenn man mitten hineinlaeuft.

Damit ist die Liste, die der Nutzer haben will, genau diese: je Schleife alle
Ausloeser mit einem Haken, der sagt, ob sie **scharf** sind. Der Haken zieht
sich von selbst, wenn das Spiel den Trap im regulaeren Ablauf scharf schaltet,
und man kann ihn selbst setzen, um den Schritt zu ueberspringen.

Die Offsets -- aus den Klassenregistrierungen, nicht geraten
-----------------------------------------------------------
    GeoTrap             enable      bool bei **+0x140**   (FUN_00bf6850)
    GeoModuleCondition  isAndCheck  bool bei **+0x13e**   (FUN_00beca50)

Beide erben `TransformData`, also gelten auch `flags` bei +0xb8 und der
Namensblock bei `[ent+0x28]` -- dieselbe Bauart wie bei den StaticModel.
Deshalb sind sie ueber ihren Klartextnamen zu finden, ohne ihren vptr zu
kennen (`ptvis.find_named`).

Was der Haken NICHT sagt
------------------------
"scharf" ist nicht dasselbe wie "schon gefeuert". Ein `isOnce`-Trap hat
intern ein Merkbit dafuer, das in keiner Registrierung steht -- das muss noch
per Differenzaufnahme gefunden werden. Bis dahin zeigt die Liste den
Scharfzustand, und das ist der Hebel, den das Spiel selbst benutzt.

    python ptsteps.py                  alle Ausloeser mit Zustand
    python ptsteps.py --floor f040     nur eine Schleife
    python ptsteps.py --arm demo_gc_p04_310
    python ptsteps.py --disarm trap_demo_stop
    python ptsteps.py --watch          Aenderungen mitschreiben
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptmem
import ptvis

T_ENABLE = 0x140            # GeoTrap.enable
E_FLAGS = 0xB8              # TransformData.flags -- 6 oder 7
MOD_LO = 0x400000           # Modulbereich, damit ein vptr als solcher gilt
MOD_HI = 0x1EB0000          # (Vtables liegen in .bss, muessen mitzaehlen)
C_ANDCHECK = 0x13E          # GeoModuleCondition.isAndCheck
E_NAMEBLOCK = ptvis.E_NAMEBLOCK
N_TEXT = ptvis.N_TEXT

WATCH_MS = 400


class Steps:
    """Die Ausloeser im laufenden Spiel, verknuepft mit dem Plan aus der fox2."""

    def __init__(self, p=None, level='hallway'):
        self.p = p or ptmem.Proc(ptmem.find_pid())
        self.m = ptvis.Mem(self.p)
        import hover
        self.base = hover.find_base(self.p)
        self.level = level
        self.plan = {}
        self.full_names = []
        self.pos = {}             # voller Name -> (x, y, z) des Volumens
        self.rows = []

    def ok(self):
        return self.base is not None

    def load_plan(self):
        """Neben dem Plan auch die VOLLEN Trap-Namen -- die braucht die
        Speichersuche, weil sie nach deren Hash sucht."""
        """Aus der fox2: je Trap die Schleifen, Pruefungen und Wirkungen.
        Das ist der Text zu jedem Haken -- ohne ihn ist die Liste nur eine
        Sammlung von Namen."""
        import struct as _st

        import ptfloors
        import ptlogic
        g = ptlogic.Graph(level=self.level)
        self.full_names = []
        # Die Lage JE TRAP -- nicht aus den zusammengefassten Regelzeilen, die
        # fuehren mehrere Traps in einer Zelle und damit nur die erste Lage.
        for t in g.doc.of_class('GeoTrap'):
            nm = g.name(t)
            if not nm:
                continue
            self.full_names.append(nm)
            tf = t.get('transform')
            if not tf:
                continue
            e = g.by_addr.get(_st.unpack('<Q', tf.value(0)[:8])[0])
            pr = e.get('transform_translation') if e is not None else None
            if pr:
                self.pos[nm] = _st.unpack('<3f', pr.value(0)[:12])
        for r in ptfloors.dedupe(ptfloors.collect(g)):
            for t in r['trap'].split(', '):
                e = self.plan.setdefault(t, {'floors': [], 'rules': []})
                for f in r['floors']:
                    if f not in e['floors']:
                        e['floors'].append(f)
                e['rules'].append({
                    'rule': r['rule'], 'check': r['check'],
                    'effect': r['effect'], 'target': r['target'],
                    'script': r['script'], 'demo': r['demo'],
                    'loop': r['loop']})
        return self.plan

    def scan(self, log=None):
        """Alle GeoTrap im Speicher -- ueber den Klartextnamen, damit die
        Klasse nicht bekannt sein muss. Zwei Suchlaeufe, rund 18 s."""
        if not self.plan or not self.full_names:
            self.load_plan()
        # Nicht per Textsuche: wir KENNEN die vollen Namen aus der fox2, und
        # der Namensblock fuehrt deren StrCode64 bei +0x10. `find_by_names`
        # sucht genau danach -- exakt statt geraten, und der Blockanfang
        # ergibt sich, statt aus der Fundstelle gerechnet zu werden.
        rows = []
        for full, ents in ptvis.find_by_names(self.p, list(self.full_names),
                                              log=log).items():
            short = full.split('|')[-1]
            pl = self.plan.get(short, {})
            for ent in ents:
                if not self._is_entity(ent):
                    continue
                rows.append({'ent': ent, 'name': full, 'short': short,
                             'floors': pl.get('floors', []),
                             'rules': pl.get('rules', []),
                             'pos': self.pos.get(full),
                             'armed': self.armed_at(ent)})
        rows.sort(key=lambda r: (r['floors'][:1], r['short']))
        self.rows = rows
        if log:
            n = sum(1 for r in rows if r['armed'])
            log('  %d Ausloeser gefunden, %d davon scharf' % (len(rows), n))
        return rows

    def _is_entity(self, ent):
        """Ist das wirklich ein GeoTrap und nicht nur irgendein Zeiger auf den
        Namensblock?

        Der Namensblock wird von vielen Stellen referenziert -- Stringtabelle,
        Hashtabellen, Kopien. Ohne Filter kamen 1553 Kandidaten statt 168
        (84 Traps je Flurkopie). Zwei Merkmale genuegen und sind beide aus dem
        Aufbau belegt: ein vptr im Modulbereich, und `flags` als TransformData-
        Erbe mit 6 oder 7.

        Gegengeprueft: mit diesem Filter stimmt das `enable`-Byte bei allen 84
        Namen mit dem der fox2 ueberein.
        """
        vt = self.m.u64(ent)
        if vt is None or not (MOD_LO + self.base <= vt <= MOD_HI + self.base):
            return False
        return (self.m.u32(ent + E_FLAGS) or 0) in (6, 7)

    E_WORLD = 0xF0            # letzte Zeile der Weltmatrix (TransformData)

    def world_pos(self, r):
        """Die WELTlage des Trap-Volumens.

        Nicht die aus der fox2 nehmen -- die ist relativ zur Levelwurzel, und
        die beiden Flurkopien stehen an verschiedenen Stellen der Welt. Wer
        die Dateikoordinate als Weltkoordinate benutzt, landet im Nirgendwo
        (im Spiel passiert, zweimal).
        """
        d = self.p.read(r['ent'] + self.E_WORLD, 12)
        if not d or len(d) != 12:
            return None
        import struct as _st
        v = _st.unpack('<3f', d)
        return None if all(abs(x) < 0.01 for x in v) else v

    def nearest(self, rows, to):
        """Von mehreren Kopien die, die dem Spieler am naechsten steht."""
        best, bd = None, None
        for r in rows:
            w = self.world_pos(r)
            if not w:
                continue
            d = sum((a - b) ** 2 for a, b in zip(w, to))
            if bd is None or d < bd:
                best, bd = r, d
        return best

    # --- lesen und schreiben ----------------------------------------------
    def armed_at(self, ent):
        v = self.m.u8(ent + T_ENABLE)
        return None if v is None else bool(v)

    def valid(self):
        if not self.rows:
            return False
        for r in self.rows[::max(1, len(self.rows) // 6)]:
            nb = self.m.u64(r['ent'] + E_NAMEBLOCK)
            if not nb or self.m.text(nb + N_TEXT) != r['name']:
                return False
        return True

    def refresh(self):
        for r in self.rows:
            r['armed'] = self.armed_at(r['ent'])
        return self.rows

    def set(self, r, on):
        self.p.write(r['ent'] + T_ENABLE, b'\x01' if on else b'\x00')
        r['armed'] = on

    def match(self, pat):
        pat = pat.lower()
        return [r for r in self.rows if pat in r['short'].lower()]


def describe(r):
    """Eine Zeile Klartext zu einem Ausloeser."""
    if not r['rules']:
        return '(nicht im Plan)'
    out = []
    for x in r['rules'][:3]:
        bits = [x['rule']]
        if x['effect']:
            bits.append(x['effect'])
        if x['target']:
            bits.append('-> ' + x['target'][:40])
        out.append('  '.join(bits))
    if len(r['rules']) > 3:
        out.append('... %d weitere' % (len(r['rules']) - 3))
    return ' | '.join(out)


def main():
    a = sys.argv[1:]
    if not ptmem.find_pid():
        sys.exit('  shadPS4 laeuft nicht')
    s = Steps()
    if not s.ok():
        sys.exit('  Modulbasis nicht gefunden -- ist P.T. geladen?')
    print('  BASE 0x%x' % s.base)
    s.scan(log=print)

    only = a[a.index('--floor') + 1] if '--floor' in a else None
    for flag, on in (('--arm', True), ('--disarm', False)):
        if flag in a:
            pat = a[a.index(flag) + 1]
            tg = s.match(pat)
            if not tg:
                sys.exit('  kein Ausloeser passt auf %r' % pat)
            for r in tg:
                s.set(r, on)
                print('  %-8s %s' % ('scharf' if on else 'aus', r['short']))
            return

    print()
    for r in s.rows:
        if only and only not in r['floors']:
            continue
        print('   [%s] %-14s %-40s 0x%x'
              % ('x' if r['armed'] else ' ', ','.join(r['floors']) or '-',
                 r['short'][:40], r['ent']))
        print('        %s' % describe(r)[:150])

    if '--watch' in a:
        print('\n  beobachte %d Ausloeser -- Strg+C beendet' % len(s.rows))
        prev = {r['ent']: r['armed'] for r in s.rows}
        try:
            while True:
                time.sleep(WATCH_MS / 1000.0)
                for r in s.refresh():
                    if prev.get(r['ent']) != r['armed']:
                        print('   %-8s %-40s %s'
                              % ('SCHARF' if r['armed'] else 'aus',
                                 r['short'][:40],
                                 ','.join(r['floors']) or '-'))
                        prev[r['ent']] = r['armed']
        except KeyboardInterrupt:
            print('\n  beendet')


if __name__ == '__main__':
    main()
