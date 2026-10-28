"""The two combs this scanner is on record for, and whether they are the answer.

``channel_ca`` measured a scanner whose only documented periodic structure
was cosmetic.  This one is not that scanner.  The record carries two
named periodic hazards for the home flatbed, and the mission for this
module is to stop either of them from being mistaken for channel
geometry:

* **the 18.63 mm sensor-axis comb** (experiments/002 §256): a
  deterministic CCD/CIS chip-joint fixed pattern at scanner
  x = 14.1 + n * 18.63 mm, "both halves, common phase, uniform ~-0.9
  dot".  That -0.9 dot is a POSITION step, not a level — the sensor's
  x mapping is discontinuous at each joint.  A mark that straddles a
  joint is read displaced, and if the three channels do not share the
  joint exactly, displaced by different amounts per channel.  0.9 dot is
  three and a half times the publish floor, so this is the one artifact
  on this scanner that could manufacture the whole result.

* **the 11.36 px COLOUR-mode comb** (experiments/017 P2): the structure
  that got colour acquisition from this scanner banned outright, because
  its 5.68 px harmonic out-contrasted the payload cell lattice and broke
  blind pitch identification.  It exists only in colour mode, which is
  to say it exists only in exactly the captures this instrument reads.

Two tests, and they answer different questions.

``spectra`` measures both combs directly, per channel, on ink-free paper
in the captures themselves rather than trusting the priors.  If a comb is
channel-COMMON it cannot produce a channel difference at all, whatever
its amplitude; the per-channel amplitudes are what settle that.

``phase_test`` is the one that actually guards the verdict, because it
needs no theory of mechanism.  Every measured mark has a position, so it
has a phase within each comb's period.  If a comb is producing the
offsets, the offsets must vary with that phase — that is what a comb IS.
The test bins the measured offsets by phase and reports the peak-to-peak
of the binned means against the scatter within bins.  A comb explanation
requires the binned range to be a large part of the effect; a range that
sits inside the noise means the comb is not carrying it, and no argument
about amplitudes or mechanisms is needed.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

MM_PER_INCH = 25.4

CCD_COMB_MM = 18.63               # experiments/002 §256, sensor axis
CCD_COMB_PHASE_MM = 14.1
COLOUR_COMB_PX_AT_1200 = 11.36    # experiments/017 P2, colour mode only
COLOUR_COMB_HARMONIC_PX = 5.68


def _paper_strip(small: np.ndarray, axis: str, paper: float,
                 tolerance: float = 25.0, min_span: int = 16,
                 dirty_fraction: float = 0.005
                 ) -> tuple[int, int] | None:
    """The longest run of rows (or columns) that is essentially all paper.

    This took two corrections, and both are worth keeping because both
    were measured rather than guessed.

    The first version demanded that a row carry NO ink at all.  Every
    dense probe page failed it — a finalists checkerboard leaves no
    perfectly clean row between its tiles — and the comb arm silently
    measured nothing on any capture.

    The second version took the band outside the printed bounding box
    instead.  That also failed, for a reason particular to this scanner:
    its captures are 9920 x 14028 at 1200 dpi, which is 210.0 x 296.9 mm
    — the sheet IS the scan area, so there is no platen margin outside
    the paper, and the dark rows at the very border of the scan put the
    bounding box at the first and last row.  Both margins measured zero.

    What works is the longest run of rows whose INKED FRACTION is under
    ``dirty_fraction``.  It tolerates the border artifact and the odd
    speck, it finds the unprinted band inside the sheet (the print clip
    keeps toner ~4 mm off every edge), and on genuinely blank paper it
    returns the whole capture.
    """
    across = 1 if axis == "x" else 0
    dirty = (small < paper - tolerance).mean(axis=across)
    clean = dirty < dirty_fraction
    best = span = start = 0
    best_start = -1
    for index, value in enumerate(clean):
        if value:
            if span == 0:
                start = index
            span += 1
            if span > best:
                best, best_start = span, start
        else:
            span = 0
    if best < min_span or best_start < 0:
        return None
    return best_start, best_start + best


def _lines(profile: np.ndarray, scan_dpi: float, top: int = 6
           ) -> tuple[np.ndarray, np.ndarray]:
    """Amplitude spectrum of a 1-D profile, in grey levels RMS vs period."""
    values = profile.astype(np.float64)
    index = np.arange(values.size, dtype=np.float64)
    # Remove the illumination ramp: these margins carry mm-scale shading
    # an order above any comb, and it would smear across the whole
    # low-frequency end of the spectrum.
    trend = np.polynomial.polynomial.polyfit(index, values, 3)
    values = values - np.polynomial.polynomial.polyval(index, trend)
    window = np.hanning(values.size)
    spectrum = np.fft.rfft(values * window)
    # Hann halves coherent amplitude; the factor restores it so the
    # numbers are readable as grey levels.
    amplitude = np.abs(spectrum) * 2.0 / (window.sum())
    frequency = np.fft.rfftfreq(values.size, d=1.0)
    with np.errstate(divide="ignore"):
        period = np.where(frequency > 0, 1.0 / np.maximum(frequency, 1e-12),
                          np.inf)
    return period, amplitude


def _at_period(period: np.ndarray, amplitude: np.ndarray, target_px: float,
               width: float = 0.03) -> float:
    """Peak amplitude within +-3 % of a target period."""
    band = (period > target_px * (1 - width)) & (period < target_px * (1 + width))
    return float(amplitude[band].max()) if band.any() else float("nan")


def spectra(rgb: np.ndarray, small: np.ndarray, *, scan_dpi: float,
            decimate: int, channel_names: Sequence[str] = ("R", "G", "B"),
            top: int = 5) -> dict[str, Any]:
    """Per-channel comb amplitudes on this capture's own blank paper."""
    paper = float(np.percentile(small, 98.0))
    ccd_px = CCD_COMB_MM / MM_PER_INCH * scan_dpi
    colour_px = COLOUR_COMB_PX_AT_1200 * scan_dpi / 1200.0
    harmonic_px = COLOUR_COMB_HARMONIC_PX * scan_dpi / 1200.0
    out: dict[str, Any] = {"paper_level": paper,
                           "ccd_comb_period_px": ccd_px,
                           "colour_comb_period_px": colour_px}
    for axis in ("x", "y"):
        strip = _paper_strip(small, axis, paper)
        if strip is None:
            out[axis] = {"note": "no ink-free strip on this capture"}
            continue
        lo, hi = strip[0] * decimate, strip[1] * decimate
        # Trim the strip's own ends: a margin abuts the sheet edge and
        # the platen lid, and those transitions are not paper.
        trim = max(1, (hi - lo) // 8)
        lo, hi = lo + trim, hi - trim
        entry: dict[str, Any] = {
            "strip_px": [int(lo), int(hi)],
            "strip_mm": [lo / scan_dpi * MM_PER_INCH,
                         hi / scan_dpi * MM_PER_INCH],
        }
        for index, name in enumerate(channel_names):
            plane = (rgb[lo:hi, :, index] if axis == "x"
                     else rgb[:, lo:hi, index])
            profile = plane.mean(axis=0 if axis == "x" else 1,
                                 dtype=np.float64)
            period, amplitude = _lines(profile, scan_dpi)
            # Only periods a comb could live at; the long end is
            # illumination and the short end is shot noise.
            usable = (period >= 3.0) & (period <= 4.0 * ccd_px)
            order = np.argsort(amplitude[usable])[::-1][:top]
            entry[name] = {
                "rms_grey": float(np.std(profile)),
                "at_ccd_comb": _at_period(period, amplitude, ccd_px),
                "at_colour_comb": _at_period(period, amplitude, colour_px),
                "at_colour_harmonic": _at_period(period, amplitude,
                                                 harmonic_px),
                "top_lines": [
                    {"period_px": float(period[usable][i]),
                     "period_mm": float(period[usable][i] / scan_dpi
                                        * MM_PER_INCH),
                     "amplitude_grey": float(amplitude[usable][i])}
                    for i in order],
            }
        out[axis] = entry
    return out


def phase_test(rows: list[dict[str, Any]], *, axis: str, channel: str,
               period_mm: float, phase_mm: float = 0.0, bins: int = 8,
               detrend: bool = True) -> dict[str, Any]:
    """Do the measured offsets vary with position inside one comb period?

    The offsets are binned by their phase in the comb.  ``binned_range``
    is the peak-to-peak of the bin means and ``within_bin_sd`` the
    typical scatter inside a bin; a comb that drives the effect shows a
    binned range comparable to the effect itself, and one that does not
    shows a range at or below what the scatter alone would produce.

    ``expected_range_from_noise`` makes that comparison quantitative: it
    is the peak-to-peak that ``bins`` independent bin means of this
    sample size would show if the underlying offsets were i.i.d. noise
    (the normal range statistic, tabulated by its standard
    approximation).  A binned range under that is evidence of NOTHING.

    ``detrend`` removes a quadratic in platen x first, and it is on by
    default because of a measured leak.  The marks on these pages sit on
    the probe lattices their pages were designed around, so their
    positions are themselves periodic and their phase coverage is badly
    uneven — one bin of the 18.63 mm test held 5 marks against another's
    72.  With coverage like that a SMOOTH platen trend (and blue has
    one: a real odd-symmetric lateral term of 0.013 dots) redistributes
    itself across the phase bins and reads as a comb.  The comb question
    is about structure at the comb's OWN period, so the smooth part is
    removed before it can be counted twice.
    """
    position = "x_mm" if axis == "x" else "y_mm"
    field = "dx_dots" if axis == "x" else "dy_dots"
    coordinates, values, platen_x = [], [], []
    for row in rows:
        value = row.get(field, {}).get(channel)
        if value is None or not math.isfinite(value):
            continue
        coordinates.append(row[position])
        values.append(value)
        platen_x.append(row["x_mm"])
    if len(values) < bins * 2:
        return {"n": len(values), "tested": False,
                "note": "too few marks to bin"}
    coordinates = np.asarray(coordinates)
    values = np.asarray(values)
    mean_before = float(values.mean())
    if detrend and len(values) > 8:
        scaled = np.asarray(platen_x)
        scaled = (scaled - scaled.mean()) / max(1e-9, scaled.std())
        design = np.column_stack([np.ones_like(scaled), scaled, scaled ** 2])
        solution, *_ = np.linalg.lstsq(design, values, rcond=None)
        values = values - design @ solution + solution[0]
    phase = np.mod(coordinates - phase_mm, period_mm) / period_mm
    edges = np.linspace(0.0, 1.0, bins + 1)
    means, counts, spreads = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        inside = values[(phase >= lo) & (phase < hi)]
        if inside.size == 0:
            continue
        means.append(float(inside.mean()))
        counts.append(int(inside.size))
        spreads.append(float(inside.std(ddof=1)) if inside.size > 1 else 0.0)
    if len(means) < 3:
        return {"n": int(values.size), "tested": False,
                "note": "marks do not cover the period"}
    within = float(np.mean(spreads))
    per_bin = float(np.mean(counts))
    # E[range] of k standard normals, k small: the usual d2 constants.
    d2 = {3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847,
          9: 2.970, 10: 3.078}.get(len(means), 3.0)
    standard_error = within / math.sqrt(max(1.0, per_bin))
    binned_range = float(max(means) - min(means))
    noise_range = d2 * standard_error
    return {
        "n": int(values.size), "tested": True,
        "period_mm": period_mm, "bins_used": len(means),
        "detrended": bool(detrend),
        "bin_means_dots": means, "bin_counts": counts,
        "binned_range_dots": binned_range,
        "within_bin_sd_dots": within,
        "expected_range_from_noise_dots": noise_range,
        "explains_effect": bool(binned_range > 2.0 * noise_range),
        "effect_mean_dots": mean_before,
        # What fraction of the measured effect a comb could account for
        # even if the whole binned range were comb.  This is the number
        # the verdict cares about: a comb that moves 0.013 dots cannot
        # be the source of a 0.175-dot constant however significant it
        # is against its own noise.
        "share_of_effect": (binned_range / abs(mean_before)
                            if abs(mean_before) > 1e-9 else float("inf")),
    }


def comb_phase_report(rows: list[dict[str, Any]], scan_dpi: float
                      ) -> dict[str, Any]:
    """Both combs, both axes, both channel pairs."""
    colour_comb_mm = COLOUR_COMB_PX_AT_1200 / 1200.0 * MM_PER_INCH
    out: dict[str, Any] = {}
    plans = (
        ("ccd-18.63mm", CCD_COMB_MM, CCD_COMB_PHASE_MM),
        ("colour-11.36px", colour_comb_mm, 0.0),
    )
    for label, period_mm, phase_mm in plans:
        for axis in ("x", "y"):
            for channel in ("R", "B"):
                out[f"{label}/{axis}/{channel}-G"] = phase_test(
                    rows, axis=axis, channel=channel,
                    period_mm=period_mm, phase_mm=phase_mm)
    return out
