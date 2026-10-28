"""Oracle: holo2.survey == holo.receive.survey (E021 region survey).

Compares the carried leaves — ``survey.py``, ``_survey_tensor.py`` and
the ``lattice.py`` pitch measurement they need — against their sources
on a grey capture, an RGB capture and a 16-bit capture: the structure-
tensor score (byte-exact), the support masks (byte-exact), the cell-
pitch vote, and every survey diagnostic.

THE ONE DECLARED ADAPTATION (C3, RULINGS G4, 2026-08-22): ``src/holo``
votes a count of 600-dpi engine dots (``_snap_c``), holo2 votes the
PRINTED PITCH itself (``_snap_pitch``) over a candidate set handed in at
the call.  Every comparison here passes the BLIND set
``CANDIDATE_PITCHES_IN``, which is what ``survey_raster`` uses when no
row is declared (C3b, RULINGS H1(b), 2026-08-22) — the union with a
declared row's pitch is holo2's own and has no counterpart to compare
against, so it is pinned inside ``holo2/tests`` instead.

Every comparison below converts at the boundary with :func:`_as_pitch`,
so the two are proven equal rather than assumed so — and
:func:`test_snap_equivalence_and_its_one_narrowing`
states exactly where they part company (a measurement 5..12 dots wide,
which ``src/holo`` snaps and holo2 declines because no format names that
pitch).

holo's tiled tensor path is pinned to its ``--workers 1`` execution by
the ``holo_sequential`` fixture — that is the path holo2's inlined
sequential loop reproduces (H3 owns holo2 concurrency).
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

import holo2.capture.scan as h2scan
import holo2.capture.survey as h2
import holo2.capture._survey_tensor as h2t
import holo2.capture.lattice as h2l
from holo.receive import scan as h1scan
from holo.receive import survey as h1
from holo.receive import _survey_tensor as h1t
from holo.receive import lattice as h1l
from _oracle_fixtures import (  # noqa: F401  (pytest fixtures)
    grey_page, holo_sequential, rgb_page, small_grey)


def _rasters(array: np.ndarray, dpi: float = 1200.0):
    return h1scan.open_capture(array, dpi), h2scan.open_capture(array, dpi)


def _support_facts(mask) -> tuple:
    return (mask.origin_yx, mask.step_px, mask.extent_px, mask.bbox,
            mask.cells.shape, mask.area_px, mask.cells.tobytes())


#: The engine grid ``src/holo``'s survey snaps against (``h1.PRINT_DPI``,
#: as the integer it denotes).  A fact about the SOURCE: holo2's own
#: survey names no engine (C3, RULINGS G4, 2026-08-22).
_SOURCE_ENGINE_DPI = int(h1.PRINT_DPI)


def _as_pitch(c_dots: int | None) -> Fraction | None:
    """``src/holo``'s dot count as the pitch holo2 votes (1/600 in each)."""
    return None if c_dots is None else Fraction(c_dots, _SOURCE_ENGINE_DPI)


def _holo_facts(survey) -> tuple:
    """``src/holo``'s survey, restated in holo2's units."""
    diagnostics = survey.diagnostics
    return (
        len(survey.regions),
        _as_pitch(survey.c_dots),
        survey.cell_pitch_px,
        tuple((_as_pitch(vote.c_dots), vote.pitch_px)
              for vote in survey.pitch_votes),
        (diagnostics.threshold, diagnostics.survey_step_px,
         diagnostics.survey_scale_px, diagnostics.component_count,
         diagnostics.refinement_tiles, diagnostics.refinement_scored_cells,
         diagnostics.refinement_grid_cells, diagnostics.refinement_fraction),
        tuple((_support_facts(region.support), region.area_mm2,
               region.median_tensor_score, region.bbox)
              for region in survey.regions),
    )


def _survey_facts(survey) -> tuple:
    diagnostics = survey.diagnostics
    return (
        len(survey.regions),
        survey.pitch_in,
        survey.cell_pitch_px,
        tuple((vote.pitch_in, vote.pitch_px) for vote in survey.pitch_votes),
        (diagnostics.threshold, diagnostics.survey_step_px,
         diagnostics.survey_scale_px, diagnostics.component_count,
         diagnostics.refinement_tiles, diagnostics.refinement_scored_cells,
         diagnostics.refinement_grid_cells, diagnostics.refinement_fraction),
        tuple((_support_facts(region.support), region.area_mm2,
               region.median_tensor_score, region.bbox)
              for region in survey.regions),
    )


