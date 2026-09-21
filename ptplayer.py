# -*- coding: utf-8 -*-
"""Spieler und Gamepad -- die Schicht unter jeder Oberflaeche.

Hier steckt alles, was mit dem laufenden Spiel redet und nichts von einem
Fenster weiss:

    XInput    so viel Controller, wie fuer Steuerkreuz, Trigger und Knoepfe
              noetig ist. Der Emulator liest denselben Controller; XInput
              erlaubt das mehrfach, es gibt also keinen Streit um das Geraet.

    Holder    haelt Hoehe und Position im Hintergrund, versetzt den Spieler
              (`teleport`, `warp`) und schaltet das Texturstreaming.

Herausgeloest aus hovergui.py am 13.09.2026, weil die Oberflaeche auf Qt
umgebaut wird und beide Fassungen dieselbe Schicht benutzen sollen. Der Inhalt
ist unveraendert uebernommen; hovergui verweist nur noch hierher.
"""
import ctypes
import math
import os
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hover
import lightscan
import paramscan
import ptcam
import ptdemo
import ptexpo
import ptmem

# Texturstreaming -- die Adressen, die GrTools selbst anfasst.
STREAM_FLAG = 0x1E706D8        # DAT_01e706d8
STREAMER_PTR = 0x1E6DEA0       # DAT_01e6dea0
STREAMER_ENABLE = 0x24144      # Byte im Streamer
# Stufenwechsel: 1 erlaubt, 0 eingefroren. Dahinter steht die
# Lua-Funktion GrTools:SuppressGradeChange (FUN_00d11d20), und
# die schreibt nur, solange STREAMER_ENABLE gesetzt ist.
STREAMER_GRADE = 0x24146


# ---------------------------------------------------------------- Gamepad
class XInput:
    """Nur so viel XInput, wie fuer das Steuerkreuz noetig ist.

    Der Emulator liest denselben Controller; XInput erlaubt das mehrfach, es
    gibt also keinen Streit um das Geraet.
    """

    DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
    LB, RB = 0x0100, 0x0200          # L1 / R1
    L3 = 0x0040                      # linker Stick gedrueckt
    # R3 ist NICHT frei: in P.T. zoomt man damit, und das Zoomen ist es, was
    # die Ausloeser im Flur scharf macht (Nutzer, 15.09.2026). Ebenso wenig
    # die Analogtrigger. Wer die Kamera aufs Pad legt, muss Tasten nehmen,
    # die das Spiel gar nicht abfragt -- Dreieck, Kreis, Viereck, Share.
    R3 = 0x0080
    BACK, START = 0x0020, 0x0010
    BTN_B, BTN_X, BTN_Y = 0x2000, 0x4000, 0x8000
    # Der untere Knopf. Auf dem Controller des Nutzers ist er mit A
    # beschriftet (gemeldet 13.09.2026); XInput nennt ihn ebenso, ein
    # DualShock druckt an derselben Stelle X.
    BTN_A = 0x1000

    class _State(ctypes.Structure):
        _fields_ = [('dwPacketNumber', ctypes.c_uint32),
                    ('wButtons', ctypes.c_uint16),
                    ('bLeftTrigger', ctypes.c_uint8),
                    ('bRightTrigger', ctypes.c_uint8),
                    ('sThumbLX', ctypes.c_int16), ('sThumbLY', ctypes.c_int16),
                    ('sThumbRX', ctypes.c_int16), ('sThumbRY', ctypes.c_int16)]

    def __init__(self):
        self.dll = None
        for name in ('XInput1_4.dll', 'xinput1_3.dll', 'XInput9_1_0.dll'):
            try:
                self.dll = ctypes.windll.LoadLibrary(name)
                break
            except OSError:
                continue

    # Schwelle fuer die Analogtrigger. XInput liefert 0..255; Microsoft
    # empfiehlt 30 als Totzone, darunter zappelt ein ausgeleierter Trigger.
    TRIGGER_ON = 40

    def triggers(self):
        """(links, rechts) als Wahrheitswerte, oder (False, False)."""
        if not self.dll:
            return False, False
        st = self._State()
        for pad in range(4):
            if self.dll.XInputGetState(pad, ctypes.byref(st)) == 0:
                return (st.bLeftTrigger >= self.TRIGGER_ON,
                        st.bRightTrigger >= self.TRIGGER_ON)
        return False, False


    def buttons(self):
        if not self.dll:
            return None
        st = self._State()
        for pad in range(4):
            if self.dll.XInputGetState(pad, ctypes.byref(st)) == 0:
                return st.wButtons
        return None

    # Totzonen aus Microsofts Empfehlung. Ohne sie driftet ein ausgeleierter
    # Stick die Kamera dauernd weg, und das sieht aus wie ein Fehler im
    # Werkzeug.
    DEAD_L, DEAD_R = 7849, 8689

    def sticks(self):
        """((lx, ly), (rx, ry)) als -1..1, Totzone schon abgezogen.

        Ohne das Herausrechnen der Totzone macht ein Stick bei 10 % Auslenkung
        schon volle Fahrt: die Kurve begaenne bei 0,24 statt bei 0.
        """
        leer = ((0.0, 0.0), (0.0, 0.0))
        if not self.dll:
            return leer
        st = self._State()
        for pad in range(4):
            if self.dll.XInputGetState(pad, ctypes.byref(st)) != 0:
                continue

            def paar(x, y, tot):
                laenge = math.hypot(x, y)
                if laenge <= tot:
                    return 0.0, 0.0
                # auf 0..1 strecken, damit direkt hinter der Totzone
                # tatsaechlich bei null angefangen wird
                f = min(1.0, (laenge - tot) / (32767.0 - tot)) / laenge
                return x * f, y * f

            return (paar(st.sThumbLX, st.sThumbLY, self.DEAD_L),
                    paar(st.sThumbRX, st.sThumbRY, self.DEAD_R))
        return leer


