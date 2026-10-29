"""e041 — where on the page is the device screen, and how is the colour balanced?

A scan-space instrument that needs no receiver run and no ground truth.
The M281's re-screen lattices are known from e038's 2-D spectra on sheet F
at 2400 dpi: the 165 lpi family at 0.0691 cycles/px, +/-14.2 deg (seen in
R and G), and the 212 lpi family at 0.0880 cycles/px, 45 deg (seen in B).
For every block of the printed field this measures, per channel, the
FFT power at those lattice points over the median power on the same
frequency ring (the random cell pattern's own broadband power), which is
e038's screen-strength number, plus the block's mean R, G, B.

Outputs, in --out: <tag>-screen-{R,G,B}.png (log-scaled maps), <tag>-mean-
{R,G,B}.png, <tag>.json (the grids), and a printed lateral profile.

    PYTHONPATH=src:. env/bin/python -m measure.e041_screen_map \
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S1/captures/S1-canon-2400rgb.tiff --tag S1 --out build/e041/maps
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

LATTICE = {  # name -> (f cyc/px, angles deg) measured on sheet F (e038)
    "165lpi": (0.0691, (14.2, -14.2, 165.8, -165.8)),
    "212lpi": (0.0880, (45.4, -45.4, 134.6, -134.6)),
}
BLOCK = 768          # px, 64 cells at 12 px/cell
WHITE_THRESHOLD = 200


def field_bbox(img: np.ndarray) -> tuple[int, int, int, int]:
    """The printed field's bounding box from a coarse mean of the min channel."""
    coarse = img[::16, ::16, :].min(axis=2).astype(np.float32)
    k = 8
    h, w = (coarse.shape[0] // k) * k, (coarse.shape[1] // k) * k
    cm = coarse[:h, :w].reshape(h // k, k, w // k, k).mean((1, 3))
    dark = cm < WHITE_THRESHOLD
    rows = np.flatnonzero(dark.mean(1) > 0.5)
    cols = np.flatnonzero(dark.mean(0) > 0.5)
    scale = 16 * k
    return (int(rows[0] * scale), int((rows[-1] + 1) * scale),
            int(cols[0] * scale), int((cols[-1] + 1) * scale))


def block_spectrum(patch: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    p = patch.astype(np.float64); p -= p.mean()
    h, w = p.shape
    win = np.outer(np.hanning(h), np.hanning(w))
    S = np.abs(np.fft.fftshift(np.fft.fft2(p * win))) ** 2
    fy = np.fft.fftshift(np.fft.fftfreq(h)); fx = np.fft.fftshift(np.fft.fftfreq(w))
    return S, fy, fx


def lattice_ratio(S, fy, fx, f: float, angles) -> float:
    FR = np.sqrt(fy[:, None] ** 2 + fx[None, :] ** 2)
    ring = np.abs(FR - f) < 0.004
    med = float(np.median(S[ring]))
    pk = 0.0
    for ang in angles:
        ty, tx = f * np.sin(np.radians(ang)), f * np.cos(np.radians(ang))
        iy, ix = int(np.argmin(np.abs(fy - ty))), int(np.argmin(np.abs(fx - tx)))
        pk = max(pk, float(S[iy - 2:iy + 3, ix - 2:ix + 3].max()))
    return pk / med if med > 0 else float("nan")


def save_map(grid: np.ndarray, path: Path, log: bool, scale: int = 24) -> None:
    g = np.log10(np.maximum(grid, 1)) if log else grid.astype(np.float64)
    lo, hi = np.nanpercentile(g, 1), np.nanpercentile(g, 99)
    im = ((np.clip(g, lo, hi) - lo) / max(hi - lo, 1e-9) * 255).astype(np.uint8)
    Image.fromarray(im).resize((im.shape[1] * scale, im.shape[0] * scale), Image.NEAREST).save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    img = np.asarray(Image.open(args.scan))
    y0, y1, x0, x1 = field_bbox(img)
    ny, nx = (y1 - y0) // BLOCK, (x1 - x0) // BLOCK
    print(f"{args.tag}: scan {img.shape}, field rows {y0}-{y1} cols {x0}-{x1}, grid {ny}x{nx} blocks of {BLOCK} px")
    grids = {f"screen165_{c}": np.zeros((ny, nx)) for c in "RGB"}
    grids.update({f"screen212_{c}": np.zeros((ny, nx)) for c in "RGB"})
    grids.update({f"mean_{c}": np.zeros((ny, nx)) for c in "RGB"})
    for by in range(ny):
        for bx in range(nx):
            ys, xs = y0 + by * BLOCK, x0 + bx * BLOCK
            blk = img[ys:ys + BLOCK, xs:xs + BLOCK, :]
            for q, c in enumerate("RGB"):
                S, fy, fx = block_spectrum(blk[..., q])
                grids[f"screen165_{c}"][by, bx] = lattice_ratio(S, fy, fx, *LATTICE["165lpi"])
                grids[f"screen212_{c}"][by, bx] = lattice_ratio(S, fy, fx, *LATTICE["212lpi"])
                grids[f"mean_{c}"][by, bx] = float(blk[..., q].mean())
        if by % 5 == 0:
            print(f"  row {by}/{ny}", flush=True)
    for name, g in grids.items():
        save_map(g, out / f"{args.tag}-{name}.png", log=name.startswith("screen"))
    json.dump({k: v.tolist() for k, v in grids.items()} | {"bbox": [y0, y1, x0, x1], "block": BLOCK},
              open(out / f"{args.tag}.json", "w"))
    mm_per_block = BLOCK / 2400 * 25.4
    print(f"\nlateral profile (column medians over rows; block = {mm_per_block:.1f} mm), {args.tag}:")
    print(" col | x mm | screen165 R  G  B | screen212 R  G  B | mean R  G  B")
    for bx in range(nx):
        s165 = [np.median(grids[f'screen165_{c}'][:, bx]) for c in "RGB"]
        s212 = [np.median(grids[f'screen212_{c}'][:, bx]) for c in "RGB"]
        mu = [np.median(grids[f'mean_{c}'][:, bx]) for c in "RGB"]
        print(f" {bx:3d} | {(x0 + (bx + 0.5) * BLOCK) / 2400 * 25.4:6.1f} | {s165[0]:6.0f} {s165[1]:6.0f} {s165[2]:6.0f} | "
              f"{s212[0]:6.0f} {s212[1]:6.0f} {s212[2]:6.0f} | {mu[0]:5.1f} {mu[1]:5.1f} {mu[2]:5.1f}")
    print(f"\nwhole-field medians {args.tag}: " + ", ".join(
        f"{k} {np.median(v):.1f}" for k, v in grids.items()))


if __name__ == "__main__":
    main()
