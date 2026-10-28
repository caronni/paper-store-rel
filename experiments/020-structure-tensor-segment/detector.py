"""Structure-tensor payload-field detector for experiment 020.

The smaller eigenvalue of the local gradient structure tensor is large only
when contrast varies in two directions. A payload lattice has that property;
a homogeneous backing, blank margin, or isolated paper edge does not.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class Candidate:
    bbox: tuple[int, int, int, int]
    area_mm2: float
    n_cells: int
    median_score: float


@dataclass(frozen=True)
class Detection:
    candidates: tuple[Candidate, ...]
    mask_cells: np.ndarray
    score_cells: np.ndarray
    threshold: float
    grid_step_px: int
    work_decimation: int


def _as_grey8(image: np.ndarray) -> np.ndarray:
    a = np.asarray(image)
    if a.ndim != 2:
        raise ValueError(f"expected a 2-D greyscale image, got {a.shape}")
    if a.dtype == np.uint8:
        return a
    out = a.astype(np.float32, copy=False)
    if out.size and float(np.nanmax(out)) > 255.5:
        out = out / 256.0
    return out


def _block_mean(a: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return np.asarray(a, np.float32)
    h = a.shape[0] // factor * factor
    w = a.shape[1] // factor * factor
    return np.asarray(a[:h, :w]).reshape(
        h // factor, factor, w // factor, factor
    ).mean(axis=(1, 3), dtype=np.float32)


def _adaptive_threshold(score: np.ndarray, sigma: float = 8.0) -> float:
    """Separate the unmodulated floor from sustained lattice texture.

    A platen acquisition is sparse: at least half its cell sites are backing,
    blank margin, or otherwise unmodulated. The lower half therefore estimates
    the scanner/stock texture floor without assuming an 8-bit contrast value.
    Log-space Otsu additionally captures textured real paper whose score lies
    above scanner noise but far below toner modulation. Taking the larger
    threshold prevents either background model from being permissive.
    """
    values = np.log1p(np.asarray(score, np.float64).ravel())
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.inf
    background = values[values <= np.median(values)]
    centre = float(np.median(background))
    mad = float(np.median(np.abs(background - centre)))
    robust_sd = max(1.4826 * mad, np.finfo(np.float32).eps)
    floor_threshold = float(np.expm1(centre + sigma * robust_sd))

    hist, edges = np.histogram(values, bins=256)
    probability = hist.astype(np.float64) / max(hist.sum(), 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    weight = np.cumsum(probability)
    mean = np.cumsum(probability * centres)
    total_mean = mean[-1]
    variance = (total_mean * weight - mean) ** 2 / np.maximum(
        weight * (1.0 - weight), np.finfo(np.float64).eps
    )
    split = int(np.argmax(variance[:-1]))
    otsu_threshold = float(np.expm1(centres[split]))
    return max(floor_threshold, otsu_threshold)


def detect(
    image: np.ndarray,
    *,
    cell_px: float,
    dpi: float,
    work_cell_px: float = 4.0,
    tensor_cells: float = 0.30,
    threshold_sigma: float = 12.0,
    density_min: int = 5,
    min_area_mm2: float = 9.0,
) -> Detection:
    """Find regions with sustained two-dimensional cell-scale modulation."""
    if cell_px <= 0 or dpi <= 0:
        raise ValueError("cell_px and dpi must be positive")
    if not 1 <= density_min <= 9:
        raise ValueError("density_min must be in [1, 9]")

    source = _as_grey8(image)
    decimation = max(1, int(round(cell_px / work_cell_px)))
    work = _block_mean(source, decimation)
    p = cell_px / decimation

    derivative_sigma = max(0.6, 0.22 * p)
    gx = ndimage.gaussian_filter(work, derivative_sigma, order=(0, 1),
                                 mode="nearest") * derivative_sigma
    gy = ndimage.gaussian_filter(work, derivative_sigma, order=(1, 0),
                                 mode="nearest") * derivative_sigma
    tensor_sigma = max(1.0, tensor_cells * p)
    jxx = ndimage.gaussian_filter(gx * gx, tensor_sigma, mode="nearest")
    jyy = ndimage.gaussian_filter(gy * gy, tensor_sigma, mode="nearest")
    jxy = ndimage.gaussian_filter(gx * gy, tensor_sigma, mode="nearest")
    trace = jxx + jyy
    disc = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0))
    minor = np.sqrt(np.maximum(0.5 * (trace - disc), 0.0))

    d = max(1, int(round(p)))
    score = _block_mean(minor, d)
    threshold = _adaptive_threshold(score, threshold_sigma)
    active = score > threshold
    neighbours = ndimage.convolve(active.astype(np.uint8),
                                   np.ones((3, 3), np.uint8),
                                   mode="constant", cval=0)
    region = active & (neighbours >= density_min)
    labels, _ = ndimage.label(region)
    px_per_mm = dpi / 25.4
    grid_step = decimation * d
    cell_area_mm2 = (grid_step / px_per_mm) ** 2

    kept = np.zeros_like(region)
    candidates: list[Candidate] = []
    for label_id, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        component = labels[sl] == label_id
        n_cells = int(component.sum())
        area = n_cells * cell_area_mm2
        if area < min_area_mm2:
            continue
        kept[sl] |= component
        y0 = sl[0].start * grid_step
        x0 = sl[1].start * grid_step
        h = component.shape[0] * grid_step
        w = component.shape[1] * grid_step
        candidates.append(Candidate(
            bbox=(y0, x0, h, w), area_mm2=area, n_cells=n_cells,
            median_score=float(np.median(score[sl][component])),
        ))
    candidates.sort(key=lambda c: -c.area_mm2)
    return Detection(tuple(candidates), kept, score, threshold, grid_step,
                     decimation)


def rasterize(detection: Detection, shape: tuple[int, int]) -> np.ndarray:
    """Expand a cell-grid detection into the source image frame."""
    step = detection.grid_step_px
    dense = np.repeat(np.repeat(detection.mask_cells, step, axis=0),
                      step, axis=1)
    out = np.zeros(shape, bool)
    out[:min(shape[0], dense.shape[0]), :min(shape[1], dense.shape[1])] = \
        dense[:shape[0], :shape[1]]
    return out