@pytest.fixture(scope="session")
def surveys(grey_page, rgb_page, small_grey):
    """Every survey this module compares, computed once."""
    wide = (small_grey.astype(np.uint16) * 256)
    cases = {
        "grey": (grey_page, 1200.0),
        "rgb": (rgb_page, 1200.0),
        "small": (small_grey, 1200.0),
        "uint16": (wide, 1200.0),
        "coarse_dpi": (small_grey, 600.0),
    }
    out = {}
    for name, (array, dpi) in cases.items():
        one, two = _rasters(array, dpi)
        out[name] = (one, two, h1.survey_raster(one), h2.survey_raster(two))
    return out


@pytest.mark.parametrize(
    "case", ["grey", "rgb", "small", "uint16", "coarse_dpi"])
def test_survey_raster_matches(surveys, case: str) -> None:
    _, _, one, two = surveys[case]
    assert _survey_facts(two) == _holo_facts(one)


def test_grey_and_rgb_surveys_are_substantive(surveys) -> None:
    """The comparison must be over a survey that actually found something."""
    for case in ("grey", "rgb"):
        _, _, one, _ = surveys[case]
        assert len(one.regions) == 2, case
        assert one.c_dots == 2 and one.cell_pitch_px == pytest.approx(4.0), case
        assert _as_pitch(one.c_dots) == Fraction(1, 300), case   # c2
        # The pitch-scale refinement path ran (not just the coarse fallback).
        assert one.diagnostics.refinement_tiles > 0, case
        assert one.diagnostics.refinement_scored_cells > 0, case


@pytest.mark.parametrize("case", ["grey", "rgb", "uint16"])
def test_support_rasterization_matches(surveys, case: str) -> None:
    _, _, one, two = surveys[case]
    for region_one, region_two in zip(one.regions, two.regions, strict=True):
        assert (region_two.support.rasterize().tobytes()
                == region_one.support.rasterize().tobytes())
        y0, x0, height, width = region_one.support.bbox
        crop = (max(0, y0 - 40), y0 + height + 40,
                max(0, x0 - 40), x0 + width + 40)
        assert (region_two.support.rasterize_crop(*crop).tobytes()
                == region_one.support.rasterize_crop(*crop).tobytes())


@pytest.mark.parametrize("case", ["grey", "rgb", "uint16"])
def test_whole_tensor_score_bytes(surveys, case: str) -> None:
    """The E021 kernel itself — holo2's sequential tiling vs holo's pool."""
    one_raster, two_raster, _, _ = surveys[case]
    pitch_px = 0.34 * one_raster.dpi / 25.4
    for tile_cells in (256, 64, 7, 10_000):
        score_one, step_one = h1t._whole_tensor_score(
            one_raster, pitch_px, tile_cells=tile_cells)
        score_two, step_two = h2t._whole_tensor_score(
            two_raster, pitch_px, tile_cells=tile_cells)
        assert step_two == step_one
        assert score_two.dtype == score_one.dtype == np.float32
        assert score_two.tobytes() == score_one.tobytes(), tile_cells


@pytest.mark.parametrize("workers", [1, 2, 4, 8])
def test_holo2_sequential_matches_holo_at_any_worker_count(
    surveys, workers: int
) -> None:
    """The inlined loop is not merely equal to ``--workers 1``.

    holo2 dropped the pool, so the claim that matters operationally is
    that its sequential result equals holo's result at the worker counts
    holo actually runs with — not just at the one the rest of this module
    pins.  (holo owns the same claim internally; this is the cross-package
    form of it, and it is what makes the H3 concurrency work a free
    choice rather than a numerics decision.)
    """
    from holo.receive import _parallel

    one_raster, two_raster, _, _ = surveys["grey"]
    pitch_px = 0.34 * one_raster.dpi / 25.4
    score_two, step_two = h2t._whole_tensor_score(two_raster, pitch_px)
    _parallel.set_worker_count(workers)
    try:
        score_one, step_one = h1t._whole_tensor_score(one_raster, pitch_px)
        survey_one = h1.survey_raster(one_raster)
    finally:
        _parallel.set_worker_count(1)
    assert step_two == step_one
    assert score_two.tobytes() == score_one.tobytes()
    assert _survey_facts(h2.survey_raster(two_raster)) == _holo_facts(
        survey_one)


