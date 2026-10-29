#!/usr/bin/env python3
"""run_sets.py -- the 2026-10-22 change set measured against the reader of
record, paired on the same inputs (adapted from ideation/run_sets.py; never
typed).

  python bootstrap/r2reader/changeset/run_sets.py READER.py [...] [--no-sets] [--no-photos]
  python bootstrap/r2reader/changeset/run_sets.py --table NAME [...]

For each reader file (BEGIN/END READER markers and the shared block):
  size     diet/w4_ladder.size (the ladder's convention, primer loader/a.py);
  audit    r2reader/count_reader.py must pass;
  sets     diet/w4_sets.sets() A-I and the margin, run as the chain runs them
           (diet/w4_harness.rpy_of: the loader's definitions + the typed text,
           N2 = B2 = 0), the script named as the reader's primer literal says
           (r.py for the reader of record, b.py once it reads b.py) so the tail
           primes on itself in both; EVERY 0/1 text-grid frame (set H, the
           margin's loupe seed 1) goes through r2reader/grid_to_pgm.py (the
           Plate's one-liner) first, for every reader; a reader that still
           has the text-grid branch also reads the two grids as text (extra
           cases 'x native ...', outside the verdict and the block total);
           then set I's slot pass (the spy on rb);
  photos   scratch/typed/{1,2,3,4}.pgm (read-only) pooled 1,2,3 and 1,2,4, the
           reader run as v.py beside scratch/typed/r.py saved under the name it
           opens as primer, N2 50533 / B2 327353449 baked in; its output (b.py
           or c.py) compared with scratch/typed/b.py.
Results: bootstrap/build/changeset/sets-NAME.json, photos-NAME.json, slots-NAME.json.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
R2R = os.path.dirname(HERE)
DIET = os.path.join(R2R, 'diet')
ROOT = os.path.dirname(R2R)                     # bootstrap/
sys.path.insert(0, DIET)
import w4_sets as ws          # noqa: E402  (its F, SETS, P2 point at build/w4: the frozen captures)
import w4_harness as wh       # noqa: E402
import w4_ladder as wl        # noqa: E402
import make_typed             # noqa: E402  (loader/make_typed.py, via w4_harness's sys.path)

OUT = os.path.join(ROOT, 'build', 'changeset')
GRIDS = os.path.join(OUT, 'grids')
os.makedirs(GRIDS, exist_ok=True)
wh.OUT = OUT                  # ws.verdict_i reads slots-NAME.json from here
PY = wh.PY
G2P = os.path.join(R2R, 'grid_to_pgm.py')
PHOTOS = 'scratch/typed'
PHOTO_N2, PHOTO_B2 = 50533, 327353449
PHOTO_ORDERS = ((1, 2, 3), (1, 2, 4))
# The slot pass's names for the reader's globals; --names FILE (a JSON object
# {name: the reader's spelling}, e.g. build/changeset/rw/search.json's 'names')
# maps them for a renamed reader.  Default: the reader's own spelling.
NAMES = {k: k for k in ('rb', 'ld', 'fm', 'wk', 'h', 'j', 'z', 'e')}


def names_of(path):
    """(the primer file the reader opens, the file it writes)"""
    s = open(path).read()
    if "open('b.py','rb')" in s:
        assert "open('c.py','wb')" in s
        return 'b.py', 'c.py'
    assert "open('r.py','rb')" in s and "open('b.py','wb')" in s
    return 'r.py', 'b.py'


def has_grid_branch(path):
    return "b'P5'" in open(path).read()


def to_pgm(txt, pad_tag=''):
    """a text grid through the Plate's one-liner (cached by name)."""
    out = os.path.join(GRIDS, os.path.basename(txt)[:-4] + pad_tag + '.pgm')
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(txt):
        # the one-liner reads grid.txt and writes grid.pgm in its working
        # directory (literals since ruling 66, b149721d), so it runs in a scratch one
        with tempfile.TemporaryDirectory() as td:
            shutil.copyfile(txt, os.path.join(td, 'grid.txt'))
            subprocess.run([PY, G2P], check=True, cwd=td)
            os.replace(os.path.join(td, 'grid.pgm'), out)
    return out


