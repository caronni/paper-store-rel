"""Standalone deterministic TIFF-in/TIFF-out scrap scan generator.

One single-frame uint8 TIFF is treated as a printed source sheet.  The tool
cuts varying source rectangles behind procedural torn-paper contours, places
them on one or more scan-sized white canvases, and optionally adds creases,
folded-back flaps, non-overlapping placement, and paper shadows. Input mode
and DPI are preserved.

This module has no generator, receiver, corpus, manifest, or device-profile
role.  Large source and destination rasters are memory-mapped; scraps are
rendered in bounded row stripes.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import tempfile
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import tifffile
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage


_STRIPE_ROWS: Final = 64
_MASK_LONG_EDGE: Final = 768
_UINT8_MAX: Final = 255
_TIFF_SUFFIXES: Final = (".tif", ".tiff")


@dataclass(frozen=True, slots=True)
class ScrapScanParameters:
    """Parameters for a deterministic collection of synthetic scan pages."""

    seed: int = 0
    pages: int = 1
    scraps_per_page: int = 12
    size_mm: tuple[float, float] = (28.0, 105.0)
    aspect_ratio: tuple[float, float] = (0.32, 1.0)
    tear_mm: float = 1.4
    fold_probability: float = 0.30
    flap_probability: float = 0.35
    shadow_strength: float = 0.12

    def __post_init__(self) -> None:
        _unsigned("seed", self.seed)
        _positive_integer("pages", self.pages)
        _positive_integer("scraps_per_page", self.scraps_per_page)
        _range("size_mm", self.size_mm, minimum=0.0, inclusive=False)
        _range(
            "aspect_ratio", self.aspect_ratio, minimum=0.0, inclusive=False)
        if self.aspect_ratio[1] > 1.0:
            raise ValueError("aspect_ratio maximum must not exceed 1")
        _nonnegative("tear_mm", self.tear_mm)
        _probability("fold_probability", self.fold_probability)
        _probability("flap_probability", self.flap_probability)
        _probability("shadow_strength", self.shadow_strength)


@dataclass(frozen=True, slots=True)
class ScrapPlan:
    """One source crop, torn contour, placement, and optional fold."""

    source_yxhw: tuple[int, int, int, int]
    center_yx: tuple[float, float]
    angle_degrees: float
    contour_xy: tuple[tuple[float, float], ...]
    shadow_offset_yx: tuple[float, float]
    shadow_strength: float
    fold_normal_xy: tuple[float, float] | None
    fold_offset: float | None
    fold_width: float | None
    folded_back: bool


@dataclass(frozen=True, slots=True)
class _RasterFacts:
    shape: tuple[int, ...]
    dpi: float
    photometric: str

    @property
    def height(self) -> int:
        return self.shape[0]

    @property
    def width(self) -> int:
        return self.shape[1]

    @property
    def channels(self) -> int:
        return 1 if len(self.shape) == 2 else self.shape[2]


def _unsigned(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or not 0 <= int(value) < 2**64
    ):
        raise ValueError(f"{name} must be an unsigned 64-bit integer")
    return int(value)


def _positive_integer(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or int(value) < 1
    ):
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _nonnegative(name: str, value: object) -> float:
    result = _finite(name, value)
    if result < 0.0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _probability(name: str, value: object) -> float:
    result = _nonnegative(name, value)
    if result > 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return result


def _range(
    name: str,
    value: object,
    *,
    minimum: float,
    inclusive: bool,
) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"{name} must be a two-tuple")
    low, high = (_finite(name, item) for item in value)
    lower_ok = low >= minimum if inclusive else low > minimum
    if not lower_ok or high < low:
        raise ValueError(f"{name} must be an increasing positive range")
    return low, high


def _domain_seed(seed: int, *coordinates: object) -> int:
    material = bytearray(b"holo/scrap-scan/v1/")
    material.extend(int(seed).to_bytes(8, "big"))
    for coordinate in coordinates:
        material.extend(b"/")
        material.extend(str(coordinate).encode("ascii"))
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _ratio(value: object) -> float:
    if isinstance(value, tuple) and len(value) == 2:
        numerator, denominator = value
        if denominator == 0:
            raise ValueError("TIFF resolution denominator is zero")
        return float(numerator) / float(denominator)
    return float(value)


def _raster_facts(path: Path) -> _RasterFacts:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in _TIFF_SUFFIXES:
        raise ValueError("source must be a TIFF file")
    with tifffile.TiffFile(path) as source:
        if len(source.pages) != 1:
            raise ValueError("source TIFF must contain exactly one frame")
        page = source.pages[0]
        shape = tuple(int(value) for value in page.shape)
        if page.dtype != np.dtype(np.uint8):
            raise ValueError("source TIFF must contain uint8 samples")
        if len(shape) == 2:
            if page.photometric != tifffile.PHOTOMETRIC.MINISBLACK:
                raise ValueError(
                    "grayscale source TIFF must use black-is-zero samples")
            photometric = "minisblack"
        elif len(shape) == 3 and shape[2] == 3:
            if page.photometric != tifffile.PHOTOMETRIC.RGB:
                raise ValueError(
                    "three-channel source TIFF must use RGB samples")
            photometric = "rgb"
        else:
            raise ValueError("source TIFF must be grayscale or RGB")
        x_tag = page.tags.get("XResolution")
        y_tag = page.tags.get("YResolution")
        unit_tag = page.tags.get("ResolutionUnit")
        if x_tag is None or y_tag is None or unit_tag is None:
            raise ValueError("source TIFF must declare its pixel density")
        if int(unit_tag.value) != 2:
            raise ValueError(
                "source TIFF pixel density must be declared in pixels per inch")
        x_dpi = _ratio(x_tag.value)
        y_dpi = _ratio(y_tag.value)
        if (
            not math.isfinite(x_dpi)
            or not math.isfinite(y_dpi)
            or x_dpi <= 0.0
            or abs(x_dpi - y_dpi) > 0.5
        ):
            raise ValueError("source TIFF must declare one square positive DPI")
    return _RasterFacts(shape, (x_dpi + y_dpi) / 2.0, photometric)


def _output_paths(output: Path, pages: int) -> tuple[Path, ...]:
    if output.suffix.lower() not in _TIFF_SUFFIXES:
        raise ValueError("output must have a .tif or .tiff suffix")
    if pages == 1:
        return (output,)
    width = max(3, len(str(pages)))
    return tuple(
        output.with_name(
            f"{output.stem}-{index:0{width}d}{output.suffix}")
        for index in range(1, pages + 1)
    )


def _edge(
    start: np.ndarray,
    stop: np.ndarray,
    *,
    points: int,
    roughness: float,
    notch: tuple[float, float] | None,
    rng: np.random.Generator,
) -> np.ndarray:
    parameter = np.linspace(0.0, 1.0, points, endpoint=False)
    result = (
        start[None, :] * (1.0 - parameter[:, None])
        + stop[None, :] * parameter[:, None]
    )
    direction = stop - start
    length = float(np.linalg.norm(direction))
    inward = np.asarray((-direction[1], direction[0])) / max(length, 1e-9)
    controls = rng.normal(0.0, roughness, 7)
    smooth = np.interp(
        parameter,
        np.linspace(0.0, 1.0, controls.size),
        controls,
    )
    jitter = rng.normal(0.0, roughness * 0.25, points)
    displacement = smooth + jitter
    if notch is not None:
        center, depth = notch
        displacement += depth * np.exp(
            -0.5 * ((parameter - center) / 0.075) ** 2)
    result += displacement[:, None] * inward[None, :]
    return np.clip(result, 0.0, 1.0)


def _contour(
    width_px: int,
    height_px: int,
    *,
    dpi: float,
    tear_mm: float,
    rng: np.random.Generator,
) -> tuple[tuple[float, float], ...]:
    width_mm = width_px * 25.4 / dpi
    height_mm = height_px * 25.4 / dpi
    roughness = min(
        0.10,
        max(0.002, tear_mm / max(min(width_mm, height_mm), 1e-6)),
    )
    corners = np.asarray(
        (
            (rng.uniform(0.00, 0.055), rng.uniform(0.00, 0.055)),
            (rng.uniform(0.945, 1.00), rng.uniform(0.00, 0.055)),
            (rng.uniform(0.945, 1.00), rng.uniform(0.945, 1.00)),
            (rng.uniform(0.00, 0.055), rng.uniform(0.945, 1.00)),
        ),
        dtype=np.float64,
    )
    # Pulled-in corners reproduce the triangular and trapezoidal pieces in
    # the E018/E021 scans without installing those scans as runtime data.
    pulled_index: int | None = None
    if rng.random() < 0.42:
        pulled_index = int(rng.integers(0, 4))
        pull = rng.uniform(0.18, 0.48)
        corners[pulled_index] += (
            np.asarray((0.5, 0.5)) - corners[pulled_index]) * pull
    if rng.random() < 0.12:
        adjacent = (pulled_index + 1) % 4 if pulled_index is not None else 1
        pull = rng.uniform(0.10, 0.30)
        corners[adjacent] += (
            np.asarray((0.5, 0.5)) - corners[adjacent]) * pull

    notch_edge = (
        int(rng.integers(0, 4)) if rng.random() < 0.38 else None)
    rows: list[np.ndarray] = []
    for edge_index in range(4):
        start = corners[edge_index]
        stop = corners[(edge_index + 1) % 4]
        edge_length_mm = float(np.linalg.norm(
            (stop - start) * np.asarray((width_mm, height_mm))))
        count = min(56, max(10, int(round(edge_length_mm / 2.5))))
        notch = (
            (rng.uniform(0.25, 0.75), rng.uniform(0.04, 0.16))
            if notch_edge == edge_index else None
        )
        rows.append(_edge(
            start,
            stop,
            points=count,
            roughness=roughness,
            notch=notch,
            rng=rng,
        ))
    polygon = np.concatenate(rows)
    return tuple((float(x), float(y)) for x, y in polygon)


def _plan_scrap(
    facts: _RasterFacts,
    parameters: ScrapScanParameters,
    rng: np.random.Generator,
) -> ScrapPlan:
    source_height_mm = facts.height * 25.4 / facts.dpi
    source_width_mm = facts.width * 25.4 / facts.dpi
    maximum = min(
        parameters.size_mm[1],
        0.92 * max(source_height_mm, source_width_mm),
    )
    minimum = min(parameters.size_mm[0], maximum)
    long_mm = math.exp(rng.uniform(math.log(minimum), math.log(maximum)))
    aspect = math.exp(rng.uniform(
        math.log(parameters.aspect_ratio[0]),
        math.log(parameters.aspect_ratio[1]),
    ))
    short_mm = long_mm * aspect
    if rng.random() < 0.5:
        width_mm, height_mm = long_mm, short_mm
    else:
        width_mm, height_mm = short_mm, long_mm
    width_px = min(
        facts.width, max(4, int(round(width_mm * facts.dpi / 25.4))))
    height_px = min(
        facts.height, max(4, int(round(height_mm * facts.dpi / 25.4))))
    source_x = int(rng.integers(0, facts.width - width_px + 1))
    source_y = int(rng.integers(0, facts.height - height_px + 1))
    angle = float(rng.uniform(-55.0, 55.0))
    radians = math.radians(angle)
    half_width = (
        abs(math.cos(radians)) * width_px
        + abs(math.sin(radians)) * height_px
    ) / 2.0
    half_height = (
        abs(math.sin(radians)) * width_px
        + abs(math.cos(radians)) * height_px
    ) / 2.0

    def center(limit: int, half: float) -> float:
        margin = half + 2.0
        if 2.0 * margin >= limit:
            return limit / 2.0
        return float(rng.uniform(margin, limit - margin))

    folded = rng.random() < parameters.fold_probability
    folded_back = folded and rng.random() < parameters.flap_probability
    if folded:
        fold_angle = rng.uniform(0.0, 2.0 * math.pi)
        fold_normal = (math.cos(fold_angle), math.sin(fold_angle))
        fold_offset = float(rng.uniform(0.12, 0.34))
        fold_width = min(
            0.08,
            max(
                0.004,
                rng.uniform(0.35, 1.2)
                / max(min(width_mm, height_mm), 1e-6),
            ),
        )
    else:
        fold_normal = None
        fold_offset = None
        fold_width = None
    shadow_px = facts.dpi / 25.4
    return ScrapPlan(
        source_yxhw=(source_y, source_x, height_px, width_px),
        center_yx=(
            center(facts.height, half_height),
            center(facts.width, half_width),
        ),
        angle_degrees=angle,
        contour_xy=_contour(
            width_px,
            height_px,
            dpi=facts.dpi,
            tear_mm=parameters.tear_mm,
            rng=rng,
        ),
        shadow_offset_yx=(
            float(rng.uniform(0.45, 1.10) * shadow_px),
            float(rng.uniform(0.35, 0.90) * shadow_px),
        ),
        shadow_strength=min(
            1.0,
            float(parameters.shadow_strength * rng.uniform(0.75, 1.20)),
        ),
        fold_normal_xy=fold_normal,
        fold_offset=fold_offset,
        fold_width=fold_width,
        folded_back=folded_back,
    )


def plan_scrap_page(
    shape: tuple[int, ...],
    dpi: float,
    parameters: ScrapScanParameters,
    *,
    page_index: int,
) -> tuple[ScrapPlan, ...]:
    """Plan one page without reading or allocating its pixels."""
    if len(shape) == 2:
        photometric = "minisblack"
    elif len(shape) == 3 and shape[2] == 3:
        photometric = "rgb"
    else:
        raise ValueError("shape must describe grayscale or RGB")
    if not 0 <= page_index < parameters.pages:
        raise ValueError("page_index is outside the requested collection")
    actual_dpi = _finite("dpi", dpi)
    if actual_dpi <= 0.0:
        raise ValueError("dpi must be positive")
    facts = _RasterFacts(
        tuple(int(value) for value in shape), actual_dpi, photometric)
    rng = np.random.default_rng(
        _domain_seed(parameters.seed, "page", page_index))
    plans: list[ScrapPlan] = []
    occupied: list[tuple[float, float, float, float]] = []
    gap = actual_dpi / 25.4
    for scrap_index in range(parameters.scraps_per_page):
        for _attempt in range(2000):
            candidate = _plan_scrap(facts, parameters, rng)
            bounds = _content_bounds(candidate)
            if all(_separated(bounds, previous, gap) for previous in occupied):
                plans.append(candidate)
                occupied.append(bounds)
                break
        else:
            raise ValueError(
                f"cannot place scrap {scrap_index + 1} of "
                f"{parameters.scraps_per_page} without overlap; reduce "
                "--scraps or --size-mm"
            )
    return tuple(plans)


def _content_bounds(plan: ScrapPlan) -> tuple[float, float, float, float]:
    """Conservative rotated paper bounds as ``y0, x0, y1, x1``."""
    _source_y, _source_x, height, width = plan.source_yxhw
    angle = math.radians(plan.angle_degrees)
    half_width = (
        abs(math.cos(angle)) * width + abs(math.sin(angle)) * height
    ) / 2.0
    half_height = (
        abs(math.sin(angle)) * width + abs(math.cos(angle)) * height
    ) / 2.0
    return (
        plan.center_yx[0] - half_height,
        plan.center_yx[1] - half_width,
        plan.center_yx[0] + half_height,
        plan.center_yx[1] + half_width,
    )


def _separated(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    gap: float,
) -> bool:
    return (
        first[2] + gap <= second[0]
        or second[2] + gap <= first[0]
        or first[3] + gap <= second[1]
        or second[3] + gap <= first[1]
    )


def _masks(plan: ScrapPlan) -> tuple[np.ndarray, np.ndarray]:
    _y, _x, height, width = plan.source_yxhw
    if width >= height:
        mask_width = _MASK_LONG_EDGE
        mask_height = max(32, int(round(_MASK_LONG_EDGE * height / width)))
    else:
        mask_height = _MASK_LONG_EDGE
        mask_width = max(32, int(round(_MASK_LONG_EDGE * width / height)))
    image = Image.new("L", (mask_width, mask_height), 0)
    draw = ImageDraw.Draw(image)
    draw.polygon(
        tuple(
            (x * (mask_width - 1), y * (mask_height - 1))
            for x, y in plan.contour_xy
        ),
        fill=255,
    )
    image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
    mask = np.asarray(image, dtype=np.float32).copy() / 255.0
    shadow_image = image.filter(ImageFilter.GaussianBlur(radius=5.0))
    shadow = np.asarray(shadow_image, dtype=np.float32).copy() / 255.0
    image.close()
    shadow_image.close()
    return mask, shadow


def _coordinates(
    plan: ScrapPlan,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
    *,
    offset_yx: tuple[float, float] = (0.0, 0.0),
) -> tuple[np.ndarray, np.ndarray]:
    _source_y, _source_x, height, width = plan.source_yxhw
    angle = math.radians(plan.angle_degrees)
    cosine = np.float32(math.cos(angle))
    sine = np.float32(math.sin(angle))
    output_y = np.arange(y0, y1, dtype=np.float32)[:, None]
    output_x = np.arange(x0, x1, dtype=np.float32)[None, :]
    delta_y = output_y - np.float32(
        plan.center_yx[0] + offset_yx[0])
    delta_x = output_x - np.float32(
        plan.center_yx[1] + offset_yx[1])
    local_x = (
        cosine * delta_x + sine * delta_y + np.float32((width - 1) / 2.0)
    )
    local_y = (
        -sine * delta_x + cosine * delta_y + np.float32((height - 1) / 2.0)
    )
    return local_y, local_x


def _sample_mask(
    mask: np.ndarray,
    local_y: np.ndarray,
    local_x: np.ndarray,
    source_height: int,
    source_width: int,
) -> np.ndarray:
    mask_y = local_y * np.float32(
        (mask.shape[0] - 1) / max(source_height - 1, 1))
    mask_x = local_x * np.float32(
        (mask.shape[1] - 1) / max(source_width - 1, 1))
    return ndimage.map_coordinates(
        mask,
        (mask_y, mask_x),
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )


def _sample_source(
    source: np.ndarray,
    plan: ScrapPlan,
    local_y: np.ndarray,
    local_x: np.ndarray,
) -> np.ndarray:
    source_y, source_x, _height, _width = plan.source_yxhw
    coordinates = (
        local_y + np.float32(source_y),
        local_x + np.float32(source_x),
    )
    if source.ndim == 2:
        return ndimage.map_coordinates(
            source,
            coordinates,
            order=1,
            mode="constant",
            cval=255.0,
            prefilter=False,
        )
    return np.stack(
        tuple(
            ndimage.map_coordinates(
                source[..., channel],
                coordinates,
                order=1,
                mode="constant",
                cval=255.0,
                prefilter=False,
            )
            for channel in range(3)
        ),
        axis=2,
    )


def _fold(
    pixels: np.ndarray,
    plan: ScrapPlan,
    local_y: np.ndarray,
    local_x: np.ndarray,
) -> np.ndarray:
    if plan.fold_normal_xy is None:
        return pixels
    _source_y, _source_x, height, width = plan.source_yxhw
    normal_x, normal_y = plan.fold_normal_xy
    assert plan.fold_offset is not None
    assert plan.fold_width is not None
    normalized_x = local_x / max(width - 1, 1) - 0.5
    normalized_y = local_y / max(height - 1, 1) - 0.5
    signed = (
        np.float32(normal_x) * normalized_x
        + np.float32(normal_y) * normalized_y
        - np.float32(plan.fold_offset)
    )
    width_normalized = np.float32(plan.fold_width)
    result = pixels.astype(np.float32, copy=False)
    dark = np.exp(
        -0.5 * ((signed + width_normalized * 0.45)
                / width_normalized) ** 2)
    light = np.exp(
        -0.5 * ((signed - width_normalized * 0.70)
                / (width_normalized * 0.75)) ** 2)
    adjustment = -22.0 * dark + 11.0 * light
    if result.ndim == 3:
        result = result + adjustment[..., None]
    else:
        result = result + adjustment
    if plan.folded_back:
        flap = np.clip(
            signed / max(float(width_normalized) * 2.0, 1e-6),
            0.0,
            1.0,
        )
        backside = 246.0
        if result.ndim == 3:
            result = (
                result * (1.0 - 0.93 * flap[..., None])
                + backside * (0.93 * flap[..., None])
            )
        else:
            result = result * (1.0 - 0.93 * flap) + backside * (0.93 * flap)
    return np.clip(result, 0.0, 255.0)


def _bounds(
    plan: ScrapPlan,
    canvas_shape: tuple[int, ...],
    *,
    shadow: bool,
) -> tuple[int, int, int, int]:
    _source_y, _source_x, height, width = plan.source_yxhw
    content_y0, content_x0, content_y1, content_x1 = _content_bounds(plan)
    if shadow:
        shadow_y, shadow_x = plan.shadow_offset_yx
        pad = max(10.0, 0.02 * max(height, width))
        y0 = min(content_y0, content_y0 + shadow_y - pad)
        x0 = min(content_x0, content_x0 + shadow_x - pad)
        y1 = max(content_y1, content_y1 + shadow_y + pad)
        x1 = max(content_x1, content_x1 + shadow_x + pad)
    else:
        y0, x0, y1, x1 = (
            content_y0 - 2.0,
            content_x0 - 2.0,
            content_y1 + 2.0,
            content_x1 + 2.0,
        )
    return (
        max(0, int(math.floor(y0))),
        max(0, int(math.floor(x0))),
        min(canvas_shape[0], int(math.ceil(y1))),
        min(canvas_shape[1], int(math.ceil(x1))),
    )


def _composite_scrap(
    source: np.ndarray,
    canvas: np.memmap,
    plan: ScrapPlan,
) -> None:
    mask, shadow_mask = _masks(plan)
    _source_y, _source_x, source_height, source_width = plan.source_yxhw
    y0, x0, y1, x1 = _bounds(plan, canvas.shape, shadow=True)
    content_y0, content_x0, content_y1, content_x1 = _bounds(
        plan, canvas.shape, shadow=False)
    for stripe_y0 in range(y0, y1, _STRIPE_ROWS):
        stripe_y1 = min(stripe_y0 + _STRIPE_ROWS, y1)
        target = canvas[stripe_y0:stripe_y1, x0:x1].astype(
            np.float32, copy=True)
        shadow_y, shadow_x = _coordinates(
            plan,
            stripe_y0,
            stripe_y1,
            x0,
            x1,
            offset_yx=plan.shadow_offset_yx,
        )
        shadow_alpha = _sample_mask(
            shadow_mask,
            shadow_y,
            shadow_x,
            source_height,
            source_width,
        ) * np.float32(plan.shadow_strength)
        if target.ndim == 3:
            target *= 1.0 - shadow_alpha[..., None]
        else:
            target *= 1.0 - shadow_alpha

        overlap_y0 = max(stripe_y0, content_y0)
        overlap_y1 = min(stripe_y1, content_y1)
        overlap_x0 = max(x0, content_x0)
        overlap_x1 = min(x1, content_x1)
        if overlap_y1 > overlap_y0 and overlap_x1 > overlap_x0:
            local_y, local_x = _coordinates(
                plan,
                overlap_y0,
                overlap_y1,
                overlap_x0,
                overlap_x1,
            )
            alpha = _sample_mask(
                mask,
                local_y,
                local_x,
                source_height,
                source_width,
            )
            pixels = _fold(
                _sample_source(source, plan, local_y, local_x),
                plan,
                local_y,
                local_x,
            )
            target_y0 = overlap_y0 - stripe_y0
            target_y1 = overlap_y1 - stripe_y0
            target_x0 = overlap_x0 - x0
            target_x1 = overlap_x1 - x0
            selected = target[
                target_y0:target_y1, target_x0:target_x1]
            if target.ndim == 3:
                selected *= 1.0 - alpha[..., None]
                selected += pixels * alpha[..., None]
            else:
                selected *= 1.0 - alpha
                selected += pixels * alpha
        canvas[stripe_y0:stripe_y1, x0:x1] = np.clip(
            np.rint(target), 0, 255).astype(np.uint8)


def _open_source(path: Path) -> np.ndarray:
    try:
        return tifffile.memmap(path, mode="r")
    except ValueError:
        # Compressed TIFFs cannot be mapped in place.  tifffile decompresses
        # them into an anonymous disk-backed mapping instead of heap RAM.
        return tifffile.imread(path, out="memmap")


def _write_page(
    source: np.ndarray,
    staged: Path,
    facts: _RasterFacts,
    plans: tuple[ScrapPlan, ...],
) -> None:
    byte_count = int(np.prod(facts.shape, dtype=np.int64))
    canvas = tifffile.memmap(
        staged,
        shape=facts.shape,
        dtype=np.uint8,
        photometric=facts.photometric,
        bigtiff=byte_count >= 2**32,
        resolution=(facts.dpi, facts.dpi),
        resolutionunit="INCH",
    )
    try:
        for y0 in range(0, facts.height, 1024):
            canvas[y0:min(y0 + 1024, facts.height)] = _UINT8_MAX
        for plan in plans:
            _composite_scrap(source, canvas, plan)
        canvas.flush()
    finally:
        mmap = getattr(canvas, "_mmap", None)
        if mmap is not None:
            mmap.close()


def generate_scrap_scans(
    source_tiff: Path,
    output_tiff: Path,
    parameters: ScrapScanParameters,
) -> tuple[Path, ...]:
    """Generate deterministic scan TIFFs and refuse every overwrite."""
    if not isinstance(parameters, ScrapScanParameters):
        raise TypeError("parameters must be ScrapScanParameters")
    source_path = Path(source_tiff)
    output = Path(output_tiff)
    facts = _raster_facts(source_path)
    outputs = _output_paths(output, parameters.pages)
    if not output.parent.is_dir():
        raise FileNotFoundError(output.parent)
    existing = tuple(path for path in outputs if path.exists())
    if existing:
        raise FileExistsError(existing[0])

    staging_directory = Path(tempfile.mkdtemp(
        prefix=".holo-scrap-scan-",
        dir=output.parent,
    ))
    staged = tuple(staging_directory / path.name for path in outputs)
    source: np.ndarray | None = None
    published: list[Path] = []
    try:
        source = _open_source(source_path)
        for page_index, staged_path in enumerate(staged):
            plans = plan_scrap_page(
                facts.shape,
                facts.dpi,
                parameters,
                page_index=page_index,
            )
            _write_page(source, staged_path, facts, plans)
        for staged_path, output_path in zip(staged, outputs, strict=True):
            os.link(staged_path, output_path)
            published.append(output_path)
    except BaseException:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        mmap = getattr(source, "_mmap", None) if source is not None else None
        if mmap is not None:
            mmap.close()
        for path in staged:
            path.unlink(missing_ok=True)
        staging_directory.rmdir()
    return outputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cut one TIFF into deterministic torn/folded scraps and compose "
            "one or more scan-sized TIFF pages."
        ),
    )
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "output",
        type=Path,
        help=(
            "output TIFF; with --pages > 1, numbered suffixes are inserted"
        ),
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="number of scan pages (default: 1)",
    )
    parser.add_argument(
        "--scraps",
        type=int,
        default=12,
        help="scraps placed on each scan page (default: 12)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="unsigned 64-bit realization selector (default: 0)",
    )
    parser.add_argument(
        "--size-mm",
        type=float,
        nargs=2,
        metavar=("MIN", "MAX"),
        default=(28.0, 105.0),
        help="long-edge range in millimetres (default: 28 105)",
    )
    parser.add_argument(
        "--tear-mm",
        type=float,
        default=1.4,
        help="typical contour displacement in millimetres (default: 1.4)",
    )
    parser.add_argument(
        "--fold-probability",
        type=float,
        default=0.30,
        help="per-scrap crease probability (default: 0.30)",
    )
    parser.add_argument(
        "--flap-probability",
        type=float,
        default=0.35,
        help="conditional folded-back flap probability (default: 0.35)",
    )
    parser.add_argument(
        "--shadow-strength",
        type=float,
        default=0.12,
        help="paper shadow opacity in [0,1] (default: 0.12)",
    )
    arguments = parser.parse_args(argv)
    try:
        parameters = ScrapScanParameters(
            seed=arguments.seed,
            pages=arguments.pages,
            scraps_per_page=arguments.scraps,
            size_mm=tuple(arguments.size_mm),
            tear_mm=arguments.tear_mm,
            fold_probability=arguments.fold_probability,
            flap_probability=arguments.flap_probability,
            shadow_strength=arguments.shadow_strength,
        )
        outputs = generate_scrap_scans(
            arguments.source, arguments.output, parameters)
    except (FileExistsError, FileNotFoundError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
