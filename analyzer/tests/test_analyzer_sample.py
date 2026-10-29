"""W1b — lanes, ownership, crops and reads (DESIGN §4.2/§4.3/§4.4).

The SYNTHETIC half builds a page-cell checkerboard at a known affine and
asks the reader to hand it back: if the +0.5, the level pitch, the crop
origin or the dots->cells conversion is wrong, the checkerboard comes
back smeared or shifted and the test says which.  The RUN-DIR half asks
the sheet-I run the four questions the wave owes: a lane for every
covered tile, the level-pitch identity, ownership frozen, and ink darker
than paper at the committed pose.
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver.data import Placement
from holo.receiver.lib import geometry as lib_geometry

from holo.receiver.plugins import color_region_anchor as anchor

from analyzer import frame, sample
from analyzer.inputs import finest_covering, page_tile_coverage
from analyzer.types import Lane, TileFootprint

from ._analyzer_fixtures import needs_sim, sim_run

# --- the synthetic page ---------------------------------------------------
PITCH_PX = 8.0
CELL_DOTS = 2
ORIGIN_Y, ORIGIN_X = 10.0, 12.0
WINDOW_CELLS = 96
RASTER = 900


def _pattern(cy: np.ndarray, cx: np.ndarray) -> np.ndarray:
    """(N, 3) of 0 (ink) / 1 (paper), one distinct pattern per channel."""
    return np.stack((((cy + cx) % 2 != 0),
                     (cy % 2 != 0),
                     (cx % 3 != 0)), axis=1).astype(np.uint8)


def _raster() -> tuple[np.ndarray, ...]:
    planes = [np.full((RASTER, RASTER), 255, np.uint8) for _ in range(3)]
    cy, cx = np.meshgrid(np.arange(WINDOW_CELLS), np.arange(WINDOW_CELLS),
                         indexing="ij")
    values = _pattern(cy.ravel(), cx.ravel()).reshape(
        WINDOW_CELLS, WINDOW_CELLS, 3)
    for iy in range(WINDOW_CELLS):
        y0 = int(ORIGIN_Y + PITCH_PX * iy)
        for ix in range(WINDOW_CELLS):
            x0 = int(ORIGIN_X + PITCH_PX * ix)
            for channel in range(3):
                planes[channel][y0:y0 + 8, x0:x0 + 8] = (
                    255 if values[iy, ix, channel] else 0)
    return tuple(planes)


def _placement(quality: float = 0.10, region_index: int = 0,
               origin: tuple[int, int] = (0, 0),
               extent: tuple[int, int, int, int] = (0, 0, WINDOW_CELLS,
                                                    WINDOW_CELLS),
               frame_level: Fraction = Fraction(1)) -> Placement:
    height, width = extent[2] - extent[0], extent[3] - extent[1]
    cy, cx = np.meshgrid(np.arange(height), np.arange(width),
                         indexing="ij")
    local = np.stack((cy.ravel(), cx.ravel()), axis=1).astype(np.int64)
    return Placement(
        window_id=("cap0", 0, region_index, extent), capture_id="cap0",
        level_index=0, region_index=region_index, patch_ordinal=0, page=0,
        rot_k=0, page_origin_yx=origin,
        native_affine=lib_geometry.compose_to_native(
            (PITCH_PX, 0.0, ORIGIN_Y, 0.0, PITCH_PX, ORIGIN_X), frame_level),
        pitch_px=float(frame_level) * PITCH_PX, route="place",
        local_cells_yx=local,
        quality=quality)


def _lane(*placements: Placement, frame_level: Fraction = Fraction(1),
          ) -> Lane:
    return Lane(capture_id="cap0", ordinal=0, level_index=0, dpi=1200.0,
                ppc=Fraction(8), frame=frame_level,
                pitch_px_native=float(frame_level) * PITCH_PX,
                pitch_px_level=PITCH_PX,
                rasters=_raster(), placements=tuple(placements))


def _footprint(halo: int = 8) -> TileFootprint:
    cells_y = cells_x = 128
    ys = np.arange(0, 64 + halo, dtype=np.int64)
    xs = np.arange(0, 64 + halo, dtype=np.int64)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    cells = np.stack((gy.ravel(), gx.ravel()), axis=1)
    in_tile = (cells[:, 0] < 64) & (cells[:, 1] < 64)
    return TileFootprint(page=0, ty=0, tx=0, halo_cells=halo,
                         page_cells_yx=cells, in_tile=in_tile,
                         cargo=np.ones(cells.shape[0], np.bool_),
                         page_shape_cells_yx=(cells_y, cells_x))


# ------------------------------------------------------------- synthetic

@pytest.mark.parametrize("frame_level", [Fraction(1), Fraction(2),
                                         Fraction(3, 2)])
def test_points_and_level_pitch_follow_the_placement(frame_level):
    """A placement posed in NATIVE pixels on a lane `frame_level` times
    coarser reads the same level points and the same level pitch."""
    lane = _lane(_placement(frame_level=frame_level),
                 frame_level=frame_level)
    fp = _footprint()
    lfp = sample.lane_footprint(lane, fp)
    assert lfp is not None
    assert lfp.observed.all()
    assert (lfp.owner_index == 0).all()
    cells = fp.page_cells_yx
    expect_y = PITCH_PX * (cells[:, 0] + 0.5) + ORIGIN_Y
    expect_x = PITCH_PX * (cells[:, 1] + 0.5) + ORIGIN_X
    assert np.allclose(lfp.points_yx[:, 0], expect_y)
    assert np.allclose(lfp.points_yx[:, 1], expect_x)
    assert sample.placement_pitch_px_level(
        lane, lane.placements[0]) == PITCH_PX
    assert sample.lane_level_pitches(lane, lfp) == {0: PITCH_PX}


def test_read_rgb_recovers_the_checkerboard_per_channel():
    lane = _lane(_placement())
    fp = _footprint()
    lfp = sample.lane_footprint(lane, fp)
    crops = sample.open_crops(lane, lfp, bound_dots=CELL_DOTS,
                              cell_dots=CELL_DOTS)
    read = sample.read_rgb(crops, lfp)
    assert read.refusal is None
    expect = _pattern(fp.page_cells_yx[:, 0], fp.page_cells_yx[:, 1])
    assert np.allclose(read.values_rgb, expect.astype(np.float64),
                       atol=1e-6)
    assert crops.divisor == 255.0
    assert crops.pitch_px_level == PITCH_PX


def test_an_offset_in_dots_moves_the_read_by_the_expected_cells():
    lane = _lane(_placement())
    fp = _footprint()
    lfp = sample.lane_footprint(lane, fp)
    # a whole cell of x offset = cell_dots dots: cell (cy, cx) must read
    # what cell (cy, cx + 1) reads.
    crops = sample.open_crops(lane, lfp, bound_dots=2 * CELL_DOTS,
                              cell_dots=CELL_DOTS)
    read = sample.read_rgb(crops, lfp, offset_dots_xy=(CELL_DOTS, 0.0))
    assert read.refusal is None
    expect = _pattern(fp.page_cells_yx[:, 0], fp.page_cells_yx[:, 1] + 1)
    assert np.allclose(read.values_rgb, expect.astype(np.float64),
                       atol=1e-6)
    # and one cell of y offset likewise
    read_y = sample.read_rgb(crops, lfp, offset_dots_xy=(0.0, CELL_DOTS))
    expect_y = _pattern(fp.page_cells_yx[:, 0] + 1, fp.page_cells_yx[:, 1])
    assert np.allclose(read_y.values_rgb, expect_y.astype(np.float64),
                       atol=1e-6)


def test_a_read_outside_the_crop_is_refused_not_filled():
    lane = _lane(_placement())
    fp = _footprint()
    lfp = sample.lane_footprint(lane, fp)
    crops = sample.open_crops(lane, lfp, bound_dots=CELL_DOTS,
                              cell_dots=CELL_DOTS)
    read = sample.read_rgb(crops, lfp, offset_dots_xy=(40.0 * CELL_DOTS,
                                                       0.0))
    assert read.refusal is not None
    assert read.refusal.startswith("outside_crop:")
    assert np.isnan(read.values_rgb).all()


def test_read_headroom_px_says_how_far_the_read_sat_from_the_refusal():
    """The other half of the refusal above (F3, review 2026-09-13).

    `outside_crop` is a verdict; this is the distance behind it, so a
    pass that never refused can say whether it had margin or was one
    pixel short of the loud answer.  A read pushed toward the edge has
    less of it, and a refused read has none to report.
    """
    lane = _lane(_placement())
    fp = _footprint()
    lfp = sample.lane_footprint(lane, fp)
    crops = sample.open_crops(lane, lfp, bound_dots=CELL_DOTS,
                              cell_dots=CELL_DOTS)

    def margin(points):
        local = np.asarray(points, np.float64)[lfp.observed] - np.asarray(
            (crops.y0, crops.x0), np.float64)
        height, width = crops.shape_yx
        return min(local[:, 0].min(), local[:, 1].min(),
                   float(height - 1) - local[:, 0].max(),
                   float(width - 1) - local[:, 1].max())

    read = sample.read_rgb(crops, lfp)
    want = margin(read.points_yx)
    assert sample.read_headroom_px(crops, lfp, read) == pytest.approx(want)

    nearer = sample.read_rgb(crops, lfp, offset_dots_xy=(-1.0, 0.0))
    assert nearer.refusal is None
    closer = sample.read_headroom_px(crops, lfp, nearer)
    assert closer == pytest.approx(margin(nearer.points_yx))
    assert closer < want

    refused = sample.read_rgb(crops, lfp, offset_dots_xy=(40.0 * CELL_DOTS,
                                                          0.0))
    assert refused.refusal is not None
    assert sample.read_headroom_px(crops, lfp, refused) is None


def test_affine_override_replaces_the_pose_for_the_read():
    lane = _lane(_placement())
    fp = _footprint()
    lfp = sample.lane_footprint(lane, fp)
    crops = sample.open_crops(lane, lfp, bound_dots=2 * CELL_DOTS,
                              cell_dots=CELL_DOTS)
    shifted = (PITCH_PX, 0.0, ORIGIN_Y, 0.0, PITCH_PX,
               ORIGIN_X + PITCH_PX)
    read = sample.read_rgb(crops, lfp, affine_override=shifted)
    assert read.refusal is None
    assert read.affine_terms == shifted
    expect = _pattern(fp.page_cells_yx[:, 0], fp.page_cells_yx[:, 1] + 1)
    assert np.allclose(read.values_rgb, expect.astype(np.float64),
                       atol=1e-6)
    # a mapping form addresses one owner
    read_map = sample.read_rgb(crops, lfp, affine_override={0: shifted})
    assert np.allclose(read_map.values_rgb, read.values_rgb, atol=0)


def test_ownership_is_frozen_by_quality_then_extent_and_is_repeatable():
    better = _placement(quality=0.05, region_index=1,
                        extent=(0, 0, 40, 40))
    worse = _placement(quality=0.50, region_index=0)
    lane = _lane(worse, better)          # deliberately the wrong order
    fp = _footprint()
    first = sample.lane_footprint(lane, fp)
    second = sample.lane_footprint(lane, fp)
    assert np.array_equal(first.owner_index, second.owner_index)
    assert np.array_equal(first.observed, second.observed)
    cells = fp.page_cells_yx
    inside_better = (cells[:, 0] < 40) & (cells[:, 1] < 40)
    # lower quality (a held-out log loss) WINS
    assert (first.owner_index[inside_better] == 1).all()
    assert (first.owner_index[~inside_better] == 0).all()
    reused = sample.lane_footprint(lane, fp, reference_arm_owner=first)
    assert np.array_equal(reused.owner_index, first.owner_index)
    assert np.array_equal(reused.points_yx, first.points_yx)


def test_a_lane_that_does_not_touch_the_footprint_returns_none():
    lane = _lane(_placement(origin=(1000, 1000)))
    assert sample.lane_footprint(lane, _footprint()) is None


# ------------------------------------------------------------ crop memo

def _crop_counter(monkeypatch) -> list[int]:
    """Count the cuts that really happen: one `native_crop` per crop."""
    calls = [0]
    real = anchor.native_crop

    def counting(*args, **kwargs):
        calls[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(anchor, "native_crop", counting)
    return calls


#: The crop memo's whole key, at the values `open_crops` defaults to.
_BASE_CUT = dict(bound_dots=2.5, cell_dots=CELL_DOTS, keep_raw=False,
                 aperture_cells=anchor.APERTURE_CELLS, aperture_kind="box")


def test_the_crop_memo_hands_back_the_same_object_and_cuts_once(monkeypatch):
    lane = _lane(_placement())
    lfp = sample.lane_footprint(lane, _footprint())
    calls = _crop_counter(monkeypatch)
    memo: dict = {}
    first = sample.open_crops(lane, lfp, memo=memo, **_BASE_CUT)
    second = sample.open_crops(lane, lfp, memo=memo, **_BASE_CUT)
    assert second is first                     # the OBJECT, not a copy
    assert calls[0] == 1 and len(memo) == 1
    # and without a memo the second call cuts again, as it always did
    third = sample.open_crops(lane, lfp, **_BASE_CUT)
    assert third is not first
    assert np.array_equal(third.filtered_rgb, first.filtered_rgb)
    assert calls[0] == 2


@pytest.mark.parametrize("changed", [
    {"bound_dots": 3.5}, {"cell_dots": CELL_DOTS + 1}, {"keep_raw": True},
    {"aperture_cells": 0.9}, {"aperture_kind": "gaussian"}])
def test_the_crop_memo_key_separates_every_argument_the_cut_reads(
        monkeypatch, changed):
    """Each of the five cut arguments moves the cut, so each is in the key.

    A key that dropped one would hand an arm the wrong pixels — the whole
    reason the key spells out what `open_crops` reads rather than naming
    the (lane, footprint) alone.
    """
    lane = _lane(_placement())
    lfp = sample.lane_footprint(lane, _footprint())
    calls = _crop_counter(monkeypatch)
    memo: dict = {}
    first = sample.open_crops(lane, lfp, memo=memo, **_BASE_CUT)
    other = sample.open_crops(lane, lfp, memo=memo,
                              **{**_BASE_CUT, **changed})
    assert other is not first
    assert calls[0] == 2 and len(memo) == 2


def test_the_crop_memo_key_separates_the_footprint_and_the_lane(monkeypatch):
    lane = _lane(_placement())
    other_lane = dc_replace(lane, capture_id="cap1")
    lfp = sample.lane_footprint(lane, _footprint(halo=8))
    wider = sample.lane_footprint(lane, _footprint(halo=12))
    theirs = sample.lane_footprint(other_lane, _footprint(halo=8))
    calls = _crop_counter(monkeypatch)
    memo: dict = {}
    mine = sample.open_crops(lane, lfp, memo=memo, **_BASE_CUT)
    assert sample.open_crops(lane, wider, memo=memo, **_BASE_CUT) is not mine
    assert sample.open_crops(other_lane, theirs, memo=memo,
                             **_BASE_CUT) is not mine
    assert calls[0] == 3 and len(memo) == 3


def test_the_lane_memo_holds_one_lane_and_drops_the_one_before(monkeypatch):
    """The bound the saving is free under: two crops, not two per lane.

    The driver's memo hands out ONE lane's dict; ask it for another lane
    and the first lane's crops go.  Without that a ten-capture key would
    hold twenty crops at once instead of two.
    """
    lane = _lane(_placement())
    other = dc_replace(lane, capture_id="cap1")
    lfp = sample.lane_footprint(lane, _footprint())
    theirs = sample.lane_footprint(other, _footprint())
    calls = _crop_counter(monkeypatch)
    memo = sample.LaneCropMemo()
    mine = sample.open_crops(lane, lfp, memo=memo.for_lane(lane.lane_id),
                             **_BASE_CUT)
    assert sample.open_crops(lane, lfp, memo=memo.for_lane(lane.lane_id),
                             **_BASE_CUT) is mine
    assert calls[0] == 1
    held = memo.for_lane(other.lane_id)
    assert held == {}                          # the first lane's crops went
    sample.open_crops(other, theirs, memo=held, **_BASE_CUT)
    assert len(held) == 1 and calls[0] == 2
    # and coming back to the first lane cuts again rather than growing
    again = memo.for_lane(lane.lane_id)
    assert again == {}
    assert sample.open_crops(lane, lfp, memo=again,
                             **_BASE_CUT) is not mine
    assert calls[0] == 3


def test_a_memoised_crop_is_not_written_through_by_its_readers():
    """The reuse is safe only because nothing writes through a `Crops`.

    A read, a re-filter at another aperture and a patch extraction all
    run over the SAME object; if any of them wrote into `filtered_rgb`
    or `raw_rgb`, the next arm to take the memo's hit would read pixels
    the first arm changed.
    """
    from analyzer import patchgrid
    from analyzer.patchspec import PatchSpec

    lane = _lane(_placement())
    lfp = sample.lane_footprint(lane, _footprint())
    memo: dict = {}
    crops = sample.open_crops(lane, lfp, memo=memo,
                              **{**_BASE_CUT, "keep_raw": True})
    before = (crops.filtered_rgb.tobytes(), crops.raw_rgb.tobytes())
    read = sample.read_rgb(crops, lfp)
    sample.refiltered_values(crops, lfp, read, aperture_cells=1.1)
    patchgrid.extract(crops, read.points_yx, read.linear_by_owner,
                      lfp.owner_index, np.arange(16, dtype=np.int64),
                      patchgrid.grid_cells(PatchSpec(), PITCH_PX),
                      (0, 1, 2))
    assert sample.open_crops(lane, lfp, memo=memo,
                             **{**_BASE_CUT, "keep_raw": True}) is crops
    assert crops.filtered_rgb.tobytes() == before[0]
    assert crops.raw_rgb.tobytes() == before[1]


# ------------------------------------------------------------- run dir
# TIER S (2026-10-09): the receiver's displaced 10x10 colour sim decoded
# into a run dir — rasters the receiver wrote, read back by the analyzer.

def _interior_tile(inputs) -> tuple[int, int, int] | None:
    """The first tile off the page edge with every stream certified."""
    page = inputs.live_pages[0]
    tiles_y, tiles_x = inputs.tiles_yx
    streams = tuple(fact.stream_id for fact in inputs.row.streams)
    return next(((page, ty, tx) for ty in range(1, tiles_y - 1)
                 for tx in range(1, tiles_x - 1)
                 if all((page, ty, tx, s) in inputs.certificates
                        for s in streams)), None)


@needs_sim
def test_the_crop_memo_moves_no_arm_and_cuts_one_crop_per_cut(monkeypatch):
    """The memo on real pixels: same rows, one cut per KIND of cut.

    Six arms of the battery over one (key, lane) of a decoded run —
    four box arms and the two patch arms, which are the two cuts the
    whole battery resolves to (bound 2.5 / keep_raw off, and bound 4.0 /
    keep_raw on).  Without the memo each arm cuts its own crop; with it
    the six arms cut two, and every arm's LLR vector, observation mask
    and blind row comes back identical field for field.

    `ctx_mode="none"` and a footprint-only mix scope are here so the
    count is the ARMS' own: production's context labels and the lane mix
    open crops of their own through process-lifetime memos, which would
    make the first battery of a process cost more than the second
    whatever this memo does.
    """
    from analyzer import arms as arms_mod

    inputs = sim_run()
    target = _interior_tile(inputs)
    assert target is not None
    key = (*target, "C")
    lane = sample.lanes_for_tile(inputs, *target)[0]
    battery = ("raw+committed", "project+committed", "subtract+committed",
               "subtract+offset", "patch+committed", "patch+offset")
    knobs = {"seed": 20260913, "ctx_mode": "none",
             "mix_scope_ladder": ("footprint",)}
    calls = _crop_counter(monkeypatch)

    def battery_rows(memo):
        calls[0] = 0
        rows = {arm: arms_mod.evidence_for(
            inputs, inputs.certificates, key, lane, arm, halo_cells=16,
            knobs=knobs, crop_memo=memo) for arm in battery}
        return rows, calls[0]

    alone, cuts_alone = battery_rows(None)
    memo: dict = {}
    shared, cuts_shared = battery_rows(memo)
    print(f"\n{key} {lane.lane_id}: {len(battery)} arms cut "
          f"{cuts_alone} crops alone, {cuts_shared} with the memo")
    assert cuts_alone == len(battery)
    assert cuts_shared == 2 and len(memo) == 2
    # the two cuts, named: (bound_dots, keep_raw) at positions 6 and 8 of
    # `sample.crop_memo_key` — the box arms' and the patch arms' wider
    # one.  A c3 row: one cell dot wider than sheet I's c2 (2.5 and 4.0).
    assert {(entry[6], entry[8]) for entry in memo} == {(3.5, False),
                                                        (5.75, True)}
    for arm in battery:
        one, two = alone[arm], shared[arm]
        assert one.blind.get("refusal") is None, one.blind["refusal"]
        assert np.array_equal(one.llr_sequential, two.llr_sequential), arm
        assert np.array_equal(one.observed, two.observed), arm
        assert _same_blind(dict(one.blind), dict(two.blind)), arm


def _same_blind(one: dict, two: dict) -> bool:
    """Blind rows equal field for field, arrays compared as arrays."""
    if one.keys() != two.keys():
        return False
    return all(_same_value(one[name], two[name]) for name in one)


def _same_value(one, two) -> bool:
    if isinstance(one, np.ndarray) or isinstance(two, np.ndarray):
        return np.array_equal(np.asarray(one), np.asarray(two))
    if isinstance(one, dict) and isinstance(two, dict):
        return _same_blind(one, two)
    if isinstance(one, (list, tuple)) and isinstance(two, (list, tuple)):
        return (len(one) == len(two)
                and all(_same_value(a, b) for a, b in zip(one, two)))
    return bool(one == two)



@needs_sim
def test_every_covered_tile_has_a_lane_at_0_9():
    inputs = sim_run()
    tiles_y, tiles_x = inputs.tiles_yx
    page = inputs.live_pages[0]
    covered = page_tile_coverage(inputs, page) > 0
    empty = {"lanes_for_tile@0.9": 0, "lanes_for_tile@1.0": 0,
             "finest_covering@0.9": 0, "finest_covering@1.0": 0}
    fell_back = 0
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            if not covered[ty, tx]:
                continue
            for fraction in (0.9, 1.0):
                if not finest_covering(inputs, page, ty, tx,
                                       cover_fraction=fraction):
                    empty[f"finest_covering@{fraction}"] += 1
                if not sample.lanes_for_tile(inputs, page, ty, tx,
                                             cover_fraction=fraction):
                    empty[f"lanes_for_tile@{fraction}"] += 1
            if sample.fallback_captures(inputs, page, ty, tx):
                fell_back += 1
    print(f"\ncovered tiles ({int(covered.sum())}) with NO lane: {empty}; "
          f"tiles using the fallback at 0.9: {fell_back}")
    assert empty["lanes_for_tile@0.9"] == 0


@needs_sim
def test_ink_reads_darker_than_paper_at_the_committed_pose():
    """The sign convention on rasters the receiver wrote."""
    from holo.receiver.plugins import color_sites
    from holo.receiver.plugins.swim import translation_bound_dots

    inputs = sim_run()
    row = inputs.row
    cell_dots = color_sites.cell_dots_of(row)
    bound = translation_bound_dots(row)
    streams = tuple(fact.stream_id for fact in row.streams)
    target = _interior_tile(inputs)
    assert target is not None
    page, ty, tx = target
    fp = frame.tile_footprint(row, page, ty, tx, 16)
    lanes = sample.lanes_for_tile(inputs, page, ty, tx)
    assert lanes
    lane = max(lanes, key=lambda item: item.ppc)
    lfp = sample.lane_footprint(lane, fp)
    assert lfp is not None
    crops = sample.open_crops(lane, lfp, bound_dots=bound,
                              cell_dots=cell_dots)
    read = sample.read_rgb(crops, lfp)
    assert read.refusal is None, read.refusal

    for stream_id, plane in zip(streams, range(3)):
        kf = frame.known_frame(inputs, inputs.certificates, fp,
                               (page, ty, tx, stream_id),
                               metadata_known=False)
        known = kf.known[:, plane] & lfp.observed
        ink = known & (kf.bits[:, plane] == 1)
        paper = known & (kf.bits[:, plane] == 0)
        if int(ink.sum()) < 50 or int(paper.sum()) < 50:
            pytest.skip(f"{stream_id}: too few labels to compare")
        mean_ink = float(np.nanmean(read.values_rgb[ink, plane]))
        mean_paper = float(np.nanmean(read.values_rgb[paper, plane]))
        print(f"\n{stream_id} plane {plane}: ink {mean_ink:.4f} < "
              f"paper {mean_paper:.4f} "
              f"(n_ink={int(ink.sum())}, n_paper={int(paper.sum())})")
        assert mean_ink < mean_paper


# ------------------------------------------------- W8 B3: A7, the aperture

def test_default_aperture_is_byte_identical_and_a_gaussian_is_not_and_the_halo_grows_with_kind():
    """A7.  The default width and kind take production's own code path,
    so no arm's pixels move; a wider box and a gaussian are new apertures
    and the crop grows for BOTH, because the margin a filter needs is a
    function of its width and its tail (a gaussian truncates at 4 sigma,
    1.7 FWHM).  The margin is the point: a filtered value at a footprint
    cell must not depend on where the crop happened to stop.
    """
    lane = _lane(_placement())
    lfp = sample.lane_footprint(lane, _footprint())
    common = dict(bound_dots=2.5, cell_dots=CELL_DOTS)
    default = sample.open_crops(lane, lfp, **common)
    spelled = sample.open_crops(lane, lfp, aperture_cells=anchor.APERTURE_CELLS,
                                aperture_kind="box", **common)
    assert default.aperture_cells == anchor.APERTURE_CELLS
    assert default.aperture_kind == "box"
    assert np.array_equal(default.filtered_rgb, spelled.filtered_rgb)
    assert default.halo_px == spelled.halo_px

    wide = sample.open_crops(lane, lfp, aperture_cells=1.4, **common)
    blur = sample.open_crops(lane, lfp, aperture_kind="gaussian", **common)
    assert not np.array_equal(default.filtered_rgb[:64, :64],
                              blur.filtered_rgb[:64, :64])
    assert sample.aperture_halo_px(PITCH_PX, anchor.APERTURE_CELLS, "box") == \
        anchor.points_halo(PITCH_PX)
    assert wide.halo_px > default.halo_px
    assert blur.halo_px > default.halo_px           # the 4-sigma tail
    with pytest.raises(sample.SampleError):
        sample.open_crops(lane, lfp, aperture_kind="tophat", **common)

    # the crop's own margin is enough: reading the same cells out of a
    # crop opened with THREE dots more of slack gives the same values,
    # so `mode="nearest"` never clamped into the answer
    for kind, cells in (("box", 1.4), ("gaussian", anchor.APERTURE_CELLS)):
        tight = sample.open_crops(lane, lfp, bound_dots=2.5,
                                  cell_dots=CELL_DOTS, aperture_cells=cells,
                                  aperture_kind=kind)
        loose = sample.open_crops(lane, lfp, bound_dots=5.5,
                                  cell_dots=CELL_DOTS, aperture_cells=cells,
                                  aperture_kind=kind)
        assert loose.halo_px > tight.halo_px
        assert np.allclose(sample.read_rgb(tight, lfp).values_rgb,
                           sample.read_rgb(loose, lfp).values_rgb, atol=1e-6)


def test_a_gaussian_crop_that_is_not_given_its_tail_reads_differently(
        monkeypatch):
    """The control for the halo factor: shrink it and the boundary cells
    DO move, which is what the 1.7 is there to prevent.

    The page here is NOISE, not the checkerboard: with 8-pixel cell
    blocks a clamped tail replicates the very value the tail would have
    read and the control cannot fail for the right reason.
    """
    rng = np.random.default_rng(20260906)
    noise = tuple(rng.integers(0, 256, (RASTER, RASTER), dtype=np.uint8)
                  for _ in range(3))
    lane = dc_replace(_lane(_placement()), rasters=noise)
    lfp = sample.lane_footprint(lane, _footprint())
    common = dict(bound_dots=2.5, cell_dots=CELL_DOTS,
                  aperture_kind="gaussian", aperture_cells=1.4)
    honest = sample.read_rgb(sample.open_crops(lane, lfp, **common), lfp)
    monkeypatch.setattr(sample, "GAUSSIAN_HALO_FACTOR", 0.05)
    starved = sample.read_rgb(sample.open_crops(lane, lfp, **common), lfp)
    assert not np.allclose(honest.values_rgb, starved.values_rgb, atol=1e-6)
