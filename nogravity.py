"""Switch the player's gravity off in eboot.bin -- permanently, no memory hunting.

Why patch the binary instead of writing to memory
-------------------------------------------------
Holding the player's Y from outside does work: 130 kHz beats the engine's 60 Hz
rewrite comfortably and the view was seen lifting. But the address lives on the
heap and has to be re-found after every restart, and six different automatic
searches failed at that. Cheat Engine is no help either -- its freeze runs far
too slowly against a value the engine rewrites every frame.

First attempt, and why it failed
--------------------------------
ChBodyPlugin's flags came out of the property registration at va 0x6ad600:

    +0xDC hasGravity   +0xDD hasCollision   +0xDE hasTurnXYZ   +0xDF hasTrap

Three places read that run of four to build a bit mask (base 0x1e; hasGravity
sets bit 0 to make 0x1f). Forcing those branches so bit 0 stayed clear applied
cleanly and changed nothing -- movement still worked, the character still fell.
So that mask only REPORTS the flags, it does not drive the physics. Reverted.

What actually sets the flag
---------------------------
The ChBodyPlugin initialiser at va 0x6b5bb8 unpacks a bitfield at [param+0xac]
into the individual bools:

    al = [r14+0xac] >> 1 & 1   ->  [+0xdc] hasGravity
    al = [r14+0xac] >> 2 & 1   ->  [+0xdd] hasCollision
    al = [r14+0xac] >> 3 & 1   ->  [+0xde] hasTurnXYZ
    al = [r14+0xac] >> 4 & 1   ->  [+0xdf] hasTrap

Turning the gravity line's `and al, 1` (24 01, va 0x6b5be1) into `and al, 0`
makes the flag come out false for every body that is built. Tested: the player
STILL falls. So the player is very likely not a ChBodyPlugin character at all --
the character manager the engine itself reads ([0x801C3FAC0]) came back empty,
because that is the AI/NPC system and P.T. barely uses it. That patch has been
dropped again; what is applied now is the physics world's own gravity constant.

This applies to every character, everywhere -- nothing will fall, in the hallway
either. That is the point for exploring the street, but it is also why this is a
switch and not part of the mod: expect stairs, the small step at the hallway's
end door and anything that relies on landing to behave oddly.

    python nogravity.py                  # every site
    python nogravity.py --only height    # just one, by key
    python nogravity.py --restore        # back to the shipped eboot
    python nogravity.py --check          # show what is currently in the file

shadPS4 must be closed, and the change takes effect on the next start.

NOTE: eboot.elf is lifted from eboot.bin, so patching here makes the ELF -- and
anything Ghidra indexed from it -- stale. That already happened once and put a
patched `mov al,1` into ptindex.txt. Run `python elfout.py --verify` before any
Ghidra work; it now diffs every mapped byte and names the offenders.
"""
import os
import shutil
import struct
import sys

import ptpaths                 # zentrale Pfade, siehe ptpaths.py
GAME = ptpaths.GAME
EBOOT = ptpaths.EBOOT
BACKUP = os.path.join(GAME, "eboot.orig.bin")

