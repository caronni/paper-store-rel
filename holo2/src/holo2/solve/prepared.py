"""The prepared plane: one region's pixels, filled and filtered ONCE.

H4 W1a, and the answer to a measured failure. ``pose_fit.prepare_region``
is v1's preparation — the region's bbox as float32 native luma with every
unsupported pixel filled to the platen backing, that same image under one
box aperture, and the support mask as float32 — and v1 built it ONCE per
region and then looped that region's windows inside it. holo2 composes
one fire per (window, stage), so calling it from a worker rebuilt all
three full-resolution arrays PER FIRE: on the real sheet's single
4800-dpi region that is ~2 Gpx, i.e. ~8 GB per array, and workers 4/8
were SIGKILLed (exit 137) on a 64 GB machine while the serial arm paid
the same arithmetic on every window.

So the preparation moves back to where v1 had it — once per (capture,
region) — and the thing that makes that safe under a worker pool is that
it is **immutable and out of the heap**: each of the three arrays is
built STREAMING (row bands, never a second full-size temporary) into a
file, and every fire then reads the SAME read-only ``np.memmap``. A fire
copies nothing, fills nothing and filters nothing; it interpolates
through coordinates, and the operating system pages in the neighbourhood
it actually touches. Peak resident memory becomes a function of the
window a fire is reading, not of the pool width, and the pages are
file-backed, so they are evictable rather than fatal.

**The values are v1's, byte for byte.** Two rules make the streaming
build identical to the whole-region one rather than nearly identical:

* the fill and the support rasterization are POINTWISE, so a row band of
  either is the same bytes as that slice of the whole;
* the aperture is not pointwise, so each band is filtered with a halo of
  ``aperture // 2`` rows above and below (scipy's box footprint is
  ``[i - k//2, i + (k-1)//2]``, so half the box is the deeper side) and
  only the interior is kept. At the region's own first and last row there
  is no halo and ``mode="nearest"`` extends exactly as it does for the
  whole array. ``uniform_filter1d`` accumulates in ``double`` over a
  sliding window whose terms are float32 luma at one scale, so the sums
  are exact and the band's interior is bit-identical, not
  approximately-identical — pinned by a test that byte-compares the whole
  built plane against ``prepare_region``'s output.

**Lifecycle.** The files live in ``<state-dir>.prepared/``, a SIBLING of
the state directory and never a child — the same discipline (and the same
reason) as ``<state-dir>.diag``: the store opens strictly, and derived
scribbles must be somewhere its open cannot see. Nothing here is durable
state: no journal, no blob sidecar, no record. A file is named by a
digest of everything its content is a function of — the capture, the
region's clipped bbox, the support mask's own bytes, the backing scalar,
the pitch and the aperture — so a reopened session REUSES what is still
valid and rebuilds what is not, and a changed input can only ever produce
a different name. Builds are temp-file-and-replace, so a crash leaves a
``.partial`` behind and never a short file under a live name; concurrent
builders are excluded by the store's own single-writer lock (F-19), which
is what makes one directory per state directory safe.

Deleting the directory is always safe and costs one rebuild. It is NOT
free in space: three float32 planes of the region, i.e. 12 bytes per
region pixel (~1.6 GB for a 1200-dpi A4 sheet, ~24 GB for the 4800-dpi
real sheet).

**REUSE WITHOUT A RASTER** (2026-08-17). Everything a name is a function
of is durable: the capture sha, the support mask and its grid, the pitch,
the aperture — and, since ``CaptureRecord`` v3, the backing scalar, which
was the one input a session used to compute from the raster's own borders
and record nowhere. So :func:`open_prepared_region` asks the question
:func:`prepared_region` asks first and then stops: are the three planes
this name stands for already complete on disk? It takes the capture's
durable ``shape_px`` instead of a ``Raster``, builds nothing, and answers
``None`` where it would have had to. That is what lets a crash-cut resume
re-earn its placement tail from the surviving prepared planes with no
scan declared at all — the derived pixels ARE on disk, they simply had no
name a pixel-free session could pronounce.

Reading a size-checked file that this session did not write is safe for a
reason outside this module: a re-earn re-executes recorded batches and
verifies each against the id the journal holds for that position
(``core.journal``), so a stale or corrupt plane produces a divergent id
and refuses loudly. Wrongness cannot slip through; the worst a bad file
can do is stop the resume.

**THE FOOTING AXIS** (H4-LANES stage 1, 2026-08-17). A region is a
CAPTURE fact and a rung is a way of sampling it, so one region has one
prepared plane PER FOOTING: same survey, same backing, same aperture in
cells — different pixels, at a pitch that scales with the rung. All of
that arrives as one value, ``capture.FootingFrame``, which carries the
exact rational transform and the native shape and answers the three
questions this module has to ask across the frame boundary (the clipped
extent, the support over a band, and the line the digest needs).

The NATIVE rung is a member of that type and not an exception to it, and
every ``FootingFrame`` method delegates to the untouched native path when
it is the identity — including :meth:`FootingFrame.digest_line`, which
contributes NOTHING at native. So the names and the bytes of every plane
that stands today are the names and bytes they were: the byte-compare pin
against ``prepare_region`` runs on the same call it always did, and a
session that never leaves the finest rung cannot tell this change
happened.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
from scipy import ndimage

from ..capture import FootingFrame, FootingRaster, Raster, SupportMask
from .place_model import PlacementConfig
from .pose_fit import PreparedRegion

#: What a preparation reads its pixels through: the authenticated native
#: raster, or one derived rung of it. Both answer ``shape`` and a bounded
#: read-only float32 ``crop_luma``, which is the whole of what the
#: streaming build below asks of a capture's pixels.
PixelSource = Raster | FootingRaster

#: The sibling directory's suffix (``diag``'s convention, same reason).
PREPARED_DIR_SUFFIX = ".prepared"
#: Bumped whenever the bytes a name stands for would change.
PREPARED_FORMAT = "holo2-prepared-1"
#: Streaming band size. Big enough that the per-band overhead disappears,
#: small enough that the build's own peak is a rounding error next to the
#: plane it is writing.
BAND_BYTES = 32 << 20
#: The three arrays a prepared region IS (``PreparedRegion`` field order).
PLANES = ("filled", "filtered", "support")


def prepared_directory(state_dir: Path) -> Path:
    """``<state-dir>.prepared`` — a sibling, never a child (module note)."""
    state_dir = Path(state_dir)
    return state_dir.parent / (state_dir.name + PREPARED_DIR_SUFFIX)


def prepared_region(
    raster: PixelSource,
    support_mask: SupportMask,
    region_index: int,
    pitch_px: float,
    *,
    config: PlacementConfig,
    backing: float,
    capture_sha256: str,
    directory: Path,
    frame: FootingFrame | None = None,
) -> PreparedRegion | None:
    """``pose_fit.prepare_region``'s answer, built once and memory-mapped.

    Same parameters, same refusals (a bbox that has left the raster, and
    a bbox holding no support), same values — the only difference is
    where the pixels live. ``capture_sha256`` and ``directory`` are what
    naming needs: the caller knows both, and deriving either here would
    mean this module guessing at facts its producer already holds.

    ``frame`` names the RUNG ``raster`` is (module note): its transform
    maps the survey's native geometry into these pixels, and ``pitch_px``
    is already denominated in them (``FootingFrame.pitch_px``). Omitting
    it means the native rung, which is what every caller that does not
    name a lane means and what every caller meant before there were
    lanes.
    """
    frame = frame or FootingFrame.native(raster.shape)
    plan = _plan(frame, support_mask, pitch_px, config=config,
                 backing=backing, capture_sha256=capture_sha256,
                 directory=directory)
    if plan is None:
        return None
    extent, shape, aperture, paths = plan
    if not all(_is_complete(paths[name], shape) for name in PLANES):
        _build(raster, support_mask, extent, paths, frame=frame,
               backing=backing, aperture=aperture)
    return _mapped(plan, region_index, backing=backing, pitch_px=pitch_px)


def open_prepared_region(
    shape_px: tuple[int, int],
    support_mask: SupportMask,
    region_index: int,
    pitch_px: float,
    *,
    config: PlacementConfig,
    backing: float,
    capture_sha256: str,
    directory: Path,
    frame: FootingFrame | None = None,
) -> PreparedRegion | None:
    """REUSE ONLY: the same planes, opened by name, with no raster at all.

    :func:`prepared_region` minus the build. Every argument is durable —
    ``shape_px`` is ``CaptureRecord.shape_px``, ``backing`` is that
    record's ``platen_backing``, and the mask, pitch and aperture come off
    the region and the placement policy — so a session holding no pixels
    can still pronounce the name and, if the three planes are complete
    under it, read them.

    ``None`` means "not available here": the same two geometric refusals
    :func:`region_extent` makes, or planes that are absent, short or torn.
    It is never a claim that the region is unpreparable — only that THIS
    session cannot prepare it without the file (module note).

    ``shape_px`` is the NATIVE shape at every rung: it is the capture's
    own durable ``shape_px``, and a ``frame`` derives its rung's shape
    from it rather than being told a second, checkable version of the
    same fact.
    """
    plan = _plan(frame or FootingFrame.native(shape_px), support_mask,
                 pitch_px, config=config, backing=backing,
                 capture_sha256=capture_sha256, directory=directory)
    if plan is None:
        return None
    _extent, shape, _aperture, paths = plan
    if not all(_is_complete(paths[name], shape) for name in PLANES):
        return None
    return _mapped(plan, region_index, backing=backing, pitch_px=pitch_px)


def region_extent(shape_px: tuple[int, int], support_mask: SupportMask,
                  pitch_px: float) -> tuple[int, int, int, int] | None:
    """The region's clipped bbox, or ``None`` where v1 refuses it.

    ``prepare_region``'s two refusals, asked without materializing
    anything. The support question is answered on the survey's own block
    grid, which is the same predicate as ``rasterize_crop(...).any()``
    over the clipped bbox because the mask is block-constant on that grid
    and the bbox starts at its origin.

    It takes the raster's SHAPE rather than the raster (2026-08-17): the
    clip is the only thing the pixels were ever consulted for here, and
    the shape is durable (``CaptureRecord.shape_px``), which is what lets
    :func:`open_prepared_region` ask the same question with no file.
    """
    if not np.isfinite(pitch_px) or pitch_px <= 0:
        raise ValueError("pitch_px must be finite and positive")
    y0, x0, height, width = support_mask.bbox
    y1 = min(int(shape_px[0]), y0 + height)
    x1 = min(int(shape_px[1]), x0 + width)
    if y1 <= y0 or x1 <= x0:
        return None
    step = support_mask.step_px
    rows = (y1 - 1 - y0) // step + 1
    cols = (x1 - 1 - x0) // step + 1
    if not support_mask.cells[:rows, :cols].any():
        return None
    return int(y0), int(x0), int(y1), int(x1)


# ------------------------------------------------------------ the identity

#: What a name resolves to: the clipped extent, the plane shape, the
#: aperture in pixels, and the three paths.
_Plan = tuple[tuple[int, int, int, int], tuple[int, int], int, dict[str, Path]]


def _plan(frame: FootingFrame, support_mask: SupportMask,
          pitch_px: float, *, config: PlacementConfig, backing: float,
          capture_sha256: str, directory: Path) -> _Plan | None:
    """Everything both doors need before they diverge on "build or not".

    Pure arithmetic over durable values, touching no pixel and no file —
    which is the whole point: the build path and the reuse-only path must
    compute the SAME name, and they do because there is one expression
    for it.

    The extent is computed NATIVE and then mapped into the rung, in that
    order, because the survey's two refusals are statements about the
    capture (a bbox off the raster, a bbox holding no support) and must
    read the same at every rung. What a coarse rung can add is a third,
    its own: too few pixels to hold one complete cell of the region
    (``FootingFrame.extent``).
    """
    extent = region_extent(frame.native_shape_px, support_mask, pitch_px)
    if extent is None:
        return None
    extent = frame.extent(extent)
    if extent is None:
        return None
    y0, x0, y1, x1 = extent
    aperture = max(1, int(round(config.aperture_cells * pitch_px)))
    digest = _digest(capture_sha256, support_mask, extent, frame=frame,
                     backing=backing, pitch_px=pitch_px, aperture=aperture)
    paths = {name: Path(directory) / f"{digest}.{name}.f32"
             for name in PLANES}
    return extent, (y1 - y0, x1 - x0), aperture, paths


def _mapped(plan: _Plan, region_index: int, *, backing: float,
            pitch_px: float) -> PreparedRegion:
    """The three complete planes of ``plan``, mapped read-only."""
    (y0, x0, _y1, _x1), shape, aperture, paths = plan
    planes = {name: _open_read_only(paths[name], shape) for name in PLANES}
    return PreparedRegion(
        region_index, int(y0), int(x0), planes["filled"], planes["filtered"],
        planes["support"], float(backing), float(pitch_px), aperture,
    )


def _digest(capture_sha256: str, support_mask: SupportMask,
            extent: tuple[int, int, int, int], *, frame: FootingFrame,
            backing: float, pitch_px: float, aperture: int) -> str:
    """Everything the bytes are a function of, hashed into their name.

    The mask's own cells are in it because a region KEY names the support
    grid's origin, step and extent but not its contents (``region_key``),
    and two surveys can disagree about which of those cells are true.
    The two floats go in as ``float.hex()``: the exact value, not a
    rounded rendering of it.

    THE FOOTING LINE IS APPENDED, not interleaved, and it is ABSENT at
    the native rung. Two rungs of one region already differ in this
    material twice over — their extents are in different frames and their
    pitches are scaled — so the line is not what keeps them apart; what
    it does is state the dependency the bytes actually have (a rung's
    pixels ARE a function of its scale) instead of leaving it implied by
    two derived numbers. Absent at native means every plane that stands
    today keeps its name, which is a pinned property and not a courtesy.
    """
    material = [
        PREPARED_FORMAT,
        f"capture={capture_sha256}",
        "extent={},{},{},{}".format(*extent),
        f"step={int(support_mask.step_px)}",
        f"mask={_mask_digest(support_mask)}",
        f"backing={float(backing).hex()}",
        f"pitch={float(pitch_px).hex()}",
        f"aperture={int(aperture)}",
    ]
    footing = frame.digest_line()
    if footing is not None:
        material.append(footing)
    return hashlib.sha256("\n".join(material).encode("utf-8")).hexdigest()[:32]


def _mask_digest(support_mask: SupportMask) -> str:
    cells = np.ascontiguousarray(support_mask.cells, dtype=bool)
    digest = hashlib.sha256(cells.tobytes())
    digest.update(b"|%d,%d" % (cells.shape[0], cells.shape[1]))
    return digest.hexdigest()


def _is_complete(path: Path, shape: tuple[int, int]) -> bool:
    """A file this size under this name is the plane the digest names."""
    try:
        return path.stat().st_size == 4 * shape[0] * shape[1]
    except OSError:
        return False


def _open_read_only(path: Path, shape: tuple[int, int]) -> np.ndarray:
    """One plane, mapped read-only: a fire reads it and nothing writes it."""
    mapped = np.memmap(path, dtype=np.float32, mode="r", shape=shape)
    return np.asarray(mapped)


# ------------------------------------------------------------- the build

def _build(raster: PixelSource, support_mask: SupportMask,
           extent: tuple[int, int, int, int], paths: dict[str, Path], *,
           frame: FootingFrame, backing: float, aperture: int) -> None:
    """Write the three planes, streaming, then publish them atomically.

    ``extent`` and every read below are in ``frame``'s pixels; the mask
    is the survey's, in native ones, so the support goes through the
    frame (which IS ``SupportMask.rasterize_crop`` at the native rung).
    The two rules that make the streaming build byte-identical to a
    whole-region one are untouched by that: the fill and the support are
    still POINTWISE, so a band of either is the same bytes as that slice
    of the whole, and the aperture still carries its halo.
    """
    y0, x0, y1, x1 = extent
    height, width = y1 - y0, x1 - x0
    directory = paths[PLANES[0]].parent
    directory.mkdir(parents=True, exist_ok=True)
    temporary = {name: paths[name].with_name(paths[name].name + ".partial")
                 for name in PLANES}
    band = max(1, BAND_BYTES // (width * 4))
    filled = np.memmap(temporary["filled"], dtype=np.float32, mode="w+",
                       shape=(height, width))
    support = np.memmap(temporary["support"], dtype=np.float32, mode="w+",
                        shape=(height, width))
    try:
        for row0, row1 in _bands(height, band):
            pixels = raster.crop_luma(y0 + row0, y0 + row1, x0, x1)
            covered = frame.support_crop(
                support_mask, y0 + row0, y0 + row1, x0, x1)
            filled[row0:row1] = np.where(
                covered, pixels, np.float32(backing)
            ).astype(np.float32, copy=False)
            support[row0:row1] = covered.astype(np.float32)
        filled.flush()
        support.flush()
        _filter_into(temporary["filtered"], filled, band=band,
                     aperture=aperture)
    finally:
        del filled, support
    for name in PLANES:
        os.replace(temporary[name], paths[name])


def _filter_into(path: Path, filled: np.ndarray, *, band: int,
                 aperture: int) -> None:
    """The single box aperture, band by band, with the filter's own halo."""
    height, width = int(filled.shape[0]), int(filled.shape[1])
    halo = aperture // 2
    filtered = np.memmap(path, dtype=np.float32, mode="w+",
                         shape=(height, width))
    try:
        for row0, row1 in _bands(height, band):
            low = max(0, row0 - halo)
            high = min(height, row1 + halo)
            # Exactly one aperture operation per pixel.  All phase and
            # payload-site reads address this array; no rotated or
            # decimated working raster is ever built.
            window = np.asarray(ndimage.uniform_filter(
                np.asarray(filled[low:high]), size=aperture, mode="nearest"))
            filtered[row0:row1] = window[row0 - low:row1 - low]
        filtered.flush()
    finally:
        del filtered


def _bands(height: int, band: int) -> list[tuple[int, int]]:
    return [(row0, min(height, row0 + band))
            for row0 in range(0, height, band)]


__all__ = [
    "BAND_BYTES", "PLANES", "PREPARED_DIR_SUFFIX", "PREPARED_FORMAT",
    "PixelSource", "open_prepared_region", "prepared_directory",
    "prepared_region", "region_extent",
]
