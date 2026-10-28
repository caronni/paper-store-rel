"""Unit pins for `tiles.planek` and the plane-isolation kernel.

Everything here is cheap and sim-free: the kernel's algebra, the row's
birth and eligibility gates, the standing-field consultation order, and
the transience law.  The existence proof — that the row certifies a tile
the ordinary colour path cannot — lives in
`test_h3_planek_existence.py`, which needs a rendered page.
"""

from __future__ import annotations

from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest

from holo3 import engine
from holo3.data import (
    AttemptFact,
    Certificate,
    PlaneField,
    WindowEvidence,
)
from holo3.format import identity
from holo3.lib import spectral
from holo3.lib.geometry import TILE_CELLS
from holo3.plugins import plane_k, tiles
from holo3.tests import _h3_support

K_FORMAT_REF = "L:c2-r0700@3392x2368"
CMY7_FORMAT_REF = "L:c3-cmy7-p120-v0@2240x1536"
CMY8_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"

PPC = Fraction(6)
SUBJECT = (0, 3, 4, "Y", PPC)

SHIFT_GRID_SIZE = 17
MIX_SEED = 20260831
MIX_ROWS = 512


def _row(ref: str):
    return identity.resolve_format_ref(ref)


# --------------------------------------------------------------------
# the kernel
# --------------------------------------------------------------------


def _synthetic(seed: int = MIX_SEED, n_rows: int = MIX_ROWS):
    """A noise-free page of channel means from a known subtractive mix."""
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, (n_rows, 3)).astype(np.uint8)
    m0 = np.asarray((235.0, 232.0, 228.0))
    # column p is plane p's shift; the OFF-DIAGONALS are the whole
    # problem this row exists for (measured on paper: magenta darkens
    # blue by 60% of what yellow does)
    coef = np.asarray(((-74.0, -24.0, -10.0),
                       (-21.0, -74.0, -17.0),
                       (-14.0, -21.0, -73.0)))
    values = m0 + bits.astype(np.float64) @ coef.T
    return values, bits, coef, m0


def test_the_mixing_model_recovers_the_channel_by_plane_shifts():
    values, bits, coef, m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    assert mix.accepted and mix.reason == spectral.REASON_ACCEPTED
    assert mix.n_full_rows == MIX_ROWS
    assert np.allclose(mix.m0, m0, atol=1e-6)
    assert np.allclose(mix.coef, coef, atol=1e-6)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_subtraction_is_exact_where_the_siblings_are_proven(plane):
    """THE ARM'S SECOND RUNG, as algebra.

    Where a cell's two sibling bits are known, their modelled
    contribution is subtracted and the residual projected on the target
    plane's own shift — so on a noise-free page the readout IS the plane
    bit, whatever the crosstalk.  The measured battery values this rung
    at five times the yield of the projection alone.
    """
    values, bits, _coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    score = spectral.plane_score(mix, values, bits, known, plane,
                                 spectral.MODE_SUBTRACT)
    assert np.allclose(score, bits[:, plane].astype(np.float64), atol=1e-6)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_the_projection_annihilates_both_siblings_in_the_mean(plane):
    values, bits, coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    functional = mix.projections[:, plane]
    for sibling in spectral.siblings_of(plane):
        assert abs(float(functional @ coef[:, sibling])) < 1e-9
    assert float(functional @ coef[:, plane]) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_with_no_sibling_proof_subtract_falls_back_to_the_projection(plane):
    values, bits, _coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    blind = np.zeros_like(bits, bool)
    blind[:, plane] = True
    subtracted = spectral.plane_score(mix, values, bits, blind, plane,
                                      spectral.MODE_SUBTRACT)
    projected = spectral.plane_score(mix, values, bits, blind, plane,
                                     spectral.MODE_PROJECT)
    assert np.array_equal(subtracted, projected)


def test_a_starved_or_thin_population_refuses_rather_than_fitting_noise():
    values, bits, _coef, _m0 = _synthetic(n_rows=64)
    known = np.ones_like(bits, bool)
    assert spectral.fit_plane_mix(values, bits, known).reason == (
        spectral.REASON_FEW_ROWS)
    values, bits, _coef, _m0 = _synthetic()
    bits[:, 2] = 0
    values = np.asarray(values)
    known = np.ones_like(bits, bool)
    assert spectral.fit_plane_mix(values, bits, known).reason == (
        spectral.REASON_STARVED)


