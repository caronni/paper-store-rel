"""The PAGE field: the attribution law, the two rows, the cell.

One field per (page, plane) and nothing else — `docs/PAGE-FIELD-DESIGN.md`
is the design of record and its invariants I1-I13 are what this module
pins.  What the field IS, asked of behaviour rather than of internals,
is the W8 suite: `test_h3_field_lifecycle`, `_evidence`, `_gauge`,
`_estimator`, `_consumers`, which superseded this module's own
collector-internal tests and took `test_h3_plane_field_lib` and
`test_h3_field_tiers` with them.  The null the one primitive's quality
floor is cut from stays in `test_h3_field_null.py`; the end-to-end yield
case, a displaced plane costing certificates and the field buying them
back, was retired 2026-09-20 with the pair of decodes that cost more
wall than the whole slow lane's budget — ledger in the receiver's
`docs/WIDENED-MATRIX-RETIREMENT-2026-09-20.md`.

The collection is measured for real here: a synthetic window over the
format's own furniture, one plane displaced by a known PAGE-axis vector,
read back through `fields_collect.collect_job` at all four placement
rotations.  That is bar B1's receiver half and it is the regression the
frame has already suffered twice (design §1, "frame regression").
"""

from __future__ import annotations

import dataclasses
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from holo.receiver import data, engine, snapshot
from holo.receiver.descriptor import (KEY_FIELD_OBS, KEY_LANE_POSES,
                                     KEY_PLANE_FIELD)
from holo.receiver.format import identity
from holo.receiver.lib import geometry, plane_field
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import (color_region, color_region_anchor,
                                   field_tiers, fields, fields_collect,
                                   tiles)
