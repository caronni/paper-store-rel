from __future__ import annotations

import dataclasses
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver import data, engine
from holo.receiver.format import identity
from holo.receiver.lib import geometry
from holo.receiver.lib.pava import N_CONTEXT_BINS, calibration_llr
from holo.receiver.plugins import (
    calibrate, local_ctx, refine, tiles, tiles_sched)
from holo.receiver.tests import (
    _h3_facts,
    _h3_fixture_geometry,
    _h3_support,
)

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-18 (the owner's price balance): `tiles.local` escalates, base
# + base x earlier fires -- the "no escalation" pricing test is replaced
# by `test_the_row_pays_its_base_once_and_its_base_again_per_earlier_fire`
# (measure/sched_trace/YIELD-OVER-CPU-2026-10-18.md §5-6); no measured
# value moved.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_the_radius_bound_is_derived_from_the_window_grid`,
# `test_the_row_can_produce_nothing_but_an_attempt_and_a_certificate`.

FORMAT_REF = _h3_facts.FORMAT_REF
COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
CAPTURE_ID = _h3_facts.CAPTURE_ID
PPC = Fraction(4)
PAGE = 0
STREAM_ID = "main"
TARGET = (0, 0)

# two tiles on a side: the window's own reach, and small enough that the
# fixture stays a unit test rather than a decode
SPAN_CELLS = 2 * geometry.TILE_CELLS
WIDE_CELLS = geometry.WINDOW_CELLS
WID = (CAPTURE_ID, 0, 0, (0, 0, SPAN_CELLS, SPAN_CELLS))
WIDE_WID = (CAPTURE_ID, 0, 0, (0, 0, WIDE_CELLS, WIDE_CELLS))

ROW = identity.resolve_format_ref(FORMAT_REF)
GEOMETRY = _h3_fixture_geometry.memoised_site_geometry(ROW)
LOOKUP = calibrate.build_site_lookup(GEOMETRY)

INK_SCORE = 1.0
PAPER_SCORE = -1.0
KNOTS = (PAPER_SCORE, INK_SCORE)
PROBS = (0.02, 0.98)

ARMING_MATRIX = (
    (tiles.STAGE_SCAN, tiles.OUTCOME_FAILED, True),
    (tiles.STAGE_UNION, tiles.OUTCOME_FAILED, True),
    (tiles.STAGE_RETRY150, tiles.OUTCOME_FAILED, True),
    (tiles.STAGE_LOCAL150, tiles.OUTCOME_FAILED, False),
    (tiles.STAGE_SCAN, tiles.OUTCOME_CERTIFIED, False),
    (tiles.STAGE_SCAN, tiles.OUTCOME_BELOW_FLOOR, False),
)


def _cells(size: int) -> np.ndarray:
    return _h3_facts.tile_cells(size)


def _placement(wid: tuple, size: int) -> data.Placement:
    return dataclasses.replace(_h3_facts.placement(wid),
                               local_cells_yx=_cells(size))


def _evidence(wid: tuple, size: int) -> data.WindowEvidence:
    cells = _cells(size)
    reference = calibrate.format_reference_values(ROW, LOOKUP, PAGE, cells)
    scores = np.where(reference > 0, INK_SCORE, PAPER_SCORE).astype(np.float32)
    knots = np.asarray(KNOTS, np.float64)
    probs = np.asarray(PROBS, np.float64)
    marginal = np.asarray(calibration_llr(scores, knots, probs), np.float32)
    return data.WindowEvidence(
        window_id=wid, capture_id=wid[0], level_index=wid[1],
        region_index=wid[2], patch_ordinal=0, page=PAGE,
        page_cells_yx=cells, scores=scores, reference_values=reference,
        knots=knots, probs=probs, n_search=int(np.count_nonzero(reference >= 0)),
        marginal_llr=marginal, printed_llr=marginal, accepted=True,
        refusal_reason="", heldout_logloss=0.1, ctx_adopted=False)


def _seeded(wid: tuple = WID, size: int = SPAN_CELLS) -> engine._Engine:
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window(wid, ordinal=0))
    instance._ingest(_placement(wid, size))
    instance._ingest(_evidence(wid, size))
    return instance


def _certificate(ty: int, tx: int) -> data.Certificate:
    return data.Certificate(
        page=PAGE, ty=ty, tx=tx, stream_id=STREAM_ID,
        user_bits=np.zeros(ROW.streams[0].user_bits, np.uint8),
        source="tiles/scan")


def _certify(instance: engine._Engine, ty: int, tx: int) -> None:
    instance._ingest(_certificate(ty, tx))


#: the subject is the tile LANE since 2026-09-21: one local fit per
#: tile per footing, every armed stream read off it
def _subject(ty: int = 0, tx: int = 0) -> tuple:
    return (PAGE, ty, tx, PPC)


def _attempt_fact(stage: str, outcome: str, ty: int = 0, tx: int = 0,
                  stream_id: str = STREAM_ID,
                  generation: int = 0) -> data.AttemptFact:
    return data.AttemptFact(
        page=PAGE, ty=ty, tx=tx, stream_id=stream_id, stage=stage,
        outcome=outcome, n_informative=1000, n_iters=60, syndrome_ok=False,
        crc_ok=False, components=((CAPTURE_ID, 0),), generation=generation)


def _arm(instance: engine._Engine, ty: int = 0, tx: int = 0,
         stream_id: str = STREAM_ID) -> None:
    """The failed scan verdict the row is armed by, at the LIVE generation.

    `eligible` reads the verdict now, not only at birth: a tile-lane
    with no current failure is not residue, it is unfinished or
    finished work.  So every admission test seeds one.
    """
    instance._ingest(_attempt_fact(
        tiles.STAGE_SCAN, tiles.OUTCOME_FAILED, ty, tx, stream_id,
        generation=instance.tile_lane_generation(
            (PAGE, ty, tx, CAPTURE_ID, 0))))


