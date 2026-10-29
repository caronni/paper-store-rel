"""Shared fixture for the plane-isolation existence proof.

Builds a synthetic printed colour page from a REAL emitted ground truth
(the colour sim's ``page000_gt.npy``), so every tile carries real codec
content and can actually certify, and renders it through a channel whose
disease is the MEASURED one: **one plane's ink is displaced in x over
part of the page**.

That shape is not invented.  e033 measured the AltaLink's yellow-plane
x-registration as a sinusoid, 0.83 dot peak and ~100 mm period, and
`measure/yask` §4.2 saw the same object directly in the yellow signal and
showed it is what separates a live column from a dead one: the two
populations peak at DIFFERENT sampling offsets, 0.00 against +0.50 dots,
so one global correction cannot serve both.  The colour lane's own
per-plane residual is a function of page-y (`anchor.fit_plane_residual`,
intercept plus slope), so a displacement that varies with page-X is
exactly what it cannot represent — which is why the band here is a
COLUMN of the page and not the whole of it.

Everything is seeded and deterministic.  Nothing here is production; the
row under test runs unchanged and this module only builds its input.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

from holo.receiver import data
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import color_region
from holo.receiver.tests import _h3_fixture_geometry as geo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uplift_fixture as base  # noqa: E402

PPC: int = base.PPC
MARGIN_PX: int = base.MARGIN_PX
PAPER_LEVEL: float = base.PAPER_LEVEL

CAPTURE_ID: str = "cap"
LEVEL_INDEX: int = 0

format_row_and_geometry = base.format_row_and_geometry
page_bits = base.page_bits
plane_rasters = base.plane_rasters
audit_certificate = base.audit_certificate


@dataclass(frozen=True)
class PlaneChannel:
    """A colour channel with one plane displaced over a column band."""

    tiles_side: int = 4
    windows_side: int = 2
    #: the plane whose ink is displaced.  2 is yellow — the measured
    #: case — but the mechanism and the row are plane-general, so the
    #: probe sweeps this.
    plane: int = 2
    absorption: float = 0.30
    noise_sd: float = 0.075
    #: which window column carries the displacement.  Leaving the other
    #: column clean is what makes the disease unrepresentable by a
    #: page-global residual, and it is what supplies the certified
    #: neighbours this residue row needs by construction.
    band_window_column: int = 1
    #: displacement in RASTER PIXELS, interpolated, so it need not land
    #: on a whole pixel or on one of the row's own grid points.  At PPC 6
    #: and the c3 sim's 3 dots per cell one pixel is half a printed dot,
    #: so the default is 1.75 dots.
    shift_px: float = 3.5
    #: seeded per-tile spread on the displaced plane's ink strength.  A
    #: band at one uniform tone puts every tile at the same point on the
    #: LDPC waterfall and the sim fails all-or-nothing; real pages are
    #: not uniform, and a residue only exists if tiles straddle the
    #: cliff.
    plane_jitter_sd: float = 0.0
    seed: int = 20260831
    #: subtractive CMY -> RGB crosstalk, row = observed channel, column =
    #: printing plane.  THE OFF-DIAGONALS ARE THE WHOLE PROBLEM this row
    #: solves: with an identity mix the target plane's channel would be a
    #: clean readout and cancelling the siblings would buy nothing.  On
    #: paper magenta darkens blue by 60% of what yellow does.
    mix: tuple[tuple[float, float, float], ...] = base.Channel.mix


def _band_columns_px(channel: PlaneChannel) -> slice:
    cells = channel.tiles_side * TILE_CELLS
    span_px = (cells // channel.windows_side) * PPC
    return slice(channel.band_window_column * span_px,
                 (channel.band_window_column + 1) * span_px)


def render(bits: np.ndarray, channel: PlaneChannel) -> np.ndarray:
    """The page, with one plane's ink displaced over the band."""
    cells = channel.tiles_side * TILE_CELLS
    field = bits[:cells, :cells].astype(np.float64)
    density = channel.absorption * field
    if channel.plane_jitter_sd:
        rng = np.random.default_rng(channel.seed + 2)
        per_tile = 1.0 + rng.normal(
            0.0, channel.plane_jitter_sd,
            (channel.tiles_side, channel.tiles_side))
        density[..., channel.plane] *= np.repeat(
            np.repeat(per_tile, TILE_CELLS, axis=0), TILE_CELLS, axis=1)
    block = np.repeat(np.repeat(density, PPC, axis=0), PPC, axis=1)
    displaced = ndimage.shift(block[..., channel.plane],
                              (0.0, float(channel.shift_px)), order=1,
                              mode="nearest")
    columns = _band_columns_px(channel)
    block[:, columns, channel.plane] = displaced[:, columns]
    clean = 1.0 - block @ np.asarray(channel.mix, np.float64).T
    side = cells * PPC
    image = np.full((side + 2 * MARGIN_PX, side + 2 * MARGIN_PX, 3),
                    PAPER_LEVEL / 255.0, np.float64)
    image[MARGIN_PX:MARGIN_PX + side, MARGIN_PX:MARGIN_PX + side] = clean
    rng = np.random.default_rng(channel.seed + 1)
    image += rng.normal(0.0, channel.noise_sd, image.shape)
    return np.clip(image * 255.0, 0.0, 255.0).astype(np.uint8)


def band_tiles(channel: PlaneChannel) -> tuple[tuple[int, int], ...]:
    """The tile addresses whose target plane is displaced."""
    per_window = channel.tiles_side // channel.windows_side
    first = channel.band_window_column * per_window
    return tuple((ty, tx) for ty in range(channel.tiles_side)
                 for tx in range(first, first + per_window))


#: The page's own cell-index -> pixel map, for a `Placement`.  NO HALF
#: CELL and no per-window origin: both are
#: `color_region.region_window`'s to add (it composes
#: `M @ (page_cell + 0.5) + t`), and an affine that already carries them
#: double-counts both.
NATIVE_AFFINE: tuple[float, ...] = geo.page_native_affine(PPC, MARGIN_PX)


def placements(channel: PlaneChannel) -> tuple[data.Placement, ...]:
    """A real `Placement` per window — THE fixture's statement of its
    own geometry, and the only one it makes.

    This is also the production seam: `calibrate.window_evidence` stamps
    its evidence from a placement and nothing else, and
    `color_region.region_window` rebuilds each window's pose from the
    placement alone.  Each window carries its OWN extent in its window
    id — the tie-break `tiles.color_candidates` orders cuts by — rather
    than the whole page.
    """
    cells = channel.tiles_side * TILE_CELLS
    span = cells // channel.windows_side
    places = []
    for index in range(channel.windows_side * channel.windows_side):
        wy, wx = divmod(index, channel.windows_side)
        extent = (wy * span, wx * span, (wy + 1) * span, (wx + 1) * span)
        places.append(geo.window_placement(
            (CAPTURE_ID, LEVEL_INDEX, index, extent), NATIVE_AFFINE,
            geo.grid_cells((0, 0), (span, span)),
            patch_ordinal=index, page=0))
    return tuple(places)


def region_windows(row: object, channel: PlaneChannel,
                   ) -> tuple[color_region.RegionWindow, ...]:
    """Disjoint windows over the page, composed BY PRODUCTION.

    Nothing here spells a pose: the placements above state the geometry
    and `color_region.region_window` composes it, half cell included.
    That half cell is 1.5 printed dots at this geometry — the same size
    as the displacement under test, and a fixture that dropped it would
    MEASURE it as one.  This fixture did, until 2026-08-31.
    """
    return tuple(geo.window_pose(row, placement)
                 for placement in placements(channel))
