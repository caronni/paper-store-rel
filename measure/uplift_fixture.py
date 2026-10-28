"""Shared fixture for the supplemental-arm existence proofs.

Builds a synthetic printed colour page from a REAL emitted ground truth
(the colour sim's ``page000_gt.npy``), so every tile carries real codec
content and can actually certify, and renders it through a channel whose
photometry is deliberately per-WINDOW: a faint tone plus a gain and
offset that are constant within a window and step between windows.

That shape is the pathology A3 exists for, stated in the arm's own words
(COLOR-UPLIFT-PLAN §1, the HP channel's cm-scale C/M mottle plus process
banding): "a gain nearly constant WITHIN a window and different between
windows, which is exactly what a per-window photometric map can absorb
and a page-global model cannot".

THE TONE IS LOAD-BEARING, and the reason is measured
(COLOR-UPLIFT-MEASUREMENTS §5.4): at full contrast the eight states sit a
whole unit apart and a page-global QDA separates them through any gain a
valid gradient can apply, so NO photometric arm — right or wrong — can
earn its gate.  The holo3 colour sim renders at contrast 1.0 with no
noise, which is exactly that regime; the faint tone here is what makes
the question answerable at all.

Everything is seeded and deterministic.

CORRECTION 2026-08-31 — CORNER HALF-CELL REMOVED.  Until this date
``region_windows`` built its pose WITHOUT the half-cell that
``color_region.region_window`` composes, so it aimed the sampler at cell
CORNERS: a 3 px = 1.5 printed-dot registration error on every window,
which the sampler's 4 px aperture then turned into an even average over
the 2x2 cell junction.  Every plane read at a quarter of its true
contrast (isolated-plane read 31.5% cell error / contrast 0.073, against
0.002% / 0.292 on centres).  Every number measured through this fixture
before that date is a HANDICAPPED number; the arms' records carry their
own corrections.  See ``holo3/tests/_h3_fixture_geometry.py`` for the
mechanism, which that module states once for every fixture.

THE HAND-BUILT POSE IS GONE 2026-08-31, same day, second commit.  The
correction above put the half cell back; it left the WRONG FORM still
representable, and the same defect had already been found in three
fixtures on one day.  ``region_windows`` now states its geometry as a
``Placement`` and lets ``color_region.region_window`` — production —
compose the pose, so this file no longer spells a half cell at all.
Byte-identical to the corrected hand-built form, proved field by field.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from holo3 import data
from holo3.format import identity
from holo3.lib.geometry import TILE_CELLS
from holo3.plugins import color_region
from holo3.tests import _h3_fixture_geometry as geo

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"

PPC = 6
MARGIN_PX = 24
PAPER_LEVEL = 235.0


@dataclass(frozen=True)
class Channel:
    tiles_side: int = 4
    windows_side: int = 2
    absorption: float = 0.30
    noise_sd: float = 0.035
    gain_sd: float = 0.075
    offset_sd: float = 0.030
    seed: int = 20260830
    # Per-plane absorption multiplier. ``(1, 1, 1)`` is the uniform
    # channel; a small third entry is A4b's own case and sheet H's
    # measured shape — two healthy planes certifying beside a starved
    # third, whose marginal is what conditioning on the certified
    # siblings sharpens from 4-vs-4 to 1-vs-1.
    plane_scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    # Subtractive CMY -> RGB crosstalk, row = observed channel, column =
    # printing plane. THE IDENTITY MIX MAKES A4b INFORMATION-FREE, and
    # that is not a tuning detail but the arm's whole premise: with
    # independent channels, knowing a cell's certified C and M says
    # NOTHING about its Y, so restricting the marginal to the consistent
    # state subset cannot sharpen anything. Real ink subtracts across
    # channels (src/holo/qualification/color_synthetic's
    # ``subtractive_rgb``), so a certified sibling explains away part of
    # the observation and the remaining component becomes readable. That
    # is what "conditioning on authority fabricates nothing about the
    # remaining components" buys.
    mix: tuple[tuple[float, float, float], ...] = (
        (1.00, 0.35, 0.15),
        (0.30, 1.00, 0.25),
        (0.20, 0.30, 1.00))
    # Seeded per-TILE spread on the starved plane's strength. A page at
    # one uniform tone puts every tile at the same point on the LDPC
    # waterfall, so the sim fails all-or-nothing and no residue can exist
    # at the cliff — the shape the pooled-row worker measured. Real pages
    # are not uniform: sheet I's Y dead bands are a MEASURED per-region
    # x-registration sinusoid (0.83 dot peak, ~100 mm period). This
    # spreads tiles across the cliff so a residue exists to rescue.
    plane_jitter_sd: float = 0.0


def page_bits(gt_path: Path, row: object) -> np.ndarray:
    planes = np.unpackbits(np.load(gt_path), axis=-1)
    cells_y = row.tiles_yx[0] * TILE_CELLS
    cells_x = row.tiles_yx[1] * TILE_CELLS
    step = planes.shape[1] // cells_y
    off = step // 2
    cells = planes[:, off::step, off::step][:, :cells_y, :cells_x]
    return np.ascontiguousarray(np.moveaxis(cells, 0, -1))


def window_gains(channel: Channel) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(channel.seed)
    n_windows = channel.windows_side * channel.windows_side
    gains = 1.0 + rng.normal(0.0, channel.gain_sd, (n_windows, 3))
    offsets = rng.normal(0.0, channel.offset_sd, (n_windows, 3))
    return gains, offsets


def render(bits: np.ndarray, channel: Channel,
           gains: np.ndarray | None,
           offsets: np.ndarray | None) -> np.ndarray:
    cells = channel.tiles_side * TILE_CELLS
    field = bits[:cells, :cells].astype(np.float64)
    density = (channel.absorption
               * np.asarray(channel.plane_scale, np.float64)) * field
    if channel.plane_jitter_sd:
        rng = np.random.default_rng(channel.seed + 2)
        per_tile = 1.0 + rng.normal(
            0.0, channel.plane_jitter_sd,
            (channel.tiles_side, channel.tiles_side))
        density[..., 2] *= np.repeat(
            np.repeat(per_tile, TILE_CELLS, axis=0), TILE_CELLS, axis=1)
    clean = 1.0 - density @ np.asarray(channel.mix, np.float64).T
    side = cells * PPC
    image = np.full((side + 2 * MARGIN_PX, side + 2 * MARGIN_PX, 3),
                    PAPER_LEVEL / 255.0, np.float64)
    block = np.repeat(np.repeat(clean, PPC, axis=0), PPC, axis=1)
    if gains is not None:
        span = cells // channel.windows_side
        for index in range(channel.windows_side * channel.windows_side):
            wy, wx = divmod(index, channel.windows_side)
            rows = slice(wy * span * PPC, (wy + 1) * span * PPC)
            columns = slice(wx * span * PPC, (wx + 1) * span * PPC)
            block[rows, columns] = (
                block[rows, columns] * gains[index] + offsets[index])
    image[MARGIN_PX:MARGIN_PX + side, MARGIN_PX:MARGIN_PX + side] = block
    rng = np.random.default_rng(channel.seed + 1)
    image += rng.normal(0.0, channel.noise_sd, image.shape)
    return np.clip(image * 255.0, 0.0, 255.0).astype(np.uint8)


def plane_rasters(image: np.ndarray, outdir: Path
                  ) -> tuple[data.PlaneRaster, ...]:
    outdir.mkdir(parents=True, exist_ok=True)
    planes = []
    for index, name in enumerate("rgb"):
        path = outdir / f"{name}.npy"
        np.save(path, image[..., index])
        planes.append(data.PlaneRaster("cap", 0, name, path,
                                       image.shape[:2]))
    return tuple(planes)


#: The page's own cell-index -> pixel map, WITHOUT the half cell and
#: without any per-window origin: `render` lays cell (0, 0) as a
#: PPC-sized block starting at MARGIN_PX, and aiming at the centre of
#: that block is the composer's job, not this module's.
NATIVE_AFFINE: tuple[float, ...] = geo.page_native_affine(PPC, MARGIN_PX)


def region_windows(row: object,
                   channel: Channel) -> tuple[color_region.RegionWindow, ...]:
    """Disjoint windows over the page, composed BY PRODUCTION.

    Nothing here spells a pose.  Each window states its geometry as a
    `Placement` and `_h3_fixture_geometry.window_pose` runs
    `color_region.region_window` over it, so the half cell that this
    fixture once dropped (see the module docstring) is not a thing this
    file can get wrong any more.

    THE DECLARED WINDOW ID IS NOT THE POSE EXTENT, deliberately: these
    four windows all carry the whole page as their id, and
    `uplift_existence` uses `window_id[3]` as an ordering tie-break that
    is DEGENERATE by construction — every window ties, and the arms'
    residue order falls through to the ordinal behind it.  The pose is
    composed from each window's real extent either way.
    """
    cells = channel.tiles_side * TILE_CELLS
    span = cells // channel.windows_side
    height, width = row.cells_yx
    windows = []
    for index in range(channel.windows_side * channel.windows_side):
        wy, wx = divmod(index, channel.windows_side)
        start = (wy * span, wx * span)
        extent = (start[0], start[1], start[0] + span, start[1] + span)
        local = geo.grid_cells((0, 0), (span, span))
        placement = geo.window_placement(
            ("cap", 0, index, extent), NATIVE_AFFINE, local,
            patch_ordinal=index, page=0)
        windows.append(geo.window_pose(
            row, placement,
            declared_window_id=("cap", 0, index, (0, 0, height, width))))
    return tuple(windows)


def format_row_and_geometry() -> tuple[object, object]:
    row = identity.resolve_format_ref(COLOR_FORMAT_REF)
    return row, identity.build_site_geometry(row)


def audit_certificate(row: object, geometry: object,
                      certificates: dict, bits: np.ndarray,
                      page: int, ty: int, tx: int) -> int:
    projection = color_region.certified_projection(
        row, geometry, page, ty, tx, certificates)
    if projection is None:
        return 0
    field, known = projection
    printed = bits[ty * TILE_CELLS:(ty + 1) * TILE_CELLS,
                   tx * TILE_CELLS:(tx + 1) * TILE_CELLS]
    return int(np.count_nonzero((field != printed) & known))
