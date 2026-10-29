"""R11 — the regimes on one band-capture: R-P page (P-a furniture only, P-b furniture + certified cells, page-final
= either), R-C cold start (n = 1, 2, 3, 4, 8 emulated tiles, five policies, the gates), R-D dead Y (the hi stream
read through (L_hi, L_hi, 0): (a) the 4th PAVA, (b) the bounded raw t_hi, (c) the healthy ceiling, (c') the
healthy map on the dead statistic), the label-shuffle null and the single-pose arm (features 'F1').

What each returns: JSON-ready rows (page / coldstart / gates / deadY / ldpc / yield) plus the per-trial LDPC
outcomes the decision rules bootstrap.  Why: the protocol's 'Regimes' section, every number paired across arms
(one furniture draw, one bootstrap count matrix, one LDPC trial set per band-capture and regime).
How: furniture from rng([MASTER_SEED, 1, bc, 0, k]) (page replicate k) or ([.., 3, bc, n, k]) (cold draw k),
folds from REGIME 2, the validation third from REGIME 12, LDPC trials from REGIME 4 (page) / 5 (cold), the
dead-Y substitution from REGIME 6, the shuffle from REGIME 7, bootstraps from REGIME 10; cold draws and LDPC
trials run on a thread pool (free-threaded interpreter), each draw carrying its own LDPC trial.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from measure.cmy_calibration.chains import MAP_SPECS, Y, W, bound_triple, demap, fit_stratified_pava, raw_scores
from measure.cmy_calibration.config import (COLD_SHAPES, FOUNTAIN_BITS, MASTER_SEED, POLICIES, REGIME, RUNGS,
                                           Params)
from measure.cmy_calibration.estimators import (ROWS, WindowBootstrap, ece, est, info_rows, logistic_slope,
                                                row_cells, slope_ci, wilson)
from measure.cmy_calibration.fit import (ARM_CHAINS, Band, Furniture, apply_context, cluster_origins,
                                         draw_furniture, fit_context, region_gates, shuffle_labels)
from measure.cmy_calibration.ldpc_sim import (Outcomes, Trial, any_stage, draw_positions, draw_users, or_outcomes,
                                              pack_bits, run_trial, run_trials, tile_yield, yield_pairs_for)

PAGE_POLICIES = ("D1-DEFAULT", "FLOORS(i)", "FLOORS(ii)")
GATE_CHAINS = ("lo-first", "hi-first", "six-maps")


def rng_for(regime: str, bc: int, n: int, k: int) -> np.random.Generator:
    return np.random.default_rng([MASTER_SEED, REGIME[regime], bc, n, k])


def arm_key(*parts: str) -> str:
    return "|".join(parts)


def page_arms() -> list[tuple[str, str, str]]:
    return [(c, w, "D1-DEFAULT") for c, w in ARM_CHAINS]


def cold_arms(cb: bool = True) -> list[tuple[str, str, str]]:
    out = [("fallback", "-", "NEVER")]
    for c, w in ARM_CHAINS[1:]:
        if w == "cb" and not cb:
            continue
        out += [(c, w, p) for p in POLICIES if p != "NEVER"]
    return out


def oracle_forms(r: np.ndarray, state: np.ndarray) -> np.ndarray:
    """oracle-recal: per form a state-balanced PAVA on the evaluation cells' own raw statistic (in-sample)."""
    stat = demap(r)
    out = np.zeros_like(stat)
    for k, spec in enumerate(MAP_SPECS):
        member = np.isin(state, spec.states)
        lab = np.isin(state, spec.pos).astype(np.uint8)
        pm = fit_stratified_pava(stat[member, k], lab[member], state[member])
        out[:, k] = 0.0 if pm is None else pm.llrs(stat[:, k])
    return out


# ---------------------------------------------------------------- page

@dataclass
class PageFit:
    """One replicate's evaluated arms on the page payload (P-a and P-b, same payload order)."""
    payload: np.ndarray
    payload_region: np.ndarray
    forms: dict[str, np.ndarray]
    stored: dict[str, np.ndarray]
    bind: dict[str, float]
    collapse: dict[str, Any]
    gates: dict[tuple[str, str], dict[str, Any]]
    refused: str | None
    extra: dict[str, Any] = field(default_factory=dict)


def fold_contexts(band: Band, X: np.ndarray, st_fit: np.ndarray, fur: Furniture, k: int, K: int, workers: int,
                  weightings: tuple[str, ...], seed_bc: int | None = None) -> list[tuple[np.ndarray, Any]]:
    """P-b: regions to K folds by a seeded permutation; the other folds' payload joins the population, half
    (Bernoulli 1/2) on the QDA side and half on the map side (certified cells: kind -1, never validation).
    Returns per fold (payload positions of the fold, context)."""
    rng = rng_for("fold", band.bc if seed_bc is None else seed_bc, 0, k)
    perm = rng.permutation(band.n_regions)
    fold_of_region = np.empty(band.n_regions, np.int64)
    fold_of_region[perm] = np.arange(band.n_regions) % K
    bern = rng.random(fur.payload.size) < 0.5
    pf = fold_of_region[fur.payload_region]

    def one(f: int) -> tuple[np.ndarray, Any]:
        other = pf != f
        q_cells = np.concatenate([fur.search, fur.payload[other & bern]])
        m_cells = np.concatenate([fur.held, fur.payload[other & ~bern]])
        kind = np.concatenate([fur.held_kind, np.full(int((other & ~bern).sum()), -1, np.int8)])
        ctx = fit_context(X[q_cells], st_fit[q_cells], X[m_cells], st_fit[m_cells], kind,
                          np.zeros(m_cells.size, bool), ("D1-DEFAULT",), weightings)
        return np.flatnonzero(pf == f), ctx

    with ThreadPoolExecutor(max_workers=max(1, min(K, workers))) as pool:
        return list(pool.map(one, range(K)))


