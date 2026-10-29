"""The pose-resampled patch — the PIXELS of the patch family (W8 B3).

BLIND, and deliberately free of every analyzer module but
:mod:`analyzer.types`: this is `analyzer.patch`'s geometry half, split
out when the filter, the tiers and the self-training took the score past
DESIGN §0.4's 1000-line cap.  It knows how to lay a sample grid in CELL
coordinates, push it through a window's own 2x2 cell->pixel map and read
the raw crop there; it knows nothing about labels, folds or states.

`analyzer.patch` imports every name here and the spelling stays
`patch.extract`, `patch.grid_cells`, `patch.PatchError` for every caller
(the one exception is `EXTRACT_CHUNK_ROWS`, which `extract` reads from
THIS module's globals).
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
from scipy import ndimage

from .types import Crops

#: Rows per extraction chunk: at 576 features the pixel-coordinate
#: transient of one chunk is ~38 MB (APPROACHES ruling 13).
EXTRACT_CHUNK_ROWS: int = 4096


class PatchError(RuntimeError):
    """The patch score cannot be produced as asked."""


# ------------------------------------------------------------- the grid

def grid_shape(spec: Any, pitch_px_level: float) -> tuple[int, int]:
    """``(S, P)``: samples per cell (capped at the pitch) and per axis."""
    samples = int(min(int(spec.samples_per_cell),
                      max(1, int(round(float(pitch_px_level))))))
    per_axis = max(1, int(round(float(spec.window_cells) * samples)))
    return samples, per_axis


def grid_cells(spec: Any, pitch_px_level: float) -> np.ndarray:
    """(P*P, 2) sample offsets from the cell centre, in CELLS, (y, x).

    ``u_j = (j + 0.5) / S - window_cells / 2`` per axis, row-major over
    (y, x) — the pixel-step grid in local cell coordinates that
    `rectified_ncc` builds, without the rectification.
    """
    samples, per_axis = grid_shape(spec, pitch_px_level)
    axis = ((np.arange(per_axis, dtype=np.float64) + 0.5) / samples
            - float(spec.window_cells) / 2.0)
    grid_y, grid_x = np.meshgrid(axis, axis, indexing="ij")
    grid = np.stack((grid_y.ravel(), grid_x.ravel()), axis=1)
    grid.setflags(write=False)
    return grid


def ring_matrix(spec: Any, pitch_px_level: float) -> np.ndarray:
    """(P*P, n_rings) averaging matrix — P1c's radial means.

    Ring `k` is the samples whose radius from the cell centre falls in
    ``[k/S, (k+1)/S)`` cells, `S` samples per cell; there are ``P // 2``
    of them (the window's half-width in samples) and the last one absorbs
    everything beyond.  Each column is a mean over its ring, so the ring
    features are the pixel features reduced by one matrix multiply — one
    extraction serves both kinds.  A ring nobody falls in gets a zero
    column (a constant feature; the standardisation's ``sd + 1e-6``
    keeps the solve well posed).

    WHY (§4 B3): the radial mean is invariant to a rotation about the
    centre and moves LESS than a pixel does under a sub-pixel shift, so
    it is the cheap shift-robust variant of the same filter — 12 features
    per channel at 8 samples per cell against 144.
    """
    samples, per_axis = grid_shape(spec, pitch_px_level)
    grid = grid_cells(spec, pitch_px_level)
    n_rings = max(1, int(per_axis) // 2)
    radius = np.hypot(grid[:, 0], grid[:, 1]) * float(samples)
    index = np.clip(np.floor(radius).astype(np.int64), 0, n_rings - 1)
    matrix = np.zeros((grid.shape[0], n_rings), np.float64)
    matrix[np.arange(grid.shape[0]), index] = 1.0
    counts = matrix.sum(axis=0)
    matrix[:, counts > 0] /= counts[counts > 0]
    matrix.setflags(write=False)
    return matrix


def ring_features(features: np.ndarray, matrix: np.ndarray,
                  n_channels: int) -> np.ndarray:
    """Reduce a channel-major pixel feature block to radial means."""
    features = np.asarray(features, np.float32)
    per_channel = int(matrix.shape[0])
    if features.shape[1] != per_channel * int(n_channels):
        raise PatchError(f"ring_features: {features.shape[1]} features is "
                         f"not {n_channels} x {per_channel}")
    blocks = [features[:, index * per_channel:(index + 1) * per_channel]
              @ matrix.astype(np.float32)
              for index in range(int(n_channels))]
    return np.concatenate(blocks, axis=1)


# ------------------------------------------------------- the extraction

def extract(crops: Crops, points_yx: np.ndarray,
            linear_by_owner: Mapping[int, np.ndarray],
            owner_index: np.ndarray, rows: np.ndarray, grid: np.ndarray,
            channels: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Resample one patch per row at the read's pose.

    Returns ``(features (len(rows), P*P*len(channels)) float32,
    inside (len(rows),) bool)``.  Per owner, in chunks of
    `EXTRACT_CHUNK_ROWS` rows: ``pix = points[i] + grid @ L_owner.T`` —
    `grid` is (y, x) and so is `L`'s row order, so there is NO axis
    reversal here (`page_map.raster_points` reverses because ITS delta is
    (x, y)); ``local = pix - (y0, x0)``; a row is `inside` iff EVERY
    sample lies in ``[0, h-1] x [0, w-1]``, and the check comes BEFORE
    the resampling so a clamp can never be silent — a row that is not
    inside is NaN.  Features are channel-major, then sample.
    """
    if crops.raw_rgb is None:
        raise PatchError("the crops carry no raw pixels; open them with "
                         "keep_raw=True")
    rows = np.asarray(rows, np.int64)
    grid = np.asarray(grid, np.float64)
    channels = tuple(int(c) for c in channels)
    n_samples = int(grid.shape[0])
    features = np.full((rows.size, n_samples * len(channels)), np.nan,
                       np.float32)
    inside = np.zeros(rows.size, bool)
    if not rows.size:
        return features, inside
    raw = crops.raw_rgb
    height, width = int(raw.shape[0]), int(raw.shape[1])
    divisor = np.float32(crops.divisor)
    planes = {channel: np.asarray(raw[..., channel], np.float32) / divisor
              for channel in channels}
    origin = np.asarray((crops.y0, crops.x0), np.float64)
    owners = np.asarray(owner_index, np.int64)[rows]
    points = np.asarray(points_yx, np.float64)[rows]
    for owner in np.unique(owners).tolist():
        if owner < 0:
            continue
        linear = linear_by_owner.get(int(owner))
        if linear is None:
            continue
        offsets = grid @ np.asarray(linear, np.float64).T   # (n_samples, 2)
        where = np.flatnonzero(owners == owner)
        for start in range(0, where.size, int(EXTRACT_CHUNK_ROWS)):
            chunk = where[start:start + int(EXTRACT_CHUNK_ROWS)]
            centre = points[chunk] - origin
            pix = centre[:, None, :] + offsets[None, :, :]
            with np.errstate(invalid="ignore"):
                ok = (np.isfinite(pix).all(axis=(1, 2))
                      & (pix[..., 0] >= 0.0).all(axis=1)
                      & (pix[..., 0] <= height - 1).all(axis=1)
                      & (pix[..., 1] >= 0.0).all(axis=1)
                      & (pix[..., 1] <= width - 1).all(axis=1))
            good = chunk[ok]
            if not good.size:
                continue
            coords = pix[ok].reshape(-1, 2).T
            for index, channel in enumerate(channels):
                values = ndimage.map_coordinates(
                    planes[channel], coords, order=1, mode="nearest",
                    output=np.float32)
                features[good, index * n_samples:(index + 1) * n_samples] = \
                    values.reshape(good.size, n_samples)
            inside[good] = True
    return features, inside


