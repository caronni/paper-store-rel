from __future__ import annotations

import dataclasses
import re

import numpy as np

from holo3 import data
from holo3.descriptor import (
    KEY_EVIDENCE_READ,
    KEY_LATTICE_SEED,
    KEY_POSE_AFFINE,
    KEY_POSE_ROUTE,
    KEY_REGION_CTX,
    WorkerBookmark,
)
from holo3.plugins import refine
from holo3.tests import _h3_facts, _h3_support

CAPTURE_ID = _h3_facts.CAPTURE_ID
WID = _h3_facts.WINDOW_ID
WID_B = (CAPTURE_ID, 0, 0, (64, 0, 128, 64))
REGION = (CAPTURE_ID, 0, 0)

ORIGIN_A = (0.0, 0.0)
ORIGIN_B = (8.0, 8.0)
BASIS_ONE = ((0, 0, 0),)
BASIS_TWO = ((0, 0, 0), (0, 0, 1))


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


def test_the_ordinals_are_owned_by_the_cell_schema_not_any_plugin():
    assert refine.ROUTE_REFINE is data.ROUTE_REFINE, (
        "the route the placement ordinal ranks on is ONE constant living "
        "in the cell schema that the plugin imports — not two equal "
        "literals in two modules that a later edit could part")
    assert not re.search(
        r"^ROUTE_REFINE\s*[:=]", (_h3_support.HOLO3_ROOT
                                  / "plugins/refine.py").read_text(),
        re.MULTILINE), (
        "the producing plugin declares no route constant of its own")
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
    assert data.placement_ordinal(_placement(0.1)) > data.placement_ordinal(
        _placement(0.2))
    assert data.region_ctx_ordinal(_ctx(0.3)) > data.region_ctx_ordinal(
        _ctx(0.4))
    assert data.region_ctx_ordinal(_ctx(9.9)) > data.region_ctx_ordinal(
        _ctx(None, adopted=False))
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


def test_outputs_derived_under_the_standing_decision_still_land():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    engine._ingest(_ctx_outcome(0.40, offset=0.1))
    assert ctx.version == 1
    late = dataclasses.replace(
        _ctx_outcome(0.40, offset=0.1),
        inputs=(_h3_facts.evidence(wid=WID_B),),
        outputs=(_h3_facts.evidence(wid=WID_B, ctx_adopted=True,
                                    printed=2.0),))
    changed, _kind = engine._ingest(late)
    assert changed is True, (
        "a re-fit reproducing the standing decision carries corrections "
        "for windows that arrived since: the derived rows land, the "
        "decision itself no-ops")
    assert engine.evidence(WID_B) is not None
    assert engine.evidence(WID_B).ctx_adopted is True
    assert ctx.version == 1


def _refused_refit_with_late_window() -> object:
    return dataclasses.replace(
        _ctx_outcome(0.50, offset=0.2),
        inputs=(_h3_facts.evidence(),
                _h3_facts.evidence(wid=WID_B)),
        outputs=(_h3_facts.evidence(ctx_adopted=True, printed=3.0),
                 _h3_facts.evidence(wid=WID_B, ctx_adopted=True,
                                    printed=3.0)))


def test_a_refusal_still_extends_the_standing_fit_to_a_starved_window():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    engine._ingest(_ctx_outcome(0.40, offset=0.1))
    engine._ingest(_h3_facts.evidence(wid=WID_B))
    assert engine.evidence(WID_B).ctx_adopted is False
    starved_printed = engine.evidence(WID_B).printed_llr.copy()
    read_b = wakes.subscribe((KEY_EVIDENCE_READ, WID_B))
    changed, _kind = engine._ingest(_refused_refit_with_late_window())
    assert changed is True, (
        "a refused re-fit is a refused DECISION, not a licence to starve "
        "the windows that joined after the standing best: the standing "
        "correction still reaches them")
    assert engine.evidence(WID_B).ctx_adopted is True
    assert not np.array_equal(engine.evidence(WID_B).printed_llr,
                              starved_printed, equal_nan=True)
    assert not np.array_equal(
        engine.evidence(WID_B).printed_llr,
        np.full(starved_printed.size, 3.0, np.float32)), (
        "the correction applied is the STANDING fit's, never the refused "
        "batch's own outputs")
    assert float(engine.evidence(WID).printed_llr[0]) == 1.0
    assert read_b.version == 1
    assert ctx.version == 1
    assert engine.region_ctx(REGION).validation_logloss == 0.40
    assert float(engine.region_ctx(REGION).offsets[0]) == np.float32(0.1)


def test_an_identical_repeat_refusal_after_the_application_wakes_nobody():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    read_b = wakes.subscribe((KEY_EVIDENCE_READ, WID_B))
    engine._ingest(_ctx_outcome(0.40, offset=0.1))
    engine._ingest(_h3_facts.evidence(wid=WID_B))
    engine._ingest(_refused_refit_with_late_window())
    assert engine.evidence(WID_B).ctx_adopted is True
    before = (ctx.version, read_b.version, len(wakes.pushed))
    changed, _kind = engine._ingest(_refused_refit_with_late_window())
    assert changed is False, (
        "once every input window carries the standing correction a repeat "
        "refusal folds to no change: the churn loop is unrepresentable")
    assert (ctx.version, read_b.version, len(wakes.pushed)) == before


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
