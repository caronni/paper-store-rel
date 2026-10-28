"""Per-channel slanted-edge engine (ISO-12233-style, no matplotlib, no scipy).

The one thing this module exists for that
``src/holo/characterize/diagnostics.py::slanted_edge_mtf50`` does not do:
it keeps the three RGB channels *separate* through the whole chain and
projects all of them onto ONE shared, reference-fitted edge line, so the
per-channel ESF offsets that come out are lateral chromatic aberration
and not three independent fits disagreeing.  It also reports MTF10 and
the 10-90 rise, which that function does not compute.

Chain, per patch:

1. linearize (sRGB EOTF by default — the scan is gamma-encoded 8-bit and
   an MTF wants a radiance-linear quantity);
2. fit the edge line on a REFERENCE image (the channel mean), row by row,
   by derivative centroid + robust linear fit;
3. project every pixel of every channel onto that one line's normal and
   bin the signed distance at 1/4 px (the super-resolution step);
4. normalize each channel's ESF on its OWN plateaus (so a channel's ink
   contrast drops out and only the shape survives);
5. LSF = central difference; Hann window of a fixed half-width centred on
   the REFERENCE centroid (shared window ⇒ comparable centroids);
6. zero-padded rFFT ⇒ MTF, read MTF50 / MTF10 in lp/mm.

Everything is in units-in-names: ``*_px`` at the scan grid, ``*_um``,
``*_lp_per_mm``, ``*_dots`` at 600 dpi print.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np


PRINT_DPI = 600.0
UM_PER_INCH = 25400.0


TONE_MODE = "srgb"          # "srgb" | "gamma22" | "none" (a control knob)


def linearize_srgb(values: np.ndarray, mode: str | None = None) -> np.ndarray:
    """8-bit encoded counts -> a radiance-linear quantity in [0, 1].

    The transfer function is a CONTROL, not a detail: the three channels
    sit at different plateau levels on a K edge (paper 228/230/232, ink
    63/61/61), so a wrong decode curve would bend their ESFs by different
    amounts and could manufacture the very channel difference this
    instrument reports.  ``mode`` lets the whole run be repeated under
    sRGB, a plain 2.2 gamma, or no decode at all; the recorded finding is
    the one that survives all three.
    """
    x = np.asarray(values, dtype=np.float64) / 255.0
    mode = mode or TONE_MODE
    if mode == "none":
        return x
    if mode == "gamma22":
        return x ** 2.2
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _gaussian_blur(values: np.ndarray, sigma_bins: float) -> np.ndarray:
    """1-D Gaussian smoothing with edge-clamped padding (no scipy)."""
    if not np.isfinite(sigma_bins) or sigma_bins < 0.05:
        return np.asarray(values, dtype=np.float64)
    radius = max(1, int(math.ceil(4.0 * sigma_bins)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (offsets / sigma_bins) ** 2)
    kernel /= kernel.sum()
    padded = np.concatenate([
        np.full(radius, values[0]), np.asarray(values, dtype=np.float64),
        np.full(radius, values[-1])])
    return np.convolve(padded, kernel, mode="valid")


def _robust_line_fit(x: np.ndarray, y: np.ndarray,
                     iterations: int = 4) -> tuple[float, float, float]:
    """Least squares with iterative 2.5-sigma trimming.  -> slope, intercept, rms."""
    keep = np.isfinite(y)
    slope = intercept = 0.0
    rms = float("nan")
    for _ in range(iterations):
        if keep.sum() < 8:
            break
        coefficients = np.polyfit(x[keep], y[keep], 1)
        slope, intercept = float(coefficients[0]), float(coefficients[1])
        residual = y - (slope * x + intercept)
        rms = float(np.sqrt(np.nanmean(residual[keep] ** 2)))
        if not np.isfinite(rms) or rms <= 0:
            break
        keep = np.isfinite(y) & (np.abs(residual) <= 2.5 * rms)
    return slope, intercept, rms


def _row_edge_centroids(reference: np.ndarray,
                        window_px: int) -> np.ndarray:
    """Sub-pixel edge column for every row, by |d/dx| centroid.

    ``reference`` is (rows, columns) with the transition running roughly
    down the columns.  A coarse per-row argmax localizes the edge, then
    the centroid is taken over +/- ``window_px`` around it, which keeps
    toner mottle and paper texture on the plateaus out of the estimate.
    """
    gradient = np.abs(np.diff(reference, axis=1))
    rows, columns = gradient.shape
    coarse = np.argmax(gradient, axis=1)
    positions = np.full(rows, np.nan)
    index = np.arange(columns, dtype=np.float64)
    for row in range(rows):
        lo = max(0, int(coarse[row]) - window_px)
        hi = min(columns, int(coarse[row]) + window_px + 1)
        weights = gradient[row, lo:hi]
        total = weights.sum()
        if total <= 0:
            continue
        # +0.5: np.diff bin i sits between samples i and i+1.
        positions[row] = float((index[lo:hi] * weights).sum() / total) + 0.5
    return positions


@dataclass
class ChannelResult:
    name: str
    esf: np.ndarray
    lsf: np.ndarray
    mtf: np.ndarray
    edge_px: float           # 50% crossing, projected coordinate
    centroid_px: float       # LSF centroid, shared window
    rise_10_90_px: float
    mtf50_lp_per_mm: float
    mtf10_lp_per_mm: float
    contrast: float          # linear-reflectance plateau separation
    spectrum: np.ndarray | None = None   # complex, for ratios and phase
    # linear plateau slopes (per px) when the plateaus were detrended:
    # (ink side, paper side).  Their SIZE is the diagnostic — a solid
    # patch whose interior shades toward its own edge is a print fact,
    # and it is exactly what corrupts an undetrended 10-90 rise.
    plateau_slopes_per_px: tuple[float, float] | None = None

    def summary(self, scan_dpi: float) -> dict[str, Any]:
        um = UM_PER_INCH / scan_dpi
        return {
            "channel": self.name,
            "mtf50_lp_per_mm": self.mtf50_lp_per_mm,
            "mtf10_lp_per_mm": self.mtf10_lp_per_mm,
            "rise_10_90_px": self.rise_10_90_px,
            "rise_10_90_um": self.rise_10_90_px * um,
            "edge_px": self.edge_px,
            "centroid_px": self.centroid_px,
            "contrast_linear": self.contrast,
        }


def compare_channels(result: "EdgeResult", *, reference: str = "G",
                     scan_dpi: float, mtf_floor: float = 0.25,
                     f_min_lp_per_mm: float = 0.4,
                     allow_intercept: bool = False,
                     ) -> dict[str, dict[str, float]]:
    """Channel-vs-reference differentials that CANCEL the common target.

    Both estimators exploit the fact that a K-toner edge presents the same
    physical profile to every channel, so everything print-side divides
    out of a channel RATIO:

    * ``dsigma2_um2`` — ``ln(MTF_c/MTF_ref) = -2 pi^2 (sig_c^2 - sig_ref^2) f^2``
      fitted over the reliable band, weighted by the reference MTF.  Only
      the DIFFERENCE of the squared widths is estimated, so toner scatter,
      paper light-spread, the printer's own edge raggedness and the ESF
      window all cancel (they are channel-common), and no Gaussian
      assumption is made about the target — only about the scanner-side
      difference.  Equivalently it is the difference of the LSF second
      moments, which add under convolution.
    * ``shift_px`` — sub-pixel registration of the two normalized ESFs by
      derivative-weighted least squares,
      ``d = sum w (E_ref - E_c) E_ref' / sum w E_ref'^2``.  The weight is
      ``E_ref'^2``, so the flat plateaus (where paper texture and toner
      mottle live, with a long lever arm) contribute nothing.  A
      whole-spectrum phase fit was tried first and is NOT used: at the
      low frequencies a 120 um printed edge leaves usable it returned
      +-1 px on a target where the level crossings agree to 0.05 px.

    ``allow_intercept`` — REQUIRED FOR LINE TARGETS, wrong for edges.
    The default fit has no constant term, which is correct for an edge:
    ``analyze_edge`` normalizes each channel's ESF on its OWN plateaus,
    so its LSF integrates to 1 in every channel and ``ln(ratio)`` really
    does go to zero at DC.  ``line_metrics`` normalizes by the PEAK and
    leaves the spectrum in linear reflectance, so for a line the DC
    ratio is the channels' ink CONTRAST ratio — and an intercept-free
    ``f^2`` fit has nowhere to put that constant except the slope.
    Measured on the e028 K registration bars, whose slightly warm black
    reads 4.5 % weaker in R than in G: the intercept-free fit reports
    ``dsigma2`` R +102 / B -107 um^2, and the same data with an
    intercept reports R -5.9 / B -12.8 — which is what the e031 sheet
    gives either way (R -6.1 / B -9.5 with, +4.0 / -32.8 without).  The
    spurious term scales with how non-neutral that engine's K is, which
    is why it looked like a per-engine physical difference.
    """
    freq = result.frequencies_lp_per_mm
    base = result.channels.get(reference)
    if base is None or base.spectrum is None:
        return {}
    usable = np.flatnonzero(base.mtf < mtf_floor)
    top = int(usable[0]) if usable.size else len(freq) - 1
    band = (freq >= f_min_lp_per_mm) & (np.arange(len(freq)) <= top)
    out: dict[str, dict[str, float]] = {}
    if band.sum() < 6:
        return out
    f = freq[band]
    weight = base.mtf[band]
    bin_px = float(np.diff(result.bin_centers_px).mean())
    for name, channel in result.channels.items():
        if channel.spectrum is None or name == reference:
            continue
        ratio = np.clip(np.abs(channel.spectrum[band])
                        / np.abs(base.spectrum[band]), 1e-6, None)
        x = f ** 2
        log_ratio = np.log(ratio)
        intercept = 0.0
        if allow_intercept:
            root = np.sqrt(weight)
            design = np.column_stack([x, np.ones_like(x)]) * root[:, None]
            solution, *_ = np.linalg.lstsq(design, log_ratio * root,
                                           rcond=None)
            slope, intercept = float(solution[0]), float(solution[1])
        else:
            slope = float((weight * x * log_ratio).sum()
                          / (weight * x * x).sum())
        dsigma2_mm2 = -slope / (2.0 * np.pi ** 2)
        # Width-match before registering: a pure-translation fit between
        # profiles of DIFFERENT width is biased toward zero (measured
        # -27% on the self-test), so blur whichever is sharper by the
        # dsigma2 just estimated and register the matched pair.
        blur_px = math.sqrt(abs(dsigma2_mm2)) * 1000.0 \
            / (UM_PER_INCH / scan_dpi) / bin_px
        reference_esf, channel_esf = base.esf, channel.esf
        if dsigma2_mm2 > 0:
            reference_esf = _gaussian_blur(reference_esf, blur_px)
        elif dsigma2_mm2 < 0:
            channel_esf = _gaussian_blur(channel_esf, blur_px)
        derivative = np.gradient(reference_esf)
        esf_weight = derivative ** 2
        difference = reference_esf - channel_esf
        shift_bins = float((esf_weight * difference * derivative).sum()
                           / max((esf_weight * derivative ** 2).sum(), 1e-30))
        shift_px = shift_bins * bin_px
        out[name] = {
            "reference": reference,
            "dsigma2_um2": dsigma2_mm2 * 1e6,
            "dsigma_um": float(np.sign(dsigma2_mm2)
                               * np.sqrt(abs(dsigma2_mm2)) * 1000.0),
            "shift_px": shift_px,
            "shift_um": shift_px * UM_PER_INCH / scan_dpi,
            "shift_dots": px_to_dots(shift_px, scan_dpi),
            "band_lo_lp_per_mm": float(f[0]),
            "band_hi_lp_per_mm": float(f[-1]),
            "band_points": int(band.sum()),
        }
        if allow_intercept:
            out[name]["log_amplitude_intercept"] = intercept
            out[name]["amplitude_ratio"] = float(math.exp(intercept))
    return out


@dataclass
class EdgeResult:
    angle_deg: float
    fit_rms_px: float
    rows_used: int
    samples: int
    frequencies_lp_per_mm: np.ndarray
    bin_centers_px: np.ndarray = field(
        default_factory=lambda: np.zeros(0))
    channels: dict[str, ChannelResult] = field(default_factory=dict)
    note: str = ""

    def summary(self, scan_dpi: float) -> dict[str, Any]:
        return {
            "angle_deg": self.angle_deg,
            "fit_rms_px": self.fit_rms_px,
            "rows_used": self.rows_used,
            "samples": self.samples,
            "channels": {
                name: result.summary(scan_dpi)
                for name, result in self.channels.items()
            },
            "note": self.note,
        }


def _crossing(x: np.ndarray, y: np.ndarray, level: float) -> float:
    """First upward crossing of ``level`` in a monotone-ish normalized ESF."""
    above = np.flatnonzero(y >= level)
    if not above.size or above[0] == 0:
        return float("nan")
    i = int(above[0])
    y0, y1 = float(y[i - 1]), float(y[i])
    if y1 == y0:
        return float(x[i])
    return float(x[i - 1] + (level - y0) * (x[i] - x[i - 1]) / (y1 - y0))


def _level_outward(x: np.ndarray, y: np.ndarray, level: float,
                   start: int, direction: int) -> float:
    """Crossing of ``level`` found by walking OUTWARD from ``start``.

    ``_crossing`` takes the first crossing anywhere in the profile, which
    is right for a clean ESF and wrong for a real one: the e028 yellow
    patch carries a mottle bump 90 px into its own ink plateau that
    rises past 0.1, and a first-crossing 10 % point lands on the bump
    instead of the edge — a 550 um "rise" on an ordinary 130 um edge.
    Anchoring the search at the 50 % crossing and walking away from it
    makes the measurement local to the transition.
    """
    if direction < 0:
        below = np.flatnonzero(y[:start + 1] <= level)
        if not below.size:
            return float("nan")
        index = int(below[-1])
        if index >= len(y) - 1:
            return float(x[index])
        y0, y1 = float(y[index]), float(y[index + 1])
        if y1 == y0:
            return float(x[index])
        return float(x[index] + (level - y0)
                     * (x[index + 1] - x[index]) / (y1 - y0))
    above = np.flatnonzero(y[start:] >= level)
    if not above.size:
        return float("nan")
    index = int(above[0]) + start
    if index == 0:
        return float(x[index])
    y0, y1 = float(y[index - 1]), float(y[index])
    if y1 == y0:
        return float(x[index])
    return float(x[index - 1] + (level - y0)
                 * (x[index] - x[index - 1]) / (y1 - y0))


def _mtf_crossing(freq: np.ndarray, mtf: np.ndarray, level: float) -> float:
    below = np.flatnonzero(mtf <= level)
    if not below.size or below[0] == 0:
        return float("nan")
    i = int(below[0])
    y0, y1 = float(mtf[i - 1]), float(mtf[i])
    if y1 == y0:
        return float(freq[i])
    return float(freq[i - 1] + (level - y0) * (freq[i] - freq[i - 1])
                 / (y1 - y0))


def _detrended_esf(
    centers: np.ndarray, esf: np.ndarray, low: float, high: float,
    polarity: float, guard_px: float,
) -> tuple[np.ndarray | None, float, tuple[float, float] | None]:
    """Normalize an ESF against two FITTED plateaus instead of two levels.

    Returns ``(normalized, median contrast, (ink slope, paper slope))``,
    or ``(None, ...)`` when either side has too few samples outside the
    guard band — the caller then falls back to the constant plateaus.
    """
    mid = (low + high) / 2.0
    crossings = np.flatnonzero(np.diff(np.signbit(esf - mid)))
    if not crossings.size:
        return None, float(abs(high - low)), None
    index = int(crossings[len(crossings) // 2])
    x_mid = float(centers[index])
    left = centers < x_mid - guard_px
    right = centers > x_mid + guard_px
    if left.sum() < 8 or right.sum() < 8:
        return None, float(abs(high - low)), None
    left_fit = np.polyfit(centers[left], esf[left], 1)
    right_fit = np.polyfit(centers[right], esf[right], 1)
    left_line = np.polyval(left_fit, centers)
    right_line = np.polyval(right_fit, centers)
    if polarity > 0:
        lo_line, hi_line, lo_fit, hi_fit = (left_line, right_line,
                                            left_fit, right_fit)
    else:
        lo_line, hi_line, lo_fit, hi_fit = (right_line, left_line,
                                            right_fit, left_fit)
    separation = hi_line - lo_line
    if float(np.min(separation)) <= 0:
        return None, float(abs(high - low)), None
    return ((esf - lo_line) / separation, float(np.median(separation)),
            (float(lo_fit[0]), float(hi_fit[0])))


def analyze_edge(
    patch: np.ndarray,
    *,
    scan_dpi: float,
    orientation: str = "vertical",
    channel_names: Sequence[str] = ("R", "G", "B"),
    bin_px: float = 0.25,
    centroid_window_px: int = 24,
    lsf_halfwidth_px: float = 40.0,
    pad_factor: int = 8,
    linearize: bool = True,
    extra_channels: dict[str, np.ndarray] | None = None,
    plateau_guard_um: float | None = None,
) -> EdgeResult:
    """Per-channel slanted-edge analysis of one straight edge.

    ``patch`` is (rows, columns, channels) 8-bit or float.  ``orientation``
    names the EDGE: ``"vertical"`` means the transition runs across the
    columns (an ESF along x, the sensor axis); ``"horizontal"`` means it
    runs across the rows (an ESF along y, the transport axis) and the
    patch is transposed internally.

    ``plateau_guard_um`` opts into a DETRENDED normalization: instead of
    two constant plateau levels, a straight line is fitted to each side
    beyond that guard distance from the 50 % crossing, and the ESF is
    normalized against those lines.  It exists because a solid toner
    patch is not flat — on the e028 sheet the M281's starved yellow
    lightens by ~8 counts over the 180 um approaching its own edge, and
    against a CONSTANT plateau that ramp pushes the 10 % crossing far out
    and reports a 563 um "rise" for a perfectly ordinary edge.  Left at
    ``None`` the function is bit-identical to the undetrended original,
    which is what the recorded ``blue_mtf`` numbers were measured with.
    """
    data = np.asarray(patch)
    if data.ndim != 3:
        raise ValueError("patch must be (rows, columns, channels)")
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError(f"bad orientation {orientation!r}")
    if orientation == "horizontal":
        data = np.transpose(data, (1, 0, 2))

    values = (linearize_srgb(data) if linearize
              else np.asarray(data, dtype=np.float64) / 255.0)
    planes: dict[str, np.ndarray] = {
        name: values[:, :, index]
        for index, name in enumerate(channel_names[:values.shape[2]])
    }
    if extra_channels:
        for name, weights in extra_channels.items():
            weight = np.asarray(weights, dtype=np.float64)
            planes[name] = np.tensordot(values, weight, axes=([2], [0]))

    reference = values.mean(axis=2)
    rows, columns = reference.shape
    centroids = _row_edge_centroids(reference, centroid_window_px)
    row_index = np.arange(rows, dtype=np.float64)
    slope, intercept, fit_rms = _robust_line_fit(row_index, centroids)
    used = int(np.isfinite(centroids).sum())
    angle_deg = float(np.degrees(np.arctan(slope)))

    # Signed distance to the fitted line, in pixels, along its normal.
    yy, xx = np.indices(reference.shape, dtype=np.float64)
    normal = 1.0 / np.sqrt(1.0 + slope * slope)
    distance = (xx - (slope * yy + intercept)) * normal

    span = min(abs(float(distance.min())), abs(float(distance.max())))
    span = float(np.floor(span / bin_px) * bin_px)
    edges = np.arange(-span, span + bin_px, bin_px)
    which = np.digitize(distance.ravel(), edges) - 1
    valid = (which >= 0) & (which < len(edges) - 1)
    which = which[valid]
    counts = np.bincount(which, minlength=len(edges) - 1).astype(np.float64)
    occupied = counts > 0
    centers = (edges[:-1] + bin_px / 2.0)[occupied]

    px_mm = UM_PER_INCH / scan_dpi / 1000.0
    n_bins = int(occupied.sum())
    padded = int(2 ** np.ceil(np.log2(max(64, n_bins * pad_factor))))
    frequencies = np.fft.rfftfreq(padded, d=bin_px * px_mm)

    # Shared LSF window: centred on the reference channel's own centroid.
    reference_lsf_center = None
    results: dict[str, ChannelResult] = {}
    ordered = list(planes.items())
    ordered.sort(key=lambda item: item[0] not in set(channel_names))
    for name, plane in ordered:
        sums = np.bincount(which, weights=plane.ravel()[valid],
                           minlength=len(edges) - 1)
        esf = (sums[occupied] / counts[occupied])
        quarter = max(4, len(esf) // 5)
        low = float(np.median(esf[:quarter]))
        high = float(np.median(esf[-quarter:]))
        polarity = 1.0 if high >= low else -1.0
        lo_plateau, hi_plateau = (low, high) if polarity > 0 else (high, low)
        contrast = float(hi_plateau - lo_plateau)
        if contrast <= 0:
            continue
        slopes: tuple[float, float] | None = None
        if plateau_guard_um is None:
            normalized = (esf - lo_plateau) / contrast
        else:
            normalized, contrast, slopes = _detrended_esf(
                centers, esf, low, high, polarity,
                plateau_guard_um / (UM_PER_INCH / scan_dpi))
            if normalized is None:
                normalized = (esf - lo_plateau) / contrast
                slopes = None
        oriented = normalized if polarity > 0 else normalized[::-1]
        oriented_centers = centers if polarity > 0 else -centers[::-1]
        edge_px = _crossing(oriented_centers, oriented, 0.5)
        if plateau_guard_um is None:
            rise = (_crossing(oriented_centers, oriented, 0.9)
                    - _crossing(oriented_centers, oriented, 0.1))
        else:
            above = np.flatnonzero(oriented >= 0.5)
            middle = int(above[0]) if above.size else len(oriented) // 2
            rise = (_level_outward(oriented_centers, oriented, 0.9,
                                   middle, +1)
                    - _level_outward(oriented_centers, oriented, 0.1,
                                     middle, -1))
        if polarity < 0:
            edge_px = -edge_px

        lsf = np.gradient(normalized, bin_px)
        weight = np.abs(lsf)
        if reference_lsf_center is None:
            reference_lsf_center = float((centers * weight).sum()
                                         / max(weight.sum(), 1e-12))
        offset = centers - reference_lsf_center
        window = np.zeros_like(lsf)
        inside = np.abs(offset) <= lsf_halfwidth_px
        window[inside] = 0.5 * (
            1.0 + np.cos(np.pi * offset[inside] / lsf_halfwidth_px))
        windowed = lsf * window
        centroid = float((centers * np.abs(windowed)).sum()
                         / max(np.abs(windowed).sum(), 1e-12))

        spectrum = np.fft.rfft(windowed, n=padded)
        if abs(spectrum[0]) <= 0:
            continue
        mtf = np.abs(spectrum) / abs(spectrum[0])
        results[name] = ChannelResult(
            name=name, esf=normalized, lsf=windowed, mtf=mtf,
            edge_px=edge_px, centroid_px=centroid,
            rise_10_90_px=float(abs(rise)),
            mtf50_lp_per_mm=_mtf_crossing(frequencies, mtf, 0.5),
            mtf10_lp_per_mm=_mtf_crossing(frequencies, mtf, 0.1),
            contrast=contrast, spectrum=spectrum,
            plateau_slopes_per_px=slopes,
        )

    return EdgeResult(
        angle_deg=angle_deg, fit_rms_px=fit_rms, rows_used=used,
        samples=int(valid.sum()), bin_centers_px=centers,
        frequencies_lp_per_mm=frequencies, channels=results,
        note=("edge ESF along +x (a 'vertical' edge) or +y (a "
              "'horizontal' one, patch transposed)"),
    )


def band_samples(image: np.ndarray, slope: float, intercept: float,
                 y0: int, y1: int, halfwidth_px: float,
                 ) -> tuple[np.ndarray, np.ndarray]:
    """Samples in a narrow band around ``x = slope * y + intercept``.

    Returns (signed distance to the line in px, values).  A whole-image
    ``np.indices`` over a long slanted line would allocate the enclosing
    rectangle, most of which is off-band, so the band is walked row by
    row instead: a 24,000-px-long groove costs its own area, not its
    bounding box.
    """
    rows = np.arange(y0, y1, dtype=np.float64)
    half = int(np.ceil(halfwidth_px)) + 2
    normal = 1.0 / np.sqrt(1.0 + slope * slope)
    distances: list[np.ndarray] = []
    values: list[np.ndarray] = []
    height, width = image.shape[:2]
    offsets = np.arange(-half, half + 1, dtype=np.float64)
    for y in rows:
        center = slope * y + intercept
        base = int(np.floor(center))
        lo, hi = base - half, base + half + 1
        if lo < 0 or hi > width or not (0 <= y < height):
            continue
        distances.append((base + offsets - center) * normal)
        values.append(image[int(y), lo:hi])
    if not distances:
        return np.empty(0), np.empty(0)
    return np.concatenate(distances), np.concatenate(values).astype(np.float64)


def bin_profile(distance: np.ndarray, values: np.ndarray,
                halfwidth_px: float, bin_px: float
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bin (distance, value) samples into a super-resolved profile."""
    edges = np.arange(-halfwidth_px, halfwidth_px + bin_px, bin_px)
    which = np.digitize(distance, edges) - 1
    valid = (which >= 0) & (which < len(edges) - 1)
    which = which[valid]
    counts = np.bincount(which, minlength=len(edges) - 1).astype(np.float64)
    sums = np.bincount(which, weights=values[valid],
                       minlength=len(edges) - 1)
    occupied = counts > 0
    return ((edges[:-1] + bin_px / 2.0)[occupied],
            sums[occupied] / counts[occupied], counts[occupied])


