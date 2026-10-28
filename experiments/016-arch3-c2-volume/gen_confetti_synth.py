#!/usr/bin/env python
"""Synthetic confetti-session generator (v2 fixture): render pieces from
the SOURCE bitmap instead of re-rotating the scan.

Why: the scan-based fixture (gen_confetti_session.py) double-interpolates
an already-marginal 8 px/cell raster (generator rotation + segmenter
counter-rotation) — measured to crush session yield. Here each piece is
produced by ONE direct coordinate sampling of the composed page's cell
field (piecewise-constant vector truth, supersampled area-averaged), so
arbitrary rotation costs nothing; the scan is then MIMICKED by an
optical-only channel (Gaussian PSF + sensor noise + level drift),
deliberately WITHOUT the M0 dev morphology (known-pessimistic at c2 — no
blind receiver passes sim-c2; this fixture tests the SESSION machinery,
channel realism was proven on real toner in 014/016). Channel constants
are calibrated by test to land in the measured real-scan band (ctx BER
~1-8% at 8 px/cell).

Same carve schedule / shelf packing / manifest as the scan-based
generator (imported), same rng label family. Usage:
  env/bin/python gen_confetti_synth.py [--out scratch/confetti_synth]
      [--schedule ...] [--backing white] [--blur 2.0] [--noise 5.0]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paperholo import compose  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
import gen_confetti_session as gcs  # noqa: E402
import gen_e016  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
OUT_DPI = 2400.0
PPC = 8              # px per cell at 2400 dpi, c2
SS = 2               # supersample factor for the one true resample
PAPER, INK = 205.0, 45.0     # measured e016 Canon grey levels (approx)
BLUR_SIGMA = 2.4     # optical PSF at output px. Calibration TARGET is the
NOISE_SIGMA = 7.0    # ctx-detector band (real e016 scans: ctx 2-5%), NOT
#                      the global 8-10% raw band: the global gap is dev
#                      morphology (deliberately excluded here), which does
#                      not degrade geometry — matching it via blur would
#                      over-penalize the lattice lock (a rotated piece
#                      pays the receiver's counter-rotation resample on
#                      top, exactly as a real rotated confetti does).


def render_piece(refl_cells: np.ndarray, rect: tuple[int, int, int],
                 angle_deg: float, backing: float,
                 gen: np.random.Generator, blur: float, noise: float
                 ) -> np.ndarray:
    """One piece: direct inverse-map sampling of the cell field at SS
    supersampling, box-mean to PPC, then the optical channel."""
    y0, x0, side = rect
    a = np.deg2rad(angle_deg)
    half = side / 2.0
    n_out = int(np.ceil(side * (abs(np.cos(a)) + abs(np.sin(a))))) + 2
    N = n_out * PPC * SS
    d = (np.arange(N) + 0.5) / (PPC * SS) - n_out / 2.0
    dv, du = np.meshgrid(d, d, indexing="ij")
    cy, cx = y0 + half, x0 + half
    yy = cy + dv * np.cos(a) - du * np.sin(a)
    xx = cx + dv * np.sin(a) + du * np.cos(a)
    inside = ((yy >= y0) & (yy < y0 + side) & (xx >= x0) & (xx < x0 + side))
    iy = np.clip(yy.astype(np.int64), 0, refl_cells.shape[0] - 1)
    ix = np.clip(xx.astype(np.int64), 0, refl_cells.shape[1] - 1)
    hi = np.where(inside, refl_cells[iy, ix], backing)
    out = hi.reshape(N // SS, SS, N // SS, SS).mean(axis=(1, 3))
    out = ndimage.gaussian_filter(out, blur, mode="nearest")
    out = out + gen.normal(0.0, noise, out.shape)
    out = out * (1.0 + 0.02 * np.sin(np.linspace(0, 3.0, out.shape[0]))
                 )[:, None]                        # slow gain drift
    return np.clip(out, 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="scratch/confetti_synth")
    # default ends in descending dense sweeps: THIS generator's legacy
    # default issued 65.5% of the field (the real-toner confetti_session
    # fixture reads 67.1% — different rng label) — below the fountain's
    # 80% rank need by construction; dense 12+8 reach 77.9%, the 6/5 mm
    # tails (at the F13 placer's measured gated floor: 5 mm, 4 mm refused)
    # reach 88.4%. NOTE (2026-07-11 review, draw-faithful carve sim): even
    # 88.4% leaves best-per-tile geometrically unable to close (single-
    # piece >=70%-coverage ceiling 1027 tiles < K=1387; union ceiling
    # 1477) — this default is the placer STRESS fixture. The CLOSURE
    # fixture is the big-sweep schedule below (98.0% issued, union
    # ceiling 1734, single-piece ceiling 1603 > K):
    #   --schedule 38xsweep,12xsweep,8xsweep,6xsweep,5xsweep \
    #   --out scratch/confetti_synth_close
    ap.add_argument("--schedule", default="45x6,25x14,12x40,8x60,"
                                          "12xsweep,8xsweep,6xsweep,5xsweep")
    ap.add_argument("--gap-mm", type=float, default=6.0)
    ap.add_argument("--backing", default="white")
    ap.add_argument("--blur", type=float, default=BLUR_SIGMA)
    ap.add_argument("--noise", type=float, default=NOISE_SIGMA)
    args = ap.parse_args()
    backing = (gcs.BACKINGS[args.backing] if args.backing in gcs.BACKINGS
               else int(args.backing))

    spec = gen_e016.make_spec()
    vspec = gen_e016.make_vspec()
    data = gen_e016.make_data(vspec)
    import paperholo.fountain as fountain
    framed = fountain.encode_volume_pages(data, vspec)[0]
    cells = compose.compose_page(framed["payload_bits"], spec,
                                 gen_e016.SEED, page=0).cell_values
    refl = np.where(cells > 0, INK, PAPER).astype(np.float32)
    H_mm = int(cells.shape[0] / (600 / 25.4 / 2))
    W_mm = int(cells.shape[1] / (600 / 25.4 / 2))
    cpmm = 600 / 25.4 / 2                        # cells per mm (11.81)
    remaining = np.ones((H_mm, W_mm), bool)
    gen = rng(gen_e016.SEED, b"e016/confetti-synth/v1")
    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)
    gap_px = int(args.gap_mm * OUT_DPI / 25.4)
    session = []
    for si, part in enumerate(args.schedule.split(","), start=1):
        s_mm, cnt = part.strip().split("x")
        cnt_i = {"all": -1, "sweep": -2}.get(cnt)
        rects_mm = gcs.carve(remaining, float(s_mm),
                             int(cnt) if cnt_i is None else cnt_i, gen)
        if not rects_mm:
            break
        pieces, sizes, metas = [], [], []
        for (ym, xm, side_mm) in rects_mm:
            rect = (int(ym * cpmm), int(xm * cpmm), int(side_mm * cpmm))
            ang = float(gen.uniform(0.0, 360.0))
            p = render_piece(refl, rect, ang, backing, gen,
                             args.blur, args.noise)
            pieces.append(p)
            sizes.append(p.shape)
            metas.append({"cell_rect": list(rect), "side_mm": side_mm,
                          "angle_deg": round(ang, 2)})
        order = gen.permutation(len(pieces))
        pos, ch, cw = gcs.shelf_pack([sizes[i] for i in order], gap_px)
        canvas = np.full((ch, cw), backing, np.uint8)
        for (py, px), i in zip(pos, order):
            p = pieces[i]
            canvas[py:py + p.shape[0], px:px + p.shape[1]] = p
            metas[i]["canvas_yx"] = [int(py), int(px)]
        name = f"confetti_scan{si:02d}"
        Image.fromarray(canvas).save(outdir / f"{name}.png",
                                     dpi=(OUT_DPI, OUT_DPI))
        cov = 100 * (1 - remaining.mean())
        session.append({"scan": name, "pieces": len(metas),
                        "manifest": metas})
        print(f"scan {si}: {len(metas)} pieces @~{s_mm}mm, canvas "
              f"{ch}x{cw}px, cumulative {cov:.1f}%", flush=True)
    top = {"source": "SYNTH render of e016 page 0 (optical-only channel)",
           "data_sha256": hashlib.sha256(data).hexdigest(),
           "out_dpi": OUT_DPI, "backing_grey": backing,
           "blur_sigma": args.blur, "noise_sigma": args.noise,
           "paper_ink": [PAPER, INK],
           "field_consumed_frac": round(1 - float(remaining.mean()), 4),
           "rng_label": "e016/confetti-synth/v1", "scans": session}
    (outdir / "session_manifest.json").write_text(json.dumps(top, indent=1))
    print(f"manifest -> {outdir/'session_manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
