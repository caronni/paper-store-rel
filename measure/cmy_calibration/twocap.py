"""R11 — R-2 (two captures of one print, summed) and the Gaussian synthetic S1 (C6) with its exact Bayes LLRs.

What: (1) R-2 on a pair of band-captures of the SAME printed cells (U12 at 2400 + 4800, U13 likewise), paired by
(window id, cell index): one shared furniture draw and fold assignment (seeded by the first capture's id), per
capture its own QDA and maps (P-a, P-b), then per chain the modes SUMMED (the three bounded scores summed, no
post-sum clamp, then demapped), SUM-OF-FORMS (the per-capture form LLRs summed; six-maps' only summed mode),
BEST-SINGLE (the capture with the higher page I_lo for that chain) and RECAL-ORACLE (per form a state-balanced
PAVA on the summed bounded raw statistic over both captures' map populations: the rejected attempt-time locus,
reference only); C4 = the conditional forms of every 3-score chain identical between SUMMED and SUM-OF-FORMS;
(2) S1: features drawn per state from N(mu_s, Sigma_s) (B3's pooled per-state mean and covariance of F), labels
uniform, in 7 x 47 pseudo-windows of 46 x 46 cells; S1b = the same labels with an independent noise draw; the
Bayes LLRs are the exact Gaussian log-density ratios.
Why: the protocol's R-2 and C6.  How: the regimes module's furniture, fold and trial machinery; seeds REGIME 11
(two-capture LDPC trials) and REGIME 8 (S1 draws).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from measure.cmy_calibration.chains import MAP_SPECS, bound_triple, demap, fit_stratified_pava
from measure.cmy_calibration.config import MASTER_SEED, REGIME, RUNGS, Params
from measure.cmy_calibration.estimators import ROWS, WindowBootstrap, est, row_cells, logistic_slope, ece
from measure.cmy_calibration.fit import Band, apply_context, build_band, draw_furniture, fit_context
from measure.cmy_calibration.ldpc_sim import Outcomes, run_trials
from measure.cmy_calibration.regimes import (PageFit, arm_key, fold_contexts, page_ldpc_rows, page_trials,
                                             rng_for)

TWO_CHAINS = (("fallback", "-"), ("lo-first", "w"), ("hi-first", "w"), ("six-maps", "w"))
MODES2 = ("SUMMED", "SUM-OF-FORMS", "BEST-SINGLE")
FORM_STREAM = {"hi": ("hi", "bicm"), "lo": ("lo", "bicm"), "hi|lo=0": ("hi", "cond"), "hi|lo=1": ("hi", "cond"),
               "lo|hi=0": ("lo", "cond"), "lo|hi=1": ("lo", "cond"), "hi|lo": ("hi", "cond"),
               "lo|hi": ("lo", "cond")}


def bad_ids(arrays: dict[str, np.ndarray], meta: dict[str, Any], band: str) -> set[str]:
    bi = meta["band_names"].index(band)
    wins = np.unique(arrays["win"][arrays["band"] == bi])
    return {str(arrays["w_id"][w]) for w in wins if not arrays["w_reg_ok"][w] or arrays["w_reg_edge"][w]}


def all_ids(arrays: dict[str, np.ndarray], meta: dict[str, Any], band: str) -> set[str]:
    bi = meta["band_names"].index(band)
    return {str(arrays["w_id"][w]) for w in np.unique(arrays["win"][arrays["band"] == bi])}


def aligned_pair(c1: tuple[dict[str, np.ndarray], dict[str, Any]], c2: tuple[dict[str, np.ndarray], dict[str, Any]],
                 band: str, bc1: int, bc2: int) -> tuple[Band, Band]:
    """Both captures' bands restricted to windows good in BOTH; cells checked aligned (ids, states)."""
    (a1, m1), (a2, m2) = c1, c2
    ids1, ids2 = all_ids(a1, m1, band), all_ids(a2, m2, band)
    drop = frozenset(bad_ids(a1, m1, band) | bad_ids(a2, m2, band) | (ids1 ^ ids2))
    b1 = build_band(a1, m1, band, bc1, drop)
    b2 = build_band(a2, m2, band, bc2, drop)
    if list(b1.win_ids) != list(b2.win_ids) or not np.array_equal(b1.state, b2.state) \
            or len(b1.regions) != len(b2.regions):
        raise SystemExit(f"{band}: the two captures do not align cell by cell")
    return b1, b2


