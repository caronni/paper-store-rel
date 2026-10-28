from __future__ import annotations

import dataclasses
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import ndimage

from holo3 import data
from holo3.format import keystream, pilots
from holo3.format.identity import build_site_geometry, resolve_format_ref
from holo3.lib import pava
from holo3.lib.geometry import TILE_CELLS, site_parity
from holo3.lib.owners import freeze_page_owners
from holo3.plugins import calibrate, refine
from holo3.tests import _h3_support

K_FOSSIL = "L:c3-r0550@2240x1536"

SAMPLE_AFFINE = (7.0, 0.02, 60.0, -0.03, 7.05, 50.0)
SAMPLE_PITCH_PX = 7.0
RASTER_SHAPE_PX = (600, 600)
RASTER_SEED = 2026

# D6.6 deleted refine.attempt_key and calibrate.window_stamp; the honest
# keys (evidence halves, pose_affine, region_pitch) replaced them and the
# certified-reach helpers below are what survives
NOT_PINNED_PENDING_D6 = ("refine.certified_reach", "calibrate.window_job")


def test_the_d6_deletion_notes_still_name_live_symbols():
    modules = {"refine": refine, "calibrate": calibrate}
    checks = _h3_support.Checks("D6.6 pending-deletion notes")
    for entry in NOT_PINNED_PENDING_D6:
        module_name, symbol = entry.split(".")
        checks.check(
            f"{entry} still exists",
            hasattr(modules[module_name], symbol),
            "D6.6 has landed and deleted it: retire the note and pin "
            "whatever replaced the symbol")
    checks.assert_clean()
    assert len(NOT_PINNED_PENDING_D6) == 2


@pytest.fixture(scope="module")
def k_row() -> object:
    return resolve_format_ref(K_FOSSIL)


@pytest.fixture(scope="module")
def k_geometry(k_row) -> object:
    return build_site_geometry(k_row)


@pytest.fixture(scope="module")
def lookup(k_geometry) -> calibrate.SiteLookup:
    return calibrate.build_site_lookup(k_geometry)


@pytest.fixture(scope="module")
def raster() -> np.ndarray:
    rng = np.random.default_rng(RASTER_SEED)
    return rng.normal(180.0, 40.0, size=RASTER_SHAPE_PX).astype(np.float32)


def test_build_site_lookup_labels_every_word_and_filler_cell(k_geometry,
                                                              lookup):
    assert lookup.kind.shape == (TILE_CELLS, TILE_CELLS)
    assert lookup.kind.flags.writeable is False
    assert lookup.index.flags.writeable is False
    word = k_geometry.word_cells_yx
    assert np.array_equal(lookup.kind[word[:, 0], word[:, 1]],
                          np.zeros(word.shape[0], np.int16))
    assert np.array_equal(lookup.index[word[:, 0], word[:, 1]],
                          np.arange(word.shape[0], dtype=np.int16))
    assert int(np.count_nonzero(lookup.kind == 0)) == pilots.N_WORD_SITES
    assert int(np.count_nonzero(lookup.kind == 1)) == (
        k_geometry.extra_cells_yx.shape[0])
    assert int(np.count_nonzero(lookup.kind < 0)) == (
        TILE_CELLS * TILE_CELLS - k_geometry.shorten_flat.size)


def _tile_cells(ty: int, tx: int) -> np.ndarray:
    grid = np.stack(np.meshgrid(np.arange(TILE_CELLS),
                                np.arange(TILE_CELLS), indexing="ij"),
                    axis=-1).reshape(-1, 2)
    return grid + np.asarray((ty * TILE_CELLS, tx * TILE_CELLS), np.int64)


def test_format_reference_values_reproduce_the_word_and_filler_field(
        k_row, k_geometry, lookup):
    page, ty, tx = 0, 2, 3
    cells = _tile_cells(ty, tx)
    values = calibrate.format_reference_values(k_row, lookup, page, cells)
    assert values.dtype == np.int8
    counter = k_row.tile_counter(page, ty, tx)
    word = pilots.word_values(k_row.seed, counter, pilots.PLANE_K)[0]
    word_cells = k_geometry.word_cells_yx
    flat = (word_cells[:, 0] * TILE_CELLS + word_cells[:, 1])
    assert np.array_equal(values[flat], word.astype(np.int8))
    extra = k_geometry.extra_cells_yx
    if extra.size:
        extra_flat = extra[:, 0] * TILE_CELLS + extra[:, 1]
        expected = keystream.bits(
            k_row.seed, keystream.DOMAIN_FILLER_VALUES, pilots.PLANE_K,
            page, cells[extra_flat, 0], cells[extra_flat, 1])
        assert np.array_equal(values[extra_flat], expected.astype(np.int8))
    assert int(np.count_nonzero(values >= 0)) == k_row.n_sites
    assert calibrate.format_reference_values(
        k_row, lookup, page, np.zeros((0, 2), np.int64)).size == 0


def test_format_reference_values_move_with_the_tile_address(k_row, lookup):
    here = calibrate.format_reference_values(
        k_row, lookup, 0, _tile_cells(2, 3))
    neighbour = calibrate.format_reference_values(
        k_row, lookup, 0, _tile_cells(2, 4))
    known = here >= 0
    assert np.array_equal(known, neighbour >= 0)
    assert not np.array_equal(here[known], neighbour[known])


def test_payload_cell_mask_is_the_complement_of_the_site_set(k_row, lookup,
                                                              k_geometry):
    cells = _tile_cells(1, 1)
    mask = calibrate.payload_cell_mask(lookup, cells)
    assert int(mask.sum()) == (TILE_CELLS * TILE_CELLS - k_row.n_sites)
    values = calibrate.format_reference_values(k_row, lookup, 0, cells)
    assert np.array_equal(mask, values < 0)


def _placement(rot_k: int, extent: tuple[int, int, int, int],
               local: np.ndarray,
               origin: tuple[int, int] = (128, 192)) -> data.Placement:
    return data.Placement(
        window_id=("cap", 0, 0, extent), capture_id="cap", level_index=0,
        region_index=0, patch_ordinal=0, page=0, rot_k=rot_k,
        page_origin_yx=origin, native_affine=SAMPLE_AFFINE,
        pitch_px=SAMPLE_PITCH_PX, route="word", local_cells_yx=local)


