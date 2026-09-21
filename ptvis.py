"""Versteckte Objekte ZUR LAUFZEIT ein- und ausblenden -- ohne Archivneubau.

Im Spiel bestaetigt am 11.09.2026: reine Schreibvorgaenge genuegen, kein
eboot-Eingriff. 120 versteckte Objekte auf sichtbar gesetzt -> sie erschienen.

Was geschrieben wird
--------------------
    ent + 0xb8   flags        7 statt 6      (TransformData_Flags, Bit 0 =
                                              ENABLE_VISIBILITY)
    body+ 0x81   isGeomActive 1 statt 0
    grmodel+0x1ac              0 statt -1    <- der eigentliche Zeichenschalter

`body+0x80` (isVisible) steht bei sichtbar UND versteckt auf 1 und
unterscheidet nichts -- wird trotzdem mitgeschrieben, damit der Satz zu dem
passt, was `FUN_007c7200` hinterlaesst.

Jedes versteckte Objekt hat schon ein Grafikmodell (`body+0xf0` ist nie 0).
Die Modelle sind also geladen; es fehlt nur der Zeichenwert.

Wie die Objekte gefunden werden
-------------------------------
Nicht ueber die Namens-Hashtabelle -- die Verwaltung bei 0x1c83318 fuehrt nur
die 46 Gimmick-Eintraege, nicht den Flur (gemessen). Sondern ueber den vptr:

    StaticModel-vptr  VA 0x1bb99a0
    286 Fundstellen = 2 x 143      P.T. haelt zwei Flurkopien
    162 x flags 7 / 124 x flags 6  = 2 x (81 / 62)

Alle drei Zahlen deckungsgleich mit `ptobjects.py` -- damit ist die Zuordnung
belegt, ohne einen einzigen Hash.

**Der Name steht im Klartext daneben:**

    block = [ent + 0x28]
      +0x08 u32 Laenge   +0x10 u64 StrCode64   +0x1c ASCII, NUL-terminiert
      "pt14_hallway|pt14_hallway_environ|shsb_bath001_ocho001_0000"

Drei Ebenen: `environ`, `gimmick`, `nazo`. Die Gimmick-Labels der Engine sind
dieselben Objekte unter anderem Namen (PhotoLisa = shsb_labl001_mapc004_lisa).

Warum es gehalten werden muss
-----------------------------
Bei jedem Stagewechsel werden die flags frisch aus der Datei gelesen -- die
Aenderung ist dann weg. Deshalb `--hold`: dieselbe Bauart wie beim Tempo, das
alle 500 ms nachgezogen wird. Der Suchlauf kostet 9 Sekunden, die Pruefung
danach nichts, also wird die Liste gemerkt und nur bei Bedarf neu gesucht.

    python ptvis.py                       auflisten
    python ptvis.py --hidden --grep ocho  filtern
    python ptvis.py --show ocho           einmalig setzen
    python ptvis.py --hide mirr001
    python ptvis.py --show-all-hidden     alles Versteckte zeigen
    python ptvis.py --hold ocho,blod      halten, bis Strg+C
    python ptvis.py --diag mirr001       alle Felder eines Objekts zeigen
    python ptvis.py --toggletest mirr001 aus/ein messen -- was aendert die Engine
    python ptvis.py --relink mirr001     nur wieder einhaengen
    python ptvis.py --slim ...           ohne body+0x80/0x81 schreiben
    python ptvis.py --norelink ...       ohne Einhaengen (relink ist aus)
    python ptvis.py --bothcopies ...     BEIDE Flurkopien schreiben

Geschrieben wird sonst nur die Kopie, in der der Spieler steht. P.T.
haelt zwei Fluere mit verschiedenen Zustaenden; die fremde traegt, was
das Spiel fuer den naechsten Loop vorbereitet hat.

Einblenden haengt das Modell noetigenfalls selbst wieder in die Zeichenliste
ein (`relink`, `FUN_00ceb450` nachgebaut). Das war die Ursache dafuer, dass
"aus" sofort wirkte und "ein" erst nach einem Stagewechsel.

Die Spalte `Liste` sagt, ob das Grafikmodell in der Zeichenliste haengt
(`grmodel+0x24` Bit 0). Steht dort `nein`, kann kein Zeichenwert es sichtbar
machen -- dann ist die gemeldete Unsymmetrie erklaert.
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hover
import ptmem

SM_VT = 0x1BB99A0           # vptr der StaticModel-Entities
VIS_BIT = 1                 # ENABLE_VISIBILITY

E_NAMEBLOCK = 0x28
E_COMPONENTS = 0x48
E_FLAGS = 0xB8
E_STATE = 0xBC
E_WORLD = 0xF0              # letzte Zeile der Weltmatrix = Position

N_LEN = 0x08                # im Namensblock: Laenge
N_HASH = 0x10               #                StrCode64 des Namens
N_TEXT = 0x1C               #                der Text, NUL-terminiert

B_ISVISIBLE = 0x80          # StaticModelBody
B_ISGEOM = 0x81
B_GRMODEL = 0xF0
G_DRAW = 0x1AC              # 0 = gezeichnet, -1 = nicht
G_LINK = 0x24               # Bit 0: in der Zeichenliste (FUN_00ceb450/630)
G_SCENE = 0x28              # die Szene, in deren Liste es haengt
G_PREV = 0x10               # Verkettung -- intrusiv, im Modell selbst
G_NEXT = 0x18
# WIDERLEGT am 14.09.2026: diese drei Offsets sind NICHT Kopf, Ende und Anzahl
# der Zeichenliste. Im Flur gemessen -- die Kette hat 306 Knoten (Kopf
# 0x34f41c360, Ende 0x347e3bf80), und das Objekt bei `grmodel+0x28` enthaelt
# keinen dieser Werte; +0x40, +0x48 und +0x50 lesen alle 0. Sie stehen nur noch
# hier, damit niemand sie erneut als Listenzeiger raet.
S_HEAD = 0x40               # WIDERLEGT
S_TAIL = 0x48               # WIDERLEGT
# Dass die Engine die Liste genau `Anzahl` mal ablaeuft und den Knotenzeiger
# NICHT prueft, ist aus FUN_00cec1f0 bei 0xcec2b7 zerlegt und bleibt richtig --
# nur steht diese Anzahl nicht hier. Wer je wieder einhaengt, muss erst den
# echten Besitzer finden UND mitzaehlen.
S_COUNT = 0x50              # WIDERLEGT
# Obergrenze beim Zaehlen der Kette: eine schon ringfoermig kaputte Liste soll
# das Werkzeug nicht haengen lassen.
WALK_MAX = 4096

HOLD_MS = 500               # wie beim Tempo: alle halbe Sekunde nachziehen


class Mem:
    """Lesehilfe, die None liefert statt zu werfen -- damit jeder Schritt
    einzeln sagen kann, wo die Kette abreisst."""

    def __init__(self, p):
        self.p = p

    def u64(self, a):
        d = self.p.read(a, 8) if a else None
        return struct.unpack('<Q', d)[0] if d and len(d) == 8 else None

    def u32(self, a):
        d = self.p.read(a, 4) if a else None
        return struct.unpack('<I', d)[0] if d and len(d) == 4 else None

    def i32(self, a):
        v = self.u32(a)
        return None if v is None else (v - (1 << 32) if v >> 31 else v)

    def u8(self, a):
        d = self.p.read(a, 1) if a else None
        return d[0] if d else None

    def text(self, a, cap=160):
        d = self.p.read(a, cap) if a else None
        if not d:
            return ''
        i = d.find(b'\0')
        return d[:i if i >= 0 else cap].decode('ascii', 'replace')

    def weak(self, cell):
        """[[zelle] + 0x18] -- Fox' schwacher Zeiger, ueberall derselbe Bau."""
        ctl = self.u64(cell)
        return self.u64(ctl + 0x18) if ctl else None


