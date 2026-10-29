from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterator

import numpy as np

#: The ladder starts at 2 ppc because the coarsest rung is where most
#: certificates are born -- e023c minted 671 of 754 (c3) and 1310 of
#: 1438 (c2) there.  Do not "optimize" it away because native looks
#: better.  06-intake-survey.md:273-275.
MINIMUM_PPC: Fraction = Fraction(2)
DEFAULT_CHUNK_ROWS: int = 128


#: Floats here denote their DISPLAYED decimal value:
#: Fraction(str(float(v))), never Fraction(v).  A binary expansion
#: forks the ppc ladder and with it every level's geometry and label.
#: 06-intake-survey.md:76-78.
def as_fraction(value: int | float | str | Fraction | np.floating) -> Fraction:
    if isinstance(value, (float, np.floating)):
        return Fraction(str(float(value)))
    return Fraction(value)


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def native_pixels_per_cell(native_dpi: int | float | str | Fraction,
                           pitch_in: int | float | str | Fraction) -> Fraction:
    return as_fraction(native_dpi) * as_fraction(pitch_in)


#: Coarse-to-native, roughly doubling and preferring integer box
#: factors; native appears exactly once and the schedule NEVER
#: upsamples.  Sampling and not the detector sets the floor -- 8 px per
#: dot roughly halves cell BER against 2.  06-intake-survey.md:82-86.
def auto_ppc_levels(native_dpi: int | float | str | Fraction,
                    pitch_in: int | float | str | Fraction,
                    ) -> tuple[Fraction, ...]:
    native = native_pixels_per_cell(native_dpi, pitch_in)
    if native <= MINIMUM_PPC:
        return (native,)
    levels = [MINIMUM_PPC]
    current = MINIMUM_PPC
    while current < native:
        divisor = _ceil(native / (2 * current))
        following = native if divisor <= 1 else native / divisor
        if following <= current:
            following = native
        levels.append(following)
        current = following
    return tuple(levels)


@dataclass(frozen=True)
class AreaPixelTransform:
    source_per_output: Fraction

    @property
    def is_identity(self) -> bool:
        return self.source_per_output == 1

    @property
    def is_integer_box(self) -> bool:
        return self.source_per_output.denominator == 1

    def output_length(self, source_length: int) -> int:
        scale = self.source_per_output
        return int(source_length) * scale.denominator // scale.numerator

    def output_shape(self, source_shape: tuple[int, ...]) -> tuple[int, int]:
        return (
            self.output_length(source_shape[0]),
            self.output_length(source_shape[1]),
        )

    def source_to_view_points(self, points_yx: np.ndarray) -> np.ndarray:
        points = np.asarray(points_yx, np.float64)
        if self.is_identity:
            return np.array(points, copy=True)
        scale = float(self.source_per_output)
        return (points + 0.5) / scale - 0.5

    def view_to_source_points(self, points_yx: np.ndarray) -> np.ndarray:
        points = np.asarray(points_yx, np.float64)
        if self.is_identity:
            return np.array(points, copy=True)
        scale = float(self.source_per_output)
        return scale * (points + 0.5) - 0.5

    def source_to_view_affine(self, affine: np.ndarray) -> np.ndarray:
        source = np.asarray(affine, np.float64)
        if self.is_identity:
            return np.array(source, copy=True)
        scale = float(self.source_per_output)
        result = np.empty((2, 3), np.float64)
        result[:, :2] = source[:, :2] / scale
        result[:, 2] = (source[:, 2] + 0.5) / scale - 0.5
        return result

    def view_to_source_affine(self, affine: np.ndarray) -> np.ndarray:
        view = np.asarray(affine, np.float64)
        if self.is_identity:
            return np.array(view, copy=True)
        scale = float(self.source_per_output)
        result = np.empty((2, 3), np.float64)
        result[:, :2] = view[:, :2] * scale
        result[:, 2] = scale * (view[:, 2] + 0.5) - 0.5
        return result


#: The frozen E018 byte-law, in this order: float64 RGB mean, float32
#: box mean, round-half-to-even, clip, uint8.  A one-ULP change forks
#: every decimated observation, and reducing a NARROW x slice changes
#: float32 tie rounding -- full output rows only.  06-intake-survey.md:99.
def _uint8_integer_box_rows(
    source: np.ndarray,
    factor: int,
    y0: int,
    y1: int,
    output_width: int,
) -> np.ndarray:
    block = source[y0 * factor:y1 * factor, :output_width * factor]
    if factor == 1 and block.ndim == 2:
        return np.array(block, copy=True)
    if block.ndim == 3:
        block = block[..., :3].mean(axis=2)
    block = np.asarray(block, np.float32)
    reduced = block.reshape(
        y1 - y0, factor, output_width, factor
    ).mean(axis=(1, 3))
    return reduced.round().clip(0, 255).astype(np.uint8)


