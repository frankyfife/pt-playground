# -*- coding: utf-8 -*-
u"""Zwischensequenzen anhalten und weiterlaufen lassen.

Was es tut
----------
Setzt genau das Bit, das die Lua-Funktion `Demox:StreamPause()` setzt. Die
Sequenz haelt an, das Spiel laeuft weiter -- die freie Kamera bleibt also
beweglich, und man kann sich in Ruhe umsehen.

Woher das kommt
---------------
`init.lua` meldet ueber FUN_00781a30 eine Schnittstelle "Demox" an, mit
Start, StreamStart, StreamPause und SetupPlayback. Die beiden
Stromfunktionen bestehen aus je einer Anweisung:

    StreamStart   and byte ptr [rax+0x111], 0xf7     Bit 0x08 loeschen
    StreamPause   or  byte ptr [rax+0x111], 8        Bit 0x08 setzen

Die Abspielschleife FUN_00b21000 prueft dasselbe Bit und arbeitet nur
weiter, solange es NULL ist.

Adressen
--------
    Verwalter   = [BASE + 0x1e5b440]        aus FUN_00b23e00
    Kopf-Index  = u32 [Verwalter + 0x38]    0xffffffff = Liste leer
    Tabelle     = [Verwalter + 0x48]        Eintraege zu 0x10 Byte
    Eintrag + 0x00  Stromobjekt   + 0x0c  naechster Index
    Stromobjekt + 0x111   Bit 0x08 = Pause

FUN_00b1dbe0 ist nur eine Registerpruefung: sie gibt den Schluessel zurueck,
wenn er in der Liste steht. Der Schluessel IST das Objekt -- deshalb laesst
sich die Liste abgehen, statt einen Zeiger zu raten.

Einschraenkungen
----------------
* Ausserhalb einer Sequenz gibt es kein Stromobjekt; dann ist nichts
  anzuhalten und `zustand()` meldet None.
* Das Bit gilt je Strom. Laufen mehrere, werden alle geschaltet.
* NICHT zu verwechseln mit dem Bildzaehler, der waehrend einer Sequenz mit
  30/s hochlaeuft: der ist eine AUSGABE. Ihn festzuhalten bringt das ganze
  Spiel zum Stillstand, nicht nur die Sequenz. Am 20.09.2026 passiert.

    python ptdemo.py             Zustand
    python ptdemo.py --pause     anhalten
    python ptdemo.py --weiter    weiterlaufen lassen
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hover
import ptmem

VERWALTER_VA = 0x1e5b440
O_KOPF, O_TABELLE = 0x38, 0x48
O_PAUSE = 0x111
BIT = 0x08
MAX = 256


def _u32(p, a):
    d = p.read(a, 4)
    return struct.unpack('<I', d)[0] if d and len(d) == 4 else None


def _u64(p, a):
    d = p.read(a, 8)
    return struct.unpack('<Q', d)[0] if d and len(d) == 8 else None


def objekte(p, base):
    u"""Alle angemeldeten Stromobjekte. Leer, wenn keine Sequenz laeuft."""
    verw = _u64(p, base + VERWALTER_VA)
    if not verw:
        return []
    kopf = _u32(p, verw + O_KOPF)
    tab = _u64(p, verw + O_TABELLE)
    if kopf is None or kopf == 0xffffffff or not tab:
        return []
    aus, i, gesehen = [], kopf, set()
    while i != 0xffffffff and i not in gesehen and len(aus) < MAX:
        gesehen.add(i)
        o = _u64(p, tab + i * 0x10)
        if o:
            aus.append(o)
        n = _u32(p, tab + i * 0x10 + 0xc)
        if n is None:
            break
        i = n
    return aus


def zustand(p, base):
    u"""True = angehalten, False = laeuft, None = keine Sequenz."""
    objs = objekte(p, base)
    if not objs:
        return None
    an = []
    for o in objs:
        d = p.read(o + O_PAUSE, 1)
        if d:
            an.append(bool(d[0] & BIT))
    if not an:
        return None
    return all(an)


def setzen(p, base, pause):
    u"""Bit setzen oder loeschen. Rueckgabe: Anzahl geschalteter Stroeme."""
    n = 0
    for o in objekte(p, base):
        d = p.read(o + O_PAUSE, 1)
        if not d:
            continue
        neu = (d[0] | BIT) if pause else (d[0] & ~BIT)
        if neu != d[0]:
            p.write(o + O_PAUSE, bytes([neu]))
        n += 1
    return n


def main():
    a = sys.argv[1:]
    pid = ptmem.find_pid()
    if not pid:
        sys.exit('  shadPS4 laeuft nicht')
    p = ptmem.Proc(pid)
    base = hover.find_base(p)
    if base is None:
        sys.exit('  Modulbasis nicht gefunden -- ist ein Level geladen?')
    objs = objekte(p, base)
    if not objs:
        print('  keine Sequenz -- nichts anzuhalten')
        return
    if '--pause' in a or '--weiter' in a:
        n = setzen(p, base, '--pause' in a)
        print('  %d Strom(e) %s' % (n, 'angehalten' if '--pause' in a
                                    else 'weitergelassen'))
    for o in objs:
        d = p.read(o + O_PAUSE, 1)
        print('  0x%-14x +0x%x = 0x%02x   %s'
              % (o, O_PAUSE, d[0] if d else 0,
                 'PAUSE' if (d[0] if d else 0) & BIT else 'laeuft'))


if __name__ == '__main__':
    main()
