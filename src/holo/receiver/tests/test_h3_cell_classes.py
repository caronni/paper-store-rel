from __future__ import annotations

import dataclasses
import re

import numpy as np

from holo.receiver import data
from holo.receiver.descriptor import (
    KEY_EVIDENCE_READ,
    KEY_LATTICE_SEED,
    KEY_POSE_AFFINE,
    KEY_POSE_ROUTE,
    KEY_REGION_CTX,
    WorkerBookmark,
)
from holo.receiver.plugins import calibrate, refine
from holo.receiver.tests import _h3_facts, _h3_support

CAPTURE_ID = _h3_facts.CAPTURE_ID
WID = _h3_facts.WINDOW_ID
WID_B = (CAPTURE_ID, 0, 0, (64, 0, 128, 64))
REGION = (CAPTURE_ID, 0, 0)

ORIGIN_A = (0.0, 0.0)
ORIGIN_B = (8.0, 8.0)
BASIS_ONE = ((0, 0, 0),)
BASIS_TWO = ((0, 0, 0), (0, 0, 1))
#: A colour basis names the page field it was fitted through as well as
#: its certificates (R6); a K basis carries no marker at all.
FIELD_SEVEN = ((data.FIELD_BASIS_KEY, 7),)
FIELD_EIGHT = ((data.FIELD_BASIS_KEY, 8),)


class _Wakes:

    def __init__(self, engine: object) -> None:
        self.engine = engine
        self.pushed: list = []
        engine._push_worker = self.pushed.append

    def subscribe(self, *keys: tuple) -> WorkerBookmark:
        subject = ("probe", len(self.engine._bookmarks))
        worker = WorkerBookmark(plugin="probe", subject=subject, reads=keys)
        self.engine._bookmarks[("probe", subject)] = worker
        self.engine._register_reads(worker, keys)
        return worker


def _wakes(fact_name: str) -> tuple[object, _Wakes]:
    engine = _h3_facts.seeded_engine(fact_name)
    return engine, _Wakes(engine)


def _placement(quality: float, origin: tuple[float, float] = ORIGIN_A,
               route: str = "word",
               basis: tuple = ()) -> data.Placement:
    return dataclasses.replace(
        _h3_facts.placement(origin_yx=origin, route=route),
        quality=quality, refine_basis=basis)


def _ctx(loss: float | None, offset: float = 0.0,
         adopted: bool = True) -> data.RegionCtx:
    return dataclasses.replace(
        _h3_facts.region_ctx(adopted=adopted, offset=offset),
        validation_logloss=loss)


def _ctx_outcome(loss: float | None, offset: float = 0.0,
                 adopted: bool = True) -> object:
    return dataclasses.replace(
        _h3_facts.ctx_outcome(adopted=adopted, offset=offset),
        ctx=_ctx(loss, offset, adopted))


def _seed(support: int, ordinal: int) -> data.LatticeSeed:
    return dataclasses.replace(
        _h3_facts.lattice_seed(support_cells=support,
                               window_ordinal=ordinal),
        rows=np.full((2, 2), float(ordinal), np.float64))


#: One name per subject, 2026-09-05: the ordinal ownership test used to
#: assert the route constant and all three ordinals' rank laws under one
#: name.  Same builders, same nine assertions, five failure names.
def test_the_refine_route_constant_lives_only_in_the_cell_schema():
    assert refine.ROUTE_REFINE is data.ROUTE_REFINE, (
        "the route the placement ordinal ranks on is ONE constant living "
        "in the cell schema that the plugin imports — not two equal "
        "literals in two modules that a later edit could part")
    assert not re.search(
        r"^ROUTE_REFINE\s*[:=]", (_h3_support.HOLO3_ROOT
                                  / "plugins/refine.py").read_text(),
        re.MULTILINE), (
        "the producing plugin declares no route constant of its own")