def _donor_field(ty: int, tx: int) -> np.ndarray:
    fields = refine.certified_fields(ROW, GEOMETRY, (_certificate(ty, tx),))
    return fields[(PAGE, ty, tx)]


# --- the neighbourhood, and where its size comes from -------------------


def test_the_neighbourhood_is_exactly_what_the_covering_windows_cover():
    store = _seeded()
    lane = (CAPTURE_ID, 0)
    wids = local_ctx.covering_windows(store, PAGE, 0, 0, lane)
    assert wids == (WID,)
    union = sorted({tile for wid in wids
                    for tile in store.evidence_reach(wid)})
    got = local_ctx.neighbourhood_tiles(store, PAGE, 0, 0, PPC)
    assert got == tuple(union)
    assert got == ((0, 0), (0, 1), (1, 0), (1, 1))


def test_the_neighbourhood_follows_the_window_geometry_not_a_constant():
    narrow = local_ctx.neighbourhood_tiles(_seeded(), PAGE, 0, 0, PPC)
    wide = local_ctx.neighbourhood_tiles(
        _seeded(WIDE_WID, WIDE_CELLS), PAGE, 0, 0, PPC)
    assert len(wide) > len(narrow), (
        "a wider window must see more tiles: the neighbourhood is read "
        "from the covering windows, never from a tuned radius")
    span = -(-geometry.WINDOW_CELLS // geometry.TILE_CELLS)
    assert len(wide) == span * span


def test_the_radius_bound_is_derived_from_the_window_grid():
    _h3_support.assert_measured(
        "neighbourhood radius bound", local_ctx.MAX_NEIGHBOUR_TILE_RADIUS,
        -(-(geometry.WINDOW_CELLS - 1) // geometry.TILE_CELLS))
    store = _seeded(WIDE_WID, WIDE_CELLS)
    for ty, tx in local_ctx.neighbourhood_tiles(store, PAGE, 0, 0, PPC):
        assert abs(ty - TARGET[0]) <= local_ctx.MAX_NEIGHBOUR_TILE_RADIUS
        assert abs(tx - TARGET[1]) <= local_ctx.MAX_NEIGHBOUR_TILE_RADIUS


def test_the_neighbourhood_is_deterministic_and_sorted():
    store = _seeded()
    first = local_ctx.neighbourhood_tiles(store, PAGE, 0, 0, PPC)
    second = local_ctx.neighbourhood_tiles(store, PAGE, 0, 0, PPC)
    assert first == second == tuple(sorted(first))


def test_a_window_with_no_evidence_yields_no_neighbourhood():
    instance = _h3_facts.new_engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window(WID, ordinal=0))
    instance._ingest(_placement(WID, SPAN_CELLS))
    assert local_ctx.neighbourhood_tiles(instance, PAGE, 0, 0, PPC) == ()


# --- eligibility: structural, never a bar ------------------------------


def test_a_tile_with_no_certified_neighbour_never_fires():
    store = _seeded()
    _arm(store)
    assert local_ctx._local_eligible(store, _subject()) is False
    assert local_ctx.prepare_local(store, _subject(),
                                   local_ctx.STAGE_LOCAL) is None


def test_one_certified_neighbour_is_the_whole_admission_rule():
    store = _seeded()
    _certify(store, 0, 1)
    _arm(store)
    assert local_ctx._local_eligible(store, _subject()) is True
    assert local_ctx.prepare_local(store, _subject(),
                                   local_ctx.STAGE_LOCAL) is not None


def test_the_targets_own_certificate_is_never_its_own_neighbour():
    store = _seeded()
    _certify(store, 0, 0)
    reach = local_ctx.neighbourhood_tiles(store, PAGE, 0, 0, PPC)
    assert local_ctx.certified_neighbours(store, PAGE, reach, TARGET) == ()


def test_a_certified_tile_never_fires_and_retires():
    store = _seeded()
    _certify(store, 0, 1)
    _arm(store)
    _certify(store, 0, 0)
    assert local_ctx._local_eligible(store, _subject()) is False
    assert local_ctx._local_retire(store, _subject()) == "certified"
    assert local_ctx.prepare_local(store, _subject(),
                                   local_ctx.STAGE_LOCAL) is None


def test_an_uncertified_tile_is_never_retired():
    store = _seeded()
    _certify(store, 0, 1)
    _arm(store)
    assert local_ctx._local_retire(store, _subject()) is None


def test_only_a_certificate_takes_a_stream_out_of_the_residue():
    """A failure ARMS, and the arming keeps until the tile certifies.

    Two narrower readings were built on this branch and refused on
    review (2026-09-21): arming only on a verdict at the tile-lane's
    CURRENT generation, and arming on the standing verdict whatever its
    generation.  `_attempt_latest` holds ONE verdict per (stage, lane),
    so both lose the rung the moment a re-read comes back
    `below_attempt_floor` — and `_local_retire` is certificate-only, so
    the bookmark would live on, never eligible, never retired.
    Measured on the traced sheet-H run: 2,667 such transitions and
    seven uncertified tile-streams ending the run in that state.  Base
    gated on the certificate alone and so does this.
    """
    store = _seeded()
    _certify(store, 0, 1)
    _arm(store)
    assert local_ctx.armed_streams(store, PAGE, 0, 0, PPC) == (STREAM_ID,)
    # the evidence moves (a re-fit bumps the generation) and the chain
    # head's next read comes back BELOW the attempt floor
    store._advance_tile_lanes({(PAGE, 0, 0, CAPTURE_ID, 0)})
    store._ingest(_attempt_fact(
        tiles.STAGE_SCAN, tiles.OUTCOME_BELOW_FLOOR,
        generation=store.tile_lane_generation((PAGE, 0, 0, CAPTURE_ID, 0))))
    assert store.attempt_verdict(PAGE, 0, 0, STREAM_ID, tiles.STAGE_SCAN,
                                 (CAPTURE_ID, 0))[0] == (
                                     tiles.OUTCOME_BELOW_FLOOR)
    assert local_ctx.armed_streams(store, PAGE, 0, 0, PPC) == (STREAM_ID,), (
        "the rung this tile was armed for is still owed: local builds "
        "its OWN components, so scan's floor is not local's")
    assert local_ctx._local_eligible(store, _subject()) is True
    assert local_ctx.prepare_local(store, _subject(),
                                   local_ctx.STAGE_LOCAL) is not None
    assert local_ctx._local_retire(store, _subject()) is None


OTHER_CAPTURE_ID = "deadbeef" * 8


def _second_capture(capture_id: str = OTHER_CAPTURE_ID,
                    ppc: Fraction = PPC) -> data.Capture:
    base = _h3_facts.capture()
    level = dataclasses.replace(base.levels[0], ppc=ppc)
    return dataclasses.replace(base, capture_id=capture_id, levels=(level,))


def _lane_fact(capture_id: str, stage: str, outcome: str,
               components: tuple | None = None) -> data.AttemptFact:
    return dataclasses.replace(
        _attempt_fact(stage, outcome),
        components=((capture_id, 0),) if components is None else components)


def test_a_failure_keeps_arming_after_its_lane_leaves_the_cover():
    """The franchise survives the lane that earned it (2026-10-03).

    The 2026-09-21 repair asked the monotone ledger only at the lanes
    covering the tile NOW, so a lane that failed and then left the
    cover -- its window's evidence refused -- took the arming with it
    when the lane that replaced it had produced only a below-floor
    read: the stream unarmed, the bookmark certificate-retired only,
    never eligible (external review claim 2, SCHED-OPEN #5(a)).  The
    footing ledger keeps it.
    """
    store = _seeded()
    _certify(store, 0, 1)
    wid_b = (OTHER_CAPTURE_ID,) + WID[1:]
    store._ingest(_second_capture())
    store._ingest(_h3_facts.window(wid_b, ordinal=1))
    store._ingest(_placement(wid_b, SPAN_CELLS))
    store._ingest(_evidence(wid_b, SPAN_CELLS))
    _arm(store)
    assert local_ctx.armed_streams(store, PAGE, 0, 0, PPC) == (STREAM_ID,)
    # lane A leaves the cover: its window's evidence is refused
    store._ingest(dataclasses.replace(_evidence(WID, SPAN_CELLS),
                                      accepted=False))
    assert store.cover_lanes(PAGE, 0, 0, PPC) == ((OTHER_CAPTURE_ID, 0),)
    # and lane B's only verdict is below the attempt floor
    store._ingest(_lane_fact(OTHER_CAPTURE_ID, tiles.STAGE_SCAN,
                             tiles.OUTCOME_BELOW_FLOOR))
    # THE HOLE, shown through the current-cover enumeration the
    # 2026-09-21 repair asked: lane A's failure still stands in the
    # store, but lane A is no longer enumerated, and no lane that IS
    # carries a failed verdict (lane B never had one, so its standing
    # verdict is its whole history).
    enumerated = local_ctx.arming_lanes(store, PAGE, 0, 0, PPC,
                                        local_ctx.ARMING_STAGES)
    assert store.attempt_verdict(PAGE, 0, 0, STREAM_ID, tiles.STAGE_SCAN,
                                 (CAPTURE_ID, 0))[0] == (
                                     tiles.OUTCOME_FAILED)
    assert (tiles.STAGE_SCAN, (CAPTURE_ID, 0)) not in enumerated
    assert not any(
        (store.attempt_verdict(PAGE, 0, 0, STREAM_ID, stage, lane)
         or ("", 0))[0] == tiles.OUTCOME_FAILED
        for stage, lane in enumerated), (
        "the fixture must reproduce the hole: no CURRENT cover lane "
        "carries a failure")
    assert local_ctx.armed_streams(store, PAGE, 0, 0, PPC) == (STREAM_ID,), (
        "a lane leaving the cover is not a certificate")
    assert local_ctx._local_eligible(store, _subject()) is True
    assert local_ctx._local_retire(store, _subject()) is None
    _certify(store, 0, 0)
    assert local_ctx.armed_streams(store, PAGE, 0, 0, PPC) == ()
    assert local_ctx._local_eligible(store, _subject()) is False
    assert local_ctx._local_retire(store, _subject()) == "certified"


def test_a_failure_arms_its_own_footing_and_no_other():
    store = _seeded()
    other_ppc = Fraction(2)
    store._ingest(_second_capture(ppc=other_ppc))
    store._ingest(_lane_fact(OTHER_CAPTURE_ID, tiles.STAGE_SCAN,
                             tiles.OUTCOME_FAILED))
    assert local_ctx.armed_streams(store, PAGE, 0, 0, other_ppc) == (
        STREAM_ID,)
    assert local_ctx.armed_streams(store, PAGE, 0, 0, PPC) == (), (
        "a failure at another ppc is that footing's residue, not this one's")
    assert store.attempt_ever_failed_at_footing(
        PAGE, 0, 0, STREAM_ID, tiles.STAGE_SCAN, other_ppc) is True
    assert store.attempt_ever_failed_at_footing(
        PAGE, 0, 0, STREAM_ID, tiles.STAGE_SCAN, PPC) is False


def test_a_summed_failure_is_keyed_by_the_footing_its_lanes_share():
    store = _seeded()
    store._ingest(_second_capture())
    store._ingest(_lane_fact(
        CAPTURE_ID, tiles.STAGE_UNION, tiles.OUTCOME_FAILED,
        components=((CAPTURE_ID, 0), (OTHER_CAPTURE_ID, 0))))
    assert store.attempt_ever_failed_at_footing(
        PAGE, 0, 0, STREAM_ID, tiles.STAGE_UNION, PPC) is True
    assert local_ctx.armed_streams(store, PAGE, 0, 0, PPC) == (STREAM_ID,)


def test_the_three_planes_of_one_tile_name_ONE_subject():
    """The saving this subject exists for, stated as a law.

    C, M and Y of one tile used to name three subjects, and each of the
    three bookmarks paid for the IDENTICAL colour head fit over the
    identical covering windows: 78 % of all job CPU on the traced
    sheet-H run, for 690 certificates.  One subject; the streams are
    the job's business (`_attempt`, pinned below).
    """
    instance = _color_engine()
    streams = tuple(fact.stream_id for fact in instance.row.streams)
    assert len(streams) > 1, "the colour sim format must be multi-stream"
    subjects = {local_ctx._local_subjects(
        instance, _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED,
                                stream_id=stream_id))
        for stream_id in streams}
    assert subjects == {(_subject(),)}


@pytest.mark.parametrize("stage,outcome,arms", ARMING_MATRIX)
def test_the_row_arms_only_on_a_failed_ordinary_attempt(stage, outcome, arms):
    store = _seeded()
    subjects = local_ctx._local_subjects(store, _attempt_fact(stage, outcome))
    assert bool(subjects) is arms
    if arms:
        assert subjects == (_subject(),)


def _color_engine() -> engine._Engine:
    request = dataclasses.replace(_h3_facts.new_engine()._request,
                                  format_ref=COLOR_FORMAT_REF)
    instance = engine._Engine(request, [])
    instance._ingest(_h3_facts.capture())
    return instance


def test_the_row_arms_on_a_colour_format_too():
    instance = _color_engine()
    fact = _attempt_fact(tiles.STAGE_SCAN, tiles.OUTCOME_FAILED)
    subjects = local_ctx._local_subjects(instance, fact)
    assert subjects == ((PAGE, 0, 0, PPC),), (
        "the colour arm is the crop-parity lever: the row must arm on "
        "every family, not only K")


def test_a_colour_tile_with_no_colour_evidence_still_prepares_nothing():
    instance = _color_engine()
    assert local_ctx._local_eligible(instance, _subject()) is False
    assert local_ctx.prepare_local(instance, _subject(),
                                   local_ctx.STAGE_LOCAL) is None


def test_one_certified_colour_stream_is_enough_to_be_a_neighbour():
    instance = _color_engine()
    streams = tuple(fact.stream_id for fact in instance.row.streams)
    assert len(streams) > 1, "the colour sim format must be multi-stream"
    reach = ((0, 0), (0, 1))
    assert local_ctx.certified_neighbours(instance, PAGE, reach,
                                          TARGET) == ()
    instance._ingest(data.Certificate(
        page=PAGE, ty=0, tx=1, stream_id=streams[0],
        user_bits=np.zeros(instance.row.streams[0].user_bits, np.uint8),
        source="tiles/scan"))
    assert local_ctx.certified_neighbours(instance, PAGE, reach,
                                          TARGET) == ((0, 1),), (
        "a colour tile with one of three planes certified still projects "
        "that plane as known cells: it is a label source")


# --- label provenance: certificates and format truth, nothing else ------


def test_labels_come_only_from_format_truth_and_certified_neighbours():
    cells = _cells(SPAN_CELLS)
    evidence = _evidence(WID, SPAN_CELLS)
    reference = np.asarray(evidence.reference_values, np.int8)
    field = _donor_field(0, 1)
    values = local_ctx.label_values(PAGE, evidence, {(PAGE, 0, 1): field})

    known = reference >= 0
    assert np.array_equal(values[known], reference[known]), (
        "the format's own word and filler bits must survive unchanged")

    ty, tx = geometry.tile_of_cell(cells[:, 0], cells[:, 1])
    donor = (~known) & (ty == 0) & (tx == 1)
    assert donor.any()
    expected = field[cells[donor, 0] % geometry.TILE_CELLS,
                     cells[donor, 1] % geometry.TILE_CELLS]
    assert np.array_equal(values[donor], expected.astype(np.int8)), (
        "cargo labels must be the certificate's own re-encoded cells")

    unproven = (~known) & ~donor
    assert unproven.any()
    assert np.all(values[unproven] == -1), (
        "a cargo cell with no certificate behind it is not a label: the "
        "project has been burned by circular context labels")


def test_no_certified_neighbour_means_no_label_beyond_the_format():
    evidence = _evidence(WID, SPAN_CELLS)
    reference = np.asarray(evidence.reference_values, np.int8)
    values = local_ctx.label_values(PAGE, evidence, {})
    assert np.array_equal(values, reference)


def test_a_certificate_outside_the_window_labels_nothing():
    evidence = _evidence(WID, SPAN_CELLS)
    far = local_ctx.label_values(PAGE, evidence, {(PAGE, 5, 5): _donor_field(5, 5)})
    assert np.array_equal(far, local_ctx.label_values(PAGE, evidence, {}))


# --- transience: the standing fit is never touched ----------------------


def test_the_local_read_is_a_copy_and_leaves_its_input_alone():
    evidence = _evidence(WID, SPAN_CELLS)
    before = np.array(evidence.printed_llr, copy=True)
    fit = local_ctx.LocalFit(np.full(N_CONTEXT_BINS, 0.5), True, "probe",
                             1000, 0.1)
    read = local_ctx.local_context_row(evidence, fit)
    assert read is not evidence
    assert np.array_equal(evidence.printed_llr, before)
    assert evidence.ctx_adopted is False
    assert read.ctx_adopted is True
    assert not np.array_equal(read.printed_llr, before)


def test_the_row_can_produce_nothing_but_an_attempt_and_a_certificate():
    _h3_support.assert_measured(
        "tiles.local produces",
        tuple(kind.__name__
              for kind in local_ctx.LOCAL_DESCRIPTOR.produces),
        ("AttemptFact", "Certificate"))
    assert data.WindowEvidence not in local_ctx.LOCAL_DESCRIPTOR.produces
    assert calibrate.CtxOutcome not in local_ctx.LOCAL_DESCRIPTOR.produces


def test_a_local_job_writes_no_evidence_and_no_region_context():
    store = _seeded()
    _certify(store, 0, 1)
    _certify(store, 1, 0)
    _arm(store)
    job = local_ctx.prepare_local(store, _subject(), local_ctx.STAGE_LOCAL)
    assert job is not None
    before, _hold_before = _h3_facts.store_snapshot(store)
    result = job()
    for fact in result.facts:
        store._ingest(fact)
    after, _hold_after = _h3_facts.store_snapshot(store)
    written = set(_h3_facts.cells_written(before, after))
    assert "_evidence" not in written, (
        "a local fit that folds evidence is not transient")
    assert "_region_ctx" not in written, (
        "the standing region context cell is not this row's to move")
    assert written <= {"_attempt_outcomes", "_attempt_latest",
                       "_attempt_ever_failed_footing", "_certificates",
                       "_equations"}


# --- the fit itself -----------------------------------------------------


def test_a_fit_with_no_labels_refuses_before_the_gate():
    evidence = _evidence(WID, SPAN_CELLS)
    empty = np.full(evidence.page_cells_yx.shape[0], -1, np.int8)
    fit = local_ctx.fit_local_context((evidence,), (empty,))
    assert fit.adopted is False
    assert fit.reason == local_ctx.REASON_NO_LABELS
    assert fit.n_search_sites == 0
    assert fit.offsets.shape == (N_CONTEXT_BINS,)


def test_the_fit_runs_the_standing_context_gate_and_reports_it():
    evidence = _evidence(WID, SPAN_CELLS)
    values = local_ctx.label_values(PAGE, evidence,
                                    {(PAGE, 0, 1): _donor_field(0, 1)})
    fit = local_ctx.fit_local_context((evidence,), (values,))
    assert fit.offsets.shape == (N_CONTEXT_BINS,)
    assert fit.n_search_sites > 0
    assert fit.reason in ("adopted", "validation_gate_failed",
                          "insufficient_search_support",
                          "search_class_starved",
                          "insufficient_validation_support",
                          "validation_class_starved")


# --- pricing ------------------------------------------------------------


def test_the_row_prices_itself_behind_every_refinement_row():
    store = _seeded()
    cost = local_ctx.LOCAL_DESCRIPTOR.cost(store, _subject(),
                                           local_ctx.STAGE_LOCAL, 0, 0)
    assert cost == local_ctx.LOCAL_COST == 220
    assert cost > refine.REFINE_COST
    assert cost > tiles_sched.PAYLOAD_COST


def test_the_row_pays_its_base_once_and_its_base_again_per_earlier_fire():
    # 2026-10-18: the row was FLAT until the owner's price balance, and
    # its re-fires popped ahead of planek's and swim's first fires
    # (measure/sched_trace/YIELD-OVER-CPU-2026-10-18.md).  Now base +
    # base x earlier fires, the one convention of every residue row.
    store = _seeded()
    subject = _subject()
    first = local_ctx.LOCAL_DESCRIPTOR.cost(store, subject,
                                            local_ctx.STAGE_LOCAL, 0, 0)
    second = local_ctx.LOCAL_DESCRIPTOR.cost(store, subject,
                                             local_ctx.STAGE_LOCAL, 1, first)
    tenth = local_ctx.LOCAL_DESCRIPTOR.cost(store, subject,
                                            local_ctx.STAGE_LOCAL, 10, first)
    assert second == first + local_ctx.LOCAL_COST
    assert tenth == first + 10 * local_ctx.LOCAL_COST
    # every residue row's FIRST fire precedes any row's SECOND
    from holo.receiver.plugins import plane_k, swim
    assert first < plane_k.PLANEK_COST < swim.SWIM_COST < second


def test_the_heavy_budget_is_the_retry_budget():
    assert tiles.max_iters_for(tiles.STAGE_LOCAL150) == tiles.RETRY_BP_MAX_ITERS
    assert tiles.max_iters_for(tiles.STAGE_LOCAL150) == 150


# --- the union first, then each lane alone ------------------------------
#
# The measured shape (`measure/local_ab`, sheet I): per-origin attempts
# are a strict superset of the union — the union never won a tile the
# lanes lost, and the lanes won four the union lost.  These pin the
# SCHEDULE of that hybrid: which component sets are attempted, in what
# order, and when it stops.  The codec is scripted out, because what is
# under test here is the sequence, not the decode.

LANES = ("aaaa1111", "bbbb2222", "cccc3333")


def _cut(capture_id: str, level_index: int = 0) -> tiles.TileCut:
    return tiles.TileCut(capture_id, level_index, PAGE, 0, 0,
                         np.zeros((1, 1), np.float32),
                         np.zeros(1, np.uint16))


class _ScriptedAttempts:
    """`tiles.attempt_tile` replaced by a script of outcomes."""

    def __init__(self, certifies: tuple | None = None) -> None:
        self.calls: list[tuple] = []
        self._certifies = certifies

    def __call__(self, row, site_geometry, components, stream_id,
                 stage, generation=0):
        signature = tiles.component_signature(components)
        self.calls.append((signature, stage))
        certified = signature == self._certifies
        return tiles._result(
            PAGE, 0, 0, stream_id, stage,
            tiles.OUTCOME_CERTIFIED if certified else tiles.OUTCOME_FAILED,
            1000, 7, certified, certified,
            np.zeros(ROW.streams[0].user_bits, np.uint8) if certified else None,
            signature)


def _run_attempt(monkeypatch, components, certifies=None):
    scripted = _ScriptedAttempts(certifies)
    monkeypatch.setattr(tiles, "attempt_tile", scripted)
    result = local_ctx._attempt(ROW, GEOMETRY, components, PAGE, 0, 0,
                                (STREAM_ID,), 0.0)
    return scripted, result


def test_the_lane_order_is_the_one_the_row_already_has():
    cuts = [_cut(LANES[2]), _cut(LANES[0]), _cut(LANES[1])]
    ordered = local_ctx.lane_order(cuts)
    assert [cut.capture_id for cut in ordered] == sorted(LANES), (
        "the lane pass must walk the lanes in the order the store "
        "enumerates them and _combine sums them")
    assert (tiles.component_signature(ordered)
            == tuple((cut.capture_id, cut.level_index) for cut in ordered)), (
        "the lane order must be component_signature's own key, so the row "
        "carries one lane order and not two")


def test_a_single_lane_subject_makes_exactly_the_attempt_it_made_before(
        monkeypatch):
    only = [_cut(LANES[0])]
    assert local_ctx.attempt_sets(only) == (tuple(only),)
    scripted, result = _run_attempt(monkeypatch, only)
    assert [signature for signature, _stage in scripted.calls] == [
        ((LANES[0], 0),)], (
        "the union IS the lane on a single-lane tile: a per-lane pass "
        "there would re-decode identical evidence under an identical "
        "attempt key")
    assert len(result.events) == 1


def test_one_build_is_read_by_every_armed_stream_in_turn(monkeypatch):
    """The stream loop is OUTSIDE the attempt-set loop.

    `build` — the local head or context fit, and the expensive half —
    has already run once when `_attempt` is called, so every armed
    stream reads the same components.  That is what the tile-lane
    subject buys, and it is what a per-stream subject could not.
    """
    cuts = [_cut(lane) for lane in LANES]
    scripted = _ScriptedAttempts(None)
    monkeypatch.setattr(tiles, "attempt_tile", scripted)
    result = local_ctx._attempt(ROW, GEOMETRY, cuts, PAGE, 0, 0,
                                ("C", "M", "Y"), 0.0)
    sets = local_ctx.attempt_sets(cuts)
    assert len(scripted.calls) == 3 * len(sets)
    assert len(result.events) == len(scripted.calls)


def test_a_certificate_stops_ONE_stream_and_not_its_siblings(monkeypatch):
    cuts = [_cut(lane) for lane in LANES]
    scripted = _ScriptedAttempts(tuple((lane, 0) for lane in sorted(LANES)))
    monkeypatch.setattr(tiles, "attempt_tile", scripted)
    result = local_ctx._attempt(ROW, GEOMETRY, cuts, PAGE, 0, 0,
                                ("C", "M", "Y"), 0.0)
    assert len(scripted.calls) == 3, (
        "each stream stops at its own first certificate; a tile-stream "
        "has one answer and the codec gate is what says so")
    assert sum(isinstance(fact, data.Certificate)
               for fact in result.facts) == 3


def test_no_lane_no_attempt(monkeypatch):
    assert local_ctx.attempt_sets([]) == ()
    scripted, result = _run_attempt(monkeypatch, [])
    assert scripted.calls == []
    assert result.facts == () and result.events == ()


def test_a_failed_union_is_followed_by_every_lane_in_order(monkeypatch):
    cuts = [_cut(LANES[2]), _cut(LANES[0]), _cut(LANES[1])]
    scripted, result = _run_attempt(monkeypatch, cuts)
    signatures = [signature for signature, _stage in scripted.calls]
    assert signatures == [
        tuple((lane, 0) for lane in sorted(LANES)),
        ((LANES[0], 0),), ((LANES[1], 0),), ((LANES[2], 0),)], (
        "the union goes first — it clears an observation floor the "
        "single lanes miss — and then every covering lane alone")
    assert {stage for _signature, stage in scripted.calls} == {
        tiles.STAGE_LOCAL150}, "every attempt is the same codec gate"
    assert len(result.events) == 4
    assert not any(isinstance(fact, data.Certificate) for fact in result.facts)


def test_a_certifying_union_never_reaches_the_lanes(monkeypatch):
    cuts = [_cut(lane) for lane in LANES]
    union = tuple((lane, 0) for lane in sorted(LANES))
    scripted, result = _run_attempt(monkeypatch, cuts, certifies=union)
    assert [signature for signature, _stage in scripted.calls] == [union]
    assert sum(isinstance(fact, data.Certificate) for fact in result.facts) == 1


def test_the_lane_pass_stops_at_the_first_certificate(monkeypatch):
    cuts = [_cut(lane) for lane in LANES]
    scripted, result = _run_attempt(monkeypatch, cuts,
                                    certifies=((LANES[1], 0),))
    assert [signature for signature, _stage in scripted.calls] == [
        tuple((lane, 0) for lane in sorted(LANES)),
        ((LANES[0], 0),), ((LANES[1], 0),)], (
        "a tile has one answer and the codec gate is what says so: the "
        "third lane is never attempted")
    assert sum(isinstance(fact, data.Certificate) for fact in result.facts) == 1
    assert len(result.events) == 3


def test_every_attempt_the_row_makes_is_reported(monkeypatch):
    cuts = [_cut(lane) for lane in LANES]
    scripted, result = _run_attempt(monkeypatch, cuts)
    facts = [fact for fact in result.facts
             if isinstance(fact, data.AttemptFact)]
    assert len(facts) == len(scripted.calls) == len(result.events), (
        "per-tool accounting: an attempt this row makes is an AttemptFact "
        "and a TileOutcome like any other row's")
    assert [fact.components for fact in facts] == [
        signature for signature, _stage in scripted.calls]


def test_a_lane_attempt_arms_no_row_the_union_did_not_already_arm():
    lane_fact = _attempt_fact(tiles.STAGE_LOCAL150, tiles.OUTCOME_FAILED)
    assert local_ctx._local_subjects(_seeded(), lane_fact) == (), (
        "local150 is not an arming stage: the row's own attempts never "
        "arm it again, however many it makes")
    assert not tiles.arms_retry(lane_fact, False), (
        "local150 is not an ordinary stage: tiles.retry does not mirror it")


# --- the existence proof: a capture with one window's own channel ------
#
# The K sim renders one channel for the whole page.  The local-patch
# capture gives the raster of window (0, 0) a directional smear and its
# own noise and leaves the other eight windows alone, so a context
# detector fitted over the region is fitted on a channel that holds for
# eight ninths of it.  These numbers are the row's reason to exist:
# without it the same capture, the same tree and the same codec gate
# stop ONE certificate short of the volume — and one is enough,
# because metadata.MIN_METADATA_EQUATIONS is 48 on a 49-tile page, so
# the last certificate is the volume.
#
# RE-MEASURED 2026-09-03 for the b8471fc re-key, after LOCAL_PATCH_NOISE_SD
# moved 49 -> 35 (noise only; the smear is the process-direction ISI the
# row exists to re-fit and stays at 5 px).  The proof needs the volume to
# close WITH the row and not without — on >= 48 of 49 and off <= 47, the
# row's gain the decisive tile — and the re-key put the standing point
# outside that window (on 45 / off 44; it had been 48 / 45).
#
# The ladder, both arms, same argv as the fixtures (on = the standing
# tree, off = tiles.local dropped), at smear 5.0:
#
#   sd 30 32 33    on 48 V    off 48 V    gain 0
#   sd 34          on 46      off 46      gain 0
#   sd 35          on 48 V    off 47      gain 1   <== taken
#   sd 36          on 47      off 47      gain 0
#   sd 37 38       on 46 45   off 46 45   gain 0
#   sd 40 43 46    on 46 46 45  off same  gain 0
#   sd 49 (old)    on 45      off 44      gain 1
#   sd 52 55       on 42      off 42      gain 0
#
# and at smears 4.0 to 6.0 every rung closes both arms or neither, except
# 4.75/47 (on 48 / off 47), which moves the smear too.  The count is NOT
# monotone in the noise — 33 gives 48, 34 gives 46, 35 gives 48, 36
# gives 47 — because each rung is a fresh draw of which patch tiles fall
# which side of the LDPC threshold.  So 35 is a SEARCHED point, as 49.0
# was, and the search will be needed again at the next fork.  The knife
# edge is inherent: on = 48 IS the quorum, and it was 48 before.
#
# What moved: the row's gain, three certificates -> one, at a different
# address — (0, 2, 1), inside the patch window (tiles 0-2 whole plus
# 8/64 of tile 3 per axis).  The control lost less (45 -> 47); the
# standing tree still lands on the quorum (48).  Still additive (off - on
# empty), still zero wrong, still closes only with the row.
#
# THIS IS THE ONLY PATCH PROOF IN THE MODULE since 2026-09-20.  A COLOUR
# twin stood below it — one window of the colour sim given its own plane
# geometry, four decodes of the widened matrix — and its own ledger had
# said since 2026-09-07 that the residue tier gains NOTHING there: the
# ordinary colour lane, reading through the page field, recovers by
# itself the nine tiles that used to need a rescue row.  It was retired
# with the two whole-page colour existence proofs by the owner's ruling;
# its episodes, goldens and the overlap case it kept measured are in
# docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md §4.  What the three K
# decodes below cost is seconds, and they are the regression the ruling
# names.


# MEASURED 2026-09-20 (the decode-cache landing): the gain is WORKER-1-ONLY.
# The same argv at eight workers certifies 48 on BOTH arms -- the control
# without `tiles.local` recovers (0, 2, 1) by itself and VERIFIES -- so the
# knife edge the ledger above names is also a schedule edge: the parallel
# schedule's extra work reaches the tile the row exists to rescue.  The
# on/off proof therefore stays at workers 1 (cached, 36 s once per
# production change); the engine-keeping consumers read the eight-worker
# decode instead, where the store is the same law at 4 s.
LOCAL_PATCH_CERTIFIED = 48
LOCAL_PATCH_CONTROL_CERTIFIED = 47
LOCAL_PATCH_GAINED = ((0, 2, 1, "main"),)
LOCAL_PATCH_FIRES = 7


def _jobs(record: object) -> dict:
    counts: dict = {}
    for event in record.events:
        if isinstance(event, data.JobDone):
            counts[event.plugin] = counts.get(event.plugin, 0) + 1
    return counts


def test_the_row_fires_on_the_capture_it_exists_for(decode_k_local_patch_w1):
    _h3_support.assert_measured("tiles.local fires on the local patch",
                                _jobs(decode_k_local_patch_w1).get(
                                    "tiles.local", 0),
                                LOCAL_PATCH_FIRES)


def _local_attempts(record: object) -> dict:
    """Every `local150` attempt the decode recorded, by component set.

    `store._fold_attempt` keys an attempt on
    `(page, ty, tx, stream, stage, max_iters, components)`, so the
    decode's own attempt ledger already says how many lanes each of this
    row's attempts was made over — no instrumentation needed.
    """
    return {key: outcome
            for key, outcome in record.attempt_outcomes.items()
            if key[4] == tiles.STAGE_LOCAL150}


def _assert_single_lane_no_op(label: str, record: object,
                              fires: int) -> None:
    """The null proof, end to end: one capture is one lane.

    `store.cover_lanes` fixes the rung, and a capture has at most one
    level per rung, so a single-capture decode gives every subject
    exactly one covering lane.  `attempt_sets` returns one set there and
    the row makes exactly the attempt it made before the hybrid — which
    is why this decode's certificate goldens did not move.
    """
    attempts = _local_attempts(record)
    checks = _h3_support.Checks(f"{label} single-lane no-op")
    checks.check("the row actually attempted something", bool(attempts))
    checks.equal("every local attempt is over one lane",
                 sorted({len(key[6]) for key in attempts}), [1])
    checks.check(
        f"no more attempts than fires ({len(attempts)} vs {fires})",
        len(attempts) <= fires,
        "a single-lane subject must not produce a second attempt")
    checks.assert_clean()


def test_a_single_capture_k_decode_never_reaches_the_lane_pass(
        decode_k_local_patch_w1):
    _assert_single_lane_no_op("k", decode_k_local_patch_w1,
                              LOCAL_PATCH_FIRES)


def test_the_row_is_a_strict_superset_of_the_same_tree_without_it(
        decode_k_local_patch_w1, decode_k_local_patch_off_w1):
    on = set(decode_k_local_patch_w1.certificates)
    off = set(decode_k_local_patch_off_w1.certificates)
    assert not (off - on), (
        f"the row lost {sorted(off - on)}: an additive tool never "
        f"displaces the attempt the ordinary rows would have made")
    _h3_support.assert_measured("local-patch certificates gained",
                                tuple(sorted(on - off)), LOCAL_PATCH_GAINED)
    _h3_support.assert_measured("local-patch certificates with the row",
                                len(on), LOCAL_PATCH_CERTIFIED)
    _h3_support.assert_measured("local-patch certificates without the row",
                                len(off), LOCAL_PATCH_CONTROL_CERTIFIED)


def test_the_control_really_ran_without_the_row(
        decode_k_local_patch_off_w1):
    assert "tiles.local" not in _jobs(decode_k_local_patch_off_w1), (
        "the control must be the same tree with the row removed, not a "
        "run where the row simply found nothing")


def test_the_rows_certificates_are_the_volume(
        decode_k_local_patch_w1, decode_k_local_patch_off_w1, sim_k):
    assert decode_k_local_patch_off_w1.status == "not-verified", (
        "the control must lose this volume, or the row is rescuing "
        "nothing that was at risk")
    assert decode_k_local_patch_off_w1.payload is None
    assert decode_k_local_patch_w1.status == "verified"
    assert decode_k_local_patch_w1.payload == sim_k.payload_data
    assert decode_k_local_patch_w1.payload_sha256 == sim_k.payload_sha256
    for key in LOCAL_PATCH_GAINED:
        assert (str(decode_k_local_patch_w1.certificates[key].source)
                == tiles.source_tag(tiles.STAGE_LOCAL150)), key


def _assert_zero_wrong(label: str, record: object, reference: object) -> None:
    checks = _h3_support.Checks(label)
    truth = reference.certificates
    for key, certificate in sorted(record.certificates.items()):
        clean = truth.get(key)
        checks.check(f"{key} is an address the clean run also certified",
                     clean is not None)
        if clean is None:
            continue
        checks.check(f"{key} carries the clean run's user bits",
                     np.array_equal(np.asarray(certificate.user_bits),
                                    np.asarray(clean.user_bits)),
                     "a wrong certificate is the one failure no additive "
                     "tool may ever produce")
    checks.assert_clean()


def test_every_certificate_the_row_mints_carries_the_clean_runs_bits(
        decode_k_local_patch_w1, decode_k_complete):
    _assert_zero_wrong("local-patch zero-wrong", decode_k_local_patch_w1,
                       decode_k_complete)


def test_the_row_is_deterministic_and_safe_at_eight_workers(
        decode_k_local_patch_w1, decode_k_local_patch_w8, decode_k_complete):
    assert decode_k_local_patch_w1.payload == decode_k_local_patch_w8.payload
    assert decode_k_local_patch_w8.payload is not None, (
        "the volume the row rescues at workers 1 must come back at "
        "workers 8 too: w8 gates payload bytes")
    _assert_zero_wrong("local-patch w8 zero-wrong", decode_k_local_patch_w8,
                       decode_k_complete)


def test_replaying_a_local_job_on_the_finished_store_writes_no_evidence(
        decode_k_local_patch_w8):
    store = decode_k_local_patch_w8.engine
    assert store is not None
    jobs = []
    for plugin, subject in sorted(store._bookmarks, key=repr):
        if plugin != "tiles.local":
            continue
        job = local_ctx.prepare_local(store, subject, local_ctx.STAGE_LOCAL)
        if job is not None:
            jobs.append(job)
    assert jobs, (
        "no local job could be prepared on the finished store: this "
        "transience proof would then be vacuous")
    before, _hold_before = _h3_facts.store_snapshot(store)
    for job in jobs:
        for fact in job().facts:
            store._ingest(fact)
    after, _hold_after = _h3_facts.store_snapshot(store)
    written = set(_h3_facts.cells_written(before, after))
    assert "_evidence" not in written
    assert "_region_ctx" not in written
    assert written <= {"_attempt_outcomes", "_attempt_latest",
                       "_attempt_ever_failed_footing", "_certificates",
                       "_equations"}
