#!/usr/bin/env python3
"""sets_cmp_at.py -- sets_cmp_prog.py's case-by-case comparison of two run_sets
JSON sets (sets-NAME.json, slots-NAME.json, photos-NAME.json) for
RESULTS-2026-10-22 section 19, where both texts print the `9@ 500/557` line:
a line already in that wording (or `cannot read`) is compared as printed,
an older one projected as sets_cmp_prog does; chunks held and done must
agree; the other text's done (its output written) must equal its line's
H = T.

  python sets_cmp_at.py BASE_DIR BASE_NAME OTHER_DIR OTHER_NAME
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sets_cmp_prog as SC   # noqa: E402

NEW = re.compile(r'^\d+@ \d+/\S+$')
_project = SC.project


def project(ln):
    s = ln.strip()
    return s if NEW.match(s) or s == 'cannot read' else _project(ln)


SC.project = project

if __name__ == '__main__':
    SC.main()
