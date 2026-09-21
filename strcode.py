"""Fox Engine StrCode64 / StrCode32 -- cracked and verified.

    StrCode64(t) = CityHash64WithSeeds(t + "\\0", k2, (t[0] << 16) + len(t)) & (2**48 - 1)
    StrCode32(t) = StrCode64(t) & 0xFFFFFFFF

Three details had to be right at once, which is why guessing failed:
  * the CityHash used is **1.0.3**, not 1.1. The two agree on the >64-byte main
    loop but differ for every input of 64 bytes or less: 1.1 rewrote the short
    paths to mix in a length-derived multiplier. Assuming 1.1 wholesale gets
    0/8727; assuming 1.0.2 wholesale gets the short strings right and every
    long one wrong;
  * the string is hashed with a trailing NUL, but the length in seed1 is the
    length WITHOUT it;
  * the result is truncated to 48 bits (not the 50/51 bits other Fox notes
    mention -- the largest hash across all of P.T. is 0xffff01b88714).

CityHash64WithSeeds(s, seed0, seed1) = HashLen16(CityHash64(s) - seed0, seed1).
seed0 is k2 = 0x9ae16a3b2f90404f, i.e. plain CityHash64WithSeed(s, seed1).

Verified against all 8727 (text, hash) pairs harvested from every .fox2 in
chunk1.psarc -- run `python strcode.py` to re-check. t[0] is taken as the first
byte; every string Fox uses is ASCII, so UTF-16 vs UTF-8 makes no difference.

    >>> import strcode
    >>> "%012x" % strcode.strcode64("/Assets/sh/level/promotion/pt_2014/ending/ending.fpk")
"""
import struct

K0 = 0xc3a5c85c97cb3127
K1 = 0xb492b66fbe98f273
K2 = 0x9ae16a3b2f90404f
K3 = 0xc949d7c7509e6557
M = 0xFFFFFFFFFFFFFFFF
MASK48 = (1 << 48) - 1


def _f64(s, i=0):
    return struct.unpack_from('<Q', s, i)[0]


def _f32(s, i=0):
    return struct.unpack_from('<I', s, i)[0]


def _rot(v, n):
    v &= M
    return v if n == 0 else ((v >> n) | (v << (64 - n))) & M


def _smix(v):
    v &= M
    return v ^ (v >> 47)


def _h128to64(lo, hi):
    mul = 0x9ddfea08eb382d69
    a = ((lo ^ hi) * mul) & M
    a ^= a >> 47
    b = ((hi ^ a) * mul) & M
    b ^= b >> 47
    return (b * mul) & M


def _hlen16(u, v):
    return _h128to64(u, v)


def _weak32(s, i, a, b):
    w, x, y, z = _f64(s, i), _f64(s, i + 8), _f64(s, i + 16), _f64(s, i + 24)
    a = (a + w) & M
    b = _rot((b + a + z) & M, 21)
    c = a
    a = (a + x + y) & M
    b = (b + _rot(a, 44)) & M
    return (a + z) & M, (b + c) & M


