# -*- coding: utf-8 -*-
u"""Freie Kamera fuer P.T. -- vom Spieler geloest.

Was es tut
----------
Nimmt dem Spiel die Kamera ab. Der Spieler bleibt, wo er ist, und laesst sich
weiter steuern; nur der Blick loest sich von ihm.

Moeglich ist das, weil der CameraSelector eine nach Prioritaet sortierte
Kameraliste fuehrt und je Bild aus der ERSTEN Kamera rendert, deren
enable-Byte gesetzt ist. P.T. haelt 32 schlafende Demo-Kameras vor der
Spielkamera -- eine davon einzuschalten genuegt, und niemand schreibt sie
danach neu.

Adressen
--------
    Selektor + 0x80   Anzahl der Kameras
    Selektor + 0x88   Feld der Kamerazeiger, nach Prioritaet sortiert
    Selektor + 0x70   Abbild der gewaehlten Kamera -- NICHT beschreiben,
                      es wird jedes Bild neu befuellt

    Kamera + 0xa8     enable        + 0xb1  Einmal-Schalter
    Kamera + 0xd8     Prioritaet    + 0xe0  Quaternion, + 0xf0 Position

Einschraenkungen
----------------
* Die geliehene Kamera ist eine DEMO-Kamera. Waehrend einer Sequenz fuehrt
  das Spiel selbst welche; vorher `--aus`, sonst bleibt der Blick bei uns.
* Blickrichtung ist die dritte Spalte der Drehmatrix, "rechts" die erste mit
  umgekehrtem Vorzeichen (rechts = vorwaerts x hoch ergibt -x).

    python ptcam.py               Zustand
    python ptcam.py --an          uebernehmen (Lage der Spielkamera)
    python ptcam.py --aus         zurueckgeben
    python ptcam.py --vor 2       zwei Meter in Blickrichtung
    python ptcam.py --seite 1     einen Meter nach rechts
    python ptcam.py --hoch 3      drei Meter nach oben (Weltachse)
    python ptcam.py --pos x y z   an eine feste Stelle
    python ptcam.py --blick 90 -20   Gierung / Neigung in Grad
    python ptcam.py --vorn        in der Liste nach vorn haengen
"""
import math
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hover
import ptmem

SEL_VA = 0x1c4d2d8
O_ABBILD, O_COUNT, O_ARRAY = 0x70, 0x80, 0x88
O_PARAM, PARAM_LEN = 0x30, 0x60      # Brennweite, Blende, Belichtung, Bloom
O_ENABLE, O_EINMAL, O_PRIO = 0xa8, 0xb1, 0xd8
O_QUAT, O_POS = 0xe0, 0xf0


def selector(p, base=None):
    u"""Der CameraSelector. `base` mitgeben, wo sie bekannt ist.

    `hover.find_base` liest die ganze eboot.bin von der Platte und durchsucht
    danach den Prozessspeicher nach dem Ankermuster. Das kostet zehntel
    Sekunden -- vertretbar einmal beim Verbinden, verheerend im Takt der
    Oberflaeche: das Fenster liess sich nur noch ruckelnd verschieben, solange
    die Kameraseite offen war.
    """
    if base is None:
        base = hover.find_base(p)
    if base is None:
        return None
    d = p.read(base + SEL_VA, 8)
    if not d or len(d) < 8:
        return None
    return struct.unpack('<Q', d)[0] or None


def kameras(p, sel):
    d = p.read(sel + O_COUNT, 16)
    if not d or len(d) < 16:
        return []
    n, feld = struct.unpack('<QQ', d)
    n &= 0xffffffff
    if not feld or not 0 < n <= 256:
        return []
    raw = p.read(feld, n * 8)
    if not raw or len(raw) < n * 8:
        return []
    return [c for c in struct.unpack('<%dQ' % n, raw) if c]


def an(p, c):
    d = p.read(c + O_ENABLE, 1)
    return bool(d and d[0])


def lage(p, c):
    d = p.read(c + O_QUAT, 0x20)
    if not d or len(d) < 0x20:
        return None, None
    return struct.unpack_from('<4f', d, 0), struct.unpack_from('<4f', d, 0x10)


