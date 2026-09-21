"""Spielstaende von P.T. finden, sichern und zuruecksetzen.

Wo sie liegen
-------------
shadPS4 kennt zwei Ablagen, und beide koennen gleichzeitig bestueckt sein --
je nachdem, ob der Emulator portabel laeuft oder nicht:

    <shadPS4-Verzeichnis>/user/home/<profil>/savedata/CUSA01127
    %APPDATA%/shadPS4/home/<profil>/savedata/CUSA01127

Nichts davon wird geraten. `<profil>` ist eine Nutzerkennung (1000, 1001, ...),
es kann also mehrere geben; darum wird jedes Profil in beiden Wurzeln
nachgesehen. Am 19.08.2026 waren hier 1000 bis 1003 angelegt, aber nur 1000
hatte Spielstaende -- ein fest verdrahtetes "1000" waere trotzdem falsch, weil
der Emulator das Profil wechseln kann und das Werkzeug auch auf fremden
Rechnern laufen soll. Das shadPS4-Verzeichnis kommt aus ptpaths, ist also in
der App einstellbar.

Sicherung
---------
Vor jedem Loeschen wird gesichert, ohne Rueckfrage. Ein Zip je Durchgang, mit
Datum und laufender Nummer, damit nie eines ueberschrieben wird:

    CUSA01127.bak.2026-08-19.001.zip

Im Zip liegt jeder Fundort unter einem eigenen Ordner (portable_1000,
appdata_1000), dazu MANIFEST.txt mit den echten Pfaden -- damit
Zurueckspielen von Hand ohne Raten geht.

    python ptsave.py              zeigen, was da ist
    python ptsave.py --backup     nur sichern
    python ptsave.py --reset      sichern und dann loeschen
"""
import datetime
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths

TITLE = 'CUSA01127'
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'save_backups')


def roots():
    """Die moeglichen Wurzeln, als (Kurzname, Pfad). Nicht auf Existenz geprueft."""
    out = [('portable', os.path.join(ptpaths.SHAD, 'user', 'home'))]
    ad = os.environ.get('APPDATA')
    if ad:
        out.append(('appdata', os.path.join(ad, 'shadPS4', 'home')))
    return out


def find():
    """Alle Spielstandordner. Liste aus (Kennung, Pfad, Dateien, Bytes)."""
    out = []
    seen = set()
    for tag, root in roots():
        if not os.path.isdir(root):
            continue
        try:
            profs = sorted(os.listdir(root))
        except OSError:
            continue
        for prof in profs:
            d = os.path.join(root, prof, 'savedata', TITLE)
            if not os.path.isdir(d):
                continue
            real = os.path.normcase(os.path.realpath(d))
            if real in seen:          # dieselbe Ablage ueber zwei Wege
                continue
            seen.add(real)
            n = size = 0
            for base, _, files in os.walk(d):
                for f in files:
                    n += 1
                    try:
                        size += os.path.getsize(os.path.join(base, f))
                    except OSError:
                        pass
            out.append(('%s_%s' % (tag, prof), d, n, size))
    return out


def _next_zip():
    """Naechster freier Name. Datum plus laufende Nummer, nie ueberschreiben."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    day = datetime.date.today().isoformat()
    i = 1
    while True:
        p = os.path.join(BACKUP_DIR, '%s.bak.%s.%03d.zip' % (TITLE, day, i))
        if not os.path.exists(p):
            return p
        i += 1


def backup(entries=None):
    """Alle Fundorte in EIN Zip. Gibt (Pfad, Anzahl Dateien) zurueck.

    Ohne Fundorte wird kein leeres Zip angelegt -- dann kommt (None, 0).
    """
    entries = find() if entries is None else entries
    if not entries:
        return None, 0
    path = _next_zip()
    n = 0
    stamp = datetime.datetime.now().isoformat(' ', 'seconds')
    lines = ['Sicherung vom %s' % stamp, '',
             'Zum Zurueckspielen den Inhalt des jeweiligen Ordners wieder',
             'nach dem hier genannten Pfad kopieren.', '']
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for tag, d, _, _ in entries:
            lines.append('%-16s %s' % (tag, d))
            for base, _, files in os.walk(d):
                for f in files:
                    full = os.path.join(base, f)
                    rel = os.path.relpath(full, d)
                    z.write(full, tag + '/' + rel.replace(os.sep, '/'))
                    n += 1
        z.writestr('MANIFEST.txt', chr(10).join(lines) + chr(10))
    return path, n


def reset(entries=None):
    """Sichern und dann loeschen. Gibt (Zip, Dateien, Liste geloescht) zurueck.

    Die Sicherung passiert IMMER und ZUERST -- schlaegt sie fehl, wird nicht
    geloescht. Geloescht wird der CUSA01127-Ordner selbst; shadPS4 legt ihn
    beim naechsten Speichern neu an.
    """
    entries = find() if entries is None else entries
    if not entries:
        return None, 0, []
    path, n = backup(entries)
    if not path:
        return None, 0, []
    gone = []
    for tag, d, _, _ in entries:
        try:
            shutil.rmtree(d)
            gone.append((True, d))
        except OSError as e:
            gone.append((False, '%s -- %s' % (d, e)))
    return path, n, gone


def human(b):
    return '%.1f KB' % (b / 1024.0) if b < 2**20 else '%.1f MB' % (b / 2**20)


def main():
    a = sys.argv[1:]
    e = find()
    if not e:
        print('  Keine Spielstaende gefunden. Gesucht wurde in:')
        for tag, r in roots():
            print('    %-9s %s' % (tag, os.path.join(r, '<profil>', 'savedata',
                                                     TITLE)))
        return
    print('  Gefunden:')
    for tag, d, n, size in e:
        print('    %-16s %d Datei(en), %s' % (tag, n, human(size)))
        print('        %s' % d)
    print()
    if '--reset' in a:
        z, n, gone = reset(e)
        print('  gesichert: %s  (%d Dateien)' % (z, n))
        for ok, d in gone:
            print('  %s %s' % ('geloescht:' if ok else 'FEHLER:  ', d))
    elif '--backup' in a:
        z, n = backup(e)
        print('  gesichert: %s  (%d Dateien)' % (z, n))
    else:
        print('  --backup sichert, --reset sichert und loescht dann.')


if __name__ == '__main__':
    main()
