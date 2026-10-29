"""The K context fold: the decision, the catch-up and the fold head.

Three invariants of 2026-10-03, on the in-memory engine:

(i)   a ctx outcome that merges after a NEWER fit of one of its windows
      corrects the newer fit, never the rows its job was prepared from
      (the outcome carries no rows at all);
(ii)  under a standing adopted decision, calibrate's stripped re-fit of
      an unchanged window folds as nothing -- no key, no generation;
(iii) the first adoption corrects every accepted row standing in the
      region and wakes exactly their read keys.

And the region pitch key moves with the SAMPLING PAIR, not the float.
"""
from __future__ import annotations

import dataclasses

import numpy as np

from holo.receiver import data
from holo.receiver.descriptor import (
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_REGION_PITCH,
    WorkerBookmark,
)
from holo.receiver.lib.pava import N_CONTEXT_BINS, calibration_llr
from holo.receiver.plugins import calibrate
from holo.receiver.tests import _h3_facts

CAPTURE_ID = _h3_facts.CAPTURE_ID
REGION = (CAPTURE_ID, 0, 0)
WID_A = _h3_facts.WINDOW_ID
WID_B = (CAPTURE_ID, 0, 0, (64, 0, 128, 64))
WID_R = (CAPTURE_ID, 0, 0, (128, 0, 192, 64))
KNOTS = np.asarray((-1.0, 1.0), np.float64)
PROBS = np.asarray((0.1, 0.9), np.float64)


def _probe(engine: object, *keys: tuple) -> WorkerBookmark:
    subject = ("probe", len(engine._bookmarks))
    worker = WorkerBookmark(plugin="probe", subject=subject, reads=keys)
    engine._bookmarks[("probe", subject)] = worker
    engine._register_reads(worker, keys)
    return worker


def _fit(wid: tuple, seed: int, accepted: bool = True) -> data.WindowEvidence:
    """A stripped calibrate row with a real PAVA map and mixed ink."""
    base = _h3_facts.evidence(wid=wid, accepted=accepted)
    rng = np.random.default_rng(seed)
    scores = rng.normal(0.0, 1.0, base.page_cells_yx.shape[0]).astype(
        np.float32)
    marginal = np.asarray(calibration_llr(scores, KNOTS, PROBS), np.float32)
    return dataclasses.replace(
        base, scores=scores, knots=KNOTS, probs=PROBS, marginal_llr=marginal,
        printed_llr=marginal, ctx_adopted=False)


def _decision(loss: float, scale: float = 0.4) -> calibrate.CtxOutcome:
    ctx = data.RegionCtx(
        CAPTURE_ID, 0, 0, np.linspace(-scale, scale, N_CONTEXT_BINS),
        True, "adopted", loss)
    return calibrate.CtxOutcome(REGION, ctx)


def _engine() -> object:
    engine = _h3_facts.new_engine()
    engine._push_worker = lambda _worker: None
    engine._ingest(_h3_facts.capture())
    engine._ingest(_h3_facts.window())
    return engine


def test_the_ctx_outcome_carries_the_decision_and_no_window_rows():
    assert [field.name for field in dataclasses.fields(
        calibrate.CtxOutcome)] == ["region_key", "ctx"]


def test_an_outcome_merged_after_a_newer_fit_corrects_the_newer_fit():
    engine = _engine()
    engine._ingest(_fit(WID_A, seed=1))
    job = calibrate.prepare_ctx(engine, REGION, calibrate.STAGE_CALIBRATE)
    newer = _fit(WID_A, seed=2)
    engine._ingest(newer)
    (prepared,) = job().facts
    outcome = dataclasses.replace(_decision(0.3),
                                  region_key=prepared.region_key)
    engine._ingest(outcome)
    standing = engine.evidence(WID_A)
    expected = calibrate.apply_standing_context(newer, outcome.ctx)
    assert standing.ctx_adopted is True
    assert np.array_equal(standing.scores, newer.scores)
    assert np.array_equal(standing.printed_llr, expected.printed_llr)
    assert standing.heldout_logloss == expected.heldout_logloss


