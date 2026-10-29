"""crk_enc.py -- Crinkler's compressor side transliterated to Python: the
4k and 1k coders, the 4k model search (ApproximateModels4k with
OptimizeWeights), the hash-size search (OptimizeHashsize), and the 1k model
search (ApproximateModels1k).  The exact mirror of crk_dec.py.

ALTERED VERSION.  This is not Crinkler.  A Python transliteration, made
2026-10-20 for the paper-store bootstrap study, of source/Compressor/*.cpp
of Crinkler (https://github.com/runestubbe/Crinkler), Copyright (c)
2005-2026 Aske Simon Christensen and Rune L. H. Stubbe, zlib licence (text
in this directory's README).  Altered: Python instead of C++/SSE; the
estimator's float32 polynomial log2 (CompressionStateEvaluator.cpp:150-160)
is replaced by numpy float64 log2; no parallelism; an optional primer
(EXTENSION, trains the model before the data); our own container (see
crk_dec.parse); for large inputs the search may run on a prefix (sample)
and the hash-size search may use fewer tries -- every caller says so.

Pointers (Crinkler source tree):
  coder        Compressor/AritCode.cpp:5-90           -> Enc
  4k model     Compressor/CompressionStream.cpp:31-167 -> compress4k
  model list   Compressor/ModelList.cpp:64-117         -> mask_list, models_of
  estimator    Compressor/CompressionState.cpp:26-149,
               CompressionStateEvaluator.cpp:27-205    -> State
  search       Compressor/Compressor.cpp:64-274         -> approximate4k
  hash tries   Crinkler/Crinkler.cpp:293-358            -> optimize_hashsize
  1k           Compressor/Compressor.cpp:276-840        -> model_data1k,
                                                           evaluate1k,
                                                           approximate1k,
                                                           compress1k
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crk_dec as D  # noqa: E402

MAX_N_MODELS = 21          # Compressor.cpp:14
MAX_MODEL_WEIGHT = 9       # Compressor.cpp:15
BASEPROB = 10              # Compressor.h:10 DEFAULT_BASEPROB
INSTANT = [(0x00, 0), (0x80, 2), (0x40, 1), (0xC0, 3), (0x20, 0), (0xA0, 2),
           (0x60, 2), (0x90, 2), (0xFF, 7), (0x51, 2), (0xB0, 3)]   # Compressor.cpp:147-162


def parity8(n):
    return bin(n & 255).count('1') & 1


def mask_list(models, terminate=True):
    """ModelList4k::GetMaskList: models = [(mask, weight)] -> (mask bytes
    sorted by weight, 32-bit weight mask)."""
    wm, left, biti, out = 0, len(models), 31, []
    w = 0
    while left:
        for mk, wt in models:
            if wt == w:
                out.append(mk)
                left -= 1
                biti -= 1
        wm |= 1 << biti
        biti -= 1
        w += 1
    while biti >= 0:
        wm |= 1 << biti
        biti -= 1
    return bytes(out), wm & ((-2 + (int(terminate) ^ parity8(wm))) & 0xFFFFFFFF)


def models_of(wm, masks):
    """ModelList4k::SetFromModelsAndMask: -> [(mask, weight)]."""
    ws, _ = D.weights_of(wm)
    return [(masks[i], w) for i, (w, _) in enumerate(ws)]


class Enc:
    """AritCode.cpp: interval_min/size 32 bit, bits written LSB-first per
    byte at dest_bit - 1, carries propagated towards bit 0."""

    def __init__(self):
        self.buf, self.dest, self.size, self.lo = bytearray(), -1, 0x80000000, 0

    def _put(self, d):
        b = self.buf
        while True:
            d -= 1
            if d < 0:
                return
            if d >> 3 >= len(b):
                b.extend(bytes((d >> 3) - len(b) + 1))
            m = 1 << (d & 7)
            v = b[d >> 3]
            b[d >> 3] = v ^ m
            if not v & m:
                return

    def code(self, zero_prob, one_prob, bit):
        """AritCode(state, zero_prob, one_prob, bit) exactly; Crinkler calls it
        with (p1, p0, 1 - y)."""
        size, lo = self.size, self.lo
        t = size * zero_prob // (zero_prob + one_prob)
        if bit:
            old = lo
            lo = (lo + t) & 0xFFFFFFFF
            if lo < old:
                self._put(self.dest)
            size -= t
        else:
            size = t
        while size < 0x80000000:
            self.dest += 1
            if lo & 0x80000000:
                self._put(self.dest)
            lo = lo << 1 & 0xFFFFFFFF
            size <<= 1
        self.size, self.lo = size, lo

    def end(self):
        d, lo, size = self.dest, self.lo, self.size
        if lo > 0:
            if (lo + size - 1) & 0xFFFFFFFF >= lo:
                d += 1
            self._put(d)
        nbytes = (d + 7) // 8 if d >= 0 else 0
        out = bytes(self.buf[:nbytes])
        return out + bytes(nbytes - len(out))


def compress4k(parts, hn, saturate=False, primer=b'', baseprob=BASEPROB):
    """parts = [(data bytes, [(mask, weight)])] -> packed bytes.  Mirrors
    crk_dec.unpack4k bit for bit (ComputeHashBits + CompressFromHashBits;
    the tiny hash table there is keyed by h % HN, so it is this table)."""
    enc = Enc()
    tab = bytearray(2 * hn)
    hist = bytearray(8)
    first = True
    for pi, (data, models) in enumerate(parts):
        masks, wm = mask_list(models, pi + 1 == len(parts))
        ws, _ = D.weights_of(wm)
        mods = [(w, hi | masks[i], masks[i]) for i, (w, hi) in enumerate(ws)]
        tab[:] = bytes(2 * hn)
        todo = []
        if first:
            todo.append((None, 1))
            todo += [(b, 0) for b in primer]
        first = False
        todo += [(b, 2) for b in data]
        CRC = D.CRC
        for byte, kind in todo:
            u = 0 if kind == 1 else 1
            for j in range(1 if kind == 1 else 8):
                p0 = p1 = baseprob
                slots = []
                for w, h0, mk in mods:
                    h = CRC[(h0 ^ u) & 255] ^ h0 >> 8
                    k = len(hist)
                    while mk:
                        k -= 1
                        if mk & 128:
                            h = CRC[(h ^ hist[k]) & 255] ^ h >> 8
                        mk = mk << 1 & 255
                    s = h % hn * 2
                    slots.append(s)
                    c0, c1 = tab[s], tab[s + 1]
                    sh = w + 2 if not c0 or not c1 else w
                    p0 += c0 << sh
                    p1 += c1 << sh
                y = 1 if kind == 1 else byte >> 7 - j & 1
                if kind != 0:
                    enc.code(p1, p0, 1 - y)
                for s in slots:
                    o = s + 1 - y
                    if tab[o] > 1:
                        tab[o] >>= 1
                    v = tab[s + y] + 1
                    tab[s + y] = 255 if v > 255 and saturate else v & 255
                u = u << 1 | y
            if kind != 1:
                hist.append(u & 255)
                if len(hist) > 64:
                    del hist[:-8]
    return enc.end(), [mask_list(m, i + 1 == len(parts)) for i, (_, m) in enumerate(parts)]


def previous_prime(n):
    """CompressionState.cpp:17-24 / Crinkler.cpp:32-39."""
    while True:
        n = (n - 2) | 1
        i = 3
        ok = True
        while i * i < n:
            if n // i * i == n:
                ok = False
                break
            i += 2
        if ok:
            return n


def default_hashsize(mb=500):
    """Crinkler.cpp:1079: best_hashsize = PreviousPrime(HASHSIZE/2) * 2 bytes,
    HASHSIZE = 500 MB by default (main.cpp:223-224)."""
    return previous_prime(mb * 1024 * 1024 // 2) * 2


def optimize_hashsize(parts, hashsize, tries, saturate=False, primer=b''):
    """Crinkler.cpp:293-358: compress with `tries` successively smaller
    prime-pair sizes, keep the smallest output (ties -> the later size)."""
    best, best_hs = None, hashsize
    sizes = []
    for _ in range(tries):
        hashsize = previous_prime(hashsize // 2) * 2
        z, _ = compress4k(parts, hashsize // 2, saturate, primer)
        sizes.append((hashsize, len(z)))
        if best is None or len(z) <= best:
            best, best_hs = len(z), hashsize
    return best_hs, sizes


# --- the estimator: CompressionState + CompressionStateEvaluator ---------

def window_ints(buf):
    """W[i] = the 8 bytes before position i as one integer, 1 back in the
    low byte (positions before the start read 0)."""
    W, w = [], 0
    for b in buf:
        W.append(w)
        w = (w << 8 | b) & 0xFFFFFFFFFFFFFFFF
    return W


def expand(mask8):
    """Crinkler mask byte (bit 7 = 1 back) -> integer mask over W."""
    return sum(255 << 8 * k for k in range(8) if mask8 >> (7 - k) & 1)


def apply_model(buf, W, m0, M, saturate):
    """CompressionState::ApplyModel for one mask over buf[m0:] (buf[:m0] =
    primer, trains only): exact contexts (FindEntry compares everything),
    boost << 2.  Returns (right, total) per coded bit (float32, exact)."""
    t = {}
    r, tt = [], []
    lim = 255 if saturate else 256
    for i, b in enumerate(buf):
        base = (W[i] & M) << 9
        u = 1
        for j in range(8):
            y = b >> 7 - j & 1
            e = t.get(base | u)
            if e is None:
                e = t[base | u] = [0, 0]
            c0, c1 = e
            if i >= m0:
                bo = 2 if not c0 or not c1 else 0
                r.append((c1 if y else c0) << bo)
                tt.append((c0 + c1) << bo)
            if y:
                v = c1 + 1
                e[1] = v if v < 256 else (255 if lim == 255 else 0)
                if c0 > 1:
                    e[0] = c0 >> 1
            else:
                v = c0 + 1
                e[0] = v if v < 256 else (255 if lim == 255 else 0)
                if c1 > 1:
                    e[1] = c1 >> 1
            u = u << 1 | y
    return np.array(r, dtype=np.float32), np.array(tt, dtype=np.float32)


class State:
    """CompressionState + CompressionStateEvaluator: predictions of all 256
    masks once, then the size of any (mask, weight) set, incrementally.
    Units: 1/256 bit (BIT_PRECISION), model cost 6*8 + 8 per model bits."""

    def __init__(self, data, primer=b'', baseprob=BASEPROB, saturate=False, masks=range(256),
                 threads=1):
        buf = bytes(primer) + bytes(data)
        W = window_ints(buf)
        m0 = len(primer)
        self.n = 8 * len(data)
        self.pred = {}
        jobs = list(masks)
        if threads > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(threads) as ex:
                res = list(ex.map(lambda mk: apply_model(buf, W, m0, expand(mk), saturate), jobs))
        else:
            res = [apply_model(buf, W, m0, expand(mk), saturate) for mk in jobs]
        for mk, rt in zip(jobs, res):
            self.pred[mk] = rt
        self.base = baseprob
        self.R = np.full(self.n, float(baseprob))
        self.T = np.full(self.n, 2.0 * baseprob)
        self.w = {}
        self.evals = 0

    def size(self, models):
        new = {mk: 1 << wt for mk, wt in models}
        for mk in sorted(set(new) | set(self.w)):
            d = new.get(mk, 0) - self.w.get(mk, 0)
            if d:
                r, t = self.pred[mk]
                self.R += d * r
                self.T += d * t
        self.w = new
        self.evals += 1
        bits = float(np.log2(self.T / self.R).sum()) + 6 * 8 + 8 * len(new)
        return int(bits * 256)


def approximate_weights(cs, models):
    """Compressor.cpp:64-75: weight = number of bytes in the mask."""
    models[:] = [(mk, bin(mk).count('1')) for mk, _ in models]
    return cs.size(models)


def optimize_weights(cs, models):
    """Compressor.cpp:77-131, coordinate search over the weights, in place."""
    index = len(models) - 1
    d = 1
    last = index
    best = approximate_weights(cs, models)
    if not models:
        return best
    while True:
        skip = False
        new = list(models)
        mk, wt = new[index]
        wt = (wt + d) & 255                 # unsigned char
        if wt > MAX_MODEL_WEIGHT:
            wt, skip = MAX_MODEL_WEIGHT, True
        if wt == 255:
            wt, skip = 0, True
        new[index] = (mk, wt)
        size = None if skip else cs.size(new)
        if not skip and size < best:
            best = size
            models[:] = new
            last = index
        else:
            if d == 1 and models[index][1] > 0:
                d = -1
            else:
                d = 1
                index -= 1
                if index == -1:
                    index = len(models) - 1
                if index == last:
                    break
    return best


def try_weights(cs, models, mode):
    return approximate_weights(cs, models) if mode == 'fast' else optimize_weights(cs, models)


def approximate4k(cs, mode='slow', progress=None):
    """Compressor.cpp:164-274 ApproximateModels4k: masks tried in bit-reversed
    order of 0..255; each candidate set = the set + the new mask, weights
    re-optimised, then every older model tried for removal; width 1 (SLOW,
    FAST) or 3 (VERYSLOW) best sets kept, the ELITE flag keeps the best
    lineage alive.  Returns ([(mask, weight)], size in 1/256 bit)."""
    if mode == 'instant':
        m = list(INSTANT)
        return m, cs.size(m)
    if cs.n == 0:
        return [(0, 0)], 0
    width = 3 if mode == 'veryslow' else 1
    INT_MAX = 2 ** 31 - 1
    ELITE = 1 << 40                          # stands for INT_MIN's sign bit
    sets = [[[], INT_MAX] for _ in range(2 * width)]
    sets[0] = [[], cs.size([]) | ELITE]
    for s in range(1, width):
        sets[s][1] = INT_MAX
    rev = [int('{:08b}'.format(m)[::-1], 2) for m in range(256)]
    for maski in range(256):
        mask = rev[maski]
        for s in range(width):
            models, msize = sets[s]
            sets[width + s] = [[], INT_MAX]
            if msize == INT_MAX:
                continue
            used = any(mk == mask for mk, _ in models)
            if not used and len(models) < MAX_N_MODELS:
                new = list(models) + [(mask, 0)]
                old_size = msize & ~ELITE
                new_size = try_weights(cs, new, mode)
                if new_size < old_size or mode == 'veryslow':
                    best = new_size
                    m = len(new) - 2
                    while m >= 0:
                        rmod = new[m]
                        cand = list(new)
                        cand[m] = cand[-1]
                        cand.pop()
                        size = try_weights(cs, cand, mode)   # re-weights cand in place
                        if size < best:
                            best = size
                            new = cand
                        else:
                            # C++ restores only the removed model: the others
                            # keep the weights the trial gave them
                            new = cand[:m] + [rmod] + cand[m + 1:] + [new[-1]]
                        m -= 1
                    nsize = best
                    if msize & ELITE and new_size < old_size:
                        sets[s][1] = msize & ~ELITE
                        nsize |= ELITE
                    sets[width + s] = [new, nsize]
        # std::stable_sort on the signed int: an ELITE size is negative
        sets.sort(key=lambda e: e[1] - 2 * ELITE if e[1] & ELITE else e[1])
        if progress:
            progress(maski + 1, cs.evals, sets[0])
    sets[0][1] &= ~ELITE
    sets.sort(key=lambda e: e[1] - 2 * ELITE if e[1] & ELITE else e[1])
    models = list(sets[0][0])
    if not models:
        models = [(0, 0)]
    size = optimize_weights(cs, models)
    return models, size


# --- 1k ------------------------------------------------------------------

def model_data1k(data, primer=b''):
    """GenerateModelData1k (Compressor.cpp:276-408) for all 33 models:
    (right, wrong) counts before the update, per coded bit."""
    buf = bytes(33) + bytes(primer) + bytes(data)
    m0 = 33 + len(primer)
    n = 8 * len(data)
    R = np.zeros((33, n), dtype=np.int64)
    Wr = np.zeros((33, n), dtype=np.int64)
    for k in range(33):
        mk = (k - 1) & 255
        t = {}
        rr, ww = [], []
        for p in range(32, len(buf)):          # p = 32 is byte position -1
            ctx = bytes(buf[p - 1 - i] if mk >> i & 1 else 0 for i in range(8))
            b = buf[p]
            cur = 0
            for j in range(8):
                y = b >> 7 - j & 1
                e = t.get((j, cur, ctx))
                if e is None:
                    e = t[(j, cur, ctx)] = [0, 0]
                if p >= m0:
                    rr.append(e[y])
                    ww.append(e[1 - y])
                e[y], e[1 - y] = e[y] + 1, e[1 - y] + 1 >> 1
                cur = cur << 1 | y
        R[k], Wr[k] = rr, ww
    bits = np.unpackbits(np.frombuffer(bytes(data), dtype=np.uint8)).astype(np.int64)
    return R, Wr, bits


def evaluate1k(md, modelmask):
    """Evaluate1K (Compressor.cpp:651-736): the best (boost 4..10, b0, b1
    4..8) for a model mask.  Returns (size in 1/256 bit, b0, b1, boost)."""
    R, Wr, bits = md
    sel = [32] + [k for k in range(32) if modelmask >> k & 1]
    rb = np.zeros(R.shape[1])
    rn, wb, wn = rb.copy(), rb.copy(), rb.copy()
    for k in sel:
        z = (R[k] * Wr[k]) == 0
        rb += np.where(z, R[k], 0)
        wb += np.where(z, Wr[k], 0)
        rn += np.where(z, 0, R[k])
        wn += np.where(z, 0, Wr[k])
    best = None
    for boost in range(4, 11):
        tr = rn + rb * boost
        tw = wn + wb * boost
        for b1 in range(4, 9):
            for b0 in range(4, 9):
                right = tr + np.where(bits == 1, b0, b1)
                wrong = tw + np.where(bits == 1, b1, b0)
                s = int(float(np.log2((right + wrong) / right).sum()) * 256)
                if best is None or s < best[0]:
                    best = (s, b0, b1, boost)
    return best


def approximate1k(md, progress=None):
    """ApproximateModels1k (Compressor.cpp:738-840): from all 32 optional
    models on, greedily switch off the one whose removal helps most."""
    best_size, best_mask, best = 2 ** 62, 0xFFFFFFFF, None
    nm = 32
    for tries in range(32):
        prev = best_mask
        flip = -1
        setbits = [k for k in range(32) if prev >> k & 1]
        for i in range(nm):
            mm = prev ^ (1 << setbits[i])
            r = evaluate1k(md, mm)
            if r[0] < best_size:
                best_size, best_mask, best, flip = r[0], mm, r, i
        nm -= 1
        if progress:
            progress(tries, best)
        if flip == -1:
            break
    return best_mask, best


def compress1k(data, modelmask, boost, b0, b1, primer=b''):
    """Compress1k (Compressor.cpp:487-649), exact contexts."""
    ms = [(k - 1) & 255 for k in range(33) if k == 32 or modelmask >> k & 1]
    tabs = [{} for _ in ms]
    buf = bytes(33) + bytes(primer) + bytes(data)
    m0 = 33 + len(primer)
    enc = Enc()
    for p in range(32, len(buf)):
        ctxs = [bytes(buf[p - 1 - i] if mk >> i & 1 else 0 for i in range(8)) for mk in ms]
        b = buf[p]
        cur = 0
        for j in range(8):
            y = b >> 7 - j & 1
            n0 = n1 = 0
            for c, t in zip(ctxs, tabs):
                e = t.get((j, cur, c))
                if e is None:
                    t[(j, cur, c)] = [1 - y, y]
                else:
                    f = boost if not e[0] or not e[1] else 1
                    n0 += e[0] * f
                    n1 += e[1] * f
                    e[y], e[1 - y] = e[y] + 1, e[1 - y] + 1 >> 1
            if p >= m0:
                enc.code(n1 + b0, n0 + b1, 1 - y)
            cur = cur << 1 | y
    return enc.end()


# --- containers -------------------------------------------------------------

def container4k(z, hn, parts_ml, sizes, saturate=False):
    c = b'C4' + hn.to_bytes(4, 'big') + bytes([int(saturate), len(sizes)])
    for n, (masks, wm) in zip(sizes, parts_ml):
        c += n.to_bytes(4, 'big') + wm.to_bytes(4, 'big') + masks
    return c + z


def container1k(z, n, mm, boost, b0, b1):
    return b'C1' + n.to_bytes(4, 'big') + mm.to_bytes(4, 'big') + bytes([boost, b0, b1]) + z


def enc4k(data, primer=b'', mode='slow', hashtries=100, hashmb=500, saturate=False,
          sample=None, threads=1, log=None):
    """Crinkler's 4k pipeline on one part: model search (on data[:sample]
    if sample is given -- a SIMPLIFICATION for large inputs), hash-size
    search, compression.  Returns (container, info)."""
    est = data if sample is None else data[:sample]
    cs = State(est, primer, BASEPROB, saturate, threads=threads)
    models, est_size = approximate4k(cs, mode)
    hs = default_hashsize(hashmb)
    sizes = []
    if hashtries:
        hs, sizes = optimize_hashsize([(data, models)], hs, hashtries, saturate, primer)
    z, ml = compress4k([(data, models)], hs // 2, saturate, primer)
    info = {'models': models, 'estimate_bytes': est_size / 2048, 'hashsize': hs,
            'evals': cs.evals, 'hashtries': len(sizes), 'packed': len(z)}
    return container4k(z, hs // 2, ml, [len(data)], saturate), info


def enc1k(data, primer=b''):
    md = model_data1k(data, primer)
    mm, (s, b0, b1, boost) = approximate1k(md)
    z = compress1k(data, mm, boost, b0, b1, primer)
    return container1k(z, len(data), mm, boost, b0, b1), {
        'modelmask': mm, 'boost': boost, 'b0': b0, 'b1': b1, 'estimate_bytes': s / 2048,
        'packed': len(z)}


if __name__ == '__main__':
    a = sys.argv[1:]
    data = open(a[0], 'rb').read()
    c, info = enc4k(data)
    open(a[1], 'wb').write(c)
    print(info, math.ceil(len(c)))
