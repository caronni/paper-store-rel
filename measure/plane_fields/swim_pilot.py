#!/usr/bin/env python
"""THE SWIM — feasibility pilot on the W6 sheet-I qualification state.

docs/PLANE-FIELDS.md §6.5.5a ratified the swim as "per-plane local-affine
search, hint-seeded, likelihood-guided, ORACLE-GATED".  Before any of that
is built, one question decides whether the line is worth a wave:

    on a handful of residue tiles, does ANY per-plane sampling offset
    turn an uncertified tile into a CERTIFICATE — and do the cheap
    estimators (neighbour interpolation, own furniture) point at the
    offset that wins?

This instrument answers it for ~10 uncertified ``(tile, stream)`` slots,
producing THREE independent per-plane offset estimates and a decode
verdict for each:

  (a) NEIGHBOUR-DERIVED — every fully certified neighbour's per-plane
      offset measured by re-encoding its certificate and NCC-locking it
      against the scan (the W4 tier-i probe, ``_probe``), then
      INVERSE-DISTANCE interpolated to the target tile.
  (b) SWIM — the plane's sampling offset wiggled over a 1-D page-x grid
      (the measured dominant axis), each candidate re-sampled and
      DECODED; acceptance is the ordinary certificate gate, never a
      score.  A 2-D (x, y) grid opens only where 1-D stalls.
  (c) OWN-FURNITURE — the failed tile's own known cells (word sites,
      dust, and any certified sibling plane) NCC-locked directly.  For Y
      that is dust-only, which is exactly the "Y dust is noise" claim.

Everything is READ-ONLY: the W6 state, the three archived 2400 dpi
captures and the regmap-gt sidecar are opened for reading and nothing is
ever written outside ``scratch/plane-fields/swim-pilot/``.  The live
``I-multi-pf`` receiver's state directory is refused by construction
(``_swim_inputs.refuse_forbidden``).

    cd <repo>
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.swim_pilot --tiles 10
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

from . import _swim_figures, _swim_inputs, _swim_region, _swim_truth
from ._swim_inputs import CAPTURE_DPI, FORMAT_REF, OUT_DIR, QUAL_STATE
from ._swim_probes import (
    fit_crosstalk_for,
    neighbour_offsets,
    own_furniture_offset,
    residual_page_dots,
)
from ._swim_setup import (
    PAGE,
    LaneRasters,
    build_placements,
    best_pose_by_tile,
    certified_index,
    choose_lane,
    residue_by_column,
    restricted_placements,
    select_controls,
    select_targets,
)

SCHEMA = "plane-fields-swim-pilot-v1"
#: The engines are FIXED-600 devices (CLAUDE.md channel facts), so one
#: print dot is ``CAPTURE_DPI / PRINT_DPI`` scan pixels.  regmap-gt
#: reports its per-plane offsets in SCAN PIXELS (``_common.PX_PER_DOT``);
#: every number this pilot reports is in PRINT DOTS, so the supervised
#: profile is divided by that factor before any comparison.
PRINT_DPI = 600.0
#: 1-D swim grid: +/- GRID_MAX page dots in x, GRID_STEP dot spacing.
GRID_MAX = 1.0
GRID_STEP = 0.125
#: 2-D fallback, opened only for a target the 1-D sweep cannot certify.
GRID2D_MAX = 0.5
GRID2D_STEP = 0.25
FIT_RADIUS_TILES = 3


# --------------------------------------------------------------------------
# target selection
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# estimators (a) and (c): the tier-i NCC probe
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# (b) the swim
# --------------------------------------------------------------------------
def plane_delta(plane: int, dx: float, dy: float = 0.0) -> np.ndarray:
    """A ``(3, 2)`` page-dot delta that moves ONE plane and nothing else."""
    delta = np.zeros((3, 2), np.float64)
    delta[plane] = (dx, dy)
    return delta


def payload_surrogate(blocks, spec, address, plane: int) -> float:
    """Mean |LLR| over the tile's payload cells — the likelihood surrogate.

    Cheap, monotone in detector confidence, and computed from the SAME
    union tensor the decoder sees.  It guides and reports; it never
    accepts (the certificate gate does that, and only that).
    """
    from holo.format import pilots
    from holo.receive.evidence_blocks import tile_attempt_view

    components = tuple(row for row in blocks if row.address == address)
    if not components:
        return float("nan")
    view = tile_attempt_view(components)
    payload = pilots.color_payload_cell_indices(spec.family_seed)
    values = view.llr_cells_f64.reshape(4096, view.arity)[payload][:, plane]
    observed = view.observed_cells().reshape(4096)[payload]
    if not observed.any():
        return 0.0
    return float(np.abs(values[observed]).mean())


def capture_blocks_at(state, spec, target, delta) -> tuple:
    """One capture's blocks for the target tile at a per-plane delta."""
    fit, raster = state
    ordinals = fit.tile_rows.get(target.address, ())
    windows = []
    for ordinal in ordinals:
        features = _swim_region.window_features(
            fit, raster, spec, ordinal, delta)
        if features is None:
            continue
        windows.append(_swim_region.window_evidence(fit, ordinal, features))
    if not windows:
        return ()
    return _swim_region.capture_blocks(fit, spec, windows)


