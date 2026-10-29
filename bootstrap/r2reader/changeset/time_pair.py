#!/usr/bin/env python3
"""time_pair.py -- paired wall times, one reader process at a time, the
readers alternating (their order flipped every round), never typed.

  python time_pair.py READER.py READER.py [...] [--rounds N]

Frames (each a fresh process as the chain runs it, run_sets.run): three whole
pages at the nominal preset (one.nominal-b030, one.nominal-b045,
two_p0.nominal-b030), the quarter one.q-tl, the near-white last page
page_p2.nominal-b045, the loupe grid one.loupe02-s2 through the Plate's
one-liner (and as text for a reader that still reads text); then the photo
pools 1,2,3 and 1,2,4 (one process per pool: seconds per photo to its
progress line, and the process's whole wall including the closing decode).
-> build/changeset/timing.json + a table of min (median).
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_sets as R   # noqa: E402

WS = R.ws
FRAMES = {'page one b030': WS.f('one.nominal-b030'), 'page one b045': WS.f('one.nominal-b045'),
          'page two_p0 b030': WS.f('two_p0.nominal-b030'), 'quarter q-tl': WS.f('one.q-tl'),
          'near-white p2 b045': WS.p2('nominal-b045'),
          'loupe s2 (PGM)': R.to_pgm(WS.x('one.loupe02-s2')), 'loupe s2 (text)': WS.x('one.loupe02-s2')}


def photo_pool(path, order, wd):
    primer, output = R.names_of(path)
    src = open(path).read()
    src = R.make_typed.put_token(src, 'N2', R.PHOTO_N2)[0]
    src = R.make_typed.put_token(src, 'B2', R.PHOTO_B2)[0]
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd)
    shutil.copy2(os.path.join(R.PHOTOS, 'r.py'), os.path.join(wd, primer))
    open(os.path.join(wd, 'v.py'), 'w').write(src)
    t0 = time.time()
    lines, secs, rc, se = R.run(src, 'v.py', [os.path.join(R.PHOTOS, f'{k}.pgm') for k in order],
                                wd, fresh=False)
    wall = time.time() - t0
    got = open(os.path.join(wd, output), 'rb').read() if os.path.exists(os.path.join(wd, output)) else None
    ok = got == open(os.path.join(R.PHOTOS, 'b.py'), 'rb').read()
    shutil.rmtree(wd, ignore_errors=True)
    return secs, round(wall, 2), ok


def main():
    a = sys.argv[1:]
    rounds = int(a[a.index('--rounds') + 1]) if '--rounds' in a else 3
    readers = [os.path.abspath(x) for x in a if x.endswith('.py')]
    acc = {r: {} for r in readers}
    wd = os.path.join(R.OUT, 'timing-wd')
    for k in range(rounds):
        order = readers if k % 2 == 0 else readers[::-1]
        for name, fr in FRAMES.items():
            for r in order:
                if fr.endswith('.txt') and not R.has_grid_branch(r):
                    continue
                lines, secs, rc, se = R.run(R.wh.rpy_of(r), R.names_of(r)[0], [fr], wd)
                acc[r].setdefault(name, []).append(secs[0] if secs and rc == 0 else None)
        for po in R.PHOTO_ORDERS:
            for r in order:
                secs, wall, ok = photo_pool(r, po, wd)
                key = 'photos ' + ''.join(map(str, po))
                acc[r].setdefault(key + ' per photo', []).append(secs)
                acc[r].setdefault(key + ' process', []).append(wall if ok else None)
        print('round', k + 1, 'done', flush=True)
    json.dump({os.path.basename(r): v for r, v in acc.items()},
              open(os.path.join(R.OUT, 'timing.json'), 'w'), indent=1)
    keys = list(FRAMES) + [f'photos {"".join(map(str, p))} {w}' for p in R.PHOTO_ORDERS
                           for w in ('per photo', 'process')]
    print('| frame | ' + ' | '.join(os.path.basename(r)[:-3] for r in readers) + ' |')
    print('|---|' + '---|' * len(readers))
    for key in keys:
        cells = []
        for r in readers:
            v = acc[r].get(key)
            if not v:
                cells.append('-')
            elif key.endswith('per photo'):
                per = list(zip(*v))
                cells.append(' / '.join(f'{min(x):.2f}' for x in per))
            else:
                v = [x for x in v if x is not None]
                cells.append(f'{min(v):.2f} ({sorted(v)[len(v) // 2]:.2f})' if v else 'FAILED')
        print(f'| {key} | ' + ' | '.join(cells) + ' |')


if __name__ == '__main__':
    main()
