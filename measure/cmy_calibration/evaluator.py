"""R31 — the PAVA evaluator measured HELD-OUT: four evaluators over the same fitted blocks, on the R11 paper extracts.

What: the hi-first chain's three maps (L_hi, L_{lo|hi=0}, L_{lo|hi=1}) fitted once per calibration context, then
read through four evaluators that share the training population, the PAVA blocks and the block probabilities:
  raw              the bounded raw score triple (every piece the per-map fallback; the fold of three raw pieces is
                   the identity, so this is the bounded raw triple itself);
  centroid-linear  the block centroids (score-weighted mean of a block's training scores) interpolated linearly in
                   probability (PavaMap.llrs, logit_interpolation False: cmy8's and A4b's evaluator);
  centroid-logit   the same nodes interpolated linearly in logit(p) (PavaMap.logit_interpolation True: the cmy
                   chain as built, color_chain.fit_chain_map);
  block-edge       nodes at each block's FIRST and LAST training score, both at the block's probability (one node
                   when they coincide), joined linearly in logit, flat beyond the end nodes; E017.6's zero node
                   inserted under the same test as fit_component_pava, on these nodes (the A8 refuter's probe
                   construction, scratchpad a8probe/edges.py, restated).
Blocks: the unique training scores are the groups (tied scores never split); a group whose value is <= the block
before it merges into it (PAV, `values[-2] >= values[-1]`), so block values rise strictly and a block's last score
is strictly below the next block's first; the probability clip is [1/(n+2), 1 - 1/(n+2)], n the map's population.
`pav_blocks` repeats the fitter's arithmetic and asserts its centroid nodes equal the fitted PavaMap's bit for bit.
Measurement (`--stage paper`): per band-capture of config.BAND_CAPTURES (bc 0-9) the R11 page furniture (P-a:
QDA on the search half, maps on the held-out half H, policy D1-DEFAULT, state-balanced 'w'), replicates k < 3,
EVALUATED ON THE PAYLOAD CELLS (never in a fit); and the cold start, n in {1, 2, 8} emulated tiles, D draws of the
run's own machinery.  Per evaluator: information hi / lo / lo|hi (estimators.info_rows, state-balanced, unclamped),
log-loss, sign flips against the truth (L = 0 counted apart), the signed margin (2b - 1) L at p1 / p5, and the
paired dI against centroid-logit with the run's window (page) or cluster-origin (cold) bootstrap.
Why: R31 (CMY-RECEIVER-PLAN §5, A8's as-built paragraph) — the owner's evaluator ruling; the 2026-10-12 review
asked for the block-edge change re-measured held-out on the separable synthetic case and on paper extracts.
evaluator_lanes.py measures the same four on the receiver's own lane (sim pages, e044 sheets A and B).
Inputs: --art = the R11 run's work directory (its cells-<capture>.npz), by flag; --out the artefact directory.

    PYTHONPATH=src:. env/bin/python -m measure.cmy_calibration.evaluator --stage paper \\
        --art scratch/cmy-calibration-20261010 \\
        --out scratch/cmy_calibration/evaluator-2026-10-12
    ... --stage report --out <same>        (evaluator-paper.json + evaluator_lanes' parts -> evaluator.md)
"""
from __future__ import annotations

import argparse
import json
import resource
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from holo.receiver.plugins.color_model import PavaMap
from measure.cmy_calibration import regimes
from measure.cmy_calibration.chains import HI, LO, MAP_SPECS, chain_output, demap, map_population, raw_scores
from measure.cmy_calibration.config import BAND_CAPTURES, COLD_SHAPES, Params
from measure.cmy_calibration.estimators import WindowBootstrap, est, info_rows
from measure.cmy_calibration.fit import Band, cluster_origins, draw_furniture, fit_context
from measure.cmy_calibration.run import load_bands, write_json

EVALUATORS = ("raw", "centroid-linear", "centroid-logit", "block-edge")
REFERENCE = "centroid-logit"
HI_FIRST = (0, 4, 5)
POLICY = "D1-DEFAULT"
PAGE_REPLICATES = 3
COLD_SIZES = (1, 2, 8)
COLD_DRAWS = 150
B_BOOT = 2000
#: info_rows' rows reported: the hi marginal, the lo marginal, lo given the true hi (the chain's second link).
INFO_ROWS = {"hi": 0, "lo": 1, "lo|hi": 7}
DEFAULT_OUT = Path("scratch/cmy_calibration/evaluator-2026-10-12")


def peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


# ---------------------------------------------------------------- blocks and the four evaluators

@dataclass(frozen=True)
class Blocks:
    """One fitted PAVA: per block its probability (unclipped), first and last training score, weight, score sum."""
    values: np.ndarray
    first: np.ndarray
    last: np.ndarray
    weights: np.ndarray
    score_sums: np.ndarray
    n_labels: int


def stratified_groups(scores: np.ndarray, labels: np.ndarray, strata: np.ndarray
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """chains.fit_stratified_pava's group weights, its arithmetic verbatim: (unique scores, pos, neg, n)."""
    raw = np.asarray(scores, np.float64).ravel()
    lab = np.asarray(labels, np.int64).ravel()
    st = np.asarray(strata, np.int64).ravel()
    order = np.argsort(raw, kind="stable")
    ss, sl, sst = raw[order], lab[order], st[order]
    unique, starts = np.unique(ss, return_index=True)
    total = float(lab.size)
    sums = {0: np.zeros(unique.size), 1: np.zeros(unique.size)}
    for cls in (0, 1):
        in_class = sl == cls
        present = np.unique(sst[in_class])
        k = float(present.size)
        for s in present:
            member = in_class & (sst == s)
            counts = np.add.reduceat(member.astype(np.float64), starts)
            sums[cls] = sums[cls] + counts * total / (2.0 * k * float(member.sum()))
    return unique, sums[1], sums[0], int(lab.size)


def weighted_groups(scores: np.ndarray, labels: np.ndarray, weights: np.ndarray
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """color_model.fit_component_pava's weighted branch (the cmy chain's), its arithmetic verbatim."""
    from holo.receiver.plugins.color_model import _within_class_weights
    raw = np.asarray(scores, np.float64).ravel()
    lab = np.asarray(labels, np.float64).ravel()
    order = np.argsort(raw, kind="stable")
    ss, sl = raw[order], lab[order]
    unique, starts = np.unique(ss, return_index=True)
    rel = _within_class_weights(np.asarray(weights, np.float64).ravel(), lab)[order]
    pos = np.add.reduceat(sl * rel, starts)
    neg = np.add.reduceat((1.0 - sl) * rel, starts)
    total = float(lab.size)
    return (unique, pos * total / (2.0 * float(np.sum(sl * rel))), neg * total / (2.0 * float(np.sum((1.0 - sl) * rel))),
            int(lab.size))


def pav_blocks(unique: np.ndarray, pos_w: np.ndarray, neg_w: np.ndarray, n_labels: int) -> Blocks:
    """The fitters' merge loop (color_model.py fit_component_pava, chains._pav) with each block's first and last
    training score carried along."""
    gw = pos_w + neg_w
    gv = pos_w / gw
    values: list[float] = []
    weights: list[float] = []
    sums: list[float] = []
    first: list[float] = []
    last: list[float] = []
    for score, value, weight in zip(unique, gv, gw):
        values.append(float(value))
        weights.append(float(weight))
        sums.append(float(score) * float(weight))
        first.append(float(score))
        last.append(float(score))
        while len(values) > 1 and values[-2] >= values[-1]:
            weight = weights[-1] + weights[-2]
            values[-2] = (values[-1] * weights[-1] + values[-2] * weights[-2]) / weight
            weights[-2] = weight
            sums[-2] += sums[-1]
            last[-2] = last[-1]
            for lst in (values, weights, sums, first, last):
                lst.pop()
    return Blocks(np.asarray(values), np.asarray(first), np.asarray(last), np.asarray(weights), np.asarray(sums),
                  int(n_labels))


def _zero_node(x: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """E017.6: a (0, 0.5) node where the nodes straddle score 0 with p straddling 1/2 (fit_component_pava's test)."""
    i = int(np.searchsorted(x, 0.0))
    if 0 < i < x.size and x[i - 1] < 0.0 < x[i] and p[i - 1] <= 0.5 <= p[i]:
        return np.insert(x, i, 0.0), np.insert(p, i, 0.5)
    return x, p


def _clip(b: Blocks) -> np.ndarray:
    pmin = 1.0 / (b.n_labels + 2.0)
    return np.array([min(max(float(v), pmin), 1.0 - pmin) for v in b.values])


def centroid_nodes(b: Blocks) -> tuple[np.ndarray, np.ndarray]:
    return _zero_node(b.score_sums / b.weights, _clip(b))


def edge_map(b: Blocks) -> PavaMap:
    """The block-edge evaluator: (first, p) and, for a block spanning more than one score, (last, p); logit-joined."""
    p = _clip(b)
    xs: list[float] = []
    ps: list[float] = []
    for a, z, q in zip(b.first, b.last, p):
        xs.append(float(a))
        ps.append(float(q))
        if z > a:
            xs.append(float(z))
            ps.append(float(q))
    x, pp = _zero_node(np.asarray(xs), np.asarray(ps))
    return PavaMap(x, pp, b.n_labels, logit_interpolation=True)


def checked_blocks(pm: PavaMap, groups: tuple[np.ndarray, np.ndarray, np.ndarray, int]) -> Blocks:
    """The blocks behind a fitted map; refuses unless their centroid nodes ARE the map's nodes (bit for bit)."""
    b = pav_blocks(*groups)
    x, p = centroid_nodes(b)
    if not (np.array_equal(x, pm.score_nodes) and np.array_equal(p, pm.probability_nodes)):
        raise SystemExit(f"blocks do not reproduce the fitted map: {x.size} vs {pm.score_nodes.size} nodes")
    return b


def evaluator_map(ev: str, pm: PavaMap, b: Blocks) -> PavaMap:
    if ev == "centroid-linear":
        return replace(pm, logit_interpolation=False)
    if ev == "centroid-logit":
        return replace(pm, logit_interpolation=True)
    if ev == "block-edge":
        return edge_map(b)
    raise ValueError(ev)


# ---------------------------------------------------------------- the metrics of one emitted population

def metrics(forms: np.ndarray, state: np.ndarray) -> dict[str, Any]:
    """forms (N, 6) in chains.FORMS order, state the manifest index (W0 C1 M2 Y3)."""
    rows = info_rows(forms, state)
    out: dict[str, Any] = {"n": int(state.size)}
    for name, i in INFO_ROWS.items():
        out[f"I_{name}"] = float(rows["I"][i])
        out[f"logloss_{name}"] = float(rows["logloss"][i])
    for name, col, bits in (("hi", 0, HI), ("lo", 1, LO)):
        L = forms[:, col]
        b = bits[state].astype(np.float64)
        m = (2.0 * b - 1.0) * L
        out[f"I_plain_{name}"] = float(1.0 - np.mean(np.logaddexp(0.0, -m)) / np.log(2.0))
        out[f"flips_{name}"] = int(np.count_nonzero(m < 0.0))
        out[f"ties_{name}"] = int(np.count_nonzero(L == 0.0))
        out[f"m_p1_{name}"], out[f"m_p5_{name}"] = (float(v) for v in np.percentile(m, [1, 5]))
        out[f"absL_lt_0p05_{name}"] = int(np.count_nonzero(np.abs(L) < 0.05))
    return out


def pooled_metrics(forms_list: list[np.ndarray], state_list: list[np.ndarray]) -> dict[str, Any]:
    return metrics(np.concatenate(forms_list), np.concatenate(state_list))


# ---------------------------------------------------------------- the paper extracts (R11's machinery)

def context_blocks(ctx: Any) -> dict[int, tuple[PavaMap, Blocks] | None]:
    """The hi-first maps of the context's D1-DEFAULT 'w' pieces with their blocks (population H, as fit_context
    fitted them: the state-balanced entry for L_hi, fit_component_pava for the conditionals)."""
    out: dict[int, tuple[PavaMap, Blocks] | None] = {}
    stat = demap(ctx.r_held)
    for k in HI_FIRST:
        pm = ctx.pieces[(POLICY, "w")][k]
        if pm is None:
            out[k] = None
            continue
        member, label = map_population(MAP_SPECS[k], ctx.held_state)
        groups = stratified_groups(stat[member, k], label[member],
                                   ctx.held_state[member] if MAP_SPECS[k].marginal else label[member])
        out[k] = (pm, checked_blocks(pm, groups))
    return out


def emit_paper(ctx: Any, r: np.ndarray, maps: dict[int, tuple[PavaMap, Blocks] | None]) -> dict[str, np.ndarray]:
    """Each evaluator's emitted forms on cells with raw scores r (chains.chain_output: fold, erasure, bound)."""
    stat = demap(r)
    lo_c, hi_c = bool(ctx.collapse["lo"]), bool(ctx.collapse["hi"])
    out = {"raw": chain_output("fallback", {}, r, lo_c, hi_c).forms}
    for ev in EVALUATORS[1:]:
        pieces = {k: None if m is None else evaluator_map(ev, *m).llrs(stat[:, k]) for k, m in maps.items()}
        out[ev] = chain_output("hi-first", pieces, r, lo_c, hi_c).forms
    return out


def map_shape(maps: dict[int, tuple[PavaMap, Blocks] | None]) -> dict[str, Any]:
    return {MAP_SPECS[k].name: None if m is None else {"blocks": int(m[1].values.size),
                                                        "spanning": int(np.count_nonzero(m[1].last > m[1].first))}
            for k, m in maps.items()}


def page_one(band: Band, k: int) -> dict[str, Any]:
    """followup.page_replicate's P-a context (same rngs), the four evaluators on the payload."""
    X = band.X["F"]
    fur = draw_furniture(regimes.rng_for("page_furniture", band.bc, 0, k), band, list(range(band.n_regions)))
    val = regimes.rng_for("valsplit", band.bc, 0, k).random(fur.held.size) < 1.0 / 3.0
    ctx = fit_context(X[fur.search], band.state[fur.search], X[fur.held], band.state[fur.held], fur.held_kind, val,
                      (POLICY,), ("w",))
    if ctx.refused is not None:
        return {"bc": band.bc, "k": k, "refused": ctx.refused}
    maps = context_blocks(ctx)
    forms = emit_paper(ctx, raw_scores(ctx.model, X[fur.payload]), maps)
    pst = band.state[fur.payload]
    grp = band.win[fur.payload]
    boot = WindowBootstrap(len(band.win_ids), B_BOOT, regimes.rng_for("bootstrap", band.bc, 0, 31000 + k))
    got = {ev: boot.info(f, pst, grp) for ev, f in forms.items()}
    rows = {}
    for ev, f in forms.items():
        row = metrics(f, pst)
        for name, i in INFO_ROWS.items():
            row[f"dI_{name}_vs_ref"] = est(got[ev][0][i] - got[REFERENCE][0][i], got[ev][1][:, i] - got[REFERENCE][1][:, i])
        rows[ev] = row
    return {"bc": band.bc, "band": band.name, "k": k, "refused": None, "maps": map_shape(maps),
            "collapse": ctx.collapse, "n_windows": len(band.win_ids), "rows": rows}


def cold_one(band: Band, n: int, k: int, origins: list[tuple[int, ...]]) -> dict[str, Any]:
    """followup.cold_one's furniture and context (same rngs), policy D1-DEFAULT, the four evaluators."""
    X = band.X["F"]
    rng = regimes.rng_for("cold", band.bc, n, k)
    oi = int(rng.integers(0, len(origins)))
    fur = draw_furniture(rng, band, origins[oi])
    val = regimes.rng_for("valsplit", band.bc, n, k).random(fur.held.size) < 1.0 / 3.0
    ctx = fit_context(X[fur.search], band.state[fur.search], X[fur.held], band.state[fur.held], fur.held_kind, val,
                      (POLICY,), ("w",))
    if ctx.refused is not None:
        return {"origin": oi, "refused": True}
    maps = context_blocks(ctx)
    pst = band.state[fur.payload]
    forms = emit_paper(ctx, raw_scores(ctx.model, X[fur.payload]), maps)
    return {"origin": oi, "refused": False, "state": pst, "forms": forms,
            "fitted": tuple(maps[k_] is not None for k_ in HI_FIRST),
            "I": {ev: info_rows(f, pst)["I"] for ev, f in forms.items()}}


def cold_summary(band: Band, n: int, draws: list[dict[str, Any]], n_origins: int) -> dict[str, Any]:
    ok = [d for d in draws if not d["refused"]]
    out: dict[str, Any] = {"bc": band.bc, "band": band.name, "n": n, "draws": len(draws), "refused": len(draws) - len(ok),
                           "n_origins": n_origins,
                           "fitted_frac": [float(np.mean([d["fitted"][i] for d in ok])) for i in range(3)], "rows": {}}
    if not ok:
        return out
    boot = WindowBootstrap(n_origins, B_BOOT, regimes.rng_for("bootstrap", band.bc, n, 31000))
    grp = np.array([d["origin"] for d in ok])
    for ev in EVALUATORS:
        row = pooled_metrics([d["forms"][ev] for d in ok], [d["state"] for d in ok])
        Ia = np.stack([d["I"][ev] for d in ok])
        Ir = np.stack([d["I"][REFERENCE] for d in ok])
        for name, i in INFO_ROWS.items():
            row[f"I_{name}"] = est(*boot.mean(Ia[:, i], grp))["est"]
            row[f"logloss_{name}"] = (1.0 - row[f"I_{name}"]) * np.log(2.0)
            row[f"dI_{name}_vs_ref"] = est(*boot.mean(Ia[:, i] - Ir[:, i], grp))
        out["rows"][ev] = row
    return out


#: followup.json's arm per evaluator (its page and c3 stages: P-a, replicate 0, D1-DEFAULT).
FOLLOWUP_ARMS = {"raw": "fallback", "centroid-linear": "hi-first", "centroid-logit": "hi-first/logit"}


def followup_repro(art: Path, page: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Max |diff| of I hi / lo / lo|hi against the follow-up run of record (bc 0-4, replicate 0), the instrument's
    null: three of the four evaluators are arms that already ran."""
    path = art / "followup-arms" / "followup.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text())
    ref = {(r["bc"], r["arm"], r["form"]): r["I"]["est"] for stage in ("page", "c3") for r in doc[stage]["page"]
           if r["population"] == "P-a" and r["replicate"] == 0}
    diffs: dict[str, float] = {}
    for rec in page:
        if rec["k"] != 0 or rec["refused"]:
            continue
        for ev, arm in FOLLOWUP_ARMS.items():
            for name in INFO_ROWS:
                got = ref.get((rec["bc"], arm, name))
                if got is not None:
                    key = f"bc{rec['bc']}|{ev}"
                    diffs[key] = max(diffs.get(key, 0.0), abs(rec["rows"][ev][f"I_{name}"] - got))
    return {"source": str(path), "max_abs_diff": diffs, "max": max(diffs.values()) if diffs else None}


def stage_paper(art: Path, out: Path, workers: int, bcs: tuple[int, ...]) -> dict[str, Any]:
    t0 = time.time()
    bands = load_bands(art, bcs)
    print(f"paper: {len(bands)} band-captures loaded ({time.time() - t0:.0f} s)", flush=True)
    jobs = [(bc, k) for bc in bcs for k in range(PAGE_REPLICATES)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        page = list(pool.map(lambda j: page_one(bands[j[0]], j[1]), jobs))
    print(f"paper: page done ({time.time() - t0:.0f} s, peak RSS {peak_rss_gb():.1f} GB)", flush=True)
    cold = []
    for bc in bcs:
        band = bands[bc]
        for n in COLD_SIZES:
            origins = cluster_origins(band, n, COLD_SHAPES)
            if not origins:
                continue
            with ThreadPoolExecutor(max_workers=workers) as pool:
                draws = list(pool.map(lambda k: cold_one(band, n, k, origins), range(COLD_DRAWS)))
            cold.append(cold_summary(band, n, draws, len(origins)))
            print(f"  cold bc{bc} {band.name} n={n}: {len(draws)} draws ({time.time() - t0:.0f} s)", flush=True)
    doc = {"art": str(art), "bcs": list(bcs), "policy": POLICY, "replicates": PAGE_REPLICATES, "cold_sizes": COLD_SIZES,
           "cold_draws": COLD_DRAWS, "B": B_BOOT, "page": page, "cold": cold,
           "bands": {bc: {"name": bands[bc].name, "cell_dots": bands[bc].cell_dots,
                          "capture": next(s.capture for s in BAND_CAPTURES if s.bc == bc)} for bc in bcs},
           "followup_repro": followup_repro(art, page), "seconds": time.time() - t0, "peak_rss_gb": peak_rss_gb()}
    write_json(out / "evaluator-paper.json", doc)
    print(f"paper: follow-up reproduction max |diff| {(doc['followup_repro'] or {}).get('max')}")
    print(f"paper: wrote {out / 'evaluator-paper.json'} ({doc['seconds']:.0f} s, peak RSS {doc['peak_rss_gb']:.1f} GB)")
    return doc


# ---------------------------------------------------------------- the report

def fmt(v: Any, d: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, dict):
        return f"{v['est']:+.{d}f} [{v['lo']:+.{d}f}, {v['hi']:+.{d}f}]"
    if isinstance(v, float):
        return f"{v:.{d}f}"
    return str(v)


HEAD = ["evaluator", "I hi", "I lo", "I lo|hi", "log-loss hi / lo (nats)", "flips hi / lo", "margin p1 hi / lo",
        "margin p5 hi / lo"]


def table_row(ev: str, r: dict[str, Any]) -> list[str]:
    return [ev, fmt(r["I_hi"]), fmt(r["I_lo"]), fmt(r["I_lo|hi"]),
            f"{r['logloss_hi']:.4f} / {r['logloss_lo']:.4f}", f"{r['flips_hi']} / {r['flips_lo']}",
            f"{r['m_p1_hi']:.3f} / {r['m_p1_lo']:.3f}", f"{r['m_p5_hi']:.3f} / {r['m_p5_lo']:.3f}"]


def md(head: list[str], rows: list[list[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(r) + " |" for r in rows])


def report_paper(doc: dict[str, Any]) -> str:
    parts = ["## Paper (R11 extracts, P-a page, payload cells, replicate 0)\n"]
    for rec in doc["page"]:
        if rec["k"] != 0:
            continue
        if rec["refused"]:
            parts.append(f"bc{rec['bc']}: refused {rec['refused']}\n")
            continue
        parts.append(f"### bc{rec['bc']} {rec['band']} (n = {rec['rows']['raw']['n']} payload cells, "
                     f"{rec['n_windows']} windows; maps {json.dumps(rec['maps'])})\n")
        parts.append(md(HEAD + ["dI hi / lo vs centroid-logit"],
                        [table_row(ev, r) + [f"{fmt(r['dI_hi_vs_ref'])} / {fmt(r['dI_lo_vs_ref'])}"]
                         for ev, r in rec["rows"].items()]) + "\n")
    parts.append("## Paper, all replicates: dI (block-edge − centroid-logit), hi / lo / lo|hi\n")
    rows = []
    for rec in doc["page"]:
        if rec["refused"]:
            continue
        r = rec["rows"]["block-edge"]
        rows.append([f"bc{rec['bc']} {rec['band']}", str(rec["k"]), fmt(r["dI_hi_vs_ref"]), fmt(r["dI_lo_vs_ref"]),
                     fmt(r["dI_lo|hi_vs_ref"]),
                     f"{rec['rows']['centroid-logit']['flips_hi']} → {r['flips_hi']}",
                     f"{rec['rows']['centroid-logit']['flips_lo']} → {r['flips_lo']}"])
    parts.append(md(["band-capture", "k", "dI hi", "dI lo", "dI lo|hi", "flips hi (logit → edge)",
                     "flips lo (logit → edge)"], rows) + "\n")
    parts.append("## Cold start (D draws pooled; I = mean over draws; dI vs centroid-logit, cluster-origin CI)\n")
    for rec in doc["cold"]:
        if not rec["rows"]:
            continue
        parts.append(f"### bc{rec['bc']} {rec['band']} n = {rec['n']} ({rec['draws']} draws, {rec['refused']} refused, "
                     f"maps fitted {['%.2f' % v for v in rec['fitted_frac']]})\n")
        parts.append(md(HEAD + ["dI hi / lo vs centroid-logit"],
                        [table_row(ev, r) + [f"{fmt(r['dI_hi_vs_ref'])} / {fmt(r['dI_lo_vs_ref'])}"]
                         for ev, r in rec["rows"].items()]) + "\n")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", choices=("paper", "report"), required=True)
    ap.add_argument("--art", type=Path, help="the R11 run's work directory (cells-<capture>.npz)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=Params().workers)
    ap.add_argument("--bcs", type=int, nargs="*", default=[s.bc for s in BAND_CAPTURES])
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.stage == "paper":
        if a.art is None:
            raise SystemExit("--art is required for --stage paper")
        stage_paper(a.art, a.out, a.workers, tuple(a.bcs))
        return
    from measure.cmy_calibration import evaluator_lanes
    text = []
    if (a.out / "evaluator-paper.json").exists():
        text.append(report_paper(json.loads((a.out / "evaluator-paper.json").read_text())))
    text.append(evaluator_lanes.report_lanes(a.out))
    (a.out / "evaluator.md").write_text("\n".join(text))
    print(f"wrote {a.out / 'evaluator.md'}")


if __name__ == "__main__":
    main()
