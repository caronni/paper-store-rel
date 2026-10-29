"""The address-word contradiction alarm: detector, seam, and silence.

D1 (Germano, 2026-09-04) accepted the loss of v1's quarantine and asked
for the alarm alone: a word that decodes legally and names a printed
position a standing placement of the same capture puts somewhere else is
an event, a loud stderr line and a diag counter — and nothing else.  The
last three tests here are that "nothing else".
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.descriptor import KEY_POSE_AFFINE
from holo.receiver.diag import model as diag_model
from holo.receiver.diag import panes, readout as diag_readout, report as diag_report
from holo.receiver.lib import geometry
from holo.receiver.plugins import contradiction, place, place_sched
from holo.receiver.tests import _h3_facts, _h3_support

CAPTURE = _h3_facts.CAPTURE_ID
#: the fixture region's printed pitch: 1200 dpi over c3's 1/200 inch
#: cell, which is what `place.region_frame` derives for it
PITCH_PX = 6.0
#: its window lattice: `geometry.window_starts(341)` over a 2048 px
#: region, asserted against the store's own plan below
HOME = (0, 0, 200, 200)
EAST = (0, 141, 200, 341)
SOUTH = (141, 0, 341, 200)
OVERLAP = (0, 141, 200, 200)
FORMAT_ID = "holo/v2/1i300-k-r0550-p60-v1@3x3"


def _wid(extent: tuple[int, int, int, int],
         level_index: int = 0) -> tuple:
    return (CAPTURE, level_index, 0, extent)


def _placement(extent: tuple[int, int, int, int],
               offset_cells: tuple[float, float] = (0.0, 0.0),
               page: int = 0, route: str = place.ROUTE_WORD,
               level_index: int = 0) -> data.Placement:
    """A placement of `extent` that reads the paper cell under it as the
    page cell `offset_cells` away — zero offset is the honest one."""
    dy, dx = offset_cells
    return data.Placement(
        window_id=_wid(extent, level_index), capture_id=CAPTURE,
        level_index=level_index, region_index=0, patch_ordinal=0,
        page=page, rot_k=0, page_origin_yx=(extent[0], extent[1]),
        native_affine=(PITCH_PX, 0.0, -PITCH_PX * dy,
                       0.0, PITCH_PX, -PITCH_PX * dx),
        pitch_px=PITCH_PX, route=route,
        local_cells_yx=_h3_facts.tile_cells())


def _capture(n_levels: int = 1) -> data.Capture:
    base = _h3_facts.capture()
    levels = tuple(
        data.Level(index=index, ppc=Fraction(4, index + 1),
                   scale=Fraction(index + 1), shape_px=base.shape_px,
                   label=f"l{index}")
        for index in range(n_levels))
    return dataclasses.replace(base, levels=levels)


def _survey() -> data.CaptureSurvey:
    """The shared fixture's region, supported over its whole extent so
    the plan lays the four windows this module places on."""
    base = _h3_facts.survey()
    region = dataclasses.replace(base.regions[0],
                                 cells=np.ones((64, 64), bool))
    return dataclasses.replace(base, regions=(region,))


def _store(n_levels: int = 1) -> object:
    store = _h3_facts.new_engine()
    store._ingest(_capture(n_levels))
    store._ingest(_survey())
    return store


@pytest.fixture()
def store() -> object:
    return _store()


def _find(store: object, standing: data.Placement,
          arriving: data.Placement) -> tuple[data.Contradiction, ...]:
    store._ingest(standing)
    return contradiction.find(store, arriving)


def test_the_planned_windows_this_test_uses_are_real_ring_neighbours(store):
    assert _wid(EAST) in contradiction.neighbour_windows(store, _wid(HOME))
    assert _wid(SOUTH) in contradiction.neighbour_windows(store, _wid(HOME))
    for extent in (HOME, EAST, SOUTH):
        assert store.window(_wid(extent)) is not None
    frame = store.frame(_wid(HOME)[:3])
    assert frame.pitch_native_px == PITCH_PX
    assert contradiction.overlap_cells(HOME, EAST) == OVERLAP
    assert contradiction.probe_native_yx(frame, OVERLAP) == (
        PITCH_PX * 100.0, PITCH_PX * 170.5)


def test_the_neighbour_set_is_the_relation_the_scheduler_subscribes_to(
        store):
    """One relation, two consumers: the check looks exactly where the
    place row already registers its pose reads, so it can never walk the
    placement table and can never see a window the scheduler ignores."""
    subscribed = tuple(
        key[1] for key in place_sched._place_reads(store, _wid(HOME))
        if key[0] == KEY_POSE_AFFINE)
    assert contradiction.neighbour_windows(store, _wid(HOME)) == subscribed
    assert _wid(HOME) not in subscribed


def test_two_placements_that_agree_on_the_paper_mint_nothing(store):
    assert _find(store, _placement(HOME), _placement(EAST)) == ()


def test_a_sub_cell_pose_difference_is_not_a_contradiction(store):
    """The false-alarm bar.  Two honest fits of the same cell differ by
    a fraction of one; below a whole cell they are reading the same
    printed cell and the alarm must stay silent."""
    found = _find(store, _placement(HOME),
                  _placement(EAST, offset_cells=(0.4, -0.4)))
    assert found == ()


def test_a_word_a_whole_cell_off_its_neighbour_is_a_contradiction(store):
    found = _find(store, _placement(HOME),
                  _placement(EAST, offset_cells=(1.0, 0.0)))
    assert len(found) == 1
    row = found[0]
    assert row.capture == CAPTURE
    assert row.window_id == _wid(EAST)
    assert row.standing_window_id == _wid(HOME)
    assert row.route == place.ROUTE_WORD
    assert row.overlap_cells == OVERLAP
    assert row.delta_cells_yx == pytest.approx((1.0, 0.0))
    assert row.tile_yx == (1, 2) and row.standing_tile_yx == (1, 2)


def test_the_contradiction_names_the_tile_each_side_asserts(store):
    found = _find(store, _placement(HOME),
                  _placement(EAST, offset_cells=(-64.0, 0.0)))
    assert len(found) == 1
    # the probe cell is (100, 180): a whole tile up on the arriving side
    assert found[0].tile_yx == (0, 2)
    assert found[0].standing_tile_yx == (1, 2)
    assert found[0].delta_cells_yx == pytest.approx((-64.0, 0.0))


def test_a_different_page_over_the_same_cells_is_a_contradiction(store):
    """No pose difference at all: same paper, same cells, two pages."""
    found = _find(store, _placement(HOME), _placement(EAST, page=1))
    assert len(found) == 1
    assert (found[0].page, found[0].standing_page) == (1, 0)
    assert found[0].delta_cells_yx == pytest.approx((0.0, 0.0))


def test_the_same_extent_at_another_rung_is_compared_too():
    """The capture's other levels see the same paper through their own
    poses, so a lane that disagrees with itself is caught."""
    store = _store(n_levels=2)
    assert _wid(HOME) in contradiction.neighbour_windows(store,
                                                         _wid(HOME, 1))
    store._ingest(_placement(HOME))
    found = contradiction.find(
        store, _placement(HOME, offset_cells=(3.0, 0.0), level_index=1))
    assert len(found) == 1
    assert found[0].standing_window_id == _wid(HOME)
    assert found[0].window_id == _wid(HOME, 1)
    assert found[0].overlap_cells == HOME


def test_only_a_word_route_produces_a_contradiction(store):
    """v1 counted contradictions among ACCEPTED placements only, and the
    producer is the decoded word: a chain or a refined pose asserts an
    address it inherited, not one it read."""
    off = (1.0, 0.0)
    assert contradiction.PRODUCING_ROUTES == frozenset({place.ROUTE_WORD})
    for route in (place.ROUTE_CHAIN, place.ROUTE_COLD, data.ROUTE_REFINE):
        assert _find(store, _placement(HOME),
                     _placement(EAST, offset_cells=off, route=route)) == ()
    assert _find(store, _placement(HOME),
                 _placement(EAST, offset_cells=off)) != ()


def test_a_window_with_no_standing_neighbour_mints_nothing(store):
    assert contradiction.find(store, _placement(EAST,
                                                offset_cells=(9.0, 9.0))) == ()


def test_a_singular_pose_is_named_on_stderr_and_never_raises(
        store, capsys: pytest.CaptureFixture):
    broken = data.Placement(
        window_id=_wid(EAST), capture_id=CAPTURE, level_index=0,
        region_index=0, patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(0, 0),
        native_affine=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0), pitch_px=PITCH_PX,
        route=place.ROUTE_WORD, local_cells_yx=_h3_facts.tile_cells())
    store._ingest(_placement(HOME))
    events: list = []
    with pytest.raises(ValueError):
        contradiction.find(store, broken)
    assert contradiction.check(store, broken, events) == 0
    assert events == []
    assert "contradiction: check failed" in capsys.readouterr().err


# --- the seam: what the fold does with one -------------------------------

def test_the_fold_emits_one_event_and_one_loud_line(
        store, capsys: pytest.CaptureFixture):
    store._ingest(_placement(HOME))
    capsys.readouterr()
    store._ingest(_placement(EAST, offset_cells=(2.0, 0.0)))
    lines = [line for line in capsys.readouterr().err.splitlines() if line]
    rows = [event for event in store._events
            if isinstance(event, data.Contradiction)]
    assert len(rows) == 1
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("CONTRADICTION: capture ")
    assert "decoded page 0 tile 1,2 rot 0 (word)" in line
    assert "asserts page 0 tile 1,2 rot 0 (word)" in line
    assert f"{OVERLAP}, apart by +2.00,+0.00 cells" in line
    assert line.endswith(
        "quarantine is not built; the payload is unaffected")
    assert line == contradiction.warning_line(rows[0])


def test_the_contradicted_placement_still_stands_and_still_owns_its_cells(
        store):
    """The whole ruling in one assertion: the alarm changes nothing.

    The arriving placement is accepted, keeps its pose, its page and its
    cells, and its window is placed — a quarantine would have refused
    every one of those.
    """
    store._ingest(_placement(HOME))
    arriving = _placement(EAST, offset_cells=(2.0, 0.0))
    store._ingest(arriving)
    assert store.placement(_wid(EAST)) is arriving
    assert store.place_stage(_wid(EAST)).placed is True
    assert store.page_cells(_wid(EAST)) is not None
    assert store.live_pages() == frozenset({0})


def test_a_contradicting_fold_writes_exactly_the_cells_a_clean_one_does():
    """No key family, no cell, no wake: the fold's footprint is the
    footprint it had before this row existed."""
    written = []
    for offset in ((0.0, 0.0), (2.0, 0.0)):
        store = _store()
        store._ingest(_placement(HOME))
        before, _hold_before = _h3_facts.store_snapshot(store)
        changed, keys, kind = store._fold(
            _placement(EAST, offset_cells=offset))
        after, _hold_after = _h3_facts.store_snapshot(store)
        written.append((changed, keys, kind,
                        _h3_facts.cells_written(before, after)))
    assert written[0] == written[1]


def test_the_alarm_is_silent_on_a_run_that_places_honestly(
        store, capsys: pytest.CaptureFixture):
    store._ingest(_placement(HOME))
    store._ingest(_placement(EAST))
    store._ingest(_placement(SOUTH))
    assert [event for event in store._events
            if isinstance(event, data.Contradiction)] == []
    assert "CONTRADICTION" not in capsys.readouterr().err


# --- the diag half -------------------------------------------------------

def _row(page: int = 0, standing_page: int = 0,
         tile_yx: tuple[int, int] = (1, 1),
         standing_tile_yx: tuple[int, int] = (2, 2)) -> data.Contradiction:
    return data.Contradiction(
        capture=CAPTURE, window_id=_wid(EAST), standing_window_id=_wid(HOME),
        route=place.ROUTE_WORD, standing_route=place.ROUTE_WORD, page=page,
        standing_page=standing_page, page_origin_yx=(0, 0),
        standing_page_origin_yx=(0, 0), rot_k=0, standing_rot_k=0,
        tile_yx=tile_yx, standing_tile_yx=standing_tile_yx,
        overlap_cells=(0, 160, 200, 200), delta_cells_yx=(2.0, 0.0))


def _run_open(pages: int = 1) -> data.RunOpen:
    return data.RunOpen(format_id=FORMAT_ID, pages=pages, tiles_yx=(3, 3),
                        stream_ids=("main",), n_captures=1, workers=1,
                        family="k")


def _folded(*rows: data.Contradiction) -> diag_model.DiagModel:
    return diag_model.fold(diag_model.empty(), (_run_open(2),) + rows)


def test_the_diag_counter_and_the_page_marks_follow_the_events():
    model = _folded(_row(), _row(page=1, tile_yx=(0, 0)))
    assert model.contradictions == 2
    assert model.fold_errors == 0
    # the second row's own page is 1 and the placement it contradicts
    # still stands on page 0: both sides are marked, each on its page
    assert model.contradicted_tiles == {0: {(1, 1), (2, 2)},
                                        1: {(0, 0)}}
    assert model.last_contradiction is not None
    assert model.last_contradiction.page == 1


def test_the_conflict_row_is_absent_until_the_alarm_fires():
    assert diag_readout.conflict_rows(_folded()) == ()
    assert len(diag_readout.all_rows(_folded())) == len(
        diag_readout.six_row_status(_folded()))
    rows = diag_readout.conflict_rows(_folded(_row()))
    assert len(rows) == 1
    assert rows[0].startswith(diag_readout.CONFLICT_ROW_PREFIX)
    assert rows[0].startswith("conflict 1 address contradiction ·")
    assert "page 0 tile 1,1" in rows[0] and "page 0 tile 2,2" in rows[0]
    assert rows[0].endswith(
        "quarantine is not built — the payload is unaffected")
    assert diag_readout.all_rows(_folded(_row()))[-1] == rows[0]
    assert "contradictions" in diag_readout.conflict_rows(
        _folded(_row(), _row()))[0]


def test_the_status_and_the_report_carry_the_count():
    assert diag_readout.status(_folded())["contradictions"] == 0
    status = diag_readout.status(_folded(_row()))
    assert status["contradictions"] == 1
    assert status["rows"][-1] == diag_readout.conflict_rows(
        _folded(_row()))[0]
    report = diag_report.build_report(_folded(_row()))
    assert report["contradictions"] == 1


def test_the_page_pane_paints_the_reserved_deep_red():
    """DIAG-DESIGN §8: the deep-red path ships with its producer, in the
    same change and never before.  This is that change."""
    quiet = panes.render_pane(_folded(), "page", 0)
    loud = panes.render_pane(_folded(_row()), "page", 0)
    assert quiet is not None and loud is not None and quiet != loud
    from PIL import Image
    import io

    pixels = np.asarray(Image.open(io.BytesIO(loud)).convert("RGB"))
    matches = np.all(pixels == np.asarray(panes.CONTRADICTION, np.uint8),
                     axis=-1)
    assert matches.any()
    assert not np.any(np.all(
        np.asarray(Image.open(io.BytesIO(quiet)).convert("RGB"))
        == np.asarray(panes.CONTRADICTION, np.uint8), axis=-1))


def test_the_events_file_round_trips_a_contradiction(tmp_path):
    path = tmp_path / "events.jsonl"
    diag_report.write_events_jsonl(path, (_row(),))
    import json

    payload = json.loads(path.read_text())
    assert payload["type"] == "Contradiction"
    assert payload["window_id"][3] == list(EAST)
    assert payload["standing_tile_yx"] == [2, 2]
    assert payload["delta_cells_yx"] == [2.0, 0.0]


# --- on a real decode's own geometry -------------------------------------

def _overlapping_placed_pairs(store: object) -> tuple[tuple[tuple, tuple],
                                                      ...]:
    pairs = []
    for wid in store.placements():
        for other in contradiction.neighbour_windows(store, wid):
            if (store.placement(other) is not None
                    and contradiction.overlap_cells(wid[3], other[3])):
                pairs.append((wid, other))
    return tuple(pairs)


def _pair_delta_cells(store: object, wid: tuple, other: tuple) -> float:
    frame = store.frame(wid[:3])
    overlap = contradiction.overlap_cells(wid[3], other[3])
    native_y, native_x = contradiction.probe_native_yx(frame, overlap)
    deltas = []
    for placement in (store.placement(wid), store.placement(other)):
        inverse = geometry.invert_affine(tuple(placement.native_affine))
        deltas.append(contradiction.page_cell_at(inverse, native_y,
                                                 native_x))
    return max(abs(deltas[0][0] - deltas[1][0]),
               abs(deltas[0][1] - deltas[1][1]))


def test_a_real_decodes_own_poses_never_contradict_each_other(
        decode_k_local_patch_w8):
    """The false-alarm margin, measured rather than assumed.

    Every overlapping pair of placements a real sim decode committed,
    re-asked at the shared paper point.  Worst disagreement measured
    2026-09-04 on this (deliberately smeared and noisy) capture: 0.41
    cells over 100+ pairs — which is why the bar is a WHOLE cell and not
    the half a rounding rule would have given it.  Since 2026-09-20 the
    store is the eight-worker decode's (the one that keeps its engine);
    same capture, same placements law.
    """
    store = decode_k_local_patch_w8.engine
    pairs = _overlapping_placed_pairs(store)
    assert len(pairs) > 10
    worst = max(_pair_delta_cells(store, wid, other) for wid, other in pairs)
    assert worst < 0.5 * contradiction.DISAGREEMENT_CELLS, worst
    for wid in store.placements():
        assert contradiction.find(store, store.placement(wid)) == ()


def test_a_displaced_pose_over_a_real_decodes_paper_fires_the_alarm(
        decode_k_local_patch_w8):
    """Existence on real geometry, honestly labelled.

    The mis-addressed placement is INJECTED, not produced: the receiver
    admits no such pose on this material (the test above), and a page
    crop pasted to fabricate one cannot both pass the pose gate at the
    wrong address and leave its overlapping neighbour enough agreement
    to place — so this is the closest honest existence proof the sim
    lane holds.  Everything else here is real: the standing pose, its
    window, its region frame and the paper point they share.
    """
    store = decode_k_local_patch_w8.engine
    wid, other = _overlapping_placed_pairs(store)[0]
    standing = store.placement(other)
    displaced = dataclasses.replace(
        store.placement(wid), route=place.ROUTE_WORD,
        native_affine=geometry.shift_affine(
            tuple(store.placement(wid).native_affine), 2.0, 0.0))
    found = contradiction.find(store, displaced)
    named = [row for row in found if row.standing_window_id == other]
    assert len(named) == 1
    assert named[0].window_id == wid
    assert named[0].standing_page == standing.page
    # 2 cells of displacement plus the neighbour's own sub-cell
    # disagreement, which rides along and is bounded by the test above
    assert abs(named[0].delta_cells_yx[0]) == pytest.approx(2.0, abs=0.5)
    assert "CONTRADICTION" in contradiction.warning_line(named[0])


# --- the null, on the two sim decodes ------------------------------------

@pytest.mark.parametrize("fixture", ["decode_k_w1", "decode_color_w8"])
def test_neither_sim_decode_contradicts_itself(request, fixture):
    """The null the ruling is built on: the mechanism has never fired on
    healthy material (v1 ~1,780 known-position reads, holo2 21k evidence
    records, both silent), and holo3's own sims are the same story.
    """
    _h3_support.skip_unless_slow_lane(f"the {fixture} sim decode")
    record = request.getfixturevalue(fixture)
    assert [event for event in record.events
            if isinstance(event, data.Contradiction)] == []
    assert "CONTRADICTION" not in record.stderr
    assert record.report["contradictions"] == 0
    assert not any(row.startswith(diag_readout.CONFLICT_ROW_PREFIX)
                   for row in record.report["rows"])
