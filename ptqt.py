# -*- coding: utf-8 -*-
r"""P.T. Playground -- Qt-Oberflaeche.

    python ptqt.py

Aufbau
------
Links eine Liste der Seiten, rechts die Seite. Elf Seiten, nach dem geordnet,
WANN etwas wirkt -- das war in der tkinter-Fassung durcheinander:

    Player      sofort im laufenden Spiel: Schweben, Warp, Tempo, Lampe
    Location    wo bin ich, was liegt hinter der naechsten Tuer
    Objects     versteckte Objekte ein- und ausblenden, ohne Neubau
    Doors       Tuerzustand und das Schlossbyte
    Build       erst beim naechsten Start: Archiv neu bauen
    Floors      Nachschlagewerk, was jede Etage freischaltet
    Screenplay  Ausloeser scharfstellen -- HOCH EXPERIMENTELL
    Tools       Spielstand, Texturen, texture.qar, Streaming, Pfade
                (dort auch die Auswahl, wo shadPS4 und das Spiel liegen --
                 fehlt eines, warnt das Werkzeug auf der Spielerseite)
    shadPS4     die Emulatorkonfiguration
    About       Credits und Lizenz

Diese Datei ist nur die Haut. Alles, was etwas ueber das Spiel WEISS, steht in
den Modulen; taucht hier ein Offset oder ein Messwert auf, ist er an der
falschen Stelle:

    ptplayer.py    Spieler und Gamepad: Schweben, Warp, Teleport, Tempo,
                   Lampe, Texturstreaming -- weiss von keinem Fenster
    pttools.py     Dateien und Unterprozesse: texture.qar, eboot-Patches
    ptvis.py       Objektsichtbarkeit im laufenden Spiel
    ptdoor.py      Tuerzustand und das Schlossbyte (body+0x80)
    ptloop.py      Ebene, Level, was hinter der naechsten Tuer liegt
    ptobjects.py   die 143 StaticModel samt Kategorie aus dem Assetpfad
    ptsteps.py     die GeoTrap-Ausloeser des Flurs
    ptconfig.py    shadPS4-Konfiguration lesen und schreiben
    ptsave.py      Spielstand sichern und zuruecksetzen
    noclip.py      die geprueften Kollisionskandidaten (Kommandozeile)

`hovergui.py`, die aeltere tkinter-Fassung, wird nicht mehr mitgeliefert.
Sie benutzt dieselben Module, es gab also nie eine zweite Wahrheit; ihr
Funktionsumfang ist hier uebernommen, und die eboot-Seite zeigt sogar alle
sieben Eingriffe, wo die alte Fassung nur einen auffuehrte.

Bedienung am Gamepad
--------------------
    Steuerkreuz oben/unten      Schwebehoehe
    X + Steuerkreuz             Warp in festen Schritten

Zoom
----
Qt uebernimmt nur die DPI-Vorgabe von Windows. Der Regler unten rechts (oder
Strg+Plus / Strg+Minus / Strg+0) skaliert die Anwendungsschrift, und weil die
Layouts in Schriftmetriken rechnen, wachsen Knoepfe und Zeilen mit. Bewusst
NICHT zusaetzlich ueber QT_SCALE_FACTOR: das laesst die Punktgroesse
unveraendert und wuerde beim naechsten Start ein zweites Mal skalieren.

PySide6
-------
Kommt aus der normalen Python-Installation dieses Rechners:

    python -m pip install --user PySide6

Frueher lag es zwingend in `vendor/` neben dem Werkzeug, weil ein
`pip install --user` einmal in einer umgeleiteten AppData-Kopie landete und
fuer das echte Python unsichtbar war (13.09.2026, damals ein Store-Python).
Mit einer Installation von python.org tritt das nicht auf. `vendor/` wird
weiterhin erkannt, aber nur noch als Rettung, wenn der normale Weg versagt --
etwa auf einem Rechner, auf den das Werkzeug samt Ordner kopiert wurde.
"""
import os
import shutil
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# PySide6 kommt aus der NORMALEN Python-Installation dieses Rechners.
#
# Frueher stand hier ein `sys.path.insert(0, VENDOR)`, das eine mitgelieferte
# Kopie VOR alles andere setzte. Grund war, dass ein `pip install --user`
# einmal in einer umgeleiteten AppData-Kopie landete und fuer das echte Python
# unsichtbar war (13.09.2026) -- ein Store-Python. Mit python.org tritt das
# nicht auf, und zwei Kopien derselben Fassung nebeneinander sind nur Ballast.
#
# `vendor/` bleibt als RETTUNG, nicht als Regel: gesucht wird es erst, wenn
# der normale Weg versagt. Sonst gewaenne es wieder.
VENDOR = os.path.join(HERE, 'vendor')

# Die Ausnahme wird NICHT verschluckt. "PySide6 fehlt" war frueher eine
# Behauptung, und sie war schon falsch: am 21.09.2026 lag die Bibliothek im
# Benutzerkontext und liess sich ueber denselben Weg einwandfrei importieren.
# Ein Import kann aus mehreren Gruenden scheitern, die von aussen gleich
# aussehen -- ein anderes Python, ein leerer Ordner `PySide6` im Suchpfad
# (Python nimmt ihn als Namensraumpaket und verdeckt das echte), fehlendes
# shiboken6. Wer das nicht anzeigt, laesst raten.
_pyside_fehler = []
try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError as _e:
    _pyside_fehler.append(u'%s: %s' % (type(_e).__name__, _e))
    if os.path.isdir(VENDOR):
        sys.path.append(VENDOR)
        try:
            from PySide6 import QtCore, QtGui, QtWidgets
            _pyside_fehler = []
        except ImportError as _e2:
            _pyside_fehler.append(u'aus vendor: %s: %s'
                                  % (type(_e2).__name__, _e2))

if _pyside_fehler:
    sys.exit(u'  PySide6 laesst sich nicht laden.\n'
             u'\n'
             u'  Interpreter: %s\n'
             u'  Grund      : %s\n'
             u'\n'
             u'  Gesucht wurde in:\n%s\n'
             u'\n'
             u'  Einrichten mit:\n'
             u'     python -m pip install --user PySide6\n'
             u'  Oder portabel neben das Werkzeug:\n'
             u'     python -m pip install --no-user --target "%s" PySide6\n'
             u'\n'
             u'  Steht oben ein anderes Python, als mit dem installiert wurde,\n'
             u'  ist DAS die Ursache -- eine Dateiverknuepfung startet nicht\n'
             u'  zwingend dasselbe wie "python" auf der Kommandozeile.'
             % (sys.executable,
                u'\n               '.join(_pyside_fehler),
                u'\n'.join(u'     %s' % (p or u'(Arbeitsverzeichnis)')
                           for p in sys.path),
                VENDOR))

import grsupp
import luaprobe
import ptconfig
import ptdoor
import ptloop
import ptmem
import ptobjects
import ptexpo
import ptplayer
import ptpaths
import ptsave
import ptstate
import ptsteps
import ptvis
import pttools
import psarc
import spawn

TICK_MS = 60

ORG, APP = 'ptplayground', 'ptqt'      # fuer QSettings
ZOOMS = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5)


def load_zoom():
    """Gespeicherter Zoom, auf einen sinnvollen Bereich beschnitten."""
    st = QtCore.QSettings(ORG, APP)
    try:
        v = float(st.value('zoom', 1.0))
    except (TypeError, ValueError):
        v = 1.0
    return min(3.0, max(0.75, v))


def save_zoom(v):
    QtCore.QSettings(ORG, APP).setValue('zoom', float(v))


def load_lang():
    v = QtCore.QSettings(ORG, APP).value('lang', 'en')
    return 'de' if str(v) == 'de' else 'en'


def save_lang(v):
    QtCore.QSettings(ORG, APP).setValue('lang', v)


# Was hinter die Startraumtuer gehaengt werden kann. Die Connectoren sind
# aus den fox2 der Stages AUSGELESEN, nicht geraten (luaprobe.STAGES).
STAGE_LABELS = [
    ('strasse', 'Street (ending)'),
    ('hallway', 'Hallway'),
    ('maze_a', 'Maze A'),
    ('maze_b', 'Maze B'),
    ('maze_c', 'Maze C'),
    ('vanilla', 'Vanilla - door untouched'),
]

# Was jede Etage freischaltet. Ausgelesen aus pt14_hallway.fox2: jede Etage
# hat ein `<name>_demo|condition_enable_demo_all`, dessen targetData genau
# diese Ereignisse benennt. Nicht zusammengefasst, nur lesbar gemacht.
FLOOR_EVENTS = [
    ('f005', 'demo gc_p04_310, demo stop'),
    ('f020', 'demo gc_p01_081, head-struck sfx off, bathroom cry vfx off'),
    ('f030', 'demo gc_p01_011 + gc_p01_020, lobby door visible / open'),
    ('f040', 'demo gc_p04_300 + gc_p04_350, change light, cry s01 -> l01'),
    ('f050', 'demo gc_p04_320, stop radio, subtitle area'),
    ('f060', 'demo gc_p03_011 + gc_p01_110, bathroom door 170, stop BGM'
             ' herald01'),
    ('f070', 'demo gc_p04_120 + gc_p04_280, baby cry vfx off'),
    ('f080', 'BGM unrest02, radio baby mimicry, baby cries, baby talks,'
             ' radio'),
    ('f100', 'stop radio, CEILING LAMP RED'),
    ('f120', 'demo gc_p02_080, change game step, disable option'),
    ('f160', 'GOTO ENDING, ending demo, force gameover'),
]


class Attacher(QtCore.QThread):
    """`Holder.attach()` im Hintergrund.

    `hover.find_base` durchsucht den Prozessspeicher nach einem 48-Byte-Muster
    und braucht Sekunden. Im Takt aufgerufen wuerde das Fenster stehen -- und
    genau darum geht ein selbsttaetiges Verbinden nur so.
    """

    done = QtCore.Signal(bool)

    def __init__(self, holder):
        super().__init__()
        self._h = holder

    def run(self):
        try:
            ok = self._h.attach()
        except Exception:
            ok = False
        self.done.emit(bool(ok))


class Runner(QtCore.QThread):
    """Eine lange Arbeit im Hintergrund, Ergebnis per Signal.

    Der Archivbau schreibt 600 MB und braucht eine halbe Minute; ohne Thread
    friert das Fenster so lange ein. Das Ergebnis kommt als Signal zurueck,
    damit die Oberflaeche nur im Hauptthread angefasst wird.
    """

    done = QtCore.Signal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            ok, msg = self._fn()
        except Exception as ex:
            ok, msg = False, 'ERROR: %s' % ex
        self.done.emit(bool(ok), str(msg))


# Englisch -> Deutsch. Nur ganze Beschriftungen, damit nichts halb uebersetzt
# wird. Was hier fehlt, bleibt englisch stehen -- besser als ein Leerfeld.
DE = {
    # Seitennamen
    'Player': 'Spieler', 'Location': 'Ort', 'Objects': 'Objekte',
    'Doors': 'Türen', 'Build': 'Bauen', 'Floors': 'Etagen',
    'Screenplay': 'Drehbuch', 'Tools': 'Werkzeug', 'About': 'Über',
    'Light': 'Licht', 'Camera': 'Kamera',
    # Kameraseite
    'Free camera': 'Freie Kamera', 'Move': 'Bewegen', 'Look': 'Blick',
    'take the camera': 'Kamera übernehmen',
    'Back to the player': 'Zurück zum Spieler',
    'Push to the front': 'Nach vorn hängen',
    'Triangle': 'Dreieck', 'Circle': 'Kreis', 'Square': 'Viereck',
    'Left stick': 'Linker Stick', 'Right stick': 'Rechter Stick',
    'L1 / R1': 'L1 / R1',
    'hand the pad to the camera and back':
        'Steuerung an die Kamera und zurück',
    'take the camera / give it back to the player':
        'Kamera übernehmen / an den Spieler zurückgeben',
    'push the camera to the front of the list':
        'Kamera nach vorn hängen',
    'move': 'bewegen', 'look around': 'umsehen',
    'drop and rise': 'senken und heben',
    'the gamepad steers the camera': 'Gamepad steuert die Kamera',
    'pin the player down while steering':
        'Spieler festhalten, solange gesteuert wird',
    'forward': 'vor', 'back': 'zurück', 'left': 'links',
    'right': 'rechts', 'up': 'hoch', 'down': 'runter',
    'step': 'Schritt', 'per tick': 'je Takt', 'height': 'Höhe',
    'yaw': 'Gierung', 'pitch': 'Neigung',
    # Lichtseite
    'type': 'Typ',
    'Exposure': 'Belichtung', 'compensation': 'Ausgleich',
    'ceiling': 'Deckel',
    # Ueberschriften
    'Hover': 'Schweben', 'Warp': 'Warp', 'Position': 'Position',
    'Walk speed': 'Laufgeschwindigkeit', 'Flashlight': 'Taschenlampe',
    'Connection': 'Verbindung', 'Where am I': 'Wo bin ich',
    'Send me to a loop': 'In eine Schleife setzen',
    'Hidden objects': 'Versteckte Objekte',
    'What is in the archive now': 'Was jetzt im Archiv steht',
    'Behind the start room door': 'Hinter der Startraumtür',
    'Start on a loop': 'Auf einer Schleife starten',
    'Spawn a baby': 'Ein Baby setzen',
    'What each floor arms': 'Was jede Etage freischaltet',
    'Patch eboot.bin': 'eboot.bin patchen',
    'Triggers in the hallway': 'Auslöser im Flur',
    'Savegame': 'Spielstand', 'Texture streaming': 'Texturstreaming',
    'Street textures': 'Straßentexturen',
    'archive: detail level frozen': 'Archiv: Detailstufe eingefroren',
    'archive: original': 'Archiv: unverändert',
    'archive: cannot tell': 'Archiv: nicht feststellbar',
    'Freeze the detail level': 'Detailstufe einfrieren',
    'Back to original': 'Zurück zum Original',
    'Export textures as PNG': 'Texturen als PNG ausgeben',
    'Restart': 'Neustart', 'Restart tool': 'Werkzeug neu starten',
    'Rescan': 'Neu suchen', 'which one': 'welche',
    'Cutscene': 'Zwischensequenz', 'pause the cutscene': 'Sequenz anhalten',
    'held': 'angehalten', 'running': 'läuft', 'no cutscene': 'keine Sequenz',
    'Read cameras': 'Kameras einlesen',
    'free camera': 'freie Kamera',
    'watch a game camera': 'durch eine Spielkamera sehen',
    'auto - first unused': 'selbsttätig - erste unbenutzte',
    'unused': 'unbenutzt', 'game camera': 'Spielkamera',
    'in use by the game': 'vom Spiel benutzt',
    'Paths': 'Pfade', 'License': 'Lizenz',
    'shadPS4 configuration': 'shadPS4-Konfiguration',
    'P.T. Playground': 'P.T. Playground',
    # Knoepfe
    'Start hovering': 'Schweben an', 'Stop hovering': 'Schweben aus',
    'forward': 'vorwärts', 'back': 'zurück', 'left': 'links',
    'right': 'rechts', 'Save spot': 'Ort merken', 'Go': 'Hin',
    'Reset': 'Zurücksetzen', 'Pick': 'Wählen',
    'Start emulator + game': 'Emulator und Spiel starten',
    'Reconnect': 'Neu verbinden', 'Set': 'Setzen',
    'Apply live': 'Sofort anwenden', 'Game default': 'Spielvorgabe',
    'Open': 'Öffnen', 'Close': 'Schließen',
    'Read state': 'Zustand lesen', 'Re-read': 'Neu lesen',
    'Take these settings': 'Diese Einstellungen übernehmen',
    'Restore original': 'Original zurückholen',
    'Build archive': 'Archiv bauen', 'reset': 'zurücksetzen',
    'on table': 'auf den Tisch', 'Apply selected': 'Ausgewählte anwenden',
    'Restore shipped eboot': 'Ausgeliefertes eboot zurückholen',
    'Reload': 'Neu laden', 'Save': 'Speichern',
    'Backup only': 'Nur sichern', 'Reset savegame': 'Spielstand löschen',
    'Open folder': 'Ordner öffnen', 'follow the player': 'dem Spieler folgen',
    'Export ...': 'Ausgeben ...', 'Open LICENSE': 'LICENSE öffnen',
    'Scan for triggers': 'Auslöser suchen',
    'Show offset': 'Offset zeigen', 'Hide offset': 'Offset verbergen',
    # Beschriftungen
    'height': 'Höhe', 'step': 'Schritt', 'hold rate': 'Halterate',
    'colour': 'Farbe', 'bright': 'Helligkeit', 'door': 'Tür',
    'stage': 'Stage', 'floor': 'Etage', 'category': 'Kategorie',
    'filter': 'Filter', 'file': 'Datei', 'how many': 'wie viele',
    'of 1061': 'von 1061', 'at x / y / z': 'bei x / y / z',
    'shadPS4:': 'shadPS4:', 'P.T.:': 'P.T.:', 'zoom': 'Zoom',
    ' zoom ': ' Zoom ',
    # Kaestchen
    'keep across loops': 'über Schleifen halten',
    'keep': 'halten',
    'hidden only': 'nur versteckte',
    'keep it across room changes': 'über Raumwechsel halten',
    'connect by itself, and reconnect after a game restart':
        'selbst verbinden, auch nach einem Neustart des Spiels',
    'arm the ending trap on every floor':
        'Ending-Falle auf jeder Etage scharfstellen',
    'give me the flashlight (needed on a fresh save)':
        'Taschenlampe geben (bei frischem Spielstand nötig)',
    'put a baby on the table': 'ein Baby auf den Tisch stellen',
    # Spalten
    'object': 'Objekt', 'what it is': 'was es ist',
    'copy': 'Kopie', 'state': 'Zustand', 'where': 'wo',
    'site': 'Stelle', 'what it does': 'was es tut',
    'what it arms': 'was es freischaltet',
    'trigger': 'Auslöser', 'floors': 'Etagen', 'armed': 'scharf',
}


# Die langen Erklaerabsaetze stehen in ptlang.py -- hier wuerden sie den
# Quelltext zutexten. Zusammengefuehrt an genau dieser Stelle, damit `tr`
# eine einzige Nachschlagequelle hat.
try:
    import ptlang
    DE.update(ptlang.DE)
except ImportError:          # ohne ptlang bleibt alles englisch, kein Absturz
    pass


def tr(text, lang):
    """Uebersetzen, wenn es dafuer einen Eintrag gibt."""
    if lang != 'de' or not text:
        return text
    return DE.get(text, text)


# --------------------------------------------------------------- Hilfsmittel
def hline():
    f = QtWidgets.QFrame()
    f.setFrameShape(QtWidgets.QFrame.HLine)
    f.setFrameShadow(QtWidgets.QFrame.Sunken)
    return f


def note(text, colour='#666'):
    """Ein Absatz Erklaerung. Bricht um und waechst nicht ins Unendliche.

    Leerer Text heisst "kein Absatz": das Label wird versteckt, und ein
    verstecktes Widget nimmt im Layout keinen Platz ein. So lassen sich
    Absaetze entfernen, ohne die Aufbaureihenfolge anzufassen.
    """
    lb = QtWidgets.QLabel(text)
    lb.setWordWrap(True)
    lb.setStyleSheet('color: %s;' % colour)
    if not text:
        lb.hide()
    return lb


