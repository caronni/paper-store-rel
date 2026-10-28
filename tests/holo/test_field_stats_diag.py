"""W5 measurement + illustration layer (docs/PLANE-FIELDS.md §6.2):
field_stats.py's detached observer, the diag viewer's bottom field band,
the folded status-row text, and the CLI epilogue formatter.

THE EVENT IS BUILT THE WAY PRODUCTION BUILDS IT.  ``_field_report`` below
composes the one event ``production_color.py::_plane_field_reporter``
emits — name ``payload.plane_fields``, Stage.PAYLOAD, the runtime's
``lane.id`` ahead of ``_production_diagnostics.plane_field_details``,
``PlaneFieldReport.snapshot()`` as the snapshot — and
``test_the_producer_shape_drives_every_consumer`` drives the real
producer functions end to end.  The W5 originals were synthetic against a
contract that promised a second ``stage.complete`` vehicle the producer
never emitted: they passed while both consumers were dead on real runs
(FieldStats' summary, then the status row's F fold).  Pin from the
producer (INDEPENDENT-PLANES §6 P5) — that is why this module now imports
the emission side, which the W5 version deliberately did not.

NAMING NOTE: Detail names are validated lowercase-only
(``holo.receive.types._NAME_RE``), so the plane suffix is
``.c``/``.m``/``.y`` on the wire and C/M/Y is a display-only spelling
restored in the summary rows and the status text.
"""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from holo import cli
from holo.format.registry import FORMAT_ROWS
from holo.receive.diag.field_stats import (
    FieldStats, FieldSummaryRow, replay_jsonl_row)
from holo.receive.diag.field_view import FieldPaneState, done_tiles
from holo.receive.diag.jsonl import JsonlDiagnostics
from holo.receive.diag.presentation import (
    PaneRenderer, _BG, _FIELD_DIM, _FIELD_DONE, _FIELD_HOLE, _FIELD_SHADE,
    _FIELD_STAGGER_PX, _STREAM_HUE, _TITLE_FILL, _TITLE_RULE, _TITLE_TEXT,
    _blit_text)
from holo.receive.diag.rows import _field_phrase, status_rows
from holo.receive.diag.viewer import LiveView
from holo.receive.types import Detail, EventContext, RuntimeEvent, Stage

_SPEC = FORMAT_ROWS["c3-r0550@2240x1536"]


def _event(sequence: int, name: str, stage: Stage,
           details: tuple[Detail, ...] = (), capture_id: str | None = "a" * 64,
           snapshot: object = None) -> RuntimeEvent:
    return RuntimeEvent(sequence, name, stage, capture_id=capture_id,
                        details=details, snapshot=snapshot)


def _field_report(sequence: int, lane_id: str, *, c=None, m=None,
                  y=None, coverage=None, adopted=None,
                  capture_id: str = "a" * 64,
                  snapshot: object = None) -> RuntimeEvent:
    """One producer-shaped ``payload.plane_fields`` event.

    Same name/stage/capture_id/lane.id envelope as
    ``LaneContext.progress`` builds around
    ``plane_field_details``; the keys are spelled out here so a single
    Detail can be omitted (which a real report never does, but the
    consumers must survive)."""
    details = [Detail("lane.id", lane_id)]
    if c is not None:
        details.append(Detail("plane_fields.rms_dots.c", c))
    if m is not None:
        details.append(Detail("plane_fields.rms_dots.m", m))
    if y is not None:
        details.append(Detail("plane_fields.rms_dots.y", y))
    if coverage is not None:
        details.append(Detail("plane_fields.coverage", coverage))
    if adopted is not None:
        details.append(Detail("plane_fields.adopted", adopted))
    return _event(sequence, "payload.plane_fields", Stage.PAYLOAD,
                  tuple(details), capture_id=capture_id, snapshot=snapshot)


# ---------------------------------------------------------------------
# FieldStats
# ---------------------------------------------------------------------

