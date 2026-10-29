"""R11 — the controls and nulls, run before any decision is read (C1 anchors, C2 fold identity, C3 weighted PAVA,
C4 linearity, C5 label-shuffle null, C6 Gaussian S1, C8 soft vs hard, C9 collapse alarms; C7 lives in run.py).

What: C1 reproduces each band's committed leave-one-out nearest-mean confusion (e041_mixture_readout.class_means /
classify on x_pp, the window's own means) and the per-bit errors and information figures derived from it
(I(hi) = I(hi_true; predicted state), I(hi|lo) = sum_v P(lo = v) I(hi; predicted | lo = v), MI, BICM =
I(hi) + I(lo)); C2 checks the fold identities numerically on 10^6 triples (|a|, |b|, |c| <= 30, max error
<= 1e-9) and at 50 significant digits with the decimal module on 200 triples (sympy is not installed: this
replaces the symbolic simplification) and on real fitted maps (demap(fold(maps)) == maps to 1e-9 before the
bound); C3 pins the stratified PAVA to fit_component_pava (class-balanced strata: nodes identical, max |diff|
<= 1e-12, in practice 0) and checks that state-balanced weights recover the payload-prior map from a C-heavy
(C:M = 50:20) synthetic population.
Why: the protocol's stop rule — a failing control stops the run with decisions null.
How: pure functions returning {..., "pass": bool}.
"""
from __future__ import annotations

import decimal
from typing import Any

import numpy as np

from holo.receiver.plugins.color_model import fit_component_pava
from measure.cmy_calibration.chains import CHAIN_MAPS, HI, LO, demap, fit_stratified_pava, fold, raw_scores
from measure.cmy_calibration.config import ANCHORS, C3_MIN_I
from measure.e041_mixture_readout import class_means, classify


# ---------------------------------------------------------------- C1

def mi_bits(J: np.ndarray) -> float:
    J = J / J.sum()
    a, b = J.sum(1, keepdims=True), J.sum(0, keepdims=True)
    m = J > 0
    return float((J[m] * np.log2(J[m] / (a @ b)[m])).sum())


def confusion_stats(conf: np.ndarray) -> dict[str, float]:
    """Per-bit hard errors (%) and the information figures of a 4 x 4 (true x predicted, W C M Y) confusion."""
    P = np.asarray(conf, np.float64)
    P = P / P.sum()

    def bit_given_pred(bits: np.ndarray, rows: list[int], sub: np.ndarray) -> np.ndarray:
        J = np.zeros((2, 4))
        for k, i in enumerate(rows):
            J[bits[i]] += sub[k]
        return J

    out = {"err_hi": 100 * float(sum(P[i, j] for i in range(4) for j in range(4) if HI[i] != HI[j])),
           "err_lo": 100 * float(sum(P[i, j] for i in range(4) for j in range(4) if LO[i] != LO[j])),
           "I_hi": mi_bits(bit_given_pred(HI, list(range(4)), P)),
           "I_lo": mi_bits(bit_given_pred(LO, list(range(4)), P)), "MI": mi_bits(P)}
    for name, bits, cond in (("I_hi_lo", HI, LO), ("I_lo_hi", LO, HI)):
        tot = 0.0
        for v in (0, 1):
            rows = [i for i in range(4) if cond[i] == v]
            sub = P[rows]
            tot += float(sub.sum()) * mi_bits(bit_given_pred(bits, rows, sub / sub.sum()))
        out[name] = tot
    out["BICM"] = out["I_hi"] + out["I_lo"]
    return out


def loo_confusion(X: np.ndarray, y: np.ndarray, win: np.ndarray) -> np.ndarray:
    """Pooled confusion of the per-window leave-one-out nearest-mean classifier (the readout's 'loo')."""
    conf = np.zeros((4, 4), np.int64)
    order = np.argsort(win, kind="stable")
    bounds = np.flatnonzero(np.diff(win[order])) + 1
    for idx in np.split(order, bounds):
        Xw, yw = X[idx].astype(np.float64), y[idx].astype(np.int64)
        mu, n = class_means(Xw, yw, 4)
        np.add.at(conf, (yw, classify(Xw, yw, mu, n)), 1)
    return conf


