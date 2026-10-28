"""Numerical scorers for compact physical and scanner diagnostics."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage


def luma709(rgb: np.ndarray) -> np.ndarray:
    """Rec.709 linear luma — the one home for the 0.2126/0.7152/0.0722
    triple (density() folds it into optical density; raster.crop_luma is
    the capture-side reflectance variant)."""
    return (
        0.2126 * rgb[..., 0]
        + 0.7152 * rgb[..., 1]
        + 0.0722 * rgb[..., 2]
    )


def density(rgb: np.ndarray, plane: str) -> np.ndarray:
    """Return the declared plane's simple scanner-density feature."""
    reflectance = np.clip(np.asarray(rgb, np.float64), 1.0 / 65535.0, 1.0)
    values = -np.log10(reflectance)
    if plane == "C":
        return values[..., 0]
    if plane == "M":
        return values[..., 1]
    if plane == "Y":
        return values[..., 2]
    grey = luma709(reflectance)
    return -np.log10(np.clip(grey, 1.0 / 65535.0, 1.0))


def bounded_translation(truth: np.ndarray, measured: np.ndarray,
                        max_shift: int, *, search_x: bool = True,
                        search_y: bool = True
                        ) -> tuple[np.ndarray, np.ndarray, int, int, float]:
    """Maximize non-wrapped correlation over a small integer translation."""
    expected = np.asarray(truth).astype(bool)
    values = np.asarray(measured, dtype=np.float64)
    if expected.shape != values.shape or expected.ndim != 2:
        raise ValueError("truth and measured arrays must be matching 2-D data")
    height, width = expected.shape
    dxs = range(-max_shift, max_shift + 1) if search_x else (0,)
    dys = range(-max_shift, max_shift + 1) if search_y else (0,)
    candidates = sorted(
        ((dx, dy) for dy in dys for dx in dxs),
        key=lambda row: (
            row[0] * row[0] + row[1] * row[1],
            abs(row[1]), abs(row[0]), row[1], row[0],
        ),
    )
    best: tuple[float, int, int, np.ndarray, np.ndarray] | None = None
    for dx, dy in candidates:
        tx0, tx1 = max(0, -dx), min(width, width - dx)
        ty0, ty1 = max(0, -dy), min(height, height - dy)
        mx0, mx1 = tx0 + dx, tx1 + dx
        my0, my1 = ty0 + dy, ty1 + dy
        left = expected[ty0:ty1, tx0:tx1].ravel()
        right = values[my0:my1, mx0:mx1].ravel()
        if (
            len(left) < 32
            or np.all(left)
            or not np.any(left)
            or np.ptp(right) == 0.0
        ):
            continue
        corr = float(np.corrcoef(left.astype(float), right)[0, 1])
        if not np.isfinite(corr):
            continue
        if best is None or corr > best[0] + 1e-12:
            best = corr, dx, dy, left, right
    if best is None:
        return expected.ravel(), values.ravel(), 0, 0, float("nan")
    corr, dx, dy, left, right = best
    return left, right, dx, dy, corr


def pattern_score(truth: np.ndarray, measured_density: np.ndarray,
                  max_shift: int = 8, *, search_x: bool = True,
                  search_y: bool = True) -> dict[str, Any]:
    left, right, dx, dy, corr = bounded_translation(
        truth, measured_density, max_shift,
        search_x=search_x, search_y=search_y,
    )
    if not math.isfinite(corr):
        return {
            "scorable": False,
            "reason": "no-finite-pattern-correlation",
        }
    ink, paper = right[left], right[~left]
    if min(len(ink), len(paper)) == 0:
        return {"scorable": False}
    candidates = np.unique(np.concatenate([ink, paper]))
    if len(candidates) > 2048:
        candidates = np.quantile(candidates, np.linspace(0.0, 1.0, 2048))
    errors = np.array([
        np.count_nonzero(ink <= threshold)
        + np.count_nonzero(paper > threshold)
        for threshold in candidates
    ])
    threshold = float(candidates[int(np.argmin(errors))])
    predicted = right > threshold
    return {
        "scorable": True,
        "translation_source_dots": [dx, dy],
        "correlation": corr,
        "threshold": threshold,
        "ink_density_median": float(np.median(ink)),
        "paper_density_median": float(np.median(paper)),
        "density_separation": float(np.median(ink) - np.median(paper)),
        "dot_error_rate": float(np.mean(predicted != left)),
        "n_source_dots": int(len(left)),
    }


