"""analyzer.inputs — the run dir, typed (PLAN §1.2, W1a)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from analyzer import inputs
from analyzer.types import Lane

from holo.receiver.tests._h3_support import assert_measured

from ._analyzer_fixtures import (DECLARED_PAGES, declared_run_dir, needs_sim,
                                 sim_run, sim_run_dir, unplaced_run_dir)


# ------------------------------------------------------------- synthetic

def test_metadata_word_inverts_decode_metadata():
    """`_metadata_word` is the exact inverse of `decode_metadata`."""
    from holo.receiver.format import metadata
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
    from holo.receiver.format import metadata
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


def test_a_plane_field_fact_is_keyed_by_page_and_plane_alone():
    """AI1, offline: the key the receiver publishes is the key we hold.

    `holo.receiver.data.PlaneField` carries no capture and no level —
    the displacement is the printer's, frozen at print time — so
    `sort_facts` may not invent either (docs/PAGE-FIELD-DESIGN.md §2.2).
    Two faces of one sheet, three planes each, is the shape a duplex
    run hands it.
    """
    import numpy as np
    from holo.receiver import data

    def field(page, plane):
        return data.PlaneField(
            page=page, plane=plane,
            delta_dots_xy=np.zeros((3, 3, 2), np.float64),
            support=np.ones((3, 3), np.float64),
            uncertainty_dots=np.full((3, 3), 0.3),
            n_observations=9, n_captures=1, ordinal=100 * page + plane)

    facts = [field(page, plane) for page in (0, 1) for plane in (0, 1, 2)]
    facts.append(data.EvidenceRevision(capture_id="cap0", page=0,
                                       revision=7964))
    sorted_facts = inputs.sort_facts(facts)
    assert set(sorted_facts["plane_fields"]) == {
        (page, plane) for page in (0, 1) for plane in (0, 1, 2)}
    assert sorted_facts["plane_fields"][(1, 2)].ordinal == 102
    # EvidenceRevision is carried in the snapshot and read by nobody here:
    # the analyzer never resumes, it exports (AI6, AI8).
    assert all(not bucket for name, bucket in sorted_facts.items()
               if name != "plane_fields")


# ------------------------------------------- the colour sim's run dir
# TIER S (2026-10-09): the receiver's displaced 10x10 colour sim decoded
# with `--complete` — 300 of 300 certified, K 78.  The sheet-I literals
# these tests carried are records (PAGE-FIELD-PLAN A1b), sheet J's are
# experiments/035's.

@needs_sim
def test_sim_run_loads_with_the_facts_the_design_names():
    run = sim_run()
    assert run.format_ref == (
        "1i200-cmy8-r0550x0550x0547-p120-v1@10x10")
    assert run.tiles_yx == (10, 10)
    assert run.cells_yx == (640, 640)
    assert run.pitch_in == Fraction(1, 200)
    assert run.live_pages == (0,)
    assert run.declared_pages == (0,)
    assert_measured("certificates of the --complete sim decode",
                    len(run.certificates), 300)
    assert len(run.captures) == 1
    assert run.rank_report == 78
    assert run.k_total == 78
    assert run.metadata_state == "ready"
    assert run.metadata_word is not None
    # An in-process decode writes the HOST's sys.argv (engine.py), so
    # the file is provenance and carries no verb worth pinning.
    assert isinstance(run.provenance["argv"], str)


@needs_sim
def test_sim_lanes_carry_ppc_frame_and_a_consistent_level_pitch():
    from holo.receiver.plugins import intake
    run = sim_run()
    capture = run.captures[0]
    levels = intake.build_levels(capture.dpi, run.pitch_in,
                                 capture.shape_px)
    assert 1 <= len(run.lanes) <= len(levels), "one capture, its levels"
    # measured 2026-10-09: placements on all three levels (frames 3, 2, 1)
    assert_measured("lanes of the --complete sim decode", len(run.lanes), 3)
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


@needs_sim
def test_sim_plane_fields_and_pooled_ctx_are_keyed_as_designed():
    """AI1: (page, plane), and nothing else, in the key — on fields the
    receiver WROTE: one per plane on the one live page, `n_captures 1`.
    Pooling needs a second capture to pair with (`color_pooled.
    MIN_CAPTURES` 2), so a one-capture run publishes no pooled context.
    """
    run = sim_run()
    assert set(run.plane_fields) == {(0, 0), (0, 1), (0, 2)}
    for key, field in run.plane_fields.items():
        assert isinstance(key, tuple) and len(key) == 2
        page, plane = key
        assert page in run.live_pages
        assert plane in (0, 1, 2)
        assert (int(field.page), int(field.plane)) == key
        assert not hasattr(field, "capture_id")
        assert int(field.n_captures) == 1
        assert field.delta_dots_xy.shape == (10, 10, 2)
    assert run.pooled_ctx == {}


@needs_sim
def test_sim_coverage_is_total_and_finest_covering_picks_one_per_capture():
    run = sim_run()
    coverage = inputs.page_tile_coverage(run, 0)
    assert coverage.shape == (10, 10)
    assert int((coverage > 0).sum()) == 10 * 10, "every tile is covered"
    lanes = inputs.finest_covering(run, 0, 5, 5)
    assert lanes
    captures = [lane_id[0] for lane_id in lanes]
    assert len(captures) == len(set(captures)), "one level per capture"
    for capture_id, level_index in lanes:
        finer = [lane for lane in run.lanes
                 if lane.capture_id == capture_id
                 and lane.level_index > level_index]
        for lane in finer:
            counts = inputs.lane_tile_coverage(run, lane.lane_id, 0)
            assert int(counts[5, 5]) < 64 * 64, (
                "a finer level that covered the tile should have won")


@needs_sim
def test_sim_mints_are_the_withhold_set():
    """A from-scratch run's mints ARE its certificates: the whole page."""
    keys = inputs.run_mint_keys(sim_run_dir())
    run = sim_run()
    assert set(keys) == set(run.certificates)


