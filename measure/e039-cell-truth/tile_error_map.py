#!/usr/bin/env python3
"""e039/e040 — per-TILE hard-decision cell error of a colour capture against
ground truth, through the receiver's sampling aperture, at the best of a
small integer pose search per tile.  MEASUREMENT ONLY (the truth is read;
the shift search is a genie): the ceiling a hard single-threshold reader
could reach on each tile, as a distribution and a map — the number a rung
has to live with, tile by tile, where `cell_error.py` gives one page mean.

Placements come from a holo3 snapshot (as in cell_error.py); each plane is
read from its complementary channel (C<-R, M<-G, Y<-B) after a uniform
box of `--aperture` px (the receiver's round(0.7 * px per cell) = 6 at
8 px/cell); for every shift in [-S, S]^2 px two per-tile thresholds are
tried, the tile's own MEDIAN (blind) and the genie midpoint between the
truth-conditional means; the shift with the lowest genie error is kept.
Tiles with fewer than 90 % of their cells placed are left out of the
statistics and drawn blank.

    PYTHONPATH=src env/bin/python measure/e039-cell-truth/tile_error_map.py \
        facts.npz page000_gt.npy scan.tiff --dots-per-cell 2 --capture SHA_PREFIX \
        --out map.json [--aperture 6] [--search 2] [--png prefix]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cell_error import placed_cells  # noqa: E402

from holo.receiver import data, snapshot  # noqa: E402

TILE_CELLS = 64
FULL_TILE = 0.9


def per_tile_median(v, tile, n_tiles, count):
    order = np.lexsort((v, tile))
    vs, ts = v[order], tile[order]
    ids = np.arange(n_tiles)
    lo = np.searchsorted(ts, ids)
    hi = np.searchsorted(ts, ids, side="right")
    med = vs[np.minimum((lo + hi) // 2, len(vs) - 1)]
    med[count == 0] = np.nan
    return med


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("facts")
    ap.add_argument("gt")
    ap.add_argument("scan")
    ap.add_argument("--dots-per-cell", type=int, required=True)
    ap.add_argument("--capture", default="")
    ap.add_argument("--aperture", type=int, default=6)
    ap.add_argument("--search", type=int, default=2, metavar="PX")
    ap.add_argument("--out", required=True)
    ap.add_argument("--png", help="prefix for one 'tiles_y x tiles_x' map per plane")
    args = ap.parse_args()

    facts = snapshot.read(args.facts)
    captures = []
    for fact in facts:
        if isinstance(fact, data.Placement) and fact.capture_id not in captures:
            captures.append(fact.capture_id)
    matching = [c for c in captures if c.startswith(args.capture)]
    if len(matching) != 1:
        raise SystemExit(f"--capture {args.capture!r} matches {len(matching)} of {captures}")
    capture_id = matching[0]
    keys, pix = placed_cells(facts, capture_id)
    del facts

    truth = np.unpackbits(np.load(args.gt), axis=2)
    d = args.dots_per_cell
    T = TILE_CELLS
    tiles_y, tiles_x = truth.shape[1] // (d * T), truth.shape[2] // (d * T)
    n_tiles = tiles_y * tiles_x
    cy, cx = keys[:, 0], keys[:, 1]
    inside = (cy >= 0) & (cx >= 0) & (cy < tiles_y * T) & (cx < tiles_x * T)
    cy, cx, pix = cy[inside], cx[inside], pix[inside]
    tile = (cy // T) * tiles_x + cx // T
    count = np.bincount(tile, minlength=n_tiles).astype(np.float64)
    full = count >= FULL_TILE * T * T

    scan = tifffile.memmap(args.scan, mode="r")
    shifts = [(dy, dx) for dy in range(-args.search, args.search + 1)
              for dx in range(-args.search, args.search + 1)]
    planes = (("C", 0), ("M", 1), ("Y", 2))
    report = {"capture": capture_id, "tiles_yx": [tiles_y, tiles_x], "aperture_px": args.aperture,
              "search_px": args.search, "full_tiles": int(full.sum()), "planes": {}}
    print(f"capture {capture_id[:12]}  placed cells {len(cy)}  full tiles {int(full.sum())}/{n_tiles}")
    for plane, (name, ch) in enumerate(planes):
        chan = np.asarray(scan[..., ch], np.float32)
        if args.aperture > 1:
            chan = ndimage.uniform_filter(chan, args.aperture)
        t = truth[plane, cy * d + d // 2, cx * d + d // 2].astype(bool)
        n_ink = np.bincount(tile, weights=t, minlength=n_tiles)
        n_blank = count - n_ink
        best_genie = np.full(n_tiles, np.inf)
        best_blind = np.full(n_tiles, np.inf)
        best_shift = np.zeros((n_tiles, 2), np.int8)
        zero_genie = None
        for dy, dx in shifts:
            v = ndimage.map_coordinates(chan, [pix[:, 0] + dy, pix[:, 1] + dx], order=1, mode="nearest")
            s_ink = np.bincount(tile, weights=v * t, minlength=n_tiles)
            s_blank = np.bincount(tile, weights=v * (~t), minlength=n_tiles)
            mid = 0.5 * (s_ink / np.maximum(n_ink, 1) + s_blank / np.maximum(n_blank, 1))
            e_genie = np.bincount(tile, weights=(v < mid[tile]) != t, minlength=n_tiles) / np.maximum(count, 1)
            med = per_tile_median(v, tile, n_tiles, count)
            e_blind = np.bincount(tile, weights=(v < med[tile]) != t, minlength=n_tiles) / np.maximum(count, 1)
            if (dy, dx) == (0, 0):
                zero_genie = e_genie.copy()
            better = e_genie < best_genie
            best_genie[better] = e_genie[better]
            best_blind[better] = e_blind[better]
            best_shift[better] = (dy, dx)
        del chan
        g, b, z = best_genie[full], best_blind[full], zero_genie[full]
        q = lambda a: {k: float(np.percentile(a, p)) for k, p in
                       (("min", 0), ("p5", 5), ("p25", 25), ("median", 50), ("p75", 75), ("p95", 95))}
        report["planes"][name] = {
            "genie_best_shift": q(g), "blind_best_shift": q(b), "genie_zero_shift": q(z),
            "tiles_le": {f"{th:.2f}": int((g <= th).sum()) for th in (0.03, 0.05, 0.08, 0.10, 0.12, 0.15)},
            "shift_rms_px": float(np.sqrt((best_shift[full].astype(float) ** 2).sum(1).mean())),
            "per_tile_genie": [None if not f else float(e) for f, e in zip(full, best_genie)],
            "per_tile_blind": [None if not f else float(e) for f, e in zip(full, best_blind)],
        }
        r = report["planes"][name]
        print(f"  {name}: genie best-shift min {r['genie_best_shift']['min']:.3f} p5 {r['genie_best_shift']['p5']:.3f} "
              f"median {r['genie_best_shift']['median']:.3f} p95 {r['genie_best_shift']['p95']:.3f} | "
              f"zero-shift median {r['genie_zero_shift']['median']:.3f} | blind median {r['blind_best_shift']['median']:.3f} | "
              f"tiles<=5% {r['tiles_le']['0.05']} <=8% {r['tiles_le']['0.08']} <=10% {r['tiles_le']['0.10']} "
              f"<=15% {r['tiles_le']['0.15']} of {int(full.sum())} | shift rms {r['shift_rms_px']:.2f} px")
        if args.png:
            img = np.full((tiles_y, tiles_x), 255, np.uint8)
            e = best_genie.reshape(tiles_y, tiles_x)
            f = full.reshape(tiles_y, tiles_x)
            img[f] = np.clip(255 * (1 - e[f] / 0.30), 0, 255).astype(np.uint8)
            Image.fromarray(img).resize((tiles_x * 12, tiles_y * 12), Image.NEAREST).save(f"{args.png}-{name}.png")
    json.dump(report, open(args.out, "w"))


if __name__ == "__main__":
    main()
