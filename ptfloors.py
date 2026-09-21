"""Was passiert in welcher Schleife -- Ebenenuebersicht als xlsx.

Wozu
----
Die eigentliche Frage des Nutzers ist nicht "wie versetze ich Lisa", sondern:
**welche Ausloeser gibt es, damit moeglichst viel vom Spiel sichtbar und
nachstellbar wird.** Das steht vollstaendig in den `.fox2` -- es muss nur
lesbar gemacht werden.

Der Aufbau (siehe `ptlogic.py` fuer die Formate)
------------------------------------------------
    GeoTrap  --conditionArray-->  GeoModuleCondition  <--owner--  DataElements

Jede `GeoModuleCondition` traegt selbst, wann sie gilt und was sie tut:

    checkFuncNames    ShIsPlayer | ShIsInView | ShPlayerInputDirection ...
    execFuncNames     LuaScript | ShDemoExec | ExecNazo | ShDoor | ...
    floorName         die Schleife, in der sie gilt
    floorNameArray    mehrere Schleifen
    floorLevel        Nummer der Schleife
    orderFloor        Schleifenbindung ueberhaupt beachten
    isOnce            nur einmal
    setEnable         schaltet andere Traps ein
    targetData        was betroffen ist (Objekte, Traps, FX)

**Wichtig:** der Trap-NAME nennt den Ordner (`...|f040_demo|...`), die
Bedingung nennt die wirkliche Schleife -- und beide koennen abweichen. Im
Zweifel gilt `floorName` der Bedingung; der Ordner steht als Nebeninfo dabei.

Die Schleifen: f000 (Startraum) f005 f010 f020 f030 f040 f050 f060 f070 f080
f090 f100 f120 f160, dazu `ending`. Angesprungen werden sie mit
`GameFloorLevel.SetFloorLevel("fNNN")` -- im Playground der Reiter *Floors*.

    python ptfloors.py                 Uebersicht in der Konsole
    python ptfloors.py --xlsx          Tabelle schreiben (Vorgabe: Desktop)
    python ptfloors.py --xlsx <pfad>
    python ptfloors.py --floor f040    nur eine Schleife, ausfuehrlich
    python ptfloors.py --level maze_C
"""
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptlogic

# Reihenfolge, in der P.T. die Schleifen durchlaeuft -- **live aus der
# Namenstabelle bei VA 0x1c85590 gelesen** (13.09.2026), nicht alphabetisch
# geraten. Sie ist ueberraschend: f010 kommt VOR f005 und f060 vor f050.
# `SetFloorLevel` sucht in genau dieser Tabelle und setzt den Index,
# `AddFloorLevel`/`SubFloorLevel` zaehlen ihn hoch und runter -- die
# Tabellenreihenfolge IST also der Ablauf.
ORDER = ['f000', 'f010', 'f005', 'f020', 'f030', 'f040', 'f060', 'f050',
         'f070', 'f080', 'f090', 'f100', 'f110', 'f120', 'f160', 'ending']

# Was die Pruef- und Ausfuehrnamen bedeuten -- aus den Klassennamen der
# DataElements abgeleitet, die daran haengen.
CHECKS = {
    'ShIsPlayer': 'Spieler betritt das Volumen',
    'ShIsInView': 'Spieler schaut hin',
    'ShPlayerInputDirection': 'Spieler drueckt in eine Richtung',
    'ShTrapCheckIsPlayer': 'Spieler betritt das Volumen',
}
EXECS = {
    'LuaScript': 'Lua ausfuehren',
    'ShDemoExec': 'Inszenierung abspielen',
    'ExecNazo': 'Raetselschritt',
    'ShDoor': 'Tuer',
    'ShMirrorSwitch': 'Spiegel umschalten',
}


def floor_folder(name):
    """Die Ebene aus dem Trap-Namen -- nur Nebeninfo."""
    for part in name.split('|'):
        if part.endswith('_demo') and part not in ('pt14_hallway_demo',
                                                   'common_demo'):
            return part[:-5]
    if 'common_demo' in name:
        return 'common'
    if '_nazo' in name:
        return 'nazo'
    return ''


def floors_of(g, ent):
    """Alle Schleifen, fuer die eine Bedingung oder ein DemoScript gilt."""
    out = []
    for prop in ('floorName', 'floorNames', 'floorNameArray'):
        p = ent.get(prop)
        if not p:
            continue
        for v in g.val(p):
            if isinstance(v, str) and v and v not in out:
                out.append(v)
    return out