from holo.receiver.tests import (_h3_facts, _h3_fixture_geometry,
                                 _h3_support)

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_the_engine_carries_both_rows_and_only_they_write_their_families`.

CAPTURE_ID = _h3_facts.CAPTURE_ID
OTHER_CAPTURE = "beadfeed" * 8
COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
ROW = identity.resolve_format_ref(COLOR_FORMAT_REF)
GEOMETRY = _h3_fixture_geometry.memoised_site_geometry(ROW)
PAGE = 0
CELL_DOTS = 3
PITCH_PX = 6.0
PX_PER_DOT = PITCH_PX / CELL_DOTS
BLUR_PX = 1.5
SPAN_CELLS = 2 * TILE_CELLS
WID = (CAPTURE_ID, 0, 0, (0, 0, SPAN_CELLS, SPAN_CELLS))
#: A second window over the same cells: two windows one certificate
#: apart both stand at pose generation 0, so only the id tells them
#: apart (`fields_collect.standing_tile`).
WID_B = (CAPTURE_ID, 0, 1, (0, 0, SPAN_CELLS, SPAN_CELLS))
INJECTED_DOTS_XY = (1.0, 0.0)
TILES_YX = ROW.tiles_yx


def _engine(format_ref: str = COLOR_FORMAT_REF) -> engine._Engine:
    request = data.DecodeRequest(
        scans=(Path("scan.tiff"),), dpis=(1200.0,), format_ref=format_ref,
        max_pages=1, workers=1, complete=False, no_close=False,
        diag_port=None,
        run_dir=Path(tempfile.mkdtemp(prefix="h3-fields-")))
    return engine._Engine(request, [])


def _cells(tiles_yx: tuple[int, int] = (6, 5),
           step: int = 8) -> np.ndarray:
    ys = np.arange(0, tiles_yx[0] * TILE_CELLS, step)
    xs = np.arange(0, tiles_yx[1] * TILE_CELLS, step)
    grid = np.stack(np.meshgrid(ys, xs, indexing="ij"), axis=-1)
    return grid.reshape(-1, 2).astype(np.int64)


def _field(**kwargs: object) -> data.PlaneField:
    return _h3_facts.plane_field(**kwargs)


# --------------------------------------------------------------------
# the collection: the frame, the gauge, the tiers
# --------------------------------------------------------------------

class _Raster:
    """A `PlaneRaster` stand-in: the job opens, the fixture holds."""

    def __init__(self, image: np.ndarray) -> None:
        self._image = image

    def open(self) -> np.ndarray:
        return self._image


def _window(rot_k: int = 0) -> color_region.RegionWindow:
    local = _h3_facts.tile_cells(SPAN_CELLS)
    placement = _h3_fixture_geometry.window_placement(
        WID, _h3_fixture_geometry.page_native_affine(PITCH_PX, 0.0), local,
        page=PAGE, rot_k=rot_k)
    return _h3_fixture_geometry.window_pose(ROW, placement)


_RENDERS: dict[tuple, tuple] = {}


def _page_to_pixels() -> np.ndarray:
    """The page cell -> pixel 2x2 of the fixture's own page map.

    Independent of the window pose the collector inverts: the injection
    is placed through the PAGE map and read back through the WINDOW's,
    so a rotation that cancelled itself in both would not pass.
    """
    terms = np.asarray(geometry.compose_from_native(
        _h3_fixture_geometry.page_native_affine(PITCH_PX, 0.0),
        Fraction(1)), np.float64).reshape(2, 3)
    return terms[:, :2]


def _render(window: color_region.RegionWindow, rot_k: int,
            page_delta_dots_xy: tuple[float, float],
            certificates: dict | None = None) -> tuple:
    """The window's own printed truth, one plane displaced on the PAGE.

    Painted at the window pose's OWN sample points, so a rotated
    placement paints the page it is standing on rather than a rotated
    picture of some other one.  The displacement is a page-axis vector
    carried into pixels through the page map, which is the geometry the
    printer acts in.

    Ink reads DARK, and the page is blurred by a dot: a hard-edged
    raster has a FLAT optimum a cell wide, and a channel with no MTF is
    not a channel (`test_h3_plugins_swim`'s own reasoning, and the same
    0.13 s stimulus).
    """
    key = (rot_k, tuple(float(v) for v in page_delta_dots_xy),
           tuple(sorted(certificates or ())))
    if key in _RENDERS:
        return _RENDERS[key]
    rows = color_region.build_window_rows(ROW, GEOMETRY, window,
                                          certificates or {}, {})
    known = np.asarray(rows.known_component_mask, bool)
    bits = np.asarray(rows.known_component_bits, np.uint8).copy()
    cells = np.asarray(rows.page_cells_yx, np.int64)
    pattern = ((cells[:, 0] * 131 + cells[:, 1] * 17) % 8).astype(np.uint8)
    for plane in range(3):
        blank = ~known[:, plane]
        bits[blank, plane] = (pattern[blank] >> plane) & 1
    points = np.asarray(window.scan_points_yx, np.float64)
    pixel_delta = _page_to_pixels() @ (
        np.asarray(page_delta_dots_xy, np.float64)[::-1] / CELL_DOTS)
    size = int(SPAN_CELLS * PITCH_PX)
    half = PITCH_PX / 2.0
    planes = []
    for plane in range(3):
        image = np.ones((size, size), np.float32)
        moved = points + (pixel_delta if plane == 2 else 0.0)
        for (py, px), value in zip(moved, bits[:, plane]):
            y0 = int(round(py - half))
            x0 = int(round(px - half))
            image[max(0, y0):y0 + int(PITCH_PX),
                  max(0, x0):x0 + int(PITCH_PX)] = 1.0 - float(value)
        planes.append(ndimage.gaussian_filter(image, BLUR_PX))
    _RENDERS[key] = tuple(_Raster(plane) for plane in planes)
    return _RENDERS[key]


def _lane(window: color_region.RegionWindow, planes: tuple,
          ppc: float = 4.0, level_index: int = 0, generation: int = 1,
          wid: tuple = WID) -> fields_collect.LaneWindows:
    return fields_collect.LaneWindows(
        level_index=level_index, ppc=ppc, windows=(window,),
        window_ids=(wid,), pose_generation=(generation,), planes=planes)


def _collect(rot_k: int = 0,
             page_delta_dots_xy: tuple[float, float] = INJECTED_DOTS_XY,
             certificates: dict | None = None,
             standing: data.FieldObservations | None = None,
             lanes: tuple[fields_collect.LaneWindows, ...] | None = None,
             revision: int = 4) -> data.FieldObservations:
    window = _window(rot_k)
    if lanes is None:
        lanes = (_lane(window,
                       _render(window, rot_k, page_delta_dots_xy,
                               certificates)),)
    result = fields_collect.collect_job(
        ROW, GEOMETRY, CAPTURE_ID, PAGE, lanes,
        {} if certificates is None else certificates, standing, revision)
    fact, = result.facts
    return fact


def _table(fact: data.FieldObservations) -> set:
    """One collection's rows, order-free.  A row is RAW (design §2.5):
    the memo carries a (tile, plane) at a time and nothing is ever
    subtracted from what was measured there."""
    return {(int(code), int(plane), int(source), round(float(dx), 9),
             round(float(dy), 9))
            for code, plane, source, (dx, dy) in zip(
                fact.tile_code, fact.plane, fact.source,
                np.asarray(fact.delta_dots_xy))}


def _by_plane(fact: data.FieldObservations, plane: int,
              source: int = plane_field.SOURCE_ANCHOR) -> np.ndarray:
    rows = (np.asarray(fact.plane) == plane) & (
        np.asarray(fact.source) == source)
    return np.asarray(fact.delta_dots_xy)[rows]


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_one_page_displacement_reads_the_same_at_every_rotation(rot_k):
    """I2 and bar B1's receiver half.

    The printer displaced the Y plane by a vector on the PAGE.  A window
    standing at rot 1 measures that vector along its own cell axes,
    where it wears the rotation; the collector maps it back through the
    pose's own rotation, so what leaves the window is the page vector
    itself and a confetti page mixing all four rotations pools into one
    field.  Un-rotated deltas measured 2.6x WORSE than none on real
    scraps (design §1) — this is the pin that stops that returning.
    """
    fact = _collect(rot_k)
    measured = _by_plane(fact, 2)
    assert measured.shape[0] >= 3, measured
    assert np.median(measured[:, 0]) == pytest.approx(
        INJECTED_DOTS_XY[0], abs=0.3), measured
    assert abs(float(np.median(measured[:, 1]))) < 0.3, measured


def test_the_planes_that_were_not_moved_read_zero():
    """I5: no cross-plane coupling.  C and M were printed in register and
    the gauge is theirs, so they straddle zero while Y keeps its own."""
    fact = _collect()
    for plane in (0, 1):
        measured = _by_plane(fact, plane)
        assert measured.size
        assert abs(float(np.median(measured[:, 0]))) < 0.3, (plane,
                                                             measured)


def test_a_tile_left_with_no_rows_is_fresh_again_at_the_next_collection():
    """What a refusal costs, this rule's included (W7 review, minor 5).

    Nothing in the fact records that a row was REFUSED — a refused
    (tile, plane) and a never-measured one look the same to
    `standing_row`, which finds no rows and returns None, so it counts
    as fresh, its window opens a crop and the dearest per-window work
    runs again.  That is the standing shape of every refusal in this
    collection; making a refusal durable is a fact-schema change and is
    owed, not ruled (design §2.3).
    """
    standing = _h3_facts.field_observations(
        CAPTURE_ID, PAGE, generation=0, codes=(0, 1), wid=WID)
    assert fields_collect.standing_row(
        standing, 0, 2, WID, 0, plane_field.SOURCE_ANCHOR) is not None
    assert fields_collect.standing_row(
        standing, 7, 2, WID, 0, plane_field.SOURCE_ANCHOR) is None


def test_the_certified_tier_searches_its_own_radius_in_printed_cells():
    """RULED 2026-09-08 (W7): a whole-tile template is bounded by the
    CELL, not by a plane's ink.

    So it is the same radius on every plane, it scales with the row, and
    it is wider than the furniture tiers' everywhere: 2.5 dots at c2 and
    3.75 at c3 against the anchor tier's 1.5 / 1.5 / 2.5.  Here the Y
    plane is displaced three dots — past the anchor tier's own wall at
    2.24 — and only the certified tile comes back with it.
    """
    assert field_tiers.certified_radius_dots(2) == 2.5
    assert field_tiers.certified_radius_dots(CELL_DOTS) == 3.75
    for plane in range(3):
        assert (field_tiers.certified_radius_dots(CELL_DOTS)
                > field_tiers.ANCHOR_RADIUS_DOTS[plane])
    displaced = (3.0, 0.0)
    assert field_tiers.saturated(np.asarray(displaced),
                                 field_tiers.ANCHOR_RADIUS_DOTS[2])
    fact = _collect(page_delta_dots_xy=displaced,
                    certificates=_tile_certificates(0, 0))
    codes = np.asarray(fact.tile_code)
    planes = np.asarray(fact.plane)
    sources = np.asarray(fact.source)
    yellow = (planes == 2) & (sources == plane_field.SOURCE_CERTIFIED)
    assert set(codes[yellow].tolist()) == {0}
    assert float(np.asarray(fact.delta_dots_xy)[yellow][0][0]) == \
        pytest.approx(displaced[0], abs=0.3)
    assert not np.any((planes == 2)
                      & (sources == plane_field.SOURCE_ANCHOR)), (
        "the anchor tier's wall refuses this displacement, as it should")


def test_the_crop_the_collection_opens_holds_that_radius():
    """The inequality nobody stated when the radius widened 1.67x.

    `window_crop` opens ONE crop per window and every tier probes inside
    it; the crop is `window_points`' own +-2-cell margin padded by
    `color_region_anchor.window_halo`, and neither knows this tier's
    radius.  A probe that fell outside would return `None` silently.
    The radius is in CELLS, so its pixel size is
    `CERTIFIED_RADIUS_CELLS * pitch_px` whatever the row: 1.25 pitch
    against the halo's 1.5 pitch + 3 px, and the sampler's 0.7-cell
    aperture fits in the two cells `window_points` adds on top.
    """
    aperture_px = color_region_anchor.APERTURE_CELLS
    assert field_tiers.CERTIFIED_RADIUS_CELLS + 0.5 * aperture_px < 2.0
    for pitch_px in (4.0, 6.0, 12.0, 24.0, 48.0):
        halo = float(color_region_anchor.window_halo(pitch_px))
        probe = field_tiers.CERTIFIED_RADIUS_CELLS * pitch_px
        assert probe < halo, (pitch_px, probe, halo)
        assert probe + 0.5 * aperture_px * pitch_px < halo + 2.0 * pitch_px


def _tile_certificates(ty: int, tx: int) -> dict:
    """Every stream of one tile certified.

    The bits are arbitrary; what matters is that the RASTER is painted
    from the same certified projection the collector correlates
    against, which is the physical situation — the certificate says what
    was printed there.
    """
    return {(PAGE, ty, tx, stream.stream_id): data.Certificate(
        page=PAGE, ty=ty, tx=tx, stream_id=stream.stream_id,
        user_bits=np.full(stream.user_bits, index % 2, np.uint8),
        source="tiles/scan")
        for index, stream in enumerate(ROW.streams)}


def test_a_second_level_of_one_capture_adds_no_observation():
    """I4 and bar B2's second half.

    Levels are the same photons; they never add weight.  The tile is
    measured at the FINEST level with a placement over it and the
    coarser lane simply owns fewer tiles — here, none.
    """
    window = _window(0)
    planes = _render(window, 0, INJECTED_DOTS_XY, None)
    fine = _lane(window, planes, ppc=4.0, level_index=0)
    coarse = _lane(window, planes, ppc=2.0, level_index=1)
    grouped = tuple(
        (fields_collect.tile_rows(lane.windows[0].page_cells_yx,
                                  TILES_YX),)
        for lane in (fine, coarse))
    owner = fields_collect.assign_tiles((fine, coarse), grouped)
    assert owner, "the assignment covered no tile at all"
    assert set(owner.values()) == {(0, 0)}, owner


def test_the_window_with_the_most_of_a_tile_measures_it():
    """One level, two windows over one tile: one measurement, and it is
    the window with the most to correlate."""
    sparse = {0: np.arange(30, dtype=np.int64)}
    dense = {0: np.arange(90, dtype=np.int64)}
    lane = fields_collect.LaneWindows(
        level_index=0, ppc=4.0, windows=(None, None),
        window_ids=(WID, WID_B), pose_generation=(1, 1),
        planes=())
    assert fields_collect.assign_tiles((lane,), ((sparse, dense),)) == {
        0: (0, 1)}
    assert fields_collect.assign_tiles((lane,), ((dense, sparse),)) == {
        0: (0, 0)}


def test_a_measurement_survives_a_pose_that_has_not_moved():
    """I9, the memo: a re-collection copies what it would re-measure.

    The measurement is a function of the pose it was taken through and
    of what was known at the tile.  Neither moved, so the row is carried
    over — which is what makes a page certifying in a hundred batches
    cost one measurement per tile rather than a hundred.
    """
    first = _collect()
    again = _collect(standing=first)
    assert _table(again) == _table(first)


def test_a_moved_pose_is_re_measured_and_a_new_certificate_too():
    first = _collect()
    moved = dataclasses.replace(
        first,
        window_generation=np.asarray(first.window_generation) + 1)
    assert fields_collect.standing_row(
        moved, 0, 2, WID, 1, plane_field.SOURCE_ANCHOR) is None
    assert fields_collect.standing_row(
        first, 0, 2, WID, 1, plane_field.SOURCE_ANCHOR) is not None
    # the (tile, plane) was furniture when it was measured; its own
    # certificate has landed since, so its template is another one
    assert fields_collect.standing_row(
        first, 0, 2, WID, 1, plane_field.SOURCE_CERTIFIED) is None


def test_a_tile_that_changed_hands_is_re_measured_at_its_new_window():
    """I4 against the memo: the owner is part of the pose's identity.

    Every freshly placed window stands at generation 0, so two windows
    over one tile collide on a generation key — and the scale-space
    order the receiver runs (coarse windows placed first, finer ones
    later) is exactly the order that hands a tile from one to the other.
    Carrying the coarse lane's row there would keep a measurement the
    owning window never made, invisibly: the carried row reports the
    generation it was measured at, so the next collection carries it
    again.
    """
    first = _collect()
    assert fields_collect.standing_row(
        first, 0, 2, WID_B, 1, plane_field.SOURCE_ANCHOR) is None
    assert fields_collect.standing_row(
        first, 0, 2, WID, 1, plane_field.SOURCE_ANCHOR) is not None
    window = _window(0)
    lane = _lane(window, _render(window, 0, (-1.0, 0.0)), wid=WID_B)
    handed = _collect(standing=first, lanes=(lane,))
    assert float(np.median(_by_plane(handed, 2)[:, 0])) < -0.5


# --------------------------------------------------------------------
# `fields.collect` — the scheduling
# --------------------------------------------------------------------

def _colour_store() -> engine._Engine:
    store = _engine()
    store._captures[CAPTURE_ID] = _h3_facts.capture()
    store._lane_page_wids[(CAPTURE_ID, 0, PAGE)] = {WID}
    return store


def _placed_store(certificates: dict) -> engine._Engine:
    """`_colour_store` with everything `prepare_collect` reads.

    The window is PLACED through the store's own fold, not poked into
    the lane index, so the level, the pose generation and the page
    cells are production's; the rasters are the fixture's, painted from
    the same certificates the collection will read.
    """
    store = _engine()
    capture = _h3_facts.capture()
    store._captures[CAPTURE_ID] = capture
    store._levels[(CAPTURE_ID, 0)] = capture.levels[0]
    store._fold(_h3_fixture_geometry.window_placement(
        WID, _h3_fixture_geometry.page_native_affine(PITCH_PX, 0.0),
        _h3_facts.tile_cells(SPAN_CELLS), page=PAGE, rot_k=0))
    store._planes_by_lane[(CAPTURE_ID, 0)] = dict(zip(
        ("r", "g", "b"),
        _render(_window(0), 0, INJECTED_DOTS_XY, certificates)))
    for certificate in certificates.values():
        store._fold(certificate)
    return store


def test_a_swim_certificate_closes_the_loop_into_the_next_collection():
    """Bar B5: the rescue row's win is evidence for the field that fed it.

    `tiles.swim` reads the page field to place its search and mints a
    certificate the ordinary rows could not.  That certificate has to
    come back round — as a certified-tile observation in the next
    collection, and as known cells for the pose work of the windows
    that own the tile — or the toolbox's top row is a leaf.

    The loop is closed here at the one stream that closes it: C and M
    are certified by `tiles.scan`, Y is NOT, and the swim's Y
    certificate is what gives Y its own template.  So both halves below
    are caused by the swim's win and by nothing else.
    """
    every = _tile_certificates(0, 0)
    swum_key = (PAGE, 0, 0, ROW.streams[2].stream_id)
    scanned = {key: certificate for key, certificate in every.items()
               if key != swum_key}
    swum = dataclasses.replace(
        every[swum_key], source=tiles.source_tag(tiles.STAGE_SWIM150))
    assert swum.source == "tiles/swim150"
    whole = {**scanned, swum_key: swum}
    code = 0

    # Y has no template of its own until the swim's certificate lands
    assert field_tiers.certified_template(ROW, GEOMETRY, PAGE, (0, 0), 2,
                                          scanned) is None
    assert field_tiers.certified_template(ROW, GEOMETRY, PAGE, (0, 0), 2,
                                          whole) is not None

    # half one: the next collection reads it through the certified tier
    store = _placed_store(whole)
    job = fields_collect.prepare_collect(store, (CAPTURE_ID, PAGE),
                                         fields_collect.STAGE_COLLECT)
    assert job is not None
    fact, = job().facts
    codes = np.asarray(fact.tile_code, np.int64)
    sources = np.asarray(fact.source, np.int64)
    assert set(sources[codes == code].tolist()) == {
        plane_field.SOURCE_CERTIFIED}
    assert plane_field.SOURCE_CERTIFIED not in set(
        sources[codes != code].tolist())

    # half two: and the same certificate is known cells for the window
    window = _window(0)
    before = color_region.build_window_rows(ROW, GEOMETRY, window,
                                            scanned, {})
    after = color_region.build_window_rows(ROW, GEOMETRY, window, whole,
                                           {})
    mine = ((np.asarray(window.page_cells_yx, np.int64)[:, 0] // TILE_CELLS
             == 0)
            & (np.asarray(window.page_cells_yx, np.int64)[:, 1]
               // TILE_CELLS == 0))
    assert not np.asarray(before.known_component_mask)[mine].all()
    assert np.asarray(after.known_component_mask)[mine].all()


def test_a_placement_births_its_own_capture_page():
    store = _colour_store()
    placement = _h3_facts.placement(page=PAGE)
    assert fields_collect._collect_subjects(store, placement) == (
        (CAPTURE_ID, PAGE),)


def test_a_certificate_births_every_capture_placed_on_that_page():
    store = _colour_store()
    store._captures[OTHER_CAPTURE] = dataclasses.replace(
        _h3_facts.capture(), capture_id=OTHER_CAPTURE)
    store._lane_page_wids[(OTHER_CAPTURE, 0, PAGE)] = {
        (OTHER_CAPTURE, 0, 0, WID[3])}
    assert fields_collect._collect_subjects(
        store, _h3_facts.certificate(page=PAGE)) == (
        (OTHER_CAPTURE, PAGE), (CAPTURE_ID, PAGE))


def test_a_capture_with_no_window_on_the_page_is_no_subject():
    store = _colour_store()
    store._lane_page_wids.clear()
    assert fields_collect._collect_subjects(
        store, _h3_facts.certificate(page=PAGE)) == ()
    assert not fields_collect._collect_eligible(store, (CAPTURE_ID, PAGE))


def test_no_field_worker_is_ever_born_on_a_k_page():
    """I11: K has one plane and no differential, `D_K = 0`."""
    store = _colour_store()
    store.row = dataclasses.replace(store.row, family=identity.Family.K)
    assert fields_collect._collect_subjects(
        store, _h3_facts.certificate(page=PAGE)) == ()
    assert fields_collect._collect_subjects(
        store, _h3_facts.placement(page=PAGE)) == ()


def test_the_collection_subscribes_to_the_page_and_to_every_level():
    store = _colour_store()
    store._captures[CAPTURE_ID] = dataclasses.replace(
        _h3_facts.capture(),
        levels=(data.Level(index=0, ppc=Fraction(4), scale=Fraction(1),
                           shape_px=(64, 64), label="l0"),
                data.Level(index=1, ppc=Fraction(2), scale=Fraction(2),
                           shape_px=(32, 32), label="l1")))
    assert fields_collect._collect_reads(store, (CAPTURE_ID, PAGE)) == (
        ("page_certs", PAGE),
        ("lane_poses", CAPTURE_ID, 0, PAGE),
        ("lane_poses", CAPTURE_ID, 1, PAGE))


def test_the_collection_prices_its_re_measurements_by_fire_ordinal():
    """And the FIRST fire is priced at one fire, not at none.

    `COLLECT_COST * 0` put the cold full-page collection under survey's
    10 and jumped the whole ladder — worst on a resume, where every
    capture's first fire is that collection (13 of them on sheet H).
    """
    store = _colour_store()
    prices = [fields_collect._collect_cost(
        store, (CAPTURE_ID, PAGE), fields_collect.STAGE_COLLECT, n, 0)
        for n in (0, 1, 2, 3)]
    assert prices == [180, 180, 360, 540]


def test_the_collector_retires_on_the_pages_done_grid_and_the_solve_never():
    """The gate is the PAYLOAD's, so only the row that measures obeys it.

    AMENDED 2026-09-08: the solve retired on the same grid, and because
    the engine asks `retire` before eligibility it retired at the pop
    that its own collection had just born it on — a page that finishes
    while a collection is in flight published no field at all.  The
    behaviour is pinned on the engine's own path in
    `test_h3_field_lifecycle.py`; this is the rule at the row.
    """
    store = _colour_store()
    assert not fields_collect._collect_retire(store, (CAPTURE_ID, PAGE))
    assert not fields._fields_retire(store, PAGE)
    done = np.ones(TILES_YX, bool)
    store._done_grid_cache[PAGE] = (store.n_certificates(), done)
    assert fields_collect._collect_retire(store, (CAPTURE_ID, PAGE))
    assert not fields._fields_retire(store, PAGE)


# --------------------------------------------------------------------
# `fields` — the solve row
# --------------------------------------------------------------------

def test_the_solve_is_born_by_a_collection_and_subscribes_to_its_page():
    store = _colour_store()
    fact = _h3_facts.field_observations(page=3)
    assert fields._fields_subjects(store, fact) == (3,)
    assert fields._fields_reads(store, 3) == ((KEY_FIELD_OBS, 3),)


def test_the_solve_is_a_flat_price_whatever_its_fire_ordinal():
    store = _colour_store()
    assert [fields._fields_cost(store, PAGE, fields.STAGE_SOLVE, n, 0)
            for n in (1, 2, 3)] == [40, 40, 40]


def test_a_plane_with_evidence_and_no_field_is_eligible_at_once():
    store = _colour_store()
    assert not fields._fields_eligible(store, PAGE)
    store._fold(_h3_facts.field_observations())
    assert fields._fields_eligible(store, PAGE)


def test_the_solve_publishes_one_field_per_plane_at_the_pages_revision():
    """I1, I6 and I12: three fields, keyed by (page, plane), a plane no
    observation reached published at zero rather than left out, and
    every one of them stamped with the evidence revision it was fitted
    at."""
    store = _colour_store()
    store._fold(_h3_facts.field_observations(delta_dots=0.8))
    job = fields.prepare_fields(store, PAGE, fields.STAGE_SOLVE)
    result = job()
    assert len(result.facts) == 3
    assert {(fact.page, fact.plane) for fact in result.facts} == {
        (PAGE, 0), (PAGE, 1), (PAGE, 2)}
    assert {fact.ordinal for fact in result.facts} == {
        store.page_evidence_revision(PAGE)}
    y_field = result.facts[2]
    assert np.count_nonzero(y_field.support) == 2
    # what the VALUE of a lone Y window's field is belongs to the gauge
    # module: under R-A the constant part of a window that saw no word
    # ink is that window's own nuisance, not the page's field
    assert not np.any(result.facts[0].support)
    event, = result.events
    assert event.page == PAGE and len(event.planes) == 3
    assert {row[0] for row in event.residual_by_capture_plane} == {
        CAPTURE_ID}


def test_a_second_capture_pools_into_the_same_page_field():
    """Bar B2: two captures, one field, and the observation count grows
    by exactly what the second capture measured."""
    store = _colour_store()
    store._fold(_h3_facts.field_observations(delta_dots=0.8))
    one = fields.page_observations(store, PAGE)
    store._fold(_h3_facts.field_observations(capture_id=OTHER_CAPTURE,
                                             delta_dots=0.8))
    two, captures = fields.page_observations(store, PAGE)
    assert captures == (OTHER_CAPTURE, CAPTURE_ID)
    assert len(two) == 2 * len(one[0])
    assert set(np.unique(two.capture).tolist()) == {0, 1}
    result = fields.prepare_fields(store, PAGE, fields.STAGE_SOLVE)()
    assert len(result.facts) == 3
    assert result.facts[2].n_captures == 2
    assert {row[0] for row in
            result.events[0].residual_by_capture_plane} == set(captures)


# --------------------------------------------------------------------
# the cells, the folds and the accessors
# --------------------------------------------------------------------

def test_a_later_solve_adopts_and_an_identical_clock_is_a_no_op():
    store = _colour_store()
    first = _field(plane=2, ordinal=3)
    changed, keys, _kind = store._fold(first)
    assert changed and keys == ((KEY_PLANE_FIELD, PAGE, 2),)
    older, _keys, _kind = store._fold(_field(plane=2, ordinal=2))
    assert older is False
    same, _keys, _kind = store._fold(_field(plane=2, ordinal=3,
                                            delta_dots=9.9))
    assert same is False
    assert store._plane_fields[(PAGE, 2)] is first
    later, keys, _kind = store._fold(_field(plane=2, ordinal=4))
    assert later and keys


def test_a_window_that_moves_off_a_page_wakes_the_page_it_left():
    """The vacated lane-page, which only this fold knows about.

    The move drops the window from page A's lane set and appends page
    B's key; without A's key too, A's standing observations keep rows
    measured through a window the receiver has since moved — attributed
    to A's tile codes — until some unrelated fact on A wakes the row.
    `fields.collect` subscribes to exactly this key.
    """
    store = _h3_facts.seeded_engine("Placement")
    store._fold(_h3_facts.BUILD["Placement"]())
    wid = _h3_facts.WINDOW_ID
    stood = store.placement(wid).page
    _adopted, keys, _kind = store._fold(
        dataclasses.replace(store.placement(wid), page=stood + 1,
                            route=data.ROUTE_REFINE))
    assert (KEY_LANE_POSES, wid[0], wid[1], stood) in keys
    assert (KEY_LANE_POSES, wid[0], wid[1], stood + 1) in keys
    assert store.lane_page_windows(wid[0], wid[1], stood) == ()


def test_the_accessors_serve_the_page_and_only_the_page():
    store = _colour_store()
    store._fold(_field(plane=2))
    served = store.page_plane_fields(PAGE)
    assert served[0] is None and served[1] is None
    assert served[2] is store._plane_fields[(PAGE, 2)]
    assert store.page_plane_fields(1) == (None, None, None)
    assert not hasattr(store, "lane_plane_fields")


def test_the_observations_accessor_orders_by_capture_and_filters_by_page():
    store = _colour_store()
    store._fold(_h3_facts.field_observations(capture_id=CAPTURE_ID))
    store._fold(_h3_facts.field_observations(capture_id=OTHER_CAPTURE))
    store._fold(_h3_facts.field_observations(capture_id=CAPTURE_ID,
                                             page=1))
    assert [fact.capture_id for fact in store.field_observations(PAGE)] == [
        OTHER_CAPTURE, CAPTURE_ID]
    assert [fact.page for fact in store.field_observations(1)] == [1]


# --------------------------------------------------------------------
# the snapshot
# --------------------------------------------------------------------

def test_the_field_is_durable_and_the_observations_regenerate(tmp_path):
    """I10: the solved field is a fact and a cache; the observations are
    derived from placements, certificates and rasters, all three of
    which a resume re-declares."""
    store = _colour_store()
    store._fold(_field(plane=2, ordinal=5))
    store._fold(_h3_facts.field_observations())
    facts = snapshot.collect(store)
    kinds = {type(fact).__name__ for fact in facts}
    assert "PlaneField" in kinds
    assert "FieldObservations" not in kinds
    assert data.FieldObservations not in snapshot.FAMILIES
    path = tmp_path / snapshot.NAME
    snapshot.write(path, facts)
    back = [fact for fact in snapshot.read(path)
            if isinstance(fact, data.PlaneField)]
    assert len(back) == 1
    assert (back[0].page, back[0].plane, back[0].ordinal) == (PAGE, 2, 5)


# --------------------------------------------------------------------
# the read side (W3 moves it behind the one mapping)
# --------------------------------------------------------------------

def test_the_read_side_offers_nothing_when_no_plane_has_a_field():
    cells = _cells()
    assert color_region.field_offsets(None, cells) is None
    assert color_region.field_offsets((None, None, None), cells) is None


def test_the_read_side_serves_dots_per_cell_for_the_planes_that_have_one():
    cells = _cells((2, 2))
    field = _field(plane=2, delta_dots=0.75, tiles_yx=(2, 2))
    offsets = color_region.field_offsets((None, None, field), cells)
    assert offsets[0] is None and offsets[1] is None
    assert offsets[2].shape == (cells.shape[0], 2)
    assert np.allclose(offsets[2][:, 0], 0.75)
    assert np.allclose(offsets[2][:, 1], 0.0)


def test_an_explicit_override_still_wins_over_the_standing_field():
    cells = _cells((2, 2))
    rows = data.WindowRows(
        patch_ordinal=7, window_id=("cap", 0, 0, (0, 0, 8, 8)), page=0,
        local_cells_yx=cells, page_cells_yx=cells,
        scan_points_yx=cells.astype(np.float64),
        states=np.zeros(cells.shape[0], np.int8),
        furniture_kind=np.zeros(cells.shape[0], np.int8),
        known_component_bits=np.zeros((cells.shape[0], 3), np.uint8),
        known_component_mask=np.ones((cells.shape[0], 3), bool),
        heldout_logloss=None)
    explicit = (None, None, np.zeros((cells.shape[0], 2)))
    field = _field(plane=2, delta_dots=0.75, tiles_yx=(2, 2))
    served = color_region.row_offsets({7: explicit}, (None, None, field),
                                      rows)
    assert served is explicit
    served = color_region.row_offsets(None, (None, None, field), rows)
    assert np.allclose(served[2][:, 0], 0.75)


# --------------------------------------------------------------------
# the engine
# --------------------------------------------------------------------

def test_the_engine_carries_both_rows_and_only_they_write_their_families():
    names = tuple(descriptor.name for descriptor in engine.DESCRIPTORS)
    assert "fields" in names and "fields.collect" in names
    assert names.index("fields.collect") < names.index("fields")
    writers = tuple(descriptor.name for descriptor in engine.DESCRIPTORS
                    if data.PlaneField in descriptor.produces)
    _h3_support.assert_measured("PlaneField writers", writers, ("fields",))
    collectors = tuple(descriptor.name for descriptor in engine.DESCRIPTORS
                       if data.FieldObservations in descriptor.produces)
    _h3_support.assert_measured("FieldObservations writers", collectors,
                               ("fields.collect",))


def test_the_tile_grid_is_the_one_the_geometry_declares():
    assert geometry.TILE_CELLS == TILE_CELLS
    assert TILES_YX == ROW.tiles_yx
