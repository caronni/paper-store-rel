"""E6 — the per-ink PSF, replicated on HEALTHY toner (AltaLink e031).

``blue_mtf`` split the Canon LiDE 400's optics from the M281's toner on
the e028 discovery pair and ranked the inks: sigma **Y 51.2 > K 45.8 >
C 42.6 > M 24.8 um**.  That ranking is confounded — the M281's colour
toner was low on that print day and the operator wrote it on the sheet —
so "yellow toner scatters more" and "this cartridge is empty" are the
same number there.

The AltaLink e031 discovery pair breaks the tie.  Same scanner, same
capture dpi, the SAME AUTHORED PAGE (identical
``page_plan_semantic_sha256``), a different engine whose Y is measured
healthy (e031 §7: Y tone range 0.515 against the M281's 0.351; density
over paper at 25 % coverage 0.0714 against 0.0110).  If yellow is still
the broadest ink here, breadth is toner physics; if it collapses to the
K/C/M club, the e028 ranking was a cartridge.

Three arms, all read-only on archived captures, no hardware:

1. **channel** — the scanner half.  A K-toner edge is the same physical
   edge in R, G and B, so a channel RATIO cancels toner scatter, paper
   light-spread and the printer's own edge raggedness, and what survives
   (``sigma_c^2 - sigma_G^2``, lateral shift) is scanner-side.  Same
   three target families as ``blue_mtf``, located from the page plan
   instead of pinned pixels — and with two sheets of the SAME page
   through the SAME scanner, each family now has a replication test it
   did not have before.  That test FOUND A MODEL DEFECT: the
   registration-cross LINE family reported ``dsigma2`` an order of
   magnitude apart on the two sheets (e028 R +102 / B -107 um^2 against
   e031's +4 / -33) while the edge families agreed.  ``compare_channels``
   fits ``ln(ratio) = -2 pi^2 dsigma2 f^2`` with no constant term, which
   is right for an edge (each channel's ESF is normalized on its own
   plateaus, so the ratio is 1 at DC by construction) and wrong for a
   line (``line_metrics`` normalizes by the PEAK, so the DC ratio is the
   channels' ink CONTRAST ratio).  The M281's slightly warm K reads
   4.5 % weaker in R than in G, and the intercept-free fit had nowhere
   to put that constant except the slope.  With ``allow_intercept`` the
   two sheets agree — cross-bar/x R -5.9 / -6.1, B -12.8 / -9.5 um^2 —
   and every family now replicates.
2. **ink** — the toner half.  Each ink's solid patch read in the channel
   that ink absorbs (C->R, M->G, Y->B, K->G), all four edges, so both
   polarities on both axes; the scanner sigma for that channel and axis
   comes out in quadrature.
3. **registration** — the per-plane lateral displacement, from the nine
   ``registration/rXcY/{K,C,M,Y}`` crosses.  Each plane is compared with
   K **read in the same channel**, so the scanner's lateral CA cancels
   exactly rather than being corrected for.  The planes are authored
   4 / 8 / 12 mm apart in x, so a residual page-scale error enters
   proportional to that baseline; the arm regresses the offsets ON the
   baseline and reports the intercept (displacement) and the slope
   (um/mm of local scale residual) separately.

Run (read-only, no scan, no print):

    cd <repo>
    PYTHONPATH=measure env/bin/python -m scanner.ink_psf --all \\
        --evidence-root <evidence> --out build/scanner/e031

Historical record of E6 (2026-08); the e028/e031 captures, reports and
plans (``SHEETS`` paths, relative to ``--evidence-root``, sha256-pinned) are
in the evidence archive.  Outputs land in ``--out``.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

import _evidence

from . import _edge
from ._crosses import (CHANNEL_INDEX, INK_CHANNEL, PLANES, _stroke,
                       registration_arm)
from ._edge import analyze_edge, compare_channels
from ._sheet import Sheet, SheetSpec
from .blue_mtf import KNIFE, LUMA_601, _mean_se, measure_knife, sha256_of

#: Every path below is RELATIVE to ``--evidence-root``, the published
#: archive root (``measure/_evidence.py``).
E028 = Path("paper-store-evidence-holo-2026-10/028-discovery-m281/discovery")
E031 = Path("paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/"
            "discovery")
E028_PLAN = E028 / "jobs"
COLOR_PLAN = E028_PLAN / (
    "hcal-discovery-color-copy0000-default-6995a5d0b5b0218d.manifest.json")
BW_PLAN = E028_PLAN / (
    "hcal-discovery-bw-copy0000-default-f3c9e5f807ca05bf.manifest.json")

# Both pairs are the SAME authored page (`discover emit` defaults,
# request_code 0), so one manifest serves both engines; `Sheet` refuses
# unless the report's page_plan_semantic_sha256 agrees.
SHEETS: dict[str, SheetSpec] = {
    "e031-color": SheetSpec(
        key="e031-color", engine="xerox-altalink-c8245",
        engine_label="Xerox AltaLink C8245",
        capture=E031 / "captures" / "discovery-color-canon-4800rgb.tiff",
        sha256="e468bd26f991484e9ddfa114cb01febc1eea9619fa86ac9"
               "29ef493698de564c0",
        report=E031 / "reports" / "production"
        / "hcal-report-discovery-color-copy0000-82abef068de7c651.json",
        manifest=COLOR_PLAN,
        record="experiments/031-xerox-altalink-discovery.md"),
    "e028-color": SheetSpec(
        key="e028-color", engine="hp-m281",
        engine_label="HP CLJ Pro M281fdw",
        capture=E028 / "captures" / "discovery-color-canon-4800rgb.tiff",
        sha256="d0f12451dfc16d06ce904a2bad324e7d1f2b30d6096d5581"
               "68d1064bdc7aeb8d",
        report=E028 / "reports"
        / "hcal-report-discovery-color-copy0000-3c1efcc081ee8108.json",
        manifest=COLOR_PLAN,
        record="experiments/028-discovery-m281.md capture 028.1b"),
    "e031-bw": SheetSpec(
        key="e031-bw", engine="xerox-altalink-c8245",
        engine_label="Xerox AltaLink C8245",
        capture=E031 / "captures" / "discovery-bw-canon-4800grey.tiff",
        sha256="65e8bf50d93d82ecd5ddaebf6aae5b5a8af0b2dd354b3071"
               "a6adf4e3dbc4ad42",
        report=E031 / "reports" / "w8"
        / "hcal-report-discovery-bw-copy0000-c4fd8826a63743f7.json",
        manifest=BW_PLAN, channels=("luma",),
        record="experiments/031-xerox-altalink-discovery.md 031.1"),
    "e028-bw": SheetSpec(
        key="e028-bw", engine="hp-m281",
        engine_label="HP CLJ Pro M281fdw",
        capture=E028 / "captures" / "discovery-bw-canon-4800grey.tiff",
        sha256="15d8716c9ad10c986f938b52befe37387773635"
               "89a44ab03e2749bc5052c847e",
        report=E028 / "reports"
        / "hcal-report-discovery-bw-copy0000-76d0b6b1161c234e.json",
        manifest=BW_PLAN, channels=("luma",),
        record="experiments/028-discovery-m281.md"),
}
COLOR_SHEETS = ("e031-color", "e028-color")
BW_SHEETS = ("e031-bw", "e028-bw")

RISE_TO_SIGMA = 2.5631          # 10-90 rise of a Gaussian ESF, in sigma
MTF50_TO_SIGMA = 0.18739        # MTF50[cy/mm] * sigma[mm] for a Gaussian


# --------------------------------------------------------------------------
# arm 1 — the scanner half: per-channel differentials on K-toner targets
# --------------------------------------------------------------------------

def _edge_row(sheet: Sheet, patch: np.ndarray, *, target: str, family: str,
              orientation: str, polarity: str, x_px: float, y_px: float,
              halfwidth_px: float, mtf_floor: float) -> dict[str, Any]:
    result = analyze_edge(
        patch, scan_dpi=sheet.spec.scan_dpi, orientation=orientation,
        lsf_halfwidth_px=halfwidth_px, extra_channels={"luma601": LUMA_601})
    differentials = compare_channels(
        result, reference="G", scan_dpi=sheet.spec.scan_dpi,
        mtf_floor=mtf_floor, f_min_lp_per_mm=1.0)
    return {
        "target": target, "family": family,
        "axis": "x" if orientation == "vertical" else "y",
        "polarity": polarity,
        "x_px": float(x_px), "y_px": float(y_px),
        "angle_deg": result.angle_deg, "fit_rms_px": result.fit_rms_px,
        "channels": {name: channel.summary(sheet.spec.scan_dpi)
                     for name, channel in result.channels.items()},
        "differentials": differentials,
    }


def _strip_band_edges(sheet: Sheet, element_id: str) -> list[tuple[str, float]]:
    """Outer edges of one HCAL-R1 identity strip's printed field.

    The strip is not a solid rule — it is a row-coded data field whose
    band pattern is the sheet's own payload, so the e028 pixel seeds do
    not port.  What DOES port is the field's outer boundary: the first
    white->black and the last black->white transition inside the
    authored rectangle.  Both are ordinary K edges.
    """
    box = sheet.rectangle_box(element_id)
    column = (box["x0"] + box["x1"]) / 2.0
    crop = sheet.crop(box["y0"] - 140, box["y1"] + 140,
                      column - 400, column + 400)
    profile = crop.mean(axis=(1, 2))
    level = (float(profile.max()) + float(profile.min())) / 2.0
    dark = profile < level
    if not dark.any():
        return []
    rows = np.flatnonzero(dark)
    top = float(box["y0"] - 140 + rows[0])
    bottom = float(box["y0"] - 140 + rows[-1])
    return [("outer-top", top), ("outer-bottom", bottom)]


def channel_arm(sheet: Sheet, segments: int = 8,
                verbose: bool = True) -> list[dict[str, Any]]:
    """K-toner targets, three families, every channel kept separate."""
    rows: list[dict[str, Any]] = []

    # (a) tone/K/1 — the only large solid K area, so the only family with
    #     room for a +-80 px LSF window (the self-test finds tighter
    #     windows biased toward zero).
    box = sheet.probe_box("tone/K/1")
    for name, orientation, polarity, edge in (
        ("toneK/left", "vertical", "falling", box["x0"]),
        ("toneK/right", "vertical", "rising", box["x1"]),
        ("toneK/top", "horizontal", "falling", box["y0"]),
        ("toneK/bottom", "horizontal", "rising", box["y1"]),
    ):
        if orientation == "vertical":
            patch = sheet.crop(box["y0"] + 60, box["y1"] - 60,
                               edge - 150, edge + 150)
            x_px, y_px = edge, (box["y0"] + box["y1"]) / 2.0
        else:
            patch = sheet.crop(edge - 150, edge + 150,
                               box["x0"] + 100, box["x1"] - 100)
            x_px, y_px = (box["x0"] + box["x1"]) / 2.0, edge
        rows.append(_edge_row(
            sheet, patch, target=name, family="solid-K-edge",
            orientation=orientation, polarity=polarity, x_px=x_px, y_px=y_px,
            halfwidth_px=80.0, mtf_floor=0.25))
        if verbose:
            _print_row(rows[-1])

    # (b) the two identity strips: long K boundaries, segmented along x,
    #     so the y-axis differentials get a platen-position series.
    for element_id in ("infra/report-0", "infra/report-1"):
        box = sheet.rectangle_box(element_id)
        x_lo = box["x0"] + 0.03 * (box["x1"] - box["x0"])
        x_hi = box["x1"] - 0.07 * (box["x1"] - box["x0"])
        span = (x_hi - x_lo) / segments
        for name, row_px in _strip_band_edges(sheet, element_id):
            for index in range(segments):
                x0 = x_lo + index * span
                patch = sheet.crop(row_px - 26, row_px + 26, x0, x0 + span)
                rows.append(_edge_row(
                    sheet, patch,
                    target=f"{element_id.split('/')[-1]}/{name}#{index}",
                    family="strip-rule-edge", orientation="horizontal",
                    polarity=("falling" if name.endswith("top")
                              else "rising"),
                    x_px=x0 + span / 2.0, y_px=row_px,
                    halfwidth_px=18.0, mtf_floor=0.35))
        if verbose:
            _print_family(rows, f"{element_id.split('/')[-1]}/")

    # (c) the K registration crosses: 3 x 3 platen positions, one
    #     vertical and one horizontal 2-dot bar each -> both axes.
    for row_index in range(3):
        for column_index in range(3):
            target = f"r{row_index}c{column_index}"
            for axis in ("x", "y"):
                measured = _stroke(sheet, target, "K", axis,
                                   ("R", "G", "B", "luma601"))
                result = measured["result"]
                # allow_intercept: a LINE's spectra are not DC-matched
                # (line_metrics normalizes by the peak, so the DC ratio
                # is the channels' ink contrast ratio).  See
                # compare_channels — without it the M281's slightly warm
                # K reads as +102 / -107 um^2 of pure artefact.
                differentials = compare_channels(
                    result, reference="G", scan_dpi=sheet.spec.scan_dpi,
                    mtf_floor=0.35, f_min_lp_per_mm=1.0,
                    allow_intercept=True)
                anchor = measured["positions"]["G"]
                rows.append({
                    "target": f"crossK/{target}/{axis}",
                    "family": "cross-bar", "axis": axis, "polarity": "line",
                    "x_px": anchor["x_px"], "y_px": anchor["y_px"],
                    "angle_deg": result.angle_deg,
                    "fit_rms_px": float("nan"),
                    "channels": {n: c.summary(sheet.spec.scan_dpi)
                                 for n, c in result.channels.items()},
                    "differentials": differentials,
                })
    if verbose:
        _print_family(rows, "crossK/")
    return rows


def _print_row(row: dict[str, Any]) -> None:
    print(f"  {row['target']:26s} axis {row['axis']} {row['polarity']:8s}")
    for name in ("R", "G", "B"):
        channel = row["channels"].get(name)
        if not channel:
            continue
        differential = row["differentials"].get(name, {})
        print(f"     {name}  MTF50 {channel['mtf50_lp_per_mm']:6.2f} "
              f"rise {channel['rise_10_90_um']:6.1f} um  "
              f"dsigma2 {differential.get('dsigma2_um2', float('nan')):+8.1f}"
              f" um^2  shift {differential.get('shift_dots', float('nan')):+.4f}"
              " dot")


def _print_family(rows: list[dict[str, Any]], prefix: str) -> None:
    members = [row for row in rows if row["target"].startswith(prefix)]
    if not members:
        return
    for name in ("R", "B"):
        values = np.array([row["differentials"].get(name, {}).get(
            "dsigma2_um2", np.nan) for row in members], dtype=float)
        shifts = np.array([row["differentials"].get(name, {}).get(
            "shift_dots", np.nan) for row in members], dtype=float)
        finite = int(np.isfinite(values).sum())
        print(f"  {prefix:26s} {name}-G n={finite:3d}  "
              f"dsigma2 {np.nanmean(values):+8.1f} um^2   "
              f"shift {np.nanmean(shifts):+.4f} dot")


# --------------------------------------------------------------------------
# per-family aggregation and the composed scanner sigma
# --------------------------------------------------------------------------

def aggregate_channels(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Family/axis means, with the polarity split into displacement + PSF.

    On an edge a measured per-channel offset is
    ``displacement + p * asymmetry``: a real lateral displacement moves a
    white->black and a black->white edge the same way, a channel-dependent
    PSF asymmetry moves them oppositely.  Hence the mean over the two
    polarities is registration and the half-difference is asymmetry.
    """
    families: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row['family']}/{row['axis']}"
        bucket = families.setdefault(key, {"n": 0, "channels": {}})
        bucket["n"] += 1
        for name, differential in row["differentials"].items():
            entry = bucket["channels"].setdefault(
                name, {"dsigma2_um2": [], "shift_dots": [],
                       "falling_dots": [], "rising_dots": []})
            entry["dsigma2_um2"].append(differential["dsigma2_um2"])
            entry["shift_dots"].append(differential["shift_dots"])
            if row["polarity"] in {"falling", "rising"}:
                entry[f"{row['polarity']}_dots"].append(
                    differential["shift_dots"])
    summary: dict[str, Any] = {}
    for key, bucket in families.items():
        stats: dict[str, Any] = {"n": bucket["n"]}
        for name, entry in bucket["channels"].items():
            channel = {metric: _mean_se(values)
                       for metric, values in entry.items()}
            falling = channel["falling_dots"]["mean"]
            rising = channel["rising_dots"]["mean"]
            if np.isfinite(falling) and np.isfinite(rising):
                channel["displacement_dots"] = (falling + rising) / 2.0
                channel["asymmetry_dots"] = (falling - rising) / 2.0
            stats[name] = channel
        summary[key] = stats
    return summary


