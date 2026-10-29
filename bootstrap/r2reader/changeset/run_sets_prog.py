#!/usr/bin/env python3
"""run_sets_prog.py -- run_sets_fresh.py (changeset/run_sets.py with the slot
pass's guard) with its outputs in build/progress/ (sets-NAME.json,
photos-NAME.json, slots-NAME.json, runs/, photos/), for the progress line of
RESULTS-2026-10-22 section 18 (ruling 56 as amended).  Same arguments as
run_sets.py (READER.py [...] [--names FILE] [--no-sets] [--no-photos]).

Three changes, all in how the output is read:
- the line `9@ 500/557` (and `cannot read` alone) is parsed beside the older
  wordings (diet/w4_harness.parse): bullseyes, held, need; blocks None (the
  line has none -- the lab's block counts come from the claims instrument);
  a `cannot read` line keeps the run's held / need so far;
- done is the reader's own signal, its output written (c.py, or b.py for a
  reader of the older names) in the work directory when the process ends;
  the line's H = T is recorded beside it (done_line) and the two compared;
- the photos run alone as well: orders 1, 2, 3, 4, then the pools 1,2,3 and
  1,2,4; every case keeps its printed lines verbatim.
"""
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_sets_fresh as RSF   # noqa: E402  (the guarded slot pass)

RS = RSF.RS
RS.OUT = os.path.join(RS.ROOT, 'build', 'progress')
RS.wh.OUT = RS.OUT
os.makedirs(RS.OUT, exist_ok=True)
RS.PHOTO_ORDERS = ((1,), (2,), (3,), (4,), (1, 2, 3), (1, 2, 4))
P56 = re.compile(r'^(\d+)@ (\d+)/(\S+)$')
_parse = RS.wh.parse


def parse(line):
    s = line.strip()
    m = P56.match(s)
    if m:
        return dict(raw=line, bullseyes=int(m[1]), blocks=None, held=int(m[2]), need=m[3],
                    done=m[3].isdigit() and int(m[2]) == int(m[3]))
    if s == 'cannot read':
        return dict(raw=line, blocks=None, cannot=True)
    out = _parse(line)
    b = re.search(r'(\d+) bullseyes', line)
    if b:
        out['bullseyes'] = int(b[1])
    return out


def parse_all(lines):
    ps, held, need = [], 0, '?'
    for ln in lines:
        x = parse(ln)
        if x.get('cannot'):
            x.update(held=held, need=need, done=False)
        held, need = x.get('held', held), x.get('need', need)
        ps.append(x)
    return ps


def job(args):
    tag, case, rpy, script, frames = args
    wd = os.path.join(RS.OUT, 'runs', tag, case.replace('/', '_'))
    t0 = time.time()
    lines, secs, rc, se = RS.run(rpy, script, frames, wd)
    ps = parse_all(lines)
    last = ps[-1] if ps else {}
    out = 'c.py' if script == 'b.py' else 'b.py'
    wrote = os.path.exists(os.path.join(wd, out))
    res = dict(case=case, frames=[os.path.relpath(f, RS.ROOT) for f in frames], lines=lines, secs=secs,
               exit=rc, blocks=[x.get('blocks') for x in ps], bullseyes=[x.get('bullseyes') for x in ps],
               held=last.get('held'), need=last.get('need'), done=wrote,
               done_line=bool(last.get('done')), stderr=se[-600:], wall=round(time.time() - t0, 1))
    shutil.rmtree(wd, ignore_errors=True)
    return res


def run_photos(name, path):
    primer, output = RS.names_of(path)
    src = open(path).read()
    src = RS.make_typed.put_token(src, 'N2', RS.PHOTO_N2)[0]
    src = RS.make_typed.put_token(src, 'B2', RS.PHOTO_B2)[0]
    want = open(os.path.join(RS.PHOTOS, 'b.py'), 'rb').read()
    out = {}
    for order in RS.PHOTO_ORDERS:
        wd = os.path.join(RS.OUT, 'photos', name, ''.join(map(str, order)))
        shutil.rmtree(wd, ignore_errors=True)
        os.makedirs(wd)
        shutil.copy2(os.path.join(RS.PHOTOS, 'r.py'), os.path.join(wd, primer))
        open(os.path.join(wd, 'v.py'), 'w').write(src)
        frames = [os.path.join(RS.PHOTOS, f'{k}.pgm') for k in order]
        lines, secs, rc, se = RS.run(src, 'v.py', frames, wd, fresh=False)
        ps = parse_all(lines)
        bp = os.path.join(wd, output)
        got = open(bp, 'rb').read() if os.path.exists(bp) else None
        out[''.join(map(str, order))] = dict(
            frames=[os.path.basename(f) for f in frames], lines=lines, blocks=[x.get('blocks') for x in ps],
            held=[x.get('held') for x in ps], need=ps[-1].get('need') if ps else None,
            bullseyes=[x.get('bullseyes') for x in ps], done=got is not None,
            done_line=bool(ps and ps[-1].get('done')), output=output,
            output_identical=(got == want), exit=rc, secs=secs, stderr=se[-400:])
        shutil.rmtree(wd, ignore_errors=True)
    RS.json.dump(out, open(os.path.join(RS.OUT, f'photos-{name}.json'), 'w'), indent=1)
    return out


RS.wh.parse = parse
RS.job = job
RS.run_photos = run_photos

if __name__ == '__main__':
    RS.main()
