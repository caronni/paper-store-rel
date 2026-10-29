#!/usr/bin/env python3
# Copied 2026-10-23 from build/changeset/edge/edge.py (gitignored, the 10-22 change set; sha256
# 8b8ee9b2b985d25aba477f586c571bdf8ad0764c2eb68919cbbfe0a5d683a882), the driver
# r2reader/changeset/RESULTS-2026-10-22.md §11 cites; its outputs stay in build/changeset/edge/ (OUT).
# Changed against the original, nothing else (these comment lines aside): BOOT goes two levels up
# from HERE, not three; OUT = build/changeset/edge is added; RND and RUNS and the five json dumps
# (pools, loo, ring15, control, alone) are joined to OUT where the original joined them to HERE.
"""The envelope edge, paired (RESULTS-2026-10-22 §11): the three reader texts
(reader_before, reader_after_edits, final reader_lite_v1) on the same hard
captures of the CURRENT stage-1 pages (build/stage1/lower/r2/page_p*.pbm).

  python edge.py render          camera.py renders -> edge/renders/ (parallel)
  python edge.py pools [JOBS]    every reader x pool, JOBS processes -> pools.json
  python edge.py alone           every frame alone, one process at a time,
                                 readers alternating (order rotated per frame)
                                 -> alone.json (the paired walls)
  python edge.py loo [JOBS]      the change set's leave-one-out texts
                                 (build/changeset/loo/, items b c d g_ft g_fm)
                                 on every edge and quarter frame alone -> loo.json
  python edge.py ring15         the stress variant: rings around all 15
                                 bullseyes of p0, each reader alone -> ring15.json
  python edge.py control         the close arrangement's control: each reader
                                 on clean-s1-p0 + the build's p1 nominal-b030
                                 (p1 closes alone in e2e) -> control.json
Each run directory holds the reader as reader.py with N2/B2 = the stage-1
build's constants and its shared d's order tuple = the build's (0,1,2,3,4,6,8) and build/stage1/lower/b.py under the primer name the
reader opens (r.py before, b.py after); a close is checked against
build/bundle/b.py.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(BOOT, 'build', 'changeset', 'edge')
PY = 'env/bin/python'
CAM = os.path.join(BOOT, 'r2', 'camera.py')
S1 = os.path.join(BOOT, 'build', 'stage1', 'lower')
PAGES = os.path.join(S1, 'r2')
PRIMER = os.path.join(S1, 'b.py')
BUNDLE = os.path.join(BOOT, 'build', 'bundle', 'b.py')
RND = os.path.join(OUT, 'renders')
RUNS = os.path.join(OUT, 'runs')
B = json.load(open(os.path.join(S1, 'build.json')))
N2, B2 = B['n2'], B['b2']
sys.path.insert(0, os.path.join(BOOT, 'stage1'))
import make_typed  # noqa: E402

READERS = {   # name: (path, primer file it opens, file it writes)
    'before': (os.path.join(BOOT, 'build', 'changeset', 'reader_before.py'), 'r.py', 'b.py'),
    'edits': (os.path.join(BOOT, 'build', 'changeset', 'reader_after_edits.py'), 'b.py', 'c.py'),
    'final': (os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py'), 'b.py', 'c.py'),
}
ORDER = ['before', 'edits', 'final']
LOO = ['b_v01', 'c_v05', 'd_v02', 'g_ft', 'g_fm']
for _k in LOO:
    READERS['without_' + _k] = (os.path.join(BOOT, 'build', 'changeset', 'loo', f'without_{_k}.py'), 'b.py', 'c.py')
NOM = ['--preset', 'nominal']
EDGE = NOM + ['--spm', '1.5', '--blur', '0.40']
QUAR = NOM + ['--spm', '2', '--blur', '0.45']
RING_BE = (3, 4, 7)     # bullseye indices (8,5) (8,11) (14,8): interior, full 8-block rings
RING_R_MM = 3.0         # blot radius: 5.9 modules, inside the 16x16 interior of each neighbour


def ring_damage(bes=RING_BE):
    side = json.load(open(os.path.join(PAGES, 'page_p0.json')))
    out = []
    for k in bes:
        bi, bj = side['bullseyes'][k]['block']
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di or dj:
                    out += ['--damage', f'blot-at:{17 * (bj + dj) + 8.5}:{17 * (bi + di) + 8.5}:{RING_R_MM}']
    return out


def renders():
    """[(name, page, camera args)]"""
    r = []
    for s in (1, 2, 3, 4):
        for p in (0, 1, 2):
            r.append((f'edge-s{s}-p{p}', p, EDGE + ['--seed', str(s)]))
    for s in (1, 2):
        for p in (0, 1, 2):
            for q in ('tl', 'tr', 'bl', 'br'):
                r.append((f'q045-s{s}-p{p}-{q}', p, QUAR + ['--frame', q, '--seed', str(s)]))
    r.append(('ring-s1-p0', 0, NOM + ['--blur', '0.30', '--seed', '1'] + ring_damage()))
    r.append(('clean-s1-p0', 0, NOM + ['--blur', '0.30', '--seed', '1']))
    return r


def frame(name):
    if os.path.isabs(name):
        return name
    return os.path.join(RND, name + '.pgm')


def pools():
    """[(group, pool, [frame names])]"""
    out = []
    for s in (1, 2, 3, 4):
        out.append(('edge', f'edge-s{s}', [f'edge-s{s}-p{p}' for p in (0, 1, 2)]))
    for s in (1, 2):
        for p in (0, 1, 2):
            out.append(('q045', f'q045-s{s}-p{p}', [f'q045-s{s}-p{p}-{q}' for q in ('tl', 'tr', 'bl', 'br')]))
    out.append(('ring', 'ring-s1-p0', ['ring-s1-p0']))
    out.append(('ring', 'clean-s1-p0', ['clean-s1-p0']))
    return out


def cam(job):
    name, p, args = job
    out = frame(name)
    t = time.time()
    subprocess.run([PY, CAM, os.path.join(PAGES, f'page_p{p}.pbm'), out,
                    '--sidecar', os.path.join(PAGES, f'page_p{p}.json')] + args,
                   check=True, capture_output=True)
    return name, round(time.time() - t, 1)


def reader_src(name):
    path = READERS[name][0]
    s = open(path).read()
    s, k1 = make_typed.put_token(s, 'N2', N2)
    s, k2 = make_typed.put_token(s, 'B2', B2)
    assert k1 == 1 and k2 == 1, (name, k1, k2)
    # the stage-1 pages are cm2 at the build's order tuple (build.json 'orders',
    # the d of stage 1's a.py); the readers' shared d carries the loader's long
    # tuple.  The decode at the close only: the read path never calls d.
    long_t, s1_t = '(0,1,2,3,4,6,8,12,16)', '(' + ','.join(map(str, B['orders'])) + ')'
    assert s.count(long_t) == 1, name
    return s.replace(long_t, s1_t)


def strip_prompt(ln):
    for pr in ('R2 frame (PGM or grid, empty line stops): ', 'file: '):
        while ln.startswith(pr):
            ln = ln[len(pr):]
    return ln.strip()


def parse(ln):
    import re
    d = dict(raw=ln)
    b = re.search(r'(\d+) bullseyes', ln)
    m = re.search(r'(\d+) blocks accepted', ln)
    c = re.search(r'chunks (\d+) / (\S+) (more|done)', ln)
    d['bullseyes'] = int(b.group(1)) if b else (None if 'cannot read' not in ln else 0)
    d['blocks'] = int(m.group(1)) if m else None
    d['held'] = int(c.group(1)) if c else None
    d['need'] = c.group(2) if c else None
    d['done'] = bool(c and c.group(3) == 'done')
    return d


def run(rname, frames, wd):
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd)
    _, primer, output = READERS[rname]
    open(os.path.join(wd, 'reader.py'), 'w').write(reader_src(rname))
    shutil.copy2(PRIMER, os.path.join(wd, primer))
    p = subprocess.Popen([PY, 'reader.py'], cwd=wd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, bufsize=1)
    rows = []
    t0 = time.time()
    for f in frames:
        t = time.time()
        la = os.getloadavg()[0]
        p.stdin.write(frame(f) + '\n')
        p.stdin.flush()
        ln = p.stdout.readline()
        r = parse(strip_prompt(ln).replace(frame(f), f))
        r.update(frame=f, secs=round(time.time() - t, 3), load1=round(la, 2))
        rows.append(r)
        if r['done'] or not ln:
            break
    try:
        p.stdin.write('\n')
        p.stdin.flush()
    except BrokenPipeError:
        pass
    so, se = p.communicate(timeout=1800)
    out = os.path.join(wd, output)
    ok = None
    if os.path.exists(out):
        ok = open(out, 'rb').read() == open(BUNDLE, 'rb').read()
    return dict(reader=rname, frames_given=frames, rows=rows, rc=p.returncode,
                stderr=se[-600:], closed=bool(rows and rows[-1]['done']),
                output_written=os.path.exists(out), output_equals_bundle=ok,
                process_secs=round(time.time() - t0, 3))


def pool_job(a):
    group, pool, frames, rname = a
    r = run(rname, frames, os.path.join(RUNS, 'pools', rname, pool))
    r.update(group=group, pool=pool)
    return r


def main():
    cmd = sys.argv[1]
    if cmd == 'render':
        os.makedirs(RND, exist_ok=True)
        with ProcessPoolExecutor(8) as ex:
            for n, s in ex.map(cam, renders()):
                print(n, s, flush=True)
        side = json.load(open(frame('ring-s1-p0')[:-4] + '.json'))
        touched = sorted({tuple(b) for d in side['damage'] for b in d.get('blocks_touched', [])})
        bes = [tuple(json.load(open(os.path.join(PAGES, 'page_p0.json')))['bullseyes'][k]['block']) for k in RING_BE]
        print('ring: blocks touched', len(touched), 'bullseyes touched', [b for b in bes if b in touched])
    elif cmd == 'pools':
        jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        args = [(g, p, f, r) for g, p, f in pools() for r in ORDER]
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(pool_job, args):
                print(r['pool'], r['reader'], [(x['bullseyes'], x['blocks'], x['held']) for x in r['rows']],
                      'closed' if r['closed'] else 'open', 'rc', r['rc'], r['output_equals_bundle'], flush=True)
                res.append(r)
        json.dump(dict(n2=N2, b2=B2, jobs=jobs, runs=res), open(os.path.join(OUT, 'pools.json'), 'w'), indent=1)
    elif cmd == 'loo':
        jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 6
        names = [n for n, _, _ in renders() if n.startswith(('edge', 'q045'))]
        args = [('loo', n, [n], 'without_' + k) for n in names for k in LOO]
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(pool_job, args):
                x = r['rows'][0]
                print(r['pool'], r['reader'], x['bullseyes'], x['blocks'], x['held'], 'rc', r['rc'], flush=True)
                res.append(r)
        json.dump(dict(runs=res), open(os.path.join(OUT, 'loo.json'), 'w'), indent=1)
    elif cmd == 'ring15':
        n = 'ring15-s1-p0'
        cam((n, 0, NOM + ['--blur', '0.30', '--seed', '1'] + ring_damage(tuple(range(15)))))
        side = json.load(open(frame(n)[:-4] + '.json'))
        touched = sorted({tuple(b) for d in side['damage'] for b in d.get('blocks_touched', [])})
        bes = {tuple(b['block']) for b in json.load(open(os.path.join(PAGES, 'page_p0.json')))['bullseyes']}
        print('ring15: blocks touched', len(touched), 'bullseyes touched', sorted(bes & set(touched)))
        res = []
        for rname in ORDER:
            r = run(rname, [n], os.path.join(RUNS, 'alone', rname, n))
            x = r['rows'][0]
            print(n, rname, x['bullseyes'], x['blocks'], x['held'], x['secs'], 'rc', r['rc'], 'load', x['load1'])
            res.append(r)
        json.dump(dict(blocks_touched=len(touched), runs=res), open(os.path.join(OUT, 'ring15.json'), 'w'), indent=1)
    elif cmd == 'control':
        p1 = os.path.join(PAGES, 'page_p1.nominal-b030.pgm')
        res = []
        for rname in ORDER:
            r = run(rname, ['clean-s1-p0', p1], os.path.join(RUNS, 'control', rname))
            print(rname, [(x['bullseyes'], x['blocks'], x['held'], x['done']) for x in r['rows']], 'rc', r['rc'],
                  'output == bundle/b.py:', r['output_equals_bundle'], flush=True)
            res.append(r)
        json.dump(dict(runs=res), open(os.path.join(OUT, 'control.json'), 'w'), indent=1)
    elif cmd == 'alone':
        names = [n for n, _, _ in renders()]
        res = []
        for i, n in enumerate(names):
            order = ORDER[i % 3:] + ORDER[:i % 3]
            for rname in order:
                r = run(rname, [n], os.path.join(RUNS, 'alone', rname, n))
                r.update(order=order)
                x = r['rows'][0]
                print(n, rname, x['bullseyes'], x['blocks'], x['held'], x['secs'], 'rc', r['rc'], 'load', x['load1'],
                      flush=True)
                res.append(r)
        json.dump(dict(n2=N2, b2=B2, runs=res), open(os.path.join(OUT, 'alone.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
