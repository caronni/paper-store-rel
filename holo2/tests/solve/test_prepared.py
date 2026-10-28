"""The prepared plane IS ``prepare_region``, byte for byte (H4 W1a).

The change under test is a materialization change and nothing else: v1's
whole-region preparation moved out of the fire (where holo2 was paying it
per window — ~8 GB of float32 per fire on the real sheet, and workers 4/8
SIGKILLed) into one streamed, memory-mapped plane per region. So the
proof obligation is exactness, at three depths:

1. the three planes are the same BYTES ``pose_fit.prepare_region``
   produces — including when the streaming band is small enough that
   every row of the region sits near a band edge, which is what pins the
   aperture halo;
2. the kernel reading them fits the same pose and reads the same cells —
   asserted as byte equality of the affine terms and of the sampled
   arrays, not as a tolerance;
3. the refusals are the same refusals, and the mapping is read-only, so
   "nothing mutates a prepared plane" is enforced rather than promised.

The fixture is deliberately awkward: a lattice with an unsupported hole
and an unsupported border, and a bbox that runs off the raster, so the
fill, the ``mode="nearest"`` edge and the clip all participate.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from holo2.capture.scan import open_capture
from holo2.capture.survey import SupportMask
from holo2.solve import prepared as prepared_module
from holo2.solve.place_model import PlacementConfig, PoseWindow
from holo2.solve.pose_fit import (fit_window_pose, platen_backing,
                                  prepare_region, sample_segment)
from holo2.solve.prepared import (open_prepared_region, prepared_directory,
                                  prepared_region, region_extent)

PITCH = 6.0
CELLS = 96
CAPTURE = "a" * 64


def _page() -> np.ndarray:
    """A binary cell lattice on paper white, with a dark platen border."""
    rng = np.random.default_rng(20260815)
    cells = rng.random((CELLS, CELLS)) < 0.5
    field = np.kron(cells, np.ones((int(PITCH), int(PITCH)), bool))
    page = np.full((640, 660), 236, np.uint8)
    page[40:40 + field.shape[0], 50:50 + field.shape[1]] = np.where(
        field, 28, 236)
    page[:32, :] = 200                     # the platen borders the backing
    page[-32:, :] = 200                    # median reads
    return page


def _mask(step: int = 32) -> SupportMask:
    """Support over the field, with a hole and an unsupported margin."""
    cells = np.zeros((20, 20), bool)
    cells[1:18, 1:18] = True
    cells[9:11, 6:9] = False               # the hole: filled to the backing
    return SupportMask(origin_yx=(40, 50), step_px=step, cells=cells,
                       extent_px=(20 * step, 20 * step))


@pytest.fixture
def fixture(tmp_path: Path):
    """Raster, mask, backing and the directory the planes are built in."""
    raster = open_capture(_page(), 600.0)
    mask = _mask()
    return raster, mask, platen_backing(raster), tmp_path / "state.prepared"


def _both(fixture, *, config: PlacementConfig | None = None):
    raster, mask, backing, directory = fixture
    config = config or PlacementConfig()
    reference = prepare_region(raster, mask, 0, PITCH, config=config,
                               backing=backing)
    built = prepared_region(raster, mask, 0, PITCH, config=config,
                            backing=backing, capture_sha256=CAPTURE,
                            directory=directory)
    assert reference is not None and built is not None
    return reference, built


def _identical(first: np.ndarray, second: np.ndarray) -> bool:
    """Byte equality, not value equality: -0.0 and NaN are not excused."""
    return (first.shape == second.shape and first.dtype == second.dtype
            and bytes(np.ascontiguousarray(first).data)
            == bytes(np.ascontiguousarray(second).data))


# ------------------------------------------------------------ (1) the bytes

def test_the_prepared_plane_is_prepare_regions_bytes(fixture) -> None:
    reference, built = _both(fixture)
    for name in ("image", "filtered", "support"):
        assert _identical(getattr(reference, name), getattr(built, name)), (
            f"{name} differs from the whole-region preparation")


def test_every_scalar_is_prepare_regions_scalar(fixture) -> None:
    reference, built = _both(fixture)
    assert (built.region_index, built.y0, built.x0) == (
        reference.region_index, reference.y0, reference.x0)
    assert built.backing == reference.backing
    assert built.pitch_prior == reference.pitch_prior
    assert built.aperture_px == reference.aperture_px
    assert built.image.shape == reference.image.shape


def test_the_streaming_bands_leave_no_seam(fixture, monkeypatch) -> None:
    """The aperture halo, pinned: one band per few rows, same bytes.

    A band of a few rows puts EVERY row of the region within the box's
    reach of a band edge, so a missing (or too small) halo shows up as a
    horizontal stripe pattern in ``filtered`` rather than as a corner
    case that a lucky fixture size hides.
    """
    raster, mask, backing, directory = fixture
    config = PlacementConfig()
    reference = prepare_region(raster, mask, 0, PITCH, config=config,
                               backing=backing)
    assert reference is not None
    for band_rows in (1, 2, 3, 7):
        monkeypatch.setattr(prepared_module, "BAND_BYTES",
                            band_rows * int(reference.image.shape[1]) * 4)
        target = directory / f"band{band_rows}"
        built = prepared_region(raster, mask, 0, PITCH, config=config,
                                backing=backing, capture_sha256=CAPTURE,
                                directory=target)
        assert built is not None
        assert _identical(reference.filtered, built.filtered), (
            f"{band_rows}-row bands changed the aperture output")
        assert _identical(reference.image, built.image)
        assert _identical(reference.support, built.support)


def test_a_wide_aperture_still_leaves_no_seam(fixture, monkeypatch) -> None:
    """The same claim where the halo is big relative to the band."""
    raster, mask, backing, directory = fixture
    config = PlacementConfig(aperture_cells=4.0)      # 24-px box at PITCH 6
    reference = prepare_region(raster, mask, 0, PITCH, config=config,
                               backing=backing)
    assert reference is not None
    assert reference.aperture_px == 24
    monkeypatch.setattr(prepared_module, "BAND_BYTES",
                        5 * int(reference.image.shape[1]) * 4)
    built = prepared_region(raster, mask, 0, PITCH, config=config,
                            backing=backing, capture_sha256=CAPTURE,
                            directory=directory)
    assert built is not None
    assert _identical(reference.filtered, built.filtered)


# ------------------------------------------------------------ (2) the kernel

def _window() -> PoseWindow:
    return PoseWindow(0, 0, (int(round(2 * PITCH)), int(round(2 * PITCH))),
                      (64, 64), 0, 4096)


def test_the_fit_and_the_cell_read_are_unchanged(fixture) -> None:
    reference, built = _both(fixture)
    config = PlacementConfig()
    window = _window()
    left = fit_window_pose(reference, window, config=config)
    right = fit_window_pose(built, window, config=config)
    assert left.segment is not None, "the fixture must actually fit"
    assert right.segment is not None
    assert left.segment.pose == right.segment.pose, (
        "the pose is not byte-equal through the mapped plane")
    assert left.lattice_seed == right.lattice_seed
    assert left.unconditioned_seed == right.unconditioned_seed
    first = sample_segment(reference, left.segment)
    second = sample_segment(built, right.segment)
    assert first is not None and second is not None
    assert _identical(first.means, second.means)
    assert _identical(first.evidence, second.evidence)
    assert np.array_equal(first.bits, second.bits)
    assert np.array_equal(first.mask, second.mask)
    assert first.midpoint == second.midpoint


# ------------------------------------------------- (3) refusals and lifecycle

def test_the_planes_are_read_only(fixture) -> None:
    """A fire reads a shared plane; nothing may write one."""
    _reference, built = _both(fixture)
    for name in ("image", "filtered", "support"):
        plane = getattr(built, name)
        assert not plane.flags.writeable
        with pytest.raises(ValueError):
            plane[0, 0] = 1.0


def test_the_refusals_are_prepare_regions_refusals(tmp_path: Path) -> None:
    """Off the raster, and no support in the clipped bbox: both refuse."""
    directory = tmp_path / "state.prepared"
    config = PlacementConfig()
    cells = np.zeros((2, 2), bool)
    cells[1, 1] = True                     # the only support, below the clip
    mask = SupportMask(origin_yx=(0, 0), step_px=4, cells=cells,
                       extent_px=(8, 8))
    clipped = open_capture(np.full((3, 8), 200, np.uint8), 600.0)
    assert prepare_region(clipped, mask, 0, PITCH, config=config,
                          backing=200.0) is None
    assert region_extent(clipped.shape, mask, PITCH) is None
    assert prepared_region(clipped, mask, 0, PITCH, config=config,
                           backing=200.0, capture_sha256=CAPTURE,
                           directory=directory) is None
    off = SupportMask(origin_yx=(64, 0), step_px=4, cells=np.ones((2, 2), bool),
                      extent_px=(8, 8))
    assert prepare_region(clipped, off, 0, PITCH, config=config,
                          backing=200.0) is None
    assert prepared_region(clipped, off, 0, PITCH, config=config,
                           backing=200.0, capture_sha256=CAPTURE,
                           directory=directory) is None
    assert not directory.exists(), "a refusal builds nothing"


def test_a_bad_pitch_refuses_exactly_as_the_kernel_does(fixture) -> None:
    raster, mask, backing, directory = fixture
    with pytest.raises(ValueError):
        prepared_region(raster, mask, 0, 0.0, config=PlacementConfig(),
                        backing=backing, capture_sha256=CAPTURE,
                        directory=directory)


def test_the_second_call_reuses_the_files(fixture) -> None:
    """Rebuild-or-reuse: the same inputs are the same name, built once."""
    raster, mask, backing, directory = fixture
    config = PlacementConfig()
    first = prepared_region(raster, mask, 0, PITCH, config=config,
                            backing=backing, capture_sha256=CAPTURE,
                            directory=directory)
    assert first is not None
    files = sorted(path.name for path in directory.iterdir())
    assert len(files) == 3, files
    stamps = {path: path.stat().st_mtime_ns for path in directory.iterdir()}
    second = prepared_region(raster, mask, 0, PITCH, config=config,
                            backing=backing, capture_sha256=CAPTURE,
                            directory=directory)
    assert second is not None
    assert {path: path.stat().st_mtime_ns
            for path in directory.iterdir()} == stamps, "it rebuilt"
    assert _identical(first.filtered, second.filtered)


def test_a_different_input_is_a_different_name(fixture) -> None:
    """Every input the bytes depend on is in the digest, so nothing aliases."""
    raster, mask, backing, directory = fixture
    config = PlacementConfig()
    names: list[set[str]] = []
    variants = (
        dict(),
        dict(backing=backing + 1.0),
        dict(pitch_px=PITCH + 0.5),
        dict(capture_sha256="b" * 64),
        dict(config=PlacementConfig(aperture_cells=1.4)),
        dict(support_mask=_mask(step=16)),
    )
    for variant in variants:
        prepared_region(
            variant.get("raster", raster),
            variant.get("support_mask", mask), 0,
            float(variant.get("pitch_px", PITCH)),
            config=variant.get("config", config),
            backing=float(variant.get("backing", backing)),
            capture_sha256=str(variant.get("capture_sha256", CAPTURE)),
            directory=directory)
        names.append({path.name for path in directory.iterdir()})
    assert all(len(step) == 3 * (index + 1)
               for index, step in enumerate(names)), (
        "two different inputs shared a file name")


def test_a_torn_file_is_rebuilt_rather_than_read(fixture) -> None:
    """Size is the completeness check, and a short file fails it."""
    raster, mask, backing, directory = fixture
    config = PlacementConfig()
    first = prepared_region(raster, mask, 0, PITCH, config=config,
                            backing=backing, capture_sha256=CAPTURE,
                            directory=directory)
    assert first is not None
    victim = next(path for path in directory.iterdir()
                  if path.name.endswith(".filtered.f32"))
    victim.write_bytes(b"\0" * 16)
    second = prepared_region(raster, mask, 0, PITCH, config=config,
                             backing=backing, capture_sha256=CAPTURE,
                             directory=directory)
    assert second is not None
    reference = prepare_region(raster, mask, 0, PITCH, config=config,
                               backing=backing)
    assert reference is not None
    assert _identical(reference.filtered, second.filtered)


# --------------------------------------------- (4) the reuse-only door (H4)

def _open_only(fixture, *, config: PlacementConfig | None = None):
    """``open_prepared_region`` with the raster replaced by its SHAPE."""
    raster, mask, backing, directory = fixture
    return open_prepared_region(
        raster.shape, mask, 0, PITCH, config=config or PlacementConfig(),
        backing=backing, capture_sha256=CAPTURE, directory=directory)


def test_the_reuse_door_refuses_before_the_planes_exist(fixture) -> None:
    """It opens; it never builds. Nothing on disk means ``None``."""
    _raster, _mask, _backing, directory = fixture
    assert _open_only(fixture) is None
    assert not directory.exists(), "the reuse-only door built something"


def test_the_reuse_door_returns_the_built_planes_byte_for_byte(
        fixture) -> None:
    """The crash-cut resume's whole claim, at the seam that answers it.

    Same name, same bytes, same scalars — reached from the capture's
    durable ``shape_px`` and its recorded backing rather than from a
    raster, which is what a session with no ``--scan`` has.
    """
    reference, built = _both(fixture)
    reused = _open_only(fixture)
    assert reused is not None
    for name in ("image", "filtered", "support"):
        assert _identical(getattr(reused, name), getattr(reference, name))
    assert (reused.backing, reused.pitch_prior, reused.aperture_px) == (
        built.backing, built.pitch_prior, built.aperture_px)
    assert (reused.y0, reused.x0) == (built.y0, built.x0)


def test_the_reuse_door_refuses_a_torn_plane_rather_than_reading_it(
        fixture) -> None:
    """Size is still the completeness check — and here it cannot rebuild."""
    _both(fixture)
    _raster, _mask, _backing, directory = fixture
    victim = next(path for path in directory.iterdir()
                  if path.name.endswith(".filtered.f32"))
    victim.write_bytes(b"\0" * 16)
    assert _open_only(fixture) is None


def test_the_reuse_door_asks_a_different_config_a_different_name(
        fixture) -> None:
    """Every digest input still separates the names, from either door."""
    _both(fixture)
    assert _open_only(fixture, config=PlacementConfig(aperture_cells=1.4)) \
        is None
    assert _open_only(fixture) is not None


def test_the_directory_is_a_sibling_never_a_child() -> None:
    state = Path("/tmp/state-run")
    assert prepared_directory(state) == Path("/tmp/state-run.prepared")
    assert state not in prepared_directory(state).parents