def test_an_adopted_revision_outranks_any_original():
    original = _placement(0.25)
    revision = _placement(0.90, basis=BASIS_ONE, route=data.ROUTE_REFINE)
    assert data.placement_ordinal(revision) > data.placement_ordinal(
        original), (
        "an adopted revision outranks any original — its held-out gate "
        "already proved it better; the route rank keeps mismatch and "
        "logloss units from ever being compared")
    assert data.placement_ordinal(
        _placement(0.90, route=data.ROUTE_REFINE)) > data.placement_ordinal(
        _placement(0.01)), (
        "the rank holds even for a revision that carries no basis: the "
        "producer's adoption gate is the proof, not the scalar")


def test_the_placement_ordinal_ranks_a_lower_quality_first():
    assert data.placement_ordinal(_placement(0.1)) > data.placement_ordinal(
        _placement(0.2))


def test_a_newer_field_outranks_a_deeper_basis_and_a_better_loss():
    """R6: the field a pose was fitted through is part of its rank.

    Two refinements fitted through DIFFERENT page fields read their
    pixels at different places, so their held-out losses are not
    comparable at all, and depth is not either — the candidate here read
    one certificate fewer and scored worse than the pose it replaces.
    What proves it is the producer's held-out gate, which compared it
    with the pose standing when its job was prepared, through the field
    that job was prepared with.
    """
    standing = _placement(0.30, route=data.ROUTE_REFINE,
                          basis=BASIS_TWO + FIELD_SEVEN)
    candidate = _placement(0.40, route=data.ROUTE_REFINE,
                           basis=BASIS_ONE + FIELD_EIGHT)
    assert data.placement_ordinal(candidate) > data.placement_ordinal(
        standing), (
        "a refinement fitted through the newer field outranks the one it "
        "replaces even on fewer certificates and a worse scalar")


def test_a_pose_fitted_through_a_field_the_page_has_left_never_lands():
    """The other half of R6, and the reason it is safe.

    A candidate carrying an OLDER field revision was fitted against a
    sampling geometry this page has already superseded; whatever its
    depth or its loss, it cannot displace a pose fitted through the
    standing field.  The window stays eligible while the two differ, so
    the work comes back at the current field rather than being lost.
    """
    standing = _placement(0.90, route=data.ROUTE_REFINE,
                          basis=BASIS_ONE + FIELD_EIGHT)
    stale = _placement(0.01, route=data.ROUTE_REFINE,
                       basis=BASIS_TWO + FIELD_SEVEN)
    assert data.placement_ordinal(stale) < data.placement_ordinal(standing)


def test_the_field_marker_is_not_a_certificate():
    """The count the ordinal ranks on is CERTIFICATES.

    A colour refinement of a page with no solved field carries the
    marker at revision zero, and must rank exactly with the K
    refinement that read the same certificates — the marker is the name
    of a basis, never a unit of evidence.  At one field, depth decides
    again.
    """
    field_zero = ((data.FIELD_BASIS_KEY, 0),)
    assert data.placement_ordinal(
        _placement(0.20, route=data.ROUTE_REFINE,
                   basis=BASIS_ONE + field_zero)) == data.placement_ordinal(
        _placement(0.20, route=data.ROUTE_REFINE, basis=BASIS_ONE))
    assert data.placement_ordinal(
        _placement(0.20, route=data.ROUTE_REFINE,
                   basis=BASIS_TWO + FIELD_EIGHT)) > data.placement_ordinal(
        _placement(0.20, route=data.ROUTE_REFINE,
                   basis=BASIS_ONE + FIELD_EIGHT))


#: The pre-R6 spelling of the ordinal, kept as the K pin's reference:
#: route, basis length, -quality.
def _ordinal_before_the_field(placement: data.Placement) -> tuple:
    return (int(placement.route == data.ROUTE_REFINE),
            len(placement.refine_basis), -float(placement.quality))


