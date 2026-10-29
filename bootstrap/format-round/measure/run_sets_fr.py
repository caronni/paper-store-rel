#!/usr/bin/env python3
"""run_sets_fr.py -- the acceptance sets A-I, the margin and the damage frames
alone, per format-round configuration (never typed).

changeset/run_sets.py unchanged (its run arrangement, the slot pass, the
verdict), with diet/w4_sets' frame roots (F, PAGES, SETS, P2) pointed at the
configuration's re-renders (render.py sets) and its outputs moved to
build/format-round/runs-sets/CFG/ (sets-CFG.json, slots-CFG.json, grids/).
The sets' definitions are w4_sets.sets(), unchanged.  The reader: the ruled
text for the record kind, the searched variant text otherwise (fr_common.READER);
the slot pass's names from fr_common.NAMES.  No photos (they are of the
format of record).

  python run_sets_fr.py CFG [JOBS]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402
import render as R   # noqa: E402

sys.path.insert(0, os.path.join(C.BOOT, 'r2reader', 'changeset'))
cfg = sys.argv[1]
os.environ.setdefault('W4_JOBS', sys.argv[2] if len(sys.argv) > 2 else '4')
import run_sets as RS   # noqa: E402

ws = R.ws_for(cfg)
assert RS.ws is ws
RS.OUT = os.path.join(C.OUT, 'runs-sets', cfg)
RS.GRIDS = os.path.join(RS.OUT, 'grids')
os.makedirs(RS.GRIDS, exist_ok=True)
RS.wh.OUT = RS.OUT
RS.wh.JOBS = int(os.environ['W4_JOBS'])
kind = C.kind_of(cfg)
RS.NAMES.update({k: C.NAMES[kind][k] for k in RS.NAMES})

if __name__ == '__main__':
    path = C.READER[kind]
    ok, line = RS.audit(path)
    print(f'== {cfg}: {os.path.relpath(path, C.BOOT)}: {line}', flush=True)
    assert ok
    t0 = time.time()
    r = RS.run_sets(cfg, path)
    print(f'   sets {r["verdict"]} slots {r["slots"]["read"]}/{r["slots"]["union"]} '
          f'missed {r["slots"]["missed"]} ({time.time() - t0:.0f} s wall)', flush=True)
