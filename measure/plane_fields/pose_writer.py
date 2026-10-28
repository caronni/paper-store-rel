#!/usr/bin/env python
"""P5 BAR — what a POSE WRITER would yield, in certificates.

docs/COMPOSITE-POSE-DESIGN.md §6 lists the writers that feed the
composite: a reader's PER-PLANE residual goes to the printer field, its
PLANE-COMMON residual goes to the window pose.  Half of that is built --
the field consumes the per-plane part every time the dial is on -- and
the other half is a MEASUREMENT with no consumer: INDEPENDENT-PLANES
§2.9b/§2.9c record a per-window plane-common residual of 0.18-0.20 print
dots median (p90 0.38, worst 0.94), self-consistent in 17% of windows at
the shipped ``TILE_FRAGMENT`` density, and apply it nowhere.

This instrument measures what applying it WOULD buy, on the archived W6
sheet-I qualification state, in the only currency the receiver has:
CERTIFICATES.  Four sampling configurations over every open ``(tile,
stream)`` slot of the state, union over the three 2400 dpi captures,
accepted by the ordinary certificate gate:

    (i)   committed          the arm's own zero -- today, pre-field
    (ii)  field              the per-plane field from the SAME probes
    (iii) field + pose-t     plus the window's plane-common translation
    (iv)  field + pose-affine  plus its plane-common local affine

Attempts only add, so (iii)/(iv) are a strict superset of (ii) by
construction; the measured quantity is the INCREMENT, reported by band,
by residual magnitude and by window self-consistency, with per-slot cell
BER so a gain shows where the gate is not crossed.

BOUNDARY (user ruling 2026-08-23): the pose WRITER is a new evidence
flow and is NOT built in src/holo.  Nothing here is imported by the
receiver; the production seam is used exactly as production uses it
(``offsets_override``), and the state, the scans and the regmap sidecar
are opened READ-ONLY.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.pose_writer --tag v1
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

from . import _density, _pose_apply, _pose_probe, _swim_inputs, _swim_region
from ._pose_apply import CONFIGS, REFIT_CONFIGS
from ._swim_inputs import CAPTURE_DPI, DEAD_BANDS, FORMAT_REF, QUAL_STATE
from ._swim_setup import (
    PAGE,
    LaneRasters,
    Target,
    build_placements,
    certified_index,
    residue_by_column,
    restricted_placements,
)

SCHEMA = "plane-fields-p5-pose-writer-v1"
OUT_DIR = _swim_inputs.MAIN_SCRATCH / "plane-fields" / "p2" / "pose-writer"
LANE_ID = "l02-8ppc-2400dpi"
PLANES = ("C", "M", "Y")

#: PRE-REGISTERED, written to disk before the first measurement runs.
BAR = {
    "statement": (
        "The pose writer earns a place in the composite-pose design if "
        "configuration (iii) or (iv) certifies at least 5 (tile, stream) "
        "slots beyond configuration (ii) on this state, OR reduces the "
        "dead-band mean cell BER by at least 0.5 percentage points "
        "relative to (ii).  Otherwise it is recorded as MEASURED "
        "NEGATIVE for this sheet, with the residual magnitude that would "
        "have been needed stated."),
    "certificate_increment_slots": 5,
    "dead_band_mean_ber_reduction_pp": 0.5,
    "baseline_configuration": "field",
    "candidate_configurations": ["field+pose-t", "field+pose-affine"],
    "exploratory_configurations": ["field-diff", "field-diff+pose-t"],
    "exploratory_note": (
        "The shipped field is fed each plane's FULL local probe offset, "
        "so its prediction already carries a page-smoothed plane-common "
        "component and a pose writer stacked on top double-counts it.  "
        "The two DIFFERENTIAL arms remove the field's own plane-common "
        "part so the plane-common sampling comes from the pose alone "
        "(COMPOSITE-POSE-DESIGN §4.1).  They are declared here BEFORE "
        "the run and are reported separately: they are NOT part of the "
        "pre-registered clause and cannot pass or fail it."),
    "population": "every open (tile, stream) slot of the W6 qualification "
                  "state, union over the three archived 2400 dpi captures",
    "gate": "the ordinary certificate gate (UNION, then RETRY150)",
}


# --------------------------------------------------------------------------
# slots
# --------------------------------------------------------------------------
def open_slots(index, tiles_yx) -> tuple[Target, ...]:
    """Every uncertified ``(tile, stream)`` slot, canonical order."""
    rows, columns = tiles_yx
    out: list[Target] = []
    for tile_y in range(rows):
        for tile_x in range(columns):
            have = index.get((PAGE, tile_y, tile_x), set())
            for stream in PLANES:
                if stream in have:
                    continue
                out.append(Target(
                    PAGE, tile_y, tile_x, stream, PLANES.index(stream),
                    "dead" if tile_x in DEAD_BANDS else "clear",
                    "target", tuple(sorted(have))))
    return tuple(out)


def lane_of(facts, lane_id: str):
    for lane in facts.captures[0].plan:
        if lane.lane_id == lane_id:
            return lane
    raise SystemExit(f"lane {lane_id!r} is not in the archived plan")


# --------------------------------------------------------------------------
# the sign check
# --------------------------------------------------------------------------
def shifted_patch(patch, spec, translation_xy):
    """The same placement with its pose translated by LOCAL print dots."""
    from dataclasses import replace

    pose = patch.segment.segment.pose
    cells_yx = np.asarray(
        (translation_xy[1] / spec.cell_dots,
         translation_xy[0] / spec.cell_dots), np.float64)
    origin = np.asarray(pose.origin_yx, np.float64) + cells_yx @ pose.matrix().T
    moved = replace(pose, origin_yx=(float(origin[0]), float(origin[1])))
    return replace(patch, segment=replace(
        patch.segment, segment=replace(patch.segment.segment, pose=moved)))


def verify_sign(spec, raster, regions, projection_for, config, poses) -> dict:
    """Re-measure the probe pass at the CORRECTED pose.

    The correction is only a correction if applying it makes the thing it
    measured go away.  Every window's pose is translated by its own
    plane-common estimate and the whole pass is re-run: a residual that
    collapses proves the sign AND the frame (a wrong ``rot_k`` handling
    would double it, not halve it); one that does not is a defect in this
    instrument, not a finding about the sheet.
    """
    from holo.receive.color_field import ProbeWindow

    moved_regions = []
    for region in regions:
        windows = []
        for window in region.windows:
            pose = poses.get(int(window.patch.patch_id))
            patch = (window.patch if pose is None else shifted_patch(
                window.patch, spec, pose.translation_xy))
            windows.append(ProbeWindow(
                patch, window.page, window.local_cells_yx,
                window.page_cells_yx))
        moved_regions.append(_density.RegionWindows(
            region.region_index, region.page, tuple(windows),
            region.is_open, region.rows))
    sites = _pose_probe.collect_site_measurements(
        spec, raster, tuple(moved_regions), projection_for, config, "all")
    after = _pose_probe.fit_window_poses(sites)
    before_rows = {key: row.magnitude_dots for key, row in poses.items()}
    after_rows = {key: row.magnitude_dots for key, row in after.items()}
    shared = sorted(set(before_rows) & set(after_rows))
    before = np.asarray([before_rows[key] for key in shared])
    residual = np.asarray([after_rows[key] for key in shared])
    return {
        "windows_compared": len(shared),
        "magnitude_before_median": float(np.median(before)) if shared else None,
        "magnitude_after_median": (
            float(np.median(residual)) if shared else None),
        "magnitude_after_p90": (
            float(np.percentile(residual, 90)) if shared else None),
        "fraction_reduced": (
            float(np.mean(residual < before)) if shared else None),
        "collapse_ratio": (
            float(np.median(residual) / np.median(before))
            if shared and np.median(before) > 0 else None),
    }


# --------------------------------------------------------------------------
# one capture
# --------------------------------------------------------------------------
def run_capture(facts, spec, capture, scan_path, lane, slots, addresses,
                args) -> tuple[dict, dict, dict]:
    """Every configuration's blocks for one capture, plus its diagnostics."""
    from holo.receive.color_field import PlaneFieldBuilder, PlaneFieldConfig
    from holo.receive.payload_model import EvidenceSource

    mark = time.time()
    holder = LaneRasters(spec, capture, scan_path)
    raster = holder.for_lane(lane)
    placements, _poses = build_placements(facts, spec, capture, lane, raster)
    regions, fully = _density.classify_windows(
        spec, facts.certificates, placements)
    projection_for, _ = _density.projection_source(spec, facts.certificates)
    n_windows = sum(len(row.windows) for row in regions)
    n_open = sum(row.n_open for row in regions)
    setup_seconds = time.time() - mark

    config = PlaneFieldConfig()
    mark = time.time()
    builder = PlaneFieldBuilder(spec, config, done_tiles=tuple(sorted(fully)))
    for region in regions:
        builder.add_certified_probes(
            raster, region.select("all"), projection_for)
    builder.solve()
    report = builder.report()
    field_seconds = time.time() - mark

    mark = time.time()
    sites = _pose_probe.collect_site_measurements(
        spec, raster, regions, projection_for, config, "all")
    poses = _pose_probe.fit_window_poses(
        sites, prior_edge_dots=args.affine_prior_edge_dots,
        min_affine_sites=args.min_affine_sites)
    cross = _pose_probe.cross_check_production(poses, report)
    probe_seconds = time.time() - mark
    if not cross["exact"]:
        raise SystemExit(
            f"the instrumented probe collector disagrees with the "
            f"production pass it claims to measure: {cross} — REFUSING")

    sign = None
    if args.verify_sign:
        mark = time.time()
        sign = verify_sign(spec, raster, regions, projection_for, config,
                           poses)
        sign["seconds"] = round(time.time() - mark, 1)

    mark = time.time()
    grouped = restricted_placements(placements, slots, -1)
    source = EvidenceSource(capture.source_sha256, lane.lane_id)
    if len(grouped) != 1:
        raise SystemExit(f"expected one payload region, got {sorted(grouped)}")
    region_index, patches = next(iter(sorted(grouped.items())))
    region_id = (f"{capture.source_sha256}/{lane.lane_id}/"
                 f"region-{region_index}/page-{PAGE}")
    fit = _swim_region.fit_region(
        spec, raster, source, patches, facts.certificates, PAGE, region_id,
        keep_features_for=frozenset())
    if fit.selected_fit is None:
        raise SystemExit(f"{capture.source_sha256[:12]}: {fit.refusal}")
    fit_seconds = time.time() - mark
    null = _swim_region.null_proof(fit, raster, spec, 0)

    # Production offers the adoption gate its whole region — payload rows
    # UNION label rows (``color_payload`` passes ``row_tuple``) — so the
    # coverage fraction it tests is the same population here.
    overrides, adopted = builder.region_offsets(PAGE, fit.rows)
    field_by_patch = {
        int(row.patch.patch_id): entry
        for row, entry in zip(fit.rows, overrides, strict=True)}
    del builder
    common = _pose_apply.field_common_content(
        fit, spec, field_by_patch, poses)
    print(f"    field plane-common change median "
          f"{common['field_common_magnitude_median']:.4f} dot vs pose "
          f"{common['pose_translation_magnitude_median']:.4f}; slope "
          f"{common['regression_slope_field_on_pose_xy']} corr "
          f"{[round(v, 3) for v in common['correlation_xy']]}", flush=True)
    divergence = _pose_apply.override_divergence(
        fit, spec, field_by_patch, poses)
    for name, row in divergence.items():
        print(f"    override {name:18s} moves {row['windows_moved']}/"
              f"{row['windows']} windows, max {row['max_abs_delta_dots']:.4f} "
              f"mean {row['mean_abs_delta_dots']:.4f} dot", flush=True)
    if any(row["max_abs_delta_dots"] <= 0.0 for row in divergence.values()):
        raise SystemExit(
            f"a configuration is a silent no-op on this capture: "
            f"{divergence} — REFUSING to report a tie")

    blocks: dict[str, dict] = {}
    nulls: dict[str, int] = {}
    timing: dict[str, float] = {}
    for name in CONFIGS:
        mark = time.time()
        blocks[name], nulls[name] = _pose_apply.capture_blocks(
            fit, raster, spec, field_by_patch, poses, name, addresses)
        timing[name] = round(time.time() - mark, 1)
        print(f"    {name:20s} {len(blocks[name]):5d} target tiles "
              f"({nulls[name]} window nulls) in {timing[name]:.0f}s",
              flush=True)

    refit_blocks: dict[str, dict] = {}
    refit_detail: dict[str, dict] = {}
    if args.refit:
        keep = frozenset(fit.tile_rows)
        for name in REFIT_CONFIGS:
            mark = time.time()
            build = _pose_apply.override_builder(
                spec, field_by_patch, poses, name)
            try:
                refit = _swim_region.fit_region(
                    spec, raster, source, patches, facts.certificates, PAGE,
                    f"{region_id}/refit-{name}", keep_features_for=keep,
                    refit_overrides={address: build for address in keep})
            except _swim_region.RefitDidNotReach as error:
                refit_detail[name] = {"refusal": f"refit no-op: {error}"}
                print(f"    refit {name:16s} REFUSED: {error}", flush=True)
                continue
            if refit.selected_fit is None:
                refit_detail[name] = {"refusal": refit.refusal}
                continue
            refit_blocks[name], refit_nulls = _pose_apply.capture_blocks(
                refit, raster, spec, field_by_patch, poses, name, addresses,
                use_cached=True)
            probe = refit.refit_probe or {}
            refit_detail[name] = {
                "arm": probe.get("arm"),
                "adopted_A1": bool(refit.adopted),
                "heldout_logloss": refit.heldout_loss,
                "max_abs_feature_delta": probe.get("max_abs_feature_delta"),
                "min_abs_feature_delta": probe.get("min_abs_feature_delta"),
                "window_nulls": refit_nulls,
                "target_tiles": len(refit_blocks[name]),
                "seconds": round(time.time() - mark, 1),
            }
            print(f"    refit {name:16s} {len(refit_blocks[name]):5d} tiles, "
                  f"arm {probe.get('arm')}, logloss "
                  f"{refit.heldout_loss:.4f} in "
                  f"{refit_detail[name]['seconds']:.0f}s", flush=True)
            del refit

    region_fit = {
        "seconds": round(fit_seconds, 1),
        "payload_windows": fit.n_payload,
        "label_rows": fit.n_labels,
        "adopted_A1": bool(fit.adopted),
        "heldout_logloss": fit.heldout_loss,
        "null_proof_delta0": null,
    }
    del fit
    holder.release()
    diagnostics = {
        "capture": capture.source_sha256,
        "dpi": capture.dpi,
        "scan": str(scan_path),
        "placements": len(placements),
        "windows": n_windows,
        "label_only_windows": n_windows - n_open,
        "mixed_windows": n_open,
        "fully_certified_tiles": len(fully),
        "setup_seconds": round(setup_seconds, 1),
        "field": {
            "seconds": round(field_seconds, 1),
            # ``report()`` runs before ``region_offsets``, so its own
            # ``adopted`` list is still empty; the region verdict is the
            # authoritative one and is what every configuration used.
            "adopted": [name for name, value in zip(PLANES, adopted)
                        if value],
            "region_adoption": [bool(value) for value in adopted],
            "coverage_by_plane": dict(zip(PLANES, report.coverage_by_plane)),
            "rms_dots": dict(zip(PLANES, report.rms_dots)),
            "peak_dots": dict(zip(PLANES, report.peak_dots)),
            "n_probes": report.n_probes,
            "n_probe_sites": report.n_probe_sites,
        },
        "probe": {
            "seconds": round(probe_seconds, 1),
            "sites_three_plane": len(sites),
            "windows_with_pose": len(poses),
            "cross_check_vs_production": cross,
        },
        "pose_residual": _pose_probe.pose_summary(poses),
        "sign_check": sign,
        "region_fit": region_fit,
        "field_plane_common_vs_pose": common,
        "override_divergence_vs_committed": divergence,
        "config_seconds": timing,
        "config_window_nulls": nulls,
        "refit": refit_detail,
        "peak_rss_gb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
    }
    poses_out = {
        int(key): {
            "patch_id": row.patch_id, "window_kind": row.window_kind,
            "n_sites": row.n_sites,
            "translation_xy": list(row.translation_xy),
            "median_xy": list(row.median_xy),
            "spread_xy": list(row.spread_xy),
            "magnitude_dots": row.magnitude_dots,
            "spread_dots": row.spread_dots,
            "consistent": row.consistent,
            "jacobian": [list(entry) for entry in row.jacobian],
            "shrinkage": row.shrinkage,
            "affine_edge_dots": row.affine_edge_dots,
            "affine_distinguishable": row.affine_distinguishable,
            "cv_translation_dots": row.cv_translation_dots,
            "cv_affine_dots": row.cv_affine_dots,
            "half_extent_cells": row.half_extent_cells,
            "centroid_xy": list(row.centroid_xy),
        }
        for key, row in poses.items()}
    return ({"frozen": blocks, "refit": refit_blocks}, diagnostics, poses_out)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def score_slots(blocks_by_capture, spec, slots, truth_bits, poses_by_capture,
                names) -> list[dict]:
    """Every open slot, every configuration: certificate and cell BER."""
    rows: list[dict] = []
    for ordinal, target in enumerate(slots):
        entry = {
            "page": target.page, "tile_y": target.tile_y,
            "tile_x": target.tile_x, "stream": target.stream,
            "plane": target.plane, "band": target.band,
            "siblings_certified": list(target.siblings_certified),
            "configurations": {},
        }
        residuals = []
        consistencies = []
        for capture_poses, capture_blocks in zip(
                poses_by_capture, blocks_by_capture[names[0]], strict=True):
            for patch_id in _patches_for(capture_blocks, target.address):
                row = capture_poses.get(patch_id)
                if row is not None:
                    residuals.append(row["magnitude_dots"])
                    consistencies.append(bool(row["consistent"]))
        entry["window_residual_dots_mean"] = (
            float(np.mean(residuals)) if residuals else None)
        entry["window_residual_dots_max"] = (
            float(np.max(residuals)) if residuals else None)
        entry["windows_self_consistent"] = (
            float(np.mean(consistencies)) if consistencies else None)
        for name in names:
            per_capture = blocks_by_capture[name]
            verdict = _pose_apply.slot_verdict(per_capture, spec, target)
            ber = (_pose_apply.slot_ber(per_capture, spec, target, truth_bits)
                   if truth_bits is not None else {})
            entry["configurations"][name] = {
                "certified": bool(verdict.get("certified")),
                "state": verdict.get("state"),
                "stage": verdict.get("stage"),
                "n_informative": verdict.get("n_informative"),
                "surrogate": verdict.get("surrogate"),
                "ber": ber.get("ber"),
                "observed": ber.get("observed"),
                "mean_abs_llr": ber.get("mean_abs_llr"),
            }
        rows.append(entry)
        if (ordinal + 1) % 50 == 0:
            print(f"    scored {ordinal + 1}/{len(slots)} slots", flush=True)
    return rows


