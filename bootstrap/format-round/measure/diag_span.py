#!/usr/bin/env python3
"""diag_span.py -- DIAGNOSTIC (outside the measurement of record; never typed):
V1's and V2's combs measure t over a 20-module span (READERS.md), but keep
the ruled lower bound t > 23 px, which a one-pixel-per-module loupe grid
(r2reader/grid_to_pgm.py) can never pass (t = 20 px).  This runs the two
loupe cases (set H, the margin's H seed 1) with copies of the two texts whose
only change is t>23 -> t>19 (written to build/format-round/diag/), through
run_sets_fr's arrangement, for the coarse configuration (the loupe grid is a
module grid: dot == coarse).  -> build/format-round/diag/span.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

out = {}
for kind in ('v1', 'v2'):
    sys.argv = ['x', f'{kind}-coarse', '2']
    for m in [m for m in list(sys.modules) if m in ('run_sets', 'run_sets_fr', 'w4_sets', 'render')]:
        del sys.modules[m]
    import run_sets_fr as F
    RS = F.RS
    src = open(C.READER[kind]).read()
    assert src.count('t>23 and') == 1
    p = os.path.join(C.OUT, 'diag', f'reader_{kind}_rw_t19.py')
    open(p, 'w').write(src.replace('t>23 and', 't>19 and'))
    RS.OUT = os.path.join(C.OUT, 'diag', f'runs-{kind}')
    RS.wh.OUT = RS.OUT
    cases, _ = RS.cases_for(p)
    cases = {k: v for k, v in cases.items() if 'H ' in k}
    res = RS.run_cases('diag-' + kind, p, cases)
    out[kind] = {k: dict(done=v['done'], held=v['held'], need=v['need'], blocks=v['blocks'], lines=v['lines'])
                 for k, v in res.items()}
C.jdump(out, os.path.join(C.OUT, 'diag', 'span.json'))
print(json.dumps(out, indent=1))
