from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from holo3 import cli, data
from holo3.diag import model as diag_model
from holo3.diag import readout as diag_readout
from holo3.format.identity import Family
from holo3.lib import decimate
from holo3.plugins import intake, tiles
from holo3.tests import _h3_facts, _h3_sims, _h3_support

PITCH_C3 = Fraction(1, 200)

CAP_X = "aa" * 32
CAP_Y = "bb" * 32
CAP_Z = "cc" * 32

LADDER_X = (Fraction(2), Fraction(8, 3), Fraction(16, 3))
LADDER_Y = (Fraction(4, 3), Fraction(2), Fraction(8, 3))
LADDER_Z = (Fraction(2), Fraction(4))

PIN_TILE = (0, 3, 3)

SHARED_EVIDENCE_PPC = Fraction(3)
A_ONLY_PPC = Fraction(6)
UNPLACED_PPC = Fraction(2)
UNION_TILE_COLUMNS = (1, 2, 3, 4, 5)
# 2026-08-30, the done-geometry gate: the second capture's window over
# these two tiles was suppressed before it ever calibrated (their every
# stream was already certified), so no second cover ever formed and the
# union subject is never born.  Measured on the pre-gate tree: all three
# union JOBS of this decode fired at (0, 3, 3) — these two subjects were
# born and never fired, and could not have (`tiles.union` refuses a tile
# with no uncertified stream).  The run's 49 certificates and its
# payload are unchanged.
DONE_GATED_UNION_TILES = ((0, 6, 1), (0, 6, 2))
TILE_ROWS = tuple(range(_h3_sims.MIXED_TILES))
STAGE_UNION_MAX_ITERS = 60


def _capture_fact(capture_id: str, dpi: float,
                  ppcs: tuple[Fraction, ...]) -> data.Capture:
    levels = tuple(
        data.Level(index=index, ppc=ppc, scale=Fraction(1),
                   shape_px=(64, 64), label=f"l{index:02d}")
        for index, ppc in enumerate(ppcs))
    return data.Capture(
        capture_id=capture_id, path=Path(capture_id[:8]), dpi=dpi,
        shape_px=(64, 64), channels=1, platen_backing=0.9, levels=levels,
        plane_dir=Path("planes"))


@pytest.fixture()
def ladder_store() -> object:
    instance = _h3_facts.new_engine()
    instance._ingest(_capture_fact(CAP_X, 1600.0, LADDER_X))
    instance._ingest(_capture_fact(CAP_Y, 400.0, LADDER_Y))
    instance._ingest(_capture_fact(CAP_Z, 1200.0, LADDER_Z))
    return instance


def test_the_cross_capture_join_maps_level_to_ppc_through_own_ladders(
        ladder_store):
    assert ladder_store.level_of_ppc(CAP_X, Fraction(8, 3)) == 1
    assert ladder_store.level_of_ppc(CAP_Y, Fraction(8, 3)) == 2
    assert ladder_store.level_of_ppc(CAP_Z, Fraction(8, 3)) is None
    assert ladder_store.union_rung_ordinal(Fraction(8, 3)) == 1
    assert ladder_store.union_rung_ordinal(Fraction(2)) == 0


def test_pairing_is_fraction_equality_never_closeness(ladder_store):
    near = decimate.as_fraction(8 / 3)
    assert near != Fraction(8, 3)
    assert ladder_store.level_of_ppc(CAP_X, near) is None
    page, ty, tx = PIN_TILE
    ladder_store._tile_cover_k[(page, ty, tx, CAP_X, 1)] = {"w1"}
    ladder_store._tile_cover_k[(page, ty, tx, CAP_Y, 2)] = {"w2"}
    assert ladder_store.cover_lanes(page, ty, tx, Fraction(8, 3)) == (
        (CAP_X, 1), (CAP_Y, 2))
    assert ladder_store.cover_lanes(page, ty, tx, near) == ()


def _union_probe_store(cover: tuple[tuple[str, int], ...]) -> object:
    page, ty, tx = PIN_TILE
    return SimpleNamespace(
        color_row_cover_tiles=lambda key: ((page, ty, tx, CAP_X, 1),),
        level=lambda cid, index: SimpleNamespace(ppc=Fraction(8, 3)),
        cover_lanes=lambda page, ty, tx, ppc: cover)


def _color_row_fact() -> object:
    return SimpleNamespace(capture_id=CAP_X, level_index=1, page=0,
                           patch_ordinal=0)


