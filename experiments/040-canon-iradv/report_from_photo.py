#!/usr/bin/env python3
"""e040 — read an HCAL-R1 machine-report strip from a PHONE PHOTO.

    PYTHONPATH=src env/bin/python experiments/040-canon-iradv/report_from_photo.py \\
        photo.jpg --box X0 Y0 X1 Y1 [--preview-width 1050] [--rotate 90]

`--box` is the strip's bounding box in preview coordinates (a copy of the
photo scaled to `--preview-width` pixels wide), generous on all sides; the
strip must lie entirely inside it. The strip is rotated to run left→right,
then RECTIFIED by its own two border bars — the top and bottom edges of the
dark band are traced column by column, fitted by cubics, and the band is
remapped so both are straight and level (this removes the bow and the
vertical perspective a hand-held shot has; the instrument's decoder fits
straight bars and pairs them, so a bowed strip finds no pair) — then the
illumination is flattened (divide by a 25-px Gaussian background) and the
instrument's own `decode_report_image` runs on the raw, flattened, unsharp-
masked and Richardson-Lucy-deblurred variants, both orientations; the
first CRC-valid observation wins. Measured 2026-09-24 on the Canon
iR-ADV C257/357 sheet: at ~9.7 px per module, flatten alone decodes; the
second photo (9.1 px per module, softer) never does — 38 bad bytes of 164.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.signal import fftconvolve

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from holo.characterize import report_strips as rs  # noqa: E402


def rectify(a: np.ndarray) -> np.ndarray:
    g = gaussian_filter(a.astype(np.float32), 1.5)
    thr = 0.5 * (np.percentile(g, 90) + np.percentile(g, 2))
    dark = g < thr
    h, w = a.shape
    xs = np.arange(w)
    top = np.full(w, np.nan)
    bot = np.full(w, np.nan)
    for x in range(w):
        ys = np.flatnonzero(dark[:, x])
        if ys.size > 8:
            top[x], bot[x] = ys[0], ys[-1]
    ok = np.isfinite(top) & np.isfinite(bot) & ((bot - top) > 0.5 * np.nanmedian(bot - top))
    T = np.polyval(np.polyfit(xs[ok], top[ok], 3), xs)
    B = np.polyval(np.polyfit(xs[ok], bot[ok], 3), xs)
    band = float(np.median(B - T))
    H = int(round(band * 1.5))
    pad = (H - band) / 2
    yy = T[None, :] - pad + np.arange(H)[:, None] * (band + 2 * pad) / H
    xx = np.broadcast_to(xs[None, :], yy.shape)
    return map_coordinates(a.astype(np.float32), [yy, xx], order=1, mode="nearest")


def flatten(a: np.ndarray) -> np.ndarray:
    bg = gaussian_filter(a, 25)
    return np.clip(a / np.maximum(bg, 1) * np.median(bg), 0, 255)


def richardson_lucy(img: np.ndarray, sigma: float, iters: int) -> np.ndarray:
    x = np.arange(-6, 7)
    psf = np.exp(-0.5 * (x / sigma) ** 2)
    psf = np.outer(psf, psf)
    psf /= psf.sum()
    o = img / 255.0
    e = np.clip(o, 1e-3, 1)
    for _ in range(iters):
        conv = fftconvolve(e, psf, mode="same")
        e = e * fftconvolve(o / np.maximum(conv, 1e-3), psf[::-1, ::-1], mode="same")
    return np.clip(e * 255, 0, 255)


def variants(base: np.ndarray):
    yield "raw", base
    f = flatten(base)
    yield "flat", f
    for amt, rad in ((1.5, 2), (3, 2), (3, 3)):
        yield f"flat+unsharp a{amt} r{rad}", np.clip(f + amt * (f - gaussian_filter(f, rad)), 0, 255)
    for sig, it in ((1.5, 10), (2.5, 15)):
        yield f"flat+RL s{sig} i{it}", richardson_lucy(f, sig, it)


def manual_bars(view: np.ndarray, thr: float) -> list[dict]:
    """The two border bars from the row profile of a rectified strip.

    The instrument's `_find_bars` wants each bar as ONE continuous >60 %-dark
    run over 55 % of the width; a glare gap in a phone frame breaks that and
    the strip is refused with the bars plainly visible (strip 3 of the
    four-strip frame, 2026-09-24).  After rectification the bars are level,
    so their rows are the two peaks of the dark-fraction profile, nine
    modules apart, and their extents the dark span of those rows."""
    dark = view < thr
    prof = dark.mean(axis=1)
    rows: list[int] = []
    for r in np.argsort(prof)[::-1]:
        if prof[r] < 0.6:
            break
        if all(abs(int(r) - q) > 30 for q in rows):
            rows.append(int(r))
        if len(rows) == 2:
            break
    if len(rows) < 2:
        return []
    bars = []
    for r in sorted(rows):
        band = dark[max(0, r - 3):r + 4].mean(axis=0)
        cols = np.flatnonzero(band > 0.5)
        bars.append({"slope": 0.0, "intercept": float(r), "x0": float(cols.min()),
                     "x1": float(cols.max() + 1), "height": 15.0})
    return bars


def decode_any(img: np.ndarray, rot: int):
    """The instrument's decoder first; if it finds no bar pair, the manual bars."""
    view = np.clip(img if rot == 0 else img[::-1, ::-1], 0, 255).astype(np.uint8)
    obs = list(rs.decode_report_image(view))
    if obs:
        return obs, "instrument"
    v = rs._reflectance(view)
    thr = 0.5 * (np.percentile(v, 90) + np.percentile(v, 2))
    bars = manual_bars(v, thr)
    if len(bars) < 2:
        return [], "manual-bars: none"
    dec = rs._decode_pair(v, bars[0], bars[1])
    if dec is None:
        return [], "manual-bars: pair rejected"
    return [rs._observation(dec, placement_index=None, rotated_180=(rot == 180))], "manual-bars"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("photo", type=Path)
    ap.add_argument("--box", type=int, nargs=4, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--preview-width", type=int, default=1050)
    ap.add_argument("--rotate", type=int, default=90, help="degrees to rotate the crop so the strip runs left-to-right")
    ap.add_argument("--save", type=Path, default=None, help="write the rectified strip PNG here")
    args = ap.parse_args()
    im = ImageOps.exif_transpose(Image.open(args.photo)).convert("L")
    s = im.width / args.preview_width
    x0, y0, x1, y1 = (int(v * s) for v in args.box)
    crop = im.crop((x0, y0, x1, y1))
    if args.rotate:
        crop = crop.rotate(args.rotate, expand=True)
    rect = rectify(np.asarray(crop))
    if args.save:
        Image.fromarray(np.clip(rect, 0, 255).astype(np.uint8)).save(args.save)
    print(f"{args.photo.name}: rectified strip {rect.shape[1]}x{rect.shape[0]} px "
          f"(~{rect.shape[1] / rs.REPORT_WIDTH_MODULES:.1f} px per module)")
    winner = None
    for name, v in variants(rect):
        for rot in (0, 180):
            obs, how = decode_any(v, rot)
            for o in obs:
                print(f"  {name:<24} rot {rot:3d}  {o.status:<12} clock {o.clock_score:.2f} "
                      f"sync {o.sync_errors} parity {o.parity_errors} xor {o.row_xor_errors}  [{how}]")
                if o.status == "ok" and winner is None:
                    winner = (f"{name} [{how}]", rot, o)
    if winner is None:
        print("NO CRC-valid report from this photo (try a sharper / closer frame)")
        return 1
    name, rot, o = winner
    r = o.report
    print(f"\nREPORT (from '{name}', rotation {rot}, CRC OK):")
    print(f"  identity: stage {r.identity.stage}, kind {r.identity.kind}, copy {r.identity.copy_index}, "
          f"request_code {r.identity.request_code}, layout_digest_128 {r.identity.layout_digest_128}")
    d = r.device_readback
    print(f"  device:   product '{d.product}' version '{d.version}' language_level {d.language_level}")
    print(f"            default_resolution {d.default_resolution}  EFFECTIVE_resolution {d.effective_resolution}")
    print(f"            page_size_points {d.page_size_points}  color_model {d.process_color_model}  duplex {d.duplex}  nonce {d.print_nonce}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
