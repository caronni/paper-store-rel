"""Physical-margin, registration, and scanner-adequacy summaries."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import numpy as np

PHYSICAL_TICK_GAPS = (
    0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0,
    3.5, 4.0, 5.0, 6.0, 8.0, 10.0,
)
PAYLOAD_CANARY_GAPS = (0.5, 1.5, 2.5, 3.5, 5.0, 6.5, 8.0, 10.0)
SCANNER_C3_ERROR_MAX = 0.05
SCANNER_C2_ERROR_MAX = 0.18
SCANNER_SAMPLING_CORRELATION_MIN = 0.20
SCANNER_BLOCKINESS_MAX = 1.25
# W9 (e031, 2026-08-06): was 1.0, which failed EVERY capture ever taken
# across two engines on files that are provably uncompressed. The statistic
# was never the problem — an independent FFT estimate of the per-pixel white
# noise reproduces it closely — the threshold was simply set above the
# scanner's real floor. Re-derived from measurement with positive AND
# negative controls on a blank-paper patch (8-bit counts):
#   clean captures, three sheets, two engines      0.46 - 0.84
#   legitimate 2400-dpi averaging mode             0.84
#   JPEG q95 / q75 / q50                           0.39 - 0.54  (blockiness
#                                                   catches these: 1.36-4.79)
#   gaussian blur sigma 0.7 / 1.5                  0.155 / 0.079
#   median 3x3                                     0.226
# 0.30 sits in the empty band between the smoothed cases (<=0.226) and the
# honest ones (>=0.46), with roughly 1.5x margin either side.
SCANNER_NOISE_MIN_8BIT = 0.30
# Below this a quiet region carries so little signal that "smoothed" and
# "flat patch" are indistinguishable. Blur sigma 1.5 reads 0.079 and must
# still FAIL rather than excuse itself as indeterminate.
SCANNER_NOISE_INDETERMINATE_8BIT = 0.05
# W10 (e031): phase-invariant comb detector on the quiet zone, closing the
# fixed-8px hole (a scanner compressing internally at lower resolution and
# interpolating up delivers seams at 16/32/64 px at arbitrary phase, which
# blockiness_8px cannot see).  Derived on real captures + degraded controls
# (experiments/031-xerox-altalink-discovery/w10_structured_capture_checks.py):
# clean blank patches across four captures incl. the 2400-dpi mode read
# <= 1.075; the weakest degraded control (JPEG q60 at half resolution,
# bilinear-upsampled, arbitrary phase) reads 2.135.  1.25 keeps ~1.16x and
# ~1.7x margins.  Patch hygiene matters: sheet-edge/backing contamination
# once read 2.2-2.5 on clean margins — the analyzer's authored quiet zone
# cannot have that problem, harnesses must emulate it.
SCANNER_COMB_MAX = 1.25
# W10 (e031): ESF overshoot beyond the edge plateaus.  Print physics cannot
# make paper brighter than paper or solid darker than solid, so overshoot is
# capture sharpening — the one smoothing-family signature whose attribution
# is clean on a single scan.  Measured only where a slanted-edge probe is
# printed (B/W discovery sheets); absent elsewhere and then non-gating.
# The metric compares the near-edge extremum of the median-smoothed ESF
# against each plateau's own 1st/99th-percentile envelope — a plateau-median
# reference reads solid-toner mottle (log-amplified in density space) as
# 5-7% false overshoot through the pipeline on clean captures.  Derived on
# the two real B/W edges (clean 0.0002/0.0026) against an unsharp-mask
# sweep on the SAME crops (sigma 12/24/48/96, amount 1.0 -> 0.0005/0.0996/
# 0.1998/0.2878): sub-edge-width radii are near-invisible AND near-harmless
# at this footing — nothing at those frequencies survives the optics — so
# the detector responds in proportion to a sharpener's capacity to distort.
# 0.05 = ~19x over clean, 2x under the weakest harmful-class control
# (sigma 24, half the measured edge width).
SCANNER_OVERSHOOT_MAX = 0.05


def summarize_tones(probes: Iterable[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    for row in probes:
        if row.get("group") != "tone" or row.get("status") != "ok":
            continue
        if row.get("kind") == "profile_tone":
            continue
        try:
            coverage = float(row.get("params", {})["coverage"])
        except (KeyError, TypeError, ValueError):
            continue
        grouped[str(row["plane"])].append(
            (coverage, float(row["density_median"]), row["probe_id"])
        )
    output: dict[str, Any] = {}
    for plane, rows in sorted(grouped.items()):
        rows.sort()
        coverage = np.asarray([row[0] for row in rows], np.float64)
        measured = np.asarray([row[1] for row in rows], np.float64)
        differences = np.diff(measured)
        output[plane] = {
            "patches": [
                {"coverage": row[0], "density_median": row[1],
                 "probe_id": row[2]}
                for row in rows
            ],
            "monotonic": bool(np.all(differences >= -0.01)),
            "monotonicity_violations": int(np.count_nonzero(differences < -0.01)),
            "density_dynamic_range": (
                float(measured[-1] - measured[0]) if len(measured) else None
            ),
            "coverage_density_correlation": (
                float(np.corrcoef(coverage, measured)[0, 1])
                if len(rows) >= 3 and np.ptp(measured) > 0 else None
            ),
        }
    return output


def summarize_registration(
    probes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in probes:
        if (
            row.get("group") == "plane-registration"
            and row.get("status") == "ok"
            and "centroid_source_dots" in row
        ):
            grouped[str(row.get("registration_target"))][str(row["plane"])] = row
    targets = []
    all_offsets = []
    for target, planes in sorted(grouped.items()):
        reference = planes.get("K")
        if reference is None:
            targets.append({
                "target": target, "status": "incomplete",
                "planes": sorted(planes),
            })
            continue
        ref = np.asarray(reference["centroid_source_dots"], np.float64)
        offsets = {}
        for plane, row in sorted(planes.items()):
            value = np.asarray(row["centroid_source_dots"], np.float64) - ref
            dpi = np.asarray(row.get("source_dpi", (600.0, 600.0)))
            microns = value / dpi * 25_400.0
            offsets[plane] = microns.tolist()
            if plane != "K":
                all_offsets.append(float(np.linalg.norm(microns)))
        targets.append({
            "target": target,
            "status": "ok" if set("KCMY") <= set(planes) else "incomplete",
            "offset_from_k_micrometres": offsets,
        })
    return {
        "targets": targets,
        "worst_plane_offset_micrometres": max(all_offsets, default=None),
        "complete_target_count": sum(
            row["status"] == "ok" for row in targets
        ),
    }


def role_census(
    rows: Iterable[dict[str, Any]],
    key,
    expected: Iterable[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Group rows by declared role and census them against the expected set.

    The one census vocabulary for every summary section: status is
    complete|incomplete with the missing/duplicated/unexpected role lists
    always present (three sections previously spoke three dialects).
    """
    expected_set = set(expected)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        name = key(row)
        if name is not None:
            grouped[str(name)].append(row)
    missing = sorted(name for name in expected_set if not grouped.get(name))
    duplicated = sorted(
        name for name in grouped
        if name in expected_set and len(grouped[name]) > 1
    )
    unexpected = sorted(name for name in grouped if name not in expected_set)
    return grouped, {
        "status": (
            "complete"
            if not (missing or duplicated or unexpected)
            else "incomplete"
        ),
        "missing_roles": missing,
        "duplicated_roles": duplicated,
        "unexpected_roles": unexpected,
    }