def audit(path):
    p = subprocess.run([PY, os.path.join(R2R, 'count_reader.py'), path], capture_output=True, text=True)
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def strip_prompt(ln):
    for pr in ('R2 frame (PGM or grid, empty line stops): ', 'file: '):
        while ln.startswith(pr):
            ln = ln[len(pr):]
    return ln.strip()


def run(rpy, script, frames, wd, timeout=1800, fresh=True):
    """w4_harness.run with the script's name a parameter (fresh=False: wd as prepared)."""
    if fresh:
        shutil.rmtree(wd, ignore_errors=True)
        os.makedirs(wd)
    open(os.path.join(wd, script), 'w').write(rpy)
    p = subprocess.Popen([PY, script], cwd=wd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, bufsize=1)
    lines, secs = [], []
    for f in frames:
        t = time.time()
        try:
            p.stdin.write(f + '\n')
            p.stdin.flush()
        except BrokenPipeError:
            break
        ln = p.stdout.readline()
        secs.append(round(time.time() - t, 2))
        if not ln:
            break
        lines.append(strip_prompt(ln))
        if ln.rstrip().endswith('done'):
            break
    try:
        p.stdin.write('\n')
        p.stdin.flush()
    except BrokenPipeError:
        pass
    so, se = p.communicate(timeout=timeout)
    return lines, secs, p.returncode, se


def job(args):
    tag, case, rpy, script, frames = args
    wd = os.path.join(OUT, 'runs', tag, case.replace('/', '_'))
    t0 = time.time()
    lines, secs, rc, se = run(rpy, script, frames, wd)
    ps = [wh.parse(l) for l in lines]
    last = ps[-1] if ps else {}
    res = dict(case=case, frames=[os.path.relpath(f, ROOT) for f in frames], lines=lines, secs=secs,
               exit=rc, blocks=[x.get('blocks') for x in ps], held=last.get('held'),
               need=last.get('need'), done=bool(last.get('done')), stderr=se[-600:],
               wall=round(time.time() - t0, 1))
    shutil.rmtree(wd, ignore_errors=True)
    return res


def run_cases(tag, path, cases):
    rpy, script = wh.rpy_of(path), names_of(path)[0]
    res = {}
    with ThreadPoolExecutor(wh.JOBS) as ex:
        for r in ex.map(job, [(tag, c, rpy, script, fr) for c, fr in cases.items()]):
            res[r['case']] = r
            print(f"{r['case']:34s} done={r['done']!s:5s} blocks={r['blocks']} chunks "
                  f"{r['held']}/{r['need']} secs={r['secs']} exit={r['exit']} {r['stderr'][-150:]!r}",
                  flush=True)
    return res


def ns_of(path):
    src = wh.rpy_of(path)
    ns = {}
    exec(compile(src.split('\nwhile ')[0], path, 'exec'), ns)
    return ns


