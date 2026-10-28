#!/usr/bin/env python
"""Analyze one scanned E025 metrology page.

The analyzer keeps physical evidence and decoder evidence distinct.  It
decodes the print-time device strip, registers from chiral corners, measures
internal warp and typed physical probes, scores deterministic channel fields
with disjoint phase/train/validation populations, checks the small LDPC
coupons, derives physical and payload-safe printable extents, and reports
capacity from the measured rectangle.  Optional per-field trace bundles retain
the full state/features/scores evidence for later detector work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.ndimage import map_coordinates
from scipy.special import logsumexp

from paperholo import ldpc
from paperholo.metrology import (
    CandidateObservation,
    CandidateSpec,
    CaptureFooting,
    GridSpec,
    LdpcYield,
    report_document,
)

import e025_common as ec

Image.MAX_IMAGE_PIXELS = None

_EXP002 = Path(__file__).resolve().parents[1] / "002-calibration-page"
if str(_EXP002) not in sys.path:
    sys.path.insert(0, str(_EXP002))
import stripdec  # noqa: E402


def _sha256_file(path: Path, chunk: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(chunk):
            digest.update(data)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _verify_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != ec.SCHEMA:
        raise ValueError(f"unsupported E025 stimulus schema {manifest.get('schema')!r}")
    if manifest.get("layout_version") != ec.LAYOUT_VERSION:
        raise ValueError(
            f"unsupported E025 layout {manifest.get('layout_version')!r}; "
            f"expected {ec.LAYOUT_VERSION}"
        )
    expected = manifest.get("manifest_semantic_sha256")
    payload = dict(manifest)
    payload.pop("manifest_semantic_sha256", None)
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if actual != expected:
        raise ValueError(f"manifest semantic digest mismatch: {actual} != {expected}")


def _dtype_scale(dtype: np.dtype[Any]) -> float:
    return float(np.iinfo(dtype).max) if np.issubdtype(dtype, np.integer) else 1.0


class RasterSource:
    """Crop-oriented scan access; memory-map compatible TIFFs when possible."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._axes = ""
        self._memmapped = False
        if path.suffix.lower() in {".tif", ".tiff"}:
            try:
                import tifffile

                with tifffile.TiffFile(path) as tif:
                    self._axes = tif.series[0].axes
                self._array = tifffile.memmap(path)
                self._memmapped = True
            except Exception as exc:
                print(f"warning: TIFF is not memory-mappable ({exc}); using Pillow",
                      file=sys.stderr)
                self._array = np.asarray(Image.open(path))
        else:
            self._array = np.asarray(Image.open(path))
        self._configure()
        self.scale = _dtype_scale(self._array.dtype)

    def _configure(self) -> None:
        array, axes = self._array, self._axes
        if array.ndim == 2:
            self.height, self.width = array.shape
            self.channels, self._layout = 1, "YX"
        elif array.ndim == 3 and (axes.endswith("YXS") or
                                  (not axes and array.shape[-1] in (3, 4))):
            self.height, self.width, self.channels = array.shape
            self._layout = "YXS"
        elif array.ndim == 3 and (axes.endswith("SYX") or array.shape[0] in (3, 4)):
            self.channels, self.height, self.width = array.shape
            self._layout = "SYX"
        else:
            raise ValueError(f"unsupported scan shape {array.shape}, axes={axes!r}")

    @property
    def is_color(self) -> bool:
        return self.channels >= 3

    @property
    def memmapped(self) -> bool:
        return self._memmapped

    def crop_rgb(self, y0: int, y1: int, x0: int, x1: int) -> np.ndarray:
        y0, y1 = max(0, y0), min(self.height, y1)
        x0, x1 = max(0, x0), min(self.width, x1)
        if y1 <= y0 or x1 <= x0:
            raise ValueError("empty scan crop")
        if self._layout == "YX":
            array = self._array[y0:y1, x0:x1]
        elif self._layout == "YXS":
            array = self._array[y0:y1, x0:x1, :3]
        else:
            array = np.moveaxis(self._array[:3, y0:y1, x0:x1], 0, -1)
        out = np.asarray(array, dtype=np.float32) / self.scale
        if out.ndim == 2:
            out = np.repeat(out[:, :, None], 3, axis=2)
        return np.clip(out, 0.0, 1.0)

    def thumbnail_grey(self, scan_dpi_x: float, scan_dpi_y: float,
                       target_dpi: float = 300.0
                       ) -> tuple[np.ndarray, float, float]:
        fx = max(1, int(round(scan_dpi_x / target_dpi)))
        fy = max(1, int(round(scan_dpi_y / target_dpi)))
        out_w, out_h = self.width // fx, self.height // fy
        if min(out_w, out_h) <= 0:
            raise ValueError("scan smaller than one thumbnail block")
        out = np.empty((out_h, out_w), np.float32)
        for oy0 in range(0, out_h, 4):
            oy1 = min(out_h, oy0 + 4)
            source = self.crop_rgb(oy0 * fy, oy1 * fy, 0, out_w * fx)
            grey = (0.2126 * source[:, :, 0] + 0.7152 * source[:, :, 1]
                    + 0.0722 * source[:, :, 2])
            out[oy0:oy1] = grey.reshape(
                oy1 - oy0, fy, out_w, fx
            ).mean(axis=(1, 3), dtype=np.float32)
        return out, float(fx), float(fy)

    def crop_thumbnail_grey(self, y0: int, y1: int, x0: int, x1: int,
                            scan_dpi_x: float, scan_dpi_y: float,
                            target_dpi: float = 600.0) -> np.ndarray:
        """Block-mean one native crop without loading the full crop at once."""
        x0, x1 = max(0, x0), min(self.width, x1)
        y0, y1 = max(0, y0), min(self.height, y1)
        fx = max(1, int(round(scan_dpi_x / target_dpi)))
        fy = max(1, int(round(scan_dpi_y / target_dpi)))
        out_w, out_h = (x1 - x0) // fx, (y1 - y0) // fy
        if min(out_w, out_h) <= 0:
            raise ValueError("strip crop is smaller than one downsample block")
        out = np.empty((out_h, out_w), np.float32)
        for oy0 in range(0, out_h, 8):
            oy1 = min(out_h, oy0 + 8)
            source = self.crop_rgb(
                y0 + oy0 * fy, y0 + oy1 * fy,
                x0, x0 + out_w * fx,
            )
            grey = (0.2126 * source[:, :, 0] + 0.7152 * source[:, :, 1]
                    + 0.0722 * source[:, :, 2])
            out[oy0:oy1] = grey.reshape(
                oy1 - oy0, fy, out_w, fx
            ).mean(axis=(1, 3), dtype=np.float32)
        return out


def _detect_corners(grey: np.ndarray, target_dpi: float = 300.0
                    ) -> list[dict[str, Any]]:
    white, black = float(np.percentile(grey, 90)), float(np.percentile(grey, 1))
    labels, _ = ndimage.label(grey < white - 0.4 * (white - black))
    nominal = 123.0 * target_dpi / ec.BASE_DPI
    found: dict[int, dict[str, Any]] = {}
    for index, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        height, width = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (0.68 * nominal <= height <= 1.45 * nominal
                and 0.68 * nominal <= width <= 1.45 * nominal):
            continue
        mask = labels[sl] == index
        if not (0.025 <= float(mask.mean()) <= 0.18):
            continue
        local_y, local_x = int(np.argmax(mask.sum(axis=1))), int(np.argmax(mask.sum(axis=0)))
        yy, xx = np.nonzero(mask)
        crossness = float(np.mean(
            (np.abs(yy - local_y) <= 3) | (np.abs(xx - local_x) <= 3)
        ))
        if crossness < 0.65:
            continue
        cy, cx = sl[0].start + local_y, sl[1].start + local_x
        y0, y1 = max(0, sl[0].start - 6), min(grey.shape[0], sl[0].stop + 6)
        x0, x1 = max(0, sl[1].start - 6), min(grey.shape[1], sl[1].stop + 6)
        sub = labels[y0:y1, x0:x1]
        satellites = []
        for other in np.unique(sub):
            if other in (0, index):
                continue
            component = sub == other
            sy, sx = np.nonzero(component)
            if not len(sy):
                continue
            bh, bw = int(np.ptp(sy)) + 1, int(np.ptp(sx)) + 1
            if not (1 <= bh <= 9 and 1 <= bw <= 9 and component.sum() >= 3):
                continue
            dy, dx = float(sy.mean() + y0 - cy), float(sx.mean() + x0 - cx)
            if 3.0 <= math.hypot(dy, dx) <= 42.0:
                satellites.append((dy, dx))
        n_sat = len(satellites)
        if not 1 <= n_sat <= 4:
            continue
        candidate = {
            "n_sat": n_sat, "x_thumb": cx + 0.5, "y_thumb": cy + 0.5,
            "crossness": crossness,
            "inward": [int(np.sign(np.mean([v[0] for v in satellites]))),
                       int(np.sign(np.mean([v[1] for v in satellites])))],
        }
        if n_sat not in found or crossness > found[n_sat]["crossness"]:
            found[n_sat] = candidate
    return [found[key] for key in sorted(found)]


def _fit_affine(layout_xy: np.ndarray, scan_xy: np.ndarray
                ) -> tuple[np.ndarray, float]:
    n = len(layout_xy)
    design, target = np.zeros((2 * n, 6)), np.zeros(2 * n)
    for index, ((x, y), (u, v)) in enumerate(zip(layout_xy, scan_xy, strict=True)):
        design[2 * index, :3] = x, y, 1.0
        design[2 * index + 1, 3:] = x, y, 1.0
        target[2 * index:2 * index + 2] = u, v
    coef, *_ = np.linalg.lstsq(design, target, rcond=None)
    residual = design @ coef - target
    return coef, float(np.sqrt(np.mean(residual**2)))