def test_the_k_placement_order_is_what_it_was_before_the_field():
    """A K basis names no field, so R6 may not reorder one K pair.

    Brute force rather than a sample: every ordered pair of a set
    crossing the three routes that write this cell, four basis depths
    and a repeated quality (so ties are in the set), compared under the
    shipped ordinal and under the pre-R6 one.  Zero disagreements is
    the claim; one would be a silent re-ranking of every black-and-white
    sheet in the record.
    """
    population = [
        _placement(quality, route=route, basis=basis)
        for quality in (0.10, 0.30, 0.30, 0.90)
        for route in ("word", "chain", data.ROUTE_REFINE)
        for basis in ((), BASIS_ONE, BASIS_TWO, BASIS_TWO + ((0, 1, 0),))]
    disagreements = [
        (left, right) for left in population for right in population
        if ((data.placement_ordinal(left) > data.placement_ordinal(right))
            != (_ordinal_before_the_field(left)
                > _ordinal_before_the_field(right)))]
    assert not disagreements, disagreements[:3]


def test_a_refinement_under_a_newer_field_lands_on_fewer_certificates():
    """R6 through the fold: the ordinal is what the store gates on.

    The engine's own merge, not the tuple — a gate-approved pose whose
    only advantage is the field it was fitted through has to reach the
    cell and wake the pose key, or the colour lane refits it forever.
    """
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    engine._ingest(_placement(0.30, route=data.ROUTE_REFINE,
                              basis=BASIS_TWO + FIELD_SEVEN))
    changed, _kind = engine._ingest(
        _placement(0.40, origin=ORIGIN_B, route=data.ROUTE_REFINE,
                   basis=BASIS_ONE + FIELD_EIGHT))
    assert changed is True
    assert affine.version == 2
    assert engine.placement(WID).native_affine[2] == ORIGIN_B[0]


def test_a_refinement_under_an_older_field_is_a_no_op_that_wakes_nobody():
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    engine._ingest(_placement(0.40, route=data.ROUTE_REFINE,
                              basis=BASIS_ONE + FIELD_EIGHT))
    before = (affine.version, len(wakes.pushed))
    changed, _kind = engine._ingest(
        _placement(0.01, origin=ORIGIN_B, route=data.ROUTE_REFINE,
                   basis=BASIS_TWO + FIELD_SEVEN))
    assert changed is False
    assert (affine.version, len(wakes.pushed)) == before
    assert engine.placement(WID).native_affine[2] == ORIGIN_A[0]


def test_the_region_ctx_ordinal_ranks_adopted_fits_by_logloss():
    assert data.region_ctx_ordinal(_ctx(0.3)) > data.region_ctx_ordinal(
        _ctx(0.4))
    assert data.region_ctx_ordinal(_ctx(9.9)) > data.region_ctx_ordinal(
        _ctx(None, adopted=False))


def test_the_lattice_seed_ordinal_ranks_support_then_window_ordinal():
    assert data.lattice_seed_ordinal(_seed(20, 7)) > \
        data.lattice_seed_ordinal(_seed(19, 0))
    assert data.lattice_seed_ordinal(_seed(20, 3)) > \
        data.lattice_seed_ordinal(_seed(20, 7))


def test_a_worse_placement_is_a_no_op_that_wakes_nobody():
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    route = wakes.subscribe((KEY_POSE_ROUTE, WID))
    assert engine._ingest(_placement(0.10))[0] is True
    before = (affine.version, route.version, len(wakes.pushed))
    changed, _kind = engine._ingest(_placement(0.20, origin=ORIGIN_B,
                                               route="chain"))
    assert changed is False
    assert (affine.version, route.version, len(wakes.pushed)) == before
    assert engine.placement(WID).quality == 0.10
    assert engine.placement(WID).native_affine[2] == ORIGIN_A[0]
    assert engine.placement(WID).route == "word"


def test_a_better_placement_lands_and_wakes_its_keys():
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    engine._ingest(_placement(0.20))
    changed, _kind = engine._ingest(_placement(0.10, origin=ORIGIN_B))
    assert changed is True
    assert affine.version == 2
    assert engine.placement(WID).quality == 0.10


