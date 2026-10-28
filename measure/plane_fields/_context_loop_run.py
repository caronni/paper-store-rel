"""The E8 run: two geometries, eight configurations, two passes.

Split out of :mod:`context_loop` so the measurement seams stay next to
each other and the driving stays here.  The setup is
``_state_context_run.run``'s, function for function — same state, same
lane, same seed, same restricted region, same withheld control
certificates, same eight tiles — so configuration (a) at G1 IS E4's
configuration (a) and is asserted against ``e3e4/e4.json`` rather than
assumed to be it.

TWO GEOMETRIES, one variable between them:

* **G1, the E1 REFIT footing.**  Each target tile's windows sampled at
  that tile's supervised 6-dof affine plus BER polish, the whole
  restricted region re-fitted around it.  Comparable to E4 digit for
  digit; SUPERVISED, so a ceiling.
* **G2, PRODUCTION-like.**  The committed pose plus the per-plane field
  built by the shipped ``TILE_FRAGMENT`` probe pass, applied to EVERY
  window of the region — configuration (ii) of the pose-writer
  instrument, which is what the ``uF`` arm samples at.  No supervision
  anywhere.  One refit per capture serves all eight tiles, because the
  field does not depend on which tile is being measured.

TWO PASSES, because configuration (g) is a cross-capture object: pass one
measures every other configuration and writes each capture's baseline Y
decisions to ``decisions/``; pass two rebuilds the consensus from all
three and measures (g).  Pass one's rows are on disk before pass two
starts, so a failure in the second pass costs one configuration, not the
run.
"""
from __future__ import annotations

import json
import resource
import time

import numpy as np

from . import _context_gt, _context_loop, _density, _swim_inputs, _swim_region
from ._context_loop import CONFIGS, NEEDS_CONSENSUS, Y_PLANE
from ._swim_inputs import FORMAT_REF, QUAL_STATE
from ._swim_setup import (
    PAGE,
    LaneRasters,
    build_placements,
    certified_index,
    choose_lane,
    residue_by_column,
    restricted_placements,
    select_controls,
    select_targets,
)
from .detector_residue import (
    CONTROL_TILES,
    DEAD_TILES,
    GT_AFFINE,
    geometry_for,
    mismatch,
    read_ceiling,
)

SCHEMA = "plane-fields-context-loop-v1"
OUT_DIR = _swim_inputs.MAIN_SCRATCH / "plane-fields" / "p2" / "e8"
DECISIONS = OUT_DIR / "decisions"
E4_JSON = (_swim_inputs.MAIN_SCRATCH / "plane-fields" / "p2" / "e3e4"
           / "e4.json")
GATE_BER = 0.0767
ARMS = ("bins", "bins+head")
GEOMETRIES = ("G1", "G2")
GEOMETRY_NAMES = {
    "G1": "E1 refit (supervised affine, bins recut)",
    "G2": "production-like (committed pose + TILE_FRAGMENT field)",
}


def _rss_gb() -> float:
    """This process's high-water mark, in GiB — the memory the run costs."""
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2)


def _mean(values):
    rows = [float(v) for v in values
            if v is not None and not isinstance(v, bool) and np.isfinite(v)]
    return float(np.mean(rows)) if rows else None


def _sd(values):
    rows = [float(v) for v in values
            if v is not None and not isinstance(v, bool) and np.isfinite(v)]
    return float(np.std(rows, ddof=1)) if len(rows) > 1 else None


def _select(targets, wanted, role: str):
    by_tile = {(row.tile_y, row.tile_x): row for row in targets
               if row.stream == "Y"}
    missing = [tile for tile in wanted if tile not in by_tile]
    if missing:
        raise SystemExit(
            f"the {role} tiles {missing} are not in this run's selection — "
            f"the seed or the selector moved and this is no longer the same "
            f"experiment as e4.json")
    return [by_tile[tile] for tile in wanted]


def _key(target) -> str:
    return f"{target.tile_y},{target.tile_x}/{target.stream}"


def _truth_for(truth_bits, target, payload_indices) -> np.ndarray:
    tile_bits = truth_bits[target.tile_y * 64:(target.tile_y + 1) * 64,
                           target.tile_x * 64:(target.tile_x + 1) * 64, :]
    return tile_bits.reshape(-1, 3)[payload_indices][:, target.plane]


# --------------------------------------------------------------------------
# the baseline decisions a consensus is built from
# --------------------------------------------------------------------------
def decision_path(sha: str, geometry: str, key: str):
    return DECISIONS / f"{sha[:12]}_{geometry}_{key.replace(',', '-').replace('/', '_')}.npz"


