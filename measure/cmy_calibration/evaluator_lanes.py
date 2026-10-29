"""R31 — the four PAVA evaluators on the receiver's OWN colour lane: the A8 sim pages and e044 sheets A / B.

What: `color_region.region_job` runs unmodified (context head off: the chain is fitted before the context and the
context is not the evaluator's) with two pass-through spies installed for the process — `color_chain.fit_cmy_chain`
records the chain's population exactly as the head hands it (QDA held-out scores, state columns, furniture kinds,
site keys, erased streams, bound) and `color_region.evidence_with_divisor` records each evidence row's raw
W-relative scores (`cmy7_relative_scores` of the selected arm's features); thread-local, so lanes run in parallel.
Offline, per lane: the chain's fit side (`head_sub_split`, `&2`) and floors as built (`color_chain.map_refusal`),
the production map (`color_chain.fit_chain_map`) and its blocks (evaluator.checked_blocks, bit for bit), then the
four evaluators (evaluator.EVALUATORS) emitted as production emits (fold_hi_first, erasure, bound) on the lane's
CARGO cells — payload sites, never in the QDA's or the maps' fit — against the emitter's GT; the three-way gate
each evaluator's candidate would meet on the chain's validation side, and `gated:<evaluator>` = that evaluator where
its gate adopts, raw where it refuses (what the lane would emit).  The nulls: the evaluator the production lane
actually wore (centroid-logit when its gate adopted, raw when it refused) reproduces the emitted evidence rows, and
the recomputed centroid-logit gate reproduces production's verdict.
Populations:
  sim   the A8 probes' pages (_h3_sims_cmy: in register, offset, faint; the render's own pose, one whole-page
        window), no field / the planted field (offset), and the probes' paper-like emulation — seeded Gaussian
        noise sigma on the three features before the QDA (rng 20261012, a8probe/papernoise.py restated).
  e044  sheet B (c3-cmy-r0850@35x24) and sheet A (c2-cmy-r0775x0700@53x37), one 2400 dpi capture each, at
        TRUTH-FITTED poses (scorelane.py's poses, windows and truth arm, its module paths re-pointed here): COLD =
        one region over every window, FIRST-FIRE = each 200-cell window its own region, both furniture-only.
Why: R31's held-out re-measure on the chain as built (evaluator.py carries the R11 paper extracts).
How: renders and poses are cached under --out; every rng is seeded.

    PYTHONPATH=src:. env/bin/python -m measure.cmy_calibration.evaluator_lanes --stage sim
    ... --stage e044 --sheet B [--levels 0 1] [--workers 6]       (poses.json first, then the lanes)
    ... --stage e044 --sheet A [--levels 0 1]
Artefacts: --out (default scratch/cmy_calibration/evaluator-2026-10-12): render/,
evaluator-sim.json, e044-<sheet>/poses.json, evaluator-e044-<sheet>.json.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from holo.receiver import data
from holo.receiver.format import identity, tile_codec
from holo.receiver.lib import pava
from holo.receiver.plugins import color_chain, color_model, color_region, color_region_head, color_sites
from holo.receiver.plugins import color_region_ctx as ctxm
from measure.cmy_calibration import scorelane
from measure.cmy_calibration.chains import demap
from measure.cmy_calibration.evaluator import (DEFAULT_OUT, EVALUATORS, HEAD, Blocks, checked_blocks, evaluator_map,
                                               md, metrics, peak_rss_gb, table_row, weighted_groups)
from measure.cmy_calibration.run import write_json

CTX_OFF = color_region_head.StackConfig(context=ctxm.ContextConfig(variant=ctxm.CONTEXT_VARIANT_OFF))
NOISE_SEED = 20261012
REPRO_TOL = 1e-4
MapSlot = tuple[color_model.PavaMap, Blocks] | None
E044 = {"B": ("1i200-cmy-r0850-p120-v1@35x24", "E044-B-c3-cmy-r0850-hp-scan.tiff", "E044-B"),
        "A": ("1i300-cmy-r0775x0700-p120-v1@53x37", "E044-A-c2-cmy-r0775x0700-hp-scan.tiff", "E044-A")}
E044_ROOT = Path("scratch/e044")

# ---------------------------------------------------------------- the spies

_LOCAL = threading.local()
_ORIG_FIT = color_chain.fit_cmy_chain
_ORIG_EVIDENCE = color_region.evidence_with_divisor


def _spy_fit(scores: np.ndarray, columns: np.ndarray, kinds: np.ndarray, site_keys: np.ndarray,
             erased: tuple[int, ...], bound: float) -> color_chain.ChainFit:
    res = _ORIG_FIT(scores, columns, kinds, site_keys, erased, bound)
    _LOCAL.rec["chain"] = (np.array(scores, np.float64), np.array(columns, np.int64), np.array(kinds, np.int8),
                           np.array(site_keys, np.int64), tuple(erased), float(bound), res)
    return res


def _spy_evidence(fit: Any, features: np.ndarray, bins: Any, *rest: Any, **kw: Any) -> Any:
    if fit.detector is None:
        _LOCAL.rec["raw"].append(np.asarray(color_model.cmy7_relative_scores(fit.model, features), np.float64))
    return _ORIG_EVIDENCE(fit, features, bins, *rest, **kw)


def install_spies() -> None:
    color_chain.fit_cmy_chain = _spy_fit
    color_region.evidence_with_divisor = _spy_evidence


def remove_spies() -> None:
    color_chain.fit_cmy_chain = _ORIG_FIT
    color_region.evidence_with_divisor = _ORIG_EVIDENCE


def captured(job: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    """Run one region_job call with this thread's recorder; (its JobResult, what the spies saw)."""
    _LOCAL.rec = {"chain": None, "raw": []}
    try:
        return job(), _LOCAL.rec
    finally:
        _LOCAL.rec = None


