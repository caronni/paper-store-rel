"""run_search.py -- ruling 32's compression-aware rename-and-rewrite search
(the cloud session's encoder lab, compressor-exploration/encoder-side:
search2.Searcher for scope-exact renames, run_rewrites' greedy best-first over
rewrites.gen + rewrites.top_moves) re-run on the current reader_lite_v1.py,
scored by ideal cm2 bits under stage 1's lowercase primer and orders
(0,1,2,3,4,6,8).  Phases alternate (renames, rewrites, renames, ...) until
neither gains.  Additions to the lab's loop: every candidate with a line over
72 characters scores +inf (the typed subset); the user functions that do I/O
or mutate their arguments (ld, wk, fm under their current names) are impure
for the rewrites; no module-level binding is renamed to a reserved name of
count_reader.py (d, q, k: the loader interface); module-level renames are tracked so the harnesses' names
(rb, ld, fm, wk, h, j, z, e) can be mapped: search.json 'names' = every
module-level name of the starting text -> its final spelling.

  python run_search.py [--workers N]
Outputs under bootstrap/build/changeset/rw/: search.log, best_typed.py,
search.json (phases, steps, module-level name map, bits)."""
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import common as C
import ev
import names2 as nm
import rewrites as R
import search2 as S

WORKERS = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else 4
MAXB = 12000
RESERVED = {'d', 'q', 'k'}   # count_reader.py: the loader's names, never bound at module level
LOGP = os.path.join(C.OUT, 'search.log')
os.makedirs(C.OUT, exist_ok=True)
logf = open(LOGP, 'a')


def log(m):
    m = time.strftime('%H:%M:%S ') + m
    print(m, flush=True)
    logf.write(m + '\n')
    logf.flush()


def too_long(b):
    return any(len(t) > 72 for t in b.split(b'\n'))


class Searcher(S.Searcher):
    def full(s, text):
        if too_long(text if isinstance(text, bytes) else text.encode()):
            return math.inf
        return super().full(text)


def module_map(old, new):
    """module-level name map across a pure rename (occurrences align 1:1)."""
    a, b = nm.bindings(old)[0], nm.bindings(new)[0]
    assert len(a) == len(b)
    out = {}
    for (_, _, n0, b0), (_, _, n1, b1) in zip(a, b):
        if b0[0] == 0:
            assert out.setdefault(n0, n1) == n1
    return out


def glyphs(bits):
    g = -(-math.ceil(bits) // 5)
    return g, -(-g // 60)


def main():
    src = C.typed_of()
    primer = C.primer()
    pool = [c for c in S.LOWER if c != 'l']
    tl = threading.local()

    def sc(t):
        b = t.encode() if isinstance(t, str) else t
        if too_long(b):
            return math.inf
        h = getattr(tl, 'h', None)
        if h is None:
            h = tl.h = ev.Handle(MAXB)
        return h.bits(b, primer)
    ex = ThreadPoolExecutor(WORKERS)
    start = sc(src)
    log(f'START {start:.3f} bits, glyphs/lines {glyphs(start)}, typed bytes {len(src.encode())}')
    names = {b[1]: b[1] for b in nm.table(src) if b[0] == 0}
    cur, best = src, start
    phases = []
    for ph in range(12):
        # ---- renames
        two = sorted({b[1] for b in nm.table(cur) if len(b[1]) == 2})
        se = Searcher(primer, MAXB, workers=WORKERS, log=log)
        t0 = time.time()
        new, nb = se.run(cur, pool, sweeps=8, extra=two,
                         cand_fn=lambda b: [n for n in pool + two if b[0] != 0 or n not in RESERVED])
        assert nm.strip_names(new) == nm.strip_names(cur)
        mm = module_map(cur, new)
        names = {k: mm.get(v, v) for k, v in names.items()}
        gain_r = nb - best
        phases.append(dict(phase=ph, kind='rename', bits=nb, delta=gain_r, wall_s=round(time.time() - t0)))
        log(f'phase {ph} renames: {nb:.3f} ({gain_r:+.3f}), {time.time() - t0:.0f} s, names {names}')
        cur, best = new, nb
        save(cur, best, start, phases, names)
        # ---- rewrites
        t0 = time.time()
        steps = []
        for rnd in range(400):
            imp = {names['ld'], names['wk'], names['fm']}
            cands = list(R.gen(cur, ('flip', 'comm', 'tperm', 'merge', 'split', 'shift', 'aug'), imp))
            cands += list(R.top_moves(cur))
            res = list(ex.map(lambda c: (sc(c[1]), c[0], c[1]), cands))
            res.sort(key=lambda r: r[0])
            if not res or res[0][0] >= best - 1e-9:
                break
            b, lab, txt = res[0]
            steps.append(dict(label=lab, bits=b, delta=b - best, raw_delta=len(txt.encode()) - len(cur.encode())))
            log(f'  rw {rnd}: {lab} {b - best:+.3f} -> {b:.3f} ({len(cands)} cands)')
            cur, best = txt, b
        gain_w = sum(s['delta'] for s in steps)
        phases.append(dict(phase=ph, kind='rewrite', bits=best, delta=gain_w, steps=steps,
                           wall_s=round(time.time() - t0)))
        log(f'phase {ph} rewrites: {best:.3f} ({gain_w:+.3f}), {len(steps)} steps, {time.time() - t0:.0f} s')
        save(cur, best, start, phases, names)
        if gain_r > -1e-9 and not steps:
            break
    x = C.M.cm2_enc.encode_int(cur.encode(), primer, ev.ORD)
    log(f'END ideal {best:.3f} (start {start:.3f}, {best - start:+.3f}); exact bits {x.bit_length()}, '
        f'glyphs {-(-x.bit_length() // 5)}')


def save(cur, best, start, phases, names):
    open(os.path.join(C.OUT, 'best_typed.py'), 'w').write(cur)
    json.dump(dict(start_bits=start, bits=best, phases=phases, names=names),
              open(os.path.join(C.OUT, 'search.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
