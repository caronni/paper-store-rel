"""The E022 pose kernel and the v1 reference field, pinned by hand.

W0 sub-wave A2 (H4-PLAN §3-W0).  ``pose_fit`` and ``reference`` are ports
of v1's ``placement/{geometry,reference}.py``, and R4 pins them
BEHAVIOURALLY — so every literal below is derived here by hand from the
published rule and the carried constants, never read back off the code.
Importing ``holo`` to cross-check would violate the firewall; the
cross-tree comparison is a scratch differential (W0-A2) and W0-B's
harness.

The window-layout arithmetic everything else stands on, computed once for
the default config (``window_cells`` 200, ``overlap_cells`` 40):

    window_px = int(round(200 * pitch))
    step_px   = max(1, int(round(160 * pitch)))
    starts(L) = [0] if L <= window_px else
                range(0, L - window_px + 1, step_px) + (L - window_px)
                if that last start is not already there

and the support estimate, on the globally phased ``[::4, ::4]`` mask:

    support_estimate = int(samples * 16 / pitch**2)

which for a FULLY supported 200x200-cell window is 40,000 at any pitch
whose 4x boxes land whole — that number is the window's cell count, and
that is the estimator's whole point.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.capture.scan import open_capture
from holo2.capture.survey import SupportMask
from holo2.format import bch, pilots
from holo2.format.format_v1 import tile_format
from holo2.solve.place_model import (PlacementConfig, PoseWindow,
                                     admission_datum)
from holo2.solve import pose_fit
from holo2.solve.pose_fit import (MIN_WINDOW_CELLS, SUBDIVISION_MAX_DEPTH,
                                  AddressPatch, LatticeSeed, PreparedRegion,
                                  fit_window_pose, jacobian_from_reciprocal,
                                  make_address_patch,
                                  median_radiometrics, platen_backing,
                                  pose_metrics, prepare_region,
                                  refresh_address_patch, sample_segment,
                                  subdivide_pose_window,
                                  subdivision_child_extents)
from holo2.solve.reference import (ReferencePage, V1ReferenceField,
                                   overlap_slices, rotate_points,
                                   rotation_affine)

PAPER = 238.0


def region(shape_px: tuple[int, int], pitch: float, *,
           support: np.ndarray | None = None,
           region_index: int = 0) -> PreparedRegion:
    """A prepared region whose pixels cost nothing but whose SHAPE is real.

    Only ``layout``/``subdivide`` read this one, and they read the image's
    shape and the support mask; a zero-stride broadcast gives both without
    allocating an A4 page at 4,800 dpi.
    """
    blank = np.broadcast_to(np.float32(PAPER), shape_px)
    if support is None:
        support = np.broadcast_to(np.float32(1.0), shape_px)
    return PreparedRegion(region_index, 0, 0, blank, blank, support,
                          PAPER, pitch, 1)


# ------------------------------------------------- the OR-9 table's first use

def test_the_kernel_reads_its_floors_from_the_or9_table() -> None:
    """The depth cap was a bare literal in v1; it is a datum here."""
    assert SUBDIVISION_MAX_DEPTH == 1
    assert admission_datum("subdivision_max_depth").value == 1
    assert MIN_WINDOW_CELLS == 70
    assert admission_datum("min_window_cells").value == 70
    # the config knob subdivide actually reads defaults to that same row
    assert PlacementConfig().min_window_cells == MIN_WINDOW_CELLS
    assert PlacementConfig().window_cells == 200
    assert PlacementConfig().overlap_cells == 40


# ---------------------------------------------------------- radiometrics

def test_median_radiometrics_midpoint_spread_and_bounded_evidence() -> None:
    """median, mean-absolute-deviation spread, and -tanh(llr/2)."""
    means = np.array([[10.0, 20.0, 30.0, 40.0]], np.float32)
    mask = np.ones((1, 4), bool)
    midpoint, bits, evidence = median_radiometrics(means, mask)
    # median(10,20,30,40) = 25; MAD = mean(15,5,5,15) = 10
    assert midpoint == 25.0
    # llr = (25 - m)/10 * 2 = 3, 1, -1, -3; evidence = -tanh(llr/2)
    assert evidence.dtype == np.float32
    assert evidence[0] == pytest.approx(
        [-np.tanh(1.5), -np.tanh(0.5), np.tanh(0.5), np.tanh(1.5)], abs=1e-7)
    assert bits.dtype == np.uint8
    assert list(bits[0]) == [1, 1, 0, 0]


def test_median_radiometrics_masks_the_statistic_but_not_the_bits() -> None:
    """The midpoint sees only selected cells; the hard bits see them all."""
    means = np.array([[10.0, 20.0, 30.0, 40.0]], np.float32)
    mask = np.array([[True, True, True, False]])
    midpoint, bits, evidence = median_radiometrics(means, mask)
    # median(10,20,30) = 20; MAD = mean(10,0,10) = 20/3
    assert midpoint == 20.0
    assert evidence[0, 3] == 0.0                     # unselected: zeroed
    assert evidence[0, 0] == pytest.approx(-np.tanh(1.5), abs=1e-7)
    assert evidence[0, 1] == 0.0                     # exactly at the median
    assert list(bits[0]) == [1, 0, 0, 0]             # the 40 is NOT masked


def test_median_radiometrics_clips_the_llr_at_eight() -> None:
    """The bounded-evidence invariant (018.7): |llr| <= 8 before tanh."""
    means = np.array([0.0] + [100.0] * 7, np.float32).reshape(1, 8)
    midpoint, _bits, evidence = median_radiometrics(
        means, np.ones((1, 8), bool))
    # median = 100; MAD = 100/8 = 12.5; (100-0)/12.5 = 8.0, exactly the clip
    assert midpoint == 100.0
    assert evidence[0, 0] == pytest.approx(-np.tanh(8.0), abs=1e-7)
    means = np.array([-1e6] + [100.0] * 7, np.float32).reshape(1, 8)
    _mid, _bits, evidence = median_radiometrics(means, np.ones((1, 8), bool))
    assert evidence[0, 0] == pytest.approx(-np.tanh(8.0), abs=1e-7)


def test_median_radiometrics_is_degenerate_on_a_two_valued_population() -> None:
    """CARRIED behaviour, measured in H4 W1 and pinned so it is not a surprise.

    The E022 median detector splits at the MEDIAN, so a population with
    no within-class spread — an exactly two-valued raster, which only a
    noiseless synthetic capture produces — has its midpoint ON a class
    the moment that class holds more than half the cells, and ``means <
    midpoint`` then selects nothing. Measured consequence on a clean
    render before the fixture dithered: 3 of 9 windows read ~50 wrong
    sites per 100-site address word and decoded nothing at all.

    This is the carried arithmetic, not a defect the port introduced, and
    W1 did not fork it (R4). The receiver-side fact it records: the hard
    decision needs a capture whose classes have SOME spread, which every
    real scan has; the evidence path is immune either way, because PAVA
    is fitted on the scores and never on these bits.
    """
    ink, paper = 26.0, 238.0
    mask = np.ones((1, 8), bool)
    majority_ink = np.array([[ink] * 5 + [paper] * 3], np.float64)
    midpoint, bits, _evidence = median_radiometrics(majority_ink, mask)
    assert midpoint == ink and not bits.any(), "the cliff, exactly"
    majority_paper = np.array([[ink] * 3 + [paper] * 5], np.float64)
    midpoint, bits, _evidence = median_radiometrics(majority_paper, mask)
    assert midpoint == paper and bits.sum() == 3, "the other majority reads"
    # ANY within-class spread removes it: the median then lands at a
    # quantile INSIDE the majority class and only its own tail is lost.
    spread = np.array([[25.0, 25.5, 26.0, 26.5, 27.0, 237.0, 238.0, 239.0]])
    _midpoint, bits, _evidence = median_radiometrics(spread, mask)
    assert bits.sum() == 4


def test_median_radiometrics_floors_a_degenerate_spread() -> None:
    means = np.full((2, 2), 7.0, np.float32)
    midpoint, bits, evidence = median_radiometrics(means, np.ones((2, 2), bool))
    assert midpoint == 7.0
    assert not evidence.any()                # spread floored at 1e-6, llr = 0
    assert not bits.any()                    # 7 < 7 is false everywhere


# ------------------------------------------------------- region preparation

def test_platen_backing_is_the_median_of_four_borders() -> None:
    pixels = np.full((200, 300), 10.0, np.float32)
    pixels[32:-32, 32:-32] = 250.0           # the interior never counts
    raster = open_capture(pixels, 600.0)
    assert platen_backing(raster) == 10.0
    # a border wider than the raster clamps rather than raising
    assert platen_backing(open_capture(np.full((3, 4), 5.0, np.float32),
                                       600.0), border_px=99) == 5.0


#: Rasters the two backing implementations are compared on. Odd AND even
#: border populations (numpy's median averages the middle PAIR on an even
#: count, and that average is exactly where two transcriptions could
#: quietly disagree), a raster smaller than the 32-px border so the clamp
#: participates, and RGB ones so the luma reduction is in the path.
_BACKING_SHAPES = ((97, 101, 1), (96, 100, 1), (12, 9, 1), (80, 64, 3),
                   (33, 65, 3))


@pytest.mark.parametrize("shape", _BACKING_SHAPES)
def test_captures_backing_is_this_kernels_backing_bit_for_bit(
        shape: tuple[int, int, int]) -> None:
    """THE DUPLICATION PIN (2026-08-17). One number, two homes, no drift.

    ``capture`` may not import ``solve``, so the platen backing exists
    twice: this carried v1 kernel, and ``capture.ingest.platen_backing``,
    which is the one an ingest RECORDS. It is a digest input —
    ``solve.prepared`` hashes it into a prepared plane's file name — so
    "close enough" is not a category here: one ULP of drift renames every
    plane on disk and makes the recorded value disagree with what a
    session holding the raster computes. Bit equality, therefore, via
    ``float.hex``, and on the awkward shapes rather than a round one.

    This test lives on the ``solve`` side because the test DAG lets a
    ``solve`` test import ``capture`` and not the reverse.
    """
    from holo2.capture.ingest import platen_backing as recorded

    height, width, channels = shape
    rng = np.random.default_rng(20260817 + height * 1000 + width)
    page = rng.integers(0, 256, dtype=np.uint8, size=(
        (height, width) if channels == 1 else (height, width, channels)))
    raster = open_capture(np.ascontiguousarray(page), 600.0)
    for border_px in (32, 8, 99):
        assert (recorded(raster, border_px=border_px).hex()
                == platen_backing(raster, border_px=border_px).hex()), (
            f"{shape} at border {border_px}: the two transcriptions parted")


def test_prepare_region_fills_unsupported_pixels_with_the_backing() -> None:
    pixels = np.full((64, 64), 20.0, np.float32)
    cells = np.zeros((4, 4), bool)
    cells[0:2, 0:2] = True                   # the top-left 32x32 px
    mask = SupportMask((0, 0), 16, cells, (64, 64))
    prepared = prepare_region(open_capture(pixels, 600.0), mask, 5, 4.0,
                              config=PlacementConfig(), backing=PAPER)
    assert prepared is not None
    assert prepared.region_index == 5 and (prepared.y0, prepared.x0) == (0, 0)
    assert prepared.image.shape == (64, 64)
    assert prepared.image.dtype == np.float32
    assert prepared.image[0, 0] == 20.0
    assert prepared.image[40, 40] == np.float32(PAPER)
    assert prepared.support.dtype == np.float32
    assert prepared.support[0, 0] == 1.0 and prepared.support[40, 40] == 0.0
    assert prepared.backing == PAPER and prepared.pitch_prior == 4.0


def test_prepare_region_aperture_rounds_half_to_even() -> None:
    """``int(round(0.7 * pitch))`` — NOT ``int(ceil)``, NOT ``+0.5``."""
    pixels = np.full((64, 64), 20.0, np.float32)
    mask = SupportMask((0, 0), 16, np.ones((4, 4), bool), (64, 64))
    raster = open_capture(pixels, 600.0)

    def aperture(pitch: float) -> int:
        prepared = prepare_region(raster, mask, 0, pitch,
                                  config=PlacementConfig(), backing=PAPER)
        assert prepared is not None
        return prepared.aperture_px

    assert aperture(4.0) == 3                # 2.8 -> 3
    assert aperture(2.0) == 1                # 1.4 -> 1
    assert aperture(5.0) == 4                # 3.5 -> 4 (half to EVEN, up)
    assert aperture(15.0) == 10              # 10.5 -> 10 (half to EVEN, down)
    assert aperture(0.5) == 1                # 0.35 -> 0, floored at 1


def test_prepare_region_refuses_empty_support_and_bad_pitch() -> None:
    pixels = np.full((64, 64), 20.0, np.float32)
    raster = open_capture(pixels, 600.0)
    config = PlacementConfig()
    # a bbox entirely past the raster edge clips to nothing
    off = SupportMask((80, 80), 16, np.ones((2, 2), bool), (32, 32))
    assert prepare_region(raster, off, 0, 4.0,
                          config=config, backing=PAPER) is None
    for bad in (0.0, -1.0, np.inf, np.nan):
        with pytest.raises(ValueError):
            prepare_region(raster, SupportMask(
                (0, 0), 16, np.ones((4, 4), bool), (64, 64)),
                0, bad, config=config, backing=PAPER)


def test_prepare_region_clips_its_crop_at_the_raster_edge() -> None:
    pixels = np.full((40, 50), 20.0, np.float32)
    mask = SupportMask((8, 10), 16, np.ones((3, 4), bool), (48, 60))
    prepared = prepare_region(open_capture(pixels, 600.0), mask, 0, 4.0,
                              config=PlacementConfig(), backing=PAPER)
    assert prepared is not None
    assert (prepared.y0, prepared.x0) == (8, 10)
    assert prepared.image.shape == (32, 40)      # min(40, 8+48), min(50,10+60)


# ---------------------------------------------------------- subdivision

def test_subdivide_places_four_corner_children() -> None:
    parent = PoseWindow(11, 2, (100, 200), (200, 160), 0, 40000)
    children = subdivide_pose_window(parent, region((4000, 4000), 4.0),
                                     config=PlacementConfig(),
                                     first_window_id=900)
    # side = max(70, min(200,160)//2) = max(70, 80) = 80
    assert [c.window_id for c in children] == [900, 901, 902, 903]
    assert {c.shape_yx_cells for c in children} == {(80, 80)}
    assert {c.depth for c in children} == {1}
    assert {c.region_index for c in children} == {2}
    assert {c.support_estimate for c in children} == {0}
    # offsets (0,0) (0, 160-80) (200-80, 0) (200-80, 160-80), times pitch 4
    assert [c.origin_yx_px for c in children] == [
        (100, 200), (100, 200 + 320), (100 + 480, 200),
        (100 + 480, 200 + 320)]


def test_subdivide_uses_the_min_window_floor_when_halving_is_smaller() -> None:
    parent = PoseWindow(0, 0, (0, 0), (100, 100), 0, 0)
    children = subdivide_pose_window(parent, region((4000, 4000), 4.0),
                                     config=PlacementConfig(),
                                     first_window_id=0)
    # side = max(70, 50) = 70 < 100, so four 70-cell corners still fit
    assert {c.shape_yx_cells for c in children} == {(70, 70)}
    assert [c.origin_yx_px for c in children] == [
        (0, 0), (0, 120), (120, 0), (120, 120)]      # (100-70) * 4 = 120


def test_subdivide_refuses_a_window_too_small_to_halve() -> None:
    """``side >= min(height, width)`` — no child may equal its parent."""
    # side = max(70, min//2), so a window refuses exactly when its
    # shorter axis is at or below the 70-cell floor
    for shape in ((70, 70), (100, 60), (12, 400), (400, 70)):
        assert subdivide_pose_window(
            PoseWindow(0, 0, (0, 0), shape, 0, 0), region((900, 900), 4.0),
            config=PlacementConfig(), first_window_id=0) == ()
    # 71 is the first shorter axis that halves above the floor, and it
    # still yields 70-cell corners (halving does not take over until 140)
    children = subdivide_pose_window(
        PoseWindow(0, 0, (0, 0), (71, 400), 0, 0), region((900, 900), 4.0),
        config=PlacementConfig(), first_window_id=0)
    assert len(children) == 4
    assert {c.shape_yx_cells for c in children} == {(70, 70)}


def test_subdivide_honours_the_depth_cap_and_the_config_switch() -> None:
    parent = PoseWindow(0, 0, (0, 0), (200, 200), SUBDIVISION_MAX_DEPTH, 0)
    assert subdivide_pose_window(parent, region((4000, 4000), 4.0),
                                 config=PlacementConfig(),
                                 first_window_id=0) == ()
    root = PoseWindow(0, 0, (0, 0), (200, 200), 0, 0)
    assert subdivide_pose_window(
        root, region((4000, 4000), 4.0),
        config=PlacementConfig(subdivide=False), first_window_id=0) == ()


def test_subdivide_rounds_its_corner_offsets_half_to_even() -> None:
    """Bare ``round()`` on the offset, then ``int()`` on the sum."""
    parent = PoseWindow(0, 0, (7, 9), (200, 200), 0, 0)
    children = subdivide_pose_window(parent, region((9000, 9000), 2.5),
                                     config=PlacementConfig(),
                                     first_window_id=0)
    # side = 100; offset 100 * 2.5 = 250.0, exact
    assert [c.origin_yx_px for c in children] == [
        (7, 9), (7, 259), (257, 9), (257, 259)]
    # a .5 offset: side 100 at pitch 0.105 -> 10.5 -> round -> 10, not 11
    children = subdivide_pose_window(parent, region((900, 900), 0.105),
                                     config=PlacementConfig(),
                                     first_window_id=0)
    assert [c.origin_yx_px for c in children] == [
        (7, 9), (7, 19), (17, 9), (17, 19)]


def test_the_cell_extent_twin_is_the_same_geometry_without_pixels() -> None:
    """W3's split: one arithmetic, asked in the frame the caller has.

    The pull scheduler names windows by capture-cell extents and holds
    no prepared region, so it asks :func:`subdivision_child_extents`;
    :func:`subdivide_pose_window` asks the same function and multiplies
    by a pitch. This pins that they cannot drift — the pixel origins are
    the cell offsets through the region's own pitch, corner for corner,
    in the same order.
    """
    prepared = region((4000, 4000), 4.0)
    parent = PoseWindow(11, 2, (100, 200), (200, 160), 0, 40000)
    children = subdivide_pose_window(parent, prepared,
                                     config=PlacementConfig(),
                                     first_window_id=900)
    extents = subdivision_child_extents((0, 0, 200, 160), depth=0,
                                        config=PlacementConfig())
    assert len(extents) == len(children) == 4
    for extent, child in zip(extents, children):
        cy0, cx0, cy1, cx1 = extent
        assert child.shape_yx_cells == (cy1 - cy0, cx1 - cx0)
        assert child.origin_yx_px == (
            int(parent.origin_yx_px[0] + round(cy0 * prepared.pitch_prior)),
            int(parent.origin_yx_px[1] + round(cx0 * prepared.pitch_prior)))


def test_the_cell_extents_are_offset_by_the_parents_own_origin() -> None:
    """The scheduler's frame: children live where the PARENT lives.

    ``subdivide_pose_window`` computes offsets against a window whose
    cell origin is implicitly zero (it carries a pixel origin instead),
    so the twin has to add the parent's cell origin itself or every
    child of every non-origin window would land in the same corner of
    the region.
    """
    config = PlacementConfig()
    assert subdivision_child_extents((320, 480, 520, 680), depth=0,
                                     config=config) == (
        (320, 480, 420, 580), (320, 580, 420, 680),
        (420, 480, 520, 580), (420, 580, 520, 680))
    assert subdivision_child_extents((0, 0, 200, 200), depth=1,
                                     config=config) == ()
    assert subdivision_child_extents(
        (0, 0, 200, 200), depth=0,
        config=PlacementConfig(subdivide=False)) == ()


# ------------------------------------------------ the fit, on real pixels

def lattice_pixels(cells_yx: tuple[int, int], pitch: int) -> np.ndarray:
    """A deterministic printed-looking cell field at an exact pitch."""
    cy, cx = np.meshgrid(np.arange(cells_yx[0]), np.arange(cells_yx[1]),
                         indexing="ij")
    ink = ((cy * 7 + cx * 13) % 3) == 0
    cells = np.where(ink, 26.0, PAPER)
    return np.repeat(np.repeat(cells, pitch, 0), pitch, 1).astype(np.float32)


@pytest.fixture(scope="module")
def lattice() -> PreparedRegion:
    pixels = lattice_pixels((96, 96), 4)
    mask = SupportMask((0, 0), 16, np.ones((24, 24), bool), (384, 384))
    prepared = prepare_region(open_capture(pixels, 600.0), mask, 0, 4.0,
                              config=PlacementConfig(), backing=PAPER)
    assert prepared is not None
    return prepared


def test_fit_measures_a_synthetic_lattice_and_reports_its_seed(
        lattice: PreparedRegion) -> None:
    config = PlacementConfig()
    window = PoseWindow(0, 0, (0, 0), (96, 96), 0, 9216)
    fit = fit_window_pose(lattice, window, config=config)
    assert fit.segment is not None and fit.lattice_seed is not None
    pitch_y, pitch_x = fit.segment.pitch_yx_px
    assert pitch_y == pytest.approx(4.0, abs=4.0 * config.pitch_tolerance)
    assert pitch_x == pytest.approx(4.0, abs=4.0 * config.pitch_tolerance)
    assert abs(fit.segment.orthogonality_error_deg) <= \
        config.shear_tolerance_deg
    assert fit.segment.window is window
    assert fit.segment.support_cells == 0        # sampling sets it, not the fit
    # the seed is the fitted reciprocal, and it inverts to the Jacobian
    seed = fit.lattice_seed
    assert pose_metrics(jacobian_from_reciprocal(seed.matrix()))[:2] == \
        pytest.approx((pitch_y, pitch_x))
    # 0.5 <= phase < 1.5 by construction of the offsets grid
    assert all(0.5 <= value < 1.5 for value in fit.segment.pose.phase_yx)


def test_a_seeded_edge_window_fits_where_a_blind_one_refuses(
        lattice: PreparedRegion) -> None:
    """The R5 seam: 10 cells at pitch 4 is 40 px < 12 periods = 48 px."""
    config = PlacementConfig()
    big = fit_window_pose(lattice, PoseWindow(0, 0, (0, 0), (96, 96)),
                          config=config)
    assert big.lattice_seed is not None
    small = PoseWindow(1, 0, (40, 40), (10, 10))
    blind = fit_window_pose(lattice, small, config=config)
    assert blind.segment is None and blind.lattice_seed is None
    seeded = fit_window_pose(lattice, small, config=config,
                             lattice_seed=big.lattice_seed)
    assert seeded.segment is not None
    # the seed is USED, never replaced, and comes back identically
    assert seeded.lattice_seed is big.lattice_seed
    assert seeded.segment.pose.jacobian_yx == big.segment.pose.jacobian_yx


def test_a_seeded_region_never_re_seeds_from_a_later_window(
        lattice: PreparedRegion) -> None:
    """v1's first-fit-wins, restated as a pure function of the argument."""
    config = PlacementConfig()
    window = PoseWindow(0, 0, (0, 0), (96, 96))
    first = fit_window_pose(lattice, window, config=config)
    assert first.lattice_seed is not None
    # a DIFFERENT (still legal) seed, offered to the same window
    other = LatticeSeed((0.25, 0.0, 0.0, 0.25))
    again = fit_window_pose(lattice, window, config=config,
                            lattice_seed=other)
    assert again.lattice_seed is other
    assert again.segment is not None