# ---------------------------------------------------------------- Halten
class Holder(threading.Thread):
    """Schreibt im Hintergrund. Hoehe ist jederzeit von aussen aenderbar."""

    POS_X, POS_Z = 0x30, 0x38          # Fussposition, Y liegt auf 0x34

    def __init__(self):
        super().__init__(daemon=True)
        self.height = 0.25      # Vorgabe: 0.25 m ueber dem Boden
        # Schreibrate in Hertz. 0 = ungedrosselt (die alte Fassung).
        #
        # GEMESSEN am 19.08.2026 im laufenden Spiel:
        #     7 Einzelschreibvorgaenge  14 672 Runden/s = 244 je Bild
        #     2 Bloecke + 2 einzeln     22 698 Runden/s = 378 je Bild
        #
        # Eine Runde dauert also rund 45-70 Mikrosekunden, und die
        # Schleife lief ohne Pause -- wir waren praktisch DURCHGEHEND
        # mitten in einer Schreibfolge. Die Engine liest einmal je Bild
        # und traf damit fast immer einen halb aktualisierten Satz:
        # Fuesse schon neu, Kapselmitte noch alt. Das ist das Zittern.
        #
        # Bei 120 Hz sind wir nur noch ~0,5 % der Zeit am Schreiben.
        self.rate = 120
        self.running = False
        self.stop_flag = False
        # status ist absichtlich kurz und immer einer von wenigen Zustaenden;
        # die Adresse landet in detail und zeigt nur der Knopf "Show offset".
        self.status = 'game not running'
        self.detail = ''
        # Gemerkte Belichtungsbloecke. Der Suchlauf dauert Sekunden, also
        # einmal suchen und danach nur noch pruefen.
        self._expo = []
        self.pos = (0.0, 0.0, 0.0)
        self.hspeed = 0.0
        self.rounds = 0
        self._p = None
        self._obj = None
        self._base = None
        self._cap = hover.CAPSULE
        self._prev_pos = None
        self._next = 0.0        # naechster Schreibzeitpunkt (Drosselung)
        # Fehlversuche in Folge. Einzelne sind normal (Ladebildschirm), viele
        # heissen, dass das Spiel weg ist.
        self._misses = 0
        # Fruehestens wieder nach dem teuren Rueckfall suchen.
        self._probe_next = 0.0
        # Die Kamera, die WIR genommen haben, und der Zaehler fuer das
        # Halten ihres Vorrangs. Siehe cam_take() und run().
        self._cam_ptr = None
        self._cam_takt = 0
        # Geschwindigkeit der freien Kamera in m/s und der Zeitpunkt des
        # letzten Schrittes. Gefahren wird HIER, nicht in der Oberflaeche:
        # deren Takt sind 33 ms, geteilt mit dem Zeichnen.
        self._cam_v = (0.0, 0.0, 0.0)
        self._cam_zeit = 0.0
        # Drehgeschwindigkeit in Grad je Sekunde und die aktuellen Winkel.
        # Die Winkel liegen HIER, nicht in der Oberflaeche: wer sie dort
        # im Zeichentakt fortschreibt, dreht in groben Spruengen.
        self._cam_dreh = (0.0, 0.0)
        self._cam_winkel = None
        self._dreh_zeit = 0.0
        # Versatz zur Spielkamera, in deren eigenen Achsen. None = nicht
        # folgen. Siehe cam_folgen() und run().
        self._cam_folge = None
        # Waagerechte Anheftung: (x, y, z) oder None. Siehe run().
        self._fix = None
        # Schuetzt den Schreibblock gegen detach(). Ohne das koennte der Thread
        # seine sieben Schreibvorgaenge noch mit der ALTEN Objektadresse zu Ende
        # bringen -- und nach einem Spiel-Neustart zeigt die irgendwohin.
        self._lock = threading.Lock()

    def attach(self):
        pid = ptmem.find_pid()
        if not pid:
            self.status, self.detail = 'game not running', ''
            return False
        try:
            p = ptmem.Proc(pid)
        except OSError as e:
            self.status, self.detail = 'no access', str(e)
            return False
        base = hover.find_base(p)
        if base is None:
            self.status = 'game running, no level loaded'
            self.detail = 'module base not found'
            return False
        obj, err = hover.chain(p, base, log=lambda *a: None)
        if err:
            self.status, self.detail = 'pointer chain failed', err
            return False
        d = p.read(obj + 0x180, 16)
        self._cap = struct.unpack('<4f', d)[0] if d else hover.CAPSULE
        self._p, self._obj, self._base = p, obj, base
        self._faden_an()
        self.status = 'game connected'
        self.detail = 'base 0x%x   obj 0x%x   capsule %.3f' % (base, obj, self._cap)
        return True

    def detach(self):
        """Handle schliessen und Verbindung vergessen.

        ptmem.Proc oeffnet ein Handle und schliesst es nie -- ohne das hier
        wuerde jedes Neuverbinden eines liegen lassen. Und der alte Zeiger MUSS
        weg: nach einem Spiel-Neustart zeigt er ins Leere, und attach() wird nur
        gerufen, wenn keine Verbindung mehr steht.
        """
        self.running = False
        with self._lock:
            p, self._p, self._obj, self._base = self._p, None, None, None
            if p is not None:
                try:
                    ptmem.k32.CloseHandle(p.h)
                except Exception:
                    pass
        self._prev_pos = None
        self.status, self.detail = 'game not running', ''

    def streaming(self, on=None):
        """Texturstreaming lesen (on=None) oder setzen -- wie GrTools es tut.

        Rueckgabe: True/False, oder None wenn nicht ermittelbar.
        """
        with self._lock:
            p, base = self._p, self._base
            if p is None or base is None:
                return None
            if on is not None:
                p.write(base + STREAM_FLAG, struct.pack('<I', 1 if on else 0))
                d = p.read(base + STREAMER_PTR, 8)
                sp = struct.unpack('<Q', d)[0] if d and len(d) == 8 else 0
                # Das Original legt den Streamer an, falls es ihn noch nicht
                # gibt. Das machen wir NICHT nach -- ohne Streamer gibt es auch
                # nichts abzuschalten, und eine Fremdallokation waere riskant.
                if sp:
                    p.write(sp + STREAMER_ENABLE, b'\x01' if on else b'\x00')
            d = p.read(base + STREAM_FLAG, 4)
            return bool(struct.unpack('<I', d)[0]) if d and len(d) == 4 else None

    def grade_change(self, on=None):
        """Stufenwechsel lesen (on=None) oder setzen.

        Entspricht GrTools:SuppressGradeChange / ContinueGradeChange. Das
        Spiel schreibt dieses Byte nur, solange das Streaming an ist -- wir
        halten uns daran, sonst stuende hier ein Wert, den der Streamer beim
        naechsten Einschalten ueberschreibt.

        Rueckgabe: True (Wechsel erlaubt), False (eingefroren) oder None.
        """
        with self._lock:
            p, base = self._p, self._base
            if p is None or base is None:
                return None
            d = p.read(base + STREAMER_PTR, 8)
            sp = struct.unpack('<Q', d)[0] if d and len(d) == 8 else 0
            if not sp:
                return None
            an = p.read(sp + STREAMER_ENABLE, 1)
            if not an or not an[0]:
                return None            # Streaming aus: das Byte gilt nicht
            if on is not None:
                p.write(sp + STREAMER_GRADE, b'\x01' if on else b'\x00')
            d = p.read(sp + STREAMER_GRADE, 1)
            return bool(d[0]) if d else None

    def teleport(self, at):
        """Den Spieler an (x, y, z) setzen. Gibt True zurueck, wenn geschrieben.

        Geschrieben werden die drei POSITIONS-Vektoren aus hover.py -- Fuesse,
        Kapselmitte (Y + Kapselmass) und die dritte Ablage. Die Bewegungsfelder
        bei 0x50/0x60 bleiben unangetastet: das ist die Bewegung je Bild, kein
        Ort. Die Y-Geschwindigkeit wird genullt, sonst nimmt der Spieler den
        Sturz von vorher mit an den neuen Platz.

        Sicher ist das, weil man nur zu gemerkten Spots springt -- also an
        Stellen, an denen der Spieler nachweislich schon stand. In eine Wand
        kann einen das nicht setzen.
        """
        with self._lock:
            p, o = self._p, self._obj
            if p is None or o is None:
                return False
            x, y, z = float(at[0]), float(at[1]), float(at[2])
            try:
                p.write(o + 0x30, struct.pack('<fff', x, y, z))
                p.write(o + 0x40, struct.pack('<fff', x, y + self._cap, z))
                p.write(o + 0x130, struct.pack('<fff', x, y, z))
                p.write(o + 0x74, struct.pack('<f', 0.0))
            except Exception:
                return False
        # Schwebt gerade jemand, soll er auf der neuen Hoehe weiterschweben und
        # nicht auf die alte zurueckgezogen werden.
        if self.running:
            self.height = y
        return True

    # Die Rotationsmatrix des Spielers. Zeile 3 (0x120) ist die Blickachse
    # -- im Spiel bestaetigt. Zeile 1 (0x100) ist die Seitenachse.
    ROW_SIDE, ROW_FWD = 0x100, 0x120
    ROW_RIGHT = ROW_SIDE            # alter Name, damit nichts bricht

    # Welches Vorzeichen entlang der Seitenachse nach RECHTS zeigt. Im Spiel
    # gemessen (14.09.2026): +1 ging nach links, der Warp war vertauscht.
    # Steht hier und nicht in der Oberflaeche -- zwei Fenster, die das selbst
    # raten, verdrehen es wieder.
    SIDE_RIGHT = -1.0

    def hovering(self, on=None):
        """Schweben abfragen oder setzen -- ohne Verbindungszwang.

        Der Schalter darf nicht davon abhaengen, ob gerade eine Verbindung
        steht: die Schleife wartet ohnehin auf `_p`, und sobald verbunden ist,
        schwebt es. Andernfalls tut der Knopf nichts, solange das Verbinden im
        Hintergrund laeuft.
        """
        if on is not None:
            self.running = bool(on)
            self._misses = 0
            self._faden_an()
        return self.running

    def _faden_an(self):
        """Den Schreibfaden starten, falls er noch nicht laeuft.

        Frueher geschah das NUR beim Einschalten des Schwebens. Alles andere,
        was in `run()` haengt -- Vorrang der eigenen Kamera halten, dem
        Spieler folgen, die freie Kamera fahren --, lief deshalb nur, solange
        jemand schwebte. Von aussen sah das aus, als taeten die Funktionen
        nichts; gesucht habe ich den Fehler in ihnen statt im Faden.

        Der Lauf ist billig, wenn nichts zu tun ist: die Schleife drosselt
        sich dann selbst auf 33 Hz und liest nur den Tacho.
        """
        if not self.is_alive() and not self.stop_flag:
            self.start()

    def alive(self):
        """Steht die Verbindung wirklich noch?

        `_obj is not None` reicht nicht: nach einem Emulator-Neustart zeigt
        der alte Zeiger irgendwohin, und die Schreibschleife meldet dann nur
        noch "game closed". Zwoelf Byte lesen kostet Mikrosekunden.
        """
        with self._lock:
            p, o = self._p, self._obj
        if p is None or o is None:
            return False
        try:
            d = p.read(o + 0x30, 12)
        except Exception:
            return False
        return bool(d) and len(d) == 12

    def facing(self, row):
        """Normierte Richtung aus einer Zeile der Rotationsmatrix."""
        with self._lock:
            p, o = self._p, self._obj
            if p is None or o is None:
                return None
            d = p.read(o + row, 12)
        if not d or len(d) != 12:
            return None
        v = struct.unpack('<3f', d)
        n = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
        return None if n < 1e-4 else (v[0] / n, v[1] / n, v[2] / n)

    def warp(self, dist, row=None, sign=1.0):
        """Einen festen Schritt in Blick- oder Seitenrichtung versetzen.

        Nur x und z werden verschoben; die Hoehe bleibt die eigene. Genau
        daran sind die frueheren Spruenge gescheitert (zweimal out of bounds),
        weil sie die Hoehe des Ziels uebernommen haben.
        """
        row = self.ROW_FWD if row is None else row
        d = self.facing(row)
        if d is None:
            return None
        with self._lock:
            p, o = self._p, self._obj
            if p is None or o is None:
                return None
            raw = p.read(o + 0x30, 12)
        if not raw or len(raw) != 12:
            return None
        cur = struct.unpack('<3f', raw)
        at = (cur[0] + d[0] * dist * sign, cur[1],
              cur[2] + d[2] * dist * sign)
        return at if self.teleport(at) else None

    # Wie viele Fehlversuche in Folge als "Spiel weg" gelten. Bei 0.05 s
    # Pause je Fehlversuch sind 40 rund zwei Sekunden -- lang genug fuer
    # jeden Stagewechsel, kurz genug, um ein geschlossenes Spiel zu merken.
    MISS_LIMIT = 40

    # ---------------------------------------------------------- Tempo
    # Die Vorgaben des SPIELS, nicht die des gebauten Archivs -- ein Reset
    # soll dorthin zurueck, wo P.T. selbst steht.
    WALK_DEFAULT = 1.0
    LIGHT_DEFAULT = {'r': 1.0, 'g': 1.0, 'b': 1.0, 'lumen': 100.0}

    # Wie oft der Rueckfall hoechstens laufen darf, in Sekunden.
    # `ptmem.find_pid` startet `tasklist` als Unterprozess und braucht
    # GEMESSEN 269 ms; die Oberflaeche taktet alle 33 ms. Ungedrosselt aus
    # einem refresh() gerufen steht das Fenster still. Zwei Sekunden sind
    # kurz genug, dass ein Regler kurz nach dem Start trotzdem greift.
    PROBE_PAUSE = 2.0

    def _proc(self):
        """Der Prozess, notfalls selbst geoeffnet.

        Der Holder verbindet sich verzoegert im Hintergrund. Ohne diesen
        Rueckfall wirkt ein Regler in den ersten Sekunden scheinbar nicht.

        Der Rueckfall ist aber TEUER und gehoert deshalb gedrosselt -- siehe
        PROBE_PAUSE. Wer im Takt der Oberflaeche danach fragt, soll ein
        schnelles "nein" bekommen statt einer Viertelsekunde Stillstand.
        """
        with self._lock:
            p, base = self._p, self._base
        if p is not None:
            return p, base
        now = time.perf_counter()
        if now < self._probe_next:
            return None, None
        self._probe_next = now + self.PROBE_PAUSE
        pid = ptmem.find_pid()
        if not pid:
            return None, None
        try:
            p = ptmem.Proc(pid)
        except OSError:
            return None, None
        return p, (base if base is not None else hover.find_base(p))

    def _obj_now(self):
        """(Prozess, Spielerobjekt) frisch ueber die Zeigerkette."""
        p, base = self._proc()
        if p is None or base is None:
            return None, None
        try:
            obj, err = hover.chain(p, base, log=lambda *a: None)
        except OSError:
            return None, None
        return (None, None) if (err or not obj) else (p, obj)

    def walk_addr(self):
        """Adresse des WIRKSAMEN Tempoblocks.

        Es gibt zwei Bloecke mit denselben acht Werten; der ueber die
        Kamera-Unterschrift gefundene laesst sich beschreiben, ohne dass sich
        das Tempo aendert -- er wird nur beim Laden gelesen. Wirksam ist die
        Kopie im Spielerkontext, `PLAYER_GAP` davor.
        """
        p, obj = self._obj_now()
        if p is None:
            return None, None
        b = obj - paramscan.PLAYER_GAP
        if not paramscan.looks_like(paramscan.read8(p, b)):
            return None, None
        return p, b

    def walk_get(self):
        p, b = self.walk_addr()
        return None if b is None else paramscan.current_rate(p, b)

    def walk_set(self, factor):
        """Tempofaktor setzen. Rueckgabe: (vorderes Maximum, Adresse) oder
        (None, None), wenn der Block nicht steht."""
        p, b = self.walk_addr()
        if b is None:
            return None, None
        v = paramscan.set_rate(p, b, float(factor))
        return v[0], b

    # -------------------------------------------------------- Taschenlampe
    def light_addr(self):
        """Adresse der aktiven Lampe. `lightscan.live_addr` prueft lumen und
        temperature mit, damit hier nie ins Leere geschrieben wird."""
        p, obj = self._obj_now()
        if p is None:
            return None, None
        return p, lightscan.live_addr(p, obj)

    def light_read(self):
        p, a = self.light_addr()
        return None if not a else lightscan.live_read(p, a)

    def light_set(self, rgb, lumen):
        """Farbe und Helligkeit setzen. Rueckgabe: Adresse oder None."""
        p, a = self.light_addr()
        if not a:
            return None
        lightscan.live_set(p, a, rgb=tuple(rgb), lumen=lumen)
        return a

    def festhalten(self, an):
        """Den Spieler waagerecht anheften -- oder wieder loslassen.

        Rueckgabe: die gemerkte Stelle, oder None. Sie wird beim EINSCHALTEN
        einmal gelesen; wer sie im Takt neu liest, heftet den Spieler nirgends
        an, sondern folgt ihm.
        """
        if not an:
            self._fix = None
            return None
        p, o = self._obj_now()
        if p is None or o is None:
            return None
        d = p.read(o + 0x30, 0x0c)
        if not d or len(d) != 0x0c:
            return None
        self._fix = struct.unpack('<3f', d)
        return self._fix

    # --------------------------------------------------------- Freie Kamera
    #
    # Der Selektor fuehrt eine nach Prioritaet sortierte Kameraliste und
    # rendert aus der ERSTEN eingeschalteten. P.T. haelt 32 schlafende
    # Demo-Kameras VOR der Spielkamera -- eine davon einzuschalten genuegt,
    # und danach schreibt niemand sie pro Bild neu. Begruendung in ptcam.py.
    def pid(self):
        """Prozessnummer der bestehenden Verbindung, oder None.

        Billig: der Holder hat sie beim Verbinden ermittelt. Wer stattdessen
        `ptmem.find_pid` fragt, startet `tasklist` -- 269 ms, gemessen.
        """
        with self._lock:
            return self._p.pid if self._p is not None else None

    def cam(self):
        """Ein Kameraobjekt, oder None.

        Jedes Mal neu aufgeloest: nach einem Ladevorgang stehen die Zeiger
        woanders, und eine gemerkte Liste zeigte dann ins Leere.

        Bewusst OHNE `_proc()`: dessen Rueckfall startet `tasklist` als
        Unterprozess und sucht danach die Modulbasis, indem er die ganze
        eboot.bin liest und den Prozessspeicher durchkaemmt. Einmal beim
        Verbinden ist das richtig; im Takt der Oberflaeche macht es das
        Programmfenster unbedienbar -- gemeldet am 15.09.2026, mit und ohne
        laufendes Spiel. Genommen wird deshalb nur, was das Verbinden ohnehin
        schon ermittelt hat.
        """
        with self._lock:
            p, base = self._p, self._base
        if p is None or base is None:
            return None
        try:
            k = ptcam.Kamera(p, base)
            k.unsere = self._cam_ptr
            return k
        except (RuntimeError, OSError, struct.error):
            return None

    def cam_state(self):
        """(aktiv?, Position, Gierung, Neigung) -- oder None ohne Kamera."""
        k = self.cam()
        if k is None:
            return None
        c = self._cam_ptr
        if c is not None and c not in k.liste:
            # Ladevorgang: das Spiel baut die Liste neu, der alte Zeiger ist
            # tot. Ihn stehen zu lassen hiesse, in fremden Speicher zu
            # schreiben.
            c = self._cam_ptr = None
        q, pos = ptcam.lage(k.p, c or k.spiel)
        if q is None:
            return None
        g, n = ptcam.winkel(q)
        return (c is not None, tuple(pos[:3]), g, n)

    def cam_benutzte(self):
        """Die Kameras, die das Spiel fuehrt. Leer ohne Verbindung."""
        k = self.cam()
        if k is None:
            return []
        try:
            return k.benutzte()
        except Exception:
            return []

    def cam_list(self):
        """Alle Kameras der Liste, oder [] ohne Verbindung."""
        k = self.cam()
        if k is None:
            return []
        try:
            return k.infos()
        except Exception:
            return []

    def cam_take(self, on, cam=None, pose=None):
        k = self.cam()
        if k is None:
            return None
        try:
            if not on:
                c = k.freigeben()
                self._cam_ptr = None
                self._cam_folge = None
                self._cam_winkel = None
                self._cam_dreh = (0.0, 0.0)
                return c
            c = k.uebernehmen(cam, pose)
        except RuntimeError:
            return None
        if c:
            # KEIN Schreibzugriff auf die Prioritaet. Der Gedanke war, uns auf
            # Editor-Rang zu setzen, damit ein Neuaufbau der Liste uns nach
            # vorn sortiert. Er zerstoert aber das Merkmal, an dem `spiel()`
            # die Spielkamera erkennt -- die schwaechste Prioritaet unter den
            # eingeschalteten. Am 20.09.2026 im laufenden Spiel passiert: die
            # Spielkamera trug danach Rang 1, und jede Demo-Kamera mit Rang 2
            # galt als Spielkamera. Der Rang bleibt, wie er ist.
            self._cam_ptr = c
            # Die Blickwinkel GLEICH mitnehmen. Ohne das bleibt
            # `_cam_winkel` None, und die Drehschleife im Faden verlangt ihn
            # -- sie uebersprang sich dann stillschweigend. Folge: der rechte
            # Stick tat nach jeder Uebernahme nichts, bis man einmal einen
            # der beiden Regler bewegt hatte, denn nur `cam_look()` setzte
            # den Wert. Am 20.09.2026 im laufenden Spiel aufgefallen.
            try:
                q, _pos = ptcam.lage(k.p, c)
                if q is not None:
                    self._cam_winkel = ptcam.winkel(q)
            except Exception:
                pass
        return c

    def demo_state(self):
        """Zwischensequenz: True angehalten, False laeuft, None keine."""
        with self._lock:
            p, base = self._p, self._base
        if p is None or base is None:
            return None
        try:
            return ptdemo.zustand(p, base)
        except OSError:
            return None

    def demo_pause(self, an):
        """Sequenz anhalten oder weiterlassen. Rueckgabe: Anzahl Stroeme."""
        with self._lock:
            p, base = self._p, self._base
        if p is None or base is None:
            return 0
        try:
            return ptdemo.setzen(p, base, bool(an))
        except OSError:
            return 0

    def cam_fahrt(self, vor=0.0, seite=0.0, hoch=0.0):
        """Die freie Kamera fahren -- in Metern JE SEKUNDE.

        Die Oberflaeche sagt nur noch, wie schnell; abgerechnet wird in
        diesem Faden mit der tatsaechlich verstrichenen Zeit. Damit haengt
        das Tempo nicht mehr am Zeichentakt, und die Schritte werden bei
        gleichem Tempo rund viermal feiner.
        """
        self._cam_v = (float(vor), float(seite), float(hoch))
        if any(self._cam_v):
            self._faden_an()

    def cam_folgen(self, an):
        """Der freien Kamera den Versatz zur Spielkamera merken -- oder nicht.

        Gemerkt wird in den ACHSEN der Spielkamera, nicht in Weltkoordinaten.
        Sonst bliebe eine Schulterkamera beim Drehen stehen: der Spieler
        schwenkt, der Versatz zeigte weiter nach Norden, und die Kamera
        landete vor ihm statt hinter ihm.

        Rueckgabe: der gemerkte Versatz (rechts, hoch, vorwaerts) oder None.
        """
        if not an:
            self._cam_folge = None
            return None
        k = self.cam()
        c = self._cam_ptr
        if k is None or c is None:
            return None
        q, gp = ptcam.lage(k.p, k.spiel)
        q2, cp = ptcam.lage(k.p, c)
        if q is None or q2 is None:
            return None
        r, h, v = ptcam.achsen(q)
        d = [cp[i] - gp[i] for i in range(3)]
        self._cam_folge = (sum(d[i] * r[i] for i in range(3)),
                           sum(d[i] * h[i] for i in range(3)),
                           sum(d[i] * v[i] for i in range(3)))
        return self._cam_folge

    def cam_fuehrt(self):
        """True, wenn gerade aus UNSERER Kamera gerendert wird.

        None heisst: wir haben keine. False heisst: wir haben eine, aber
        jemand steht davor -- in einer Sequenz der Normalfall, bis die
        Schleife in run() den Platz zurueckholt.
        """
        if self._cam_ptr is None:
            return None
        k = self.cam()
        if k is None:
            return None
        try:
            return k.fuehrt(self._cam_ptr)
        except OSError:
            return None

    def cam_move(self, vor=0.0, seite=0.0, welt_hoch=0.0):
        k = self.cam()
        if k is None or k.aktiv() is None:
            return False
        try:
            k.schieben(vor=vor, seite=seite, welt_hoch=welt_hoch)
        except RuntimeError:
            return False
        return True

    def cam_drehen(self, gier=0.0, neig=0.0):
        """Die freie Kamera drehen -- in Grad JE SEKUNDE.

        Wie `cam_fahrt`: die Oberflaeche sagt nur, wie schnell; gerechnet
        wird in diesem Faden mit der tatsaechlich verstrichenen Zeit.
        """
        self._cam_dreh = (float(gier), float(neig))
        if any(self._cam_dreh):
            self._faden_an()

    def cam_winkel(self):
        """Die aktuellen Winkel (Gierung, Neigung) oder None."""
        return self._cam_winkel

    def cam_look(self, gier, neig):
        self._cam_winkel = (float(gier), float(neig))
        k = self.cam()
        if k is None or k.aktiv() is None:
            return False
        try:
            k.setzen(q=ptcam.quat(gier, neig))
        except RuntimeError:
            return False
        return True

    def cam_to_player(self):
        """Die freie Kamera dorthin holen, wo die Spielkamera steht."""
        k = self.cam()
        if k is None or k.aktiv() is None:
            return False
        q, pos = ptcam.lage(k.p, k.spiel)
        if q is None:
            return False
        k.setzen(pos=list(pos[:3]), q=q)
        return True

    # ---------------------------------------------------------- Belichtung
    def expo_find(self):
        """Bloecke suchen und merken. Gehoert in einen HINTERGRUNDLAUF.

        Der Suchlauf geht durch den ganzen Prozessspeicher. Im Takt der
        Oberflaeche aufgerufen wuerde das Fenster stehen -- dieselbe Falle
        wie beim Verbinden, das deshalb schon im Attacher laeuft.
        """
        p, _ = self._proc()
        if p is None:
            return 0
        try:
            found = ptexpo.find(p)
        except OSError:
            return 0
        with self._lock:
            self._expo = found
        return len(found)

    def expo_addrs(self):
        """Prozess und die noch tragfaehigen Adressen.

        Geprueft wird JEDES Mal: nach einem Ladevorgang kann an einer
        gemerkten Adresse etwas ganz anderes liegen, und ein Schreiben ins
        Blaue kostet einen Absturz statt einer Meldung.
        """
        p, _ = self._proc()
        if p is None:
            return None, []
        with self._lock:
            gemerkt = list(self._expo)
        return p, [a for a in gemerkt if ptexpo.gueltig(p, a)]

    def expo_read(self):
        p, a = self.expo_addrs()
        return ptexpo.read(p, a[0]) if a else None

    def expo_set(self, comp=None, hoch=None, tief=None):
        """Setzen. Rueckgabe: Zahl der beschriebenen Bloecke, 0 = keiner."""
        p, a = self.expo_addrs()
        if not a:
            return 0
        return ptexpo.write(p, a, comp=comp, hoch=hoch, tief=tief)

    def _tacho(self, p, o):
        """Waagerechtes Tempo aus der Fussposition -- reine Anzeige."""
        d = p.read(o + self.POS_X, 12)
        if not d or len(d) != 12:
            return
        x = struct.unpack_from('<f', d, 0)[0]
        z = struct.unpack_from('<f', d, 8)[0]
        now = time.time()
        if self._prev_pos is None:
            self._prev_pos = (x, z, now)
            return
        px, pz, pt = self._prev_pos
        dt = now - pt
        if dt < 0.05:                  # nicht jede Mikrorunde messen
            return
        inst = math.hypot(x - px, z - pz) / dt
        # etwas glaetten, sonst zittert die Anzeige unlesbar
        self.hspeed = 0.7 * self.hspeed + 0.3 * inst
        self._prev_pos = (x, z, now)
        # Y liegt zwischen X und Z im selben Block -- kostet keinen Lesevorgang
        # extra. Frueher wurde pos nur alle 20000 Runden gesetzt; fuer den
        # Positionsspeicher auf L1 muss sie aktuell sein.
        self.pos = (x, struct.unpack_from('<f', d, 4)[0], z)

    def run(self):
        zero = struct.pack('<f', 0.0)
        while not self.stop_flag:
            if self._p is None:
                time.sleep(0.05)
                continue
            # Ohne Schweben laeuft die Runde gedrosselt und nur lesend weiter,
            # damit der Tacho lebt. Wird aber angeheftet, muss sie voll laufen:
            # bei 33 Hz gegen ein Spiel, das jedes Bild schreibt, rutscht der
            # Spieler sichtbar weg.
            idle = (not self.running and self._fix is None
                    and not any(self._cam_v) and not any(self._cam_dreh))
            lo = struct.pack('<f', self.height)
            hi = struct.pack('<f', self.height + self._cap)
            try:
                with self._lock:
                    o, p = self._obj, self._p
                    if o is None or p is None:
                        continue       # detach() war schneller
                    if self.running:
                        # BLOCKWEISE statt sieben Einzelschreibvorgaenge: die
                        # zusammenhaengenden Felder werden gelesen, nur die
                        # Y-Anteile ersetzt und in EINEM Zug zurueckgeschrieben.
                        # X, Z und die waagerechte Geschwindigkeit bleiben
                        # dadurch unangetastet -- man kann weiter laufen.
                        #
                        # Zweck ist nicht Geschwindigkeit, sondern dass die
                        # Engine nie einen halb aktualisierten Satz sieht.
                        a = p.read(o + 0x30, 0x18)
                        b = p.read(o + 0x50, 0x28)
                        if a and b:
                            a = bytearray(a)
                            b = bytearray(b)
                            a[0x04:0x08] = lo     # +0x34  Fuesse
                            a[0x14:0x18] = hi     # +0x44  Kapselmitte
                            b[0x04:0x08] = lo     # +0x54
                            b[0x14:0x18] = lo     # +0x64
                            b[0x24:0x28] = zero   # +0x74  Y-Geschwindigkeit
                            p.write(o + 0x30, bytes(a))
                            p.write(o + 0x50, bytes(b))
                            p.write(o + 0x134, lo)
                            p.write(o + 0x194, lo)
                    # Festhalten: waagerecht anheften. Gebraucht wird das bei
                    # der freien Kamera -- der Emulator liest denselben
                    # Controller, der linke Stick laesst also den Spieler
                    # mitlaufen, waehrend man nur die Kamera bewegen wollte.
                    # Nur X und Z, die Hoehe bleibt dem Schweben ueberlassen.
                    if self._fix is not None:
                        c = p.read(o + 0x30, 0x0c)
                        if c and len(c) == 0x0c:
                            c = bytearray(c)
                            c[0x00:0x04] = struct.pack('<f', self._fix[0])
                            c[0x08:0x0c] = struct.pack('<f', self._fix[2])
                            if not self.running:
                                c[0x04:0x08] = struct.pack('<f', self._fix[1])
                            p.write(o + 0x30, bytes(c))
                    self._tacho(p, o)
            except Exception:
                # `running` bleibt STEHEN. Ein einzelner fehlgeschlagener
                # Zugriff -- Ladebildschirm, Stagewechsel, ein Moment ohne
                # Level -- darf das Schweben nicht beenden; sonst hoert es
                # nach Bruchteilen einer Sekunde auf und sieht wie ein Sprung
                # aus. Erst wenn es dauerhaft nicht mehr geht, ist das Spiel
                # wirklich weg.
                self._misses += 1
                if self._misses >= self.MISS_LIMIT:
                    self.running = False
                    self.status = 'game closed'
                time.sleep(0.05)
                continue
            else:
                self._misses = 0
            # Den Vorrang der eigenen Kamera halten. Sequenzen schalten eigene
            # Demo-Kameras ein und sortieren das Feld um; ohne das hier waere
            # der Blick nach dem ersten Umschalten weg. Nur jeder vierte Takt:
            # die Pruefung liest ein Byte je Kamera, und das hat im vollen
            # Takt nichts verloren.
            # Die freie Kamera drehen. Die Winkel werden hier fortge-
            # schrieben und ueber cam_winkel() gemeldet; die Oberflaeche
            # zeigt sie nur noch an.
            if (self._cam_ptr is not None and any(self._cam_dreh)
                    and self._cam_winkel is None):
                # Zweite Sicherung zur oben genannten: kommt eine Drehung an,
                # ohne dass die Winkel stehen, hier nachholen statt sie
                # wegzuwerfen. Kostet nichts, solange der Wert gesetzt ist.
                try:
                    q, _pos = ptcam.lage(self._p, self._cam_ptr)
                    if q is not None:
                        self._cam_winkel = ptcam.winkel(q)
                except Exception:
                    pass
            if (self._cam_ptr is not None and any(self._cam_dreh)
                    and self._cam_winkel is not None):
                jetzt = time.perf_counter()
                dtd = jetzt - (self._dreh_zeit or jetzt)
                self._dreh_zeit = jetzt
                if 0.0 < dtd < 0.25:
                    dg, dn = self._cam_dreh
                    g, n = self._cam_winkel
                    g = (g + dg * dtd + 180.0) % 360.0 - 180.0
                    n = max(-89.0, min(89.0, n + dn * dtd))
                    self._cam_winkel = (g, n)
                    try:
                        k = self.cam()
                        if k is not None:
                            k.setzen(q=ptcam.quat(g, n))
                    except Exception:
                        pass
            else:
                self._dreh_zeit = 0.0

            # Die freie Kamera fahren, mit echter Zeitdifferenz.
            if self._cam_ptr is not None and any(self._cam_v):
                jetzt = time.perf_counter()
                dt = jetzt - (self._cam_zeit or jetzt)
                self._cam_zeit = jetzt
                # Ein zu grosser Abstand heisst: die Schleife stand (Ladebild,
                # Stagewechsel). Den Sprung nachzuholen wuerde die Kamera
                # meterweit versetzen, also wird er verworfen.
                if 0.0 < dt < 0.25:
                    try:
                        k = self.cam()
                        if k is not None:
                            a, b, c = self._cam_v
                            k.schieben(vor=a * dt, seite=b * dt,
                                       welt_hoch=c * dt)
                    except Exception:
                        pass
            else:
                self._cam_zeit = 0.0

            # Dem Spieler folgen. Jeden Takt, nicht jeden vierten: bei
            # 8 Hz ruckelte das sichtbar. Zwei Lesevorgaenge, ein
            # Schreibvorgang -- das traegt.
            if self._cam_ptr is not None and self._cam_folge is not None:
                try:
                    k = self.cam()
                    if k is not None:
                        q, gp = ptcam.lage(k.p, k.spiel)
                        if q is not None:
                            r, h, v = ptcam.achsen(q)
                            a, b, cc = self._cam_folge
                            k.setzen(q=q, pos=[gp[i] + a * r[i] + b * h[i]
                                               + cc * v[i] for i in range(3)])
                except Exception:
                    pass
            self._cam_takt += 1
            if self._cam_ptr is not None and self._cam_takt % 4 == 0:
                try:
                    k = self.cam()
                    if k is None:
                        pass
                    elif self._cam_ptr in k.liste:
                        k.vorrang(self._cam_ptr)
                    else:
                        self._cam_ptr = None
                except Exception:
                    pass
            if idle:
                time.sleep(0.03)
                continue
            # Drosseln. Ohne das laeuft die Schleife durchgehend und die Engine
            # liest immer mitten in einer Folge -- siehe die Messung oben.
            if self.rate > 0:
                nxt = self._next + 1.0 / self.rate
                now = time.perf_counter()
                if nxt > now:
                    time.sleep(nxt - now)
                    self._next = nxt
                else:
                    self._next = now      # nicht aufholen, sonst Dauerlauf
            self.rounds += 1
            if self.rounds % 20000 == 0:
                d = p.read(o + 0x30, 16)
                if not d:
                    self.running = False
                    self.status = 'game closed'
                else:
                    self.pos = struct.unpack('<4f', d)[:3]
