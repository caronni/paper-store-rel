from __future__ import annotations

import dataclasses
import inspect
import weakref
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.special import logsumexp

from holo.receiver import data, engine
from holo.receiver.format import pilots, tile_codec
from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.lib import geometry
from holo.receiver.plugins import color_model, color_refine, color_region
from holo.receiver.plugins import color_sites
from holo.receiver.plugins import color_region_anchor as anchor
from holo.receiver.plugins import color_region_ctx as ctx
from holo.receiver.plugins import color_region_head as region_head
from holo.receiver.tests import _h3_facts, _h3_fixture_geometry, _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_blind_component_bits_separate_a_bimodal_reflectance`,
# `test_color_collect_labels_expands_furniture_into_three_plane_rows`,
# `test_fit_cmy7_head_walks_its_support_floors`,
# `test_improves_needs_a_strict_gain_that_costs_no_furniture_leg`,
# `test_qualify_cmy8_support_walks_its_class_and_diversity_floors`.

CMY8_TINY = "c3-cmy8-r0550@2x2"
CMY7_FOSSIL = "L:c3-cmy7-p120-v0@2240x1536"

RASTER_PPC = 6
RASTER_MARGIN_PX = 24
RASTER_PAPER = 240
RASTER_INK = 60
RASTER_NOISE_SEED = 9

SHEARED_AFFINE = (12.03, 0.021, 5000.0, -0.019, 12.05, 4000.0)
AFFINE_ULP_BAR_PX = 1e-11
HALF_CELL_SIGNATURE_PX = 6.0

# D6.8(a) landed: lane_generation is gone; the surviving contract is the
# scheduler's one-in-flight rule (a stale result never lands because an
# older job is never in flight beside a newer one)
LANE_GENERATION_IS_MECHANISM = False

COLOR_LANE = ("cap", 0, 0)
COLOR_LANE_RUNG_1 = ("cap", 1, 0)
COLOR_ASSEMBLY_PRICE = 15
COLOR_REFIT_PRICES = (160, 320, 480)
RUNG_PREMIUM = 2

RETIRED_LABEL_CAP = 40_000
FULL_FIT_ROWS = 45_000


@pytest.fixture(scope="module")
def cmy8_row() -> object:
    return resolve_format_ref(CMY8_TINY)


@pytest.fixture(scope="module")
def cmy8_geometry(cmy8_row) -> object:
    return _h3_fixture_geometry.memoised_site_geometry(cmy8_row)


def _page_cells(row) -> np.ndarray:
    height, width = row.cells_yx
    return np.stack(np.meshgrid(np.arange(height), np.arange(width),
                                indexing="ij"), axis=-1).reshape(-1, 2)


def _color_row(page: int, ordinal: int,
               values: np.ndarray) -> data.ColorEvidenceRow:
    return data.ColorEvidenceRow(
        capture_id="cap", level_index=0, patch_ordinal=ordinal, page=page,
        page_cells_yx=np.asarray([[0, 0], [0, 1]], np.int64),
        values=values, heldout_logloss=0.1)


def _fold(store: object, fact: data.ColorEvidenceRow) -> tuple:
    return engine._Engine._fold_color_row(store, fact)


def _fold_store(geometry: object) -> SimpleNamespace:
    # `_advance_tile_lanes` is the fold's own method (INV-G1), so the
    # bench borrows it unbound exactly as it borrows `_fold_color_row`.
    store = SimpleNamespace(_color_rows={}, _tile_cover_color={},
                            _color_row_cover={}, _color_row_lanes=set(),
                            _tile_lane_generation={},
                            _union_generation={},
                            _levels={("cap", 0): data.Level(
                                index=0, ppc=Fraction(8), scale=Fraction(1),
                                shape_px=(8, 8), label="l0")},
                            geometry=geometry)
    store._advance_tile_lanes = (
        lambda keys: engine._Engine._advance_tile_lanes(store, keys))
    return store


def test_lane_generation_is_gone_and_one_in_flight_is_the_replacement():
    assert LANE_GENERATION_IS_MECHANISM is False
    fields = tuple(f.name for f in dataclasses.fields(data.ColorEvidenceRow))
    assert "lane_generation" not in fields
    assert "lane_generation" not in inspect.signature(
        color_region.region_job).parameters
    assert "lane_generation" not in inspect.getsource(
        engine._Engine._fold_color_row)
    from holo.receiver.descriptor import WorkerBookmark

    bookmark_fields = tuple(
        f.name for f in dataclasses.fields(WorkerBookmark))
    assert "inflight" in bookmark_fields
    assert "pending" in bookmark_fields


def test_a_fresh_colour_lane_result_is_folded_and_wakes_its_own_row_key(
        cmy8_geometry):
    store = _fold_store(cmy8_geometry)
    changed, keys, kind = _fold(
        store, _color_row(0, 3, np.asarray([[1.0], [2.0]], np.float32)))
    assert changed is True
    assert keys == (("color_row", "cap", 0, 0, 3),)
    assert kind == "other"
    assert sorted(store._color_rows) == [("cap", 0, 0, 3)]
    assert store._color_row_cover[("cap", 0, 0, 3)] == tuple(sorted(
        store._tile_cover_color))


def test_a_changed_colour_lane_result_replaces_the_standing_row(
        cmy8_geometry):
    store = _fold_store(cmy8_geometry)
    first = _color_row(0, 3, np.asarray([[1.0], [2.0]], np.float32))
    second = _color_row(0, 3, np.asarray([[9.0], [9.0]], np.float32))
    assert _fold(store, first)[0] is True
    changed, keys, _kind = _fold(store, second)
    assert changed is True
    assert keys == (("color_row", "cap", 0, 0, 3),)
    standing = store._color_rows[("cap", 0, 0, 3)]
    assert standing is second


def test_an_identical_colour_lane_result_changes_nothing(cmy8_geometry):
    store = _fold_store(cmy8_geometry)
    values = np.asarray([[1.0], [2.0]], np.float32)
    assert _fold(store, _color_row(0, 3, values))[0] is True
    changed, keys, _kind = _fold(
        store, _color_row(0, 3, np.array(values, copy=True)))
    assert changed is False
    assert keys == ()


def test_colour_lane_rows_are_keyed_by_capture_level_page_and_ordinal(
        cmy8_geometry):
    store = _fold_store(cmy8_geometry)
    values = np.asarray([[1.0], [2.0]], np.float32)
    for page, ordinal in ((0, 3), (1, 3), (0, 4)):
        _fold(store, _color_row(page, ordinal, values))
    assert sorted(store._color_rows) == [
        ("cap", 0, 0, 3), ("cap", 0, 0, 4), ("cap", 0, 1, 3)]


def test_blind_component_bits_separate_a_bimodal_reflectance():
    rng = np.random.default_rng(70707)
    dark = rng.normal(0.2, 0.02, 400)
    light = rng.normal(0.9, 0.02, 400)
    means = np.concatenate((dark, light))
    bits, llr = color_model.blind_component_bits(means)
    assert bits.dtype == np.uint8
    assert np.array_equal(bits, (llr > 0.0).astype(np.uint8))
    assert bits[:400].all()
    assert not bits[400:].any()
    assert float(np.abs(llr).min()) > 0.0
    _h3_support.assert_measured("BLIND_CONFIDENT_LLR",
                               color_model.BLIND_CONFIDENT_LLR, 2.0)


def _mixture(rng: np.random.Generator, n_states: int, per_state: int,
             spread: float = 0.05
             ) -> tuple[np.ndarray, np.ndarray]:
    states = np.repeat(np.arange(n_states), per_state)
    bits = tile_codec.states_to_planes(states.astype(np.uint8))
    features = (0.9 - 0.6 * bits.astype(np.float64)
                + rng.normal(0.0, spread, bits.shape))
    return features, states


def test_fit_qda_recovers_the_planted_class_means_and_scores():
    rng = np.random.default_rng(20260829)
    features, states = _mixture(rng, 8, 120)
    model = color_model.fit_qda(features, states, 8)
    assert model.n_states == 8 and model.n_features == 3
    assert model.degenerate is False
    assert model.clipped_planes == ()
    assert np.array_equal(model.class_counts, np.full(8, 120))
    for state in range(8):
        planted = 0.9 - 0.6 * tile_codec.states_to_planes(
            np.uint8(state)).astype(np.float64)
        assert np.allclose(model.means[state], planted, atol=0.02)
    scores = color_model.qda_log_scores(model, features)
    assert scores.shape == (features.shape[0], 8)
    assert np.array_equal(np.argmax(scores, axis=1), states)
    reference = np.empty_like(scores)
    for state in range(8):
        difference = features - model.means[state]
        whitened = np.linalg.solve(model.cholesky[state], difference.T)
        reference[:, state] = (-0.5 * (whitened * whitened).sum(axis=0)
                               - 0.5 * model.log_determinants[state])
    assert np.array_equal(scores, reference)


def test_fit_qda_flags_a_missing_class_as_degenerate():
    rng = np.random.default_rng(4321)
    features, states = _mixture(rng, 8, 40)
    keep = states != 5
    model = color_model.fit_qda(features[keep], states[keep], 8)
    assert model.degenerate is True
    assert int(model.class_counts[5]) == 0
    clipped = color_model.clip_unsupported_planes(
        model, np.full((4, 3), 9.0))
    assert np.all(np.abs(clipped) <= color_model.DEGENERATE_LLR_CLIP)


def test_fit_qda_clips_the_planes_that_two_collapsed_states_share():
    rng = np.random.default_rng(99)
    states = np.repeat(np.arange(8), 60)
    bits = tile_codec.states_to_planes(states.astype(np.uint8)).astype(
        np.float64)
    bits[:, 0] = 0.0
    features = 0.9 - 0.6 * bits + rng.normal(0.0, 0.02, bits.shape)
    model = color_model.fit_qda(features, states, 8)
    assert 0 in model.clipped_planes


def test_cmy8_marginal_llrs_match_a_brute_force_bit_marginalisation():
    rng = np.random.default_rng(5150)
    scores = rng.normal(0.0, 3.0, size=(40, 8))
    marginals = color_model.cmy8_marginal_llrs(scores)
    bits = tile_codec.states_to_planes(
        np.arange(8, dtype=np.uint8)).astype(bool)
    expected = np.empty((40, 3), np.float64)
    for plane in range(3):
        one = bits[:, plane]
        expected[:, plane] = (logsumexp(scores[:, one], axis=1)
                              - logsumexp(scores[:, ~one], axis=1))
    assert np.array_equal(marginals, expected)
    assert np.array_equal(marginals, ctx.plane_marginals(scores))


def test_cmy7_relative_scores_pin_state_zero_as_the_reference():
    rng = np.random.default_rng(606)
    features, states = _mixture(rng, 7, 60)
    model = color_model.fit_qda(features, states, 7)
    relative = color_model.cmy7_relative_scores(model, features)
    scores = color_model.qda_log_scores(model, features)
    assert np.array_equal(relative, scores[:, 1:] - scores[:, :1])
    assert relative.shape == (features.shape[0], 6)
    assert np.array_equal(ctx.augment(relative)[:, 0], np.zeros(
        features.shape[0]))


def _states_with(counts: dict[int, int]) -> np.ndarray:
    return np.concatenate([np.full(n, state, np.int64)
                           for state, n in sorted(counts.items())])


def test_qualify_cmy8_support_walks_its_class_and_diversity_floors():
    _h3_support.assert_measured(
        "cmy8 calibration floors",
        (color_model.CMY8_CALIBRATION_MIN_CLASS_LABELS,
         color_model.CMY8_CALIBRATION_MIN_STATES_PER_CLASS,
         color_model.CMY8_CALIBRATION_MIN_LABELS_PER_STATE),
        (6, 2, 3))
    healthy = _states_with({state: 6 for state in range(8)})
    supported, reasons = color_model.qualify_cmy8_support(healthy)
    assert supported == (True, True, True)
    assert reasons == (None, None, None)
    starved = _states_with({0: 40, 1: 1, 2: 40, 3: 1, 4: 40, 5: 1, 6: 40,
                            7: 1})
    supported, reasons = color_model.qualify_cmy8_support(starved)
    assert supported[0] is False
    assert reasons[0] == "class_labels:1"
    thin = _states_with({0: 40, 1: 8, 2: 40, 3: 1, 4: 40, 5: 1,
                         6: 40, 7: 1})
    supported, reasons = color_model.qualify_cmy8_support(thin)
    assert supported[0] is False
    assert reasons[0] == "state_diversity:1"


def test_fit_cmy8_detector_calibrates_every_supported_plane():
    rng = np.random.default_rng(1717)
    training, training_states = _mixture(rng, 8, 200)
    calibration, calibration_states = _mixture(rng, 8, 40)
    detector = color_model.fit_cmy8_detector(
        training, training_states, calibration, calibration_states)
    assert detector.supported_planes == (True, True, True)
    assert detector.unsupported_reasons == (None, None, None)
    assert detector.calibration_labels == calibration_states.size
    llrs = detector.llrs(calibration)
    bits = tile_codec.states_to_planes(
        calibration_states.astype(np.uint8))
    assert np.array_equal((llrs > 0.0).astype(np.uint8), bits)


def test_fit_cmy8_detector_zeroes_a_plane_without_calibration_support():
    rng = np.random.default_rng(2323)
    training, training_states = _mixture(rng, 8, 200)
    calibration, calibration_states = _mixture(rng, 8, 40)
    keep = (calibration_states & 1) == 0
    keep[:2] = True
    detector = color_model.fit_cmy8_detector(
        training, training_states, calibration[keep],
        calibration_states[keep])
    assert detector.supported_planes[0] is False
    assert detector.unsupported_reasons[0] is not None
    assert np.array_equal(detector.llrs(calibration)[:, 0],
                          np.zeros(calibration.shape[0]))


def test_fit_component_pava_is_a_monotone_calibration_map():
    rng = np.random.default_rng(808)
    scores = rng.normal(0.0, 2.0, 600)
    labels = (rng.random(600) < 1.0 / (1.0 + np.exp(-scores))).astype(
        np.int64)
    fitted = color_model.fit_component_pava(scores, labels)
    assert fitted.n_labels == 600
    assert np.all(np.diff(fitted.score_nodes) > 0.0)
    assert np.all(np.diff(fitted.probability_nodes) >= 0.0)
    assert float(fitted.probability_nodes.min()) > 0.0
    assert float(fitted.probability_nodes.max()) < 1.0
    llrs = fitted.llrs(np.sort(scores))
    assert np.all(np.diff(llrs) >= -1e-12)


def test_neutral_pava_map_emits_a_zero_llr_everywhere():
    neutral = color_model.neutral_pava_map(17)
    assert neutral.n_labels == 17
    assert np.array_equal(neutral.llrs(np.asarray([-9.0, 0.0, 9.0])),
                          np.zeros(3))


def test_head_sub_split_is_the_second_bit_of_the_site_hash():
    keys = np.stack((np.zeros(64, np.int64),
                     np.arange(64, dtype=np.int64) // 8,
                     np.arange(64, dtype=np.int64) % 8), axis=1)
    split = color_model.head_sub_split(keys)
    assert np.array_equal(
        split, (geometry.site_hash(keys[:, 1], keys[:, 2]) & 2) == 0)
    assert 0 < int(split.sum()) < split.size


def _head_case(n_fit: int, n_val: int
               ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: list[tuple[int, int, int]] = []
    states: list[int] = []
    slot = 0
    for state in range(7):
        for _ in range(n_fit):
            rows.append((0, 0, 4 * slot))
            states.append(state)
            slot += 1
        for _ in range(n_val):
            rows.append((0, 0, 4 * slot + 2))
            states.append(state)
            slot += 1
    keys = np.asarray(rows, np.int64)
    labels = np.asarray(states, np.int64)
    onehot = np.zeros((labels.size, 6), np.float64)
    for index, state in enumerate(labels):
        if state > 0:
            onehot[index, state - 1] = 1.0
    rng = np.random.default_rng(3)
    scores = 0.3 * onehot * 6.0 + rng.normal(0.0, 0.3, onehot.shape)
    return scores, labels, keys


@pytest.mark.parametrize(
    "n_fit,n_val,reason",
    [(10, 6, "adopted"),
     (9, 6, "search_class_starved"),
     (10, 2, "heldout_starved")])
def test_fit_cmy7_head_walks_its_support_floors(n_fit, n_val, reason):
    _h3_support.assert_measured(
        "cmy7 head floors",
        (color_model.HEAD_MIN_SEARCH_PER_STATE,
         color_model.HEAD_MIN_VALIDATION,
         color_model.HEAD_MIN_VALIDATION_PER_STATE,
         color_model.HEAD_N_OFFSETS),
        (10, 40, 3, 6))
    scores, states, keys = _head_case(n_fit, n_val)
    head, actual = color_model.fit_cmy7_head(scores, states, keys)
    assert actual == reason
    assert (head is None) is (reason != "adopted")
    if head is not None:
        assert color_model.HEAD_SCALE_MIN <= head.scale <= (
            color_model.HEAD_SCALE_MAX)
        assert head.offsets.shape == (6,)
        assert np.array_equal(head.apply(scores),
                              head.scale * scores + head.offsets)


def test_reference_states_place_word_and_dust_states_by_the_format(
        cmy8_row, cmy8_geometry):
    cells = _page_cells(cmy8_row)
    states, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    known = states >= 0
    assert int(known.sum()) == cmy8_row.tiles_per_page * cmy8_row.n_sites
    empty = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, np.zeros((0, 2), np.int64))
    assert empty[0].size == 0 and empty[1].size == 0
    assert int(np.count_nonzero(kinds == 0)) == (
        cmy8_row.tiles_per_page * pilots.N_WORD_SITES)
    assert int(np.count_nonzero(kinds == 1)) == (
        cmy8_row.tiles_per_page * cmy8_row.n_dust)
    assert np.array_equal(known, kinds >= 0)
    assert set(np.unique(states[kinds == 0]).tolist()) == set(
        cmy8_row.word_states)
    assert set(np.unique(states[kinds == 1]).tolist()) <= set(
        cmy8_row.dust_base_cycle)
    counter = cmy8_row.tile_counter(0, 1, 1)
    word_cells = cmy8_geometry.word_cells_yx + np.asarray((64, 64))
    flat = {tuple(cell): index for index, cell in enumerate(cells.tolist())}
    rows = np.asarray([flat[tuple(cell)] for cell in word_cells.tolist()])
    assert np.array_equal(
        states[rows],
        pilots.color_word_states(
            cmy8_row.seed, (counter,), cmy8_row)[0].astype(np.int8))


@pytest.fixture(scope="module")
def cmy8_states(cmy8_row, cmy8_geometry) -> tuple[np.ndarray, np.ndarray,
                                                   np.ndarray]:
    cells = _page_cells(cmy8_row)
    states, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    rng = np.random.default_rng(RASTER_NOISE_SEED)
    full = np.where(states >= 0, states,
                    rng.integers(0, 8, states.size)).astype(np.uint8)
    return cells, states, full


def _window_rows(cmy8_row, cmy8_geometry, cells, states, kinds
                 ) -> data.WindowRows:
    known = states >= 0
    bits = tile_codec.states_to_planes(
        np.maximum(states, 0).astype(np.uint8))
    return data.WindowRows(
        patch_ordinal=0, window_id=("cap", 0, 0, (0, 0) + cmy8_row.cells_yx),
        page=0, local_cells_yx=cells, page_cells_yx=cells,
        scan_points_yx=cells.astype(np.float64), states=states,
        furniture_kind=kinds, known_component_bits=bits.astype(np.uint8),
        known_component_mask=np.repeat(known[:, None], 3, axis=1),
        heldout_logloss=None)


def test_owner_selection_is_invariant_under_window_permutation(
        cmy8_row, cmy8_geometry, cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    half = cells.shape[0] // 2
    first = _window_rows(cmy8_row, cmy8_geometry, cells[:half],
                         states[:half], kinds[:half])
    second = data.WindowRows(
        **{**_window_rows(cmy8_row, cmy8_geometry, cells[half:],
                          states[half:], kinds[half:]).__dict__,
           "patch_ordinal": 1})
    forward = region_head.owner_selection((first, second))
    backward = region_head.owner_selection((second, first))
    assert np.array_equal(forward.keys, backward.keys)
    assert np.array_equal(forward.states, backward.states)
    assert np.array_equal(forward.kinds, backward.kinds)
    assert np.array_equal(forward.search, backward.search)


def test_owner_selection_gives_a_shared_cell_to_the_lower_ordinal(
        cmy8_row, cmy8_geometry, cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells, states, kinds)
    later = data.WindowRows(**{**rows.__dict__, "patch_ordinal": 5})
    selection = region_head.owner_selection((later, rows))
    assert set(selection.window_ordinals.tolist()) == {1}
    assert selection.keys.shape[0] == int((states >= 0).sum())
    assert np.array_equal(selection.keys[:, 0],
                          np.zeros(selection.keys.shape[0], np.int64))


def test_the_fit_split_gives_every_populated_state_both_sides(
        cmy8_row, cmy8_geometry, cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    selection = region_head.owner_selection(
        (_window_rows(cmy8_row, cmy8_geometry, cells, states, kinds),))
    for state in np.unique(selection.states):
        rows = selection.states == state
        assert int(np.count_nonzero(rows & selection.search)) >= 1
        assert int(np.count_nonzero(rows & ~selection.search)) >= 1


def _clean_features(states: np.ndarray, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    bits = tile_codec.states_to_planes(
        np.maximum(states, 0).astype(np.uint8))
    return 0.9 - 0.6 * bits.astype(np.float64) + rng.normal(
        0.0, 0.02, bits.shape)


def test_fit_detector_accepts_a_clean_colour_window(cmy8_row, cmy8_geometry,
                                                     cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells, states, kinds)
    selection = region_head.owner_selection((rows,))
    features = _clean_features(states)
    fitted, reason = region_head.fit_detector(
        cmy8_row.family, selection, (features,))
    assert reason == ""
    assert fitted is not None
    assert fitted.detector is not None
    assert fitted.detector.supported_planes == (True, True, True)
    assert fitted.heldout_loss == pytest.approx(0.0, abs=1e-6)
    assert fitted.word_heldout_loss == pytest.approx(0.0, abs=1e-6)
    assert fitted.dust_heldout_loss == pytest.approx(0.0, abs=1e-6)
    assert fitted.heldout_scores is None


def test_fit_detector_refuses_an_empty_or_state_starved_window(
        cmy8_row, cmy8_geometry, cmy8_states):
    empty = region_head.OwnerSelection(
        np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64),
        np.zeros(0, np.int8), np.zeros((0, 3), np.int64),
        np.zeros(0, bool))
    assert region_head.fit_detector(cmy8_row.family, empty, ()) == (
        None, "no_known_furniture")
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    blinded = np.where(states == 5, np.int8(-1), states)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells, blinded, kinds)
    selection = region_head.owner_selection((rows,))
    fitted, reason = region_head.fit_detector(
        cmy8_row.family, selection, (_clean_features(blinded),))
    assert fitted is None
    assert reason == "search_split_missing_state"


def test_improves_needs_a_strict_gain_that_costs_no_furniture_leg():
    def fit(loss: float, word: float, dust: float) -> region_head.DetectorFit:
        return region_head.DetectorFit(
            model=None, detector=None, heldout_loss=loss,
            word_heldout_loss=word, dust_heldout_loss=dust,
            heldout_scores=None, heldout_states=None, heldout_keys=None)

    _h3_support.assert_measured("STACK_GATE_SLACK",
                               region_head.STACK_GATE_SLACK, 1e-9)
    assert region_head.improves(fit(1.0, 1.0, 1.0), None) is True
    assert region_head.improves(fit(0.5, 1.0, 1.0),
                                 fit(1.0, 1.0, 1.0)) is True
    assert region_head.improves(fit(1.0, 1.0, 1.0),
                                 fit(1.0, 1.0, 1.0)) is False
    assert region_head.improves(fit(0.5, 1.5, 1.0),
                                 fit(1.0, 1.0, 1.0)) is False
    assert region_head.improves(fit(0.5, 1.0, 1.5),
                                 fit(1.0, 1.0, 1.0)) is False


def test_cargo_masks_select_exactly_the_payload_cells(cmy8_row,
                                                       cmy8_geometry):
    cells = _page_cells(cmy8_row)
    mask = color_region.cargo_site_mask(cmy8_geometry)
    assert int(mask.sum()) == cmy8_row.payload_cells
    indices = color_sites.cargo_row_indices(cmy8_geometry, cells)
    assert indices.size == cmy8_row.tiles_per_page * cmy8_row.payload_cells
    states, _kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    assert (states[indices] < 0).all()


def test_suppression_and_emission_track_the_fully_certified_tiles(
        cmy8_row, cmy8_geometry):
    cells = _page_cells(cmy8_row)
    certificates: dict = {}
    assert color_region.suppressed_tile_codes(
        cmy8_row, certificates, 0).size == 0
    for stream in cmy8_row.streams:
        certificates[(0, 1, 0, stream.stream_id)] = data.Certificate(
            0, 1, 0, stream.stream_id, np.zeros(4, np.uint8), "s")
    certificates[(0, 0, 1, "C")] = data.Certificate(
        0, 0, 1, "C", np.zeros(4, np.uint8), "s")
    suppressed = color_region.suppressed_tile_codes(
        cmy8_row, certificates, 0)
    assert suppressed.tolist() == [1 * cmy8_row.tiles_yx[1] + 0]
    emit = color_region.emission_mask(cmy8_row, cells, suppressed)
    assert int((~emit).sum()) == 64 * 64
    assert not emit[(cells[:, 0] // 64 == 1) & (cells[:, 1] // 64 == 0)].any()


def test_certified_projection_reproduces_the_printed_colour_field(
        cmy8_row, cmy8_geometry):
    rng = np.random.default_rng(3)
    certificates = {}
    for stream in cmy8_row.streams:
        certificates[(0, 1, 1, stream.stream_id)] = data.Certificate(
            0, 1, 1, stream.stream_id,
            rng.integers(0, 2, size=stream.user_bits, dtype=np.uint8), "t")
    projection = color_region.certified_projection(
        cmy8_row, cmy8_geometry, 0, 1, 1, certificates)
    assert projection is not None
    bits, known = projection
    assert bits.shape == (64, 64, 3)
    assert bool(known.all())
    counter = cmy8_row.tile_counter(0, 1, 1)
    word = cmy8_geometry.word_cells_yx
    assert np.array_equal(
        bits[word[:, 0], word[:, 1]],
        tile_codec.states_to_planes(
            pilots.color_word_states(cmy8_row.seed, (counter,), cmy8_row)[0]))
    assert color_region.certified_projection(
        cmy8_row, cmy8_geometry, 0, 0, 0, certificates) is None


def test_build_window_rows_resolves_certified_cargo_into_states(
        cmy8_row, cmy8_geometry):
    rng = np.random.default_rng(31)
    certificates = {}
    for stream in cmy8_row.streams:
        certificates[(0, 1, 1, stream.stream_id)] = data.Certificate(
            0, 1, 1, stream.stream_id,
            rng.integers(0, 2, size=stream.user_bits, dtype=np.uint8), "t")
    cells = _page_cells(cmy8_row)
    window = _region_window(cmy8_row, cells)
    rows = color_region.build_window_rows(
        cmy8_row, cmy8_geometry, window, certificates, {})
    in_tile = (cells[:, 0] // 64 == 1) & (cells[:, 1] // 64 == 1)
    assert (rows.states[in_tile] >= 0).all()
    assert bool(rows.known_component_mask[in_tile].all())
    other = (cells[:, 0] // 64 == 0) & (cells[:, 1] // 64 == 0)
    assert int((rows.states[other] >= 0).sum()) == cmy8_row.n_sites
    labels = color_region.build_label_rows(cmy8_row, cmy8_geometry, window)
    assert labels is not None
    assert labels.states.size == (
        cmy8_row.tiles_per_page * cmy8_row.n_sites)
    assert (labels.furniture_kind >= 0).all()
    assert bool(labels.known_component_mask.all())


def _region_window(row, cells: np.ndarray) -> color_region.RegionWindow:
    """The whole page as one window, composed BY PRODUCTION.

    This helper hand-built its own pose until 2026-08-31 and dropped the
    half cell `color_region.region_window` composes, which aimed every
    sample at a cell CORNER; its 75 tests passed either way because they
    assert structure and counts rather than cell accuracy, so the defect
    was latent here for as long as it existed.  Now nothing here spells
    a pose: the geometry is a `Placement` and production composes it.
    """
    height, width = row.cells_yx
    placement = _h3_fixture_geometry.window_placement(
        ("cap", 0, 0, (0, 0, height, width)),
        _h3_fixture_geometry.page_native_affine(RASTER_PPC, RASTER_MARGIN_PX),
        cells)
    return _h3_fixture_geometry.window_pose(row, placement)


def _printed_planes(row, full_states: np.ndarray, tmp_path: Path) -> tuple:
    height, width = row.cells_yx
    bits = tile_codec.states_to_planes(full_states).reshape(
        height, width, 3)
    side_y = height * RASTER_PPC + 2 * RASTER_MARGIN_PX
    side_x = width * RASTER_PPC + 2 * RASTER_MARGIN_PX
    image = np.full((side_y, side_x, 3), RASTER_PAPER, np.uint8)
    block = np.kron(
        np.where(bits, RASTER_INK, RASTER_PAPER).astype(
            np.uint8).transpose(2, 0, 1),
        np.ones((RASTER_PPC, RASTER_PPC), np.uint8)).transpose(1, 2, 0)
    image[RASTER_MARGIN_PX:RASTER_MARGIN_PX + height * RASTER_PPC,
          RASTER_MARGIN_PX:RASTER_MARGIN_PX + width * RASTER_PPC] = block
    rng = np.random.default_rng(RASTER_NOISE_SEED)
    image = np.clip(
        image.astype(np.int16) + rng.normal(0.0, 2.0, image.shape).astype(
            np.int16), 0, 255).astype(np.uint8)
    planes = []
    for index, name in enumerate("rgb"):
        path = tmp_path / f"{name}.npy"
        np.save(path, image[..., index])
        planes.append(data.PlaneRaster("cap", 0, name, path,
                                       image.shape[:2]))
    return tuple(planes)


#: ONE PRINTED PAGE AND ONE HEAD FOR THE MODULE, 2026-09-05: five tests
#: re-rendered the identical raster and two ran a whole extra region job
#: just to obtain the head they apply.  Same seed, same states, same
#: composer: every byte-level read below gets the raster it built itself.
@pytest.fixture(scope="module")
def printed_page(cmy8_row, cmy8_states, tmp_path_factory) -> tuple:
    _cells, _states, full = cmy8_states
    return _printed_planes(cmy8_row, full,
                           tmp_path_factory.mktemp("h3-color-page"))


@pytest.fixture(scope="module")
def standing_head(cmy8_row, cmy8_geometry, cmy8_states, printed_page):
    cells, _states, _full = cmy8_states
    window = _region_window(cmy8_row, cells)
    return _standing_head(cmy8_row, cmy8_geometry, window, printed_page)


def test_region_job_reads_a_synthetic_printed_colour_page(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page):
    cells, _states, full = cmy8_states
    window = _region_window(cmy8_row, cells)
    result = color_region.region_job(
        cmy8_row, cmy8_geometry, (window,), (), printed_page, {},
        region_head.StackConfig(), "cap", 0)
    evidence = [fact for fact in result.facts
                if isinstance(fact, data.ColorEvidenceRow)]
    lane_fits = [fact for fact in result.facts
                 if isinstance(fact, region_head.ColorLaneFit)]
    assert len(result.facts) == 2 and len(evidence) == 1, (
        "the colour region job publishes evidence rows, the lane fit "
        "record its own pricing reads, and — where the lane pools — its "
        "context population: its adopted/refusal report stays the "
        "CalibrateAdopted event")
    assert len(lane_fits) == 1
    assert lane_fits[0].head_fitted is True
    assert lane_fits[0].head is not None
    assert lane_fits[0].assembled == (window.patch_ordinal,)
    row = evidence[0]
    assert row.capture_id == "cap" and row.page == 0
    assert row.values.shape == (cells.shape[0], 3)
    order = {tuple(cell): index
             for index, cell in enumerate(cells.tolist())}
    selected = np.asarray([order[tuple(cell)]
                           for cell in row.page_cells_yx.tolist()])
    truth = tile_codec.states_to_planes(full)[selected]
    hard = (row.values > 0.0).astype(np.uint8)
    assert float((hard == truth).mean()) == 1.0
    assert len(result.events) == 1
    assert result.events[0].adopted is True
    assert result.events[0].reason == "accepted"


def test_region_job_prunes_a_page_whose_tiles_are_all_certified(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page):
    cells, _states, _full = cmy8_states
    window = _region_window(cmy8_row, cells)
    certificates = {}
    for ty in range(cmy8_row.tiles_yx[0]):
        for tx in range(cmy8_row.tiles_yx[1]):
            for stream in cmy8_row.streams:
                certificates[(0, ty, tx, stream.stream_id)] = (
                    data.Certificate(0, ty, tx, stream.stream_id,
                                     np.zeros(4, np.uint8), "s"))
    result = color_region.region_job(
        cmy8_row, cmy8_geometry, (window,), (), printed_page, certificates,
        region_head.StackConfig(), "cap", 0)
    assert len(result.facts) == 1
    pruned = result.facts[0]
    assert isinstance(pruned, region_head.ColorLaneFit)
    assert pruned.assembled == (window.patch_ordinal,)
    assert pruned.head_fitted is False and pruned.head is None, (
        "a pruned page returns before the fit: it clears the window's "
        "assembly debt without paying a head fit into the re-fit ordinal")
    assert len(result.events) == 1
    assert result.events[0].reason == "fully_certified_pruned"


def _standing_head(cmy8_row, cmy8_geometry, window, planes):
    result = color_region.region_job(
        cmy8_row, cmy8_geometry, (window,), (), planes, {},
        region_head.StackConfig(), "cap", 0)
    lane_fit = next(fact for fact in result.facts
                    if isinstance(fact, region_head.ColorLaneFit))
    return lane_fit.head


def test_the_assembly_job_reads_the_page_with_the_standing_head(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page, standing_head,
        monkeypatch):
    cells, _states, full = cmy8_states
    window = _region_window(cmy8_row, cells)
    assert standing_head is not None
    monkeypatch.setattr(
        region_head, "fit_detector",
        lambda *args, **kwargs: pytest.fail(
            "an assembly fire must not fit anything"))
    late = dataclasses.replace(window, patch_ordinal=4)
    result = color_region.assembly_job(
        cmy8_row, cmy8_geometry, standing_head, (late,), printed_page, {},
        "cap", 0)
    evidence = [fact for fact in result.facts
                if isinstance(fact, data.ColorEvidenceRow)]
    assert len(evidence) == 1 and len(result.facts) == 2
    row = evidence[0]
    assert row.patch_ordinal == 4
    order = {tuple(cell): index
             for index, cell in enumerate(cells.tolist())}
    selected = np.asarray([order[tuple(cell)]
                           for cell in row.page_cells_yx.tolist()])
    truth = tile_codec.states_to_planes(full)[selected]
    hard = (row.values > 0.0).astype(np.uint8)
    assert float((hard == truth).mean()) == 1.0, (
        "applying the standing head reads the printed page as well as the "
        "fire that fitted it — this is first evidence, not a compromise")
    lane_fit = result.facts[-1]
    assert isinstance(lane_fit, region_head.ColorLaneFit)
    assert lane_fit.assembled == (4,)
    assert lane_fit.head_fitted is False and lane_fit.head is None
    assert result.events[0].reason == "assembled"


def test_the_lane_assembles_its_debt_and_refits_only_once_settled(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page, standing_head,
        monkeypatch):
    cells, _states, _full = cmy8_states
    window = _region_window(cmy8_row, cells)
    wids = (window.window_id,)
    monkeypatch.setattr(color_region, "region_window",
                        lambda store, wid: window)
    store = SimpleNamespace(
        row=cmy8_row, geometry=cmy8_geometry,
        lane_page_windows=lambda *lane: wids,
        rgb_planes=lambda lane: printed_page,
        certificates=lambda: {},
        page_plane_fields=lambda page: None,
        # no field stands on this page, so no head on it owes a refit
        # and the assembly stage is reachable (W8 R-D, `refit_owed`)
        field_revision=lambda page: 0,
        pooled_ctx_enabled=lambda: False,
        captures=lambda: ("cap",),
        color_lane_head=lambda lane: store.standing,
        color_lane_debt=lambda lane: store.debt)

    def lane_fit_of(stage: str) -> region_head.ColorLaneFit:
        job = color_region.prepare_color(store, COLOR_LANE, stage)
        return next(fact for fact in job().facts
                    if isinstance(fact, region_head.ColorLaneFit))

    store.standing, store.debt = None, wids
    assert lane_fit_of(color_region.STAGE_COLOR).head_fitted is True, (
        "the lane's very first fire has no head to apply: it fits one, "
        "and that fit is ordinal 1")
    store.standing, store.debt = standing_head, wids
    assert lane_fit_of(color_region.STAGE_COLOR).head_fitted is False, (
        "a debt fire with a head standing applies it")
    store.standing, store.debt = standing_head, ()
    assert lane_fit_of(color_region.STAGE_COLOR_REFIT).head_fitted is True


def test_anchor_pose_points_are_the_affine_applied_to_local_cells():
    affine = (6.0, 0.1, 30.0, -0.2, 6.05, 40.0)
    cells = np.asarray([[0, 0], [1, 0], [0, 1], [7, 9]], np.int64)
    points = anchor.pose_points(affine, cells)
    linear = anchor.pose_linear(affine)
    assert np.array_equal(linear, np.asarray(((6.0, 0.1), (-0.2, 6.05))))
    assert np.array_equal(
        points, cells @ linear.T + np.asarray((30.0, 40.0)))
    corners = anchor.window_points((10, 12), affine)
    assert corners.shape == (4, 2)
    assert corners[:, 0].min() < points[:, 0].min()
    assert corners[:, 0].max() > points[:, 0].max()
    assert anchor.window_halo(6.0) == 12
    assert anchor.points_halo(6.0) == 7


def test_native_crop_clamps_to_the_plane_and_keeps_three_channels():
    planes = tuple(np.arange(100 * 120, dtype=np.uint8).reshape(100, 120)
                   for _ in range(3))
    y0, x0, raw = anchor.native_crop(
        planes, np.asarray([[-50.0, -50.0], [500.0, 500.0]]), 4)
    assert (y0, x0) == (0, 0)
    assert raw.shape == (100, 120, 3)
    y0, x0, raw = anchor.native_crop(
        planes, np.asarray([[40.0, 50.0], [60.0, 70.0]]), 4)
    assert (y0, x0) == (36, 46)
    assert raw.shape == (28, 28, 3)


@pytest.mark.parametrize(
    "dtype,ink,paper,expected",
    [(np.uint8, 60, 240, 255.0),
     (np.uint16, 4000, 60000, 255.0),
     (np.float32, 0.24, 0.94, 1.0)])
def test_the_streamed_divisor_matches_the_materialised_crop_maxima(
        dtype, ink, paper, expected):
    planes = tuple(np.full((80, 90), paper, dtype) for _ in range(3))
    for index, plane in enumerate(planes):
        plane[10 + index:40, 12:50] = ink
    points = (
        np.asarray([[8.0, 9.0], [30.0, 44.0]]),
        np.asarray([[41.0, 51.0], [70.0, 80.0]]),
        np.asarray([[-400.0, -400.0], [-300.0, -300.0]]),
    )
    crops = {
        ordinal: anchor.native_crop(planes, window, 4)
        for ordinal, window in enumerate(points)
    }
    materialised = (
        255.0
        if max(float(np.max(raw)) if raw.size else 0.0
               for _y0, _x0, raw in crops.values()) > 1.5
        else 1.0
    )
    streamed = anchor.native_divisor(tuple(
        anchor.crop_maximum(planes, window, 4) for window in points))
    assert crops[2][2].size == 0
    assert anchor.crop_maximum(planes, points[2], 4) == 0.0
    assert streamed == materialised == expected


def test_the_region_job_never_holds_two_native_crops_at_once(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page, monkeypatch):
    cells, _states, _full = cmy8_states
    window = _region_window(cmy8_row, cells)
    windows = (window, dataclasses.replace(window, patch_ordinal=1))
    native_crop = anchor.native_crop
    live: list[weakref.ref] = []
    peak = 0

    def counting(planes_, points_yx, halo):
        nonlocal peak
        crop = native_crop(planes_, points_yx, halo)
        live[:] = [ref for ref in live if ref() is not None]
        live.append(weakref.ref(crop[2]))
        peak = max(peak, len(live))
        return crop

    monkeypatch.setattr(anchor, "native_crop", counting)
    result = color_region.region_job(
        cmy8_row, cmy8_geometry, windows, (), printed_page, {},
        region_head.StackConfig(), "cap", 0)
    assert result.events[0].adopted is True
    assert all(isinstance(fact, (data.ColorEvidenceRow,
                                 region_head.ColorLaneFit))
               for fact in result.facts)
    assert peak == 1


def test_features_at_reads_one_page_delta_the_same_at_every_rotation(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page):
    """Bar B1 at the unit level, on the read side.

    A registration delta is the PRINTER's and is written along the page
    axes.  The same delta, applied to the same page cells through four
    windows placed at rot 0, 1, 2 and 3, must read the same pixels — it
    is one fact about one sheet.  Applying it through the window's LOCAL
    2x2 instead, which is what every consumer did before the mapping
    existed, reads somewhere else entirely at rot 1, 2 and 3, and the
    second half of this test is that difference.
    """
    cells, _states, _full = cmy8_states
    height, width = cmy8_row.cells_yx
    planes = tuple(plane.open() for plane in printed_page)
    cell_dots = color_region.cell_dots_of(cmy8_row)
    page_delta = np.tile((0.7, -0.35), (cells.shape[0], 1))
    at_rotation: dict[int, np.ndarray] = {}
    through_the_pose: dict[int, np.ndarray] = {}
    for rot_k in (0, 1, 2, 3):
        placement = _h3_fixture_geometry.window_placement(
            ("cap", 0, 0, (0, 0, height, width)),
            _h3_fixture_geometry.page_native_affine(RASTER_PPC,
                                                    RASTER_MARGIN_PX),
            cells, rot_k=rot_k)
        window = _h3_fixture_geometry.window_pose(cmy8_row, placement)
        rows = color_region.build_window_rows(
            cmy8_row, cmy8_geometry, window, {}, {})
        order = np.lexsort((rows.page_cells_yx[:, 1],
                            rows.page_cells_yx[:, 0]))
        offsets = (page_delta[:rows.page_cells_yx.shape[0]], None,
                   page_delta[:rows.page_cells_yx.shape[0]])
        read = anchor.features_at(planes, rows, window.page_linear, offsets,
                                  cell_dots, float(RASTER_PPC), 255.0)
        at_rotation[rot_k] = read[order]
        local = anchor.features_at(
            planes, rows, anchor.pose_linear(window.affine), offsets,
            cell_dots, float(RASTER_PPC), 255.0)
        through_the_pose[rot_k] = local[order]
    for rot_k in (1, 2, 3):
        assert np.allclose(at_rotation[rot_k], at_rotation[0]), rot_k
    for rot_k in (1, 2, 3):
        assert not np.allclose(through_the_pose[rot_k], at_rotation[0]), (
            f"rot {rot_k} through the LOCAL 2x2 must land elsewhere; a "
            "test that cannot tell the two apart pins nothing")
    assert np.allclose(through_the_pose[0], at_rotation[0])


def test_features_at_refuses_a_window_whose_offset_leaves_the_raster(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page):
    """One None collapses the region's corrected arm, by design."""
    cells, _states, _full = cmy8_states
    window = _region_window(cmy8_row, cells)
    rows = color_region.build_window_rows(
        cmy8_row, cmy8_geometry, window, {}, {})
    planes = tuple(plane.open() for plane in printed_page)
    cell_dots = color_region.cell_dots_of(cmy8_row)
    far = np.tile((0.0, -10_000.0), (rows.page_cells_yx.shape[0], 1))
    assert anchor.features_at(
        planes, rows, window.page_linear, (far, None, None), cell_dots,
        float(RASTER_PPC), 255.0) is None
    near = np.zeros_like(far)
    assert anchor.features_at(
        planes, rows, window.page_linear, (near, None, None), cell_dots,
        float(RASTER_PPC), 255.0) is not None


def test_a_window_with_no_correction_reads_at_the_pose_and_keeps_the_arm(
        cmy8_row, cmy8_geometry, cmy8_states, printed_page):
    """The two answers a seam can give, and why they are not the same.

    ADDED 2026-09-08 (the W3a review's finding 1).  `row_offsets` has
    two ways to say "nothing to apply here" and they mean different
    things: a tuple of per-plane Nones is THIS WINDOW read at its own
    pose, and the region keeps a corrected arm built from whatever the
    other windows contributed; the bare `None` is the PAGE saying no
    plane is solved anywhere, and it takes the whole region's second arm
    with it.  A seam that confused them — `swim.offsets_builder` did —
    silently discarded every fitted window's correction the moment one
    covering window failed to fit on a page with no field yet.
    """
    cells, _states, _full = cmy8_states
    window = _region_window(cmy8_row, cells)
    rows = color_region.build_window_rows(
        cmy8_row, cmy8_geometry, window, {}, {})

    def inputs_with(answer):
        return color_region.build_region_inputs(
            cmy8_row, cmy8_geometry, (window,), (), printed_page, {},
            "cap", 0, None, None, lambda _rows: answer)

    at_the_pose = inputs_with((None, None, None))
    assert at_the_pose.corrected is not None
    assert np.allclose(at_the_pose.corrected[0], at_the_pose.base_tuple[0]), (
        "a window with no correction must read exactly what the base arm "
        "reads, not a displaced approximation of it")
    assert inputs_with(None).corrected is None, (
        "the page-level None is the other answer and must keep meaning "
        "what it means: no corrected arm at all")
    shifted = np.tile((0.5, 0.0), (rows.page_cells_yx.shape[0], 1))
    moved = inputs_with((shifted, None, None))
    assert moved.corrected is not None
    assert not np.allclose(moved.corrected[0], moved.base_tuple[0]), (
        "a test that cannot tell a correction from its absence pins "
        "nothing")


def test_region_context_bins_share_one_bin_per_physical_cell(cmy8_row,
                                                              cmy8_geometry,
                                                              cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells, states, kinds)
    evidence = np.zeros((cells.shape[0], 3), np.float64)
    bins = ctx.region_context_bins((rows,), lambda _o: evidence, True)
    assert len(bins) == 1
    assert bins[0].shape == (cells.shape[0], 3)
    assert bins[0].dtype == np.int8
    assert int((bins[0] < 0).sum()) > 0
    assert int(bins[0].max()) <= 8


@pytest.mark.parametrize("non_increasing", (True, False))
def test_ordered_offsets_are_monotone_in_the_declared_direction(
        non_increasing):
    from holo.receiver.lib.pava import N_CONTEXT_BINS

    rng = np.random.default_rng(11)
    bins = rng.integers(0, N_CONTEXT_BINS, 400)
    labels = rng.random(400) < 0.5
    logits = np.where(labels, 1.0, -1.0) + 0.4 * bins
    offsets = ctx.ordered_offsets(logits, labels, np.ones(400), bins,
                                  non_increasing)
    assert offsets.shape == (N_CONTEXT_BINS,)
    differences = np.diff(offsets)
    if non_increasing:
        assert np.all(differences <= 1e-12)
    else:
        assert np.all(differences >= -1e-12)


def test_anchor_curve_centres_a_context_curve_on_its_own_weight():
    offsets = np.asarray([1.0, 2.0, 3.0] + [0.0] * 6)
    bins = np.asarray([0, 1, 2, 0], np.int64)
    weights = np.ones(4)
    centred = ctx.anchor_curve(offsets, bins, weights)
    assert float(np.sum(weights * centred[bins])) == pytest.approx(0.0)
    assert np.array_equal(ctx.anchor_curve(offsets, bins, np.zeros(4)),
                          offsets)


def test_label_floor_refusal_names_the_starved_side():
    config = ctx.ContextConfig()
    assert config.enabled is True
    assert ctx.ContextConfig(variant=ctx.CONTEXT_VARIANT_OFF).enabled is (
        False)
    search = np.zeros(200, bool)
    search[:100] = True
    assert ctx.label_floor_refusal(search, config) == ""
    thin_search = np.zeros(200, bool)
    thin_search[:10] = True
    assert ctx.label_floor_refusal(thin_search, config) == (
        ctx.REASON_SEARCH_STARVED)
    thin_validation = np.ones(120, bool)
    thin_validation[:10] = False
    assert ctx.label_floor_refusal(thin_validation, config) == (
        ctx.REASON_VALIDATION_STARVED)


def _lane_store(head_fits: int = 0, debt: tuple = (),
                head: object = None,
                field_revision: int = 0) -> SimpleNamespace:
    """The pricing bench: a lane's fit count, its assembly debt, and —
    since W8 — the head and the page fields the stage rule reads.

    `head` None is a lane that has never fitted; a head standing at
    revision 0 beside a page whose field revision is 0 is a lane that has
    fitted and owes no refit, which is the state the pricing assertions
    below are about (`color_region.refit_owed`).  The refit-debt
    behaviour itself is `test_h3_field_lifecycle`'s, over the real store.
    """
    return SimpleNamespace(
        color_lane_head_fits=lambda lane: head_fits,
        color_lane_debt=lambda lane: debt,
        color_lane_head=lambda lane: head,
        field_revision=lambda page: field_revision)


def test_the_colour_lane_prices_assembly_flat_and_refits_by_head_fits():
    cost = engine.DESCRIPTOR_BY_NAME["color"].cost
    assert cost(_lane_store(), COLOR_LANE, color_region.STAGE_COLOR,
                0, 0) == COLOR_ASSEMBLY_PRICE
    assert tuple(
        cost(_lane_store(head_fits=fits), COLOR_LANE,
             color_region.STAGE_COLOR_REFIT, 1, 0)
        for fits in (1, 2, 3)) == COLOR_REFIT_PRICES, (
        "a re-fit reads every label the region owns: the lane's nth head "
        "fit pays 160*n (ruling 2026-08-29 night)")
    assert cost(_lane_store(head_fits=2), COLOR_LANE_RUNG_1,
                color_region.STAGE_COLOR_REFIT,
                1, 0) == COLOR_REFIT_PRICES[1] + RUNG_PREMIUM
    assert cost(_lane_store(head_fits=0), COLOR_LANE,
                color_region.STAGE_COLOR_REFIT,
                9, 0) == COLOR_REFIT_PRICES[0], (
        "a lane that has never fitted still pays a full first re-fit — "
        "an unfitted ordinal must never price the work at zero")


def test_an_assembly_debt_wake_prices_as_assembly_even_with_rows_standing():
    descriptor = engine.DESCRIPTOR_BY_NAME["color"]
    standing = _h3_facts.lane_head()
    owed = _lane_store(head_fits=3, debt=(("cap", 0, 0, (0, 0, 8, 8)),),
                       head=standing)
    settled = _lane_store(head_fits=3, head=standing)
    assert descriptor.stage(owed, COLOR_LANE) == color_region.STAGE_COLOR
    assert descriptor.cost(owed, COLOR_LANE,
                           descriptor.stage(owed, COLOR_LANE),
                           7, 480) == COLOR_ASSEMBLY_PRICE, (
        "first work for a never-assembled window is assembly however "
        "many rows the lane already holds and however often it has "
        "fired: it belongs ahead of cold placement, not behind it")
    assert descriptor.stage(settled,
                            COLOR_LANE) == color_region.STAGE_COLOR_REFIT
    assert descriptor.cost(settled, COLOR_LANE,
                           color_region.STAGE_COLOR_REFIT,
                           7, 0) == COLOR_REFIT_PRICES[2]


def _lane_fold_store() -> SimpleNamespace:
    return SimpleNamespace(_color_lane_assembled={}, _color_lane_head={},
                           _color_lane_head_fits={},
                           _lane_page_wids={}, _placements={})


def _lane_fit(assembled: tuple, head_fitted: bool,
              standing: object = None) -> region_head.ColorLaneFit:
    return region_head.ColorLaneFit("cap", 0, 0, assembled, head_fitted,
                                    standing)


def test_the_refit_ordinal_counts_head_fits_and_never_plain_fires():
    store = _lane_fold_store()
    fold = engine._Engine._fold_color_lane_fit
    price = engine.DESCRIPTOR_BY_NAME["color"].cost
    reader = SimpleNamespace(
        color_lane_head_fits=lambda lane:
            engine._Engine.color_lane_head_fits(store, lane))
    fold(store, _lane_fit((0,), True))
    first = price(reader, COLOR_LANE, color_region.STAGE_COLOR_REFIT, 1, 0)
    fold(store, _lane_fit((1, 2), False))
    fold(store, _lane_fit((3,), False))
    between = price(reader, COLOR_LANE, color_region.STAGE_COLOR_REFIT,
                    3, 0)
    fold(store, _lane_fit((0, 1, 2, 3), True))
    after = price(reader, COLOR_LANE, color_region.STAGE_COLOR_REFIT, 4, 0)
    assert (first, between, after) == (COLOR_REFIT_PRICES[0],
                                       COLOR_REFIT_PRICES[0],
                                       COLOR_REFIT_PRICES[1]), (
        "two assembly fires between two re-fits leave the next re-fit's "
        "price exactly where the first re-fit left it")
    assert store._color_lane_head_fits[COLOR_LANE] == 2
    assert store._color_lane_assembled[COLOR_LANE] == {0, 1, 2, 3}


def test_only_a_fire_that_fitted_publishes_a_standing_head():
    store = _lane_fold_store()
    fold = engine._Engine._fold_color_lane_fit
    fold(store, _lane_fit((0,), True))
    assert engine._Engine.color_lane_head(store, COLOR_LANE) is None, (
        "a refused fit performed the work — it pays the ordinal — but "
        "leaves nothing standing to apply")
    standing = object()
    fold(store, _lane_fit((0,), True, standing))
    assert engine._Engine.color_lane_head(store, COLOR_LANE) is standing
    fold(store, _lane_fit((1,), False))
    assert engine._Engine.color_lane_head(store, COLOR_LANE) is standing, (
        "an assembly fire carries no head: it must not clear the one it "
        "just applied")


def test_assembly_debt_is_every_placed_window_no_fire_has_covered():
    store = _lane_fold_store()
    wids = tuple(("cap", 0, 0, (0, 0, 8, index + 8)) for index in range(3))
    store._lane_page_wids[COLOR_LANE] = set(wids)
    for ordinal, wid in enumerate(wids):
        store._placements[wid] = SimpleNamespace(patch_ordinal=ordinal)
    debt = engine._Engine.color_lane_debt
    assert debt(store, COLOR_LANE) == tuple(sorted(wids))
    engine._Engine._fold_color_lane_fit(store, _lane_fit((0, 2), False))
    assert debt(store, COLOR_LANE) == (wids[1],)
    engine._Engine._fold_color_lane_fit(store, _lane_fit((1,), False))
    assert debt(store, COLOR_LANE) == ()


def _context_population(n_rows: int, seed: int) -> object:
    from holo.receiver.lib.pava import N_CONTEXT_BINS

    rng = np.random.default_rng(seed)
    states = (np.arange(n_rows) % 2).astype(np.int64)
    scores = np.zeros((n_rows, 2), np.float64)
    scores[:, 1] = np.where(states == 1, 0.6, -0.6) + rng.normal(
        0.0, 1.0, n_rows)
    bins = rng.integers(0, N_CONTEXT_BINS, (n_rows, 3)).astype(np.int8)
    return ctx.Population(scores, states, bins, np.zeros(n_rows, np.int8))


def test_the_context_fit_reads_every_label_of_a_population_past_the_cap(
        monkeypatch):
    from holo.receiver.lib.pava import class_balanced_weights

    assert FULL_FIT_ROWS > RETIRED_LABEL_CAP
    search = _context_population(FULL_FIT_ROWS, 3)
    validation = _context_population(FULL_FIT_ROWS, 4)
    fitted: list[int] = []
    original = ctx.ordered_offsets

    def recording(logits, labels, weights, bins, non_increasing):
        fitted.append(int(logits.size))
        return original(logits, labels, weights, bins, non_increasing)

    monkeypatch.setattr(ctx, "ordered_offsets", recording)
    ctx._fit_one_curve(
        np.array(search.scores), np.array(validation.scores), [None, None],
        search, validation, class_balanced_weights(search.states),
        class_balanced_weights(validation.states), 1, 0, True,
        ctx.ContextConfig())
    assert fitted == [FULL_FIT_ROWS], (
        "the fit ran on a subsample: every label the region owns must reach "
        "the curve")


def test_fit_region_context_refuses_a_region_with_no_context_cells(
        cmy8_row, cmy8_geometry, cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    rows = _window_rows(cmy8_row, cmy8_geometry, cells, states, kinds)
    selection = region_head.owner_selection((rows,))
    features = selection.gather((_clean_features(states),))
    model = color_model.fit_qda(
        features[selection.search], selection.states[selection.search], 8)
    detector = color_model.fit_cmy8_detector(
        features[selection.search], selection.states[selection.search],
        features, selection.states)
    verdict = ctx.fit_region_context(
        model, detector, None, features,
        np.full((features.shape[0], 3), -1, np.int8), selection.states,
        selection.kinds, selection.search, ctx.ContextConfig())
    assert verdict.head is None
    assert verdict.adopted is False
    assert verdict.reason == ctx.REASON_NO_CELLS


def test_context_head_applies_one_offset_per_plane_bin():
    offsets = np.zeros((2, 3, 9), np.float64)
    offsets[0, 0, 4] = 1.0
    offsets[1, 2, 0] = -2.0
    head = ctx.ContextHead(offsets, np.ones((2, 3), bool))
    scores = np.zeros((3, 2), np.float64)
    bins = np.asarray([[4, 0, 0], [0, 0, 0], [-1, -1, -1]], np.int8)
    out = head.apply_states(scores, bins)
    assert out[0, 0] == 1.0
    assert out[1, 1] == -2.0
    assert np.array_equal(out[2], np.zeros(2))


def _color_labels(cmy8_row, cmy8_geometry, cells, states, kinds
                  ) -> color_refine.ColorLabels:
    rows = _window_rows(cmy8_row, cmy8_geometry, cells, states, kinds)
    return color_refine.collect_labels(
        0, rows.page_cells_yx, rows.furniture_kind,
        rows.known_component_bits, rows.known_component_mask)


def test_color_collect_labels_expands_furniture_into_three_plane_rows(
        cmy8_row, cmy8_geometry, cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    labels = _color_labels(cmy8_row, cmy8_geometry, cells, states, kinds)
    n_furniture = int((kinds >= 0).sum())
    assert int(labels.is_furniture.sum()) == 3 * n_furniture
    assert labels.row_indices.size == labels.planes.size
    assert set(labels.planes.tolist()) == {0, 1, 2}
    assert np.array_equal(
        labels.validation,
        color_refine.block_validation(0, labels.page_cells_yx))
    assert float(labels.weights[labels.train].sum()) > 0.0
    _h3_support.assert_measured("FURNITURE_LOSS_SLACK",
                               color_refine.FURNITURE_LOSS_SLACK, 1e-9)


def test_color_support_metrics_refuse_a_furniture_only_window(
        cmy8_row, cmy8_geometry, cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    labels = _color_labels(cmy8_row, cmy8_geometry, cells, states, kinds)
    supported, reason = color_refine.support_metrics(labels)
    assert supported is False
    assert reason == "insufficient_payload_train"


def test_color_select_pose_sites_keeps_furniture_and_caps_cargo(
        cmy8_row, cmy8_geometry, cmy8_states):
    cells, states, _full = cmy8_states
    _s, kinds = color_model.reference_states(
        cmy8_row, cmy8_geometry, 0, cells)
    labels = _color_labels(cmy8_row, cmy8_geometry, cells, states, kinds)
    train = color_refine.select_pose_sites(labels, validation=False)
    valid = color_refine.select_pose_sites(labels, validation=True)
    assert set(train.tolist()) & set(valid.tolist()) == set()
    assert labels.train[train].all()
    assert labels.validation[valid].all()
    assert np.array_equal(train, np.sort(train))
    assert np.array_equal(
        train, color_refine.select_pose_sites(labels, validation=False))


def test_window_pose_reads_the_linear_part_off_the_region_affine():
    affine = (6.0, 0.1, 30.0, -0.2, 6.05, 40.0)
    local_pose = color_refine.window_pose(affine)
    assert local_pose.origin_yx == (30.0, 40.0)
    assert np.array_equal(local_pose.matrix(),
                          np.asarray(((6.0, 0.1), (-0.2, 6.05))))
    assert local_pose.pitch_px == pytest.approx(
        0.5 * (float(np.hypot(6.0, -0.2)) + float(np.hypot(0.1, 6.05))))
    cells = np.asarray([[0, 0], [3, 4]], np.int64)
    assert np.array_equal(local_pose.points(cells),
                          anchor.pose_points(affine, cells))


def _placement(rot_k: int) -> data.Placement:
    shape = (48, 48)
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    return data.Placement(
        window_id=("cap", 3, 0, (100, 200, 148, 248)), capture_id="cap",
        level_index=3, region_index=0, patch_ordinal=17, page=0,
        rot_k=rot_k, page_origin_yx=(400, 300),
        native_affine=SHEARED_AFFINE, pitch_px=12.04, route="word",
        local_cells_yx=local.astype(np.int64))


@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
@pytest.mark.parametrize("scale", (Fraction(1), Fraction(3)))
def test_revised_native_affine_inverts_the_region_window_affine(rot_k,
                                                                scale):
    row = resolve_format_ref(CMY7_FOSSIL)
    placement = _placement(rot_k)
    placements = {placement.window_id: placement}
    levels = {("cap", 3): SimpleNamespace(scale=scale)}
    store = SimpleNamespace(
        placement=placements.get,
        level=lambda capture_id, level_index: levels[(capture_id,
                                                      level_index)],
        row=row)
    window = color_region.region_window(store, placement.window_id)
    recovered = color_refine.revised_native_affine(
        color_refine.window_pose(window.affine), rot_k,
        window.shape_yx_cells, placement.page_origin_yx, scale)
    drift = max(abs(a - b) for a, b in zip(recovered, SHEARED_AFFINE,
                                           strict=True))
    assert drift <= AFFINE_ULP_BAR_PX, (rot_k, scale, drift)


def test_a_half_cell_slip_survives_the_colour_affine_round_trip():
    row = resolve_format_ref(CMY7_FOSSIL)
    placement = _placement(0)
    placements = {placement.window_id: placement}
    levels = {("cap", 3): SimpleNamespace(scale=Fraction(1))}
    store = SimpleNamespace(
        placement=placements.get,
        level=lambda capture_id, level_index: levels[(capture_id,
                                                      level_index)],
        row=row)
    window = color_region.region_window(store, placement.window_id)
    base = color_refine.window_pose(window.affine)
    linear = base.matrix()
    slipped = color_refine.LocalPose(
        origin_yx=tuple(np.asarray(base.origin_yx, np.float64)
                        + linear @ np.full(2, 0.5)),
        jacobian_yx=base.jacobian_yx, phase_yx=base.phase_yx,
        pitch_px=base.pitch_px, angle_deg=base.angle_deg)
    recovered = color_refine.revised_native_affine(
        slipped, 0, window.shape_yx_cells, placement.page_origin_yx,
        Fraction(1))
    drift = max(abs(a - b) for a, b in zip(recovered, SHEARED_AFFINE,
                                           strict=True))
    assert drift == pytest.approx(HALF_CELL_SIGNATURE_PX, abs=0.05)


def test_reach_certified_lists_every_certified_stream_in_reach(
        cmy8_row):
    from holo.receiver.plugins import refine
    cells = np.asarray([[0, 0], [63, 63], [64, 0], [130, 5]], np.int64)
    certificates = {
        (0, 0, 0, "C"), (0, 0, 0, "M"), (0, 1, 0, "Y"),
        (0, 5, 5, "C"), (1, 0, 0, "C")}
    store = SimpleNamespace(
        row=cmy8_row, has_certificate=lambda key: key in certificates)
    reach = refine.reach_tiles(cells)
    assert color_refine.reach_certified(store, 0, reach) == (
        (0, 0, 0, "C"), (0, 0, 0, "M"), (0, 1, 0, "Y"))
    assert color_refine.reach_certified(store, 2, reach) == ()