def test_the_fit_refuses_a_blank_region_and_invents_no_seed() -> None:
    blank = np.full((384, 384), PAPER, np.float32)
    mask = SupportMask((0, 0), 16, np.ones((24, 24), bool), (384, 384))
    prepared = prepare_region(open_capture(blank, 600.0), mask, 0, 4.0,
                              config=PlacementConfig(), backing=PAPER)
    assert prepared is not None
    fit = fit_window_pose(prepared, PoseWindow(0, 0, (0, 0), (96, 96)),
                          config=PlacementConfig())
    assert fit.segment is None and fit.lattice_seed is None


def test_the_fit_refuses_a_window_shorter_than_four_periods(
        lattice: PreparedRegion) -> None:
    seed = LatticeSeed((0.25, 0.0, 0.0, 0.25))
    fit = fit_window_pose(lattice, PoseWindow(0, 0, (0, 0), (3, 3)),
                          config=PlacementConfig(), lattice_seed=seed)
    assert fit.segment is None
    assert fit.lattice_seed is seed          # the region's fact is untouched


# ---------------------------------- the declared-pitch zoom-refit branch (W3)

def _decoy_plus_true_lattice_pixels(
        cells: int, pitch: int, a_true: float, a_decoy: float,
        decoy_angle_deg: float) -> np.ndarray:
    """A real axis-aligned lattice, submerged under a stronger decoy.

    Raw sinusoids, not ink/paper cells, so each component is a single
    clean spectral peak and the construction can be reasoned about by
    hand. The TRUE lattice sits exactly on ``pitch``, axis-aligned, at
    amplitude ``a_true``. The DECOY is a pair of components at the same
    spatial-frequency MAGNITUDE (so it lands inside ``lattice_reciprocal``'s
    radial band) but at ``decoy_angle_deg`` and ``decoy_angle_deg + 80``
    from the x-axis — 80, not 90, so a fit that locks onto the decoy pair
    measures a real ~5deg orthogonality error (the gate is 3deg) and a
    real >6% pitch miss on one axis, at amplitude ``a_decoy`` so the
    blind global-argmax search picks the decoy over the true lattice.
    """
    ys, xs = np.meshgrid(np.arange(cells * pitch), np.arange(cells * pitch),
                         indexing="ij")
    f = 1.0 / pitch
    theta = np.deg2rad(decoy_angle_deg)
    fy1, fx1 = f * np.cos(theta), f * np.sin(theta)
    theta2 = theta + np.deg2rad(80.0)
    fy2, fx2 = f * np.cos(theta2), f * np.sin(theta2)
    image = (
        PAPER
        + a_true * np.cos(2 * np.pi * ys / pitch)
        + a_true * np.cos(2 * np.pi * xs / pitch)
        + a_decoy * np.cos(2 * np.pi * (fy1 * ys + fx1 * xs))
        + a_decoy * np.cos(2 * np.pi * (fy2 * ys + fx2 * xs))
    )
    return image.astype(np.float32)


