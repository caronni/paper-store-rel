#!/usr/bin/env python3
"""one_bull.py -- RESULTS-2026-10-22 §14: one bullseye left on the page.

From the stage-1 page build/stage1/lower/r2/page_p0.pbm, 14 of the 15
bullseye blocks are destroyed (their 16 x 16 interior: inked with camera.py's
own --damage be:LIST, or blanked to paper in a copy of the PBM; the shared
frame lines stay, they belong to the neighbours' timing frames too), leaving
  A (14,8)  the central bullseye   (farthest block 27 steps)
  B (2,2)   the corner bullseye    (farthest block 45 steps)
  C (26,14) a bottom bullseye      (farthest block 40 steps)
rendered whole page, no crop, with r2/camera.py at
  n030  --preset nominal --blur 0.30 --seed 1        (spm 2)
  n045  --preset nominal --blur 0.45 --seed 1        (spm 2)
  s7    --preset nominal --spm 7 --blur 0.30 --seed 1
plus the clean page at each setting.  Beyond the brief (the n045 seed-1 finder
misses A, B and C on the clean page): D (20,11) and E (26,2) at n045, and
  n045s2 --preset nominal --blur 0.45 --seed 2       (A, B, C)
Every reader text reads every render
alone, one frame:
  probe  in-process: the text's definitions exec'd (everything before its
         main loop), its block read (rb, renamed per text by --names maps) and
         nothing else wrapped by a spy that records, per call, the position,
         the walk key, the outcome (accepted / white test / CRC fail) and
         whether the walk placed the block (the queue grew by 4 before the
         next read); every queued state's position is mapped to the nearest
         block centre through the render's homography -> probe.json
  alone  the text as a process (r2reader/changeset/edge.py's E.run, its N2/B2
         and order-tuple fix), one process at a time, the texts alternating,
         order rotated per render -> alone.json (counts + paired walls)
  tables markdown from the two files

  python one_bull.py render | probe [JOBS] | alone | tables
Outputs: build/changeset/onebull/ (gitignored).  The four texts are copied to
onebull/texts/ at the first command and every run reads the copies.
"""
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import edge as E   # noqa: E402

OUT = os.path.join(BOOT, 'build', 'changeset', 'onebull')
TXT = os.path.join(OUT, 'texts')
RND = os.path.join(OUT, 'renders')
PGS = os.path.join(OUT, 'pages')
CS = os.path.join(BOOT, 'build', 'changeset')
SRC = {   # name: (source text, names map file or None, primer, output)
    'record': (os.path.join(CS, 'reader_before.py'), None, 'r.py', 'b.py'),
    'ruled': (os.path.join(BOOT, 'r2reader', 'reader_lite_v1.py'), os.path.join(CS, 'rw', 'names.json'),
              'b.py', 'c.py'),
    'alternative': (os.path.join(HERE, 'reader_nod.py'), os.path.join(CS, 'nod', 'rw', 'search.json'),
                    'b.py', 'c.py'),
    'union': (os.path.join(HERE, 'reader_both.py'), os.path.join(CS, 'both', 'rw', 'search.json'),
              'b.py', 'c.py'),
}
ORDER = [k for k in SRC if os.path.exists(SRC[k][0])]
KEYS = ('rb', 'ld', 'fm', 'wk', 'h', 'j', 'z', 'e', 'f', 'm')
PAGE = os.path.join(E.PAGES, 'page_p0.pbm')
SIDE = os.path.join(E.PAGES, 'page_p0.json')
S = json.load(open(SIDE))
BES = [tuple(b['block']) for b in S['bullseyes']]
CASES = {'A': (14, 8), 'B': (2, 2), 'C': (26, 14), 'D': (20, 11), 'E': (26, 2)}
SETTINGS = {
    'n030': ['--preset', 'nominal', '--blur', '0.30', '--seed', '1'],
    'n045': ['--preset', 'nominal', '--blur', '0.45', '--seed', '1'],
    's7': ['--preset', 'nominal', '--spm', '7', '--blur', '0.30', '--seed', '1'],
    'n045s2': ['--preset', 'nominal', '--blur', '0.45', '--seed', '2'],
}
# beyond the brief: at n045 seed 1 the finder misses A, B and C on the CLEAN page
# too, so n045 adds D and E (found there) and n045s2 re-draws the capture
VARIANTS = {st: ['clean'] + [f'{c}-{p}' for c in cs for p in ('ink', 'white')]
            for st, cs in (('n030', 'ABC'), ('n045', 'ABCDE'), ('s7', 'ABC'), ('n045s2', 'ABC'))}
