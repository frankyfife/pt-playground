"""FoxData v5 (.fox2) writer -- create entities, grow properties, rebuild a file.

fox2edit.py can only overwrite a value that already exists. This is the other
half: new entities, new map entries, new strings, with every derived field
recomputed. Nothing here is guessed -- `python fox2build.py selftest` loads all
32 .fox2 in chunk1.psarc, re-serialises each one from the parsed model and
compares it byte for byte with the original.

Appending is safe because entity offsets are implicit: entities sit back to
back and every reference between them is a 48-bit runtime address, never a file
offset. Adding an entity at the end therefore moves nothing, and growing an
entity in the middle only shifts the ones behind it in the file -- which no
reference cares about.

Layout, all of it verified against the shipped data:

  file    0x00 '\\xf2box5' + 3 pad
          0x08 u32 entity count
          0x0c u32 string-table offset
          0x10 u32 entity-table offset (always 0x20)
          0x14..0x1f zero
          then entities, then the string table, then zero padding, then the
          literal footer 'end\\0' + 10 zero bytes.
          total = align16(string-table end + 24); the footer sits at total-14.
          Every file in the game obeys this, including the padding minimum --
          the shipped gap between table and footer runs 10..25 bytes, i.e. the
          16-residue is free but at least 10 bytes are always spent.

  entity  0x40 header, then its properties back to back.
          +0x02, +0x14, +0x18 are class metadata this writer never invents; it
          copies them from a template entity of the same class.
          +0x2c is 0x40 + the static properties, +0x30 is 0x40 + all of them.
          The two differ on exactly the 205 entities that own dynamic ones, so
          writing only +0x2c would truncate the entity walk.

  prop    0x20 header, then values.
          size   = align16(0x20 + count * stride)
          stride = align16(8 + element size) inside a string-map, where each
                   slot is an 8-byte key followed by the value; plain element
                   size otherwise.
          EntityLink is 32 bytes, not the 24 the old type table claimed. Both
          fit a lone link (align16 hides the difference); a two-entry map does
          not, which is why fox2.py used to read the second connector as junk.

String tables ship sorted by text, so build() sorts too. The engine works on
hashes alone -- order has never mattered to it -- but matching the shipped
shape costs nothing.

    import fox2build
    doc = fox2build.Doc.load(blob)
    loc = doc.copy_entity(src_doc, src_ent, addr=doc.free_addr())
    doc.dataset().map_append('dataList', doc.intern('name'), pack_addr(loc.addr))
    blob = doc.build()
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptpaths
import fox2, strcode

MAGIC = b'\xf2box5'
FOOTER = b'end\0' + b'\0' * 10          # 14 bytes, at total-14
FOOTER_GAP = 24                         # min bytes from table end to file end

# element sizes; EntityLink corrected to 32
ESZ = {k: v[1] for k, v in fox2.TYPES.items()}
ESZ[22] = 32

STRINGY = (11, 12, 20)                  # String, Path, FilePtr -- values are hashes


def align16(n):
    return (n + 15) & ~15


def pack_addr(a):
    return struct.pack('<Q', a)


def hashes_used(ent):
    """Every StrCode64 an entity refers to: its class, its property names, its
    string-ish values, its map keys and the three hashes inside each link."""
    out = {ent.chash}
    for p in ent.props:
        out.add(p.hash)
        if p.container == 2:
            out.update(p.keys())
        for i in range(p.count):
            if p.type in STRINGY:
                out.add(struct.unpack('<Q', p.value(i))[0])
            elif p.type == 22:
                out.update(struct.unpack_from('<3Q', p.value(i)))
    return out


class Prop:
    """One property. `data` is the raw value block, exactly size-0x20 bytes, so
    trailing padding survives a load/build round trip untouched."""

    def __init__(self, hash, type, container, count, data, hpad=b'\0' * 16):
        self.hash, self.type, self.container, self.count = hash, type, container, count
        self.data = bytearray(data)
        self.hpad = bytes(hpad)

    @classmethod
    def parse(cls, blob, off):
        h, = struct.unpack_from('<Q', blob, off)
        t, cont, cnt, voff, size = struct.unpack_from('<BBHHH', blob, off + 8)
        if voff != 0x20:
            raise ValueError('property at 0x%x has value offset 0x%x, not 0x20' % (off, voff))
        return cls(h, t, cont, cnt, blob[off + 0x20:off + size],
                   blob[off + 0x10:off + 0x20])

    @property
    def esz(self):
        return ESZ.get(self.type, 8)

    @property
    def stride(self):
        return align16(8 + self.esz) if self.container == 2 else self.esz

    @property
    def size(self):
        return align16(0x20 + self.count * self.stride)

    def name(self, names):
        return names.get(self.hash, '#%012x' % self.hash)

    # --- values ------------------------------------------------------------
    def slot(self, i):
        """(key_offset, value_offset) of element i inside self.data."""
        base = i * self.stride
        return (base, base + 8) if self.container == 2 else (None, base)

    def value(self, i=0):
        _, v = self.slot(i)
        return bytes(self.data[v:v + self.esz])

    def key(self, i):
        k, _ = self.slot(i)
        if k is None:
            raise TypeError('not a map')
        return struct.unpack_from('<Q', self.data, k)[0]

    def set_value(self, i, raw):
        if len(raw) != self.esz:
            raise ValueError('value is %d bytes, %s takes %d' % (len(raw), self.type, self.esz))
        _, v = self.slot(i)
        self.data[v:v + self.esz] = raw

    def append(self, raw, key=None):
        """Grow the property by one element. Recomputes size on its own."""
        if self.container == 2 and key is None:
            raise ValueError('a string-map entry needs a key')
        if len(raw) != self.esz:
            raise ValueError('value is %d bytes, type %d takes %d' % (len(raw), self.type, self.esz))
        slot = bytearray(self.stride)
        if self.container == 2:
            struct.pack_into('<Q', slot, 0, key)
            slot[8:8 + len(raw)] = raw
        else:
            slot[0:len(raw)] = raw
        # drop the old tail padding, add the slot, let pack() re-pad
        self.data = bytearray(self.data[:self.count * self.stride]) + slot
        self.count += 1

    def set_items(self, items):
        """Replace the whole value block of a non-map property."""
        if self.container == 2:
            raise TypeError('use set_map_items on a string-map')
        data = bytearray()
        for raw in items:
            if len(raw) != self.esz:
                raise ValueError('value is %d bytes, type %d takes %d'
                                 % (len(raw), self.type, self.esz))
            data += raw
        self.data, self.count = data, len(items)

    def set_map_items(self, items):
        """Replace the whole value block of a string-map. items: [(key, raw)]."""
        if self.container != 2:
            raise TypeError('not a string-map')
        data = bytearray()
        for key, raw in items:
            slot = bytearray(self.stride)
            struct.pack_into('<Q', slot, 0, key)
            slot[8:8 + len(raw)] = raw
            data += slot
        self.data, self.count = data, len(items)

    def keys(self):
        return [self.key(i) for i in range(self.count)]

    def pack(self):
        body = bytes(self.data).ljust(self.size - 0x20, b'\0')[:self.size - 0x20]
        return (struct.pack('<QBBHHH', self.hash, self.type, self.container,
                            self.count, 0x20, self.size) + self.hpad + body)


class Ent:
    """One entity. `head` keeps the original 0x40 bytes so class metadata this
    writer does not understand (+0x02, +0x14, +0x18) is carried over verbatim."""

    def __init__(self, head, props, nstatic):
        self.head = bytearray(head)
        self.props = props
        self.nstatic = nstatic

    @classmethod
    def parse(cls, blob, off):
        hsz, = struct.unpack_from('<H', blob, off)
        if hsz != 0x40:
            raise ValueError('entity at 0x%x has a 0x%x header' % (off, hsz))
        nstat, ndyn, poff, s1, s2 = struct.unpack_from('<HHIII', blob, off + 0x24)
        if poff != 0x40:
            raise ValueError('entity at 0x%x starts properties at 0x%x' % (off, poff))
        props, p = [], off + poff
        for _ in range(nstat + ndyn):
            pr = Prop.parse(blob, p)
            props.append(pr)
            p += pr.size
        e = cls(blob[off:off + 0x40], props, nstat)
        if e.size_static() != s1 or e.size_total() != max(s1, s2):
            raise ValueError('entity at 0x%x: sizes %d/%d, computed %d/%d'
                             % (off, s1, s2, e.size_static(), e.size_total()))
        return e

    @property
    def addr(self):
        return struct.unpack_from('<Q', self.head, 0x0a)[0]

    @addr.setter
    def addr(self, a):
        struct.pack_into('<Q', self.head, 0x0a, a)

    @property
    def id(self):
        return struct.unpack_from('<H', self.head, 0x12)[0]

    @id.setter
    def id(self, v):
        struct.pack_into('<H', self.head, 0x12, v)

    @property
    def chash(self):
        return struct.unpack_from('<Q', self.head, 0x1c)[0]

    @property
    def ndyn(self):
        return len(self.props) - self.nstatic

    def size_static(self):
        return 0x40 + sum(p.size for p in self.props[:self.nstatic])

    def size_total(self):
        return 0x40 + sum(p.size for p in self.props)

    def get(self, hash_or_name, names=None):
        h = hash_or_name if isinstance(hash_or_name, int) else strcode.strcode64(hash_or_name)
        for p in self.props:
            if p.hash == h:
                return p
        return None

    def require(self, name):
        p = self.get(name)
        if p is None:
            raise KeyError('entity @%x has no property %r' % (self.addr, name))
        return p

    def pack(self):
        h = bytearray(self.head)
        struct.pack_into('<HH', h, 0x24, self.nstatic, self.ndyn)
        struct.pack_into('<I', h, 0x28, 0x40)
        struct.pack_into('<II', h, 0x2c, self.size_static(), self.size_total())
        return bytes(h) + b''.join(p.pack() for p in self.props)


class Doc:
    """A whole .fox2, loadable and rebuildable."""

    def __init__(self, fhead, ents, strings):
        self.fhead = bytearray(fhead)
        self.ents = ents
        self.strings = dict(strings)        # hash -> text

    # --- load / save -------------------------------------------------------
    @classmethod
    def load(cls, blob):
        if blob[:5] != MAGIC:
            raise ValueError('not a fox2')
        count, stroff, entoff = struct.unpack_from('<III', blob, 8)
        if entoff != 0x20:
            raise ValueError('entity table at 0x%x, not 0x20' % entoff)
        ents, o = [], entoff
        for _ in range(count):
            e = Ent.parse(blob, o)
            ents.append(e)
            o += e.size_total()
        if o != stroff:
            raise ValueError('entities end at 0x%x, string table at 0x%x' % (o, stroff))
        strings, p, limit = {}, stroff, len(blob) - len(FOOTER)
        while p + 12 <= limit:
            h, n = struct.unpack_from('<QI', blob, p)
            if h == 0 and n == 0:           # into the padding
                break
            if p + 12 + n > limit:
                break
            strings[h] = blob[p + 12:p + 12 + n].decode('utf8', 'replace')
            p += 12 + n
        return cls(blob[:0x20], ents, strings)

    @classmethod
    def loadfile(cls, path):
        return cls.load(open(path, 'rb').read())

    def build(self):
        body = b''.join(e.pack() for e in self.ents)
        stroff = 0x20 + len(body)
        tab = bytearray()
        for text in sorted(self.strings.values()):
            b = text.encode('utf8')
            tab += struct.pack('<QI', strcode.strcode64(text), len(b)) + b
        total = align16(stroff + len(tab) + FOOTER_GAP)
        head = bytearray(self.fhead)
        struct.pack_into('<III', head, 8, len(self.ents), stroff, 0x20)
        out = bytearray(total)
        out[:0x20] = head
        out[0x20:stroff] = body
        out[stroff:stroff + len(tab)] = tab
        out[total - len(FOOTER):] = FOOTER
        return bytes(out)

    # --- strings -----------------------------------------------------------
    def intern(self, text):
        h = strcode.strcode64(text)
        prev = self.strings.get(h)
        if prev is not None and prev != text:
            raise ValueError('hash collision: %012x is already %r' % (h, prev))
        self.strings[h] = text
        return h

    def names(self):
        return dict(self.strings)

    # --- lookup ------------------------------------------------------------
    def by_addr(self, a):
        for e in self.ents:
            if e.addr == a:
                return e
        return None

    def named(self, text):
        """Entities whose `name` property carries this text."""
        h = strcode.strcode64(text)
        out = []
        for e in self.ents:
            p = e.get('name')
            if p and p.count and struct.unpack_from('<Q', p.data, 0)[0] == h:
                out.append(e)
        return out

    def of_class(self, cls):
        h = strcode.strcode64(cls)
        return [e for e in self.ents if e.chash == h]

    def dataset(self):
        d = self.of_class('DataSet')
        if len(d) != 1:
            raise KeyError('expected exactly one DataSet, found %d' % len(d))
        return d[0]

    # --- allocation --------------------------------------------------------
    def free_addr(self, base=0x7F000000, step=0x70):
        """An address no entity in this file uses. The shipped game never goes
        above 0x7b85640, so anything from 0x7F000000 up is clear of it."""
        used = {e.addr for e in self.ents}
        a = base
        while a in used:
            a += step
        return a

    def free_id(self):
        return max([e.id for e in self.ents] + [0]) + 1

    # --- creation ----------------------------------------------------------
    def copy_entity(self, src_doc, src_ent, addr=None, id=None):
        """Clone an entity out of another document, texts and all.

        The class metadata in the entity header comes along untouched, which is
        the whole point: a hand-built ShRelativeStageLocator would have to guess
        those fields, a copied one cannot get them wrong.
        """
        props = [Prop(p.hash, p.type, p.container, p.count, bytes(p.data), p.hpad)
                 for p in src_ent.props]
        e = Ent(bytes(src_ent.head), props, src_ent.nstatic)
        e.addr = self.free_addr() if addr is None else addr
        e.id = self.free_id() if id is None else id
        self.ents.append(e)
        # carry over the texts this clone actually refers to, and only those --
        # importing the whole source table would bloat the file with strings
        # from a level that has nothing to do with this one
        for h in hashes_used(e):
            if h not in self.strings and h in src_doc.strings:
                self.strings[h] = src_doc.strings[h]
        return e

    # --- property helpers --------------------------------------------------
    def set_str(self, ent, prop, text, index=0):
        ent.require(prop).set_value(index, struct.pack('<Q', self.intern(text)))

    def set_addr(self, ent, prop, addr, index=0):
        ent.require(prop).set_value(index, pack_addr(addr))

    def set_u32(self, ent, prop, v, index=0):
        ent.require(prop).set_value(index, struct.pack('<I', v))

    def set_vec(self, ent, prop, x, y, z, w=0.0, index=0):
        ent.require(prop).set_value(index, struct.pack('<4f', x, y, z, w))

    def map_append(self, ent, prop, key_text, raw):
        ent.require(prop).append(raw, key=self.intern(key_text))

    def link(self, package, archive, name):
        """A 32-byte EntityLink: package / archive / nameInArchive, then the
        runtime handle slot the engine fills in itself."""
        return struct.pack('<QQQQ', self.intern(package), self.intern(archive),
                           self.intern(name), 0)


# --------------------------------------------------------------------------
def _selftest():
    import psarc, foxfast, foxfpk
    game = ptpaths.GAME
    a = psarc.Psarc(os.path.join(game, "chunk1.orig.psarc"))
    ok = bad = 0
    for n in a.names:
        if not n.lower().endswith(('.fpk', '.fpkd')):
            continue
        fp = foxfpk.Fpk(foxfast.decrypt(a.read(a.index_of(n))))
        for ent in fp.ents:
            if not ent['path'].lower().endswith('.fox2'):
                continue
            blob = ent['data']
            try:
                out = Doc.load(blob).build()
            except Exception as ex:
                print('  FAIL %-44s %s' % (os.path.basename(ent['path']), ex))
                bad += 1
                continue
            if out == blob:
                ok += 1
            else:
                bad += 1
                d = next((i for i in range(min(len(out), len(blob)))
                          if out[i] != blob[i]), min(len(out), len(blob)))
                print('  DIFF %-44s len %d -> %d, first at 0x%x'
                      % (os.path.basename(ent['path']), len(blob), len(out), d))
    print('round trip: %d byte-identical, %d broken' % (ok, bad))
    return bad == 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'selftest':
        sys.exit(0 if _selftest() else 1)
    print(__doc__)