def recal_forms(r1h: np.ndarray, r2h: np.ndarray, st_h: np.ndarray, r1: np.ndarray, r2: np.ndarray) -> np.ndarray:
    """RECAL-ORACLE: per form a state-balanced PAVA on the summed bounded raw statistic of the map population."""
    fh = demap(bound_triple(r1h)[0] + bound_triple(r2h)[0])
    fe = demap(bound_triple(r1)[0] + bound_triple(r2)[0])
    out = np.zeros_like(fe)
    for k, spec in enumerate(MAP_SPECS):
        member = np.isin(st_h, spec.states)
        pm = fit_stratified_pava(fh[member, k], np.isin(st_h, spec.pos)[member].astype(np.uint8), st_h[member])
        out[:, k] = 0.0 if pm is None else pm.llrs(fe[:, k])
    return out


def capture_outputs(band: Band, X: np.ndarray, fur: Any, k: int, params: Params, seed_bc: int
                    ) -> dict[str, Any]:
    """Per population: payload raw r, map-side (r, states), per chain (forms, stored)."""
    arms = [(c, w, "D1-DEFAULT") for c, w in TWO_CHAINS]
    ctx = fit_context(X[fur.search], band.state[fur.search], X[fur.held], band.state[fur.held], fur.held_kind,
                      np.zeros(fur.held.size, bool), ("D1-DEFAULT",), ("w",))
    r, outs = apply_context(ctx, X[fur.payload], arms)
    res: dict[str, Any] = {"P-a": {"r": r, "rh": [(ctx.r_held, ctx.held_state, None)],
                                   "out": {a[0]: (o.forms, o.stored) for a, o in outs.items()}}}
    n = fur.payload.size
    pb: dict[str, Any] = {"r": np.zeros((n, 3)), "rh": [], "out": {c: (np.zeros((n, 6)),
                                                                        np.zeros((n, 6 if c == "six-maps" else 3)))
                                                                    for c, _ in TWO_CHAINS}}
    for pos, fctx in fold_contexts(band, X, band.state, fur, k, params.K, params.workers, ("w",), seed_bc):
        rf, o2 = apply_context(fctx, X[fur.payload[pos]], arms)
        if rf is not None:
            pb["r"][pos] = rf
        pb["rh"].append((fctx.r_held, fctx.held_state, pos))
        for a, o in o2.items():
            pb["out"][a[0]][0][pos] = o.forms
            pb["out"][a[0]][1][pos] = o.stored
    res["P-b"] = pb
    return res


def i_lo(boot: WindowBootstrap, forms: np.ndarray, st: np.ndarray, grp: np.ndarray) -> float:
    return float(boot.info(forms, st, grp)[0][1])