DATA = {tuple(b): c for b, c in zip(S['slot_block'], S['slot_chunk']) if c is not None}
BH, BW = S['BH'], S['BW']


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def freeze():
    os.makedirs(TXT, exist_ok=True)
    for k in ORDER:
        dst = os.path.join(TXT, k + '.py')
        if not os.path.exists(dst):
            shutil.copy2(SRC[k][0], dst)
        nm = os.path.join(TXT, k + '.names.json')
        if not os.path.exists(nm):
            if SRC[k][1]:
                m = json.load(open(SRC[k][1]))
                m = m.get('names', m)
            else:
                m = {x: x for x in KEYS}
            json.dump({x: m[x] for x in KEYS}, open(nm, 'w'), indent=1)
    E.READERS = {k: (os.path.join(TXT, k + '.py'), SRC[k][2], SRC[k][3]) for k in ORDER}
    E.RUNS = os.path.join(OUT, 'runs')


def names(k):
    return json.load(open(os.path.join(TXT, k + '.names.json')))


def survivors(case):
    return [i for i, b in enumerate(BES) if b != CASES[case]]


def white_page(case):
    """page_p0.pbm with the 16 x 16 interiors of the 14 other bullseyes set to paper."""
    out = os.path.join(PGS, f'page_p0-{case}-white.pbm')
    if os.path.exists(out):
        return out
    raw = open(PAGE, 'rb').read()
    p1 = raw.index(b'\n') + 1
    p2 = raw.index(b'\n', p1) + 1
    w, h = map(int, raw[p1:p2].split())
    bits = np.unpackbits(np.frombuffer(raw[p2:], dtype=np.uint8)).reshape(h, -1)
    md, x0, y0 = S['module_dots'], S['x0_dots'], S['y0_dots']
    for k in survivors(case):
        bi, bj = BES[k]
        c0, r0 = 17 * bj + 1, 17 * bi + 1
        bits[y0 + md * r0:y0 + md * (r0 + 16), x0 + md * c0:x0 + md * (c0 + 16)] = 0
    os.makedirs(PGS, exist_ok=True)
    open(out, 'wb').write(raw[:p2] + np.packbits(bits, axis=1).tobytes())
    return out


def render_jobs():
    jobs = []
    for st, args in SETTINGS.items():
        for v in VARIANTS[st]:
            name = f'{st}-{v}'
            if v == 'clean':
                jobs.append((name, PAGE, args))
            else:
                case, pol = v.split('-')
                if pol == 'ink':
                    jobs.append((name, PAGE, args + ['--damage', 'be:' + '+'.join(map(str, survivors(case)))]))
                else:
                    jobs.append((name, white_page(case), args))
    return jobs


def frame(name):
    return os.path.join(RND, name + '.pgm')


def cam(job):
    name, page, args = job
    t = time.time()
    subprocess.run([E.PY, E.CAM, page, frame(name), '--sidecar', SIDE] + args, check=True, capture_output=True)
    return name, round(time.time() - t, 1)


def geometry(name):
    tj = json.load(open(frame(name)[:-4] + '.json'))
    Hm = np.array(tj['homography_grid_modules_to_px'])

    def px(c, r):
        v = Hm @ [c, r, 1]
        return v[0] / v[2] - 0.5, v[1] / v[2] - 0.5
    cen = {(bi, bj): px(17 * bj + 9.5, 17 * bi + 9.5) for bi in range(BH) for bj in range(BW)}
    a, b = px(9.5, 9.5), px(26.5, 9.5)
    return cen, math.hypot(b[0] - a[0], b[1] - a[1])


