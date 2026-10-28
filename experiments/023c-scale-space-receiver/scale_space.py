"""Deterministic, direct-from-native scale-space primitives for E023c.

E023c expresses resolution in *scan pixels per printed cell* (ppc).  Every
derived view is an area average of the immutable native raster; views are
never recursively resized.  This module owns the small amount of arithmetic
needed to make that statement precise:

* an automatic, coarse-to-fine ppc schedule ending at native resolution;
* a rational, separable area transform anchored at the native pixel boundary;
* bounded-memory row/column chunking, including direct writes to a memmap;
* the exact pixel-centre map used to transfer an E022 affine pose.

The integer path deliberately retains the operation order of E018's
``decimate_scan.py``.  It is therefore byte-identical to the registered box
decimation, including RGB-to-grey conversion and NumPy's rounding rule.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Iterator

import numpy as np

from paperholo import pilotsearch


Rational = int | float | str | Fraction


def _fraction(value: Rational, name: str) -> Fraction:
    """Return a finite, positive and reproducible rational value."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a positive number")
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            raise ValueError(f"{name} must be finite")
        # Fraction(float) preserves binary noise.  CLI/configuration decimals
        # are intended as decimal quantities instead.
        result = Fraction(str(float(value)))
    else:
        try:
            result = Fraction(value)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{name} must be a positive number") from exc
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def native_pixels_per_cell(native_dpi: Rational, cell_factor: int) -> Fraction:
    """Nominal native pixels/cell for a ``c`` format at 600-dpi basis."""
    if isinstance(cell_factor, (bool, np.bool_)):
        raise ValueError("cell_factor must be a positive integer")
    c = int(cell_factor)
    if c != cell_factor or c <= 0:
        raise ValueError("cell_factor must be a positive integer")
    return _fraction(native_dpi, "native_dpi") * c / 600


def auto_ppc_levels(
    native_dpi: Rational,
    cell_factor: int,
    minimum_ppc: Rational = 2,
) -> tuple[Fraction, ...]:
    """Choose a short, monotone coarse-to-fine ppc schedule.

    The first view is exactly ``minimum_ppc`` when native sampling can support
    it.  Later views approximately double resolution while preferring an
    integer native decimation factor.  Native resolution is always last and
    appears only once.  Examples are::

        c2 @ 1200 dpi -> 2, 4 ppc
        c3 @ 1200 dpi -> 2, 3, 6 ppc
        c3 @ 4800 dpi -> 2, 4, 8, 12, 24 ppc
        c3 @  600 dpi -> 2, 3 ppc

    If native resolution is at or below the requested floor, the only legal
    level is native; this routine never upsamples.
    """
    native = native_pixels_per_cell(native_dpi, cell_factor)
    floor = _fraction(minimum_ppc, "minimum_ppc")
    if native <= floor:
        return (native,)

    levels = [floor]
    current = floor
    while current < native:
        # Pick native / n nearest to (but no more than) 2*current.  Thus all
        # levels after the exact floor use an integer native box factor.
        divisor = _ceil(native / (2 * current))
        following = native if divisor <= 1 else native / divisor
        if following <= current:  # Defensive against a future policy edit.
            following = native
        levels.append(following)
        current = following
    return tuple(levels)


