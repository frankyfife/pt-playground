"""Fox Engine PathCode64 -- aus benanntem Code nachgebaut, nicht geraten.

Herkunft
--------
Disassembliert aus dem MGSV-TPP-Prototyp (04.08.2015), der eine Linker-Map mit
242 338 benannten Symbolen mitbringt -- siehe pedis.py und
[[mgsv-tpp-prototype-symbols]]:

    ?GetPathCodeFromString@Path@fs@fox@@   0x14002fab0  -> Sprungstummel
    ?FromString@PathCodeImpl@fs@fox@@      0x14002dc90
    ?GetImplicitCode@PathCodeResolver@...  0x14002dcc0
    ff_path_code                           0x141878ae0
    ff_path_ext_code                       0x141878b80
    ff_path_code_set_userflag              0x141878b50
    raw_path_hash_code                     0x141878cd0   <- der Kern
    ?CityHash64@cityhash@impl@@            0x141877fb0

Der Kern (`raw_path_hash_code`) ist CityHash64 mit einem CityHash-Finalizer
obendrauf, verwoben mit den **letzten acht Bytes des Strings, big endian**
gelesen (kuerzere Strings rechtsbuendig).

Aufbau des 64-Bit-Codes:

    Bit 63..51   Endungscode = raw_path_hash_code(endung ohne Punkt) & 0x1FFF
    Bit 50       "user flag"  (ff_path_code_set_userflag)
    Bit 49..0    Pfadhash     = raw_path_hash_code(pfad)

Der Pfad geht **ohne `as/`-Praefix und ohne Endung** hinein, mit `/` als
Trenner.

Belege
------
* Alle 11 Endungscodes aus MGSVs `logs/assets_.dump` exakt reproduziert
  (bnk 1752, ffnt 1740, fmtt 164, fsm 3131, fsop 1439, json 3609, lua 796,
  sbp 5980, subp 3832, wem 422, wmv 7263).
* Alle 1332 Pfad-Hash-Paare aus derselben Datei getroffen, sobald Bit 50
  beruecksichtigt wird -- die 647 anfaenglichen "Fehlschlaege" unterschieden
  sich um **genau** 0x4000000000000, und `ff_path_code_set_userflag` setzt
  genau dieses Bit.

    python foxpath.py <pfad> [...]        Code fuer Pfade rechnen
    python foxpath.py --selftest          gegen assets_.dump pruefen
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths
from strcode import cityhash64

M64 = (1 << 64) - 1
M50 = (1 << 50) - 1
KMUL = 0x9DDFEA08EB382D69
K2 = 0x651E95C4D06FBFB1
USERFLAG = 1 << 50
EXT_SHIFT = 51
EXT_MASK = 0x1FFF

# Der assets_.dump des MGSV-Prototyps, aus playground.json
# (Schluessel "mgsv_asset_dump"). Ohne Eintrag leer.
DUMP = ptpaths.MGSV_DUMP


def raw_path_hash_code(s):
    """0x141878cd0. CityHash64 plus Finalizer, verwoben mit dem String-Ende."""
    b = s.encode() if isinstance(s, str) else s
    n = len(b)
    if n == 0:
        return 0
    # Die letzten <=8 Bytes, big endian: das letzte Zeichen landet im
    # niedrigsten Byte. Kuerzere Strings sitzen rechtsbuendig.
    tail = 0
    cl = 0
    i = n - 1
    while i >= 0 and cl < 64:
        tail = (tail + (b[i] << cl)) & M64
        i -= 1
        cl += 8
    h = cityhash64(b)
    c = ((((K2 + h) & M64) ^ tail) * KMUL) & M64
    a = ((c ^ (c >> 47)) ^ tail) & M64
    a = (a * KMUL) & M64
    return ((a ^ (a >> 47)) * KMUL) & M64


def ext_code(ext):
    """ff_path_ext_code -- fuehrender Punkt wird uebersprungen."""
    e = ext[1:] if ext.startswith('.') else ext
    return raw_path_hash_code(e) & EXT_MASK


def path_code(path, userflag=False):
    """Vollstaendiger 64-Bit-Code fuer einen Archivpfad.

    `path` wie im Archiv, z. B. 'as/sh/chara/lte/Pictures/foo.1.ftexs' oder
    '/as/...'. Praefix `as/` und Endung werden abgeschnitten, Backslashes zu
    Schraegstrichen.
    """
    p = path.replace('\\', '/').lstrip('/')
    if p.startswith('as/'):
        p = p[3:]
    # Die Endung ist alles ab dem ERSTEN Punkt des Dateinamens, nicht ab dem
    # letzten. Belegt an P.T.s texture.qar: die Mip-Streams heissen
    # "foo.1.ftexs" ... "foo.6.ftexs" und haben SECHS verschiedene
    # Endungscodes -- mit rpartition waeren alle "ftexs" und damit gleich.
    head, _, name = p.rpartition('/')
    stem, dot, ext = name.partition('.')
    base = (head + '/' + stem) if head else stem
    if not dot:
        ext = ''
    code = raw_path_hash_code(base) & M50
    if userflag:
        code |= USERFLAG
    return (ext_code(ext) << EXT_SHIFT) | code


def split(code):
    """Code -> (pfadhash ohne Flag, userflag, endungscode)."""
    return code & M50, bool(code & USERFLAG), code >> EXT_SHIFT


def selftest():
    import io
    import pickle

    class Safe(pickle.Unpickler):
        # Fremdes Pickle: nichts importieren lassen.
        def find_class(self, m, n):
            raise pickle.UnpicklingError('blockiert: %s.%s' % (m, n))

    soll = {'bnk': 1752, 'ffnt': 1740, 'fmtt': 164, 'fsm': 3131, 'fsop': 1439,
            'json': 3609, 'lua': 796, 'sbp': 5980, 'subp': 3832, 'wem': 422,
            'wmv': 7263}
    bad = [e for e, v in soll.items() if ext_code(e) != v]
    print('  Endungscodes : %d von %d   %s'
          % (len(soll) - len(bad), len(soll), 'OK' if not bad else bad))

    if not os.path.exists(DUMP):
        print('  Pfadhashes   : uebersprungen, %s fehlt' % DUMP)
        return not bad
    raw = open(DUMP, 'rb').read().replace(b'\r\n', b'\n')
    d = Safe(io.BytesIO(raw), encoding='latin1').load()
    hit = flag = 0
    for _, v in d.items():
        arc, want = v[1], v[2]
        for uf in (False, True):
            if path_code(arc, uf) == want:
                hit += 1
                flag += uf
                break
    print('  Pfadhashes   : %d von %d   (davon %d mit gesetztem user flag)'
          % (hit, len(d), flag))
    return not bad and hit == len(d)


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == '--selftest':
        sys.exit(0 if selftest() else 1)
    else:
        for p in a:
            lo, uf, ec = split(path_code(p))
            print('  %016x   pfad %013x  flag %d  endung %d   %s'
                  % (path_code(p), lo, uf, ec, p))