def matrix(q):
    u"""Drehmatrix aus (x, y, z, w) -- dieselbe Rechnung wie in camview."""
    x, y, z, w = q
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def achsen(q):
    u"""rechts, hoch, vorwaerts -- aus den SPALTEN der Drehmatrix.

    Dass die dritte Spalte die Blickrichtung ist, steht nicht in der Doku,
    sondern folgt aus der View-Matrix im Konstantenpuffer: deren dritte Zeile
    ist die Tiefenrichtung, und sie ist genau diese Spalte.

    Die erste Spalte zeigt nach LINKS, nicht nach rechts. Gemeldet hat es der
    Nutzer (Stick nach rechts, Kamera nach links), nachrechnen laesst es sich
    aber auch: in einem rechtshaendigen System ist

        rechts = vorwaerts x hoch

    und mit vorwaerts = +z, hoch = +y ergibt das -x. Deshalb das Minus, und
    zwar an EINER Stelle: Stick, Tastatur, die Knoepfe und `--seite` benutzen
    alle dieselbe Achse. Wer nur den Stick dreht, macht die uebrigen drei
    falsch.
    """
    R = matrix(q)
    return ([-R[0][0], -R[1][0], -R[2][0]],
            [R[0][1], R[1][1], R[2][1]],
            [R[0][2], R[1][2], R[2][2]])


def quat(gier, neig):
    u"""Quaternion aus Gierung (um die Welt-y-Achse) und Neigung.

    Die Neigung wird negiert, weil eine Drehung um +x die Blickrichtung nach
    UNTEN kippt: die dritte Spalte von R_x(b) ist (0, -sin b, cos b). Ohne das
    meldet `winkel` das Gegenteil dessen, was man eingegeben hat -- gepruefte
    Rueckrechnung, kein Geschmack.
    """
    a, b = math.radians(gier) / 2.0, math.radians(-neig) / 2.0
    x1, y1, z1, w1 = 0.0, math.sin(a), 0.0, math.cos(a)
    x2, y2, z2, w2 = math.sin(b), 0.0, 0.0, math.cos(b)
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def winkel(q):
    u"""Gierung und Neigung in Grad -- aus der Blickrichtung zurueckgerechnet."""
    _, _, vor = achsen(q)
    gier = math.degrees(math.atan2(vor[0], vor[2]))
    neig = math.degrees(math.asin(max(-1.0, min(1.0, vor[1]))))
    return gier, neig


