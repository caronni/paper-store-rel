#!/usr/bin/env python3
"""claims_comp.py -- claims_fresh.py's call-for-call instrument (its frames,
its exec of each text as the chain runs it, its read with the spy on the
block read) on the composite texts of RESULTS-2026-10-22 section 17, with the
texts and name maps of names_comp.py.

  python claims_comp.py claims BASE OTHER [JOBS]  -> build/composite/claims/claims-OTHER-vs-BASE.json
  python claims_comp.py edits TEXT [JOBS]         -> build/composite/claims/edits-TEXT.json
  python claims_comp.py padspy TEXT [JOBS]        -> build/composite/claims/padspy-TEXT.json
  python claims_comp.py tables

claims: OTHER against BASE, every capture alone, call for call (the locator:
bullseyes, pitch, every seed pose, the header bytes; then every block-read
call: the pose as it stood and the bytes returned).  BASE, OTHER in ruled
comp pad padt.
edits: TEXT before its search (build/composite/reader_edits_TEXT.py, its
parent's spelling) against the searched TEXT, call for call.
padspy: the padded arm TEXT (pad or padt) with a spy on its sampler: every
sample outside the old clamp box [0, 16h-17] x [0, 16j-17], by calling
chain (the first two named frames above the sampler), the largest excursion
in pixels, and where its four bilinear reads land (the weights that are
non-zero only): 'pad' = in the white padding (past the bottom row, or a
negative index wrapped to the end of the buffer), 'rowwrap' = in the image
but through the horizontal wrap (a column left of 0 or right of h-1 reads the
adjacent row's other end), 'image' = lawful image pixels; and the margin left
before an IndexError (the deepest index against the buffer's length, both
directions).
"""
import hashlib
import json
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import claims_fresh as CF  # noqa: E402  (frames, ns, read, snap: unchanged)
import names_comp as NC    # noqa: E402

OUT = os.path.join(BOOT, 'build', 'composite', 'claims')


def key(r):
    return (r['pitch'], r['seeds'], r['header'], r['calls'])


def summary(r, base=None):
    x = dict(error=r['error'], bullseyes=r['bullseyes'], header=bool(r['header']), calls=len(r['calls']),
             accepted=r['accepted'], held=r['held'],
             digest=hashlib.sha256(repr(key(r)).encode()).hexdigest()[:16])
    if r['error']:
        x['where'] = r.get('where')
    if base is not None:
        x['locator_identical'] = (r['pitch'], r['seeds'], r['header']) == (base['pitch'], base['seeds'], base['header'])
        x['calls_identical'] = r['calls'] == base['calls']
        diff = [i for i, (a, b) in enumerate(zip(r['calls'], base['calls'])) if a != b]
        x['first_diff'] = diff[0] if diff else (None if len(r['calls']) == len(base['calls'])
                                                 else min(len(r['calls']), len(base['calls'])))
        x['n_diff'] = len(diff) + abs(len(r['calls']) - len(base['calls']))
        x['bytes_only'] = len(r['calls']) == len(base['calls']) and all(
            a[0] == b[0] for a, b in zip(r['calls'], base['calls']))
        x['chunks_identical'] = ({c[1][:4] for c in r['calls'] if c[1]} == {c[1][:4] for c in base['calls'] if c[1]})
    return x


def rel(f):
    return os.path.relpath(f, BOOT) if f.startswith(BOOT) else f


def claims_job(arg):
    group, frame, base, other = arg
    b = CF.read(base, NC.TEXT[base], NC.arm_map(base), frame)
    o = CF.read(other, NC.TEXT[other], NC.arm_map(other), frame)
    return dict(group=group, frame=rel(frame), texts={base: summary(b), other: summary(o, b)})


def edits_job(arg):
    group, frame, t = arg
    x = CF.read(t + '_edits', NC.EDITS[t], NC.edits_map(t), frame)
    y = CF.read(t, NC.TEXT[t], NC.arm_map(t), frame)
    return dict(group=group, frame=rel(frame), identical=(key(x), x['error'] is None) == (key(y), y['error'] is None),
                edits=(x['accepted'], x['held'], x['error']), searched=(y['accepted'], y['held'], y['error']))


