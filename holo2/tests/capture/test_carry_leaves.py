"""The H2a carried leaves compose, holo2-only (no ``holo`` on the path).

Numerical equivalence to ``src/holo`` is pinned outside this tree
(``tests/holo2_oracles/``). What this file asserts is the holo2-side contract:
ingest -> footing ladder -> survey runs end to end on nothing but
``holo2``, keeps the capture's dtype, and derives every footing directly
from native.

The page is built by an integer hash of the cell indices — deterministic
and RNG-free, matching this suite's house style.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from holo2.capture.scale_space import (AreaPixelTransform, ScaleSchedule,
                                       area_decimate, auto_ppc_levels,
                                       derive_scale_levels,
                                       native_pixels_per_cell)
from holo2.capture.scan import open_capture
from holo2.capture.survey import (CANDIDATE_PITCHES_IN, candidate_pitches,
                                  region_candidates, survey_raster)

CELL_PX = 4


def _page_at(cell_px: int, height: int = 768, width: int = 768) -> np.ndarray:
    """Paper white with one printed scrap of hash-patterned cells.

    ``cell_px`` is how wide a cell is ON THE CAPTURE, so at a declared
    dpi it fixes the PHYSICAL pitch the survey has to name: 4 px at
    1200 dpi is c2, 3 px at 1200 dpi is 1/400 in (C3b's union case).
    """
    page = np.full((height, width), 235, np.uint8)
    rows, cols = 120, 130
    y, x = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    ink = ((y * 2654435761 + x * 40503 + y * x * 97) >> 3) & 1
    cells = np.kron(ink.astype(bool), np.ones((cell_px, cell_px), bool))
    page[100:100 + cells.shape[0], 110:110 + cells.shape[1]] = np.where(
        cells, 30, 235)
    return page


def _page(height: int = 768, width: int = 768) -> np.ndarray:
    return _page_at(CELL_PX, height, width)


@pytest.fixture(scope="module")
def page() -> np.ndarray:
    return _page()


def test_ingest_authenticates_and_freezes(page: np.ndarray) -> None:
    raster = open_capture(page, 1200.0)
    assert len(raster.source_sha256) == 64
    assert raster.source.shape == page.shape
    assert raster.source.channels == 1
    assert str(raster.native_dtype) == "uint8"
    raster.verify_source_unchanged()          # in-memory: detached at ingest
    crop = raster.crop_native(0, 8, 0, 8)
    assert not crop.flags.writeable


#: The two printed pitches these ladder cases were written at, as the
#: rationals identity carries (C3, RULINGS G4, 2026-08-22): they were
#: spelled ``2`` and ``3`` when the ladder divided by a hard-coded 600.
C2, C3 = Fraction(1, 300), Fraction(1, 200)


def test_footing_ladder_is_derived_from_the_declared_dpi() -> None:
    assert native_pixels_per_cell(1200, C2) == Fraction(4)
    assert auto_ppc_levels(1200, C2) == (Fraction(2), Fraction(4))
    assert auto_ppc_levels(1000, C3) == (
        Fraction(2), Fraction(5, 2), Fraction(5))
    schedule = ScaleSchedule.auto(1200, C2)
    assert [level.label for level in schedule.levels] == [
        "l00-2ppc-600dpi", "l01-4ppc-1200dpi"]
    assert schedule.levels[-1].is_native


def test_the_ladder_refuses_a_dot_count_where_a_pitch_is_asked_for() -> None:
    """The unit's own guard (review fix, C3, 2026-08-22).

    THE FORK THIS PREVENTS: ``native_pixels_per_cell(1200, 2)`` USED to
    raise — the second argument was a dot count, validated as a positive
    integer — and after C3 turned it into a pitch it would return
    ``Fraction(2400)``, a whole footing ladder at 600x the intended
    pitch, because ``Rational`` accepts a bare ``int`` on purpose.  Every
    footing id and every evidence key derived from that ladder would be
    wrong and nothing would say so.
    """
    for dots in (1, 2, 3, 4):
        with pytest.raises(ValueError, match="not a printed cell"):
            native_pixels_per_cell(1200, dots)
        with pytest.raises(ValueError, match="not a printed cell"):
            auto_ppc_levels(1200, dots)
        with pytest.raises(ValueError, match="not a printed cell"):
            ScaleSchedule.auto(1200, dots)


def test_views_come_from_native_not_from_each_other(page: np.ndarray) -> None:
    """ppc 2 derived directly == ppc 2 derived directly (never via a level)."""
    levels = dict(
        (level.ppc, view)
        for level, view in derive_scale_levels(page, ScaleSchedule.auto(4800, C3))
    )
    assert set(levels) == {Fraction(n) for n in (2, 4, 8, 12, 24)}
    for ppc, view in levels.items():
        transform = AreaPixelTransform(Fraction(24) / ppc)
        assert view.dtype == page.dtype
        assert view.shape == transform.output_shape(page.shape)
        assert view.tobytes() == area_decimate(page, transform).tobytes()
    assert levels[Fraction(24)].tobytes() == page.tobytes()  # native is exact


def test_survey_finds_the_scrap_and_names_it(page: np.ndarray) -> None:
    raster = open_capture(page, 1200.0)
    survey = survey_raster(raster)
    assert survey.regions, "the synthetic scrap must be surveyed"
    candidates = region_candidates(raster.source_sha256, survey)
    assert len(candidates) == len(survey.regions)
    biggest = candidates[0]
    y0, x0, height, width = biggest.bbox_px
    assert 60 <= y0 <= 140 and 70 <= x0 <= 150     # near the printed scrap
    assert height > 300 and width > 300
    assert biggest.area_mm2 > 9.0                  # the E021 component floor
    assert biggest.pitch_in_vote == survey.pitch_in
    # A region IS its capture and its support grid: surveying the same
    # capture again names exactly the same regions.
    again = region_candidates(raster.source_sha256, survey_raster(raster))
    assert [(item.capture_sha256, item.support.origin_yx, item.support.step_px,
             item.support.extent_px) for item in again] == [
        (item.capture_sha256, item.support.origin_yx, item.support.step_px,
         item.support.extent_px) for item in candidates]


def test_a_declared_rational_pitch_is_surveyed_where_a_blind_one_is_not(
        ) -> None:
    """C3b (RULINGS H1(b), 2026-08-22): the union, end to end on a raster.

    The page here is the same hash-patterned scrap as the rest of this
    file, printed at THREE pixels a cell and captured at 1200 dpi — a
    physical pitch of 1/400 in, which is lawful, names a format
    (``1i400-k-r0700@...``) and is no registered pitch CLASS.  A blind
    survey finds the region and honestly declines to name its pitch: no
    candidate is within ``C_SNAP_TOLERANCE`` of 3 px (the nearest, c2 at
    4 px, is 25% away).  Handed the row the operator actually declared,
    the same survey votes 1/400 and measures it at 3.0 px.

    THE FORK THIS PREVENTS is the one C3 left behind: ``pitch_in_vote``
    of ``None`` makes ``solve.plans.region_view`` carry every region of
    the capture as UNSCHEDULABLE, so a decode of a lawfully-identified
    sheet places no window and spends no fire — silently, with every
    golden green, because a vote is not part of any identity.  H1(a)
    made such a sheet buildable; without the union it would still have
    been undecodable, which is H1 half-executed.

    A raster is used rather than a synthetic ``_pitch_vote`` (which is
    unit-testable by injecting a ``PitchMeasurement``, as the cross-tree
    oracle does) because the claim worth pinning is about the WHOLE
    survey: that the region is found either way and only the naming
    changes.
    """
    raster = open_capture(_page_at(3), 1200.0)
    declared = Fraction(1, 400)
    assert declared not in CANDIDATE_PITCHES_IN
    assert candidate_pitches(declared) != CANDIDATE_PITCHES_IN

    blind = survey_raster(raster)
    told = survey_raster(raster, declared_pitch_in=declared)
    assert len(blind.regions) == len(told.regions) == 1   # same region...
    assert blind.pitch_in is None and blind.cell_pitch_px is None
    assert told.pitch_in == declared                      # ...named only here
    assert told.cell_pitch_px == pytest.approx(3.0)
    assert region_candidates(raster.source_sha256, blind)[0].pitch_in_vote \
        is None
    assert region_candidates(
        raster.source_sha256, told)[0].pitch_in_vote == declared


def test_a_declared_pitch_class_leaves_the_survey_bit_identical(
        page: np.ndarray) -> None:
    """The other half of the union: a c1..c4 row is a no-op, measured.

    ``candidate_pitches`` returns the blind tuple ITSELF for a declared
    pitch that is already a candidate, so this cannot fail while that
    holds — which is the point.  The declared pitch here is deliberately
    NOT the one this page votes (the scrap's strongest credible line is
    its 6 px harmonic, so the vote is c3 while the row says c2): the
    union is about the candidate SET, and a declared class must not
    steer the vote toward itself either.  It is pinned at the SURVEY
    because that is the claim the verdicts gate is a canary for: every
    row in the corpus sits at a registered class, so C3b could not have
    moved a single decode, and this says so at the one place the union
    enters.
    """
    raster = open_capture(page, 1200.0)
    blind = survey_raster(raster)
    told = survey_raster(raster, declared_pitch_in=Fraction(1, 300))
    assert blind.pitch_in is not None                 # it names one...
    assert blind.pitch_in == told.pitch_in            # ...and the same one
    assert blind.cell_pitch_px == told.cell_pitch_px
    assert [(vote.pitch_in, vote.pitch_px) for vote in blind.pitch_votes] == [
        (vote.pitch_in, vote.pitch_px) for vote in told.pitch_votes]
    assert [region.bbox for region in blind.regions] == [
        region.bbox for region in told.regions]


def test_rgb_capture_surveys_through_the_luma_contract(page: np.ndarray) -> None:
    rgb = np.stack([page, page, page], axis=2)
    raster = open_capture(rgb, 1200.0)
    assert raster.source.channels == 3
    grey = open_capture(page, 1200.0)
    # Equal channels reduce to the same raw luma, so the survey agrees.
    assert [region.bbox for region in survey_raster(raster).regions] == [
        region.bbox for region in survey_raster(grey).regions]
