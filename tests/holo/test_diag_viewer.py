"""Viewer-level gates for the live diag view.

The full-decode byte/state parity of ``--diag`` is pinned by the production
roundtrip battery (``fine_diagnostic_parity``).  These tests pin the viewer
itself: the e023c transport contract (per-page frame revisions, one current
composed frame per page, small status.json), the six-row stats block, the
pane presentation rules that are easy to regress silently (one pane-wide
count font, no background stripes, a box on every detected region),
per-event snapshot scoping, and failure isolation (a broken view never
breaks the scalar log).
"""
from __future__ import annotations

import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from holo.format.registry import FORMAT_ROWS
from holo.receive.diag import ReceiveDiagnostics
from holo.receive.observer import ReceiverQualificationStatus
from holo.receive.survey import SupportMask, SurveyRegion, region_from_record
from holo.receive.types import (
    AddressArtifact, AddressProduct, BchConflictRecord, Detail, EventContext,
    ParkedWindowRecord, PoseRecord, RefineAddressPlan, RuntimeEvent, Stage,
    SupportRun, SurveyRegionRecord)


_SPEC = FORMAT_ROWS["c3-r0550@2240x1536"]


class _Feed:
    """Sequence-correct synthetic event feed for one diagnostics instance."""

    def __init__(self, observer: ReceiveDiagnostics) -> None:
        self.observer = observer
        self.sequence = 0
        self.context = EventContext(
            qualification_status="provisional",
            format_id=_SPEC.spec_id,
            receiver_policy_id="qualification/viewer-test/v1",
            page_domain=(0,),
            lane_id="l00",
            effective_dpi=1200.0,
        )

    def emit(self, name: str, stage: Stage, details: tuple[Detail, ...] = (),
             snapshot: object = None, capture: str | None = None) -> None:
        event = RuntimeEvent(
            self.sequence, name, stage, capture, "", details,
            context=self.context, snapshot=snapshot)
        self.sequence += 1
        self.observer(event)


def _diagnostics(tmp_path: Path, **overrides) -> ReceiveDiagnostics:
    arguments = dict(
        receiver_policy_id="qualification/viewer-test/v1",
        page_domain=(0,),
        qualification_status=ReceiverQualificationStatus.PROVISIONAL,
        qualification_notes=("viewer test",),
        interval_s=0.0,
        panel_width=200,
        port=None,
    )
    arguments.update(overrides)
    return ReceiveDiagnostics(tmp_path / "diag", _SPEC, **arguments)


def _survey_snapshot(
    origin: tuple[int, int] = (40, 60),
    grid: tuple[int, int] = (6, 5),
    extent: tuple[int, int] = (90, 76),
) -> dict[str, object]:
    cells = np.zeros(grid, bool)
    cells[1:-1, 1:-1] = True
    support = SupportMask(origin, 16, cells, extent)
    region = SurveyRegion(support, 25.0, 40.0)
    return {
        "kind": "survey",
        "survey": SimpleNamespace(regions=(region,)),
        "regions": (),
    }


def _multi_survey_snapshot(specs) -> dict[str, object]:
    """Survey snapshot with N regions (one (origin, grid, extent) each)."""
    regions = []
    for origin, grid, extent in specs:
        cells = np.zeros(grid, bool)
        cells[1:-1, 1:-1] = True
        regions.append(SurveyRegion(
            SupportMask(origin, 16, cells, extent), 25.0, 40.0))
    return {"kind": "survey",
            "survey": SimpleNamespace(regions=tuple(regions)),
            "regions": ()}


def test_region_states_ignore_foreign_lane_indices(tmp_path) -> None:
    """Region ordinals are LANE-RELATIVE: rungs segment independently, so
    an M/R level's `address.region` N addresses its BASE lane's Nth region,
    not the Nth region of whichever rung is currently on screen.  Applying
    them lit the wrong scrap (or dropped silently when out of range) —
    and the counts in the scraps row inherited the same mix."""
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    sequence = [0]
    coarse = EventContext(lane_id="l00", level_ordinal=0)

    def emit(name, details=(), snapshot=None, context=None,
             stage: Stage = Stage.ADDRESS) -> None:
        view.feed(RuntimeEvent(sequence[0], name, stage, "b" * 64, "",
                               tuple(details), context=context or coarse,
                               snapshot=snapshot))
        sequence[0] += 1

    def states():
        return [row.state for row in view._scan.regions]

    emit("capture.open", stage=Stage.INGEST)
    # Coarse rung finds ONE scrap; the finer rung splits it into THREE.
    emit("survey.complete", (Detail("survey.regions", 1),),
         snapshot=_survey_snapshot(), context=coarse, stage=Stage.SURVEY)
    fine = EventContext(lane_id="l01", level_ordinal=1)
    emit("survey.complete", (Detail("survey.regions", 3),),
         snapshot=_multi_survey_snapshot((
             ((40, 60), (6, 5), (90, 76)),
             ((140, 60), (6, 5), (90, 76)),
             ((240, 60), (6, 5), (90, 76)))),
         context=fine, stage=Stage.SURVEY)
    assert view._scan.lane == "l01"
    assert len(states()) == 3

    # POSITIVE CONTROL: the owning lane's own indices still paint.
    emit("address.region_open", (Detail("address.region", 2),), context=fine)
    assert states() == ["surveyed", "surveyed", "active"]
    emit("address.region_complete",
         (Detail("address.region", 2), Detail("address.state", "accepted")),
         context=fine)
    assert states() == ["surveyed", "surveyed", "accepted"]

    # PRODUCTION-SHAPED M-level survey over l00 (details only, no snapshot):
    # its region 0 is l00's single scrap, NOT l01's first third.
    mopup = EventContext(lane_id="m00", level_ordinal=2)
    emit("survey.complete", (Detail("survey.regions", 0),
                             Detail("survey.mopup_of", "l00")),
         snapshot=None, context=mopup, stage=Stage.SURVEY)
    assert view._scan.mopup_base == "l00"
    assert view._scan.lane == "l01"        # empty survey relabels nothing
    emit("address.region_open", (Detail("address.region", 0),), context=mopup)
    assert states() == ["surveyed", "surveyed", "accepted"], (
        "an M-level index must not repaint the on-screen rung's region")
    emit("address.region_complete",
         (Detail("address.region", 0),
          Detail("address.state", "pose_refused")), context=mopup)
    assert states() == ["surveyed", "surveyed", "accepted"]

    # R-levels name their base the same way and are guarded identically.
    refine = EventContext(lane_id="r00", level_ordinal=3)
    emit("survey.complete", (Detail("survey.regions", 0),
                             Detail("survey.refine_of", "l00")),
         snapshot=None, context=refine, stage=Stage.SURVEY)
    assert view._scan.mopup_base is None and view._scan.refine_base == "l00"
    emit("address.region_open", (Detail("address.region", 1),),
         context=refine)
    assert states() == ["surveyed", "surveyed", "accepted"]

    # An ordinary rung re-surveying takes ownership back.
    emit("survey.complete", (Detail("survey.regions", 3),),
         snapshot=_multi_survey_snapshot((
             ((40, 60), (6, 5), (90, 76)),
             ((140, 60), (6, 5), (90, 76)),
             ((240, 60), (6, 5), (90, 76)))),
         context=fine, stage=Stage.SURVEY)
    assert view._scan.refine_base is None
    emit("address.region_open", (Detail("address.region", 1),), context=fine)
    assert states() == ["surveyed", "active", "surveyed"]


def test_scan_frame_is_the_one_resume_contract(tmp_path) -> None:
    """ScanFrame replaced twelve field names spelled out in five places
    (init, capture.open reset, _SCAN_FIELDS, _restore_scan, seed.py) that
    nothing pinned to agree.  It is now ONE enumeration — keep it so."""
    import dataclasses
    from holo.receive.diag.scan_model import ScanFrame, ScanModel
    from holo.receive.diag.presentation import PaneRenderer

    names = {f.name for f in dataclasses.fields(ScanFrame)}
    assert names == {
        "regions", "transform", "lane", "active_window", "underlay",
        "lane_regions", "survey_seen", "queue_total", "deferred",
        "planned", "mopup_base", "refine_base", "uplift_arm"}

    # blank() must not alias its mutable defaults across captures.
    one, two = ScanFrame.blank(), ScanFrame.blank()
    assert one.planned is not two.planned
    assert one.regions is not two.regions

    # capture_frame/apply round-trip every field, so a stash cannot drop one.
    model = ScanModel(PaneRenderer((64, 64), (1, 1), 120))
    model.lane, model.deferred, model.mopup_base = "l07", 5, "l00"
    model.planned[(0, 1)] = [(1, 2, 3, 4), "pending"]
    frame = model.capture_frame()
    model.apply(ScanFrame.blank())
    assert model.lane is None and model.deferred == 0 and not model.planned
    model.apply(frame)
    assert (model.lane, model.deferred, model.mopup_base) == ("l07", 5, "l00")
    assert model.planned[(0, 1)] == [(1, 2, 3, 4), "pending"]


def _patch(page: int = 0) -> SimpleNamespace:
    cells = np.stack(np.meshgrid(
        np.arange(64, 128), np.arange(64, 192), indexing="ij"),
        axis=-1).reshape(-1, 2)
    observation = SimpleNamespace(page=page, tile_yx=(1, 1), site_index=7)
    return SimpleNamespace(
        patch_id=1, region_index=0, redundant=False,
        candidate=SimpleNamespace(page=page, origin_yx=(64, 64), rot_k=0),
        page_cells_yx=cells,
        observations=(observation,) * 1 + tuple(
            SimpleNamespace(page=page, tile_yx=(1, 1), site_index=index)
            for index in range(20)),
    )


