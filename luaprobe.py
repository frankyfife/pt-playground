"""Instrument P.T.'s Lua bindings from start.lua and read the result in the log.

Why this and not another data edit
----------------------------------
Every data change so far cost a playthrough and returned one bit. Three of them
returned "nothing happened", which does not even say which link in the chain
broke. This gives observability instead: it wraps the stage and game-control
bindings at boot and beacons every call, so one playthrough produces a trace of
what the game actually does -- which floor it thinks it is on, whether the door
trap calls LoadStage, whether GotoEnding is ever reached.

Why it can work when gshook.py cannot
-------------------------------------
gshook replaces gameState.lua, and the shipped one is compiled Fox-Lua that
cannot be chain-loaded, so the state machine dies after OnLoadStart. start.lua
is different: it is plain source under one LCG layer, it runs, and the beacon
proves it. Its only limitation was that the bindings no-op at boot because the
singleton is still null -- but the binding *tables* are already there (start.lua
calls ShGameMainControl.IsGuiEditor() itself), so replacing their entries with
wrappers at boot makes them fire later, during play.

Reading the trace
-----------------
    grep -o 'PTDBG/[A-Za-z0-9_.-]*' shad_log.txt | sort -u

    OWNER.<table>.<fn>   which global table really owns a binding
    WRAPPED.<table>.N    how many wrappers took
    CALL.<fn>.<args>     an actual call, with its arguments

    python luaprobe.py                          # build it
    python luaprobe.py --roadstage              # Türtausch + Taschenlampe
    python luaprobe.py --roadstage --lumen 400  # heller (Vorgabe 100)
    python luaprobe.py --roadstage --nolight    # ohne Lampe
    python luaprobe.py --roadstage --floor-ending   # Floorwechsel-Versuch
    python luaprobe.py --roadstage --speed 2.0  # doppelte Laufgeschwindigkeit
    python luaprobe.py --stage maze_a           # Irrgarten A hinter die Tür
    python luaprobe.py --stage vanilla          # Tür wieder unangetastet
    python luaprobe.py --gimmick Ocho           # Lisa in den Startraum
    python luaprobe.py --gimmick Baby --gimmick-at 0,0,-8
    python luaprobe.py --restore                # back to the untouched original

shadPS4 must be closed: it holds chunk1.psarc open while a game is loaded.
"""
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psarc, foxlua

import ptpaths                 # zentrale Pfade, siehe ptpaths.py
GAME = ptpaths.GAME
ORIG = os.path.join(GAME, "chunk1.orig.psarc")
LIVE = os.path.join(GAME, "chunk1.psarc")
HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "mod", "probe_start.lua")

START = "silent/start.lua"


def check_free():
    """shadPS4 keeps chunk1.psarc open while a game is loaded, and the rename at
    the end then dies with a WinError 32 traceback -- after the build has already
    done all its work. Fail early and say what to do instead."""
    if not os.path.exists(LIVE):
        return
    try:
        os.rename(LIVE, LIVE)          # no-op that still needs exclusive access
    except OSError:
        sys.exit("chunk1.psarc is locked -- close shadPS4 (and its launcher) "
                 "and run this again. Nothing was written.")


PARAMS = "/as/sh/level_asset/chara/parameter/ShParameterTables.lua"

# Was sich hinter die Startraumtuer haengen laesst. Die Connector-Schluessel
# sind aus den fox2 der Stages ausgelesen (Entity "Connector_<schluessel>"),
# nicht geraten -- maze_A/B heissen anders als der Rest.
#
# Nur `ending` braucht die Operation aus roadstage.py: es ist als einzige Stage
# OHNE ShRelativeStageLocator gebaut und kann ohne den gar nicht angehaengt
# werden. Die Flure bringen ihren mit.
STAGES = {
    'vanilla':  (None, None, False),
    'hallway':  ('hallway/pt14_hallway',            'startDoor', False),
    'maze_a':   ('hallway_maze_A/pt14_hallway_maze_A', 'Start',   False),
    'maze_b':   ('hallway_maze_B/pt14_hallway_maze_B', 'Start',   False),
    'maze_c':   ('hallway_maze_C/pt14_hallway_maze_C', 'startDoor', False),
    'strasse':  ('ending/ending',                   'road',      True),
}
FPK_ROOT = "/Assets/sh/level/promotion/pt_2014/%s.fpk"


