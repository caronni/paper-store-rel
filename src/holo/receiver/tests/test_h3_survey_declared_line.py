"""A vote FINER than the declared row is not always a misdeclared dpi.

MEASURED 2026-10-02 (Canon iR-ADV C257, sheet H `c2-cmy8-r0775@53x37`):
both 4800 dpi captures refused the resume with "voted printed pitch
1/600 in, but the declared format row is 1/300 in", while all four 2400
captures of the same sheet surveyed cleanly.  At 4800 a c2 cell is 16
px and the engine's dot lattice 8 px; the vote's per-band contrast is
peak over the band's median, that median rises with pitch, and the 16
px line read ~15 against the floor of 30 on the one central crop per
component.  What cleared the floor was {11.31, 8.00, 4.76} px: no
integer ratios, the loudest line (8) chosen, a class finer, refused.
Eight of nine other crops of the same page voted 1/300.

THE GUARD (survey._finer_vote_cause) asks the narrower question such a
vote raises: is the DECLARED lattice on the page, two perpendicular
lines at exactly the declared pitch (lib/pitch_line.declared_line)?  If
it is, in a strict majority of the regions that gave a verdict, the
finer vote was the row's own harmonic and the capture proceeds as the
D5 fallback; otherwise it refuses as before, now naming the line.  A
COARSER vote — the e033.2 misdeclared-dpi direction — refuses
unconditionally and never consults the line.

The statistic's measured basis, on real crops (scratch evidence, not
test material, so recorded here; contrast at the declared pitch P and at
2P on the vote's 2048 window):

    sheet H 4800 a, run's component crop    5.74 / 1.77
    sheet H 4800 a, scan centre             6.12 / 2.62
    sheet H 4800 b, run's component crop    6.25 / 2.49
    sheet H 4800 b, scan centre             6.39 / 2.23
    sheet G 4800, component crop           14.37 / 2.33
    sheet G 4800, scan centre              13.38 / 2.62
    sheet H 2400 a, scan centre            12.23 / 3.04
    sheet G 2400, scan centre              12.87 / 2.37

and the readers' null: 136 empty rings read at most 3.72.  The guard
reads a 4096 window (LINE_WINDOW_PX), where the same captures read: H
11.0-20.4 at P, G 19.9-25.2, empty rings at most 4.85 (five windows per
capture, 2026-10-03) -- LINE_FLOOR 7.0 sits between.

THE STIMULUS is the module lattice of test_h3_plugins_intake_survey (6
px cells at 1200 dpi, 1/200 in).  The real misfire has no synthetic
twin — a random binary lattice carries no dot sub-lattice to outvote
its cell line — so the finer vote is stimulated by patching
`survey._pitch_vote` to return one; the refusal is real: declared 1/100
in (12 px) against the 6 px lattice votes 1/200, finer, and a 6 px
lattice has no 12 px line.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver import data, engine
from holo.receiver.format.identity import Family
from holo.receiver.lib import pitch_line
from holo.receiver.plugins import intake, survey
from holo.receiver.tests.test_h3_plugins_intake_survey import (
    LATTICE_DPI,
    LATTICE_MARGIN_PX,
    LATTICE_PITCH_IN,
    LATTICE_PITCH_PX,
    _lattice_grey,
)

DECLARED_PX = float(LATTICE_PITCH_IN) * LATTICE_DPI
FINER_VOTE = (Fraction(1, 300), 4.0)
TOO_COARSE_A_ROW = Fraction(1, 100)
FORCED_CAUSE = "declared dpi forced (--dpi-force)"
#: 96 px holds 61 ring bins at 6 px, 112 px holds 92: the 64-bin floor
#: falls between them.
SCRAP_SIDE_PX = 96
SMALLEST_JUDGED_SIDE_PX = 112


@pytest.fixture(scope="module")
def lattice() -> np.ndarray:
    return _lattice_grey()


def _capture_and_planes(tmp_path: Path, image: np.ndarray,
                        dpi_forced: bool = False,
                        ) -> tuple[data.Capture, tuple]:
    plane_dir = tmp_path / "planes"
    plane_dir.mkdir(parents=True, exist_ok=True)
    levels = intake.build_levels(LATTICE_DPI, LATTICE_PITCH_IN, image.shape)
    native_index = levels[-1].index
    path = intake.plane_path(plane_dir, native_index, intake.PLANE_GREY)
    np.save(path, image)
    raster = data.PlaneRaster("cap", native_index, intake.PLANE_GREY, path,
                              image.shape)
    capture = data.Capture(
        capture_id="cap", path=tmp_path / "scan.tiff", dpi=LATTICE_DPI,
        shape_px=image.shape, channels=1, platen_backing=240.0,
        levels=levels, plane_dir=plane_dir, dpi_forced=dpi_forced)
    return capture, (raster,)


def _fallbacks(events: tuple) -> tuple[data.SurveyPitchFallback, ...]:
    return tuple(event for event in events
                 if isinstance(event, data.SurveyPitchFallback))


def test_the_declared_line_is_present_at_the_lattice_pitch(lattice):
    verdict = pitch_line.declared_line(lattice, DECLARED_PX)
    assert verdict is not None and verdict.present
    assert verdict.contrast >= pitch_line.LINE_FLOOR
    assert verdict.pitch_px == pytest.approx(
        LATTICE_PITCH_PX, rel=pitch_line.C_SNAP_TOLERANCE)


def test_the_declared_line_is_absent_at_twice_the_lattice_pitch(lattice):
    """2P is what a row declared a class too coarse would look for."""
    verdict = pitch_line.declared_line(lattice, 2.0 * DECLARED_PX)
    assert verdict is not None
    assert not verdict.present
    assert verdict.contrast < pitch_line.LINE_FLOOR


def test_a_scrap_too_small_for_the_ring_gives_no_verdict(lattice):
    def crop(side: int) -> np.ndarray:
        y0 = LATTICE_MARGIN_PX
        return lattice[y0:y0 + side, y0:y0 + side]

    assert pitch_line.declared_line(crop(SCRAP_SIDE_PX), DECLARED_PX) is None
    judged = pitch_line.declared_line(crop(SMALLEST_JUDGED_SIDE_PX),
                                      DECLARED_PX)
    assert judged is not None and judged.present


JUDGEMENTS = (
    ((), False, "declared lattice untested: no region large enough to "
                "judge"),
    ((8.0,), True, "declared lattice present: line 8.0 at 16.0 px, "
                   "present in 1 of 1 regions"),
    ((4.9,), False, "declared lattice absent: line 4.9 at 16.0 px, "
                    "present in 0 of 1 regions"),
    ((8.0, 4.9), False, "declared lattice absent: line 8.0 at 16.0 px, "
                        "present in 1 of 2 regions"),
    ((8.0, 4.9, 9.5), True, "declared lattice present: line 9.5 at 16.0 "
                            "px, present in 2 of 3 regions"),
)


@pytest.mark.parametrize("contrasts,present,detail", JUDGEMENTS,
                         ids=[str(row[0]) for row in JUDGEMENTS])
def test_the_lattice_is_present_in_a_strict_majority_of_verdicts(
        contrasts, present, detail):
    verdicts = tuple(pitch_line.LineVerdict(16.0, contrast)
                     for contrast in contrasts)
    assert pitch_line.judge(verdicts) == (present, detail)


def test_a_finer_vote_over_a_present_declared_lattice_proceeds_at_it(
        tmp_path, lattice, monkeypatch, capsys):
    calls: list[float] = []

    def finer(crop: np.ndarray, dpi: float, pitches: tuple) -> tuple:
        calls.append(dpi)
        return FINER_VOTE

    monkeypatch.setattr(survey, "_pitch_vote", finer)
    capture, planes = _capture_and_planes(tmp_path, lattice)
    result, events = survey.survey_capture(capture, planes, LATTICE_PITCH_IN)
    assert calls, "the patched vote never ran: the stimulus proves nothing"
    assert result.pitch_class is None
    assert result.pitch_px == DECLARED_PX
    assert len(result.regions) == 1
    fallbacks = _fallbacks(events)
    assert len(fallbacks) == 1
    assert fallbacks[0].pitch_px == DECLARED_PX
    assert fallbacks[0].cause.startswith(
        "finer vote 1/300 in, declared lattice present: line ")
    assert fallbacks[0].cause.endswith("present in 1 of 1 regions")
    stderr = capsys.readouterr().err
    assert "voted no printed pitch (finer vote 1/300 in" in stderr, stderr
    assert "proceeding on the declared pitch 1/200 in" in stderr
    # An accepted capture is surveyed again as a forced one, so its
    # products are the forced survey's, refinement included -- not the
    # first pass's regions refined at the harmonic the vote named.
    forced, _ = survey.survey_capture(
        *_capture_and_planes(tmp_path, lattice, dpi_forced=True),
        LATTICE_PITCH_IN)
    assert result.pitch_px == forced.pitch_px
    assert _region_keys(result) == _region_keys(forced)
    assert all(np.array_equal(a.cells, b.cells)
               for a, b in zip(result.regions, forced.regions))


def _region_keys(found: data.CaptureSurvey) -> tuple:
    return tuple((region.origin_yx, region.step_px, region.extent_px,
                  region.area_mm2, region.median_tensor_score)
                 for region in found.regions)


def test_a_finer_vote_over_an_absent_declared_lattice_still_refuses(
        tmp_path, lattice):
    view = survey.NativeView(dpi=LATTICE_DPI, shape=lattice.shape,
                             planes=(lattice,))
    assert survey.survey_view(view, TOO_COARSE_A_ROW)[1] == LATTICE_PITCH_IN
    capture, planes = _capture_and_planes(tmp_path, lattice)
    with pytest.raises(ValueError) as excinfo:
        survey.survey_capture(capture, planes, TOO_COARSE_A_ROW)
    message = str(excinfo.value)
    assert "voted printed pitch 1/200 in" in message
    assert "declared format row is 1/100 in" in message
    assert "(declared lattice absent: line " in message
    assert "present in 0 of 1 regions)" in message


def test_a_coarser_vote_refuses_without_ever_reading_the_line(
        tmp_path, lattice, monkeypatch):
    """The e033.2 direction: the refusal text is today's, to the letter."""
    read: list[float] = []
    monkeypatch.setattr(pitch_line, "declared_line",
                        lambda image, pitch_px: read.append(pitch_px))
    capture, planes = _capture_and_planes(tmp_path, lattice)
    with pytest.raises(ValueError) as excinfo:
        survey.survey_capture(capture, planes, Fraction(1, 300))
    assert str(excinfo.value) == (
        "survey of capture cap voted printed pitch 1/200 in, but the "
        "declared format row is 1/300 in")
    assert read == []