def tastentabelle(zeilen):
    """Tastenbelegung als zweispaltige Tabelle.

    Als eigenes Widget mit Rahmen, nicht als Fliesstext: wer im Spiel sitzt
    und wissen will, welche Taste was tut, sucht eine Zeile, keinen Absatz.
    Die Beschriftungen sind gewoehnliche QLabel und laufen damit durch
    `apply_lang` wie alles andere.
    """
    rahmen = QtWidgets.QFrame()
    rahmen.setFrameShape(QtWidgets.QFrame.StyledPanel)
    g = QtWidgets.QGridLayout(rahmen)
    g.setContentsMargins(10, 8, 10, 8)
    g.setHorizontalSpacing(14)
    g.setVerticalSpacing(3)
    for i, (taste, was) in enumerate(zeilen):
        lb = QtWidgets.QLabel(taste)
        f = lb.font()
        f.setBold(True)
        lb.setFont(f)
        g.addWidget(lb, i, 0)
        g.addWidget(QtWidgets.QLabel(was), i, 1)
    g.setColumnStretch(1, 1)
    return rahmen


def head(text):
    lb = QtWidgets.QLabel(text)
    f = lb.font()
    f.setBold(True)
    f.setPointSize(f.pointSize() + 1)
    lb.setFont(f)
    return lb


class WheelGuard(QtCore.QObject):
    """Verwirft Radereignisse auf Auswahlfeldern ohne Fokus.

    Haengt an der Anwendung, damit auch spaeter erzeugte Felder erfasst sind
    (die shadPS4-Seite baut ihre erst beim Laden der Datei). Ohne Fokus wird
    das Ereignis abgelehnt und wandert zur Rollflaeche weiter -- was der Nutzer
    ohnehin wollte. Nach einem Klick hat das Feld den Fokus, dann wirkt das Rad
    wie gewohnt.
    """

    WATCHED = (QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox,
               QtWidgets.QSlider)

    def eventFilter(self, obj, ev):
        if (ev.type() == QtCore.QEvent.Wheel
                and isinstance(obj, self.WATCHED)
                and not obj.hasFocus()):
            ev.ignore()
            return True          # verschluckt -- die Rollflaeche bekommt es
        return super().eventFilter(obj, ev)


class Page(QtWidgets.QWidget):
    """Eine Seite mit senkrechtem Layout und einer Statuszeile unten.

    Die Seite lebt in einer QScrollArea (siehe Main). Sie darf also beliebig
    hoch werden -- was nicht ins Fenster passt, wird gerollt statt
    abgeschnitten. Bei 200 % Zoom ist das keine Feinheit, sondern der
    Unterschied zwischen bedienbar und nicht.
    """

    TITLE = '?'
    # Baeume und Tabellen bekommen ein Mindestmass. Im Rollbereich wuerden sie
    # sonst auf ihre kleinste sinnvolle Groesse zusammenfallen.
    LIST_MIN_H = 220

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.box = QtWidgets.QVBoxLayout(self)
        self.box.setContentsMargins(14, 12, 14, 12)
        self.box.setSpacing(6)
        self.status = QtWidgets.QLabel('')
        self.status.setWordWrap(True)
        self.build()
        # findChildren nimmt in PySide6 genau EINEN Typ, kein Tupel.
        for kind in (QtWidgets.QTreeWidget, QtWidgets.QTableWidget,
                     QtWidgets.QScrollArea):
            for w in self.findChildren(kind):
                w.setMinimumHeight(self.LIST_MIN_H)
        self.box.addStretch(1)
        self.box.addWidget(self.status)

    def build(self):
        raise NotImplementedError

    def say(self, text, ok=None):
        colour = '#666' if ok is None else ('#0a0' if ok else '#c00')
        self.status.setStyleSheet('color: %s;' % colour)
        self.status.setText(text)

    def refresh(self):
        """Wird im Takt gerufen, solange die Seite sichtbar ist."""


# ------------------------------------------------------------------ Spieler
class PlayerPage(Page):
    # Schrittweiten fuer die Schwebehoehe, aus hovergui uebernommen. Ohne sie
    # kam man nur in 0.05er-Schritten voran, und der Takt rechnete fest mit
    # 0.25 -- zwei verschiedene Schrittweiten fuer dieselbe Zahl.
    STEPS = [0.05, 0.1, 0.25, 0.5, 1.0, 2.0]
    DEF_STEP = 0.25
    """Schweben, Warp, Teleport -- alles ueber ptplayer.Holder."""

    TITLE = 'Player'

    def build(self):
        self.box.addWidget(head('Hover'))
        self.box.addWidget(note('Holds the player at a fixed height while x and z stay free, so'
                                ' you can still walk. Pad: L3 toggles it, D-pad up and down'
                                ' change the height, left and right change the step.'))

        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('height'))
        self.sp_h = QtWidgets.QDoubleSpinBox()
        self.sp_h.setRange(-50.0, 50.0)
        self.sp_h.setSingleStep(0.05)
        self.sp_h.setDecimals(2)
        self.sp_h.setValue(self.app.holder.height)
        self.sp_h.valueChanged.connect(self._height)
        r.addWidget(self.sp_h)
        r.addWidget(QtWidgets.QLabel('m'))
        r.addWidget(QtWidgets.QLabel('step'))
        self.cmb_step = QtWidgets.QComboBox()
        for s in self.STEPS:
            self.cmb_step.addItem('%.2f m' % s, s)
        self.cmb_step.setCurrentIndex(self.STEPS.index(self.DEF_STEP))
        self.cmb_step.currentIndexChanged.connect(self._step_changed)
        r.addWidget(self.cmb_step)
        self.bt_hover = QtWidgets.QPushButton('Start hovering')
        self.bt_hover.clicked.connect(self._toggle)
        r.addWidget(self.bt_hover)
        r.addStretch(1)
        self.box.addLayout(r)
        self.sp_h.setSingleStep(self.DEF_STEP)

        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('hold rate'))
        self.cmb_rate = QtWidgets.QComboBox()
        for hz, txt in ((60, '60 Hz  (once per frame)'),
                        (120, '120 Hz  (twice)'),
                        (180, '180 Hz  (three times)'),
                        (240, '240 Hz  (four times)'),
                        (0, 'unthrottled')):
            self.cmb_rate.addItem(txt, hz)
        self.cmb_rate.setCurrentIndex(1)
        self.cmb_rate.currentIndexChanged.connect(self._rate)
        r.addWidget(self.cmb_rate)
        r.addStretch(1)
        self.box.addLayout(r)
        self.box.addWidget(note('How often the height gets rewritten. It affects hovering only.'))
        self.box.addWidget(note(''))

        self.box.addWidget(hline())
        self.box.addWidget(head('Warp'))
        self.box.addWidget(note('Moves you one step in the direction you are looking - through'
                                ' doors and walls. Pad: hold X, then D-pad up and down for'
                                ' forward and back, left and right to strafe.'))
        self.box.addWidget(note('Turn Hover on first. Warping out of bounds without it means falling, and falling gets you killed by Lisa.', '#a00'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('step'))
        self.sp_w = QtWidgets.QDoubleSpinBox()
        # Der Flur ist rund 32 m lang (aus den Weltlagen seiner Fallen
        # gemessen). 20 m sind mehr als jedes Hindernis und weniger als
        # ein Sprung aus dem Level.
        self.sp_w.setRange(0.05, 20.0)
        self.sp_w.setSingleStep(0.05)
        self.sp_w.setDecimals(2)
        self.sp_w.setValue(1.0)
        r.addWidget(self.sp_w)
        r.addWidget(QtWidgets.QLabel('m'))
        for label, which, sign in (('forward', 'fwd', +1),
                                   ('back', 'fwd', -1),
                                   ('left', 'side', -1),
                                   ('right', 'side', +1)):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda _=False, w=which, s=sign:
                              self._warp(w, s))
            r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self.box.addWidget(note(''))

        self.box.addWidget(hline())
        self.box.addWidget(head('Position'))
        self.box.addWidget(note(
            'Remembers places you have stood and jumps back to them. Pad: L1'
            ' saves where you are, R1 cycles through the saved ones.'))
        self.lb_pos = QtWidgets.QLabel('-')
        self.lb_pos.setStyleSheet('font-family: Consolas, monospace;')
        self.box.addWidget(self.lb_pos)
        r = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton('Save spot')
        b.clicked.connect(self._save)
        r.addWidget(b)
        self.cmb_spot = QtWidgets.QComboBox()
        self.cmb_spot.setMinimumWidth(220)
        r.addWidget(self.cmb_spot)
        b = QtWidgets.QPushButton('Go')
        b.clicked.connect(self._go)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)

        # ------------------------------------------------------ Tempo
        self.box.addWidget(hline())
        self.box.addWidget(head('Walk speed'))
        self.box.addWidget(note('Drag and it acts at once. Pad: L2 slower, R2 faster.'))
        r = QtWidgets.QHBoxLayout()
        self.sl_walk = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_walk.setRange(10, 1000)          # 0.10 .. 10.00, in 1/100
        self.sl_walk.setValue(100)
        self.sl_walk.valueChanged.connect(self._walk)
        r.addWidget(self.sl_walk, 1)
        self.lb_walk = QtWidgets.QLabel('1.00 x')
        self.lb_walk.setMinimumWidth(64)
        r.addWidget(self.lb_walk)
        b = QtWidgets.QPushButton('Reset')
        b.clicked.connect(lambda: self._set_walk(1.0))
        r.addWidget(b)
        self.box.addLayout(r)
        self.cb_walkkeep = QtWidgets.QCheckBox('keep it across room changes')
        self.cb_walkkeep.setChecked(True)
        self.box.addWidget(self.cb_walkkeep)

        # Taschenlampe und Belichtung stehen auf der Seite "Light".

        # -------------------------------------------------- Verbindung
        self.box.addWidget(hline())
        self.box.addWidget(head('Connection'))
        self.lb_paths_warn = QtWidgets.QLabel('')
        self.lb_paths_warn.setWordWrap(True)
        self.lb_paths_warn.setStyleSheet('color: #c00;')
        self.box.addWidget(self.lb_paths_warn)
        r = QtWidgets.QHBoxLayout()
        # Der meistgebrauchte Knopf der ganzen Oberflaeche -- entsprechend
        # gross. Vorher ging er zwischen den anderen unter.
        self.bt_start = QtWidgets.QPushButton('Start emulator + game')
        self.bt_start.clicked.connect(self._start_game)
        f = self.bt_start.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.1)
        self.bt_start.setFont(f)
        self.bt_start.setMinimumHeight(32)
        self.bt_start.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                    QtWidgets.QSizePolicy.Fixed)
        # Farbig, aber in mass: die Flaeche traegt die Aufmerksamkeit, die
        # Groesse bleibt moderat. Es ist der meistgebrauchte Knopf der
        # Oberflaeche und ging zwischen den anderen unter.
        self.bt_start.setStyleSheet(
            'QPushButton { background: #2a6fb5; color: white;'
            ' border: 1px solid #1d4f80; border-radius: 3px;'
            ' padding: 5px 14px; }'
            'QPushButton:hover { background: #3781cc; }'
            'QPushButton:pressed { background: #1d4f80; }'
            'QPushButton:disabled { background: #9aa6b0; color: #eee; }')
        r.addWidget(self.bt_start, 1)
        b = QtWidgets.QPushButton('Reconnect')
        b.clicked.connect(self._reconnect)
        r.addWidget(b)
        self.box.addLayout(r)
        self.cb_auto = QtWidgets.QCheckBox(
            'connect by itself, and reconnect after a game restart')
        self.cb_auto.setChecked(True)
        self.box.addWidget(self.cb_auto)
        self.box.addWidget(note('Connecting scans the process memory and runs in the'
                                ' background, so the window stays usable.',
                                '#888'))

        self._walk_re = 0

    # -- Aktionen
    def _height(self, v):
        self.app.holder.height = float(v)

    def hover_step(self):
        """Die eingestellte Schrittweite in Metern."""
        s = self.cmb_step.currentData()
        return self.DEF_STEP if s is None else float(s)

    def hover_step_cycle(self, d):
        """Schrittweite eine Stufe weiter -- fuers Steuerkreuz.

        Ohne Umlauf: am Ende stehenbleiben ist beim Blindbedienen mit dem Pad
        angenehmer, als von 2 m auf 0,05 m zu springen.
        """
        i = max(0, min(self.cmb_step.count() - 1,
                       self.cmb_step.currentIndex() + d))
        if i != self.cmb_step.currentIndex():
            self.cmb_step.setCurrentIndex(i)
        self.say('step %.2f m' % self.hover_step())

    def _step_changed(self):
        # Das Drehfeld folgt der Auswahl, sonst haette dasselbe Feld je nach
        # Bedienweg zwei verschiedene Schrittweiten.
        self.sp_h.setSingleStep(self.hover_step())

    def _toggle(self):
        """Schweben umschalten -- SOFORT, ohne auf die Verbindung zu warten.

        Frueher brach das hier ab, wenn `attach()` False lieferte. Seit das
        Verbinden im Hintergrund laeuft, liefert es beim ersten Druck immer
        False -- der Knopf tat also nichts. Die Schreibschleife wartet ohnehin
        auf die Verbindung.
        """
        h = self.app.holder
        on = h.hovering(not h.hovering())
        self.bt_hover.setText('Stop hovering' if on else 'Start hovering')
        if not on:
            self.say('hovering off')
            return
        if h.alive():
            self.say('hovering at %.2f m' % h.height, True)
        else:
            self.app.attach()
            self.say('hovering armed at %.2f m - starts as soon as the game'
                     ' is connected' % h.height, True)

    def _warp(self, which, sign):
        if not self.app.attach():
            return
        # Links/rechts waren vertauscht: +1 entlang der Seitenachse zeigt
        # nach LINKS (im Spiel gemessen). Das Vorzeichen steht in ptplayer,
        # damit es nicht in jedem Fenster neu geraten wird.
        H = ptplayer.Holder
        if which == 'fwd':
            row, s = H.ROW_FWD, sign
        else:
            row, s = H.ROW_SIDE, sign * H.SIDE_RIGHT
        at = self.app.holder.warp(self.sp_w.value(), row, s)
        if at is None:
            self.say('no warp - not attached', False)
            return
        self.say('%s %.2f m -> (%.2f, %.2f, %.2f)'
                 % (which, self.sp_w.value(), at[0], at[1], at[2]), True)

    def _save(self):
        p = self.app.holder.pos
        if not any(p):
            self.say('no position yet - attach first', False)
            return
        self.app.spots.append(tuple(p))
        self.cmb_spot.addItem('%d.  (%.2f, %.2f, %.2f)'
                              % (len(self.app.spots), p[0], p[1], p[2]))
        self.cmb_spot.setCurrentIndex(len(self.app.spots) - 1)
        self.say('spot %d saved' % len(self.app.spots), True)

    def _go(self):
        i = self.cmb_spot.currentIndex()
        if i < 0 or i >= len(self.app.spots):
            self.say('no spot selected', False)
            return
        if self.app.holder.teleport(self.app.spots[i]):
            self.say('jumped to spot %d' % (i + 1), True)
        else:
            self.say('teleport failed - not attached', False)

    # -- Tempo
    WALK_STEP = 0.25          # je Trigger-Druck, wie im alten Werkzeug

    def hover_toggle(self):
        """Schweben an/aus -- vom Knopf UND von L3 am Pad."""
        self._toggle()

    def walk_bump(self, sign):
        """Tempo um einen Schritt (L2/R2). Grenzen wie der Regler."""
        v = max(0.10, min(10.0, self._walk_value() + sign * self.WALK_STEP))
        self._set_walk(v)

    def spot_save(self):
        self._save()

    def spot_cycle(self):
        """R1 geht reihum durch die gemerkten Spots.

        Reihum statt immer zum letzten: mit mehreren Plaetzen kommt man so
        ohne Maus ueberall hin, und bei einem einzigen verhaelt es sich wie
        ein einfaches "zurueck dorthin".
        """
        n = self.cmb_spot.count()
        if not n:
            self.say('no spots saved yet - press L1 in game', False)
            return
        self.cmb_spot.setCurrentIndex((self.cmb_spot.currentIndex() + 1) % n)
        self._go()

    def _walk_value(self):
        return round(self.sl_walk.value() / 100.0, 2)

    def _set_walk(self, f):
        self.sl_walk.setValue(int(round(f * 100)))

    def _walk(self):
        f = self._walk_value()
        self.lb_walk.setText('%.2f x' % f)
        top, at = self.app.holder.walk_set(f)
        if at is None:
            self.say('walk block not found - is a level loaded?', False)
            return
        self.say('%.2f x   front max %.2f   @0x%x' % (f, top, at), True)


    # -- Verbindung
    def _reconnect(self):
        self.app.holder.detach()
        if self.app.holder.attach():
            self.say(self.app.holder.detail, True)
        else:
            self.say('%s  %s' % (self.app.holder.status,
                                 self.app.holder.detail), False)

    def _launch(self, exe, env, what):
        """Emulator starten. Gemeinsam fuer beide Knoepfe."""
        if ptmem.find_pid():
            self.say('P.T. is already running')
            return
        for path, name in ((exe, os.path.basename(exe)),
                           (ptpaths.EBOOT, 'eboot.bin')):
            if not os.path.exists(path):
                self.say('%s not found - check the paths in Tools' % name,
                         False)
                return
        try:
            subprocess.Popen([exe, '-g', ptpaths.EBOOT], cwd=ptpaths.SHAD,
                             env=env)
        except Exception as ex:
            self.say('could not start: %s' % ex, False)
            return
        # Der Emulator braucht bis zu einer Minute, bis der Spielerzeiger
        # steht. Nicht sofort verbinden, sondern es dem Takt ueberlassen.
        self.app.autohook_until = time.monotonic() + 60.0
        self.say('started %s - hooking up for the next 60 s' % what, True)

    def _start_game(self):
        if ptmem.find_pid():
            self.say('P.T. is already running')
            return
        # PT_CLEAR ausdruecklich entfernen. Das Werkzeug setzt es nicht
        # mehr -- der experimentelle Build ist raus --, aber es koennte aus
        # einer Shell stammen, und die normale Exe kennt den Schalter nicht.
        env = dict(os.environ)
        env.pop('PT_CLEAR', None)
        self._launch(ptpaths.EXE, env, 'shadPS4')

    def _rate(self, i):
        hz = self.cmb_rate.itemData(i)
        self.app.holder.rate = int(hz or 0)
        self.say('hover hold rate %s - nothing else uses it'
                 % ('unthrottled' if not hz else '%d Hz' % hz))

    # -- Nachziehen, im Takt
    def keep(self):
        """Das Tempo nachziehen.

        Beides setzt das Spiel bei jedem Raumwechsel auf seine eigenen Werte
        zurueck. Geschrieben wird nur, was abweicht, und ausschliesslich ueber
        die Zeigerkette -- eine Bytesuche hat hier nichts zu suchen.
        """
        if self.cb_walkkeep.isChecked():
            f = self._walk_value()
            if abs(f - ptplayer.Holder.WALK_DEFAULT) > 0.005:
                cur = self.app.holder.walk_get()
                if cur is not None and abs(cur - f) > 0.005:
                    if self.app.holder.walk_set(f)[1] is not None:
                        self._walk_re += 1
                        self.say('%.2f x   re-applied %d x after room changes'
                                 % (f, self._walk_re), True)

    def refresh(self):
        # Fehlende Pfade dort melden, wo die Startknoepfe sitzen -- wer auf
        # "Start" drueckt, soll es vorher wissen und nicht danach.
        if self.app._tick % 32 == 0:
            miss = []
            if not os.path.isfile(ptpaths.EXE):
                miss.append('shadPS4.exe')
            if not os.path.isfile(ptpaths.EBOOT):
                miss.append('eboot.bin')
            self.lb_paths_warn.setText(
                ('%s not found - set the paths on the Tools page.'
                 % ' and '.join(miss)) if miss else '')
        want = ('Stop hovering' if self.app.holder.hovering()
                else 'Start hovering')
        # Der Knopftext folgt dem Zustand, nicht umgekehrt: L3 am Pad schaltet
        # dasselbe, und dann darf der Knopf nicht das Gegenteil behaupten.
        if self.bt_hover.property('i18n_orig') != want:
            self.bt_hover.setProperty('i18n_orig', want)
            self.bt_hover.setText(tr(want, getattr(self.app, '_lang', 'en')))
        p = self.app.holder.pos
        self.lb_pos.setText('x %8.2f    y %7.2f    z %8.2f   -  %.2f m/s'
                            % (p[0], p[1], p[2], self.app.holder.hspeed))