def tune_win(tail, on):
    """WIN_ON in der Sonde setzen -- loest am Tuerhaken das Outro aus.

    Der Weg ist ShGameMainControl.GoToLocation(0); die Null steht als
    `clear = 0` in Konamis eigenem sh_game_debug.lua. Siehe Phase 5 der Sonde.
    """
    import re as _re
    if not on:
        return tail
    tail, n = _re.subn(rb'(local WIN_ON\s*=\s*)false', rb'\g<1>true', tail)
    if n != 1:
        sys.exit("WIN_ON nicht genau einmal in der Sonde gefunden -- nichts gebaut.")
    print("  Ende: ChangeGameStep -> SetFloorLevel(ending) -> GotoEnding,"
          " am Tuerhaken")
    return tail


def tune_stage(tail, stage):
    """SWAP_ON / ROAD_FPK / ROAD_CONNECTOR in der Sonde setzen."""
    if stage not in STAGES:
        sys.exit("unbekannte Stage %r -- moeglich: %s"
                 % (stage, ', '.join(sorted(STAGES))))
    path, conn, _ = STAGES[stage]
    if path is None:
        tail, n = re.subn(rb'(local SWAP_ON\s*=\s*)true', rb'\g<1>false', tail)
        if n != 1:
            sys.exit("SWAP_ON nicht genau einmal gefunden -- nichts gebaut.")
        print("  Stage: vanilla -- die Tuer bleibt unangetastet")
        return tail
    for name, val in (('ROAD_FPK', FPK_ROOT % path), ('ROAD_CONNECTOR', conn)):
        pat = (r'(local %s\s*=\s*)"[^"]*"' % name).encode()
        tail, n = re.subn(pat, (r'\g<1>"%s"' % val).encode(), tail)
        if n != 1:
            sys.exit("%s nicht genau einmal gefunden -- nichts gebaut." % name)
    print("  Stage: %s -> %s  (Connector %r)" % (stage, FPK_ROOT % path, conn))
    return tail


def _block_span(src, key):
    """(anfang, ende) der geschweiften Klammer hinter `key`.

    Ausgeschnitten wird, damit eine Ersetzung NUR dort greift: ein globales
    Zahlen-Ersetzen wuerde auch focalLength und die Lampe erwischen.
    """
    if key.encode() not in src:
        sys.exit("%s nicht in %s gefunden -- nichts gebaut." % (key, PARAMS))
    start = src.index(key.encode())
    open_brace = src.index(b'{', start)
    depth = 0
    for j in range(open_brace, len(src)):
        c = src[j:j + 1]
        if c == b'{':
            depth += 1
        elif c == b'}':
            depth -= 1
            if depth == 0:
                return open_brace, j + 1
    sys.exit("Klammern von %s nicht ausgewogen -- nichts gebaut." % key)


def _speed_in(src, factor):
    """moveSpeedRate mit `factor` multiplizieren. Gibt den neuen Quelltext."""
    a, b = _block_span(src, 'moveSpeedRate')
    n = [0]

    def scale(m):
        n[0] += 1
        return b'%s%.4f' % (m.group(1), float(m.group(2)) * factor)

    new = re.sub(rb'((?:min|max)\s*=\s*)([0-9]*\.?[0-9]+)', scale, src[a:b])
    if n[0] != 8:
        sys.exit("moveSpeedRate: %d statt 8 Werte getroffen -- nichts gebaut."
                 % n[0])
    print("  Laufgeschwindigkeit: %.2f-fach (8 Werte)" % factor)
    return src[:a] + new + src[b:]


