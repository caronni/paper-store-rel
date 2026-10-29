#!/usr/bin/env python3
"""names_fresh.py -- the module-level name maps of the fresh-eyes texts
(RESULTS-2026-10-22 section 16), spelling of record -> the text's spelling:
the ruled text's map (build/changeset/rw/names.json, record -> ruled) composed
with each arm's search map (build/changeset/fresh/rw-ARM/search.json, ruled
-> arm).  Writes build/changeset/fresh/names-ARM.json ({'names': {...}}, the
form run_sets.py --names and one_bull.py read) for ruled and every searched
arm.

  python bootstrap/r2reader/changeset/names_fresh.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
CS = os.path.join(BOOT, 'build', 'changeset')
OUT = os.path.join(CS, 'fresh')
ARMS = ('f2', 'f3', 'f5', 'f6', 'f1', 'f4')
TEXT = {'ruled': os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py'),
        **{a: os.path.join(HERE, f'reader_{a}_fresh.py') for a in ARMS}}
EDITS = {a: os.path.join(HERE, f'reader_edits_{a}_fresh.py') for a in ARMS}


def ruled_map():
    return json.load(open(os.path.join(CS, 'rw', 'names.json')))['names']


def arm_map(arm):
    rec = ruled_map()
    if arm == 'ruled':
        return dict(rec)
    m = json.load(open(os.path.join(OUT, f'rw-{arm}', 'search.json')))['names']
    return {k: m.get(v, v) for k, v in rec.items()}


def path(arm):
    return os.path.join(OUT, f'names-{arm}.json')


def main():
    for a in ('ruled',) + ARMS:
        if a != 'ruled' and not os.path.exists(os.path.join(OUT, f'rw-{a}', 'search.json')):
            continue
        m = arm_map(a)
        json.dump(dict(names=m), open(path(a), 'w'), indent=1)
        print(a, {k: m[k] for k in ('rb', 'ld', 'fm', 'wk', 'v', 'ft', 'w', 'f', 'h', 'j', 'z', 'e', 'm')})


if __name__ == '__main__':
    main()