def save_decisions(sha, geometry, key, grid, values) -> None:
    """One (capture, geometry, tile) baseline Y LLR over the lattice.

    PAGE cell coordinates are written, never the lattice's own packed
    key: that key is ``y * (region max x + 1) + x``, a region-LOCAL
    encoding whose stride differs between captures because their
    placements do.  A consensus is a page-cell object and has to be
    addressed as one.
    """
    DECISIONS.mkdir(parents=True, exist_ok=True)
    column = grid.unique_of([np.asarray(row)[:, Y_PLANE] for row in values])
    np.savez_compressed(
        decision_path(sha, geometry, key),
        cells_yx=np.asarray(grid.unique_cells, np.int32),
        llr=np.asarray(column, np.float32))


def consensus_page(shas, geometry, key, cells_yx) -> tuple[np.ndarray, dict]:
    """The summed baseline Y LLR per page cell, over every capture on disk.

    The lattice is deduplicated per capture, so a page cell appears at
    most once per file and ``np.add.at`` is summing across CAPTURES, not
    across a capture's own overlapping windows.
    """
    total = np.zeros(cells_yx, np.float32)
    seen = np.zeros(cells_yx, np.int16)
    found = []
    for sha in shas:
        path = decision_path(sha, geometry, key)
        if not path.is_file():
            continue
        with np.load(path) as handle:
            cells = np.asarray(handle["cells_yx"], np.int64)
            llr = np.asarray(handle["llr"], np.float32)
        total[cells[:, 0], cells[:, 1]] += llr
        seen[cells[:, 0], cells[:, 1]] += 1
        found.append(sha)
    return total, {"captures": found, "cells": int((seen > 0).sum()),
                   "cells_all_captures": int((seen >= len(shas)).sum())}


# --------------------------------------------------------------------------
# one refit's shared lattice, and every configuration's bins
# --------------------------------------------------------------------------
def prepare(fit, truth_bits, configs, consensus, save, log) -> dict:
    """Lattice, null proof, decisions and one bin set per configuration.

    The baseline SCORING pass (every region cell's post-context evidence)
    is the second most expensive thing here after the refit itself, so it
    runs only when a configuration in this pass consumes it or when the
    decisions are being written for a later one.
    """
    mark = time.time()
    evidence = _context_gt.region_evidence(fit)
    state = _context_loop.build_lattice(fit, truth_bits, evidence)
    baseline_rows = state.grid.scatter(state.base_bins)
    identical = all(np.array_equal(left, right) for left, right in
                    zip(fit.context_bins, baseline_rows, strict=True))
    if not identical:
        raise RuntimeError(
            "rebuilding A5's bins through the E8 lattice did not reproduce "
            "the ladder's own — the seam is not the ladder's ink map and "
            "every configuration below would be measuring the instrument")
    out: dict = {
        "null_proof_bins_bit_identical": True,
        "n_unique_cells": state.grid.n_unique,
        "ink_disagreement": _context_loop.ink_disagreement(state),
        "known_bit_agreement": _context_loop.known_bit_agreement(
            fit, truth_bits),
        "bins": {}, "columns": {}, "state": state, "baseline_values": None,
    }
    columns: dict[str, np.ndarray] = {}
    if save or any(name in configs for name in ("e1", "e2", "h")):
        values = _context_loop.post_context_evidence(fit, baseline_rows)
        out["baseline_values"] = values
        columns["e1"] = state.grid.unique_of(
            _context_loop.decision_column(fit, values))
        columns["h"] = state.grid.unique_of(
            _context_loop.posterior_column(fit, values))
    if consensus is not None:
        columns["g"] = state.grid.unique_of(
            _context_loop.consensus_column(fit, consensus))
    for name in configs:
        if name == "e2" or (name in ("e1", "g", "h") and name not in columns):
            continue
        out["bins"][name] = _context_loop.config_bins(
            state, name, y_column=columns.get(name))
    if "e2" in configs and "e1" in out["bins"]:
        rows_e1 = state.grid.scatter(out["bins"]["e1"])
        second = _context_loop.post_context_evidence(fit, rows_e1)
        columns["e2"] = state.grid.unique_of(
            _context_loop.decision_column(fit, second))
        out["bins"]["e2"] = _context_loop.config_bins(
            state, "e2", y_column=columns["e2"])
        out["convergence"] = {
            "y_bins_changed_a_to_e1": float(np.mean(
                out["bins"]["e1"][:, Y_PLANE]
                != state.base_bins[:, Y_PLANE])),
            "y_bins_changed_e1_to_e2": float(np.mean(
                out["bins"]["e2"][:, Y_PLANE]
                != out["bins"]["e1"][:, Y_PLANE])),
            "y_ink_changed_a_to_e1": float(np.mean(
                (columns["e1"] > 0.5) != (state.base_ink[:, Y_PLANE] > 0.5))),
            "y_ink_changed_e1_to_e2": float(np.mean(
                (columns["e2"] > 0.5) != (columns["e1"] > 0.5))),
        }
        del second
    out["columns"] = {
        name: _context_loop.ink_disagreement(state, column)["Y"]
        for name, column in columns.items()}
    out["columns"]["a"] = _context_loop.ink_disagreement(state)["Y"]
    out["y_bin_histogram"] = {
        name: _context_loop.bin_histogram(bins)["Y"]
        for name, bins in out["bins"].items()}
    out["prepare_seconds"] = round(time.time() - mark, 1)
    log(f"      lattice {state.grid.n_unique} cells, ink wrong "
        + ", ".join(f"{plane} {100 * row['fraction']:.2f}%" for plane, row
                    in out["ink_disagreement"].items())
        + "; decisions " + ", ".join(
            f"{name} {100 * row['fraction']:.2f}%"
            for name, row in sorted(out["columns"].items()))
        + f" [{out['prepare_seconds']:.0f}s]")
    return out


