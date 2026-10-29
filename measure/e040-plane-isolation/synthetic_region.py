#!/usr/bin/env python3
"""e040 — the instrument's null: a PERFECT print of one plane, rendered
from the emitted field through that plane's fitted affine into the same
region as a real rendering, as the grey `render_planes.py` would write
(255 blank, 0 inked, nearest cell).  `addressability.py` on it must read
every tile at 0 errors with `--geometry` = that plane and no local search;
anything else is the instrument's own defect, not the print's.

    PYTHONPATH=src env/bin/python measure/e040-plane-isolation/synthetic_region.py \
        region.json planes.json out_dir --plane C
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tifffile

CHUNK_ROWS = 1024


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("region_json")
    ap.add_argument("planes_json")
    ap.add_argument("out_dir")
    ap.add_argument("--plane", required=True, choices=("C", "M", "Y"))
    args = ap.parse_args()

    region = json.load(open(args.region_json))
    planes = json.load(open(args.planes_json))
    y0, x0, h, w = region["region_yx_hw"]
    aff = np.asarray(planes["planes"][args.plane]["affine_cell_to_px"])
    truth = np.unpackbits(np.load(planes["gt"]), axis=2)["CMY".index(args.plane)]
    cells_y, cells_x = truth.shape
    m = np.array([[aff[0, 0], aff[0, 1]], [aff[1, 0], aff[1, 1]]])
    inv = np.linalg.inv(m)
    off = -inv @ np.array([aff[0, 2], aff[1, 2]])

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    grey = tifffile.memmap(str(out / f"{args.plane}.tiff"), shape=(h, w), dtype=np.uint8,
                           photometric="minisblack")
    for r in range(0, h, CHUNK_ROWS):
        yy, xx = np.mgrid[y0 + r:y0 + min(r + CHUNK_ROWS, h), x0:x0 + w]
        cy = np.floor(inv[0, 0] * yy + inv[0, 1] * xx + off[0]).astype(int)
        cx = np.floor(inv[1, 0] * yy + inv[1, 1] * xx + off[1]).astype(int)
        inside = (cy >= 0) & (cx >= 0) & (cy < cells_y) & (cx < cells_x)
        bits = np.zeros(cy.shape, np.uint8)
        bits[inside] = truth[cy[inside], cx[inside]]
        grey[r:r + yy.shape[0]] = np.where(bits > 0, 0, 255).astype(np.uint8)
    grey.flush()
    sidecar = dict(region)
    sidecar["greys"] = {args.plane: str(out / f"{args.plane}.tiff")}
    sidecar["synthetic_perfect_plane"] = args.plane
    json.dump(sidecar, open(out / "region.json", "w"), indent=1)
    print(json.dumps(sidecar, indent=1))


if __name__ == "__main__":
    main()
