"""E021 structure-tensor scoring on bounded raster crops (carried leaf).

Copied and adapted from ``src/holo/receive/_survey_tensor.py`` under the
holo2 firewall (copy-and-adapt, never import).  This private module owns
the qualified tensor primitive and its overlap-safe whole-view tiling;
:mod:`holo2.capture.survey` re-exports the established helpers used by
qualification.

ONE adaptation: :func:`_whole_tensor_score` runs its tiles sequentially
inline instead of through ``holo.receive._parallel``.  holo2 gets its own
concurrency in H3, and the sequential form is bit-identical to the
original by that module's own contract (tiles are pure functions of
frozen raster bytes writing disjoint output slices, consumed in
submission order); it is literally the code path the original takes at
``--workers 1``, where ``submit_map`` returns ``None``.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from .scan import Raster


WORK_CELL_PX = 4.0
DERIVATIVE_CELLS = 0.22
TENSOR_CELLS = 0.30

TENSOR_TILE_CELLS = 256
"""Maximum output-grid side filtered in one whole-platen tensor tile."""


def tensor_geometry(cell_px: float) -> tuple[int, int, int]:
    """Return ``(input decimation, work pitch, native output step)``."""
    if not math.isfinite(cell_px) or cell_px <= 0:
        raise ValueError("cell_px must be finite and positive")
    decimation = max(1, int(round(cell_px / WORK_CELL_PX)))
    work_pitch = max(1, int(round(cell_px / decimation)))
    return decimation, work_pitch, decimation * work_pitch


def _minor_eigen_work(
    work: np.ndarray, *, pitch_work_px: float, sample: int
) -> np.ndarray:
    """Structure-tensor score for an already aperture-decimated crop."""
    image = np.asarray(work, np.float32)
    if image.ndim != 2:
        raise ValueError("tensor work image must be 2-D")
    if min(image.shape, default=0) < 3:
        return np.zeros((0, 0), np.float32)
    derivative_sigma = max(0.6, DERIVATIVE_CELLS * pitch_work_px)
    gx = ndimage.gaussian_filter(
        image, derivative_sigma, order=(0, 1), mode="nearest"
    ) * derivative_sigma
    gy = ndimage.gaussian_filter(
        image, derivative_sigma, order=(1, 0), mode="nearest"
    ) * derivative_sigma
    tensor_sigma = max(1.0, TENSOR_CELLS * pitch_work_px)
    jxx = ndimage.gaussian_filter(gx * gx, tensor_sigma, mode="nearest")
    jyy = ndimage.gaussian_filter(gy * gy, tensor_sigma, mode="nearest")
    jxy = ndimage.gaussian_filter(gx * gy, tensor_sigma, mode="nearest")
    trace = jxx + jyy
    discriminant = np.sqrt(
        np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0)
    )
    minor = np.sqrt(np.maximum(0.5 * (trace - discriminant), 0.0))
    height = minor.shape[0] // sample * sample
    width = minor.shape[1] // sample * sample
    if height == 0 or width == 0:
        return np.zeros((0, 0), np.float32)
    return minor[:height, :width].reshape(
        height // sample, sample, width // sample, sample
    ).mean(axis=(1, 3), dtype=np.float32)


def _block_mean(image: np.ndarray, factor: int) -> np.ndarray:
    """Historical float32 box aperture; trailing partial blocks are dropped."""
    if factor <= 1:
        return np.asarray(image, np.float32)
    height = image.shape[0] // factor * factor
    width = image.shape[1] // factor * factor
    if height == 0 or width == 0:
        return np.zeros((0, 0), np.float32)
    return np.asarray(image[:height, :width]).reshape(
        height // factor, factor, width // factor, factor
    ).mean(axis=(1, 3), dtype=np.float32)


def _minor_eigen_score_array(
    image: np.ndarray, pitch_px: float
) -> tuple[np.ndarray, int]:
    """Array oracle for the qualified E021 structure-tensor primitive."""
    decimation, sample, step = tensor_geometry(pitch_px)
    work = _block_mean(image, decimation)
    if min(work.shape, default=0) < 3:
        # Retain paperholo's historical small-crop return convention.
        return np.zeros((0, 0), np.float32), decimation
    return (
        _minor_eigen_work(
            work,
            pitch_work_px=pitch_px / decimation,
            sample=sample,
        ),
        step,
    )


def _tensor_halo_cells(pitch_work_px: float, sample: int) -> int:
    """Exact compact support of the two truncated Gaussian stages."""
    derivative = max(0.6, DERIVATIVE_CELLS * pitch_work_px)
    tensor = max(1.0, TENSOR_CELLS * pitch_work_px)
    derivative_radius = int(4.0 * derivative + 0.5)
    tensor_radius = int(4.0 * tensor + 0.5)
    work_halo = derivative_radius + tensor_radius
    return math.ceil(work_halo / sample)


def _score_crop(
    raster: Raster,
    *,
    pitch_px: float,
    box: tuple[int, int, int, int],
) -> tuple[np.ndarray, int]:
    """Score one exact native-coordinate crop with a crop-local aperture."""
    y0, y1, x0, x1 = box
    source = _feature_luma(raster, y0, y1, x0, x1)
    return _minor_eigen_score_array(source, pitch_px)


def _feature_luma(
    raster: Raster, r0: int, r1: int, c0: int, c1: int
) -> np.ndarray:
    """Unclipped E021 feature plane with stable 8/16-bit amplitude.

    The historical 16-bit contract represented an 8-bit scan multiplied by
    256 and divided it back before log-Otsu; preserve that convention.
    """
    luma = raster.crop_luma(r0, r1, c0, c1)
    return luma / np.float32(256.0) if raster.luma_max > 512.0 else luma


def _whole_tensor_score(
    raster: Raster,
    pitch_px: float,
    *,
    tile_cells: int = TENSOR_TILE_CELLS,
) -> tuple[np.ndarray, int]:
    """Whole-view score from oracle-qualified overlap-safe bounded tiles."""
    if isinstance(tile_cells, bool) or not isinstance(
            tile_cells, (int, np.integer)) or tile_cells < 1:
        raise ValueError("tile_cells must be a positive integer")
    decimation, sample, step = tensor_geometry(pitch_px)
    rows = raster.shape[0] // step
    cols = raster.shape[1] // step
    if rows == 0 or cols == 0:
        return np.zeros((0, 0), np.float32), step
    out = np.empty((rows, cols), np.float32)
    halo = _tensor_halo_cells(pitch_px / decimation, sample)
    tiles: list[tuple[int, int, int, int, int, int, int, int]] = []
    for row0 in range(0, rows, int(tile_cells)):
        row1 = min(rows, row0 + int(tile_cells))
        ext_row0 = max(0, row0 - halo)
        ext_row1 = min(rows, row1 + halo)
        for col0 in range(0, cols, int(tile_cells)):
            col1 = min(cols, col0 + int(tile_cells))
            ext_col0 = max(0, col0 - halo)
            ext_col1 = min(cols, col1 + halo)
            tiles.append((
                row0, row1, col0, col1,
                ext_row0, ext_row1, ext_col0, ext_col1,
            ))

    def _score_tile(
        tile: tuple[int, int, int, int, int, int, int, int],
    ) -> tuple[np.ndarray, int]:
        _row0, _row1, _col0, _col1 = tile[:4]
        ext_row0, ext_row1, ext_col0, ext_col1 = tile[4:]
        return _score_crop(
            raster,
            pitch_px=pitch_px,
            box=(
                ext_row0 * step,
                (raster.shape[0] // decimation * decimation
                 if ext_row1 == rows else ext_row1 * step),
                ext_col0 * step,
                (raster.shape[1] // decimation * decimation
                 if ext_col1 == cols else ext_col1 * step),
            ),
        )

    # Tiles are overlap-safe independent crops writing disjoint output
    # slices; scoring is a pure function of frozen raster bytes, so tile
    # order cannot change a value.  H2 runs them sequentially in
    # submission order — exactly the original's ``--workers 1`` path
    # (``_parallel.submit_map`` returns ``None`` there and the caller
    # falls back to ``map``).  H3 owns holo2 concurrency; when it lands,
    # the first tile must still complete before any task is submitted so
    # a lazily-derived lane raster materializes exactly once.
    results: list[tuple[np.ndarray, int]] = [_score_tile(tiles[0])]
    results.extend(_score_tile(tile) for tile in tiles[1:])
    for tile, (patch, patch_step) in zip(tiles, results, strict=True):
        row0, row1, col0, col1 = tile[:4]
        ext_row0, ext_row1, ext_col0, ext_col1 = tile[4:]
        if patch_step != step or patch.shape != (
                ext_row1 - ext_row0, ext_col1 - ext_col0):
            raise RuntimeError("tensor tile changed the E021 output grid")
        out[row0:row1, col0:col1] = patch[
            row0 - ext_row0 : row1 - ext_row0,
            col0 - ext_col0 : col1 - ext_col0,
        ]
    return out, step
