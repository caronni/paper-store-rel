from __future__ import annotations

import dataclasses
from fractions import Fraction

import numpy as np
import pytest

from holo3 import data, engine
from holo3.format import identity
from holo3.lib import geometry
from holo3.lib.pava import N_CONTEXT_BINS, calibration_llr
from holo3.plugins import calibrate, color_region, local_ctx, refine, tiles
from holo3.tests import _h3_facts, _h3_sims, _h3_support
from holo3.tests import conftest as h3_conftest

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
GEOMETRY = identity.build_site_geometry(ROW)
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


def _subject(ty: int = 0, tx: int = 0) -> tuple:
    return (PAGE, ty, tx, STREAM_ID, PPC)


def _attempt_fact(stage: str, outcome: str) -> data.AttemptFact:
    return data.AttemptFact(
        page=PAGE, ty=0, tx=0, stream_id=STREAM_ID, stage=stage,
        outcome=outcome, n_informative=1000, n_iters=60, syndrome_ok=False,
        crc_ok=False, components=((CAPTURE_ID, 0),))


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
    _h3_support.assert_golden(
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
    assert local_ctx._local_eligible(store, _subject()) is False
    assert local_ctx.prepare_local(store, _subject(),
                                   local_ctx.STAGE_LOCAL) is None


def test_one_certified_neighbour_is_the_whole_admission_rule():
    store = _seeded()
    _certify(store, 0, 1)
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
    _certify(store, 0, 0)
    assert local_ctx._local_eligible(store, _subject()) is False
    assert local_ctx._local_retire(store, _subject()) is True
    assert local_ctx.prepare_local(store, _subject(),
                                   local_ctx.STAGE_LOCAL) is None


def test_an_uncertified_tile_is_never_retired():
    store = _seeded()
    _certify(store, 0, 1)
    assert local_ctx._local_retire(store, _subject()) is False


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
    assert subjects == ((PAGE, 0, 0, STREAM_ID, PPC),), (
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
    _h3_support.assert_golden(
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
    assert written <= {"_attempt_outcomes", "_certificates", "_equations"}


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
                                           local_ctx.STAGE_LOCAL, 1, 0)
    assert cost == local_ctx.LOCAL_COST == 220
    assert cost > refine.REFINE_COST
    assert cost > tiles.PAYLOAD_COST


def test_the_row_pays_the_ordinary_rung_premium_and_no_escalation():
    store = _seeded()
    subject = _subject()
    first = local_ctx.LOCAL_DESCRIPTOR.cost(store, subject,
                                            local_ctx.STAGE_LOCAL, 1, 0)
    tenth = local_ctx.LOCAL_DESCRIPTOR.cost(store, subject,
                                            local_ctx.STAGE_LOCAL, 10, first)
    assert first == tenth, (
        "this row does not re-price by fire ordinal; the schedule table "
        "must not mark it as one that does")


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

    def __call__(self, row, site_geometry, components, stream_id, stage):
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
                                STREAM_ID, 0.0)
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


def test_the_local_patch_capture_is_a_derived_stimulus_not_an_artefact(
        sim_k_local_patch, sim_k):
    assert sim_k_local_patch.tiff_sha256 != sim_k.tiff_sha256
    assert sim_k_local_patch.format_ref == sim_k.format_ref
    assert sim_k_local_patch.payload_sha256 == sim_k.payload_sha256
    assert sim_k_local_patch.tiff.is_file()


def test_the_row_fires_on_the_capture_it_exists_for(decode_k_local_patch_w1):
    _h3_support.assert_golden("tiles.local fires on the local patch",
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
    _h3_support.assert_golden("local-patch certificates gained",
                              tuple(sorted(on - off)), LOCAL_PATCH_GAINED)
    _h3_support.assert_golden("local-patch certificates with the row",
                              len(on), LOCAL_PATCH_CERTIFIED)
    _h3_support.assert_golden("local-patch certificates without the row",
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


# --- the colour existence proof: one window's own plane geometry ------
#
# Colour has no separate context row: `color_region` fits the WHOLE head
# per lane and page — QDA class model, CMY8 detector calibration, the
# registration residuals, the feature divisor and the context matrix —
# and applies it to every window.  The colour patch capture gives window
# (0, 0) its own plane geometry: the R channel (the one cyan absorbs) is
# sampled 5 px = 0.83 cell off in x, with the window's own noise.  The
# region fits ONE residual per plane as a function of page-y, so a jump
# confined to one window is averaged away there; a fit over that window
# alone represents it exactly.  The gain is therefore expected to land
# on the C stream of the patch tiles, and it does.
#
# THE CLAIM WAS RE-SCOPED 2026-08-31, AND THE ROW IS NOT AT FAULT.
# What this proof asserted until then was EXCLUSIVE — "without this row
# the same tree stops three certificates short".  That is now false, and
# the honest repair is to stop asserting it rather than to keep failing
# on it.  Measured through `measure/h3_plane_fields.py --sim
# color-patch --drop`, current main, workers 1, `--complete`:
#
#   every row live                     294 certs; tiles.local 15 fires,
#                                      6 certificates
#   `tiles.planek` dropped             294, BIT-IDENTICAL — planek does
#                                      not fire while local is present
#   `tiles.local` dropped alone        294, and `tiles.planek` fires 6
#                                      times and mints THE SAME 6
#   the WHOLE residue tier dropped     288 — C 92, the six are gone, no
#   (the control this module now uses) tier row fires, and NO OTHER row
#                                      has learned the rescue
#
# So `tiles.local` still earns its six certificates; what broke is the
# CONTROL.  `tiles.planek` (merged after these goldens were taken)
# substitutes for the row exactly, so `gained = on - off` went empty
# against a control that dropped `tiles.local` alone.
#
# THE EPISODES, dated:
#
#   written 2026-08-30   EXCLUSIVE claim: without `tiles.local` the same
#                        tree stops three certificates short.  True when
#                        written — it was the only row that could do
#                        this.
#   measured 2026-08-31  OVERLAP: `tiles.planek` merges, and on this
#                        capture it does the same job.  The exclusive
#                        claim is now FALSE, not merely unproven.
#   re-scoped 2026-08-31 TIER claim: the residue tier collectively earns
#                        these six certificates.  The control drops the
#                        whole tier (`conftest.COLOR_PATCH_RESIDUE_TIER`)
#                        and loses all six, so the claim is measured, not
#                        assumed.  What the row does INSIDE the tier is
#                        pinned separately and exactly: local mints the
#                        six, no other residue row fires while it is
#                        present, and planek covers for it precisely when
#                        it is dropped.
#
#   re-keyed 2026-09-03  THE FIRST TWO CLAUSES ABOVE NO LONGER HOLD:
#                        the b8471fc re-key made this page harder, and
#                        with every row present local mints six of the
#                        nine and planek three (C (0,2), (1,2), (2,2));
#                        planek fires 15 against local's 43, where it
#                        fired zero.  The TIER claim and the overlap
#                        case are untouched — the control still drops
#                        the whole tier and loses every gained address.
#                        Content, not mechanism.
#
# This weakens no truth.  The exclusivity that no longer exists stops
# being asserted; everything that IS true — the yield, the attribution,
# the overlap — is pinned harder than before.  If a re-hardened stimulus
# ever puts the rescue back out of planek's reach,
# `test_dropping_the_local_row_alone_only_hands_the_work_to_planek`
# fails and the exclusive claim can be restored deliberately.
#
# A stimulus outside planek's rescue family would be the other repair —
# planek does per-plane spectral isolation plus a blind +-2.0-dot
# x-shift search, so a REGISTRATION defect is exactly what it covers —
# but FIVE DIRECTIONS WERE MEASURED AND ALL FAILED (same instrument,
# all-rows-live, `tiles.local` certificates in brackets):
#
#   x-shift  8 px   285 certs, C 89   local fires 36 [0], planek 36 [0]
#   x-shift 11 px   273,       C 89   local 12 [0],      planek 12 [0]
#   y-shift  5 px   297               local 3 [0],       planek 3 [0]
#   y-shift  9 px   285,       C 89   local 36 [0],      planek 36 [0]
#   y-shift 13 px   288,       C 90   local 36 [0],      planek 36 [0]
#   smear  s=3 px   297               neither row arms at all
#   smear  s=5 px   297               neither row arms at all
#   smear  s=7 px   285,       C 89   local 45 [0],      planek 45 [0]
#
# Escalating the displacement does not move the rescue from planek to
# local: past about 6 dots the damaged tiles are lost to BOTH rows.
# Moving it to y leaves every row's family at once (planek searches x
# only, and the local head's registration fit does not recover y here
# either).  A directional smear — the shape the K proof above uses, and
# the one structurally outside both planek's translation family and
# uplift's photometric one — is either too weak to arm anything or
# strong enough to lose the tiles outright.  `tiles.local`'s COLOUR arm
# has a narrow rescue window on this stimulus family and the original
# 5 px x-shift is inside it; so, now, is planek.  A stimulus in local's
# window and out of planek's is still worth having — a colour analogue
# of the K patch's own local-context defect, at a magnitude between
# "arms nothing" and "loses the tile" — but it is a separate line, and
# the tier claim above does not wait on it.

# Re-measured 2026-08-31 against the TIER control.  The count of gained
# certificates is unchanged at six, but they are a DIFFERENT six: the
# old golden read three tile rows by two columns, and the receiver now
# earns two rows by three columns (four addresses overlap).  Both sets
# lie inside the patch window, which spans tiles 0-3 on each axis.
#
# RE-MEASURED AGAIN 2026-09-03 for the b8471fc re-key: 294 -> 280 with the
# tier, 288 -> 271 without; the nine are a strict superset of the old six
# (tile row 2 joins rows 0 and 1), all on the misregistered C plane inside
# the patch window; `off - on` empty.
COLOR_PATCH_CERTIFIED = 280
COLOR_PATCH_CONTROL_CERTIFIED = 271
COLOR_PATCH_GAINED = ((0, 0, 0, "C"), (0, 0, 1, "C"), (0, 0, 2, "C"),
                      (0, 1, 0, "C"), (0, 1, 1, "C"), (0, 1, 2, "C"),
                      (0, 2, 0, "C"), (0, 2, 1, "C"), (0, 2, 2, "C"))
COLOR_PATCH_FIRES = 43

# The cross-row ledger this episode teaches.  The module never noticed
# planek arriving because nothing here read any row but `tiles.local`.
# This pin is the loud version: while the row under test is present, NO
# other residue row fires on this capture, so a new row that starts
# firing moves a number instead of silently taking the proof's
# certificates the moment the control drops one row.  Measured
# 2026-08-31 on current main at workers 1.
#
# A fires count cannot see who MINTS; the split is pinned by source in
# COLOR_PATCH_GAINED_BY_SOURCE below.
COLOR_PATCH_RESIDUE_FIRES: dict[str, int] = {
    "tiles.local": 43, "tiles.planek": 15, "tiles.uplift": 0}
# who mints the tier's gain, by certificate source (2026-09-03)
COLOR_PATCH_GAINED_BY_SOURCE: dict[str, int] = {
    tiles.source_tag(tiles.STAGE_LOCAL150): 6,
    tiles.source_tag(tiles.STAGE_PLANEK150): 3}
COLOR_PATCH_TILES = tuple((ty, tx) for ty in range(4) for tx in range(4))


def test_the_colour_patch_capture_is_a_derived_stimulus_not_an_artefact(
        sim_color_local_patch, sim_color):
    assert sim_color_local_patch.tiff_sha256 != sim_color.tiff_sha256
    assert sim_color_local_patch.format_ref == sim_color.format_ref
    assert sim_color_local_patch.payload_sha256 == sim_color.payload_sha256
    assert sim_color_local_patch.tiff.is_file()


def test_the_colour_arm_fires_on_the_capture_it_exists_for(
        decode_color_local_patch_w1):
    _h3_support.assert_golden(
        "tiles.local fires on the colour patch",
        _jobs(decode_color_local_patch_w1).get("tiles.local", 0),
        COLOR_PATCH_FIRES)


def test_the_residue_tier_is_a_strict_superset_of_the_tree_without_it(
        decode_color_local_patch_w1,
        decode_color_local_patch_no_residue_w1):
    """The TIER's claim, since 2026-08-31 — see the episode above.

    The control drops every residue row, not `tiles.local` alone,
    because two rows can now do this job and dropping one leaves the
    other holding the page up.  What survives the re-scope is the
    honest half: these six certificates exist because the residue tier
    exists, and nothing outside it produces them.
    """
    on = set(decode_color_local_patch_w1.certificates)
    off = set(decode_color_local_patch_no_residue_w1.certificates)
    assert not (off - on), (
        f"the tier lost {sorted(off - on)}: an additive tool never "
        f"displaces the attempt the ordinary rows would have made")
    _h3_support.assert_golden("colour-patch certificates gained",
                              tuple(sorted(on - off)), COLOR_PATCH_GAINED)
    _h3_support.assert_golden("colour-patch certificates with the tier",
                              len(on), COLOR_PATCH_CERTIFIED)
    _h3_support.assert_golden("colour-patch certificates without the tier",
                              len(off), COLOR_PATCH_CONTROL_CERTIFIED)


def test_the_colour_gain_lands_on_the_plane_and_tiles_the_patch_damages(
        decode_color_local_patch_w1,
        decode_color_local_patch_no_residue_w1):
    gained = (set(decode_color_local_patch_w1.certificates)
              - set(decode_color_local_patch_no_residue_w1.certificates))
    checks = _h3_support.Checks("colour gain attribution")
    for page, ty, tx, stream_id in sorted(gained):
        checks.equal(f"({ty},{tx}) gain is on the misregistered plane",
                     stream_id, "C")
        checks.check(f"({ty},{tx}) is a patch tile",
                     (ty, tx) in COLOR_PATCH_TILES)
    checks.assert_clean()


def test_which_residue_rows_fire_beside_the_row_under_test_is_pinned(
        decode_color_local_patch_w1):
    """The residue-fire ledger beside the row is pinned; a row appearing
    here is the signal to re-check the tier control.

    A residue row that never fires here cannot be quietly holding the
    proof up; a row that starts firing is exactly what happened in
    2026-08-31's episode, and it went unnoticed because no test read
    any row but this one.
    """
    jobs = _jobs(decode_color_local_patch_w1)
    _h3_support.assert_golden(
        "colour-patch residue fires",
        {row: jobs.get(row, 0) for row in COLOR_PATCH_RESIDUE_FIRES},
        COLOR_PATCH_RESIDUE_FIRES)


def test_which_rows_mint_the_tier_s_gain_is_pinned(
        decode_color_local_patch_w1,
        decode_color_local_patch_no_residue_w1):
    gained = (set(decode_color_local_patch_w1.certificates)
              - set(decode_color_local_patch_no_residue_w1.certificates))
    by_source: dict[str, int] = {}
    for key in gained:
        source = str(decode_color_local_patch_w1.certificates[key].source)
        by_source[source] = by_source.get(source, 0) + 1
    _h3_support.assert_golden("colour-patch gain by minting source",
                              by_source, COLOR_PATCH_GAINED_BY_SOURCE)
    assert sum(by_source.values()) == len(COLOR_PATCH_GAINED)


def test_the_colour_control_really_ran_without_the_tier(
        decode_color_local_patch_no_residue_w1):
    """The control is the tree with the WHOLE tier removed.

    Checked row by row against the tier the conftest declares, so
    adding a row there without adding it to the control is not
    something this module can do quietly.
    """
    jobs = _jobs(decode_color_local_patch_no_residue_w1)
    still_firing = sorted(row for row in h3_conftest.COLOR_PATCH_RESIDUE_TIER
                          if row in jobs)
    assert not still_firing, (
        f"{still_firing} fired in the control: it must be the same tree "
        f"with the residue tier removed, not a run where the rows "
        f"happened to find nothing")


def test_dropping_the_local_row_alone_only_hands_the_work_to_planek(
        decode_color_local_patch_w1, decode_color_local_patch_off_w1):
    """The overlap, kept measured — the heart of the 2026-08-31 episode.

    `tiles.local` is not exclusive any more: remove it and
    `tiles.planek` mints the very same certificates, which is why the
    proof above had to become a claim about the TIER.  Pinning it here
    means the day the overlap ends — a re-hardened stimulus, or a
    change to either row — this case fails and the exclusive claim can
    be restored deliberately instead of by accident.
    """
    on = set(decode_color_local_patch_w1.certificates)
    without_local = set(decode_color_local_patch_off_w1.certificates)
    jobs = _jobs(decode_color_local_patch_off_w1)
    assert jobs.get("tiles.planek", 0) > 0, (
        "tiles.planek no longer fires when tiles.local is dropped: the "
        "overlap this module records has ended, and the tier claim can "
        "go back to being a claim about the row")
    assert on == without_local, (
        f"planek no longer covers for tiles.local exactly: "
        f"{sorted(on ^ without_local)}")


def test_a_single_capture_colour_decode_never_reaches_the_lane_pass(
        decode_color_local_patch_w1):
    _assert_single_lane_no_op("colour", decode_color_local_patch_w1,
                              COLOR_PATCH_FIRES)


def test_the_colour_control_really_ran_without_the_row(
        decode_color_local_patch_off_w1):
    assert "tiles.local" not in _jobs(decode_color_local_patch_off_w1)


def _emitted_page_bits(capture: object) -> np.ndarray:
    """The emitted page, one component triple per cell — absolute truth."""
    row = identity.resolve_format_ref(capture.format_ref)
    planes = np.unpackbits(_h3_sims.load_emit_gt(capture), axis=-1)
    cells_y = row.tiles_yx[0] * geometry.TILE_CELLS
    cells_x = row.tiles_yx[1] * geometry.TILE_CELLS
    step = planes.shape[1] // cells_y
    off = step // 2
    cells = planes[:, off::step, off::step][:, :cells_y, :cells_x]
    return np.ascontiguousarray(np.moveaxis(cells, 0, -1))


def test_every_colour_certificate_agrees_with_the_emitted_page(
        decode_color_local_patch_w1, sim_color_local_patch):
    row = identity.resolve_format_ref(sim_color_local_patch.format_ref)
    site_geometry = identity.build_site_geometry(row)
    page_bits = _emitted_page_bits(sim_color_local_patch)
    certificates = decode_color_local_patch_w1.certificates
    checks = _h3_support.Checks("colour-patch zero-wrong")
    addresses = sorted({key[:3] for key in certificates})
    assert addresses, "no colour certificates to audit"
    for page, ty, tx in addresses:
        projection = color_region.certified_projection(
            row, site_geometry, page, ty, tx, certificates)
        assert projection is not None
        bits, known = projection
        printed = page_bits[ty * geometry.TILE_CELLS:
                            (ty + 1) * geometry.TILE_CELLS,
                            tx * geometry.TILE_CELLS:
                            (tx + 1) * geometry.TILE_CELLS]
        wrong = int(np.count_nonzero((bits != printed) & known))
        checks.check(f"tile ({page},{ty},{tx}) zero wrong", wrong == 0,
                     f"{wrong} known component bits disagree with the "
                     f"emitted page")
    checks.assert_clean()


def test_the_colour_arm_is_payload_identical_at_one_and_eight_workers(
        decode_color_local_patch_w1, decode_color_local_patch_w8,
        sim_color):
    assert (decode_color_local_patch_w1.payload
            == decode_color_local_patch_w8.payload)
    assert decode_color_local_patch_w1.payload == sim_color.payload_data
    assert (decode_color_local_patch_w1.payload_sha256
            == sim_color.payload_sha256)


def test_replaying_a_local_job_on_the_finished_store_writes_no_evidence(
        decode_k_local_patch_w1):
    store = decode_k_local_patch_w1.engine
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
    assert written <= {"_attempt_outcomes", "_certificates", "_equations"}