def find_entities(p, base):
    """Alle StaticModel-Entities ueber ihren vptr. Kostet rund 9 Sekunden."""
    pat = struct.pack('<Q', SM_VT + base)
    out = []
    for b, s in p.regions():
        if s > 0x10000000:
            continue
        blob = p.read(b, s)
        if not blob:
            continue
        i = blob.find(pat)
        while i >= 0:
            if i % 16 == 0:
                out.append(b + i)
            i = blob.find(pat, i + 8)
    return out


def _regions(p):
    return [(b, sz) for b, sz in p.regions() if sz <= 0x10000000]


def _blocks_to_entities(p, blocks, log=None):
    """Zu Namensbloecken die Entities finden: irgendwo steht ein Zeiger auf den
    Block, und der steht bei `ent+0x28`.

    Einmal pro Region mit numpy gegen alle Bloecke zusammen -- nicht je Block
    einzeln durch jede Region. Der alte Weg war quadratisch und sah bei weiten
    Mustern wie ein Absturz aus.
    """
    import numpy as np
    if not blocks:
        return []
    targets = np.array(sorted(set(blocks)), dtype='<u8')
    out = []
    for b, sz in _regions(p):
        blob = p.read(b, sz)
        if not blob or len(blob) < 8:
            continue
        n = (len(blob) // 8) * 8
        arr = np.frombuffer(blob[:n], dtype='<u8')
        for i in np.nonzero(np.isin(arr, targets))[0]:
            i = int(i)
            out.append((b + i * 8 - E_NAMEBLOCK, int(arr[i])))
    if log:
        log('  %d Entity-Treffer' % len(out))
    return out


def find_by_names(p, names, log=None):
    """Entities zu bekannten VOLLEN Namen finden -- exakt, ohne Textsuche.

    Der Namensblock fuehrt bei +0x10 den StrCode64 des Namens. Den koennen wir
    offline berechnen (`strcode.py`, gegen 8727 Paare geprueft), also wird
    genau danach gesucht: Block = Fundstelle - 0x10.

    Rueckgabe: {voller Name: [Entity-Adressen]}
    """
    import numpy as np
    import strcode
    want = {}
    for nm in names:
        want.setdefault(strcode.strcode64(nm) & ((1 << 48) - 1), nm)
    keys = np.array(sorted(want), dtype='<u8')
    MASK = np.uint64((1 << 48) - 1)

    blocks = {}
    for b, sz in _regions(p):
        blob = p.read(b, sz)
        if not blob or len(blob) < 8:
            continue
        n = (len(blob) // 8) * 8
        arr = np.frombuffer(blob[:n], dtype='<u8') & MASK
        for i in np.nonzero(np.isin(arr, keys))[0]:
            i = int(i)
            blocks[b + i * 8 - N_HASH] = want[int(arr[i])]
    if log:
        log('  %d Namensbloecke fuer %d Namen' % (len(blocks), len(want)))

    out = {}
    for ent, blk in _blocks_to_entities(p, list(blocks), log=log):
        nm = blocks.get(blk)
        if nm:
            out.setdefault(nm, []).append(ent)
    return out


def find_named(p, text, log=None, cap=20000):
    """Entities finden, deren Name diesen Text ENTHAELT.

    Der Blockanfang wird ueber die Selbstreferenz gefunden: der Block beginnt
    mit einem Zeiger auf sein eigenes Textfeld, also `u64[B] == B + 0x1c`.
    Vorher wurde `Fund - 0x1c` gerechnet -- das stimmt nur, wenn das Muster am
    Anfang des Namens steht, und lieferte bei `trap_` nur Zufallstreffer.

    Wer die vollen Namen kennt, nimmt besser `find_by_names()`.
    """
    pat = text.encode('ascii')
    regions = _regions(p)
    blocks = set()
    for b, sz in regions:
        blob = p.read(b, sz)
        if not blob:
            continue
        i = blob.find(pat)
        while i >= 0 and len(blocks) <= cap:
            # rueckwaerts den Blockanfang suchen
            for back in range(0, 0x100, 8):
                o = (i - back) & ~7
                if o < 0 or o + 8 > len(blob):
                    continue
                v = struct.unpack_from('<Q', blob, o)[0]
                if v == b + o + N_TEXT:
                    blocks.add(b + o)
                    break
            i = blob.find(pat, i + 1)
    if log:
        log('  %d Namensbloecke fuer %r' % (len(blocks), text))
    return _blocks_to_entities(p, list(blocks), log=log)


def body_of(m, ent):
    """StaticModelBody der Entity -- FUN_004e8c40 nachgebaut."""
    cont = m.u64(ent + E_COMPONENTS)
    if not cont or not m.u64(cont + 0x10):
        return None
    first = m.u64(cont + 8)
    elem0 = m.u64(first) if first else None
    return m.weak(elem0 + 0x20) if elem0 else None


class Session:
    """Gemerkte Objektliste. Der Suchlauf kostet Sekunden, die Pruefung
    nichts -- also einmal suchen und danach nur noch nachsehen, ob die
    Adressen noch stimmen."""

    def __init__(self, p=None):
        self.p = p or ptmem.Proc(ptmem.find_pid())
        self.m = Mem(self.p)
        self.base = hover.find_base(self.p)
        self.rows = []
        self.full = True        # voller Schreibsatz -- Verstecken ist damit
                                # belegt; das Einblenden heilt der Relink
        self.relink_on_show = True
        # Nur die Kopie beschreiben, in der der Spieler steht. P.T. haelt zwei
        # Flurkopien mit VERSCHIEDENEN Zustaenden; die fremde traegt, was das
        # Spiel fuer den naechsten Loop vorbereitet hat, und die zu
        # ueberschreiben ist nicht nur wirkungslos, sondern womoeglich
        # schaedlich.
        self.own_copy_only = True

    def ok(self):
        return self.base is not None

    def valid(self):
        """Billige Stichprobe: stimmen vptr und Name noch?"""
        if not self.rows:
            return False
        want = SM_VT + self.base
        for r in self.rows[::max(1, len(self.rows) // 8)]:
            if self.m.u64(r['ent']) != want:
                return False
        return True

    def scan(self, log=None):
        m = self.m
        rows = []
        for e in find_entities(self.p, self.base):
            nb = m.u64(e + E_NAMEBLOCK)
            full = m.text(nb + N_TEXT) if nb else ''
            parts = full.split('|')
            body = body_of(m, e)
            d = self.p.read(e + E_WORLD, 12)
            rows.append({
                'ent': e, 'full': full, 'short': parts[-1] if parts else '',
                'layer': (parts[1].replace('pt14_hallway_', '')
                          if len(parts) > 2 else ''),
                'body': body,
                'gr': m.u64(body + B_GRMODEL) if body else None,
                'link': (m.u32(m.u64(body + B_GRMODEL) + G_LINK)
                         if body and m.u64(body + B_GRMODEL) else None),
                'pos': struct.unpack('<3f', d) if d else (0.0, 0.0, 0.0)})
        rows.sort(key=lambda r: (r['short'], r['ent']))
        self.rows = rows
        if log:
            vis = sum(1 for r in rows if self.is_on(r))
            log('  %d StaticModel  (%d sichtbar, %d versteckt)'
                % (len(rows), vis, len(rows) - vis))
        return rows

    def ensure(self, log=None):
        if not self.valid():
            self.scan(log=log)
        return self.rows

    # --- lesen -------------------------------------------------------------
    def is_on(self, r):
        return bool((self.m.u32(r['ent'] + E_FLAGS) or 0) & VIS_BIT)

    def state(self, r):
        m = self.m
        return {
            'flags': m.u32(r['ent'] + E_FLAGS),
            'isvis': m.u8(r['body'] + B_ISVISIBLE) if r['body'] else None,
            'isgeom': m.u8(r['body'] + B_ISGEOM) if r['body'] else None,
            'draw': m.i32(r['gr'] + G_DRAW) if r['gr'] else None,
            'link': m.u32(r['gr'] + G_LINK) if r['gr'] else None,
            'scene': m.u64(r['gr'] + G_SCENE) if r['gr'] else None}

    def names(self):
        """Kurzname -> Anzahl der Fundstellen (beide Flurkopien)."""
        out = {}
        for r in self.rows:
            out[r['short']] = out.get(r['short'], 0) + 1
        return out

    def match(self, pat):
        pat = pat.lower()
        return [r for r in self.rows if pat in r['short'].lower()]

    # --- schreiben ---------------------------------------------------------
    def set(self, r, on, full=None):
        """Sichtbarkeit setzen.

        VOLL ist die Vorgabe (`self.full = True`): `flags` am Entity,
        `body+0x80`, `body+0x81` und der Zeichenwert am Grafikmodell. Dass
        Verstecken damit wirkt, ist im Spiel belegt -- daran wird nichts
        geaendert.

        SCHMAL (`--slim`): nur `flags` und der Zeichenwert. Zum Vergleichen,
        falls sich der Verdacht bestaetigt, dass `body+0x81` (isGeomActive)
        das Aushaengen aus der Zeichenliste anstoesst.

        Beim Einblenden wird noetigenfalls wieder eingehaengt (`relink`) --
        das war die Ursache der gemeldeten Unsymmetrie.
        """
        full = self.full if full is None else full
        p = self.m.p
        cur = self.m.u32(r['ent'] + E_FLAGS) or 0
        p.write(r['ent'] + E_FLAGS,
                struct.pack('<I', (cur | VIS_BIT) if on else (cur & ~VIS_BIT)))
        if full and r['body']:
            p.write(r['body'] + B_ISVISIBLE, b'\x01')
            p.write(r['body'] + B_ISGEOM, b'\x01' if on else b'\x00')
        if r['gr']:
            if on and self.relink_on_show and not self.in_list(r):
                self.relink(r, log=lambda *x: None)
            p.write(r['gr'] + G_DRAW, struct.pack('<i', 0 if on else -1))

    def is_drawn(self, r):
        """Wird das Modell gezeichnet? Der Zeichenwert entscheidet: -1 heisst
        nein, alles ab 0 ist eine Detailstufe."""
        if not r['gr']:
            return None
        v = self.m.i32(r['gr'] + G_DRAW)
        return None if v is None else v >= 0

    def in_list(self, r):
        if not r['gr']:
            return None
        v = self.m.u32(r['gr'] + G_LINK)
        return None if v is None else bool(v & 1)

    def needs(self, r, want):
        """Muss geschrieben werden? Nicht nur `flags` pruefen -- genau das war
        die Luecke: haengt die Engine das Modell aus, bleibt `flags` stehen und
        das Nachziehen merkte nichts."""
        if ((self.m.u32(r['ent'] + E_FLAGS) or 0) & VIS_BIT) != (1 if want else 0):
            return True
        d = self.is_drawn(r)
        return d is not None and d != want

    # Der Bereich, in dem die Gastobjekte dieses Spiels liegen. Gemessen an
    # allen beobachteten Adressen (Entities 0x343.../0x348..., Spielerobjekt
    # 0x354...). Ein Zeiger ausserhalb ist Muell, und darauf wird nicht
    # geschrieben.
    GUEST_LO, GUEST_HI = 0x100000000, 0x1000000000

    def _plausible(self, a):
        return bool(a) and self.GUEST_LO < a < self.GUEST_HI

    # relink ist ABGESCHALTET. Grund, gemessen am 14.09.2026 im Flur:
    #
    #     122 Grafikmodelle tragen Listenbit 0 und prev/next, die Kette hat
    #     306 Knoten (Kopf 0x34f41c360, Ende 0x347e3bf80). Das Objekt bei
    #     `grmodel+0x28` enthaelt keinen dieser Werte -- +0x40, +0x48 und
    #     +0x50 lesen alle 0.
    #
    # `grmodel+0x28` ist also NICHT der Listenbesitzer, und S_HEAD/S_TAIL/
    # S_COUNT waren geraten. Die Folge war schlimmer als ein nicht gezeichnetes
    # Objekt: der Code sah immer `head == 0`, nahm den Zweig "Liste ist leer"
    # und schrieb den Modellzeiger in zwei unbekannte Felder eines lebenden
    # Engine-Objekts. Drei Abstuerze auf VA 0xcec2b7 (Abbau der Zeichenliste)
    # passen dazu, ebenso die Reproduktion: Tueren ausblenden, dann Loop
    # wechseln.
    #
    # Wieder einschalten erst, wenn der echte Besitzer gefunden ist -- gesucht
    # wird ein Objekt, dessen Felder Kopf, Ende und die Laenge der Kette
    # enthalten. `chain_len()` unten misst die Kette und bleibt dafuer da.
    RELINK_ENABLED = False

    def relink(self, r, log=print):
        """Schreibt NICHTS. Siehe RELINK_ENABLED oben.

        Das Modell erscheint beim naechsten Stagewechsel -- die Engine liest
        die flags dann frisch aus der Datei und haengt selbst ein.
        """
        if not self.RELINK_ENABLED:
            log('  %s: wird beim naechsten Tuerdurchgang gezeichnet'
                ' (Wiedereinhaengen ist abgeschaltet)' % r['short'])
            return False
        raise NotImplementedError(
            'relink ist abgeschaltet, bis der Listenbesitzer gefunden ist')

    def player_pos(self):
        """Wo steht der Spieler? Ueber dieselbe Zeigerkette wie hover.

        Gibt None zurueck, wenn kein Level geladen ist -- dann gibt es auch
        keine Kopie, der man etwas zuordnen koennte.
        """
        try:
            obj, err = hover.chain(self.p, self.base, log=lambda *x: None)
        except OSError:
            return None
        if err or not obj:
            return None
        d = self.p.read(obj + 0x30, 12)
        if not d or len(d) != 12:
            return None
        return struct.unpack('<3f', d)

    def nearest_copy(self, rows, to=None):
        """Welche dieser Fundstellen ist die des Spielers?

        Entscheidung ueber den Abstand der Weltlage. Gibt die Zeile zurueck
        oder None, wenn keine Lage bekannt ist.
        """
        here = self.player_pos() if to is None else to
        if not here:
            return None
        best, bd = None, None
        for r in rows:
            p = r.get('pos')
            if not p:
                continue
            d = sum((a - b) ** 2 for a, b in zip(p, here))
            if bd is None or d < bd:
                best, bd = r, d
        return best

    def chain_len(self, head):
        """Wie viele Knoten haengen ab `head` in der Kette?

        Vorwaerts ueber `next` (grmodel+0x18), begrenzt auf WALK_MAX. Gibt None
        zurueck, wenn ein Zeiger unplausibel ist oder die Grenze reisst.

        Der Kopf muss MITGEGEBEN werden: wo die Engine ihn haelt, ist unbekannt
        (siehe die widerlegten S_*-Offsets). Ermitteln laesst er sich, indem man
        von einem verketteten Knoten ueber `prev` zurueckgeht.
        """
        node = head
        n = 0
        while node:
            if not self._plausible(node):
                return None
            n += 1
            if n > WALK_MAX:
                return None
            nxt = self.m.u64(node + G_NEXT)
            if nxt is None:
                return None
            node = nxt
        return n

    def snapshot(self, r):
        """Alle Felder, die beim Sichtbarschalten mitspielen."""
        st = self.state(r)
        return {'flags': st['flags'], 'isVisible': st['isvis'],
                'isGeomActive': st['isgeom'], 'draw': st['draw'],
                'inList': (st['link'] or 0) & 1, 'link': st['link'],
                'scene': st['scene'],
                'next': self.m.u64(r['gr'] + G_NEXT) if r['gr'] else None,
                'prev': self.m.u64(r['gr'] + G_PREV) if r['gr'] else None}

    def targets(self, wanted):
        """Welche Fundstellen wirklich geschrieben werden.

        Mit `own_copy_only` (Vorgabe) je Objektname nur die dem Spieler
        naechste. Ohne Spielerlage -- kein Level geladen -- alle, denn sonst
        wirkte nichts, und das waere die schlechtere Ueberraschung.
        """
        rows = [r for r in self.rows if r['short'] in wanted]
        if not self.own_copy_only:
            return rows
        here = self.player_pos()
        if not here:
            return rows
        by = {}
        for r in rows:
            by.setdefault(r['short'], []).append(r)
        out = []
        for group in by.values():
            if len(group) == 1:
                out.extend(group)
                continue
            pick = self.nearest_copy(group, here)
            out.append(pick if pick is not None else group[0])
        return out

    def apply(self, wanted):
        """`wanted`: {kurzname: True/False}.

        Geschrieben wird nur die eigene Flurkopie, solange `own_copy_only`
        steht -- siehe `targets()`.
        """
        n = 0
        for r in self.targets(wanted):
            self.set(r, wanted[r['short']])
            n += 1
        return n


def hold(sess, wanted, log=print, once=False):
    """Auswahl halten. Bei jedem Stagewechsel liest die Engine die flags
    frisch aus der Datei -- ohne Nachziehen ist die Aenderung nach dem
    naechsten Tuerdurchgang weg."""
    n = 0
    try:
        while True:
            if not sess.valid():
                log('  Objektliste neu suchen ...')
                sess.scan(log=log)
            sess.apply(wanted)
            n += 1
            if once:
                return n
            if n % 120 == 0:
                log('  ... %d Runden gehalten' % n)
            time.sleep(HOLD_MS / 1000.0)
    except KeyboardInterrupt:
        log('\n  beendet nach %d Runden' % n)
    return n


def main():
    a = sys.argv[1:]
    if not ptmem.find_pid():
        sys.exit('  shadPS4 laeuft nicht')
    s = Session()
    # Alte Fassung auf Wunsch: beide Flurkopien schreiben.
    if '--bothcopies' in a:
        s.own_copy_only = False
    if not s.ok():
        sys.exit('  Modulbasis nicht gefunden -- ist P.T. geladen?')
    print('  BASE 0x%x' % s.base)
    s.scan(log=print)

    def pick(flag):
        return a[a.index(flag) + 1] if flag in a else None

    # --- Schreibbefehle ---------------------------------------------------
    wanted = {}
    if '--show-all-hidden' in a:
        for r in s.rows:
            if not s.is_on(r):
                wanted[r['short']] = True
    if '--slim' in a:
        s.full = False
        print('  schmaler Schreibsatz (nur flags und Zeichenwert)')
    if '--norelink' in a:
        s.relink_on_show = False
        print('  Einhaengen abgeschaltet')

    if '--relink' in a:
        pat = a[a.index('--relink') + 1].lower()
        tg = [x for x in s.rows if pat in x['short'].lower()]
        if not tg:
            sys.exit('  kein Objekt passt auf %r' % pat)
        for r in tg:
            s.relink(r)
        return

    if '--toggletest' in a:
        pat = a[a.index('--toggletest') + 1].lower()
        tg = [x for x in s.rows if pat in x['short'].lower()]
        if not tg:
            sys.exit('  kein Objekt passt auf %r' % pat)
        hold = 6.0
        keys = ('flags', 'isVisible', 'isGeomActive', 'draw', 'inList')
        print('\n  Messung an %d Fundstelle(n) von %r -- P.T. haelt zwei'
              % (len(tg), tg[0]['short']))
        print('  Flurkopien, deshalb werden ALLE gesetzt. Schreibsatz: %s'
              % ('voll' if s.full else 'schmal'))

        def show_state(label):
            for r in tg:
                st = s.snapshot(r)
                print('     %-10s 0x%-12x %s'
                      % (label, r['ent'],
                         '  '.join('%s=%s' % (k, st[k]) for k in keys)))
            return {r['ent']: s.snapshot(r) for r in tg}

        before = show_state('vorher')

        print('\n  >>> blende AUS und warte %.0f s -- JETZT hinsehen' % hold)
        for r in tg:
            s.set(r, False)
        time.sleep(hold)
        after_off = show_state('nach aus')

        print('\n  >>> blende EIN und warte %.0f s -- JETZT hinsehen' % hold)
        for r in tg:
            s.set(r, True)
        time.sleep(hold)
        after_on = show_state('nach ein')

        print('\n  Auswertung:')
        for r in tg:
            e = r['ent']
            b, o, n = before[e], after_off[e], after_on[e]
            eng = [k for k in b if o[k] != n[k] and k not in
                   ('flags', 'isVisible', 'isGeomActive', 'draw')]
            print('     0x%x' % e)
            print('        Liste vorher=%s  nach aus=%s  nach ein=%s'
                  % (b['inList'], o['inList'], n['inList']))
            print('        draw  vorher=%s  nach aus=%s  nach ein=%s'
                  % (b['draw'], o['draw'], n['draw']))
            if o['inList'] and n['inList']:
                print('        -> nie ausgehaengt. Dann entscheidet allein der')
                print('           Zeichenwert, und beide Richtungen muessen')
                print('           wirken. Tun sie es nicht, liegt es woanders.')
            elif not o['inList'] and n['inList']:
                print('        -> ausgehaengt und wieder eingehaengt. Der')
                print('           relink greift; wenn das Bild folgt, ist die')
                print('           Unsymmetrie behoben.')
            elif not o['inList'] and not n['inList']:
                print('        -> ausgehaengt und NICHT zurueckgekommen. Der')
                print('           relink hat nicht gegriffen -- Szene oder')
                print('           Listenkopf pruefen.')
            if eng:
                print('        Von der Engine selbst geaendert: %s'
                      % ', '.join(eng))
        print('\n  Sag, was du gesehen hast: verschwand es beim ersten Halt,')
        print('  und kam es beim zweiten zurueck?')
        return

    if '--diag' in a:
        pat = a[a.index('--diag') + 1].lower()
        print()
        for r in [x for x in s.rows if pat in x['short'].lower()]:
            st = s.state(r)
            print('  %s   Ebene %s' % (r['short'], r['layer']))
            print('     ent      0x%-12x flags=%s' % (r['ent'], st['flags']))
            print('     body     0x%-12x isVisible=%s isGeomActive=%s'
                  % (r['body'] or 0, st['isvis'], st['isgeom']))
            print('     grmodel  0x%-12x draw=%-4s Liste=%s (0x%x)'
                  % (r['gr'] or 0, st['draw'],
                     'ja' if (st['link'] or 0) & 1 else 'NEIN', st['link'] or 0))
            print('     Szene    0x%-12x  Nachfolger 0x%-12x Vorgaenger 0x%x'
                  % (st['scene'] or 0,
                     s.m.u64(r['gr'] + G_NEXT) if r['gr'] else 0,
                     s.m.u64(r['gr'] + G_PREV) if r['gr'] else 0))
        return

    for flag, on in (('--show', True), ('--hide', False)):
        pat = pick(flag)
        if pat:
            for part in pat.split(','):
                tg = s.match(part.strip())
                if not tg:
                    sys.exit('  kein Objekt passt auf %r' % part.strip())
                for r in tg:
                    wanted[r['short']] = on
    pat = pick('--hold')
    if pat:
        for part in pat.split(','):
            tg = s.match(part.strip())
            if not tg:
                sys.exit('  kein Objekt passt auf %r' % part.strip())
            for r in tg:
                wanted[r['short']] = True

    if wanted and '--hold' not in a:
        n = s.apply(wanted)
        print('\n  %d Fundstellen gesetzt (%d Objektnamen)'
              % (n, len(wanted)))
        for nm in sorted(wanted):
            print('     %-4s %s' % ('ON' if wanted[nm] else 'off', nm))
        print('\n  Hinweis: beim naechsten Stagewechsel liest die Engine die')
        print('  flags wieder aus der Datei. Dauerhaft nur mit --hold.')
        return
    if wanted:
        print('\n  halte %d Objektnamen, Strg+C beendet' % len(wanted))
        hold(s, wanted)
        return

    # --- nur auflisten ----------------------------------------------------
    sel = s.rows
    if '--grep' in a:
        sel = s.match(pick('--grep'))
    if '--hidden' in a:
        sel = [r for r in sel if not s.is_on(r)]
    print()
    # Die eigene Kopie markieren. P.T. haelt zwei Fluere, und geschrieben wird
    # in beide -- sehen sollte man trotzdem, welche die eigene ist.
    mine = set()
    here = s.player_pos()
    if here:
        by = {}
        for r in sel:
            by.setdefault(r['short'], []).append(r)
        for rows in by.values():
            pick_r = s.nearest_copy(rows, here)
            if pick_r is not None:
                mine.add(id(pick_r))
        print('     >  = die Kopie, in der du stehst (%.1f, %.1f, %.1f)'
              % here)
        print()
    for r in sel:
        st = s.state(r)
        print('   %s %-3s %-42s %-8s 0x%-12x flags=%s isVis=%-4s geom=%-4s '
              'draw=%-4s Liste=%-3s (%7.2f,%6.2f,%7.2f)'
              % ('>' if id(r) in mine else ' ',
                 'ON ' if s.is_on(r) else 'off', r['short'][:42], r['layer'],
                 r['ent'], st['flags'], st['isvis'], st['isgeom'], st['draw'],
                 'ja' if (r['link'] or 0) & 1 else 'nein',
                 *r['pos']))


if __name__ == '__main__':
    main()
