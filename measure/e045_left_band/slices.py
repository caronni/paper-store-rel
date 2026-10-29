"""e045 — per-slice statistics of a cmy cell field read at some pose arm (measure/e045_left_band/cells.py).

A slice is the set of cells whose centre lies in [x0, x1) mm of page x.  Per slice:

  errors     four-state hard error with a GENIE colour table (nearest class mean, the means fitted with the
             GT labels, as the e043/e044 readouts do): `band` = one table over the whole field (the readouts'
             number), `slice` = a table per slice (what is left once the slice's own levels are known);
             per plane, per state, the W -> ink share.
  separation per plane in its own channel (C in R, M in G, Y in B), white = W cells, ink = the plane's own
             cells: means, sds, d' = (mu_W - mu_P) / sqrt((sd_W^2 + sd_P^2) / 2), the best single-threshold
             W-vs-P error (e041_mixture_readout.best_threshold_err).
  neighbours a linear model of a cell's own-channel value on its four neighbours' states (N, S, W, E x C, M,
             Y indicators; outside the field = W, paper), fitted on the W cells and on the plane's own cells
             separately: the intercepts w0 / p0 are the white and the ink with all-white neighbours, d'0 their
             separation over the pooled residual sd; per neighbour state the mean coefficient (spread into
             the cell, symmetric) and the N - S and W - E differences (the direction a misregistered plane
             pushes its ink: the registration signature).
  offsets    per plane M - C, Y - C (dy, dx printed dots) of the windows whose centre lies in the slice
             ("ok" flags), median and IQR; the count of non-ok flags.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from measure.cmy_probe.bands import PLANES_OF_CLASS, STATE_NAMES
from measure.e041_mixture_readout import best_threshold_err, class_means, classify

PLANES = ("C", "M", "Y")
DIRS = ("N", "S", "W", "E")
Rec = dict[str, Any]


def slice_edges(x_from_mm: float, x_to_mm: float, width_mm: float) -> np.ndarray:
    """Edges every width_mm from x_from_mm; a last slice narrower than half a width joins its neighbour."""
    e = list(np.arange(x_from_mm, x_to_mm, width_mm))
    if x_to_mm - e[-1] < 0.5 * width_mm and len(e) > 1:
        e.pop()
    return np.array(e + [x_to_mm])


def predict(X: np.ndarray, cls: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Genie nearest-class-mean decisions over the cells in mask (means from those cells); -1 elsewhere."""
    ok = mask & np.isfinite(X).all(-1)
    pred = np.full(cls.shape, -1, np.int64)
    Xr, yr = X[ok].astype(np.float64), cls[ok].astype(np.int64)
    if len(yr):
        mu, _ = class_means(Xr, yr, len(STATE_NAMES))
        pred[ok] = classify(Xr, yr, mu, None)
    return pred


def error_stats(cls: np.ndarray, pred: np.ndarray, mask: np.ndarray) -> Rec:
    ok = mask & (pred >= 0)
    y, p = cls[ok].astype(np.int64), pred[ok]
    n = max(len(y), 1)
    th, ph = PLANES_OF_CLASS[y], PLANES_OF_CLASS[p]
    out = {"n": int(len(y)), "err": 100.0 * float((y != p).sum()) / n}
    for i, pl in enumerate(PLANES):
        out[f"err_{pl}"] = 100.0 * float((th[:, i] != ph[:, i]).sum()) / n
    for s, nm in enumerate(STATE_NAMES):
        sel = y == s
        out[f"err_state_{nm}"] = 100.0 * float((p[sel] != s).mean()) if sel.any() else float("nan")
    wrong = y != p
    out["share_W_cells"] = 100.0 * float((wrong & (y == 0)).sum()) / max(int(wrong.sum()), 1)
    return out