def _address_snapshot(page: int = 0) -> dict[str, object]:
    word = SimpleNamespace(
        page=page, tile_yx=(1, 1), expected_counter=25, decoded_counter=25,
        errors=0, erasures=10, certified=True, conflict=False)
    result = SimpleNamespace(
        placements=(_patch(page),), unresolved=(), words=(word,))
    return {"kind": "address", "product": SimpleNamespace(transient=result)}


def _committed_snapshot() -> dict[str, object]:
    certificate = SimpleNamespace(page=0, tile_yx=(2, 3), stream_id="main")
    counters = SimpleNamespace(
        scan=SimpleNamespace(evaluations=5, decoder_calls=4,
                             bp_iterations=100, crc_ok=2),
        union=SimpleNamespace(evaluations=1, decoder_calls=1,
                              bp_iterations=10, crc_ok=1),
        retry150=SimpleNamespace(evaluations=1, decoder_calls=1,
                                 bp_iterations=150, crc_ok=1),
        divergences=1,
    )
    state = SimpleNamespace(
        certificates=(certificate,), counters=counters, close=None)
    return {"kind": "barrier", "state": state, "delta": None,
            "base_digest": None, "source_sha256": "a" * 64,
            "close": None, "spec": _SPEC}


def _run_session(feed: _Feed) -> None:
    feed.emit("session.open", Stage.INGEST,
              (Detail("captures.requested", 1),
               Detail("captures.retained", 0)))
    feed.emit("capture.open", Stage.INGEST, capture="b" * 64)
    feed.emit("survey.complete", Stage.SURVEY,
              (Detail("survey.regions", 1),),
              snapshot=_survey_snapshot(), capture="b" * 64)
    feed.emit("address.region_open", Stage.ADDRESS,
              (Detail("address.region", 0),), capture="b" * 64)
    feed.emit("address.final", Stage.ADDRESS,
              (Detail("address.placements", 1),
               Detail("address.unresolved", 0),
               Detail("address.words", 1),
               Detail("address.words_certified", 1),
               Detail("address.words_conflicting", 0),
               Detail("address.placements_quarantined", 0)),
              snapshot=_address_snapshot(), capture="b" * 64)
    feed.emit("payload.attempt", Stage.PAYLOAD,
              (Detail("payload.page", 0), Detail("payload.tile_y", 1),
               Detail("payload.tile_x", 1),
               Detail("payload.attempt_state", "certified"),
               Detail("payload.attempt_stage", "scan"),
               Detail("payload.decoder_invoked", True),
               Detail("payload.certificate_is_new", True)),
              capture="b" * 64)
    feed.emit("barrier.committed", Stage.SCHEDULE,
              (Detail("lane.id", "l00"),),
              snapshot=_committed_snapshot(), capture="b" * 64)


def test_viewer_transport_and_six_row_block(tmp_path) -> None:
    diagnostics = _diagnostics(tmp_path)
    feed = _Feed(diagnostics)
    _run_session(feed)

    directory = tmp_path / "diag"
    status = json.loads((directory / "status.json").read_text())
    assert status["schema"] == "holo-diag-viewer-1"
    assert status["frame"] >= 4  # milestones rendered, revision advanced
    assert status["pages"] == [0]
    assert status["page_default"] == 0
    assert len(status["rows"]) == 6
    labels = [row.split()[0] for row in status["rows"]]
    # v0.27 row order: scraps are lane-scoped, so lane context precedes.
    assert labels == ["format", "lane", "scraps", "address", "LDPC",
                      "fountain"]
    assert _SPEC.spec_id in status["rows"][0]
    assert "1200 dpi" in status["rows"][1]
    assert "1 located" in status["rows"][2]
    assert "1 placed" in status["rows"][2]
    # §10.3.2 exact mapped footprint: REGISTERED PAYLOAD cells only. The
    # fixture patch spans 2 whole tiles, so 2 * (4096 - 100 furniture).
    tiles_y, tiles_x = _SPEC.layout.tiles_yx
    assert f"mapped footprint 0.2% (7992/{tiles_y * tiles_x * 3996} cells)" \
        in status["rows"][2]
    assert "1 match" in status["rows"][3]
    assert "0 conflict" in status["rows"][3]
    assert "deferred 0" in status["rows"][3]
    # Authoritative barrier counters replaced the transient tallies.
    assert "calls 6" in status["rows"][4]
    assert "+1 BP150" in status["rows"][4]
    assert "divergences 1" in status["rows"][4]
    assert "failed" in status["rows"][4] and "low" in status["rows"][4]

    # v0.32: ONE composed frame per page, not four per-pane files.
    data = (directory / "frame_p000.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert not list(directory.glob("pane_*.png"))
    with Image.open(io.BytesIO(data)) as frame:
        assert frame.width == 4 * 200          # four equal panes in one row
        assert frame.height > round(200 * 1536 / 2240)   # + title bar

    previous = status["frame"]
    feed.emit("close.check", Stage.CLOSE,
              (Detail("close.status", "open"),),
              snapshot={"kind": "close", "state": None,
                        "record": SimpleNamespace(
                            status=SimpleNamespace(value="open")),
                        "progress": None, "spec": _SPEC,
                        "deferred_counts": False})
    status = json.loads((directory / "status.json").read_text())
    assert status["frame"] > previous
    assert diagnostics.failures == ()
    diagnostics.close()


def test_snapshot_opt_in_is_scoped_per_event(tmp_path) -> None:
    diagnostics = _diagnostics(tmp_path)
    context = EventContext()

    def event(name: str) -> RuntimeEvent:
        return RuntimeEvent(0, name, Stage.PAYLOAD, context=context)

    assert diagnostics.wants_snapshots is True
    assert diagnostics.wants_snapshot(event("survey.complete"))
    assert diagnostics.wants_snapshot(event("barrier.committed"))
    assert not diagnostics.wants_snapshot(event("payload.attempt"))
    assert not diagnostics.wants_snapshot(event("pose_refine.window_progress"))
    diagnostics.close()


def test_view_failure_isolates_and_scalar_log_survives(tmp_path) -> None:
    diagnostics = _diagnostics(tmp_path)
    feed = _Feed(diagnostics)
    feed.emit("session.open", Stage.INGEST)
    # A malformed pass-through snapshot must break only the view.
    feed.emit("address.final", Stage.ADDRESS,
              snapshot={"kind": "address",
                        "product": SimpleNamespace(
                            transient=SimpleNamespace(
                                placements=(SimpleNamespace(),), words=()))})
    assert len(diagnostics.failures) == 1
    assert "address.final" in diagnostics.failures[0]
    feed.emit("session.complete", Stage.CLOSE)

    directory = tmp_path / "diag"
    names = [json.loads(line)["name"] for line in
             (directory / "events.jsonl").read_text().splitlines()]
    assert names == ["session.open", "address.final", "session.complete"]
    # The dead view stops requesting snapshots.
    assert not diagnostics.wants_snapshot(
        RuntimeEvent(3, "survey.complete", Stage.SURVEY,
                     context=EventContext()))

    written = diagnostics.finalize(SimpleNamespace(status=None))
    names = {path.name for path in written}
    assert {"report.json", "diagnostic-health.json"} <= names
    health = json.loads((directory / "diagnostic-health.json").read_text())
    assert health["capabilities"]["view"] is False
    assert health["failures"]
    diagnostics.close()


def test_refine_level_address_final_keeps_viewer_alive(tmp_path) -> None:
    """The ``--refine`` blackout regression (typed R-level dispatch).

    An R-level's stage-A ``address.final`` snapshot product carries a
    :class:`RefineAddressPlan` transient — base-lane references
    (refinement INPUT), never placements/words.  The viewer must ingest
    nothing from it and stay alive: before the typed dispatch this
    raised ``AttributeError: 'RefineAddressPlan' object has no attribute
    'placements'`` at the first R level, and the observer boundary
    dropped the view for the rest of the session (every later R lane and
    the close rendered nothing).  The adopted poses arrive on the same
    lane's refined re-emission (``address.refined``), whose snapshot
    carries an ordinary address result and ingests normally.
    """
    diagnostics = _diagnostics(tmp_path)
    feed = _Feed(diagnostics)
    _run_session(feed)
    directory = tmp_path / "diag"
    before = json.loads((directory / "status.json").read_text())
    assert "placements 1 accepted" in before["rows"][3]

    # The R level runs as its own lane over the same capture; its address
    # product is the real empty durable mint around the typed plan.
    feed.context = EventContext(
        qualification_status="provisional",
        format_id=_SPEC.spec_id,
        receiver_policy_id="qualification/viewer-test/v1",
        page_domain=(0,),
        lane_id="r00",
        effective_dpi=1200.0,
    )
    prefix = "b" * 64 + "/r00"
    product = AddressProduct(
        AddressArtifact(f"{prefix}/address", f"{prefix}/survey", ()),
        (),
        transient=RefineAddressPlan(
            base_lane_id="l00", poses=(), regions=(), certificates=()))
    feed.emit("survey.complete", Stage.SURVEY,
              (Detail("survey.regions", 0),
               Detail("survey.refine_of", "l00")), capture="b" * 64)
    feed.emit("address.final", Stage.ADDRESS,
              (Detail("address.placements", 0),
               Detail("address.unresolved", 0),
               Detail("address.words", 0),
               Detail("address.words_certified", 0),
               Detail("address.words_conflicting", 0),
               Detail("address.placements_quarantined", 0)),
              snapshot={"kind": "address", "product": product},
              capture="b" * 64)
    assert diagnostics.failures == ()
    status = json.loads((directory / "status.json").read_text())
    # Empty by design: nothing ingested, the base lane's facts stand,
    # and the view kept rendering.
    assert "placements 1 accepted" in status["rows"][3]
    assert status["frame"] > before["frame"]

    # The refined re-emission rides an ordinary address result under the
    # R lane's own key: the base patch repaints there, the address row
    # counts the R lane's re-mint, and the §10.3.2 mapped footprint
    # still counts every cell exactly once.
    feed.emit("address.final", Stage.ADDRESS,
              (Detail("address.refined", True),
               Detail("address.placements", 1)),
              snapshot=_address_snapshot(), capture="b" * 64)
    assert diagnostics.failures == ()
    after = json.loads((directory / "status.json").read_text())
    assert "placements 2 accepted" in after["rows"][3]
    assert after["rows"][2] == status["rows"][2]
    assert after["frame"] > status["frame"]

    # Later events still render (the pre-fix blackout swallowed these).
    feed.emit("session.complete", Stage.CLOSE)
    final = json.loads((directory / "status.json").read_text())
    assert final["frame"] > after["frame"]
    assert "session complete" in final["rows"][1]
    diagnostics.close()


def test_finalize_writes_all_touched_pages_and_marks_done(tmp_path) -> None:
    diagnostics = _diagnostics(tmp_path)
    feed = _Feed(diagnostics)
    _run_session(feed)
    feed.emit("payload.attempt", Stage.PAYLOAD,
              (Detail("payload.page", 2), Detail("payload.tile_y", 0),
               Detail("payload.tile_x", 0),
               Detail("payload.attempt_state", "attempted_failed"),
               Detail("payload.attempt_stage", "scan"),
               Detail("payload.decoder_invoked", True),
               Detail("payload.certificate_is_new", False)),
              capture="b" * 64)

    written = diagnostics.finalize(SimpleNamespace(
        status=SimpleNamespace(value="open")))
    names = {path.name for path in written}
    assert {"report.json", "diagnostic-health.json", "status.json",
            "frame_p000.png", "frame_p002.png"} <= names
    assert not {name for name in names if name.startswith("pane_")}

    directory = tmp_path / "diag"
    status = json.loads((directory / "status.json").read_text())
    assert status["done"] is True
    assert status["pages"] == [0, 2]
    health = json.loads((directory / "diagnostic-health.json").read_text())
    assert health["capabilities"]["view"] is True
    assert health["capabilities"]["server"] is False
    assert diagnostics.failures == ()
    diagnostics.close()


def test_status_updates_between_pane_frames(tmp_path) -> None:
    """§10.6: scalar rows are unthrottled; pane frames keep the throttle."""
    from holo.receive.diag.viewer import LiveView

    clock = [0.0]
    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=1000.0, port=None,
                    clock=lambda: clock[0])
    context = EventContext(lane_id="l00")

    def emit(sequence: int, name: str, details=(),
             stage: Stage = Stage.PAYLOAD) -> None:
        view.feed(RuntimeEvent(sequence, name, stage, "b" * 64, "",
                               tuple(details), context=context))

    emit(0, "session.open", (), Stage.INGEST)   # milestone: pane frame 1
    directory = tmp_path / "view"
    first = json.loads((directory / "status.json").read_text())
    clock[0] = 10.0                             # inside the 1000 s throttle
    emit(1, "payload.attempt",
         (Detail("payload.page", 0), Detail("payload.tile_y", 0),
          Detail("payload.tile_x", 0),
          Detail("payload.attempt_state", "attempted_failed"),
          Detail("payload.attempt_stage", "scan"),
          Detail("payload.decoder_invoked", True),
          Detail("payload.certificate_is_new", False)))
    second = json.loads((directory / "status.json").read_text())
    assert second["frame"] == first["frame"]    # no pane frame minted
    assert second["rows"] != first["rows"]      # but the text moved
    assert "calls 1" in second["rows"][4]
    assert "1 failed" in second["rows"][4]