def test_a_ppc_reached_by_one_capture_mints_no_union_subject():
    store = _union_probe_store(((CAP_X, 1),))
    assert tiles._union_subjects(store, _color_row_fact()) == ()


def test_two_distinct_captures_at_one_exact_ppc_mint_the_union_subject():
    store = _union_probe_store(((CAP_X, 1), (CAP_Y, 2)))
    page, ty, tx = PIN_TILE
    _h3_support.assert_golden(
        "union subject at 8/3",
        tiles._union_subjects(store, _color_row_fact()),
        ((page, ty, tx, Fraction(8, 3)),))


def test_same_source_at_two_dpis_is_the_q2_fatal_refusal(tmp_path: Path):
    import tifffile

    image = np.full((64, 64), 200, np.uint8)
    first = tmp_path / "a.tiff"
    second = tmp_path / "b.tiff"
    tifffile.imwrite(first, image)
    tifffile.imwrite(second, image)
    sha = intake.sha256_file(first)
    assert sha == intake.sha256_file(second)
    with pytest.raises(ValueError) as excinfo:
        intake.ingest_captures((first, second), (1200.0, 600.0), PITCH_C3,
                               Family.K, tmp_path / "run")
    message = str(excinfo.value)
    assert "Q2" in message
    assert "1200.0" in message
    assert "600.0" in message
    assert sha in message


def test_the_intake_asserts_a_strictly_ascending_ladder():
    good = _capture_fact(CAP_X, 1600.0, LADDER_X).levels
    intake.assert_ascending_ladder(CAP_X, good)
    for bad in ((Fraction(3), Fraction(2)),
                (Fraction(2), Fraction(2), Fraction(3))):
        levels = _capture_fact(CAP_X, 1200.0, bad).levels
        with pytest.raises(data.IntegrityError) as excinfo:
            intake.assert_ascending_ladder(CAP_X, levels)
        assert "strictly ascending" in str(excinfo.value)


def test_every_built_ladder_passes_the_intake_invariant():
    for dpi in (600.0, 1000.0, 1200.0, 1600.0, 2400.0, 4800.0):
        levels = intake.build_levels(dpi, PITCH_C3, (256, 256))
        intake.assert_ascending_ladder("probe", levels)
        assert intake.levels_ppc(levels) == tuple(
            str(level.ppc) for level in levels)


def _open_event(capture: str, ladder: tuple[str, ...],
                duplicate: bool = False) -> data.CaptureOpen:
    return data.CaptureOpen(capture=capture, dpi=600.0, shape_yx=(9, 9),
                            channels=1, duplicate=duplicate,
                            levels_ppc=ladder)


def test_a_disjoint_ladder_capture_gets_the_isolation_advisory():
    folded = diag_model.fold(diag_model.empty(), [
        _open_event(CAP_X, ("4/3",)),
        _open_event(CAP_Y, ("2", "4")),
        _open_event(CAP_Z, ("2", "8/3"))])
    line = diag_readout.ladder_isolation_advisory(folded)
    assert line is not None
    assert CAP_X[:12] in line
    assert "4/3" in line
    assert "certificate-only" in line
    assert CAP_Y[:12] not in line
    assert CAP_Z[:12] not in line


def test_captures_sharing_any_rung_get_no_isolation_advisory():
    folded = diag_model.fold(diag_model.empty(), [
        _open_event(CAP_X, ("2", "8/3")),
        _open_event(CAP_Y, ("2", "4"))])
    assert diag_readout.ladder_isolation_advisory(folded) is None


def test_a_single_capture_is_never_isolated():
    folded = diag_model.fold(diag_model.empty(), [
        _open_event(CAP_X, ("4/3",))])
    assert diag_readout.ladder_isolation_advisory(folded) is None


def test_the_isolation_advisory_rides_the_cli_status_rows():
    events = [_open_event(CAP_X, ("4/3",)), _open_event(CAP_Y, ("2", "4"))]
    result = data.RunResult(status="open", payload=None,
                            payload_sha256=None, certified=0)
    rows = cli._status_rows(events, result)
    assert any(row.startswith("ladder   ") and "certificate-only" in row
               for row in rows)


