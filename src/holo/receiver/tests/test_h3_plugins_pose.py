from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from holo.receiver.format.identity import resolve_format_ref
from holo.receiver.lib import geometry
from holo.receiver.plugins import place, pose, words
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_pose_tolerance_row_is_frozen`.

LATTICE_PITCH_PX = 7.83
LATTICE_ANGLE_DEG = 0.4
LATTICE_ORIGIN_YX = (12.3, 9.7)
LATTICE_SHAPE_PX = (900, 900)
LATTICE_BITS_SEED = 20260829
LATTICE_NOISE_SEED = 7
WINDOW_ORIGIN_YX = (40, 52)
WINDOW_CELLS_YX = (80, 80)

PITCH_RECOVERY_TOL_PX = 0.02
ANGLE_RECOVERY_TOL_DEG = 0.05
ORIGIN_RECOVERY_TOL_PX = 1.0

TINY_ROW = "c3-k-r0550@2x2"


def test_pose_tolerance_row_is_frozen():
    _h3_support.assert_measured("PITCH_TOLERANCE", pose.PITCH_TOLERANCE, 0.06)
    _h3_support.assert_measured("SHEAR_TOLERANCE_DEG",
                               pose.SHEAR_TOLERANCE_DEG, 3.0)
    _h3_support.assert_measured("APERTURE_CELLS", pose.APERTURE_CELLS, 0.7)
    _h3_support.assert_measured("PHASE_STEP_CELLS", pose.PHASE_STEP_CELLS,
                               0.125)
    _h3_support.assert_measured("MIN_SPECTRAL_PERIODS",
                               pose.MIN_SPECTRAL_PERIODS, 12)
    _h3_support.assert_measured("SUBDIVISION_MAX_DEPTH",
                               pose.SUBDIVISION_MAX_DEPTH, 1)
    _h3_support.assert_measured("MIN_WINDOW_CELLS", pose.MIN_WINDOW_CELLS, 70)
    _h3_support.assert_measured("WHOLE_WORD_PARITY", pose.WHOLE_WORD_PARITY, 2)
    _h3_support.assert_measured(
        "audit row",
        (pose.AUDIT_MIN_SITES, pose.AUDIT_BAD, pose.AUDIT_GOOD,
         pose.AUDIT_POST_BAR), (15, 0.35, 0.20, 0.25))


@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
def test_rotation_affine_composed_with_its_inverse_is_the_identity(rot_k):
    shape = (37, 53)
    rotated_shape = shape if rot_k % 2 == 0 else shape[::-1]
    rotation, translation = pose.rotation_affine(rot_k, shape)
    inverse_rotation, inverse_translation = pose.rotation_affine(
        (4 - rot_k) % 4, rotated_shape)
    points = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                  indexing="ij"), axis=-1).reshape(-1, 2)
    forward = points @ rotation.T + translation
    back = forward @ inverse_rotation.T + inverse_translation
    assert np.array_equal(back, points.astype(np.float64))


@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
def test_rotation_affine_agrees_with_the_lib_rotated_points(rot_k):
    shape = (9, 13)
    points = np.stack(np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                                  indexing="ij"), axis=-1).reshape(-1, 2)
    rotation, translation = pose.rotation_affine(rot_k, shape)
    through_pose = points @ rotation.T + translation
    through_lib = geometry.rotated_points(points, shape, rot_k)
    assert np.array_equal(through_pose, through_lib.astype(np.float64))


def test_rotation_affine_wraps_rot_k_modulo_four():
    shape = (9, 13)
    for rot_k in range(4):
        base = pose.rotation_affine(rot_k, shape)
        wrapped = pose.rotation_affine(rot_k + 4, shape)
        assert np.array_equal(base[0], wrapped[0])
        assert np.array_equal(base[1], wrapped[1])


@pytest.mark.parametrize(
    "origin,fragment,page,expected",
    [((0, 0), (4, 4), (10, 10), ((0, 4), (0, 4), (0, 4), (0, 4))),
     ((-2, -3), (4, 4), (10, 10), ((0, 2), (0, 1), (2, 4), (3, 4))),
     ((8, 8), (4, 4), (10, 10), ((8, 10), (8, 10), (0, 2), (0, 2)))])
def test_overlap_slices_clips_a_fragment_onto_the_page(origin, fragment,
                                                       page, expected):
    slices = pose.overlap_slices(origin, fragment, page)
    assert slices is not None
    assert tuple((s.start, s.stop) for s in slices) == expected
    page_y, page_x, frag_y, frag_x = slices
    assert page_y.stop - page_y.start == frag_y.stop - frag_y.start
    assert page_x.stop - page_x.start == frag_x.stop - frag_x.start


def test_overlap_slices_returns_none_when_the_fragment_misses_the_page():
    assert pose.overlap_slices((-10, 0), (4, 4), (10, 10)) is None
    assert pose.overlap_slices((0, 10), (4, 4), (10, 10)) is None


def test_overlap_slices_moves_no_pixel_when_it_clips():
    origin = (-2, -3)
    fragment = np.arange(16, dtype=np.int64).reshape(4, 4)
    page = np.zeros((10, 10), np.int64)
    page_y, page_x, frag_y, frag_x = pose.overlap_slices(
        origin, fragment.shape, page.shape)
    page[page_y, page_x] = fragment[frag_y, frag_x]
    assert page[0, 0] == fragment[2, 3]
    assert np.array_equal(page[page_y, page_x], fragment[frag_y, frag_x])
    assert page[page_y.stop:, :].sum() == 0
    assert page[:, page_x.stop:].sum() == 0


@pytest.mark.parametrize("parity", (0, 1))
def test_parity_mask_is_the_lib_site_parity_at_the_declared_origin(parity):
    shape = (17, 23)
    origin = (5, 9)
    mask = pose.parity_mask(shape, origin, parity)
    ys = origin[0] + np.arange(shape[0])[:, None]
    xs = origin[1] + np.arange(shape[1])[None, :]
    assert np.array_equal(mask, geometry.site_parity(ys, xs) == parity)
    other = pose.parity_mask(shape, origin, 1 - parity)
    assert np.array_equal(mask, ~other)


@pytest.mark.parametrize(
    "best,rival,passes",
    [(0.05, 0.30, True),
     (0.05, 0.2000001, True),
     (0.05, 0.20, False),
     (0.05, 0.12, False),
     (0.10, 0.30, True),
     (0.25, 0.30, False)])
def test_rival_gate_needs_a_decoy_over_the_bar_and_the_declared_gap(
        best, rival, passes):
    assert pose.rival_gate(best, rival, place.GATE_RIVAL_DECOY,
                           place.GATE_MINIMUM_GAP) is passes


def _lattice_bits(shape_cells: tuple[int, int]) -> np.ndarray:
    rng = np.random.default_rng(LATTICE_BITS_SEED)
    return (rng.random(shape_cells) < 0.5).astype(np.uint8)


def _jacobian(pitch_px: float, angle_deg: float) -> np.ndarray:
    angle = np.deg2rad(angle_deg)
    return pitch_px * np.asarray(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])


def _render_lattice(bits: np.ndarray, jacobian: np.ndarray,
                    origin_yx: tuple[float, float],
                    shape_px: tuple[int, int], paper: float = 235.0,
                    ink: float = 80.0, noise: float = 3.0) -> np.ndarray:
    return _render_states(bits, np.asarray((paper, ink)), jacobian,
                          origin_yx, shape_px, paper, noise)


def _render_states(states: np.ndarray, levels: np.ndarray,
                   jacobian: np.ndarray, origin_yx: tuple[float, float],
                   shape_px: tuple[int, int], paper: float,
                   noise: float = 3.0) -> np.ndarray:
    inverse = np.linalg.inv(jacobian)
    ys, xs = np.meshgrid(np.arange(shape_px[0], dtype=np.float64),
                         np.arange(shape_px[1], dtype=np.float64),
                         indexing="ij")
    py = ys - origin_yx[0]
    px = xs - origin_yx[1]
    cell_y = np.floor(inverse[0, 0] * py + inverse[0, 1] * px).astype(
        np.int64)
    cell_x = np.floor(inverse[1, 0] * py + inverse[1, 1] * px).astype(
        np.int64)
    inside = ((cell_y >= 0) & (cell_y < states.shape[0])
              & (cell_x >= 0) & (cell_x < states.shape[1]))
    image = np.full(shape_px, paper, np.float64)
    image[inside] = levels[states[cell_y[inside], cell_x[inside]]]
    rng = np.random.default_rng(LATTICE_NOISE_SEED)
    image = image + rng.normal(0.0, noise, shape_px)
    return np.clip(np.rint(image), 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def planted_lattice() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bits = _lattice_bits((140, 140))
    jacobian = _jacobian(LATTICE_PITCH_PX, LATTICE_ANGLE_DEG)
    image = _render_lattice(bits, jacobian, LATTICE_ORIGIN_YX,
                            LATTICE_SHAPE_PX)
    return bits, jacobian, image


@pytest.fixture(scope="module")
def planted_pixels(planted_lattice) -> pose.WindowPixels:
    _bits, _jacobian, image = planted_lattice
    support = np.ones(image.shape, bool)
    support[:, 860:] = False
    pixels = pose.window_pixels(
        np.asarray(image, np.float32), support, WINDOW_ORIGIN_YX,
        WINDOW_CELLS_YX, LATTICE_PITCH_PX, 231.0, resolve_format_ref(TINY_ROW))
    assert pixels is not None
    return pixels


def test_window_pixels_reproduces_its_own_fill_and_filter_chain(
        planted_lattice, planted_pixels):
    _bits, _jacobian, image = planted_lattice
    support = np.ones(image.shape, bool)
    support[:, 860:] = False
    luma = np.asarray(image, np.float32)
    filled = np.where(support, luma, np.float32(231.0)).astype(np.float32)
    aperture = max(1, int(round(pose.APERTURE_CELLS * LATTICE_PITCH_PX)))
    filtered = np.asarray(
        ndimage.uniform_filter(filled, size=aperture, mode="nearest"))
    assert planted_pixels.aperture_px == aperture
    assert np.array_equal(planted_pixels.filled, filled)
    assert np.array_equal(planted_pixels.filtered, filtered)
    assert planted_pixels.origin_yx == WINDOW_ORIGIN_YX
    assert planted_pixels.shape_yx_cells == WINDOW_CELLS_YX
    assert planted_pixels.backing == 231.0


def test_window_pixels_refuses_a_window_with_no_support():
    assert pose.window_pixels(
        np.zeros((40, 40), np.float32), np.zeros((40, 40), bool), (0, 0),
        (4, 4), 6.0, 200.0, resolve_format_ref(TINY_ROW)) is None


def test_jacobian_from_reciprocal_inverts_the_reciprocal_basis():
    jacobian = _jacobian(LATTICE_PITCH_PX, LATTICE_ANGLE_DEG)
    reciprocal = np.linalg.inv(jacobian)
    recovered = pose.jacobian_from_reciprocal(reciprocal)
    assert np.allclose(recovered, jacobian, rtol=0.0, atol=1e-12)


def test_pose_metrics_reads_pitch_angle_and_orthogonality_off_a_jacobian():
    jacobian = _jacobian(LATTICE_PITCH_PX, LATTICE_ANGLE_DEG)
    pitch_y, pitch_x, angle, orthogonal = pose.pose_metrics(jacobian)
    assert pitch_y == pytest.approx(LATTICE_PITCH_PX, abs=1e-12)
    assert pitch_x == pytest.approx(LATTICE_PITCH_PX, abs=1e-12)
    assert angle == pytest.approx(-LATTICE_ANGLE_DEG, abs=1e-9)
    assert orthogonal == pytest.approx(0.0, abs=1e-9)
    sheared = np.asarray([[6.0, 0.6], [0.0, 6.0]])
    assert pose.pose_metrics(sheared)[3] != pytest.approx(0.0, abs=1e-6)


def test_lattice_reciprocal_recovers_the_planted_reciprocal_basis(
        planted_pixels):
    wy, wx = planted_pixels.origin_yx
    cells_y, cells_x = planted_pixels.shape_yx_cells
    py1 = wy + int(round(cells_y * LATTICE_PITCH_PX))
    px1 = wx + int(round(cells_x * LATTICE_PITCH_PX))
    spectral = planted_pixels.filled[wy:py1, wx:px1]
    blind = pose.lattice_reciprocal(spectral, LATTICE_PITCH_PX)
    assert blind is not None
    jacobian = pose.jacobian_from_reciprocal(blind)
    pitch_y, pitch_x, angle, _orthogonal = pose.pose_metrics(jacobian)
    assert pitch_y == pytest.approx(LATTICE_PITCH_PX,
                                    abs=PITCH_RECOVERY_TOL_PX)
    assert pitch_x == pytest.approx(LATTICE_PITCH_PX,
                                    abs=PITCH_RECOVERY_TOL_PX)
    assert abs(angle) == pytest.approx(LATTICE_ANGLE_DEG,
                                       abs=ANGLE_RECOVERY_TOL_DEG)
    prior = np.asarray([[1.0 / LATTICE_PITCH_PX, 0.0],
                        [0.0, 1.0 / LATTICE_PITCH_PX]])
    seeded = pose.lattice_reciprocal(spectral, LATTICE_PITCH_PX,
                                     prior_f=prior)
    assert seeded is not None
    assert np.allclose(seeded, blind, atol=1e-6)


def test_lattice_reciprocal_refuses_a_lattice_free_field():
    rng = np.random.default_rng(555)
    flat = rng.normal(200.0, 2.0, size=(400, 400)).astype(np.float32)
    reciprocal = pose.lattice_reciprocal(flat, 900.0)
    assert reciprocal is None


def test_fit_window_pose_recovers_the_planted_pose(planted_lattice,
                                                    planted_pixels):
    _bits, jacobian, _image = planted_lattice
    fit = pose.fit_window_pose(planted_pixels)
    assert fit.segment is not None
    assert fit.lattice_seed is not None
    assert fit.unconditioned_seed is not None
    fitted = fit.segment.pose
    assert fitted.pitch_px == pytest.approx(LATTICE_PITCH_PX,
                                            abs=PITCH_RECOVERY_TOL_PX)
    assert np.allclose(fitted.matrix(), jacobian, atol=0.05)
    origin = np.asarray(fitted.origin_yx, np.float64)
    truth = (np.asarray(LATTICE_ORIGIN_YX, np.float64)
             + jacobian @ np.full(2, 0.5))
    lattice_origin = truth + jacobian @ np.rint(
        np.linalg.solve(jacobian, origin - truth))
    assert np.allclose(origin, lattice_origin,
                       atol=ORIGIN_RECOVERY_TOL_PX)
    assert fit.segment.shape_yx_cells == WINDOW_CELLS_YX


#: The R plane of a cmy page (R7, R24): C dark, W, Y and M light, at R of
#: e043c sheet 3's bars (`_h3_sims_cmy.e043c_sheet3_bars`), indexed by
#: presence id W 0, C 1, M 2, Y 4.
CMY_ROW = "c3-cmy-r0850@10x10"
CMY_R_LEVELS = (231.0, 51.0, 217.0, 0.0, 230.0)
CMY_STATES_SEED = 20261012


def test_fit_phase_locks_the_true_phase_on_a_seeded_r_window():
    row = resolve_format_ref(CMY_ROW)
    rng = np.random.default_rng(CMY_STATES_SEED)
    states = rng.choice(np.asarray(row.state_ids), size=(140, 140))
    jacobian = _jacobian(LATTICE_PITCH_PX, LATTICE_ANGLE_DEG)
    paper = CMY_R_LEVELS[0]
    image = _render_states(states, np.asarray(CMY_R_LEVELS), jacobian,
                           LATTICE_ORIGIN_YX, LATTICE_SHAPE_PX, paper)
    pixels = pose.window_pixels(
        np.asarray(image, np.float32), np.ones(image.shape, bool),
        WINDOW_ORIGIN_YX, WINDOW_CELLS_YX, LATTICE_PITCH_PX, paper, row)
    assert pixels is not None
    fitted = pose._fit_phase(pixels, jacobian)
    assert fitted is not None
    phase_yx, _contrast = fitted
    origin = (np.asarray(WINDOW_ORIGIN_YX, np.float64)
              + jacobian @ np.asarray(phase_yx))
    truth = (np.asarray(LATTICE_ORIGIN_YX, np.float64)
             + jacobian @ np.full(2, 0.5))
    first_cell = np.rint(np.linalg.solve(jacobian, origin - truth))
    lattice_origin = truth + jacobian @ first_cell
    assert np.allclose(origin, lattice_origin, atol=ORIGIN_RECOVERY_TOL_PX)
    # The window's own split reads C alone dark; np.median, inside the
    # light three quarters, would read light cells dark too.
    segment = pose.PoseSegment(
        pose.Pose((float(origin[0]), float(origin[1])),
                  tuple(map(tuple, jacobian.tolist())), phase_yx,
                  LATTICE_PITCH_PX, LATTICE_ANGLE_DEG),
        WINDOW_CELLS_YX, 0, 0.0, (LATTICE_PITCH_PX, LATTICE_PITCH_PX), 0.0)
    sample = pose.sample_segment(pixels, segment)
    assert sample is not None
    assert sample.mask.all()
    cy, cx = (int(first_cell[0]), int(first_cell[1]))
    window_states = states[cy:cy + WINDOW_CELLS_YX[0],
                           cx:cx + WINDOW_CELLS_YX[1]]
    assert np.array_equal(sample.bits, (window_states == 1).astype(np.uint8))


@pytest.mark.parametrize("dark_share", (0.20, 0.25, 0.30))
def test_the_r_split_falls_between_the_populations(dark_share):
    cmy = resolve_format_ref(CMY_ROW)
    dark = int(round(dark_share * 1000))
    values = np.concatenate((np.full(dark, CMY_R_LEVELS[1]),
                             np.full(1000 - dark, CMY_R_LEVELS[2])))
    split = words.addressing_split(values, cmy)
    assert CMY_R_LEVELS[1] < split < CMY_R_LEVELS[2]


def test_luma_families_keep_np_median_smoke():
    # A smoke check, not a discriminator: for a luma row addressing_split
    # returns np.median itself, so this compares np.median with np.median.
    # It catches a luma row routed onto the R quantiles; it cannot catch
    # np.median swapped for np.quantile(., 0.5), which lands on the same
    # middle element of an odd count.
    spread = np.random.default_rng(CMY_STATES_SEED).normal(
        140.0, 30.0, 999).astype(np.float32)
    assert (words.addressing_split(spread, resolve_format_ref(TINY_ROW))
            == float(np.median(spread)))


def test_fit_window_pose_refuses_a_featureless_field():
    flat = np.full((700, 700), 200.0, np.float32)
    pixels = pose.window_pixels(
        flat, np.ones(flat.shape, bool), (10, 10), (80, 80),
        LATTICE_PITCH_PX, 200.0, resolve_format_ref(TINY_ROW))
    assert pixels is not None
    fit = pose.fit_window_pose(pixels)
    assert fit.segment is None
    assert fit.unconditioned_seed is None


def test_fit_window_pose_is_deterministic(planted_pixels):
    first = pose.fit_window_pose(planted_pixels)
    second = pose.fit_window_pose(planted_pixels)
    assert first.segment is not None and second.segment is not None
    assert first.segment.pose == second.segment.pose
    assert np.array_equal(first.lattice_seed, second.lattice_seed)


@pytest.fixture(scope="module")
def planted_sample(planted_pixels) -> pose.SegmentSample:
    fit = pose.fit_window_pose(planted_pixels)
    assert fit.segment is not None
    sample = pose.sample_segment(planted_pixels, fit.segment)
    assert sample is not None
    return sample


def test_sample_segment_agrees_with_median_radiometrics(planted_sample):
    midpoint, bits, evidence = pose.median_radiometrics(
        planted_sample.means, planted_sample.mask,
        resolve_format_ref(TINY_ROW))
    assert planted_sample.midpoint == midpoint
    assert np.array_equal(planted_sample.bits, bits)
    assert np.array_equal(planted_sample.evidence, evidence)
    assert planted_sample.segment.support_cells == int(
        planted_sample.mask.sum())
    assert not evidence[~planted_sample.mask].any()


def test_median_radiometrics_signs_ink_negative_and_paper_positive():
    means = np.asarray([[10.0, 200.0], [10.0, 200.0]], np.float32)
    mask = np.ones((2, 2), bool)
    midpoint, bits, evidence = pose.median_radiometrics(
        means, mask, resolve_format_ref(TINY_ROW))
    assert midpoint == 105.0
    assert np.array_equal(bits, np.asarray([[1, 0], [1, 0]], np.uint8))
    assert (evidence[bits == 1] < 0.0).all()
    assert (evidence[bits == 0] > 0.0).all()


def test_address_core_erodes_the_mask_but_never_empties_it():
    mask = np.zeros((20, 20), bool)
    mask[4:16, 4:16] = True
    core = pose.address_core(mask)
    assert core.sum() == 8 * 8
    assert (core & ~mask).sum() == 0
    thin = np.zeros((20, 20), bool)
    thin[9:11, 9:11] = True
    assert np.array_equal(pose.address_core(thin), thin)
    assert np.array_equal(pose.address_core(mask, 0), mask)


@pytest.fixture(scope="module")
def reference_field() -> words.ReferenceField:
    return words.ReferenceField(resolve_format_ref(TINY_ROW))


def test_fragment_reference_sites_round_trips_the_rotation_frame(
        reference_field):
    mask = np.ones((48, 48), bool)
    for rot_k in range(4):
        points, expected, absolute = pose.fragment_reference_sites(
            mask, reference_field, 0, (16, 24), rot_k)
        assert points.shape[0] == expected.size == absolute.shape[0]
        assert expected.size > 0
        page = reference_field.page(0)
        assert np.array_equal(
            expected, page.values[absolute[:, 0], absolute[:, 1]])
        assert page.sites[absolute[:, 0], absolute[:, 1]].all()
        assert points[:, 0].max() < mask.shape[0]
        assert points[:, 1].max() < mask.shape[1]


def test_fragment_reference_sites_is_empty_off_the_page(reference_field):
    mask = np.ones((8, 8), bool)
    points, expected, absolute = pose.fragment_reference_sites(
        mask, reference_field, 0, (-40, -40), 0)
    assert points.shape == (0, 2)
    assert expected.size == 0
    assert absolute.shape == (0, 2)


def _score_memo_inputs(field: words.ReferenceField, origin: tuple[int, int],
                       size: int) -> tuple[np.ndarray, ...]:
    page = field.page(0)
    bits = page.values[origin[0]:origin[0] + size,
                       origin[1]:origin[1] + size].copy()
    evidence = (1.0 - 2.0 * bits.astype(np.float32))
    return evidence, bits, np.ones((size, size), bool)


def test_score_memo_is_pure_and_the_cache_never_changes_an_answer(
        reference_field):
    evidence, bits, mask = _score_memo_inputs(reference_field, (16, 24), 96)
    memo = pose.ScoreMemo(reference_field)
    first = memo.parity_score(evidence, bits, mask, 0, (16, 24), 0, 0)
    second = memo.parity_score(evidence, bits, mask, 0, (16, 24), 0, 0)
    fresh = pose.ScoreMemo(reference_field).parity_score(
        evidence, bits, mask, 0, (16, 24), 0, 0)
    assert first == second == fresh
    assert first[0] == 0.0
    assert first[1] == 0
    assert first[2] > 0
    wrong = memo.parity_score(evidence, bits, mask, 0, (20, 24), 0, 0)
    assert wrong[0] > first[0]


def test_score_memo_reports_no_support_off_the_page(reference_field):
    evidence, bits, mask = _score_memo_inputs(reference_field, (16, 24), 96)
    memo = pose.ScoreMemo(reference_field)
    off = memo.parity_score(evidence, bits, mask, 0, (-500, -500), 0, 0)
    assert off == (1.0, 0, 0, -np.inf)


def test_score_memo_candidate_passes_only_inside_both_gates(reference_field):
    evidence, bits, mask = _score_memo_inputs(reference_field, (16, 24), 96)
    memo = pose.ScoreMemo(reference_field)
    truth = memo.candidate(evidence, bits, mask, 0, (16, 24), 0, 30,
                           place.GATE_SEARCH_TRUE,
                           place.GATE_VALIDATION_TRUE, "word")
    assert truth.passes is True
    assert truth.route == "word"
    assert truth.search_mismatch == 0.0 and truth.validation_mismatch == 0.0
    starved = memo.candidate(evidence, bits, mask, 0, (16, 24), 0,
                             10 ** 6, place.GATE_SEARCH_TRUE,
                             place.GATE_VALIDATION_TRUE, "word")
    assert starved.passes is False
    decoy = memo.candidate(evidence, bits, mask, 0, (20, 28), 0, 30,
                           place.GATE_SEARCH_TRUE,
                           place.GATE_VALIDATION_TRUE, "word")
    assert decoy.passes is False


def test_whole_word_parity_scores_both_parities_together(reference_field):
    evidence, bits, mask = _score_memo_inputs(reference_field, (16, 24), 96)
    memo = pose.ScoreMemo(reference_field)
    search = memo.parity_score(evidence, bits, mask, 0, (16, 24), 0, 0)
    validation = memo.parity_score(evidence, bits, mask, 0, (16, 24), 0, 1)
    whole = memo.parity_score(evidence, bits, mask, 0, (16, 24), 0,
                              pose.WHOLE_WORD_PARITY)
    assert whole[2] == search[2] + validation[2]
    assert whole[1] == search[1] + validation[1]


def test_audit_segment_keeps_a_clean_fragment_whole(reference_field):
    size = 96
    origin = (16, 24)
    evidence, bits, mask = _score_memo_inputs(reference_field, origin, size)
    sample = pose.SegmentSample(
        pose.PoseSegment(
            pose.Pose((0.0, 0.0), ((6.0, 0.0), (0.0, 6.0)), (0.5, 0.5),
                      6.0, 0.0),
            (size, size), int(mask.sum()), 0.0, (6.0, 6.0), 0.0),
        np.zeros((size, size), np.float32), mask, bits, evidence, 0.0)
    good, refused, kept, residual = pose.audit_segment(
        sample, mask, reference_field, 0, origin, 0, 30)
    assert refused is False
    assert residual == 0.0
    assert kept > 0
    assert np.array_equal(good, mask)


def test_audit_segment_refuses_a_fragment_that_straddles_a_wrong_address(
        reference_field):
    size = 96
    origin = (16, 24)
    evidence, bits, mask = _score_memo_inputs(reference_field, origin, size)
    rng = np.random.default_rng(31415)
    scrambled = bits.copy()
    scrambled[:] = rng.integers(0, 2, size=bits.shape, dtype=np.uint8)
    sample = pose.SegmentSample(
        pose.PoseSegment(
            pose.Pose((0.0, 0.0), ((6.0, 0.0), (0.0, 6.0)), (0.5, 0.5),
                      6.0, 0.0),
            (size, size), int(mask.sum()), 0.0, (6.0, 6.0), 0.0),
        np.zeros((size, size), np.float32), mask, scrambled, evidence, 0.0)
    _good, refused, _kept, residual = pose.audit_segment(
        sample, mask, reference_field, 0, origin, 0, 30)
    assert refused is True
    assert residual > pose.AUDIT_POST_BAR


@pytest.mark.parametrize(
    "extent,children",
    [((0, 0, 200, 200), ((0, 0, 100, 100), (0, 100, 100, 200),
                         (100, 0, 200, 100), (100, 100, 200, 200))),
     ((10, 20, 160, 170), ((10, 20, 85, 95), (10, 95, 85, 170),
                           (85, 20, 160, 95), (85, 95, 160, 170)))])
def test_subdivision_child_extents_quarters_a_large_window(extent, children):
    assert pose.subdivision_child_extents(extent, 0) == children


def test_subdivision_child_extents_stops_at_the_declared_depth():
    assert pose.subdivision_child_extents((0, 0, 200, 200), 1) == ()


def test_subdivision_child_extents_refuses_a_window_at_the_cell_floor():
    assert pose.subdivision_child_extents((0, 0, 70, 70), 0) == ()
    assert pose.subdivision_child_extents((0, 0, 64, 200), 0) == ()
    assert pose.subdivision_child_extents((0, 0, 140, 140), 0) != ()


def test_subdivision_children_overlap_when_the_floor_binds():
    extent = (0, 0, 130, 130)
    children = pose.subdivision_child_extents(extent, 0)
    assert len(children) == 4
    sides = {(c[2] - c[0], c[3] - c[1]) for c in children}
    assert sides == {(pose.MIN_WINDOW_CELLS, pose.MIN_WINDOW_CELLS)}
    covered = np.zeros((130, 130), np.int64)
    for cy0, cx0, cy1, cx1 in children:
        covered[cy0:cy1, cx0:cx1] += 1
    assert covered.min() >= 1
    assert covered.max() > 1


def test_refine_patch_pose_refuses_a_fragment_below_the_site_floor(
        reference_field, planted_pixels):
    size = 8
    mask = np.ones((size, size), bool)
    sample = pose.SegmentSample(
        pose.PoseSegment(
            pose.Pose((50.0, 60.0), ((6.0, 0.0), (0.0, 6.0)), (0.5, 0.5),
                      6.0, 0.0),
            (size, size), int(mask.sum()), 0.0, (6.0, 6.0), 0.0),
        np.zeros((size, size), np.float32), mask,
        np.zeros((size, size), np.uint8),
        np.zeros((size, size), np.float32), 0.0)
    assert pose.refine_patch_pose(
        planted_pixels, sample, reference_field, 0, (0, 0), 0) is None


def test_refine_grid_is_the_declared_angle_and_phase_ladder():
    angles, phases = pose._refine_grids()
    assert angles[0] == pytest.approx(-pose.REFINE_ANGLE_DEG)
    assert angles[-1] == pytest.approx(pose.REFINE_ANGLE_DEG)
    assert len(angles) == 7
    assert phases[0] == pytest.approx(-pose.REFINE_PHASE_CELLS)
    assert phases[-1] == pytest.approx(pose.REFINE_PHASE_CELLS)
    assert len(phases) == 9
    assert 0.0 in [round(float(a), 12) for a in angles]
    assert 0.0 in [round(float(p), 12) for p in phases]