def _patches_for(capture_blocks, address) -> set[int]:
    return {int(origin.patch_id)
            for block in capture_blocks.get(address, ())
            for origin in block.origins}


def summarise(rows: list[dict], names, baseline: str) -> dict:
    """Certificates per configuration, and the increment that decides."""
    def certified(name, subset) -> int:
        return sum(1 for row in subset
                   if row["configurations"][name]["certified"])

    def mean_ber(name, subset):
        values = [row["configurations"][name]["ber"] for row in subset
                  if row["configurations"][name].get("ber") is not None]
        return float(np.mean(values)) if values else None

    dead = [row for row in rows if row["band"] == "dead"]
    clear = [row for row in rows if row["band"] == "clear"]
    strata = {"all": rows, "dead_band": dead, "clear_band": clear,
              "Y": [row for row in rows if row["stream"] == "Y"],
              "not_Y": [row for row in rows if row["stream"] != "Y"]}
    magnitudes = [row["window_residual_dots_mean"] for row in rows
                  if row["window_residual_dots_mean"] is not None]
    cut = float(np.median(magnitudes)) if magnitudes else 0.0
    strata["residual_above_median"] = [
        row for row in rows
        if (row["window_residual_dots_mean"] or 0.0) > cut]
    strata["residual_below_median"] = [
        row for row in rows
        if row["window_residual_dots_mean"] is not None
        and row["window_residual_dots_mean"] <= cut]
    strata["windows_agree"] = [
        row for row in rows if (row["windows_self_consistent"] or 0.0) >= 0.5]
    strata["windows_disagree"] = [
        row for row in rows
        if row["windows_self_consistent"] is not None
        and row["windows_self_consistent"] < 0.5]

    table: dict[str, dict] = {}
    for key, subset in strata.items():
        table[key] = {
            "slots": len(subset),
            "certified": {name: certified(name, subset) for name in names},
            "increment_over_baseline": {
                name: certified(name, subset) - certified(baseline, subset)
                for name in names},
            "mean_ber": {name: mean_ber(name, subset) for name in names},
            "mean_ber_delta_pp": {
                name: (None if mean_ber(name, subset) is None
                       or mean_ber(baseline, subset) is None
                       else 100.0 * (mean_ber(name, subset)
                                     - mean_ber(baseline, subset)))
                for name in names},
        }
    won = {
        name: sorted(
            (row["tile_y"], row["tile_x"], row["stream"]) for row in rows
            if row["configurations"][name]["certified"]
            and not row["configurations"][baseline]["certified"])
        for name in names}
    lost = {
        name: sorted(
            (row["tile_y"], row["tile_x"], row["stream"]) for row in rows
            if row["configurations"][baseline]["certified"]
            and not row["configurations"][name]["certified"])
        for name in names}
    return {"residual_median_cut_dots": cut, "by_stratum": table,
            "slots_won_over_baseline": won,
            "slots_lost_versus_baseline": lost}