# Was sich an der Taschenlampe stellen laesst. Die Namen stammen aus
# handyLightParameter in ShParameterTables.lua, nicht aus einer Vermutung:
#
#     innerRange = 0.005      outerRange = 5
#     color = { r=1.0, g=1.0, b=1.0 }
#     temperature = 5000.0    colorDeflection = 0.0
#     lumen = 100.0           lightSize = 0.05
#     umbraAngle = 78.0       penumbraAngle = 30.0
#     attenuationExponent = 1.2
#     dimmer = 0.1            powerScale = 1.0
#
# `lumen` fehlt hier mit Absicht: das setzt die Sonde je Bild per
# SendCommand("SetHandyLight"), ein Tabellenwert daneben waere nur verwirrend.
LIGHT_KEYS = ('innerRange', 'outerRange', 'temperature', 'colorDeflection',
              'lightSize', 'umbraAngle', 'penumbraAngle',
              'attenuationExponent', 'dimmer', 'powerScale')


def _light_in(src, values):
    """handyLightParameter setzen. `values`: {schluessel: zahl}, dazu die
    Sonderfaelle 'r', 'g', 'b' fuer die Farbe.

    Jeder Schluessel MUSS genau einmal getroffen werden. Wird er es nicht,
    bricht der Bau ab, statt still das Alte zu behalten -- ein Regler, der
    scheinbar wirkt und nichts tut, kostet mehr Zeit als ein Abbruch.
    """
    a, b = _block_span(src, 'handyLightParameter')
    block = src[a:b]

    # Farbe zuerst: sie liegt in einem eigenen Unterblock, und ein r= dort
    # darf nicht mit einem r= ausserhalb verwechselt werden.
    rgb = {k: values[k] for k in ('r', 'g', 'b') if k in values}
    if rgb:
        ca, cb = _block_span(block, 'color')
        cblock = block[ca:cb]
        for k, v in rgb.items():
            pat = (r'(\b%s\s*=\s*)([0-9]*\.?[0-9]+)' % k).encode()
            cblock, n = re.subn(pat, (r'\g<1>%.4f' % v).encode(), cblock)
            if n != 1:
                sys.exit("color.%s nicht genau einmal getroffen (%d) --"
                         " nichts gebaut." % (k, n))
        block = block[:ca] + cblock + block[cb:]
        print("  Taschenlampe Farbe: r=%.2f g=%.2f b=%.2f"
              % (values.get('r', 1.0), values.get('g', 1.0),
                 values.get('b', 1.0)))

    for k in LIGHT_KEYS:
        if k not in values:
            continue
        pat = (r'(\b%s\s*=\s*)([0-9]*\.?[0-9]+)' % k).encode()
        block, n = re.subn(pat, (r'\g<1>%.4f' % values[k]).encode(), block)
        if n != 1:
            sys.exit("handyLightParameter.%s nicht genau einmal getroffen"
                     " (%d) -- nichts gebaut." % (k, n))
        print("  Taschenlampe %-20s %.4f" % (k, values[k]))
    return src[:a] + block + src[b:]


# Was sich an der Belichtung stellen laesst. Die Namen stammen aus
# lightingParameter in ShParameterTables.lua, je Floor einmal:
#
#     minExposure = -10.0     maxExposure = 1
#     exposureCompensation = 0.0     keyValue = 1.0
#     addExpComp0/1/2 = -4.8 / -3.8 / -2.4
#     addExpComp_Ev0/1/2 = 0.0 / -3.0 / -5.0
#     bloomWeight = 0.9|1.2   bloomBrightnessExtraction = 3.0
#     bloomSize = 2.0         shutterSpeed = 0.035
EXPO_KEYS = ('minExposure', 'maxExposure', 'exposureCompensation',
             'keyValue', 'addExpComp0', 'addExpComp1', 'addExpComp2',
             'addExpComp_Ev0', 'addExpComp_Ev1', 'addExpComp_Ev2',
             'bloomWeight', 'bloomBrightnessExtraction', 'bloomSize',
             'shutterSpeed')
EXPO_FLOORS = 15          # so viele Untertabellen hat lightingParameter


