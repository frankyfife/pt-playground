# -*- coding: utf-8 -*-
u"""Texturzerfall im Aussenbereich abstellen.

Was es tut
----------
Haengt in `init.lua` eine Zeile hinter das Einschalten des Texturstreamings:

    GrTools():SuppressGradeChange()

Damit friert das Spiel die Detailstufe seiner Texturen ein, statt sie nach
Entfernung zu wechseln. Auf der Strasse zerfallen Texturen sonst, je naeher
man an ein Objekt herangeht -- der Wechsel auf die hoehere Stufe misslingt
unter shadPS4.

Einschraenkungen
----------------
* Eingefroren wird die Stufe, die beim Laden gilt -- die Strasse bleibt also
  unscharf. Sie bleibt aber stabil.
* Betrifft das ganze Spiel, nicht nur den Aussenbereich.
* Das Archiv wird neu geschrieben; das Spiel muss dafuer geschlossen sein.

    python grsupp.py                 Zustand des aktiven Archivs
    python grsupp.py --an            Zeile einbauen, Archiv ersetzen
    python grsupp.py --aus           Zeile entfernen, Archiv ersetzen
    python grsupp.py --psarc <datei> Ergebnis woandershin schreiben
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import foxfast
import psarc
import ptpaths

ZIEL = '/init.lua'
ANKER = b'\tGrTools():EnableTextureStreaming()\r\n'
ZEILE = b'\tGrTools():SuppressGradeChange()\r\n'


def lua(arc):
    u"""Den Klartext von init.lua aus einem Archiv, oder None."""
    try:
        klar = foxfast.decrypt(arc.read(arc.index_of(ZIEL)))
    except Exception:
        return None
    return klar if ANKER in klar else None


def zustand(pfad=None):
    u"""True = eingefroren, False = nicht, None = nicht feststellbar."""
    pfad = pfad or os.path.join(ptpaths.GAME, 'chunk1.psarc')
    if not os.path.exists(pfad):
        return None
    try:
        klar = lua(psarc.Psarc(pfad))
    except Exception:
        return None
    return None if klar is None else (ZEILE in klar)


def bauen(quelle, ziel, an=True):
    u"""Archiv mit oder ohne die Zeile schreiben.

    Rueckgabe: (True, Meldung) oder (False, Grund). Das Ergebnis wird vor dem
    Schreiben zurueckentschluesselt und geprueft -- ein unlesbares init.lua
    haette zur Folge, dass das Spiel gar nicht mehr startet.
    """
    arc = psarc.Psarc(quelle)
    klar = lua(arc)
    if klar is None:
        return False, 'init.lua nicht lesbar'
    neu = klar.replace(ANKER + ZEILE, ANKER).replace(ANKER, ANKER + ZEILE) \
        if an else klar.replace(ANKER + ZEILE, ANKER).replace(ZEILE, b'')
    if neu == klar:
        return True, 'war schon so'
    ver = foxfast.encrypt(neu)
    if foxfast.decrypt(ver) != neu:
        return False, 'Verschluesselung nicht umkehrbar'
    tmp = ziel + '.tmp'
    psarc.build(arc, tmp, {arc.index_of(ZIEL): ver})
    pruef = psarc.Psarc(tmp)
    gut = foxfast.decrypt(pruef.read(pruef.index_of(ZIEL))) == neu
    # Beide Leser halten ihre Datei offen. Unter Windows laesst sich eine
    # offene Datei nicht ersetzen, also erst schliessen.
    pruef.f.close()
    arc.f.close()
    if not gut:
        os.remove(tmp)
        return False, 'Gegenprobe im Archiv fehlgeschlagen'
    os.replace(tmp, ziel)
    return True, 'eingebaut' if an else 'entfernt'


def main():
    a = sys.argv[1:]
    aktiv = os.path.join(ptpaths.GAME, 'chunk1.psarc')
    quelle = a[a.index('--quelle') + 1] if '--quelle' in a else aktiv
    ziel = a[a.index('--psarc') + 1] if '--psarc' in a else aktiv
    if '--an' not in a and '--aus' not in a:
        z = zustand(quelle)
        print('  %s: %s' % (os.path.basename(quelle),
                            {True: 'Detailstufe eingefroren',
                             False: 'unveraendert',
                             None: 'nicht feststellbar'}[z]))
        return
    ok, text = bauen(quelle, ziel, '--an' in a)
    print('  %s -- %s' % (text, os.path.basename(ziel)))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