def evaluate(fit, spec, prepared, name, targets, references, truth_bits,
             payload_indices, log) -> dict:
    """One configuration: refit the head once, then every tile, both arms."""
    mark = time.time()
    state = prepared["state"]
    bins = state.grid.scatter(prepared["bins"][name])
    head_fit, head_record = _context_gt.refit_context_head(fit, bins)
    candidates = {arm: _context_gt.with_context(fit, bins, detector_fit)
                  for arm, detector_fit in (("bins", None),
                                            ("bins+head", head_fit))}
    row: dict = {
        "description": _context_loop.CONFIG_NAMES[name],
        "head_refit": head_record,
        "redefined_bin": bool(name in _context_loop.REDEFINED_BIN),
        "references": {
            arm: _context_loop.reference_error(
                fit, bins, references, truth_bits, payload_indices,
                candidate.selected_fit)
            for arm, candidate in candidates.items()},
        "tiles": {},
    }
    for target in targets:
        truth = _truth_for(truth_bits, target, payload_indices)
        entry = {"bin_change": _context_loop.bin_change(
            state, prepared["bins"][name], fit, target.address), "arms": {}}
        for arm, candidate in candidates.items():
            blocks = _context_gt.tile_blocks(candidate, spec, target.address)
            entry["arms"][arm] = {
                **mismatch(blocks, spec, target.address, target.plane,
                           payload_indices, truth),
                "_blocks": blocks}
        row["tiles"][_key(target)] = entry
    row["seconds"] = round(time.time() - mark, 1)

    def rate(target) -> str:
        value = row["tiles"][_key(target)]["arms"]["bins"]["ber"]
        return "n/a" if value is None else f"{value:.4f}"

    log(f"      ({name}) " + " ".join(
        f"{_key(target).split('/')[0]}:{rate(target)}" for target in targets)
        + f"  head {head_record['reason']} [{row['seconds']:.0f}s]")
    return row


# --------------------------------------------------------------------------
# one capture
# --------------------------------------------------------------------------
def capture_pass(capture, spec, scans, facts, lane, targets, measured,
                 ceiling, fit_certificates, truth_bits, payload_indices,
                 *, fit_radius, configs, geometries, consensus_for, save,
                 references, log) -> dict:
    """Every configuration at every geometry for ONE capture's raster.

    ONE capture is resident at a time (E1's rule — two production
    receivers run on this machine).  What survives the release is a few
    tens of kilobytes of evidence blocks per (tile, geometry,
    configuration, arm).
    """
    from holo.receive.payload_model import EvidenceSource

    sha = capture.source_sha256
    started = time.time()
    holder = LaneRasters(spec, capture, scans[sha])
    try:
        raster = holder.for_lane(lane)
        rss_raster = _rss_gb()
        placements, _poses = build_placements(facts, spec, capture, lane,
                                              raster)
        grouped = restricted_placements(placements, targets, fit_radius)
        source = EvidenceSource(sha, lane.lane_id)
        region_index, patches = _region_for(grouped, measured)
        region_id = (f"{sha}/{lane.lane_id}/region-{region_index}/"
                     f"page-{PAGE}")
        out: dict = {"capture": sha, "geometries": {},
                     "rss_after_raster_gb": rss_raster,
                     "setup_seconds": round(time.time() - started, 1)}
        log(f"  {sha[:12]} region {region_index}: {len(patches)} placements; "
            f"setup {out['setup_seconds']:.0f}s, RSS after raster "
            f"{rss_raster:.1f} GB")
        if "G1" in geometries:
            out["geometries"]["G1"] = _g1(
                spec, raster, source, patches, fit_certificates, region_id,
                sha, measured, references, ceiling, truth_bits,
                payload_indices, configs=configs,
                consensus_for=consensus_for, save=save, log=log)
        if "G2" in geometries:
            out["geometries"]["G2"] = _g2(
                spec, raster, source, patches, facts, placements,
                fit_certificates, region_id, sha, measured, references,
                truth_bits, payload_indices, configs=configs,
                consensus_for=consensus_for, save=save, log=log)
        out["seconds"] = round(time.time() - started, 1)
        out["peak_rss_gb"] = _rss_gb()
        return out
    finally:
        holder.release()


