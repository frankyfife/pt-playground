# -*- coding: utf-8 -*-
r"""Tueren in P.T. -- Zustand lesen und aufmachen, ohne das Archiv neu zu bauen.

Wie eine Tuer in P.T. wirklich funktioniert
-------------------------------------------
Belegt am 13.09.2026 aus `pt14_hallway.fox2`, nicht geraten:

Es gibt fuenf `trap_DoorGacha*` (japanisch *gacha* = klappernde Klinke, also
"verschlossen"). Jeder fuehrt ein `ShTrapExecDoorCallbackDataElement` mit

    funcName       ExecDoor
    checkLocator   pt14_hallway|pt14_hallway_environ|shsb_hous001_door002_lobby
    soundId        Play_sfx_door_hit_01

Die Sperre ist also **keine Wand, sondern eine Pruefung**: der Trap sieht
nach, ob die GESCHLOSSENE Tuervariante aktiv ist. Eine Tuer ist in P.T. ein
Variantentausch, keine Animation:

    zu                              offen
    shsb_hous001_door002_lobby      shsb_hous001_door002_lobby_open
    shsb_hous001_door002_bathroom   shsb_hous001_door002_bathroom_20 / _170

Und die Umschaltung steht ebenfalls in den Daten. Jede `GeoModuleCondition`
mit `execFuncNames = LuaScript` traegt vier Felder:

    floorName      die Schleife
    staticModel    das Objekt
    isVisible      sichtbar danach
    isGeomActive   Kollision danach

Daraus die Tuerzeilen (29 Umschaltungen gibt es im ganzen Spiel;
`ptfloors.py` liest sie aus den GeoModuleConditions):

    f005  lobby       versteckt / Kollision aus  \\  5_trap_change_static_model
    f005  lobby_open  sichtbar  / Kollision an   /   -> Tuer OFFEN
    f030  lobby       versteckt / Kollision AN       2_trap_demo_gc_p01_011
    f060  lobby       versteckt / Kollision aus  \\  4_trap_demo_gc_p01_090
    f060  lobby_open  sichtbar  / Kollision an   /   -> Tuer OFFEN

Was im Spiel gemessen wurde -- und was daran falsch war
------------------------------------------------------
Der Tausch allein reicht NICHT. Im Spiel (f060, 13.09.2026) war danach das
offene Tuerblatt zu sehen, der Weg blieb aber gesperrt und das Klappern
spielte weiter. Also stimmt die Ableitung "Kollision = isGeomActive" nicht.

Der eboot sagt, was das Schloss wirklich liest. `ExecDoor` wird in
FUN_00917310 unter dem Namen registriert und haengt an der Vtable 0x1bcb300;
Slot +0x18 ist FUN_009165c0, dessen Hauptzweig FUN_00916670 vor dem Klappern
FUN_00916b70 fragt. Die Funktion endet auf genau einer Pruefung:

    lVar4 = FUN_004e8c40(local_40);          // Body des checkLocator
    bVar5 = *(char *)(lVar4 + 0x80) != 0;    // isVisible

Also `body+0x80`, nicht `+0x81`. Und `ptvis.Session.set` schreibt dieses Byte
grundsaetzlich auf 1 -- auch beim Ausblenden:

    p.write(r['body'] + B_ISVISIBLE, b'\x01')       # immer 1
    p.write(r['body'] + B_ISGEOM, b'\x01' if on else b'\x00')

Damit sah das Schloss die geschlossene Tuer weiter, egal was sonst geschaltet
wurde. Genau das war zu hoeren. `set_lock()` zieht das Byte darum nach; an
ptvis selbst wird nichts geaendert, dort ist das Verstecken so belegt.

OFFEN BLEIBT die Kollision. Dass der Weg auch durch das OFFENE Blatt gesperrt
ist und die ausgeblendete `door005_close` weiter blockt, heisst: die Kollision
des Flurs haengt nicht an diesen Modellen. In P.T. geht man durch die Endtuer
ohnehin nicht hindurch -- den Wechsel macht `trap_unloadAndChangeStage`. Wer
nur weiterkommen will, nimmt den Trap, nicht die Tuer.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptmem
import ptvis

# Die Paare aus den fox2-Bedingungen. Links zu, rechts offen.
# Rechts stehen ALLE Offen-Varianten, in der Reihenfolge der Bevorzugung.
# Die Badtuer hat zwei: `_170` ist ganz auf, `_20` nur einen Spalt, und je
# nach Floor laedt das Spiel die eine oder die andere.
PAIRS = [
    ('lobby',    'shsb_hous001_door002_lobby',
                 ('shsb_hous001_door002_lobby_open',)),
    ('bathroom', 'shsb_hous001_door002_bathroom',
                 ('shsb_hous001_door002_bathroom_170',
                  'shsb_hous001_door002_bathroom_20')),
    ('hallway',  'shsb_hous001_door001_hallway_in',
                 ('shsb_hous001_door001_hallway_out',)),
]
# door005_close traegt "close" im Namen und hat kein offenes Gegenstueck --
# das ist die zweite Tuer am Flurende. Sie wird beim Oeffnen nur abgeschaltet.
SOLO_CLOSED = ['shsb_hous001_door005_close']

ALL = [n for _, a, b in PAIRS for n in (a,) + b] + SOLO_CLOSED


def rows_by_name(s):
    """Die gefundenen Zeilen nach kurzem Objektnamen gruppieren."""
    out = {}
    for r in s.rows:
        out.setdefault(r['short'], []).append(r)
    return out


def state(s, log=print):
    """Je Tuer und Kopie: zu oder offen.

    Die Kopien werden ueber die Weltlage unterschieden, nicht ueber die
    Adresse -- die Adresse sagt nichts darueber, in welcher der Spieler steht.
    """
    by = rows_by_name(s)
    log('  %-16s %-5s %-34s %-6s %-6s %s'
        % ('Tuer', 'Kopie', 'Objekt', 'sicht', 'kolli', 'Lage'))

    def line(tag, nm, i, r):
        st = s.state(r)
        pos = ('(%7.2f, %6.2f, %7.2f)' % r['pos']) if r.get('pos') else ''
        log('  %-16s %-5s %-34s %-6s %-6s %s'
            % (tag, '#%d' % i, nm[:34],
               'AN' if s.is_on(r) else 'aus',
               'an' if st.get('isgeom') else 'aus', pos))

    for tag, closed, opened in PAIRS:
        for kind, nm in ([('zu', closed)]
                         + [('offen', o) for o in opened]):
            for i, r in enumerate(by.get(nm, [])):
                line('%s/%s' % (tag, kind), nm, i, r)
        # Was heisst das zusammen? Zu ist eine Tuer, wenn die geschlossene
        # Variante Kollision hat -- genau das prueft trap_DoorGacha*.
        for i in range(max([len(by.get(closed, []))]
                           + [len(by.get(o, [])) for o in opened])):
            cl = by.get(closed, [])[i] if i < len(by.get(closed, [])) else None
            zu = bool(cl and s.state(cl)['isgeom'])
            log('  %-16s %-5s -> %s' % ('= %s' % tag, '#%d' % i,
                                        'ZU' if zu else 'offen'))
    for nm in SOLO_CLOSED:
        for i, r in enumerate(by.get(nm, [])):
            line('sperre', nm, i, r)


def offen_variante(opened, s=None):
    """Die Offen-Variante, die in der geladenen Kulisse wirklich liegt.

    Ohne Sitzung laesst sich das nicht wissen; dann gilt die erste. `apply()`
    wirft ohnehin weg, wozu es keine Zeile findet -- falsch waere es also
    nicht, nur wirkungslos.
    """
    if s is not None:
        da = set(r['short'] for r in s.rows)
        for nm in opened:
            if nm in da:
                return nm
    return opened[0]


def wanted(which=None, opening=True, s=None):
    """Der Sollzustand als {Objektname: sichtbar}.

    Genau der Tausch, den das Spiel in f005 und f060 selbst ausfuehrt.
    `ptvis.Session.set` schreibt Sichtbarkeit und `isGeomActive` gemeinsam,
    also traegt eine Angabe je Objekt.

    Beim OEFFNEN wird genau eine Offen-Variante sichtbar -- die, die in der
    Kulisse liegt; die uebrigen bleiben aus, sonst staenden zwei Tuerblaetter
    ineinander. Beim SCHLIESSEN gehen alle aus.
    """
    want = {}
    for tag, closed, opened in PAIRS:
        if which and which != tag:
            continue
        want[closed] = not opening
        nimm = offen_variante(opened, s) if opening else None
        for nm in opened:
            want[nm] = (nm == nimm)
    if not which or which == 'lobby':
        for nm in SOLO_CLOSED:
            want[nm] = not opening
    return want


def set_lock(s, want, log=print):
    """Das eine Byte, das das Schloss wirklich liest.

    Aus dem eboot belegt, nicht geraten. `ExecDoor` haengt an der Vtable
    0x1bcb300, deren Slot +0x18 auf FUN_009165c0 zeigt; der Hauptzweig
    FUN_00916670 fragt vor dem Klappern FUN_00916b70, und die Funktion endet
    auf genau einer Pruefung:

        lVar4 = FUN_004e8c40(local_40);          // Body des checkLocator
        bVar5 = *(char *)(lVar4 + 0x80) != 0;    // isVisible

    Geklappert wird also, solange `body+0x80` des GESCHLOSSENEN Tuermodells
    steht. `ptvis.Session.set` schreibt dieses Byte aber grundsaetzlich auf 1
    -- auch beim Ausblenden (dort ist das so belegt und bleibt so). Fuer
    Tueren muss es danach gesetzt werden, sonst sieht das Schloss die Tuer
    weiter und der Tausch bleibt wirkungslos. Genau das war im Spiel zu
    hoeren.
    """
    n = 0
    for r in s.rows:
        if r['short'] not in want or not r['body']:
            continue
        val = b'\x01' if want[r['short']] else b'\x00'
        s.p.write(r['body'] + ptvis.B_ISVISIBLE, val)
        n += 1
    if n:
        log('     body+0x%02x (isVisible, das Schloss liest es) an %d '
            'Fundstellen gesetzt' % (ptvis.B_ISVISIBLE, n))
    return n


def apply(s, want, log=print):
    todo = {k: v for k, v in want.items()
            if any(r['short'] == k and s.needs(r, v) for r in s.rows)}
    if todo:
        n = s.apply(todo)
        for k in sorted(todo):
            log('     %-34s -> %s' % (k, 'AN' if todo[k] else 'aus'))
    else:
        n = 0
        log('  Sichtbarkeit steht schon so')
    # Immer nachziehen, auch wenn `needs` nichts zu tun sah: das Schlossbyte
    # geht in `needs` nicht ein, und ptvis setzt es beim Ausblenden auf 1.
    set_lock(s, want, log=log)
    return n


def main():
    a = sys.argv[1:]
    if not ptmem.find_pid():
        sys.exit('  shadPS4 laeuft nicht')
    s = ptvis.Session()
    if not s.ok():
        sys.exit('  Modulbasis nicht gefunden -- ist P.T. geladen?')
    print('  BASE 0x%x' % s.base)
    s.scan()
    print('  %d StaticModel' % len(s.rows))
    s.rows = [r for r in s.rows if r['short'] in ALL]
    print('  %d Tuerfundstellen' % len(s.rows))
    print()

    which = None
    for tag, _, _ in PAIRS:
        if tag in a:
            which = tag

    if '--open' in a or '--close' in a:
        opening = '--open' in a
        want = wanted(which, opening, s)
        print('  %s %s' % ('oeffne' if opening else 'schliesse',
                           which or 'alle Tueren'))
        apply(s, want)
        if '--hold' in a:
            print()
            print('  halte den Zustand -- Strg+C beendet')
            try:
                n = 0
                while True:
                    if not s.valid():
                        s.scan()
                        s.rows = [r for r in s.rows if r['short'] in ALL]
                    todo = {k: v for k, v in want.items()
                            if any(r['short'] == k and s.needs(r, v)
                                   for r in s.rows)}
                    if todo:
                        s.apply(todo)
                        n += 1
                        print('   %s  nachgezogen (%d x)'
                              % (time.strftime('%H:%M:%S'), n))
                    # Das Schlossbyte JEDE Runde -- ptvis setzt es beim
                    # Ausblenden auf 1 zurueck, und `needs` sieht es nicht.
                    set_lock(s, want, log=lambda *x: None)
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print()
                print('  beendet')
        return

    state(s)
    print()
    print('  --open lobby   tauscht die Tuer am Flurende auf offen')


if __name__ == '__main__':
    main()