SCANNER_FAMILY = "solid-K-edge"


def scanner_sigmas(knife: dict[str, Any],
                   rows_by_sheet: dict[str, Sequence[dict[str, Any]]]
                   ) -> dict[str, Any]:
    """Per-channel, per-axis scanner sigma: luma anchor + differentials.

    ``sigma_luma`` is the glass-level anchor from the e028 knife edge's
    narrowest snap-score groove, on the MTF50 basis that ``blue_mtf``'s
    ink arm used, so these numbers stay comparable with the recorded
    e028 ranking.  R and B follow from the measured
    ``sigma_c^2 - sigma_G^2`` of the ``solid-K-edge`` family — the only
    one whose +-80 px LSF window the self-test finds unbiased, and (see
    the module docstring) the only kind that replicates between sheets.

    The differentials are POOLED over every colour sheet supplied.
    There is one scanner and one capture dpi, so its sigma is one
    quantity; and the K patch gives only n=2 edges per axis per sheet,
    where the per-sheet estimate swings by +-3 um.  Pooling both halves
    the noise and, more importantly, makes the cross-engine ink
    comparison exact: any residual error in the anchor now shifts both
    engines by the same amount instead of one against the other.  The
    per-sheet values stay in the report as the replication check.
    """
    sigma_luma = MTF50_TO_SIGMA / knife["narrowest"]["mtf50_lp_per_mm"] * 1000.0
    out: dict[str, Any] = {
        "sigma_luma_um": sigma_luma,
        "sigma_luma_um_fwhm_basis": knife["narrowest"]["fwhm_um"] / 2.3548,
        "pooled_over": sorted(rows_by_sheet),
        "family": SCANNER_FAMILY,
        "basis": ("sigma_luma = 0.18739 / MTF50(narrowest knife groove); "
                  "R and B via the pooled solid-K-edge dsigma2 on the "
                  "matching axis; the groove is a line of unknown physical "
                  "width so sigma_luma is an UPPER bound and every ink "
                  "sigma below is correspondingly a LOWER bound"),
        "by_axis": {},
    }
    for axis in ("x", "y"):
        entry: dict[str, Any] = {"G": sigma_luma, "luma": sigma_luma}
        for name in ("R", "B"):
            values = [row["differentials"][name]["dsigma2_um2"]
                      for rows in rows_by_sheet.values() for row in rows
                      if row["family"] == SCANNER_FAMILY and row["axis"] == axis
                      and name in row["differentials"]]
            stats = _mean_se(values)
            delta = stats["mean"] if np.isfinite(stats["mean"]) else 0.0
            entry[name] = math.sqrt(max(sigma_luma ** 2 + delta, 1.0))
            entry[f"dsigma2_{name}_um2"] = delta
            entry[f"dsigma2_{name}_se_um2"] = stats.get("se", float("nan"))
            entry[f"dsigma2_{name}_n"] = stats.get("n", 0)
            entry[f"ratio_{name}_over_G"] = entry[name] / sigma_luma
        out["by_axis"][axis] = entry
    return out