# ---------------------------------------------------------------- the chain as built, four ways

def lane_maps(chain: tuple) -> tuple[list[MapSlot], list[str]]:
    """color_chain.fit_cmy_chain's maps (fit side, floors, erasure) with their blocks."""
    values, labels, _kinds, keys, erased, _bound, _res = chain
    fit = color_model.head_sub_split(keys)
    val = ~fit
    if 0 in erased:
        return [None, None, None], [color_chain.CHAIN_REASON_HI_ERASED] * 3
    maps: list[MapSlot] = []
    reasons: list[str] = []
    for i, (stream, _sib) in enumerate(color_chain.CHAIN_MAPS):
        refusal = (color_chain.MAP_REASON_ERASED if stream in erased
                   else color_chain.map_refusal(labels[fit], labels[val], i))
        reasons.append(refusal or color_chain.CHAIN_REASON_ADOPTED)
        if refusal:
            maps.append(None)
            continue
        pm = color_chain.fit_chain_map(values[fit], labels[fit], i)
        member, lab = color_chain.map_population(labels[fit], i)
        groups = weighted_groups(color_chain.chain_statistic(values[fit][member], i), lab[member],
                                 pava.class_balanced_weights(labels[fit][member], len(tile_codec.CMY_STATE_IDS)))
        maps.append((pm, checked_blocks(pm, groups)))
    return maps, reasons


def lane_emit(raw: np.ndarray, maps: list[MapSlot], ev: str, erased: tuple[int, ...], bound: float) -> np.ndarray:
    """One evaluator's emitted triple as evidence_with_divisor emits it (head, erasure, bound; context off)."""
    if ev == "raw" or all(m is None for m in maps):
        return color_chain._emitted(raw, erased, bound)
    fallback = color_chain.bounded(raw, bound)
    pieces = [color_chain.chain_statistic(fallback, i) if m is None
              else evaluator_map(ev, *m).llrs(color_chain.chain_statistic(raw, i)) for i, m in enumerate(maps)]
    return color_chain._emitted(color_chain.fold_hi_first(*pieces), erased, bound)


def lane_gates(chain: tuple, maps: list[MapSlot]) -> dict[str, Any]:
    """The three-way gate (fit_cmy_chain's) each evaluator's candidate meets on the validation side."""
    values, labels, kinds, keys, erased, bound, _res = chain
    val = ~color_model.head_sub_split(keys)
    if not np.any(val) or all(m is None for m in maps):
        return {ev: None for ev in EVALUATORS[1:]}
    inc = color_chain.gate_losses(color_chain._emitted(values[val], erased, bound), labels[val], kinds[val])
    out: dict[str, Any] = {"incumbent": inc}
    for ev in EVALUATORS[1:]:
        cand = color_chain.gate_losses(lane_emit(values[val], maps, ev, erased, bound), labels[val], kinds[val])
        out[ev] = {"adopted": bool(color_chain._three_way(cand, inc)), "candidate": cand}
    return out