def _safe_descending_gap(
    items: "Iterable[tuple[float, bool]]", *, complete: bool,
) -> float | None:
    """Tightest gap whose whole looser suffix passed.

    Scans the ladder from the loosest gap down, AND-ing pass flags; the
    answer exists only for a complete ladder (a missing rung would make
    the claim optimistic).  The one home for both edge ladders.
    """
    safe = None
    running = complete
    for gap, passed in sorted(items, reverse=True):
        running = running and passed
        if running:
            safe = gap
    return safe


def _tick_classification(row: dict[str, Any]) -> str:
    if row.get("status") != "ok":
        return "unobservable"
    tick = row.get("tick")
    if not isinstance(tick, dict) or not tick.get("scorable"):
        return "unscorable"
    return str(tick.get("classification", "unscorable"))


def summarize_physical_ticks(
    probes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Ink-extent ladder from REGISTERED tick verdicts + the clip line.

    Verdicts come from the registered ink coverage of each tick (028.2:
    the retired unregistered p05 rule failed solidly printed ticks on
    1-3 dot displacement).  The headline product is the layout-referenced
    printable clip line per edge, estimated from partially printed ticks
    and bounded by the absent/full ones.  Layout coordinates convolve the
    engine margin with this impression's feed registration; copy variance
    is calibration's job.
    """

    paper = [
        float(row["density_median"]) for row in probes
        if row.get("group") == "background" and row.get("status") == "ok"
    ]
    baseline = float(np.median(paper)) if paper else None
    grouped: dict[str, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
    for row in probes:
        if row.get("group") != "physical-ink-extent":
            continue
        parts = str(row["probe_id"]).split("/")
        if len(parts) != 3:
            continue
        edge, gap_text = parts[1], parts[2]
        try:
            gap = float(gap_text)
        except ValueError:
            continue
        grouped[edge].append((gap, row))
    edges = {}
    for edge in ("top", "right", "bottom", "left"):
        rows = sorted(grouped.get(edge, []), key=lambda item: item[0])
        complete = (
            len(rows) == len(PHYSICAL_TICK_GAPS)
            and {gap for gap, _row in rows} == set(PHYSICAL_TICK_GAPS)
        )
        ticks = []
        estimates: list[float] = []
        upper_bounds: list[float] = []
        lower_bounds: list[float] = []
        partial_gaps: list[float] = []
        for gap, row in rows:
            classification = _tick_classification(row)
            tick = row.get("tick") if isinstance(row.get("tick"), dict) else {}
            size_mm = tick.get("size_mm") or [None, None]
            axis_size = (
                size_mm[0] if edge in {"left", "right"} else size_mm[1]
            )
            entry = {
                "gap_mm": gap,
                "classification": classification,
                "passed": classification == "full",
                "probe_id": row["probe_id"],
                "ink_fraction_nominal": tick.get("ink_fraction_nominal"),
                "ink_fraction_registered": tick.get(
                    "ink_fraction_registered"
                ),
                "displacement_layout_dots": tick.get(
                    "displacement_layout_dots"
                ),
            }
            if "clip_mm_estimate" in tick:
                entry["clip_mm_estimate"] = tick["clip_mm_estimate"]
            ticks.append(entry)
            if axis_size is None:
                continue
            if classification == "partial":
                partial_gaps.append(gap)
                if "clip_mm_estimate" in tick:
                    estimates.append(float(tick["clip_mm_estimate"]))
            elif classification == "full":
                upper_bounds.append(gap + 0.15 * float(axis_size))
            elif classification == "absent":
                lower_bounds.append(gap + 0.90 * float(axis_size))
        safe = _safe_descending_gap(
            (
                (entry["gap_mm"], entry["passed"])
                for entry in ticks
            ),
            complete=complete,
        )
        clip_upper = min(upper_bounds) if upper_bounds else None
        clip_lower = max(lower_bounds) if lower_bounds else 0.0
        if estimates:
            clip = float(np.median(estimates))
        elif (
            clip_upper is not None
            and clip_lower <= clip_upper + 0.5
        ):
            clip = 0.5 * (min(clip_lower, clip_upper) + clip_upper)
        else:
            clip = None
        edges[edge] = {
            "complete": complete,
            "safe_gap_mm": safe,
            "first_partial_gap_mm": (
                min(partial_gaps) if partial_gaps else None
            ),
            "printable_clip_mm": clip,
            "clip_bounds_mm": [clip_lower, clip_upper],
            "n_partial_ticks": len(partial_gaps),
            "ticks": ticks,
        }
    return {
        "paper_density_baseline": baseline,
        "printable_clip_mm": {
            edge: edges[edge]["printable_clip_mm"] for edge in edges
        },
        "clip_scope": (
            "layout-frame distance from the page edge at which printed ink "
            "begins; convolves the engine margin with this impression's "
            "print-to-paper registration"
        ),
        "edges": edges,
    }


EDGE_FLAT_COMPARABILITY = 0.02


def summarize_payload_edges(
    fields: Iterable[dict[str, Any]],
    candidates: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Edge-canary BER-vs-gap curves: characterization data, not verdicts.

    Ruling 2026-08-04 (workplan W3): the print margin is the measured
    clip line; these curves are the check against it.  The former
    passed/exact_references_ok/safe-rectangle verdict layer let one
    interior worst-window tail veto every edge product on the page and
    is deleted, not redesigned.  ``edge_flat_gap_mm`` is a descriptive
    statistic (arm upper within EDGE_FLAT_COMPARABILITY of its interior
    reference for the whole looser suffix), never a gate.
    """

    candidate_rows = {
        int(row["candidate_code"]): row for row in candidates
    }
    grouped: dict[str, dict[float, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in fields:
        if row.get("family") == "edge-canary":
            grouped[str(row["edge"])][float(row["gap_mm"])].append(row)
    edges = {}
    for edge in ("top", "right", "bottom", "left"):
        gaps = grouped.get(edge, {})
        rows = []
        arm_codes: set[int] = set()
        for gap in sorted(gaps):
            arms = []
            for arm in gaps[gap]:
                code = int(arm["candidate_code"])
                arm_codes.add(code)
                interior = candidate_rows.get(code, {})
                interior_upper = interior.get(
                    "worst_error_wilson_upper_95"
                )
                arm_upper = (
                    arm.get("error_wilson_95") or [None, None]
                )[1]
                arms.append({
                    "field_id": arm["field_id"],
                    "candidate_id": arm["candidate_id"],
                    "candidate_code": code,
                    "status": arm.get("status"),
                    "error_rate": arm.get("error_rate"),
                    "error_wilson_upper_95": arm_upper,
                    "interior_error_wilson_upper_95": interior_upper,
                    "edge_penalty": (
                        None
                        if arm_upper is None or interior_upper is None
                        else float(arm_upper) - float(interior_upper)
                    ),
                })
            rows.append({"gap_mm": gap, "arms": arms})
        complete = (
            {row["gap_mm"] for row in rows} == set(PAYLOAD_CANARY_GAPS)
            and all(len(gaps[row["gap_mm"]]) == 2 for row in rows)
        )
        arm_curves = {}
        for code in sorted(arm_codes):
            interior_upper = candidate_rows.get(code, {}).get(
                "worst_error_wilson_upper_95"
            )
            items = []
            for row in rows:
                for arm in row["arms"]:
                    if arm["candidate_code"] != code:
                        continue
                    # Small arms carry a Wilson sample-size floor an
                    # absolute margin cannot clear: a point estimate at
                    # or under the interior's upper is also "flat".
                    flat = bool(
                        arm["status"] == "ok"
                        and interior_upper is not None
                        and (
                            (
                                arm["error_wilson_upper_95"] is not None
                                and float(arm["error_wilson_upper_95"])
                                <= float(interior_upper)
                                + EDGE_FLAT_COMPARABILITY
                            )
                            or (
                                arm["error_rate"] is not None
                                and float(arm["error_rate"])
                                <= float(interior_upper)
                            )
                        )
                    )
                    items.append((float(row["gap_mm"]), flat))
            arm_curves[str(code)] = {
                "candidate_id": candidate_rows.get(code, {}).get(
                    "candidate_id"
                ),
                "interior_error_wilson_upper_95": interior_upper,
                "edge_flat_gap_mm": _safe_descending_gap(
                    items, complete=complete
                ),
                "comparability_margin": EDGE_FLAT_COMPARABILITY,
            }
        edges[edge] = {
            "complete": complete,
            "arm_curves": arm_curves,
            "gaps": rows,
        }
    return {
        "edges": edges,
        "scope": (
            "edge-canary BER-vs-gap data with interior references; the "
            "physical print margin lives in physical_ink_extent."
        ),
    }

def _compression_advisory(quiet: dict[str, Any] | None) -> dict[str, Any]:
    """Non-gating capture forensics carried with the compression check.

    Only ``level_occupancy`` remains: the posterisation / bit-depth-reduction
    probe, a NULL DETECTOR on every real capture to date (pinned by test so
    nobody re-derives it as a gate; it does catch a synthetic posterisation).

    The spectral knee / flatness advisory that briefly lived here was
    RETIRED (W9 second pass, then W10): on blank paper the "signal" is paper
    texture, every spectral statistic proved patch-unstable (knee 15-32
    lp/mm within one sheet), and flatness additionally flags a legitimate
    lower-DPI averaging mode whose payload volume decoded byte-exact.  The
    structured-feature checks that replaced it gate in
    ``checks.compression`` (comb) and ``checks.sharpening`` (overshoot).
    """
    if quiet is None:
        return {"status": "unavailable"}
    return {
        "status": "measured",
        "gating": "none - advisory only, see W10 in CHARACTERIZE-WORKPLAN",
        "level_occupancy": quiet.get("level_occupancy"),
    }


def _sharpening_check(
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Capture-sharpening gate from the printed slanted edge (W10).

    Overshoot beyond the ESF plateaus cannot come from the printer, so a
    single scan attributes it to the capture path.  The probe exists on B/W
    discovery sheets only; when no resolved edge is present the check
    reports not-measured and does not gate — an honest reduction in
    coverage on colour pages, not an indeterminate page verdict.
    """
    measured = [
        row for row in probes
        if row.get("kind") == "slanted_edge"
        and row.get("status") == "ok"
        and isinstance(row.get("mtf"), dict)
        and row["mtf"].get("resolved")
        and row["mtf"].get("overshoot_fraction") is not None
    ]
    if not measured:
        return {
            "status": "not-measured",
            "pass": None,
            "threshold_exclusive": SCANNER_OVERSHOOT_MAX,
            "basis": "no resolved slanted-edge probe on this page kind",
        }
    worst = max(
        float(row["mtf"]["overshoot_fraction"]) for row in measured
    )
    passed = worst < SCANNER_OVERSHOOT_MAX
    return {
        "status": "pass" if passed else "fail",
        "pass": passed,
        "overshoot_fraction": worst,
        "threshold_exclusive": SCANNER_OVERSHOOT_MAX,
        "probe_ids": [row.get("probe_id") for row in measured],
    }


def summarize_scanner_adequacy(
    probes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    all_rows = list(probes)
    rows = [
        row for row in all_rows if row.get("group") == "scanner-adequacy"
    ]

    def role(row: dict[str, Any]) -> str | None:
        declared = row.get("params", {}).get("adequacy_role")
        return None if declared is None else str(declared)


    expected_roles = {
        "quiet",
        "entropy",
        "solid_class_c3",
        "marginal_class_c2",
        "sampling_horizontal",
        "sampling_vertical",
    }
    grouped, census = role_census(rows, role, expected_roles)

    def unique(name: str) -> dict[str, Any] | None:
        values = grouped.get(name, [])
        return values[0] if len(values) == 1 else None

    def pattern_check(name: str, threshold: float) -> dict[str, Any]:
        row = unique(name)
        pattern = {} if row is None else row.get("pattern", {})
        error = pattern.get("dot_error_rate")
        passed = bool(
            row is not None
            and row.get("status") == "ok"
            and pattern.get("scorable")
            and error is not None
            and float(error) < threshold
        )
        return {
            "status": (
                "pass" if passed
                else "missing-or-duplicated" if row is None
                else "fail"
            ),
            "pass": passed,
            "threshold_exclusive": threshold,
            "dot_error_rate": error,
            "correlation": pattern.get("correlation"),
            "probe_id": None if row is None else row.get("probe_id"),
        }

    sampling_axes = {}
    for axis, name in (
        ("horizontal", "sampling_horizontal"),
        ("vertical", "sampling_vertical"),
    ):
        row = unique(name)
        pattern = {} if row is None else row.get("pattern", {})
        correlation = pattern.get("correlation")
        passed = bool(
            row is not None
            and row.get("status") == "ok"
            and pattern.get("scorable")
            and correlation is not None
            and float(correlation) >= SCANNER_SAMPLING_CORRELATION_MIN
        )
        sampling_axes[axis] = {
            "status": (
                "pass" if passed
                else "missing-or-duplicated" if row is None
                else "fail"
            ),
            "pass": passed,
            "correlation": correlation,
            "minimum_correlation": SCANNER_SAMPLING_CORRELATION_MIN,
            "dot_error_rate": pattern.get("dot_error_rate"),
            "probe_id": None if row is None else row.get("probe_id"),
        }

    quiet = unique("quiet")
    entropy = unique("entropy")
    noise = (
        None if quiet is None
        else quiet.get("paper_noise_highpass_8bit_counts")
    )
    entropy_blockiness = (
        None if entropy is None else entropy.get("blockiness_8px")
    )
    comb = None if quiet is None else quiet.get("blockiness_comb")
    comb_max = None if not isinstance(comb, dict) else comb.get("max")
    # comb absent (old fixtures, tiny synthetic crops) => the limb simply is
    # not measured and cannot fail; when present it gates like blockiness.
    comb_ok = comb_max is None or float(comb_max) < SCANNER_COMB_MAX
    if noise is None or entropy_blockiness is None:
        compression_verdict = "indeterminate"
    elif float(noise) < SCANNER_NOISE_INDETERMINATE_8BIT:
        compression_verdict = "indeterminate"
    elif (
        float(noise) >= SCANNER_NOISE_MIN_8BIT
        and float(entropy_blockiness) < SCANNER_BLOCKINESS_MAX
        and comb_ok
    ):
        compression_verdict = "pass"
    else:
        compression_verdict = "fail"

    c3 = pattern_check("solid_class_c3", SCANNER_C3_ERROR_MAX)
    c2 = pattern_check("marginal_class_c2", SCANNER_C2_ERROR_MAX)
    sampling_pass = all(
        row["pass"] for row in sampling_axes.values()
    )
    solid_complete = (
        unique("solid_class_c3") is not None
        and all(unique(name) is not None for name in (
            "sampling_horizontal", "sampling_vertical"
        ))
    )
    if not solid_complete:
        solid_verdict = "indeterminate"
    elif c3["pass"] and sampling_pass:
        solid_verdict = "adequate"
    else:
        solid_verdict = "inadequate"

    c2_complete = (
        solid_complete
        and unique("marginal_class_c2") is not None
        and unique("quiet") is not None
        and unique("entropy") is not None
    )
    sharpening = _sharpening_check(all_rows)
    if solid_verdict == "inadequate":
        c2_verdict = "inadequate"
    elif not c2_complete or compression_verdict == "indeterminate":
        c2_verdict = "indeterminate"
    elif (
        c2["pass"] and compression_verdict == "pass"
        and sharpening["status"] != "fail"
    ):
        c2_verdict = "adequate"
    else:
        c2_verdict = "inadequate"

    return {
        "status": census["status"],
        "verdict": (
            "adequate" if c2_verdict == "adequate"
            else "inadequate" if solid_verdict == "inadequate"
            else "indeterminate"
        ),
        "checks": {
            "identity": {
                "status": "pass",
                "pass": True,
                "basis": "page identity already decoded before measurement",
            },
            "solid_class": c3,
            "marginal_class": c2,
            "sampling": {
                "status": "pass" if sampling_pass else "fail",
                "pass": sampling_pass,
                "axes": sampling_axes,
            },
            "compression": {
                "verdict": compression_verdict,
                "quiet_noise_highpass_8bit_counts": noise,
                "noise_minimum_8bit_counts": SCANNER_NOISE_MIN_8BIT,
                "noise_below_8bit_counts_is_indeterminate": (
                    SCANNER_NOISE_INDETERMINATE_8BIT
                ),
                "entropy_blockiness_8px": entropy_blockiness,
                "blockiness_maximum_exclusive": SCANNER_BLOCKINESS_MAX,
                "comb_max": comb_max,
                "comb_max_period_px": (
                    None if not isinstance(comb, dict)
                    else comb.get("max_period_px")
                ),
                "comb_maximum_exclusive": SCANNER_COMB_MAX,
                "advisory": _compression_advisory(quiet),
            },
            "sharpening": sharpening,
        },
        "mode_classes": {
            "solid_class": {"verdict": solid_verdict},
            "c2_class": {"verdict": c2_verdict},
        },
        "missing_roles": census["missing_roles"],
        "duplicated_roles": census["duplicated_roles"],
        "unexpected_roles": census["unexpected_roles"],
        "probes": rows,
    }


def summarize_screen_paths(
    probes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize matched PRN controls without conflating path and colorants."""

    rows = [row for row in probes if row.get("group") == "screen"]
    role_specs = {
        "imagemask-C": {
            "path": "single-plane-imagemask",
            "planes": ("C",),
        },
        "devicecmyk-C": {
            "path": "DeviceCMYK-image",
            "planes": ("C",),
        },
        "devicecmyk-CM": {
            "path": "DeviceCMYK-image",
            "planes": ("C", "M"),
        },
        "opm1-CM": {
            "path": "sequential-overprint-opm1",
            "planes": ("C", "M"),
        },
    }
    required_roles = tuple(role_specs)
    if not rows:
        return {
            "status": "incomplete",
            "valid_control": False,
            "missing_roles": list(required_roles),
            "duplicated_roles": [],
            "unexpected_roles": [],
            "unresolved_roles": [],
            "control_mismatches": [],
            "role_spec_mismatches": [],
            "controls": {},
            "comparisons": [],
            "scope": (
                "descriptive matched-PRN path and plane-content controls only"
            ),
        }

    grouped, census = role_census(
        rows,
        lambda row: row.get("screen", {}).get("control_role"),
        required_roles,
    )
    missing = census["missing_roles"]
    duplicated = census["duplicated_roles"]
    unexpected = census["unexpected_roles"]
    control_rows = {
        role: members[0]
        for role, members in grouped.items()
        if len(members) == 1 and role in role_specs
    }

    def common_signature(row: dict[str, Any]) -> tuple[Any, ...]:
        screen = row.get("screen", {})
        return (
            screen.get("matched_set"),
            screen.get("authored_pattern_sha256"),
            tuple(screen.get("authored_shape_yx", ())),
            tuple(screen.get("authored_dpi", ())),
            tuple(screen.get("physical_extent_mm", ())),
            screen.get("measurement_feature"),
            row.get("plane"),
        )

    reference = control_rows.get(required_roles[0])
    control_mismatches = []
    if reference is not None:
        signature = common_signature(reference)
        control_mismatches = sorted(
            role for role, row in control_rows.items()
            if common_signature(row) != signature
        )
    role_spec_mismatches = sorted(
        role for role, row in control_rows.items()
        if (
            row.get("screen", {}).get("emission_path")
            != role_specs[role]["path"]
            or tuple(
                row.get("screen", {}).get("authored_planes", ())
            ) != role_specs[role]["planes"]
        )
    )
    unresolved = sorted(
        role for role, row in control_rows.items()
        if (
            row.get("status") != "ok"
            or row.get("screen", {}).get("resolved") is not True
        )
    )
    valid_control = bool(
        reference is not None
        and not missing
        and not duplicated
        and not unexpected
        and not control_mismatches
        and not role_spec_mismatches
    )

    comparison_specs = (
        {
            "comparison_id": "single-C-path",
            "comparison_kind": "emission-path",
            "baseline_role": "imagemask-C",
            "candidate_role": "devicecmyk-C",
            "held_constant": "PRN bits, geometry, C-only colorants",
            "changed_variable": (
                "single-plane imagemask versus DeviceCMYK image"
            ),
        },
        {
            "comparison_id": "overlap-CM-path",
            "comparison_kind": "emission-path",
            "baseline_role": "devicecmyk-CM",
            "candidate_role": "opm1-CM",
            "held_constant": "PRN bits, geometry, overlapping C+M colorants",
            "changed_variable": (
                "direct DeviceCMYK image versus sequential OPM1"
            ),
        },
        {
            "comparison_id": "devicecmyk-plane-content",
            "comparison_kind": "plane-content",
            "baseline_role": "devicecmyk-C",
            "candidate_role": "devicecmyk-CM",
            "held_constant": "PRN bits, geometry, DeviceCMYK image path",
            "changed_variable": "C-only versus overlapping C+M colorants",
        },
    )

    def relative_metrics(
        baseline_row: dict[str, Any],
        candidate_row: dict[str, Any],
    ) -> dict[str, Any]:
        baseline_screen = baseline_row["screen"]
        candidate_screen = candidate_row["screen"]
        excess_delta = float(
            candidate_screen[
                "off_ground_truth_excess_energy_fraction"
            ]
        ) - float(
            baseline_screen[
                "off_ground_truth_excess_energy_fraction"
            ]
        )
        baseline_correlation = baseline_screen.get(
            "authored_observed_log_power_correlation"
        )
        candidate_correlation = candidate_screen.get(
            "authored_observed_log_power_correlation"
        )
        correlation_delta = (
            None
            if (
                baseline_correlation is None
                or candidate_correlation is None
            )
            else float(candidate_correlation) - float(baseline_correlation)
        )
        peak_delta = float(
            candidate_screen["strongest_off_ground_truth_artifact"][
                "observed_to_authored_transfer_ratio"
            ]
        ) - float(
            baseline_screen["strongest_off_ground_truth_artifact"][
                "observed_to_authored_transfer_ratio"
            ]
        )
        return {
            "delta_off_ground_truth_excess_energy_fraction": excess_delta,
            "delta_authored_observed_log_power_correlation": (
                correlation_delta
            ),
            "delta_strongest_artifact_ratio": peak_delta,
            "descriptive_direction": (
                "higher-off-ground-truth-energy"
                if excess_delta > 0.0
                else "lower-off-ground-truth-energy"
                if excess_delta < 0.0
                else "equal-off-ground-truth-energy"
            ),
        }

    comparisons = []
    if valid_control:
        for spec in comparison_specs:
            baseline = control_rows[spec["baseline_role"]]
            candidate = control_rows[spec["candidate_role"]]
            if (
                baseline.get("screen", {}).get("resolved") is not True
                or candidate.get("screen", {}).get("resolved") is not True
            ):
                continue
            comparisons.append({
                **spec,
                **relative_metrics(baseline, candidate),
                "claim_scope": (
                    "single matched control; descriptive difference only, "
                    "requiring repeat prints before attribution"
                ),
            })

    if valid_control and not unresolved:
        status = "complete"
    elif valid_control:
        status = "unresolved"
    else:
        status = "invalid-control"
    return {
        "status": status,
        "valid_control": valid_control,
        "matched_set": (
            None
            if reference is None
            else reference.get("screen", {}).get("matched_set")
        ),
        "authored_pattern_sha256": (
            None
            if reference is None
            else reference.get("screen", {}).get(
                "authored_pattern_sha256"
            )
        ),
        "missing_roles": missing,
        "duplicated_roles": duplicated,
        "unexpected_roles": unexpected,
        "unresolved_roles": unresolved,
        "control_mismatches": control_mismatches,
        "role_spec_mismatches": role_spec_mismatches,
        "controls": {
            role: {
                "probe_id": row.get("probe_id"),
                "status": row.get("status"),
                "emission_path": row.get(
                    "screen", {}
                ).get("emission_path"),
                "authored_planes": row.get(
                    "screen", {}
                ).get("authored_planes"),
                "screen": row.get("screen"),
            }
            for role, row in sorted(control_rows.items())
        },
        "comparisons": comparisons,
        "scope": (
            "descriptive matched-PRN controls; path comparisons hold "
            "colorants fixed, while the plane-content comparison is "
            "explicitly not labeled as a path effect"
        ),
    }


def summarize_contrast_ratios(
    probes: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Fine/coarse grating contrast ratios from the authored rulers (W10).

    density_separation(g2 @ 600 grid) / density_separation(g2 @ 300 grid),
    per plane and orientation: contrast at a KNOWN authored frequency
    relative to the same sheet's coarse rung.  Being a same-sheet ratio it
    is scanner-gain/exposure/mode invariant — the property the absolute
    noise floor lacks.  It is NOT a gate: the ratio convolves printer MTF
    with capture MTF, and the two engines measurably differ (e031 K g2-h:
    Xerox 0.56 vs M281 0.46), so a bar would encode an engine, not a
    capture.  Use it across captures of ONE sheet (the HOWTO's rescan
    comparison), where the printer contribution is frozen.
    """
    separations: dict[tuple[str, str, int], float] = {}
    for row in probes:
        if row.get("group") != "grid-discovery" or row.get("status") != "ok":
            continue
        params = row.get("params", {})
        diagnostic = str(params.get("diagnostic", ""))
        if diagnostic not in {"g2-h", "g2-v"}:
            continue
        grid = params.get("grid")
        pattern = row.get("pattern", {})
        separation = pattern.get("density_separation")
        if (
            not isinstance(grid, (list, tuple)) or len(grid) != 2
            or grid[0] != grid[1] or separation is None
            or not pattern.get("scorable")
        ):
            continue
        key = (str(row.get("plane")), diagnostic, int(grid[0]))
        separations[key] = float(separation)
    ratios: dict[str, dict[str, Any]] = {}
    for (plane, diagnostic, grid), fine in sorted(separations.items()):
        if grid != 600:
            continue
        coarse = separations.get((plane, diagnostic, 300))
        if coarse is None or coarse <= 0.0:
            continue
        ratios.setdefault(plane, {})[diagnostic] = {
            "ratio_600_over_300": fine / coarse,
            "separation_600": fine,
            "separation_300": coarse,
        }
    return {
        "scope": (
            "printer-and-capture convolved; same-sheet cross-capture "
            "comparison only; advisory, never a gate"
        ),
        "planes": ratios,
    }
