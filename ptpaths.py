"""Wo liegen shadPS4 und P.T.? -- eine einzige Quelle fuer alle Werkzeuge.

Warum
-----
Die Pfade standen in fuenfzehn Skripten fest verdrahtet. Solange alles auf
einem Rechner blieb, war das bequem; sobald die App weitergegeben wird, ist es
unbrauchbar. Dieses Modul liest `playground.json` neben den Skripten und faellt
auf die bisherigen Werte zurueck, wenn es die Datei nicht gibt -- kein
bestehendes Werkzeug aendert dadurch sein Verhalten.

    import ptpaths
    ptpaths.GAME      Spielverzeichnis (enthaelt eboot.bin, chunk1.psarc)
    ptpaths.SHAD      shadPS4-Verzeichnis (enthaelt shadPS4.exe)
    ptpaths.QAR       texture.qar im Spielverzeichnis
    ptpaths.LOG       shad_log.txt des Emulators
    ptpaths.MGSV      MGSV-Prototyp, falls eingetragen (sonst leer)
    ptpaths.MGSV_DUMP dessen assets_.dump, falls eingetragen
    ptpaths.QAR_DICT  qar-Woerterbuch, sonst neben den Skripten gesucht
    ptpaths.LOG       shad_log.txt des Emulators
    ptpaths.MGSV      MGSV-Prototyp, falls eingetragen (sonst leer)
    ptpaths.MGSV_DUMP dessen assets_.dump, falls eingetragen
    ptpaths.QAR_DICT  qar-Woerterbuch, sonst neben den Skripten gesucht
    ptpaths.PSARC     chunk1.psarc
    ptpaths.ORIG      chunk1.orig.psarc  (unveraenderte Sicherung)

Nach dem Schreiben von `playground.json` muss ein laufendes Werkzeug neu
gestartet werden -- die Werte werden beim Import einmal festgelegt.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, 'playground.json')

# Rueckfall ohne Konfigurationsdatei: dieser Ordner liegt ueblicherweise
# IM shadPS4-Verzeichnis, also ist das Elternverzeichnis die beste
# Vermutung. Stimmt sie nicht, setzt man die Pfade auf der Tools-Seite.
DEFAULT_SHAD = os.path.dirname(HERE)
DEFAULT_GAME = os.path.join(DEFAULT_SHAD, 'installed_games', 'CUSA01127')

# sha256 der eboot.bin, gemessen an DIESER Installation (P.T. 1.00, CUSA01127).
# Bewusst nicht als "offizieller" Wert ausgegeben: er stammt aus dem hier
# vorhandenen Spiel, nicht aus einer verifizierten Originalquelle. Die App
# zeigt Soll und Ist nebeneinander, damit man selbst urteilen kann.
EBOOT_SHA256 = '6c9ca0c4bd53d01ad1678db2ff7ca031c8cf8ea2b4857669aa7ca0becba5d512'
EBOOT_SIZE = 26614736


def load():
    """Konfiguration lesen. Fehlt sie oder ist sie kaputt, gilt der Rueckfall."""
    try:
        with open(CONFIG, encoding='utf8') as f:
            return json.load(f)
    except Exception:
        return {}


def save(cfg):
    tmp = CONFIG + '.tmp'
    with open(tmp, 'w', encoding='utf8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG)


_cfg = load()
SHAD = _cfg.get('shadps4') or DEFAULT_SHAD
GAME = _cfg.get('game') or DEFAULT_GAME

LOG = os.path.join(SHAD, 'user', 'log', 'shad_log.txt')

# Zusatzquellen einzelner Werkzeuge. Ohne Eintrag in playground.json
# bleiben sie leer, und das jeweilige Werkzeug sagt selbst Bescheid.
MGSV = _cfg.get('mgsv_prototype') or ''
MGSV_DUMP = _cfg.get('mgsv_asset_dump') or ''
QAR_DICT = (_cfg.get('qar_dictionary')
            or os.path.join(HERE, 'qar_dictionary.txt'))

LOG = os.path.join(SHAD, 'user', 'log', 'shad_log.txt')

# Zusatzquellen einzelner Werkzeuge. Ohne Eintrag in playground.json
# bleiben sie leer, und das jeweilige Werkzeug sagt selbst Bescheid.
MGSV = _cfg.get('mgsv_prototype') or ''
MGSV_DUMP = _cfg.get('mgsv_asset_dump') or ''
QAR_DICT = (_cfg.get('qar_dictionary')
            or os.path.join(HERE, 'qar_dictionary.txt'))

QAR = os.path.join(GAME, 'texture.qar')
QAR_BAK = os.path.join(GAME, 'bak', 'texture.qar')
PSARC = os.path.join(GAME, 'chunk1.psarc')
ORIG = os.path.join(GAME, 'chunk1.orig.psarc')
EBOOT = os.path.join(GAME, 'eboot.bin')
EXE = os.path.join(SHAD, 'shadPS4.exe')
# Eigener Build mit Analyseschaltern (PT_CLEAR). Liegt NEBEN der normalen Exe,
# damit die erprobte Fassung unberuehrt bleibt. Kann fehlen -- wer sie anbietet,
# muss das pruefen.
EXE_EXP = os.path.join(SHAD, 'shadPS4-experimental.exe')


def eboot_state(path=None):
    """(zustand, text) -- fuer die Anzeige in der App.

    zustand: 'ok' | 'anders' | 'fehlt'
    """
    import hashlib
    p = path or EBOOT
    if not os.path.exists(p):
        return 'fehlt', 'eboot.bin not found in %s' % os.path.dirname(p)
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    got = h.hexdigest()
    if got == EBOOT_SHA256:
        return 'ok', 'eboot.bin matches the reference (P.T. 1.00)'
    return 'anders', ('eboot.bin differs - other game version or modified\n'
                      'expected %s\ngot      %s' % (EBOOT_SHA256[:32], got[:32]))


def game_ok(path):
    """Sieht dieses Verzeichnis nach einer P.T.-Installation aus?"""
    return all(os.path.exists(os.path.join(path, n))
               for n in ('eboot.bin', 'chunk1.psarc'))


def shad_ok(path):
    return os.path.exists(os.path.join(path, 'shadPS4.exe'))


if __name__ == '__main__':
    print('  Konfiguration : %s  (%s)'
          % (CONFIG, 'vorhanden' if os.path.exists(CONFIG) else 'Ruckfall'))
    print('  shadPS4       : %s  %s' % (SHAD, 'OK' if shad_ok(SHAD) else 'FEHLT'))
    print('  Spiel         : %s  %s' % (GAME, 'OK' if game_ok(GAME) else 'FEHLT'))
    print('  eboot         : %s' % (eboot_state()[1].splitlines()[0]))
    print('  qar aktiv     : %s' % ('ja' if os.path.exists(QAR) else 'nein'))
    print('  qar Sicherung : %s' % ('ja' if os.path.exists(QAR_BAK) else 'nein'))
