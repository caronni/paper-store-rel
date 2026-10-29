#!/usr/bin/env python3
"""e042 — raw cell error of a ONE-PLANE (K) holo page per tile, at truth-fitted poses.

MEASUREMENT ONLY: the emitted field (`page000_gt.npy`, one bit per cell packed along x,
1 = inked) places the page; nothing here can mint a certificate.  The numbers are the
ceiling a blind reader could reach with perfect placement, hard decisions, no context.

Placement: the field's bounding box on a decimated scan gives a first affine (cells ->
scan px); a grid of 128x128-cell truth blocks, each cross-correlated (high-passed FFT)
with the scan around its prediction, gives correspondences for a least-squares affine;
then every 64x64-cell tile is refined by its own truth block within +-SEARCH px.

Per tile, at the refined pose, every cell centre is sampled after a box aperture of
round(0.7 x px per cell) (the receiver's calibrate.APERTURE_CELLS), dark = inked, and
compared with the truth under two thresholds: GENIE (midpoint of the truth-conditional
means: the best single threshold for that tile) and BLIND (the 25th/75th-percentile
midpoint over the tile's cells, as e040's addressability instrument).  The tile's 100
address-word sites (words.word_site_index of the row's site seed) are counted separately:
BCH(127,50) -> (100,23) corrects t = 13, so <= 13 wrong sites = ADDRESSABLE AT THE TRUE
POSE (the receiver's placement gates are stricter: an upper bound on what it can address).

    PYTHONPATH=src:. env/bin/python measure/e042-c1-truth/c1_tile_error.py \\
        scan.tiff page000_gt.npy --format c1-k-r0700@106x74 --out-dir DIR
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage

from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.plugins import words


def row_px_per_cell(scan_dpi: float, cell_dots: int, engine_dpi: float = 600.0) -> float:
    return scan_dpi / engine_dpi * cell_dots

TILE = 64
BLOCK = 128
EMULATE = {"1x1 (c1)": (1, 1), "1 wide x 2 tall": (2, 1), "2 wide x 1 tall": (1, 2), "2x2 (c2)": (2, 2)}
BCH_T = 13
HIGHPASS = 24


def highpass(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, np.float32)
    return a - ndimage.uniform_filter(a, HIGHPASS)


def field_bbox(scan: np.ndarray, k: int = 16) -> tuple[float, float, float, float]:
    """(top, left, bottom, right) scan px of the printed field from a decimated darkness map."""
    H, W = (scan.shape[0] // k) * k, (scan.shape[1] // k) * k
    small = np.empty((H // k, W // k), np.float32)
    for r in range(0, H, k * 256):
        blk = np.asarray(scan[r:min(r + k * 256, H), :W], np.float32)
        small[r // k:r // k + blk.shape[0] // k] = blk.reshape(-1, k, W // k, k).mean((1, 3))
    paper = np.percentile(small, 99)
    dark = small < paper - 25
    rows = np.flatnonzero(dark.mean(1) > 0.5)
    cols = np.flatnonzero(dark.mean(0) > 0.5)
    return rows[0] * k, cols[0] * k, (rows[-1] + 1) * k, (cols[-1] + 1) * k


def correlate(scan, truth_block, py, px, scale, pad, z_bar=6.0):
    """(dy, dx) of a truth block (cells) rendered at `scale` px/cell around its predicted
    top-left (py, px) in scan px; None off-raster or without a clear peak (z < z_bar)."""
    n_y, n_x = truth_block.shape
    sy, sx = int(round(n_y * scale)), int(round(n_x * scale))
    r0, c0 = int(round(py)) - pad, int(round(px)) - pad
    r1, c1 = r0 + sy + 2 * pad, c0 + sx + 2 * pad
    if r0 < 0 or c0 < 0 or r1 > scan.shape[0] or c1 > scan.shape[1]:
        return None
    crop = -highpass(np.asarray(scan[r0:r1, c0:c1], np.float32))
    iy = np.minimum((np.arange(sy) / scale).astype(int), n_y - 1)
    ix = np.minimum((np.arange(sx) / scale).astype(int), n_x - 1)
    t = highpass(truth_block[iy][:, ix].astype(np.float32))
    cc = np.fft.irfft2(np.fft.rfft2(crop) * np.conj(np.fft.rfft2(t, s=crop.shape)), s=crop.shape)
    win = cc[:2 * pad + 1, :2 * pad + 1]
    k = np.unravel_index(int(win.argmax()), win.shape)
    z = (win[k] - win.mean()) / (win.std() + 1e-9)
    if z < z_bar:
        return None
    dy, dx = float(k[0]), float(k[1])
    if 0 < k[0] < win.shape[0] - 1:          # parabolic sub-pixel
        a, b, c = win[k[0] - 1, k[1]], win[k], win[k[0] + 1, k[1]]
        dy += 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
    if 0 < k[1] < win.shape[1] - 1:
        a, b, c = win[k[0], k[1] - 1], win[k], win[k[0], k[1] + 1]
        dx += 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
    return dy - pad - (py - round(py)), dx - pad - (px - round(px))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scan")
    ap.add_argument("gt")
    ap.add_argument("--format", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--search", type=int, default=24, help="per-tile refinement radius, scan px")
    ap.add_argument("--rot180", action="store_true", help="the sheet lies upside down on the glass")
    ap.add_argument("--emulate", action="store_true",
                    help="also read the c1 page as coarser cells: aligned groups of cells whose truth is uniform "
                         "(1x2 = two cells stacked, 2x1 = side by side, 2x2) are read as one cell (mean of their "
                         "samples, per-tile genie threshold) — an ESTIMATE of how 1x2 / 2x1 / c2 cells would read; "
                         "the 2x2 row checks the estimate against the engine's measured c2")
    ap.add_argument("--probe", type=int, default=0, metavar="N",
                    help="pose/aperture self-check on N random placed tiles: the genie error at the fitted "
                         "pose against offsets of -1..+1 px and apertures 1/3/5 (a pose artefact shows as a "
                         "lower error off the fitted pose)")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    scan = tifffile.memmap(args.scan, mode="r")
    if scan.ndim == 3:
        scan = np.asarray(scan).mean(2).astype(np.uint8)
    if args.rot180:
        scan = np.ascontiguousarray(np.asarray(scan)[::-1, ::-1])
    truth = np.unpackbits(np.load(args.gt), axis=1).astype(bool)          # (cells_y, cells_x)
    row = resolve_format_ref(args.format)
    cy_n, cx_n = truth.shape
    tiles_y, tiles_x = cy_n // TILE, cx_n // TILE
    site_index = words.word_site_index(row.sites_seed)
    sites = np.argwhere(site_index >= 0)
    assert len(sites) == 100, len(sites)

    # 1. first affine from the field's top-left corner and the nominal pitch (the scan's right
    #    edge can read dark: the bounding box's far corner is not trusted)
    top, left, bottom, right = field_bbox(scan)
    nominal = float(row_px_per_cell(scan_dpi=2400.0, cell_dots=1))
    aff = np.array([[nominal, 0.0, top], [0.0, nominal, left]])
    print(f"field bbox px {top},{left}..{bottom},{right}; nominal px/cell {nominal:.3f}")

    def blocks(stride, pad, z_bar, predict):
        src, dst = [], []
        for by in range(0, cy_n - BLOCK + 1, stride):
            for bx in range(0, cx_n - BLOCK + 1, stride):
                py, px = predict(by, bx)
                d = correlate(scan, truth[by:by + BLOCK, bx:bx + BLOCK], py, px, nominal, pad, z_bar)
                if d is not None:
                    src.append((by, bx))
                    dst.append((py + d[0], px + d[1]))
        return np.array(src, float), np.array(dst, float)

    def robust_fit(src, dst, design):
        keep = np.ones(len(src), bool)
        for _ in range(4):
            X = design(src[keep])
            sol, *_ = np.linalg.lstsq(X, dst[keep], rcond=None)
            res = np.hypot(*(dst - design(src) @ sol).T)
            mad = np.median(res[keep]) + 1e-6
            keep = res < max(3.0, 4.0 * mad)
        return sol, res, keep

    lin = lambda c: np.column_stack([c[:, 0], c[:, 1], np.ones(len(c))])
    quad = lambda c: np.column_stack([c[:, 0], c[:, 1], np.ones(len(c)), c[:, 0] ** 2,
                                      c[:, 0] * c[:, 1], c[:, 1] ** 2])
    src, dst = blocks(BLOCK * 3, 160, 8.0, lambda by, bx: aff @ np.array([by, bx, 1.0]))
    sol, res, keep = robust_fit(src, dst, lin)
    aff = sol.T
    print(f"coarse: {keep.sum()}/{len(src)} blocks kept; residual rms {np.sqrt((res[keep] ** 2).mean()):.2f} px")
    src, dst = blocks(BLOCK * 2, 32, 6.0, lambda by, bx: aff @ np.array([by, bx, 1.0]))
    qsol, res, keep = robust_fit(src, dst, quad)
    print(f"field:  {keep.sum()}/{len(src)} blocks kept; quadratic residual rms "
          f"{np.sqrt((res[keep] ** 2).mean()):.2f} px, max {res[keep].max():.1f}")

    def predict(cy, cx):
        return quad(np.array([[cy, cx]], float))[0] @ qsol

    scale = float(np.sqrt(abs(np.linalg.det(aff[:, :2]))))
    aperture = max(1, int(round(0.7 * scale)))

    def jacobian(cy, cx):
        """local d(scan px)/d(cell) of the quadratic field at (cy, cx): rows d/dcy, d/dcx."""
        dy = np.array([1.0, 0.0, 0.0, 2 * cy, cx, 0.0]) @ qsol
        dx = np.array([0.0, 1.0, 0.0, 0.0, cy, 2 * cx]) @ qsol
        return np.array([dy, dx])
    shifts = {}
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            py, px = predict(ty * TILE, tx * TILE)
            d = correlate(scan, truth[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE],
                          py, px, scale, args.search, 5.0)
            if d is not None:
                shifts[(ty, tx)] = d
    first = len(shifts)
    for _ in range(3):                                   # grow from placed neighbours, tight search
        added = 0
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                if (ty, tx) in shifts:
                    continue
                nb = [shifts[(ty + a, tx + b)] for a in range(-2, 3) for b in range(-2, 3)
                      if (ty + a, tx + b) in shifts]
                if len(nb) < 3:
                    continue
                m = np.median(np.array(nb), axis=0)
                py, px = predict(ty * TILE, tx * TILE)
                d = correlate(scan, truth[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE],
                              py + m[0], px + m[1], scale, 6, 4.0)
                if d is not None:
                    shifts[(ty, tx)] = (m[0] + d[0], m[1] + d[1])
                    added += 1
        if not added:
            break
    print(f"tiles placed: {first} by wide search (+-{args.search} px), {len(shifts)} after growth")
    rows, err_map, word_map = [], np.full((tiles_y, tiles_x), np.nan), np.full((tiles_y, tiles_x), np.nan)
    cyy, cxx = np.mgrid[0:TILE, 0:TILE]
    emu = {name: [0, 0] for name in EMULATE}
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            c0y, c0x = ty * TILE, tx * TILE
            tb = truth[c0y:c0y + TILE, c0x:c0x + TILE]
            py, px = predict(c0y, c0x)
            d = shifts.get((ty, tx))
            if d is None:
                rows.append({"ty": ty, "tx": tx, "placed": 0})
                continue
            ly, lx = cyy + 0.5, cxx + 0.5
            J = jacobian(c0y + TILE / 2, c0x + TILE / 2)
            gy = py + J[0, 0] * ly + J[1, 0] * lx + d[0] - 0.5
            gx = px + J[0, 1] * ly + J[1, 1] * lx + d[1] - 0.5
            r0 = int(np.floor(gy.min())) - 4
            c0 = int(np.floor(gx.min())) - 4
            r1 = int(np.ceil(gy.max())) + 5
            c1 = int(np.ceil(gx.max())) + 5
            crop = np.asarray(scan[max(r0, 0):r1, max(c0, 0):c1], np.float32)
            if aperture > 1:
                crop = ndimage.uniform_filter(crop, aperture)
            v = ndimage.map_coordinates(crop, [gy - max(r0, 0), gx - max(c0, 0)], order=1, mode="nearest")
            ink, blank = v[tb], v[~tb]
            genie = 0.5 * (ink.mean() + blank.mean())
            lo, hi = np.percentile(v, (25, 75))
            blind = 0.5 * (lo + hi)
            e_genie = float(np.mean((v < genie) != tb))
            e_blind = float(np.mean((v < blind) != tb))
            ws = v[sites[:, 0], sites[:, 1]]
            wt = tb[sites[:, 0], sites[:, 1]]
            w_err = int(np.count_nonzero((ws < blind) != wt))
            dprime = float((blank.mean() - ink.mean()) / (0.5 * (ink.std() + blank.std()) + 1e-9))
            if args.emulate:
                for name, (gy_, gx_) in EMULATE.items():
                    vv = v.reshape(TILE // gy_, gy_, TILE // gx_, gx_)
                    tt = tb.reshape(TILE // gy_, gy_, TILE // gx_, gx_)
                    uni = tt.all(axis=(1, 3)) | (~tt).all(axis=(1, 3))
                    if uni.sum() < 20:
                        continue
                    val = vv.mean(axis=(1, 3))[uni]
                    lab = tt.all(axis=(1, 3))[uni]
                    if lab.all() or (~lab).all():
                        continue
                    g = 0.5 * (val[lab].mean() + val[~lab].mean())
                    emu[name][0] += int(np.count_nonzero((val < g) != lab))
                    emu[name][1] += int(lab.size)
            err_map[ty, tx] = e_genie
            word_map[ty, tx] = w_err
            rows.append({"ty": ty, "tx": tx, "placed": 1, "shift_dy_px": round(d[0], 2),
                         "shift_dx_px": round(d[1], 2), "err_genie": round(e_genie, 5),
                         "err_blind": round(e_blind, 5), "word_errors": w_err,
                         "addressable": int(w_err <= BCH_T), "dprime": round(dprime, 3),
                         "ink_mean": round(float(ink.mean()), 2), "blank_mean": round(float(blank.mean()), 2)})
    if args.probe:
        rng = np.random.default_rng(0)
        cand = [(r["ty"], r["tx"]) for r in rows if r["placed"]]
        pick = [cand[k] for k in rng.choice(len(cand), min(args.probe, len(cand)), replace=False)]
        offs = [(oy, ox) for oy in (-1.0, -0.5, 0.0, 0.5, 1.0) for ox in (-1.0, -0.5, 0.0, 0.5, 1.0)]
        table = {}
        for ap_px in (1, 3, 5):
            gains = []
            for ty, tx in pick:
                c0y, c0x = ty * TILE, tx * TILE
                tb = truth[c0y:c0y + TILE, c0x:c0x + TILE]
                py, px = predict(c0y, c0x)
                d = shifts[(ty, tx)]
                J = jacobian(c0y + TILE / 2, c0x + TILE / 2)
                ly, lx = cyy + 0.5, cxx + 0.5
                gy0 = py + J[0, 0] * ly + J[1, 0] * lx + d[0] - 0.5
                gx0 = px + J[0, 1] * ly + J[1, 1] * lx + d[1] - 0.5
                r0, c0 = int(np.floor(gy0.min())) - 6, int(np.floor(gx0.min())) - 6
                crop = np.asarray(scan[max(r0, 0):int(np.ceil(gy0.max())) + 7,
                                       max(c0, 0):int(np.ceil(gx0.max())) + 7], np.float32)
                if ap_px > 1:
                    crop = ndimage.uniform_filter(crop, ap_px)
                errs = []
                for oy, ox in offs:
                    v = ndimage.map_coordinates(crop, [gy0 + oy - max(r0, 0), gx0 + ox - max(c0, 0)],
                                                order=1, mode="nearest")
                    g = 0.5 * (v[tb].mean() + v[~tb].mean())
                    errs.append(float(np.mean((v < g) != tb)))
                errs = np.array(errs)
                gains.append((errs[offs.index((0.0, 0.0))], errs.min(), offs[int(errs.argmin())]))
            at = np.array([g[0] for g in gains])
            best = np.array([g[1] for g in gains])
            table[ap_px] = {"at_pose_median": float(np.median(at)), "best_offset_median": float(np.median(best)),
                            "share_best_at_zero": float(np.mean([g[2] == (0.0, 0.0) for g in gains]))}
            print(f"probe aperture {ap_px} px: genie error at the fitted pose {np.median(at):.4f}, best of 25 "
                  f"offsets {np.median(best):.4f}; best offset = (0,0) in {table[ap_px]['share_best_at_zero']:.0%}")
        json.dump(table, open(out / "probe.json", "w"), indent=1)
    keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[-1].keys()).index(k) if k in rows[-1] else 99)
    with open(out / "tiles.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    placed = [r for r in rows if r["placed"]]
    eg = np.array([r["err_genie"] for r in placed])
    eb = np.array([r["err_blind"] for r in placed])
    we = np.array([r["word_errors"] for r in placed])
    addr = [r for r in placed if r["addressable"]]
    ea = np.array([r["err_genie"] for r in addr]) if addr else np.array([np.nan])
    eab = np.array([r["err_blind"] for r in addr]) if addr else np.array([np.nan])
    summ = {"format": args.format, "scan": args.scan, "aperture_px": aperture, "px_per_cell": scale,
            "tiles": tiles_y * tiles_x, "placed": len(placed),
            "err_genie": {"mean": float(eg.mean()), "p10": float(np.percentile(eg, 10)),
                          "median": float(np.median(eg)), "p90": float(np.percentile(eg, 90)),
                          "min": float(eg.min())},
            "err_blind": {"mean": float(eb.mean()), "median": float(np.median(eb)), "min": float(eb.min())},
            "word_errors": {"median": float(np.median(we)), "p10": float(np.percentile(we, 10)),
                            "min": int(we.min())},
            "addressable_at_truth_pose": len(addr),
            "addressable_err_genie": {"mean": float(ea.mean()), "median": float(np.median(ea)),
                                      "min": float(ea.min()), "max": float(ea.max())},
            "addressable_err_blind": {"mean": float(eab.mean()), "median": float(np.median(eab))},
            "tiles_err_genie_below": {f"{t:.2f}": int((eg < t).sum()) for t in (0.03, 0.05, 0.08, 0.10, 0.13, 0.15)}}
    if args.emulate:
        summ["emulated_cells"] = {k: {"errors": v[0], "cells": v[1], "err": (v[0] / v[1] if v[1] else None)}
                                  for k, v in emu.items()}
    json.dump(summ, open(out / "summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))
    vmax = 0.30
    img = np.clip(np.nan_to_num(err_map, nan=vmax) / vmax, 0, 1)
    Image.fromarray((img * 255).astype(np.uint8)).resize((tiles_x * 6, tiles_y * 6), Image.NEAREST).save(
        out / "err-genie-map.png")
    am = np.nan_to_num(word_map, nan=100) <= BCH_T
    Image.fromarray((am * 255).astype(np.uint8)).resize((tiles_x * 6, tiles_y * 6), Image.NEAREST).save(
        out / "addressable-map.png")


if __name__ == "__main__":
    main()
