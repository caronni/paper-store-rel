"""search2.py -- greedy coordinate descent over a program's bindings, scored by
the ideal code length under a.py's d() model (C mirror, ev.Handle).

Screening substitutes the binding's occurrence spans in the text directly (no
proof); the best-scoring candidate is then PROVED by names2.rename (scope-exact,
re-resolved) and, in window mode, confirmed by a FULL evaluation before it is
kept.  Window mode (monolith): the prefix up to the binding's first occurrence
is fed once (checkpoint), each candidate is scored on [first occurrence, last
occurrence + W) against the base text's same region, undoing after each try.
Ties keep the current name."""
import keyword, time, threading
from concurrent.futures import ThreadPoolExecutor
import names2 as nm, ev

LOWER = [chr(c) for c in range(97, 123)]
UPPER = [chr(c) for c in range(65, 91)]


def occ_spans(src):
    """binding -> list of (byte start, byte end) in src (frozen/builtin left out)."""
    occ, frozen, kws = nm.bindings(src)
    b = src.encode(); lines = b.split(b'\n')
    offs = [0]
    for L in lines: offs.append(offs[-1] + len(L) + 1)
    sp = nm._spans(lines, occ)
    out = {}
    for (node, kind, name, bd), (ln, c0, c1) in zip(occ, sp):
        if bd[0] == 'builtin' or bd in frozen: continue
        if kind == 'arg' and name in kws: continue
        out.setdefault(bd, []).append((offs[ln - 1] + c0, offs[ln - 1] + c1))
    return out


def subst(b, spans, new):
    parts, last = [], 0
    for s, e in sorted(spans):
        parts.append(b[last:s]); parts.append(new); last = e
    parts.append(b[last:])
    return b''.join(parts)


class Searcher:
    def __init__(s, primer, maxbytes, workers=2, window=None, log=print):
        s.primer = primer if isinstance(primer, bytes) else primer.encode()
        s.maxbytes, s.window, s.log = maxbytes, window, log
        s.ex = ThreadPoolExecutor(workers); s.workers = workers
        s.tl = threading.local()
        s.nfull = s.ntry = 0

    def H(s):
        h = getattr(s.tl, 'h', None)
        if h is None: h = s.tl.h = ev.Handle(s.maxbytes)
        return h

    def full(s, text):
        s.nfull += 1
        return s.H().bits(text, s.primer)

    def run(s, src, pool, sweeps=3, extra=(), only=None, cand_fn=None):
        cur = src; best = s.full(cur.encode()); start = best
        s.log(f'start {best:.1f} bits')
        for sw in range(sweeps):
            changed, t0 = 0, time.time()
            tab = nm.table(cur)
            order = sorted(tab, key=lambda b: -tab[b])
            if only: order = [b for b in order if only(b)]
            # bindings are re-keyed after every accepted rename: walk by (scope, name) identity
            pending = list(order)
            while pending:
                b = pending.pop(0)
                spans = occ_spans(cur)
                if b not in spans: continue
                sp = spans[b]
                cands = cand_fn(b) if cand_fn else [n for n in list(pool) + list(extra)]
                cands = [n for n in dict.fromkeys(cands) if n != b[1] and not keyword.iskeyword(n)]
                base = cur.encode()
                if s.window is None:
                    def sc(n):
                        return s.full(subst(base, sp, n.encode()))
                    res = list(s.ex.map(lambda n: (sc(n), n), cands))
                    ref = best
                else:
                    a = min(x for x, _ in sp); z = max(y for _, y in sp)
                    W = s.window
                    # one checkpoint per worker thread: score in chunks per thread
                    chunks = [cands[i::s.workers] for i in range(s.workers)]
                    def work(ch):
                        h = s.H(); h.prefix(s.primer + base[:a])
                        r = [(h.trybits(base[a:z + W]), None)]
                        for n in ch:
                            t = subst(base, sp, n.encode())
                            dz = len(t) - len(base)
                            r.append((h.trybits(t[a:z + dz + W]), n))
                        return r
                    rr = list(s.ex.map(work, chunks))
                    ref = rr[0][0][0]
                    res = [x for r in rr for x in r[1:]]
                s.ntry += len(res)
                res.sort()
                for sc_, n in res:
                    if sc_ >= ref - 1e-9: break
                    try:
                        out = nm.rename(cur, {b: n})
                    except (nm.Unsound, SyntaxError):
                        continue
                    if s.window is not None:
                        f = s.full(out.encode())
                        if f >= best - 1e-9: break
                        sc_ = f
                    best, cur = sc_, out; changed += 1
                    break
            s.log(f'sweep {sw + 1}: {best:.1f} bits ({best - start:+.1f}), {changed} changed, {time.time() - t0:.0f} s, tries {s.ntry}')
            if not changed: break
        return cur, best
