"""e041 S10p — synthetic 2400 dpi scans of a small probe page, for e041_probe_readout's smoke test.

Writes a manifest to the S10p contract (five black fiducials, twelve patches over every kind and
target) and paints it as a 2400 dpi RGB TIFF: the 600 dpi page raster mapped through a chosen pose
(shift, scale, rotation, optional 180 deg turn) by nearest sampling, then an optional Gaussian blur
and seeded Gaussian noise.  Ink is multiplicative on the paper white (rgb / 255 * white).

    PYTHONPATH=src:. env/bin/python -m measure.e041_probe_synth --out /tmp/x --name clean
    PYTHONPATH=src:. env/bin/python -m measure.e041_probe_synth --out /tmp/x --name rot \
        --rot180 --shift-mm 3.2 -2.1 --rot-deg 0.3 --scale 1.004
    PYTHONPATH=src:. env/bin/python -m measure.e041_probe_synth --out /tmp/x --name blur \
        --blur-px 6 --noise-sd 8 --white 245
    (--manifest M paints the generator's own manifest instead, at its full page size.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

DPI = 600
SCAN_DPI = 2400
PAGE_MM = (100.0, 80.0)                    # (w, h): a small page keeps the smoke test fast
PATCHES = [  # (rgb, method, kind, target)
    ((0, 255, 255), "default", "pattern", "C"), ((20, 240, 250), "highlpi", "pattern", "C"),
    ((255, 0, 255), "highlpi", "pattern", "M"), ((255, 255, 0), "matrix1x1", "pattern", "Y"),
    ((0, 0, 255), "highlpi", "vector", "CM"), ((0, 255, 0), "default", "vector", "CY"),
    ((255, 0, 0), "matrix1x1", "srgb", "MY"), ((0, 0, 0), "highlpi", "tonerblack", "CMY"),
    ((255, 255, 255), "default", "pattern", "W"), ((250, 250, 250), "highlpi", "srgb", "W"),
    ((255, 40, 230), "default", "srgb", "M"), ((235, 245, 10), "highlpi", "vector", "Y"),
]


def mm_to_dot(v: float) -> int:
    return int(round(v * DPI / 25.4))


def dot_to_mm(d: int) -> float:
    return d * 25.4 / DPI


def build_manifest(seed0: int = 1000) -> dict[str, Any]:
    W, H = PAGE_MM
    fids = [("F0", 6.0, 6.0, 3.0), ("F1", W - 9.0, 6.0, 3.0), ("F2", 6.0, H - 9.0, 3.0),
            ("F3", W - 9.0, H - 9.0, 3.0), ("F4", 30.0, 7.0, 6.0)]
    fiducials = [{"id": i, "x_mm": dot_to_mm(mm_to_dot(x)), "y_mm": dot_to_mm(mm_to_dot(y)),
                  "w_mm": 3.0, "h_mm": h, "rgb": [0, 0, 0]} for i, x, y, h in fids]
    patches = []
    for k, (rgb, method, kind, target) in enumerate(PATCHES):
        x = 14.0 + (k % 6) * 12.5
        y = 22.0 + (k // 6) * 22.0
        seed = seed0 + k
        pat = np.random.default_rng(seed).integers(0, 2, size=(31, 31), dtype=np.uint8)
        patches.append({"id": k, "x_mm": dot_to_mm(mm_to_dot(x)), "y_mm": dot_to_mm(mm_to_dot(y)),
                        "rgb": list(rgb), "method": method, "kind": kind, "target": target, "seed": seed,
                        "pattern_sha256": hashlib.sha256(pat.tobytes()).hexdigest()})
    return {"tag": "S10p-synth", "dpi": DPI, "page_mm": [W, H], "bytes": 0, "sha256": "",
            "fiducials": fiducials,
            "patch_px": {"pattern_dots": 93, "solid_dots": 24, "cell_dots": 3, "cells": 31},
            "patches": patches, "layout_seed": 0, "excluded_zones_mm": {}, "notes": ["synthetic"]}


def page_raster(man: dict[str, Any]) -> np.ndarray:
    W, H = man["page_mm"]
    page = np.full((mm_to_dot(H), mm_to_dot(W), 3), 255, np.uint8)
    for f in man["fiducials"]:
        y, x = mm_to_dot(f["y_mm"]), mm_to_dot(f["x_mm"])
        page[y:y + mm_to_dot(f["h_mm"]), x:x + mm_to_dot(f["w_mm"])] = f["rgb"]
    for p in man["patches"]:
        y, x = mm_to_dot(p["y_mm"]), mm_to_dot(p["x_mm"])
        pat = np.random.default_rng(p["seed"]).integers(0, 2, size=(31, 31), dtype=np.uint8)
        ink = np.kron(pat, np.ones((3, 3), np.uint8)).astype(bool)
        page[y:y + 93, x:x + 93][ink] = p["rgb"]
        page[y + 93:y + 117, x:x + 93] = p["rgb"]
    return page


def paint(page: np.ndarray, *, rot180: bool, shift_mm: tuple[float, float], scale: float,
          rot_deg: float, pad_mm: float, blur_px: float, noise_sd: float, white: float,
          seed: int) -> np.ndarray:
    Hd, Wd = page.shape[:2]
    if rot180:
        page = page[::-1, ::-1]
    sub = SCAN_DPI / DPI
    pad = int(round(pad_mm * SCAN_DPI / 25.4))
    Hs, Ws = int(Hd * sub) + 2 * pad, int(Wd * sub) + 2 * pad
    th = np.radians(rot_deg)
    # forward: page dot (x, y) -> canvas (col, row) = s * R * sub * (x, y) + pad + shift; invert per pixel
    Rinv = np.array([[np.cos(th), np.sin(th)], [-np.sin(th), np.cos(th)]]) / (scale * sub)
    off = np.array([pad + shift_mm[0] * SCAN_DPI / 25.4, pad + shift_mm[1] * SCAN_DPI / 25.4])
    out = np.empty((Hs, Ws, 3), np.float32)
    cols = np.arange(Ws) + 0.5 - off[0]
    for r0 in range(0, Hs, 512):
        rows = np.arange(r0, min(r0 + 512, Hs)) + 0.5 - off[1]
        C, R = np.meshgrid(cols, rows)
        xd = np.floor(Rinv[0, 0] * C + Rinv[0, 1] * R).astype(np.int64)
        yd = np.floor(Rinv[1, 0] * C + Rinv[1, 1] * R).astype(np.int64)
        ok = (xd >= 0) & (xd < Wd) & (yd >= 0) & (yd < Hd)
        blk = np.full(C.shape + (3,), 255.0, np.float32)
        blk[ok] = page[yd[ok], xd[ok]]
        out[r0:r0 + len(rows)] = blk * (white / 255.0)
    if blur_px > 0:
        for c in range(3):
            out[..., c] = ndimage.gaussian_filter(out[..., c], blur_px, mode="nearest")
    if noise_sd > 0:
        out += np.random.default_rng(seed).normal(0.0, noise_sd, out.shape).astype(np.float32)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--rot180", action="store_true")
    ap.add_argument("--shift-mm", type=float, nargs=2, default=(0.0, 0.0))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--rot-deg", type=float, default=0.0)
    ap.add_argument("--pad-mm", type=float, default=8.0)
    ap.add_argument("--blur-px", type=float, default=0.0)
    ap.add_argument("--noise-sd", type=float, default=0.0)
    ap.add_argument("--white", type=float, default=255.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--manifest", default=None, help="paint this S10p manifest instead of the built-in page")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    if args.manifest:
        man = json.loads(Path(args.manifest).read_text())
    else:
        man = build_manifest()
        (out / "S10p-synth.manifest.json").write_text(json.dumps(man, indent=1))
    img = paint(page_raster(man), rot180=args.rot180, shift_mm=tuple(args.shift_mm), scale=args.scale,
                rot_deg=args.rot_deg, pad_mm=args.pad_mm, blur_px=args.blur_px, noise_sd=args.noise_sd,
                white=args.white, seed=args.seed)
    Image.fromarray(img).save(out / f"{args.name}.tiff")
    print(f"wrote {out / (args.name + '.tiff')} {img.shape[1]} x {img.shape[0]} px")


if __name__ == "__main__":
    main()
