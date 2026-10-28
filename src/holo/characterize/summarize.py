"""Conservative per-page summaries of measured fields and probes."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

import numpy as np

from .model import (
    BASE_DPI,
    CANDIDATES_BY_CODE,
    PAGE_MM,
    REQUEST_NAMES,
    SUMMARY_SCHEMA,
    discovery_candidate_codes,
)
from .statistics import extremum, tier_for_error
from .summarize_physical import (
    summarize_payload_edges,
    summarize_physical_ticks,
    summarize_registration,
    summarize_contrast_ratios,
    summarize_scanner_adequacy,
    summarize_screen_paths,
    summarize_tones,
)
from .verify import QUALIFICATION_ERROR_UPPER_MAX

SCALE_TOLERANCE = 0.02


def _grid_key(grid: Iterable[int]) -> str:
    x, y = (int(value) for value in grid)
    return f"{x}x{y}"


def _core_fields(fields: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in fields
        if row.get("family") in {"channel", "calibration", "frontier"}
        and row.get("role") != "edge-canary"
    ]


def summarize_candidates(
    fields: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in _core_fields(fields):
        grouped[int(row["candidate_code"])].append(row)

    output: list[dict[str, Any]] = []
    for code in sorted(grouped):
        candidate = CANDIDATES_BY_CODE[code]
        rows = grouped[code]
        measured = [row for row in rows if row.get("status") == "ok"]
        complete = len(measured) == len(rows) and bool(rows)
        worst_error = extremum(
            measured, lambda row: row.get("error_rate"), max)
        worst_upper = extremum(
            measured,
            lambda row: (row.get("error_wilson_95") or (None, None))[1],
            max)
        worst_window_error = extremum(
            measured,
            lambda row: row.get("window_dispersion", {}).get(
                "worst_window_error_rate"),
            max)
        worst_window_upper = extremum(
            measured,
            lambda row: row.get("window_dispersion", {}).get(
                "worst_window_wilson_upper_95"),
            max)
        minimum_information = extremum(
            measured,
            lambda row: row.get("mutual_information_bits_per_cell"), min)
        minimum_soft_information = extremum(
            measured,
            lambda row: row.get(
                "generalized_mutual_information_bits_per_cell"),
            min)
        minimum_density = extremum(
            measured,
            lambda row: row.get("empirical_information_bits_per_mm2"), min)
        usable = bool(
            complete
            and worst_upper is not None
            and worst_window_upper is not None
            and worst_upper < QUALIFICATION_ERROR_UPPER_MAX
            and worst_window_upper < QUALIFICATION_ERROR_UPPER_MAX
        )
        window_errors = np.asarray([
            float(window["error_rate"])
            for row in measured
            for window in row.get("windows", [])
            if window.get("status") == "ok"
        ])
        window_quantiles = (
            None if not window_errors.size else {
                "n_windows": int(window_errors.size),
                "p50": float(np.percentile(window_errors, 50)),
                "p90": float(np.percentile(window_errors, 90)),
                "p95": float(np.percentile(window_errors, 95)),
                "max": float(np.max(window_errors)),
            }
        )
        confusions = [
            np.asarray(row["confusion"], dtype=np.int64)
            for row in measured if row.get("confusion") is not None
        ]
        state_error_rates: list[float | None] | None = None
        worst_state_error = None
        if confusions and len(confusions) == len(measured):
            pooled = sum(confusions[1:], start=confusions[0].copy())
            totals = pooled.sum(axis=1)
            state_error_rates = [
                None if total == 0
                else float(1.0 - pooled[state, state] / total)
                for state, total in enumerate(totals)
            ]
            known = [value for value in state_error_rates
                     if value is not None]
            worst_state_error = max(known) if known else None
        output.append({
            "candidate_code": code,
            "candidate_id": candidate.candidate_id,
            "page_kind": candidate.page_kind,
            "grid_dpi": list(candidate.grid_dpi),
            "cell_dots": list(candidate.cell_dots),
            "cell_pitch_mm": list(candidate.pitch_mm),
            "alphabet": candidate.alphabet,
            "states": list(candidate.states),
            "state_planes": [
                list(state_planes)
                for state_planes in candidate.state_planes
            ],
            "bit_names": list(candidate.bit_names),
            "planes": list(candidate.planes),
            "emission_path": candidate.emission_path,
            "symbol_shape": candidate.symbol_shape,
            "role": candidate.role,
            "n_fields_expected": len(rows),
            "n_fields_measured": len(measured),
            "evidence_complete": complete,
            "worst_error_rate": worst_error,
            "worst_error_wilson_upper_95": worst_upper,
            "worst_window_error_rate": worst_window_error,
            "worst_window_wilson_upper_95": worst_window_upper,
            "window_error_quantiles": window_quantiles,
            "state_error_rates": state_error_rates,
            "worst_state_error_rate": worst_state_error,
            "minimum_mutual_information_bits_per_cell": minimum_information,
            "minimum_generalized_mutual_information_bits_per_cell": (
                minimum_soft_information
            ),
            "minimum_empirical_information_bits_per_mm2": minimum_density,
            "tier": tier_for_error(
                None
                if worst_error is None or worst_window_error is None
                else max(worst_error, worst_window_error)
            ),
            "provisional_usable": usable,
            "field_ids": [row["field_id"] for row in rows],
            "failures": [
                {
                    "field_id": row["field_id"],
                    "status": row.get("status"),
                    "reason": row.get("reason"),
                }
                for row in rows if row.get("status") != "ok"
            ],
        })
    return output


def summarize_grid_rulers(
    probes: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[
        str, dict[str, dict[str, dict[str, Any]]]
    ] = defaultdict(lambda: defaultdict(dict))
    for row in probes:
        if row.get("group") != "grid-discovery":
            continue
        parts = str(row["probe_id"]).split("/")
        if len(parts) != 4:
            continue
        grid, plane, diagnostic = parts[1:]
        pattern = row.get("pattern", {})
        passed = bool(
            row.get("status") == "ok"
            and pattern.get("scorable")
            and float(pattern.get("correlation", -1.0)) >= 0.45
            and float(pattern.get("dot_error_rate", 1.0)) < 0.20
        )
        grouped[grid][plane][diagnostic] = {
            "passed": passed,
            "correlation": pattern.get("correlation"),
            "dot_error_rate": pattern.get("dot_error_rate"),
            "density_separation": pattern.get("density_separation"),
            "probe_id": row["probe_id"],
            "params": row.get("params", {}),
        }
    output = {}
    for grid, plane_rows in sorted(grouped.items()):
        planes = {}
        for plane, diagnostics in sorted(plane_rows.items()):
            g1_complete = {"g1-v", "g1-h"} <= set(diagnostics)
            g2_complete = {"g2-v", "g2-h"} <= set(diagnostics)
            g1_resolved = bool(
                g1_complete
                and diagnostics["g1-v"]["passed"]
                and diagnostics["g1-h"]["passed"]
            )
            g2_resolved = bool(
                g2_complete
                and diagnostics["g2-v"]["passed"]
                and diagnostics["g2-h"]["passed"]
            )
            finest = (
                "1-on/1-off" if g1_resolved
                else "2-on/2-off" if g2_resolved
                else None
            )
            expected = {
                "g1-v", "g1-h", "g2-v", "g2-h", "dots", "line-pair"
            }
            planes[plane] = {
                "diagnostics": diagnostics,
                "complete": set(diagnostics) == expected,
                "g1_complete": g1_complete,
                "g2_complete": g2_complete,
                "g1_resolved": g1_resolved,
                "g2_resolved": g2_resolved,
                "finest_resolved_pattern": finest,
                "addressable": bool(g1_resolved or g2_resolved),
            }
        output[grid] = {
            "planes": planes,
            "complete": bool(
                planes and all(row["complete"] for row in planes.values())
            ),
            "addressable": bool(
                planes and all(
                    row["addressable"] for row in planes.values()
                )
            ),
        }
    return output


def summarize_dpi_and_cells(
    candidates: Iterable[dict[str, Any]],
    grid_rulers: dict[str, dict[str, Any]],
    geometry: dict[str, Any],
) -> dict[str, Any]:
    scale_x = float(geometry["scale_ratio_x"])
    scale_y = float(geometry["scale_ratio_y"])
    scale_ok = bool(
        abs(scale_x - 1.0) <= SCALE_TOLERANCE
        and abs(scale_y - 1.0) <= SCALE_TOLERANCE
    )
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    candidate_rows = list(candidates)
    for row in candidate_rows:
        grouped[tuple(int(value) for value in row["grid_dpi"])].append(row)

    equal_pitch_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for row in candidate_rows:
        pitch = row["cell_pitch_mm"]
        measurement_signature = (
            str(row["page_kind"]),
            str(row["alphabet"]),
            tuple(str(value) for value in row["states"]),
            tuple(
                tuple(str(value) for value in state_planes)
                for state_planes in row["state_planes"]
            ),
            tuple(str(value) for value in row["bit_names"]),
            tuple(str(value) for value in row["planes"]),
            str(row["emission_path"]),
            str(row["symbol_shape"]),
            str(row["role"]),
        )
        key = (
            int(round(float(pitch[0]) * 1_000_000)),
            int(round(float(pitch[1]) * 1_000_000)),
            *measurement_signature,
        )
        equal_pitch_groups[key].append(row)
    equal_pitch_controls = []
    for key, rows in sorted(equal_pitch_groups.items()):
        distinct_grids = {
            tuple(int(value) for value in row["grid_dpi"]) for row in rows
        }
        if len(distinct_grids) < 2:
            continue
        ordered = sorted(
            rows,
            key=lambda row: (
                int(row["grid_dpi"][0]) * int(row["grid_dpi"][1]),
                row["grid_dpi"],
            ),
        )
        baseline = next(
            (
                row for row in ordered
                if row["worst_error_rate"] is not None
            ),
            None,
        )
        comparisons = []
        for row in ordered:
            if baseline is None or row["worst_error_rate"] is None:
                relationship = "unmeasurable"
            else:
                delta = (
                    float(row["worst_error_rate"])
                    - float(baseline["worst_error_rate"])
                )
                relationship = (
                    "better" if delta < -0.01
                    else "worse" if delta > 0.01
                    else "equivalent-within-1pct"
                )
            comparisons.append({
                "candidate_id": row["candidate_id"],
                "grid_dpi": row["grid_dpi"],
                "cell_dots": row["cell_dots"],
                "symbol_shape": row["symbol_shape"],
                "state_planes": row["state_planes"],
                "worst_error_rate": row["worst_error_rate"],
                "provisional_usable": row["provisional_usable"],
                "relative_to_lowest_measured_grid": relationship,
            })
        measured_errors = [
            float(row["worst_error_rate"]) for row in ordered
            if row["worst_error_rate"] is not None
        ]
        equal_pitch_controls.append({
            "cell_pitch_mm": [key[0] / 1_000_000, key[1] / 1_000_000],
            "position_variance_worst_error_spread": (
                None if len(measured_errors) < 2
                else max(measured_errors) - min(measured_errors)
            ),
            "measurement_signature": {
                "page_kind": key[2],
                "alphabet": key[3],
                "states": list(key[4]),
                "state_planes": [list(row) for row in key[5]],
                "bit_names": list(key[6]),
                "planes": list(key[7]),
                "emission_path": key[8],
                "symbol_shape": key[9],
                "role": key[10],
            },
            "comparisons": comparisons,
        })

    grids = []
    highest: tuple[int, int] | None = None
    for grid in sorted(grouped, key=lambda value: (value[0] * value[1], value)):
        rows = grouped[grid]
        ruler = grid_rulers.get(_grid_key(grid))
        def ruler_passes(row: dict[str, Any]) -> bool:
            if ruler is None:
                return False
            planes = ruler.get("planes", {})
            required = CANDIDATES_BY_CODE[
                int(row["candidate_code"])
            ].planes
            return bool(
                required
                and all(
                    plane in planes and planes[plane]["addressable"]
                    for plane in required
                )
            )

        usable = [
            row for row in rows
            if row["provisional_usable"] and ruler_passes(row) and scale_ok
        ]
        any_addressable_candidate = any(ruler_passes(row) for row in rows)
        by_alphabet: dict[str, dict[str, Any]] = {}
        for alphabet in sorted({str(row["alphabet"]) for row in rows}):
            choices = [
                row for row in usable if row["alphabet"] == alphabet
            ]
            if choices:
                smallest = min(
                    choices,
                    key=lambda row: (
                        float(row["cell_pitch_mm"][0])
                        * float(row["cell_pitch_mm"][1]),
                        row["cell_dots"],
                    ),
                )
                by_alphabet[alphabet] = {
                    "candidate_id": smallest["candidate_id"],
                    "cell_dots": smallest["cell_dots"],
                    "cell_pitch_mm": smallest["cell_pitch_mm"],
                    "worst_error_rate": smallest["worst_error_rate"],
                    "worst_error_wilson_upper_95": (
                        smallest["worst_error_wilson_upper_95"]
                    ),
                }
        if usable:
            highest = grid
        grids.append({
            "authored_grid_dpi": list(grid),
            "tested_candidate_count": len(rows),
            "ruler": (
                ruler if ruler is not None
                else {"complete": False, "addressable": None,
                      "reason": "no ruler on this page kind"}
            ),
            "scale_status": "nominal" if scale_ok else "scaled",
            "scale_ratio_xy": [scale_x, scale_y],
            "usable_candidate_count": len(usable),
            "usable_candidate_codes": [
                int(row["candidate_code"]) for row in usable
            ],
            "smallest_usable_cell_by_alphabet": by_alphabet,
            "status": (
                "usable" if usable
                else "scaled" if not scale_ok
                else (
                    "ruler_missing"
                    if ruler is None
                    else "not_addressable"
                ) if not any_addressable_candidate
                else "no_qualified_cell"
            ),
        })
    return {
        "scale_tolerance_fraction": SCALE_TOLERANCE,
        "physical_scale_status": "nominal" if scale_ok else "scaled",
        "highest_useful_authored_grid_dpi": (
            None if highest is None else list(highest)
        ),
        "warning": (
            "This is the highest useful authored grid on this exact "
            "request/path/media/scanner footing, not manufacturer-native DPI."
        ),
        "equal_physical_pitch_controls": equal_pitch_controls,
        "grids": grids,
    }


TIER_DEFINITIONS = {
    "solid": "error_rate < 0.01",
    "marginal": "0.01 <= error_rate < 0.08",
    "fragile": "0.08 <= error_rate < 0.20",
    "collapsed": "error_rate >= 0.20",
    "unmeasurable": "no finite error measurement",
    "provisional_usable": (
        "evidence complete AND whole-field and worst-window Wilson "
        "uppers < 0.08"
    ),
}

# e-IRA mother-code ladder rates (FEC-DESIGN; k/4096).  Local constants:
# the characterize instrument keeps its import firewall from holo.core.
LDPC_RUNG_RATES = {
    "r0550": 2240 / 4096,
    "r0625": 2560 / 4096,
    "r0700": 2880 / 4096,
    "r0775": 3200 / 4096,
    "r0859": 3520 / 4096,
}

CAPACITY_MARGINS_MM = (4.5, 5.0, 6.0)


def _binary_entropy(p: float) -> float:
    clamped = min(max(float(p), 0.0), 0.5)
    if clamped in (0.0,):
        return 0.0
    return float(
        -clamped * math.log2(clamped)
        - (1.0 - clamped) * math.log2(1.0 - clamped)
    )


def summarize_rung_planning(
    candidates: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Rung -> window-yield -> net-density ESTIMATE table (workplan W4c).

    Tails price the fountain instead of gating rungs: a window supports a
    rung when its hard-decision cell information 1-h2(p) clears the rate;
    the failing fraction becomes expected tile erasures the fountain
    reserve must cover.  Single-copy, hard-decision, supervised — binding
    rung freezes stay with calibrate/combine.
    """

    rows = []
    for row in candidates:
        quantiles = row.get("window_error_quantiles")
        if not row.get("provisional_usable") or not quantiles:
            continue
        candidate = CANDIDATES_BY_CODE[int(row["candidate_code"])]
        per_rung = {}
        for rung, rate in LDPC_RUNG_RATES.items():
            supported = {
                name: bool(1.0 - _binary_entropy(quantiles[name]) >= rate)
                for name in ("p50", "p95", "max")
            }
            margin_p50 = (
                1.0 - _binary_entropy(quantiles["p50"]) - rate
            )
            per_rung[rung] = {
                "rate": rate,
                "hard_decision_margin_at_p50": margin_p50,
                "supported_at": supported,
                "net_bits_per_mm2_at_full_yield": (
                    rate * candidate.alphabet_bits
                    * candidate.cells_per_mm2
                ),
            }
        rows.append({
            "candidate_code": int(row["candidate_code"]),
            "candidate_id": row["candidate_id"],
            "window_error_quantiles": quantiles,
            "rungs": per_rung,
        })
    return {
        "scope": (
            "hard-decision single-copy ESTIMATE: window supports a rung "
            "iff 1-h2(window error) >= rate; net density = rate x yield "
            "x alphabet bits x cells/mm2 with tile failures priced as "
            "fountain erasures, never a qualification"
        ),
        "rows": rows,
    }