def _affine_apply(coef: np.ndarray, x: np.ndarray,
                  y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a, b, c, d, e, f = coef
    return a * x + b * y + c, d * x + e * y + f


def register(source: RasterSource, page: dict[str, Any],
             scan_dpi_x: float, scan_dpi_y: float
             ) -> tuple[np.ndarray, dict[str, Any], np.ndarray, float, float]:
    thumb, fx, fy = source.thumbnail_grey(scan_dpi_x, scan_dpi_y)
    detected = {item["n_sat"]: item for item in _detect_corners(thumb)}
    expected = {
        int(item["satellites"]): item for item in page["infrastructure"]
        if item["kind"] == "corner_mark"
    }
    common = sorted(set(detected) & set(expected))
    if len(common) < 3:
        raise RuntimeError(f"found chiral corners {sorted(detected)}; need at least 3")
    layout = np.array([[expected[key]["cx_layout_dots"],
                        expected[key]["cy_layout_dots"]] for key in common])
    scan = np.array([[detected[key]["x_thumb"] * fx - 0.5,
                      detected[key]["y_thumb"] * fy - 0.5] for key in common])
    coef, rms = _fit_affine(layout, scan)
    a, b, _c, d, e, _f = coef
    scale_x, scale_y = math.hypot(a, d), math.hypot(b, e)
    geometry = {
        "corners_found": [{**detected[key], "x_scan": float(scan[i, 0]),
                            "y_scan": float(scan[i, 1])}
                           for i, key in enumerate(common)],
        "affine_layout_to_scan": coef.tolist(),
        "corner_fit_rms_px": rms,
        "px_per_layout_dot_x": scale_x,
        "px_per_layout_dot_y": scale_y,
        "nominal_px_per_layout_dot_x": scan_dpi_x / ec.BASE_DPI,
        "nominal_px_per_layout_dot_y": scan_dpi_y / ec.BASE_DPI,
        "scale_ratio_x": scale_x / (scan_dpi_x / ec.BASE_DPI),
        "scale_ratio_y": scale_y / (scan_dpi_y / ec.BASE_DPI),
        "rotation_deg": math.degrees(math.atan2(d, a)),
        "shear_deg": math.degrees(math.atan2(b, e)),
        "mirrored": bool(a * e - b * d < 0),
    }
    return coef, geometry, thumb, fx, fy


def _sample_scan_points(source: RasterSource, coef: np.ndarray,
                        x_layout: np.ndarray, y_layout: np.ndarray,
                        max_crop_pixels: int = 3_000_000) -> np.ndarray:
    """Sample arbitrary layout points without materializing a huge full crop."""
    shape = x_layout.shape
    px, py = _affine_apply(coef, x_layout.ravel(), y_layout.ravel())
    order = np.argsort(py)
    out = np.empty((len(px), 3), np.float32)
    start = 0
    while start < len(order):
        first = start
        chosen = [order[start]]
        x_min = x_max = float(px[order[start]])
        y_min = y_max = float(py[order[start]])
        start += 1
        while start < len(order) and len(chosen) < 65_536:
            idx = order[start]
            nx0, nx1 = min(x_min, float(px[idx])), max(x_max, float(px[idx]))
            ny0, ny1 = min(y_min, float(py[idx])), max(y_max, float(py[idx]))
            area = (nx1 - nx0 + 6.0) * (ny1 - ny0 + 6.0)
            if area > max_crop_pixels and len(chosen) >= 64:
                break
            chosen.append(idx)
            x_min, x_max, y_min, y_max = nx0, nx1, ny0, ny1
            start += 1
        indices = np.asarray(chosen, dtype=np.int64)
        x0 = max(0, int(math.floor(x_min)) - 2)
        x1 = min(source.width, int(math.ceil(x_max)) + 3)
        y0 = max(0, int(math.floor(y_min)) - 2)
        y1 = min(source.height, int(math.ceil(y_max)) + 3)
        if x1 <= x0 or y1 <= y0:
            raise RuntimeError("registered sample points lie outside the scan")
        crop = source.crop_rgb(y0, y1, x0, x1)
        coords = [py[indices] - y0, px[indices] - x0]
        out[indices] = np.stack([
            map_coordinates(crop[:, :, channel], coords, order=1, mode="nearest")
            for channel in range(3)
        ], axis=1)
        if start == first:  # defensive; the loop must always consume one point
            start += 1
    return out.reshape(shape + (3,))


def _cell_xy(field: dict[str, Any], grid: GridSpec,
             indices: np.ndarray, phase_x: float = 0.0,
             phase_y: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    iy, ix = np.divmod(indices, int(field["nx"]))
    pitch_x = ec.BASE_DPI * grid.c_x / grid.dpi_x
    pitch_y = ec.BASE_DPI * grid.c_y / grid.dpi_y
    x = float(field["x_layout_dots"]) + (ix + 0.5 + phase_x) * pitch_x
    y = float(field["y_layout_dots"]) + (iy + 0.5 + phase_y) * pitch_y
    return x.astype(np.float64), y.astype(np.float64)


def _sample_indices(source: RasterSource, coef: np.ndarray,
                    field: dict[str, Any], grid: GridSpec,
                    indices: np.ndarray, phase_x: float,
                    phase_y: float) -> np.ndarray:
    x, y = _cell_xy(field, grid, indices, phase_x, phase_y)
    return _sample_scan_points(source, coef, x, y)


def _sample_all_cells(source: RasterSource, coef: np.ndarray,
                      field: dict[str, Any], grid: GridSpec,
                      phase_x: float, phase_y: float,
                      aperture: float) -> np.ndarray:
    """Sample in row blocks; bound native scan work for 4800-dpi captures."""
    nx, ny = int(field["nx"]), int(field["ny"])
    a, b, _c, d, e, _f = coef
    px_cell_x = math.hypot(a, d) * ec.BASE_DPI * grid.c_x / grid.dpi_x
    px_cell_y = math.hypot(b, e) * ec.BASE_DPI * grid.c_y / grid.dpi_y
    field_width_px = max(1.0, nx * px_cell_x)
    rows_per_block = max(1, min(ny, int(2_500_000 / max(
        field_width_px * max(px_cell_y, 1.0), 1.0
    ))))
    out = np.empty((nx * ny, 3), np.float32)
    offsets = (0.0,) if aperture <= 0 else (-aperture, 0.0, aperture)
    for y0 in range(0, ny, rows_per_block):
        y1 = min(ny, y0 + rows_per_block)
        indices = np.arange(y0 * nx, y1 * nx, dtype=np.int64)
        samples = []
        for dy in offsets:
            for dx in offsets:
                samples.append(_sample_indices(
                    source, coef, field, grid, indices,
                    phase_x + dx, phase_y + dy,
                ))
        out[indices] = np.mean(np.stack(samples), axis=0)
    return out


def _features(rgb: np.ndarray, color: bool) -> np.ndarray:
    reflectance = np.clip(rgb, 1.0 / 65535.0, 1.0)
    density = -np.log10(reflectance)
    if color:
        return density.astype(np.float32)
    grey = (0.2126 * reflectance[:, 0] + 0.7152 * reflectance[:, 1]
            + 0.0722 * reflectance[:, 2])
    return (-np.log10(np.clip(grey, 1.0 / 65535.0, 1.0)))[:, None].astype(np.float32)


def _use_color_features(source: RasterSource,
                        definition: ec.ChannelDefinition) -> bool:
    """Keep pure K one-dimensional; retain RGB for every chromatic path."""
    return bool(source.is_color and definition.planes != ("K",))


def _split_indices(n_population: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    indices = np.arange(n_population, dtype=np.int64)
    phase = indices[indices % 8 == 0]
    train = indices[np.isin(indices % 8, (1, 2, 3))]
    validation = indices[np.isin(indices % 8, (4, 5, 6, 7))]
    return phase, train, validation


def _balanced_subset(indices: np.ndarray, states: np.ndarray,
                     n_states: int, per_state: int = 128) -> np.ndarray:
    selected = []
    flat = states.ravel()
    for state in range(n_states):
        where = indices[flat[indices] == state]
        if len(where) > per_state:
            pick = np.linspace(0, len(where) - 1, per_state).round().astype(int)
            where = where[pick]
        selected.append(where)
    if any(len(item) == 0 for item in selected):
        raise RuntimeError("phase population is missing a state")
    return np.sort(np.concatenate(selected))


def _separation(features: np.ndarray, labels: np.ndarray,
                n_states: int) -> float:
    overall = features.mean(axis=0)
    between = within = 0.0
    for state in range(n_states):
        group = features[labels == state]
        if len(group) < 2:
            return -math.inf
        mean = group.mean(axis=0)
        between += len(group) * float(np.sum((mean - overall) ** 2))
        within += float(np.sum((group - mean) ** 2))
    return between / max(within, 1e-12)


@dataclass(frozen=True)
class QDAModel:
    means: np.ndarray
    inverse_covariances: np.ndarray
    log_determinants: np.ndarray

    def scores(self, features: np.ndarray) -> np.ndarray:
        out = np.empty((len(features), len(self.means)), np.float32)
        for state in range(len(self.means)):
            delta = features - self.means[state]
            out[:, state] = -0.5 * (
                np.einsum("ij,jk,ik->i", delta,
                          self.inverse_covariances[state], delta)
                + self.log_determinants[state]
            )
        return out


def _fit_qda(features: np.ndarray, labels: np.ndarray,
             n_states: int) -> QDAModel:
    dimension = features.shape[1]
    means = np.empty((n_states, dimension), np.float64)
    inverse = np.empty((n_states, dimension, dimension), np.float64)
    logdet = np.empty(n_states, np.float64)
    for state in range(n_states):
        group = features[labels == state].astype(np.float64)
        if len(group) <= dimension + 1:
            raise RuntimeError(f"state {state} has only {len(group)} training cells")
        means[state] = group.mean(axis=0)
        covariance = np.atleast_2d(np.cov(group, rowvar=False))
        if dimension == 1:
            covariance = np.array([[max(float(covariance.ravel()[0]), 1e-6)]])
        else:
            scale = max(float(np.trace(covariance)) / dimension, 1e-6)
            covariance += np.eye(dimension) * (1e-3 * scale)
        inverse[state] = np.linalg.inv(covariance)
        logdet[state] = np.linalg.slogdet(covariance)[1]
    return QDAModel(means, inverse, logdet)


def _confusion(truth: np.ndarray, predicted: np.ndarray,
               n_states: int) -> np.ndarray:
    out = np.zeros((n_states, n_states), np.int64)
    np.add.at(out, (truth.astype(int), predicted.astype(int)), 1)
    return out


def _mutual_information(confusion: np.ndarray) -> float:
    joint = confusion.astype(np.float64)
    if joint.sum() == 0:
        return 0.0
    joint /= joint.sum()
    expected = joint.sum(axis=1, keepdims=True) @ joint.sum(axis=0, keepdims=True)
    nz = joint > 0
    return float(np.sum(joint[nz] * np.log2(joint[nz] / expected[nz])))


def _choose_phase(source: RasterSource, coef: np.ndarray,
                  field: dict[str, Any], grid: GridSpec,
                  states: np.ndarray, definition: ec.ChannelDefinition,
                  n_population: int) -> tuple[float, float, float]:
    phase_pool, _train, _validation = _split_indices(n_population)
    indices = _balanced_subset(phase_pool, states, len(definition.states))
    labels = states.ravel()[indices]
    use_color = _use_color_features(source, definition)
    values = (0.0, -0.20, 0.20, -0.40, 0.40)
    best = (-math.inf, 0.0, 0.0)
    for phase_y in values:
        for phase_x in values:
            rgb = _sample_indices(
                source, coef, field, grid, indices, phase_x, phase_y
            )
            score = _separation(
                _features(rgb, use_color), labels, len(definition.states)
            )
            if score > best[0]:
                best = score, phase_x, phase_y
    # Refine the winning basin.  The full +/-0.48-cell range is necessary at
    # page edges: a corner affine is a pose model, not a local lattice phase
    # oracle, and sub-cell corner-centroid bias can accumulate across A4.
    refine_x = tuple(np.clip(
        (best[1] - 0.10, best[1], best[1] + 0.10), -0.48, 0.48
    ))
    refine_y = tuple(np.clip(
        (best[2] - 0.10, best[2], best[2] + 0.10), -0.48, 0.48
    ))
    for phase_y in refine_y:
        for phase_x in refine_x:
            rgb = _sample_indices(
                source, coef, field, grid, indices,
                float(phase_x), float(phase_y),
            )
            score = _separation(
                _features(rgb, use_color), labels, len(definition.states)
            )
            if score > best[0]:
                best = score, float(phase_x), float(phase_y)
    return float(best[1]), float(best[2]), float(best[0])


# ---------------------------------------------------------------------------
# Windowed geometry (analyzer v3, opt-in via --geometry window).
#
# The v2 contract solved ONE global corner affine plus ONE constant sub-cell
# phase per field, with the phase search clamped to +/-0.48 cell.  Measured on
# the first physical pair (2026-07-18, Phase A of WORKPLAN-analyzer-v2.md) that
# model is falsified twice over:
#   * static offsets exceed the box: grid-control/600-c2 needs phase_y +1.30..
#     +1.60 cells and color pure/C/c2 needs +1.64..+2.28 cells;
#   * the true phase DRIFTS within one field: spatial/top/c3 ramps -0.43 ->
#     +0.80 cell top-to-bottom, which no constant phase can track.
# Both produce fields that read at or near chance while the ink is intact:
# re-sampling the same pixels with a per-band phase took spatial/top/c3 from
# 11.40% to 0.01% and grid-control/600-c2 from 43.04% to 2.82%.
#
# LABEL HYGIENE.  Geometry and lock decisions may only consume the phase split
# (index mod 8 == 0) and the QDA training split (1,2,3).  The validation split
# (4,5,6,7) is never allowed to influence pose, phase, model choice or the
# accept/refuse decision; it is only ever scored.  The phase search maximises
# class separation computed against the TRUE phase-split labels, which is also
# what breaks the mod-1-cell ambiguity a label-free lattice search would have.
# ---------------------------------------------------------------------------

WINDOW_TARGET_CELLS = 96
WINDOW_MIN_CELLS = 24
WINDOW_SEARCH_WIDE = 2.6      # cells; must exceed the measured 2.28-cell offset
WINDOW_SEARCH_LOCAL = 0.7     # cells around an inherited seed
WINDOW_PHASE_SAMPLE = 1400    # cells used by the search itself
WINDOW_LOCK_MAX_ERROR = 0.25  # phase-split error above which a window refuses


def _window_bounds(nx: int, ny: int, target: int = WINDOW_TARGET_CELLS
                   ) -> list[tuple[int, int, int, int]]:
    """Tile a field into near-square windows of ~target cells per side."""
    def cuts(n: int) -> list[tuple[int, int]]:
        if n <= target + WINDOW_MIN_CELLS:
            return [(0, n)]
        k = max(1, int(round(n / target)))
        edges = [int(round(i * n / k)) for i in range(k + 1)]
        return [(edges[i], edges[i + 1]) for i in range(k)]
    return [(y0, y1, x0, x1) for y0, y1 in cuts(ny) for x0, x1 in cuts(nx)]


def _window_indices(nx: int, bounds: tuple[int, int, int, int]) -> np.ndarray:
    y0, y1, x0, x1 = bounds
    rows = np.arange(y0, y1, dtype=np.int64)[:, None]
    cols = np.arange(x0, x1, dtype=np.int64)[None, :]
    return (rows * nx + cols).ravel()


def _phase_search(source: RasterSource, coef: np.ndarray, field: dict[str, Any],
                  grid: GridSpec, indices: np.ndarray, labels: np.ndarray,
                  n_states: int, use_color: bool, seed: tuple[float, float] | None
                  ) -> tuple[float, float, float]:
    """Coarse-to-fine phase search; wide and unclamped when there is no seed.

    Separation is computed against true phase-split labels, so sampling one
    whole cell off scores POORLY -- the integer-cell ambiguity is resolved.
    """
    def score(px: float, py: float) -> float:
        rgb = _sample_indices(source, coef, field, grid, indices, px, py)
        return _separation(_features(rgb, use_color), labels, n_states)

    if seed is None:
        span, step, base = WINDOW_SEARCH_WIDE, 0.1, (0.0, 0.0)
    else:
        span, step, base = WINDOW_SEARCH_LOCAL, 0.1, seed

    def better(value: float, px: float, py: float,
               best: tuple[float, float, float]) -> bool:
        """Strictly better, or an exact tie that sits closer to the base.

        The v2 estimator swept (0, -0.2, +0.2, -0.4, +0.4) with a strict '>',
        so a flat or degenerate score surface kept the first, NEGATIVE,
        candidate.  Measured over the first physical pair that bias is real:
        -0.48 appears 62 times against +0.48 35 times and 121 of 196 axes are
        negative (p = 0.0012).  Ties here resolve toward the base instead.
        """
        if value > best[0] + 1e-12:
            return True
        if value < best[0] - 1e-12:
            return False
        here = (px - base[0]) ** 2 + (py - base[1]) ** 2
        there = (best[1] - base[0]) ** 2 + (best[2] - base[1]) ** 2
        return here < there

    best = (-math.inf, base[0], base[1])
    for dy in np.arange(base[1] - span, base[1] + span + 1e-9, step):
        value = score(base[0], float(dy))
        if better(value, base[0], float(dy), best):
            best = (value, base[0], float(dy))
    for dx in np.arange(base[0] - span, base[0] + span + 1e-9, step):
        value = score(float(dx), best[2])
        if better(value, float(dx), best[2], best):
            best = (value, float(dx), best[2])
    # The coarse grid leaves at most half a step of error, so a +/-0.06 refine
    # at 0.03 cell is sufficient and three times cheaper than a wider grid.
    for dy in np.arange(best[2] - 0.06, best[2] + 0.06 + 1e-9, 0.03):
        for dx in np.arange(best[1] - 0.06, best[1] + 0.06 + 1e-9, 0.03):
            value = score(float(dx), float(dy))
            if better(value, float(dx), float(dy), best):
                best = (value, float(dx), float(dy))
    return best[1], best[2], best[0]


def _solve_windows(source: RasterSource, coef: np.ndarray, field: dict[str, Any],
                   grid: GridSpec, states: np.ndarray,
                   definition: ec.ChannelDefinition, n_population: int,
                   use_color: bool, aperture: float, nx: int, ny: int,
                   window_cells: int, field_phase: tuple[float, float],
                   ) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Per-window phase + local QDA.  Returns per-cell features and records.

    Windows are visited in raster order and inherit the previous accepted
    window's phase as a seed (the E022 chained-anchor pattern); only the first
    window, and any window whose local search fails, pays the wide search.

    FALLBACK CONTRACT: `field_phase` is the v2 whole-field solution.  Any window
    that cannot solve its own geometry -- too few labelled cells (an FEC
    codeword suffix), a missing state, or a failed lock -- is sampled at
    `field_phase` instead.  Windowed mode is therefore a strict superset of
    field mode: it can improve a region or leave it at the v2 result, never
    replace it with an unseeded guess.  (Measured 2026-07-18: without this,
    coupon fields whose calibration prefix does not reach every window fell
    back to phase (0,0) and regressed from 4.59% to 19.43%.)
    """
    flat = states.ravel()
    n_states = len(definition.states)
    dimension = 3 if use_color else 1
    features = np.zeros((nx * ny, dimension), np.float32)
    records: list[dict[str, Any]] = []
    seed: tuple[float, float] | None = None

    for bounds in _window_bounds(nx, ny, window_cells):
        indices = _window_indices(nx, bounds)
        phase_pool = indices[(indices % 8 == 0) & (indices < n_population)]
        train_pool = indices[np.isin(indices % 8, (1, 2, 3)) & (indices < n_population)]
        record: dict[str, Any] = {
            "bounds_yx": list(bounds), "n_cells": int(indices.size),
            "n_phase": int(phase_pool.size), "n_train": int(train_pool.size),
        }
        # A window needs its own labelled population to solve geometry.
        usable = phase_pool.size >= 200 and train_pool.size >= 200
        if usable:
            sub = phase_pool
            if sub.size > WINDOW_PHASE_SAMPLE:
                pick = np.linspace(0, sub.size - 1, WINDOW_PHASE_SAMPLE)
                sub = sub[pick.round().astype(int)]
            labels = flat[sub]
            if len(np.unique(labels)) < n_states:
                usable = False
        if not usable:
            # Inherit geometry; the window is still sampled so that its cells
            # (e.g. an FEC codeword suffix) are scored, but it cannot certify
            # its own lock.  Prefer a neighbour that DID lock, else the v2
            # whole-field solution -- never an unseeded guess.
            px, py = seed if seed is not None else field_phase
            record.update({"phase_x": px, "phase_y": py, "separation": None,
                           "lock_error": None, "state": "inherited",
                           "phase_source": "neighbour" if seed else "field"})
            features[indices] = _features(_sample_all_window(
                source, coef, field, grid, indices, px, py, aperture), use_color)
            records.append(record)
            continue

        local = {int(v): i for i, v in enumerate(indices)}
        train_local = np.array([local[int(v)] for v in train_pool], np.int64)
        phase_local = np.array([local[int(v)] for v in sub], np.int64)

        def attempt(from_seed: tuple[float, float] | None
                    ) -> tuple[float, float, float, float | None, np.ndarray]:
            px_, py_, sep_ = _phase_search(source, coef, field, grid, sub,
                                           labels, n_states, use_color, from_seed)
            feats = _features(_sample_all_window(
                source, coef, field, grid, indices, px_, py_, aperture), use_color)
            err: float | None = None
            try:
                model = _fit_qda(feats[train_local], flat[train_pool], n_states)
                # Lock quality is measured on the PHASE split, never validation.
                pred = np.argmax(model.scores(feats[phase_local]), axis=1)
                err = float(np.mean(pred != flat[sub]))
            except RuntimeError:
                pass
            return px_, py_, sep_, err, feats

        px, py, sep, lock_error, window_features = attempt(seed)
        retried = False
        # A chained seed is wrong at a transport discontinuity (a y-step, a
        # fold): fall back to the unclamped wide search rather than inheriting
        # a pose that cannot lock.
        if (seed is not None
                and (lock_error is None or lock_error > WINDOW_LOCK_MAX_ERROR)):
            retried = True
            alt = attempt(None)
            if alt[3] is not None and (lock_error is None or alt[3] < lock_error):
                px, py, sep, lock_error, window_features = alt

        if lock_error is not None and lock_error <= WINDOW_LOCK_MAX_ERROR:
            state = "locked"
            seed = (px, py)
            phase_source = "own"
        else:
            # Refuse the window's own solution and fall back rather than
            # emitting a pose that failed its lock test.
            state = "unresolved"
            px, py = seed if seed is not None else field_phase
            phase_source = "neighbour" if seed is not None else "field"
            window_features = _features(_sample_all_window(
                source, coef, field, grid, indices, px, py, aperture), use_color)
        features[indices] = window_features
        record.update({"phase_x": px, "phase_y": py, "separation": sep,
                       "lock_error": lock_error, "state": state,
                       "phase_source": phase_source, "wide_retry": retried})
        records.append(record)
    return features, records


def _sample_all_window(source: RasterSource, coef: np.ndarray,
                       field: dict[str, Any], grid: GridSpec,
                       indices: np.ndarray, phase_x: float, phase_y: float,
                       aperture: float) -> np.ndarray:
    """Aperture-averaged sampling of an explicit index list (chunked)."""
    offsets = (0.0,) if aperture <= 0 else (-aperture, 0.0, aperture)
    out = np.zeros((indices.size, 3), np.float64)
    chunk = 250_000
    for start in range(0, indices.size, chunk):
        piece = indices[start:start + chunk]
        acc = np.zeros((piece.size, 3), np.float64)
        for dy in offsets:
            for dx in offsets:
                acc += _sample_indices(source, coef, field, grid, piece,
                                       phase_x + dx, phase_y + dy)
        out[start:start + piece.size] = acc / (len(offsets) ** 2)
    return out.astype(np.float32)


def _trace_write(trace_dir: Path | None, trace_index: list[dict[str, Any]],
                 ordinal: int, field: dict[str, Any], truth: np.ndarray,
                 predicted: np.ndarray, split: np.ndarray,
                 features: np.ndarray, scores: np.ndarray,
                 bit_llr: list[np.ndarray]) -> None:
    if trace_dir is None:
        return
    trace_dir.mkdir(parents=True, exist_ok=True)
    filename = f"f{ordinal:03d}.npz"
    np.savez_compressed(
        trace_dir / filename,
        true_state=truth.astype(np.uint8),
        predicted_state=predicted.astype(np.uint8),
        split=split.astype(np.uint8),
        features=features.astype(np.float32),
        state_scores=scores.astype(np.float32),
        bit_llr=(np.stack(bit_llr, axis=1).astype(np.float32)
                 if bit_llr else np.empty((len(truth), 0), np.float32)),
    )
    trace_index.append({
        "field_id": field["field_id"], "file": filename,
        "flat_order": "row-major",
        "split_codes": {"phase": 0, "train": 1, "validation": 2, "codeword": 3},
        "nx": int(field["nx"]), "ny": int(field["ny"]),
    })


def score_field(*, source: RasterSource, coef: np.ndarray,
                page: dict[str, Any], field: dict[str, Any],
                scan_dpi_x: float, scan_dpi_y: float,
                physical_sheet_id: str, max_bp_iters: int,
                trace_dir: Path | None, trace_index: list[dict[str, Any]],
                ordinal: int, geometry_mode: str = "field",
                window_cells: int = WINDOW_TARGET_CELLS,
                ) -> tuple[CandidateObservation, dict[str, Any]]:
    candidate = CandidateSpec.from_dict(page["candidates"][field["candidate_key"]])
    definition = ec.CHANNELS[page["candidates"][field["candidate_key"]]["definition_id"]]
    grid = candidate.grid
    states = ec.field_states(field, definition)
    n_population = (
        int(field["calibration_cells"])
        if field["family"] == "fec_coupon"
        else states.size
    )
    a, b, _c, d, e, _f = coef
    measured_x = math.hypot(a, d) * ec.BASE_DPI * grid.c_x / grid.dpi_x
    measured_y = math.hypot(b, e) * ec.BASE_DPI * grid.c_y / grid.dpi_y
    floor = min(measured_x, measured_y)
    aperture = min(0.18, max(0.0, 0.5 - 0.60 / max(floor, 1e-6)))
    use_color = _use_color_features(source, definition)
    flat = states.ravel()
    nx, ny = int(field["nx"]), int(field["ny"])
    windows: list[dict[str, Any]] = []
    unresolved_mask: np.ndarray | None = None

    if geometry_mode == "window":
        # Always solve the v2 whole-field phase first: it is the seed and the
        # guaranteed fallback, which makes this mode a superset of field mode.
        field_px, field_py, field_score = _choose_phase(
            source, coef, field, grid, states, definition, n_population
        )
        features, windows = _solve_windows(
            source, coef, field, grid, states, definition, n_population,
            use_color, aperture, nx, ny, window_cells, (field_px, field_py),
        )
        locked = [w for w in windows if w["state"] == "locked"]
        phase_x = float(np.median([w["phase_x"] for w in locked])) if locked else field_px
        phase_y = float(np.median([w["phase_y"] for w in locked])) if locked else field_py
        phase_score = (float(np.median([w["separation"] for w in locked]))
                       if locked else field_score)
        unresolved_mask = np.zeros(nx * ny, bool)
        for w in windows:
            if w["state"] != "locked":
                unresolved_mask[_window_indices(nx, tuple(w["bounds_yx"]))] = True
    else:
        phase_x, phase_y, phase_score = _choose_phase(
            source, coef, field, grid, states, definition, n_population
        )
        rgb = _sample_all_cells(
            source, coef, field, grid, phase_x, phase_y, aperture
        )
        features = _features(rgb, use_color)

    phase, train, validation = _split_indices(n_population)
    if unresolved_mask is not None:
        # Fit on geometry-locked cells where possible; unresolved regions are
        # still SCORED (they carry the field-phase fallback, i.e. the v2
        # result), so the headline number stays comparable to field mode and
        # can never be inflated by scoring only the regions that locked.
        keep_train = train[~unresolved_mask[train]]
        if keep_train.size > max(train.size // 8, 200):
            train = keep_train
        locked_validation = validation[~unresolved_mask[validation]]
    else:
        locked_validation = validation
    model = _fit_qda(features[train], flat[train], len(definition.states))
    scores = model.scores(features)
    predicted = np.argmax(scores, axis=1).astype(np.uint8)
    scored = validation
    conf = _confusion(flat[scored], predicted[scored], len(definition.states))
    state_accuracy = float(np.mean(predicted[scored] == flat[scored]))
    mi = _mutual_information(conf)
    locked_stats: dict[str, Any] | None = None
    if unresolved_mask is not None and locked_validation.size >= 100:
        locked_conf = _confusion(flat[locked_validation],
                                 predicted[locked_validation],
                                 len(definition.states))
        locked_stats = {
            "n_validation_cells": int(locked_validation.size),
            "state_accuracy": float(np.mean(
                predicted[locked_validation] == flat[locked_validation])),
            "mutual_information_bpc": _mutual_information(locked_conf),
        }

    bit_llr: list[np.ndarray] = []
    bit_ber: dict[str, float] = {}
    numbers = np.arange(len(definition.states))
    for level, level_name in enumerate(definition.bit_levels):
        zero = (numbers & (1 << level)) == 0
        llr = logsumexp(scores[:, ~zero], axis=1) - logsumexp(scores[:, zero], axis=1)
        bit_llr.append(llr.astype(np.float32))
        truth = (flat >> level) & 1
        bit_ber[level_name] = float(np.mean((llr[scored] > 0) != truth[scored]))
    hard_error = float(np.mean(list(bit_ber.values()))) if bit_ber else 1.0 - state_accuracy

    yields: list[LdpcYield] = []
    per_level: dict[str, Any] = {}
    if field["family"] == "fec_coupon":
        n_words, start = int(field["n_codewords"]), int(field["codeword_start"])
        spec = ldpc.LDPC_LADDER[field["rate_id"]]
        for level, level_name in enumerate(definition.bit_levels):
            attempted = certified = wrong = iterations = 0
            true_bits = ((flat[start:] >> level) & 1).reshape(n_words, ldpc.N_BITS)
            llr_words = bit_llr[level][start:].reshape(n_words, ldpc.N_BITS)
            for word_llr, true_word in zip(llr_words, true_bits, strict=True):
                decoded, syndrome_ok, n_iter = ldpc.decode(
                    word_llr, spec, max_iters=max_bp_iters
                )
                exact = bool(np.array_equal(decoded, true_word))
                attempted += 1
                iterations += n_iter
                if syndrome_ok and exact:
                    certified += 1
                elif syndrome_ok:
                    wrong += 1
            yields.append(LdpcYield(
                rate_id=field["rate_id"], code_rate=spec.rate,
                attempted=attempted, certified=certified, wrong=wrong,
                mean_iterations=iterations / attempted if attempted else 0.0,
                level_id=level_name,
            ))
            per_level[level_name] = {
                "attempted": attempted, "certified_exact": certified,
                "syndrome_valid_wrong": wrong, "iterations": iterations,
            }

    split = np.full(states.size, 2, np.uint8)
    split[phase] = 0
    split[train] = 1
    if field["family"] == "fec_coupon":
        split[n_population:] = 3
    _trace_write(
        trace_dir, trace_index, ordinal, field, flat, predicted, split,
        features, scores, bit_llr,
    )
    nominal_x, nominal_y = grid.nominal_scan_samples(scan_dpi_x, scan_dpi_y)
    sampling_tier = (
        "reference" if floor >= 6.0 else "qualified-4px" if floor >= 4.0
        else "nyquist-edge" if floor >= 2.0 else "undersampled"
    )
    diagnostics = {
        "field_id": field["field_id"], "family": field["family"],
        "role": field["role"], "phase_x_cells": phase_x,
        "phase_y_cells": phase_y, "phase_separation_score": phase_score,
        "aperture_radius_cells": aperture,
        "feature_space": "rgb-density" if use_color else "grey-density",
        "state_accuracy": state_accuracy, "state_confusion": conf.tolist(),
        "bit_ber": bit_ber, "sampling_tier": sampling_tier,
        "per_level_ldpc": per_level,
    }
    if "edge" in field:
        diagnostics.update({"edge": field["edge"],
                            "edge_gap_mm": field["edge_gap_mm"]})
    geometry_summary: dict[str, Any] | None = None
    if geometry_mode == "window":
        n_locked = sum(1 for w in windows if w["state"] == "locked")
        ys = [w["phase_y"] for w in windows if w["state"] == "locked"]
        xs = [w["phase_x"] for w in windows if w["state"] == "locked"]
        geometry_summary = {
            "mode": "window", "window_cells": window_cells,
            "n_windows": len(windows), "n_locked": n_locked,
            "n_unresolved": sum(1 for w in windows if w["state"] == "unresolved"),
            "n_inherited": sum(1 for w in windows if w["state"] == "inherited"),
            "phase_y_span_cells": (max(ys) - min(ys)) if ys else None,
            "phase_x_span_cells": (max(xs) - min(xs)) if xs else None,
            "phase_y_range": [min(ys), max(ys)] if ys else None,
            "field_phase_fallback": [field_px, field_py],
            "validation_cells_total": int(validation.size),
            "validation_cells_in_locked_windows": int(locked_validation.size),
            "locked_windows_only": locked_stats,
            "scoring_rule": ("headline statistics cover ALL validation cells; "
                             "unresolved windows carry the field-phase "
                             "fallback, never a failed pose"),
            "windows": windows,
        }
        diagnostics["geometry"] = {
            key: value for key, value in geometry_summary.items()
            if key != "windows"
        }
    else:
        diagnostics["geometry"] = {"mode": "field"}
    # A field whose windows never locked has NOT certified its geometry; saying
    # so is the point of the refusal contract (a coin-flip BER reported as
    # "scan adequate" is exactly the v2 failure this replaces).  The number is
    # still reported -- it is the field-phase fallback -- but it is flagged.
    if geometry_mode == "window":
        adequate = bool(geometry_summary["n_locked"] > 0 and scored.size >= 100)
    else:
        adequate = bool(np.isfinite(phase_score))
    observation = CandidateObservation(
        candidate=candidate,
        stratum_id=f"{physical_sheet_id}/{field['stratum']}",
        hard_error_rate=hard_error,
        mutual_information_bpc=mi,
        n_validation_cells=int(scored.size),
        scan_adequate=adequate,
        nominal_scan_samples_x=nominal_x,
        nominal_scan_samples_y=nominal_y,
        measured_scan_samples_x=measured_x,
        measured_scan_samples_y=measured_y,
        ldpc=tuple(yields), diagnostics=diagnostics,
    )
    summary = {
        "field_id": field["field_id"], "family": field["family"],
        "role": field["role"],
        "candidate_id": candidate.candidate_id, "stratum": field["stratum"],
        "grid": candidate.grid.to_dict(),
        "symbol_shape": candidate.symbol_shape,
        "hard_error_rate": hard_error, "mutual_information_bpc": mi,
        "state_accuracy": state_accuracy, "bit_ber": bit_ber,
        "phase_separation_score": phase_score,
        "measured_samples_per_cell": [measured_x, measured_y],
        "ldpc": [item.to_dict() for item in yields],
        "geometry_mode": geometry_mode,
    }
    if geometry_summary is not None:
        summary["geometry"] = geometry_summary
    if "edge" in field:
        summary.update({"edge": field["edge"], "edge_gap_mm": field["edge_gap_mm"]})
    return observation, summary


def _sample_rect(source: RasterSource, coef: np.ndarray, probe: dict[str, Any],
                 nx: int, ny: int) -> np.ndarray:
    gx, gy = _rect_layout_points(probe, nx, ny)
    return _sample_scan_points(source, coef, gx, gy)


def _rect_layout_points(probe: dict[str, Any], nx: int,
                        ny: int) -> tuple[np.ndarray, np.ndarray]:
    x0, y0 = float(probe["x_layout_dots"]), float(probe["y_layout_dots"])
    width, height = float(probe["w_layout_dots"]), float(probe["h_layout_dots"])
    xx = x0 + (np.arange(nx) + 0.5) / nx * width
    yy = y0 + (np.arange(ny) + 0.5) / ny * height
    return np.meshgrid(xx, yy)


def _rect_scan_visibility(source: RasterSource, coef: np.ndarray,
                          probe: dict[str, Any], nx: int,
                          ny: int) -> tuple[bool, float]:
    """Return full-footprint visibility and sampled-center visibility.

    Edge ticks deliberately approach the physical paper boundary.  A scanner
    crop may therefore omit part or all of a valid printed tick.  Treating
    interpolator edge clamping as observed paper would confound scanner extent
    with printer extent; treating a wholly outside tick as fatal would discard
    the rest of an otherwise useful capture.
    """
    gx, gy = _rect_layout_points(probe, nx, ny)
    px, py = _affine_apply(coef, gx, gy)
    center_visible = ((px >= 0.0) & (px <= source.width - 1.0)
                      & (py >= 0.0) & (py <= source.height - 1.0))

    x0, y0 = float(probe["x_layout_dots"]), float(probe["y_layout_dots"])
    x1 = x0 + float(probe["w_layout_dots"])
    y1 = y0 + float(probe["h_layout_dots"])
    cx, cy = _affine_apply(
        coef, np.array([x0, x1, x1, x0]), np.array([y0, y0, y1, y1])
    )
    fully_visible = bool(np.all(
        (cx >= 0.0) & (cx <= source.width - 1.0)
        & (cy >= 0.0) & (cy <= source.height - 1.0)
    ))
    return fully_visible, float(np.mean(center_visible))


def _plane_density(rgb: np.ndarray, plane: str) -> np.ndarray:
    reflectance = np.clip(rgb, 1.0 / 65535.0, 1.0)
    density = -np.log10(reflectance)
    if plane == "C":
        return density[..., 0]
    if plane == "M":
        return density[..., 1]
    if plane == "Y":
        return density[..., 2]
    grey = (0.2126 * reflectance[..., 0] + 0.7152 * reflectance[..., 1]
            + 0.0722 * reflectance[..., 2])
    return -np.log10(np.clip(grey, 1.0 / 65535.0, 1.0))


def _align_pattern_translation(truth: np.ndarray, values: np.ndarray,
                               max_shift: int, *, search_x: bool = True,
                               search_y: bool = True,
                               ) -> tuple[np.ndarray, np.ndarray, int, int, float]:
    """Align a small physical probe without hiding blur or deformation.

    Corner registration leaves print/scan warp of several 600-dpi source dots
    across a page. For a periodic target, a half-period translation reverses
    direct correlation even when modulation is strong. Search only a bounded
    integer translation, score the non-wrapped overlap, and retain the winning
    displacement. Blur, dropout, scale error, and non-rigid distortion remain
    in the metric.
    """
    if truth.shape != values.shape or truth.ndim != 2:
        raise ValueError("pattern truth and samples must be matching 2-D arrays")
    height, width = truth.shape
    dx_values = range(-max_shift, max_shift + 1) if search_x else (0,)
    dy_values = range(-max_shift, max_shift + 1) if search_y else (0,)
    shifts = sorted(
        ((dx, dy) for dy in dy_values for dx in dx_values),
        key=lambda item: (item[0] * item[0] + item[1] * item[1],
                          abs(item[1]), abs(item[0]), item[1], item[0]),
    )
    best: tuple[float, int, int, np.ndarray, np.ndarray] | None = None
    for dx, dy in shifts:
        tx0, tx1 = max(0, -dx), min(width, width - dx)
        ty0, ty1 = max(0, -dy), min(height, height - dy)
        vx0, vx1 = tx0 + dx, tx1 + dx
        vy0, vy1 = ty0 + dy, ty1 + dy
        aligned_truth = truth[ty0:ty1, tx0:tx1].ravel()
        aligned_values = values[vy0:vy1, vx0:vx1].ravel()
        if (len(aligned_truth) < 16 or np.all(aligned_truth)
                or not np.any(aligned_truth)):
            continue
        corr = float(np.corrcoef(
            aligned_truth.astype(np.float64), aligned_values
        )[0, 1])
        if not np.isfinite(corr):
            continue
        if best is None or corr > best[0] + 1e-12:
            best = (corr, dx, dy, aligned_truth, aligned_values)
    if best is None:
        return truth.ravel(), values.ravel(), 0, 0, float("nan")
    corr, dx, dy, aligned_truth, aligned_values = best
    return aligned_truth, aligned_values, dx, dy, corr


def _score_pattern_probe(source: RasterSource, coef: np.ndarray,
                         probe: dict[str, Any]) -> dict[str, Any]:
    bits = ec.pattern_bits(probe)
    h, w = bits.shape
    x0, y0 = float(probe["x_layout_dots"]), float(probe["y_layout_dots"])
    step = ec.BASE_DPI / int(probe["source_dpi"])
    yy, xx = np.indices((h, w))
    rgb = _sample_scan_points(
        source, coef, x0 + (xx + 0.5) * step, y0 + (yy + 0.5) * step
    )
    orientation = probe["params"].get("orientation")
    truth, values, shift_x, shift_y, corr = _align_pattern_translation(
        bits.astype(bool), _plane_density(rgb, probe["plane"]), max_shift=8,
        search_x=orientation != "horizontal_lines",
        search_y=orientation != "vertical_lines",
    )
    ink = values[truth]
    white = values[~truth]
    if not len(ink) or not len(white):
        return {"probe_id": probe["probe_id"], "kind": probe["kind"],
                "plane": probe["plane"], "scorable": False}
    threshold = (float(np.median(ink)) + float(np.median(white))) / 2.0
    predicted = values > threshold
    separation = float(np.median(ink) - np.median(white))
    return {
        "probe_id": probe["probe_id"], "kind": probe["kind"],
        "plane": probe["plane"], "scorable": True,
        "ink_density_median": float(np.median(ink)),
        "white_density_median": float(np.median(white)),
        "density_separation": separation,
        "dot_error_rate": float(np.mean(predicted != truth)),
        "correlation": corr,
        "phase_alignment_source_dots": [shift_x, shift_y],
        "n_aligned_source_dots": int(len(truth)),
        "resolved": bool(separation > 0.03 and corr > 0.20),
        "params": probe["params"],
    }


def _score_phase_rail(source: RasterSource, coef: np.ndarray,
                      probe: dict[str, Any]) -> dict[str, Any]:
    result = _score_pattern_probe(source, coef, probe)
    bits = ec.pattern_bits(probe)
    axis = probe["params"]["axis"]
    expected = bits[bits.shape[0] // 2] if axis == "x" else bits[:, bits.shape[1] // 2]
    n = len(expected)
    x0, y0 = float(probe["x_layout_dots"]), float(probe["y_layout_dots"])
    step = ec.BASE_DPI / int(probe["source_dpi"])
    if axis == "x":
        x = x0 + (np.arange(n) + 0.5) * step
        y = np.full(n, y0 + float(probe["h_layout_dots"]) / 2.0)
    else:
        x = np.full(n, x0 + float(probe["w_layout_dots"]) / 2.0)
        y = y0 + (np.arange(n) + 0.5) * step
    signal = _plane_density(_sample_scan_points(source, coef, x, y), "K")
    period = int(probe["params"]["on_dots"] + probe["params"]["off_dots"])
    windows = []
    for start in range(0, n - period * 8 + 1, max(period * 8, 128)):
        stop = min(n, start + max(period * 16, 256))
        truth = expected[start:stop].astype(np.float64)
        measured = signal[start:stop].astype(np.float64)
        scores = []
        for shift in range(-period, period + 1):
            scores.append(float(np.corrcoef(np.roll(truth, shift), measured)[0, 1]))
        best = int(np.nanargmax(scores)) - period
        windows.append({
            "position_source_dots": (start + stop) / 2.0,
            "phase_residual_source_dots": float(best),
            "correlation": float(np.nanmax(scores)),
        })
    result["transport_phase_windows"] = windows
    return result


def _score_tone_probe(source: RasterSource, coef: np.ndarray,
                      probe: dict[str, Any]) -> dict[str, Any]:
    params = probe["params"]
    mode, axis = params["mode"], params["axis"]
    if mode == "fixed-profile":
        nx, ny = (192, 16) if axis == "x" else (12, 192)
    else:
        nx, ny = (24, 12) if axis == "x" else (12, 24)
    rgb = _sample_rect(source, coef, probe, nx, ny)
    density = _plane_density(rgb, probe["plane"])
    authored = ec.pattern_bits(probe)
    row = {
        "probe_id": probe["probe_id"], "plane": probe["plane"],
        "mode": mode, "axis": axis,
        "coverage": float(params["coverage"]),
        "actual_authored_coverage": float(np.mean(authored)),
        "station": params["station"],
        "center_mm": [
            ec.dots_to_mm(float(probe["x_layout_dots"])
                          + float(probe["w_layout_dots"]) / 2.0),
            ec.dots_to_mm(float(probe["y_layout_dots"])
                          + float(probe["h_layout_dots"]) / 2.0),
        ],
        "mean_density": float(np.mean(density)),
        "std_density": float(np.std(density)),
        "mean_rgb": np.mean(rgb, axis=(0, 1)).tolist(),
    }
    if mode == "fixed-profile":
        profile = np.mean(density, axis=0 if axis == "x" else 1)
        authored_profile = np.mean(authored, axis=0 if axis == "x" else 1)
        edges = np.linspace(0, len(authored_profile), len(profile) + 1).astype(int)
        authored_binned = np.array([
            float(np.mean(authored_profile[edges[index]:edges[index + 1]]))
            if edges[index + 1] > edges[index] else float(authored_profile[edges[index]])
            for index in range(len(profile))
        ])
        kernel = np.ones(7, np.float64) / 7.0
        smooth = np.convolve(profile, kernel, mode="valid")
        authored_smooth = np.convolve(authored_binned, kernel, mode="valid")
        p05, p95 = np.percentile(smooth, (5, 95))
        authored_p05, authored_p95 = np.percentile(authored_smooth, (5, 95))
        row.update({
            "profile_density": smooth.tolist(),
            "authored_coverage_profile": authored_smooth.tolist(),
            "profile_bins": len(smooth),
            "profile_rms_density": float(np.std(smooth)),
            "profile_p95_p05_density": float(p95 - p05),
            "authored_profile_p95_p05_coverage": float(
                authored_p95 - authored_p05
            ),
            "relative_p95_p05": float(
                (p95 - p05) / max(float(np.mean(smooth)), 1e-6)
            ),
        })
    return row


def _tone_models(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit coverage effects plus independent page-x/page-y density slopes."""
    out: dict[str, Any] = {}
    for plane in "KCMY":
        selected = [row for row in rows if row["plane"] == plane]
        if not selected:
            continue
        levels = sorted({float(row["coverage"]) for row in selected})
        design = np.zeros((len(selected), len(levels) + 2), np.float64)
        response = np.array([row["mean_density"] for row in selected])
        for index, row in enumerate(selected):
            design[index, levels.index(float(row["coverage"]))] = 1.0
            design[index, -2] = row["center_mm"][0] / ec.PAGE_MM[0] - 0.5
            design[index, -1] = row["center_mm"][1] / ec.PAGE_MM[1] - 0.5
        coef, _residuals, rank, _singular = np.linalg.lstsq(
            design, response, rcond=None
        )
        fitted = design @ coef
        curve = coef[:len(levels)]
        out[plane] = {
            "n_samples": len(selected), "rank": int(rank),
            "coverages": levels,
            "tone_curve_density_at_page_center": curve.tolist(),
            "horizontal_density_delta_per_page": float(coef[-2]),
            "vertical_density_delta_per_page": float(coef[-1]),
            "residual_rms_density": float(np.sqrt(np.mean((response - fitted) ** 2))),
            "monotonic_violations": int(np.sum(np.diff(curve) < -0.01)),
            "model": "coverage categorical + centered linear x + centered linear y",
        }
    return out


def _score_background_probe(source: RasterSource, coef: np.ndarray,
                            probe: dict[str, Any]) -> dict[str, Any]:
    rgb = _sample_rect(source, coef, probe, 12, 12)
    return {
        "probe_id": probe["probe_id"],
        "station": probe["params"]["station"],
        "center_mm": [
            ec.dots_to_mm(float(probe["x_layout_dots"])
                          + float(probe["w_layout_dots"]) / 2.0),
            ec.dots_to_mm(float(probe["y_layout_dots"])
                          + float(probe["h_layout_dots"]) / 2.0),
        ],
        "mean_rgb": np.mean(rgb, axis=(0, 1)).tolist(),
        "std_rgb": np.std(rgb, axis=(0, 1)).tolist(),
        "mean_density": {
            plane: float(np.mean(_plane_density(rgb, plane)))
            for plane in "KCMY"
        },
    }


def _background_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"witnesses": [], "spatial_fit": {}}
    design = np.array([
        [1.0, row["center_mm"][0] / ec.PAGE_MM[0] - 0.5,
         row["center_mm"][1] / ec.PAGE_MM[1] - 0.5]
        for row in rows
    ], np.float64)
    values = np.array([row["mean_rgb"] for row in rows], np.float64)
    fit: dict[str, Any] = {}
    for channel, index in zip("RGB", range(3), strict=True):
        coef, _residuals, rank, _singular = np.linalg.lstsq(
            design, values[:, index], rcond=None
        )
        predicted = design @ coef
        fit[channel] = {
            "rank": int(rank), "center_reflectance": float(coef[0]),
            "horizontal_reflectance_delta_per_page": float(coef[1]),
            "vertical_reflectance_delta_per_page": float(coef[2]),
            "residual_rms": float(np.sqrt(np.mean(
                (values[:, index] - predicted) ** 2
            ))),
        }
    return {"witnesses": rows, "spatial_fit": fit}


def _score_registration_cross(source: RasterSource, coef: np.ndarray,
                              probe: dict[str, Any]) -> dict[str, Any]:
    bits = ec.pattern_bits(probe)
    h, w = bits.shape
    x0, y0 = float(probe["x_layout_dots"]), float(probe["y_layout_dots"])
    step = ec.BASE_DPI / int(probe["source_dpi"])
    yy, xx = np.indices((h, w))
    rgb = _sample_scan_points(
        source, coef, x0 + (xx + 0.5) * step, y0 + (yy + 0.5) * step
    )
    density = _plane_density(rgb, probe["plane"])
    baseline = float(np.percentile(density, 50))
    peak = float(np.percentile(density, 99))
    weights = np.clip(density - baseline - 0.15 * (peak - baseline), 0.0, None)
    total = float(weights.sum())
    ok = total > 1e-9 and peak - baseline > 0.02
    if ok:
        measured_x = float(np.sum(weights * xx) / total)
        measured_y = float(np.sum(weights * yy) / total)
        residual_source: list[float | None] = [
            measured_x - (w - 1) / 2.0,
            measured_y - (h - 1) / 2.0,
        ]
        scale_mm = 25.4 / float(probe["source_dpi"])
        residual_mm: list[float | None] = [
            float(value) * scale_mm for value in residual_source
            if value is not None
        ]
    else:
        residual_source = [None, None]
        residual_mm = [None, None]
    return {
        "probe_id": probe["probe_id"], "target": probe["params"]["target"],
        "plane": probe["plane"], "ok": ok,
        "residual_source_dots": residual_source,
        "residual_mm": residual_mm,
        "density_contrast": peak - baseline,
    }


def _registration_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targets = []
    vectors = []
    for target in sorted({row["target"] for row in rows}):
        by_plane = {row["plane"]: row for row in rows if row["target"] == target}
        if "K" not in by_plane or not by_plane["K"]["ok"]:
            targets.append({"target": target, "ok": False, "planes": by_plane})
            continue
        relative = {}
        for plane in "CMY":
            if plane not in by_plane or not by_plane[plane]["ok"]:
                relative[plane] = None
                continue
            vector = [
                by_plane[plane]["residual_mm"][axis]
                - by_plane["K"]["residual_mm"][axis]
                for axis in range(2)
            ]
            relative[plane] = vector
            vectors.append(vector)
        targets.append({"target": target,
                        "ok": all(relative[plane] is not None for plane in "CMY"),
                        "relative_to_k_mm": relative, "planes": by_plane})
    magnitudes = [math.hypot(*vector) for vector in vectors]
    return {
        "reference_plane": "K", "targets": targets,
        "rms_relative_registration_mm": (
            float(np.sqrt(np.mean(np.square(magnitudes)))) if magnitudes else None
        ),
        "maximum_relative_registration_mm": max(magnitudes, default=None),
        "interpretation": (
            "per-plane cross-centroid residual after the common corner affine; "
            "CMY values subtract the local K residual"
        ),
    }


def score_probes(source: RasterSource, coef: np.ndarray,
                 page: dict[str, Any], thumb: np.ndarray) -> dict[str, Any]:
    white, black = float(np.percentile(thumb, 90)), float(np.percentile(thumb, 1))
    span = max(white - black, 1e-6)
    response, fixed, background, registration = [], [], [], []
    patterns, ticks, rails = [], [], []
    for probe in page["probes"]:
        if probe["kind"] == "edge_tick":
            fully_visible, visible_fraction = _rect_scan_visibility(
                source, coef, probe, 7, 7
            )
            row = {
                "probe_id": probe["probe_id"],
                "edge": probe["params"]["edge"],
                "gap_mm": float(probe["params"]["gap_mm"]),
                "scan_visible_fraction": visible_fraction,
            }
            if not fully_visible:
                ticks.append({**row, "coverage": None,
                              "status": "unobservable"})
                continue
            rgb = _sample_rect(source, coef, probe, 7, 7)
            grey = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1]
                    + 0.0722 * rgb[..., 2])
            coverage = float(np.clip((white - float(np.mean(grey))) / span, 0.0, 1.2))
            status = "present" if coverage >= 0.50 else "partial" if coverage >= 0.10 else "absent"
            ticks.append({**row, "coverage": coverage, "status": status})
        elif probe["group"] == "tone-metrology":
            row = _score_tone_probe(source, coef, probe)
            (fixed if row["mode"] == "fixed-profile" else response).append(row)
        elif probe["group"] == "background":
            background.append(_score_background_probe(source, coef, probe))
        elif probe["group"] == "plane-registration":
            registration.append(_score_registration_cross(source, coef, probe))
        elif probe["kind"] == "phase_rail":
            rails.append(_score_phase_rail(source, coef, probe))
        elif probe["kind"] != "paper":
            patterns.append(_score_pattern_probe(source, coef, probe))
    edge_records = {}
    for edge in ("top", "bottom", "left", "right"):
        rows = sorted((row for row in ticks if row["edge"] == edge),
                      key=lambda row: row["gap_mm"])
        present = [row["gap_mm"] for row in rows if row["status"] == "present"]
        conservative = None
        for row in rows:
            if all(item["status"] == "present" for item in rows
                   if item["gap_mm"] >= row["gap_mm"]):
                conservative = row["gap_mm"]
                break
        edge_records[edge] = {
            "ticks": rows,
            "minimum_present_gap_mm": min(present) if present else None,
            "conservative_contiguous_present_gap_mm": conservative,
            "maximum_absent_gap_mm": max(
                (row["gap_mm"] for row in rows if row["status"] == "absent"),
                default=None,
            ),
        }
    return {
        "printable_ticks": {"edges": edge_records,
                            "interpretation": "solid-ink physical reach, not payload safety"},
        "tone_metrology": {
            "fixed_profiles": fixed, "response_samples": response,
            "deconfounded_models": _tone_models(response),
        },
        "background": _background_summary(background),
        "plane_registration": _registration_summary(registration),
        "morphology_frequency": patterns,
        "geometry_rails": rails,
    }