@needs_sim
def test_live_pages_are_the_placed_ones_not_the_declared_100():
    run = inputs.load_run(declared_run_dir())
    assert len(run.declared_pages) == DECLARED_PAGES == 100
    assert run.live_pages == (0,)
    assert run.metadata_state == "ready"
    with pytest.raises(inputs.InputsError,
                       match="no page carries an accepted placement"):
        inputs.load_run(unplaced_run_dir())


@needs_sim
def test_rung_ppc_filters_the_lane_set():
    """`--rung PPC` reproduces production's shared-ppc pairing (§4.2)."""
    present = sim_run().lanes[-1].ppc
    run = inputs.load_run(sim_run_dir(), rung_ppc=present)
    assert {lane.ppc for lane in run.lanes} == {present}
    assert len(run.lanes) == 1
    with pytest.raises(inputs.InputsError):
        inputs.load_run(sim_run_dir(), rung_ppc=32)


# ------------------------------------------------------ --format-ref


def test_format_ref_override_must_resolve(tmp_path: Path):
    (tmp_path / "report.json").write_text("{}", "utf-8")
    (tmp_path / "events.jsonl").write_text(
        '{"type": "RunOpen", "format_id": "c2-cmy8-r0547@53x37"}\n', "utf-8")
    with pytest.raises(inputs.InputsError, match="does not resolve"):
        inputs.load_run(tmp_path, format_ref="L:no-such-fossil@1x1")


