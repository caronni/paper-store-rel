"""The ladder's SUB-NATIVE rungs, on disk (H4-LANES stage 1).

What a footing raster has to be, and nothing about what reads one:

1. **it is the carried arm's own bytes**, reached through a file. The
   decimation is ``scale_space``'s, whose output is oracle-pinned, so the
   proof obligation here is that routing it through a memmap and a
   temp-file-and-replace changes nothing — asserted by byte-comparing the
   file against ``area_decimate`` of the same native array in memory;
2. **the name is a function of everything the bytes depend on**, so two
   different inputs never share one and equal inputs always do;
3. **the lifecycle is ``solve.prepared``'s**: reuse by name, size is the
   completeness check, and a ``.partial`` never stands under a live name;
4. **the geometry maps exactly**, and the NATIVE frame is a member of the
   type rather than an exception outside it — every ``FootingFrame``
   method must be the identity's own answer at native, because that is
   what makes "nothing that stands today is renamed or rebuilt" a
   structural property.

The fixture is a real acquisition (``synthetic_print`` at 600 dpi, c3)
because the ladder is a function of a declared dpi and a printed cell:
``auto_ppc_levels`` gives ``(2, 3)`` there, which is the smallest real
ladder that has a sub-native rung at all.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo2.capture.footing_raster import (FOOTING_SUFFIX, FootingFrame,
                                          footing_plan, footing_transform,
                                          open_footing_raster,
                                          write_footing_raster)
from holo2.capture.ingest import derive_footing_rasters, footing_raster_for
from holo2.capture.scale_space import area_decimate, auto_ppc_levels
from holo2.capture.scan import open_capture
from holo2.capture.survey import SupportMask

DPI = 600.0
#: The printed pitch these fixtures are written at: c3, an
#: exact 1/200 in (C3, RULINGS G4 — it was the dot count 3).
PITCH_IN = Fraction(1, 200)
#: c3 at 600 dpi: ppc 3 native, one sub-native rung at 2.
LADDER = (Fraction(2), Fraction(3))
CAPTURE = "c" * 64


@pytest.fixture
def raster(synthetic_print: Path):
    return open_capture(synthetic_print, DPI)


def _native(raster) -> np.ndarray:
    height, width = raster.shape
    return raster.crop_native(0, height, 0, width)


def _plan(raster, ppc: Fraction, directory: Path):
    return footing_plan(raster.source_sha256,
                        footing_transform(ppc, LADDER[-1]), raster.shape,
                        raster.native_dtype, directory=directory)


# ------------------------------------------------------------- (1) the bytes

def test_the_ladder_is_the_one_the_capture_declares(raster) -> None:
    """A guard on the fixture: the arm must really give a coarse rung."""
    assert auto_ppc_levels(DPI, PITCH_IN) == LADDER


def test_the_file_is_the_carried_arms_bytes(raster, tmp_path: Path) -> None:
    """THE CLAIM: the arm against itself, through a file.

    ``area_decimate`` in memory versus the streamed memmap the rung is,
    byte for byte. If routing the carried decimation through a file could
    change one value, every downstream lane would be reading pixels the
    oracle never pinned.
    """
    directory = tmp_path / "state.prepared"
    transform = footing_transform(LADDER[0], LADDER[-1])
    plan = _plan(raster, LADDER[0], directory)
    write_footing_raster(_native(raster), transform, plan)
    rung = open_footing_raster(plan, LADDER[0])
    assert rung is not None
    reference = area_decimate(_native(raster), transform)
    assert rung.shape == tuple(reference.shape)
    assert bytes(np.ascontiguousarray(rung.pixels).data) == bytes(
        np.ascontiguousarray(reference).data)
    assert rung.pixels.dtype == reference.dtype == raster.native_dtype


def test_a_crop_is_bounded_frozen_and_float32(raster, tmp_path: Path) -> None:
    """``Raster.crop_luma``'s contract, on a rung."""
    directory = tmp_path / "state.prepared"
    rung = footing_raster_for(
        raster, LADDER[0], LADDER[-1], capture_sha256=raster.source_sha256,
        shape_px=raster.shape, dtype=str(raster.native_dtype),
        directory=directory)
    assert rung is not None
    crop = rung.crop_luma(4, 9, 6, 11)
    assert crop.dtype == np.float32 and crop.shape == (5, 5)
    assert not crop.flags.writeable
    assert np.array_equal(crop, np.asarray(rung.pixels[4:9, 6:11], np.float32))
    height, width = rung.shape
    for box in ((0, height + 1, 0, 4), (0, 4, -1, 4), (5, 5, 0, 4)):
        with pytest.raises(ValueError):
            rung.crop_luma(*box)


