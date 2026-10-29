"""Sheet F: does the cell's phase against the device screen carry the
missing information, and does a nonlinear model beat the linear ceiling?

Builds on measure/stripe_f_discriminant.py (same tiles, same raw-patch
features, cached to an .npz on first use).  Adds:

  phase-branch   patch LDA fitted per bin of the cell's phase against the
                 plane's screen lattice (the moire between 3-dot cells and
                 the 3.62-dot / 2.83-dot device screens is page-stationary,
                 so a per-phase discriminant can absorb it if it is the loss)
  phase-feats    patch LDA + sin/cos of the screen phase and its harmonics
  mlp            one-hidden-layer network over patch + C context (numpy)

Screen lattice frequencies come from the 2-D spectra measured on this
sheet (measure/stripe_f 2-D FFT): R/G 0.0691 cyc/px at +/-14.2 deg,
B 0.0880 cyc/px at -134.6 deg, with 12 px per cell.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from analyzer.inputs import load_run
from measure.stripe_f import load_gt_cells
from measure.stripe_f_discriminant import fit_lda, apply_lda, metrics, \
    tile_features, TILE

PX_PER_CELL = 12.0
SCREEN = {  # plane -> (f cyc/px, angle deg) of its sensitive channel's peak
    "C": (0.0691, +14.2), "M": (0.0691, -14.2), "Y": (0.0880, -134.6)}


def screen_phase(plane: str, page_x: np.ndarray, page_y: np.ndarray) -> np.ndarray:
    f, ang = SCREEN[plane]
    fc = f * PX_PER_CELL
    fx, fy = fc * np.cos(np.radians(ang)), fc * np.sin(np.radians(ang))
    return np.mod(fx * page_x + fy * page_y, 1.0)          # in cycles


def load_or_build(args, inputs, gt_cells):
    cache = Path(args.out) / "features.npz"
    if cache.exists():
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    rows = [int(v) for v in args.rows.split(",")]
    cols = [int(v) for v in args.cols.split(",")] + [args.stripe_col]
    parts = []
    for ty in rows:
        for tx in cols:
            t = tile_features(inputs, gt_cells, ty, tx)
            if t is None:
                continue
            n = t["n"]
            parts.append(dict(t, ty_arr=np.full(n, ty), tx_arr=np.full(n, tx)))
        print("row", ty, "done", flush=True)
    d = {k: np.concatenate([p[k] for p in parts]) for k in ("X", "box", "y", "ctx_c", "ctx_cm", "ty_arr", "tx_arr")}
    # page cell coordinates: tile_features keeps observed cells in footprint
    # order (row-major within the tile) minus the ones it skipped at the
    # crop edge — recover them from the kept count is unsafe, so rebuild:
    # the discriminant stored no index; we re-derive here from n per tile
    # being exactly 64x64 when nothing was skipped (assert) .
    idx = []
    for p in parts:
        assert p["n"] == TILE * TILE, (p["ty"], p["tx"], p["n"])
        yy, xx = np.mgrid[0:TILE, 0:TILE]
        idx.append(np.stack([p["ty"] * TILE + yy.ravel(), p["tx"] * TILE + xx.ravel()], 1))
    d["page_yx"] = np.concatenate(idx)
    np.savez(cache, **d)
    return d


def mlp_fit(X, y, hidden=64, epochs=12, lr=0.05, seed=0, l2=1e-4):
    rng = np.random.default_rng(seed)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xs = ((X - mu) / sd).astype(np.float32)
    n, d = Xs.shape
    W1 = (rng.standard_normal((d, hidden)) / np.sqrt(d)).astype(np.float32); b1 = np.zeros(hidden, np.float32)
    W2 = (rng.standard_normal(hidden) / np.sqrt(hidden)).astype(np.float32); b2 = np.float32(0.0)
    t = y.astype(np.float32)
    B = 512
    for ep in range(epochs):
        order = rng.permutation(n)
        for i in range(0, n, B):
            j = order[i:i + B]; xb = Xs[j]; tb = t[j]
            h = np.maximum(xb @ W1 + b1, 0.0)
            z = h @ W2 + b2
            p = 1.0 / (1.0 + np.exp(-z))
            g = (p - tb) / len(j)
            gW2 = h.T @ g + l2 * W2; gb2 = g.sum()
            gh = np.outer(g, W2) * (h > 0)
            gW1 = xb.T @ gh + l2 * W1; gb1 = gh.sum(0)
            W1 -= lr * gW1; b1 -= lr * gb1; W2 -= lr * gW2; b2 -= lr * gb2
        lr *= 0.8
    return (mu, sd, W1, b1, W2, b2)


def mlp_score(X, m):
    mu, sd, W1, b1, W2, b2 = m
    h = np.maximum(((X - mu) / sd).astype(np.float32) @ W1 + b1, 0.0)
    return h @ W2 + b2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gen-dir", required=True)
    ap.add_argument("--format-ref", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", default="2,3,6,7,10,11,14,15,18,19,22,23")
    ap.add_argument("--cols", default="4,8,16,20")
    ap.add_argument("--stripe-col", type=int, default=12)
    ap.add_argument("--phase-bins", type=int, default=8)
    args = ap.parse_args()
    inputs = load_run(args.run_dir, format_ref=args.format_ref)
    gt_cells = load_gt_cells(Path(args.gen_dir))
    d = load_or_build(args, inputs, gt_cells)
    outside = d["tx_arr"] != args.stripe_col
    even = d["ty_arr"] % 2 == 0
    CH = {"C": 0, "M": 1, "Y": 2}
    page_y, page_x = d["page_yx"][:, 0].astype(float), d["page_yx"][:, 1].astype(float)
    for plane in ("M", "Y"):
        p = CH[plane]
        ph = screen_phase(plane, page_x, page_y)
        harm = np.stack([np.sin(2 * np.pi * k * ph) for k in (1, 2, 3)] + [np.cos(2 * np.pi * k * ph) for k in (1, 2, 3)], 1) * 100
        for region, sel in (("outside", outside), ("stripe", ~outside)):
            tr = sel & even; te = sel & ~even
            ytr, yte = d["y"][tr, p], d["y"][te, p]
            X = d["X"]; Xc = np.hstack([X, d["ctx_c"] * 100])
            res = {}
            f = fit_lda(Xc[tr], ytr); res["patch+C"] = metrics(apply_lda(Xc[te], f), yte)
            Xp = np.hstack([Xc, harm]); f = fit_lda(Xp[tr], ytr); res["phase-feats"] = metrics(apply_lda(Xp[te], f), yte)
            bins = np.minimum((ph * args.phase_bins).astype(int), args.phase_bins - 1)
            score = np.zeros(te.sum()); bte = bins[te]; btr = bins[tr]
            for b in range(args.phase_bins):
                f = fit_lda(Xc[tr][btr == b], ytr[btr == b]); score[bte == b] = apply_lda(Xc[te][bte == b], f)
            res["phase-branch"] = metrics(score, yte)
            # how much does the plain box threshold vary with phase? (diagnostic)
            v = d["box"][:, p]
            per_bin = [float(((v[te][bte == b] < np.median(v[tr])) != (yte[bte == b] == 1)).mean()) for b in range(args.phase_bins)]
            m = mlp_fit(Xc[tr], ytr, seed=1); res["mlp"] = metrics(mlp_score(Xc[te], m), yte)
            print(f"{plane} {region:8s} n_test {te.sum():6d} | " + " | ".join(f"{k} err {r['err']:.3f} d' {r['dprime']:.2f}" for k, r in res.items()), flush=True)
            print(f"      box-threshold error by screen-phase bin: {np.round(per_bin, 3).tolist()}")
            # per sibling state of the best model
            best = min(res, key=lambda k: res[k]["err"])
            sc = mlp_score(Xc[te], m) if best == "mlp" else score if best == "phase-branch" else apply_lda(Xp[te], fit_lda(Xp[tr], ytr)) if best == "phase-feats" else apply_lda(Xc[te], fit_lda(Xc[tr], ytr))
            oth = [q for q in range(3) if q != p]
            sib = d["y"][te][:, oth[0]] + 2 * d["y"][te][:, oth[1]]
            names = ["none", "C" if oth[0] == 0 else "M", "M" if oth[1] == 1 else "Y", "both"]
            print("      best", best, "error by sibling state:",
                  {names[s]: round(float(((sc[sib == s] > 0) != (yte[sib == s] == 1)).mean()), 3) for s in range(4)})


if __name__ == "__main__":
    main()
