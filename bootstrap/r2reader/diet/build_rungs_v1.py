"""build_rungs_v1.py -- the 2026-10-20 diet ladder from the v1 readable reader
(../reader.py), never typed.

Each rung = (name, parent, edits); an edit is (old, new) -- `old` must occur
exactly once in the parent -- or ('REGION', start, end, new): the text from
the unique line `start` up to (not including) the unique line `end` is
replaced by `new`.  The rung files land in v1/ (r00 = reader.py itself), so
every rung is provably its parent plus the listed edits.
Usage: python build_rungs_v1.py [NAME ...]   (no names: all rungs)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.join(HERE, 'v1')
RUNGS = []


def rung(name, parent, *edits):
    RUNGS.append((name, parent, edits))


def apply(src, edits, name):
    for ed in edits:
        if ed[0] == 'REGION':
            _, a, b, new = ed
            assert src.count(a) == 1 and src.count(b) == 1, (name, a, b)
            i, j = src.index(a), src.index(b)
            assert i < j, (name, a, b)
            src = src[:i] + new + src[j:]
        else:
            old, new = ed
            assert src.count(old) == 1, (name, old[:60], src.count(old))
            src = src.replace(old, new)
    return src


# ---- r01: one global threshold -------------------------------------------
rung('r01_global_threshold', 'r00_reader',
     ('TABLES = [bytes(int(x < t) for x in range(256)) for t in range(257)]\n', ''),
     ('REGION', 'def binarise(img, w, h):', '# ---- 2. bullseyes', '''def binarise(img, w, h):
    # Ink = 1: one threshold, midway between the frame's 5th and 95th
    # percentile
    s = sorted(img[::97])
    t = (s[len(s) // 20] + s[len(s) - 1 - len(s) // 20]) // 2
    return img.translate(bytes(int(x < t) for x in range(256)))


'''))

# ---- r02: the 13-run comb only (no washed-out centre form) ---------------
rung('r02_comb13', 'r01_global_threshold',
     ('REGION', '    out = []\n    for i in range(1 + line[0], len(edge) - 12, 2):',
      'def ring_fit(value, x, y, p):', '''    out = []
    for i in range(1 + line[0], len(edge) - 14, 2):
        c0 = edge[i] + edge[i + 1]
        span = edge[i + 12] + edge[i + 13] - c0
        if span >= 24 and 96 * min(edge[i] - edge[i - 1],
                                   edge[i + 14] - edge[i + 13]) >= span:
            if max(abs(12 * (edge[i + k + 6] + edge[i + k + 7] - c0)
                       - (k + 6) * span) for k in KS) <= (
                    3 * span + 144) // 10:
                out.append((c0 + edge[i + 12] + edge[i + 13] - 2, span))
    return out


'''))

# ---- r03: no pitch refinement on the grey image --------------------------
rung('r03_no_pitch_refine', 'r01_global_threshold',
     ('''            for st in (p // 25, p // 50, p // 100):
                f, p = max((ring_fit(value, cx, cy, pp), pp)
                           for pp in (p - st, p, p + st))
''', ''))

# ---- r04: header without Chase -------------------------------------------
rung('r04_header_no_chase', 'r03_no_pitch_refine',
     ('''        lv = [t - v[x, y] + ((v[x - 1, y] + v[x + 1, y] + v[x, y - 1]
                              + v[x, y + 1] - 4 * v[x, y]) * s8 >> 3)
              for x, y in HEAD]
        weak = sorted(range(68), key=lambda i: abs(lv[i]))[:4]
        for f in range(16):
            b = [int(z > 0) for z in lv]
            for j in range(4):
                b[weak[j]] ^= f >> j & 1
            x = int(''.join('01'[z] for z in b), 2)
            if crc32((x >> 20).to_bytes(6, e)) % 2 ** 20 == x % 2 ** 20:
                return (x >> 20).to_bytes(6, e)
''', '''        x = int(''.join('01'[t - v[a, b] + ((v[a - 1, b] + v[a + 1, b]
                                + v[a, b - 1] + v[a, b + 1] - 4 * v[a, b])
                               * s8 >> 3) > 0] for a, b in HEAD), 2)
        if crc32((x >> 20).to_bytes(6, e)) % 2 ** 20 == x % 2 ** 20:
            return (x >> 20).to_bytes(6, e)
'''))

# ---- r05: no offset extrapolation in the walk ----------------------------
rung('r05_no_offset_extrapolation', 'r03_no_pitch_refine',
     ('    fixed, phase = {}, -1\n', '    phase = -1\n'),
     ('        fixed[bi, bj] = (ox, oy)\n', ''),
     ('''                bx, by = fixed.get((bi - di, bj - dj), (ox, oy))
                off[bi + di, bj + dj] = (2 * ox - bx, 2 * oy - by)
''', '''                off[bi + di, bj + dj] = (ox, oy)
'''))

# ---- r06: one walk (no refit to the accepted blocks, no re-walk) ---------
WALK_R06 = '''def walk(value, P, w, h, p, seeds):
    # Breadth first from the bullseye blocks (seeds, not read).  A
    # block's place is the pose plus the offset of the sound neighbour
    # that reached it, refined on the 68 timing modules (3 x 3 search at
    # 1/2, 1/4, 1/8, 1/16 module).  The clock is sound when the timing
    # score reaches 60 % of the modules' total deviation from their
    # mean, or the block's CRC checks; only sound blocks are walked
    # through, and blocks that leave the frame are not read.
    # -> the accepted 32-byte blocks
    off, todo, got, phase = {}, seeds[:], [], -1
    for b in seeds:
        off[b] = (0, 0)
    for bi, bj in todo:
        x0, y0 = at(P, 17 * bj, 17 * bi)
        x1, y1 = at(P, 17 * bj + 17, 17 * bi)
        x2, y2 = at(P, 17 * bj, 17 * bi + 17)
        ox, oy = off[bi, bj]

        def spot(dx, dy):
            return (x0 + ox + ((x1 - x0) * dx + (x2 - x0) * dy) // 17,
                    y0 + oy + ((y1 - y0) * dx + (y2 - y0) * dy) // 17)
        if [1 for x, y in [spot(-11, -11), spot(10, 10), spot(10, -11),
                           spot(-11, 10)]
                if min(x, y) < 0 or x > 16 * w - 32 or y > 16 * h - 32]:
            continue
        if phase < 0:
            phase = sum(value(*spot(dx, dy)) * (1 - 2 * par)
                        for dx, dy, par in FRAME) < 0
            phase = (bi + bj + phase) % 2
        flip = (bi + bj + phase) % 2
        fr = [(spot(dx, dy), 1 - 2 * (par ^ flip))
              for dx, dy, par in FRAME]
        mx = my = 0
        for st in (p // 2, p // 4, p // 8, p // 16):
            s, mx, my = max((sum(value(x + a, y + b) * wt
                                 for (x, y), wt in fr), a, b)
                            for a in (mx - st, mx, mx + st)
                            for b in (my - st, my, my + st))
        ox, oy = ox + mx, oy + my
        tv = [(value(*spot(dx, dy)), 1 - 2 * (par ^ flip))
              for dx, dy, par in FRAME]
        t = sum(v for v, i in tv) // 68
        sound = 5 * sum(v * i for v, i in tv) >= 3 * sum(
            abs(v - t) for v, i in tv)
        if (bi, bj) not in seeds:
            w32 = read_block(value, spot)
            if w32:
                got.append(w32)
                sound = 1
        if sound:
            for di, dj in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                if (bi + di, bj + dj) not in off:
                    off[bi + di, bj + dj] = (ox, oy)
                    todo.append((bi + di, bj + dj))
    return got


'''
rung('r06_one_walk', 'r05_no_offset_extrapolation',
     ('REGION', 'def walk(value, P, w, h, p, seeds, place):', 'def read_block(value, spot):',
      WALK_R06),
     ('REGION', '    seeds = [(r // 17, c // 17) for c, r in pts]\n',
      '# ======== main: one frame per line ========', '''    seeds = [(r // 17, c // 17) for c, r in pts]
    return walk(value, P, w, h, found[0][3] // 16, seeds), hd, '%d bullseyes' % len(found)
'''))

# ---- r07: the homography is taken whenever four bullseyes give one -------
rung('r07_no_homography_refusal', 'r05_no_offset_extrapolation',
     ('''        if D and [1 for c, r, x, y in pts if 20 * abs(
                s[6] * c + s[7] * r) > 3 * abs(D)] == []:
            if [1 for c, r, x, y in pts if abs(at(s + [D], c, r)[0] - x)
                    + abs(at(s + [D], c, r)[1] - y) > p // 16] == []:
                P = s + [D]
''', '''        if D:
            P = s + [D]
'''))

# ---- r08: no bullseye score, no progress notes ---------------------------
rung('r08_no_static_details', 'r07_no_homography_refusal',
     ('''            v = [(value(cx + (dx * p >> 4), cy + (dy * p >> 4)), i)
                 for dx, dy, i in RING]
            t = (sum(a for a, i in v if i) // N_INK
                 + sum(a for a, i in v if i == 0) // N_WHITE) // 2
            found.append((sum((a < t) == i for a, i in v), cx, cy, p))
''', '''            found.append((f, cx, cy, p))
'''),
     ("""    return got, hd, '%d bullseyes, %d walks' % (len(found), i + 1)
