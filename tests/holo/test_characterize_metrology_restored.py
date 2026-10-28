from __future__ import annotations

import hashlib

import numpy as np

import holo.characterize.fields as fields_module
import holo.characterize.probes as probes_module
import holo.characterize.sampling as sampling_module
from holo.characterize.diagnostics import screen_fingerprint
from holo.characterize.fields import _window_specs, measure_field
from holo.characterize.probes import measure_probe
from holo.characterize.sampling import _sample_plane
from holo.characterize.model import CANDIDATES_BY_CODE
from holo.characterize.patterns import field_states
from holo.characterize.summarize import (
    summarize_candidates,
    summarize_dpi_and_cells,
    summarize_grid_rulers,
    summarize_probes,
)
from holo.characterize.summarize_physical import (
    summarize_scanner_adequacy,
    summarize_screen_paths,
)
from holo.characterize.raster import RasterSource
from holo.characterize.statistics import generalized_mutual_information


def _candidate(
    *,
    grid: tuple[int, int],
    cell: tuple[int, int],
    shape: str = "solid",
):
    return next(
        candidate for candidate in CANDIDATES_BY_CODE.values()
        if candidate.page_kind == "bw"
        and candidate.grid_dpi == grid
        and candidate.cell_dots == cell
        and candidate.alphabet == "K2"
        and candidate.symbol_shape == shape
    )


def test_physical_windows_cover_once_and_expand_only_for_support() -> None:
    ordinary = _candidate(grid=(600, 600), cell=(2, 2))
    specs = _window_specs(342, 283, ordinary)
    coverage = np.zeros((283, 342), np.uint8)
    for row in specs:
        y0, y1, x0, x1 = row["bounds_yx_cells"]
        coverage[y0:y1, x0:x1] += 1
        assert max(row["span_mm"]) <= 4.7
        assert row["expanded_for_support"] is False
    assert np.all(coverage == 1)

    coarse = _candidate(grid=(300, 300), cell=(6, 6))
    coarse_specs = _window_specs(57, 47, coarse)
    assert all(row["expanded_for_support"] for row in coarse_specs)
    assert max(max(row["span_mm"]) for row in coarse_specs) < 6.2