def test_the_native_rung_is_never_derived_onto_disk(raster,
                                                    tmp_path: Path) -> None:
    """It IS the authenticated scan; a copy of it would be a second one."""
    identity = footing_transform(LADDER[-1], LADDER[-1])
    assert identity.is_identity
    with pytest.raises(ValueError):
        footing_plan(raster.source_sha256, identity, raster.shape,
                     raster.native_dtype, directory=tmp_path)
    derived = derive_footing_rasters(raster, LADDER,
                                     directory=tmp_path / "state.prepared")
    assert derived == (LADDER[0],), "the ladder minus its native rung"
    assert len(list((tmp_path / "state.prepared").iterdir())) == 1


# -------------------------------------------------------------- (2) the name

def test_a_different_input_is_a_different_name(raster, tmp_path: Path) -> None:
    """Everything the bytes are a function of separates the names."""
    directory = tmp_path / "state.prepared"
    base = _plan(raster, LADDER[0], directory)
    variants = (
        footing_plan("d" * 64, footing_transform(LADDER[0], LADDER[-1]),
                     raster.shape, raster.native_dtype, directory=directory),
        footing_plan(raster.source_sha256,
                     footing_transform(Fraction(1), LADDER[-1]),
                     raster.shape, raster.native_dtype, directory=directory),
        footing_plan(raster.source_sha256,
                     footing_transform(LADDER[0], LADDER[-1]),
                     (raster.shape[0] + 1, raster.shape[1]),
                     raster.native_dtype, directory=directory),
        footing_plan(raster.source_sha256,
                     footing_transform(LADDER[0], LADDER[-1]),
                     raster.shape, np.dtype(np.uint16), directory=directory),
    )
    assert len({plan.path for plan in (base, *variants)}) == 5
    assert base.path == _plan(raster, LADDER[0], directory).path
    assert base.path.name.endswith(FOOTING_SUFFIX)


# --------------------------------------------------------- (3) the lifecycle

def test_the_second_call_reuses_the_file(raster, tmp_path: Path) -> None:
    """Reuse by name: the same inputs are the same rung, derived once."""
    directory = tmp_path / "state.prepared"
    naming = dict(capture_sha256=raster.source_sha256, shape_px=raster.shape,
                  dtype=str(raster.native_dtype), directory=directory)
    first = footing_raster_for(raster, LADDER[0], LADDER[-1], **naming)
    assert first is not None
    plan = _plan(raster, LADDER[0], directory)
    stamp = plan.path.stat().st_mtime_ns
    second = footing_raster_for(raster, LADDER[0], LADDER[-1], **naming)
    assert second is not None
    assert plan.path.stat().st_mtime_ns == stamp, "it rebuilt"
    assert bytes(np.ascontiguousarray(second.pixels).data) == bytes(
        np.ascontiguousarray(first.pixels).data)


def test_a_partial_never_stands_under_a_live_name(raster,
                                                  tmp_path: Path) -> None:
    """The crash semantics: temp-file-and-replace, size is completeness."""
    directory = tmp_path / "state.prepared"
    plan = _plan(raster, LADDER[0], directory)
    directory.mkdir(parents=True)
    partial = plan.path.with_name(plan.path.name + ".partial")
    partial.write_bytes(b"\0" * 16)
    assert not plan.stands(), "a .partial is not the rung"
    assert open_footing_raster(plan, LADDER[0]) is None
    # A torn file UNDER the live name fails the size check too, and the
    # deriving door rebuilds it rather than mapping it.
    plan.path.write_bytes(b"\0" * 16)
    assert not plan.stands()
    rebuilt = footing_raster_for(
        raster, LADDER[0], LADDER[-1], capture_sha256=raster.source_sha256,
        shape_px=raster.shape, dtype=str(raster.native_dtype),
        directory=directory)
    assert rebuilt is not None and plan.stands()
    assert not partial.exists() or partial.stat().st_size == 16