def test_field_stats_accumulates_rms_peak_coverage_adopted() -> None:
    stats = FieldStats()
    stats(_field_report(0, "l00", c=0.10, m=0.05, coverage=0.9,
                        adopted="C,M"))
    stats(_field_report(1, "l00", c=0.40, y=0.02, coverage=0.7,
                        adopted="C,M"))
    stats(_field_report(2, "l00", c=0.20))
    stats(_field_report(3, "l01", y=0.9, coverage=0.5, adopted=""))

    rows = {(row.capture_id, row.lane_id): row for row in stats.summary()}
    l00 = rows[("a" * 64, "l00")]
    assert l00.calls == 3
    assert l00.rms_dots == {"C": 0.20, "M": 0.05, "Y": 0.02}    # last wins
    assert l00.peak_dots == {"C": 0.40, "M": 0.05, "Y": 0.02}   # max so far
    assert l00.coverage == pytest.approx(0.7)                   # last wins
    assert l00.adopted_counts == {"C,M": 2}

    l01 = rows[("a" * 64, "l01")]
    assert l01.calls == 1
    assert l01.rms_dots == {"Y": 0.9}
    assert l01.adopted_counts == {"": 1}


def test_field_stats_reads_only_the_producer_event() -> None:
    """Dial off (no plane_fields events, ever) leaves both products
    empty/None, and there is exactly ONE vehicle: a stage.complete
    carrying plane_fields Details cannot occur — the producer never
    decorates one — so reading it would only ever match a fixture."""
    stats = FieldStats()
    stats(_event(0, "stage.complete", Stage.PAYLOAD,
                (Detail("lane.id", "l00"),)))
    stats(_event(1, "stage.open", Stage.PAYLOAD))
    stats(_event(2, "stage.complete", Stage.PAYLOAD,
                (Detail("plane_fields.rms_dots.c", 1.0),)))   # not a vehicle
    stats(_field_report(3, "l00"))     # the vehicle, but no scalar keys
    assert stats.summary() == ()
    assert stats.latest_field() is None


def test_field_stats_retains_only_the_last_valid_snapshot() -> None:
    stats = FieldStats()
    first = {"planes": [[0, 0, 0, 0.1, 0.0]], "exaggeration_hint": 10.0}
    second = {"planes": [[1, 0, 0, 0.2, 0.0]], "exaggeration_hint": 5.0}
    stats(_event(0, "payload.plane_fields", Stage.PAYLOAD, snapshot=first))
    stats(_event(1, "payload.plane_fields", Stage.PAYLOAD, snapshot=second))
    assert stats.latest_field() == second
    # Malformed snapshots (not a dict, or missing "planes") never win.
    stats(_event(2, "payload.plane_fields", Stage.PAYLOAD, snapshot="oops"))
    stats(_event(3, "payload.plane_fields", Stage.PAYLOAD, snapshot={}))
    assert stats.latest_field() == second


def test_replay_jsonl_row_round_trips_field_details() -> None:
    original = _field_report(5, "l02", c=0.33, coverage=0.42,
                             adopted="C")
    row = json.loads(json.dumps(original.to_dict()))
    replayed = replay_jsonl_row(row)
    assert replayed.snapshot is None       # the scalar log never carries one
    stats = FieldStats()
    stats(replayed)
    (summary,) = stats.summary()
    assert summary.lane_id == "l02"
    assert summary.rms_dots == {"C": 0.33}
    assert summary.coverage == pytest.approx(0.42)
    assert summary.adopted_counts == {"C": 1}


def test_field_stats_replays_a_real_jsonl_log(tmp_path) -> None:
    """The CLI epilogue's actual data path: JsonlDiagnostics writes every
    event's Details unconditionally, so replaying its file recovers the
    same accumulation a live-attached FieldStats would have produced."""
    log = JsonlDiagnostics(tmp_path / "diag")
    log(_field_report(0, "l00", c=0.5, coverage=0.6, adopted="C"))
    log(_event(1, "stage.complete", Stage.PAYLOAD,
               (Detail("lane.id", "l00"),)))  # ordinary event, no fields

    stats = FieldStats()
    with log.events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stats(replay_jsonl_row(json.loads(line)))
    (row,) = stats.summary()
    assert row.calls == 1
    assert row.rms_dots == {"C": 0.5}
    assert row.coverage == pytest.approx(0.6)