def c1_anchor(arrays: dict[str, np.ndarray], meta: dict[str, Any], band: str, committed: list[list[int]],
              bc: int, role: str) -> dict[str, Any]:
    bi = meta["band_names"].index(band)
    sel = arrays["band"] == bi
    conf = loo_confusion(arrays["x_pp"][sel], arrays["y"][sel], arrays["win"][sel])
    com = np.asarray(committed, np.int64)
    got, want = confusion_stats(conf), confusion_stats(com)
    ok = all(abs(got[k] - want[k]) <= 0.3 for k in ("err_hi", "err_lo")) and \
        all(abs(got[k] - want[k]) <= 0.005 for k in ("I_hi", "I_lo", "I_hi_lo", "I_lo_hi", "MI"))
    if role == "control":
        ok = ok and all(got[k] >= C3_MIN_I for k in ("I_hi", "I_lo", "I_hi_lo", "I_lo_hi"))
    return {"bc": bc, "band": band, "confusion_committed": com.tolist(), "confusion_reproduced": conf.tolist(),
            "max_abs_diff": int(np.abs(conf - com).max()), **{k: got[k] for k in got},
            "committed_stats": want, "protocol_anchor": ANCHORS.get(bc), "n_cells": int(sel.sum()), "pass": bool(ok)}


# ---------------------------------------------------------------- C2

def _dec_fold(a: decimal.Decimal, b: decimal.Decimal, c: decimal.Decimal, chain: str
              ) -> tuple[decimal.Decimal, ...]:
    one = decimal.Decimal(1)

    def sig(x: decimal.Decimal) -> decimal.Decimal:
        return one / (one + (-x).exp())
    lead = a - (one - sig(b)).ln()
    s_big, s_small = lead + sig(c).ln(), lead + (one - sig(c)).ln()
    sC, sM, sY = (s_big, b, s_small) if chain == "lo-first" else (s_big, s_small, b)

    def lse(x: decimal.Decimal, y: decimal.Decimal) -> decimal.Decimal:
        return (x.exp() + y.exp()).ln()
    zero = decimal.Decimal(0)
    return (lse(sC, sM) - lse(zero, sY), lse(sC, sY) - lse(zero, sM), sM, sC - sY, sY, sC - sM)


def c2_selfcheck(n_numeric: int = 1_000_000, n_decimal: int = 200, seed: int = 20261010) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {}
    ok = True
    for chain in ("lo-first", "hi-first"):
        a, b, c = (rng.uniform(-30, 30, n_numeric) for _ in range(3))
        f = demap(fold(chain, a, b, c))
        idx = CHAIN_MAPS[chain]
        err = max(float(np.abs(f[:, idx[0]] - a).max()), float(np.abs(f[:, idx[1]] - b).max()),
                  float(np.abs(f[:, idx[2]] - c).max()))
        decimal.getcontext().prec = 60
        derr = decimal.Decimal(0)
        for _ in range(n_decimal):
            ta, tb, tc = (decimal.Decimal(repr(float(v))) for v in rng.uniform(-30, 30, 3))
            g = _dec_fold(ta, tb, tc, chain)
            derr = max(derr, abs(g[idx[0]] - ta), abs(g[idx[1]] - tb), abs(g[idx[2]] - tc))
        out[chain] = {"numeric_max_err": err, "n_numeric": n_numeric, "decimal_max_err": float(derr),
                      "n_decimal": n_decimal, "decimal_digits": 60}
        ok &= err <= 1e-9 and derr <= decimal.Decimal("1e-40")
    out["pass"] = bool(ok)
    return out


def c2_real(ctx: Any, X: np.ndarray, policy: str = "D1-DEFAULT") -> dict[str, Any]:
    """On real fitted maps: demap(fold(pieces)) reproduces each chain's three pieces (before the bound)."""
    if ctx.refused is not None:
        return {"pass": True, "skipped": ctx.refused}
    r = raw_scores(ctx.model, X)
    stat = demap(r)
    worst = 0.0
    for chain in ("lo-first", "hi-first"):
        idx = CHAIN_MAPS[chain]
        pieces = []
        for k in idx:
            pm = ctx.pieces[(policy, "w")][k]
            pieces.append(stat[:, k] if pm is None else pm.llrs(stat[:, k]))
        f = demap(fold(chain, *pieces))
        worst = max(worst, *(float(np.abs(f[:, k] - p).max()) for k, p in zip(idx, pieces)))
    return {"max_err": worst, "n_cells": int(X.shape[0]), "pass": bool(worst <= 1e-9)}


# ---------------------------------------------------------------- C3

