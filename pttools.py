# -*- coding: utf-8 -*-
r"""Datei- und Systemhelfer -- was beide Oberflaechen brauchen.

Herausgeloest aus `hovergui.py` am 14.09.2026, weil die Qt-Fassung genau
dasselbe braucht und eine zweite Kopie unweigerlich auseinanderlaeuft. Hier
steht nichts ueber das Spiel im Speicher (das ist `ptplayer.py`), sondern nur
Umgang mit Dateien und Unterprozessen.

    qar_state / qar_toggle    texture.qar weg- und zurueckschieben
    eboot_run                 nogravity.py aufrufen (eboot-Patches)
    run_tool                  irgendein Werkzeug hier im Ordner aufrufen
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ptpaths


# ------------------------------------------------------------------ texture.qar
def qar_state():
    """('on'|'off'|'none', Text) -- liegt texture.qar im Spielverzeichnis?

    'on'   Archiv aktiv (das Spiel laedt die hochaufgeloesten Stufen)
    'off'  nur die Sicherung in bak\\ vorhanden
    'none' weder noch -- dann laesst sich nichts umschalten
    """
    a, b = os.path.exists(ptpaths.QAR), os.path.exists(ptpaths.QAR_BAK)
    if a and b:
        return 'on', 'texture.qar is active (backup present)'
    if a and not b:
        return 'on', 'texture.qar is active - NO backup in bak\\'
    if b:
        return 'off', 'texture.qar removed - backup in bak\\'
    return 'none', 'neither texture.qar nor bak\\texture.qar found'


def qar_toggle():
    """Archiv weg- oder zurueckschieben. Gibt eine Meldung zurueck.

    Es wird NIE geloescht, nur zwischen Spielverzeichnis und bak\\ verschoben
    -- beide Richtungen sind damit verlustfrei umkehrbar.
    """
    st, _ = qar_state()
    try:
        if st == 'on':
            os.makedirs(os.path.dirname(ptpaths.QAR_BAK), exist_ok=True)
            if os.path.exists(ptpaths.QAR_BAK):
                os.remove(ptpaths.QAR)          # Sicherung gibt es schon
                return 'texture.qar removed (backup was already there)'
            shutil.move(ptpaths.QAR, ptpaths.QAR_BAK)
            return 'texture.qar moved to bak\\'
        if st == 'off':
            shutil.copy2(ptpaths.QAR_BAK, ptpaths.QAR)
            return 'texture.qar restored from bak\\'
        return 'nothing to do - no archive found'
    except Exception as e:
        return 'ERROR: %s' % e


# --------------------------------------------------------------- Unterprozesse
def run_tool(script, args):
    """Ein Werkzeug aus diesem Ordner aufrufen. Gibt (ok, Ausgabe).

    Immer mit demselben Python wie dieses Programm und mit `cwd=HERE`, damit
    die Werkzeuge ihre Nachbarmodule finden.
    """
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, script)] + list(args),
                           capture_output=True, text=True, encoding='utf8',
                           errors='replace', cwd=HERE)
        out = ((r.stdout or '') + (r.stderr or '')).strip()
        return r.returncode == 0, out
    except Exception as e:
        return False, str(e)


def eboot_run(args):
    """nogravity.py aufrufen -- das setzt und loest die eboot-Patches."""
    return run_tool('nogravity.py', args)
