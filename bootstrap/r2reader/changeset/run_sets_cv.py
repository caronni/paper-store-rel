#!/usr/bin/env python3
"""run_sets_cv.py -- run_sets_prog.py (the `9@ 500/557` parse, done read as
the reader's own output written, the photos alone and pooled) with its
outputs in build/converge/final/sets/ (sets-NAME.json, photos-NAME.json,
slots-NAME.json, runs/, photos/), for the reader of the convergence's fixed
point (ruling 60, 2026-10-23).  Same arguments as run_sets.py (READER.py
[...] [--names FILE] [--no-sets] [--no-photos]); compare with section 20's
run by sets_cmp_at.py build/pad reader_lite_v1 build/converge/final/sets
reader_lite_v1.  CV_FINAL (environment): another final directory in place of
build/converge/final (the re-run of 2026-10-23 used build/converge/v3/final).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_sets_prog as RSP   # noqa: E402

RS = RSP.RS
RS.OUT = os.path.join(os.environ.get('CV_FINAL', os.path.join(RS.ROOT, 'build', 'converge', 'final')), 'sets')
RS.wh.OUT = RS.OUT
os.makedirs(RS.OUT, exist_ok=True)

if __name__ == '__main__':
    RS.main()