def nearest(cen, pitch, x, y):
    q = min(cen, key=lambda k: (cen[k][0] - x) ** 2 + (cen[k][1] - y) ** 2)
    return q, math.hypot(cen[q][0] - x, cen[q][1] - y) / pitch


def probe(arg):
    """one text on one render, in process -> the per-block record."""
    tname, rname = arg
    freeze()   # a spawned worker
    N = names(tname)
    src = E.reader_src(tname)
    ns = {}
    exec(compile(src.split('\nwhile ')[0], tname, 'exec'), ns)
    for k in ('rb', 'ld', 'fm', 'wk', 'f'):
        assert callable(ns[N[k]]), (tname, k)
    M = ns[N['m']]
    assert len(M) == 256 and M[0] == (-8, -8), (tname, 'm')
    t0 = time.time()
    ns[N['h']], ns[N['j']], ns[N['z']] = ns[N['ld']](frame(rname))
    ns[N['e']] = b''
    o, hdr = ns[N['fm']]()
    ns[N['e']] = hdr
    n_be = len(o[1])
    calls = []
    queue = o[1]
    rb, f = ns[N['rb']], ns[N['f']]

    def spy(s):
        n0 = len(queue)
        out = rb(s)
        if out:
            kind = 'ok'
        else:
            r, t = f(s)
            kind = 'white' if sum(r[x, y] < t for x, y in M) <= 3 else 'crc'
        calls.append(dict(x=s[0] / 16, y=s[1] / 16, key=list(s[5]), kind=kind, qlen=n0,
                          chunk=int.from_bytes(out[:2], 'big') if out else None))
        return out
    accepted = []
    if hdr:
        ns[N['rb']] = spy
        accepted = ns[N['wk']](*o)
        ns[N['rb']] = rb
    wall = time.time() - t0
    for i, c in enumerate(calls):   # placed: the queue grew by 4 before the next read
        nxt = calls[i + 1]['qlen'] if i + 1 < len(calls) else len(queue)
        c['placed'] = nxt - c['qlen'] == 4
        assert nxt - c['qlen'] in (0, 4), (tname, rname, nxt - c['qlen'])
    cen, pitch = geometry(rname)
    seeds = [list(nearest(cen, pitch, s[0] / 16, s[1] / 16)[0]) for s in o[1][:n_be]]
    queued = {}
    far = 0
    for s in queue:
        q, d = nearest(cen, pitch, s[0] / 16, s[1] / 16)
        if d < 0.5:
            queued[q] = queued.get(q, 0) + 1
        else:
            far += 1
    blocks = {}
    mism = 0
    maxoff = 0.0
    offgrid = {}
    for c in calls:
        q, d = nearest(cen, pitch, c['x'], c['y'])
        if d >= 0.5:
            k = c['kind'] + ('P' if c['placed'] else '')
            offgrid[k] = offgrid.get(k, 0) + 1
            continue
        maxoff = max(maxoff, d)
        b = blocks.setdefault(q, dict(calls=0, ok=0, white=0, crc=0, placed=0, chunk_ok=0))
        b['calls'] += 1
        b[c['kind']] += 1
        b['placed'] += c['placed']
        if c['kind'] == 'ok':
            if DATA.get(q) == c['chunk']:
                b['chunk_ok'] += 1
            else:
                mism += 1
    held = {int.from_bytes(x[:2], 'big') for x in accepted}
    return dict(text=tname, render=rname, bullseyes=n_be, seeds=seeds, offgrid_calls=offgrid,
                distinct_read=sum(1 for b in blocks.values() if b['ok']),
                header=bool(hdr), accepted=len(accepted), held=len(held),
                calls=len(calls), queued_states=len(queue), queued_far=far, chunk_mismatch=mism,
                max_call_offset_blocks=round(maxoff, 3), pitch_px=round(pitch, 3), secs=round(wall, 2),
                blocks={f'{k[0]},{k[1]}': v for k, v in blocks.items()},
                queued={f'{k[0]},{k[1]}': v for k, v in queued.items()})