def _region_for(grouped, measured) -> tuple:
    """The one restricted region that carries the measured tiles."""
    from ._swim_region import patch_tiles

    wanted = {row.address for row in measured}
    best = None
    for index, patches in sorted(grouped.items()):
        covered = set()
        for patch in patches:
            covered.update(patch_tiles(patch))
        hits = len(wanted & covered)
        if best is None or hits > best[0]:
            best = (hits, index, patches)
    if best is None or best[0] == 0:
        raise SystemExit("no restricted region carries the measured tiles")
    return best[1], best[2]


def _g1(spec, raster, source, patches, fit_certificates, region_id, sha,
        measured, references, ceiling, truth_bits, payload_indices, *,
        configs, consensus_for, save, log) -> dict:
    """One refit PER TILE at that tile's supervised affine (E4's footing)."""
    from .gt_affine import affine_override_builder

    out: dict = {"name": GEOMETRY_NAMES["G1"], "tiles": {}, "references": {}}
    for target in measured:
        key = _key(target)
        mark = time.time()
        geometry = geometry_for(
            ceiling["targets"][(target.tile_y, target.tile_x, target.stream)],
            target.plane, polish=True)
        try:
            refit = _swim_region.fit_region(
                spec, raster, source, patches, fit_certificates, PAGE,
                f"{region_id}/g1-{key}",
                keep_features_for=frozenset({target.address}),
                keep_all_features=True,
                refit_overrides={target.address: affine_override_builder(
                    target.address, geometry["by_capture"][sha])})
        except _swim_region.RefitDidNotReach as error:
            out["tiles"][key] = {"error": f"refit no-op: {error}"}
            continue
        if refit.selected_fit is None or refit.context_bins is None:
            out["tiles"][key] = {"error": refit.refusal or "A5 not adopted"}
            continue
        log(f"    G1 {key:<12} refit {'A1' if refit.adopted else 'A0'} "
            f"logloss {refit.heldout_loss:.5f} [{time.time() - mark:.0f}s]")
        prepared = prepare(refit, truth_bits, configs,
                           consensus_for("G1", key), save, log)
        if save:
            save_decisions(sha, "G1", key, prepared["state"].grid,
                           prepared["baseline_values"])
        entry = {
            "arm": "A1" if refit.adopted else "A0",
            "heldout_logloss": float(refit.heldout_loss),
            "refit_probe": refit.refit_probe,
            "polish_extra_dots_xy": geometry["polish_extra_dots_xy"],
            "configurations": {},
            **{name: prepared[name] for name in
               ("null_proof_bins_bit_identical", "n_unique_cells",
                "ink_disagreement", "known_bit_agreement", "columns",
                "y_bin_histogram", "prepare_seconds")},
        }
        if "convergence" in prepared:
            entry["convergence"] = prepared["convergence"]
        for name in configs:
            if name not in prepared["bins"]:
                continue
            row = evaluate(refit, spec, prepared, name, [target], references,
                           truth_bits, payload_indices, log)
            out["references"].setdefault(key, {})[name] = row.pop("references")
            entry["configurations"][name] = {
                **{k: v for k, v in row.items() if k != "tiles"},
                **row["tiles"][key]}
        entry["seconds"] = round(time.time() - mark, 1)
        out["tiles"][key] = entry
        del prepared, refit
    return out


