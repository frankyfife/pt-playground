"""Read and write shadPS4's memory directly -- no Cheat Engine needed.

Cheat Engine is just ReadProcessMemory/WriteProcessMemory with a UI on top, and
those are two ctypes calls. Doing it from here means the search can use the
structure we recovered from the eboot instead of hunting for a value by hand.

What we are looking for is a ChBodyPlugin, the character body object. Its layout
came out of the property registration at va 0x6ad600:

    +0x90   modelName                    String
    +0xd8   ChBodyPlugin_Visibility      uint32
    +0xDC   hasGravity                   bool     <- the switch
    +0xDD   hasCollision                 bool
    +0xDE   hasTurnXYZ                   bool
    +0xDF   hasTrap                      bool
    +0xE0   noControlHeightWithNoMotion  bool
    +0xE1   allStopWhileInvisible        bool
    +0x1b8  useCharacterController       bool
    +0x270  lastFramePos                 Vector3
    +0x2a8  motionSpeedRate              float
    +0x2ac  hasSubCollision              bool

That gives a signature no value scan can match: six 0/1 bytes in a row at 0xDC,
a finite position at 0x270, and a sane motion rate at 0x2a8. The old attempt at
this failed because it froze an address found by value, and the engine keeps
ring-buffer copies -- with the object's shape known, a single hit anywhere
identifies the whole thing.

    python ptmem.py scan               # find candidate ChBodyPlugins
    python ptmem.py watch <addr>       # follow one candidate's position
    python ptmem.py show <addr>        # dump its flag block
    python ptmem.py float <addr>       # hasGravity off (the hover)
    python ptmem.py set <addr> <off> <0|1>

shadPS4 must be RUNNING with the game loaded for any of this.
"""
import ctypes
import ctypes.wintypes as w
import math
import struct
import sys
import time

k32 = ctypes.WinDLL('kernel32', use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
ACCESS = (PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
          | PROCESS_VM_WRITE | PROCESS_VM_OPERATION)

MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
PAGE_EXECUTE_READWRITE = 0x40
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01

# offsets recovered from the eboot
O_MODELNAME = 0x90
O_VISIBILITY = 0xd8
O_HASGRAVITY = 0xdc
O_FLAGS_END = 0xe2          # six bools, 0xdc..0xe1
O_CHARACTERCTRL = 0x1b8
O_LASTFRAMEPOS = 0x270
O_MOTIONSPEED = 0x2a8

FLAGS = [(0xdc, 'hasGravity'), (0xdd, 'hasCollision'), (0xde, 'hasTurnXYZ'),
         (0xdf, 'hasTrap'), (0xe0, 'noControlHeightWithNoMotion'),
         (0xe1, 'allStopWhileInvisible')]


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong),
                ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", w.DWORD),
                ("__alignment1", w.DWORD),
                ("RegionSize", ctypes.c_ulonglong),
                ("State", w.DWORD),
                ("Protect", w.DWORD),
                ("Type", w.DWORD),
                ("__alignment2", w.DWORD)]


def find_pid(name='shadPS4'):
    import subprocess
    out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if parts and parts[0].lower().startswith(name.lower()) \
                and 'launcher' not in parts[0].lower():
            return int(parts[1])
    return None


class Proc:
    def __init__(self, pid):
        self.h = k32.OpenProcess(ACCESS, False, pid)
        if not self.h:
            raise OSError('OpenProcess failed (%d) -- run this elevated?'
                          % ctypes.get_last_error())
        self.pid = pid

    def regions(self):
        mbi = MEMORY_BASIC_INFORMATION64()
        addr = 0
        while addr < 0x7FFFFFFFFFFF:
            n = k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr),
                                   ctypes.byref(mbi), ctypes.sizeof(mbi))
            if not n:
                addr += 0x1000
                if addr > 0x900000000:
                    break
                continue
            if (mbi.State == MEM_COMMIT
                    and mbi.Protect in (PAGE_READWRITE, PAGE_EXECUTE_READWRITE)
                    and not (mbi.Protect & PAGE_GUARD)):
                yield mbi.BaseAddress, mbi.RegionSize
            addr = mbi.BaseAddress + mbi.RegionSize

    def read(self, addr, size):
        buf = (ctypes.c_char * size)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size,
                                     ctypes.byref(got)):
            return None
        return bytes(buf[:got.value])

    def write(self, addr, data):
        got = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data,
                                    len(data), ctypes.byref(got))
        return bool(ok) and got.value == len(data)