def blockiness(image: np.ndarray, block: int = 8) -> float | None:
    """Boundary/interior gradient ratio for JPEG-like blocking."""
    values = np.asarray(image, dtype=np.float64)
    if values.ndim == 3:
        values = values.mean(axis=2)
    if min(values.shape) < block * 3:
        return None
    gx = np.abs(np.diff(values, axis=1))
    gy = np.abs(np.diff(values, axis=0))
    boundary = np.concatenate([
        gx[:, block - 1::block].ravel(),
        gy[block - 1::block, :].ravel(),
    ])
    inside_x = np.ones(gx.shape[1], bool)
    inside_x[block - 1::block] = False
    inside_y = np.ones(gy.shape[0], bool)
    inside_y[block - 1::block] = False
    interior = np.concatenate([gx[:, inside_x].ravel(), gy[inside_y, :].ravel()])
    return float(np.mean(boundary) / max(float(np.mean(interior)), 1e-12))


def highpass_noise(image: np.ndarray) -> float:
    values = np.asarray(image, dtype=np.float64)
    if values.ndim == 3:
        values = values.mean(axis=2)
    if min(values.shape) < 3:
        return 0.0
    smooth = (
        values[:-2, :-2] + values[:-2, 1:-1] + values[:-2, 2:]
        + values[1:-1, :-2] + values[1:-1, 1:-1] + values[1:-1, 2:]
        + values[2:, :-2] + values[2:, 1:-1] + values[2:, 2:]
    ) / 9.0
    return float(np.std(values[1:-1, 1:-1] - smooth))


