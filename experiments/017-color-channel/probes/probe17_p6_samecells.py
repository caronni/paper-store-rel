#!/usr/bin/env python
"""probe17_p6_samecells.py — P6 seven-vs-eight decision numbers, part B.

The measured-confusion (not MI-abstraction) version of the 7-vs-8 question:
on the SAME printed 8-state CAL-1 field (state8_c3), per-level C/M/Y
presence-bit BER

  (a) WITH the triple: 8-class CV-QDA over all cells (the 3-independent-level
      architecture — the triple occurs at ~12.5% of cells by construction);
  (b) the same detector's bits restricted to true-non-triple cells;
  (c) the triple's own cells' bits under (a);
  (d) EXCLUDED: a retrained 7-class CV-QDA on exactly the non-triple cells
      (what a true 7-state format would see on those cells);
  (e) decision-time-only exclusion: 8-class training, argmax restricted to
      the 7 non-triple classes (posterior mass of CMY reassigned).

(b) vs (d) isolates detector-crowding cost on shared cells; (c) is the
triple's own unreliability; (a) vs (d) is the full per-level price of
carrying the triple.

Machinery reused verbatim: cal_core registration/white model,
cal_color.aligned_cell_densities + _gaussian_cv_classify (deterministic
interleaved folds). Validation gate: the 8-class run must reproduce the
archived calpage_report accuracy/MI for that engine.

Run: env/bin/python experiments/017-color-channel/probes/probe17_p6_samecells.py \\
         --scan-dir <evidence>/scans --e002-build <002's build>   (~2-4 min/scan)
Writes experiments/017-color-channel/build/probe17_p6_samecells.json (the
record is the copy beside this file).
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "experiments" / "002-calibration-page"))

import cal_color as ccol  # noqa: E402
import cal_core as cc  # noqa: E402

SCAN_NAMES = {
    "home_m281": "test-scan-calpage-color.png",
    "xerox_altalink": "xerox-cal-hp-scan.png",
}
REPORT_NAMES = {
    "home_m281": "calpage_report.json",
    "xerox_altalink": "calpage_report_xerox.json",
}
SCANS: dict[str, Path] = {}    # set from --scan-dir in __main__
REPORTS: dict[str, Path] = {}  # set from --e002-build in __main__
NAMES8 = ["W", "C", "M", "CM", "Y", "CY", "MY", "CMY"]


def bit(v: np.ndarray, i: int) -> np.ndarray:
    return (v >> i) & 1


def level_ber(pred: np.ndarray, true: np.ndarray) -> dict:
    out = {p: float((bit(pred, i) != bit(true, i)).mean())
           for i, p in enumerate("CMY")}
    out["mean"] = float(np.mean([out[p] for p in "CMY"]))
    out["n"] = int(true.size)
    return out


def level_detail(pred: np.ndarray, true: np.ndarray) -> dict:
    """Per-level 2x2 structure: miss/fa + binary MI (hard-decision MLC view)."""
    out = {}
    mis = []
    for i, p in enumerate("CMY"):
        tb, pb = bit(true, i), bit(pred, i)
        conf = np.zeros((2, 2), np.float64)
        for a in (0, 1):
            for b in (0, 1):
                conf[a, b] = float(((tb == a) & (pb == b)).sum())
        miss = float(conf[1, 0] / max(conf[1].sum(), 1))
        fa = float(conf[0, 1] / max(conf[0].sum(), 1))
        mi = ccol._mi_bits_from_counts(conf)
        mis.append(mi)
        out[p] = {"miss": round(miss, 4), "fa": round(fa, 4),
                  "mi_bits": round(mi, 4)}
    out["levels_mi_sum"] = round(float(np.sum(mis)), 4)
    return out


def restricted_argmax_pred(X: np.ndarray, y: np.ndarray, n_states: int,
                           drop: int, n_folds: int = 5) -> np.ndarray:
    """8-class-trained CV-QDA, argmax over classes != drop (variant e).
    Exact line-for-line mirror of ccol._gaussian_cv_classify (deterministic
    interleaved folds, scale-aware ridge, empirical log priors) with one
    change: class `drop` is skipped at DECISION time only."""
    X = np.asarray(X, np.float64)
    n, d = X.shape
    folds = np.arange(n) % n_folds
    pred = np.full(n, -1, np.int64)
    for f in range(n_folds):
        tr = folds != f
        te = ~tr
        Xtr, ytr = X[tr], y[tr]
        n_tr = len(ytr)
        logp = np.full((int(te.sum()), n_states), -np.inf)
        Xte = X[te]
        for k in range(n_states):
            if k == drop:
                continue
            sel = ytr == k
            nk = int(sel.sum())
            if nk < d + 2:
                continue
            mu = Xtr[sel].mean(axis=0)
            C = np.atleast_2d(np.cov(Xtr[sel], rowvar=False))
            C = C + (1e-4 * float(np.trace(C)) / d + 1e-12) * np.eye(d)
            np.linalg.slogdet(C)  # parity with the original (sign unused)
            _, logdet = np.linalg.slogdet(C)
            diff = Xte - mu
            q = np.einsum("ij,ij->i", diff, np.linalg.solve(C, diff.T).T)
            logp[:, k] = -0.5 * q - 0.5 * logdet + np.log(nk / n_tr)
        pred[te] = np.argmax(logp, axis=1)
    return pred


def run_engine(eng: str) -> dict:
    t0 = time.time()
    print(f"[{eng}] loading + registering {SCANS[eng]} ...", flush=True)
    scan = cc.load_scan(SCANS[eng])
    cc.register(scan)
    wm = cc.white_model(scan)

    e = cc.entry(scan["manifest"], "state8_C")
    states = cc.load_gt_named(e["params"]["states_gt"]).astype(np.int64)

    feats, per_plane = [], {}
    for p in "CMY":
        D, summ = ccol.aligned_cell_densities(scan, f"state8_{p}", wm)
        assert D.shape == states.shape, (p, D.shape, states.shape)
        feats.append(D.ravel())
        per_plane[p] = {k: summ.get(k) for k in ("method", "channel", "ber", "null_ok")}
    X = np.stack(feats, axis=1)
    y = states.ravel()

    # ---- (a) 8-class, all cells (WITH triple) ----------------------------
    res8 = ccol._gaussian_cv_classify(X, y, 8)
    pred8 = np.asarray(res8["pred"], np.int64)

    # validation gate vs the archived report
    rep = json.load(open(REPORTS[eng]))
    s8 = rep["families"]["density_color"]["color_alphabet"]["state8"]
    d_acc = abs(res8["accuracy"] - s8["accuracy"])
    d_mi = abs(res8["mi_bits"] - s8["mi_bits"])
    gate_ok = d_acc < 1e-6 and d_mi < 1e-6
    print(f"[{eng}] reproduction gate: d_acc={d_acc:.2e} d_mi={d_mi:.2e} "
          f"{'PASS' if gate_ok else 'LOOSE (report below regardless)'}")

    nontri = y != 7
    tri = ~nontri

    # ---- (d) retrained 7-class on the non-triple cells --------------------
    res7 = ccol._gaussian_cv_classify(X[nontri], y[nontri], 7)
    pred7 = np.asarray(res7["pred"], np.int64)

    # ---- (e) 8-trained, decision restricted to 7 --------------------------
    pred_e = restricted_argmax_pred(X, y, 8, drop=7)

    out = {
        "scan": str(SCANS[eng]),
        "scan_sha256": scan["sha256"],
        "n_cells": int(y.size),
        "n_triple_true": int(tri.sum()),
        "triple_fraction": round(float(tri.mean()), 4),
        "per_plane_decode": per_plane,
        "reproduction_gate": {"d_acc": d_acc, "d_mi": d_mi, "pass": bool(gate_ok)},
        "acc8": round(float(res8["accuracy"]), 4),
        "mi8_uniform": round(float(res8["mi_bits"]), 4),
        "acc7_retrained_nontriple": round(float(res7["accuracy"]), 4),
        "mi7_retrained_uniform": round(float(res7["mi_bits"]), 4),
        "a_with_triple_all_cells": level_ber(pred8, y),
        "b_with_triple_nontriple_cells": level_ber(pred8[nontri], y[nontri]),
        "c_with_triple_triple_cells_own_bits": level_ber(pred8[tri], y[tri]),
        "d_excluded_retrained7_same_nontriple_cells": level_ber(pred7, y[nontri]),
        "e_excluded_decision_only_nontriple_cells":
            level_ber(pred_e[nontri], y[nontri]),
        "a_level_detail_all_cells": level_detail(pred8, y),
        "d_level_detail_retrained7_nontriple": level_detail(pred7, y[nontri]),
        "elapsed_s": round(time.time() - t0, 1),
    }
    del scan
    gc.collect()
    return out


def main() -> None:
    out = {}
    for eng in SCANS:
        out[eng] = run_engine(eng)
    outp = REPO / "experiments/017-color-channel/build/probe17_p6_samecells.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(outp, "w"), indent=1)
    print(json.dumps(out, indent=1))
    print(f"\nwritten: {outp}")


if __name__ == "__main__":
    _ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _ap.add_argument("--scan-dir", type=Path, required=True)
    _ap.add_argument("--e002-build", type=Path, required=True)
    _args = _ap.parse_args()
    SCANS.update({k: _args.scan_dir / v for k, v in SCAN_NAMES.items()})
    REPORTS.update({k: _args.e002_build / v for k, v in REPORT_NAMES.items()})
    main()