def _expo_in(src, values):
    """lightingParameter auf ALLEN Floors setzen. `values`: {name: zahl}.

    Auf allen, weil nicht bestimmt ist, welcher Floor gerade gilt -- und weil
    eine Analysehilfe ohnehin ueberall greifen soll.

    Das Zahlenmuster traegt hier `-?`: `minExposure = -10.0` ist negativ, und
    ohne Vorzeichen im Muster wuerde die Ersetzung `-10.0` zu `-8.0` statt zu
    `8.0` machen -- also das Vorzeichen stehen lassen und die Zahl tauschen.
    Das waere ein stiller Vorzeichenfehler, und genau den soll das Muster
    ausschliessen.
    """
    a, b = _block_span(src, 'lightingParameter')
    block = src[a:b]
    for k in EXPO_KEYS:
        if k not in values:
            continue
        pat = (r'(\b%s\s*=\s*)(-?[0-9]*\.?[0-9]+)' % k).encode()
        block, n = re.subn(pat, (r'\g<1>%.4f' % values[k]).encode(), block)
        if n != EXPO_FLOORS:
            sys.exit("lightingParameter.%s %d-mal statt %d getroffen --"
                     " nichts gebaut." % (k, n, EXPO_FLOORS))
        print("  Belichtung %-28s %.4f  (%d Floors)" % (k, values[k], n))
    return src[:a] + block + src[b:]


def tune_params(archive, speed=None, light=None, expo=None):
    """Beide Eingriffe in ShParameterTables.lua -- in EINEM Durchgang.

    Getrennt ginge es nicht: beide lesen dieselbe Datei aus dem Archiv, und
    der zweite Override wuerde den ersten schlicht ueberschreiben. Also
    nacheinander auf demselben Quelltext arbeiten und einmal zurueckschreiben.

    Die Datei ist LCG-verschluesselt, aber Klartext-Lua darunter -- und der
    Loader nimmt Klartext an (kein Magic => keine Entschluesselung), genau wie
    bei start.lua.
    """
    i = archive.index_of(PARAMS)
    src = foxlua.decrypt(archive.read(i))
    if speed is not None:
        src = _speed_in(src, speed)
    if light:
        src = _light_in(src, light)
    if expo:
        src = _expo_in(src, expo)
    return {i: src}


def movespeed(archive, factor):
    """Nur die Laufgeschwindigkeit -- duenner Aufruf von tune_params."""
    return tune_params(archive, speed=factor)


FLOORS = ('f005', 'f020', 'f030', 'f040', 'f050', 'f060', 'f070', 'f080',
          'f100', 'f120', 'f160', 'ending')


def tune_floor(tail, on=False, name=None):
    """FLOOR_ON in der Sonde einschalten.

    Steht in der Sonde auf false, weil der Floorwechsel am 17.08.2026 die
    Startraumtür unbrauchbar gemacht hat (RelocateGimmicks versetzt sie mit).
    Nur auf ausdrücklichen Wunsch einschalten -- und dann wissen, dass der
    Lauf schiefgehen kann.
    """
    if not on:
        return tail
    tail, n = re.subn(rb'(local FLOOR_ON\s*=\s*)false', rb'\g<1>true', tail)
    if n != 1:
        sys.exit("FLOOR_ON nicht genau einmal in der Sonde gefunden "
                 "(%d Treffer) -- nichts gebaut." % n)
    if name:
        if name not in FLOORS:
            sys.exit("unbekannte Etage %r -- moeglich: %s"
                     % (name, ", ".join(FLOORS)))
        tail, n = re.subn(rb'(local FLOOR_NAME\s*=\s*)"[^"]*"',
                          (r'\g<1>"%s"' % name).encode(), tail)
        if n != 1:
            sys.exit("FLOOR_NAME nicht genau einmal gefunden -- nichts gebaut.")
    print("  Floorwechsel: AN, Ziel %s (Versuch -- kann die Tuer versetzen)"
          % (name or "ending"))
    return tail


