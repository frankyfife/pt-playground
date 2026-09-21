"""Arm P.T.'s own "go to ending" trap on every floor instead of only the last.

The street does not need to be loaded by hand. The game already owns a working
path into it: finish the loop and a real-time sequence walks the player out of
the house into the open street area. That path is pure data and it sits in
pt14_hallway.fox2 the whole time.

How the shipped mechanism works
-------------------------------
Each floor owns a demo group fXXX_demo whose `condition_enable_demo_all` arms
that floor's traps as the player walks in. The f160 one arms three things:

    trap_goto_ending          GeoTrap, box at local z -5.58
    ShDemoScript_goto_ending  demoId gc_p00_010, stepString "GotoEnding"
    trap_force_gameover       box at (0.60, 1.38, -13.56), loopCount 30

`trap_goto_ending`'s condition checks ShIsPlayer, runs trapGotoEnding.lua and
carries orderFloor=True / floorName="ending". Walk into that box while it is
armed and the game orders the ending floor -- the route a finished playthrough
takes. The box is present on every lap; only the arming is gated.

Why this arms everywhere
------------------------
The first version re-keyed f160's condition to floorLevel=1 / floorName="f005"
and it did nothing. That approach was wrong in a way the savegame makes
obvious: which floor you are on when you load is progression state held in the
save, so pinning the arming to one specific floor bets on the run happening to
be there. It also assumed floorLevel/floorName are a *check*; trapEnableData.lua
is compiled, so that was a guess, and re-keying would misfire if the script
instead SETS the floor.

So: leave every condition's own keying alone and only extend the arming lists.
`trap_goto_ending` gets appended to the targetData of all eleven
`condition_enable_demo_all` entities. Whichever floor the save resumes at, the
trap comes up armed, and every condition still fires exactly when it always did
-- this rides on machinery that demonstrably works during normal play instead
of on a reading of a script we cannot read.

The two links are copied byte for byte out of f160's own targetData, so not one
hash is synthesised. trap_force_gameover is deliberately not copied along: it
exists to end the run.

    python gotoending.py            # build it
    python gotoending.py --restore  # back to the untouched original

shadPS4 must be closed: it holds chunk1.psarc open while a game is loaded.
"""
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psarc, foxfast, foxfpk, fox2, fox2build

import ptpaths                 # zentrale Pfade, siehe ptpaths.py
GAME = ptpaths.GAME
ORIG = os.path.join(GAME, "chunk1.orig.psarc")
LIVE = os.path.join(GAME, "chunk1.psarc")

FPKD = "/as/sh/level/promotion/pt_2014/hallway/pt14_hallway.fpkd"
FOX2 = "/Assets/sh/level/promotion/pt_2014/hallway/pt14_hallway.fox2"

SOURCE = "pt14_hallway|pt14_hallway_demo|f160_demo|condition_enable_demo_all"
WANT = ("trap_goto_ending", "ShDemoScript_goto_ending")
COND_SUFFIX = "condition_enable_demo_all"


def link_name(doc, raw):
    """Last path component of an EntityLink's nameInArchive."""
    _, _, n = struct.unpack_from('<3Q', raw)
    return doc.strings.get(n, '#%012x' % n).split('|')[-1]


