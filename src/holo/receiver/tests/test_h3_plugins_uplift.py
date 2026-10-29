from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver import data, engine
from holo.receiver.format import tile_codec
from holo.receiver.format.identity import (
    Family,
    build_site_geometry,
    resolve_format_ref,
)
from holo.receiver.plugins import (
    color_arms,
    color_conditioning,
    color_model,
    color_photometry,
    color_region_head as region_head,
    tiles,
    uplift,
)
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-18 (the owner's price balance): "a3 price by fire ordinal"
# [210, 210, 420, 630] -> [210, 420, 630, 840] -- every residue row pays
# base + base x earlier fires, its base once and never twice
# (measure/sched_trace/YIELD-OVER-CPU-2026-10-18.md §5-6); the literals
# are unchanged.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_a_planes_own_column_never_enters_its_own_pattern_code`,
# `test_the_ported_a3_constants_are_the_values_its_policy_token_names`,
# `test_the_ported_a4b_constants_are_the_values_its_policy_token_names`,
# `test_the_reveal_field_is_the_two_bit_hash_whose_low_bit_is_the_spec`,
# `test_the_row_runs_after_refinement_and_re_prices_by_fire_ordinal`.

CMY8_TINY = "c3-cmy8-r0550@2x2"
CMY7_FOSSIL = "L:c3-cmy7-p120-v0@2240x1536"
K_TINY = "c3-k-r0550@2x2"

# the v1 policy constants this port carries, with the token that names
# them (RECEIVE-DESIGN §6.2a "Identity and qualification")
A3_POLICY_TOKEN = "winphot-gainoffset-adaptivehalo-shrink20"
A4B_POLICY_TOKEN = "knownfield-conditioned-marginals-ulane-only"
A3_CONSTANTS = {
    "WINDOW_PHOT_PRIOR_LABELS": 20.0,
    "WINDOW_PHOT_HALO_POOL_WEIGHT": 1.0,
    "WINDOW_PHOT_MIN_SEARCH_LABELS": 40,
    "WINDOW_PHOT_MIN_STATES": 3,
    "WINDOW_PHOT_MIN_HELDOUT": 20,
    "WINDOW_PHOT_GATE_SLACK": 1e-9,
    "WINDOW_PHOT_MIN_VARIANCE": 1e-12,
}
A4B_CONSTANTS = {
    "CONDITIONING_REVEAL_MASK": 12,
    "CONDITIONING_REVEAL_SHIFT": 2,
    "CONDITIONING_N_PATTERNS": 4,
    "CONDITIONED_MIN_CLASS_LABELS": 6,
    "CONDITIONED_MIN_LABELS": 40,
    "CONDITIONED_MIN_VALIDATION": 20,
    "CONDITIONED_MAX_LABELS": 100_000,
    "CONDITIONING_MAX_CERT_CELLS": 400_000,
}

A3_PRICE = 210
A4B_PRICE = 220


@pytest.fixture(scope="module")
def cmy8_row() -> object:
    return resolve_format_ref(CMY8_TINY)


@pytest.fixture(scope="module")
def cmy8_geometry(cmy8_row) -> object:
    return build_site_geometry(cmy8_row)


def _page_cells(row) -> np.ndarray:
    height, width = row.cells_yx
    return np.stack(np.meshgrid(np.arange(height), np.arange(width),
                                indexing="ij"), axis=-1).reshape(-1, 2)


def _window_rows(row, geometry, cells, ordinal: int = 0) -> data.WindowRows:
    states, kinds = color_model.reference_states(row, geometry, 0, cells)
    known = states >= 0
    bits = tile_codec.states_to_planes(np.maximum(states, 0).astype(np.uint8))
    return data.WindowRows(
        patch_ordinal=ordinal,
        window_id=("cap", 0, ordinal, (0, 0) + row.cells_yx),
        page=0, local_cells_yx=cells, page_cells_yx=cells,
        scan_points_yx=cells.astype(np.float64), states=states,
        furniture_kind=kinds, known_component_bits=bits.astype(np.uint8),
        known_component_mask=np.repeat(known[:, None], 3, axis=1),
        heldout_logloss=None)


def _clean_features(states: np.ndarray, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    bits = tile_codec.states_to_planes(
        np.maximum(states, 0).astype(np.uint8))
    return 0.9 - 0.6 * bits.astype(np.float64) + rng.normal(
        0.0, 0.02, bits.shape)


# ---------------------------------------------------------------- constants


def test_the_ported_a3_constants_are_the_values_its_policy_token_names():
    found = {name: getattr(color_photometry, name) for name in A3_CONSTANTS}
    _h3_support.assert_measured(
        f"A3 constants ({A3_POLICY_TOKEN})", found, A3_CONSTANTS)


def test_the_ported_a4b_constants_are_the_values_its_policy_token_names():
    found = {name: getattr(color_conditioning, name)
             for name in A4B_CONSTANTS}
    _h3_support.assert_measured(
        f"A4b constants ({A4B_POLICY_TOKEN})", found, A4B_CONSTANTS)


def test_the_retired_applicability_floors_were_not_ported():
    # RECEIVE-DESIGN v0.52: A3's two region dispersion floors and A4b's
    # park flag are RETIRED, measured non-separating on 27 lanes of two
    # captures. Scheduling is the applicability answer; a floor here
    # would be a constant fitted to the corpus that refused the arm.
    retired = ("A3_DISPERSION_FLOOR", "A3_NORM_DISPERSION_FLOOR",
               "map_dispersion", "WindowMapDispersion")
    for name in retired:
        assert not hasattr(color_photometry, name), name
    assert not hasattr(color_conditioning, "CONDITIONING_PARKED")
    assert not hasattr(color_conditioning, "CONDITIONING_REASON_REGION_GATE")


def test_the_arms_expose_no_tuning_surface_beyond_the_shrinkage_prior():
    config = color_photometry.WindowPhotometryConfig()
    assert config.prior_labels == color_photometry.WINDOW_PHOT_PRIOR_LABELS
    stack = region_head.StackConfig()
    assert stack.window_photometry == config


def test_a_nonpositive_shrinkage_prior_is_refused():
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            color_photometry.WindowPhotometryConfig(prior_labels=bad)


# ------------------------------------------------------------------ A3 fit


def _faint_features(states: np.ndarray, seed: int = 3) -> np.ndarray:
    # THE TONE IS LOAD-BEARING (COLOR-UPLIFT-MEASUREMENTS §5.4): at the
    # full-contrast tone the eight classes sit a whole unit apart, a
    # page-global QDA separates them through any gain a valid map can
    # apply, and every held-out NLL is exactly -0.0 — so NO photometric
    # arm, right or wrong, could earn its gate. The faint tone is what
    # makes the question answerable at all.
    rng = np.random.default_rng(seed)
    bits = tile_codec.states_to_planes(
        np.maximum(states, 0).astype(np.uint8))
    return 0.90 - 0.12 * bits.astype(np.float64) + rng.normal(
        0.0, 0.045, bits.shape)


def _photometry_case(cmy8_row, cmy8_geometry, gains, offsets):
    cells = _page_cells(cmy8_row)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells)
    selection = region_head.owner_selection((rows,))
    features = _faint_features(rows.states)
    fitted, reason = region_head.fit_detector(
        cmy8_row.family, selection, (features,))
    assert reason == "" and fitted is not None
    distorted = features * np.asarray(gains) + np.asarray(offsets)
    return fitted, selection, rows, distorted


def test_the_window_map_fit_is_deterministic_and_rng_free(cmy8_row,
                                                          cmy8_geometry):
    fitted, selection, rows, distorted = _photometry_case(
        cmy8_row, cmy8_geometry, (1.30, 0.80, 1.15), (-0.12, 0.09, 0.04))
    config = color_photometry.WindowPhotometryConfig()
    first = color_photometry.fit_window_photometry(
        fitted.model, selection, (rows,), (distorted,), config)
    second = color_photometry.fit_window_photometry(
        fitted.model, selection, (rows,), (distorted,), config)
    assert first.accepted == second.accepted
    for left, right in zip(first.fits, second.fits):
        assert left.reason == right.reason
        if left.window_map is None:
            assert right.window_map is None
            continue
        assert np.array_equal(left.window_map.gains, right.window_map.gains)
        assert np.array_equal(left.window_map.offsets,
                              right.window_map.offsets)


def test_the_window_map_pulls_the_window_onto_the_region_class_means(
        cmy8_row, cmy8_geometry):
    fitted, selection, rows, distorted = _photometry_case(
        cmy8_row, cmy8_geometry, (1.30, 0.80, 1.15), (-0.12, 0.09, 0.04))
    result = color_photometry.fit_window_photometry(
        fitted.model, selection, (rows,), (distorted,),
        color_photometry.WindowPhotometryConfig())
    assert result.accepted == 1, result.reasons
    # the arm's own objective: "what affine transform would put this
    # window's labelled cells on top of the region model's classes?"
    known = selection.gather((distorted,))
    targets = np.asarray(fitted.model.means, np.float64)[selection.states]
    mapped = result.fits[0].window_map.apply(known)
    before = float(np.mean((known - targets) ** 2))
    after = float(np.mean((mapped - targets) ** 2))
    assert after < before, (
        f"the map must move the window toward the region class means "
        f"({after:.5f} !< {before:.5f})")
    # and the pre-gate it passed is the one that decides, on the window's
    # OWN held-out labels
    assert result.fits[0].candidate_nll < result.fits[0].identity_nll


def test_a_stronger_shrinkage_prior_pulls_the_map_toward_identity(
        cmy8_row, cmy8_geometry):
    fitted, selection, rows, distorted = _photometry_case(
        cmy8_row, cmy8_geometry, (1.30, 0.80, 1.15), (-0.12, 0.09, 0.04))
    previous = None
    for prior in (20.0, 200.0, 20_000.0):
        result = color_photometry.fit_window_photometry(
            fitted.model, selection, (rows,), (distorted,),
            color_photometry.WindowPhotometryConfig(prior_labels=prior))
        if not result.accepted:
            continue
        distance = float(np.max(np.abs(
            result.fits[0].window_map.gains - 1.0)))
        if previous is not None:
            assert distance < previous, (
                "shrinkage is measured in effective labels: a larger prior "
                "must move the fitted gain toward the identity map")
        previous = distance
    assert previous is not None


def test_a_starved_window_refuses_with_ks_own_vocabulary(cmy8_row,
                                                         cmy8_geometry):
    cells = _page_cells(cmy8_row)[:4]
    rows = _window_rows(cmy8_row, cmy8_geometry, cells)
    selection = region_head.owner_selection((rows,))
    full = _window_rows(cmy8_row, cmy8_geometry, _page_cells(cmy8_row))
    model = region_head.fit_detector(
        cmy8_row.family, region_head.owner_selection((full,)),
        (_clean_features(full.states),))[0].model
    result = color_photometry.fit_window_photometry(
        model, selection, (rows,), (_clean_features(rows.states),),
        color_photometry.WindowPhotometryConfig())
    assert result.accepted == 0
    assert result.arm_reason == color_photometry.REASON_NO_WINDOW_MAPS
    assert result.fits[0].reason in (
        color_photometry.REASON_SEARCH_STARVED,
        color_photometry.REASON_STATE_SUPPORT,
        color_photometry.REASON_HELDOUT_STARVED)


def test_a_region_with_no_accepted_map_hands_back_its_own_arrays(
        cmy8_row, cmy8_geometry):
    cells = _page_cells(cmy8_row)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells)
    selection = region_head.owner_selection((rows,))
    features = _clean_features(rows.states)
    model = region_head.fit_detector(
        cmy8_row.family, selection, (features,))[0].model
    given = (features,)
    result = color_photometry.fit_window_photometry(
        model, selection, (rows,), given,
        color_photometry.WindowPhotometryConfig())
    if result.accepted == 0:
        assert result.features is given, (
            "a refused arm is a BIT-EXACT null: the caller gets its own "
            "tuple object back, never an identity transform")