def union_verdict(per_capture_blocks, spec, target, *,
                  retry150: bool = True) -> dict:
    """The oracle over the union of every capture's blocks for this tile.

    Production spends a SELECTIVE retry150 on its residue before the
    close, so a pilot that judged the swim on the 60-iteration union
    alone would under-report it.  Each candidate therefore gets the
    ordinary UNION attempt and, only if that fails, the RETRY150 attempt
    — two distinct attempt identities, exactly as the receiver mints
    them, and either one's certificate is a pass.
    """
    blocks = tuple(row for rows in per_capture_blocks for row in rows)
    if not blocks:
        return {"certified": False, "reason": "no blocks"}
    stages = [_swim_region.AttemptStage.UNION]
    if retry150:
        stages.append(_swim_region.AttemptStage.RETRY150)
    row: dict = {"certified": False, "reason": "no components"}
    for stage in stages:
        result = _swim_region.attempt(
            blocks, spec, target.address, target.stream, stage=stage)
        if result is None:
            break
        record = result.record
        row = {
            "certified": result.certificate is not None,
            "stage": stage.value,
            "state": record.state.value,
            "n_informative": int(record.n_informative),
            "n_iters": int(record.n_iters),
            "syndrome_ok": record.syndrome_ok,
            "crc_ok": record.crc_ok,
            "certificate_id": (None if result.certificate is None
                               else result.certificate.certificate_id),
        }
        if row["certified"]:
            break
    row["surrogate"] = payload_surrogate(
        blocks, spec, target.address, target.plane)
    return row


def swim_target(states, spec, target, *, grid, grid2d) -> dict:
    """(b): sweep the plane's sampling offset; the certificate gate accepts."""
    started = time.time()
    candidates: list[dict] = []
    certified: list[dict] = []
    for dx in grid:
        delta = plane_delta(target.plane, float(dx))
        blocks = [capture_blocks_at(state, spec, target, delta)
                  for state in states.values()]
        verdict = union_verdict(blocks, spec, target)
        row = {"dx": float(dx), "dy": 0.0, **verdict}
        candidates.append(row)
        if row["certified"]:
            certified.append(row)
    if not certified and grid2d:
        for dy in grid2d:
            for dx in grid:
                delta = plane_delta(target.plane, float(dx), float(dy))
                blocks = [capture_blocks_at(state, spec, target, delta)
                          for state in states.values()]
                verdict = union_verdict(blocks, spec, target)
                row = {"dx": float(dx), "dy": float(dy), **verdict}
                candidates.append(row)
                if row["certified"]:
                    certified.append(row)
            if certified:
                break
    scores = np.asarray([row.get("surrogate", np.nan) for row in candidates])
    best = int(np.nanargmax(scores)) if np.isfinite(scores).any() else 0
    plateau = list(certified)
    # The reported winner is the certified candidate the surrogate ranks
    # highest — every member of the plateau is an equally valid pass of
    # the gate, so the tie-break has to be stated rather than implied.
    won = (max(plateau, key=lambda row: row.get("surrogate", -np.inf))
           if plateau else None)
    return {
        "candidates_attempted": len(candidates),
        "certified_any": bool(certified),
        "winning": (None if won is None else
                    {"dx": won["dx"], "dy": won["dy"]}),
        "plateau_width": len(plateau),
        "plateau": [(row["dx"], row["dy"]) for row in plateau],
        "unique_winner": len(plateau) == 1,
        "surrogate_argmax": {"dx": candidates[best]["dx"],
                             "dy": candidates[best]["dy"]},
        "seconds": round(time.time() - started, 2),
        "curve": candidates,
    }


# --------------------------------------------------------------------------
# one target: three estimates, four verdicts
# --------------------------------------------------------------------------
def ber_curve(states, spec, target, truth_bits, grid) -> dict:
    """CELL error rate against the printed truth, versus sampling offset.

    The oracle is binary and silent about mechanism; this is the
    measurement behind it.  Sheet I closed VERIFIED, so the exact printed
    cells of an UNCERTIFIED tile are recoverable from the recovered
    payload (``_swim_truth``, validated on certified tiles first).  A
    swim that cannot certify still tells us whether the offset it chose
    was RIGHT — the BER minimum — and whether the minimum is anywhere
    near the code's threshold.
    """
    from holo.receive.evidence_blocks import tile_attempt_view

    payload_indices, truth = _swim_truth.tile_truth(
        truth_bits, target.address, target.plane, spec)
    rows: list[dict] = []
    for dx in grid:
        delta = plane_delta(target.plane, float(dx))
        blocks = tuple(
            row for state in states.values()
            for row in capture_blocks_at(state, spec, target, delta))
        components = tuple(row for row in blocks
                           if row.address == target.address)
        if not components:
            continue
        entry = _swim_truth.hard_decision_ber(
            tile_attempt_view(components), payload_indices, truth,
            target.plane, ink_is_positive=True)
        rows.append({"dx": float(dx), **entry})
    if not rows:
        return {"points": []}
    bers = np.asarray([row["ber"] for row in rows], np.float64)
    best = int(np.nanargmin(bers))
    return {
        "points": rows,
        "ink_fraction_truth": float(truth.mean()),
        "ber_at_zero": float(
            next(row["ber"] for row in rows if row["dx"] == 0.0)),
        "ber_min": float(bers[best]),
        "ber_argmin_dx": rows[best]["dx"],
    }


