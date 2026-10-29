"""enc_crkpy.py -- the encoder of dec_crkpy.py: Crinkler's model search
(fam.search = ApproximateModels4k + OptimizeWeights, SLOW) on a sample of
the input (the first SAMPLE bytes; Crinkler searches the whole input, which
it can afford at 4 KB -- a SIMPLIFICATION, stated wherever it is used), then
the exact mirror of dec_crkpy's model with Crinkler's arithmetic coder
(crk_enc.Enc).  ALTERED VERSION of Crinkler (zlib licence, see README).

  enc(data, sample=65536, threads=1) -> container"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crk_enc as E  # noqa: E402
import fam as F  # noqa: E402

P = 262143977
SUB24 = list(range(256)) + [(1 << o) - 1 for o in (9, 10, 11, 12, 14, 16, 20, 24)]
SUB8 = list(range(256))


def search(sample, threads=1, max_models=21, rule='crk', subsets=None):
    """rule 'crk' = the first round (unbounded counters in the estimator);
    'crksat' = counters saturating at 255 as dec_crkpy's table does (the
    refuter's question); subsets = the candidate byte subsets (SUB24
    default; SUB8 = Crinkler's 256)."""
    subsets = SUB24 if subsets is None else subsets
    cands = [F.mask_of_bits(b) for b in subsets]
    fm = F.Fam(sample, b'', cands, rule, threads)
    ev = F.Eval(fm, 2, 10, lambda m: 4 * len(m), char_bits=8)    # 4 container bytes per model
    models, _ = F.search(ev, max_models=max_models, maxw=9)
    return [(subsets[k], w) for k, w in sorted(models, key=lambda kw: kw[1])], ev.evals


def compress(data, models):
    ms = [F.mask_of_bits(b) for b, _ in models]
    ws = [w for _, w in models]
    k = len(models)
    t = bytearray(2 * P)
    enc = E.Enc()
    h, top = 0, (1 << 192) - 1
    mw = list(zip(range(k), ms, ws))
    for b in data:
        u = 1
        for j in range(8):
            p0 = p1 = 10
            sl = []
            for m, M, w in mw:
                q = (((h & M) << 8 | u) * 2654435761 + m) % P * 2
                sl.append(q)
                c0, c1 = t[q], t[q + 1]
                if c0 and c1:
                    p0 += c0 << w
                    p1 += c1 << w
                else:
                    p0 += c0 << w + 2
                    p1 += c1 << w + 2
            y = b >> 7 - j & 1
            enc.code(p1, p0, 1 - y)
            o, s = (0, 1) if y else (1, 0)
            for q in sl:
                if t[q + o] > 1:
                    t[q + o] >>= 1
                if t[q + s] < 255:
                    t[q + s] += 1
            u = u << 1 | y
        h = (h << 8 | b) & top
    head = len(data).to_bytes(4, 'big') + bytes([k])
    for b, w in models:
        head += b.to_bytes(3, 'big') + bytes([w])
    return head + enc.end()


def enc(data, sample=65536, threads=1, models=None):
    if models is None:
        models, _ = search(data[:sample], threads)
    return compress(data, models)
