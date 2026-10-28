"""probe17 P3-dust-label-sufficiency — stage 2: the density sweep.

Question: how many keystream-known labeled cells ('training dust') does the
8-class full-covariance QDA need before it matches full cross-tile training?

Protocol (measured on real scans, features from probe17_dust_features.py):
  pool   = all 16 e004 A3 tiles' cells (16 x 38,940 = 623,040 c3 cells,
           position-balanced 8x8 across the page)
  dust   = N labeled cells, N = density x pool_cells, placed either
           'uniform' (uniform random over the pool) or 'periodic' (the real
           dust pattern: the SAME m = N/16 in-tile cell positions repeated
           in every tile)
  train  = full-cov QDA (uniform priors), feature sets rgb (C/M/Y plane
           densities) and rgb+grey (union-aligned luma density 4th feature)
  eval   = symbol accuracy + plug-in MI b/cell on ALL pool cells not used
           for training
  ceiling= 16-fold cross-tile QDA (the published 004.0 footing; rgb must
           reproduce home 1.896 / office 2.150 b/cell or the run is invalid)

Repeats per condition: N_SEEDS draws; report mean / min / max. Degenerate
draws (any class with < n_features+2 samples) are redrawn (counted).

Usage:
  env/bin/python scratch/probe17_dust_sweep.py \
      scratch/probe17_feats_home.npz scratch/probe17_feats_xerox.npz
Writes scratch/probe17_dust_report.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path("<repo>")
sys.path.insert(0, str(REPO / "experiments" / "004-finalists-checkerboard"))
sys.path.insert(0, str(REPO / "experiments" / "002-calibration-page"))

from analyze_e004 import GaussianQDA  # noqa: E402  (the 004.0 classifier)
import cal_color as ccol  # noqa: E402  (_confusion, _mi_bits_from_counts)

N_STATES = 7
N_SEEDS = 12
DENSITIES = [0.0001, 0.00025, 0.0005, 0.001,
             0.0025, 0.005, 0.0075, 0.01, 0.02]  # fraction of pool cells
REQUESTED = {0.0025, 0.005, 0.0075, 0.01, 0.02}   # the probe's ladder
PAGE_CELLS_C3 = 2220 * 1500  # e011 archive A4 c3 field, for the caveat math
BAR_BCELL = 0.03


def load_feats(path: str) -> dict:
    z = np.load(path, allow_pickle=False)
    tiles = [str(t) for t in z["tile_names"]]
    out = {"scan": str(z["scan_name"]), "sha": str(z["scan_sha256"]),
           "tiles": []}
    for k in tiles:
        X3 = z[f"X3_{k}"].astype(np.float64)
        g = z[f"g_{k}"].astype(np.float64)[:, None]
        out["tiles"].append({
            "name": k,
            "X": np.concatenate([X3, g], axis=1),  # cols: C,M,Y,grey
            "y": z[f"y_{k}"].astype(np.int64),
            "shape": tuple(int(v) for v in z[f"shape_{k}"]),
        })
    return out


def score(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    conf = ccol._confusion(y_true, y_pred, N_STATES).astype(np.float64)
    return (float(np.trace(conf) / conf.sum()),
            float(ccol._mi_bits_from_counts(conf)))


def cross_tile_ceiling(tiles: list[dict], cols: slice) -> dict:
    conf = np.zeros((N_STATES, N_STATES), np.int64)
    for hold in range(len(tiles)):
        Xtr = np.concatenate([t["X"][:, cols] for i, t in enumerate(tiles)
                              if i != hold])
        ytr = np.concatenate([t["y"] for i, t in enumerate(tiles)
                              if i != hold])
        q = GaussianQDA().fit(Xtr, ytr, N_STATES)
        pred = q.predict(tiles[hold]["X"][:, cols])
        conf += ccol._confusion(tiles[hold]["y"], pred, N_STATES)
    conf = conf.astype(np.float64)
    return {"accuracy": float(np.trace(conf) / conf.sum()),
            "mi_bits": float(ccol._mi_bits_from_counts(conf))}


def dust_condition(X: np.ndarray, y: np.ndarray, n_tile_cells: int,
                   n_tiles: int, density: float, placement: str,
                   cols: slice, rng: np.random.Generator) -> dict:
    pool = X.shape[0]
    n_feat = X[:, cols].shape[1]
    accs, mis, ns, redraws = [], [], [], 0
    for _ in range(N_SEEDS):
        for _attempt in range(60):
            if placement == "uniform":
                n = max(int(round(density * pool)), N_STATES * (n_feat + 2))
                idx = rng.choice(pool, size=n, replace=False)
            else:  # periodic: same in-tile positions in every tile
                m = max(int(round(density * pool / n_tiles)), 4)
                pos = rng.choice(n_tile_cells, size=m, replace=False)
                idx = (np.arange(n_tiles)[:, None] * n_tile_cells
                       + pos[None, :]).ravel()
            cnt = np.bincount(y[idx], minlength=N_STATES)
            if cnt.min() >= n_feat + 2:
                break
            redraws += 1
        else:
            continue  # unfit draw after 60 tries: skip this seed
        mask = np.ones(pool, bool)
        mask[idx] = False
        q = GaussianQDA().fit(X[idx][:, cols], y[idx], N_STATES)
        pred = q.predict(X[mask][:, cols])
        a, m_ = score(y[mask], pred)
        accs.append(a)
        mis.append(m_)
        ns.append(len(idx))
    return {"n_labels_mean": float(np.mean(ns)), "n_seeds_ok": len(mis),
            "redraws": redraws,
            "acc_mean": float(np.mean(accs)), "acc_min": float(np.min(accs)),
            "mi_mean": float(np.mean(mis)), "mi_min": float(np.min(mis)),
            "mi_max": float(np.max(mis))}


def run_engine(path: str, label: str) -> dict:
    d = load_feats(path)
    tiles = d["tiles"]
    n_tile_cells = tiles[0]["y"].size
    assert all(t["y"].size == n_tile_cells for t in tiles)
    X = np.concatenate([t["X"] for t in tiles])
    y = np.concatenate([t["y"] for t in tiles])
    pool = X.shape[0]
    print(f"\n=== {label}: {d['scan']} (sha {d['sha'][:12]}) — "
          f"pool {pool} cells ===", flush=True)

    featsets = {"rgb": slice(0, 3), "rgb+grey": slice(0, 4)}
    rep: dict = {"scan": d["scan"], "sha256": d["sha"], "pool_cells": pool,
                 "n_tiles": len(tiles), "ceilings": {}, "sweep": {}}
    for fname, cols in featsets.items():
        c = cross_tile_ceiling(tiles, cols)
        rep["ceilings"][fname] = c
        print(f"ceiling cross-tile [{fname}]: acc {c['accuracy']:.4f} "
              f"MI {c['mi_bits']:.4f} b/cell", flush=True)

    rng = np.random.default_rng(np.random.SeedSequence(
        [17] + list(label.encode())))  # stable (str hash is salted)
    for fname, cols in featsets.items():
        ceil = rep["ceilings"][fname]["mi_bits"]
        for placement in ("uniform", "periodic"):
            for dens in DENSITIES:
                r = dust_condition(X, y, n_tile_cells, len(tiles), dens,
                                   placement, cols, rng)
                r["density_pct"] = dens * 100
                r["delta_mi_mean"] = ceil - r["mi_mean"]
                r["delta_mi_worst"] = ceil - r["mi_min"]
                rep["sweep"][f"{fname}|{placement}|{dens}"] = r
                flag = ("PASS" if r["delta_mi_mean"] <= BAR_BCELL else "    ")
                req = "*" if dens in REQUESTED else " "
                print(f"[{fname:8s}|{placement:8s}] {dens*100:5.3f}%{req} "
                      f"N~{r['n_labels_mean']:7.0f}  "
                      f"acc {r['acc_mean']:.4f} (min {r['acc_min']:.4f})  "
                      f"MI {r['mi_mean']:.4f} (min {r['mi_min']:.4f})  "
                      f"dMI mean {r['delta_mi_mean']:+.4f} "
                      f"worst {r['delta_mi_worst']:+.4f}  {flag}"
                      + (f" redraws={r['redraws']}" if r["redraws"] else ""),
                      flush=True)
    return rep


def main(paths: list[str]) -> None:
    t0 = time.time()
    labels = ["home-M281", "office-AltaLink"][: len(paths)]
    report = {"probe": "P3-dust-label-sufficiency", "n_states": N_STATES,
              "n_seeds": N_SEEDS, "bar_b_cell": BAR_BCELL,
              "page_cells_c3_a4": PAGE_CELLS_C3, "engines": {}}
    for p, lab in zip(paths, labels):
        report["engines"][lab] = run_engine(p, lab)
    report["runtime_s"] = round(time.time() - t0, 1)
    out = REPO / "scratch" / "probe17_dust_report.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"\nwrote {out} ({report['runtime_s']}s)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
