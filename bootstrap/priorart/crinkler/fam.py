"""fam.py -- the Crinkler family, made for Python, and its hybrids with cm2.

Contains an ALTERED VERSION of Crinkler's model search (ApproximateModels4k
and OptimizeWeights, source/Compressor/Compressor.cpp:77-274; Crinkler (c)
2005-2026 Aske Simon Christensen and Rune L. H. Stubbe, zlib licence, text
in this directory's README): generalised to any candidate list, any weight
range and an objective that charges the parameters' typed text.

One model, five knobs.  For every bit, every model k has a context mask M_k
(an integer over the history h = all earlier bytes as one big-endian integer,
the byte 1 back in the low 8 bits) and a weight w_k; its counter pair sits in
ONE dict under the key (h & M_k, u), u = the bits of the current byte so far
behind a leading 1 (cm2's key: two masks whose values coincide share a pair).
  p_y = BASE + sum_k c_y << (w_k + BOOST * [c_other == 0])
  after the bit: c_y += 1, c_other = RULE(c_other)
  RULE  'crk'  c >> 1 if c > 1           (Crinkler 4k, CounterState.cpp:12-23)
        'crksat'  the same with c_y saturating at 255 (/SATURATE; search
               estimator only, predict(); added after the refuter's round)
        'k1'   (c + 1) >> 1               (Crinkler 1k, Compressor.cpp:592)
        'cm2'  min(c, c // 4 + 2)         (cm2 v2)
  BOOST 2 = Crinkler (x4), 1 = cm2 (x2); BASE 10 = Crinkler 4k, 1 = cm2.
  Counters unbounded (Crinkler's 8-bit wrap is an artefact of its table).
The coder is cm2 v2's big-integer rANS (bit 0 owns [0, p0)), so a model's
cost is exactly what the typed currency pays.

cm2 v2 itself is the member masks = 256**o - 1 for o in (0,1,2,3,4,6,8,12,16),
w_k = k, BOOST 1, BASE 1, RULE cm2.  Crinkler-as-Python is masks = any of
the 256 subsets of the last 8 bytes, searched weights 0..9, BOOST 2, BASE 10,
RULE crk.

API
  predict(buf, m0, M, rule)        per coded bit: (right count, wrong count)
  Fam(data, primer, cands, rule)   predictions of every candidate mask once
     .bits(models, boost, base)    exact model cost in bits (no key sharing)
  search(fam, ...)                 Crinkler's greedy (ApproximateModels4k +
                                   OptimizeWeights) over any candidate list,
                                   objective = bits + parameter text in bits
  model_ref(...), encode_int(...), decode(...)   the exact coder (with sharing)
"""
import math

import numpy as np