def _decoy_region(config: PlacementConfig) -> PreparedRegion:
    pixels = _decoy_plus_true_lattice_pixels(96, 4, 5.0, 40.0, 27.0)
    mask = SupportMask((0, 0), 16, np.ones((24, 24), bool), (384, 384))
    prepared = prepare_region(open_capture(pixels, 600.0), mask, 0, 4.0,
                              config=config, backing=PAPER)
    assert prepared is not None
    return prepared


def test_fit_window_pose_zoom_refits_around_the_declared_pitch() -> None:
    """The DECLARED-PITCH retry (``fit_window_pose``, the ``seed_rows is
    None`` arm of the post-blind-refusal ``retry_prior``): H4-W3-PLAN
    records this arm as firing in no test.  Without it, a full-size
    window whose blind fit locks a decoy would simply refuse; with it,
    the retry re-centres on the format's OWN axis-aligned pitch (never a
    measured prior, because no seed exists yet) and recovers the real,
    weaker lattice underneath.

    LIVENESS (checked by hand, then reverted): replacing the branch's
    ``else np.array([[1/prior, 0], [0, 1/prior]])`` fallback with
    ``retry_prior = seed_rows`` (so the retry degenerates to a second
    blind pass, ``prior_f=None``) makes ``fit.segment`` come back
    ``None`` on this exact fixture -- the decoy fit is refused again
    and nothing rescues it.
    """
    config = PlacementConfig()
    prepared = _decoy_region(config)
    window = PoseWindow(0, 0, (0, 0), (96, 96), 0, 9216)

    # Prove the BLIND arm alone really does fail the geometric gate here
    # -- the precondition the retry branch exists to fix.  The 384x384
    # crop is under ``spectral_px`` (2048), so it IS the spectral crop
    # ``fit_window_pose`` would use.
    blind = pose_fit.lattice_reciprocal(prepared.image, 4.0)
    assert blind is not None                     # a peak is found ...
    _py, blind_pitch_x, _angle, blind_orth = pose_metrics(
        jacobian_from_reciprocal(blind))
    assert abs(blind_orth) > config.shear_tolerance_deg      # ... but sheared
    assert abs(blind_pitch_x / 4.0 - 1.0) > config.pitch_tolerance

    # fit_window_pose, given NO seed, must still succeed via the retry.
    fit = fit_window_pose(prepared, window, config=config)
    assert fit.segment is not None, "the declared-pitch retry did not rescue it"
    assert fit.unconditioned_seed is not None     # a fresh measurement ...
    assert fit.lattice_seed == fit.unconditioned_seed   # ... and the region's
    pitch_y, pitch_x = fit.segment.pitch_yx_px
    assert abs(pitch_y / 4.0 - 1.0) <= config.pitch_tolerance
    assert abs(pitch_x / 4.0 - 1.0) <= config.pitch_tolerance
    assert abs(fit.segment.orthogonality_error_deg) <= config.shear_tolerance_deg