def test_lazy_render_keeps_per_page_revisions_paired(tmp_path) -> None:
    """W21: only reached pages re-render, and each keeps its own revision."""
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=0.0, port=None,
                    clock=lambda: 0.0)
    context = EventContext(lane_id="l00")
    sequence = [0]

    def attempt(page: int, ty: int, tx: int) -> None:
        view.feed(RuntimeEvent(
            sequence[0], "payload.attempt", Stage.PAYLOAD, "b" * 64, "",
            (Detail("payload.page", page), Detail("payload.tile_y", ty),
             Detail("payload.tile_x", tx),
             Detail("payload.attempt_state", "certified"),
             Detail("payload.attempt_stage", "scan"),
             Detail("payload.decoder_invoked", True),
             Detail("payload.certificate_is_new", True)),
            context=context))
        sequence[0] += 1

    attempt(0, 1, 1)
    attempt(5, 2, 2)
    # Both reached pages hold rasters; only a watched page costs an encode.
    assert {key[1] for key in view._raster if key[1] >= 0} == {0, 5}
    assert set(view._png) == {0} and set(view._page_frame) == {0}

    # v0.32: selecting page 5 composes it, and it then keeps its own
    # (page, revision) pair while page 0 moves on.
    view._wanted_page = 5
    attempt(5, 3, 3)
    both = dict(view._page_frame)
    assert set(both) == {0, 5}
    page5_bytes = view._png[5]
    page5_raster = view._raster[("D", 5)]
    scan_raster = view._raster[("A", -1)]

    view._wanted_page = 0
    attempt(0, 4, 4)            # only page 0 is reached and watched now
    assert view._page_frame[0] > both[0]
    assert view._page_frame[5] == both[5]          # revision held
    assert view._png[5] is page5_bytes             # composed bytes held
    # The composed frame reuses cached pane rasters, so an unwatched page
    # re-encodes nothing and pane A is not redrawn off a payload event.
    assert view._raster[("D", 5)] is page5_raster
    assert view._raster[("A", -1)] is scan_raster
    status = json.loads((tmp_path / "view" / "status.json").read_text())
    assert status["page_frames"]["5"] == both[5]
    assert status["page_frames"]["0"] == view._frame


def test_client_requests_unmaterialized_wanted_page() -> None:
    """v0.32 wanted-page contract, browser side (2026-08-02 deadlock fix).

    The composer materializes a non-default page only after the browser
    requests it, but the browser historically fetched only pages already
    carrying a revision in ``page_frames`` — so flipping to a
    never-composed page did nothing, forever.  Pin the teaching fetch:
    the undefined-revision branch must still request ``frame.png`` for
    the picked page (the 404 is the teaching signal).
    """
    from holo.receive.diag.presentation import _PAGE

    assert "now===undefined" in _PAGE
    teaching = _PAGE.split("now===undefined", 1)[1]
    assert "fetch('frame.png?page='+page" in teaching.split("else", 1)[0]


@pytest.mark.skipif(
    not os.environ.get("HOLO_RUN_LOOPBACK_TESTS"),
    reason="set HOLO_RUN_LOOPBACK_TESTS=1 for the loopback server smoke")
