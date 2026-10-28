#!/usr/bin/env python
"""exp-019 QUALIFICATION — measure the two design choices against EXACT ground
truth on constructed solid-cell fields:

  * GROWTH: hysteresis (find_lattice_candidates) vs the blind
    threshold+close+open+dilate baseline — boundary tightness, interior
    quiet-zone bridging, torn-shape fidelity.
  * WINDOW: multi-cell (2) vs per-cell (1) — field completeness.

Cases (native 24 px/cell): normal square, interior-quiet-zone (enclosed
blank hole), torn (corner cut off), faint (heavily blurred). Prints a table
(IoU vs GT field, component count, mask/GT area ratio) and writes a figure.

  env/bin/python qualify_e019.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import ndimage
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/019-platen-segment"))

from paperholo import segment                       # noqa: E402
import gen_platen_fixture as G                        # noqa: E402

C, DOT = 24, 8                     # native c3
BACK, MARG = 40.0, 225.0          # backing / paper margin


def make_case(rng, kind, fc=90, margin_c=22, back_c=14):
    """(image, gt_field_cells) — gt True where the printed piece genuinely is
    (the quiet hole is interior = part of the piece; the torn corner is not)."""
    field = G._render_field(rng, fc, fc, DOT)          # fc x fc solid cells
    gt = np.ones((fc, fc), bool)
    if kind == "quiet":                                # enclosed blank hole
        oy, ox, qs = fc * 2 // 5, fc // 4, fc // 4
        field[oy * C:(oy + qs) * C, ox * C:(ox + qs) * C] = MARG
        gt[oy:oy + qs, ox:ox + qs] = False             # a blank hole is NOT lattice
    elif kind == "torn":                               # cut the top-left corner
        yy, xx = np.mgrid[0:fc, 0:fc]
        keep = (yy + xx) >= fc * 0.55
        gt &= keep
        field[np.kron(~keep, np.ones((C, C), bool))] = MARG
    elif kind == "faint":
        field = ndimage.gaussian_filter(field, 11.0)   # heavy PSF
    off = back_c + margin_c
    N = off + fc + margin_c + back_c
    img = np.full((N * C, N * C), BACK, np.float32)
    img[back_c * C:(N - back_c) * C, back_c * C:(N - back_c) * C] = MARG
    img[off * C:(off + fc) * C, off * C:(off + fc) * C] = field
    img = ndimage.gaussian_filter(img, 6.0) + rng.normal(0, 7.0, img.shape)
    img = np.clip(img, 0, 255)                          # realistic 8-bit range
    gt_full = np.zeros((N, N), bool)
    gt_full[off:off + fc, off:off + fc] = gt
    return img, gt_full


def _overview(mask_cells, ref):                        # align to ref shape
    ny, nx = min(mask_cells.shape[0], ref.shape[0]), min(mask_cells.shape[1],
                                                         ref.shape[1])
    return mask_cells[:ny, :nx], ref[:ny, :nx]


def hyst(img, win):
    act = segment._activity_map(img, C, win)
    r = ndimage.binary_propagation(act > 22, mask=act > 8)
    r = ndimage.binary_opening(r, np.ones((3, 3)), iterations=max(1, round(win / 2)))
    return ndimage.binary_fill_holes(r)


def blind(img, win, std_delta=12.0):
    act = segment._activity_map(img, C, win)
    core = act > std_delta
    core = ndimage.binary_closing(core, np.ones((3, 3)), iterations=2)
    core = ndimage.binary_opening(core, np.ones((3, 3)),
                                  iterations=max(1, round(win / 2)))
    return ndimage.binary_dilation(core, np.ones((3, 3)), iterations=3)


def score(mask, gt):
    m, g = _overview(mask, gt)
    inter = (m & g).sum()
    iou = inter / max((m | g).sum(), 1)
    ncomp = ndimage.label(m)[1]
    kept = inter / max(g.sum(), 1)                 # field-kept
    ratio = m.sum() / max(g.sum(), 1)              # area vs true field
    return iou, ncomp, kept, ratio


def main():
    rng = np.random.default_rng(19)
    kinds = ["normal", "quiet", "torn", "faint"]
    detectors = [("blind  1-cell", lambda im: blind(im, 1)),
                 ("blind  2-cell", lambda im: blind(im, 2)),
                 ("HYSTERESIS 2c", lambda im: hyst(im, 2))]
    print(f"{'case':8s} {'detector':14s}  IoU   comps  field-kept  area/GT")
    figs = []
    for kind in kinds:
        img, gt = make_case(rng, kind)
        row = [img]
        for name, fn in detectors:
            m = fn(img)
            iou, nc, kept, ratio = score(m, gt)
            print(f"{kind:8s} {name:14s}  {iou:.2f}   {nc:2d}     {kept:5.1%}"
                  f"      {ratio:.2f}")
            row.append((m, name))
        figs.append((kind, gt, row))
        print()

    # figure: rows = cases, cols = [scan, GT, blind-1c, blind-2c, hyst-2c]
    def up(m, ref):
        return np.kron(m.astype(np.uint8) * 255, np.ones((6, 6), np.uint8))
    tiles = []
    for kind, gt, row in figs:
        img = row[0]
        base = np.clip((img[::4, ::4] - img.min()) / (np.ptp(img) + 1e-6) * 255,
                       0, 255).astype(np.uint8)
        strip = [base, up(gt, gt)[:base.shape[0], :base.shape[1]]]
        for (m, _name) in row[1:]:
            u = up(m, gt)[:base.shape[0], :base.shape[1]]
            strip.append(u)
        h = min(s.shape[0] for s in strip)
        strip = [s[:h] for s in strip]
        tiles.append(np.concatenate(strip, axis=1))
    hh = min(t.shape[0] for t in tiles)
    grid = np.concatenate([t[:hh] for t in tiles], axis=0)
    out = ROOT / "experiments/019-platen-segment/build/qualify_hyst_vs_blind.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(grid).save(out)
    print("cols: scan | GT | blind-1c | blind-2c | HYSTERESIS-2c ; "
          "rows: normal/quiet/torn/faint")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