def test_receive_diagnostics_wants_the_plane_fields_snapshot(tmp_path) -> None:
    from holo.receive.diag import ReceiveDiagnostics
    from holo.receive.observer import ReceiverQualificationStatus

    diagnostics = ReceiveDiagnostics(
        tmp_path / "diag", _SPEC,
        receiver_policy_id="qualification/field-stats-test/v1",
        page_domain=(0,),
        qualification_status=ReceiverQualificationStatus.PROVISIONAL,
        qualification_notes=("field stats test",),
        interval_s=0.0, panel_width=120, port=None,
    )
    event = RuntimeEvent(0, "payload.plane_fields", Stage.PAYLOAD,
                         context=EventContext())
    assert diagnostics.wants_snapshot(event)
    diagnostics.close()


# ---------------------------------------------------------------------
# PaneRenderer.field_band
# ---------------------------------------------------------------------

def _panes(tiles_yx=(2, 2), panel_width=80) -> PaneRenderer:
    return PaneRenderer((64, 64), tiles_yx, panel_width)


def _reference_title_strip(
        panes: PaneRenderer, text: str, color: tuple[int, int, int],
) -> np.ndarray:
    """Independently reconstruct the band's title bar (fill+outline+text),
    the same way field_band builds it -- but never by copying field_band's
    OWN output, so this is a real check of what got drawn, not a tautology.
    """
    width = 4 * panes.width
    bar = panes.title_height
    image = Image.new("RGB", (width, bar), _BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, bar - 1),
                   fill=_TITLE_FILL, outline=_TITLE_RULE)
    text_xy = (7, max(1, (bar - panes.title_size) // 2 - 1))
    _blit_text(draw, text_xy, text, color, panes.title_size)
    return np.asarray(image)


def test_field_band_geometry_and_no_data_dim_title() -> None:
    panes = _panes()
    raster, factor = panes.field_band((), 1.0)
    assert factor == 0.0
    assert raster.shape == (
        panes.title_height + panes.field_body_height, 4 * panes.width, 3)
    expected = _reference_title_strip(panes, "E FIELD", _FIELD_DIM)
    assert np.array_equal(raster[:panes.title_height], expected)


def test_field_band_title_reports_the_clamped_factor() -> None:
    panes = _panes(tiles_yx=(1, 4), panel_width=80)
    # A huge delta against a huge hint: the ~2-tile-width cap must win.
    raster, factor = panes.field_band(
        ((0, 0, 0, 1000.0, 0.0),), exaggeration_hint=1e6)
    width = 4 * panes.width
    cell_w = (width - 8) / 4     # pad=4 both sides, tile_x=4
    assert factor == pytest.approx((2.0 * cell_w) / 1000.0)
    expected = _reference_title_strip(
        panes, f"E FIELD x{factor:.0f}", _TITLE_TEXT)
    assert np.array_equal(raster[:panes.title_height], expected)


def test_field_band_honours_a_tighter_hint() -> None:
    panes = _panes(tiles_yx=(1, 4), panel_width=80)
    raster, factor = panes.field_band(
        ((0, 0, 0, 10.0, 0.0),), exaggeration_hint=0.5)
    assert factor == pytest.approx(0.5)


def test_field_band_caps_a_y_arrow_against_the_block_height() -> None:
    """The band squeezes a whole page into a strip, so its blocks are far
    wider than tall.  Capping the longest arrow at 2 tile WIDTHS therefore
    let a y-pointing arrow span a dozen tile ROWS (INDEPENDENT-PLANES
    §2.6); the cap is per axis, against that axis' own block dimension."""
    panes = _panes(tiles_yx=(12, 4), panel_width=80)
    cell_w = (4 * panes.width - 8) / 4
    cell_h = (panes.field_body_height - 8) / 12
    assert cell_w > 3 * cell_h              # the anisotropy at issue

    raster, factor = panes.field_band(
        ((0, 6, 2, 0.0, 1.0),), exaggeration_hint=1e6)
    assert factor == pytest.approx(2.0 * cell_h)

    body = raster[panes.title_height:]
    drawn = np.flatnonzero(np.any(
        np.all(body == np.array(_STREAM_HUE["C"]), axis=-1), axis=1))
    span = int(drawn[-1] - drawn[0])
    # shaft (2 blocks) + the per-plane stagger + the <=4 px head, and
    # nowhere near the 12-row (whole band) reach of the width-only cap.
    assert span <= 2 * cell_h + _FIELD_STAGGER_PX + 4
    assert span < body.shape[0] / 3


def test_field_band_keeps_x_arrows_long_when_the_field_is_horizontal() -> None:
    """The per-axis cap is not a global shortening: the measured Y
    registration wander is an x sinusoid, and an all-x field must still
    draw to the full 2-tile-width reach."""
    panes = _panes(tiles_yx=(12, 4), panel_width=80)
    cell_w = (4 * panes.width - 8) / 4
    _raster, factor = panes.field_band(
        ((0, 6, 2, 1.0, 0.0), (1, 6, 2, -0.5, 0.0)), exaggeration_hint=1e6)
    assert factor == pytest.approx(2.0 * cell_w)


def test_field_band_shades_only_blocks_at_or_above_threshold() -> None:
    panes = _panes(tiles_yx=(1, 2), panel_width=80)
    raster, _factor = panes.field_band(
        ((0, 0, 0, 0.25, 0.0), (1, 0, 1, 0.10, 0.0)),
        exaggeration_hint=1.0, threshold_dots=0.25)
    body = raster[panes.title_height:]
    cell_w = body.shape[1] // 2
    left_shaded = np.any(np.all(
        body[:, :cell_w] == np.array(_FIELD_SHADE), axis=-1))
    right_shaded = np.any(np.all(
        body[:, cell_w:] == np.array(_FIELD_SHADE), axis=-1))
    assert left_shaded and not right_shaded


def test_field_band_draws_the_plane_stream_colour() -> None:
    panes = _panes(tiles_yx=(1, 1), panel_width=80)
    raster, _factor = panes.field_band(
        ((0, 0, 0, 40.0, 0.0),), exaggeration_hint=1.0)   # plane 0 == C
    body = raster[panes.title_height:]
    color = np.array(_STREAM_HUE["C"])
    assert np.any(np.all(body == color, axis=-1))


def test_field_band_out_of_range_tiles_are_dropped() -> None:
    panes = _panes(tiles_yx=(1, 1), panel_width=80)
    raster, factor = panes.field_band(
        ((0, 5, 5, 3.0, 0.0),), exaggeration_hint=1.0)
    # No in-range magnitude to normalize against: falls back to the hint.
    assert factor == pytest.approx(1.0)


# ---------------------------------------------------------------------
# LiveView: byte-stability, band growth, dirty/revision tracking
# ---------------------------------------------------------------------

def _live_view(tmp_path, panel_width: int = 120) -> LiveView:
    return LiveView(tmp_path / "view", _SPEC, page_domain=(0,),
                    panel_width=panel_width, interval_s=1000.0, port=None,
                    clock=lambda: 0.0)


def _emitter(view: LiveView, context: EventContext):
    sequence = [0]

    def emit(name: str, stage: Stage, details: tuple[Detail, ...] = (),
             snapshot: object = None) -> None:
        view.feed(RuntimeEvent(sequence[0], name, stage, "b" * 64, "",
                               tuple(details), context=context,
                               snapshot=snapshot))
        sequence[0] += 1

    return emit


def test_no_plane_fields_event_composes_byte_identical_frames(tmp_path) -> None:
    """The null proof (W2 dial-off requirement): a session that never sees
    a payload.plane_fields snapshot, nor any plane_fields Details, must
    compose byte-identical frames to a bare four-pane compose() call --
    the pre-existing behaviour, unchanged."""
    view = _live_view(tmp_path)
    emit = _emitter(view, EventContext(lane_id="l00"))
    emit("session.open", Stage.INGEST)
    emit("capture.open", Stage.INGEST)
    emit("stage.complete", Stage.PAYLOAD, (Detail("lane.id", "l00"),))
    view._render(force=True, compose_all=True)

    assert view._field.band(view._panes, 0) is None
    png = view._png[0]
    reference = view._panes.compose((
        view._raster[("A", -1)], view._raster[("B", 0)],
        view._raster[("C", 0)], view._raster[("D", 0)]))
    assert png == reference
    with Image.open(io.BytesIO(png)) as frame:
        assert frame.height == view._panes.title_height + view._panes.height
        assert frame.width == 4 * view._panes.width


def test_plane_fields_snapshot_grows_the_band_and_carries_the_title(
        tmp_path) -> None:
    view = _live_view(tmp_path)
    emit = _emitter(view, EventContext(lane_id="l00"))
    emit("session.open", Stage.INGEST)
    emit("capture.open", Stage.INGEST)
    view._render(force=True, compose_all=True)
    baseline_height = Image.open(io.BytesIO(view._png[0])).height

    emit("payload.plane_fields", Stage.PAYLOAD,
         snapshot={"planes": [[0, 0, 0, 0.5, 0.1]],
                   "exaggeration_hint": 20.0})
    view._render(force=True, compose_all=True)

    expected_raster, expected_factor = view._panes.field_band(
        ((0, 0, 0, 0.5, 0.1),), 20.0)
    assert expected_factor > 0
    assert np.array_equal(view._field.band(view._panes, 0), expected_raster)

    grown = Image.open(io.BytesIO(view._png[0]))
    band_h = expected_raster.shape[0]
    assert grown.height == baseline_height + band_h
    assert grown.width == 4 * view._panes.width
    composed = np.asarray(grown.convert("RGB"))
    assert np.array_equal(composed[-band_h:], expected_raster)


def test_second_snapshot_forces_recomposition(tmp_path) -> None:
    view = _live_view(tmp_path)
    emit = _emitter(view, EventContext(lane_id="l00"))
    emit("session.open", Stage.INGEST)
    emit("capture.open", Stage.INGEST)
    emit("payload.plane_fields", Stage.PAYLOAD,
         snapshot={"planes": [[0, 0, 0, 0.5, 0.0]],
                   "exaggeration_hint": 5.0})
    view._render(force=True, compose_all=True)
    first_png = view._png[0]
    first_revision = view._field.revision

    emit("payload.plane_fields", Stage.PAYLOAD,
         snapshot={"planes": [[0, 0, 0, 2.0, 0.0]],
                   "exaggeration_hint": 5.0})
    view._render(force=True, compose_all=True)
    assert view._field.revision == first_revision + 1
    assert view._png[0] != first_png


def test_finalize_composes_the_band_in_the_terminal_frame(tmp_path) -> None:
    view = _live_view(tmp_path)
    emit = _emitter(view, EventContext(lane_id="l00"))
    emit("session.open", Stage.INGEST)
    emit("capture.open", Stage.INGEST)
    emit("payload.plane_fields", Stage.PAYLOAD,
         snapshot={"planes": [[2, 1, 1, 0.3, -0.2]],
                   "exaggeration_hint": 8.0})
    view.finalize(SimpleNamespace(status=None))
    with Image.open(io.BytesIO(view._png[0])) as frame:
        assert frame.height > view._panes.title_height + view._panes.height


# ---------------------------------------------------------------------
# rows.py: the folded F status-row text
# ---------------------------------------------------------------------

def test_field_phrase_only_appears_when_data_exists() -> None:
    empty = SimpleNamespace(_field=FieldPaneState())
    assert _field_phrase(empty) == ""
    full = SimpleNamespace(_field=FieldPaneState(
        rms={"C": 0.05, "Y": -0.1}, adopted="C,M"))
    assert _field_phrase(full) == "F C+0.05d Y-0.10d [C,M]"


def test_field_phrase_is_empty_without_a_field_state() -> None:
    assert _field_phrase(SimpleNamespace()) == ""


# ---------------------------------------------------------------------
# field_view.py: FieldPaneState
# ---------------------------------------------------------------------

def test_field_pane_state_ingest_snapshot_and_details() -> None:
    state = FieldPaneState()
    assert state.snapshot is None and not state.dirty and state.revision == 0

    state.ingest_snapshot({"planes": [[0, 1, 1, 0.5, 0.0]],
                           "exaggeration_hint": 4.0})
    assert state.dirty and state.revision == 1
    assert state.snapshot["exaggeration_hint"] == 4.0

    state.dirty = False
    state.ingest_snapshot("not a dict")   # malformed: ignored
    state.ingest_snapshot({"no_planes_key": True})   # malformed: ignored
    assert not state.dirty and state.revision == 1

    state.ingest_details(
        {"lane.id": "l00", "plane_fields.rms_dots.c": 0.12,
         "plane_fields.adopted": "C"})
    assert state.rms == {"C": 0.12}
    assert state.adopted == "C"
    state.ingest_details({"lane.id": "l00"})   # ordinary event: no-op
    assert state.rms == {"C": 0.12} and state.adopted == "C"


def test_field_pane_state_build_raster_and_phrase() -> None:
    state = FieldPaneState()
    assert state.phrase() == ""
    panes = PaneRenderer((64, 64), (1, 1), 80)
    empty_raster, _factor = panes.field_band((), 1.0)
    assert np.array_equal(state.build_raster(panes), empty_raster)

    state.ingest_snapshot({"planes": [[0, 0, 0, 10.0, 0.0]],
                           "exaggeration_hint": 2.0})
    expected, _factor = panes.field_band(((0, 0, 0, 10.0, 0.0),), 2.0)
    assert np.array_equal(state.build_raster(panes), expected)

    state.ingest_details({"plane_fields.rms_dots.m": -0.07})
    assert state.phrase() == "F M-0.07d [none]"


def test_done_rows_accept_both_pinned_shapes() -> None:
    """``[ty, tx]`` is page-less and applies everywhere; ``[page, ty, tx]``
    belongs to its own page only.  The length-blind unpack read a 3-row as
    ``(page, ty)``, i.e. painted the wrong tile on every page."""
    rows = ([1, 2], (0, 3, 4), [1, 3, 5], "junk", [7])
    assert list(done_tiles(rows, 0)) == [(1, 2), (3, 4)]
    assert list(done_tiles(rows, 1)) == [(1, 2), (3, 5)]
    assert list(done_tiles(rows, 2)) == [(1, 2)]
    # No page context: every row counts, whatever page it names.
    assert list(done_tiles(rows, None)) == [(1, 2), (3, 4), (3, 5)]


def test_band_paints_only_this_page_as_done() -> None:
    """A certified tile on page 0 must not read as "nothing left to
    measure" on page 1, where it is the blind spot the operator is
    hunting (the black/green split, PLANE-FIELDS §6.2)."""
    state = FieldPaneState()
    panes = PaneRenderer((128, 128), (1, 2), 80)
    state.ingest_snapshot({
        "planes": [[0, 0, 0, 0.5, 0.0]],       # tile (0,0) covered
        "done": [[0, 0, 1], [1, 0, 1]],        # tile (0,1) done on BOTH
        "exaggeration_hint": 2.0})
    page0 = state.band(panes, 0)
    state.ingest_snapshot({
        "planes": [[0, 0, 0, 0.5, 0.0]],
        "done": [[0, 0, 1]],                   # done on page 0 only
        "exaggeration_hint": 2.0})
    assert np.array_equal(state.band(panes, 0), page0)   # page 0 unchanged
    page1 = state.band(panes, 1)
    body = page1[panes.title_height:]
    right = body[:, body.shape[1] // 2:]
    assert np.any(np.all(right == np.array(_FIELD_HOLE), axis=-1))
    assert not np.any(np.all(right == np.array(_FIELD_DONE), axis=-1))


def test_band_cache_is_per_page_and_dropped_on_a_new_snapshot() -> None:
    state = FieldPaneState()
    panes = PaneRenderer((128, 128), (1, 2), 80)
    assert state.band(panes, 0) is None          # dial off: no band at all
    state.ingest_snapshot({"planes": [[0, 0, 0, 0.5, 0.0]],
                           "done": [], "exaggeration_hint": 2.0})
    first = state.band(panes, 0)
    assert state.band(panes, 0) is first         # cached, not re-rendered
    state.band(panes, 1)
    state.retain({0})
    state.ingest_snapshot({"planes": [[2, 0, 1, 0.5, 0.0]],
                           "done": [], "exaggeration_hint": 2.0})
    assert not np.array_equal(state.band(panes, 0), first)


def test_status_row_folds_field_text_only_when_data_exists(tmp_path) -> None:
    view = _live_view(tmp_path)
    emit = _emitter(view, EventContext(lane_id="l00"))
    emit("session.open", Stage.INGEST,
        (Detail("captures.requested", 1), Detail("captures.retained", 0)))

    before = status_rows(view, 0)
    assert len(before) == 6
    assert "F " not in before[0]

    emit("payload.plane_fields", Stage.PAYLOAD,
        (Detail("lane.id", "l00"), Detail("plane_fields.rms_dots.c", 0.42),
         Detail("plane_fields.adopted", "C")))
    after = status_rows(view, 0)
    assert len(after) == 6
    assert "F C+0.42d [C]" in after[0]
    # Only the format row changed; the six-row invariant stays a fixed
    # SET of concerns, not a fixed set of bytes.
    assert after[1:] == before[1:]


# ---------------------------------------------------------------------
# CLI epilogue: _print_plane_fields
# ---------------------------------------------------------------------

def _certificate(page: int, stream_id: str):
    return SimpleNamespace(page=page, stream_id=stream_id)


def test_print_plane_certificates_splits_a_colour_row(capsys) -> None:
    """P1 (docs/INDEPENDENT-PLANES.md §6): certified AND open per plane,
    over the page domain actually in play."""
    spec = FORMAT_ROWS["c3-cmy8-p120-v0@2240x1536"]
    per_page = spec.tiles_per_page
    state = SimpleNamespace(certificates=(
        *(_certificate(0, "C") for _ in range(3)),
        *(_certificate(0, "M") for _ in range(2)),
        _certificate(1, "C"),
    ))
    cli._print_plane_certificates(state, spec, None)
    out = capsys.readouterr().out
    slots = 2 * per_page                      # pages 0 and 1 both reached
    assert f"planes (2 page(s) × {per_page} tiles = {slots} slots/plane)" in out
    assert f"C 4 certified, {slots - 4} open" in out
    assert f"M 2 certified, {slots - 2} open" in out
    assert f"Y 0 certified, {slots} open" in out


def test_print_plane_certificates_counts_requested_pages(capsys) -> None:
    """--page widens the domain even where nothing certified: the pages
    were asked for, so their slots are open, not absent."""
    spec = FORMAT_ROWS["c3-cmy8-p120-v0@2240x1536"]
    cli._print_plane_certificates(
        SimpleNamespace(certificates=(_certificate(0, "Y"),)), spec, (0, 1))
    out = capsys.readouterr().out
    assert f"= {2 * spec.tiles_per_page} slots/plane" in out
    assert "Y 1 certified" in out


def test_print_plane_certificates_never_invents_a_denominator(capsys) -> None:
    """§10.3.2's rule, ported: with no page reached and none requested
    there is no slot denominator, and zero open is not the answer."""
    spec = FORMAT_ROWS["c3-cmy8-p120-v0@2240x1536"]
    cli._print_plane_certificates(
        SimpleNamespace(certificates=()), spec, None)
    out = capsys.readouterr().out
    assert "C 0 certified · M 0 certified · Y 0 certified" in out
    assert "open slots unavailable (no page reached)" in out
    assert "0 open" not in out


def test_print_plane_certificates_is_silent_for_one_stream_rows(capsys) -> None:
    """K output is unchanged, and the packed cmy7 rows have no per-plane
    certificate to count either."""
    state = SimpleNamespace(certificates=(_certificate(0, "main"),))
    for row_id in ("c3-r0550@2240x1536", "c3-cmy7-p120-v0@2240x1536"):
        cli._print_plane_certificates(state, FORMAT_ROWS[row_id], (0,))
        assert capsys.readouterr().out == ""


def test_print_plane_fields_is_silent_on_empty_summary(capsys) -> None:
    cli._print_plane_fields(())
    assert capsys.readouterr().out == ""


def test_print_plane_fields_formats_a_synthetic_summary(capsys) -> None:
    row = FieldSummaryRow(
        capture_id="a" * 64, lane_id="l00", calls=3,
        rms_dots={"C": 0.12, "M": 0.03},
        peak_dots={"C": 0.40, "M": 0.05},
        coverage=0.83,
        adopted_counts={"C,M": 2, "": 1},
    )
    cli._print_plane_fields((row,))
    out = capsys.readouterr().out
    assert "plane fields aaaaaaaaaaaa/l00 (3 event(s))" in out
    assert "C rms 0.12d peak 0.40d" in out
    assert "M rms 0.03d peak 0.05d" in out
    assert "coverage 83.0%" in out
    assert "(none)×1" in out and "C,M×2" in out


def test_print_plane_fields_handles_missing_rms_and_coverage(capsys) -> None:
    row = FieldSummaryRow(
        capture_id="", lane_id="", calls=1, rms_dots={}, peak_dots={},
        coverage=None, adopted_counts={},
    )
    cli._print_plane_fields((row,))
    out = capsys.readouterr().out
    assert "no per-plane rms reported" in out
    assert "coverage n/a" in out
    assert "adopted (none)" in out


def _production_event(sequence: int = 1, lane_id: str = "l01-4ppc-1200dpi",
                      **report_kwargs) -> RuntimeEvent:
    """The event the PRODUCER builds, through the producer's own code.

    ``production_color.py::_plane_field_reporter`` calls
    ``LaneContext.progress("payload.plane_fields", details=
    plane_field_details(row), snapshot_factory=…plane_fields(row))``, and
    ``LaneContext.progress`` prepends ``lane.id``; the runtime stamps
    stage and capture_id.  Building it any other way is how the W5 layer
    shipped two dead consumers.
    """
    from holo.receive import _production_diagnostics
    from holo.receive.color_field import PlaneFieldReport

    defaults = dict(
        rms_dots=(0.31, 0.42, 0.29),
        peak_dots=(0.55, 0.61, 0.44),
        coverage_by_plane=(0.99, 0.98, 0.97),
        coverage=0.98,
        adopted=("C", "M", "Y"),
        regions=4,
        regions_adopted_by_plane=(4, 4, 3),
        n_samples=1200,
        quiver=((0, 1, 2, 0.5, -0.1),),
        # PAGE-AWARE rows (INDEPENDENT-PLANES §6 P1): the producer emits
        # (page, tile_y, tile_x), filled from the certificate set rather
        # than from whatever the probe pass happened to reach.
        done_tiles=((0, 0, 0),),
        exaggeration_hint=40.0,
    )
    defaults.update(report_kwargs)
    row = PlaneFieldReport(**defaults)
    return RuntimeEvent(
        sequence, "payload.plane_fields", Stage.PAYLOAD,
        capture_id="a" * 64,
        details=(Detail("lane.id", lane_id),
                 *_production_diagnostics.plane_field_details(row)),
        snapshot=row.snapshot(),
    )


def test_the_producer_shape_drives_every_consumer(tmp_path) -> None:
    """ONE event, both consumers (INDEPENDENT-PLANES §6 P1/P5).

    The W6 qualification run measured ``summary() == ()`` on 25 real
    field reports, and the status row's F fold stayed dead after that fix
    because only FieldStats was repaired — the class, not the instance.
    This drives the real producer through both.
    """
    event = _production_event()

    stats = FieldStats()
    stats(event)
    rows = stats.summary()
    assert rows, "the producer's event must populate the summary"
    assert rows[0].rms_dots["M"] == pytest.approx(0.42)
    assert rows[0].coverage == pytest.approx(0.98)
    assert rows[0].lane_id == "l01-4ppc-1200dpi"
    assert stats.latest_field() is not None

    view = _live_view(tmp_path)
    view.feed(RuntimeEvent(0, "session.open", Stage.INGEST,
                           context=EventContext(lane_id="l00")))
    view.feed(event)
    assert view._field.rms and view._field.adopted == "C,M,Y"
    assert "F C+0.31d M+0.42d Y+0.29d [C,M,Y]" in status_rows(view, 0)[0]
    assert view._field.revision == 1
    assert view._field.band(view._panes, 0) is not None
