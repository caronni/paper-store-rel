#!/usr/bin/env python3
"""run_search_cv.py -- run_search_at.py's loop (ruling 32's rename-and-rewrite
search, rw/run_search.py's pieces, constrained: 72 columns, d/q/k kept out of
module scope) for the convergence of ruling 60 (2026-10-23): the reader text
of a staging tree, its N2/B2 baked from the round's candidate c.py, scored by
ideal cm2 bits under the round's a.py (a stage-1 chain build with c.py as the
content, stage1/chain_v2.py) at the tuple that build chose.  The impure set
is section 20's (be, v, cb, fr: the tree's spelling since section 19).

  python run_search_cv.py --reader R.PY --bundle C.PY --primer A.PY --orders 0,1,2,3,4,6 --out DIR [--workers N]
Outputs in DIR: search.log, best_typed.py, search.json (run_search's), and
candidate_reader.py = R.PY with its typed region replaced by the winner
(rw/common.put_back: shared block, N2/B2 tokens and markers restored).
"""
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'rw'))


def arg(name, default=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else default


SRC = os.path.abspath(arg('--reader'))
BUNDLE = os.path.abspath(arg('--bundle'))
PRIMER = os.path.abspath(arg('--primer'))
ORDERS = tuple(int(x) for x in arg('--orders').split(','))
OUT = os.path.abspath(arg('--out'))
import common as C   # noqa: E402

C.M.BUNDLE = BUNDLE
C.M.the_reader.__defaults__ = (BUNDLE,)
C.READER = SRC
C.PRIMER = PRIMER
C.OUT = OUT
os.makedirs(OUT, exist_ok=True)
_typed_of, _put_back = C.typed_of, C.put_back
C.typed_of = lambda path=SRC: _typed_of(path)
C.put_back = lambda typed, path=SRC: _put_back(typed, path)

import run_search as RS   # noqa: E402  (after C.OUT: its log opens there)
import ev                 # noqa: E402
import names2 as nm       # noqa: E402
import rewrites as R      # noqa: E402

ev.Handle.__init__.__defaults__ = (ORDERS,)
IMPURE_START = ('be', 'v', 'cb', 'fr')


def main():
    log, WORKERS, RESERVED = RS.log, RS.WORKERS, RS.RESERVED
    src = C.typed_of()
    primer = C.primer()
    pool = [c for c in RS.S.LOWER if c != 'l']
    tl = threading.local()

    def sc(t):
        b = t.encode() if isinstance(t, str) else t
        if RS.too_long(b):
            return math.inf
        h = getattr(tl, 'h', None)
        if h is None:
            h = tl.h = ev.Handle(RS.MAXB)
        return h.bits(b, primer)
    ex = ThreadPoolExecutor(WORKERS)
    start = sc(src)
    log(f'START cv {SRC} {start:.3f} bits, glyphs/lines {RS.glyphs(start)}, typed bytes {len(src.encode())}, '
        f'primer {PRIMER} ({len(primer)} B), orders {ORDERS}, bundle {BUNDLE}, impure {IMPURE_START}')
    names = {b[1]: b[1] for b in nm.table(src) if b[0] == 0}
    for k in IMPURE_START:
        assert k in names, k
    cur, best = src, start
    phases = []
    for ph in range(12):
        two = sorted({b[1] for b in nm.table(cur) if len(b[1]) == 2})
        se = RS.Searcher(primer, RS.MAXB, workers=WORKERS, log=log)
        t0 = time.time()
        new, nb = se.run(cur, pool, sweeps=8, extra=two,
                         cand_fn=lambda b: [n for n in pool + two if b[0] != 0 or n not in RESERVED])
        assert nm.strip_names(new) == nm.strip_names(cur)
        mm = RS.module_map(cur, new)
        names = {k: mm.get(v, v) for k, v in names.items()}
        gain_r = nb - best
        phases.append(dict(phase=ph, kind='rename', bits=nb, delta=gain_r, wall_s=round(time.time() - t0)))
        log(f'phase {ph} renames: {nb:.3f} ({gain_r:+.3f}), {time.time() - t0:.0f} s, names moved '
            f'{ {k: v for k, v in names.items() if k != v} }')
        cur, best = new, nb
        RS.save(cur, best, start, phases, names)
        t0 = time.time()
        steps = []
        for rnd in range(400):
            imp = {names[k] for k in IMPURE_START}
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
        RS.save(cur, best, start, phases, names)
        if gain_r > -1e-9 and not steps:
            break
    x = C.M.cm2_enc.encode_int(cur.encode(), primer, ORDERS)
    x0 = C.M.cm2_enc.encode_int(src.encode(), primer, ORDERS)
    moved = cur != src
    if moved:
        open(os.path.join(OUT, 'candidate_reader.py'), 'w').write(C.put_back(cur))
    json.dump(dict(start_bits=start, bits=best, exact_bits_start=x0.bit_length(), exact_bits=x.bit_length(),
                   glyphs_start=-(-x0.bit_length() // 5), glyphs=-(-x.bit_length() // 5), moved=moved,
                   orders=list(ORDERS), primer=PRIMER, bundle=BUNDLE, reader=SRC),
              open(os.path.join(OUT, 'summary.json'), 'w'), indent=1)
    log(f'END cv ideal {best:.3f} (start {start:.3f}, {best - start:+.3f}); exact bits {x0.bit_length()} -> '
        f'{x.bit_length()}, glyphs {-(-x0.bit_length() // 5)} -> {-(-x.bit_length() // 5)}; text moved {moved}')


if __name__ == '__main__':
    main()
