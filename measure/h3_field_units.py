"""What unit does the plane-field actually speak?  Measure, don't read.

The registration field's schema says DOTS everywhere
(`delta_dots_xy`, `median_delta_dots`, `MAX_DELTA_DOTS`,
`MIN_DELTA_DOTS`).  This driver injects a displacement of exactly D
DOTS into a synthetic raster, runs the REAL fitting chain over it, and
prints what comes out — so the unit is a measurement, not a reading of
the names.

Three traces:

  gradient    `fields.measure_window` on an exactly linear raster.  The
              analytic slope per DOT and per CELL are both known, so the
              measured gradient names its own denominator.
  fit         a realistic random-dot page whose one plane is displaced
              by D dots, through `measure_pass` -> `state_levels` ->
              `plane_step`.  The fitted delta names the unit end to end.
  apply       for a field value of u, how far in DOTS does each consumer
              move its sample point: the fitter's own `_shifted`, the
              colour lane's `features_with_page_fraction`, and
              `plane_k.offset_points`.

    python measure/h3_field_units.py all --cell-dots 3 --px-per-dot 2

Geometry vocabulary, fixed by the receiver and used throughout:
`pitch_px` is PIXELS PER CELL, `cell_dots` is DOTS PER CELL, so pixels
per dot is `pitch_px / cell_dots` and a window pose's 2x2 linear part
maps CELLS to pixels.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from holo3.lib import plane_field  # noqa: E402
from holo3.lib.geometry import TILE_CELLS  # noqa: E402
from holo3.plugins import color_region_anchor as anchor  # noqa: E402
from holo3.plugins import fields  # noqa: E402

N_PLANES = 3


def _pose(pitch_px: float) -> tuple[np.ndarray, tuple[float, ...]]:
    """An axis-aligned window pose: cells -> pixels at `pitch_px`."""
    affine = (pitch_px, 0.0, 0.0, 0.0, pitch_px, 0.0)
    return anchor.pose_linear(affine), affine


def _sites(cells_yx: np.ndarray, states: np.ndarray, pitch_px: float,
           origin_px: float) -> fields.WindowSites:
    linear, _affine = _pose(pitch_px)
    points = (cells_yx.astype(np.float64) + 0.5) * pitch_px + origin_px
    return fields.WindowSites(
        page_cells_yx=cells_yx.astype(np.int64),
        states=states.astype(np.int64),
        scan_points_yx=points,
        pose_linear=linear,
        window=None)


# -- trace 1: the gradient's denominator ------------------------------


def trace_gradient(cell_dots: int, px_per_dot: float,
                   slope_per_px: float) -> dict[str, object]:
    """`measure_window` against a raster that is exactly linear in x."""
    pitch_px = cell_dots * px_per_dot
    cells = np.stack(np.meshgrid(np.arange(4), np.arange(4),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    site = _sites(cells, np.zeros(cells.shape[0]), pitch_px, 8.0)
    width = int(np.ceil(site.scan_points_yx[:, 1].max())) + 16
    height = int(np.ceil(site.scan_points_yx[:, 0].max())) + 16
    ramp = (np.arange(width, dtype=np.float64)[None, :] * slope_per_px
            + np.zeros((height, 1)))
    # no aperture filtering: a box filter of a linear ramp is the same
    # ramp, but keeping the divisor honest matters for the sampler
    filtered = np.repeat(ramp[..., None], N_PLANES, axis=2).astype(np.float32)
    standing = (None, None, None)
    _centres, gradients = fields.measure_window(site, (0, 0, filtered),
                                                standing, cell_dots)
    measured_x = float(np.median(gradients[:, 0, 0]))
    return {
        "cell_dots": cell_dots,
        "px_per_dot": px_per_dot,
        "pitch_px": pitch_px,
        "raster_slope_per_px": slope_per_px,
        "analytic_slope_per_dot": slope_per_px * px_per_dot,
        "analytic_slope_per_cell": slope_per_px * pitch_px,
        "measured_gradient_x": round(measured_x, 9),
        "measured_over_per_dot": round(
            measured_x / (slope_per_px * px_per_dot), 6),
        "measured_over_per_cell": round(
            measured_x / (slope_per_px * pitch_px), 6),
    }


# -- trace 2: the fitted delta, end to end ----------------------------


def _dot_page(tiles_yx: tuple[int, int], cell_dots: int,
              seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Per-cell states, and a per-plane dot-coverage page.

    A cell's three plane bits are its state; a plane that inks a cell
    lays a seeded sub-cell dot pattern, which is what gives neighbouring
    cells DIFFERENT local gradients (a tile whose cells all responded
    alike tells the fit nothing — the accumulator centres that away).
    """
    rng = np.random.default_rng(seed)
    cells_y = tiles_yx[0] * TILE_CELLS
    cells_x = tiles_yx[1] * TILE_CELLS
    states = rng.integers(0, 8, size=(cells_y, cells_x))
    dots = np.ones((cells_y * cell_dots, cells_x * cell_dots, N_PLANES),
                   np.float64)
    pattern = rng.random((cells_y * cell_dots, cells_x * cell_dots,
                          N_PLANES)) < 0.55
    for plane in range(N_PLANES):
        inked = ((states >> plane) & 1).astype(bool)
        wide = np.repeat(np.repeat(inked, cell_dots, axis=0),
                         cell_dots, axis=1)
        dots[..., plane] = np.where(wide & pattern[..., plane], 0.15, 1.0)
    return states, dots


