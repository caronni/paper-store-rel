"""R11 — the stages: selfcheck (C2, C3), extract (feature caches + parity + C1), smoke, time, run (C5-C7 first,
then every regime, C4, C8, C9, the decisions) and the JSON of record.

What: one function per stage of the protocol's run order, each writing its artefact under config.ARTEFACTS:
selfcheck.json, cells-<capture>.npz/.json, extract-controls.json, smoke.json, time.json and
cmy-calibration.json (the one JSON of record; report.md is rendered from it by report.py).
Why: the protocol's 'Run order' and stop rule — a failing control writes decisions: null, names the control and
prints no verdict.  How: bands are rebuilt from the caches (fit.build_band); the regimes run one band-capture at
a time with their own thread pools; meta.code_sha256 hashes every .py of the package (decide.py included) at the
start of the run stage.  Inputs (config's docstring): extract reads the scans and manifests under evidence_root and
the scale readouts under scale_root, run records the scans' and manifests' paths, sizes and hashes from
evidence_root; a missing input is refused by name before any work (measure/_evidence.need).
"""
from __future__ import annotations

import hashlib
import json
import platform
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from measure import _evidence
from measure.cmy_calibration import controls, regimes, twocap
from measure.cmy_calibration.chains import demap
from measure.cmy_calibration.config import (ARTEFACTS, BAND_CAPTURES, CAPTURES, COLD_SIZES, DEADY_CONTROL_BCS,
                                            DECISION_BCS, MASTER_SEED, NULL_BCS, PAINTED_S2_BC, PROTOCOL_VERSION,
                                            REGIME, RUNGS, SYNTH_S1_BC, SYNTH_S1B_BC, TWO_CAPTURE_PAIRS, WORKTREE,
                                            Params)
from measure.cmy_calibration.estimators import ROWS, info_rows, logistic_slope, row_cells
from measure.cmy_calibration.extract import (extract_capture, git_head, load_cells, sha256_file, write_cells)
from measure.cmy_calibration.fit import Band, build_band
from measure.cmy_calibration.ldpc_sim import time_decodes

PKG = Path(__file__).resolve().parent
TOOL = "cmy_calibration"
#: Every place the build departs from the protocol text, with the reason (2026-10-10, the builder).
DEVIATIONS: tuple[str, ...] = (
    "2026-10-10 C2: sympy is not installed in env/; the symbolic simplification is replaced by a 60-digit "
    "decimal-module evaluation of the identities on 200 random triples (max error <= 1e-40) beside the protocol's "
    "10^6-triple float check.",
    "2026-10-10 figures: matplotlib is not installed in env/; fig01-fig11 are drawn with PIL (plots.py).",
    "2026-10-10 C3: the protocol names no tolerance for 'recovers the payload-prior map'; coded as mean |dp| over "
    "a score grid <= 0.01 and below a third of the class-balanced fit's deviation.",
    "2026-10-10 extraction: one npz per (sheet, capture) holding its bands, keyed by the scan's and extract.py's "
    "sha256 (the protocol says one per band-capture); windows may be read on threads after a serial-vs-threaded "
    "bit-identity check (--workers, default serial).",
    "2026-10-10 weighting: the state-balanced PAVA gives each binary class N/2 split equally over its PRESENT "
    "states; with all four states present this is the protocol's w = 1/(K n_s) summed to N; with a state absent "
    "(ALWAYS policy only) it keeps the receiver's binary balance instead of K = 3.",
    "2026-10-10 ALWAYS: a map whose population lacks one binary class cannot be fitted (fit_component_pava divides "
    "by the class count); it falls back to its raw piece.",
    "2026-10-10 six-maps has no score triple: its emitted forms are clipped at +-20 each (the LDPC's own clip); "
    "its region gate scores the lo-first fold of its lo, hi|lo=0 and hi|lo=1 forms.",
    "2026-10-10 erasure law in healthy regimes: a detected label-space collapse erases the stream for every arm; the "
    "surviving marginal is the chain's own fitted map where it has one (hi-first, six-maps), else the bounded raw "
    "form (lo-first, fallback) — D2 rules the dead-Y case separately.",
    "2026-10-10 R-D page uses P-a only (no P-b certified folds on the dead page); page-final there = P-a.",
    "2026-10-10 C5 null: P-a only at page (P-b's certified cells would carry true labels, a leak by construction); "
    "cold draws use D_null for both information and LDPC; the gate reads lo-first / hi-first / six-maps under "
    "D1-DEFAULT.",
    "2026-10-10 page LDPC: trial t uses furniture replicate t mod R (the protocol leaves the replicate of a trial "
    "open).",
    "2026-10-10 slope intervals: computed for the hi and lo rows of replicate 0 only, on cells aggregated by "
    "(window, state, L rounded to 0.05 nats); every other slope is a point estimate.",
    "2026-10-10 two captures: six-maps enters D1's two-capture cells through SUM-OF-FORMS, its only summed mode; "
    "RECAL-ORACLE sums the per-capture bounded raw triples before its per-form PAVA.",
    "2026-10-10 D3 reading: n*_info and the tile floor are taken over all four decision band-captures together "
    "(every one must meet the condition; q averaged over them); yields pooled over them; the D1 winner's two "
    "conditional maps are lo-first's when the winner is the fallback or six-maps.",
    "2026-10-10 C7 runs R-P with R = 1 and T = T_null on the painted page.",
    "2026-10-10 auxiliary seeds: bootstrap generators use [MASTER_SEED, 10, bc, n, k] with k offsets per use "
    "(page k*10+features, cold 1000+features, dead Y 500+k / 600, two captures n=2), the LDPC-row and yield "
    "bootstraps [MASTER_SEED, 10, bc, 7|8], decide's [MASTER_SEED, 10, 99, k], the time stage [MASTER_SEED, 99]; "
    "dead-Y cold trials use REGIME 5 with k + 10000 (all explicit, none unseeded).",
    "2026-10-10 an opt-in --diagnostic-continue (default off) records a failed control and finishes the run into "
    "cmy-calibration-diagnostic.json with decisions null and the rules' reading as decisions_unratified, so one "
    "expensive run is not lost to a stop; the JSON of record keeps the protocol's stop rule.",
)


def jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return jsonable(x.tolist())
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return v if np.isfinite(v) else None
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(obj), indent=1))


def code_sha256() -> dict[str, str]:
    files = sorted(PKG.glob("*.py"))
    per = {f.name: sha256_file(f) for f in files}
    per["_all"] = hashlib.sha256("".join(per[f.name] for f in files).encode()).hexdigest()
    return per


# ---------------------------------------------------------------- stage 0 / 1

def stage_selfcheck(art: Path = ARTEFACTS) -> dict[str, Any]:
    out = {"C2": controls.c2_selfcheck(), "C3": controls.c3_pava()}
    out["pass"] = out["C2"]["pass"] and out["C3"]["pass"]
    write_json(art / "selfcheck.json", out)
    return out


def cells_path(art: Path, key: str) -> Path:
    return art / f"cells-{key}.npz"


def cache_current(path: Path) -> bool:
    if not path.exists():
        return False
    _, meta = load_cells(path)
    return bool(meta.get("scan_sha256")) and meta.get("extract_sha256") == sha256_file(PKG / "extract.py")


def need_capture_inputs(key: str, evidence_root: Path, scale_root: Path) -> None:
    """Refuse by name, before any work, unless the capture's scan, manifest, bands npz and scale readout exist."""
    cap = CAPTURES[key]
    _evidence.need(cap.scan_at(evidence_root), cap.manifest_at(evidence_root), cap.bands_npz_at(evidence_root),
                   tool=TOOL)
    _evidence.need(cap.windows_csv_at(scale_root), cap.summary_json_at(scale_root), tool=TOOL,
                   regenerate=cap.readout_command(evidence_root, scale_root))