def line_metrics(name: str, centers: np.ndarray, profile: np.ndarray,
                 *, scan_dpi: float, halfwidth_px: float,
                 pad_factor: int = 8,
                 polarity: float = 0.0) -> tuple[ChannelResult, np.ndarray]:
    """FWHM + windowed-FFT MTF of one super-resolved line profile."""
    baseline = float(np.median(np.concatenate([profile[:12], profile[-12:]])))
    signal = profile - baseline
    if polarity == 0.0:
        polarity = -1.0 if abs(signal.min()) >= abs(signal.max()) else 1.0
    signal = signal * polarity
    peak = float(signal.max())
    if peak <= 0:
        raise ValueError("line profile has no peak")
    normalized = signal / peak
    top = int(np.argmax(normalized))
    left = _crossing(centers[:top + 1], normalized[:top + 1], 0.5)
    right = -_crossing(-centers[top:][::-1], normalized[top:][::-1], 0.5)
    fwhm = (abs(right - left) if np.isfinite(left) and np.isfinite(right)
            else float("nan"))
    window = 0.5 * (1.0 + np.cos(np.pi * np.clip(
        centers / halfwidth_px, -1.0, 1.0)))
    windowed = signal * window
    padded = int(2 ** np.ceil(np.log2(max(64, len(centers) * pad_factor))))
    px_mm = UM_PER_INCH / scan_dpi / 1000.0
    frequencies = np.fft.rfftfreq(padded, d=float(np.diff(centers).min())
                                  * px_mm)
    spectrum = np.fft.rfft(windowed, n=padded)
    mtf = np.abs(spectrum) / abs(spectrum[0])
    return ChannelResult(
        name=name, esf=normalized, lsf=windowed, mtf=mtf,
        edge_px=float("nan"), spectrum=spectrum,
        centroid_px=float((centers * windowed).sum()
                          / max(windowed.sum(), 1e-12)),
        rise_10_90_px=float(fwhm),
        mtf50_lp_per_mm=_mtf_crossing(frequencies, mtf, 0.5),
        mtf10_lp_per_mm=_mtf_crossing(frequencies, mtf, 0.1),
        contrast=peak,
    ), frequencies


def px_to_dots(value_px: float, scan_dpi: float) -> float:
    """Scan pixels -> 600-dpi printer dots."""
    return value_px * PRINT_DPI / scan_dpi
