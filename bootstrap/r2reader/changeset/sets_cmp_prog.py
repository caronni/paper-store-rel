#!/usr/bin/env python3
"""sets_cmp_prog.py -- the acceptance sets and photo runs of the progress-line
text against the composite, case by case (RESULTS-2026-10-22 section 18), from
the run_sets JSON files (sets-NAME.json, slots-NAME.json, photos-NAME.json).
Every old line is PROJECTED to the new wording -- 'NAME: N bullseyes, B
blocks, chunks H / T more|done' -> 'N@ H/T', 'NAME: cannot read, ...' ->
'cannot read' -- and must equal the new line printed; chunks held and done
must agree; the new text's done (its output written) must equal its line's
H = T.

  python sets_cmp_prog.py BASE_DIR BASE_NAME OTHER_DIR OTHER_NAME
"""
import json
import os
import re
import sys

OLD = re.compile(r'^(?:.*: )?(\d+) bullseyes, \d+ blocks(?: accepted)?, chunks (\d+) / (\S+) (?:more|done)$')
OLDX = re.compile(r'^.*: cannot read, \d+ blocks(?: accepted)?, chunks \d+ / \S+ (?:more|done)$')


def project(ln):
    m = OLD.match(ln.strip())
    if m:
        return f'{m[1]}@ {m[2]}/{m[3]}'
    if OLDX.match(ln.strip()):
        return 'cannot read'
    return 'UNPROJECTED ' + ln


def load(d, n, what):
    p = os.path.join(d, f'{what}-{n}.json')
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    bd, bn, od, on = sys.argv[1:5]
    R, S = load(bd, bn, 'sets'), load(od, on, 'sets')
    if R and S:
        bad, lines, cannot, dl = [], 0, 0, []
        for c, r in R['cases'].items():
            x = S['cases'][c]
            pj = [project(ln) for ln in r['lines']]
            lines += len(x['lines'])
            cannot += sum(ln == 'cannot read' for ln in x['lines'])
            if (x['held'], x['done']) != (r['held'], r['done']) or pj != x['lines']:
                bad.append((c, r['held'], r['done'], x['held'], x['done'], pj, x['lines']))
            if x['done'] != x.get('done_line'):
                dl.append(c)
        print(f'sets: {len(R["cases"])} base cases, {len(S["cases"])} other; differ (held, done or the projected '
              f'line): {len(bad)}; lines compared {lines} ({cannot} cannot read); done != H = T: {dl}')
        for b in bad:
            print('   ', b)
        for k, X in (('base', R), ('other', S)):
            v = X['verdict']
            print(f"   {k}: " + ' '.join(f"{x}={'pass' if v[x] else 'FAIL'}" for x in 'ABCDEFGHI') +
                  f" all={v['all']} slots {X['slots']['read']}/{X['slots']['union']} missed {X['slots']['missed']} "
                  f"margin {v['margin']} damage alone {v['F alone']}")
        print('   slot pass per partial frame identical:', R['slots']['per_frame'] == S['slots']['per_frame'])
    P0, P = load(bd, bn, 'photos'), load(od, on, 'photos')
    if P0 and P:
        for o in P:
            if o not in P0:
                print(f'photos {o}: no base run')
                continue
            a, b = P0[o], P[o]
            pj = [project(ln) for ln in a.get('lines', [])]
            same = dict(held=a['held'] == b['held'], bullseyes=a['bullseyes'] == b['bullseyes'],
                        done=a['done'] == b['done'], output_identical=a['output_identical'] == b['output_identical'],
                        lines=(pj == b['lines']) if 'lines' in a else 'no base lines')
            print(f"photos {o}: other lines {b['lines']}; done {b['done']} (H = T {b.get('done_line')}), "
                  f"{b['output']} == scratch/typed/b.py: {b['output_identical']}; identical to base {same}")


if __name__ == '__main__':
    main()