def per_sheet_sigmas(knife: dict[str, Any],
                     per_family: dict[str, Any]) -> dict[str, Any]:
    """The same composition from ONE sheet — the replication check."""
    sigma_luma = MTF50_TO_SIGMA / knife["narrowest"]["mtf50_lp_per_mm"] * 1000.0
    out: dict[str, Any] = {"sigma_luma_um": sigma_luma, "by_axis": {}}
    for axis in ("x", "y"):
        stats = per_family.get(f"{SCANNER_FAMILY}/{axis}", {})
        entry: dict[str, Any] = {"G": sigma_luma, "luma": sigma_luma}
        for name in ("R", "B"):
            delta = stats.get(name, {}).get("dsigma2_um2", {}).get("mean", 0.0)
            entry[name] = math.sqrt(max(sigma_luma ** 2 + delta, 1.0))
            entry[f"dsigma2_{name}_um2"] = delta
            entry[f"ratio_{name}_over_G"] = entry[name] / sigma_luma
        out["by_axis"][axis] = entry
    return out


# --------------------------------------------------------------------------
# arm 2 — the toner half: per-ink edge width on the same sheet
# --------------------------------------------------------------------------

INK_TARGETS = (
    # probe id template, family, which sides to measure
    ("tone/{plane}/1", "tone-solid", ("left", "right", "top", "bottom")),
    ("selectivity/{plane}", "selectivity-solid", ("left", "right")),
)
SIDE_GEOMETRY = {
    "left": ("vertical", "falling", "x"),
    "right": ("vertical", "rising", "x"),
    "top": ("horizontal", "falling", "y"),
    "bottom": ("horizontal", "rising", "y"),
}