def _fit_for(fits, capture_sha256: str, address):
    """The restricted-region fit that carries this tile, and its ordinals."""
    best = None
    for region_index, fit in sorted(fits.get(capture_sha256, {}).items()):
        if fit.selected_fit is None:
            continue
        ordinals = fit.tile_rows.get(address, ())
        if ordinals and (best is None or len(ordinals) > len(best[1])):
            best = (fit, ordinals, region_index)
    return best


def run_targets(facts, spec, lane, targets, fits, rasters, scans,
                fit_certificates, grid, grid2d, truth_bits=None,
                ber_tiles: int = 0) -> list[dict]:
    """Every target's three offset estimates and four decode verdicts.

    THE PROBES SEE ONLY ``fit_certificates`` (2026-08-22 review fix).  A
    reproduction control withholds its own Y certificate, and building
    the probe index from the FULL certificate set handed that certificate
    straight back through the own-furniture estimator: the control got a
    full-tile template where a real residue tile has ~14 dust cells, so
    control and target were never on the same footing.  The same index
    decides which neighbours count as certified, so a withheld control is
    also not offered to its neighbours as a template.
    """
    certificates_by_address: dict = {}
    for record in fit_certificates:
        certificates_by_address.setdefault(
            (int(record.page), *(int(v) for v in record.tile_yx)),
            []).append(record)
    index = certified_index(fit_certificates)
    poses_by_tile = {
        capture.source_sha256: best_pose_by_tile(
            facts.poses_for(capture.source_sha256, lane.lane_id),
            lane.lane_id)
        for capture in facts.captures}
    px_per_dot = CAPTURE_DPI / PRINT_DPI
    columns = {row["tx"]: row for row in _swim_inputs.regmap_gt_columns()}
    dy_rel = np.asarray(
        [columns[tx]["dY_rel_x"] for tx in sorted(columns)]) / px_per_dot
    dy_rel_mean = float(np.mean(dy_rel))

    crosstalk: dict[str, tuple[float, float]] = {}
    null_proved: dict[str, dict] = {}
    ber_budget = int(ber_tiles)
    rows: list[dict] = []
    for target in targets:
        mark = time.time()
        states: dict[str, tuple] = {}
        ordinals_by_capture: dict[str, tuple] = {}
        for capture in facts.captures:
            found = _fit_for(fits, capture.source_sha256, target.address)
            if found is None:
                continue
            fit, ordinals, _region = found
            states[capture.source_sha256] = (
                fit, rasters[capture.source_sha256])
            ordinals_by_capture[capture.source_sha256] = ordinals
        if not states:
            rows.append({"tile_y": target.tile_y, "tile_x": target.tile_x,
                         "stream": target.stream, "band": target.band,
                         "role": target.role,
                         "error": "no restricted-region window carries it"})
            continue
        for sha, (fit, raster) in states.items():
            if sha not in null_proved:
                null_proved[sha] = _swim_region.null_proof(
                    fit, raster, spec, ordinals_by_capture[sha][0])

        estimates = {"neighbour": {}, "own": {}}
        for sha, (fit, _raster) in states.items():
            path = scans[sha]
            if sha not in crosstalk:
                crosstalk[sha] = fit_crosstalk_for(
                    spec, path, poses_by_tile[sha], certificates_by_address,
                    index)
            estimates["neighbour"][sha] = neighbour_offsets(
                spec, path, crosstalk[sha], poses_by_tile[sha],
                certificates_by_address, index, target.address, target.plane,
                radius=3, min_neighbours=4)
            pose = poses_by_tile[sha].get(target.address)
            estimates["own"][sha] = (
                {"offset_dots_xy": None, "error": "no committed pose"}
                if pose is None else own_furniture_offset(
                    spec, path, crosstalk[sha], pose, target.address,
                    certificates_by_address.get(target.address, ()),
                    target.plane))

        zeros = {sha: residual_page_dots(
            fit, spec, ordinals_by_capture[sha][0], target.plane)
            for sha, (fit, _raster) in states.items()}

        def deltas(kind: str) -> dict:
            out: dict[str, np.ndarray] = {}
            for sha in states:
                offset = estimates[kind][sha].get("offset_dots_xy")
                if offset is None:
                    continue
                out[sha] = np.asarray(offset, np.float64) - np.asarray(
                    zeros[sha], np.float64)
            return out

        def verdict_at(per_capture: dict, label: str) -> dict:
            blocks = []
            for sha, (fit, raster) in states.items():
                delta = per_capture.get(sha)
                blocks.append(capture_blocks_at(
                    (fit, raster), spec, target,
                    None if delta is None
                    else plane_delta(target.plane, float(delta[0]),
                                     float(delta[1]))))
            return {"label": label,
                    "delta_by_capture": {
                        sha: [float(value) for value in row]
                        for sha, row in per_capture.items()},
                    **union_verdict(blocks, spec, target)}

        baseline = verdict_at({}, "delta=0")
        neighbour_deltas = deltas("neighbour")
        own_deltas = deltas("own")
        verdict_a = (verdict_at(neighbour_deltas, "(a) neighbour-derived")
                     if neighbour_deltas else
                     {"label": "(a) neighbour-derived", "certified": False,
                      "reason": "no usable neighbour probe"})
        verdict_c = (verdict_at(own_deltas, "(c) own-furniture")
                     if own_deltas else
                     {"label": "(c) own-furniture", "certified": False,
                      "reason": "no usable own-furniture lock"})
        swim = swim_target(states, spec, target, grid=grid,
                           grid2d=(() if baseline["certified"] else grid2d))

        def mean_delta(rowset: dict) -> float | None:
            if not rowset:
                return None
            return float(np.mean([row[0] for row in rowset.values()]))

        column = columns.get(target.tile_x, {})
        rows.append({
            "page": target.page, "tile_y": target.tile_y,
            "tile_x": target.tile_x, "stream": target.stream,
            "plane": target.plane, "band": target.band, "role": target.role,
            "siblings_certified": list(target.siblings_certified),
            "captures": sorted(states),
            "windows_by_capture": {sha: len(value)
                                   for sha, value in
                                   ordinals_by_capture.items()},
            "null_proof_delta0": {sha: null_proved[sha] for sha in states},
            "zero_is_residual_page_dots": zeros,
            "estimates": estimates,
            "delta_neighbour_dx": mean_delta(neighbour_deltas),
            "delta_own_dx": mean_delta(own_deltas),
            "regmap_gt": {
                "dY_rel_x_scan_px": column.get("dY_rel_x"),
                "dY_rel_x_dots": (
                    None if not column else
                    float(column["dY_rel_x"] / px_per_dot)),
                "dY_rel_x_centred": (
                    None if not column else
                    float(column["dY_rel_x"] / px_per_dot - dy_rel_mean)),
                "column_residue_033_4": column.get("residue")},
            "verdicts": {"baseline": baseline, "neighbour": verdict_a,
                         "own": verdict_c},
            "swim": swim,
            "seconds": round(time.time() - mark, 1),
        })
        winner = swim["winning"]
        print(f"  {target.tile_y:>2},{target.tile_x:<2} {target.stream} "
              f"[{target.band[:4]}/{target.role[:6]}] "
              f"d0={'CERT' if baseline['certified'] else 'fail'} "
              f"(a)={'CERT' if verdict_a.get('certified') else 'fail'} "
              f"(c)={'CERT' if verdict_c.get('certified') else 'fail'} "
              f"swim={'CERT@%+.3f' % winner['dx'] if winner else 'fail'} "
              f"[{swim['candidates_attempted']} cand, "
              f"{swim['seconds']:.0f}s] "
              f"est a={rows[-1]['delta_neighbour_dx']} "
              f"c={rows[-1]['delta_own_dx']}")
        if truth_bits is not None and ber_budget > 0:
            rows[-1]["ber_curve"] = ber_curve(
                states, spec, target, truth_bits, grid)
            ber_budget -= 1
            curve = rows[-1]["ber_curve"]
            if curve["points"]:
                print(f"       truth BER {curve['ber_at_zero']:.4f} at "
                      f"delta=0 -> {curve['ber_min']:.4f} at "
                      f"{curve['ber_argmin_dx']:+.3f} "
                      f"(ink {curve['ink_fraction_truth']:.3f})")
    return rows


