#!/usr/bin/env python3
"""brk_at.py -- section 17's refuter's 199 built break frames (RECORD-2026-10-20,
ruling 54's entry: narrow strips, last-row quarters, ink-bottom pages, turns),
rebuilt from their recipe for RESULTS-2026-10-22 section 19.  The recipe is
the refuter's mkbrk.py (159 frames) and mkbrk2.py (40) of 2026-10-22, kept in
the session scratchpad, not in the tree: crops of three frozen captures
(build/w4/w1f4/one.nominal-b030.pgm, one.flatbed300.pgm,
build/w4/sets4/one.n045-s2.pgm) cut at the found bullseyes' extremes plus a
fraction of their span, with 180-degree turns, an inked last row or last
three rows, an inked frame, narrow vertical strips about a bullseye column,
and (brk2) strips, horizontal strips and boxes of 34-48 px (at the 947-px
scale) about the median bullseye.  The bullseyes come from the composite of
section 17 (build/progress/reader_before.py, git 789ea8fa's reader; its
locator reads what every later text reads, section 18's claims).  Written to
build/at/brk/brk/ and build/at/brk/brk2/; with --check DIR1 DIR2 every frame
is compared byte for byte with the refuter's copies.

  python bootstrap/r2reader/changeset/brk_at.py [--check SCRATCH/brk SCRATCH/brk2]
"""
import hashlib
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(BOOT, 'r2reader', 'diet'))
import w4_harness as wh   # noqa: E402

OUT = os.path.join(BOOT, 'build', 'at', 'brk')
COMPOSITE = os.path.join(BOOT, 'build', 'progress', 'reader_before.py')
_NS = {}


def ns():
    if not _NS:
        exec(compile(wh.rpy_of(COMPOSITE).split('\nwhile ')[0], 'composite', 'exec'), _NS)
    return _NS


def load(f):
    s = open(f, 'rb').read()
    m, n = [int(x) for x in s[:64].split()[1:3]]
    return np.frombuffer(s[len(s) - m * n:], np.uint8).reshape(n, m).copy()


def save(a, d, name):
    os.makedirs(d, exist_ok=True)
    a = np.ascontiguousarray(a)
    open(os.path.join(d, name + '.pgm'), 'wb').write(b'P5\n%d %d\n255\n' % (a.shape[1], a.shape[0]) + a.tobytes())


def seeds(f):
    d = ns()
    d['h'], d['j'], d['z'] = d['cb'](f)
    d['e'] = b''
    c, e = d['ld']()
    return [(s[0] / 16, s[1] / 16) for s in c[1]], c[0] / 16


