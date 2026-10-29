"""Sheet F: the joint-model ceiling — a wide window and a genie context.

Any HMM / MRF / iterative (turbo) scheme can at best hand the per-cell
classifier the TRUE states of the neighbouring cells.  So the ceiling of
that whole family is a classifier GIVEN those states.  This instrument
fits, per plane and region (outside the stripe / inside):

  window W x W cells of raw RGB (default 9x9 = 108 px), 4-px binned
  contexts:
    none      pixels only
    C         the C plane's W x W bits (blind-available: C is certified)
    genie     all three planes' W x W bits, the centre's OWN bit removed
              (what a perfect neighbour decoder would supply)
  models: ridge LDA; one-hidden-layer network (numpy) for the contexts
          that matter.

Train even tile rows, test odd rows.  Reports error, d', the BSC capacity
bound 1-H(err), and the error by sibling state.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from analyzer.frame import tile_footprint
from analyzer.inputs import load_run
from analyzer.sample import lane_footprint, lanes_for_tile, open_crops, \
    read_rgb
from measure.stripe_f import load_gt_cells
from measure.stripe_f_discriminant import fit_lda, apply_lda, metrics
from measure.stripe_f_phase import mlp_fit, mlp_score


def h2(p):
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -p * np.log2(p) - (1 - p) * np.log2(1 - p)


def extract(inputs, gt_cells, ty, tx, W, binpx, halo):
    """Pixels + W x W neighbourhood bits for every cell of one tile.

    The footprint carries `halo` cells so the neighbourhood bits of edge
    cells are real; features are computed for the in-tile cells only.
    """
    fp = tile_footprint(inputs.row, 0, ty, tx, halo, geometry=inputs.geometry)
    lane = lanes_for_tile(inputs, 0, ty, tx)[0]
    lfp = lane_footprint(lane, fp)
    if lfp is None:
        return None
    crops = open_crops(lane, lfp, bound_dots=2.0, cell_dots=3, keep_raw=True)
    r = read_rgb(crops, lfp, offset_dots_xy=(0.0, 0.0))
    if r.refusal:
        return None
    pts = r.points_yx
    raw = np.asarray(crops.raw_rgb)
    pitch = float(crops.pitch_px_level)
    win = int(round(W * pitch)); half = win // 2
    cells = fp.page_cells_yx
    y0, x0 = cells[:, 0].min(), cells[:, 1].min()
    hy, hx = cells[:, 0].max() - y0 + 1, cells[:, 1].max() - x0 + 1
    grid = np.zeros((3, hy, hx), np.uint8)
    grid[:, cells[:, 0] - y0, cells[:, 1] - x0] = gt_cells[:, cells[:, 0], cells[:, 1]]
    R = W // 2
    padg = np.zeros((3, hy + 2 * R, hx + 2 * R), np.uint8); padg[:, R:R + hy, R:R + hx] = grid
    feats, ctx, labels, keep = [], [], [], []
    for i in np.flatnonzero(lfp.observed & fp.in_tile & np.all(np.isfinite(pts), axis=1)):
        cy, cx = pts[i] - (crops.y0, crops.x0)
        y, x = int(round(cy)), int(round(cx))
        if y - half < 0 or x - half < 0 or y - half + win > raw.shape[0] or x - half + win > raw.shape[1]:
            continue
        w = raw[y - half:y - half + win, x - half:x - half + win].astype(np.float32)
        n = win // binpx
        wb = w[:n * binpx, :n * binpx].reshape(n, binpx, n, binpx, 3).mean((1, 3))
        feats.append(wb.ravel())
        gy, gx = cells[i, 0] - y0, cells[i, 1] - x0
        ctx.append(padg[:, gy:gy + W, gx:gx + W].reshape(3, -1))
        labels.append(grid[:, gy, gx])
        keep.append(i)
    return dict(ty=ty, tx=tx, X=np.asarray(feats, np.float32), ctx=np.asarray(ctx, np.uint8),
                y=np.asarray(labels, np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gen-dir", required=True)
    ap.add_argument("--format-ref", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", default="2,3,6,7,10,11,14,15,18,19,22,23")
    ap.add_argument("--cols", default="4,8,16,20")
    ap.add_argument("--stripe-col", type=int, default=12)
    ap.add_argument("--window", type=int, default=9)
    ap.add_argument("--binpx", type=int, default=4)
    ap.add_argument("--mlp-epochs", type=int, default=8)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    W = args.window
    cache = out / f"features_w{W}_b{args.binpx}.npz"
    if cache.exists():
        z = np.load(cache); d = {k: z[k] for k in z.files}
    else:
        inputs = load_run(args.run_dir, format_ref=args.format_ref)
        gt_cells = load_gt_cells(Path(args.gen_dir))
        parts = []
        for ty in [int(v) for v in args.rows.split(",")]:
            for tx in [int(v) for v in args.cols.split(",")] + [args.stripe_col]:
                t = extract(inputs, gt_cells, ty, tx, W, args.binpx, W // 2 + 1)
                if t is not None:
                    n = len(t["y"]); parts.append(dict(t, ty_arr=np.full(n, ty), tx_arr=np.full(n, tx)))
            print("row", ty, "extracted", flush=True)
        d = {k: np.concatenate([p[k] for p in parts]) for k in ("X", "ctx", "y", "ty_arr", "tx_arr")}
        np.savez(cache, **d)
    print("cells", len(d["y"]), "pixel features", d["X"].shape[1], "context bits per plane", d["ctx"].shape[2], flush=True)
    outside = d["tx_arr"] != args.stripe_col
    even = d["ty_arr"] % 2 == 0
    centre = (W * W) // 2
    CH = {"C": 0, "M": 1, "Y": 2}
    for plane in ("M", "Y"):
        p = CH[plane]
        ctx_c = d["ctx"][:, 0, :].astype(np.float32) * 100
        genie = d["ctx"].astype(np.float32).copy(); genie[:, p, centre] = 0.0   # own bit removed
        genie = genie.reshape(len(genie), -1) * 100
        for region, sel in (("outside", outside), ("stripe", ~outside)):
            tr = sel & even; te = sel & ~even
            ytr, yte = d["y"][tr, p], d["y"][te, p]
            oth = [q for q in range(3) if q != p]
            sib = d["y"][te][:, oth[0]] + 2 * d["y"][te][:, oth[1]]
            sibnames = ["none", "CMY"[oth[0]], "CMY"[oth[1]], "both"]
            for cname, Xf, use_mlp in (("none", d["X"], False),
                                       ("C", np.hstack([d["X"], ctx_c]), region == "outside"),
                                       ("genie", np.hstack([d["X"], genie]), True)):
                f = fit_lda(Xf[tr], ytr, lam=3e-2); sc = apply_lda(Xf[te], f); m = metrics(sc, yte)
                bystate = {sibnames[s]: round(float(((sc[sib == s] > 0) != (yte[sib == s] == 1)).mean()), 3) for s in range(4)}
                print(f"{plane} {region:8s} ctx {cname:6s} LDA : err {m['err']:.3f} d' {m['dprime']:.2f} "
                      f"cap<= {1 - h2(m['err']):.2f} bit/cell  by state {bystate}", flush=True)
                if use_mlp:
                    mm = mlp_fit(Xf[tr], ytr, hidden=96, epochs=args.mlp_epochs, seed=2)
                    sc = mlp_score(Xf[te], mm); m = metrics(sc, yte)
                    bystate = {sibnames[s]: round(float(((sc[sib == s] > 0) != (yte[sib == s] == 1)).mean()), 3) for s in range(4)}
                    print(f"{plane} {region:8s} ctx {cname:6s} MLP : err {m['err']:.3f} d' {m['dprime']:.2f} "
                          f"cap<= {1 - h2(m['err']):.2f} bit/cell  by state {bystate}", flush=True)


if __name__ == "__main__":
    main()
