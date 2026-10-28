"""E022 null battery, first v1 rungs (gap-audit port, 2026-07-31).

Historical E022 qualified its zero-false-accept record with adversarial
nulls (0/49 over 784 field hypotheses).  These are the first format-v1
ports: a true rendered fragment must place on its own page via COLD
correlation, and the same fragment against same-seed WRONG-page values
must refuse.  The remaining rungs — wrong-seed sibling-row null,
GT-affine pose battery, mirror refusal, cross-scrap fill — are ported in
``test_placement_null_battery_extended.py`` (2026-07-31).
"""
from __future__ import annotations

import numpy as np
import pytest

from holo.receive.place import place_survey
from holo.receive.placement.defaults import PROVISIONAL_V1_PLACEMENT_POLICY
from holo.receive.placement.model import PlacementConfig
from holo.receive.scan import open_capture
from holo.receive.survey import (
    PayloadSurvey,
    SupportMask,
    SurveyDiagnostics,
    SurveyRegion,
)

import _roundtrip_fixture as roundtrip


@pytest.fixture(scope="module")
def fixture():
    return roundtrip._build_fixture()


@pytest.fixture(scope="module")
def fragment(fixture):
    """One non-tile-aligned 128-cell true fragment on a paper canvas."""
    spec = fixture.spec
    ppc = int(round(roundtrip._DPI / 600.0)) * spec.cell_dots
    field_px = np.asarray(fixture.raster.shape)
    cells_yx = np.asarray(spec.layout.cells_yx)
    origin_px = (field_px - cells_yx * ppc) // 2
    y0 = int(origin_px[0] + 32 * ppc)
    x0 = int(origin_px[1] + 32 * ppc)
    span = 128 * ppc
    piece = np.array(fixture.raster[y0:y0 + span, x0:x0 + span], copy=True)
    margin = 16 * ppc
    canvas = np.full(
        (span + 2 * margin, span + 2 * margin),
        float(fixture.raster.max()), fixture.raster.dtype)
    canvas[margin:margin + span, margin:margin + span] = piece
    canvas.setflags(write=False)
    # Support covers the printed fragment only — the paper margin is not
    # search support, exactly as E021 segmentation would report it.
    support = SupportMask(
        (margin, margin), span, np.ones((1, 1), bool), (span, span))
    return open_capture(canvas, roundtrip._DPI), support


def _survey(raster, support, spec) -> PayloadSurvey:
    px_per_mm = raster.dpi / 25.4
    return PayloadSurvey(
        regions=(SurveyRegion(
            support, support.area_px / (px_per_mm * px_per_mm), 1.0),),
        c_dots=spec.cell_dots,
        cell_pitch_px=raster.dpi * spec.cell_dots / 600.0,
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(None, 1, 1.0, 1, 0, 0, 0),
    )


def _place(fragment, spec, pages, *, with_word: bool):
    raster, support = fragment
    budgets, word = PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
        spec, pages, 0, PlacementConfig())
    return place_survey(
        raster, _survey(raster, support, spec), spec,
        pages=pages, budgets=budgets,
        word_budget=word if with_word else None,
    )


def test_true_fragment_accepts_on_cold_correlation(fixture, fragment) -> None:
    """The blind rung: no word seeding, page 0 only — cold must carry it."""
    result = _place(fragment, fixture.spec, (0,), with_word=False)
    accepted = [row for row in result.placements if not row.redundant]
    assert accepted, [row.reason for row in result.unresolved]
    assert all(row.candidate.page == 0 for row in accepted)
    assert any(row.route == "correlation" for row in accepted)
    assert not result.quarantined_patch_ids


def test_true_fragment_rejects_wrong_page_values(fixture, fragment) -> None:
    """Same seeds, same site geometry, wrong-page values: must refuse.

    This is the v1 form of E022's hardest null (true fragment vs
    same-seed wrong-geometry field): every word site descrambles against
    another counter's codeword, so acceptance here is a false accept.
    Stage A stays enabled — its decoded true counter must be discarded as
    outside the declared page domain, never adopted.
    """
    wrong_pages = (7,)
    assert fixture.spec.max_pages > 7
    result = _place(fragment, fixture.spec, wrong_pages, with_word=True)
    assert result.placements == ()
    assert result.unresolved, "null produced no attempts at all"
    allowed = {
        "winner_failed_heldout_gate", "rival_gap_failed",
        "insufficient_support",
    }
    assert {row.reason for row in result.unresolved} <= allowed
    assert result.hypotheses_evaluated > 0