# Wo ein Ziel stehen kann. Nicht jede Regel benutzt `targetData` -- das
# Sichtbarmachen eines Objekts steht in `staticModel`, ein Tuerzustand in
# `door_*`, ein Ton in `soundId`. Ohne diese Liste bleibt die Zielspalte bei
# einem Drittel der Regeln leer.
TARGET_PROPS = ('targetData', 'staticModel', 'modelData', 'gameObjectName',
                'door_hallway_in', 'door_hallway_out', 'door_bathroom',
                'door_bathroom_20', 'door_bathroom_170', 'door_lobby',
                'door_lobby_open', 'lightData', 'lightID10', 'soundId',
                'subtitleMsgId', 'targetStageLabel', 'checkName')


def _flat(v):
    if isinstance(v, (list, tuple)):
        return ', '.join(str(x).split('|')[-1] for x in v if str(x))
    return str(v).split('|')[-1]


def targets(d):
    out = []
    for k in TARGET_PROPS:
        if k in d:
            t = _flat(d[k])
            if t and t not in out:
                out.append('%s' % t if k in ('targetData', 'staticModel',
                                             'modelData')
                           else '%s=%s' % (k, t))
    return ', '.join(out)


def effect(d, script=''):
    """Was die Regel bewirkt, in Worten.

    "unsichtbar" darf nur stehen, wenn die Regel wirklich Sichtbarkeit
    schaltet. Mehrere Lichtregeln fuehren einen `staticModel` mit (die Lampe),
    ohne ihn ein- oder auszublenden -- ohne diese Pruefung stand bei ihnen
    faelschlich "unsichtbar".
    """
    out = []
    vis = 'EnableStaticModel' in script
    if d.get('isVisible'):
        out.append('sichtbar')
    elif vis and ('staticModel' in d or 'modelData' in d):
        out.append('unsichtbar')
    if d.get('isGeomActive'):
        out.append('Geometrie an')
    if d.get('setEnable'):
        out.append('schaltet Traps ein')
    if d.get('enable_light') is not None and 'enable_light' in d:
        out.append('Licht %s' % ('an' if d['enable_light'] else 'aus'))
    if d.get('soundId'):
        out.append('Ton %s' % _flat(d['soundId']))
    if d.get('commandId'):
        out.append('Befehl %s' % _flat(d['commandId']))
    if d.get('demoId'):
        out.append('Demo %s' % _flat(d['demoId']))
    if d.get('loopCount'):
        out.append('ab Schleife %s' % d['loopCount'])
    return ', '.join(out)


def collect(g):
    """Eine Zeile je (Trap, Regel). Das ist die Grundtabelle."""
    rows = []
    lvl = getattr(g, 'level', 'hallway')
    for t in g.doc.of_class('GeoTrap'):
        tname = g.name(t)
        folder = floor_folder(tname)
        tf = t.get('transform')
        pos = ''
        if tf:
            e = g.by_addr.get(struct.unpack('<Q', tf.value(0)[:8])[0])
            p = e.get('transform_translation') if e is not None else None
            if p:
                x, y, z = struct.unpack('<3f', p.value(0)[:12])
                pos = '%.1f / %.1f / %.1f' % (x, y, z)
        for cname, cond in g.conditions_of(t):
            if cond is None:
                rows.append({'level': lvl,
                             'folder': folder, 'trap': tname.split('|')[-1],
                             'pos': pos, 'rule': cname,
                             'floors': [], 'check': '', 'exec': '',
                             'script': '', 'demo': '', 'target': '',
                             'effect': '', 'loop': '',
                             'once': '', 'note': 'Regel nicht aufloesbar'})
                continue
            d = dict(g.fields(cond))
            kids = g.children.get(cond.addr, ())
            script = demo = ''
            for k in kids:
                kd = dict(g.fields(k))
                if kd.get('scriptFile'):
                    script = os.path.basename(str(kd['scriptFile']))
                if kd.get('demoId'):
                    demo = str(kd['demoId'])
            # Die Schleifenangabe steht NICHT immer an der Regel. Bei den
            # Demo-Ausloesern sitzt sie am Kind-Element
            # (ShTrapExecRelativeStageDemoPlay... fuehrt floorName und
            # floorNameArray). Ohne diese Vereinigung landen genau die
            # interessantesten Ausloeser unter "(gilt immer)" statt unter
            # ihrer Schleife -- im Spiel aufgefallen, als
            # `trap_demo_gc_p04_300` in f040 fehlte.
            fl = list(floors_of(g, cond))
            for k in kids:
                for x in floors_of(g, k):
                    if x not in fl:
                        fl.append(x)
            rows.append({
                'level': lvl,
                'folder': folder, 'trap': tname.split('|')[-1], 'pos': pos,
                'rule': cname, 'floors': fl,
                'check': str(d.get('checkFuncNames', '')),
                'exec': str(d.get('execFuncNames', '')),
                'script': script, 'demo': demo or str(d.get('demoId', '')),
                'target': targets(d), 'effect': effect(d, script),
                'loop': str(d.get('loopCount', '')),
                'once': 'ja' if d.get('isOnce') else '',
                'note': ('schaltet Traps ein' if d.get('setEnable') else '')})
    return rows


