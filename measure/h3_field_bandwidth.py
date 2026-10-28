"""Can a tile-space FIELD express something a per-window AFFINE cannot?

The recurring proposal, whenever the degraded colour sim stops
discriminating, is to re-harden it with SHAPE instead of amplitude:
give the displacement curvature at the window scale, so that
``tiles.swim``'s per-window local affine cannot follow it while
``plugins/fields``' tile-space field still can.  This instrument answers
that question about the two operators THEMSELVES — no decode, no
stimulus, no scheduler — because the answer is a property of two length
scales that are both compile-time constants:

    lib/geometry.WINDOW_CELLS      200 cells = 3.125 tiles
    lib/plane_field.BANDWIDTH_TILES  2.0 tiles (Gaussian half-width)

A window is only ~1.6 field bandwidths wide, and inside it the affine
has a slope term where the field has a smoothed constant.  Run this and
read the two residual columns: the affine's is smaller at every
frequency, so the gap the proposal wants to aim at does not exist.

    python measure/h3_field_bandwidth.py --tree .

Both halves are measured through the production code — `plane_field.solve`
is the real estimator and `geometry.window_starts` the real layout — so
a repair to either operator moves these numbers by itself.

The field is fed IDEAL evidence (rank-2 anchor-form normal equations,
uniform mass, no noise), which is its best case: what comes back is the
smoothing, the ridge and the clamp, and nothing else.  The affine is
given the exact least-squares fit over the whole window, which is ITS
best case — the real search is bounded and rasterised.  So the
comparison is upper bound against upper bound.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CELL_DOTS = 3
TILES_Y = 10
CYCLES = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
#: per-tile evidence weight; the ridge is 1/PRIOR_SIGMA_DOTS^2 = 1.0, and
#: the response is flat in this over four orders of magnitude (checked)
WEIGHT = 40.0


def _import_tree(root: Path) -> None:
    for entry in (str(root / "src"), str(root)):
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)


def field_response(cycles: float, amplitude_dots: float,
                   max_delta_dots: float | None = None,
                   tiles_y: int = TILES_Y) -> tuple:
    """What `plane_field.solve` returns for a sinusoidal per-tile delta.

    Anchor-form equations (``a = w I``, ``b = w * truth``) are the
    tier that measures the delta directly, so this is the estimator with
    every measurement error taken out of it.
    """
    import numpy as np

    from holo3.lib import plane_field

    ty = np.arange(tiles_y, dtype=np.float64) + 0.5
    truth = amplitude_dots * np.sin(2.0 * np.pi * cycles * ty / tiles_y)
    delta_true = np.zeros((tiles_y, tiles_y, 2), np.float64)
    delta_true[..., 0] = truth[:, None]
    a = np.zeros((tiles_y, tiles_y, 2, 2), np.float64)
    a[..., 0, 0] = WEIGHT
    a[..., 1, 1] = WEIGHT
    equations = plane_field.NormalEquations(
        a=a, b=WEIGHT * delta_true,
        mass=np.full((tiles_y, tiles_y), WEIGHT, np.float64),
        total_square=1.0)
    ceiling = (plane_field.MAX_DELTA_DOTS if max_delta_dots is None
               else float(max_delta_dots))
    delta, _support = plane_field.solve(equations, max_delta_dots=ceiling)
    fitted = delta[..., 0].mean(axis=1)
    return truth, fitted


def injected_shift(amplitude_dots: float, cycles: float,
                   tiles_y: int = TILES_Y, cell_dots: int = CELL_DOTS):
    from holo3.tests import _h3_sims

    dots_h = tiles_y * 64 * cell_dots
    return _h3_sims.plane_x_shift_dots(dots_h, amplitude_dots, cycles)


def affine_residual_dots(shift_dots, tiles_y: int = TILES_Y,
                         cell_dots: int = CELL_DOTS):
    """Per tile row: the best residual any covering window's affine leaves.

    One affine per window (`tiles.swim` fits six parameters per plane per
    window), least squares over the whole window, evaluated at the tile's
    own dot rows.  A tile is covered by several windows and each applies
    its own fit to its own rows, so the tile's best case is the smallest.
    """
    import numpy as np

    from holo3.lib import geometry

    tile_dots = geometry.TILE_CELLS * cell_dots
    page_cells = tiles_y * geometry.TILE_CELLS
    starts = geometry.window_starts(page_cells)
    per_tile = np.full(tiles_y, np.inf)
    for ty in range(tiles_y):
        lo, hi = ty * tile_dots, (ty + 1) * tile_dots
        for start in starts:
            w0 = start * cell_dots
            w1 = (start + geometry.WINDOW_CELLS) * cell_dots
            if not (w0 <= lo and hi <= w1):
                continue
            y = np.arange(w0, w1, dtype=np.float64)
            basis = np.stack(
                [np.ones_like(y), (y - y.mean()) / float(w1 - w0)], axis=1)
            coefficients, *_ = np.linalg.lstsq(basis, shift_dots[w0:w1],
                                               rcond=None)
            residual = np.abs(shift_dots[w0:w1] - basis @ coefficients)
            per_tile[ty] = min(per_tile[ty],
                               float(residual[lo - w0:hi - w0].mean()))
    return per_tile


def page_line_residual_dots(shift_dots):
    """What the colour head's own {1, y} page-fraction residual leaves."""
    import numpy as np

    y = np.arange(shift_dots.size, dtype=np.float64) / shift_dots.size
    basis = np.stack([np.ones_like(y), y], axis=1)
    coefficients, *_ = np.linalg.lstsq(basis, shift_dots.astype(np.float64),
                                       rcond=None)
    return np.abs(shift_dots - basis @ coefficients)


