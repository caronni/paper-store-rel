"""R11 follow-up — two arm families measured after the run of record: marginal-only chains and the logit evaluator.

What: every existing arm is left untouched (this module imports the instrument and edits none of it):
  A. MARGINAL-ONLY chains.  `hi-first-marginal` = the hi-first fold with ONLY L_hi fitted (the state-balanced 'w'
     map of the regime's policy, as the existing hi-first) and both conditional pieces RAW — the per-map fallback,
     i.e. the form of the bounded raw triple that chains.chain_output emits for an unfitted piece — folded back by
     the existing hi-first fold, bounded and demapped into the six consumer forms; `lo-first-marginal` likewise
     with only L_lo (the lo-first fold).
  B. The LOGIT evaluator.  The SAME PAVA nodes (score_nodes, probability_nodes of the fitted PavaMap) interpolated
     linearly in logit(p) = log(p / (1 - p)) instead of in p (holo's PavaMap.llrs); np.interp extrapolates flat
     beyond the end nodes.  Applied to every fitted map of lo-first, hi-first, six-maps and both marginal-only
     chains; those arms are named `<chain>/logit`.
Measurements (decision band-captures bc 0-3 = B3@2400, U12@2400, U12@4800, X10 of config.BAND_CAPTURES):
  page        P-a and P-b information, replicate 0, policy D1-DEFAULT, all eight estimator rows, the window
              bootstrap with the run's own count matrix (B = 2000), paired dI vs the fallback; the fallback,
              lo-first, hi-first and six-maps rows are checked against the JSON of record (max |diff| recorded).
  c3          the must-not-lose check on A1@2400 (bc 4), P-a replicate 0, the same rows and check.
  cold        n in {1, 2, 3, 4, 8}, draws k = 0..D-1 of the run's draw machinery and seeds (D = 150), policies
              D1-DEFAULT and ALWAYS: chain-level information and dI vs the fallback (bootstrap over cluster origins
              with the run's count matrix); per map the dI of the linear and of the logit evaluation against its
              raw piece (the ALWAYS map on H, weighting 'w' — the run's T3 definition).
  repro-cold  bc 1 n = 1 with the run's 400 draws: the chain rows and the per-map dI against the JSON (the cold
              machinery's reproduction check; not a measurement).
  ldpc        U12@2400 (bc 1) at r0850: page-final (any(P-a) OR any(P-b) as the run's final_any_rows; replicates
              t mod R; the run's trials t = 0..T-1 with user bits drawn for all three rungs so the rng stream is
              the run's) and cold n = 2 (draws k = 0..T-1, both policies); lo any-stage and hi BICM (+ lo BICM and
              hi any-stage); per arm Wilson AND a region-cluster bootstrap CI; paired differences with a
              region-cluster bootstrap CI and the exact McNemar test; retry150 off (any-stage reads the 60-iteration
              success only).  The fallback's and hi-first's outcomes are compared bit for bit with the JSON's packed
              outcomes on the trials the run made.
  report      followup.json (every number with its n and interval) and followup.md (the tables).
Why: the run found PavaMap.llrs' probability-space interpolation costs 0.02-0.12 bit on near-separable pairs and
that the fitted CONDITIONAL maps are what lose on pages while the fitted marginals gain; these arms separate the
two effects.  How: per stage a parts/<stage>.json under the output directory; every rng is the run's
(regimes.rng_for) or [MASTER_SEED, REGIME['bootstrap'], bc, 20000 + key] for the new cluster bootstraps.
Inputs: --art, the R11 run's work directory (its cells-<capture>.npz caches and cmy-calibration-diagnostic.json, the
JSON of record checked against), named by flag (no default); output --out, default <art>/followup-arms.

Command (one stage per invocation; `report` merges the parts):
    PYTHONPATH=src:. env/bin/python -m measure.cmy_calibration.followup --art build/cmy-calibration --stage page
    (stages: page, c3, cold, repro-cold, ldpc, report; the run of record read and wrote
    scratch/cmy-calibration-20261010/ and its followup-arms/)
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from holo.receiver.plugins.color_model import PavaMap
from measure.cmy_calibration import regimes
from measure.cmy_calibration.chains import MAP_SPECS, ChainOut, bound_triple, chain_output, demap, raw_scores
from measure.cmy_calibration.config import (COLD_SHAPES, COLD_SIZES, DECISION_BCS, MASTER_SEED, REGIME, RUNGS,
                                            Params)
from measure.cmy_calibration.estimators import ROWS, WindowBootstrap, est, info_rows, mcnemar_exact, wilson
from measure.cmy_calibration.fit import Band, Context, cluster_origins, draw_furniture, fit_context
from measure.cmy_calibration.ldpc_sim import Trial, any_stage, draw_positions, draw_users, run_trial, run_trials, \
    unpack_bits
from measure.cmy_calibration.run import code_sha256, jsonable, load_bands, write_json

OUT_NAME = "followup-arms"
SOURCE_NAME = "cmy-calibration-diagnostic.json"
PAGE_POLICY = "D1-DEFAULT"
COLD_POLICIES = ("D1-DEFAULT", "ALWAYS")
LDPC_RUNG = "r0850"
LDPC_BC = 1
C3_BC = 4
COLD_LDPC_N = 2
FORMS6 = ROWS[:6]
REPRO_TOL = 5e-5


@dataclass(frozen=True)
class Arm:
    """One emitted-evidence arm: the fold chain, the maps it fits (every other piece raw) and the evaluator."""
    name: str
    chain: str
    maps: tuple[int, ...]
    logit: bool


_BASE: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("lo-first", "lo-first", (1, 2, 3)), ("hi-first", "hi-first", (0, 4, 5)),
    ("six-maps", "six-maps", (0, 1, 2, 3, 4, 5)), ("hi-first-marginal", "hi-first", (0,)),
    ("lo-first-marginal", "lo-first", (1,)))
ARMS: tuple[Arm, ...] = ((Arm("fallback", "fallback", (), False),)
                         + tuple(Arm(n, c, m, False) for n, c, m in _BASE)
                         + tuple(Arm(f"{n}/logit", c, m, True) for n, c, m in _BASE))
ARM_BY_NAME = {a.name: a for a in ARMS}
#: The JSON of record's (chain, weighting) for the arms that already ran — the reproduction checks.
REF_ARMS = {"fallback": ("fallback", "-"), "lo-first": ("lo-first", "w"), "hi-first": ("hi-first", "w"),
            "six-maps": ("six-maps", "w")}
LDPC_ARMS = ("fallback", "hi-first", "hi-first-marginal", "hi-first/logit", "hi-first-marginal/logit")
LDPC_PAIRS = tuple((a, "fallback") for a in LDPC_ARMS[1:]) + tuple((a, "hi-first") for a in LDPC_ARMS[2:])
METRICS = ("lo_any", "hi_bicm", "lo_bicm", "hi_any")


# ---------------------------------------------------------------- the evaluator and the arms

def logit_llrs(pmap: PavaMap, scores: np.ndarray) -> np.ndarray:
    """The map's own nodes interpolated linearly in logit(p) (flat beyond the end nodes)."""
    p = np.asarray(pmap.probability_nodes, np.float64)
    return np.interp(np.asarray(scores, np.float64), pmap.score_nodes, np.log(p) - np.log1p(-p))