def run_twocap(b1: Band, b2: Band, params: Params, *, T: int | None = None, rungs: tuple[str, ...] = RUNGS,
               ldpc: bool = True, log: Any = print, label: str = "") -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    fits: list[PageFit] = []
    c4 = 0.0
    for k in range(params.R):
        fur = draw_furniture(rng_for("page_furniture", b1.bc, 0, k), b1, list(range(b1.n_regions)))
        caps = [capture_outputs(b, b.X["F"], fur, k, params, b1.bc) for b in (b1, b2)]
        st, grp = b1.state[fur.payload], b1.win[fur.payload]
        boot = WindowBootstrap(len(b1.win_ids), params.B, rng_for("bootstrap", b1.bc, 2, k))
        forms: dict[str, np.ndarray] = {}
        for pop in ("P-a", "P-b"):
            o1, o2 = caps[0][pop]["out"], caps[1][pop]["out"]
            for chain, _ in TWO_CHAINS:
                f1, s1 = o1[chain]
                f2, s2 = o2[chain]
                sof = f1 + f2
                forms[arm_key(pop, chain, "SUM-OF-FORMS", "-")] = sof
                if chain != "six-maps":
                    summed = demap(s1 + s2)
                    forms[arm_key(pop, chain, "SUMMED", "-")] = summed
                    c4 = max(c4, float(np.abs(summed[:, 2:] - sof[:, 2:]).max()))
                best = f1 if i_lo(boot, f1, st, grp) >= i_lo(boot, f2, st, grp) else f2
                forms[arm_key(pop, chain, "BEST-SINGLE", "-")] = best
            if pop == "P-a":
                (rh1, sth, _), (rh2, _, _) = caps[0][pop]["rh"][0], caps[1][pop]["rh"][0]
                forms[arm_key(pop, "recal", "RECAL-ORACLE", "-")] = recal_forms(rh1, rh2, sth, caps[0][pop]["r"],
                                                                                caps[1][pop]["r"])
            else:
                rec = np.zeros((fur.payload.size, 6))
                for (rh1, sth, pos), (rh2, _, _) in zip(caps[0][pop]["rh"], caps[1][pop]["rh"]):
                    if rh1 is not None and rh2 is not None:
                        rec[pos] = recal_forms(rh1, rh2, sth, caps[0][pop]["r"][pos], caps[1][pop]["r"][pos])
                forms[arm_key(pop, "recal", "RECAL-ORACLE", "-")] = rec
        for key, f in forms.items():
            pop, chain, mode, _ = key.split("|")
            point, bI = boot.info(f, st, grp)
            ref = forms.get(arm_key(pop, chain, "SUM-OF-FORMS", "-"))
            dpt, dbt = (boot.info(ref, st, grp) if ref is not None else (None, None))
            for i, row in enumerate(ROWS):
                L, b, w = row_cells(f, st, i)
                rows.append({"band": label or b1.name, "bc": [b1.bc, b2.bc], "replicate": k, "population": pop,
                             "chain": chain, "form": row, "mode": mode, "I": est(point[i], bI[:, i]),
                             "dI_vs_sum_of_forms": (est(point[i] - dpt[i], bI[:, i] - dbt[:, i])
                                                    if dpt is not None else None),
                             "slope": logistic_slope(L, b, w)[0], "ece": ece(L, b, w), "loses": None,
                             "n_cells": int(st.size)})
        fits.append(PageFit(fur.payload, fur.payload_region, forms, {}, {}, {}, {}, None))
        log(f"  twocap {label or b1.name} replicate {k}: C4 max |SUMMED - SUM-OF-FORMS| on conditionals {c4:.3g}")
    out: dict[str, Any] = {"twocapture": rows, "C4_max_abs": c4, "ldpc": [], "yield": [], "outcomes": None}
    if ldpc:
        T = params.T_page if T is None else T
        outs = Outcomes()
        trials = page_trials(b1, fits, T, rungs, regime="twocapture", n_key=2)
        for trial, res in run_trials(trials, params.workers, max_iters=params.max_iters,
                                     retry_iters=params.retry_iters, alpha=params.alpha, retry=params.retry150):
            outs.add(trial, res)
        outs = outs.frozen()

        def fields_of(arm: str) -> dict[str, Any]:
            pop, chain, mode, _ = arm.split("|")
            return {"regime": "twocapture", "n": None, "features": "F", "population": pop, "chain": chain,
                    "weighting": "-" if chain in ("fallback", "recal") else "w", "policy": "D1-DEFAULT", "gate": None, "capmode": mode, "band": label or b1.name}
        got = page_ldpc_rows(outs, {"bc": b1.bc}, rungs, fields_of)
        out["ldpc"], out["yield"], out["outcomes"] = got["ldpc"], got["yield"], outs
        mark_losses(out["twocapture"], out["ldpc"])
    return out


