#!/usr/bin/env python3
"""render.py -- every capture of the format round's measurement, per
configuration, with bootstrap/r2/camera.py unchanged and the camera arguments
of record (never typed).

  python render.py sets [JOBS] [CFG ...]     the w4 acceptance sets' frames:
      w1f4/  every frame w4_sets.sets() names from build/w4/w1f4 (its camera
             arguments from build/w4/w1f4/renders.json), page = the cfg's
             pages/{one,two_p0,two_p1};
      sets4/ w4_sets.EXTRA (camera) + the two loupe grids (w4_sets.loupe, the
             cfg's one.grid.txt: a module grid, so X-dot's == X-coarse's);
      p2f4/  the ten page_p2 frames, the arguments recorded in the frozen
             build/w4/p2f4/page_p2.NAME.json (w4_lastpage.render's way).
  python render.py edge [JOBS] [CFG ...]     RESULTS §11's renders (changeset
      r2reader/changeset/edge.py renders(): edge spm 1.5 blur 0.40 seeds 1-4,
      the sigma 0.45 quarters spm 2 seeds 1-2, ring-s1-p0, clean-s1-p0) of the
      cfg's stage-1 lower pages (build/format-round/pages/CFG/page_p*).
  python render.py onebull [JOBS] [CFG ...]  §14's one-bullseye renders (one_bull.py):
      survivors A (14,8) B (2,2) C (26,14), the other 14 bullseye interiors
      inked (--damage be:LIST) or blanked to paper (a PBM copy), n030 / n045
      / n045s2 / s7, plus the clean page at each setting.
  python render.py check                     record-coarse == the frozen renders,
      byte for byte (build/w4/{w1f4,sets4,p2f4}, build/changeset/edge/renders,
      build/changeset/onebull/renders).
Outputs: build/format-round/{sets,edge,onebull}/CFG/.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402

sys.path.insert(0, os.path.join(C.BOOT, 'r2reader', 'diet'))
sys.path.insert(0, os.path.join(C.BOOT, 'r2'))
W1F4 = os.path.join(C.BOOT, 'build', 'w4', 'w1f4')
SETS4 = os.path.join(C.BOOT, 'build', 'w4', 'sets4')
P2F4 = os.path.join(C.BOOT, 'build', 'w4', 'p2f4')
P2_FRAMES = ('q-tl', 'q-tr', 'q-bl', 'q-br', 'centre', 'q-br-2spm', 'nominal-b045', 'hard-b030',
             'nominal-b030', 'flatbed300')
NOM = ['--preset', 'nominal']
EDGE = NOM + ['--spm', '1.5', '--blur', '0.40']
QUAR = NOM + ['--spm', '2', '--blur', '0.45']
RING_BE = (3, 4, 7)
RING_R_MM = 3.0
OB_CASES = {'A': (14, 8), 'B': (2, 2), 'C': (26, 14)}
OB_SETTINGS = {
    'n030': ['--preset', 'nominal', '--blur', '0.30', '--seed', '1'],
    'n045': ['--preset', 'nominal', '--blur', '0.45', '--seed', '1'],
    'n045s2': ['--preset', 'nominal', '--blur', '0.45', '--seed', '2'],
    's7': ['--preset', 'nominal', '--spm', '7', '--blur', '0.30', '--seed', '1'],
}


def cfg_dirs(cfg):
    d = os.path.join(C.SETS_OUT, cfg)
    return dict(pages=os.path.join(d, 'pages'), w1f4=os.path.join(d, 'w1f4'), sets4=os.path.join(d, 'sets4'),
                p2f4=os.path.join(d, 'p2f4'))


def ws_for(cfg):
    """diet/w4_sets with its frame roots pointed at the cfg's renders."""
    import w4_sets as ws
    d = cfg_dirs(cfg)
    ws.F, ws.PAGES, ws.SETS, ws.P2 = d['w1f4'], d['pages'], d['sets4'], d['p2f4']
    return ws


def cam(job):
    out, page, side, args = job
    import camera
    os.makedirs(os.path.dirname(out), exist_ok=True)
    camera.main([page, out, '--sidecar', side] + args)
    return out


