"""One pass over a colour capture: the yellow plane, the blank-paper map,
the dot candidates and a 600-dpi luma for the report-strip search.

The TIFF is memory-mapped and read in row bands, box-decimated to a
working resolution of ~1200 dpi (a 4800 capture by 4, a 2400 by 2), so
a 6.9 GB file never sits in memory whole.  Yellow toner absorbs blue:
after white balance on paper (per-channel reflectance against the
paper's own white, estimated per 10 mm block) the yellow plane is the
blue deficit ``d = (r + g) / 2 - b`` — cyan and magenta drive it
negative, black leaves it near zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

MM_PER_INCH: float = 25.4

#: Working resolution the band pass decimates to (dots per inch).
WORKING_DPI_TARGET: float = 1200.0

#: White balance: per-channel percentile inside a block, and the block.
WHITE_PERCENTILE: float = 90.0
WHITE_BLOCK_MM: float = 10.0

#: A pixel is C/M/K ink when red or green reflectance falls below this.
INK_RG_REFLECTANCE: float = 0.80

#: A 1 mm block is printed content when more than this fraction of its
#: pixels are C/M/K ink, or more than ``CONTENT_YELLOW_FRACTION`` of
#: them sit above the yellow threshold (a MIC dot covers ~2 % of a block).
CONTENT_INK_FRACTION: float = 0.01
CONTENT_YELLOW_FRACTION: float = 0.06

#: Content is dilated by this much before a block counts as blank paper:
#: toner scatter beside printed content images the content's own grid
#: (on the M681 at 2 mm the scatter carried a lattice of its own;
#: measured 2026-10-09), so only paper this far from any ink counts.
CONTENT_DILATE_MM: int = 6

#: A block is paper (not the platen lid or the scanner's dark border)
#: when its luma is within this fraction of the paper white.
PAPER_LUMA_FRACTION: float = 0.90

#: Yellow threshold: the deficit median plus this many robust sigmas,
#: never less than ``YELLOW_FLOOR`` reflectance units; blobs grow down to
#: ``YELLOW_LOW_SIGMAS`` (hysteresis) for centroid and area.
YELLOW_SIGMAS: float = 8.0
YELLOW_FLOOR: float = 0.03
YELLOW_LOW_SIGMAS: float = 4.0

#: Dot candidates: equivalent diameter bounds in mm.  The floor (~19 px
#: at 1200 dpi) sits above the paper specks (3-7 px) and the M281's
#: yellow background scatter (median 14 px), below the lattice dots
#: (2nd-percentile areas 32 px Canon, 79 VersaLink, 15-22 M681, 20 M281
#: — the HP dots are the faint ones); measured 2026-10-09.
DOT_MIN_DIAMETER_MM: float = 0.105
DOT_MAX_DIAMETER_MM: float = 0.45


@dataclass(frozen=True)
class Capture:
    """A memory-mapped RGB capture and its resolution."""

    path: Path
    array: np.ndarray
    dpi: float

    @property
    def height_px(self) -> int:
        return int(self.array.shape[0])

    @property
    def width_px(self) -> int:
        return int(self.array.shape[1])

    def mm(self, px: float) -> float:
        return float(px) / self.dpi * MM_PER_INCH

    def px(self, mm: float) -> int:
        return int(round(float(mm) / MM_PER_INCH * self.dpi))


def open_capture(path: Path) -> Capture:
    """Memory-map one RGB TIFF; refuses greyscale (yellow is invisible there)."""
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        tag = page.tags.get("XResolution")
        if tag is None:
            raise ValueError(f"{path}: no XResolution tag")
        num, den = tag.value
        dpi = float(num) / float(den)
    array = tifffile.memmap(path, mode="r")
    if array.ndim != 3 or array.shape[2] < 3:
        raise ValueError(f"{path}: not an RGB capture (shape {array.shape})")
    return Capture(path=Path(path), array=array, dpi=dpi)


def decimation_factor(dpi: float) -> int:
    return max(1, int(round(dpi / WORKING_DPI_TARGET)))


def box_decimate(native: np.ndarray, factor: int) -> np.ndarray:
    """Mean over ``factor`` x ``factor`` blocks, float32 in [0, 1] (two
    uint16 partial sums: four times faster than a float reduction)."""
    h = native.shape[0] // factor * factor
    w = native.shape[1] // factor * factor
    view = native[:h, :w, :3]
    if factor == 1:
        return np.asarray(view, dtype=np.float32) / np.float32(255.0)
    rows = view.reshape(h // factor, factor, w, 3).sum(axis=1, dtype=np.uint16)
    both = rows.reshape(h // factor, w // factor, factor, 3).sum(axis=2, dtype=np.uint16)
    return both.astype(np.float32) / np.float32(255.0 * factor * factor)


def block_white(rgb: np.ndarray, block_px: int, floor_rgb: np.ndarray) -> np.ndarray:
    """Per-pixel paper white: the per-channel percentile of each block,
    never below ``floor_rgb`` (a block that is all ink keeps the page's)."""
    h, w = rgb.shape[:2]
    by = max(1, -(-h // block_px))
    bx = max(1, -(-w // block_px))
    white = np.empty((by, bx, 3), np.float32)
    for iy in range(by):
        for ix in range(bx):
            tile = rgb[iy * block_px:(iy + 1) * block_px, ix * block_px:(ix + 1) * block_px]
            white[iy, ix] = np.percentile(tile.reshape(-1, 3), WHITE_PERCENTILE, axis=0)
    white = np.maximum(white, floor_rgb[None, None, :])
    return np.repeat(np.repeat(white, block_px, axis=0), block_px, axis=1)[:h, :w]


def blue_deficit(rgb: np.ndarray, white: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``d = (r + g) / 2 - b`` and ``min(r, g)`` in paper-relative reflectance."""
    refl = rgb / np.maximum(white, np.float32(1e-3))
    rg_min = np.minimum(refl[..., 0], refl[..., 1])
    d = 0.5 * (refl[..., 0] + refl[..., 1]) - refl[..., 2]
    return d.astype(np.float32), rg_min.astype(np.float32)


@dataclass(frozen=True)
class YellowStats:
    """Global paper white and the yellow threshold, from blank samples."""

    paper_white_rgb: tuple[float, float, float]
    deficit_median: float
    deficit_sigma: float
    threshold_high: float
    threshold_low: float


def yellow_stats(capture: Capture, *, samples_per_axis: int = 7,
                 sample_mm: float = 6.0) -> YellowStats:
    """Sample a deterministic grid of small windows; the blankest decide."""
    f = decimation_factor(capture.dpi)
    size = capture.px(sample_mm)
    ys = np.linspace(capture.px(15), capture.height_px - capture.px(15) - size, samples_per_axis)
    xs = np.linspace(capture.px(15), capture.width_px - capture.px(15) - size, samples_per_axis)
    tiles: list[np.ndarray] = []
    for y in ys.astype(int):
        for x in xs.astype(int):
            tiles.append(box_decimate(capture.array[y:y + size, x:x + size], f))
    scores = [float(t.reshape(-1, 3).mean(axis=0).min() - t.reshape(-1, 3).std(axis=0).max())
              for t in tiles]
    order = np.argsort(scores)[::-1][: max(4, len(tiles) // 6)]
    white = np.median([np.percentile(tiles[i].reshape(-1, 3), WHITE_PERCENTILE, axis=0)
                       for i in order], axis=0).astype(np.float32)
    values = []
    for i in order:
        d, rg = blue_deficit(tiles[i], white[None, None, :])
        values.append(d[rg > 0.9])
    pooled = np.concatenate(values)
    med = float(np.median(pooled))
    sigma = float(1.4826 * np.median(np.abs(pooled - med)))
    high = med + max(YELLOW_SIGMAS * sigma, YELLOW_FLOOR)
    low = med + max(YELLOW_LOW_SIGMAS * sigma, 0.5 * YELLOW_FLOOR)
    return YellowStats(paper_white_rgb=tuple(float(v) for v in white),
                       deficit_median=med, deficit_sigma=sigma,
                       threshold_high=high, threshold_low=low)


def detect_blobs(d: np.ndarray, stats: YellowStats, *, working_dpi: float,
                 y_offset_px: int = 0) -> np.ndarray:
    """Yellow-dot candidates in one working-resolution deficit map.

    Returns rows ``(y_px, x_px, area_px, mean_deficit)`` in working
    pixels, ``y_offset_px`` added; hysteresis: grown at the low
    threshold, kept when some pixel clears the high one and the area is
    dot-sized.  Per-label statistics by ``bincount`` (scipy's
    ``maximum`` sorts the whole band)."""
    low = d > stats.threshold_low
    labels, n = ndimage.label(low)
    if n == 0:
        return np.empty((0, 4), np.float64)
    yy, xx = np.nonzero(low)
    lab = labels[yy, xx]
    val = d[yy, xx].astype(np.float64)
    w = val - stats.threshold_low
    area = np.bincount(lab, minlength=n + 1)[1:].astype(np.float64)
    wsum = np.bincount(lab, weights=w, minlength=n + 1)[1:]
    cy = np.bincount(lab, weights=w * yy, minlength=n + 1)[1:] / np.maximum(wsum, 1e-12)
    cx = np.bincount(lab, weights=w * xx, minlength=n + 1)[1:] / np.maximum(wsum, 1e-12)
    mean = np.bincount(lab, weights=val, minlength=n + 1)[1:] / np.maximum(area, 1)
    high = np.bincount(lab[val > stats.threshold_high], minlength=n + 1)[1:] > 0
    px_mm = working_dpi / MM_PER_INCH
    amin = np.pi / 4 * (DOT_MIN_DIAMETER_MM * px_mm) ** 2
    amax = np.pi / 4 * (DOT_MAX_DIAMETER_MM * px_mm) ** 2
    keep = high & (area >= amin) & (area <= amax)
    return np.column_stack([cy[keep] + y_offset_px, cx[keep], area[keep], mean[keep]])


@dataclass
class PageMaps:
    """What one band pass keeps of a capture."""

    working_dpi: float
    factor: int
    block_px: int
    blocks_mm: float
    content: np.ndarray        # bool, per ~1 mm block: printed content
    paper: np.ndarray          # bool, per block: paper, not lid/border
    blank: np.ndarray          # bool, per block: paper, content dilated away
    blobs: np.ndarray          # (n, 4) y_px, x_px, area_px, peak at working dpi
    luma600: np.ndarray        # uint8, Rec.709 luma decimated to ~600 dpi
    luma600_dpi: float

    def blank_at_mm(self, y_mm: np.ndarray, x_mm: np.ndarray) -> np.ndarray:
        iy = np.floor(np.asarray(y_mm) / self.blocks_mm).astype(int)
        ix = np.floor(np.asarray(x_mm) / self.blocks_mm).astype(int)
        ok = (iy >= 0) & (ix >= 0) & (iy < self.blank.shape[0]) & (ix < self.blank.shape[1])
        out = np.zeros(np.shape(iy), bool)
        out[ok] = self.blank[iy[ok], ix[ok]]
        return out


def band_pass(capture: Capture, stats: YellowStats, *, band_blocks: int = 10) -> PageMaps:
    """Read the whole capture once, band by band (halo for blob seams)."""
    f = decimation_factor(capture.dpi)
    wdpi = capture.dpi / f
    block = int(round(wdpi / MM_PER_INCH))
    blocks_mm = block / wdpi * MM_PER_INCH
    white_block = int(round(WHITE_BLOCK_MM / blocks_mm)) * block
    h_work = capture.height_px // f
    w_work = capture.width_px // f
    nby, nbx = h_work // block, w_work // block
    content = np.zeros((nby, nbx), bool)
    lum_blocks = np.zeros((nby, nbx), np.float32)
    halo = block
    floor = 0.85 * np.asarray(stats.paper_white_rgb, np.float32)
    band = band_blocks * block
    blob_rows: list[np.ndarray] = []
    l600_factor = max(1, int(round(wdpi / 600.0)))
    luma_parts: list[np.ndarray] = []
    for y0 in range(0, nby * block, band):
        y1 = min(y0 + band, nby * block)
        a0, a1 = max(0, y0 - halo), min(h_work, y1 + halo)
        rgb = box_decimate(capture.array[a0 * f:a1 * f, : w_work * f], f)
        white = block_white(rgb, white_block, floor)
        d, rg = blue_deficit(rgb, white)
        core = slice(y0 - a0, y0 - a0 + (y1 - y0))
        dc, rgc = d[core, : nbx * block], rg[core, : nbx * block]
        rows = (y1 - y0) // block
        ink = (rgc < INK_RG_REFLECTANCE).reshape(rows, block, nbx, block).mean(axis=(1, 3))
        yel = (dc > stats.threshold_high).reshape(rows, block, nbx, block).mean(axis=(1, 3))
        content[y0 // block:y0 // block + rows] = (ink > CONTENT_INK_FRACTION) | (yel > CONTENT_YELLOW_FRACTION)
        luma = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
        lum_blocks[y0 // block:y0 // block + rows] = luma[core, : nbx * block].reshape(
            rows, block, nbx, block).mean(axis=(1, 3))
        blobs = detect_blobs(d, stats, working_dpi=wdpi, y_offset_px=a0)
        if len(blobs):
            inside = (blobs[:, 0] >= y0) & (blobs[:, 0] < y1)
            blob_rows.append(blobs[inside])
        lc = luma[core]
        hh = lc.shape[0] // l600_factor * l600_factor
        ww = lc.shape[1] // l600_factor * l600_factor
        l6 = lc[:hh, :ww].reshape(hh // l600_factor, l600_factor, ww // l600_factor,
                                  l600_factor).mean(axis=(1, 3))
        luma_parts.append(np.clip(l6 * 255.0 + 0.5, 0, 255).astype(np.uint8))
    paper_luma = float(0.2126 * stats.paper_white_rgb[0] + 0.7152 * stats.paper_white_rgb[1]
                       + 0.0722 * stats.paper_white_rgb[2])
    paper = lum_blocks > PAPER_LUMA_FRACTION * paper_luma
    paper = ndimage.binary_erosion(paper, iterations=2) | (paper & content)
    dil = ndimage.binary_dilation(content, iterations=CONTENT_DILATE_MM)
    blank = paper & ~dil
    blobs_all = np.concatenate(blob_rows) if blob_rows else np.empty((0, 4))
    return PageMaps(working_dpi=wdpi, factor=f, block_px=block, blocks_mm=blocks_mm,
                    content=content, paper=paper, blank=blank, blobs=blobs_all,
                    luma600=np.concatenate(luma_parts, axis=0), luma600_dpi=wdpi / l600_factor)
