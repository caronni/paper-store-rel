"""Tier-i registration probes: certified GT vs the scan, at committed poses.

One probe measures, for ONE certified tile and ONE plane whose stream is
certified there, the subpixel displacement between

* the exact printed cells of that plane (re-encoded from the certificate
  by :func:`holo.receive.color_projection.project_certified_color_tile`,
  expanded to dots by the format's solid-cell rule), and
* the archived scan, sampled through the committed ``PoseRecord`` affine,

and reports it in PRINT-DOTS along the PAGE axes (the units the field
stores; docs/PLANE-FIELDS.md §6.1 constraint 1).

Reused verbatim-in-spirit from ``scratch/xerox-v1-20260818/regmap-gt``
(the supervised instrument this one must reproduce): the separable
cumsum ``boxcar``/``highpass``, the normalised FFT ``xcorr_shift`` with
its parabolic peak and background-rms ratio, the Lucas-Kanade
``lk_shift`` subpixel refinement against a Gaussian-blurred model, the
``_lock`` = FFT-integer-then-LK composition with its 1 px sanity clause,
and the B-channel crosstalk-removal form ``B - a*R - b*G``.  What is NOT
reused: the global nine-anchor scan<-dot affine (this instrument uses the
receiver's committed per-window poses) and the page GT sidecar (this
instrument re-encodes from certificates).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates

PLANE_NAMES = ("C", "M", "Y")
CHANNEL_OF_PLANE = (0, 1, 2)       # R<->C, G<->M, B<->Y (ink = dark)

HIGHPASS_PX = 25                   # boxcar width, regmap-gt HP
MODEL_SIGMA_PX = 2.0               # regmap-gt MODEL_SIGMA
LK_BORDER_PX = 12
PROBE_MARGIN_CELLS = 4             # model window inset inside the tile
SEARCH_DOTS = 4.0                  # task-pinned probe range, +/- print dots
PLANE_SEARCH_DOTS = 3.0            # per-plane range around the common lock

_SCAN_CACHE: dict[str, np.ndarray] = {}


# --------------------------------------------------------------------------
# scan access (read-only, memmap; one handle per worker process)
# --------------------------------------------------------------------------
def scan_image(path: str) -> np.ndarray:
    image = _SCAN_CACHE.get(path)
    if image is None:
        import tifffile
        image = tifffile.imread(path, out="memmap")
        _SCAN_CACHE[path] = image
    return image


def scan_patch(path: str, y0: int, x0: int, height: int, width: int
               ) -> np.ndarray | None:
    image = scan_image(path)
    if y0 < 0 or x0 < 0 or y0 + height > image.shape[0] \
            or x0 + width > image.shape[1]:
        return None
    return np.asarray(image[y0:y0 + height, x0:x0 + width, :], np.float32)


# --------------------------------------------------------------------------
# filters and correlation (adapted from regmap-gt/_common.py, _subpix.py)
# --------------------------------------------------------------------------
def boxcar(field: np.ndarray, width: int) -> np.ndarray:
    """Separable boxcar via cumulative sums, 'same' with edge replication."""
    def one(values: np.ndarray, axis: int) -> np.ndarray:
        pad = [(0, 0)] * values.ndim
        pad[axis] = (width // 2, width - 1 - width // 2)
        padded = np.pad(values, pad, mode="edge")
        cumulative = np.cumsum(padded, axis=axis)
        low = [slice(None)] * values.ndim
        high = [slice(None)] * values.ndim
        low[axis] = slice(width, None)
        high[axis] = slice(0, -width)
        head = np.take(cumulative, [width - 1], axis=axis)
        body = cumulative[tuple(low)] - cumulative[tuple(high)]
        return np.concatenate([head, body], axis=axis) / width
    return one(one(field, 0), 1)


def highpass(field: np.ndarray, width: int = HIGHPASS_PX) -> np.ndarray:
    return field - boxcar(field, width)


def xcorr_shift(reference: np.ndarray, target: np.ndarray, max_shift: int):
    """Normalised cross-correlation of equal-size fields (regmap-gt form).

    Returns ``(dy, dx, peak, ratio)``: the shift that aligns ``target``
    onto ``reference``, the normalised peak, and peak / background rms.
    """
    a = reference - reference.mean()
    b = target - target.mean()
    na = float(np.sqrt((a * a).sum()))
    nb = float(np.sqrt((b * b).sum()))
    if na == 0.0 or nb == 0.0:
        return 0.0, 0.0, 0.0, 0.0
    spectrum = np.fft.rfft2(a) * np.conj(np.fft.rfft2(b))
    surface = np.fft.fftshift(
        np.fft.irfft2(spectrum, s=a.shape) / (na * nb))
    cy, cx = a.shape[0] // 2, a.shape[1] // 2
    m = int(max_shift)
    window = surface[cy - m:cy + m + 1, cx - m:cx + m + 1]
    iy, ix = np.unravel_index(np.argmax(window), window.shape)
    peak = float(window[iy, ix])

    def parabola(minus: float, centre: float, plus: float) -> float:
        curvature = minus - 2 * centre + plus
        return 0.0 if curvature == 0 else 0.5 * (minus - plus) / curvature

    sy = sx = 0.0
    if 0 < iy < window.shape[0] - 1:
        sy = parabola(window[iy - 1, ix], window[iy, ix], window[iy + 1, ix])
    if 0 < ix < window.shape[1] - 1:
        sx = parabola(window[iy, ix - 1], window[iy, ix], window[iy, ix + 1])
    background = window.copy()
    y0, y1 = max(0, iy - 5), min(window.shape[0], iy + 6)
    x0, x1 = max(0, ix - 5), min(window.shape[1], ix + 6)
    background[y0:y1, x0:x1] = np.nan
    rms = float(np.sqrt(np.nanmean(background ** 2)))
    ratio = peak / rms if rms > 0 else 0.0
    return (iy - m) + sy, (ix - m) + sx, peak, ratio


def lk_shift(model: np.ndarray, target: np.ndarray, iterations: int = 6,
             border: int = LK_BORDER_PX, init=(0.0, 0.0)):
    """Find ``(dy,dx)`` with ``target(y,x) ~ a*model(y-dy, x-dx) + b``.

    Cells are 2 dots = 8 scan px, so the raw correlation peak is a broad
    triangle and parabolic interpolation on it is biased; the LK step
    against a smoothed model is unbiased under symmetric blur mismatch.
    """
    m = model.astype(np.float64)
    t = target.astype(np.float64)
    gy, gx = np.gradient(gaussian_filter(m, 1.0))
    height, width = m.shape
    ys, xs = np.mgrid[border:height - border, border:width - border]
    dy, dx = float(init[0]), float(init[1])
    for _ in range(iterations):
        sampled = map_coordinates(m, [ys - dy, xs - dx], order=3,
                                  mode="nearest")
        grad_y = map_coordinates(gy, [ys - dy, xs - dx], order=1,
                                 mode="nearest")
        grad_x = map_coordinates(gx, [ys - dy, xs - dx], order=1,
                                 mode="nearest")
        patch = t[border:height - border, border:width - border]
        design = np.stack([sampled.ravel(), np.ones(sampled.size)], axis=1)
        coefficients, *_ = np.linalg.lstsq(design, patch.ravel(), rcond=None)
        amplitude, offset = coefficients
        if amplitude <= 0:
            return np.nan, np.nan, 0.0
        residual = patch.ravel() - (amplitude * sampled.ravel() + offset)
        jacobian = np.stack(
            [-amplitude * grad_y.ravel(), -amplitude * grad_x.ravel()],
            axis=1)
        try:
            step, *_ = np.linalg.lstsq(jacobian, residual, rcond=None)
        except np.linalg.LinAlgError:
            return np.nan, np.nan, 0.0
        dy += float(step[0])
        dx += float(step[1])
        if abs(step[0]) < 1e-4 and abs(step[1]) < 1e-4:
            break
        if abs(dy) > 40 or abs(dx) > 40:
            return np.nan, np.nan, 0.0
    sampled = map_coordinates(m, [ys - dy, xs - dx], order=3, mode="nearest")
    patch = t[border:height - border, border:width - border]
    centred_model = sampled - sampled.mean()
    centred_patch = patch - patch.mean()
    denominator = float(np.sqrt((centred_model ** 2).sum()
                                * (centred_patch ** 2).sum()))
    correlation = (float((centred_model * centred_patch).sum()) / denominator
                   if denominator > 0 else 0.0)
    return dy, dx, correlation


def _lock(model: np.ndarray, target: np.ndarray, search_px: int):
    """FFT integer lock + LK subpixel (regmap-gt ``_lock``)."""
    dy, dx, peak, ratio = xcorr_shift(model, target, search_px)
    dy, dx = -dy, -dx        # displacement of scan content vs the model
    ly, lx, correlation = lk_shift(model, target, init=(round(dy), round(dx)))
    if (np.isfinite(ly) and abs(ly - dy) < 1.0 and abs(lx - dx) < 1.0):
        return ly, lx, peak, ratio, correlation, "lk"
    return dy, dx, peak, ratio, correlation, "fft"


# --------------------------------------------------------------------------
# one tile's probe
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TileJob:
    """Everything a worker needs for one certified tile (picklable)."""

    page: int
    tile_y: int
    tile_x: int
    planes: tuple[int, ...]              # plane indices with a certificate
    native_affine: tuple[float, ...]     # 2x3 row-major, page-cell -> px
    bits: np.ndarray                     # (64,64,3) uint8 printed presence
    known_all: bool
    pose_id: str
    lane_id: str
    pose_quality: float
    cell_dots: int


def _affine_parts(native_affine) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(native_affine, np.float64).reshape(2, 3)
    return matrix[:, :2].copy(), matrix[:, 2].copy()


def pose_scale_px(native_affine) -> tuple[float, float]:
    """(px per cell along page-y, px per cell along page-x) for one pose."""
    linear, _ = _affine_parts(native_affine)
    return (float(np.hypot(*linear[:, 0])), float(np.hypot(*linear[:, 1])))


def _render_model(job: TileJob, linear: np.ndarray, translation: np.ndarray,
                  oy: int, ox: int, height: int, width: int
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Printed-dot model images for this tile, on the scan pixel lattice.

    A cell is a solid ``cell_dots`` x ``cell_dots`` dot block
    (``gen.compose.cells_to_dots``), so nearest-cell lookup of the
    inverse-mapped pixel centre IS the exact printed field.
    """
    inverse = np.linalg.inv(linear)
    ys, xs = np.mgrid[oy:oy + height, ox:ox + width]
    points = np.stack([ys.ravel(), xs.ravel()], axis=1).astype(np.float64)
    cells = (points - translation) @ inverse.T
    index = np.rint(cells).astype(np.int64)
    index[:, 0] -= job.tile_y * 64
    index[:, 1] -= job.tile_x * 64
    inside = ((index[:, 0] >= 0) & (index[:, 0] < 64)
              & (index[:, 1] >= 0) & (index[:, 1] < 64))
    clipped = np.clip(index, 0, 63)
    models = np.zeros((len(job.planes), height * width), np.float32)
    for slot, plane in enumerate(job.planes):
        values = job.bits[clipped[:, 0], clipped[:, 1], plane].astype(
            np.float32)
        models[slot] = np.where(inside, values, 0.0)
    outside_fraction = float(1.0 - inside.mean())
    return models.reshape(len(job.planes), height, width), np.float64(
        outside_fraction)