def lane_record(row: identity.FormatRow, geometry: identity.SiteGeometry, res: Any, rec: dict[str, Any],
                states_of: Callable[[np.ndarray], np.ndarray]) -> dict[str, Any] | None:
    """One lane's populations: cargo forms per evaluator, its truth columns, the gate verdicts and the null."""
    evidence = [f for f in res.facts if isinstance(f, data.ColorEvidenceRow)]
    if rec["chain"] is None or not evidence:
        return None
    if len(evidence) != len(rec["raw"]):
        raise SystemExit(f"{len(evidence)} evidence rows vs {len(rec['raw'])} recorded raw arrays")
    chain = rec["chain"]
    maps, reasons = lane_maps(chain)
    worn = "centroid-logit" if chain[6].head is not None else "raw"
    raw = np.concatenate(rec["raw"])
    cells = np.concatenate([np.asarray(e.page_cells_yx, np.int64) for e in evidence])
    emitted = np.concatenate([np.asarray(e.values, np.float64) for e in evidence])
    emits = {ev: lane_emit(raw, maps, ev, chain[4], chain[5]) for ev in EVALUATORS}
    null = float(np.max(np.abs(emits[worn] - emitted))) if emitted.size else 0.0
    if null > REPRO_TOL:
        raise SystemExit(f"null failed: the worn evaluator {worn} misses the emitted rows by {null}")
    gates = lane_gates(chain, maps)
    logit_gate = gates.get("centroid-logit")
    if (logit_gate is not None and logit_gate["adopted"]) != (worn == "centroid-logit"):
        raise SystemExit(f"the recomputed gate disagrees with production's verdict {chain[6].reason}")
    for ev in EVALUATORS[1:]:
        emits[f"gated:{ev}"] = emits[ev] if gates.get(ev) and gates[ev]["adopted"] else emits["raw"]
    cargo = color_sites.cargo_row_indices(geometry, cells)
    columns = color_region_head.state_columns(row.state_ids, states_of(cells[cargo]))
    return {"forms": {ev: demap(t[cargo]) for ev, t in emits.items()}, "state": np.asarray(columns, np.int64),
            "cells": cells[cargo], "null_max_abs": null, "worn": worn, "production_reason": chain[6].reason,
            "map_reasons": reasons, "erased": list(chain[4]), "n_fit": int(np.count_nonzero(
                color_model.head_sub_split(chain[3]))), "n_validation": int(np.count_nonzero(
                    ~color_model.head_sub_split(chain[3]))),
            "maps": [None if m is None else {"blocks": int(m[1].values.size),
                                             "spanning": int(np.count_nonzero(m[1].last > m[1].first))} for m in maps],
            "gates": gates, "heldout_p99_max_abs": float(np.quantile(np.abs(chain[0]).max(1), 0.99))}


