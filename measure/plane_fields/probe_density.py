#!/usr/bin/env python
"""E5/E5b — the probe-DENSITY comparison (INDEPENDENT-PLANES §2.9/§2.9b).

Declared densities, on ONE archived ``(capture, lane)`` of the W6
qualification state, through the production pass itself:

    A  block-per-bin   one 5x5-cell block per field bin  (what is built)
    B  whole-tile      one 64x64-cell NCC per certified tile (V0's method)
    C  every-block     every eligible 5x5 block
    F  tile-fragment   one probe per (certified tile, covering window)

E5 (2026-08-22) ruled between A, B and C on the LABEL-ONLY window
footing and shipped A.  E5b (2026-08-23) adds F and drops the two
eligibility predicates E5 inherited: label-only windows only, and a
template that must fit wholly inside one window.  Every run declares its
``--window-kind`` so the effect of dropping the first is visible on its
own.

Reported per density: reach in certified tiles (split by window kind),
probe count, wall time, ms/probe, template-size distribution, per-plane
field coverage/rms/peak, adoption per plane, the SOLVED field's column
profile against the supervised regmap-gt sinusoid, the per-TILE field
residual, the NCC-quality distribution including what the 0.30 floor
rejects, and the per-window PLANE-COMMON residual (the pose feedback,
measured and never applied).

READ-ONLY.  Never writes a state, never calls ``save_session``.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.probe_density [--capture 1] [--modes ...]
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import numpy as np

from . import _density, _density_figures, _swim_inputs
from ._swim_inputs import DEAD_BANDS, PLANES

SCHEMA = "plane-fields-e5-probe-density-v2"
OUT_DIR = _swim_inputs.MAIN_SCRATCH / "plane-fields" / "p2" / "e5b"

MODES = ("block-per-bin", "whole-tile", "every-block", "tile-fragment")
LABEL = {"block-per-bin": "A block/bin", "whole-tile": "B whole-tile",
         "every-block": "C every-block", "tile-fragment": "F tile-fragment"}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="E5/E5b probe densities")
    parser.add_argument("--capture", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--lane", default=None,
                        help="force a lane id (default: finest ordinary)")
    parser.add_argument(
        "--modes", default="block-per-bin,whole-tile,tile-fragment",
        help=f"comma-separated subset of {','.join(MODES)}")
    parser.add_argument(
        "--window-kind", default="all",
        choices=("all", "label-only", "mixed"),
        help="which windows the probe pass is offered (production: all)")
    parser.add_argument(
        "--bridge-label-only", action="store_true",
        help="also run every mode on the label-only footing (the E5 bridge)")
    parser.add_argument("--census-only", action="store_true",
                        help="site selection only — no NCC, no raster")
    parser.add_argument("--precision-tiles", type=int, default=400,
                        help="tiles the matched per-probe comparison uses")
    parser.add_argument("--skip-precision", action="store_true")
    parser.add_argument("--figure-only", action="store_true",
                        help="re-draw the PNG from an existing run JSON")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--tag", default="e5b")
    return parser.parse_args(argv)


# --------------------------------------------------------------------------
# scoring against the supervised measurement
# --------------------------------------------------------------------------
def regmap_truth(columns: int) -> dict[str, np.ndarray]:
    header = json.loads(
        (_swim_inputs.REGMAP_GT / "plane-offsets.json").read_text())
    px_per_dot = float(header["px_per_dot"])
    by_column = {int(row["tx"]): row
                 for row in _swim_inputs.regmap_gt_columns()}
    out: dict[str, np.ndarray] = {}
    for key in ("dY_rel_x", "dC_x", "dM_x", "dY_x"):
        out[key] = np.asarray([
            by_column[tile_x][key] / px_per_dot if tile_x in by_column
            else np.nan for tile_x in range(columns)], np.float64)
    out["px_per_dot"] = px_per_dot
    return out


def score(profile: dict, truth: dict) -> dict:
    from .field_from_certs import compare_profiles

    entry: dict = {}
    for key in ("dY_rel_x", "dC_x", "dM_x", "dY_x"):
        entry[key] = compare_profiles(
            np.asarray(profile[key], np.float64), truth[key])
    return entry


def stratum_addresses(population: frozenset, count: int) -> frozenset:
    """A tile stratum that reaches the dead bands AND the clean columns.

    Deterministic: the addresses are enumerated in canonical order inside
    each half and taken at an even stride, so the stratum is a function
    of the state, not of a draw.
    """
    dead = sorted(a for a in population if a[2] in DEAD_BANDS)
    clean = sorted(a for a in population if a[2] not in DEAD_BANDS)
    picked: list[tuple[int, int, int]] = []
    for population, share in ((dead, count // 2), (clean, count - count // 2)):
        if not population or share <= 0:
            continue
        stride = max(1, len(population) // share)
        picked.extend(population[::stride][:share])
    return frozenset(picked)


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def main(argv=None) -> int:                                  # noqa: C901
    args = parse_args(argv)
    modes = [name.strip() for name in args.modes.split(",") if name.strip()]
    for name in modes:
        if name not in MODES:
            raise SystemExit(f"unknown mode {name!r}; pick from {MODES}")
    started = time.time()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.figure_only:
        path = out_dir / f"{args.tag}.json"
        figure = _density_figures.draw(
            json.loads(path.read_text()), out_dir / f"{args.tag}.png")
        print(f"redrew {figure} from {path}")
        return 0
    tree_before = _swim_inputs.tree_state()

    facts = _swim_inputs.read_facts(verbose=False)
    print(f"state {facts.state_path}\n      sha {facts.state_sha256[:16]}… "
          f"close={facts.close_status} certificates={len(facts.certificates)}",
          flush=True)

    from holo.format.resolve import resolve_format_ref
    from holo.receive.color_field import PlaneFieldConfig, ProbeMode

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec = resolve_format_ref(_swim_inputs.FORMAT_REF)
    tiles_yx = (spec.layout.cells_yx[0] // 64, spec.layout.cells_yx[1] // 64)

    capture = facts.captures[args.capture - 1]
    scan_path = _swim_inputs.verified_scan_paths()[capture.source_sha256]
    lane = _density.pick_lane(capture, args.lane)
    print(f"capture {capture.ordinal + 1}/{len(facts.captures)} "
          f"{capture.source_sha256[:12]}… {capture.dpi:g} dpi  "
          f"lane {lane.lane_id} ({lane.target_ppc_num / lane.target_ppc_den:g}"
          f" px/cell)\nscan  {scan_path.name}", flush=True)

    from ._swim_setup import LaneRasters, build_placements

    rasters = LaneRasters(spec, capture, scan_path)
    raster = rasters.for_lane(lane)
    placements, _by_patch = build_placements(
        facts, spec, capture, lane, raster)
    regions, fully = _density.classify_windows(
        spec, facts.certificates, placements)
    n_windows = sum(len(row.windows) for row in regions)
    n_open = sum(row.n_open for row in regions)
    print(f"placements {len(placements)} -> regions {len(regions)}, "
          f"windows {n_windows} = {n_windows - n_open} label-only + "
          f"{n_open} mixed; fully-certified tiles {len(fully)} "
          f"of {tiles_yx[0] * tiles_yx[1]}", flush=True)

    truth = regmap_truth(tiles_yx[1])
    done_tiles = tuple(sorted(fully))
    full_projection, _ = _density.projection_source(spec, facts.certificates)

    # ---- reach: which certified tiles each density can probe at all ---
    census: dict[str, dict] = {}
    for mode_name in modes:
        config = PlaneFieldConfig(probe_mode=ProbeMode(mode_name))
        found = _density.site_census(
            spec, regions, full_projection, config, args.window_kind)
        census[mode_name] = found
        cells = found["template_cells"]
        by_kind = "  ".join(
            f"{kind} {len(row['tiles']):d}t/{row['sites']:,}s"
            for kind, row in found["by_kind"].items())
        print(f"  reach {LABEL[mode_name]:16s} sites {found['n_sites']:9,d}  "
              f"tiles {len(found['tiles']):5d} of {len(fully)} certified  "
              f"[{by_kind}]  template cells median "
              f"{int(np.median(cells)) if cells.size else 0:,}  "
              f"({found['selection_seconds']:.1f} s)", flush=True)
    reach_document = {
        name: {
            "n_sites": row["n_sites"],
            "n_tiles": len(row["tiles"]),
            "selection_seconds": round(row["selection_seconds"], 2),
            "template_cells": summarize(
                row["template_cells"].astype(np.float64)),
            "total_template_cells": int(row["template_cells"].sum()),
            "by_window_kind": {
                kind: {"windows": entry["windows"], "sites": entry["sites"],
                       "tiles": len(entry["tiles"])}
                for kind, entry in row["by_kind"].items()},
            "tiles_reached_only_through_mixed_windows": len(
                row["by_kind"]["mixed"]["tiles"]
                - row["by_kind"]["label-only"]["tiles"]),
        }
        for name, row in census.items()
    }
    shared_reach = frozenset.intersection(
        *(census[name]["tiles"] for name in modes)) if modes else frozenset()
    print(f"  reach shared by every mode: {len(shared_reach)} tiles",
          flush=True)

    results: dict[str, dict] = {}
    bridge: dict[str, dict] = {}
    per_probe: dict[str, dict] = {}
    if not args.census_only:
        # ---- full sheet, one run per density ---------------------------
        for mode_name in modes:
            config = PlaneFieldConfig(probe_mode=ProbeMode(mode_name))
            entry = run_one(
                spec, raster, regions, full_projection, config, done_tiles,
                args.window_kind, tiles_yx, truth, census[mode_name])
            results[mode_name] = entry
            say_density(LABEL[mode_name], entry)
            if args.bridge_label_only and args.window_kind != "label-only":
                bridge[mode_name] = run_one(
                    spec, raster, regions, full_projection, config,
                    done_tiles, "label-only", tiles_yx, truth, None)
                say_density(
                    f"{LABEL[mode_name]} (label-only footing)",
                    bridge[mode_name])

        # ---- quality distribution + matched per-probe precision --------
        if not args.skip_precision and shared_reach:
            precision_tiles = stratum_addresses(
                shared_reach, args.precision_tiles)
            precision_projection, _ = _density.projection_source(
                spec, facts.certificates, precision_tiles)
            for mode_name in modes:
                config = PlaneFieldConfig(probe_mode=ProbeMode(mode_name))
                per_probe[mode_name] = precision(
                    spec, raster, regions, precision_projection, config,
                    precision_tiles, args.window_kind, truth)
                say_precision(LABEL[mode_name], per_probe[mode_name])
            shared = frozenset.intersection(*(
                frozenset(map(tuple, per_probe[name]["tile_set"]))
                for name in modes))
            for mode_name in modes:
                per_probe[mode_name]["shared_tiles"] = len(shared)
                per_probe[mode_name]["tile_set"] = None
            print(f"  tiles every mode produced a three-plane site on: "
                  f"{len(shared)}", flush=True)

    rasters.release()
    tree_after = _swim_inputs.tree_state()
    document = {
        "schema": SCHEMA,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "runtime_seconds": round(time.time() - started, 1),
        "void_tree_moved": _swim_inputs.tree_moved(tree_before, tree_after),
        "tree_before": tree_before, "tree_after": tree_after,
        "modes": modes,
        "window_kind": args.window_kind,
        "inputs": {
            "state_path": facts.state_path,
            "state_sha256": facts.state_sha256,
            "close_status": facts.close_status,
            "format_row_id": facts.format_row_id,
            "receiver_policy_id": facts.receiver_policy_id,
            "capture_ordinal": capture.ordinal + 1,
            "capture_sha256": capture.source_sha256,
            "capture_dpi": capture.dpi,
            "scan_path": str(scan_path),
            "lane_id": lane.lane_id,
            "lane_px_per_cell": lane.target_ppc_num / lane.target_ppc_den,
            "tiles_yx": list(tiles_yx),
            "regmap_gt_dir": str(_swim_inputs.REGMAP_GT),
            "regmap_px_per_dot": truth["px_per_dot"],
        },
        "method": {
            "anchors": "NOT collected — probes only (see _density docstring)",
            "solve": "one solve after every region's probes",
            "probe_min_quality": 0.30,
            "probe_block_cells": 5,
            "bins_per_tile": 1,
            "dead_band_columns": list(DEAD_BANDS),
            "machine_load": "two unrelated decodes were running; wall times "
                            "are comparable WITHIN this run, not against E5",
        },
        "counts": {
            "placements": len(placements),
            "windows": n_windows,
            "label_only_windows": n_windows - n_open,
            "mixed_windows": n_open,
            "probe_windows": n_windows - n_open,
            "open_windows": n_open,
            "fully_certified_tiles": len(fully),
            "tiles_total": tiles_yx[0] * tiles_yx[1],
            "window_shape_yx_cells": sorted({
                tuple(int(v) for v in window.patch.segment.segment
                      .window.shape_yx_cells)
                for region in regions for window in region.windows}),
        },
        "reach": reach_document,
        "reach_shared_by_every_mode": len(shared_reach),
        "regmap_gt_profile": {
            key: [None if not np.isfinite(v) else round(float(v), 5)
                  for v in truth[key]]
            for key in ("dY_rel_x", "dC_x", "dM_x", "dY_x")},
        "full_sheet": results,
        "label_only_footing": bridge,
        "per_probe_precision": per_probe,
    }
    path = out_dir / f"{args.tag}.json"
    path.write_text(json.dumps(document, indent=1, allow_nan=True))
    figure = (
        _density_figures.draw(document, out_dir / f"{args.tag}.png")
        if results else None)
    print(f"\nwrote {path}" + (f"\n      {figure}" if figure else "")
          + f"\nruntime {document['runtime_seconds']:.0f} s")
    if document["void_tree_moved"]:
        print("WARNING: src/holo moved during the run — this result is VOID")
    return 0


def run_one(spec, raster, regions, projection, config, done_tiles, kind,
            tiles_yx, truth, census_row) -> dict:
    """One density over the whole sheet: cost, field, adoption, pose."""
    builder, report, _adoption, wall = _density.run_density(
        spec, raster, regions, projection, config, done_tiles, kind)
    profile = _density.field_column_profile(
        builder._field, regions[0].page, tiles_yx)
    tile_rows = _density.field_tile_relative(
        builder._field, regions[0].page, tiles_yx)
    entry = {
        "scope": f"full sheet, {kind} windows",
        "window_kind": kind,
        "reach_tiles": (
            len(census_row["tiles"]) if census_row is not None else None),
        "n_probe_sites": report.n_probe_sites,
        "n_probes": report.n_probes,
        "probe_seconds": round(report.probe_seconds, 2),
        "wall_seconds": round(wall, 2),
        "ms_per_probe": round(1000.0 * wall / max(1, report.n_probes), 3),
        "ms_per_site": round(1000.0 * wall / max(1, report.n_probe_sites), 3),
        "solve_seconds": round(report.solve_seconds, 2),
        "coverage_by_plane": dict(zip(PLANES, report.coverage_by_plane)),
        "rms_dots": dict(zip(PLANES, report.rms_dots)),
        "peak_dots": dict(zip(PLANES, report.peak_dots)),
        "adopted": list(report.adopted),
        "regions_adopted_by_plane": dict(
            zip(PLANES, report.regions_adopted_by_plane)),
        "regions": report.regions,
        "n_samples": report.n_samples,
        "profile": {key: [None if not np.isfinite(v) else round(v, 5)
                          for v in profile[key]]
                    for key in ("dC_x", "dM_x", "dY_x", "dY_rel_x")},
        "covered_tiles_by_column": profile["covered_tiles"],
        "score": score(profile, truth),
        "tile_residual_vs_gt": tile_residual(tile_rows, truth),
        "adoption_detail": _density.adoption_detail(
            builder._field, regions, config),
        "window_pose_residual": _density.pose_residual_summary(report),
    }
    del builder
    return entry


def precision(spec, raster, regions, projection, config, tiles, kind,
              truth) -> dict:
    """Per-PROBE agreement with the supervised measurement, matched tiles."""
    rows = _density.instrumented_probes(
        spec, raster, regions, projection, config, tiles=tiles, kind=kind)
    sites = _density.per_site_relative(rows)
    residual = np.asarray(
        [row["dY_rel_x"] - truth["dY_rel_x"][row["tile_x"]]
         for row in sites
         if np.isfinite(truth["dY_rel_x"][row["tile_x"]])], np.float64)
    # Per TILE as well as per site: a 5x5 density can put several sites on
    # one tile, so the site-level scatter is not the number a per-tile
    # field consumes.
    by_tile: dict[tuple[int, int], list[float]] = {}
    for row in sites:
        by_tile.setdefault(
            (row["tile_y"], row["tile_x"]), []).append(row["dY_rel_x"])
    tile_residual_rows = np.asarray([
        float(np.median(values)) - truth["dY_rel_x"][tile_x]
        for (_tile_y, tile_x), values in by_tile.items()
        if np.isfinite(truth["dY_rel_x"][tile_x])], np.float64)
    cells = np.asarray(
        [row["cells"] for row in rows if "cells" in row], np.float64)
    return {
        "tiles": len(tiles),
        "quality": _density.quality_summary(rows, config.probe_min_quality),
        "template_cells": summarize(cells),
        "sites_with_all_three_planes": len(sites),
        "sites_per_tile": round(len(sites) / max(1, len(by_tile)), 3),
        "residual_vs_regmap_gt": summarize(residual),
        "per_tile_residual_vs_regmap_gt": summarize(tile_residual_rows),
        "tile_set": sorted(by_tile),
    }


def tile_residual(rows, truth: dict) -> dict:
    """Per-TILE field ``dY_rel_x`` against the supervised column value.

    The decision-shaped accuracy number: how far the field the receiver
    would APPLY at a tile sits from the supervised measurement of that
    tile's column, over every tile the field covers.
    """
    values = np.asarray(
        [row[2] - truth["dY_rel_x"][row[1]] for row in rows
         if np.isfinite(truth["dY_rel_x"][row[1]])], np.float64)
    entry = summarize(values)
    entry["tiles"] = len(rows)
    return entry


def summarize(values: np.ndarray) -> dict:
    finite = np.asarray(values, np.float64)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return {"n": 0, "mean": float("nan"), "sd": float("nan"),
                "mad": float("nan")}
    return {
        "n": int(finite.size),
        "mean": float(finite.mean()),
        "sd": float(finite.std(ddof=1)) if finite.size > 1 else float("nan"),
        "mad": float(np.median(np.abs(finite - np.median(finite))) * 1.4826),
        "median": float(np.median(finite)),
        "p10": float(np.percentile(finite, 10)),
        "p90": float(np.percentile(finite, 90)),
    }


def say_density(label: str, entry: dict) -> None:
    print(f"\n== {label} ==  {entry['scope']}", flush=True)
    print(f"  sites {entry['n_probe_sites']:,}  probes {entry['n_probes']:,}  "
          f"{entry['wall_seconds']:.1f} s  "
          f"{entry['ms_per_probe']:.2f} ms/probe", flush=True)
    residual = entry.get("tile_residual_vs_gt")
    if residual:
        print(f"  field vs regmap-gt, per covered tile: n={residual['n']} "
              f"bias {residual['mean']:+.3f} sd {residual['sd']:.3f} "
              f"mad {residual['mad']:.3f} dot", flush=True)
    for region in entry.get("adoption_detail", ()):
        for name, gate in region["planes"].items():
            print(f"    gate {name}: coverage "
                  f"{gate['coverage_fraction']:.3f}/"
                  f"{gate['coverage_gate']:.2f}  sd "
                  f"{gate.get('median_uncertainty_dots', float('nan')):.3f}/"
                  f"{gate['uncertainty_gate']:.2f}  magnitude "
                  f"{gate.get('median_magnitude_dots', float('nan')):.4f}/"
                  f"{gate['magnitude_gate']:.2f}", flush=True)
    print("  coverage " + "  ".join(
        f"{name} {entry['coverage_by_plane'][name]:.3f}" for name in PLANES)
        + "   rms " + "  ".join(
            f"{name} {entry['rms_dots'][name]:.3f}" for name in PLANES)
        + "   peak " + "  ".join(
            f"{name} {entry['peak_dots'][name]:.3f}" for name in PLANES),
        flush=True)
    print(f"  adopted {entry['adopted'] or '(none)'}", flush=True)
    for key in ("dY_rel_x", "dC_x", "dM_x", "dY_x"):
        row = entry["score"][key]
        print(f"    {key:9s} spearman {row['spearman']:+.4f}  amp x"
              f"{row['amplitude_ratio']:.2f}  n={row['n_columns']}",
              flush=True)
    pose = entry.get("window_pose_residual") or {}
    if pose.get("windows"):
        print(f"  window pose residual (MEASURED, not applied): "
              f"{pose['windows']} windows, magnitude median "
              f"{pose['magnitude_dots']['median']:.3f} p90 "
              f"{pose['magnitude_dots']['p90']:.3f} max "
              f"{pose['magnitude_dots']['max']:.3f} dot; within-window "
              f"spread median "
              f"{pose['within_window_spread_dots']['median']:.3f} dot; "
              f"consistent {pose['fraction_consistent']:.0%} of "
              f"{pose['windows_with_multiple_sites']} multi-site windows",
              flush=True)


def say_precision(label: str, entry: dict) -> None:
    print(f"  per-probe {label}: {entry['sites_with_all_three_planes']} "
          f"three-plane sites, template cells median "
          f"{entry['template_cells'].get('median', float('nan')):,.0f}, "
          f"dY_rel_x - GT bias "
          f"{entry['residual_vs_regmap_gt']['mean']:+.3f} "
          f"sd {entry['residual_vs_regmap_gt']['sd']:.3f} "
          f"mad {entry['residual_vs_regmap_gt']['mad']:.3f} dot "
          f"(per tile mad "
          f"{entry['per_tile_residual_vs_regmap_gt']['mad']:.3f})",
          flush=True)
    for name in PLANES:
        plane_entry = entry["quality"]["per_plane"][name]
        if plane_entry["measured"]:
            print(f"      {name}: q median {plane_entry['median']:.3f}, "
                  f"below {0.30:.2f} floor "
                  f"{plane_entry['fraction_below_floor']:.1%} of "
                  f"{plane_entry['measured']}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