def test_a_trusted_declaration_takes_no_vote_and_works_at_the_declared_pitch(
        tmp_path, lattice, monkeypatch, capsys):
    def no_vote(*_args: object) -> object:
        raise AssertionError("a forced dpi must not vote")

    monkeypatch.setattr(survey, "_pitch_vote", no_vote)
    view = survey.NativeView(dpi=LATTICE_DPI, shape=lattice.shape,
                             planes=(lattice,))
    regions, voted, pitch_px, _score, _step = survey.survey_view(
        view, LATTICE_PITCH_IN, trust_declared=True)
    assert voted is None
    assert pitch_px == DECLARED_PX
    assert len(regions) == 1

    capture, planes = _capture_and_planes(tmp_path, lattice,
                                          dpi_forced=True)
    result, events = survey.survey_capture(capture, planes, LATTICE_PITCH_IN)
    assert result.pitch_class is None
    assert result.pitch_px == DECLARED_PX
    assert _fallbacks(events) == (data.SurveyPitchFallback(
        capture="cap", declared_pitch_in="1/200", pitch_px=DECLARED_PX,
        n_regions=1, cause=FORCED_CAUSE),)
    assert f"voted no printed pitch ({FORCED_CAUSE}); proceeding" in (
        capsys.readouterr().err)


