from __future__ import annotations

import dataclasses
import inspect
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.format import pilots, tile_codec
from holo.receiver.format.identity import build_site_geometry, resolve_format_ref
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import tiles, tiles_sched
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_arms_retry_is_armed_by_the_attempt_alone_not_by_close_readiness`,
# `test_bp_budget_is_a_property_of_the_stage_alone`,
# `test_failed_scan_yields_exactly_one_retry_subject`,
# `test_failed_union_yields_a_ppc_scoped_retry_subject`,
# `test_k_eff_bits_and_evidence_arity_follow_the_family`,
# `test_ordinary_stage_and_outcome_vocabulary_is_pinned`,
# `test_source_tag_names_the_stage_that_minted_the_certificate`.
# 2026-10-12 (CMY-RECEIVER-PLAN A3): `ARITY_BY_FAMILY values` [1, 3, 6]
# -> [1, 3, 3, 6] -- cmy joins with its three W-relative state scores
# (C, M, Y), which `tiles.stream_llrs` demaps per label stream.

K_FOSSIL = "L:c3-r0550@2240x1536"
CMY8_FOSSIL = "L:c2-cmy8-p120-v0@3328x2304"

PIN_ADDRESS = (0, 3, 5)
HARD_LLR = 4.0

# DESCRIPTOR-PLAN item 12 executed (D6 Wave 2): the freeze row, the
# TileEvidence fact and the epoch machinery are deleted; tile attempts
# assemble their decoder input at fire time
FREEZE_ROW_DELETED_SYMBOLS = (
    "freeze_tile_evidence", "latest_components", "FREEZE_DESCRIPTOR",
    "CORE_ARM", "arms_scan", "prepare_freeze")


@pytest.fixture(scope="module")
def k_row() -> object:
    return resolve_format_ref(K_FOSSIL)


@pytest.fixture(scope="module")
def k_geometry(k_row) -> object:
    return build_site_geometry(k_row)


@pytest.fixture(scope="module")
def cmy8_row() -> object:
    return resolve_format_ref(CMY8_FOSSIL)


def _attempt_fact(stage: str, outcome: str,
                  components: tuple = (("cap-a", 0),),
                  stream_id: str = "main") -> data.AttemptFact:
    page, ty, tx = PIN_ADDRESS
    return data.AttemptFact(
        page=page, ty=ty, tx=tx, stream_id=stream_id, stage=stage,
        outcome=outcome, n_informative=1800, n_iters=60, syndrome_ok=False,
        crc_ok=False, components=components)


def _cut(capture_id: str, level_index: int = 0,
         values: np.ndarray | None = None,
         observed_flat: np.ndarray | None = None) -> tiles.TileCut:
    page, ty, tx = PIN_ADDRESS
    return tiles.TileCut(
        capture_id=capture_id, level_index=level_index, page=page, ty=ty,
        tx=tx,
        values=(np.zeros((4, 1), np.float32) if values is None else values),
        observed_flat=(np.arange(4, dtype=np.uint16)
                       if observed_flat is None else observed_flat))


def test_the_freeze_row_is_deleted_and_assembly_is_fire_time():
    checks = _h3_support.Checks("DESCRIPTOR-PLAN item 12 deletions")
    for symbol in FREEZE_ROW_DELETED_SYMBOLS:
        checks.check(f"tiles.{symbol} is deleted",
                     not hasattr(tiles, symbol),
                     "the freeze machinery must stay deleted (item 12)")
    checks.check("data.TileEvidence is deleted",
                 not hasattr(data, "TileEvidence"),
                 "the TileEvidence fact died with the freeze row")
    for symbol in ("TileCut", "assemble_tile", "assemble_union",
                   "cover_keys", "evidence_cover_cells",
                   "color_cover_cells"):
        checks.check(f"tiles.{symbol} exists", hasattr(tiles, symbol),
                     "fire-time assembly is the replacement mechanism")
    checks.assert_clean()


def test_ordinary_stage_and_outcome_vocabulary_is_pinned():
    _h3_support.assert_measured("ORDINARY_STAGES", tiles.ORDINARY_STAGES,
                               ("scan", "union"))
    _h3_support.assert_measured("STAGE_RETRY150", tiles.STAGE_RETRY150,
                               "retry150")
    _h3_support.assert_measured("OUTCOME_FAILED", tiles.OUTCOME_FAILED,
                               "attempted_failed")
    _h3_support.assert_measured("OUTCOME_CERTIFIED", tiles.OUTCOME_CERTIFIED,
                               "certified")
    _h3_support.assert_measured("OUTCOME_BELOW_FLOOR",
                               tiles.OUTCOME_BELOW_FLOOR,
                               "below_attempt_floor")


def test_bp_budget_is_a_property_of_the_stage_alone():
    _h3_support.assert_measured("BP_ALPHA", tiles.BP_ALPHA, 0.8)
    _h3_support.assert_measured(
        "max_iters_for",
        tuple(tiles.max_iters_for(stage)
              for stage in ("scan", "union", "retry150")),
        (60, 60, 150))


def test_arms_retry_is_armed_by_the_attempt_alone_not_by_close_readiness():
    fact = _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED)
    assert tiles.arms_retry(fact, False) is True
    _h3_support.assert_measured(
        "arms_retry parameters",
        tuple(inspect.signature(tiles.arms_retry).parameters),
        ("fact", "certified"))
    source = inspect.getsource(tiles.arms_retry)
    for forbidden in ("close", "ready", "k_total", "metadata"):
        assert forbidden not in source, forbidden


@pytest.mark.parametrize(
    "stage,outcome,certified,arms",
    [(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED, False, True),
     (tiles.STAGE_UNION, tiles.OUTCOME_FAILED, False, True),
     (tiles.STAGE_SCAN, tiles.OUTCOME_FAILED, True, False),
     (tiles.STAGE_SCAN, tiles.OUTCOME_CERTIFIED, False, False),
     (tiles.STAGE_SCAN, tiles.OUTCOME_BELOW_FLOOR, False, False),
     (tiles.STAGE_RETRY150, tiles.OUTCOME_FAILED, False, False)])
def test_retry_arming_table(stage, outcome, certified, arms):
    assert tiles.arms_retry(
        _attempt_fact(stage, outcome), certified) is arms


def test_failed_scan_yields_exactly_one_retry_subject():
    fact = _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED)
    store = SimpleNamespace(has_certificate=lambda key: False)
    page, ty, tx = PIN_ADDRESS
    _h3_support.assert_measured(
        "scan retry subject", tiles_sched._retry_subjects(store, fact),
        ((tiles.STAGE_SCAN, page, ty, tx, "main", 0, "cap-a"),))


def test_failed_union_yields_a_ppc_scoped_retry_subject():
    fact = _attempt_fact(
        tiles.STAGE_UNION, tiles.OUTCOME_FAILED,
        components=(("cap-a", 2), ("cap-b", 1)))
    levels = {("cap-a", 2): Fraction(6), ("cap-b", 1): Fraction(6)}
    store = SimpleNamespace(
        has_certificate=lambda key: False,
        level=lambda capture_id, index: SimpleNamespace(
            ppc=levels[(capture_id, index)]))
    page, ty, tx = PIN_ADDRESS
    _h3_support.assert_measured(
        "union retry subject", tiles_sched._retry_subjects(store, fact),
        ((tiles.STAGE_UNION, page, ty, tx, "main", Fraction(6), None),))


def test_a_certified_tile_arms_no_retry_subject():
    fact = _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED)
    page, ty, tx = PIN_ADDRESS
    certified = {(page, ty, tx, "main")}
    store = SimpleNamespace(has_certificate=certified.__contains__)
    assert tiles_sched._retry_subjects(store, fact) == ()


# THE cmy RETRY'S PRICE (the owner's price balance, 2026-10-18): on cmy
# alone `tiles.retry` sits above the residue rows' first fires and below
# cold placement; every other family, and `tiles.cond` on every family,
# keeps the scan's price of the baseline's lane.
CMY_REF = "c3-cmy-r0850@10x10"
CMY8_REF = "c3-cmy8-r0550x0550x0547@10x10"
K_REF = "c3-k-r0550@10x10"


def _priced_store(format_ref: str, union_rung: int) -> object:
    return SimpleNamespace(row=resolve_format_ref(format_ref),
                           union_rung_ordinal=lambda ppc: union_rung)


@pytest.mark.parametrize("format_ref,base,stage", [
    (K_REF, 20, "payload"), (CMY8_REF, 20, "payload"),
    (CMY_REF, 241, "retry_cmy")])
@pytest.mark.parametrize("rung", (0, 2))
def test_the_retry_price_and_stage_follow_the_family(format_ref, base,
                                                     stage, rung):
    retry = tiles_sched.RETRY_DESCRIPTOR
    store = _priced_store(format_ref, rung)
    page, ty, tx = PIN_ADDRESS
    for subject in ((tiles.STAGE_SCAN, page, ty, tx, "s", rung, "cap-a"),
                    (tiles.STAGE_UNION, page, ty, tx, "s", Fraction(6),
                     None)):
        assert retry.stage(store, subject) == stage
        for attempts in (0, 1, 5):
            assert retry.cost(store, subject, stage, attempts, 0) \
                == base + 2 * rung
    assert (stage, base) in retry.prices


@pytest.mark.parametrize("format_ref", (K_REF, CMY8_REF, CMY_REF))
@pytest.mark.parametrize("rung", (0, 2))
def test_cond_keeps_the_scan_price_on_every_family(format_ref, rung):
    cond = tiles_sched.COND_DESCRIPTOR
    store = _priced_store(format_ref, rung)
    page, ty, tx = PIN_ADDRESS
    subject = (tiles.STAGE_SCAN, page, ty, tx, "lo", rung, "cap-a")
    assert cond.stage(store, subject) == tiles_sched.STAGE_PAYLOAD
    assert cond.cost(store, subject, "payload", 0, 0) == 20 + 2 * rung


def test_the_cmy_retry_sits_between_swim_first_fire_and_cold_placement():
    from holo.receiver.lib.decimate import auto_ppc_levels
    from holo.receiver.plugins import place, swim
    # the rung index runs over the decimation ladder; derived, not typed:
    # the cmy record's pitches (c2, c3) and c4, at the Canon's 4800 dpi
    # -- a deeper ladder (c5 at 4800) fails here instead of drifting
    deepest_rung = max(len(auto_ppc_levels(4800, Fraction(cell_dots, 600)))
                       for cell_dots in (2, 3, 4)) - 1
    assert deepest_rung == 4
    assert swim.SWIM_COST < tiles_sched.RETRY_CMY_COST
    assert (tiles_sched.RETRY_CMY_COST
            + tiles_sched.RUNG_COST * deepest_rung
            < place.STAGE_COST[place.STAGE_COLD_LIVE])


def test_an_attempt_without_components_arms_no_retry_subject():
    fact = _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED,
                         components=())
    store = SimpleNamespace(has_certificate=lambda key: False)
    assert tiles_sched._retry_subjects(store, fact) == ()


@pytest.mark.parametrize(
    "capture_ids,arms",
    [((), False), (("cap-a",), False), (("cap-a", "cap-a"), False),
     (("cap-a", "cap-b"), True), (("cap-a", "cap-b", "cap-c"), True)])
def test_arms_union_needs_two_distinct_captures(capture_ids, arms):
    components = tuple(_cut(name) for name in capture_ids)
    assert tiles.arms_union(components) is arms


def _certificate(bits: np.ndarray, source: str) -> data.Certificate:
    page, ty, tx = PIN_ADDRESS
    return data.Certificate(page, ty, tx, "main", bits, source)


def test_merge_certificate_accepts_the_first_and_keeps_the_standing_source():
    certs: dict = {}
    first = _certificate(np.zeros(4, np.uint8), "tiles/scan")
    duplicate = _certificate(np.zeros(4, np.uint8), "tiles/union")
    assert tiles.merge_certificate(certs, first) is True
    assert tiles.merge_certificate(certs, duplicate) is False
    page, ty, tx = PIN_ADDRESS
    assert certs[(page, ty, tx, "main")].source == "tiles/scan"
    assert len(certs) == 1


def test_merge_certificate_raises_on_conflicting_user_bits():
    certs: dict = {}
    tiles.merge_certificate(certs, _certificate(np.zeros(4, np.uint8), "a"))
    with pytest.raises(data.IntegrityError) as excinfo:
        tiles.merge_certificate(
            certs, _certificate(np.ones(4, np.uint8), "b"))
    assert "conflicting certificates" in str(excinfo.value)
    assert "certify different user bits" in str(excinfo.value)


# Moved here from test_h3_drift_receiver.py when the v1 receiver was retired
# 2026-09-05: it never had a v1 oracle — it is holo3 mint logic that sat in
# the drift module because the tile attempts around it were compared against
# `holo.receive.tiles`.  It walks the whole mint boundary in one go: accept,
# ignore the duplicate without losing the standing source, refuse the
# conflict.
def test_conflicting_certificate_mint_raises_integrity_error():
    bits_a = np.zeros(8, np.uint8)
    bits_b = bits_a.copy()
    bits_b[3] = 1
    certs: dict = {}
    tiles.merge_certificate(certs, data.Certificate(0, 1, 2, "main", bits_a,
                                                    "tiles/scan"))
    tiles.merge_certificate(certs, data.Certificate(0, 1, 2, "main", bits_a,
                                                    "tiles/union"))
    assert len(certs) == 1
    assert certs[(0, 1, 2, "main")].source == "tiles/scan"
    with pytest.raises(data.IntegrityError):
        tiles.merge_certificate(certs, data.Certificate(0, 1, 2, "main",
                                                        bits_b,
                                                        "tiles/union"))


def test_merge_certificate_separates_streams_at_one_address():
    certs: dict = {}
    page, ty, tx = PIN_ADDRESS
    for stream_id in ("C", "M", "Y"):
        assert tiles.merge_certificate(certs, data.Certificate(
            page, ty, tx, stream_id, np.zeros(4, np.uint8), "s")) is True
    assert sorted(certs) == [(page, ty, tx, name) for name in ("C", "M", "Y")]


def _printed_user_bits(row) -> np.ndarray:
    rng = np.random.default_rng(11)
    return rng.integers(0, 2, size=row.streams[0].user_bits, dtype=np.uint8)


def test_printed_cells_for_reproduces_the_format_known_sites(
        k_row, k_geometry):
    page, ty, tx = PIN_ADDRESS
    field = tiles.printed_cells_for(
        k_row, k_geometry, page, ty, tx, _printed_user_bits(k_row))
    assert field.shape == (TILE_CELLS, TILE_CELLS)
    counter = k_row.tile_counter(page, ty, tx)
    word = pilots.word_values(k_row.seed, counter, k_row.streams[0].plane)[0]
    cells = k_geometry.word_cells_yx
    assert np.array_equal(field[cells[:, 0], cells[:, 1]], word)


def test_printed_cells_for_round_trips_through_the_tile_decoder(
        k_row, k_geometry):
    page, ty, tx = PIN_ADDRESS
    user = _printed_user_bits(k_row)
    field = tiles.printed_cells_for(k_row, k_geometry, page, ty, tx, user)
    evidence = tiles.TileCut(
        capture_id="synthetic", level_index=0, page=page, ty=ty, tx=tx,
        values=((2.0 * field.astype(np.float32) - 1.0)
                * np.float32(HARD_LLR)).reshape(-1, 1),
        observed_flat=np.arange(tile_codec.N_CELLS, dtype=np.uint16))
    result = tiles.attempt_tile(
        k_row, k_geometry, (evidence,), "main", tiles.STAGE_SCAN)
    assert result.fact.outcome == tiles.OUTCOME_CERTIFIED
    assert result.fact.n_iters == 0
    assert result.fact.syndrome_ok is True and result.fact.crc_ok is True
    assert result.certificate is not None
    assert np.array_equal(result.certificate.user_bits, user)
    assert result.certificate.source == "tiles/scan"
    assert result.fact.components == (("synthetic", 0),)


def test_printed_cells_for_refuses_a_forked_site_geometry(k_row, k_geometry):
    page, ty, tx = PIN_ADDRESS
    forked = dataclasses.replace(
        k_geometry,
        shorten_flat=np.sort(
            (np.asarray(k_geometry.shorten_flat) + 7) % tile_codec.N_CELLS))
    with pytest.raises(data.IntegrityError) as excinfo:
        tiles.printed_cells_for(
            k_row, forked, page, ty, tx, _printed_user_bits(k_row))
    assert "wrong address or forked keystream" in str(excinfo.value)


def test_a_wrong_tile_address_prints_a_different_field(k_row, k_geometry):
    user = _printed_user_bits(k_row)
    here = tiles.printed_cells_for(k_row, k_geometry, 0, 3, 5, user)
    neighbour = tiles.printed_cells_for(k_row, k_geometry, 0, 3, 6, user)
    assert not np.array_equal(here, neighbour)


def test_non_finite_evidence_is_refused_because_zero_is_the_erasure(
        k_row, k_geometry):
    page, ty, tx = PIN_ADDRESS
    values = np.zeros((tile_codec.N_CELLS, 1), np.float32)
    values[17, 0] = np.float32("nan")
    evidence = tiles.TileCut(
        capture_id="synthetic", level_index=0, page=page, ty=ty, tx=tx,
        values=values,
        observed_flat=np.arange(tile_codec.N_CELLS, dtype=np.uint16))
    with pytest.raises(data.IntegrityError) as excinfo:
        tiles.attempt_tile(
            k_row, k_geometry, (evidence,), "main", tiles.STAGE_SCAN)
    assert "0.0 is the only erasure spelling" in str(excinfo.value)


def test_an_all_erasure_tile_lands_below_the_attempt_floor(
        k_row, k_geometry):
    page, ty, tx = PIN_ADDRESS
    evidence = tiles.TileCut(
        capture_id="synthetic", level_index=0, page=page, ty=ty, tx=tx,
        values=np.zeros((tile_codec.N_CELLS, 1), np.float32),
        observed_flat=np.arange(tile_codec.N_CELLS, dtype=np.uint16))
    result = tiles.attempt_tile(
        k_row, k_geometry, (evidence,), "main", tiles.STAGE_SCAN)
    assert result.fact.outcome == tiles.OUTCOME_BELOW_FLOOR
    assert result.certificate is None
    assert result.fact.n_informative == 0
    assert result.fact.syndrome_ok is None and result.fact.crc_ok is None


def test_k_eff_bits_and_evidence_arity_follow_the_family(k_row, cmy8_row):
    assert tiles.evidence_arity(k_row) == 1
    assert tiles.evidence_arity(cmy8_row) == 3
    _h3_support.assert_measured("ARITY_BY_FAMILY values",
                               sorted(tiles.ARITY_BY_FAMILY.values()),
                               [1, 3, 3, 6])
    assert tiles.k_eff_bits(k_row) == (
        tile_codec.tile_capacity("r0550", 0) + tile_codec.CRC_BITS
        - k_row.n_sites)


def test_unresolved_streams_and_tile_done_agree_for_a_colour_row(cmy8_row):
    certs: dict = {}
    assert tiles.unresolved_streams(cmy8_row, certs, 0, 1, 2) == (
        "C", "M", "Y")
    assert tiles.tile_done(cmy8_row, certs, 0, 1, 2) is False
    for stream_id in ("C", "M"):
        certs[(0, 1, 2, stream_id)] = data.Certificate(
            0, 1, 2, stream_id, np.zeros(4, np.uint8), "s")
    assert tiles.unresolved_streams(cmy8_row, certs, 0, 1, 2) == ("Y",)
    assert tiles.tile_done(cmy8_row, certs, 0, 1, 2) is False
    certs[(0, 1, 2, "Y")] = data.Certificate(
        0, 1, 2, "Y", np.zeros(4, np.uint8), "s")
    assert tiles.unresolved_streams(cmy8_row, certs, 0, 1, 2) == ()
    assert tiles.tile_done(cmy8_row, certs, 0, 1, 2) is True


def test_close_input_is_sorted_by_address(cmy8_row):
    certs: dict = {}
    for key in ((1, 0, 0, "Y"), (0, 2, 1, "C"), (0, 0, 0, "M")):
        certs[key] = data.Certificate(
            key[0], key[1], key[2], key[3], np.zeros(4, np.uint8), "s")
    ordered = tiles.close_input(certs)
    assert tuple((c.page, c.ty, c.tx, c.stream_id) for c in ordered) == (
        (0, 0, 0, "M"), (0, 2, 1, "C"), (1, 0, 0, "Y"))


def test_done_tile_grid_marks_only_fully_certified_tiles(cmy8_row):
    certs: dict = {}
    for stream_id in ("C", "M", "Y"):
        certs[(0, 4, 7, stream_id)] = data.Certificate(
            0, 4, 7, stream_id, np.zeros(4, np.uint8), "s")
    certs[(0, 4, 8, "C")] = data.Certificate(
        0, 4, 8, "C", np.zeros(4, np.uint8), "s")
    certs[(1, 0, 0, "C")] = data.Certificate(
        1, 0, 0, "C", np.zeros(4, np.uint8), "s")
    grid = tiles.done_tile_grid(cmy8_row, certs, 0)
    assert grid.shape == cmy8_row.tiles_yx
    assert bool(grid[4, 7]) is True
    assert bool(grid[4, 8]) is False
    assert int(grid.sum()) == 1
    assert int(tiles.done_tile_grid(cmy8_row, certs, 1).sum()) == 0


def _identity_pose(pitch_px: float, origin_yx: tuple[int, int],
                   extent: tuple[int, int, int, int]) -> tuple:
    affine = (pitch_px, 0.0, float(origin_yx[0]),
              0.0, pitch_px, float(origin_yx[1]))
    return (0, extent, affine)


def test_project_done_marks_the_supported_cells_of_certified_tiles(k_row):
    pitch_px = 3.0
    origin = (40, 55)
    shape_cells = (128, 128)
    extent = (0, 0, 128, 128)
    support = np.ones(shape_cells, bool)
    support[:, 100:] = False
    grid = np.zeros(k_row.tiles_yx, bool)
    grid[0, 1] = True
    done = tiles.project_done(
        (_identity_pose(pitch_px, origin, extent),), {0: grid}, origin,
        pitch_px, shape_cells, support)
    expected = np.zeros(shape_cells, bool)
    expected[0:TILE_CELLS, TILE_CELLS:2 * TILE_CELLS] = True
    expected &= support
    assert np.array_equal(done, expected)
    assert int(done.sum()) == TILE_CELLS * (100 - TILE_CELLS)


def test_project_done_is_empty_without_a_certified_grid(k_row):
    pitch_px = 3.0
    origin = (40, 55)
    shape_cells = (128, 128)
    done = tiles.project_done(
        (_identity_pose(pitch_px, origin, (0, 0, 128, 128)),),
        {0: np.zeros(k_row.tiles_yx, bool)}, origin, pitch_px, shape_cells,
        np.ones(shape_cells, bool))
    assert not done.any()
    assert not tiles.project_done(
        (_identity_pose(pitch_px, origin, (0, 0, 128, 128)),), {}, origin,
        pitch_px, shape_cells, np.ones(shape_cells, bool)).any()


def test_source_tag_names_the_stage_that_minted_the_certificate():
    _h3_support.assert_measured(
        "source tags",
        tuple(tiles.source_tag(stage)
              for stage in ("scan", "union", "retry150")),
        ("tiles/scan", "tiles/union", "tiles/retry150"))
