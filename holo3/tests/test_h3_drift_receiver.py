from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from holo3.data import Certificate, IntegrityError
from holo3.format import pilots as h3_pilots
from holo3.format.identity import SiteGeometry, build_site_geometry
from holo3.format.identity import resolve_format_ref as h3_resolve
from holo3.lib import pava as h3_pava
from holo3.plugins import calibrate as h3_cal
from holo3.plugins import color_conditioning as h3_conditioning
from holo3.plugins import color_model as h3_cm
from holo3.plugins import color_photometry as h3_photometry
from holo3.plugins import color_refine as h3_color_refine
from holo3.plugins import refine as h3_refine
from holo3.plugins import tiles as h3_tiles
from holo3.tests import _h3_support

v1_fossils = pytest.importorskip("holo.format.fossils")
v1_metadata = pytest.importorskip("holo.format.metadata")
v1_resolve_mod = pytest.importorskip("holo.format.resolve")
v1_detect = pytest.importorskip("holo.receive.detect")
v1_ctx = pytest.importorskip("holo.receive._payload_context")
v1_sampling = pytest.importorskip("holo.receive._payload_sampling")
v1_payload = pytest.importorskip("holo.receive.payload")
v1_certified_refine = pytest.importorskip("holo.receive.certified_refine")
v1_color_detect = pytest.importorskip("holo.receive.color_detect")
v1_color_cal = pytest.importorskip("holo.receive.color_calibration")
v1_color_anchor = pytest.importorskip("holo.receive.color_anchoring")
v1_color_refine = pytest.importorskip("holo.receive.color_refine")
v1_tiles = pytest.importorskip("holo.receive.tiles")
v1_evidence = pytest.importorskip("holo.receive.evidence")
v1_compose = pytest.importorskip("holo.gen.compose")
h2_refine_fit = pytest.importorskip("holo2.solve.refine_fit")
h2_place_model = pytest.importorskip("holo2.solve.place_model")
h2_reference = pytest.importorskip("holo2.solve.reference")
v1_place_model = pytest.importorskip("holo.receive.placement.model")

pytestmark = pytest.mark.skipif(
    not _h3_support.slow_lane(),
    reason=f"cross-tree drift equivalence is a full-lane corpus: set "
           f"{_h3_support.SLOW_LANE_ENV}=1")

v1_resolve = v1_resolve_mod.resolve_format_ref
attempt_k_tile = v1_payload.attempt_k_tile
AttemptStage = v1_evidence.AttemptStage
AttemptState = v1_evidence.AttemptState

RECEIVER_SEED = 20260828
E029_REF = "L:c2-r0700@3392x2368"
SIM_K_REF = "c3-k-r0550@7x7"
MAG = 6.0


@pytest.fixture(scope="module", autouse=True)
def _v1_serial_workers():
    import os

    previous = os.environ.get("HOLO_RECEIVE_WORKERS")
    os.environ["HOLO_RECEIVE_WORKERS"] = "1"
    try:
        yield "1"
    finally:
        if previous is None:
            os.environ.pop("HOLO_RECEIVE_WORKERS", None)
        else:
            os.environ["HOLO_RECEIVE_WORKERS"] = previous


def _n(fast: int, full: int) -> int:
    return full if _h3_support.oracle_sweeps() else fast


def eq_arrays(a: np.ndarray, b: np.ndarray) -> bool:
    a = np.asarray(a)
    b = np.asarray(b)
    return (a.dtype == b.dtype and a.shape == b.shape
            and bool(np.array_equal(a, b)))


def _k_row_and_lookup(format_ref: str):
    row = h3_resolve(format_ref)
    spec = v1_resolve(format_ref)
    word = h3_pilots.word_site_cells_yx(row.sites_seed)
    filler = h3_pilots.filler_site_cells_yx(
        row.sites_seed, row.n_sites - h3_pilots.N_WORD_SITES, word)
    empty = np.zeros(0, np.int64)
    geometry = SiteGeometry(word, filler, empty, empty, empty, empty)
    return row, spec, geometry, h3_cal.build_site_lookup(geometry)


ROW, SPEC, GEOMETRY, LOOKUP = _k_row_and_lookup(E029_REF)


