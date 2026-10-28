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

from fractions import Fraction

import numpy as np
import pytest

from holo3.data import Placement

from analyzer import frame, sample
from analyzer.inputs import finest_covering, page_tile_coverage
from analyzer.types import Lane, TileFootprint

from ._analyzer_fixtures import i_inputs, needs_i_run

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
               ) -> Placement:
    height, width = extent[2] - extent[0], extent[3] - extent[1]
    cy, cx = np.meshgrid(np.arange(height), np.arange(width),
                         indexing="ij")
    local = np.stack((cy.ravel(), cx.ravel()), axis=1).astype(np.int64)
    return Placement(
        window_id=("cap0", 0, region_index, extent), capture_id="cap0",
        level_index=0, region_index=region_index, patch_ordinal=0, page=0,
        rot_k=0, page_origin_yx=origin,
        native_affine=(PITCH_PX, 0.0, ORIGIN_Y, 0.0, PITCH_PX, ORIGIN_X),
        pitch_px=PITCH_PX, route="place", local_cells_yx=local,
        quality=quality)


def _lane(*placements: Placement) -> Lane:
    return Lane(capture_id="cap0", ordinal=0, level_index=0, dpi=1200.0,
                ppc=Fraction(8), frame=Fraction(1),
                pitch_px_native=PITCH_PX, pitch_px_level=PITCH_PX,
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

def test_points_and_level_pitch_follow_the_placement():
    lane = _lane(_placement())
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


# ------------------------------------------------------------- run dir

@needs_i_run
def test_sheet_i_every_covered_tile_has_a_lane_at_0_9():
    inputs = i_inputs()
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


@needs_i_run
def test_sheet_i_level_pitch_is_the_placement_pitch_over_the_frame():
    inputs = i_inputs()
    for lane in inputs.lanes:
        for placement in lane.placements[:64]:
            assert sample.placement_pitch_px_level(lane, placement) == (
                float(placement.pitch_px) / float(lane.frame))
        pitches = [sample.placement_pitch_px_level(lane, placement)
                   for placement in lane.placements]
        spread = (max(pitches) - min(pitches)) / float(np.median(pitches))
        print(f"\n{lane.lane_id}: ppc={lane.ppc} frame={lane.frame} "
              f"pitch spread {spread:.4%}")


@needs_i_run
def test_sheet_i_ink_reads_darker_than_paper_at_the_committed_pose():
    from holo3.plugins import color_sites
    from holo3.plugins.swim import translation_bound_dots

    inputs = i_inputs()
    row = inputs.row
    cell_dots = color_sites.cell_dots_of(row)
    bound = translation_bound_dots(row)
    streams = tuple(fact.stream_id for fact in row.streams)
    page = inputs.live_pages[0]
    target = None
    for ty in range(10, 40):
        for tx in range(10, 30):
            if all((page, ty, tx, s) in inputs.certificates
                   for s in streams):
                target = (page, ty, tx)
                break
        if target:
            break
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


@needs_i_run
def test_sheet_i_ownership_is_identical_when_computed_twice():
    inputs = i_inputs()
    page = inputs.live_pages[0]
    fp = frame.tile_footprint(inputs.row, page, 20, 18, 16)
    for lane in sample.lanes_for_tile(inputs, page, 20, 18):
        first = sample.lane_footprint(lane, fp)
        second = sample.lane_footprint(lane, fp)
        if first is None:
            assert second is None
            continue
        assert np.array_equal(first.owner_index, second.owner_index)
        assert np.array_equal(first.observed, second.observed)
        assert np.array_equal(first.points_yx, second.points_yx,
                              equal_nan=True)
