from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data
from holo.receiver.format.identity import Family
from holo.receiver.lib.decimate import (
    AreaPixelTransform,
    area_decimate,
    auto_ppc_levels,
    native_pixels_per_cell,
)
from holo.receiver.plugins import intake, survey
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_candidate_pitches_admit_the_declared_row_without_dropping_any`,
# `test_level_labels_name_the_rung_and_its_effective_dpi`,
# `test_minimum_ppc_is_the_two_pixel_per_cell_floor`,
# `test_platen_backing_is_the_median_of_the_border_strips`,
# `test_support_mask_fills_small_holes_and_keeps_large_ones`,
# `test_survey_regions_are_ordered_by_supported_area`,
# `test_tensor_geometry_is_the_declared_work_cell_decimation`,
# `test_the_survey_sort_really_reverses_the_raster_detection_order`.

LATTICE_PITCH_PX = 6
LATTICE_CELLS = 120
LATTICE_MARGIN_PX = 40
LATTICE_SEED = 5
LATTICE_DPI = 1200.0
LATTICE_PITCH_IN = Fraction(1, 200)

# recorded 2026-08-29 on machine 4's free-threaded 3.14 venv (then named
# env314t), on the synthetic 6 px/cell lattice below
VOTED_PITCH_PX = 5.983739837398375
SURVEY_STEP_PX = 16

INTEGER_LADDERS = (
    (1200.0, Fraction(1, 200), (2, 3, 6)),
    (2400.0, Fraction(1, 200), (2, 4, 6, 12)),
    (1200.0, Fraction(1, 300), (2, 4)),
    (4800.0, Fraction(1, 300), (2, 4, 8, 16)),
    (600.0, Fraction(1, 300), (2,)),
    (1200.0, Fraction(1, 150), (2, 4, 8)),
)


@pytest.mark.parametrize("dpi,pitch_in,ppc", INTEGER_LADDERS)
def test_the_level_ladder_is_integer_only_for_every_shipped_footing(
        dpi, pitch_in, ppc):
    assert auto_ppc_levels(dpi, pitch_in) == tuple(
        Fraction(value) for value in ppc)
    levels = intake.build_levels(dpi, pitch_in, (1200, 900))
    assert tuple(int(level.ppc) for level in levels) == ppc
    for level in levels:
        assert level.scale.denominator == 1
        assert AreaPixelTransform(level.scale).is_integer_box
    assert levels[-1].scale == 1
    assert levels[-1].shape_px == (1200, 900)
    assert levels[-1].ppc == native_pixels_per_cell(dpi, pitch_in)
    assert tuple(level.index for level in levels) == tuple(
        range(len(levels)))


def test_a_fractional_footing_level_materialises_by_exact_rational_area(
        tmp_path: Path, lattice_grey):
    import tifffile

    levels = intake.build_levels(1000.0, Fraction(1, 300), (900, 900))
    assert tuple(str(level.scale) for level in levels) == ("5/3", "1")
    assert AreaPixelTransform(levels[0].scale).is_integer_box is False
    scan = tmp_path / "frac.tiff"
    tifffile.imwrite(scan, lattice_grey)
    capture, rasters, _events = intake.ingest_capture(
        scan, 1000.0, Fraction(1, 300), Family.K, tmp_path / "runf")
    assert tuple(str(level.scale) for level in capture.levels) == (
        "5/3", "1")
    by_level = {raster.level_index: raster for raster in rasters}
    expected = area_decimate(lattice_grey,
                             intake.level_transform(capture.levels[0]))
    assert np.array_equal(np.asarray(by_level[0].open()), expected)
    assert expected.shape == capture.levels[0].shape_px


def test_minimum_ppc_is_the_two_pixel_per_cell_floor():
    from holo.receiver.lib import decimate

    _h3_support.assert_measured("MINIMUM_PPC", decimate.MINIMUM_PPC,
                               Fraction(2))
    assert auto_ppc_levels(300.0, Fraction(1, 300)) == (Fraction(1),)
    assert auto_ppc_levels(600.0, Fraction(1, 300)) == (Fraction(2),)


def test_level_labels_name_the_rung_and_its_effective_dpi():
    levels = intake.build_levels(2400.0, Fraction(1, 200), (1200, 900))
    _h3_support.assert_measured(
        "level labels", tuple(level.label for level in levels),
        ("l00-2ppc-400dpi", "l01-4ppc-800dpi", "l02-6ppc-1200dpi",
         "l03-12ppc-2400dpi"))


def test_sha256_file_matches_hashlib(tmp_path: Path):
    payload = bytes(range(256)) * 40
    target = tmp_path / "blob.bin"
    target.write_bytes(payload)
    assert intake.sha256_file(target) == hashlib.sha256(
        payload).hexdigest()


def _lattice_bits() -> np.ndarray:
    rng = np.random.default_rng(LATTICE_SEED)
    return rng.random((LATTICE_CELLS, LATTICE_CELLS)) < 0.5


def _lattice_grey() -> np.ndarray:
    rng = np.random.default_rng(LATTICE_SEED)
    bits = rng.random((LATTICE_CELLS, LATTICE_CELLS)) < 0.5
    span = LATTICE_CELLS * LATTICE_PITCH_PX
    side = span + 2 * LATTICE_MARGIN_PX
    image = np.full((side, side), 240, np.uint8)
    block = np.kron(
        np.where(bits, 70, 240).astype(np.uint8),
        np.ones((LATTICE_PITCH_PX, LATTICE_PITCH_PX), np.uint8))
    image[LATTICE_MARGIN_PX:LATTICE_MARGIN_PX + span,
          LATTICE_MARGIN_PX:LATTICE_MARGIN_PX + span] = block
    noise = rng.normal(0.0, 2.0, image.shape).astype(np.int16)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def lattice_grey() -> np.ndarray:
    return _lattice_grey()


def test_load_native_round_trips_a_grey_tiff(tmp_path: Path, lattice_grey):
    import tifffile

    target = tmp_path / "grey.tiff"
    tifffile.imwrite(target, lattice_grey)
    loaded = intake.load_native(target)
    assert loaded.shape == lattice_grey.shape
    assert loaded.dtype == np.uint8
    assert np.array_equal(np.asarray(loaded), lattice_grey)


def test_load_native_drops_a_singleton_channel_axis(tmp_path: Path):
    import tifffile

    rgb = np.zeros((32, 40, 1), np.uint8)
    rgb[..., 0] = np.arange(32 * 40, dtype=np.uint8).reshape(32, 40)
    target = tmp_path / "single.tiff"
    tifffile.imwrite(target, rgb)
    assert intake.load_native(target).shape == (32, 40)


def test_platen_backing_is_the_median_of_the_border_strips():
    image = np.full((200, 200), 17, np.uint8)
    image[intake.BORDER_PX:-intake.BORDER_PX,
          intake.BORDER_PX:-intake.BORDER_PX] = 250
    assert intake.platen_backing(image) == 17.0
    _h3_support.assert_measured("BORDER_PX", intake.BORDER_PX, 32)


def test_native_and_derived_plane_names_follow_the_family():
    assert intake.native_plane_names(1) == ("g",)
    assert intake.native_plane_names(3) == ("r", "g", "b")
    assert intake.derived_planes(1, Family.K) == (("g", None),)
    assert intake.derived_planes(3, Family.K) == (("y", None),)
    assert intake.derived_planes(3, Family.CMY8) == (
        ("r", 0), ("g", 1), ("b", 2))
    assert intake.derived_planes(3, Family.CMY7) == (
        ("r", 0), ("g", 1), ("b", 2))


def test_ingest_capture_honours_the_declared_dpi_and_writes_every_plane(
        tmp_path: Path, lattice_grey):
    import tifffile

    scan = tmp_path / "scan.tiff"
    tifffile.imwrite(scan, lattice_grey)
    run_dir = tmp_path / "run"
    capture, rasters, events = intake.ingest_capture(
        scan, LATTICE_DPI, LATTICE_PITCH_IN, Family.K, run_dir)
    assert capture.capture_id == intake.sha256_file(scan)
    assert capture.dpi == LATTICE_DPI
    assert capture.channels == 1
    assert capture.shape_px == lattice_grey.shape
    assert capture.platen_backing == pytest.approx(240.0, abs=2.0)
    assert tuple(int(level.ppc) for level in capture.levels) == (2, 3, 6)
    assert len(rasters) == len(capture.levels)
    for raster in rasters:
        assert raster.path.is_file()
        assert raster.capture_id == capture.capture_id
        assert raster.open().shape == raster.shape_px
    native = intake.native_level(capture)
    assert native.index == capture.levels[-1].index
    assert np.array_equal(
        np.asarray(rasters[0].open()), lattice_grey)
    assert len(events) == 1
    assert events[0].duplicate is False
    assert events[0].capture == capture.capture_id


def test_ingest_captures_reports_a_repeated_file_as_a_duplicate(
        tmp_path: Path, lattice_grey):
    import tifffile

    first = tmp_path / "a.tiff"
    second = tmp_path / "b.tiff"
    tifffile.imwrite(first, lattice_grey)
    tifffile.imwrite(second, lattice_grey)
    assert intake.sha256_file(first) == intake.sha256_file(second)
    captures, rasters, events = intake.ingest_captures(
        (first, second), (LATTICE_DPI, LATTICE_DPI), LATTICE_PITCH_IN,
        Family.K, tmp_path / "run2")
    assert len(captures) == 1
    assert len(rasters) == len(captures[0].levels)
    assert tuple(event.duplicate for event in events) == (False, True)


def test_decimated_planes_equal_a_direct_area_decimation(
        tmp_path: Path, lattice_grey):
    import tifffile

    scan = tmp_path / "scan3.tiff"
    tifffile.imwrite(scan, lattice_grey)
    capture, rasters, _events = intake.ingest_capture(
        scan, LATTICE_DPI, LATTICE_PITCH_IN, Family.K, tmp_path / "run3")
    by_level = {raster.level_index: raster for raster in rasters}
    for level in capture.levels[:-1]:
        expected = area_decimate(lattice_grey,
                                 intake.level_transform(level))
        assert np.array_equal(np.asarray(by_level[level.index].open()),
                              expected)
        assert expected.shape == level.shape_px


def test_level_pitch_and_extent_are_exact_at_every_rung():
    levels = intake.build_levels(LATTICE_DPI, LATTICE_PITCH_IN, (1200, 900))
    native_pitch = float(LATTICE_PITCH_IN) * LATTICE_DPI
    for level in levels:
        assert intake.level_pitch_px(level, native_pitch) == (
            native_pitch / float(level.scale))
    assert intake.level_extent(levels[0], (0, 0, 1200, 900)) == (
        0, 0, 400, 300)
    assert intake.level_extent(levels[1], (6, 10, 1200, 900)) == (
        3, 5, 600, 450)
    assert intake.level_extent(levels[2], (6, 10, 1200, 900)) == (
        6, 10, 1200, 900)
    assert intake.level_extent(levels[0], (0, 0, 1, 1)) is None


def test_level_centres_map_a_level_index_to_its_native_centre():
    levels = intake.build_levels(LATTICE_DPI, LATTICE_PITCH_IN, (1200, 900))
    coarse = levels[0]
    assert coarse.scale == 3
    centres = intake.level_centres(coarse, np.arange(4, dtype=np.int64))
    assert np.array_equal(centres, np.asarray([1, 4, 7, 10]))
    native = intake.level_centres(levels[-1], np.arange(4, dtype=np.int64))
    assert np.array_equal(native, np.arange(4))


def _region(step_px: int = 16, shape: tuple[int, int] = (10, 10),
            origin_yx: tuple[int, int] = (32, 48)) -> data.Region:
    cells = np.ones(shape, bool)
    cells[0, 0] = False
    cells.setflags(write=False)
    return data.Region(
        capture_id="cap", region_index=0, origin_yx=origin_yx,
        step_px=step_px, cells=cells,
        extent_px=(shape[0] * step_px, shape[1] * step_px),
        area_mm2=10.0, median_tensor_score=1.0)


def test_region_support_crop_clamps_to_the_region_and_never_overruns():
    levels = intake.build_levels(LATTICE_DPI, LATTICE_PITCH_IN, (1200, 900))
    region = _region()
    crop = intake.region_support_crop(region, levels[-1], 0, 200, 0, 260)
    assert crop.shape == (200, 260)
    assert not crop[:32, :48].any()
    assert crop[64:80, 64:80].all()
    assert not crop[32:48, 48:64].any()
    far = intake.region_support_crop(region, levels[-1], 5000, 5010, 5000,
                                     5010)
    assert far.shape == (10, 10)
    assert not far.any()


def test_region_support_crop_agrees_across_the_level_ladder():
    levels = intake.build_levels(LATTICE_DPI, LATTICE_PITCH_IN, (1200, 900))
    region = _region()
    native = intake.region_support_crop(region, levels[-1], 0, 240, 0, 240)
    coarse = intake.region_support_crop(region, levels[0], 0, 80, 0, 80)
    centres = intake.level_centres(levels[0], np.arange(80, dtype=np.int64))
    assert np.array_equal(coarse, native[np.ix_(centres, centres)])


def _native_view(image: np.ndarray, dpi: float = LATTICE_DPI
                 ) -> survey.NativeView:
    return survey.NativeView(dpi=dpi, shape=image.shape, planes=(image,))


def test_survey_view_votes_the_printed_pitch_off_a_synthetic_lattice(
        lattice_grey):
    regions, voted, pitch_px, score, step = survey.survey_view(
        _native_view(lattice_grey), LATTICE_PITCH_IN)
    assert voted == LATTICE_PITCH_IN
    assert pitch_px == pytest.approx(VOTED_PITCH_PX, rel=1e-12)
    assert pitch_px == pytest.approx(float(LATTICE_PITCH_IN) * LATTICE_DPI,
                                     rel=0.01)
    assert step == SURVEY_STEP_PX
    assert score.shape[0] > 0
    assert len(regions) == 1
    region = regions[0]
    assert region.support.any()
    assert region.origin_yx[0] <= LATTICE_MARGIN_PX
    assert region.origin_yx[1] <= LATTICE_MARGIN_PX
    assert region.extent_px[0] >= LATTICE_CELLS * LATTICE_PITCH_PX
    assert region.extent_px[1] >= LATTICE_CELLS * LATTICE_PITCH_PX


def test_survey_view_is_empty_on_a_raster_below_the_survey_cell_floor():
    regions, voted, pitch_px, score, step = survey.survey_view(
        _native_view(np.full((32, 32), 240, np.uint8)), LATTICE_PITCH_IN)
    assert regions == ()
    assert voted is None and pitch_px is None
    assert score.size == 0
    assert step == SURVEY_STEP_PX


def test_candidate_pitches_admit_the_declared_row_without_dropping_any():
    assert survey.candidate_pitches(None) == survey.CANDIDATE_PITCHES_IN
    assert survey.candidate_pitches(
        Fraction(1, 200)) == survey.CANDIDATE_PITCHES_IN
    widened = survey.candidate_pitches(Fraction(1, 250))
    assert set(survey.CANDIDATE_PITCHES_IN) <= set(widened)
    assert Fraction(1, 250) in widened
    assert widened == tuple(sorted(widened))
    _h3_support.assert_measured(
        "CANDIDATE_PITCHES_IN", survey.CANDIDATE_PITCHES_IN,
        (Fraction(1, 600), Fraction(1, 300), Fraction(1, 200),
         Fraction(1, 150)))


def _capture_and_planes(tmp_path: Path, image: np.ndarray,
                        dpi: float) -> tuple[data.Capture, tuple]:
    plane_dir = tmp_path / "planes"
    plane_dir.mkdir(parents=True, exist_ok=True)
    levels = intake.build_levels(dpi, LATTICE_PITCH_IN, image.shape)
    native_index = levels[-1].index
    path = intake.plane_path(plane_dir, native_index, intake.PLANE_GREY)
    np.save(path, image)
    raster = data.PlaneRaster("cap", native_index, intake.PLANE_GREY, path,
                              image.shape)
    capture = data.Capture(
        capture_id="cap", path=tmp_path / "scan.tiff", dpi=dpi,
        shape_px=image.shape, channels=1, platen_backing=240.0,
        levels=levels, plane_dir=plane_dir)
    return capture, (raster,)


def test_survey_capture_refuses_a_declared_pitch_the_sheet_contradicts(
        tmp_path: Path, lattice_grey):
    capture, planes = _capture_and_planes(tmp_path, lattice_grey,
                                          LATTICE_DPI)
    with pytest.raises(ValueError) as excinfo:
        survey.survey_capture(capture, planes, Fraction(1, 300))
    message = str(excinfo.value)
    assert "voted printed pitch 1/200 in" in message
    assert "declared format row is 1/300 in" in message


def test_survey_capture_accepts_the_pitch_the_sheet_agrees_with(
        tmp_path: Path, lattice_grey):
    capture, planes = _capture_and_planes(tmp_path, lattice_grey,
                                          LATTICE_DPI)
    result, events = survey.survey_capture(capture, planes,
                                           LATTICE_PITCH_IN)
    assert result.capture_id == "cap"
    assert result.pitch_class == LATTICE_PITCH_IN
    assert result.pitch_px == pytest.approx(VOTED_PITCH_PX, rel=1e-12)
    assert len(result.regions) == 1
    region = result.regions[0]
    assert region.region_index == 0
    assert region.cells.dtype == bool
    assert region.cells.flags.writeable is False
    assert region.area_mm2 > 0.0
    assert len(events) == 1
    event = events[0]
    assert event.capture == "cap"
    assert event.n_regions == 1
    assert event.pitch_class == "1/200"
    assert event.preview_decim == SURVEY_STEP_PX
    assert event.regions[0].support_cells == int(region.cells.sum())


TWO_PATCH_SMALL_CELLS = 45
TWO_PATCH_BIG_CELLS = 90
TWO_PATCH_GAP_PX = 60
# recorded 2026-08-29 on machine 4's free-threaded 3.14 venv (then named
# env314t), on the two-patch lattice below; the SMALL patch sits
# top-left, so raster/detection order is the reverse of area order
TWO_PATCH_SHAPE_PX = (620, 950)
TWO_PATCH_DETECTION_ORIGINS = ((36, 36), (36, 365))
TWO_PATCH_AREA_ORDER_ORIGINS = ((36, 365), (36, 36))


def _lattice_patch(rng: np.random.Generator, n_cells: int) -> np.ndarray:
    bits = rng.random((n_cells, n_cells)) < 0.5
    return np.kron(np.where(bits, 70, 240).astype(np.uint8),
                   np.ones((LATTICE_PITCH_PX, LATTICE_PITCH_PX), np.uint8))


@pytest.fixture(scope="module")
def two_patch_grey() -> np.ndarray:
    rng = np.random.default_rng(LATTICE_SEED)
    small = _lattice_patch(rng, TWO_PATCH_SMALL_CELLS)
    big = _lattice_patch(rng, TWO_PATCH_BIG_CELLS)
    margin = LATTICE_MARGIN_PX
    height = 2 * margin + max(small.shape[0], big.shape[0])
    width = (2 * margin + small.shape[1] + TWO_PATCH_GAP_PX + big.shape[1])
    image = np.full((height, width), 240, np.uint8)
    image[margin:margin + small.shape[0],
          margin:margin + small.shape[1]] = small
    big_x0 = margin + small.shape[1] + TWO_PATCH_GAP_PX
    image[margin:margin + big.shape[0], big_x0:big_x0 + big.shape[1]] = big
    noise = rng.normal(0.0, 2.0, image.shape).astype(np.int16)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_survey_regions_are_ordered_by_supported_area(tmp_path: Path,
                                                       two_patch_grey):
    from holo.receiver.plugins.survey import _RawRegion, _support_area_px

    small = np.ones((4, 4), bool)
    large = np.ones((9, 9), bool)
    assert _support_area_px(small, 16, (64, 64)) == 64 * 64
    assert _support_area_px(large, 16, (144, 144)) == 144 * 144
    assert isinstance(_RawRegion((0, 0), small, 16, (64, 64), 1.0).score,
                      float)

    assert two_patch_grey.shape == TWO_PATCH_SHAPE_PX
    capture, planes = _capture_and_planes(tmp_path, two_patch_grey,
                                          LATTICE_DPI)
    result, events = survey.survey_capture(capture, planes, LATTICE_PITCH_IN)
    assert len(result.regions) == 2
    _h3_support.assert_measured(
        "two-patch region origins in area order",
        tuple(region.origin_yx for region in result.regions),
        TWO_PATCH_AREA_ORDER_ORIGINS)
    assert result.regions[0].area_mm2 > result.regions[1].area_mm2
    assert [region.region_index for region in result.regions] == [0, 1]
    measured = [_support_area_px(np.asarray(region.cells, bool),
                                 region.step_px, region.extent_px)
                for region in result.regions]
    assert measured[0] > measured[1]
    assert [mark.origin_yx for mark in events[0].regions] == list(
        TWO_PATCH_AREA_ORDER_ORIGINS)


def test_the_survey_sort_really_reverses_the_raster_detection_order(
        two_patch_grey):
    raw, voted, _pitch_px, _score, _step = survey.survey_view(
        _native_view(two_patch_grey), LATTICE_PITCH_IN)
    assert voted == LATTICE_PITCH_IN
    _h3_support.assert_measured(
        "two-patch detection-order origins",
        tuple(region.origin_yx for region in raw),
        TWO_PATCH_DETECTION_ORIGINS)
    assert TWO_PATCH_DETECTION_ORIGINS != TWO_PATCH_AREA_ORDER_ORIGINS, (
        "the two patches no longer disagree on detection and area order: "
        "this pin can no longer tell a sorted survey from an unsorted one")


def test_support_mask_fills_small_holes_and_keeps_large_ones():
    active = np.ones((40, 40), bool)
    active[10, 10] = False
    active[20:32, 20:32] = False
    filled = survey.support_mask(active, survey.SUPPORT_HOLE_RADIUS_CELLS)
    assert filled[10, 10]
    assert not filled[26, 26]
    assert np.array_equal(survey.support_mask(active, 0.5), active)
    _h3_support.assert_measured("SUPPORT_HOLE_RADIUS_CELLS",
                               survey.SUPPORT_HOLE_RADIUS_CELLS, 3.0)


def test_tensor_geometry_is_the_declared_work_cell_decimation():
    _h3_support.assert_measured("WORK_CELL_PX", survey.WORK_CELL_PX, 4.0)
    _h3_support.assert_measured("SURVEY_CELL_UM", survey.SURVEY_CELL_UM,
                               340.0)
    assert survey.tensor_geometry(16.06) == (4, 4, 16)
    assert survey.tensor_geometry(6.0) == (2, 3, 6)
    assert survey.tensor_geometry(2.0) == (1, 2, 2)
    for pitch_px in (2.0, 6.0, 16.06, 64.0):
        decimation, work, step = survey.tensor_geometry(pitch_px)
        assert step == decimation * work