def test_the_reuse_only_door_opens_and_never_builds(raster,
                                                    tmp_path: Path) -> None:
    """``raster=None``: a session holding no pixels reads what stands."""
    directory = tmp_path / "state.prepared"
    naming = dict(capture_sha256=raster.source_sha256, shape_px=raster.shape,
                  dtype=str(raster.native_dtype), directory=directory)
    assert footing_raster_for(None, LADDER[0], LADDER[-1], **naming) is None
    assert not directory.exists(), "the reuse-only door built something"
    assert footing_raster_for(raster, LADDER[0], LADDER[-1], **naming)
    assert footing_raster_for(None, LADDER[0], LADDER[-1], **naming)


# ------------------------------------------------------------ (4) the frame

def _mask() -> SupportMask:
    cells = np.zeros((6, 6), bool)
    cells[1:5, 1:5] = True
    cells[3, 3] = False
    return SupportMask(origin_yx=(12, 18), step_px=12, cells=cells,
                       extent_px=(72, 72))


def test_the_native_frame_is_the_identity_everywhere() -> None:
    """Native is a MEMBER of the type, so nothing it touches can move."""
    frame = FootingFrame.native((600, 600))
    mask = _mask()
    assert frame.is_native and frame.shape_px == (600, 600)
    assert frame.pitch_px(6.25) == 6.25
    assert frame.extent((10, 20, 300, 400)) == (10, 20, 300, 400)
    assert frame.digest_line() is None, (
        "a native digest line would rename every plane that stands")
    assert np.array_equal(frame.support_crop(mask, 0, 96, 0, 96),
                          mask.rasterize_crop(0, 96, 0, 96))


def test_a_coarse_extent_keeps_only_whole_rung_pixels() -> None:
    """``scale_space``'s trailing-pixel rule, run backwards."""
    frame = FootingFrame.of(Fraction(2), Fraction(6), (600, 600))
    assert frame.shape_px == (200, 200)
    # scale 3: [10, 300) -> first whole pixel ceil(10/3) = 4, one past the
    # last is floor(300/3) = 100.
    assert frame.extent((10, 12, 300, 303)) == (4, 4, 100, 101)
    # Too coarse to hold one complete pixel of the region: refused, the
    # same shape of refusal ``region_extent`` makes for a bbox off the
    # raster.
    assert frame.extent((10, 10, 11, 300)) is None


def test_a_coarse_support_asks_the_centre_question() -> None:
    """The rule ``plans.sample_support`` already applies one level up.

    Rung pixel ``j`` covers native ``[3j, 3j+3)`` at scale 3, so its
    centre is native ``3j + 1`` — asserted against the native mask
    directly rather than against a second implementation of the same
    arithmetic.
    """
    frame = FootingFrame.of(Fraction(2), Fraction(6), (600, 600))
    mask = _mask()
    crop = frame.support_crop(mask, 0, 32, 0, 32)
    assert crop.shape == (32, 32)
    native = mask.rasterize_crop(0, 96, 0, 96)
    expected = native[1::3, 1::3][:32, :32]
    assert np.array_equal(crop, expected)
    # And a box entirely off the support reads false rather than raising.
    assert not frame.support_crop(mask, 60, 70, 60, 70).any()


def test_the_pitch_scales_with_the_rung() -> None:
    """A cell is the same paper at every rung; the pixels over it are not."""
    assert FootingFrame.of(Fraction(2), Fraction(6),
                           (600, 600)).pitch_px(6.0) == 2.0
    assert FootingFrame.of(Fraction(3), Fraction(6),
                           (600, 600)).pitch_px(6.0) == 3.0
    assert FootingFrame.of(Fraction(2), Fraction(2),
                           (600, 600)).is_native
