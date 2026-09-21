"""P.T.s Bewegungsparameter finden und stellen -- Struktur aus dem Code gelesen.

Herkunft der Struktur
---------------------
Nicht geraten. `FUN_012520d0` im P.T.-eboot ist der Parser von
`ShParameter.ReloadParameterTables`; dort steht woertlich:

    FUN_00952440(&t, "front",          &min_f, &max_f);
    FUN_00952440(&t, DAT_01422314,     &min_l, &max_l);   // "left"
    FUN_00952440(&t, DAT_01422319,     &min_b, &max_b);   // "back"
    FUN_00952440(&t, "right",          &min_r, &max_r);
    puVar2[4] = min_f;  puVar2[5] = min_l;
    puVar2[6] = min_b;  puVar2[7] = min_r;
    *puVar2   = max_f;  puVar2[1] = max_l;
    puVar2[2] = max_b;  puVar2[3] = max_r;
    puVar2[8]  = focalLength;
    puVar2[9]  = rotVelMaxX * (PI/180);
    puVar2[10] = rotVelMaxY * (PI/180);
    puVar2[11] = rotInterpHalfLife;

Also ein Float-Feld: erst die vier **max**, dann die vier **min**, dann die
Kamera. Die Namen der beiden DAT-Konstanten wurden im eboot nachgeschlagen,
`_DAT_01422010` ist 0.0174533 = PI/180.

Daraus folgt auch, warum eine Suche nach `rotVelMax = 108.75` nie etwas findet:
im Speicher steht der Wert im **Bogenmass** (1.898).

Gefunden wird ueber `focalLength` (13.0) auf Index 8 zusammen mit
`rotInterpHalfLife` (1/30) auf Index 11 -- zwei feste Werte in festem Abstand,
das ist eine belastbare Unterschrift. Der Blockanfang ist dann Anker - 0x20.

    python paramscan.py              suchen und zeigen
    python paramscan.py --speed 2.0  Tempo verdoppeln
    python paramscan.py --speed 1.0  zurueck auf die Vorgabe

Adressen wandern bei jedem Spielstart, deshalb sucht jeder Aufruf neu.
P.T. muss laufen.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptmem

FOCAL = 13.0                 # puVar2[8]
HALFLIFE = 2.0 / 60.0        # puVar2[11]
ANCHOR_GAP = 0xc             # Abstand [8] -> [11]
BASE_BACK = 0x20             # Abstand [8] -> [0]

# Reihenfolge exakt wie im Dekompilat, mit den Vorgaben aus
# ShParameterTables.lua
FIELDS = [('front.max', 1.00), ('left.max', 0.75), ('back.max', 0.50),
          ('right.max', 0.75), ('front.min', 0.50), ('left.min', 0.40),
          ('back.min', 0.25), ('right.min', 0.40)]
DEFAULTS = [v for _, v in FIELDS]


def find(p):
    """Alle Bloecke: focalLength auf [8] UND rotInterpHalfLife auf [11]."""
    a, b = struct.pack('<f', FOCAL), struct.pack('<f', HALFLIFE)
    out = []
    for base, size in p.regions():
        if size > 0x10000000:
            continue
        blob = p.read(base, size)
        if not blob:
            continue
        i = blob.find(a)
        while i >= 0:
            if blob[i + ANCHOR_GAP:i + ANCHOR_GAP + 4] == b and i >= BASE_BACK:
                out.append(base + i - BASE_BACK)
            i = blob.find(a, i + 4)
    return out


def read(p, base):
    d = p.read(base, 0x30)
    return list(struct.unpack('<12f', d)) if d and len(d) == 0x30 else None



# ---------------------------------------------------------------------------
# Der Block, der zur Laufzeit WIRKLICH gelesen wird
# ---------------------------------------------------------------------------
# Gemessen am 19.08. im laufenden Spiel: der ueber die Kamera-Unterschrift
# gefundene Block (oben) laesst sich beschreiben, die Werte bleiben stehen --
# und das Tempo aendert sich NICHT. Er wird beim Laden ausgewertet und danach
# nicht mehr gelesen. Deshalb wirkt die Lua-Tabelle statisch, aber nichts
# davon dynamisch.
#
# Beim Laden werden die acht Werte in eine zweite Struktur kopiert. Die wurde
# ueber eine Bytesuche nach genau der Achterfolge gefunden:
#
#     0x24878a800   Block A, mit Kamera dahinter  -> wirkungslos
#     0x354f984ac   Block B, im Spielerkontext    -> WIRKT
#
# Messung dazu (P.T. im schnellen Zustand, Rate 0.20 geschrieben):
#     Block A auf 0.20   Median 4.64 m/s   unveraendert
#     Block B auf 0.20   Median 1.04 m/s   5.28 * 0.20 = 1.06, passt
#
# Der Hebel ist also linear und multipliziert sich auf den Zustand, den das
# Spiel selbst setzt (der Blick auf das Bild im Flur verdreifacht das Tempo,
# ohne einen dieser Werte anzufassen -- gemessen, siehe speedwatch.py).
#
# Block B enthaelt keine Kamerawerte, davor stehen Winkel um +-PI. Gefunden
# wird er darum ueber das VERHAELTNIS der acht Werte zueinander, das beim
# Skalieren erhalten bleibt: 1 : 0.75 : 0.50 : 0.75 : 0.50 : 0.40 : 0.25 : 0.40.

RATIO = [v / DEFAULTS[0] for v in DEFAULTS]
PLAYER_GAP = 0xa644          # Block B lag bei Spielerobjekt - diesem Abstand


def read8(p, addr):
    d = p.read(addr, 32)
    return list(struct.unpack('<8f', d)) if d and len(d) == 32 else None


def looks_like(v, tol=0.02):
    """Achterfolge im richtigen Verhaeltnis? Skalierung egal."""
    if not v or not (0.01 < v[0] < 100.0):
        return False
    for i in range(1, 8):
        want = RATIO[i] * v[0]
        if abs(v[i] - want) > tol * want:
            return False
    return True


def find_active(p, obj=None, factors=(1.0,)):
    """Block B suchen. Erst am bekannten Abstand, sonst im ganzen Speicher.

    `obj` ist das Spielerobjekt aus hover.chain(). Stimmt der Abstand, ist
    die Suche in Millisekunden vorbei; sonst kostet die Bytesuche ueber
    ~3.7 GB rund neun Sekunden. `factors` nennt die Skalierungen, nach denen
    gesucht wird -- wer schon einmal umgestellt hat, gibt den zuletzt
    gesetzten Wert mit an, sonst wird er nicht wiedergefunden.
    """
    if obj:
        a = obj - PLAYER_GAP
        if looks_like(read8(p, a)):
            return [a]

    cam = set(find(p))                      # Block A ausschliessen
    pats = []
    for f in factors:
        pats.append(struct.pack('<8f', *[v * f for v in DEFAULTS]))
    out = []
    for base, size in p.regions():
        if size > 0x10000000:
            continue
        blob = p.read(base, size)
        if not blob:
            continue
        for pat in pats:
            i = blob.find(pat)
            while i >= 0:
                a = base + i
                if a not in cam and a not in out:
                    out.append(a)
                i = blob.find(pat, i + 4)
    return out


def set_rate(p, base, f):
    """Alle acht Werte auf das f-fache der VORGABE setzen.

    Immer von der Vorgabe aus, nie vom aktuellen Wert -- sonst multipliziert
    sich jeder Aufruf auf den vorigen drauf. Alle acht gemeinsam, damit das
    Verhaeltnis erhalten bleibt und find_active() den Block wiederfindet.
    """
    for i, v in enumerate(DEFAULTS):
        p.write(base + i * 4, struct.pack('<f', v * f))
    return read8(p, base)


def current_rate(p, base):
    v = read8(p, base)
    return (v[0] / DEFAULTS[0]) if v else None


def main():
    a = sys.argv[1:]
    pid = ptmem.find_pid()
    if not pid:
        sys.exit('  shadPS4 laeuft nicht')
    p = ptmem.Proc(pid)
    print('  suche focalLength=13.0 auf [8] mit rotInterpHalfLife=1/30 auf [11] ...')
    blocks = find(p)
    if not blocks:
        sys.exit('  nicht gefunden -- laeuft das Spiel schon im Level?')
    print('  %d Block/Bloecke\n' % len(blocks))

    if '--speed' in a:
        f = float(a[a.index('--speed') + 1])
        # NICHT in die oben gefundenen Bloecke schreiben: die werden nur beim
        # Laden gelesen. Gemessen am 19.08. -- dort gesetzt bleiben die Werte
        # stehen, das Tempo aendert sich nicht. Wirksam ist allein die Kopie
        # im Spielerkontext, die find_active() sucht.
        print('  suche den wirksamen Block ...')
        act = find_active(p, factors=(1.0, f))
        if not act:
            sys.exit('  nicht gefunden. Laeuft ein Level, und stehen die acht'
                     ' Werte noch im Verhaeltnis der Vorgabe?')
        for base in act:
            v = set_rate(p, base, f)
            print('  0x%x auf das %.2f-fache gesetzt, front max %.2f'
                  % (base, f, v[0]))
        print()

    for base in blocks:
        v = read(p, base)
        if not v:
            continue
        print('  Block 0x%x' % base)
        for i, (nm, dflt) in enumerate(FIELDS):
            print('     [%d] %-10s %7.3f   (Vorgabe %.2f, Faktor %.2f)'
                  % (i, nm, v[i], dflt, v[i] / dflt))
        print('     [8] focalLength %7.3f' % v[8])
        print('     [9] rotVelMaxX  %7.3f rad = %.1f Grad' % (v[9], v[9] * 180 / 3.14159265))
        print('    [11] halfLife    %7.4f' % v[11])
        print()


if __name__ == '__main__':
    main()