def summarise(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    """Pooled metrics per evaluator over lanes, lane-level gate tallies and the worst null."""
    ok = [x for x in lanes if x is not None]
    if not ok:
        return {"lanes": 0}
    rows = {ev: metrics(np.concatenate([x["forms"][ev] for x in ok]), np.concatenate([x["state"] for x in ok]))
            for ev in ok[0]["forms"]}
    gates = {ev: sum(bool(x["gates"].get(ev) and x["gates"][ev]["adopted"]) for x in ok) for ev in EVALUATORS[1:]}
    return {"lanes": len(ok), "rows": rows, "gate_adopted_lanes": gates,
            "worn": {w: sum(x["worn"] == w for x in ok) for w in ("raw", "centroid-logit")},
            "null_max_abs": max(x["null_max_abs"] for x in ok),
            "map_reasons": sorted({"/".join(x["map_reasons"]) for x in ok}),
            "heldout_p99_max_abs": [x["heldout_p99_max_abs"] for x in ok][:3]
            + ([float(np.median([x["heldout_p99_max_abs"] for x in ok]))] if len(ok) > 3 else []),
            "first_lane": {k: ok[0][k] for k in ("production_reason", "map_reasons", "maps", "gates", "n_fit",
                                                 "n_validation", "erased")}}


# ---------------------------------------------------------------- sim: the A8 probe pages

SIM_CONFIGS: tuple[tuple[str, float, bool], ...] = (
    ("cmy", 0.0, False), ("offset", 0.0, False), ("offset", 0.0, True), ("faint", 0.0, False),
    ("offset", 0.06, False), ("offset", 0.06, True), ("offset", 0.04, False), ("offset", 0.04, True),
    ("faint", 0.06, False), ("faint", 0.04, False), ("cmy", 0.06, False))


def sim_capture(render: Path, page: str) -> Any:
    from holo.receiver.tests import _h3_sims_cmy as s
    make, cap, sha, name = {"cmy": (s.make_cmy, s.capture_cmy, s.CMY_TIFF_SHA256, "cmy"),
                            "offset": (s.make_cmy_offset, s.capture_cmy_offset, s.CMY_OFFSET_TIFF_SHA256, "cmy-offset"),
                            "faint": (s.make_cmy_faint, s.capture_cmy_faint, s.CMY_FAINT_TIFF_SHA256, "cmy-faint")}[page]
    d = render / name
    c = cap(d) if (d / "cmy-emit").is_dir() and any(d.glob("*.tiff")) else None
    if c is None or c.tiff_sha256 != sha:
        make(d)
        c = cap(d)
    if c.tiff_sha256 != sha:
        raise SystemExit(f"render {page}: sha {c.tiff_sha256} vs {sha}")
    return c


def sim_geometry(cap: Any) -> tuple[identity.FormatRow, int]:
    row = identity.resolve_format_ref(cap.format_ref)
    return row, int(row.pitch_in * cap.dpi)


def sim_window(row: identity.FormatRow, pitch_px: int) -> color_region.RegionWindow:
    """test_h3_e2e_cmy._true_window restated: the whole page at the render's own pose."""
    from holo.receiver.tests import _h3_fixture_geometry as fg, _h3_sims
    cy, cx = row.cells_yx
    placement = fg.window_placement(("sim-cmy", 0, 0, (0, 0, cy, cx)),
                                    fg.page_native_affine(pitch_px, _h3_sims.COLOR_BORDER_DOTS * _h3_sims.UPSAMPLE - 0.5),
                                    fg.grid_cells((0, 0), (cy, cx)))
    return fg.window_pose(row, placement)


def sim_gt(cap: Any, row: identity.FormatRow) -> np.ndarray:
    """test_h3_e2e_cmy._gt_states restated: the emitter's GT page as presence ids per cell."""
    from holo.receiver.tests import _h3_sims
    planes = np.unpackbits(_h3_sims.load_emit_gt(cap), axis=-1)
    cy, cx = row.cells_yx
    step = planes.shape[1] // cy
    cells = planes[:, step // 2::step, step // 2::step][:, :cy, :cx]
    return tile_codec.planes_to_states(np.moveaxis(cells, 0, -1))


def planted_fields(row: identity.FormatRow) -> tuple[data.PlaneField, ...]:
    """test_h3_e2e_cmy._planted_fields restated: C zero, M and Y at CMY_OFFSET_PAGE_PX on every tile."""
    from holo.receiver.tests import _h3_sims, _h3_sims_cmy
    out = []
    for plane, offset_px in enumerate(_h3_sims_cmy.CMY_OFFSET_PAGE_PX):
        delta = np.zeros(row.tiles_yx + (2,), np.float64)
        delta[...] = np.asarray(offset_px, np.float64) / _h3_sims.UPSAMPLE
        out.append(data.PlaneField(page=0, plane=plane, delta_dots_xy=delta, support=np.ones(row.tiles_yx),
                                   uncertainty_dots=np.zeros(row.tiles_yx), n_observations=1, n_captures=1,
                                   ordinal=1))
    return tuple(out)


def noisy_inputs(sigma: float) -> Callable[..., Any]:
    """a8probe/papernoise.py's patch: N(0, sigma) on every base and corrected feature array, a fresh rng per call."""
    orig = color_region.build_region_inputs

    def build(*a: Any, **k: Any) -> Any:
        inp = orig(*a, **k)
        rng = np.random.default_rng(NOISE_SEED)

        def add(arrs: Any) -> Any:
            if arrs is None:
                return None
            return tuple(np.asarray(x, np.float64) + sigma * rng.standard_normal(np.shape(x)) for x in arrs)
        return replace(inp, base_tuple=add(inp.base_tuple), corrected=add(inp.corrected))
    return build


def stage_sim(out: Path) -> dict[str, Any]:
    import tifffile
    t0 = time.time()
    render = out / "render"
    results = []
    orig_build = color_region.build_region_inputs
    install_spies()
    try:
        for page, sigma, field in SIM_CONFIGS:
            t1 = time.time()
            cap = sim_capture(render, page)
            row, pitch_px = sim_geometry(cap)
            geometry = identity.build_site_geometry(row)
            image = tifffile.imread(cap.tiff)
            planes = tuple(SimpleNamespace(open=lambda c=c: image[..., c]) for c in range(3))
            gt = sim_gt(cap, row)
            color_region.build_region_inputs = noisy_inputs(sigma) if sigma else orig_build
            try:
                res, rec = captured(lambda: color_region.region_job(
                    row, geometry, (sim_window(row, pitch_px),), (), planes, {}, CTX_OFF, "sim-cmy", 0,
                    plane_fields=planted_fields(row) if field else None))
            finally:
                color_region.build_region_inputs = orig_build
            lane = lane_record(row, geometry, res, rec, lambda cells: gt[cells[:, 0], cells[:, 1]])
            summ = summarise([lane])
            summ.update({"page": page, "sigma": sigma, "field": field, "seconds": time.time() - t1})
            results.append(summ)
            r = summ.get("rows", {})
            print(f"sim {page} sigma {sigma} field {int(field)}: "
                  + "  ".join(f"{ev} {r[ev]['I_plain_hi']:.4f}/{r[ev]['I_plain_lo']:.4f}" for ev in r)
                  + f"  worn {summ.get('worn')} null {summ.get('null_max_abs', 0):.1e} ({time.time() - t1:.0f} s)",
                  flush=True)
    finally:
        remove_spies()
    doc = {"configs": results, "seconds": time.time() - t0, "peak_rss_gb": peak_rss_gb()}
    write_json(out / "evaluator-sim.json", doc)
    print(f"sim: wrote {out / 'evaluator-sim.json'} ({doc['seconds']:.0f} s, peak RSS {doc['peak_rss_gb']:.1f} GB)")
    return doc


# ---------------------------------------------------------------- e044: the receiver's lane on paper

def point_scorelane(sheet: str, art: Path) -> str:
    """scorelane's module paths re-pointed at this sheet's capture, manifest and GT (scratch/e044 on machine 1)."""
    fmt, scan, tag = E044[sheet]
    scorelane.ART = art
    scorelane.SCAN = E044_ROOT / "captures" / scan
    scorelane.MANIFEST = E044_ROOT / "jobs" / f"{tag}-manifest.json"
    scorelane.GT = E044_ROOT / "jobs" / f"{tag}-page000_gt.npy"
    scorelane.READOUT_SUMMARY = art / "absent-readout-summary.json"
    scorelane.FORMAT_REF = fmt
    scorelane.CAPTURE_ID = f"e044-{sheet}-scan"
    return fmt


def stage_e044(out: Path, sheet: str, level_indices: list[int], workers: int) -> dict[str, Any]:
    from holo.receiver.plugins.intake import build_levels
    from measure.e041_probe_readout import read_rgb
    t0 = time.time()
    art = out / f"e044-{sheet}"
    art.mkdir(parents=True, exist_ok=True)
    fmt = point_scorelane(sheet, art)
    if not (art / "poses.json").exists():
        scorelane.stage_poses(art, workers)
    poses = json.loads((art / "poses.json").read_text())
    row = identity.resolve_format_ref(fmt)
    geometry = identity.build_site_geometry(row)
    cell_dots = color_sites.cell_dots_of(row)
    man = json.loads(scorelane.MANIFEST.read_text())
    if tuple(man["page_cells_yx"]) != row.cells_yx or man["format_id"] != fmt:
        raise SystemExit("manifest vs the receiver's row: contract fork")
    origin = tuple(int(v) for v in man["origin_dots_yx"])
    states = scorelane.gt_states(row, cell_dots)
    truth = scorelane.truth_points(poses, origin, cell_dots, *row.cells_yx)
    img = read_rgb(scorelane.SCAN)
    levels = build_levels(scorelane.SCAN_DPI, row.pitch_in, img.shape[:2])
    print(f"e044 {sheet}: scan {img.shape}, levels ppc {[str(lv.ppc) for lv in levels]} ({time.time() - t0:.0f} s, "
          f"peak RSS {peak_rss_gb():.1f} GB)", flush=True)
    doc: dict[str, Any] = {"sheet": sheet, "format": fmt, "scan": str(scorelane.SCAN), "gt": str(scorelane.GT),
                           "poses": {k: poses[k] for k in ("orientation", "nonaffine", "offsets_vs_C_dots")},
                           "levels": {}}

    def states_of(cells: np.ndarray) -> np.ndarray:
        return states[cells[:, 0], cells[:, 1]]
    install_spies()
    try:
        for li in [i for i in level_indices if i < len(levels)]:
            t1 = time.time()
            level = levels[li]
            planes = scorelane.level_planes(img, level)
            windows, wstats = scorelane.level_windows(row, level, truth, float(poses["sub"]))
            offsets_of = scorelane.truth_offsets_of(truth, level.scale, windows, cell_dots)

            def lane(ws: tuple[color_region.RegionWindow, ...]) -> dict[str, Any] | None:
                res, rec = captured(lambda: color_region.region_job(
                    row, geometry, ws, (), planes, {}, CTX_OFF, scorelane.CAPTURE_ID, level.index,
                    offsets_of=offsets_of))
                return lane_record(row, geometry, res, rec, states_of)
            entry: dict[str, Any] = {"ppc": str(level.ppc), "windows": wstats}
            with ThreadPoolExecutor(max(1, workers)) as ex:
                cold = ex.submit(lane, windows)
                first = list(ex.map(lambda w: lane((w,)), windows))
                entry["cold"] = summarise([cold.result()])
            entry["first_fire"] = summarise(first)
            entry["first_fire_refused_lanes"] = sum(x is None for x in first)
            entry["seconds"] = time.time() - t1
            doc["levels"][str(li)] = entry
            r = entry["cold"].get("rows", {})
            print(f"e044 {sheet} level {li} ppc {level.ppc}: cold "
                  + "  ".join(f"{ev} {r[ev]['I_hi']:.4f}/{r[ev]['I_lo']:.4f}" for ev in r)
                  + f" ({entry['seconds']:.0f} s, peak RSS {peak_rss_gb():.1f} GB)", flush=True)
            write_json(out / f"evaluator-e044-{sheet}.json", doc)
    finally:
        remove_spies()
    doc["seconds"] = time.time() - t0
    doc["peak_rss_gb"] = peak_rss_gb()
    write_json(out / f"evaluator-e044-{sheet}.json", doc)
    print(f"e044 {sheet}: wrote evaluator-e044-{sheet}.json ({doc['seconds']:.0f} s, peak RSS {doc['peak_rss_gb']:.1f} GB)")
    return doc


# ---------------------------------------------------------------- report

def gate_cell(summary: dict[str, Any]) -> str:
    g = summary.get("gate_adopted_lanes", {})
    return " / ".join(f"{ev.split('-')[-1]} {g.get(ev, 0)}" for ev in EVALUATORS[1:])


def report_lanes(out: Path) -> str:
    parts = []
    if (out / "evaluator-sim.json").exists():
        doc = json.loads((out / "evaluator-sim.json").read_text())
        parts.append("## Sim pages (receiver lane, render pose, cargo cells; gate = three-way gate adopts, "
                     "linear / logit / edge)\n")
        for summary in doc["configs"]:
            if not summary.get("rows"):
                parts.append(f"{summary['page']} sigma {summary['sigma']} field {int(summary['field'])}: no lane\n")
                continue
            parts.append(f"### {summary['page']}, sigma {summary['sigma']}, field {'planted' if summary['field'] else 'none'} "
                         f"(n = {summary['rows']['raw']['n']}; worn {summary['worn']}; gate {gate_cell(summary)}; held-out max|summary| p99 "
                         f"{summary['heldout_p99_max_abs'][0]:.3g}; null {summary['null_max_abs']:.1e})\n")
            parts.append(md(HEAD + ["I plain hi / lo"],
                            [table_row(ev, r) + [f"{r['I_plain_hi']:.4f} / {r['I_plain_lo']:.4f}"]
                             for ev, r in summary["rows"].items()]) + "\n")
    for sheet in E044:
        path = out / f"evaluator-e044-{sheet}.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        parts.append(f"## e044 sheet {sheet} ({doc['format']}, truth-fitted poses, context off, cargo cells)\n")
        for li, entry in doc["levels"].items():
            for regime in ("cold", "first_fire"):
                summary = entry[regime]
                if not summary.get("rows"):
                    continue
                parts.append(f"### level {li} (ppc {entry['ppc']}), {regime}: {summary['lanes']} lanes, worn {summary['worn']}, "
                             f"gate {gate_cell(summary)}, null {summary['null_max_abs']:.1e}, map verdicts {summary['map_reasons']}\n")
                parts.append(md(HEAD, [table_row(ev, r) for ev, r in summary["rows"].items()]) + "\n")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", choices=("sim", "e044"), required=True)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--sheet", choices=tuple(E044), default="B")
    ap.add_argument("--levels", type=int, nargs="*", default=[0, 1])
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.stage == "sim":
        stage_sim(a.out)
    else:
        stage_e044(a.out, a.sheet, a.levels, a.workers)


if __name__ == "__main__":
    main()