@dataclass(frozen=True)
class AreaPixelTransform:
    """Pixel-centre transform from a source raster to one area-derived view.

    ``source_per_output = p/q`` means one output pixel spans ``p/q`` source
    pixels.  In boundary coordinates, output pixel ``j`` covers
    ``[j*p/q, (j+1)*p/q]``.  In array pixel-centre coordinates this is::

        source = (p/q) * (view + 0.5) - 0.5

    The transform is downsample-or-identity only.  Partial output pixels at
    the bottom and right are discarded, matching E018 integer box behavior.
    """

    source_per_output: Fraction

    def __post_init__(self) -> None:
        scale = _fraction(self.source_per_output, "source_per_output")
        if scale < 1:
            raise ValueError("area transform does not upsample")
        object.__setattr__(self, "source_per_output", scale)

    @classmethod
    def from_dpi(
        cls,
        source_dpi: Rational,
        output_dpi: Rational,
    ) -> "AreaPixelTransform":
        source = _fraction(source_dpi, "source_dpi")
        output = _fraction(output_dpi, "output_dpi")
        return cls(source / output)

    @classmethod
    def from_ppc(
        cls,
        source_ppc: Rational,
        output_ppc: Rational,
    ) -> "AreaPixelTransform":
        source = _fraction(source_ppc, "source_ppc")
        output = _fraction(output_ppc, "output_ppc")
        return cls(source / output)

    @property
    def is_identity(self) -> bool:
        return self.source_per_output == 1

    @property
    def is_integer_box(self) -> bool:
        return self.source_per_output.denominator == 1

    @property
    def source_centroid_offset(self) -> Fraction:
        return (self.source_per_output - 1) / 2

    def output_length(self, source_length: int) -> int:
        n = int(source_length)
        if n != source_length or n < 0:
            raise ValueError("source length must be a non-negative integer")
        scale = self.source_per_output
        return n * scale.denominator // scale.numerator

    def output_shape(self, source_shape: tuple[int, ...]) -> tuple[int, int]:
        if len(source_shape) not in (2, 3):
            raise ValueError("source shape must describe a grey or RGB raster")
        return (
            self.output_length(int(source_shape[0])),
            self.output_length(int(source_shape[1])),
        )

    def source_to_view_points(self, points_yx: np.ndarray) -> np.ndarray:
        points = np.asarray(points_yx, np.float64)
        if points.shape[-1:] != (2,):
            raise ValueError("pixel points must have final dimension 2")
        scale = float(self.source_per_output)
        return (points + 0.5) / scale - 0.5

    def view_to_source_points(self, points_yx: np.ndarray) -> np.ndarray:
        points = np.asarray(points_yx, np.float64)
        if points.shape[-1:] != (2,):
            raise ValueError("pixel points must have final dimension 2")
        scale = float(self.source_per_output)
        return scale * (points + 0.5) - 0.5

    def to_view_pose(
        self,
        pose: pilotsearch.AffinePose,
    ) -> pilotsearch.AffinePose:
        """Map a cell-to-source pose into derived-view coordinates."""
        scale = float(self.source_per_output)
        origin = self.source_to_view_points(pose.origin_yx)
        jacobian = pose.matrix() / scale
        return replace(
            pose,
            origin_yx=(float(origin[0]), float(origin[1])),
            jacobian_yx=tuple(
                tuple(float(value) for value in row) for row in jacobian),
            pitch_px=float(pose.pitch_px) / scale,
        )

    def from_view_pose(
        self,
        pose: pilotsearch.AffinePose,
    ) -> pilotsearch.AffinePose:
        """Map a cell-to-view pose back into native source coordinates."""
        scale = float(self.source_per_output)
        origin = self.view_to_source_points(pose.origin_yx)
        jacobian = pose.matrix() * scale
        return replace(
            pose,
            origin_yx=(float(origin[0]), float(origin[1])),
            jacobian_yx=tuple(
                tuple(float(value) for value in row) for row in jacobian),
            pitch_px=float(pose.pitch_px) * scale,
        )


@dataclass(frozen=True)
class ScaleLevel:
    """One immutable level in an E023c capture pyramid."""

    index: int
    ppc: Fraction
    dpi: Fraction
    transform: AreaPixelTransform

    @property
    def is_native(self) -> bool:
        return self.transform.is_identity

    @property
    def label(self) -> str:
        def render(value: Fraction) -> str:
            return (str(value.numerator) if value.denominator == 1
                    else f"{value.numerator}-{value.denominator}")
        return f"l{self.index:02d}-{render(self.ppc)}ppc-{render(self.dpi)}dpi"


@dataclass(frozen=True)
class ScaleSchedule:
    """A registered direct-from-native scale plan for one format/capture."""

    native_dpi: Fraction
    cell_factor: int
    minimum_ppc: Fraction
    native_ppc: Fraction
    levels: tuple[ScaleLevel, ...]

    @classmethod
    def auto(
        cls,
        native_dpi: Rational,
        cell_factor: int,
        minimum_ppc: Rational = 2,
    ) -> "ScaleSchedule":
        dpi = _fraction(native_dpi, "native_dpi")
        floor = _fraction(minimum_ppc, "minimum_ppc")
        native_ppc = native_pixels_per_cell(dpi, cell_factor)
        ppcs = auto_ppc_levels(dpi, cell_factor, floor)
        levels = tuple(
            ScaleLevel(
                index=index,
                ppc=ppc,
                dpi=ppc * 600 / int(cell_factor),
                transform=AreaPixelTransform(native_ppc / ppc),
            )
            for index, ppc in enumerate(ppcs)
        )
        return cls(
            native_dpi=dpi,
            cell_factor=int(cell_factor),
            minimum_ppc=floor,
            native_ppc=native_ppc,
            levels=levels,
        )


