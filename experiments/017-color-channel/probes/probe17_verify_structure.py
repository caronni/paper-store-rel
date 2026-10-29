#!/usr/bin/env python
"""P4 verification: is the tile-scale pair-field structure real?

1. Cross-scan repeatability (M281: finalists vs finalists-2-col, same sheet,
   re-placed scan): per-tile pair fields from independent scans. If
   rms(scan1-scan2)/sqrt(2) << model-residual rms, the structure the
   global+linear model misses is PRINT-FROZEN, not scan/anchor noise.
2. Split-half within scan (works for the single AltaLink scan): per tile,
   even/odd anchor cells give two independent tile means; noise on the
   tile mean = rms(h1-h2)/2.

Usage: probe17_verify_structure.py <dir holding probe17_perplane_reg.py's
       probe17_reg_*.npz for finalists, finalists-2-col and
       xerox-e004-finalists-hp-scan>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PLANES = "CMY"


def load(npz_path: Path) -> dict:
    z = np.load(npz_path)
    tiles = sorted({k.split("/")[0] for k in z.files})
    data = {}
    for t in tiles:
        if not float(z[f"{t}/lock"][3]):
            continue
        data[t] = {p: {k: z[f"{t}/{p}/{k}"]
                       for k in ("dy", "dx", "y_page", "x_page")}
                   for p in PLANES}
    return data


def tile_pair_means(data: dict, a: str, b: str, sel=None) -> dict:
    out = {}
    for t, d in data.items():
        va = {ax: d[a][ax] if sel is None else d[a][ax][sel(len(d[a][ax]))]
              for ax in ("dy", "dx")}
        vb = {ax: d[b][ax] if sel is None else d[b][ax][sel(len(d[b][ax]))]
              for ax in ("dy", "dx")}
        out[t] = {ax: float(np.mean(va[ax]) - np.mean(vb[ax]))
                  for ax in ("dy", "dx")}
    return out


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    reg_dir = Path(sys.argv[1])
    d1 = load(reg_dir / "probe17_reg_finalists.npz")
    d2 = load(reg_dir / "probe17_reg_finalists-2-col.npz")
    dx = load(reg_dir / "probe17_reg_xerox-e004-finalists-hp-scan.npz")

    print("== 1. M281 cross-scan repeatability of tile-mean PAIR fields ==")
    for a, b in (("Y", "C"), ("M", "C")):
        p1 = tile_pair_means(d1, a, b)
        p2 = tile_pair_means(d2, a, b)
        tiles = sorted(set(p1) & set(p2))
        for ax in ("dy", "dx"):
            v1 = np.array([p1[t][ax] for t in tiles])
            v2 = np.array([p2[t][ax] for t in tiles])
            diff = v1 - v2
            spread = np.std((v1 + v2) / 2)
            print(f" {a}-{b} {ax}: cross-scan rms diff {np.std(diff):.3f} "
                  f"(per-scan noise {np.std(diff)/np.sqrt(2):.3f}) vs "
                  f"tile-field spread {spread:.3f} dots  "
                  f"corr={np.corrcoef(v1, v2)[0,1]:.3f}")

    print("\n== 2. Split-half (even/odd cells) tile-mean noise ==")
    for label, dset in (("M281 scan1", d1), ("AltaLink", dx)):
        for a, b in (("Y", "C"), ("M", "C")):
            ph1 = tile_pair_means(dset, a, b, sel=lambda n: np.arange(0, n, 2))
            ph2 = tile_pair_means(dset, a, b, sel=lambda n: np.arange(1, n, 2))
            pfull = tile_pair_means(dset, a, b)
            tiles = sorted(pfull)
            for ax in ("dy", "dx"):
                h1 = np.array([ph1[t][ax] for t in tiles])
                h2 = np.array([ph2[t][ax] for t in tiles])
                full = np.array([pfull[t][ax] for t in tiles])
                noise = np.std(h1 - h2) / 2
                print(f" {label} {a}-{b} {ax}: tile-mean noise {noise:.3f} "
                      f"vs field spread {np.std(full):.3f} dots")


if __name__ == "__main__":
    main()