def patch(blob):
    doc = fox2build.Doc.load(blob)

    src = doc.named(SOURCE)
    if len(src) != 1:
        raise KeyError("expected 1 %r, found %d" % (SOURCE, len(src)))
    td = src[0].require('targetData')
    donors = {}
    for i in range(td.count):
        raw = td.value(i)
        donors[link_name(doc, raw)] = raw
    missing = [w for w in WANT if w not in donors]
    if missing:
        raise KeyError("f160 does not arm %s" % missing)

    targets = []
    for e in doc.ents:
        p = e.get('name')
        if not p or not p.count:
            continue
        h, = struct.unpack_from('<Q', p.data, 0)
        nm = doc.strings.get(h, '')
        if nm.split('|')[-1] == COND_SUFFIX:
            targets.append((nm, e))
    targets.sort()
    print("  %d arming conditions found" % len(targets))

    added = 0
    for nm, e in targets:
        td = e.get('targetData')
        if td is None:
            print("     %-10s no targetData, skipped" % nm.split('|')[-2])
            continue
        have = {link_name(doc, td.value(i)) for i in range(td.count)}
        new = [w for w in WANT if w not in have]
        for w in new:
            td.append(donors[w])
            added += 1
        fn = e.get('floorName')
        floor = doc.strings.get(struct.unpack('<Q', fn.value())[0], '?') if fn else '?'
        print("     %-10s targetData %d -> %d   %s"
              % (floor, td.count - len(new), td.count,
                 '+' + ', '.join(new) if new else 'already armed'))

    print("  %d links appended" % added)
    out = doc.build()

    # re-read with the plain parser, the way the game would: the entity walk
    # only reaches the end if every size field it passes is right
    fx = fox2.Fox2(out)
    assert fx.count == len(doc.ents) and len(fx.ents) == fx.count, \
        "rebuilt file does not walk to the end"
    armed = 0
    for e in fx.ents:
        if str(e.name).split('|')[-1] != COND_SUFFIX:
            continue
        t = e.get('targetData')
        if t and all(any(v.split('|')[-1] == w for v in t.values) for w in WANT):
            armed += 1
    assert armed == len(targets), "only %d of %d conditions arm the ending" % (armed, len(targets))
    print("  verified: all %d conditions arm %s" % (armed, list(WANT)))
    return out


def overrides(archive, log=print):
    """{index: daten} fuer den gemeinsamen Bau ueber luaprobe.

    Damit laesst sich die Ending-Falle zusammen mit Stage, Tempo, Lampe und
    Spawn in EINEM Archiv bauen, statt chunk1.psarc gegenseitig zu ueber-
    schreiben. Dieselbe Form wie spawn.overrides().
    """
    i = archive.index_of(FPKD)
    raw = archive.read(i)
    fp = foxfpk.Fpk(foxfast.decrypt(raw))
    fp.replace(FOX2, patch(fp.get(FOX2)))
    new = foxfast.encrypt(fp.build())
    log('  Ending-Falle scharf: pt14_hallway.fpkd %d -> %d Byte'
        % (len(raw), len(new)))
    return {i: new}


def build():
    if not os.path.exists(ORIG):
        sys.exit("missing %s -- keep the untouched original there" % ORIG)
    a = psarc.Psarc(ORIG)
    i = a.index_of(FPKD)
    raw = a.read(i)
    fp = foxfpk.Fpk(foxfast.decrypt(raw))
    fp.replace(FOX2, patch(fp.get(FOX2)))
    new = foxfast.encrypt(fp.build())
    print("  pt14_hallway.fpkd: %d -> %d bytes" % (len(raw), len(new)))

    tmp = os.path.join(GAME, "chunk1.__new.psarc")
    psarc.build(a, tmp, {i: new})
    del a
    if os.path.exists(LIVE):
        os.remove(LIVE)
    os.rename(tmp, LIVE)
    print("  wrote %s (%d bytes)" % (LIVE, os.path.getsize(LIVE)))


def verify():
    a = psarc.Psarc(LIVE)
    b = psarc.Psarc(ORIG)
    fp = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(FPKD))))
    fx = fox2.Fox2(fp.get(FOX2))
    n = 0
    for e in fx.ents:
        if str(e.name).split('|')[-1] != COND_SUFFIX:
            continue
        t = e.get('targetData')
        if t and any(v.split('|')[-1] == WANT[0] for v in t.values):
            n += 1
    print("  in the built archive: %d conditions arm the ending trap" % n)
    changed = [nm for i, nm in enumerate(a.names) if a.read(i + 1) != b.read(i + 1)]
    print("  psarc entries changed: %d  %s" % (len(changed), changed))


if __name__ == "__main__":
    if "--restore" in sys.argv[1:]:
        if os.path.exists(LIVE):
            os.remove(LIVE)
        shutil.copy2(ORIG, LIVE)
        print("restored untouched original")
    else:
        build()
        verify()