def _source_array(array: np.ndarray) -> np.ndarray:
    source = np.asanyarray(array)
    if source.ndim not in (2, 3):
        raise ValueError("source raster must be 2-D grey or 3-D RGB")
    if source.ndim == 3 and source.shape[2] < 3:
        raise ValueError("RGB source raster must carry at least three planes")
    if not np.issubdtype(source.dtype, np.number) or np.iscomplexobj(source):
        raise ValueError("source raster must be real numeric")
    return source


def area_output_shape(
    source_shape: tuple[int, ...],
    transform: AreaPixelTransform,
) -> tuple[int, int]:
    """Return the complete-pixel output shape for ``transform``."""
    if not isinstance(transform, AreaPixelTransform):
        raise TypeError("transform must be an AreaPixelTransform")
    return transform.output_shape(source_shape)


def _source_interval(
    output_start: int,
    output_stop: int,
    scale: Fraction,
) -> tuple[int, int]:
    """Exact half-open source interval touched by output pixel boundaries."""
    p, q = scale.numerator, scale.denominator
    start = output_start * p // q
    stop = (output_stop * p + q - 1) // q
    return start, stop


def _integer_box_rows(
    source: np.ndarray,
    factor: int,
    y0: int,
    y1: int,
    output_width: int,
) -> np.ndarray:
    """E018 operation order over complete-width output rows.

    NumPy's tuple-axis float32 mean can resolve an exact rounding boundary
    differently for a narrow nonzero-x slice.  Keeping complete registered
    rows is consequently part of byte compatibility, not just an
    optimization detail.  Memory remains bounded by the caller's row chunk.
    """
    block = source[y0 * factor:y1 * factor, :output_width * factor]
    if factor == 1 and block.ndim == 2 and block.dtype == np.uint8:
        return np.array(block, copy=True)
    if block.ndim == 3:
        block = block[..., :3].mean(axis=2)
    block = np.asarray(block, np.float32)
    reduced = block.reshape(
        y1 - y0, factor, output_width, factor
    ).mean(axis=(1, 3))
    return reduced.round().clip(0, 255).astype(np.uint8)


def _area_average_axis(
    values: np.ndarray,
    *,
    axis: int,
    source_start: int,
    output_start: int,
    output_stop: int,
    scale: Fraction,
) -> np.ndarray:
    """Integrate a piecewise-constant signal over exact rational intervals.

    Each output sample is accumulated in increasing source-pixel order.
    Unlike a prefix-sum difference, this produces identical floating-point
    values when a caller changes chunk boundaries (including exact .5 ties).
    """
    moved = np.moveaxis(np.asarray(values, np.float64), axis, -1)
    width = moved.shape[-1]
    if width <= 0:
        raise ValueError("area averaging received an empty source interval")

    p, q = scale.numerator, scale.denominator
    outputs = np.arange(output_start, output_stop, dtype=np.int64)
    starts = outputs * p
    stops = starts + p
    bases = starts // q
    averaged = np.zeros(moved.shape[:-1] + (len(outputs),), np.float64)
    # An interval of length p/q can touch at most ceil(p/q)+1 source
    # samples.  Zero-overlap endpoint samples are harmless and filtered.
    max_samples = (p + q - 1) // q + 1
    for offset in range(max_samples):
        absolute = bases + offset
        local = absolute - source_start
        lower = absolute * q
        upper = lower + q
        overlaps = np.maximum(
            0, np.minimum(stops, upper) - np.maximum(starts, lower))
        active = overlaps != 0
        if not np.any(active):
            continue
        if np.any(local[active] < 0) or np.any(local[active] >= width):
            raise RuntimeError("internal area interval escaped its source tile")
        samples = np.take(moved, np.clip(local, 0, width - 1), axis=-1)
        averaged += samples * (overlaps / p)
    return np.moveaxis(averaged, -1, axis)


