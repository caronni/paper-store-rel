"""Registration crosses: reading a 2-dot bar, and what its position means.

Arm 3 of ``ink_psf``, plus the bar reader that arm 1's ``cross-bar``
family also uses.  Split out of ``ink_psf`` because it is one subject —
the ``registration/rXcY/{K,C,M,Y}`` target, how to measure a bar on it,
and how to turn nine of those into a per-plane displacement — and
because that subject carries the arm's whole argument: the planes are
authored 4 / 8 / 12 mm apart in x, so a raw offset from K is
``displacement + baseline * local page-scale residual`` and the two have
to be separated before any number means anything.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from . import _edge
from ._edge import (UM_PER_INCH, EdgeResult, band_samples, bin_profile,
                    line_metrics)
from ._sheet import Sheet
from .blue_mtf import LUMA_601, _mean_se

PLANES = ("K", "C", "M", "Y")
# Each ink read in the channel it absorbs; K is near-neutral (measured
# ink RGB 52/54/54 on e031) and is carried in all three.
INK_CHANNEL = {"C": "R", "M": "G", "Y": "B", "K": "G"}
CHANNEL_INDEX = {"R": 0, "G": 1, "B": 2}
# patterns.py renders a 71 x 142-dot cross with stroke 2: the vertical
# stroke lands on columns 34-35 and the horizontal one on rows 70-71, so
# in the affine's dot-INDEX frame their centres sit at +34.5 / +70.5 from
# the raster origin.  The origin is ``*_source_dots`` (the integer the
# emitter actually places at), not ``*_layout_dots`` (the unrounded mm
# conversion) — the two differ by up to 0.5 dot = 21 um, which is the
# size of the plane offsets this arm measures.
STROKE_CENTRE_DOTS = (34.5, 70.5)


def _half_max_centre(centres: np.ndarray, profile: np.ndarray) -> float:
    """Midpoint of the half-maximum crossings of a unit-peak line profile."""
    values = np.asarray(profile, dtype=np.float64)
    above = np.flatnonzero(values >= 0.5)
    if not above.size:
        return float("nan")
    return float((centres[int(above[0])] + centres[int(above[-1])]) / 2.0)


def _stroke(sheet: Sheet, target: str, plane: str, axis: str,
            channels: Sequence[str], halfwidth_px: float = 26.0
            ) -> dict[str, Any]:
    """One 2-dot bar of one registration cross, super-resolved.

    ``axis='x'`` reads the VERTICAL bar (an x position); ``axis='y'``
    reads the horizontal one, with the patch transposed so both take one
    code path.  Three things make the position usable at the 20 um scale
    the plane offsets live at:

    * the bar is sheared by the page's own rotation, which the affine
      already knows exactly, so the band is WALKED along the known line
      rather than re-fitted from ~1000 noisy rows;
    * the samples come from both sides of the cross centre, with the
      other bar's 16 px excluded, so the profile is a clean line and the
      averaging length is the whole bar rather than one arm;
    * every requested channel is projected onto the SAME line, so the
      per-channel centroids differ only by the scanner's lateral CA and
      the ratios of ``compare_channels`` stay valid.
    """
    probe_id = f"registration/{target}/{plane}"
    box = sheet.probe_box(probe_id)
    probe = sheet.probes[probe_id]
    height, width = box["y1"] - box["y0"], box["x1"] - box["x0"]
    if axis == "x":
        data, y_origin, x_origin = sheet.crop_at(
            box["y0"] + 0.03 * height, box["y1"] - 0.03 * height,
            box["cx"] - 90, box["cx"] + 90)
        slope = sheet.vertical_slope
        cross_at = box["cy"] - y_origin
        along_origin, across_origin = float(y_origin), float(x_origin)
    else:
        data, y_origin, x_origin = sheet.crop_at(
            box["cy"] - 90, box["cy"] + 90,
            box["x0"] + 0.03 * width, box["x1"] - 0.03 * width)
        data = np.transpose(data, (1, 0, 2))
        slope = sheet.horizontal_slope
        cross_at = box["cx"] - x_origin
        along_origin, across_origin = float(x_origin), float(y_origin)

    values = _edge.linearize_srgb(data)
    rows = values.shape[0]
    spans = [(0, int(max(0, cross_at - 70))),
             (int(min(rows, cross_at + 70)), rows)]
    spans = [(lo, hi) for lo, hi in spans if hi - lo >= 40]
    if not spans:
        raise ValueError(f"{probe_id}/{axis}: no usable bar length")
    kept = np.concatenate([np.arange(lo, hi) for lo, hi in spans])
    reference = values.mean(axis=2)
    coarse = float(np.argmin(reference[kept].mean(axis=0)))
    reference_row = float(kept.mean())
    intercept = coarse - slope * reference_row
    normal = 1.0 / math.sqrt(1.0 + slope * slope)

    planes: dict[str, np.ndarray] = {
        name: values[:, :, CHANNEL_INDEX[name]]
        for name in channels if name in CHANNEL_INDEX
        and CHANNEL_INDEX[name] < values.shape[2]
    }
    if "luma" in channels:
        planes["luma"] = values[:, :, 0]
    if "luma601" in channels and values.shape[2] == 3:
        planes["luma601"] = np.tensordot(values, LUMA_601, axes=([2], [0]))

    results: dict[str, Any] = {}
    positions: dict[str, dict[str, Any]] = {}
    centres = np.zeros(0)
    frequencies = np.zeros(0)
    polarity = 0.0
    for name, plane_values in planes.items():
        chunks = [band_samples(plane_values, slope, intercept, lo, hi,
                               halfwidth_px) for lo, hi in spans]
        distance = np.concatenate([chunk[0] for chunk in chunks])
        sample = np.concatenate([chunk[1] for chunk in chunks])
        centres, profile, _counts = bin_profile(distance, sample,
                                                halfwidth_px, 0.25)
        result, frequencies = line_metrics(
            name, centres, profile, scan_dpi=sheet.spec.scan_dpi,
            halfwidth_px=halfwidth_px, polarity=polarity)
        polarity = -1.0                 # dark bar: lock the first verdict
        results[name] = result
        authored = float(probe["x_source_dots" if axis == "x"
                               else "y_source_dots"]
                         + STROKE_CENTRE_DOTS[0 if axis == "x" else 1])
        entry: dict[str, Any] = {
            "fwhm_um": result.rise_10_90_px * sheet.spec.um_per_px,
            "peak_linear": result.contrast, "authored_dots": authored,
        }
        # Two independent centre estimators.  The centroid is efficient
        # but a one-sided toner tail drags it, and a per-INK tail is
        # exactly what would fake a per-plane offset; the half-max
        # midpoint is blind to the tails.  Both are carried so the
        # difference is a recorded control, not an assumption.
        for tag, offset in (("", result.centroid_px),
                            ("halfmax_", _half_max_centre(centres,
                                                          result.esf))):
            across = across_origin + coarse + offset / normal
            along = along_origin + reference_row
            x_px, y_px = ((across, along) if axis == "x" else (along, across))
            layout = sheet.to_layout(x_px, y_px)
            measured = layout[0] if axis == "x" else layout[1]
            entry.update({
                f"{tag}x_px": float(x_px), f"{tag}y_px": float(y_px),
                f"{tag}layout_dots": float(measured),
                f"{tag}residual_dots": float(measured - authored),
            })
        positions[name] = entry
    return {
        "target": target, "plane": plane, "axis": axis,
        "positions": positions,
        "result": EdgeResult(
            angle_deg=float(np.degrees(np.arctan(slope))),
            fit_rms_px=float("nan"), rows_used=rows,
            samples=int(sum(hi - lo for lo, hi in spans)),
            frequencies_lp_per_mm=frequencies, bin_centers_px=centres,
            channels=results,
            note="registration cross bar (the bar's own width divides out)"),
    }


def registration_arm(sheet: Sheet, verbose: bool = True) -> dict[str, Any]:
    """Per-plane offset from K, measured in the plane's OWN channel.

    Reading plane P and K in the same channel makes the scanner's lateral
    chromatic aberration cancel identically rather than be corrected for.
    """
    if len(sheet.spec.channels) != 3:
        return {}
    dot_um = UM_PER_INCH / 600.0
    targets: list[dict[str, Any]] = []
    for row_index in range(3):
        for column_index in range(3):
            target = f"r{row_index}c{column_index}"
            entry: dict[str, Any] = {"target": target, "planes": {},
                                     "offset_from_k_um": {},
                                     "offset_from_k_halfmax_um": {}}
            reference: dict[str, dict[str, Any]] = {}
            for axis in ("x", "y"):
                # K read in all three channels at once: each colour plane
                # is then compared with the K bar seen through the SAME
                # channel, so lateral CA cancels identically.
                measured = _stroke(sheet, target, "K", axis, ("R", "G", "B"))
                reference[axis] = measured["positions"]
                entry["planes"].setdefault("K", {})[axis] = \
                    measured["positions"][INK_CHANNEL["K"]]
                entry["planes"]["K"][axis]["by_channel_residual_dots"] = {
                    name: value["residual_dots"]
                    for name, value in measured["positions"].items()}
            for plane in ("C", "M", "Y"):
                channel = INK_CHANNEL[plane]
                offsets: dict[str, dict[str, float]] = {"": {}, "halfmax_": {}}
                for axis in ("x", "y"):
                    measured = _stroke(sheet, target, plane, axis, (channel,))
                    position = measured["positions"][channel]
                    position["channel"] = channel
                    entry["planes"].setdefault(plane, {})[axis] = position
                    for tag in offsets:
                        offsets[tag][axis] = (
                            position[f"{tag}residual_dots"]
                            - reference[axis][channel][f"{tag}residual_dots"]
                        ) * dot_um
                entry["offset_from_k_um"][plane] = [offsets[""]["x"],
                                                    offsets[""]["y"]]
                entry["offset_from_k_halfmax_um"][plane] = [
                    offsets["halfmax_"]["x"], offsets["halfmax_"]["y"]]
            targets.append(entry)
            if verbose:
                text = "  ".join(
                    f"{plane} ({entry['offset_from_k_um'][plane][0]:+6.1f},"
                    f"{entry['offset_from_k_um'][plane][1]:+6.1f})"
                    for plane in ("C", "M", "Y"))
                print(f"  {target}  dK um  {text}")
    return {"targets": targets, "per_plane": _per_plane(targets),
            "baseline_fit": _baseline_fit(targets),
            "stroke_width": _stroke_width(targets)}


def _per_plane(targets: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for plane in ("C", "M", "Y"):
        dx = [entry["offset_from_k_um"][plane][0] for entry in targets]
        dy = [entry["offset_from_k_um"][plane][1] for entry in targets]
        control = [entry["offset_from_k_halfmax_um"][plane]
                   for entry in targets]
        out[plane] = {
            "baseline_mm": 4.0 * PLANES.index(plane),
            "dx_um": _mean_se(dx), "dy_um": _mean_se(dy),
            "dx_dots": _mean_se([v / (UM_PER_INCH / 600.0) for v in dx]),
            "dy_dots": _mean_se([v / (UM_PER_INCH / 600.0) for v in dy]),
            "dx_um_halfmax_control": _mean_se([v[0] for v in control]),
            "dy_um_halfmax_control": _mean_se([v[1] for v in control]),
        }
    return out


def _baseline_fit(targets: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Split the offsets into a plane term and a baseline-proportional one.

    layout.py places one target's K/C/M/Y crosses 4 mm apart in x, so a
    residual page-scale error between the fitted affine and the print
    enters every offset as ``epsilon * baseline`` — the report's own
    ``plane_registration`` cannot tell that from a plane displacement.
    Regressing the three offsets of one target ON their 4 / 8 / 12 mm
    baseline separates them: the SLOPE is the local scale residual in
    um/mm, and the INTERCEPT is what is left at zero baseline, i.e. the
    plane displacement under the gauge that the contamination is exactly
    linear in baseline.

    ``fit_residual_um`` is the validity flag and must be read with the
    intercept.  Three points on two parameters always fit SOMETHING; a
    residual of a few um means the three planes really do share one line
    (so no plane has a displacement of its own), while a large one means
    a plane is off the trend and the split does not describe the data —
    read the raw per-plane means instead.  Measured: 2.2-3.6 um on the
    e031 AltaLink sheet, 15.1 um on e028's y axis, where the M281's Y
    sits ~80 um below the C/M trend.
    """
    baselines = np.array([4.0, 8.0, 12.0])
    design = np.column_stack([np.ones(3), baselines])
    out: dict[str, Any] = {"gauge": (
        "offset(P) = intercept + slope * baseline_mm, fitted per target "
        "over C/M/Y; intercept = plane displacement, slope = local "
        "residual page scale.  The two are separable only because the "
        "baselines differ (4/8/12 mm); a scale error COMMON to every "
        "target is absorbed into slope, which is the intended gauge.")}
    for axis, index in (("x", 0), ("y", 1)):
        intercepts, slopes, residuals = [], [], []
        for entry in targets:
            values = np.array([entry["offset_from_k_um"][plane][index]
                               for plane in ("C", "M", "Y")])
            solution, *_ = np.linalg.lstsq(design, values, rcond=None)
            intercepts.append(float(solution[0]))
            slopes.append(float(solution[1]))
            residuals.append(float(np.sqrt(np.mean(
                (values - design @ solution) ** 2))))
        out[axis] = {
            "intercept_um": _mean_se(intercepts),
            "slope_um_per_mm": _mean_se(slopes),
            "fit_residual_um": _mean_se(residuals),
            "per_target_intercept_um": intercepts,
            "per_target_slope_um_per_mm": slopes,
        }
    return out


def _stroke_width(targets: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """FWHM of each plane's 2-dot bar — a LINE-target per-ink width.

    Convolved with the authored 2-dot (84.7 um) stroke, which is common
    to all four planes, so only the plane-to-plane ORDER is meaningful.
    """
    out: dict[str, Any] = {}
    for plane in PLANES:
        for axis in ("x", "y"):
            values = [entry["planes"][plane][axis]["fwhm_um"]
                      for entry in targets]
            peaks = [entry["planes"][plane][axis]["peak_linear"]
                     for entry in targets]
            out[f"{plane}/{axis}"] = {"fwhm_um": _mean_se(values),
                                      "peak_linear": _mean_se(peaks)}
    return out