# ------------------------------ unconditioned_seed's anti-laundering contract

def test_unconditioned_seed_never_carries_a_consulted_seed_back_out(
        lattice: PreparedRegion) -> None:
    """R5's anti-laundering rule (``lattice_seed.py`` module docstring,
    "What a proposal may carry"): a fit that CONSULTED an incoming seed
    must report ``unconditioned_seed is None``, in both arms that read
    one -- the small-window edge arm (uses the seed as its only fit,
    no measurement at all) and the full-window CONDITIONED zoom-refit
    retry (blind fails, an existing seed rescues it).  Re-proposing the
    seed under the rescued window's own name would be circular and
    would let a poorly-supported window launder a better window's
    numbers -- exactly what H4-W3-PLAN records as unpinned.

    LIVENESS (checked by hand, then reverted): replacing
    ``measured = (None if conditioned else LatticeSeed.from_matrix(...))``
    with an unconditional ``LatticeSeed.from_matrix(...)`` (i.e. always
    reporting a measurement, laundering included) makes this test's
    second assertion fail on the conditioned arm below.
    """
    config = PlacementConfig()

    # Arm 1: the small-window edge arm (the R5 seam: 10 cells at pitch 4
    # is 40px, under the 12-period/48px full-window floor).
    seed = LatticeSeed((0.25, 0.0, 0.0, 0.25))
    small = fit_window_pose(lattice, PoseWindow(1, 0, (40, 40), (10, 10)),
                            config=config, lattice_seed=seed)
    assert small.segment is not None
    assert small.unconditioned_seed is None

    # Arm 2: the full-window CONDITIONED zoom-refit retry -- blind fails
    # its gates on the decoy fixture, the supplied seed rescues it.
    prepared = _decoy_region(config)
    window = PoseWindow(0, 0, (0, 0), (96, 96), 0, 9216)
    axis_seed = LatticeSeed((0.25, 0.0, 0.0, 0.25))
    conditioned_fit = fit_window_pose(prepared, window, config=config,
                                      lattice_seed=axis_seed)
    assert conditioned_fit.segment is not None
    assert conditioned_fit.unconditioned_seed is None
    assert conditioned_fit.lattice_seed is axis_seed        # kept, not replaced