def padspy_job(arg):
    group, frame, t = arg
    N = NC.arm_map(t)
    d, _ = CF.ns(t, NC.TEXT[t], N)
    smp = N['v']   # the sampler (v of record, rb in the ruled spelling)
    orig = d[smp]
    hits = {}
    st = dict(n=0, lo=0, hi=0)

    def spy(s, x):
        st['n'] += 1
        h, j, z = d[N['h']], d[N['j']], d[N['z']]
        if not (0 <= s <= 16 * h - 17 and 0 <= x <= 16 * j - 17):
            f = sys._getframe(1)
            ch = []
            while f and len(ch) < 2:
                if not f.f_code.co_name.startswith('<'):
                    ch.append(f.f_code.co_name)
                f = f.f_back
            q, p, i = s & 15, x & 15, (x >> 4) * h + (s >> 4)
            kinds = set()
            for di, dc, w in ((0, 0, (16 - q) * (16 - p)), (1, 1, q * (16 - p)), (h, 0, (16 - q) * p),
                              (h + 1, 1, q * p)):
                if not w:
                    continue
                k = i + di
                st['hi'] = max(st['hi'], k)
                st['lo'] = min(st['lo'], k)
                kk = k % len(z) if -len(z) <= k < len(z) else None
                col = (s >> 4) + dc
                if kk is None:
                    kinds.add('INDEXERROR')
                elif kk >= h * j:
                    kinds.add('pad')
                elif not 0 <= col < h:
                    kinds.add('rowwrap')
                else:
                    kinds.add('image')
            ex = max(-s, s - (16 * h - 17), -x, x - (16 * j - 17)) / 16
            e = hits.setdefault(' <- '.join(ch) + ' [' + '+'.join(sorted(kinds)) + ']', [0, 0.0])
            e[0] += 1
            e[1] = max(e[1], round(ex, 2))
        return orig(s, x)
    d[smp] = spy
    try:
        r = CF.read(t, NC.TEXT[t], N, frame)
    finally:
        d[smp] = orig
    z = d.get(N['z'])
    h, j = d.get(N['h']), d.get(N['j'])
    return dict(group=group, frame=rel(frame), samples=st['n'], out_of_box=hits, error=r['error'],
                bullseyes=r['bullseyes'], header=bool(r['header']), accepted=r['accepted'], held=r['held'],
                buffer=len(z) if z else None, image=(h * j) if h else None, deepest_index=st['hi'],
                most_negative_index=st['lo'])


def main():
    cmd = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    if cmd == 'claims':
        base, other = sys.argv[2], sys.argv[3]
        jobs = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(claims_job, [(g, f, base, other) for g, f in CF.frames()]):
                x = r['texts'][other]
                print(r['frame'], r['texts'][base]['accepted'], x['accepted'], x['locator_identical'],
                      x['calls_identical'], x['n_diff'], x['error'] and x['error'][:40], flush=True)
                res.append(r)
        json.dump(dict(base=base, other=other, runs=res),
                  open(os.path.join(OUT, f'claims-{other}-vs-{base}.json'), 'w'), indent=1)
        same = sum(r['texts'][other]['locator_identical'] and r['texts'][other]['calls_identical'] and
                   r['texts'][other]['error'] == r['texts'][base]['error'] for r in res)
        print(f'{other} vs {base}: identical call for call on {same} of {len(res)} captures')
    elif cmd == 'edits':
        t = sys.argv[2]
        jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(edits_job, [(g, f, t) for g, f in CF.frames()]):
                print(r['frame'], r['identical'], flush=True)
                res.append(r)
        json.dump(dict(text=t, runs=res), open(os.path.join(OUT, f'edits-{t}.json'), 'w'), indent=1)
        bad = [r['frame'] for r in res if not r['identical']]
        print(f'{t}: edits == searched, call for call, on {len(res) - len(bad)} of {len(res)}; differ: {bad}')
    elif cmd == 'padspy':
        t = sys.argv[2]
        jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(padspy_job, [(g, f, t) for g, f in CF.frames()]):
                print(r['frame'], r['accepted'], r['held'], r['out_of_box'], r['error'] and r['error'][:40], flush=True)
                res.append(r)
        json.dump(dict(text=t, runs=res), open(os.path.join(OUT, f'padspy-{t}.json'), 'w'), indent=1)
    elif cmd == 'tables':
        tables()


