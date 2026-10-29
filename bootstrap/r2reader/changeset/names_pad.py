#!/usr/bin/env python3
"""names_pad.py -- the module-level name maps of the texts of
RESULTS-2026-10-22 section 20 (the grey padding applied), in names_at's
interface (TEXT, EDITS, arm_map, edits_map) so claims_pad can hand it to
claims_at/claims_comp: at = build/pad/reader_before.py (section 19's applied
text, the literal '@', saved by apply_pad.py), names_at's 'at' map; pad =
r2reader/reader_lite_v1.py as applied (the typed region of
changeset/reader_pad128_at.py), names_at's 'pad128' map.  Writes
build/pad/names-TEXT.json ({'names': {...}}; run_sets --names takes it).

  python bootstrap/r2reader/changeset/names_pad.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import names_at as NA   # noqa: E402

OUT = os.path.join(BOOT, 'build', 'pad')
TEXT = {'at': os.path.join(OUT, 'reader_before.py'),
        'pad': os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py')}
EDITS = {}
FROM = {'at': 'at', 'pad': 'pad128'}


def arm_map(t):
    return NA.arm_map(FROM[t])


def edits_map(t):
    raise KeyError(t)


def main():
    for t in TEXT:
        m = arm_map(t)
        json.dump(dict(names=m), open(os.path.join(OUT, f'names-{t}.json'), 'w'), indent=1)
        print(t, {k: m[k] for k in ('rb', 'ld', 'fm', 'wk', 'v', 'ft', 'w', 'f', 'fr', 'h', 'j', 'z', 'e', 'm')})


if __name__ == '__main__':
    main()