def _g2(spec, raster, source, patches, facts, placements, fit_certificates,
        region_id, sha, measured, references, truth_bits, payload_indices, *,
        configs, consensus_for, save, log) -> dict:
    """ONE refit at the field, serving every tile (the field is tile-blind)."""
    from holo.receive.color_field import PlaneFieldBuilder, PlaneFieldConfig

    from ._pose_apply import override_builder

    mark = time.time()
    rows_fit = _swim_region.fit_region(
        spec, raster, source, patches, fit_certificates, PAGE,
        f"{region_id}/g2-rows", keep_features_for=frozenset())
    if rows_fit.selected_fit is None:
        return {"name": GEOMETRY_NAMES["G2"], "error": rows_fit.refusal}
    committed = {"arm": "A1" if rows_fit.adopted else "A0",
                 "heldout_logloss": float(rows_fit.heldout_loss),
                 "seconds": round(time.time() - mark, 1)}
    log(f"    G2 committed fit {committed['arm']} logloss "
        f"{committed['heldout_logloss']:.5f} [{committed['seconds']:.0f}s]")

    mark = time.time()
    regions, fully = _density.classify_windows(spec, facts.certificates,
                                               placements)
    projection_for, _ = _density.projection_source(spec, facts.certificates)
    builder = PlaneFieldBuilder(spec, PlaneFieldConfig(),
                               done_tiles=tuple(sorted(fully)))
    for region in regions:
        builder.add_certified_probes(raster, region.select("all"),
                                     projection_for)
    builder.solve()
    report = builder.report()
    overrides, adopted = builder.region_offsets(PAGE, rows_fit.rows)
    field_by_patch = {int(row.patch.patch_id): entry
                      for row, entry in zip(rows_fit.rows, overrides,
                                            strict=True)}
    field = {
        "adopted": [_context_loop.PLANE_NAMES[plane]
                    for plane in range(3) if adopted[plane]],
        "rms_dots": {_context_loop.PLANE_NAMES[plane]: float(value)
                     for plane, value in enumerate(report.rms_dots)},
        "peak_dots": {_context_loop.PLANE_NAMES[plane]: float(value)
                      for plane, value in enumerate(report.peak_dots)},
        "coverage_by_plane": [float(value)
                              for value in report.coverage_by_plane],
        "n_probe_sites": int(report.n_probe_sites),
        "probe_mode": "TILE_FRAGMENT (the shipped density)",
        "seconds": round(time.time() - mark, 1),
    }
    log(f"    G2 field {field['adopted']} rms {field['rms_dots']} "
        f"[{field['seconds']:.0f}s]")
    addresses = frozenset(rows_fit.tile_rows)
    del builder, rows_fit, regions

    mark = time.time()
    build = override_builder(spec, field_by_patch, {}, "field")
    out: dict = {"name": GEOMETRY_NAMES["G2"], "committed": committed,
                 "field": field, "tiles": {}, "references": {}}
    try:
        refit = _swim_region.fit_region(
            spec, raster, source, patches, fit_certificates, PAGE,
            f"{region_id}/g2-field",
            keep_features_for=frozenset(row.address for row in measured),
            keep_all_features=True,
            refit_overrides={address: build for address in addresses})
    except _swim_region.RefitDidNotReach as error:
        out["error"] = f"refit no-op: {error}"
        return out
    if refit.selected_fit is None or refit.context_bins is None:
        out["error"] = refit.refusal or "A5 not adopted"
        return out
    out["refit"] = {
        "arm": "A1" if refit.adopted else "A0",
        "heldout_logloss": float(refit.heldout_loss),
        "refit_probe": refit.refit_probe,
        "windows_overridden": len(addresses),
        "seconds": round(time.time() - mark, 1)}
    log(f"    G2 field refit {out['refit']['arm']} logloss "
        f"{out['refit']['heldout_logloss']:.5f} "
        f"[{out['refit']['seconds']:.0f}s]")
    # The consensus is a per-tile object only because G1's refit is; at G2
    # ONE fit serves every tile, so the map is keyed on the geometry alone.
    prepared = prepare(refit, truth_bits, configs, consensus_for("G2", "all"),
                       save, log)
    if save:
        save_decisions(sha, "G2", "all", prepared["state"].grid,
                       prepared["baseline_values"])
    out["region"] = {name: prepared[name] for name in
                     ("null_proof_bins_bit_identical", "n_unique_cells",
                      "ink_disagreement", "known_bit_agreement", "columns",
                      "y_bin_histogram", "prepare_seconds")}
    if "convergence" in prepared:
        out["region"]["convergence"] = prepared["convergence"]
    for name in configs:
        if name not in prepared["bins"]:
            continue
        row = evaluate(refit, spec, prepared, name, measured, references,
                       truth_bits, payload_indices, log)
        out["references"].setdefault("all", {})[name] = row.pop("references")
        for key, tile in row["tiles"].items():
            out["tiles"].setdefault(key, {"configurations": {}})[
                "configurations"][name] = {
                    **{k: v for k, v in row.items() if k != "tiles"}, **tile}
    del prepared, refit
    return out


# --------------------------------------------------------------------------
# the union, and the two summaries
# --------------------------------------------------------------------------
def union_rows(measured, per_capture, spec, truth_bits, payload_indices,
               geometries) -> dict:
    """Union each tile's blocks across captures, per geometry/config/arm."""
    from .swim_pilot import union_verdict

    out: dict[str, list[dict]] = {}
    for geometry in geometries:
        rows: list[dict] = []
        for target in measured:
            key = _key(target)
            entries = {}
            for sha, capture in per_capture.items():
                block = ((capture["geometries"].get(geometry) or {})
                         .get("tiles", {}).get(key))
                if block and "error" not in block:
                    entries[sha] = block["configurations"]
            row = {"tile_y": target.tile_y, "tile_x": target.tile_x,
                   "band": target.band, "role": target.role,
                   "captures": sorted(entries), "configurations": {}}
            if not entries:
                row["error"] = "not carried"
                rows.append(row)
                continue
            truth = _truth_for(truth_bits, target, payload_indices)
            names = [name for name in CONFIGS
                     if all(name in value for value in entries.values())]
            for name in names:
                entry = {"description": _context_loop.CONFIG_NAMES[name],
                         "arms": {}}
                for arm in ARMS:
                    blocks = [tuple(value[name]["arms"][arm]["_blocks"])
                              for value in entries.values()]
                    union = tuple(row_ for group in blocks for row_ in group)
                    verdict = (union_verdict(blocks, spec, target)
                               if len(union) >= 2 else
                               {"certified": False,
                                "reason": "fewer than two blocks in the union"})
                    entry["arms"][arm] = {
                        **mismatch(union, spec, target.address, target.plane,
                                   payload_indices, truth),
                        "verdict": verdict,
                        "per_capture": {
                            sha: {k: v for k, v
                                  in value[name]["arms"][arm].items()
                                  if not k.startswith("_")}
                            for sha, value in entries.items()},
                    }
                row["configurations"][name] = entry
            rows.append(row)
        out[geometry] = rows
    return out


