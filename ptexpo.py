# -*- coding: utf-8 -*-
"""Die Belichtung des Spiels im laufenden Bild stellen.

Wozu
----
Die Taschenlampe leuchtet fuenf Meter weit und kann die Leere jenseits der
Levelgeometrie nicht ausfuellen. Die Belichtung dagegen wirkt auf das GANZE
Bild und macht sichtbar, was zu dunkel ist -- fuer Analyse das passende
Werkzeug.

Wie der Weg gefunden wurde
--------------------------
Drei Versuche, eine Erkenntnis:

1. Die Taschenlampe ist als Weg erschoepft, und das ist belegt, nicht
   vermutet. `SetHandyLight` uebertraegt laut Befehlsverteiler nur `enable`
   und `lumen`. Die Funktion, die Reichweite und Winkel ins Lichtobjekt
   schreibt (FUN_0124fe00), hat per Querverweis GENAU EINEN Aufrufer -- die
   Erzeugungsfunktion. Sie laeuft nicht pro Bild. Passend dazu im Spiel
   gemessen: 10 000 und 1 000 000 Lumen leuchten gleich weit.

2. Die Parametertabelle (15 Bloecke ab 0x24878a880, Schrittweite 0x38) traegt
   die Belichtung je Floor. Ein Schreiben dort waehrend des Spiels wirkt NICHT
   -- sie wird beim Laden gelesen. Wohl aber wirkt eine Aenderung der
   Lua-Quelle im psarc (`luaprobe.py --exposure`), im Spiel bestaetigt.

3. Der Nutzer wies darauf hin, dass das Spiel die Helligkeit zur Laufzeit
   selbst nachfaehrt -- im Irrgarten zu sehen. Das heisst zwingend, dass es
   eine laufende Fassung gibt. Gefunden wurde sie ueber die Werte, die der
   Bau aus Schritt 2 gesetzt hatte: dieselbe Achterfolge kehrt in sechs
   Bloecken wieder, und ein Schreiben dort wirkt SOFORT -- im Spiel
   bestaetigt, dunkler und heller jeweils deutlich sichtbar.

Die Form, an der erkannt wird
-----------------------------
    minExposure | maxExposure | exposureCompensation | 0.2 0.1 2.0 3.0 1.2

Die fuenf Werte am Ende werden nie geschrieben und dienen als Erkennung. Sie
stammen aus derselben Tabelle (dimmer 0.1, bloomSize 2.0,
bloomBrightnessExtraction 3.0, attenuationExponent 1.2); wer sie ueber
`luaprobe.py --exposure` veraendert, macht die Erkennung stumpf. Das ist der
Preis dafuer, ohne feste Adressen auszukommen -- und feste Adressen waeren
schlimmer, denn sie verschieben sich beim naechsten Start.

Es gibt MEHRERE Fassungen (gemessen: sechs). Geschrieben wird in alle. Welche
das Bild speist, ist nicht bestimmt, und die Bildpuffer wechseln sich ab --
nur eine zu bedienen hiesse flackern.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptmem

# Reihenfolge im Laufzeitblock, ab minExposure
I_MIN, I_MAX, I_COMP = 0, 1, 2
SCHWANZ = (0.2, 0.1, 2.0, 3.0, 1.2)     # unveraendert, dient der Erkennung
LEN = 8                                  # Floats je Block

# Die Vorgaben des SPIELS aus ShParameterTables.lua -- ein Reset soll dorthin
# zurueck, nicht auf den Stand eines gebauten Archivs.
DEFAULT_MIN = -10.0
DEFAULT_MAX = 1.0
DEFAULT_COMP = 0.0

# So weit laesst sich stellen. Die obere Grenze ist nicht vom Spiel gesetzt,
# sondern gewaehlt: jenseits davon ist das Bild nur noch weiss und damit fuer
# eine Analyse so wertlos wie schwarz.
COMP_MIN, COMP_MAX = -10.0, 16.0
MAX_MIN, MAX_MAX = -10.0, 24.0


# Kleinster Abstand zwischen Boden und Decke. Faellt die Decke darunter, ist
# es keine Klammer mehr -- und der Block gilt als verschwunden.
MIN_SPANNE = 0.01


def _klammer(lo, hi, comp, streng=True):
    """Sind das wirklich min/max/comp einer Belichtung?

    Der Schwanz allein reicht nicht: gemessen fanden sich damit zehn Stellen,
    drei davon mit `min == max` (1.21/1.21, 3.57/3.57, 1.61/1.61). Eine
    Klammer ist aber ein INTERVALL -- wo unten und oben gleich sind, ist es
    keine, sondern ein Zufallstreffer im Nachbarspeicher. Dort zu schreiben
    waere genau der Fehlschreiber, den die Erkennung verhindern soll.
    """
    if not all(-60.0 <= v <= 60.0 for v in (lo, hi, comp)):
        return False
    return lo < hi if streng else lo <= hi


def find(p):
    """Alle Laufzeitbloecke suchen. Gibt die Adressen von `minExposure`.

    Gesucht wird ueber den unveraenderlichen Schwanz, NICHT ueber die
    Belichtungswerte selbst: die stellt der Nutzer ja gerade, und eine Suche,
    die den eigenen Schreibwert als Muster braucht, findet sich nach dem
    ersten Regeln nicht mehr wieder.
    """
    muster = struct.pack('<5f', *SCHWANZ)
    out = []
    for base, size in p.regions():
        if size > 0x10000000:
            continue
        blob = p.read(base, size)
        if not blob:
            continue
        i = blob.find(muster)
        while i >= 0:
            start = i - 3 * 4
            if start >= 0:
                v = struct.unpack_from('<3f', blob, start)
                if _klammer(*v):
                    out.append(base + start)
            i = blob.find(muster, i + 4)
    return out


def gueltig(p, addr):
    """Traegt `addr` noch einen Block?

    Bewusst NACHSICHTIGER als die Suche. Die Suche muss streng sein, sonst
    findet sie Zufallstreffer; eine laengst gefundene Adresse dagegen nur
    darauf abzuklopfen, ob der Schwanz noch Zeichen fuer Zeichen stimmt, waere
    zu viel verlangt -- aendert das Spiel auch nur einen dieser Werte, gaelte
    der Block als verschwunden und der Regler wirkte genau einmal. Genau das
    ist passiert.

    Dieselbe Trennung gilt schon in `lightscan`: `find_light` sucht und ist
    streng, `live_addr` prueft eine berechnete Adresse und ist es nicht.

    Geprueft wird deshalb nur noch, ob dort ueberhaupt eine Klammer steht:
    lesbar, Werte im Bereich, min < max. Liegt die Adresse nach einem
    Ladevorgang wirklich woanders, faellt das damit immer noch auf -- und der
    Aufrufer sucht dann nach.
    """
    d = p.read(addr, LEN * 4)
    if not d or len(d) < LEN * 4:
        return False
    # NICHT streng: eine Decke, die genau auf dem Boden liegt, ist zwar keine
    # brauchbare Klammer, aber immer noch UNSER Block. Streng geprueft gaelte
    # er als verschwunden, und der Nutzer kaeme nicht mehr heran, um die Decke
    # wieder anzuheben. Genau das ist im Spiel passiert.
    return _klammer(*struct.unpack_from('<3f', d, 0), streng=False)


def read(p, addr):
    d = p.read(addr, 3 * 4)
    if not d or len(d) < 12:
        return None
    lo, hi, comp = struct.unpack('<3f', d)
    return {'min': lo, 'max': hi, 'comp': comp}


def write(p, addrs, comp=None, hoch=None, tief=None):
    """In ALLE Bloecke schreiben. Gibt die Zahl der beschriebenen zurueck.

    In alle, weil nicht bestimmt ist, welcher das Bild speist, und weil die
    Bildpuffer sich abwechseln -- nur einen zu bedienen hiesse flackern.
    """
    n = 0
    for a in addrs:
        if not gueltig(p, a):
            continue
        # Boden und Decke duerfen sich nicht ueberholen. Eine Decke unter dem
        # Boden ist keine Klammer mehr; die Suche findet den Block dann nicht
        # wieder, und der Regler waere fuer den Rest des Laufs tot.
        v = read(p, a)
        boden = float(tief) if tief is not None else v['min']
        decke = float(hoch) if hoch is not None else v['max']
        if decke < boden + MIN_SPANNE:
            if hoch is not None:
                decke = boden + MIN_SPANNE
            else:
                boden = decke - MIN_SPANNE
        if tief is not None or decke != v['max']:
            p.write(a + I_MIN * 4, struct.pack('<f', boden))
        if hoch is not None or boden != v['min']:
            p.write(a + I_MAX * 4, struct.pack('<f', decke))
        if comp is not None:
            p.write(a + I_COMP * 4, struct.pack('<f', float(comp)))
        n += 1
    return n


if __name__ == '__main__':
    p = ptmem.Proc(ptmem.find_pid())
    a = find(p)
    print('  %d Laufzeitbloecke' % len(a))
    for x in a:
        v = read(p, x)
        print('     0x%-12x min %7.2f  max %7.2f  comp %7.2f'
              % (x, v['min'], v['max'], v['comp']))
