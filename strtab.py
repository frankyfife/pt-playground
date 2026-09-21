"""Ground-truth StrCode64 table, harvested from the game's own .fox2 files.

.fox2 stores property names, class names and String/Path/FilePtr *values* as a
48-bit StrCode64; the plain text sits in a string table at the end of each file.
Fox's StrCode64 is a seeded CityHash64 variant -- plain CityHash64 truncated to
48 bits does NOT reproduce it (checked against all 8727 pairs below, 0 matches),
so do not guess at the algorithm. Every string P.T. actually uses is already
present in some string table, which is all an editor needs:

    import strtab
    t = strtab.load()
    t["/Assets/sh/level/promotion/pt_2014/ending/ending.fpk"]   # -> hash or KeyError

A KeyError means that exact string does not occur anywhere in the game, so its
hash cannot be recovered this way -- reuse an existing string instead, or crack
the seeding first.

    python strtab.py build      # rescan chunk1.psarc, refresh the cache
    python strtab.py find ending
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "strtab.json")
sys.path.insert(0, HERE)
import ptpaths
GAME = ptpaths.GAME


def build(archive=None):
    sys.path.insert(0, HERE)
    import psarc, foxfast, foxfpk, fox2
    a = psarc.Psarc(archive or os.path.join(GAME, "chunk1.orig.psarc"))
    out = {}
    for i, nm in enumerate(a.names):
        if not (nm.endswith(".fpk") or nm.endswith(".fpkd")):
            continue
        try:
            c = foxfpk.Fpk(foxfast.decrypt(a.read(i + 1)))
        except Exception:
            continue
        for e in c.ents:
            if not e["path"].endswith(".fox2"):
                continue
            try:
                fx = fox2.Fox2(foxfast.decrypt(e["data"]))
            except Exception:
                continue
            for h, s in fx.names.items():
                out.setdefault(s, h)
    json.dump(out, open(CACHE, "w"))
    return out


def load():
    if not os.path.exists(CACHE):
        return build()
    return json.load(open(CACHE))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "find"
    if cmd == "build":
        t = build()
        print("harvested %d distinct strings -> %s" % (len(t), CACHE))
    else:
        t = load()
        pat = sys.argv[2].lower()
        for s in sorted(t):
            if pat in s.lower():
                print("%012x  %s" % (t[s], s))
