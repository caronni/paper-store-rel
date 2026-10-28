#!/usr/bin/env python
"""P4 stage 2: centroid-noise stats, v1 registration-model fits, dust sim.

Reads scratch/probe17_reg_<scan>.npz (from probe17_perplane_reg.py).

  * centroid noise per plane/channel = MAD-std of per-cell displacement
    after removing the per-tile median (noise excludes the registration
    field itself);
  * truth field = per-tile per-plane mean offsets (16 tiles), cross-checked
    against whole-tile GT xcorr;
  * v1 model: offset(y) = global + linear-in-y, fitted per plane/axis;
    residuals of TILE means vs model = model adequacy; also global-only and
    global+linear(y,x) for comparison;
  * dust simulation: draw N pure-plane cells per page from the measured
    per-cell dataset (N = dust-density ladder), fit v1 model, evaluate at
    the 16 tile centres vs truth; bootstrap -> max-abs prediction error
    distribution. Budget: half-cell at c3 = 1.5 dots.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_SCRATCH = Path(__file__).resolve().parent
PLANES = "CMY"
BUDGET_DOTS = 1.5
N_DUST = (100, 200, 400, 650, 900)
N_BOOT = 300
RNG = np.random.default_rng(20260710)


def mad_std(v: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def load(npz_path: Path) -> dict:
    z = np.load(npz_path)
    tiles = sorted({k.split("/")[0] for k in z.files})
    data: dict[str, dict] = {}
    for t in tiles:
        if not float(z[f"{t}/lock"][3]):
            continue
        d = {"lock": z[f"{t}/lock"]}
        for p in PLANES:
            d[p] = {k: z[f"{t}/{p}/{k}"]
                    for k in ("dy", "dx", "mass", "y_page", "x_page", "tile")}
        data[t] = d
    return data


def fit_eval(y: np.ndarray, x: np.ndarray, v: np.ndarray,
             yq: np.ndarray, xq: np.ndarray, model: str) -> np.ndarray:
    """LSQ fit of v(y,x); predict at (yq, xq). models: g, g+y, g+y+x."""
    cols = [np.ones_like(y)]
    qcols = [np.ones_like(yq)]
    if model in ("g+y", "g+y+x"):
        cols.append(y)
        qcols.append(yq)
    if model == "g+y+x":
        cols.append(x)
        qcols.append(xq)
    A = np.stack(cols, axis=1)
    coef, *_ = np.linalg.lstsq(A, v, rcond=None)
    return np.stack(qcols, axis=1) @ coef


def main(paths: list[str]) -> None:
    report = {}
    for path in map(Path, paths):
        data = load(path)
        tiles = sorted(data)
        res: dict = {"n_tiles": len(tiles)}
        # tile centres + truth means -------------------------------------
        truth = {p: {} for p in PLANES}
        for p in PLANES:
            ty = np.array([np.mean(data[t][p]["y_page"]) for t in tiles])
            tx = np.array([np.mean(data[t][p]["x_page"]) for t in tiles])
            mdy = np.array([np.mean(data[t][p]["dy"]) for t in tiles])
            mdx = np.array([np.mean(data[t][p]["dx"]) for t in tiles])
            xcy = np.array([data[t][p]["tile"][0] for t in tiles])
            xcx = np.array([data[t][p]["tile"][1] for t in tiles])
            truth[p] = dict(ty=ty, tx=tx, mdy=mdy, mdx=mdx, xcy=xcy, xcx=xcx)
            res[f"{p}/xcorr_vs_centroid_rms_dy"] = float(
                np.sqrt(np.mean((mdy - xcy) ** 2)))
            res[f"{p}/xcorr_vs_centroid_rms_dx"] = float(
                np.sqrt(np.mean((mdx - xcx) ** 2)))
        # per-cell noise (tile-median removed) ---------------------------
        for p in PLANES:
            ry = np.concatenate([data[t][p]["dy"] - np.median(data[t][p]["dy"])
                                 for t in tiles])
            rx = np.concatenate([data[t][p]["dx"] - np.median(data[t][p]["dx"])
                                 for t in tiles])
            res[f"{p}/cell_noise_dy_madstd"] = mad_std(ry)
            res[f"{p}/cell_noise_dx_madstd"] = mad_std(rx)
            res[f"{p}/cell_noise_dy_std"] = float(np.std(ry))
            res[f"{p}/cell_noise_dx_std"] = float(np.std(rx))
            res[f"{p}/n_cells_page"] = int(sum(len(data[t][p]["dy"])
                                               for t in tiles))
        # model adequacy on tile means -----------------------------------
        for p in PLANES:
            tr = truth[p]
            for ax, mv in (("dy", tr["mdy"]), ("dx", tr["mdx"])):
                for model in ("g", "g+y", "g+y+x"):
                    pred = fit_eval(tr["ty"], tr["tx"], mv,
                                    tr["ty"], tr["tx"], model)
                    r = mv - pred
                    res[f"{p}/{ax}/model_{model}_rms"] = float(
                        np.sqrt(np.mean(r ** 2)))
                    res[f"{p}/{ax}/model_{model}_max"] = float(
                        np.max(np.abs(r)))
                # drift over measured span (g+y fit)
                pred = fit_eval(tr["ty"], tr["tx"], mv, tr["ty"], tr["tx"], "g+y")
                span = tr["ty"].max() - tr["ty"].min()
                slope = np.polyfit(tr["ty"], mv, 1)[0]
                res[f"{p}/{ax}/gy_drift_over_span_dots"] = float(slope * span)
                res[f"{p}/{ax}/gy_slope_dots_per_100mm"] = float(
                    slope * 100 / 25.4 * 600)
                res[f"{p}/{ax}/offset_mean_dots"] = float(np.mean(mv))
        # relative plane fields (Y-C, M-C) at tile level ------------------
        # the common composite-lock jitter (measured ~0.35 dots rms/tile) is
        # common-mode across planes and cancels in these differences; in the
        # real receiver it is the PILOT grid's error budget, not dust's.
        for a, b in (("Y", "C"), ("M", "C"), ("Y", "M")):
            for ax in ("dy", "dx"):
                d = truth[a]["m" + ax] - truth[b]["m" + ax]
                ty = truth[a]["ty"]
                tx = truth[a]["tx"]
                slope = np.polyfit(ty, d, 1)[0]
                span = ty.max() - ty.min()
                res[f"{a}-{b}/{ax}/mean_dots"] = float(np.mean(d))
                res[f"{a}-{b}/{ax}/drift_over_span_dots"] = float(slope * span)
                res[f"{a}-{b}/{ax}/tile_scatter_madstd"] = mad_std(d)
                for model in ("g", "g+y", "g+y+x"):
                    pred = fit_eval(ty, tx, d, ty, tx, model)
                    r = d - pred
                    res[f"{a}-{b}/{ax}/model_{model}_rms"] = float(
                        np.sqrt(np.mean(r ** 2)))
                    res[f"{a}-{b}/{ax}/model_{model}_max"] = float(
                        np.max(np.abs(r)))
        # dust simulation --------------------------------------------------
        pool = {p: {k: np.concatenate([data[t][p][k] for t in tiles])
                    for k in ("dy", "dx", "y_page", "x_page")} for p in PLANES}
        for p in PLANES:
            tr = truth[p]
            npool = len(pool[p]["dy"])
            for n in N_DUST:
                maxerr, rmserr = [], []
                for _ in range(N_BOOT):
                    idx = RNG.choice(npool, size=n, replace=False)
                    errs = []
                    for ax, mv in (("dy", tr["mdy"]), ("dx", tr["mdx"])):
                        pred = fit_eval(pool[p]["y_page"][idx],
                                        pool[p]["x_page"][idx],
                                        pool[p][ax][idx],
                                        tr["ty"], tr["tx"], "g+y")
                        errs.append(np.abs(mv - pred))
                    e = np.concatenate(errs)
                    maxerr.append(e.max())
                    rmserr.append(np.sqrt(np.mean(e ** 2)))
                res[f"{p}/dust_n{n}/maxerr_med"] = float(np.median(maxerr))
                res[f"{p}/dust_n{n}/maxerr_p90"] = float(
                    np.percentile(maxerr, 90))
                res[f"{p}/dust_n{n}/rms_med"] = float(np.median(rmserr))
        # PAIR dust simulation: fit each plane from its own dust draw, then
        # score the predicted RELATIVE field (a-b) at tile centres vs the
        # tile-mean truth difference — common lock jitter cancels on both
        # sides; this is the dust-chargeable error.
        for a, b in (("Y", "C"), ("M", "C")):
            tra, trb = truth[a], truth[b]
            ty, tx = tra["ty"], tra["tx"]
            for n in N_DUST:
                na = min(n, len(pool[a]["dy"]))
                nb = min(n, len(pool[b]["dy"]))
                maxerr, rmserr = [], []
                for _ in range(N_BOOT):
                    ia = RNG.choice(len(pool[a]["dy"]), size=na, replace=False)
                    ib = RNG.choice(len(pool[b]["dy"]), size=nb, replace=False)
                    errs = []
                    for ax in ("dy", "dx"):
                        tdiff = tra["m" + ax] - trb["m" + ax]
                        pa = fit_eval(pool[a]["y_page"][ia], pool[a]["x_page"][ia],
                                      pool[a][ax][ia], ty, tx, "g+y")
                        pb = fit_eval(pool[b]["y_page"][ib], pool[b]["x_page"][ib],
                                      pool[b][ax][ib], ty, tx, "g+y")
                        errs.append(np.abs(tdiff - (pa - pb)))
                    e = np.concatenate(errs)
                    maxerr.append(e.max())
                    rmserr.append(np.sqrt(np.mean(e ** 2)))
                res[f"{a}-{b}/dust_n{n}/maxerr_med"] = float(np.median(maxerr))
                res[f"{a}-{b}/dust_n{n}/maxerr_p90"] = float(
                    np.percentile(maxerr, 90))
                res[f"{a}-{b}/dust_n{n}/rms_med"] = float(np.median(rmserr))
                res[f"{a}-{b}/dust_n{n}/n_used"] = [int(na), int(nb)]
        report[path.stem] = res
    out = _SCRATCH / "probe17_fit_report.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"-> {out}")

    # pretty print the essentials
    for scan, res in report.items():
        print(f"\n=== {scan} (tiles={res['n_tiles']}) ===")
        for p in PLANES:
            print(f" {p}: n={res[f'{p}/n_cells_page']}  "
                  f"cell-noise MADstd (dy,dx)=("
                  f"{res[f'{p}/cell_noise_dy_madstd']:.3f},"
                  f"{res[f'{p}/cell_noise_dx_madstd']:.3f}) dots  "
                  f"xcorr-vs-centroid rms=("
                  f"{res[f'{p}/xcorr_vs_centroid_rms_dy']:.3f},"
                  f"{res[f'{p}/xcorr_vs_centroid_rms_dx']:.3f})")
            for ax in ("dy", "dx"):
                print(f"   {ax}: mean {res[f'{p}/{ax}/offset_mean_dots']:+.2f} "
                      f"drift/span {res[f'{p}/{ax}/gy_drift_over_span_dots']:+.2f} "
                      f"| tile-resid rms g={res[f'{p}/{ax}/model_g_rms']:.3f} "
                      f"g+y={res[f'{p}/{ax}/model_g+y_rms']:.3f} "
                      f"g+y+x={res[f'{p}/{ax}/model_g+y+x_rms']:.3f} "
                      f"| max g+y={res[f'{p}/{ax}/model_g+y_max']:.3f}")
            for n in N_DUST:
                print(f"   dust n={n:4d}: maxerr med "
                      f"{res[f'{p}/dust_n{n}/maxerr_med']:.3f} "
                      f"p90 {res[f'{p}/dust_n{n}/maxerr_p90']:.3f} "
                      f"rms med {res[f'{p}/dust_n{n}/rms_med']:.3f} dots")
        for pair in ("Y-C", "M-C", "Y-M"):
            print(f" {pair}: dy mean {res[f'{pair}/dy/mean_dots']:+.2f} "
                  f"drift {res[f'{pair}/dy/drift_over_span_dots']:+.2f} "
                  f"scatter {res[f'{pair}/dy/tile_scatter_madstd']:.3f} | "
                  f"dx mean {res[f'{pair}/dx/mean_dots']:+.2f} "
                  f"drift {res[f'{pair}/dx/drift_over_span_dots']:+.2f} "
                  f"scatter {res[f'{pair}/dx/tile_scatter_madstd']:.3f}")
            for ax in ("dy", "dx"):
                print(f"   {ax} model resid: g rms/max "
                      f"{res[f'{pair}/{ax}/model_g_rms']:.3f}/"
                      f"{res[f'{pair}/{ax}/model_g_max']:.3f}  g+y "
                      f"{res[f'{pair}/{ax}/model_g+y_rms']:.3f}/"
                      f"{res[f'{pair}/{ax}/model_g+y_max']:.3f}  g+y+x "
                      f"{res[f'{pair}/{ax}/model_g+y+x_rms']:.3f}/"
                      f"{res[f'{pair}/{ax}/model_g+y+x_max']:.3f}")
        for pair in ("Y-C", "M-C"):
            for n in N_DUST:
                if f"{pair}/dust_n{n}/maxerr_med" in res:
                    print(f" {pair} dust n={n:4d} (used {res[f'{pair}/dust_n{n}/n_used']}): "
                          f"maxerr med {res[f'{pair}/dust_n{n}/maxerr_med']:.3f} "
                          f"p90 {res[f'{pair}/dust_n{n}/maxerr_p90']:.3f} "
                          f"rms med {res[f'{pair}/dust_n{n}/rms_med']:.3f} dots")


if __name__ == "__main__":
    main(sys.argv[1:])