def test_unmaterialized_page_is_unavailable_not_another_page(tmp_path) -> None:
    """§10.5: never serve a different page's image under a 200."""
    served: list[str] = []
    diagnostics = _diagnostics(tmp_path, port=0, on_server=served.append)
    feed = _Feed(diagnostics)
    _run_session(feed)
    base = served[0]
    with urllib.request.urlopen(
            base + "frame.png?page=0&frame=1", timeout=5) as response:
        assert response.read()[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(urllib.error.HTTPError) as missing:
        urllib.request.urlopen(base + "frame.png?page=7&frame=1", timeout=5)
    assert missing.value.code == 404
    diagnostics.close()


def test_glyph_blit_matches_draw_text() -> None:
    """The pane-C glyph cache must be bit-exact against draw.text."""
    from PIL import Image, ImageDraw

    from holo.receive.diag.presentation import _blit_text, _font

    for text in ("1", "42", "100"):
        reference = Image.new("RGB", (48, 20), (250, 250, 250))
        ImageDraw.Draw(reference).text(
            (3, 2), text, fill=(34, 34, 34), font=_font(10))
        cached = Image.new("RGB", (48, 20), (250, 250, 250))
        _blit_text(ImageDraw.Draw(cached), (3, 2), text, (34, 34, 34), 10)
        assert np.array_equal(np.asarray(reference), np.asarray(cached)), text


def test_work_in_flight_overlays_track_events(tmp_path) -> None:
    """v0.27: pane-A planned windows and pane-D retry frontier lifecycles."""
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    context = EventContext(lane_id="l00")
    sequence = [0]

    def emit(name: str, details=(), snapshot: object = None,
             stage: Stage = Stage.ADDRESS) -> None:
        view.feed(RuntimeEvent(sequence[0], name, stage, "b" * 64, "",
                               tuple(details), context=context,
                               snapshot=snapshot))
        sequence[0] += 1

    emit("address.window_planned",
         (Detail("address.region", 0), Detail("address.window", 3),
          Detail("address.box_y", 100), Detail("address.box_x", 100),
          Detail("address.box_h", 400), Detail("address.box_w", 400)))
    assert view._scan.planned[(0, 3)][1] == "pending"
    emit("address.cold_deferred",
         (Detail("address.region", 0), Detail("address.patch", 0),
          Detail("address.window", 3), Detail("address.deferred", 1)))
    assert view._scan.planned[(0, 3)][1] == "parked"
    assert view._scan.deferred == 1
    # v0.29 rest-decode is its own state, and a refused rest returns the
    # window to parked rather than leaving it falsely "working".
    emit("address.word_rest_open",
         (Detail("address.region", 0), Detail("address.patch", 0),
          Detail("address.window", 3)))
    assert view._scan.planned[(0, 3)][1] == "rest"
    emit("address.word_rest_refused",
         (Detail("address.region", 0), Detail("address.patch", 0),
          Detail("address.window", 3)))
    assert view._scan.planned[(0, 3)][1] == "parked"
    emit("address.cold_open",
         (Detail("address.region", 0), Detail("address.patch", 0),
          Detail("address.window", 3), Detail("address.pages", 312)))
    assert view._scan.planned[(0, 3)][1] == "active"
    assert "cold search" in view._phase
    emit("address.window_resolved",
         (Detail("address.region", 0), Detail("address.window", 3),
          Detail("address.outcome", "accepted")))
    assert (0, 3) not in view._scan.planned

    emit("payload.retry_open", (Detail("payload.retry_tiles", 2),),
         snapshot={"kind": "retry_frontier",
                   "tiles": ((0, 1, 1, "main"), (0, 2, 2, "main"))},
         stage=Stage.PAYLOAD)
    assert view._retry_pending == {(0, 1, 1, "main"), (0, 2, 2, "main")}
    emit("payload.attempt",
         (Detail("payload.page", 0), Detail("payload.tile_y", 1),
          Detail("payload.tile_x", 1),
          Detail("payload.attempt_state", "attempted_failed"),
          Detail("payload.attempt_stage", "retry150"),
          Detail("payload.decoder_invoked", True),
          Detail("payload.certificate_is_new", False)),
         stage=Stage.PAYLOAD)
    assert view._retry_pending == {(0, 2, 2, "main")}
    emit("payload.retry_complete", (), stage=Stage.PAYLOAD)
    assert view._retry_pending == set()


def test_payload_reach_snapshot_builder() -> None:
    """W18: owner-frozen cells reduce to exact per-page touched tiles."""
    from holo.receive import _diagnostic_snapshots as snapshots

    frontier = SimpleNamespace(pages=(
        SimpleNamespace(page=0, cells_yx=np.asarray(
            [[0, 0], [63, 63], [64, 0], [70, 200]], np.int64)),
    ))
    snapshot = snapshots.payload(frontier, _SPEC)
    assert snapshot["kind"] == "payload_reach"
    tiles_x = int(_SPEC.layout.tiles_yx[1])
    assert set(snapshot["pages"][0].tolist()) == {0, tiles_x, tiles_x + 3}


_CSS_COMMENT = re.compile(rb"/\*.*?\*/", re.S)


def _assert_no_aspect_ratio_declaration(shell: bytes) -> None:
    """The shell declares NO frame geometry (041d9a8).

    The composed PNG carries its own proportions; a CSS ``aspect-ratio``
    restated them from a separate guess and stretched the image
    (``object-fit: fill``) the moment the two disagreed, which the W5
    bottom band made routine.  The v0.32 assertion ``b"aspect-ratio:" in
    shell`` outlived the declaration it was written for and went on
    passing against the CSS COMMENT that explains the removal — so strip
    comments before looking.
    """
    naked = _CSS_COMMENT.sub(b"", shell)
    assert b"aspect-ratio" not in naked, (
        "the shell re-declared a frame aspect ratio")


def test_shell_declares_no_geometry_and_legends_every_pane(tmp_path) -> None:
    """The fast counterpart of the loopback smoke: the same two shell
    facts, without a server (the loopback test is opt-in, so it guarded
    nothing on an ordinary run)."""
    shell = _tile_view(tmp_path)._shell()
    assert b"width:100%" in shell
    _assert_no_aspect_ratio_declaration(shell)
    # One legend column per pane A-D, plus the W5 bottom band (P1).
    assert shell.count(b"<div><b>") == 5
    assert b"repeat(5,1fr)" in shell
    for phrase in (b"scan regions", b"page-space placements", b"BCH word",
                   b"payload tiles", b"plane fields"):
        assert phrase in shell
    # The band's four block colours are named, black and green apart.
    assert b"BLACK" in shell and b"DARK GREEN" in shell


@pytest.mark.skipif(
    not os.environ.get("HOLO_RUN_LOOPBACK_TESTS"),
    reason="set HOLO_RUN_LOOPBACK_TESTS=1 for the loopback server smoke")
def test_loopback_server_serves_status_and_panes(tmp_path) -> None:
    served: list[str] = []
    diagnostics = _diagnostics(
        tmp_path, port=0, on_server=served.append)
    assert len(served) == 1 and served[0].startswith("http://localhost:")
    feed = _Feed(diagnostics)
    _run_session(feed)
    base = served[0]
    with urllib.request.urlopen(base + "status.json", timeout=5) as response:
        status = json.load(response)
    assert status["frame"] >= 1 and len(status["rows"]) == 6
    with urllib.request.urlopen(base, timeout=5) as response:
        shell = response.read()
    assert b"scan regions" in shell and b"payload tiles" in shell
    # v0.32: one responsive composed frame, not four fixed-width panes.
    assert b"width:100%" in shell
    _assert_no_aspect_ratio_declaration(shell)
    with urllib.request.urlopen(
            f"{base}frame.png?page=0&frame=1", timeout=5) as response:
        assert response.read()[:8] == b"\x89PNG\r\n\x1a\n"
    # §10.7: the exact loopback host is required — DNS rebinding refused.
    rebind = urllib.request.Request(
        base + "status.json", headers={"Host": "evil.example"})
    with pytest.raises(urllib.error.HTTPError) as refusal:
        urllib.request.urlopen(rebind, timeout=5)
    assert refusal.value.code == 403
    diagnostics.close()


def _tile_view(tmp_path: Path, width: int = 600):
    """A LiveView over the widest registered tile grid (52x36 c2 rows)."""
    from holo.receive.diag.viewer import LiveView

    spec = FORMAT_ROWS["c2-cmy7-p120-v0@3328x2304"]
    return LiveView(tmp_path / "view", spec, page_domain=(0,),
                    panel_width=width, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)


def test_payload_pane_has_no_background_stripes(tmp_path) -> None:
    """v0.32: the stream-segment split must not re-inset the tile box.

    The pre-v0.32 double inset dropped one column of every drawn tile,
    printing a background stripe per tile column ("white stripes").
    """
    from holo.receive.diag.presentation import (
        _CHIP_UNSEEN, _TILE_STATE_CERTIFIED)

    view = _tile_view(tmp_path)
    tile_y, tile_x = view._tiles_yx
    states = view._tile_states(0)
    states[:, :, :] = _TILE_STATE_CERTIFIED           # every tile drawn
    pane = view._pane_tiles(0)

    # A fully certified page leaves no untouched-grid pixel anywhere.
    unseen = np.all(pane == np.asarray(_CHIP_UNSEEN[0], np.uint8), axis=2)
    assert not unseen.any(), f"{int(unseen.sum())} background px in pane D"
    # ... and no fully-background column survives between tile columns.
    assert not np.all(unseen, axis=0).any()

    # The same must hold for a three-stream (CMY8) row, where the segment
    # split is real rather than degenerate.
    color = _tile_view(tmp_path / "cmy8")
    color._streams = ("C", "M", "Y")
    color._tiles.clear()
    color._tile_states(0)[:, :, :] = _TILE_STATE_CERTIFIED
    pane = color._pane_tiles(0)
    unseen = np.all(pane == np.asarray(_CHIP_UNSEEN[0], np.uint8), axis=2)
    assert not np.all(unseen, axis=0).any()
    assert (tile_y, tile_x) == (52, 36)


def test_word_pane_uses_one_font_for_every_count(tmp_path) -> None:
    """§10.3.3: one pane-wide count font, sized against ``100``.

    The pre-v0.32 per-label fallback printed ``100`` at size 6 beside ``42``
    at size 9 in the same pane.
    """
    from holo.receive.diag.presentation import (
        _CHIP_TEXT, _WORD_SOLVED, _glyph)

    view = _tile_view(tmp_path)
    size = view._panes.count_font()
    assert size is not None, "600px must carry counts on the 36-tile row"
    room = round(view._panes.width / view._tiles_yx[1]) - 4
    assert _glyph(size, "100")[0].size[0] <= room
    assert _glyph(size + 1, "100")[0].size[0] > room   # and it is the largest

    # Every touched tile prints at that one size: the widest label renders.
    view._word_state[(0, 0, 0)] = _WORD_SOLVED
    view._sites[(0, 0, 0)] = (1 << 100) - 1
    view._word_state[(0, 0, 1)] = _WORD_SOLVED
    view._sites[(0, 0, 1)] = (1 << 42) - 1
    pane = view._pane_words(0)

    def expected(box, text: str) -> np.ndarray:
        """The tile as it must look: one chip, one font, one text color."""
        from PIL import Image, ImageDraw

        from holo.receive.diag.presentation import _CHIP_GREEN, _blit_text
        tile = Image.new("RGB", (box[2] - box[0] + 1, box[3] - box[1] + 1),
                         _CHIP_GREEN[0])
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 0, tile.width - 1, tile.height - 1),
                       outline=_CHIP_GREEN[1])
        _blit_text(draw, (2, 1), text, _CHIP_TEXT, size)
        return np.asarray(tile)

    for tx, text in ((0, "100"), (1, "42")):
        box = view._panes.tile_box(0, tx)
        crop = pane[box[1]:box[3] + 1, box[0]:box[2] + 1]
        assert np.array_equal(crop, expected(box, text)), text