LSF_GRID_UM = np.arange(-160.0, 160.1, 5.0)
# Differencing stencil for the displayed LSF.  The ESF is binned at
# 0.25 px (1.3 um) and differentiating it there is pure bin noise; a
# +-10 um central difference broadens a sigma ~ 37 um line spread by
# 0.4 % and cuts the noise by about 4x.
LSF_STENCIL_UM = 10.0
# Plateaus are fitted, not assumed flat, beyond this distance from the
# 50 % crossing.  250 um is >= 3.8 sigma for the widest edge on either
# sheet, so no part of the transition is inside a plateau fit.
PLATEAU_GUARD_UM = 250.0


def _lsf_profile(result: Any, esf: np.ndarray,
                 um_per_px: float) -> list[float]:
    """Unit-peak LSF on a fixed micrometre grid, centred on the edge.

    Both polarities are carried in the SAME physical direction: for a
    rising step ``dESF/dx = PSF(x)`` and for a falling one ``-PSF(x)``,
    so flipping the falling case leaves the point spread in one common
    frame, ink on the left and paper on the right.  A falling-vs-rising
    difference in this profile is therefore NOT a scanner asymmetry —
    the scanner LSF is polarity-blind — it is a print-side
    leading/trailing edge asymmetry.
    """
    centres = np.asarray(result.bin_centers_px, dtype=np.float64)
    if centres.size < 8:
        return []
    profile = np.asarray(esf, dtype=np.float64)
    offsets_um = centres * um_per_px
    if profile[:8].mean() > profile[-8:].mean():
        profile = 1.0 - profile          # always ink(0) -> paper(1) in +x
    # Anchor on the 50 % CROSSING, not on a global LSF centroid: the ESF
    # runs +-760 um and its plateau noise, clipped positive, outweighs
    # the 25 um transition when it is given that lever arm (measured:
    # the centroid landed 160 um out).  Plateau noise never reaches 0.5.
    above = np.flatnonzero(profile >= 0.5)
    if not above.size:
        return []
    anchor = float(offsets_um[int(above[0])])
    near = np.abs(offsets_um - anchor) <= 80.0
    local = np.clip(np.gradient(profile, offsets_um)[near], 0.0, None)
    total = float(local.sum())
    if total > 0:
        anchor = float((offsets_um[near] * local).sum() / total)
    grid = LSF_GRID_UM + anchor
    forward = np.interp(grid + LSF_STENCIL_UM, offsets_um, profile)
    backward = np.interp(grid - LSF_STENCIL_UM, offsets_um, profile)
    lsf = (forward - backward) / (2.0 * LSF_STENCIL_UM)
    peak = float(np.max(np.abs(lsf)))
    return [float(value) for value in lsf / max(peak, 1e-12)]