# -------------------------------------------- the phase objective's own gate

def slanted_support(support: np.ndarray, percentile: float) -> np.ndarray:
    """The same support, cut back along a SLANTED, ragged boundary.

    Ragged in cell terms on purpose: an axis-aligned cut gives all 64
    hypotheses the same site count, where a half-cell phase shift moves
    nothing.  The slant makes the covered count differ BETWEEN
    hypotheses, which is how a window at a support edge actually reads.
    """
    height, width = support.shape
    ramp = (np.arange(height, dtype=np.float64)[:, None]
            + 0.37 * np.arange(width, dtype=np.float64)[None, :])
    return np.where(ramp < np.percentile(ramp, percentile), support,
                    np.float32(0.0)).astype(np.float32)


def test_the_phase_objective_scores_until_its_site_gate_bites(
        lattice: PreparedRegion) -> None:
    """The 16-site gate, walked from a full window to an unscorable one.

    The objective scores a hypothesis only when more than 16 of its cell
    centres sit over ``coverage > 0.9``, and a grid where NO hypothesis
    clears that gate stays all-``-inf`` — so the fit refuses on the
    ``np.isfinite`` test after the argmax rather than returning the
    ``-inf`` corner as a phase.  That refusal is the tail's own path and
    nothing else in this file reaches it: every other refusal here is a
    GEOMETRIC one, taken before the objective runs at all.

    The ladder is deliberately fitted OFF the fixture's grid — a slightly
    rotated Jacobian, so the reads land between pixels — and cut with a
    ragged boundary, so hypotheses of differing length are what the
    reduction actually sees.

    (This is the residue of the batched-phase-grid card, whose twin was
    deleted 2026-08-17: the arms it compared are gone, the coverage it
    bought is real and stays.  The arm's own evidence is
    ``holo2/measure/fit_phase_equivalence.py``, run by path.)
    """
    from dataclasses import replace
    config = PlacementConfig()
    window = PoseWindow(0, 0, (0, 0), (96, 96))
    fit = fit_window_pose(lattice, window, config=config)
    assert fit.segment is not None

    angle = np.deg2rad(0.4)
    jacobian = np.array([[np.cos(angle), np.sin(angle)],
                         [-np.sin(angle), np.cos(angle)]]) @ \
        fit.segment.pose.matrix()
    scored, refused = [], []
    for percentile in (100.0, 70.0, 40.0, 20.0, 8.0, 3.0, 1.0, 0.2):
        cut = replace(lattice,
                      support=slanted_support(lattice.support, percentile))
        phase = pose_fit._fit_phase(cut, jacobian, window, config)
        (refused if phase is None else scored).append(percentile)
        if phase is not None:
            (phase_y, phase_x), contrast = phase
            # The grid is [0.5, 1.5) and the parabola moves a winner by at
            # most half a step, so a returned phase cannot leave that band.
            assert 0.5 - config.phase_step_cells / 2 <= phase_y
            assert phase_y < 1.5 + config.phase_step_cells / 2
            assert 0.5 - config.phase_step_cells / 2 <= phase_x
            assert phase_x < 1.5 + config.phase_step_cells / 2
            assert np.isfinite(contrast) and contrast > 0.0
    # Teeth: the ladder really spanned scored and unscorable windows, and
    # the gate bit monotonically — every refusal below every score.
    assert len(scored) >= 3 and len(refused) >= 1
    assert max(refused) < min(scored)


