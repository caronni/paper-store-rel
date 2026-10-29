#!/usr/bin/env python3
"""edge_fr.py -- RESULTS-2026-10-22 §11's envelope edge and sigma 0.45
quarters, and §14's one-bullseye renders, per format-round configuration
(never typed).

r2reader/changeset/edge.py is imported unchanged for its run arrangement
(E.run: the text as a process in a fresh directory, N2/B2 = the stage-1 lower
build's, its order tuple fix, build/stage1/lower/b.py under the primer name,
a close checked against build/bundle/b.py); the renders are this round's
(render.py edge / onebull: the configuration's stage-1 lower pages, the same
camera arguments).  The pages of every configuration carry the stage-1 lower
payload, so every text closes to the same bundle.

  python edge_fr.py pools [JOBS]    4 edge pools (seeds 1-4, p0 p1 p2) + 6 quarter pools
                                    (seeds 1-2 x page, tl tr bl br) + ring-s1-p0 + clean-s1-p0,
                                    every configuration -> edge/pools.json
  python edge_fr.py alone [JOBS]    every edge render alone -> edge/alone.json
  python edge_fr.py onebull [JOBS]  every one-bullseye render alone -> onebull/alone.json
  python edge_fr.py walls           paired walls: a few frames, one process at a time, the
                                    eight configurations alternating, order rotated, 3 rounds
                                    -> walls.json
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

sys.path.insert(0, os.path.join(C.BOOT, 'r2reader', 'changeset'))
import edge as E   # noqa: E402

E.READERS = {cfg: (C.READER[C.kind_of(cfg)], 'b.py', 'c.py') for cfg in C.CONFIGS}
E.RUNS = os.path.join(C.OUT, 'runs-edge')


def edge_frame(cfg, n):
    return os.path.join(C.OUT, 'edge', cfg, n + '.pgm')


def pool_job(a):
    group, pool, frames, cfg, sub = a
    r = E.run(cfg, frames, os.path.join(E.RUNS, sub, cfg, pool))
    r.update(group=group, pool=pool, cfg=cfg)
    for x in r['rows']:
        x['frame'] = os.path.basename(x['frame'])[:-4] if x['frame'].endswith('.pgm') else x['frame']
    import shutil
    shutil.rmtree(os.path.join(E.RUNS, sub, cfg, pool), ignore_errors=True)
    return r


def pools_args():
    out = []
    for cfg in C.CONFIGS:
        for g, p, fs in E.pools():
            out.append((g, p, [edge_frame(cfg, f) for f in fs], cfg, 'pools'))
    return out


def alone_args(kind):
    out = []
    if kind == 'edge':
        names = [n for n, _, _ in E.renders()]
        for cfg in C.CONFIGS:
            for n in names:
                out.append(('alone', n, [edge_frame(cfg, n)], cfg, 'alone'))
    else:
        import render as R
        for cfg in C.CONFIGS:
            for st in R.OB_SETTINGS:
                for v in ['clean'] + [f'{c}-{p}' for c in R.OB_CASES for p in ('ink', 'white')]:
                    n = f'{st}-{v}'
                    out.append(('onebull', n, [os.path.join(C.OUT, 'onebull', cfg, n + '.pgm')], cfg, 'onebull'))
    return out


def go(args, jobs, path):
    res = []
    with ProcessPoolExecutor(jobs) as ex:
        for r in ex.map(pool_job, args):
            print(r['cfg'], r['pool'], [(x['bullseyes'], x['blocks'], x['held']) for x in r['rows']],
                  'closed' if r['closed'] else 'open', 'rc', r['rc'], r['output_equals_bundle'], flush=True)
            res.append(r)
    C.jdump(dict(n2=E.N2, b2=E.B2, jobs=jobs, runs=res), path)


WALL_FRAMES = ('clean-s1-p0', 'edge-s1-p0', 'q045-s1-p0-tl')


def walls():
    res = []
    for rd in range(3):
        for k, f in enumerate(WALL_FRAMES):
            order = C.CONFIGS[(rd * 3 + k) % 8:] + C.CONFIGS[:(rd * 3 + k) % 8]
            if rd % 2:
                order = order[::-1]
            for cfg in order:
                r = pool_job(('walls', f'{f}-r{rd}', [edge_frame(cfg, f)], cfg, 'walls'))
                x = r['rows'][0]
                print(rd, f, cfg, x['secs'], x['load1'], x['blocks'], x['held'], flush=True)
                res.append(dict(round=rd, frame=f, cfg=cfg, secs=x['secs'], load1=x['load1'], blocks=x['blocks'],
                                held=x['held'], process_secs=r['process_secs']))
    C.jdump(res, os.path.join(C.OUT, 'walls.json'))


if __name__ == '__main__':
    cmd = sys.argv[1]
    jn = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if cmd == 'pools':
        go(pools_args(), jn, os.path.join(C.OUT, 'edge', 'pools.json'))
    elif cmd == 'alone':
        go(alone_args('edge'), jn, os.path.join(C.OUT, 'edge', 'alone.json'))
    elif cmd == 'onebull':
        go(alone_args('onebull'), jn, os.path.join(C.OUT, 'onebull', 'alone.json'))
    elif cmd == 'walls':
        walls()
