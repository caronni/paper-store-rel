#!/usr/bin/env python3
"""names_cv.py -- the module-level name maps for the convergence of ruling 60
(2026-10-23), in names_at's interface (TEXT, EDITS, arm_map, edits_map) so
claims_cv can hand it to claims_at/claims_comp: pre = the reader text before
the convergence's search step (env CV_PRE; section 20's text, names_pad's
'pad' map), cv = the searched candidate (env CV_CAND), pre's map composed
with the search's module-level name map (env CV_NAMES = its search.json).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import names_pad as NP   # noqa: E402

TEXT = {'pre': os.environ['CV_PRE'], 'cv': os.environ['CV_CAND']}
EDITS = {}


def arm_map(t):
    up = NP.arm_map('pad')
    if t == 'pre':
        return up
    m = json.load(open(os.environ['CV_NAMES']))['names']
    return {k: m.get(v, v) for k, v in up.items()}


def edits_map(t):
    raise KeyError(t)
