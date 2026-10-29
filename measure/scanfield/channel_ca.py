"""Is scanner per-channel geometry worth compensating for a colour decode?

One number decides it.  ``src/holo/receiver/plugins/fields.py`` will not publish a
per-plane registration field whose delta is under ``MIN_DELTA_DOTS =
0.25`` printed dots, because below that the read side is better off
keeping its standing correction.  A scanner-channel field would ride the
same read-side seam and is subject to the same floor, so:

    across the platen, how far apart do R, G and B put the same physical
    mark, in 600-dpi printed dots, and does that reach 0.25 dots
    anywhere a payload region sits (x 4-206 mm, y 4-293 mm)?

Pre-registered verdict rule, fixed before any capture was read:

* **USEFUL** iff some channel pair and axis reaches |offset| >= 0.25
  dots somewhere in the payload band, AND that offset reproduces across
  two captures on the same scanner (per-target |difference| median at
  most half the magnitude claimed).  A scanner field that does not
  reproduce is not a scanner field.
* **NOT USEFUL** otherwise, and a measured negative closes the line.

Reported alongside, because it is the number a FIELD would actually be
worth: the same statistic after removing the platen-wide mean.  A
constant per-channel offset is already absorbed by the per-plane pose
and by the plane field's own constant term, so only the varying part is
new information.

Arms
----
``--selftest``  synthetic marks with injected sub-pixel channel shifts;
                calibrates the centroid estimator against truth.
``--marks``     43 small K marks per discovery capture, x 4-206 mm.
``--edges``     every side of seven K rectangles, polarity-split, so
                displacement and PSF skew are separated.
``--margin``    the confetti-field boundary of sheet I's three 2400-dpi
                captures — a payload sheet at payload dpi, an UPPER
                BOUND only (see ``_margin``).
``--all``       all four, then the verdict.

Read-only on every capture.  No scan, no print, no decode.

    cd <repo>
    PYTHONPATH=measure env/bin/python -m scanfield.channel_ca --all \\
        --evidence-root <evidence> --out build/scanfield

Historical record (2026-09); the discovery and sheet-I captures (paths
relative to ``--evidence-root``) are in the evidence archive.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import _evidence
from scanner._edge import UM_PER_INCH, analyze_edge, compare_channels
from scanner._sheet import Sheet
from scanner.ink_psf import SHEETS

from . import _margin, _targets
from ._figure import draw_offset_map
from ._marks import mark_offsets, selftest

PRINT_DPI = 600.0
FLOOR_DOTS = 0.25                 # src/holo/receiver/plugins/fields.py MIN_DELTA_DOTS
C2_CELL_DOTS = 2.0
PAYLOAD_X_MM = (4.0, 206.0)
PAYLOAD_Y_MM = (4.0, 293.0)
CHANNELS = ("R", "B")             # differentials, always against G
COLOUR_SHEETS = ("e031-color", "e028-color")

MARGIN_CAPTURES: tuple[_margin.MarginCapture, ...] = tuple(
    _margin.MarginCapture(
        key=f"sheetI-2400-{suffix or 'a'}",
        path=Path("paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/"
                  f"I/captures/I-canon-2400rgb{suffix}.tiff"),
        scan_dpi=2400.0,
        record="experiments/033 sheet I (c2-cmy8-r0700, VERIFIED)")
    for suffix in ("", "-displaced", "-displaced2"))


def _mm(value_px: float, scan_dpi: float) -> float:
    return value_px * UM_PER_INCH / scan_dpi / 1000.0


def _in_payload(x_mm: float, y_mm: float) -> bool:
    return (PAYLOAD_X_MM[0] <= x_mm <= PAYLOAD_X_MM[1]
            and PAYLOAD_Y_MM[0] <= y_mm <= PAYLOAD_Y_MM[1])


# --- arms -----------------------------------------------------------------

def marks_arm(keys: Sequence[str], tone: str | None, evidence_root: Path,
              verbose: bool = True) -> list[dict[str, Any]]:
    specs = _targets.mark_specs()
    rows: list[dict[str, Any]] = []
    for key in keys:
        sheet = Sheet(SHEETS[key].under(evidence_root))
        dpi = sheet.spec.scan_dpi
        kept = 0
        with sheet:
            for spec, cx, cy, patch in _targets.mark_patches(sheet, specs):
                result = mark_offsets(patch, scan_dpi=dpi, tone=tone)
                if not result.ok:
                    continue
                kept += 1
                rows.append({
                    "capture": key, "arm": "marks",
                    "target": spec.name, "family": spec.family,
                    "x_mm": _mm(cx, dpi), "y_mm": _mm(cy, dpi),
                    "support_px": result.support_px,
                    "contrast_G": result.contrast.get("G"),
                    "excluded_fraction": result.excluded_fraction,
                    "dx_dots": {c: result.offsets_dots[c]["dx_dots"]
                                for c in CHANNELS},
                    "dy_dots": {c: result.offsets_dots[c]["dy_dots"]
                                for c in CHANNELS},
                })
        if verbose:
            print(f"  marks  {key}: {kept}/{len(specs)} marks read",
                  file=sys.stderr)
    return rows


def edges_arm(keys: Sequence[str], tone: str | None, evidence_root: Path,
              verbose: bool = True) -> list[dict[str, Any]]:
    specs = _targets.edge_specs()
    rows: list[dict[str, Any]] = []
    for key in keys:
        sheet = Sheet(SHEETS[key].under(evidence_root))
        dpi = sheet.spec.scan_dpi
        halfwidth = 40.0 * dpi / 4800.0
        kept = 0
        with sheet:
            for item in _targets.edge_patches(sheet, specs):
                result = analyze_edge(
                    item.patch, scan_dpi=dpi, orientation=item.orientation,
                    lsf_halfwidth_px=halfwidth,
                    centroid_window_px=max(6, int(round(halfwidth / 2))),
                    linearize=tone != "none")
                if "G" not in result.channels:
                    continue
                differentials = compare_channels(result, scan_dpi=dpi)
                if not differentials:
                    continue
                kept += 1
                rows.append({
                    "capture": key, "arm": "edges",
                    "target": item.target, "family": item.family,
                    "side": item.side, "axis": item.axis,
                    "polarity": item.polarity, "segment": item.segment,
                    "x_mm": _mm(item.x_px, dpi), "y_mm": _mm(item.y_px, dpi),
                    "contrast_G": result.channels["G"].contrast,
                    "angle_deg": result.angle_deg,
                    "shift_dots": {c: differentials[c]["shift_dots"]
                                   for c in CHANNELS if c in differentials},
                })
        if verbose:
            print(f"  edges  {key}: {kept} edge segments read",
                  file=sys.stderr)
    return rows


def _polarity_pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold each rectangle's two polarities into displacement + skew.

    A real lateral displacement moves a paper->ink and an ink->paper edge
    the SAME way; a channel-dependent PSF asymmetry moves them
    oppositely.  The mean is therefore the registration number and the
    half-difference is the skew — the term a centroid cannot separate,
    which is why this arm exists next to ``marks``.
    """
    grouped: dict[tuple, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = (row["capture"], row["target"], row["axis"], row["segment"])
        grouped[key][row["polarity"]] = row
    out: list[dict[str, Any]] = []
    for (capture, target, axis, segment), pair in sorted(
            grouped.items(), key=lambda item: str(item[0])):
        if len(pair) != 2:
            continue
        falling, rising = pair["falling"], pair["rising"]
        entry: dict[str, Any] = {
            "capture": capture, "arm": "edges-paired", "target": target,
            "axis": axis, "segment": segment, "family": falling["family"],
            "x_mm": 0.5 * (falling["x_mm"] + rising["x_mm"]),
            "y_mm": 0.5 * (falling["y_mm"] + rising["y_mm"]),
            "displacement_dots": {}, "skew_dots": {},
        }
        for channel in CHANNELS:
            a = falling["shift_dots"].get(channel)
            b = rising["shift_dots"].get(channel)
            if a is None or b is None:
                continue
            entry["displacement_dots"][channel] = 0.5 * (a + b)
            entry["skew_dots"][channel] = 0.5 * (a - b)
        if entry["displacement_dots"]:
            out.append(entry)
    return out


def margin_arm(tone: str | None, segments: int, evidence_root: Path,
               verbose: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for declared in MARGIN_CAPTURES:
        capture = replace(declared, path=evidence_root / declared.path)
        if not capture.path.exists():
            if verbose:
                print(f"  margin {capture.key}: MISSING {capture.path}",
                      file=sys.stderr)
            continue
        found = _margin.boundary_rows(capture, segments=segments, tone=tone)
        for row in found:
            row["arm"] = "margin"
            row["family"] = f"field-boundary-{row['side']}"
        rows += found
        if verbose:
            print(f"  margin {capture.key}: {len(found)} segments",
                  file=sys.stderr)
    return rows


# --- aggregation ----------------------------------------------------------

def _series(rows: list[dict[str, Any]], axis: str, channel: str
            ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(x_mm, y_mm, offset_dots) for one axis and channel, payload band."""
    xs, ys, values = [], [], []
    for row in rows:
        if not _in_payload(row["x_mm"], row["y_mm"]):
            continue
        if row["arm"] == "marks":
            value = row["dx_dots" if axis == "x" else "dy_dots"].get(channel)
        elif row["arm"] == "edges-paired":
            if row["axis"] != axis:
                continue
            value = row["displacement_dots"].get(channel)
        elif row["arm"] == "margin":
            if row["axis"] != axis:
                continue
            value = row["shift_dots"].get(channel)
        else:
            continue
        if value is None or not math.isfinite(value):
            continue
        xs.append(row["x_mm"])
        ys.append(row["y_mm"])
        values.append(value)
    return np.asarray(xs), np.asarray(ys), np.asarray(values)


def platen_model(x_mm: np.ndarray, values: np.ndarray) -> dict[str, Any]:
    """Quadratic in platen x, and what it predicts across the payload band.

    Lateral chromatic aberration from a lens is odd-symmetric about the
    optical axis, so the LINEAR coefficient is the term with a physical
    story; the quadratic is carried to keep an even component from
    hiding inside the residual.
    """
    if x_mm.size < 6:
        return {"n": int(x_mm.size), "fitted": False}
    centre = 0.5 * (PAYLOAD_X_MM[0] + PAYLOAD_X_MM[1])
    scale = 0.5 * (PAYLOAD_X_MM[1] - PAYLOAD_X_MM[0])
    u = (x_mm - centre) / scale
    design = np.column_stack([np.ones_like(u), u, u * u])
    solution, *_ = np.linalg.lstsq(design, values, rcond=None)
    predicted = design @ solution
    residual = values - predicted
    # Evaluate the model only where it was SAMPLED.  Extrapolating a
    # quadratic from a 70 mm span out to the whole 202 mm payload band
    # invents a range the data never saw.
    grid = (np.linspace(float(x_mm.min()), float(x_mm.max()), 64)
            - centre) / scale
    curve = np.column_stack([np.ones_like(grid), grid, grid * grid]) @ solution
    return {
        "n": int(x_mm.size), "fitted": True,
        "model_x_mm": [float(x_mm.min()), float(x_mm.max())],
        "constant_dots": float(solution[0]),
        "linear_dots_per_half_platen": float(solution[1]),
        "quadratic_dots": float(solution[2]),
        "residual_rms_dots": float(np.sqrt(np.mean(residual ** 2))),
        "model_min_dots": float(curve.min()),
        "model_max_dots": float(curve.max()),
        "model_range_dots": float(curve.max() - curve.min()),
    }


def summarize(rows: list[dict[str, Any]], arms: Sequence[str]
              ) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arm in arms:
        subset = [row for row in rows if row["arm"] == arm]
        for axis in ("x", "y"):
            for channel in CHANNELS:
                xs, ys, values = _series(subset, axis, channel)
                if not values.size:
                    continue
                centred = values - values.mean()
                out[f"{arm}/{axis}/{channel}-G"] = {
                    "n": int(values.size),
                    "x_mm_span": [float(xs.min()), float(xs.max())],
                    "mean_dots": float(values.mean()),
                    "median_dots": float(np.median(values)),
                    "std_dots": float(values.std(ddof=1))
                    if values.size > 1 else 0.0,
                    "max_abs_dots": float(np.abs(values).max()),
                    "max_abs_demeaned_dots": float(np.abs(centred).max()),
                    "p95_abs_dots": float(np.percentile(np.abs(values), 95)),
                    "fraction_over_floor": float(
                        np.mean(np.abs(values) >= FLOOR_DOTS)),
                    "cells_c2": float(np.abs(values).max() / C2_CELL_DOTS),
                    "platen_model": platen_model(xs, values),
                }
        if arm == "edges-paired":
            for axis in ("x", "y"):
                for channel in CHANNELS:
                    skew = np.asarray([
                        row["skew_dots"][channel] for row in subset
                        if row["axis"] == axis and channel in row["skew_dots"]
                        and math.isfinite(row["skew_dots"][channel])])
                    if not skew.size:
                        continue
                    out[f"skew/{axis}/{channel}-G"] = {
                        "n": int(skew.size),
                        "mean_dots": float(skew.mean()),
                        "max_abs_dots": float(np.abs(skew).max()),
                        "note": "half-difference of the two polarities = "
                                "channel PSF asymmetry, NOT a displacement",
                    }
    return out


LEFT_BAND_MM = (4.0, 60.0)
RIGHT_BAND_MM = (150.0, 206.0)


def antisymmetry(rows: list[dict[str, Any]], arms: Sequence[str]
                 ) -> dict[str, Any]:
    """Right platen band minus left platen band, per arm and channel.

    Lateral chromatic aberration is ODD-SYMMETRIC about the lens axis:
    if the scanner has any, the two ends of the platen carry it with
    opposite sign and this difference is where it shows.  e033 recorded
    exactly that shape for the Canon's R-G, and the payload sheet's
    field boundary shows it too (blue -0.12 dots at x 5 mm, +0.19 at
    x 205 mm).  The discriminator is that the ``marks`` and
    ``edges-paired`` arms CANCEL everything print-side by construction
    and the ``margin`` arm does not: a shape that appears only in the
    margin arm is the printer's per-plane magnification, not the
    scanner's optics.
    """
    out: dict[str, Any] = {}
    for arm in arms:
        subset = [row for row in rows if row["arm"] == arm]
        for axis in ("x", "y"):
            for channel in CHANNELS:
                xs, _, values = _series(subset, axis, channel)
                if not values.size:
                    continue
                left = values[(xs >= LEFT_BAND_MM[0])
                              & (xs <= LEFT_BAND_MM[1])]
                right = values[(xs >= RIGHT_BAND_MM[0])
                               & (xs <= RIGHT_BAND_MM[1])]
                if left.size < 2 or right.size < 2:
                    continue
                spread = math.sqrt(left.var(ddof=1) / left.size
                                   + right.var(ddof=1) / right.size)
                difference = float(right.mean() - left.mean())
                out[f"{arm}/{axis}/{channel}-G"] = {
                    "n_left": int(left.size), "n_right": int(right.size),
                    "left_mean_dots": float(left.mean()),
                    "right_mean_dots": float(right.mean()),
                    "right_minus_left_dots": difference,
                    "standard_error_dots": spread,
                    "significant": bool(abs(difference) > 3.0 * spread),
                }
    return out


def reproducibility(rows: list[dict[str, Any]], arm: str,
                    keys: Sequence[str]) -> dict[str, Any]:
    """Paired per-target agreement between two captures of one scanner."""
    if len(keys) != 2:
        return {}
    index: dict[tuple, dict[str, float]] = defaultdict(dict)
    for row in rows:
        if row["arm"] != arm or row["capture"] not in keys:
            continue
        if not _in_payload(row["x_mm"], row["y_mm"]):
            continue
        for axis in ("x", "y"):
            if arm == "marks":
                values = row["dx_dots" if axis == "x" else "dy_dots"]
            elif arm == "edges-paired":
                if row["axis"] != axis:
                    continue
                values = row["displacement_dots"]
            else:
                continue
            for channel in CHANNELS:
                value = values.get(channel)
                if value is None or not math.isfinite(value):
                    continue
                identity = (row["target"], row.get("segment", 0), axis,
                            channel)
                index[identity][row["capture"]] = value
    out: dict[str, Any] = {}
    buckets: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for (target, segment, axis, channel), pair in index.items():
        if len(pair) != 2:
            continue
        buckets[(axis, channel)].append((pair[keys[0]], pair[keys[1]]))
    for (axis, channel), pairs in sorted(buckets.items()):
        first = np.asarray([p[0] for p in pairs])
        second = np.asarray([p[1] for p in pairs])
        difference = second - first
        correlation = (float(np.corrcoef(first, second)[0, 1])
                       if first.size > 2 and first.std() > 0
                       and second.std() > 0 else float("nan"))
        out[f"{axis}/{channel}-G"] = {
            "n_paired": int(first.size),
            "mean_a_dots": float(first.mean()),
            "mean_b_dots": float(second.mean()),
            "median_abs_difference_dots": float(np.median(np.abs(difference))),
            "max_abs_difference_dots": float(np.abs(difference).max()),
            "pearson_r": correlation,
        }
    return out


def verdict(summary: dict[str, Any], repro: dict[str, Any]) -> dict[str, Any]:
    """The pre-registered decision, evaluated on the primary arms."""
    primary = [key for key in summary
               if key.startswith(("marks/", "edges-paired/"))]
    worst_raw = {"key": None, "value": 0.0}
    worst_field = {"key": None, "value": 0.0}
    for key in primary:
        entry = summary[key]
        if entry["max_abs_dots"] > worst_raw["value"]:
            worst_raw = {"key": key, "value": entry["max_abs_dots"]}
        if entry["max_abs_demeaned_dots"] > worst_field["value"]:
            worst_field = {"key": key,
                           "value": entry["max_abs_demeaned_dots"]}
    reproduces = True
    for key, entry in repro.items():
        if entry["median_abs_difference_dots"] > 0.5 * FLOOR_DOTS:
            reproduces = False
    over_floor = worst_raw["value"] >= FLOOR_DOTS
    return {
        "floor_dots": FLOOR_DOTS,
        "floor_source": "src/holo/receiver/plugins/fields.py MIN_DELTA_DOTS",
        "payload_band_x_mm": list(PAYLOAD_X_MM),
        "payload_band_y_mm": list(PAYLOAD_Y_MM),
        "worst_raw_offset": worst_raw,
        "worst_field_offset": worst_field,
        "raw_over_floor": bool(over_floor),
        "field_over_floor": bool(worst_field["value"] >= FLOOR_DOTS),
        "cross_capture_agrees_within_half_floor": bool(reproduces),
        # Both legs, as pre-registered: an offset that clears the floor
        # but does not reproduce across two captures of one scanner is
        # not a scanner field, it is noise with a large maximum.
        "verdict": "USEFUL" if (over_floor and reproduces) else "NOT USEFUL",
        "headroom_factor": (FLOOR_DOTS / worst_raw["value"]
                            if worst_raw["value"] > 0 else float("inf")),
    }


# --- driver ---------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scanfield.channel_ca", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--marks", action="store_true")
    parser.add_argument("--edges", action="store_true")
    parser.add_argument("--margin", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--tone", choices=("srgb", "gamma22", "none"),
                        default="srgb",
                        help="capture transfer function to invert — the "
                             "robustness control")
    parser.add_argument("--margin-segments", type=int, default=10)
    parser.add_argument("--no-figure", dest="figure", action="store_false",
                        help="skip the PNG offset map")
    parser.add_argument("--sheets", nargs="+", default=list(COLOUR_SHEETS))
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.all:
        args.selftest = args.marks = args.edges = args.margin = True
    if not (args.selftest or args.marks or args.edges or args.margin):
        parser.error("choose an arm (or --all)")
    if args.marks or args.edges or args.margin:
        args.evidence_root = _evidence.resolve(args.evidence_root,
                                               tool="channel_ca")
    if args.marks or args.edges:
        _evidence.need(*(path for key in args.sheets if key in SHEETS
                         for spec in (SHEETS[key].under(args.evidence_root),)
                         for path in (spec.capture, spec.report,
                                      spec.manifest)), tool="channel_ca")
    root = args.evidence_root or Path()

    report: dict[str, Any] = {
        "instrument": "measure/scanfield/channel_ca",
        "purpose": "does scanner per-channel geometry clear the 0.25-dot "
                   "publish floor anywhere a payload region sits?",
        "scanner": "Canon LiDE 400 (scanner of record)",
        "generated_unix": int(time.time()),
        "tone_curve": args.tone,
        "floor_dots": FLOOR_DOTS,
        "sheets": {key: {
            "capture": str(root / SHEETS[key].capture),
            "sha256": SHEETS[key].sha256,
            "engine": SHEETS[key].engine_label,
            "scan_dpi": SHEETS[key].scan_dpi,
            "record": SHEETS[key].record,
        } for key in args.sheets},
    }
    rows: list[dict[str, Any]] = []
    arms: list[str] = []

    if args.selftest:
        report["selftest"] = selftest(tone=args.tone)
        worst = max(abs(case["error_dx_dots"])
                    for case in report["selftest"])
        report["selftest_worst_error_dots"] = worst
        print(f"  selftest: worst |error| {worst:.5f} dots", file=sys.stderr)
    if args.marks:
        rows += marks_arm(args.sheets, args.tone, args.evidence_root)
        arms.append("marks")
    if args.edges:
        edge_rows = edges_arm(args.sheets, args.tone, args.evidence_root)
        paired = _polarity_pairs(edge_rows)
        rows += edge_rows + paired
        arms += ["edges", "edges-paired"]
    if args.margin:
        rows += margin_arm(args.tone, args.margin_segments, args.evidence_root)
        arms.append("margin")

    report["rows"] = rows
    report["summary"] = summarize(rows, arms)
    report["antisymmetry"] = antisymmetry(rows, arms)
    if args.marks:
        report["reproducibility_marks"] = reproducibility(
            rows, "marks", args.sheets)
    if args.edges:
        report["reproducibility_edges"] = reproducibility(
            rows, "edges-paired", args.sheets)
    repro = dict(report.get("reproducibility_marks", {}))
    repro.update(report.get("reproducibility_edges", {}))
    if args.marks or args.edges:
        report["verdict"] = verdict(report["summary"], repro)

    args.out.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.tone == "srgb" else f"-{args.tone}"
    path = args.out / f"channel-ca{suffix}.json"
    path.write_text(json.dumps(report, indent=1, sort_keys=False,
                               allow_nan=True))
    print(f"wrote {path}", file=sys.stderr)
    if args.figure and (args.marks or args.edges or args.margin):
        figure = args.out / f"channel-ca{suffix}.png"
        draw_offset_map(figure, report)
        print(f"wrote {figure}", file=sys.stderr)
    _print_tables(report)
    return 0


def _print_tables(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    if summary:
        print(f"\n{'arm/axis/pair':<26}{'n':>5}{'mean':>9}{'max|.|':>9}"
              f"{'max|.-mean|':>13}{'range(fit)':>12}{'x span mm':>18}")
        for key in sorted(summary):
            entry = summary[key]
            if key.startswith("skew/"):
                continue
            model = entry["platen_model"]
            span = entry["x_mm_span"]
            print(f"{key:<26}{entry['n']:>5}{entry['mean_dots']:>9.4f}"
                  f"{entry['max_abs_dots']:>9.4f}"
                  f"{entry['max_abs_demeaned_dots']:>13.4f}"
                  f"{model.get('model_range_dots', float('nan')):>12.4f}"
                  f"{span[0]:>9.1f}{span[1]:>9.1f}")
        skews = [key for key in sorted(summary) if key.startswith("skew/")]
        if skews:
            print(f"\n{'PSF skew (not displacement)':<26}{'n':>5}"
                  f"{'mean':>9}{'max|.|':>9}")
            for key in skews:
                entry = summary[key]
                print(f"{key:<26}{entry['n']:>5}{entry['mean_dots']:>9.4f}"
                      f"{entry['max_abs_dots']:>9.4f}")
    skewed = report.get("antisymmetry")
    if skewed:
        print(f"\nplaten antisymmetry (right band - left band)\n"
              f"{'  arm/axis/pair':<28}{'nL':>4}{'nR':>4}{'left':>9}"
              f"{'right':>9}{'R-L':>9}{'s.e.':>9}{'3-sigma?':>10}")
        for key in sorted(skewed):
            entry = skewed[key]
            print(f"  {key:<26}{entry['n_left']:>4}{entry['n_right']:>4}"
                  f"{entry['left_mean_dots']:>9.4f}"
                  f"{entry['right_mean_dots']:>9.4f}"
                  f"{entry['right_minus_left_dots']:>9.4f}"
                  f"{entry['standard_error_dots']:>9.4f}"
                  f"{str(entry['significant']):>10}")
    for name in ("reproducibility_marks", "reproducibility_edges"):
        block = report.get(name)
        if not block:
            continue
        print(f"\n{name}\n{'  axis/pair':<16}{'n':>5}{'mean A':>10}"
              f"{'mean B':>10}{'med|A-B|':>11}{'max|A-B|':>11}{'r':>8}")
        for key in sorted(block):
            entry = block[key]
            print(f"  {key:<14}{entry['n_paired']:>5}"
                  f"{entry['mean_a_dots']:>10.4f}{entry['mean_b_dots']:>10.4f}"
                  f"{entry['median_abs_difference_dots']:>11.4f}"
                  f"{entry['max_abs_difference_dots']:>11.4f}"
                  f"{entry['pearson_r']:>8.3f}")
    final = report.get("verdict")
    if final:
        print(f"\nVERDICT: {final['verdict']}  "
              f"(worst raw {final['worst_raw_offset']['value']:.4f} dots at "
              f"{final['worst_raw_offset']['key']}, floor "
              f"{final['floor_dots']}, headroom "
              f"{final['headroom_factor']:.1f}x)")


if __name__ == "__main__":
    raise SystemExit(main())