def _source_interval(output_start: int, output_stop: int,
                     scale: Fraction) -> tuple[int, int]:
    p, q = scale.numerator, scale.denominator
    return output_start * p // q, (output_stop * p + q - 1) // q


def _area_weighted_axis_int64(
    values: np.ndarray,
    axis: int,
    source_start: int,
    output_start: int,
    output_stop: int,
    scale: Fraction,
) -> np.ndarray:
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
            0, np.minimum(stops, upper) - np.maximum(starts, lower))
        active = overlaps != 0
        if not np.any(active):
            continue
        if np.any(local[active] < 0) or np.any(local[active] >= width):
            raise RuntimeError("area interval escaped its source tile")
        samples = np.take(moved, np.clip(local, 0, width - 1), axis=-1)
        weighted += samples * overlaps
    return np.moveaxis(weighted, -1, axis)


def _round_ratio_int64(numerator: np.ndarray, denominator: int,
                       ) -> np.ndarray:
    values = np.asarray(numerator, np.int64)
    quotient, remainder = np.divmod(values, denominator)
    half = denominator // 2
    increment = remainder > half
    if denominator % 2 == 0:
        increment |= (remainder == half) & ((quotient & 1) != 0)
    return (quotient + increment).astype(np.uint8)


def _uint8_rational_rows(
    source: np.ndarray,
    scale: Fraction,
    y0: int,
    y1: int,
    output_width: int,
) -> np.ndarray:
    sy0, sy1 = _source_interval(y0, y1, scale)
    sx0, sx1 = _source_interval(0, output_width, scale)
    block = source[sy0:sy1, sx0:sx1]
    channels = 3 if block.ndim == 3 else 1
    values = (np.asarray(block[..., :3], np.int64).sum(axis=2)
              if channels == 3 else np.asarray(block, np.int64))
    horizontal = _area_weighted_axis_int64(
        values, axis=1, source_start=sx0, output_start=0,
        output_stop=output_width, scale=scale)
    numerator = _area_weighted_axis_int64(
        horizontal, axis=0, source_start=sy0, output_start=y0,
        output_stop=y1, scale=scale)
    denominator = channels * scale.numerator * scale.numerator
    return _round_ratio_int64(numerator, denominator)


def iter_area_decimation_chunks(
    array: np.ndarray,
    transform: AreaPixelTransform,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> Iterator[tuple[slice, np.ndarray]]:
    out_h, out_w = transform.output_shape(array.shape)
    if out_h == 0 or out_w == 0:
        return
    scale = transform.source_per_output
    if transform.is_integer_box:
        factor = scale.numerator
        rows = min(chunk_rows, max(1, 256 // factor))
        for y0 in range(0, out_h, rows):
            y1 = min(out_h, y0 + rows)
            yield slice(y0, y1), _uint8_integer_box_rows(
                array, factor, y0, y1, out_w)
        return
    rows = min(chunk_rows, max(1, 256 // _ceil(scale)))
    for y0 in range(0, out_h, rows):
        y1 = min(out_h, y0 + rows)
        yield slice(y0, y1), _uint8_rational_rows(array, scale, y0, y1,
                                                  out_w)


def area_decimate_into(
    array: np.ndarray,
    transform: AreaPixelTransform,
    output: np.ndarray,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> np.ndarray:
    for output_rows, chunk in iter_area_decimation_chunks(
            array, transform, chunk_rows):
        output[output_rows, :] = chunk
    return output


def area_decimate(
    array: np.ndarray,
    transform: AreaPixelTransform,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> np.ndarray:
    output = np.empty(transform.output_shape(array.shape), np.uint8)
    return area_decimate_into(array, transform, output, chunk_rows)


def area_decimate_rgb_into(
    array: np.ndarray,
    transform: AreaPixelTransform,
    output: np.ndarray,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> np.ndarray:
    for channel in range(3):
        area_decimate_into(
            array[..., channel], transform, output[..., channel], chunk_rows)
    return output


def area_decimate_rgb(
    array: np.ndarray,
    transform: AreaPixelTransform,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> np.ndarray:
    output = np.empty(
        transform.output_shape(array.shape) + (3,), np.uint8)
    return area_decimate_rgb_into(array, transform, output, chunk_rows)


#: Equal-channel mean IS the registered K photometry (E021): do not
#: invent luminance weights.  plane_mean_luma_f32 below is the colour
#: lane's decimate-then-mean form, which is NOT mean-then-decimate.
def luma_f32(pixels: np.ndarray) -> np.ndarray:
    if pixels.ndim == 3:
        return pixels[..., :3].mean(axis=2, dtype=np.float32)
    return pixels.astype(np.float32, copy=False)


def plane_mean_luma_f32(r: np.ndarray, g: np.ndarray,
                        b: np.ndarray) -> np.ndarray:
    return np.stack((r, g, b), axis=2).mean(axis=2, dtype=np.float32)