def stage_extract(art: Path = ARTEFACTS, keys: tuple[str, ...] | None = None, ap07: bool = False,
                  log: Any = print, workers: int = 1, *, evidence_root: Path, scale_root: Path) -> dict[str, Any]:
    """Each capture's cache (one scan in memory at a time), the parity gate, then C1 on every band-capture."""
    from measure.cmy_calibration.extract import parity_gate
    selected = keys or tuple(CAPTURES)
    current = {key for key in selected if cache_current(cells_path(art, key))}
    for key in selected:
        if key not in current:
            need_capture_inputs(key, evidence_root, scale_root)
    for key in selected:
        cap = CAPTURES[key]
        path = cells_path(art, key)
        if key in current:
            log(f"{key}: cache {path} current")
            continue
        scan, manifest = cap.scan_at(evidence_root), cap.manifest_at(evidence_root)
        arrays, meta = extract_capture(scan, manifest, float(cap.scan_dpi), cap.bands, ap07, log, workers=workers)
        meta.update({"capture": key, "scan_sha256": sha256_file(scan), "scan_bytes": scan.stat().st_size,
                     "white_expected": list(cap.white_rgb),
                     "parity": parity_gate(arrays, meta, cap.windows_csv_at(scale_root))})
        write_cells(path, arrays, meta)
        log(f"{key}: {meta['n_cells']} cells, parity {'pass' if meta['parity']['pass'] else 'FAIL'}, "
            f"{meta['wall_s']:.0f} s")
    missing = [k for k in CAPTURES if not cells_path(art, k).exists()]
    if missing:
        log(f"C1 waits for the caches of {missing}")
        bad = [k for k in CAPTURES if k not in missing and load_cells(cells_path(art, k))[1].get("parity", {})
               .get("pass") is False]
        return {"pass": not bad, "pending": missing, "parity_failed": bad}
    return stage_c1(art, log, evidence_root=evidence_root, scale_root=scale_root)


def stage_c1(art: Path = ARTEFACTS, log: Any = print, *, evidence_root: Path, scale_root: Path) -> dict[str, Any]:
    """C1 against each capture's scale readout summary (evidence_root names the scans in the refusal's recipe)."""
    for cap in CAPTURES.values():
        _evidence.need(cap.summary_json_at(scale_root), tool=TOOL,
                       regenerate=cap.readout_command(evidence_root, scale_root))
    rows, extraction, parity = [], [], {}
    summaries: dict[str, Any] = {}
    for spec in BAND_CAPTURES:
        arrays, meta = load_cells(cells_path(art, spec.capture))
        parity[spec.capture] = meta.get("parity", {}).get("pass")
        if spec.capture not in summaries:
            summaries[spec.capture] = json.loads(CAPTURES[spec.capture].summary_json_at(scale_root).read_text())
        com = next(b for b in summaries[spec.capture]["bands"] if b["name"] == spec.band)["confusion_loo"]
        rows.append(controls.c1_anchor(arrays, meta, spec.band, com, spec.bc, spec.role))
        band = build_band(arrays, meta, spec.band, spec.bc)
        extraction.append({"bc": spec.bc, "band": spec.band, "capture": spec.capture,
                           "windows": int(np.sum(arrays["band"][np.unique(arrays["win"], return_index=True)[1]]
                                                 == meta["band_names"].index(spec.band))),
                           "excluded": band.excluded, "regions": band.n_regions,
                           "cells": int(sum(r.size for r in band.regions)),
                           "cells_per_region": int(band.regions[0].size) if band.regions else 0,
                           "skipped_windows": meta.get("skipped", [])})
        log(f"C1 bc{spec.bc} {spec.band}: max |diff| {rows[-1]['max_abs_diff']}, err hi/lo "
            f"{rows[-1]['err_hi']:.3f}/{rows[-1]['err_lo']:.3f} %, pass {rows[-1]['pass']}")
    out = {"C1": rows, "extraction": extraction, "parity": parity,
           "pass": all(r["pass"] for r in rows) and all(v is not False for v in parity.values())}
    write_json(art / "extract-controls.json", out)
    return out


# ---------------------------------------------------------------- bands

def load_bands(art: Path, bcs: tuple[int, ...]) -> dict[int, Band]:
    cache: dict[str, tuple[dict[str, np.ndarray], dict[str, Any]]] = {}
    out = {}
    for spec in BAND_CAPTURES:
        if spec.bc not in bcs:
            continue
        if spec.capture not in cache:
            cache[spec.capture] = load_cells(cells_path(art, spec.capture))
        out[spec.bc] = build_band(*cache[spec.capture], spec.band, spec.bc)
    return out