def demo_rows(g):
    """Die Reaktionen: ShDemoScript haengt an demoId + messageName."""
    out = []
    ents = list(g.demos()) + list(
        g.doc.of_class('ShGameControllerMessageScript'))
    for e in ents:
        d = dict(g.fields(e))
        tgt = d.get('targetData', '')
        if isinstance(tgt, (list, tuple)):
            tgt = ', '.join(str(x).split('|')[-1] for x in tgt)
        else:
            tgt = str(tgt).split('|')[-1]
        out.append({
            'level': getattr(g, 'level', 'hallway'),
            'name': g.name(e, short=True), 'floors': floors_of(g, e),
            'demo': str(d.get('demoId', '')),
            'message': str(d.get('messageName', '')),
            'script': os.path.basename(str(d.get('scriptFile', ''))),
            'target': tgt,
            'visible': ('sichtbar' if d.get('isVisible')
                        else ('Geometrie an' if d.get('isGeomActive') else ''))})
    return out


def dedupe(rows):
    """Dieselbe Regel wird oft von mehreren Traps gefuehrt -- `condition_
    enable_demo_all` haengt an jedem `trap_enable_trap_all`, also an einem je
    Ebenenordner. Zwoelf gleiche Zeilen sagen nichts; die Traps gehoeren in
    EINE Zelle."""
    keyed = collections.OrderedDict()
    for r in rows:
        k = (r['level'], r['rule'], tuple(r['floors']), r['check'], r['exec'],
             r['script'], r['demo'], r['target'], r['effect'], r['loop'],
             r['once'], r['note'])
        cur = keyed.setdefault(k, dict(r, traps=[], folders=[]))
        if r['trap'] not in cur['traps']:
            cur['traps'].append(r['trap'])
        if r['folder'] and r['folder'] not in cur['folders']:
            cur['folders'].append(r['folder'])
    out = []
    for r in keyed.values():
        r['trap'] = ', '.join(r['traps'])
        r['folder'] = ', '.join(sorted(r['folders']))
        out.append(r)
    return out


def by_floor(rows):
    out = collections.defaultdict(list)
    for r in rows:
        for f in (r['floors'] or ['(gilt immer)']):
            out[f].append(r)
    return out


def order_key(f):
    return (ORDER.index(f), '') if f in ORDER else (len(ORDER), f)


def console(g, rows, demos, only=None):
    tf, td = by_floor(rows), by_floor(demos)
    keys = sorted(set(tf) | set(td), key=order_key)
    for f in keys:
        if only and f != only:
            continue
        print('\n=== %s   %d Regel(n), %d Reaktion(en)'
              % (f, len(tf.get(f, [])), len(td.get(f, []))))
        for r in tf.get(f, []):
            print('   %-32s %-28s %-24s %s'
                  % (r['rule'][:32],
                     CHECKS.get(r['check'], r['check'])[:28],
                     (r['demo'] or r['script'])[:24], r['effect'][:44]))
            if r['target']:
                print('        Ziel: %s' % r['target'][:110])
            print('        Trap: %s' % r['trap'][:110])
        for r in td.get(f, []):
            print('     -> %-12s %-22s %-26s %s'
                  % (r['demo'], r['message'][:22], r['script'][:26],
                     r['target'][:40]))