def tune_light(tail, lumen=None, off=False, rgb=None, always=False):
    """LIGHT_LUMEN / LIGHT_ON in der Sonde setzen, ohne die Datei anzufassen.

    Die Helligkeit will man ausprobieren, und jedes Ausprobieren kostet einen
    Durchlauf -- deshalb hier ein Schalter statt eines Handedits. Trifft das
    Muster nicht mehr (weil jemand die Konstante umbenannt hat), wird
    ABGEBROCHEN und nicht still das Alte gebaut: ein stumm falsch gebauter
    Stand kostet mehr als ein Abbruch.
    """
    if lumen is not None:
        tail, n = re.subn(rb'(local LIGHT_LUMEN\s*=\s*)[0-9.]+',
                          rb'\g<1>%s' % ('%.1f' % lumen).encode(), tail)
        if n != 1:
            sys.exit("LIGHT_LUMEN nicht genau einmal in der Sonde gefunden "
                     "(%d Treffer) -- nichts gebaut." % n)
        print("  Taschenlampe: %.1f Lumen" % lumen)
    if rgb:
        # Die Farbe geht ZUSAETZLICH in die Sonde. Der Tabellenwert wirkt
        # nachweislich nur im Startraum -- im Flur wird die Lampe neu
        # gesetzt, ohne dass der Parameterblock angefasst wird. Ob
        # SetHandyLight ein Farbfeld annimmt, muss der Bau zeigen.
        for name, key in (('LIGHT_R', 'r'), ('LIGHT_G', 'g'),
                          ('LIGHT_B', 'b')):
            if key not in rgb:
                continue
            pat = (r'(local %s\s*=\s*)[0-9.]+' % name).encode()
            tail, n = re.subn(pat,
                              (r'\g<1>%.4f' % rgb[key]).encode(), tail)
            if n != 1:
                sys.exit("%s nicht genau einmal in der Sonde gefunden (%d)"
                         " -- nichts gebaut." % (name, n))
        print("  Taschenlampe (Sonde): r=%.2f g=%.2f b=%.2f"
              % (rgb.get('r', 1.0), rgb.get('g', 1.0), rgb.get('b', 1.0)))

    if always:
        # Die Sonde schaltet die Taschenlampe per SendCommand ein. Ohne
        # das hat ein FRISCHER Spielstand gar keine Lampe -- vom Nutzer
        # am 19.08. gemeldet. LIGHT_ALWAYS sorgt dafuer, dass sie das
        # auch ohne Tuertausch tut (sonst laeuft der Lampencode nie).
        tail, n = re.subn(rb"(local LIGHT_ALWAYS\s*=\s*)false",
                          rb"\g<1>true", tail)
        if n != 1:
            sys.exit("LIGHT_ALWAYS nicht genau einmal in der Sonde"
                     " gefunden (%d) -- nichts gebaut." % n)
        print("  Taschenlampe: wird eingeschaltet")

    if off:
        tail, n = re.subn(rb'(local LIGHT_ON\s*=\s*)true', rb'\g<1>false', tail)
        if n != 1:
            sys.exit("LIGHT_ON nicht genau einmal in der Sonde gefunden "
                     "(%d Treffer) -- nichts gebaut." % n)
        print("  Taschenlampe: aus")
    return tail


def _mirror_arg(a):
    """--mirror              alle Basisfarben des Bades
    --mirror name,name2   nur diese
    --mirror-red          einfaerben statt durchsichtig machen (Diagnose)"""
    global MIRROR_RED
    if '--mirror' not in a:
        return False
    MIRROR_RED = '--mirror-red' in a
    j = a.index('--mirror') + 1
    if j < len(a) and not a[j].startswith('--'):
        return [x.strip() for x in a[j].split(',') if x.strip()]
    return True



MIRROR_RED = False        # Diagnosemodus: einfaerben statt loeschen


def _light_arg(a):
    """--light r=1,g=0.2,b=0.2,outerRange=15

    Ein Schalter fuer alle Kennwerte statt zehn einzelner: die Namen stehen
    ohnehin so in ShParameterTables.lua, und ein Tippfehler faellt beim Bauen
    sofort auf (der Schluessel wird dann nicht genau einmal getroffen und der
    Bau bricht ab).
    """
    if '--light' not in a:
        return None
    out = {}
    for part in a[a.index('--light') + 1].split(','):
        part = part.strip()
        if not part:
            continue
        if '=' not in part:
            sys.exit('  --light erwartet schluessel=wert, bekam %r' % part)
        k, v = part.split('=', 1)
        k = k.strip()
        if k not in LIGHT_KEYS + ('r', 'g', 'b'):
            sys.exit('  unbekannter Lichtwert %r -- moeglich: %s'
                     % (k, ', '.join(('r', 'g', 'b') + LIGHT_KEYS)))
        try:
            out[k] = float(v)
        except ValueError:
            sys.exit('  %s=%r ist keine Zahl' % (k, v))
    return out or None



