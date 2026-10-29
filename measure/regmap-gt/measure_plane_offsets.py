#!/usr/bin/env python
# Historical record of e033 (supervised per-plane registration on sheet I, the AltaLink Y sinusoid; PAGE-FIELD B3's
# reference), retired from scratch/xerox-v1-20260818/regmap-gt/ 2026-10-09; inputs in the evidence archive.
# Regenerates build/regmap-gt/{plane-offsets.json,per-column.json,plane-offsets.png} with: PYTHONPATH=src:. env/bin/python measure/regmap-gt/measure_plane_offsets.py --evidence-root DIR [--rows N] [--jobs N]
"""Per-plane print registration on a real scan, measured against the GT bitmap.

Hypothesis under test: the Y plane carries a column-periodic registration
offset (fraction of a cell) that corrupts Y cell sampling in the decoder's
plane-common poses, explaining column-banded Y certificate failure.

Measurement: for a grid of patches (one printed tile each), lock a
plane-common registration, then measure each plane's own subpixel
displacement against the ground-truth bitmap.  The discriminating quantity
is dY - (dC+dM)/2; the control is dC - dM.

READ-ONLY: opens the scan TIFF and page000_gt.npy only.  Never touches
receive.state.

Usage:
    PYTHONPATH=src:. env/bin/python measure/regmap-gt/measure_plane_offsets.py --evidence-root DIR [--rows N] [--jobs N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _common import (gt_patch, scan_patch, highpass, xcorr_shift,  # noqa: E402
                     TILES_YX, TILE_DOTS, PX_PER_DOT, OUT_DIR,
                     configure, _evidence)
from _subpix import lk_shift, blur_model                            # noqa: E402

# scan <- GT-dot affine, fitted by _anchor.py on nine wide-search anchors
#   y_scan = AY[0]*yd + AY[1]*xd + AY[2]
#   x_scan = AX[0]*yd + AX[1]*xd + AX[2]
AY = (4.005148, 0.003337, 273.43)
AX = (-0.001985, 4.002649, 451.74)

# B-channel crosstalk removal: B_res = B - CT[0]*R - CT[1]*G  (fitted below)
CT = (-0.03788, 0.47056)

PATCH_DOTS = TILE_DOTS          # 128 dots = 512 scan px = 64 cells
PAD = 44                        # search headroom around the nominal window
HP = 25                         # highpass boxcar, px
COMMON_SEARCH = 32
PLANE_SEARCH = 12
MODEL_SIGMA = 2.0

# decoder certificate residue (failed tiles out of 53) per tile_x
RESIDUE = [7, 1, 21, 5, 0, 0, 0, 14, 53, 38, 37, 39, 0, 0, 0, 45, 49, 45,
           31, 47, 2, 0, 0, 0, 4, 3, 5, 43, 50, 24, 12, 0, 2, 0, 0, 0, 4]
DEAD = {8, 16, 28, 9, 10, 11, 15, 17, 18, 19, 27, 29}
CLEAN = {4, 5, 6, 12, 13, 14, 21, 22, 23, 31, 33, 34, 35}


def nominal(yd: float, xd: float):
    return (AY[0] * yd + AY[1] * xd + AY[2],
            AX[0] * yd + AX[1] * xd + AX[2])


def up4(a):
    return np.kron(a, np.ones((PX_PER_DOT, PX_PER_DOT), np.float32))


def _lock(model, tgt, search, refine=True):
    """FFT integer lock + LK subpixel.  Returns (dy,dx,peak,ratio,corr,src)."""
    dy, dx, peak, ratio = xcorr_shift(model, tgt, search)
    dy, dx = -dy, -dx        # displacement of scan content vs the model
    ly, lx, corr = lk_shift(model, tgt, init=(round(dy), round(dx)))
    if (refine and np.isfinite(ly)
            and abs(ly - dy) < 1.0 and abs(lx - dx) < 1.0):
        return ly, lx, peak, ratio, corr, "lk"
    return dy, dx, peak, ratio, corr, "fft"


def measure_patch(ty: int, tx: int):
    y0d = ty * TILE_DOTS
    x0d = tx * TILE_DOTS
    n = PATCH_DOTS * PX_PER_DOT
    yc, xc = nominal(y0d + PATCH_DOTS / 2.0, x0d + PATCH_DOTS / 2.0)
    oy = int(round(yc - n / 2)) - PAD
    ox = int(round(xc - n / 2)) - PAD
    sp = scan_patch(oy, ox, n + 2 * PAD, n + 2 * PAD)
    if sp.shape[0] != n + 2 * PAD or sp.shape[1] != n + 2 * PAD:
        return None

    # ink-positive, illumination-free channel fields (full padded crop)
    R = -highpass(sp[:, :, 0], HP)
    G = -highpass(sp[:, :, 1], HP)
    B = -highpass(sp[:, :, 2], HP)
    Bres = B - CT[0] * R - CT[1] * G

    gts = [gt_patch(p, y0d, x0d, PATCH_DOTS, PATCH_DOTS).astype(np.float32)
           for p in range(3)]
    models = [highpass(blur_model(up4(g), MODEL_SIGMA), HP) for g in gts]
    m_common = highpass(blur_model(up4(sum(gts)), MODEL_SIGMA), HP)

    def win(a, sy=0, sx=0):
        return a[PAD + sy:PAD + sy + n, PAD + sx:PAD + sx + n]

    cy, cx, cpk, crat, ccorr, _ = _lock(m_common, win(R + G + Bres),
                                        COMMON_SEARCH)
    iy, ix = int(round(cy)), int(round(cx))
    if abs(iy) > PAD - 14 or abs(ix) > PAD - 14:
        return None

    out = {"tile_y": ty, "tile_x": tx,
           "common_dy": cy, "common_dx": cx, "common_corr": ccorr,
           "common_peak": cpk, "common_ratio": crat}
    fields = {"C": R, "M": G, "Y": Bres}
    for pi, name in enumerate("CMY"):
        dy, dx, pk, rat, corr, src = _lock(
            models[pi], win(fields[name], iy, ix), PLANE_SEARCH)
        out[f"d{name}_y"] = iy + dy
        out[f"d{name}_x"] = ix + dx
        out[f"{name}_peak"] = pk
        out[f"{name}_ratio"] = rat
        out[f"{name}_corr"] = corr
        out[f"{name}_src"] = src
    # raw-B control for Y (no crosstalk removal)
    dy, dx, pk, rat, corr, _ = _lock(models[2], win(B, iy, ix), PLANE_SEARCH)
    out["dYraw_y"] = iy + dy
    out["dYraw_x"] = ix + dx
    out["Yraw_corr"] = corr
    for ax in "yx":
        out[f"dY_rel_{ax}"] = out[f"dY_{ax}"] - 0.5 * (out[f"dC_{ax}"]
                                                       + out[f"dM_{ax}"])
        out[f"dCM_{ax}"] = out[f"dC_{ax}"] - out[f"dM_{ax}"]
    return out


def fit_crosstalk(n_patches: int = 12):
    """Global least-squares B ~ a*R + b*G on highpassed channels."""
    rng = np.random.default_rng(7)
    A = []
    y = []
    for _ in range(n_patches):
        ty = int(rng.integers(2, TILES_YX[0] - 2))
        tx = int(rng.integers(2, TILES_YX[1] - 2))
        yc, xc = nominal(ty * TILE_DOTS + 64, tx * TILE_DOTS + 64)
        sp = scan_patch(int(yc) - 256, int(xc) - 256, 512, 512)
        R = highpass(sp[:, :, 0], HP)[32:-32, 32:-32].ravel()
        G = highpass(sp[:, :, 1], HP)[32:-32, 32:-32].ravel()
        B = highpass(sp[:, :, 2], HP)[32:-32, 32:-32].ravel()
        A.append(np.stack([R, G], axis=1))
        y.append(B)
    A = np.concatenate(A)
    y = np.concatenate(y)
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return float(coef[0]), float(coef[1])


def _job(args):
    try:
        return measure_patch(*args)
    except Exception as exc:                       # noqa: BLE001
        return {"tile_y": args[0], "tile_x": args[1], "error": repr(exc)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=11)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default=str(OUT_DIR / "plane-offsets.json"))
    _evidence.add_argument(ap)
    ap.add_argument("--fit-crosstalk", action="store_true")
    args = ap.parse_args()
    configure(args.evidence_root)

    if args.fit_crosstalk:
        print("crosstalk fit B ~ a*R + b*G:", fit_crosstalk())
        return

    rows = np.unique(np.linspace(1, TILES_YX[0] - 2, args.rows).round()
                     .astype(int))
    tasks = [(int(ty), int(tx)) for ty in rows for tx in range(TILES_YX[1])]
    print(f"{len(tasks)} patches, rows={list(rows)}", flush=True)
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            res = list(ex.map(_job, tasks, chunksize=4))
    else:
        res = [_job(t) for t in tasks]
    res = [r for r in res if r]
    with open(args.out, "w") as fh:
        json.dump({"affine_y": AY, "affine_x": AX, "crosstalk": CT,
                   "patch_dots": PATCH_DOTS, "px_per_dot": PX_PER_DOT,
                   "residue": RESIDUE, "rows": [int(r) for r in rows],
                   "patches": res}, fh, indent=1)
    print(f"wrote {args.out}: {len(res)} patches")
    # aggregate: per-column table + plane-offsets.png
    import runpy
    runpy.run_path(os.path.join(HERE, "report.py"), run_name="__main__")


if __name__ == "__main__":
    main()