def load_pair(art: Path, bc1: int, bc2: int, band: str) -> tuple[Band, Band]:
    s1 = next(s for s in BAND_CAPTURES if s.bc == bc1)
    s2 = next(s for s in BAND_CAPTURES if s.bc == bc2)
    return twocap.aligned_pair(load_cells(cells_path(art, s1.capture)), load_cells(cells_path(art, s2.capture)),
                               band, bc1, bc2)


# ---------------------------------------------------------------- stage 3: time

def projected_decodes(p: Params) -> dict[str, float]:
    """Upper bounds of decodes (no dedupe) per regime under the parameters."""
    per = 12
    c3 = 4 * len(p.c3_rungs)
    cold_arms = 13 + (8 if p.cb_ldpc else 0)
    page_arms = 7 - (0 if p.cb_ldpc else 2)
    n_sizes = len(COLD_SIZES) - (0 if p.n8_ldpc else 1)
    d: dict[str, float] = {
        "page": 4 * p.T_page * page_arms * 2 * per,
        "page_c3": 6 * p.T_c3 * page_arms * c3,
        "cold": 4 * n_sizes * p.D_ldpc * cold_arms * per,
        "cold_c3": 6 * n_sizes * p.D_ldpc * cold_arms * c3,
        "rs": (4 * p.T_page * page_arms * 2 * per + 4 * 3 * p.D_ldpc * cold_arms * per) if p.rs_ldpc else 0,
        "deadY": 6 * (p.T_page * 4 * 3 + n_sizes * p.D_ldpc * 3 * 3),
        "twocap": (p.T_page + p.T_c3) * 12 * 2 * per,
        "nulls": 2 * (p.T_null * 7 * per + 2 * p.D_null * 21 * per),
        "s1_s2": p.T_page * 7 * 2 * per + p.T_null * 7 * 2 * per}
    d["total"] = float(sum(d.values()))
    return d


REDUCTIONS = (("c3 LDPC to r0850 only", {"c3_rungs": ("r0850",)}), ("drop R-S LDPC", {"rs_ldpc": False}),
              ("drop the class-balanced arms' LDPC", {"cb_ldpc": False}), ("drop n = 8 LDPC", {"n8_ldpc": False}))


def stage_time(art: Path = ARTEFACTS, params: Params = Params(), budget_min: float = 55.0,
               log: Any = print) -> dict[str, Any]:
    band = load_bands(art, (0,))[0]
    pf = regimes.page_fit(band, "F", 0, params, pops=("P-a",), oracle=False)
    lab = pf.forms["P-a|lo-first|w|D1-DEFAULT"][:, 1]
    st = band.state[pf.payload]
    walls = time_decodes(lab, st, "lo", RUNGS, 30, np.random.default_rng([MASTER_SEED, 99]))
    mean_ms = float(np.mean([0.5 * w["fail_ms"] + 0.5 * w["ok_ms"] for w in walls.values()]))
    chosen = params
    steps = []
    proj = projected_decodes(chosen)["total"] * mean_ms / 1e3 / 8 / 60
    for name, change in REDUCTIONS:
        if proj <= budget_min:
            break
        chosen = replace(chosen, **change)
        steps.append(name)
        proj = projected_decodes(chosen)["total"] * mean_ms / 1e3 / 8 / 60
    out = {"walls": walls, "mean_decode_ms": mean_ms, "projected_min": proj, "budget_min": budget_min,
           "reductions": steps, "params": asdict(chosen), "decodes": projected_decodes(chosen)}
    write_json(art / "time.json", out)
    log(json.dumps(jsonable(out), indent=1))
    return out


# ---------------------------------------------------------------- the controls run inside 'run'