def page_fit(band: Band, feats: str, k: int, params: Params, *, shuffle: bool = False,
             X_override: np.ndarray | None = None, pops: tuple[str, ...] = ("P-a", "P-b"),
             oracle: bool = True, arms: list[tuple[str, str, str]] | None = None) -> PageFit:
    X = band.X[feats] if X_override is None else X_override
    arms = arms or page_arms()
    fur = draw_furniture(rng_for("page_furniture", band.bc, 0, k), band, list(range(band.n_regions)))
    st_fit = (shuffle_labels(rng_for("shuffle", band.bc, 0, k), band, fur, list(range(band.n_regions)))
              if shuffle else band.state)
    val = rng_for("valsplit", band.bc, 0, k).random(fur.held.size) < 1.0 / 3.0
    ctx = fit_context(X[fur.search], st_fit[fur.search], X[fur.held], st_fit[fur.held], fur.held_kind, val,
                      PAGE_POLICIES)
    pst = band.state[fur.payload]
    r, outs = apply_context(ctx, X[fur.payload], arms)
    forms: dict[str, np.ndarray] = {}
    stored: dict[str, np.ndarray] = {}
    bind: dict[str, float] = {}
    for a, o in outs.items():
        key = arm_key("P-a", *a)
        forms[key], stored[key], bind[key] = o.forms, o.stored, float(o.bind.mean())
    if oracle and r is not None:
        forms[arm_key("P-a", "oracle", "w", "-")] = oracle_forms(r, pst)
    extra: dict[str, Any] = {"map_diag": {MAP_SPECS[m].name: vars(d) for m, d in ctx.diag.items()},
                             "collapse_P-b": []}
    if "P-b" in pops:
        n = fur.payload.size
        fb = {arm_key("P-b", *a): np.zeros((n, 6)) for a in arms}
        sb = {arm_key("P-b", *a): np.zeros((n, 6 if a[0] == "six-maps" else 3)) for a in arms}
        bb = {arm_key("P-b", *a): np.zeros(n, bool) for a in arms}
        rb = np.zeros((n, 3))
        for pos, fctx in fold_contexts(band, X, st_fit, fur, k, params.K, params.workers, ("w", "cb")):
            rf, o2 = apply_context(fctx, X[fur.payload[pos]], arms)
            extra["collapse_P-b"].append(fctx.collapse)
            if rf is not None:
                rb[pos] = rf
            for a, o in o2.items():
                key = arm_key("P-b", *a)
                fb[key][pos], sb[key][pos], bb[key][pos] = o.forms, o.stored, o.bind
        forms.update(fb)
        stored.update(sb)
        bind.update({kk: float(v.mean()) for kk, v in bb.items()})
        if oracle:
            forms[arm_key("P-b", "oracle", "w", "-")] = oracle_forms(rb, pst)
    gates = region_gates(ctx, GATE_CHAINS)
    return PageFit(fur.payload, fur.payload_region, forms, stored, bind, ctx.collapse, gates, ctx.refused, extra)


def info_record(boot: WindowBootstrap, forms: np.ndarray, state: np.ndarray, group: np.ndarray,
                slope_rows: tuple[str, ...], B_slope: int) -> dict[str, dict[str, Any]]:
    point, bootI = boot.info(forms, state, group)
    pt = info_rows(forms, state)
    out = {}
    for i, row in enumerate(ROWS):
        L, b, w = row_cells(forms, state, i)
        if row in slope_rows:
            a, c, alo, ahi = slope_ci(forms, state, group, i, boot, B_slope)
        else:
            (a, c), alo, ahi = logistic_slope(L, b, w), None, None
        out[row] = {"I": est(point[i], bootI[:, i]), "logloss": float(pt["logloss"][i]),
                    "hard_err": float(pt["hard_err"][i]), "ece": ece(L, b, w),
                    "slope": {"a": a, "c": c, "lo": alo, "hi": ahi}}
    return out


def page_trials(band: Band, fits: list[PageFit], T: int, rungs: tuple[str, ...], regime: str = "ldpc_page",
                n_key: int = 0, streams: tuple[str, ...] = ("hi", "lo"), modes: tuple[str, ...] = ("bicm", "cond"),
                arm_filter: Any = None) -> Any:
    """Trial t uses replicate t % R; the region is uniform; positions from that region's payload."""
    for t in range(T):
        pf = fits[t % len(fits)]
        rng = rng_for(regime, band.bc, n_key, t)
        g = int(rng.integers(0, int(pf.payload_region.max()) + 1))
        cand = np.flatnonzero(pf.payload_region == g)
        pos, st, over = draw_positions(rng, cand, band.state[pf.payload[cand]])
        users = draw_users(rng, rungs)
        arms = {a: f[pos] for a, f in pf.forms.items() if arm_filter is None or arm_filter(a)}
        yield Trial(key=(MASTER_SEED, REGIME[regime], band.bc, n_key, t), state=st, users=users, arms=arms,
                    overflow=over, streams=streams, modes=modes, rungs=rungs)


