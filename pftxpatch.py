"""Eine Textur im .pftxs-Container aendern -- dort, wo das Spiel sie liest.

Warum hier und nicht im chunk1
------------------------------
`shsb_bath001_dc_bsm_alp` liegt in BEIDEN Ablagen, aber in verschiedenen
Fassungen:

    chunk1/sourceimages   2048x2048, BC3   wird NICHT gelesen
    resident.pftxs         256x256,  BC1   die geladene Fassung

Am 19.08.2026 gemessen: die chunk1-Fassung knallrot eingefaerbt -- im Spiel
blieb alles unveraendert. Der Patch muss also in den Container.

Aufbau (siehe pftxs.py): PFTX-Kopf, Tabelle, dann je Eintrag ein FTEX-Kopf
und ein PSUB-Verzeichnis mit absoluten Offsets auf die Mipstroeme. Weil hier
NUR an Ort und Stelle ersetzt wird -- gleiche Bytezahl, nur andere Inhalte --
bleiben alle Offsets gueltig und der Container muss nicht neu gebaut werden.
Passt ein neu komprimierter Block nicht in den alten Platz, wird er
ABGELEHNT statt ueberschrieben.

    python pftxpatch.py --check                  durchrechnen
    python pftxpatch.py --check --red            Diagnosefarbe statt Alpha
"""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ftex
import pftxs
import psarc
import ptpaths
import texpatch

# Container -> Texturname. Beides noetig: derselbe Name kommt in mehreren
# Containern vor (shsb_pssg001_dc_bsm_alp im Flur, shsb_mapp001_dc_bsm_alp
# im Ending), und getroffen werden soll genau die Badezimmerfassung.
# BELEGT durch das Modell selbst: shsb_bath001_mirr001.fmdl (aus dem
# Community-Paket) nennt seine Texturen im Klartext:
#
#     Shader             fox3DFW_ParallaxReflection
#     Base_Tex_SRGB      shsb_bath001_mi02_bsm.tga
#     Mask_Tex_LIN       shsb_bath001_mi02_bsm_alp.tga   <-- die Maske
#     Height_Tex_LIN     shsb_bath001_mi02_hgt.tga
#
# Der Spiegel laeuft ueber einen Parallax-Reflexionsshader, und `mi02_bsm_alp`
# ist dessen MASKE -- sie entscheidet, wo die Reflexion durchkommt. Base und
# Height sind reinweiss, nur die Maske ist grau gesprenkelt: genau das daempft
# das Spiegelbild.
#
# Eine Maske macht man deshalb nicht durchsichtig, sondern WEISS.
# `dc_bsm_alp` war eine Fehlspur -- aehnliches Aussehen, aber der Spiegel
# referenziert sie nicht.
MIRROR = ('pt14_hallway', 'shsb_bath001_mi02_bsm_alp')
WHITE = 0xFFFF        # RGB565


def patch(blob, name, colour=None, clear_alpha=False, log=print):
    """Gibt den geaenderten Container zurueck. Laenge bleibt gleich.

    Arbeitet auf `pftxs.chunks()`: dort steht je Chunk die Adresse des
    Kopfs, die Rohgroesse, die gepackte Groesse und ob roh oder zlib. Damit
    entfaellt jede eigene Offsetrechnung -- genau die hatte am 19.08. in
    fremde Texturen geschrieben.
    """
    p = pftxs.Pftxs(blob)
    hit = [e for e in p.ents if e['name'].endswith(name)]
    if not hit:
        log('  %s nicht im Container' % name)
        return blob
    e = hit[0]
    h = ftex.Header(p.header(e))
    log('  %s  %dx%d fmt=%d' % (name, h.w, h.h, h.fmt))

    out = bytearray(blob)
    done = skip = 0
    for tp, lv, raw, csz, roh, coff in p.chunks(e):
        src = bytes(out[tp + coff:tp + coff + csz])
        if roh:
            plain = src
        else:
            try:
                plain = zlib.decompress(src)
            except zlib.error:
                skip += 1
                continue
        if len(plain) != raw:
            skip += 1
            continue
        fixed = texpatch._paint(plain, h.fmt, colour, clear_alpha)
        new = fixed if roh else zlib.compress(fixed, 9)
        if len(new) > csz:
            skip += 1
            continue
        out[tp + coff:tp + coff + len(new)] = new
        if len(new) < csz:
            fill = csz - len(new)
            out[tp + coff + len(new):tp + coff + csz] = bytes(fill)
        done += 1
    log('  %d Chunks geaendert, %d uebersprungen' % (done, skip))
    if len(out) != len(blob):
        log('  LAENGE VERAENDERT -- verworfen')
        return blob
    return bytes(out)


def overrides(archive, colour=None, clear_alpha=False, log=print):
    """Override-Dict fuer psarc.build."""
    cont, name = MIRROR
    hit = [n for n in archive.names if n.endswith('/%s.pftxs' % cont)]
    if not hit:
        log('  %s.pftxs nicht im Archiv' % cont)
        return {}
    i = archive.index_of(hit[0])
    new = patch(archive.read(i), name, colour, clear_alpha, log)
    return {i: new}


def main():
    a = sys.argv[1:]
    ar = psarc.Psarc(ptpaths.ORIG)
    col = texpatch.RED if '--red' in a else WHITE
    ov = overrides(ar, colour=col, clear_alpha=False)
    print()
    print('  %d Container wuerde(n) ersetzt' % len(ov))


if __name__ == '__main__':
    main()