def test_score_crop_and_feature_luma(surveys) -> None:
    one_raster, two_raster, _, _ = surveys["rgb"]
    box = (128, 640, 96, 608)
    assert (h2t._feature_luma(two_raster, *box).tobytes()
            == h1t._feature_luma(one_raster, *box).tobytes())
    for pitch_px in (4.0, 16.06299212598, 24.0):
        patch_one, step_one = h1t._score_crop(
            one_raster, pitch_px=pitch_px, box=box)
        patch_two, step_two = h2t._score_crop(
            two_raster, pitch_px=pitch_px, box=box)
        assert step_two == step_one
        assert patch_two.tobytes() == patch_one.tobytes()


@pytest.mark.parametrize(
    "cell_px", [1.0, 2.0, 3.5, 4.0, 6.0, 16.062992125984252, 24.0, 96.0])
def test_tensor_geometry(cell_px: float) -> None:
    assert h2t.tensor_geometry(cell_px) == h1t.tensor_geometry(cell_px)


def test_tensor_constants_and_halo() -> None:
    assert (h2t.WORK_CELL_PX, h2t.DERIVATIVE_CELLS, h2t.TENSOR_CELLS,
            h2t.TENSOR_TILE_CELLS) == (
        h1t.WORK_CELL_PX, h1t.DERIVATIVE_CELLS, h1t.TENSOR_CELLS,
        h1t.TENSOR_TILE_CELLS)
    for pitch_work_px in (1.0, 4.0, 4.015, 8.0):
        for sample in (1, 2, 4):
            assert (h2t._tensor_halo_cells(pitch_work_px, sample)
                    == h1t._tensor_halo_cells(pitch_work_px, sample))


def test_survey_constants() -> None:
    for name in ("SURVEY_CELL_UM", "DENSITY_MIN", "MIN_AREA_MM2",
                 "C_SNAP_TOLERANCE", "SUPPORT_HOLE_RADIUS_CELLS",
                 "REFINE_BOUNDARY_SURVEY_CELLS", "REFINE_VALLEY_FRACTION",
                 "REFINE_VALLEY_RUN", "REFINE_VALLEY_MIN_SPAN_FRACTION",
                 "REFINE_VALLEY_HALO_SURVEY_CELLS", "REFINE_TILE_CELLS",
                 "REFINE_TILE_HALO_CELLS", "PITCH_PROBES_PX"):
        assert getattr(h2, name) == getattr(h1, name), name
    # ``PRINT_DPI`` and ``MAX_C_DOTS`` left holo2 at C3 (RULINGS G4) and
    # are therefore not compared but RELATED: holo2's candidate set is
    # exactly a subset of the dot ladder they described, so the two
    # leaves still speak about the same lattice.
    assert not hasattr(h2, "PRINT_DPI") and not hasattr(h2, "MAX_C_DOTS")
    for candidate in h2.CANDIDATE_PITCHES_IN:
        dots = candidate * _SOURCE_ENGINE_DPI
        assert dots.denominator == 1, candidate
        assert 1 <= dots <= h1.MAX_C_DOTS, candidate


def test_support_mask_hole_filling(small_grey: np.ndarray) -> None:
    """The topology-aware support completion, on constructed activity."""
    activity = np.zeros((60, 60), bool)
    activity[5:55, 5:55] = True
    activity[10:12, 10:12] = False      # a small enclosed dropout: filled
    activity[20:34, 20:34] = False      # a large enclosed dropout: kept
    activity[0:3, 0:3] = True           # a detached corner: exterior
    for radius in (0.0, 1.0, 3.0, 8.0, 40.0):
        one = h1.support_mask(activity, radius)
        two = h2.support_mask(activity, radius)
        assert two.tobytes() == one.tobytes(), radius
        assert two.dtype == one.dtype == np.bool_


def test_adaptive_threshold(small_grey: np.ndarray) -> None:
    rng = np.random.default_rng(99)
    cases = [
        np.zeros((32, 32), np.float32),
        np.full((16, 16), -1.0, np.float32),
        rng.random((64, 64)).astype(np.float32) * 40.0,
        small_grey.astype(np.float32),
        np.array([[np.inf, 1.0], [2.0, 3.0]], np.float32),
    ]
    # -1.0 and inf are deliberate: log1p warns identically in both copies.
    with np.errstate(divide="ignore", invalid="ignore"):
        for score in cases:
            assert h2._adaptive_threshold(score) == h1._adaptive_threshold(score)


def test_full_support(small_grey: np.ndarray) -> None:
    one_raster, two_raster = _rasters(small_grey)
    assert (_support_facts(h2.full_support(two_raster))
            == _support_facts(h1.full_support(one_raster)))


