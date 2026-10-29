"""lzdict encoder (unconstrained, deterministic, stdlib only).

python3 enc.py IN OUT [--variant main|raw] [--greedy] [--passes K]
               [--depth D] [PRIMER ...]

main: the 20-line adaptive decoder in dec.py.  raw: the 15-line
no-entropy-coder decoder in dec_raw.py.  The window is PRIMER bytes + IN.

Match finding: for every position the Pareto list (shortest distance for
every reachable length) from a 1-byte / 2-byte nearest-occurrence table
plus a 3-byte hash chain searched D deep (most recent first).
Parsing: backward dynamic programming over that list.  For `raw` the code
lengths are static, so the DP is exactly optimal for the candidates.  For
`main` the DP carries the decoder's 3-state symbol context (previous token
start/literal/match) and prices every bit with -log2 of counts gathered by
the previous pass's real adaptive coder; K passes, the smallest output kept.
"""
import sys, math, time
from array import array

MAXLEN = 255          # decoder copies with (o[x:x+l]*l)[:l]: keep l small
SYMB = (0, 512, 1024)  # symbol tree base by previous token: start/lit/match
LITB = 1536            # literal tree base (value 256 + byte)
OFFB = 4096            # distance tree base; keys >= 4096 adapt with >> 5


def lcp(W, a, b, m):
    x = int.from_bytes(W[a:a + m], 'big') ^ int.from_bytes(W[b:b + m], 'big')
    return m if x == 0 else (m * 8 - x.bit_length()) >> 3


def find_matches(W, start, depth):
    """Flat Pareto lists L1,d1,L2,d2,... per position i >= start."""
    N = len(W)
    chains, last1, last2 = {}, {}, {}

    def insert(p):
        last1[W[p]] = p
        if p + 2 <= N:
            last2[W[p:p + 2]] = p
        if p + 3 <= N:
            chains.setdefault(W[p:p + 3], []).append(p)

    for p in range(start):
        insert(p)
    starts, flat = array('l', [0]), array('l')
    for i in range(start, N):
        m = min(MAXLEN, N - i)
        best = 0
        cands = []
        if W[i] in last1:
            cands.append(last1[W[i]])
        if m >= 2 and W[i:i + 2] in last2:
            cands.append(last2[W[i:i + 2]])
        if m >= 3:
            lst = chains.get(W[i:i + 3], ())
            cands += lst[-1:-depth - 1:-1]
        for p in cands:
            if W[p + best] == W[i + best]:
                L = lcp(W, p, i, m)
                if L > best:
                    flat.append(L)
                    flat.append(i - p)
                    best = L
                    if best == m:
                        break
        starts.append(len(flat))
        insert(i)
    return starts, flat


# ---------------------------------------------------------------- main model
def cctx(b, u):
    return b + u.bit_length()      # continuation bit: keyed by depth


def dctx(b, u):
    return b + 64 + u              # data bit: keyed by the tree node