def _expo_arg(a):
    """--exposure maxExposure=16,exposureCompensation=4

    Ein Schalter fuer alle Kennwerte, wie bei --light: die Namen stehen so in
    ShParameterTables.lua, und ein Tippfehler bricht den Bau ab, statt still
    nichts zu tun.
    """
    if '--exposure' not in a:
        return None
    out = {}
    for part in a[a.index('--exposure') + 1].split(','):
        part = part.strip()
        if not part:
            continue
        if '=' not in part:
            sys.exit('  --exposure erwartet schluessel=wert, bekam %r' % part)
        k, v = part.split('=', 1)
        k = k.strip()
        if k not in EXPO_KEYS:
            sys.exit('  unbekannter Belichtungswert %r -- moeglich: %s'
                     % (k, ', '.join(EXPO_KEYS)))
        try:
            out[k] = float(v)
        except ValueError:
            sys.exit('  %s=%r ist keine Zahl' % (k, v))
    return out or None


def _show_arg(a):
    """--show a,b  schaltet EIN, --hide a,b schaltet AUS. Beides zusammen ist
    erlaubt; wer denselben Namen doppelt nennt, bekommt den letzten Wert."""
    out = {}
    for flag, val in (('--show', True), ('--hide', False)):
        if flag in a:
            for n in a[a.index(flag) + 1].split(','):
                n = n.strip()
                if n:
                    out[n] = val
    return out or None



def build(spawn=False, roadstage=False, lumen=None, nolight=False, floor=False,
          speed=None, stage=None, gimmick=None, gimmick_at=None, winclear=False,
          floorname=None, show=None, light=None, mirror=False, lighton=False,
          expo=None):
    if not os.path.exists(ORIG):
        sys.exit("missing %s -- keep the untouched original there" % ORIG)
    check_free()
    a = psarc.Psarc(ORIG)
    i = a.index_of(START)
    # start.lua ships encrypted. Decrypt before appending, or the loader sees
    # the magic, decrypts the whole file, and turns our plaintext tail into
    # garbage -- start.lua then dies on a syntax error and nothing runs.
    base = foxlua.decrypt(a.read(i))
    if base[:2] == b'\x1b\x4c':
        sys.exit("start.lua came out compiled, not source -- aborting")
    tail = tune_light(open(PROBE, "rb").read(), lumen=lumen, off=nolight,
                       rgb=light,
                       always=lighton)
    tail = tune_floor(tail, on=floor or bool(floorname), name=floorname)
    # Phase 5 der Sonde: ChangeGameStep -> SetFloorLevel("ending") -> GotoEnding.
    # Die Reihenfolge stammt aus einem Lauf, der schon einmal sauber durchlief.
    tail = tune_win(tail, winclear)
    if stage:
        tail = tune_stage(tail, stage)
        # Nur die Strasse braucht die Aufbereitung aus roadstage.py.
        roadstage = roadstage or STAGES[stage][2]
    lua = base + b"\n\n" + tail
    print("  start.lua: %d + %d = %d bytes" % (len(base), len(tail), len(lua)))

    ov = {i: lua}
    if speed is not None or light or expo:
        ov.update(tune_params(a, speed=speed, light=light, expo=expo))
    if winclear:
        # Zusaetzlich P.T.s eigene Falle auf allen Etagen scharf schalten.
        # ALLEIN wirkt sie nicht (im Spiel geprueft: 11 von 11 Etagen scharf,
        # trotzdem passierte nichts) -- sie schadet aber auch nicht und deckt
        # den Fall ab, dass jemand regulaer bis zum Flur durchspielt.
        import gotoending
        ov.update(gotoending.overrides(a))
    if gimmick:
        # Ein Gimmick in den Startraum setzen (GameObjectLocator +
        # ShGimmickLocatorParameter). Siehe spawn.py.
        import spawn as spawnmod
        ov.update(spawnmod.overrides(a, gimmick,
                                     gimmick_at or spawnmod.AT))
    if spawn:
        import endingspawn
        ov.update(endingspawn.overrides(a))
    if roadstage:
        import roadstage as rs
        ov.update(rs.overrides(a, donor="--donor" in sys.argv[1:],
                               merge="--merge" in sys.argv[1:],
                               floor="--floor" in sys.argv[1:],
                               strip_player="--noplayer" in sys.argv[1:]))

    if show:
        # Versteckte Objekte an ihrem eigenen Platz einschalten (flags Bit 0).
        # Kein Spawn: die Dinge stehen laengst dort, wo die Entwickler sie
        # hingestellt haben -- Ocho neben der Wanne, das Blut an seiner Wand.
        import ptobjects
        ov.update(ptobjects.overrides(a, show))

    if mirror:
        # Die Verdeckung vor dem Badezimmerspiegel durchsichtig machen.
        #
        # GEMESSEN am 19.08.: `shsb_bath001_dc_bsm_alp` liegt in ZWEI
        # Fassungen vor -- 2048x2048/BC3 im chunk1 und 256x256/BC1 in
        # resident.pftxs. Gelesen wird die zweite; die chunk1-Fassung blieb
        # selbst knallrot eingefaerbt im Spiel unsichtbar.
        import pftxpatch
        ov.update(pftxpatch.overrides(
            a, colour=(pftxpatch.texpatch.RED if MIRROR_RED else None),
            clear_alpha=not MIRROR_RED))

    tmp = os.path.join(GAME, "chunk1.__new.psarc")
    psarc.build(a, tmp, ov)
    del a
    if os.path.exists(LIVE):
        os.remove(LIVE)
    os.rename(tmp, LIVE)
    print("  wrote %s (%d bytes)" % (LIVE, os.path.getsize(LIVE)))


