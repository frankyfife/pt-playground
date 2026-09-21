"""Was steht gerade im gebauten Archiv? -- Ist-Zustand statt Erinnerung.

Warum
-----
Die App zeigte bisher die Werte, mit denen SIE gestartet wurde, nicht die, die
tatsaechlich im Spiel landen. Wer zwischendurch von Hand baut -- oder wem jemand
anders dazwischenbaut -- sieht dann etwas anderes, als er bekommt. Genau das ist
am 18.08.2026 passiert: mehrere Testbauten ohne --gimmick haben ein gespawntes
Objekt still ueberschrieben, und in der GUI stand weiter der alte Eintrag.

Deshalb wird hier alles aus `chunk1.psarc` selbst gelesen. Die Datei ist die
Wahrheit; eine ini koennte immer daneben liegen.

    import ptstate
    ptstate.read()      -> dict mit stage, speed, lumen, light_on, gimmick, at

Alles einzeln abgesichert: fehlt ein Wert oder ist das Archiv unerwartet
aufgebaut, steht dort None statt einer Ausrede.
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths


def _lua_tail(a):
    """Der von luaprobe angehaengte Teil von silent/start.lua, entschluesselt."""
    import foxlua
    raw = a.read(a.index_of('/silent/start.lua'))
    return raw if b'LIGHT_LUMEN' in raw else foxlua.decrypt(raw)


def _stage_from(tail):
    """SWAP_ON / ROAD_FPK zurueck auf einen Stage-Schluessel abbilden."""
    import luaprobe
    if re.search(rb'local SWAP_ON\s*=\s*false', tail):
        return 'vanilla'
    m = re.search(rb'local ROAD_FPK\s*=\s*"([^"]*)"', tail)
    if not m:
        return None
    path = m.group(1).decode('utf8', 'replace')
    for key, (p, _conn, _road) in luaprobe.STAGES.items():
        if p and luaprobe.FPK_ROOT % p == path:
            return key
    return None


def _speed_from(a):
    """Faktor aus dem ERSTEN moveSpeedRate, gegen das Original gerechnet.

    luaprobe multipliziert alle acht Werte mit demselben Faktor, einer genuegt
    also. Gegen chunk1.orig.psarc statt gegen eine gemerkte Zahl -- so stimmt
    es auch nach einem Bau von Hand.
    """
    import foxlua, psarc, luaprobe

    def first(arc):
        src = foxlua.decrypt(arc.read(arc.index_of(luaprobe.PARAMS)))
        i = src.find(b'moveSpeedRate')
        if i < 0:
            return None
        m = re.search(rb'[-+]?\d+\.\d+', src[i:i + 400])
        return float(m.group()) if m else None

    cur = first(a)
    if cur is None or not os.path.exists(ptpaths.ORIG):
        return None
    base = first(psarc.Psarc(ptpaths.ORIG))
    if not base:
        return None
    return round(cur / base, 2)


def _gimmick_from(a):
    """Das von uns gespawnte Objekt -- oder (None, None), wenn keins drin ist.

    Erkannt wird es durch VERGLEICH mit chunk1.orig.psarc: der Startraum bringt
    von Haus aus genau ein Gimmick mit (die Papiertuete auf dem Tisch). Ist im
    gebauten Archiv eines mehr, ist das unseres -- spawn.py haengt es hinten an.

    Nicht ueber den Namen: `spawn._name_of` liefert den HASH, nicht den Text,
    ein Namensvergleich greift also nie. Und nicht ueber die Position: ein
    Spawn genau auf dem Tisch saehe sonst aus wie die mitgelieferte Tuete.
    """
    import fox2build, foxfast, foxfpk, psarc
    import spawn as sp

    def gimmicks(arc):
        fp = foxfpk.Fpk(foxfast.decrypt(arc.read(arc.index_of(sp.START_FPKD))))
        doc = fox2build.Doc.load(fp.get(sp.START_FOX2))
        out = []
        for e in doc.of_class('GameObjectLocator'):
            if sp._text(doc, e, 'typeName') != 'ShGimmick':
                continue
            par = doc.by_addr(sp._addr(e, 'parameters'))
            tf = doc.by_addr(sp._addr(e, 'transform'))
            at = struct.unpack('<4f', tf.require('transform_translation').value(0))[:3]                 if tf is not None else None
            out.append((sp._text(doc, par, 'partsType') if par is not None else None, at))
        return out

    cur = gimmicks(a)
    if not os.path.exists(ptpaths.ORIG):
        return (None, None)
    base = len(gimmicks(psarc.Psarc(ptpaths.ORIG)))
    if len(cur) <= base:
        return (None, None)
    return cur[-1]                 # das zuletzt angehaengte ist unseres


# Was sich am Licht bauen laesst, mit den Vorgaben des SPIELS aus
# ShParameterTables.lua. Die Vorgabe steht hier und nicht in der Oberflaeche:
# sie ist eine Eigenschaft des Spiels, und zwei Fassungen derselben Zahl
# laufen frueher oder spaeter auseinander.
LIGHT_FIELDS = (('outerRange', 5.0), ('umbraAngle', 78.0),
                ('penumbraAngle', 30.0))


def _light_from(a):
    """Reichweite und Kegel aus ShParameterTables.lua im gebauten Archiv.

    Gelesen wird der handyLightParameter-Block, nicht die ganze Datei:
    `umbraAngle` kaeme sonst auch in `shadowUmbraAngle` vor und die
    Zuordnung waere Zufall.
    """
    import foxlua, psarc, luaprobe
    src = foxlua.decrypt(a.read(a.index_of(luaprobe.PARAMS)))
    x, y = luaprobe._block_span(src, 'handyLightParameter')
    block = src[x:y]
    out = {}
    for name, _vorgabe in LIGHT_FIELDS:
        m = re.search((r'\b%s\s*=\s*(-?[0-9]*\.?[0-9]+)' % name).encode(),
                      block)
        out[name] = float(m.group(1)) if m else None
    return out


def read():
    """Ist-Zustand des gebauten Archivs. Fehlendes wird None, nichts wirft."""
    out = {'stage': None, 'speed': None, 'lumen': None, 'light_on': None,
           'gimmick': None, 'at': None, 'built': None, 'error': None,
           'floor': None, 'win': None, 'lighton': None, 'light': None}
    try:
        import psarc
        if not os.path.exists(ptpaths.PSARC):
            out['error'] = 'chunk1.psarc not found'
            return out
        out['built'] = os.path.getmtime(ptpaths.PSARC)
        a = psarc.Psarc(ptpaths.PSARC)

        try:
            tail = _lua_tail(a)
            out['stage'] = _stage_from(tail)
            m = re.search(rb'local LIGHT_LUMEN\s*=\s*([0-9.]+)', tail)
            if m:
                out['lumen'] = float(m.group(1))
            m = re.search(rb'local LIGHT_ON\s*=\s*(true|false)', tail)
            if m:
                out['light_on'] = m.group(1) == b'true'
            # Floor und Ending-Falle: beides steht als Konstante in der
            # Sonde. Gesucht wird IMMER nach `local <NAME>` -- ein blosses
            # `FLOOR_ON =` trifft sonst den Kommentar daneben und meldet
            # den falschen Zustand.
            m = re.search(rb'local FLOOR_ON\s*=\s*(true|false)', tail)
            on = bool(m) and m.group(1) == b'true'
            m = re.search(rb'local FLOOR_NAME\s*=\s*"([^"]*)"', tail)
            if on and m:
                out['floor'] = m.group(1).decode('ascii', 'replace')
            m = re.search(rb'local WIN_ON\s*=\s*(true|false)', tail)
            if m:
                out['win'] = m.group(1) == b'true'
            m = re.search(rb'local LIGHT_ALWAYS\s*=\s*(true|false)', tail)
            if m:
                out['lighton'] = m.group(1) == b'true'
        except Exception as e:
            out['error'] = 'lua: %s' % e

        try:
            out['light'] = _light_from(a)
        except Exception as e:
            out['error'] = (out['error'] or '') + ' light: %s' % e

        try:
            out['speed'] = _speed_from(a)
        except Exception as e:
            out['error'] = (out['error'] or '') + ' speed: %s' % e

        try:
            out['gimmick'], out['at'] = _gimmick_from(a)
        except Exception as e:
            out['error'] = (out['error'] or '') + ' gimmick: %s' % e
    except Exception as e:
        out['error'] = str(e)
    return out


if __name__ == '__main__':
    import time
    st = read()
    print('  Ist-Zustand von chunk1.psarc')
    print('    gebaut    : %s' % (time.strftime('%d.%m. %H:%M',
                                                time.localtime(st['built']))
                                  if st['built'] else '-'))
    print('    Stage     : %s' % st['stage'])
    print('    Tempo     : %s' % (('x%.1f' % st['speed']) if st['speed'] else '-'))
    print('    Lampe     : %s' % ('aus' if st['light_on'] is False
                                  else ('%.0f lm' % st['lumen']) if st['lumen']
                                  else '-'))
    print('    Spawn     : %s%s' % (st['gimmick'] or 'keiner',
                                    ('  bei (%.2f, %.2f, %.2f)' % st['at'])
                                    if st['at'] else ''))
    if st['error']:
        print('    Hinweis   : %s' % st['error'])