def ldpc_rows(outs: Outcomes, base: dict[str, Any], rungs: tuple[str, ...], fields_of: Any,
              with_any: bool = True) -> tuple[list, list]:
    """ldpc rows (bicm / cond / any per stream and rung) and yield rows for every arm in outs; page-final arms
    are added by the caller as their own Outcomes."""
    rows, yrows = [], []
    rng = np.random.default_rng([MASTER_SEED, REGIME["bootstrap"], base.get("bc", 0), 7])
    T = len(outs.overflow)
    idx = rng.integers(0, max(T, 1), size=(2000, max(T, 1)))
    of = float(np.mean(outs.overflow)) if outs.overflow else 0.0
    for arm, d in outs.arms.items():
        f = fields_of(arm)
        for (st, mode, r), v in d.items():
            k = int(v.sum())
            lo, hi = wilson(k, v.size)
            rows.append({**base, **f, "stream": st, "mode": mode, "rung": r, "T": int(v.size), "successes": k,
                         "wilson": {"lo": lo, "hi": hi}, "false_accepts": int(outs.false_accepts[arm][(st, mode, r)]
                                                                             .sum()),
                         "overflow_frac": of, "retry150_successes": int(outs.retry[arm][(st, mode, r)].sum()),
                         "outcomes": pack_bits(v)})
        if with_any and all((s, "bicm", r) in d for s in ("hi", "lo") for r in rungs):
            for r in rungs:
                h, l_ = any_stage(d, r, r)
                for st, v in (("hi", h), ("lo", l_)):
                    k = int(v.sum())
                    lo, hi = wilson(k, v.size)
                    rows.append({**base, **f, "stream": st, "mode": "any", "rung": r, "T": int(v.size),
                                 "successes": k, "wilson": {"lo": lo, "hi": hi}, "false_accepts": 0,
                                 "overflow_frac": of, "retry150_successes": None, "outcomes": pack_bits(v)})
            for rh, rl in yield_pairs_for(rungs):
                y = tile_yield(d, rh, rl)
                yrows.append({**base, **f, "pair": f"{rh}x{rl}",
                              "bits_per_tile": est(float(y.mean()), y[idx].mean(1)), "T": int(y.size)})
    return rows, yrows


def final_outcomes(outs: Outcomes) -> Outcomes:
    """Page-final per arm: P-a OR P-b on the same trials (any-stage is then built from the OR'ed components,
    and separately recorded as any(P-a) OR any(P-b) by the caller)."""
    fin = Outcomes(overflow=list(outs.overflow))
    for arm, d in outs.arms.items():
        if not arm.startswith("P-a|"):
            continue
        other = "P-b|" + arm[4:]
        if other not in outs.arms:
            continue
        key = "final|" + arm[4:]
        fin.arms[key] = or_outcomes(d, outs.arms[other])
        fin.false_accepts[key] = or_outcomes(outs.false_accepts[arm], outs.false_accepts[other])
        fin.retry[key] = or_outcomes(outs.retry[arm], outs.retry[other])
    return fin


def page_fields(feats: str, regime: str) -> Any:
    def f(arm: str) -> dict[str, Any]:
        pop, chain, wt, pol = arm.split("|")
        return {"regime": regime, "n": None, "features": feats, "population": pop, "chain": chain,
                "weighting": wt, "policy": pol, "gate": None}
    return f


def run_page(band: Band, feats: str, params: Params, *, ldpc: bool = True, rungs: tuple[str, ...] = RUNGS,
             T: int | None = None, shuffle: bool = False, regime: str = "page", log: Any = print,
             cb_ldpc: bool = True, ldpc_pops: tuple[str, ...] = ("P-a", "P-b")) -> dict[str, Any]:
    """R-P on one band-capture: R replicates, information per (population, arm, row), LDPC page-final."""
    pops = ("P-a",) if shuffle else ("P-a", "P-b")
    page_rows: list[dict[str, Any]] = []
    fits: list[PageFit] = []
    for k in range(params.R):
        pf = page_fit(band, feats, k, params, shuffle=shuffle, pops=pops)
        boot = WindowBootstrap(len(band.win_ids), params.B,
                               rng_for("bootstrap", band.bc, 0, k * 10 + (1 if feats == "F1" else 0)))
        grp = band.win[pf.payload]
        pst = band.state[pf.payload]
        keys = list(pf.forms)

        def rec_of(key: str, k: int = k, boot: WindowBootstrap = boot) -> dict[str, dict[str, Any]]:
            return info_record(boot, pf.forms[key], pst, grp, ("hi", "lo") if k == 0 else (), params.B_slope)
        with ThreadPoolExecutor(max_workers=max(1, params.workers)) as pool:
            recs = list(pool.map(rec_of, keys))
        for key, rec in zip(keys, recs):
            f = pf.forms[key]
            pop, chain, wt, pol = key.split("|")
            for row, v in rec.items():
                page_rows.append({"bc": band.bc, "features": feats, "population": pop, "replicate": k,
                                  "chain": chain, "weighting": wt, "policy": pol, "regime": regime, "form": row,
                                  **v, "bound_bind_frac": pf.bind.get(key), "n_cells": int(f.shape[0]),
                                  "n_windows": len(band.win_ids)})
        log(f"  {regime} bc{band.bc} {feats} replicate {k}: {len(pf.forms)} arms; collapse {pf.collapse}")
        fits.append(pf)
    out: dict[str, Any] = {"page": page_rows, "fits": fits, "ldpc": [], "yield": [], "outcomes": None}
    if ldpc:
        T = params.T_page if T is None else T
        def flt(a: str) -> bool:
            return (cb_ldpc or "|cb|" not in a) and a.split("|")[0] in ldpc_pops
        outs = Outcomes()
        for trial, res in run_trials(page_trials(band, fits, T, rungs, arm_filter=flt), params.workers,
                                     max_iters=params.max_iters, retry_iters=params.retry_iters, alpha=params.alpha,
                                     retry=params.retry150):
            outs.add(trial, res)
        outs = outs.frozen()
        out.update(page_ldpc_rows(outs, {"bc": band.bc}, rungs, page_fields(feats, regime)))
        out["outcomes"] = outs
    return out


