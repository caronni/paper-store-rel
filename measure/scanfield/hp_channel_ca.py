"""The same question as ``channel_ca``, asked of the home/HP flatbed.

``channel_ca`` asked whether the Canon LiDE 400's per-channel geometry
reaches the plane-field service's 0.25-dot publish floor, and answered
NOT USEFUL by a factor of 2.8.  This module asks it of the OTHER scanner
in the corpus — the M281fdw MFP's own flatbed, "home flatbed 1200", the
scanner every experiment before 012.3 used.

The floor, the pre-registered rule and the estimator are the same by
import, not by restatement:

* **USEFUL** iff some channel pair and axis reaches |offset| >= 0.25 dots
  somewhere in the payload band, AND that offset reproduces across two
  captures on the same scanner.
* **NOT USEFUL** otherwise.

with the field number reported alongside — the same statistic after the
platen-wide mean is removed, because a constant per-channel offset is
already absorbed by the per-plane pose and by the plane field's own
constant term, and only the varying part is information a FIELD could
carry.  On this scanner that distinction stops being bookkeeping and
becomes the whole answer.

Three things differ from the Canon instrument, all forced by the corpus
rather than chosen:

**Targets are found, not looked up** (``hp_targets``).  This scanner's
colour captures are all from 2026-07-04..06, weeks before the HCAL
discovery page and the ``Sheet`` machinery that locates targets on it.

**Reproducibility is tested on the platen profile, not per target.**
``channel_ca`` paired targets by name across two captures of one page.
Here the five primary captures are the same sheet at four DIFFERENT
placements — flat, displaced, rotated 90 degrees, rotated 180 degrees —
so there is no shared target name, and building a correspondence would
mean registering the point clouds and trusting that registration inside
the very measurement it serves.  It is also the wrong test: a scanner
field is a function of PLATEN position, so what has to reproduce is the
offset-versus-platen-x profile, and that is what is compared.

**Those rotations are an arm, not a nuisance.**  ``channel_ca`` recorded
as a caveat that its two captures sat within 0.5 mm of the same platen
translation, so it could not separate "locked to the platen" from
"locked to the page".  Here the same physical sheet was scanned at 0, 90
and 180 degrees.  A page-locked effect — printer per-plane registration,
or anything else print-side — must rotate with the page: at 180 degrees
its sign flips in platen coordinates, and at 90 degrees its two axes
exchange.  A platen-locked effect does neither.  The corpus that was
never meant for this question happens to answer it exactly.

    cd <repo>
    PYTHONPATH=measure env/bin/python -m scanfield.hp_channel_ca --all \\
        --evidence-root <evidence> --out build/scanfield
"""
from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import _evidence

from . import hp_comb, hp_inventory, hp_targets
from ._marks import mark_offsets, selftest
from .channel_ca import (C2_CELL_DOTS, CHANNELS, FLOOR_DOTS, PAYLOAD_X_MM,
                         PAYLOAD_Y_MM, PRINT_DPI, _in_payload,
                         antisymmetry, platen_model, verdict)

SCAN_DPI = 1200.0
BIN_MM = 12.0                     # platen-x bin for the profile comparison
MIN_BIN_COUNT = 3