def arm_outputs(ctx: Context, r: np.ndarray | None, n_cells: int, policy: str, arms: tuple[Arm, ...]
                ) -> dict[str, ChainOut]:
    """Each arm's emitted evidence on cells with raw scores r under the policy's 'w' pieces; zeros when the
    context is refused (as fit.apply_context)."""
    if ctx.refused is not None or r is None:
        z = np.zeros((n_cells, 6))
        return {a.name: ChainOut(z, np.zeros((n_cells, 3)), np.zeros(n_cells, bool)) for a in arms}
    stat = demap(r)
    src = ctx.pieces.get((policy, "w"), {})
    cache: dict[tuple[int, bool], np.ndarray] = {}
    out: dict[str, ChainOut] = {}
    for arm in arms:
        pieces: dict[int, np.ndarray | None] = {}
        for k in arm.maps:
            pm = src.get(k)
            if pm is None:
                pieces[k] = None
                continue
            if (k, arm.logit) not in cache:
                cache[(k, arm.logit)] = logit_llrs(pm, stat[:, k]) if arm.logit else pm.llrs(stat[:, k])
            pieces[k] = cache[(k, arm.logit)]
        out[arm.name] = chain_output(arm.chain, pieces, r, bool(ctx.collapse["lo"]), bool(ctx.collapse["hi"]))
    return out


# ---------------------------------------------------------------- page

@dataclass
class PageRep:
    k: int
    payload: np.ndarray
    payload_region: np.ndarray
    forms: dict[str, np.ndarray]            # "P-a|arm" / "P-b|arm" -> (N, 6)
    bind: dict[str, float]
    collapse: dict[str, Any]


def page_replicate(band: Band, k: int, params: Params, pops: tuple[str, ...], arms: tuple[Arm, ...]) -> PageRep:
    """regimes.page_fit's furniture, context and P-b folds (same rngs), evaluated for the given arms."""
    X = band.X["F"]
    fur = draw_furniture(regimes.rng_for("page_furniture", band.bc, 0, k), band, list(range(band.n_regions)))
    val = regimes.rng_for("valsplit", band.bc, 0, k).random(fur.held.size) < 1.0 / 3.0
    ctx = fit_context(X[fur.search], band.state[fur.search], X[fur.held], band.state[fur.held], fur.held_kind, val,
                      (PAGE_POLICY,), ("w",))
    n = fur.payload.size
    r = None if ctx.refused is not None or ctx.model is None else raw_scores(ctx.model, X[fur.payload])
    forms: dict[str, np.ndarray] = {}
    bind: dict[str, float] = {}
    for name, o in arm_outputs(ctx, r, n, PAGE_POLICY, arms).items():
        forms[f"P-a|{name}"], bind[f"P-a|{name}"] = o.forms, float(o.bind.mean())
    if "P-b" in pops:
        fb = {a.name: np.zeros((n, 6)) for a in arms}
        bb = {a.name: np.zeros(n, bool) for a in arms}
        for pos, fctx in regimes.fold_contexts(band, X, band.state, fur, k, params.K, params.workers, ("w",)):
            rf = (None if fctx.refused is not None or fctx.model is None
                  else raw_scores(fctx.model, X[fur.payload[pos]]))
            for name, o in arm_outputs(fctx, rf, pos.size, PAGE_POLICY, arms).items():
                fb[name][pos], bb[name][pos] = o.forms, o.bind
        for a in arms:
            forms[f"P-b|{a.name}"], bind[f"P-b|{a.name}"] = fb[a.name], float(bb[a.name].mean())
    return PageRep(k, fur.payload, fur.payload_region, forms, bind, dict(ctx.collapse))


