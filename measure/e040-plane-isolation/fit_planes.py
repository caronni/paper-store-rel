#!/usr/bin/env python3
"""e040 — per-plane page geometry and the spectral mixing model of a colour
capture, fitted against the emitted field.  MEASUREMENT ONLY: the truth
(`page000_gt.npy`) is read; nothing here can mint a certificate.

Geometry: for each plane (C from the red channel, M from green, Y from
blue) a grid of truth blocks is rendered at the nominal pitch and
cross-correlated (high-passed, FFT) with the scan around its predicted
position; every peak above a z bar is one correspondence cell-corner ->
scan px; an affine truth-cell -> scan-px is fitted per plane, twice
(the second pass predicts from the first fit with a tighter search).  A
quadratic fit is reported beside it so a non-affine page shows.

Mixing: on pixel blocks, every pixel's three plane bits come from each
plane's OWN affine (inverse-mapped), and  v = m0 + mC*C + mM*M + mY*Y  is
fitted by least squares over RGB.  B = [mC mM mY] inverted gives the three
isolating functionals: s = inv(B) (v - m0) estimates (C, M, Y) per pixel.

    PYTHONPATH=src env/bin/python measure/e040-plane-isolation/fit_planes.py \
        scan.tiff page000_gt.npy out.json --seed C:y,x M:y,x Y:y,x [--px-per-cell 8]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import tifffile
from scipy import ndimage

CHANNEL = {"C": 0, "M": 1, "Y": 2}
HIGHPASS_PX = 24


def highpass(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, np.float32)
    return a - ndimage.uniform_filter(a, HIGHPASS_PX)


def correlate_block(scan_chan, truth_block, pred_y, pred_x, pad, scale):
    """Return (dy, dx, z) of the truth block's best offset around its
    prediction, or None when the crop leaves the raster."""
    n = truth_block.shape[0]
    size = int(round(n * scale))
    y0, x0 = int(round(pred_y)) - pad, int(round(pred_x)) - pad
    y1, x1 = y0 + size + 2 * pad, x0 + size + 2 * pad
    if y0 < 0 or x0 < 0 or y1 > scan_chan.shape[0] or x1 > scan_chan.shape[1]:
        return None
    crop = np.asarray(scan_chan[y0:y1, x0:x1], np.float32)
    idx = (np.arange(size) / scale).astype(int)
    rendered = truth_block[idx][:, idx].astype(np.float32)
    a = -highpass(crop)
    t = highpass(rendered)
    cc = np.fft.irfft2(np.fft.rfft2(a) * np.conj(np.fft.rfft2(t, s=a.shape)), s=a.shape)
    win = cc[:2 * pad + 1, :2 * pad + 1]
    k = np.unravel_index(int(win.argmax()), win.shape)
    z = float((win.max() - win.mean()) / (win.std() + 1e-9))
    return k[0] - pad, k[1] - pad, z


def fit_affine(cells, px):
    """cells (n,2) [ty,tx] -> px (n,2) [y,x]; returns 2x3 and rms px."""
    design = np.column_stack([cells, np.ones(len(cells))])
    sol, *_ = np.linalg.lstsq(design, px, rcond=None)
    res = design @ sol - px
    return sol.T, float(np.sqrt((res ** 2).sum(1).mean()))


def fit_quadratic_rms(cells, px):
    ty, tx = cells[:, 0], cells[:, 1]
    design = np.column_stack([ty, tx, ty * tx, ty * ty, tx * tx, np.ones(len(ty))])
    sol, *_ = np.linalg.lstsq(design, px, rcond=None)
    res = design @ sol - px
    return float(np.sqrt((res ** 2).sum(1).mean()))


def apply(aff, ty, tx):
    return (aff[0, 0] * ty + aff[0, 1] * tx + aff[0, 2],
            aff[1, 0] * ty + aff[1, 1] * tx + aff[1, 2])


def invert(aff):
    m = np.array([[aff[0, 0], aff[0, 1]], [aff[1, 0], aff[1, 1]]])
    inv = np.linalg.inv(m)
    off = -inv @ np.array([aff[0, 2], aff[1, 2]])
    return inv, off


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scan")
    ap.add_argument("gt")
    ap.add_argument("out")
    ap.add_argument("--seed", nargs=3, required=True,
                    help="per-plane scan px of truth cell (0,0): C:y,x M:y,x Y:y,x")
    ap.add_argument("--px-per-cell", type=float, default=8.0)
    ap.add_argument("--block-cells", type=int, default=256)
    ap.add_argument("--z-bar", type=float, default=8.0)
    args = ap.parse_args()

    scan = tifffile.memmap(args.scan, mode="r")
    truth = np.unpackbits(np.load(args.gt), axis=2)        # (3, cells_y, cells_x)
    cells_y, cells_x = truth.shape[1:]
    seeds = {}
    for item in args.seed:
        name, yx = item.split(":")
        seeds[name] = tuple(float(v) for v in yx.split(","))
    s = args.px_per_cell
    out = {"scan": args.scan, "gt": args.gt, "scan_shape_yx": list(scan.shape[:2]),
           "cells_yx": [int(cells_y), int(cells_x)], "planes": {}}

    for name, chan in CHANNEL.items():
        plane = truth[chan]
        oy, ox = seeds[name]
        aff = np.array([[s, 0.0, oy], [0.0, s, ox]])
        record = {}
        for pass_index, (n, pad, step) in enumerate(((args.block_cells, 240, 1280),
                                                     (128, 64, 640))):
            pts_cells, pts_px, zs = [], [], []
            for ty0 in range(128, cells_y - n, step):
                for tx0 in range(128, cells_x - n, step):
                    py, px = apply(aff, ty0, tx0)
                    scale = float(np.sqrt(abs(np.linalg.det(aff[:, :2]))))
                    hit = correlate_block(scan[..., chan], plane[ty0:ty0 + n, tx0:tx0 + n],
                                          py, px, pad, scale)
                    if hit is None or hit[2] < args.z_bar:
                        continue
                    dy, dx, z = hit
                    pts_cells.append((ty0, tx0))
                    pts_px.append((round(py) + dy, round(px) + dx))
                    zs.append(z)
            pts_cells = np.asarray(pts_cells, float)
            pts_px = np.asarray(pts_px, float)
            if pass_index == 1:
                record["blocks"] = [{"ty0": int(c[0]), "tx0": int(c[1]), "py": float(q[0]),
                                     "px": float(q[1]), "z": float(z), "cells": n}
                                    for c, q, z in zip(pts_cells, pts_px, zs)]
            if len(pts_cells) < 4:
                raise SystemExit(f"plane {name} pass {pass_index}: only {len(pts_cells)} blocks matched")
            aff, rms = fit_affine(pts_cells, pts_px)
            record[f"pass{pass_index}"] = {
                "blocks": int(len(pts_cells)), "z_min": float(min(zs)), "z_median": float(np.median(zs)),
                "affine_rms_px": rms, "quadratic_rms_px": fit_quadratic_rms(pts_cells, pts_px)}
            print(f"{name} pass {pass_index}: {len(pts_cells)} blocks, z min {min(zs):.1f}, "
                  f"affine rms {rms:.2f} px, quadratic rms {record[f'pass{pass_index}']['quadratic_rms_px']:.2f} px")
        record["affine_cell_to_px"] = aff.tolist()
        record["px_per_cell"] = [float(np.hypot(aff[0, 0], aff[1, 0])), float(np.hypot(aff[0, 1], aff[1, 1]))]
        record["rotation_rad"] = float(np.arctan2(aff[1, 0], aff[0, 0]))
        record["origin_px"] = [float(aff[0, 2]), float(aff[1, 2])]
        out["planes"][name] = record

    # ---- mixing model on LOCALLY registered pixel blocks: a global affine
    # misplaces cells by ~2 at this scale (its rms above), which would
    # shrink every coefficient toward zero; each plane's own matched
    # block pose (pass 1, 128 cells) is exact to ~1 px over the block.
    H, W = scan.shape[:2]
    scale = {n: float(np.sqrt(abs(np.linalg.det(np.asarray(out["planes"][n]["affine_cell_to_px"])[:, :2]))))
             for n in CHANNEL}
    by_key = {n: {(b["ty0"], b["tx0"]): b for b in out["planes"][n]["blocks"]} for n in CHANNEL}
    common = sorted(set(by_key["C"]) & set(by_key["M"]) & set(by_key["Y"]),
                    key=lambda k: abs(k[0] - cells_y // 2) + abs(k[1] - cells_x // 2))[:12]
    rows_v, rows_b = [], []
    for key in common:
        bc = by_key["C"][key]
        n = bc["cells"]
        y0, x0 = int(round(bc["py"])) + 64, int(round(bc["px"])) + 64     # inside the C block
        size = int(n * scale["C"]) - 128
        block = np.asarray(scan[y0:y0 + size, x0:x0 + size, :], np.float32).reshape(-1, 3)
        yy, xx = np.mgrid[y0:y0 + size, x0:x0 + size]
        bits = []
        ok = np.ones(yy.size, bool)
        for name, chan in CHANNEL.items():
            bp = by_key[name][key]
            cy = np.floor(bp["ty0"] + (yy.ravel() - bp["py"]) / scale[name]).astype(int)
            cx = np.floor(bp["tx0"] + (xx.ravel() - bp["px"]) / scale[name]).astype(int)
            ok &= (cy >= 0) & (cx >= 0) & (cy < cells_y) & (cx < cells_x)
            bits.append(truth[chan][np.clip(cy, 0, cells_y - 1), np.clip(cx, 0, cells_x - 1)])
        bits = np.stack(bits, 1)[ok].astype(np.float64)
        rows_v.append(block[ok]); rows_b.append(bits)
    out["mixing_blocks"] = [list(k) for k in common]
    v = np.concatenate(rows_v); b = np.concatenate(rows_b)
    design = np.column_stack([np.ones(len(b)), b])
    coef, *_ = np.linalg.lstsq(design, v, rcond=None)       # (4, 3): rows m0, mC, mM, mY
    resid = v - design @ coef
    m0, B = coef[0], coef[1:].T                              # B columns = mC, mM, mY
    Binv = np.linalg.inv(B)
    est = (v - m0) @ Binv.T                                  # per-pixel plane estimates
    out["mixing"] = {
        "pixels": int(len(b)), "m0": m0.tolist(),
        "mC": coef[1].tolist(), "mM": coef[2].tolist(), "mY": coef[3].tolist(),
        "residual_sd_rgb": resid.std(0).tolist(),
        "B_inverse": Binv.tolist(),
        "pixel_hard_error": {n: float(np.mean((est[:, i] > 0.5) != (b[:, i] > 0.5)))
                             for i, n in enumerate("CMY")},
        "pixel_estimate_sd": {n: float(est[b[:, i] > 0.5, i].std()) for i, n in enumerate("CMY")},
    }
    print("mixing: m0", np.round(m0, 1), "mC", np.round(coef[1], 1), "mM", np.round(coef[2], 1),
          "mY", np.round(coef[3], 1), "pixel hard error", out["mixing"]["pixel_hard_error"])
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