def _uint8_area_denominator(
    source: np.ndarray,
    scale: Fraction,
) -> int:
    """Return the exact normalization denominator or refuse int64 overflow.

    Rational overlap lengths are integer numerators over ``q``.  Dividing an
    overlap by the output footprint ``p/q`` cancels ``q``, so a two-dimensional
    grey area mean has denominator ``p**2``.  RGB follows E018's first-three-
    plane mean and therefore has denominator ``3 * p**2``.

    Every intermediate weighted sum is non-negative and bounded by the final
    numerator.  Proving ``255 * denominator`` fits in int64 is consequently a
    sufficient guard for both separable passes and the final exact rounding.
    """
    channels = 3 if source.ndim == 3 else 1
    denominator = channels * scale.numerator * scale.numerator
    if 255 * denominator > np.iinfo(np.int64).max:
        raise OverflowError(
            "exact uint8 rational area numerator exceeds int64 capacity")
    return denominator


def _area_weighted_axis_int64(
    values: np.ndarray,
    *,
    axis: int,
    source_start: int,
    output_start: int,
    output_stop: int,
    scale: Fraction,
) -> np.ndarray:
    """Accumulate one rational-area axis as exact overlap numerators."""
    moved = np.moveaxis(np.asarray(values, np.int64), axis, -1)
    width = moved.shape[-1]
    if width <= 0:
        raise ValueError("area averaging received an empty source interval")

    p, q = scale.numerator, scale.denominator
    outputs = np.arange(output_start, output_stop, dtype=np.int64)
    starts = outputs * p
    stops = starts + p
    bases = starts // q
    weighted = np.zeros(moved.shape[:-1] + (len(outputs),), np.int64)
    max_samples = (p + q - 1) // q + 1
    for offset in range(max_samples):
        absolute = bases + offset
        local = absolute - source_start
        lower = absolute * q
        upper = lower + q
        overlaps = np.maximum(
            0, np.minimum(stops, upper) - np.maximum(starts, lower))
        active = overlaps != 0
        if not np.any(active):
            continue
        if np.any(local[active] < 0) or np.any(local[active] >= width):
            raise RuntimeError("internal area interval escaped its source tile")
        samples = np.take(moved, np.clip(local, 0, width - 1), axis=-1)
        weighted += samples * overlaps
    return np.moveaxis(weighted, -1, axis)


def _round_unsigned_ratio_to_uint8(
    numerator: np.ndarray,
    denominator: int,
) -> np.ndarray:
    """Round a non-negative exact ratio to uint8 with ties-to-even."""
    values = np.asarray(numerator, np.int64)
    if np.any(values < 0) or denominator <= 0:
        raise ValueError("exact area ratio must be non-negative")
    quotient, remainder = np.divmod(values, int(denominator))
    twice = remainder * 2
    rounded = quotient + (
        (twice > denominator)
        | ((twice == denominator) & ((quotient & 1) != 0))
    )
    return np.clip(rounded, 0, 255).astype(np.uint8)


def _rational_area_tile_uint8(
    block: np.ndarray,
    scale: Fraction,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
    sy0: int,
    sx0: int,
    denominator: int,
) -> np.ndarray:
    """Exact uint8 rational-area tile, including E018 RGB plane averaging."""
    if block.ndim == 3:
        values = np.asarray(block[..., :3], np.int64).sum(axis=2)
    else:
        values = np.asarray(block, np.int64)
    horizontal = _area_weighted_axis_int64(
        values,
        axis=1,
        source_start=sx0,
        output_start=x0,
        output_stop=x1,
        scale=scale,
    )
    numerator = _area_weighted_axis_int64(
        horizontal,
        axis=0,
        source_start=sy0,
        output_start=y0,
        output_stop=y1,
        scale=scale,
    )
    return _round_unsigned_ratio_to_uint8(numerator, denominator)


def _rational_area_tile(
    source: np.ndarray,
    transform: AreaPixelTransform,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
    *,
    uint8_denominator: int | None,
) -> np.ndarray:
    scale = transform.source_per_output
    sy0, sy1 = _source_interval(y0, y1, scale)
    sx0, sx1 = _source_interval(x0, x1, scale)
    block = source[sy0:sy1, sx0:sx1]
    if uint8_denominator is not None:
        return _rational_area_tile_uint8(
            block, scale, y0, y1, x0, x1, sy0, sx0,
            uint8_denominator)

    # Non-uint8 rasters do not have a finite integer sample denominator.  Keep
    # the deterministic float64 fallback, without claiming exact tie behavior.
    if block.ndim == 3:
        block = block[..., :3].mean(axis=2)
    block = np.asarray(block, np.float64)
    horizontal = _area_average_axis(
        block,
        axis=1,
        source_start=sx0,
        output_start=x0,
        output_stop=x1,
        scale=scale,
    )
    reduced = _area_average_axis(
        horizontal,
        axis=0,
        source_start=sy0,
        output_start=y0,
        output_stop=y1,
        scale=scale,
    )
    return reduced.round().clip(0, 255).astype(np.uint8)