def probe_tile(job: TileJob, scan_path: str, crosstalk: tuple[float, float]
               ) -> dict:
    """Measure per-plane offsets for one certified tile.  Read-only."""
    linear, translation = _affine_parts(job.native_affine)
    low = PROBE_MARGIN_CELLS
    high = 64 - PROBE_MARGIN_CELLS - 1
    corners = np.array([[job.tile_y * 64 + a, job.tile_x * 64 + b]
                        for a in (low, high) for b in (low, high)],
                       np.float64)
    projected = corners @ linear.T + translation
    py_scale, px_scale = pose_scale_px(job.native_affine)
    px_per_dot = 0.5 * (py_scale + px_scale) / job.cell_dots
    search_px = int(round(SEARCH_DOTS * px_per_dot))
    plane_search_px = int(round(PLANE_SEARCH_DOTS * px_per_dot))
    pad = search_px + 8

    oy = int(np.floor(projected[:, 0].min()))
    ox = int(np.floor(projected[:, 1].min()))
    height = int(np.ceil(projected[:, 0].max())) - oy + 1
    width = int(np.ceil(projected[:, 1].max())) - ox + 1
    patch = scan_patch(scan_path, oy - pad, ox - pad,
                       height + 2 * pad, width + 2 * pad)
    if patch is None:
        return {"page": job.page, "tile_y": job.tile_y, "tile_x": job.tile_x,
                "error": "out_of_raster"}

    red = -highpass(patch[:, :, 0])
    green = -highpass(patch[:, :, 1])
    blue = -highpass(patch[:, :, 2])
    fields = (red, green,
              blue - crosstalk[0] * red - crosstalk[1] * green)

    models, outside_fraction = _render_model(
        job, linear, translation, oy, ox, height, width)
    blurred = np.stack([highpass(gaussian_filter(model, MODEL_SIGMA_PX))
                        for model in models])
    common_model = highpass(gaussian_filter(
        models.sum(axis=0), MODEL_SIGMA_PX))

    def window(field: np.ndarray, sy: int = 0, sx: int = 0) -> np.ndarray:
        return field[pad + sy:pad + sy + height, pad + sx:pad + sx + width]

    common_target = sum(window(fields[plane]) for plane in job.planes)
    cy, cx, c_peak, c_ratio, c_corr, c_src = _lock(
        common_model, common_target, search_px)
    if not np.isfinite(cy) or abs(cy) > pad - 8 or abs(cx) > pad - 8:
        return {"page": job.page, "tile_y": job.tile_y, "tile_x": job.tile_x,
                "error": "common_lock_failed"}
    iy, ix = int(round(cy)), int(round(cx))

    inverse = np.linalg.inv(linear)

    def to_dots(dy_px: float, dx_px: float) -> tuple[float, float]:
        delta = inverse @ np.array([dy_px, dx_px], np.float64)
        return (float(delta[1] * job.cell_dots),
                float(delta[0] * job.cell_dots))     # (dx, dy) in page dots

    result = {
        "page": job.page, "tile_y": job.tile_y, "tile_x": job.tile_x,
        "pose_id": job.pose_id, "lane_id": job.lane_id,
        "pose_quality": job.pose_quality,
        "px_per_dot": px_per_dot,
        "outside_fraction": float(outside_fraction),
        "known_all": bool(job.known_all),
        "window_px": [int(height), int(width)],
        "common_dots_xy": list(to_dots(cy, cx)),
        "common_peak": float(c_peak), "common_ratio": float(c_ratio),
        "common_corr": float(c_corr), "common_src": c_src,
        "planes": {},
    }
    for slot, plane in enumerate(job.planes):
        dy, dx, peak, ratio, correlation, source = _lock(
            blurred[slot], window(fields[plane], iy, ix), plane_search_px)
        if not np.isfinite(dy):
            result["planes"][PLANE_NAMES[plane]] = {"error": "lock_failed"}
            continue
        offset_dots_xy = to_dots(iy + dy, ix + dx)
        result["planes"][PLANE_NAMES[plane]] = {
            "offset_dots_xy": list(offset_dots_xy),
            "peak": float(peak), "ratio": float(ratio),
            "corr": float(correlation), "src": source,
        }
    return result


