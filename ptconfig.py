"""shadPS4-Einstellungen lesen und aendern.

Wo sie liegen
-------------
Beide Ablagen folgen demselben Aufbau, nur die Wurzel ist verschieden:

    portabel   <shadPS4-Verzeichnis>/user
    sonst      %APPDATA%/shadPS4

und darunter jeweils

    config.toml                      gilt fuer alle Spiele
    custom_configs/CUSA01127.toml    gilt nur fuer P.T.

Die spielspezifische Datei ist die interessantere: was dort steht, betrifft
nur P.T. Am 19.08.2026 wichen auf diesem Rechner presentMode (Mailbox statt
Immediate) und readbacksMode (2 statt 0) voneinander ab -- die beiden Dateien
sind also wirklich unterschiedlich in Gebrauch.

Warum zeilenweise geschrieben wird
----------------------------------
Python liest TOML seit 3.11 mit `tomllib`, kann es aber nicht schreiben, und
eine Fremdbibliothek soll das Werkzeug nicht brauchen. Selbst neu zu
serialisieren waere ohnehin die schlechtere Wahl: das wuerfelt Reihenfolge und
Formatierung durcheinander und schreibt Schluessel um, die niemand angefasst
hat. Stattdessen wird genau die Zeile ersetzt, deren Wert sich aendert --
alles andere bleibt Byte fuer Byte stehen.

Vor jeder Aenderung wird gesichert.

VORSICHT beim laufenden Emulator: die globale Datei enthaelt die
Fensterposition (geometry_x, mw_width ...), und die kann nur beim Beenden
dorthin gelangen -- shadPS4 schreibt die Konfiguration also mindestens
teilweise selbst zurueck. Ob das auch die spielspezifische Datei betrifft,
ist NICHT gemessen. Solange das offen ist, sperrt die App das Speichern,
wenn das Spiel laeuft; das ist Vorsicht, kein Messergebnis.

    python ptconfig.py                        zeigen, was da ist
    python ptconfig.py GPU vblankFrequency    einen Wert zeigen
"""
import datetime
import io
import json
import os
import shutil
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths

TITLE = 'CUSA01127'

# Abschnitte, die im Fenster nichts verloren haben: Fensterposition, zuletzt
# geoeffnete Dateien, Pfadlisten. Nichts davon beeinflusst das Spiel.
HIDE_SECTIONS = ('GUI', 'Keys')

# Kurzerklaerungen. Nur fuer Schluessel, bei denen der Name allein nicht
# reicht -- alles andere bleibt bewusst unkommentiert, statt eine Erfindung
# danebenzuschreiben.
HINTS = {
    ('GPU', 'readbacks'):
        'read GPU memory back to the CPU - some games need it, costs speed',
    ('GPU', 'readbacksMode'): '0 = off, higher = more aggressive',
    ('GPU', 'readbackLinearImages'): 'read back linear images as well',
    ('GPU', 'copyGPUBuffers'): 'copy GPU buffers instead of mapping them',
    ('GPU', 'directMemoryAccess'): 'let the GPU touch guest memory directly',
    ('GPU', 'presentMode'):
        'Immediate = no vsync, Mailbox = vsync without stutter, Fifo = vsync',
    ('GPU', 'vblankFrequency'): 'emulated vblank rate in Hz',
    ('GPU', 'vblankDivider'): 'divides the vblank rate - 2 halves it',
    ('GPU', 'fsrEnabled'): 'FSR upscaling',
    ('GPU', 'rcasEnabled'): 'RCAS sharpening on top of FSR',
    ('GPU', 'rcasAttenuation'): 'how strong the sharpening is',
    ('GPU', 'internalScreenWidth'): 'what the game renders at',
    ('GPU', 'internalScreenHeight'): 'what the game renders at',
    ('GPU', 'screenWidth'): 'window size',
    ('GPU', 'screenHeight'): 'window size',
    ('GPU', 'nullGpu'): 'render nothing at all - for testing only',
    ('GPU', 'dumpShaders'): 'write every shader to disk',
    ('GPU', 'patchShaders'): 'apply shader fixes - leave this on',
    ('General', 'extraDmemInMbytes'): 'extra guest memory in MB',
    ('General', 'logFilter'): 'empty means everything',
    ('General', 'logType'): 'sync writes immediately, async is faster',
    ('Debug', 'logEnabled'): 'write a log file at all',
    ('Debug', 'showFpsCounter'): 'frame counter in the window',
    ('Debug', 'DebugDump'): 'dump modules and shaders on start',
    ('Debug', 'CollectShader'): 'collect shaders for later dumping',
    ('Vulkan', 'crashDiagnostic'): 'slow, but says why the GPU died',
    ('Vulkan', 'validation'): 'Vulkan validation layers - slow',
    ('Vulkan', 'pipelineCacheEnable'): 'cache pipelines, shortens loading',
    ('Vulkan', 'gpuId'): 'which GPU to use, -1 picks automatically',
}

