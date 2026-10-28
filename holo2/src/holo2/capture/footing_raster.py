"""The footing raster: one capture's SUB-NATIVE rungs, derived onto disk.

H4-LANES stage 1. holo2 has carried the identity half of v1's cascade
since day one — every capture declares the same ``auto_ppc_levels``
ladder, and every evidence key names its footing — while the READING half
was collapsed to one lane. Lifting that collapse needs the coarse rungs
to EXIST as pixels somewhere, and this module is where they live.

**Native to decimated, always** (H4-LANES ruling 2). Every rung is an
exact-rational area average taken DIRECTLY from the authenticated native
raster, never from another rung: that is v1's own law, it is what makes
ppc the cross-capture correspondence, and it is enforced by the carried
arm this module CALLS rather than reimplements (``scale_space``, whose
bytes are oracle-pinned). Nothing here does arithmetic on a pixel — it
names files, streams :func:`~holo2.capture.scale_space.area_decimate_into`
into them, and maps geometry between the native frame and a rung's.

**The naming discipline is ``solve.prepared``'s, for the same reasons.**
A file is named by a digest of everything its content is a function of —
the capture's own SHA-256, the native array's shape and dtype, the
decimation's exact rational scale, and a format tag that is bumped
whenever the bytes a name stands for would change. Builds are
temp-file-and-replace, so a crash leaves a ``.partial`` and never a short
file under a live name; SIZE is the completeness check; and a name that
already stands is REUSED rather than rebuilt. Two consequences worth
stating: a re-derivation of bytes already on disk costs one ``stat``, and
a rung derived under a policy that is later abandoned is inert rather
than wrong.

**Where they live and who writes them.** The files go in the
``<state-dir>.prepared`` sibling beside the prepared planes — same
lifetime, same "delete it and pay one rebuild" contract, same
single-writer exclusion from the store's own lock. The WRITER is the
ingest fire (``capture.ingest``), which is the one place that already
holds the native pixels and already pays a full pass over them; the
READER is ``solve``, which may import this package but not the other way
round. That is why the naming, the geometry and the file format are all
HERE, in capture, and why the module takes plain arrays: the two
``crop_native`` calls that feed it stay in ``ingest.py``, which is the
module §6.8 already entitles to raw capture pixels.

THE FOOTING FRAME
-----------------
:class:`FootingFrame` is the second half of the module and the only place
a coordinate crosses between frames. A region's survey is a CAPTURE fact
in holo2 (one survey per acquisition, not one per footing — ``ingest``
states why), so its support mask and bbox are denominated in NATIVE
pixels while a rung's pixels are not. Two mappings close that gap, and
both are exact integer arithmetic with the identity case delegating to
the native code path unchanged:

* :meth:`FootingFrame.extent` keeps the footing pixels whose support lies
  WHOLLY inside the native extent — ``scale_space``'s own "incomplete
  trailing pixels are discarded" boundary rule, run backwards, so a rung
  never claims a pixel that half-hangs off the region;
* :meth:`FootingFrame.support_crop` calls a footing pixel supported iff
  its CENTRE lands in a supported native pixel. That is the rule
  ``solve.plans.sample_support`` already applies to the same
  block-constant grid one level up ("a cell is supported iff its centre
  lands in a true survey cell"), which is what makes it a restatement
  rather than a new decision.

Both are DEAD at stage 1 — the reading set is finest-only, and the finest
rung IS native, so every frame the receiver builds is the identity one.
They are written now because the mechanism they belong to is, and they
are pinned directly rather than through a lane that does not run yet.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from .scale_space import AreaPixelTransform, area_decimate_into
from .survey import SupportMask

#: Bumped whenever the bytes a footing-raster name stands for would
#: change — a different decimation, a different on-disk layout. It is the
#: DECIMATION's identity in the digest, the way ``PREPARED_FORMAT`` is the
#: preparation's.
FOOTING_FORMAT = "holo2-footing-1"
#: The on-disk suffix. A raw C-order array of the capture's native dtype:
#: no header, because the digest already names the shape and the dtype,
#: and size is therefore an exact completeness check.
FOOTING_SUFFIX = ".footing.raw"


def footing_transform(ppc: Fraction, native_ppc: Fraction
                      ) -> AreaPixelTransform:
    """The exact-rational native-to-rung map of one footing.

    ``source_per_output`` is ``native_ppc / ppc``: a rung at half the
    native sampling integrates two native pixels per output pixel. The
    ladder never upsamples (``auto_ppc_levels`` ends AT native), so this
    is always >= 1 and the carried transform's own guard says so.
    """
    return AreaPixelTransform(Fraction(native_ppc) / Fraction(ppc))


@dataclass(frozen=True)
class FootingPlan:
    """What one rung's file IS: its path, its shape and its dtype.

    Pure arithmetic over durable values — the capture's sha, shape and
    dtype, and the transform — so the writer and every reader compute the
    SAME name from the same facts, and a session holding no pixels can
    still pronounce it.
    """

    path: Path
    shape_px: tuple[int, int]
    dtype: np.dtype

    @property
    def nbytes(self) -> int:
        return int(self.dtype.itemsize) * self.shape_px[0] * self.shape_px[1]

    def stands(self) -> bool:
        """A file this size under this name is the rung the digest names."""
        try:
            return self.path.stat().st_size == self.nbytes
        except OSError:
            return False


def footing_plan(capture_sha256: str, transform: AreaPixelTransform,
                 native_shape_px: tuple[int, int], dtype: np.dtype | str, *,
                 directory: Path) -> FootingPlan:
    """Name one rung of one capture, without touching a pixel or a file."""
    if transform.is_identity:
        raise ValueError(
            "the native rung is the authenticated scan itself and is never "
            "derived onto disk")
    native = np.dtype(dtype)
    shape = transform.output_shape(tuple(int(v) for v in native_shape_px))
    scale = transform.source_per_output
    material = "\n".join((
        FOOTING_FORMAT,
        f"capture={capture_sha256}",
        "native={},{}".format(int(native_shape_px[0]),
                              int(native_shape_px[1])),
        f"dtype={native.str}",
        f"scale={scale.numerator}/{scale.denominator}",
    ))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return FootingPlan(Path(directory) / f"{digest}{FOOTING_SUFFIX}",
                       shape, native)


def write_footing_raster(source: np.ndarray, transform: AreaPixelTransform,
                         plan: FootingPlan) -> None:
    """Stream one rung into its file, then publish it atomically.

    The decimation is the carried arm's, chunk by chunk into a
    ``w+`` memmap, so the build's own peak is one chunk rather than one
    rung — which is what lets this run inside an ingest fire beside a
    2 GB scan. ``area_decimate_into`` releases the GIL over every one of
    those chunks, so the pooled lane overlaps it with placement on the
    captures that already landed.
    """
    temporary = plan.path.with_name(plan.path.name + ".partial")
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    target = np.memmap(temporary, dtype=plan.dtype, mode="w+",
                       shape=plan.shape_px)
    try:
        area_decimate_into(source, transform, target)
        target.flush()
    finally:
        del target
    os.replace(temporary, plan.path)


@dataclass(frozen=True, eq=False)
class FootingRaster:
    """One derived rung, mapped read-only — a raster to everyone above.

    ``eq=False`` on purpose: the field is an ndarray, so a generated
    ``__eq__``/``__hash__`` would raise on the first comparison anybody
    tried. A mapped rung has IDENTITY semantics — it is a handle onto a
    file, and two handles onto the same file are the same rung by name,
    which is the question ``footing_plan`` answers.

    It answers the two questions ``solve.prepared`` asks a capture's
    pixels (``shape`` and a bounded float32 luma crop) and nothing else,
    which is the whole of what a preparation needs. It is deliberately
    NOT a :class:`~holo2.capture.scan.Raster`: a ``Raster`` is an
    AUTHENTICATED acquisition, and manufacturing one over derived pixels
    would put a second thing that claims to be a capture identity into
    the tree. A rung is a function of an acquisition; it is not one.

    An RGB capture's rungs are single-plane, because the carried
    ``area_decimate_into`` projects to the historical E021 luma plane on
    the way down. The luma of a rung is therefore the stored value, and
    reading it costs a float32 cast.
    """

    pixels: np.ndarray
    ppc: Fraction

    @property
    def shape(self) -> tuple[int, int]:
        return (int(self.pixels.shape[0]), int(self.pixels.shape[1]))

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        """Read-only raw float32 luma for a strict in-bounds box.

        ``Raster.crop_luma``'s contract, spelled for a two-dimensional
        single-plane rung: bounds are refused rather than clipped, the
        result never aliases the mapping, and it is frozen.
        """
        height, width = self.shape
        if not (0 <= r0 < r1 <= height and 0 <= c0 < c1 <= width):
            raise ValueError(
                f"crop ({r0},{r1},{c0},{c1}) is not an in-bounds box of "
                f"footing raster {self.shape}")
        out = np.array(self.pixels[r0:r1, c0:c1], dtype=np.float32,
                       copy=True, order="C")
        out.setflags(write=False)
        return out


def open_footing_raster(plan: FootingPlan, ppc: Fraction
                        ) -> FootingRaster | None:
    """The rung this name stands for, or ``None`` when it does not stand.

    REUSE ONLY, and never a claim that the rung is underivable — only
    that it is not on disk here. Mapping a file this session did not
    write is safe for ``solve.prepared``'s reason: a re-earn verifies
    every re-executed batch against the id the journal holds, so a stale
    or corrupt rung produces a divergent id and refuses loudly instead of
    slipping through.
    """
    if not plan.stands():
        return None
    mapped = np.memmap(plan.path, dtype=plan.dtype, mode="r",
                       shape=plan.shape_px)
    return FootingRaster(np.asarray(mapped), Fraction(ppc))


# ------------------------------------------------------------- the frame

@dataclass(frozen=True)
class FootingFrame:
    """One rung's pixel frame, and the two maps into it from native.

    Carried by everything that prepares or reads a footing's pixels. The
    NATIVE frame is a first-class member of this type rather than a
    special case outside it (:meth:`native`), and every method delegates
    to the untouched native code path when it is: that is what makes
    "the native rung's bytes and names are exactly today's" a structural
    property instead of a promise.
    """

    transform: AreaPixelTransform
    native_shape_px: tuple[int, int]

    @classmethod
    def native(cls, native_shape_px: tuple[int, int]) -> "FootingFrame":
        return cls(AreaPixelTransform(Fraction(1)),
                   (int(native_shape_px[0]), int(native_shape_px[1])))

    @classmethod
    def of(cls, ppc: Fraction, native_ppc: Fraction,
           native_shape_px: tuple[int, int]) -> "FootingFrame":
        return cls(footing_transform(ppc, native_ppc),
                   (int(native_shape_px[0]), int(native_shape_px[1])))

    @property
    def is_native(self) -> bool:
        return self.transform.is_identity

    @property
    def shape_px(self) -> tuple[int, int]:
        return self.transform.output_shape(self.native_shape_px)

    def pitch_px(self, native_pitch_px: float) -> float:
        """The printed cell's pitch IN THIS RUNG'S PIXELS.

        A cell measures the same paper at every rung; what changes is how
        many pixels are laid over it, and that is the transform's own
        scale. Exactly ``native_pitch_px`` at the native rung, by
        construction rather than by rounding.
        """
        if self.is_native:
            return float(native_pitch_px)
        return float(native_pitch_px) / float(self.transform.source_per_output)

    def extent(self, native_extent: tuple[int, int, int, int]
               ) -> tuple[int, int, int, int] | None:
        """A native bbox, as the rung pixels WHOLLY inside it.

        ``scale_space``'s boundary doctrine run backwards: an output
        pixel exists only where its whole rational support is available,
        so the first kept pixel is ``ceil(y0*q/p)`` and one past the last
        is ``floor(y1*q/p)``. ``None`` where a rung is too coarse to hold
        one complete pixel of the region, which is the same shape of
        refusal ``region_extent`` already makes for a bbox off the
        raster.
        """
        if self.is_native:
            return native_extent
        y0, x0, y1, x1 = native_extent
        scale = self.transform.source_per_output
        p, q = scale.numerator, scale.denominator
        fy0, fy1 = -(-y0 * q // p), y1 * q // p
        fx0, fx1 = -(-x0 * q // p), x1 * q // p
        if fy1 <= fy0 or fx1 <= fx0:
            return None
        return int(fy0), int(fx0), int(fy1), int(fx1)

    def support_crop(self, support_mask: SupportMask, r0: int, r1: int,
                     c0: int, c1: int) -> np.ndarray:
        """Support over a box of THIS rung's pixels.

        Native delegates to ``SupportMask.rasterize_crop`` untouched. A
        coarse rung asks the centre question: rung pixel ``j`` covers
        native ``[j*p/q, (j+1)*p/q)``, its centre sits at
        ``(p(2j+1) - q) / 2q``, and the pixel is supported iff the native
        pixel containing that centre is. Integer arithmetic throughout —
        a float here would make support a function of rounding at exactly
        the rungs where the boxes are widest.
        """
        if self.is_native:
            return support_mask.rasterize_crop(r0, r1, c0, c1)
        if not (0 <= r0 < r1 and 0 <= c0 < c1):
            raise ValueError("support crop must be a non-empty positive box")
        rows = self._centres(np.arange(r0, r1, dtype=np.int64))
        cols = self._centres(np.arange(c0, c1, dtype=np.int64))
        origin_y, origin_x = support_mask.origin_yx
        height, width = support_mask.extent_px
        step = support_mask.step_px
        cells = support_mask.cells
        inside_y = (rows >= origin_y) & (rows < origin_y + height)
        inside_x = (cols >= origin_x) & (cols < origin_x + width)
        out = np.zeros((r1 - r0, c1 - c0), bool)
        if not inside_y.any() or not inside_x.any():
            return out
        grid_y = ((rows[inside_y] - origin_y) // step).astype(np.intp)
        grid_x = ((cols[inside_x] - origin_x) // step).astype(np.intp)
        out[np.ix_(np.flatnonzero(inside_y), np.flatnonzero(inside_x))] = (
            cells[np.ix_(grid_y, grid_x)])
        return out

    def digest_line(self) -> str | None:
        """This frame, as one line of a derived file's name — or nothing.

        ``None`` at the native rung, and that is the whole point: a
        digest that adds nothing there cannot rename a single file that
        already stands (``solve.prepared``'s byte-compare pin).
        """
        if self.is_native:
            return None
        scale = self.transform.source_per_output
        return f"footing={scale.numerator}/{scale.denominator}"

    def _centres(self, indices: np.ndarray) -> np.ndarray:
        scale = self.transform.source_per_output
        p, q = scale.numerator, scale.denominator
        return (p * (2 * indices + 1) - q) // (2 * q)


__all__ = [
    "FOOTING_FORMAT", "FOOTING_SUFFIX", "FootingFrame", "FootingPlan",
    "FootingRaster", "footing_plan", "footing_transform",
    "open_footing_raster", "write_footing_raster",
]