def c3_pava(seed: int = 20261010, n_random: int = 300) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    worst = 0.0
    exact = True
    for _ in range(n_random):
        n = int(rng.integers(4, 600))
        s = np.round(rng.normal(0, 3, n), int(rng.integers(0, 3)))
        lab = (rng.random(n) < rng.uniform(0.1, 0.9)).astype(np.int64)
        if lab.min() == lab.max():
            continue
        a, b = fit_component_pava(s, lab), fit_stratified_pava(s, lab, lab)
        if a.score_nodes.shape != b.score_nodes.shape:
            exact, worst = False, float("inf")
            continue
        exact &= bool(np.array_equal(a.score_nodes, b.score_nodes)
                      and np.array_equal(a.probability_nodes, b.probability_nodes))
        worst = max(worst, float(np.abs(a.score_nodes - b.score_nodes).max()),
                    float(np.abs(a.probability_nodes - b.probability_nodes).max()))
    # conditional maps: state strata (one state per class) == label strata
    s = rng.normal(0, 3, 500)
    st = rng.choice([0, 2], 500)
    lab = (st == 2).astype(np.int64)
    a, b = fit_component_pava(s, lab), fit_stratified_pava(s, lab, st)
    cond_same = bool(np.array_equal(a.score_nodes, b.score_nodes)
                     and np.array_equal(a.probability_nodes, b.probability_nodes))
    # payload-prior recovery on the hi marginal: class 1 = {C, M}, class 0 = {W, Y}
    centres = {0: -6.0, 3: -2.5, 2: 1.5, 1: 6.0}

    def sample(counts: dict[int, int]) -> tuple[np.ndarray, np.ndarray]:
        st_ = np.concatenate([np.full(c, s_) for s_, c in counts.items()])
        return centres_arr(st_) + rng.normal(0, 2.0, st_.size), st_

    def centres_arr(st_: np.ndarray) -> np.ndarray:
        return np.vectorize(centres.get)(st_).astype(np.float64)

    ref_s, ref_st = sample({0: 60000, 1: 60000, 2: 60000, 3: 60000})
    ref = fit_stratified_pava(ref_s, HI[ref_st], ref_st)
    tilt_s, tilt_st = sample({0: 25000, 1: 50000, 2: 20000, 3: 25000})
    w_map = fit_stratified_pava(tilt_s, HI[tilt_st], tilt_st)
    cb_map = fit_component_pava(tilt_s, HI[tilt_st])
    grid = np.linspace(-8, 8, 321)

    def prob(m: Any) -> np.ndarray:
        return np.interp(grid, m.score_nodes, m.probability_nodes)
    dw = float(np.abs(prob(w_map) - prob(ref)).mean())
    dcb = float(np.abs(prob(cb_map) - prob(ref)).mean())
    recover = dw <= 0.01 and dw < dcb / 3.0
    return {"class_balanced_exact": exact, "class_balanced_max_abs": worst, "n_random": n_random,
            "conditional_identical": cond_same, "payload_prior_mean_dp_weighted": dw,
            "payload_prior_mean_dp_class_balanced": dcb, "recover_rule": "mean |dp| on [-8, 8] <= 0.01 and < cb/3",
            "pass": bool(exact and worst <= 1e-12 and cond_same and recover)}


# ---------------------------------------------------------------- C5 / C6 / C8 / C9 readers

CAL_CHAINS = ("lo-first", "hi-first", "six-maps")


def c5_check(page_rows: list[dict[str, Any]], cold_rows: list[dict[str, Any]], ldpc_rows: list[dict[str, Any]]
             ) -> dict[str, Any]:
    bad: list[str] = []
    fb: list[dict[str, Any]] = []
    for r in page_rows:
        if r["chain"] in CAL_CHAINS and r["weighting"] == "w" and not (-0.02 <= r["I"]["est"] <= 0.01):
            bad.append(f"page bc{r['bc']} {r['chain']} {r['form']} I {r['I']['est']:.4f}")
        if r["chain"] == "fallback":
            fb.append({"bc": r["bc"], "regime": "page", "form": r["form"], "I": r["I"]["est"]})
    for r in cold_rows:
        if r.get("I") is None or r.get("map") is not None:
            continue
        if r["chain"] in CAL_CHAINS and r["weighting"] == "w" and r["policy"] == "D1-DEFAULT" \
                and not (-0.02 <= r["I"]["est"] <= 0.01):
            bad.append(f"cold bc{r['bc']} n{r['n']} {r['chain']} {r['form']} I {r['I']['est']:.4f}")
        if r["chain"] == "fallback":
            fb.append({"bc": r["bc"], "regime": f"cold n={r['n']}", "form": r["form"], "I": r["I"]["est"]})
    ld_bad = [f"{r['regime']} bc{r['bc']} n{r['n']} {r['chain']} {r['stream']} {r['mode']} {r['rung']} "
              f"{r['successes']}/{r['T']}" for r in ldpc_rows
              if r.get("chain") in CAL_CHAINS and r.get("weighting") == "w" and r["successes"] > 0
              and r.get("policy") in ("D1-DEFAULT",)]
    return {"violations": bad[:50], "n_violations": len(bad), "ldpc_violations": ld_bad[:50],
            "fallback_null_I": fb, "pass": not bad and not ld_bad}