def test_the_placement_tie_break_is_deterministic_first_writer_stands():
    for first, second in ((ORIGIN_A, ORIGIN_B), (ORIGIN_B, ORIGIN_A)):
        engine, wakes = _wakes("Placement")
        affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
        assert engine._ingest(_placement(0.10, origin=first))[0] is True
        changed, _kind = engine._ingest(_placement(0.10, origin=second))
        assert changed is False
        assert affine.version == 1
        assert engine.placement(WID).native_affine[2] == first[0]


def test_a_placement_a_b_a_cycle_is_unrepresentable():
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    first = _placement(0.20)
    better = _placement(0.10, origin=ORIGIN_B)
    engine._ingest(first)
    engine._ingest(better)
    assert affine.version == 2
    changed, _kind = engine._ingest(first)
    assert changed is False
    assert affine.version == 2
    assert engine.placement(WID).quality == better.quality
    assert engine.placement(WID).native_affine == better.native_affine


def test_a_grown_basis_lands_even_at_slightly_worse_scalar_quality():
    engine, _wakes_unused = _wakes("Placement")
    engine._ingest(_placement(0.30, basis=BASIS_ONE, route="refine"))
    changed, _kind = engine._ingest(
        _placement(0.35, origin=ORIGIN_B, basis=BASIS_TWO, route="refine"))
    assert changed is True
    assert engine.placement(WID).refine_basis == BASIS_TWO
    shrunk, _kind = engine._ingest(_placement(0.01, basis=BASIS_ONE,
                                              route="refine"))
    assert shrunk is False
    assert engine.placement(WID).refine_basis == BASIS_TWO


def test_an_adopted_revision_outranks_the_original_across_units():
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    engine._ingest(_placement(0.05))
    changed, _kind = engine._ingest(
        _placement(0.90, origin=ORIGIN_B, route=refine.ROUTE_REFINE,
                   basis=BASIS_ONE))
    assert changed is True
    assert affine.version == 2
    assert engine.placement(WID).route == refine.ROUTE_REFINE


def test_a_worse_ctx_fit_is_a_no_op_that_wakes_nobody():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    assert engine._ingest(_ctx_outcome(0.40, offset=0.1))[0] is True
    assert ctx.version == 1
    before = len(wakes.pushed)
    changed, _kind = engine._ingest(_ctx_outcome(0.50, offset=0.2))
    assert changed is False
    assert ctx.version == 1 and len(wakes.pushed) == before
    assert engine.region_ctx(REGION).validation_logloss == 0.40


def test_a_better_ctx_fit_lands_and_wakes_the_region_key():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    engine._ingest(_ctx_outcome(0.40, offset=0.1))
    changed, _kind = engine._ingest(_ctx_outcome(0.30, offset=0.2))
    assert changed is True
    assert ctx.version == 2
    assert engine.region_ctx(REGION).validation_logloss == 0.30


def test_an_adopted_ctx_never_falls_back_to_a_refused_refit():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    engine._ingest(_ctx_outcome(0.40, offset=0.1))
    changed, _kind = engine._ingest(_ctx_outcome(None, adopted=False))
    assert changed is False
    assert ctx.version == 1
    assert engine.region_ctx(REGION).adopted is True
    lands, _kind = engine._ingest(_ctx_outcome(0.20, offset=0.3))
    assert lands is True and ctx.version == 2


def test_the_ctx_tie_break_is_deterministic_first_writer_stands():
    for first, second in ((0.1, 0.2), (0.2, 0.1)):
        engine, wakes = _wakes("CtxOutcome")
        ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
        engine._ingest(_ctx_outcome(0.40, offset=first))
        changed, _kind = engine._ingest(_ctx_outcome(0.40, offset=second))
        assert changed is False
        assert ctx.version == 1
        assert float(engine.region_ctx(REGION).offsets[0]) == np.float32(
            first)


