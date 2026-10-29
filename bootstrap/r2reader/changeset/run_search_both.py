#!/usr/bin/env python3
"""run_search_both.py -- ruling 32's rename-and-rewrite search (rw/run_search.py,
unchanged: the constrained run, d/q/k kept out of module scope, lines <= 72,
ld/wk/fm impure, stage 1's lowercase primer, orders (0,1,2,3,4,6,8)) pointed
at the union text changeset/reader_edits_both.py (apply_both.py, the union gate), outputs
under build/changeset/both/rw/ (search.log, search.json, best_typed.py).

  python bootstrap/r2reader/changeset/run_search_both.py [--workers N]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'rw'))
import common as C   # noqa: E402

SRC = os.path.join(HERE, 'reader_edits_both.py')
C.READER = SRC
C.OUT = os.path.join(C.ROOT, 'build', 'changeset', 'both', 'rw')
_typed_of, _put_back = C.typed_of, C.put_back
C.typed_of = lambda path=SRC: _typed_of(path)
C.put_back = lambda typed, path=SRC: _put_back(typed, path)

import run_search   # noqa: E402

if __name__ == '__main__':
    run_search.main()