def page_ldpc_rows(outs: Outcomes, base: dict[str, Any], rungs: tuple[str, ...], fields_of: Any
                   ) -> dict[str, list]:
    """Per-population rows, the page-final BICM / COND components (P-a OR P-b) and the page-final any-stage
    with its yields."""
    r1, y1 = ldpc_rows(outs, base, rungs, fields_of)
    r2, _ = ldpc_rows(final_outcomes(outs), base, rungs, fields_of, with_any=False)
    r3, y3 = final_any_rows(outs, base, rungs, fields_of)
    return {"ldpc": r1 + r2 + r3, "yield": y1 + y3}


def final_any_rows(outs: Outcomes, base: dict[str, Any], rungs: tuple[str, ...], fields_of: Any
                   ) -> tuple[list, list]:
    """Page-final any-stage = any(P-a) OR any(P-b), population 'final', mode 'any'; yields from the same."""
    rows, yrows = [], []
    rng = np.random.default_rng([MASTER_SEED, REGIME["bootstrap"], base.get("bc", 0), 8])
    T = len(outs.overflow)
    idx = rng.integers(0, max(T, 1), size=(2000, max(T, 1)))
    for arm, d in outs.arms.items():
        if not arm.startswith("P-a|") or "P-b|" + arm[4:] not in outs.arms:
            continue
        e = outs.arms["P-b|" + arm[4:]]
        if not all((s, "bicm", r) in d for s in ("hi", "lo") for r in rungs):
            continue
        f = {**fields_of(arm), "population": "final"}
        for r in rungs:
            ha, la = any_stage(d, r, r)
            hb, lb = any_stage(e, r, r)
            for st, v in (("hi", ha | hb), ("lo", la | lb)):
                k = int(v.sum())
                lo, hi = wilson(k, v.size)
                rows.append({**base, **f, "stream": st, "mode": "any", "rung": r, "T": int(v.size),
                             "successes": k, "wilson": {"lo": lo, "hi": hi}, "false_accepts": 0,
                             "overflow_frac": None, "retry150_successes": None, "outcomes": pack_bits(v)})
        for rh, rl in yield_pairs_for(rungs):
            ha, _ = any_stage(d, rh, rl)
            hb, _ = any_stage(e, rh, rl)
            _, la = any_stage(d, rh, rl)
            _, lb = any_stage(e, rh, rl)
            y = FOUNTAIN_BITS[rh] * (ha | hb).astype(np.float64) + FOUNTAIN_BITS[rl] * (la | lb).astype(np.float64)
            yrows.append({**base, **f, "pair": f"{rh}x{rl}", "bits_per_tile": est(float(y.mean()),
                                                                                 y[idx].mean(1)),
                          "T": int(y.size)})
    return rows, yrows


# ---------------------------------------------------------------- cold start

@dataclass
class ColdDraw:
    origin: int
    refused: bool
    collapse: dict[str, Any]
    I: dict[str, np.ndarray]                 # arm -> (8,) per row
    err: dict[str, np.ndarray]
    maps: dict[str, dict[str, Any]]
    gates: dict[tuple[str, str], dict[str, Any]]
    I_lo_payload: dict[str, float]
    ldpc: dict[str, dict[tuple[str, str, str], tuple[int, ...]]] | None
    overflow: float