def test_mixed_pair_artefacts_reproduce_their_frozen_shas(sim_k_mixed):
    capture_a, capture_b = sim_k_mixed
    _h3_support.assert_golden("mixed capture A tiff sha256",
                              _h3_sims.sha256_file(capture_a.tiff),
                              _h3_sims.MIXED_A_TIFF_SHA256)
    _h3_support.assert_golden("mixed capture B tiff sha256",
                              _h3_sims.sha256_file(capture_b.tiff),
                              _h3_sims.MIXED_B_TIFF_SHA256)
    assert capture_a.dpi == 2 * capture_b.dpi


def test_mixed_decode_is_verified_and_byte_exact(decode_k_mixed_w1,
                                                 sim_k_mixed):
    capture_a, _capture_b = sim_k_mixed
    assert decode_k_mixed_w1.exit_code == 0
    assert decode_k_mixed_w1.status == "verified"
    assert decode_k_mixed_w1.payload == capture_a.payload_data
    _h3_support.assert_golden("recovered mixed payload sha256",
                              decode_k_mixed_w1.payload_sha256,
                              _h3_sims.K_PAYLOAD_SHA256)
    assert decode_k_mixed_w1.certified == _h3_sims.MIXED_TILES ** 2


def test_mixed_workers_do_not_change_the_payload(decode_k_mixed_w1,
                                                 decode_k_mixed_w8):
    assert decode_k_mixed_w8.exit_code == 0
    assert decode_k_mixed_w8.payload == decode_k_mixed_w1.payload


def test_union_subjects_exist_exactly_at_the_shared_evidence_ppc(
        decode_k_mixed_w1):
    subjects = decode_k_mixed_w1.union_subjects
    expected = tuple(sorted(
        (0, ty, tx, SHARED_EVIDENCE_PPC)
        for ty in TILE_ROWS for tx in UNION_TILE_COLUMNS
        if (0, ty, tx) not in DONE_GATED_UNION_TILES))
    _h3_support.assert_golden("mixed union subject census", subjects,
                              expected)
    ppcs = {subject[3] for subject in subjects}
    assert ppcs == {SHARED_EVIDENCE_PPC}
    assert A_ONLY_PPC not in ppcs
    assert UNPLACED_PPC not in ppcs


def _certified_attempts(record) -> dict[tuple, tuple]:
    return {key: key[6] for key, outcome in record.attempt_outcomes.items()
            if outcome == tiles.OUTCOME_CERTIFIED}


def test_certificates_are_fed_by_both_captures(decode_k_mixed_w1):
    sha_a = _h3_sims.MIXED_A_TIFF_SHA256
    sha_b = _h3_sims.MIXED_B_TIFF_SHA256
    fed: dict[str, set] = {sha_a: set(), sha_b: set()}
    for key, components in _certified_attempts(decode_k_mixed_w1).items():
        for capture_id, _level in components:
            fed[capture_id].add((key[0], key[1], key[2]))
    hole_a = {(0, ty, _h3_sims.MIXED_HOLE_A_TILE_COLUMN)
              for ty in TILE_ROWS}
    assert fed[sha_b] >= hole_a
    assert len(fed[sha_a]) >= len(TILE_ROWS) * (_h3_sims.MIXED_TILES - 2)
    covered = fed[sha_a] | fed[sha_b]
    assert covered == {(page, ty, tx)
                       for page, ty, tx, _s in decode_k_mixed_w1.certificates}


def test_the_split_tile_certifies_only_at_the_mixed_union(
        decode_k_mixed_w1):
    sha_a = _h3_sims.MIXED_A_TIFF_SHA256
    sha_b = _h3_sims.MIXED_B_TIFF_SHA256
    ty, tx = _h3_sims.MIXED_UNION_TILE_YX
    outcomes = {
        (key[4], key[6]): outcome
        for key, outcome in decode_k_mixed_w1.attempt_outcomes.items()
        if (key[0], key[1], key[2]) == (0, ty, tx)}
    solo_a = outcomes[(tiles.STAGE_SCAN, ((sha_a, 1),))]
    solo_b = outcomes[(tiles.STAGE_SCAN, ((sha_b, 1),))]
    assert solo_a == tiles.OUTCOME_BELOW_FLOOR
    assert solo_b == tiles.OUTCOME_BELOW_FLOOR
    # component_signature sorts on capture sha; a re-freeze re-orders it
    union_key = (tiles.STAGE_UNION, tuple(sorted(((sha_a, 1), (sha_b, 1)))))
    assert outcomes[union_key] == tiles.OUTCOME_CERTIFIED
    assert (0, ty, tx, "main") in decode_k_mixed_w1.certificates