def screen_fingerprint(
    image: np.ndarray,
    authored: np.ndarray,
    scan_dpi_x: float,
    scan_dpi_y: float,
    *,
    low_lpi: float = 30.0,
    high_lpi: float = 300.0,
    radial_bin_lpi: float = 8.0,
) -> dict[str, Any]:
    """Compare observed power with the exact authored PRN spectrum.

    A robust radial transfer fit absorbs ordinary resolution falloff.  The
    remaining positive spectral energy is descriptive evidence of structure
    that was not present in the authored PRN field; it is not, by itself, a
    claim about a printer's universal screen.
    """

    values = np.asarray(image, dtype=np.float64)
    truth = np.asarray(authored, dtype=np.float64)
    if values.ndim == 3:
        values = density(values, "K")
    if values.ndim != 2 or truth.ndim != 2 or values.shape != truth.shape:
        return {
            "resolved": False,
            "reason": "observed-and-authored-shapes-differ",
        }
    height, width = values.shape
    if min(height, width) < 64:
        return {"resolved": False, "reason": "crop-too-small"}
    if (
        not np.all(np.isfinite(values))
        or not np.all(np.isfinite(truth))
        or np.ptp(values) <= 1e-9
        or np.ptp(truth) <= 0.0
    ):
        return {
            "resolved": False,
            "reason": "insufficient-finite-pattern-contrast",
        }

    window = np.hanning(height)[:, None] * np.hanning(width)[None, :]

    def power_spectrum(array: np.ndarray) -> np.ndarray:
        centered = array - float(np.mean(array))
        transform = np.fft.fftshift(np.fft.fft2(centered * window))
        return np.abs(transform) ** 2

    observed_power = power_spectrum(values)
    authored_power = power_spectrum(truth)
    fy = np.fft.fftshift(np.fft.fftfreq(height)) * scan_dpi_y
    fx = np.fft.fftshift(np.fft.fftfreq(width)) * scan_dpi_x
    frequency_y, frequency_x = np.meshgrid(fy, fx, indexing="ij")
    radius = np.hypot(frequency_x, frequency_y)
    angle = np.degrees(np.arctan2(frequency_y, frequency_x))
    upper = min(
        float(high_lpi),
        0.90 * 0.5 * min(float(scan_dpi_x), float(scan_dpi_y)),
    )
    search = (radius >= float(low_lpi)) & (radius <= upper)
    if upper <= low_lpi or not np.any(search):
        return {"resolved": False, "reason": "no-search-bins"}

    authored_search = authored_power[search]
    observed_search = observed_power[search]
    authored_floor = max(
        float(np.percentile(authored_search, 10.0)),
        float(np.mean(authored_search)) * 1e-6,
        1e-18,
    )
    stabilized_authored = np.maximum(authored_power, authored_floor)
    radial_index = np.floor(
        (radius - float(low_lpi)) / float(radial_bin_lpi)
    ).astype(np.int64)
    predicted_power = np.zeros_like(observed_power)
    fitted_bins = 0
    for index in np.unique(radial_index[search]):
        band = search & (radial_index == index)
        ratios = observed_power[band] / stabilized_authored[band]
        finite = ratios[np.isfinite(ratios)]
        if not len(finite):
            continue
        scale = max(float(np.median(finite)), 0.0)
        predicted_power[band] = stabilized_authored[band] * scale
        fitted_bins += 1
    fitted = search & (predicted_power > 0.0)
    if not np.any(fitted):
        return {"resolved": False, "reason": "radial-transfer-fit-failed"}

    excess = np.maximum(observed_power - predicted_power, 0.0)
    observed_total = max(float(np.sum(observed_power[fitted])), 1e-18)
    excess_fraction = float(np.sum(excess[fitted]) / observed_total)
    ratio = np.zeros_like(observed_power)
    ratio[fitted] = (
        observed_power[fitted]
        / np.maximum(predicted_power[fitted], 1e-18)
    )
    masked_ratio = np.where(fitted, ratio, -np.inf)
    peak_y, peak_x = np.unravel_index(
        int(np.argmax(masked_ratio)), masked_ratio.shape
    )

    authored_log = np.log1p(
        stabilized_authored[fitted] / authored_floor
    )
    observed_floor = max(
        float(np.percentile(observed_power[fitted], 10.0)),
        float(np.mean(observed_power[fitted])) * 1e-6,
        1e-18,
    )
    observed_log = np.log1p(
        observed_power[fitted] / observed_floor
    )
    correlation = (
        float(np.corrcoef(authored_log, observed_log)[0, 1])
        if (
            np.ptp(authored_log) > 0.0
            and np.ptp(observed_log) > 0.0
        )
        else None
    )
    if correlation is not None and not math.isfinite(correlation):
        correlation = None

    return {
        "resolved": True,
        "method": "authored-prn-radial-transfer-residual-v1",
        "frequency_range_lpi": [float(low_lpi), upper],
        "radial_bin_lpi": float(radial_bin_lpi),
        "n_frequency_bins": int(np.count_nonzero(fitted)),
        "n_radial_transfer_bins": fitted_bins,
        "authored_observed_log_power_correlation": correlation,
        "off_ground_truth_excess_energy_fraction": excess_fraction,
        "strongest_off_ground_truth_artifact": {
            "lpi": float(radius[peak_y, peak_x]),
            "angle_deg": float(angle[peak_y, peak_x] % 180.0),
            "observed_to_authored_transfer_ratio": float(
                ratio[peak_y, peak_x]
            ),
        },
        "interpretation": (
            "descriptive residual against this exact authored PRN field; "
            "not a universal printer-screen verdict"
        ),
    }