def cold_draw(band: Band, X: np.ndarray, n: int, k: int, origins: list[tuple[int, ...]], params: Params,
              arms: list[tuple[str, str, str]], *, shuffle: bool, ldpc: bool, rungs: tuple[str, ...]) -> ColdDraw:
    rng = rng_for("cold", band.bc, n, k)
    oi = int(rng.integers(0, len(origins)))
    regions = origins[oi]
    fur = draw_furniture(rng, band, regions)
    st_fit = shuffle_labels(rng_for("shuffle", band.bc, n, k), band, fur, regions) if shuffle else band.state
    val = rng_for("valsplit", band.bc, n, k).random(fur.held.size) < 1.0 / 3.0
    ctx = fit_context(X[fur.search], st_fit[fur.search], X[fur.held], st_fit[fur.held], fur.held_kind, val)
    pst = band.state[fur.payload]
    r, outs = apply_context(ctx, X[fur.payload], arms)
    I, err = {}, {}
    for a, o in outs.items():
        ir = info_rows(o.forms, pst)
        I[arm_key(*a)], err[arm_key(*a)] = ir["I"], ir["hard_err"]
    maps: dict[str, dict[str, Any]] = {}
    if r is not None:
        stat, fb = demap(r), demap(bound_triple(r)[0])
        for m, spec in enumerate(MAP_SPECS):
            d = ctx.diag[m]
            member = np.isin(pst, spec.states)
            pm = ctx.maps.get(("H", "w", m))
            f_map = np.zeros((pst.size, 6))
            f_fb = np.zeros((pst.size, 6))
            f_fb[:, m] = fb[:, m]
            f_map[:, m] = fb[:, m] if pm is None else pm.llrs(stat[:, m])
            im = info_rows(f_map[member], pst[member])["I"][m]
            ifb = info_rows(f_fb[member], pst[member])["I"][m]
            q_i = bool(d.qualified.get("Hfit")) and (spec.marginal or d.pregate.get("Hfit") is True)
            q_ii = bool(d.qualified.get("H")) and (spec.marginal or d.pregate.get("H") is True)
            maps[spec.name] = {"fitted": pm is not None, "q_i": q_i, "q_ii": q_ii, "q_d1": bool(d.qualified.get("H")),
                               "pregate_i": d.pregate.get("Hfit"), "pregate_ii": d.pregate.get("H"),
                               "I_map": float(im), "I_fallback": float(ifb)}
    gates = region_gates(ctx, GATE_CHAINS)
    I_lo = {arm_key(*a): float(I[arm_key(*a)][1]) for a in arms}
    res = None
    over = 0.0
    if ldpc:
        trng = rng_for("ldpc_cold", band.bc, n, k)
        cand = np.flatnonzero(fur.payload_region == 0)
        pos, st, ov = draw_positions(trng, cand, pst[cand])
        users = draw_users(trng, rungs)
        tr = Trial(key=(MASTER_SEED, REGIME["ldpc_cold"], band.bc, n, k), state=st, users=users,
                   arms={arm_key(*a): outs[a].forms[pos] for a in arms if params.cb_ldpc or a[1] != "cb"},
                   overflow=ov, rungs=rungs)
        res = run_trial(tr, params.max_iters, params.retry_iters, params.alpha, params.retry150)
        over = ov / pos.size
    return ColdDraw(oi, ctx.refused is not None, ctx.collapse, I, err, maps, gates, I_lo, res, over)


def run_cold(band: Band, feats: str, n: int, params: Params, *, D_info: int | None = None,
             D_ldpc: int | None = None, shuffle: bool = False, rungs: tuple[str, ...] = RUNGS,
             regime: str = "cold", log: Any = print) -> dict[str, Any]:
    X = band.X[feats]
    origins = cluster_origins(band, n, COLD_SHAPES)
    if not origins:
        return {"coldstart": [], "gates": [], "ldpc": [], "yield": [], "draws": [], "skipped": "no cluster fits"}
    D_info = params.D_info if D_info is None else D_info
    D_ldpc = params.D_ldpc if D_ldpc is None else D_ldpc
    arms = cold_arms(True)

    def task(k: int) -> ColdDraw:
        return cold_draw(band, X, n, k, origins, params, arms, shuffle=shuffle, ldpc=k < D_ldpc, rungs=rungs)

    with ThreadPoolExecutor(max_workers=max(1, params.workers)) as pool:
        draws = list(pool.map(task, range(D_info)))
    log(f"  {regime} bc{band.bc} {feats} n={n}: {D_info} draws, {sum(d.refused for d in draws)} refused, "
        f"lo-collapse {np.mean([d.collapse['lo'] for d in draws]):.3f}")
    return summarise_cold(band, feats, n, params, draws, arms, len(origins), regime, rungs)