def refit_spot_check(spec, targets, report, fits, rasters, patches_by_capture,
                     fit_certificates, lane, *, count: int) -> list[dict]:
    """The brief's required spot-check: per-candidate REFIT, same verdict?

    The frozen detector is the pilot's load-bearing approximation.  For up
    to ``count`` targets this re-runs the WHOLE restricted region with the
    target's windows sampled at the chosen delta BEFORE the fit — so the
    detector, its A5 context bins and the emission all see the shifted
    evidence — and compares the verdict with the frozen-detector one.

    RANKED RESIDUE-FIRST (2026-08-22 review fix).  The old order put
    certified rows first, so the approximation was only ever validated on
    the two clear-band controls — the population where it is benign
    rather than the one it stresses.
    """
    by_address = {(row["page"], row["tile_y"], row["tile_x"], row["stream"]):
                  row for row in report if "error" not in row}
    ranked = sorted(
        (row for row in targets
         if (row.page, row.tile_y, row.tile_x, row.stream) in by_address),
        key=lambda row: (
            0 if row.band == "dead" and row.role == "target" else 1,
            row.tile_x, row.tile_y))
    rows: list[dict] = []
    for target in ranked[:count]:
        entry = by_address[(target.page, target.tile_y, target.tile_x,
                            target.stream)]
        swim = entry["swim"]
        chosen = swim["winning"] or swim["surrogate_argmax"]
        delta = plane_delta(target.plane, chosen["dx"], chosen["dy"])
        states: dict[str, tuple] = {}
        for sha, by_region in fits.items():
            found = _fit_for(fits, sha, target.address)
            if found is None:
                continue
            _old, _ordinals, region_index = found
            patches = patches_by_capture[sha].get(region_index, ())
            if not patches:
                continue
            region_id = (f"{sha}/{lane.lane_id}/region-{region_index}/"
                         f"page-{PAGE}")
            from holo.receive.payload_model import EvidenceSource

            del _old
            refit = _swim_region.fit_region(
                spec, rasters[sha], EvidenceSource(sha, lane.lane_id),
                patches, fit_certificates, PAGE, region_id,
                keep_features_for=frozenset({target.address}),
                refit_deltas={target.address: delta})
            if refit.selected_fit is None:
                continue
            states[sha] = (refit, rasters[sha])
        if not states:
            continue
        blocks = [capture_blocks_at(state, spec, target, None)
                  for state in states.values()]
        refit_verdict = union_verdict(blocks, spec, target)
        rows.append({
            "page": target.page, "tile_y": target.tile_y,
            "tile_x": target.tile_x, "stream": target.stream,
            "delta": chosen,
            "frozen_detector_certified": bool(swim["certified_any"]),
            "refit_certified": bool(refit_verdict["certified"]),
            "verdict_changed": (bool(swim["certified_any"])
                                != bool(refit_verdict["certified"])),
            "refit_verdict": refit_verdict,
            "refit_heldout_logloss": {
                sha: state[0].heldout_loss for sha, state in states.items()},
            # The proof the delta reached this capture's features at all:
            # ``fit_region`` raises rather than returning a fit whose
            # selected arm equals its own zero.
            "refit_probe": {sha: state[0].refit_probe
                            for sha, state in states.items()},
        })
        print(f"  spot-check {target.tile_y},{target.tile_x}/"
              f"{target.stream} @ dx={chosen['dx']:+.3f} "
              f"dy={chosen['dy']:+.3f}: frozen="
              f"{'CERT' if swim['certified_any'] else 'fail'} "
              f"refit={'CERT' if refit_verdict['certified'] else 'fail'}")
    return rows


