"""One region, one prepared plane PER RUNG (H4-LANES stage 1).

``solve/prepared.py`` gained a footing axis, and this file pins the two
halves of that which could go wrong in opposite directions:

* **the native rung did not move.** Not "produces equal bytes" — that is
  ``test_prepared``'s standing claim and it still runs untouched — but
  that the NAME is the same string it was before the axis existed, so a
  ``<state-dir>.prepared`` sibling written by yesterday's code is reused
  by today's rather than silently rebuilt beside itself. It is pinned as
  a literal, because "unchanged" is not a property you can assert against
  the code that changed;
* **a coarse rung is really prepared from ITS OWN pixels**, at its own
  pitch, over its own support — asserted against a whole-region
  reference built in this file from the carried decimation, so the
  streaming build's band halo is under test at a coarse rung too and not
  only at native.

The plane's own half is here as well (the memo and the two doors are
keyed by rung), and the fd budget's ladder arithmetic, because that is
the number the lanes made countable.

The fixture is ``test_prepared``'s, deliberately: the golden below is a
digest of that page, that mask and that pitch, so the two files pin the
same bytes from the two sides.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from scipy import ndimage

from holo2.capture import FootingFrame
from holo2.capture.ingest import ingest_capture
from holo2.capture.scale_space import area_decimate
from holo2.capture.scan import open_capture
from holo2.core.commit import CommitEngine
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.solve import prepared as prepared_module
from holo2.solve.place_model import PlacementConfig
from holo2.solve.plane import open_plane
from holo2.solve.plane_views import (FD_FIXED, FD_PER_CAPTURE, FD_PER_REGION,
                                     fd_budget)
from holo2.solve.pose_fit import platen_backing
from holo2.solve.prepared import prepared_region
from holo2.format.registry_rows import format_row
from conftest import make_session, registry
from test_prepared import CAPTURE, PITCH, _identical, _mask, _page

#: THE NATIVE NAME, frozen. Every prepared plane that stands in any
#: ``<state-dir>.prepared`` sibling written before the footing axis
#: existed is named by this expression, so a change here is a change that
#: silently orphans derived pixels and costs a full rebuild — deliberate
#: when ``PREPARED_FORMAT`` moves, a bug otherwise. It is the digest of
#: ``test_prepared``'s page, mask, backing, pitch and aperture, and it was
#: taken by running the PRE-CHANGE ``_digest`` expression (``git show
#: HEAD``, transcribed and evaluated on this fixture) rather than by
#: recording what the new code happens to produce — a golden read off the
#: code it is meant to constrain constrains nothing.
NATIVE_DIGEST = "bb30ae194ba747f6ab0b81019dc10b02"

#: The rung this file prepares at: half the native sampling, so the
#: transform's scale is exactly 2 and every mapping below is checkable by
#: hand.
COARSE_PPC = Fraction(3)
NATIVE_PPC = Fraction(6)

DPI = 600.0
ROW = format_row("c3-k-r0550", (2, 2), 1)


@pytest.fixture
def fixture(tmp_path: Path):
    """``test_prepared``'s fixture, plus the two frames over it."""
    raster = open_capture(_page(), 600.0)
    mask = _mask()
    return raster, mask, platen_backing(raster), tmp_path / "state.prepared"


def _frames(raster):
    return (FootingFrame.native(raster.shape),
            FootingFrame.of(COARSE_PPC, NATIVE_PPC, raster.shape))


def _names(directory: Path) -> set[str]:
    return {path.name.split(".")[0] for path in directory.iterdir()}


# ------------------------------------------------- (1) the native rung stands

def test_the_native_name_is_the_one_that_already_stands(fixture) -> None:
    """The golden: naming must be BACKWARD-compatible, not merely stable."""
    raster, mask, backing, directory = fixture
    built = prepared_region(raster, mask, 0, PITCH, config=PlacementConfig(),
                            backing=backing, capture_sha256=CAPTURE,
                            directory=directory)
    assert built is not None
    assert _names(directory) == {NATIVE_DIGEST}, (
        "the native prepared plane was renamed; every derived pixel on "
        "every machine is orphaned by this")


def test_naming_the_native_frame_names_the_same_files(fixture) -> None:
    """Native is a MEMBER of the frame type, not an exception outside it."""
    raster, mask, backing, directory = fixture
    native, _coarse = _frames(raster)
    common = dict(config=PlacementConfig(), backing=backing,
                  capture_sha256=CAPTURE, directory=directory)
    implicit = prepared_region(raster, mask, 0, PITCH, **common)
    explicit = prepared_region(raster, mask, 0, PITCH, frame=native, **common)
    assert implicit is not None and explicit is not None
    assert _names(directory) == {NATIVE_DIGEST}, "two names for one rung"
    assert _identical(implicit.filtered, explicit.filtered)