def summarize_capacity_by_margin(
    candidates: Iterable[dict[str, Any]],
    clip_by_edge: dict[str, Any] | None,
) -> dict[str, Any]:
    """Capacity as a function of a CHOSEN uniform margin (workplan W3c).

    Margin policy is a devices/profiles decision made downstream; the
    analyzer reports the arithmetic at standard margins plus the measured
    clip line, and never picks one.
    """

    margins: list[dict[str, Any]] = [
        {"margin_mm": value, "source": "standard"}
        for value in CAPACITY_MARGINS_MM
    ]
    clips = [
        float(value)
        for value in (clip_by_edge or {}).values()
        if value is not None
    ]
    if clip_by_edge and len(clips) == 4:
        margins.append({
            "margin_mm": math.ceil(max(clips) * 10.0) / 10.0,
            "source": "measured-clip-worst-edge",
        })
    usable = [
        row for row in candidates
        if row.get("provisional_usable")
        and row.get("minimum_empirical_information_bits_per_mm2")
        is not None
    ]
    table = []
    for entry in sorted(margins, key=lambda row: row["margin_mm"]):
        margin = float(entry["margin_mm"])
        width = PAGE_MM[0] - 2.0 * margin
        height = PAGE_MM[1] - 2.0 * margin
        area = max(0.0, width) * max(0.0, height)
        table.append({
            **entry,
            "width_mm": width,
            "height_mm": height,
            "area_mm2": area,
            "candidates": [
                {
                    "candidate_code": int(row["candidate_code"]),
                    "candidate_id": row["candidate_id"],
                    "empirical_information_bits": (
                        float(row[
                            "minimum_empirical_information_bits_per_mm2"
                        ]) * area
                    ),
                    "raw_alphabet_bits": (
                        CANDIDATES_BY_CODE[int(row["candidate_code"])]
                        .alphabet_bits
                        * CANDIDATES_BY_CODE[int(row["candidate_code"])]
                        .cells_per_mm2
                        * area
                    ),
                }
                for row in usable
            ],
        })
    return {
        "scope": (
            "uniform-margin arithmetic before production furniture, "
            "coding, fountain reserve, and archive margin; margin "
            "POLICY is chosen downstream against these numbers"
        ),
        "margins": table,
    }