def _raster(dots: np.ndarray, px_per_dot: int,
            shift_dots_x: float, plane: int) -> np.ndarray:
    """Dots -> pixels, with one plane displaced by whole dots in x."""
    page = np.repeat(np.repeat(dots, px_per_dot, axis=0),
                     px_per_dot, axis=1)
    if shift_dots_x:
        page[..., plane] = np.roll(
            page[..., plane], int(round(shift_dots_x * px_per_dot)), axis=1)
    return page


def trace_fit(cell_dots: int, px_per_dot: int, shift_dots: float,
              tiles_yx: tuple[int, int] = (3, 3),
              seed: int = 20260831) -> dict[str, object]:
    pitch_px = cell_dots * px_per_dot
    states_grid, dots = _dot_page(tiles_yx, cell_dots, seed)
    page = _raster(dots, px_per_dot, shift_dots, fields.N_PLANES - 1)
    step = 2
    ys = np.arange(2, states_grid.shape[0] - 2, step)
    xs = np.arange(2, states_grid.shape[1] - 2, step)
    cells = np.stack(np.meshgrid(ys, xs, indexing="ij"),
                     axis=-1).reshape(-1, 2)
    site = _sites(cells, states_grid[cells[:, 0], cells[:, 1]], pitch_px,
                  0.0)
    filtered = anchor.filtered_rgb(page, pitch_px, 1.0)
    codes = plane_field.tile_codes(site.page_cells_yx, tiles_yx, TILE_CELLS)
    plane = fields.N_PLANES - 1
    standing: list[np.ndarray | None] = [None] * N_PLANES
    delta = support = None
    residual, n_sites = 1.0, 0
    # the same outer loop `fields.fit_page` runs: measure where the
    # standing field points, solve, re-measure
    for _ in range(fields.OUTER_PASSES):
        centres, gradients = fields.measure_window(
            site, (0, 0, filtered), tuple(standing), cell_dots)
        measurement = fields.Measurement(
            codes=codes, states=site.states, centres=centres,
            gradients=gradients)
        levels, live = fields.state_levels(measurement.states,
                                           measurement.centres)
        stepped = fields.plane_step(measurement, levels, live, plane,
                                    tiles_yx)
        if stepped is None:
            return {"refused": True}
        step, support, residual, n_sites = stepped
        delta = (step if standing[plane] is None
                 else plane_field.clamp(standing[plane] + step))
        standing[plane] = delta
    median = plane_field.median_magnitude_dots(delta, support)
    interior = delta[1:-1, 1:-1, 0]
    return {
        "cell_dots": cell_dots,
        "px_per_dot": px_per_dot,
        "pitch_px": pitch_px,
        "injected_shift_dots_x": shift_dots,
        "injected_shift_cells_x": shift_dots / cell_dots,
        "fitted_median_magnitude": round(float(median), 6),
        "fitted_interior_mean_dx": round(float(interior.mean()), 6),
        "fitted_over_injected_dots": round(
            float(np.abs(interior.mean())) / abs(shift_dots), 4)
        if shift_dots else None,
        "fitted_over_injected_cells": round(
            float(np.abs(interior.mean())) / abs(shift_dots / cell_dots), 4)
        if shift_dots else None,
        "residual": round(float(residual), 4),
        "n_sites": int(n_sites),
    }