def test_support_mask_refusals_match() -> None:
    good = dict(origin_yx=(0, 0), step_px=4, cells=np.ones((3, 3), bool),
                extent_px=(12, 12))
    assert _support_facts(h2.SupportMask(**good)) == _support_facts(
        h1.SupportMask(**good))
    broken = [
        dict(origin_yx=(-1, 0)), dict(step_px=0), dict(extent_px=(0, 12)),
        dict(cells=np.zeros((3, 3), bool)), dict(extent_px=(40, 12)),
        dict(cells=np.ones((3, 3, 3), bool)),
    ]
    for override in broken:
        with pytest.raises(ValueError) as excinfo_one:
            h1.SupportMask(**dict(good, **override))
        with pytest.raises(ValueError) as excinfo_two:
            h2.SupportMask(**dict(good, **override))
        assert str(excinfo_two.value) == str(excinfo_one.value), override


def test_support_mask_is_frozen(small_grey: np.ndarray) -> None:
    mask = h2.SupportMask((0, 0), 4, np.ones((3, 3), bool), (12, 12))
    assert not mask.cells.flags.writeable
    with pytest.raises(ValueError):
        mask.cells[0, 0] = False


# -- the carried lattice measurement (survey's c_dots input) ----------------


def test_lattice_pitch_measurement(small_grey: np.ndarray, grey_page) -> None:
    crops = [grey_page[200:600, 200:600], small_grey[100:480, 120:500],
             small_grey[:64, :64]]
    for crop in crops:
        for probes in (h1l.PITCH_PROBES_PX, h1.PITCH_PROBES_PX, (4.0, 8.0)):
            try:
                one = h1l.measure_cell_pitch(crop, probes_px=probes)
            except ValueError as exc_one:
                # The refusal classes are distinct objects by construction
                # (holo2.lattice.LatticeNotFound); compare name + message.
                with pytest.raises(ValueError) as excinfo_two:
                    h2l.measure_cell_pitch(crop, probes_px=probes)
                assert type(excinfo_two.value).__name__ == type(exc_one).__name__
                assert str(excinfo_two.value) == str(exc_one)
                assert getattr(excinfo_two.value, "pitch_px", None) == getattr(
                    exc_one, "pitch_px", None)
                continue
            two = h2l.measure_cell_pitch(crop, probes_px=probes)
            assert (two.pitch_px, two.angle_rad, two.contrast) == (
                one.pitch_px, one.angle_rad, one.contrast)
            assert two.candidates == one.candidates
            assert two.strong == one.strong


def test_lattice_constants() -> None:
    assert (h2l.PITCH_PROBES_PX, h2l.CONTRAST_FLOOR, h2l.MEASURE_WINDOW_PX,
            h2l.RATIO_TOLERANCE, h2l.DEDUPE_TOLERANCE) == (
        h1l.PITCH_PROBES_PX, h1l.CONTRAST_FLOOR, h1l.MEASURE_WINDOW_PX,
        h1l.RATIO_TOLERANCE, h1l.DEDUPE_TOLERANCE)


@pytest.mark.parametrize("pitch_px", [1.9, 3.98, 4.0, 4.3, 24.0, 26.0, 200.0])
def test_snap_c(pitch_px: float) -> None:
    """holo2's pitch snap IS ``src/holo``'s dot snap, in inches.

    Except in the narrowed band, which this case list reaches at 24 px /
    1200 dpi (12 dots — a pitch no format names): there holo2 declines,
    and the sweep below is where that is stated as a rule rather than as
    an exception in a parametrize list.
    """
    for dpi in (600.0, 1200.0, 4800.0):
        theirs = _as_pitch(h1._snap_c(pitch_px, dpi))
        ours = h2._snap_pitch(pitch_px, dpi, h2.CANDIDATE_PITCHES_IN)
        if theirs is not None and theirs not in h2.CANDIDATE_PITCHES_IN:
            assert ours is None
        else:
            assert ours == theirs