def classify(P, rname):
    """per surviving data block: read / reached-failed (crc, white) / queued-not-read / never."""
    v = rname.split('-', 1)[1]
    if v == 'clean':
        seeds = BES
    else:
        seeds = [CASES[v.split('-')[0]]]
    out = []
    for q in DATA:
        k = f'{q[0]},{q[1]}'
        b = P['blocks'].get(k)
        dist = min(abs(q[0] - s[0]) + abs(q[1] - s[1]) for s in seeds)
        if b and b['ok']:
            st = 'read'
        elif b and b['crc']:
            st = 'crc'
        elif b and b['white']:
            st = 'white'
        elif k in P['queued']:
            st = 'queued'
        else:
            st = 'never'
        edge = q[0] in (0, BH - 1) or q[1] in (0, BW - 1)
        out.append(dict(block=list(q), dist=dist, state=st, edge=edge,
                        placed=bool(b and b['placed'])))
    return out


def main():
    cmd = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    freeze()
    if cmd == 'render':
        os.makedirs(RND, exist_ok=True)
        jobs = render_jobs()
        with ProcessPoolExecutor(int(sys.argv[2]) if len(sys.argv) > 2 else 4) as ex:
            for n, s in ex.map(cam, jobs):
                side = json.load(open(frame(n)[:-4] + '.json'))
                print(n, s, 's', side['out_sha256'][:12], 'damage', [d['kind'][:40] for d in side['damage']],
                      flush=True)
        ref = os.path.join(E.PAGES, 'page_p0.nominal-b030.pgm')
        print('n030-clean == build page_p0.nominal-b030.pgm:', sha(frame('n030-clean')) == sha(ref))
        json.dump(dict(texts={k: dict(src=os.path.relpath(SRC[k][0], BOOT), sha256=sha(os.path.join(TXT, k + '.py')))
                              for k in ORDER},
                       renders={n: dict(page=os.path.relpath(p, BOOT), args=a, sha256=sha(frame(n)))
                                for n, p, a in jobs}),
                  open(os.path.join(OUT, 'manifest.json'), 'w'), indent=1)
    elif cmd == 'probe':
        jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        args = [(t, n) for n, _, _ in render_jobs() for t in ORDER]
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(probe, args):
                print(r['render'], r['text'], 'be', r['bullseyes'], 'hdr', r['header'], 'acc', r['accepted'],
                      'held', r['held'], 'distinct', r['distinct_read'], 'calls', r['calls'], 'offgrid', r['offgrid_calls'], 'mism', r['chunk_mismatch'], 'far', r['queued_far'],
                      'off', r['max_call_offset_blocks'], r['secs'], flush=True)
                res.append(r)
        json.dump(dict(runs=res), open(os.path.join(OUT, 'probe.json'), 'w'), indent=1)
    elif cmd == 'alone':
        res = []
        for i, (n, _, _) in enumerate(render_jobs()):
            order = ORDER[i % len(ORDER):] + ORDER[:i % len(ORDER)]
            for t in order:
                r = E.run(t, [frame(n)], os.path.join(E.RUNS, 'alone', t, n))
                r.update(order=order, render=n)
                x = r['rows'][0]
                print(n, t, x['bullseyes'], x['blocks'], x['held'], x['secs'], 'rc', r['rc'], 'load', x['load1'],
                      flush=True)
                res.append(r)
        json.dump(dict(n2=E.N2, b2=E.B2, runs=res), open(os.path.join(OUT, 'alone.json'), 'w'), indent=1)
    elif cmd == 'tables':
        tables()


