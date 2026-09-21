"""Fox Engine .fox2 (FoxData v5) reader.

File header (0x20):
  0x00 char[5] '\\xf2box5'  + 3 pad
  0x08 u32  entity count
  0x0c u32  string-table offset
  0x10 u32  entity-table offset (0x20)

Entity (header 0x40):
  +0x00 u16 header size (0x40)
  +0x06 char[4] 'ent\\0'
  +0x0a u64 runtime address (link target)
  +0x12 u16 id
  +0x1c u64 class-name hash (StrCode64)
  +0x24 u32 property count
  +0x28 u32 offset to first property
  +0x2c u32 entity size
  +0x30 u32 entity size incl. dynamic block

Property (header 0x20):
  +0x00 u64 name hash
  +0x08 u8  data type
  +0x09 u8  container type (0 static, 1 dynamic, 2 string-map, 3 list)
  +0x0a u16 element count
  +0x0c u16 offset to values (0x20)
  +0x0e u16 property size (16-byte aligned)

String table: repeated (u64 hash, u32 length, bytes).
"""
import struct

TYPES = {
    0: ('int8', 1), 1: ('uint8', 1), 2: ('int16', 2), 3: ('uint16', 2),
    4: ('int32', 4), 5: ('uint32', 4), 6: ('int64', 8), 7: ('uint64', 8),
    8: ('float', 4), 9: ('double', 8), 10: ('bool', 1), 11: ('String', 8),
    12: ('Path', 8), 13: ('EntityPtr', 8), 14: ('Vector3', 16),
    15: ('Vector4', 16), 16: ('Quat', 16), 17: ('Matrix3', 48),
    18: ('Matrix4', 64), 19: ('Color', 16), 20: ('FilePtr', 8),
    21: ('EntityHandle', 8), 22: ('EntityLink', 32), 23: ('PropertyInfo', 8),
    24: ('WideVector3', 16),
}
CONTAINERS = {0: 'array', 1: 'dyn', 2: 'map', 3: 'list'}


def stride_of(type, container):
    """Bytes per element. Inside a string-map each slot is an 8-byte key plus
    the value, the whole slot padded to 16 -- so a map of EntityLink advances
    48, not 40. Getting this wrong reads every entry after the first as junk,
    which is how the hallway's endDoor connector used to come out empty."""
    esz = TYPES.get(type, ('?', 8))[1]
    return ((8 + esz + 15) & ~15) if container == 2 else esz


class Prop:
    def __init__(self, blob, off, names):
        self.off = off
        self.hash, = struct.unpack_from('<Q', blob, off)
        self.type, self.container, self.count, self.voff, self.size = \
            struct.unpack_from('<BBHHH', blob, off + 8)
        self.tname, esz = TYPES.get(self.type, ('t%d' % self.type, 8))
        self.name = names.get(self.hash, '#%012x' % self.hash)
        self.values = []
        self.keys = []
        p = off + self.voff
        end = off + self.size
        stride = stride_of(self.type, self.container)
        for _ in range(self.count):
            if p + stride > end:
                break
            q = p
            if self.container == 2:
                k, = struct.unpack_from('<Q', blob, q)
                self.keys.append(names.get(k, '#%012x' % k))
                q += 8
            self.values.append(self._decode(blob, q, esz, names))
            p += stride

    def _decode(self, blob, q, esz, names):
        t = self.type
        if t in (11, 12, 20):
            h, = struct.unpack_from('<Q', blob, q)
            return names.get(h, '#%012x' % h)
        if t == 8:
            return struct.unpack_from('<f', blob, q)[0]
        if t == 9:
            return struct.unpack_from('<d', blob, q)[0]
        if t in (14, 15, 16, 19, 24):
            return tuple(round(x, 6) for x in struct.unpack_from('<4f', blob, q))
        if t == 10:
            return bool(blob[q])
        if t in (0, 2, 4, 6):
            return int.from_bytes(blob[q:q + esz], 'little', signed=True)
        if t == 22:      # EntityLink: package / archive / nameInArchive, then
            pkg, arc, nm = struct.unpack_from('<3Q', blob, q)   # the runtime slot
            return '%s|%s|%s' % (names.get(pkg, '#%012x' % pkg),
                                 names.get(arc, '#%012x' % arc),
                                 names.get(nm, '#%012x' % nm))
        if t in (13, 21):
            return '@%x' % struct.unpack_from('<Q', blob, q)[0]
        return int.from_bytes(blob[q:q + esz], 'little')

    def __repr__(self):
        v = self.values
        if self.container == 2:
            v = list(zip(self.keys, self.values))
        if len(v) == 1:
            v = v[0]
        elif len(v) > 12:
            v = '[%d items] %r ...' % (len(v), v[:6])
        return '%s (%s%s) = %r' % (self.name, self.tname,
                                   '' if self.container == 0 else '/' + CONTAINERS.get(self.container, '?'), v)