def test_word_pane_tri_state_address_authority(tmp_path) -> None:
    """v0.43 declared ruling: pane C splits green on address authority.

    Full green = the word decoder produced the address (a word-route SOLVE,
    carried by ``address.patch_accepted``'s word-tile details); lighter
    green = placement-addressed and the final word PASSED the §5.4
    known-position evaluation; observed-but-unvalidated stays amber; deep
    red stays contradiction-only and is never repainted by a later solve.
    """
    from holo.receive.diag.presentation import (
        _CHIP_AMBER, _CHIP_GREEN, _CHIP_GREEN_SOFT, _PAGE, _WORD_CONFLICT,
        _WORD_FLOOR, _WORD_SOLVED, _WORD_VALIDATED)
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=200, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    context = EventContext(lane_id="l00")
    sequence = [0]

    def emit(name: str, details=(), snapshot: object = None) -> None:
        view.feed(RuntimeEvent(sequence[0], name, Stage.ADDRESS, "b" * 64,
                               "", tuple(details), context=context,
                               snapshot=snapshot))
        sequence[0] += 1

    # A word-route acceptance names the tile the seeder decoded: SOLVED.
    emit("address.patch_accepted",
         (Detail("address.region", 0), Detail("address.patch", 0),
          Detail("address.page", 0), Detail("address.route", "word"),
          Detail("address.redundant", False),
          Detail("address.word_tile_y", 1),
          Detail("address.word_tile_x", 1)))
    assert view._word_state[(0, 1, 1)] == _WORD_SOLVED
    # A chain acceptance carries no word-tile details and marks nothing.
    emit("address.patch_accepted",
         (Detail("address.region", 0), Detail("address.patch", 1),
          Detail("address.page", 0), Detail("address.route", "chain"),
          Detail("address.redundant", False)))
    assert set(view._word_state) == {(0, 1, 1)}

    def word(ty: int, tx: int, **overrides) -> SimpleNamespace:
        row = dict(page=0, tile_yx=(ty, tx), expected_counter=0,
                   decoded_counter=0, errors=0, erasures=10,
                   certified=True, conflict=False)
        row.update(overrides)
        return SimpleNamespace(**row)

    words = (word(1, 1),                     # solved tile also matches §5.4
             word(2, 2),                     # placement-read + validated
             word(3, 3, decoded_counter=None, errors=None, erasures=40,
                  certified=False),          # observed, below the floor
             word(4, 4, certified=False, conflict=True))
    emit("address.final",
         (Detail("address.placements", 2),
          Detail("address.unresolved", 0),
          Detail("address.placements_quarantined", 0)),
         snapshot={"kind": "address", "product": SimpleNamespace(
             transient=SimpleNamespace(
                 placements=(), unresolved=(), words=words))})
    assert view._word_state[(0, 1, 1)] == _WORD_SOLVED     # green stands
    assert view._word_state[(0, 2, 2)] == _WORD_VALIDATED  # lighter green
    assert view._word_state[(0, 3, 3)] == _WORD_FLOOR      # amber unchanged
    assert view._word_state[(0, 4, 4)] == _WORD_CONFLICT
    # v0.32 ruling stands: deep red is contradiction-only and sticky — a
    # later word-route solve never repaints a conflicted tile.
    emit("address.patch_accepted",
         (Detail("address.region", 0), Detail("address.patch", 2),
          Detail("address.page", 0), Detail("address.route", "word"),
          Detail("address.redundant", False),
          Detail("address.word_tile_y", 4),
          Detail("address.word_tile_x", 4)))
    assert view._word_state[(0, 4, 4)] == _WORD_CONFLICT

    # The rendered chips differ: soft fill at each tile centre.
    pane = view._pane_words(0)
    fills = {}
    for (ty, tx), chip in (((1, 1), _CHIP_GREEN),
                           ((2, 2), _CHIP_GREEN_SOFT),
                           ((3, 3), _CHIP_AMBER)):
        box = view._panes.tile_box(ty, tx)
        centre = pane[(box[1] + box[3]) // 2, (box[0] + box[2]) // 2]
        assert tuple(int(v) for v in centre) == chip[0], (ty, tx)
        fills[(ty, tx)] = tuple(int(v) for v in centre)
    assert len(set(fills.values())) == 3       # tri-state actually renders

    # The legend under the frame names both green authorities.
    assert "green word-route solved" in _PAGE
    assert "light green placement-read + validated" in _PAGE

    # §10.3.2 row text is unchanged by the split: both greens are "match".
    from holo.receive.diag.rows import status_rows
    assert "2 match" in status_rows(view, 0)[3]


def test_scan_pane_boxes_every_detected_region(tmp_path) -> None:
    """§10.3.3: a detected region carries a tight box from survey onward,
    not only once it has been placed."""
    from holo.receive.diag.presentation import _BLUE, _GREEN
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=200, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    view.feed(RuntimeEvent(
        0, "survey.complete", Stage.SURVEY, "b" * 64, "",
        (Detail("survey.regions", 1),),
        context=EventContext(lane_id="l00"),
        snapshot=_survey_snapshot()))

    detected = view._pane_scan()
    assert np.all(detected == np.asarray(_BLUE, np.uint8), axis=2).any(), \
        "a surveyed-but-unplaced region must still be outlined"

    view._scan.set_region_state(0, "accepted")
    placed = view._pane_scan()
    assert np.all(placed == np.asarray(_GREEN, np.uint8), axis=2).any()


def test_session_phase_and_capture_resume(tmp_path) -> None:
    """v0.33 D14a: the lane row's phase tail carries the rung/tail
    announcement, and capture.resume swaps pane A to the resumed capture
    WITHOUT inflating the captures-seen counter or wholesale-clearing the
    retained per-capture pane-A model the way capture.open does.

    Event order matches the production scheduler (measured 2026-08-02):
    EVERY slot resumes, including the rung's first — whose resume must
    keep the phase tail at "capture 1/N" (the counter previously ran one
    ahead for every slot of every rung)."""
    from holo.receive.diag.rows import status_rows
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    context = EventContext(lane_id="l00")
    sequence = [0]

    def emit(name: str, details=(), snapshot: object = None,
             capture: str | None = None,
             stage: Stage = Stage.SCHEDULE) -> None:
        view.feed(RuntimeEvent(sequence[0], name, stage, capture, "",
                               tuple(details), context=context,
                               snapshot=snapshot))
        sequence[0] += 1

    emit("session.open", (Detail("captures.requested", 2),
                          Detail("captures.retained", 0)),
         stage=Stage.INGEST)
    emit("capture.open", capture="b" * 64, stage=Stage.INGEST)
    assert view._captures_seen == 1
    emit("session.phase", (Detail("phase.kind", "rung"),
                           Detail("phase.ppc", "2"),
                           Detail("phase.captures", 2)))
    assert "rung 2ppc · capture 1/2" in status_rows(view, 0)[1]
    # The rung's FIRST slot resumes too; the tail must stay at 1/2 for
    # the whole slot.
    emit("capture.resume", capture="b" * 64)
    assert view._captures_seen == 1
    assert "rung 2ppc · capture 1/2" in status_rows(view, 0)[1]
    emit("survey.complete", (Detail("survey.regions", 1),),
         snapshot=_survey_snapshot(), capture="b" * 64, stage=Stage.SURVEY)
    assert len(view._scan.regions) == 1

    # Mid-phase switch: current-capture context follows, counters do not.
    emit("capture.resume", capture="c" * 64)
    assert view._captures_seen == 1                # no inflation
    assert view._capture_sha == "c" * 64           # pane A follows (§10.5)
    assert view._scan.regions == []                # fresh capture, no model
    assert "capture 2/2" in status_rows(view, 0)[1]

    # Resuming back restores the retained pane-A model instead of the
    # capture.open wholesale reset; k stays capped at the phase total.
    emit("capture.resume", capture="b" * 64)
    assert view._captures_seen == 1
    assert len(view._scan.regions) == 1
    assert view._scan.survey_seen is True
    assert "capture 2/2" in status_rows(view, 0)[1]

    emit("session.phase", (Detail("phase.kind", "tail"),
                           Detail("phase.parked", 14)))
    assert "mop-up tail · 14 parked" in status_rows(view, 0)[1]
    assert view._phase_rung is None


def test_cold_progress_is_phase_only_and_never_milestone(tmp_path) -> None:
    """v0.33 D14c: heartbeats move only the phase text — no snapshot, no
    forced frame, no pane-A dirtying (§10.6 count-based bounding is pinned
    at the search layer)."""
    from holo.receive.diag.rows import status_rows
    from holo.receive.diag.viewer import (
        _MILESTONES, LiveView, SNAPSHOT_EVENTS)

    assert "address.cold_progress" not in _MILESTONES
    assert "address.cold_progress" not in SNAPSHOT_EVENTS
    assert "session.phase" not in SNAPSHOT_EVENTS
    assert "session.phase" not in _MILESTONES
    assert "capture.resume" not in SNAPSHOT_EVENTS

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    context = EventContext(lane_id="l00")
    view.feed(RuntimeEvent(
        0, "address.cold_open", Stage.ADDRESS, "b" * 64, "",
        (Detail("address.region", 0), Detail("address.patch", 0),
         Detail("address.window", 3), Detail("address.pages", 312)),
        context=context))
    view._scan.dirty = False
    view.feed(RuntimeEvent(
        1, "address.cold_progress", Stage.ADDRESS, "b" * 64, "",
        (Detail("address.pages", 312), Detail("address.page_ordinal", 47)),
        context=context))
    assert view._phase == "cold 47/312"
    assert view._scan.dirty is False           # heartbeat never redraws A
    assert "cold 47/312" in status_rows(view, 0)[1]


def test_parked_chips_survive_barrier_and_retire(tmp_path) -> None:
    """v0.33 D14b/D19: windows resolved "parked" become durable pane-A
    chips that survive address.final and their lane's barrier (§10.5
    exemption), print a plan-level digit, and clear only at terminal
    M-level resolution or when a committed state no longer carries them."""
    from holo.receive.diag.presentation import _PARKED_MOPUP
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    base = EventContext(lane_id="l00", level_ordinal=0)
    sequence = [0]

    def emit(name: str, details=(), snapshot: object = None,
             context: EventContext = base,
             stage: Stage = Stage.ADDRESS) -> None:
        view.feed(RuntimeEvent(sequence[0], name, stage, "b" * 64, "",
                               tuple(details), context=context,
                               snapshot=snapshot))
        sequence[0] += 1

    emit("capture.open", stage=Stage.INGEST)
    emit("survey.complete", (Detail("survey.regions", 1),),
         snapshot=_survey_snapshot(), stage=Stage.SURVEY)
    for window in (3, 4):
        emit("address.window_planned",
             (Detail("address.region", 0), Detail("address.window", window),
              Detail("address.box_y", 45), Detail("address.box_x", 65),
              Detail("address.box_h", 60), Detail("address.box_w", 60)))
        emit("address.window_resolved",
             (Detail("address.region", 0), Detail("address.window", window),
              Detail("address.outcome", "parked")))
    assert not view._scan.planned                       # transient rows resolved
    keys = {("b" * 64, "l00", 0, 3), ("b" * 64, "l00", 0, 4)}
    assert set(view._scan.parked_chips) == keys
    assert all(row[1] == "1" for row in view._scan.parked_chips.values())
    # Native-px boxes (not pane-frozen).  This lane's context carries no
    # native_per_view, so it IS native and the stored box is the emitted
    # one; the normalization is exercised in the cross-rung tests below.
    assert view._scan.parked_chips[("b" * 64, "l00", 0, 3)][0] == (45, 65, 60, 60)

    # The §10.5 exemption: address.final clears lane-local overlays but
    # not this class; the barrier snapshot carrying the durable rows keeps
    # both chips alive.
    emit("address.final", (Detail("address.placements", 0),
                           Detail("address.unresolved", 0),
                           Detail("address.placements_quarantined", 0)))
    assert set(view._scan.parked_chips) == keys

    def parked_row(window: int) -> SimpleNamespace:
        return SimpleNamespace(capture_id="b" * 64, lane_id="l00",
                               region_index=0, window_id=window)

    def barrier(*windows: int) -> dict[str, object]:
        state = SimpleNamespace(
            certificates=(), counters=None, close=None,
            parked=tuple(parked_row(window) for window in windows))
        return {"kind": "barrier", "state": state, "delta": None,
                "base_digest": None, "source_sha256": "b" * 64,
                "close": None, "spec": _SPEC}

    emit("barrier.committed", (Detail("lane.id", "l00"),),
         snapshot=barrier(3, 4), stage=Stage.SCHEDULE)
    assert set(view._scan.parked_chips) == keys
    pane = view._pane_scan()
    amber = np.all(pane == np.asarray(_PARKED_MOPUP, np.uint8), axis=2)
    assert amber.any(), "parked-for-mop-up chips must be drawn"
    prior_transform = view._scan.transform
    prior_regions = view._scan.regions

    # The M-level is an ordinary lane whose survey names its base lane and
    # carries zero regions; underlay/transform must be preserved so chips
    # stay page-aligned (not a wrong-size corner pile).
    mopup = EventContext(lane_id="m00", level_ordinal=2)
    emit("survey.complete", (Detail("survey.regions", 0),
                             Detail("survey.mopup_of", "l00")),
         snapshot={"kind": "survey",
                   "survey": SimpleNamespace(regions=()), "regions": ()},
         context=mopup, stage=Stage.SURVEY)
    assert view._scan.mopup_base == "l00"
    assert set(view._scan.parked_chips) == keys         # survey clears nothing
    assert view._scan.transform is prior_transform
    assert view._scan.regions is prior_regions
    pane = view._pane_scan()
    amber = np.all(pane == np.asarray(_PARKED_MOPUP, np.uint8), axis=2)
    assert amber.any(), "chips must still draw after empty mop-up survey"
    emit("address.window_resolved",
         (Detail("address.region", 0), Detail("address.window", 3),
          Detail("address.outcome", "accepted")), context=mopup)
    assert set(view._scan.parked_chips) == {("b" * 64, "l00", 0, 4)}

    # Retirement by committed state: the M-level's barrier no longer
    # carries the remaining row, so the last chip is erased.
    emit("barrier.committed", (Detail("lane.id", "m00"),),
         snapshot=barrier(), context=mopup, stage=Stage.SCHEDULE)
    assert view._scan.parked_chips == {}
    pane = view._pane_scan()
    amber = np.all(pane == np.asarray(_PARKED_MOPUP, np.uint8), axis=2)
    assert not amber.any()


def test_overlays_hold_one_native_frame_across_rungs(tmp_path) -> None:
    """THE e030 LAW: an overlay lands at the same pane locus no matter
    which rung emitted it, or which rung surveyed last.

    A mop-up level reuses its base lane's raster, so it emits BASE-LANE
    pixels — while the underlay belongs to whichever ladder rung surveyed
    most recently.  Pane A normalizes every overlay to capture-native
    pixels at ingest (``EventContext.native_per_view``), so one frame
    serves them all.  Before that, the M-level's coarse boxes were
    projected through the fine rung's transform and collapsed into a
    corner pile (e030 CMY8, 2026-08-05).

    l00 and l01 below describe the SAME physical region at an 8x
    resolution ratio, so their native frames are identical and any
    correctly-normalized box is pane-invariant across them."""
    from holo.receive.diag.presentation import _PARKED_MOPUP, _PENDING_OUTLINE
    from holo.receive.diag.viewer import LiveView

    view = LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=120, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)
    capture = "b" * 64
    sequence = [0]

    def emit(name, details=(), snapshot=None, context=None,
             stage: Stage = Stage.ADDRESS) -> None:
        view.feed(RuntimeEvent(sequence[0], name, stage, capture, "",
                               tuple(details), context=context or coarse,
                               snapshot=snapshot))
        sequence[0] += 1

    # Coarse base rung: 8 native px per lane px.
    coarse = EventContext(lane_id="l00", level_ordinal=0,
                          native_per_view=(8, 1))
    # Fine rung: native.  Same physical region, 8x the pixels.
    fine = EventContext(lane_id="l01", level_ordinal=1,
                        native_per_view=(1, 1))
    # Mop-up over l00 — copies its base lane's ratio (cascade _scale_plan).
    mopup = EventContext(lane_id="m00", level_ordinal=2,
                         native_per_view=(8, 1))

    # Lane-px box, far enough into the region that the UN-normalized
    # reading still lands on the pane (so the negative control measures a
    # displacement rather than a clip).
    box = (Detail("address.box_y", 60), Detail("address.box_x", 50),
           Detail("address.box_h", 6), Detail("address.box_w", 5))

    def loci(colour):
        hit = np.all(view._pane_scan() == np.asarray(colour, np.uint8),
                     axis=2)
        ys, xs = np.where(hit)
        assert len(ys) > 0, "overlay vanished from pane A"
        return float(ys.mean()), float(xs.mean())

    emit("capture.open", stage=Stage.INGEST)
    emit("survey.complete", (Detail("survey.regions", 1),),
         snapshot=_survey_snapshot(origin=(5, 7), grid=(6, 5),
                                   extent=(88, 72)),
         context=coarse, stage=Stage.SURVEY)
    emit("address.window_planned",
         (Detail("address.region", 0), Detail("address.window", 3)) + box,
         context=coarse)
    planned_on_base = loci(_PENDING_OUTLINE)
    emit("address.window_resolved",
         (Detail("address.region", 0), Detail("address.window", 3),
          Detail("address.outcome", "parked")), context=coarse)
    chip_on_base = loci(_PARKED_MOPUP)

    # The fine rung surveys the same region and replaces the underlay.
    emit("survey.complete", (Detail("survey.regions", 1),),
         snapshot=_survey_snapshot(origin=(40, 56), grid=(44, 36),
                                   extent=(704, 576)),
         context=fine, stage=Stage.SURVEY)
    assert abs(loci(_PARKED_MOPUP)[0] - chip_on_base[0]) < 2.0
    assert abs(loci(_PARKED_MOPUP)[1] - chip_on_base[1]) < 2.0

    # PRODUCTION-SHAPED M-level survey: details only, NO snapshot.  Two
    # prior fixes were dead code because they lived behind the viewer's
    # snapshot gate, which this event never passes.
    emit("survey.complete", (Detail("survey.regions", 0),
                             Detail("survey.mopup_of", "l00")),
         snapshot=None, context=mopup, stage=Stage.SURVEY)
    assert view._scan.mopup_base == "l00"
    # Retire the chip first: it occupies the same locus, and amber would
    # paint over the pending outline the assertions below measure.
    emit("address.window_resolved",
         (Detail("address.region", 0), Detail("address.window", 3),
          Detail("address.outcome", "accepted")), context=mopup)

    # The M level re-plans the window in BASE-LANE pixels.
    emit("address.window_planned",
         (Detail("address.region", 0), Detail("address.window", 3)) + box,
         context=mopup)
    planned_on_mopup = loci(_PENDING_OUTLINE)
    assert abs(planned_on_mopup[0] - planned_on_base[0]) < 2.0
    assert abs(planned_on_mopup[1] - planned_on_base[1]) < 2.0

    # NEGATIVE CONTROL: the same emission without the lane's ratio is the
    # pre-fix path — coarse pixels read as native, collapsing toward the
    # pane origin.  Proves the assertions above have teeth.
    view._scan.planned.clear()
    emit("address.window_planned",
         (Detail("address.region", 0), Detail("address.window", 9)) + box,
         context=EventContext(lane_id="m00", level_ordinal=2))
    unframed = loci(_PENDING_OUTLINE)
    assert (abs(unframed[0] - planned_on_base[0])
            + abs(unframed[1] - planned_on_base[1])) > 20.0


