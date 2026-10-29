"""w4_slots.py -- which data SLOTS a reader reads, per frame and pooled (never
typed).  Every accepted block (a spy on the reader's block read: read_block
of the readable rungs and reader.py, rb of the minified readers) is mapped
to the true slot whose centre lies nearest its placed centre (truth
homography of the render); a slot is "in frame" when its 18 x 18 lattice
lies inside the image.  The frames are read in order as one run: since the
2026-10-20 night ruling a block's CRC covers the payload's header, so the
first header read is carried to the later frames, as the reader's own main
loop carries it.
Usage: python w4_slots.py READER.py FRAME [FRAME ...]
"""
import inspect
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from w4_debug import ns_of  # noqa: E402


def slots(ns, frame, known=None):
    """-> (data slots in frame, slots read, the payload's header after this
    frame)"""
    tj = json.load(open(frame[:-4] + '.json'))
    side = json.load(open(os.path.join(os.path.dirname(frame), tj['page_sidecar'])))
    Hm = np.array(tj['homography_grid_modules_to_px'])
    w, h = tj['size_px']

    def px(c, r):
        v = Hm @ [c, r, 1]
        return v[0] / v[2] - 0.5, v[1] / v[2] - 0.5
    data = {tuple(b) for b, c in zip(side['slot_block'], side['slot_chunk']) if c is not None}
    inf = set()
    for bi, bj in data:
        if all(0 <= x <= w - 1.001 and 0 <= y <= h - 1.001
               for x, y in (px(17 * bj + a, 17 * bi + b) for a in (.5, 17.5) for b in (.5, 17.5))):
            inf.add((bi, bj))
    got = []
    key = 'read_block' if 'read_block' in ns else 'rb'
    rb = ns[key]

    def spy(*a):
        out = rb(*a)
        s = a[1] if len(a) > 1 else a[0]          # read_block(value, s[, h6]) / rb(s)
        if out:
            c = s(0, 0) if callable(s) else s     # r00 passes spot(), the rungs a seed
            got.append((c[0] / 16, c[1] / 16))
        return out
    ns[key] = spy
    if 'read_frame' in ns:
        args = (frame, known) if len(inspect.signature(ns['read_frame']).parameters) > 1 \
            else (frame,)
        hd = ns['read_frame'](*args)[1]
        known = known or hd
    else:                                          # minified: globals h, j, z, then fm()
        ns['h'], ns['j'], ns['z'] = ns['ld'](frame)
        if isinstance(ns.get('e'), bytes):         # m11 on: e = the payload's header (b'': none)
            ns['e'] = known or b''
        r = ns['fm']()
        if isinstance(r[0], tuple):                # m11 on: fm -> ((pitch, seeds), header)
            ns['e'] = known = known or r[1] or b''
            if known:
                ns['wk'](*r[0])
    ns[key] = rb
    cen = {(bi, bj): px(17 * bj + 9.5, 17 * bi + 9.5) for bi, bj in data}
    read = set()
    for x, y in got:
        read.add(min(cen, key=lambda q: math.hypot(cen[q][0] - x, cen[q][1] - y)))
    return inf, read, known


if __name__ == '__main__':
    ns = ns_of(sys.argv[1])
    U, R, known = set(), set(), None
    for f in sys.argv[2:]:
        inf, read, known = slots(ns, os.path.abspath(f), known)
        U |= inf
        R |= read
        print(f'{os.path.basename(f):28s} data slots in frame {len(inf):3d}, read {len(read & inf):3d}'
              f' (+{len(read - inf)} outside), missed {sorted(inf - read)}')
    print(f'POOLED: data slots in some frame {len(U)}, read {len(R & U)}, missed {sorted(U - R)}')