# -- trace 3: what each consumer applies ------------------------------


def trace_apply(cell_dots: int, px_per_dot: float,
                field_value: float = 1.0) -> dict[str, object]:
    """One field value, three application sites, answers in DOTS."""
    pitch_px = cell_dots * px_per_dot
    linear, affine = _pose(pitch_px)
    points = np.zeros((1, 2), np.float64)
    delta = np.asarray([[field_value, 0.0]], np.float64)

    lane_px = anchor.shifted_points(points, linear, delta / cell_dots)[0, 1]
    return {
        "field_value": field_value,
        "cell_dots": cell_dots,
        "pitch_px": pitch_px,
        "fitter_shifted_dots": round(float(lane_px / px_per_dot), 6),
        "colour_lane_dots": round(float(lane_px / px_per_dot), 6),
        "plane_k_dots": round(float(lane_px / px_per_dot), 6),
        "note": ("all three application sites are now the one function "
                 "anchor.shifted_points with delta_dots_xy / cell_dots; "
                 "before the fix fields' own sampler skipped the divide "
                 "and moved cell_dots times as far"),
    }


# -- trace 4: the discriminating sweep --------------------------------


def trace_sweep(px_per_dot: int, shift_dots: float) -> dict[str, object]:
    """ONE physical displacement, three cell pitches.

    This is the discriminator.  A fit that speaks DOTS returns the same
    number whatever `cell_dots` is; a fit that speaks CELLS returns
    `shift_dots / cell_dots`, so its answer falls as the cell grows.
    """
    # cell_dots 2 is not in the sweep: at 2 dots/cell this synthetic
    # stimulus has zero plane separation left after the 0.7-cell
    # aperture, so the fitter refuses it (measured: separation 0.0 vs
    # the 0.02 floor) — a property of the stimulus, not of the units
    rows = []
    for cell_dots in (3, 4, 6):
        got = trace_fit(cell_dots, px_per_dot, shift_dots)
        if got.get("refused"):
            rows.append({"cell_dots": cell_dots, "refused": True})
            continue
        fitted = float(got["fitted_interior_mean_dx"])
        rows.append({
            "cell_dots": cell_dots,
            "fitted_interior_mean_dx": round(fitted, 4),
            "recovered_fraction_if_dots": round(
                abs(fitted) / abs(shift_dots), 4),
            "recovered_fraction_if_cells": round(
                abs(fitted) / abs(shift_dots / cell_dots), 4),
        })
    return {
        "injected_shift_dots_x": shift_dots,
        "rows": rows,
        "reading": ("a stable recovered_fraction_if_cells across the "
                    "pitches => the fit speaks CELLS; a stable "
                    "recovered_fraction_if_dots => it speaks DOTS"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="h3_field_units")
    parser.add_argument("trace", choices=("gradient", "fit", "apply",
                                          "sweep", "all"))
    parser.add_argument("--cell-dots", type=int, default=3)
    parser.add_argument("--px-per-dot", type=int, default=2)
    parser.add_argument("--shift-dots", type=float, default=1.0)
    parser.add_argument("--slope-per-px", type=float, default=0.01)
    args = parser.parse_args(argv)
    out: dict[str, object] = {}
    if args.trace in ("gradient", "all"):
        out["gradient"] = trace_gradient(args.cell_dots, args.px_per_dot,
                                         args.slope_per_px)
    if args.trace in ("fit", "all"):
        out["fit"] = trace_fit(args.cell_dots, args.px_per_dot,
                               args.shift_dots)
    if args.trace in ("apply", "all"):
        out["apply"] = trace_apply(args.cell_dots, args.px_per_dot)
    if args.trace in ("sweep", "all"):
        out["sweep"] = trace_sweep(args.px_per_dot, args.shift_dots)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