def brk(d):
    src = {'nom': 'build/w4/w1f4/one.nominal-b030.pgm', 'fb': 'build/w4/w1f4/one.flatbed300.pgm',
           'n45': 'build/w4/sets4/one.n045-s2.pgm'}
    for tag, f in src.items():
        f = os.path.join(BOOT, f)
        a = load(f)
        S, p = seeds(f)
        n, m = a.shape
        bx = max(S, key=lambda t: t[1])
        tx = min(S, key=lambda t: t[1])
        rx = max(S, key=lambda t: t[0])
        lx = min(S, key=lambda t: t[0])
        span = (max(x for x, y in S) - min(x for x, y in S)) / 4
        for k in (0.08, 0.10, 0.12, 0.15, 0.2):
            off = int(k * span)
            save(a[n // 2: int(bx[1]) + off, m // 2 - 50:], d, f'{tag}-bot-{k}')
            save(a[: int(bx[1]) + off, :], d, f'{tag}-botfull-{k}')
            save(a[int(tx[1]) - off:, :], d, f'{tag}-topfull-{k}')
            save(a[:, : int(rx[0]) + off], d, f'{tag}-right-{k}')
            save(a[:, int(lx[0]) - off:], d, f'{tag}-left-{k}')
            b = a[: int(bx[1]) + off, :].copy()
            b[-1, :] = 0
            save(b, d, f'{tag}-botink1-{k}')
            b = a[: int(bx[1]) + off, :].copy()
            b[-3:, :] = 0
            save(b, d, f'{tag}-botink3-{k}')
            save(a[: int(bx[1]) + off, :][::-1, ::-1], d, f'{tag}-botfull180-{k}')
        cx = round(sorted(S)[len(S) // 2][0])
        for wfr in (0.25, 0.3, 0.4, 0.6):
            w = int(wfr * span)
            save(a[:, max(0, cx - w):cx + w], d, f'{tag}-narrow-{wfr}')
            save(a[:, max(0, cx - w):cx + w][::-1, ::-1], d, f'{tag}-narrow180-{wfr}')
        save(a[::-1, ::-1], d, f'{tag}-rot180')
        b = a.copy()
        b[-1, :] = 0
        save(b, d, f'{tag}-lastrowink')
        b = a.copy()
        b[-2:, :] = 0
        b[:, -2:] = 0
        save(b, d, f'{tag}-inkframe')
        save(a[n // 2:int(bx[1]) + int(0.1 * span), :m // 2 + 40], d, f'{tag}-qbl-lastrows')
        save(a[n // 2:int(bx[1]) + int(0.1 * span), :m // 2 + 40][::-1, ::-1], d, f'{tag}-qbl-lastrows180')


def brk2(d):
    for tag, f in {'nom': 'build/w4/w1f4/one.nominal-b030.pgm', 'fb': 'build/w4/w1f4/one.flatbed300.pgm'}.items():
        f = os.path.join(BOOT, f)
        a = load(f)
        S, p = seeds(f)
        n, m = a.shape
        cx, cy = sorted(S)[len(S) // 2]
        cx, cy = round(cx), round(cy)
        sc = m / 947
        for wpx in (34, 38, 42, 48):
            w = int(wpx * sc / 2)
            save(a[:, cx - w:cx + w], d, f'{tag}-strip{wpx}')
            save(a[:, cx - w:cx + w][::-1, ::-1], d, f'{tag}-strip{wpx}-180')
            save(a[cy - w:cy + w, :], d, f'{tag}-hstrip{wpx}')
            save(a[cy - w:cy + w, cx - w:cx + w], d, f'{tag}-box{wpx}')
            b = a[cy - w:cy + w, :].copy()
            b[-1, :] = 0
            save(b, d, f'{tag}-hstrip{wpx}-ink')


def frames():
    out = []
    for g in ('brk', 'brk2'):
        d = os.path.join(OUT, g)
        out += [(g, os.path.join(d, f)) for f in sorted(os.listdir(d)) if f.endswith('.pgm')]
    return out


def main():
    brk(os.path.join(OUT, 'brk'))
    brk2(os.path.join(OUT, 'brk2'))
    fr = frames()
    print(len(fr), 'frames:', sum(g == 'brk' for g, _ in fr), 'brk +', sum(g == 'brk2' for g, _ in fr), 'brk2')
    if '--check' in sys.argv:
        k = sys.argv.index('--check')
        ref = dict(brk=sys.argv[k + 1], brk2=sys.argv[k + 2])
        same, diff, missing = 0, [], []
        for g, f in fr:
            r = os.path.join(ref[g], os.path.basename(f))
            if not os.path.exists(r):
                missing.append(r)
                continue
            a, b = (hashlib.sha256(open(x, 'rb').read()).hexdigest() for x in (f, r))
            if a == b:
                same += 1
            else:
                diff.append(os.path.basename(f))
        extra = [x for g in ref for x in os.listdir(ref[g]) if x.endswith('.pgm')
                 and not os.path.exists(os.path.join(OUT, g, x))]
        print(f'against the refuter\'s copies: {same} byte-identical, differ {diff}, missing there {missing}, '
              f'only there {extra}')


if __name__ == '__main__':
    main()
