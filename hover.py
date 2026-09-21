"""Lances Schweben fuer P.T. -- ohne Suche, ueber einen festen Zeigerpfad.

Was hier drin steckt
--------------------
Der Spieler faellt auf der Strasse, weil es dort keine Kollision gibt (von
Kojima nie gebaut -- unabhaengig belegt). Lances Loesung war, den Avatar
schweben zu lassen; sein Problem war, die Speicheradresse nach jedem Neustart
wiederzufinden. Genau das entfaellt hier: die Position haengt an einer Kette
aus lauter FESTEN Offsets, die bei jedem Start neu abgelaufen wird.

    BASE    ueber ein 48-Byte-Codemuster ab FUN_0093fc80 im Prozess gesucht
    Spieler [0x1c91f58 + BASE] - 0x20        vptr == 0x1bcd630 + BASE
    Kontext [Spieler + 0x190]
    A       [Kontext + 8]                    vptr VA 0x1bceda0
    elem    [A + 0x10] + (0 - (int)[A + 0xc]) * 0x1a8
    obj     [elem + 0x58]                    vptr VA 0x1bd9be0

`vt[0x2c0]` (0x1257e50) ist reine Adressrechnung und wird hier nachgerechnet
statt im Spiel aufgerufen -- deshalb braucht das Ganze keinen eboot-Eingriff.

Die drei Felder, die zusammen gehalten werden muessen (einzeln wirkungslos,
gemeinsam traegt es -- die Engine rechnet offenbar aus mehreren):

    obj+0x30   Position der Fuesse       Y-Basis
    obj+0x40   Position der Kapselmitte  Y + 0.8  (Kapselmasse in obj+0x180)
    obj+0x130  dritte Kopie              Y-Basis

X und Z werden JEDE Runde frisch gelesen und unveraendert zurueckgeschrieben --
nur Y wird genagelt. Deshalb laesst sich weiterlaufen, und deshalb ist es ein
Schweben und kein Festhalten an einem Punkt.

    python hover.py                # schweben auf 0.5 m ueber dem Boden
    python hover.py --height 1.2
    python hover.py --atomic       # Versuchsvariante: Bloecke statt Einzelwerte
    python hover.py --show         # nur anzeigen, nichts schreiben

shadPS4 muss laufen. Abbruch mit Strg+C.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elfout
import ptmem

CAPSULE = 0.8          # Abstand Fuesse -> Kapselmitte, aus obj+0x180 gelesen
ANCHOR_VA = 0x93FC80   # Codemuster fuer die Basissuche
PLAYER_HOLDER = 0x1C91F58
PLAYER_VT = 0x1BCD630
A_VT = 0x1BCEDA0
OBJ_VT = 0x1BD9BE0
FIELDS = (0x30, 0x40, 0x130)


def find_base(p):
    """BASE = Fundstelle des Musters - (VA - 0x400000) - 0x400000.

    Der Emulator laedt das Modul bei jedem Start woanders hin; ein eindeutiges
    Codemuster ist der einzige verlaessliche Anker. 48 Bytes reichen -- im
    ganzen Prozess gibt es genau eine Fundstelle.
    """
    d = open(elfout.EBOOT, 'rb').read()
    mp = elfout._selfmap(d)
    off = None
    for fo, base, sz in mp:
        if base <= ANCHOR_VA < base + sz:
            off = fo + (ANCHOR_VA - base)
    pat = d[off:off + 48]
    for b, s in p.regions():
        if s > 0x8000000:
            continue
        blob = p.read(b, s)
        if not blob:
            continue
        i = blob.find(pat)
        if i >= 0:
            return (b + i) - ANCHOR_VA
    return None


def chain(p, base, log=print):
    """Vom statischen Zeiger bis zum Objekt mit der Position."""
    def q(a):
        d = p.read(a, 8)
        return struct.unpack('<Q', d)[0] if d and len(d) == 8 else None

    def i32(a):
        d = p.read(a, 4)
        return struct.unpack('<i', d)[0] if d and len(d) == 4 else None

    holder = q(PLAYER_HOLDER + base)
    if not holder:
        return None, 'Spielerzeiger nicht lesbar -- laeuft das Spiel schon?'
    player = holder - 0x20
    if q(player) != PLAYER_VT + base:
        return None, 'vptr am Spieler passt nicht (0x%x)' % (q(player) or 0)
    ctx = q(player + 0x190)
    A = q(ctx + 8) if ctx else None
    if not A or q(A) != A_VT + base:
        return None, 'A fehlt oder hat den falschen vptr'
    arr, idx = q(A + 0x10), i32(A + 0xc)
    obj = q(arr + (0 - idx) * 0x1a8 + 0x58) if arr is not None else None
    if not obj or q(obj) != OBJ_VT + base:
        return None, 'obj fehlt oder hat den falschen vptr'
    log('  Spieler 0x%x   obj 0x%x' % (player, obj))
    return obj, None


def main():
    args = sys.argv[1:]
    height = 0.5
    if '--height' in args:
        height = float(args[args.index('--height') + 1])

    pid = ptmem.find_pid()
    if not pid:
        sys.exit('  shadPS4 laeuft nicht')
    p = ptmem.Proc(pid)
    base = find_base(p)
    if base is None:
        sys.exit('  Modulbasis nicht gefunden -- ist P.T. geladen?')
    print('  BASE 0x%x' % base)
    obj, err = chain(p, base, log=print)
    if err:
        sys.exit('  ' + err)

    d = p.read(obj + 0x180, 16)
    cap = struct.unpack('<4f', d)[0] if d else CAPSULE
    print('  Kapselhoehe aus obj+0x180: %.3f' % cap)

    if '--show' in args:
        for f in FIELDS:
            print('  obj+0x%-4x = %s' % (f, struct.unpack('<4f', p.read(obj + f, 16))))
        return

    atomic = '--atomic' in args
    print('  schwebe auf %.2f m%s -- Strg+C beendet'
          % (height, '  [atomic]' if atomic else ''))
    lo = struct.pack('<f', height)
    hi = struct.pack('<f', height + cap)
    zero = struct.pack('<f', 0.0)
    n = 0
    try:
        while True:
            # X und Z bleiben unangetastet: nur die vier Y-Bytes schreiben.
            #
            # Die drei ersten allein reichen NICHT -- damit laeuft man zwar auf
            # der Strasse, sinkt aber langsam durch. Gemessen, waehrend sie
            # gehalten wurden:
            #     obj+0x74   -24.50 in 2.5 s  = -9.8 m/s^2  -> Y-GESCHWINDIGKEIT
            #     obj+0x54 / +0x64 / +0x194   -0.41 in 2.5 s (davon getrieben)
            # Die Anzeige nimmt diese zweite Ablage. Also alle halten, und vor
            # allem die Geschwindigkeit auf null nageln, damit nichts mehr
            # aufsummiert. Nur Y -- die waagerechte Geschwindigkeit bleibt,
            # sonst koennte man sich nicht bewegen.
            if atomic:
                # Variante --atomic: die zusammenhaengenden Felder in EINEM
                # Schreibvorgang statt einzeln. X, Z und die waagerechte
                # Geschwindigkeit werden dabei frisch gelesen und unveraendert
                # zurueckgeschrieben. Der Gedanke: die Engine sieht nie einen
                # halb aktualisierten Satz.
                a = p.read(obj + 0x30, 0x18)
                b = p.read(obj + 0x50, 0x28)
                if not a or not b:
                    print('\n  Spiel beendet -- Schweben nach %d Runden gestoppt' % n)
                    return
                a = bytearray(a); b = bytearray(b)
                a[0x04:0x08] = lo      # +0x34  Fuesse
                a[0x14:0x18] = hi      # +0x44  Kapselmitte
                b[0x04:0x08] = lo      # +0x54
                b[0x14:0x18] = lo      # +0x64
                b[0x24:0x28] = zero    # +0x74  Y-Geschwindigkeit
                p.write(obj + 0x30, bytes(a))
                p.write(obj + 0x50, bytes(b))
                p.write(obj + 0x134, lo)
                p.write(obj + 0x194, lo)
            else:
                # Die bewaehrte Fassung: alle sieben in jeder Runde einzeln.
                # Eine Variante, die die vier "ruhigen" Felder nur jede achte
                # Runde schrieb, war im Spiel deutlich NERVOESER -- die Anzeige
                # braucht offenbar alle Werte zueinander passend, nicht nur die
                # umkaempften. Nicht wieder ausduennen.
                p.write(obj + 0x30 + 4, lo)
                p.write(obj + 0x40 + 4, hi)
                p.write(obj + 0x130 + 4, lo)
                p.write(obj + 0x54, lo)
                p.write(obj + 0x64, lo)
                p.write(obj + 0x194, lo)
                p.write(obj + 0x74, zero)
            n += 1
            if n % 200000 == 0:
                # Wird das Spiel geschlossen, liefert read() None. Sauber
                # aufhoeren statt mit einem Traceback aus dem Hintergrundlauf
                # zu fallen -- das sagt sonst nicht, was eigentlich passiert ist.
                d = p.read(obj + 0x30, 16)
                if not d:
                    print('\n  Spiel beendet -- Schweben nach %d Runden gestoppt' % n)
                    return
                print('  ... (%.3f, %.3f, %.3f)' % struct.unpack('<4f', d)[:3])
    except KeyboardInterrupt:
        print('\n  beendet nach %d Schreibrunden' % n)


if __name__ == '__main__':
    main()
