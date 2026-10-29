#!/usr/bin/env python3
"""claims_fresh.py -- claim-level comparison of the fresh-eyes arms against the
ruled text (RESULTS-2026-10-22 section 16), every capture alone, in process.

  python claims_fresh.py claims [JOBS] [ARM ...]   -> fresh/claims/claims.json
  python claims_fresh.py clamps [JOBS]             -> fresh/claims/clamps.json
  python claims_fresh.py edits [JOBS] [ARM ...]    -> fresh/claims/edits.json
  python claims_fresh.py tables

claims: each text's definitions exec'd (run_sets.ns_of: the loader's
definitions + the typed text, as the chain runs it); per frame alone: the
loader, the locator (bullseyes, pitch, every seed pose, the header bytes),
then -- when the header reads -- the walk with a spy on the block read that
records, per call, the pose (position, both axes, flip, walk key) as it
stood at the call and the bytes returned.  Every arm is compared with the
ruled text call for call: identical, or the first differing call and the
number of differing calls; a frame whose locator or walk raises is recorded
with the exception (the process would print 'cannot read').
clamps: the ruled text, and F3 before its search with the walk's frame check
at 11 modules (11*p>>4) and rb's clamps KEPT, each with a spy on the sampler
rb that counts every call whose position lies outside the clamp box
[0, 16h-17] x [0, 16j-17], by calling chain (the first two named frames
above the sampler: w <- ld = the rotation search, f <- ld = the header read,
f <- be = the walk's block read, ft <- v / w <- ft = the walk's refinement)
and the largest excursion in pixels; plus F5's own unclamped sampler on the
same frames: which out-of-range samples would IndexError (beyond the last
row) and which wrap silently (negative or past the right edge).
edits: each arm's text before its search (reader_edits_ARM_fresh.py, the
ruled spelling) against the searched text, call for call (the search must
change nothing that is read).
Frames: the 54 frames of the acceptance sets A-I + margin, the four phone
photos, section 11's 39 renders (edge, q045, ring, clean, ring15) and section
14's 32 one-bullseye renders.
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
import run_sets as RS     # noqa: E402
import names_fresh as NF  # noqa: E402

OUT = os.path.join(BOOT, 'build', 'changeset', 'fresh', 'claims')
EDGE_R = os.path.join(BOOT, 'build', 'changeset', 'edge', 'renders')
ONEB_R = os.path.join(BOOT, 'build', 'changeset', 'onebull', 'renders')
ARMS = ['f2', 'f3', 'f5', 'f6', 'f1']


def frames():
    out = []
    seen = set()
    for st, cases in RS.ws.sets().items():
        for c, fr in cases.items():
            for f in fr:
                f = RS.to_pgm(f) if f.endswith('.txt') else f
                if f not in seen:
                    seen.add(f)
                    out.append(('set', f))
    for k in (1, 2, 3, 4):
        out.append(('photo', os.path.join(RS.PHOTOS, f'{k}.pgm')))
    for f in sorted(os.listdir(EDGE_R)):
        if f.endswith('.pgm'):
            out.append(('edge', os.path.join(EDGE_R, f)))
    for f in sorted(os.listdir(ONEB_R)):
        if f.endswith('.pgm'):
            out.append(('onebull', os.path.join(ONEB_R, f)))
    return out


_NS = {}


def ns(key, path, names, edits=()):
    if key not in _NS:
        src = RS.wh.rpy_of(path)
        for a, b in edits:
            assert src.count(a) == 1, (key, a)
            src = src.replace(a, b)
        d = {}
        exec(compile(src.split('\nwhile ')[0], key, 'exec'), d)
        _NS[key] = (d, names)
    return _NS[key]


def snap(s):
    return (s[0], s[1], tuple(s[2]), tuple(s[3]), s[4], tuple(s[5]))


def read(key, path, names, frame):
    d, N = ns(key, path, names)
    rec = dict(error=None, bullseyes=None, header=None, pitch=None, seeds=None, calls=[], accepted=0, held=0)
    try:
        d[N['h']], d[N['j']], d[N['z']] = d[N['ld']](frame)
        d[N['e']] = b''
        o, hdr = d[N['fm']]()
        rec.update(bullseyes=len(o[1]), header=hdr.hex() if hdr else None, pitch=o[0],
                   seeds=[snap(s) for s in o[1]])
        d[N['e']] = hdr
        if hdr:
            rb = d[N['rb']]
            calls = rec['calls']

            def spy(s):
                p = snap(s)
                out = rb(s)
                calls.append((p, out.hex() if out else out))
                return out
            d[N['rb']] = spy
            try:
                acc = d[N['wk']](*o)
            finally:
                d[N['rb']] = rb
            rec['accepted'] = len(acc)
            rec['held'] = len({x[:2] for x in acc})
    except Exception as ex:   # the process's bare except: 'cannot read'
        rec['error'] = f'{type(ex).__name__}: {ex}'[:200]
        rec['where'] = traceback.format_exc().strip().splitlines()[-3:]
    return rec


def texts(arms):
    t = {'ruled': (NF.TEXT['ruled'], NF.arm_map('ruled'))}
    for a in arms:
        t[a] = (NF.TEXT[a], NF.arm_map(a))
    return t


def claims_job(arg):
    group, frame, arms = arg
    T = texts(arms)
    recs = {k: read(k, p, n, frame) for k, (p, n) in T.items()}
    base = recs['ruled']
    out = dict(group=group, frame=os.path.relpath(frame, BOOT) if frame.startswith(BOOT) else frame, texts={})
    for k, r in recs.items():
        x = dict(error=r['error'], bullseyes=r['bullseyes'], header=bool(r['header']), calls=len(r['calls']),
                 accepted=r['accepted'], held=r['held'],
                 digest=hashlib.sha256(repr((r['pitch'], r['seeds'], r['header'], r['calls'])).encode()).hexdigest()[:16])
        if r['error']:
            x['where'] = r.get('where')
        if k != 'ruled':
            x['locator_identical'] = (r['pitch'], r['seeds'], r['header']) == (base['pitch'], base['seeds'], base['header'])
            x['calls_identical'] = r['calls'] == base['calls']
            diff = [i for i, (a, b) in enumerate(zip(r['calls'], base['calls'])) if a != b]
            x['first_diff'] = diff[0] if diff else (None if len(r['calls']) == len(base['calls'])
                                                     else min(len(r['calls']), len(base['calls'])))
            x['n_diff'] = len(diff) + abs(len(r['calls']) - len(base['calls']))
        out['texts'][k] = x
    return out


def edits_job(arg):
    group, frame, arms = arg
    out = dict(group=group, frame=os.path.relpath(frame, BOOT) if frame.startswith(BOOT) else frame, arms={})
    for a in arms:
        x = read(a + '_edits', NF.EDITS[a], NF.arm_map('ruled'), frame)
        y = read(a, NF.TEXT[a], NF.arm_map(a), frame)
        out['arms'][a] = dict(identical=(x['pitch'], x['seeds'], x['header'], x['calls'], x['error'] is None) ==
                              (y['pitch'], y['seeds'], y['header'], y['calls'], y['error'] is None),
                              edits=(x['accepted'], x['held'], x['error']), searched=(y['accepted'], y['held'], y['error']))
    return out


F3_11 = [('16*j-32-s[1])<5*p>>3:continue', '16*j-32-s[1])<11*p>>4:continue')]


def clamps_job(arg):
    group, frame = arg
    rec = {}
    N0 = NF.arm_map('ruled')   # the pre-search F3/F5 texts keep the ruled spelling
    for key, path, edits in (('ruled', NF.TEXT['ruled'], ()), ('f3_11', NF.EDITS['f3'], F3_11),
                             ('f5_edits', NF.EDITS['f5'], ())):
        d, N = ns(key, path, N0, edits)
        smp = N['v']   # the sampler (v of record, rb in the ruled spelling)
        orig = d[smp]
        hits = {}
        st = dict(n=0)

        def spy(s, x, orig=orig, hits=hits, st=st, d=d, key=key):
            st['n'] += 1
            h, j = d[N['h']], d[N['j']]
            lo_x, hi_x, lo_y, hi_y = 0, 16 * h - 17, 0, 16 * j - 17
            if not (lo_x <= s <= hi_x and lo_y <= x <= hi_y):
                f = sys._getframe(1)
                ch = []
                while f and len(ch) < 2:
                    if not f.f_code.co_name.startswith('<'):
                        ch.append(f.f_code.co_name)
                    f = f.f_back
                ex = max(lo_x - s, s - hi_x, lo_y - x, x - hi_y) / 16
                kind = 'index' if (x >> 4) * h + (s >> 4) + h + 1 >= h * j else 'wrap'
                k = ' <- '.join(ch) + (f' [{kind}]' if key == 'f5_edits' else '')
                e = hits.setdefault(k, [0, 0.0])
                e[0] += 1
                e[1] = max(e[1], round(ex, 2))
            return orig(s, x)
        d[smp] = spy
        try:
            r = read(key, path, N0, frame)
        finally:
            d[smp] = orig
        rec[key] = dict(samples=st['n'], out_of_box=hits, error=r['error'], bullseyes=r['bullseyes'],
                        header=bool(r['header']), accepted=r['accepted'], held=r['held'], calls=len(r['calls']))
    return dict(group=group, frame=os.path.relpath(frame, BOOT) if frame.startswith(BOOT) else frame, texts=rec)


def main():
    cmd = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    if cmd == 'claims':
        arms = sys.argv[3:] or ARMS
        args = [(g, f, arms) for g, f in frames()]
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(claims_job, args):
                print(r['frame'], {k: (v['bullseyes'], v['accepted'], v['held'], v.get('calls_identical'), v.get('n_diff'),
                                       v['error'] and v['error'][:40]) for k, v in r['texts'].items()}, flush=True)
                res.append(r)
        json.dump(dict(arms=arms, runs=res), open(os.path.join(OUT, 'claims.json'), 'w'), indent=1)
    elif cmd == 'edits':
        arms = sys.argv[3:] or ARMS
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(edits_job, [(g, f, arms) for g, f in frames()]):
                print(r['frame'], {a: v['identical'] for a, v in r['arms'].items()}, flush=True)
                res.append(r)
        json.dump(dict(arms=arms, runs=res), open(os.path.join(OUT, 'edits.json'), 'w'), indent=1)
        for a in arms:
            bad = [r['frame'] for r in res if not r['arms'][a]['identical']]
            print(f'{a}: edits == searched, call for call, on {len(res) - len(bad)} of {len(res)} frames; differ: {bad}')
    elif cmd == 'clamps':
        res = []
        with ProcessPoolExecutor(jobs) as ex:
            for r in ex.map(clamps_job, frames()):
                print(r['frame'], {k: (v['accepted'], v['held'], v['out_of_box'], v['error'] and v['error'][:40])
                                   for k, v in r['texts'].items()}, flush=True)
                res.append(r)
        json.dump(dict(runs=res), open(os.path.join(OUT, 'clamps.json'), 'w'), indent=1)
    elif cmd == 'tables':
        tables()


def tables():
    p = os.path.join(OUT, 'claims.json')
    if os.path.exists(p):
        C = json.load(open(p))
        print('### claims: frames where the arm differs from the ruled text (alone, in process)\n')
        for a in C['arms']:
            by = {}
            for r in C['runs']:
                x = r['texts'][a]
                g = by.setdefault(r['group'], dict(frames=0, identical=0, loc_diff=0, call_diff=0, err=0,
                                                   d_acc=0, d_held=0, list=[]))
                g['frames'] += 1
                b = r['texts']['ruled']
                if x['calls_identical'] and x['locator_identical'] and x['error'] == b['error']:
                    g['identical'] += 1
                else:
                    g['loc_diff'] += not x['locator_identical']
                    g['call_diff'] += not x['calls_identical']
                    g['list'].append((os.path.basename(r['frame']), b['accepted'], x['accepted'], b['held'], x['held'],
                                      x['n_diff'], x['error'] and x['error'][:50]))
                g['err'] += bool(x['error']) and not b['error']
                g['d_acc'] += x['accepted'] - b['accepted']
                g['d_held'] += x['held'] - b['held']
            for g, v in by.items():
                print(f"{a} {g}: {v['identical']}/{v['frames']} identical; locator differs {v['loc_diff']}, calls differ "
                      f"{v['call_diff']}, new errors {v['err']}, Δaccepted {v['d_acc']:+d}, Δheld {v['d_held']:+d}")
                for t in v['list']:
                    print('    ', t)
    p = os.path.join(OUT, 'clamps.json')
    if os.path.exists(p):
        C = json.load(open(p))
        print('\n### clamps: samples outside the clamp box, by chain (count, max px out)\n')
        tot = {}
        for r in C['runs']:
            for k, v in r['texts'].items():
                for ch, (n, m) in v['out_of_box'].items():
                    e = tot.setdefault((k, r['group'], ch), [0, 0.0, 0])
                    e[0] += n
                    e[1] = max(e[1], m)
                    e[2] += 1
        for (k, g, ch), (n, m, nf) in sorted(tot.items()):
            print(f'{k} {g} {ch}: {n} samples on {nf} frames, max {m} px')
        for r in C['runs']:
            t = r['texts']
            if any(v['out_of_box'] for v in t.values()) or t['f5_edits']['error'] or \
                    (t['f5_edits']['accepted'], t['f5_edits']['held']) != (t['f3_11']['accepted'], t['f3_11']['held']):
                print('  ', os.path.basename(r['frame']), {k: (v['accepted'], v['held'], v['error'] and v['error'][:30],
                                                              v['out_of_box']) for k, v in t.items()})


if __name__ == '__main__':
    main()
