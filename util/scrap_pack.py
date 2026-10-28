#!/usr/bin/env python3
"""Find payload-textured scraps, approve them, and pack them losslessly.

This is deliberately a standalone utility.  Its small structure-tensor front
end is copied from the coarse idea qualified by experiment e021, but this file
does not import paperholo or any experiment module.

Typical use::

    python util/scrap_pack.py scan.tiff
    python util/scrap_pack.py scan.png -o scan-packed.png --cell-px 24

``--cell-px`` is the nominal payload-cell pitch in the input raster.  It is 24
pixels for the common c3 payload scanned at 4800 dpi.  The coarse survey uses
roughly 8/3 of that pitch (64 pixels by default), and each detected box is
expanded by ``--margin-cells`` payload cells before packing.
"""
from __future__ import annotations

import argparse
import html
import os
import secrets
import tempfile
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import imagecodecs
import numpy as np
import tifffile
from PIL import Image, ImageDraw
from scipy import ndimage

TENSOR_SCORE_FLOOR = 0.003
FULL_PNG_VERIFY_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True, order=True)
class Box:
    """Half-open native-pixel rectangle, ``(y0, x0, y1, x1)``."""

    y0: int
    x0: int
    y1: int
    x1: int

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def width(self) -> int:
        return self.x1 - self.x0


@dataclass(frozen=True)
class Raster:
    """Depth-preserving input raster."""

    array: np.ndarray
    path: Path


@dataclass(frozen=True)
class Placement:
    """Placement of one source box on the packed canvas."""

    source_index: int
    y: int
    x: int
    rotated: bool = False


def _validate_raster(array: np.ndarray, path: Path) -> np.ndarray:
    a = np.asarray(array)
    if a.ndim == 3 and a.shape[-1] not in (3, 4):
        if a.shape[0] in (3, 4):
            a = np.moveaxis(a, 0, -1)
        else:
            raise ValueError(
                f"{path}: expected grey, RGB, or RGBA; got shape {a.shape}"
            )
    elif a.ndim not in (2, 3):
        raise ValueError(
            f"{path}: expected one image, not shape {a.shape}"
        )
    if a.dtype.kind != "u" or a.dtype.itemsize not in (1, 2):
        raise ValueError(
            f"{path}: expected unsigned 8- or 16-bit samples; got {a.dtype}"
        )
    return a


def load_image(path: str | Path) -> Raster:
    """Load one TIFF or PNG without reducing its sample depth."""

    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in (".tif", ".tiff"):
        with tifffile.TiffFile(source) as tif:
            if len(tif.series) != 1:
                raise ValueError(f"{source}: expected one TIFF image series")
            axes = tif.series[0].axes
            if any(axis in axes for axis in "TZQ"):
                raise ValueError(
                    f"{source}: expected a single-page TIFF, axes={axes!r}"
                )
            page = tif.series[0].pages[0]
            photometric = getattr(
                page.photometric, "name", str(page.photometric)
            ).upper()
            if photometric not in {"MINISBLACK", "RGB"}:
                detail = (
                    "CMYK/Separated" if photometric == "SEPARATED"
                    else photometric
                )
                raise ValueError(
                    f"{source}: unsupported TIFF photometric {detail}; "
                    "expected MINISBLACK grey or RGB(A)"
                )
            orientation_tag = page.tags.get("Orientation")
            orientation = (
                int(orientation_tag.value) if orientation_tag is not None else 1
            )
            if orientation != 1:
                raise ValueError(
                    f"{source}: unsupported TIFF orientation {orientation}; "
                    "normalize to top-left first"
                )
            if int(page.samplesperpixel) == 4:
                extras = {
                    getattr(value, "name", str(value)).upper()
                    for value in page.extrasamples
                }
                if photometric != "RGB" or extras != {"UNASSALPHA"}:
                    raise ValueError(
                        f"{source}: four-channel TIFF must be RGB with one "
                        "unassociated alpha channel"
                    )
        try:
            array = tifffile.imread(source, out="memmap")
        except Exception:
            array = tifffile.imread(source)
    elif suffix == ".png":
        # Pillow down-converts RGB16 PNG.  imagecodecs/libpng does not.
        array = imagecodecs.imread(source, codec="png", memmap=False)
    else:
        raise ValueError(f"{source}: input must be TIFF or PNG")
    return Raster(_validate_raster(array, source), source)