def test_an_unknown_readout_mode_is_refused_by_name():
    values, bits, _coef, _m0 = _synthetic()
    known = np.ones_like(bits, bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    with pytest.raises(ValueError, match="unknown mode"):
        spectral.plane_score(mix, values, bits, known, 2, "blue")


# --------------------------------------------------------------------
# the offset grid and the standing field
# --------------------------------------------------------------------


def test_the_offset_grid_is_the_measured_one_and_leads_with_nominal():
    grid = plane_k.shift_grid()
    _h3_support.assert_golden("planek offset grid size", len(grid),
                              SHIFT_GRID_SIZE)
    assert grid[0] == 0.0, (
        "nominal must be the first candidate so a tie keeps the pose the "
        "receiver committed rather than a neighbouring offset"
    )
    assert sorted(grid) == [
        round(plane_k.SHIFT_MIN_DOTS + index * plane_k.SHIFT_STEP_DOTS, 6)
        for index in range(SHIFT_GRID_SIZE)]
    assert min(grid) == plane_k.SHIFT_MIN_DOTS
    assert max(grid) == plane_k.SHIFT_MAX_DOTS


def _field(delta_dots: float, supported: bool,
           tiles_yx: tuple[int, int] = (4, 4)) -> PlaneField:
    delta = np.zeros((*tiles_yx, 2), np.float64)
    delta[..., 0] = delta_dots
    support = np.full(tiles_yx, 1.0 if supported else 0.0)
    return PlaneField(capture_id="cap", level_index=0, page=0, plane=2,
                      delta_dots_xy=delta, support=support,
                      n_certificates=0, n_sites=0, residual=0.0,
                      median_delta_dots=abs(delta_dots))


def _cells_of_tile(ty: int, tx: int) -> np.ndarray:
    ys = np.arange(ty * TILE_CELLS, (ty + 1) * TILE_CELLS)
    xs = np.arange(tx * TILE_CELLS, (tx + 1) * TILE_CELLS)
    grid = np.stack(np.meshgrid(ys, xs, indexing="ij"), axis=-1)
    return grid.reshape(-1, 2)


def test_no_published_field_leaves_the_blind_estimator_in_charge():
    assert plane_k.field_delta_dots(None, _cells_of_tile(1, 1)) is None


def test_a_field_with_no_support_in_reach_is_not_consulted():
    """The row asks the standing fit first, but only where it HAS an
    answer: `lib/plane_field` returns exactly zero delta for a tile with
    no evidence in reach, which is the honest answer and not a
    measurement.  Taking that zero would silently retire the blind
    estimator over the very bands it exists for."""
    field = _field(1.75, supported=False)
    assert plane_k.field_delta_dots(field, _cells_of_tile(1, 1)) is None


def test_a_supported_field_speaks_first_and_carries_its_own_delta():
    field = _field(1.75, supported=True)
    delta = plane_k.field_delta_dots(field, _cells_of_tile(1, 1))
    assert delta is not None
    assert delta.shape == (TILE_CELLS * TILE_CELLS, 2)
    assert np.allclose(delta[:, 0], 1.75)
    assert np.allclose(delta[:, 1], 0.0)


def test_a_partly_supported_field_refuses_rather_than_extrapolating():
    field = _field(1.75, supported=True)
    field.support[1, 1] = 0.0
    assert plane_k.field_delta_dots(field, _cells_of_tile(1, 1)) is None


# --------------------------------------------------------------------
# the transient decoder input
# --------------------------------------------------------------------


def _evidence(accepted: bool = True, n_cells: int = 8) -> WindowEvidence:
    cells = np.stack((np.zeros(n_cells, np.int64),
                      np.arange(n_cells, dtype=np.int64)), axis=1)
    return WindowEvidence(
        window_id=("cap", 0, 0, (0, 0, 128, 128)), capture_id="cap",
        level_index=0, region_index=0, patch_ordinal=0, page=0,
        page_cells_yx=cells, scores=np.zeros(n_cells, np.float32),
        reference_values=np.zeros(n_cells, np.int8),
        knots=np.zeros(0), probs=np.zeros(0), n_search=0,
        marginal_llr=np.arange(n_cells, dtype=np.float32),
        printed_llr=np.arange(n_cells, dtype=np.float32),
        accepted=accepted, refusal_reason="" if accepted else "starved",
        heldout_logloss=0.25 if accepted else None, ctx_adopted=False)


@pytest.mark.parametrize("plane", (0, 1, 2))
def test_only_the_target_plane_column_carries_evidence(plane):
    """0.0 IS the erasure spelling, and `tiles._attempt_cmy8` reads only
    the stream's own column, so a plane-isolated cut says nothing at all
    about the two planes it did not read."""
    read = SimpleNamespace(window=SimpleNamespace(patch_ordinal=0))
    row = plane_k.transient_row(read, _evidence(), plane, 3)
    assert row is not None
    assert np.array_equal(row.values[:, plane],
                          np.arange(8, dtype=np.float32))
    for other in spectral.siblings_of(plane):
        assert not np.any(row.values[:, other])


def test_a_refused_window_contributes_no_transient_row():
    read = SimpleNamespace(window=SimpleNamespace(patch_ordinal=0))
    assert plane_k.transient_row(read, _evidence(accepted=False), 2,
                                 3) is None


def test_no_cut_means_no_attempt_and_no_fact():
    facts, events = plane_k.attempt_components(
        _row(CMY8_FORMAT_REF), None, (), "Y")
    assert facts == () and events == ()


# --------------------------------------------------------------------
# birth, eligibility, retirement, price
# --------------------------------------------------------------------


def _fact(stage: str = tiles.STAGE_RETRY150,
          outcome: str = tiles.OUTCOME_FAILED) -> AttemptFact:
    return AttemptFact(page=0, ty=3, tx=4, stream_id="Y", stage=stage,
                       outcome=outcome, n_informative=100, n_iters=150,
                       syndrome_ok=False, crc_ok=None,
                       components=(("cap", 0),))


def _store(ref: str, *, certified: frozenset = frozenset(),
           reach: tuple = ((3, 5),), color_rows: tuple = (("cap", 0, 0, 0),),
           ) -> SimpleNamespace:
    row = _row(ref)
    return SimpleNamespace(
        row=row, geometry=identity.build_site_geometry(row),
        level=lambda capture_id, level_index: SimpleNamespace(ppc=PPC),
        cover_lanes=lambda page, ty, tx, ppc: (("cap", 0),),
        tile_cover=lambda key: ((), color_rows),
        evidence_reach=lambda wid: None,
        color_row_cover_tiles=lambda key: tuple(
            (0, ty, tx, "cap", 0) for ty, tx in reach),
        has_certificate=lambda key: key in certified,
        union_rung_ordinal=lambda ppc: 0)


@pytest.mark.parametrize("ref", (K_FORMAT_REF, CMY7_FORMAT_REF))
def test_the_row_is_never_born_off_cmy8(ref):
    """cmy7 has no per-plane codeword to decode — its base-7 packing is a
    JOINT symbol over three planes — and K has no siblings to cancel.
    The gate is at birth, so neither page ever carries a planek subject."""
    store = _store(ref)
    fact = _fact()
    assert plane_k._planek_subjects(store, fact) == ()


def test_a_failed_cmy8_attempt_is_what_gives_the_row_a_subject():
    store = _store(CMY8_FORMAT_REF)
    assert plane_k._planek_subjects(store, _fact()) == (SUBJECT,)


@pytest.mark.parametrize("stage,outcome", (
    (tiles.STAGE_SCAN, tiles.OUTCOME_CERTIFIED),
    (tiles.STAGE_PLANEK150, tiles.OUTCOME_FAILED),
    (tiles.STAGE_LOCAL150, tiles.OUTCOME_FAILED),
))
def test_the_row_does_not_arm_itself_or_follow_a_certificate(stage, outcome):
    store = _store(CMY8_FORMAT_REF)
    assert plane_k._planek_subjects(store, _fact(stage, outcome)) == ()


def test_eligibility_is_the_local_rows_shape():
    store = _store(CMY8_FORMAT_REF,
                   certified=frozenset({(0, 3, 5, "C")}))
    assert plane_k._planek_eligible(store, SUBJECT)
    assert not plane_k._planek_retire(store, SUBJECT)


def test_no_certified_material_in_reach_means_no_fire():
    """A RESIDUE ARM BY CONSTRUCTION, and the ablation says so: with the
    certified neighbours' labels gone the measured battery certifies
    zero on every crop, even though the isolated signal is no worse.  A
    PAVA map fitted on 120 format sites per tile cannot price 3,976
    payload cells."""
    store = _store(CMY8_FORMAT_REF)
    assert not plane_k._planek_eligible(store, SUBJECT)
    assert plane_k.prepare_planek(store, SUBJECT, plane_k.STAGE_PLANEK) \
        is None


def test_no_covering_colour_row_means_no_fire():
    store = _store(CMY8_FORMAT_REF, certified=frozenset({(0, 3, 5, "C")}),
                   color_rows=())
    assert not plane_k._planek_eligible(store, SUBJECT)
    assert plane_k.prepare_planek(store, SUBJECT, plane_k.STAGE_PLANEK) \
        is None


def test_a_certified_target_retires_the_subject_before_any_pixel():
    store = _store(CMY8_FORMAT_REF,
                   certified=frozenset({(0, 3, 4, "Y"), (0, 3, 5, "C")}))
    assert plane_k._planek_retire(store, SUBJECT)
    assert not plane_k._planek_eligible(store, SUBJECT)
    assert plane_k.prepare_planek(store, SUBJECT, plane_k.STAGE_PLANEK) \
        is None


@pytest.mark.parametrize("ref", (K_FORMAT_REF, CMY7_FORMAT_REF))
def test_prepare_refuses_off_cmy8_even_if_a_subject_is_handed_to_it(ref):
    store = _store(ref, certified=frozenset({(0, 3, 5, "main")}))
    subject = (0, 3, 4, _row(ref).streams[0].stream_id, PPC)
    assert plane_k.prepare_planek(store, subject,
                                  plane_k.STAGE_PLANEK) is None
    assert not plane_k._planek_eligible(store, subject)


def test_the_row_declares_the_reads_that_can_wake_it():
    store = _store(CMY8_FORMAT_REF)
    keys = plane_k._planek_reads(store, SUBJECT)
    kinds = {key[0] for key in keys}
    assert kinds == {"color_row", "plane_field", "tile"}
    assert ("plane_field", "cap", 0, 0, 2) in keys, (
        "the row consults the standing field, so a newly published one "
        "must wake it")


def test_the_row_prices_itself_above_every_other_residue_row():
    # ...except `tiles.swim` (240) and the two colds (250/260).  Swim
    # pays a whole local colour head fit plus a bounded per-plane
    # raster search; this row re-reads one plane and searches an
    # offset.  Both are last resorts among residue rows; cold is last
    # by price (PAGE-DOMAIN §6), not a residue row.
    from holo3.plugins import place, swim

    store = _store(CMY8_FORMAT_REF)
    prices = {name: price for descriptor in engine.DESCRIPTORS
              for name, price in ((descriptor.name, value)
                                  for _stage, value in descriptor.prices)}
    assert plane_k.PLANEK_COST > max(
        price for name, price in prices.items()
        if name not in (plane_k.PLUGIN, swim.PLUGIN, "place"))
    assert swim.SWIM_COST > plane_k.PLANEK_COST
    assert place.STAGE_COST[place.STAGE_COLD_LIVE] > swim.SWIM_COST
    first = plane_k._planek_cost(store, SUBJECT, plane_k.STAGE_PLANEK, 1, 0)
    assert first == plane_k.PLANEK_COST
    third = plane_k._planek_cost(store, SUBJECT, plane_k.STAGE_PLANEK, 3, 0)
    assert third == 3 * plane_k.PLANEK_COST, (
        "the escalation door: nothing is capped, the row just drifts "
        "behind cheaper work each time a growing frontier wakes it")


def test_the_heavy_budget_is_the_one_the_tile_vocabulary_declares():
    assert plane_k.tiles.STAGE_PLANEK150 in tiles.HEAVY_STAGES
    assert tiles.max_iters_for(tiles.STAGE_PLANEK150) == (
        tiles.RETRY_BP_MAX_ITERS)


def test_the_descriptor_produces_only_transient_facts():
    descriptor = plane_k.PLANEK_DESCRIPTOR
    assert descriptor.produces == (AttemptFact, Certificate), (
        "the fits are built inside the job and dropped: no standing "
        "evidence row, no region context cell, no pose"
    )
    assert descriptor.born_by == (AttemptFact,)
    assert descriptor.subject_kind == "tile"