""", """    return got, hd
"""),
     ("""        return got, hd, 'grid'
""", """        return got, hd
"""),
     ("""        return [], None, 'no bullseye'
""", """        return [], None
"""),
     ("""    got, hd, note = read_frame(name)
""", """    got, hd = read_frame(name)
"""),
     ("""    note = note + ', header ' + ['unread', 'read'][hd != None]
""", ""),
     ("""    print(name + ':', note + ',', len(got), 'blocks accepted, chunks',
          held, '/', need, ['- more frames needed', '- done'][done])
""", """    print(name + ':', len(got), 'blocks accepted, chunks', held, '/',
          need, ['- more frames needed', '- done'][done])
"""))

# ---- r09: THE CLOCK-LINE POSE --------------------------------------------
# The least-squares pose over all bullseyes (lattice snap, Bareiss/Cramer
# similarity/affine/homography, local-pitch points, the +-9 degree tilt
# search) goes; every bullseye gets its own seed pose from its clock lines;
# the header in the four quarter turns of the seeds fixes the orientation;
# one walk spreads from every seed at once, learning the 17-module steps
# as it goes, and a block is reached once (by position).
POSE_R09 = '''# ---- 4. pose: a seed per bullseye, from its clock lines --------------
# A seed [x, y, A, B, f, k]: the centre of a block's centre module (1/16
# px); the pixel vectors (1/16 px) of 17 modules along the block's
# columns (A) and rows (B); the phase f of its timing frame; how the
# walk reached it (0 a bullseye, 1..4 = +A, -A, +B, -B from its parent).
def spot(s, dx, dy):
    # module (dx, dy) from the seed's centre module, 1/16 px
    return (s[0] + (s[2][0] * dx + s[3][0] * dy) // 17,
            s[1] + (s[2][1] * dx + s[3][1] * dy) // 17)


def clock(value, x, y, p):
    # The bullseye's clock lines: the timing row above its centre and
    # the timing column left of it, 9 modules out (8 when the page is
    # upside down).  Each line is looked for 8.5 modules out and
    # re-centred at 6 modules either side of the centre on the
    # alternation of the 7 modules along it (3 x 3 search, 1/2 .. 1/16
    # module); the chord between the two points gives the line's
    # direction and its pitch.  -> [A, B], A along +x, B along +y
    out = []
    for ex, ey in ((1, 0), (0, 1)):
        q = []
        for t in (-6, 6):
            cx = x + ((2 * t * ex - 17 * ey) * p >> 5)
            cy = y + ((2 * t * ey - 17 * ex) * p >> 5)
            mx = my = 0
            for st in (p // 32, p // 64, p // 128, p // 256):
                f, mx, my = max((abs(sum(
                    value(cx + a + (i * ex * p >> 4), cy + b + (i * ey * p >> 4))
                    * (1 - 2 * (i % 2)) for i in range(-3, 4))), a, b)
                    for a in (mx - st, mx, mx + st)
                    for b in (my - st, my, my + st))
            q.append((cx + mx, cy + my))
        out.append([(q[1][0] - q[0][0]) * 17 // 12,
                    (q[1][1] - q[0][1]) * 17 // 12])
    return out


def turn(s, n):
    # the seed of the page turned n quarter turns: (A, B) -> (B, -A)
    for i in range(n):
        s = s[:2] + [s[3], [-s[2][0], -s[2][1]]] + s[4:]
    return s


def sample(value, s):
    # the block's 18 x 18 modules (timing frame included) at their centres
    v = {}
    for dy in range(-9, 9):
        for dx in range(-9, 9):
            v[dx, dy] = value(*spot(s, dx, dy))
    return v


# ---- 3. header and orientation ---------------------------------------
def header(value, s):
    # The 68 header bits around a bullseye seen through seed s: the
    # threshold midway between its ink and white rings, the equaliser
    # at 4, 8 and 0 eighths of the Laplacian, Chase over the four least
    # reliable bits.  -> the six header bytes if the 20-bit check
    # (CRC-32 of the six bytes mod 2**20) passes
    v = sample(value, s)
    t = (sum(v[dx, dy] for dx, dy, i in RING if i) // N_INK + sum(
        v[dx, dy] for dx, dy, i in RING if i == 0) // N_WHITE) // 2
    for s8 in (4, 8, 0):
        lv = [t - v[a, b] + ((v[a - 1, b] + v[a + 1, b] + v[a, b - 1]
                              + v[a, b + 1] - 4 * v[a, b]) * s8 >> 3)
              for a, b in HEAD]
        weak = sorted(range(68), key=lambda i: abs(lv[i]))[:4]
        for f in range(16):
            b = [int(z > 0) for z in lv]
            for j in range(4):
                b[weak[j]] ^= f >> j & 1
            x = int(''.join('01'[z] for z in b), 2)
            if crc32((x >> 20).to_bytes(6, e)) % 2 ** 20 == x % 2 ** 20:
                return (x >> 20).to_bytes(6, e)


# ---- 5. walk ---------------------------------------------------------
def walk(value, w, h, p, todo):
    # Breadth first from every seed at once.  A block is placed at its
    # parent's centre plus the parent's 17-module step, refined on its
    # 68 timing modules (3 x 3 search at 1/2, 1/4, 1/8, 1/16 module),
    # and the step it was reached by is corrected by that refinement:
    # the walk learns the lattice as it goes.  The clock is sound when
    # the timing score reaches 60 % of the modules' total deviation from
    # their mean, or the block's CRC checks; only sound blocks are
    # walked through; blocks that leave the frame are not read; a block
    # within a cell of 5 modules of one already reached is not reached
    # again.  -> the accepted 32-byte blocks
    seen, got, c = {}, [], 5 * p >> 4
    for s in todo:
        u, v = s[0] // c, s[1] // c
        if [1 for i in (-1, 0, 1) for j in (-1, 0, 1)
                if (u + i, v + j) in seen]:
            continue
        seen[u, v] = 1
        if [1 for x, y in [spot(s, -11, -11), spot(s, 10, 10),
                           spot(s, 10, -11), spot(s, -11, 10)]
                if min(x, y) < 0 or x > 16 * w - 32 or y > 16 * h - 32]:
            continue
        fr = [(spot(s, dx, dy), 1 - 2 * (par ^ s[4]))
              for dx, dy, par in FRAME]
        if s[5]:
            mx = my = 0
            for st in (p // 32, p // 64, p // 128, p // 256):
                f, mx, my = max((sum(value(x + a, y + b) * wt
                                     for (x, y), wt in fr), a, b)
                                for a in (mx - st, mx, mx + st)
                                for b in (my - st, my, my + st))
            k = s[5] - 1
            g = 1 - 2 * (k % 2)
            s[0], s[1] = s[0] + mx, s[1] + my
            s[2 + k // 2] = [s[2 + k // 2][0] + g * mx,
                             s[2 + k // 2][1] + g * my]
        tv = [(value(*spot(s, dx, dy)), 1 - 2 * (par ^ s[4]))
              for dx, dy, par in FRAME]
        t = sum(v for v, i in tv) // 68
        sound = 5 * sum(v * i for v, i in tv) >= 3 * sum(
            abs(v - t) for v, i in tv)
        if s[5]:
            w32 = read_block(value, s)
            if w32:
                got.append(w32)
                sound = 1
        if sound:
            for k in range(4):
                g = 1 - 2 * (k % 2)
                todo.append([s[0] + g * s[2 + k // 2][0],
                             s[1] + g * s[2 + k // 2][1],
                             s[2], s[3], 1 - s[4], k + 1])
    return got


def read_block(value, s):
    # Threshold midway between the 9th darkest and the 9th brightest of
    # the 68 timing modules (34 ink, 34 white; a block on the paper
    # margin sharing one timing line with the page still has 9 inks, so
    # its data read white).  A block showing the rings is an unseen
    # bullseye.  Level and Laplacian per data module -> block(); None
    # if not tried
    v = sample(value, s)
    m = sorted(v[dx, dy] for dx, dy, i in FRAME)
    t = (m[8] + m[59]) // 2
    if 5 * sum((v[x, y] < t) == i for x, y, i in RING) > 4 * len(RING):
        return None
    return block([(t - v[x, y], v[x - 1, y] + v[x + 1, y] + v[x, y - 1]
                   + v[x, y + 1] - 4 * v[x, y]) for x, y in DATA])


'''
FRAME_R09 = '''def read_frame(name):
    # -> (32-byte blocks, header or None)
    w, h, img = load(name)
    if w == 0:
        return read_grid(img)
    value = sampler(img, w, h)
    found = bullseyes(img, binarise(img, w, h), w, h, value)
    seeds = [[x, y] + clock(value, x, y, p) for f, x, y, p in found]
    # the header in the four quarter turns of every seed, best first;
    # the turn whose check passes is the page's (none: upright)
    hd, n = None, 0
    for s in seeds:
        for m in (1, 2, 3, 0):
            if hd == None:
                hd, n = header(value, turn(s, m)), m
    seeds = [turn(s, n) for s in seeds]
    for s in seeds:
        s += [int(sum(value(*spot(s, dx, dy)) * (1 - 2 * par)
                      for dx, dy, par in FRAME) < 0), 0]
    return walk(value, w, h, found[0][3] if found else 0, seeds), hd
'''
rung('r09_clock', 'r08_no_static_details',
     ('REGION', '# ---- 4. pose ----', '# ---- 6. a block ----', POSE_R09),
     ('REGION', 'def read_frame(name):', '# ======== main: one frame per line ========', FRAME_R09),
     ("""    return hd, got