def slots(ns, frame, known=None):
    """ideation/run_sets.slots (w4_slots' spy on rb), fm -> ((pitch, seeds), header)."""
    import numpy as np
    tj = json.load(open(frame[:-4] + '.json'))
    side = json.load(open(os.path.join(os.path.dirname(frame), tj['page_sidecar'])))
    Hm = np.array(tj['homography_grid_modules_to_px'])
    w, h = tj['size_px']

    def px(c, r):
        v = Hm @ [c, r, 1]
        return v[0] / v[2] - 0.5, v[1] / v[2] - 0.5
    data = {tuple(b) for b, c in zip(side['slot_block'], side['slot_chunk']) if c is not None}
    inf = set()
    for bi, bj in data:
        if all(0 <= x <= w - 1.001 and 0 <= y <= h - 1.001
               for x, y in (px(17 * bj + a, 17 * bi + b) for a in (.5, 17.5) for b in (.5, 17.5))):
            inf.add((bi, bj))
    got = []
    N = NAMES
    rb = ns[N['rb']]

    def spy(*a):
        out = rb(*a)
        if out:
            s = a[0]
            got.append((s[0] / 16, s[1] / 16))
        return out
    ns[N['rb']] = spy
    ns[N['h']], ns[N['j']], ns[N['z']] = ns[N['ld']](frame)
    ns[N['e']] = known or b''
    r = ns[N['fm']]()
    ns[N['e']] = known = known or r[1] or b''
    if known:
        ns[N['wk']](*r[0])
    ns[N['rb']] = rb
    cen = {(bi, bj): px(17 * bj + 9.5, 17 * bi + 9.5) for bi, bj in data}
    read = set()
    for x, y in got:
        read.add(min(cen, key=lambda q: math.hypot(cen[q][0] - x, cen[q][1] - y)))
    return inf, read, known


def slot_pass(name, path):
    ns = ns_of(path)
    U, R, per, known = set(), set(), {}, None
    for n in ws.P2_PARTIAL:
        inf, read, known = slots(ns, ws.p2(n), known)
        U, R = U | inf, R | read
        per[n] = [len(inf), len(read & inf), sorted(inf - read)]
    out = dict(rung=name, union=len(U), read=len(R & U), missed=sorted(U - R), per_frame=per)
    json.dump(out, open(os.path.join(OUT, f'slots-{name}.json'), 'w'), indent=1)
    return out


def cases_for(path):
    cases = {}
    native = {}
    for st in ws.sets().values():
        for c, fr in st.items():
            cases[c] = [to_pgm(f) if f.endswith('.txt') else f for f in fr]
            if has_grid_branch(path) and any(f.endswith('.txt') for f in fr):
                native['x native ' + c] = fr
    return cases, native


def run_sets(name, path):
    cases, native = cases_for(path)
    res = run_cases('CS-' + name, path, {**cases, **native})
    extra = {c: res.pop(c) for c in native}
    sp = slot_pass(name, path)
    v = ws.verdict(res, name)
    out = dict(reader=os.path.relpath(path, ROOT), size=wl.size(path), cases=res, extra=extra,
               verdict=v, slots=sp)
    json.dump(out, open(os.path.join(OUT, f'sets-{name}.json'), 'w'), indent=1)
    return out


def run_photos(name, path):
    primer, output = names_of(path)
    src = open(path).read()
    src = make_typed.put_token(src, 'N2', PHOTO_N2)[0]
    src = make_typed.put_token(src, 'B2', PHOTO_B2)[0]
    want = open(os.path.join(PHOTOS, 'b.py'), 'rb').read()
    out = {}
    for order in PHOTO_ORDERS:
        wd = os.path.join(OUT, 'photos', name, ''.join(map(str, order)))
        shutil.rmtree(wd, ignore_errors=True)
        os.makedirs(wd)
        shutil.copy2(os.path.join(PHOTOS, 'r.py'), os.path.join(wd, primer))
        open(os.path.join(wd, 'v.py'), 'w').write(src)
        frames = [os.path.join(PHOTOS, f'{k}.pgm') for k in order]
        lines, secs, rc, se = run(src, 'v.py', frames, wd, fresh=False)
        ps = [wh.parse(l) for l in lines]
        bp = os.path.join(wd, output)
        got = open(bp, 'rb').read() if os.path.exists(bp) else None
        out[''.join(map(str, order))] = dict(
            frames=[os.path.basename(f) for f in frames], blocks=[x.get('blocks') for x in ps],
            held=[x.get('held') for x in ps], need=ps[-1].get('need') if ps else None,
            bullseyes=[int(l.split(' bullseyes')[0].split()[-1]) if ' bullseyes' in l else None
                       for l in lines],
            done=bool(ps and ps[-1].get('done')), output=output,
            output_identical=(got == want), exit=rc, secs=secs, stderr=se[-400:])
        shutil.rmtree(wd, ignore_errors=True)
    json.dump(out, open(os.path.join(OUT, f'photos-{name}.json'), 'w'), indent=1)
    return out