def set_jobs(cfg):
    ws = ws_for(cfg)
    d = cfg_dirs(cfg)
    rj = {r['name']: r for r in json.load(open(os.path.join(W1F4, 'renders.json')))['renders']}
    names = set()
    for st in ws.sets().values():
        for fr in st.values():
            for f in fr:
                if os.path.dirname(f) == d['w1f4']:
                    names.add(os.path.basename(f)[:-4])
    jobs = []
    for n in sorted(names):
        r = rj[n]
        page = os.path.join(d['pages'], os.path.basename(r['page']))
        jobs.append((os.path.join(d['w1f4'], n + '.pgm'), page + '.pbm', page + '.json', r['camera_args']))
    for n, (page, argv) in ws.EXTRA.items():
        pg = os.path.join(d['pages'], page)
        jobs.append((os.path.join(d['sets4'], n + '.pgm'), pg + '.pbm', pg + '.json', argv))
    import camera
    for n in P2_FRAMES:
        t = json.load(open(os.path.join(P2F4, f'page_p2.{n}.json')))
        a = ['--preset', t['preset'], '--seed', str(t['seed']), '--rot90', str(t.get('rot90', 0))]
        for k in camera.PARAMS:
            a += [f'--{k}', repr(t['params'][k])]
        if t.get('crop_frac'):
            a += ['--crop'] + [repr(v) for v in t['crop_frac']]
        pg = os.path.join(d['p2f4'], 'page_p2')
        jobs.append((os.path.join(d['p2f4'], f'page_p2.{n}.pgm'), pg + '.pbm', pg + '.json', a))
    return jobs


def loupes(cfg):
    ws = ws_for(cfg)
    os.makedirs(ws.SETS, exist_ok=True)
    ws.loupe('one.loupe02-s1', 'one', 0.002, 1)
    ws.loupe('one.loupe02-s2', 'one', 0.002, 2)


def ring_damage(side, bes=RING_BE):
    out = []
    for k in bes:
        bi, bj = side['bullseyes'][k]['block']
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di or dj:
                    out += ['--damage', f'blot-at:{17 * (bj + dj) + 8.5}:{17 * (bi + di) + 8.5}:{RING_R_MM}']
    return out


def edge_renders():
    r = []
    for s in (1, 2, 3, 4):
        for p in (0, 1, 2):
            r.append((f'edge-s{s}-p{p}', p, EDGE + ['--seed', str(s)]))
    for s in (1, 2):
        for p in (0, 1, 2):
            for q in ('tl', 'tr', 'bl', 'br'):
                r.append((f'q045-s{s}-p{p}-{q}', p, QUAR + ['--frame', q, '--seed', str(s)]))
    r.append(('ring-s1-p0', 0, None))
    r.append(('clean-s1-p0', 0, NOM + ['--blur', '0.30', '--seed', '1']))
    return r


def edge_jobs(cfg):
    pg = os.path.join(C.STAGE1_PAGES, cfg)
    side0 = json.load(open(os.path.join(pg, 'page_p0.json')))
    jobs = []
    for n, p, a in edge_renders():
        if a is None:
            a = NOM + ['--blur', '0.30', '--seed', '1'] + ring_damage(side0)
        jobs.append((os.path.join(C.OUT, 'edge', cfg, n + '.pgm'), os.path.join(pg, f'page_p{p}.pbm'),
                     os.path.join(pg, f'page_p{p}.json'), a))
    return jobs


def read_pbm(path):
    raw = open(path, 'rb').read()
    p1 = raw.index(b'\n') + 1
    p2 = raw.index(b'\n', p1) + 1
    w, h = map(int, raw[p1:p2].split())
    return raw[:p2], np.unpackbits(np.frombuffer(raw[p2:], dtype=np.uint8)).reshape(h, -1)