def looks_like_plugin(b, o):
    """b is a chunk, o an offset in it that we treat as a plugin base.

    The first cut of this passed two million hits: zero-filled memory satisfies
    "every byte is 0 or 1" everywhere. So test for what a live character must
    actually look like rather than for what it merely may not be.
    """
    if o + O_MOTIONSPEED + 4 > len(b):
        return False
    # a character that is standing on something has gravity and collision on
    if b[o + O_HASGRAVITY] != 1 or b[o + O_HASGRAVITY + 1] != 1:
        return False
    for k in range(O_HASGRAVITY, O_FLAGS_END):
        if b[o + k] > 1:
            return False
    if b[o + O_CHARACTERCTRL] > 1:
        return False
    # modelName is a real reference, never empty on an instantiated body
    if struct.unpack_from('<Q', b, o + O_MODELNAME)[0] == 0:
        return False
    x, y, z, ww = struct.unpack_from('<4f', b, o + O_LASTFRAMEPOS)
    for v in (x, y, z):
        if v != v or abs(v) > 100000.0:
            return False
    if abs(x) < 0.001 and abs(z) < 0.001:     # unplaced
        return False
    if abs(y) > 50.0:                          # nobody is that high up in P.T.
        return False
    if ww != 0.0 and ww != 1.0:
        return False
    sp, = struct.unpack_from('<f', b, O_MOTIONSPEED + o)
    if sp != sp or not (0.05 <= sp <= 20.0):
        return False
    return True


def scan(p, log=print):
    hits = []
    scanned = 0
    for base, size in p.regions():
        if size > 0x4000000:                  # skip the huge reservations
            continue
        b = p.read(base, size)
        if not b:
            continue
        scanned += size
        for o in range(0, len(b) - O_MOTIONSPEED - 4, 8):
            if looks_like_plugin(b, o):
                x, y, z, _ = struct.unpack_from('<4f', b, o + O_LASTFRAMEPOS)
                hits.append((base + o, x, y, z))
    log('  scanned %.1f MB, %d candidates' % (scanned / 1048576.0, len(hits)))
    return hits


def show(p, addr, log=print):
    b = p.read(addr, O_MOTIONSPEED + 8)
    if not b:
        log('  cannot read 0x%x' % addr)
        return
    x, y, z, _ = struct.unpack_from('<4f', b, O_LASTFRAMEPOS)
    sp, = struct.unpack_from('<f', b, O_MOTIONSPEED)
    log('  0x%x  lastFramePos = (%.3f, %.3f, %.3f)  motionSpeedRate = %.3f'
        % (addr, x, y, z, sp))
    log('        ' + '  '.join('%s=%d' % (n, b[o]) for o, n in FLAGS))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    pid = find_pid()
    if not pid:
        sys.exit('shadPS4 is not running -- start the game first.')
    print('  shadPS4 pid %d' % pid)
    p = Proc(pid)

    if cmd == 'scan':
        hits = scan(p)
        hits.sort(key=lambda h: abs(h[2]))    # plausible heights first
        for a, x, y, z in hits[:40]:
            print('  0x%-14x pos = (%9.3f, %8.3f, %9.3f)' % (a, x, y, z))
        if len(hits) > 40:
            print('  ... %d more' % (len(hits) - 40))
    elif cmd == 'watch':
        a = int(sys.argv[2], 0)
        for _ in range(int(sys.argv[3]) if len(sys.argv) > 3 else 20):
            show(p, a)
            time.sleep(0.5)
    elif cmd == 'show':
        show(p, int(sys.argv[2], 0))
    elif cmd == 'float':
        a = int(sys.argv[2], 0)
        show(p, a)
        ok = p.write(a + O_HASGRAVITY, b'\x00')
        print('  hasGravity -> 0 : %s' % ('written' if ok else 'FAILED'))
        show(p, a)
    elif cmd == 'hover':
        off = float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
        lead = find_player(p)
        if lead:
            hover(p, lead, EYE + off)
    elif cmd == 'find':
        find_player(p)
    elif cmd == 'set':
        a, off, val = int(sys.argv[2], 0), int(sys.argv[3], 0), int(sys.argv[4])
        ok = p.write(a + off, bytes([val]))
        print('  [0x%x+0x%x] = %d : %s' % (a, off, val, 'written' if ok else 'FAILED'))
        show(p, a)
    else:
        print(__doc__)




# --- differential tracking -------------------------------------------------
# The structural signature came up empty, which means the registration offsets
# are not all members of one struct the way it looked. So do it without any
# layout assumption: remember every plausible position vector, let the player
# walk, and keep the ones that moved like a player. Whatever survives IS the
# character, and the bytes around it then tell us what the layout really is.