def test_wide_phase_fallback_recovers_a_two_cell_discontinuity() -> None:
    candidate = _candidate(grid=(600, 600), cell=(2, 2))
    nx, ny = 110, 50
    field = {
        "field_id": "test/two-window-phase",
        "candidate_code": candidate.code,
        "nx": nx,
        "ny": ny,
        "x_layout_dots": 50.0,
        "y_layout_dots": 50.0,
        "w_layout_dots": nx * 2.0,
        "h_layout_dots": ny * 2.0,
        "copy_index": 0,
        "stage": "calibration",
        "kind": "bw",
        "family": "calibration",
        "role": "calibration",
        "position": "test",
    }
    states = field_states(field, candidate)
    field["state_sha256"] = hashlib.sha256(states.tobytes()).hexdigest()
    image = np.full((250, 350), 255, np.uint8)
    for cell_y in range(ny):
        for cell_x in range(nx):
            if not states[cell_y, cell_x]:
                continue
            shift = 0 if cell_x < 55 else 5
            x0 = 50 + 2 * cell_x + shift
            y0 = 50 + 2 * cell_y + shift
            image[y0:y0 + 2, x0:x0 + 2] = 0

    result = measure_field(
        RasterSource(image),
        np.asarray(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
        field,
    )

    assert result["status"] == "ok"
    assert result["n_windows_expected"] == 2
    first, second = result["windows"]
    assert first["phase"]["K"]["search_mode"] == "wide-initial"
    assert second["phase"]["K"]["search_mode"] == "wide-fallback"
    assert second["phase"]["K"]["wide_fallback_reason"] is not None
    assert min(second["phase"]["K"]["offset_cells"]) > 1.9
    assert second["phase"]["K"]["certify_error_rate"] == 0.0


def test_non_solid_sampling_integrates_the_authored_motif(
    monkeypatch,
) -> None:
    candidate = _candidate(
        grid=(600, 600), cell=(2, 2), shape="diagonal"
    )
    observed: dict[str, np.ndarray] = {}

    def fake_sample(_source, _affine, x, y):
        xx, yy = np.broadcast_arrays(x, y)
        observed["x"] = xx.copy()
        observed["y"] = yy.copy()
        return np.full(xx.shape + (3,), 0.1, np.float32)

    for module in (sampling_module, fields_module, probes_module):
        if hasattr(module, "sample_layout_points"):
            monkeypatch.setattr(
                module, "sample_layout_points", fake_sample
            )
    values = _sample_plane(
        object(),
        np.eye(2, 3),
        np.asarray([10.0]),
        np.asarray([20.0]),
        plane="K",
        candidate=candidate,
        pitch_x=2.0,
        pitch_y=2.0,
    )

    assert observed["x"].shape == (1, 2)
    assert sorted(observed["x"].ravel()) == [9.5, 10.5]
    assert sorted(observed["y"].ravel()) == [19.5, 20.5]
    assert np.allclose(values, 1.0)


def test_profile_tone_retains_params_and_declared_axis_trace() -> None:
    width, height = 80, 20
    x0 = y0 = 10
    image = np.full((60, 120), 255, np.uint8)
    for x in range(x0, x0 + width):
        image[y0:y0 + height, x] = round(240 - 1.5 * (x - x0))
    probe = {
        "probe_id": "tone/K/profile",
        "kind": "profile_tone",
        "group": "tone",
        "plane": "K",
        "params": {
            "coverage": 0.5,
            "axis": "x",
            "mode": "fixed-profile",
            "station": "test",
        },
        "seed_label": "test-profile",
        "w_source_dots": width,
        "h_source_dots": height,
        "source_dpi": [600, 600],
        "x_source_dots": x0,
        "y_source_dots": y0,
        "x_layout_dots": x0,
        "y_layout_dots": y0,
        "w_layout_dots": width,
        "h_layout_dots": height,
    }

    result = measure_probe(
        RasterSource(image),
        np.asarray(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
        probe,
    )

    assert result["params"] == probe["params"]
    profile = result["profile"]
    assert profile["axis"] == "x"
    assert profile["n_bins"] == width
    assert len(profile["density_bins"]) == width
    assert len(profile["authored_coverage_bins"]) == width
    assert np.all(np.diff(profile["axis_position_page_mm"]) > 0)
    assert profile["linear_slope_density_per_mm"] > 0


def _measure_phase_rail(
    axis: str,
    shift_source_dots: np.ndarray,
    *,
    blank: bool = False,
) -> dict:
    long_side = len(shift_source_dots)
    cross_side = 30
    width, height = (
        (long_side, cross_side)
        if axis == "x"
        else (cross_side, long_side)
    )
    x0 = y0 = 30
    probe = {
        "probe_id": f"geometry/phase-{axis}",
        "kind": "phase_rail",
        "group": "transport-geometry",
        "plane": "K",
        "params": {
            "axis": axis,
            "orientation": (
                "vertical_lines" if axis == "x"
                else "horizontal_lines"
            ),
            "on_dots": 3,
            "off_dots": 3,
        },
        "seed_label": f"test-phase-{axis}",
        "w_source_dots": width,
        "h_source_dots": height,
        "source_dpi": [600, 600],
        "x_source_dots": x0,
        "y_source_dots": y0,
        "x_layout_dots": x0,
        "y_layout_dots": y0,
        "w_layout_dots": width,
        "h_layout_dots": height,
    }
    image = np.ones((height + 60, width + 60), np.float32)
    if not blank:
        positions = np.arange(long_side, dtype=np.float64) + 0.5
        ink = ((positions - shift_source_dots) % 6.0) < 3.0
        reflectance = np.where(ink, 0.12, 0.94)
        if axis == "x":
            image[y0:y0 + height, x0:x0 + width] = reflectance[None, :]
        else:
            image[y0:y0 + height, x0:x0 + width] = reflectance[:, None]
    return measure_probe(
        RasterSource(image),
        np.asarray(((1.0, 0.0, -0.5), (0.0, 1.0, -0.5))),
        probe,
    )


def test_phase_rails_report_local_step_and_gradual_transport_drift() -> None:
    length = 720
    positions = np.arange(length, dtype=np.float64) + 0.5
    baseline = _measure_phase_rail("x", np.zeros(length))
    stepped = _measure_phase_rail(
        "x", np.where(positions < length / 2.0, 0.0, 2.0)
    )
    gradual = _measure_phase_rail("y", 2.0 * positions / length)

    baseline_trace = baseline["phase_rail"]
    stepped_trace = stepped["phase_rail"]
    gradual_trace = gradual["phase_rail"]
    assert baseline_trace["valid"] is True
    assert baseline_trace["phase_span_source_dots"] < 0.05
    for trace in (stepped_trace, gradual_trace):
        assert trace["valid"] is True
        assert trace["phase_drift_source_dots"] > 1.5
        assert trace["phase_span_source_dots"] > 1.5
        assert trace["minimum_valid_correlation"] > 0.5
        assert all(point["valid"] for point in trace["trace"])
        assert all(
            point["density_p05_p95"][1]
            > point["density_p05_p95"][0]
            for point in trace["trace"]
        )
        page_positions = [
            point["axis_position_page_mm"] for point in trace["trace"]
        ]
        assert np.all(np.diff(page_positions) > 0.0)
    stepped_phases = [
        point["phase_source_dots_unwrapped"]
        for point in stepped_trace["trace"]
    ]
    gradual_phases = [
        point["phase_source_dots_unwrapped"]
        for point in gradual_trace["trace"]
    ]
    assert stepped_phases[:2] == [0.0, 0.0]
    assert np.allclose(stepped_phases[2:], 2.0)
    assert np.all(np.diff(gradual_phases) >= -1e-12)

    summary = summarize_probes([stepped, gradual])[
        "transport_geometry"
    ]
    assert summary["status"] == "complete"
    assert summary["valid"] is True
    assert set(summary["rails"]) == {"x", "y"}
    assert summary["rails"]["x"]["probe_id"] == "geometry/phase-x"
    assert summary["rails"]["y"]["probe_id"] == "geometry/phase-y"


def test_phase_rail_invalid_contrast_and_missing_axis_are_explicit() -> None:
    invalid_x = _measure_phase_rail(
        "x", np.zeros(720, dtype=np.float64), blank=True
    )

    rail = invalid_x["phase_rail"]
    assert invalid_x["status"] == "ok"
    assert rail["valid"] is False
    assert rail["reason"] == "no-valid-phase-segments"
    assert rail["phase_drift_source_dots"] is None
    assert rail["phase_span_source_dots"] is None
    assert rail["n_valid_segments"] == 0
    assert all(not point["valid"] for point in rail["trace"])

    summary = summarize_probes([invalid_x])["transport_geometry"]
    assert summary["status"] == "partial"
    assert summary["valid"] is False
    assert summary["missing_axes"] == ["y"]
    assert summary["valid_axes"] == []
    assert summary["rails"]["x"] is invalid_x
    assert summary["rails"]["y"] is None

    missing = summarize_probes([])["transport_geometry"]
    assert missing["status"] == "missing"
    assert missing["valid"] is False
    assert missing["missing_axes"] == ["x", "y"]


def _screen_row(
    role: str,
    path: str,
    planes: tuple[str, ...],
    measurement: dict,
    *,
    digest: str = "ab" * 32,
) -> dict:
    return {
        "probe_id": f"screen/path/{role}",
        "kind": "entropy_field",
        "group": "screen",
        "plane": "K",
        "status": "ok",
        "screen": {
            **measurement,
            "matched_set": "prn-path-v1",
            "control_role": role,
            "emission_path": path,
            "measurement_feature": "luma-density",
            "authored_pattern_sha256": digest,
            "authored_shape_yx": [256, 256],
            "authored_dpi": [600, 600],
            "authored_planes": list(planes),
            "physical_extent_mm": [
                256 / 600 * 25.4,
                256 / 600 * 25.4,
            ],
        },
    }


def test_screen_spectrum_is_authored_relative_and_path_summary_is_restrained(
) -> None:
    rng = np.random.default_rng(91)
    truth = (rng.random((256, 256)) < 0.5).astype(np.float64)
    baseline_observed = 0.1 + 0.8 * truth
    yy, xx = np.indices(truth.shape, dtype=np.float64)
    artifact_observed = baseline_observed + 0.25 * np.cos(
        2.0 * np.pi * (80.0 * xx / 600.0 + 60.0 * yy / 600.0)
    )
    baseline = screen_fingerprint(
        baseline_observed, truth, 600.0, 600.0
    )
    artifact = screen_fingerprint(
        artifact_observed, truth, 600.0, 600.0
    )

    assert baseline["resolved"] is True
    assert artifact["resolved"] is True
    assert baseline["off_ground_truth_excess_energy_fraction"] < 1e-10
    assert artifact["off_ground_truth_excess_energy_fraction"] > 0.20
    peak = artifact["strongest_off_ground_truth_artifact"]
    assert 95.0 < peak["lpi"] < 104.0
    assert 34.0 < peak["angle_deg"] < 39.0
    assert peak["observed_to_authored_transfer_ratio"] > 100.0
    assert "not a universal printer-screen verdict" in (
        artifact["interpretation"]
    )

    rows = [
        _screen_row(
            "imagemask-C", "single-plane-imagemask", ("C",), baseline
        ),
        _screen_row(
            "devicecmyk-C", "DeviceCMYK-image", ("C",), artifact
        ),
        _screen_row(
            "devicecmyk-CM", "DeviceCMYK-image", ("C", "M"), artifact
        ),
        _screen_row(
            "opm1-CM",
            "sequential-overprint-opm1",
            ("C", "M"),
            baseline,
        ),
    ]
    summary = summarize_screen_paths(rows)

    assert summary["status"] == "complete"
    assert summary["valid_control"] is True
    assert summary["missing_roles"] == []
    assert set(summary["controls"]) == {
        "imagemask-C",
        "devicecmyk-C",
        "devicecmyk-CM",
        "opm1-CM",
    }
    comparisons = {
        row["comparison_id"]: row for row in summary["comparisons"]
    }
    device = comparisons["single-C-path"]
    assert (
        device["delta_off_ground_truth_excess_energy_fraction"] > 0.20
    )
    assert device["descriptive_direction"] == (
        "higher-off-ground-truth-energy"
    )
    assert "descriptive difference only" in device["claim_scope"]
    assert comparisons["overlap-CM-path"][
        "delta_off_ground_truth_excess_energy_fraction"
    ] < -0.20
    assert comparisons["overlap-CM-path"]["comparison_kind"] == (
        "emission-path"
    )
    assert comparisons["devicecmyk-plane-content"][
        "delta_off_ground_truth_excess_energy_fraction"
    ] == 0.0
    assert comparisons["devicecmyk-plane-content"]["comparison_kind"] == (
        "plane-content"
    )

    mismatched = list(rows)
    mismatched[1] = _screen_row(
        "devicecmyk-C",
        "DeviceCMYK-image",
        ("C",),
        artifact,
        digest="cd" * 32,
    )
    refused_control = summarize_screen_paths(mismatched)
    assert refused_control["status"] == "invalid-control"
    assert refused_control["valid_control"] is False
    assert refused_control["control_mismatches"] == ["devicecmyk-C"]
    assert refused_control["comparisons"] == []


def _adequacy_row(
    probe_id: str,
    *,
    error: float = 0.01,
    correlation: float = 0.8,
) -> dict:
    roles = {
        "scanner/c3": "solid_class_c3",
        "scanner/c2": "marginal_class_c2",
        "scanner/g2/horizontal_lines": "sampling_horizontal",
        "scanner/g2/vertical_lines": "sampling_vertical",
        "scanner/entropy": "entropy",
    }
    return {
        "probe_id": probe_id,
        "kind": "cell_field",
        "group": "scanner-adequacy",
        "status": "ok",
        "params": {"adequacy_role": roles[probe_id]},
        "pattern": {
            "scorable": True,
            "dot_error_rate": error,
            "correlation": correlation,
        },
    }


def test_scanner_adequacy_has_explicit_mode_class_verdicts() -> None:
    rows = [
        _adequacy_row("scanner/c3", error=0.02),
        _adequacy_row("scanner/c2", error=0.10),
        _adequacy_row("scanner/g2/horizontal_lines"),
        _adequacy_row("scanner/g2/vertical_lines"),
        {
            **_adequacy_row("scanner/entropy"),
            "blockiness_8px": 1.05,
        },
        {
            "probe_id": "quiet/main",
            "kind": "quiet_zone",
            "group": "scanner-adequacy",
            "status": "ok",
            "params": {"adequacy_role": "quiet"},
            "paper_noise_highpass_8bit_counts": 1.5,
        },
    ]

    healthy = summarize_scanner_adequacy(rows)
    assert healthy["status"] == "complete"
    assert healthy["verdict"] == "adequate"
    assert healthy["mode_classes"]["solid_class"]["verdict"] == "adequate"
    assert healthy["mode_classes"]["c2_class"]["verdict"] == "adequate"

    # W9 re-pointed this, deliberately, without weakening it. The test pins
    # the INDETERMINATE pathway; 0.2 counts exercised it under the old 0.5
    # indeterminate floor. Measurement since (CHARACTERIZE-WORKPLAN W9) puts
    # smoothed captures at 0.079-0.226 counts and honest ones at 0.46-0.84,
    # so 0.2 is no longer "cannot tell" — it is squarely a smoothed capture
    # and must FAIL. The indeterminate band now lives below 0.05.
    rows[-1]["paper_noise_highpass_8bit_counts"] = 0.2
    smoothed = summarize_scanner_adequacy(rows)
    assert smoothed["mode_classes"]["solid_class"]["verdict"] == "adequate"
    assert smoothed["mode_classes"]["c2_class"]["verdict"] == "inadequate"

    rows[-1]["paper_noise_highpass_8bit_counts"] = 0.03
    synthetic = summarize_scanner_adequacy(rows)
    assert synthetic["mode_classes"]["solid_class"]["verdict"] == "adequate"
    assert synthetic["mode_classes"]["c2_class"]["verdict"] == "indeterminate"


def test_grid_summary_retains_six_diagnostics_and_finest_resolution() -> None:
    rows = []
    for diagnostic in (
        "g1-v", "g1-h", "g2-v", "g2-h", "dots", "line-pair"
    ):
        rows.append({
            "probe_id": f"grid/600x600/K/{diagnostic}",
            "group": "grid-discovery",
            "status": "ok",
            "params": {"diagnostic": diagnostic},
            "pattern": {
                "scorable": True,
                "correlation": 0.9,
                "dot_error_rate": 0.01,
                "density_separation": 0.8,
            },
        })

    result = summarize_grid_rulers(rows)["600x600"]["planes"]["K"]

    assert result["complete"] is True
    assert set(result["diagnostics"]) == {
        "g1-v", "g1-h", "g2-v", "g2-h", "dots", "line-pair"
    }
    assert result["finest_resolved_pattern"] == "1-on/1-off"


def test_soft_score_gmi_uses_information_beyond_hard_confusion() -> None:
    truth = np.asarray([0, 1] * 64)
    strong = np.where(
        truth[:, None] == np.arange(2)[None, :], 4.0, -4.0
    )
    flat = np.zeros_like(strong)

    assert generalized_mutual_information(
        strong, truth
    )["bits_per_cell"] > 0.99
    assert generalized_mutual_information(
        flat, truth
    )["bits_per_cell"] == 0.0


def test_equal_pitch_controls_preserve_the_measurement_signature() -> None:
    solid_300 = _candidate(grid=(300, 300), cell=(1, 1))
    solid_600 = _candidate(grid=(600, 600), cell=(2, 2))
    diagonal_600 = _candidate(
        grid=(600, 600), cell=(2, 2), shape="diagonal"
    )

    fields = []
    for candidate in (solid_300, solid_600, diagonal_600):
        fields.append({
            "field_id": f"field/{candidate.candidate_id}",
            "candidate_code": candidate.code,
            "family": "channel",
            "role": "channel",
            "status": "ok",
            "error_rate": 0.01,
            "error_wilson_95": [0.005, 0.02],
            "window_dispersion": {
                "worst_window_error_rate": 0.01,
                "worst_window_wilson_upper_95": 0.02,
            },
            "mutual_information_bits_per_cell": 0.9,
            "generalized_mutual_information_bits_per_cell": 0.8,
            "empirical_information_bits_per_mm2": 100.0,
        })

    candidates = summarize_candidates(fields)
    diagonal = next(
        row for row in candidates
        if row["candidate_code"] == diagonal_600.code
    )
    assert diagonal["symbol_shape"] == "diagonal"
    assert diagonal["state_planes"] == [[], ["K"]]

    result = summarize_dpi_and_cells(
        candidates,
        grid_rulers={},
        geometry={"scale_ratio_x": 1.0, "scale_ratio_y": 1.0},
    )
    controls = result["equal_physical_pitch_controls"]
    solid = next(
        row for row in controls
        if row["measurement_signature"]["symbol_shape"] == "solid"
    )
    assert {
        row["candidate_id"] for row in solid["comparisons"]
    } == {solid_300.candidate_id, solid_600.candidate_id}
    assert all(
        diagonal_600.candidate_id
        not in {
            comparison["candidate_id"]
            for comparison in control["comparisons"]
        }
        for control in controls
    )


def test_local_window_collapse_cannot_qualify_a_clean_average() -> None:
    candidate = _candidate(grid=(600, 600), cell=(2, 2))
    result = summarize_candidates([{
        "field_id": "field/local-collapse",
        "candidate_code": candidate.code,
        "family": "channel",
        "role": "channel",
        "status": "ok",
        "error_rate": 0.01,
        "error_wilson_95": [0.005, 0.02],
        "window_dispersion": {
            "worst_window_error_rate": 0.50,
            "worst_window_wilson_upper_95": 0.60,
        },
        "mutual_information_bits_per_cell": 0.9,
        "generalized_mutual_information_bits_per_cell": 0.8,
        "empirical_information_bits_per_mm2": 100.0,
    }])[0]

    assert result["worst_error_wilson_upper_95"] == 0.02
    assert result["worst_window_error_rate"] == 0.50
    assert result["worst_window_wilson_upper_95"] == 0.60
    assert result["provisional_usable"] is False