def mark_losses(rows: list[dict[str, Any]], ldrows: list[dict[str, Any]]) -> None:
    """loses = I(SUMMED) < I(SUM-OF-FORMS) with the paired CI excluding 0 (replicate 0, P-a), or the SUMMED
    page-final LDPC success lower than SUM-OF-FORMS' with disjoint Wilson intervals at some rung."""
    lk = {(r["chain"], r["capmode"], r["stream"], r["mode"], r["rung"]): r for r in ldrows
          if r.get("population") == "final" and r["mode"] in ("bicm", "cond")}
    for row in rows:
        if row["mode"] != "SUMMED":
            continue
        d = row["dI_vs_sum_of_forms"]
        info_loses = d is not None and row["replicate"] == 0 and row["population"] == "P-a" and d["hi"] < 0
        st, mode = FORM_STREAM[row["form"]]
        ld_loses = False
        for r in RUNGS:
            a = lk.get((row["chain"], "SUMMED", st, mode, r))
            b = lk.get((row["chain"], "SUM-OF-FORMS", st, mode, r))
            if a and b and a["wilson"]["hi"] < b["wilson"]["lo"]:
                ld_loses = True
        row["loses"] = bool(info_loses or ld_loses)


# ---------------------------------------------------------------- S1, the Gaussian synthetic

def pooled_gaussians(band: Band, feats: str = "F") -> tuple[np.ndarray, np.ndarray]:
    X = band.X[feats]
    mu = np.stack([X[band.state == s].mean(0) for s in range(4)])
    cov = np.stack([np.cov(X[band.state == s].T) for s in range(4)])
    return mu, cov


def synth_arrays(mu: np.ndarray, cov: np.ndarray, labels: np.ndarray, noise_rng: np.random.Generator,
                 rows: int = 7, cols: int = 47, cells: int = 46) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """An extract-shaped npz for a pseudo band: rows x cols windows of cells x cells, features ~ N(mu_y, cov_y)."""
    n_w = rows * cols
    per = cells * cells
    chol = np.linalg.cholesky(cov)
    z = noise_rng.standard_normal((labels.size, 3))
    X = mu[labels] + np.einsum("nij,nj->ni", chol[labels], z)
    rr, cc = np.divmod(np.arange(per), cells)
    gr, gc = np.divmod(np.arange(n_w), cols)
    arrays = {"band": np.zeros(labels.size, np.uint8), "win": np.repeat(np.arange(n_w), per).astype(np.int32),
              "r": np.tile(rr, n_w).astype(np.uint8), "c": np.tile(cc, n_w).astype(np.uint8),
              "x_pp": X.astype(np.float64), "x_1": X.astype(np.float64), "y": labels.astype(np.uint8),
              "w_id": np.array([f"S1-w{r:02d}-{c:02d}" for r, c in zip(gr, gc)]), "w_grid_row": gr,
              "w_grid_col": gc, "w_reg_ok": np.ones(n_w, bool), "w_reg_edge": np.zeros(n_w, bool)}
    meta = {"band_names": ["S1"], "bands": {"S1": {"cell_dots": 2}}, "capture": "synthetic"}
    return arrays, meta


def synth_pair(mu: np.ndarray, cov: np.ndarray, bc1: int, bc2: int, rows: int = 7, cols: int = 47
               ) -> tuple[Band, Band]:
    n = rows * cols * 46 * 46
    labels = np.random.default_rng([MASTER_SEED, REGIME["synth_s1"], bc1, 0, 0]).integers(0, 4, n)
    out = []
    for bc in (bc1, bc2):
        arrays, meta = synth_arrays(mu, cov, labels, np.random.default_rng([MASTER_SEED, REGIME["synth_s1"], bc, 0, 1]),
                                    rows, cols)
        out.append(build_band(arrays, meta, "S1", bc))
    return out[0], out[1]


def bayes_scores(X: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Exact (sC, sM, sY) = log N(x; mu_X, Sigma_X) - log N(x; mu_W, Sigma_W)."""
    q = np.empty((X.shape[0], 4))
    for s in range(4):
        L = np.linalg.cholesky(cov[s])
        z = np.linalg.solve(L, (X - mu[s]).T)
        q[:, s] = -0.5 * (z * z).sum(0) - np.log(np.diag(L)).sum()
    return q[:, 1:] - q[:, :1]