def reference_rows(per_capture, geometries) -> dict:
    """The certified clean-column references, pooled over refits/captures.

    One row per (capture, refit, configuration, arm): at G1 there are as
    many refits as measured tiles, at G2 exactly one.  Pooling them is
    pooling correlated rows, and ``n_rows`` sits next to ``n_tiles``
    everywhere so the reader can see it.
    """
    out: dict[str, dict] = {}
    for geometry in geometries:
        pooled: dict[str, dict[str, list]] = {}
        for capture in per_capture.values():
            block = capture["geometries"].get(geometry) or {}
            for by_config in (block.get("references") or {}).values():
                for name, by_arm in by_config.items():
                    for arm, entry in by_arm.items():
                        if entry.get("ber") is None:
                            continue
                        pooled.setdefault(name, {}).setdefault(
                            arm, []).append(entry)
        out[geometry] = {
            name: {arm: {
                "n_rows": len(rows),
                "n_tiles": len({address for row in rows
                                for address in row["by_tile"]}),
                "ber": _mean(row["ber"] for row in rows),
                "ber_sd": _sd(row["ber"] for row in rows),
                "cells": int(sum(row["cells"] for row in rows)),
            } for arm, rows in by_arm.items()}
            for name, by_arm in pooled.items()}
    return out


def summarise(union, references, geometries) -> dict:
    """Dead / control means, the gap, and the fraction of the oracle gain."""
    out: dict[str, dict] = {}
    for geometry in geometries:
        rows = [row for row in union.get(geometry, ()) if "error" not in row]
        by_configuration: dict[str, dict] = {}
        names = sorted({name for row in rows for name in row["configurations"]},
                       key=lambda value: CONFIGS.index(value))
        for name in names:
            entry: dict = {"description": _context_loop.CONFIG_NAMES[name]}
            for arm in ARMS:
                groups: dict[str, list[float]] = {"dead": [], "control": []}
                certified: dict[str, list[dict]] = {"dead": [], "control": []}
                for row in rows:
                    if name not in row["configurations"]:
                        continue
                    group = "dead" if row["role"] == "target" else "control"
                    cell = row["configurations"][name]["arms"][arm]
                    if cell["ber"] is not None:
                        groups[group].append(float(cell["ber"]))
                    if cell["verdict"].get("certified"):
                        certified[group].append({
                            "tile": [row["tile_y"], row["tile_x"]],
                            "certificate_id": cell["verdict"].get(
                                "certificate_id"),
                            "stage": cell["verdict"].get("stage"),
                            "crc_ok": cell["verdict"].get("crc_ok"),
                            "syndrome_ok": cell["verdict"].get("syndrome_ok"),
                            "n_iters": cell["verdict"].get("n_iters")})
                entry[arm] = {
                    "dead_mean": _mean(groups["dead"]),
                    "dead_sd": _sd(groups["dead"]),
                    "control_mean": _mean(groups["control"]),
                    "control_sd": _sd(groups["control"]),
                    "n_dead": len(groups["dead"]),
                    "n_control": len(groups["control"]),
                    "gap_pp": (None if not groups["dead"] or not groups["control"]
                               else float(100.0 * (np.mean(groups["dead"])
                                                   - np.mean(groups["control"])))),
                    "certified_dead": len(certified["dead"]),
                    "certified_control": len(certified["control"]),
                    "certificates": certified["dead"] + certified["control"],
                    "reference": ((references.get(geometry) or {})
                                  .get(name, {}).get(arm)),
                }
            by_configuration[name] = entry
        base = by_configuration.get("a")
        oracle = by_configuration.get("b")
        for name, entry in by_configuration.items():
            for arm in ARMS:
                for group in ("dead", "control"):
                    left = None if base is None else base[arm][f"{group}_mean"]
                    right = entry[arm][f"{group}_mean"]
                    delta = (None if left is None or right is None
                             else float(100.0 * (right - left)))
                    entry[arm][f"{group}_delta_pp"] = delta
                    span = (None if base is None or oracle is None
                            or base[arm][f"{group}_mean"] is None
                            or oracle[arm][f"{group}_mean"] is None else
                            float(100.0 * (oracle[arm][f"{group}_mean"]
                                           - base[arm][f"{group}_mean"])))
                    entry[arm][f"{group}_oracle_pp"] = span
                    entry[arm][f"{group}_oracle_fraction"] = (
                        None if delta is None or not span else delta / span)
                left = None if base is None else base[arm]["gap_pp"]
                entry[arm]["gap_closed_pp"] = (
                    None if left is None or entry[arm]["gap_pp"] is None
                    else float(left - entry[arm]["gap_pp"]))
                ref = entry[arm].get("reference")
                base_ref = None if base is None else base[arm].get("reference")
                entry[arm]["reference_delta_pp"] = (
                    None if not ref or not base_ref
                    or ref.get("ber") is None or base_ref.get("ber") is None
                    else float(100.0 * (ref["ber"] - base_ref["ber"])))
        out[geometry] = {"name": GEOMETRY_NAMES[geometry],
                         "n_tiles": len(rows),
                         "by_configuration": by_configuration}
    return out