def test_window_page_cells_rotates_then_translates_then_clips(k_row):
    shape = (32, 32)
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    placement = _placement(1, (0, 0, 32, 32), local)
    cells = calibrate.window_page_cells(placement, shape, k_row.cells_yx)
    assert cells.shape == local.shape
    expected = np.stack(
        (shape[1] - 1 - local[:, 1], local[:, 0]), axis=1) + np.asarray(
            (128, 192), np.int64)
    assert np.array_equal(cells, expected)


def test_window_page_cells_drops_cells_that_fall_off_the_page(k_row):
    shape = (32, 32)
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    placement = _placement(0, (0, 0, 32, 32), local, origin=(-8, -8))
    cells = calibrate.window_page_cells(placement, shape, k_row.cells_yx)
    assert cells.shape[0] == 24 * 24
    assert cells.min() >= 0


def _sample_cells() -> np.ndarray:
    return np.stack(np.meshgrid(np.arange(20, 60), np.arange(30, 70),
                                indexing="ij"), axis=-1).reshape(-1, 2)


def test_window_crop_bounds_include_the_aperture_halo(raster):
    cells = _sample_cells()
    points = calibrate.scan_points_yx(SAMPLE_AFFINE, Fraction(1), cells)
    crop = calibrate.window_crop((raster,), points, RASTER_SHAPE_PX,
                                 SAMPLE_PITCH_PX)
    halo = int(np.ceil(calibrate.APERTURE_CELLS * SAMPLE_PITCH_PX)) + 2
    assert crop.y0 == max(0, int(np.floor(points[:, 0].min())) - halo)
    assert crop.x0 == max(0, int(np.floor(points[:, 1].min())) - halo)
    assert crop.y0 + crop.filtered.shape[0] <= RASTER_SHAPE_PX[0]
    assert crop.x0 + crop.filtered.shape[1] <= RASTER_SHAPE_PX[1]
    assert crop.filtered.dtype == np.float32
    assert calibrate._aperture_px(SAMPLE_PITCH_PX) == 5


def _naive_window_means(raster: np.ndarray, points: np.ndarray,
                        pitch_px: float) -> np.ndarray:
    y0, x0, y1, x1 = calibrate._crop_bounds(points, RASTER_SHAPE_PX,
                                            pitch_px)
    raw = calibrate.crop_luma((raster,), y0, y1, x0, x1)
    filtered = ndimage.uniform_filter(
        raw, size=calibrate._aperture_px(pitch_px), mode="nearest")
    return calibrate.sample_points(
        calibrate.WindowCrop(y0, x0, filtered, 0.0), points)


@pytest.mark.parametrize("n_cells", (1600, 64))
def test_sampled_window_means_equals_the_full_filter_derivation(raster,
                                                                 n_cells):
    cells = _sample_cells()[:n_cells]
    points = calibrate.scan_points_yx(SAMPLE_AFFINE, Fraction(1), cells)
    optimized = calibrate.sampled_window_means(
        (raster,), points, RASTER_SHAPE_PX, SAMPLE_PITCH_PX)
    assert np.array_equal(
        optimized, _naive_window_means(raster, points, SAMPLE_PITCH_PX))


def test_window_scores_are_ink_positive_around_the_median():
    means = np.asarray([10.0, 20.0, 200.0, 210.0], np.float32)
    scores = calibrate.window_scores(means)
    midpoint = np.float32(np.median(means))
    spread = np.float32(np.abs(means - midpoint).mean())
    assert np.array_equal(scores, (midpoint - means) / spread)
    assert (scores[:2] > 0.0).all()
    assert (scores[2:] < 0.0).all()
    flat = calibrate.window_scores(np.full(8, 42.0, np.float32))
    assert np.array_equal(flat, np.zeros(8, np.float32))


def test_points_inside_raster_is_a_closed_interval_test():
    assert calibrate.points_inside_raster(
        np.asarray([[0.0, 0.0], [99.0, 199.0]]), (100, 200)) is True
    assert calibrate.points_inside_raster(
        np.asarray([[0.0, 0.0], [99.5, 199.0]]), (100, 200)) is False
    assert calibrate.points_inside_raster(
        np.asarray([[-0.1, 0.0]]), (100, 200)) is False
    assert calibrate.points_inside_raster(
        np.zeros((0, 2)), (100, 200)) is True