def iter_area_decimation_chunks(
    array: np.ndarray,
    transform: AreaPixelTransform,
    *,
    chunk_rows: int = 128,
    chunk_cols: int = 2048,
) -> Iterator[tuple[slice, np.ndarray]]:
    """Yield complete-width uint8 row chunks of a direct area transform.

    Rational row chunks are computed in bounded column tiles.  A TIFF memmap
    is therefore touched only over the source footprint needed for the
    current tile; no full-size grey or floating-point raster is materialized.
    Results do not depend on either chunk size.  The registered integer path
    instead retains complete source rows because that is required for
    byte-identical E018 float32 reduction; it remains vertically bounded.
    """
    source = _source_array(array)
    if not isinstance(transform, AreaPixelTransform):
        raise TypeError("transform must be an AreaPixelTransform")
    rows, cols = int(chunk_rows), int(chunk_cols)
    if rows <= 0 or cols <= 0:
        raise ValueError("chunk_rows and chunk_cols must be positive")
    out_h, out_w = transform.output_shape(source.shape)
    if out_h == 0 or out_w == 0:
        return

    integer = transform.is_integer_box
    factor = transform.source_per_output.numerator if integer else None
    uint8_denominator = (
        None if integer or source.dtype != np.uint8 else
        _uint8_area_denominator(source, transform.source_per_output)
    )
    # Bound native rows even when a caller asks for a very tall output chunk.
    # At 50k pixels wide this keeps the integer float work image near 50 MiB.
    if integer:
        rows = min(rows, max(1, 256 // int(factor)))
    for y0 in range(0, out_h, rows):
        y1 = min(out_h, y0 + rows)
        if integer:
            yield slice(y0, y1), _integer_box_rows(
                source, int(factor), y0, y1, out_w)
            continue
        chunk = np.empty((y1 - y0, out_w), np.uint8)
        for x0 in range(0, out_w, cols):
            x1 = min(out_w, x0 + cols)
            tile = _rational_area_tile(
                source, transform, y0, y1, x0, x1,
                uint8_denominator=uint8_denominator)
            chunk[:, x0:x1] = tile
        yield slice(y0, y1), chunk


def area_decimate_into(
    array: np.ndarray,
    transform: AreaPixelTransform,
    output: np.ndarray,
    *,
    chunk_rows: int = 128,
    chunk_cols: int = 2048,
) -> np.ndarray:
    """Write one derived uint8 view into a supplied ndarray or memmap."""
    source = _source_array(array)
    target = np.asanyarray(output)
    expected = transform.output_shape(source.shape)
    if target.ndim != 2 or tuple(target.shape) != expected:
        raise ValueError(f"output shape must be {expected}")
    if target.dtype != np.uint8:
        raise ValueError("output dtype must be uint8")
    if not target.flags.writeable:
        raise ValueError("output raster must be writeable")
    for rows, chunk in iter_area_decimation_chunks(
            source, transform, chunk_rows=chunk_rows, chunk_cols=chunk_cols):
        target[rows, :] = chunk
    return output


def area_decimate(
    array: np.ndarray,
    transform: AreaPixelTransform,
    *,
    chunk_rows: int = 128,
    chunk_cols: int = 2048,
) -> np.ndarray:
    """Return a uint8 view derived directly from ``array`` by exact area."""
    source = _source_array(array)
    output = np.empty(transform.output_shape(source.shape), np.uint8)
    return area_decimate_into(
        source,
        transform,
        output,
        chunk_rows=chunk_rows,
        chunk_cols=chunk_cols,
    )


def derive_scale_levels(
    native: np.ndarray,
    schedule: ScaleSchedule,
    *,
    chunk_rows: int = 128,
    chunk_cols: int = 2048,
) -> Iterator[tuple[ScaleLevel, np.ndarray]]:
    """Derive schedule levels independently from the same native raster.

    This convenience generator makes the non-recursive contract explicit.
    Large receivers should normally call :func:`area_decimate_into` with a
    disk-backed destination and release each view after its level commits.
    """
    source = _source_array(native)
    for level in schedule.levels:
        yield level, area_decimate(
            source,
            level.transform,
            chunk_rows=chunk_rows,
            chunk_cols=chunk_cols,
        )
