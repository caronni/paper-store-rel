#!/usr/bin/env python3
"""e040 — is a rendering ADDRESSABLE?  Per tile, the 100 address-word sites
are read from a grey rendering at a plane's own fitted geometry through
the receiver's sampling aperture (`--aperture`, calibrate.APERTURE_CELLS
0.7 of a cell), hard-decided against a threshold taken over ALL 4,096
cells of the tile (never over the word's own 100 sites: a word carrying k
ones would then be charged |k - 50| errors on a perfect read — found by
the 2026-10-01 refuter), and counted against the word the format law
says the tile carries (`words.reference_page`: the K word in the
two-state colour alphabet, inked = 1).  BCH(127,50) corrects t = 13, so
<= 13 wrong sites is the CODE's bound; the receiver's placement gates
(soft mismatch < 0.20 per parity half, the rival gap, dust-site
references) are stricter, so this is an upper bound on what placement
could accept.  MEASUREMENT ONLY — the pose comes from the emitted field
(fit_planes.py): the ceiling a blind reader could reach, not a blind
result.

Controls (`--control`): `shuffle` scores each tile against another
tile's word (expect ~50 %); `offset` reads one cell to the right of every
site (expect ~50 % on a one-dot cell).

    PYTHONPATH=src env/bin/python measure/e040-plane-isolation/addressability.py \
        region.json planes.json --rendering C --geometry C [--format c1-cmy8-r0700@106x74]
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import tifffile
from scipy import ndimage

from holo.format import pilots
from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.plugins import words

BCH_T = 13


def local_shift(grey, aff, template, cy0, cx0, y0, x0, pad):
    """Best (dy, dx) of a tile's rendered truth block around its affine
    prediction, by high-passed FFT cross-correlation; None off-raster."""
    n = template.shape[0]
    scale = float(np.sqrt(abs(np.linalg.det(aff[:, :2]))))
    size = int(round(n * scale))
    ty = aff[0, 0] * cy0 + aff[0, 1] * cx0 + aff[0, 2] - y0
    tx = aff[1, 0] * cy0 + aff[1, 1] * cx0 + aff[1, 2] - x0
    r0, c0 = int(round(ty)) - pad, int(round(tx)) - pad
    r1, c1 = r0 + size + 2 * pad, c0 + size + 2 * pad
    if r0 < 0 or c0 < 0 or r1 > grey.shape[0] or c1 > grey.shape[1]:
        return None
    crop = np.asarray(grey[r0:r1, c0:c1], np.float32)
    idx = (np.arange(size) / scale).astype(int)
    rendered = template[idx][:, idx]
    a = -(crop - ndimage.uniform_filter(crop, 24))
    t = rendered - ndimage.uniform_filter(rendered, 24)
    cc = np.fft.irfft2(np.fft.rfft2(a) * np.conj(np.fft.rfft2(t, s=a.shape)), s=a.shape)
    win = cc[:2 * pad + 1, :2 * pad + 1]
    k = np.unravel_index(int(win.argmax()), win.shape)
    return (k[0] - pad - (ty - round(ty)), k[1] - pad - (tx - round(tx)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("region_json")
    ap.add_argument("planes_json")
    ap.add_argument("--rendering", required=True, choices=("C", "M", "Y", "luma"))
    ap.add_argument("--geometry", required=True, choices=("C", "M", "Y", "mean"),
                    help="whose fitted affine places the sites; mean = average of C, M, Y")
    ap.add_argument("--format", default="c1-cmy8-r0700@106x74")
    ap.add_argument("--control", choices=("none", "shuffle", "offset"), default="none")
    ap.add_argument("--aperture", type=int, default=6, metavar="PX",
                    help="uniform_filter aperture before sampling; the receiver's is "
                         "round(0.7 * px per cell) = 6 at 8 px/cell; 1 = raw pixel")
    ap.add_argument("--local-search", type=int, default=0, metavar="PX",
                    help="refine each tile's pose by correlating its 64x64 truth block "
                         "(the plane's own, luma: ink count) within +-PX; 0 = global affine only")
    ap.add_argument("--out")
    args = ap.parse_args()

    region = json.load(open(args.region_json))
    planes = json.load(open(args.planes_json))["planes"]
    y0, x0, h, w = region["region_yx_hw"]
    grey = np.asarray(tifffile.memmap(region["greys"][args.rendering], mode="r"), np.float32)
    if args.aperture > 1:
        grey = ndimage.uniform_filter(grey, args.aperture)
    if args.geometry == "mean":
        aff = np.mean([np.asarray(planes[n]["affine_cell_to_px"]) for n in "CMY"], axis=0)
    else:
        aff = np.asarray(planes[args.geometry]["affine_cell_to_px"])

    truth = np.unpackbits(np.load(json.load(open(args.planes_json))["gt"]), axis=2)
    template_plane = (truth.sum(0) if args.rendering == "luma"
                      else truth["CMY".index(args.rendering)]).astype(np.float32)
    row = resolve_format_ref(args.format)
    ref = words.reference_page(row, 0)
    site_index = words.word_site_index(row.sites_seed)
    sites = np.argwhere(site_index >= 0)                     # (100, 2) window-local cells
    order = site_index[sites[:, 0], sites[:, 1]]
    sites = sites[np.argsort(order)]
    tiles_y, tiles_x = row.tiles_yx
    T = pilots.TILE_CELLS
    ALL = np.argwhere(np.ones((T, T), bool))                # every cell of a tile

    rng = np.random.default_rng(0)
    results = []
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            cy = ty * T + sites[:, 0]
            cx = tx * T + sites[:, 1]
            if args.control == "offset":
                cx = cx + 1
            py = aff[0, 0] * (cy + 0.5) + aff[0, 1] * (cx + 0.5) + aff[0, 2] - y0 - 0.5
            px = aff[1, 0] * (cy + 0.5) + aff[1, 1] * (cx + 0.5) + aff[1, 2] - x0 - 0.5
            pad = args.local_search
            if py.min() < 1 + pad or px.min() < 1 + pad or py.max() > h - 2 - pad or px.max() > w - 2 - pad:
                continue
            shift = (0, 0)
            if pad:
                shift = local_shift(grey, aff, template_plane[ty * T:(ty + 1) * T, tx * T:(tx + 1) * T],
                                    ty * T, tx * T, y0, x0, pad)
                if shift is None:
                    continue
                py, px = py + shift[0], px + shift[1]
            v = ndimage.map_coordinates(grey, [py, px], order=1, mode="nearest", output=np.float32)
            ay = aff[0, 0] * (ty * T + ALL[:, 0] + 0.5) + aff[0, 1] * (tx * T + ALL[:, 1] + 0.5) + aff[0, 2] - y0 - 0.5 + shift[0]
            ax = aff[1, 0] * (ty * T + ALL[:, 0] + 0.5) + aff[1, 1] * (tx * T + ALL[:, 1] + 0.5) + aff[1, 2] - x0 - 0.5 + shift[1]
            every = ndimage.map_coordinates(grey, [ay, ax], order=1, mode="nearest", output=np.float32)
            lo, hi = np.percentile(every, (25, 75))
            threshold = 0.5 * (lo + hi) if hi > lo else float(every.mean())
            expected = ref.values[ty * T + sites[:, 0], tx * T + sites[:, 1]].astype(bool)
            if args.control == "shuffle":
                oty, otx = rng.integers(tiles_y), rng.integers(tiles_x)
                expected = ref.values[oty * T + sites[:, 0], otx * T + sites[:, 1]].astype(bool)
            read = v < threshold                               # dark = inked = word bit 1
            errors = int(np.count_nonzero(read != expected))
            results.append({"ty": ty, "tx": tx, "errors": errors, "shift_px": list(map(float, shift)),
                            "inked_mean": float(v[expected].mean()),
                            "blank_mean": float(v[~expected].mean())})
    if not results:
        raise SystemExit("no tile lies wholly inside the region")
    e = np.array([r["errors"] for r in results])
    summary = {
        "rendering": args.rendering, "geometry": args.geometry, "control": args.control,
        "tiles": int(len(e)),
        "errors": {"min": int(e.min()), "p5": float(np.percentile(e, 5)), "median": float(np.median(e)),
                   "p95": float(np.percentile(e, 95)), "max": int(e.max()), "mean": float(e.mean())},
        "decodable_le13": int(np.count_nonzero(e <= BCH_T)),
        "decodable_fraction": float(np.mean(e <= BCH_T)),
        "le20": int(np.count_nonzero(e <= 20)),
        "inked_minus_blank_mean": float(np.mean([r["blank_mean"] - r["inked_mean"] for r in results])),
        "local_search_px": args.local_search, "aperture_px": args.aperture,
        "shift_px_rms": float(np.sqrt(np.mean([r["shift_px"][0] ** 2 + r["shift_px"][1] ** 2 for r in results]))),
    }
    print(json.dumps(summary, indent=1))
    if args.out:
        json.dump({"summary": summary, "tiles": results}, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
