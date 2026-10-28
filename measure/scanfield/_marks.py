"""Per-channel first-moment registration of one small achromatic mark.

The question this estimator exists for is not sharpness but POSITION: at
one place on the platen, how far apart do R, G and B put the same
physical black mark?  A K mark is one object in every channel, so its
own shape, its toner raggedness and the printer that laid it are all
channel-COMMON and cancel in a channel difference.  What survives is the
scanner's own per-channel geometry.

Why a first moment rather than an edge fit.  ``scanner/_edge`` needs a
straight edge long enough to fill quarter-pixel bins by its own slant;
the marks that reach the OUTER platen — the 1.19 mm edge ticks at
x ~ 4 mm and x ~ 205 mm, the 1.31 mm plus marks — are too small for
that, and the outer platen is exactly where lateral chromatic aberration
would live.  A centroid needs no slant, uses both axes of one mark, and
under convolution is exactly additive: ``centroid(mark * psf) =
centroid(mark) + centroid(psf)``, so the channel difference is the
difference of the two channels' PSF first moments and the mark drops out
identically.  That also fixes what the number MEANS: it is where the
channel puts the mass, skew included, which is the quantity a sampler
that reads cell centres actually suffers.

Three things are done to keep it honest, and ``selftest`` measures all
three against injected truth:

* ONE window, shared by every channel, taken from the channel mean.  Per
  channel windows would let a contrast difference become a position
  difference.
* Per-channel level normalization against a median ink level (inside an
  eroded footprint) and a median paper level (outside a dilated one), so
  a channel that simply reads the toner darker is not a channel that
  reads it displaced.
* A weight floor AND a common support mask.  Paper texture has a long
  lever arm at the window rim, and the AltaLink lays yellow MIC tracking
  dots on every colour sheet — invisible in red and green, DARK IN BLUE.
  Measured here before the mask existed: on the AltaLink discovery sheet
  the thin-stroke marks reported B-G offsets up to 1.96 dots, while the
  M281 sheet, which has no MIC dots at all (e031 §7 / 007.8), reported
  0.16 dots on the same targets through the same code.  That is a
  contaminant, not a scanner.  Weights are therefore zeroed outside the
  mark's OWN footprint (taken from the channel mean, so it is the same
  region in every channel) dilated by ``support_halo_um``, which is set
  wide enough to contain the PSF tails and narrow enough to exclude a
  speck sitting a fifth of a millimetre away.  ``excluded_fraction``
  reports how much weight the mask threw away, per channel: it is the
  contamination meter, and on a MIC sheet blue's is visibly the largest.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from scanner._edge import PRINT_DPI, UM_PER_INCH, linearize_srgb

_ERF = np.vectorize(math.erf, otypes=[np.float64])


@dataclass(frozen=True)
class MarkResult:
    """One mark, one capture: where each channel put it."""

    ok: bool
    note: str
    support_px: int
    contrast: dict[str, float]
    centroid_px: dict[str, tuple[float, float]]     # (y, x), window-local
    offsets_dots: dict[str, dict[str, float]]       # channel -> dx/dy dots
    excluded_fraction: dict[str, float]             # weight outside support

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "note": self.note, "support_px": self.support_px,
            "contrast": self.contrast,
            "centroid_px": {k: {"y": v[0], "x": v[1]}
                            for k, v in self.centroid_px.items()},
            "offsets_dots": self.offsets_dots,
            "excluded_fraction": self.excluded_fraction,
        }


def _grow(mask: np.ndarray, steps: int) -> np.ndarray:
    """4-neighbour dilation, ``steps`` times (no scipy in this package)."""
    out = mask
    for _ in range(max(0, steps)):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _shrink(mask: np.ndarray, steps: int) -> np.ndarray:
    return ~_grow(~mask, steps)


def _shift_bilinear(image: np.ndarray, dy: float, dx: float) -> np.ndarray:
    """``out(p) = image(p - d)`` — image translated by ``d``, zero-padded."""
    rows, columns = image.shape
    iy, ix = int(math.floor(dy)), int(math.floor(dx))
    fy, fx = dy - iy, dx - ix
    out = np.zeros_like(image)
    for (oy, ox), weight in (((0, 0), (1 - fy) * (1 - fx)),
                             ((0, 1), (1 - fy) * fx),
                             ((1, 0), fy * (1 - fx)),
                             ((1, 1), fy * fx)):
        if weight == 0.0:
            continue
        sy, sx = iy + oy, ix + ox
        ya, yb = max(0, sy), min(rows, rows + sy)
        xa, xb = max(0, sx), min(columns, columns + sx)
        if yb <= ya or xb <= xa:
            continue
        out[ya:yb, xa:xb] += weight * image[ya - sy:yb - sy, xa - sx:xb - sx]
    return out


def _gradient_shift(reference: np.ndarray, channel: np.ndarray,
                    region: np.ndarray, *, iterations: int = 4
                    ) -> tuple[float, float] | None:
    """Least-squares translation of ``channel`` relative to ``reference``.

    The centroid estimator above is exact under convolution but has a
    LEVER ARM: a speck of contamination anywhere in the support moves the
    first moment in proportion to its distance from the mark.  On the
    AltaLink's thin-stroke registration crosses, one MIC dot near the end
    of a 6 mm stroke moved blue by 1.96 dots.  This estimator has no
    lever arm — it is the Gauss-Newton solution of
    ``min_d || ref(p - d) - c(p) ||^2`` over the support, so its weight
    is the image GRADIENT and a speck on a flat plateau contributes a
    residual rather than a displacement.  Blur differences between
    channels are even and the gradient is odd, so a symmetric width
    mismatch integrates out; the selftest measures what is left.

    Returns ``(dy, dx)`` in pixels, or ``None`` if the normal equations
    are singular (no gradient to register against).
    """
    weight = region.astype(np.float64)
    total_dy, total_dx = 0.0, 0.0
    for _ in range(iterations):
        warped = _shift_bilinear(reference, total_dy, total_dx)
        gy, gx = np.gradient(warped)
        gy, gx = gy * weight, gx * weight
        difference = (channel - warped) * weight
        matrix = np.array([[float((gy * gy).sum()), float((gy * gx).sum())],
                           [float((gy * gx).sum()), float((gx * gx).sum())]])
        vector = np.array([float((gy * difference).sum()),
                           float((gx * difference).sum())])
        if abs(np.linalg.det(matrix)) < 1e-12:
            return None
        step = np.linalg.solve(matrix, -vector)
        total_dy += float(step[0])
        total_dx += float(step[1])
        if abs(step[0]) < 1e-4 and abs(step[1]) < 1e-4:
            break
    return total_dy, total_dx


def mark_offsets(patch: np.ndarray, *, scan_dpi: float,
                 channel_names: Sequence[str] = ("R", "G", "B"),
                 reference: str = "G", tone: str | None = None,
                 weight_floor: float = 0.25,
                 halo_fraction: float = 0.45,
                 support_halo_um: float = 120.0,
                 min_support_px: int = 64,
                 min_contrast: float = 0.10) -> MarkResult:
    """Channel-vs-reference offset of the mark centred in ``patch``.

    ``patch`` is (rows, columns, channels), 8-bit as scanned.  Returns
    offsets in 600-dpi printed dots, ``dx`` along the sensor axis
    (columns) and ``dy`` along the transport axis (rows).
    """
    data = np.asarray(patch)
    if data.ndim != 3 or data.shape[2] < len(channel_names):
        raise ValueError("patch must be (rows, columns, >=len(channels))")
    values = linearize_srgb(data, tone)
    planes = {name: values[:, :, index]
              for index, name in enumerate(channel_names)}
    if reference not in planes:
        raise ValueError(f"reference {reference!r} not among {channel_names}")

    mean = values[:, :, :len(channel_names)].mean(axis=2)
    paper_guess = float(np.percentile(mean, 92.0))
    ink_guess = float(np.percentile(mean, 3.0))
    if paper_guess - ink_guess <= min_contrast:
        return MarkResult(False, "no ink in patch", 0, {}, {}, {}, {})
    footprint = mean < 0.5 * (paper_guess + ink_guess)
    support = int(footprint.sum())
    if support < min_support_px:
        return MarkResult(False, f"footprint {support} px", support,
                          {}, {}, {}, {})

    rows, columns = np.nonzero(footprint)
    y0, y1 = int(rows.min()), int(rows.max())
    x0, x1 = int(columns.min()), int(columns.max())
    pad_y = max(6, int(round(halo_fraction * (y1 - y0 + 1))))
    pad_x = max(6, int(round(halo_fraction * (x1 - x0 + 1))))
    wy0, wy1 = max(0, y0 - pad_y), min(mean.shape[0], y1 + pad_y + 1)
    wx0, wx1 = max(0, x0 - pad_x), min(mean.shape[1], x1 + pad_x + 1)
    if wy1 - wy0 < 8 or wx1 - wx0 < 8:
        return MarkResult(False, "window collapsed", support, {}, {}, {}, {})

    window = footprint[wy0:wy1, wx0:wx1]
    core = _shrink(window, 2)
    if not core.any():
        core = window
    halo_px = int(round(support_halo_um / (UM_PER_INCH / scan_dpi)))
    region = _grow(window, halo_px)
    ring = ~_grow(window, max(4, halo_px))
    if ring.sum() < 32:
        return MarkResult(False, "no paper ring", support, {}, {}, {}, {})

    yy, xx = np.mgrid[0:wy1 - wy0, 0:wx1 - wx0].astype(np.float64)
    centroids: dict[str, tuple[float, float]] = {}
    contrast: dict[str, float] = {}
    excluded: dict[str, float] = {}
    fractions: dict[str, np.ndarray] = {}
    for name in channel_names:
        crop = planes[name][wy0:wy1, wx0:wx1]
        ink = float(np.median(crop[core]))
        paper = float(np.median(crop[ring]))
        span = paper - ink
        contrast[name] = span
        if span <= min_contrast:
            return MarkResult(False, f"{name} contrast {span:.3f}",
                              support, contrast, {}, {}, {})
        fraction = np.clip((paper - crop) / span, 0.0, 1.0)
        fractions[name] = fraction
        weight = np.clip(fraction - weight_floor, 0.0, None)
        loose = float(weight.sum())
        weight = np.where(region, weight, 0.0)
        total = float(weight.sum())
        if total <= 0.0:
            return MarkResult(False, f"{name} weightless", support,
                              contrast, {}, {}, {})
        excluded[name] = (loose - total) / loose if loose > 0.0 else 0.0
        centroids[name] = (float((weight * yy).sum() / total),
                           float((weight * xx).sum() / total))

    per_px_dots = PRINT_DPI / scan_dpi
    base_y, base_x = centroids[reference]
    offsets: dict[str, dict[str, float]] = {}
    for name in channel_names:
        if name == reference:
            continue
        moment_dy = centroids[name][0] - base_y
        moment_dx = centroids[name][1] - base_x
        gradient = _gradient_shift(fractions[reference], fractions[name],
                                   region)
        if gradient is None:
            return MarkResult(False, f"{name} has no gradient", support,
                              contrast, centroids, {}, excluded)
        offsets[name] = {
            "reference": reference,
            "dx_dots": gradient[1] * per_px_dots,
            "dy_dots": gradient[0] * per_px_dots,
            "dx_um": gradient[1] * UM_PER_INCH / scan_dpi,
            "dy_um": gradient[0] * UM_PER_INCH / scan_dpi,
            "dx_dots_moment": moment_dx * per_px_dots,
            "dy_dots_moment": moment_dy * per_px_dots,
        }
    return MarkResult(True, "", support, contrast, centroids, offsets,
                      excluded)


# --- synthetic calibration ------------------------------------------------

def _blurred_box(coordinate: np.ndarray, centre: float, side: float,
                 sigma: float) -> np.ndarray:
    """A box of width ``side`` centred at ``centre``, Gaussian-blurred.

    Exact: the convolution of a box with a Gaussian is a difference of
    error functions, so a sub-pixel ``centre`` is applied EXACTLY rather
    than by interpolating a sampled image (which would blur it again and
    bias the very quantity under test).
    """
    root = sigma * math.sqrt(2.0)
    hi = (coordinate - centre + side / 2.0) / root
    lo = (coordinate - centre - side / 2.0) / root
    return 0.5 * (_ERF(hi) - _ERF(lo))


def synth_mark(*, size_px: int, side_px: float, sigma_px: float | tuple,
               shift_xy_px: tuple[float, float], contrast: float,
               skew_px: float = 0.0, skew_weight: float = 0.0,
               noise: float = 0.0, specks: int = 0, speck_px: float = 9.0,
               speck_channel: int = 2, speck_depth: float = 0.30,
               seed: int = 0) -> tuple[np.ndarray, tuple[float, float]]:
    """A synthetic K square seen by three channels, with known truth.

    Channel 0 (R) carries ``shift_xy_px``; channels 1 and 2 sit at the
    origin, so the injected R-G offset is known exactly.  ``sigma_px``
    may be a per-channel triple: the scanner's measured channel widths
    differ by a few percent, and a centroid must not turn a width
    difference into a position.  ``skew_*`` adds a one-sided PSF lobe to
    channel 2 (B) — the term a centroid CANNOT distinguish from a
    displacement, and the reason the polarity split in the edge arm is
    carried alongside.  ``specks`` scatters dark blobs into
    ``speck_channel`` only, on a lattice around the mark: the AltaLink's
    yellow MIC dots, which are dark in blue and are the measured reason
    the support mask exists.
    """
    rng = np.random.default_rng(seed)
    axis = np.arange(size_px, dtype=np.float64)
    centre = (size_px - 1) / 2.0
    sigmas = ((sigma_px,) * 3 if isinstance(sigma_px, (int, float))
              else tuple(sigma_px))
    out = np.zeros((size_px, size_px, 3), dtype=np.float64)
    for index in range(3):
        dx, dy = (shift_xy_px if index == 0 else (0.0, 0.0))
        sigma = sigmas[index]
        profile_x = _blurred_box(axis, centre + dx, side_px, sigma)
        profile_y = _blurred_box(axis, centre + dy, side_px, sigma)
        ink = np.outer(profile_y, profile_x)
        if index == 2 and skew_weight > 0.0:
            lobe_x = _blurred_box(axis, centre + skew_px, side_px, sigma)
            lobe = np.outer(profile_y, lobe_x)
            ink = (1.0 - skew_weight) * ink + skew_weight * lobe
        out[:, :, index] = 1.0 - contrast * ink
    if specks:
        for _ in range(specks):
            cy = float(rng.uniform(0, size_px))
            cx = float(rng.uniform(0, size_px))
            blob = np.outer(_blurred_box(axis, cy, speck_px, 1.5),
                            _blurred_box(axis, cx, speck_px, 1.5))
            out[:, :, speck_channel] -= speck_depth * blob
    if noise:
        out += rng.normal(0.0, noise, out.shape)
    encoded = np.clip(out, 0.0, 1.0)
    srgb = np.where(encoded <= 0.0031308, encoded * 12.92,
                    1.055 * encoded ** (1.0 / 2.4) - 0.055)
    return (np.round(srgb * 255.0).astype(np.uint8),
            (shift_xy_px[0], shift_xy_px[1]))


def selftest(scan_dpi: float = 4800.0, tone: str | None = None
             ) -> list[dict[str, Any]]:
    """Injected-truth cases for ``mark_offsets``.  Seeded, deterministic."""
    cases: list[dict[str, Any]] = []
    plans = [
        ("clean", dict(shift_xy_px=(0.0, 0.0), noise=0.0, specks=0)),
        ("shift-0.10px", dict(shift_xy_px=(0.10, -0.06), noise=0.0)),
        ("shift-0.50px", dict(shift_xy_px=(0.50, 0.25), noise=0.0)),
        ("shift-2.00px", dict(shift_xy_px=(2.00, -1.00), noise=0.0)),
        ("noisy", dict(shift_xy_px=(0.50, 0.25), noise=0.004)),
        ("mic-specks", dict(shift_xy_px=(0.50, 0.25), noise=0.004,
                            specks=8)),
        ("mic-specks-heavy", dict(shift_xy_px=(0.50, 0.25), noise=0.004,
                                  specks=40)),
        ("blur-mismatch", dict(shift_xy_px=(0.50, 0.25), noise=0.004,
                               sigma_px=(3.45, 3.0, 2.55))),
        ("skew-B", dict(shift_xy_px=(0.0, 0.0), noise=0.004,
                        skew_px=6.0, skew_weight=0.10)),
    ]
    for name, override in plans:
        kwargs: dict[str, Any] = dict(
            size_px=240, side_px=112.0, sigma_px=3.0, contrast=0.80,
            shift_xy_px=(0.0, 0.0), seed=20260830)
        kwargs.update(override)
        patch, truth = synth_mark(**kwargs)
        result = mark_offsets(patch, scan_dpi=scan_dpi, tone=tone)
        measured = result.offsets_dots.get("R", {})
        per_px_dots = PRINT_DPI / scan_dpi
        row = {
            "case": name,
            "ok": result.ok,
            "truth_dx_px": truth[0], "truth_dy_px": truth[1],
            "measured_dx_px": measured.get("dx_dots", float("nan"))
            / per_px_dots,
            "measured_dy_px": measured.get("dy_dots", float("nan"))
            / per_px_dots,
        }
        row["error_dx_px"] = row["measured_dx_px"] - truth[0]
        row["error_dy_px"] = row["measured_dy_px"] - truth[1]
        row["error_dx_dots"] = row["error_dx_px"] * per_px_dots
        row["error_dy_dots"] = row["error_dy_px"] * per_px_dots
        row["excluded_fraction_B"] = result.excluded_fraction.get("B")
        blue_case = result.offsets_dots.get("B", {})
        row["measured_B_dx_dots"] = blue_case.get("dx_dots")
        row["measured_B_dy_dots"] = blue_case.get("dy_dots")
        if kwargs.get("skew_weight"):
            blue = result.offsets_dots.get("B", {})
            row["skew_truth_px"] = (kwargs["skew_weight"]
                                    * kwargs["skew_px"])
            row["skew_measured_px"] = (blue.get("dx_dots", float("nan"))
                                       / per_px_dots)
        cases.append(row)
    return cases
