#!/usr/bin/env python
"""W0 / V0 — the per-plane registration field from certificates alone.

docs/PLANE-FIELDS.md §3c P0 and §6.2 W0.  This instrument builds the
per-plane translation-delta field for a colour receive state PURELY from

    certificates  +  committed poses  +  the archived scan

— no page GT sidecar, no fitted global affine, no receiver code changed —
and compares it against the supervised ``regmap-gt`` measurement of the
sheet-I Y-plane x-registration sinusoid (e033 §033.4).

PRE-REGISTERED GATE (fixed before the first run, docs/PLANE-FIELDS.md
§4 V0).  The comparison quantity is the SUPERVISED HEADLINE QUANTITY,
``dY_rel_x`` = Y minus the (C+M)/2 plane-common mean, per tile column:
it is the quantity the sinusoid was measured in and the only one that is
reference-free (this instrument's zero is the committed pose, regmap-gt's
zero is its own nine-anchor affine; the raw per-plane profiles differ by
that unknown common frame, so they are reported as context, never as the
gate).  V0 PASSES iff, for the Y-plane x-offset per-column profile:

    Spearman(instrument, regmap-gt) >= 0.7
    dominant period within +/-20% of the regmap-gt period
    amplitude (peak-to-peak of the per-column profile) within a factor 2

C and M ride along as controls: ``dCM_x`` = C - M is likewise
reference-free; the raw C/M profiles are reported for completeness.

READ-ONLY: opens the state (``load_session``), the scan TIFF and the
regmap-gt JSON.  Never writes a state, never calls ``save_session``.

    cd <repo>          # or a plane-fields worktree
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.field_from_certs [--capture 1] \
            [--workers 8] [--limit N] [--bandwidth-tiles 2.0]
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import _figures, _inputs, _probe
from ._probe import PLANE_NAMES, TileJob

SCHEMA = "plane-fields-w0-v1"
GATE = {"spearman_min": 0.7, "period_tolerance": 0.20,
        "amplitude_factor": 2.0}
# Sheet-I decoder Y-certificate residue per tile column (e033 §033.4,
# carried by regmap-gt/measure_plane_offsets.py) — context for the
# figure only; no metric depends on it.
RESIDUE = (7, 1, 21, 5, 0, 0, 0, 14, 53, 38, 37, 39, 0, 0, 0, 45, 49, 45,
           31, 47, 2, 0, 0, 0, 4, 3, 5, 43, 50, 24, 12, 0, 2, 0, 0, 0, 4)


# --------------------------------------------------------------------------
# committed geometry
# --------------------------------------------------------------------------
def pose_page_rect(row) -> tuple[int, int, int, int]:
    """Page-cell rectangle a committed pose covers (``_pose_span_tiles``).

    Mirrors ``production_refine._pose_span_tiles``: the window's rotated
    shape at its integer cell origin encloses every audited cell.
    """
    height, width = (int(value) for value in row.window_shape_yx_cells)
    if int(row.rot90) % 2:
        height, width = width, height
    y0, x0 = (int(value) for value in row.cell_origin_yx)
    return y0, x0, y0 + height, x0 + width


def select_poses(facts: _inputs.StateFacts, tiles_yx: tuple[int, int]):
    """Best committed pose per (page, tile), finest ordinary lane first.

    A tile qualifies only when its FULL 64x64 page-cell extent lies
    inside the window's page-cell rectangle: a partially covered tile
    would probe against cells the window never carried.
    """
    rank_of_lane = {
        lane.lane_id: (0 if lane.kind == "ordinary" else 1, -lane.target_ppc,
                       lane.ordinal)
        for lane in facts.lanes
    }
    best: dict[tuple[int, int, int], tuple] = {}
    contained = partial = 0
    for row in facts.poses:
        if row.placement_outcome != "accepted":
            continue
        rank = rank_of_lane.get(row.lane_id)
        if rank is None:
            continue
        y0, x0, y1, x1 = pose_page_rect(row)
        for tile_y in range(max(0, y0) // 64, min(tiles_yx[0],
                                                  (max(0, y1) + 63) // 64)):
            for tile_x in range(max(0, x0) // 64,
                                min(tiles_yx[1], (max(0, x1) + 63) // 64)):
                inside = (y0 <= tile_y * 64 and y1 >= tile_y * 64 + 64
                          and x0 <= tile_x * 64 and x1 >= tile_x * 64 + 64)
                if not inside:
                    partial += 1
                    continue
                contained += 1
                key = (int(row.page), tile_y, tile_x)
                score = (*rank, -float(row.quality))
                current = best.get(key)
                if current is None or score < current[0]:
                    best[key] = (score, row)
    return {key: value[1] for key, value in best.items()}, contained, partial


def build_jobs(facts: _inputs.StateFacts, spec, poses, limit: int | None):
    """One ``TileJob`` per certified tile that a committed pose contains."""
    from holo.receive.color_projection import project_certified_color_tile

    stream_of_plane = {profile.stream_id: plane for plane, profile
                       in enumerate(spec.stream_profiles)}
    grouped: dict[tuple[int, int, int], list] = {}
    for record in facts.certificates:
        grouped.setdefault(
            (int(record.page), *(int(v) for v in record.tile_yx)),
            []).append(record)

    jobs: list[TileJob] = []
    skipped_no_pose = 0
    plane_certificates = [0, 0, 0]
    for address in sorted(grouped):
        records = grouped[address]
        planes = tuple(sorted({stream_of_plane[row.stream_id]
                               for row in records
                               if row.stream_id in stream_of_plane}))
        for plane in planes:
            plane_certificates[plane] += 1
        pose = poses.get(address)
        if pose is None:
            skipped_no_pose += 1
            continue
        if not planes:
            continue
        projection = project_certified_color_tile(records, spec, address)
        known = np.asarray(projection.known_mask)
        jobs.append(TileJob(
            page=address[0], tile_y=address[1], tile_x=address[2],
            planes=planes,
            native_affine=tuple(float(v) for v in pose.native_affine),
            bits=np.asarray(projection.component_bits, np.uint8),
            known_all=bool(all(known[..., plane].all() for plane in planes)),
            pose_id=pose.pose_id, lane_id=pose.lane_id,
            pose_quality=float(pose.quality),
            cell_dots=int(spec.cell_dots),
        ))
        if limit is not None and len(jobs) >= limit:
            break
    return jobs, skipped_no_pose, tuple(plane_certificates), len(grouped)


# --------------------------------------------------------------------------
# probing
# --------------------------------------------------------------------------
def _run_probe(args):
    job, scan_path, crosstalk = args
    try:
        return _probe.probe_tile(job, scan_path, crosstalk)
    except Exception as exc:                                # noqa: BLE001
        return {"page": job.page, "tile_y": job.tile_y, "tile_x": job.tile_x,
                "error": repr(exc)}


def run_probes(jobs, scan_path: str, crosstalk, workers: int):
    tasks = [(job, scan_path, crosstalk) for job in jobs]
    if workers <= 1:
        return [_run_probe(task) for task in tasks]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run_probe, tasks, chunksize=8))


def probe_rows(results: list[dict]) -> list[dict]:
    """Flatten probes into per-tile rows with the derived contrasts."""
    rows: list[dict] = []
    for result in results:
        if "planes" not in result:
            continue
        row = {key: result[key] for key in
               ("page", "tile_y", "tile_x", "lane_id", "px_per_dot",
                "common_dots_xy", "common_corr", "outside_fraction")}
        offsets = {}
        for name, values in result["planes"].items():
            if "offset_dots_xy" not in values:
                continue
            offsets[name] = values["offset_dots_xy"]
            row[f"d{name}_x"] = values["offset_dots_xy"][0]
            row[f"d{name}_y"] = values["offset_dots_xy"][1]
            row[f"{name}_corr"] = values["corr"]
            row[f"{name}_peak"] = values["peak"]
            row[f"{name}_ratio"] = values["ratio"]
            row[f"{name}_src"] = values["src"]
        if {"C", "M"} <= offsets.keys():
            row["dCM_x"] = offsets["C"][0] - offsets["M"][0]
            row["dCM_y"] = offsets["C"][1] - offsets["M"][1]
        if {"C", "M", "Y"} <= offsets.keys():
            for axis, index in (("x", 0), ("y", 1)):
                row[f"dY_rel_{axis}"] = (
                    offsets["Y"][index]
                    - 0.5 * (offsets["C"][index] + offsets["M"][index]))
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------
QUANTITIES = ("dC_x", "dM_x", "dY_x", "dC_y", "dM_y", "dY_y",
              "dY_rel_x", "dY_rel_y", "dCM_x", "dCM_y")


def mad(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    return float(np.median(np.abs(values - np.median(values))) * 1.4826)


def per_column(rows: list[dict], columns: int) -> list[dict]:
    table: list[dict] = []
    for tile_x in range(columns):
        selected = [row for row in rows if row["tile_x"] == tile_x]
        entry: dict = {"tile_x": tile_x, "n_tiles": len(selected)}
        for key in QUANTITIES:
            values = np.array([row[key] for row in selected if key in row],
                              np.float64)
            entry[f"n_{key}"] = int(values.size)
            entry[key] = float(np.median(values)) if values.size else float(
                "nan")
            entry[f"{key}_mad"] = mad(values)
        for name in PLANE_NAMES:
            values = np.array(
                [row[f"{name}_corr"] for row in selected
                 if f"{name}_corr" in row], np.float64)
            entry[f"{name}_corr"] = (float(np.median(values))
                                     if values.size else float("nan"))
        table.append(entry)
    return table


def smooth_field(rows: list[dict], tiles_yx: tuple[int, int], key_x: str,
                 key_y: str, bandwidth_tiles: float):
    """Gaussian-weighted local mean of the delta field over tile space.

    Nonparametric by design (docs/PLANE-FIELDS.md §3: harmonics are a
    prior, never the representation).  Support radius = 3 sigma; a grid
    node with no probe inside it stays NaN.
    """
    points = np.array([[row["tile_y"], row["tile_x"]] for row in rows
                       if key_x in row], np.float64)
    values = np.array([[row[key_x], row[key_y]] for row in rows
                       if key_x in row], np.float64)
    rows_n, columns_n = tiles_yx
    field = np.full((2, rows_n, columns_n), np.nan)
    counts = np.zeros((rows_n, columns_n))
    if points.size == 0:
        return field, counts
    for row in rows:
        if key_x in row:
            counts[row["tile_y"], row["tile_x"]] += 1
    radius = 3.0 * bandwidth_tiles
    for tile_y in range(rows_n):
        distance_y = points[:, 0] - tile_y
        near_y = np.abs(distance_y) <= radius
        if not near_y.any():
            continue
        for tile_x in range(columns_n):
            distance_x = points[:, 1] - tile_x
            near = near_y & (np.abs(distance_x) <= radius)
            if not near.any():
                continue
            squared = distance_y[near] ** 2 + distance_x[near] ** 2
            weights = np.exp(-0.5 * squared / bandwidth_tiles ** 2)
            total = weights.sum()
            if total <= 1e-9:
                continue
            field[0, tile_y, tile_x] = float(
                weights @ values[near, 0] / total)
            field[1, tile_y, tile_x] = float(
                weights @ values[near, 1] / total)
    return field, counts


# --------------------------------------------------------------------------
# comparison against the supervised regmap-gt measurement
# --------------------------------------------------------------------------
def dominant_period_tiles(profile: np.ndarray) -> float:
    """Peak of the Hann-windowed DFT (regmap-gt/report.py's estimator)."""
    finite = np.isfinite(profile)
    if finite.sum() < 8:
        return float("nan")
    values = np.where(finite, profile, np.nanmean(profile))
    values = values - values.mean()
    spectrum = np.abs(np.fft.rfft(values * np.hanning(values.size)))
    index = int(np.argmax(spectrum[1:]) + 1)
    return float(values.size) / index


def compare_profiles(instrument: np.ndarray, truth: np.ndarray) -> dict:
    from scipy.stats import spearmanr

    both = np.isfinite(instrument) & np.isfinite(truth)
    entry: dict = {"n_columns": int(both.sum())}
    if both.sum() >= 4:
        result = spearmanr(instrument[both], truth[both])
        entry["spearman"] = float(result.statistic)
        entry["spearman_p"] = float(result.pvalue)
        entry["pearson"] = float(np.corrcoef(instrument[both],
                                             truth[both])[0, 1])
    else:
        entry["spearman"] = float("nan")
        entry["spearman_p"] = float("nan")
        entry["pearson"] = float("nan")
    for label, values in (("instrument", instrument), ("truth", truth)):
        finite = values[np.isfinite(values)]
        entry[f"{label}_peak_to_peak_dots"] = (
            float(finite.max() - finite.min()) if finite.size else float("nan"))
        entry[f"{label}_std_dots"] = (float(finite.std())
                                      if finite.size else float("nan"))
        entry[f"{label}_period_tiles"] = dominant_period_tiles(values)
        entry[f"{label}_period_mm"] = (
            entry[f"{label}_period_tiles"] * 64 * 2 / 600.0 * 25.4)
    entry["amplitude_ratio"] = (entry["instrument_peak_to_peak_dots"]
                                / entry["truth_peak_to_peak_dots"])
    entry["std_ratio"] = (entry["instrument_std_dots"]
                          / entry["truth_std_dots"])
    entry["period_ratio"] = (entry["instrument_period_tiles"]
                             / entry["truth_period_tiles"])
    return entry


def apply_gate(entry: dict) -> dict:
    spearman = entry.get("spearman", float("nan"))
    period_ratio = entry.get("period_ratio", float("nan"))
    amplitude_ratio = entry.get("amplitude_ratio", float("nan"))
    checks = {
        "spearman": bool(np.isfinite(spearman)
                         and spearman >= GATE["spearman_min"]),
        "period": bool(np.isfinite(period_ratio)
                       and abs(period_ratio - 1.0)
                       <= GATE["period_tolerance"]),
        "amplitude": bool(np.isfinite(amplitude_ratio)
                          and 1.0 / GATE["amplitude_factor"]
                          <= amplitude_ratio <= GATE["amplitude_factor"]),
    }
    return {"gate": GATE, "checks": checks,
            "verdict": "PASS" if all(checks.values()) else "FAIL"}


def load_regmap_gt(directory: Path) -> tuple[list[dict], float]:
    rows = json.loads((directory / "per-column.json").read_text())
    header = json.loads((directory / "plane-offsets.json").read_text())
    return rows, float(header["px_per_dot"])


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def verify_pose_convention(jobs, scan_path: str, count: int) -> dict:
    """Round-trip a sample of committed poses before probing anything.

    The criterion cannot be "argmax exactly at zero": the registration
    error this instrument exists to measure is itself up to ~0.4 cell,
    so the ink-contrast peak legitimately sits at the nearest sampled
    shift.  What a WRONG convention would look like is a peak half a
    cell or a whole cell away, or no separation at all.  So the test is
    (a) the zero-shift contrast at least 3x the one-cell-shifted
    contrast, on EVERY probed plane, and (b) the peak within a quarter
    cell of zero on the PLANE-COMMON planes C and M.

    Why (b) excludes Y: the committed pose is a plane-common lock whose
    only word evidence is W/CM, so C and M are the planes that define
    "the convention holds".  Y's departure from that pose is precisely
    the measurand — sheet I's measured Y excursion reaches 0.42 cell,
    which by construction moves the Y contrast peak to the neighbouring
    sampled shift on the dead-band tiles.  Judging the convention by Y
    would be judging it by the phenomenon.  Y's fraction is reported.
    """
    if not jobs:
        return {"n_tiles": 0}
    step = max(1, len(jobs) // max(1, count))
    checks = [_probe.verify_pose(job, scan_path)
              for job in jobs[::step][:count]]
    checks = [entry for entry in checks if entry is not None]
    summary: dict = {"n_tiles": len(checks), "per_plane": {}, "tiles": checks}
    for name in PLANE_NAMES:
        rows = [entry for entry in checks if name in entry["planes"]]
        if not rows:
            continue
        shifts = np.asarray(rows[0]["shifts_cells"], np.float64)
        zero = int(np.argmin(np.abs(shifts)))
        one_cell = [index for index, shift in enumerate(shifts)
                    if abs(shift) >= 1.0]
        curves = np.asarray([entry["planes"][name]["ink_contrast_by_x_shift"]
                             for entry in rows], np.float64)
        argmaxes = np.asarray([entry["planes"][name]["argmax_shift_cells"]
                               for entry in rows], np.float64)
        pearson = [entry["planes"][name]["luma_vs_any_ink_pearson"]
                   for entry in rows]
        summary["per_plane"][name] = {
            "n": len(rows),
            "median_ink_contrast_at_zero_shift": float(
                np.median(curves[:, zero])),
            "median_ink_contrast_at_one_cell_shift": float(
                np.median(curves[:, one_cell])),
            "fraction_argmax_within_quarter_cell": float(
                np.mean(np.abs(argmaxes) <= 0.25)),
            "median_luma_vs_any_ink_pearson": float(np.median(pearson)),
        }
    separated = all(
        row["median_ink_contrast_at_zero_shift"]
        >= 3.0 * max(row["median_ink_contrast_at_one_cell_shift"], 1e-9)
        for row in summary["per_plane"].values())
    common = [summary["per_plane"][name] for name in ("C", "M")
              if name in summary["per_plane"]]
    peaked = bool(common) and all(
        row["fraction_argmax_within_quarter_cell"] >= 0.9 for row in common)
    summary["criterion"] = {
        "zero_shift_contrast_ge_3x_one_cell_all_planes": bool(separated),
        "peak_within_quarter_cell_on_C_and_M": bool(peaked),
    }
    summary["verdict"] = (
        "page-cell -> native pixel CENTRES confirmed"
        if summary["per_plane"] and separated and peaked
        else "CONVENTION UNCONFIRMED — do not trust the probes")
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="W0/V0: per-plane registration field from certificates")
    parser.add_argument("--state", default=str(_inputs.SHEET_I_STATE))
    parser.add_argument("--capture", type=int, default=1,
                        choices=sorted(_inputs.SHEET_I_SCANS))
    parser.add_argument("--scan", default=None,
                        help="override the scan path for --capture")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None,
                        help="probe only the first N certified tiles")
    parser.add_argument("--bandwidth-tiles", type=float, default=2.0)
    parser.add_argument("--exaggeration", type=float, default=2.5,
                        help="quiver gain, tile widths per print dot")
    parser.add_argument("--figures-only", action="store_true",
                        help="re-render the PNGs from an existing run JSON")
    parser.add_argument("--threshold-dots", type=float, default=0.25,
                        help="dead-band shading threshold in the figure")
    parser.add_argument("--verify-tiles", type=int, default=24,
                        help="pose-convention round-trips before probing")
    parser.add_argument("--tag", default="I")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--out-dir", default=str(_inputs.OUT_DIR))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.figures_only:
        return redraw_from_json(args)
    started = time.time()
    tree_before = _inputs.tree_state()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scan_path = Path(args.scan) if args.scan else _inputs.SHEET_I_SCANS[
        args.capture]
    state_path = Path(args.state)
    print(f"scan  {scan_path}", flush=True)
    scan_sha = _inputs.sha256_file(scan_path)
    recorded = _inputs.recorded_scan_shas()
    recorded_sha = recorded.get(str(scan_path))
    if recorded_sha is not None and recorded_sha != scan_sha:
        raise SystemExit(f"scan sha mismatch vs scan-shas.txt: {scan_sha}")
    print(f"      sha256 {scan_sha} (scan-shas.txt: "
          f"{'match' if recorded_sha else 'not listed'})", flush=True)

    facts = _inputs.read_state_facts(state_path, scan_sha,
                                     use_cache=not args.no_cache)
    print(f"state {state_path}\n      sha256 {facts.state_sha256}\n"
          f"      format {facts.format_row_id} close={facts.close_status} "
          f"capture {facts.capture_index + 1}/{facts.n_captures} "
          f"dpi={facts.capture_dpi:g} shape={facts.capture_shape_yx}",
          flush=True)

    from holo.format.resolve import resolve_format_ref
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec = resolve_format_ref(facts.format_row_id)
    tiles_yx = (spec.layout.cells_yx[0] // 64, spec.layout.cells_yx[1] // 64)
    image_shape = _probe.scan_image(str(scan_path)).shape
    if tuple(image_shape[:2]) != tuple(facts.capture_shape_yx):
        raise SystemExit(
            f"scan shape {image_shape[:2]} != capture record "
            f"{facts.capture_shape_yx}")

    poses, contained, partial = select_poses(facts, tiles_yx)
    jobs, no_pose, plane_certificates, n_addresses = build_jobs(
        facts, spec, poses, args.limit)
    print(f"poses {len(facts.poses)} rows -> {len(poses)} tiles fully "
          f"contained ({partial} partial spans skipped); certified "
          f"addresses {n_addresses}, jobs {len(jobs)}, no-pose {no_pose}",
          flush=True)

    pose_check = verify_pose_convention(jobs, str(scan_path),
                                        args.verify_tiles)
    print(f"pose convention: {pose_check.get('verdict', 'n/a')}", flush=True)
    for name, entry in pose_check.get("per_plane", {}).items():
        print(f"    {name}: ink contrast "
              f"{entry['median_ink_contrast_at_zero_shift']:+.1f} counts at "
              f"zero shift vs "
              f"{entry['median_ink_contrast_at_one_cell_shift']:+.1f} at one "
              f"cell; peak within a quarter cell on "
              f"{entry['fraction_argmax_within_quarter_cell']:.0%} of "
              f"{entry['n']} tiles; luma~ink r="
              f"{entry['median_luma_vs_any_ink_pearson']:+.3f}", flush=True)

    crosstalk = _probe.fit_crosstalk(jobs, str(scan_path))
    print("crosstalk  B_res = B - %.5f*R - %.5f*G" % crosstalk, flush=True)

    probe_started = time.time()
    results = run_probes(jobs, str(scan_path), crosstalk, args.workers)
    probe_seconds = time.time() - probe_started
    rows = probe_rows(results)
    errors: dict[str, int] = {}
    for result in results:
        if "error" in result:
            errors[result["error"]] = errors.get(result["error"], 0) + 1
        for name, values in result.get("planes", {}).items():
            if "error" in values:
                key = f"{name}:{values['error']}"
                errors[key] = errors.get(key, 0) + 1
    counts = {name: sum(1 for row in rows if f"d{name}_x" in row)
              for name in PLANE_NAMES}
    print(f"probes {len(rows)} tiles in {probe_seconds:.0f}s "
          f"(C {counts['C']} / M {counts['M']} / Y {counts['Y']}), "
          f"errors {errors or 'none'}", flush=True)

    columns = per_column(rows, tiles_yx[1])
    smooth = {}
    sample_counts = {}
    for key, (key_x, key_y) in (("C", ("dC_x", "dC_y")),
                                ("M", ("dM_x", "dM_y")),
                                ("Y", ("dY_x", "dY_y")),
                                ("Yrel", ("dY_rel_x", "dY_rel_y"))):
        field, count = smooth_field(rows, tiles_yx, key_x, key_y,
                                    args.bandwidth_tiles)
        smooth[key] = (field[0], field[1])
        sample_counts[key] = count

    truth_rows, truth_px_per_dot = load_regmap_gt(_inputs.REGMAP_GT)
    truth_by_column = {int(row["tx"]): row for row in truth_rows}
    comparison: dict[str, dict] = {}
    for label, key in (("Y_rel_x", "dY_rel_x"), ("CM_diff_x", "dCM_x"),
                       ("Y_rel_y", "dY_rel_y"), ("C_x_raw", "dC_x"),
                       ("M_x_raw", "dM_x"), ("Y_x_raw", "dY_x")):
        instrument = np.array([entry[key] for entry in columns], np.float64)
        truth = np.array(
            [truth_by_column[entry["tile_x"]][key] / truth_px_per_dot
             if entry["tile_x"] in truth_by_column else np.nan
             for entry in columns], np.float64)
        comparison[label] = compare_profiles(instrument, truth)
        comparison[label]["truth_units"] = "scan px / %.0f = print dots" % (
            truth_px_per_dot)
    verdict = apply_gate(comparison["Y_rel_x"])

    tree_after = _inputs.tree_state()
    document = {
        "schema": SCHEMA,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "runtime_seconds": round(time.time() - started, 1),
        "probe_seconds": round(probe_seconds, 1),
        "state_load_seconds": round(facts.load_seconds, 1),
        "void_tree_moved": _inputs.tree_moved(tree_before, tree_after),
        "tree_before": tree_before, "tree_after": tree_after,
        "inputs": {
            "state_path": str(state_path),
            "state_sha256": facts.state_sha256,
            "state_bytes": facts.state_bytes,
            "scan_path": str(scan_path), "scan_sha256": scan_sha,
            "scan_sha_recorded": recorded_sha,
            "scan_shape_yx": [int(v) for v in image_shape[:2]],
            "capture_index": facts.capture_index + 1,
            "n_captures": facts.n_captures,
            "capture_dpi": facts.capture_dpi,
            "format_row_id": facts.format_row_id,
            "receiver_policy_id": facts.receiver_policy_id,
            "close_status": facts.close_status,
            "regmap_gt_dir": str(_inputs.REGMAP_GT),
            "regmap_gt_per_column_sha256": _inputs.sha256_file(
                _inputs.REGMAP_GT / "per-column.json"),
            "regmap_gt_plane_offsets_sha256": _inputs.sha256_file(
                _inputs.REGMAP_GT / "plane-offsets.json"),
            "lanes": [vars_of(lane) for lane in facts.lanes],
        },
        "method": {
            "units": "print dots along PAGE axes (pose Jacobian inverse)",
            "search_dots": _probe.SEARCH_DOTS,
            "highpass_px": _probe.HIGHPASS_PX,
            "model_sigma_px": _probe.MODEL_SIGMA_PX,
            "probe_margin_cells": _probe.PROBE_MARGIN_CELLS,
            "crosstalk_B_minus_aR_bG": list(crosstalk),
            "bandwidth_tiles": args.bandwidth_tiles,
            "cell_dots": int(spec.cell_dots),
            "tiles_yx": list(tiles_yx),
        },
        "counts": {
            "certified_addresses": n_addresses,
            "certificates": len(facts.certificates),
            "plane_certificates": {
                name: plane_certificates[index]
                for index, name in enumerate(PLANE_NAMES)},
            "poses_capture": len(facts.poses),
            "tiles_with_pose": len(poses),
            "partial_spans_skipped": partial,
            "jobs": len(jobs), "probed_tiles": len(rows),
            "probes_per_plane": counts,
            "skipped_no_pose": no_pose,
            "errors": errors,
        },
        "gate": verdict,
        "pose_convention_check": pose_check,
        "comparison": comparison,
        "per_column": columns,
        "smooth_field": {
            key: {"dx_dots": _nan_list(value[0]),
                  "dy_dots": _nan_list(value[1])}
            for key, value in smooth.items()},
        "probes": rows,
    }
    json_path = out_dir / f"field-from-certs-{args.tag}.json"
    json_path.write_text(json.dumps(document, indent=1, allow_nan=True))

    field_png, comparison_png = draw_outputs(
        out_dir, args.tag, tiles_yx=tiles_yx, smooth=smooth,
        sample_counts=sample_counts, columns=columns,
        truth_by_column=truth_by_column, truth_px_per_dot=truth_px_per_dot,
        comparison=comparison, verdict=verdict, probed_tiles=len(rows),
        format_row_id=facts.format_row_id,
        capture_index=facts.capture_index, exaggeration=args.exaggeration,
        threshold_dots=args.threshold_dots)

    print("\n== V0 gate (Y plane, dY_rel_x per column) ==")
    entry = comparison["Y_rel_x"]
    print(f"  spearman   {entry['spearman']:+.3f} (>= {GATE['spearman_min']})"
          f"  p={entry['spearman_p']:.2g}  n={entry['n_columns']}")
    print(f"  period     {entry['instrument_period_mm']:.1f} mm vs GT "
          f"{entry['truth_period_mm']:.1f} mm  ratio "
          f"{entry['period_ratio']:.3f} (+/-{GATE['period_tolerance']:.0%})")
    print(f"  amplitude  {entry['instrument_peak_to_peak_dots']:.3f} dot pp "
          f"vs GT {entry['truth_peak_to_peak_dots']:.3f} dot pp  ratio "
          f"{entry['amplitude_ratio']:.3f} (factor "
          f"{GATE['amplitude_factor']:g})")
    print(f"  VERDICT    {verdict['verdict']}  {verdict['checks']}")
    print("\n== controls ==")
    for label in ("CM_diff_x", "Y_rel_y", "C_x_raw", "M_x_raw", "Y_x_raw"):
        entry = comparison[label]
        print(f"  {label:10s} spearman {entry['spearman']:+.3f}  amp ratio "
              f"{entry['amplitude_ratio']:.2f}  instrument pp "
              f"{entry['instrument_peak_to_peak_dots']:.3f} dot  GT pp "
              f"{entry['truth_peak_to_peak_dots']:.3f} dot")
    if document["void_tree_moved"]:
        print("\nWARNING: src/holo moved during the run — this result is VOID")
    print(f"\nwrote {json_path}\n      {field_png}\n      {comparison_png}")
    print(f"runtime {document['runtime_seconds']:.0f} s")
    return 0


def draw_outputs(out_dir: Path, tag: str, *, tiles_yx, smooth, sample_counts,
                 columns, truth_by_column, truth_px_per_dot, comparison,
                 verdict, probed_tiles: int, format_row_id: str,
                 capture_index: int, exaggeration: float,
                 threshold_dots: float) -> tuple[Path, Path]:
    """Render both artifacts; shared by a full run and ``--figures-only``."""
    entry = comparison["Y_rel_x"]
    field_png = out_dir / f"plane-fields-{tag}.png"
    _figures.draw_field(
        field_png, sample_counts, smooth, tiles_yx,
        exaggeration=exaggeration, threshold_dots=threshold_dots,
        title=(f"sheet {tag}: per-plane translation-delta field from "
               f"{probed_tiles} certified tiles ({format_row_id}, capture "
               f"{capture_index + 1})"))
    comparison_png = out_dir / f"comparison-{tag}.png"
    axis = [row["tile_x"] for row in columns]
    _figures.draw_comparison(
        comparison_png, axis,
        np.array([row["dY_rel_x"] for row in columns], np.float64),
        np.array([row["dY_rel_x_mad"] for row in columns], np.float64),
        np.array([truth_by_column[tile_x]["dY_rel_x"] / truth_px_per_dot
                  if tile_x in truth_by_column else np.nan
                  for tile_x in axis], np.float64),
        [RESIDUE[tile_x] if tile_x < len(RESIDUE) else 0 for tile_x in axis],
        title=(f"V0: per-column Y x-offset  dY - (C+M)/2  ==  "
               f"{verdict['verdict']}  (Spearman {entry['spearman']:+.3f}, "
               f"amplitude x{entry['amplitude_ratio']:.2f}, period "
               f"{entry['instrument_period_mm']:.0f} mm vs "
               f"{entry['truth_period_mm']:.0f} mm)"),
        subtitle=("instrument = certificates + committed poses (no page GT, "
                  "no global affine); truth = regmap-gt supervised"))
    return field_png, comparison_png


def redraw_from_json(args) -> int:
    """Re-render both PNGs from a finished run — no state, no probing.

    The measurement is expensive and deterministic, so illustration
    choices (quiver gain, threshold shading) are re-editable without
    touching the archived inputs.  Nothing here can change a number.
    """
    out_dir = Path(args.out_dir)
    json_path = out_dir / f"field-from-certs-{args.tag}.json"
    document = json.loads(json_path.read_text())
    tiles_yx = tuple(document["method"]["tiles_yx"])
    smooth = {}
    for key, value in document["smooth_field"].items():
        smooth[key] = tuple(
            np.array([[np.nan if cell is None else float(cell)
                       for cell in row] for row in value[axis]], np.float64)
            for axis in ("dx_dots", "dy_dots"))
    sample_counts = {}
    for key, probe_key in (("C", "dC_x"), ("M", "dM_x"), ("Y", "dY_x"),
                           ("Yrel", "dY_rel_x")):
        counts = np.zeros(tiles_yx)
        for row in document["probes"]:
            if probe_key in row:
                counts[row["tile_y"], row["tile_x"]] += 1
        sample_counts[key] = counts
    truth_rows, truth_px_per_dot = load_regmap_gt(_inputs.REGMAP_GT)
    field_png, comparison_png = draw_outputs(
        out_dir, args.tag, tiles_yx=tiles_yx, smooth=smooth,
        sample_counts=sample_counts, columns=document["per_column"],
        truth_by_column={int(row["tx"]): row for row in truth_rows},
        truth_px_per_dot=truth_px_per_dot,
        comparison=document["comparison"], verdict=document["gate"],
        probed_tiles=int(document["counts"]["probed_tiles"]),
        format_row_id=document["inputs"]["format_row_id"],
        capture_index=int(document["inputs"]["capture_index"]) - 1,
        exaggeration=args.exaggeration, threshold_dots=args.threshold_dots)
    print(f"redrew from {json_path}\n      {field_png}\n      "
          f"{comparison_png}")
    return 0


def vars_of(lane) -> dict:
    return {"lane_id": lane.lane_id, "ordinal": lane.ordinal,
            "target_ppc": lane.target_ppc, "kind": lane.kind,
            "native_per_view": lane.native_per_view}


def _nan_list(field: np.ndarray) -> list:
    return [[None if not np.isfinite(value) else round(float(value), 5)
             for value in row] for row in field]


if __name__ == "__main__":
    raise SystemExit(main())
