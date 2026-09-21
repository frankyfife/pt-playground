"""Give the street a stage root and a door connector, so the engine can place it.

Why this exists
---------------
LoadStage joins two stages by name: the arriving stage is moved until its
`targetConnector` sits on the departing stage's `baseConnector`, flipped 180
degrees in yaw so the two doorways face each other. That is measurable in the
shipped data -- the hallway's Connector_endDoor sits at local (-0.006, -1.400,
-6.100) with yaw 0, and the hallway's own stage root places Connector_startDoor
at exactly that world spot with yaw 180.

The street cannot take part in that. `ending.fpk` was never built as a relative
stage: it owns no ShRelativeStageLocator, no connector, and -- the part that
really bites -- no hierarchy at all. All 2160 StaticModels in ending_env.fox2
sit at parent=0. In pt14_start and pt14_hallway every single entity roots at the
ShRelativeStageLocator (69/69 and 2456/2456), which is how the engine moves a
stage: it sets the root's transform and the scene graph carries the geometry.
So a bare locator dropped next to the street would move an empty hierarchy and
the street would stay exactly where it was authored.

Hence three things, not one:
  1. a ShRelativeStageLocator with a named connector,
  2. a Locator the connector points at, placed at the near end of the road,
  3. all 2160 models re-parented onto that root.

Which file
----------
Everything goes into **ending_env.fox2**, not ending.fox2. Parent and connector
references are 48-bit entity addresses, and across all 32 .fox2 in the game not
one handle ever points into another file -- the only outward reference at all is
a dangling `capturePosition` in sh_sky.fox2. Cross-file parenting is therefore
completely unattested, and re-parenting is the part that must work. Both shipped
stages also keep their locator in the same file as the geometry it moves.

The one assumption left is that the engine looks for the ShRelativeStageLocator
across every DataSet of the loaded fpk rather than only in the fox2 whose name
matches it. That is what LoadStage's signature suggests -- it takes an .fpk path
and nothing names a root fox2 anywhere -- but it is the thing to re-check first
if the street still lands nowhere.

Orientation
-----------
The start room is the same shape as the street: its Connector_door sits at the
low-z end (0, 0, -12) facing yaw 180, i.e. pointing out of the room, with the
geometry running from z -12.95 up to 0. The road runs from z -8.2 to 239.3, so
its connector belongs at the low-z end facing the same way. If the player comes
out facing backwards, YAW is the single knob -- flip it by 180.

    python roadstage.py            # dry run, prints what it would build
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths
import fox2build

ENV_FOX2 = "/Assets/sh/level/promotion/pt_2014/ending/ending_env.fox2"
ROOT_FOX2 = "/Assets/sh/level/promotion/pt_2014/ending/ending.fox2"
START_FOX2 = "/Assets/sh/level/promotion/pt_2014/start/pt14_start.fox2"

CONNECTOR_KEY = "road"                    # what targetConnector must be set to
CONNECTOR_NAME = "ending|Connector_road"  # the entity the link resolves to

# Where the connector sits, in the street's own coordinates.
#
# The obvious choice is the near end of the road (0.4, 0, -7), just onto the
# lowest-z tile. That places fine and the street is visible at the door -- but
# the player drops straight through it, and the flags are not to blame: the
# street already ships 1471 models at flags=7 and 606 at 6, exactly like the
# hallway and the start room, and only 13 sat at 5. isIsolated is not it either
# (the start room is False throughout and perfectly solid).
#
# What is left is that the collision world does not follow the stage transform.
# Joining at the near end forces a big move plus a 180-degree turn: the visuals
# follow it, the collision stays at the authored coordinates, and the player
# falls through ground he can see.
#
# So put the connector where no move is needed. The start room's Connector_door
# sits at world (0, 0, 12) facing yaw 0, and the engine's rule -- measured on
# the hallway -- is target-connector world == base-connector world with yaw
# turned 180. Give the connector exactly that as its LOCAL transform and the
# stage transform comes out identity: the street stays on its authored
# coordinates, where its collision already is.
#
# (0, 0, 12) is well inside the road footprint: ground spans x -4.5..24,
# z -8.2..239, and z 0..10 alone holds 1269 models.
WHERE = (0.0, 0.0, 12.0)
YAW = 180.0


def _quat_y(deg):
    r = math.radians(deg) / 2.0
    return (0.0, math.sin(r), 0.0, math.cos(r))


GEOM_BIT = 0x2
EMPTY = 0xb8a0bf169f98          # StrCode64("")


def fix_collision(env, log=print):
    """Switch the street's collision back on.

    It is not missing, it is disabled. ending.fpk ships 63 .geom meshes and 2090
    of the 2160 StaticModels name one, but the ground and the main buildings sit
    at flags=5 -- 0b101, bit 1 clear -- while every walkable model in the hallway
    and the start room carries 7 or 6, both of which have that bit set. That is
    exactly the "scenery is solid but the floor is not there" behaviour: the
    player drops through the road, which is what Lance describes too.
    """
    n = 0
    for e in env.ents:
        g, f = e.get('geomFile'), e.get('flags')
        if g is None or f is None or g.count == 0 or f.count == 0:
            continue
        if struct.unpack('<Q', g.value())[0] == EMPTY:
            continue                       # nothing to collide with
        v = struct.unpack('<I', f.value())[0]
        if v & GEOM_BIT:
            continue
        f.set_value(0, struct.pack('<I', v | GEOM_BIT))
        n += 1
    log("  collision    bit set on %d StaticModels" % n)
    return n


def attach(env_blob, start_blob, where=WHERE, yaw=YAW,
           key=CONNECTOR_KEY, name=CONNECTOR_NAME, collision=True,
           donor_doc=None, log=print):
    """Returns the rebuilt ending_env.fox2."""
    env = fox2build.Doc.load(env_blob)
    if collision:
        fix_collision(env, log=log)
    src = fox2build.Doc.load(start_blob)

    if env.of_class('ShRelativeStageLocator'):
        raise RuntimeError('this ending_env.fox2 already has a stage root')

    # --- templates: copy a working locator rather than invent one -----------
    src_root = src.of_class('ShRelativeStageLocator')[0]
    src_conn = src.named('pt14_start|pt14_start_environ|Connector_door')[0]
    src_arr = src.of_class('StaticModelArrayLocator')[0]
    src_root_tf = src.by_addr(struct.unpack('<Q', src_root.require('transform').value())[0])
    src_conn_tf = src.by_addr(struct.unpack('<Q', src_conn.require('transform').value())[0])
    src_arr_tf = src.by_addr(struct.unpack('<Q', src_arr.require('transform').value())[0])

    root = env.copy_entity(src, src_root)
    root_tf = env.copy_entity(src, src_root_tf)
    conn = env.copy_entity(src, src_conn)
    conn_tf = env.copy_entity(src, src_conn_tf)
    arr = env.copy_entity(src, src_arr)
    arr_tf = env.copy_entity(src, src_arr_tf)

    dataset = env.dataset()

    # --- the stage root ----------------------------------------------------
    env.set_str(root, 'name', 'ShRelativeStageLocator')
    env.set_addr(root, 'dataSet', dataset.addr)
    env.set_addr(root, 'parent', 0)
    env.set_addr(root, 'transform', root_tf.addr)
    env.set_addr(root, 'shearTransform', 0)
    env.set_addr(root, 'pivotTransform', 0)
    env.set_u32(root, 'flags', 7)
    root.require('connectors').set_map_items(
        [(env.intern(key), env.link('', ENV_FOX2, name))])

    # identity: the engine overwrites this at load time with the placement it
    # solves for, exactly as it does for the hallway
    env.set_addr(root_tf, 'owner', root.addr)
    env.set_vec(root_tf, 'transform_scale', 1.0, 1.0, 1.0)
    env.set_vec(root_tf, 'transform_rotation_quat', 0.0, 0.0, 0.0, 1.0)
    env.set_vec(root_tf, 'transform_translation', 0.0, 0.0, 0.0)

    # --- the connector the link resolves to --------------------------------
    env.set_str(conn, 'name', name)
    env.set_addr(conn, 'dataSet', dataset.addr)
    env.set_addr(conn, 'parent', root.addr)
    env.set_addr(conn, 'transform', conn_tf.addr)
    env.set_addr(conn, 'shearTransform', 0)
    env.set_addr(conn, 'pivotTransform', 0)
    env.set_u32(conn, 'flags', 7)
    conn.require('children').set_items([])

    q = _quat_y(yaw)
    env.set_addr(conn_tf, 'owner', conn.addr)
    env.set_vec(conn_tf, 'transform_scale', 1.0, 1.0, 1.0)
    env.set_vec(conn_tf, 'transform_rotation_quat', *q)
    env.set_vec(conn_tf, 'transform_translation', where[0], where[1], where[2])

    # --- the StaticModelArrayLocator ---------------------------------------
    # Both walkable stages own exactly one of these and the ending stage owns
    # none -- it is the only class the start room has that the street lacks and
    # that the hallway also has. The name is literal: it holds the array of
    # static models, and the collision world is built from that subtree. Which
    # is why the street renders perfectly and has nothing to stand on, and why
    # Lance fell through it too. Hanging the models straight off the stage root
    # (as the first version did) reproduces the shipped omission.
    env.set_str(arr, 'name', 'StaticModelArrayLocator')
    env.set_addr(arr, 'dataSet', dataset.addr)
    env.set_addr(arr, 'parent', root.addr)
    env.set_addr(arr, 'transform', arr_tf.addr)
    env.set_addr(arr, 'shearTransform', 0)
    env.set_addr(arr, 'pivotTransform', 0)
    env.set_u32(arr, 'flags', 7)

    env.set_addr(arr_tf, 'owner', arr.addr)
    env.set_vec(arr_tf, 'transform_scale', 1.0, 1.0, 1.0)
    env.set_vec(arr_tf, 'transform_rotation_quat', 0.0, 0.0, 0.0, 1.0)
    env.set_vec(arr_tf, 'transform_translation', 0.0, 0.0, 0.0)

    # --- hang the street off the array locator, and that off the root ------
    # parent and children are kept mirror-consistent in the shipped data
    # (69/69 in pt14_start), so both sides get written.
    built = (root, conn, arr, root_tf, conn_tf, arr_tf)
    models = []
    for e in env.ents:
        if e in built:
            continue
        p = e.get('parent')
        if p is None or p.count == 0:
            continue
        if struct.unpack('<Q', p.value())[0] != 0:
            continue
        p.set_value(0, fox2build.pack_addr(arr.addr))
        models.append(e.addr)
    # --- optional: a floor borrowed from a stage that provably collides ------
    # The control run settled that the swap itself is fine -- pt14_hallway_maze_A
    # loaded through the same intercepted door was walkable. So either the
    # street's own meshes do not collide, or nothing in this stage does. One
    # cloned model answers that: shsb_hous001_vrtn004 is a maze_A house shell
    # with a 549 KB geom at flags=7, and it is walked on in the real game.
    #
    #   player stands on it -> the street's meshes are the problem, and a floor
    #                          can simply be built out of borrowed ones
    #   player falls anyway  -> this stage has no collision at all, and only a
    #                          runtime trick is left (which is where Lance ended)
    if donor_doc is not None:
        src_m = donor_doc.named(DONOR_NAME)
        if not src_m:
            raise KeyError('donor %r not found' % DONOR_NAME)
        src_m = src_m[0]
        src_mtf = donor_doc.by_addr(struct.unpack('<Q', src_m.require('transform').value())[0])
        m = env.copy_entity(donor_doc, src_m)
        mtf = env.copy_entity(donor_doc, src_mtf)
        env.set_str(m, 'name', 'ending|DonorFloor')
        env.set_addr(m, 'dataSet', dataset.addr)
        env.set_addr(m, 'parent', arr.addr)
        env.set_addr(m, 'transform', mtf.addr)
        env.set_addr(m, 'shearTransform', 0)
        env.set_addr(m, 'pivotTransform', 0)
        env.set_u32(m, 'flags', 7)
        m.require('children').set_items([])
        env.set_addr(mtf, 'owner', m.addr)
        env.set_vec(mtf, 'transform_scale', 1.0, 1.0, 1.0)
        env.set_vec(mtf, 'transform_rotation_quat', 0.0, 0.0, 0.0, 1.0)
        env.set_vec(mtf, 'transform_translation', *DONOR_AT)
        models.append(m.addr)
        dl0 = dataset.require('dataList')
        h = env.intern('ending|DonorFloor')
        if h not in set(dl0.keys()):
            dl0.append(fox2build.pack_addr(m.addr), key=h)
        log("  donor floor     @%x  %s at (%.1f, %.1f, %.1f)"
            % (m.addr, DONOR_NAME.split('|')[-1], DONOR_AT[0], DONOR_AT[1], DONOR_AT[2]))

    moved = len(models)
    arr.require('children').set_items([fox2build.pack_addr(a) for a in models])
    root.require('children').set_items(
        [fox2build.pack_addr(a) for a in (arr.addr, conn.addr)])

    # --- register the named entities in the DataSet ------------------------
    dl = dataset.require('dataList')
    have = set(dl.keys())
    for ent, nm in ((root, 'ShRelativeStageLocator'), (conn, name),
                    (arr, 'StaticModelArrayLocator')):
        h = env.intern(nm)
        if h not in have:
            dl.append(fox2build.pack_addr(ent.addr), key=h)

    log("  array locator   @%x  holds %d static models" % (arr.addr, moved))
    log("  stage root      @%x  connector %r -> %r" % (root.addr, key, name))
    log("  connector       @%x  t=(%.3f, %.3f, %.3f) yaw=%.1f" %
        (conn.addr, where[0], where[1], where[2], yaw))
    log("  re-parented     %d world-root entities onto the stage root" % moved)
    log("  dataList        %d entries" % dl.count)
    return env.build()


def attach_split(root_blob, env_blob, start_blob, where=WHERE, yaw=YAW,
                 key=CONNECTOR_KEY, name=CONNECTOR_NAME, log=print):
    """Same construction, but the locator goes into ending.fox2 -- the fox2 the
    fpk is named after -- while the geometry it moves stays in ending_env.fox2.

    Why: the log says no street asset was ever requested, not one of the 30
    street-exclusive shsb groups. The .fpkd holding the fox2 is read before any
    model is, so the engine can abandon the load before touching an asset --
    which is exactly what a missing ShRelativeStageLocator would cause, and it
    explains the earlier targetConnector="none" run too.

    The cost is that `parent` now crosses a file boundary, which nothing in the
    shipped data ever does. If the street loads but does not move with the
    locator, that is the answer, and the fix is to merge ending_env's entities
    into ending.fox2 rather than to point across.

    Returns (new_ending_fox2, new_ending_env_fox2).
    """
    root_doc = fox2build.Doc.load(root_blob)
    env = fox2build.Doc.load(env_blob)
    src = fox2build.Doc.load(start_blob)

    if root_doc.of_class('ShRelativeStageLocator'):
        raise RuntimeError('this ending.fox2 already has a stage root')

    src_root = src.of_class('ShRelativeStageLocator')[0]
    src_conn = src.named('pt14_start|pt14_start_environ|Connector_door')[0]
    src_root_tf = src.by_addr(struct.unpack('<Q', src_root.require('transform').value())[0])
    src_conn_tf = src.by_addr(struct.unpack('<Q', src_conn.require('transform').value())[0])

    root = root_doc.copy_entity(src, src_root)
    root_tf = root_doc.copy_entity(src, src_root_tf)
    conn = root_doc.copy_entity(src, src_conn)
    conn_tf = root_doc.copy_entity(src, src_conn_tf)
    dataset = root_doc.dataset()

    root_doc.set_str(root, 'name', 'ShRelativeStageLocator')
    root_doc.set_addr(root, 'dataSet', dataset.addr)
    root_doc.set_addr(root, 'parent', 0)
    root_doc.set_addr(root, 'transform', root_tf.addr)
    root_doc.set_addr(root, 'shearTransform', 0)
    root_doc.set_addr(root, 'pivotTransform', 0)
    root_doc.set_u32(root, 'flags', 7)
    root.require('connectors').set_map_items(
        [(root_doc.intern(key), root_doc.link('', ROOT_FOX2, name))])

    root_doc.set_addr(root_tf, 'owner', root.addr)
    root_doc.set_vec(root_tf, 'transform_scale', 1.0, 1.0, 1.0)
    root_doc.set_vec(root_tf, 'transform_rotation_quat', 0.0, 0.0, 0.0, 1.0)
    root_doc.set_vec(root_tf, 'transform_translation', 0.0, 0.0, 0.0)

    root_doc.set_str(conn, 'name', name)
    root_doc.set_addr(conn, 'dataSet', dataset.addr)
    root_doc.set_addr(conn, 'parent', root.addr)
    root_doc.set_addr(conn, 'transform', conn_tf.addr)
    root_doc.set_addr(conn, 'shearTransform', 0)
    root_doc.set_addr(conn, 'pivotTransform', 0)
    root_doc.set_u32(conn, 'flags', 7)
    conn.require('children').set_items([])

    q = _quat_y(yaw)
    root_doc.set_addr(conn_tf, 'owner', conn.addr)
    root_doc.set_vec(conn_tf, 'transform_scale', 1.0, 1.0, 1.0)
    root_doc.set_vec(conn_tf, 'transform_rotation_quat', *q)
    root_doc.set_vec(conn_tf, 'transform_translation', where[0], where[1], where[2])

    dl = dataset.require('dataList')
    have = set(dl.keys())
    for ent, nm in ((root, 'ShRelativeStageLocator'), (conn, name)):
        h = root_doc.intern(nm)
        if h not in have:
            dl.append(fox2build.pack_addr(ent.addr), key=h)

    # the geometry, in the other file, points back at the locator
    kids = [conn.addr]
    moved = 0
    for e in env.ents:
        p = e.get('parent')
        if p is None or p.count == 0:
            continue
        if struct.unpack('<Q', p.value())[0] != 0:
            continue
        p.set_value(0, fox2build.pack_addr(root.addr))
        kids.append(e.addr)
        moved += 1
    root.require('children').set_items([fox2build.pack_addr(a) for a in kids])

    log("  stage root      @%x in ending.fox2, connector %r -> %r"
        % (root.addr, key, name))
    log("  connector       @%x  t=(%.3f, %.3f, %.3f) yaw=%.1f"
        % (conn.addr, where[0], where[1], where[2], yaw))
    log("  re-parented     %d entities in ending_env.fox2 across the file boundary"
        % moved)
    return root_doc.build(), env.build()


def _selfcheck(blob, key=CONNECTOR_KEY, name=CONNECTOR_NAME, log=print):
    """Re-read the built file the way the game would."""
    import fox2
    fx = fox2.Fox2(blob)
    root = fx.find(cls='ShRelativeStageLocator')
    assert len(root) == 1, 'expected one stage root, found %d' % len(root)
    root = root[0]
    conn = [e for e in fx.ents if e.name == name]
    assert len(conn) == 1, 'expected one connector, found %d' % len(conn)
    conn = conn[0]

    c = root.get('connectors')
    assert c.count == 1 and c.keys[0] == key, 'connector map is %r' % c
    assert c.values[0] == '|%s|%s' % (ENV_FOX2, name), 'link is %r' % c.values[0]

    arr = fx.find(cls='StaticModelArrayLocator')
    assert len(arr) == 1, 'expected one StaticModelArrayLocator, found %d' % len(arr)
    arr = arr[0]

    def kids_of(e):
        return {int(v[1:], 16) for v in e.get('children').values if v != '@0'}

    def parented_to(e):
        return {x.addr for x in fx.ents if x.get('parent')
                and int(x.get('parent').values[0][1:], 16) == e.addr}

    orphans = [e for e in fx.ents
               if e.get('parent') and int(e.get('parent').values[0][1:], 16) == 0
               and e.addr != root.addr]
    assert not orphans, '%d entities still at parent 0' % len(orphans)
    assert kids_of(root) == parented_to(root) == {arr.addr, conn.addr}, \
        'stage root should hold exactly the array locator and the connector'
    assert kids_of(arr) == parented_to(arr), \
        'array locator children and parent links disagree'
    assert int(arr.get('parent').values[0][1:], 16) == root.addr, \
        'array locator is not under the stage root'
    kids = kids_of(arr)

    tf = fx.by_addr[int(conn.get('transform').values[0][1:], 16)]
    import collections
    c = collections.Counter()
    for e in fx.find(cls='StaticModel'):
        g, f = e.get('geomFile'), e.get('flags')
        if g and f:
            c[(f.values[0], bool(g.values[0]))] += 1
    left = [k for k in c if k[1] and not (k[0] & GEOM_BIT)]
    assert not left, "still collision-less with a geom mesh: %s" % left
    log("  verified: %d entities, root @%x, %d children, connector at %s" %
        (fx.count, root.addr, len(kids),
         tf.get('transform_translation').values[0][:3]))
    log("  verified: StaticModel (flags, hasGeom) %s, none walkable without the bit"
        % dict(c))
    return True


def _selfcheck_split(root_blob, env_blob, key=CONNECTOR_KEY,
                     name=CONNECTOR_NAME, log=print):
    import fox2
    rx = fox2.Fox2(root_blob)
    ex = fox2.Fox2(env_blob)
    root = rx.find(cls='ShRelativeStageLocator')
    assert len(root) == 1, 'expected one stage root, found %d' % len(root)
    root = root[0]
    conn = [e for e in rx.ents if e.name == name]
    assert len(conn) == 1, 'expected one connector, found %d' % len(conn)
    conn = conn[0]

    c = root.get('connectors')
    assert c.count == 1 and c.keys[0] == key, 'connector map is %r' % c
    assert c.values[0] == '|%s|%s' % (ROOT_FOX2, name), 'link is %r' % c.values[0]

    kids = {int(v[1:], 16) for v in root.get('children').values}
    pointed = {e.addr for e in ex.ents
               if e.get('parent') and int(e.get('parent').values[0][1:], 16) == root.addr}
    orphans = [e for e in ex.ents
               if e.get('parent') and int(e.get('parent').values[0][1:], 16) == 0]
    assert not orphans, '%d entities in ending_env still at parent 0' % len(orphans)
    assert kids == pointed | {conn.addr}, 'children list and parent links disagree'

    tf = rx.by_addr[int(conn.get('transform').values[0][1:], 16)]
    log("  verified: ending.fox2 %d entities, ending_env %d, root @%x, %d children,"
        " connector at %s" % (rx.count, ex.count, root.addr, len(kids),
                              tf.get('transform_translation').values[0][:3]))
    return True


ENDING_FPKD = "/as/sh/level/promotion/pt_2014/ending/ending.fpkd"
ENDING_FPK = "/as/sh/level/promotion/pt_2014/ending/ending.fpk"
START_FPKD = "/as/sh/level/promotion/pt_2014/start/pt14_start.fpkd"

# a model from a stage that provably collides, for the discriminating test
DONOR_FPKD = "/as/sh/level/promotion/pt_2014/hallway_maze_A/pt14_hallway_maze_A.fpkd"
DONOR_FPK = "/as/sh/level/promotion/pt_2014/hallway_maze_A/pt14_hallway_maze_A.fpk"
DONOR_FOX2 = "/Assets/sh/level/promotion/pt_2014/hallway_maze_A/pt14_hallway_maze_A.fox2"
DONOR_NAME = "pt14_hallway_maze_A|pt14_hallway_env_A|shsb_hous001_vrtn004_0000"
DONOR_ASSET = "shsb_hous001_vrtn004"
DONOR_AT = (0.0, 0.0, 12.0)      # right where the connector puts the player

# A catch floor, on request: the street's own ground mesh duplicated one metre
# lower. shsb_mapp001 is tiled three times along z (0, 108, 201) and so covers
# the map exactly; scaling each copy by 1.1 adds roughly five metres of margin
# all round. Using the real ground rather than a flat plate keeps the kerbs and
# pavement profile, just lowered.
FLOOR_SOURCES = ("shsb_mapp001_0000", "shsb_mapp001_0001", "shsb_mapp001_0002")
FLOOR_Y = -1.0
FLOOR_SCALE = 1.1


def merge_into_root(root_blob, env_blob, start_blob, where=WHERE, yaw=YAW,
                    key=CONNECTOR_KEY, name=CONNECTOR_NAME, floor=False,
                    log=print):
    """Move the street into ending.fox2 and build the stage there.

    Every stage in the game that a player can walk on is a single fox2 with its
    models inside it. The ending is the only one split across several, and its
    2160 models live in ending_env.fox2 -- a secondary file. Everything else has
    now been ruled out: the load path is fine (maze_A swapped onto the same door
    was walkable), the meshes all ship and are full, the flags match, the
    hierarchy has been rebuilt down to the StaticModelArrayLocator, identity
    placement changed nothing, and a model borrowed from a stage that provably
    collides did not collide here either.

    That last result is what points here: the borrowed model was placed in
    ending_env.fox2 too. If the collision world is built from the stage's root
    fox2, its failure is exactly what this hypothesis predicts.

    So: merge the models into ending.fox2, leave ending_env.fox2 as an empty
    DataSet, and hang the stage root there. Returns (root, env).
    """
    root = fox2build.Doc.load(root_blob)
    env = fox2build.Doc.load(env_blob)
    src = fox2build.Doc.load(start_blob)
    fix_collision(env, log=log)

    if root.of_class('ShRelativeStageLocator'):
        raise RuntimeError('this ending.fox2 already has a stage root')

    rds = root.dataset()
    eds = env.dataset()
    root.strings.update(env.strings)

    # --- move every entity except the source DataSet ------------------------
    moved = [e for e in env.ents if e is not eds]
    for e in moved:
        d = e.get('dataSet')
        if d is not None and d.count:
            if struct.unpack('<Q', d.value())[0] == eds.addr:
                d.set_value(0, fox2build.pack_addr(rds.addr))
        root.ents.append(e)
    log("  merged          %d entities into ending.fox2" % len(moved))

    edl = eds.require('dataList')
    rdl = rds.require('dataList')
    have = set(rdl.keys())
    for i in range(edl.count):
        k = edl.key(i)
        if k not in have:
            rdl.append(edl.value(i), key=k)
            have.add(k)

    # --- the stage, built in the root file now ------------------------------
    src_root = src.of_class('ShRelativeStageLocator')[0]
    src_conn = src.named('pt14_start|pt14_start_environ|Connector_door')[0]
    src_arr = src.of_class('StaticModelArrayLocator')[0]
    g = lambda e: src.by_addr(struct.unpack('<Q', e.require('transform').value())[0])

    loc = root.copy_entity(src, src_root)
    loc_tf = root.copy_entity(src, g(src_root))
    conn = root.copy_entity(src, src_conn)
    conn_tf = root.copy_entity(src, g(src_conn))
    arr = root.copy_entity(src, src_arr)
    arr_tf = root.copy_entity(src, g(src_arr))

    for ent, nm, parent, tf in ((loc, 'ShRelativeStageLocator', 0, loc_tf),
                                (arr, 'StaticModelArrayLocator', None, arr_tf),
                                (conn, name, None, conn_tf)):
        root.set_str(ent, 'name', nm)
        root.set_addr(ent, 'dataSet', rds.addr)
        root.set_addr(ent, 'parent', loc.addr if parent is None else parent)
        root.set_addr(ent, 'transform', tf.addr)
        root.set_addr(ent, 'shearTransform', 0)
        root.set_addr(ent, 'pivotTransform', 0)
        root.set_u32(ent, 'flags', 7)
        root.set_addr(tf, 'owner', ent.addr)
        root.set_vec(tf, 'transform_scale', 1.0, 1.0, 1.0)
        root.set_vec(tf, 'transform_rotation_quat', 0.0, 0.0, 0.0, 1.0)
        root.set_vec(tf, 'transform_translation', 0.0, 0.0, 0.0)

    loc.require('connectors').set_map_items(
        [(root.intern(key), root.link('', ROOT_FOX2, name))])
    conn.require('children').set_items([])
    q = _quat_y(yaw)
    root.set_vec(conn_tf, 'transform_rotation_quat', *q)
    root.set_vec(conn_tf, 'transform_translation', where[0], where[1], where[2])

    built = (loc, arr, conn, loc_tf, arr_tf, conn_tf)
    models = []
    for e in root.ents:
        if e in built:
            continue
        p = e.get('parent')
        if p is None or p.count == 0:
            continue
        if struct.unpack('<Q', p.value())[0] != 0:
            continue
        p.set_value(0, fox2build.pack_addr(arr.addr))
        models.append(e.addr)
    if floor:
        made = 0
        for nm in FLOOR_SOURCES:
            hits = root.named(nm)
            if not hits:
                log("  catch floor     source %r not found, skipped" % nm)
                continue
            srcm = hits[0]
            srctf = root.by_addr(struct.unpack('<Q', srcm.require('transform').value())[0])
            m = root.copy_entity(root, srcm)
            mtf = root.copy_entity(root, srctf)
            base = struct.unpack('<4f', srctf.require('transform_translation').value())
            root.set_str(m, 'name', 'ending|CatchFloor_%d' % made)
            root.set_addr(m, 'dataSet', rds.addr)
            root.set_addr(m, 'parent', arr.addr)
            root.set_addr(m, 'transform', mtf.addr)
            root.set_addr(m, 'shearTransform', 0)
            root.set_addr(m, 'pivotTransform', 0)
            root.set_u32(m, 'flags', 7)
            m.require('children').set_items([])
            root.set_addr(mtf, 'owner', m.addr)
            root.set_vec(mtf, 'transform_scale', FLOOR_SCALE, FLOOR_SCALE, FLOOR_SCALE)
            root.set_vec(mtf, 'transform_rotation_quat', 0.0, 0.0, 0.0, 1.0)
            root.set_vec(mtf, 'transform_translation', base[0], FLOOR_Y, base[2])
            models.append(m.addr)
            h = root.intern('ending|CatchFloor_%d' % made)
            if h not in have:
                rdl.append(fox2build.pack_addr(m.addr), key=h)
                have.add(h)
            log("  catch floor     @%x from %-18s at (%.2f, %.2f, %.2f) scale %.2f"
                % (m.addr, nm, base[0], FLOOR_Y, base[2], FLOOR_SCALE))
            made += 1

    arr.require('children').set_items([fox2build.pack_addr(x) for x in models])
    loc.require('children').set_items(
        [fox2build.pack_addr(x) for x in (arr.addr, conn.addr)])

    for ent, nm in ((loc, 'ShRelativeStageLocator'), (conn, name),
                    (arr, 'StaticModelArrayLocator')):
        h = root.intern(nm)
        if h not in have:
            rdl.append(fox2build.pack_addr(ent.addr), key=h)
            have.add(h)

    # --- ending_env.fox2 keeps only its (now empty) DataSet -----------------
    env.ents = [eds]
    edl.set_map_items([])

    log("  stage root      @%x in ending.fox2, %d models under the array locator"
        % (loc.addr, len(models)))
    log("  connector       @%x  t=(%.1f, %.1f, %.1f) yaw=%.1f  key=%r"
        % (conn.addr, where[0], where[1], where[2], yaw, key))
    return root.build(), env.build()



def _strip_player(a, log=print):
    """Take the cutscene's own player out of ending.fpk.

    ending.fpk carries 2.67 MB of character data -- plr0_main0_def.fmdl, its
    .fcnp and a finger rig -- because the shipped ending animates its own actor.
    pt14_hallway_maze_A.fpk and pt14_start.fpk carry none of that, and both are
    walkable through the very same intercepted door.

    So loading this stage hands the engine a second, cutscene-flavoured player
    definition. If that is what the player ends up as, nothing about the ground
    matters: a demo actor has no reason to be kept on it. That would also
    explain why a borrowed collision mesh and a catch floor changed nothing --
    the problem is not the stage's collision, it is the player's.
    """
    import foxfast, foxfpk
    fp = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(ENDING_FPK))))
    keep, drop = [], []
    for e in fp.ents:
        low = e['path'].lower()
        (drop if ('/chara/' in low or '/rig/' in low) else keep).append(e)
    for e in drop:
        log("  stripped        %9d B  %s" % (len(e['data']), e['path']))
    fp.ents = keep
    fp.count = len(keep)
    log("  ending.fpk      %d -> %d entries" % (len(keep) + len(drop), len(keep)))
    return {a.index_of(ENDING_FPK): foxfast.encrypt(fp.build())}


def overrides(a, donor=False, merge=False, floor=False,
              strip_player=False, log=print):
    """{psarc index: rebuilt ending.fpkd} for an open Psarc.

    Uses attach(), i.e. the locator lives in ending_env.fox2 beside the geometry
    it moves, so `parent` never crosses a file boundary -- which nothing in the
    shipped data ever does.
    """
    import foxfast, foxfpk
    ep = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(ENDING_FPKD))))
    sp = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(START_FPKD))))
    if merge:
        r, e = merge_into_root(ep.get(ROOT_FOX2), ep.get(ENV_FOX2),
                               sp.get(START_FOX2), floor=floor, log=log)
        log("  ending.fox2: %d -> %d bytes, ending_env.fox2 -> %d bytes"
            % (len(ep.get(ROOT_FOX2)), len(r), len(e)))
        ep.replace(ROOT_FOX2, r)
        ep.replace(ENV_FOX2, e)
        out = {a.index_of(ENDING_FPKD): foxfast.encrypt(ep.build())}
        if strip_player:
            out.update(_strip_player(a, log=log))
        return out

    donor_doc = None
    if donor:
        dp = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(DONOR_FPKD))))
        donor_doc = fox2build.Doc.load(dp.get(DONOR_FOX2))
    old = ep.get(ENV_FOX2)
    new = attach(old, sp.get(START_FOX2), donor_doc=donor_doc, log=log)
    _selfcheck(new, log=log)
    log("  ending_env.fox2: %d -> %d bytes" % (len(old), len(new)))
    ep.replace(ENV_FOX2, new)
    out = {a.index_of(ENDING_FPKD): foxfast.encrypt(ep.build())}

    if donor:
        # the donor's mesh and collision live in maze_A's asset container, so
        # they have to travel with it -- entry hashes are MD5 of the PATH, so a
        # container takes new payloads of any size without complaint
        ak = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(DONOR_FPK))))
        ek = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(ENDING_FPK))))
        have = {e['path'].lower() for e in ek.ents}
        n = 0
        for e in ak.ents:
            if DONOR_ASSET in e['path'].lower() and e['path'].lower() not in have:
                ek.add(e['path'], e['data'])
                n += 1
                log("  donor asset     %9d B  %s" % (len(e['data']), e['path']))
        log("  ending.fpk      +%d entries" % n)
        out[a.index_of(ENDING_FPK)] = foxfast.encrypt(ek.build())
    return out


if __name__ == '__main__':
    import psarc, foxfast, foxfpk
    GAME = ptpaths.GAME
    a = psarc.Psarc(os.path.join(GAME, "chunk1.orig.psarc"))
    ep = foxfpk.Fpk(foxfast.decrypt(
        a.read(a.index_of("/as/sh/level/promotion/pt_2014/ending/ending.fpkd"))))
    sp = foxfpk.Fpk(foxfast.decrypt(
        a.read(a.index_of("/as/sh/level/promotion/pt_2014/start/pt14_start.fpkd"))))
    oldr, olde = ep.get(ROOT_FOX2), ep.get(ENV_FOX2)
    newr, newe = attach_split(oldr, olde, sp.get(START_FOX2))
    print("  ending.fox2:     %d -> %d bytes" % (len(oldr), len(newr)))
    print("  ending_env.fox2: %d -> %d bytes" % (len(olde), len(newe)))
    _selfcheck_split(newr, newe)
