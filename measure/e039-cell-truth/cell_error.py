#!/usr/bin/env python3
"""e039 — raw per-plane cell error of a colour capture against ground truth.

Takes holo3's own placements from a fact snapshot (window-local cells,
page origin, native affine), samples the capture's RGB at every placed
cell centre, and compares a hard read against the emitted per-dot truth
(`page000_gt.npy`: planes C, M, Y, 1 bit per 600-dpi dot, packed along x).
Plane p is read from its complementary scan channel (C<-R, M<-G, Y<-B),
dark = inked.  Two thresholds per plane: the MEDIAN of the sampled cells
(blind) and the genie midpoint between the truth-conditional means (the
best a single global threshold can do).  A plane at ~50 % carries nothing;
this is a floor-free hard-decision number, not the receiver's soft decoder.

    PYTHONPATH=src env/bin/python measure/e039-cell-truth/cell_error.py \
        facts.npz page000_gt.npy scan.tiff --dots-per-cell 3 [--capture SHA_PREFIX]
"""
from __future__ import annotations

import argparse

import numpy as np
from PIL import Image
from scipy import ndimage

from holo.receiver import data, snapshot
from holo.receiver.plugins.calibrate import window_page_cells

Image.MAX_IMAGE_PIXELS = None


def placed_cells(facts, capture_id):
    """page cell (y, x) -> native scan (y_px, x_px) of its centre, deduplicated."""
    seen = {}
    for fact in facts:
        if not isinstance(fact, data.Placement) or fact.capture_id != capture_id:
            continue
        # calibrate.window_page_cells: window-local cells rotated by rot_k
        # within the window's shape, plus the page origin -> PAGE cells.
        # calibrate.scan_points_yx: the affine takes PAGE cells (+0.5),
        # (y, x) order, rows (a0 a1 a2 | a3 a4 a5) -> native (y_px, x_px).
        a = fact.native_affine
        y0, x0, y1, x1 = fact.window_id[3]
        page = window_page_cells(fact, (y1 - y0, x1 - x0), (1 << 30, 1 << 30))
        py = page[:, 0]
        px = page[:, 1]
        ys = a[0] * (py + 0.5) + a[1] * (px + 0.5) + a[2]
        xs = a[3] * (py + 0.5) + a[4] * (px + 0.5) + a[5]
        for key in zip(py.tolist(), px.tolist(), ys.tolist(), xs.tolist()):
            seen.setdefault(key[:2], key[2:])
    keys = np.array(list(seen.keys()), np.int64)
    pix = np.array(list(seen.values()), np.float64)
    return keys, pix


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("facts")
    ap.add_argument("gt")
    ap.add_argument("scan")
    ap.add_argument("--dots-per-cell", type=int, required=True)
    ap.add_argument("--capture", default="",
                    help="capture sha prefix (default: the first capture placed)")
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

    packed = np.load(args.gt)
    if packed.ndim == 2:                                        # K: one plane
        packed = packed[None]
    truth = np.unpackbits(packed, axis=2)                       # (planes, H_dots, W_dots)
    d = args.dots_per_cell
    cy, cx = keys[:, 0], keys[:, 1]
    inside = ((cy >= 0) & (cx >= 0) & (cy * d + d // 2 < truth.shape[1])
              & (cx * d + d // 2 < truth.shape[2]))
    cy, cx, pix = cy[inside], cx[inside], pix[inside]

    scan = np.asarray(Image.open(args.scan)).astype(np.float32)
    if scan.ndim == 2:
        scan = scan[..., None]
    planes = (("K", 0),) if truth.shape[0] == 1 else (("C", 0), ("M", 1), ("Y", 2))
    print(f"capture {capture_id[:12]}  placed cells {len(cy)}")
    for plane, (name, channel) in enumerate(planes):
        channel = min(channel, scan.shape[2] - 1)
        t = truth[plane, cy * d + d // 2, cx * d + d // 2].astype(bool)
        v = ndimage.map_coordinates(scan[..., channel], [pix[:, 0], pix[:, 1]],
                                    order=1, mode="nearest")
        blind = v < np.median(v)
        mid = 0.5 * (v[t].mean() + v[~t].mean())
        genie = v < mid
        print(f"  {name}: inked {t.mean():.3f}  mean level inked {v[t].mean():6.1f} / blank "
              f"{v[~t].mean():6.1f}  error median-threshold {np.mean(blind != t):.3f}  "
              f"genie-threshold {np.mean(genie != t):.3f}")
    if len(planes) == 3 and scan.shape[2] == 3:
        # Joint read: nearest truth-conditional RGB centroid of the 8 ink
        # states (C + 2M + 4Y), a genie classifier -- the best any
        # single-cell colour read without context can do.
        rgb = np.stack([ndimage.map_coordinates(scan[..., c], [pix[:, 0], pix[:, 1]],
                                                order=1, mode="nearest") for c in range(3)], 1)
        bits = np.stack([truth[p, cy * d + d // 2, cx * d + d // 2] for p in range(3)], 1)
        state = bits[:, 0] + 2 * bits[:, 1] + 4 * bits[:, 2]
        centroids = np.stack([rgb[state == s].mean(0) for s in range(8)])
        guess = np.argmin(((rgb[:, None, :] - centroids[None]) ** 2).sum(2), 1)
        print(f"  joint 8-state genie: state error {np.mean(guess != state):.3f}  per plane "
              + "  ".join(f"{n} {np.mean(((guess >> p) & 1) != bits[:, p]):.3f}"
                          for p, n in enumerate('CMY')))


if __name__ == "__main__":
    main()
