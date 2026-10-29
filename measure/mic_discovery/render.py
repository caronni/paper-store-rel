"""The two pictures: the folded cell at lattice resolution and a 1:1
crop of the raw capture (plus its blue deficit, stretched)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .capture import Capture, blue_deficit, box_decimate, block_white

SITE_PX: int = 16


def cell_png(value: np.ndarray, path: Path) -> None:
    """Black = dot, white = empty, mid grey = never observed; a light
    grid between sites, the row/column order of the matrix."""
    rows, cols = value.shape
    img = np.full((rows * SITE_PX + 1, cols * SITE_PX + 1), 200, np.uint8)
    for r in range(rows):
        for c in range(cols):
            v = value[r, c]
            fill = 0 if v == 1 else 255 if v == 0 else 128
            img[r * SITE_PX + 1:(r + 1) * SITE_PX, c * SITE_PX + 1:(c + 1) * SITE_PX] = fill
    Image.fromarray(img).save(path)


def tiled(value_at, cols: int, rows: int) -> np.ndarray:
    """The infinite pattern over ``rows`` x ``cols`` sites from (0, 0) —
    a sheared cell (row shift ``b`` != 0) reads more easily tiled."""
    jj, ii = np.mgrid[0:rows, 0:cols]
    return value_at(ii, jj)


def crop_pngs(capture: Capture, centre_xy_mm: tuple[float, float], size_mm: float,
              white_rgb: tuple[float, float, float], raw_path: Path, deficit_path: Path) -> list[int]:
    """Native-resolution crop (no resampling) and its blue deficit with
    gain, so dots invisible to the eye in the raw crop show; returns the
    crop box ``[y0, x0, y1, x1]`` in capture pixels."""
    half = capture.px(size_mm / 2)
    cy, cx = capture.px(centre_xy_mm[1]), capture.px(centre_xy_mm[0])
    y0, x0 = max(0, cy - half), max(0, cx - half)
    y1, x1 = min(capture.height_px, cy + half), min(capture.width_px, cx + half)
    raw = np.asarray(capture.array[y0:y1, x0:x1, :3])
    Image.fromarray(raw).save(raw_path)
    rgb = box_decimate(raw, 1)
    white = block_white(rgb, max(rgb.shape[:2]), 0.85 * np.asarray(white_rgb, np.float32))
    d, _ = blue_deficit(rgb, white)
    Image.fromarray(np.clip(255 - d * 1200.0, 0, 255).astype(np.uint8)).save(deficit_path)
    return [int(y0), int(x0), int(y1), int(x1)]