def white_page(cfg, case):
    pg = os.path.join(C.STAGE1_PAGES, cfg, 'page_p0')
    out = os.path.join(C.OUT, 'onebull', cfg, 'pages', f'page_p0-{case}-white.pbm')
    S = json.load(open(pg + '.json'))
    hdr, bits = read_pbm(pg + '.pbm')
    md, x0, y0 = S['module_dots'], S['x0_dots'], S['y0_dots']
    for b in S['bullseyes']:
        bi, bj = b['block']
        if (bi, bj) == OB_CASES[case]:
            continue
        c0, r0 = 17 * bj + 1, 17 * bi + 1
        bits[y0 + md * r0:y0 + md * (r0 + 16), x0 + md * c0:x0 + md * (c0 + 16)] = 0
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'wb').write(hdr + np.packbits(bits, axis=1).tobytes())
    return out


def onebull_jobs(cfg):
    pg = os.path.join(C.STAGE1_PAGES, cfg, 'page_p0')
    S = json.load(open(pg + '.json'))
    bes = [tuple(b['block']) for b in S['bullseyes']]
    jobs = []
    for st, args in OB_SETTINGS.items():
        out = lambda v: os.path.join(C.OUT, 'onebull', cfg, f'{st}-{v}.pgm')   # noqa: E731
        jobs.append((out('clean'), pg + '.pbm', pg + '.json', args))
        for case, blk in OB_CASES.items():
            surv = [i for i, b in enumerate(bes) if b != blk]
            jobs.append((out(f'{case}-ink'), pg + '.pbm', pg + '.json',
                         args + ['--damage', 'be:' + '+'.join(map(str, surv))]))
            jobs.append((out(f'{case}-white'), white_page(cfg, case), pg + '.json', args))
    return jobs


def run(kind, jobs_n, cfgs):
    jobs = []
    for cfg in cfgs:
        if kind == 'sets':
            loupes(cfg)
            jobs += set_jobs(cfg)
        elif kind == 'edge':
            jobs += edge_jobs(cfg)
        else:
            jobs += onebull_jobs(cfg)
    print(kind, len(jobs), 'renders', flush=True)
    with ProcessPoolExecutor(jobs_n) as ex:
        for i, o in enumerate(ex.map(cam, jobs)):
            if i % 25 == 0:
                print(i, os.path.relpath(o, C.OUT), flush=True)
    print(kind, 'done', flush=True)


def check():
    bad = n = 0
    pairs = []
    d = cfg_dirs('record-coarse')
    for sub, ref in (('w1f4', W1F4), ('sets4', SETS4), ('p2f4', P2F4)):
        for f in sorted(os.listdir(d[sub])):
            if f.endswith(('.pgm', '.txt')) and not f.endswith('.grid.txt'):
                pairs.append((os.path.join(d[sub], f), os.path.join(ref, f)))
    ed = os.path.join(C.OUT, 'edge', 'record-coarse')
    for f in sorted(os.listdir(ed) if os.path.isdir(ed) else []):
        if f.endswith('.pgm'):
            pairs.append((os.path.join(C.OUT, 'edge', 'record-coarse', f),
                          os.path.join(C.BOOT, 'build', 'changeset', 'edge', 'renders', f)))
    ob = os.path.join(C.OUT, 'onebull', 'record-coarse')
    if os.path.isdir(ob):
        for f in sorted(os.listdir(ob)):
            if f.endswith('.pgm'):
                pairs.append((os.path.join(ob, f), os.path.join(C.BOOT, 'build', 'changeset', 'onebull', 'renders', f)))
    for a, b in pairs:
        if not os.path.exists(b):
            print('no frozen counterpart', os.path.relpath(b, C.BOOT))
            continue
        n += 1
        if C.sha(a) != C.sha(b):
            bad += 1
            print('DIFFERS', os.path.relpath(a, C.OUT), os.path.relpath(b, C.BOOT))
    print(f'check: {n} renders compared, {bad} differ')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'check':
        check()
    else:
        jn = int(a[1]) if len(a) > 1 and a[1].isdigit() else 6
        cfgs = [x for x in a[1:] if not x.isdigit()] or C.CONFIGS
        run(a[0], jn, cfgs)
