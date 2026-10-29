"""e041 — what structure does a print carry? Crops and 2-D spectra, no truth.

For each scan: a pixel-scale crop (upscaled, per channel and RGB) and the
2-D power spectrum of a window at the same scan coordinates, with the
strongest off-axis peaks listed as lines/inch and angle. The screen map
(`e041_screen_map.py`) only weighs the two KNOWN lattices (165 lpi ±14°,
212 lpi 45°); this tool finds whatever is there, so a print that carries a
screen the map does not know is not mistaken for an unscreened one.

    PYTHONPATH=src:. env/bin/python -m measure.e041_spectrum \
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S7b/captures/S7b-canon-2400rgb.tiff --tag S7b \
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S9/captures/S9-canon-2400rgb.tiff --tag S9 \
        --window 13000,4500 --window 13000,10000 --size 2048 \
        --out build/e041/maps

Coordinates are scan pixels (row, col) at the scan's own dpi (default 2400).
Peaks are reported for each channel after removing the DC term and the
cell-grid harmonics (0° / 90° within ±4°), as (lpi, angle, power over the
local ring median).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path))


def spectrum(block: np.ndarray) -> np.ndarray:
    b = block.astype(np.float64)
    b -= b.mean()
    n = b.shape[0]
    w = np.hanning(n)
    b *= np.outer(w, w)
    return np.abs(np.fft.fftshift(np.fft.fft2(b))) ** 2


def peaks(S: np.ndarray, dpi: float, n_top: int = 8, f_max: float = 0.2):
    n = S.shape[0]
    f = np.fft.fftshift(np.fft.fftfreq(n))
    fy, fx = np.meshgrid(f, f, indexing="ij")
    r = np.hypot(fy, fx)
    ang = np.degrees(np.arctan2(fy, fx))
    # local background: median in radial rings of width 0.004 cycles/px
    ring = np.floor(r / 0.004).astype(int)
    bg = np.ones_like(S)
    for k in np.unique(ring):
        m = ring == k
        bg[m] = np.median(S[m]) + 1e-12
    ratio = S / bg
    on_axis = (np.abs(((ang + 90) % 90) - 0) < 4) | (np.abs(((ang + 90) % 90) - 90) < 4)
    cand = (r > 0.02) & (r < f_max) & (~on_axis) & (fx >= 0)  # one half-plane
    out = []
    taken = np.zeros_like(S, dtype=bool)
    for _ in range(n_top):
        m = cand & ~taken
        if not m.any():
            break
        i = np.argmax(np.where(m, ratio, 0))
        iy, ix = np.unravel_index(i, S.shape)
        out.append((r[iy, ix] * dpi, ang[iy, ix], ratio[iy, ix]))
        # exclude a neighbourhood around this peak
        taken |= np.hypot(fy - fy[iy, ix], fx - fx[iy, ix]) < 0.006
    return out


def save_crop(img: np.ndarray, y: int, x: int, size: int, up: int, path: Path) -> None:
    c = img[y:y + size, x:x + size]
    big = Image.fromarray(c).resize((size * up, size * up), Image.NEAREST)
    big.save(path)


def save_spectrum(S: np.ndarray, f_max: float, path: Path) -> None:
    n = S.shape[0]
    half = int(round(f_max * n))
    c = S[n // 2 - half:n // 2 + half, n // 2 - half:n // 2 + half]
    v = np.log10(c + 1e-9)
    lo, hi = np.percentile(v, [50, 99.9])
    g = np.clip((v - lo) / (hi - lo + 1e-12), 0, 1)
    Image.fromarray((g * 255).astype(np.uint8)).resize((512, 512), Image.BILINEAR).save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="append", required=True)
    ap.add_argument("--tag", action="append", required=True)
    ap.add_argument("--window", action="append", required=True, help="row,col of the window's top-left")
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--crop", type=int, default=300, help="crop edge in px (from the window's top-left)")
    ap.add_argument("--up", type=int, default=4)
    ap.add_argument("--dpi", type=float, default=2400.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    assert len(args.scan) == len(args.tag)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    windows = [tuple(int(v) for v in w.split(",")) for w in args.window]
    for scan, tag in zip(args.scan, args.tag):
        img = load(scan)
        print(f"{tag}: {img.shape}")
        for wi, (y, x) in enumerate(windows):
            save_crop(img, y, x, args.crop, args.up, out / f"{tag}-w{wi}-crop.png")
            blk = img[y:y + args.size, x:x + args.size]
            mean = blk.reshape(-1, 3).mean(axis=0)
            print(f"  window {wi} at ({y},{x}) size {args.size}: mean RGB {mean[0]:.1f} {mean[1]:.1f} {mean[2]:.1f}")
            for ci, ch in enumerate("RGB"):
                S = spectrum(blk[:, :, ci])
                save_spectrum(S, 0.2, out / f"{tag}-w{wi}-spec_{ch}.png")
                pk = peaks(S, args.dpi)
                desc = ", ".join(f"{lpi:.0f} lpi @{a:+.0f}° x{ratio:.0f}" for lpi, a, ratio in pk[:6])
                print(f"    {ch}: {desc}")
        del img


if __name__ == "__main__":
    main()
