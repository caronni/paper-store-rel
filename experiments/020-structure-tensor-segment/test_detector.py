from __future__ import annotations

import numpy as np
import pytest

import detector
import run_e020


def _e020(scene):
    result = detector.detect(scene.image, cell_px=run_e020.P,
                             dpi=run_e020.DPI)
    return result, detector.rasterize(result, scene.image.shape)


def test_blank_paper_edges_do_not_form_candidates():
    scene = run_e020.make_scene("edges_only", 319)
    result, mask = _e020(scene)
    assert len(result.candidates) == 0
    assert not mask.any()


def test_faint_fields_survive_adaptive_threshold():
    scene = run_e020.make_scene("faint_blurred", 319)
    result, mask = _e020(scene)
    iou, precision, recall, _ = run_e020._metrics(mask, scene.truth)
    assert len(result.candidates) == 3
    assert iou > 0.85
    assert precision > 0.92
    assert recall > 0.90


def test_dark_backing_excludes_white_margins():
    scene = run_e020.make_scene("dark_margins", 319)
    result, mask = _e020(scene)
    iou, precision, recall, _ = run_e020._metrics(mask, scene.truth)
    assert len(result.candidates) == 3
    assert iou > 0.85
    assert precision > 0.92
    assert recall > 0.90


def test_input_validation_and_uint16_scale():
    scene = run_e020.make_scene("white_lid", 319)
    base = detector.detect(scene.image, cell_px=run_e020.P,
                           dpi=run_e020.DPI)
    wide = detector.detect(scene.image.astype(np.uint16) * 256,
                           cell_px=run_e020.P, dpi=run_e020.DPI)
    assert np.array_equal(base.mask_cells, wide.mask_cells)
    with pytest.raises(ValueError, match="2-D"):
        detector.detect(np.zeros((10, 10, 3), np.uint8), cell_px=8, dpi=1600)