def summarise_cold(band: Band, feats: str, n: int, params: Params, draws: list[ColdDraw],
                   arms: list[tuple[str, str, str]], n_origins: int, regime: str, rungs: tuple[str, ...]
                   ) -> dict[str, Any]:
    boot = WindowBootstrap(n_origins, params.B, rng_for("bootstrap", band.bc, n, 1000 + (feats == "F1")))
    grp = np.array([d.origin for d in draws])
    D = len(draws)
    rows: list[dict[str, Any]] = []
    base = {"bc": band.bc, "n": n, "features": feats, "regime": regime}
    fb_key = arm_key("fallback", "-", "NEVER")
    fbI = np.stack([d.I[fb_key] for d in draws])
    for a in arms:
        key = arm_key(*a)
        Ia = np.stack([d.I[key] for d in draws])
        Ea = np.stack([d.err[key] for d in draws])
        for i, row in enumerate(ROWS):
            p, b = boot.mean(Ia[:, i], grp)
            pd, bd = boot.mean(Ia[:, i] - fbI[:, i], grp)
            rows.append({**base, "chain": a[0], "weighting": a[1], "policy": a[2], "map": None, "form": row,
                         "I": est(p, b), "dI_vs_fallback": est(pd, bd), "hard_err": float(Ea[:, i].mean()),
                         "region_refusal_frac": float(np.mean([d.refused for d in draws])), "n_draws": D})
    for wpair in (("lo-first", "D1-DEFAULT"), ("hi-first", "D1-DEFAULT")):
        kw, kc = arm_key(wpair[0], "w", wpair[1]), arm_key(wpair[0], "cb", wpair[1])
        for i, row in enumerate(ROWS[:2]):
            dv = np.array([d.I[kw][i] - d.I[kc][i] for d in draws])
            p, b = boot.mean(dv, grp)
            rows.append({**base, "chain": wpair[0], "weighting": "w-cb", "policy": wpair[1], "map": None,
                         "form": row, "I": None, "dI_w_minus_cb": est(p, b), "n_draws": D})
    for spec in MAP_SPECS:
        ms = [d.maps.get(spec.name) for d in draws if spec.name in d.maps]
        if not ms:
            continue
        g2 = np.array([d.origin for d in draws if spec.name in d.maps])
        dI = np.array([m["I_map"] - m["I_fallback"] for m in ms])
        p, b = boot.mean(dI, g2)
        rows.append({**base, "chain": None, "weighting": "w", "policy": "ALWAYS", "map": spec.name, "form": None,
                     "qualified_frac": {"i": float(np.mean([m["q_i"] for m in ms])),
                                        "ii": float(np.mean([m["q_ii"] for m in ms])),
                                        "d1": float(np.mean([m["q_d1"] for m in ms]))},
                     "pregate_pass_frac": {v: float(np.mean([m[f"pregate_{v}"] is True for m in ms]))
                                           for v in ("i", "ii")},
                     "fitted_frac": float(np.mean([m["fitted"] for m in ms])),
                     "I_map": float(np.mean([m["I_map"] for m in ms])),
                     "I_fallback": float(np.mean([m["I_fallback"] for m in ms])), "dI": est(p, b),
                     "region_refusal_frac": float(np.mean([d.refused for d in draws])), "n_draws": len(ms)})
    collapse = {"lo": float(np.mean([d.collapse["lo"] for d in draws])),
                "hi": float(np.mean([d.collapse["hi"] for d in draws])),
                "any": float(np.mean([d.collapse["lo"] or d.collapse["hi"] for d in draws])), "n_draws": D}
    out: dict[str, Any] = {"coldstart": rows, "collapse": {**base, **collapse}, "gates": [], "ldpc": [],
                           "yield": [], "draws": draws}
    ld = [d for d in draws if d.ldpc is not None]
    if ld:
        outs = Outcomes()
        for d in ld:
            outs.overflow.append(d.overflow)
            for arm, res in d.ldpc.items():
                for kk, v in res.items():
                    outs.arms.setdefault(arm, {}).setdefault(kk, []).append(v[0])
                    outs.false_accepts.setdefault(arm, {}).setdefault(kk, []).append(v[1])
                    outs.retry.setdefault(arm, {}).setdefault(kk, []).append(v[2])
        outs = outs.frozen()

        def fields_of(arm: str) -> dict[str, Any]:
            c, w, p = arm.split("|")
            return {"regime": regime, "n": n, "features": feats, "population": "cold", "chain": c,
                    "weighting": w, "policy": p, "gate": None}
        r_, y_ = ldpc_rows(outs, {"bc": band.bc}, rungs, fields_of)
        out["ldpc"], out["yield"] = r_, y_
        out["outcomes"] = outs
        out["gates"] = gate_rows(band, feats, n, draws, ld, outs, boot, grp, rungs, regime)
    else:
        out["gates"] = gate_rows(band, feats, n, draws, [], None, boot, grp, rungs, regime)
    return out


def gate_rows(band: Band, feats: str, n: int, draws: list[ColdDraw], ld: list[ColdDraw], outs: Outcomes | None,
              boot: WindowBootstrap, grp: np.ndarray, rungs: tuple[str, ...], regime: str) -> list[dict[str, Any]]:
    """Per (chain, source v, gate): refusal with Wilson, dust-only share of G3 refusals, false refusal / adoption
    against the payload I_lo, and the policy tile yield (adopted -> FLOORS(v) outcomes, else the fallback's)."""
    rows = []
    fb_key = arm_key("fallback", "-", "NEVER")
    for chain in GATE_CHAINS:
        for v, pol in (("i", "FLOORS(i)"), ("ii", "FLOORS(ii)")):
            cand_key = arm_key(chain, "w", pol)
            for gate in ("G0", "G1", "G2", "G3"):
                adopt = np.array([bool(d.gates.get((chain, v), {}).get(gate, False)) for d in draws])
                refused = ~adopt
                better = np.array([d.I_lo_payload[cand_key] > d.I_lo_payload[fb_key] for d in draws])
                k = int(refused.sum())
                wl = wilson(k, refused.size)
                dust_only = np.array([bool(d.gates.get((chain, v), {}).get("G3_dust_only_refusal", False))
                                      for d in draws])
                row: dict[str, Any] = {
                    "bc": band.bc, "n": n, "features": feats, "regime": regime, "chain": chain, "valsrc": v,
                    "gate": gate, "refusal": {"est": k / refused.size, "lo": wl[0], "hi": wl[1]},
                    "dust_only_share": (float(dust_only[refused].mean()) if gate == "G3" and k else None),
                    "false_refusal": float(np.mean(refused & better)), "false_adoption": float(np.mean(adopt & ~better)),
                    "n_draws": len(draws), "policy_yield": None, "policy_yield_trials": None}
                if outs is not None and ld:
                    ad = np.array([bool(d.gates.get((chain, v), {}).get(gate, False)) for d in ld])
                    per_rung = {}
                    for r in rungs:
                        yc = tile_yield(outs.arms[cand_key], r, r)
                        yf = tile_yield(outs.arms[fb_key], r, r)
                        per_rung[r] = np.where(ad, yc, yf)
                    mean_y = np.mean(np.stack(list(per_rung.values())), 0)
                    g_ld = np.array([d.origin for d in ld])
                    p, b = boot.mean(mean_y, g_ld)
                    row["policy_yield"] = est(p, b)
                    row["policy_yield_trials"] = [float(x) for x in mean_y]
                    row["T"] = len(ld)
                rows.append(row)
    return rows