# ---------------------------------------------------------------- Wo bin ich
class WherePage(Page):
    """Ebene, Level und was hinter der naechsten Tuer liegt."""

    TITLE = 'Location'

    def build(self):
        self.box.addWidget(head('Where am I'))
        self.box.addWidget(note('Shows which loop you are in and which one lies behind the next'
                                ' door.'))
        self.lb_here = QtWidgets.QLabel('-')
        f = self.lb_here.font()
        f.setPointSize(f.pointSize() + 2)
        self.lb_here.setFont(f)
        self.box.addWidget(self.lb_here)
        self.lb_next = QtWidgets.QLabel('-')
        self.box.addWidget(self.lb_next)

        self.box.addWidget(hline())
        self.box.addWidget(head('Send me to a loop'))
        self.box.addWidget(note('Sets the loop you land in. Takes effect when you walk through'
                                ' the start room door.'))
        self.box.addWidget(note('Can crash the emulator - that has happened. Save your progress'
                                ' first.',
                                '#a00'))
        r = QtWidgets.QHBoxLayout()
        self.cmb_floor = QtWidgets.QComboBox()
        self.cmb_floor.setMinimumWidth(140)
        r.addWidget(self.cmb_floor)
        b = QtWidgets.QPushButton('Set')
        b.clicked.connect(self._set)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self._where = None
        self._where_pid = None
        self._filled = False

    def _attach(self):
        """Das gemerkte `Where` -- aber nur, wenn es zum LAUFENDEN Spiel gehoert.

        Ohne die Pruefung auf die Prozessnummer haengt die Seite nach einem
        Emulator-Neustart weiter am toten Prozess: das gemerkte Objekt traegt
        einen ungueltigen Zeiger und eine Basisadresse, die es nicht mehr
        gibt, und die Anzeige bleibt leer. Jedes Mal neu anzuhaengen waere
        aber auch falsch -- der Aufbau kostet einen Suchlauf, und der gehoert
        nicht in den Takt.
        """
        # Die Prozessnummer vom Holder, NICHT ueber ptmem.find_pid: das
        # startet `tasklist` und kostet gemessen 269 ms -- bei einem Takt von
        # 33 ms stand das Fenster, solange diese Seite offen war. Der Holder
        # ermittelt sie beim Verbinden ohnehin und gibt sie nach einem
        # Emulator-Neustart als neue heraus, die Neustarterkennung bleibt also
        # erhalten.
        pid = self.app.holder.pid()
        if not pid:
            self._where = None
            self._where_pid = None
            return None
        if self._where is not None and self._where_pid == pid:
            return self._where
        try:
            w = ptloop.Where()
        except Exception:
            self._where = None
            self._where_pid = None
            return None
        if not getattr(w, 'base', None):
            return None
        self._where = w
        self._where_pid = pid
        # Die Etagenliste haengt am selben Objekt und muss mit neu gefuellt
        # werden, sonst stehen dort die Namen des alten Laufs.
        if self._filled:
            self.cmb_floor.clear()
            self._filled = False
        return w

    def _set(self):
        w = self._attach()
        name = self.cmb_floor.currentText()
        if w is None or not name:
            self.say('not attached', False)
            return
        if w.set_floor(name):
            self.say('set to %s - now walk through the door' % name, True)
        else:
            self.say('could not set %s' % name, False)

    def refresh(self):
        w = self._attach()
        if w is None:
            self.lb_here.setText('game not running')
            self.lb_next.setText('')
            return
        # `text()` baut die Zeile schon fertig -- Level, Schleife, Index und
        # die vorgeladene naechste Stage. Nachbauen hiesse, dieselbe Logik
        # zweimal zu pflegen.
        try:
            self.lb_here.setText(w.text())
        except Exception:
            self.lb_here.setText('pointer chain failed')
            return
        try:
            self.lb_next.setText(w.next_text() or '')
        except Exception:
            self.lb_next.setText('')
        if not self._filled:
            # table() liefert Namen, teils None, wenn ein Hash unbekannt ist.
            try:
                names = [n for n in w.table() if n]
            except Exception:
                names = []
            if names:
                self.cmb_floor.addItems(names)
                self._filled = True


# ------------------------------------------------------------------ Objekte
class ObjectsPage(Page):
    """Die 143 StaticModel ein- und ausblenden, ohne Neubau."""

    TITLE = 'Objects'

    def build(self):
        self.box.addWidget(head('Hidden objects'))
        self.box.addWidget(note('Switches the 62 objects P.T. ships hidden. Acts at once, no'
                                ' rebuild needed.'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('category'))
        self.cmb_cat = QtWidgets.QComboBox()
        self.cmb_cat.setMinimumWidth(120)
        self.cmb_cat.currentTextChanged.connect(lambda _: self._fill())
        r.addWidget(self.cmb_cat)
        r.addWidget(QtWidgets.QLabel('filter'))
        self.ed_filter = QtWidgets.QLineEdit()
        self.ed_filter.textChanged.connect(lambda _: self._fill())
        r.addWidget(self.ed_filter)
        self.cb_hidden = QtWidgets.QCheckBox('hidden only')
        self.cb_hidden.setChecked(True)
        self.cb_hidden.toggled.connect(lambda _: self._fill())
        r.addWidget(self.cb_hidden)
        self.box.addLayout(r)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['object', 'what it is'])
        self.tree.setColumnWidth(0, 300)
        self.tree.setRootIsDecorated(True)
        self.box.addWidget(self.tree, 1)

        r = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton('Apply live')
        b.clicked.connect(self._apply)
        r.addWidget(b)
        self.cb_keep = QtWidgets.QCheckBox('keep across loops')
        self.cb_keep.setChecked(True)
        r.addWidget(self.cb_keep)
        b = QtWidgets.QPushButton('Game default')
        b.clicked.connect(self._reset)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self._rows = []
        self._orig = {}
        self._want = {}
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        try:
            cur = ptobjects.scan(psarc.Psarc(ptpaths.PSARC))
            org = ptobjects.scan(psarc.Psarc(ptpaths.ORIG))
        except Exception as ex:
            self.say('cannot read the archive: %s' % ex, False)
            return
        self._rows = cur
        self._orig = {r['short']: r['visible'] for r in org}
        self._want = {r['short']: r['visible'] for r in cur}
        cats = sorted({r.get('cat') or '?' for r in cur})
        self.cmb_cat.blockSignals(True)
        self.cmb_cat.addItems(['- all -'] + cats)
        self.cmb_cat.blockSignals(False)
        self._loaded = True
        self._fill()

    def _fill(self):
        if not self._loaded:
            return
        pat = self.ed_filter.text().strip().lower()
        cat = self.cmb_cat.currentText()
        rows = [r for r in self._rows
                if (not pat or pat in r['short'].lower()
                    or pat in r['note'].lower())
                and (cat in ('', '- all -') or (r.get('cat') or '?') == cat)
                # Gegen das ORIGINAL pruefen, nicht gegen den Haken: sonst
                # verschwindet ein Objekt aus der Liste, sobald man es
                # einschaltet, und ist nicht mehr abwaehlbar.
                and (not self.cb_hidden.isChecked()
                     or not self._orig.get(r['short'], r['visible']))]
        rows.sort(key=lambda r: ((r.get('cat') or '?'), r['group'], r['short']))
        self.tree.clear()
        by = {}
        for r in rows:
            key = r.get('cat') or '?'
            if key not in by:
                top = QtWidgets.QTreeWidgetItem(self.tree, [key, ''])
                fnt = top.font(0)
                fnt.setBold(True)
                top.setFont(0, fnt)
                top.setExpanded(True)
                by[key] = top
            it = QtWidgets.QTreeWidgetItem(by[key], [r['short'], r['note']])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(0, QtCore.Qt.Checked
                             if self._want.get(r['short']) else
                             QtCore.Qt.Unchecked)
            it.setData(0, QtCore.Qt.UserRole, r['short'])
        for key, top in by.items():
            top.setText(0, '%s  (%d)' % (key, top.childCount()))
        self.say('%d object(s) listed' % len(rows))

    def _collect(self):
        """Die Haken einsammeln. Was nicht in der Liste steht, bleibt wie es
        war -- ein Filter darf nichts abschalten, was man nicht sieht."""
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            short = item.data(0, QtCore.Qt.UserRole)
            if short:
                self._want[short] = (item.checkState(0) == QtCore.Qt.Checked)
            it += 1
        return dict(self._want)

    def _apply(self):
        want = self._collect()
        sess = self.app.vis()
        if sess is None:
            self.say('shadPS4 is not running, or no level loaded', False)
            return
        todo = {k: v for k, v in want.items()
                if any(r['short'] == k and sess.needs(r, v) for r in sess.rows)}
        if not todo:
            self.say('already as ticked - nothing to write')
            return
        n = sess.apply(todo)
        self.app.vis_keep = want if self.cb_keep.isChecked() else None
        self.say('%d object(s) written live, %d spot(s) in your hallway copy'
                 % (len(todo), n), True)

    def _reset(self):
        sess = self.app.vis()
        if sess is None:
            self.say('shadPS4 is not running', False)
            return
        n = sess.apply(dict(self._orig))
        self._want = dict(self._orig)
        self.app.vis_keep = None
        self._fill()
        self.say('%d spots back to the game default' % n, True)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._load()


# -------------------------------------------------------------------- Tueren
class DoorsPage(Page):
    """Tuerzustand lesen und das Schloss loesen."""

    TITLE = 'Doors'

    def build(self):
        self.box.addWidget(head('Doors'))
        self.box.addWidget(note('Switches a door between its closed and its open model, and'
                                ' clears the lock the game checks before it rattles the handle.'))
        self.box.addWidget(note('The rattle stops and the door shows open, but you still cannot'
                                ' walk through: collision is a separate asset and no visibility'
                                ' switch reaches it. Use Warp to get past a door.',
                                '#a60'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('door'))
        self.cmb = QtWidgets.QComboBox()
        self.cmb.addItems([t for t, _, _ in ptdoor.PAIRS] + ['all doors'])
        self.cmb.setMinimumWidth(120)
        r.addWidget(self.cmb)
        for label, opening in (('Open', True), ('Close', False)):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda _=False, o=opening: self._set(o))
            r.addWidget(b)
        b = QtWidgets.QPushButton('Read state')
        b.clicked.connect(self._state)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self.tbl = QtWidgets.QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(['door', 'copy', 'state', 'where'])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.box.addWidget(self.tbl, 1)

    def _which(self):
        t = self.cmb.currentText()
        return None if t == 'all doors' else t

    def _set(self, opening):
        sess = self.app.vis()
        if sess is None:
            self.say('shadPS4 is not running, or no level loaded', False)
            return
        want = ptdoor.wanted(self._which(), opening, sess)
        msgs = []
        ptdoor.apply(sess, want, log=lambda s: msgs.append(s.strip()))
        self.say('%s %s - %s' % ('opened' if opening else 'closed',
                                 self._which() or 'all doors',
                                 '; '.join(msgs)[:160]), True)
        self._state()

    def _state(self):
        sess = self.app.vis()
        if sess is None:
            self.say('shadPS4 is not running', False)
            return
        self.tbl.setRowCount(0)
        for tag, closed, _open in ptdoor.PAIRS:
            hits = [r for r in sess.rows if r['short'] == closed]
            for i, r in enumerate(hits):
                # Zu ist eine Tuer, wenn die GESCHLOSSENE Variante ihre
                # Geometrie an hat -- genau darauf sieht trap_DoorGacha*.
                shut = bool(sess.state(r)['isgeom'])
                pos = r.get('pos')
                row = self.tbl.rowCount()
                self.tbl.insertRow(row)
                for c, txt in enumerate((tag, '#%d' % i,
                                         'SHUT' if shut else 'open',
                                         '(%.1f, %.1f, %.1f)' % pos
                                         if pos else '')):
                    self.tbl.setItem(row, c, QtWidgets.QTableWidgetItem(txt))