class Entity:
    def __init__(self, blob, off, names):
        self.off = off
        self.addr, = struct.unpack_from('<Q', blob, off + 0x0a)
        self.id, = struct.unpack_from('<H', blob, off + 0x12)
        self.chash, = struct.unpack_from('<Q', blob, off + 0x1c)
        # +0x24 u16 static property count, +0x26 u16 dynamic property count
        self.nprops, self.ndyn, self.poff, self.size, self.size2 = \
            struct.unpack_from('<HHIII', blob, off + 0x24)
        self.nprops += self.ndyn
        # +0x2c covers the static block only; the dynamic block extends to +0x30
        self.size = max(self.size, self.size2)
        self.cls = names.get(self.chash, '#%012x' % self.chash)
        self.props = []
        p = off + self.poff
        end = off + self.size
        for _ in range(self.nprops):
            if p + 0x20 > end:
                break
            pr = Prop(blob, p, names)
            if pr.size < 0x20 or p + pr.size > end:
                break
            self.props.append(pr)
            p += pr.size

    def get(self, name):
        for p in self.props:
            if p.name == name:
                return p
        return None

    @property
    def name(self):
        p = self.get('name')
        return p.values[0] if p and p.values else ''


class Fox2:
    def __init__(self, blob):
        assert blob[:5] == b'\xf2box5', 'not a fox2'
        self.blob = blob
        self.count, self.stroff, self.entoff = struct.unpack_from('<III', blob, 8)
        self.names = {0xb8a0bf169f98: ''}  # StrCode64("")
        p = self.stroff
        while p + 12 <= len(blob):
            h, n = struct.unpack_from('<QI', blob, p)
            if p + 12 + n > len(blob):
                break
            self.names[h] = blob[p + 12:p + 12 + n].decode('utf8', 'replace')
            p += 12 + n
        self.ents = []
        o = self.entoff
        for _ in range(self.count):
            e = Entity(blob, o, self.names)
            self.ents.append(e)
            o += e.size
        self.by_addr = {e.addr: e for e in self.ents}

    def find(self, cls=None, name=None):
        out = []
        for e in self.ents:
            if cls and cls.lower() not in e.cls.lower():
                continue
            if name and name.lower() not in str(e.name).lower():
                continue
            out.append(e)
        return out


def load(path):
    return Fox2(open(path, 'rb').read())


if __name__ == '__main__':
    import sys
    f = load(sys.argv[1])
    pat = sys.argv[2].lower() if len(sys.argv) > 2 else ''
    print('entities: %d  strings: %d' % (f.count, len(f.names)))
    for e in f.ents:
        blob = '%s %s' % (e.cls, e.name)
        if pat and pat not in blob.lower() and not any(pat in repr(p).lower() for p in e.props):
            continue
        print('\n[%d] %s  "%s"  @%x  props=%d' % (e.id, e.cls, e.name, e.addr, e.nprops))
        for p in e.props:
            print('    ', p)