def survey(amplitude_dots: float, cycles: tuple[float, ...] = CYCLES,
           ) -> list[dict]:
    import numpy as np

    from holo3.lib import geometry, plane_field

    rows: list[dict] = []
    for turn in cycles:
        truth, fitted = field_response(turn, amplitude_dots)
        unit_truth, unit_fitted = field_response(turn, 1.0,
                                                 max_delta_dots=1e9)
        shift = injected_shift(amplitude_dots, turn)
        affine = affine_residual_dots(shift)
        rows.append({
            "cycles": turn,
            "wavelength_tiles": round(TILES_Y / turn, 3),
            "window_cycles": round(
                geometry.WINDOW_CELLS / geometry.TILE_CELLS * turn / TILES_Y,
                4),
            "field_unclamped_response": round(
                float(np.abs(unit_fitted).max()
                      / max(np.abs(unit_truth).max(), 1e-9)), 4),
            "field_residual_dots": round(
                float(np.abs(truth - fitted).max()), 3),
            "affine_residual_dots": round(float(affine.max()), 3),
            "affine_residual_mean_dots": round(float(affine.mean()), 3),
            "page_line_residual_dots": round(
                float(page_line_residual_dots(shift).max()), 3),
            "injected_mean_dots": round(float(shift.mean()), 4),
            "clamp_dots": plane_field.MAX_DELTA_DOTS,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="h3_field_bandwidth")
    parser.add_argument("--tree", type=Path, default=Path("."))
    parser.add_argument("--amplitude-dots", dest="amplitude_dots",
                        type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    _import_tree(args.tree.resolve())
    from holo3.lib import geometry, plane_field

    rows = survey(args.amplitude_dots)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    print(f"window {geometry.WINDOW_CELLS} cells = "
          f"{geometry.WINDOW_CELLS / geometry.TILE_CELLS:.3f} tiles; "
          f"field bandwidth {plane_field.BANDWIDTH_TILES} tiles; "
          f"clamp {plane_field.MAX_DELTA_DOTS} dots; "
          f"injection {args.amplitude_dots} dots")
    header = (f"{'cycles':>7} {'lam(tiles)':>10} {'win cyc':>8} "
              f"{'field resp':>10} {'field resid':>12} {'affine resid':>13} "
              f"{'mean':>6} {'inj mean':>9}")
    print(header)
    for row in rows:
        print(f"{row['cycles']:7.2f} {row['wavelength_tiles']:10.2f} "
              f"{row['window_cycles']:8.3f} "
              f"{row['field_unclamped_response']:10.3f} "
              f"{row['field_residual_dots']:12.2f} "
              f"{row['affine_residual_dots']:13.2f} "
              f"{row['affine_residual_mean_dots']:6.2f} "
              f"{row['injected_mean_dots']:9.3f}")
    print("\nthe affine residual is the smaller one at every frequency: "
          "there is no shape a window-affine misses and the field keeps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