# key -> (file offset, shipped bytes, patched bytes, what it does)
SITES = {
    # THE ONE THAT MATTERS. The user's observation: standing still on the street
    # the player does NOT fall -- only the next step drops him. That is exactly
    # what noControlHeightWithNoMotion describes: with no motion the height is
    # not regulated at all. Moving turns the regulation on, it finds no ground,
    # and down he goes.
    #
    # The ChBodyPlugin initialiser at va 0x6b5c23 extracts it from bit 6:
    #     mov al, [r14+0xac] ; shr al, 6 ; and al, 1 ; mov [r13+0xe0], al
    # Turning `and al, 1` (24 01) into `mov al, 1` (b0 01) -- same length --
    # pins the flag on, so the height is never regulated and nothing falls.
    'height': (0x2c1ffd, bytes([0x24, 0x01]), bytes([0xb0, 0x01]),
               'and al,1 -> mov al,1  (noControlHeightWithNoMotion always on)'),
    # GotoGameOver (va 0x924f90) is four instructions:
    #     rax = [0x1c85508]      the game-state singleton
    #     if rax: [rax+0x70] = 0x10     state 16 == game over
    # Making its `je` unconditional skips that store, so the reset never fires.
    # This is the permanent form of what the Lua hook did by hand -- it stops
    # the RESET, not Lisa's appearance; the kill demo can still play.
    # DER BODENSTRAHL DER SPIELERPLATZIERUNG.
    # FUN_0093fc80 setzt den Spieler einmalig auf den Boden, indem es von
    #     pos + (0, +1.5, 0)   bis   pos + (0, -10, 0)
    # gegen CollisionStatic strahlt (Maske 0x700) und den Treffer als neue
    # Position nimmt. Bei einem Fehlschlag passiert GAR NICHTS -- der Spieler
    # wird nie platziert, und die Routine versucht es jeden Frame erneut.
    #
    # Auf der Strasse landet der Spieler laut Beobachtung bei ca. -79 m,
    # waehrend die Fahrbahn bei y~0 liegt. Der Strahl reicht nur 1,5 m nach
    # oben und kann sie deshalb NIE erreichen -- die Kollision mag da sein,
    # die Pruefung kommt nur nicht hin.
    #
    # Der obere Startpunkt wird darum von 1.5 auf 90.0 gezogen: aus -79 heraus
    # beginnt der Strahl dann bei +11, also ueber der Fahrbahn und unter den
    # Dachkanten, und faellt auf die Strasse. Nur die Y-Komponente, ein float.
    #
    # ACHTUNG BEIM RECHNEN: luaapi.va2off() liefert Offsets in eboot.ELF, hier
    # wird aber eboot.BIN gepatcht -- die Layouts sind verschieden. Der richtige
    # Weg ist elfout._selfmap(). va 0x1420254 -> eboot.bin 0x102c624.
    'groundray': (0x102c624, struct.pack('<f', 1.5), struct.pack('<f', 500.0),
                  'Bodenstrahl oben  +1.5 -> +500 m'),
    # Die Gegenrichtung. Mit 90 m nach oben aenderte sich nichts, also war der
    # auf -79 getunte Wert nicht die Antwort. Beide Enden auf 500 m machen aus
    # dem Versuch eine ENTSCHEIDUNG: findet ein 1000 m langer Strahl in dieser
    # Stage immer noch nichts, ist dort schlicht nichts in CollisionStatic
    # eingetragen -- und die Strahllaenge war eine Sackgasse.
    'groundray_dn': (0x102c614, struct.pack('<f', -10.0), struct.pack('<f', -500.0),
                     'Bodenstrahl unten -10 -> -500 m'),
    'gameover': (0x53136d, bytes([0x74, 0x07]), bytes([0xeb, 0x07]),
                 'je -> jmp             (GotoGameOver writes no state)'),
    # DIE SCHWERKRAFT SELBST. Der height-Patch schaltet nur die Hoehen-
    # REGELUNG ab -- der freie Fall bleibt. Gemessen in hover.py:
    #     obj+0x74   -24.50 in 2.5 s  = -9.8 m/s^2   Y-Geschwindigkeit
    # Das Hover-Skript nagelt diese Geschwindigkeit jede Runde auf null, und
    # genau dieses Gegeneinander ist das Zittern. Wer die Ursache abstellen
    # will, muss an die Konstante.
    #
    # Im eboot stehen vier Werte, alle als (0, g, 0) eingebettet:
    #     0x1086dec  -9.80   \  liegen zusammen, deshalb eine Stelle
    #     0x1086df4  -9.80   /
    #     0x10924e4  -9.81
    #     0x1093204  -9.81
    #
    # NICHT belegt, welche davon die Spielerphysik treibt -- deshalb einzeln
    # schaltbar, damit man es eingrenzen kann statt alles auf einmal zu aendern.
    'gravity': (0x1086dec, struct.pack('<fff', -9.8, 0.0, -9.8),
                struct.pack('<fff', 0.0, 0.0, 0.0),
                'Schwerkraft -9.80 -> 0   (zwei Werte, Kandidat 1)'),
    'gravity_b': (0x10924e4, struct.pack('<f', -9.81), struct.pack('<f', 0.0),
                  'Schwerkraft -9.81 -> 0   (Kandidat 2)'),
    'gravity_c': (0x1093204, struct.pack('<f', -9.81), struct.pack('<f', 0.0),
                  'Schwerkraft -9.81 -> 0   (Kandidat 3)'),
}


def read():
    with open(EBOOT, 'rb') as f:
        return bytearray(f.read())


def state(d):
    out = []
    for key, (off, orig, patched, what) in sorted(SITES.items()):
        cur = bytes(d[off:off + len(orig)])
        tag = 'shipped' if cur == orig else ('PATCHED' if cur == patched else '???')
        out.append((key, off, cur, tag, what))
    return out


def show(d):
    for key, off, cur, tag, what in state(d):
        print('  %-9s file 0x%-8x %s  %-8s  %s'
              % (key, off, ' '.join('%02x' % b for b in cur), tag, what))


def selected(args):
    """Which sites this run touches. Patching one at a time keeps the result
    readable: with the game-over site in as well, a player who no longer falls
    and a player who falls but is never reset look the same from the outside."""
    if '--only' not in args:
        return dict(SITES)
    key = args[args.index('--only') + 1]
    if key not in SITES:
        sys.exit('unknown site %r -- have: %s' % (key, ', '.join(sorted(SITES))))
    return {key: SITES[key]}


def main():
    if not os.path.exists(EBOOT):
        sys.exit('missing %s' % EBOOT)
    args = sys.argv[1:]
    d = read()

    if '--check' in args:
        show(d)
        return

    if '--restore' in args:
        if not os.path.exists(BACKUP):
            sys.exit('no backup at %s -- nothing to restore from' % BACKUP)
        try:
            shutil.copy2(BACKUP, EBOOT)
        except PermissionError:
            sys.exit('eboot.bin is locked -- close shadPS4 and try again.')
        print('restored the shipped eboot.bin')
        show(read())
        return

    sel = selected(args)
    for key, (off, orig, patched, what) in sel.items():
        cur = bytes(d[off:off + len(orig)])
        if cur == patched:
            continue
        if cur != orig:
            sys.exit('file 0x%x holds %s, expected %s -- refusing to patch'
                     % (off, cur.hex(' '), orig.hex(' ')))
    if not os.path.exists(BACKUP):
        shutil.copy2(EBOOT, BACKUP)
        print('  backed up the shipped eboot to %s' % os.path.basename(BACKUP))
    for key, (off, orig, patched, what) in sel.items():
        d[off:off + len(patched)] = patched
    try:
        with open(EBOOT, 'wb') as f:
            f.write(d)
    except PermissionError:
        sys.exit('eboot.bin is locked -- close shadPS4 and try again. '
                 'Nothing was written.')
    print('  patched %d site(s): %s' % (len(sel), ', '.join(sorted(sel))))
    show(read())
    print('\n  takes effect on the next start; undo with --restore')


if __name__ == '__main__':
    main()