def verify_pose(job: TileJob, scan_path: str,
                shifts_cells=(-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0)
                ) -> dict | None:
    """Prove the ``native_affine`` convention before trusting any probe.

    ``PoseRecord.native_affine`` is documented as the row-major 2x3 map
    from ABSOLUTE PAGE-CELL (y,x) to native-source pixel CENTRES.  If
    that is what it is, then sampling the raw scan at the mapped centres
    of one certified tile must (a) separate the plane's ink-1 cells from
    its ink-0 cells in that plane's channel, and (b) peak at zero cell
    shift — a half-cell error in the origin convention (centre vs
    corner) would collapse the separation and move the argmax.
    """
    linear, translation = _affine_parts(job.native_affine)
    grid_y, grid_x = np.mgrid[0:64, 0:64]
    cells = np.stack([grid_y.ravel() + job.tile_y * 64,
                      grid_x.ravel() + job.tile_x * 64], axis=1).astype(
                          np.float64)
    corners = cells @ linear.T + translation
    margin = 3 * int(round(max(pose_scale_px(job.native_affine))))
    oy = int(np.floor(corners[:, 0].min())) - margin
    ox = int(np.floor(corners[:, 1].min())) - margin
    height = int(np.ceil(corners[:, 0].max())) - oy + margin
    width = int(np.ceil(corners[:, 1].max())) - ox + margin
    patch = scan_patch(scan_path, oy, ox, height, width)
    if patch is None:
        return None
    entry: dict = {"page": job.page, "tile_y": job.tile_y,
                   "tile_x": job.tile_x, "planes": {}, "shifts_cells": list(
                       shifts_cells)}
    luma = patch.mean(axis=2)
    any_ink = job.bits.reshape(4096, 3).max(axis=1).astype(np.float64)
    for plane in job.planes:
        bits = job.bits[:, :, plane].reshape(4096)
        channel = patch[:, :, CHANNEL_OF_PLANE[plane]]
        contrasts = []
        for shift in shifts_cells:
            points = ((cells + np.array([0.0, shift])) @ linear.T
                      + translation - np.array([oy, ox], np.float64))
            values = map_coordinates(channel, points.T, order=1,
                                     mode="nearest")
            contrasts.append(float(values[bits == 0].mean()
                                   - values[bits == 1].mean()))
        points = cells @ linear.T + translation - np.array([oy, ox],
                                                           np.float64)
        sampled_luma = map_coordinates(luma, points.T, order=1,
                                       mode="nearest")
        entry["planes"][PLANE_NAMES[plane]] = {
            "ink_contrast_by_x_shift": contrasts,
            "argmax_shift_cells": float(
                shifts_cells[int(np.argmax(contrasts))]),
            "luma_vs_any_ink_pearson": float(
                np.corrcoef(sampled_luma, any_ink)[0, 1]),
            "ink_fraction": float(bits.mean()),
        }
    return entry