def _calibration_case(n_search_per_class: int, n_heldout: int
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs: list[int] = []
    labels: list[int] = []
    for index in range(n_search_per_class * 2):
        xs.append(2 * index)
        labels.append(index % 2)
    for index in range(n_heldout):
        xs.append(2 * index + 1)
        labels.append(index % 2)
    cells = np.stack((np.zeros(len(xs), np.int64),
                      np.asarray(xs, np.int64)), axis=1)
    rng = np.random.default_rng(1)
    scores = (np.asarray(labels, np.float64) * 2.0 - 1.0
              + rng.normal(0.0, 0.1, len(xs)))
    return scores, np.asarray(labels, np.int8), cells


def test_the_calibration_split_is_the_site_parity():
    scores, labels, cells = _calibration_case(10, 10)
    parity = site_parity(cells[:, 0], cells[:, 1]).astype(bool)
    assert int(np.count_nonzero(~parity)) == 20
    assert int(np.count_nonzero(parity)) == 10


@pytest.mark.parametrize(
    "search_per_class,heldout,accepted,reason",
    [(10, 10, True, "accepted"),
     (9, 10, False, "search_class_starved"),
     (10, 9, False, "heldout_starved"),
     (9, 9, False, "search_class_starved"),
     (40, 40, True, "accepted")])
def test_fit_window_calibration_is_a_boundary_at_the_declared_floors(
        search_per_class, heldout, accepted, reason):
    _h3_support.assert_golden("CAL_MIN_PER_CLASS", pava.CAL_MIN_PER_CLASS,
                              10)
    _h3_support.assert_golden("CAL_MIN_HELDOUT", pava.CAL_MIN_HELDOUT, 10)
    scores, labels, cells = _calibration_case(search_per_class, heldout)
    fit = calibrate.fit_window_calibration(scores, labels, cells)
    assert fit.accepted is accepted
    assert fit.reason == reason
    if accepted:
        assert fit.n_search == search_per_class * 2
        assert fit.heldout_logloss is not None and fit.heldout_logloss > 0.0
        assert fit.marginal_llr.shape == scores.shape
        assert fit.knots.size > 0
    else:
        assert fit.n_search == 0
        assert fit.heldout_logloss is None
        assert fit.marginal_llr.size == 0


def test_fit_window_calibration_marginal_llr_is_the_pava_calibration():
    scores, labels, cells = _calibration_case(40, 40)
    fit = calibrate.fit_window_calibration(scores, labels, cells)
    parity = site_parity(cells[:, 0], cells[:, 1]).astype(bool)
    knots, probs = pava._pava_nodes(scores[~parity], labels[~parity])
    assert np.array_equal(fit.knots, knots)
    assert np.array_equal(fit.probs, probs)
    assert np.array_equal(
        fit.marginal_llr,
        np.asarray(pava.calibration_llr(scores, knots, probs), np.float32))
    assert float(np.mean((fit.marginal_llr > 0) == (labels > 0))) == 1.0


def _synthetic_window(k_row, k_geometry, lookup, raster
                      ) -> tuple[data.Placement, tuple[int, int]]:
    shape = (40, 40)
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    return _placement(0, (0, 0, 40, 40), local), shape


def test_calibrate_window_refuses_a_window_that_leaves_the_raster(
        k_row, k_geometry, lookup, raster):
    shape = (40, 40)
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    placement = data.Placement(
        window_id=("cap", 0, 0, (0, 0, 40, 40)), capture_id="cap",
        level_index=0, region_index=0, patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(0, 0),
        native_affine=(7.0, 0.0, 5000.0, 0.0, 7.0, 5000.0),
        pitch_px=SAMPLE_PITCH_PX, route="word", local_cells_yx=local)
    evidence = calibrate.calibrate_window(
        (raster,), placement, shape, k_row, lookup, SAMPLE_PITCH_PX,
        Fraction(1))
    assert evidence.accepted is False
    assert evidence.refusal_reason == "outside_raster"
    assert evidence.page_cells_yx.shape == (0, 2)


def _printed_window(k_row, k_geometry, lookup, page_origin: tuple[int, int],
                    shape: tuple[int, int]
                    ) -> tuple[data.Placement, np.ndarray]:
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    placement = _placement(0, (0, 0, shape[0], shape[1]), local,
                           origin=page_origin)
    cells = calibrate.window_page_cells(placement, shape, k_row.cells_yx)
    values = calibrate.format_reference_values(k_row, lookup, 0, cells)
    return placement, values


def test_calibrate_window_reads_a_synthetic_printed_window(
        k_row, k_geometry, lookup):
    shape = (48, 48)
    page_origin = (128, 192)
    placement, values = _printed_window(k_row, k_geometry, lookup,
                                        page_origin, shape)
    cells = calibrate.window_page_cells(placement, shape, k_row.cells_yx)
    rng = np.random.default_rng(808)
    printed = rng.integers(0, 2, size=cells.shape[0], dtype=np.uint8)
    known = values >= 0
    printed[known] = values[known].astype(np.uint8)
    points = calibrate.scan_points_yx(placement.native_affine, Fraction(1),
                                      cells)
    height = int(np.ceil(points[:, 0].max())) + 20
    width = int(np.ceil(points[:, 1].max())) + 20
    plane = np.full((height, width), 235.0, np.float32)
    for point, ink in zip(np.rint(points).astype(np.int64), printed,
                          strict=True):
        if ink:
            plane[point[0] - 2:point[0] + 3,
                  point[1] - 2:point[1] + 3] = 60.0
    evidence = calibrate.calibrate_window(
        (plane,), placement, shape, k_row, lookup, SAMPLE_PITCH_PX,
        Fraction(1))
    assert evidence.accepted is True
    assert evidence.refusal_reason == ""
    assert evidence.page_cells_yx.shape[0] == cells.shape[0]
    assert np.array_equal(evidence.reference_values, values)
    hard = (evidence.printed_llr > 0.0).astype(np.uint8)
    assert np.array_equal(hard[known], printed[known])
    assert evidence.heldout_logloss is not None
    assert evidence.ctx_adopted is False
    resampled = calibrate.resample_window(
        (plane,), placement, evidence, k_row, lookup, SAMPLE_PITCH_PX,
        Fraction(1))
    assert np.array_equal(resampled.scores, evidence.scores)
    assert np.array_equal(resampled.reference_values,
                          evidence.reference_values)


def test_context_neighbour_counts_are_the_eight_neighbour_ink_totals():
    cells = np.stack(np.meshgrid(np.arange(4), np.arange(4),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    ink = np.zeros(16, bool)
    ink[[0, 1, 2, 4, 6, 8, 9, 10]] = True
    counts, valid = calibrate.context_neighbour_counts(cells, ink)
    assert counts.dtype == np.int8
    interior = np.flatnonzero(valid)
    assert sorted(interior.tolist()) == [5, 6, 9, 10]
    assert int(counts[5]) == 8
    assert int(counts[10]) == 2
    assert not valid[0]


def test_context_neighbour_counts_refuse_a_window_with_a_repeated_cell():
    cells = np.asarray([[0, 0], [0, 0], [1, 1]], np.int64)
    with pytest.raises(ValueError) as excinfo:
        calibrate.context_neighbour_counts(cells, np.zeros(3, bool))
    assert "repeats a page cell" in str(excinfo.value)


def test_apply_context_offsets_is_additive_and_clamped():
    llr = np.asarray([0.0, 5.0, -5.0, 11.9], np.float64)
    bins = np.asarray([-1, 3, 3, 3], np.int8)
    offsets = np.zeros(pava.N_CONTEXT_BINS, np.float64)
    offsets[3] = 2.0
    out = calibrate.apply_context_offsets(llr, bins, offsets)
    assert out[0] == 0.0
    assert out[1] == 7.0
    assert out[2] == -3.0
    assert out[3] == pava.CTX_LLR_CLAMP
    _h3_support.assert_golden("CTX_LLR_CLAMP", pava.CTX_LLR_CLAMP, 12.0)
    _h3_support.assert_golden("N_CONTEXT_BINS", pava.N_CONTEXT_BINS, 9)


def _context_side(n_false: int, seed: int, n_true: int | None = None
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray,
                             np.ndarray]:
    rng = np.random.default_rng(seed)
    labels = np.concatenate((
        np.zeros(n_false, bool),
        np.ones(n_false if n_true is None else n_true, bool)))
    counts = rng.integers(0, pava.N_CONTEXT_BINS, labels.size).astype(
        np.int8)
    llr = np.where(labels, 1.0, -1.0) + 0.6 * counts.astype(np.float64)
    ids = np.arange(labels.size, dtype=np.int64)
    return llr, counts, labels, ids


def test_context_decision_walks_its_four_support_floors_in_order():
    _h3_support.assert_golden(
        "context floors",
        (pava.CTX_MIN_SEARCH, pava.CTX_MIN_SEARCH_PER_CLASS,
         pava.CTX_MIN_VALIDATION, pava.CTX_MIN_VALIDATION_PER_CLASS),
        (80, 20, 40, 10))
    healthy_search = _context_side(60, 1)
    healthy_validation = _context_side(30, 2)
    tiny = _context_side(5, 3)
    starved_class = _context_side(70, 4, n_true=15)
    starved_validation_class = _context_side(50, 5, n_true=5)
    assert calibrate.context_decision(tiny, healthy_validation)[2] == (
        "insufficient_search_support")
    assert calibrate.context_decision(starved_class,
                                      healthy_validation)[2] == (
        "search_class_starved")
    assert calibrate.context_decision(healthy_search, tiny)[2] == (
        "insufficient_validation_support")
    assert calibrate.context_decision(
        healthy_search, starved_validation_class)[2] == (
        "validation_class_starved")
    offsets, adopted, reason, baseline, candidate = (
        calibrate.context_decision(healthy_search, healthy_validation))
    assert offsets.shape == (pava.N_CONTEXT_BINS,)
    assert reason in ("adopted", "validation_gate_failed")
    assert adopted is (reason == "adopted")
    assert baseline is not None and candidate is not None
    assert np.all(np.diff(offsets) <= 1e-12)


def test_context_decision_refuses_a_site_with_conflicting_labels():
    llr, counts, labels, ids = _context_side(60, 1)
    ids = ids.copy()
    ids[1] = ids[0]
    labels = labels.copy()
    labels[1] = ~labels[0]
    with pytest.raises(ValueError) as excinfo:
        calibrate.context_decision((llr, counts, labels, ids),
                                   _context_side(30, 2))
    assert "conflicting labels" in str(excinfo.value)


def test_site_weights_and_unique_class_support_deduplicate_a_shared_cell():
    ids = np.asarray([0, 0, 1, 2, 2, 2], np.int64)
    weights = calibrate.site_weights(ids)
    assert np.allclose(weights, [0.5, 0.5, 1.0, 1 / 3, 1 / 3, 1 / 3])
    assert float(weights.sum()) == pytest.approx(3.0)
    labels = np.asarray([True, True, False, False, False, False])
    assert calibrate.unique_class_support(labels, ids) == (2, 1)


def _evidence(window_id, page, cells, values, llr, logloss,
              region_index=0) -> data.WindowEvidence:
    return data.WindowEvidence(
        window_id=window_id, capture_id="cap", level_index=0,
        region_index=region_index, patch_ordinal=0, page=page,
        page_cells_yx=np.asarray(cells, np.int32),
        scores=np.zeros(len(cells), np.float32),
        reference_values=np.asarray(values, np.int8),
        knots=np.zeros(0), probs=np.zeros(0), n_search=0,
        marginal_llr=np.asarray(llr, np.float32),
        printed_llr=np.asarray(llr, np.float32), accepted=True,
        refusal_reason="", heldout_logloss=logloss, ctx_adopted=False)


def test_physical_cell_ids_share_one_id_across_overlapping_windows():
    left = _evidence(("cap", 0, 0, (0, 0, 2, 2)), 0,
                     [[0, 0], [0, 1]], [-1, -1], [1.0, 2.0], 0.1)
    right = _evidence(("cap", 0, 0, (0, 1, 2, 3)), 0,
                      [[0, 1], [0, 2]], [-1, -1], [3.0, 4.0], 0.2)
    ids = calibrate.physical_cell_ids((left, right))
    assert ids[0][1] == ids[1][0]
    assert len(set(np.concatenate(ids).tolist())) == 3


def test_freeze_owners_gives_each_payload_cell_to_its_best_window(
        k_row, lookup):
    cells = _tile_cells(0, 0)
    payload = cells[calibrate.payload_cell_mask(lookup, cells)]
    better = _evidence(("cap", 0, 0, (0, 0, 64, 64)), 0, payload,
                       np.full(payload.shape[0], -1, np.int8),
                       np.full(payload.shape[0], 1.0), 0.05)
    worse = _evidence(("cap", 0, 0, (0, 32, 64, 96)), 0, payload,
                      np.full(payload.shape[0], -1, np.int8),
                      np.full(payload.shape[0], -1.0), 0.50,
                      region_index=1)
    owned = calibrate.freeze_owners((worse, better), k_row.cells_yx, lookup,
                                    "cap", 0)
    assert len(owned) == 1
    page = owned[0]
    assert page.capture_id == "cap"
    assert page.level_index == 0
    assert page.cells_yx.shape[0] == payload.shape[0]
    assert np.array_equal(page.printed_llr,
                          np.full(payload.shape[0], 1.0, np.float32))
    assert set(page.owner_window.tolist()) == {1}


def test_freeze_owners_matches_the_lib_owner_law(k_row, lookup):
    cells = _tile_cells(0, 0)
    payload = cells[calibrate.payload_cell_mask(lookup, cells)]
    rows = (
        _evidence(("cap", 0, 0, (0, 0, 64, 64)), 0, payload,
                  np.full(payload.shape[0], -1, np.int8),
                  np.arange(payload.shape[0], dtype=np.float64), 0.30),
        _evidence(("cap", 0, 0, (0, 32, 64, 96)), 0, payload,
                  np.full(payload.shape[0], -1, np.int8),
                  -np.arange(payload.shape[0], dtype=np.float64), 0.10,
                  region_index=1))
    owned = calibrate.freeze_owners(rows, k_row.cells_yx, lookup, "cap", 0)
    candidates = [
        (index, row.page, np.asarray(row.page_cells_yx, np.int64),
         np.arange(row.page_cells_yx.shape[0]),
         np.asarray(row.printed_llr, np.float32))
        for index, row in enumerate(rows)]
    order_keys = [(float(row.heldout_logloss), tuple(row.window_id[3]),
                   int(row.region_index), "K") for row in rows]
    expected = freeze_page_owners(candidates, k_row.cells_yx, order_keys)
    assert len(owned) == len(expected)
    assert np.array_equal(owned[0].cells_yx, expected[0][1])
    assert np.array_equal(owned[0].printed_llr, expected[0][2])
    assert np.array_equal(owned[0].owner_window, expected[0][3])


def test_block_validation_stripes_by_block_and_page():
    cells = np.stack(np.meshgrid(np.arange(64), np.arange(64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    _h3_support.assert_golden("BLOCK_CELLS", refine.BLOCK_CELLS, 16)
    _h3_support.assert_golden("VALIDATION_MODULUS", refine.VALIDATION_MODULUS,
                              4)
    flags = refine.block_validation(0, cells)
    blocks = cells // refine.BLOCK_CELLS
    token = (0 * refine.STRIPE_PAGE_COEFFICIENT
             + blocks[:, 0] * refine.STRIPE_Y_COEFFICIENT
             + blocks[:, 1] * refine.STRIPE_X_COEFFICIENT)
    assert np.array_equal(flags, (token % 4) == 0)
    for block in np.unique(blocks, axis=0):
        selected = (blocks == block).all(axis=1)
        assert len(set(flags[selected].tolist())) == 1
    assert not np.array_equal(flags, refine.block_validation(1, cells))


def test_block_weights_normalise_each_block_to_unit_mass():
    ids = np.asarray([7, 7, 7, 9, 11, 11], np.int64)
    weights = refine.block_weights(ids)
    assert np.allclose(weights, [1 / 3, 1 / 3, 1 / 3, 1.0, 0.5, 0.5])
    assert float(weights.sum()) == pytest.approx(3.0)
    assert refine.block_weights(np.zeros(0, np.int64)).size == 0


def test_deterministic_cap_is_seed_free_and_permutation_stable():
    cells = np.stack(np.meshgrid(np.arange(20), np.arange(20),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    positions = np.arange(cells.shape[0], dtype=np.int64)
    capped = refine.deterministic_cap(positions, cells, 40)
    assert capped.size == 40
    assert np.array_equal(
        refine.deterministic_cap(positions, cells, 40), capped)
    rng = np.random.default_rng(99)
    shuffled = rng.permutation(positions)
    other = refine.deterministic_cap(shuffled, cells, 40)
    assert set(other.tolist()) == set(capped.tolist())
    assert np.array_equal(
        refine.deterministic_cap(positions, cells, 10 ** 6), positions)


def _labels_for(k_row, k_geometry, lookup, page: int = 0,
                ty: int = 1, tx: int = 1) -> tuple:
    cells = _tile_cells(ty, tx)
    values = calibrate.format_reference_values(k_row, lookup, page, cells)
    rng = np.random.default_rng(6060)
    user = rng.integers(0, 2, size=k_row.streams[0].user_bits,
                        dtype=np.uint8)
    from holo3.plugins import tiles

    field = tiles.printed_cells_for(k_row, k_geometry, page, ty, tx, user)
    printed = {(page, ty, tx): field}
    return cells, values, printed, field


def test_collect_labels_joins_pilot_sites_and_certified_cargo(
        k_row, k_geometry, lookup):
    cells, values, printed, field = _labels_for(k_row, k_geometry, lookup)
    labels = refine.collect_labels(0, cells, values, printed)
    assert labels.rows.size == cells.shape[0]
    assert int(labels.is_pilot.sum()) == k_row.n_sites
    pilots_rows = labels.rows[labels.is_pilot]
    assert np.array_equal(labels.values[labels.is_pilot],
                          values[pilots_rows].astype(np.uint8))
    cargo = ~labels.is_pilot
    cargo_cells = labels.page_cells_yx[cargo]
    assert np.array_equal(
        labels.values[cargo],
        field[cargo_cells[:, 0] % TILE_CELLS,
              cargo_cells[:, 1] % TILE_CELLS])
    assert np.array_equal(
        labels.validation[labels.is_pilot],
        site_parity(labels.page_cells_yx[labels.is_pilot][:, 0],
                    labels.page_cells_yx[labels.is_pilot][:, 1]).astype(
                        bool))
    assert np.array_equal(labels.validation[cargo],
                          refine.block_validation(0, cargo_cells))
    assert float(labels.weights[labels.train].sum()) > 0.0


def test_collect_labels_drops_cargo_with_no_certified_tile(k_row,
                                                            k_geometry,
                                                            lookup):
    cells, values, _printed, _field = _labels_for(k_row, k_geometry, lookup)
    labels = refine.collect_labels(0, cells, values, {})
    assert int(labels.is_pilot.sum()) == labels.rows.size
    assert labels.rows.size == k_row.n_sites


def test_support_metrics_names_the_first_floor_it_fails(k_row, k_geometry,
                                                         lookup):
    _h3_support.assert_golden(
        "refine support floors",
        (refine.MIN_PAYLOAD_TRAIN, refine.MIN_PAYLOAD_VALIDATION,
         refine.MIN_TRAIN_PER_CLASS, refine.MIN_VALIDATION_PER_CLASS,
         refine.MIN_CERTIFIED_BLOCKS, refine.MIN_POSE_PILOTS),
        (64, 32, 20, 10, 4, 30))
    cells, values, printed, _field = _labels_for(k_row, k_geometry, lookup)
    supported, reason, counts = refine.support_metrics(
        refine.collect_labels(0, cells, values, printed))
    assert supported is True
    assert reason == ""
    assert counts["n_certified_blocks"] == 16
    assert counts["n_payload_train"] > refine.MIN_PAYLOAD_TRAIN
    starved, starved_reason, starved_counts = refine.support_metrics(
        refine.collect_labels(0, cells, values, {}))
    assert starved is False
    assert starved_reason == "insufficient_payload_train"
    assert starved_counts["n_payload_train"] == 0


def test_select_pose_sites_keeps_every_pilot_and_caps_the_cargo(
        k_row, k_geometry, lookup):
    cells, values, printed, _field = _labels_for(k_row, k_geometry, lookup)
    labels = refine.collect_labels(0, cells, values, printed)
    train = refine.select_pose_sites(labels, validation=False)
    valid = refine.select_pose_sites(labels, validation=True)
    assert set(train.tolist()) & set(valid.tolist()) == set()
    assert labels.train[train].all()
    assert labels.validation[valid].all()
    assert int(labels.is_pilot[train].sum()) == int(
        (labels.is_pilot & labels.train).sum())
    assert train.size <= refine.POSE_SITE_CAP_TRAIN
    assert valid.size <= refine.POSE_SITE_CAP_VALIDATION
    assert np.array_equal(
        train, refine.select_pose_sites(labels, validation=False))
    assert np.array_equal(np.sort(labels.rows[train]), labels.rows[train])


def test_pose_candidate_rotates_and_shifts_the_base_pose():
    base = refine.LocalPose((10.0, 20.0), ((6.0, 0.0), (0.0, 6.0)),
                            (0.0, 0.0), 6.0, 0.0)
    same = refine.pose_candidate(base, 0.0, 0.0, 0.0)
    assert same.origin_yx == pytest.approx(base.origin_yx)
    assert np.allclose(same.matrix(), base.matrix())
    shifted = refine.pose_candidate(base, 0.0, 0.5, -0.25)
    assert shifted.origin_yx == pytest.approx((13.0, 18.5))
    turned = refine.pose_candidate(base, 0.1, 0.0, 0.0)
    assert turned.angle_deg == pytest.approx(0.1, abs=1e-9)
    assert turned.pitch_px == pytest.approx(6.0, abs=1e-9)


def test_pose_objective_is_the_class_separation_over_the_spread():
    means = np.asarray([10.0, 10.0, 90.0, 90.0], np.float64)
    values = np.asarray([1, 1, 0, 0], np.uint8)
    weights = np.ones(4, np.float64)
    assert refine.pose_objective(means, values, weights) == pytest.approx(
        2.0)
    assert refine.pose_objective(means, np.ones(4, np.uint8),
                                 weights) == -np.inf
    flat = np.full(4, 50.0, np.float64)
    assert refine.pose_objective(flat, values, weights) == 0.0


def test_weighted_logloss_is_the_weighted_binary_cross_entropy():
    logits = np.asarray([0.0, 2.0, -2.0], np.float64)
    values = np.asarray([1, 1, 0], np.float64)
    weights = np.asarray([1.0, 2.0, 3.0], np.float64)
    expected = float(
        np.sum(weights * (np.logaddexp(0.0, logits) - values * logits))
        / weights.sum())
    assert refine.weighted_logloss(logits, values, weights) == expected
    assert refine.weighted_logloss(
        np.asarray([50.0]), np.asarray([1.0]),
        np.asarray([1.0])) == pytest.approx(0.0, abs=1e-20)


def test_score_reference_and_window_scores_share_the_calibrate_convention():
    means = np.asarray([10.0, 20.0, 200.0, 210.0], np.float32)
    midpoint, spread = refine.score_reference(means)
    assert midpoint == np.float32(np.median(means))
    assert spread == np.float32(np.abs(means - midpoint).mean())
    assert np.array_equal(refine.window_scores(means, midpoint, spread),
                          calibrate.window_scores(means))


@pytest.mark.parametrize(
    "candidate_loss,candidate_pilot,candidate_raw,adopts",
    [(1.0 - 2e-4, 0.10, 0.10, True),
     (1.0, 0.10, 0.10, False),
     (1.0 - 2e-4, 0.10 + refine.PILOT_MISMATCH_SLACK, 0.10, True),
     (1.0 - 2e-4, 0.10 + 2 * refine.PILOT_MISMATCH_SLACK, 0.10, False),
     (1.0 - 2e-4, 0.10, 0.10 + 2 * refine.PILOT_MISMATCH_SLACK, False),
     (1.0 - 5e-5, 0.10, 0.10, False)])
def test_adoption_gate_needs_a_strict_heldout_gain(candidate_loss,
                                                   candidate_pilot,
                                                   candidate_raw, adopts):
    _h3_support.assert_golden("MIN_HELDOUT_GAIN", refine.MIN_HELDOUT_GAIN,
                              1e-4)
    _h3_support.assert_golden("PILOT_MISMATCH_SLACK",
                              refine.PILOT_MISMATCH_SLACK, 0.005)
    assert refine.adoption_gate(1.0, candidate_loss, 0.10, candidate_pilot,
                                0.10, candidate_raw) is adopts


def test_candidate_and_fine_grids_cover_the_declared_search_box():
    coarse = refine.candidate_grid()
    assert len(coarse) == 3 * 3 * 3
    assert (0.0, 0.0, 0.0) in [
        tuple(round(v, 12) for v in row) for row in coarse]
    for dtheta, du, dv in coarse:
        assert abs(dtheta) <= refine.ANGLE_LIMIT_DEG + 1e-9
        assert abs(du) <= refine.PHASE_LIMIT_CELLS + 1e-9
        assert abs(dv) <= refine.PHASE_LIMIT_CELLS + 1e-9
    fine = refine.fine_grid((0.0, 0.0, 0.0))
    assert len(fine) > 0
    for dtheta, du, dv in fine:
        assert abs(dtheta) <= refine.ANGLE_LIMIT_DEG + 1e-9
        assert abs(du) <= refine.PHASE_LIMIT_CELLS + 1e-9
        assert abs(dv) <= refine.PHASE_LIMIT_CELLS + 1e-9
    edge = refine.fine_grid((refine.ANGLE_LIMIT_DEG,
                             refine.PHASE_LIMIT_CELLS,
                             refine.PHASE_LIMIT_CELLS))
    assert all(abs(row[0]) <= refine.ANGLE_LIMIT_DEG + 1e-9 for row in edge)


def test_select_best_breaks_an_exact_contrast_tie_by_loss_then_norm():
    candidates = {
        (0.0, 0.0, 0.0): (5.0, 0.30),
        (0.05, 0.0, 0.0): (5.0, 0.20),
        (-0.05, 0.0, 0.0): (5.0, 0.20),
        (0.10, 0.0, 0.0): (4.0, 0.01),
    }
    assert refine.select_best(candidates, tuple(candidates)) == (
        -0.05, 0.0, 0.0)
    tied = {
        (0.0, 0.25, 0.0): (5.0, 0.20),
        (0.0, 0.0, 0.0): (5.0, 0.20),
    }
    assert refine.select_best(tied, tuple(tied)) == (0.0, 0.0, 0.0)
    within_tie = {
        (0.0, 0.0, 0.0): (5.0, 0.20),
        (0.05, 0.0, 0.0): (5.0 - refine.CONTRAST_TIE / 2.0, 0.10),
    }
    assert refine.select_best(within_tie, tuple(within_tie)) == (
        0.05, 0.0, 0.0)
    outside_tie = {
        (0.0, 0.0, 0.0): (5.0, 0.20),
        (0.05, 0.0, 0.0): (4.0, 0.10),
    }
    assert refine.select_best(outside_tie, tuple(outside_tie)) == (
        0.0, 0.0, 0.0)


def test_revised_placement_stamps_the_refine_route_and_the_fitted_basis():
    local = np.zeros((1, 2), np.int64)
    placement = _placement(0, (0, 0, 1, 1), local)
    revision = refine.Revision(True, refine.OUTCOME_ADOPTED,
                               (1.0, 0.0, 2.0, 0.0, 1.0, 3.0),
                               basis=((0, 1, 1), (0, 2, 3)))
    revised = refine.revised_placement(placement, revision)
    assert revised.native_affine == revision.affine
    assert revised.route == refine.ROUTE_REFINE
    assert revised.window_id == placement.window_id
    assert revised.refine_basis == ((0, 1, 1), (0, 2, 3)), (
        "the adopted placement carries the certified reach the revision "
        "was fitted from — the gate the lift re-arms against"
    )
    assert placement.route == "word"
    assert placement.refine_basis == ()


def test_reach_tiles_and_certified_reach_are_sorted_and_deduplicated():
    cells = np.asarray([[0, 0], [63, 63], [64, 0], [64, 65], [130, 5]],
                       np.int64)
    assert refine.reach_tiles(cells) == ((0, 0), (1, 0), (1, 1), (2, 0))
    certified = frozenset({(0, 1, 0), (0, 2, 0), (1, 0, 0)})
    assert refine.certified_reach(0, refine.reach_tiles(cells),
                                  certified) == ((0, 1, 0), (0, 2, 0))


REACH_CELLS = ((0, 0), (63, 63), (64, 0), (64, 65), (130, 5))
FULL_REACH = frozenset({(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 2, 0)})


def _reach_cells() -> np.ndarray:
    return np.asarray(REACH_CELLS, np.int64)


def _reach() -> tuple:
    return refine.reach_tiles(_reach_cells())


@pytest.mark.parametrize(
    "certified,basis,eligible",
    [(frozenset(), (), False),
     (frozenset({(0, 0, 0)}), (), True),
     (FULL_REACH, (), False),
     (frozenset({(0, 0, 0)}), ((0, 0, 0),), False),
     (frozenset({(0, 0, 0), (0, 1, 0)}), ((0, 0, 0),), True),
     (frozenset({(0, 1, 0)}), ((0, 0, 0),), False),
     (FULL_REACH, ((0, 0, 0),), False)])
def test_refine_re_arms_only_when_the_reach_outgrows_the_adopted_basis(
        certified, basis, eligible):
    assert refine.refine_eligible(0, _reach(), certified,
                                  basis) is eligible


def test_a_reach_that_moved_instead_of_growing_never_re_arms_refine():
    moved = frozenset({(0, 1, 0), (0, 1, 1)})
    assert refine.refine_eligible(0, _reach(), moved,
                                  ((0, 0, 0),)) is False, (
        "eligibility is a STRICT SUPERSET test, so the adopted basis can "
        "only grow: that is the whole termination argument"
    )


@pytest.mark.parametrize(
    "certified,exhausted",
    [(frozenset(), False),
     (frozenset({(0, 0, 0)}), False),
     (FULL_REACH, True)])
def test_refine_retires_only_on_a_fully_certified_reach(certified,
                                                        exhausted):
    assert refine.refine_exhausted(0, _reach(),
                                   certified) is exhausted


def test_an_empty_reach_is_not_an_exhausted_one():
    assert refine.refine_exhausted(0, (), frozenset()) is False


def test_reach_certified_asks_the_store_one_tile_at_a_time(k_row):
    certified = {(0, 0, 0, "main"), (0, 1, 1, "main")}
    asked: list[tuple] = []

    def has_certificate(key: tuple) -> bool:
        asked.append(key)
        return key in certified

    store = SimpleNamespace(row=k_row, has_certificate=has_certificate)
    assert refine.reach_certified(store, 0, _reach()) == frozenset(
        {(0, 0, 0), (0, 1, 1)})
    assert set(asked) == {(0, ty, tx, stream.stream_id)
                          for ty, tx in refine.reach_tiles(_reach_cells())
                          for stream in k_row.streams}


def test_certified_fields_reprints_one_field_per_address(k_row, k_geometry):
    from holo3.plugins import tiles

    rng = np.random.default_rng(4242)
    user = rng.integers(0, 2, size=k_row.streams[0].user_bits,
                        dtype=np.uint8)
    certificates = (
        data.Certificate(0, 1, 1, "main", user, "tiles/scan"),
        data.Certificate(0, 1, 1, "main", user, "tiles/union"),
        data.Certificate(0, 2, 3, "main", user, "tiles/scan"))
    fields = refine.certified_fields(k_row, k_geometry, certificates)
    assert sorted(fields) == [(0, 1, 1), (0, 2, 3)]
    assert np.array_equal(
        fields[(0, 1, 1)],
        tiles.printed_cells_for(k_row, k_geometry, 0, 1, 1, user))
    assert not np.array_equal(fields[(0, 1, 1)], fields[(0, 2, 3)])


FIT_TILE = (0, 1, 1)
FIT_SHIFT_CELLS = 0.25
FIT_PAPER = 235.0
FIT_INK = 60.0


def _shifted_print(k_row, k_geometry, lookup, du_cells: float) -> tuple:
    shape = (TILE_CELLS, TILE_CELLS)
    local = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    placement = _placement(0, (0, 0, TILE_CELLS, TILE_CELLS), local,
                           origin=(TILE_CELLS, TILE_CELLS))
    cells = calibrate.window_page_cells(placement, shape, k_row.cells_yx)
    from holo3.plugins import tiles

    rng = np.random.default_rng(4242)
    user = rng.integers(0, 2, size=k_row.streams[0].user_bits,
                        dtype=np.uint8)
    field = tiles.printed_cells_for(k_row, k_geometry, *FIT_TILE, user)
    ink = field[cells[:, 0] % TILE_CELLS, cells[:, 1] % TILE_CELLS]
    matrix = np.asarray(SAMPLE_AFFINE, np.float64).reshape(2, 3)
    truth = matrix.copy()
    truth[:, 2] += matrix[:, :2] @ np.asarray((du_cells, 0.0), np.float64)
    points = (cells.astype(np.float64) + 0.5) @ truth[:, :2].T + truth[:, 2]
    plane = np.full((int(np.ceil(points[:, 0].max())) + 20,
                     int(np.ceil(points[:, 1].max())) + 20), FIT_PAPER,
                    np.float32)
    for point, dark in zip(np.rint(points).astype(np.int64), ink,
                           strict=True):
        if dark:
            plane[point[0] - 1:point[0] + 2,
                  point[1] - 1:point[1] + 2] = FIT_INK
    evidence = calibrate.calibrate_window(
        (plane,), placement, shape, k_row, lookup, SAMPLE_PITCH_PX,
        Fraction(1))
    return placement, evidence, plane, {FIT_TILE: field}


def test_an_adopted_revision_publishes_the_reach_it_actually_fitted_from(
        k_row, k_geometry, lookup, monkeypatch):
    # the two-entry grid keeps the fit at millisecond cost; the real
    # search box is pinned by the grid test above
    monkeypatch.setattr(
        refine, "candidate_grid",
        lambda: ((0.0, 0.0, 0.0), (0.0, FIT_SHIFT_CELLS, 0.0)))
    monkeypatch.setattr(refine, "fine_grid", lambda best: ())
    placement, evidence, plane, printed = _shifted_print(
        k_row, k_geometry, lookup, FIT_SHIFT_CELLS)
    assert evidence.accepted is True
    revision = refine.refine_window(placement, evidence, plane, (0, 0),
                                    FIT_PAPER, Fraction(1), printed)
    assert revision.adopted is True
    assert revision.reason == refine.OUTCOME_ADOPTED
    assert revision.du_cells == FIT_SHIFT_CELLS
    assert revision.basis == (FIT_TILE,), (
        "a fit that publishes no basis leaves the lift with an empty gate "
        "and refine re-fires on its own adoption forever"
    )
    assert refine.revised_placement(placement,
                                    revision).refine_basis == (FIT_TILE,)


def test_a_refusing_fit_publishes_no_basis_to_re_arm_against(k_row,
                                                             k_geometry,
                                                             lookup):
    placement, evidence, plane, _printed = _shifted_print(
        k_row, k_geometry, lookup, 0.0)
    revision = refine.refine_window(placement, evidence, plane, (0, 0),
                                    FIT_PAPER, Fraction(1), {})
    assert revision.adopted is False
    assert revision.reason == "insufficient_payload_train"
    assert revision.basis == ()


def test_local_pose_matrix_and_segment_expose_the_same_linear_part():
    cells = _tile_cells(0, 0)
    local_pose, local = refine.local_segment(SAMPLE_AFFINE, Fraction(1),
                                             cells)
    assert np.array_equal(local, cells - cells.min(axis=0))
    matrix = np.asarray(SAMPLE_AFFINE, np.float64).reshape(2, 3)[:, :2]
    assert np.array_equal(local_pose.matrix(), matrix)
    assert local_pose.pitch_px == pytest.approx(
        0.5 * (float(np.hypot(*matrix[:, 0]))
               + float(np.hypot(*matrix[:, 1]))))


def test_replace_keeps_window_evidence_frozen():
    row = _evidence(("cap", 0, 0, (0, 0, 2, 2)), 0, [[0, 0]], [-1], [1.0],
                    0.1)
    updated = replace(row, ctx_adopted=True)
    assert updated is not row
    assert updated.ctx_adopted is True
    assert row.ctx_adopted is False
    assert data.WindowEvidence.__dataclass_params__.frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.ctx_adopted = True
    with pytest.raises(dataclasses.FrozenInstanceError):
        updated.heldout_logloss = 0.0
    for field in ("window_id", "capture_id", "page", "page_cells_yx"):
        assert getattr(updated, field) is getattr(row, field)