def table(names):
    rows = ['| reader | raw | cm2 | glyphs | lines | A | B | C | D | E | F | G | H | I | I slots | all | '
            'margin | F alone | blocks | s (5 jobs) | photos 1,2,3 blocks (chunks) | 1,2,4 | closes |',
            '|' + '---|' * 23]
    for n in names:
        sp = os.path.join(OUT, f'sets-{n}.json')
        pp = os.path.join(OUT, f'photos-{n}.json')
        s = json.load(open(sp)) if os.path.exists(sp) else None
        ph = json.load(open(pp)) if os.path.exists(pp) else None
        if s:
            v, sz = s['verdict'], s['size']
            pf = ' | '.join({True: 'pass', False: '**FAIL**', None: 'n/a'}[v[k]] for k in ws.REQUIRED)
            sets = (f"{sz['raw']} | {sz['cm2']} | {sz['glyphs']} | {sz['lines']} | {pf} | {v.get('I note', '')} | "
                    f"{'PASS' if v['all'] else 'fail'} | {v['margin']} | {v['F alone']} | {v['blocks']} | {v['secs']}")
        else:
            sets = ' | '.join(['-'] * 16)
        if ph:
            a, b = ph['123'], ph['124']
            fmt = lambda r: ' '.join(f"{x}({y})" for x, y in zip(r['blocks'], r['held']))  # noqa: E731
            cl = ' / '.join(f"{'done' if r['done'] else 'OPEN'}{'=' if r['output_identical'] else ''}"
                            for r in (a, b))
            photos = f"{fmt(a)} | {fmt(b)} | {cl}"
        else:
            photos = '- | - | -'
        rows.append(f'| {n} | {sets} | {photos} |')
    return '\n'.join(rows)


def main():
    a = sys.argv[1:]
    if '--table' in a:
        print(table([x for x in a if x != '--table']))
        return
    do_sets, do_photos = '--no-sets' not in a, '--no-photos' not in a
    if '--names' in a:
        k = a.index('--names')
        m = json.load(open(a[k + 1]))
        NAMES.update({x: m.get('names', m)[x] for x in NAMES})
        del a[k:k + 2]
    paths = [os.path.abspath(x) for x in a if not x.startswith('--')]
    for path in paths:
        name = os.path.basename(path)[:-3]
        ok, line = audit(path)
        print(f'== {name}: {line}', flush=True)
        if not ok:
            print('   AUDIT FAILED, skipped')
            continue
        print('   size', wl.size(path), flush=True)
        if do_sets:
            t0 = time.time()
            r = run_sets(name, path)
            print(f'   sets {r["verdict"]} slots {r["slots"]["read"]}/{r["slots"]["union"]} '
                  f'missed {r["slots"]["missed"]} ({time.time() - t0:.0f} s wall)', flush=True)
            for c, x in r['extra'].items():
                print(f'   {c}: done={x["done"]} blocks={x["blocks"]} chunks {x["held"]}/{x["need"]}')
        if do_photos:
            t0 = time.time()
            r = run_photos(name, path)
            for k, v in r.items():
                print(f'   photos {k}: blocks {v["blocks"]} held {v["held"]}/{v["need"]} bullseyes '
                      f'{v["bullseyes"]} done={v["done"]} {v["output"]}==scratch b.py:{v["output_identical"]} '
                      f'secs {v["secs"]} {v["stderr"][-120:]!r}', flush=True)
            print(f'   ({time.time() - t0:.0f} s wall)')
    print(table([os.path.basename(p)[:-3] for p in paths]))


if __name__ == '__main__':
    main()