class Kamera(object):
    u"""Spielkamera und freie Kamera, aufgeloest aus der Liste."""

    def __init__(self, p, base=None):
        self.p = p
        self.sel = selector(p, base)
        if not self.sel:
            raise RuntimeError('Selektor nicht aufloesbar -- Level geladen?')
        self.liste = kameras(p, self.sel)
        if not self.liste:
            raise RuntimeError('Kameraliste leer')
        self.abbild = struct.unpack('<Q', p.read(self.sel + O_ABBILD, 8))[0]
        # Schalter und Prioritaet je Kamera, einmal gelesen. `spiel` und
        # `aktiv` gehen beide ueber die ganze Liste; ohne diesen Zwischenhalt
        # sind das bei 33 Kameras ueber hundert Einzelzugriffe je Abfrage.
        self._flags = {}
        # Der Zeiger, den WIR eingeschaltet haben. Wird von aussen
        # gesetzt; ohne ihn faellt aktiv() auf die alte Regel zurueck.
        self.unsere = None
        # Der Zeiger, den WIR eingeschaltet haben. Wird von aussen
        # gesetzt; ohne ihn faellt aktiv() auf die alte Regel zurueck.
        self.unsere = None

    def _flag(self, c):
        f = self._flags.get(c)
        if f is None:
            d = self.p.read(c + O_ENABLE, O_PRIO - O_ENABLE + 1)
            f = ((d[0], d[-1]) if d and len(d) == O_PRIO - O_ENABLE + 1
                 else (0, 255))
            self._flags[c] = f
        return f

    def prio(self, c):
        return self._flag(c)[1]

    @property
    def spiel(self):
        u"""Die Spielkamera: die eingeschaltete mit der SCHWAECHSTEN Prioritaet.

        Nicht einfach "die letzte eingeschaltete": sobald unsere freie Kamera
        die einzige eingeschaltete ist, waere das unsere eigene, und `aktiv`
        faende nichts mehr. Die Prioritaet trennt beide sauber -- die
        Spielkamera hat 3 ("Game"), die Demo-Kameras 2.

        Sie ist der Bezug fuer die Uebernahme: von ihr werden Lage und
        Bildparameter kopiert, damit das Bild beim Einschalten nicht springt.
        """
        beste = None
        for c in self.liste:
            # Die eigene Kamera kommt nie in Frage. Solange die Spielkamera
            # mitlaeuft, gewinnt sie ohnehin mit Rang 3 -- aber in einer
            # Sequenz ist sie aus, und dann bliebe unsere uebrig. `spiel`
            # lieferte dann uns selbst, und alles, was sich auf die
            # Spielkamera bezieht, bezoege sich auf die eigene Lage:
            # "back to the player" kopierte uns auf uns selbst und tat
            # sichtbar nichts. Im Spiel am 20.09.2026 aufgefallen.
            if c == self.unsere:
                continue
            if not self._flag(c)[0]:
                continue
            if beste is None or self.prio(c) >= self.prio(beste):
                beste = c
        if beste is None:
            # Nichts eingeschaltet: das ist ein Zwischenzustand (Laden,
            # Menue). Der letzte Eintrag ist die beste Vermutung, aber nie
            # die eigene.
            for c in reversed(self.liste):
                if c != self.unsere:
                    return c
        return beste or self.liste[-1]

    def ruhig(self, dauer=0.30):
        u"""Welche schlafenden Kameras schreibt gerade NIEMAND?

        Waehrend einer Sequenz fuehrt das Spiel selbst Demo-Kameras -- und
        genau die haben wir uns geliehen. Wer eine beschriebene erwischt,
        kommt vom Fleck nicht weg, und das sieht von aussen aus, als greife
        die Uebernahme nicht. Der Unterschied ist messbar: eine ungenutzte
        Kamera aendert ihre Lage in 0,3 Sekunden um kein Bit.
        """
        vorher = {}
        for c in self.liste:
            d = self.p.read(c + O_QUAT, 0x20)
            if d and len(d) == 0x20:
                vorher[c] = d
        time.sleep(dauer)
        out = []
        for c, d0 in vorher.items():
            d1 = self.p.read(c + O_QUAT, 0x20)
            if d1 == d0:
                out.append(c)
        return out

    def unbenutzt(self, c):
        u"""Hat diese Kamera noch nie jemand beschrieben?

        Am 20.09.2026 gemessen: die Kameras, die das Spiel fuehrt, tragen
        eine eigene Lage -- die der Startsequenz sogar die der Spielkamera.
        Alle uebrigen stehen auf exakt 0/0/0 und bleiben es, auch ueber 25 s
        mit gesetztem enable-Byte. Eine Lage von null heisst also: frei.

        Anhaltspunkt, keine Garantie. Nach einem Ladevorgang steht eine
        Kamera wieder auf null und kann danach doch in Gebrauch gehen.
        """
        d = self.p.read(c + O_POS, 12)
        if not d or len(d) != 12:
            return False
        return max(abs(v) for v in struct.unpack('<3f', d)) < 0.001

    def benutzte(self):
        u"""Die Kameras, die das Spiel fuehrt -- ohne die Spielkamera.

        Erkannt an der Lage: was nie beschrieben wurde, steht auf 0/0/0.
        Wer durch eine Sequenzkamera sehen will, waehlt aus dieser Liste.
        """
        spiel = self.spiel
        return [c for c in self.liste
                if c != spiel and not self.unbenutzt(c)]

    def freie(self, ruhig=None):
        u"""Eine schlafende Kamera VOR der Spielkamera.

        Nur solche kommen in Frage: die Schleife bricht beim ersten
        eingeschalteten Eintrag ab, eine Kamera dahinter kaeme nie an die
        Reihe. Einmal-Kameras (+0xb1) scheiden aus, die schalten sich nach
        einem Bild selbst wieder ab.

        ZWEI DURCHGAENGE. Erst die unbenutzten: die Startsequenz fuehrt die
        Kamera, die vorn in der Liste steht, und wer von vorn nimmt, erwischt
        genau sie -- die Lage wird dann jedes Bild ueberschrieben, und der
        Blick springt zurueck. Ist keine unbenutzte uebrig, gilt die alte
        Reihenfolge; eine Kamera, die spaeter jemand an sich nimmt, ist immer
        noch besser als gar keine.
        """
        spiel = self.spiel

        def geht(c):
            if self._flag(c)[0]:
                return False
            d = self.p.read(c + O_EINMAL, 1)
            if d and d[0]:
                return False
            return not (ruhig is not None and c not in ruhig)

        for nur_unbenutzte in (True, False):
            for c in self.liste:
                if c == spiel:
                    break
                if not geht(c):
                    continue
                if nur_unbenutzte and not self.unbenutzt(c):
                    continue
                return c
        return None

    def irgendeine_ruhige(self, ruhig):
        u"""Eine ruhige, schlafende Kamera -- egal an welcher Stelle.

        Notnagel fuer den Fall, dass vor der gerade fuehrenden Kamera keine
        ruhige mehr steht. Sie wird dann per `nach_vorn` an Position 0
        gehaengt.
        """
        for c in self.liste:
            if self._flag(c)[0]:
                continue
            d = self.p.read(c + O_EINMAL, 1)
            if d and d[0]:
                continue
            if c in ruhig:
                return c
        return None

    def nach_vorn(self, cam):
        u"""Den Zeiger dieser Kamera auf Platz 0 des Feldes tauschen.

        Das Feld bei Selektor+0x88 ist eine schlichte Zeigerliste, und die
        Update laeuft sie der Reihe nach ab. Wer vorn steht, gewinnt -- auch
        gegen eine Sequenz. Getauscht, nicht eingefuegt: so bleibt die Laenge
        gleich, und ein Tausch laesst sich mit denselben zwei Schreibvorgaengen
        zuruecknehmen.

        Der Tausch wird NICHT zurueckgenommen, und das ist kein Versaeumnis:
        die Reihenfolge unter den schlafenden Demo-Kameras hat keine
        Bedeutung. Entscheidend ist nur, ob eine eingeschaltete Kamera vor der
        Spielkamera steht -- und die Spielkamera wird hier nie angefasst, sie
        sitzt am Ende der Liste. Schaltet eine Sequenz ihre Kamera ein, ist das
        weiterhin die einzige eingeschaltete Demo-Kamera und gewinnt, ganz
        gleich an welcher Stelle sie steht. Beim naechsten Ladevorgang baut das
        Spiel die Liste ohnehin neu.

        Rueckgabe: (index, alter_zeiger_auf_0) zum Zuruecknehmen, oder None,
        wenn die Kamera schon vorn steht.
        """
        d = self.p.read(self.sel + O_COUNT, 16)
        n, feld = struct.unpack('<QQ', d)
        n &= 0xffffffff
        raw = self.p.read(feld, n * 8)
        zeiger = list(struct.unpack('<%dQ' % n, raw))
        if not zeiger or zeiger[0] == cam:
            return None
        i = zeiger.index(cam)
        self.p.write(feld, struct.pack('<Q', cam))
        self.p.write(feld + i * 8, struct.pack('<Q', zeiger[0]))
        self.liste = kameras(self.p, self.sel)
        return (i, zeiger[0])

    def aktiv(self):
        u"""Die Kamera, die WIR genommen haben -- sonst die erste eingeschaltete.

        Der Unterschied entscheidet in Sequenzen. Die schalten eigene
        Demo-Kameras ein; "die erste eingeschaltete" waere dann deren, und
        das Werkzeug haette eine fremde Kamera fuer seine gehalten. Ist
        `unsere` gesetzt und steht der Zeiger noch in der Liste, gilt er --
        auch wenn gerade jemand anders vorn steht. Dass wir den Vorrang
        verloren haben, beantwortet `fuehrt()`, nicht diese Frage hier.
        """
        if self.unsere and self.unsere in self.liste:
            return self.unsere
        spiel = self.spiel
        for c in self.liste:
            if c == spiel:
                return None
            if self._flag(c)[0]:
                return c
        return None

    def erste_an(self):
        u"""Die erste eingeschaltete Kamera der Liste -- aus der rendert das
        Spiel. Gemessen: es zaehlt der Platz, nicht der Rang."""
        for c in self.liste:
            if self._flag(c)[0]:
                return c
        return None

    def fuehrt(self, c):
        u"""Rendert das Spiel gerade aus DIESER Kamera?"""
        self._flags.clear()
        return bool(c) and self.erste_an() == c

    def vorrang(self, c):
        u"""`c` wieder an die Spitze holen. Gibt zurueck, was noetig war.

        Zwei Dinge koennen fehlen, und eine Sequenz nimmt beide: das
        enable-Byte, das sie beim Umschalten loescht, und den Platz, wenn sie
        das Feld umsortiert. Geschrieben wird nur, was tatsaechlich fehlt --
        das hier laeuft im Takt.
        """
        getan = []
        self._flags.clear()
        if not self._flag(c)[0]:
            self.p.write(c + O_ENABLE, b'\x01')
            self._flags.pop(c, None)
            getan.append('enable')
        if self.erste_an() != c and self.nach_vorn(c) is not None:
            getan.append('vorn')
        return getan

    # --- Steuerung ---------------------------------------------------------
    def infos(self):
        u"""Alle Kameras der Liste, fuer die Auswahl in der Oberflaeche.

        Der Flaggenspeicher wird vorher geleert: eine Liste, die alte Werte
        zeigt, waere schlimmer als gar keine.
        """
        self._flags.clear()
        aus = []
        for i, c in enumerate(self.liste):
            an, prio = self._flag(c)
            q, pos = lage(self.p, c)
            aus.append({'nr': i, 'ptr': c, 'an': bool(an), 'prio': prio,
                        'pos': tuple(pos[:3]) if pos is not None else None,
                        'frei': self.unbenutzt(c), 'spiel': c == self.spiel})
        return aus

    def uebernehmen(self, cam=None, pose=None):
        u"""Eine ruhige Kamera nehmen -- notfalls nach vorn haengen.

        Zwei Dinge koennen schieflaufen, und von aussen sehen sie gleich aus
        ("die Kamera bewegt sich nicht"):

          * wir haben eine Kamera erwischt, die das Spiel gerade selbst
            beschreibt (waehrend einer Sequenz) -- dagegen hilft `ruhig`
          * vor uns steht eine eingeschaltete Kamera und gewinnt -- dagegen
            hilft `nach_vorn`

        Deshalb beides, in dieser Reihenfolge.

        Mit `cam` wird genau diese genommen. Eine bereits aktive andere wird
        dabei ABGESCHALTET -- sonst gewinnt sie weiter, wenn sie vor der
        gewaehlten steht, und die Auswahl sieht wirkungslos aus.
        """
        alt = self.aktiv()
        if cam is None:
            # NUR die eigene zaehlt. `aktiv()` faellt ohne `unsere` auf "die
            # erste eingeschaltete" zurueck -- und in einer Sequenz ist das
            # DEREN Kamera. Sie hier zurueckzugeben hiesse, sie zu
            # uebernehmen: das Werkzeug haelt danach den Vorrang einer fremden
            # Kamera, der Nutzer sieht die Sequenz und kommt nicht heraus.
            # Am 20.09.2026 in der Startsequenz passiert.
            if alt and alt == self.unsere:
                return alt
            still = self.ruhig()
            c = self.freie(ruhig=still)
            self.getauscht = None
            if not c:
                c = self.irgendeine_ruhige(still)
                if not c:
                    raise RuntimeError('keine ruhige schlafende Kamera gefunden')
                self.getauscht = self.nach_vorn(c)
        else:
            if cam not in self.liste:
                raise RuntimeError('diese Kamera steht nicht in der Liste')
            if cam == self.spiel:
                # Die Spielkamera als eigene zu merken verdirbt spiel():
                # das schliesst die eigene aus, und dann gilt eine
                # Demo-Kamera als Spielkamera.
                raise RuntimeError('die Spielkamera laesst sich nicht leihen')
            c = cam
            if alt and alt != c:
                self.p.write(alt + O_ENABLE, b'\x00')
                self._flags.pop(alt, None)
            self.getauscht = None
            if self.liste.index(c) > self.liste.index(self.spiel):
                self.getauscht = self.nach_vorn(c)
        s = self.spiel
        # `pose` entscheidet, ob die Lage der Spielkamera hineinkopiert wird.
        # True: ja (freie Kamera, sonst Weltursprung). False: nein (man will
        # durch die gewaehlte hindurchsehen). None: wie bisher geraten.
        if pose is True or (pose is None and (cam is None or self.unbenutzt(c))):
            # Eine nie beschriebene Kamera steht auf 0/0/0 -- dem
            # Weltursprung, meist weit ausserhalb des Raums. Sie bekommt
            # deshalb Lage und Parameter der Spielkamera, damit der Blick
            # dort anfaengt, wo man gerade steht. Dasselbe gilt fuer die
            # selbsttaetige Wahl: wer nichts aussucht, will keinen Sprung.
            self.p.write(c + O_PARAM, self.p.read(s + O_PARAM, PARAM_LEN))
            self.p.write(c + O_QUAT, self.p.read(s + O_QUAT, 0x20))
        # Eine ausdruecklich gewaehlte Kamera, die das Spiel fuehrt, traegt
        # ihre EIGENE Lage. Die bleibt stehen -- wer sie aussucht, will durch
        # sie hindurchsehen, nicht sie ueberschreiben.
        self.p.write(c + O_ENABLE, b'\x01')
        self._flags.pop(c, None)
        # Zum Schluss den Platz sichern. `freie()` liefert eine schlafende
        # Kamera VOR der Spielkamera -- das genuegt aber nicht, wenn eine
        # fremde eingeschaltete noch weiter vorn steht, wie in einer Sequenz.
        # Frueher wurde nur im Notfallzweig nach vorn gehaengt; wer mitten in
        # einer Sequenz uebernahm, bekam eine Kamera, die nie an die Reihe kam.
        if self.erste_an() != c:
            self.nach_vorn(c)
        return c

    def erzwingen(self):
        u"""Die aktive freie Kamera an Position 0 haengen.

        Fuer den Fall, dass eine Sequenz mitten im Betrieb eine Kamera vor
        unserer einschaltet. Rueckgabe: True, wenn getauscht wurde.
        """
        c = self.aktiv()
        if not c:
            for x in self.liste:
                if self._flag(x)[0] and x != self.spiel:
                    c = x
                    break
        if not c:
            raise RuntimeError('keine freie Kamera aktiv -- erst --an')
        return self.nach_vorn(c) is not None

    def freigeben(self):
        c = self.aktiv()
        if c:
            self.p.write(c + O_ENABLE, b'\x00')
        return c

    def setzen(self, pos=None, q=None):
        c = self.aktiv()
        if not c:
            raise RuntimeError('keine freie Kamera aktiv -- erst --an')
        q0, p0 = lage(self.p, c)
        if q is not None:
            self.p.write(c + O_QUAT, struct.pack('<4f', q[0], q[1], q[2], q[3]))
        if pos is not None:
            self.p.write(c + O_POS,
                         struct.pack('<4f', pos[0], pos[1], pos[2], p0[3]))
        return c

    def schieben(self, vor=0.0, seite=0.0, hoch=0.0, welt_hoch=0.0):
        c = self.aktiv()
        if not c:
            raise RuntimeError('keine freie Kamera aktiv -- erst --an')
        q, pos = lage(self.p, c)
        r, u, f = achsen(q)
        neu = [pos[i] + vor * f[i] + seite * r[i] + hoch * u[i]
               for i in range(3)]
        neu[1] += welt_hoch
        return self.setzen(pos=neu)