# --------------------------------------------------- (2) two rungs, two files

def test_two_rungs_of_one_region_name_two_files(fixture) -> None:
    """The footing axis, at the seam it exists in: the name."""
    raster, mask, backing, directory = fixture
    native, coarse = _frames(raster)
    common = dict(config=PlacementConfig(), backing=backing,
                  capture_sha256=CAPTURE, directory=directory)
    height, width = raster.shape
    fine = prepared_region(raster, mask, 0, PITCH, frame=native, **common)
    rung = area_decimate(raster.crop_native(0, height, 0, width),
                         coarse.transform)
    lane = prepared_region(_Rung(rung), mask, 0, coarse.pitch_px(PITCH),
                           frame=coarse, **common)
    assert fine is not None and lane is not None
    names = _names(directory)
    assert len(names) == 2 and NATIVE_DIGEST in names
    assert lane.image.shape != fine.image.shape
    assert (lane.y0, lane.x0) != (fine.y0, fine.x0)
    assert lane.pitch_prior == PITCH / 2 == coarse.pitch_px(PITCH)


class _Rung:
    """The two members ``prepared`` asks a capture's pixels for.

    ``capture.FootingRaster`` in miniature, so this file can prepare from
    an in-memory decimation without going through a state directory —
    the file-backed path is ``test_footing_raster``'s claim, and the one
    under test here is the PREPARATION.
    """

    def __init__(self, pixels: np.ndarray) -> None:
        self.pixels = pixels
        self.shape = (int(pixels.shape[0]), int(pixels.shape[1]))

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        return np.array(self.pixels[r0:r1, c0:c1], np.float32, order="C")


def test_a_coarse_plane_is_its_own_rungs_whole_region_preparation(
        fixture, monkeypatch) -> None:
    """THE CLAIM: the streamed coarse plane IS the whole-region one.

    ``prepare_region`` cannot be the oracle here — it rasterizes support
    in NATIVE coordinates and has no frame to ask — so the reference is
    built in one piece from the same three ingredients the streaming
    build uses band by band. The band is forced small enough that every
    row of the region sits near a band edge, which is what puts the
    aperture halo under test at this rung rather than at native.
    """
    raster, mask, backing, directory = fixture
    _native, coarse = _frames(raster)
    height, width = raster.shape
    rung = area_decimate(raster.crop_native(0, height, 0, width),
                         coarse.transform)
    pitch = coarse.pitch_px(PITCH)
    config = PlacementConfig()
    monkeypatch.setattr(prepared_module, "BAND_BYTES",
                        3 * int(rung.shape[1]) * 4)
    built = prepared_region(_Rung(rung), mask, 0, pitch, frame=coarse,
                            config=config, backing=backing,
                            capture_sha256=CAPTURE, directory=directory)
    assert built is not None

    extent = coarse.extent(prepared_module.region_extent(
        raster.shape, mask, PITCH))
    assert extent is not None
    y0, x0, y1, x1 = extent
    aperture = max(1, int(round(config.aperture_cells * pitch)))
    covered = coarse.support_crop(mask, y0, y1, x0, x1)
    pixels = np.array(rung[y0:y1, x0:x1], np.float32)
    image = np.where(covered, pixels, np.float32(backing)).astype(np.float32)
    filtered = np.asarray(ndimage.uniform_filter(
        image, size=aperture, mode="nearest"))
    assert (built.y0, built.x0, built.aperture_px) == (y0, x0, aperture)
    assert _identical(built.image, image)
    assert _identical(built.support, covered.astype(np.float32))
    assert _identical(built.filtered, filtered), (
        "the coarse rung's band halo is not the whole-region aperture")


# ------------------------------------------------------- (3) the plane's memo

@pytest.fixture
def plane(tmp_path: Path, synthetic_print: Path):
    """A real plane over one ingested capture, rungs and all."""
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    ingest_capture(engine, synthetic_print, DPI, ROW.pitch_in,
                   directory=None)
    yield open_plane(store, engine, ROW, ((synthetic_print, DPI),))
    store.close()