def summarize_registration_map(
    page: dict[str, Any],
    geometry: dict[str, Any],
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Page-wide displacement observations after the corner affine (W2b).

    Sources: registered edge ticks (print wander + affine extrapolation),
    bounded-translation pattern probes, and internal plus marks.  This is
    the supervised registration measurement the retired tick rule was
    implicitly (and destructively) sensitive to.
    """

    positions = {
        str(row["probe_id"]): row for row in page.get("probes", [])
    }
    dot_mm = 25.4 / BASE_DPI
    entries = []
    for row in probes:
        record = positions.get(str(row.get("probe_id", "")))
        if record is None or row.get("status") != "ok":
            continue
        center = [
            (float(record["x_layout_dots"])
             + float(record.get("w_layout_dots", 0.0)) / 2.0) * dot_mm,
            (float(record["y_layout_dots"])
             + float(record.get("h_layout_dots", 0.0)) / 2.0) * dot_mm,
        ]
        tick = row.get("tick")
        if (
            isinstance(tick, dict)
            and tick.get("displacement_layout_dots") is not None
        ):
            dx, dy = tick["displacement_layout_dots"]
            entries.append({
                "source": "edge-tick",
                "probe_id": row["probe_id"],
                "position_mm": center,
                "dx_layout_dots": float(dx),
                "dy_layout_dots": float(dy),
            })
            continue
        pattern = row.get("pattern")
        if (
            isinstance(pattern, dict)
            and pattern.get("scorable")
            and pattern.get("translation_source_dots") is not None
            # Weak-correlation fits saturate the translation search, and
            # PERIODIC patterns (gratings/checkers/rails) are ambiguous
            # displacement witnesses modulo their period: only aperiodic
            # PRND content (coverage-parameterized) testifies here.
            and float(pattern.get("correlation") or 0.0) >= 0.45
            and "coverage" in row.get("params", {})
        ):
            stride = float(row.get("sample_stride_source_dots", 1))
            dpi = row.get("source_dpi", [BASE_DPI, BASE_DPI])
            shift_x, shift_y = pattern["translation_source_dots"]
            entries.append({
                "source": "pattern",
                "probe_id": row["probe_id"],
                "position_mm": center,
                "dx_layout_dots": (
                    float(shift_x) * stride * BASE_DPI / float(dpi[0])
                ),
                "dy_layout_dots": (
                    float(shift_y) * stride * BASE_DPI / float(dpi[1])
                ),
            })
    for mark in geometry.get("internal_plus", {}).get("marks", []):
        if not mark.get("ok"):
            continue
        entries.append({
            "source": "plus-mark",
            "probe_id": f"plus/{mark.get('index')}",
            "position_mm": [
                float(mark["x_layout_dots"]) * dot_mm,
                float(mark["y_layout_dots"]) * dot_mm,
            ],
            "dx_layout_dots": float(mark["dx_layout_dots"]),
            "dy_layout_dots": float(mark["dy_layout_dots"]),
        })
    magnitudes = [
        math.hypot(row["dx_layout_dots"], row["dy_layout_dots"])
        for row in entries
    ]
    return {
        "n_observations": len(entries),
        "max_displacement_layout_dots": (
            max(magnitudes) if magnitudes else None
        ),
        "observations": entries,
    }


def summarize_probes(probes: list[dict[str, Any]]) -> dict[str, Any]:
    quiet = [
        row for row in probes if row.get("group") == "scanner-adequacy"
    ]
    morphology = [
        row for row in probes if row.get("group") == "morphology"
    ]
    screens = [
        row for row in probes if row.get("group") == "screen"
    ]
    transport_geometry = [
        row for row in probes if row.get("group") == "transport-geometry"
    ]
    geometry_by_axis: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unexpected_geometry = []
    for row in transport_geometry:
        axis = row.get("params", {}).get("axis")
        if axis in {"x", "y"}:
            geometry_by_axis[str(axis)].append(row)
        else:
            unexpected_geometry.append(row.get("probe_id"))
    geometry_rails = {
        axis: (
            rows[0] if len(rows) == 1 else None
        )
        for axis in ("x", "y")
        for rows in (geometry_by_axis.get(axis, []),)
    }
    missing_geometry_axes = [
        axis for axis in ("x", "y") if not geometry_by_axis.get(axis)
    ]
    duplicated_geometry_axes = [
        axis for axis, rows in geometry_by_axis.items() if len(rows) > 1
    ]
    valid_geometry_axes = [
        axis for axis, row in geometry_rails.items()
        if (
            row is not None
            and row.get("status") == "ok"
            and row.get("phase_rail", {}).get("valid") is True
        )
    ]
    if not transport_geometry:
        geometry_status = "missing"
    elif (
        missing_geometry_axes
        or duplicated_geometry_axes
        or unexpected_geometry
    ):
        geometry_status = "partial"
    else:
        geometry_status = "complete"
    selectivity = []
    for row in probes:
        if row.get("group") != "color-selectivity":
            continue
        plane = str(row["plane"])
        medians = row.get("channel_density_medians", {})
        intended = medians.get(plane)
        off_target = [
            float(medians[name])
            for name in "CMY"
            if name != plane and name in medians
        ]
        selectivity.append({
            "probe_id": row["probe_id"],
            "plane": plane,
            "status": row.get("status"),
            "channel_density_medians": medians,
            "intended_minus_worst_other_density": (
                None if intended is None or not off_target
                else float(intended) - max(off_target)
            ),
        })
    return {
        "tone_response": summarize_tones(probes),
        "tone_profiles": [
            row for row in probes
            if (
                row.get("group") == "tone"
                and row.get("kind") == "profile_tone"
            )
        ],
        "plane_registration": summarize_registration(probes),
        "physical_ink_extent": summarize_physical_ticks(probes),
        "scanner_adequacy": quiet,
        "scanner_adequacy_summary": summarize_scanner_adequacy(probes),
        "capture_contrast_ratios": summarize_contrast_ratios(probes),
        "morphology": morphology,
        "screening": summarize_screen_paths(screens),
        "color_selectivity": selectivity,
        "grid_rulers": summarize_grid_rulers(probes),
        "transport_geometry": {
            "group": "transport-geometry",
            "status": geometry_status,
            "valid": (
                geometry_status == "complete"
                and set(valid_geometry_axes) == {"x", "y"}
            ),
            "rails": geometry_rails,
            "valid_axes": valid_geometry_axes,
            "missing_axes": missing_geometry_axes,
            "duplicated_axes": duplicated_geometry_axes,
            "unexpected_axis_probe_ids": unexpected_geometry,
        },
    }


def build_page_summary(
    *,
    page: dict[str, Any],
    geometry: dict[str, Any],
    fields: list[dict[str, Any]],
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = summarize_candidates(fields)
    diagnostics = summarize_probes(probes)
    payload_extent = summarize_payload_edges(fields, candidates)
    clip_by_edge = diagnostics["physical_ink_extent"].get(
        "printable_clip_mm"
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "stage": page["stage"],
        "kind": page["kind"],
        "copy_index": page["copy_index"],
        "request_code": page["request_code"],
        "request": page["request"],
        "tier_definitions": TIER_DEFINITIONS,
        "candidate_results": candidates,
        "dpi_and_cells": summarize_dpi_and_cells(
            candidates,
            diagnostics["grid_rulers"],
            geometry,
        ),
        "payload_extent": payload_extent,
        "capacity_by_margin_mm": summarize_capacity_by_margin(
            candidates, clip_by_edge
        ),
        "rung_planning": summarize_rung_planning(candidates),
        "registration_map": summarize_registration_map(
            page, geometry, probes
        ),
        "diagnostics": diagnostics,
    }