def score_plus_marks(source: RasterSource, coef: np.ndarray,
                     page: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in page["infrastructure"]:
        if item["kind"] != "geometry_plus":
            continue
        cx, cy = float(item["cx_layout_dots"]), float(item["cy_layout_dots"])
        offsets = np.arange(-20, 21, dtype=np.float64)
        xx, yy = np.meshgrid(cx + offsets, cy + offsets)
        density = _plane_density(_sample_scan_points(source, coef, xx, yy), "K")
        threshold = float(np.percentile(density, 75))
        weights = np.clip(density - threshold, 0.0, None)
        total = float(weights.sum())
        if total <= 1e-9:
            rows.append({"index": item["index"], "ok": False})
            continue
        measured_x = float(np.sum(weights * xx) / total)
        measured_y = float(np.sum(weights * yy) / total)
        rows.append({
            "index": item["index"], "ok": True,
            "x_mm": ec.dots_to_mm(cx), "y_mm": ec.dots_to_mm(cy),
            "dx_layout_dots": measured_x - cx,
            "dy_layout_dots": measured_y - cy,
        })
    ok = [row for row in rows if row.get("ok")]
    residual = [math.hypot(row["dx_layout_dots"], row["dy_layout_dots"])
                for row in ok]
    return {
        "marks": rows, "n_ok": len(ok),
        "residual_rms_layout_dots": (
            float(math.sqrt(np.mean(np.square(residual)))) if residual else None
        ),
        "residual_max_layout_dots": max(residual) if residual else None,
    }


def decode_machine_strips(source: RasterSource, coef: np.ndarray,
                          page: dict[str, Any], scan_dpi_x: float,
                          scan_dpi_y: float) -> list[dict[str, Any]]:
    """Decode each declared strip in a registration-guided local crop.

    Full-page global thresholding is unnecessarily fragile on a color page
    dominated by large chromatic fields.  LAY=1 remains self-scaling inside
    each crop; registration merely selects the neighborhood.
    """
    decoded: list[tuple[int, dict[str, Any]]] = []
    for entry in page["infrastructure"]:
        if entry["kind"] != "machine_strip":
            continue
        x0 = ec.mm_to_dots(float(entry["x_mm"]) - 1.5)
        y0 = ec.mm_to_dots(float(entry["y_mm"]) - 1.5)
        x1 = ec.mm_to_dots(float(entry["x_mm"]) + 187.0)
        y1 = ec.mm_to_dots(float(entry["y_mm"]) + 4.5)
        px, py = _affine_apply(
            coef,
            np.array([x0, x1, x1, x0], np.float64),
            np.array([y0, y0, y1, y1], np.float64),
        )
        pad_x = max(4, round(scan_dpi_x / 25.4 * 1.0))
        pad_y = max(4, round(scan_dpi_y / 25.4 * 1.0))
        sx0 = max(0, int(math.floor(float(px.min()))) - pad_x)
        sx1 = min(source.width, int(math.ceil(float(px.max()))) + pad_x)
        sy0 = max(0, int(math.floor(float(py.min()))) - pad_y)
        sy1 = min(source.height, int(math.ceil(float(py.max()))) + pad_y)
        if sx1 > sx0 and sy1 > sy0:
            local = source.crop_thumbnail_grey(
                sy0, sy1, sx0, sx1, scan_dpi_x, scan_dpi_y,
                target_dpi=600.0,
            )
            candidates = stripdec.decode_image(
                np.clip(local * 255.0, 0, 255).astype(np.uint8)
            )
            if candidates:
                best = max(candidates, key=lambda item: (
                    bool(item["crc_ok"]), bool(item["magic_ok"]),
                    float(item["clock_score"]),
                ))
                decoded.append((int(entry["index"]), best))
    out = []
    for placement_index, strip in decoded:
        payload = strip["payload"]
        nul = payload.find(b"\x00")
        text = payload[:nul if nul >= 0 else 388].decode("ascii", errors="replace")
        fields = {}
        for token in text.split(";"):
            if "=" in token:
                key, value = token.split("=", 1)
                fields[key] = value
        out.append({
            "placement_index": placement_index,
            "crc_ok": bool(strip["crc_ok"]), "magic_ok": bool(strip["magic_ok"]),
            "clock_score": float(strip["clock_score"]),
            "module_px": [float(value) for value in strip["module_px"]],
            "skew_deg": float(strip["skew_deg"]),
            "rotated_180": bool(strip["rotated_180"]),
            "fields": fields, "payload_text": text,
        })
    return out


def _payload_safe_extent(field_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    all_interior = [row for row in field_summaries if row["family"] == "prnd"]
    primary_interior = [row for row in all_interior if row["role"] == "channel"]
    edge_rows = [row for row in field_summaries if row["family"] == "edge_canary"]
    fallback_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for row in all_interior:
        fallback_by_candidate.setdefault(row["candidate_id"], []).append(row)
    by_candidate: dict[str, list[dict[str, Any]]] = {}
    for row in primary_interior:
        by_candidate.setdefault(row["candidate_id"], []).append(row)
    edges = {}
    for edge in ("top", "bottom", "left", "right"):
        rows = sorted((row for row in edge_rows if row["edge"] == edge),
                      key=lambda row: row["edge_gap_mm"])
        evaluated = []
        for row in rows:
            references = by_candidate.get(row["candidate_id"], [])
            reference_scope = "role=channel"
            if not references:
                references = fallback_by_candidate.get(row["candidate_id"], [])
                reference_scope = "fallback:any-prnd"
            reference_ber = max((item["hard_error_rate"] for item in references), default=0.0)
            reference_mi = min((item["mutual_information_bpc"] for item in references),
                               default=row["mutual_information_bpc"])
            ber_limit = max(0.02, reference_ber + 0.01)
            mi_floor = max(0.0, reference_mi - 0.10)
            passed = bool(
                np.isfinite(row["phase_separation_score"])
                and row["hard_error_rate"] <= ber_limit
                and row["mutual_information_bpc"] >= mi_floor
            )
            evaluated.append({
                **row, "passed": passed, "ber_limit": ber_limit,
                "mi_floor_bpc": mi_floor,
                "reference_scope": reference_scope,
                "reference_field_ids": [item["field_id"] for item in references],
            })
        conservative = None
        for row in evaluated:
            if all(item["passed"] for item in evaluated
                   if item["edge_gap_mm"] >= row["edge_gap_mm"]):
                conservative = row["edge_gap_mm"]
                break
        edges[edge] = {
            "canaries": evaluated,
            "conservative_payload_margin_mm": conservative,
        }
    margins = {edge: edges[edge]["conservative_payload_margin_mm"] for edge in edges}
    complete = all(value is not None for value in margins.values())
    rectangle = None
    if complete:
        rectangle = {
            "x0_mm": margins["left"], "y0_mm": margins["top"],
            "x1_mm": ec.PAGE_MM[0] - margins["right"],
            "y1_mm": ec.PAGE_MM[1] - margins["bottom"],
            "width_mm": ec.PAGE_MM[0] - margins["left"] - margins["right"],
            "height_mm": ec.PAGE_MM[1] - margins["top"] - margins["bottom"],
        }
        rectangle["area_mm2"] = rectangle["width_mm"] * rectangle["height_mm"]
    return {
        "edges": edges, "margins_mm": margins,
        "usable_rectangle_mm": rectangle,
        "rule": "smallest edge gap whose canary and every more-inboard canary pass",
        "thresholds": "relative to same-candidate interior BER/MI; absolute BER floor 0.02",
    }


def _capacity(page: dict[str, Any], field_summaries: list[dict[str, Any]],
              safe_extent: dict[str, Any]) -> list[dict[str, Any]]:
    rect = safe_extent["usable_rectangle_mm"]
    if rect is None:
        return []
    evidence: dict[str, list[dict[str, Any]]] = {}
    coupons: dict[str, list[dict[str, Any]]] = {}
    for row in field_summaries:
        target = coupons if row["family"] == "fec_coupon" else evidence
        if row["family"] != "edge_canary":
            target.setdefault(row["candidate_id"], []).append(row)
    rows = []
    for candidate_id, candidate_raw in sorted(page["candidates"].items()):
        candidate = CandidateSpec.from_dict(candidate_raw)
        nx = int(rect["width_mm"] / candidate.grid.cell_pitch_mm_x)
        ny = int(rect["height_mm"] / candidate.grid.cell_pitch_mm_y)
        cells = nx * ny
        measurements = evidence.get(candidate_id, [])
        worst_mi = min((item["mutual_information_bpc"] for item in measurements),
                       default=None)
        worst_ber = max((item["hard_error_rate"] for item in measurements),
                        default=None)
        fec = []
        for coupon in coupons.get(candidate_id, []):
            levels = coupon["ldpc"]
            exact = bool(levels and all(
                item["certified"] == item["attempted"] and item["wrong"] == 0
                for item in levels
            ))
            rate = float(levels[0]["code_rate"]) if levels else 0.0
            fec.append({
                "rate_id": levels[0]["rate_id"] if levels else None,
                "all_levels_exact": exact,
                "coupon_attempts_per_level": levels[0]["attempted"] if levels else 0,
                "coded_payload_bits_in_measured_rectangle": (
                    cells * len(candidate.bit_levels) * rate if exact else None
                ),
                "caution": "small confirmation coupon; not a production confidence bound",
            })
        rows.append({
            "candidate_id": candidate_id, "grid": candidate.grid.to_dict(),
            "usable_cells": cells, "usable_shape_cells": [nx, ny],
            "raw_bits": cells * candidate.payload_bits_per_cell,
            "raw_megabytes": cells * candidate.payload_bits_per_cell / 8e6,
            "worst_measured_hard_error_rate": worst_ber,
            "minimum_measured_mi_bpc": worst_mi,
            "empirical_information_bits": None if worst_mi is None else cells * worst_mi,
            "empirical_information_megabytes": (
                None if worst_mi is None else cells * worst_mi / 8e6
            ),
            "fec_confirmations": fec,
        })
    return rows


def _diag_overlay(thumb: np.ndarray, coef: np.ndarray, fx: float, fy: float,
                  page: dict[str, Any], field_summaries: list[dict[str, Any]],
                  safe_extent: dict[str, Any], out: Path) -> None:
    lo, hi = np.percentile(thumb, (1, 99))
    image = Image.fromarray(
        np.clip((thumb - lo) / max(hi - lo, 1e-9) * 255, 0, 255).astype(np.uint8)
    ).convert("RGB")
    draw = ImageDraw.Draw(image)
    summary = {item["field_id"]: item for item in field_summaries}
    for field in page["fields"]:
        x0, y0 = float(field["x_layout_dots"]), float(field["y_layout_dots"])
        x1, y1 = x0 + float(field["w_layout_dots"]), y0 + float(field["h_layout_dots"])
        px, py = _affine_apply(coef, np.array([x0, x1, x1, x0]),
                              np.array([y0, y0, y1, y1]))
        polygon = [(float(x / fx), float(y / fy)) for x, y in zip(px, py, strict=True)]
        row = summary[field["field_id"]]
        color = (40, 210, 60) if row["hard_error_rate"] <= 0.02 else (230, 60, 40)
        draw.line(polygon + [polygon[0]], fill=color, width=2)
    rect = safe_extent.get("usable_rectangle_mm")
    if rect is not None:
        x0, y0 = ec.mm_to_dots(rect["x0_mm"]), ec.mm_to_dots(rect["y0_mm"])
        x1, y1 = ec.mm_to_dots(rect["x1_mm"]), ec.mm_to_dots(rect["y1_mm"])
        px, py = _affine_apply(coef, np.array([x0, x1, x1, x0]),
                              np.array([y0, y0, y1, y1]))
        polygon = [(float(x / fx), float(y / fy)) for x, y in zip(px, py, strict=True)]
        draw.line(polygon + [polygon[0]], fill=(50, 130, 255), width=3)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)


def analyze(*, scan: Path, manifest_path: Path, scan_dpi_x: float,
            scan_dpi_y: float, printer_id: str, scanner_id: str,
            print_path: str, scan_mode: str, role: str, media: str,
            consumable_state: str, sheet_id: str, capture_id: str,
            readback_dpi: tuple[int, int] | None, max_bp_iters: int,
            diag: Path | None, trace_dir: Path | None,
            geometry_mode: str = "field",
            window_cells: int = WINDOW_TARGET_CELLS) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    _verify_manifest(manifest)
    page = manifest["pages"][0]
    if not sheet_id:
        raise ValueError("sheet_id must identify the physical print copy")
    source = RasterSource(scan)
    coef, geometry, thumb, fx, fy = register(
        source, page, scan_dpi_x, scan_dpi_y
    )
    strips = decode_machine_strips(
        source, coef, page, scan_dpi_x, scan_dpi_y
    )
    trace_index: list[dict[str, Any]] = []
    observations, field_summaries = [], []
    for ordinal, field in enumerate(page["fields"]):
        observation, summary = score_field(
            source=source, coef=coef, page=page, field=field,
            scan_dpi_x=scan_dpi_x, scan_dpi_y=scan_dpi_y,
            physical_sheet_id=sheet_id, max_bp_iters=max_bp_iters,
            trace_dir=trace_dir, trace_index=trace_index, ordinal=ordinal,
            geometry_mode=geometry_mode, window_cells=window_cells,
        )
        observations.append(observation)
        field_summaries.append(summary)
        ldpc_text = ""
        if summary["ldpc"]:
            certified = sum(item["certified"] for item in summary["ldpc"])
            attempted = sum(item["attempted"] for item in summary["ldpc"])
            ldpc_text = f" LDPC={certified}/{attempted}"
        geometry_text = ""
        if summary.get("geometry"):
            g = summary["geometry"]
            geometry_text = (f" win={g['n_locked']}/{g['n_windows']}"
                             f" spanY={g['phase_y_span_cells']:.2f}"
                             if g["phase_y_span_cells"] is not None
                             else f" win={g['n_locked']}/{g['n_windows']}")
        print(f"{field['field_id']}: BER={summary['hard_error_rate']:.4f} "
              f"MI={summary['mutual_information_bpc']:.3f}{ldpc_text}{geometry_text}")

    probes = score_probes(source, coef, page, thumb)
    geometry["internal_warp"] = score_plus_marks(source, coef, page)
    safe_extent = _payload_safe_extent(field_summaries)
    capacities = _capacity(page, field_summaries, safe_extent)
    factorials = {
        role_name: [
            row for row in field_summaries if row["role"] == role_name
        ]
        for role_name in (
            "shape-control", "aspect-control", "constellation-control",
            "emission-path-control",
        )
    }
    factorials = {key: value for key, value in factorials.items() if value}
    if trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        (trace_dir / "index.json").write_text(json.dumps({
            "schema": "paper-store/e025/trace-index/v1",
            "manifest_semantic_sha256": manifest["manifest_semantic_sha256"],
            "capture_sha256": _sha256_file(scan), "fields": trace_index,
        }, indent=2, sort_keys=True) + "\n")

    automatic_readback = None
    valid_strips = [item for item in strips if item["crc_ok"]]
    if valid_strips:
        text = valid_strips[0]["fields"].get("RE")
        if text:
            try:
                automatic_readback = ec.parse_pair(text)
            except ValueError:
                automatic_readback = None
    footing = CaptureFooting(
        sheet_id=sheet_id, printer_id=printer_id, scanner_id=scanner_id,
        print_path=print_path, scan_mode=scan_mode,
        scan_dpi_x=scan_dpi_x, scan_dpi_y=scan_dpi_y,
        requested_dpi=(None if manifest["requested_dpi"] is None
                       else tuple(manifest["requested_dpi"])),
        readback_dpi=readback_dpi or automatic_readback,
        media=media, consumable_state=consumable_state,
        capture_sha256=_sha256_file(scan), capture_id=capture_id or scan.stem,
    )
    if diag is not None:
        _diag_overlay(thumb, coef, fx, fy, page, field_summaries, safe_extent, diag)
    metadata = {
        "experiment": "E025", "role": role,
        "stimulus_manifest": str(manifest_path),
        "stimulus_manifest_semantic_sha256": manifest["manifest_semantic_sha256"],
        "bundle_id": manifest["bundle_id"], "page_id": page["page_id"],
        "page_kind": page["page_kind"],
        "source_shape": [source.height, source.width, source.channels],
        "source_memmapped": source.memmapped,
        "detector_contract": (
            "phase indices mod8=0; QDA train mod8=1,2,3; held-out validation "
            "mod8=4,5,6,7; FEC suffix disjoint"
        ),
        "geometry_contract": (
            "field: one global corner affine + one constant per-field phase "
            "clamped to +/-0.48 cell (analyzer v2). "
            "window: per-window phase, wide unclamped first search then "
            "chained local search, per-window QDA, lock certified on the "
            "phase split, unresolved windows excluded from channel statistics "
            "and counted (analyzer v3)."
        ),
        "e025": {
            "schema": ("paper-store/e025/analysis/v2" if geometry_mode == "field"
                       else "paper-store/e025/analysis/v3-window"),
            "geometry_mode": geometry_mode,
            "device_readback_strips": strips,
            "geometry": geometry,
            "probes": probes,
            "field_summaries": field_summaries,
            "candidate_factorials": factorials,
            "payload_safe_extent": safe_extent,
            "capacity": capacities,
            "trace_directory": None if trace_dir is None else str(trace_dir),
        },
    }
    if diag is not None:
        metadata["diagnostic_png"] = str(diag)
    document = report_document(
        footing=footing, observations=observations, metadata=metadata
    )
    if safe_extent["usable_rectangle_mm"] is not None:
        rect = safe_extent["usable_rectangle_mm"]
        print(f"payload-safe rectangle {rect['width_mm']:.1f} x {rect['height_mm']:.1f} "
              f"mm ({rect['area_mm2']:.0f} mm2)")
    else:
        print("payload-safe rectangle unresolved: one or more edge arms did not bracket")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scan-dpi", type=float)
    parser.add_argument("--scan-dpi-x", type=float)
    parser.add_argument("--scan-dpi-y", type=float)
    parser.add_argument("--printer-id", required=True)
    parser.add_argument("--scanner-id", required=True)
    parser.add_argument("--print-path", default="raw-postscript")
    parser.add_argument("--scan-mode", default="unknown")
    parser.add_argument("--role", choices=("emitter", "sensor", "pipeline"),
                        default="pipeline")
    parser.add_argument("--media", default="")
    parser.add_argument("--consumable-state", default="")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--capture-id", default="")
    parser.add_argument("--readback", help="manual effective XxY fallback")
    parser.add_argument("--max-bp-iters", type=int, default=60)
    parser.add_argument("--geometry", choices=("field", "window"),
                        default="field",
                        help="field = analyzer v2 (one constant phase per "
                             "field); window = analyzer v3 per-window phase")
    parser.add_argument("--window-cells", type=int, default=WINDOW_TARGET_CELLS,
                        help="target window side in cells for --geometry window")
    parser.add_argument("--diag", type=Path)
    parser.add_argument("--trace-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    dpi_x = args.scan_dpi_x or args.scan_dpi
    dpi_y = args.scan_dpi_y or args.scan_dpi or dpi_x
    if dpi_x is None or dpi_y is None:
        raise SystemExit("provide --scan-dpi or both axis-specific scan DPIs")
    trace_dir = args.trace_dir
    document = analyze(
        scan=args.scan, manifest_path=args.manifest,
        scan_dpi_x=dpi_x, scan_dpi_y=dpi_y,
        printer_id=args.printer_id, scanner_id=args.scanner_id,
        print_path=args.print_path, scan_mode=args.scan_mode, role=args.role,
        media=args.media, consumable_state=args.consumable_state,
        sheet_id=args.sheet_id, capture_id=args.capture_id,
        readback_dpi=None if args.readback is None else ec.parse_pair(args.readback),
        max_bp_iters=args.max_bp_iters, diag=args.diag, trace_dir=trace_dir,
        geometry_mode=args.geometry, window_cells=args.window_cells,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(f"report {args.out}")
    if trace_dir is not None:
        print(f"traces {trace_dir}")


if __name__ == "__main__":
    main()