# Feste Auswahlen statt freier Eingabe, wo der Wert nur wenige Formen kennt.
CHOICES = {
    ('GPU', 'presentMode'): ['Immediate', 'Mailbox', 'Fifo'],
    ('GPU', 'FullscreenMode'): ['Windowed', 'Borderless', 'Fullscreen'],
    ('General', 'logType'): ['sync', 'async'],
}


def roots():
    """(Kurzname, Wurzel) -- beide Ablagen, ohne Pruefung auf Existenz."""
    out = [('portable', os.path.join(ptpaths.SHAD, 'user'))]
    ad = os.environ.get('APPDATA')
    if ad:
        out.append(('appdata', os.path.join(ad, 'shadPS4')))
    return out


def files():
    """Alle vorhandenen Konfigurationen als (Kennung, Pfad).

    Die spielspezifische steht vor der globalen, weil sie fuer P.T. die
    genauere ist.
    """
    out = []
    seen = set()
    for tag, root in roots():
        for what, rel in (('game', os.path.join('custom_configs',
                                                TITLE + '.json')),
                          ('global', 'config.json')):
            p = os.path.join(root, rel)
            if not os.path.isfile(p):
                continue
            real = os.path.normcase(os.path.realpath(p))
            if real in seen:
                continue
            seen.add(real)
            out.append(('%s (%s)' % (what, tag), p))
    return out


def stale_files():
    """Die alten .toml -- gefunden, aber ohne Wirkung.

    shadPS4 liest sie seit dem Build vom 13.09.2026 nicht mehr. Sie hier zu
    melden ist ehrlicher, als sie zu verschweigen: wer sie im Verzeichnis
    sieht, haelt sie sonst fuer die Wahrheit.
    """
    out = []
    for tag, root in roots():
        for rel in (os.path.join('custom_configs', TITLE + '.toml'),
                    'config.toml'):
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                out.append(p)
    return out


def load(path):
    """Dict aus Abschnitt -> {Schluessel: Wert}. Wirft bei kaputtem JSON.

    shadPS4 legt die Einstellungen als JSON mit Abschnitten der obersten Ebene
    ab (`General`, `Vulkan`, `GPU`, ...). Werte, die selbst Objekte oder Listen
    sind, bleiben stehen und werden von der Oberflaeche uebersprungen.
    """
    with io.open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('unerwarteter Aufbau: keine Abschnitte')
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def fmt(v):
    """Einen Wert so schreiben, wie TOML ihn erwartet."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace(BSLASH, BSLASH + BSLASH).replace('"', BSLASH + '"')
    return '"' + s + '"'


def backup(path):
    """Kopie neben die Datei legen, fortlaufend nummeriert."""
    day = datetime.date.today().isoformat()
    i = 1
    while True:
        p = '%s.bak.%s.%03d' % (path, day, i)
        if not os.path.exists(p):
            shutil.copy2(path, p)
            return p
        i += 1


def write(path, changes):
    """changes: {(Abschnitt, Schluessel): Wert}. Gibt (Zahl, Sicherung).

    Anders als bei der TOML-Fassung duerfen fehlende Schluessel ANGELEGT
    werden: die Datei wird geparst und vollstaendig neu geschrieben, ein
    unbekannter Schluessel steht danach sichtbar drin und kann nichts
    zerreissen. Bei der zeilenweisen TOML-Bearbeitung war das Verbot noetig,
    hier nicht.

    Vor dem Schreiben wird gesichert, und geschrieben wird ueber eine
    Zwischendatei -- ein abgebrochener Schreibvorgang soll keine halbe
    Konfiguration hinterlassen.
    """
    if not changes:
        return 0, None
    bak = backup(path)
    with io.open(path, encoding='utf-8') as f:
        data = json.load(f)
    n = 0
    for (sec, key), val in changes.items():
        node = data.setdefault(sec, {})
        if not isinstance(node, dict):
            continue
        if node.get(key) != val:
            node[key] = val
            n += 1
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return n, bak


def main():
    a = sys.argv[1:]
    fs = files()
    if not fs:
        print('  Keine Konfiguration gefunden. Gesucht in:')
        for tag, r in roots():
            print('    %-9s %s' % (tag, r))
        return
    for tag, p in fs:
        print('  %-18s %s' % (tag, p))
    print()
    tag, path = fs[0]
    d = load(path)
    if len(a) == 2:
        print('  %s / %s = %r' % (a[0], a[1], d.get(a[0], {}).get(a[1])))
        return
    print('  Inhalt von %s:' % tag)
    for sec in d:
        if sec in HIDE_SECTIONS:
            print('    [%s]  (ausgeblendet)' % sec)
            continue
        print('    [%s]' % sec)
        for k, v in d[sec].items():
            print('       %-26s %-20s %s' % (k, repr(v),
                                             HINTS.get((sec, k), '')))


if __name__ == '__main__':
    main()
