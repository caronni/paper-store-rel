#!/usr/bin/env python3
"""apply_cv.py -- the reader text of the convergence's fixed point (ruling 60,
2026-10-23; bootstrap/CONVERGENCE-2026-10-23.md) written IN PLACE:
r2reader/reader_lite_v1.py = the staging tree's reader (the typed region the
search re-runs of rounds 1 and 2 chose, changeset/run_search_cv.py; put back
by rw/common.put_back), with one header paragraph added before the run line.
Refuses unless reader_lite_v1.py is section 20's text (sha 4677ed3f...) or
already this output; section 20's text is saved to
build/converge/final/reader_before.py (+ .sha256).

  python bootstrap/r2reader/changeset/apply_cv.py
"""
import hashlib
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
TARGET = os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py')
STAGED = os.path.join(BOOT, 'build', 'converge', 'tree', 'bootstrap', 'r2reader', 'reader_lite_v1.py')
BEFORE = os.path.join(BOOT, 'build', 'converge', 'final', 'reader_before.py')
BEFORE_SHA = '4677ed3f1e3c31cd792edabaa15f15d9472ff89f7f569e87228c7d49d236faae'
ANCHOR = '# Only the region between the READER markers is typed, minus the shared\n'
WORDS = ("The convergence of the three searches (ruling 60 of 2026-10-23; "
         "bootstrap/CONVERGENCE-2026-10-23.md, changeset/run_search_cv.py): the search re-run "
         "under the chain's own primer, the uppercase a.py of a stage-1 build with c.py as the "
         "content, at that build's tuple (0,1,2,3,4,6) (the earlier runs: the lowercase a.py of "
         "the stand-in build at (0,1,2,3,4,6,8)).  Round 1 moved cb and fr to the top, f after "
         "ax and v before sp and ft, respelled ax's step c sz, sp's bit y sz, ft's grey r z and "
         "v's placed f p, and took two tuple orders in dd and one in v; round 2, under round "
         "1's a.py, respelled the pitch p r in fr, rb and a, and took (x+t)*16 in dd, r>>8 in "
         "fr and >>8 for //256 in rb (shift), t>23 in sp (flip); no module-level name moved; "
         "round 3's winner (one glyph fewer in the upper case, one more in the lower) is not "
         "taken.  Each round identical call for call on the 129 captures.")


def main():
    staged = open(STAGED).read()
    add = textwrap.fill(WORDS, 75, initial_indent='# ', subsequent_indent='# ') + '\n'
    assert staged.count(ANCHOR) == 1
    new = staged.replace(ANCHOR, add + ANCHOR)
    region = lambda s: s.split('# BEGIN READER\n', 1)[1]
    assert region(new) == region(staged)
    cur = open(TARGET).read()
    h = hashlib.sha256(cur.encode()).hexdigest()
    assert h == BEFORE_SHA or cur == new, 'reader_lite_v1.py is neither section 20\'s text nor this output'
    if h == BEFORE_SHA:
        os.makedirs(os.path.dirname(BEFORE), exist_ok=True)
        open(BEFORE, 'w').write(cur)
        open(BEFORE + '.sha256', 'w').write(f'{h}  reader_before.py\n')
    head = lambda s: s.split('# BEGIN READER\n', 1)[0]
    assert head(cur).replace(ANCHOR, add + ANCHOR) == head(new) or cur == new
    open(TARGET, 'w').write(new)
    print(add, end='')
    print('written', TARGET, hashlib.sha256(new.encode()).hexdigest())


if __name__ == '__main__':
    main()
