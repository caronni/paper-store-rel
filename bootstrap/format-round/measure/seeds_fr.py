#!/usr/bin/env python3
"""seeds_fr.py -- false seeds and true bullseyes, per capture, per format-round
configuration (never typed; measurement only).

For each capture alone, in process (as changeset/run_sets.slots runs a text:
the loader's definitions + the typed text exec'd up to its main loop):
  1. the finder's candidate list is recorded by a spy on dd (nothing else
     wrapped); every candidate is mapped through the capture's
     homography_grid_modules_to_px (a loupe grid PGM: one pixel per module,
     six white modules of border) to grid modules and called TRUE when it is
     within one module (Euclidean) of the centre of a bullseye block's module
     (0,0), (17 bj + 9.5, 17 bi + 9.5); every other candidate is a FALSE seed;
  2. the header as the capture reads it alone (fm with e = b'');
  3. the walk (wk) from every seed, the header given as the page's own when
     the capture does not read it (the slot pass's 'known'): a spy on the
     block read (rb) records each read's seed index s[5][0] and outcome
     (accepted / white / failed); a seed STARTED A WALK when a read carries
     its index; the chunks held = the accepted reads' chunk ids;
  4. the counterfactual: the same capture with the finder's list filtered to
     its TRUE seeds (fm and wk re-run in a fresh namespace) -> chunks held;
     cost = chunks(true seeds only) - chunks(as found).
True bullseyes in frame: the bullseye centres inside the image, less those
the render's damage records destroy (be:...) and, for the one-bullseye
renders, the 14 destroyed by name.

  python seeds_fr.py run GROUP [JOBS] [CFG ...]   GROUP = sets | edge | onebull
                                                  -> build/format-round/seeds/GROUP-CFG.json
"""
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fr_common as C   # noqa: E402
import render as R   # noqa: E402

sys.path.insert(0, os.path.join(C.BOOT, 'r2reader', 'changeset'))
OUTD = os.path.join(C.OUT, 'seeds')
BES = [(bi, bj) for bi in (2, 14, 26) for bj in (2, 8, 14)] + [(bi, bj) for bi in (8, 20) for bj in (5, 11, 17)]


def frames(group, cfg):
    """[(case label, frame path, page json path, destroyed bullseyes)]"""
    out = []
    if group == 'sets':
        ws = R.ws_for(cfg)
        seen = set()
        for st in ws.sets().values():
            for fr in st.values():
                for f in fr:
                    if f not in seen:
                        seen.add(f)
                        out.append(f)
        res = []
        for f in out:
            if f.endswith('.txt'):
                pgm = os.path.join(C.OUT, 'runs-sets', cfg, 'grids', os.path.basename(f)[:-4] + '.pgm')
                res.append((os.path.basename(f)[:-4], pgm, os.path.join(ws.PAGES, 'one.json'), []))
            else:
                res.append((os.path.relpath(f, os.path.join(C.SETS_OUT, cfg))[:-4], f, None, None))
        return res
    if group == 'edge':
        return [(n, os.path.join(C.OUT, 'edge', cfg, n + '.pgm'), None, None) for n, _, _ in R.edge_renders()]
    res = []
    for st in R.OB_SETTINGS:
        for v in ['clean'] + [f'{c}-{p}' for c in R.OB_CASES for p in ('ink', 'white')]:
            n = f'{st}-{v}'
            gone = [] if v == 'clean' else [b for b in BES if b != R.OB_CASES[v[0]]]
            res.append((n, os.path.join(C.OUT, 'onebull', cfg, n + '.pgm'), None, gone))
    return res


def truth(fpath, pjson, gone):
    """-> (px -> grid modules, [(bullseye, centre px)] in frame, page sidecar)"""
    tj = None
    if pjson is None:
        tj = json.load(open(fpath[:-4] + '.json'))
        pjson = tj['page_sidecar']
        Hm = np.array(tj['homography_grid_modules_to_px'])
        w, h = tj['size_px']
        if gone is None:
            gone = [tuple(b) for d in tj['damage'] for b in d.get('bullseyes', []) if d['kind'].startswith('be')]
    else:
        Hm = np.array([[1.0, 0, 6], [0, 1, 6], [0, 0, 1]])
        hd = open(fpath, 'rb').read(64).split()
        w, h = int(hd[1]), int(hd[2])
    Hi = np.linalg.inv(Hm)

    def to_mod(x, y):
        u = Hi @ [x + 0.5, y + 0.5, 1.0]
        return u[0] / u[2], u[1] / u[2]
    inf = []
    for bi, bj in BES:
        v = Hm @ [17 * bj + 9.5, 17 * bi + 9.5, 1]
        x, y = v[0] / v[2] - 0.5, v[1] / v[2] - 0.5
        if 0 <= x < w and 0 <= y < h and (bi, bj) not in set(map(tuple, gone or [])):
            inf.append((bi, bj))
    return to_mod, inf, json.load(open(pjson))