def test_a_ctx_a_b_a_cycle_is_unrepresentable():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    first = _ctx_outcome(0.40, offset=0.1)
    engine._ingest(first)
    engine._ingest(_ctx_outcome(0.30, offset=0.2))
    changed, _kind = engine._ingest(first)
    assert changed is False
    assert ctx.version == 2
    assert engine.region_ctx(REGION).validation_logloss == 0.30


def test_a_window_arriving_under_a_standing_decision_is_read_through_it():
    """The fold head hands the standing offsets to a stripped arrival.

    Until 2026-10-03 a window that joined after the standing best waited
    for the next ctx outcome to carry its correction (bc730a0: coupling
    that to adoption starved late windows, 274 e029 certificates).  The
    head corrects it as it lands, under the STANDING fit -- never a
    refused re-fit's.
    """
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    engine._ingest(_ctx_outcome(0.40, offset=0.1))
    read_b = wakes.subscribe((KEY_EVIDENCE_READ, WID_B))
    arrival = _h3_facts.evidence(wid=WID_B)
    engine._ingest(arrival)
    standing = engine.evidence(WID_B)
    assert standing.ctx_adopted is True
    expected = calibrate.apply_standing_context(
        arrival, engine.region_ctx(REGION))
    assert np.array_equal(standing.printed_llr, expected.printed_llr)
    assert read_b.version == 1
    assert ctx.version == 1


def test_a_refused_refit_folds_to_no_change_and_wakes_nobody():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    read_b = wakes.subscribe((KEY_EVIDENCE_READ, WID_B))
    engine._ingest(_ctx_outcome(0.40, offset=0.1))
    engine._ingest(_h3_facts.evidence(wid=WID_B))
    corrected = engine.evidence(WID_B).printed_llr.copy()
    before = (ctx.version, read_b.version, len(wakes.pushed))
    for refit in (_ctx_outcome(0.50, offset=0.2),
                  _ctx_outcome(None, adopted=False)):
        changed, _kind = engine._ingest(refit)
        assert changed is False, (
            "a refused decision re-folds nothing: every row already "
            "carries the standing correction from its own fold")
    assert (ctx.version, read_b.version, len(wakes.pushed)) == before
    assert np.array_equal(engine.evidence(WID_B).printed_llr, corrected)
    assert float(engine.region_ctx(REGION).offsets[0]) == np.float32(0.1)


def test_a_weaker_lattice_seed_is_a_no_op_that_wakes_nobody():
    engine, wakes = _wakes("LatticeSeed")
    seed = wakes.subscribe((KEY_LATTICE_SEED,) + REGION)
    assert engine._ingest(_seed(20, 5))[0] is True
    assert seed.version == 1
    changed, _kind = engine._ingest(_seed(5, 0))
    assert changed is False and seed.version == 1


def test_a_stronger_lattice_seed_lands_and_wakes():
    engine, wakes = _wakes("LatticeSeed")
    seed = wakes.subscribe((KEY_LATTICE_SEED,) + REGION)
    engine._ingest(_seed(20, 5))
    changed, _kind = engine._ingest(_seed(21, 9))
    assert changed is True and seed.version == 2
    assert engine.lattice_seed(REGION).support_cells == 21


def test_the_seed_tie_break_is_the_window_ordinal_in_either_order():
    for first, second in ((5, 3), (3, 5)):
        engine, _probe = _wakes("LatticeSeed")
        engine._ingest(_seed(20, first))
        engine._ingest(_seed(20, second))
        assert engine.lattice_seed(REGION).window_ordinal == 3, (
            "equal support resolves on the producing window ordinal: both "
            "arrival orders converge on the same seed")


def test_a_seed_a_b_a_cycle_is_unrepresentable():
    engine, wakes = _wakes("LatticeSeed")
    seed = wakes.subscribe((KEY_LATTICE_SEED,) + REGION)
    engine._ingest(_seed(20, 5))
    engine._ingest(_seed(20, 3))
    assert seed.version == 2
    changed, _kind = engine._ingest(_seed(20, 5))
    assert changed is False and seed.version == 2
    assert engine.lattice_seed(REGION).window_ordinal == 3