def _tiny_run_dir(tmp_path: Path, run_open_ref: str) -> Path:
    """A run dir carrying the F1 volume's certificates and one placement.

    Only what `load_run` reads: a report with one capture, a RunOpen, a
    fact snapshot and three 4x4 rasters behind the one lane.
    """
    import json

    import numpy as np
    from holo.receiver import data, snapshot

    from analyzer import close as close_mod

    from ._analyzer_fixtures import emitted_volume

    volume = emitted_volume()
    capture_id = "c0ffee000000f1f1"
    run = tmp_path / "run"
    (run / capture_id[:12]).mkdir(parents=True)
    (run / "report.json").write_text(json.dumps({
        "capture_facts": [{"capture": capture_id, "ordinal": 0,
                           "dpi": 1200.0, "channels": 3, "levels_ppc": [],
                           "shape_yx": [4, 4]}],
        "pages": [0]}), "utf-8")
    (run / "events.jsonl").write_text(json.dumps(
        {"type": "RunOpen", "format_id": run_open_ref,
         "pitch_in": float(volume.row.pitch_in)}) + "\n", "utf-8")
    for plane in ("r", "g", "b"):
        np.save(run / capture_id[:12] / f"l00-{plane}.npy",
                np.zeros((4, 4), np.uint8))
    placement = data.Placement(
        window_id=(capture_id, 0, 0, (0, 0, 4, 4)), capture_id=capture_id,
        level_index=0, region_index=0, patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(0, 0), native_affine=(6.0, 0.0, 0.0, 0.0, 6.0, 0.0),
        pitch_px=6.0, route="place",
        local_cells_yx=np.zeros((1, 2), np.int16), quality=0.1)
    certificates = tuple(
        close_mod.as_certificate(key, bits, source="emitted")
        for key, bits in sorted(volume.truth.user_bits.items()))
    snapshot.write(run / snapshot.NAME, (placement, *certificates))
    return run


def test_a_format_ref_override_restores_the_emitted_seed(tmp_path: Path):
    """PLAN §6: sheet J's RunOpen carries the BARE id, which now mints a
    different AES seed (finding G1).  With `--format-ref
    L:c2-cmy8-r0547@53x37` the row carries the seed J was emitted with,
    and gate 1 — every snapshot certificate against GT user bits, the
    truth rebuilt under the run's ref — is the only witness that says
    so.  The fork is pinned on J's own ids; the override and gate 1 on
    a run dir whose RunOpen declares a forked seed of the F1 volume's
    geometry and whose certificates are the emitted ones.
    """
    from holo.receiver.format import identity

    from analyzer import truth as truth_mod

    from ._analyzer_fixtures import emitted_volume

    fossil = "L:c2-cmy8-r0547@53x37"
    assert identity.resolve_format_ref(fossil).seed == (
        b"holo/v2/c2-cmy8-r0547@53x37")
    assert identity.resolve_format_ref(fossil).seed != (
        identity.resolve_format_ref("c2-cmy8-r0547@53x37").seed), (
        "the bare id forks the seed")

    volume = emitted_volume()
    forked_ref = "c3-cmy8-r0550@10x10"
    run_dir = _tiny_run_dir(tmp_path, forked_ref)
    declared = inputs.load_run(run_dir)
    assert declared.format_ref == forked_ref
    assert declared.row.seed != volume.row.seed
    assert "format_ref_override" not in declared.provenance
    forked_truth = truth_mod.load_truth(None, volume.payload_path,
                                        declared.row, 1,
                                        format_ref=declared.format_ref)
    with pytest.raises(truth_mod.TruthError, match="WRONG CERTIFICATE"):
        truth_mod.gate_certificates(forked_truth, declared)

    run = inputs.load_run(run_dir, format_ref=volume.format_ref)
    assert run.format_ref == volume.format_ref
    assert run.row.seed == volume.row.seed
    assert run.provenance["format_ref_override"] == {
        "run_open": forked_ref, "used": volume.format_ref}
    gate = truth_mod.gate_certificates(
        truth_mod.load_truth(None, volume.payload_path, run.row, 1,
                             format_ref=run.format_ref), run)
    assert gate["mismatches"] == 0 and gate["checked"] == len(run.certificates)
    assert gate["checked"] == 300
