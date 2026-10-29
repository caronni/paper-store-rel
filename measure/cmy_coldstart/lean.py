"""Y's lean toward M, on the raw field measurement before any solve (CMY-RECEIVER-PLAN A9; CMY-DESIGN §11 G12).

What: the 2x3 scrap the suite decodes (`holo.receiver.tests._h3_sims_cmy`, its seeded origin), rendered by the
suite's own renderer with M and Y at constant offsets from C (no drift), and measured where the field's evidence is
made: every (tile, plane) of the scrap's GT templates through `fields_collect.measure_window`, one window over the
scrap at the render's TRUE pose (composed by the production composer), each template weighted the way
`field_tiers.cross_talk_weights` weights it.  Per plane the mean raw x displacement over the scrap's tiles; Y - C,
Y - C minus the plant, and that excess as a share of (dM - dY) -- how far toward M Y reads.  Four arms:
  shipped     the stimulus as the suite renders it (`CMY_C2_GAIN_PX`, the cross-talk weights)
  gain 0      no dot gain
  no M ink    M's coverage cleared before the render (the templates, M's states included, unchanged)
  no weights  every template unweighted (`weights=None`)
at the plants (dM, dY) in dots: A (0.5, -0.5), A mirrored (-0.5, 0.5), Y alone (0.0, -1.0) and Z (0, 0).
Why: the grid's field reads Y about a third of the way toward M wherever the two differ (RESULTS-2026-10-12); this
separates the solve, the dot gain, M's ink and the cross-talk table as causes, on the measurement the solve consumes.
How: `python -m measure.cmy_coldstart.lean --out DIR` emits into DIR, renders in memory, writes DIR/lean.json and
prints the table (31 s on machine 1).

    cd <repo> && PYTHONPATH=src:. \\
        env/bin/python -u -m measure.cmy_coldstart.lean --out <dir>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

TILE_CELLS = 64
PLANES = ("C", "M", "Y")
SHAPE: tuple[int, int] = (2, 3)
PLANTS_DOTS: dict[str, tuple[float, float]] = {
    "A": (0.5, -0.5), "A mirrored": (-0.5, 0.5), "Y alone": (0.0, -1.0), "Z": (0.0, 0.0)}
#: name -> (the shipped dot gain, M's ink, the cross-talk weights)
ARMS: dict[str, tuple[bool, bool, bool]] = {
    "shipped": (True, True, True), "gain 0": (False, True, True), "no M ink": (True, False, True),
    "no weights": (True, True, False)}

Fresh = tuple[tuple[int, int, Any], ...]


def scrap_window(sims: Any, row: Any, origin: tuple[int, int], shape: tuple[int, int]) -> tuple[Any, Any]:
    """One window over the scrap at the render's own pose: page cell c at border + pitch * (c - its first cell) in
    the pixel-edge frame, half a pixel later than the native affine's."""
    from holo.receiver.plugins import fields_collect
    from holo.receiver.tests import _h3_fixture_geometry as geometry

    pitch_px = float(sims.CMY_C2_TILE_DOTS // TILE_CELLS * sims.CMY_C2_PX_PER_DOT)
    border_px = float(sims.COLOR_BORDER_DOTS * sims.CMY_C2_PX_PER_DOT)
    y0_cells, x0_cells = origin[0] * TILE_CELLS, origin[1] * TILE_CELLS
    extent_cells = (shape[0] * TILE_CELLS, shape[1] * TILE_CELLS)
    window_id = ("lean", 0, 0, (y0_cells, x0_cells, y0_cells + extent_cells[0], x0_cells + extent_cells[1]))
    affine = (pitch_px, 0.0, border_px - 0.5 - pitch_px * y0_cells,
              0.0, pitch_px, border_px - 0.5 - pitch_px * x0_cells)
    placement = geometry.window_placement(window_id, affine, geometry.grid_cells((0, 0), extent_cells))
    window = geometry.window_pose(row, placement)
    return window, fields_collect.cell_lookup(window.page_cells_yx, row.tiles_yx[1])


def gt_templates(row: Any, cells: np.ndarray, origin: tuple[int, int], shape: tuple[int, int],
                 cell_dots: int, weighted: bool) -> Fresh:
    """Every (tile, plane) of the scrap as a certified template of its GT bits."""
    from holo.receiver.format import tile_codec
    from holo.receiver.lib import plane_field
    from holo.receiver.plugins import field_tiers

    out: list[tuple[int, int, Any]] = []
    for ty in range(origin[0], origin[0] + shape[0]):
        for tx in range(origin[1], origin[1] + shape[1]):
            cut = (slice(ty * TILE_CELLS, (ty + 1) * TILE_CELLS), slice(tx * TILE_CELLS, (tx + 1) * TILE_CELLS))
            bits = np.stack([cells[p][cut] for p in range(3)], -1).reshape(-1, 3).astype(np.uint8)
            states = tile_codec.planes_to_states(bits)
            for plane in range(3):
                out.append((ty * row.tiles_yx[1] + tx, plane, field_tiers.Template(
                    page_cells_yx=field_tiers._tile_cells(ty, tx), bits=bits[:, plane],
                    source=plane_field.SOURCE_CERTIFIED, radius_dots=field_tiers.certified_radius_dots(cell_dots),
                    weights=field_tiers.cross_talk_weights(row, states, plane) if weighted else None)))
    return tuple(out)


def measure_arm(sims: Any, row: Any, window: Any, lookup: Any, scrap: np.ndarray, fresh: Fresh, cell_dots: int,
                plant_dots: tuple[float, float], gain_px: int, m_ink: bool) -> dict[str, Any]:
    """Render the scrap at one plant and read every template's raw displacement, no solve."""
    from holo.receiver.plugins import fields_collect
    from holo.receiver.tests import _h3_sims

    coverage = scrap.copy()
    if not m_ink:
        coverage[1] = 0.0
    px_per_dot = sims.CMY_C2_PX_PER_DOT
    d_m, d_y = plant_dots
    channel = sims.cmy_c2_channel(((0, 0), (round(d_m * px_per_dot), 0), (round(d_y * px_per_dot), 0)))
    image = _h3_sims._render_coverage(coverage, sims.COLOR_BORDER_DOTS, channel, upsample=px_per_dot,
                                      gain_px=gain_px)
    crop = fields_collect.owner_crop(window, (image[..., 0], image[..., 1], image[..., 2]))
    rows = fields_collect.measure_window(row, window, crop, lookup, fresh, cell_dots)
    delta = np.asarray(rows.delta_dots_xy, np.float64).reshape(-1, 2)
    plane_of = np.asarray(rows.plane, np.int64)
    raw = {name: (float(delta[plane_of == p, 0].mean()) if (plane_of == p).any() else None)
           for p, name in enumerate(PLANES)}
    excess = raw["Y"] - raw["C"] - d_y
    return {"raw_x_dots": {k: None if v is None else round(v, 3) for k, v in raw.items()},
            "rows": {name: int((plane_of == p).sum()) for p, name in enumerate(PLANES)},
            "m_minus_c": None if raw["M"] is None else round(raw["M"] - raw["C"], 3),
            "y_minus_c": round(raw["Y"] - raw["C"], 3), "y_minus_c_minus_plant": round(excess, 3),
            "toward_m": round(excess / (d_m - d_y), 3) if d_m != d_y else None}


def _signed(value: float | None, places: int = 3) -> str:
    return "-" if value is None else f"{value:+.{places}f}"


def row_text(r: dict[str, Any]) -> str:
    raw, n = r["raw_x_dots"], r["rows"]
    return (f"| {r['arm']} | {r['plant']} {tuple(r['plant_dots'])} | {_signed(raw['C'])} | {_signed(raw['M'])} | "
            f"{_signed(raw['Y'])} | {n['C']}/{n['M']}/{n['Y']} | {_signed(r['m_minus_c'])} | "
            f"{_signed(r['y_minus_c'])} | {_signed(r['y_minus_c_minus_plant'])} | {_signed(r['toward_m'], 2)} |")


HEADER = ("| arm | plant (dM, dY) | raw C | raw M | raw Y | rows C/M/Y | M - C | Y - C | Y - C - dY | share of "
          "dM - dY |\n|---|---|---|---|---|---|---|---|---|---|")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    from holo.receiver.format import identity
    from holo.receiver.tests import _h3_sims, _h3_sims_cmy as sims

    args.out.mkdir(parents=True, exist_ok=True)
    row = identity.resolve_format_ref(sims.CMY_C2_FORMAT_REF)
    _spec, coverage = sims._emit_cmy_c2(args.out)
    origin = sims.cmy_c2_crop_origin(SHAPE)
    step = sims.CMY_C2_TILE_DOTS
    cell_dots = step // TILE_CELLS
    scrap = coverage[:, origin[0] * step:(origin[0] + SHAPE[0]) * step,
                     origin[1] * step:(origin[1] + SHAPE[1]) * step]
    cells = coverage[:, ::cell_dots, ::cell_dots]
    window, lookup = scrap_window(sims, row, origin, SHAPE)
    fresh = {weighted: gt_templates(row, cells, origin, SHAPE, cell_dots, weighted) for weighted in (True, False)}
    print(HEADER, flush=True)
    results = []
    for plant, plant_dots in PLANTS_DOTS.items():
        for arm, (gain, m_ink, weighted) in ARMS.items():
            result = measure_arm(sims, row, window, lookup, scrap, fresh[weighted], cell_dots, plant_dots,
                                 sims.CMY_C2_GAIN_PX if gain else 0, m_ink)
            results.append({"arm": arm, "plant": plant, "plant_dots": list(plant_dots), **result})
            print(row_text(results[-1]), flush=True)
    meta = {"format": sims.CMY_C2_FORMAT_REF, "shape": list(SHAPE), "origin_tiles": list(origin),
            "gain_px": sims.CMY_C2_GAIN_PX, "sims_source": sims.SOURCE_DIGEST,
            "base_sims_source": _h3_sims.SOURCE_DIGEST}
    (args.out / "lean.json").write_text(json.dumps({"meta": meta, "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
