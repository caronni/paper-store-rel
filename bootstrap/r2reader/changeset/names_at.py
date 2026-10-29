#!/usr/bin/env python3
"""names_at.py -- the module-level name maps of the texts of RESULTS-2026-10-22
section 19, spelling of record -> the text's spelling: prog = names_prog's
prog map (the text of section 18, copied to build/at/reader_before.py); at =
prog composed with build/at/rw-at/search.json (r2reader/reader_lite_v1.py as
applied, the literal '@'); pad128 = at composed with
build/at/rw-pad128/search.json (r2reader/changeset/reader_pad128_at.py, the
grey padding, never applied).  A text before its search keeps its parent's
spelling.  The same interface as names_comp (TEXT, EDITS, arm_map,
edits_map), so claims_at can hand it to claims_comp.  Writes
build/at/names-TEXT.json ({'names': {...}}; run_sets --names takes it).

  python bootstrap/r2reader/changeset/names_at.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import names_prog as NP   # noqa: E402

OUT = os.path.join(BOOT, 'build', 'at')
TEXT = {'prog': os.path.join(OUT, 'reader_before.py'),
        'at': os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py'),
        'pad128': os.path.join(HERE, 'reader_pad128_at.py')}
EDITS = {'at': os.path.join(OUT, 'reader_edits_at.py'),
         'pad128': os.path.join(OUT, 'reader_edits_pad128.py')}
PARENT = {'at': 'prog', 'pad128': 'at'}


def arm_map(t):
    if t == 'prog':
        return NP.arm_map('prog')
    up = arm_map(PARENT[t])
    m = json.load(open(os.path.join(OUT, f'rw-{t}', 'search.json')))['names']
    return {k: m.get(v, v) for k, v in up.items()}


def edits_map(t):
    return arm_map(PARENT[t])


def main():
    for t in TEXT:
        if t != 'prog' and not os.path.exists(os.path.join(OUT, f'rw-{t}', 'search.json')):
            continue
        m = arm_map(t)
        json.dump(dict(names=m), open(os.path.join(OUT, f'names-{t}.json'), 'w'), indent=1)
        print(t, {k: m[k] for k in ('rb', 'ld', 'fm', 'wk', 'v', 'ft', 'w', 'f', 'fr', 'h', 'j', 'z', 'e', 'm')})


if __name__ == '__main__':
    main()