def slanted_edge_mtf50(image: np.ndarray, scan_dpi_x: float,
                       scan_dpi_y: float, angle_deg: float) -> dict[str, Any]:
    """Known-angle oversampled ESF/LSF estimate in cycles/mm."""
    values = np.asarray(image, dtype=np.float64)
    if values.ndim == 3:
        values = density(values, "K")
    height, width = values.shape
    if min(height, width) < 32:
        return {"resolved": False, "reason": "crop-too-small"}
    yy, xx = np.indices(values.shape, dtype=np.float64)
    x_mm = (xx - (width - 1) / 2.0) * 25.4 / scan_dpi_x
    y_mm = (yy - (height - 1) / 2.0) * 25.4 / scan_dpi_y
    angle = math.radians(angle_deg)
    distance = x_mm * math.cos(angle) + y_mm * math.sin(angle)
    bin_mm = min(25.4 / scan_dpi_x, 25.4 / scan_dpi_y) / 4.0
    lo, hi = np.percentile(distance, (5.0, 95.0))
    edges = np.arange(lo, hi + bin_mm, bin_mm)
    which = np.digitize(distance.ravel(), edges) - 1
    valid = (which >= 0) & (which < len(edges) - 1)
    counts = np.bincount(which[valid], minlength=len(edges) - 1)
    sums = np.bincount(
        which[valid], weights=values.ravel()[valid],
        minlength=len(edges) - 1,
    )
    usable = counts > 0
    esf = sums[usable] / counts[usable]
    if len(esf) < 32 or np.ptp(esf) < 0.01:
        return {"resolved": False, "reason": "insufficient-edge-contrast"}
    lsf = np.diff(esf)
    lsf *= np.hanning(len(lsf))
    mtf = np.abs(np.fft.rfft(lsf))
    if mtf[0] <= 0:
        return {"resolved": False, "reason": "zero-lsf"}
    mtf /= mtf[0]
    freq = np.fft.rfftfreq(len(lsf), d=bin_mm)
    below = np.flatnonzero(mtf <= 0.5)
    if not len(below):
        return {
            "resolved": False,
            "reason": "mtf50-above-sampled-band",
            "nyquist_cycles_per_mm": float(freq[-1]),
        }
    index = int(below[0])
    if index == 0:
        mtf50 = float(freq[0])
    else:
        x0, x1 = float(freq[index - 1]), float(freq[index])
        y0, y1 = float(mtf[index - 1]), float(mtf[index])
        denominator = y1 - y0
        if abs(denominator) < 1e-12:
            mtf50 = x1
        else:
            mtf50 = x0 + (0.5 - y0) * (x1 - x0) / denominator
    # Overshoot (W10, e031): a sharpening halo is a sustained near-edge
    # excursion BEYOND anything the plateau itself does.  Print physics
    # cannot make paper brighter than paper; on the ink side the same
    # argument only holds once toner mottle is accounted for — in density
    # space the log amplifies solid-side texture, and comparing a raw ESF
    # max against the plateau MEDIAN reads that mottle as 5-7% "overshoot"
    # on clean captures (measured through the pipeline on both real B/W
    # sheets).  So: smooth the ESF over 5 bins (kills single-bin spikes,
    # preserves 10+-bin halos), take each plateau's own 1st/99th-percentile
    # ENVELOPE as the reference, and search only the near-edge band between
    # the plateaus.  Mottle is stationary along the edge, so it raises the
    # envelope and the near-edge extremum together and cancels; a halo does
    # not.
    kernel = min(5, max(1, len(esf) // 8) | 1)
    smooth = ndimage.median_filter(esf, size=kernel, mode="nearest")
    quarter = max(4, len(smooth) // 4)
    side_a = smooth[:quarter]
    side_b = smooth[-quarter:]
    middle = smooth[quarter:-quarter]
    if float(np.median(side_a)) <= float(np.median(side_b)):
        low_side, high_side = side_a, side_b
    else:
        low_side, high_side = side_b, side_a
    low_plateau = float(np.median(low_side))
    high_plateau = float(np.median(high_side))
    span = high_plateau - low_plateau
    if span > 0 and middle.size:
        low_envelope = float(np.percentile(low_side, 1))
        high_envelope = float(np.percentile(high_side, 99))
        overshoot_low = max(
            0.0, (low_envelope - float(middle.min())) / span
        )
        overshoot_high = max(
            0.0, (float(middle.max()) - high_envelope) / span
        )
    else:
        overshoot_low = overshoot_high = 0.0
    return {
        "resolved": True,
        "mtf50_cycles_per_mm": mtf50,
        "mtf50_lpi": mtf50 * 25.4,
        "nyquist_cycles_per_mm": float(freq[-1]),
        "edge_contrast_density": float(np.ptp(esf)),
        "overshoot_low_fraction": overshoot_low,
        "overshoot_high_fraction": overshoot_high,
        "overshoot_fraction": max(overshoot_low, overshoot_high),
    }


def blockiness_comb(
    image: np.ndarray, periods: tuple[int, ...] = (8, 16, 24, 32, 48, 64),
) -> dict[str, Any] | None:
    """Phase-invariant periodic-seam detector for block compression.

    W10 (e031).  The fixed :func:`blockiness` check assumes JPEG applied at
    the DELIVERED resolution with 8-px blocks on the crop's own grid.  A
    scanner that compresses internally at a lower resolution and
    interpolates up delivers seams at 16/32/64 px, at an arbitrary phase —
    invisible to the aligned 8-px check.  Here the per-column (and per-row)
    mean absolute gradients are folded modulo each candidate period; a seam
    at ANY phase concentrates in one fold.  Statistic per period is
    max(fold) / median(fold): ~1 on clean captures, elevated when a comb is
    present.  Meaningful only on UNPRINTED regions — authored content is
    grid-locked and would comb by construction.
    """
    values = np.asarray(image, dtype=np.float64)
    if values.ndim == 3:
        values = values.mean(axis=2)
    if min(values.shape) < 3 * max(periods):
        return None
    profile_x = np.abs(np.diff(values, axis=1)).mean(axis=0)
    profile_y = np.abs(np.diff(values, axis=0)).mean(axis=1)
    out: dict[str, float] = {}
    for period in periods:
        worst = 0.0
        for profile in (profile_x, profile_y):
            usable = (len(profile) // period) * period
            if usable < 3 * period:
                continue
            folds = profile[:usable].reshape(-1, period).mean(axis=0)
            median = float(np.median(folds))
            if median <= 0.0:
                continue
            worst = max(worst, float(folds.max()) / median)
        if worst > 0.0:
            out[str(period)] = worst
    if not out:
        return None
    max_period = max(out, key=out.get)
    return {
        "periods": out,
        "max": out[max_period],
        "max_period_px": int(max_period),
    }


def level_occupancy(image: np.ndarray, *, levels: int = 255) -> dict[str, Any]:
    """Quantisation forensics on the digitised levels of a quiet region.

    JPEG level clustering, bit-depth reduction and posterisation all leave
    UNOCCUPIED levels inside an otherwise continuous span.  A clean capture
    of paper occupies every level between its extremes.  Blind to smoothing,
    so this complements :func:`spectral_signature` rather than replacing it.
    """
    values = np.asarray(image, dtype=np.float64)
    if values.ndim == 3:
        values = values.mean(axis=2)
    counts_index = np.rint(values * float(levels)).astype(np.int64)
    low = int(counts_index.min())
    high = int(counts_index.max())
    span = high - low + 1
    histogram = np.bincount((counts_index - low).ravel(), minlength=span)
    occupied = int((histogram > 0).sum())
    interior_gaps = int((histogram == 0).sum())
    total = float(histogram.sum())
    probability = histogram[histogram > 0] / total
    entropy = float(-(probability * np.log2(probability)).sum())
    return {
        "level_low": low,
        "level_high": high,
        "level_span": int(span),
        "levels_occupied": occupied,
        "interior_gaps": interior_gaps,
        "occupancy_fraction": float(occupied / span) if span else None,
        "entropy_bits_per_pixel": entropy,
        "n_samples": int(total),
    }
