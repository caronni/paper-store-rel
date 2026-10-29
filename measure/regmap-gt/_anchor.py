# Historical record of e033 (supervised per-plane registration on sheet I, the AltaLink Y sinusoid; PAGE-FIELD B3's
# reference), retired from scratch/xerox-v1-20260818/regmap-gt/ 2026-10-09; inputs in the evidence archive.
# Regenerates build/regmap-gt/affine.npy with: PYTHONPATH=src:. env/bin/python measure/regmap-gt/_anchor.py --evidence-root DIR
"""Stage 0: find the global scan<-GT affine by wide-search anchor matching."""
from __future__ import annotations
import argparse
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (gt_patch, scan_patch, highpass, xcorr_shift,  # noqa: E402
                     FIELD_DOTS_YX, PX_PER_DOT, OUT_DIR, configure, _evidence)


def gt_ink(y0d, x0d, hd, wd, planes=(0, 1, 2)):
    """Summed GT ink over planes, dot resolution."""
    acc = np.zeros((hd, wd), np.float32)
    for p in planes:
        acc += gt_patch(p, y0d, x0d, hd, wd)
    return acc


def up4(a):
    return np.kron(a, np.ones((PX_PER_DOT, PX_PER_DOT), np.float32))


def match(y0d, x0d, nd, affine, max_shift, hp=25, planes=(0, 1, 2)):
    """Match a nd x nd dot GT block; affine maps dot->scan px."""
    ref = highpass(up4(gt_ink(y0d, x0d, nd, nd, planes)), hp)
    n = nd * PX_PER_DOT
    yc, xc = affine(y0d + nd / 2, x0d + nd / 2)
    pad = max_shift + 8
    sp = scan_patch(int(round(yc - n / 2)) - pad, int(round(xc - n / 2)) - pad,
                    n + 2 * pad, n + 2 * pad)
    dark = 765.0 - sp.sum(axis=2)
    dark = highpass(dark, hp)
    tgt = dark[pad:pad + n, pad:pad + n]
    dy, dx, peak, ratio = xcorr_shift(ref, tgt, max_shift)
    # scan feature displacement relative to nominal position
    return -dy, -dx, peak, ratio


def make_affine(p):
    """p = (y0, x0, sy, sx, tilt) ; tilt in rad, small."""
    y0, x0, sy, sx, t = p

    def f(yd, xd):
        y = y0 + sy * yd + t * sx * xd
        x = x0 + sx * xd - t * sy * yd
        return y, x
    return f


if __name__ == "__main__":
    _ap = argparse.ArgumentParser()
    _evidence.add_argument(_ap)
    configure(_ap.parse_args().evidence_root)
    # initial guess from the supplied bbox (y trustworthy, x loose)
    a0 = make_affine((164.0, 448.0, 27300.0 / 6784, 4.0, -0.00342))
    H, W = FIELD_DOTS_YX
    nd = 256          # 1024 px
    pts = []
    for fy in (0.08, 0.5, 0.92):
        for fx in (0.06, 0.5, 0.94):
            y0d = int((H - nd) * fy)
            x0d = int((W - nd) * fx)
            oy, ox, pk, r = match(y0d, x0d, nd, a0, 300)
            pts.append((y0d + nd / 2, x0d + nd / 2, oy, ox, pk, r))
            print(f"yd={y0d+nd/2:7.0f} xd={x0d+nd/2:7.0f} "
                  f"off_y={oy:8.2f} off_x={ox:8.2f} peak={pk:.4f} r={r:.1f}")
    P = np.array(pts)
    # refit affine: scan = A @ [yd, xd, 1]
    M = np.stack([P[:, 0], P[:, 1], np.ones(len(P))], axis=1)
    ys, xs = a0(P[:, 0], P[:, 1])
    ys = ys + P[:, 2]
    xs = xs + P[:, 3]
    cy = np.linalg.lstsq(M, ys, rcond=None)[0]
    cx = np.linalg.lstsq(M, xs, rcond=None)[0]
    print("\ny_scan = %.4f*yd + %.6f*xd + %.2f" % (cy[0], cy[1], cy[2]))
    print("x_scan = %.6f*yd + %.4f*xd + %.2f" % (cx[0], cx[1], cx[2]))
    res_y = ys - M @ cy
    res_x = xs - M @ cx
    print("residual y", np.round(res_y, 2))
    print("residual x", np.round(res_x, 2))
    np.save(str(OUT_DIR / "affine.npy"), np.stack([cy, cx]))