class RC:
    """Mirror of the decoder: LZMA-style carry range coder."""

    def __init__(self):
        self.low, self.rng, self.cache, self.csize = 0, 1, 0, 1
        self.out = bytearray()
        self.P, self.n0, self.n1 = {}, {}, {}

    def shift(self):
        low = self.low
        if low < 0xFF000000 or low >= 1 << 32:
            carry, temp = low >> 32, self.cache
            while True:
                self.out.append((temp + carry) & 0xFF)
                temp = 0xFF
                self.csize -= 1
                if self.csize == 0:
                    break
            self.cache = (low >> 24) & 0xFF
        self.csize += 1
        self.low = (low & 0x00FFFFFF) << 8

    def bit(self, c, y):
        while self.rng < 1 << 24:
            self.rng <<= 8
            self.shift()
        p = self.P.setdefault(c, 2048)
        t = (self.rng >> 12) * p
        if y:
            self.low += t
            self.rng -= t
            self.n1[c] = self.n1.get(c, 0) + 1
        else:
            self.rng = t
            self.n0[c] = self.n0.get(c, 0) + 1
        self.P[c] = p + (((1 - y << 12) - p >> (4 + (c > 4095))) + y)

    def num(self, b, v):
        u = 1
        for j in range(v.bit_length() - 2, -1, -1):
            self.bit(cctx(b, u), 1)
            y = (v >> j) & 1
            self.bit(dctx(b, u), y)
            u = u * 2 + y
        self.bit(cctx(b, u), 0)

    def finish(self):
        lo, hi = self.low, self.low + self.rng
        for k in range(48, -1, -1):          # final value with most zeros
            V = ((lo + (1 << k) - 1) >> k) << k
            if V < hi:
                break
        self.low = V
        for _ in range(5):
            self.shift()
        out = self.out
        assert out[:5] == bytes(5)           # virtual cache byte + 32 zeros
        out = out[5:]
        s = 0
        while s < 8 and out and out[-1] == 0:   # decoder pads 8 zero bytes
            out = out[:-1]
            s += 1
        return bytes(out)


class Costs:
    def __init__(self, rc=None):
        if rc is None:
            self.f = lambda c, y: 1.0
        else:
            n0, n1 = rc.n0, rc.n1

            def f(c, y):
                a, b = n0.get(c, 0), n1.get(c, 0)
                return -math.log2(((b if y else a) + 0.4) / (a + b + 0.8))
            self.f = f
        self.symtab, self.offc = {}, {}

    def numcost(self, b, v):
        f, u, s = self.f, 1, 0.0
        for j in range(v.bit_length() - 2, -1, -1):
            s += f(cctx(b, u), 1)
            y = (v >> j) & 1
            s += f(dctx(b, u), y)
            u = u * 2 + y
        return s + f(cctx(b, u), 0)

    def sym(self, b):
        t = self.symtab.get(b)
        if t is None:
            t = self.symtab[b] = [0.0] + [self.numcost(b, v) for v in range(1, 512)]
        return t

    def off(self, d):
        x = self.offc.get(d)
        if x is None:
            x = self.offc[d] = self.numcost(OFFB, d)
        return x


def encode_main(W, start, toks):
    rc = RC()
    i, prev = start, 0
    for l, d in toks:
        rc.num(SYMB[min(prev, 2)], l)
        if d == 0:
            rc.num(LITB, 256 + W[i])
        else:
            rc.num(OFFB, d)
        i += l
        prev = l
    assert i == len(W)
    return rc.finish(), rc


def parse_main(W, start, starts, flat, costs, allcut=48):
    N = len(W)
    cost = [[0.0] * (N + 1) for _ in range(3)]
    ch = [[None] * (N + 1) for _ in range(3)]
    lit = costs.sym(LITB)
    sts = [costs.sym(b) for b in SYMB]
    for i in range(N - 1, start - 1, -1):
        a, e = starts[i - start], starts[i - start + 1]
        litnext = lit[256 + W[i]] + cost[1][i + 1]
        mlist = []
        prevL = 1
        for q in range(a, e, 2):
            L, d = flat[q], flat[q + 1]
            if L <= prevL:
                continue
            oc = costs.off(d)
            if L <= allcut:
                ls = range(prevL + 1, L + 1)
            else:  # long match: short lengths and the full one only
                ls = list(range(prevL + 1, min(L, allcut) + 1)) + [L]
            for l in ls:
                mlist.append((l, oc + cost[2][i + l], d))
            prevL = L
        for st in range(3):
            sy = sts[st]
            best, bc = sy[1] + litnext, (1, 0)
            for l, rest, d in mlist:
                v = sy[l] + rest
                if v < best:
                    best, bc = v, (l, d)
            cost[st][i] = best
            ch[st][i] = bc
    toks, i, st = [], start, 0
    while i < N:
        l, d = ch[st][i]
        toks.append((l, d))
        i += l
        st = min(l, 2)
    return toks


