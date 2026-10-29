#!/usr/bin/env python3
"""cannot_cv.py -- cannot_prog.py's 'cannot read' session (photo 1, a missing
file, photo 2, a file that is not a PGM, photo 3; the photos' primer as b.py,
N2 50533 / B2 327353449) on section 20's reader (pre, build/converge/final/
reader_before.py) and the reader of the convergence's fixed point (cv,
r2reader/reader_lite_v1.py).  Outputs in build/converge/final/cannot/.

  [CV_FINAL=DIR] [CV_PRE=READER.py] python bootstrap/r2reader/changeset/cannot_cv.py
(CV_FINAL in place of build/converge/final, CV_PRE in place of its
reader_before.py: the re-run of 2026-10-23, build/converge/v3/final.)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cannot_prog as CP   # noqa: E402

FINAL = os.environ.get('CV_FINAL', os.path.join(CP.RS.ROOT, 'build', 'converge', 'final'))
CP.OUT = os.path.join(FINAL, 'cannot')
CP.TEXTS = {'pre': os.environ.get('CV_PRE', os.path.join(CP.RS.ROOT, 'build', 'converge', 'final', 'reader_before.py')),
            'cv': os.path.join(CP.RS.ROOT, 'r2reader', 'reader_lite_v1.py')}

if __name__ == '__main__':
    CP.main()