def _ink_edge(sheet: Sheet, box: dict[str, float], side: str,
              channel: str, halfwidth_px: float = 80.0,
              pad: float = 150.0, inset: float = 80.0) -> dict[str, Any]:
    """One edge of one ink solid, read in one channel.

    ``sigma_rise_um`` (the 10-90 rise over 2.5631) is the statistic the
    ranking uses.  ``sigma_mtf50_um`` is carried as a DIAGNOSTIC only and
    should not be read as a second opinion: MTF50 on a ~120 um printed
    edge sits at 3-5 lp/mm, low enough that the LSF window and the
    plateau residual dominate it, and it swings by 2x between the two
    edges of one patch where the rise moves by 5 %.
    """
    orientation, polarity, axis = SIDE_GEOMETRY[side]
    index = CHANNEL_INDEX.get(channel)
    if orientation == "vertical":
        edge = box["x0"] if side == "left" else box["x1"]
        patch = sheet.crop(box["y0"] + inset, box["y1"] - inset,
                           edge - pad, edge + pad, index)
        x_px, y_px = edge, (box["y0"] + box["y1"]) / 2.0
    else:
        edge = box["y0"] if side == "top" else box["y1"]
        patch = sheet.crop(edge - pad, edge + pad,
                           box["x0"] + inset, box["x1"] - inset, index)
        x_px, y_px = (box["x0"] + box["x1"]) / 2.0, edge
    result = analyze_edge(patch, scan_dpi=sheet.spec.scan_dpi,
                          orientation=orientation,
                          channel_names=(channel,),
                          lsf_halfwidth_px=halfwidth_px,
                          plateau_guard_um=PLATEAU_GUARD_UM)
    measured = result.channels[channel]
    rise_um = measured.rise_10_90_px * sheet.spec.um_per_px
    slopes = measured.plateau_slopes_per_px or (float("nan"), float("nan"))
    return {
        "side": side, "axis": axis, "polarity": polarity,
        "channel": channel, "x_px": float(x_px), "y_px": float(y_px),
        "lsf_um": _lsf_profile(result, measured.esf, sheet.spec.um_per_px),
        "plateau_slope_ink_per_100um": (
            slopes[0] / sheet.spec.um_per_px * 100.0),
        "plateau_slope_paper_per_100um": (
            slopes[1] / sheet.spec.um_per_px * 100.0),
        "rise_10_90_um": rise_um,
        "sigma_rise_um": rise_um / RISE_TO_SIGMA,
        "sigma_mtf50_um": (MTF50_TO_SIGMA / measured.mtf50_lp_per_mm * 1000.0
                           if measured.mtf50_lp_per_mm > 0 else float("nan")),
        "mtf50_lp_per_mm": measured.mtf50_lp_per_mm,
        "contrast_linear": measured.contrast,
        "edge_fit_rms_px": result.fit_rms_px,
        "rows_used": result.rows_used,
    }