def _series(rows: list[dict[str, Any]], axis: str, channel: str
            ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(x_mm, y_mm, offset_dots) for one axis and channel, payload band.

    ``channel_ca._series`` knows the arms of ITS instrument; this one
    carries the two polarities of this one.  The payload-band gate and
    the units are the same by import.
    """
    xs, ys, values = [], [], []
    for row in rows:
        if row["arm"] not in ("marks", "holes"):
            continue
        if not _in_payload(row["x_mm"], row["y_mm"]):
            continue
        value = row["dx_dots" if axis == "x" else "dy_dots"].get(channel)
        if value is None or not math.isfinite(value):
            continue
        xs.append(row["x_mm"])
        ys.append(row["y_mm"])
        values.append(value)
    return np.asarray(xs), np.asarray(ys), np.asarray(values)


# --- arms -----------------------------------------------------------------

def marks_arm(captures: Sequence[hp_inventory.Capture], tone: str,
              polarities: Sequence[str] = ("dark",),
              want_comb: bool = False, verbose: bool = True
              ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every isolated achromatic mark on every capture, one at a time.

    One capture is resident at a time and dropped before the next: at
    557 MB decoded, holding the primary five would be 2.8 GB for no
    reason.  The decimated search image is computed once per capture and
    shared by every polarity and by the comb spectra.
    """
    rows: list[dict[str, Any]] = []
    census: dict[str, Any] = {}
    for capture in captures:
        started = time.time()
        rgb = hp_targets.load_rgb(str(capture.path))
        small = hp_targets.decimate_mean(
            rgb.mean(axis=2, dtype=np.float32), hp_targets.DECIMATE)
        entry: dict[str, Any] = {"scan_dpi": capture.scan_dpi}
        for polarity in polarities:
            candidates, found = hp_targets.find_candidates(
                rgb, scan_dpi=capture.scan_dpi, polarity=polarity,
                small=small)
            kept = rejected = 0
            for candidate, patch in hp_targets.iter_marks(
                    rgb, candidates, scan_dpi=capture.scan_dpi,
                    polarity=polarity, tone=tone):
                result = mark_offsets(
                    patch, scan_dpi=capture.scan_dpi,
                    tone="none" if polarity == "light" else tone)
                if not result.ok:
                    continue
                good, ratio = hp_targets.achromatic(result.contrast)
                if not good:
                    rejected += 1
                    continue
                kept += 1
                rows.append({
                    "capture": capture.name,
                    "arm": "marks" if polarity == "dark" else "holes",
                    "polarity": polarity,
                    "engine": capture.engine,
                    "role": capture.role,
                    "placement": capture.placement,
                    "target": f"{polarity}-{candidate.index}",
                    "family": capture.experiment,
                    "x_mm": candidate.cx / capture.scan_dpi * 25.4,
                    "y_mm": candidate.cy / capture.scan_dpi * 25.4,
                    "area_px": candidate.area_px,
                    "contrast_ratio": ratio,
                    "contrast_G": result.contrast.get("G"),
                    "excluded_fraction": result.excluded_fraction,
                    "dx_dots": {c: result.offsets_dots[c]["dx_dots"]
                                for c in CHANNELS},
                    "dy_dots": {c: result.offsets_dots[c]["dy_dots"]
                                for c in CHANNELS},
                    "dx_dots_moment": {
                        c: result.offsets_dots[c]["dx_dots_moment"]
                        for c in CHANNELS},
                    "dy_dots_moment": {
                        c: result.offsets_dots[c]["dy_dots_moment"]
                        for c in CHANNELS},
                })
            found.update({"kept": float(kept),
                          "rejected_chromatic": float(rejected)})
            entry[polarity] = found
        if want_comb:
            entry["spectra"] = hp_comb.spectra(
                rgb, small, scan_dpi=capture.scan_dpi,
                decimate=hp_targets.DECIMATE)
        census[capture.name] = entry
        del rgb, small
        gc.collect()
        if verbose:
            counts = {p: int(entry[p].get("kept", 0)) for p in polarities}
            print(f"  {capture.name:<40} {counts}  "
                  f"{time.time() - started:.1f}s", file=sys.stderr)
    return rows, census


# --- platen-profile reproducibility ---------------------------------------

def platen_profile(rows: list[dict[str, Any]], capture: str, axis: str,
                   channel: str, bin_mm: float = BIN_MM
                   ) -> dict[int, tuple[float, int]]:
    """Mean offset per platen-x bin, for one capture, axis and channel."""
    subset = [row for row in rows if row["capture"] == capture]
    xs, _, values = _series(subset, axis, channel)
    out: dict[int, tuple[float, int]] = {}
    if not values.size:
        return out
    for index in np.unique((xs // bin_mm).astype(int)):
        inside = values[(xs // bin_mm).astype(int) == index]
        if inside.size >= MIN_BIN_COUNT:
            out[int(index)] = (float(inside.mean()), int(inside.size))
    return out


def profile_reproducibility(rows: list[dict[str, Any]],
                            captures: Sequence[str], arm: str = "marks",
                            bin_mm: float = BIN_MM) -> dict[str, Any]:
    """Do two captures agree bin-for-bin along the platen?

    Reported in the shape ``channel_ca.verdict`` consumes, so the
    pre-registered rule reads it without knowing it came from bins
    rather than from named targets.
    """
    subset = [row for row in rows if row["arm"] == arm]
    out: dict[str, Any] = {}
    for axis in ("x", "y"):
        for channel in CHANNELS:
            profiles = {name: platen_profile(subset, name, axis, channel,
                                             bin_mm)
                        for name in captures}
            paired: list[tuple[float, float]] = []
            for index in sorted(set.intersection(
                    *[set(p) for p in profiles.values()]) if profiles else []):
                values = [profiles[name][index][0] for name in captures]
                for first in range(len(values)):
                    for second in range(first + 1, len(values)):
                        paired.append((values[first], values[second]))
            if len(paired) < 3:
                continue
            first = np.asarray([p[0] for p in paired])
            second = np.asarray([p[1] for p in paired])
            difference = second - first
            correlation = (float(np.corrcoef(first, second)[0, 1])
                           if first.size > 2 and first.std() > 0
                           and second.std() > 0 else float("nan"))
            out[f"{axis}/{channel}-G"] = {
                "n_paired": int(first.size),
                "bin_mm": bin_mm,
                "mean_a_dots": float(first.mean()),
                "mean_b_dots": float(second.mean()),
                "median_abs_difference_dots":
                    float(np.median(np.abs(difference))),
                "max_abs_difference_dots": float(np.abs(difference).max()),
                "pearson_r": correlation,
            }
    return out


# --- placement arm: is the effect locked to the platen or to the page? ----

def orientation_arm(rows: list[dict[str, Any]],
                    captures: Sequence[hp_inventory.Capture]
                    ) -> dict[str, Any]:
    """Compare capture means across the 0 / 90 / 180 degree placements.

    The prediction is arithmetic, not statistical.  Let the flat capture
    read (dx, dy) in PLATEN coordinates.

    * If the effect is locked to the PAGE, the 180-degree capture must
      read (-dx, -dy) — the page carries it around with it — and the
      90-degree capture must read the two axes exchanged.
    * If the effect is locked to the PLATEN, every placement reads the
      same (dx, dy), because the sheet's orientation is not part of the
      measurement at all.

    A page-locked term of this size would be printer per-plane
    registration, which is the plane-field service's own business and
    NOT a scanner property; separating them is the whole reason this arm
    exists.
    """
    by_placement: dict[str, dict[str, Any]] = {}
    index = {capture.name: capture for capture in captures}
    for capture_name in {row["capture"] for row in rows}:
        capture = index.get(capture_name)
        if capture is None or capture.role != "primary":
            continue
        subset = [row for row in rows
                  if row["capture"] == capture_name and row["arm"] == "marks"]
        entry: dict[str, Any] = {"placement": capture.placement,
                                 "n": len(subset)}
        for axis in ("x", "y"):
            for channel in CHANNELS:
                _, _, values = _series(subset, axis, channel)
                if values.size:
                    entry[f"{axis}/{channel}-G"] = float(values.mean())
        by_placement[capture_name] = entry

    flat = [name for name, entry in by_placement.items()
            if entry["placement"].startswith("flat")]
    tests: dict[str, Any] = {}
    if flat:
        reference = by_placement[flat[0]]
        for name, entry in sorted(by_placement.items()):
            if name == flat[0]:
                continue
            comparison: dict[str, Any] = {"placement": entry["placement"]}
            for channel in CHANNELS:
                for axis in ("x", "y"):
                    key = f"{axis}/{channel}-G"
                    if key not in entry or key not in reference:
                        continue
                    comparison[f"{key}/observed"] = entry[key]
                    comparison[f"{key}/platen_locked_predicts"] = \
                        reference[key]
                    if "180" in entry["placement"]:
                        comparison[f"{key}/page_locked_predicts"] = \
                            -reference[key]
                    elif "90" in entry["placement"]:
                        other = f"{'y' if axis == 'x' else 'x'}/{channel}-G"
                        comparison[f"{key}/page_locked_predicts"] = \
                            reference.get(other)
            tests[name] = comparison
    return {"by_placement": by_placement, "against_flat": tests}


MIN_POLARITY_N = 8


def polarity_arm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Black marks against white holes: displacement or PSF asymmetry?

    The half-SUM of the two polarities is the displacement (both move
    together) and the half-DIFFERENCE is the per-channel PSF asymmetry
    (they move oppositely).  Reported per axis and channel over the
    capture population, because the two polarities are different objects
    on different pages and cannot be paired target for target.

    MEASURED NEGATIVE on this corpus, and the gate below is why it is
    reported as one rather than as a number.  A white hole needs to be
    at least 0.35 mm across AND to sit inside an unbroken 0.4 mm ink
    collar, and across all 23 captures exactly ONE object qualified.
    One target has no standard error, and its offsets came back at
    +1.39 dots — an order above anything the dark arm sees anywhere,
    which is what a single marginal fit looks like, not a measurement.
    Reporting it as a polarity split would have turned one bad target
    into a claim about the scanner's PSF.

    So the displacement-versus-skew separation is OWED on this scanner,
    not answered.  ``channel_ca`` answers it on the Canon with a
    slanted-edge arm, which needs a K rectangle at least 4 mm on a side;
    these pages have them, but at 2 px per printed dot the engine has a
    quarter of the sub-pixel bins it had at 4800 dpi, and that is a
    separate build.
    """
    out: dict[str, Any] = {}
    for axis in ("x", "y"):
        for channel in CHANNELS:
            dark = _series([r for r in rows if r["arm"] == "marks"],
                           axis, channel)[2]
            light = _series([r for r in rows if r["arm"] == "holes"],
                            axis, channel)[2]
            if dark.size < MIN_POLARITY_N or light.size < MIN_POLARITY_N:
                out[f"{axis}/{channel}-G"] = {
                    "n_dark": int(dark.size), "n_light": int(light.size),
                    "tested": False,
                    "note": f"fewer than {MIN_POLARITY_N} targets of one "
                            f"polarity — the split is not runnable on this "
                            f"corpus, and a single hole is not a measurement",
                }
                continue
            out[f"{axis}/{channel}-G"] = {
                "n_dark": int(dark.size), "n_light": int(light.size),
                "tested": True,
                "dark_mean_dots": float(dark.mean()),
                "light_mean_dots": float(light.mean()),
                "displacement_dots": 0.5 * float(dark.mean() + light.mean()),
                "psf_asymmetry_dots": 0.5 * float(dark.mean() - light.mean()),
                "standard_error_dots": float(math.sqrt(
                    dark.var(ddof=1) / dark.size
                    + light.var(ddof=1) / light.size)) / 2.0,
            }
    return out


# --- aggregation ----------------------------------------------------------

def transport_model(y_mm: np.ndarray, values: np.ndarray) -> dict[str, Any]:
    """The same quadratic fit, but DOWN the page instead of across it.

    ``platen_model`` answers the lateral-aberration question, which is a
    function of sensor position.  It is the wrong axis for the term this
    scanner actually has.  The offset that matters here is on the
    TRANSPORT axis, and the transport is the documented unstable part of
    this instrument: stochastic y steps fresh on every scan, and a y
    scale that changes with acquisition mode (experiments/002 §270).  A
    per-channel timing offset is proportional to carriage speed, so if
    the carriage does not hold speed down the page, the "constant" is
    not one — it is a field in y, and a field in y is exactly what would
    be worth publishing.

    Fitted over the payload band in y, evaluated only where sampled.
    """
    if y_mm.size < 6:
        return {"n": int(y_mm.size), "fitted": False}
    centre = 0.5 * (PAYLOAD_Y_MM[0] + PAYLOAD_Y_MM[1])
    scale = 0.5 * (PAYLOAD_Y_MM[1] - PAYLOAD_Y_MM[0])
    u = (y_mm - centre) / scale
    design = np.column_stack([np.ones_like(u), u, u * u])
    solution, *_ = np.linalg.lstsq(design, values, rcond=None)
    residual = values - design @ solution
    grid = (np.linspace(float(y_mm.min()), float(y_mm.max()), 64)
            - centre) / scale
    curve = np.column_stack([np.ones_like(grid), grid, grid * grid]) @ solution
    return {
        "n": int(y_mm.size), "fitted": True,
        "model_y_mm": [float(y_mm.min()), float(y_mm.max())],
        "constant_dots": float(solution[0]),
        "linear_dots_per_half_page": float(solution[1]),
        "quadratic_dots": float(solution[2]),
        "residual_rms_dots": float(np.sqrt(np.mean(residual ** 2))),
        "model_range_dots": float(curve.max() - curve.min()),
    }


def summarize(rows: list[dict[str, Any]], arms: Sequence[str]
              ) -> dict[str, Any]:
    """Per-arm statistics, including the demeaned (field) number."""
    out: dict[str, Any] = {}
    for arm in arms:
        subset = [row for row in rows if row["arm"] == arm]
        for axis in ("x", "y"):
            for channel in CHANNELS:
                xs, ys, values = _series(subset, axis, channel)
                # A one-target arm has a mean, a maximum and a standard
                # deviation of exactly zero, and all three are lies.  The
                # hole arm found ONE hole in 23 captures; leaving its row
                # in the results table would put a number where the
                # honest entry is "not runnable".
                if values.size < MIN_POLARITY_N:
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
                    "median_abs_demeaned_dots":
                        float(np.median(np.abs(centred))),
                    "p95_abs_dots": float(np.percentile(np.abs(values), 95)),
                    "fraction_over_floor": float(
                        np.mean(np.abs(values) >= FLOOR_DOTS)),
                    "cells_c2": float(np.abs(values).max() / C2_CELL_DOTS),
                    "platen_model": platen_model(xs, values),
                    "transport_model": transport_model(ys, values),
                }
    return out


def channel_separation(summary: dict[str, Any], arm: str = "marks"
                       ) -> dict[str, Any]:
    """R-to-B, the largest separation any pair of channels shows.

    The estimator differences everything against G, so neither reported
    pair is the worst case: the extreme channel pair is R against B, and
    on a plane-mapped colour page that is the CYAN plane against the
    YELLOW plane — cyan absorbs red, yellow absorbs blue.  A per-plane
    delta is what the publish floor is written about, so this is the
    number the floor should actually be read against.
    """
    out: dict[str, Any] = {}
    for axis in ("x", "y"):
        red = summary.get(f"{arm}/{axis}/R-G")
        blue = summary.get(f"{arm}/{axis}/B-G")
        if not red or not blue:
            continue
        separation = red["mean_dots"] - blue["mean_dots"]
        out[axis] = {
            "R_minus_G_dots": red["mean_dots"],
            "B_minus_G_dots": blue["mean_dots"],
            "R_minus_B_dots": separation,
            "R_minus_B_um": separation * 25400.0 / PRINT_DPI,
            "over_floor": bool(abs(separation) >= FLOOR_DOTS),
            "as_fraction_of_c2_cell": abs(separation) / C2_CELL_DOTS,
        }
    return out


def verdict_robustness(rows: list[dict[str, Any]], summary: dict[str, Any],
                       arm: str = "marks") -> dict[str, Any]:
    """How the pre-registered statistic behaves as captures accumulate.

    The pre-registered rule tests a MAXIMUM over targets, and a maximum
    is not scale-free: draw more samples from the same distribution and
    it climbs, with the physics unchanged.  That is not a hypothetical
    here — it is what happened.  The 8-capture run of this instrument
    reported worst |offset| 0.2300 dots and NOT USEFUL; adding the
    fifteen secondary captures took the same statistic to 0.2618 and
    the verdict to USEFUL, while the population MEAN moved by 0.007
    dots.  Nothing about the scanner changed between those two runs.

    So the growth curve is reported next to the verdict: the worst
    |offset| over the first k captures, in a fixed order, against the
    mean over the same k.  A mean that holds while the max climbs is
    the signature of a constant plus noise, and it is the reader's
    warning not to read the max as a physical quantity.  The rule is
    still evaluated exactly as pre-registered — this block reports, it
    does not adjudicate.
    """
    worst_key = None
    worst = 0.0
    for key, entry in summary.items():
        if key.startswith(f"{arm}/") and entry["max_abs_dots"] > worst:
            worst, worst_key = entry["max_abs_dots"], key
    if worst_key is None:
        return {}
    _, axis, pair = worst_key.split("/")
    channel = pair.split("-")[0]
    order: list[str] = []
    for row in rows:
        if row["arm"] == arm and row["capture"] not in order:
            order.append(row["capture"])
    curve: list[dict[str, Any]] = []
    for count in range(1, len(order) + 1):
        subset = [row for row in rows
                  if row["arm"] == arm and row["capture"] in order[:count]]
        _, _, values = _series(subset, axis, channel)
        if not values.size:
            continue
        curve.append({
            "captures": count, "n": int(values.size),
            "max_abs_dots": float(np.abs(values).max()),
            "mean_dots": float(values.mean()),
            "p95_abs_dots": float(np.percentile(np.abs(values), 95)),
        })
    entry = summary[worst_key]
    return {
        "statistic": worst_key,
        "note": "the pre-registered rule tests a maximum over targets, "
                "which grows with sample size at fixed physics",
        "growth": curve,
        "max_abs_dots": entry["max_abs_dots"],
        "p95_abs_dots": entry["p95_abs_dots"],
        "mean_dots": entry["mean_dots"],
        "fraction_over_floor": entry["fraction_over_floor"],
        "n_over_floor": int(round(entry["fraction_over_floor"] * entry["n"])),
        "n": entry["n"],
    }


def field_verdict(summary: dict[str, Any], arm: str = "marks"
                  ) -> dict[str, Any]:
    """The second decision: would a scanner FIELD be publishable?

    ``src/holo/receiver/plugins/fields.py publishable`` gates on the MEDIAN magnitude
    of the fitted delta over its support, not on a maximum, so the
    honest comparison for a field is the median absolute deviation from
    the platen-wide constant.  This is deliberately a separate verdict
    from the pre-registered one: the pre-registered rule asks whether
    there is a channel offset at all, and this asks whether what is left
    after a constant has been removed is worth a field.
    """
    worst = {"key": None, "median": 0.0, "max": 0.0}
    for key, entry in summary.items():
        if not key.startswith(f"{arm}/"):
            continue
        if entry["median_abs_demeaned_dots"] > worst["median"]:
            worst = {"key": key,
                     "median": entry["median_abs_demeaned_dots"],
                     "max": entry["max_abs_demeaned_dots"]}
    return {
        "floor_dots": FLOOR_DOTS,
        "floor_gate": "src/holo/receiver/plugins/fields.py publishable() — median "
                      "magnitude of the fitted field over its support",
        "worst_median_abs_demeaned_dots": worst["median"],
        "worst_max_abs_demeaned_dots": worst["max"],
        "worst_key": worst["key"],
        "headroom_factor": (FLOOR_DOTS / worst["median"]
                            if worst["median"] > 0 else float("inf")),
        "verdict": "FIELD PUBLISHABLE" if worst["median"] >= FLOOR_DOTS
                   else "FIELD NOT PUBLISHABLE",
    }


# --- driver ---------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scanfield.hp_channel_ca", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--marks", action="store_true")
    parser.add_argument("--holes", action="store_true",
                        help="white-hole polarity split")
    parser.add_argument("--comb", action="store_true",
                        help="the 18.63 mm and 11.36 px comb confounders")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--tone", choices=("srgb", "gamma22", "none"),
                        default="srgb")
    parser.add_argument("--roles", nargs="+",
                        default=["primary", "control", "k-only"])
    parser.add_argument("--bin-mm", type=float, default=BIN_MM)
    parser.add_argument("--no-figure", dest="figure", action="store_false")
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.all:
        args.selftest = args.marks = args.holes = args.comb = True
    if not (args.selftest or args.marks or args.holes or args.comb):
        parser.error("choose an arm (or --all)")

    hp_inventory.use_evidence_root(args.evidence_root)
    captures = hp_inventory.take(tuple(args.roles))
    if not captures and (args.marks or args.holes or args.comb):
        _evidence.need(*(capture.path for capture in hp_inventory.HOME_COLOUR
                         if capture.role in args.roles), tool="hp_channel_ca")
    report: dict[str, Any] = {
        "instrument": "measure/scanfield/hp_channel_ca",
        "purpose": "does the home/HP flatbed's per-channel geometry clear "
                   "the 0.25-dot publish floor anywhere a payload sits?",
        "scanner": hp_inventory.HOME_FLATBED,
        "sibling": "measure/scanfield/channel_ca (Canon LiDE 400)",
        "generated_unix": int(time.time()),
        "tone_curve": args.tone,
        "floor_dots": FLOOR_DOTS,
        "payload_band_x_mm": list(PAYLOAD_X_MM),
        "payload_band_y_mm": list(PAYLOAD_Y_MM),
        "captures": [{"name": c.name, "engine": c.engine, "role": c.role,
                      "placement": c.placement, "experiment": c.experiment,
                      "scan_dpi": c.scan_dpi, "content": c.content}
                     for c in captures],
    }

    if args.selftest:
        # At THIS footing.  The Canon arm calibrated at 4800 dpi, where
        # the floor is 2 px; here it is half a pixel, and an estimator
        # that was 300x below the floor there is not automatically below
        # it here.  This is the number that says whether the verdict is
        # measuring the scanner or measuring the instrument.
        report["selftest"] = selftest(scan_dpi=SCAN_DPI, tone=args.tone)
        worst = max(abs(case["error_dx_dots"]) for case in report["selftest"])
        worst_dy = max(abs(case["error_dy_dots"])
                       for case in report["selftest"])
        report["selftest_worst_error_dots"] = max(worst, worst_dy)
        report["selftest_scan_dpi"] = SCAN_DPI
        print(f"  selftest @{SCAN_DPI:g} dpi: worst |error| "
              f"{max(worst, worst_dy):.5f} dots", file=sys.stderr)

    rows: list[dict[str, Any]] = []
    arms: list[str] = []
    if args.marks or args.holes or args.comb:
        polarities = tuple(p for p, on in
                           (("dark", args.marks or args.comb),
                            ("light", args.holes)) if on)
        rows, census = marks_arm(captures, args.tone, polarities,
                                 want_comb=args.comb)
        report["census"] = census
        arms = [{"dark": "marks", "light": "holes"}[p] for p in polarities]

    report["rows"] = rows
    if rows:
        report["summary"] = summarize(rows, arms)
        report["antisymmetry"] = antisymmetry(rows, arms)
        report["channel_separation"] = channel_separation(report["summary"])
        primary = [c.name for c in captures if c.role == "primary"]
        if len(primary) >= 2:
            report["reproducibility_profile"] = profile_reproducibility(
                rows, primary, bin_mm=args.bin_mm)
        report["orientation"] = orientation_arm(rows, captures)
        if args.holes:
            report["polarity"] = polarity_arm(rows)
        if args.comb:
            report["comb_phase"] = hp_comb.comb_phase_report(
                [r for r in rows if r["arm"] == "marks"], SCAN_DPI)
        report["verdict"] = verdict(
            report["summary"], report.get("reproducibility_profile", {}))
        report["verdict_robustness"] = verdict_robustness(
            rows, report["summary"])
        report["field_verdict"] = field_verdict(report["summary"])

    args.out.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.tone == "srgb" else f"-{args.tone}"
    path = args.out / f"hp-channel-ca{suffix}.json"
    path.write_text(json.dumps(report, indent=1, allow_nan=True))
    print(f"wrote {path}", file=sys.stderr)
    if args.figure and rows:
        from .hp_figure import draw_hp_offset_map
        figure = args.out / f"hp-channel-ca{suffix}.png"
        draw_hp_offset_map(figure, report)
        print(f"wrote {figure}", file=sys.stderr)
    _print_tables(report)
    return 0


def _print_tables(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    if summary:
        print(f"\n{'arm/axis/pair':<22}{'n':>5}{'mean':>9}{'sd':>8}"
              f"{'max|.|':>9}{'med|.-mean|':>13}{'range(x)':>10}"
              f"{'range(y)':>10}{'x span mm':>18}")
        for key in sorted(summary):
            entry = summary[key]
            model = entry["platen_model"]
            down = entry["transport_model"]
            span = entry["x_mm_span"]
            print(f"{key:<22}{entry['n']:>5}{entry['mean_dots']:>9.4f}"
                  f"{entry['std_dots']:>8.4f}{entry['max_abs_dots']:>9.4f}"
                  f"{entry['median_abs_demeaned_dots']:>13.4f}"
                  f"{model.get('model_range_dots', float('nan')):>10.4f}"
                  f"{down.get('model_range_dots', float('nan')):>10.4f}"
                  f"{span[0]:>9.1f}{span[1]:>9.1f}")
    separation = report.get("channel_separation")
    if separation:
        print("\nchannel separation (R-G, B-G, and the extreme pair R-B)")
        for axis, entry in sorted(separation.items()):
            print(f"  {axis}: R-G {entry['R_minus_G_dots']:+.4f}  "
                  f"B-G {entry['B_minus_G_dots']:+.4f}  "
                  f"R-B {entry['R_minus_B_dots']:+.4f} dots "
                  f"({entry['R_minus_B_um']:+.2f} um)  "
                  f"over floor: {entry['over_floor']}")
    orientation = report.get("orientation", {}).get("against_flat")
    if orientation:
        print("\nplacement arm — platen-locked or page-locked?")
        for name, entry in sorted(orientation.items()):
            print(f"  {name}  [{entry['placement']}]")
            for key in sorted(k for k in entry if k.endswith("/observed")):
                stem = key[: -len("/observed")]
                platen = entry.get(f"{stem}/platen_locked_predicts")
                page = entry.get(f"{stem}/page_locked_predicts")
                if platen is None:
                    continue
                page_text = "n/a" if page is None else f"{page:+.4f}"
                print(f"    {stem:<8} observed {entry[key]:+.4f}  "
                      f"platen-locked predicts {platen:+.4f}  "
                      f"page-locked predicts {page_text}")
    polarity = report.get("polarity")
    if polarity:
        runnable = [e for e in polarity.values() if e.get("tested")]
        print("\npolarity split — black marks vs white holes")
        if not runnable:
            example = next(iter(polarity.values()))
            print(f"  NOT RUNNABLE: {example['n_light']} usable white "
                  f"hole(s) against {example['n_dark']} marks — "
                  f"displacement vs PSF skew stays OWED on this scanner")
        else:
            print(f"{'  axis/pair':<14}{'n dark':>8}{'n light':>8}{'dark':>10}"
                  f"{'light':>10}{'displace':>11}{'PSF skew':>11}{'s.e.':>9}")
            for key, entry in sorted(polarity.items()):
                if not entry.get("tested"):
                    continue
                print(f"  {key:<12}{entry['n_dark']:>8}{entry['n_light']:>8}"
                      f"{entry['dark_mean_dots']:>10.4f}"
                      f"{entry['light_mean_dots']:>10.4f}"
                      f"{entry['displacement_dots']:>11.4f}"
                      f"{entry['psf_asymmetry_dots']:>11.4f}"
                      f"{entry['standard_error_dots']:>9.4f}")
    comb = report.get("comb_phase")
    if comb:
        print("\ncomb phase test — do the offsets vary within a comb period?")
        print(f"{'  comb/axis/pair':<28}{'n':>5}{'binned range':>14}"
              f"{'noise range':>13}{'effect':>10}{'explains?':>11}")
        for key, entry in sorted(comb.items()):
            if not entry.get("tested"):
                continue
            print(f"  {key:<26}{entry['n']:>5}"
                  f"{entry['binned_range_dots']:>14.4f}"
                  f"{entry['expected_range_from_noise_dots']:>13.4f}"
                  f"{entry['effect_mean_dots']:>10.4f}"
                  f"{str(entry['explains_effect']):>11}")
    repro = report.get("reproducibility_profile")
    if repro:
        print(f"\nplaten-profile reproducibility across the primary captures\n"
              f"{'  axis/pair':<14}{'pairs':>7}{'mean A':>10}{'mean B':>10}"
              f"{'med|A-B|':>11}{'max|A-B|':>11}{'r':>8}")
        for key, entry in sorted(repro.items()):
            print(f"  {key:<12}{entry['n_paired']:>7}"
                  f"{entry['mean_a_dots']:>10.4f}{entry['mean_b_dots']:>10.4f}"
                  f"{entry['median_abs_difference_dots']:>11.4f}"
                  f"{entry['max_abs_difference_dots']:>11.4f}"
                  f"{entry['pearson_r']:>8.3f}")
    robust = report.get("verdict_robustness")
    if robust and robust.get("growth"):
        print(f"\nthe pre-registered statistic as captures accumulate "
              f"({robust['statistic']})")
        print(f"{'  captures':<11}{'n':>7}{'max|.|':>10}{'p95|.|':>10}"
              f"{'mean':>10}")
        for point in robust["growth"]:
            print(f"  {point['captures']:<9}{point['n']:>7}"
                  f"{point['max_abs_dots']:>10.4f}"
                  f"{point['p95_abs_dots']:>10.4f}"
                  f"{point['mean_dots']:>10.4f}")
        print(f"  {robust['n_over_floor']} of {robust['n']} marks "
              f"({100 * robust['fraction_over_floor']:.2f} %) are at or over "
              f"the floor")
    final = report.get("verdict")
    if final:
        print(f"\nPRE-REGISTERED VERDICT: {final['verdict']}  "
              f"(worst raw {final['worst_raw_offset']['value']:.4f} dots at "
              f"{final['worst_raw_offset']['key']}, floor "
              f"{final['floor_dots']}, headroom "
              f"{final['headroom_factor']:.2f}x)")
    field = report.get("field_verdict")
    if field:
        print(f"FIELD VERDICT: {field['verdict']}  "
              f"(worst median |offset - platen mean| "
              f"{field['worst_median_abs_demeaned_dots']:.4f} dots at "
              f"{field['worst_key']}, headroom "
              f"{field['headroom_factor']:.1f}x)")


if __name__ == "__main__":
    raise SystemExit(main())
