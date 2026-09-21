"""Fox Engine (P.T. / CUSA01127) encrypted-Lua codec.

Header: 4-byte magic 0xA0F8EFE6 (LE), 4-byte u32 seed, then ciphertext.
Keystream: LCG over 32-bit words.
    state = ((seed << 16) ^ 0x65760000) | seed
    inc   = seed * 0x116
    out[i] = state ^ src[i];  state = state * 0x2E90EDD + inc
Files without the magic are passed through untouched by the engine loader,
so plaintext .lua works as a drop-in.
"""
import struct, sys, os

MAGIC = 0xA0F8EFE6
M = 0x2E90EDD
MASK = 0xFFFFFFFF


def keystream(seed, nwords):
    state = (((seed << 16) & MASK) ^ 0x65760000) | seed
    state &= MASK
    inc = (seed * 0x116) & MASK
    for _ in range(nwords):
        yield state
        state = (state * M + inc) & MASK


def _crypt(body, seed):
    # trailing bytes that do not fill a whole u32 are copied verbatim
    nw = len(body) // 4
    tail = len(body) - nw * 4
    ks = b''.join(struct.pack('<I', k) for k in keystream(seed, nw))
    return bytes(a ^ b for a, b in zip(body, ks)) + body[nw * 4:]


def decrypt(blob):
    magic, seed = struct.unpack_from('<II', blob, 0)
    if magic != MAGIC:
        return blob  # engine returns it unchanged
    return _crypt(blob[8:], seed)


def encrypt(data, seed=0x12345678):
    return struct.pack('<II', MAGIC, seed) + _crypt(data, seed)


if __name__ == '__main__':
    mode, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    blob = open(src, 'rb').read()
    out = decrypt(blob) if mode == 'd' else encrypt(blob)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, 'wb').write(out)
    print(f'{mode} {src} -> {dst}  ({len(blob)} -> {len(out)} bytes)')
    print(repr(out[:200]))
