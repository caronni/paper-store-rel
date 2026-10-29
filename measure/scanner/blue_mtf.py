"""Blue-channel scanner characterization from the EXISTING e028 scans.

docs/INDEPENDENT-PLANES.md §4.I item 3 / §6 P2: e028 measured the Canon
LiDE 400's LUMA MTF from a knife edge (glass-level MTF10 ~ 17 lp/mm) and
e033 found an R-G lateral CA, but the BLUE channel — where the Y plane
is read — was never characterized.  Y reads "optically soft" on sheet I
(pixel correlation 0.57 vs C 0.77).  This instrument splits *scanner blue
optics* from *toner scatter* using archived captures only.

THE ARGUMENT, in three steps:

1. **Absolute anchor (luma, glass level).**  ``--knife`` re-derives 028.4
   from `canon-4800-knife-edge-20260804-gray.tiff`.  That scan is single
   channel, so it can anchor luma and nothing else.
2. **Per-channel differentials (paper level).**  ``--color`` reads K-toner
   targets on the e028 colour discovery sheet, captured RGB at 4800 dpi.
   K toner presents the SAME physical edge to R, G and B, so in a channel
   RATIO every print-side term — toner scatter, paper light-spread,
   development raggedness — cancels, and what survives is scanner-side:
   ``dsigma2 = sigma_c^2 - sigma_G^2`` and the lateral shift.  This is why
   a printed target can answer a scanner question.
3. **Composition.**  sigma_B = sqrt(sigma_luma^2 + dsigma2_B), with the
   luma sigma from step 1.

What this CANNOT do: measure the absolute blue MTF at the glass plane
(no colour knife-edge capture exists), or separate a per-channel focus
difference at the paper plane from one at the glass plane.

Run (no hardware, read-only on every scan):

    cd <repo>
    PYTHONPATH=measure env/bin/python -m scanner.blue_mtf --all \\
        --evidence-root <evidence> --out build/scanner

Historical record of the P2 scanner characterization (2026-08); the
e028 captures (``KNIFE``/``COLOR`` paths, relative to ``--evidence-root``,
sha256-pinned) are in the evidence archive.  Outputs land in ``--out``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import tifffile

import _evidence

from . import _edge
from ._edge import (UM_PER_INCH, ChannelResult, EdgeResult,
                    analyze_edge, band_samples, bin_profile,
                    compare_channels, line_metrics, linearize_srgb)

#: Capture paths are RELATIVE to ``--evidence-root``, the published
#: archive root (``measure/_evidence.py``).
KNIFE = {
    "path": Path("paper-store-evidence-holo-2026-10/028-discovery-m281/"
                 "knife-edge/captures/knife-edge-canon-4800grey.tiff"),
    "sha256": "58a3ceb1e52b984315db435e9b65dbc0e921cd5ce90acb8b5e0088ce3f32e058",
    "dpi": 4800.0,
    "record": "experiments/028-discovery-m281.md 028.4",
}
COLOR = {
    "path": Path("paper-store-evidence-holo-2026-10/028-discovery-m281/"
                 "discovery/captures/discovery-color-canon-4800rgb.tiff"),
    "sha256": "d0f12451dfc16d06ce904a2bad324e7d1f2b30d6096d558168d1064bdc7aeb8d",
    "dpi": 4800.0,
    "record": "experiments/028-discovery-m281.md capture 028.1b",
}
LUMA_601 = np.array([0.299, 0.587, 0.114])

# --- e028 colour sheet: K-toner targets, located once and pinned here. ---
# tone/K/1.0 (the layout's only large solid-K area: 8 x 5 mm at x_mm 88,
# y_mm 207) and the two HCAL-R1 strip frames (long thin solid-K rules).
TONE_K_SOLID = {"x0": 16558, "x1": 18060, "y0": 38836, "y1": 39766}
STRIP_EDGES = (
    # name, seed row, falling (white->black going down), x span
    ("strip-top/outer-top", 2330, True, (11200, 27800)),
    ("strip-top/outer-bottom", 2790, False, (11200, 27800)),
    ("strip-bottom/outer-top", 52670, True, (11200, 27800)),
    ("strip-bottom/outer-bottom", 53105, False, (11200, 27800)),
)
# registration/<target>/K crosses: 3 x 3 platen positions, stroke 2 dots.
CROSS_X_SEEDS = (6630, 17968, 29306)
CROSS_Y_SEEDS = (31440, 33896, 36352)


def sha256_of(path: Path, chunk: int = 1 << 24) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# 1. luma anchor: the e028 knife edge
# --------------------------------------------------------------------------

def _blade_axis(image: np.ndarray, decimate: int = 8,
                threshold: int = 115) -> float:
    small = image[::decimate, ::decimate]
    ys, xs = np.nonzero(small < threshold)
    centred = np.stack([xs - xs.mean(), ys - ys.mean()]).astype(np.float64)
    covariance = centred @ centred.T / centred.shape[1]
    values, vectors = np.linalg.eigh(covariance)
    axis = vectors[:, int(np.argmax(values))]
    return float(np.degrees(np.arctan2(axis[1], axis[0])))


def _groove_slope_and_positions(image: np.ndarray, decimate: int = 2,
                                threshold: int = 115
                                ) -> tuple[float, list[float], np.ndarray]:
    """Slope and offsets of the snap-score grooves, by shear projection.

    The grooves are the only in-focus, in-contact (flush-face) targets on
    the blade — 028.4's own corrected reading, after the spine-side cast
    shadow and the cutting-side grind were disqualified.
    """
    small = image[::decimate, ::decimate].astype(np.float32)
    mask = small < threshold
    for _ in range(24):                     # erode off the edges and taper
        mask[1:-1, 1:-1] &= (mask[:-2, 1:-1] & mask[2:, 1:-1]
                             & mask[1:-1, :-2] & mask[1:-1, 2:])
    yy, xx = np.indices(small.shape, dtype=np.float32)
    values = small[mask]
    ys, xs = yy[mask], xx[mask]

    def project(slope: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        distance = xs - slope * ys
        edges = np.arange(distance.min(), distance.max() + 2, 2.0)
        which = np.digitize(distance, edges) - 1
        inside = (which >= 0) & (which < len(edges) - 1)
        which = which[inside]
        counts = np.bincount(which, minlength=len(edges) - 1)
        sums = np.bincount(which, weights=values[inside],
                           minlength=len(edges) - 1)
        keep = counts > 300
        return ((edges[:-1] + 1.0)[keep], sums[keep] / counts[keep],
                counts[keep])

    best: tuple[float, float] | None = None
    for slope in np.arange(-2.2, -1.4, 0.01):
        centres, profile, _ = project(float(slope))
        if len(profile) < 200:
            continue
        detrended = (profile - np.convolve(profile, np.ones(31) / 31,
                                           mode="same"))[31:-31]
        spread = float(np.median(np.abs(detrended - np.median(detrended))))
        if spread <= 0:
            continue
        score = float(-detrended.min() / spread)
        if best is None or score > best[1]:
            best = (float(slope), score)
    assert best is not None
    slope = best[0]
    centres, profile, _ = project(slope)
    detrended = profile - np.convolve(profile, np.ones(31) / 31, mode="same")
    offsets: list[float] = []
    for i in range(31, len(detrended) - 31):
        if detrended[i] < -8.0 and detrended[i] == detrended[i - 8:i + 9].min():
            offsets.append(float(centres[i]) * decimate)
    return slope, offsets, mask


def measure_knife(scan_dpi: float, evidence_root: Path,
                  verbose: bool = True) -> dict[str, Any]:
    image = tifffile.imread(evidence_root / KNIFE["path"])
    height, width = image.shape
    axis_deg = _blade_axis(image)
    slope, offsets, mask = _groove_slope_and_positions(image)
    mask_decimate = 2
    rows: list[dict[str, Any]] = []
    for offset in offsets:
        candidates = np.arange(100, height - 100, 8)
        columns = offset + slope * candidates
        inside = (columns > 200) & (columns < width - 200)
        candidates, columns = candidates[inside], columns[inside]
        good = [int(y) for y, x in zip(candidates, columns)
                if _mask_clear(mask, y // mask_decimate, x // mask_decimate)]
        if len(good) < 50:      # candidates are sampled every 8 rows
            continue
        distance, values = band_samples(image, slope, offset,
                                        good[0], good[-1], 24.0)
        if not distance.size:
            continue
        centres, profile, counts = bin_profile(
            distance, linearize_srgb(values), 24.0, 0.25)
        result, frequencies = line_metrics(
            "luma", centres, profile, scan_dpi=scan_dpi, halfwidth_px=24.0)
        keep = frequencies <= 30.0
        frequency_axis = frequencies[keep].tolist()
        rows.append({
            "offset_px": offset,
            "rows_used": good[-1] - good[0],
            "samples": int(distance.size),
            "min_bin_count": int(counts.min()),
            "fwhm_px": result.rise_10_90_px,
            "fwhm_um": result.rise_10_90_px * UM_PER_INCH / scan_dpi,
            "mtf50_lp_per_mm": result.mtf50_lp_per_mm,
            "mtf10_lp_per_mm": result.mtf10_lp_per_mm,
            "peak_linear": result.contrast,
            "mtf": result.mtf[keep].tolist(),
        })
        if verbose:
            print(f"  groove @{offset:8.0f}  FWHM {rows[-1]['fwhm_um']:5.1f} um"
                  f"  MTF50 {result.mtf50_lp_per_mm:5.2f}"
                  f"  MTF10 {result.mtf10_lp_per_mm:5.2f} lp/mm")
    if not rows:
        raise RuntimeError("no usable snap-score groove found")
    narrowest = min(rows, key=lambda row: row["fwhm_px"])
    fwhm = np.array([row["fwhm_px"] for row in rows])
    return {
        "scan": str(evidence_root / KNIFE["path"]),
        "sha256": KNIFE["sha256"],
        "record": KNIFE["record"],
        "scan_dpi": scan_dpi,
        "shape": [int(height), int(width)],
        "channels": 1,
        "blade_axis_deg": axis_deg,
        "groove_slope_dx_dy": slope,
        "grooves": rows,
        "narrowest": {k: v for k, v in narrowest.items() if k != "mtf"},
        "fwhm_px_median": float(np.median(fwhm)),
        "frequencies_lp_per_mm": frequency_axis,
        "target_note": (
            "snap-score groove = a LINE, so its FWHM is an UPPER bound on "
            "the LSF and its MTF a LOWER bound; 028.4 reads the narrowest "
            "groove for exactly this reason"),
    }


def _mask_clear(mask: np.ndarray, y: float, x: float, margin: int = 12) -> bool:
    y, x = int(y), int(x)
    if not (margin <= y < mask.shape[0] - margin
            and margin <= x < mask.shape[1] - margin):
        return False
    return bool(mask[y - margin:y + margin, x - margin:x + margin].all())


# --------------------------------------------------------------------------
# 2. per-channel differentials on K-toner targets in the RGB capture
# --------------------------------------------------------------------------

@dataclass
class Measurement:
    target: str
    family: str
    axis: str                 # "x" (sensor) or "y" (transport)
    x_px: float
    y_px: float
    angle_deg: float
    channels: dict[str, dict[str, Any]]
    differentials: dict[str, dict[str, float]]
    polarity: str = "line"    # "falling" | "rising" | "line"

    def as_json(self) -> dict[str, Any]:
        return {
            "target": self.target, "family": self.family, "axis": self.axis,
            "polarity": self.polarity,
            "x_px": self.x_px, "y_px": self.y_px,
            "x_mm": self.x_px * UM_PER_INCH / 4800.0 / 1000.0,
            "y_mm": self.y_px * UM_PER_INCH / 4800.0 / 1000.0,
            "angle_deg": self.angle_deg,
            "channels": self.channels,
            "differentials": self.differentials,
        }


def _locate_edge(image, y_lo: int, y_hi: int, x0: int, x1: int,
                 falling: bool) -> int:
    profile = np.asarray(image[y_lo:y_hi, x0:x1:16, :]).mean(axis=(1, 2))
    gradient = np.diff(profile)
    index = int(np.argmin(gradient) if falling else np.argmax(gradient))
    return y_lo + index


def _locate_dark_column(image, y0: int, y1: int, x_lo: int, x_hi: int) -> int:
    profile = np.asarray(image[y0:y1:8, x_lo:x_hi, :]).mean(axis=(0, 2))
    return x_lo + int(np.argmin(profile))


def _locate_dark_row(image, y_lo: int, y_hi: int, x0: int, x1: int) -> int:
    profile = np.asarray(image[y_lo:y_hi, x0:x1:8, :]).mean(axis=(1, 2))
    return y_lo + int(np.argmin(profile))


def _edge_measurement(patch: np.ndarray, *, target: str, family: str,
                      orientation: str, x_px: float, y_px: float,
                      scan_dpi: float, halfwidth_px: float,
                      mtf_floor: float, f_min: float, polarity: str
                      ) -> tuple[Measurement, EdgeResult]:
    result = analyze_edge(
        patch, scan_dpi=scan_dpi, orientation=orientation,
        lsf_halfwidth_px=halfwidth_px,
        extra_channels={"luma601": LUMA_601})
    differentials = compare_channels(
        result, reference="G", scan_dpi=scan_dpi,
        mtf_floor=mtf_floor, f_min_lp_per_mm=f_min)
    return Measurement(
        target=target, family=family,
        axis="x" if orientation == "vertical" else "y", polarity=polarity,
        x_px=x_px, y_px=y_px, angle_deg=result.angle_deg,
        channels={name: channel.summary(scan_dpi)
                  for name, channel in result.channels.items()},
        differentials=differentials,
    ), result


def _line_result(patch: np.ndarray, *, scan_dpi: float, orientation: str,
                 halfwidth_px: float, slope_span: float = 0.02,
                 slope_step: float = 0.0005) -> EdgeResult:
    """Per-channel super-resolved profile of a thin dark BAR.

    Same ratio logic as an edge: the bar's own (unknown) width is
    channel-common and divides out, so ``compare_channels`` is valid on
    a line target even though its absolute MTF is not the scanner's.
    """
    data = np.asarray(patch)
    if orientation == "horizontal":
        data = np.transpose(data, (1, 0, 2))
    values = linearize_srgb(data)
    reference = values.mean(axis=2)
    rows, columns = reference.shape
    best: tuple[float, float, float] | None = None
    for slope in np.arange(-slope_span, slope_span + slope_step / 2,
                           slope_step):
        intercept = columns / 2.0 - slope * (rows - 1) / 2.0
        distance, sample = band_samples(reference, float(slope), intercept,
                                        0, rows, halfwidth_px)
        if not distance.size:
            continue
        centres, profile, _ = bin_profile(distance, sample,
                                          halfwidth_px, 0.25)
        depth = float(np.median(profile[:8]) + np.median(profile[-8:])) / 2.0
        score = depth - float(profile.min())
        if best is None or score > best[2]:
            best = (float(slope), float(centres[int(np.argmin(profile))]),
                    score)
    assert best is not None
    slope, offset, _ = best
    intercept = columns / 2.0 - slope * (rows - 1) / 2.0 + offset
    channels: dict[str, ChannelResult] = {}
    frequencies = np.zeros(0)
    centres = np.zeros(0)
    planes = {"R": values[:, :, 0], "G": values[:, :, 1], "B": values[:, :, 2],
              "luma601": np.tensordot(values, LUMA_601, axes=([2], [0]))}
    polarity = 0.0
    for name, plane in planes.items():
        distance, sample = band_samples(plane, slope, intercept, 0, rows,
                                        halfwidth_px)
        centres, profile, _ = bin_profile(distance, sample, halfwidth_px, 0.25)
        channel, frequencies = line_metrics(
            name, centres, profile, scan_dpi=scan_dpi,
            halfwidth_px=halfwidth_px, polarity=polarity)
        polarity = -1.0
        channels[name] = channel
    return EdgeResult(
        angle_deg=float(np.degrees(np.arctan(slope))), fit_rms_px=float("nan"),
        rows_used=rows, samples=rows * columns,
        frequencies_lp_per_mm=frequencies, bin_centers_px=centres,
        channels=channels, note="line target (bar width divides out)")


def measure_color(scan_dpi: float, evidence_root: Path, segments: int = 8,
                  verbose: bool = True) -> dict[str, Any]:
    image = tifffile.memmap(evidence_root / COLOR["path"], mode="r")
    height, width, _ = image.shape
    measurements: list[Measurement] = []
    curves: dict[str, dict[str, list[float]]] = {}

    # (a) the solid K patch: the only target with room for a wide LSF
    #     window, so the only one whose ABSOLUTE MTF is trustworthy.
    patch = TONE_K_SOLID
    plans = (
        ("toneK/left", "vertical", "falling",
         (patch["y0"] + 60, patch["y1"] - 60,
          patch["x0"] - 150, patch["x0"] + 150)),
        ("toneK/right", "vertical", "rising",
         (patch["y0"] + 60, patch["y1"] - 60,
          patch["x1"] - 150, patch["x1"] + 150)),
        ("toneK/top", "horizontal", "falling",
         (patch["y0"] - 150, patch["y0"] + 150,
          patch["x0"] + 100, patch["x1"] - 100)),
        ("toneK/bottom", "horizontal", "rising",
         (patch["y1"] - 150, patch["y1"] + 150,
          patch["x0"] + 100, patch["x1"] - 100)),
    )
    for name, orientation, polarity, (y0, y1, x0, x1) in plans:
        crop = np.asarray(image[y0:y1, x0:x1, :])
        measurement, result = _edge_measurement(
            crop, target=name, family="solid-K-edge", orientation=orientation,
            x_px=(x0 + x1) / 2.0, y_px=(y0 + y1) / 2.0, scan_dpi=scan_dpi,
            halfwidth_px=80.0, mtf_floor=0.25, f_min=1.0, polarity=polarity)
        measurements.append(measurement)
        curves[name] = {
            "frequencies_lp_per_mm": result.frequencies_lp_per_mm[
                result.frequencies_lp_per_mm <= 12.0].tolist(),
            **{channel: result.channels[channel].mtf[
                result.frequencies_lp_per_mm <= 12.0].tolist()
               for channel in ("R", "G", "B", "luma601")},
        }
        if verbose:
            _print_measurement(measurement)

    # (b) the two HCAL-R1 strip frames: long rules, segmented along x, so
    #     the y-axis differentials get a platen-position series.  The rule
    #     is ~37 px thick, so the LSF window has to be tight — absolute
    #     MTF here is window-truncated, the RATIOS are not.
    for name, seed, falling, (x_lo, x_hi) in STRIP_EDGES:
        span = (x_hi - x_lo) // segments
        for index in range(segments):
            x0 = x_lo + index * span
            row = _locate_edge(image, seed - 70, seed + 70, x0, x0 + span,
                               falling)
            crop = np.asarray(image[row - 26:row + 26, x0:x0 + span, :])
            measurement, _ = _edge_measurement(
                crop, target=f"{name}#{index}", family="strip-rule-edge",
                orientation="horizontal", x_px=x0 + span / 2.0, y_px=row,
                scan_dpi=scan_dpi, halfwidth_px=18.0,
                mtf_floor=0.35, f_min=1.0,
                polarity="falling" if falling else "rising")
            measurements.append(measurement)
        if verbose:
            _print_family(measurements, f"{name}#")

    # (c) the K registration crosses: 3 x 3 platen positions, one vertical
    #     and one horizontal 2-dot bar each -> both axes, nine positions.
    for row_index, y_seed in enumerate(CROSS_Y_SEEDS):
        for column_index, x_seed in enumerate(CROSS_X_SEEDS):
            column = _locate_dark_column(image, y_seed - 400, y_seed + 400,
                                         x_seed - 160, x_seed + 160)
            row = _locate_dark_row(image, y_seed - 500, y_seed + 500,
                                   column - 260, column - 60)
            for axis, orientation, crop_box in (
                ("x", "vertical", (row - 480, row - 60,
                                   column - 45, column + 45)),
                ("y", "horizontal", (row - 45, row + 45,
                                     column + 60, column + 330)),
            ):
                y0, y1, x0, x1 = crop_box
                crop = np.asarray(image[y0:y1, x0:x1, :])
                result = _line_result(crop, scan_dpi=scan_dpi,
                                      orientation=orientation,
                                      halfwidth_px=26.0)
                differentials = compare_channels(
                    result, reference="G", scan_dpi=scan_dpi,
                    mtf_floor=0.35, f_min_lp_per_mm=1.0)
                measurements.append(Measurement(
                    target=f"crossK/r{row_index}c{column_index}/{axis}",
                    family="cross-bar", axis=axis,
                    x_px=float(column), y_px=float(row),
                    angle_deg=result.angle_deg,
                    channels={n: c.summary(scan_dpi)
                              for n, c in result.channels.items()},
                    differentials=differentials))
    if verbose:
        _print_family(measurements, "crossK/")
    del image
    return {
        "scan": str(evidence_root / COLOR["path"]),
        "sha256": COLOR["sha256"],
        "record": COLOR["record"],
        "scan_dpi": scan_dpi,
        "shape": [int(height), int(width)],
        "channels": 3,
        "measurements": [m.as_json() for m in measurements],
        "mtf_curves": curves,
    }


def _print_measurement(measurement: Measurement) -> None:
    print(f"  {measurement.target:28s} axis {measurement.axis} "
          f"angle {measurement.angle_deg:+.3f}")
    for name in ("R", "G", "B", "luma601"):
        channel = measurement.channels.get(name)
        if not channel:
            continue
        differential = measurement.differentials.get(name, {})
        print(f"     {name:8s} MTF50 {channel['mtf50_lp_per_mm']:6.2f} "
              f"MTF10 {channel['mtf10_lp_per_mm']:6.2f} "
              f"rise {channel['rise_10_90_um']:6.1f} um "
              f"dsigma {differential.get('dsigma_um', float('nan')):+7.2f} um "
              f"shift {differential.get('shift_dots', float('nan')):+7.4f} dot")


def _print_family(measurements: list[Measurement], prefix: str) -> None:
    rows = [m for m in measurements if m.target.startswith(prefix)]
    if not rows:
        return
    for name in ("R", "B"):
        shifts = np.array([m.differentials.get(name, {}).get("shift_dots",
                                                             np.nan)
                           for m in rows], dtype=float)
        sigmas = np.array([m.differentials.get(name, {}).get("dsigma2_um2",
                                                            np.nan)
                           for m in rows], dtype=float)
        print(f"  {prefix:26s} {name}-G  n={np.isfinite(shifts).sum():3d}  "
              f"shift {np.nanmean(shifts):+7.4f} +- "
              f"{np.nanstd(shifts) / max(np.sqrt(np.isfinite(shifts).sum()), 1):.4f} dot"
              f"   dsigma2 {np.nanmean(sigmas):+8.1f} um^2")


# --------------------------------------------------------------------------
# 3. the OTHER half of the split: per-INK edge width on the same sheet
# --------------------------------------------------------------------------

# selectivity/{C,M,Y}: 5 x 6 mm solids at x_mm 139/145/151, y_mm 227, each
# read in the channel its ink absorbs.  Located once and pinned.
INK_SOLIDS = {
    "C": {"x0": 26160, "x1": 27140, "channel": 0},
    "M": {"x0": 27300, "x1": 28272, "channel": 1},
    "Y": {"x0": 28432, "x1": 29400, "channel": 2},
}
INK_ROWS = (42700, 43700)


def measure_inks(scan_dpi: float, scanner_sigma_um: dict[str, float],
                 evidence_root: Path, verbose: bool = True) -> dict[str, Any]:
    """Per-ink edge width, each ink read in the channel that sees it.

    The scanner half of the question is answered by the channel ratios;
    this is the toner half, on the same sheet and the same capture: how
    wide is a C / M / Y / K edge once the scanner's own sigma for THAT
    channel comes out in quadrature.  Heavily confounded — one sheet, one
    capture, the M281's colour toner was low on this print day (the
    operator wrote it on the sheet), and the leading/trailing edge
    asymmetry is as large as the ink-to-ink difference.  A direction, not
    a number, and NOT a measurement of sheet I (different engine, sheet
    and capture dpi).
    """
    image = tifffile.memmap(evidence_root / COLOR["path"], mode="r")
    names = ("R", "G", "B")
    rows: list[dict[str, Any]] = []
    plans = [(ink, spec["channel"], spec["x0"], spec["x1"], INK_ROWS)
             for ink, spec in INK_SOLIDS.items()]
    plans.append(("K", 1, TONE_K_SOLID["x0"], TONE_K_SOLID["x1"],
                  (TONE_K_SOLID["y0"] + 60, TONE_K_SOLID["y1"] - 60)))
    for ink, channel, x0, x1, (y0, y1) in plans:
        name = names[channel]
        for polarity, x_edge in (("falling", x0), ("rising", x1)):
            crop = np.asarray(image[y0:y1, x_edge - 150:x_edge + 150,
                                    channel])[:, :, None]
            result = analyze_edge(crop, scan_dpi=scan_dpi,
                                  orientation="vertical",
                                  channel_names=(name,),
                                  lsf_halfwidth_px=80.0)
            measured = result.channels[name]
            rise_um = measured.rise_10_90_px * UM_PER_INCH / scan_dpi
            total = rise_um / 2.5631
            scanner = scanner_sigma_um.get(name, float("nan"))
            rows.append({
                "ink": ink, "channel": name, "polarity": polarity,
                "x_px": x_edge,
                "rise_10_90_um": rise_um,
                "mtf50_lp_per_mm": measured.mtf50_lp_per_mm,
                "sigma_total_um": total,
                "sigma_scanner_um": scanner,
                "sigma_ink_um": math.sqrt(max(total ** 2 - scanner ** 2, 0.0)),
                "contrast_linear": measured.contrast,
            })
            if verbose:
                print(f"  {ink} {polarity:8s} in {name}: rise "
                      f"{rise_um:6.1f} um  sigma_total {total:5.1f}  "
                      f"sigma_ink {rows[-1]['sigma_ink_um']:5.1f} um")
    del image
    return {"rows": rows,
            "scanner_sigma_um": scanner_sigma_um,
            "caveat": ("one sheet, one capture, M281 with low colour toner; "
                       "leading/trailing asymmetry is as large as the "
                       "ink-to-ink difference")}


# --------------------------------------------------------------------------
# 4. synthetic self-test: the estimators against a known truth
# --------------------------------------------------------------------------

def selftest(scan_dpi: float = 4800.0) -> dict[str, Any]:
    micron_per_px = UM_PER_INCH / scan_dpi
    rows, columns, angle = 1600, 400, 5.0
    out: list[dict[str, Any]] = []
    for sigmas, shifts, halfwidth in (
        ((15.0, 15.0, 15.0), (0.0, 0.0, 0.0), 80.0),
        ((15.0, 15.0, 22.0), (0.0, 0.0, -0.35), 80.0),
        ((45.0, 45.0, 52.0), (0.0, 0.0, 0.25), 80.0),
        ((45.0, 45.0, 52.0), (0.0, 0.0, 0.25), 18.0),
    ):
        yy, xx = np.indices((rows, columns), dtype=np.float64)
        slope = math.tan(math.radians(angle))
        stack = np.empty((rows, columns, 3))
        for index, (sigma, shift) in enumerate(zip(sigmas, shifts)):
            distance = xx - (slope * yy + columns / 2
                             - slope * rows / 2) - shift
            scaled = distance / (sigma / micron_per_px * math.sqrt(2.0))
            stack[:, :, index] = 0.5 * (
                1.0 + np.vectorize(math.erf)(scaled))
        linear = 0.02 + 0.85 * stack
        encoded = np.where(linear <= 0.0031308, linear * 12.92,
                           1.055 * linear ** (1 / 2.4) - 0.055)
        patch = np.clip(encoded * 255, 0, 255).astype(np.uint8)
        result = analyze_edge(patch, scan_dpi=scan_dpi,
                              orientation="vertical",
                              lsf_halfwidth_px=halfwidth)
        differentials = compare_channels(result, reference="G",
                                         scan_dpi=scan_dpi, mtf_floor=0.25,
                                         f_min_lp_per_mm=1.0)
        truth = sigmas[2] ** 2 - sigmas[1] ** 2
        blue = result.channels["B"]
        out.append({
            "sigmas_um": list(sigmas), "shifts_px": list(shifts),
            "lsf_halfwidth_px": halfwidth,
            "mtf50_measured": blue.mtf50_lp_per_mm,
            "mtf50_expected": 0.18739 / (sigmas[2] / 1000.0),
            "mtf10_measured": blue.mtf10_lp_per_mm,
            "mtf10_expected": 0.34161 / (sigmas[2] / 1000.0),
            "rise_measured_um": blue.rise_10_90_px * micron_per_px,
            "rise_expected_um": 2.5631 * sigmas[2],
            "dsigma2_measured_um2": differentials["B"]["dsigma2_um2"],
            "dsigma2_true_um2": truth,
            "shift_measured_px": differentials["B"]["shift_px"],
            "shift_true_px": shifts[2],
        })
        print(f"  sigma {sigmas} shift {shifts} hw {halfwidth:g}: "
              f"MTF50 {out[-1]['mtf50_measured']:.2f}/"
              f"{out[-1]['mtf50_expected']:.2f}  "
              f"dsigma2 {out[-1]['dsigma2_measured_um2']:+.1f}/"
              f"{truth:+.1f} um^2  "
              f"shift {out[-1]['shift_measured_px']:+.4f}/"
              f"{shifts[2]:+.2f} px")
    return {"cases": out}


# --------------------------------------------------------------------------

def _aggregate(color: dict[str, Any], knife: dict[str, Any] | None
               ) -> dict[str, Any]:
    """Per-family channel differentials, and the composed blue sigma.

    Edge shifts are reported POLARITY-PAIRED.  On an edge, a measured
    per-channel offset is ``displacement + p * asymmetry``: a true lateral
    displacement moves a white->black and a black->white edge the same
    way, while a channel-dependent PSF asymmetry (a one-sided tail) moves
    them oppositely.  The mean over the two polarities is therefore the
    registration number, and the half-difference is the asymmetry — which
    is exactly why every edge target here is measured on BOTH of its
    edges.  Line targets cannot be split this way and are reported raw.
    """
    families: dict[str, dict[str, Any]] = {}
    for measurement in color["measurements"]:
        bucket = families.setdefault(
            f"{measurement['family']}/{measurement['axis']}",
            {"family": measurement["family"], "axis": measurement["axis"],
             "n": 0, "channels": {}})
        bucket["n"] += 1
        for name, differential in measurement["differentials"].items():
            entry = bucket["channels"].setdefault(
                name, {"dsigma2_um2": [], "shift_px": [], "shift_dots": [],
                       "falling_dots": [], "rising_dots": []})
            entry["dsigma2_um2"].append(differential["dsigma2_um2"])
            entry["shift_px"].append(differential["shift_px"])
            entry["shift_dots"].append(differential["shift_dots"])
            if measurement["polarity"] in {"falling", "rising"}:
                entry[f"{measurement['polarity']}_dots"].append(
                    differential["shift_dots"])
    summary: dict[str, Any] = {}
    for key, bucket in families.items():
        stats: dict[str, Any] = {"n": bucket["n"]}
        for name, entry in bucket["channels"].items():
            channel_stats = {metric: _mean_se(values)
                             for metric, values in entry.items()}
            falling = channel_stats["falling_dots"]["mean"]
            rising = channel_stats["rising_dots"]["mean"]
            if np.isfinite(falling) and np.isfinite(rising):
                channel_stats["displacement_dots"] = (falling + rising) / 2.0
                channel_stats["asymmetry_dots"] = (falling - rising) / 2.0
            stats[name] = channel_stats
        summary[key] = stats

    composed = None
    if knife is not None:
        # 028.4's glass-level luma anchor, as a Gaussian-equivalent sigma
        # from the NARROWEST groove (an upper bound on the LSF).
        fwhm_um = knife["narrowest"]["fwhm_um"]
        sigma_luma = fwhm_um / 2.3548
        blue = []
        for key, stats in summary.items():
            if "B" not in stats:
                continue
            delta = stats["B"]["dsigma2_um2"]["mean"]
            blue.append({
                "family_axis": key,
                "dsigma2_um2": delta,
                "sigma_B_um": math.sqrt(max(sigma_luma ** 2 + delta, 0.0)),
                "sigma_ratio_B_over_G": (
                    math.sqrt(max(sigma_luma ** 2 + delta, 0.0)) / sigma_luma),
            })
        composed = {"sigma_luma_um_from_knife": sigma_luma,
                    "basis": "narrowest snap-score groove FWHM / 2.3548",
                    "caveat": ("the groove is a line of unknown physical "
                               "width, so sigma_luma is an UPPER bound and "
                               "every composed sigma inherits that"),
                    "per_family": blue}
    return {"per_family": summary, "composed_blue": composed}


def scanner_sigmas(report: dict[str, Any],
                   family: str = "solid-K-edge/y") -> dict[str, Any]:
    """Per-channel scanner sigma: the luma anchor plus the differentials.

    sigma_G comes from the knife-edge groove (an UPPER bound, MTF50
    basis), and sigma_R / sigma_B from it via the measured
    ``sigma_c^2 - sigma_G^2``.  Default family is the K patch, whose
    +-80 px window is the only one the self-test finds unbiased.
    """
    knife = report.get("knife")
    aggregate = report.get("aggregate", {}).get("per_family", {})
    if not knife:
        return {}
    sigma_g = 0.18739 / knife["narrowest"]["mtf50_lp_per_mm"] * 1000.0
    out = {"G": sigma_g}
    stats = aggregate.get(family, {})
    for name in ("R", "B"):
        delta = stats.get(name, {}).get("dsigma2_um2", {}).get("mean", 0.0)
        out[name] = math.sqrt(max(sigma_g ** 2 + delta, 1.0))
    out["basis"] = (f"sigma_G = 0.18739 / MTF50(narrowest groove); "
                    f"R and B via dsigma2 from {family}")
    return out


def _mean_se(values: Iterable[float]) -> dict[str, float]:
    array = np.array(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if not array.size:
        return {"mean": float("nan"), "se": float("nan"), "n": 0}
    return {
        "mean": float(array.mean()),
        "se": float(array.std(ddof=1) / math.sqrt(array.size))
        if array.size > 1 else float("nan"),
        "sd": float(array.std(ddof=1)) if array.size > 1 else float("nan"),
        "n": int(array.size),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knife", action="store_true",
                        help="luma anchor from the e028 knife-edge scan")
    parser.add_argument("--color", action="store_true",
                        help="per-channel differentials from the RGB scan")
    parser.add_argument("--selftest", action="store_true",
                        help="synthetic edges with known sigma and shift")
    parser.add_argument("--inks", action="store_true",
                        help="the toner half: per-ink edge width on the "
                             "same sheet (needs --knife and --color)")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--segments", type=int, default=8,
                        help="x segments per strip rule (default 8)")
    parser.add_argument("--verify-sha", action="store_true",
                        help="hash the inputs (the colour scan is 6.9 GB)")
    parser.add_argument("--tone", choices=("srgb", "gamma22", "none"),
                        default="srgb",
                        help="capture transfer function to invert; the "
                             "robustness control for every channel ratio")
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-figure", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.all:
        arguments.knife = arguments.color = True
        arguments.selftest = arguments.inks = True
    if not (arguments.knife or arguments.color or arguments.selftest
            or arguments.inks):
        parser.error("pick --knife / --color / --selftest / --inks / --all")
    if arguments.inks and not (arguments.knife and arguments.color):
        parser.error("--inks needs --knife (the sigma anchor) and --color "
                     "(the differentials that split it per channel)")
    if arguments.knife or arguments.color:
        arguments.evidence_root = _evidence.resolve(arguments.evidence_root,
                                                    tool="blue_mtf")
        _evidence.need(*(arguments.evidence_root / spec["path"]
                         for wanted, spec in ((arguments.knife, KNIFE),
                                              (arguments.color, COLOR))
                         if wanted), tool="blue_mtf")
    arguments.out.mkdir(parents=True, exist_ok=True)
    _edge.TONE_MODE = arguments.tone

    report: dict[str, Any] = {
        "instrument": "measure/scanner/blue_mtf.py",
        "purpose": ("docs/INDEPENDENT-PLANES.md 4.I item 3 / 6 P2 — "
                    "blue-channel scanner characterization from existing "
                    "scans"),
        "scanner": "Canon LiDE 400 (CIS), 4800 dpi, e028 print-day captures",
        "generated_unix": time.time(),
        "tone_curve": arguments.tone,
        "inputs": {},
    }
    for tag, spec in (("knife", KNIFE), ("color", COLOR)):
        if arguments.evidence_root is None:
            break
        capture = arguments.evidence_root / spec["path"]
        entry = {"path": str(capture), "sha256_expected": spec["sha256"],
                 "record": spec["record"], "exists": capture.exists()}
        if arguments.verify_sha and capture.exists():
            entry["sha256_measured"] = sha256_of(capture)
            entry["sha256_ok"] = entry["sha256_measured"] == spec["sha256"]
        report["inputs"][tag] = entry

    if arguments.selftest:
        print("[selftest] synthetic edges")
        report["selftest"] = selftest()
    knife_result = None
    if arguments.knife:
        print("[knife] e028 glass-level luma anchor")
        knife_result = measure_knife(KNIFE["dpi"], arguments.evidence_root)
        report["knife"] = knife_result
        narrowest = knife_result["narrowest"]
        print(f"  narrowest groove: FWHM {narrowest['fwhm_um']:.1f} um "
              f"MTF50 {narrowest['mtf50_lp_per_mm']:.2f} "
              f"MTF10 {narrowest['mtf10_lp_per_mm']:.2f} lp/mm "
              f"(028.4: 50 um / 9-14 / ~17)")
    if arguments.color:
        print("[color] per-channel differentials on K-toner targets")
        color_result = measure_color(COLOR["dpi"], arguments.evidence_root,
                                     segments=arguments.segments)
        report["color"] = color_result
        report["aggregate"] = _aggregate(color_result, knife_result)

    if arguments.inks:
        print("[inks] per-ink edge width, scanner sigma removed in "
              "quadrature")
        sigmas = scanner_sigmas(report)
        report["scanner_sigma_um"] = sigmas
        report["inks"] = measure_inks(
            COLOR["dpi"],
            {k: v for k, v in sigmas.items() if isinstance(v, float)},
            arguments.evidence_root)

    suffix = "" if arguments.tone == "srgb" else f"-{arguments.tone}"
    path = arguments.out / f"blue-mtf{suffix}.json"
    path.write_text(json.dumps(report, indent=1, default=float))
    print(f"wrote {path}")
    if not arguments.no_figure and "color" in report:
        from ._figures import draw_report
        figure = arguments.out / f"blue-mtf{suffix}.png"
        draw_report(figure, report)
        print(f"wrote {figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