def tables():
    P = {(r['text'], r['render']): r for r in json.load(open(os.path.join(OUT, 'probe.json')))['runs']}
    A = {(r['reader'], r['render']): r for r in json.load(open(os.path.join(OUT, 'alone.json')))['runs']}
    rn = [n for n, _, _ in render_jobs()]
    print('| render | ' + ' | '.join(ORDER) + ' | walls s (' + ' / '.join(ORDER) + ') | load1 |')
    print('|---|' + '---|' * (len(ORDER) + 2))
    for n in rn:
        cells = []
        for t in ORDER:
            x = A[t, n]['rows'][0]
            p = P[t, n]
            assert (x['bullseyes'], x['blocks'], x['held']) == (p['bullseyes'], p['accepted'], p['held']), (t, n, x, p)
            cells.append(f"{x['bullseyes']}/{x['blocks']}/{x['held']}")
        print(f'| {n} | ' + ' | '.join(cells) + ' | ' + ' / '.join(f"{A[t, n]['rows'][0]['secs']:.2f}" for t in ORDER)
              + f" | {A[ORDER[0], n]['rows'][0]['load1']} |")
    print('\n| render | text | data blocks | read | CRC failed | white test | queued not read | never reached | '
          'unread on the edge | unread max dist | placed but unread |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for n in rn:
        for t in ORDER:
            c = classify(P[t, n], n)
            cnt = {s: sum(1 for x in c if x['state'] == s) for s in ('read', 'crc', 'white', 'queued', 'never')}
            un = [x for x in c if x['state'] != 'read']
            print(f"| {n} | {t} | {len(c)} | {cnt['read']} | {cnt['crc']} | {cnt['white']} | {cnt['queued']} | "
                  f"{cnt['never']} | {sum(x['edge'] for x in un)} | {max([x['dist'] for x in un], default='—')} | "
                  f"{sum(x['placed'] for x in un)} |")
    print('\n### blocks read / data blocks by walk distance from the surviving seed (bins of 5 steps)\n')
    bins = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 35), (36, 40), (41, 45)]
    print('| render | text | ' + ' | '.join(f'{a}–{b}' for a, b in bins) + ' |')
    print('|---|---|' + '---|' * len(bins))
    for n in rn:
        if n.endswith('clean'):
            continue
        if not any(P[t, n]['header'] for t in ORDER):
            print(f'| {n} | all | header not read: no block read by any text |' + ' |' * (len(bins) - 1))
            continue
        for t in ORDER:
            c = classify(P[t, n], n)
            cells = []
            for a, b in bins:
                xs = [x for x in c if a <= x['dist'] <= b]
                if not xs:
                    cells.append('—')
                    continue
                r = sum(x['state'] == 'read' for x in xs)
                cells.append(f'{r}/{len(xs)}' if r < len(xs) else f'**{r}/{len(xs)}**')
            print(f'| {n} | {t} | ' + ' | '.join(cells) + ' |')
    print('\n### unread blocks, listed (block (row,col) dist state[P = placed, walk passed through]; E = edge)\n')
    for n in rn:
        if not any(P[t, n]['header'] for t in ORDER):
            print(f'- {n}: header not read by any text ({P[ORDER[0], n]["bullseyes"]} bullseye found)')
            continue
        for t in ORDER:
            c = classify(P[t, n], n)
            un = sorted([x for x in c if x['state'] != 'read'], key=lambda x: x['dist'])
            s = ' '.join(f"({x['block'][0]},{x['block'][1]}){x['dist']}{x['state'][0]}{'P' if x['placed'] else ''}"
                         f"{'E' if x['edge'] else ''}" for x in un)
            print(f'- {n} {t} ({len(un)}): {s}')
    print('\n### destroyed bullseye blocks: what the walk did there (calls: outcome, placed)\n')
    for n in rn:
        if n.endswith('clean') or not any(P[t, n]['header'] for t in ORDER):
            continue
        case = n.split('-')[1]
        for t in ORDER:
            p = P[t, n]
            out = []
            for k in survivors(case):
                b = p['blocks'].get(f'{BES[k][0]},{BES[k][1]}')
                if b is None:
                    out.append('q' if f'{BES[k][0]},{BES[k][1]}' in p['queued'] else '-')
                else:
                    out.append(('c' if b['crc'] else 'w' if b['white'] else 'o') + ('P' if b['placed'] else ''))
            print(f"- {n} {t}: seeds {p['seeds']}; off-grid reads {p['offgrid_calls']}; destroyed: {' '.join(out)}; "
                  f"chunk mismatches {p['chunk_mismatch']}, queued off-grid {p['queued_far']}, max call offset "
                  f"{p['max_call_offset_blocks']} block")


if __name__ == '__main__':
    main()