# ------------------------------------------------------------ the sampler

def test_sample_segment_dtype_and_support_contract(
        lattice: PreparedRegion) -> None:
    fit = fit_window_pose(lattice, PoseWindow(4, 0, (0, 0), (96, 96)),
                          config=PlacementConfig())
    assert fit.segment is not None
    sample = sample_segment(lattice, fit.segment)
    assert sample is not None
    assert sample.means.dtype == np.float32
    assert sample.mask.dtype == np.bool_
    assert sample.bits.dtype == np.uint8
    assert sample.evidence.dtype == np.float32
    assert isinstance(sample.midpoint, float)
    assert sample.means.shape == sample.mask.shape == (96, 96)
    assert sample.bits.shape == sample.evidence.shape == (96, 96)
    # the sampler is what fills in support_cells; the fit leaves it at 0
    assert fit.segment.support_cells == 0
    assert sample.segment.support_cells == int(sample.mask.sum()) > 0
    assert sample.segment.window is fit.segment.window
    assert not sample.evidence[~sample.mask].any()


def test_sample_segment_refuses_a_pose_that_lands_off_the_support(
        lattice: PreparedRegion) -> None:
    fit = fit_window_pose(lattice, PoseWindow(0, 0, (0, 0), (96, 96)),
                          config=PlacementConfig())
    assert fit.segment is not None
    from dataclasses import replace
    moved = replace(fit.segment, pose=replace(
        fit.segment.pose, origin_yx=(100000.0, 100000.0)))
    assert sample_segment(lattice, moved) is None