def _cell_grid(y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
    return np.stack(np.meshgrid(np.arange(y0, y1, dtype=np.int64),
                                np.arange(x0, x1, dtype=np.int64),
                                indexing="ij"), axis=-1).reshape(-1, 2)


def test_calibrate_row_identity_agrees_with_v1_resolution():
    assert ROW.seed == SPEC.seed
    assert ROW.sites_seed == SPEC.family_seed
    assert ROW.tiles_yx == SPEC.layout.tiles_yx
    assert ROW.cells_yx == SPEC.layout.cells_yx


def test_calibrate_site_lookup_and_reference_labels_match_v1_sampling():
    kind, index = v1_sampling._site_lookup(SPEC.family_seed, SPEC.n_filler)
    assert eq_arrays(LOOKUP.kind, kind)
    assert eq_arrays(LOOKUP.index, index)
    cells = _cell_grid(120, 260, 64, 200)
    for page in (0, 1):
        mine = h3_cal.format_reference_values(ROW, LOOKUP, page, cells)
        assert eq_arrays(mine, v1_sampling.format_reference_values(
            SPEC, page, cells))
    assert eq_arrays(h3_cal.payload_cell_mask(LOOKUP, cells),
                     v1_payload.payload_cell_mask(SPEC, cells))
    labels = h3_cal.format_reference_values(ROW, LOOKUP, 0, cells)
    assert int(np.count_nonzero(labels >= 0)) > 200


def test_calibrate_filler_branch_reference_labels_match_v1():
    row, spec, _geometry, lookup = _k_row_and_lookup("c2-k-r0700-p120@53x37")
    assert row.seed == spec.seed
    v1_kind = v1_sampling._site_lookup(spec.family_seed, spec.n_filler)[0]
    assert eq_arrays(lookup.kind, v1_kind)
    cells = _cell_grid(120, 260, 64, 200)
    assert eq_arrays(h3_cal.format_reference_values(row, lookup, 1, cells),
                     v1_sampling.format_reference_values(spec, 1, cells))
    assert int(np.count_nonzero(lookup.kind == 1)) == 20


@pytest.mark.parametrize("pitch_values", ([8.0], [8.0, 7.5, 9.25],
                                          [6.0, 6.5, 7.0, 7.25]))
def test_calibrate_region_pitch_matches_v1_sampling(pitch_values):
    patches = tuple(SimpleNamespace(segment=SimpleNamespace(
        segment=SimpleNamespace(pose=SimpleNamespace(pitch_px=value))))
        for value in pitch_values)
    assert (h3_cal.region_pitch_px(pitch_values)
            == v1_sampling._region_pitch(patches))


class _Pose:

    def __init__(self, matrix: np.ndarray, origin: np.ndarray,
                 pitch_px: float) -> None:
        self.matrix = matrix
        self.origin = origin
        self.pitch_px = pitch_px

    def points(self, cells_yx: np.ndarray) -> np.ndarray:
        return np.asarray(cells_yx, np.float64) @ self.matrix.T + self.origin


@pytest.mark.parametrize("pitch_px,angle_deg,cells_yx,origin,shape_yx", (
    (8.0, 0.0, (40, 50), (60.0, 70.0), (700, 800)),
    (7.9375, 0.35, (48, 64), (33.25, 41.5), (900, 1000)),
    (2.0, -0.2, (60, 90), (12.5, 9.25), (300, 400)),
    (16.25, 1.1, (24, 30), (80.5, 55.0), (900, 900)),
))
def test_calibrate_window_sampling_matches_v1_payload_sampling(
        pitch_px, angle_deg, cells_yx, origin, shape_yx):
    rng = np.random.default_rng(RECEIVER_SEED + int(pitch_px * 100))
    theta = np.deg2rad(angle_deg)
    matrix = pitch_px * np.asarray(
        ((np.cos(theta), -np.sin(theta)), (np.sin(theta), np.cos(theta))),
        np.float64)
    pose = _Pose(matrix, np.asarray(origin, np.float64), pitch_px)
    ny, nx = cells_yx
    local = _cell_grid(0, ny, 0, nx)
    points = pose.points(local.astype(np.float64))
    image = rng.integers(0, 256, size=shape_yx, dtype=np.uint8)
    raster = SimpleNamespace(
        shape=shape_yx,
        crop_luma=lambda y0, y1, x0, x1: image[y0:y1, x0:x1])
    patch = SimpleNamespace(segment=SimpleNamespace(segment=SimpleNamespace(
        window=SimpleNamespace(shape_yx_cells=(ny, nx)), pose=pose)))
    v1_crop = v1_sampling._window_crop(raster, patch, pitch_px)
    rows = v1_sampling._WindowRows(0, local.astype(np.int32),
                                   local.astype(np.int32), points)
    v1_means = v1_sampling._sample_rows(v1_crop, rows, shape_yx)
    mine_crop = h3_cal.window_crop([image], points, shape_yx, pitch_px)
    mine_means = h3_cal.sample_points(mine_crop, points)
    assert eq_arrays(mine_means, v1_means)
    assert v1_sampling._filter_signature((patch,)) == (
        int(np.ceil(h3_cal.APERTURE_CELLS * pitch_px)) + 2,
        max(1, int(round(h3_cal.APERTURE_CELLS * pitch_px))))
    assert eq_arrays(h3_cal.window_scores(mine_means),
                     v1_sampling._scores(v1_means))
    assert h3_cal.window_scores(mine_means).dtype == np.float32


def test_calibrate_crop_luma_matches_the_v1_raster_laws():
    rng = np.random.default_rng(RECEIVER_SEED + 1)
    rgb = rng.integers(0, 256, size=(40, 50, 3), dtype=np.uint8)
    grey = rng.integers(0, 256, size=(40, 50), dtype=np.uint8)
    assert eq_arrays(
        h3_cal.crop_luma([rgb[..., 0], rgb[..., 1], rgb[..., 2]], 3, 30, 5, 40),
        rgb[3:30, 5:40].mean(axis=2, dtype=np.float32))
    assert eq_arrays(h3_cal.crop_luma([grey], 3, 30, 5, 40),
                     grey[3:30, 5:40].astype(np.float32))


@pytest.mark.parametrize("tag", ("random", "constant", "bimodal", "tiny"))
def test_calibrate_window_scores_edge_cases_match_v1(tag):
    rng = np.random.default_rng(RECEIVER_SEED + 2)
    means = {
        "random": rng.normal(128.0, 40.0, size=4096).astype(np.float32),
        "constant": np.full(512, 200.0, np.float32),
        "bimodal": np.where(rng.random(4096) < 0.4, 20.0,
                            230.0).astype(np.float32),
        "tiny": np.asarray([1.0, 1.0, 1.0000001], np.float32),
    }[tag]
    assert eq_arrays(h3_cal.window_scores(means), v1_sampling._scores(means))


def _v1_window_fit(scores: np.ndarray, labels: np.ndarray,
                   page_cells: np.ndarray, page: int):
    parity = ((131 * page_cells[:, 0] + 17 * page_cells[:, 1]) & 1).astype(bool)
    known = labels >= 0
    search_mask = known & ~parity
    heldout_mask = known & parity
    ids = v1_sampling._site_ids(SPEC, page, page_cells)
    search = v1_detect.CalibrationObservations(
        "w", scores[search_mask], labels[search_mask], ids[search_mask])
    heldout = v1_detect.CalibrationObservations(
        "w", scores[heldout_mask], labels[heldout_mask], ids[heldout_mask])
    fit = v1_detect.fit_calibration(search, heldout)
    if not fit.accepted:
        return fit, None, None
    llr = np.asarray(fit.calibration.llr(scores), np.float32)
    probability = fit.calibration.probability(scores[heldout_mask])
    heldout_labels = labels[heldout_mask].astype(np.float64)
    loss = float(-np.mean(heldout_labels * np.log(probability)
                          + (1.0 - heldout_labels)
                          * np.log(1.0 - probability)))
    return fit, llr, loss


@pytest.mark.parametrize("n_cells,ink_bias,page,starve", (
    (16384, 1.4, 0, ""),
    (4096, 0.35, 1, ""),
    (4096, 3.0, 0, ""),
    (4096, 1.0, 0, "class"),
    (4096, 1.0, 0, "none"),
))
def test_calibrate_window_fit_matches_v1_detect_including_refusals(
        n_cells, ink_bias, page, starve):
    rng = np.random.default_rng(RECEIVER_SEED + n_cells + page + len(starve))
    side = int(np.sqrt(n_cells))
    cells = _cell_grid(200, 200 + side, 300, 300 + side)
    labels = h3_cal.format_reference_values(ROW, LOOKUP, page, cells)
    if starve == "class":
        labels = np.where(labels >= 0, np.int8(1), np.int8(-1)).astype(np.int8)
    if starve == "none":
        labels = np.full(labels.size, -1, np.int8)
    truth = labels.astype(np.float64)
    scores = (rng.normal(0.0, 1.0, size=cells.shape[0])
              + ink_bias * np.where(truth > 0, 1.0, -1.0)).astype(np.float32)
    v1_fit, v1_llr, v1_loss = _v1_window_fit(scores, labels, cells, page)
    mine = h3_cal.fit_window_calibration(scores, labels, cells)
    assert mine.accepted == v1_fit.accepted
    reason = "accepted" if mine.accepted else mine.reason
    assert reason == v1_fit.reason
    if not v1_fit.accepted:
        return
    assert eq_arrays(mine.knots, v1_fit.calibration.knots)
    assert eq_arrays(mine.probs, v1_fit.calibration.probabilities)
    assert mine.n_search == v1_fit.n_search
    assert eq_arrays(mine.marginal_llr, v1_llr)
    assert mine.heldout_logloss == v1_loss
    bound = v1_detect.clamp_for(mine.n_search)
    assert float(np.max(np.abs(mine.marginal_llr))) <= bound + 1e-6


def test_calibrate_tiny_window_refuses_with_the_same_reason_as_v1():
    rng = np.random.default_rng(RECEIVER_SEED + 3)
    cells = _cell_grid(64, 70, 64, 70)
    labels = h3_cal.format_reference_values(ROW, LOOKUP, 0, cells)
    scores = rng.normal(size=cells.shape[0]).astype(np.float32)
    v1_fit = _v1_window_fit(scores, labels, cells, 0)[0]
    mine = h3_cal.fit_window_calibration(scores, labels, cells)
    assert not mine.accepted
    assert mine.reason == v1_fit.reason


@pytest.mark.parametrize("keep", (1.0, 0.85, 0.5))
def test_calibrate_context_primitives_match_v1_detect(keep):
    rng = np.random.default_rng(RECEIVER_SEED + int(keep * 100))
    grid = _cell_grid(30, 70, 50, 95)
    cells = grid[rng.random(grid.shape[0]) < keep]
    ink = rng.random(cells.shape[0]) < 0.45
    mine_counts, mine_valid = h3_cal.context_neighbour_counts(cells, ink)
    v1_counts, v1_valid = v1_detect.context_neighbour_counts(cells, ink)
    assert eq_arrays(mine_counts, v1_counts)
    assert eq_arrays(mine_valid, v1_valid)
    bins = np.where(mine_valid, mine_counts, -1).astype(np.int8)
    assert eq_arrays(bins, v1_detect.context_bins(v1_counts, valid=v1_valid))
    llr = rng.normal(0.0, 6.0, size=cells.shape[0])
    offsets = np.sort(rng.uniform(-4.0, 4.0, size=9))[::-1].copy()
    assert eq_arrays(h3_cal.apply_context_offsets(llr, bins, offsets),
                     v1_detect.apply_context_offsets(llr, bins, offsets))


def test_calibrate_duplicate_page_cell_raises_on_both_sides():
    duplicates = np.asarray([[1, 1], [1, 1], [2, 2]], np.int64)
    with pytest.raises(ValueError):
        h3_cal.context_neighbour_counts(duplicates, np.zeros(3, bool))
    with pytest.raises(ValueError):
        v1_detect.context_neighbour_counts(duplicates, np.zeros(3, bool))


def _ctx_population(rng: np.random.Generator, n_sites: int,
                    duplicate_fraction: float, signal: float, ink_rate: float,
                    ctx_slope: float = -0.35):
    ids = np.arange(n_sites, dtype=np.int64)
    n_duplicates = int(n_sites * duplicate_fraction)
    ids = np.concatenate((ids, ids[:n_duplicates]))
    labels = rng.random(n_sites) < ink_rate
    labels = np.concatenate((labels, labels[:n_duplicates]))
    counts = rng.integers(0, 9, size=ids.size).astype(np.int8)
    llr = (signal * np.where(labels, 1.0, -1.0)
           + rng.normal(0.0, 1.5, size=ids.size)
           + ctx_slope * counts.astype(np.float64))
    order = rng.permutation(ids.size)
    return llr[order], counts[order], labels[order], ids[order]


CTX_CASES = (
    ("wide", (900, 0.25, 1.1, 0.5), (500, 0.2, 1.1, 0.5)),
    ("noisy", (400, 0.4, 0.15, 0.45), (260, 0.35, 0.15, 0.45)),
    ("balanced-strong", (1200, 0.1, 2.4, 0.5), (700, 0.1, 2.4, 0.5)),
    ("gate-should-fail", (600, 0.0, 1.0, 0.5, -0.5), (600, 0.0, 1.0, 0.5, 0.9)),
)


@pytest.mark.parametrize("tag,search_args,validation_args", CTX_CASES,
                         ids=[row[0] for row in CTX_CASES])
def test_calibrate_region_context_decision_matches_v1_fit_context(
        tag, search_args, validation_args):
    rng = np.random.default_rng(RECEIVER_SEED + len(tag))
    search = _ctx_population(rng, *search_args)
    validation = _ctx_population(rng, *validation_args)
    validation = (validation[0], validation[1], validation[2],
                  validation[3] + 10 ** 6)
    offsets, adopted, reason, base_loss, cand_loss = h3_cal.context_decision(
        search, validation)
    search_obs = v1_detect.ContextObservations(
        "r", search[0], search[1], search[2].astype(np.uint8), search[3])
    validation_obs = v1_detect.ContextObservations(
        "r", validation[0], validation[1], validation[2].astype(np.uint8),
        validation[3])
    assert eq_arrays(h3_cal.site_weights(search[3]), search_obs.weights)
    assert (h3_cal.unique_class_support(search[2], search[3])
            == search_obs.unique_class_support)
    fit = v1_detect.fit_context(search_obs, validation_obs)
    if fit.eligible:
        expected_base = v1_ctx._binary_logloss(
            validation_obs.baseline_llr, validation_obs.labels,
            validation_obs.weights)
        expected_cand = v1_ctx._binary_logloss(
            validation_obs.baseline_llr
            + fit.offsets[validation_obs.neighbour_count],
            validation_obs.labels, validation_obs.weights)
        expected_adopted = expected_cand < expected_base
        expected_reason = ("adopted" if expected_adopted
                           else "validation_gate_failed")
    else:
        expected_base = expected_cand = None
        expected_adopted = False
        expected_reason = fit.reason
    assert eq_arrays(offsets, fit.offsets)
    assert adopted == expected_adopted
    assert reason == expected_reason
    assert base_loss == expected_base
    assert cand_loss == expected_cand
    if fit.eligible:
        assert bool(np.all(np.diff(offsets) <= 1e-12))


CTX_FLOORS = (
    ("search-total", (40, 0.0, 1.0, 0.5), (300, 0.0, 1.0, 0.5),
     "insufficient_search_support"),
    ("search-class", (300, 0.0, 1.0, 0.02), (300, 0.0, 1.0, 0.5),
     "search_class_starved"),
    ("validation-total", (300, 0.0, 1.0, 0.5), (20, 0.0, 1.0, 0.5),
     "insufficient_validation_support"),
    ("validation-class", (300, 0.0, 1.0, 0.5), (300, 0.0, 1.0, 0.01),
     "validation_class_starved"),
)


@pytest.mark.parametrize("tag,search_args,validation_args,expected",
                         CTX_FLOORS, ids=[row[0] for row in CTX_FLOORS])
def test_calibrate_context_floor_cascade_names_its_reason(
        tag, search_args, validation_args, expected):
    rng = np.random.default_rng(RECEIVER_SEED + 7 + len(tag))
    search = _ctx_population(rng, *search_args)
    validation = _ctx_population(rng, *validation_args)
    validation = (validation[0], validation[1], validation[2],
                  validation[3] + 10 ** 6)
    offsets, adopted, reason, base_loss, cand_loss = h3_cal.context_decision(
        search, validation)
    assert reason == expected
    assert not adopted
    assert base_loss is None and cand_loss is None
    assert not np.any(offsets)


def test_calibrate_empty_context_sides_refuse_with_their_named_reasons():
    rng = np.random.default_rng(RECEIVER_SEED + 8)
    empty = (np.zeros(0, np.float64), np.zeros(0, np.int8), np.zeros(0, bool),
             np.zeros(0, np.int64))
    populated = _ctx_population(rng, 300, 0.0, 1.0, 0.5)
    assert h3_cal.context_decision(empty, populated)[2] == \
        "insufficient_search_support"
    assert h3_cal.context_decision(populated, empty)[2] == \
        "insufficient_validation_support"


def test_calibrate_physical_cell_ids_match_v1_payload_context():
    rows = []
    for start_y, start_x, ny, nx, page in ((10, 20, 12, 15, 0),
                                           (18, 26, 14, 11, 0),
                                           (40, 60, 9, 9, 1)):
        cells = _cell_grid(start_y, start_y + ny, start_x, start_x + nx)
        rows.append(SimpleNamespace(page=page,
                                    page_cells_yx=cells.astype(np.int32)))
    rows = tuple(rows)
    mine = h3_cal.physical_cell_ids(rows)
    theirs = v1_ctx._physical_cell_ids(rows)
    assert len(mine) == len(theirs)
    for a, b in zip(mine, theirs):
        assert eq_arrays(a, b)


REFINE_SHARED_CONSTANTS = (
    "BLOCK_CELLS", "VALIDATION_MODULUS", "MIN_PAYLOAD_TRAIN",
    "MIN_PAYLOAD_VALIDATION", "MIN_TRAIN_PER_CLASS",
    "MIN_VALIDATION_PER_CLASS", "MIN_CERTIFIED_BLOCKS", "MIN_POSE_PILOTS",
    "MIN_HELDOUT_GAIN", "PILOT_MISMATCH_SLACK", "ANGLE_LIMIT_DEG",
    "ANGLE_COARSE_STEP_DEG", "ANGLE_FINE_STEP_DEG", "PHASE_LIMIT_CELLS",
    "PHASE_COARSE_STEP_CELLS", "PHASE_FINE_STEP_CELLS", "POSE_SITE_CAP_TRAIN",
    "POSE_SITE_CAP_VALIDATION")


@pytest.mark.parametrize("name", REFINE_SHARED_CONSTANTS)
def test_refine_constants_agree_across_all_three_trees(name):
    assert (getattr(h3_refine, name) == getattr(v1_certified_refine, name)
            == getattr(h2_refine_fit, name))


def test_refine_private_constants_match_the_frozen_second_copies():
    assert (h3_refine.SCORE_SPREAD_FLOOR == h2_refine_fit.SCORE_SPREAD_FLOOR
            == 1e-6)
    assert (h3_refine.STRIPE_PAGE_COEFFICIENT, h3_refine.STRIPE_Y_COEFFICIENT,
            h3_refine.STRIPE_X_COEFFICIENT) == (104729, 1009, 9177)
    assert (h3_refine.CAP_HASH_Y, h3_refine.CAP_HASH_X) == (
        11400714819323198485, 14029467366897019727)


def _make_labels(seed: int, n: int, page: int = 2):
    rng = np.random.default_rng(seed)
    cells = np.stack([rng.integers(0, 400, n), rng.integers(0, 400, n)],
                     axis=1).astype(np.int64)
    cells = np.unique(cells, axis=0)
    n = cells.shape[0]
    rows = np.arange(n, dtype=np.int64)
    is_pilot = rng.random(n) < 0.35
    values = rng.integers(0, 2, n).astype(np.uint8)
    validation = np.empty(n, bool)
    validation[is_pilot] = np.asarray(
        (cells[is_pilot, 0] * 131 + cells[is_pilot, 1] * 17) & 1, bool)
    validation[~is_pilot] = v1_certified_refine._block_validation(
        page, cells[~is_pilot])
    block_ids = (is_pilot.astype(np.int64) * 10 ** 12 + page * 10 ** 9
                 + (cells[:, 0] // 16) * 10 ** 4 + cells[:, 1] // 16)
    weights = np.zeros(n, np.float64)
    weights[~validation] = v1_certified_refine._block_weights(
        block_ids[~validation])
    weights[validation] = v1_certified_refine._block_weights(
        block_ids[validation])
    mine = h3_refine.SegmentLabels(rows, cells, values, validation, weights,
                                   is_pilot, block_ids)
    holo2_labels = h2_refine_fit.SegmentLabels(rows, cells, values, validation,
                                               weights, is_pilot, block_ids)
    v1_labels = v1_certified_refine.SegmentLabels(
        rows, cells, values, validation, weights, is_pilot, block_ids,
        tuple(None if pilot else "a" * 64 for pilot in is_pilot))
    return mine, holo2_labels, v1_labels


def test_refine_block_kernels_match_v1_and_holo2():
    rng = np.random.default_rng(7)
    cells = np.stack([rng.integers(0, 3000, 5000),
                      rng.integers(0, 3000, 5000)], axis=1).astype(np.int64)
    for page in (0, 1, 5, 17):
        mine = h3_refine.block_validation(page, cells)
        assert eq_arrays(mine, v1_certified_refine._block_validation(page,
                                                                     cells))
        assert eq_arrays(mine, h2_refine_fit.block_validation(page, cells))
    ids = rng.integers(0, 40, 4000).astype(np.int64)
    assert eq_arrays(h3_refine.block_weights(ids),
                     v1_certified_refine._block_weights(ids))
    assert eq_arrays(h3_refine.block_weights(ids),
                     h2_refine_fit.block_weights(ids))
    empty = np.zeros(0, np.int64)
    assert eq_arrays(h3_refine.block_weights(empty),
                     v1_certified_refine._block_weights(empty))


def test_refine_support_metrics_and_caps_match_v1_and_holo2():
    mine, holo2_labels, v1_labels = _make_labels(11, 6000)
    assert (h3_refine.support_metrics(mine)
            == v1_certified_refine._support_metrics(v1_labels)
            == h2_refine_fit.support_metrics(holo2_labels))
    for starved_n in (40, 200, 900):
        small, small2, small1 = _make_labels(starved_n, starved_n)
        assert (h3_refine.support_metrics(small)
                == v1_certified_refine._support_metrics(small1)
                == h2_refine_fit.support_metrics(small2))
    positions = np.flatnonzero(~mine.is_pilot)
    for cap in (0, 10, 500, positions.size, positions.size + 5):
        got = h3_refine.deterministic_cap(positions, mine.page_cells_yx, cap)
        assert eq_arrays(got, v1_certified_refine._deterministic_cap(
            positions, v1_labels, cap))
        assert eq_arrays(got, h2_refine_fit.deterministic_cap(
            positions, holo2_labels.page_cells_yx, cap))
    for validation in (False, True):
        got = h3_refine.select_pose_sites(mine, validation)
        assert eq_arrays(got, v1_certified_refine.select_pose_sites(
            v1_labels, validation))
        assert eq_arrays(got, h2_refine_fit.select_pose_sites(holo2_labels,
                                                              validation))


def test_refine_pose_candidate_matches_v1_and_holo2_pose_models():
    jacobian = ((6.9931, 0.0812), (-0.0812, 6.9931))
    matrix = np.asarray(jacobian, np.float64)
    base = h3_refine.LocalPose(
        (13.25, -7.5), jacobian, (0.5, 0.75),
        0.5 * (float(np.hypot(*matrix[:, 0])) + float(np.hypot(*matrix[:, 1]))),
        float(np.degrees(np.arctan2(matrix[0, 1], matrix[1, 1]))))
    holo2_base = h2_place_model.AffinePose(base.origin_yx, base.jacobian_yx,
                                           base.phase_yx, base.pitch_px,
                                           base.angle_deg)
    v1_base = v1_place_model.AffinePose(base.origin_yx, base.jacobian_yx,
                                        base.phase_yx, base.pitch_px,
                                        base.angle_deg)
    for key in ((0.0, 0.0, 0.0), (0.15, -0.25, 0.0625),
                (-0.05, 0.125, -0.1875), (0.0333, -0.0001, 0.2499)):
        mine = h3_refine.pose_candidate(base, *key)
        holo2_pose = h2_refine_fit.pose_candidate(holo2_base, *key)
        v1_pose = v1_certified_refine._pose_candidate(v1_base, *key)
        assert (mine.origin_yx == holo2_pose.origin_yx == v1_pose.origin_yx)
        assert (mine.jacobian_yx == holo2_pose.jacobian_yx
                == v1_pose.jacobian_yx)
        assert mine.phase_yx == holo2_pose.phase_yx == v1_pose.phase_yx
        assert mine.pitch_px == holo2_pose.pitch_px == v1_pose.pitch_px
        assert mine.angle_deg == holo2_pose.angle_deg == v1_pose.angle_deg
    assert h3_refine.pose_candidate(base, 0.0, 0.0, 0.0) == base


def test_refine_objectives_match_v1_and_holo2():
    rng = np.random.default_rng(RECEIVER_SEED + 9)
    means = rng.normal(180.0, 40.0, 3000)
    values = rng.integers(0, 2, 3000).astype(np.uint8)
    weights = rng.random(3000) + 0.1
    assert (h3_refine.pose_objective(means, values, weights)
            == v1_certified_refine._pose_objective(means, values, weights)
            == h2_refine_fit.pose_objective(means, values, weights))
    zeros = np.zeros(3000, np.uint8)
    assert (h3_refine.pose_objective(means, zeros, weights)
            == v1_certified_refine._pose_objective(means, zeros, weights)
            == -np.inf)
    logits = rng.normal(0.0, 4.0, 3000)
    assert (h3_refine.weighted_logloss(logits, values, weights)
            == v1_certified_refine._weighted_logloss(logits, values, weights)
            == h2_refine_fit.weighted_logloss(logits, values, weights))


def test_refine_search_grid_and_tie_break_match_holo2():
    assert h3_refine.candidate_grid() == h2_refine_fit.candidate_grid()
    assert (0.0, 0.0, 0.0) in h3_refine.candidate_grid()
    assert len(h3_refine.candidate_grid()) == 27
    for coarse in h3_refine.candidate_grid():
        assert h3_refine.fine_grid(coarse) == h2_refine_fit.fine_grid(coarse)
    keys = h3_refine.candidate_grid()
    for trial in range(5):
        rng = np.random.default_rng(100 + trial)
        table = {key: (float(rng.normal()), float(rng.normal()))
                 for key in keys}
        tied = dict(table)
        for key in keys[:4]:
            tied[key] = (2.5, table[key][1])
        for candidates in (table, tied):
            assert (h3_refine.select_best(candidates, keys)
                    == h2_refine_fit.select_best(candidates, keys))


def test_refine_adoption_gate_matches_v1_and_every_clause_binds():
    for a in (0.0, 0.1, -0.2):
        for b in (0.0, 0.005, -0.006):
            for c in (0.0, 0.004, 0.006):
                assert (h3_refine.adoption_gate(1.0, 1.0 - a, 0.1, 0.1 + b,
                                                0.2, 0.2 + c)
                        == v1_certified_refine._adoption_gate(
                            1.0, 1.0 - a, 0.1, 0.1 + b, 0.2, 0.2 + c))
    assert not h3_refine.adoption_gate(1.0, 1.0 - 1e-5, 0.1, 0.1, 0.2, 0.2)
    assert not h3_refine.adoption_gate(1.0, 0.5, 0.1, 0.1051, 0.2, 0.2)
    assert not h3_refine.adoption_gate(1.0, 0.5, 0.1, 0.1, 0.2, 0.2051)
    assert h3_refine.adoption_gate(1.0, 0.5, 0.1, 0.1049, 0.2, 0.2049)


class _ReferenceProvider:

    def __init__(self, page_object) -> None:
        self._page = page_object

    def page(self, page: int):
        return self._page


def test_refine_collect_labels_matches_holo2_reference_join():
    rng = np.random.default_rng(3)
    page = 3
    height, width = 256, 256
    base_sites = rng.random((height, width)) < 0.03
    base_values = rng.integers(0, 2, (height, width)).astype(np.uint8)
    certified = {(0, 0), (1, 2), (2, 1), (3, 3), (0, 2)}
    printed = {(page, ty, tx): rng.integers(0, 2, (64, 64), dtype=np.uint8)
               for ty, tx in certified}
    cargo_mask = np.zeros((height, width), bool)
    rich_values = base_values.copy()
    for ty, tx in certified:
        y0, x0 = ty * 64, tx * 64
        block = np.ones((64, 64), bool)
        block &= ~base_sites[y0:y0 + 64, x0:x0 + 64]
        cargo_mask[y0:y0 + 64, x0:x0 + 64] = block
        target = rich_values[y0:y0 + 64, x0:x0 + 64]
        target[block] = printed[(page, ty, tx)][block]
    rich_sites = base_sites | cargo_mask
    cells = _cell_grid(30, 230, 20, 220)
    reference = np.where(base_sites[cells[:, 0], cells[:, 1]],
                         base_values[cells[:, 0], cells[:, 1]].astype(np.int8),
                         np.int8(-1))
    mine = h3_refine.collect_labels(page, cells, reference, printed)
    theirs = h2_refine_fit.collect_labels(
        page, cells,
        _ReferenceProvider(h2_reference.ReferencePage(page, base_values,
                                                      base_sites)),
        _ReferenceProvider(h2_reference.ReferencePage(page, rich_values,
                                                      rich_sites)))
    for field in ("rows", "page_cells_yx", "values", "validation", "weights",
                  "is_pilot", "block_ids"):
        assert eq_arrays(getattr(mine, field), getattr(theirs, field)), field
    assert bool((mine.weights > 0).all())
    assert mine.is_pilot.any() and (~mine.is_pilot).any()
    assert 0.2 < float(np.mean(mine.validation[~mine.is_pilot])) < 0.3
    pilots_only = h3_refine.collect_labels(page, cells, reference, {})
    assert not (~pilots_only.is_pilot).any()


_STATE_BITS = (np.arange(8)[:, None] >> np.arange(3)[None, :]) & 1


def _gen_features(states: np.ndarray, rng: np.random.Generator,
                  noise: float = 0.06,
                  collapse_pair: tuple[int, int] | None = None) -> np.ndarray:
    bits = _STATE_BITS[states % 8].astype(np.float64)
    means = 0.9 - 0.55 * bits
    if collapse_pair is not None:
        source, target = collapse_pair
        means[states == target] = 0.9 - 0.55 * _STATE_BITS[source].astype(
            np.float64)
    return means + rng.normal(0.0, noise, (states.size, 3))


def test_color_blind_component_bits_match_v1_color_detect():
    rng = np.random.default_rng(RECEIVER_SEED)
    shapes = ((40, 3), (200,), (64, 6), (25, 25), (300, 3), (12, 2))
    for trial, shape in enumerate(shapes):
        means = rng.uniform(0.0, 1.0, shape)
        if trial == 3:
            means = np.round(means, 1)
        mine_bits, mine_llr = h3_cm.blind_component_bits(means)
        v1_bits, v1_llr = v1_color_detect.blind_component_bits(means)
        assert eq_arrays(mine_bits, v1_bits)
        assert eq_arrays(mine_llr, v1_llr)
        assert mine_bits.dtype == np.uint8 and mine_llr.dtype == np.float64
    assert (h3_cm.BLIND_CONFIDENT_LLR
            == v1_color_detect.BLIND_CONFIDENT_LLR)


def _compare_qda(rng: np.random.Generator, x: np.ndarray, y: np.ndarray,
                 n_states: int):
    mine = h3_cm.fit_qda(x, y, n_states)
    theirs = v1_color_detect.fit_equal_prior_qda(x, y, n_states=n_states)
    assert eq_arrays(mine.means, theirs.means)
    for state in range(n_states):
        assert eq_arrays(mine.cholesky[state], theirs.cholesky[state])
    assert eq_arrays(mine.log_determinants, theirs.log_determinants)
    assert eq_arrays(mine.class_counts, theirs.class_counts)
    assert mine.clipped_planes == theirs.clipped_planes
    assert mine.degenerate == theirs.degenerate
    probe = _gen_features(rng.integers(0, n_states, 120), rng)
    assert eq_arrays(h3_cm.qda_log_scores(mine, probe),
                     v1_color_detect.qda_log_scores(theirs, probe))
    if n_states == 7:
        assert eq_arrays(h3_cm.cmy7_relative_scores(mine, probe),
                         v1_color_detect.cmy7_relative_scores(theirs, probe))
    else:
        raw = rng.normal(0.0, 4.0, (90, 8))
        assert eq_arrays(h3_cm.cmy8_marginal_llrs(raw),
                         v1_color_detect.cmy8_marginal_llrs(raw))
        assert eq_arrays(h3_cm.cmy8_raw_llrs(mine, probe),
                         v1_color_detect.cmy8_raw_llrs(theirs, probe))
    return mine


def test_color_qda_fit_and_scores_match_v1_color_detect():
    rng = np.random.default_rng(RECEIVER_SEED)
    for trial in range(_n(4, 10)):
        n_states = 7 if trial % 2 == 0 else 8
        n = int(rng.integers(60, 400))
        y = rng.integers(0, n_states, n)
        y[:n_states] = np.arange(n_states)
        _compare_qda(rng, _gen_features(y, rng), y, n_states)


def test_color_qda_degenerate_and_collapsed_paths_match_v1():
    rng = np.random.default_rng(RECEIVER_SEED + 1)
    n_degenerate = 0
    for trial, missing in enumerate(((3,), (0, 5), (6,))):
        n_states = 8 if trial != 1 else 7
        allowed = np.setdiff1d(np.arange(n_states), np.asarray(missing))
        y = rng.choice(allowed, 160)
        mine = _compare_qda(rng, _gen_features(y, rng), y, n_states)
        n_degenerate += bool(mine.degenerate)
    assert n_degenerate == 3
    n_clipped = 0
    for pair in ((1, 5), (2, 6), (0, 4)):
        y = rng.integers(0, 8, 240)
        y[:8] = np.arange(8)
        mine = _compare_qda(rng, _gen_features(y, rng, noise=0.03,
                                               collapse_pair=pair), y, 8)
        n_clipped += bool(mine.clipped_planes)
    assert n_clipped >= 2


def test_color_component_pava_matches_v1_color_detect():
    rng = np.random.default_rng(RECEIVER_SEED + 2)
    cases = []
    for trial in range(_n(4, 10)):
        n = int(rng.integers(12, 300))
        labels = rng.integers(0, 2, n)
        labels[:2] = (0, 1)
        scores = rng.normal(0.0, 3.0, n) + 2.5 * (labels - 0.5)
        if trial % 3 == 1:
            scores = np.round(scores, 1)
        cases.append((scores, labels))
    cases.append((np.asarray([-2.0, -1.0, 1.0, 2.0]),
                  np.asarray([0, 0, 1, 1])))
    cases.append((np.asarray([-1.0, 0.5, 0.5, 2.0, 3.0]),
                  np.asarray([1, 0, 1, 0, 0])))
    for scores, labels in cases:
        mine = h3_cm.fit_component_pava(scores, labels)
        theirs = v1_color_detect.fit_component_pava(scores, labels)
        assert eq_arrays(mine.score_nodes, theirs.score_nodes)
        assert eq_arrays(mine.probability_nodes, theirs.probability_nodes)
        assert mine.n_labels == theirs.n_labels
        probe = rng.normal(0.0, 5.0, 200)
        assert eq_arrays(mine.llrs(probe), theirs.llrs(probe))
    anchored = h3_cm.fit_component_pava(np.asarray([-2.0, -1.0, 1.0, 2.0]),
                                        np.asarray([0, 0, 1, 1]))
    assert np.any(anchored.score_nodes == 0.0)
    assert np.any(anchored.probability_nodes == 0.5)
    assert eq_arrays(h3_cm.neutral_pava_map(30).llrs(rng.normal(0, 5, 50)),
                     np.zeros(50))


def test_color_cmy8_support_qualification_matches_v1_color_detect():
    rng = np.random.default_rng(RECEIVER_SEED + 3)
    populations = [rng.integers(0, 8, int(rng.integers(8, 80)))
                   for _ in range(_n(4, 8))]
    populations += [np.full(40, 7), rng.choice((1, 3, 5, 7), 48),
                    rng.choice((0, 7), 60),
                    np.tile(np.asarray((1, 2, 4, 5, 6, 7)), 3)]
    for states in populations:
        supported, reasons = h3_cm.qualify_cmy8_support(states)
        theirs = v1_color_detect.qualify_cmy8_calibration_support(states)
        assert supported == tuple(theirs.supported_planes)
        assert reasons == tuple(theirs.unsupported_reasons)


def test_color_newton_head_solver_matches_v1_color_calibration():
    rng = np.random.default_rng(RECEIVER_SEED + 4)
    for _ in range(_n(6, 25)):
        n = int(rng.integers(80, 400))
        states = rng.integers(0, 7, n)
        states[:7] = np.arange(7)
        base = rng.normal(0.0, 3.0, (7, 6))
        scores = base[states] + rng.normal(0.0, 1.5, (n, 6))
        weights = v1_color_cal.class_balanced_weights(states)
        mine_scale, mine_offsets, mine_iters = h3_cm._newton(scores, states,
                                                             weights)
        v1_scale, v1_offsets, v1_iters = v1_color_cal._newton(scores, states,
                                                              weights)
        assert mine_scale == v1_scale
        assert eq_arrays(mine_offsets, v1_offsets)
        assert mine_iters == v1_iters


def test_color_class_balanced_weights_match_v1_color_calibration():
    rng = np.random.default_rng(RECEIVER_SEED + 5)
    for _ in range(_n(4, 10)):
        labels = rng.integers(0, 7, int(rng.integers(5, 200)))
        assert eq_arrays(h3_pava.class_balanced_weights(labels),
                         v1_color_cal.class_balanced_weights(labels))
    single = np.full(30, 4)
    assert eq_arrays(h3_pava.class_balanced_weights(single),
                     v1_color_cal.class_balanced_weights(single))


def test_color_head_sub_split_matches_v1_color_calibration():
    rng = np.random.default_rng(RECEIVER_SEED + 6)
    keys = np.column_stack((rng.integers(0, 4, 500),
                            rng.integers(0, 5000, 500),
                            rng.integers(0, 5000, 500))).astype(np.int64)
    assert eq_arrays(h3_cm.head_sub_split(keys),
                     v1_color_cal.head_sub_split(keys))


COLOR_REFINE_SHARED = ("BLOCK_CELLS", "MIN_CERTIFIED_BLOCKS",
                       "MIN_HELDOUT_GAIN", "MIN_PAYLOAD_TRAIN",
                       "MIN_PAYLOAD_VALIDATION", "MIN_POSE_PILOTS",
                       "MIN_TRAIN_PER_CLASS", "MIN_VALIDATION_PER_CLASS",
                       "POSE_SITE_CAP_TRAIN", "POSE_SITE_CAP_VALIDATION")


@pytest.mark.parametrize("name", COLOR_REFINE_SHARED)
def test_color_refine_floors_match_the_v1_colour_namespace(name):
    assert getattr(h3_color_refine, name) == getattr(v1_color_refine, name)


def test_color_refine_private_constants_match_v1():
    assert (h3_color_refine.FURNITURE_LOSS_SLACK
            == v1_color_refine.FURNITURE_LOSS_SLACK == 1e-9)
    assert np.uint64(h3_color_refine.PLANE_TOKEN_MIX) == \
        v1_color_refine._PLANE_TOKEN_MIX
    for name in ("ANGLE_LIMIT_DEG", "ANGLE_COARSE_STEP_DEG",
                 "ANGLE_FINE_STEP_DEG", "PHASE_LIMIT_CELLS",
                 "PHASE_COARSE_STEP_CELLS", "PHASE_FINE_STEP_CELLS"):
        assert getattr(h3_refine, name) == getattr(v1_color_refine, name), name
    assert h3_color_refine.SCORE_SPREAD_FLOOR == 1e-6
    assert (h3_color_refine.CAP_HASH_Y, h3_color_refine.CAP_HASH_X) == (
        11400714819323198485, 14029467366897019727)


def _evidence_from_dense(capture_id: str, page: int, ty: int, tx: int,
                         values: np.ndarray,
                         observed: np.ndarray) -> h3_tiles.TileCut:
    flat = np.flatnonzero(observed).astype(np.uint16)
    return h3_tiles.TileCut(capture_id, 0, page, ty, tx,
                            np.asarray(values[flat], np.float32), flat)


def _cells_to_llr(cells: np.ndarray) -> np.ndarray:
    return ((2.0 * cells.astype(np.float64) - 1.0) * MAG).reshape(-1, 1)


def _sim_k_page():
    rng = np.random.default_rng(RECEIVER_SEED)
    row = h3_resolve(SIM_K_REF)
    geometry = build_site_geometry(row)
    spec = v1_resolve(SIM_K_REF)
    n_tiles = row.tiles_per_page
    symbol_bits = row.streams[0].symbol_bits
    k_total = 137
    symbols = rng.integers(0, 2, (n_tiles, symbol_bits), dtype=np.uint8)
    page_cells = v1_compose.compose_page_cells(spec, 0, symbols, k_total)
    counters = np.asarray([row.tile_counter(0, ty, tx)
                           for ty in range(row.tiles_yx[0])
                           for tx in range(row.tiles_yx[1])], np.int64)
    meta_bits = v1_metadata.tile_bits(
        v1_metadata.encode_metadata(0, k_total), counters)
    truth = {}
    for index in range(counters.size):
        ty, tx = divmod(index, row.tiles_yx[1])
        truth[(ty, tx)] = np.concatenate(
            (np.asarray([meta_bits[index]], np.uint8), symbols[index]))
    return row, geometry, spec, page_cells, counters, truth


def test_printed_cells_for_reproduces_the_v1_emitted_page_slice():
    row, geometry, spec, page_cells, _counters, truth = _sim_k_page()
    assert row.seed == spec.seed
    assert row.streams[0].user_bits == spec.tile_user_bits
    for (ty, tx), user in truth.items():
        field = h3_tiles.printed_cells_for(row, geometry, 0, ty, tx, user)
        assert np.array_equal(
            field, page_cells[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64])


def test_printed_cells_for_matches_the_v1_reencoder_and_refuses_a_fork():
    row, geometry, _spec, _page_cells, counters, truth = _sim_k_page()
    ty, tx = 3, 4
    user = truth[(ty, tx)]
    counter = int(counters[ty * row.tiles_yx[1] + tx])
    spec = v1_resolve(SIM_K_REF)
    assert np.array_equal(
        v1_tiles._reencode_printed_cells(spec, counter, 0, ty, tx, user,
                                         int(geometry.slot_a[counter]),
                                         int(geometry.slot_b[counter])),
        h3_tiles.printed_cells_for(row, geometry, 0, ty, tx, user))
    forked = SiteGeometry(
        geometry.word_cells_yx, geometry.extra_cells_yx,
        h3_pilots.site_cell_indices(v1_fossils.FAMILY_SEED_P120, 0),
        geometry.payload_flat, geometry.slot_a, geometry.slot_b)
    with pytest.raises(IntegrityError):
        h3_tiles.printed_cells_for(row, forked, 0, ty, tx, user)


def test_k_tile_attempts_match_the_v1_attempt_records():
    rng = np.random.default_rng(RECEIVER_SEED + 11)
    row, geometry, spec, page_cells, _counters, truth = _sim_k_page()
    ty, tx = 3, 4
    user = truth[(ty, tx)]
    tile_cells = page_cells[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
    values = _cells_to_llr(tile_cells)
    observed = np.ones(4096, bool)
    block = _evidence_from_dense("sha-a", 0, ty, tx, values, observed)
    result = h3_tiles.attempt_tile(row, geometry, (block,), "main",
                                   h3_tiles.STAGE_SCAN)
    assert result.fact.outcome == h3_tiles.OUTCOME_CERTIFIED
    assert np.array_equal(result.certificate.user_bits, user)
    assert result.certificate.source == "tiles/scan"
    assert result.fact.n_informative == 4096 - row.n_sites
    record, cert = attempt_k_tile(
        values[:, 0].reshape(64, 64), spec, (0, ty, tx), AttemptStage.SCAN,
        source_sha256="a" * 64, lane_id="lane",
        component_block_ids=("b" * 64,))
    assert (record.state is AttemptState.CERTIFIED) == (
        result.fact.outcome == h3_tiles.OUTCOME_CERTIFIED)
    assert record.n_informative == result.fact.n_informative
    assert record.n_iters == result.fact.n_iters
    v1_user = np.unpackbits(np.frombuffer(cert.packed_user_bits, np.uint8),
                            bitorder="little")[:row.streams[0].user_bits]
    assert np.array_equal(v1_user, result.certificate.user_bits)

    noisy = values.copy()
    noisy[rng.choice(4096, 60, replace=False)] *= -1.0
    noisy_result = h3_tiles.attempt_tile(
        row, geometry, (_evidence_from_dense("sha-a", 0, ty, tx, noisy,
                                             observed),), "main",
        h3_tiles.STAGE_SCAN)
    assert noisy_result.fact.outcome == h3_tiles.OUTCOME_CERTIFIED
    assert np.array_equal(noisy_result.certificate.user_bits, user)
    v1_noisy, _ = attempt_k_tile(
        noisy[:, 0].reshape(64, 64), spec, (0, ty, tx), AttemptStage.SCAN,
        source_sha256="a" * 64, lane_id="lane",
        component_block_ids=("b" * 64,))
    assert v1_noisy.n_iters == noisy_result.fact.n_iters

    broken = values.copy()
    broken[rng.choice(4096, 1400, replace=False)] *= -1.0
    broken_block = _evidence_from_dense("sha-a", 0, ty, tx, broken, observed)
    broken_result = h3_tiles.attempt_tile(row, geometry, (broken_block,),
                                          "main", h3_tiles.STAGE_SCAN)
    assert broken_result.fact.outcome == h3_tiles.OUTCOME_FAILED
    assert broken_result.certificate is None
    assert not (broken_result.fact.syndrome_ok and broken_result.fact.crc_ok)
    assert h3_tiles.arms_retry(broken_result.fact, certified=False)
    retry = h3_tiles.attempt_tile(row, geometry, (broken_block,), "main",
                                  h3_tiles.STAGE_RETRY150)
    assert h3_tiles.max_iters_for(h3_tiles.STAGE_RETRY150) == 150
    v1_retry, _ = attempt_k_tile(
        broken[:, 0].reshape(64, 64), spec, (0, ty, tx),
        AttemptStage.RETRY150, source_sha256="a" * 64, lane_id="lane",
        component_block_ids=("b" * 64,))
    assert v1_retry.n_iters == retry.fact.n_iters
    assert (v1_retry.state is AttemptState.CERTIFIED) == (
        retry.fact.outcome == h3_tiles.OUTCOME_CERTIFIED)


def test_below_attempt_floor_matches_the_v1_refusal_and_never_arms_retry():
    row, geometry, spec, page_cells, _counters, truth = _sim_k_page()
    ty, tx = 3, 4
    values = _cells_to_llr(page_cells[ty * 64:(ty + 1) * 64,
                                      tx * 64:(tx + 1) * 64])
    k_eff = h3_tiles.k_eff_bits(row)
    assert k_eff == v1_tiles.k_eff_bits(spec)
    keep = np.zeros(4096, bool)
    non_site = np.setdiff1d(np.arange(4096),
                            np.asarray(geometry.shorten_flat, np.int64))
    keep[non_site[:k_eff - 1]] = True
    starved = h3_tiles.attempt_tile(
        row, geometry, (_evidence_from_dense("sha-a", 0, ty, tx, values,
                                             keep),), "main",
        h3_tiles.STAGE_SCAN)
    assert starved.fact.outcome == h3_tiles.OUTCOME_BELOW_FLOOR
    assert starved.fact.n_iters == 0
    assert starved.fact.syndrome_ok is None
    assert starved.fact.crc_ok is None
    assert not h3_tiles.arms_retry(starved.fact, certified=False)
    v1_starved, _ = attempt_k_tile(
        (values[:, 0] * keep).reshape(64, 64), spec, (0, ty, tx),
        AttemptStage.SCAN, source_sha256="a" * 64, lane_id="lane",
        component_block_ids=("b" * 64,))
    assert v1_starved.state is AttemptState.BELOW_ATTEMPT_FLOOR
    assert v1_starved.n_informative == starved.fact.n_informative


def test_conflicting_certificate_mint_raises_integrity_error():
    bits_a = np.zeros(8, np.uint8)
    bits_b = bits_a.copy()
    bits_b[3] = 1
    certs: dict = {}
    h3_tiles.merge_certificate(certs, Certificate(0, 1, 2, "main", bits_a,
                                                  "tiles/scan"))
    h3_tiles.merge_certificate(certs, Certificate(0, 1, 2, "main", bits_a,
                                                  "tiles/union"))
    assert len(certs) == 1
    assert certs[(0, 1, 2, "main")].source == "tiles/scan"
    with pytest.raises(IntegrityError):
        h3_tiles.merge_certificate(certs, Certificate(0, 1, 2, "main", bits_b,
                                                      "tiles/union"))


# ------------------------------------------------------------------------
# The supplemental arms A3 and A4b (RECEIVE-DESIGN §6.2a). These pin the
# PORTED NUMERICS against the v1 fitters they came from: policy tokens
# winphot-gainoffset-adaptivehalo-shrink20 and
# knownfield-conditioned-marginals-ulane-only. A mismatch here is a
# ported-constant fork, never a test to update.
# ------------------------------------------------------------------------

A3_CONSTANT_NAMES = (
    "WINDOW_PHOT_PRIOR_LABELS", "WINDOW_PHOT_HALO_POOL_WEIGHT",
    "WINDOW_PHOT_MIN_SEARCH_LABELS", "WINDOW_PHOT_MIN_STATES",
    "WINDOW_PHOT_MIN_HELDOUT", "WINDOW_PHOT_GATE_SLACK",
    "WINDOW_PHOT_MIN_VARIANCE", "REASON_ADOPTED", "REASON_SEARCH_STARVED",
    "REASON_STATE_SUPPORT", "REASON_HELDOUT_STARVED", "REASON_GATE_FAILED",
    "REASON_NO_WINDOW_MAPS", "REASON_REGION_GATE_FAILED")

A4B_CONSTANT_NAMES = (
    "CONDITIONING_REVEAL_MASK", "CONDITIONING_REVEAL_SHIFT",
    "CONDITIONING_N_PATTERNS", "CONDITIONED_MIN_CLASS_LABELS",
    "CONDITIONED_MIN_LABELS", "CONDITIONED_MIN_VALIDATION",
    "CONDITIONED_MAX_LABELS", "CONDITIONING_MAX_CERT_CELLS",
    "CONDITIONING_NLL_UNMEASURED", "CONDITIONING_REASON_ADOPTED",
    "CONDITIONING_REASON_STARVED", "CONDITIONING_REASON_HELDOUT_STARVED",
    "CONDITIONING_REASON_GATE_FAILED", "CONDITIONING_REASON_NO_STRATUM",
    "CONDITIONING_REASON_NO_CELLS", "CONDITIONING_REASON_UNSUPPORTED",
    "CONDITIONING_REASON_REGION_FORCED")


def test_a3_constants_match_v1_color_locality():
    v1_locality = pytest.importorskip("holo.receive.color_locality")
    for name in A3_CONSTANT_NAMES:
        assert getattr(h3_photometry, name) == getattr(v1_locality, name), (
            f"{name} forked from its v1 policy value")


def test_a4b_constants_match_v1_color_conditioning():
    v1_conditioning = pytest.importorskip("holo.receive.color_conditioning")
    for name in A4B_CONSTANT_NAMES:
        assert getattr(h3_conditioning, name) == getattr(
            v1_conditioning, name), f"{name} forked from its v1 policy value"
    assert h3_conditioning.CMY8_SIBLINGS == v1_color_detect.CMY8_SIBLINGS


def test_a3_balanced_base_weights_match_v1_color_locality():
    v1_locality = pytest.importorskip("holo.receive.color_locality")
    rng = np.random.default_rng(RECEIVER_SEED + 11)
    for _ in range(_n(6, 30)):
        n = int(rng.integers(60, 400))
        states = rng.integers(0, 8, n)
        states[:8] = np.arange(8)
        base = rng.choice((1.0, 0.25, 0.5), n)
        assert eq_arrays(h3_photometry.balanced_base_weights(states, base),
                         v1_locality.balanced_base_weights(states, base))


def test_a3_weighted_affine_matches_v1_color_locality():
    v1_locality = pytest.importorskip("holo.receive.color_locality")
    rng = np.random.default_rng(RECEIVER_SEED + 12)
    for _ in range(_n(6, 30)):
        n = int(rng.integers(60, 400))
        features = rng.normal(0.8, 0.15, (n, 3))
        targets = rng.normal(0.8, 0.15, (n, 3))
        weights = rng.random(n)
        if trial_flat := bool(rng.integers(0, 2)):
            features[:, 1] = 0.5           # the pure-offset limit
        mine = h3_photometry.weighted_affine(features, targets, weights)
        theirs = v1_locality._weighted_affine(features, targets, weights)
        assert eq_arrays(mine[0], theirs[0]), trial_flat
        assert eq_arrays(mine[1], theirs[1])


def test_a4b_masking_and_pattern_kernels_match_v1_color_conditioning():
    v1_conditioning = pytest.importorskip("holo.receive.color_conditioning")
    cells = np.stack(np.meshgrid(np.arange(64), np.arange(64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    assert eq_arrays(h3_conditioning.masking_reveal_codes(cells),
                     v1_conditioning.masking_reveal_codes(cells))
    rng = np.random.default_rng(RECEIVER_SEED + 13)
    mask = rng.integers(0, 2, (512, 3)).astype(bool)
    assert eq_arrays(h3_conditioning.conditioning_pattern_codes(mask),
                     v1_conditioning.conditioning_pattern_codes(mask))
    codes = rng.integers(0, 4, 512)
    for plane in range(3):
        assert eq_arrays(h3_conditioning.pattern_view_mask(plane, codes),
                         v1_conditioning.pattern_view_mask(plane, codes))


def test_a4b_sibling_subset_marginals_match_v1_color_detect():
    rng = np.random.default_rng(RECEIVER_SEED + 14)
    for _ in range(_n(6, 30)):
        n = int(rng.integers(40, 300))
        scores = rng.normal(0.0, 2.5, (n, 8))
        mask = rng.integers(0, 2, (n, 3)).astype(bool)
        bits = rng.integers(0, 2, (n, 3)).astype(np.uint8)
        assert eq_arrays(
            h3_conditioning.cmy8_conditioned_marginal_llrs(scores, mask,
                                                           bits),
            v1_color_detect.cmy8_marginal_llrs(scores, mask, bits))
        for plane in range(3):
            allowed = v1_color_detect.cmy8_sibling_allowed(plane, mask, bits)
            assert eq_arrays(
                h3_conditioning.cmy8_sibling_allowed(plane, mask, bits),
                allowed)
            assert eq_arrays(
                h3_conditioning.cmy8_plane_marginal(scores, plane, allowed),
                v1_color_detect.cmy8_plane_marginal(scores, plane, allowed))