def rule_fn(rule):
    return {'crk': lambda c: c >> 1 if c > 1 else c,
            'k1': lambda c: c + 1 >> 1,
            'cm2': lambda c: min(c, c // 4 + 2)}[rule]


def predict(buf, m0, M, rule):
    """(right, wrong) counts per coded bit of buf[m0:] for mask M (separate
    dict: no sharing with other masks)."""
    t = {}
    r, e = [], []
    h = 0
    top = (M.bit_length() + 7) // 8
    lim = 256 ** max(top, 1)
    if rule in ('crk', 'crksat'):
        cap = 255 if rule == 'crksat' else 1 << 62
        for i, b in enumerate(buf):
            base = h & M
            u = 1
            for j in range(8):
                y = b >> 7 - j & 1
                k = (base, u)
                c = t.get(k)
                if c is None:
                    c = t[k] = [0, 0]
                if i >= m0:
                    r.append(c[y])
                    e.append(c[1 - y])
                if c[y] < cap:
                    c[y] += 1
                o = c[1 - y]
                if o > 1:
                    c[1 - y] = o >> 1
                u = u << 1 | y
            h = (h << 8 | b) % lim
    else:
        f = rule_fn(rule)
        for i, b in enumerate(buf):
            base = h & M
            u = 1
            for j in range(8):
                y = b >> 7 - j & 1
                k = (base, u)
                c = t.get(k)
                if c is None:
                    c = t[k] = [0, 0]
                if i >= m0:
                    r.append(c[y])
                    e.append(c[1 - y])
                c[y] += 1
                c[1 - y] = f(c[1 - y])
                u = u << 1 | y
            h = (h << 8 | b) % lim
    return np.array(r, dtype=np.float32), np.array(e, dtype=np.float32)


def mask_of_bits(bits):
    """byte-subset (bit i = i + 1 bytes back) -> integer mask over h."""
    return sum(255 << 8 * i for i in range(bits.bit_length()) if bits >> i & 1)


def cm2_masks():
    return [256 ** o - 1 for o in (0, 1, 2, 3, 4, 6, 8, 12, 16)]


def candidates(extra_orders=(9, 10, 11, 12, 14, 16, 20, 24)):
    """Crinkler's 256 byte subsets of the last 8 bytes in Crinkler's visiting
    order (Compressor.cpp:181-195 visits the bit-reversed mask byte of
    maski = 0..255; Crinkler's bit 7 is 1 byte back, ours bit 0, so the
    order is plainly subset 0, 1, 2, ...) + longer contiguous orders."""
    return [mask_of_bits(s) for s in range(256)] + [256 ** o - 1 for o in extra_orders]


def lit_len(v):
    """Typed characters of the shortest Python literal of v (decimal or hex)."""
    return min(len(str(v)), len(hex(v)))


class Fam:
    def __init__(self, data, primer, cands, rule, threads=1):
        buf = bytes(primer) + bytes(data)
        self.n = 8 * len(data)
        self.cands = list(cands)
        if threads > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(threads) as ex:
                res = list(ex.map(lambda M: predict(buf, len(primer), M, rule), self.cands))
        else:
            res = [predict(buf, len(primer), M, rule) for M in self.cands]
        self.r = [a for a, _ in res]
        self.e = [b for _, b in res]
        self.boosted = {}
        self.y = None

    def parts(self, k, boost):
        key = (k, boost)
        if key not in self.boosted:
            r, e = self.r[k], self.e[k]
            self.boosted[key] = (np.where(e == 0, r * 2 ** boost, r).astype(np.float32),
                                 np.where(r == 0, e * 2 ** boost, e).astype(np.float32))
        return self.boosted[key]

    def bits(self, models, boost, base):
        """models = [(candidate index, weight)] -> sum log2(s / p_right)."""
        R = np.full(self.n, float(base))
        Wr = np.full(self.n, float(base))
        for k, w in models:
            a, b = self.parts(k, boost)
            R += a * 2.0 ** w
            Wr += b * 2.0 ** w
        return float(np.log2((R + Wr) / R).sum())


class Eval:
    """Incremental size for the search: cost = bits + text bits of the
    parameters (chars * 300 / 64: a typed character carries 300/64 bits of
    the payload, 60 base-32 digits + 4 check glyphs per data line)."""

    def __init__(self, fam, boost, base, param_chars, char_bits=300 / 64):
        self.f, self.boost, self.base = fam, boost, base
        self.pc, self.cb = param_chars, char_bits
        self.R = np.full(fam.n, float(base))
        self.W = np.full(fam.n, float(base))
        self.w = {}
        self.evals = 0
        self.n = fam.n

    def size(self, models):
        new = {k: 2.0 ** w for k, w in models}
        for k in sorted(set(new) | set(self.w)):
            d = new.get(k, 0.0) - self.w.get(k, 0.0)
            if d:
                a, b = self.f.parts(k, self.boost)
                self.R += d * a
                self.W += d * b
        self.w = new
        self.evals += 1
        bits = float(np.log2((self.R + self.W) / self.R).sum())
        return int(256 * (bits + self.cb * self.pc(models)))


def optimize_weights(cs, models, maxw, init=None):
    """Compressor.cpp:77-131 (OptimizeWeights), weights 0..maxw; the start is
    ApproximateWeights (bytes in the mask) unless init gives one."""
    if init is None:
        models[:] = [(k, min(maxw, bin(cs.f.cands[k]).count('1') // 8)) for k, _ in models]
    else:
        models[:] = [(k, init(k, w)) for k, w in models]
    best = cs.size(models)
    if not models:
        return best
    index = last = len(models) - 1
    d = 1
    while True:
        k, w = models[index]
        nw = w + d
        skip = nw > maxw or nw < 0
        if not skip:
            new = list(models)
            new[index] = (k, nw)
            size = cs.size(new)
        if not skip and size < best:
            best, models[:], last = size, new, index
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


def search(cs, order=None, max_models=21, maxw=9, width=1, start=None, progress=None,
           final_reset=None):
    """Compressor.cpp:164-274 (ApproximateModels4k, SLOW = width 1,
    VERYSLOW = width 3) over the candidates in `order`; start = an initial
    model set (Crinkler starts empty).  Returns (models, cost).
    final_reset: upstream's last OptimizeWeights (:269) starts from
    ApproximateWeights (:83), i.e. every weight reset to the mask's byte
    count.  The first round of this study kept the searched weights instead
    (an undeclared deviation the refuter found); the default is now upstream's
    (env CRK_FINAL_KEEP=1 restores the first round's behaviour)."""
    if final_reset is None:
        import os
        final_reset = os.environ.get('CRK_FINAL_KEEP') != '1'
    order = list(range(len(cs.f.cands))) if order is None else order
    INT_MAX = 2 ** 62
    ELITE = 1 << 63
    init = list(start or [])
    sets = [[init, cs.size(init) | ELITE]] + [[[], INT_MAX] for _ in range(2 * width - 1)]
    key = lambda e: e[1] - 2 * ELITE if e[1] & ELITE else e[1]  # noqa: E731
    for step, mask in enumerate(order):
        for s in range(width):
            models, msize = sets[s]
            sets[width + s] = [[], INT_MAX]
            if msize == INT_MAX:
                continue
            if any(k == mask for k, _ in models) or len(models) >= max_models:
                continue
            new = list(models) + [(mask, 0)]
            old = msize & ~ELITE
            new_size = optimize_weights(cs, new, maxw)
            if new_size < old or width > 1:
                best = new_size
                m = len(new) - 2
                while m >= 0:
                    rmod = new[m]
                    cand = list(new)
                    cand[m] = cand[-1]
                    cand.pop()
                    size = optimize_weights(cs, cand, maxw)
                    if size < best:
                        best, new = size, cand
                    else:
                        new = cand[:m] + [rmod] + cand[m + 1:] + [new[-1]]
                    m -= 1
                nsize = best
                if msize & ELITE and new_size < old:
                    sets[s][1] = msize & ~ELITE
                    nsize |= ELITE
                sets[width + s] = [new, nsize]
        sets.sort(key=key)
        if progress:
            progress(step, cs.evals, sets[0])
    sets[0][1] &= ~ELITE
    sets.sort(key=key)
    models = list(sets[0][0])
    if final_reset:
        size = optimize_weights(cs, models, maxw)
    else:
        size = optimize_weights(cs, models, maxw, init=lambda k, w: w)
    return models, size


# --- the exact coder (what the typed d computes) ---------------------------

def model_ref(data, primer, masks, weights, boost, base, rule, cap=None):
    """Per coded bit (y, p0, p1), with cm2's shared dict (keys (h & M, u))."""
    f = rule_fn(rule)
    t, h, m, out = {}, 0, len(primer), []
    top = max((M.bit_length() + 7) // 8 for M in masks) if masks else 1
    lim = 256 ** max(top, 1)
    mw = list(zip(masks, weights))
    for i, b in enumerate(bytes(primer) + bytes(data)):
        u = 1
        for j in range(8):
            g = [t.setdefault((h & M, u), [0, 0]) for M in masks]
            p = [base + sum(c[y] << w + boost * (c[1 - y] < 1) for (M, w), c in zip(mw, g))
                 for y in (0, 1)]
            y = b >> 7 - j & 1
            if i >= m:
                out.append((y, p[0], p[1]))
            for c in g:
                c[y], c[1 - y] = c[y] + 1, f(c[1 - y])
                if cap and c[y] > cap:
                    c[y] = cap
            u = 2 * u + y
        h = (h << 8 | b) % lim
    return out


def encode_int(data, primer, masks, weights, boost, base, rule, cap=None):
    x = 0
    for y, p0, p1 in reversed(model_ref(data, primer, masks, weights, boost, base, rule, cap)):
        py = p1 if y else p0
        x = x // py * (p0 + p1) + (p0 if y else 0) + x % py
    return x


def decode(x, n, primer, masks, weights, boost, base, rule, cap=None):
    f = rule_fn(rule)
    t, h, m = {}, 0, len(primer)
    top = max((M.bit_length() + 7) // 8 for M in masks) if masks else 1
    lim = 256 ** max(top, 1)
    mw = list(zip(masks, weights))
    out = bytearray()
    for i in range(m + n):
        u = 1
        for j in range(8):
            g = [t.setdefault((h & M, u), [0, 0]) for M in masks]
            p = [base + sum(c[y] << w + boost * (c[1 - y] < 1) for (M, w), c in zip(mw, g))
                 for y in (0, 1)]
            if i < m:
                y = primer[i] >> 7 - j & 1
            else:
                s = p[0] + p[1]
                o = x % s
                y = int(o >= p[0])
                x = x // s * p[y] + o - p[0] * y
            for c in g:
                c[y], c[1 - y] = c[y] + 1, f(c[1 - y])
                if cap and c[y] > cap:
                    c[y] = cap
            u = 2 * u + y
        b = u & 255
        if i >= m:
            out.append(b)
        h = (h << 8 | b) % lim
    return bytes(out)


def digits(x):
    """base-32 digits of x (the typed G)."""
    return max(1, math.ceil(x.bit_length() / 5)) if x else 0