def ink_arm(sheet: Sheet, sigmas: dict[str, Any],
            verbose: bool = True) -> dict[str, Any]:
    """Per-ink edge width, each ink read in the channel that sees it."""
    rows: list[dict[str, Any]] = []
    colour = len(sheet.spec.channels) == 3
    for template, family, sides in INK_TARGETS:
        for plane in PLANES:
            probe_id = template.format(plane=plane)
            if probe_id not in sheet.probes:
                continue
            box = sheet.probe_box(probe_id)
            channels = ([INK_CHANNEL[plane]] if colour else ["luma"])
            if colour and plane == "K":
                channels = ["G", "R", "B"]
            for channel in channels:
                for side in sides:
                    row = _ink_edge(sheet, box, side, channel)
                    axis = row["axis"]
                    scanner = sigmas["by_axis"][axis].get(
                        channel, float("nan"))
                    row.update({
                        "ink": plane, "family": family, "probe": probe_id,
                        "sigma_scanner_um": scanner,
                        "sigma_ink_um": math.sqrt(max(
                            row["sigma_rise_um"] ** 2 - scanner ** 2, 0.0)),
                        "primary": channel == INK_CHANNEL[plane] or not colour,
                    })
                    rows.append(row)
                    if verbose:
                        print(f"  {family:18s} {plane} {side:7s} in "
                              f"{channel:4s}: rise {row['rise_10_90_um']:6.1f}"
                              f" um  sigma_tot {row['sigma_rise_um']:5.1f}"
                              f"  sigma_scan {scanner:5.1f}"
                              f"  sigma_ink {row['sigma_ink_um']:5.1f} um")
    return {"rows": rows, "per_ink": _per_ink(rows)}