def separation(X: np.ndarray, cls: np.ndarray, mask: np.ndarray) -> Rec:
    out: Rec = {}
    ok = mask & np.isfinite(X).all(-1)
    for k, pl in enumerate(PLANES):
        w, p = X[ok & (cls == 0), k].astype(np.float64), X[ok & (cls == k + 1), k].astype(np.float64)
        if len(w) < 5 or len(p) < 5:
            continue
        sd = np.sqrt(0.5 * (w.var() + p.var()))
        v = np.concatenate([w, p])
        ink = np.concatenate([np.zeros(len(w), bool), np.ones(len(p), bool)])
        out[pl] = {"mu_W": float(w.mean()), "sd_W": float(w.std()), "mu_P": float(p.mean()), "sd_P": float(p.std()),
                   "dprime": float((w.mean() - p.mean()) / sd), "best_err": 100.0 * best_threshold_err(v, ink)}
    return out


def neighbour_states(cls: np.ndarray) -> dict[str, np.ndarray]:
    """Per direction the neighbouring cell's class (outside the field = 0, W)."""
    P = np.pad(cls, 1, constant_values=0)
    return {"N": P[:-2, 1:-1], "S": P[2:, 1:-1], "W": P[1:-1, :-2], "E": P[1:-1, 2:]}


def neighbour_model(X: np.ndarray, cls: np.ndarray, mask: np.ndarray, nb: dict[str, np.ndarray]) -> Rec:
    """Per plane in its own channel: the W-cell and P-cell regressions on the 12 neighbour indicators."""
    ok = mask & np.isfinite(X).all(-1)
    out: Rec = {}
    for k, pl in enumerate(PLANES):
        fits, res = {}, []
        for tag, state in (("W", 0), ("P", k + 1)):
            sel = ok & (cls == state)
            if sel.sum() < 60:
                break
            F = np.column_stack([np.ones(int(sel.sum()))] + [(nb[d][sel] == s).astype(np.float64)
                                                             for d in DIRS for s in (1, 2, 3)])
            v = X[sel, k].astype(np.float64)
            beta, *_ = np.linalg.lstsq(F, v, rcond=None)
            r = v - F @ beta
            res.append(r)
            B = beta[1:].reshape(4, 3)                                  # rows N S W E, columns C M Y
            fits[tag] = {"b0": float(beta[0]), "sd_res": float(r.std()),
                         "spread": {PLANES[s]: float(B[:, s].mean()) for s in range(3)},
                         "N_minus_S": {PLANES[s]: float(B[0, s] - B[1, s]) for s in range(3)},
                         "W_minus_E": {PLANES[s]: float(B[2, s] - B[3, s]) for s in range(3)}}
        if len(fits) == 2:
            sd = float(np.sqrt(np.mean([r.var() for r in res])))
            out[pl] = {"w0": fits["W"]["b0"], "p0": fits["P"]["b0"], "dprime0": (fits["W"]["b0"] - fits["P"]["b0"]) / sd,
                       "W_fit": fits["W"], "P_fit": fits["P"]}
    return out


def offsets(wins: list[Rec], centres_mm: np.ndarray, x0: float, x1: float) -> Rec:
    """M - C, Y - C (dy, dx dots) over windows centred in [x0, x1) with both planes "ok"; flags not ok."""
    sel = [w for w, c in zip(wins, centres_mm) if x0 <= c < x1 and "skipped" not in w]
    out: Rec = {"windows": len(sel), "flags_not_ok": sum(1 for w in sel for f in w.get("flags", {}).values() if f != "ok")}
    for pl in ("M", "Y"):
        d = np.array([np.subtract(w["d"][pl], w["d"]["C"]) for w in sel
                      if w["flags"].get(pl) == "ok" and w["flags"].get("C") == "ok"], float).reshape(-1, 2)
        for j, ax in enumerate(("dy", "dx")):
            v = d[:, j]
            out[f"{pl}C_{ax}"] = float(np.median(v)) if len(v) else float("nan")
            out[f"{pl}C_{ax}_iqr"] = float(np.subtract(*np.percentile(v, [75, 25]))) if len(v) > 3 else float("nan")
    for pl in PLANES:
        d = np.array([w["d"][pl] for w in sel if w["flags"].get(pl) == "ok"], float).reshape(-1, 2)
        out[f"{pl}_abs_dy"] = float(np.median(d[:, 0])) if len(d) else float("nan")
        out[f"{pl}_abs_dx"] = float(np.median(d[:, 1])) if len(d) else float("nan")
    return out
