"""e041 — WHERE is the screen? A fine map of periodic-structure energy.

`e041_screen_map.py` weighs two known lattices in 8 mm blocks; this tool
asks a different question at 1.4 mm resolution: in each small block, is
there ANY screen (a sharp off-axis peak in the 140–240 lpi annulus) and
how strong is it, and how dark is the block? Regions where the screen
energy drops to the floor are the "unscreened pieces"; the map and the
block means tell whether those are the dark pieces the eye sees.

NOT VALID AT THE c3 PITCH (e041 log, correction of 2026-10-05 02:10): the c3
cell lattice (200 lpi) sits inside the 140–240 lpi annulus, its sinc nulls
pull the annulus median down and inflate the ratio whether or not a screen is
present — an UNSCREENED c3 print reads ~34, like the screened S7b/S9/S1dash
sheets (29–37), while an unscreened c2 print read 20. Use it only on c2
prints; for c3, or whenever the engine's screen lattices are known, use the
lattice-specific tools (`e041_screen_map.py`, `e041_band_screen.py`,
`e041_spectrum.py`), which read peaks at known frequency AND angle that no
cell grid produces. Kept as a c2 tool and as the record of the mistake.

    PYTHONPATH=src:. env/bin/python -m measure.e041_screen_fine \
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S9/captures/S9-canon-2400rgb.tiff --tag S9 --out build/e041/maps

Outputs: <tag>-fine-screen.png (log screen ratio, bright = screened),
<tag>-fine-mean.png (block mean of the channel), <tag>-fine.npz (both
arrays + geometry) and a text summary: the floor, the fraction of the
field below it, the unscreened regions as bounding boxes in mm from the
field's top-left, and the darkness of screened vs unscreened blocks.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from measure.e041_screen_map import field_bbox

Image.MAX_IMAGE_PIXELS = None
CH = {"R": 0, "G": 1, "B": 2}


def annulus_mask(n: int, dpi: float, lpi_lo: float, lpi_hi: float, axis_deg: float):
    f = np.fft.fftshift(np.fft.fftfreq(n))
    fy, fx = np.meshgrid(f, f, indexing="ij")
    r = np.hypot(fy, fx) * dpi
    ang = np.degrees(np.arctan2(fy, fx))
    off_axis = np.minimum(np.abs(((ang % 90) + 45) % 90 - 45), 90) > axis_deg
    return (r >= lpi_lo) & (r <= lpi_hi) & off_axis


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--channel", default="G")
    ap.add_argument("--block", type=int, default=128)
    ap.add_argument("--step", type=int, default=64)
    ap.add_argument("--dpi", type=float, default=2400.0)
    ap.add_argument("--lpi", default="140,240", help="annulus in lines/inch")
    ap.add_argument("--axis-deg", type=float, default=8.0, help="exclude this much around 0/90 (the cell grid)")
    ap.add_argument("--floor-quantile", type=float, default=0.02,
                    help="the floor is this quantile of the ratio over blocks of a scrambled copy")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    img = np.asarray(Image.open(args.scan))
    r0, r1, c0, c1 = field_bbox(img)
    g = img[r0:r1, c0:c1, CH[args.channel]].astype(np.float32)
    del img
    H, W = g.shape
    n, st = args.block, args.step
    lo, hi = (float(v) for v in args.lpi.split(","))
    mask = annulus_mask(n, args.dpi, lo, hi, args.axis_deg)
    win = np.outer(np.hanning(n), np.hanning(n)).astype(np.float32)
    nby = (H - n) // st + 1
    nbx = (W - n) // st + 1
    ratio = np.zeros((nby, nbx), np.float32)
    mean = np.zeros((nby, nbx), np.float32)
    # a scrambled control: the same blocks with pixels shuffled give the no-screen floor
    rng = np.random.default_rng(0)
    ctrl = []
    for by in range(nby):
        rows = g[by * st: by * st + n]
        blocks = np.lib.stride_tricks.sliding_window_view(rows, (n, n), axis=(0, 1))[0, ::st][:nbx]
        b = blocks - blocks.mean(axis=(1, 2), keepdims=True)
        S = np.abs(np.fft.fftshift(np.fft.fft2(b * win), axes=(1, 2))) ** 2
        ann = S[:, mask]
        ratio[by] = ann.max(axis=1) / (np.median(ann, axis=1) + 1e-9)
        mean[by] = blocks.mean(axis=(1, 2))
        if by % 40 == 0:
            sb = blocks[::max(1, nbx // 8)].copy()
            for k in range(sb.shape[0]):
                flat = sb[k].ravel(); rng.shuffle(flat); sb[k] = flat.reshape(n, n)
            sb = sb - sb.mean(axis=(1, 2), keepdims=True)
            Sc = np.abs(np.fft.fftshift(np.fft.fft2(sb * win), axes=(1, 2))) ** 2
            annc = Sc[:, mask]
            ctrl.extend((annc.max(axis=1) / (np.median(annc, axis=1) + 1e-9)).tolist())
        if by % 50 == 0:
            print(f"  block row {by}/{nby}", flush=True)
    ctrl = np.array(ctrl)
    floor = float(np.quantile(ctrl, 1 - args.floor_quantile))  # above the scrambled control's 98th pct
    unscreened = ratio < floor
    mm_per_block = st / args.dpi * 25.4
    print(f"{args.tag}: field {H}x{W} px at ({r0},{c0}); {nby}x{nbx} blocks of {n} px, step {st} px = {mm_per_block:.2f} mm")
    print(f"  screen ratio: median {np.median(ratio):.1f}, p10 {np.quantile(ratio, .1):.1f}, p90 {np.quantile(ratio, .9):.1f};"
          f" scrambled control median {np.median(ctrl):.1f}, floor (its {100 * (1 - args.floor_quantile):.0f}th pct) {floor:.1f}")
    print(f"  unscreened blocks (ratio < floor): {unscreened.mean() * 100:.2f} % of the field")
    print(f"  block mean {args.channel}: screened {mean[~unscreened].mean():.1f}, unscreened {mean[unscreened].mean():.1f}"
          if unscreened.any() else "  no unscreened blocks")
    # regions
    lab, nlab = ndimage.label(unscreened)
    sizes = ndimage.sum(unscreened, lab, range(1, nlab + 1))
    order = np.argsort(-sizes)
    print(f"  unscreened regions: {nlab}; the largest (bbox in mm from the field's top-left: top-bottom x left-right, area mm², mean {args.channel}):")
    for k in order[:12]:
        sl = ndimage.find_objects((lab == k + 1).astype(np.int8))[0]
        t, b = sl[0].start * mm_per_block, (sl[0].stop) * mm_per_block
        l, r = sl[1].start * mm_per_block, (sl[1].stop) * mm_per_block
        area = sizes[k] * mm_per_block ** 2
        print(f"    {t:6.1f}-{b:6.1f} mm x {l:6.1f}-{r:6.1f} mm  area {area:7.1f}  mean {mean[lab == k + 1].mean():.1f}")
    colmed = np.median(ratio, axis=0)
    print("  screen ratio, column median, per 4 mm from the field's left: " +
          " ".join(f"{np.median(colmed[i:i + 6]):.0f}" for i in range(0, nbx, 6)))
    rowmed_right = np.median(ratio[:, nbx // 2:], axis=1)
    rowmed_left = np.median(ratio[:, :nbx // 2], axis=1)
    print("  screen ratio, row median over the RIGHT half, last 8 mm from the field's bottom (0.68 mm steps): " +
          " ".join(f"{v:.0f}" for v in rowmed_right[-12:]))
    print("  same, LEFT half: " + " ".join(f"{v:.0f}" for v in rowmed_left[-12:]))
    print("  first 8 mm from the top, right / left: " + " ".join(f"{v:.0f}" for v in rowmed_right[:12]) +
          " / " + " ".join(f"{v:.0f}" for v in rowmed_left[:12]))
    meanrow_right = np.median(mean[:, nbx // 2:], axis=1)
    print(f"  block mean {args.channel}, row median over the RIGHT half, last 8 mm: " + " ".join(f"{v:.0f}" for v in meanrow_right[-12:]))
    # images
    lr = np.log10(ratio + 1)
    v = np.clip((lr - np.log10(floor + 1)) / (np.quantile(lr, .99) - np.log10(floor + 1) + 1e-9), 0, 1)
    Image.fromarray((v * 255).astype(np.uint8)).resize((nbx * 2, nby * 2), Image.NEAREST).save(out / f"{args.tag}-fine-screen.png")
    med = float(np.median(mean)); span = 12.0
    mv = np.clip((mean - (med - span)) / (2 * span), 0, 1)
    Image.fromarray((mv * 255).astype(np.uint8)).resize((nbx * 2, nby * 2), Image.NEAREST).save(out / f"{args.tag}-fine-mean.png")
    np.savez_compressed(out / f"{args.tag}-fine.npz", ratio=ratio, mean=mean, floor=floor, bbox=np.array([r0, r1, c0, c1]),
                        block=n, step=st, channel=args.channel)


if __name__ == "__main__":
    main()
