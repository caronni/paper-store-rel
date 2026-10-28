"""analyzer.inputs — the run dir, typed (PLAN §1.2, W1a)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from analyzer import inputs
from analyzer.types import Lane

from ._analyzer_fixtures import (I_RUN_DIR, J_RUN_DIR, i_inputs, j_inputs,
                                 needs_i_run, needs_j_run)


# ------------------------------------------------------------- synthetic

def test_metadata_word_inverts_decode_metadata():
    """`_metadata_word` is the exact inverse of `decode_metadata`."""
    from holo3.format import metadata
    for version, k in ((0, 1), (0, 1759), (0, 1340), (0, 5277),
                       (1, metadata.MAX_K - 1)):
        word = inputs._metadata_word(version, k)
        assert word >> (1 + metadata.K_BITS) == 0, "top 5 bits must be zero"
        table = metadata.coefficient_table(metadata.MAX_COUNTER)
        equations = {
            index: (int(table[index]) & word).bit_count() & 1
            for index in range(200)}
        result = metadata.decode_metadata(equations)
        assert result.rank == metadata.METADATA_BITS
        assert (result.version, result.k) == (version, k)


def test_metadata_word_refuses_out_of_range_k():
    from holo3.format import metadata
    with pytest.raises(inputs.InputsError):
        inputs._metadata_word(0, metadata.MAX_K)


def test_lane_policy_is_checked(tmp_path: Path):
    with pytest.raises(inputs.InputsError):
        inputs.load_run(tmp_path, lanes="finest")


def test_absent_run_dir_is_named(tmp_path: Path):
    with pytest.raises(inputs.InputsError) as excinfo:
        inputs.load_run(tmp_path)
    assert "report.json" in str(excinfo.value)


def test_run_open_absent_events(tmp_path: Path):
    (tmp_path / "report.json").write_text("{}", "utf-8")
    with pytest.raises(inputs.InputsError) as excinfo:
        inputs.read_run_open(tmp_path)
    assert "events.jsonl" in str(excinfo.value)


# ------------------------------------------------------------ sheet I

@needs_i_run
def test_i_run_loads_with_the_facts_the_design_names():
    run = i_inputs()
    assert run.format_ref == "L:c2-cmy8-r0700-p120-x1@3392x2368"
    assert run.tiles_yx == (53, 37)
    assert run.cells_yx == (3392, 2368)
    assert run.pitch_in == Fraction(1, 300)
    assert run.live_pages == (0,)
    assert run.declared_pages == (0,)
    assert len(run.certificates) == 5880
    assert len(run.captures) == 4
    assert run.rank_report == 5277
    assert run.k_total == 5277
    assert run.metadata_state == "ready"
    assert run.metadata_word is not None
    assert run.provenance["argv"].startswith(
        "holo3/__main__.py decode")


@needs_i_run
def test_i_lanes_carry_ppc_frame_and_a_consistent_level_pitch():
    run = i_inputs()
    assert len(run.lanes) == 13, "3 x 3 levels + the 4800's 4"
    for lane in run.lanes:
        assert isinstance(lane, Lane)
        assert lane.ppc * lane.frame == Fraction(
            int(round(lane.dpi)) * run.pitch_in)
        # PLAN §1.3: level pitch = placement.pitch_px / frame.
        assert lane.pitch_px_level == pytest.approx(
            lane.pitch_px_native / float(lane.frame))
        assert len(lane.rasters) == 3
        for raster in lane.rasters:
            assert raster.ndim == 2
        shape = run.captures[lane.ordinal].shape_px
        assert lane.rasters[0].shape[0] == pytest.approx(
            shape[0] / float(lane.frame), abs=1)
        assert lane.placements, "a lane exists only where placements do"
        assert all(item.level_index == lane.level_index
                   for item in lane.placements)


@needs_i_run
def test_i_plane_fields_and_pooled_ctx_are_keyed_as_designed():
    run = i_inputs()
    assert len(run.plane_fields) == 13
    for (capture_id, level_index, page, plane) in run.plane_fields:
        assert page == 0
        assert plane == 0, "the I run published a C field only"
        assert (capture_id, level_index) in {
            lane.lane_id for lane in run.lanes}
    assert set(run.pooled_ctx) == {(0, "2"), (0, "4"), (0, "8")}


@needs_i_run
def test_i_coverage_is_total_and_finest_covering_picks_one_per_capture():
    run = i_inputs()
    coverage = inputs.page_tile_coverage(run, 0)
    assert coverage.shape == (53, 37)
    assert int((coverage > 0).sum()) == 53 * 37, "every tile is covered"
    lanes = inputs.finest_covering(run, 0, 26, 18)
    captures = [lane_id[0] for lane_id in lanes]
    assert len(captures) == len(set(captures)), "one level per capture"
    for capture_id, level_index in lanes:
        finer = [lane for lane in run.lanes
                 if lane.capture_id == capture_id
                 and lane.level_index > level_index]
        for lane in finer:
            counts = inputs.lane_tile_coverage(run, lane.lane_id, 0)
            assert int(counts[26, 18]) < 64 * 64, (
                "a finer level that covered the tile should have won")


@needs_i_run
def test_i_run_mints_are_the_withhold_set():
    keys = inputs.run_mint_keys(I_RUN_DIR)
    assert len(keys) == 14, "the resume-3 run minted 14 distinct keys"
    run = i_inputs()
    assert all(key in run.certificates for key in keys)


# ------------------------------------------------------------ sheet J

@needs_j_run
def test_j_live_pages_are_the_placed_ones_not_the_declared_100():
    run = j_inputs()
    assert len(run.declared_pages) == 100
    assert run.live_pages == (0, 1)
    assert run.row.display_id == "c2-cmy8-r0547@53x37"
    assert len(run.lanes) == 3
    assert run.metadata_state == "ready"
    assert run.k_total == 4020


@needs_j_run
def test_rung_ppc_filters_the_lane_set():
    """`--rung PPC` reproduces production's shared-ppc pairing (§4.2).

    Exercised on J (one capture, three levels) rather than I so the test
    session loads the 6.5 GB sheet-I snapshot exactly once.
    """
    run = inputs.load_run(J_RUN_DIR, rung_ppc=8)
    assert {str(lane.ppc) for lane in run.lanes} == {"8"}
    assert len(run.lanes) == 1
    with pytest.raises(inputs.InputsError):
        inputs.load_run(J_RUN_DIR, rung_ppc=32)


@needs_j_run
def test_j_coverage_leaves_most_tiles_uncovered():
    run = j_inputs()
    for page in run.live_pages:
        coverage = inputs.page_tile_coverage(run, page)
        covered = int((coverage > 0).sum())
        assert 0 < covered < 53 * 37, "a fragment sheet touches few tiles"


# ------------------------------------------------------ --format-ref


def test_format_ref_override_must_resolve(tmp_path: Path):
    (tmp_path / "report.json").write_text("{}", "utf-8")
    (tmp_path / "events.jsonl").write_text(
        '{"type": "RunOpen", "format_id": "c2-cmy8-r0547@53x37"}\n', "utf-8")
    with pytest.raises(inputs.InputsError, match="does not resolve"):
        inputs.load_run(tmp_path, format_ref="L:no-such-fossil@1x1")


@needs_j_run
def test_j_needs_the_fossil_seed_and_gate_1_passes_with_it():
    """PLAN §6: J's RunOpen carries the BARE id, which now mints a
    different AES seed (finding G1).  With `--format-ref
    L:c2-cmy8-r0547@53x37` the row carries the seed J was emitted with,
    and gate 1 — every snapshot certificate against GT user bits — is
    the only witness that says so.
    """
    from analyzer import truth as truth_mod
    from ._analyzer_fixtures import J_GEN_DIR, J_PAYLOAD

    fossil = "L:c2-cmy8-r0547@53x37"
    run = inputs.load_run(J_RUN_DIR, format_ref=fossil)
    assert run.format_ref == fossil
    assert run.row.row_id == fossil
    assert run.row.seed == b"holo/v2/c2-cmy8-r0547@53x37"
    assert run.row.seed != j_inputs().row.seed, "the bare id forks the seed"
    assert run.provenance["format_ref_override"] == {
        "run_open": "c2-cmy8-r0547@53x37", "used": fossil}

    truth = truth_mod.load_truth(J_GEN_DIR, J_PAYLOAD, run.row, 2,
                                 format_ref=run.format_ref)
    gate = truth_mod.gate_certificates(truth, run)
    assert gate["mismatches"] == 0 and gate["checked"] == len(run.certificates)
    assert gate["checked"] > 0
