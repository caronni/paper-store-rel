"""probe17 P3-dust-label-sufficiency — stage 1: per-cell feature extraction.

Extracts, for every e004 A3 tile (7-state c3 CMY composite), the per-cell
density features the 004.0 analyzer uses (C/M/Y planes each genie-warp
aligned in its own scan channel = the 'rgb' feature set) PLUS a 4th 'grey'
luma-density feature (grey channel decoded with the union C|M|Y dot bitmap
as the warp genie — the A3 analog of 004.0's K-aligned grey 4th feature).

Reuses analyze_e004.tile_features / decode_rect_by_squares verbatim (import,
no reimplementation). GT comes only from build/e004_gt (sha-gated gen output).

Usage:
  env/bin/python scratch/probe17_dust_features.py <scan.png> <out.npz>
Run from anywhere; paths resolved absolutely.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO = Path("<repo>")
E004 = REPO / "experiments" / "004-finalists-checkerboard"
sys.path.insert(0, str(E004))

import analyze_e004 as ae  # noqa: E402  (the 004.0 machinery, verbatim)
import cal_core as cc  # noqa: E402


def grey_feature(scan: dict, wm: dict, name: str) -> np.ndarray:
    """Grey-channel density per cell, warp-aligned on the union dot bitmap."""
    e0 = cc.entry(scan["manifest"], f"{name}_C")
    cell = int(e0["params"]["cell_dots"])
    gt_union = None
    for p in "CMY":
        e = cc.entry(scan["manifest"], f"{name}_{p}")
        g = cc.load_gt(e)
        gt_union = g.copy() if gt_union is None else (gt_union | g)
    out = ae.decode_rect_by_squares(scan, e0, gt_union, cell, "grey",
                                    soft=False, diagnostics=False)
    means = out["means"]
    nc_y, nc_x = means.shape
    xg, yg = np.meshgrid(
        e0["x_dots"] + (np.arange(nc_x) + 0.5) * cell,
        e0["y_dots"] + (np.arange(nc_y) + 0.5) * cell)
    white = cc.white_at(wm, xg, yg, "grey")
    D = -np.log10(np.maximum(means, 1.0) / np.maximum(white, 1e-3))
    return D.astype(np.float32)


def main(scan_path: str, out_path: str) -> None:
    t0 = time.time()
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    scan = cc.load_scan(scan_path)
    print(f"scan {Path(scan_path).name}: {scan.get('sha256')}", flush=True)
    reg = cc.register(scan, manifest)
    print(f"registered: { {k: v for k, v in reg.items() if isinstance(v, (int, float, str, bool))} }",
          flush=True)
    wm = cc.white_model(scan)

    tiles = ae.tiles_of(manifest, "A3")
    payload: dict = {"scan_name": Path(scan_path).name,
                     "scan_sha256": scan.get("sha256", "")}
    tile_names = []
    for t in tiles:
        name = t["name"]
        X3, y = ae.tile_features(scan, wm, name, "CMY")   # (n,3) C,M,Y density
        g = grey_feature(scan, wm, name)                   # (nc_y, nc_x)
        assert g.size == y.size, (name, g.shape, y.shape)
        key = name.replace("/", "__")
        payload[f"X3_{key}"] = X3.astype(np.float32)
        payload[f"g_{key}"] = g.ravel().astype(np.float32)
        payload[f"y_{key}"] = y.astype(np.int16)
        payload[f"shape_{key}"] = np.array(g.shape, np.int32)
        tile_names.append(key)
        print(f"{name}: {y.size} cells, states {np.bincount(y, minlength=7)}",
              flush=True)
    payload["tile_names"] = np.array(tile_names)
    np.savez_compressed(out_path, **payload)
    print(f"saved {out_path} in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