def vec_candidates(p):
    out = {}
    for base, size in p.regions():
        if size > 0x4000000:
            continue
        b = p.read(base, size)
        if not b:
            continue
        for o in range(0, len(b) - 16, 4):
            x, y, z, w = struct.unpack_from('<4f', b, o)
            if x != x or y != y or z != z:
                continue
            if abs(x) > 500 or abs(z) > 500 or abs(y) > 50:
                continue
            if abs(x) < 0.001 and abs(z) < 0.001:
                continue
            if w != 0.0 and w != 1.0:
                continue
            out[base + o] = (x, y, z)
    return out


def snapshot(p, addrs):
    out = {}
    for a in addrs:
        d = p.read(a, 16)
        if d and len(d) == 16:
            out[a] = struct.unpack('<3f', d[:12])
    return out


# --- the hover -------------------------------------------------------------
# Confirmed live: writing the player's Y at the leading address lifts the view
# cleanly and visibly. The engine rewrites it every frame, so the hold has to
# keep running -- at ~130 kHz against a 60 Hz engine that is not a contest.
#
# Finding it takes two observations, because a value scan alone cannot tell the
# source from its ~600 mirrors:
#   1. plausible position vectors that CHANGE while the player moves;
#   2. of those, the ones that change FIRST -- the mirrors trail by a frame.
#
# Both start room and street have their floor at y=0 and the eye sits at 1.65,
# so one absolute height works in either place.

EYE = 1.65


# The start room's footprint, from pt14_start.fox2: its models sit at local
# x -0.40..1.81, z -12.95..0, and the stage root is yaw 180 at the origin, so in
# world terms the room is x -1.8..0.4, z 0..13. Generous margins here because
# those are model origins, not mesh extents.
ROOM = (-4.0, 3.0, -1.0, 16.0)      # xmin, xmax, zmin, zmax


def find_player(p, seconds=3.0, log=print):
    """The player's position vector, found by where it is allowed to be.

    Earlier attempts scored "changes first", which only measured scan order, and
    then "one frame ahead of the majority", which drowned in the character's own
    ~250 bones. The room itself is the better test: a real position stays inside
    it for seconds on end, moves continuously and never teleports. Noise does
    none of that.

    The player has to be MOVING while this runs.
    """
    cands = []
    for base, size in p.regions():
        if size > 0x4000000:
            continue
        b = p.read(base, size)
        if not b:
            continue
        for o in range(0, len(b) - 12, 4):
            x, y, z = struct.unpack_from('<3f', b, o)
            if y != y or not (EYE - 0.12 < y < EYE + 0.12):
                continue
            if x != x or z != z:
                continue
            if not (ROOM[0] < x < ROOM[1] and ROOM[2] < z < ROOM[3]):
                continue
            cands.append(base + o)
    log('  %d addresses hold an eye-height point inside the room' % len(cands))
    if not cands:
        return []

    track = {a: [] for a in cands}
    t0 = time.time()
    while time.time() - t0 < seconds:
        for a in cands:
            d = p.read(a, 12)
            if d:
                track[a].append(struct.unpack('<3f', d))
        time.sleep(0.02)

    good = []
    for a, vs in track.items():
        if len(vs) < 8:
            continue
        ok, path, jump = True, 0.0, 0.0
        for i in range(1, len(vs)):
            x0, y0, z0 = vs[i - 1]
            x1, y1, z1 = vs[i]
            if y1 != y1 or not (EYE - 0.12 < y1 < EYE + 0.12):
                ok = False
                break
            if not (ROOM[0] < x1 < ROOM[1] and ROOM[2] < z1 < ROOM[3]):
                ok = False
                break
            d = math.hypot(x1 - x0, z1 - z0)
            path += d
            jump = max(jump, d)
        if ok and path > 0.3 and jump < 1.0:
            good.append((path, a, vs[-1]))
    good.sort(reverse=True)
    log('  %d stayed in the room, moved smoothly and never jumped' % len(good))
    for path, a, v in good[:6]:
        log('  0x%-12x walked %5.2f  now (%7.3f, %6.3f, %8.3f)'
            % (a, path, v[0], v[1], v[2]))
    return [a for _, a, _ in good[:8]]


def hover(p, addrs, target, log=print):
    log('  holding y = %.3f on %d addresses -- Ctrl+C to stop' % (target, len(addrs)))
    tgt = struct.pack('<f', target)
    n = 0
    t0 = time.time()
    try:
        while True:
            for a in addrs:
                p.write(a + 4, tgt)
            n += 1
            if n % 200000 == 0:
                d = p.read(addrs[0], 12)
                x, y, z = struct.unpack('<3f', d)
                log('    %6.0fs  pos = (%7.3f, %6.3f, %8.3f)  %.0f kHz'
                    % (time.time() - t0, x, y, z, n / (time.time() - t0) / 1000))
    except KeyboardInterrupt:
        log('  stopped')


if __name__ == '__main__':
    main()