def verify():
    a = psarc.Psarc(LIVE)
    b = psarc.Psarc(ORIG)
    blob = a.read(a.index_of(START))
    # Marker, die Umbauten an der Sonde ueberleben. "GotoEnding" stand hier
    # frueher mit drin und schlug Fehlalarm, sobald eine Runde das Binding
    # nicht mehr umwickelt -- der Beacon-Pfad ist das einzig Verlaessliche.
    ok = b"/app0/PTDBG/" in blob
    print("  probe present in the built archive: %s" % ok)
    tail = blob[len(foxlua.decrypt(b.read(b.index_of(START)))):]
    for line in tail.split(b'\n'):
        if (b'bcn("R2' in line or b'FIRE_ON =' in line
                or b'LIGHT_ON ' in line or b'LIGHT_LUMEN ' in line):
            print("     %s" % line.strip().decode('utf8', 'replace'))
    changed = [nm for i, nm in enumerate(a.names) if a.read(i + 1) != b.read(i + 1)]
    print("  psarc entries changed: %d  %s" % (len(changed), changed))
    print("\n  after playing, read the trace with:")
    print("    grep -o 'PTDBG/[A-Za-z0-9_.-]*' %s | sort -u"
          % ptpaths.LOG)


if __name__ == "__main__":
    if "--restore" in sys.argv[1:]:
        if os.path.exists(LIVE):
            os.remove(LIVE)
        shutil.copy2(ORIG, LIVE)
        print("restored untouched original")
    else:
        a = sys.argv[1:]
        build(spawn="--spawn" in a, roadstage="--roadstage" in a,
              lumen=float(a[a.index("--lumen") + 1]) if "--lumen" in a else None,
              nolight="--nolight" in a, floor="--floor-ending" in a,
              winclear="--winclear" in a,
              floorname=a[a.index("--floor") + 1] if "--floor" in a else None,
              speed=float(a[a.index("--speed") + 1]) if "--speed" in a else None,
              stage=a[a.index("--stage") + 1] if "--stage" in a else None,
              gimmick=a[a.index("--gimmick") + 1] if "--gimmick" in a else None,
              gimmick_at=tuple(float(x) for x in a[a.index("--gimmick-at") + 1].split(","))
              if "--gimmick-at" in a else None,
              show=_show_arg(a),
              light=_light_arg(a),
              expo=_expo_arg(a),
              mirror=_mirror_arg(a),
              lighton="--lighton" in a)
        verify()