def _ber_cliff(rows: list[dict]) -> dict:
    """Where the certificate gate sits on the ground-truth BER axis.

    Every candidate offset is one (cell BER, certified?) pair, so the
    pilot can state the decode threshold as a MEASURED interval rather
    than a constant: the worst BER that still certified, and the best
    BER that did not.
    """
    certified: list[float] = []
    failed: list[float] = []
    for row in rows:
        curve = row.get("ber_curve") or {}
        gate = {entry["dx"]: bool(entry.get("certified"))
                for entry in row["swim"]["curve"] if entry["dy"] == 0.0}
        for point in curve.get("points", ()):
            value = point.get("ber")
            if value is None:
                continue
            (certified if gate.get(point["dx"]) else failed).append(
                float(value))
    return {
        "certified_candidates": len(certified),
        "failed_candidates": len(failed),
        "worst_certified_ber": max(certified) if certified else None,
        "best_certified_ber": min(certified) if certified else None,
        "best_failed_ber": min(failed) if failed else None,
        "reachable_by_translation": [
            {"tile_y": row["tile_y"], "tile_x": row["tile_x"],
             "band": row["band"], "role": row["role"],
             "ber_at_zero": (row.get("ber_curve") or {}).get("ber_at_zero"),
             "ber_min": (row.get("ber_curve") or {}).get("ber_min"),
             "ber_argmin_dx": (row.get("ber_curve") or {}).get(
                 "ber_argmin_dx")}
            for row in rows if row.get("ber_curve", {}).get("points")],
    }