def greedy_parse(W, start, starts, flat, minlen=3):
    toks, i, N = [], start, len(W)
    while i < N:
        a, e = starts[i - start], starts[i - start + 1]
        if e > a and flat[e - 2] >= minlen:
            toks.append((flat[e - 2], flat[e - 1]))
            i += flat[e - 2]
        else:
            toks.append((1, 0))
            i += 1
    return toks


# ----------------------------------------------------------------- raw model
RAWK = 9   # Exp-Golomb order of the distance in dec_raw.py


def glen(v):
    return 2 * v.bit_length() - 1


def rawoff(d):
    return glen((d - 1 + (1 << RAWK)) >> RAWK) + RAWK


def put_gamma_k(bits, v, k, prefix=True):
    hi = v >> k
    if prefix:
        for j in range(hi.bit_length() - 2, -1, -1):
            bits.append(1)
            bits.append((hi >> j) & 1)
        bits.append(0)
    for j in range(k - 1, -1, -1):
        bits.append((v >> j) & 1)


def parse_raw(W, start, starts, flat):
    N = len(W)
    cost = [0] * (N + 1)
    ch = [None] * (N + 1)
    for i in range(N - 1, start - 1, -1):
        best, bc = 9 + cost[i + 1], (1, 0)
        a, e = starts[i - start], starts[i - start + 1]
        prevL = 1
        for q in range(a, e, 2):
            L, d = flat[q], flat[q + 1]
            oc = rawoff(d)
            for l in range(prevL + 1, L + 1):
                v = glen(l) + oc + cost[i + l]
                if v < best:
                    best, bc = v, (l, d)
            prevL = max(prevL, L)
        cost[i], ch[i] = best, bc
    toks, i = [], start
    while i < N:
        toks.append(ch[i])
        i += ch[i][0]
    return toks


def encode_raw(W, start, toks):
    bits, i = [], start
    for l, d in toks:
        put_gamma_k(bits, l, 0)
        if d == 0:
            put_gamma_k(bits, 256 + W[i], 8, prefix=False)
        else:
            put_gamma_k(bits, d - 1 + (1 << RAWK), RAWK)
        i += l
    bits += [0] * (-len(bits) % 8)
    out = bytearray()
    for j in range(0, len(bits), 8):
        b = 0
        for q in bits[j:j + 8]:
            b = b * 2 + q
        out.append(b)
    return bytes(out)


def compress(data, primer, variant='main', greedy=False, passes=12, depth=128,
             log=None):
    W = primer + data
    start = len(primer)
    starts, flat = find_matches(W, start, depth)
    if variant == 'raw':
        toks = greedy_parse(W, start, starts, flat) if greedy else \
            parse_raw(W, start, starts, flat)
        return encode_raw(W, start, toks)
    if greedy:
        return encode_main(W, start, greedy_parse(W, start, starts, flat))[0]
    costs, best = Costs(), None
    for k in range(passes):
        out, rc = encode_main(W, start, parse_main(W, start, starts, flat, costs))
        if log:
            log('pass %d: %d bytes' % (k, len(out)))
        if best is None or len(out) < len(best):
            best = out
        costs = Costs(rc)
    return best


def main():
    args = sys.argv[1:]
    kw, rest = {}, []
    while args:
        a = args.pop(0)
        if a == '--variant':
            kw['variant'] = args.pop(0)
        elif a == '--greedy':
            kw['greedy'] = True
        elif a == '--passes':
            kw['passes'] = int(args.pop(0))
        elif a == '--depth':
            kw['depth'] = int(args.pop(0))
        else:
            rest.append(a)
    primer = b''.join(open(f, 'rb').read() for f in rest[2:])
    data = open(rest[0], 'rb').read()
    t0 = time.time()
    out = compress(data, primer, log=lambda s: print(s, file=sys.stderr), **kw)
    open(rest[1], 'wb').write(out)
    print('total %.1fs size %d' % (time.time() - t0, len(out)), file=sys.stderr)


if __name__ == '__main__':
    main()