def _zeig(k):
    c = k.aktiv()
    s = k.spiel
    q, pos = lage(k.p, s)
    print('  Selektor 0x%x, %d Kameras' % (k.sel, len(k.liste)))
    print('  Spielkamera 0x%x  %.3f %.3f %.3f' % ((s,) + tuple(pos[:3])))
    if c:
        q, pos = lage(k.p, c)
        g, n = winkel(q)
        print('  FREIE KAMERA 0x%x aktiv' % c)
        print('     Position %.3f %.3f %.3f' % tuple(pos[:3]))
        print('     Blick    Gierung %.1f  Neigung %.1f' % (g, n))
    else:
        print('  keine freie Kamera aktiv (naechste waere 0x%x)'
              % (k.freie() or 0))


def main():
    a = sys.argv[1:]
    if not ptmem.find_pid():
        sys.exit('  shadPS4 laeuft nicht')
    k = Kamera(ptmem.Proc(ptmem.find_pid()))
    if not a:
        _zeig(k)
        print()
        print('  --an / --aus / --vor n / --seite n / --hoch n')
        print('  --pos x y z / --blick gierung neigung')
        return
    if a[0] == '--an':
        c = k.uebernehmen()
        print('  freie Kamera 0x%x uebernommen' % c)
        _zeig(k)
    elif a[0] == '--aus':
        print('  zurueckgegeben' if k.freigeben() else '  war nicht aktiv')
    elif a[0] == '--vorn':
        print('  nach vorn gehaengt' if k.erzwingen() else '  stand schon vorn')
        _zeig(k)
    elif a[0] in ('--vor', '--seite', '--hoch') and len(a) == 2:
        schluessel = {'--vor': 'vor', '--seite': 'seite',
                      '--hoch': 'welt_hoch'}[a[0]]
        k.schieben(**{schluessel: float(a[1])})
        _zeig(k)
    elif a[0] == '--pos' and len(a) == 4:
        k.setzen(pos=[float(x) for x in a[1:]])
        _zeig(k)
    elif a[0] == '--blick' and len(a) == 3:
        k.setzen(q=quat(float(a[1]), float(a[2])))
        _zeig(k)
    else:
        sys.exit('  unbekannt: %s' % ' '.join(a))


if __name__ == '__main__':
    main()
