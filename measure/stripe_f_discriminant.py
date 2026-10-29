"""Sheet F: how much of the M and Y cell information is in the pixels?

Offline, supervised ceiling (a SCORE-column instrument: it reads the
emitted ground truth, like measure/c-third-layer-20260906/analyze_patches.py
did for sheet H).  For every cell of a set of tiles it extracts the raw
RGB patch around the cell centre at the committed pose and fits linear
discriminants of increasing scope:

  box       the production aperture: 0.7-cell box mean of the sensitive
            channel (what the arms see), best single threshold
  rgb3      the three channel means at the cell (QDA, the colour model)
  patch     ridge-LDA over the whole 3-cell x 3-cell RGB patch (432 feats)
  patch+C   patch + the C plane's 3x3 neighbourhood bits (C is certified
            page-wide, so this context is blind-available)
  patch+CM  patch + C and M 3x3 bits (the ceiling for Y if M certified)
  branch    patch, one LDA per centre-cell sibling state (W8 'branches')

Train on even tile rows, test on odd, outside the stripe; also train in
the stripe / test outside and vice versa.  Reports test error at the
training threshold, AUC, and d' of the score.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from analyzer.frame import tile_footprint
from analyzer.inputs import load_run
from analyzer.sample import lane_footprint, lanes_for_tile, open_crops, \
    read_rgb
from measure.stripe_f import load_gt_cells

TILE = 64
WIN_CELLS = 3          # patch window edge in cells
BINPX = 3              # pixel binning inside the window


def tile_features(inputs, gt_cells, ty, tx):
    fp = tile_footprint(inputs.row, 0, ty, tx, 0, geometry=inputs.geometry)
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
    win = int(round(WIN_CELLS * pitch))          # 36 px
    half = win // 2
    cells = fp.page_cells_yx
    gt = gt_cells[:, cells[:, 0], cells[:, 1]].astype(np.uint8)   # (3, n)
    gt_grid = gt.reshape(3, TILE, TILE)
    # neighbourhood bits (3x3) per plane, zero-padded
    pad = np.zeros((3, TILE + 2, TILE + 2), np.uint8)
    pad[:, 1:-1, 1:-1] = gt_grid
    nb = np.stack([pad[:, 1 + dy:1 + dy + TILE, 1 + dx:1 + dx + TILE]
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=1)  # (3, 9, 64, 64)
    nb = nb.reshape(3, 9, TILE * TILE)
    ok = lfp.observed & np.all(np.isfinite(pts), axis=1)
    feats, box, rgb3, labels, ctx_c, ctx_cm, keep = [], [], [], [], [], [], []
    ap = max(1, int(round(0.7 * pitch)))
    a2 = ap // 2
    for i in np.flatnonzero(ok):
        cy, cx = pts[i] - (crops.y0, crops.x0)
        y, x = int(round(cy)), int(round(cx))
        if y - half < 0 or x - half < 0 or y + half + 1 > raw.shape[0] or x + half + 1 > raw.shape[1]:
            continue
        w = raw[y - half:y - half + win, x - half:x - half + win].astype(np.float32)
        # bin BINPX x BINPX
        wb = w.reshape(win // BINPX, BINPX, win // BINPX, BINPX, 3).mean((1, 3))
        feats.append(wb.ravel())
        b = raw[y - a2:y - a2 + ap, x - a2:x - a2 + ap].astype(np.float32).mean((0, 1))
        box.append(b)
        rgb3.append(b)
        labels.append(gt[:, i])
        ctx_c.append(nb[0, :, i])
        ctx_cm.append(np.concatenate([nb[0, :, i], nb[1, :, i]]))
        keep.append(i)
    return dict(ty=ty, tx=tx, X=np.asarray(feats, np.float32), box=np.asarray(box, np.float32),
                y=np.asarray(labels, np.uint8), ctx_c=np.asarray(ctx_c, np.float32),
                ctx_cm=np.asarray(ctx_cm, np.float32), n=len(keep))


def fit_lda(X, y, lam=1e-2):
    mu = X.mean(0); Xs = X - mu; sd = Xs.std(0) + 1e-6; Xs = Xs / sd
    t = np.where(y == 1, 1.0, -1.0)
    XtX = Xs.T @ Xs / len(y) + lam * np.eye(X.shape[1])
    w = np.linalg.solve(XtX, Xs.T @ t / len(y))
    s = Xs @ w
    thr = 0.5 * (s[y == 1].mean() + s[y == 0].mean())
    return mu, sd, w, thr


def apply_lda(X, f):
    mu, sd, w, thr = f
    return ((X - mu) / sd) @ w - thr


def qda_fit(X, y):
    out = {}
    for c in (0, 1):
        Z = X[y == c]; out[c] = (Z.mean(0), np.cov(Z.T) + 1e-6 * np.eye(X.shape[1]))
    return out


def qda_score(X, m):
    def ll(mu, S):
        Si = np.linalg.inv(S); r = X - mu
        return -0.5 * np.einsum('ni,ij,nj->n', r, Si, r) - 0.5 * np.log(np.linalg.det(S))
    return ll(*m[1]) - ll(*m[0])


def metrics(score, y):
    err = float(((score > 0) != (y == 1)).mean())
    r = score.argsort().argsort().astype(float) + 1
    npos = int((y == 1).sum())
    auc = float((r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * (len(y) - npos)))
    d = float((score[y == 1].mean() - score[y == 0].mean())
              / np.sqrt(0.5 * (score[y == 1].var() + score[y == 0].var())))
    return dict(err=err, auc=auc, dprime=d, n=int(len(y)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gen-dir", required=True)
    ap.add_argument("--format-ref", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rows", default="2,3,6,7,10,11,14,15,18,19,22,23")
    ap.add_argument("--cols", default="4,8,16,20")
    ap.add_argument("--stripe-col", type=int, default=12)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    inputs = load_run(args.run_dir, format_ref=args.format_ref)
    gt_cells = load_gt_cells(Path(args.gen_dir))
    rows = [int(v) for v in args.rows.split(",")]
    cols = [int(v) for v in args.cols.split(",")]

    tiles = []
    for ty in rows:
        for tx in cols + [args.stripe_col]:
            t = tile_features(inputs, gt_cells, ty, tx)
            if t is not None:
                tiles.append(t)
        print(f"row {ty}: {len(tiles)} tiles so far", flush=True)

    def pool(sel):
        ts = [t for t in tiles if sel(t)]
        return {k: np.concatenate([t[k] for t in ts]) for k in ("X", "box", "y", "ctx_c", "ctx_cm")}

    outside_even = pool(lambda t: t["tx"] != args.stripe_col and t["ty"] % 2 == 0)
    outside_odd = pool(lambda t: t["tx"] != args.stripe_col and t["ty"] % 2 == 1)
    stripe_even = pool(lambda t: t["tx"] == args.stripe_col and t["ty"] % 2 == 0)
    stripe_odd = pool(lambda t: t["tx"] == args.stripe_col and t["ty"] % 2 == 1)
    print("cells: outside even/odd", len(outside_even["y"]), len(outside_odd["y"]),
          "stripe even/odd", len(stripe_even["y"]), len(stripe_odd["y"]))

    results = []
    CH = {"C": 0, "M": 1, "Y": 2}
    for plane in ("M", "Y", "C"):
        p = CH[plane]
        for train_name, tr, test_name, te in (
                ("outside-even", outside_even, "outside-odd", outside_odd),
                ("stripe-even", stripe_even, "stripe-odd", stripe_odd),
                ("stripe-all", pool(lambda t: t["tx"] == args.stripe_col), "outside-odd", outside_odd),
                ("outside-even", outside_even, "stripe-odd", stripe_odd)):
            ytr, yte = tr["y"][:, p], te["y"][:, p]
            row = {"plane": plane, "train": train_name, "test": test_name}
            # box: sensitive channel mean, ink is dark -> score = thr - value
            v = tr["box"][:, p]; thr = 0.5 * (v[ytr == 1].mean() + v[ytr == 0].mean())
            row["box"] = metrics(thr - te["box"][:, p], yte)
            # rgb3 QDA
            m = qda_fit(tr["box"], ytr); row["rgb3-qda"] = metrics(qda_score(te["box"], m), yte)
            # patch LDA
            f = fit_lda(tr["X"], ytr); row["patch"] = metrics(apply_lda(te["X"], f), yte)
            # patch + C context
            Xc_tr = np.hstack([tr["X"], tr["ctx_c"] * 100]); Xc_te = np.hstack([te["X"], te["ctx_c"] * 100])
            f = fit_lda(Xc_tr, ytr); row["patch+C"] = metrics(apply_lda(Xc_te, f), yte)
            # patch + C and M context (for Y and C only; for M it leaks the label)
            if plane != "M":
                Xcm_tr = np.hstack([tr["X"], tr["ctx_cm"] * 100]); Xcm_te = np.hstack([te["X"], te["ctx_cm"] * 100])
                f = fit_lda(Xcm_tr, ytr); row["patch+CM"] = metrics(apply_lda(Xcm_te, f), yte)
            # branch: one LDA per centre-cell C state (blind-available branch)
            sc_tr = tr["ctx_c"][:, 4]; sc_te = te["ctx_c"][:, 4]
            score = np.zeros(len(yte))
            for s in (0, 1):
                f = fit_lda(tr["X"][sc_tr == s], ytr[sc_tr == s])
                score[sc_te == s] = apply_lda(te["X"][sc_te == s], f)
            row["branch-C"] = metrics(score, yte)
            results.append(row)
            print(f"{plane} train {train_name:13s} test {test_name:12s} | "
                  + " | ".join(f"{k} err {row[k]['err']:.3f} d' {row[k]['dprime']:.2f}"
                               for k in ("box", "rgb3-qda", "patch", "patch+C", "patch+CM", "branch-C") if k in row),
                  flush=True)
    (out / "discriminant.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