def s1_controls(b3: Band, params: Params, T: int, D_detect: int, log: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """C6 on the Gaussian S1 (and S1b): R-P all chains vs the exact Bayes LLRs, LDPC, two captures, dead Y."""
    mu, cov = twocap.pooled_gaussians(b3)
    s1, s1b = twocap.synth_pair(mu, cov, SYNTH_S1_BC, SYNTH_S1B_BC)
    page = regimes.run_page(s1, "F", params, T=T, log=log)
    pf = page["fits"][0]
    st = s1.state[pf.payload]
    bayes_f = demap(twocap.bayes_scores(s1.X["F"][pf.payload], mu, cov))
    bayes = dict(zip(ROWS, info_rows(bayes_f, st)["I"].tolist()))
    s_a = twocap.bayes_scores(s1.X["F"], mu, cov)
    s_b = twocap.bayes_scores(s1b.X["F"], mu, cov)
    summed, sof = demap(s_a + s_b), demap(s_a) + demap(s_b)
    I_sum, I_sof = info_rows(summed, s1.state)["I"], info_rows(sof, s1.state)["I"]
    slopes = [logistic_slope(*row_cells(summed, s1.state, i))[0] for i in (0, 1)]
    tc_bayes = {"identical": bool(np.abs(summed[:, 2:] - sof[:, 2:]).max() <= 1e-9),
                "summed_ge": bool(I_sum[0] >= I_sof[0] - 1e-12 and I_sum[1] >= I_sof[1] - 1e-12),
                "slope_ok": bool(all(abs(a - 1.0) <= 0.05 for a in slopes)), "I_summed": I_sum[:2],
                "I_sum_of_forms": I_sof[:2], "summed_slope": slopes}
    tc = twocap.run_twocap(s1, s1b, params, ldpc=False, log=log, label="S1")
    tc_bayes["identical"] = tc_bayes["identical"] and tc["C4_max_abs"] <= 1e-9
    dead = regimes.run_deady(s1, "F", params, sizes=COLD_SIZES, ldpc=False, D_info=D_detect, log=log)
    detect = {r["n"]: r["detect_rate"] for r in dead["deadY"] if r["regime"] == "cold" and r["arm"] == "a"}
    page_dead = [r for r in dead["deadY"] if r["regime"] == "page"]
    c6 = controls.c6_check(page["page"], bayes, page["ldpc"], tc_bayes, page_dead, detect)
    rows = {"page": page["page"], "ldpc": page["ldpc"], "yield": page["yield"], "twocapture": tc["twocapture"],
            "deadY": dead["deadY"]}
    return c6, rows


def null_controls(bands: dict[int, Band], params: Params, log: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    page_rows, cold_rows, ld = [], [], []
    for bc in bands:
        pg = regimes.run_page(bands[bc], "F", params, T=params.T_null, shuffle=True, regime="null-page", log=log)
        page_rows += pg["page"]
        ld += pg["ldpc"]
        for n in (1, 3):
            cd = regimes.run_cold(bands[bc], "F", n, params, D_info=params.D_null, D_ldpc=params.D_null, shuffle=True,
                                  regime="null-cold", log=log)
            cold_rows += cd["coldstart"]
            ld += cd["ldpc"]
    c5 = controls.c5_check(page_rows, cold_rows, ld)
    return c5, {"page": page_rows, "coldstart": cold_rows, "ldpc": ld}


def painted_s2(art: Path, params: Params, log: Any) -> dict[str, Any]:
    """C7: e041_scale_synth's default page (B3 = cmy4 c2) painted at 2400 with blur 0, white 230, the S14 solid
    bar toners, noise 24, seed 7; extraction -> confusion -> R-P with LDPC -> the C5 null on it."""
    import tifffile

    import measure.e041_scale_synth as ss
    from measure.e041_mixture_synth import TONER_RGB
    d = art / "s2"
    d.mkdir(parents=True, exist_ok=True)
    man, npz = ss.build()
    mpath = d / "S14-synth.manifest.json"
    mpath.write_text(json.dumps(man, indent=1))
    np.savez_compressed(d / "S14-synth-bands.npz", **npz)
    tiff = d / "s2-2400.tiff"
    if not tiff.exists():
        toner = dict(TONER_RGB)
        toner.update({"C": (46, 151, 194), "M": (215, 67, 119), "Y": (229, 219, 88)})
        img = ss.paint_scan(*ss.page_planes(man, npz), toner, {}, scan_dpi=2400.0, rot180=False,
                            shift_mm=(0.0, 0.0), scale=1.0, rot_deg=0.0, pad_mm=8.0, blur_px=0.0, noise_sd=24.0,
                            white=230.0, seed=7)
        tifffile.imwrite(tiff, img, photometric="rgb", resolution=(2400.0, 2400.0), resolutionunit="INCH")
    arrays, meta = extract_capture(tiff, mpath, 2400.0, ("B3",), False, log)
    band = build_band(arrays, meta, "B3", PAINTED_S2_BC)
    conf = controls.loo_confusion(arrays["x_pp"], arrays["y"], arrays["win"])
    page = regimes.run_page(band, "F", replace(params, R=1), T=params.T_null, log=log)
    c5, null_rows = null_controls({PAINTED_S2_BC: band}, replace(params, R=1), log)
    return {"confusion_loo": conf.tolist(), "stats": controls.confusion_stats(conf), "regions": band.n_regions,
            "page_rows": len(page["page"]), "ldpc_rows": len(page["ldpc"]), "C5": c5, "pass": bool(c5["pass"]),
            "_rows": {"page": page["page"], "ldpc": page["ldpc"], "nulls": null_rows}}


def c2_real_band(band: Band) -> dict[str, Any]:
    """C2 on real data: replicate 0's P-a context, demap(fold(maps)) == maps on the payload."""
    from measure.cmy_calibration.fit import draw_furniture, fit_context
    fur = draw_furniture(regimes.rng_for("page_furniture", band.bc, 0, 0), band, list(range(band.n_regions)))
    X = band.X["F"]
    ctx = fit_context(X[fur.search], band.state[fur.search], X[fur.held], band.state[fur.held], fur.held_kind,
                      np.zeros(fur.held.size, bool), ("D1-DEFAULT",), ("w",))
    return controls.c2_real(ctx, X[fur.payload])


def pava_maps_record(band: Band) -> dict[str, Any]:
    """fig10's input: B3's marginal maps, weighted vs class-balanced, at page (replicate 0, P-a) and at n = 1
    (cold draw 0)."""
    from measure.cmy_calibration.config import COLD_SHAPES
    from measure.cmy_calibration.fit import cluster_origins, draw_furniture, fit_context
    X = band.X["F"]
    out: dict[str, Any] = {}
    origins = cluster_origins(band, 1, COLD_SHAPES)
    for name, rng, regions in (("page", regimes.rng_for("page_furniture", band.bc, 0, 0), list(range(band.n_regions))),
                               ("n1", regimes.rng_for("cold", band.bc, 1, 0), None)):
        if regions is None:
            regions = list(origins[int(rng.integers(0, len(origins)))])
        fur = draw_furniture(rng, band, regions)
        ctx = fit_context(X[fur.search], band.state[fur.search], X[fur.held], band.state[fur.held], fur.held_kind,
                          np.zeros(fur.held.size, bool), ("D1-DEFAULT",), ("w", "cb"))
        out[name] = {m: {w: (None if ctx.maps.get(("H", w, k)) is None else
                             {"score_nodes": ctx.maps[("H", w, k)].score_nodes,
                              "probability_nodes": ctx.maps[("H", w, k)].probability_nodes})
                         for w in ("w", "cb")} for k, m in ((0, "L_hi"), (1, "L_lo"))}
    return out


def stage_smoke(art: Path = ARTEFACTS, log: Any = print) -> dict[str, Any]:
    """Protocol stage 2: T = D = 20 on B3 and S1; only control pass/fail is read and written."""
    p = Params(T_page=20, T_c3=20, D_info=20, D_ldpc=20, B=200, B_slope=20, T_null=20, D_null=20, D_detect=20)
    bands = load_bands(art, (0,))
    c6, _ = s1_controls(bands[0], p, 20, 20, log)
    c5, _ = null_controls({0: bands[0]}, p, log)
    c2r = c2_real_band(bands[0])
    page = regimes.run_page(bands[0], "F", p, T=20, log=log)
    cold = regimes.run_cold(bands[0], "F", 1, p, log=log)
    out = {"C2_real": c2r["pass"], "C5": c5["pass"], "C6": c6["pass"], "ran_page_rows": len(page["page"]),
           "ran_cold_rows": len(cold["coldstart"]), "params": asdict(p)}
    write_json(art / "smoke.json", out)
    log(json.dumps(out))
    return out


# ---------------------------------------------------------------- stage 5: run

def strip(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in ("fits", "draws", "outcomes")}


def stage_run(art: Path = ARTEFACTS, params: Params | None = None, smoke: bool = False,
              decision_bcs: tuple[int, ...] = DECISION_BCS, log: Any = print,
              workers: int | None = None, diagnostic_continue: bool = False, *,
              evidence_root: Path) -> dict[str, Any]:
    """The run.  diagnostic_continue (opt-in, default off): a failed control is recorded and the run goes on;
    the output is then cmy-calibration-diagnostic.json with decisions null and the rules' reading under
    'decisions_unratified' — never the JSON of record.  evidence_root: the scans and manifests meta records."""
    t0 = time.time()
    scans = {k: c.scan_at(evidence_root) for k, c in CAPTURES.items()}
    manifests = sorted({c.manifest_at(evidence_root) for c in CAPTURES.values()})
    _evidence.need(*scans.values(), *manifests, tool=TOOL)
    if params is None:
        tj = json.loads((art / "time.json").read_text()) if (art / "time.json").exists() else None
        params = Params(**{**tj["params"], "c3_rungs": tuple(tj["params"]["c3_rungs"])}) if tj else Params()
    if workers is not None:
        params = replace(params, workers=workers)
    tj_walls = (json.loads((art / "time.json").read_text()) if (art / "time.json").exists() else {})
    if not smoke and not params.floors_ok():
        raise SystemExit(f"parameters below the pre-registered floors: {params}")
    meta = {"protocol_version": PROTOCOL_VERSION, "worktree": str(WORKTREE), "head_sha": git_head(),
            "code_sha256": code_sha256(), "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__, "seeds": {"master": MASTER_SEED, "regimes": REGIME},
            "params": asdict(params), "smoke": smoke,
            "walls": {r: {"ok_ms": w["ok_ms"], "fail_ms": w["fail_ms"]} for r, w in tj_walls.get("walls", {}).items()},
            "time_stage": {k: tj_walls.get(k) for k in ("projected_min", "reductions", "mean_decode_ms")}}
    doc: dict[str, Any] = {"meta": meta, "extraction": [], "controls": {}, "page": [], "coldstart": [], "gates": [],
                           "twocapture": [], "deadY": [], "ldpc": [], "yield": [], "decisions": None,
                           "deviations": list(DEVIATIONS), "collapse": []}
    sc = json.loads((art / "selfcheck.json").read_text()) if (art / "selfcheck.json").exists() else stage_selfcheck(art)
    ec = json.loads((art / "extract-controls.json").read_text())
    doc["controls"].update({"C1": ec["C1"], "C2": sc["C2"], "C3": sc["C3"]})
    doc["extraction"] = ec["extraction"]
    meta["scans"] = [{"id": k, "path": str(s), "bytes": s.stat().st_size,
                      "sha256": load_cells(cells_path(art, k))[1].get("scan_sha256")} for k, s in scans.items()]
    meta["manifests"] = [{"path": str(m), "sha256": sha256_file(m)} for m in manifests]
    out_path = art / ("smoke.json" if smoke else "cmy-calibration-diagnostic.json" if diagnostic_continue
                      else "cmy-calibration.json")
    doc["failed_controls"] = []

    def stop(name: str) -> bool:
        """True = return now (the stop rule); in diagnostic mode the failure is recorded and the run goes on."""
        doc["failed_controls"].append(name)
        log(f"STOP: control {name} failed; decisions null" + (" (diagnostic: continuing)" if diagnostic_continue
                                                               else ""))
        if diagnostic_continue:
            return False
        doc["decisions"] = None
        doc["stopped_by"] = name
        meta["wall_s"] = time.time() - t0
        write_json(out_path, doc)
        return True
    if not (ec["pass"] or smoke) and stop("C1"):
        return doc
    if not sc["pass"] and stop("C2" if not sc["C2"]["pass"] else "C3"):
        return doc
    bands = load_bands(art, tuple(s.bc for s in BAND_CAPTURES))
    c6, s1_rows = s1_controls(bands[0], params, params.T_page, params.D_detect, log)
    doc["controls"]["C6"] = {**c6, "rows": s1_rows}
    c5, null_rows = null_controls({bc: bands[bc] for bc in NULL_BCS}, params, log)
    doc["controls"]["C5"] = {**c5, "rows": null_rows}
    if not smoke:
        c7 = painted_s2(art, params, log)
        doc["controls"]["C7"] = c7
    for name in ("C6", "C5", "C7"):
        if name in doc["controls"] and not doc["controls"][name]["pass"] and stop(name):
            return doc
    real_c2 = []
    for bc in decision_bcs:
        b = bands[bc]
        res = regimes.run_page(b, "F", params, log=log, cb_ldpc=params.cb_ldpc)
        doc["page"] += res["page"]
        doc["ldpc"] += res["ldpc"]
        doc["yield"] += res["yield"]
        real_c2.append({"bc": bc, **c2_real_band(b)})
        if bc == 0:
            doc["maps_B3"] = pava_maps_record(b)
        rs = regimes.run_page(b, "F1", params, ldpc=params.rs_ldpc, regime="page", log=log,
                              cb_ldpc=params.cb_ldpc)
        doc["page"] += rs["page"]
        doc["ldpc"] += rs["ldpc"]
        doc["yield"] += rs["yield"]
        for n in COLD_SIZES:
            cd = regimes.run_cold(b, "F", n, params, D_ldpc=(params.D_ldpc if (n != 8 or params.n8_ldpc) else 0),
                                  log=log)
            for k in ("coldstart", "gates", "ldpc", "yield"):
                doc[k] += cd[k]
            doc["collapse"].append(cd.get("collapse"))
            if n <= 3:
                cs = regimes.run_cold(b, "F1", n, params, D_ldpc=params.D_ldpc if params.rs_ldpc else 0,
                                      regime="cold", log=log)
                for k in ("coldstart", "gates", "ldpc", "yield"):
                    doc[k] += cs[k]
        dy = regimes.run_deady(b, "F", params, sizes=COLD_SIZES, log=log)
        doc["deadY"] += dy["deadY"]
        doc["ldpc"] += dy["ldpc"]
    doc["controls"]["C2"]["real"] = real_c2
    if not all(r["pass"] for r in real_c2) and stop("C2"):
        return doc
    for spec in BAND_CAPTURES:
        if spec.role != "control":
            continue
        b = bands[spec.bc]
        res = regimes.run_page(b, "F", params, T=params.T_c3, rungs=params.c3_rungs, log=log,
                               cb_ldpc=params.cb_ldpc, ldpc_pops=("P-a",))
        doc["page"] += res["page"]
        doc["ldpc"] += res["ldpc"]
        doc["yield"] += res["yield"]
        for n in COLD_SIZES:
            cd = regimes.run_cold(b, "F", n, params, rungs=params.c3_rungs,
                                  D_ldpc=(params.D_ldpc if (n != 8 or params.n8_ldpc) else 0), log=log)
            for k in ("coldstart", "gates", "ldpc", "yield"):
                doc[k] += cd[k]
            doc["collapse"].append(cd.get("collapse"))
        if spec.bc in DEADY_CONTROL_BCS:
            dy = regimes.run_deady(b, "F", params, sizes=COLD_SIZES, rungs=params.c3_rungs, log=log)
            doc["deadY"] += dy["deadY"]
            doc["ldpc"] += dy["ldpc"]
    c4 = []
    for bc1, bc2, name in TWO_CAPTURE_PAIRS:
        b1, b2 = load_pair(art, bc1, bc2, name)
        tc = twocap.run_twocap(b1, b2, params, T=params.T_page if name == "U12" else params.T_c3,
                               rungs=RUNGS if name == "U12" else params.c3_rungs, log=log, label=name)
        doc["twocapture"] += tc["twocapture"]
        doc["ldpc"] += tc["ldpc"]
        doc["yield"] += tc["yield"]
        c4.append({"band": name, "max_abs": tc["C4_max_abs"], "pass": tc["C4_max_abs"] <= 1e-9})
    doc["controls"]["C4"] = {"rows": c4, "pass": all(r["pass"] for r in c4)}
    if not doc["controls"]["C4"]["pass"] and stop("C4"):
        return doc
    doc["controls"]["C8"] = controls.c8_check(doc["page"], ec["C1"])
    doc["controls"]["C9"] = controls.c9_rows([c for c in doc["collapse"] if c], doc["deadY"])
    meta["wall_s"] = time.time() - t0
    from measure.cmy_calibration import decide
    if doc["failed_controls"]:
        doc["decisions"] = None
        doc["decisions_unratified"] = decide.decide(doc)
    else:
        doc["decisions"] = decide.decide(doc)
    write_json(out_path, doc)
    log(f"wrote {out_path} in {meta['wall_s'] / 60:.1f} min")
    return doc