# ---------------------------------------------------------------- dead Y

def dead_features(band: Band, feats: str) -> np.ndarray:
    """Every Y cell's features replaced by those of a uniformly drawn W cell of the same window (seeded)."""
    X = band.X[feats].copy()
    rng = rng_for("deadY", band.bc, 0, 0)
    for w in range(len(band.win_ids)):
        cells = np.flatnonzero(band.win == w)
        ys = cells[band.state[cells] == Y]
        ws = cells[band.state[cells] == W]
        if ys.size and ws.size:
            X[ys] = band.X[feats][rng.choice(ws, ys.size, replace=True)]
    return X


def hi_arms(ctx_dead: Any, ctx_ok: Any, Xd: np.ndarray, Xh: np.ndarray, page: bool) -> dict[str, np.ndarray]:
    """R-D's hi LLRs (read through (L_hi, L_hi, 0), bounded) as (N, 6) forms with only hi non-zero."""
    def through(L: np.ndarray) -> np.ndarray:
        s, _ = bound_triple(np.stack([L, L, np.zeros_like(L)], 1))
        f = np.zeros((L.size, 6))
        f[:, 0] = demap(s)[:, 0]
        return f
    out: dict[str, np.ndarray] = {}
    n = Xd.shape[0]
    if ctx_dead.refused is None:
        rd = raw_scores(ctx_dead.model, Xd)
        t_raw = demap(rd)[:, 0]
        t_bnd = demap(bound_triple(rd)[0])[:, 0]
        pm = ctx_dead.pieces[("D1-DEFAULT", "w")][0]
        out["a"] = through(t_bnd if pm is None else pm.llrs(t_raw))
        out["b"] = through(t_bnd)
        if ctx_ok.refused is None and page:
            hm = ctx_ok.pieces[("D1-DEFAULT", "w")][0]
            out["c'"] = through(t_bnd if hm is None else hm.llrs(t_raw))
    else:
        out["a"] = out["b"] = np.zeros((n, 6))
    if ctx_ok.refused is None:
        rh = raw_scores(ctx_ok.model, Xh)
        hm = ctx_ok.pieces[("D1-DEFAULT", "w")][0]
        out["c"] = through(demap(bound_triple(rh)[0])[:, 0] if hm is None else hm.llrs(demap(rh)[:, 0]))
    else:
        out["c"] = np.zeros((n, 6))
    return out