def _write_scans(tmp_path: Path, image: np.ndarray) -> tuple[Path, Path]:
    import tifffile

    first, second = tmp_path / "a.tiff", tmp_path / "b.tiff"
    tifffile.imwrite(first, image)
    tifffile.imwrite(second, image[:, ::-1].copy())
    return first, second


def test_the_forced_flag_reaches_each_capture_padded_to_one_per_scan(
        tmp_path, lattice):
    first, second = _write_scans(tmp_path, lattice)
    row = SimpleNamespace(pitch_in=LATTICE_PITCH_IN, family=Family.K)
    request = data.DecodeRequest(
        scans=(first, second), dpis=(LATTICE_DPI, LATTICE_DPI),
        format_ref="unused", max_pages=None, workers=1, complete=False,
        no_close=False, diag_port=None, run_dir=tmp_path / "run",
        dpi_forced=(True,))
    captures, _rasters, _events = engine._intake_run(request, row)
    assert tuple(capture.dpi_forced for capture in captures) == (
        True, False)


def test_one_source_declared_both_voted_and_forced_is_refused(
        tmp_path, lattice):
    first, _second = _write_scans(tmp_path, lattice)
    with pytest.raises(ValueError,
                       match="declared both --dpi and --dpi-force"):
        intake.ingest_captures(
            (first, first), (LATTICE_DPI, LATTICE_DPI), LATTICE_PITCH_IN,
            Family.K, tmp_path / "run", forced=(False, True))