def test_address_patch_wraps_and_refreshes_one_window(
        lattice: PreparedRegion) -> None:
    fit = fit_window_pose(lattice, PoseWindow(0, 0, (0, 0), (96, 96)),
                          config=PlacementConfig())
    assert fit.segment is not None
    sample = sample_segment(lattice, fit.segment)
    assert sample is not None
    patch = make_address_patch(sample)
    assert patch.shape_yx == (96, 96)
    assert patch.region_index == 0 and patch.depth == 0
    assert patch.means is sample.means and patch.bits is sample.bits
    assert patch.evidence is sample.evidence
    assert patch.frame_pose is fit.segment.pose
    eroded = sample.mask.copy()
    eroded[0, :] = False
    assert refresh_address_patch(patch, sample, eroded).mask[0, 0] == \
        np.bool_(False)
    with pytest.raises(ValueError):
        AddressPatch(sample, np.ones((5, 5), bool))
    other = PoseWindow(99, 0, (0, 0), (96, 96))
    from dataclasses import replace
    with pytest.raises(ValueError):
        refresh_address_patch(patch, replace(
            sample, segment=replace(fit.segment, window=other)))


# --------------------------------------------------------- the lattice seed

def test_lattice_seed_round_trips_through_its_durable_form() -> None:
    matrix = np.array([[0.25, 0.001], [-0.002, 0.2499]], np.float64)
    seed = LatticeSeed.from_matrix(matrix)
    assert seed.rows == (0.25, 0.001, -0.002, 0.2499)
    assert np.array_equal(seed.matrix(), matrix)
    assert LatticeSeed.from_matrix(seed.matrix()) == seed
    for bad in ((1.0, 2.0, 3.0), (1.0, 2.0, 3.0, float("nan")),
                (1.0, 2.0, 3.0, float("inf"))):
        with pytest.raises(ValueError):
            LatticeSeed(bad)                                # type: ignore[arg-type]


# ------------------------------------------------------- the reference field