def summarise(report: list[dict], residue: dict) -> dict:
    """The pilot's headline: who certified, who agreed, what it cost."""
    from scipy import stats

    rows = [row for row in report if "error" not in row]
    targets = [row for row in rows if row["role"] == "target"]
    controls = [row for row in rows if row["role"] != "target"]

    def certified(rowset, key: str) -> int:
        if key == "swim":
            return sum(1 for row in rowset if row["swim"]["certified_any"])
        return sum(1 for row in rowset
                   if row["verdicts"][key].get("certified"))

    def gap(row, left: str, right: str):
        values = {
            "neighbour": row.get("delta_neighbour_dx"),
            "own": row.get("delta_own_dx"),
            "swim": (None if row["swim"]["winning"] is None
                     else row["swim"]["winning"]["dx"]),
            "surrogate": row["swim"]["surrogate_argmax"]["dx"],
            "regmap": (row["regmap_gt"] or {}).get("dY_rel_x_centred"),
        }
        a, b = values[left], values[right]
        return None if a is None or b is None else abs(float(a) - float(b))

    def spearman(left: str, right: str):
        pairs = [(row.get("delta_neighbour_dx") if left == "neighbour"
                  else row.get("delta_own_dx") if left == "own"
                  else row["swim"]["surrogate_argmax"]["dx"],
                  (row["regmap_gt"] or {}).get("dY_rel_x_centred")
                  if right == "regmap" else None)
                 for row in targets if row["stream"] == "Y"]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if len(pairs) < 4:
            return None
        result = stats.spearmanr([a for a, _ in pairs],
                                 [b for _, b in pairs])
        return {"rho": float(result.statistic),
                "p": float(result.pvalue), "n": len(pairs)}

    dead = [row for row in targets if row["band"] == "dead"]
    return {
        "n_targets": len(targets), "n_controls": len(controls),
        "certified": {
            "targets": {key: certified(targets, key) for key in
                        ("baseline", "neighbour", "own", "swim")},
            "controls": {key: certified(controls, key) for key in
                         ("baseline", "neighbour", "own", "swim")},
            "targets_neither": sum(
                1 for row in targets
                if not row["swim"]["certified_any"]
                and not row["verdicts"]["neighbour"].get("certified")
                and not row["verdicts"]["own"].get("certified")),
            "dead_band_targets": len(dead),
            "dead_band_swim_certified": sum(
                1 for row in dead if row["swim"]["certified_any"]),
        },
        "offset_agreement_dots": [
            {"tile_y": row["tile_y"], "tile_x": row["tile_x"],
             "stream": row["stream"], "band": row["band"],
             "role": row["role"],
             "neighbour_dx": row.get("delta_neighbour_dx"),
             "own_dx": row.get("delta_own_dx"),
             "swim_dx": (None if row["swim"]["winning"] is None
                         else row["swim"]["winning"]["dx"]),
             "surrogate_argmax_dx": row["swim"]["surrogate_argmax"]["dx"],
             "regmap_dY_rel_x_centred":
                 (row["regmap_gt"] or {}).get("dY_rel_x_centred"),
             "|a-b|": gap(row, "neighbour", "swim"),
             "|c-b|": gap(row, "own", "swim"),
             "|a-c|": gap(row, "neighbour", "own"),
             "|a-regmap|": gap(row, "neighbour", "regmap"),
             "|argmax-regmap|": gap(row, "surrogate", "regmap")}
            for row in rows],
        "sinusoid_reproduction": {
            "neighbour_vs_regmap": spearman("neighbour", "regmap"),
            "own_vs_regmap": spearman("own", "regmap"),
            "surrogate_argmax_vs_regmap": spearman("surrogate", "regmap"),
        },
        "ber_cliff": _ber_cliff(rows),
        "cost": {
            "candidates_per_target_mean": (
                None if not rows else float(np.mean(
                    [row["swim"]["candidates_attempted"] for row in rows]))),
            "swim_seconds_per_target_mean": (
                None if not rows else float(np.mean(
                    [row["swim"]["seconds"] for row in rows]))),
            "total_seconds_per_target_mean": (
                None if not rows else float(np.mean(
                    [row["seconds"] for row in rows]))),
            "open_Y_slots_on_sheet": int(sum(residue["Y"])),
        },
    }