def c6_check(page_rows: list[dict[str, Any]], bayes: dict[str, float], ldpc_rows: list[dict[str, Any]],
             twocap: dict[str, Any], dead_page: list[dict[str, Any]], detect: dict[int, float]) -> dict[str, Any]:
    """S1 at R-P (P-a, replicate 0): each chain within 0.005 bits of Bayes on every form and of each other;
    no Wilson-disjoint chain pair in LDPC; the two-capture and dead-Y legs."""
    chains = ("fallback", "lo-first", "hi-first", "six-maps")
    pa = [r for r in page_rows if r["population"] == "P-a" and r["replicate"] == 0 and r["weighting"] in ("w", "-")
          and r["chain"] in chains]
    devs = {f"{r['chain']} {r['form']}": r["I"]["est"] - bayes[r["form"]] for r in pa}
    worst_bayes = max((abs(v) for v in devs.values()), default=0.0)
    spread = 0.0
    for form in bayes:
        vals = [r["I"]["est"] for r in pa if r["form"] == form]
        if vals:
            spread = max(spread, max(vals) - min(vals))
    disjoint = []
    by: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for r in ldpc_rows:
        if r.get("chain") in chains and r.get("weighting") in ("w", "-") and r.get("population") == "final":
            by.setdefault((r["stream"], r["mode"], r["rung"], r["population"]), []).append(r)
    for key, rs in by.items():
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i]["wilson"], rs[j]["wilson"]
                if a["hi"] < b["lo"] or b["hi"] < a["lo"]:
                    disjoint.append(f"{key} {rs[i]['chain']} vs {rs[j]['chain']}")
    tc = twocap
    dead_ab = {r["arm"]: r["I_hi"]["est"] for r in dead_page if r.get("replicate") == 0}
    ab_gap = abs(dead_ab.get("a", 0.0) - dead_ab.get("b", 0.0)) if dead_ab else float("inf")
    ok = (worst_bayes <= 0.005 and spread <= 0.005 and not disjoint and tc["identical"] and tc["summed_ge"]
          and tc["slope_ok"] and min(detect.values(), default=0.0) >= 0.99 and ab_gap <= 0.005)
    return {"max_dev_from_bayes": worst_bayes, "devs": devs, "chain_spread": spread, "ldpc_disjoint": disjoint,
            "twocapture": tc, "deadY_detect": detect, "deadY_a_minus_b": ab_gap, "bayes_I": bayes, "pass": bool(ok)}


def c8_check(page_rows: list[dict[str, Any]], c1: list[dict[str, Any]]) -> dict[str, Any]:
    out = []
    hard = {r["bc"]: r for r in c1}
    for r in page_rows:
        if r["chain"] == "six-maps" and r["population"] == "P-a" and r["replicate"] == 0 and r["form"] in ("hi", "lo") \
                and r["bc"] in hard and r["features"] == "F":
            anchor = hard[r["bc"]]["I_hi" if r["form"] == "hi" else "I_lo"]
            out.append({"bc": r["bc"], "form": r["form"], "soft": r["I"]["est"], "hard": anchor,
                        "ok": bool(r["I"]["est"] >= anchor - 0.01)})
    return {"rows": out, "pass": True, "warning": [o for o in out if not o["ok"]]}


def c9_rows(collapse: list[dict[str, Any]], dead_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"healthy_false_collapse": collapse,
            "deadY_detect": [{"bc": r["bc"], "n": r["n"], "detect_rate": r["detect_rate"]} for r in dead_rows
                             if r.get("regime") == "cold" and r["arm"] == "a"], "pass": True}

