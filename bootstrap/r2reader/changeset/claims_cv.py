#!/usr/bin/env python3
"""claims_cv.py -- claims_at.py's instrument (call for call on the 129
captures, the finder's threshold as each text used it; --brk the 199 break
frames) on the convergence's two reader texts (names_cv: pre, cv; env CV_PRE,
CV_CAND, CV_NAMES), outputs in env CV_OUT.

  CV_PRE=.. CV_CAND=.. CV_NAMES=.. CV_OUT=.. python claims_cv.py claims pre cv [JOBS] [--brk]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import claims_at as CA    # noqa: E402
import names_cv as NV     # noqa: E402

CA.NA = NV
CA.CC.NC = NV
CA.CC.OUT = os.environ['CV_OUT']

if __name__ == '__main__':
    CA.main()
