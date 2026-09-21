"""Lift the ELF out of P.T.'s eboot.bin so Ghidra or IDA can open it.

eboot.bin is a decrypted fself: a SELF header (magic 4F 15 3D 1D) with a segment
table, wrapping an ordinary x86-64 ELF that starts at 0x120. We have been
reading it all along -- luaapi.py parses exactly this to map VAs to file
offsets -- but never as a standalone file.

The catch is that the ELF's own program headers carry *logical* offsets, while
the real positions of the payloads live in the SELF segment table. Each SELF
segment names its program header in bits 20..31 of its flags word. So the fix is
mechanical: copy every segment's bytes out, lay them down contiguously, and
rewrite p_offset to where they actually landed.

Two further tweaks so stock tools accept the result:
  * e_type 0xfe00 (ET_SCE_DYNEXEC) -> 2 (ET_EXEC)
  * program headers that have no SELF segment get p_offset/p_filesz zeroed
    rather than pointing at nothing

The point of doing this at all: the parts of the binary that carry names --
Lua bindings, Fox property registrations -- gave us anchors and were tractable
with a linear sweep. ShPlayerController has no such anchor, and finding the
player's own update path needs function boundaries, cross-references and a
decompiler. That is what this file is for.

    python elfout.py            # writes eboot.elf next to eboot.bin
    python elfout.py --verify   # re-read the result and compare a known site
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths

GAME = ptpaths.GAME
EBOOT = os.path.join(GAME, "eboot.bin")
OUT = os.path.join(GAME, "eboot.elf")

SELF_MAGIC = bytes([0x4f, 0x15, 0x3d, 0x1d])
PT_LOAD = 1


def parse(d):
    if d[:4] != SELF_MAGIC:
        sys.exit('not a SELF -- magic is %s' % d[:4].hex(' '))
    nseg, = struct.unpack_from('<H', d, 0x18)
    segs = []
    for i in range(nseg):
        flags, off, fsz, msz = struct.unpack_from('<QQQQ', d, 0x20 + i * 32)
        segs.append({'flags': flags, 'off': off, 'fsz': fsz, 'msz': msz,
                     'phdr': (flags >> 20) & 0xFFF})
    elf = 0x20 + nseg * 32
    if d[elf:elf + 4] != b'\x7fELF':
        sys.exit('no ELF header at 0x%x' % elf)
    e_phoff, = struct.unpack_from('<Q', d, elf + 0x20)
    e_phentsize, e_phnum = struct.unpack_from('<HH', d, elf + 0x36)
    phs = []
    for i in range(e_phnum):
        o = elf + e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from('<II', d, o)
        p_off, p_va, p_pa = struct.unpack_from('<QQQ', d, o + 0x08)
        p_fsz, p_msz, p_align = struct.unpack_from('<QQQ', d, o + 0x20)
        phs.append(dict(type=p_type, flags=p_flags, off=p_off, va=p_va, pa=p_pa,
                        fsz=p_fsz, msz=p_msz, align=p_align, raw_off=o))
    return elf, e_phoff, e_phentsize, e_phnum, phs, segs


def build(log=print):
    d = open(EBOOT, 'rb').read()
    elf, e_phoff, e_phentsize, e_phnum, phs, segs = parse(d)
    log('  SELF: %d segments, ELF at 0x%x, %d program headers'
        % (len(segs), elf, e_phnum))

    # which SELF segment carries which program header
    src = {}
    for s in segs:
        i = s['phdr']
        if i < e_phnum:
            src.setdefault(i, s)

    hdr_size = 0x40 + e_phnum * e_phentsize
    cursor = (hdr_size + 0xFFF) & ~0xFFF
    out = bytearray()
    placed = []
    for i, ph in enumerate(phs):
        s = src.get(i)
        if s is None or s['fsz'] == 0:
            placed.append((i, None, 0, 0))
            continue
        data = d[s['off']:s['off'] + s['fsz']]
        pad = (-len(out)) % 0x1000 if out else 0
        out += b'\0' * pad
        off = cursor + len(out)
        out += data
        placed.append((i, off, len(data), s['off']))
        log('    ph[%d] type=0x%-8x vaddr=0x%-10x %8d bytes  from file 0x%x -> 0x%x'
            % (i, ph['type'], ph['va'], len(data), s['off'], off))

    head = bytearray(d[elf:elf + 0x40])
    struct.pack_into('<H', head, 0x10, 2)        # ET_SCE_DYNEXEC -> ET_EXEC
    struct.pack_into('<Q', head, 0x20, 0x40)     # phoff right after the header
    struct.pack_into('<Q', head, 0x28, 0)        # no section headers
    struct.pack_into('<HH', head, 0x3a, 0, 0)    # shentsize, shnum
    struct.pack_into('<H', head, 0x3e, 0)        # shstrndx

    phtab = bytearray()
    for i, ph in enumerate(phs):
        raw = bytearray(d[ph['raw_off']:ph['raw_off'] + e_phentsize])
        _, off, size, _ = placed[i]
        struct.pack_into('<Q', raw, 0x08, off or 0)
        struct.pack_into('<Q', raw, 0x20, size)
        phtab += raw

    blob = bytearray(head + phtab)
    blob += b'\0' * (cursor - len(blob))
    blob += out
    with open(OUT, 'wb') as f:
        f.write(blob)
    log('  wrote %s (%.1f MB)' % (OUT, len(blob) / 1048576))
    return blob


def _selfmap(d):
    """VA -> file offset for the fself, parsed here rather than borrowed.

    luaapi now prefers eboot.elf as its analysis source, so importing it here
    would compare the lifted ELF against itself and pass unconditionally. That
    is how a stale ELF -- lifted while nogravity.py's two patches were applied,
    then never rebuilt after the restore -- went unnoticed and put a patched
    `mov al,1` into the Ghidra index. This function must stay self-contained.
    """
    nseg, = struct.unpack_from('<H', d, 0x18)
    segs = [struct.unpack_from('<QQQQ', d, 0x20 + i * 32) for i in range(nseg)]
    elf = 0x20 + nseg * 32
    e_phoff, = struct.unpack_from('<Q', d, elf + 0x20)
    e_phentsize, e_phnum = struct.unpack_from('<HH', d, elf + 0x36)
    phs = []
    for i in range(e_phnum):
        o = elf + e_phoff + i * e_phentsize
        phs.append((struct.unpack_from('<I', d, o)[0],
                    struct.unpack_from('<Q', d, o + 0x10)[0],
                    struct.unpack_from('<Q', d, o + 0x20)[0]))
    mp = []
    for f, off, fsz, _ in segs:
        i = (f >> 20) & 0xFFF
        if i < len(phs) and phs[i][0] == PT_LOAD:
            mp.append((off, phs[i][1], min(fsz, phs[i][2])))
    return mp


def _read(mp, blob, va, n):
    for fo, base, sz in mp:
        if base <= va < base + sz:
            return blob[fo + (va - base):fo + (va - base) + n]
    return None


def verify(log=print):
    """Every mapped byte must match the fself -- not just a few sample sites.

    A spot check would have missed nothing here, but a full diff also answers
    the more useful question: *which* bytes differ, i.e. exactly which patches
    the lifted ELF was carrying when Ghidra indexed it.
    """
    src = open(EBOOT, 'rb').read()
    smap = _selfmap(src)
    blob = open(OUT, 'rb').read()
    e_phoff, = struct.unpack_from('<Q', blob, 0x20)
    e_phentsize, e_phnum = struct.unpack_from('<HH', blob, 0x36)
    loads = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, = struct.unpack_from('<I', blob, o)
        p_off, p_va = struct.unpack_from('<QQ', blob, o + 0x08)
        p_fsz, = struct.unpack_from('<Q', blob, o + 0x20)
        if p_type == PT_LOAD and p_fsz:
            loads.append((p_va, p_off, p_fsz))

    diffs = []
    for p_va, p_off, p_fsz in loads:
        theirs = _read(smap, src, p_va, p_fsz)
        mine = blob[p_off:p_off + p_fsz]
        if theirs is None or len(theirs) != len(mine):
            log('  segment 0x%x: no counterpart in the fself' % p_va)
            diffs.append((p_va, -1, -1))
            continue
        if theirs == mine:
            continue
        for i in range(p_fsz):
            if theirs[i] != mine[i]:
                diffs.append((p_va + i, theirs[i], mine[i]))

    if not diffs:
        log('  verification: every mapped byte matches eboot.bin')
        return True
    log('  verification: %d byte(s) DIFFER from eboot.bin' % len(diffs))
    for va, a, b in diffs[:20]:
        log('     va 0x%-9x  eboot %02x  elf %02x' % (va, a, b))
    log('  the ELF is stale -- rebuild it (python elfout.py) and re-run PTIndex.java')
    return False


if __name__ == '__main__':
    if '--verify' in sys.argv[1:]:
        verify()
    else:
        build()
        print()
        verify()
