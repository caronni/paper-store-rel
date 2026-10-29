#!/usr/bin/env python3
"""e040 — render a colour capture's isolated planes as black-on-white
greys, from the mixing model `fit_planes.py` fitted.

For a region (default: the centre quarter), every pixel's RGB is unmixed
through inv(B) into (C, M, Y) estimates; each estimate s is written as a
uint8 grey 160 - 40 s (blank 160, inked 120), so the per-pixel noise is
carried, not clipped.  `luma` is the plain
equal-channel mean the receiver addresses on — the control.  With
`--rgb-from P` a synthetic three-channel TIFF is also written whose R, G
and B all carry plane P's grey, so a colour decode of it addresses on
that plane alone (its luma IS the plane).  Nothing here is promotable:
the mixing model was fitted against the emitted field.

    PYTHONPATH=src env/bin/python measure/e040-plane-isolation/render_planes.py \
        scan.tiff planes.json out_dir [--region y0 x0 h w] [--rgb-from C M]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tifffile

CHUNK_ROWS = 512
BLANK_GREY = 160.0
GAIN = 40.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scan")
    ap.add_argument("planes_json")
    ap.add_argument("out_dir")
    ap.add_argument("--region", nargs=4, type=int, metavar=("Y0", "X0", "H", "W"),
                    help="scan-pixel box; default the centre quarter")
    ap.add_argument("--rgb-from", nargs="*", default=(), choices=("C", "M", "Y"))
    ap.add_argument("--dpi", type=float, default=4800.0)
    args = ap.parse_args()

    scan = tifffile.memmap(args.scan, mode="r")
    H, W = scan.shape[:2]
    if args.region:
        y0, x0, h, w = args.region
    else:
        y0, x0, h, w = H // 4, W // 4, H // 2, W // 2
    model = json.load(open(args.planes_json))["mixing"]
    m0 = np.asarray(model["m0"], np.float32)
    binv = np.asarray(model["B_inverse"], np.float32)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = ("C", "M", "Y", "luma")
    files = {n: tifffile.memmap(str(out / f"{n}.tiff"), shape=(h, w), dtype=np.uint8,
                                photometric="minisblack") for n in names}
    rgb_files = {n: tifffile.memmap(str(out / f"{n}-as-rgb.tiff"), shape=(h, w, 3), dtype=np.uint8,
                                    photometric="rgb") for n in args.rgb_from}
    for r in range(0, h, CHUNK_ROWS):
        rows = np.asarray(scan[y0 + r:y0 + min(r + CHUNK_ROWS, h), x0:x0 + w, :], np.float32)
        est = (rows - m0) @ binv.T                       # (rows, w, 3) plane estimates
        # Unclipped: blank 160, inked 120, the plane estimate's own noise
        # (sd ~1.1 when inked) spans +-3 sd within 0..255.  The first
        # rendering, 255*(1-s), saturated 74 % of pixels and holo3's survey
        # fragmented it into 117 regions (2026-10-01).
        greys = np.clip(BLANK_GREY - GAIN * est, 0, 255).astype(np.uint8)
        for i, n in enumerate("CMY"):
            files[n][r:r + rows.shape[0]] = greys[..., i]
        files["luma"][r:r + rows.shape[0]] = np.clip(rows.mean(2), 0, 255).astype(np.uint8)
        for n, f in rgb_files.items():
            f[r:r + rows.shape[0]] = greys[..., "CMY".index(n), None]
    for f in list(files.values()) + list(rgb_files.values()):
        f.flush()
    sidecar = {"scan": args.scan, "planes_json": args.planes_json,
               "region_yx_hw": [y0, x0, h, w], "dpi": args.dpi,
               "greys": {n: str(out / f"{n}.tiff") for n in names},
               "rgb": {n: str(out / f"{n}-as-rgb.tiff") for n in args.rgb_from}}
    json.dump(sidecar, open(out / "region.json", "w"), indent=1)
    print(json.dumps(sidecar, indent=1))


if __name__ == "__main__":
    main()