def test_snap_equivalence_and_its_one_narrowing() -> None:
    """The C3 adaptation, swept: where the two agree, and where they do not.

    THE ONE fork this pins (RULINGS G4, 2026-08-22): holo2 votes a
    PRINTED PITCH and ``src/holo`` votes 600-dpi engine dots, so if the
    pitch form were not the same decision, every window lattice on every
    capture would move while every golden seed stayed green — a silent
    re-place of the whole receiver.  Over the shared candidate set the
    two agree on every accept AND every refusal; the only difference is
    that a measurement 5..12 dots wide (a pitch no format names) snaps
    there and honestly declines here.

    The scan is deterministic (seeded) and covers the boundary shells of
    every candidate, where a metric difference — nearest-by-rounding
    versus nearest-by-ratio — would show up if there were one.

    It exercises ONE line at a time, which is why
    :func:`test_pitch_vote_composition_over_several_lines` exists: the
    survey's vote is a maximum over all the snapped lines of a crop, and
    that composition has a divergence this sweep cannot see.
    """
    import random

    rng = random.Random(20260822)
    narrowed = 0
    for _ in range(20_000):
        dpi = rng.choice([600.0, 1200.0, 1600.0, 2400.0, 4800.0, 1197.6])
        pitch_px = rng.uniform(0.5, 110.0)
        theirs = h1._snap_c(pitch_px, dpi)
        ours = h2._snap_pitch(pitch_px, dpi, h2.CANDIDATE_PITCHES_IN)
        if theirs is not None and _as_pitch(theirs) not in (
                h2.CANDIDATE_PITCHES_IN):
            assert ours is None, (pitch_px, dpi, theirs)
            narrowed += 1
            continue
        assert ours == _as_pitch(theirs), (pitch_px, dpi)
    assert narrowed > 0, "the sweep must actually reach the narrowed band"
    # The boundary shells, exactly: 4% inside and outside each candidate.
    for dpi in (600.0, 1200.0, 2400.0, 4800.0):
        for candidate in h2.CANDIDATE_PITCHES_IN:
            exact = float(candidate) * dpi
            for factor in (1.0, 1.039, 0.961, 1.041, 0.959):
                px = exact * factor
                assert (h2._snap_pitch(px, dpi, h2.CANDIDATE_PITCHES_IN)
                        == _as_pitch(h1._snap_c(px, dpi))), (candidate, factor)


def _both_votes(lines: list[tuple[float, float]], dpi: float,
                monkeypatch) -> tuple:
    """``_pitch_vote`` on both trees, over the same credible spectral lines.

    The measurement is INJECTED, not measured: what is under test is
    "which of several snapped lines becomes the vote", and hunting for a
    crop whose spectrum reliably shows two named lines would pin the
    fixture, not the composition.  Each tree gets its own
    ``PitchMeasurement`` type — they are distinct classes by the firewall.
    """
    crop = np.zeros((64, 64), np.float32)
    for module, kind in ((h1, h1l.PitchMeasurement), (h2, h2l.PitchMeasurement)):
        measurement = kind(lines[0][0], 0.0, lines[0][1],
                           tuple(lines), tuple(lines))
        monkeypatch.setattr(module, "measure_cell_pitch",
                            lambda *a, _m=measurement, **k: _m)
    theirs = h1._pitch_vote(crop, dpi)
    ours = h2._pitch_vote(crop, dpi, h2.CANDIDATE_PITCHES_IN)
    return (
        None if theirs is None else (_as_pitch(theirs.c_dots), theirs.pitch_px),
        None if ours is None else (ours.pitch_in, ours.pitch_px),
    )


def test_pitch_vote_composition_over_several_lines(monkeypatch) -> None:
    """The snap is equivalent per LINE; the vote is a maximum OVER lines.

    THE FORK THIS PINS (review fix, C3, 2026-08-22): the sweep above
    exercises ``_snap_pitch`` in isolation and therefore cannot see
    ``_pitch_vote``'s ``max`` over the snapped lines.  When the largest
    credible line is out of set holo2 does NOT decline the crop — it
    falls to the largest IN-SET line and returns a different pitch and a
    different ``pitch_px`` from ``src/holo``'s.  That is the direction an
    in-scope sheet wants (a c3 region whose 2x harmonic dominated used to
    vote a 6-dot lattice no row spells, and now votes c3), and an edit
    that "hardened" holo2 into declining the whole crop — the reading
    "refusing a 5-dot measurement is not a lost decode" invites — would
    silently un-place exactly those regions with every golden still green.
    """
    # Both lines in set: the two trees agree, maximum and all.
    assert _both_votes([(4.0, 100.0), (2.0, 90.0)], 600.0, monkeypatch) == (
        (Fraction(1, 150), 4.0), (Fraction(1, 150), 4.0))
    # The largest line is OUT of set (6 px at 600 dpi = 6 dots = 1/100 in):
    # src/holo votes it, holo2 falls to the c3 line beneath it.
    assert _both_votes([(6.0, 100.0), (3.0, 90.0)], 600.0, monkeypatch) == (
        (Fraction(6, 600), 6.0), (Fraction(1, 200), 3.0))
    # No in-set line at all: only then does holo2 decline the crop.
    assert _both_votes([(6.0, 100.0)], 600.0, monkeypatch) == (
        (Fraction(6, 600), 6.0), None)
