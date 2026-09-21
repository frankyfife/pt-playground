"""Ein Gimmick in den Startraum setzen -- Lisa, das Baby, die Deckenlampe.

Wie ein Spawn in P.T. aussieht
------------------------------
Zwei Entities, aus den ausgelieferten Daten abgelesen (pt14_hallway.fox2):

    GameObjectLocator
        name        "stage|gruppe|GimmickLocator_<X>"
        parent      -> ShRelativeStageLocator der Stage
        transform   -> TransformEntity (Position, Drehung)
        flags       7
        typeName    "ShGimmick"
        groupId     0
        parameters  -> ShGimmickLocatorParameter

    ShGimmickLocatorParameter
        owner       -> der GameObjectLocator
        partsType   "Ocho" | "Baby" | "Bag" | "CeilLamp" | "Freezer"

Statt die Entities von Grund auf zu bauen, werden die **echten aus dem Flur
kopiert** und umgeschrieben -- so stimmen alle Felder, die wir gar nicht kennen.

Ziel ist der **Startraum**: er ist immer geladen, ueberschaubar und man steht
sofort davor. Ausmasse, an den 69 Objektpositionen in pt14_start.fox2
nachgemessen (nicht geschaetzt):

    x   -2.278 .. 2.092
    y   -0.200 .. 2.994      y 0 = Boden, y ~3 = Decke, y 0.8 = Tischplatte
    z  -12.954 .. 0.000      Spieler bei z -9.5, Tuer bei z 0

Dort wurzeln alle 69 Entities am ShRelativeStageLocator, neue muessen also
genauso haengen.

partsType: nur diese fuenf sind im Spiel belegt. Der Verteiler FUN_00953260
kennt 15 Werte, die uebrigen zehn Namen sind unbekannt (9900 Kandidaten
durchprobiert, kein Treffer) -- darunter vermutlich die Halbfrau `hsh`.

    python spawn.py                       Lisa auf halber Strecke
    python spawn.py --parts Baby --at 0,0,-9
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fox2build
import foxfast
import foxfpk

START_FPKD = "/as/sh/level/promotion/pt_2014/start/pt14_start.fpkd"
START_FOX2 = "/Assets/sh/level/promotion/pt_2014/start/pt14_start.fox2"
PARTS = ('Ocho', 'Baby', 'Bag', 'CeilLamp', 'Freezer')

# Zusaetzliche Modelle, die das Spiel NICHT als Gimmick registriert, fuer die es
# aber eine .parts gibt -- ohne die kann das Gimmick-System nichts erzeugen.
# Gefunden durch Auflisten der .fpkd:
#
#     resident.fpkd         5 .parts  -> genau die fuenf oben
#     plparts_normal.fpkd   2 .parts  -> plr (Spieler) und lig (Lampe)
#
# Die uebrigen Modelle in resident.fpk (coc, dol, hsh = Half_Women, lte) haben
# ein .fmdl, aber KEINE .parts -- die liessen sich nur mit einer selbst
# geschriebenen .parts spawnen, das ist ein eigenes Vorhaben.
#
# Registriert wird ueber ShGimmickSetUp.lua, die dieselbe Form benutzt wie die
# fuenf Originale. Ob das Spiel ohne AddMotionPath auskommt, ist NICHT belegt --
# alle fuenf Originale bringen eine Bewegung mit. Deshalb steht hier, wo
# bekannt, eine mit dabei.
EXTRA_PARTS = {
    'Player': ('/Assets/sh/parts/chara/plr/plr0_main0_def_v00.parts', None),
    'Flashlight': ('/Assets/sh/parts/item/lig/lig0_main0_def.parts', None),
}

GIMMICK_LUA = '/as/sh/level_asset/chara/gimmick/ShGimmickSetUp.lua'


def _register_extra(archive, parts):
    """ShGimmickSetUp.lua um einen partsType erweitern.

    Rueckgabe: {index: klartext} oder {} wenn nichts zu tun ist.

    Die Datei ist LCG-verschluesselt, der Loader nimmt aber auch Klartext an
    (kein Magic => keine Entschluesselung) -- genau wie bei ShParameterTables
    und start.lua. Deshalb wird hier unverschluesselt zurueckgegeben.
    """
    if parts not in EXTRA_PARTS:
        return {}
    import foxlua
    path, motion = EXTRA_PARTS[parts]
    i = archive.index_of(GIMMICK_LUA)
    src = foxlua.decrypt(archive.read(i))
    if b'AddPartsPath' not in src:
        sys.exit('  AddPartsPath nicht in %s -- Aufbau unerwartet' % GIMMICK_LUA)
    nl = chr(10)
    add = nl + ('--%s (nachtraeglich registriert)' % parts) + nl
    add += ('Gimmick.AddPartsPath{ partName = "%s", path = "%s" }'
            % (parts, path)) + nl
    if motion:
        add += ('Gimmick.AddMotionPath{ key = "%s", path = "%s" }'
                % (parts, motion)) + nl
    # vor das abschliessende `return this`, sonst laeuft die Zeile nie
    tail = b'return this'
    if tail in src:
        cut = src.rindex(tail)
        out = src[:cut] + add.encode('utf8') + src[cut:]
    else:
        out = src + add.encode('utf8')
    return {i: out}

# Bezugspunkte, aus pt14_start.fox2 ausgelesen (nicht geschaetzt):
#
#     ShPlayer    (0.000, 0.000, -9.531)   Blickrichtung 0 Grad
#     ShGimmick   (2.092, 0.800, -7.218)   das Gimmick, das der Raum selbst hat
#
# Vorgabe deshalb einen Meter rechts und einen Meter vor dem Spieler -- da
# steht man beim Spielstart unmittelbar davor. Ein Wert wie (0,0,-6) liegt
# dagegen 3,5 m hinter dem Spieler und damit ausserhalb des Blickfelds.
PLAYER_AT = (0.0, 0.0, -9.531)
AT = (1.0, 0.0, -8.5)
# Das Objekt, das der Startraum selbst mitbringt, ist die Papiertuete auf dem
# Tisch. Ihre Position ist damit die exakte Tischplatte -- brauchbar, weil ein
# Objekt bei y=0 im Tisch steckt statt darauf.
BAG_AT = (2.092, 0.8, -7.218)
# Wo das Baby wirklich sauber auf dem Tisch sitzt -- IM SPIEL ausprobiert und
# vom Nutzer bestaetigt, nicht aus den Leveldaten abgeleitet:
#
#   x 1.6     neben der Tuete statt in ihr
#   y 0.90    Tischplatte ist 0.8; bei 0.8 sinkt das Modell ein, weil sein
#             Ursprung nicht an den Fuessen liegt
#   z -7.9    die Tuetenposition -7.218 setzte es zu weit nach hinten
#
# Frueher stand hier -7.218 (die exakte Tuetenposition) und y 0.95, beides aus
# den Daten hergeleitet. Der Versuch im Spiel hat beides korrigiert.
TABLE_AT = (1.6, 0.9, -7.9)


def _fpk(archive, path):
    return foxfpk.Fpk(foxfast.decrypt(archive.read(archive.index_of(path))))


def _quat_y(deg):
    import math
    r = math.radians(deg) / 2.0
    return (0.0, math.sin(r), 0.0, math.cos(r))


def overrides(archive, parts='Ocho', at=AT, yaw=0.0, log=print):
    known = tuple(PARTS) + tuple(EXTRA_PARTS)
    if parts not in known:
        sys.exit('  unbekannter partsType %r -- moeglich: %s'
                 % (parts, ', '.join(known)))

    start = _fpk(archive, START_FPKD)
    dst = fox2build.Doc.load(start.get(START_FOX2))

    # --- Vorlage: das Gimmick, das der Startraum SELBST hat ----------------
    # Aus derselben Stage zu kopieren ist sicherer als aus dem Flur: Eltern-
    # knoten, Namensschema und Flags stimmen dann von allein. Der Startraum hat
    # genau zwei GameObjectLocator -- den PlayerLocator (typeName "ShPlayer")
    # und ein Gimmick. Gebraucht wird das zweite.
    gl = [e for e in dst.of_class('GameObjectLocator')
          if _text(dst, e, 'typeName') == 'ShGimmick']
    if not gl:
        sys.exit('  kein vorhandenes Gimmick im Startraum -- Vorlage fehlt')
    t_loc = gl[0]
    t_tf = dst.by_addr(_addr(t_loc, 'transform'))
    t_par = dst.by_addr(_addr(t_loc, 'parameters'))
    if t_tf is None or t_par is None:
        sys.exit('  Vorlage unvollstaendig (transform/parameters fehlen)')

    # --- kopieren ----------------------------------------------------------
    loc = dst.copy_entity(dst, t_loc)
    tf = dst.copy_entity(dst, t_tf)
    par = dst.copy_entity(dst, t_par)

    root = dst.by_addr(_addr(t_loc, 'parent'))       # die Gimmick-Gruppe
    if root is None:
        sys.exit('  Elternknoten der Vorlage nicht gefunden')
    dataset = dst.dataset()
    name = 'pt14_start|pt14_start_gimmick|GimmickLocator_%s' % parts

    dst.set_str(loc, 'name', name)
    dst.set_addr(loc, 'dataSet', dataset.addr)
    dst.set_addr(loc, 'parent', root.addr)
    dst.set_addr(loc, 'transform', tf.addr)
    dst.set_addr(loc, 'shearTransform', 0)
    dst.set_addr(loc, 'pivotTransform', 0)
    dst.set_u32(loc, 'flags', 7)
    dst.set_str(loc, 'typeName', 'ShGimmick')
    dst.set_u32(loc, 'groupId', 0)
    dst.set_addr(loc, 'parameters', par.addr)
    loc.require('children').set_items([])

    q = _quat_y(yaw)
    dst.set_addr(tf, 'owner', loc.addr)
    dst.set_vec(tf, 'transform_scale', 1.0, 1.0, 1.0)
    dst.set_vec(tf, 'transform_rotation_quat', *q)
    dst.set_vec(tf, 'transform_translation', at[0], at[1], at[2])

    dst.set_addr(par, 'owner', loc.addr)
    dst.set_str(par, 'partsType', parts)

    # --- anhaengen und eintragen ------------------------------------------
    kids = root.require('children')
    have = [kids.value(i) for i in range(kids.count)]
    kids.set_items(have + [fox2build.pack_addr(loc.addr)])

    dl = dataset.require('dataList')
    h = dst.intern(name)
    if h not in set(dl.keys()):
        dl.append(fox2build.pack_addr(loc.addr), key=h)

    log('  Gimmick %-9s @%x  bei (%.2f, %.2f, %.2f) yaw %.0f'
        % (parts, loc.addr, at[0], at[1], at[2], yaw))
    log('  an Gruppe @%x, jetzt %d Kinder, dataList %d Eintraege'
        % (root.addr, kids.count, dl.count))

    start.replace(START_FOX2, dst.build())
    out = {archive.index_of(START_FPKD): foxfast.encrypt(start.build())}
    extra = _register_extra(archive, parts)
    if extra:
        log('  %s zusaetzlich in ShGimmickSetUp.lua registriert' % parts)
        out.update(extra)
    return out


def _name_of(doc, ent):
    p = ent.get('name', doc.names())
    if p is None:
        return ''
    return p.name and str(p.value(0)) or ''


def _text(doc, ent, prop):
    """Textwert einer String-Eigenschaft, ueber die Stringtabelle aufgeloest."""
    import struct
    p = ent.get(prop)
    if not p or not p.count:
        return ''
    return doc.strings.get(struct.unpack('<Q', p.value())[0], '')


def _addr(ent, prop):
    import struct
    p = ent.get(prop)
    if p is None:
        return 0
    return struct.unpack('<Q', p.value(0))[0] if isinstance(p.value(0), bytes) \
        else p.value(0)


if __name__ == '__main__':
    import psarc
    a = sys.argv[1:]
    parts = a[a.index('--parts') + 1] if '--parts' in a else 'Ocho'
    at = tuple(float(x) for x in a[a.index('--at') + 1].split(',')) \
        if '--at' in a else AT
    import ptpaths             # zentrale Pfade, siehe ptpaths.py
    arc = psarc.Psarc(ptpaths.ORIG)
    overrides(arc, parts, at)
    print('  (Trockenlauf -- schreiben uebernimmt luaprobe.py)')