# ------------------------------------------------------------- A4b kernels


def test_a3_never_writes_into_the_feature_arrays_it_was_given(
        cmy8_row, cmy8_geometry):
    fitted, selection, rows, distorted = _photometry_case(
        cmy8_row, cmy8_geometry, (1.30, 0.80, 1.15), (-0.12, 0.09, 0.04))
    before = distorted.copy()
    result = color_photometry.fit_window_photometry(
        fitted.model, selection, (rows,), (distorted,),
        color_photometry.WindowPhotometryConfig())
    assert np.array_equal(distorted, before), (
        "the correction is TRANSIENT: the arm allocates a mapped tuple "
        "and never edits the evidence it was handed")
    if result.accepted:
        assert result.features[0] is not distorted


def test_the_reveal_field_is_the_two_bit_hash_whose_low_bit_is_the_spec():
    cells = np.stack(np.meshgrid(np.arange(64), np.arange(64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    codes = color_conditioning.masking_reveal_codes(cells)
    hashed = 131 * cells[:, 0] + 17 * cells[:, 1]
    assert np.array_equal(codes, ((hashed & 12) >> 2).astype(np.int8))
    # the low bit IS §6.2a's named &4 selector
    assert np.array_equal((codes & 1) != 0, (hashed & 4) != 0)
    counts = np.bincount(codes.astype(np.int64), minlength=4)
    _h3_support.assert_measured("reveal field partition over a tile",
                               tuple(counts.tolist()),
                               (1024, 1024, 1024, 1024))


def test_the_reveal_field_is_independent_of_the_qda_and_head_splits():
    cells = np.stack(np.meshgrid(np.arange(64), np.arange(64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    hashed = 131 * cells[:, 0] + 17 * cells[:, 1]
    codes = color_conditioning.masking_reveal_codes(cells)
    for split in (hashed & 1, hashed & 2):
        joint = np.bincount(
            (codes.astype(np.int64) * 2) + (split != 0).astype(np.int64),
            minlength=8)
        assert set(joint.tolist()) == {512}, (
            "the reveal field must partition every furniture cell "
            "independently of the &1 QDA split and the &2 head sub-split")


def test_a_planes_own_column_never_enters_its_own_pattern_code():
    mask = np.asarray([[True, False, False], [False, True, True],
                       [True, True, True], [False, False, False]], bool)
    codes = color_conditioning.conditioning_pattern_codes(mask)
    _h3_support.assert_measured(
        "pattern codes", codes.tolist(),
        [[0, 1, 1], [3, 2, 2], [3, 3, 3], [0, 0, 0]])


def test_conditioning_restricts_the_marginal_to_the_sibling_subset():
    rng = np.random.default_rng(7)
    scores = rng.normal(0.0, 2.0, (32, 8))
    mask = np.zeros((32, 3), bool)
    bits = np.zeros((32, 3), np.uint8)
    plain = color_conditioning.cmy8_conditioned_marginal_llrs(
        scores, mask, bits)
    assert np.array_equal(plain, color_model.cmy8_marginal_llrs(scores)), (
        "with nothing known the conditioned kernel must be the historical "
        "expression, value for value")
    mask[:, 1] = True
    bits[:, 1] = 1
    conditioned = color_conditioning.cmy8_conditioned_marginal_llrs(
        scores, mask, bits)
    assert not np.allclose(conditioned[:, 0], plain[:, 0])
    # plane 1 is its own column and is never conditioned on itself
    assert np.array_equal(conditioned[:, 1], plain[:, 1])
    allowed = color_conditioning.cmy8_sibling_allowed(0, mask, bits)
    assert np.array_equal(allowed.sum(axis=1), np.full(32, 4))


def test_a_starved_stratum_falls_back_to_the_unconditioned_marginal():
    rng = np.random.default_rng(11)
    n = 30
    population = color_conditioning.ConditioningPopulation(
        scores=rng.normal(0.0, 1.0, (n, 8)),
        bits=rng.integers(0, 2, (n, 3)).astype(np.uint8),
        labelled=np.ones((n, 3), bool),
        pattern=np.full((n, 3), 3, np.int8),
        kinds=np.ones(n, np.int8),
        from_certificates=np.zeros(n, bool))
    detector = _tiny_detector(rng)
    fit = color_conditioning.fit_conditioned_marginals(
        detector, population, population)
    assert fit.head is None
    assert fit.reason == color_conditioning.CONDITIONING_REASON_NO_STRATUM
    assert all(row.reason == color_conditioning.CONDITIONING_REASON_STARVED
               for row in fit.strata if row.pattern == 3)


def test_a4b_never_writes_into_the_population_it_was_given():
    rng = np.random.default_rng(23)
    n = 900
    states = np.tile(np.arange(8), n // 8)
    population = color_conditioning.ConditioningPopulation(
        scores=rng.normal(0.0, 1.0, (states.size, 8)),
        bits=tile_codec.states_to_planes(states.astype(np.uint8)),
        labelled=np.ones((states.size, 3), bool),
        pattern=np.tile(np.arange(4), states.size // 4 + 1
                        )[:states.size, None].repeat(3, axis=1
                                                     ).astype(np.int8),
        kinds=(np.arange(states.size) % 2).astype(np.int8),
        from_certificates=np.zeros(states.size, bool))
    before = tuple(np.array(getattr(population, name), copy=True)
                   for name in ("scores", "bits", "labelled", "pattern"))
    detector = _tiny_detector(rng)
    color_conditioning.fit_conditioned_marginals(
        detector, population, population)
    for name, snapshot in zip(("scores", "bits", "labelled", "pattern"),
                              before):
        assert np.array_equal(getattr(population, name), snapshot), name


def _tiny_detector(rng) -> color_model.Cmy8Detector:
    states = np.repeat(np.arange(8), 24)
    bits = tile_codec.states_to_planes(states.astype(np.uint8))
    features = 0.9 - 0.6 * bits + rng.normal(0.0, 0.03, bits.shape)
    return color_model.fit_cmy8_detector(features, states, features, states)


# --------------------------------------------------------- row eligibility


def _attempt(page=0, ty=0, tx=0, stream_id="c",
             outcome=tiles.OUTCOME_FAILED) -> data.AttemptFact:
    return data.AttemptFact(
        page=page, ty=ty, tx=tx, stream_id=stream_id,
        stage=tiles.STAGE_SCAN, outcome=outcome, n_informative=1,
        n_iters=1, syndrome_ok=False, crc_ok=False,
        components=(("cap", 0),))


def _subject_store(row, certified=()) -> SimpleNamespace:
    keys = set(certified)
    return SimpleNamespace(
        row=row,
        has_certificate=lambda key: key in keys,
        certificate_keys=lambda: tuple(sorted(keys)))


def test_a_k_coding_never_births_a_supplemental_subject():
    row = resolve_format_ref(K_TINY)
    assert row.family is Family.K
    assert color_arms.arms_for_family(Family.K) == ()
    store = _subject_store(row)
    assert uplift._uplift_subjects(store, _attempt(stream_id="main")) == ()


def test_a_single_stream_coding_never_births_the_a4b_arm():
    row = resolve_format_ref(CMY7_FOSSIL)
    assert row.family is Family.CMY7
    assert len(row.streams) == 1, (
        "cmy7 packs one stream, so A4b has no sibling to condition on")
    assert color_arms.arms_for_family(Family.CMY7) == (
        color_arms.UPLIFT_ARM_A3,)
    store = _subject_store(row)
    subjects = uplift._uplift_subjects(store, _attempt(stream_id="main"))
    arms = {subject[3] for subject in subjects}
    assert arms == {color_arms.UPLIFT_ARM_A3}


def test_a_certified_tile_births_nothing_and_a_failure_births_both_arms(
        cmy8_row):
    store = _subject_store(cmy8_row)
    certified = _subject_store(
        cmy8_row, certified={(0, 0, 0, "c")})
    assert uplift._uplift_subjects(
        store, _attempt(outcome=tiles.OUTCOME_CERTIFIED)) == ()
    assert uplift._uplift_subjects(certified, _attempt()) == ()
    subjects = uplift._uplift_subjects(store, _attempt())
    assert {subject[3] for subject in subjects} == set(
        color_arms.UPLIFT_ARMS)
    assert {subject[:3] for subject in subjects} == {("cap", 0, 0)}


def _targets_store(row, certified) -> SimpleNamespace:
    keys = set(certified)
    return SimpleNamespace(
        row=row,
        has_certificate=lambda key: key in keys,
        window_cover_tiles=lambda wid: ((0, 0, 0, "cap", 0),))


def test_a4b_never_fires_on_a_tile_with_no_certified_sibling(cmy8_row):
    store = _targets_store(cmy8_row, ())
    assert uplift.lane_targets(store, color_arms.UPLIFT_ARM_A4B, "cap", 0,
                               0, ("w",)) == ()
    a3 = uplift.lane_targets(store, color_arms.UPLIFT_ARM_A3, "cap", 0, 0,
                             ("w",))
    assert len(a3) == 1 and len(a3[0][2]) == len(cmy8_row.streams), (
        "the zero-frontier fix: A3 needs only poses and a residue")


def test_a4b_fires_on_exactly_the_tiles_that_keep_a_certified_sibling(
        cmy8_row):
    first = cmy8_row.streams[0].stream_id
    store = _targets_store(cmy8_row, {(0, 0, 0, first)})
    targets = uplift.lane_targets(store, color_arms.UPLIFT_ARM_A4B, "cap",
                                  0, 0, ("w",))
    assert len(targets) == 1
    assert first not in targets[0][2]
    assert len(targets[0][2]) == len(cmy8_row.streams) - 1


def test_a_fully_certified_tile_is_never_offered_to_either_arm(cmy8_row):
    every = {(0, 0, 0, stream.stream_id) for stream in cmy8_row.streams}
    store = _targets_store(cmy8_row, every)
    for arm in color_arms.UPLIFT_ARMS:
        assert uplift.lane_targets(store, arm, "cap", 0, 0, ("w",)) == (), (
            "monotone by construction: a certified address is never "
            "re-attempted")


# --------------------------------------------------------------- the row


def test_the_row_declares_only_attempts_and_certificates():
    assert uplift.UPLIFT_DESCRIPTOR.produces == (
        data.AttemptFact, data.Certificate), (
        "the correction is transient: the row writes no evidence row and "
        "no standing cell")
    assert uplift.UPLIFT_DESCRIPTOR.born_by == (data.AttemptFact,)
    assert uplift.UPLIFT_DESCRIPTOR.name == "tiles.uplift"


def test_the_row_runs_after_refinement_and_re_prices_by_fire_ordinal():
    prices = {name: price for descriptor in engine.DESCRIPTORS
              for name, price in ((descriptor.name, value)
                                  for _stage, value in descriptor.prices)}
    assert A3_PRICE > prices["refine"] and A4B_PRICE > prices["refine"], (
        "a supplemental row must run after every lane that could still "
        "shrink the residue")
    descriptor = uplift.UPLIFT_DESCRIPTOR
    subject = ("cap", 0, 0, color_arms.UPLIFT_ARM_A3)
    ladder = [descriptor.cost(None, subject, uplift.STAGE_A3, n, 0)
              for n in range(4)]
    _h3_support.assert_measured("a3 price by fire ordinal", ladder,
                               [210, 420, 630, 840])
    a4b = ("cap", 0, 0, color_arms.UPLIFT_ARM_A4B)
    assert descriptor.cost(None, a4b, uplift.STAGE_A4B, 2, 0) == 660
    assert descriptor.cost(None, ("cap", 3, 0, "a3"), uplift.STAGE_A3,
                           0, 0) == A3_PRICE + 3 * uplift.RUNG_COST


def test_the_heavy_budget_is_the_retry_budget_and_lives_in_one_place():
    assert tiles.max_iters_for(uplift.STAGE_A3) == tiles.RETRY_BP_MAX_ITERS
    assert tiles.max_iters_for(uplift.STAGE_A4B) == tiles.RETRY_BP_MAX_ITERS
    assert tiles.RETRY_BP_MAX_ITERS == 150
    assert uplift.STAGE_A3 not in tiles.ORDINARY_STAGES
    assert uplift.STAGE_A4B not in tiles.ORDINARY_STAGES


def test_a_supplemental_attempt_never_re_arms_the_ordinary_retry_row():
    fact = _attempt()
    heavy = data.AttemptFact(
        **{**fact.__dict__, "stage": uplift.STAGE_A3})
    assert tiles.arms_retry(heavy, False) is False, (
        "the supplemental stages are not ordinary stages, so a failed "
        "supplemental attempt cannot manufacture a retry")


def test_the_row_retires_when_the_page_has_no_residue_left():
    grid_done = np.ones((2, 2), bool)
    grid_open = np.zeros((2, 2), bool)
    subject = ("cap", 0, 0, color_arms.UPLIFT_ARM_A3)
    for grid, cause in ((grid_done, uplift.RETIRE_PAGE_DONE),
                        (grid_open, None)):
        store = SimpleNamespace(
            lane_page_windows=lambda *a: ("w",),
            done_grid=lambda page, grid=grid: grid)
        assert uplift._uplift_retire(store, subject) == cause
        assert uplift._uplift_eligible(store, subject) is (cause is None)


def test_the_row_reads_the_poses_the_frontier_and_the_page_field():
    """The supplemental arms read through the page field like the lane.

    They run `build_region_inputs`, so a newly solved field changes what
    they sample; a row that did not subscribe would go on reading at the
    bare pose until something else happened to wake it.
    """
    subject = ("cap", 0, 3, color_arms.UPLIFT_ARM_A4B)
    assert uplift._uplift_reads(None, subject) == (
        ("lane_poses", "cap", 0, 3), ("page_certs", 3),
        ("plane_field", 3, 0), ("plane_field", 3, 1),
        ("plane_field", 3, 2))


def test_the_standard_ladder_never_reaches_either_arm(cmy8_row,
                                                      cmy8_geometry,
                                                      monkeypatch):
    cells = _page_cells(cmy8_row)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells)
    selection = region_head.owner_selection((rows,))
    features = (_clean_features(rows.states),)
    calls: list[str] = []
    monkeypatch.setattr(
        color_photometry, "fit_window_photometry",
        lambda *a, **k: calls.append("a3"))
    monkeypatch.setattr(
        color_conditioning, "fit_conditioned_marginals",
        lambda *a, **k: calls.append("a4b"))
    region_head.fit_region_stack(
        cmy8_row, selection, (rows,), features, None,
        (np.ones(cells.shape[0], bool),), region_head.StackConfig())
    assert calls == [], (
        "override-only reachability: the standard ladder has no branch "
        "that could engage either arm, so it does not even pay for one")
