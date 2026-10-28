"""Which black things on the HCAL-R1 discovery page to read, and where.

The platen is 216 mm wide and a payload page covers essentially all of
it (sheet I prints to 4 mm margins), so a scanner field has to be
answered across the WHOLE width — including the outer 30 mm at each end,
which ``scanner/blue_mtf`` never sampled (its targets span x 35-155 mm).
That outer band is exactly where a lens' lateral chromatic aberration is
largest, so leaving it out would have left the question open at the only
place it could have been interesting.

Two kinds of target, chosen by what the estimator each one feeds needs:

* **marks** — small isolated K objects, read by ``_marks.mark_offsets``.
  They are the only structures the page puts at x ~ 4 mm and x ~ 206 mm
  (the printed edge ticks), and they give both axes from one object.
  The corner marks' chirality satellite sits inside the window and does
  not matter: a centroid DIFFERENCE cancels any channel-common shape.
* **edges** — K rectangles at least 4 mm on a side, read by
  ``scanner/_edge``'s slanted-edge engine, all four sides so each axis
  gets both polarities.  A real displacement moves both polarities the
  same way and a channel-dependent PSF skew moves them oppositely, so
  the pair separates the two — which is what tells us whether the mark
  arm's first moments are displacement or skew.

Everything is located through ``scanner/_sheet.Sheet`` (page manifest x
HCAL corner affine), never by pinned pixels, so one code path reads any
capture of this page.  Probes whose ``gap_mm`` puts them inside the
measured ~4.2 mm print clip (e028 §028.2) are not on paper at all and
are excluded by construction rather than by a contrast gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np

from scanner._sheet import Sheet

# e028 measured the M281's print clip at ~4.2 mm on all edges; a tick
# authored closer to the sheet edge than this is simply not printed.
PRINT_CLIP_MM: float = 4.0
MARK_PAD_MM: float = 0.85
EDGE_PAD_MM: float = 0.55
EDGE_INSET: float = 0.12          # trim each edge's ends by this fraction


@dataclass(frozen=True)
class MarkSpec:
    name: str
    family: str
    kind: str                     # "probe" | "rectangle"


@dataclass(frozen=True)
class EdgeSpec:
    name: str
    family: str
    kind: str
    segments: int = 1


@dataclass(frozen=True)
class EdgePatch:
    """One side of one rectangle, ready for ``analyze_edge``."""

    target: str
    family: str
    side: str                     # left | right | top | bottom
    axis: str                     # x (sensor) | y (transport)
    polarity: str                 # falling | rising
    segment: int
    orientation: str              # vertical | horizontal
    x_px: float
    y_px: float
    patch: np.ndarray


def mark_specs() -> list[MarkSpec]:
    """Small K marks, ordered so the platen extremes come first."""
    out: list[MarkSpec] = [
        MarkSpec(f"infra/corner-{n}", "corner-mark", "rectangle")
        for n in (1, 2, 3, 4)
    ]
    for edge in ("left", "right", "top", "bottom"):
        for gap in (4.0, 5.0, 6.0, 8.0, 10.0):
            if gap < PRINT_CLIP_MM:
                continue
            label = f"{gap:g}"
            out.append(MarkSpec(f"edge-tick/{edge}/{label}",
                                f"edge-tick-{edge}", "probe"))
    out += [MarkSpec(f"infra/plus-{n}", "plus-mark", "rectangle")
            for n in range(10)]
    out += [MarkSpec(f"registration/r{r}c{c}/K", "registration-cross",
                     "probe")
            for r in range(3) for c in range(3)]
    return out


def edge_specs() -> list[EdgeSpec]:
    """K rectangles big enough for the slanted-edge engine."""
    return [
        EdgeSpec("scanner/c3", "cell-field", "probe", segments=3),
        EdgeSpec("scanner/c2", "cell-field", "probe", segments=3),
        EdgeSpec("scanner/entropy", "cell-field", "probe", segments=2),
        EdgeSpec("tone/K/0.75", "tone-patch", "probe"),
        EdgeSpec("tone/K/0.9", "tone-patch", "probe"),
        EdgeSpec("tone/K/1", "solid-K", "probe"),
        EdgeSpec("tone/K/feed", "tone-profile", "probe", segments=3),
    ]


def _box(sheet: Sheet, spec: MarkSpec | EdgeSpec) -> dict[str, float] | None:
    try:
        if spec.kind == "rectangle":
            return sheet.rectangle_box(spec.name)
        return sheet.probe_box(spec.name)
    except KeyError:
        return None


def mark_patches(sheet: Sheet, specs: list[MarkSpec]
                 ) -> Iterator[tuple[MarkSpec, float, float, np.ndarray]]:
    """Yield ``(spec, x_px, y_px, patch)`` for every mark that is on the
    raster.  The crop is the authored box plus a fixed pad: deliberately
    TIGHT, because the registration crosses' C/M/Y siblings sit 4 mm away
    and a window wide enough to reach one would poison the red channel."""
    pad = MARK_PAD_MM / 25.4 * sheet.spec.scan_dpi
    for spec in specs:
        box = _box(sheet, spec)
        if box is None:
            continue
        try:
            patch = sheet.crop(box["y0"] - pad, box["y1"] + pad,
                               box["x0"] - pad, box["x1"] + pad)
        except ValueError:
            continue
        if patch.shape[2] < 3:
            continue
        yield spec, box["cx"], box["cy"], patch


def edge_patches(sheet: Sheet, specs: list[EdgeSpec]
                 ) -> Iterator[EdgePatch]:
    """Yield every side of every rectangle, split into ``segments``."""
    dpi = sheet.spec.scan_dpi
    pad = EDGE_PAD_MM / 25.4 * dpi
    for spec in specs:
        box = _box(sheet, spec)
        if box is None:
            continue
        width = box["x1"] - box["x0"]
        height = box["y1"] - box["y0"]
        if min(width, height) < 4.0 / 25.4 * dpi:
            continue
        for side in ("left", "right", "top", "bottom"):
            vertical = side in ("left", "right")
            polarity = "falling" if side in ("left", "top") else "rising"
            axis = "x" if vertical else "y"
            along = height if vertical else width
            inset = EDGE_INSET * along
            lo = (box["y0"] if vertical else box["x0"]) + inset
            hi = (box["y1"] if vertical else box["x1"]) - inset
            if hi - lo < 8:
                continue
            step = (hi - lo) / spec.segments
            cut = (box["x0"] if side == "left" else
                   box["x1"] if side == "right" else
                   box["y0"] if side == "top" else box["y1"])
            for index in range(spec.segments):
                a, b = lo + index * step, lo + (index + 1) * step
                try:
                    if vertical:
                        patch = sheet.crop(a, b, cut - pad, cut + pad)
                        x_px, y_px = cut, 0.5 * (a + b)
                    else:
                        patch = sheet.crop(cut - pad, cut + pad, a, b)
                        x_px, y_px = 0.5 * (a + b), cut
                except ValueError:
                    continue
                if patch.shape[2] < 3 or min(patch.shape[:2]) < 8:
                    continue
                yield EdgePatch(
                    target=spec.name, family=spec.family, side=side,
                    axis=axis, polarity=polarity, segment=index,
                    orientation="vertical" if vertical else "horizontal",
                    x_px=float(x_px), y_px=float(y_px), patch=patch)