def run_deady(band: Band, feats: str, params: Params, *, sizes: tuple[int, ...], ldpc: bool = True,
              rungs: tuple[str, ...] = RUNGS, T: int | None = None, D_info: int | None = None,
              D_ldpc: int | None = None, log: Any = print) -> dict[str, Any]:
    """R-D page-final and cold start; lo force-erased, hi via arms a / b / c (/ c' at page)."""
    Xd = dead_features(band, feats)
    Xh = band.X[feats]
    rows: list[dict[str, Any]] = []
    ldrows: list[dict[str, Any]] = []
    T = params.T_page if T is None else T
    # page
    fits = []
    for k in range(params.R):
        fur = draw_furniture(rng_for("page_furniture", band.bc, 0, k), band, list(range(band.n_regions)))
        val = np.zeros(fur.held.size, bool)
        cd = fit_context(Xd[fur.search], band.state[fur.search], Xd[fur.held], band.state[fur.held], fur.held_kind,
                         val, ("D1-DEFAULT",), ("w",))
        ch = fit_context(Xh[fur.search], band.state[fur.search], Xh[fur.held], band.state[fur.held], fur.held_kind,
                         val, ("D1-DEFAULT",), ("w",))
        forms = hi_arms(cd, ch, Xd[fur.payload], Xh[fur.payload], True)
        boot = WindowBootstrap(len(band.win_ids), params.B, rng_for("bootstrap", band.bc, 0, 500 + k))
        pst = band.state[fur.payload]
        for arm, f in forms.items():
            p, b = boot.info(f, pst, band.win[fur.payload])
            rows.append({"bc": band.bc, "regime": "page", "n": None, "replicate": k, "arm": arm,
                         "I_hi": est(p[0], b[:, 0]), "detect": bool(cd.collapse["lo"]),
                         "n_cells": int(pst.size)})
        fits.append(PageFit(fur.payload, fur.payload_region, {arm_key("P-a", a, "-", "-"): f for a, f in forms.items()},
                            {}, {}, cd.collapse, {}, cd.refused))
    log(f"  deadY bc{band.bc} page: detect {[f.collapse['lo'] for f in fits]}")
    if ldpc:
        outs = Outcomes()
        for trial, res in run_trials(page_trials(band, fits, T, rungs, streams=("hi",), modes=("bicm",)),
                                     params.workers, max_iters=params.max_iters, retry_iters=params.retry_iters,
                                     alpha=params.alpha, retry=params.retry150):
            outs.add(trial, res)
        ldrows += deady_ldpc_rows(outs.frozen(), band.bc, "page", None, rungs)
    # cold
    for n in sizes:
        origins = cluster_origins(band, n, COLD_SHAPES)
        if not origins:
            continue
        Di = params.D_info if D_info is None else D_info
        Dl = params.D_ldpc if D_ldpc is None else D_ldpc

        def task(k: int, n: int = n, origins: list[tuple[int, ...]] = origins) -> tuple[Any, ...]:
            rng = rng_for("cold", band.bc, n, k)
            oi = int(rng.integers(0, len(origins)))
            fur = draw_furniture(rng, band, origins[oi])
            val = np.zeros(fur.held.size, bool)
            cd = fit_context(Xd[fur.search], band.state[fur.search], Xd[fur.held], band.state[fur.held],
                             fur.held_kind, val, ("D1-DEFAULT",), ("w",))
            ch = fit_context(Xh[fur.search], band.state[fur.search], Xh[fur.held], band.state[fur.held],
                             fur.held_kind, val, ("D1-DEFAULT",), ("w",))
            pst = band.state[fur.payload]
            forms = hi_arms(cd, ch, Xd[fur.payload], Xh[fur.payload], False)
            Ihi = {a: float(info_rows(f, pst)["I"][0]) for a, f in forms.items()}
            res = None
            if ldpc and k < Dl:
                trng = rng_for("ldpc_cold", band.bc, n, 10_000 + k)
                cand = np.flatnonzero(fur.payload_region == 0)
                pos, st, ov = draw_positions(trng, cand, pst[cand])
                tr = Trial(key=(MASTER_SEED, REGIME["ldpc_cold"], band.bc, n, 10_000 + k), state=st,
                           users=draw_users(trng, rungs), arms={arm_key("cold", a, "-", "-"): f[pos]
                                                                for a, f in forms.items()},
                           overflow=ov, streams=("hi",), modes=("bicm",), rungs=rungs)
                res = (run_trial(tr, params.max_iters, params.retry_iters, params.alpha, params.retry150), ov)
            return oi, bool(cd.collapse["lo"]), bool(ch.collapse["lo"] or ch.collapse["hi"]), Ihi, res

        with ThreadPoolExecutor(max_workers=max(1, params.workers)) as pool:
            got = list(pool.map(task, range(Di)))
        boot = WindowBootstrap(len(origins), params.B, rng_for("bootstrap", band.bc, n, 600))
        grp = np.array([g[0] for g in got])
        det = float(np.mean([g[1] for g in got]))
        fc = float(np.mean([g[2] for g in got]))
        for arm in got[0][3]:
            p, b = boot.mean(np.array([g[3][arm] for g in got]), grp)
            rows.append({"bc": band.bc, "regime": "cold", "n": n, "arm": arm, "I_hi": est(p, b),
                         "detect_rate": det, "false_collapse_rate": fc, "n_draws": Di})
        if ldpc:
            outs = Outcomes()
            for g in got:
                if g[4] is None:
                    continue
                res, ov = g[4]
                outs.overflow.append(ov / 3976)
                for arm, d in res.items():
                    for kk, v in d.items():
                        outs.arms.setdefault(arm, {}).setdefault(kk, []).append(v[0])
                        outs.false_accepts.setdefault(arm, {}).setdefault(kk, []).append(v[1])
                        outs.retry.setdefault(arm, {}).setdefault(kk, []).append(v[2])
            ldrows += deady_ldpc_rows(outs.frozen(), band.bc, "cold", n, rungs)
        log(f"  deadY bc{band.bc} n={n}: detect {det:.3f}, healthy false collapse {fc:.3f}")
    return {"deadY": rows, "ldpc": ldrows}


def deady_ldpc_rows(outs: Outcomes, bc: int, regime: str, n: int | None, rungs: tuple[str, ...]) -> list:
    rows = []
    for arm, d in outs.arms.items():
        a = arm.split("|")[1]
        for r in rungs:
            v = d[("hi", "bicm", r)]
            k = int(v.sum())
            lo, hi = wilson(k, v.size)
            rows.append({"bc": bc, "regime": f"deadY-{regime}", "n": n, "features": "F", "population": regime,
                         "chain": None, "weighting": "w", "policy": None, "gate": None, "arm": a, "stream": "hi",
                         "mode": "bicm", "rung": r, "T": int(v.size), "successes": k, "wilson": {"lo": lo, "hi": hi},
                         "false_accepts": int(outs.false_accepts[arm][("hi", "bicm", r)].sum()),
                         "overflow_frac": float(np.mean(outs.overflow)) if outs.overflow else None,
                         "retry150_successes": int(outs.retry[arm][("hi", "bicm", r)].sum()),
                         "outcomes": pack_bits(v)})
    return rows


def with_features(band: Band, feats: str, X: np.ndarray) -> Band:
    return replace(band, X={**band.X, feats: X})