def _source_block_mean(array: np.ndarray, factor: int) -> np.ndarray:
    """Block-average a possibly huge/memory-mapped raster in short bands."""

    h = array.shape[0] // factor * factor
    w = array.shape[1] // factor * factor
    if h == 0 or w == 0:
        return np.zeros((0, 0), np.float32)
    oh, ow = h // factor, w // factor
    out = np.empty((oh, ow), np.float32)
    scale = float(np.iinfo(array.dtype).max)
    # Eight output rows bounds color-RGB16 temporaries even on wide scans.
    for oy0 in range(0, oh, 8):
        oy1 = min(oh, oy0 + 8)
        source = array[oy0 * factor:oy1 * factor, :w]
        if source.ndim == 2:
            work = np.asarray(source, np.float32)
            out[oy0:oy1] = work.reshape(
                oy1 - oy0, factor, ow, factor
            ).mean(axis=(1, 3), dtype=np.float32) / scale
        else:
            target = np.zeros((oy1 - oy0, ow), np.float32)
            if source.shape[-1] == 4:
                alpha = np.asarray(source[..., 3], np.float32) / scale
                transparent = 1.0 - alpha
                for channel in range(3):
                    work = np.asarray(source[..., channel], np.float32) / scale
                    visible = work * alpha + transparent
                    target += visible.reshape(
                        oy1 - oy0, factor, ow, factor
                    ).mean(axis=(1, 3), dtype=np.float32) / 3.0
            else:
                for channel in range(3):
                    work = np.asarray(source[..., channel], np.float32)
                    target += work.reshape(
                        oy1 - oy0, factor, ow, factor
                    ).mean(axis=(1, 3), dtype=np.float32) / (3.0 * scale)
            out[oy0:oy1] = target
    return out


def _block_mean(array: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return np.asarray(array, np.float32)
    h = array.shape[0] // factor * factor
    w = array.shape[1] // factor * factor
    if h == 0 or w == 0:
        return np.zeros((0, 0), np.float32)
    return np.asarray(array[:h, :w], np.float32).reshape(
        h // factor, factor, w // factor, factor
    ).mean(axis=(1, 3), dtype=np.float32)


def _tensor_score(
    array: np.ndarray, cell_px: float
) -> tuple[np.ndarray, np.ndarray, int]:
    """Coarse rotation-neutral two-dimensional texture score."""

    survey_px = max(3.0, float(cell_px) * (8.0 / 3.0))
    decimation = max(1, int(round(survey_px / 4.0)))
    work_pitch = max(1, int(round(survey_px / decimation)))
    step = decimation * work_pitch
    work = _source_block_mean(array, decimation)
    if min(work.shape, default=0) < 3:
        empty = np.zeros((0, 0), np.float32)
        return empty, empty, step

    derivative_sigma = max(0.6, 0.22 * work_pitch)
    gx = ndimage.gaussian_filter(
        work, derivative_sigma, order=(0, 1), mode="nearest"
    ) * derivative_sigma
    gy = ndimage.gaussian_filter(
        work, derivative_sigma, order=(1, 0), mode="nearest"
    ) * derivative_sigma
    tensor_sigma = max(1.0, 0.30 * work_pitch)
    jxx = ndimage.gaussian_filter(gx * gx, tensor_sigma, mode="nearest")
    jyy = ndimage.gaussian_filter(gy * gy, tensor_sigma, mode="nearest")
    jxy = ndimage.gaussian_filter(gx * gy, tensor_sigma, mode="nearest")
    trace = jxx + jyy
    disc = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0))
    minor = np.sqrt(np.maximum(0.5 * (trace - disc), 0.0))
    # Local variance is a narrow anti-aliasing safety arm.  It catches dense
    # texture that happens to land at the derivative grid's Nyquist frequency;
    # a 3x3 opening in detect_boxes prevents isolated paper edges from using it.
    local_mean = ndimage.gaussian_filter(work, tensor_sigma, mode="nearest")
    local_variance = np.maximum(
        ndimage.gaussian_filter(work * work, tensor_sigma, mode="nearest")
        - local_mean * local_mean,
        0.0,
    )
    texture = np.sqrt(local_variance)
    return (
        _block_mean(minor, work_pitch),
        _block_mean(texture, work_pitch),
        step,
    )


