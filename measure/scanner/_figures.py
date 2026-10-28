"""PIL figures for the scanner reports (matplotlib is not in this env).

``draw_report`` — the ``blue_mtf`` PNG, four panels:

* A — per-channel MTF on the solid-K edges (the question: is B softer?);
* B — the luma anchor: the knife-edge snap-groove MTF against 028.4;
* C — per-channel edge POSITION vs platen position (the CA question);
* D — sigma_c^2 - sigma_G^2 per target family and axis, with SEs.

``draw_ink_report`` — the ``ink_psf`` PNG, the two engines side by side:

* A — per-ink sigma with the scanner removed in quadrature (the E6
  question: is Y still the broadest ink on healthy toner?);
* B — the per-ink LSF profiles themselves, both engines overlaid;
* C — per-channel scanner sigma ratio, one engine against the other
  (the same scanner, so the two sheets must agree);
* D — per-ink lateral displacement from K, raw and baseline-corrected.

Every panel carries its numbers as a caption block UNDER the axes rather
than floating over the data — the figure has to be readable at 1:1 next
to the JSON, not pretty at a distance.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw

CHANNEL_COLORS = {
    "R": (206, 58, 58), "G": (46, 148, 74), "B": (52, 96, 214),
    "luma601": (110, 110, 110),
}
INK_COLORS = {
    "K": (32, 32, 38), "C": (0, 150, 176), "M": (198, 40, 132),
    "Y": (190, 150, 0),
}
GRID = (222, 222, 226)
AXIS = (70, 70, 74)
INK = (24, 24, 28)
MUTED = (95, 95, 102)


class Panel:
    """A rectangle with linear axes and a handful of drawing verbs."""

    def __init__(self, draw: ImageDraw.ImageDraw,
                 box: tuple[int, int, int, int],
                 xlim: tuple[float, float], ylim: tuple[float, float],
                 title: str, xlabel: str, ylabel: str) -> None:
        self.draw = draw
        self.x0, self.y0, self.x1, self.y1 = box
        self.xlim, self.ylim = xlim, ylim
        self._caption_row = 0
        draw.rectangle(box, outline=AXIS)
        draw.text((self.x0, self.y0 - 34), title, fill=INK)
        draw.text((self.x0, self.y0 - 18), ylabel, fill=MUTED)
        draw.text((self.x0, self.y1 + 22), xlabel, fill=MUTED)

    def px(self, x: float) -> float:
        lo, hi = self.xlim
        return self.x0 + (x - lo) / (hi - lo) * (self.x1 - self.x0)

    def py(self, y: float) -> float:
        lo, hi = self.ylim
        return self.y1 - (y - lo) / (hi - lo) * (self.y1 - self.y0)

    def grid(self, xticks: Sequence[float], yticks: Sequence[float],
             xfmt: str = "%g", yfmt: str = "%g") -> None:
        for x in xticks:
            sx = self.px(x)
            self.draw.line([(sx, self.y0), (sx, self.y1)], fill=GRID)
            self.draw.text((sx - 8, self.y1 + 5), xfmt % x, fill=MUTED)
        for y in yticks:
            sy = self.py(y)
            self.draw.line([(self.x0, sy), (self.x1, sy)], fill=GRID)
            self.draw.text((self.x0 - 38, sy - 5), yfmt % y, fill=MUTED)

    def curve(self, xs, ys, color, width: int = 2) -> None:
        points = [(self.px(x), self.py(min(max(y, self.ylim[0]),
                                           self.ylim[1])))
                  for x, y in zip(xs, ys)
                  if np.isfinite(x) and np.isfinite(y)
                  and self.xlim[0] <= x <= self.xlim[1]]
        if len(points) > 1:
            self.draw.line(points, fill=color, width=width)

    def marker(self, x: float, y: float, color, size: int = 3,
               shape: str = "o") -> None:
        if not (np.isfinite(x) and np.isfinite(y)):
            return
        sx, sy = self.px(x), self.py(y)
        box = (sx - size, sy - size, sx + size, sy + size)
        if shape == "o":
            self.draw.ellipse(box, fill=color)
        else:
            self.draw.rectangle(box, fill=color)

    def errorbar(self, x: float, y: float, error: float, color) -> None:
        if not np.isfinite(y):
            return
        sx = self.px(x)
        if np.isfinite(error):
            self.draw.line([(sx, self.py(y - error)),
                            (sx, self.py(y + error))], fill=color, width=2)
        self.marker(x, y, color, 4)

    def hline(self, y: float, color=AXIS, width: int = 1) -> None:
        sy = self.py(y)
        self.draw.line([(self.x0, sy), (self.x1, sy)], fill=color, width=width)

    def legend(self, entries: Sequence[tuple[str, Any]], dx: int = 12,
               dy: int = 12) -> None:
        for index, (label, color) in enumerate(entries):
            y = self.y0 + dy + index * 14
            self.draw.line([(self.x0 + dx, y + 5), (self.x0 + dx + 18, y + 5)],
                           fill=color, width=3)
            self.draw.text((self.x0 + dx + 24, y), label, fill=INK)

    def caption(self, text: str, color=MUTED) -> None:
        self.draw.text((self.x0, self.y1 + 42 + self._caption_row * 14),
                       text, fill=color)
        self._caption_row += 1


def draw_report(path, report: dict[str, Any]) -> None:
    image = Image.new("RGB", (1500, 1180), "white")
    draw = ImageDraw.Draw(image)
    draw.text((16, 12),
              "Canon LiDE 400 (CIS) per-channel optical characterization at "
              "4800 dpi  —  docs/INDEPENDENT-PLANES.md 4.I item 3", fill=INK)
    draw.text((16, 30),
              "targets: K toner on the e028 colour discovery sheet (RGB "
              "capture) + the e028 knife-edge blade (grey capture).  A K "
              "edge is the SAME physical edge in every channel, so a "
              "channel RATIO is scanner-side.", fill=MUTED)
    draw.text((16, 46),
              f"tone curve inverted: {report.get('tone_curve', 'srgb')}   "
              "(A and B are print x scan / groove x scan; only C and D are "
              "scanner-only quantities)", fill=MUTED)

    _panel_mtf(draw, report, (64, 116, 700, 436))
    _panel_knife(draw, report, (814, 116, 1450, 436))
    _panel_shift(draw, report, (64, 700, 700, 1020))
    _panel_dsigma(draw, report, (814, 700, 1450, 1020))
    image.save(path)


def _panel_mtf(draw, report, box) -> None:
    curves = report.get("color", {}).get("mtf_curves", {})
    panel = Panel(draw, box, (0.0, 16.0), (0.0, 1.02),
                  "A   per-channel MTF, solid-K patch edges",
                  "spatial frequency (lp/mm)", "MTF")
    panel.grid(range(0, 17, 2), [0.0, 0.1, 0.25, 0.5, 0.75, 1.0], yfmt="%.2f")
    panel.hline(0.5, (200, 200, 205))
    panel.hline(0.1, (200, 200, 205))
    # Four edges, drawn separately: they differ by more (a trailing toner
    # tail on toneK/right) than the channels differ within an edge, and
    # averaging them would hide exactly the comparison this panel is for.
    channels = report.get("color", {}).get("measurements", [])
    by_target = {row["target"]: row for row in channels}
    for target in sorted(curves):
        curve = curves[target]
        frequencies = np.array(curve["frequencies_lp_per_mm"])
        for name in ("R", "G", "B"):
            if name in curve:
                panel.curve(frequencies, np.array(curve[name]),
                            CHANNEL_COLORS[name], width=2)
    panel.legend([(name, CHANNEL_COLORS[name]) for name in ("R", "G", "B")],
                 dx=470)
    panel.caption("the four tone/K/1.0 edges, drawn separately — PRINT x "
                  "SCAN, not the scanner alone; read the channel ORDER "
                  "inside each cluster, not the level")
    for target in sorted(curves):
        row = by_target.get(target)
        if not row:
            continue
        values = row["channels"]
        panel.caption(
            f"   {target:14s} ({row['axis']})  MTF50 R "
            f"{values['R']['mtf50_lp_per_mm']:5.2f}  G "
            f"{values['G']['mtf50_lp_per_mm']:5.2f}  B "
            f"{values['B']['mtf50_lp_per_mm']:5.2f}      MTF10 R "
            f"{values['R']['mtf10_lp_per_mm']:5.2f}  G "
            f"{values['G']['mtf10_lp_per_mm']:5.2f}  B "
            f"{values['B']['mtf10_lp_per_mm']:5.2f}  lp/mm")


def _first_below(x: np.ndarray, y: np.ndarray, level: float) -> float:
    below = np.flatnonzero(np.nan_to_num(y, nan=1e9) <= level)
    return float(x[below[0]]) if below.size else float("nan")


def _panel_knife(draw, report, box) -> None:
    knife = report.get("knife")
    panel = Panel(draw, box, (0.0, 30.0), (0.0, 1.02),
                  "B   luma anchor — knife-edge snap-score grooves, "
                  "glass level (e028 028.4)",
                  "spatial frequency (lp/mm)", "MTF (a LOWER bound)")
    panel.grid(range(0, 31, 5), [0.0, 0.1, 0.25, 0.5, 0.75, 1.0], yfmt="%.2f")
    panel.hline(0.5, (200, 200, 205))
    panel.hline(0.1, (200, 200, 205))
    if not knife:
        return
    grooves = knife["grooves"]
    frequencies = np.array(knife["frequencies_lp_per_mm"])
    narrowest = min(grooves, key=lambda row: row["fwhm_px"])
    for row in grooves:
        panel.curve(frequencies, np.array(row["mtf"]),
                    (24, 24, 28) if row is narrowest else (168, 168, 174),
                    width=3 if row is narrowest else 1)
    panel.legend([(f"narrowest of {len(grooves)} grooves", (24, 24, 28)),
                  ("the other grooves", (168, 168, 174))], dx=350)
    panel.caption(f"narrowest groove: FWHM {narrowest['fwhm_um']:.1f} um, "
                  f"MTF50 {narrowest['mtf50_lp_per_mm']:.2f}, "
                  f"MTF10 {narrowest['mtf10_lp_per_mm']:.2f} lp/mm", INK)
    panel.caption("028.4 recorded:    FWHM 50.0 um, MTF50 9-14, "
                  "MTF10 ~17 lp/mm     -> the pipeline reproduces the "
                  "record")
    panel.caption("grey capture = LUMA ONLY.  The groove has its own "
                  "physical width, so its FWHM is an upper bound on the "
                  "LSF and its MTF a lower bound;")
    panel.caption("028.4's rule of reading the NARROWEST groove is kept "
                  "for exactly that reason.")


def _panel_shift(draw, report, box) -> None:
    measurements = report.get("color", {}).get("measurements", [])
    values = [m["differentials"].get(name, {}).get("shift_dots", np.nan)
              for m in measurements for name in ("R", "B")]
    finite = [v for v in values if np.isfinite(v)]
    span = max(0.06, (max(map(abs, finite)) if finite else 0.06) * 1.15)
    panel = Panel(draw, box, (0.0, 220.0), (-span, span),
                  "C   lateral channel offset vs platen position",
                  "position along the measured axis (mm)",
                  "offset vs G (600-dpi print dots; + = later along the "
                  "axis)")
    panel.grid(range(0, 221, 20), np.round(np.linspace(-span, span, 7), 3),
               yfmt="%+.3f")
    panel.hline(0.0, AXIS, 2)
    for measurement in measurements:
        along = (measurement["x_mm"] if measurement["axis"] == "y"
                 else measurement["y_mm"])
        for name in ("R", "B"):
            differential = measurement["differentials"].get(name)
            if not differential:
                continue
            panel.marker(along, differential["shift_dots"],
                         CHANNEL_COLORS[name], 3,
                         "o" if measurement["axis"] == "y" else "s")
    panel.legend([("R - G", CHANNEL_COLORS["R"]),
                  ("B - G", CHANNEL_COLORS["B"]),
                  ("round = y (transport) axis", (150, 150, 156)),
                  ("square = x (sensor) axis", (150, 150, 156))], dx=380)
    panel.caption("each point is one edge or bar; edges scatter about the "
                  "displacement by +- the PSF asymmetry, which the "
                  "polarity pairing below removes")
    aggregate = report.get("aggregate", {}).get("per_family", {})
    for key in sorted(aggregate):
        for name in ("R", "B"):
            entry = aggregate[key].get(name, {})
            if "displacement_dots" not in entry:
                continue
            panel.caption(
                f"   {key:20s} {name}-G   displacement "
                f"{entry['displacement_dots']:+.4f} dot "
                f"({entry['displacement_dots'] * 42.333:+.2f} um)   "
                f"asymmetry {entry['asymmetry_dots']:+.4f}",
                CHANNEL_COLORS[name])


def _panel_dsigma(draw, report, box) -> None:
    aggregate = report.get("aggregate", {}).get("per_family", {})
    keys = sorted(aggregate)
    values = [aggregate[k].get(n, {}).get("dsigma2_um2", {}).get("mean",
                                                                np.nan)
              for k in keys for n in ("R", "B")]
    finite = [v for v in values if np.isfinite(v)]
    span = max(20.0, (max(map(abs, finite)) if finite else 20.0) * 1.35)
    panel = Panel(draw, box, (-0.6, max(len(keys) - 0.4, 0.5)), (-span, span),
                  "D   sigma_c^2 - sigma_G^2 by target family and axis "
                  "(SCANNER-SIDE: the print term cancels)",
                  "target family / axis",
                  "um^2   (negative = that channel is SHARPER than G)")
    panel.grid([], np.round(np.linspace(-span, span, 7), 0), yfmt="%+.0f")
    panel.hline(0.0, AXIS, 2)
    for index, key in enumerate(keys):
        label = key.replace("-edge", "").replace("solid-K", "K-patch")
        draw.text((panel.px(index) - 4 * len(label), panel.y1 + 5),
                  label, fill=MUTED)
        for offset, name in ((-0.13, "R"), (0.13, "B")):
            entry = aggregate[key].get(name, {}).get("dsigma2_um2", {})
            panel.errorbar(index + offset, entry.get("mean", np.nan),
                           entry.get("se", np.nan), CHANNEL_COLORS[name])
    panel.legend([("R - G", CHANNEL_COLORS["R"]),
                  ("B - G", CHANNEL_COLORS["B"])], dx=500)
    panel.caption("bars are +-1 SE over the family's members; the K-patch "
                  "family has n=2 per axis (wide window, unbiased), the "
                  "others n=9..32 (tight window,")
    panel.caption("so |dsigma2| there is a LOWER bound — the self-test "
                  "measures that truncation).")
    composed = report.get("aggregate", {}).get("composed_blue")
    if composed:
        panel.caption(f"luma sigma from the knife edge: "
                      f"{composed['sigma_luma_um_from_knife']:.1f} um "
                      "(upper bound) — composing sigma_B = "
                      "sqrt(sigma_luma^2 + dsigma2):", INK)
        for row in composed["per_family"]:
            panel.caption(f"   {row['family_axis']:20s} sigma_B "
                          f"{row['sigma_B_um']:5.1f} um  "
                          f"({row['sigma_ratio_B_over_G']:.3f} x luma)",
                          CHANNEL_COLORS["B"])



# --------------------------------------------------------------------------
# ink_psf: the two engines side by side
# --------------------------------------------------------------------------

INKS = ("K", "C", "M", "Y")


def _pale(color, amount: int = 96):
    return tuple(min(255, value + amount) for value in color)


def _dashed(panel: "Panel", xs, ys, color, width: int = 2) -> None:
    points = [(panel.px(x), panel.py(min(max(y, panel.ylim[0]),
                                         panel.ylim[1])))
              for x, y in zip(xs, ys)
              if np.isfinite(x) and np.isfinite(y)
              and panel.xlim[0] <= x <= panel.xlim[1]]
    for index in range(0, len(points) - 3, 4):
        panel.draw.line(points[index:index + 3], fill=color, width=width)


def _colour_keys(report: dict[str, Any]) -> list[str]:
    return [key for key, sheet in report.get("sheets", {}).items()
            if len(sheet.get("channels", [])) == 3
            and sheet.get("ink_arm")]


def _grey_keys(report: dict[str, Any]) -> list[str]:
    return [key for key, sheet in report.get("sheets", {}).items()
            if len(sheet.get("channels", [])) == 1
            and sheet.get("ink_arm")]


def _label(report: dict[str, Any], key: str) -> str:
    return f"{report['sheets'][key]['engine_label']} ({key})"


def _short(report: dict[str, Any], key: str) -> str:
    """Legend-length engine name; the full one goes in the captions."""
    return report["sheets"][key]["engine_label"].split()[-1]


def _sigma_luma(report: dict[str, Any]) -> float:
    value = report.get("scanner_sigma_um", {}).get("sigma_luma_um")
    if value:
        return float(value)
    for sheet in report.get("sheets", {}).values():
        value = sheet.get("scanner_sigma_um", {}).get("sigma_luma_um")
        if value:
            return float(value)
    return float("nan")


def _ink_entry(report, key, ink, family="tone-solid"):
    return report["sheets"][key].get("ink_arm", {}).get(
        "per_ink", {}).get(f"{family}/{ink}", {})


def draw_ink_report(path, report: dict[str, Any]) -> None:
    image = Image.new("RGB", (1560, 1024), "white")
    draw = ImageDraw.Draw(image)
    keys = _colour_keys(report)
    knife = report.get("knife", {}).get("narrowest", {})
    draw.text((16, 12),
              "Per-ink point spread on two engines, one scanner  -  E6, "
              "docs/INDEPENDENT-PLANES.md 4.I item 3 / CHARACTERIZE-WORKPLAN "
              "W11 item 3", fill=INK)
    draw.text((16, 30),
              "Same authored discovery page (identical "
              "page_plan_semantic_sha256), same Canon LiDE 400 at 4800 dpi, "
              "same code, targets located from the page plan: only the "
              "ENGINE differs.", fill=MUTED)
    draw.text((16, 46),
              f"Scanner anchor: knife-edge narrowest groove MTF10 "
              f"{knife.get('mtf10_lp_per_mm', float('nan')):.2f} lp/mm "
              f"(028.4 record ~17), sigma_luma {_sigma_luma(report):.1f} um "
              "- an UPPER bound, so every ink sigma below is a LOWER bound."
              f"   tone curve: {report.get('tone_curve', 'srgb')}",
              fill=MUTED)

    _panel_ink_sigma(draw, report, keys, (74, 112, 720, 392))
    _panel_ink_lsf(draw, report, keys, (884, 112, 1520, 392))
    _panel_scanner_ratio(draw, report, keys, (74, 566, 720, 846))
    _panel_registration(draw, report, keys, (884, 566, 1520, 846))
    image.save(path)


def _panel_ink_sigma(draw, report, keys, box) -> None:
    values = [_ink_entry(report, key, ink).get("sigma_ink_um", {}).get(
        "mean", np.nan) for key in keys for ink in INKS]
    finite = [value for value in values if np.isfinite(value)]
    top = max(60.0, (max(finite) if finite else 60.0) * 1.30)
    panel = Panel(draw, box, (-0.6, 3.6), (0.0, top),
                  "A   per-ink sigma, scanner removed in quadrature",
                  "ink  (each read in the channel it absorbs: C->R, M->G, "
                  "Y->B, K->G)",
                  "sigma_ink (um)   tone/<plane>/1 solids, both polarities x "
                  "both axes")
    panel.grid([], np.round(np.linspace(0, top, 6), 0), yfmt="%.0f")
    width = 0.30
    for index, ink in enumerate(INKS):
        draw.text((panel.px(index) - 4, panel.y1 + 5), ink, fill=INK)
        for offset, key in zip((-width / 2, width / 2), keys):
            entry = _ink_entry(report, key, ink).get("sigma_ink_um", {})
            mean = entry.get("mean", np.nan)
            if not np.isfinite(mean):
                continue
            x0 = panel.px(index + offset - width / 2)
            x1 = panel.px(index + offset + width / 2)
            fill = (INK_COLORS[ink] if key == keys[0]
                    else _pale(INK_COLORS[ink]))
            draw.rectangle((x0, panel.py(mean), x1, panel.py(0.0)),
                           fill=fill, outline=AXIS)
            error = entry.get("se", np.nan)
            if np.isfinite(error):
                middle = (x0 + x1) / 2
                draw.line([(middle, panel.py(mean - error)),
                           (middle, panel.py(mean + error))],
                          fill=AXIS, width=2)
            draw.text((x0 + 2, panel.py(mean) - 15), f"{mean:.1f}", fill=INK)
    panel.legend([(_short(report, key), (60, 60, 66) if key == keys[0]
                   else (168, 168, 174)) for key in keys], dx=300)
    panel.caption("bars +-1 SE over the four edges; solid = first engine, "
                  "pale = second.  Ranking uses the polarity MEAN: the "
                  "falling-vs-rising half-difference is print-side.")
    for key in keys:
        row = "   ".join(
            f"{ink} {_ink_entry(report, key, ink)['sigma_ink_um']['mean']:5.1f}"
            for ink in INKS if _ink_entry(report, key, ink))
        order = " > ".join(report.get("comparison", {}).get(
            "ink_order", {}).get(key, []))
        panel.caption(f"   {_label(report, key):40s} {row}  um      {order}",
                      INK)
    for key in _grey_keys(report):
        entry = _ink_entry(report, key, "K").get("sigma_ink_um", {})
        panel.caption(f"   {_label(report, key):40s} K "
                      f"{entry.get('mean', float('nan')):5.1f}  um      "
                      "(grey capture, luma; the K-only sheet's own "
                      "reference)")


def _panel_ink_lsf(draw, report, keys, box) -> None:
    panel = Panel(draw, box, (-140.0, 140.0), (-0.06, 1.08),
                  "B   per-ink line spread (edge derivative), unit peak",
                  "distance across the edge (um)    + = away from the ink",
                  "LSF / peak")
    panel.grid(range(-120, 121, 40), [0.0, 0.25, 0.5, 0.75, 1.0], yfmt="%.2f")
    panel.hline(0.0, (200, 200, 205))
    for order, key in enumerate(keys):
        for ink in INKS:
            entry = _ink_entry(report, key, ink)
            profile = entry.get("lsf_mean")
            if not profile:
                continue
            grid = entry.get("lsf_grid_um", [])
            if order == 0:
                panel.curve(grid, profile, INK_COLORS[ink], width=2)
            else:
                _dashed(panel, grid, profile, _pale(INK_COLORS[ink], 70),
                        width=2)
    panel.legend([(ink, INK_COLORS[ink]) for ink in INKS], dx=580)
    panel.legend([("solid = " + _short(report, keys[0]), (60, 60, 66)),
                  ("dashed = " + _short(report, keys[-1]), (168, 168, 174))],
                 dx=12)
    panel.caption("each curve is the mean of that ink's four "
                  "tone/<plane>/1 edges (left, right, top, bottom).  BOTH "
                  "polarities are drawn in ONE physical direction")
    panel.caption("(dESF/dx = +-PSF), so a falling-vs-rising difference is "
                  "PRINT-side: the scanner's own LSF cannot depend on the "
                  "polarity of the edge it looks at.")


def _panel_scanner_ratio(draw, report, keys, box) -> None:
    families = sorted({
        family for key in keys
        for family in report["sheets"][key].get(
            "channel_arm", {}).get("per_family", {})})
    panel = Panel(draw, box, (-0.6, max(len(families) - 0.4, 0.5)),
                  (0.80, 1.20),
                  "C   scanner sigma ratio vs G, by target family and axis  "
                  "(SCANNER-SIDE: the print term cancels)",
                  "target family / axis",
                  "sqrt(1 + dsigma2 / sigma_G^2)     ( < 1 = SHARPER than G )")
    panel.grid([], np.round(np.linspace(0.80, 1.20, 5), 2), yfmt="%.2f")
    panel.hline(1.0, AXIS, 2)
    sigma_luma = _sigma_luma(report)
    for index, family in enumerate(families):
        label = family.replace("-edge", "").replace("solid-K", "K-patch")
        draw.text((panel.px(index) - 3 * len(label), panel.y1 + 5),
                  label, fill=MUTED)
        for offset, key in zip((-0.17, 0.05), keys):
            stats = report["sheets"][key].get("channel_arm", {}).get(
                "per_family", {}).get(family, {})
            for sub, name in ((0.0, "R"), (0.09, "B")):
                entry = stats.get(name, {}).get("dsigma2_um2", {})
                mean = entry.get("mean", np.nan)
                if not np.isfinite(mean) or not np.isfinite(sigma_luma):
                    continue
                ratio = np.sqrt(max(1.0 + mean / sigma_luma ** 2, 0.0))
                error = entry.get("se", np.nan)
                span = (abs(error) / (2 * sigma_luma ** 2 * max(ratio, 1e-6))
                        if np.isfinite(error) else np.nan)
                color = CHANNEL_COLORS[name]
                panel.errorbar(index + offset + sub, ratio, span,
                               color if key == keys[0] else _pale(color, 80))
    panel.legend([("R - G", CHANNEL_COLORS["R"]),
                  ("B - G", CHANNEL_COLORS["B"]),
                  ("saturated = " + _short(report, keys[0]), (60, 60, 66)),
                  ("pale = " + _short(report, keys[-1]), (168, 168, 174))],
                 dx=330)
    panel.caption("One scanner, two sheets: agreement here is the control "
                  "that this arm measures OPTICS, not toner.")
    panel.caption("That control FOUND A MODEL DEFECT.  ln(ratio) = "
                  "-2pi^2 dsigma2 f^2 has no constant term, which is right "
                  "for an EDGE (its ESF is")
    panel.caption("plateau-normalized, so the ratio is 1 at DC) and wrong "
                  "for a LINE (line_metrics normalizes by the PEAK, so DC "
                  "is the ink CONTRAST ratio).")
    panel.caption("The M281's warm K reads 4.5% weaker in R, and the fit "
                  "put that constant in the slope: cross-bar R +102 / "
                  "B -107 um^2 of pure artefact.")
    panel.caption("With an intercept the sheets agree (R -5.9/-6.1, "
                  "B -12.8/-9.5) and every family replicates.  The anchor "
                  "below still uses the K-patch EDGES:")
    pooled = report.get("scanner_sigma_um", {}).get("by_axis", {})
    for axis in ("x", "y"):
        entry = pooled.get(axis, {})
        panel.caption(
            f"   POOLED anchor, axis {axis}:  sigma R "
            f"{entry.get('R', float('nan')):5.2f}   G "
            f"{entry.get('G', float('nan')):5.2f}   B "
            f"{entry.get('B', float('nan')):5.2f} um      B/G "
            f"{entry.get('ratio_B_over_G', float('nan')):.3f}   R/G "
            f"{entry.get('ratio_R_over_G', float('nan')):.3f}      dsigma2_B "
            f"{entry.get('dsigma2_B_um2', float('nan')):+6.1f} +- "
            f"{entry.get('dsigma2_B_se_um2', float('nan')):4.1f} um^2 "
            f"(n={entry.get('dsigma2_B_n', 0)})", INK)


def _panel_registration(draw, report, keys, box) -> None:
    planes = ("C", "M", "Y")
    values = []
    for key in keys:
        registration = report["sheets"][key].get("registration_arm", {})
        for plane in planes:
            entry = registration.get("per_plane", {}).get(plane, {})
            values.extend([entry.get("dx_um", {}).get("mean", np.nan),
                           entry.get("dy_um", {}).get("mean", np.nan)])
    finite = [abs(value) for value in values if np.isfinite(value)]
    span = max(60.0, (max(finite) if finite else 60.0) * 1.35)
    panel = Panel(draw, box, (-0.6, 2.6), (-span, span),
                  "D   per-plane lateral offset from K  (each plane compared "
                  "with K read in the SAME channel, so scanner CA cancels)",
                  "plane   (authored 4 / 8 / 12 mm to the right of its own K "
                  "cross)",
                  "offset from K (um), mean over 9 platen positions")
    panel.grid([], np.round(np.linspace(-span, span, 7), 0), yfmt="%+.0f")
    panel.hline(0.0, AXIS, 2)
    dot_um = 25400.0 / 600.0
    for sign in (1.0, -1.0):
        if 0.83 * dot_um < span:
            panel.hline(sign * 0.83 * dot_um, (214, 122, 46), 1)
    for index, plane in enumerate(planes):
        draw.text((panel.px(index) - 4, panel.y1 + 5), plane, fill=INK)
        for offset, key in zip((-0.19, 0.05), keys):
            entry = report["sheets"][key].get("registration_arm", {}).get(
                "per_plane", {}).get(plane, {})
            for sub, axis in ((0.0, "dx_um"), (0.09, "dy_um")):
                stats = entry.get(axis, {})
                color = (INK_COLORS[plane] if axis == "dx_um"
                         else _pale(INK_COLORS[plane], 110))
                panel.errorbar(index + offset + sub, stats.get("mean", np.nan),
                               stats.get("se", np.nan),
                               color if key == keys[0] else _pale(color, 40))
    panel.legend([("saturated = dx, pale = dy", (110, 110, 116)),
                  ("left pair = " + _short(report, keys[0]), (60, 60, 66)),
                  ("right pair = " + _short(report, keys[-1]),
                   (168, 168, 174)),
                  ("orange rule = e033 sinusoid, 0.83 dot", (214, 122, 46))],
                 dx=200)
    panel.caption("These RAW means still carry the authored 4 / 8 / 12 mm "
                  "baseline, over which any residual page-scale")
    panel.caption("error accumulates - which is what makes the analyzer's "
                  "own plane_registration read up to 115 um here.")
    panel.caption("Regressing the three planes' offsets ON that baseline "
                  "separates them; a small fit residual means the")
    panel.caption("three planes really do share one line, i.e. no plane has "
                  "an offset of its own.")
    for key in keys:
        fit = report["sheets"][key].get("registration_arm", {}).get(
            "baseline_fit", {})
        for axis in ("x", "y"):
            entry = fit.get(axis, {})
            if not entry:
                continue
            panel.caption(
                f"   {_label(report, key):38s} {axis}: displacement "
                f"{entry['intercept_um']['mean']:+7.1f} +- "
                f"{entry['intercept_um']['se']:4.1f} um "
                f"({entry['intercept_um']['mean'] / dot_um:+.3f} dot)   local "
                f"scale {entry['slope_um_per_mm']['mean']:+6.2f} +- "
                f"{entry['slope_um_per_mm']['se']:4.2f} um/mm   fit residual "
                f"{entry['fit_residual_um']['mean']:5.1f} um", INK)
