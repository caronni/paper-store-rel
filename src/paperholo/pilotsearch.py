"""E022 pilot-field placement between platen survey and payload decoding.

v2 (2026-07-14): per-WINDOW native pose. The v1 implementation fitted one
similarity pose per E021 region on an internal block-mean working image and
selected its angle with a region-scale contrast objective that is measurably
flat in angle (decimated-3 largest region: contrast 40.34 at an 0.55 deg
wrong angle vs 40.73 at the true angle -> whole region unresolved while the
true angle placed at mismatch 0.144). v2 deletes the working image and the
region pose:

- every observation window measures its OWN full affine pose: the two
  lattice fundamentals of its gradient spectrum give the 2x2 Jacobian
  (rotation + anisotropic scale + shear) blind mod 90, refined sub-bin by
  zoom-DFT; sub-cell phase by coarse search + quadratic subpixel;
- cells are sampled from the ORIGINAL scan through that pose: one
  axis-aligned box prefilter per region crop (radiometric aperture, the
  measured decimate-first advantage) and one order-1 subpixel read per cell
  centre. No rotation, no deskew, no decimated working raster; 23.85
  px/cell is sampled as exactly 23.85 px/cell;
- an accepted window propagates its FULL pose to the region's remaining
  windows (rot90-aware page-origin prediction through the Jacobian); the
  neighbor still fits its own pose and passes its own gates. Consistency
  failures re-anchor through the full-page search and may open a new pose
  component (touching scraps, folds, scanner y-steps);
- the local propagated placement searches SEARCH-parity sites only and is
  accepted on the disjoint VALIDATION-parity sites (the v1 neighbor route
  violated this split); rivals are reported only where actually searched;
- pilot observations are emitted under the ERODED window mask (the rim
  samples backing and is confidently wrong - the measured 016.7 class);
- windows that add no needed PILOT support are still recorded as full
  redundant placements (pose + audited core): payload need != pilot need,
  and E023 samples payload cells through every gated pose. Only their
  pilot emission, anchor duty, and the accepted counter are skipped.

BCH remains an optional fast address seed for high-quality complete words
(measured 3.3x cheaper than one padded full-page correlation), verified
against the pilot field, never the only acceptance evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable, Sequence

import numpy as np
from scipy import ndimage
from scipy.signal import fftconvolve

from . import acquire, place, pilots
from .compose import ComposeSpec
from .formats import FormatDescriptor
from .platen import PayloadRegion, PayloadSurvey


@dataclass(frozen=True)
class SearchConfig:
    window_cells: int = 200
    overlap_cells: int = 40
    erode_cells: int = 2
    min_support: int = 30
    found_tile_min_sites: int = 20
    gate_true: float = 0.20
    gate_decoy: float = 0.20
    gate_gap: float = 0.08
    validation_true: float = 0.24
    neighbor_radius_cells: int = 3
    consistency_cells: int = 2
    bch_first: bool = True
    bch_max_errors: int = 13
    bch_max_tiles: int = 1
    bch_min_mask_fraction: float = 0.82
    allow_overhang: bool = True
    # v2 pose machinery
    pitch_tol: float = 0.06          # window pitch vs survey prior
    shear_tol_deg: float = 3.0       # basis-vector orthogonality bound
    aperture_cells: float = 0.7      # box prefilter, fraction of pitch
    phase_step_cells: float = 0.125  # coarse phase grid step
    spectral_px: int = 2048          # spectral crop cap (per window)
    min_spectral_periods: int = 12   # below: reuse region J or refuse
    subdivide: bool = True
    min_window_cells: int = 70
    refine: bool = True
    refine_angle_deg: float = 0.15
    refine_angle_step_deg: float = 0.05
    refine_phase_cells: float = 0.25
    refine_phase_step_cells: float = 0.0625
    # straddle audit (a window across a scanner y-step or fold locks one
    # side's lattice; the other side's sites read ~50% against the placed
    # address and must not be emitted). Change-point on the per-row/col
    # wrong-rate profile — fixed blocks leak at block boundaries.
    audit_bin_cells: int = 4
    audit_bad: float = 0.35          # stripped side must read at least this
    audit_good: float = 0.20         # kept side must read at most this
    audit_min_sites: int = 15
    audit_post_bar: float = 0.25     # residual wrong rate after strips
    audit_reject_fraction: float = 0.5


@dataclass(frozen=True)
class AffinePose:
    """Cell-index coordinates -> original scan pixel coordinates.

    origin_yx is the FULL-scan native (subpixel) coordinate of cell (0,0)'s
    centre; jacobian_yx rows map a (cell_y, cell_x) step to (dy, dx) px.
    det(J) > 0 always; rot90/reflection bookkeeping stays outside J.
    footing_factor is 1 in v2 (native sampling; kept for report compat)."""

    origin_yx: tuple[float, float]
    jacobian_yx: tuple[tuple[float, float], tuple[float, float]]
    angle_deg: float
    pitch_px: float
    phase_yx: tuple[float, float]
    footing_factor: int = 1

    def matrix(self) -> np.ndarray:
        return np.asarray(self.jacobian_yx, np.float64)

    def points(self, cells_yx: np.ndarray) -> np.ndarray:
        q = np.asarray(cells_yx, np.float64)
        return q @ self.matrix().T + np.asarray(self.origin_yx, np.float64)


@dataclass
class Window:
    """One observation window: native px origin (region-local) + cell grid."""

    y: int          # region-local native px
    x: int
    h: int          # grid CELLS
    w: int
    support: int    # estimated mask support in cells
    depth: int = 0  # subdivision depth


@dataclass(frozen=True)
class WindowProgress:
    """Detached observer snapshot for one in-flight E022 window.

    The snapshot is never stored in :class:`SearchResult`; it exists only so
    entry points can render progress without reaching into mutable search
    locals.  Coordinates and counts are plain JSON-safe Python values.
    """

    region_index: int
    ordinal: int
    queue_total: int
    queue_remaining: int
    depth: int
    stage: str
    outcome: str | None
    window_origin_yx_px: tuple[int, int]
    window_shape_yx_cells: tuple[int, int]
    scan_bbox_yxhw_px: tuple[float, float, float, float]
    anchors: int
    placements: int
    accepted: int
    attempted_routes: tuple[str, ...]
    method: str | None
    pose_origin_yx: tuple[float, float] | None
    jacobian_yx: tuple[tuple[float, float], tuple[float, float]] | None
    angle_deg: float | None
    pitch_px: float | None
    pitch_v_px: float | None
    pitch_u_px: float | None
    ortho_dev_deg: float | None
    phase_conf: float | None
    phase_yx: tuple[float, float] | None
    placement_page: int | None
    placement_origin_yx: tuple[int, int] | None
    placement_rot_k: int | None
    mismatch: float | None
    validation_mismatch: float | None
    support: int | None
    elapsed_s: float


def _observer_float(value) -> float | None:
    """Return a finite detached float suitable for strict JSON metadata."""
    if value is None:
        return None
    out = float(value)
    return out if np.isfinite(out) else None


@dataclass
class RegionContext:
    """Per-region native sampling context (no decimated working image)."""

    region_index: int
    region: PayloadRegion
    y0: int
    x0: int
    crop: np.ndarray          # float32, backing-filled outside the mask
    filt: np.ndarray          # box-prefiltered crop (the sampling aperture)
    mask_f: np.ndarray        # float32 mask for coverage interpolation
    backing: float
    pitch_prior: float
    aperture_px: int
    lattice_f: np.ndarray | None = None   # region-level reciprocal rows (2x2)


@dataclass
class PlacedWindow:
    region_index: int
    window: Window
    page: int
    origin_yx: tuple[int, int]
    rot_k: int
    method: str
    mismatch: float
    validation_mismatch: float
    rival_mismatch: float | None
    support: int
    pose: AffinePose
    elapsed_s: float
    component: int = 0
    rival_searched: bool = False
    predicted_residual_cells: float | None = None
    bch_errors: int | None = None
    scan_id: str = ""
    # gated placement whose pilot sites were all already observed this scan;
    # carries payload coverage for E023 but emitted no pilot observations
    # and never served as an anchor (component -1 when not chained).
    redundant: bool = False
    diagnostics: dict = field(default_factory=dict)
    page_cells_yx: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 2), np.int32), repr=False
    )


@dataclass(frozen=True)
class PilotObservation:
    region_index: int
    window_yx: tuple[int, int]
    scan_yx: tuple[float, float]
    bit: int
    expected: int
    weight: float
    method: str
    scan_id: str = ""


@dataclass
class PilotTileEvidence:
    page: int
    tile_y: int
    tile_x: int
    expected_bits: np.ndarray
    observations: dict[int, list[PilotObservation]] = field(default_factory=dict)
    bch_ok: bool | None = None
    bch_attempted: bool = False
    bch_refused: bool = False
    bch_errors: int | None = None
    bch_erasures: int = 100
    bch_elapsed_s: float = 0.0

    @property
    def observed_sites(self) -> int:
        return len(self.observations)


@dataclass
class SearchResult:
    placements: list[PlacedWindow] = field(default_factory=list)
    tiles: dict[tuple[int, int, int], PilotTileEvidence] = field(default_factory=dict)
    region_states: dict[int, str] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)


# E023c continuation is a bounded route hint, not a new E022 tuning arm.
# Keep the bound outside SearchConfig so existing E022 state envelopes and
# their registered search-config digests remain schema-compatible.
LOWER_HINT_LIMIT = 8
LOWER_RUNNER_UP_RESERVE = 2


# ---------------------------------------------------------------------------
# region preparation (native footing)
# ---------------------------------------------------------------------------

def platen_backing(image: np.ndarray, border_px: int = 32) -> float:
    """Median border grey without materializing the full image (memmap-safe)."""
    b = border_px
    strips = [
        np.asarray(image[:b], np.float32).ravel(),
        np.asarray(image[-b:], np.float32).ravel(),
        np.asarray(image[:, :b], np.float32).ravel(),
        np.asarray(image[:, -b:], np.float32).ravel(),
    ]
    return float(np.median(np.concatenate(strips)))


def prepare_region(
    image: np.ndarray,
    region: PayloadRegion,
    region_index: int,
    pitch_px: float,
    *,
    config: SearchConfig = SearchConfig(),
    backing: float | None = None,
) -> RegionContext | None:
    """Native sampling context: crop + one box prefilter, no decimation."""
    if pitch_px <= 0:
        raise ValueError("pitch_px must be positive")
    y0, x0, h, w = region.bbox
    crop = np.asarray(image[y0:y0 + h, x0:x0 + w], np.float32)
    mask = np.asarray(region.mask[:crop.shape[0], :crop.shape[1]], bool)
    if crop.size == 0 or not mask.any():
        return None
    if backing is None:
        backing = platen_backing(image)
    filled = np.where(mask, crop, np.float32(backing))
    aperture = max(1, int(round(config.aperture_cells * pitch_px)))
    filt = ndimage.uniform_filter(filled, size=aperture, mode="nearest")
    return RegionContext(
        region_index=region_index, region=region, y0=int(y0), x0=int(x0),
        crop=filled, filt=filt, mask_f=mask.astype(np.float32),
        backing=float(backing), pitch_prior=float(pitch_px),
        aperture_px=aperture,
    )


# ---------------------------------------------------------------------------
# spectral pose (full affine Jacobian, blind mod 90)
# ---------------------------------------------------------------------------

def _zoom_peak(gw: np.ndarray, f_yx: np.ndarray, *, span_bins: float = 1.5,
               grid: int = 13) -> tuple[np.ndarray, float]:
    """Sub-bin DTFT peak around f_yx on a windowed gradient image."""
    hh, ww = gw.shape
    ys = np.arange(hh, dtype=np.float64)
    xs = np.arange(ww, dtype=np.float64)
    fy = f_yx[0] + np.linspace(-span_bins, span_bins, grid) / hh
    fx = f_yx[1] + np.linspace(-span_bins, span_bins, grid) / ww
    ey = np.exp(-2j * np.pi * np.outer(fy, ys)).astype(np.complex64)
    ex = np.exp(-2j * np.pi * np.outer(fx, xs)).astype(np.complex64)
    z = np.abs(ey @ gw.astype(np.complex64) @ ex.T)
    iy, ix = np.unravel_index(int(np.argmax(z)), z.shape)

    def _para(v0, v1, v2):
        d = v0 - 2 * v1 + v2
        return 0.0 if abs(d) < 1e-12 else float(
            np.clip(0.5 * (v0 - v2) / d, -0.5, 0.5))

    dy = dx = 0.0
    if 0 < iy < grid - 1:
        dy = _para(z[iy - 1, ix], z[iy, ix], z[iy + 1, ix])
    if 0 < ix < grid - 1:
        dx = _para(z[iy, ix - 1], z[iy, ix], z[iy, ix + 1])
    step_y = (fy[1] - fy[0]) if grid > 1 else 0.0
    step_x = (fx[1] - fx[0]) if grid > 1 else 0.0
    refined = np.array([fy[iy] + dy * step_y, fx[ix] + dx * step_x])
    return refined, float(z[iy, ix])


def _windowed_gradient(crop: np.ndarray) -> np.ndarray:
    g = np.hypot(*np.gradient(crop.astype(np.float32)))
    g -= float(g.mean())
    wy = np.hanning(g.shape[0]).astype(np.float32)[:, None]
    wx = np.hanning(g.shape[1]).astype(np.float32)[None, :]
    return g * wy * wx


def lattice_reciprocal(
    crop: np.ndarray,
    pitch_prior: float,
    *,
    band: float = 0.22,
    prior_f: np.ndarray | None = None,
) -> np.ndarray | None:
    """Both lattice fundamental frequency vectors, rows (f_v, f_u).

    f_v is the more-vertical peak (fy > 0), f_u the more-horizontal
    (fx > 0). With prior_f the coarse FFT is skipped and both peaks are
    zoom-refit locally (the cheap per-window path)."""
    gw = _windowed_gradient(crop)
    if prior_f is not None:
        fv, cv = _zoom_peak(gw, np.asarray(prior_f[0], np.float64))
        fu, cu = _zoom_peak(gw, np.asarray(prior_f[1], np.float64))
        if cv <= 0 or cu <= 0:
            return None
        return _normalize_reciprocal(np.stack([fv, fu]))
    mag = np.abs(np.fft.rfft2(gw))
    fy = np.fft.fftfreq(gw.shape[0])[:, None]
    fx = np.fft.rfftfreq(gw.shape[1])[None, :]
    fr = np.hypot(fy, fx)
    f0 = 1.0 / pitch_prior
    in_band = (fr > f0 * (1.0 - band)) & (fr < f0 * (1.0 + band))
    if not in_band.any():
        return None
    m1 = np.where(in_band, mag, 0.0)
    iy, ix = np.unravel_index(int(np.argmax(m1)), m1.shape)
    if m1[iy, ix] <= 0:
        return None
    f1 = np.array([float(fy[iy, 0]), float(fx[0, ix])])
    ang = np.arctan2(fy, fx)
    d1 = float(np.arctan2(f1[0], f1[1]))
    dist = np.abs(((ang - d1 + np.pi / 2) % np.pi) - np.pi / 2)
    perp = dist > (np.pi / 2 - np.deg2rad(20.0))
    m2 = np.where(in_band & perp, mag, 0.0)
    jy, jx = np.unravel_index(int(np.argmax(m2)), m2.shape)
    if m2[jy, jx] <= 0:
        return None
    f2 = np.array([float(fy[jy, 0]), float(fx[0, jx])])
    f1, _ = _zoom_peak(gw, f1)
    f2, _ = _zoom_peak(gw, f2)
    return _normalize_reciprocal(np.stack([f1, f2]))


def _normalize_reciprocal(f_rows: np.ndarray) -> np.ndarray:
    """Order rows (f_v more-vertical, f_u more-horizontal), fix signs."""
    a, b = f_rows[0], f_rows[1]
    if abs(a[0]) >= abs(a[1]):
        fv, fu = a, b
    else:
        fv, fu = b, a
    if fv[0] < 0:
        fv = -fv
    if fu[1] < 0:
        fu = -fu
    return np.stack([fv, fu])


def jacobian_from_reciprocal(f_rows: np.ndarray) -> np.ndarray:
    """J = F^-1: columns are the lattice basis vectors b_v, b_u (px)."""
    return np.linalg.inv(np.asarray(f_rows, np.float64))


def _pose_metrics(jac: np.ndarray) -> tuple[float, float, float, float]:
    b_v = jac[:, 0]
    b_u = jac[:, 1]
    pitch_v = float(np.hypot(*b_v))
    pitch_u = float(np.hypot(*b_u))
    angle = float(np.degrees(np.arctan2(b_u[0], b_u[1])))
    ortho = float(np.degrees(np.arctan2(b_v[0], b_v[1])) - 90.0 - angle)
    ortho = ((ortho + 180.0) % 360.0) - 180.0
    return pitch_v, pitch_u, angle, ortho


def fit_window_pose(
    ctx: RegionContext,
    win: Window,
    *,
    config: SearchConfig = SearchConfig(),
) -> tuple[AffinePose, dict] | None:
    """Spectral Jacobian + sub-cell phase for one window; None = refusal."""
    p = ctx.pitch_prior
    wy1 = min(ctx.crop.shape[0], win.y + int(round(win.h * p)))
    wx1 = min(ctx.crop.shape[1], win.x + int(round(win.w * p)))
    crop = ctx.crop[win.y:wy1, win.x:wx1]
    if min(crop.shape, default=0) < 4 * p:
        return None
    # spectral crop: central cap (speed), gradient masked to the region
    sp = config.spectral_px
    cy = (crop.shape[0] - min(crop.shape[0], sp)) // 2
    cx = (crop.shape[1] - min(crop.shape[1], sp)) // 2
    spec_crop = crop[cy:cy + sp, cx:cx + sp]
    meta: dict = {}
    if min(spec_crop.shape) >= config.min_spectral_periods * p:
        # every window measures its OWN lattice, full coarse fit. (A
        # region-level prior seeded the zoom refit in an earlier draft;
        # the fold fixture measured it inheriting the wrong side's angle
        # — a 1.6 deg fold moves the fundamental ~7 bins, outside the
        # zoom capture — so the prior path is reserved for windows too
        # small to measure at all.)
        f_rows = lattice_reciprocal(spec_crop, p)
    else:
        f_rows = ctx.lattice_f          # too small to measure: inherit
        meta["spectral"] = "inherited"
    if f_rows is None:
        return None
    jac = jacobian_from_reciprocal(f_rows)
    pitch_v, pitch_u, angle, ortho = _pose_metrics(jac)
    meta.update({"pitch_v_px": pitch_v, "pitch_u_px": pitch_u,
                 "angle_deg": angle, "ortho_dev_deg": ortho})
    if (abs(pitch_v / p - 1.0) > config.pitch_tol
            or abs(pitch_u / p - 1.0) > config.pitch_tol
            or abs(ortho) > config.shear_tol_deg
            or np.linalg.det(jac) <= 0):
        return None
    if ctx.lattice_f is None:
        ctx.lattice_f = f_rows
    phase = _fit_phase(ctx, jac, win, config)
    if phase is None:
        return None
    (u, v), conf = phase
    origin = (np.array([ctx.y0 + win.y, ctx.x0 + win.x], np.float64)
              + jac @ np.array([u, v]))
    meta.update({"phase_conf": conf, "phase_cells": (float(u), float(v))})
    pose = AffinePose(
        origin_yx=(float(origin[0]), float(origin[1])),
        jacobian_yx=((float(jac[0, 0]), float(jac[0, 1])),
                     (float(jac[1, 0]), float(jac[1, 1]))),
        angle_deg=angle,
        pitch_px=float(0.5 * (pitch_v + pitch_u)),
        phase_yx=(float(u), float(v)),
        footing_factor=1,
    )
    return pose, meta


def _fit_phase(
    ctx: RegionContext,
    jac: np.ndarray,
    win: Window,
    config: SearchConfig,
) -> tuple[tuple[float, float], float] | None:
    """Sub-cell grid phase: coarse cell-unit search + quadratic subpixel.

    The objective is the house blind statistic |cell mean - masked median|
    on a coarse cell subgrid, evaluated on the prefiltered image through the
    candidate pose (original pixels, no resample)."""
    p = ctx.pitch_prior
    n_cy, n_cx = win.h, win.w
    k = max(1, int(round(max(n_cy, n_cx) / 40)))
    gi, gj = np.meshgrid(np.arange(0, n_cy, k), np.arange(0, n_cx, k),
                         indexing="ij")
    grid = np.stack([gi.ravel(), gj.ravel()], axis=1).astype(np.float64)
    base = np.array([win.y, win.x], np.float64)
    # local median of the prefiltered image inside the window/mask
    wy1 = min(ctx.filt.shape[0], win.y + int(round(n_cy * p)))
    wx1 = min(ctx.filt.shape[1], win.x + int(round(n_cx * p)))
    sub = ctx.filt[win.y:wy1:4, win.x:wx1:4]
    subm = ctx.mask_f[win.y:wy1:4, win.x:wx1:4] > 0.5
    if not subm.any():
        return None
    mid = float(np.median(sub[subm]))
    step = config.phase_step_cells
    offsets = np.arange(0.5, 1.5 - 1e-9, step)
    scores = np.full((offsets.size, offsets.size), -np.inf)
    for a, u in enumerate(offsets):
        for b, v in enumerate(offsets):
            pts = (grid + np.array([u, v])) @ jac.T + base
            m = ndimage.map_coordinates(
                ctx.filt, pts.T, order=1, cval=ctx.backing)
            q = ndimage.map_coordinates(
                ctx.mask_f, pts.T, order=1, cval=0.0)
            sel = q > 0.9
            if int(sel.sum()) < 16:
                continue
            scores[a, b] = float(np.abs(m[sel] - mid).mean())
    ia, ib = np.unravel_index(int(np.argmax(scores)), scores.shape)
    if not np.isfinite(scores[ia, ib]):
        return None

    def _para(m1, m0, p1):
        d = m1 - 2 * m0 + p1
        return 0.0 if abs(d) < 1e-12 else float(
            np.clip(0.5 * (m1 - p1) / d, -0.5, 0.5))

    du = dv = 0.0
    if 0 < ia < offsets.size - 1 and np.isfinite(
            scores[ia - 1, ib]) and np.isfinite(scores[ia + 1, ib]):
        du = _para(scores[ia - 1, ib], scores[ia, ib], scores[ia + 1, ib])
    if 0 < ib < offsets.size - 1 and np.isfinite(
            scores[ia, ib - 1]) and np.isfinite(scores[ia, ib + 1]):
        dv = _para(scores[ia, ib - 1], scores[ia, ib], scores[ia, ib + 1])
    u = float(offsets[ia] + du * step)
    v = float(offsets[ib] + dv * step)
    return (u, v), float(scores[ia, ib])


# ---------------------------------------------------------------------------
# native window sampling
# ---------------------------------------------------------------------------

@dataclass
class SampledWindow:
    means: np.ndarray
    mask: np.ndarray          # coverage > 0.85 cells
    bits: np.ndarray
    evidence: np.ndarray      # bounded signed, bit0=+1 bit1=-1, 0 off-mask
    mid: float
    pose: AffinePose


def sample_window(
    ctx: RegionContext,
    pose: AffinePose,
    n_cy: int,
    n_cx: int,
) -> SampledWindow | None:
    """One subpixel read per cell centre through the pose (prefiltered)."""
    jac = pose.matrix()
    local = (np.asarray(pose.origin_yx, np.float64)
             - np.array([ctx.y0, ctx.x0], np.float64))
    gi, gj = np.meshgrid(np.arange(n_cy), np.arange(n_cx), indexing="ij")
    pts = (np.stack([gi.ravel(), gj.ravel()], axis=1).astype(np.float64)
           @ jac.T + local)
    means = ndimage.map_coordinates(
        ctx.filt, pts.T, order=1, cval=ctx.backing).reshape(n_cy, n_cx)
    cover = ndimage.map_coordinates(
        ctx.mask_f, pts.T, order=1, cval=0.0).reshape(n_cy, n_cx)
    cell_mask = cover > 0.85
    if not cell_mask.any():
        return None
    mid = float(np.median(means[cell_mask]))
    spread = max(float(np.abs(means[cell_mask] - mid).mean()), 1e-6)
    llr = np.clip((mid - means) / spread, -8.0, 8.0) * 2.0
    evidence = -np.tanh(llr / 2.0).astype(np.float32)
    evidence[~cell_mask] = 0.0
    return SampledWindow(
        means=means, mask=cell_mask,
        bits=(means < mid).astype(np.uint8),
        evidence=evidence, mid=mid, pose=pose,
    )


# ---------------------------------------------------------------------------
# scoring / placement primitives (parity-split throughout)
# ---------------------------------------------------------------------------

def _core(mask: np.ndarray, erode_cells: int) -> np.ndarray:
    if erode_cells <= 0:
        return np.asarray(mask, bool)
    out = ndimage.binary_erosion(mask, iterations=erode_cells)
    return out if out.any() else np.asarray(mask, bool)


def _box_sum(a: np.ndarray, h: int, w: int) -> np.ndarray:
    c = np.cumsum(np.cumsum(np.asarray(a, np.float64), axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return c[h:, w:] - c[:-h, w:] - c[h:, :-w] + c[:-h, :-w]


def _parity_mask(
    shape: tuple[int, int],
    origin_yx: tuple[int, int],
    parity: int,
) -> np.ndarray:
    """Checkerboard parity over a page-coordinate rectangle.

    The frozen split is ``(131*y + 17*x) & 1``.  Both coefficients are odd,
    so this is exactly ``(y + x) & 1``.  Build only the two coordinate
    vectors plus the boolean checkerboard; ``np.indices`` would materialize
    two full int64 page arrays.
    """
    h, w = shape
    y0, x0 = origin_yx
    rows = (np.arange(h, dtype=np.intp) + (y0 & 1)) & 1
    cols = (np.arange(w, dtype=np.intp) + (x0 & 1)) & 1
    return (rows[:, None] ^ cols[None, :]) == parity


def _split_mask(mask: np.ndarray, parity: int) -> np.ndarray:
    return np.asarray(mask, bool) & _parity_mask(mask.shape, (0, 0), parity)


def _score_known(
    evidence: np.ndarray,
    mask: np.ndarray,
    spec: ComposeSpec,
    seed: bytes,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
    *,
    parity: int | None = None,
) -> tuple[float, int, float]:
    values, sites = place.pilot_field(spec, seed, page)
    obs = np.rot90(np.asarray(evidence, np.float32), rot_k)
    keep = np.rot90(np.asarray(mask, bool), rot_k)
    sl = place.overlap_slices(origin_yx, obs.shape, values.shape)
    if sl is None:
        return 1.0, 0, -np.inf
    pys, pxs, fys, fxs = sl
    selected = sites[pys, pxs] & keep[fys, fxs]
    if parity is not None:
        # Local placement probes this function up to 50 times per anchor.
        # Splitting the full page here made a large-sheet anchor walk
        # quadratic in both work and allocation.  Parity is a page-coordinate
        # property, so the overlap rectangle is exactly sufficient.
        selected &= _parity_mask(
            selected.shape,
            (int(pys.start or 0), int(pxs.start or 0)),
            parity,
        )
    if not selected.any():
        return 1.0, 0, -np.inf
    expected = 1.0 - 2.0 * values[pys, pxs].astype(np.float32)
    weights = np.abs(obs[fys, fxs][selected])
    corr = float(np.sum(expected[selected] * obs[fys, fxs][selected]))
    total = float(weights.sum())
    mismatch = (total - corr) / (2.0 * total) if total > 0 else 1.0
    return float(mismatch), int(selected.sum()), corr / np.sqrt(max(total, 1e-9))


def correlate_fragment(
    evidence: np.ndarray,
    mask: np.ndarray,
    spec: ComposeSpec,
    seed: bytes,
    *,
    pages: Sequence[int],
    pending_cell_mask: dict[int, np.ndarray] | None,
    config: SearchConfig,
) -> place.Placement:
    """Soft pilot-field FFT search with disjoint validation sites."""
    obs0 = np.asarray(evidence, np.float32)
    mask0 = np.asarray(mask, bool)
    radius = place.EXCLUDE_RADIUS_CELLS
    tops: list[dict] = []
    n_hyp = 0
    for page_no in pages:
        values, all_sites = place.pilot_field(spec, seed, int(page_no))
        search_sites = _split_mask(all_sites, 0)
        expected = np.where(
            search_sites, 1.0 - 2.0 * values.astype(np.float32), 0.0
        ).astype(np.float32)
        for rot_k in range(4):
            obs = np.rot90(obs0, rot_k)
            keep = np.rot90(mask0, rot_k).astype(np.float32)
            ph = pw = 0
            exp_work, site_work = expected, search_sites
            if config.allow_overhang:
                ph, pw = obs.shape[0] - 1, obs.shape[1] - 1
                exp_work = np.pad(expected, ((ph, ph), (pw, pw)))
                site_work = np.pad(search_sites, ((ph, ph), (pw, pw)))
            elif (obs.shape[0] > expected.shape[0]
                  or obs.shape[1] > expected.shape[1]):
                continue
            weighted = obs * keep
            corr = fftconvolve(exp_work, weighted[::-1, ::-1], mode="valid")
            weight = fftconvolve(
                site_work.astype(np.float32),
                (np.abs(obs) * keep)[::-1, ::-1], mode="valid",
            )
            support = np.rint(fftconvolve(
                site_work.astype(np.float32), keep[::-1, ::-1], mode="valid",
            )).astype(np.int32)
            with np.errstate(divide="ignore", invalid="ignore"):
                mismatch = (weight - corr) / (2.0 * weight)
                z = corr / np.sqrt(weight)
            bad = (support < config.min_support) | (weight <= 0)
            if pending_cell_mask is not None:
                pending = pending_cell_mask.get(int(page_no))
                if pending is None:
                    bad[:] = True
                else:
                    pending_work = (np.pad(pending, ((ph, ph), (pw, pw)))
                                    if config.allow_overhang else pending)
                    bad |= _box_sum(pending_work, obs.shape[0], obs.shape[1]) <= 0
            z = np.where(bad, -np.inf, z)
            n_hyp += 1
            flat = int(np.argmax(z))
            iy, ix = np.unravel_index(flat, z.shape)
            if not np.isfinite(z[iy, ix]):
                continue
            top = {
                "page": int(page_no), "rot_k": rot_k,
                "origin": (int(iy) - ph, int(ix) - pw),
                "z": float(z[iy, ix]), "mismatch": float(mismatch[iy, ix]),
                "support": int(support[iy, ix]),
            }
            z[max(0, iy - radius):iy + radius + 1,
              max(0, ix - radius):ix + radius + 1] = -np.inf
            flat2 = int(np.argmax(z))
            iy2, ix2 = np.unravel_index(flat2, z.shape)
            if np.isfinite(z[iy2, ix2]):
                top["z2"] = float(z[iy2, ix2])
                top["mismatch2"] = float(mismatch[iy2, ix2])
            tops.append(top)
    if not tops:
        return place.Placement(ok=False, diagnostics={"reason": "no_candidates"})
    best = max(tops, key=lambda row: row["z"])
    rivals: list[tuple[float, float]] = []
    for row in tops:
        if row is best:
            if "z2" in row:
                rivals.append((row["z2"], row["mismatch2"]))
        else:
            rivals.append((row["z"], row["mismatch"]))
    rival_z, rival_mismatch = max(rivals, default=(-np.inf, 1.0))
    validation, validation_support, _ = _score_known(
        obs0, mask0, spec, seed, best["page"], best["origin"],
        best["rot_k"], parity=1,
    )
    gap = float(rival_mismatch - best["mismatch"])
    ok = (
        best["mismatch"] < config.gate_true
        and rival_mismatch > config.gate_decoy
        and gap >= config.gate_gap
        and validation < config.validation_true
        and validation_support >= config.min_support
    )
    return place.Placement(
        ok=bool(ok), page=best["page"], origin_yx=best["origin"],
        rot_k=best["rot_k"], mismatch=best["mismatch"],
        support=best["support"], z=best["z"],
        rival_mismatch=float(rival_mismatch), rival_z=float(rival_z),
        z_gap=float(best["z"] - rival_z),
        diagnostics={
            "n_hypotheses": n_hyp,
            "validation_mismatch": validation,
            "validation_support": validation_support,
            "mismatch_gap": gap,
            "rival_searched": True,
            "soft": True,
        },
    )


def try_bch_seed(
    bits: np.ndarray,
    evidence: np.ndarray,
    mask: np.ndarray,
    spec: ComposeSpec,
    seed: bytes,
    *,
    pages: Sequence[int],
    config: SearchConfig,
) -> tuple[place.Placement | None, int | None, float]:
    """Try high-quality complete BCH words; verify against the pilot field.

    The acceptance mismatch runs on SEARCH-parity sites and the disjoint
    VALIDATION-parity check must also pass (v1 scored all sites)."""
    start = perf_counter()
    if min(bits.shape, default=0) < spec.pilot.period_cells:
        return None, None, perf_counter() - start
    if float(np.mean(mask)) < config.bch_min_mask_fraction:
        return None, None, perf_counter() - start
    for rot_k in range(4):
        oriented_bits = np.rot90(bits, rot_k)
        oriented_mask = np.rot90(mask, rot_k)
        candidates = acquire.stage_a(
            oriented_bits, spec.pilot, seed,
            "K" if spec.n_levels > 1 else spec.plane,
            max_errors=config.bch_max_errors,
            max_tiles=config.bch_max_tiles,
            page_tiles_yx=spec.page_tiles_yx,
        )
        positions = pilots.site_positions_tile(spec.pilot, seed)
        for candidate in candidates:
            wy, wx = candidate["tile_window_origin"]
            visible = oriented_mask[wy + positions[:, 0], wx + positions[:, 1]]
            if int(visible.sum()) < 90:
                continue
            message = candidate["message"]
            page_no = int(message["page"])
            if page_no not in pages:
                continue
            period = spec.pilot.period_cells
            origin = (
                int(message["ptile_y"] * period - wy),
                int(message["ptile_x"] * period - wx),
            )
            mismatch, support, z = _score_known(
                evidence, mask, spec, seed, page_no, origin, rot_k,
                parity=0,
            )
            validation, validation_support, _ = _score_known(
                evidence, mask, spec, seed, page_no, origin, rot_k, parity=1,
            )
            if (mismatch < config.gate_true
                    and support >= config.min_support
                    and validation < config.validation_true
                    and validation_support >= config.min_support):
                elapsed = perf_counter() - start
                return place.Placement(
                    ok=True, page=page_no, origin_yx=origin, rot_k=rot_k,
                    mismatch=mismatch, support=support, z=z,
                    rival_mismatch=1.0, rival_z=-np.inf, z_gap=np.inf,
                    diagnostics={
                        "validation_mismatch": validation,
                        "validation_support": validation_support,
                        "rival_searched": False,
                        "bch_seed": True,
                    },
                ), int(candidate["n_err"]), elapsed
    return None, None, perf_counter() - start


# ---------------------------------------------------------------------------
# pose propagation (full affine, rot90-aware)
# ---------------------------------------------------------------------------

def _rot_affine(rot_k: int, shape: tuple[int, int]
                ) -> tuple[np.ndarray, np.ndarray]:
    """page = S @ q + t for a frame of `shape` under np.rot90 by rot_k
    (matches _rotated_points exactly; pinned by tests)."""
    h, w = shape
    if rot_k == 0:
        return np.eye(2), np.zeros(2)
    if rot_k == 1:
        return np.array([[0.0, -1.0], [1.0, 0.0]]), np.array([w - 1.0, 0.0])
    if rot_k == 2:
        return -np.eye(2), np.array([h - 1.0, w - 1.0])
    return np.array([[0.0, 1.0], [-1.0, 0.0]]), np.array([0.0, h - 1.0])


def _rotated_points(points: np.ndarray, shape: tuple[int, int], rot_k: int
                    ) -> np.ndarray:
    y, x = points[:, 0], points[:, 1]
    h, w = shape
    if rot_k == 0:
        return np.stack([y, x], axis=1)
    if rot_k == 1:
        return np.stack([w - 1 - x, y], axis=1)
    if rot_k == 2:
        return np.stack([h - 1 - y, w - 1 - x], axis=1)
    return np.stack([x, h - 1 - y], axis=1)


def predict_from_anchor(
    anchor: PlacedWindow,
    pose_w: AffinePose,
    shape_w_cells: tuple[int, int],
) -> tuple[int, int]:
    """Predicted page origin of a window from an accepted anchor's full pose.

    The window's own fitted origin is transported through the anchor's
    Jacobian into anchor cell offsets, then through the anchor's rot90
    placement into page coordinates."""
    jac_a = anchor.pose.matrix()
    d_px = (np.asarray(pose_w.origin_yx, np.float64)
            - np.asarray(anchor.pose.origin_yx, np.float64))
    d_cells = np.linalg.solve(jac_a, d_px)
    s, t_a = _rot_affine(anchor.rot_k, (anchor.window.h, anchor.window.w))
    _, t_w = _rot_affine(anchor.rot_k, shape_w_cells)
    o_w = (s @ d_cells + t_a - t_w
           + np.asarray(anchor.origin_yx, np.float64))
    return int(round(o_w[0])), int(round(o_w[1]))


def _rank_lower_hints(
    lower_hints: Sequence[PlacedWindow],
    pose_w: AffinePose,
    *,
    limit: int = LOWER_HINT_LIMIT,
    runner_up_reserve: int = LOWER_RUNNER_UP_RESERVE,
) -> list[tuple[int, PlacedWindow]]:
    """Return a bounded continuation portfolio for one current window.

    Accepted lower-scale placements remain ahead of losing hypotheses, but a
    small tail is reserved for the nearest retained runners.  Without that
    reservation a normal page's many accepted placements globally truncated
    every runner before it could be tested.  Unused accepted or runner slots
    fill one another, so sparse hint inventories do not waste the bound.
    """
    bound = max(0, int(limit))
    reserve = max(0, int(runner_up_reserve))
    if bound == 0:
        return []

    target = np.asarray(pose_w.origin_yx, np.float64)
    ranked = sorted(
        enumerate(lower_hints),
        key=lambda item: (
            float(np.linalg.norm(
                np.asarray(item[1].pose.origin_yx, np.float64) - target)),
            int(item[1].page), int(item[1].rot_k), item[0],
        ),
    )
    accepted = [row for row in ranked
                if row[1].method != "lower_runner_up"]
    runners = [row for row in ranked
               if row[1].method == "lower_runner_up"]

    n_runners = min(len(runners), reserve, bound)
    n_accepted = min(len(accepted), bound - n_runners)
    chosen = accepted[:n_accepted] + runners[:n_runners]
    remaining = bound - len(chosen)
    if remaining:
        extra_accepted = accepted[n_accepted:n_accepted + remaining]
        chosen.extend(extra_accepted)
        remaining -= len(extra_accepted)
    if remaining:
        chosen.extend(runners[n_runners:n_runners + remaining])
    return chosen


def place_by_prediction(
    evidence: np.ndarray,
    mask: np.ndarray,
    spec: ComposeSpec,
    seed: bytes,
    page: int,
    rot_k: int,
    predicted: tuple[int, int],
    config: SearchConfig,
) -> place.Placement | None:
    """Bounded local placement around a pose-propagated prediction.

    The argmax runs on SEARCH-parity sites only; acceptance additionally
    needs the disjoint VALIDATION-parity sites (v1 argmaxed on all sites and
    then 'validated' on a subset of them — the split was violated)."""
    best = None
    r = config.neighbor_radius_cells
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            origin = (predicted[0] + dy, predicted[1] + dx)
            mismatch, support, z = _score_known(
                evidence, mask, spec, seed, page, origin, rot_k, parity=0,
            )
            if best is None or z > best[0]:
                best = (z, mismatch, support, origin)
    if best is None:
        return None
    z, mismatch, support, origin = best
    validation, validation_support, _ = _score_known(
        evidence, mask, spec, seed, page, origin, rot_k, parity=1,
    )
    residual = float(max(abs(origin[0] - predicted[0]),
                         abs(origin[1] - predicted[1])))
    if (mismatch >= config.gate_true
            or validation >= config.validation_true
            or support < config.min_support
            or validation_support < config.min_support
            or residual > config.consistency_cells):
        return None
    return place.Placement(
        ok=True, page=page, origin_yx=origin, rot_k=rot_k,
        mismatch=mismatch, support=support, z=z,
        rival_mismatch=1.0, rival_z=-np.inf, z_gap=np.inf,
        diagnostics={
            "validation_mismatch": validation,
            "validation_support": validation_support,
            "predicted_origin": tuple(int(v) for v in predicted),
            "predicted_residual_cells": residual,
            "rival_searched": False,
            "chained": True,
        },
    )


# ---------------------------------------------------------------------------
# post-placement pose refinement (search-parity train, validation-parity gate)
# ---------------------------------------------------------------------------

def refine_pose(
    ctx: RegionContext,
    sampled: SampledWindow,
    placement: place.Placement,
    spec: ComposeSpec,
    seed: bytes,
    config: SearchConfig,
) -> tuple[AffinePose, dict] | None:
    """Subpixel (angle, phase) refinement on expected pilot labels.

    Objective = mean signed margin on SEARCH-parity sites (train); the
    refinement is kept only if the disjoint VALIDATION-parity hard mismatch
    does not degrade. Never a BCH objective."""
    pl = place.Placement(ok=True, page=placement.page,
                         origin_yx=placement.origin_yx,
                         rot_k=placement.rot_k)
    sites_ij, expected = place.fragment_pilot_sites(
        pl, sampled.bits.shape, sampled.mask, spec, seed)
    if sites_ij.shape[0] < 2 * config.min_support:
        return None
    # absolute page coords -> the SAME parity classes the placer used
    rotated = _rotated_points(sites_ij, sampled.bits.shape, placement.rot_k)
    page_yx = rotated + np.asarray(placement.origin_yx, np.int64)
    parity = ((page_yx[:, 0] * 131 + page_yx[:, 1] * 17) & 1).astype(bool)
    train = ~parity        # parity 0 = search set
    heldout = parity
    if int(train.sum()) < 20 or int(heldout.sum()) < 20:
        return None
    jac0 = sampled.pose.matrix()
    local0 = (np.asarray(sampled.pose.origin_yx, np.float64)
              - np.array([ctx.y0, ctx.x0], np.float64))
    sgn = 1.0 - 2.0 * expected.astype(np.float64)   # +1 paper, -1 ink
    mid = sampled.mid
    q = sites_ij.astype(np.float64)

    def _eval(dth_deg: float, du: float, dv: float
              ) -> tuple[float, float]:
        a = np.deg2rad(dth_deg)
        rot = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
        jac = rot @ jac0
        base = local0 + jac0 @ np.array([du, dv])
        pts = q @ jac.T + base
        m = ndimage.map_coordinates(
            ctx.filt, pts.T, order=1, cval=ctx.backing)
        margin = float(np.mean((mid - m[train]) * -sgn[train]))
        mis_ho = float(np.mean((m[heldout] < mid)
                               != (expected[heldout] > 0)))
        return margin, mis_ho

    _, base_ho = _eval(0.0, 0.0, 0.0)
    best = (None, 0.0, 0.0, 0.0, base_ho)
    for dth in np.arange(-config.refine_angle_deg,
                         config.refine_angle_deg + 1e-9,
                         config.refine_angle_step_deg):
        for du in np.arange(-config.refine_phase_cells,
                            config.refine_phase_cells + 1e-9,
                            config.refine_phase_step_cells):
            for dv in np.arange(-config.refine_phase_cells,
                                config.refine_phase_cells + 1e-9,
                                config.refine_phase_step_cells):
                margin, mis_ho = _eval(float(dth), float(du), float(dv))
                if best[0] is None or margin > best[0]:
                    best = (margin, float(dth), float(du), float(dv), mis_ho)
    _, dth, du, dv, mis_ho = best
    if mis_ho > base_ho + 0.005:      # held-out must not degrade
        return None
    a = np.deg2rad(dth)
    rot = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    jac = rot @ jac0
    origin = (np.asarray(sampled.pose.origin_yx, np.float64)
              + jac0 @ np.array([du, dv]))
    pitch_v, pitch_u, angle, _ = _pose_metrics(jac)
    pose = AffinePose(
        origin_yx=(float(origin[0]), float(origin[1])),
        jacobian_yx=((float(jac[0, 0]), float(jac[0, 1])),
                     (float(jac[1, 0]), float(jac[1, 1]))),
        angle_deg=angle,
        pitch_px=float(0.5 * (pitch_v + pitch_u)),
        phase_yx=sampled.pose.phase_yx,
        footing_factor=1,
    )
    return pose, {"refine_dtheta_deg": dth, "refine_du_cells": du,
                  "refine_dv_cells": dv, "heldout_pre": base_ho,
                  "heldout_post": mis_ho}


# ---------------------------------------------------------------------------
# per-block placement audit (the y-step / fold emission-poison class)
# ---------------------------------------------------------------------------

def audit_blocks(
    sampled: SampledWindow,
    core: np.ndarray,
    placement: place.Placement,
    spec: ComposeSpec,
    seed: bytes,
    config: SearchConfig,
) -> tuple[np.ndarray, dict]:
    """Strip window strips whose sites contradict the placed address.

    A window straddling a scanner y-step or fold carries ONE self-consistent
    lattice (an integer-cell jump preserves the sub-cell phase) but two page
    mappings; placement locks the majority side and the minority side's
    sites read ~50% against the placed address. A per-axis change-point on
    the site wrong-rate profile finds the cut: one side must read above
    audit_bad, the other below audit_good, and the bad side is removed from
    the emission core. A window whose residual wrong rate stays above the
    post bar is refused (subdivided windows recover each side)."""
    pl = place.Placement(ok=True, page=placement.page,
                         origin_yx=placement.origin_yx,
                         rot_k=placement.rot_k)
    sites_ij, expected = place.fragment_pilot_sites(
        pl, sampled.bits.shape, core, spec, seed)
    stats: dict = {"n_sites": int(sites_ij.shape[0]), "strips": [],
                   "refused": False}
    if sites_ij.shape[0] < 2 * config.audit_min_sites:
        return core, stats
    bits = sampled.bits[sites_ij[:, 0], sites_ij[:, 1]]
    wrong = (bits != expected).astype(np.float64)
    good = np.asarray(core, bool).copy()
    keep = np.ones(sites_ij.shape[0], bool)
    # up to two strips per axis (a bad MIDDLE band needs two cuts). The
    # split criterion is minimum binomial impurity — a max rate-difference
    # criterion measurably preferred a tail cut that left 14.5% poison in
    # the kept side (the y-step fixture caught it).
    for axis in (0, 1, 0, 1):
        idx = np.flatnonzero(keep)
        if idx.size < 2 * config.audit_min_sites:
            break
        coords = sites_ij[idx, axis]
        order = np.argsort(coords, kind="stable")
        cs = coords[order]
        ws = wrong[idx][order]
        n = cs.size
        cum = np.concatenate([[0.0], np.cumsum(ws)])
        best = None
        for split in range(config.audit_min_sites,
                           n - config.audit_min_sites):
            if cs[split] == cs[split - 1]:
                continue
            lo = cum[split] / split
            hi = (cum[n] - cum[split]) / (n - split)
            cost = (split * lo * (1.0 - lo)
                    + (n - split) * hi * (1.0 - hi))
            if best is None or cost < best[0]:
                cut = 0.5 * (cs[split - 1] + cs[split])
                best = (cost, lo, hi, float(cut))
        if best is None:
            continue
        _, lo, hi, cut = best
        bad_lo = lo > hi
        bad, ok_rate = (lo, hi) if bad_lo else (hi, lo)
        if not (bad > config.audit_bad and ok_rate < config.audit_good):
            continue
        edge = int(np.ceil(cut))
        if axis == 0:
            if bad_lo:
                good[:edge, :] = False
            else:
                good[edge:, :] = False
        else:
            if bad_lo:
                good[:, :edge] = False
            else:
                good[:, edge:] = False
        stats["strips"].append(
            {"axis": int(axis), "cut_cells": float(cut),
             "bad_low_side": bool(bad_lo), "bad_rate": float(bad),
             "kept_rate": float(ok_rate)})
        keep &= good[sites_ij[:, 0], sites_ij[:, 1]]
    kept = int(keep.sum())
    residual = float(wrong[keep].mean()) if kept else 1.0
    stats["kept_sites"] = kept
    stats["residual_wrong"] = residual
    if kept < config.min_support or residual > config.audit_post_bar:
        stats["refused"] = True
    return good, stats


# ---------------------------------------------------------------------------
# observation emission + known-position words
# ---------------------------------------------------------------------------

def _add_placement_observations(
    result: SearchResult,
    ctx: RegionContext,
    sampled: SampledWindow,
    placed: PlacedWindow,
    core: np.ndarray,
    spec: ComposeSpec,
    seed: bytes,
    config: SearchConfig,
) -> set[tuple[int, int, int]]:
    """Emit pilot observations under the ERODED, block-audited core mask
    (016.7 rim + the straddle audit)."""
    pl = place.Placement(
        ok=True, page=placed.page, origin_yx=placed.origin_yx,
        rot_k=placed.rot_k,
    )
    sites_local, expected = place.fragment_pilot_sites(
        pl, sampled.bits.shape, core, spec, seed
    )
    if not sites_local.size:
        return set()
    rotated = _rotated_points(sites_local, sampled.bits.shape, placed.rot_k)
    absolute = rotated + np.asarray(placed.origin_yx, np.int64)
    scan_points = placed.pose.points(sites_local)
    positions = pilots.site_positions_tile(spec.pilot, seed)
    position_index = {tuple(p): i for i, p in enumerate(positions.tolist())}
    period = spec.pilot.period_cells
    touched: set[tuple[int, int, int]] = set()
    for idx, (absolute_yx, local_yx) in enumerate(zip(absolute, sites_local)):
        ay, ax = int(absolute_yx[0]), int(absolute_yx[1])
        if not (0 <= ay < spec.page_cells_yx[0]
                and 0 <= ax < spec.page_cells_yx[1]):
            continue
        tile_y, site_y = divmod(ay, period)
        tile_x, site_x = divmod(ax, period)
        site_index = position_index.get((site_y, site_x))
        if site_index is None:
            continue
        key = (placed.page, tile_y, tile_x)
        tile = result.tiles.get(key)
        if tile is None:
            expected_word = pilots.expected_word_bits(
                spec.pilot, seed,
                "K" if spec.n_levels > 1 else spec.plane,
                placed.page, tile_y, tile_x, **spec.word_geometry,
            )
            tile = PilotTileEvidence(
                placed.page, tile_y, tile_x, expected_word
            )
            result.tiles[key] = tile
        iy, ix = int(local_yx[0]), int(local_yx[1])
        obs = PilotObservation(
            region_index=placed.region_index,
            window_yx=(placed.window.y, placed.window.x),
            scan_yx=(float(scan_points[idx, 0]), float(scan_points[idx, 1])),
            bit=int(sampled.bits[iy, ix]),
            expected=int(expected[idx]),
            weight=float(abs(sampled.evidence[iy, ix])),
            method=placed.method, scan_id=placed.scan_id,
        )
        tile.observations.setdefault(site_index, []).append(obs)
        touched.add(key)
    return touched


def decode_known_tiles(
    result: SearchResult,
    spec: ComposeSpec,
    seed: bytes,
) -> None:
    """Known-position BCH errors/erasures reads on aggregated tile evidence.

    Same-scan observations of one site are correlated (overlapping windows
    read the same pixels) — only the highest-weight observation per scan
    votes; independent scans combine by weighted vote."""
    plane = "K" if spec.n_levels > 1 else spec.plane
    for key, tile in result.tiles.items():
        bits = np.zeros(100, np.uint8)
        known: list[int] = []
        for site_index, observations in tile.observations.items():
            per_scan: dict[str, PilotObservation] = {}
            for obs in observations:
                cur = per_scan.get(obs.scan_id)
                if cur is None or obs.weight > cur.weight:
                    per_scan[obs.scan_id] = obs
            vote = sum((1.0 if obs.bit else -1.0) * max(obs.weight, 1e-3)
                       for obs in per_scan.values())
            bits[site_index] = np.uint8(vote >= 0)
            known.append(site_index)
        erasures = np.setdiff1d(np.arange(100), np.asarray(known, np.int64))
        tile.bch_erasures = int(erasures.size)
        if erasures.size > 26:
            tile.bch_ok = None
            continue
        # full decoder strength: decode_erasures gates 2e + f <= 2*t_full
        # internally. (v1/v2 passed (26-f)//2 here, which decode_erasures
        # reads as REDUCED strength and refuses whenever f > 2*max_errors —
        # clean words with >6 erasures could never decode; caught by the
        # cross-scrap fill fixture.)
        max_errors = pilots.code_for_layout(spec.pilot).t_full
        tile.bch_attempted = True
        start = perf_counter()
        decoded = pilots.decode_word(
            bits, spec.pilot, seed, plane, max_errors,
            erasures=erasures, **spec.word_geometry,
        )
        tile.bch_elapsed_s = perf_counter() - start
        if decoded is None:
            tile.bch_ok = None
            tile.bch_refused = True
            tile.bch_errors = None
        else:
            tile.bch_ok = bool(
                int(decoded["page"]) == key[0]
                and int(decoded["ptile_y"]) == key[1]
                and int(decoded["ptile_x"]) == key[2]
            )
            tile.bch_errors = int(decoded["n_errors"])


def _pending_masks(
    spec: ComposeSpec, pages: Sequence[int], seed: bytes,
    result: SearchResult,
) -> dict[int, np.ndarray]:
    """True at pilot SITES with no observation yet — SITE granular.

    Tile granularity (v2's first form: a tile with >=20 observed sites left
    the need mask wholesale) rejected a later scrap whose only contribution
    was the SAME tile's unobserved half — exactly the cross-scrap
    resurrection the design promises. Pending is therefore per site: a
    second scrap covering the other half of a partially observed pilot
    tile always adds needed support."""
    positions = pilots.site_positions_tile(spec.pilot, seed)
    period = spec.pilot.period_cells
    out: dict[int, np.ndarray] = {}
    for page in pages:
        _, sites = place.pilot_field(spec, seed, int(page))
        out[int(page)] = sites.copy()
    for (page_no, tile_y, tile_x), tile in result.tiles.items():
        pending = out.get(int(page_no))
        if pending is None:
            continue
        for site_index in tile.observations:
            sy, sx = positions[site_index]
            pending[tile_y * period + int(sy),
                    tile_x * period + int(sx)] = False
    return out


def _adds_needed_support(
    mask: np.ndarray,
    placement: place.Placement,
    pending: dict[int, np.ndarray],
) -> bool:
    """True iff the placement covers at least one unobserved pilot site."""
    page_pending = pending.get(int(placement.page))
    if page_pending is None:
        return False
    rotated = np.rot90(np.asarray(mask, bool), int(placement.rot_k))
    slices = place.overlap_slices(
        placement.origin_yx, rotated.shape, page_pending.shape
    )
    if slices is None:
        return False
    pys, pxs, fys, fxs = slices
    return bool(np.any(page_pending[pys, pxs] & rotated[fys, fxs]))


# ---------------------------------------------------------------------------
# window layout + the per-region search loop
# ---------------------------------------------------------------------------

def _layout_windows(ctx: RegionContext, config: SearchConfig) -> list[Window]:
    p = ctx.pitch_prior
    hh, ww = ctx.crop.shape
    win_px = int(round(config.window_cells * p))
    step_px = max(1, int(round((config.window_cells - config.overlap_cells) * p)))

    def _starts(n: int) -> list[int]:
        if n <= win_px:
            return [0]
        out = list(range(0, n - win_px + 1, step_px))
        if out[-1] != n - win_px:
            out.append(n - win_px)
        return out

    # support estimate on a 4x-subsampled mask (a 4800-dpi region's full
    # integral image would be ~0.6 GB float64 for nothing)
    sub = 4
    m4 = ctx.mask_f[::sub, ::sub] > 0.5
    ii = np.pad(np.cumsum(np.cumsum(m4, axis=0), axis=1).astype(np.float64),
                ((1, 0), (1, 0)))

    def _cells_in(y0: int, x0: int, y1: int, x1: int) -> int:
        a, b = y0 // sub, x0 // sub
        c, d = min(m4.shape[0], y1 // sub), min(m4.shape[1], x1 // sub)
        if c <= a or d <= b:
            return 0
        px_in = float(ii[c, d] - ii[a, d] - ii[c, b] + ii[a, b]) * sub * sub
        return int(px_in / (p * p))

    windows: list[Window] = []
    for y in _starts(hh):
        for x in _starts(ww):
            n_cy = min(config.window_cells, int((hh - y) / p))
            n_cx = min(config.window_cells, int((ww - x) / p))
            if n_cy < 8 or n_cx < 8:
                continue
            y1 = min(hh, y + int(round(n_cy * p)))
            x1 = min(ww, x + int(round(n_cx * p)))
            support = _cells_in(y, x, y1, x1)
            if support >= config.min_support:
                windows.append(Window(y, x, n_cy, n_cx, support))
    windows.sort(key=lambda win: (-win.support, win.y, win.x))
    return windows


def _subdivide(win: Window, ctx: RegionContext, config: SearchConfig
               ) -> list[Window]:
    if not config.subdivide or win.depth >= 1:
        return []
    half = max(config.min_window_cells, min(win.h, win.w) // 2)
    if half < config.min_window_cells or half >= min(win.h, win.w):
        return []
    p = ctx.pitch_prior
    out = []
    for oy in (0, win.h - half):
        for ox in (0, win.w - half):
            out.append(Window(
                y=win.y + int(round(oy * p)), x=win.x + int(round(ox * p)),
                h=half, w=half, support=0, depth=win.depth + 1,
            ))
    return out


def search_survey(
    image: np.ndarray,
    survey: PayloadSurvey,
    descriptor: FormatDescriptor,
    *,
    pages: Sequence[int] = (0,),
    config: SearchConfig = SearchConfig(),
    scan_id: str = "",
    pitch_px_prior: float | None = None,
    scan_dpi: float | None = None,
    lower_hints: Sequence[PlacedWindow] = (),
    on_window: Callable[[SearchResult, WindowProgress], None] | None = None,
    on_region: Callable[[SearchResult, int], None] | None = None,
) -> SearchResult:
    """Run E022 largest-region-first on one complete format hypothesis.

    Pitch prior chain (the section-2 contract): the survey's measured
    pitch; else an explicit pitch_px_prior; else the descriptor's physical
    pitch through a trusted scan_dpi (scan_dpi * cell_dots / 600 on the
    frozen print grid). Each window's spectral fit re-measures the local
    pitch either way — the prior only centres the search band, and the
    pitch_tol consistency gate rejects a wrong prior honestly.

    ``lower_hints`` is deliberately a placement-route hint, not inherited
    evidence.  Its pose must already be expressed in this raster's pixel
    coordinates.  Hints only predict a bounded page origin; this level's
    freshly fitted pose, freshly sampled pixels, and normal pilot gates make
    the decision.  With the default empty sequence E022 is byte-for-byte the
    standalone algorithm.
    """
    pitch = survey.cell_pitch_px
    prior_source = "survey"
    if pitch is None and pitch_px_prior is not None:
        pitch = pitch_px_prior
        prior_source = "explicit"
    if pitch is None and scan_dpi is not None:
        pitch = scan_dpi * descriptor.cell_dots / 600.0
        prior_source = "descriptor"
    if pitch is None:
        raise ValueError(
            "E022 needs E021 cell_pitch_px, a pitch_px_prior, or scan_dpi "
            "for the descriptor pitch prior")
    if survey.c_dots is not None and survey.c_dots != descriptor.cell_dots:
        raise ValueError(
            f"survey c{survey.c_dots} does not match {descriptor.format_id} "
            f"c{descriptor.cell_dots}"
        )
    spec = descriptor.spec()
    seed = descriptor.seed
    result = SearchResult()
    found: set[tuple[int, int, int]] = set()
    audit: dict[int, list[dict]] = {}
    backing = platen_backing(image)
    order = sorted(range(len(survey.regions)),
                   key=lambda idx: -survey.regions[idx].area_mm2)
    result.diagnostics["region_order"] = order
    total_start = perf_counter()
    observer_s = 0.0

    def notify_region(region_index: int) -> None:
        nonlocal observer_s
        if on_region is None:
            return
        started = perf_counter()
        try:
            on_region(result, region_index)
        finally:
            observer_s += perf_counter() - started

    for region_index in order:
        region = survey.regions[region_index]
        ctx = prepare_region(
            image, region, region_index, float(pitch),
            config=config, backing=backing,
        )
        rows: list[dict] = []
        audit[region_index] = rows
        if ctx is None:
            result.region_states[region_index] = "pose_refused"
            notify_region(region_index)
            continue
        anchors: list[PlacedWindow] = []
        accepted = 0
        n_components = 0
        queue = list(_layout_windows(ctx, config))
        qi = 0
        while qi < len(queue):
            win = queue[qi]
            qi += 1
            row: dict = {"window": [win.y, win.x, win.h, win.w],
                         "depth": win.depth}
            rows.append(row)
            t_win = perf_counter()
            window_observer_s = 0.0
            pose = None
            pose_meta: dict = {}
            placement = None
            method = ""
            routes: list[str] = []

            def notify_window(stage: str) -> None:
                nonlocal observer_s, window_observer_s
                if on_window is None:
                    return
                started = perf_counter()
                try:
                    bbox_h = max(0.0, min(
                        float(ctx.crop.shape[0] - win.y),
                        float(win.h) * float(ctx.pitch_prior)))
                    bbox_w = max(0.0, min(
                        float(ctx.crop.shape[1] - win.x),
                        float(win.w) * float(ctx.pitch_prior)))
                    page = None if placement is None else placement.page
                    origin = (
                        None if placement is None else placement.origin_yx)
                    rot_k = None if placement is None else placement.rot_k
                    mismatch = (
                        None if placement is None else placement.mismatch)
                    validation = None
                    support = (
                        None if placement is None else placement.support)
                    if placement is not None:
                        validation = placement.diagnostics.get(
                            "validation_mismatch")
                    snapshot = WindowProgress(
                        region_index=int(region_index), ordinal=int(qi),
                        queue_total=int(len(queue)),
                        queue_remaining=int(len(queue) - qi),
                        depth=int(win.depth), stage=str(stage),
                        outcome=row.get("outcome"),
                        window_origin_yx_px=(int(win.y), int(win.x)),
                        window_shape_yx_cells=(int(win.h), int(win.w)),
                        scan_bbox_yxhw_px=(
                            float(ctx.y0 + win.y),
                            float(ctx.x0 + win.x), bbox_h, bbox_w),
                        anchors=len(anchors),
                        placements=len(result.placements),
                        accepted=int(accepted),
                        attempted_routes=tuple(routes),
                        method=(str(method) if method else None),
                        pose_origin_yx=(
                            None if pose is None else
                            tuple(float(v) for v in pose.origin_yx)),
                        jacobian_yx=(None if pose is None else tuple(
                            tuple(float(v) for v in values)
                            for values in pose.jacobian_yx)),
                        angle_deg=(None if pose is None else
                                   float(pose.angle_deg)),
                        pitch_px=(None if pose is None else
                                  float(pose.pitch_px)),
                        pitch_v_px=_observer_float(
                            pose_meta.get("pitch_v_px")),
                        pitch_u_px=_observer_float(
                            pose_meta.get("pitch_u_px")),
                        ortho_dev_deg=_observer_float(
                            pose_meta.get("ortho_dev_deg")),
                        phase_conf=_observer_float(
                            pose_meta.get("phase_conf")),
                        phase_yx=(None if pose is None else
                                  tuple(float(v) for v in pose.phase_yx)),
                        placement_page=(
                            None if page is None else int(page)),
                        placement_origin_yx=(
                            None if origin is None else
                            tuple(int(v) for v in origin)),
                        placement_rot_k=(
                            None if rot_k is None else int(rot_k)),
                        mismatch=_observer_float(mismatch),
                        validation_mismatch=_observer_float(validation),
                        support=(
                            None if support is None else int(support)),
                        elapsed_s=max(
                            0.0, started - t_win - window_observer_s),
                    )
                    on_window(result, snapshot)
                finally:
                    elapsed = perf_counter() - started
                    observer_s += elapsed
                    window_observer_s += elapsed

            notify_window("window_open")
            got = fit_window_pose(ctx, win, config=config)
            if got is None:
                row["outcome"] = "pose_refused"
                queue.extend(_subdivide(win, ctx, config))
                notify_window("window_complete")
                continue
            pose, pose_meta = got
            row["pose"] = {k: v for k, v in pose_meta.items()
                           if not isinstance(v, np.ndarray)}
            # Retain the fitted physical pose even when address placement is
            # refused.  E023c may carry at most a bounded set of these losing
            # address hypotheses to a finer raster, where they are sampled
            # afresh and must pass the normal local gates.  This is an audit
            # sidecar only; standalone E022 never consumes it.
            row["pose_field"] = {
                "origin_yx": tuple(float(v) for v in pose.origin_yx),
                "jacobian_yx": tuple(
                    tuple(float(v) for v in values)
                    for values in pose.jacobian_yx),
                "angle_deg": float(pose.angle_deg),
                "pitch_px": float(pose.pitch_px),
                "phase_yx": tuple(float(v) for v in pose.phase_yx),
            }
            notify_window("pose_fitted")
            sampled = sample_window(ctx, pose, win.h, win.w)
            if sampled is None or int(sampled.mask.sum()) < config.min_support:
                row["outcome"] = "insufficient_support"
                notify_window("window_complete")
                continue
            core = _core(sampled.mask, config.erode_cells)
            pending = _pending_masks(spec, pages, seed, result)
            bch_errors = None
            component = None
            residual = None
            # 1) pose-propagated local placement from existing anchors
            if anchors:
                routes.append("chain")
                notify_window("chain")
                t0 = perf_counter()
                for a_idx, anchor in enumerate(anchors):
                    predicted = predict_from_anchor(
                        anchor, pose, (win.h, win.w))
                    placement = place_by_prediction(
                        sampled.evidence, core, spec, seed,
                        anchor.page, anchor.rot_k, predicted, config,
                    )
                    if placement is not None:
                        method = "chain"
                        component = anchor.component
                        residual = placement.diagnostics.get(
                            "predicted_residual_cells")
                        break
                result.timings["chain_s"] = (
                    result.timings.get("chain_s", 0.0)
                    + perf_counter() - t0)
            # 2) E023c lower-scale continuation.  Rank by physical
            # proximity so a large page inventory remains bounded.  A hint
            # never supplies bits, a pose, or an acceptance result: it only
            # supplies the page/orientation and predicted page origin used by
            # the same local gate as an ordinary neighbour.
            if placement is None and lower_hints:
                routes.append("lower_hints")
                notify_window("lower_hints")
                t0 = perf_counter()
                ranked_hints = _rank_lower_hints(lower_hints, pose)
                for hint_rank, (hint_index, hint) in enumerate(ranked_hints):
                    if int(hint.page) not in pages:
                        continue
                    predicted = predict_from_anchor(
                        hint, pose, (win.h, win.w))
                    placement = place_by_prediction(
                        sampled.evidence, core, spec, seed,
                        hint.page, hint.rot_k, predicted, config,
                    )
                    if placement is not None:
                        method = "lower_chain"
                        residual = placement.diagnostics.get(
                            "predicted_residual_cells")
                        placement.diagnostics.update({
                            "lower_hint_index": int(hint_index),
                            "lower_hint_rank": int(hint_rank),
                            "lower_hint_scan_id": str(hint.scan_id),
                            "lower_hint_method": str(hint.method),
                        })
                        break
                result.timings["lower_hint_s"] = (
                    result.timings.get("lower_hint_s", 0.0)
                    + perf_counter() - t0)
            # 3) BCH short-circuit on mask-dense complete-word windows
            if placement is None and config.bch_first:
                routes.append("bch")
                notify_window("bch")
                placement, bch_errors, elapsed = try_bch_seed(
                    sampled.bits, sampled.evidence, core, spec, seed,
                    pages=pages, config=config,
                )
                result.timings["bch_seed_s"] = (
                    result.timings.get("bch_seed_s", 0.0) + elapsed)
                if placement is not None:
                    method = "bch_seed"
            # 4) full-page correlation (also the re-anchor path). The
            # search is NOT pending-pruned: a fully-covered duplicate must
            # place and be recorded as redundant_skipped (audit trail),
            # not fail as "no candidates"; the un-pruned rival set is
            # strictly larger = refusal-biased.
            if placement is None:
                routes.append("correlation")
                notify_window("correlation")
                t0 = perf_counter()
                placement = correlate_fragment(
                    sampled.evidence, core, spec, seed, pages=pages,
                    pending_cell_mask=None, config=config,
                )
                result.timings["correlation_s"] = (
                    result.timings.get("correlation_s", 0.0)
                    + perf_counter() - t0)
                method = "correlation"
            if not placement.ok:
                # retry ledger: an E023-directed revisit needs the losing
                # hypothesis, not just "unresolved"
                row["outcome"] = "unresolved"
                row["mismatch"] = float(placement.mismatch)
                row["reason"] = placement.diagnostics.get("reason", "gates")
                if placement.page is not None:
                    row["best_candidate"] = {
                        "page": int(placement.page),
                        "origin_yx": list(placement.origin_yx),
                        "rot_k": int(placement.rot_k),
                        "support": int(placement.support),
                        "rival_mismatch": float(placement.rival_mismatch),
                        "validation_mismatch": placement.diagnostics.get(
                            "validation_mismatch"),
                        "mismatch_gap": placement.diagnostics.get(
                            "mismatch_gap"),
                    }
                queue.extend(_subdivide(win, ctx, config))
                notify_window("window_complete")
                continue
            # post-placement subpixel refinement (train/held-out split)
            refine_meta: dict = {}
            if config.refine:
                notify_window("refine")
                refined = refine_pose(
                    ctx, sampled, placement, spec, seed, config)
                if refined is not None:
                    new_pose, refine_meta = refined
                    resampled = sample_window(ctx, new_pose, win.h, win.w)
                    if (resampled is not None
                            and int(resampled.mask.sum())
                            >= config.min_support):
                        sampled = resampled
                        pose = new_pose
                        core = _core(sampled.mask, config.erode_cells)
            # straddle audit: a y-step/fold window must not emit its
            # minority side at the majority side's addresses
            core, audit_stats = audit_blocks(
                sampled, core, placement, spec, seed, config)
            row["straddle_audit"] = audit_stats
            if audit_stats["refused"]:
                row["outcome"] = "audit_refused"
                queue.extend(_subdivide(win, ctx, config))
                notify_window("window_complete")
                continue
            # payload need != pilot need: a window whose pilot sites are
            # all already observed still carries payload coverage E023
            # samples through its pose, so the gated placement is RECORDED
            # either way; only pilot emission / anchor duty / the accepted
            # counter are reserved for non-redundant windows.
            redundant = not _adds_needed_support(core, placement, pending)
            if redundant:
                record_component = -1 if component is None else int(component)
            else:
                if component is None:
                    component = n_components
                    n_components += 1
                record_component = int(component)
            diag = dict(placement.diagnostics)
            diag.update(refine_meta)
            diag["straddle_audit"] = audit_stats
            rival_searched = bool(diag.get("rival_searched", False))
            record = PlacedWindow(
                region_index=region_index, window=win,
                page=int(placement.page), origin_yx=placement.origin_yx,
                rot_k=int(placement.rot_k), method=method,
                mismatch=float(placement.mismatch),
                validation_mismatch=float(
                    diag.get("validation_mismatch", 1.0)),
                rival_mismatch=(float(placement.rival_mismatch)
                                if rival_searched else None),
                support=int(placement.support), pose=pose,
                elapsed_s=max(
                    0.0, perf_counter() - t_win - window_observer_s),
                component=record_component,
                rival_searched=rival_searched,
                predicted_residual_cells=residual,
                bch_errors=bch_errors, scan_id=scan_id,
                redundant=redundant,
                diagnostics=diag,
            )
            local_points = np.argwhere(core)
            rotated_points = _rotated_points(
                local_points, sampled.bits.shape, record.rot_k
            )
            page_points = rotated_points + np.asarray(
                record.origin_yx, np.int64
            )
            inside = (
                (page_points[:, 0] >= 0)
                & (page_points[:, 0] < spec.page_cells_yx[0])
                & (page_points[:, 1] >= 0)
                & (page_points[:, 1] < spec.page_cells_yx[1])
            )
            record.page_cells_yx = page_points[inside].astype(
                np.int32, copy=False
            )
            result.placements.append(record)
            if redundant:
                row["outcome"] = "redundant_skipped"
                row["origin_yx"] = list(placement.origin_yx)
                notify_window("window_complete")
                continue
            anchors.append(record)
            touched = _add_placement_observations(
                result, ctx, sampled, record, core, spec, seed, config
            )
            for key in touched:
                if result.tiles[key].observed_sites >= config.found_tile_min_sites:
                    found.add(key)
            accepted += 1
            row["outcome"] = "accepted"
            row["method"] = method
            row["origin_yx"] = list(placement.origin_yx)
            row["mismatch"] = float(placement.mismatch)
            row["validation"] = record.validation_mismatch
            row["component"] = int(component)
            notify_window("window_complete")
        if accepted:
            region_state = "accepted"
        elif any(row.redundant for row in result.placements
                 if row.region_index == region_index):
            region_state = "redundant"   # placed everywhere, nothing new
        else:
            region_state = "unresolved"
        result.region_states[region_index] = region_state
        notify_region(region_index)
    decode_known_tiles(result, spec, seed)
    result.timings["total_s"] = perf_counter() - total_start - observer_s
    result.diagnostics["found_tiles"] = sorted(found)
    result.diagnostics["format_id"] = descriptor.format_id
    result.diagnostics["pages"] = [int(page) for page in pages]
    result.diagnostics["scan_id"] = scan_id
    result.diagnostics["pitch_prior_px"] = float(pitch)
    result.diagnostics["pitch_prior_source"] = prior_source
    result.diagnostics["window_audit"] = audit
    return result
