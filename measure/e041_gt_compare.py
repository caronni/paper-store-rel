"""e041 — a scan against its ground truth, per cell state, without the receiver.

Both S1 and S6 carry sheet F's bits, so the printed state of every cell is
known.  For every tile this registers the scan to the tile's ground-truth
C plane by FFT cross-correlation of the red channel (C reads at d' ~5 on
both sheets), refines M and Y by the same correlation on their own
channels, samples each cell's R, G, B through a 0.5-cell box at the
registered centre, and bins the samples by the cell's true state
(W, C, M, CM, Y, CY, MY, CMY).

Per tile and plane it reports the single-ink-vs-white separation d', the
white and ink levels, the best-threshold hard error, and the registration
offsets; per page the state table (mean R, G, B per state) and the
lateral profile.  Comparing two sheets' tables is the answer to "why do
they look different".

    env/bin/python util/ps_gt.py \
        <evidence>/paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/F/jobs/page000.ps \
        --out build/e041/F-page000_gt.npy \
        --expect-sha256 a9420188d346c787db829a8d11ea164b17ebdf802e191cfe6e5883177fe899bf
    PYTHONPATH=src:. env/bin/python -m measure.e041_gt_compare \
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S1/captures/S1-canon-2400rgb.tiff \
        --gt build/e041/F-page000_gt.npy \
        --tag S1 --out build/e041/gt-compare

(2026-10-09: sheet F's page000_gt.npy is not in the published archive; util/ps_gt.py regenerates it
from the published PostScript, gated on the published F/emission/manifest.json's gt_sha256.)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from measure.e041_screen_map import field_bbox

Image.MAX_IMAGE_PIXELS = None
TILE = 64
CELL_DOTS = 3
STATES = ("W", "C", "M", "CM", "Y", "CY", "MY", "CMY")   # index = C + 2M + 4Y
PLANES = ("C", "M", "Y")


def load_gt(path: Path) -> np.ndarray:
    packed = np.load(path)
    bits = np.unpackbits(packed, axis=2, bitorder="big")
    return bits[:, 1::CELL_DOTS, 1::CELL_DOTS].astype(np.uint8)     # (3, 2240, 1536)


def xcorr_shift(img: np.ndarray, tmpl: np.ndarray, max_shift: int) -> tuple[float, float, float]:
    """Shift (dy, dx) of tmpl inside img maximising normalised correlation,
    sub-pixel by parabolic fit; returns (dy, dx, peak corr)."""
    a = img - img.mean(); b = tmpl - tmpl.mean()
    H, W = a.shape; h, w = b.shape
    pad = np.zeros_like(a); pad[:h, :w] = b
    cc = np.fft.irfft2(np.fft.rfft2(a) * np.conj(np.fft.rfft2(pad)), s=a.shape)
    cc = cc[:max_shift * 2 + 1, :max_shift * 2 + 1]
    iy, ix = np.unravel_index(np.argmax(cc), cc.shape)
    def sub(v, i):
        if 0 < i < v.size - 1:
            l, c, r = v[i - 1], v[i], v[i + 1]
            d = l - 2 * c + r
            return i + (0.5 * (l - r) / d if d != 0 else 0.0)
        return float(i)
    dy = sub(cc[:, ix], iy); dx = sub(cc[iy, :], ix)
    peak = cc[iy, ix] / (np.sqrt((a[:h, :w] ** 2).sum() * (b ** 2).sum()) + 1e-9)
    return float(dy), float(dx), float(peak)


def sample_cells(ch: np.ndarray, oy: float, ox: float, pitch: float, box: int = 6) -> np.ndarray:
    """Mean of a box x box px window at every cell centre of a 64x64 tile
    (one box filter over the tile's window, then one fancy index)."""
    from scipy.ndimage import uniform_filter
    ys = np.round(oy + (np.arange(TILE) + 0.5) * pitch).astype(int)
    xs = np.round(ox + (np.arange(TILE) + 0.5) * pitch).astype(int)
    y0, y1 = ys.min() - box, ys.max() + box + 1
    x0, x1 = xs.min() - box, xs.max() + box + 1
    win = ch[y0:y1, x0:x1]
    filt = uniform_filter(win, size=box, mode="nearest")
    return filt[np.ix_(ys - y0, xs - x0)].astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--gt", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", default="all", help="tile rows, e.g. 0,5,10 or all")
    ap.add_argument("--search-px", type=int, default=20)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    img = np.asarray(Image.open(args.scan))
    gt = load_gt(Path(args.gt))
    y0, y1, x0, x1 = field_bbox(img)
    pitch_y = (y1 - y0) / gt.shape[1]; pitch_x = (x1 - x0) / gt.shape[2]
    pitch = 0.5 * (pitch_y + pitch_x)
    print(f"{args.tag}: field bbox rows {y0}-{y1} cols {x0}-{x1}, pitch {pitch_y:.3f} x {pitch_x:.3f} px/cell")
    rows = range(gt.shape[1] // TILE) if args.rows == "all" else [int(v) for v in args.rows.split(",")]
    ny, nx = gt.shape[1] // TILE, gt.shape[2] // TILE

    def window(oy, ox, S):
        wy0, wx0 = int(oy) - S, int(ox) - S
        return wy0, wx0, img[wy0:wy0 + TILE * 12 + 2 * S + 12, wx0:wx0 + TILE * 12 + 2 * S + 12]

    def locate(g, ty, tx, oy, ox, S):
        wy0, wx0, win = window(oy, ox, S)
        tmpl = np.kron(g[0, ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE].astype(np.float32),
                       np.ones((12, 12), np.float32))
        dy, dx, pk = xcorr_shift(255.0 - win[..., 0].astype(np.float32), tmpl, S)
        return wy0 + dy, wx0 + dx, pk

    # orientation: the centre tile against the truth as-is and rotated 180 deg
    cty, ctx = ny // 2, nx // 2
    nom = lambda ty, tx: (y0 + ty * TILE * pitch_y, x0 + tx * TILE * pitch_x)
    cands = {}
    for name, g in (("as-is", gt), ("rot180", gt[:, ::-1, ::-1])):
        cands[name] = locate(g, cty, ctx, *nom(cty, ctx), 150)
    orient = max(cands, key=lambda k: cands[k][2])
    gt_o = gt if orient == "as-is" else gt[:, ::-1, ::-1]
    print(f"orientation: {orient} (centre-tile corr as-is {cands['as-is'][2]:.2f}, rot180 {cands['rot180'][2]:.2f})")
    # global affine page-cell -> scan px from six anchors (wide search)
    anchors = [(2, 2), (2, nx - 3), (cty, ctx), (ny - 3, 2), (ny - 3, nx - 3), (cty, 2)]
    A, B = [], []
    for ty, tx in anchors:
        oy, ox, pk = locate(gt_o, ty, tx, *nom(ty, tx), 150)
        if pk > 0.2:
            A.append([ty * TILE, tx * TILE, 1.0]); B.append([oy, ox])
    A, B = np.asarray(A), np.asarray(B)
    if len(A) < 3:
        raise SystemExit("affine anchors failed; is the scan this sheet?")
    M, *_ = np.linalg.lstsq(A, B, rcond=None)         # (3,2): [cy, cx, 1] -> [y, x]
    pitch = 0.5 * (np.hypot(M[0, 0], M[0, 1]) + np.hypot(M[1, 0], M[1, 1]))
    print(f"affine from {len(A)} anchors: pitch {pitch:.4f} px/cell, skew {np.degrees(np.arctan2(M[0, 1], M[0, 0])):+.3f} deg")
    S = args.search_px
    tiles = []
    state_sum = np.zeros((8, 3)); state_n = np.zeros(8)
    for ty in rows:
        for tx in range(nx):
            gy, gx = ty * TILE, tx * TILE
            tgt = gt_o[:, gy:gy + TILE, gx:gx + TILE]
            oy, ox = (np.array([gy, gx, 1.0]) @ M)
            wy0, wx0, win = window(oy, ox, S)
            if win.shape[0] < TILE * 12 + 2 * S or win.shape[1] < TILE * 12 + 2 * S:
                continue
            reg = {}
            tmpl = np.kron(tgt[0].astype(np.float32), np.ones((12, 12), np.float32))
            dy, dx, pk = xcorr_shift(255.0 - win[..., 0].astype(np.float32), tmpl, S)
            reg[0] = (wy0 + dy, wx0 + dx, pk)
            # M and Y: refine within +/- PLANE_S px of the C pose (the planes
            # differ by at most ~2 dots = 8 px; a wider search finds screen aliases)
            PLANE_S = 6
            for p in (1, 2):
                py0, px0 = int(round(reg[0][0])) - PLANE_S, int(round(reg[0][1])) - PLANE_S
                pwin = img[py0:py0 + TILE * 12 + 2 * PLANE_S + 12, px0:px0 + TILE * 12 + 2 * PLANE_S + 12, p]
                tmpl = np.kron(tgt[p].astype(np.float32), np.ones((12, 12), np.float32))
                dy, dx, pk = xcorr_shift(255.0 - pwin.astype(np.float32), tmpl, PLANE_S)
                reg[p] = (py0 + dy, px0 + dx, pk)
            # the orientation flips the page: report tile indices in PAGE coordinates
            rec = {"ty": ty if orient == "as-is" else ny - 1 - ty,
                   "tx": tx if orient == "as-is" else nx - 1 - tx}
            st = (tgt[0] + 2 * tgt[1] + 4 * tgt[2]).astype(int)
            for p, name in enumerate(PLANES):
                oyp, oxp, pk = reg[p]
                vals = sample_cells(img[..., p], oyp, oxp, pitch)
                single = st == (1 << p); white = st == 0
                mu_w, sd_w = vals[white].mean(), vals[white].std()
                mu_i, sd_i = vals[single].mean(), vals[single].std()
                d = (mu_w - mu_i) / np.sqrt(0.5 * (sd_w ** 2 + sd_i ** 2))
                bit = tgt[p].astype(bool).ravel(); v = vals.ravel()
                order = np.argsort(v); vb = bit[order]
                cum_ink = np.cumsum(vb); n_ink = vb.sum()
                k = np.arange(1, v.size + 1)
                err = ((k - cum_ink) + (n_ink - cum_ink)) / v.size
                rec[name] = {"dprime": float(d), "white_mu": float(mu_w), "white_sd": float(sd_w),
                             "ink_mu": float(mu_i), "ink_sd": float(sd_i),
                             "hard_err": float(err.min()), "corr": float(pk),
                             "reg_dy_px": float(reg[p][0] - reg[0][0]), "reg_dx_px": float(reg[p][1] - reg[0][1])}
                if p == 0:
                    rgb = np.stack([sample_cells(img[..., q], oyp, oxp, pitch) for q in range(3)], -1)
                    for s_ in range(8):
                        m = st == s_
                        if m.any():
                            state_sum[s_] += rgb[m].sum(0); state_n[s_] += m.sum()
            tiles.append(rec)
        print(f"  row {ty} done ({len(tiles)} tiles)", flush=True)
    json.dump({"tiles": tiles, "state_mean_rgb": (state_sum / np.maximum(state_n, 1)[:, None]).tolist(),
               "state_n": state_n.tolist(), "pitch": float(pitch), "orientation": orient, "bbox": [y0, y1, x0, x1]},
              open(out / f"{args.tag}.json", "w"))
    print(f"\n{args.tag}: per-state mean R G B (n cells)")
    for s, name in enumerate(STATES):
        m = state_sum[s] / max(state_n[s], 1)
        print(f"  {name:4s} {m[0]:6.1f} {m[1]:6.1f} {m[2]:6.1f}   n={int(state_n[s])}")
    print(f"\n{args.tag}: whole-page medians per plane")
    for name in PLANES:
        v = [t[name] for t in tiles]
        print(f"  {name}: d' {np.median([x['dprime'] for x in v]):.2f}  white {np.median([x['white_mu'] for x in v]):.1f} (sd {np.median([x['white_sd'] for x in v]):.1f})"
              f"  ink {np.median([x['ink_mu'] for x in v]):.1f} (sd {np.median([x['ink_sd'] for x in v]):.1f})"
              f"  hard err {np.median([x['hard_err'] for x in v]):.3f}  corr {np.median([x['corr'] for x in v]):.2f}"
              f"  reg vs C dy {np.median([x['reg_dy_px'] for x in v]):+.1f} dx {np.median([x['reg_dx_px'] for x in v]):+.1f} px")
    print(f"\n{args.tag}: lateral profile by tile column (median over rows): tx | d' C M Y | hard err C M Y")
    for tx in range(nx):
        col = [t for t in tiles if t["tx"] == tx]
        if not col:
            continue
        print(f"  {tx:2d} | " + " ".join(f"{np.median([t[p]['dprime'] for t in col]):4.2f}" for p in PLANES)
              + " | " + " ".join(f"{np.median([t[p]['hard_err'] for t in col]):.3f}" for p in PLANES))


if __name__ == "__main__":
    main()
