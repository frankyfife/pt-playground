"""Give the ending stage a player spawn, so the street is somewhere to stand.

Evidence this is the missing piece
----------------------------------
GotoEnding() loads the street with **SetNextStageByPath** -- the very call the
game uses to boot into pt14_start. And pt14_start is the only stage in the whole
game that owns a player spawn:

    GameObjectLocator "pt14_start|PlayerLocator"  typeName=ShPlayer groupId=0
      transform  (0, 0, -9.53)      -- y sits exactly on the floor
      parameters -> ShPlayerLocatorParameter (owner only)

The hallway has none (its connector carries the player across) and ending.fpk
has none (the shipped cutscene places the player itself). So once the sequence
ends, nothing has ever told the engine where the player is -- which is what a
game-over firing over and over looks like. Round 3 blocked GotoGameOver 14 times
and it simply kept coming.

So: clone that spawn into ending.fox2 and put it on the road. Three entities --
the locator, its TransformEntity and its parameter block -- copied out of
pt14_start rather than invented, which is what fox2build.copy_entity is for.

Road geometry: ground dead flat at y=0, x -4.5..24.0, z -8.2..239.3, with the
dense part between z -8 and 30. The lowest-z road tile sits at (0.403, 0, -8.2).

    python endingspawn.py            # dry run, prints what it would build
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths
import fox2build

ENDING_FPKD = "/as/sh/level/promotion/pt_2014/ending/ending.fpkd"
START_FPKD = "/as/sh/level/promotion/pt_2014/start/pt14_start.fpkd"
ROOT_FOX2 = "/Assets/sh/level/promotion/pt_2014/ending/ending.fox2"
START_FOX2 = "/Assets/sh/level/promotion/pt_2014/start/pt14_start.fox2"

SPAWN_NAME = "ending|PlayerLocator"
# Runde 23 landete "ganz unten, weit unter der Strasse". Dafuer gibt es zwei
# Ursachen, die von aussen gleich aussehen: der Spawn wird ignoriert, oder er
# greift und der Spieler faellt sofort durch. Drei Meter Hoehe trennen sie --
# startet er oben und sinkt, greift der Locator und es ist die Kollision;
# landet er sofort wieder unten, wird der Locator gar nicht benutzt.
# 3 m waren zu wenig -- der Nutzer konnte nicht sagen, ob er faellt. 30 m
# sind rund 2,5 Sekunden Fall und damit unuebersehbar.
WHERE = (0.4, 30.0, 0.0)    # auf der Fahrbahn, nahes Ende, 30 m darueber
YAW = 0.0                   # Blick nach +z, in Strassenrichtung


def _quat_y(deg):
    r = math.radians(deg) / 2.0
    return (0.0, math.sin(r), 0.0, math.cos(r))


def patch(root_blob, start_blob, where=WHERE, yaw=YAW, name=SPAWN_NAME, log=print):
    root = fox2build.Doc.load(root_blob)
    src = fox2build.Doc.load(start_blob)

    if root.named(name):
        raise RuntimeError("ending.fox2 already has %r" % name)

    src_loc = src.named("pt14_start|PlayerLocator")
    if len(src_loc) != 1:
        raise KeyError("expected one PlayerLocator in pt14_start, found %d" % len(src_loc))
    src_loc = src_loc[0]
    src_tf = src.by_addr(struct.unpack('<Q', src_loc.require('transform').value())[0])
    src_par = src.by_addr(struct.unpack('<Q', src_loc.require('parameters').value())[0])
    if src_tf is None or src_par is None:
        raise KeyError("PlayerLocator's transform or parameters are missing")

    loc = root.copy_entity(src, src_loc)
    tf = root.copy_entity(src, src_tf)
    par = root.copy_entity(src, src_par)
    dataset = root.dataset()

    root.set_str(loc, 'name', name)
    root.set_addr(loc, 'dataSet', dataset.addr)
    root.set_addr(loc, 'parent', 0)          # the ending stage has no hierarchy
    root.set_addr(loc, 'transform', tf.addr)
    root.set_addr(loc, 'shearTransform', 0)
    root.set_addr(loc, 'pivotTransform', 0)
    root.set_addr(loc, 'parameters', par.addr)
    root.set_u32(loc, 'flags', 7)
    root.set_u32(loc, 'groupId', 0)
    root.set_str(loc, 'typeName', 'ShPlayer')
    loc.require('children').set_items([])

    q = _quat_y(yaw)
    root.set_addr(tf, 'owner', loc.addr)
    root.set_vec(tf, 'transform_scale', 1.0, 1.0, 1.0)
    root.set_vec(tf, 'transform_rotation_quat', *q)
    root.set_vec(tf, 'transform_translation', where[0], where[1], where[2])

    root.set_addr(par, 'owner', loc.addr)

    dl = dataset.require('dataList')
    h = root.intern(name)
    if h not in set(dl.keys()):
        dl.append(fox2build.pack_addr(loc.addr), key=h)

    log("  spawn %r @%x  t=(%.3f, %.3f, %.3f) yaw=%.1f  typeName=ShPlayer"
        % (name, loc.addr, where[0], where[1], where[2], yaw))
    log("  dataList %d entries" % dl.count)
    return root.build()


def selfcheck(blob, name=SPAWN_NAME, log=print):
    import fox2
    fx = fox2.Fox2(blob)
    got = [e for e in fx.ents if e.name == name]
    assert len(got) == 1, "expected one %r, found %d" % (name, len(got))
    e = got[0]
    assert e.cls == 'GameObjectLocator', "spawn is a %s" % e.cls
    assert e.get('typeName').values[0] == 'ShPlayer', \
        "typeName is %r" % e.get('typeName').values[0]
    tf = fx.by_addr[int(e.get('transform').values[0][1:], 16)]
    par = fx.by_addr[int(e.get('parameters').values[0][1:], 16)]
    assert par.cls == 'ShPlayerLocatorParameter', "parameters is a %s" % par.cls
    assert int(par.get('owner').values[0][1:], 16) == e.addr, "parameter owner is wrong"
    log("  verified: %d entities, spawn at %s, %s"
        % (fx.count, tf.get('transform_translation').values[0][:3], par.cls))
    return True


def overrides(a):
    """{psarc index: rebuilt ending.fpkd} for an open Psarc."""
    import foxfast, foxfpk
    ep = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(ENDING_FPKD))))
    sp = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(START_FPKD))))
    old = ep.get(ROOT_FOX2)
    new = patch(old, sp.get(START_FOX2))
    selfcheck(new)
    print("  ending.fox2: %d -> %d bytes" % (len(old), len(new)))
    ep.replace(ROOT_FOX2, new)
    return {a.index_of(ENDING_FPKD): foxfast.encrypt(ep.build())}


if __name__ == '__main__':
    import psarc
    GAME = ptpaths.GAME
    a = psarc.Psarc(os.path.join(GAME, "chunk1.orig.psarc"))
    overrides(a)