# ------------------------------------------------------------------- Bauen
class BuildPage(Page):
    """Was erst beim naechsten Spielstart wirkt -- das Archiv neu bauen.

    Gebaut wird immer gegen `chunk1.orig.psarc`, das unberuehrte Original.
    Deshalb muss JEDE Abweichung mitgegeben werden, auch die aus einem
    frueheren Bau -- sonst faellt sie still wieder heraus.
    """

    TITLE = 'Build'

    def build(self):
        self.box.addWidget(head('What is in the archive now'))
        self.box.addWidget(note('What chunk1.psarc currently holds, read from the file itself.'))
        self.lb_state = QtWidgets.QLabel('-')
        self.lb_state.setWordWrap(True)
        self.lb_state.setStyleSheet('font-family: Consolas, monospace;')
        self.box.addWidget(self.lb_state)
        r = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton('Re-read')
        b.clicked.connect(self._state)
        r.addWidget(b)
        b = QtWidgets.QPushButton('Take these settings')
        b.clicked.connect(self._adopt)
        r.addWidget(b)
        b = QtWidgets.QPushButton('Restore original')
        b.clicked.connect(self._restore)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self.box.addWidget(note('Restore copies the shipped archive back, byte for byte. That'
                                ' is not the same as building "vanilla".',
                                '#888'))

        self.box.addWidget(hline())
        self.box.addWidget(head('Behind the start room door'))
        self.box.addWidget(note('Rewrites chunk1.psarc and takes effect on the next start.'
                                ' Close the game first - it holds the archive open.'))
        self.box.addWidget(note('This part is dependable.',
                                '#0a0'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('stage'))
        self.cmb_stage = QtWidgets.QComboBox()
        for key, label in STAGE_LABELS:
            self.cmb_stage.addItem(label, key)
        self.cmb_stage.setMinimumWidth(180)
        r.addWidget(self.cmb_stage)
        r.addStretch(1)
        self.box.addLayout(r)

        self.box.addWidget(hline())
        self.box.addWidget(head('Start on a loop'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('floor'))
        self.cmb_floor = QtWidgets.QComboBox()
        self.cmb_floor.addItem('- leave it alone -', '')
        # Die Liste kommt aus luaprobe, nicht aus FLOOR_EVENTS: luaprobe
        # akzeptiert zusaetzlich "ending", und zwei Listen derselben Sache
        # laufen auseinander.
        for name in luaprobe.FLOORS:
            self.cmb_floor.addItem(name, name)
        r.addWidget(self.cmb_floor)
        r.addStretch(1)
        self.box.addLayout(r)
        self.box.addWidget(note('EXPERIMENTAL: changing the loop relocates gimmicks. It has'
                                ' left the start room door stuck shut, and it can crash the'
                                ' emulator.',
                                '#a00'))
        self.box.addWidget(note('Only meaningful with the hallway behind the door: the mazes'
                                ' carry f110 alone, and the start room and the ending carry no'
                                ' loops at all.'))

        self.cb_win = QtWidgets.QCheckBox('arm the ending trap on every floor')
        self.box.addWidget(self.cb_win)
        self.box.addWidget(note('Arms the ending trap on every floor. Walk into the box in the'
                                ' hallway and the real ending plays. Needs the hallway behind'
                                ' the door.'))

        self.cb_lighton = QtWidgets.QCheckBox(
            'give me the flashlight (needed on a fresh save)')
        self.cb_lighton.setChecked(True)
        self.box.addWidget(self.cb_lighton)

        self.box.addWidget(hline())
        self.box.addWidget(head('Flashlight reach'))
        self.box.addWidget(note(
            'Range and cone of the torch. These cannot be changed while the'
            ' game runs: the cone body is built once when the light is created,'
            ' which is why a hundredfold brightness still stops at the same'
            ' distance. Only the archive reaches them.'))
        self.box.addWidget(note(
            'The game ships 5 metres with a 78 degree cone and a 30 degree'
            ' core. Forty metres lights a whole corridor and has been confirmed'
            ' in game. Widening the angles changes the shape noticeably, so'
            ' change them one at a time.', '#888'))
        self.box.addWidget(note(
            'Range alone is not enough: the 100 lumen the game ships are tuned'
            ' for five metres and are too dim to see anything at forty. Raise'
            ' brightness on the Light page as well, or the longer range looks'
            ' like nothing happened.', '#a60'))
        r = QtWidgets.QHBoxLayout()
        self.light_sp = {}
        for name, lo, hi, step in (('outerRange', 0.1, 200.0, 1.0),
                                   ('umbraAngle', 1.0, 179.0, 1.0),
                                   ('penumbraAngle', 1.0, 179.0, 1.0)):
            r.addWidget(QtWidgets.QLabel(name))
            e = QtWidgets.QDoubleSpinBox()
            e.setRange(lo, hi)
            e.setSingleStep(step)
            e.setDecimals(1)
            e.setValue(dict(ptstate.LIGHT_FIELDS)[name])
            r.addWidget(e)
            self.light_sp[name] = e
        b = QtWidgets.QPushButton('reset')
        b.clicked.connect(self._light_reset_build)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)

        self.box.addWidget(hline())
        self.box.addWidget(head('Spawn a gimmick'))
        self.box.addWidget(note('Of eight gimmick types only one shows up - P.T. picks it by'
                                ' progress, not by this setting.'))
        self.box.addWidget(note(
            'Only Baby is known to appear. The others come from the same parts'
            ' files; whether they show up is unclear.', '#a60'))
        r = QtWidgets.QHBoxLayout()
        self.cb_baby = QtWidgets.QCheckBox('put it in the start room')
        self.cb_baby.toggled.connect(self._baby)
        r.addWidget(self.cb_baby)
        r.addWidget(QtWidgets.QLabel('type'))
        self.cmb_gimmick = QtWidgets.QComboBox()
        # Die Liste kommt aus spawn, nicht aus einer abgetippten Aufzaehlung:
        # ein abgetipptes 'baby' hat den Bau gerade erst scheitern lassen.
        for name in tuple(spawn.PARTS) + tuple(spawn.EXTRA_PARTS):
            self.cmb_gimmick.addItem(name, name)
        self.cmb_gimmick.setCurrentIndex(
            self.cmb_gimmick.findData(spawn.PARTS[1]))    # Baby als Vorauswahl
        r.addWidget(self.cmb_gimmick)
        r.addStretch(1)
        self.box.addLayout(r)
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('at x / y / z'))
        self.xyz = []
        for v in spawn.AT:
            e = QtWidgets.QDoubleSpinBox()
            e.setRange(-999.0, 999.0)
            e.setDecimals(2)
            e.setValue(v)
            r.addWidget(e)
            self.xyz.append(e)
        b = QtWidgets.QPushButton('reset')
        b.clicked.connect(lambda: self._set_xyz(spawn.AT))
        r.addWidget(b)
        b = QtWidgets.QPushButton('on table')
        b.clicked.connect(lambda: self._set_xyz(spawn.TABLE_AT))
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self.box.addWidget(note(
            'Start room:'
            '  x -2.28..2.09,  y -0.2..2.99,  z -12.95..0.'
            '  y 0 is the floor, y 3 the ceiling, y 0.8 the table top.'
            '  The player starts at (%g, %g, %g), the door is at z 0.'
            % spawn.PLAYER_AT, '#888'))

        self.box.addWidget(hline())
        self.bt_build = QtWidgets.QPushButton('Build archive')
        self.bt_build.clicked.connect(self._build)
        self.box.addWidget(self.bt_build)
        self._runner = None
        self._state()

    # -- Ist-Zustand
    def _state(self):
        """Was wirklich im Archiv steht."""
        try:
            st = ptstate.read()
        except Exception as ex:
            self.lb_state.setText('cannot read the archive: %s' % ex)
            return None
        if st.get('error') and not st.get('built'):
            self.lb_state.setText('archive: %s' % st['error'])
            return st
        when = (time.strftime('%d.%m. %H:%M', time.localtime(st['built']))
                if st.get('built') else '?')
        # Steht ueberhaupt nichts drin, ist es das unberuehrte Original --
        # das ist eine Aussage und kein Fehler, also sagt sie das auch.
        de = getattr(self.app, '_lang', 'en') == 'de'
        li = st.get('light') or {}
        licht_ab = any(li.get(n) is not None and abs(li[n] - v) > 1e-3
                       for n, v in ptstate.LIGHT_FIELDS)
        if not licht_ab and not any(st.get(k) for k in
                                    ('stage', 'floor', 'win', 'lighton',
                                     'gimmick')):
            self.lb_state.setText(
                ('unber\u00fchrtes Original  (wie ausgeliefert, %s)' if de
                 else 'untouched original  (as shipped, %s)') % when)
            return st
        # Wie bei der Zeile darueber: zusammengesetzt und mit Zeitstempel,
        # also nicht nachschlagbar -- die Sprache muss hier gefragt werden.
        w = ((lambda en, de: de) if de else (lambda en, de: en))
        bits = [w('stage %s', 'Stage %s') % (st.get('stage') or '?')]
        if st.get('floor'):
            bits.append(w('floor %s', 'Etage %s') % st['floor'])
        if st.get('win'):
            bits.append(w('ending trap ARMED', 'Ending-Falle SCHARF'))
        if st.get('lighton'):
            bits.append(w('flashlight on', 'Taschenlampe an'))
        li = st.get('light') or {}
        abw = ['%s %g' % (n, li[n]) for n, v in ptstate.LIGHT_FIELDS
               if li.get(n) is not None and abs(li[n] - v) > 1e-3]
        if abw:
            # Die Feldnamen bleiben stehen: sie heissen in
            # ShParameterTables.lua genauso.
            bits.append(w('torch ', 'Lampe ') + ', '.join(abw))
        gim = st.get('gimmick') or w('none', 'keiner')
        if st.get('at'):
            gim += w(' at (%.2f, %.2f, %.2f)',
                     ' bei (%.2f, %.2f, %.2f)') % st['at']
        bits.append(w('spawn %s', 'Spawn %s') % gim)
        self.lb_state.setText(w('built %s\n%s', 'gebaut %s\n%s')
                              % (when, '   '.join(bits)))
        return st

    def _restore(self):
        """Das unberuehrte Original zurueckkopieren.

        Mit Rueckfrage, weil der gebaute Stand dabei verloren geht -- und der
        kann eine halbe Minute Bauzeit gekostet haben.
        """
        if ptmem.find_pid():
            self.say('P.T. is running - close it first, it holds the archive'
                     ' open', False)
            return
        if not os.path.exists(ptpaths.ORIG):
            self.say('chunk1.orig.psarc not found - nothing to restore from',
                     False)
            return
        got = QtWidgets.QMessageBox.question(
            self, 'Restore original archive',
            'Copy chunk1.orig.psarc over chunk1.psarc?\n\n'
            'Everything that was built into the archive is discarded -'
            ' stage, floor, ending trap, spawn.',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if got != QtWidgets.QMessageBox.Yes:
            self.say('left alone')
            return
        try:
            shutil.copy2(ptpaths.ORIG, ptpaths.PSARC)
        except Exception as ex:
            self.say('could not restore: %s' % ex, False)
            return
        self._state()
        self.say('restored the untouched original', True)

    def relabel(self):
        """Nach einem Sprachwechsel: die zusammengebaute Zustandszeile neu."""
        self._state()

    def _adopt(self):
        """Die Bedienelemente auf den gebauten Stand stellen.

        Damit laesst sich eine einzelne Sache aendern, ohne versehentlich
        alles andere zurueckzusetzen -- der Bau schreibt immer den GANZEN
        Stand, weil er beim Original anfaengt.
        """
        st = self._state()
        if not st:
            return
        i = self.cmb_stage.findData(st.get('stage'))
        if i >= 0:
            self.cmb_stage.setCurrentIndex(i)
        i = self.cmb_floor.findData(st.get('floor') or '')
        if i >= 0:
            self.cmb_floor.setCurrentIndex(i)
        self.cb_win.setChecked(bool(st.get('win')))
        self.cb_lighton.setChecked(bool(st.get('lighton')))
        self.cb_baby.setChecked(bool(st.get('gimmick')))
        i = self.cmb_gimmick.findData(st.get('gimmick'))
        if i >= 0:
            self.cmb_gimmick.setCurrentIndex(i)
        for name, v in ptstate.LIGHT_FIELDS:
            got = (st.get('light') or {}).get(name)
            self.light_sp[name].setValue(v if got is None else got)
        if st.get('at'):
            self._set_xyz(st['at'])
        self.say('controls set to what is in the archive')

    def _light_reset_build(self):
        """Zurueck auf die Vorgaben des Spiels."""
        for name, v in ptstate.LIGHT_FIELDS:
            self.light_sp[name].setValue(v)

    def _set_xyz(self, at):
        for e, v in zip(self.xyz, at):
            e.setValue(v)

    def _baby(self, on):
        """Beim Anhaken die Koordinaten auf den Tisch stellen.

        Die Tischhoehe bleibt die Vorgabe, auch nachdem aus dem Baby eine
        Auswahl geworden ist -- fuer das Baby war sie gemeint, und fuer die
        uebrigen ist ohnehin kein Platz belegt, an dem sie besser stuenden.
        Ueberschreiben laesst es sich weiter.
        """
        if on:
            self._set_xyz(spawn.TABLE_AT)

    def _build(self):
        if self._runner is not None and self._runner.isRunning():
            return
        if ptmem.find_pid():
            self.say('P.T. is running - close it first, it holds the'
                     ' archive open', False)
            return
        stage = self.cmb_stage.currentData()
        want = self.app.obj_wanted()
        forced = ''
        # Die versteckten Objekte liegen alle im FLUR. Mit umgeleiteter Tuer
        # kommt man dort nie hin, also waere der Bau wirkungslos.
        if want and stage != 'vanilla':
            stage, forced = 'vanilla', '  (stage forced to vanilla)'
        cmd = ['--stage', stage]
        if self.cb_win.isChecked():
            cmd += ['--winclear']
        if self.cb_lighton.isChecked():
            cmd += ['--lighton']
        floor = self.cmb_floor.currentData()
        warn = ''
        if floor:
            cmd += ['--floor', floor]
            # Nicht verbieten -- es ist ein Playground. Aber sagen, dass die
            # Etage dort kaum etwas ausloest: ihre Wirkungen stehen in der
            # Level-fox2, und ausserhalb des Flurs gibt es nur f110.
            if stage not in ('hallway', 'vanilla'):
                warn = ('  NOTE: floor %s with stage %s - outside the hallway'
                        ' only f110 exists, so little will react' % (floor,
                                                                     stage))
        # Nur mitgeben, was vom Spiel abweicht -- sonst steht in jedem
        # gebauten Archiv ein --light, auch wenn nichts geaendert wurde, und
        # die Zustandszeile meldete dauerhaft eine Abweichung.
        licht = ['%s=%g' % (n, self.light_sp[n].value())
                 for n, v in ptstate.LIGHT_FIELDS
                 if abs(self.light_sp[n].value() - v) > 1e-3]
        if licht:
            cmd += ['--light', ','.join(licht)]
        if self.cb_baby.isChecked():
            # Den Namen aus spawn.PARTS holen, nicht abtippen: die Pruefung
            # dort unterscheidet Gross- und Kleinschreibung, und 'baby' hat
            # den Bau mit "unbekannter partsType" abbrechen lassen.
            cmd += ['--gimmick', self.cmb_gimmick.currentData(),
                    '--gimmick-at', ','.join('%g' % e.value()
                                             for e in self.xyz)]
        # Alles, was vom ORIGINAL abweicht, muss mit: luaprobe faengt jedes
        # Mal dort an, also fiele Frueheres sonst still heraus.
        on = sorted(n for n, v in want.items() if v)
        off = sorted(n for n, v in want.items() if not v)
        if on:
            cmd += ['--show', ','.join(on)]
        if off:
            cmd += ['--hide', ','.join(off)]

        self.bt_build.setEnabled(False)
        self.say('building %s%s - takes a moment (600 MB)%s'
                 % (stage, forced, warn))
        self._runner = Runner(lambda: pttools.run_tool('luaprobe.py', cmd))
        self._runner.done.connect(self._built)
        self._runner.start()

    def _built(self, ok, msg):
        self.bt_build.setEnabled(True)
        self._state()
        lines = [l.strip() for l in msg.splitlines() if l.strip()]
        self.say(('done: %s' % lines[-1] if ok and lines else
                  ('done' if ok else 'ERROR: %s' % (lines[-1] if lines
                                                    else '?')))[:200], ok)


# ------------------------------------------------------------------ Etagen
class FloorsPage(Page):
    """Nachschlagewerk: was jede Etage freischaltet."""

    TITLE = 'Floors'

    def build(self):
        self.box.addWidget(head('What each floor arms'))
        self.box.addWidget(note('Reference only: what each hallway loop arms. Nothing here is a'
                                ' switch.'))
        self.box.addWidget(note('These are hallway loops. The mazes carry f110 alone.',
                                '#a60'))
        t = QtWidgets.QTableWidget(len(FLOOR_EVENTS), 2)
        t.setHorizontalHeaderLabels(['floor', 'what it arms'])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setColumnWidth(0, 70)
        t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        t.setWordWrap(True)
        for i, (name, what) in enumerate(FLOOR_EVENTS):
            t.setItem(i, 0, QtWidgets.QTableWidgetItem(name))
            t.setItem(i, 1, QtWidgets.QTableWidgetItem(what))
        t.resizeRowsToContents()
        self.box.addWidget(t, 1)
        self.box.addWidget(note('The full per-loop switch list comes from the'
                                ' GeoModuleConditions in the archive:'
                                ' "python ptfloors.py --all" writes it out.',
                                '#888'))


# ----------------------------------------------------------------- Werkzeug
class ToolsPage(Page):
    """Spielstand, Texturen, texture.qar, Streaming und die Pfade."""

    TITLE = 'Tools'

    def build(self):
        self.box.addWidget(head('Savegame'))
        self.box.addWidget(note('Deletes the savegame, always after writing a backup. The'
                                ' confirmation names every place it found one.'))
        r = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton('Backup only')
        b.clicked.connect(self._save_backup)
        r.addWidget(b)
        b = QtWidgets.QPushButton('Open folder')
        b.clicked.connect(self._save_open)
        r.addWidget(b)
        b = QtWidgets.QPushButton('Reset savegame')
        b.clicked.connect(self._save_reset)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)

        self.box.addWidget(hline())
        self.box.addWidget(head('Texture streaming'))
        self.box.addWidget(note('Toggle this on the loading or title screen - the streamer only'
                                ' picks it up when it next builds its list.'))
        r = QtWidgets.QHBoxLayout()
        self.bt_stream = QtWidgets.QPushButton('Texture streaming: ?')
        self.bt_stream.clicked.connect(self._stream)
        r.addWidget(self.bt_stream)
        self.bt_grade = QtWidgets.QPushButton('Mip grade: ?')
        self.bt_grade.clicked.connect(self._grade)
        r.addWidget(self.bt_grade)
        r.addStretch(1)
        self.box.addLayout(r)
        self.box.addWidget(note(
            'Freezes the texture detail level so it stops changing with'
            ' distance. Needs texture streaming on.', '#888'))

        self.box.addWidget(hline())
        self.box.addWidget(head('Street textures'))
        self.box.addWidget(note(
            'On the street textures fall apart as you walk up to an object.'
            ' This writes one line into the archive that freezes the texture'
            ' detail level, so it stops changing with distance.'))
        self.box.addWidget(note(
            'The street stays blurry - it is the level loaded at the start'
            ' that gets frozen. It applies to the whole game, and the archive'
            ' is rewritten, so P.T. has to be closed.', '#a60'))
        r = QtWidgets.QHBoxLayout()
        self.lb_strasse = QtWidgets.QLabel('')
        r.addWidget(self.lb_strasse)
        self.bt_strasse_an = QtWidgets.QPushButton('Freeze the detail level')
        self.bt_strasse_an.clicked.connect(lambda: self._strasse(True))
        r.addWidget(self.bt_strasse_an)
        self.bt_strasse_aus = QtWidgets.QPushButton('Back to original')
        self.bt_strasse_aus.clicked.connect(lambda: self._strasse(False))
        r.addWidget(self.bt_strasse_aus)
        r.addStretch(1)
        self.box.addLayout(r)

        self.box.addWidget(hline())
        self.box.addWidget(head('texture.qar'))
        self.box.addWidget(note('Holds most of the textures in the game. Moving it out is never'
                                ' a delete: the file goes to bak\\ and comes back from there.'))
        r = QtWidgets.QHBoxLayout()
        self.bt_qar = QtWidgets.QPushButton('texture.qar: ?')
        self.bt_qar.clicked.connect(self._qar)
        r.addWidget(self.bt_qar)
        r.addStretch(1)
        self.box.addLayout(r)
        self.lb_qar = QtWidgets.QLabel('')
        self.box.addWidget(self.lb_qar)

        self.box.addWidget(hline())
        self.box.addWidget(head('Export textures as PNG'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('how many'))
        self.sp_texn = QtWidgets.QSpinBox()
        self.sp_texn.setRange(1, 1061)
        self.sp_texn.setValue(50)
        r.addWidget(self.sp_texn)
        r.addWidget(QtWidgets.QLabel('of 1061'))
        self.bt_tex = QtWidgets.QPushButton('Export ...')
        self.bt_tex.clicked.connect(self._export)
        r.addWidget(self.bt_tex)
        r.addStretch(1)
        self.box.addLayout(r)

        self.box.addWidget(hline())
        self.box.addWidget(head('Paths'))
        self.box.addWidget(note(
            'Where shadPS4 and the game live. Changes are saved at once but'
            ' only take effect after restarting this tool - the values are'
            ' read once at import.'))
        self.ed_path = {}
        for key, label, hint in (
                ('shadps4', 'shadPS4', 'the folder holding shadPS4.exe'),
                ('game', 'P.T.', 'the folder holding eboot.bin')):
            r = QtWidgets.QHBoxLayout()
            lb = QtWidgets.QLabel('%s' % label)
            lb.setMinimumWidth(70)
            r.addWidget(lb)
            ed = QtWidgets.QLineEdit(ptpaths.SHAD if key == 'shadps4'
                                     else ptpaths.GAME)
            ed.setReadOnly(True)
            r.addWidget(ed, 1)
            b = QtWidgets.QPushButton('Choose ...')
            b.clicked.connect(lambda _=False, k=key, h=hint: self._pick(k, h))
            r.addWidget(b)
            self.box.addLayout(r)
            self.ed_path[key] = ed
        self.lb_paths = QtWidgets.QLabel('')
        self.lb_paths.setWordWrap(True)
        self.box.addWidget(self.lb_paths)
        self._check_paths()
        self._runner = None
        self._refresh_buttons()

    def _refresh_buttons(self):
        st, txt = pttools.qar_state()
        self.bt_qar.setText({'on': 'texture.qar: ACTIVE  (click to remove)',
                             'off': 'texture.qar: removed  (click to restore)',
                             'none': 'texture.qar: not found'}[st])
        self.bt_qar.setEnabled(st != 'none')
        self.lb_qar.setText(txt)
        on = self.app.holder.streaming()
        self.bt_stream.setText(
            'Texture streaming: %s'
            % ('?' if on is None else ('ON  (click to turn off)' if on
                                       else 'off  (click to turn on)')))
        self.bt_stream.setEnabled(on is not None)
        z = grsupp.zustand()
        # Der Zustand wird im Takt gesetzt und kommt deshalb nicht durch
        # `apply_lang`, das nur einmal ueber die gebauten Widgets geht.
        self.lb_strasse.setText(
            tr({True: 'archive: detail level frozen',
                False: 'archive: original',
                None: 'archive: cannot tell'}[z],
               getattr(self.app, '_lang', 'en')))
        laeuft = bool(ptmem.find_pid())
        self.bt_strasse_an.setEnabled(z is False and not laeuft)
        self.bt_strasse_aus.setEnabled(z is True and not laeuft)
        gr = self.app.holder.grade_change()
        self.bt_grade.setText(
            'Mip grade: %s'
            % ('?' if gr is None else ('changing  (click to freeze)' if gr
                                       else 'FROZEN  (click to release)')))
        self.bt_grade.setEnabled(gr is not None)

    # -- Pfade
    def _pick(self, key, hint):
        """Verzeichnis waehlen und sofort speichern.

        Verzeichnis, nicht Datei: beide Pfade sind Ordner, und ein Nutzer, der
        die .exe anklickt, soll trotzdem zum Ziel kommen -- deshalb wird ein
        mitgegebener Dateipfad auf sein Verzeichnis zurueckgefuehrt.
        """
        start = self.ed_path[key].text() or ''
        got = QtWidgets.QFileDialog.getExistingDirectory(
            self, 'Choose %s' % hint, start)
        if not got:
            return
        got = os.path.normpath(got)
        if os.path.isfile(got):
            got = os.path.dirname(got)
        cfg = ptpaths.load()
        cfg[key] = got
        try:
            ptpaths.save(cfg)
        except Exception as ex:
            self.say('could not save the path: %s' % ex, False)
            return
        self.ed_path[key].setText(got)
        self._check_paths()
        self.say('saved - restart this tool for it to take effect', True)

    def _check_paths(self):
        """Liegt dort wirklich, was erwartet wird?

        Geprueft wird gegen die EINGETRAGENEN Felder, nicht gegen ptpaths:
        nach einer Aenderung gelten die Modulwerte erst nach einem Neustart,
        und die Warnung soll den neuen Stand beurteilen.
        """
        bad = []
        shad = self.ed_path['shadps4'].text()
        game = self.ed_path['game'].text()
        if not shad or not os.path.isfile(os.path.join(shad, 'shadPS4.exe')):
            bad.append('no shadPS4.exe in the shadPS4 folder')
        if not game or not os.path.isfile(os.path.join(game, 'eboot.bin')):
            bad.append('no eboot.bin in the P.T. folder')
        if bad:
            self.lb_paths.setStyleSheet('color: #c00;')
            self.lb_paths.setText('Not set up: ' + '; '.join(bad)
                                  + '. Nothing that touches the game or the'
                                    ' archive will work until this is fixed.')
        else:
            self.lb_paths.setStyleSheet('color: #0a0;')
            self.lb_paths.setText('Both paths look right.')
        return not bad

    # -- Spielstand
    def _save_backup(self):
        z, n = ptsave.backup()
        if not z:
            self.say('nothing to back up', False)
            return
        self.say('saved %d files to %s' % (n, os.path.basename(z)), True)

    def _save_open(self):
        """Den Spielstandordner im Explorer zeigen.

        Es koennen mehrere sein -- shadPS4 legt je Fassung einen an. Dann
        werden alle geoeffnet; einen davon auszusuchen waere geraten.
        """
        e = ptsave.find()
        if not e:
            self.say('no savegame found', False)
            return
        for _, d, _, _ in e:
            try:
                os.startfile(d)
            except OSError as ex:
                self.say(str(ex), False)
                return
        self.say('opened %d folder(s)' % len(e), True)

    def _save_reset(self):
        e = ptsave.find()
        if not e:
            self.say('no savegame found', False)
            return
        places = '\n'.join('  %s  (%d files)' % (d, n) for _, d, n, _ in e)
        got = QtWidgets.QMessageBox.question(
            self, 'Reset savegame',
            'Delete the P.T. savegame in these places?\n\n%s\n\n'
            'A backup is written first.' % places,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if got != QtWidgets.QMessageBox.Yes:
            self.say('left alone')
            return
        try:
            # reset() sichert selbst, und zwar ZUERST: schlaegt die Sicherung
            # fehl, loescht es nicht. Ein eigener backup()-Aufruf davor
            # schriebe nur ein zweites, gleiches Zip.
            z, n, gone = ptsave.reset(e)
        except Exception as ex:
            self.say(str(ex), False)
            return
        weg = [d for ok, d in gone if ok]
        hing = [d for ok, d in gone if not ok]
        if hing:
            # Ein Ordner, der sich nicht loeschen liess, darf nicht als
            # Erfolg durchgehen -- meist haelt ihn der laufende Emulator.
            self.say('backed up %d file(s) to %s, removed %d of %d - failed:'
                     ' %s' % (n, os.path.basename(z or '?'), len(weg),
                              len(gone), '; '.join(hing)[:120]), False)
        else:
            self.say('backed up %d file(s) to %s, then removed %d place(s)'
                     % (n, os.path.basename(z or '?'), len(weg)), True)

    # -- Streaming und qar
    def _stream(self):
        on = self.app.holder.streaming()
        if on is None:
            self.say('not attached - start the game first', False)
            return
        self.app.holder.streaming(not on)
        self._refresh_buttons()
        self.say('texture streaming %s - takes effect when the streamer next'
                 ' builds its list' % ('off' if on else 'on'), True)

    def _strasse(self, an):
        if ptmem.find_pid():
            self.say('P.T. is running - close it first', False)
            return
        ziel = os.path.join(ptpaths.GAME, 'chunk1.psarc')
        ok, text = grsupp.bauen(ziel, ziel, an)
        self._refresh_buttons()
        self.say('%s - takes effect on the next start' % text if ok
                 else text, ok)

    def _grade(self):
        gr = self.app.holder.grade_change()
        if gr is None:
            self.say('needs a running game with texture streaming on', False)
            return
        self.app.holder.grade_change(not gr)
        self._refresh_buttons()
        self.say('mip grade %s' % ('released' if not gr else 'frozen'), True)

    def _qar(self):
        if ptmem.find_pid():
            self.say('P.T. is running - close it first', False)
            return
        msg = pttools.qar_toggle()
        self._refresh_buttons()
        self.say(msg, not msg.startswith('ERROR'))

    # -- Texturen
    def _export(self):
        if self._runner is not None and self._runner.isRunning():
            return
        # Der Export liest texture.qar. Ist es weggeschoben, gibt es nichts
        # zu holen -- das lieber hier sagen als eine leere Fehlermeldung
        # durchreichen.
        if not os.path.exists(ptpaths.QAR):
            self.say('texture.qar is not in place - restore it first', False)
            return
        out = QtWidgets.QFileDialog.getExistingDirectory(
            self, 'Where should the PNGs go?')
        if not out:
            return
        n = self.sp_texn.value()
        self.bt_tex.setEnabled(False)
        self.say('exporting %d textures - this takes a while ...' % n)

        def work():
            ok, msg = pttools.run_tool('ftex.py', ['--png', out, str(n)])
            if ok:
                got = len([f for f in os.listdir(out)
                           if f.lower().endswith('.png')])
                return True, '%d PNG files in %s' % (got, out)
            return False, (msg.splitlines() or ['?'])[-1]

        self._runner = Runner(work)
        self._runner.done.connect(self._exported)
        self._runner.start()

    def _exported(self, ok, msg):
        self.bt_tex.setEnabled(True)
        self.say(msg[:200], ok)

    def refresh(self):
        # Der Streamingzustand kann sich ohne uns aendern (Spielstart).
        if self.app._tick % 16 == 0:
            self._refresh_buttons()


# ---------------------------------------------------------------- shadPS4
class ConfigPage(Page):
    """Die shadPS4-Konfiguration, direkt bearbeitbar.

    Angezeigt wird, was wirklich in der Datei steht -- die Liste ist nicht
    fest verdrahtet, sondern wird aus dem TOML aufgebaut. Schluessel einer
    neueren shadPS4-Fassung erscheinen damit von allein.

    Geschrieben wird nur, was angefasst wurde, und nur in bereits vorhandene
    Zeilen (siehe ptconfig.write). Vorher legt ptconfig eine Sicherung an.
    """

    TITLE = 'shadPS4'

    def build(self):
        self.box.addWidget(head('shadPS4 configuration'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('file'))
        self.files = ptconfig.files()
        self.cmb = QtWidgets.QComboBox()
        for tag, path in self.files:
            self.cmb.addItem(tag, path)
        self.cmb.currentIndexChanged.connect(lambda _: self._load())
        r.addWidget(self.cmb)
        b = QtWidgets.QPushButton('Reload')
        b.clicked.connect(self._load)
        r.addWidget(b)
        b = QtWidgets.QPushButton('Save')
        b.clicked.connect(self._save)
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self.lb_path = QtWidgets.QLabel('')
        self.lb_path.setStyleSheet('color: #888;')
        self.box.addWidget(self.lb_path)

        self.area = QtWidgets.QScrollArea()
        self.area.setWidgetResizable(True)
        self.body = QtWidgets.QWidget()
        self.grid = QtWidgets.QFormLayout(self.body)
        self.area.setWidget(self.body)
        self.box.addWidget(self.area, 1)
        self._vars = {}
        self._load()

    def _load(self):
        while self.grid.rowCount():
            self.grid.removeRow(0)
        self._vars = {}
        if not self.files:
            self.say('no shadPS4 config found', False)
            return
        path = self.cmb.currentData()
        self.lb_path.setText(path or '')
        try:
            data = ptconfig.load(path)
        except Exception as ex:
            self.say('cannot read: %s' % ex, False)
            return
        for sec in data:
            if sec in ptconfig.HIDE_SECTIONS:
                continue
            self.grid.addRow(head(sec))
            for key, val in data[sec].items():
                if isinstance(val, (list, dict)):
                    continue          # Listen kommen nur im GUI-Teil vor
                w = self._widget(sec, key, val)
                self.grid.addRow(key, w)
                self._vars[(sec, key)] = (w, val)
                hint = ptconfig.HINTS.get((sec, key))
                if hint:
                    self.grid.addRow('', note(hint, '#888'))
        self.say('%d value(s) loaded' % len(self._vars))

    def _widget(self, sec, key, val):
        """Passendes Bedienelement zum Werttyp."""
        if isinstance(val, bool):
            w = QtWidgets.QCheckBox()
            w.setChecked(val)
            return w
        choices = ptconfig.CHOICES.get((sec, key))
        if choices:
            w = QtWidgets.QComboBox()
            w.addItems([str(c) for c in choices])
            i = w.findText(str(val))
            if i >= 0:
                w.setCurrentIndex(i)
            return w
        w = QtWidgets.QLineEdit(str(val))
        return w

    @staticmethod
    def _read(w):
        if isinstance(w, QtWidgets.QCheckBox):
            return w.isChecked()
        if isinstance(w, QtWidgets.QComboBox):
            return w.currentText()
        return w.text()

    def _save(self):
        """Nur die geaenderten Werte schreiben -- typgerecht.

        Der Typ kommt vom GELESENEN Wert, nicht vom eingetippten Text: wo
        vorher eine Zahl stand, muss wieder eine hin. Tippt jemand Unsinn,
        wird das gemeldet und NICHTS geschrieben -- eine halb geschriebene
        Konfiguration waere schlimmer als eine abgelehnte Eingabe.
        """
        if not self.files:
            return
        path = self.cmb.currentData()
        changes, bad = {}, []
        for (sec, key), (w, old) in self._vars.items():
            raw = self._read(w)
            try:
                if isinstance(old, bool):
                    new = bool(raw)
                elif isinstance(old, int):
                    new = int(str(raw).strip())
                elif isinstance(old, float):
                    new = float(str(raw).strip())
                else:
                    new = str(raw)
            except ValueError:
                bad.append('%s / %s' % (sec, key))
                continue
            if new != old:
                changes[(sec, key)] = new
        if bad:
            self.say('not a number: %s - nothing written'
                     % ', '.join(bad), False)
            return
        if not changes:
            self.say('nothing changed')
            return
        try:
            n, bak = ptconfig.write(path, changes)
        except Exception as ex:
            self.say('write failed: %s' % ex, False)
            return
        running = ' - shadPS4 reads it at start, so restart it' \
            if ptmem.find_pid() else ''
        self.say('%d value(s) written, backup %s%s'
                 % (n, os.path.basename(bak or '?'), running), True)
        self._load()


# ------------------------------------------------------------- Screenplay
class ScreenplayPage(Page):
    """Die Ausloeser des Flurs scharfstellen und anspringen.

    HOCH EXPERIMENTELL, und der Nutzer hat das im Spiel belegt: das Verhalten
    ist unberechenbar, sichtbar passiert oft nichts, und der Sprung in die
    Trap-Box wirft den Spieler durch die Welt. Bleibt auf ausdruecklichen
    Wunsch drin -- aber mit dieser Warnung davor, nicht dahinter.

    Belastbar sind dagegen die Umschaltungen je Schleife mit ihrer
    Ausloeseart -- `ptfloors.py` liest sie aus den GeoModuleConditions des
    Archivs und gibt sie aus.
    """

    TITLE = 'Screenplay'

    def build(self):
        self.box.addWidget(head('Triggers in the hallway'))
        self.box.addWidget(note('HIGHLY EXPERIMENTAL: unpredictable, often nothing visible'
                                ' happens, and firing throws the player across the world.',
                                '#a00'))
        self.box.addWidget(note('The dependable version of this is the switch list read'
                                ' from the archive: "python ptfloors.py --all".'))
        r = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton('Scan for triggers')
        b.clicked.connect(self._scan)
        r.addWidget(b)
        r.addWidget(QtWidgets.QLabel('filter'))
        self.ed = QtWidgets.QLineEdit()
        self.ed.textChanged.connect(lambda _: self._fill())
        r.addWidget(self.ed, 1)
        self.box.addLayout(r)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['trigger', 'floors', 'armed'])
        self.tree.setColumnWidth(0, 260)
        self.tree.setRootIsDecorated(False)
        self.tree.itemDoubleClicked.connect(self._fire)
        self.box.addWidget(self.tree, 1)
        self.box.addWidget(note('Double-click a row to arm it and jump into its box.',
                                '#888'))
        self._steps = None
        self._rows = []

    def _scan(self):
        if not ptmem.find_pid():
            self.say('shadPS4 is not running', False)
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            st = ptsteps.Steps()
            if not st.ok():
                self.say('module base not found', False)
                return
            st.scan()
        except Exception as ex:
            self.say('scan failed: %s' % ex, False)
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._steps = st
        self._rows = st.rows
        self._fill()

    def _fill(self):
        self.tree.clear()
        pat = self.ed.text().strip().lower()
        groups = {}
        for r in self._rows:
            if pat and pat not in r['short'].lower():
                continue
            groups.setdefault(r['short'], []).append(r)
        for short in sorted(groups):
            rows = groups[short]
            armed = sum(1 for r in rows if r['armed'])
            it = QtWidgets.QTreeWidgetItem(
                self.tree,
                [short, ', '.join(rows[0]['floors'][:6]),
                 '%d/%d' % (armed, len(rows))])
            it.setData(0, QtCore.Qt.UserRole, short)
        self.say('%d trigger name(s), %d spot(s)'
                 % (len(groups), sum(len(v) for v in groups.values())))

    def _fire(self, item, col):
        """Scharfstellen und in die Box springen.

        Die WELTlage nehmen (ent+0xf0), nicht die aus der fox2: die ist
        relativ zur Levelwurzel, und die beiden Flurkopien stehen woanders.
        Von den Kopien die naechste -- das ist die, in der der Spieler steht.
        Genau daran sind fruehere Spruenge gescheitert (zweimal out of
        bounds).
        """
        if self._steps is None:
            return
        short = item.data(0, QtCore.Qt.UserRole)
        rows = [r for r in self._rows if r['short'] == short]
        for r in rows:
            self._steps.set(r, True)
        here = self.app.holder.pos
        pick = self._steps.nearest(rows, here) if any(here) else None
        at = self._steps.world_pos(pick) if pick else None
        if at is None:
            self.say('%s armed - no world position, walk into it yourself'
                     % short, False)
            self._fill()
            return
        if self.app.holder.teleport(at):
            self.say('%s armed and jumped to (%.2f, %.2f, %.2f)'
                     % (short, at[0], at[1], at[2]), True)
        else:
            self.say('%s armed, but the jump failed (not attached)' % short,
                     False)
        self._fill()


# ------------------------------------------------------------------- Ueber
class AboutPage(Page):
    """Credits und Lizenz.

    Die Lizenz ist MIT mit einer Zusatzbedingung: der Credits-Abschnitt muss
    unveraendert mitgehen. Reines MIT verlangt nur den Copyright-Hinweis; der
    ausdrueckliche Satz zu den Credits war der Wunsch, um den es ging. GPL
    waere falsch gewesen -- die verlangt, dass Ableitungen wieder GPL sind,
    und das schraenkt die Anpassung ein, die frei bleiben soll.
    """

    TITLE = 'About'

    CREDITS = [
        ('frankyfife',
         'Co-author, concept and direction. Every feature in this tool'
         ' exists because he asked for it, and every finding was confirmed'
         ' by him testing it in the running game.'),
        ('Claude (Opus 5, Anthropic)',
         'Reverse engineering, memory analysis and implementation. Worked out'
         ' the player pointer chain and the movement parameters, the door'
         ' locks, the flashlight and the exposure block, the camera selector'
         ' behind the free camera, and the Fox Engine archive formats this'
         ' tool reads and writes - PSARC, FPK, FOX2, QAR and the PFTXS'
         ' texture packs.'),
        ('Lance McDonald',
         'For the original ideas of floating the player above the floor and'
         ' of detaching the camera from him, to see the parts of P.T. it'
         ' does not let you walk to. Credited as their originator, not as a'
         ' contributor to this software.'),
        ('The shadPS4 developers',
         'None of this exists without the emulator. P.T. is not a title'
         ' they owe anyone anything for; it runs at all because of their'
         ' work. Credited as such, not as contributors to this'
         ' software.'),
        ('P.T. shadPS4 texture workarounds by loreanxavier',
         'The chunk1 workarounds. Without his work, developing the tool'
         ' and working on the game would have been much more difficult, at'
         " least at the beginning. By the way, this archive doesn't include"
         ' the textures for the street area.'
         '  www.moddb.com/mods/pt-shadps4-texture-workarounds'),
    ]

    def build(self):
        t = head('P.T. Playground')
        f = t.font()
        f.setPointSize(f.pointSize() + 4)
        t.setFont(f)
        self.box.addWidget(t)
        self.box.addWidget(note('Live tools and archive patcher for P.T. (CUSA01127) under'
                                ' shadPS4.'))
        self.box.addWidget(hline())
        for who, what in self.CREDITS:
            self.box.addWidget(head(who))
            self.box.addWidget(note(what, '#444'))
        self.box.addWidget(hline())
        # Das Werk selbst -- bewusst NICHT in der Liste oben. Dort stehen
        # Leute, auf deren Arbeit dieses Werkzeug aufsetzt.
        self.box.addWidget(head('The game'))
        self.box.addWidget(note(
            'Deliberately not in the list above. That list is for people whose work this tool builds on, and the people who made P.T. did not contribute to it. They made the thing it is for. P.T. was released in August 2014 under the studio name "7780s Studio", which was Kojima Productions, published by Konami Digital Entertainment, and directed by Hideo Kojima together with Guillermo del Toro.', '#444'))
        self.box.addWidget(note(
            'Thank you, Hideo Kojima. P.T. gets more out of a single corridor than most games get out of an entire world, and it is the reason this tool exists at all. Taking it apart only made the respect for it bigger.\n\nIt was delisted in April 2015 and has never been rereleased. It cannot be bought any more, only kept by those who already have a copy. I think that is a real shame. A work like this should not depend on whether you happened to reach for it in time, and not wanting to watch it quietly disappear is a good part of why this tool exists.\n\nNamed here out of respect, not as an endorsement of any kind.', '#444'))
        self.box.addWidget(hline())
        self.box.addWidget(head('License'))
        self.box.addWidget(note(
            'MIT License with an attribution requirement. Copy, change and'
            ' redistribute it freely, including commercially. The one'
            ' condition: the copyright notice, the licence text and the'
            ' credits above must stay intact. Add your own name for what you'
            ' changed - do not remove the existing entries.', '#444'))
        b = QtWidgets.QPushButton('Open LICENSE')
        b.clicked.connect(self._license)
        r = QtWidgets.QHBoxLayout()
        r.addWidget(b)
        r.addStretch(1)
        self.box.addLayout(r)
        self.box.addWidget(hline())
        self.box.addWidget(note(
            'Unofficial fan tool. P.T. and Silent Hills are property of'
            ' Konami Digital Entertainment. Not affiliated with or endorsed'
            ' by Konami, Kojima Productions or the shadPS4 project. No game'
            ' assets are shipped - everything it touches must already be on'
            ' your own machine, from your own copy of the game.'))

    def _license(self):
        path = os.path.join(HERE, 'LICENSE')
        if not os.path.exists(path):
            self.say('LICENSE not found next to the tool', False)
            return
        os.startfile(path)
        self.say('opened %s' % path)


# -------------------------------------------------------------------- Licht
class ExpoFinder(QtCore.QThread):
    """`Holder.expo_find()` im Hintergrund.

    Der Suchlauf geht durch den ganzen Prozessspeicher und braucht Sekunden.
    Im Takt aufgerufen stuende das Fenster -- dieselbe Ueberlegung wie beim
    Attacher.
    """

    done = QtCore.Signal(int)

    def __init__(self, holder):
        super().__init__()
        self._h = holder

    def run(self):
        try:
            n = self._h.expo_find()
        except Exception:
            n = 0
        self.done.emit(int(n))


class LightPage(Page):
    """Taschenlampe und Belichtung.

    Warum beides hier und die Lampe nicht mehr beim Spieler: der Nutzer wollte
    eine eigene Struktur fuer Licht, und die Lampe gehoert dazu.
    """

    TITLE = 'Light'

    def build(self):
        self.box.addWidget(head('Flashlight'))
        self.box.addWidget(note('Colour and brightness of the torch the player carries.'
                                ' Both take effect at once.'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('colour'))
        self.sw_colour = QtWidgets.QFrame()
        self.sw_colour.setFixedSize(28, 18)
        self.sw_colour.setFrameShape(QtWidgets.QFrame.Box)
        r.addWidget(self.sw_colour)
        b = QtWidgets.QPushButton('Pick')
        b.clicked.connect(self._pick)
        r.addWidget(b)
        self.lb_colour = QtWidgets.QLabel('1.00 1.00 1.00')
        r.addWidget(self.lb_colour)
        r.addStretch(1)
        self.box.addLayout(r)
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('bright'))
        self.sl_lumen = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_lumen.setRange(0, 2000)
        self.sl_lumen.setValue(int(ptplayer.Holder.LIGHT_DEFAULT['lumen']))
        self.sl_lumen.valueChanged.connect(self._light)
        r.addWidget(self.sl_lumen, 1)
        self.lb_lumen = QtWidgets.QLabel('100 lm')
        self.lb_lumen.setMinimumWidth(64)
        r.addWidget(self.lb_lumen)
        b = QtWidgets.QPushButton('Reset')
        b.clicked.connect(self._light_reset)
        r.addWidget(b)
        self.box.addLayout(r)
        self.cb_lightkeep = QtWidgets.QCheckBox('keep it across room changes')
        self.cb_lightkeep.setChecked(True)
        self.box.addWidget(self.cb_lightkeep)
        # -------------------------------------------------- Belichtung
        self.box.addWidget(hline())
        self.box.addWidget(head('Exposure'))
        self.box.addWidget(note(
            'Brightens or darkens the WHOLE image instead of a five metre cone,'
            ' so distant surfaces with no light of their own become visible.'
            ' The torch cannot do that: its range is baked in when the light is'
            ' created, which is why a hundredfold brightness still stops at the'
            ' same distance.'))
        self.box.addWidget(note(
            'Compensation shifts the exposure directly. Ceiling raises the limit'
            ' the automatic exposure may open up to - the game caps it at 1, and'
            ' without lifting that cap the compensation runs against the cap.',
            '#888'))

        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('compensation'))
        self.sl_comp = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        # In halben Blendenstufen, damit sich fein stellen laesst.
        self.sl_comp.setRange(int(ptexpo.COMP_MIN * 2), int(ptexpo.COMP_MAX * 2))
        self.sl_comp.setValue(int(ptexpo.DEFAULT_COMP * 2))
        self.sl_comp.valueChanged.connect(self._expo)
        r.addWidget(self.sl_comp, 1)
        self.lb_comp = QtWidgets.QLabel('+0.0 EV')
        self.lb_comp.setMinimumWidth(72)
        r.addWidget(self.lb_comp)
        self.box.addLayout(r)

        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('ceiling'))
        self.sl_max = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_max.setRange(int(ptexpo.MAX_MIN), int(ptexpo.MAX_MAX))
        self.sl_max.setValue(int(ptexpo.DEFAULT_MAX))
        self.sl_max.valueChanged.connect(self._expo)
        r.addWidget(self.sl_max, 1)
        self.lb_max = QtWidgets.QLabel('1 EV')
        self.lb_max.setMinimumWidth(72)
        r.addWidget(self.lb_max)
        b = QtWidgets.QPushButton('Reset')
        b.clicked.connect(self._expo_reset)
        r.addWidget(b)
        self.box.addLayout(r)

        self.cb_expokeep = QtWidgets.QCheckBox('keep it across room changes')
        self.cb_expokeep.setChecked(True)
        self.box.addWidget(self.cb_expokeep)

        self.lb_expo = QtWidgets.QLabel('')
        self.lb_expo.setWordWrap(True)
        self.box.addWidget(self.lb_expo)

        self._rgb = [1.0, 1.0, 1.0]
        self._light_re = 0
        self._expo_re = 0
        self._finder = None
        self._show_colour()
        self._expo_enable(False)

    # -- Lampe
    def _show_colour(self):
        r, g, b = self._rgb
        self.sw_colour.setStyleSheet(
            'background: #%02x%02x%02x;'
            % (int(r * 255), int(g * 255), int(b * 255)))
        self.lb_colour.setText('%.2f %.2f %.2f' % (r, g, b))

    def _pick(self):
        r, g, b = self._rgb
        cur = QtGui.QColor.fromRgbF(r, g, b)
        got = QtWidgets.QColorDialog.getColor(cur, self, 'Flashlight colour')
        if got.isValid():
            self._rgb = [got.redF(), got.greenF(), got.blueF()]
            self._show_colour()
            self._light()

    def _light(self):
        lm = self.sl_lumen.value()
        self.lb_lumen.setText('%d lm' % lm)
        at = self.app.holder.light_set(self._rgb, lm)
        if at is None:
            self.say('no level loaded - no light to write', False)
            return
        self.say('%.2f/%.2f/%.2f  %d lm  @0x%x'
                 % (self._rgb[0], self._rgb[1], self._rgb[2], lm, at), True)

    def _light_reset(self):
        d = ptplayer.Holder.LIGHT_DEFAULT
        self._rgb = [d['r'], d['g'], d['b']]
        self._show_colour()
        self.sl_lumen.setValue(int(d['lumen']))     # loest _light aus
        self.say('back to the game default')

    # -- Belichtung
    def _expo_enable(self, on):
        for w in (self.sl_comp, self.sl_max):
            w.setEnabled(bool(on))

    def _comp_value(self):
        return self.sl_comp.value() / 2.0

    def _expo(self):
        comp, hoch = self._comp_value(), float(self.sl_max.value())
        self.lb_comp.setText('%+.1f EV' % comp)
        self.lb_max.setText('%d EV' % int(hoch))
        n = self.app.holder.expo_set(comp=comp, hoch=hoch)
        if not n:
            # Nicht bloss meckern: nach einem Ladevorgang koennen die Bloecke
            # woanders liegen, und dann ist Nachsuchen die richtige Antwort.
            self.say('exposure blocks moved - looking again ...', False)
            self._rescan()
            return
        self.say('%+.1f EV, ceiling %d   in %d blocks' % (comp, int(hoch), n),
                 True)

    def _expo_reset(self):
        self.sl_max.setValue(int(ptexpo.DEFAULT_MAX))
        self.sl_comp.setValue(int(ptexpo.DEFAULT_COMP * 2))
        self._expo()
        self.say('back to the game default')

    # -- Nachziehen, im Takt
    def keep(self):
        """Lampe und Belichtung nachziehen.

        Beides setzt das Spiel bei jedem Raumwechsel auf seine eigenen Werte
        zurueck. Geschrieben wird nur, was abweicht -- ein staendiges
        Schreiben waere unnoetig und stuende dem Spiel im Weg.
        """
        if self.cb_lightkeep.isChecked():
            lm = self.sl_lumen.value()
            d = ptplayer.Holder.LIGHT_DEFAULT
            same = (all(abs(c - 1.0) < 1e-3 for c in self._rgb)
                    and abs(lm - d['lumen']) < 0.5)
            if not same:
                cur = self.app.holder.light_read()
                if cur and not (abs(cur['r'] - self._rgb[0]) < 1e-3
                                and abs(cur['g'] - self._rgb[1]) < 1e-3
                                and abs(cur['b'] - self._rgb[2]) < 1e-3
                                and abs(cur['lumen'] - lm) < 0.5):
                    if self.app.holder.light_set(self._rgb, lm) is not None:
                        self._light_re += 1
                        self.say('%d lm   re-applied %d x'
                                 % (lm, self._light_re), True)
        if self.cb_expokeep.isChecked() and self.sl_comp.isEnabled():
            comp, hoch = self._comp_value(), float(self.sl_max.value())
            same = (abs(comp - ptexpo.DEFAULT_COMP) < 0.05
                    and abs(hoch - ptexpo.DEFAULT_MAX) < 0.05)
            if not same:
                cur = self.app.holder.expo_read()
                if cur and not (abs(cur['comp'] - comp) < 0.05
                                and abs(cur['max'] - hoch) < 0.05):
                    if self.app.holder.expo_set(comp=comp, hoch=hoch):
                        self._expo_re += 1
                        self.say('%+.1f EV   re-applied %d x'
                                 % (comp, self._expo_re), True)
                    else:
                        self._rescan()

    def refresh(self):
        # Der Suchlauf laeuft einmal, sobald ein Level geladen ist -- und im
        # Hintergrund, weil er den ganzen Prozessspeicher durchgeht.
        if self._finder is not None:
            return
        if self.sl_comp.isEnabled():
            if self.app._tick % 16 == 0:
                cur = self.app.holder.expo_read()
                if cur is None:
                    # Keine tragfaehige Adresse mehr -- nach einem Ladevorgang
                    # liegen die Bloecke woanders. Ohne diesen Zweig blieben
                    # die Regler freigeschaltet und schrieben ins Nichts: sie
                    # sehen bedienbar aus und tun nichts, und gesucht wurde
                    # nie wieder, weil hier frueher einfach zurueckgekehrt
                    # wurde.
                    self._rescan()
                    return
                self.lb_expo.setText(
                    'game right now:  compensation %+.1f EV,  ceiling %d EV,'
                    '  floor %d EV'
                    % (cur['comp'], int(cur['max']), int(cur['min'])))
            return
        if self.app._tick % 16 or not self.app.holder.alive():
            return
        self._rescan()

    def _rescan(self):
        """Erneut suchen -- im Hintergrund, und nur einer zur Zeit."""
        if self._finder is not None:
            return
        self._expo_enable(False)
        self.lb_expo.setText('looking for the exposure blocks ...')
        self._finder = ExpoFinder(self.app.holder)
        self._finder.done.connect(self._found)
        # Der Faden muss eine Referenz behalten, bis er wirklich fertig ist --
        # sonst raeumt Python ihn weg, waehrend er noch laeuft.
        self._finder.finished.connect(self._finder.deleteLater)
        self._finder.start()

    def _found(self, n):
        self._finder = None
        if not n:
            self.lb_expo.setText('no exposure blocks found - load a level,'
                                 ' then come back to this page')
            return
        cur = self.app.holder.expo_read()
        if not cur:
            # Ohne den Stand des Spiels duerfen die Regler NICHT frei werden:
            # sie stuenden auf ihren Anfangswerten, und die erste Bewegung
            # schriebe den Deckel des Spiels still auf 1 zurueck. Genau das ist
            # passiert -- im Bild stand "ceiling 1 EV", obwohl 16 gebaut war.
            self.lb_expo.setText('blocks found, but not readable yet -'
                                 ' trying again')
            return
        # Die Regler auf den Stand des Spiels setzen, OHNE zu schreiben --
        # sonst ueberschriebe das blosse Oeffnen der Seite den Zustand.
        for w, v in ((self.sl_comp, int(round(cur['comp'] * 2))),
                     (self.sl_max, int(round(cur['max'])))):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.lb_comp.setText('%+.1f EV' % self._comp_value())
        self.lb_max.setText('%d EV' % self.sl_max.value())
        self._expo_enable(True)
        self.lb_expo.setText('%d exposure blocks found' % n)


