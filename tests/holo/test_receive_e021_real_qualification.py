"""Fast structural tests for the opt-in authentic E021 campaign."""
from __future__ import annotations

import numpy as np

from paperholo import platen

from _qualify_e021_real import (
    CORPUS,
    SOURCE_SHA256,
    _differences,
    _holo_contract,
    _legacy_contract,
    _topology_for_support,
)
from holo.receive.survey import (
    PayloadSurvey,
    PitchVote,
    SupportMask,
    SurveyDiagnostics,
    SurveyRegion,
)


def test_authentic_catalog_is_frozen_and_covers_c2_c3_grey_rgb() -> None:
    names = {case.name for case in CORPUS}
    assert names == set(SOURCE_SHA256)
    assert len(names) == len(CORPUS)
    assert any(case.expected_c == 2 for case in CORPUS)
    assert any(case.expected_c == 3 for case in CORPUS)
    assert any("rgb" in case.role for case in CORPUS)
    assert all(len(value) == 64 for value in SOURCE_SHA256.values())


def test_neutral_contract_hashes_the_same_dense_support() -> None:
    cells = np.ones((5, 7), bool)
    cells[2, 3] = False
    support = SupportMask((4, 6), 2, cells, (10, 14))
    dense = support.rasterize()
    dpi = 600.0
    area = int(np.count_nonzero(dense)) / (dpi / 25.4) ** 2
    holo = PayloadSurvey(
        regions=(
            SurveyRegion(
                support=support,
                area_mm2=area,
                median_tensor_score=4.5,
            ),
        ),
        c_dots=2,
        cell_pitch_px=2.0,
        pitch_votes=(PitchVote(2, 2.0),),
        diagnostics=SurveyDiagnostics(
            threshold=0.25,
            survey_step_px=2,
            survey_scale_px=3.0,
            component_count=1,
            refinement_tiles=2,
            refinement_scored_cells=30,
            refinement_grid_cells=60,
        ),
    )
    legacy = platen.PayloadSurvey(
        regions=(
            platen.PayloadRegion(
                bbox=support.bbox,
                mask=dense,
                area_mm2=area,
                angle_hint_deg=-3.25,
                score=4.5,
            ),
        ),
        c_dots=2,
        cell_pitch_px=2.0,
        pitch_votes=((2, 2.0),),
        diagnostics={
            "survey_threshold": 0.25,
            "survey_step_px": 2,
            "survey_scale_px": 3.0,
            "survey_components": 1,
            "refine_tiles": 2,
            "refine_scored_cells": 30,
            "refine_grid_cells": 60,
            "refine_fraction": 0.5,
        },
    )

    assert _holo_contract(holo) == _legacy_contract(legacy)


def test_topology_reports_small_and_large_enclosed_holes_separately() -> None:
    cells = np.ones((25, 30), bool)
    cells[4, 4] = False
    cells[8:17, 15:24] = False
    support = SupportMask((0, 0), 1, cells, cells.shape)

    topology = _topology_for_support(support, pitch_px=1.0)

    assert topology["foreground_components"] == 1
    assert topology["enclosed_holes"] == 2
    assert topology["fill_eligible_residual_holes"] == 1
    assert topology["largest_holes"][0]["fill_eligible"] is False
    assert topology["largest_holes"][1]["fill_eligible"] is True


def test_recursive_difference_paths_are_actionable() -> None:
    left = {"regions": [{"bbox": [1, 2, 3, 4], "mask": "a"}]}
    right = {"regions": [{"bbox": [1, 2, 9, 4], "mask": "b"}]}

    assert _differences(left, right) == [
        "regions[0].bbox[2]: 3!=9",
        "regions[0].mask: 'a'!='b'",
    ]