def reproduction_of_e4(union) -> dict:
    """Configurations (a) and (b) at G1 ARE E4's — assert, do not assume."""
    if not E4_JSON.is_file():
        return {"checked": 0, "reason": "e3e4/e4.json is not on disk"}
    document = json.loads(E4_JSON.read_text())
    reference = {(row["tile_y"], row["tile_x"]): row
                 for row in document["e4"]["rows"] if "error" not in row}
    per_tile: dict[str, dict] = {}
    worst = 0.0
    checked = 0
    for row in union.get("G1", ()):
        found = reference.get((row["tile_y"], row["tile_x"]))
        if found is None or "error" in row:
            continue
        for name in ("a", "b"):
            here = (row["configurations"].get(name, {})
                    .get("arms", {}).get("bins", {}).get("ber"))
            there = (found["configurations"].get(name, {})
                     .get("arms", {}).get("bins", {}).get("ber"))
            if here is None or there is None:
                continue
            gap = abs(float(here) - float(there))
            per_tile[f"{row['tile_y']},{row['tile_x']}/{name}"] = {
                "e4_ber": float(there), "e8_ber": float(here), "abs_gap": gap}
            worst = max(worst, gap)
            checked += 1
    return {"checked": checked, "max_abs_gap": worst,
            "exact": bool(checked > 0 and worst == 0.0), "per_tile": per_tile}


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def run(args) -> int:                                          # noqa: C901
    from holo.format import pilots
    from holo.format.resolve import resolve_format_ref
    from holo.receive import _parallel

    from . import _swim_truth
    from ._context_loop_report import write_bar, write_outputs

    started = time.time()
    _parallel.set_worker_count(max(1, int(args.workers)))
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
    withheld = frozenset(
        (*row.address, row.stream) for row in targets
        if row.role.startswith("reproduction-control"))
    fit_certificates = tuple(
        row for row in facts.certificates
        if (int(row.page), *(int(v) for v in row.tile_yx), row.stream_id)
        not in withheld)
    measured = (_select(targets, DEAD_TILES, "dead-band")
                + _select(targets, CONTROL_TILES, "control"))
    if args.limit:
        measured = measured[:args.limit]
    geometries = tuple(row for row in GEOMETRIES
                       if row in tuple(args.geometries.split(",")))
    configs = tuple(row for row in CONFIGS
                    if row in tuple(args.configs.split(",")))

    ceiling = read_ceiling(GT_AFFINE)
    if ceiling["state_sha256"] != facts.state_sha256:
        raise SystemExit(
            f"gt-affine-final2 was run against state "
            f"{ceiling['state_sha256'][:12]} and this is "
            f"{facts.state_sha256[:12]}")
    if ceiling["lane"] != lane.lane_id:
        raise SystemExit(f"lane moved: {ceiling['lane']} -> {lane.lane_id}")
    references = [(0, tile_y, tile_x)
                  for tile_y, tile_x in sorted(ceiling["references"])][
                      :args.reference_tiles]

    print(f"state {facts.state_sha256[:12]} {facts.close_status} certs "
          f"{len(facts.certificates)} lane {lane.lane_id} coverage {coverage}")
    print("measured: " + ", ".join(
        f"{row.tile_y},{row.tile_x}[{row.band[:1]}"
        f"{'C' if row.role != 'target' else ''}]" for row in measured))
    print(f"geometries {geometries} configurations {configs}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_bar(OUT_DIR / "e8-bar.json", geometries, configs, measured,
              tree_before)

    payload = (QUAL_STATE.parent / "recovered.bin").read_bytes()
    mark = time.time()
    truth_bits, truth_report = _swim_truth.page_component_bits(
        spec, payload, args.q, PAGE)
    truth_report["validation"] = _swim_truth.validate_against_certificates(
        truth_bits, spec, facts.certificates, sample=24)
    truth_report["seconds"] = round(time.time() - mark, 1)
    if not truth_report["validation"].get("exact"):
        raise SystemExit(
            f"the reconstructed printed field does NOT match the "
            f"certificates: {truth_report['validation']}")
    print(f"truth field rebuilt in {truth_report['seconds']}s, exact on "
          f"{truth_report['validation']['checked']} certified tiles")
    payload_indices = pilots.color_payload_cell_indices(spec.family_seed)
    captures = facts.captures[:args.captures]
    shas = [row.source_sha256 for row in captures]

    def merge(into: dict, new: dict) -> None:
        """Fold pass two's rows into pass one's, configuration by config."""
        for geometry, block in new["geometries"].items():
            target = into.setdefault("geometries", {}).setdefault(geometry, {})
            for field, value in block.items():
                if field == "tiles":
                    for key, tile in value.items():
                        slot = target.setdefault("tiles", {}).setdefault(key, {})
                        for inner, payload_ in tile.items():
                            if inner == "configurations":
                                slot.setdefault("configurations", {}).update(
                                    payload_)
                            else:
                                slot.setdefault(inner, payload_)
                elif field == "references":
                    for key, by_config in value.items():
                        target.setdefault("references", {}).setdefault(
                            key, {}).update(by_config)
                else:
                    target.setdefault(field, value)

    per_capture: dict[str, dict] = {}
    failures: list[dict] = []
    passes = [("one", tuple(name for name in configs
                            if name not in NEEDS_CONSENSUS), True)]
    if any(name in NEEDS_CONSENSUS for name in configs):
        passes.append(("two", tuple(name for name in configs
                                    if name in NEEDS_CONSENSUS), False))
    for label, subset, save in passes:
        if not subset:
            continue
        print(f"\n=== pass {label}: configurations {subset} ===")

        def consensus_for(geometry: str, key: str, _save=save):
            if _save:
                return None
            page, record = consensus_page(shas, geometry, key,
                                          spec.layout.cells_yx)
            print(f"      consensus {geometry}/{key}: "
                  f"{len(record['captures'])} captures, "
                  f"{record['cells']} cells")
            return page

        for capture in captures:
            try:
                row = capture_pass(
                    capture, spec, scans, facts, lane, targets, measured,
                    ceiling, fit_certificates, truth_bits, payload_indices,
                    fit_radius=args.fit_radius, configs=subset,
                    geometries=geometries, consensus_for=consensus_for,
                    save=save, references=references, log=print)
            except Exception as error:                         # noqa: BLE001
                # Pass one's rows are what the other seven configurations
                # cost hours to produce; a failure in the consensus pass
                # must not take them with it.  Pass one still raises.
                if label == "one":
                    raise
                print(f"  !! pass {label} FAILED on "
                      f"{capture.source_sha256[:12]}: {error!r}")
                failures.append({"pass": label,
                                 "capture": capture.source_sha256,
                                 "error": repr(error)})
                continue
            merge(per_capture.setdefault(capture.source_sha256,
                                         {"capture": capture.source_sha256}),
                  row)
            print(f"  {capture.source_sha256[:12]} pass {label} done in "
                  f"{row['seconds']:.0f}s; RSS "
                  f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.1f} GB")

    union = union_rows(measured, per_capture, spec, truth_bits,
                       payload_indices, geometries)
    del truth_bits
    for row in (value for rows in union.values() for value in rows):
        for entry in (row.get("configurations") or {}).values():
            for arm in entry["arms"].values():
                arm.pop("_blocks", None)
    for capture in per_capture.values():
        for block in capture["geometries"].values():
            for tile in block.get("tiles", {}).values():
                for entry in (tile.get("configurations") or {}).values():
                    for arm in (entry.get("arms") or {}).values():
                        arm.pop("_blocks", None)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw.json").write_text(json.dumps(
        {"schema": SCHEMA + "-raw", "per_capture": per_capture,
         "union": union, "truth_field": truth_report,
         "pass_failures": failures},
        indent=1, sort_keys=True, default=str))
    print(f"raw rows written to {OUT_DIR / 'raw.json'}")

    references_summary = reference_rows(per_capture, geometries)
    return write_outputs(
        args, facts, spec, lane, coverage, scans, ceiling, measured,
        references, residue, truth_report, per_capture, union,
        summarise(union, references_summary, geometries),
        reproduction_of_e4(union), tree_before, started,
        geometries=geometries, configs=configs, failures=failures)


__all__ = ["ARMS", "CONFIGS", "DECISIONS", "E4_JSON", "GATE_BER",
           "GEOMETRIES", "GEOMETRY_NAMES", "OUT_DIR", "SCHEMA",
           "capture_pass", "consensus_page", "decision_path", "evaluate",
           "prepare", "reference_rows", "reproduction_of_e4", "run",
           "save_decisions", "summarise", "union_rows"]
