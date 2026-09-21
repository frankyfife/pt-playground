"""Den Taschenlampen-Block im Speicher finden -- und stellen.

Warum es ihn geben MUSS
-----------------------
Am 19.08.2026 im Spiel beobachtet: mit gepatchtem `handyLightParameter`
(r=1, g=0.15, b=0.15) leuchtet die Lampe im Startraum **rot**, und beim
Durchschreiten der Tuer wird sie wieder **weiss**. Die Tabelle wird also
gelesen -- und danach ueberschreibt etwas die Werte. Es gibt somit eine
Fassung im Arbeitsspeicher, und was ueberschrieben werden kann, kann auch
gesetzt werden.

Wie gesucht wird
----------------
Ueber die STRUKTUR, nicht ueber eine Farbe. Das war ein Fehlschlag wert:
`0.0, 1.0, 0.0` als Bytefolge kommt im Speicher 62743-mal vor -- Nullen und
Einsen stehen ueberall, eine Farbsuche findet also fast nur Zufall.

Eindeutig ist dagegen `temperature = 5000.0` mit `lumen` acht Byte dahinter
und drei brauchbaren Farbwerten davor. Damit bleiben drei Treffer: die
Taschenlampe (lumen 100) und zwei Raumlichter (lumen 25000 und 30000).

Der Block liegt bei 0x24878a83c, also unmittelbar HINTER dem
Bewegungsparameterblock 0x24878a800 -- davor stehen focalLength 13.0 und
rotVelMax 1.898. Es ist derselbe Parameterbereich.

Was wirkt
---------
Schreiben in diesen Block wirkt, aber nicht sofort: uebernommen wird beim
naechsten LADEN (Raumwechsel, Tod, Neustart). Am 19.08. im Spiel bestaetigt
-- Farbe auf gruen geschrieben, nach dem Tod im Startraum gruene Lampe.

    python lightscan.py                     suchen und die Umgebung zeigen
    python lightscan.py --watch             laufend beobachten
    python lightscan.py --set r=1,g=0,b=0   setzen


P.T. muss laufen.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptmem

# Reihenfolge wie in ShParameterTables.lua. Ob die Engine sie genauso
# uebernimmt, ist offen -- deshalb wird die Umgebung ausgegeben und nicht
# blind ein Feldname auf einen Offset geklebt.
TABLE = ('innerRange', 'outerRange', 'r', 'g', 'b', 'temperature',
         'colorDeflection', 'lumen', 'lightSize', 'umbraAngle',
         'penumbraAngle', 'attenuationExponent', 'shadowUmbraAngle',
         'shadowPenumbraAngle', 'shadowAttenuationExponent', 'dimmer',
         'shadowBias', 'viewBias', 'powerScale')

TEMPERATURE = 5000.0


def find_rgb(p, rgb=(1.0, 0.15, 0.15), tol=1e-4):
    """Adressen, an denen drei Floats hintereinander diese Farbe ergeben."""
    want = struct.pack('<3f', *rgb)
    out = []
    for base, size in p.regions():
        if size > 0x10000000:
            continue
        blob = p.read(base, size)
        if not blob:
            continue
        i = blob.find(want)
        while i >= 0:
            out.append(base + i)
            i = blob.find(want, i + 4)
    return out


def find_temperature(p):
    """Adressen mit dem Float 5000.0 -- der Rueckfall ohne Farbpatch."""
    want = struct.pack('<f', TEMPERATURE)
    out = []
    for base, size in p.regions():
        if size > 0x10000000:
            continue
        blob = p.read(base, size)
        if not blob:
            continue
        i = blob.find(want)
        while i >= 0:
            out.append(base + i)
            i = blob.find(want, i + 4)
    return out


def find_light(p):
    """Lichtbloecke ueber die STRUKTUR finden, nicht ueber eine Farbe.

    Warum nicht ueber die Farbe: `0.0, 1.0, 0.0` als Bytefolge kommt im
    Speicher 62743-mal vor -- Nullen und Einsen stehen ueberall. Eine
    Farbsuche findet also fast nur Zufall. Die Struktur dagegen ist
    eindeutig: temperature (5000.0) und acht Byte spaeter lumen, davor drei
    Floats, die als Farbe taugen.

    Gibt die Adresse der FARBE zurueck (also temperature - 12).
    """
    want = struct.pack('<f', TEMPERATURE)
    out = []
    for base, size in p.regions():
        if size > 0x10000000:
            continue
        blob = p.read(base, size)
        if not blob:
            continue
        i = blob.find(want)
        while i >= 0:
            col = i - 12
            if col >= 0 and col + 24 <= len(blob):
                r, g, b, t, cd, lm = struct.unpack_from('<6f', blob, col)
                if (all(0.0 <= v <= 4.0 for v in (r, g, b))
                        and 0.0 < lm <= 100000.0
                        and -1.0 <= cd <= 1.0):
                    out.append(base + col)
            i = blob.find(want, i + 4)
    return out



# ---------------------------------------------------------------------------
# Die AKTIVE Lampe -- die, die im Flur wirklich leuchtet
# ---------------------------------------------------------------------------
# Am 19.08.2026 durch Differenzsuche gefunden: Farbe im Spiel umschalten
# lassen (die Sonde faerbt gruen, der Flur weiss), beide Zustaende scannen,
# den Rest per Halbierung eingrenzen. Von 64379 Kandidaten blieb einer.
#
# Warum die frueheren Suchen fehlschlugen: ich hatte die Farbe VOR
# `temperature` erwartet, weil sie in ShParameterTables.lua so steht. Im
# Speicher steht sie DAHINTER. Die Struktur:
#
#     -24   lumen          100.0
#     -20   temperature   5000.0
#      +0   r, g, b
#     +48   Position       (folgt dem Spieler)
#     +64   Quaternion     (Blickrichtung)
#
# Position und Blickrichtung im selben Block -- das ist die Lampe am Spieler,
# nicht eine Leuchte im Level.
LIVE_GAP = 0xa7d0          # Abstand zum Spielerobjekt
LIVE_LUMEN = -24           # relativ zur Farbe
LIVE_TEMP = -20


def live_addr(p, obj):
    """Adresse der aktiven Lampenfarbe. None, wenn die Struktur nicht passt.

    Geprueft wird ueber lumen und temperature an ihren festen Abstaenden --
    eine blosse Adressrechnung wuerde nach einem Spielneustart stumm
    irgendwohin schreiben.
    """
    a = obj - LIVE_GAP
    d = p.read(a + LIVE_LUMEN, 48)
    if not d or len(d) < 48:
        return None
    lm, t = struct.unpack_from('<2f', d, 0)
    r, g, b = struct.unpack_from('<3f', d, -LIVE_LUMEN)
    # lumen DARF 0 sein: das ist die ausgeschaltete Lampe, kein falscher
    # Block. Hier wird nichts gesucht, sondern eine berechnete Adresse
    # geprueft -- es gibt nur die eine, also kann es keinen Fehltreffer
    # geben. Mit `0.0 < lm` sperrte sich das Werkzeug selbst aus, sobald
    # jemand die Helligkeit auf 0 stellte. In `find_light`, das wirklich
    # sucht, bleibt die strengere Bedingung stehen.
    if not (0.0 <= lm <= 100000.0 and 1000.0 <= t <= 20000.0):
        return None
    if not all(0.0 <= v <= 8.0 for v in (r, g, b)):
        return None
    return a


def live_read(p, addr):
    d = p.read(addr + LIVE_LUMEN, 48)
    if not d or len(d) < 48:
        return None
    lm, t = struct.unpack_from('<2f', d, 0)
    r, g, b = struct.unpack_from('<3f', d, -LIVE_LUMEN)
    return {'lumen': lm, 'temperature': t, 'r': r, 'g': g, 'b': b}


def live_set(p, addr, rgb=None, lumen=None):
    """Farbe und Helligkeit der aktiven Lampe setzen."""
    if rgb is not None:
        p.write(addr, struct.pack('<3f', *[float(v) for v in rgb]))
    if lumen is not None:
        p.write(addr + LIVE_LUMEN, struct.pack('<f', float(lumen)))
    return live_read(p, addr)



def dump(p, addr, before=8, after=20):
    """Die Floats um eine Fundstelle -- damit man die Struktur SIEHT,
    statt sie zu raten."""
    lo = addr - before * 4
    d = p.read(lo, (before + after) * 4)
    if not d:
        return []
    out = []
    for i in range(before + after):
        v, = struct.unpack_from('<f', d, i * 4)
        out.append((lo + i * 4, (i - before) * 4, v))
    return out


def main():
    a = sys.argv[1:]
    pid = ptmem.find_pid()
    if not pid:
        sys.exit('  P.T. laeuft nicht.')
    p = ptmem.Proc(pid)

    print('  suche die Farbe 1.00 / 0.15 / 0.15 ...')
    hits = find_rgb(p)
    how = 'Farbe'
    if not hits:
        print('  nicht gefunden -- suche stattdessen temperature = 5000.0')
        hits = find_temperature(p)
        how = 'temperature'
    if not hits:
        sys.exit('  nichts gefunden. Laeuft schon ein Level?')
    print('  %d Fundstelle(n) ueber %s' % (len(hits), how))
    print()

    for addr in hits[:6]:
        print('  === 0x%x' % addr)
        for a2, off, v in dump(p, addr):
            tag = ''
            if how == 'Farbe' and 0 <= off < len(TABLE) * 4 - 8:
                idx = off // 4 + 2          # die Farbe ist Feld 2..4
                if idx < len(TABLE):
                    tag = '  ' + TABLE[idx]
            print('     %+4d  0x%x  %12.4f%s' % (off, a2, v, tag))
        print()

    if '--watch' in a:
        print('  beobachte die erste Fundstelle -- jetzt durch die Tuer gehen.')
        print('  Ausgabe nur bei AENDERUNG. Strg+C beendet.')
        addr = hits[0]
        prev = None
        while True:
            d = p.read(addr - 32, 128)
            if not d:
                print('  Lesen abgebrochen -- Spiel beendet?')
                break
            vals = struct.unpack('<32f', d)
            if prev is None or any(abs(x - y) > 1e-4
                                   for x, y in zip(vals, prev)):
                print('  %s  %s' % (time.strftime('%H:%M:%S'),
                                    ' '.join('%.3f' % v for v in vals[6:14])))
                prev = vals
            time.sleep(0.1)

    if '--set' in a:
        vals = {}
        for part in a[a.index('--set') + 1].split(','):
            k, v = part.split('=')
            vals[k.strip()] = float(v)
        addr = hits[0]
        for k, v in vals.items():
            if k not in TABLE:
                sys.exit('  unbekannt: %s' % k)
            off = (TABLE.index(k) - 2) * 4     # relativ zur Farbe
            p.write(addr + off, struct.pack('<f', v))
            print('  %s = %.3f  an 0x%x' % (k, v, addr + off))


if __name__ == '__main__':
    main()