def test_a_stripped_refit_over_unchanged_evidence_folds_as_nothing():
    engine = _engine()
    engine._ingest(_fit(WID_A, seed=1))
    engine._ingest(_decision(0.3))
    fit = _probe(engine, (KEY_EVIDENCE_FIT, WID_A))
    read = _probe(engine, (KEY_EVIDENCE_READ, WID_A))
    generations = dict(engine._tile_lane_generation)
    changed, _kind = engine._ingest(_fit(WID_A, seed=1))
    assert changed is False
    assert (fit.version, read.version) == (0, 0)
    assert engine._tile_lane_generation == generations
    assert engine.evidence(WID_A).ctx_adopted is True


def test_the_first_adoption_corrects_every_accepted_standing_row():
    engine = _engine()
    rows = {wid: _fit(wid, seed=index)
            for index, wid in enumerate((WID_A, WID_B))}
    rows[WID_R] = _fit(WID_R, seed=9, accepted=False)
    for row in rows.values():
        engine._ingest(row)
    reads = {wid: _probe(engine, (KEY_EVIDENCE_READ, wid)) for wid in rows}
    fits = {wid: _probe(engine, (KEY_EVIDENCE_FIT, wid)) for wid in rows}
    outcome = _decision(0.3)
    changed, _kind = engine._ingest(outcome)
    assert changed is True
    for wid in (WID_A, WID_B):
        expected = calibrate.apply_standing_context(rows[wid], outcome.ctx)
        assert engine.evidence(wid).ctx_adopted is True
        assert np.array_equal(engine.evidence(wid).printed_llr,
                              expected.printed_llr)
        assert reads[wid].version == 1
    assert engine.evidence(WID_R) is rows[WID_R]
    assert reads[WID_R].version == 0
    assert all(probe.version == 0 for probe in fits.values()), (
        "the catch-up moves the READ half only: the ctx row subscribes "
        "to the fit half and is not re-woken by its own decision")


def test_a_better_decision_re_corrects_the_standing_rows_under_itself():
    engine = _engine()
    engine._ingest(_fit(WID_A, seed=1))
    engine._ingest(_decision(0.3, scale=0.4))
    better = _decision(0.2, scale=0.8)
    engine._ingest(better)
    expected = calibrate.apply_standing_context(_fit(WID_A, seed=1),
                                                better.ctx)
    assert np.array_equal(engine.evidence(WID_A).printed_llr,
                          expected.printed_llr)


def _pitched(pitch_px: float, quality: float) -> data.Placement:
    return _h3_facts.placement(pitch_px=pitch_px, quality=quality)


def test_the_region_pitch_key_moves_with_the_sampling_pair_alone():
    engine = _engine()
    probe = _probe(engine, (KEY_REGION_PITCH,) + REGION)
    engine._ingest(_pitched(4.0, quality=0.5))
    assert probe.version == 1
    assert calibrate.sampling_pair(4.05) == calibrate.sampling_pair(4.0)
    engine._ingest(_pitched(4.05, quality=0.4))
    assert engine.region_pitch(REGION) == 4.05, "the exact median stands"
    assert probe.version == 1, "a pitch inside one pair re-reads nothing"
    assert calibrate.sampling_pair(4.4) != calibrate.sampling_pair(4.05)
    engine._ingest(_pitched(4.4, quality=0.3))
    assert probe.version == 2


def test_the_sampling_pair_is_the_halo_and_the_aperture_the_reads_use():
    for pitch_px in (2.0, 3.6, 4.0, 7.3, 16.0):
        halo, aperture = calibrate.sampling_pair(pitch_px)
        assert aperture == calibrate._aperture_px(pitch_px)
        points = np.asarray(((100.0, 100.0),))
        y0, x0, _y1, _x1 = calibrate._crop_bounds(points, (400, 400),
                                                  pitch_px)
        assert (y0, x0) == (100 - halo, 100 - halo)
