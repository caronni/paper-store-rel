"""search_v2.py -- stage1/search.py (items 10 and 11: the rewrite candidates
and the joint name search on a.py's own text, scored by the exact typed
total) run for the convergence of ruling 60 (2026-10-23) with every input
explicit, through the environment (so the search's spawned workers, which
re-import this module, see the same):

  CV_TREE    the bootstrap/ tree whose stage1/ (template.py, make_typed.py,
             search.py) and r2reader/reader_lite_v1.py are run (a staging
             tree under build/converge/ holds the round's candidates);
  CV_BUNDLE  the R2 content (the round's candidate c.py): the reader's N2 / B2
             and the frontier's R2 payload (the page bound stays the
             record's, make_typed.R2_PAGES_BOUND, 3 pages);
  CV_BUILD   where search.json goes (M.BUILD/<case>/) and the reader copy;
  CV_FROZEN  the directory frozen_<case>.json is written to (--freeze); the
             tree's spellings are replaced only at the fixed point.

  CV_TREE=.. CV_BUNDLE=.. CV_BUILD=.. CV_FROZEN=.. python bootstrap/stage1/search_v2.py --case C --freeze [--workers N]
The tuple frontier is per run (search.py stage 1: the base spelling's
frontier choice is the search's tuple).
"""
import os
import sys

TREE = os.path.abspath(os.environ['CV_TREE'])
sys.path.insert(0, os.path.join(TREE, 'stage1'))
import make_typed as M  # noqa: E402
import search as S  # noqa: E402

assert os.path.abspath(M.HERE) == os.path.join(TREE, 'stage1'), M.HERE
assert os.path.abspath(S.HERE) == os.path.join(TREE, 'stage1'), S.HERE
M.BUNDLE = os.path.abspath(os.environ['CV_BUNDLE'])
M.the_reader.__defaults__ = (M.BUNDLE,)
M.BUILD = os.path.abspath(os.environ['CV_BUILD'])
M.READER_COPY = os.path.join(M.BUILD, 'reader_e2e.py')
S.HERE = os.path.abspath(os.environ['CV_FROZEN'])

if __name__ == '__main__':
    a = sys.argv[1:]
    os.makedirs(S.HERE, exist_ok=True)
    os.makedirs(M.BUILD, exist_ok=True)
    print(f'search_v2: tree {TREE}, bundle {M.BUNDLE}, build {M.BUILD}, frozen -> {S.HERE}', flush=True)
    S.run(a[a.index('--case') + 1], int(a[a.index('--workers') + 1]) if '--workers' in a else 4, '--freeze' in a)