def _draw(report: dict, tag: str) -> None:
    """The two figures: per-target offsets, and the decode cliff."""
    rows = [row for row in report["targets"] if "error" not in row]
    offsets = [{
        "tile_y": row["tile_y"], "tile_x": row["tile_x"],
        "stream": row["stream"], "role": row["role"],
        "neighbour_dx": row.get("delta_neighbour_dx"),
        "own_dx": row.get("delta_own_dx"),
        "swim_dx": (None if row["swim"]["winning"] is None
                    else row["swim"]["winning"]["dx"]),
        "regmap_dx": (row["regmap_gt"] or {}).get("dY_rel_x_centred"),
        "plateau_dx": [dx for dx, dy in row["swim"]["plateau"] if dy == 0.0],
    } for row in rows]
    if offsets:
        _swim_figures.draw_offsets(
            OUT_DIR / f"offsets-{tag}.png", offsets,
            title=("swim pilot — per-plane sampling offset estimates, "
                   "page dots relative to the PlaneResidual zero"))
    # Certified curves first (the gate actually fires there), then the
    # dead-band residue: those are the two things worth looking at.
    ranked = sorted(rows, key=lambda row: (
        0 if row["swim"]["certified_any"] else 1,
        0 if row["band"] == "dead" else 1, row["tile_x"]))
    curves = []
    for row in ranked[:4]:
        curve = [entry for entry in row["swim"]["curve"]
                 if entry["dy"] == 0.0]
        if len(curve) < 3:
            continue
        ber = row.get("ber_curve") or {}
        by_dx = {point["dx"]: point.get("ber")
                 for point in ber.get("points", ())}
        curves.append({
            "label": (f"page {row['page']} tile ({row['tile_y']},"
                      f"{row['tile_x']}) stream {row['stream']} "
                      f"[{row['band']}/{row['role']}]"),
            "offsets": [entry["dx"] for entry in curve],
            "scores": [entry.get("surrogate", float("nan"))
                       for entry in curve],
            "certified": [bool(entry.get("certified")) for entry in curve],
            "bers": ([by_dx.get(entry["dx"]) for entry in curve]
                     if by_dx else None),
            "neighbour_dx": row.get("delta_neighbour_dx"),
            "own_dx": row.get("delta_own_dx"),
            "regmap_dx": (row["regmap_gt"] or {}).get("dY_rel_x_centred"),
            "note": ("certified at "
                     + ", ".join(f"{dx:+.3f}" for dx, _dy
                                 in row["swim"]["plateau"])
                     if row["swim"]["plateau"]
                     else "no candidate certified"
                          + (f"; truth BER {ber['ber_at_zero']:.3f} at 0 -> "
                             f"{ber['ber_min']:.3f} at "
                             f"{ber['ber_argmin_dx']:+.3f}"
                             if ber.get("points") else "")),
        })
    if curves:
        _swim_figures.draw_cliff(
            OUT_DIR / f"cliff-{tag}.png", curves,
            title="swim pilot — decode outcome versus sampling offset")


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def _grid(maximum: float, step: float) -> np.ndarray:
    count = int(round(maximum / step))
    return np.round(np.arange(-count, count + 1) * step, 6)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plane_fields.swim_pilot", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", type=int, default=10,
                        help="how many uncertified (tile, stream) targets")
    parser.add_argument("--clear-band-targets", type=int, default=3,
                        help="of those, how many from OUTSIDE the dead bands")
    parser.add_argument("--reproduction-controls", type=int, default=2,
                        help="certified tiles decoded with their own "
                             "certificates withheld (does the restricted "
                             "fit reproduce a production certificate?)")
    parser.add_argument("--fit-radius", type=int, default=FIT_RADIUS_TILES,
                        help="detector-fit population radius in tiles; "
                             "-1 fits the WHOLE region (production "
                             "population, full cost)")
    parser.add_argument("--grid-max", type=float, default=GRID_MAX)
    parser.add_argument("--grid-step", type=float, default=GRID_STEP)
    parser.add_argument("--no-grid2d", action="store_true",
                        help="skip the (x, y) fallback for stalled targets")
    parser.add_argument("--ber-tiles", type=int, default=0,
                        help="targets that also get a GROUND-TRUTH cell-BER "
                             "curve, rebuilt from the closed volume")
    parser.add_argument("--q", type=float, default=0.9,
                        help="the emission's source fraction (sheet I: 0.9); "
                             "validated against real certificates")
    parser.add_argument("--spot-checks", type=int, default=2,
                        help="targets re-run with a per-candidate REFIT")
    parser.add_argument("--lane", default=None,
                        help="force one lane id instead of choosing")
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--redraw", default=None,
                        help="re-derive the SUMMARY and re-render the "
                             "figures from an existing results JSON, then "
                             "exit — the raw per-candidate rows are the "
                             "record and are never touched")
    parser.add_argument("--tag", default="v1")
    args = parser.parse_args(argv)

    if args.redraw:
        path = Path(args.redraw)
        report = json.loads(path.read_text())
        report["summary"] = summarise(
            report["targets"], report["residue_by_column"])
        path.write_text(json.dumps(report, indent=1, sort_keys=True,
                                   default=str))
        _draw(report, args.tag)
        print(f"re-scored and redrew {path}")
        return 0

    from holo.format.resolve import resolve_format_ref

    started = time.time()
    tree_before = _swim_inputs.tree_state()
    facts = _swim_inputs.read_facts(rebuild=args.rebuild_cache)
    spec = resolve_format_ref(FORMAT_REF)
    scans = _swim_inputs.verified_scan_paths()
    index = certified_index(facts.certificates)
    residue = residue_by_column(index, spec.layout.tiles_yx)
    targets = select_targets(
        index, spec.layout.tiles_yx, n_tiles=args.tiles,
        n_clear=args.clear_band_targets,
        n_controls=args.reproduction_controls, seed=args.seed)
    lane, coverage = choose_lane(facts, targets, forced=args.lane)
    targets = targets + select_controls(
        facts, index, lane, targets, count=args.reproduction_controls,
        radius=args.fit_radius, seed=args.seed)
    grid = _grid(args.grid_max, args.grid_step)
    grid2d = () if args.no_grid2d else tuple(
        float(value) for value in _grid(GRID2D_MAX, GRID2D_STEP)
        if value != 0.0)
    # A control withholds ONE stream's certificate, never the tile's whole
    # certificate set: the point is to present the detector with exactly
    # the shape of a Y-only residue tile.
    withheld = frozenset(
        (*row.address, row.stream) for row in targets
        if row.role.startswith("reproduction-control"))
    fit_certificates = tuple(
        row for row in facts.certificates
        if (int(row.page), *(int(v) for v in row.tile_yx), row.stream_id)
        not in withheld)

    print(f"state {facts.state_sha256[:12]}… {facts.close_status} "
          f"certs {len(facts.certificates)} lane {lane.lane_id} "
          f"coverage {coverage}")
    print("targets: " + ", ".join(
        f"{row.tile_y},{row.tile_x}/{row.stream}[{row.band[:1]}"
        f"{'C' if row.role != 'target' else ''}]" for row in targets))

    from holo.receive.payload_model import EvidenceSource

    states: dict[str, tuple] = {}
    rasters_by_capture: dict[str, LaneRasters] = {}
    fits: dict[str, dict[int, object]] = {}
    patches_by_capture: dict[str, dict] = {}
    setup: list[dict] = []
    for capture in facts.captures:
        mark = time.time()
        holder = LaneRasters(spec, capture, scans[capture.source_sha256])
        rasters_by_capture[capture.source_sha256] = holder
        raster = holder.for_lane(lane)
        placements, _pose_by_patch = build_placements(
            facts, spec, capture, lane, raster)
        placed_s = time.time() - mark
        grouped = restricted_placements(
            placements, targets, args.fit_radius)
        patches_by_capture[capture.source_sha256] = grouped
        source = EvidenceSource(capture.source_sha256, lane.lane_id)
        keep = frozenset(row.address for row in targets)
        by_region: dict[int, object] = {}
        for region_index, patches in sorted(grouped.items()):
            region_id = (f"{capture.source_sha256}/{lane.lane_id}/"
                         f"region-{region_index}/page-{PAGE}")
            fit = _swim_region.fit_region(
                spec, raster, source, patches, fit_certificates, PAGE,
                region_id, keep_features_for=keep)
            by_region[region_index] = fit
        fits[capture.source_sha256] = by_region
        states[capture.source_sha256] = raster
        setup.append({
            "capture": capture.source_sha256,
            "placements": len(placements),
            "place_committed_seconds": round(placed_s, 1),
            "regions": {
                str(key): {
                    "windows": value.n_windows, "labels": value.n_labels,
                    "adopted_A1": value.adopted,
                    "heldout_logloss": value.heldout_loss,
                    "refusal": value.refusal}
                for key, value in by_region.items()},
            "setup_seconds": round(time.time() - mark, 1),
        })
        print(f"  {capture.source_sha256[:12]}… placements "
              f"{len(placements)} in {placed_s:.0f}s; regions "
              + ", ".join(f"{key}:{value.n_windows}w/{value.n_labels}l"
                          f"{'*' if value.adopted else ''}"
                          for key, value in sorted(by_region.items()))
              + f"; total {time.time() - mark:.0f}s")

    truth_bits = None
    truth_report = None
    if args.ber_tiles > 0:
        payload = (QUAL_STATE.parent / "recovered.bin").read_bytes()
        mark = time.time()
        truth_bits, truth_report = _swim_truth.page_component_bits(
            spec, payload, args.q, PAGE)
        truth_report["validation"] = (
            _swim_truth.validate_against_certificates(
                truth_bits, spec, facts.certificates, sample=24))
        truth_report["seconds"] = round(time.time() - mark, 1)
        if not truth_report["validation"].get("exact"):
            raise SystemExit(
                f"the reconstructed printed field does NOT match the "
                f"certificates: {truth_report['validation']} — REFUSING "
                f"to report a BER against it")
        print(f"truth field rebuilt from recovered.bin in "
              f"{truth_report['seconds']}s, exact on "
              f"{truth_report['validation']['checked']} certified tiles")
    report = run_targets(facts, spec, lane, targets, fits, states, scans,
                         fit_certificates, grid, grid2d, truth_bits,
                         args.ber_tiles)
    del truth_bits
    spot = refit_spot_check(
        spec, targets, report, fits, states, patches_by_capture,
        fit_certificates, lane, count=args.spot_checks)
    for holder in rasters_by_capture.values():
        holder.release()

    tree_after = _swim_inputs.tree_state()
    out = {
        "schema": SCHEMA,
        "state": {"path": str(QUAL_STATE), "sha256": facts.state_sha256,
                  "close": facts.close_status,
                  "payload_sha256": facts.payload_sha256,
                  "certificates": len(facts.certificates),
                  "plan_lanes_appended_by_this_tree":
                      list(facts.plan_lanes_appended)},
        "format": {"ref": FORMAT_REF, "spec_id": spec.spec_id,
                   "tiles_yx": list(spec.layout.tiles_yx),
                   "cell_dots": spec.cell_dots, "dpi": CAPTURE_DPI},
        "lane": {"lane_id": lane.lane_id,
                 "target_ppc": lane.target_ppc_num / lane.target_ppc_den,
                 "target_coverage_by_capture": list(coverage)},
        "residue_by_column": residue,
        "grid": {"dx": [float(value) for value in grid],
                 "dy_fallback": list(grid2d),
                 "fit_radius_tiles": args.fit_radius},
        "approximations": [
            "restricted region: the detector is fitted over the windows "
            "within --fit-radius tiles of a target, not the whole page "
            "region",
            "frozen detector: ONE fit at delta = 0 scores every candidate; "
            "its A5 context bins are reused unchanged",
            "delta = 0 is the PlaneResidual (dial-OFF) sampling, not the "
            "W6 state's dial-ON field sampling",
            "the archived scale plan is a strict PREFIX of this tree's "
            "(u02-field appended); the state loads with the session-level "
            "spec binding skipped and the prefix asserted instead",
        ],
        "setup": setup,
        "truth_field": truth_report,
        "summary": summarise(report, residue),
        "targets": report,
        "refit_spot_checks": spot,
        "tree_before": tree_before,
        "tree_after": tree_after,
        "tree_moved": _swim_inputs.tree_moved(tree_before, tree_after),
        "wall_seconds": round(time.time() - started, 1),
        "peak_rss_gb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"swim-pilot-{args.tag}.json"
    path.write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    _draw(out, args.tag)
    print(f"\nwrote {path}")
    return 0


__all__ = ["SCHEMA", "ber_curve", "main", "payload_surrogate",
           "run_targets", "summarise", "swim_target", "union_verdict"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