# ------------------------------------------------------------------ Fenster
# ------------------------------------------------------------------ Kamera
class CameraPage(Page):
    """Die Kamera vom Spieler loesen.

    Der Weg dahin steht in ptcam.py; hier nur das Noetigste: der Selektor
    rendert aus der ERSTEN eingeschalteten Kamera seiner nach Prioritaet
    sortierten Liste, und P.T. haelt 32 schlafende Demo-Kameras vor der
    Spielkamera. Eine davon einzuschalten genuegt.
    """

    TITLE = 'Camera'
    # Taste -> (vorwaerts, seitwaerts, Welt-Hoehe) in Schrittweiten
    KEYS = {
        QtCore.Qt.Key_W: (1, 0, 0), QtCore.Qt.Key_S: (-1, 0, 0),
        QtCore.Qt.Key_A: (0, -1, 0), QtCore.Qt.Key_D: (0, 1, 0),
        QtCore.Qt.Key_E: (0, 0, 1), QtCore.Qt.Key_Q: (0, 0, -1),
    }

    def build(self):
        self.box.addWidget(head('Free camera'))
        self.box.addWidget(note(
            'Detaches the view from the player capsule. The player stays where'
            ' he is and keeps walking; only the eye moves.'))
        self.box.addWidget(note(
            'Hand the camera back before a cutscene - otherwise it keeps the'
            ' view instead of the cutscene camera.', '#a60'))

        r = QtWidgets.QHBoxLayout()
        self.cb_take = QtWidgets.QCheckBox('take the camera')
        self.cb_take.toggled.connect(self._take)
        r.addWidget(self.cb_take)
        self.bt_here = QtWidgets.QPushButton('Back to the player')
        self.bt_here.clicked.connect(self._here)
        r.addWidget(self.bt_here)
        r.addStretch(1)
        self.box.addLayout(r)

        r = QtWidgets.QHBoxLayout()
        self.rb_frei = QtWidgets.QRadioButton('free camera')
        self.rb_frei.setChecked(True)
        self.rb_frei.setToolTip(
            'Borrow a camera nothing has ever used, put it where the game'
            ' camera is, and fly it yourself. This is the one that survives'
            ' cutscenes.')
        r.addWidget(self.rb_frei)
        self.rb_schau = QtWidgets.QRadioButton('watch a game camera')
        self.rb_schau.setToolTip(
            'Borrow a camera the game drives and keep its own position. You'
            ' see through it and ride along; the game keeps moving it, so the'
            ' movement keys will not get you anywhere.')
        r.addWidget(self.rb_schau)
        r.addStretch(1)
        self.box.addLayout(r)

        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('which one'))
        self.cmb_cam = QtWidgets.QComboBox()
        self.cmb_cam.setMinimumWidth(260)
        r.addWidget(self.cmb_cam, 1)
        self.cmb_cam.currentIndexChanged.connect(self._cam_gewechselt)
        b = QtWidgets.QPushButton('Read cameras')
        b.clicked.connect(self._cam_fuellen)
        r.addWidget(b)
        self.box.addLayout(r)
        self.box.addWidget(note(
            'Which camera to borrow. "unused" means nothing has ever written'
            ' its position - those are the safe ones. The game drives some of'
            ' the others: during the opening it writes the one at the front of'
            ' the list every single frame, which is why the view used to snap'
            ' back. Picking one that is in use puts you at its own position;'
            ' an unused one starts where you are standing.', '#888'))

        self.box.addWidget(hline())
        self.box.addWidget(head('Move'))
        self.box.addWidget(note(
            'W A S D move, Q and E drop and rise - hold them down. Click into'
            ' this page first, otherwise the keys go somewhere else.'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('step'))
        self.sp_step = QtWidgets.QDoubleSpinBox()
        self.sp_step.setRange(0.01, 5.0)
        self.sp_step.setSingleStep(0.05)
        self.sp_step.setValue(0.15)
        self.sp_step.setSuffix(' m')
        r.addWidget(self.sp_step)
        r.addWidget(QtWidgets.QLabel('per tick'))
        r.addStretch(1)
        self.box.addLayout(r)

        self.cb_pad = QtWidgets.QCheckBox('the gamepad steers the camera')
        self.cb_pad.toggled.connect(self._steuern)
        self.box.addWidget(self.cb_pad)
        self.cb_folgen = QtWidgets.QCheckBox('follow the player')
        self.cb_folgen.setToolTip(
            'Keeps the distance and direction the camera has right now,'
            ' measured in the game camera\'s own axes, and holds it while'
            ' the player walks. Fly to where you want to watch from, then'
            ' tick this - a shoulder view swings around with him.')
        self.cb_folgen.toggled.connect(self._folgen)
        self.box.addWidget(self.cb_folgen)
        self.cb_fix = QtWidgets.QCheckBox('pin the player down while steering')
        self.cb_fix.setChecked(True)
        self.box.addWidget(self.cb_fix)
        self.box.addWidget(tastentabelle((
            ('Triangle', 'hand the pad to the camera and back'),
            ('Circle', 'take the camera / give it back to the player'),
            ('Square', 'hold the cutscene / let it go on'),
            ('Left stick', 'move'),
            ('Right stick', 'look around'),
            ('L1 / R1', 'drop and rise'),
        )))
        self.box.addWidget(note(
            'The emulator reads the same pad, so without pinning the left'
            ' stick walks the player as well. Sideways only - the height'
            ' stays with hovering.', '#888'))

        gitter = QtWidgets.QGridLayout()
        for text, spalte, zeile, arg in (
                ('forward', 1, 0, {'vor': 1}), ('back', 1, 1, {'vor': -1}),
                ('left', 0, 1, {'seite': -1}), ('right', 2, 1, {'seite': 1}),
                ('up', 3, 0, {'welt_hoch': 1}),
                ('down', 3, 1, {'welt_hoch': -1})):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _=False, a=arg: self._step(a))
            gitter.addWidget(b, zeile, spalte)
        self.box.addLayout(gitter)

        self.box.addWidget(hline())
        self.box.addWidget(hline())
        self.box.addWidget(head('Cutscene'))
        self.box.addWidget(note(
            'Holds the cutscene where it is. The game keeps running, so the'
            ' free camera stays free - fly around the frozen scene and let it'
            ' go on when you are done. Nothing to hold outside a cutscene.'))
        r = QtWidgets.QHBoxLayout()
        self.cb_demo = QtWidgets.QCheckBox('pause the cutscene')
        self.cb_demo.toggled.connect(self._demo)
        r.addWidget(self.cb_demo)
        self.lb_demo = QtWidgets.QLabel('')
        r.addWidget(self.lb_demo)
        r.addStretch(1)
        self.box.addLayout(r)

        self.box.addWidget(hline())
        self.box.addWidget(head('Look'))
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('yaw'))
        self.sl_yaw = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_yaw.setRange(-180, 180)
        self.sl_yaw.valueChanged.connect(self._look)
        r.addWidget(self.sl_yaw, 1)
        self.lb_yaw = QtWidgets.QLabel('0')
        self.lb_yaw.setMinimumWidth(48)
        r.addWidget(self.lb_yaw)
        self.box.addLayout(r)
        r = QtWidgets.QHBoxLayout()
        r.addWidget(QtWidgets.QLabel('pitch'))
        self.sl_pitch = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_pitch.setRange(-89, 89)
        self.sl_pitch.valueChanged.connect(self._look)
        r.addWidget(self.sl_pitch, 1)
        self.lb_pitch = QtWidgets.QLabel('0')
        self.lb_pitch.setMinimumWidth(48)
        r.addWidget(self.lb_pitch)
        self.box.addLayout(r)

        self.lb_pos = QtWidgets.QLabel('')
        self.lb_pos.setStyleSheet('font-family: Consolas, monospace;')
        self.box.addWidget(self.lb_pos)

        # Tastendruecke sammeln und im eigenen Takt anwenden. Ein Schritt je
        # keyPressEvent haengt an der Tastaturwiederholrate des Systems -- das
        # ruckelt, setzt verzoegert ein und ist auf jedem Rechner anders.
        self._held = set()
        self._stumm = False        # Regler wird gerade programmatisch gesetzt
        self._gier = 0.0
        self._neig = 0.0
        # Ob gerade aus UNSERER Kamera gerendert wird. Nur jeder achte
        # Takt geprueft: die Frage liest ein Byte je Kamera.
        self._fuehrt = None
        # Zeiger der Spielkamera, aus der Auswahlliste. Sie zu waehlen
        # heisst zurueckgeben -- siehe _take().
        self._cam_spiel = None
        self.steuert = False
        # WUNSCH gegen ZUSTAND. `steuert` sagt, ob das Pad die Kamera gerade
        # fuehrt; das kann das Spiel jederzeit beenden. `_pad_wunsch` sagt,
        # ob der Nutzer es so haben will, und das aendert nur er selbst.
        self._pad_wunsch = False
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self._takt = QtCore.QTimer(self)
        self._takt.setInterval(33)
        self._takt.timeout.connect(self._fahren)
        self._takt.start()

    # -- Tasten
    def keyPressEvent(self, e):
        if e.key() in self.KEYS and not e.isAutoRepeat():
            self._held.add(e.key())
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() in self.KEYS and not e.isAutoRepeat():
            self._held.discard(e.key())
            return
        super().keyReleaseEvent(e)

    TAKT = 0.033          # Sollabstand dieses Taktes, siehe _takt

    def _fahren(self):
        """Nur noch sagen, WIE SCHNELL -- gefahren wird im Holder-Faden.

        Vorher wurde hier je Takt ein fester Schritt geschrieben: 33 ms,
        geteilt mit dem Zeichnen des Fensters, also grobe und ungleiche
        Spruenge. Der Regler heisst weiterhin "je Takt" und meint dieselbe
        Strecke; daraus wird hier eine Geschwindigkeit.
        """
        if not self.cb_take.isChecked():
            self.app.holder.cam_fahrt(0.0, 0.0, 0.0)
            # Auch die Drehung anhalten. Fehlte das, lief eine Kamera, der
            # man das Pad mitten im Schwenk entzog, endlos weiter.
            self.app.holder.cam_drehen(0.0, 0.0)
            return
        s = self.sp_step.value()
        vor = seite = hoch = 0.0
        for k in self._held:
            a, b, c = self.KEYS[k]
            vor += a * s
            seite += b * s
            hoch += c * s
        vor, seite, hoch = self._pad(vor, seite, hoch, s)
        self.app.holder.cam_fahrt(vor / self.TAKT, seite / self.TAKT,
                                  hoch / self.TAKT)

    def taste(self):
        """Die Taste, die das Pad an die Kamera gibt."""
        return ptplayer.XInput.BTN_Y

    def pad_knopf(self, neu):
        """Die drei Kameratasten auswerten. `neu` sind die frisch gedrueckten.

        Fest belegt statt waehlbar: drei Funktionen auf drei Tasten sind
        schneller erklaert als eine Auswahlliste, und P.T. fragt Dreieck,
        Kreis und Viereck ohnehin nicht ab.
        """
        X = ptplayer.XInput
        if neu & X.BTN_B:
            # Uebernehmen oder zurueckgeben -- ueber das Kaestchen, damit
            # Anzeige und Zustand nicht auseinanderlaufen.
            self.cb_take.setChecked(not self.cb_take.isChecked())
        if neu & X.BTN_X:
            # Viereck ist frei, seit die Vorrangschleife das Nachvornhaengen
            # selbst macht. Anhalten gehoert genau dorthin: man braucht es
            # mitten in einer Sequenz, mit beiden Sticks in Gebrauch.
            self.cb_demo.setChecked(not self.cb_demo.isChecked())
        if neu & X.BTN_Y:
            self.pad_umschalten()

    def pad_umschalten(self):
        """Umschalttaste gedrueckt: Pad an die Kamera oder zurueck ans Spiel.

        Ein Umschalter, keine Haltetaste: beide Sticks sind in Gebrauch, und
        dabei noch eine dritte Taste zu halten ist nicht zu bedienen.

        Geht ueber das KAESTCHEN, nicht am Kaestchen vorbei. Vorher legte das
        Pad einen Zustand um, den die Oberflaeche nirgends zeigte -- das sah
        aus, als reagiere sie nicht.
        """
        self.cb_pad.setChecked(not self.cb_pad.isChecked())
        return True

    def _steuern(self, on):
        """Das Kaestchen ist der Zustand. Einziger Weg hinein."""
        self._pad_wunsch = bool(on)
        if on and not self.cb_take.isChecked():
            # Ohne uebernommene Kamera gibt es nichts zu steuern. Das Haekchen
            # muss dann auch wieder weg, sonst behauptet es etwas Falsches.
            # Der WUNSCH bleibt aber stehen: die Kamera kann gerade erst
            # weggefallen sein, weil das Spiel zu Sequenzbeginn die Liste neu
            # baut. Sobald wieder eine gehalten wird, greift er von selbst.
            self.cb_pad.blockSignals(True)
            self.cb_pad.setChecked(False)
            self.cb_pad.blockSignals(False)
            self.steuert = False
            self.say('take the camera first - the pad arms itself then', False)
            return
        self.steuert = bool(on)
        stelle = None
        if self.steuert and self.cb_fix.isChecked():
            stelle = self.app.holder.festhalten(True)
        else:
            self.app.holder.festhalten(False)
        if self.steuert:
            self.say('pad steers the camera%s'
                     % (' - player pinned' if stelle else ''), True)
        else:
            self.say('pad back with the game', True)

    def _pad_nachziehen(self):
        """Den Wunsch nach Padsteuerung wieder greifen lassen.

        Faellt der Kamerazeiger weg -- das Spiel baut die Liste zu Beginn
        einer Sequenz neu, und `cam_state()` verwirft ihn dann --, nimmt der
        Takt das Haekchen "take the camera" STILL heraus. Vorher blieb die
        Padsteuerung danach aus: die Kamera war wieder da, der rechte Stick
        aber tot, waehrend die Knoepfe im Werkzeug weiter drehten.

        Billig genug fuer den Takt: liegt nichts an, ist es ein Vergleich.
        """
        soll = bool(self._pad_wunsch and self.cb_take.isChecked())
        if soll == self.steuert and soll == self.cb_pad.isChecked():
            return
        self.cb_pad.blockSignals(True)
        self.cb_pad.setChecked(soll)
        self.cb_pad.blockSignals(False)
        self.steuert = soll
        self.app.holder.festhalten(bool(soll and self.cb_fix.isChecked()))

    def _pad(self, vor, seite, hoch, s):
        """Gamepad dazurechnen -- solange es der Kamera gehoert."""
        if not self.steuert:
            return vor, seite, hoch
        pad = getattr(self.app, 'pad', None)
        if pad is None:
            return vor, seite, hoch
        (lx, ly), (rx, ry) = pad.sticks()
        vor += ly * s * 2.0
        seite += lx * s * 2.0
        btn = pad.buttons() or 0
        X = ptplayer.XInput
        # Hoch und runter auf L1/R1. Nicht aufs Steuerkreuz -- das gehoert der
        # Schwebehoehe und wird staendig gebraucht. Nicht auf die
        # Analogtrigger -- die bleiben dem Spiel. L1 und R1 dagegen kennt P.T.
        # nicht; im Werkzeug merken und wechseln sie Orte, und das ruht,
        # solange die Kamera das Pad hat.
        if btn & X.RB:
            hoch += s * 2.0
        if btn & X.LB:
            hoch -= s * 2.0
        if rx or ry:
            # Blickgeschwindigkeit in Grad je Takt. Vom Schritt entkoppelt:
            # wer fein positionieren will, soll sich nicht zugleich zaeh
            # umsehen muessen.
            #
            # rx wird ABGEZOGEN: eine wachsende Gierung dreht die
            # Blickrichtung von +z nach +x, und +x ist links (rechts =
            # vorwaerts x hoch = -x). Ohne das Minus dreht der Stick nach
            # rechts die Kamera nach links.
            # Nur noch die Drehgeschwindigkeit setzen -- fortgeschrieben
            # wird im Holder-Faden, mit echter Zeitdifferenz. Dieselben
            # 2,5 bzw. 2,0 Grad je Takt wie vorher, nur auf Grad je Sekunde
            # umgerechnet, damit sich das Gefuehl nicht aendert.
            self.app.holder.cam_drehen(-rx * 2.5 / self.TAKT,
                                       ry * 2.0 / self.TAKT)
        else:
            self.app.holder.cam_drehen(0.0, 0.0)
        return vor, seite, hoch

    def _zeige_blick(self):
        self._stumm = True
        self.sl_yaw.setValue(int(round(self._gier)))
        self.sl_pitch.setValue(int(round(self._neig)))
        self._stumm = False
        self.lb_yaw.setText('%d' % self.sl_yaw.value())
        self.lb_pitch.setText('%d' % self.sl_pitch.value())

    # -- Knoepfe
    def _cam_fuellen(self):
        """Die Auswahlliste einlesen. Nur auf Knopfdruck, nie im Takt."""
        L = self.app.holder.cam_list()
        if not L:
            self.say('no camera list - is a level loaded?', False)
            return
        self._cam_spiel = next((d['ptr'] for d in L if d['spiel']), None)
        vorher = self.cmb_cam.currentData()
        self.cmb_cam.clear()
        spr = getattr(self.app, '_lang', 'en')
        self.cmb_cam.addItem(tr('auto - first unused', spr), None)
        frei = 0
        for d in L:
            if d['spiel']:
                was = tr('game camera', spr)
            elif d['frei']:
                was = tr('unused', spr)
                frei += 1
            else:
                was = tr('in use by the game', spr)
            lage = ('%7.2f %6.2f %7.2f' % d['pos']) if d['pos'] else ''
            self.cmb_cam.addItem('#%-3d %-18s %s%s'
                                 % (d['nr'], was, lage,
                                    '   ON' if d['an'] else ''), d['ptr'])
        i = self.cmb_cam.findData(vorher)
        self.cmb_cam.setCurrentIndex(i if i >= 0 else 0)
        self.say('%d cameras, %d unused' % (len(L), frei), True)

    def _modus(self):
        """(Kamera, Lage kopieren?) aus Betriebsart und Auswahl.

        Bei "watch" und ohne ausdrueckliche Auswahl wird die erste vom Spiel
        gefuehrte genommen -- "auto" hiesse dort sonst "irgendeine unbenutzte",
        also genau das Gegenteil.
        """
        wahl = self._cam_wahl()
        if self.rb_schau.isChecked():
            if wahl is None:
                da = self.app.holder.cam_benutzte()
                wahl = da[0] if da else None
            return wahl, False
        return wahl, True

    def _cam_gewechselt(self):
        """Auswahl geaendert: sofort umschalten, wenn wir schon halten.

        Ohne das musste man aus- und wieder einschalten, damit die Wahl
        greift -- und das sah aus, als taete die Liste nichts.
        """
        if not self.cb_take.isChecked():
            return
        self._take(True)

    def _cam_wahl(self):
        """Der gewaehlte Zeiger, oder None fuer die selbsttaetige Wahl."""
        return self.cmb_cam.currentData() if self.cmb_cam.count() else None

    def _take(self, on):
        if on and self._cam_spiel and self._cam_wahl() == self._cam_spiel:
            # Die Spielkamera ist nicht zu leihen -- sie IST der
            # Normalzustand. Sie zu merken wuerde `spiel()` verderben:
            # das schliesst die eigene Kamera aus, und dann hielte das
            # Werkzeug eine Demo-Kamera fuer die Spielkamera.
            self.app.holder.cam_take(False)
            self.cb_take.blockSignals(True)
            self.cb_take.setChecked(False)
            self.cb_take.blockSignals(False)
            self.say('handed back to the game', True)
            return
        c = self.app.holder.cam_take(on, *self._modus()) if on \
            else self.app.holder.cam_take(False)
        if on and not c:
            self.cb_take.setChecked(False)
            self.say('no free camera - is a level loaded?', False)
            return
        if not on:
            if self.cb_folgen.isChecked():
                self.cb_folgen.blockSignals(True)
                self.cb_folgen.setChecked(False)
                self.cb_folgen.blockSignals(False)
            # Ohne blockSignals liefe hier _steuern(False) und loeschte den
            # Wunsch. Dann war das Pad nach dem naechsten Uebernehmen still
            # tot -- die Kamera liess sich ueber das Werkzeug drehen, ueber
            # den Stick nicht, und nichts sagte warum.
            self.cb_pad.blockSignals(True)
            self.cb_pad.setChecked(False)
            self.cb_pad.blockSignals(False)
            self.steuert = False
            self.app.holder.festhalten(False)
        self.say('camera taken' if on else 'camera handed back', True)
        if on:
            self._sync_look()

    def _folgen(self, on):
        if on and self.app.holder.cam_folgen(True) is None:
            self.cb_folgen.blockSignals(True)
            self.cb_folgen.setChecked(False)
            self.cb_folgen.blockSignals(False)
            self.say('take the camera first', False)
            return
        if not on:
            self.app.holder.cam_folgen(False)
        self.say('following the player' if on else 'standing still', True)

    def _demo(self, on):
        n = self.app.holder.demo_pause(on)
        if not n:
            self.cb_demo.blockSignals(True)
            self.cb_demo.setChecked(False)
            self.cb_demo.blockSignals(False)
            self.say('no cutscene running', False)
            return
        self.say('cutscene held' if on else 'cutscene goes on', True)

    def _here(self):
        if self.app.holder.cam_to_player():
            self._sync_look()
            self.say('back where the player looks', True)
        else:
            self.say('take the camera first', False)

    def _step(self, arg):
        s = self.sp_step.value() * 6.0
        if not self.app.holder.cam_move(**{k: v * s for k, v in arg.items()}):
            self.say('take the camera first', False)

    def _look(self):
        self.lb_yaw.setText('%d' % self.sl_yaw.value())
        self.lb_pitch.setText('%d' % self.sl_pitch.value())
        if self._stumm:
            return
        self._gier = float(self.sl_yaw.value())
        self._neig = float(self.sl_pitch.value())
        self.app.holder.cam_look(self._gier, self._neig)

    def _sync_look(self):
        st = self.app.holder.cam_state()
        if not st:
            return
        self._gier = float(st[2])
        self._neig = float(max(-89.0, min(89.0, st[3])))
        self._zeige_blick()

    def refresh(self):
        st = self.app.holder.cam_state()
        if not st:
            self.lb_pos.setText('')
            return
        aktiv, pos, g, n = st
        if aktiv:
            # Die Winkel fuehrt jetzt der Holder. Hier werden sie nur noch
            # abgeholt, damit Regler und Zahlen mitlaufen.
            w = self.app.holder.cam_winkel()
            if w is not None and (w[0] != self._gier or w[1] != self._neig):
                self._gier, self._neig = w
                self._zeige_blick()
        if aktiv and self.app._tick % 8 == 0:
            self._fuehrt = self.app.holder.cam_fuehrt()
        if self.app._tick % 8 == 0:
            z = self.app.holder.demo_state()
            self.lb_demo.setText({True: 'held', False: 'running',
                                  None: 'no cutscene'}[z])
            if z is not None and z != self.cb_demo.isChecked():
                self.cb_demo.blockSignals(True)
                self.cb_demo.setChecked(z)
                self.cb_demo.blockSignals(False)
        if aktiv != self.cb_take.isChecked():
            self.cb_take.blockSignals(True)
            self.cb_take.setChecked(aktiv)
            self.cb_take.blockSignals(False)
        self._pad_nachziehen()
        # "taking it back" heisst: eine Sequenz hat sich davorgeschoben,
        # und die Schleife im Holder holt den Platz gerade zurueck.
        was = 'game'
        if aktiv:
            was = 'free' if self._fuehrt is not False else 'free, taking it back'
        self.lb_pos.setText('%s  %8.3f %8.3f %8.3f   yaw %6.1f  pitch %5.1f'
                            % (was, pos[0], pos[1], pos[2], g, n))


