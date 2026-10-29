#!/usr/bin/env python3
"""names_prog.py -- the module-level name maps of the progress-line texts
(RESULTS-2026-10-22 section 18), spelling of record -> the text's spelling:
before = names_comp's comp map (the composite of section 17, copied to
build/progress/reader_before.py); prog = before composed with
build/progress/rw-prog/search.json (r2reader/reader_lite_v1.py as applied).
The text before its search (build/progress/reader_edits_prog.py) keeps the
composite's spelling.  The same interface as names_comp (TEXT, EDITS,
arm_map, edits_map), so claims_prog can hand it to claims_comp.  Writes
build/progress/names-TEXT.json ({'names': {...}}; run_sets --names takes it).

  python bootstrap/r2reader/changeset/names_prog.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import names_comp as NC   # noqa: E402

OUT = os.path.join(BOOT, 'build', 'progress')
TEXT = {'before': os.path.join(OUT, 'reader_before.py'),
        'prog': os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py')}
EDITS = {'prog': os.path.join(OUT, 'reader_edits_prog.py')}
PARENT = {'prog': 'before'}


def arm_map(t):
    if t == 'before':
        return NC.arm_map('comp')
    up = arm_map(PARENT[t])
    m = json.load(open(os.path.join(OUT, f'rw-{t}', 'search.json')))['names']
    return {k: m.get(v, v) for k, v in up.items()}


def edits_map(t):
    return arm_map(PARENT[t])


def main():
    for t in TEXT:
        m = arm_map(t)
        json.dump(dict(names=m), open(os.path.join(OUT, f'names-{t}.json'), 'w'), indent=1)
        print(t, {k: m[k] for k in ('rb', 'ld', 'fm', 'wk', 'v', 'ft', 'w', 'f', 'fr', 'h', 'j', 'z', 'e', 'm')})


if __name__ == '__main__':
    main()