def _otsu_log_threshold(score: np.ndarray) -> float:
    values = np.log1p(np.asarray(score, np.float64).ravel())
    values = values[np.isfinite(values)]
    if values.size == 0 or float(np.ptp(values)) <= np.finfo(float).eps:
        return np.inf
    hist, edges = np.histogram(values, bins=256)
    probability = hist.astype(np.float64) / max(int(hist.sum()), 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    weight = np.cumsum(probability)
    mean = np.cumsum(probability * centres)
    variance = (mean[-1] * weight - mean) ** 2 / np.maximum(
        weight * (1.0 - weight), np.finfo(np.float64).eps
    )
    return float(np.expm1(centres[int(np.argmax(variance[:-1]))]))


def detect_boxes(
    array: np.ndarray,
    *,
    cell_px: float = 24.0,
    margin_cells: float = 4.0,
    min_blocks: int = 80,
) -> list[Box]:
    """Return margin-inclusive payload-texture boxes in native coordinates.

    The detector itself is coarse.  Bounding boxes, rather than detailed masks,
    deliberately absorb internal texture holes.  Expansion is in nominal
    payload cells.  Components remain independent even if their rectangular
    margins overlap; rotated scraps often have harmless overlapping corners.
    """

    image = _validate_raster(np.asarray(array), Path("<array>"))
    if cell_px <= 0 or margin_cells < 0 or min_blocks <= 0:
        raise ValueError(
            "cell_px/min_blocks must be positive; margin nonnegative"
        )
    score, texture, step = _tensor_score(image, cell_px)
    if score.size == 0:
        return []
    threshold = max(_otsu_log_threshold(score), TENSOR_SCORE_FLOOR)
    tensor_active = score > threshold
    neighbours = ndimage.convolve(
        tensor_active.astype(np.uint8), np.ones((3, 3), np.uint8),
        mode="constant", cval=0,
    )
    tensor_active &= neighbours >= 5
    texture_threshold = max(_otsu_log_threshold(texture), 0.02)
    # The qualified tensor statistic stays authoritative.  Use the variance
    # arm only as an anti-alias fallback when the tensor arm has no component
    # large enough to emit; unioning both can create tiny bridges between two
    # otherwise independent real scraps.
    tensor_labels, tensor_count = ndimage.label(tensor_active)
    tensor_sizes = ndimage.sum(
        tensor_active,
        tensor_labels,
        index=np.arange(1, tensor_count + 1),
    )
    if np.any(np.asarray(tensor_sizes) >= min_blocks):
        active = tensor_active
    else:
        active = ndimage.binary_opening(
            ndimage.binary_fill_holes(texture > texture_threshold),
            structure=np.ones((3, 3), bool),
        )
    labels, _ = ndimage.label(active)
    margin = int(round(margin_cells * cell_px))
    height, width = image.shape[:2]
    boxes: list[Box] = []
    for label_id, slices in enumerate(ndimage.find_objects(labels), start=1):
        if slices is None:
            continue
        component = labels[slices] == label_id
        if int(component.sum()) < min_blocks:
            continue
        y0 = max(0, slices[0].start * step - margin)
        x0 = max(0, slices[1].start * step - margin)
        y1 = min(height, slices[0].stop * step + margin)
        x1 = min(width, slices[1].stop * step + margin)
        if y1 > y0 and x1 > x0:
            boxes.append(Box(y0, x0, y1, x1))
    return sorted(boxes)


@dataclass(frozen=True)
class _Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


def _intersects(a: _Rect, b: _Rect) -> bool:
    return not (
        a.right <= b.x or b.right <= a.x
        or a.bottom <= b.y or b.bottom <= a.y
    )


def _split_free(free: _Rect, used: _Rect) -> list[_Rect]:
    if not _intersects(free, used):
        return [free]
    out: list[_Rect] = []
    if used.x > free.x:
        out.append(_Rect(free.x, free.y, used.x - free.x, free.height))
    if used.right < free.right:
        out.append(_Rect(
            used.right, free.y, free.right - used.right, free.height
        ))
    if used.y > free.y:
        out.append(_Rect(free.x, free.y, free.width, used.y - free.y))
    if used.bottom < free.bottom:
        out.append(_Rect(
            free.x, used.bottom, free.width, free.bottom - used.bottom
        ))
    return [r for r in out if r.width > 0 and r.height > 0]


def _prune_free(rectangles: list[_Rect]) -> list[_Rect]:
    out: list[_Rect] = []
    for index, rect in enumerate(rectangles):
        contained = False
        for other_index, other in enumerate(rectangles):
            if index == other_index:
                continue
            if (
                rect.x >= other.x and rect.y >= other.y
                and rect.right <= other.right and rect.bottom <= other.bottom
            ):
                contained = True
                break
        if not contained and rect not in out:
            out.append(rect)
    return out


def _pack_at_width(
    boxes: list[Box], order: list[int], bin_width: int
) -> tuple[list[Placement], int, int] | None:
    max_height = sum(max(box.height, box.width) for box in boxes)
    free = [_Rect(0, 0, bin_width, max_height)]
    placements: list[Placement] = []
    used_rects: list[_Rect] = []
    for source_index in order:
        box = boxes[source_index]
        choices: list[tuple[tuple[int, int, int, int], _Rect, bool]] = []
        orientations = [(box.width, box.height, False)]
        if box.height != box.width:
            orientations.append((box.height, box.width, True))
        for free_rect in free:
            for width, height, rotated in orientations:
                if width <= free_rect.width and height <= free_rect.height:
                    rect = _Rect(free_rect.x, free_rect.y, width, height)
                    short = min(
                        free_rect.width - width, free_rect.height - height
                    )
                    choices.append((
                        (rect.bottom, short,
                         free_rect.width * free_rect.height - width * height,
                         rect.x),
                        rect,
                        rotated,
                    ))
        if not choices:
            return None
        _score, placed, rotated = min(choices, key=lambda item: item[0])
        placements.append(Placement(
            source_index, placed.y, placed.x, rotated
        ))
        used_rects.append(placed)
        split: list[_Rect] = []
        for free_rect in free:
            split.extend(_split_free(free_rect, placed))
        free = _prune_free(split)
    height = max(rect.bottom for rect in used_rects)
    width = max(rect.right for rect in used_rects)
    return placements, height, width


def pack_boxes(boxes: Iterable[Box]) -> tuple[list[Placement], int, int]:
    """Deterministically search compact non-overlapping rectangle layouts."""

    items = list(boxes)
    if not items:
        return [], 0, 0
    if any(box.height <= 0 or box.width <= 0 for box in items):
        raise ValueError("cannot pack an empty box")
    total_area = sum(box.height * box.width for box in items)
    lower = max(min(box.height, box.width) for box in items)
    upper = sum(max(box.height, box.width) for box in items)
    search_upper = min(
        upper, max(lower, int(np.ceil(np.sqrt(total_area) * 3)))
    )
    widths = set(int(value) for value in np.linspace(
        lower, search_upper, min(160, max(2, search_upper - lower + 1))
    ))
    widths.update(
        dimension
        for box in items
        for dimension in (box.width, box.height)
        if lower <= dimension <= search_upper
    )
    widths.add(upper)
    indices = list(range(len(items)))
    orders = [
        sorted(indices, key=lambda i: (
            -items[i].height * items[i].width,
            -max(items[i].height, items[i].width), i,
        )),
        sorted(indices, key=lambda i: (
            -max(items[i].height, items[i].width),
            -min(items[i].height, items[i].width), i,
        )),
        sorted(indices, key=lambda i: (-items[i].height, -items[i].width, i)),
        sorted(indices, key=lambda i: (-items[i].width, -items[i].height, i)),
        indices,
    ]
    best: tuple[tuple[int, int, int], list[Placement], int, int] | None = None
    for width in sorted(widths):
        for order in orders:
            result = _pack_at_width(items, order, width)
            if result is None:
                continue
            placements, height, used_width = result
            objective = (
                height * used_width,
                max(height, used_width),
                height + used_width,
            )
            if best is None or objective < best[0]:
                best = objective, placements, height, used_width
    if best is None:
        raise RuntimeError("rectangle packer found no layout")
    return best[1], best[2], best[3]


def _background_value(array: np.ndarray) -> np.ndarray | int:
    """Robust platen color from a sparse sample of the source border."""

    h, w = array.shape[:2]
    stride = max(1, max(h, w) // 4096)
    samples = [
        np.asarray(array[0, ::stride]),
        np.asarray(array[h - 1, ::stride]),
        np.asarray(array[::stride, 0]),
        np.asarray(array[::stride, w - 1]),
    ]
    joined = np.concatenate([
        sample.reshape(-1, array.shape[2]) if array.ndim == 3
        else sample.reshape(-1)
        for sample in samples
    ], axis=0)
    median = np.median(joined, axis=0)
    if array.ndim == 2:
        return int(round(float(median)))
    return np.rint(median).astype(array.dtype)


def compose_packed(
    array: np.ndarray,
    boxes: Iterable[Box],
    placements: Iterable[Placement],
    height: int,
    width: int,
) -> np.ndarray:
    """Build the packed raster without resampling or depth conversion."""

    source = _validate_raster(np.asarray(array), Path("<array>"))
    items = list(boxes)
    layout = list(placements)
    shape = (height, width) + (() if source.ndim == 2 else (source.shape[2],))
    canvas = np.empty(shape, dtype=source.dtype)
    canvas[...] = _background_value(source)
    for placement in layout:
        box = items[placement.source_index]
        crop = np.asarray(source[box.y0:box.y1, box.x0:box.x1])
        if placement.rotated:
            crop = np.rot90(crop)
        ph, pw = crop.shape[:2]
        canvas[
            placement.y:placement.y + ph,
            placement.x:placement.x + pw,
        ] = crop
    return canvas


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _save_png(path: Path, array: np.ndarray) -> None:
    best: bytes | None = None
    for strategy in (
        imagecodecs.PNG.STRATEGY.DEFAULT,
        imagecodecs.PNG.STRATEGY.FILTERED,
        imagecodecs.PNG.STRATEGY.RLE,
    ):
        encoded = imagecodecs.png_encode(
            array,
            level=imagecodecs.PNG.COMPRESSION.BEST,
            strategy=strategy,
            filter=imagecodecs.PNG.FILTER.ALL,
        )
        if best is None or len(encoded) < len(best):
            best = encoded
    assert best is not None
    if array.nbytes <= FULL_PNG_VERIFY_BYTES:
        decoded = imagecodecs.png_decode(best)
        if decoded.dtype != array.dtype or not np.array_equal(decoded, array):
            raise RuntimeError("PNG verification failed")
    elif not imagecodecs.png_check(best):
        raise RuntimeError("PNG integrity check failed")
    _atomic_bytes(path, best)


def _same_samples(first: np.ndarray, second: np.ndarray) -> bool:
    if first.shape != second.shape or first.dtype != second.dtype:
        return False
    for y0 in range(0, first.shape[0], 64):
        if not np.array_equal(first[y0:y0 + 64], second[y0:y0 + 64]):
            return False
    return True


def _save_tiff(path: Path, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    best: Path | None = None
    best_size: int | None = None
    settings = (
        ("zstd", {"level": 15}, True),
        ("zstd", {"level": 15}, False),
        ("deflate", {"level": 9}, True),
        ("deflate", {"level": 9}, False),
    )
    try:
        for compression, args, predictor in settings:
            descriptor, name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tiff", dir=path.parent
            )
            os.close(descriptor)
            candidate = Path(name)
            try:
                tifffile.imwrite(
                    candidate,
                    array,
                    photometric="rgb" if array.ndim == 3 else "minisblack",
                    extrasamples=(
                        "unassalpha"
                        if array.ndim == 3 and array.shape[2] == 4 else None
                    ),
                    compression=compression,
                    compressionargs=args,
                    predictor=predictor,
                    metadata=None,
                    bigtiff=array.nbytes >= 2**32,
                )
                size = candidate.stat().st_size
                if best_size is None or size < best_size:
                    if best is not None:
                        best.unlink(missing_ok=True)
                    best, best_size = candidate, size
                else:
                    candidate.unlink(missing_ok=True)
            except Exception:
                candidate.unlink(missing_ok=True)
        if best is None:
            raise RuntimeError("no TIFF compressor succeeded")
        decoded = tifffile.imread(best, out="memmap")
        try:
            if not _same_samples(decoded, array):
                raise RuntimeError("TIFF verification failed")
        finally:
            mmap = getattr(decoded, "_mmap", None)
            if mmap is not None:
                mmap.close()
        os.replace(best, path)
        best = None
    finally:
        if best is not None:
            best.unlink(missing_ok=True)


def save_lossless(path: str | Path, array: np.ndarray) -> Path:
    """Write the smallest verified candidate PNG or TIFF encoding."""

    target = Path(path)
    raster = _validate_raster(np.asarray(array), target)
    # PNG and several TIFF predictors expect native-endian words.  Endianness
    # is storage representation, not color depth; preserve numeric samples.
    if raster.dtype.itemsize == 2 and not raster.dtype.isnative:
        raster = raster.astype(np.uint16)
    raster = np.ascontiguousarray(raster)
    suffix = target.suffix.lower()
    if suffix == ".png":
        _save_png(target, raster)
    elif suffix in (".tif", ".tiff"):
        _save_tiff(target, raster)
    else:
        raise ValueError("output extension must be .png, .tif, or .tiff")
    return target


def _preview_png(array: np.ndarray, boxes: list[Box], max_width: int = 1800) -> bytes:
    h, w = array.shape[:2]
    stride = max(1, int(np.ceil(max(h, w) / max_width)))
    sample = np.asarray(array[::stride, ::stride])
    scale = float(np.iinfo(sample.dtype).max)
    if sample.ndim == 2:
        pixels = np.clip(sample.astype(np.float32) * (255.0 / scale), 0, 255)
        preview = Image.fromarray(pixels.astype(np.uint8), "L").convert("RGB")
    else:
        pixels = np.clip(
            sample[..., :3].astype(np.float32) * (255.0 / scale), 0, 255
        )
        preview = Image.fromarray(pixels.astype(np.uint8), "RGB")
        if sample.shape[-1] == 4:
            alpha = np.clip(
                sample[..., 3].astype(np.float32) * (255.0 / scale), 0, 255
            ).astype(np.uint8)
            visible = Image.new("RGB", preview.size, (255, 255, 255))
            visible.paste(preview, mask=Image.fromarray(alpha, "L"))
            preview = visible
    draw = ImageDraw.Draw(preview, "RGBA")
    for box in boxes:
        xy = (
            box.x0 / stride, box.y0 / stride,
            max(box.x0 / stride + 1, box.x1 / stride),
            max(box.y0 / stride + 1, box.y1 / stride),
        )
        draw.rectangle(
            xy, fill=(255, 140, 0, 35),
            outline=(255, 165, 0, 255), width=2,
        )
    import io

    buffer = io.BytesIO()
    preview.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def request_approval(
    preview_png: bytes,
    summary: str,
    *,
    port: int = 0,
    open_browser: bool = True,
) -> bool:
    """Show one local approval pane and block until Approve or Cancel."""

    token = secrets.token_urlsafe(18)
    decision = threading.Event()
    approved = False
    page = f"""<!doctype html><html><head><meta charset=\"utf-8\">
<title>Scrap pack review</title><style>
body{{margin:0;background:#171717;color:#eee;font:15px system-ui,sans-serif}}
main{{max-width:1900px;margin:auto;padding:18px}} img{{display:block;max-width:100%;
height:auto;background:#222}} .bar{{position:sticky;top:0;background:#171717ee;
padding:10px 0;z-index:2}} button{{font-size:16px;padding:9px 18px;margin-right:8px}}
.approve{{background:#247d3e;color:white;border:1px solid #58b970}}
.cancel{{background:#333;color:white;border:1px solid #777}}</style></head>
<body><main><div class=\"bar\"><div>{html.escape(summary)}</div>
<form method=\"post\" style=\"display:inline\" action=\"/{token}/approve\">
<button class=\"approve\">Approve and export</button></form>
<form method=\"post\" style=\"display:inline\" action=\"/{token}/cancel\">
<button class=\"cancel\">Cancel</button></form></div>
<img alt=\"Detected scrap regions\" src=\"/{token}/preview.png\"></main></body></html>"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def _send(self, code: int, content_type: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in (f"/{token}", f"/{token}/"):
                self._send(200, "text/html; charset=utf-8", page.encode())
            elif parsed.path == f"/{token}/preview.png":
                self._send(200, "image/png", preview_png)
            else:
                self._send(404, "text/plain", b"not found")

        def do_POST(self) -> None:  # noqa: N802
            nonlocal approved
            parsed = urlparse(self.path)
            if parsed.path == f"/{token}/approve":
                approved = True
            elif parsed.path == f"/{token}/cancel":
                approved = False
            else:
                self._send(404, "text/plain", b"not found")
                return
            decision.set()
            self._send(
                200, "text/html; charset=utf-8",
                b"<p>Decision received. You may close this pane.</p>",
            )

    server = ThreadingHTTPServer(("127.0.0.1", int(port)), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/{token}/"
    print(f"review: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        decision.wait()
    except KeyboardInterrupt:
        approved = False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
    return approved


def _default_output(path: Path) -> Path:
    suffix = ".tiff" if path.suffix.lower() in (".tif", ".tiff") else ".png"
    return path.with_name(f"{path.stem}-packed{suffix}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "image", type=Path, help="one 8/16-bit grey/RGB TIFF or PNG"
    )
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument(
        "--cell-px", type=float, default=24.0,
        help="nominal payload-cell pitch in scan pixels (default: 24)",
    )
    parser.add_argument(
        "--margin-cells", type=float, default=4.0,
        help="implicit box expansion in payload cells (default: 4)",
    )
    parser.add_argument(
        "--min-blocks", type=int, default=80,
        help="smallest coarse component to keep (default: 80 blocks)",
    )
    parser.add_argument(
        "--port", type=int, default=0,
        help="local review port; 0 chooses a free port",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="print the review URL without opening a browser",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="replace an existing output after approval",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    raster = load_image(args.image)
    print(
        f"loaded {raster.path}: {raster.array.shape}, {raster.array.dtype}; "
        f"cell={args.cell_px:g}px",
        flush=True,
    )
    boxes = detect_boxes(
        raster.array,
        cell_px=args.cell_px,
        margin_cells=args.margin_cells,
        min_blocks=args.min_blocks,
    )
    if not boxes:
        print("no payload-textured scraps found; no output written")
        return 2
    placements, packed_h, packed_w = pack_boxes(boxes)
    output = args.output or _default_output(raster.path)
    if output.exists() and not args.force:
        print(f"output already exists: {output} (use --force to replace it)")
        return 2
    summary = (
        f"{len(boxes)} segment{'s' if len(boxes) != 1 else ''}; "
        f"{raster.array.shape[1]}x{raster.array.shape[0]} -> "
        f"{packed_w}x{packed_h}; margin {args.margin_cells:g} cells; "
        f"output {output.name}"
    )
    preview = _preview_png(raster.array, boxes)
    if not request_approval(
        preview, summary, port=args.port, open_browser=not args.no_open
    ):
        print("cancelled; no output written")
        return 1
    packed = compose_packed(
        raster.array, boxes, placements, packed_h, packed_w
    )
    actual = save_lossless(output, packed)
    print(
        f"wrote {actual} ({actual.stat().st_size:,} bytes, "
        f"{packed.dtype}, shape {packed.shape})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
