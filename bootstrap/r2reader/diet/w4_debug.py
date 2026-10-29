"""w4_debug.py -- a rung's stages on one frame against the truth (never typed).
Usage: python w4_debug.py READER FRAME
Prints the bullseyes found (with the true one nearest), each seed's clock
pose against the truth homography's local 17-module vectors, the header per
turn, and the walk's count.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import w4_harness as wh  # noqa: E402
from w4_one import path  # noqa: E402


def ns_of(reader):
    src = wh.rpy_of(reader)
    ns = {}
    exec(compile(src.split('chunks, heads, done')[0].split('# ======== main')[0]
                 .split('\nwhile ')[0], reader, 'exec'), ns)
    return ns


def main():
    reader, frame = sys.argv[1], path(sys.argv[2])
    ns = ns_of(reader)
    tj = json.load(open(frame[:-4] + '.json'))
    side = json.load(open(tj['page_sidecar']))
    Hm = np.array(tj['homography_grid_modules_to_px'])

    def px(c, r):
        v = Hm @ [c, r, 1]
        return v[0] / v[2] - 0.5, v[1] / v[2] - 0.5
    w, h, img = ns['load'](frame)
    value = ns['sampler'](img, w, h)
    found = ns['bullseyes'](img, ns['binarise'](img, w, h), w, h, value)
    print(len(found), 'bullseyes found')
    for f in found:
        x, y, p = f[1] / 16, f[2] / 16, f[3] / 256
        b = min(side['bullseyes'], key=lambda b: math.hypot(px(b['centre_col'] + .5, b['centre_row'] + .5)[0] - x,
                                                            px(b['centre_col'] + .5, b['centre_row'] + .5)[1] - y))
        tx, ty = px(b['centre_col'] + .5, b['centre_row'] + .5)
        print(f'  score {f[0]} at ({x:.1f}, {y:.1f}) pitch {p:.3f}; true {b["block"]} ({tx:.1f}, {ty:.1f}) '
              f'err {math.hypot(tx - x, ty - y) / p:.2f} mod')
        if 'clock' in ns or 'pose' in ns:
            A, B = ns.get('pose', ns.get('clock'))(value, f[1], f[2], f[3])
            c, r = b['centre_col'] + .5, b['centre_row'] + .5
            TA = [(px(c + 17, r)[i] - px(c, r)[i]) * 16 for i in (0, 1)]
            TB = [(px(c, r + 17)[i] - px(c, r)[i]) * 16 for i in (0, 1)]
            print(f'    clock A {A} B {B}; truth col {[round(v) for v in TA]} row {[round(v) for v in TB]}')
            s = [f[1], f[2], A, B]
            print('    headers', [(m, ns['header'](value, ns['turn'](s, m))) for m in range(4)])


if __name__ == '__main__':
    main()