def _per_ink(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Ink sigma with the leading/trailing asymmetry taken out.

    Every ink is measured on both polarities of both axes, and the
    polarity MEAN is the ranking statistic because the half-difference
    is large: on the M281 sheet M reads 10.6 um falling against 39.0 um
    rising, as big as the whole ink-to-ink spread.  That half-difference
    is PRINT-side, not scanner-side — the scanner's LSF is the same for
    a white->ink and an ink->white edge, so a polarity-dependent width
    can only come from the toner's own leading/trailing behaviour.
    """
    out: dict[str, Any] = {}
    for family in sorted({row["family"] for row in rows}):
        for ink in PLANES:
            members = [row for row in rows
                       if row["family"] == family and row["ink"] == ink
                       and row["primary"]]
            if not members:
                continue
            profiles = [row["lsf_um"] for row in members if row["lsf_um"]]
            entry: dict[str, Any] = {
                "n": len(members),
                "channel": members[0]["channel"],
                "sigma_ink_um": _mean_se(
                    [row["sigma_ink_um"] for row in members]),
                "sigma_total_um": _mean_se(
                    [row["sigma_rise_um"] for row in members]),
                "contrast_linear": _mean_se(
                    [row["contrast_linear"] for row in members]),
                "lsf_grid_um": LSF_GRID_UM.tolist(),
                "lsf_mean": (np.mean(profiles, axis=0).tolist()
                             if profiles else []),
            }
            for axis in ("x", "y"):
                falling = [row["sigma_ink_um"] for row in members
                           if row["axis"] == axis
                           and row["polarity"] == "falling"]
                rising = [row["sigma_ink_um"] for row in members
                          if row["axis"] == axis
                          and row["polarity"] == "rising"]
                if falling and rising:
                    entry[f"sigma_{axis}_um"] = (
                        float(np.mean(falling)) + float(np.mean(rising))) / 2.0
                    entry[f"asymmetry_{axis}_um"] = (
                        float(np.mean(falling)) - float(np.mean(rising))) / 2.0
            out[f"{family}/{ink}"] = entry
    return out


# --------------------------------------------------------------------------

def sheet_header(spec: SheetSpec, sheet: Sheet) -> dict[str, Any]:
    geometry = sheet.geometry
    return {
        "key": spec.key, "engine": spec.engine,
        "engine_label": spec.engine_label,
        "capture": str(spec.capture), "sha256": spec.sha256,
        "report": str(spec.report), "manifest": str(spec.manifest),
        "record": spec.record, "scan_dpi": spec.scan_dpi,
        "channels": list(spec.channels),
        "page_plan_semantic_sha256": sheet.page_plan_sha256,
        "geometry": {
            "affine_layout_to_scan": geometry["affine_layout_to_scan"],
            "rotation_deg": geometry["rotation_deg"],
            "scale_ratio_x": geometry["scale_ratio_x"],
            "scale_ratio_y": geometry["scale_ratio_y"],
            "corner_fit_rms_layout_dots":
                geometry["corner_fit_rms_layout_dots"],
            "internal_plus_rms_layout_dots":
                geometry["internal_plus"]["residual_rms_layout_dots"],
        },
    }


def measure_all(specs: Sequence[SheetSpec], knife: dict[str, Any],
                segments: int, arms: Iterable[str], verbose: bool = True
                ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Two passes: the scanner first, from every sheet, then the toner.

    The channel arm has to finish on ALL colour sheets before any ink
    sigma is composed, because the scanner anchor is pooled over them
    (``scanner_sigmas``).  Doing it in one pass per sheet would give
    each engine its own anchor and put the n=2 noise of the K patch
    straight into the cross-engine comparison this instrument exists to
    make.
    """
    arms = set(arms)
    sheets: dict[str, Any] = {}
    channel_rows: dict[str, list[dict[str, Any]]] = {}
    for spec in specs:
        with Sheet(spec) as sheet:
            sheets[spec.key] = sheet_header(spec, sheet)
            if len(spec.channels) != 3 or "channel" not in arms:
                continue
            if verbose:
                print(f"[{spec.key}] channel arm — K-toner differentials")
            rows = channel_arm(sheet, segments=segments, verbose=verbose)
            channel_rows[spec.key] = rows
            sheets[spec.key]["channel_arm"] = {
                "measurements": rows,
                "per_family": aggregate_channels(rows)}
            sheets[spec.key]["scanner_sigma_um_this_sheet"] = per_sheet_sigmas(
                knife, sheets[spec.key]["channel_arm"]["per_family"])
    sigmas = scanner_sigmas(knife, channel_rows)
    if verbose:
        for axis, entry in sigmas["by_axis"].items():
            print(f"[scanner] axis {axis}: sigma R {entry['R']:.2f}  G "
                  f"{entry['G']:.2f}  B {entry['B']:.2f} um   B/G "
                  f"{entry['ratio_B_over_G']:.3f}  R/G "
                  f"{entry['ratio_R_over_G']:.3f}  (pooled n="
                  f"{entry['dsigma2_B_n']})")
    for spec in specs:
        out = sheets[spec.key]
        out["scanner_sigma_um"] = sigmas
        with Sheet(spec) as sheet:
            if "ink" in arms:
                if verbose:
                    print(f"[{spec.key}] ink arm — scanner removed in "
                          "quadrature")
                out["ink_arm"] = ink_arm(sheet, sigmas, verbose=verbose)
            if "registration" in arms and len(spec.channels) == 3:
                if verbose:
                    print(f"[{spec.key}] registration arm — per-plane offsets")
                out["registration_arm"] = registration_arm(sheet,
                                                           verbose=verbose)
    return sheets, sigmas


def compare(sheets: dict[str, Any]) -> dict[str, Any]:
    """The two engines side by side, on the statistics that carry."""
    out: dict[str, Any] = {"ink_sigma_um": {}, "ink_order": {},
                           "scanner_replication": {}, "registration_um": {}}
    for key, sheet in sheets.items():
        ink = sheet.get("ink_arm", {}).get("per_ink", {})
        values = {name.split("/")[-1]: entry["sigma_ink_um"]["mean"]
                  for name, entry in ink.items()
                  if name.startswith("tone-solid/")}
        out["ink_sigma_um"][key] = values
        out["ink_order"][key] = sorted(values, key=lambda ink: -values[ink])
        # One scanner: the per-sheet channel differentials are a
        # REPLICATION test, not two measurements of two things.
        families = sheet.get("channel_arm", {}).get("per_family", {})
        out["scanner_replication"][key] = {
            family: {name: {"dsigma2_um2": stats[name]["dsigma2_um2"]["mean"],
                            "se": stats[name]["dsigma2_um2"].get("se"),
                            "n": stats[name]["dsigma2_um2"].get("n")}
                     for name in ("R", "B") if name in stats}
            for family, stats in families.items()}
        registration = sheet.get("registration_arm", {})
        if registration:
            out["registration_um"][key] = {
                "raw_mean": {plane: [entry["dx_um"]["mean"],
                                     entry["dy_um"]["mean"]]
                             for plane, entry in
                             registration["per_plane"].items()},
                "baseline_intercept": {
                    axis: registration["baseline_fit"][axis][
                        "intercept_um"]["mean"] for axis in ("x", "y")},
                "baseline_slope_um_per_mm": {
                    axis: registration["baseline_fit"][axis][
                        "slope_um_per_mm"]["mean"] for axis in ("x", "y")},
                "baseline_fit_residual_um": {
                    axis: registration["baseline_fit"][axis][
                        "fit_residual_um"]["mean"] for axis in ("x", "y")},
            }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sheets", default="e031-color,e028-color",
                        help="comma-separated keys from SHEETS "
                             f"({', '.join(SHEETS)})")
    parser.add_argument("--arms", default="channel,ink,registration",
                        help="which arms to run")
    parser.add_argument("--all", action="store_true",
                        help="every sheet (adds the two B/W K references)")
    parser.add_argument("--segments", type=int, default=8,
                        help="x segments per identity-strip edge")
    parser.add_argument("--tone", choices=("srgb", "gamma22", "none"),
                        default="srgb",
                        help="capture transfer function to invert; the "
                             "robustness control for every channel ratio")
    parser.add_argument("--verify-sha", action="store_true",
                        help="hash every input (the colour scans are 6.9 GB)")
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-figure", action="store_true")
    arguments = parser.parse_args(argv)
    keys = (list(COLOR_SHEETS) + list(BW_SHEETS) if arguments.all
            else [key.strip() for key in arguments.sheets.split(",")
                  if key.strip()])
    unknown = [key for key in keys if key not in SHEETS]
    if unknown:
        parser.error(f"unknown sheet(s) {unknown}; have {sorted(SHEETS)}")
    arguments.out.mkdir(parents=True, exist_ok=True)
    _edge.TONE_MODE = arguments.tone
    root = _evidence.resolve(arguments.evidence_root, tool="ink_psf")
    specs = {key: SHEETS[key].under(root) for key in keys}
    _evidence.need(root / KNIFE["path"],
                   *(path for key in keys for path in (
                       specs[key].capture, specs[key].report,
                       specs[key].manifest)), tool="ink_psf")

    report: dict[str, Any] = {
        "instrument": "measure/scanner/ink_psf.py",
        "purpose": ("E6 — replicate the per-ink PSF on healthy toner: "
                    "docs/INDEPENDENT-PLANES.md 2.8 / 4.I item 3, "
                    "docs/CHARACTERIZE-WORKPLAN.md W11 item 3"),
        "scanner": "Canon LiDE 400 (CIS), 4800 dpi, one scanner of record",
        "generated_unix": time.time(),
        "tone_curve": arguments.tone,
        "knife_anchor_input": {"path": str(root / KNIFE["path"]),
                               "sha256": KNIFE["sha256"],
                               "record": KNIFE["record"]},
        "sheets": {},
    }
    if arguments.verify_sha:
        checks = {"knife": (root / KNIFE["path"], KNIFE["sha256"])}
        for key in keys:
            checks[key] = (specs[key].capture, specs[key].sha256)
        report["sha_verification"] = {}
        for name, (path, expected) in checks.items():
            measured = sha256_of(path) if path.exists() else None
            report["sha_verification"][name] = {
                "path": str(path), "expected": expected,
                "measured": measured, "ok": measured == expected}
            print(f"  sha {name:12s} {'OK' if measured == expected else 'MISMATCH'}")

    print("[knife] glass-level luma anchor (shared: one scanner)")
    knife = measure_knife(float(KNIFE["dpi"]), root, verbose=False)
    report["knife"] = knife
    narrowest = knife["narrowest"]
    print(f"  narrowest groove: FWHM {narrowest['fwhm_um']:.1f} um  "
          f"MTF50 {narrowest['mtf50_lp_per_mm']:.2f}  "
          f"MTF10 {narrowest['mtf10_lp_per_mm']:.2f} lp/mm "
          f"(028.4 record: ~17 lp/mm)")

    arms = [name.strip() for name in arguments.arms.split(",") if name.strip()]
    sheets, sigmas = measure_all([specs[key] for key in keys], knife,
                                 arguments.segments, arms)
    report["sheets"] = sheets
    report["scanner_sigma_um"] = sigmas
    report["comparison"] = compare(sheets)

    suffix = "" if arguments.tone == "srgb" else f"-{arguments.tone}"
    path = arguments.out / f"e031-ink-psf{suffix}.json"
    path.write_text(json.dumps(report, indent=1, default=float))
    print(f"wrote {path}")
    if not arguments.no_figure:
        from ._figures import draw_ink_report
        figure = arguments.out / f"e031-ink-psf{suffix}.png"
        draw_ink_report(figure, report)
        print(f"wrote {figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