def page_info_rows(band: Band, rep: PageRep, B: int, workers: int) -> list[dict[str, Any]]:
    """I per (population, arm, row) with the run's window bootstrap and the paired dI vs the fallback."""
    boot = WindowBootstrap(len(band.win_ids), B, regimes.rng_for("bootstrap", band.bc, 0, rep.k * 10))
    grp = band.win[rep.payload]
    pst = band.state[rep.payload]
    keys = list(rep.forms)

    def one(key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p, b = boot.info(rep.forms[key], pst, grp)
        return p, b, info_rows(rep.forms[key], pst)["hard_err"]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        got = dict(zip(keys, pool.map(one, keys)))
    rows = []
    for key in keys:
        pop, arm = key.split("|")
        p, b, err = got[key]
        pf, bf, _ = got[f"{pop}|fallback"]
        for i, row in enumerate(ROWS):
            rows.append({"bc": band.bc, "band": band.name, "population": pop, "arm": arm, "replicate": rep.k,
                         "policy": PAGE_POLICY, "form": row, "I": est(p[i], b[:, i]),
                         "dI_vs_fallback": est(p[i] - pf[i], b[:, i] - bf[:, i]), "hard_err": float(err[i]),
                         "bound_bind_frac": rep.bind[key], "n_cells": int(pst.size),
                         "n_windows": len(band.win_ids), "B": B})
    return rows


def page_repro(doc: dict[str, Any], rows: list[dict[str, Any]], bc: int) -> dict[str, Any]:
    """Max |diff| of I (est, lo, hi) of the arms that already ran against the JSON of record's rows."""
    idx = {(r["population"], r["chain"], r["weighting"], r["form"]): r["I"] for r in doc["page"]
           if r["bc"] == bc and r["features"] == "F" and r["replicate"] == 0 and r["policy"] == PAGE_POLICY
           and r["regime"] == "page"}
    diffs: dict[str, float] = {}
    missing = 0
    for r in rows:
        if r["arm"] not in REF_ARMS:
            continue
        chain, wt = REF_ARMS[r["arm"]]
        ref = idx.get((r["population"], chain, wt, r["form"]))
        if ref is None:
            missing += 1
            continue
        d = max(abs(r["I"][q] - ref[q]) for q in ("est", "lo", "hi"))
        key = f"{r['population']}|{r['arm']}"
        diffs[key] = max(diffs.get(key, 0.0), d)
    return {"bc": bc, "max_abs_diff": diffs, "missing": missing,
            "pass_4dp": bool(diffs) and missing == 0 and all(v < REPRO_TOL for v in diffs.values())}


# ---------------------------------------------------------------- cold start

@dataclass
class ColdOne:
    k: int
    origin: int
    region: int
    refused: bool
    collapse_any: bool
    I: dict[str, np.ndarray]                                   # "policy|arm" -> (8,)
    maps: dict[str, dict[str, Any]]
    ldpc: dict[str, dict[tuple[str, str, str], tuple[int, ...]]] | None


def cold_keys(arms: tuple[Arm, ...]) -> list[str]:
    return ["NEVER|fallback"] + [f"{pol}|{a.name}" for pol in COLD_POLICIES for a in arms if a.name != "fallback"]


def cold_one(band: Band, n: int, k: int, origins: list[tuple[int, ...]], params: Params, arms: tuple[Arm, ...],
             ldpc_keys: tuple[str, ...] | None) -> ColdOne:
    """regimes.cold_draw's furniture, context and LDPC trial (same rngs; users drawn for all three rungs, decoded
    at LDPC_RUNG only), evaluated for the given arms under both cold policies."""
    X = band.X["F"]
    rng = regimes.rng_for("cold", band.bc, n, k)
    oi = int(rng.integers(0, len(origins)))
    fur = draw_furniture(rng, band, origins[oi])
    val = regimes.rng_for("valsplit", band.bc, n, k).random(fur.held.size) < 1.0 / 3.0
    ctx = fit_context(X[fur.search], band.state[fur.search], X[fur.held], band.state[fur.held], fur.held_kind, val,
                      COLD_POLICIES, ("w",))
    pst = band.state[fur.payload]
    npay = fur.payload.size
    r = None if ctx.refused is not None or ctx.model is None else raw_scores(ctx.model, X[fur.payload])
    chained = tuple(a for a in arms if a.name != "fallback")
    outs = {"NEVER|fallback": arm_outputs(ctx, r, npay, COLD_POLICIES[0], (ARM_BY_NAME["fallback"],))["fallback"]}
    for pol in COLD_POLICIES:
        for name, o in arm_outputs(ctx, r, npay, pol, chained).items():
            outs[f"{pol}|{name}"] = o
    I = {key: info_rows(o.forms, pst)["I"] for key, o in outs.items()}
    maps: dict[str, dict[str, Any]] = {}
    if r is not None:
        stat, fbf = demap(r), demap(bound_triple(r)[0])
        for m, spec in enumerate(MAP_SPECS):
            member = np.isin(pst, spec.states)
            pm = ctx.maps.get(("H", "w", m))
            cols = {"fallback": fbf[:, m], "linear": fbf[:, m] if pm is None else pm.llrs(stat[:, m]),
                    "logit": fbf[:, m] if pm is None else logit_llrs(pm, stat[:, m])}
            vals: dict[str, Any] = {}
            for label, col in cols.items():
                f = np.zeros((pst.size, 6))
                f[:, m] = col
                vals[label] = float(info_rows(f[member], pst[member])["I"][m])
            maps[spec.name] = {**vals, "fitted": pm is not None, "q_d1": bool(ctx.diag[m].qualified.get("H"))}
    res = None
    if ldpc_keys is not None:
        trng = regimes.rng_for("ldpc_cold", band.bc, n, k)
        cand = np.flatnonzero(fur.payload_region == 0)
        pos, st, ov = draw_positions(trng, cand, pst[cand])
        tr = Trial(key=(MASTER_SEED, REGIME["ldpc_cold"], band.bc, n, k), state=st, users=draw_users(trng, RUNGS),
                   arms={key: outs[key].forms[pos] for key in ldpc_keys}, overflow=ov, rungs=(LDPC_RUNG,))
        res = run_trial(tr, params.max_iters, params.retry_iters, params.alpha, False)
    return ColdOne(k, oi, int(origins[oi][0]), ctx.refused is not None, bool(ctx.collapse["lo"] or ctx.collapse["hi"]),
                   I, maps, res)


def run_cold_draws(band: Band, n: int, D: int, params: Params, arms: tuple[Arm, ...],
                   ldpc_keys: tuple[str, ...] | None = None, T_ldpc: int = 0) -> tuple[list[ColdOne], int]:
    origins = cluster_origins(band, n, COLD_SHAPES)
    if not origins:
        return [], 0

    def task(k: int) -> ColdOne:
        return cold_one(band, n, k, origins, params, arms, ldpc_keys if k < T_ldpc else None)
    with ThreadPoolExecutor(max_workers=max(1, params.workers)) as pool:
        draws = list(pool.map(task, range(max(D, T_ldpc))))
    return draws, len(origins)


def cold_summary(band: Band, n: int, draws: list[ColdOne], n_origins: int, B: int) -> dict[str, Any]:
    """Chain rows (I and dI vs fallback) and per-map rows (dI linear / logit vs the raw piece), bootstrapped over
    cluster origins with the run's count matrix."""
    boot = WindowBootstrap(n_origins, B, regimes.rng_for("bootstrap", band.bc, n, 1000))
    grp = np.array([d.origin for d in draws])
    fb = np.stack([d.I["NEVER|fallback"] for d in draws])
    base = {"bc": band.bc, "band": band.name, "n": n, "n_draws": len(draws), "n_origins": n_origins, "B": B}
    rows = []
    for key in draws[0].I:
        pol, arm = key.split("|")
        Ia = np.stack([d.I[key] for d in draws])
        for i, row in enumerate(ROWS):
            p, b = boot.mean(Ia[:, i], grp)
            pd, bd = boot.mean(Ia[:, i] - fb[:, i], grp)
            rows.append({**base, "policy": pol, "arm": arm, "form": row, "I": est(p, b),
                         "dI_vs_fallback": est(pd, bd)})
    maprows = []
    for spec in MAP_SPECS:
        sel = [d for d in draws if spec.name in d.maps]
        if not sel:
            continue
        g2 = np.array([d.origin for d in sel])
        v = {lab: np.array([d.maps[spec.name][lab] for d in sel]) for lab in ("fallback", "linear", "logit")}
        out = {**base, "map": spec.name, "n_draws": len(sel), "policy": "ALWAYS", "weighting": "w",
               "fitted_frac": float(np.mean([d.maps[spec.name]["fitted"] for d in sel])),
               "q_d1_frac": float(np.mean([d.maps[spec.name]["q_d1"] for d in sel])),
               "I_fallback": float(v["fallback"].mean()), "I_linear": float(v["linear"].mean()),
               "I_logit": float(v["logit"].mean())}
        for name, val in (("dI_linear", v["linear"] - v["fallback"]), ("dI_logit", v["logit"] - v["fallback"]),
                          ("logit_minus_linear", v["logit"] - v["linear"])):
            out[name] = est(*boot.mean(val, g2))
        maprows.append(out)
    return {"chain": rows, "maps": maprows, "refused_frac": float(np.mean([d.refused for d in draws])),
            "collapse_frac": float(np.mean([d.collapse_any for d in draws]))}


def cold_repro(doc: dict[str, Any], summ: dict[str, Any], bc: int, n: int) -> dict[str, Any]:
    """The run's cold rows (D = 400) against this module's on the same draws: chain I / dI and per-map dI."""
    ch = {(r["chain"], r["weighting"], r["policy"], r["form"]): r for r in doc["coldstart"]
          if r["bc"] == bc and r["n"] == n and r["features"] == "F" and r["regime"] == "cold" and r.get("map") is None
          and r.get("I") is not None}
    mp = {r["map"]: r for r in doc["coldstart"] if r["bc"] == bc and r["n"] == n and r["features"] == "F"
          and r["regime"] == "cold" and r.get("map") is not None}
    diffs: dict[str, float] = {}
    for r in summ["chain"]:
        arm = r["arm"]
        if arm not in REF_ARMS:
            continue
        chain, wt = REF_ARMS[arm]
        ref = ch.get((chain, wt, r["policy"], r["form"]))
        if ref is None:
            continue
        d = max(max(abs(r["I"][q] - ref["I"][q]) for q in ("est", "lo", "hi")),
                max(abs(r["dI_vs_fallback"][q] - ref["dI_vs_fallback"][q]) for q in ("est", "lo", "hi")))
        key = f"{r['policy']}|{arm}"
        diffs[key] = max(diffs.get(key, 0.0), d)
    for r in summ["maps"]:
        ref = mp.get(r["map"])
        if ref is None:
            continue
        diffs[f"map|{r['map']}"] = max(abs(r["dI_linear"][q] - ref["dI"][q]) for q in ("est", "lo", "hi"))
    return {"bc": bc, "n": n, "max_abs_diff": diffs, "n_compared": len(diffs),
            "pass_4dp": bool(diffs) and all(v < REPRO_TOL for v in diffs.values())}


# ---------------------------------------------------------------- LDPC

def cluster_bootstrap(clusters: np.ndarray, B: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, int]:
    """(cluster index per trial, (B, G) multinomial resample counts over the G distinct clusters, G)."""
    uniq, inv = np.unique(clusters, return_inverse=True)
    G = int(uniq.size)
    return inv.ravel(), rng.multinomial(G, np.full(G, 1.0 / G), size=B).astype(np.float64), G


def cluster_mean(values: np.ndarray, inv: np.ndarray, counts: np.ndarray) -> tuple[float, np.ndarray]:
    G = counts.shape[1]
    s = np.bincount(inv, weights=values.astype(np.float64), minlength=G)
    m = np.bincount(inv, minlength=G).astype(np.float64)
    return float(values.mean()), (counts @ s) / np.maximum(counts @ m, 1e-300)


def ldpc_stats(metrics: dict[str, dict[str, np.ndarray]], clusters: np.ndarray, B: int, rng: np.random.Generator,
               base: dict[str, Any]) -> dict[str, Any]:
    """Per arm and metric: k / T, Wilson, region-cluster CI; per pair: delta successes with its cluster CI and
    the exact McNemar test."""
    inv, counts, G = cluster_bootstrap(clusters, B, rng)
    arms, pairs = [], []
    for arm, ms in metrics.items():
        for metric, v in ms.items():
            T = int(v.size)
            k = int(v.sum())
            wl = wilson(k, T)
            p, b = cluster_mean(v, inv, counts)
            lo, hi = np.percentile(b, [2.5, 97.5])
            arms.append({**base, "arm": arm, "metric": metric, "successes": k, "T": T, "rate": p,
                         "wilson": {"lo": wl[0], "hi": wl[1]}, "cluster_ci": {"lo": float(lo), "hi": float(hi)},
                         "n_clusters": G, "B": B})
    for a, ref in LDPC_PAIRS:
        if a not in metrics or ref not in metrics:
            continue
        for metric in metrics[a]:
            x, y = metrics[a][metric].astype(bool), metrics[ref][metric].astype(bool)
            T = int(x.size)
            p, b = cluster_mean(x.astype(np.float64) - y.astype(np.float64), inv, counts)
            lo, hi = np.percentile(b, [2.5, 97.5])
            pairs.append({**base, "arm": a, "vs": ref, "metric": metric, "T": T,
                          "delta_successes": int(x.sum()) - int(y.sum()),
                          "delta_successes_ci": {"lo": float(lo * T), "hi": float(hi * T)},
                          "delta_rate": {"est": p, "lo": float(lo), "hi": float(hi)},
                          "discordant": {"arm_only": int(np.sum(x & ~y)), "ref_only": int(np.sum(~x & y))},
                          "mcnemar_p": mcnemar_exact(x, y), "n_clusters": G, "B": B})
    return {"arms": arms, "pairs": pairs}


def as_bool(d: dict[tuple[str, str, str], list[int]]) -> dict[tuple[str, str, str], np.ndarray]:
    return {kk: np.asarray(v, bool) for kk, v in d.items()}


def stream_metrics(d: dict[tuple[str, str, str], np.ndarray]) -> dict[str, np.ndarray]:
    h, l_ = any_stage(d, LDPC_RUNG, LDPC_RUNG)
    return {"lo_any": l_, "hi_bicm": d[("hi", "bicm", LDPC_RUNG)], "lo_bicm": d[("lo", "bicm", LDPC_RUNG)],
            "hi_any": h}


def ldpc_index(doc: dict[str, Any], bc: int) -> dict[tuple[Any, ...], dict[str, Any]]:
    return {(r["regime"], r["population"], r.get("n"), r["chain"], r["weighting"], r["policy"], r["stream"],
             r["mode"]): r for r in doc["ldpc"] if r["bc"] == bc and r.get("features") == "F"
            and r.get("rung") == LDPC_RUNG and r["regime"] in ("page", "cold")}


def bits_equal(ref: dict[str, Any] | None, mine: np.ndarray) -> dict[str, Any]:
    if ref is None:
        return {"compared": 0, "equal": None}
    m = min(int(ref["T"]), int(mine.size))
    theirs = unpack_bits(ref["outcomes"], int(ref["T"]))[:m]
    return {"compared": m, "equal": bool(np.array_equal(theirs, mine[:m].astype(bool))),
            "theirs": int(theirs.sum()), "mine": int(mine[:m].sum())}


def ldpc_page(band: Band, params: Params, T: int, doc: dict[str, Any], log: Any) -> dict[str, Any]:
    arms = tuple(ARM_BY_NAME[a] for a in LDPC_ARMS)
    fits = []
    for k in range(params.R):
        rep = page_replicate(band, k, params, ("P-a", "P-b"), arms)
        fits.append(regimes.PageFit(rep.payload, rep.payload_region, rep.forms, {}, rep.bind, rep.collapse, {}, None))
        log(f"  ldpc page bc{band.bc} replicate {k} fitted")
    trials = (replace(t, rungs=(LDPC_RUNG,)) for t in regimes.page_trials(band, fits, T, RUNGS))
    outc: dict[str, dict[tuple[str, str, str], list[int]]] = {}
    fa: dict[str, int] = {}
    regions: list[int] = []
    for trial, res in run_trials(trials, params.workers, max_iters=params.max_iters, retry_iters=params.retry_iters,
                                 alpha=params.alpha, retry=False):
        t = int(trial.key[-1])
        pf = fits[t % len(fits)]
        regions.append(int(regimes.rng_for("ldpc_page", band.bc, 0, t).integers(0, int(pf.payload_region.max()) + 1)))
        for arm, d in res.items():
            for kk, v in d.items():
                outc.setdefault(arm, {}).setdefault(kk, []).append(int(v[0]))
                fa[arm] = fa.get(arm, 0) + int(v[1])
    metrics: dict[str, dict[str, np.ndarray]] = {}
    for arm in LDPC_ARMS:
        a, b = as_bool(outc[f"P-a|{arm}"]), as_bool(outc[f"P-b|{arm}"])
        ma, mb = stream_metrics(a), stream_metrics(b)
        metrics[arm] = {m: ma[m] | mb[m] for m in METRICS}
        metrics[arm]["lo_any_P-a"], metrics[arm]["lo_any_P-b"] = ma["lo_any"], mb["lo_any"]
    clusters = np.asarray(regions)
    stats = ldpc_stats(metrics, clusters, params.B,
                       np.random.default_rng([MASTER_SEED, REGIME["bootstrap"], band.bc, 20_000]),
                       {"bc": band.bc, "regime": "page-final", "rung": LDPC_RUNG, "policy": PAGE_POLICY})
    idx = ldpc_index(doc, band.bc)
    repro = {}
    for arm in ("fallback", "hi-first"):
        chain, wt = REF_ARMS[arm]
        for pop in ("P-a", "P-b"):
            d = as_bool(outc[f"{pop}|{arm}"])
            for st in ("hi", "lo"):
                for mode in ("bicm", "cond"):
                    ref = idx.get(("page", pop, None, chain, wt, PAGE_POLICY, st, mode))
                    repro[f"{pop}|{arm}|{st}|{mode}"] = bits_equal(ref, d[(st, mode, LDPC_RUNG)])
        ref = idx.get(("page", "final", None, chain, wt, PAGE_POLICY, "lo", "any"))
        repro[f"final|{arm}|lo|any"] = bits_equal(ref, metrics[arm]["lo_any"])
    return {"stats": stats, "repro": repro, "false_accepts": fa, "T": T, "R": params.R,
            "regions_used": int(np.unique(clusters).size), "n_regions": band.n_regions,
            "outcomes": {arm: {m: v.astype(int).tolist() for m, v in ms.items()} for arm, ms in metrics.items()},
            "trial_region": clusters.tolist()}


def ldpc_cold(band: Band, params: Params, T: int, doc: dict[str, Any], log: Any) -> dict[str, Any]:
    arms = tuple(ARM_BY_NAME[a] for a in LDPC_ARMS)
    keys = tuple(k for k in cold_keys(arms))
    draws, n_orig = run_cold_draws(band, COLD_LDPC_N, 0, params, arms, keys, T)
    log(f"  ldpc cold bc{band.bc} n={COLD_LDPC_N}: {len(draws)} draws, {sum(d.refused for d in draws)} refused")
    metrics: dict[str, dict[str, np.ndarray]] = {}
    fa: dict[str, int] = {}
    for key in keys:
        d = {kk: np.array([dr.ldpc[key][kk][0] for dr in draws], bool) for kk in draws[0].ldpc[key]}
        fa[key] = int(sum(dr.ldpc[key][kk][1] for dr in draws for kk in dr.ldpc[key]))
        metrics[key] = stream_metrics(d)
    clusters = np.array([d.region for d in draws])
    out_stats: dict[str, Any] = {"arms": [], "pairs": []}
    for pol in COLD_POLICIES:
        sub = {"fallback": metrics["NEVER|fallback"]}
        sub.update({a: metrics[f"{pol}|{a}"] for a in LDPC_ARMS[1:]})
        st = ldpc_stats(sub, clusters, params.B,
                        np.random.default_rng([MASTER_SEED, REGIME["bootstrap"], band.bc, 20_002]),
                        {"bc": band.bc, "regime": "cold", "n": COLD_LDPC_N, "rung": LDPC_RUNG, "policy": pol})
        out_stats["arms"] += [r for r in st["arms"] if pol == COLD_POLICIES[0] or r["arm"] != "fallback"]
        out_stats["pairs"] += st["pairs"]
    idx = ldpc_index(doc, band.bc)
    repro = {}
    for key, (chain, wt, pol) in (("NEVER|fallback", ("fallback", "-", "NEVER")),
                                  ("D1-DEFAULT|hi-first", ("hi-first", "w", "D1-DEFAULT")),
                                  ("ALWAYS|hi-first", ("hi-first", "w", "ALWAYS"))):
        for st in ("hi", "lo"):
            for mode in ("bicm", "cond"):
                ref = idx.get(("cold", "cold", COLD_LDPC_N, chain, wt, pol, st, mode))
                mine = np.array([d.ldpc[key][(st, mode, LDPC_RUNG)][0] for d in draws], bool)
                repro[f"{key}|{st}|{mode}"] = bits_equal(ref, mine)
    return {"stats": out_stats, "repro": repro, "false_accepts": fa, "T": T, "n_origins": n_orig,
            "regions_used": int(np.unique(clusters).size),
            "outcomes": {k: {m: v.astype(int).tolist() for m, v in ms.items()} for k, ms in metrics.items()},
            "trial_region": clusters.tolist()}


# ---------------------------------------------------------------- stages

def load_doc(art: Path) -> dict[str, Any]:
    return json.loads((art / SOURCE_NAME).read_text())


def check_params(doc: dict[str, Any], params: Params) -> None:
    run_p = {k: v for k, v in doc["meta"]["params"].items() if k in ("R", "K", "B", "max_iters", "retry_iters",
                                                                       "alpha")}
    mine = {k: getattr(params, k) for k in run_p}
    if run_p != mine:
        raise SystemExit(f"parameters differ from the run of record: {run_p} vs {mine}")


def stage_page(art: Path, params: Params, bcs: tuple[int, ...], log: Any) -> dict[str, Any]:
    doc = load_doc(art)
    check_params(doc, params)
    bands = load_bands(art, bcs)
    rows, repro = [], []
    for bc in bcs:
        t0 = time.time()
        rep = page_replicate(bands[bc], 0, params, ("P-a", "P-b"), ARMS)
        r = page_info_rows(bands[bc], rep, params.B, params.workers)
        rows += r
        repro.append(page_repro(doc, r, bc))
        log(f"  page bc{bc} {bands[bc].name}: {len(r)} rows, repro {repro[-1]['pass_4dp']} "
            f"({max(repro[-1]['max_abs_diff'].values()):.2e}) in {time.time() - t0:.0f} s")
    return {"page": rows, "repro": repro}


def stage_c3(art: Path, params: Params, log: Any) -> dict[str, Any]:
    doc = load_doc(art)
    check_params(doc, params)
    band = load_bands(art, (C3_BC,))[C3_BC]
    rep = page_replicate(band, 0, params, ("P-a",), ARMS)
    rows = page_info_rows(band, rep, params.B, params.workers)
    repro = page_repro(doc, rows, C3_BC)
    log(f"  c3 bc{C3_BC} {band.name}: repro {repro['pass_4dp']}")
    return {"page": rows, "repro": repro}


def stage_cold(art: Path, params: Params, bcs: tuple[int, ...], sizes: tuple[int, ...], D: int,
               log: Any) -> dict[str, Any]:
    bands = load_bands(art, bcs)
    out: dict[str, Any] = {"chain": [], "maps": [], "meta": []}
    for bc in bcs:
        for n in sizes:
            t0 = time.time()
            draws, n_orig = run_cold_draws(bands[bc], n, D, params, ARMS)
            if not draws:
                out["meta"].append({"bc": bc, "n": n, "skipped": "no cluster fits"})
                continue
            s = cold_summary(bands[bc], n, draws, n_orig, params.B)
            out["chain"] += s["chain"]
            out["maps"] += s["maps"]
            out["meta"].append({"bc": bc, "n": n, "n_draws": len(draws), "n_origins": n_orig,
                                "refused_frac": s["refused_frac"], "collapse_frac": s["collapse_frac"],
                                "wall_s": time.time() - t0})
            log(f"  cold bc{bc} n={n}: {len(draws)} draws, refused {s['refused_frac']:.3f}, "
                f"collapse {s['collapse_frac']:.3f}, {time.time() - t0:.0f} s")
    return out


def stage_repro_cold(art: Path, params: Params, log: Any, bc: int = 1, n: int = 1, D: int = 400) -> dict[str, Any]:
    doc = load_doc(art)
    band = load_bands(art, (bc,))[bc]
    draws, n_orig = run_cold_draws(band, n, D, params, ARMS)
    s = cold_summary(band, n, draws, n_orig, params.B)
    rep = cold_repro(doc, s, bc, n)
    log(f"  repro-cold bc{bc} n={n} D={D}: pass {rep['pass_4dp']} over {rep['n_compared']} "
        f"(max {max(rep['max_abs_diff'].values()):.2e})")
    return rep


def stage_ldpc(art: Path, params: Params, T: int, log: Any) -> dict[str, Any]:
    doc = load_doc(art)
    check_params(doc, params)
    band = load_bands(art, (LDPC_BC,))[LDPC_BC]
    t0 = time.time()
    page = ldpc_page(band, params, T, doc, log)
    t1 = time.time()
    log(f"  ldpc page-final: {t1 - t0:.0f} s; repro {[v['equal'] for v in page['repro'].values()]}")
    cold = ldpc_cold(band, params, T, doc, log)
    log(f"  ldpc cold n={COLD_LDPC_N}: {time.time() - t1:.0f} s; repro {[v['equal'] for v in cold['repro'].values()]}")
    return {"page_final": page, "cold": cold, "wall_s": {"page": t1 - t0, "cold": time.time() - t1}}


# ---------------------------------------------------------------- report

def fe(e: dict[str, float] | None, d: int = 4) -> str:
    if e is None or e.get("est") is None:
        return "-"
    return f"{e['est']:.{d}f} [{e['lo']:.{d}f}, {e['hi']:.{d}f}]"


def fs(e: dict[str, float] | None, d: int = 4) -> str:
    if e is None or e.get("est") is None:
        return "-"
    return f"{e['est']:+.{d}f} [{e['lo']:+.{d}f}, {e['hi']:+.{d}f}]"


def md_page(rows: list[dict[str, Any]], title: str, delta: bool) -> list[str]:
    key = "dI_vs_fallback" if delta else "I"
    out = [title, "", "| arm | pop | " + " | ".join(FORMS6) + " | bind | n |",
           "|---|---|" + "---|" * (len(FORMS6) + 2)]
    by: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in rows:
        by.setdefault((r["arm"], r["population"]), {})[r["form"]] = r
    for a in ARMS:
        for pop in ("P-a", "P-b"):
            d = by.get((a.name, pop))
            if not d or (delta and a.name == "fallback"):
                continue
            cells = [(fs if delta else fe)(d[f][key]) for f in FORMS6]
            any_r = d[FORMS6[0]]
            out.append(f"| {a.name} | {pop} | " + " | ".join(cells) + f" | {any_r['bound_bind_frac']:.3f} | "
                       f"{any_r['n_cells']} |")
    return out + [""]


def md_ldpc(st: dict[str, Any], label: str) -> list[str]:
    out = [f"{label} — per arm (k/T, Wilson, region-cluster bootstrap)", "",
           "| policy | arm | metric | k/T | Wilson | cluster CI | clusters |", "|---|---|---|---|---|---|---|"]
    for r in st["arms"]:
        out.append(f"| {r['policy']} | {r['arm']} | {r['metric']} | {r['successes']}/{r['T']} | "
                   f"[{r['wilson']['lo']:.3f}, {r['wilson']['hi']:.3f}] | "
                   f"[{r['cluster_ci']['lo']:.3f}, {r['cluster_ci']['hi']:.3f}] | {r['n_clusters']} |")
    out += ["", f"{label} — paired differences (arm minus reference, same trials)", "",
            "| policy | arm | vs | metric | delta k | cluster CI (k) | arm-only / ref-only | McNemar p |",
            "|---|---|---|---|---|---|---|---|"]
    for r in st["pairs"]:
        out.append(f"| {r['policy']} | {r['arm']} | {r['vs']} | {r['metric']} | {r['delta_successes']:+d} | "
                   f"[{r['delta_successes_ci']['lo']:+.1f}, {r['delta_successes_ci']['hi']:+.1f}] | "
                   f"{r['discordant']['arm_only']} / {r['discordant']['ref_only']} | {r['mcnemar_p']:.4f} |")
    return out + [""]


def stage_report(out_dir: Path, source_json: Path) -> dict[str, Any]:
    parts = {p.stem: json.loads(p.read_text()) for p in sorted((out_dir / "parts").glob("*.json"))}
    doc: dict[str, Any] = {"meta": {"source_json": str(source_json), "code_sha256": code_sha256(),
                                    "params": asdict(Params()), "arms": [asdict(a) for a in ARMS],
                                    "ldpc_arms": list(LDPC_ARMS), "ldpc_rung": LDPC_RUNG,
                                    "cold_policies": list(COLD_POLICIES), "page_policy": PAGE_POLICY},
                           **parts}
    write_json(out_dir / "followup.json", doc)
    md = ["# R11 follow-up — marginal-only chains and the logit evaluator", "",
          f"Source of record: {source_json}. Arms: " + ", ".join(a.name for a in ARMS) + ".", ""]
    if "page" in parts:
        md += ["## Reproduction (page, against the JSON of record; 4 dp = |diff| < 5e-5)", ""]
        for r in parts["page"]["repro"]:
            md.append(f"- bc{r['bc']}: pass {r['pass_4dp']}, max |diff| "
                      + ", ".join(f"{k} {v:.1e}" for k, v in r["max_abs_diff"].items()))
        md.append("")
        for bc in sorted({r["bc"] for r in parts["page"]["page"]}):
            rows = [r for r in parts["page"]["page"] if r["bc"] == bc]
            name = rows[0]["band"]
            md += md_page(rows, f"## Page information bc{bc} ({name}), replicate 0, D1-DEFAULT — I [95 % window CI]",
                          False)
            md += md_page(rows, f"### bc{bc} ({name}) — dI vs fallback (paired, same count matrix)", True)
    if "c3" in parts:
        r = parts["c3"]
        md += [f"## c3 must-not-lose check — A1@2400 (bc{C3_BC}) P-a; repro pass {r['repro']['pass_4dp']}", "",
               "| arm | I_hi | dI_hi vs fallback | I_lo | dI_lo vs fallback |", "|---|---|---|---|---|"]
        by = {(x["arm"], x["form"]): x for x in r["page"]}
        for a in ARMS:
            h, lo = by[(a.name, "hi")], by[(a.name, "lo")]
            md.append(f"| {a.name} | {fe(h['I'])} | {fs(h['dI_vs_fallback'])} | {fe(lo['I'])} | "
                      f"{fs(lo['dI_vs_fallback'])} |")
        md.append("")
    if "repro-cold" in parts:
        r = parts["repro-cold"]
        md += [f"## Cold reproduction (bc{r['bc']} n={r['n']}, the run's 400 draws): pass {r['pass_4dp']} over "
               f"{r['n_compared']} rows, max |diff| {max(r['max_abs_diff'].values()):.1e}", ""]
    if "cold" in parts:
        c = parts["cold"]
        for bc in sorted({r["bc"] for r in c["chain"]}):
            rows = [r for r in c["chain"] if r["bc"] == bc]
            md += [f"## Cold chain information bc{bc} ({rows[0]['band']}) — I and dI vs fallback [95 % origin CI]",
                   "", "| n | policy | arm | I_hi | dI_hi | I_lo | dI_lo | draws |",
                   "|---|---|---|---|---|---|---|---|"]
            by = {(r["n"], r["policy"], r["arm"], r["form"]): r for r in rows}
            for n in sorted({r["n"] for r in rows}):
                for pol in ("NEVER",) + COLD_POLICIES:
                    for a in ARMS:
                        h, lo = by.get((n, pol, a.name, "hi")), by.get((n, pol, a.name, "lo"))
                        if h is None:
                            continue
                        md.append(f"| {n} | {pol} | {a.name} | {fe(h['I'])} | {fs(h['dI_vs_fallback'])} | "
                                  f"{fe(lo['I'])} | {fs(lo['dI_vs_fallback'])} | {h['n_draws']} |")
            md.append("")
            mrows = [r for r in c["maps"] if r["bc"] == bc]
            md += [f"### bc{bc} per-map dI vs the raw piece (ALWAYS map on H, 'w')", "",
                   "| n | map | fitted | dI linear | dI logit | logit - linear | draws |",
                   "|---|---|---|---|---|---|---|"]
            for r in mrows:
                md.append(f"| {r['n']} | {r['map']} | {r['fitted_frac']:.3f} | {fs(r['dI_linear'])} | "
                          f"{fs(r['dI_logit'])} | {fs(r['logit_minus_linear'])} | {r['n_draws']} |")
            md.append("")
    if "ldpc" in parts:
        p = parts["ldpc"]
        for name, label in (("page_final", f"## LDPC page-final, U12@2400 (bc{LDPC_BC}) {LDPC_RUNG}, "
                                           f"T = {p['page_final']['T']}"),
                            ("cold", f"## LDPC cold n = {COLD_LDPC_N}, U12@2400 (bc{LDPC_BC}) {LDPC_RUNG}, "
                                     f"T = {p['cold']['T']}")):
            md += [label, "", "Reproduction (bit for bit vs the run's packed outcomes): "
                   + ", ".join(f"{k}: {v['equal']} ({v['compared']})" for k, v in p[name]["repro"].items()),
                   f"; false accepts: {sum(p[name]['false_accepts'].values())}; distinct regions "
                   f"{p[name]['regions_used']}", ""]
            md += md_ldpc(p[name]["stats"], label.lstrip("# "))
    (out_dir / "followup.md").write_text("\n".join(md))
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=("page", "c3", "cold", "repro-cold", "ldpc", "report"))
    ap.add_argument("--art", required=True,
                    help="the R11 run's work directory: cells-<capture>.npz and cmy-calibration-diagnostic.json")
    ap.add_argument("--out", default=None, help=f"output directory (default <art>/{OUT_NAME})")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--bcs", default=",".join(str(b) for b in DECISION_BCS))
    ap.add_argument("--cold-sizes", default=",".join(str(n) for n in COLD_SIZES))
    ap.add_argument("--draws", type=int, default=150, help="cold information draws per (bc, n)")
    ap.add_argument("--trials", type=int, default=200, help="LDPC trials (page-final and cold n = 2)")
    args = ap.parse_args()
    art = Path(args.art)
    out_dir = Path(args.out) if args.out else art / OUT_NAME
    (out_dir / "parts").mkdir(parents=True, exist_ok=True)
    params = replace(Params(), workers=args.workers)
    bcs = tuple(int(b) for b in args.bcs.split(","))
    t0 = time.time()
    log = print
    if args.stage == "report":
        stage_report(out_dir, art / SOURCE_NAME)
        log(f"wrote {out_dir / 'followup.json'} and followup.md")
        return
    if args.stage == "page":
        res = stage_page(art, params, bcs, log)
    elif args.stage == "c3":
        res = stage_c3(art, params, log)
    elif args.stage == "cold":
        res = stage_cold(art, params, bcs, tuple(int(n) for n in args.cold_sizes.split(",")), args.draws, log)
    elif args.stage == "repro-cold":
        res = stage_repro_cold(art, params, log)
    else:
        res = stage_ldpc(art, params, args.trials, log)
    res["_wall_s"] = time.time() - t0
    res["_args"] = {**vars(args), "out": str(out_dir)}
    write_json(out_dir / "parts" / f"{args.stage}.json", jsonable(res))
    log(f"stage {args.stage} done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