def fit_crosstalk(jobs: list[TileJob], scan_path: str, count: int = 12,
                  seed: int = 20260820) -> tuple[float, float]:
    """Global least squares ``B ~ a*R + b*G`` on highpassed channels.

    regmap-gt's ``fit_crosstalk``, re-fitted here from certified-tile
    patches so the instrument carries no constant imported from the
    supervised measurement it is validated against.
    """
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(jobs), size=min(count, len(jobs)), replace=False)
    design: list[np.ndarray] = []
    observed: list[np.ndarray] = []
    for index in picks:
        job = jobs[int(index)]
        linear, translation = _affine_parts(job.native_affine)
        centre = (np.array([job.tile_y * 64 + 32.0, job.tile_x * 64 + 32.0])
                  @ linear.T + translation)
        patch = scan_patch(scan_path, int(centre[0]) - 256,
                           int(centre[1]) - 256, 512, 512)
        if patch is None:
            continue
        red = highpass(patch[:, :, 0])[32:-32, 32:-32].ravel()
        green = highpass(patch[:, :, 1])[32:-32, 32:-32].ravel()
        blue = highpass(patch[:, :, 2])[32:-32, 32:-32].ravel()
        design.append(np.stack([red, green], axis=1))
        observed.append(blue)
    if not design:
        raise SystemExit("crosstalk fit found no usable patches")
    coefficients, *_ = np.linalg.lstsq(
        np.concatenate(design), np.concatenate(observed), rcond=None)
    return float(coefficients[0]), float(coefficients[1])


__all__ = [
    "CHANNEL_OF_PLANE", "PLANE_NAMES", "SEARCH_DOTS", "TileJob",
    "boxcar", "fit_crosstalk", "highpass", "lk_shift", "pose_scale_px",
    "probe_tile", "scan_image", "scan_patch", "verify_pose", "xcorr_shift",
]