def test_parked_chip_digit_omitted_below_fit_keeps_outline() -> None:
    """§10.3.3 as amended: per-chip digit omission below fit, outline kept
    — never the pane-wide one-font blanking."""
    from holo.receive.diag.presentation import _PARKED_MOPUP, PaneRenderer

    panes = PaneRenderer((1536, 2240), (24, 35), 240)
    big, small = (10, 10, 60, 40), (100, 100, 103, 103)
    pane = panes.scan([], None, (), None,
                      parked=((big, "2"), (small, "2")))
    amber = np.all(pane == np.asarray(_PARKED_MOPUP, np.uint8), axis=2)
    # Both outlines are drawn...
    assert amber[big[1], big[0]:big[2]].any()
    assert amber[small[1], small[0]:small[2]].any()
    # ... the big chip prints its digit strictly inside the outline, the
    # tiny chip cannot fit one and stays outline-only inside.
    assert amber[big[1] + 1:big[3] - 1, big[0] + 1:big[2] - 1].any()
    assert not amber[small[1] + 1:small[3] - 1,
                     small[0] + 1:small[2] - 1].any()


def _durable_region(index: int, origin_yx: tuple[int, int]
                    ) -> SurveyRegionRecord:
    """A real committed region record matching ``_survey_snapshot``'s
    support shape: a 6x5 step-16 grid with cells[1:5, 1:4] true."""
    return SurveyRegionRecord(
        region_id=f"{'b' * 64}/l00/region-{index}",
        capture_id="b" * 64,
        lane_id="l00",
        origin_yx=origin_yx,
        extent_yx=(90, 76),
        support_step_px=16,
        support_shape_yx=(6, 5),
        support_runs=(SupportRun(6, 3), SupportRun(11, 3),
                      SupportRun(16, 3), SupportRun(21, 3)),
        area_mm2=25.0,
        median_tensor_score=40.0,
    )