def xlsx(g, rows, demos, path):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    head = Font(bold=True, color='FFFFFF')
    fill = PatternFill('solid', fgColor='31506E')
    wrap = Alignment(vertical='top', wrap_text=True)

    def sheet(title, cols, data):
        ws = wb.create_sheet(title)
        ws.append(cols)
        for c in ws[1]:
            c.font = head
            c.fill = fill
            c.alignment = Alignment(vertical='center')
        for row in data:
            ws.append(row)
        for i, w in enumerate(WIDTH.get(title, []), 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for r in ws.iter_rows(min_row=2):
            for c in r:
                c.alignment = wrap
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        return ws

    tf, td = by_floor(rows), by_floor(demos)
    keys = sorted(set(tf) | set(td), key=order_key)

    # --- Uebersicht: eine Zeile je (Level, Schleife) ---
    ov = []
    levels = []
    for r in rows + demos:
        if r['level'] not in levels:
            levels.append(r['level'])
    for lv in levels:
        for f in keys:
            rr = [r for r in tf.get(f, []) if r['level'] == lv]
            dd = [r for r in td.get(f, []) if r['level'] == lv]
            if not rr and not dd:
                continue
            demoids = sorted({r['demo'] for r in rr + dd if r['demo']})
            objs = sorted({r['target'] for r in rr + dd
                           if r['target'] and 'shsb_' in r['target']})
            checks = sorted({CHECKS.get(r['check'], r['check'])
                             for r in rr if r['check']})
            effects = []
            for r in rr:
                if r['effect'] and r['effect'] not in effects:
                    effects.append(r['effect'])
            ov.append([lv, f, len(rr), len(dd), ', '.join(demoids),
                       ', '.join(checks), chr(10).join(effects),
                       chr(10).join(objs)])
    sheet('Uebersicht',
          ['Level', 'Schleife', 'Regeln', 'Reaktionen', 'Inszenierungen',
           'Ausloeseart', 'was passiert', 'geschaltete Objekte'], ov)

    # --- Ausloeser ---
    sheet('Ausloeser',
          ['Level', 'Schleife', 'Ordner', 'Trap', 'Lage x/y/z', 'Regel',
           'Pruefung', 'Aktion', 'Skript', 'Demo', 'Wirkung', 'Ziel',
           'ab Schleife', 'nur einmal', 'Bemerkung'],
          [[r['level'], f, r['folder'], r['trap'], r['pos'], r['rule'],
            CHECKS.get(r['check'], r['check']),
            EXECS.get(r['exec'], r['exec']), r['script'], r['demo'],
            r['effect'], r['target'], r['loop'], r['once'], r['note']]
           for f in keys for r in tf.get(f, [])])

    # --- Reaktionen ---
    sheet('Reaktionen',
          ['Level', 'Schleife', 'Name', 'Demo', 'Nachricht', 'Skript',
           'Ziel', 'Wirkung'],
          [[r['level'], f, r['name'], r['demo'], r['message'], r['script'],
            r['target'],
            r['visible']]
           for f in keys for r in td.get(f, [])])

    # --- Lisa ---
    lisa = []
    for f in keys:
        for r in tf.get(f, []) + td.get(f, []):
            blob = ' '.join(str(v) for v in r.values())
            if 'ocho' in blob.lower():
                lisa.append([r['level'], f,
                             r.get('trap') or r.get('name', ''),
                             r.get('rule') or r.get('message', ''),
                             r['target'],
                             r.get('visible') or r.get('note', '')])
    sheet('Lisa', ['Level', 'Schleife', 'Trap / Script',
                   'Regel / Nachricht', 'Ziel', 'Wirkung'], lisa)

    del wb['Sheet']
    wb.save(path)
    return path


WIDTH = {
    'Uebersicht': [16, 10, 8, 12, 30, 30, 40, 44],
    'Ausloeser': [9, 10, 9, 34, 16, 32, 26, 22, 26, 13, 30, 44, 11, 11, 20],
    'Reaktionen': [9, 10, 48, 13, 22, 28, 40, 14],
    'Lisa': [9, 10, 40, 32, 40, 16],
}


ALL = ['start', 'hallway', 'maze_A', 'maze_B', 'maze_C']


def main():
    a = sys.argv[1:]
    levels = (ALL if '--all' in a
              else [a[a.index('--level') + 1] if '--level' in a else 'hallway'])
    rows, demos, g = [], [], None
    for lv in levels:
        gg = ptlogic.Graph(level=lv)
        g = g or gg
        rr, dd = dedupe(collect(gg)), demo_rows(gg)
        rows += rr
        demos += dd
        print('  %-9s %3d Regeln an %2d Traps, %2d Reaktionen'
              % (lv, len(rr), len(gg.doc.of_class('GeoTrap')), len(dd)))

    if '--xlsx' in a:
        i = a.index('--xlsx')
        name = ('PT_Schleifen_alle.xlsx' if '--all' in a
                else 'PT_Schleifen_%s.xlsx' % levels[0])
        path = (a[i + 1] if len(a) > i + 1 and not a[i + 1].startswith('--')
                else os.path.join(os.path.expanduser('~'), 'Desktop', name))
        print('  geschrieben: %s' % xlsx(g, rows, demos, path))
        return
    console(g, rows, demos,
            only=a[a.index('--floor') + 1] if '--floor' in a else None)


if __name__ == '__main__':
    main()
