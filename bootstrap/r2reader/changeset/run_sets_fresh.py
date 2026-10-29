#!/usr/bin/env python3
"""run_sets_fresh.py -- changeset/run_sets.py unchanged, its outputs moved to
build/changeset/fresh/ (sets-NAME.json, photos-NAME.json, slots-NAME.json,
runs/), for the fresh-eyes arms (RESULTS-2026-10-22 section 16).  Same
arguments as run_sets.py (READER.py [...] [--names FILE] [--no-sets]
[--no-photos] | --table NAME [...]).

One addition: set I's slot pass calls the reader's locator in process,
outside the reader's own try/except; a text whose locator raises on a
partial frame (F5: the unclamped sampler, IndexError) would abort the pass.
Here such a frame counts as read nothing (what the process prints: 'cannot
read'), the rb spy is taken back out, and the frame's in-frame slots still
count in the union; the exception is printed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_sets as RS   # noqa: E402

RS.OUT = os.path.join(RS.ROOT, 'build', 'changeset', 'fresh')
RS.wh.OUT = RS.OUT
os.makedirs(RS.OUT, exist_ok=True)
_slots = RS.slots


def slots(ns, frame, known=None):
    rb = ns[RS.NAMES['rb']]
    try:
        return _slots(ns, frame, known)
    except Exception as ex:
        ns[RS.NAMES['rb']] = rb
        print(f'   slot pass: {os.path.basename(frame)} raised {type(ex).__name__}: {ex} -> read nothing', flush=True)
        ns2 = dict(ns)
        ns2[RS.NAMES['ld']] = lambda f: (0, 0, b'')
        ns2[RS.NAMES['fm']] = lambda: ((0, []), b'')
        inf, _, _ = _slots(ns2, frame, known)
        return inf, set(), known


RS.slots = slots

if __name__ == '__main__':
    RS.main()