def _durable_state() -> SimpleNamespace:
    """A committed-state stand-in carrying the real durable record types
    the v0.45 resume seed consumes: two survey regions, one accepted pose
    (its window covers page tiles (1..2, 1..2)), one parked window on the
    second region, and one durable BCH conflict at tile (4, 4)."""
    prefix = "b" * 64 + "/l00"
    pose = PoseRecord(
        pose_id=f"{prefix}/patch-1/pose",
        capture_id="b" * 64,
        lane_id="l00",
        region_id=f"{prefix}/region-0",
        patch_id=1,
        placement_outcome="accepted",
        page=0,
        cell_origin_yx=(64, 64),
        native_affine=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
        rot90=0,
        quality=0.9,
        window_id=2,
        window_origin_yx_px=(0, 0),
        window_shape_yx_cells=(128, 128),
        window_depth=0,
        lane_pose_origin_yx=(40.0, 60.0),
        lane_pose_jacobian=(4.0, 0.0, 0.0, 4.0),
        lane_pose_phase_yx=(0.0, 0.0),
        lane_pose_pitch_px=4.0,
        lane_pose_angle_deg=0.0,
        segment_support_cells=400,
        segment_phase_contrast=1.0,
        segment_pitch_yx_px=(4.0, 4.0),
        segment_orthogonality_error_deg=0.1,
    )
    parked = ParkedWindowRecord(
        parked_id=f"{prefix}/parked-5",
        capture_id="b" * 64,
        lane_id="l00",
        region_id=f"{prefix}/region-1",
        region_index=1,
        window_id=5,
        origin_yx_px=(10, 10),
        shape_yx_cells=(16, 16),
        depth=0,
        support_estimate=0.5,
        pose_origin_yx=(210.0, 70.0),
        pose_jacobian=(4.0, 0.0, 0.0, 4.0),
        pose_phase_yx=(0.0, 0.0),
        pose_pitch_px=4.0,
        pose_angle_deg=0.0,
        support_cells=100,
        phase_contrast=1.0,
        pitch_yx_px=(4.0, 4.0),
        orthogonality_error_deg=0.1,
        patch_ordinal=3,
        attempted_routes=("chain",),
        cell_pitch_px=4.0,
        lattice_f=None,
    )
    conflict = BchConflictRecord(
        page=0, tile_yx=(4, 4), decoded_counter=7, errors=2, erasures=10,
        contributor_patch_ids=(2,))
    artifact = AddressArtifact(
        address_id=f"{prefix}/address",
        survey_id=f"{prefix}/survey",
        pose_ids=(pose.pose_id,),
        bch_conflicts=(conflict,),
        parked_ids=(parked.parked_id,),
    )
    capture = SimpleNamespace(
        source_sha256="b" * 64,
        plan=(SimpleNamespace(lane_id="l00", base_lane_id="l00"),
              SimpleNamespace(lane_id="m00", base_lane_id="l00")),
        levels=(SimpleNamespace(address=artifact),),
    )
    return SimpleNamespace(
        regions=(_durable_region(0, (40, 60)), _durable_region(1, (200, 60))),
        poses=(pose,),
        parked=(parked,),
        captures=(capture,),
        certificates=(),
        counters=None,
        close=None,
    )


def _open_resumed(feed: _Feed, state: SimpleNamespace) -> None:
    feed.emit("session.open", Stage.INGEST,
              (Detail("captures.requested", 1),
               Detail("captures.retained", 1)),
              snapshot={"kind": "committed", "state": state, "spec": _SPEC})
    feed.emit("capture.open", Stage.INGEST, capture="b" * 64)