def verdict(summary: dict, names) -> dict:
    """The pre-registered bar, applied -- exploratory arms kept apart."""
    table = summary["by_stratum"]
    dead = table["dead_band"]["mean_ber_delta_pp"]

    def block(subset):
        increments = {name: table["all"]["increment_over_baseline"][name]
                      for name in subset}
        reductions = {name: (None if dead.get(name) is None else -dead[name])
                      for name in subset}
        return increments, reductions

    candidates = [name for name in names
                  if name in BAR["candidate_configurations"]]
    exploratory = [name for name in names
                   if name in BAR["exploratory_configurations"]]
    increments, reductions = block(candidates)
    extra_increments, extra_reductions = block(exploratory)
    passed_certificates = any(
        value >= BAR["certificate_increment_slots"]
        for value in increments.values())
    passed_ber = any(
        value is not None and value >= BAR["dead_band_mean_ber_reduction_pp"]
        for value in reductions.values())
    return {
        "certificate_increment": increments,
        "dead_band_ber_reduction_pp": reductions,
        "passed_certificate_clause": passed_certificates,
        "passed_ber_clause": passed_ber,
        "passed": bool(passed_certificates or passed_ber),
        "exploratory_certificate_increment": extra_increments,
        "exploratory_dead_band_ber_reduction_pp": extra_reductions,
    }


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="plane_fields.pose_writer", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lane", default=LANE_ID)
    parser.add_argument("--captures", default="1,2,3",
                        help="which archived captures to union")
    parser.add_argument("--limit-slots", type=int, default=0,
                        help="stop after this many open slots (0 = all)")
    parser.add_argument("--affine-prior-edge-dots", type=float, default=0.25,
                        help="shrinkage prior: print dots of EXTRA "
                             "displacement the Jacobian may produce at the "
                             "edge of a window's probe-site cloud")
    parser.add_argument("--min-affine-sites", type=int, default=6)
    parser.add_argument("--no-refit", dest="refit", action="store_false",
                        help="frozen detector only (skip the E1 refit arm)")
    parser.add_argument("--no-verify-sign", dest="verify_sign",
                        action="store_false")
    parser.add_argument("--no-ber", dest="ber", action="store_false")
    parser.add_argument("--q", type=float, default=0.9)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--tag", default="v1")
    parser.add_argument("--figure-only", default=None,
                        help="redraw the PNG from an existing run JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:            # noqa: C901
    args = parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.figure_only:
        from . import _pose_figures

        document = json.loads(Path(args.figure_only).read_text())
        path = _pose_figures.draw(document, out_dir / f"{args.tag}.png")
        print(f"redrew {path}")
        return 0

    from holo.format.resolve import resolve_format_ref
    from holo.receive import _parallel

    _parallel.set_worker_count(max(1, int(args.workers)))
    started = time.time()
    tree_before = _swim_inputs.tree_state()
    (out_dir / f"{args.tag}-bar.json").write_text(json.dumps({
        "schema": SCHEMA + "-bar",
        "declared": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pre_registered_bar": BAR,
        "tree_at_declaration": tree_before,
        "state": str(QUAL_STATE),
        "lane": args.lane,
    }, indent=1, sort_keys=True) + "\n")

    facts = _swim_inputs.read_facts(rebuild=args.rebuild_cache)
    spec = resolve_format_ref(FORMAT_REF)
    scans = _swim_inputs.verified_scan_paths()
    index = certified_index(facts.certificates)
    residue = residue_by_column(index, spec.layout.tiles_yx)
    slots = open_slots(index, spec.layout.tiles_yx)
    if args.limit_slots:
        slots = slots[:args.limit_slots]
    addresses = frozenset(row.address for row in slots)
    lane = lane_of(facts, args.lane)
    chosen = [int(value) for value in args.captures.split(",") if value]
    captures = [facts.captures[value - 1] for value in chosen]
    print(f"state {facts.state_sha256[:12]}… {facts.close_status} "
          f"certs {len(facts.certificates)} lane {lane.lane_id}\n"
          f"open slots {len(slots)} over {len(addresses)} tiles "
          f"(residue C {sum(residue['C'])} M {sum(residue['M'])} "
          f"Y {sum(residue['Y'])}); captures {chosen}", flush=True)

    truth_bits = truth_report = None
    if args.ber:
        mark = time.time()
        from . import _swim_truth

        payload = (QUAL_STATE.parent / "recovered.bin").read_bytes()
        truth_bits, truth_report = _swim_truth.page_component_bits(
            spec, payload, args.q, PAGE)
        truth_report["validation"] = (
            _swim_truth.validate_against_certificates(
                truth_bits, spec, facts.certificates, sample=24))
        truth_report["seconds"] = round(time.time() - mark, 1)
        if not truth_report["validation"].get("exact"):
            raise SystemExit(
                f"the reconstructed printed field does NOT match the "
                f"certificates: {truth_report['validation']} — REFUSING")
        print(f"truth field rebuilt in {truth_report['seconds']}s, exact on "
              f"{truth_report['validation']['checked']} certified tiles",
              flush=True)

    frozen: dict[str, list] = {name: [] for name in CONFIGS}
    refit: dict[str, list] = {name: [] for name in REFIT_CONFIGS}
    diagnostics: list[dict] = []
    poses_by_capture: list[dict] = []
    for capture in captures:
        print(f"\ncapture {capture.ordinal + 1} "
              f"{capture.source_sha256[:12]}…", flush=True)
        blocks, row, poses = run_capture(
            facts, spec, capture, scans[capture.source_sha256], lane, slots,
            addresses, args)
        for name in CONFIGS:
            frozen[name].append(blocks["frozen"][name])
        for name in REFIT_CONFIGS:
            if name in blocks["refit"]:
                refit[name].append(blocks["refit"][name])
        diagnostics.append(row)
        poses_by_capture.append(poses)
        pose_all = row["pose_residual"]["all_windows"]
        print(f"  pose residual: {pose_all['windows']} windows, magnitude "
              f"median {pose_all['magnitude_dots']['median']:.3f} p90 "
              f"{pose_all['magnitude_dots']['p90']:.3f} max "
              f"{pose_all['magnitude_dots']['max']:.3f} dot; spread median "
              f"{pose_all['within_window_spread_dots']['median']:.3f}; "
              f"consistent {pose_all['fraction_consistent']:.0%}",
              flush=True)
        print(f"  peak RSS {row['peak_rss_gb']} GB", flush=True)

    print("\nscoring the frozen-detector footing", flush=True)
    frozen_rows = score_slots(
        frozen, spec, slots, truth_bits, poses_by_capture, CONFIGS)
    frozen_summary = summarise(frozen_rows, CONFIGS, BAR[
        "baseline_configuration"])
    refit_rows = refit_summary = None
    usable = [name for name in REFIT_CONFIGS
              if len(refit[name]) == len(captures)]
    if usable:
        print("scoring the E1 refit footing", flush=True)
        refit_rows = score_slots(
            refit, spec, slots, truth_bits, poses_by_capture, usable)
        refit_summary = summarise(
            refit_rows, usable, BAR["baseline_configuration"])
    del truth_bits

    tree_after = _swim_inputs.tree_state()
    document = {
        "schema": SCHEMA,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pre_registered_bar": BAR,
        "state": {"path": str(QUAL_STATE), "sha256": facts.state_sha256,
                  "close": facts.close_status,
                  "payload_sha256": facts.payload_sha256,
                  "certificates": len(facts.certificates),
                  "format_row_id": facts.format_row_id,
                  "receiver_policy_id": facts.receiver_policy_id},
        "format": {"ref": FORMAT_REF, "spec_id": spec.spec_id,
                   "tiles_yx": list(spec.layout.tiles_yx),
                   "cell_dots": spec.cell_dots, "dpi": CAPTURE_DPI},
        "lane": {"lane_id": lane.lane_id,
                 "target_ppc": lane.target_ppc_num / lane.target_ppc_den},
        "inputs": {
            "scans": {sha: str(path) for sha, path in scans.items()},
            "recovered_payload": str(QUAL_STATE.parent / "recovered.bin"),
            "recovered_payload_sha256": _swim_inputs.sha256_file(
                QUAL_STATE.parent / "recovered.bin"),
            "captures_used": chosen,
        },
        "method": {
            "configurations": list(CONFIGS),
            "probe_mode": "TILE_FRAGMENT (the shipped density)",
            "anchors": "NOT collected — probes only, as E5/E5b/E5c were",
            "pose_model": (
                "plane-common per window, LOCAL print dots: quality-weighted "
                "mean (translation) and a ridge-shrunk local affine in dots "
                "per cell, shrunk toward identity with a "
                f"{args.affine_prior_edge_dots} dot edge-displacement prior"),
            "affine_distinguishability": "leave-one-site-out prediction error",
            "composite_order": "field delta then pose, additive at the "
                               "offsets_override seam",
            "baseline_path": "every configuration, (i) included, goes "
                             "through the same override seam",
            "workers": int(args.workers),
        },
        "approximations": [
            "one payload region per capture, fitted over ALL its placements "
            "(no restriction radius)",
            "frozen detector: one fit at the arm's zero scores every "
            "configuration; the E1 refit arm removes exactly that",
            "anchors are not collected, so configuration (ii) is the field "
            "from probes alone, not production's uF arm in full",
            "the archived scale plan is a strict PREFIX of this tree's",
        ],
        "residue_by_column": residue,
        "slots": {"open": len(slots), "tiles": len(addresses)},
        "truth_field": truth_report,
        "captures": diagnostics,
        "window_poses": poses_by_capture,
        "frozen": {"per_slot": frozen_rows, "summary": frozen_summary,
                   "verdict": verdict(frozen_summary, CONFIGS)},
        "refit": (None if refit_summary is None else {
            "configurations": usable, "per_slot": refit_rows,
            "summary": refit_summary,
            "verdict": verdict(refit_summary, usable)}),
        "tree_before": tree_before,
        "tree_after": tree_after,
        "void_tree_moved": _swim_inputs.tree_moved(tree_before, tree_after),
        "wall_seconds": round(time.time() - started, 1),
        "peak_rss_gb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
    }
    path = out_dir / f"{args.tag}.json"
    path.write_text(json.dumps(document, indent=1, sort_keys=True,
                               default=str))
    from . import _pose_figures

    figure = _pose_figures.draw(document, out_dir / f"{args.tag}.png")
    say(document)
    print(f"\nwrote {path}\n      {figure}\n"
          f"runtime {document['wall_seconds']:.0f}s, peak RSS "
          f"{document['peak_rss_gb']} GB")
    if document["void_tree_moved"]:
        print("WARNING: src/holo moved during the run — this result is VOID")
    return 0


def say(document: dict) -> None:
    for footing in ("frozen", "refit"):
        entry = document.get(footing)
        if not entry:
            continue
        print(f"\n== {footing} footing ==")
        table = entry["summary"]["by_stratum"]
        names = list(table["all"]["certified"])
        header = "  stratum              slots  " + "  ".join(
            f"{name:>18s}" for name in names)
        print(header)
        for key in ("all", "dead_band", "clear_band", "windows_agree",
                    "residual_above_median"):
            row = table.get(key)
            if not row:
                continue
            print(f"  {key:20s} {row['slots']:5d}  " + "  ".join(
                f"{row['certified'][name]:18d}" for name in names))
            print(f"  {'  mean BER':20s} {'':5s}  " + "  ".join(
                "%18s" % ("—" if row["mean_ber"][name] is None
                          else f"{row['mean_ber'][name]:.4f}")
                for name in names))
        print("  verdict: " + json.dumps(entry["verdict"]))


__all__ = ["BAR", "SCHEMA", "main", "open_slots", "score_slots",
           "summarise", "verdict", "verify_sign"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
