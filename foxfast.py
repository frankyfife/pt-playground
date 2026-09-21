"""Vectorised Fox-Engine LCG codec (same math as pt_tools/foxlua.py, numpy-fast)."""
import struct
import numpy as np

MAGIC = 0xA0F8EFE6
M = 0x2E90EDD
MASK = 0xFFFFFFFF
LANES = 8192


def keystream_words(seed, nwords):
    state = ((((seed << 16) & MASK) ^ 0x65760000) | seed) & MASK
    inc = (seed * 0x116) & MASK
    if nwords == 0:
        return np.zeros(0, dtype=np.uint32)
    k = min(LANES, nwords)
    # first k states, sequentially
    first = np.empty(k, dtype=np.uint64)
    s = state
    for i in range(k):
        first[i] = s
        s = (s * M + inc) & MASK
    # jump constants for a k-step advance:  s' = A*s + B
    A, B = 1, 0
    for _ in range(k):
        A = (A * M) & MASK
        B = (B * M + inc) & MASK
    out = np.empty(((nwords + k - 1) // k) * k, dtype=np.uint32)
    cur = first
    A64, B64 = np.uint64(A), np.uint64(B)
    MASK64 = np.uint64(MASK)
    for p in range(0, len(out), k):
        out[p:p + k] = cur.astype(np.uint32)
        cur = (cur * A64 + B64) & MASK64
    return out[:nwords]


def _crypt(body, seed):
    nw = len(body) // 4
    ks = keystream_words(seed, nw).view(np.uint8)
    src = np.frombuffer(body[:nw * 4], dtype=np.uint8)
    return (src ^ ks).tobytes() + body[nw * 4:]


def decrypt(blob):
    magic, seed = struct.unpack_from('<II', blob, 0)
    if magic != MAGIC:
        return blob
    return _crypt(blob[8:], seed)


def encrypt(data, seed=0x12345678):
    return struct.pack('<II', MAGIC, seed) + _crypt(data, seed)


if __name__ == '__main__':
    import sys, os
    mode, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    blob = open(src, 'rb').read()
    out = decrypt(blob) if mode == 'd' else encrypt(blob)
    open(dst, 'wb').write(out)
    print('%s %s -> %s (%d -> %d)' % (mode, src, dst, len(blob), len(out)))