def test_the_plane_prepares_each_rung_from_its_own_pixels(plane) -> None:
    """The memo is keyed by rung, and a coarse rung derives its raster.

    The fixture ingests with NO directory, so no rung is on disk when
    this starts: preparing the coarse lane has to derive one, which is
    the door a session whose ``.prepared`` sibling was deleted goes
    through.
    """
    config = PlacementConfig()
    region = plane.captures[0].regions[0]
    footings = plane.captures[0].footings
    assert len(footings) >= 2, "the fixture must have a coarse rung"
    coarse, native = footings[0].footing_id, footings[-1].footing_id

    fine = plane.prepared_region(region, config=config)
    assert fine is not None
    assert plane.prepared_region(region, config=config,
                                 footing_id=native) is fine, (
        "the implicit rung is not the capture's native one")
    lane = plane.prepared_region(region, config=config, footing_id=coarse)
    assert lane is not None and lane is not fine
    assert plane.prepared_region(region, config=config,
                                 footing_id=coarse) is lane, "it rebuilt"
    assert lane.image.shape != fine.image.shape
    assert lane.pitch_prior < fine.pitch_prior
    # Three planes per rung, plus the one rung raster the coarse lane
    # had to derive to be prepared at all.
    directory = plane.derived_directory()
    assert len(list(directory.iterdir())) == 7
    assert plane.footing_frame(native).is_native
    assert not plane.footing_frame(coarse).is_native


def test_a_rung_this_plane_does_not_hold_prepares_nothing(plane) -> None:
    config = PlacementConfig()
    region = plane.captures[0].regions[0]
    assert plane.prepared_region(region, config=config,
                                 footing_id="nope:1/1") is None
    assert plane.footing_frame("nope:1/1") is None
    assert not plane.has_footing_pixels("nope:1/1")


def test_the_provider_binds_the_fire_to_this_lineages_derived_pixels(
        tmp_path: Path, synthetic_print: Path) -> None:
    """The DECODE path, not the direct one: provider -> worker -> rung.

    ``capture`` knows nothing about state directories, so the fire is
    handed one at binding time by the provider, which has the plane. This
    is the wiring that makes an ordinary run emit rungs at all — the
    direct ``ingest_capture`` door above is the unit lane's — and it is
    asserted by firing the bound worker and finding the file, rather than
    by reading the attribute and hoping.
    """
    from holo2.core.work import ExpansionRequest, ProgressSink
    from holo2.solve import RealIngestProvider

    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    try:
        scans = ((synthetic_print, DPI),)
        plane = open_plane(store, engine, ROW, scans)
        provider = RealIngestProvider(ROW, scans)
        (descriptor,) = provider.expand(
            plane, ExpansionRequest(entry="ingest/all/always"))
        worker = provider.worker(plane, descriptor)
        assert worker.directory == plane.derived_directory()
        worker.run(plane, (), ProgressSink("ingest"))
        rungs = [path for path in plane.derived_directory().iterdir()
                 if path.name.endswith(".footing.raw")]
        assert len(rungs) == 1, (
            "an ordinary decode's ingest fire emitted no sub-native rung")
    finally:
        store.close()


def test_the_ingest_fire_leaves_the_rungs_where_the_plane_finds_them(
        tmp_path: Path, synthetic_print: Path) -> None:
    """The producer/consumer seam, end to end and without a scheduler."""
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    directory = tmp_path / "state.prepared"
    try:
        ingest_capture(engine, synthetic_print, DPI, ROW.pitch_in,
                       directory=directory)
        assert len(list(directory.iterdir())) == 1, "one sub-native rung"
        plane = open_plane(store, engine, ROW, ((synthetic_print, DPI),))
        coarse = plane.captures[0].footings[0].footing_id
        assert plane.has_footing_pixels(coarse)
        lane = plane.prepared_region(plane.captures[0].regions[0],
                                     config=PlacementConfig(),
                                     footing_id=coarse)
        assert lane is not None
        # The fire's rung was REUSED, not re-derived beside itself.
        rungs = [path for path in directory.iterdir()
                 if path.name.endswith(".footing.raw")]
        assert len(rungs) == 1
    finally:
        store.close()


# ------------------------------------------------------------ (4) the budget

def test_the_fd_budget_covers_the_longest_ladder() -> None:
    """The arithmetic the lanes made countable (H4-LANES stage 1).

    The longest ladder a capture can declare is c3 at 4800 dpi — ppc 2,
    4, 8, 12, 24 — so a capture maps its scan plus four rungs, and a
    region maps three prepared planes per rung. Both terms must cover
    that, because the failure they exist to prevent is Errno 24 at hour N.
    """
    rungs = 5
    assert FD_PER_CAPTURE >= rungs, "a capture maps its scan plus its rungs"
    assert FD_PER_REGION >= 3 * rungs, "three planes per (region, rung)"
    # Nine platens of ~20 regions each, at full ladder: mappings fit.
    demo = fd_budget(9, 180)
    assert demo >= FD_FIXED + 9 * rungs + 180 * 3 * rungs