class Main(QtWidgets.QMainWindow):
    PAGES = (PlayerPage, LightPage, CameraPage, WherePage, ObjectsPage,
             DoorsPage, BuildPage,
             FloorsPage, ScreenplayPage, ToolsPage, ConfigPage,
             AboutPage)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('P.T. Playground')
        # Die Startgroesse folgt dem Zoom, sonst ist das Fenster bei
        # 200 % voller Rollbalken. Die Mindestgroesse bleibt klein: die
        # Seiten rollen, es geht also nichts verloren, wenn der Nutzer das
        # Fenster kleiner zieht.
        z = load_zoom()
        self.resize(int(860 * z), int(640 * z))
        self.setMinimumSize(420, 320)
        self.holder = ptplayer.Holder()
        self.pad = ptplayer.XInput()
        self.spots = []
        self._vis = None
        self.vis_keep = None
        self._pad_prev = 0
        self._trig_prev = (False, False)
        self._trig_hold = 0
        self._tick = 0
        self._attacher = None
        self._next_try = 0.0
        self._dead = 0            # Verbindung mehrfach hintereinander tot?

        central = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.nav = QtWidgets.QListWidget()
        self.nav.setFixedWidth(132)
        self.nav.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.stack = QtWidgets.QStackedWidget()
        # Der Stapel fuehrt die ROLLBEREICHE; die Seiten stehen in
        # `self.pages`. Wer die Seite braucht, nimmt die Liste.
        self.pages = []
        for cls in self.PAGES:
            page = cls(self)
            area = QtWidgets.QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QtWidgets.QFrame.NoFrame)
            area.setWidget(page)
            self.stack.addWidget(area)
            self.pages.append(page)
            self.nav.addItem(cls.TITLE)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        # Die Spielerseite wird vom Pad bedient, egal welche Seite offen ist.
        self.player = self.pages[0]
        # Die Kameraseite wird vom Pad bedient, egal welche Seite offen ist --
        # genau wie die Spielerseite.
        self.cam_page = [p for p in self.pages
                         if p.__class__ is CameraPage][0]
        self.nav.setCurrentRow(0)
        lay.addWidget(self.nav)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Bedienelemente in eine Werkzeugleiste, NICHT in die Statusleiste:
        # die schneidet ab, sobald das Fenster schmaler wird als die Summe
        # ihrer Widgets, und bietet keinen Ueberlauf. Eine QToolBar klappt
        # ueberzaehlige Knoepfe stattdessen in ein Menue.
        self.tools = QtWidgets.QToolBar('view')
        self.tools.setMovable(False)
        self.tools.setFloatable(False)
        self.addToolBar(self.tools)
        self.bt_offset = QtWidgets.QPushButton('Show offset')
        self.bt_offset.setCheckable(True)
        self.bt_offset.toggled.connect(self._offset)
        self.tools.addWidget(self.bt_offset)
        self.bt_rescan = QtWidgets.QPushButton('Rescan')
        self.bt_rescan.setToolTip(
            'Throws away everything the tool remembers and looks it up again:'
            ' the object list behind the door and object pages, the pointer'
            ' chain to the player, and the module base. Use it after a loop'
            ' change or a restart of the game. Hovering survives.')
        self.bt_rescan.clicked.connect(self._rescan)
        self.tools.addWidget(self.bt_rescan)
        self.bt_restart = QtWidgets.QPushButton('Restart tool')
        self.bt_restart.setToolTip(
            'Starts the tool again and closes this window. The game keeps'
            ' running. Needed after changing the paths, and whenever the door'
            ' and object lists stop matching the level: that list is scanned'
            ' once and is not rebuilt when the loop changes.')
        self.bt_restart.clicked.connect(self._restart)
        self.tools.addWidget(self.bt_restart)
        self.tools.addSeparator()
        # Ein Klappmenue statt zweier Auswahlfelder: eingebettete Widgets
        # wandern nicht in den Ueberlauf einer QToolBar, ein Knopf kann also
        # abgeschnitten werden -- bei 430 px und Zoom 2,0 gemessen.
        self.bt_view = QtWidgets.QToolButton()
        self.bt_view.setText('View')
        self.bt_view.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.menu_view = QtWidgets.QMenu(self.bt_view)
        self.bt_view.setMenu(self.menu_view)
        self.tools.addWidget(self.bt_view)

        self.bar = self.statusBar()
        # Die Statusleiste fuehrt nur noch Text. Die Adressen aendern sich bei
        # jedem Emulatorstart und sind nur beim Nachmessen interessant --
        # deshalb nicht von vorn herein sichtbar.
        self.lb_detail = QtWidgets.QLabel('')
        self.lb_detail.setStyleSheet('color: #888; font-family: Consolas,'
                                     ' monospace;')
        self.lb_detail.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse)      # zum Kopieren
        self.bar.addWidget(self.lb_detail, 1)
        self.lb_link = QtWidgets.QLabel('')
        self.bar.addPermanentWidget(self.lb_link)

        # Zoom. Die Grundschrift wird EINMAL gemerkt, sonst multipliziert
        # jedes Verstellen auf die schon vergroesserte Schrift.
        self._base_pt = QtWidgets.QApplication.font().pointSizeF()
        if self._base_pt <= 0:
            self._base_pt = 9.0
        self.cmb_zoom = QtWidgets.QComboBox()
        for z in ZOOMS:
            self.cmb_zoom.addItem('%d %%' % round(z * 100), z)
        cur = load_zoom()
        i = self.cmb_zoom.findData(cur)
        if i < 0:
            self.cmb_zoom.addItem('%d %%' % round(cur * 100), cur)
            i = self.cmb_zoom.count() - 1
        self.cmb_zoom.setCurrentIndex(i)
        self.cmb_zoom.currentIndexChanged.connect(self._zoom_picked)
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItem('English', 'en')
        self.cmb_lang.addItem('Deutsch', 'de')
        self.cmb_lang.setCurrentIndex(1 if load_lang() == 'de' else 0)
        self.cmb_lang.currentIndexChanged.connect(self._lang_picked)
        # Die Auswahlfelder bleiben als Zustandstraeger, nur unsichtbar --
        # Tastenkuerzel und Speichern zeigen weiter auf sie.
        for c in (self.cmb_zoom, self.cmb_lang):
            c.hide()
        self._build_view_menu()
        self._apply_zoom(cur, tell=False)

        # Strg+Plus / Strg+Minus / Strg+0 wie im Browser.
        for seq, fn in (
                ('Ctrl+=', lambda: self._zoom_by(+1)),
                ('Ctrl++', lambda: self._zoom_by(+1)),
                ('Ctrl+-', lambda: self._zoom_by(-1)),
                ('Ctrl+0', lambda: self._set_zoom(1.0))):
            a = QtGui.QAction(self)
            a.setShortcut(QtGui.QKeySequence(seq))
            a.triggered.connect(fn)
            self.addAction(a)

        self._lang = 'en'
        if load_lang() == 'de':
            self.apply_lang('de')

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)

    def _build_view_menu(self):
        """Zoom und Sprache als Menueeintraege, mit Haken am aktiven."""
        m = self.menu_view
        m.clear()
        zg = QtGui.QActionGroup(m)
        zg.setExclusive(True)
        m.addSection('Zoom')
        for i in range(self.cmb_zoom.count()):
            a = m.addAction(self.cmb_zoom.itemText(i))
            a.setCheckable(True)
            a.setActionGroup(zg)
            a.setChecked(i == self.cmb_zoom.currentIndex())
            a.triggered.connect(
                lambda _=False, k=i: self.cmb_zoom.setCurrentIndex(k))
        m.addSection('Language')
        lg = QtGui.QActionGroup(m)
        lg.setExclusive(True)
        for i in range(self.cmb_lang.count()):
            a = m.addAction(self.cmb_lang.itemText(i))
            a.setCheckable(True)
            a.setActionGroup(lg)
            a.setChecked(i == self.cmb_lang.currentIndex())
            a.triggered.connect(
                lambda _=False, k=i: self.cmb_lang.setCurrentIndex(k))

    # -- Sprache
    def _lang_picked(self, i):
        lang = self.cmb_lang.itemData(i) or 'en'
        save_lang(lang)
        self.apply_lang(lang)
        self._build_view_menu()

    def _rescan(self):
        """Alles Gemerkte verwerfen und frisch suchen.

        Das Schweben ueberlebt: `detach()` schaltet es ab, also wird es
        gemerkt und danach wieder gesetzt -- sonst fiele der Spieler beim
        blossen Auffrischen. Der Wunsch "ueber Schleifen halten"
        (`vis_keep`) bleibt ebenfalls stehen: das ist eine Vorgabe des
        Nutzers, kein Zwischenspeicher.

        Gemeldet wird ueber die Statuszeile der gerade sichtbaren Seite --
        eine Werkzeugleiste hat keine eigene, und ein Knopf, der seine
        Beschriftung aendert, verwirrt mehr als er hilft.
        """
        lief = self.holder.running
        self._vis = None
        self.holder.detach()
        ok = self.holder.attach()
        self.holder.running = bool(lief and ok)
        seite = self.stack.currentWidget()
        if hasattr(seite, 'say'):
            seite.say('rescanned - %s' % self.holder.status, ok)

    def _restart(self):
        """Das Werkzeug neu starten. Das Spiel laeuft weiter.

        Der neue Lauf wird zuerst gestartet und erst dann dieses Fenster
        geschlossen: schlaegt das Starten fehl, bleibt alles, wie es war. Die
        kurze Ueberschneidung ist unkritisch -- der neue Lauf sucht erst
        Prozess und Modulbasis, und das dauert laenger als das Schliessen.
        """
        args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]
        if not QtCore.QProcess.startDetached(sys.executable, args, HERE):
            self.bt_restart.setText('restart failed - close and start it'
                                    ' yourself')
            return
        self.close()

    def apply_lang(self, lang):
        """Die schon gebauten Widgets durchgehen und beschriften.

        Kein Qt-Linguist: die Texte stehen im Quelltext, ein
        Uebersetzungslauf waere ein eigener Bauschritt. Weil alle
        Beschriftungen statisch sind, genuegt ein Durchlauf -- und der
        ORIGINALTEXT wird beim ersten Mal gemerkt, damit das Zurueckschalten
        nicht auf einer Uebersetzung aufsetzt.
        """
        self._lang = lang
        pool = [self] + self.pages
        for root in pool:
            for kind, get, put in (
                    (QtWidgets.QLabel, 'text', 'setText'),
                    (QtWidgets.QPushButton, 'text', 'setText'),
                    (QtWidgets.QCheckBox, 'text', 'setText'),
                    (QtWidgets.QRadioButton, 'text', 'setText'),
                    (QtWidgets.QGroupBox, 'title', 'setTitle')):
                for w in root.findChildren(kind):
                    orig = w.property('i18n_orig')
                    if orig is None:
                        orig = getattr(w, get)()
                        w.setProperty('i18n_orig', orig)
                    getattr(w, put)(tr(orig, lang))
        # Kurzinfos genauso. Sie stehen ebenfalls im Quelltext, und seit
        # der Restart-Knopf in der Werkzeugleiste sitzt, traegt eine davon
        # den ganzen Erklaerabsatz. Ohne Kurzinfo passiert nichts.
        for root in pool:
            for w in root.findChildren(QtWidgets.QWidget):
                tip = w.property('i18n_tip')
                if tip is None:
                    tip = w.toolTip()
                    if not tip:
                        continue
                    w.setProperty('i18n_tip', tip)
                w.setToolTip(tr(tip, lang))
        # Kopfzeilen von Baeumen und Tabellen
        for pg in self.pages:
            for kind in (QtWidgets.QTreeWidget, QtWidgets.QTableWidget):
                for w in pg.findChildren(kind):
                    heads = w.property('i18n_heads')
                    if heads is None:
                        n = (w.columnCount() if hasattr(w, 'columnCount')
                             else 0)
                        heads = [w.headerItem().text(c) for c in range(n)] \
                            if isinstance(w, QtWidgets.QTreeWidget) else \
                            [w.horizontalHeaderItem(c).text()
                             if w.horizontalHeaderItem(c) else ''
                             for c in range(n)]
                        w.setProperty('i18n_heads', heads)
                    labels = [tr(h, lang) for h in heads]
                    if isinstance(w, QtWidgets.QTreeWidget):
                        w.setHeaderLabels(labels)
                    else:
                        w.setHorizontalHeaderLabels(labels)
        # Die Seitenliste
        for i, cls in enumerate(self.PAGES):
            self.nav.item(i).setText(tr(cls.TITLE, lang))
        # Zeilen, die mit Zahlen zusammengebaut werden, kann kein
        # Woerterbuchdurchlauf erreichen -- die Seite baut sie selbst neu.
        for pg in self.pages:
            again = getattr(pg, 'relabel', None)
            if again is not None:
                again()

    def _offset(self, on):
        self.bt_offset.setText('Hide offset' if on else 'Show offset')
        self.lb_detail.setText(self.holder.detail if on else '')

    def obj_wanted(self):
        """Was auf der Objects-Seite angehakt ist -- als {Name: sichtbar}.

        Der Bau braucht ALLE Abweichungen vom Original, nicht nur die neuen:
        luaprobe faengt jedes Mal bei chunk1.orig.psarc an.
        """
        for pg in self.pages:
            if isinstance(pg, ObjectsPage) and pg._loaded:
                want = pg._collect()
                return {k: v for k, v in want.items()
                        if v != pg._orig.get(k, v)}
        return {}

    # -- Zoom
    def _apply_zoom(self, factor, tell=True):
        """Die Anwendungsschrift setzen -- wirkt sofort auf alle Seiten.

        Die Layouts rechnen in Schriftmetriken, also wachsen Knoepfe,
        Eingabefelder, Baumzeilen und Abstaende mit. Rahmenbreiten bleiben;
        die braeuchten QT_SCALE_FACTOR und damit einen Neustart, und beides
        zusammen wuerde doppelt skalieren.
        """
        app = QtWidgets.QApplication.instance()
        f = app.font()
        f.setPointSizeF(self._base_pt * factor)
        app.setFont(f)
        # Bereits gebaute Fenster uebernehmen eine neue Anwendungsschrift nicht
        # von selbst, sobald sie eine eigene tragen. Skaliert wird aber NUR die
        # Punktgroesse: `w.setFont(f)` wuerde Fettschrift und eigene Groessen
        # loeschen -- Ueberschriften und der Startknopf waren danach flach.
        for w in app.allWidgets():
            pt0 = w.property('font_pt0')
            wf = w.font()
            if pt0 is None:
                pt0 = wf.pointSizeF()
                if pt0 <= 0:
                    pt0 = self._base_pt
                w.setProperty('font_pt0', pt0)
            wf.setPointSizeF(float(pt0) * factor)
            w.setFont(wf)
            w.updateGeometry()
        self.nav.setFixedWidth(int(132 * factor))
        # Die Sicht auf lange Objektnamen soll nicht abgeschnitten werden.
        for page in self.pages:
            tree = getattr(page, 'tree', None)
            if tree is not None:
                tree.setColumnWidth(0, int(300 * factor))
        save_zoom(factor)
        if tell:
            self.bar.showMessage('zoom %d %%' % round(factor * 100), 4000)

    def _zoom_picked(self, i):
        z = self.cmb_zoom.itemData(i)
        if z:
            self._apply_zoom(float(z))
        self._build_view_menu()

    def _set_zoom(self, z):
        i = self.cmb_zoom.findData(z)
        if i >= 0:
            self.cmb_zoom.setCurrentIndex(i)
        else:
            self._apply_zoom(z)

    def _zoom_by(self, d):
        i = self.cmb_zoom.currentIndex() + d
        if 0 <= i < self.cmb_zoom.count():
            self.cmb_zoom.setCurrentIndex(i)

    # -- Verbindung
    def attach(self):
        """Steht die Verbindung? Wenn nicht, im Hintergrund aufbauen.

        Frueher galt `_obj is not None` als verbunden. Nach einem
        Emulator-Neustart zeigt der alte Zeiger aber irgendwohin: die
        Schreibschleife faengt die Ausnahme und meldet "game closed", und weil
        `attach` zufrieden war, wurde nie neu verbunden. Jetzt entscheidet ein
        echtes Lesen (`holder.alive()`).
        """
        if self.holder.alive():
            return True
        self._try_attach(force=True)
        return False

    def _try_attach(self, force=False):
        """Verbindungsversuch im Hintergrund, hoechstens alle drei Sekunden.

        Im Takt direkt zu verbinden geht nicht: `hover.find_base` durchsucht
        den Prozessspeicher und braucht Sekunden.
        """
        if self._attacher is not None and self._attacher.isRunning():
            return
        now = time.monotonic()
        if not force and now < self._next_try:
            return
        self._next_try = now + 3.0
        if not ptmem.find_pid():
            self.holder.status = 'game not running'
            self._dead = 0
            self.holder.detach()
            return
        # NICHT beim ersten Zucken loslassen. `detach()` schliesst das Handle,
        # und die laufende Schreibschleife faellt dann in ihre Ausnahme -- das
        # hat das Schweben nach Bruchteilen einer Sekunde beendet. Ein
        # Ladebildschirm oder Stagewechsel sieht aber genauso aus wie ein
        # geschlossenes Spiel. Also erst nach mehreren Versuchen in Folge.
        if self.holder._obj is not None:
            self._dead += 1
            if self._dead < 3:
                return
            self.holder.detach()
        self._dead = 0
        self.holder.status = 'connecting ...'
        self._attacher = Attacher(self.holder)
        self._attacher.done.connect(self._attached)
        self._attacher.start()

    def _attached(self, ok):
        if ok:
            self._dead = 0
            self.bar.showMessage('connected - %s' % self.holder.detail, 4000)

    def _auto_on(self):
        cb = getattr(self.player, 'cb_auto', None)
        return cb is None or cb.isChecked()

    def vis(self):
        """Die Objektliste -- einmal suchen, danach nur pruefen.

        Der Suchlauf kostet Sekunden; deshalb wird er nicht in den Takt
        gelegt, sondern nur auf Knopfdruck ausgeloest.
        """
        if self._vis is not None and self._vis.valid():
            return self._vis
        if not ptmem.find_pid():
            return None
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            sess = ptvis.Session()
            if not sess.ok():
                return None
            sess.scan()
        except Exception:
            traceback.print_exc()
            return None
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._vis = sess if sess.rows else None
        return self._vis

    # -- Takt
    def tick(self):
        self._tick += 1
        b = self.pad.buttons()
        if b is not None:
            new = b & ~self._pad_prev
            X = ptplayer.XInput
            H = ptplayer.Holder
            pl = self.player          # die Pad-Belegung gehoert dem Spieler,
                                      # nicht der gerade sichtbaren Seite
            if b & X.BTN_A:
                # X gehalten (XInput meldet es als A) macht das Steuerkreuz zum Warp.
                dist = pl.sp_w.value()
                for mask, row, sign in (
                        (X.DPAD_UP, H.ROW_FWD, +1.0),
                        (X.DPAD_DOWN, H.ROW_FWD, -1.0),
                        (X.DPAD_LEFT, H.ROW_SIDE, -H.SIDE_RIGHT),
                        (X.DPAD_RIGHT, H.ROW_SIDE, +H.SIDE_RIGHT)):
                    if new & mask:
                        self.holder.warp(dist, row, sign)
            else:
                # Ohne Modifikator: Hoehe. Die Anzeige muss mit, sonst steht
                # im Feld etwas anderes als im Spiel.
                schritt = pl.hover_step()
                for mask, d in ((X.DPAD_UP, +1), (X.DPAD_DOWN, -1)):
                    if new & mask:
                        pl.sp_h.setValue(round(self.holder.height
                                               + d * schritt, 3))
                # Links und rechts wechseln die Schrittweite -- wie in
                # hovergui. Mit gehaltenem X sind sie der Warp, ohne X waren
                # sie bisher unbelegt.
                for mask, d in ((X.DPAD_RIGHT, +1), (X.DPAD_LEFT, -1)):
                    if new & mask:
                        pl.hover_step_cycle(d)
            if new & X.L3:
                pl.hover_toggle()
            # L1 und R1 heben und senken die Kamera, solange sie das Pad hat.
            # Orte merken und wechseln ruht so lange -- eine doppelte Belegung
            # haelt man im Spiel nicht auseinander.
            if not self.cam_page.steuert:
                if new & X.LB:
                    pl.spot_save()
                if new & X.RB:
                    pl.spot_cycle()
            self.cam_page.pad_knopf(new)
            self._pad_prev = b

        # L2/R2: Tempo runter und hoch. Erster Druck sofort, danach
        # Wiederholung beim Halten -- schnell genug zum Durchfahren, langsam
        # genug zum Treffen.
        lt, rt = self.pad.triggers()
        for on, was, sign in ((lt, self._trig_prev[0], -1),
                              (rt, self._trig_prev[1], +1)):
            if on and not was:
                self.player.walk_bump(sign)
                self._trig_hold = 0
            elif on:
                self._trig_hold += 1
                if self._trig_hold % 4 == 0:
                    self.player.walk_bump(sign)
        self._trig_prev = (lt, rt)

        page = self.pages[self.stack.currentIndex()]
        if page is not None:
            page.refresh()
        if self._tick % 8 == 0:
            self._keep()
            # Tempo und Lampe nachziehen, auch wenn die Seite nicht sichtbar
            # ist -- sonst faellt beides zurueck, sobald man wegblaettert.
            for pg in self.pages:
                if hasattr(pg, 'keep'):
                    pg.keep()
            self._autohook()
            self.lb_link.setText(self.holder.status
                                 + ('' if self.pad.dll else '   (no pad)'))
            if self.bt_offset.isChecked():
                self.lb_detail.setText(self.holder.detail)

    def _autohook(self):
        """Selbsttaetig verbinden, solange nichts haengt.

        Deckt beides ab: den Emulatorstart (der braucht bis zu einer Minute,
        bis der Spielerzeiger steht) und einen Neustart des Spiels im Betrieb.
        Der Versuch laeuft im Hintergrund und ist auf alle drei Sekunden
        gedrosselt.
        """
        if self.holder.alive():
            self.autohook_until = None
            return
        until = getattr(self, 'autohook_until', None)
        if until is not None and time.monotonic() <= until:
            self._try_attach()          # Startfenster: immer versuchen
            return
        self.autohook_until = None
        if self._auto_on():
            self._try_attach()

    def _keep(self):
        """Sichtbarkeit nachziehen -- die Engine liest die Felder bei jedem
        Stagewechsel frisch aus der Datei. Kein Suchlauf hier, der kostet
        Sekunden und hat im Takt nichts zu suchen."""
        want = self.vis_keep
        if not want or self._vis is None or not self._vis.valid():
            return
        todo = {k: v for k, v in want.items()
                if any(r['short'] == k and self._vis.needs(r, v)
                       for r in self._vis.rows)}
        if todo:
            self._vis.apply(todo)

    def _faeden_anhalten(self, frist=5000):
        """Jeden laufenden QThread anhalten, bevor sein Objekt verschwindet.

        Qt bricht hart ab, wenn ein QThread-Objekt abgeraeumt wird, waehrend
        sein Faden laeuft ("QThread: Destroyed while thread \'\' is still
        running"). Das passierte beim Schliessen kurz nach dem Beenden des
        Emulators: `Attacher` durchsucht dann noch den Speicher eines
        sterbenden Prozesses, und `hover.find_base` braucht dafuer Sekunden.

        Gesucht wird im `__dict__` der Fenster und Seiten. `findChildren`
        hilft nicht -- diese Faeden werden ohne Elternobjekt erzeugt.
        """
        faeden = []
        for besitzer in [self] + list(getattr(self, 'pages', []) or []):
            try:
                werte = list(vars(besitzer).values())
            except TypeError:
                continue
            for v in werte:
                if isinstance(v, QtCore.QThread):
                    faeden.append(v)

        for t in faeden:
            try:
                if t.isRunning():
                    # Kein Signal mehr in eine Oberflaeche, die es gleich
                    # nicht mehr gibt.
                    t.blockSignals(True)
                    t.requestInterruption()
            except RuntimeError:
                pass          # das C++-Objekt ist schon weg
        for t in faeden:
            try:
                if t.isRunning() and not t.wait(frist):
                    t.terminate()
                    t.wait(1000)
            except RuntimeError:
                pass
        return len(faeden)

    def closeEvent(self, ev):
        # ZUERST den Takt anhalten. Sonst startet er waehrend des Aufraeumens
        # einen neuen Verbindungsversuch, und der laeuft dann ins Leere.
        for besitzer in [self] + list(getattr(self, 'pages', []) or []):
            try:
                werte = list(vars(besitzer).values())
            except TypeError:
                continue
            for v in werte:
                if isinstance(v, QtCore.QTimer):
                    try:
                        v.stop()
                    except RuntimeError:
                        pass

        self.holder.stop_flag = True
        self.holder.running = False
        self._faeden_anhalten()

        # Auch den Schreibfaden auslaufen lassen: er liest und schreibt im
        # Prozess des Spiels, und das soll nicht in ein geschlossenes Handle
        # laufen, waehrend der Rest schon abgeraeumt wird.
        try:
            if self.holder.is_alive():
                self.holder.join(1.5)
        except Exception:
            pass
        super().closeEvent(ev)


# Der Fusion-Stil zeichnet ein leeres Kaestchen nur als hellen Rahmen -- auf
# grauem Grund sieht man nicht, wo man klicken soll. Deshalb eine eigene
# Flaeche mit deutlichem Rand, und im angehakten Zustand eine Fuellung.
BOXES = """
QCheckBox::indicator, QRadioButton::indicator,
QTreeWidget::indicator, QTreeView::indicator {
    width: 15px; height: 15px;
    border: 2px solid #6a6a6a;
    background: #fbfbfb;
}
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover,
QTreeWidget::indicator:hover, QTreeView::indicator:hover {
    border-color: #2a6fb5;
    background: #eef5fd;
}
QCheckBox::indicator:checked, QTreeWidget::indicator:checked,
QTreeView::indicator:checked, QRadioButton::indicator:checked {
    background: #2a6fb5;
    border-color: #1d4f80;
}
QCheckBox::indicator:disabled, QTreeWidget::indicator:disabled {
    border-color: #b4b4b4; background: #ededed;
}
"""


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(BOXES)
    # Auf Anwendungsebene, damit auch spaeter erzeugte Felder erfasst sind.
    guard = WheelGuard(app)
    app.installEventFilter(guard)
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