def test_reference_page_carries_the_printed_word_of_every_tile() -> None:
    """Descrambling and BCH-decoding a site column returns the counter."""
    fmt = tile_format("c3-k-r0550", (2, 3))
    field = V1ReferenceField(fmt)
    page = field.page(0)
    assert isinstance(page, ReferencePage)
    assert page.values.shape == fmt.cells_yx == (128, 192)
    assert page.sites.shape == page.values.shape
    assert int(page.sites.sum()) == pilots.N_WORD_SITES * fmt.tiles_per_page
    cells = pilots.word_site_cells_yx(fmt.family_seed)
    for ty in range(2):
        for tx in range(3):
            read = page.values[ty * 64 + cells[:, 0], tx * 64 + cells[:, 1]]
            assert pilots.decode_word(read, fmt.seed) == \
                fmt.tile_counter(0, ty, tx)
            assert page.sites[ty * 64 + cells[:, 0],
                              tx * 64 + cells[:, 1]].all()


def test_reference_pages_differ_but_share_one_site_mask() -> None:
    fmt = tile_format("c2-k-r0550", (2, 2))
    field = V1ReferenceField(fmt)
    first, second = field.page(0), field.page(1)
    assert not np.array_equal(first.values, second.values)
    assert first.sites is second.sites         # page-invariant, shared
    assert field.page(0) is first              # memoized by the full key
    assert not first.values.flags.writeable
    assert not first.sites.flags.writeable
    with pytest.raises(ValueError):
        first.values[0, 0] = 1


def test_reference_field_refuses_pages_outside_the_counter_space() -> None:
    fmt = tile_format("c2-k-r0700", (4, 4))
    field = V1ReferenceField(fmt)
    assert field.spec is fmt
    with pytest.raises(ValueError):
        field.page(fmt.max_pages)
    with pytest.raises(ValueError):
        field.page(-1)
    for bad in (True, np.True_, 1.0, "0", None):
        with pytest.raises(TypeError):
            field.page(bad)                             # type: ignore[arg-type]
    assert field.page(np.int64(2)).page == 2            # numpy ints are fine


def test_reference_values_are_only_ever_on_sites() -> None:
    fmt = tile_format("c3-k-r0550", (1, 2))
    page = V1ReferenceField(fmt).page(3)
    assert not page.values[~page.sites].any()
    # a v1 word is a BCH codeword of a counter, so it is not all-zero
    assert page.values[page.sites].any()
    assert page.values.dtype == np.uint8 and page.sites.dtype == np.bool_


def test_reference_page_validates_its_own_shapes() -> None:
    with pytest.raises(ValueError):
        ReferencePage(0, np.zeros((4, 4), np.uint8), np.zeros((4, 5), bool))
    with pytest.raises(ValueError):
        ReferencePage(0, np.zeros(4, np.uint8), np.zeros(4, bool))


# ------------------------------------------------- rotation / clipping algebra

@pytest.mark.parametrize("shape", [(7, 11), (11, 7), (1, 5), (4, 4)])
@pytest.mark.parametrize("rot_k", [-4, -1, 0, 1, 2, 3, 4, 7])
def test_rotate_points_is_exactly_np_rot90(shape: tuple[int, int],
                                           rot_k: int) -> None:
    """The affine IS ``np.rot90``'s, checked against numpy itself."""
    grid = np.arange(shape[0] * shape[1]).reshape(shape)
    rotated = np.rot90(grid, rot_k % 4)
    ys, xs = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                         indexing="ij")
    source = np.stack([ys.ravel(), xs.ravel()], axis=1)
    moved = rotate_points(source, shape, rot_k)
    assert moved.dtype == np.int64
    assert np.array_equal(rotated[moved[:, 0], moved[:, 1]],
                          grid[source[:, 0], source[:, 1]])


def test_rotation_affine_literals() -> None:
    matrix, translation = rotation_affine(0, (7, 11))
    assert np.array_equal(matrix, np.eye(2))
    assert np.array_equal(translation, np.zeros(2))
    matrix, translation = rotation_affine(1, (7, 11))
    assert np.array_equal(matrix, [[0.0, -1.0], [1.0, 0.0]])
    assert np.array_equal(translation, [10.0, 0.0])          # width - 1
    matrix, translation = rotation_affine(2, (7, 11))
    assert np.array_equal(matrix, -np.eye(2))
    assert np.array_equal(translation, [6.0, 10.0])          # h-1, w-1
    matrix, translation = rotation_affine(3, (7, 11))
    assert np.array_equal(matrix, [[0.0, 1.0], [-1.0, 0.0]])
    assert np.array_equal(translation, [0.0, 6.0])           # height - 1
    # rot_k is taken modulo 4, including negatives
    assert np.array_equal(rotation_affine(-1, (7, 11))[0],
                          rotation_affine(3, (7, 11))[0])


def test_overlap_slices_clips_an_overhanging_fragment() -> None:
    assert overlap_slices((0, 0), (6, 6), (10, 10)) == (
        slice(0, 6), slice(0, 6), slice(0, 6), slice(0, 6))
    # top-left overhang: the page keeps [0, 3), the fragment [3, 6)
    assert overlap_slices((-3, -2), (6, 6), (10, 10)) == (
        slice(0, 3), slice(0, 4), slice(3, 6), slice(2, 6))
    # bottom-right overhang
    assert overlap_slices((7, 8), (6, 6), (10, 10)) == (
        slice(7, 10), slice(8, 10), slice(0, 3), slice(0, 2))
    # no overlap at all, on either side
    assert overlap_slices((10, 0), (6, 6), (10, 10)) is None
    assert overlap_slices((-6, 0), (6, 6), (10, 10)) is None
    assert overlap_slices((0, -6), (6, 6), (10, 10)) is None


def test_bch_word_length_is_the_site_count_the_field_prints() -> None:
    """The one cross-check that ties reference values to the format leaf."""
    assert pilots.N_WORD_SITES == 100
    assert pilots.encode_word(0).size == pilots.N_WORD_SITES
    # BCH(127,50,t=13) shortened to (100,23): 2e + f <= 26 is bch's budget
    assert bch.T == 13