def classify(seeds, to_mod):
    out = []
    for s in seeds:
        mx, my = to_mod(s[-3] / 16, s[-2] / 16)
        best = min(BES, key=lambda b: (mx - 17 * b[1] - 9.5) ** 2 + (my - 17 * b[0] - 9.5) ** 2)
        d = math.hypot(mx - 17 * best[1] - 9.5, my - 17 * best[0] - 9.5)
        bj, bi = round((mx - 9.5) / 17), round((my - 9.5) / 17)
        out.append(dict(mod=[round(mx, 2), round(my, 2)], true=d <= 1.0, bullseye=list(best) if d <= 1.0 else None,
                        dist=round(d, 2), near_block=[bi, bj], off=[round(mx - 17 * bj - 9.5, 2),
                                                                     round(my - 17 * bi - 9.5, 2)]))
    return out


def one(kind, fpath, keep, known):
    """one pass: -> (seeds as found, header alone, walk record) with the finder's list
    filtered by keep (None = as found)."""
    import run_sets as RS
    N = C.NAMES[kind]
    ns = RS.ns_of(C.READER[kind])
    ns[N['h']], ns[N['j']], ns[N['z']] = ns[N['ld']](fpath)
    dd0, got = ns[N['dd']], []

    def dd(c):
        s = dd0(c)
        got.append(list(s))
        return [x for i, x in enumerate(s) if keep is None or i in keep]
    ns[N['dd']] = dd
    ns[N['e']] = b''
    (p, r), hdr = ns[N['fm']]()
    n_seeds = len(r)
    ns[N['e']] = hdr or known
    rb0, reads = ns[N['rb']], []

    def rb(s):
        x = rb0(s)
        reads.append((s[5][0], None if x is None else (b'' if not x else int.from_bytes(x[:2], 'big'))))
        return x
    ns[N['rb']] = rb
    acc = ns[N['wk']](p, r) if r else []
    return got[0] if got else [], bool(hdr), n_seeds, reads, acc


def job(a):
    group, cfg, label, fpath, pjson, gone = a
    kind = C.kind_of(cfg)
    to_mod, inf, side = truth(fpath, pjson, gone)
    known = bytes.fromhex(side['header']['bytes_hex'])
    seeds, hdr, n_seeds, reads, acc = one(kind, fpath, None, known)
    cl = classify(seeds, to_mod)
    true_idx = {i for i, c in enumerate(cl) if c['true']}
    found = sorted({tuple(c['bullseye']) for c in cl if c['true']})
    started = {q for q, _ in reads}
    fq = [i for i, c in enumerate(cl) if not c['true']]
    fr = [(q, x) for q, x in reads if q in set(fq)]
    chunks = {x for x in (int.from_bytes(b[:2], 'big') for b in acc)}
    rec = dict(group=group, cfg=cfg, case=label, frame=os.path.relpath(fpath, C.OUT), seeds=len(seeds),
               true_seeds=len(true_idx), false_seeds=len(fq), bullseyes_in_frame=len(inf),
               true_found_in_frame=len(set(found) & set(inf)), found=[list(b) for b in found],
               missed_in_frame=[list(b) for b in sorted(set(inf) - set(found))],
               header_alone=hdr, false_started_walk=sum(q in started for q in fq),
               false_walk_reads=len(fr), false_walk_accepted=sum(isinstance(x, int) for _, x in fr),
               false_walk_white=sum(x == b'' for _, x in fr), blocks=len(acc), chunks=len(chunks),
               seed_detail=cl)
    if fq:
        s2, h2, n2, r2, acc2 = one(kind, fpath, true_idx, known)
        ch2 = {int.from_bytes(b[:2], 'big') for b in acc2}
        rec.update(cf_blocks=len(acc2), cf_chunks=len(ch2), cf_header_alone=h2,
                   cost_chunks=len(ch2) - len(chunks), lost=sorted(ch2 - chunks), gained=sorted(chunks - ch2))
    else:
        rec.update(cf_blocks=len(acc), cf_chunks=len(chunks), cf_header_alone=hdr, cost_chunks=0, lost=[], gained=[])
    return rec


def run(group, jobs, cfgs):
    os.makedirs(OUTD, exist_ok=True)
    args = [(group, cfg) + f for cfg in cfgs for f in frames(group, cfg)]
    res = {cfg: [] for cfg in cfgs}
    with ProcessPoolExecutor(jobs) as ex:
        for r in ex.map(job, args):
            res[r['cfg']].append(r)
            print(f"{r['cfg']:14s} {r['case']:34s} seeds {r['seeds']:3d} true {r['true_seeds']:2d} false "
                  f"{r['false_seeds']:3d} found {r['true_found_in_frame']}/{r['bullseyes_in_frame']} hdr "
                  f"{int(r['header_alone'])} walks {r['false_started_walk']} reads {r['false_walk_reads']} "
                  f"chunks {r['chunks']} cf {r['cf_chunks']} cost {r['cost_chunks']}", flush=True)
    for cfg in cfgs:
        C.jdump(res[cfg], os.path.join(OUTD, f'{group}-{cfg}.json'))


if __name__ == '__main__':
    a = sys.argv[1:]
    assert a[0] == 'run'
    jn = int(a[2]) if len(a) > 2 and a[2].isdigit() else 4
    cfgs = [x for x in a[2:] if not x.isdigit()] or C.CONFIGS
    run(a[1], jn, cfgs)