""", """    return got, hd
"""))

# ---- r10: the seed pose from the bullseye's own timing frame -------------
# (its four clock lines scored together, 68 modules, signed alternation in
# either phase, rotation searched to +-9 degrees in each quarter turn); the
# rest as r09.
FRAME_POSE = '''def pose(value, x, y, p):
    # The bullseye's seed pose from its own timing frame -- its four
    # clock lines together, 68 modules -- scored (either phase) at
    # rotations of s/4096 radian, about 0.9 degree steps to 9 degrees,
    # in each quarter turn (the lines are 9 modules out on two sides, 8
    # on the others).  -> [A, B], A along +x, B along +y
    best = []
    for s in range(-640, 641, 64):
        c = 4096 - s * s // 8192
        A = [17 * p * c >> 16, 17 * p * s >> 16]
        for n in range(4):
            q = turn([x, y, A, [-A[1], A[0]]], n)
            best.append((abs(sum(value(*spot(q, dx, dy)) * (1 - 2 * par)
                                 for dx, dy, par in FRAME)), s, A))
    f, s, A = max(best)
    return [A, [-A[1], A[0]]]


'''
rung('r10_frame_pose', 'r09_clock',
     ('REGION', 'def clock(value, x, y, p):', 'def turn(s, n):', FRAME_POSE),
     ('    seeds = [[x, y] + clock(value, x, y, p) for f, x, y, p in found]\n',
      '    seeds = [[x, y] + pose(value, x, y, p) for f, x, y, p in found]\n'))

# ---- r11: the joint pose ---------------------------------------------------
# The frame's rotation and quarter turn from the timing frames of ALL its
# bullseye blocks scored together (+-9 degrees, 0.9 degree steps, x 4
# turns); then each seed's own A and B from its four neighbour blocks'
# centres, refined on their timing frames (the clock lines one block out):
# rotation, pitch and shear per seed, no least squares.  The walk's block
# refinement and the neighbours' are one function.
FIT_R11 = """def fit(value, s, p):
    # Block s's centre refined on its 68 timing modules (phase s[4]):
    # 3 x 3 search at 1/2, 1/4, 1/8, 1/16 module -> the offset, 1/16 px
    fr = [(spot(s, dx, dy), 1 - 2 * (par ^ s[4]))
          for dx, dy, par in FRAME]
    mx = my = 0
    for st in (p // 32, p // 64, p // 128, p // 256):
        f, mx, my = max((sum(value(x + a, y + b) * wt
                             for (x, y), wt in fr), a, b)
                        for a in (mx - st, mx, mx + st)
                        for b in (my - st, my, my + st))
    return mx, my


"""
FRAME_R11 = """def read_frame(name):
    # -> (32-byte blocks, header or None)
    w, h, img = load(name)
    if w == 0:
        return read_grid(img)
    value = sampler(img, w, h)
    found = bullseyes(img, binarise(img, w, h), w, h, value)
    # the frame's rotation (r/4096 radian, about 0.9 degree steps to 9
    # degrees) and quarter turn: the timing frames of all its bullseye
    # blocks scored together, either phase each
    best = []
    for r in range(-640, 641, 64):
        c = 4096 - r * r // 8192
        for n in range(4):
            best.append((sum(abs(sum(value(*spot(q, dx, dy)) * (1 - 2 * par)
                                     for dx, dy, par in FRAME))
                             for q in [turn([x, y, [17 * p * c >> 16, 17 * p * r >> 16],
                                             [-17 * p * r >> 16, 17 * p * c >> 16]], n)
                                       for f, x, y, p in found]), r, n))
    f, r, n = max(best)
    c = 4096 - r * r // 8192
    seeds = []
    for f, x, y, p in found:
        s = turn([x, y, [17 * p * c >> 16, 17 * p * r >> 16],
                  [-17 * p * r >> 16, 17 * p * c >> 16]], n)
        s += [int(sum(value(*spot(s, dx, dy)) * (1 - 2 * par)
                      for dx, dy, par in FRAME) < 0), 0]
        # A and B from the four neighbours' refined centres
        m = []
        for k in range(4):
            g = 1 - 2 * (k % 2)
            t = [x + g * s[2 + k // 2][0], y + g * s[2 + k // 2][1], s[2], s[3], 1 - s[4]]
            a, b = fit(value, t, p)
            m.append((t[0] + a, t[1] + b))
        s[2:4] = [[(m[0][0] - m[1][0]) // 2, (m[0][1] - m[1][1]) // 2],
                  [(m[2][0] - m[3][0]) // 2, (m[2][1] - m[3][1]) // 2]]
        seeds.append(s)
    # the header in the four quarter turns of every seed, best first;
    # the turn whose check passes is the page's (none: the frame's own)
    hd, n = None, 0
    for s in seeds:
        for m in range(4):
            if hd == None:
                hd, n = header(value, turn(s, m)), m
    seeds = [turn(s, n * (hd != None)) for s in seeds]
    return walk(value, w, h, found[0][3] if found else 0, seeds), hd
"""
rung('r11_joint_pose', 'r09_clock',
     ('REGION', 'def clock(value, x, y, p):', 'def turn(s, n):', FIT_R11),
     ("""        fr = [(spot(s, dx, dy), 1 - 2 * (par ^ s[4]))
              for dx, dy, par in FRAME]
        if s[5]:
            mx = my = 0
            for st in (p // 32, p // 64, p // 128, p // 256):
                f, mx, my = max((sum(value(x + a, y + b) * wt
                                     for (x, y), wt in fr), a, b)
                                for a in (mx - st, mx, mx + st)
                                for b in (my - st, my, my + st))
            k = s[5] - 1""", """        if s[5]:
            mx, my = fit(value, s, p)
            k = s[5] - 1"""),
     ('REGION', 'def read_frame(name):', '# ======== main: one frame per line ========', FRAME_R11))

# ---- r12: the walk learns both axes ----------------------------------------
# A block is (seed, i, j) in its seed's lattice; after its refinement its A
# and B are measured to its placed neighbours one block nearer the seed
# (in breadth-first order both exist for i, j != 0), instead of correcting
# only the axis it was reached along (the other went stale under
# perspective: 0.35 module at block corners ten blocks from a lone seed).
WALK_R12 = """def walk(value, w, h, p, todo):
    # Breadth first from every seed at once; a block is (seed, i, j) in
    # its seed's own block lattice.  It is placed at its parent's centre
    # plus the parent's 17-module step and refined on its 68 timing
    # modules; its own steps A and B are then measured to its placed
    # neighbours one block nearer the seed: the walk learns the lattice
    # as it goes.  The clock is sound when the timing score reaches 60 %
    # of the modules' total deviation from their mean, or the block's
    # CRC checks; only sound blocks are walked through; blocks that leave
    # the frame are not read; a block within a cell of 5 modules of one
    # already reached is not reached again.  -> the accepted blocks
    seen, done, got, c = {}, {}, [], 5 * p >> 4
    for s in todo:
        u, v = s[0] // c, s[1] // c
        if [1 for a in (-1, 0, 1) for b in (-1, 0, 1)
                if (u + a, v + b) in seen]:
            continue
        seen[u, v] = 1
        if [1 for x, y in [spot(s, -11, -11), spot(s, 10, 10),
                           spot(s, 10, -11), spot(s, -11, 10)]
                if min(x, y) < 0 or x > 16 * w - 32 or y > 16 * h - 32]:
            continue
        g, i, j = s[5]
        if i or j:
            mx, my = fit(value, s, p)
            s[0], s[1] = s[0] + mx, s[1] + my
            for k, d in ((2, j), (3, i)):
                q = (d > 0) - (d < 0)
                t = done.get((g, i - q * (k == 3), j - q * (k == 2)))
                if t:
                    s[k] = [q * (s[0] - t[0]), q * (s[1] - t[1])]
        tv = [(value(*spot(s, dx, dy)), 1 - 2 * (par ^ s[4]))
              for dx, dy, par in FRAME]
        t = sum(v for v, i in tv) // 68
        sound = 5 * sum(v * i for v, i in tv) >= 3 * sum(
            abs(v - t) for v, i in tv)
        if i or j:
            w32 = read_block(value, s)
            if w32:
                got.append(w32)
                sound = 1
        if sound:
            done[g, i, j] = s
            for k in range(4):
                q = 1 - 2 * (k % 2)
                todo.append([s[0] + q * s[2 + k // 2][0],
                             s[1] + q * s[2 + k // 2][1], s[2], s[3],
                             1 - s[4], (g, i + q * (k > 1), j + q * (k < 2))])
    return got


"""
rung('r12_walk_both_axes', 'r11_joint_pose',
     ('REGION', 'def walk(value, w, h, p, todo):', 'def read_block(value, s):', WALK_R12),
     ("""                      for dx, dy, par in FRAME) < 0), 0]
""", """                      for dx, dy, par in FRAME) < 0), (len(seeds), 0, 0)]
"""))

# ---- r13: a second read for sound blocks whose CRC failed ------------------
# after the walk, with A and B from both neighbours on each axis (central
# differences; the seed's own row and column have no neighbour nearer the
# seed across the walk's direction)
rung('r13_retry_central', 'r12_walk_both_axes',
     ("""    seen, done, got, c = {}, {}, [], 5 * p >> 4
""", """    seen, done, got, c, miss = {}, {}, [], 5 * p >> 4, []
"""),
     ("""            if w32:
                got.append(w32)
                sound = 1
        if sound:
            done[g, i, j] = s
""", """            if w32:
                got.append(w32)
                sound = 1
            elif sound:
                miss.append(s)
        if sound:
            done[g, i, j] = s
"""),
     ("""                             1 - s[4], (g, i + q * (k > 1), j + q * (k < 2))])
    return got
""", """                             1 - s[4], (g, i + q * (k > 1), j + q * (k < 2))])
    for s in miss:
        g, i, j = s[5]
        for k, a, b in ((2, (g, i, j + 1), (g, i, j - 1)),
                        (3, (g, i + 1, j), (g, i - 1, j))):
            if a in done and b in done:
                s[k] = [(done[a][0] - done[b][0]) // 2,
                        (done[a][1] - done[b][1]) // 2]
        w32 = read_block(value, s)
        if w32:
            got.append(w32)
    return got
"""))

# ---- r14: r13 with the per-tile binarisation back (r01 refused under the
# seed pose: the global threshold loses bullseyes on sigma 0.45 quarters)
BIN_TILES = '''def binarise(img, w, h):
    # Ink = 1.  One threshold per tile of about 1/64 of the frame's
    # perimeter: the midpoint of the tile's 5th and 95th percentile, or
    # the frame's global one where the tile is flat (paper, background).
    s = sorted(img[::97])
    lo, hi = s[len(s) // 20], s[len(s) - 1 - len(s) // 20]
    out, step = bytearray(w * h), max(16, (w + h) // 64)
    for y0 in range(0, h, step):
        y1 = min(h, y0 + step)
        for x0 in range(0, w, step):
            x1 = min(w, x0 + step)
            v = sorted(b''.join(img[y * w + x0:y * w + x1:3]
                                for y in range(y0, y1, 3)))
            a, b = v[len(v) // 20], v[len(v) - 1 - len(v) // 20]
            t = (lo + hi) // 2
            if 4 * (b - a) > hi - lo:
                t = (a + b) // 2
            for y in range(y0, y1):
                row = img[y * w + x0:y * w + x1]
                out[y * w + x0:y * w + x1] = row.translate(
                    bytes(int(x < t) for x in range(256)))
    return bytes(out)


'''
rung('r14_tile_threshold', 'r13_retry_central',
     ('REGION', 'def binarise(img, w, h):', '# ---- 2. bullseyes', BIN_TILES))

# ---- single-edit probes on r13 ---------------------------------------------
HEAD_CHASE = """        lv = [t - v[a, b] + ((v[a - 1, b] + v[a + 1, b] + v[a, b - 1]
                              + v[a, b + 1] - 4 * v[a, b]) * s8 >> 3)
              for a, b in HEAD]
        weak = sorted(range(68), key=lambda i: abs(lv[i]))[:4]
        for f in range(16):
            b = [int(z > 0) for z in lv]
            for j in range(4):
                b[weak[j]] ^= f >> j & 1
            x = int(''.join('01'[z] for z in b), 2)
            if crc32((x >> 20).to_bytes(6, e)) % 2 ** 20 == x % 2 ** 20:
                return (x >> 20).to_bytes(6, e)
"""
HEAD_PLAIN = """        x = int(''.join('01'[t - v[a, b] + ((v[a - 1, b] + v[a + 1, b]
                                + v[a, b - 1] + v[a, b + 1] - 4 * v[a, b])
                               * s8 >> 3) > 0] for a, b in HEAD), 2)
        if crc32((x >> 20).to_bytes(6, e)) % 2 ** 20 == x % 2 ** 20:
            return (x >> 20).to_bytes(6, e)
"""
rung('r15_header_no_chase', 'r13_retry_central', (HEAD_CHASE, HEAD_PLAIN))
COMB13 = ('REGION', '    out = []\n    for i in range(1 + line[0], len(edge) - 12, 2):',
          'def ring_fit(value, x, y, p):', '''    out = []
    for i in range(1 + line[0], len(edge) - 14, 2):
        c0 = edge[i] + edge[i + 1]
        span = edge[i + 12] + edge[i + 13] - c0
        if span >= 24 and 96 * min(edge[i] - edge[i - 1],
                                   edge[i + 14] - edge[i + 13]) >= span:
            if max(abs(12 * (edge[i + k + 6] + edge[i + k + 7] - c0)
                       - (k + 6) * span) for k in KS) <= (
                    3 * span + 144) // 10:
                out.append((c0 + edge[i + 12] + edge[i + 13] - 2, span))
    return out


''')
rung('r16_comb13', 'r13_retry_central', COMB13)
RING_HIT = ("""            hit = sum(bits[(cy + (dy * p >> 4) + 8 >> 4) * w
                           + (cx + (dx * p >> 4) + 8 >> 4)] == i
                      for dx, dy, i in RING)
            if 4 * hit < 3 * len(RING):
                continue
""", "")
rung('r17_no_ring_hit', 'r13_retry_central', RING_HIT)
RING_MEANS = [
    ("""N_INK = sum(ink for dx, dy, ink in RING)
N_WHITE = len(RING) - N_INK
""", ""),
    ("""    # contrast of the ring template at centre (x, y) (1/16 px), pitch p
    # (1/256 px): proportional to mean white minus mean ink
    ink = white = 0
    for dx, dy, i in RING:
        if i:
            ink += value(x + (dx * p >> 4), y + (dy * p >> 4))
        else:
            white += value(x + (dx * p >> 4), y + (dy * p >> 4))
    return white * N_INK - ink * N_WHITE
""", """    # contrast of the ring template at centre (x, y) (1/16 px), pitch p
    # (1/256 px): its whites minus its inks
    return sum(value(x + (dx * p >> 4), y + (dy * p >> 4)) * (1 - 2 * i)
               for dx, dy, i in RING)
"""),
    ("""    t = (sum(v[dx, dy] for dx, dy, i in RING if i) // N_INK + sum(
        v[dx, dy] for dx, dy, i in RING if i == 0) // N_WHITE) // 2
""", """    m = sorted(v[dx, dy] for dx, dy, i in FRAME)
    t = (m[8] + m[59]) // 2
""")]
rung('r18_no_ring_means', 'r13_retry_central', *RING_MEANS)
SOUND_CRC = ("""            if w32:
                got.append(w32)
                sound = 1
            elif sound:
                miss.append(s)
""", """            if w32:
                got.append(w32)
            elif sound:
                miss.append(s)
""")
rung('r19_sound_by_timing', 'r13_retry_central', SOUND_CRC)
BOUNDS = ("""            if min(cx, cy) < p // 2 or cx > 16 * w - p // 2 - 32:
                continue
            if cy > 16 * h - p // 2 - 32:
                continue
""", "")
rung('r20_no_finder_bounds', 'r17_no_ring_hit', BOUNDS)

# ---- r21: r13 + the four free probes (r15, r16, r18, r19) ------------------
rung('r21_compose', 'r13_retry_central', (HEAD_CHASE, HEAD_PLAIN), COMB13, *RING_MEANS, SOUND_CRC)

# ---- r22: the grid text is drawn as an image (3 px per module) and read by
# the image path; the loupe path's own code (cell, read_grid, BULLS) goes
LOAD_GRID = ("""    return 0, 0, raw.split()
""", """    # the module grid as text: drawn at 3 px per module, '1' ink (0),
    # '0' white (255), anything else 128, in a margin of 4 white modules
    rows = raw.split()
    z = [b'0' * (len(rows[0]) + 8)] * 4
    rows = z + [b'0000' + r + b'0000' for r in rows] + z
    return 3 * len(rows[0]), 3 * len(rows), b''.join(
        bytes({48: 255, 49: 0}.get(z, 128) for z in r for i in 'abc') * 3
        for r in rows)
""")
rung('r22_grid_as_image', 'r21_compose', LOAD_GRID,
     ('REGION', '# ---- the loupe path ---', '# ---- one frame ---', ''),
     ("""    if w == 0:
        return read_grid(img)
""", ""),
     ("""BULLS = [(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)] + [
    (bi, bj) for bi in (8, 20) for bj in (5, 11, 17)]
""", ""))

# ---- r23: one decode for header and blocks (the header's equaliser order
# becomes the blocks' 8, 4, 0; still no Chase for the header)
rung('r23_one_decode', 'r22_grid_as_image',
     ('REGION', 'def header(value, s):', '# ---- 5. walk', '''def header(value, s):
    # the 68 header bits around a bullseye seen through seed s -> the six
    # header bytes if the 20-bit check passes
    v = sample(value, s)
    m = sorted(v[dx, dy] for dx, dy, i in FRAME)
    return decode(v, (m[8] + m[59]) // 2, HEAD, 20)


def decode(v, t, u, m):
    # modules u sampled as v, threshold t; m check bits (32: a data
    # block, CRC-32 of its 28 bytes; 20: the header, CRC-32 of its six
    # bytes mod 2**20).  Equaliser at 8, 4 and 0 eighths of the
    # Laplacian; for a data block at each strength Chase over the six
    # least reliable modules, at 0 also every single flip.  -> the bytes
    # before the check, or None
    n = len(u)
    for s8 in (8, 4, 0):
        lv = [t - v[a, b] + ((v[a - 1, b] + v[a + 1, b] + v[a, b - 1]
                              + v[a, b + 1] - 4 * v[a, b]) * s8 >> 3)
              for a, b in u]
        x = int(''.join('01'[z > 0] for z in lv), 2)
        wk = sorted(range(n), key=lambda i: abs(lv[i]))[:6 * (m > 20)]
        for f in [sum(1 << n - 1 - wk[j] for j in range(len(wk))
                      if f >> j & 1) for f in range(2 ** len(wk))] + [
                1 << i for i in range(n * (s8 < 1) * (m > 20))]:
            y = x ^ f
            if crc32((y >> m).to_bytes((n - m) // 8, e)) % 2 ** m == (
                    y % 2 ** m):
                return (y >> m).to_bytes((n - m) // 8, e)


'''),
     ('REGION', 'def read_block(value, s):', '# ---- one frame ---', '''def read_block(value, s):
    # Threshold midway between the 9th darkest and the 9th brightest of
    # the 68 timing modules.  A block showing the rings is an unseen
    # bullseye, one with fewer than 4 inks a white slot: not tried.
    v = sample(value, s)
    m = sorted(v[dx, dy] for dx, dy, i in FRAME)
    t = (m[8] + m[59]) // 2
    if 5 * sum((v[x, y] < t) == i for x, y, i in RING) > 4 * len(RING):
        return None
    if sum(v[x, y] < t for x, y in DATA) > 3:
        return decode(v, t, DATA, 32)


'''))

# ---- r24: no grey centre refinement in the finder; a seed's centre is the
# mean of its four neighbours' refined centres (computed for A and B anyway);
# bullseyes ordered by their binarised ring-hit count
rung('r24_centre_from_neighbours', 'r23_one_decode',
     ("""            for st in (p // 64, p // 128, p // 256):
                f, cx, cy = max((ring_fit(value, a, b, p), a, b)
                                for a in (cx - st, cx, cx + st)
                                for b in (cy - st, cy, cy + st))
            found.append((f, cx, cy, p))
""", """            found.append((hit, cx, cy, p))
"""),
     ('REGION', 'def ring_fit(value, x, y, p):', 'def bullseyes(img, bits, w, h, value):', ''),
     ("""        s[2:4] = [[(m[0][0] - m[1][0]) // 2, (m[0][1] - m[1][1]) // 2],
                  [(m[2][0] - m[3][0]) // 2, (m[2][1] - m[3][1]) // 2]]
""", """        s[:4] = [sum(z[0] for z in m) // 4, sum(z[1] for z in m) // 4,
                 [(m[0][0] - m[1][0]) // 2, (m[0][1] - m[1][1]) // 2],
                 [(m[2][0] - m[3][0]) // 2, (m[2][1] - m[3][1]) // 2]]
"""))

# ---- r27: the second read also takes the block's centre from its placed
# neighbours (the mean of the pairs' midpoints): an estimate independent of
# the block's own refinement, which can sit ~0.1 module off at sigma 0.45
rung('r27_retry_centre', 'r24_centre_from_neighbours',
     ("""    for s in miss:
        g, i, j = s[5]
        for k, a, b in ((2, (g, i, j + 1), (g, i, j - 1)),
                        (3, (g, i + 1, j), (g, i - 1, j))):
            if a in done and b in done:
                s[k] = [(done[a][0] - done[b][0]) // 2,
                        (done[a][1] - done[b][1]) // 2]
""", """    for s in miss:
        g, i, j = s[5]
        q = []
        for k, a, b in ((2, (g, i, j + 1), (g, i, j - 1)),
                        (3, (g, i + 1, j), (g, i - 1, j))):
            if a in done and b in done:
                s[k] = [(done[a][0] - done[b][0]) // 2,
                        (done[a][1] - done[b][1]) // 2]
                q += [[(done[a][0] + done[b][0]) // 2,
                       (done[a][1] + done[b][1]) // 2]]
        if q:
            s[0] = sum(z[0] for z in q) // len(q)
            s[1] = sum(z[1] for z in q) // len(q)
"""))

# ---- r26: a fifth, 1/32-module step in the block refinement
rung('r26_fine_step', 'r24_centre_from_neighbours',
     ("""    mx = my = 0
    for st in (p // 32, p // 64, p // 128, p // 256):
        f, mx, my = max((sum(value(x + a, y + b) * wt
                             for (x, y), wt in fr), a, b)""",
      """    mx = my = 0
    for st in (p // 32, p // 64, p // 128, p // 256, p // 512):
        f, mx, my = max((sum(value(x + a, y + b) * wt
                             for (x, y), wt in fr), a, b)"""))

# ---- r25: place first, read after: the walk only places (sound by timing);
# then every placed block in frame is read once, with A and B by central
# differences wherever both neighbours were placed (r13's second read for all)
rung('r25_place_then_read', 'r24_centre_from_neighbours',
     ("""    seen, done, got, c, miss = {}, {}, [], 5 * p >> 4, []
""", """    seen, done, got, c, miss = {}, {}, [], 5 * p >> 4, []
    # miss: every placed block in frame but the seeds, read after the walk
"""),
     ("""        if i or j:
            w32 = read_block(value, s)
            if w32:
                got.append(w32)
            elif sound:
                miss.append(s)
        if sound:
""", """        if i or j:
            miss.append(s)
        if sound:
"""))

# ==== the SET pass (owner's ruling, 2026-10-20 night: "Simplify the reader!
# We need good enough recovery, not perfect."): probes on r27, measured by
# w4_sets.py (a payload closes from a reasonable set of frames, pooled) ====
NO_MISS = [("""    seen, done, got, c, miss = {}, {}, [], 5 * p >> 4, []
""", """    seen, done, got, c = {}, {}, [], 5 * p >> 4
"""),
           ("""            if w32:
                got.append(w32)
            elif sound:
                miss.append(s)
""", """            if w32:
                got.append(w32)
"""),
           ('REGION', '    for s in miss:\n', 'def read_block(value, s):', """    return got


""")]
rung('s01_no_second_read', 'r27_retry_centre', *NO_MISS)
NO_NB = ('REGION', "        # A and B from the four neighbours' refined centres\n",
         '        seeds.append(s)\n', '')
rung('s02_no_seed_neighbours', 'r27_retry_centre', NO_NB)
EQ_LOOP = '    for s8 in (8, 4, 0):\n'
rung('s04a_eq_4_0', 'r27_retry_centre', (EQ_LOOP, '    for s8 in (4, 0):\n'))
rung('s04b_eq_4_only', 'r27_retry_centre', (EQ_LOOP, '    for s8 in (4,):\n'),
     ('1 << i for i in range(n * (s8 < 1) * (m > 20))]:',
      '1 << i for i in range(n * (m > 20))]:'))
rung('s05_no_equaliser', 'r27_retry_centre', (EQ_LOOP, '    for s8 in (0,):\n'))
CHASE6 = '[:6 * (m > 20)]'
rung('s06_singles_only', 'r27_retry_centre', (CHASE6, '[:0]'))
rung('s07_plain_read', 'r27_retry_centre', (CHASE6, '[:0]'),
     ('1 << i for i in range(n * (s8 < 1) * (m > 20))]:', '1 << i for i in range(0)]:'))
rung('s09_header_frame_turn', 'r27_retry_centre',
     ("""        for m in range(4):
            if hd == None:
                hd, n = header(value, turn(s, m)), m
""", """        if hd == None:
            hd = header(value, s)
"""),
     ('    seeds = [turn(s, n * (hd != None)) for s in seeds]\n', ''))
RB_RING = """    if 5 * sum((v[x, y] < t) == i for x, y, i in RING) > 4 * len(RING):
        return None
"""
rung('s11_no_rb_ring_check', 'r27_retry_centre', (RB_RING, ''))
WHITE = ("""    if sum(v[x, y] < t for x, y in DATA) > 3:
        return decode(v, t, DATA, 32)
""", """    return decode(v, t, DATA, 32)
""")
rung('s12_no_white_check', 'r27_retry_centre', WHITE)
HDR4 = ("""        for m in range(4):
            if hd == None:
                hd, n = header(value, turn(s, m)), m
""", """        if hd == None:
            hd = header(value, s)
""")
HDR4b = ('    seeds = [turn(s, n * (hd != None)) for s in seeds]\n', '')
DEC_NOCHASE = ('REGION', 'def decode(v, t, u, m):', '# ---- 5. walk', '''def decode(v, t, u, m):
    # modules u sampled as v, threshold t; m check bits (32: a data
    # block, CRC-32 of its 28 bytes; 20: the header, CRC-32 of its six
    # bytes mod 2**20).  Equaliser at 8, 4 and 0 eighths of the
    # Laplacian; for a data block at 0 also every single flip.  -> the
    # bytes before the check, or None
    n = len(u)
    for s8 in (8, 4, 0):
        x = int(''.join('01'[t - v[a, b] + ((v[a - 1, b] + v[a + 1, b]
                                + v[a, b - 1] + v[a, b + 1] - 4 * v[a, b])
                               * s8 >> 3) > 0] for a, b in u), 2)
        for f in [0] + [1 << i for i in range(n * (s8 < 1) * (m > 20))]:
            y = x ^ f
            if crc32((y >> m).to_bytes((n - m) // 8, e)) % 2 ** m == (
                    y % 2 ** m):
                return (y >> m).to_bytes((n - m) // 8, e)


''')
DEC_ONE = ('REGION', 'def decode(v, t, u, m):', '# ---- 5. walk', '''def decode(v, t, u, m):
    # modules u sampled as v, threshold t; m check bits (32: a data
    # block, CRC-32 of its 28 bytes; 20: the header, CRC-32 of its six
    # bytes mod 2**20).  The equaliser at half the Laplacian; for a data
    # block also every single flip.  -> the bytes before the check, or
    # None
    n = len(u)
    x = int(''.join('01'[t - v[a, b] + (v[a - 1, b] + v[a + 1, b]
                                         + v[a, b - 1] + v[a, b + 1]
                                         - 4 * v[a, b] >> 1) > 0]
                    for a, b in u), 2)
    for f in [0] + [1 << i for i in range(n * (m > 20))]:
        y = x ^ f
        if crc32((y >> m).to_bytes((n - m) // 8, e)) % 2 ** m == y % 2 ** m:
            return (y >> m).to_bytes((n - m) // 8, e)


''')
# c01: the structural drops that cost no set (s01, s02, s09, s11) and the
# decode without Chase (s06: equaliser 8, 4, 0; single flips at 0)
rung('c01_compose', 'r27_retry_centre', *NO_MISS, NO_NB, HDR4, HDR4b, (RB_RING, ''), DEC_NOCHASE)
# c02: c01 with ONE equaliser strength (half the Laplacian) and single
# flips, and no white-slot check (the decode is cheap now)
rung('c02_one_strength', 'c01_compose', DEC_ONE, WHITE)
# c03: no axis learning at all: every block keeps its seed's A and B (each
# block is reached by the nearest seed); no block index, no done table
WALK_C03 = """def walk(value, w, h, p, todo):
    # Breadth first from every seed at once.  A block is placed at its
    # parent's centre plus its seed's 17-module step and refined on its
    # 68 timing modules.  The clock is sound when the timing score
    # reaches 60 % of the modules' total deviation from their mean; only
    # sound blocks are walked through; blocks that leave the frame are
    # not read; a block within a cell of 5 modules of one already
    # reached is not reached again.  -> the accepted blocks
    seen, got, c = {}, [], 5 * p >> 4
    for s in todo:
        u, v = s[0] // c, s[1] // c
        if [1 for a in (-1, 0, 1) for b in (-1, 0, 1)
                if (u + a, v + b) in seen]:
            continue
        seen[u, v] = 1
        if [1 for x, y in [spot(s, -11, -11), spot(s, 10, 10),
                           spot(s, 10, -11), spot(s, -11, 10)]
                if min(x, y) < 0 or x > 16 * w - 32 or y > 16 * h - 32]:
            continue
        if s[5]:
            mx, my = fit(value, s, p)
            s[0], s[1] = s[0] + mx, s[1] + my
            w32 = read_block(value, s)
            if w32:
                got.append(w32)
        tv = [(value(*spot(s, dx, dy)), 1 - 2 * (par ^ s[4]))
              for dx, dy, par in FRAME]
        t = sum(v for v, i in tv) // 68
        if 5 * sum(v * i for v, i in tv) >= 3 * sum(abs(v - t) for v, i in tv):
            for k in range(4):
                q = 1 - 2 * (k % 2)
                todo.append([s[0] + q * s[2 + k // 2][0],
                             s[1] + q * s[2 + k // 2][1], s[2], s[3],
                             1 - s[4], 1])
    return got


"""
rung('c03_no_axis_learning', 'c02_one_strength',
     ('REGION', 'def walk(value, w, h, p, todo):', 'def read_block(value, s):', WALK_C03),
     ('                      for dx, dy, par in FRAME) < 0), (len(seeds), 0, 0)]\n',
      '                      for dx, dy, par in FRAME) < 0), 0]\n'))
rung('c04_mean_threshold', 'c02_one_strength',
     ("""    s = sorted(img[::97])
    t = (s[len(s) // 20] + s[len(s) - 1 - len(s) // 20]) // 2
""", """    t = sum(img[::97]) // len(img[::97])
"""))
rung('c05_no_column_comb', 'c02_one_strength',
     ('REGION', '            y0, y1 = max(0, y - d2 // 2 - 2), min(h, y + d2 // 2 + 3)\n',
      '            if min(cx, cy) < p // 2 or cx > 16 * w - p // 2 - 32:\n',
      '            cx, cy, p = 4 * c4, 16 * y, 32 * d2 // 3\n'))
rung('c06_no_sort', 'c02_one_strength',
     ('    return sorted(found, reverse=True)\n', '    return found\n'))
rung('c09_no_rotation_search', 'c02_one_strength',
     ('    for r in range(-640, 641, 64):\n', '    for r in (0,):\n'))
# c10: c02 + the mean threshold (c04) + no bullseye sort (c06)
rung('c10_compose', 'c02_one_strength',
     ("""    s = sorted(img[::97])
    t = (s[len(s) // 20] + s[len(s) - 1 - len(s) // 20]) // 2
""", """    t = sum(img[::97]) // len(img[::97])
"""),
     ('    return sorted(found, reverse=True)\n', '    return found\n'))
rung('c14_no_soundness', 'c10_compose',
     ("""        tv = [(value(*spot(s, dx, dy)), 1 - 2 * (par ^ s[4]))
              for dx, dy, par in FRAME]
        t = sum(v for v, i in tv) // 68
        sound = 5 * sum(v * i for v, i in tv) >= 3 * sum(
            abs(v - t) for v, i in tv)
""", """        sound = 1
"""))
NEWEST = ("""    if hd:
        heads[hd] = heads.get(hd, 0) + 1
    if heads:
        hd = max(heads, key=heads.get)
""", """    if hd:
        heads = hd
    if heads:
        hd = heads
""")
rung('c20_compose', 'c10_compose', NEWEST)
rung('c23_no_frame_check', 'c20_compose',
     ("""        if [1 for x, y in [spot(s, -11, -11), spot(s, 10, 10),
                           spot(s, 10, -11), spot(s, -11, 10)]
                if min(x, y) < 0 or x > 16 * w - 32 or y > 16 * h - 32]:
            continue
""", ""))
rung('c24_no_grid_margin', 'c23_no_frame_check',
     ("""    z = [b'0' * (len(rows[0]) + 8)] * 4
    rows = z + [b'0000' + r + b'0000' for r in rows] + z
""", ""))
rung('c27_weak_soundness', 'c23_no_frame_check',
     ("""        t = sum(v for v, i in tv) // 68
        sound = 5 * sum(v * i for v, i in tv) >= 3 * sum(
            abs(v - t) for v, i in tv)
""", """        sound = sum(v * i for v, i in tv) > 0
"""))
rung('c29_own_cell_dedupe', 'c23_no_frame_check',
     ("""        if [1 for a in (-1, 0, 1) for b in (-1, 0, 1)
                if (u + a, v + b) in seen]:
            continue
        seen[u, v] = 1
""", """        if (u, v) in seen:
            continue
        seen[u, v] = 1
"""))
rung('c29b_own_cell_dedupe', 'c20_compose',
     ("""        if [1 for a in (-1, 0, 1) for b in (-1, 0, 1)
                if (u + a, v + b) in seen]:
            continue
        seen[u, v] = 1
""", """        if (u, v) in seen:
            continue
        seen[u, v] = 1
"""))
# ---- set I (the last page, mostly white): the threshold must not follow
# the paper.  The frame-wide mean (c04) sits next to paper on a 90 % white
# frame; the 5th/95th percentile midpoint failed on the same frames.
MEAN_T = """    t = sum(img[::97]) // len(img[::97])
"""
rung('d01_minmax_threshold', 'c29b_own_cell_dedupe',
     (MEAN_T, """    t = (min(img[::97]) + max(img[::97])) // 2
"""))
rung('d03_minmax_margin1', 'd01_minmax_threshold',
     ("""        if [1 for x, y in [spot(s, -11, -11), spot(s, 10, 10),
                           spot(s, 10, -11), spot(s, -11, 10)]""",
      """        if [1 for x, y in [spot(s, -10, -10), spot(s, 9, 9),
                           spot(s, 9, -10), spot(s, -10, 9)]"""))
rung('d04_white_check_back', 'd03_minmax_margin1',
     ("""    return decode(v, t, DATA, 32)
""", """    if sum(v[x, y] < t for x, y in DATA) > 3:
        return decode(v, t, DATA, 32)
"""))
# ---- d05: the 2026-10-20 night format rulings.  (1) A data block's CRC-32
# covers the payload's six header bytes followed by its bytes 0-27: blocks
# are checked against the payload's header (the first one read in the run;
# on that frame, its own), and a frame is not walked until a header is
# known.  (2) The tail asserts the decoded bundle's CRC-32 == B2 (a print-
# time token like N2) before it writes b.py.
rung('d05_header_bound', 'd04_white_check_back',
     ('def decode(v, t, u, m):\n', 'def decode(v, t, u, m, h6):\n'),
     ("        if crc32((y >> m).to_bytes((n - m) // 8, e)) % 2 ** m == y % 2 ** m:\n",
      "        if crc32(h6 + (y >> m).to_bytes((n - m) // 8, e)) % 2 ** m == (\n"
      "                y % 2 ** m):\n"),
     ('    return decode(v, (m[8] + m[59]) // 2, HEAD, 20)\n',
      "    return decode(v, (m[8] + m[59]) // 2, HEAD, 20, b'')\n"),
     ('        return decode(v, t, DATA, 32)\n', '        return decode(v, t, DATA, 32, h6)\n'),
     ('def read_block(value, s):\n', 'def read_block(value, s, h6):\n'),
     ('def walk(value, w, h, p, todo):\n', 'def walk(value, w, h, p, todo, h6):\n'),
     ('            w32 = read_block(value, s)\n', '            w32 = read_block(value, s, h6)\n'),
     ('def read_frame(name):\n', 'def read_frame(name, known):\n'),
     ('    return walk(value, w, h, found[0][3] if found else 0, seeds), hd\n',
      """    # blocks are checked against the payload's header: the first one read
    # in the run, on that frame its own; none yet: nothing can validate
    h6 = known or hd
    if h6 == None:
        return [], None
    return walk(value, w, h, found[0][3] if found else 0, seeds, h6), hd
"""),
     ("chunks, heads, done, need = {}, {}, 0, '?'\n", "chunks, heads, done, need = {}, None, 0, '?'\n"),
     ('    got, hd = read_frame(name)\n', '    got, hd = read_frame(name, heads)\n'),
     ("""    if hd:
        heads = hd
    if heads:
""", """    heads = heads or hd
    if heads:
"""),
     ("""    out = d(int.from_bytes(data, e), N2, open('r.py', 'rb').read())
    open('b.py', 'wb').write(out)
""", """    out = d(int.from_bytes(data, e), N2, open('r.py', 'rb').read())
    assert crc32(out) == B2
    open('b.py', 'wb').write(out)
"""))
# ---- d06: the refuter's panel 21 fixes, ruled 2026-10-20 night.  (1) An
# unreadable input (a mistyped name, a trailing space, a directory, an
# empty, truncated or commented file, a 0 x 0 image) is reported as
# "cannot read" and the session goes on; the end of the input ends the run
# like an empty line.  (2) The progress line says how many bullseyes the
# frame showed.  (3) A block on its seed's own row or column (q = 0) does
# not take its own earlier copy as the neighbour its step is measured to.
rung('d06_panel21', 'd05_header_bound',
     ('                t = done.get((g, i - q * (k == 3), j - q * (k == 2)))\n'
      '                if t:\n',
      '                t = done.get((g, i - q * (k == 3), j - q * (k == 2)))\n'
      '                if t and q:\n'),
     ('    # -> (32-byte blocks, header or None)\n',
      '    # -> (32-byte blocks, header or None, bullseyes found)\n'),
     ('        return [], None\n    return walk(value, w, h, found[0][3] if found else 0, seeds, h6), hd\n',
      '        return [], None, len(found)\n'
      '    return (walk(value, w, h, found[0][3] if found else 0, seeds, h6), hd,\n'
      '            len(found))\n'),
     ("""    name = input('R2 frame (P5 PGM or 0/1 grid, empty line stops): ')
    if name == '':
        break
    got, hd = read_frame(name, heads)
""", """    try:
        name = input('R2 frame (P5 PGM or 0/1 grid, empty line stops): ').strip()
    except EOFError:
        break
    if name == '':
        break
    try:
        got, hd, note = read_frame(name, heads)
        note = '%d bullseyes' % note
    except Exception:
        got, hd, note = [], None, 'cannot read'
"""),
     ("""    print(name + ':', len(got), 'blocks accepted, chunks', held, '/',
          need, ['- more frames needed', '- done'][done])
""", """    print(name + ': ' + note + ',', len(got), 'blocks accepted, chunks', held,
          '/', need, ['- more frames needed', '- done'][done])
"""))
rung('d02_p1_p99_threshold', 'c29b_own_cell_dedupe',
     (MEAN_T, """    s = sorted(img[::97])
    t = (s[len(s) // 100] + s[len(s) - 1 - len(s) // 100]) // 2
"""))
rung('c16_newest_header', 'c10_compose',
     ("""    if hd:
        heads[hd] = heads.get(hd, 0) + 1
    if heads:
        hd = max(heads, key=heads.get)
""", """    if hd:
        heads = hd
    if heads:
        hd = heads
"""))


def build(names=None):
    os.makedirs(V1, exist_ok=True)
    # the ladder's base: reader.py as it stood before the 2026-10-20 night
    # rulings (block CRC bound to the header, tail asserting B2), frozen
    src0 = open(os.path.join(V1, 'r00_base.py')).read()
    texts = {'r00_reader': src0}
    open(os.path.join(V1, 'r00_reader.py'), 'w').write(src0)
    for name, parent, edits in RUNGS:
        texts[name] = apply(texts[parent], edits, name)
        if names and name not in names:
            continue
        open(os.path.join(V1, name + '.py'), 'w').write(texts[name])
        print('wrote', name)
    return texts


if __name__ == '__main__':
    build(sys.argv[1:] or None)