def tables():
    for f in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, f)
        if f.startswith('claims-'):
            C = json.load(open(p))
            b, o = C['base'], C['other']
            by = {}
            for r in C['runs']:
                x, y = r['texts'][o], r['texts'][b]
                g = by.setdefault(r['group'], dict(frames=0, identical=0, loc=0, calls=0, err=0, da=0, dh=0, lst=[]))
                g['frames'] += 1
                if x['locator_identical'] and x['calls_identical'] and x['error'] == y['error']:
                    g['identical'] += 1
                else:
                    g['loc'] += not x['locator_identical']
                    g['calls'] += not x['calls_identical']
                    g['lst'].append((os.path.basename(r['frame']), y['bullseyes'], x['bullseyes'], y['accepted'],
                                     x['accepted'], y['held'], x['held'], x['n_diff'], x['locator_identical'],
                                     x['bytes_only'], x['error'] and x['error'][:50]))
                g['err'] += bool(x['error']) and not y['error']
                g['da'] += x['accepted'] - y['accepted']
                g['dh'] += x['held'] - y['held']
            print(f'\n### {o} against {b}, call for call, every capture alone\n')
            print('| group | identical | locator differs | calls differ | new errors | Δ blocks | Δ chunks |')
            print('|---|---|---|---|---|---|---|')
            tot = [0, 0]
            for g, v in by.items():
                tot[0] += v['identical']
                tot[1] += v['frames']
                print(f"| {g} | {v['identical']}/{v['frames']} | {v['loc']} | {v['calls']} | {v['err']} | "
                      f"{v['da']:+d} | {v['dh']:+d} |")
            print(f'| all | {tot[0]}/{tot[1]} | | | | | |')
            for g, v in by.items():
                for t in v['lst']:
                    print('   ', g, '(frame, bullseyes base/other, blocks base/other, chunks base/other, n_diff, '
                          'locator identical, poses identical (bytes only), error):', t)
        elif f.startswith('edits-'):
            C = json.load(open(p))
            bad = [r['frame'] for r in C['runs'] if not r['identical']]
            print(f"\n{C['text']}: before its search == searched, call for call, on "
                  f"{len(C['runs']) - len(bad)} of {len(C['runs'])}; differ: {bad}")
        elif f.startswith('padspy-'):
            C = json.load(open(p))
            tot = {}
            for r in C['runs']:
                for ch, (n, m) in r['out_of_box'].items():
                    e = tot.setdefault((r['group'], ch), [0, 0.0, 0])
                    e[0] += n
                    e[1] = max(e[1], m)
                    e[2] += 1
            print(f"\n### {C['text']}: samples outside the old clamp box, by chain and where they land\n")
            print('| group | chain [where the bilinear reads land] | samples | frames | max px out |\n|---|---|---|---|---|')
            for (g, ch), (n, m, nf) in sorted(tot.items()):
                print(f'| {g} | {ch} | {n:,} | {nf} | {m} |')
            worst = max((r['deepest_index'] - r['buffer'] for r in C['runs'] if r['buffer']), default=None)
            neg = min((r['most_negative_index'] + r['buffer'] for r in C['runs'] if r['buffer']), default=None)
            rows = max(((r['deepest_index'] - r['image']) / (r['image'] / 1) for r in C['runs'] if r['buffer']),
                       default=None)
            print(f'\n  deepest index - buffer length (negative = inside): {worst}; most negative index + buffer '
                  f'length (positive = inside): {neg}; deepest overrun past the image as a fraction of the image: '
                  f'{rows:.4f}')
            print('  errors:', [(os.path.basename(r['frame']), r['error']) for r in C['runs'] if r['error']])


if __name__ == '__main__':
    main()