def test_resume_seeds_panes_a_and_c_from_durable_records(tmp_path) -> None:
    """v0.45 declared ruling: a resumed invocation's panes A and C start
    from durable records — the scrap layout (region support, states,
    parked chips) and the address landscape (committed placement cover,
    exact sticky conflicts) — with nothing fabricated: no preview
    underlay (pixels are never re-read), no observed-site counts, no
    mapped-footprint progress, and neither green authority (word-route
    solve and the §5.4 pass are not durably recorded)."""
    from holo.receive.diag.presentation import (
        _CHIP_AMBER_SOFT, _CHIP_RED, _CHIP_TEXT, _GREEN, _PARKED_MOPUP,
        _WORD_CONFLICT, _WORD_SEEDED)

    diagnostics = _diagnostics(tmp_path)
    feed = _Feed(diagnostics)
    _open_resumed(feed, _durable_state())
    view = diagnostics._viewer

    # Pane A: the seed lane is the base lane of the next uncommitted
    # level (M(l00)); both regions stand with their durable states.
    assert view._scan.lane == "l00"
    assert view._scan.survey_seen is True
    assert view._scan.transform is not None
    assert view._scan.underlay is None            # no pixels were re-read
    states = [region.state for region in view._scan.regions]
    assert states == ["accepted", "parked"]
    chip_key = ("b" * 64, "l00", 1, 5)
    assert set(view._scan.parked_chips) == {chip_key}
    assert view._scan.parked_chips[chip_key][1] == "1"  # plan-level digit
    pane_a = view._pane_scan()
    assert np.all(pane_a == np.asarray(_GREEN, np.uint8), axis=2).any()
    assert np.all(pane_a == np.asarray(_PARKED_MOPUP, np.uint8),
                  axis=2).any()

    # Pane C: the pose's oriented window (cells 64..192 square) covers
    # tiles (1..2, 1..2) as committed-addressed; the conflict is exact.
    seeded = {(0, 1, 1), (0, 1, 2), (0, 2, 1), (0, 2, 2)}
    assert {key for key, value in view._word_state.items()
            if value == _WORD_SEEDED} == seeded
    assert view._word_state[(0, 4, 4)] == _WORD_CONFLICT
    assert view._sites == {}                     # counts are live facts
    assert view._covered_payload == {}           # footprint is live work
    pane_c = view._pane_words(0)
    for (ty, tx), chip in (((1, 1), _CHIP_AMBER_SOFT), ((4, 4), _CHIP_RED)):
        box = view._panes.tile_box(ty, tx)
        centre = pane_c[(box[1] + box[3]) // 2, (box[0] + box[2]) // 2]
        assert tuple(int(v) for v in centre) == chip[0], (ty, tx)
    # A seeded tile prints NO count (never a fabricated zero or number).
    box = view._panes.tile_box(1, 1)
    crop = pane_c[box[1]:box[3] + 1, box[0]:box[2] + 1]
    assert not np.all(crop == np.asarray(_CHIP_TEXT, np.uint8),
                      axis=2).any()

    # The rows read the durable truth: located/placed from exact region
    # classification, the conflict on the address row, and NO seeded tile
    # in the live word-evaluation buckets.
    status = json.loads(
        (tmp_path / "diag" / "status.json").read_text())
    assert "2 located" in status["rows"][2]
    assert "1 placed" in status["rows"][2]
    assert ("words 0 match, 0 insufficient, 0 refused, 1 conflict"
            in status["rows"][3])
    assert diagnostics.failures == ()
    diagnostics.close()


def test_seeded_facts_never_double_count_live_events(tmp_path) -> None:
    """The idempotence pin: seed from durable records, then feed the same
    facts live.  Live re-reads upgrade seeded chips in place (one entry
    per (page, tile)), site counts and the mapped footprint count exactly
    once (equal to a never-seeded control view), a live re-park of the
    same window overwrites its seeded chip under the same identity key,
    and re-applying the seed changes nothing."""
    from holo.receive.diag.presentation import (
        _WORD_CONFLICT, _WORD_SEEDED, _WORD_VALIDATED)

    state = _durable_state()
    seeded_diag = _diagnostics(tmp_path / "seeded")
    seeded_feed = _Feed(seeded_diag)
    _open_resumed(seeded_feed, state)
    control_diag = _diagnostics(tmp_path / "control")
    control_feed = _Feed(control_diag)
    control_feed.emit("session.open", Stage.INGEST,
                      (Detail("captures.requested", 1),
                       Detail("captures.retained", 0)))
    control_feed.emit("capture.open", Stage.INGEST, capture="b" * 64)

    def live_session(feed: _Feed) -> None:
        # The SAME facts the seed derived from, arriving live: the survey
        # regions (rebuilt transients), the placement with its word
        # observations, and the §5.4-validated word on tile (1, 1).
        feed.emit("survey.complete", Stage.SURVEY,
                  (Detail("survey.regions", 2),),
                  snapshot={"kind": "survey",
                            "survey": SimpleNamespace(regions=tuple(
                                region_from_record(row)
                                for row in state.regions)),
                            "regions": state.regions},
                  capture="b" * 64)
        cells = np.stack(np.meshgrid(
            np.arange(64, 192), np.arange(64, 192), indexing="ij"),
            axis=-1).reshape(-1, 2)
        patch = SimpleNamespace(
            patch_id=1, region_index=0, redundant=False,
            candidate=SimpleNamespace(page=0, origin_yx=(64, 64), rot_k=0),
            page_cells_yx=cells,
            observations=tuple(
                SimpleNamespace(page=0, tile_yx=(1, 1), site_index=index)
                for index in range(21)),
        )
        word = SimpleNamespace(
            page=0, tile_yx=(1, 1), expected_counter=25, decoded_counter=25,
            errors=0, erasures=10, certified=True, conflict=False)
        feed.emit("address.final", Stage.ADDRESS,
                  (Detail("address.placements", 1),
                   Detail("address.unresolved", 0),
                   Detail("address.placements_quarantined", 0)),
                  snapshot={"kind": "address",
                            "product": SimpleNamespace(
                                transient=SimpleNamespace(
                                    placements=(patch,), unresolved=(),
                                    words=(word,)))},
                  capture="b" * 64)

    live_session(seeded_feed)
    live_session(control_feed)
    seeded_view = seeded_diag._viewer
    control_view = control_diag._viewer

    # The live survey replaced the seeded model wholesale, as any prior
    # model (region 0 then re-accepted through the live placement); the
    # live word evaluation upgraded the seeded chip in place.
    assert [row.state for row in seeded_view._scan.regions] == [
        "accepted", "surveyed"]
    assert [row.state for row in control_view._scan.regions] == [
        "accepted", "surveyed"]
    assert seeded_view._word_state[(0, 1, 1)] == _WORD_VALIDATED
    assert seeded_view._word_state[(0, 4, 4)] == _WORD_CONFLICT
    # Zero double-counting: sites, footprint, and every live-touched
    # (page, tile) state equal the never-seeded control exactly.
    assert seeded_view._sites == control_view._sites
    assert seeded_view._covered_payload == control_view._covered_payload
    for key, value in control_view._word_state.items():
        assert seeded_view._word_state[key] == value
    extra = {key: value
             for key, value in seeded_view._word_state.items()
             if key not in control_view._word_state}
    assert set(extra.values()) <= {_WORD_SEEDED, _WORD_CONFLICT}

    # A live re-park of the same durable window overwrites its seeded
    # chip under the same identity key — never a second chip.
    chip_key = ("b" * 64, "l00", 1, 5)
    assert chip_key in seeded_view._scan.parked_chips
    seeded_feed.context = EventContext(
        qualification_status="provisional", format_id=_SPEC.spec_id,
        receiver_policy_id="qualification/viewer-test/v1",
        page_domain=(0,), lane_id="l00", effective_dpi=1200.0,
        level_ordinal=0)
    seeded_feed.emit("address.window_planned", Stage.ADDRESS,
                     (Detail("address.region", 1),
                      Detail("address.window", 5),
                      Detail("address.box_y", 210),
                      Detail("address.box_x", 70),
                      Detail("address.box_h", 64),
                      Detail("address.box_w", 64)), capture="b" * 64)
    seeded_feed.emit("address.window_resolved", Stage.ADDRESS,
                     (Detail("address.region", 1),
                      Detail("address.window", 5),
                      Detail("address.outcome", "parked")),
                     capture="b" * 64)
    assert [key for key in seeded_view._scan.parked_chips
            if key == chip_key] == [chip_key]

    # Re-applying the seed is a no-op against the evolved live model.
    words_before = dict(seeded_view._word_state)
    regions_before = seeded_view._scan.regions
    seeded_view._seed_committed(state)
    assert seeded_view._word_state == words_before
    assert seeded_view._scan.regions is regions_before
    assert seeded_diag.failures == () and control_diag.failures == ()
    seeded_diag.close()
    control_diag.close()


def test_seed_runs_only_on_the_committed_bootstrap(tmp_path) -> None:
    """The headless-no-cost pin.  Seeding lives exclusively inside the
    ``session.open`` committed-snapshot branch: without an observer no
    snapshot factory ever runs (§10.6), a scalar-only observer opts out
    of snapshots entirely, and a session.open with no snapshot performs
    zero seed work.  The builders are pure functions of the frozen state
    records — they receive no raster and can touch no pixels."""
    from holo.receive.diag import JsonlDiagnostics
    from holo.receive.diag import viewer as viewer_module

    # Scalar-only diagnostics never opt into snapshots at all.
    assert not getattr(JsonlDiagnostics, "wants_snapshots", False)

    diagnostics = _diagnostics(tmp_path)
    feed = _Feed(diagnostics)
    original_words = viewer_module.seed_words
    calls = [0]

    def counting_seed(state, tiles_yx):
        calls[0] += 1
        return original_words(state, tiles_yx)

    viewer_module.seed_words = counting_seed
    try:
        feed.emit("session.open", Stage.INGEST,
                  (Detail("captures.requested", 1),
                   Detail("captures.retained", 1)))
        view = diagnostics._viewer
        assert calls[0] == 0                    # no snapshot -> no seed
        assert view._scan.seed == {}
        assert view._word_state == {}
        feed.emit("session.open", Stage.INGEST,
                  (Detail("captures.requested", 1),
                   Detail("captures.retained", 1)),
                  snapshot={"kind": "committed",
                            "state": _durable_state(), "spec": _SPEC})
        assert calls[0] == 1                    # exactly the bootstrap
    finally:
        viewer_module.seed_words = original_words
    assert diagnostics.failures == ()
    diagnostics.close()


def _cmy8_view(tmp_path: Path, width: int = 600):
    from holo.receive.diag.viewer import LiveView

    spec = FORMAT_ROWS["c3-cmy8-p120-v0@2240x1536"]
    return LiveView(tmp_path / "cmy8", spec, page_domain=(0,),
                    panel_width=width, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)


def test_payload_row_splits_certificates_per_plane(tmp_path) -> None:
    """P1 (docs/INDEPENDENT-PLANES.md §6): a colour row's whole-run
    certificate total hides the only asymmetry that matters — every
    Y-vs-C question in the 2026-08 campaign cost a multi-GB state load.
    The split rides the payload row; the block stays six rows."""
    from holo.receive.diag.presentation import _TILE_STATE_CERTIFIED
    from holo.receive.diag.rows import status_rows

    view = _cmy8_view(tmp_path)
    assert view._streams == ("C", "M", "Y")
    tiles_y, tiles_x = view._tiles_yx
    per_page = tiles_y * tiles_x

    rows = status_rows(view, 0)
    assert len(rows) == 6 and "planes" not in rows[4]   # nothing reached yet

    states = view._tile_states(0)
    states[0, :, :] = _TILE_STATE_CERTIFIED             # C: every tile
    states[1, 0, :] = _TILE_STATE_CERTIFIED             # M: one row
    rows = status_rows(view, 0)
    assert len(rows) == 6
    # Beside the total it qualifies, ahead of the row's clippable tail.
    assert (f"[C {per_page}/{per_page}, M {tiles_x}/{per_page},"
            f" Y 0/{per_page}] · {0} failed") in rows[4]

    # A second reached page grows the denominator, not a seventh row.
    view._tile_states(1)
    rows = status_rows(view, 0)
    assert len(rows) == 6
    assert f"C {per_page}/{2 * per_page}" in rows[4]


def test_payload_row_is_unchanged_for_a_one_stream_row(tmp_path) -> None:
    """K (and the packed cmy7 rows) have no per-plane certificate to
    count, so their payload row reads exactly as before."""
    from holo.receive.diag.presentation import _TILE_STATE_CERTIFIED
    from holo.receive.diag.rows import status_rows

    view = _tile_view(tmp_path)                 # c2-cmy7: one stream
    assert view._streams == ("main",)
    view._tile_states(0)[0, 0, 0] = _TILE_STATE_CERTIFIED
    assert "planes" not in status_rows(view, 0)[4]


def test_deferred_close_still_publishes_k(tmp_path) -> None:
    """v0.32: `--complete` shows K — it is the certified metadata word."""
    from holo.receive.close_progress import (
        CloseBlockProgress, CloseMetadataProgress, CloseProgress)

    diagnostics = _diagnostics(tmp_path)
    feed = _Feed(diagnostics)
    _run_session(feed)
    feed.emit("close.check", Stage.CLOSE,
              (Detail("close.status", "open"),),
              snapshot={"kind": "close",
                        "state": SimpleNamespace(certificates=()),
                        "record": SimpleNamespace(
                            status=SimpleNamespace(value="open")),
                        "progress": CloseProgress(
                            1294, 604,
                            (CloseBlockProgress(0, 1294, 604, 0, False),),
                            CloseMetadataProgress(24, 0, 0, False, 604)),
                        "spec": _SPEC,
                        "deferred_counts": True})
    row = json.loads(
        (tmp_path / "diag" / "status.json").read_text())["rows"][5]
    assert row.startswith("fountain ")
    assert "604/1294 K" in row                 # K is live under --complete
    assert "metadata trusted" in row
    assert "rank/solve deferred" in row        # and only those are deferred
    assert "rank 604/1294" not in row          # never a faked rank
    diagnostics.close()
