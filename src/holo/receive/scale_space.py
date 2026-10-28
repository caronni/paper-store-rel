"""Direct-from-native scale-space primitives for the E023c cascade.

Resolution is expressed in scan pixels per printed cell (ppc).  Every view
is an area average of the immutable native raster; a level is never resized
from another level.  This module defines the complete contract:

* a deterministic coarse-to-fine schedule ending at native resolution;
* exact rational pixel-boundary support with incomplete trailing pixels
  discarded;
* chunked writes whose chunk geometry cannot change numerical results; and
* pixel-centre and cell-to-pixel affine transforms between native and view.

The uint8 path retains the E018/E023c operation order byte-for-byte.  Unlike
historical E023c, other real dtypes retain their dtype and native numerical
range: in particular uint16 views are never clipped or converted to uint8.

Chunk sizes are mechanical work-set controls only.  They are deliberately
caller-tunable and have no effect on the output domain, shape, or values.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterator, TypeAlias

import numpy as np


Rational: TypeAlias = int | float | str | Fraction

_PRINT_DPI = 600
_MINIMUM_PPC = Fraction(2)
# Historical E023c work-set defaults.  They are not acceptance limits:
# callers may choose any positive values, and the qualification battery pins
# byte identity down to one output row and one output column per tile.
_DEFAULT_CHUNK_ROWS = 128
_DEFAULT_CHUNK_COLS = 2048


def _fraction(value: Rational, name: str) -> Fraction:
    """Return a finite, positive rational without preserving float noise."""
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a positive number")
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            raise ValueError(f"{name} must be finite")
        # Configuration floats denote their displayed decimal value.  Using
        # Fraction(float) here would turn e.g. 0.1 into a huge binary ratio.
        result = Fraction(str(float(value)))
    else:
        try:
            result = Fraction(value)
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"{name} must be a positive number") from exc
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a positive integer")
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if result <= 0 or result != value:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def native_pixels_per_cell(
    native_dpi: Rational,
    cell_factor: int,
) -> Fraction:
    """Nominal native pixels/cell for a ``c`` format on the 600-dpi grid."""
    c = _positive_integer(cell_factor, "cell_factor")
    return _fraction(native_dpi, "native_dpi") * c / _PRINT_DPI


def auto_ppc_levels(
    native_dpi: Rational,
    cell_factor: int,
) -> tuple[Fraction, ...]:
    """Choose the historical short, monotone coarse-to-native schedule.

    The exact floor is first when native sampling supports it.  Subsequent
    levels approximately double ppc while preferring integer native box
    factors.  Native is present exactly once and the function never upsamples.

    Typical schedules are ``c2@1200: 2,4``, ``c3@1200: 2,3,6`` and
    ``c3@4800: 2,4,8,12,24``.
    """
    native = native_pixels_per_cell(native_dpi, cell_factor)
    if native <= _MINIMUM_PPC:
        return (native,)

    levels = [_MINIMUM_PPC]
    current = _MINIMUM_PPC
    while current < native:
        divisor = _ceil(native / (2 * current))
        following = native if divisor <= 1 else native / divisor
        if following <= current:  # Defensive: guarantees forward progress.
            following = native
        levels.append(following)
        current = following
    return tuple(levels)


@dataclass(frozen=True, slots=True)
class AreaPixelTransform:
    """Pixel-centre map from native source to one area-derived view.

    If ``source_per_output = p/q``, output pixel ``j`` integrates source
    boundary support ``[j*p/q, (j+1)*p/q]``.  Array coordinates denote pixel
    centres, hence ``source = scale * (view + 0.5) - 0.5``.
    """

    source_per_output: Fraction

    def __post_init__(self) -> None:
        scale = _fraction(self.source_per_output, "source_per_output")
        if scale < 1:
            raise ValueError("area transform does not upsample")
        object.__setattr__(self, "source_per_output", scale)

    @property
    def is_identity(self) -> bool:
        return self.source_per_output == 1

    @property
    def is_integer_box(self) -> bool:
        return self.source_per_output.denominator == 1

    def output_length(self, source_length: int) -> int:
        if isinstance(source_length, (bool, np.bool_)):
            raise ValueError("source length must be a non-negative integer")
        try:
            length = int(source_length)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "source length must be a non-negative integer"
            ) from exc
        if length != source_length or length < 0:
            raise ValueError("source length must be a non-negative integer")
        scale = self.source_per_output
        return length * scale.denominator // scale.numerator

    def output_shape(self, source_shape: tuple[int, ...]) -> tuple[int, int]:
        if len(source_shape) not in (2, 3):
            raise ValueError("source shape must describe a grey or RGB raster")
        return (
            self.output_length(source_shape[0]),
            self.output_length(source_shape[1]),
        )

    def source_to_view_points(self, points_yx: np.ndarray) -> np.ndarray:
        points = _points(points_yx)
        if self.is_identity:
            return np.array(points, copy=True)
        scale = float(self.source_per_output)
        return (points + 0.5) / scale - 0.5

    def view_to_source_points(self, points_yx: np.ndarray) -> np.ndarray:
        points = _points(points_yx)
        if self.is_identity:
            return np.array(points, copy=True)
        scale = float(self.source_per_output)
        return scale * (points + 0.5) - 0.5

    def source_to_view_affine(self, affine: np.ndarray) -> np.ndarray:
        """Map a cell-to-native 2x3 affine into derived-view pixels."""
        source = _affine(affine)
        if self.is_identity:
            return np.array(source, copy=True)
        scale = float(self.source_per_output)
        result = np.empty((2, 3), np.float64)
        result[:, :2] = source[:, :2] / scale
        result[:, 2] = (source[:, 2] + 0.5) / scale - 0.5
        return result

    def view_to_source_affine(self, affine: np.ndarray) -> np.ndarray:
        """Map a cell-to-view 2x3 affine back into native pixels."""
        view = _affine(affine)
        if self.is_identity:
            return np.array(view, copy=True)
        scale = float(self.source_per_output)
        result = np.empty((2, 3), np.float64)
        result[:, :2] = view[:, :2] * scale
        result[:, 2] = scale * (view[:, 2] + 0.5) - 0.5
        return result


def _points(value: np.ndarray) -> np.ndarray:
    points = np.asarray(value, np.float64)
    if points.shape[-1:] != (2,):
        raise ValueError("pixel points must have final dimension 2")
    if not np.isfinite(points).all():
        raise ValueError("pixel points must be finite")
    return points


def _affine(value: np.ndarray) -> np.ndarray:
    affine = np.asarray(value, np.float64)
    if affine.shape != (2, 3):
        raise ValueError(f"cell-to-pixel affine must have shape (2,3), got "
                         f"{affine.shape}")
    if not np.isfinite(affine).all():
        raise ValueError("cell-to-pixel affine must be finite")
    return affine


@dataclass(frozen=True, slots=True)
class ScaleLevel:
    """One immutable direct-native level in an E023c schedule."""

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

        return (f"l{self.index:02d}-{render(self.ppc)}ppc-"
                f"{render(self.dpi)}dpi")


@dataclass(frozen=True, slots=True)
class ScaleSchedule:
    """A direct-from-native scale plan for one format and capture."""

    levels: tuple[ScaleLevel, ...]

    @classmethod
    def auto(
        cls,
        native_dpi: Rational,
        cell_factor: int,
    ) -> "ScaleSchedule":
        dpi = _fraction(native_dpi, "native_dpi")
        c = _positive_integer(cell_factor, "cell_factor")
        native_ppc = native_pixels_per_cell(dpi, c)
        levels = tuple(
            ScaleLevel(
                index=index,
                ppc=ppc,
                dpi=ppc * _PRINT_DPI / c,
                transform=AreaPixelTransform(native_ppc / ppc),
            )
            for index, ppc in enumerate(auto_ppc_levels(dpi, c))
        )
        return cls(levels)


def _source_array(array: np.ndarray) -> np.ndarray:
    source = np.asanyarray(array)
    if source.ndim not in (2, 3):
        raise ValueError("source raster must be 2-D grey or 3-D RGB")
    if source.ndim == 3 and source.shape[2] < 3:
        raise ValueError("RGB source raster must carry at least three planes")
    if (not np.issubdtype(source.dtype, np.number)
            or np.issubdtype(source.dtype, np.complexfloating)
            or np.issubdtype(source.dtype, np.bool_)):
        raise ValueError(f"source raster must be real numeric, got "
                         f"{source.dtype}")
    return source


def _source_interval(
    output_start: int,
    output_stop: int,
    scale: Fraction,
) -> tuple[int, int]:
    """Exact half-open source interval touched by output boundaries."""
    p, q = scale.numerator, scale.denominator
    return output_start * p // q, (output_stop * p + q - 1) // q


def _uint8_integer_box_rows(
    source: np.ndarray,
    factor: int,
    y0: int,
    y1: int,
    output_width: int,
) -> np.ndarray:
    """Frozen E018 uint8 operation order over complete output rows."""
    block = source[y0 * factor:y1 * factor, :output_width * factor]
    if factor == 1 and block.ndim == 2:
        return np.array(block, copy=True)
    if block.ndim == 3:
        # E018 first averaged RGB with NumPy's default accumulator.
        block = block[..., :3].mean(axis=2)
    block = np.asarray(block, np.float32)
    reduced = block.reshape(
        y1 - y0, factor, output_width, factor
    ).mean(axis=(1, 3))
    return reduced.round().clip(0, 255).astype(np.uint8)


def _coordinates_fit_int64(
    source_shape: tuple[int, ...],
    y1: int,
    x1: int,
    scale: Fraction,
) -> bool:
    limit = np.iinfo(np.int64).max
    p, q = scale.numerator, scale.denominator
    largest_output = max(y1, x1, 1)
    largest_source = max(int(source_shape[0]), int(source_shape[1]), 1)
    return (largest_output * p + p <= limit
            and largest_source * q + q <= limit)


def _integer_accumulator_fits(
    source: np.ndarray,
    scale: Fraction,
) -> bool:
    info = np.iinfo(source.dtype)
    magnitude = max(abs(int(info.min)), abs(int(info.max)))
    channels = 3 if source.ndim == 3 else 1
    denominator = channels * scale.numerator * scale.numerator
    return magnitude * denominator <= np.iinfo(np.int64).max


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
    for offset in range(_ceil(scale) + 1):
        absolute = bases + offset
        local = absolute - source_start
        lower = absolute * q
        upper = lower + q
        overlaps = np.maximum(
            0, np.minimum(stops, upper) - np.maximum(starts, lower)
        )
        active = overlaps != 0
        if not np.any(active):
            continue
        if np.any(local[active] < 0) or np.any(local[active] >= width):
            raise RuntimeError("area interval escaped its source tile")
        samples = np.take(moved, np.clip(local, 0, width - 1), axis=-1)
        weighted += samples * overlaps
    return np.moveaxis(weighted, -1, axis)


def _round_ratio_int64(
    numerator: np.ndarray,
    denominator: int,
    dtype: np.dtype,
) -> np.ndarray:
    """Round an exact signed ratio to nearest-even in ``dtype``."""
    values = np.asarray(numerator, np.int64)
    quotient, remainder = np.divmod(values, denominator)
    half = denominator // 2
    increment = remainder > half
    if denominator % 2 == 0:
        increment |= (remainder == half) & ((quotient & 1) != 0)
    return (quotient + increment).astype(dtype)


def _integer_area_tile_int64(
    block: np.ndarray,
    scale: Fraction,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
    sy0: int,
    sx0: int,
    dtype: np.dtype,
) -> np.ndarray:
    channels = 3 if block.ndim == 3 else 1
    values = (np.asarray(block[..., :3], np.int64).sum(axis=2)
              if channels == 3 else np.asarray(block, np.int64))
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
    denominator = channels * scale.numerator * scale.numerator
    return _round_ratio_int64(numerator, denominator, dtype)


def _integer_box_tile_int64(
    block: np.ndarray,
    factor: int,
    output_shape: tuple[int, int],
    dtype: np.dtype,
) -> np.ndarray:
    """Fast exact native-range box mean for non-uint8 integer rasters."""
    channels = 3 if block.ndim == 3 else 1
    values = (np.asarray(block[..., :3], np.int64).sum(axis=2)
              if channels == 3 else np.asarray(block, np.int64))
    height, width = output_shape
    numerator = values.reshape(
        height, factor, width, factor
    ).sum(axis=(1, 3), dtype=np.int64)
    return _round_ratio_int64(
        numerator, channels * factor * factor, dtype
    )


def _overlap_weights(index: int, scale: Fraction) -> tuple[tuple[int, int], ...]:
    """Source indices and integer overlap numerators for one output pixel."""
    p, q = scale.numerator, scale.denominator
    start, stop = index * p, (index + 1) * p
    first, final = start // q, (stop + q - 1) // q
    rows: list[tuple[int, int]] = []
    for source_index in range(first, final):
        overlap = max(
            0,
            min(stop, (source_index + 1) * q)
            - max(start, source_index * q),
        )
        if overlap:
            rows.append((source_index, overlap))
    return tuple(rows)


def _round_python_ratio(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    twice = remainder * 2
    return quotient + int(
        twice > denominator
        or (twice == denominator and quotient % 2 != 0)
    )


def _integer_area_tile_python(
    source: np.ndarray,
    scale: Fraction,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
) -> np.ndarray:
    """Arbitrary-precision exact fallback; avoids a semantic scale limit."""
    result = np.empty((y1 - y0, x1 - x0), source.dtype)
    channels = 3 if source.ndim == 3 else 1
    denominator = channels * scale.numerator * scale.numerator
    y_weights = [_overlap_weights(y, scale) for y in range(y0, y1)]
    x_weights = [_overlap_weights(x, scale) for x in range(x0, x1)]
    for oy, ys in enumerate(y_weights):
        for ox, xs in enumerate(x_weights):
            total = 0
            for sy, wy in ys:
                for sx, wx in xs:
                    if channels == 3:
                        sample = sum(
                            int(value) for value in source[sy, sx, :3]
                        )
                    else:
                        sample = int(source[sy, sx])
                    total += sample * wy * wx
            result[oy, ox] = _round_python_ratio(total, denominator)
    return result


def _area_average_axis_float64(
    values: np.ndarray,
    *,
    axis: int,
    source_start: int,
    output_start: int,
    output_stop: int,
    scale: Fraction,
) -> np.ndarray:
    """Separable rational-area averaging with float64 accumulation."""
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
    for offset in range(_ceil(scale) + 1):
        absolute = bases + offset
        local = absolute - source_start
        lower = absolute * q
        upper = lower + q
        overlaps = np.maximum(
            0, np.minimum(stops, upper) - np.maximum(starts, lower)
        )
        active = overlaps != 0
        if not np.any(active):
            continue
        if np.any(local[active] < 0) or np.any(local[active] >= width):
            raise RuntimeError("area interval escaped its source tile")
        samples = np.take(moved, np.clip(local, 0, width - 1), axis=-1)
        averaged += samples * (overlaps / p)
    return np.moveaxis(averaged, -1, axis)


def _float_area_tile_python(
    source: np.ndarray,
    scale: Fraction,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
) -> np.ndarray:
    result = np.empty((y1 - y0, x1 - x0), source.dtype)
    denominator = scale.numerator * scale.numerator
    y_weights = [_overlap_weights(y, scale) for y in range(y0, y1)]
    x_weights = [_overlap_weights(x, scale) for x in range(x0, x1)]
    for oy, ys in enumerate(y_weights):
        for ox, xs in enumerate(x_weights):
            total = 0.0
            for sy, wy in ys:
                for sx, wx in xs:
                    sample = source[sy, sx]
                    value = (float(np.asarray(sample)[:3].mean())
                             if source.ndim == 3 else float(sample))
                    total += value * wy * wx
            result[oy, ox] = total / denominator
    return result


def _area_tile(
    source: np.ndarray,
    transform: AreaPixelTransform,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
) -> np.ndarray:
    scale = transform.source_per_output
    sy0, sy1 = _source_interval(y0, y1, scale)
    sx0, sx1 = _source_interval(x0, x1, scale)
    block = source[sy0:sy1, sx0:sx1]

    if np.issubdtype(source.dtype, np.integer):
        if (_integer_accumulator_fits(source, scale)
                and _coordinates_fit_int64(source.shape, y1, x1, scale)):
            if transform.is_integer_box:
                return _integer_box_tile_int64(
                    block,
                    scale.numerator,
                    (y1 - y0, x1 - x0),
                    source.dtype,
                )
            return _integer_area_tile_int64(
                block, scale, y0, y1, x0, x1, sy0, sx0, source.dtype
            )
        return _integer_area_tile_python(source, scale, y0, y1, x0, x1)

    if not _coordinates_fit_int64(source.shape, y1, x1, scale):
        return _float_area_tile_python(source, scale, y0, y1, x0, x1)
    values = (np.asarray(block[..., :3], np.float64).mean(axis=2)
              if block.ndim == 3 else np.asarray(block, np.float64))
    horizontal = _area_average_axis_float64(
        values,
        axis=1,
        source_start=sx0,
        output_start=x0,
        output_stop=x1,
        scale=scale,
    )
    reduced = _area_average_axis_float64(
        horizontal,
        axis=0,
        source_start=sy0,
        output_start=y0,
        output_stop=y1,
        scale=scale,
    )
    return reduced.astype(source.dtype)


def iter_area_decimation_chunks(
    array: np.ndarray,
    transform: AreaPixelTransform,
    *,
    chunk_rows: int = _DEFAULT_CHUNK_ROWS,
    chunk_cols: int = _DEFAULT_CHUNK_COLS,
) -> Iterator[tuple[slice, np.ndarray]]:
    """Yield complete-width row chunks of one direct-native transform.

    Rational and non-uint8 integer views are computed in column tiles.  The
    frozen uint8 integer-box path intentionally retains complete registered
    rows because reducing narrow x slices can change float32 tie rounding.
    """
    source = _source_array(array)
    if not isinstance(transform, AreaPixelTransform):
        raise TypeError("transform must be an AreaPixelTransform")
    rows = _positive_integer(chunk_rows, "chunk_rows")
    cols = _positive_integer(chunk_cols, "chunk_cols")
    out_h, out_w = transform.output_shape(source.shape)
    if out_h == 0 or out_w == 0:
        return

    frozen_uint8_box = (
        source.dtype == np.dtype(np.uint8) and transform.is_integer_box
    )
    factor = transform.source_per_output.numerator
    if transform.is_integer_box:
        # Preserve E023c's factor-adaptive native-row workset.  This changes
        # scheduling only: an integer factor f consumes at most 256 source
        # rows per yielded output chunk, while a smaller caller request stays
        # authoritative.  Output values and domain remain unchanged.
        rows = min(rows, max(1, 256 // factor))
    for y0 in range(0, out_h, rows):
        y1 = min(out_h, y0 + rows)
        if frozen_uint8_box:
            yield slice(y0, y1), _uint8_integer_box_rows(
                source, factor, y0, y1, out_w
            )
            continue
        chunk = np.empty((y1 - y0, out_w), source.dtype)
        for x0 in range(0, out_w, cols):
            x1 = min(out_w, x0 + cols)
            chunk[:, x0:x1] = _area_tile(
                source, transform, y0, y1, x0, x1
            )
        yield slice(y0, y1), chunk


def area_decimate_into(
    array: np.ndarray,
    transform: AreaPixelTransform,
    output: np.ndarray,
    *,
    chunk_rows: int = _DEFAULT_CHUNK_ROWS,
    chunk_cols: int = _DEFAULT_CHUNK_COLS,
) -> np.ndarray:
    """Write a native-range derived view into an ndarray or memmap."""
    source = _source_array(array)
    if not isinstance(transform, AreaPixelTransform):
        raise TypeError("transform must be an AreaPixelTransform")
    target = np.asanyarray(output)
    expected = transform.output_shape(source.shape)
    if target.ndim != 2 or tuple(target.shape) != expected:
        raise ValueError(f"output shape must be {expected}")
    if target.dtype != source.dtype:
        raise ValueError(f"output dtype must retain native {source.dtype}")
    if not target.flags.writeable:
        raise ValueError("output raster must be writeable")
    if np.may_share_memory(source, target):
        raise ValueError("source and output rasters must not share memory")
    for output_rows, chunk in iter_area_decimation_chunks(
        source,
        transform,
        chunk_rows=chunk_rows,
        chunk_cols=chunk_cols,
    ):
        target[output_rows, :] = chunk
    return output


def area_decimate(
    array: np.ndarray,
    transform: AreaPixelTransform,
    *,
    chunk_rows: int = _DEFAULT_CHUNK_ROWS,
    chunk_cols: int = _DEFAULT_CHUNK_COLS,
) -> np.ndarray:
    """Materialize one native-range view directly from ``array``."""
    source = _source_array(array)
    output = np.empty(transform.output_shape(source.shape), source.dtype)
    return area_decimate_into(
        source,
        transform,
        output,
        chunk_rows=chunk_rows,
        chunk_cols=chunk_cols,
    )


def area_decimate_rgb_into(
    array: np.ndarray,
    transform: AreaPixelTransform,
    output: np.ndarray,
    *,
    chunk_rows: int = _DEFAULT_CHUNK_ROWS,
    chunk_cols: int = _DEFAULT_CHUNK_COLS,
) -> np.ndarray:
    """Write one direct-native, channel-preserving RGB view.

    The established :func:`area_decimate_into` contract deliberately
    projects RGB to the historical E021 luma plane.  Color rows need the
    same spatial transform without that projection, so this explicit leaf
    applies the frozen scalar operation independently to C-contiguous R, G,
    and B planes.  K never calls this function.
    """
    source = _source_array(array)
    if source.ndim != 3 or source.shape[2] != 3:
        raise ValueError("channel-preserving decimation needs exactly RGB")
    target = np.asanyarray(output)
    expected_yx = transform.output_shape(source.shape)
    expected = expected_yx + (3,)
    if target.shape != expected:
        raise ValueError(f"RGB output shape must be {expected}")
    if target.dtype != source.dtype:
        raise ValueError(f"RGB output dtype must retain native {source.dtype}")
    if not target.flags.writeable:
        raise ValueError("RGB output raster must be writeable")
    if np.may_share_memory(source, target):
        raise ValueError("source and RGB output rasters must not share memory")
    for channel in range(3):
        area_decimate_into(
            source[..., channel],
            transform,
            target[..., channel],
            chunk_rows=chunk_rows,
            chunk_cols=chunk_cols,
        )
    return output


def area_decimate_rgb(
    array: np.ndarray,
    transform: AreaPixelTransform,
    *,
    chunk_rows: int = _DEFAULT_CHUNK_ROWS,
    chunk_cols: int = _DEFAULT_CHUNK_COLS,
) -> np.ndarray:
    """Materialize one aligned RGB lane without changing K photometry."""
    source = _source_array(array)
    if source.ndim != 3 or source.shape[2] != 3:
        raise ValueError("channel-preserving decimation needs exactly RGB")
    output = np.empty(
        transform.output_shape(source.shape) + (3,), source.dtype)
    return area_decimate_rgb_into(
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
    chunk_rows: int = _DEFAULT_CHUNK_ROWS,
    chunk_cols: int = _DEFAULT_CHUNK_COLS,
) -> Iterator[tuple[ScaleLevel, np.ndarray]]:
    """Derive every level independently from the same native raster."""
    source = _source_array(native)
    if not isinstance(schedule, ScaleSchedule):
        raise TypeError("schedule must be a ScaleSchedule")
    for level in schedule.levels:
        yield level, area_decimate(
            source,
            level.transform,
            chunk_rows=chunk_rows,
            chunk_cols=chunk_cols,
        )


__all__ = [
    "AreaPixelTransform",
    "Rational",
    "ScaleLevel",
    "ScaleSchedule",
    "area_decimate",
    "area_decimate_into",
    "area_decimate_rgb",
    "area_decimate_rgb_into",
    "auto_ppc_levels",
    "derive_scale_levels",
    "iter_area_decimation_chunks",
    "native_pixels_per_cell",
]