def cityhash64(s):
    """CityHash64, version 1.0.x."""
    if isinstance(s, str):
        s = s.encode('utf8')
    n = len(s)

    if n <= 16:
        if n > 8:
            a = _f64(s)
            b = _f64(s, n - 8)
            return (_hlen16(a, _rot((b + n) & M, n)) ^ b) & M
        if n >= 4:
            return _hlen16((n + (_f32(s) << 3)) & M, _f32(s, n - 4))
        if n > 0:
            a, b, c = s[0], s[n >> 1], s[n - 1]
            y = (a + (b << 8)) & M
            z = (n + (c << 2)) & M
            return (_smix(((y * K2) ^ (z * K3)) & M) * K2) & M
        return K2

    if n <= 32:
        a = (_f64(s) * K1) & M
        b = _f64(s, 8)
        c = (_f64(s, n - 8) * K2) & M
        d = (_f64(s, n - 16) * K0) & M
        return _hlen16((_rot((a - b) & M, 43) + _rot(c, 30) + d) & M,
                       (a + _rot((b ^ K3) & M, 20) - c + n) & M)

    if n <= 64:
        z = _f64(s, 24)
        a = (_f64(s) + (n + _f64(s, n - 16)) * K0) & M
        b = _rot((a + z) & M, 52)
        c = _rot(a, 37)
        a = (a + _f64(s, 8)) & M
        c = (c + _rot(a, 7)) & M
        a = (a + _f64(s, 16)) & M
        vf, vs = (a + z) & M, (b + _rot(a, 31) + c) & M
        a = (_f64(s, 16) + _f64(s, n - 32)) & M
        z = _f64(s, n - 8)
        b = _rot((a + z) & M, 52)
        c = _rot(a, 37)
        a = (a + _f64(s, n - 24)) & M
        c = (c + _rot(a, 7)) & M
        a = (a + _f64(s, n - 16)) & M
        wf, ws = (a + z) & M, (b + _rot(a, 31) + c) & M
        r = _smix(((vf + ws) * K2 + (wf + vs) * K0) & M)
        return (_smix((r * K0 + vs) & M) * K2) & M

    x = _f64(s, n - 40)
    y = (_f64(s, n - 16) + _f64(s, n - 56)) & M
    z = _hlen16((_f64(s, n - 48) + n) & M, _f64(s, n - 24))
    v = _weak32(s, n - 64, n, z)
    w = _weak32(s, n - 32, (y + K1) & M, x)
    x = (x * K1 + _f64(s)) & M
    i, rem = 0, (n - 1) & ~63
    while rem:
        x = (_rot((x + y + v[0] + _f64(s, i + 8)) & M, 37) * K1) & M
        y = (_rot((y + v[1] + _f64(s, i + 48)) & M, 42) * K1) & M
        x ^= w[1]
        y = (y + v[0] + _f64(s, i + 40)) & M
        z = (_rot((z + w[0]) & M, 33) * K1) & M
        v = _weak32(s, i, (v[1] * K1) & M, (x + w[0]) & M)
        w = _weak32(s, i + 32, (z + w[1]) & M, (y + _f64(s, i + 16)) & M)
        z, x = x, z
        i += 64
        rem -= 64
    return _hlen16((_hlen16(v[0], w[0]) + (_smix(y) * K1) + z) & M,
                   (_hlen16(v[1], w[1]) + x) & M)


def strcode64(text):
    b = text.encode('utf8') if isinstance(text, str) else text
    seed1 = ((b[0] << 16) + len(b)) & M if b else 0
    return _hlen16((cityhash64(b + b'\0') - K2) & M, seed1) & MASK48


def strcode32(text):
    return strcode64(text) & 0xFFFFFFFF


if __name__ == '__main__':
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import strtab
    pairs = strtab.load()
    bad = [(t, h, strcode64(t)) for t, h in pairs.items() if strcode64(t) != h]
    print('StrCode64 self-test: %d/%d ok' % (len(pairs) - len(bad), len(pairs)))
    for t, want, got in bad[:10]:
        print('  %-60r want %012x got %012x' % (t[:60], want, got))
    # StrCode32 cross-check against values the game itself reported
    known32 = {'playerCameraPosition': 0xCFEB8CA8, 'playerCameraRotation': 0x2043F109,
               'IsOnGround': 0x66105A8C, 'ResetCharacter': 0x318AED8D,
               'RequestResetLife': 0x2521AA3F, 'OnResetGameStopGame': 0xED811B0F,
               'OnResetGameUnloadStage': 0xD426FDBA, 'OnLoadHallway': 0x0CA498A3,
               'OnRestartGame': 0x52016EAF, 'GetPartsPath': 0x598E6D3D}
    n = sum(1 for k, v in known32.items() if strcode32(k) == v)
    print('StrCode32 cross-check vs Fox.StrCode32: %d/%d ok' % (n, len(known32)))
    for k, v in known32.items():
        if strcode32(k) != v:
            print('  %-24s want %08x got %08x' % (k, v, strcode32(k)))
