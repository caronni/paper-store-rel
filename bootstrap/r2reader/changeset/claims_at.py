#!/usr/bin/env python3
"""claims_at.py -- claims_comp.py's call-for-call instrument (its frames, its
exec of each text's definitions as the chain runs them, its read with the
spy on the block read) on the texts of RESULTS-2026-10-22 section 19, with
names_at's texts and maps; outputs in build/at/claims/.  Two additions:
- the claims comparison also records, per text and capture, the finder's
  binarisation threshold AS THE TEXT USED IT: the loader's buffer is handed
  to the text as a bytes subclass whose translate() records its table, and
  the table bytes(x<t for x in range(256)) holds exactly t ones; beside it
  the threshold over the image alone, min(z[:h*j:97])+max(z[:h*j:97])>>1;
- --brk: the frames are section 17's refuter's 199 built break frames
  (brk_at.py, build/at/brk/) instead of the 129 captures.

  python claims_at.py claims BASE OTHER [JOBS] [--brk]   -> claims/claims-OTHER-vs-BASE[-brk].json
  python claims_at.py edits TEXT [JOBS]                  -> claims/edits-TEXT.json
  python claims_at.py padspy TEXT [JOBS] [--brk]         -> claims/padspy-TEXT[-brk].json
  python claims_at.py diffcalls BASE OTHER FRAME [...]  every differing block-read call, pose and bytes
  python claims_at.py tables
BASE, OTHER, TEXT in prog at pad128.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import claims_comp as CC   # noqa: E402
import names_at as NA      # noqa: E402
import brk_at as BK        # noqa: E402

CC.NC = NA
CC.OUT = os.path.join(BOOT, 'build', 'at', 'claims')
CF = CC.CF
BRK = '--brk' in sys.argv
if BRK:
    sys.argv.remove('--brk')
    CF.frames = BK.frames
    SUFFIX = '-brk'
else:
    SUFFIX = ''


class Z(bytes):
    def translate(self, table, *a):
        self.rec.append(sum(table))
        return bytes.translate(self, table, *a)


def read_t(key, frame):
    d, N = CF.ns(key, NA.TEXT[key], NA.arm_map(key))
    ld = d[N['ld']]
    rec, img = [], []

    def ld2(f):
        h, j, z = ld(f)
        z2 = Z(z)
        z2.rec = rec
        im = z[:h * j:97]
        img.append(min(im) + max(im) >> 1)
        return h, j, z2
    d[N['ld']] = ld2
    try:
        r = CF.read(key, NA.TEXT[key], NA.arm_map(key), frame)
    finally:
        d[N['ld']] = ld
    r['threshold'] = rec[0] if rec else None
    r['threshold_image'] = img[0] if img else None
    r['translates'] = len(rec)
    return r


def claims_job(arg):
    group, frame, base, other = arg
    b = read_t(base, frame)
    o = read_t(other, frame)
    sb, so = CC.summary(b), CC.summary(o, b)
    for s, r in ((sb, b), (so, o)):
        s.update(threshold=r['threshold'], threshold_image=r['threshold_image'], translates=r['translates'],
                 chunks=sorted({c[1][:4] for c in r['calls'] if c[1]}))
    so['threshold_identical'] = o['threshold'] == b['threshold']
    return dict(group=group, frame=CC.rel(frame), texts={base: sb, other: so})


def diffcalls(base, other, frames):
    for f in frames:
        b, o = read_t(base, f), read_t(other, f)
        print(f'== {os.path.basename(f)}: locator identical '
              f'{(b["pitch"], b["seeds"], b["header"]) == (o["pitch"], o["seeds"], o["header"])}, '
              f'calls {len(b["calls"])} / {len(o["calls"])}, threshold {b["threshold"]} / {o["threshold"]}')
        for i in range(max(len(b['calls']), len(o['calls']))):
            x = b['calls'][i] if i < len(b['calls']) else None
            y = o['calls'][i] if i < len(o['calls']) else None
            if x != y:
                print(f'  call {i}: {base} {x}')
                print(f'  call {i}: {other} {y}')


def main():
    cmd = sys.argv[1]
    os.makedirs(CC.OUT, exist_ok=True)
    if cmd == 'diffcalls':
        diffcalls(sys.argv[2], sys.argv[3], sys.argv[4:])
        return
    if cmd != 'claims':
        if cmd == 'padspy' and BRK:
            t = sys.argv[2]
            jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
            res = []
            with ProcessPoolExecutor(jobs) as ex:
                for r in ex.map(CC.padspy_job, [(g, f, t) for g, f in CF.frames()]):
                    print(r['frame'], r['accepted'], r['held'], r['out_of_box'], r['error'] and r['error'][:40],
                          flush=True)
                    res.append(r)
            json.dump(dict(text=t, runs=res), open(os.path.join(CC.OUT, f'padspy-{t}-brk.json'), 'w'), indent=1)
            return
        CC.main()
        return
    base, other = sys.argv[2], sys.argv[3]
    jobs = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    res = []
    with ProcessPoolExecutor(jobs) as ex:
        for r in ex.map(claims_job, [(g, f, base, other) for g, f in CF.frames()]):
            x, y = r['texts'][other], r['texts'][base]
            print(r['frame'], y['accepted'], x['accepted'], x['locator_identical'], x['calls_identical'],
                  x['n_diff'], 'thr', y['threshold'], x['threshold'], x['error'] and x['error'][:40], flush=True)
            res.append(r)
    json.dump(dict(base=base, other=other, runs=res),
              open(os.path.join(CC.OUT, f'claims-{other}-vs-{base}{SUFFIX}.json'), 'w'), indent=1)
    same = sum(r['texts'][other]['locator_identical'] and r['texts'][other]['calls_identical'] and
               r['texts'][other]['error'] == r['texts'][base]['error'] for r in res)
    thr = sum(r['texts'][other]['threshold_identical'] for r in res)
    lost = [(os.path.basename(r['frame']), sorted(set(r['texts'][base]['chunks']) - set(r['texts'][other]['chunks'])))
            for r in res if set(r['texts'][base]['chunks']) - set(r['texts'][other]['chunks'])]
    errs = [(os.path.basename(r['frame']), r['texts'][other]['error']) for r in res
            if r['texts'][other]['error'] and not r['texts'][base]['error']]
    print(f'{other} vs {base}: identical call for call on {same} of {len(res)} captures; threshold identical on '
          f'{thr} of {len(res)}; chunks lost {lost}; new errors {errs}')


if __name__ == '__main__':
    main()
