"""A capture whose survey votes NO printed pitch is not lost.

The survey snaps each component's measured cell spacing to a candidate
pitch and takes the plurality.  Two outcomes have always been distinct
and were treated alike:

  CONTRADICTION — a clear vote that disagrees with the declared format
    row.  The run refuses, loudly.  That refusal STAYS: it is the
    e033.2 misdeclared-dpi catch, and every certificate minted after it
    would be recorded against a geometry nobody declared.  Its test is
    `test_h3_plugins_intake_survey.py::
    test_survey_capture_refuses_a_declared_pitch_the_sheet_contradicts`.

  NO VOTE — a tie, or nothing that snaps.  This used to leave the
    capture with `pitch_px` None, and a survey with no pitch built no
    frames, so the capture contributed no windows at all: a whole scan
    lost in silence, on exactly the fragment and confetti material that
    votes worst (few components, cut edges, mixed sheets).  Ported from
    v1 on 2026-09-04 (RULINGS.md D5, `k-placement-07`): warn, and work
    at the DECLARED pitch, which is the pitch `place.region_frame`
    builds every frame on either way.

THE STIMULUS is a TIE, because a tie is the only no-vote cause that
leaves a decodable payload on the sheet — so the proof can be "the
capture is read", not merely "windows appear".  It is also real
material: a platen load of scraps from two sheets of different codings
is the case `placement-24` names.  The K sim page (one component, one
vote for its 1/200 in row) gets one 24-cell patch at 1/150 in — another
CANDIDATE pitch, so it snaps and votes — laid in a paper strip beside
it with a 96 px gap so the two never merge into one component.  One
vote each, no plurality, no vote.

Measured on this stimulus at workers 1, `--max-pages 1` (2026-09-04):

  before  1 job (the survey), frontier queued 0, 0 certificates,
          run open, NOT RECOVERED — the page was never addressed
  after   48 certificates, close VERIFIED, payload byte-exact, and
          the same job counts as the clean K serial run (the rival
          region's own window is priced but never runs: the close
          preempts it)

The patch is 24 cells because the survey needs a component of at least
`MIN_AREA_MM2` (9 mm²) that is at least 32 px on its short side to
measure a pitch at all: 24 cells at 8 px is 192 px and 16.5 mm², clear
of both floors with margin.
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.diag import model as diag_model
from holo.receiver.diag import report as diag_report
from holo.receiver.plugins import intake, survey
from holo.receiver.tests import _h3_facts, _h3_sims, _h3_support
from holo.receiver.tests import test_h3_e2e_sims as sims_pins

DPI = 1200.0
DECLARED_PITCH_IN = Fraction(1, 200)
RIVAL_PITCH_IN = Fraction(1, 150)
DECLARED_PITCH_PX = float(DECLARED_PITCH_IN) * DPI
TIE_SEED = 20260904
TIE_MARGIN_PX = 40
TIE_GAP_PX = 96
TIE_DECLARED_CELLS = 60
TIE_RIVAL_CELLS = 45
TIE_SHAPE_PX = (440, 896)

WARNING_FRAGMENT = "voted no printed pitch (tie or no snap)"


def _lattice(seed: int, pitch_in: Fraction, cells: int) -> np.ndarray:
    # its own generator per patch, so leaving one out of the canvas
    # cannot change the other's bits: the three rasters below differ
    # by which patches are present and by nothing else
    rng = np.random.default_rng(seed)
    cell_px = int(pitch_in * DPI)
    bits = rng.random((cells, cells)) < 0.5
    return np.kron(
        np.where(bits, _h3_sims.K_INK_LEVEL,
                 _h3_sims.K_PAPER_LEVEL).astype(np.uint8),
        np.ones((cell_px, cell_px), np.uint8))


def _tie_raster(declared: bool = True, rival: bool = True) -> np.ndarray:
    left = _lattice(TIE_SEED, DECLARED_PITCH_IN, TIE_DECLARED_CELLS)
    right = _lattice(TIE_SEED + 1, RIVAL_PITCH_IN, TIE_RIVAL_CELLS)
    image = np.full(TIE_SHAPE_PX, _h3_sims.K_PAPER_LEVEL, np.uint8)
    if declared:
        image[TIE_MARGIN_PX:TIE_MARGIN_PX + left.shape[0],
              TIE_MARGIN_PX:TIE_MARGIN_PX + left.shape[1]] = left
    if rival:
        x0 = TIE_MARGIN_PX + left.shape[1] + TIE_GAP_PX
        image[TIE_MARGIN_PX:TIE_MARGIN_PX + right.shape[0],
              x0:x0 + right.shape[1]] = right
    return image


def _voted(image: np.ndarray) -> Fraction | None:
    view = survey.NativeView(dpi=DPI, shape=image.shape, planes=(image,))
    return survey.survey_view(view, DECLARED_PITCH_IN)[1]


def _capture_and_planes(tmp_path: Path, image: np.ndarray
                        ) -> tuple[data.Capture, tuple]:
    plane_dir = tmp_path / "planes"
    plane_dir.mkdir(parents=True, exist_ok=True)
    levels = intake.build_levels(DPI, DECLARED_PITCH_IN, image.shape)
    native_index = levels[-1].index
    path = intake.plane_path(plane_dir, native_index, intake.PLANE_GREY)
    np.save(path, image)
    raster = data.PlaneRaster("tie", native_index, intake.PLANE_GREY, path,
                             image.shape)
    capture = data.Capture(
        capture_id="tie", path=tmp_path / "scan.tiff", dpi=DPI,
        shape_px=image.shape, channels=1, platen_backing=240.0,
        levels=levels, plane_dir=plane_dir)
    return capture, (raster,)


def _fallbacks(events: tuple) -> tuple[data.SurveyPitchFallback, ...]:
    return tuple(event for event in events
                 if isinstance(event, data.SurveyPitchFallback))


def test_the_stimulus_really_ties_two_rival_pitch_votes():
    """Each patch votes on its own; together they tie and vote nothing.

    Without both halves the capture proves nothing: a stimulus whose
    rival patch stopped voting would vote the declared pitch and pass
    the decode test below for the wrong reason.
    """
    assert _voted(_tie_raster(rival=False)) == DECLARED_PITCH_IN
    assert _voted(_tie_raster(declared=False)) == RIVAL_PITCH_IN
    assert _voted(_tie_raster()) is None


def test_a_tie_votes_no_pitch_and_the_survey_works_at_the_declared_one(
        tmp_path: Path, capsys):
    capture, planes = _capture_and_planes(tmp_path, _tie_raster())
    result, events = survey.survey_capture(capture, planes,
                                           DECLARED_PITCH_IN)
    assert result.pitch_class is None
    assert result.pitch_px == DECLARED_PITCH_PX
    assert len(result.regions) == 2
    fallbacks = _fallbacks(events)
    assert len(fallbacks) == 1
    assert fallbacks[0] == data.SurveyPitchFallback(
        capture="tie", declared_pitch_in="1/200",
        pitch_px=DECLARED_PITCH_PX, n_regions=2)
    stderr = capsys.readouterr().err
    assert WARNING_FRAGMENT in stderr, stderr
    assert "proceeding on the declared pitch 1/200 in" in stderr


def test_a_survey_that_does_vote_neither_warns_nor_moves(tmp_path: Path,
                                                         capsys):
    """One patch alone votes a plurality of one — nothing is ported away."""
    capture, planes = _capture_and_planes(tmp_path,
                                          _tie_raster(rival=False))
    result, events = survey.survey_capture(capture, planes,
                                           DECLARED_PITCH_IN)
    assert result.pitch_class == DECLARED_PITCH_IN
    assert result.pitch_px == pytest.approx(DECLARED_PITCH_PX, rel=0.01)
    assert _fallbacks(events) == ()
    assert WARNING_FRAGMENT not in capsys.readouterr().err


def test_a_survey_that_measured_no_pitch_still_gets_frames_and_windows():
    """Including an ARCHIVED one: a resumed state's survey fact may carry
    `pitch_px` None, and the frames it feeds never read that field."""
    instance = _h3_facts.seeded_engine("CaptureSurvey")
    unvoted = dataclasses.replace(_h3_facts.survey(), pitch_class=None,
                                  pitch_px=None)
    instance._fold(unvoted)
    key = (_h3_facts.CAPTURE_ID, 0, 0)
    frame = instance.frame(key)
    assert frame is not None
    assert frame.pitch_native_px == DECLARED_PITCH_PX
    assert instance.windows()
    assert all(wid[0] == _h3_facts.CAPTURE_ID
               for wid in instance.windows())


def test_the_diag_report_carries_the_pitch_fallback():
    capture_id = "1f" * 32
    events = (
        data.RunOpen(format_id="c3-k-r0550@7x7", pages=1, tiles_yx=(7, 7),
                     stream_ids=("main",), n_captures=1, workers=1,
                     family="k"),
        data.CaptureOpen(capture=capture_id, dpi=DPI, shape_yx=TIE_SHAPE_PX,
                         channels=1, duplicate=False, ordinal=0),
        data.SurveyPitchFallback(capture=capture_id,
                                 declared_pitch_in="1/200",
                                 pitch_px=DECLARED_PITCH_PX, n_regions=2),
    )
    model = diag_model.fold(diag_model.empty(), events)
    assert model.fold_errors == 0
    facts = diag_report.build_report(model)["capture_facts"]
    assert facts[0]["pitch_fallback"] == {
        "declared_pitch_in": "1/200", "pitch_px": DECLARED_PITCH_PX,
        "n_regions": 2}
    quiet = diag_model.fold(diag_model.empty(), events[:2])
    assert diag_report.build_report(quiet)[
        "capture_facts"][0]["pitch_fallback"] is None


def test_the_rival_pitch_sim_capture_derives_from_the_frozen_k_render(
        sim_k_rival_pitch, sim_k):
    assert sim_k_rival_pitch.tiff_sha256 != sim_k.tiff_sha256
    assert sim_k_rival_pitch.format_ref == sim_k.format_ref
    assert sim_k_rival_pitch.payload_sha256 == sim_k.payload_sha256
    assert sim_k_rival_pitch.tiff.is_file()


def test_a_capture_that_votes_no_pitch_is_still_read_to_a_verified_close(
        decode_k_rival_pitch_w1, sim_k):
    record = decode_k_rival_pitch_w1
    assert record.exit_code == 0
    assert record.status == "verified"
    assert record.payload == sim_k.payload_data
    _h3_support.assert_golden("rival-pitch payload sha256",
                              record.payload_sha256,
                              _h3_sims.K_PAYLOAD_SHA256)
    assert record.certified == sims_pins.K_SERIAL_CERTIFICATES


def test_the_no_vote_run_warns_once_and_records_the_declared_pitch(
        decode_k_rival_pitch_w1):
    record = decode_k_rival_pitch_w1
    fallbacks = _fallbacks(record.events)
    assert len(fallbacks) == 1
    assert fallbacks[0].declared_pitch_in == "1/200"
    assert fallbacks[0].pitch_px == DECLARED_PITCH_PX
    assert fallbacks[0].n_regions == 2
    assert WARNING_FRAGMENT in record.stderr, record.stderr
    facts = record.report["capture_facts"][0]
    assert facts["pitch_fallback"]["pitch_px"] == DECLARED_PITCH_PX
    assert [region["pitch_px"] for region in facts["regions"]] == [
        DECLARED_PITCH_PX, DECLARED_PITCH_PX]
