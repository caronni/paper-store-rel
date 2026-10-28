"""Forward E025 physical-channel metrology preflight."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "025-channel-metrology"
if str(EXP) not in sys.path:
    sys.path.insert(0, str(EXP))

import analyze_e025 as analyzer  # noqa: E402
import e025_common as ec  # noqa: E402
import emit_e025 as emitter  # noqa: E402
import profile_e025 as profiler  # noqa: E402
from paperholo.metrology import GridSpec  # noqa: E402


def test_fixed_seed_patterns_and_state_fields_are_deterministic() -> None:
    probe = {
        "kind": "tone", "h_source_dots": 47, "w_source_dots": 83,
        "seed_label": "test/tone", "params": {"coverage": 0.37},
    }
    first = ec.pattern_bits(probe)
    second = ec.pattern_bits(probe)
    assert np.array_equal(first, second)
    assert first.mean() == pytest.approx(0.37, abs=0.03)

    field = {
        "field_id": "test/cmy", "family": "prnd", "seed_label": "test/cmy",
        "nx": 64, "ny": 32,
    }
    definition = ec.CHANNELS["cmy8-image"]
    states = ec.field_states(field, definition)
    assert np.array_equal(states, ec.field_states(field, definition))
    counts = np.bincount(states.ravel(), minlength=8)
    assert counts.max() - counts.min() <= 1
    assert ec.SEED_TEXT == "paper-store/e025/channel-metrology-v2"

    grid = GridSpec(600, 600, 2, 2)
    marked = np.ones((1, 1), np.uint8)
    motifs = {
        shape: ec.expand_cells(marked, grid, shape)
        for shape in ("solid-cell", "main-diagonal", "horizontal-half",
                      "vertical-half")
    }
    assert motifs["solid-cell"].sum() == 4
    assert all(motifs[shape].sum() == 2 for shape in
               ("main-diagonal", "horizontal-half", "vertical-half"))
    assert len({value.tobytes() for value in motifs.values()}) == 4

    profile_probe = {
        "kind": "profile_tone", "h_source_dots": 23,
        "w_source_dots": 701, "seed_label": "test/profile-tone",
        "params": {"coverage": 0.50, "axis": "x"},
    }
    profile_bits = ec.pattern_bits(profile_probe)
    assert profile_bits.mean() == pytest.approx(0.50, abs=1e-3)
    assert np.ptp(profile_bits.mean(axis=0)) <= 1 / 23


def _emit(prefix: Path, kind: str) -> tuple[Path, Path, dict]:
    preset = "hp-m281-bw" if kind == "mono" else "hp-m281-color"
    return emitter.emit(
        output_prefix=prefix, page_kind=kind, primary_grid=600,
        comparison_grids=(300, 1200, 2400), request=(600, 600),
        preset=preset,
    )


def test_emission_is_deterministic_dense_and_forward_only(tmp_path: Path) -> None:
    ps1, mf1, m1 = _emit(tmp_path / "one", "mono")
    ps2, mf2, m2 = _emit(tmp_path / "two", "mono")
    assert ps1.read_bytes() == ps2.read_bytes()
    assert mf1.read_bytes() == mf2.read_bytes()
    assert m1 == m2
    page = m1["pages"][0]
    assert m1["schema"] == "paper-store/e025/stimulus/v2"
    assert m1["layout_version"] == 2
    assert len(page["fields"]) == 51
    assert len(page["probes"]) == 136
    assert {item["family"] for item in page["fields"]} == {
        "prnd", "edge_canary", "fec_coupon",
    }
    assert sum(item["kind"] == "machine_strip"
               for item in page["infrastructure"]) == 2
    assert sum(item["kind"] == "edge_tick" for item in page["probes"]) == 52
    assert sum(item["group"] == "background" for item in page["probes"]) == 10
    assert {item["role"] for item in page["fields"]} >= {
        "shape-control", "aspect-control",
    }
    assert "atlas" not in page and "rates" not in m1 and "modes" not in m1
    postscript = ps1.read_text()
    assert postscript.count("%%Page:") == 1
    assert "PHCAL1;LAY=1" in postscript
    assert "/ImagingBBox" in postscript and "/ProcessColorModel" in postscript

    # Statistical area follows the frontier, not coarse physical cell size.
    area_by_cell: dict[int, float] = {}
    for field in page["fields"]:
        if field["family"] != "prnd":
            continue
        grid = page["candidates"][field["candidate_key"]]["grid"]
        if grid["dpi_x"] != 600:
            continue
        area_by_cell.setdefault(grid["c_x"], 0.0)
        area_by_cell[grid["c_x"]] += (
            field["w_layout_dots"] * field["h_layout_dots"]
        )
    assert area_by_cell[2] > 10 * area_by_cell[6]


def test_color_page_is_one_page_and_keeps_exact_paths_distinct(tmp_path: Path) -> None:
    ps, _mf, manifest = _emit(tmp_path / "color", "color")
    page = manifest["pages"][0]
    assert ps.read_text().count("%%Page:") == 1
    assert len(page["fields"]) == 47
    assert len(page["probes"]) == 200
    definitions = {item["definition_id"] for item in page["candidates"].values()}
    assert {"k1-mask", "c1-mask", "m1-mask", "y1-mask",
            "cm4-image", "cmy8-image", "cmy8-opm",
            "kcmy4-image"} <= definitions
    assert sum(item["group"] == "plane-registration"
               for item in page["probes"]) == 36
    assert page["candidates"][
        next(key for key, value in page["candidates"].items()
             if value["definition_id"] == "cmy8-image" and
             value["grid"]["c_x"] == 2 and value["grid"]["dpi_x"] == 600)
    ]["emission_path"] == "DeviceCMYK-image"
    assert any(value["emission_path"] == "sequential-imagemask-overprint-opm1"
               for value in page["candidates"].values())


def test_scan_clipped_edge_tick_is_unobservable_not_fatal(tmp_path: Path) -> None:
    scan = tmp_path / "scan.png"
    Image.fromarray(np.full((100, 100), 255, np.uint8)).save(scan)
    source = analyzer.RasterSource(scan)
    probe = {
        "probe_id": "edge/bottom/tick-0",
        "kind": "edge_tick",
        "group": "printable-extent",
        "x_layout_dots": 20.0,
        "y_layout_dots": 101.0,
        "w_layout_dots": 10.0,
        "h_layout_dots": 4.0,
        "params": {"edge": "bottom", "gap_mm": 0.0},
    }
    probes = analyzer.score_probes(
        source, np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0]),
        {"probes": [probe]}, np.full((10, 10), 1.0, np.float32),
    )
    row = probes["printable_ticks"]["edges"]["bottom"]["ticks"][0]
    assert row["status"] == "unobservable"
    assert row["coverage"] is None
    assert row["scan_visible_fraction"] == 0.0
    assert (probes["printable_ticks"]["edges"]["bottom"]
            ["conservative_contiguous_present_gap_mm"] is None)


def test_pattern_alignment_removes_only_bounded_translation() -> None:
    yy, xx = np.indices((41, 43))
    truth = ((xx // 3 + yy // 4) % 2).astype(bool)
    values = np.roll(np.roll(truth.astype(np.float64), 5, axis=1), -4, axis=0)
    aligned_truth, aligned_values, dx, dy, corr = (
        analyzer._align_pattern_translation(truth, values, max_shift=8)
    )
    assert (dx, dy) == (5, -4)
    assert corr == pytest.approx(1.0)
    assert np.array_equal(aligned_truth, aligned_values.astype(bool))


def test_payload_extent_uses_designated_channel_baseline() -> None:
    base = {
        "candidate_id": "candidate", "family": "prnd",
        "field_id": "interior/channel", "role": "channel",
        "hard_error_rate": 0.10, "mutual_information_bpc": 0.70,
    }
    stressed = {
        **base, "field_id": "control/stressed", "role": "equal-pitch-control",
        "hard_error_rate": 0.49, "mutual_information_bpc": 0.01,
    }
    edge = {
        **base, "field_id": "edge/top/c2-10", "family": "edge_canary",
        "role": "payload-safe-extent", "edge": "top", "edge_gap_mm": 10.0,
        "hard_error_rate": 0.15, "mutual_information_bpc": 0.60,
        "phase_separation_score": 1.0,
    }
    extent = analyzer._payload_safe_extent([base, stressed, edge])
    evaluated = extent["edges"]["top"]["canaries"][0]
    assert evaluated["reference_scope"] == "role=channel"
    assert evaluated["reference_field_ids"] == ["interior/channel"]
    assert evaluated["ber_limit"] == pytest.approx(0.11)
    assert not evaluated["passed"]


@pytest.fixture(scope="module")
def mono_roundtrip(tmp_path_factory: pytest.TempPathFactory) -> dict:
    if os.environ.get("HOLO_RUN_SLOW_TESTS") != "1":
        pytest.skip(
            "set HOLO_RUN_SLOW_TESTS=1 for the E025 Ghostscript "
            "roundtrip")
    if shutil.which("gs") is None:
        pytest.skip("ghostscript required")
    path = tmp_path_factory.mktemp("e025-mono")
    ps, manifest, _ = _emit(path / "mono", "mono")
    png = path / "mono.png"
    subprocess.run([
        "gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=pnggray",
        "-r600", "-o", str(png), str(ps),
    ], check=True, timeout=120)
    report = analyzer.analyze(
        scan=png, manifest_path=manifest,
        scan_dpi_x=600, scan_dpi_y=600,
        printer_id="ghostscript", scanner_id="synthetic",
        print_path="postscript", scan_mode="pnggray", role="pipeline",
        media="synthetic", consumable_state="none",
        sheet_id="synthetic-mono-sheet", capture_id="synthetic-mono",
        readback_dpi=None, max_bp_iters=20,
        diag=path / "diag.png", trace_dir=None,
    )
    return {"path": path, "ps": ps, "manifest": manifest,
            "png": png, "report": report}


@pytest.fixture(scope="module")
def color_roundtrip(tmp_path_factory: pytest.TempPathFactory) -> dict:
    if os.environ.get("HOLO_RUN_SLOW_TESTS") != "1":
        pytest.skip(
            "set HOLO_RUN_SLOW_TESTS=1 for the E025 Ghostscript "
            "roundtrip")
    if shutil.which("gs") is None:
        pytest.skip("ghostscript required")
    path = tmp_path_factory.mktemp("e025-color")
    ps, manifest, _ = _emit(path / "color", "color")
    png = path / "color.png"
    subprocess.run([
        "gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=png16m",
        "-r600", "-o", str(png), str(ps),
    ], check=True, timeout=120)
    report = analyzer.analyze(
        scan=png, manifest_path=manifest,
        scan_dpi_x=600, scan_dpi_y=600,
        printer_id="ghostscript", scanner_id="synthetic",
        print_path="postscript", scan_mode="png16m", role="pipeline",
        media="synthetic", consumable_state="none",
        sheet_id="synthetic-color-sheet", capture_id="synthetic-color",
        readback_dpi=None, max_bp_iters=20,
        diag=path / "diag.png", trace_dir=None,
    )
    return {"path": path, "ps": ps, "manifest": manifest,
            "png": png, "report": report}


def test_clean_mono_decodes_strips_edges_probes_and_fec(
    mono_roundtrip: dict,
) -> None:
    report = mono_roundtrip["report"]
    e025 = report["metadata"]["e025"]
    assert e025["schema"] == "paper-store/e025/analysis/v2"
    assert len(e025["device_readback_strips"]) == 2
    assert all(item["crc_ok"] for item in e025["device_readback_strips"])
    assert {item["fields"]["RE"] for item in e025["device_readback_strips"]} == {
        "600x600"
    }
    rectangle = e025["payload_safe_extent"]["usable_rectangle_mm"]
    assert rectangle is not None and rectangle["area_mm2"] > 60_000
    fec = [item for item in e025["field_summaries"]
           if item["family"] == "fec_coupon"]
    assert len(fec) == 2
    assert all(level["certified"] == level["attempted"] == 2
               for field in fec for level in field["ldpc"])
    c2c3 = [item for item in e025["field_summaries"]
            if item["family"] == "prnd" and
            ("c2" in item["field_id"] or "c3" in item["field_id"])]
    assert all(item["hard_error_rate"] < 0.001 for item in c2c3)
    assert e025["geometry"]["internal_warp"]["n_ok"] >= 10
    tone = e025["probes"]["tone_metrology"]
    assert len(tone["fixed_profiles"]) == 5
    assert tone["deconfounded_models"]["K"]["rank"] == 9
    assert max(item["authored_profile_p95_p05_coverage"]
               for item in tone["fixed_profiles"]) < 0.001
    assert len(e025["probes"]["background"]["witnesses"]) == 10
    assert len(e025["candidate_factorials"]["shape-control"]) == 4
    assert len(e025["candidate_factorials"]["aspect-control"]) == 2
    assert all(item["resolved"] for item in
               e025["probes"]["morphology_frequency"])
    assert (mono_roundtrip["path"] / "diag.png").exists()


def test_clean_color_scores_exact_alphabets_and_all_coupon_levels(
    color_roundtrip: dict,
) -> None:
    e025 = color_roundtrip["report"]["metadata"]["e025"]
    assert len(e025["device_readback_strips"]) == 2
    assert all(item["crc_ok"] for item in e025["device_readback_strips"])
    rectangle = e025["payload_safe_extent"]["usable_rectangle_mm"]
    assert rectangle is not None and rectangle["width_mm"] >= 208
    fec = [item for item in e025["field_summaries"]
           if item["family"] == "fec_coupon"]
    assert len(fec) == 3
    assert sum(level["attempted"] for field in fec for level in field["ldpc"]) == 18
    assert all(level["certified"] == level["attempted"] and level["wrong"] == 0
               for field in fec for level in field["ldpc"])
    cmy = next(item for item in e025["field_summaries"]
               if item["field_id"] == "states/middle/cmy8-c2")
    assert cmy["mutual_information_bpc"] > 2.95
    assert cmy["hard_error_rate"] < 0.002
    assert all(item["resolved"] for item in
               e025["probes"]["morphology_frequency"])
    tone = e025["probes"]["tone_metrology"]
    assert len(tone["fixed_profiles"]) == 12
    assert len(tone["response_samples"]) == 56
    assert max(item["authored_profile_p95_p05_coverage"]
               for item in tone["fixed_profiles"]) < 0.001
    assert all(model["rank"] == 9
               for model in tone["deconfounded_models"].values())
    registration = e025["probes"]["plane_registration"]
    assert len(registration["targets"]) == 9
    assert registration["maximum_relative_registration_mm"] < 0.05
    assert len(e025["probes"]["background"]["witnesses"]) == 10
    assert len(e025["candidate_factorials"]["constellation-control"]) == 2
    kcmy = next(item for item in e025["field_summaries"]
                if item["field_id"] == "states/top/kcmy4-c2")
    assert kcmy["mutual_information_bpc"] > 1.95
    assert kcmy["hard_error_rate"] < 0.002
    # The alternate OPM path remains an independent measurement, regardless
    # of whether this Ghostscript version preserves or destroys its overlaps.
    opm = next(item for item in e025["field_summaries"]
               if item["field_id"] == "states/bottom/cmy8-opm-c2")
    assert opm["candidate_id"] != cmy["candidate_id"]


def test_trace_bundle_retains_full_field_evidence(
    color_roundtrip: dict, tmp_path: Path,
) -> None:
    manifest = json.loads(Path(color_roundtrip["manifest"]).read_text())
    page = manifest["pages"][0]
    field = next(item for item in page["fields"]
                 if item["field_id"] == "edge/top/c2-0.5")
    source = analyzer.RasterSource(color_roundtrip["png"])
    coef, _geometry, _thumb, _fx, _fy = analyzer.register(source, page, 600, 600)
    index: list[dict] = []
    analyzer.score_field(
        source=source, coef=coef, page=page, field=field,
        scan_dpi_x=600, scan_dpi_y=600,
        physical_sheet_id="synthetic-color-sheet", max_bp_iters=20,
        trace_dir=tmp_path, trace_index=index, ordinal=0,
    )
    assert index[0]["field_id"] == field["field_id"]
    trace = np.load(tmp_path / "f000.npz")
    n = field["nx"] * field["ny"]
    assert trace["true_state"].shape == (n,)
    assert trace["features"].shape == (n, 3)
    assert trace["state_scores"].shape == (n, 8)
    assert trace["bit_llr"].shape == (n, 3)
    assert set(np.unique(trace["split"])) == {0, 1, 2}


def test_profile_uses_measured_extent_and_keeps_hint_advisory(
    color_roundtrip: dict,
) -> None:
    report = color_roundtrip["report"]
    profile = profiler.build_profile(
        kind="pipeline", policy_id="survey", reports=[report], references=[]
    )
    assert profile["qualified"]
    assert profile["schema"] == "paper-store/e025/profile/v2"
    assert profile["qualified"][0]["candidate_id"].startswith("cmy8-image-")
    assert profile["qualified"][0]["rate_id"] == "r0775"
    assert profile["payload_safe_extent"]["intersection_rectangle_mm"] is not None
    assert profile["receiver_hint"]["may_weaken_receiver_gates"] is False
    payload = dict(profile)
    digest = payload.pop("semantic_sha256")
    assert profiler._digest(payload) == digest

    production = profiler.build_profile(
        kind="pipeline", policy_id="production", reports=[report], references=[]
    )
    assert not production["qualified"]
    with pytest.raises(ValueError, match="repeated scan"):
        profiler.build_profile(
            kind="pipeline", policy_id="survey",
            reports=[report, report], references=[],
        )

    target = copy.deepcopy(report)
    target["metadata"]["role"] = "sensor"
    target["footing"]["scanner_id"] = "target-scanner"
    reference = copy.deepcopy(report)
    reference["footing"]["scanner_id"] = "reference-scanner"
    sensor = profiler.build_profile(
        kind="sensor", policy_id="survey",
        reports=[target], references=[reference],
    )
    assert len(sensor["scanner_deltas"]) == len(report["observations"])
    assert all(item["hard_error_delta"] == 0.0
               for item in sensor["scanner_deltas"])


# ---------------------------------------------------------------------------
# Windowed geometry (analyzer v3).
#
# The v2 contract solved one constant sub-cell phase per field.  Measured on
# the first physical pair (2026-07-18) the true phase both leaves the +/-0.48
# search box and drifts within a single field, so small-cell fields read near
# chance with their ink intact.  These tests pin the two properties that make
# the windowed replacement safe to compare against the old numbers.
# ---------------------------------------------------------------------------

def _score_both_modes(png: Path, manifest: Path, field_id: str,
                      window_cells: int = 96) -> dict:
    page = json.loads(manifest.read_text())["pages"][0]
    field = next(f for f in page["fields"] if f["field_id"] == field_id)
    source = analyzer.RasterSource(png)
    coef, _geometry, _thumb, _fx, _fy = analyzer.register(source, page, 600, 600)
    out = {}
    for mode in ("field", "window"):
        _observation, summary = analyzer.score_field(
            source=source, coef=coef, page=page, field=field,
            scan_dpi_x=600, scan_dpi_y=600, physical_sheet_id="synthetic",
            max_bp_iters=20, trace_dir=None, trace_index=[], ordinal=0,
            geometry_mode=mode, window_cells=window_cells,
        )
        out[mode] = summary
    return out


def test_window_geometry_reports_contract_and_never_loses_to_field_mode(
    mono_roundtrip: dict,
) -> None:
    """On a clean render both modes must agree, and v3 must expose its contract."""
    scored = _score_both_modes(
        mono_roundtrip["png"], mono_roundtrip["manifest"], "spatial/middle/c2"
    )
    field, window = scored["field"], scored["window"]
    assert field["geometry_mode"] == "field"
    assert window["geometry_mode"] == "window"

    geometry = window["geometry"]
    for key in ("n_windows", "n_locked", "n_unresolved", "n_inherited",
                "field_phase_fallback", "validation_cells_total",
                "validation_cells_in_locked_windows", "windows"):
        assert key in geometry, key
    assert geometry["n_windows"] >= 4
    assert geometry["n_windows"] == (geometry["n_locked"]
                                     + geometry["n_unresolved"]
                                     + geometry["n_inherited"])

    # Headline statistics must cover EVERY validation cell: a field may never be
    # flattered by scoring only the windows that locked.
    assert geometry["validation_cells_total"] >= geometry[
        "validation_cells_in_locked_windows"]

    # Superset property: windows that cannot solve their own geometry fall back
    # to the whole-field phase, so window mode can never read worse.
    assert window["hard_error_rate"] <= field["hard_error_rate"] + 5e-3


def test_window_geometry_recovers_a_field_that_constant_phase_cannot(
    mono_roundtrip: dict, tmp_path: Path,
) -> None:
    """Inject a non-affine drift; only per-window phase should survive it.

    The displacement is sinusoidal in y with zero linear component, so the
    global corner affine cannot absorb it -- exactly the residual measured on
    the real capture, where the required phase drifts by up to 2.49 cells
    across one field.
    """
    original = np.asarray(Image.open(mono_roundtrip["png"]).convert("L"))
    height = original.shape[0]
    rows = np.arange(height)
    # One page-height period of +/-4 authored dots.  Across the target field
    # that is ~1.6 c2 cells of drift -- far outside the +/-0.5-cell reach of a
    # constant phase -- while within one 48-cell window it is only ~0.17 cell,
    # so a per-window phase can still track it.  A single sine has no linear
    # component for the corner affine to absorb.
    shift = 4.0 * np.sin(2.0 * np.pi * rows / height)
    warped = np.empty_like(original)
    for y in range(height):
        whole = int(np.floor(shift[y]))
        frac = float(shift[y] - whole)
        near = np.roll(original[y], whole)
        far = np.roll(original[y], whole + 1)
        warped[y] = np.clip((1.0 - frac) * near + frac * far, 0, 255).astype(
            original.dtype
        )
    warped_png = tmp_path / "mono-warped.png"
    Image.fromarray(warped).save(warped_png)

    scored = _score_both_modes(
        warped_png, mono_roundtrip["manifest"], "spatial/middle/c2",
        window_cells=48,
    )
    field_ber = scored["field"]["hard_error_rate"]
    window_ber = scored["window"]["hard_error_rate"]

    # The injected drift must actually hurt the constant-phase model, otherwise
    # this test proves nothing about the fix.
    assert field_ber > 0.02, f"warp did not stress field mode ({field_ber:.4f})"
    assert window_ber < field_ber / 2.0, (
        f"window mode failed to recover the drift: "
        f"field {field_ber:.4f} vs window {window_ber:.4f}"
    )
    assert scored["window"]["geometry"]["n_locked"] >= 1
