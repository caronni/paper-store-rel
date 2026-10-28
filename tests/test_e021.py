"""Strict e021 contract tests.

Unlike the retired 021.0 battery, these tests require one-to-one ownership,
exact candidate counts, mask IoU, no extras, global-c behavior, and
non-vacuous angle/refusal checks.  Bbox overlap alone never passes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import platen  # noqa: E402


INK, PAPER, BACK = 68.0, 226.0, 40.0
DPI = 1600.0
CELL_PX = 8


def test_survey_scale_tracks_scanner_dpi_on_one_physical_footing() -> None:
    pitch_1200 = platen.SURVEY_CELL_UM / 1000.0 * 1200.0 / 25.4
    pitch_4800 = platen.SURVEY_CELL_UM / 1000.0 * 4800.0 / 25.4
    decim_1200, work_1200, step_1200 = platen._tensor_geometry(pitch_1200)
    decim_4800, work_4800, step_4800 = platen._tensor_geometry(pitch_4800)

    assert pitch_1200 == pytest.approx(16.063, abs=0.001)
    assert pitch_4800 == pytest.approx(64.252, abs=0.001)
    assert (decim_1200, work_1200, step_1200) == (4, 4, 16)
    assert (decim_4800, work_4800, step_4800) == (16, 4, 64)


def field(*, cell_px: int = CELL_PX, n_px: int = 1400,
          seed: int = 201) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = n_px // cell_px
    bits = rng.random((n, n)) < 0.5
    return np.where(
        np.kron(bits, np.ones((cell_px, cell_px), bool)), INK, PAPER
    ).astype(np.float32)


def compose_scene(
    pieces: list[tuple[np.ndarray, np.ndarray, tuple[int, int]]],
    *,
    shape: tuple[int, int],
    blur: float = 2.0,
    noise: float = 5.0,
    seed: int = 202,
) -> tuple[np.ndarray, list[np.ndarray]]:
    canvas = np.full(shape, BACK, np.float32)
    truths: list[np.ndarray] = []
    for image, payload_mask, (y0, x0) in pieces:
        h = min(image.shape[0], shape[0] - y0)
        w = min(image.shape[1], shape[1] - x0)
        canvas[y0:y0 + h, x0:x0 + w] = image[:h, :w]
        truth = np.zeros(shape, bool)
        truth[y0:y0 + h, x0:x0 + w] = payload_mask[:h, :w]
        truths.append(truth)
    rng = np.random.default_rng(seed)
    canvas = ndimage.gaussian_filter(canvas, blur)
    canvas += rng.normal(0.0, noise, canvas.shape)
    return np.clip(canvas, 0.0, 255.0), truths


def predicted_masks(
    survey: platen.PayloadSurvey, shape: tuple[int, int]
) -> list[np.ndarray]:
    masks: list[np.ndarray] = []
    for region in survey.regions:
        y0, x0, h, w = region.bbox
        dense = np.zeros(shape, bool)
        dense[y0:y0 + h, x0:x0 + w] = region.mask[:h, :w]
        masks.append(dense)
    return masks


def strict_assignment(
    survey: platen.PayloadSurvey,
    truths: list[np.ndarray],
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    predictions = predicted_masks(survey, truths[0].shape)
    assert len(predictions) == len(truths), (
        f"one-to-one contract: {len(predictions)} candidates for "
        f"{len(truths)} truth regions"
    )
    iou = np.zeros((len(truths), len(predictions)), np.float64)
    for i, truth in enumerate(truths):
        for j, prediction in enumerate(predictions):
            union = int((truth | prediction).sum())
            iou[i, j] = int((truth & prediction).sum()) / max(union, 1)
    rows, cols = linear_sum_assignment(-iou)
    return iou, list(zip(rows.tolist(), cols.tolist()))


def assert_no_fill_eligible_holes(survey: platen.PayloadSurvey) -> None:
    assert survey.cell_pitch_px is not None
    for region in survey.regions:
        cleaned = platen._support_mask(
            region.mask,
            platen.SUPPORT_HOLE_RADIUS_CELLS * survey.cell_pitch_px,
        )
        assert np.array_equal(region.mask, cleaned)


def test_margin_bearing_field_one_to_one_and_tight() -> None:
    payload = field(seed=203)
    margin = 40
    scrap = np.full(
        (payload.shape[0] + 2 * margin, payload.shape[1] + 2 * margin),
        PAPER, np.float32,
    )
    scrap[margin:-margin, margin:-margin] = payload
    payload_mask = np.zeros(scrap.shape, bool)
    payload_mask[margin:-margin, margin:-margin] = True
    canvas, truths = compose_scene(
        [(scrap, payload_mask, (300, 300))], shape=(2400, 2400), seed=203
    )

    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    iou, assignment = strict_assignment(survey, truths)
    assert iou[assignment[0]] > 0.97
    assert survey.c_dots == 3
    assert abs(survey.cell_pitch_px - CELL_PX) < 0.3
    assert_no_fill_eligible_holes(survey)


def test_rotated_regions_have_unique_ownership_and_safe_hints() -> None:
    pieces = []
    angles = (7.0, 27.0, 41.0)
    positions = ((250, 250), (250, 2300), (2300, 1100))
    for index, (angle, position) in enumerate(zip(angles, positions)):
        payload = field(n_px=1200, seed=210 + index)
        rotated = ndimage.rotate(
            payload, angle, reshape=True, order=1, mode="constant", cval=BACK
        )
        mask = ndimage.rotate(
            np.ones(payload.shape, np.uint8), angle, reshape=True, order=0,
            mode="constant", cval=0,
        ) > 0
        pieces.append((rotated, mask, position))
    canvas, truths = compose_scene(
        pieces, shape=(4400, 4400), seed=220
    )

    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    iou, assignment = strict_assignment(survey, truths)
    assert min(iou[pair] for pair in assignment) > 0.82
    assert survey.c_dots == 3

    hints = []
    for truth_index, region_index in assignment:
        hint = survey.regions[region_index].angle_hint_deg
        if hint is None:
            continue
        expected = -angles[truth_index]
        error = abs(((hint - expected + 45.0) % 90.0) - 45.0)
        hints.append(error)
    assert hints, "angle contract must be exercised, not vacuously pass"
    assert max(hints) < 2.0
    assert_no_fill_eligible_holes(survey)


def test_support_mask_fills_holes_but_preserves_exterior_concavity() -> None:
    activity = np.zeros((20, 28), bool)
    activity[2:18, 2:14] = True
    activity[2:18, 16:26] = True
    activity[7:10, 6:9] = False              # enclosed tensor dropout
    activity[2:9, 11:14] = False             # exterior-connected notch
    activity[6:13, 18:25] = False            # larger enclosed real void

    support = platen._support_mask(activity)

    assert support[7:10, 6:9].all()
    assert not support[2:9, 11:14].any()
    assert not support[6:13, 18:25].any()
    assert ndimage.label(activity)[1] == ndimage.label(support)[1] == 2


def test_boundary_refinement_restores_hole_but_keeps_open_gap() -> None:
    base = np.zeros((24, 36), bool)
    base[2:22, 2:34] = True
    active = base.copy()
    active[9:12, 8:11] = False
    active[2:22, 17:19] = False
    domain = base & ~active
    known = np.ones(base.shape, bool)

    merged = platen._merge_boundary_refinement(
        base, domain, active, known
    )

    assert merged[9:12, 8:11].all()
    assert not merged[2:22, 17:19].any()
    assert ndimage.label(merged)[1] == 2


def test_pitch_refinement_splits_a_subsurvey_gap() -> None:
    first = field(n_px=1200, seed=225)
    second = field(n_px=1200, seed=226)
    gap_px = int(round(0.4 * DPI / 25.4))
    canvas, truths = compose_scene(
        [
            (first, np.ones(first.shape, bool), (400, 400)),
            (
                second,
                np.ones(second.shape, bool),
                (400, 400 + first.shape[1] + gap_px),
            ),
        ],
        shape=(2200, 400 + first.shape[1] * 2 + gap_px + 800),
        seed=227,
    )

    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    iou, assignment = strict_assignment(survey, truths)

    assert min(iou[pair] for pair in assignment) > 0.80
    assert survey.diagnostics["refine_mode"] == "boundary-gap-tiles"
    assert survey.diagnostics["refine_tiles"] > 0


def test_blank_paper_edges_and_noise_emit_nothing() -> None:
    rng = np.random.default_rng(230)
    canvas = np.full((2600, 2600), BACK, np.float32)
    canvas[300:1800, 300:1800] = PAPER       # homogeneous paper + 1-D edges
    canvas[2100:2130, 400:2200] = PAPER      # thin edge/ribbon, no payload
    canvas += rng.normal(0.0, 5.0, canvas.shape)
    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    assert survey.regions == ()
    assert survey.c_dots is None
    assert survey.cell_pitch_px is None


def test_faint_field_is_not_relabelled_or_silently_dropped() -> None:
    healthy = field(seed=240)
    faint = ndimage.gaussian_filter(
        133.0 + (field(seed=241) - 147.0) * 0.35, 4.0
    )
    pieces = [
        (healthy, np.ones(healthy.shape, bool), (300, 300)),
        (faint, np.ones(faint.shape, bool), (300, 2000)),
    ]
    canvas, truths = compose_scene(
        pieces, shape=(2200, 3800), blur=1.5, seed=242
    )
    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    iou, assignment = strict_assignment(survey, truths)
    assert min(iou[pair] for pair in assignment) > 0.80
    assert survey.c_dots == 3


def test_payload_dominated_platen_keeps_adjacent_piece_independent() -> None:
    page = field(n_px=2500, seed=250)
    side = field(n_px=350, seed=251)
    canvas, truths = compose_scene(
        [
            (page, np.ones(page.shape, bool), (100, 100)),
            (side, np.ones(side.shape, bool), (2650, 100)),
        ],
        shape=(3000, 3000),
        seed=252,
    )
    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    iou, assignment = strict_assignment(survey, truths)
    assert min(iou[pair] for pair in assignment) > 0.80
    assert survey.c_dots == 3


def test_thin_region_survives_without_fake_angle() -> None:
    large = field(seed=260)
    ribbon = field(n_px=1200, seed=261)[:32, :]
    canvas, truths = compose_scene(
        [
            (large, np.ones(large.shape, bool), (300, 300)),
            (ribbon, np.ones(ribbon.shape, bool), (2100, 500)),
        ],
        shape=(2600, 3200),
        seed=262,
    )
    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    iou, assignment = strict_assignment(survey, truths)
    assert min(iou[pair] for pair in assignment) > 0.70
    ribbon_region = survey.regions[assignment[1][1]]
    assert ribbon_region.angle_hint_deg is None
    assert survey.c_dots == 3


def test_mixed_c_platen_refuses_global_c() -> None:
    c3 = field(cell_px=8, seed=270)
    c6 = field(cell_px=16, n_px=1408, seed=271)
    canvas, truths = compose_scene(
        [
            (c3, np.ones(c3.shape, bool), (300, 300)),
            (c6, np.ones(c6.shape, bool), (300, 1900)),
        ],
        shape=(2400, 3600),
        seed=272,
    )
    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    strict_assignment(survey, truths)
    assert survey.c_dots is None
    assert survey.cell_pitch_px is None
    assert {vote[0] for vote in survey.pitch_votes} == {3, 6}


def test_input_guards_and_16bit_scale_invariance() -> None:
    with pytest.raises(ValueError, match="2-D"):
        platen.detect_payload_regions(
            np.zeros((10, 10, 3), np.uint8), dpi=DPI
        )
    with pytest.raises(ValueError, match="dpi"):
        platen.detect_payload_regions(np.zeros((100, 100)), dpi=0)
    assert platen.detect_payload_regions(
        np.zeros((40, 40), np.uint8), dpi=DPI
    ).regions == ()

    payload = field(seed=280)
    canvas, _ = compose_scene(
        [(payload, np.ones(payload.shape, bool), (300, 300))],
        shape=(2200, 2200), seed=281,
    )
    survey8 = platen.detect_payload_regions(canvas, dpi=DPI)
    survey16 = platen.detect_payload_regions(
        (canvas * 256.0).astype(np.float32), dpi=DPI
    )
    assert survey8.c_dots == survey16.c_dots == 3
    assert len(survey8.regions) == len(survey16.regions) == 1
    assert survey8.regions[0].bbox == survey16.regions[0].bbox
    assert np.array_equal(survey8.regions[0].mask, survey16.regions[0].mask)


def test_annotated_png_smoke() -> None:
    sys.path.insert(0, str(ROOT / "experiments/021-payload-regions"))
    import analyze_e021

    payload = field(seed=290)
    canvas, _ = compose_scene(
        [(payload, np.ones(payload.shape, bool), (300, 300))],
        shape=(2200, 2200), seed=291,
    )
    survey = platen.detect_payload_regions(canvas, dpi=DPI)
    image = analyze_e021.annotate(
        canvas, survey.regions, target_w=600,
        title=f"c{survey.c_dots}",
    )
    assert image.width == 600 and image.height > 0
