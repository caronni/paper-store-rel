# BEGIN READER
#--- shared with the loader (not typed) ---
# The loader's definitions: the typed chain writes r.py as a.py's
# definitions (d = the cm2 v2 decoder, q = the alphabet, k = the line
# check) followed by the reader text with this region dropped, so the
# reader never binds d, q or k.  It uses d; this copy only lets
# reader.py run on its own.
def d(x, n, primer):
  # cm2 v2 (typed/cm2_dec.py's decode, body verbatim): the coded message
  # x as ONE integer, output length n, primer bytes -> the n decoded bytes.
  # Per bit the model gives weights p0, p1; slot = x % (p0+p1) says the
  # bit (slot >= p0 is a 1) and x shrinks to x // s * p_y + slot - cum.
  ms = [256 ** o - 1 for o in (0, 1, 2, 3, 4, 6, 8, 12, 16)]
  m, t, h = len(primer), {}, 0
  for i in range(m + n):
    c0 = 1
    for j in range(8):
      cs = [t.setdefault((h & q, c0), [0, 0]) for q in ms]
      p = [1 + sum(c[y] << w + (c[1 - y] == 0) for w, c in enumerate(cs))
           for y in (0, 1)]
      if i < m:
        y = primer[i] >> 7 - j & 1
      else:
        f, slot = divmod(x, p[0] + p[1])
        y = slot >= p[0]
        x = f * p[y] + slot - p[0] * y
      for c in cs:
        c[y], c[1 - y] = c[y] + 1, min(c[1 - y], c[1 - y] // 4 + 2)
      c0 = c0 * 2 + y
    h = h << 8 | c0 & 255
  return h.to_bytes(m + n, 'big')[m:]
#--- end shared ---
e = 'big'   # byte order for int.from_bytes (3.9/3.10 need it spelled)
# R2 page reader v1 (R2-FORMAT v1, 2026-10-20), the readable reference.
#
# Run `python3 r.py` and give it frames, one file name per line: P5 PGM
# photos or scans of R2 pages, whole or partial, in any quarter turn,
# or the module grid typed as text (H lines of W characters, '1' ink,
# '0' white, anything else unreadable).  Blocks are pooled over all
# frames and pages, with one progress line per frame.  When chunks
# 0..N-1 are held and the data's CRC-32 equals the header's, the data
# are decompressed with cm2 (primer: the text of r.py) into b.py.  An
# empty line stops.
#
# Typed subset: no import, no float, no true division, no semicolon,
# tilde or at-sign; builtins input open print len range sum min max abs
# enumerate sorted int ord chr bytes bytearray str only.  Integers
# throughout; pixel positions in 1/16 px, pixel i's value sitting at
# coordinate 16 i.  The names e, d, q, k, g are the loader's: e = 'big'
# and d = cm2 are used here, q and k (the alphabet and the line check)
# are not; the page's CRC-32 is the reader's own, crc32.
#
# A frame (R2-FORMAT "Decoding"): 1 binarise, 2 find the bullseyes by
# their comb, 4 pose from the bullseyes, 3 header and orientation, 5
# walk the blocks out from the bullseyes, 6 pool CRC-checked blocks.

# ---- the page (R2-FORMAT v1) ----------------------------------------
# Bullseye block, module (dx, dy) from its centre, q = dx*dx + dy*dy:
# rings for q <= 42, ink iff the integer nearest the root of q is even
# (the q listed here); white for 43..56; header for q >= 57.
INK_Q = (0, 4, 5, 13, 16, 17, 18, 20, 32, 34, 36, 37, 40, 41)
RING = [(dx, dy, dx * dx + dy * dy in INK_Q)
        for dy in range(-7, 8) for dx in range(-7, 8)
        if dx * dx + dy * dy < 57]
N_INK = sum(ink for dx, dy, ink in RING)
N_WHITE = len(RING) - N_INK
# the header modules in block raster order; bits 0-67 are the header
HEAD = [(dx, dy) for dy in range(-8, 8) for dx in range(-8, 8)
        if dx * dx + dy * dy > 56][:68]
# A block seen from its centre module (block-local (8, 8)): its 256
# data modules in raster order, and the 68 timing modules around them
# with the parity of dx + dy (the timing value alternates with it).
DATA = [(dx, dy) for dy in range(-8, 8) for dx in range(-8, 8)]
FRAME = [(dx, dy, (dx + dy) % 2) for dy in range(-9, 9)
         for dx in range(-9, 9) if dx in (-9, 8) or dy in (-9, 8)]
# bullseye blocks (block row, block column): the loupe path uses them,
# a photo is posed from the bullseyes it shows
BULLS = [(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)] + [
    (bi, bj) for bi in (8, 20) for bj in (5, 11, 17)]
TABLES = [bytes(int(x < t) for x in range(256)) for t in range(257)]


def crc32(t):
    # The page's one check (R2-FORMAT "CRC-32"): register ffffffff; for
    # each byte xor it in, then eight times shift right, xor edb88320
    # if the bit shifted out was 1; the CRC is the register xor
    # ffffffff.  Blocks, header and data are all checked with it.
    r = 2 ** 32 - 1
    for b in t:
        r ^= b
        for j in range(8):
            r = r >> 1 ^ 0xEDB88320 * (r & 1)
    return r ^ 2 ** 32 - 1


# ---- input -----------------------------------------------------------
def load(name):
    # P5 PGM -> (width, height, pixels); anything else is grid text
    # -> (0, 0, its lines)
    raw = open(name, 'rb').read()
    if raw[:2] == b'P5':
        f = raw[:64].split()
        w, h = int(f[1]), int(f[2])
        return w, h, raw[len(raw) - w * h:]
    return 0, 0, raw.split()


def sampler(img, w, h):
    # bilinear grey value at (x, y) in 1/16 px, clamped to the frame
    def value(x, y):
        x = min(max(x, 0), 16 * w - 17)
        y = min(max(y, 0), 16 * h - 17)
        i, fx, fy = (y >> 4) * w + (x >> 4), x & 15, y & 15
        top = img[i] * (16 - fx) + img[i + 1] * fx
        low = img[i + w] * (16 - fx) + img[i + w + 1] * fx
        return top * (16 - fy) + low * fy >> 8
    return value


# ---- 1. binarise -----------------------------------------------------
def binarise(img, w, h):
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
                out[y * w + x0:y * w + x1] = row.translate(TABLES[t])
    return bytes(out)


# ---- 2. bullseyes ----------------------------------------------------
KS = (-5, 5, -4, 4, -3, 3, -2, 2)


def combs(line):
    # The bullseye's signature along any line through its centre: 13
    # alternating runs, ink first and last, one module each, framed by
    # white runs of at least a quarter module.  Run centres (unlike run
    # edges) do not move with the threshold: the first and last ink
    # runs' centres are 12 modules apart, and the centres of the runs
    # for modules -5..-2 and 2..5 must sit on that grid within 0.3
    # module + 0.6 px.  The centre ink module, alone among whites, may
    # wash out under blur: then the middle is one 3-module white run.
    # -> [(4 x centre, 2 x the 12-module distance)], px along the line
    edge, x, v = [0], 0, line[0]
    while x >= 0:
        x = line.find(1 - v, x)
        if x > 0:
            edge.append(x)
            v = 1 - v
    edge.append(len(line))
    out = []
    for i in range(1 + line[0], len(edge) - 12, 2):
        for m in (2, 0):
            last = i + 10 + m
            if last + 2 < len(edge):
                c0 = edge[i] + edge[i + 1]
                span, j = edge[last] + edge[last + 1] - c0, 0
                if span < 24 or 96 * min(edge[i] - edge[i - 1], edge[
                        last + 2] - edge[last + 1]) < span:
                    j = 99
                while j < 8:
                    o = i + KS[j] + 6 - (KS[j] > 0) * (2 - m)
                    if abs(12 * (edge[o] + edge[o + 1] - c0) - (
                            KS[j] + 6) * span) > (3 * span + 144) // 10:
                        j = 99
                    j += 1
                if j == 8:
                    out.append((c0 + edge[last] + edge[last + 1] - 2,
                                span))
    return out


def ring_fit(value, x, y, p):
    # contrast of the ring template at centre (x, y) (1/16 px), pitch p
    # (1/256 px): proportional to mean white minus mean ink
    ink = white = 0
    for dx, dy, i in RING:
        if i:
            ink += value(x + (dx * p >> 4), y + (dy * p >> 4))
        else:
            white += value(x + (dx * p >> 4), y + (dy * p >> 4))
    return white * N_INK - ink * N_WHITE


def bullseyes(img, bits, w, h, value):
    # Every row is searched for the comb; a hit is confirmed by the
    # comb along the column through its middle (which gives the
    # centre's row), then by the ring pattern on the binarised frame
    # (75 % of its 177 modules); then centre and pitch are refined on
    # the grey image.  -> [(modules agreeing, x, y, pitch)] best
    # first; x, y in 1/16 px, the pitch in 1/256 px per module
    found = []
    for y in range(h):
        for c4, d2 in combs(bits[y * w:y * w + w]):
            x = c4 + 2 >> 2
            if [f for f in found if 16 * abs(f[1] - 4 * c4)
                    + 16 * abs(f[2] - 16 * y) < 6 * f[3]]:
                continue
            y0, y1 = max(0, y - d2 // 2 - 2), min(h, y + d2 // 2 + 3)
            col = [(abs(r4 - 4 * (y - y0)), r4, e2)
                   for r4, e2 in combs(bits[y0 * w + x:y1 * w:w])]
            if col == []:
                continue
            dist, r4, e2 = min(col)
            if 6 * dist > d2:
                continue
            cx, cy, p = 4 * c4, 4 * (r4 + 4 * y0), 16 * (d2 + e2) // 3
            if min(cx, cy) < p // 2 or cx > 16 * w - p // 2 - 32:
                continue
            if cy > 16 * h - p // 2 - 32:
                continue
            hit = sum(bits[(cy + (dy * p >> 4) + 8 >> 4) * w
                           + (cx + (dx * p >> 4) + 8 >> 4)] == i
                      for dx, dy, i in RING)
            if 4 * hit < 3 * len(RING):
                continue
            for st in (p // 64, p // 128, p // 256):
                f, cx, cy = max((ring_fit(value, a, b, p), a, b)
                                for a in (cx - st, cx, cx + st)
                                for b in (cy - st, cy, cy + st))
            for st in (p // 25, p // 50, p // 100):
                f, p = max((ring_fit(value, cx, cy, pp), pp)
                           for pp in (p - st, p, p + st))
            v = [(value(cx + (dx * p >> 4), cy + (dy * p >> 4)), i)
                 for dx, dy, i in RING]
            t = (sum(a for a, i in v if i) // N_INK
                 + sum(a for a, i in v if i == 0) // N_WHITE) // 2
            found.append((sum((a < t) == i for a, i in v), cx, cy, p))
    return sorted(found, reverse=True)


# ---- 4. pose ---------------------------------------------------------
# A pose P maps module (c, r), counted from a bullseye's centre, to
# (x, y) in 1/16 px: a 3 x 3 integer matrix, x = (P0 c + P1 r + P2) //
# (P6 c + P7 r + P8) and y likewise with P3, P4, P5.
def at(P, c, r):
    z = P[6] * c + P[7] * r + P[8]
    return ((P[0] * c + P[1] * r + P[2]) // z,
            (P[3] * c + P[4] * r + P[5]) // z)


def turned(P, n):
    # the pose for the page turned n quarter turns: P(-r, c), n times
    for i in range(n):
        P = [P[1], -P[0], P[2], P[4], -P[3], P[5], P[7], -P[6], P[8]]
    return P


def turn_back(u, n):
    # module (c, r) under a pose P -> the same module under turned(P, n)
    c, r = u[0], u[1]
    for i in range(n):
        c, r = r, -c
    return c, r


def det(m):
    # determinant by fraction-free elimination (Bareiss): exact
    m, sign, prev, n = [r[:] for r in m], 1, 1, len(m)
    for i in range(n - 1):
        j = i
        while m[j][i] == 0:
            j += 1
            if j == n:
                return 0
        if j > i:
            m[i], m[j], sign = m[j], m[i], -sign
        for j in range(i + 1, n):
            for c in range(i + 1, n):
                m[j][c] = (m[j][c] * m[i][i]
                           - m[j][i] * m[i][c]) // prev
        prev = m[i][i]
    return sign * m[n - 1][n - 1]


def solve(rows):
    # least squares through the normal equations, exactly (Cramer):
    # rows of (coefficients, value) -> (numerators, common denominator)
    n = len(rows[0][0])
    A = [[sum(a[i] * a[j] for a, z in rows) for j in range(n)]
         for i in range(n)]
    b = [sum(a[i] * z for a, z in rows) for i in range(n)]
    return [det([A[i][:j] + [b[i]] + A[i][j + 1:] for i in range(n)])
            for j in range(n)], det(A)


def fit(pts, p):
    # A pose from points [(c, r, x, y)]: one gives pitch and position
    # (rotation 0); two, or a row of them, a similarity; three an
    # affine map; four or more a homography -- unless its perspective
    # term reaches 15 % or it misses a point by a module, then affine.
    # p: the pitch in 1/256 px.  The result is scaled to P8 = 2**30.
    c0, r0, x0, y0 = pts[0]
    P = [p, 0, 16 * x0, 0, p, 16 * y0, 0, 0, 16]
    c1, r1 = pts[-1][0] - c0, pts[-1][1] - r0
    if len(pts) == 2 or len(pts) > 2 and sum(
            abs((c - c0) * r1 - (r - r0) * c1)
            for c, r, x, y in pts) == 0:
        s, D = solve([([c, -r, 1, 0], x) for c, r, x, y in pts]
                     + [([r, c, 0, 1], y) for c, r, x, y in pts])
        P = [s[0], -s[1], s[2], s[1], s[0], s[3], 0, 0, D]
    elif len(pts) > 2:
        s, D = solve([([c, r, 1, 0, 0, 0], x) for c, r, x, y in pts]
                     + [([0, 0, 0, c, r, 1], y) for c, r, x, y in pts])
        P = s[:6] + [0, 0, D]
    if len(pts) > 3:
        s, D = solve([([c, r, 1, 0, 0, 0, -c * x, -r * x], x)
                      for c, r, x, y in pts]
                     + [([0, 0, 0, c, r, 1, -c * y, -r * y], y)
                        for c, r, x, y in pts])
        if D and [1 for c, r, x, y in pts if 20 * abs(
                s[6] * c + s[7] * r) > 3 * abs(D)] == []:
            if [1 for c, r, x, y in pts if abs(at(s + [D], c, r)[0] - x)
                    + abs(at(s + [D], c, r)[1] - y) > p // 16] == []:
                P = s + [D]
    return [x * 2 ** 30 // P[8] for x in P]


def isqrt(n):
    # the integer square root (Newton)
    x, y = n, (n + 1) // 2
    while y < x:
        x, y = y, (y + n // y) // 2
    return x


def lattice(dc, dr):
    # the bullseye lattice vector nearest (dc, dr) in 1/16 module:
    # (column, row) = a (102, 0) + b (51, 102)
    b = (dr + 816) // 1632
    a = (dc - 816 * b + 816) // 1632
    return 102 * a + 51 * b, 102 * b


def poses(found):
    # Snap the pixel vector from an anchor to every other bullseye to
    # the lattice, in both quarter-turn classes (the lattice tells 0 or
    # 180 from 90 or 270 degrees, except for vectors like (204, 204)).
    # The anchor with most bullseyes on the lattice wins; its other
    # class is kept too if as good.  Modules are counted in the class's
    # own frame: there the page is upright or upside down.  Each
    # bullseye's own pitch then adds four points 8 modules from its
    # centre along the fitted axes, and the pose is fitted again: the
    # local scale under perspective, even for a row of bullseyes.
    # -> [(pose, [(c, r, x, y)] best first)]
    tries = []
    for A in found:
        for turn in (0, 1):
            pts, qs = [], []
            for B in found:
                vx, vy = B[1] - A[1], B[2] - A[2]
                if turn:
                    vx, vy = vy, -vx
                dc, dr = 256 * vx // A[3], 256 * vy // A[3]
                c, r = lattice(dc, dr)
                if 25 * ((dc - 16 * c) ** 2 + (dr - 16 * r) ** 2) <= (
                        256 * (c * c + r * r) + 57600):
                    pts.append((c, r, B[1], B[2]))
                    qs.append(B[3])
            tries.append((len(pts), A[0], A[1], A[2], turn, pts, qs))
    tries.sort(reverse=True)
    out = []
    for n, score, ax, ay, turn, pts, qs in tries[:2]:
        if (n, ax, ay) == tries[0][:1] + tries[0][2:4] and (
                out == [] or n > 1):
            P, more = fit(pts, qs[0]), []
            for i in range(n * (n > 1)):
                c, r, x, y = pts[i]
                X, Y = at(P, c, r)
                for dc, dr in ((8, 0), (-8, 0), (0, 8), (0, -8)):
                    U, V = at(P, c + dc, r + dr)
                    L = 2 * isqrt((U - X) ** 2 + (V - Y) ** 2)
                    more.append((c + dc, r + dr, x + (U - X) * qs[i]
                                 // L, y + (V - Y) * qs[i] // L))
            if more:
                P = fit(pts + more, qs[0])
            out.append((P, pts))
    return out


# ---- 3. header and orientation ---------------------------------------
def header(value, P, c, r):
    # The 68 header bits around the bullseye at module (c, r): the
    # threshold midway between its ink and white rings, the equaliser
    # at 4, 8 and 0 eighths of the Laplacian, Chase over the four least
    # reliable bits.  -> the six header bytes if the 20-bit check
    # (CRC-32 of the six bytes mod 2**20) passes, else None
    v = {}
    for dy in range(-9, 9):
        for dx in range(-9, 9):
            v[dx, dy] = value(*at(P, c + dx, r + dy))
    t = (sum(v[dx, dy] for dx, dy, i in RING if i) // N_INK + sum(
        v[dx, dy] for dx, dy, i in RING if i == 0) // N_WHITE) // 2
    for s8 in (4, 8, 0):
        lv = [t - v[x, y] + ((v[x - 1, y] + v[x + 1, y] + v[x, y - 1]
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


def tilt(value, P):
    # A lone bullseye gives no rotation.  Its block's 68 timing modules
    # do: the rotation by s/4096 radian (about 0.9 degree steps up to 9
    # degrees) and the quarter turn whose timing frame scores best
    # (either phase).  -> (the rotated pose, that quarter turn first)
    best = []
    for s in range(-640, 641, 64):
        a = 4096 - s * s // 8192
        Q = [P[0] * a + P[1] * s, P[1] * a - P[0] * s, 4096 * P[2],
             P[3] * a + P[4] * s, P[4] * a - P[3] * s, 4096 * P[5],
             P[6] * a + P[7] * s, P[7] * a - P[6] * s, 4096 * P[8]]
        for n in range(4):
            R = turned(Q, n)
            best.append((abs(sum(value(*at(R, dx, dy)) * (1 - 2 * par)
                                 for dx, dy, par in FRAME)), n, Q))
    f, n, Q = max(best)
    return Q, (n, n ^ 2, n ^ 1, n ^ 3)


def orient(value, cands):
    # Read the header around each bullseye, best first, in the quarter
    # turns its pose allows (one bullseye: any, after its tilt); the
    # first that checks fixes the page's orientation.  -> (header or
    # None, the pose turned upright, the bullseyes' modules (c, r)
    # under it); no header: the frame as it is
    for i in range(len(cands)):
        P, pts = cands[i]
        turns = (0, 2)
        if len(pts) == 1:
            P, turns = tilt(value, P)
            cands[i] = (P, pts)
        for u in pts:
            for n in turns:
                hd = header(value, turned(P, n), *turn_back(u, n))
                if hd:
                    return hd, turned(P, n), [turn_back(v, n)
                                              for v in pts]
    return None, cands[0][0], [turn_back(v, 0) for v in cands[0][1]]


# ---- 5. walk ---------------------------------------------------------
def walk(value, P, w, h, p, seeds, place, h6):
    # Breadth first from the bullseye blocks (seeds, not read).  A
    # block's place is the pose plus an offset predicted from the sound
    # neighbour that reached it (its offset plus the change from the
    # block behind it), refined on the 68 timing modules (3 x 3 search
    # at 1/2, 1/4, 1/8, 1/16 module).  The clock is sound when the
    # timing score reaches 60 % of the modules' total deviation from
    # their mean, or the block's CRC checks; only sound blocks are
    # walked through, and blocks that leave the frame are not read.
    # place: block -> centre (1/16 px) of every block accepted so far;
    # a placed block is not read again and hands its exact offset on.
    # h6: the payload's header bytes, against which blocks are checked.
    # -> (sound blocks whose CRC failed, newly accepted 32-byte blocks)
    off, todo, got, missed = {}, seeds[:], [], 0
    fixed, phase = {}, -1
    for b in seeds:
        off[b] = (0, 0)
    for bi, bj in todo:
        x0, y0 = at(P, 17 * bj, 17 * bi)
        x1, y1 = at(P, 17 * bj + 17, 17 * bi)
        x2, y2 = at(P, 17 * bj, 17 * bi + 17)
        ox, oy = off[bi, bj]
        if (bi, bj) in place:
            ox, oy = place[bi, bj][0] - x0, place[bi, bj][1] - y0

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
        if (bi, bj) not in place:
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
                w32 = read_block(value, spot, h6)
                if w32:
                    got.append(w32)
                    place[bi, bj] = spot(0, 0)
                    sound = 1
                missed += sound and w32 == b''
            if sound == 0:
                continue
        fixed[bi, bj] = (ox, oy)
        for di, dj in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            if (bi + di, bj + dj) not in off:
                bx, by = fixed.get((bi - di, bj - dj), (ox, oy))
                off[bi + di, bj + dj] = (2 * ox - bx, 2 * oy - by)
                todo.append((bi + di, bj + dj))
    return missed, got


def read_block(value, spot, h6):
    # Sample the block's 18 x 18 modules (timing frame included) at
    # their centres.  Threshold midway between the 9th darkest and the
    # 9th brightest of the 68 timing modules (34 ink, 34 white; a block
    # on the paper margin sharing one timing line with the page still
    # has 9 inks, so its data read white).  A block showing the rings
    # is an unseen bullseye.  Level and Laplacian per data module ->
    # block(); None if not tried
    v = {}
    for dy in range(-9, 9):
        for dx in range(-9, 9):
            v[dx, dy] = value(*spot(dx, dy))
    s = sorted(v[dx, dy] for dx, dy, i in FRAME)
    t = (s[8] + s[59]) // 2
    if 5 * sum((v[x, y] < t) == i for x, y, i in RING) > 4 * len(RING):
        return None
    return block([(t - v[x, y], v[x - 1, y] + v[x + 1, y] + v[x, y - 1]
                   + v[x, y + 1] - 4 * v[x, y]) for x, y in DATA], h6)


# ---- 6. a block ------------------------------------------------------
def block(soft, h6):
    # 256 (level, Laplacian) pairs, level > 0 = ink -> the 32 bytes
    # whose CRC-32 checks, else b'' (None: a white slot, not tried).
    # The CRC-32 is over the payload's six header bytes h6 followed by
    # the block's bytes 0-27, so a block validates only against its
    # own payload's header.  Equaliser at 8, 4 and 0 eighths of the
    # Laplacian; at each strength the plain read, Chase over the six
    # least reliable modules, and at 0 every single flip.
    if sum(a > 0 for a, b in soft) < 4:
        return None
    for s8 in (8, 4, 0):
        lv = [a + (b * s8 >> 3) for a, b in soft]
        base = int(''.join('01'[x > 0] for x in lv), 2)
        weak = sorted(range(256), key=lambda i: abs(lv[i]))[:6]
        flips = [sum(1 << 255 - weak[j] for j in range(6) if f >> j & 1)
                 for f in range(64)]
        if s8 == 0:
            flips = flips + [1 << i for i in range(256)]
        for f in flips:
            w32 = (base ^ f).to_bytes(32, e)
            if crc32(h6 + w32[:28]) == int.from_bytes(w32[28:], e):
                return w32
    return b''


# ---- the loupe path --------------------------------------------------
def cell(rows, bi, bj, dx, dy):
    # module (dx, dy) from the centre of block (bi, bj): ink 16, white
    # -16, unreadable 0
    z = rows[17 * bi + 9 + dy][17 * bj + 9 + dx]
    return 16 * ((z == 49) - (z == 48))


def read_grid(rows, known):
    # H lines of W modules in any quarter turn: the turn in which a
    # bullseye's header checks is used, else the grid as given.  Blocks
    # are checked against the payload's header (known, else the grid's
    # own); with no header there is nothing to check them against.
    # -> (header or None, 32-byte blocks)
    use, hd = rows, None
    for n in range(4):
        if len(rows) == 511 and len(rows[0]) == 358 and hd == None:
            for bi, bj in BULLS:
                x = int(''.join('01'[cell(rows, bi, bj, dx, dy) > 0]
                                for dx, dy in HEAD), 2)
                if hd == None and crc32((x >> 20).to_bytes(6, e)) % (
                        2 ** 20) == x % 2 ** 20:
                    use, hd = rows, (x >> 20).to_bytes(6, e)
        rows = [bytes(rows[len(rows) - 1 - i][c]
                      for i in range(len(rows)))
                for c in range(len(rows[0]))]
    got, h6 = [], known or hd
    for bi in range((len(use) - 1) // 17 * (h6 != None)):
        for bj in range((len(use[0]) - 1) // 17):
            if (bi, bj) not in BULLS:
                w32 = block([(cell(use, bi, bj, dx, dy), 0)
                             for dx, dy in DATA], h6)
                if w32:
                    got.append(w32)
    return hd, got


# ---- one frame -------------------------------------------------------
def read_frame(name, known):
    # known: the payload's header (the first one read in this run) or
    # None.  A block's CRC covers its payload's header, so a frame is
    # walked only once a header is known (from it or an earlier frame);
    # a frame of another payload reads its header but accepts nothing.
    # -> (32-byte blocks, header or None, a note for the progress line)
    w, h, img = load(name)
    if w == 0:
        hd, got = read_grid(img, known)
        return got, hd, 'grid'
    value = sampler(img, w, h)
    found = bullseyes(img, binarise(img, w, h), w, h, value)
    if found == []:
        return [], None, '0 bullseyes'
    hd, P, pts = orient(value, poses(found))
    h6 = known or hd
    if h6 == None:
        return [], None, '%d bullseyes' % len(found)
    seeds = [(r // 17, c // 17) for c, r in pts]
    # Up to three walks.  After each, the pose is refitted to the
    # centres of all blocks accepted so far (a homography through up
    # to hundreds of CRC-proven points), and the next walk reads only
    # the rest; no walk follows one that gained nothing or left no
    # sound block unread.
    got, place, p = [], {}, found[0][3]
    for i in range(3):
        missed, new = walk(value, P, w, h, p // 16, seeds, place, h6)
        got = got + new
        if new == [] or missed == 0 or len(place) < 8:
            break
        P = fit([(17 * c, 17 * r, x, y)
                 for (r, c), (x, y) in place.items()], p)
    return got, hd, '%d bullseyes, %d walks' % (len(found), i + 1)
# ======== main: one frame per line ========
# The payload's header is the first one read; blocks are checked against
# it, so frames of another payload add nothing.
chunks, head, done, need = {}, None, 0, '?'
# A name is stripped (a trailing space from drag and drop); a file that
# cannot be read or parsed is reported and skipped; the end of the input
# stops like an empty line.
while done == 0:
    try:
        name = input('R2 frame (P5 PGM or 0/1 grid, '
                     'empty line stops): ')
    except EOFError:
        break
    name = name.strip()
    if name == '':
        break
    try:
        got, hd, note = read_frame(name, head)
        note = note + ', header ' + ['unread', 'read'][hd != None]
    except Exception:
        got, hd, note = [], None, 'cannot read'
    for w32 in got:
        chunks[int.from_bytes(w32[:2], e)] = w32[2:28]
    head = head or hd
    if head:
        hd = head
        size = int.from_bytes(hd[:2], e)
        need = (size + 25) // 26
        if len([i for i in range(need) if i in chunks]) == need:
            data = b''.join(chunks[i] for i in range(need))[:size]
            done = crc32(data) == int.from_bytes(hd[2:], e)
    held = len([i for i in chunks if need == '?' or i < need])
    print(name + ':', note + ',', len(got), 'blocks accepted, chunks',
          held, '/', need, ['- more frames needed', '- done'][done])
if done:
    # N2 and B2 are print-time constants, the decompressed bundle's
    # length and CRC-32: the loader's encoder writes the numbers in
    # place of the names.  The primer is r.py's bytes; decode, check the
    # result against B2 (an r.py re-saved with other line ends or an
    # extra newline decodes to garbage), and only then write.
    out = d(int.from_bytes(data, e), N2, open('r.py', 'rb').read())
    assert crc32(out) == B2
    open('b.py', 'wb').write(out)
# END READER
