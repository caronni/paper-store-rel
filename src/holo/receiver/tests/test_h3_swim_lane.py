"""`tiles.swim` subjected per tile-LANE: one build, one verdict per stream.

Since 2026-10-03 the swim's subject is (page, ty, tx, ppc), the shape
`tiles.local` took on 2026-09-21: everything a fire constructs — the
lane plans, the three-plane affine search over every covering window,
the colour head read through it — is stream-independent, and the
stream id reaches the work only at `tiles.attempt_tile`.  These pins
are behavioural and run on the in-memory engine; the construction is
counted through a monkeypatched `swim_components`, never decoded.
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data, engine, sched_trace
from holo.receiver.format import identity
from holo.receiver.lib import geometry
from holo.receiver.plugins import swim, tiles
from holo.receiver.tests import _h3_facts

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
CAPTURE_ID = _h3_facts.CAPTURE_ID
PPC = Fraction(4)
PAGE = 0
SPAN_CELLS = 2 * geometry.TILE_CELLS
WID = (CAPTURE_ID, 0, 0, (0, 0, SPAN_CELLS, SPAN_CELLS))
ROW = identity.resolve_format_ref(COLOR_FORMAT_REF)
STREAMS = tuple(stream.stream_id for stream in ROW.streams)
SUBJECT = (PAGE, 0, 0, PPC)


def _color_engine() -> engine._Engine:
    request = dataclasses.replace(_h3_facts.new_engine()._request,
                                  format_ref=COLOR_FORMAT_REF)
    instance = engine._Engine(request, [])
    instance._ingest(_h3_facts.capture())
    return instance


def _failed(stream_id: str, stage: str = tiles.STAGE_SCAN,
            ty: int = 0, tx: int = 0) -> data.AttemptFact:
    return data.AttemptFact(
        page=PAGE, ty=ty, tx=tx, stream_id=stream_id, stage=stage,
        outcome=tiles.OUTCOME_FAILED, n_informative=1000, n_iters=60,
        syndrome_ok=False, crc_ok=False, components=((CAPTURE_ID, 0),))


def _certificate(stream_index: int) -> data.Certificate:
    stream = ROW.streams[stream_index]
    return data.Certificate(
        page=PAGE, ty=0, tx=0, stream_id=stream.stream_id,
        user_bits=np.zeros(stream.user_bits, np.uint8), source="tiles/scan")


def _covered_engine(armed: tuple[int, ...]) -> engine._Engine:
    """A colour tile-lane under one placed window, `armed` streams failed."""
    store = _color_engine()
    store._ingest(_h3_facts.window(WID, ordinal=0))
    store._ingest(dataclasses.replace(
        _h3_facts.placement(WID),
        local_cells_yx=_h3_facts.tile_cells(SPAN_CELLS)))
    store._ingest(_h3_facts.color_row())
    lane = (CAPTURE_ID, 0)
    if lane not in store._planes_by_lane:
        store._planes_by_lane[lane] = {"r": None, "g": None, "b": None}
    for index in armed:
        store._ingest(_failed(STREAMS[index]))
    return store


class _Spy:
    """Counts constructions and attempts; certifies the streams named."""

    def __init__(self, certify: tuple[str, ...] = ()) -> None:
        self.constructions = 0
        self.attempted: list[str] = []
        self.certify = certify

    def components(self, row, geometry_, plan, certificates, page, ty, tx):
        self.constructions += 1
        # a cut that names its lane: the verdict is stamped with that
        # lane's generation (`local_ctx.Generations.of`, 2026-10-03)
        cut = tiles.TileCut(plan.lane[0], plan.lane[1], page, ty, tx,
                            np.zeros((1, 1), np.float32),
                            np.zeros(1, np.uint16))
        return [cut], []

    def attempt(self, row, geometry_, components, stream_id, stage,
                generation=0) -> tiles.TileAttemptResult:
        self.attempted.append(stream_id)
        outcome = (tiles.OUTCOME_CERTIFIED if stream_id in self.certify
                   else tiles.OUTCOME_FAILED)
        fact = dataclasses.replace(_failed(stream_id, stage),
                                   outcome=outcome)
        certificate = None
        if stream_id in self.certify:
            index = STREAMS.index(stream_id)
            certificate = dataclasses.replace(
                _certificate(index), source=tiles.source_tag(stage))
        return tiles.TileAttemptResult(fact, certificate, object())


def _spied(monkeypatch: pytest.MonkeyPatch,
           certify: tuple[str, ...] = ()) -> _Spy:
    spy = _Spy(certify)
    monkeypatch.setattr(swim, "swim_components", spy.components)
    monkeypatch.setattr(swim.tiles, "attempt_tile", spy.attempt)
    return spy


def test_c_m_and_y_failures_arm_one_tile_lane_subject():
    store = _color_engine()
    subjects = {swim._swim_subjects(store, _failed(stream_id))
                for stream_id in STREAMS}
    assert subjects == {(SUBJECT,)}, (
        "a stream id in the subject is the sibling bug coming back: C, M "
        "and Y of one tile name the same tile-lane")


def test_two_armed_streams_share_one_construction(monkeypatch):
    store = _covered_engine(armed=(0, 2))
    spy = _spied(monkeypatch)
    job = swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM)
    assert job is not None
    result = job()
    assert spy.constructions == 1, (
        "the fit and the head read are stream-independent: one build per "
        "tile-lane, whatever the number of armed streams")
    assert spy.attempted == [STREAMS[0], STREAMS[2]], (
        "one attempt per ARMED stream, in the format row's order; the "
        "unarmed one is not this fire's work")
    verdicts = [fact for fact in result.facts
                if isinstance(fact, data.AttemptFact)]
    assert [fact.stream_id for fact in verdicts] == [STREAMS[0], STREAMS[2]]
    assert all(fact.stage == tiles.STAGE_SWIM150 for fact in verdicts)
    assert not any(isinstance(fact, data.Certificate)
                   for fact in result.facts)
    assert len(result.events) == 2


def test_a_certificate_ends_its_own_stream_and_no_other(monkeypatch):
    store = _covered_engine(armed=(0, 1, 2))
    spy = _spied(monkeypatch, certify=(STREAMS[0],))
    job = swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM)
    assert job is not None
    result = job()
    assert spy.constructions == 1
    assert spy.attempted == list(STREAMS)
    certified = [fact.stream_id for fact in result.facts
                 if isinstance(fact, data.Certificate)]
    assert certified == [STREAMS[0]]


def test_a_stream_certified_before_prepare_is_not_attempted(monkeypatch):
    store = _covered_engine(armed=(0, 1))
    store._ingest(_certificate(0))
    spy = _spied(monkeypatch)
    job = swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM)
    assert job is not None
    job()
    assert spy.attempted == [STREAMS[1]], (
        "the armed set is read at prepare, on the engine thread: a stream "
        "the store already holds a certificate for is not re-attempted")


def test_nothing_armed_and_uncertified_prepares_nothing(monkeypatch):
    store = _covered_engine(armed=(0,))
    store._ingest(_certificate(0))
    spy = _spied(monkeypatch)
    assert swim._swim_eligible(store, SUBJECT) is False
    assert swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM) is None
    assert spy.constructions == 0


def test_retirement_waits_for_every_stream_of_the_tile():
    store = _covered_engine(armed=(0, 1, 2))
    for index in range(len(STREAMS)):
        assert swim._swim_retire(store, SUBJECT) is None, (
            f"{index} of {len(STREAMS)} streams certified: still live work")
        store._ingest(_certificate(index))
    assert swim._swim_retire(store, SUBJECT) == "certified"


def test_the_reads_hold_every_stream_s_arming_verdict():
    store = _covered_engine(armed=(0,))
    keys = swim._swim_reads(store, SUBJECT)
    attempt_streams = {key[4] for key in keys if key[0] == "attempt"}
    assert attempt_streams == set(STREAMS), (
        "an unarmed sibling's later failure is a stream this subject now "
        "owes a read: its verdict key must wake the row")


def test_a_k_page_has_no_swim_subject():
    store = _h3_facts.new_engine()
    store._ingest(_h3_facts.capture())
    fact = _failed(store.row.streams[0].stream_id)
    assert swim._swim_subjects(store, fact) == ()
    assert swim._swim_eligible(store, SUBJECT) is False
    assert swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM) is None


def test_the_trace_digests_a_swim_fire_and_off_records_nothing(
        monkeypatch, tmp_path: Path):
    store = _covered_engine(armed=(0, 1))
    _spied(monkeypatch)
    trace = sched_trace.arm(tmp_path, workers=1, every_s=3600.0)
    try:
        trace.clear_input()
        assert swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM) is not None
        kind, digest, bare, _reason = trace.take_input()
        assert kind == "swim_inputs" and digest and bare
        trace.clear_input()
        swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM)
        again = trace.take_input()
        assert again[1] == digest and again[2] == bare, (
            "the same evidence digests the same: a repeat fire is visible")
        store._ingest(_certificate(0))
        trace.clear_input()
        swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM)
        shrunk = trace.take_input()
        assert shrunk[1] != digest, "the armed set is part of the input"
        assert shrunk[2] != bare, (
            "a new certificate on the tile is a new label set")
    finally:
        sched_trace.disarm()
    assert sched_trace.TRACE.enabled is False
    assert swim.prepare_swim(store, SUBJECT, swim.STAGE_SWIM) is not None
