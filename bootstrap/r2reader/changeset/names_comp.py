#!/usr/bin/env python3
"""names_comp.py -- the module-level name maps of the composite texts
(RESULTS-2026-10-22 section 17), spelling of record -> the text's spelling:
ruled = build/changeset/rw/names.json (record -> ruled); comp = ruled composed
with build/composite/rw-comp/search.json (ruled -> composite); pad / padt =
comp composed with build/composite/rw-pad|rw-padt/search.json.  Texts:
ruled = build/composite/reader_ruled.py (the copy of the ruled text), comp =
r2reader/reader_lite_v1.py (the composite applied in place), pad / padt =
build/composite/reader_pad.py / reader_padt.py (the searched padded arms,
never applied).  Writes build/composite/names-TEXT.json ({'names': {...}}).

  python bootstrap/r2reader/changeset/names_comp.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(BOOT, 'build', 'composite')
CS = os.path.join(BOOT, 'build', 'changeset')
TEXT = {'ruled': os.path.join(OUT, 'reader_ruled.py'),
        'comp': os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py'),
        'pad': os.path.join(OUT, 'reader_pad.py'),
        'padt': os.path.join(OUT, 'reader_padt.py')}
EDITS = {k: os.path.join(OUT, f'reader_edits_{k}.py') for k in ('comp', 'pad', 'padt')}
PARENT = {'comp': 'ruled', 'pad': 'comp', 'padt': 'comp'}


def arm_map(t):
    if t == 'ruled':
        return dict(json.load(open(os.path.join(CS, 'rw', 'names.json')))['names'])
    up = arm_map(PARENT[t])
    m = json.load(open(os.path.join(OUT, f'rw-{t}', 'search.json')))['names']
    return {k: m.get(v, v) for k, v in up.items()}


def edits_map(t):
    """the text before its search keeps its parent's spelling."""
    return arm_map(PARENT[t])


def path(t):
    return os.path.join(OUT, f'names-{t}.json')


def main():
    for t in TEXT:
        if t != 'ruled' and not os.path.exists(os.path.join(OUT, f'rw-{t}', 'search.json')):
            continue
        m = arm_map(t)
        json.dump(dict(names=m), open(path(t), 'w'), indent=1)
        print(t, {k: m[k] for k in ('rb', 'ld', 'fm', 'wk', 'v', 'ft', 'w', 'f', 'h', 'j', 'z', 'e', 'm')})


if __name__ == '__main__':
    main()
