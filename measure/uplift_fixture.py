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
own corrections.  See ``src/holo/receiver/tests/_h3_fixture_geometry.py`` for the
mechanism, which that module states once for every fixture.

THE HAND-BUILT POSE IS GONE 2026-08-31, same day, second commit.  The
correction above put the half cell back; it left the WRONG FORM still
representable, and the same defect had already been found in three
fixtures on one day.  ``region_windows`` now states its geometry as a
``Placement`` and lets ``color_region.region_window`` — production —
compose the pose, so this file no longer spells a half cell at all.
Byte-identical to the corrected hand-built form, proved field by field.

THE STARVED PLANE CAN NOW BE PRINTED OUT OF REGISTER 2026-09-12 (the
lead's ruling; ``docs/PAGE-FIELD-DESIGN.md`` §7.1's A4b debt).  A4b is
fitted BESIDE the registration arm, and this fixture used to inherit
that second arm from the always-on {1, y} residual the design retired —
so when that went, the arm's margin went to zero with it.
``Channel.starved_shift_px`` lays the starved plane's ink a whole number
of pixels along x (2 px = one printed dot = a third of a cell at c3) and
``plane_fields`` publishes the same displacement as the page's standing
field, which the instrument hands ``build_region_inputs`` the way
``plugins/uplift.py`` hands production's.  A channel that prints in
register leaves both off and is byte-identical to this file's earlier
renders, proved plane by plane, so the A3 record above is untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from holo.receiver import data
from holo.receiver.format import identity
from holo.receiver.lib.geometry import TILE_CELLS
from holo.receiver.plugins import color_region
from holo.receiver.tests import _h3_fixture_geometry as geo

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"

PPC = 6
MARGIN_PX = 24
PAPER_LEVEL = 235.0

#: The plane A4b starves, displaces and then conditions: Y, the third,
#: which is sheet H's measured shape — C and M certify and become the
#: authority, Y is the one left over.
STARVED_PLANE = 2


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
    # The starved plane's PRINT REGISTRATION ERROR, in whole capture
    # pixels along +x, which is the physical effect A4b is fitted beside.
    # `build_region_inputs` only has a corrected arm to fit where the
    # page carries a field, and a field only stands where a plane is
    # really out of register: with no displacement anywhere the fixture
    # poses A4b its question against a single-armed head, which is the
    # state that read margin exactly zero (PAGE-FIELD-DESIGN §7.1).
    # PPC px is one cell and one cell is `cell_dots` printed dots, so
    # 2 px is a third of a cell = 1 dot at c3 — inside the 0.3-0.4 cell
    # band, and a WHOLE pixel, so the render displaces the plane's ink
    # without interpolating it.
    starved_shift_px: int = 0
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


def shifted_x(plane_px: np.ndarray, shift_px: int) -> np.ndarray:
    """One plane's ink moved along +x, paper shifted in behind it.

    `shift_px` is at least 1, which is the whole domain `render` calls
    it over: at 0 the slice below is empty and at a negative shift this
    would move the ink the other way while `plane_fields` still said
    +x.  A probe that wants the other direction takes both signs the
    way `_h3_sims.shift_plane_x` does, and says so in the field too.
    """
    out = np.zeros_like(plane_px)
    out[:, shift_px:] = plane_px[:, :-shift_px]
    return out


def starved_shift_dots(row: object, channel: Channel) -> float:
    """The starved plane's displacement in PRINTED DOTS along page x.

    The render moves ink by whole PIXELS and the field speaks dots, so
    this is the one conversion between them: PPC pixels are one cell and
    one cell is `cell_dots` dots.  Exact at every rung the fixture can
    carry, which is what lets the injected field below match the render
    to the bit.
    """
    return (channel.starved_shift_px
            * color_region.cell_dots_of(row) / PPC)


def injected_field(plane: int, tiles_yx: tuple[int, int],
                   delta_x_dots: float) -> data.PlaneField:
    """One plane's field: a constant x displacement over the whole page.

    Measured everywhere, so support is 1 and uncertainty 0 — this is a
    displacement the fixture WROTE, not one anybody estimated.
    """
    delta_dots_xy = np.zeros((tiles_yx[0], tiles_yx[1], 2), np.float64)
    delta_dots_xy[..., 0] = delta_x_dots
    return data.PlaneField(
        page=0, plane=plane, delta_dots_xy=delta_dots_xy,
        support=np.ones(tiles_yx, np.float64),
        uncertainty_dots=np.zeros(tiles_yx, np.float64),
        n_observations=tiles_yx[0] * tiles_yx[1], n_captures=1, ordinal=1)


def plane_fields(row: object, channel: Channel
                 ) -> tuple[data.PlaneField, ...] | None:
    """The page's standing per-plane fields, as production hands them.

    THE INJECTED FIELD, NOT A SOLVED ONE, and deliberately: the
    displacement is a constant this fixture wrote, so the exact field is
    known and the arm under test stays A4b rather than the estimator,
    which has its own bars on its own stimuli (PAGE-FIELD-DESIGN §6,
    B1-B3).

    ALL THREE PLANES OR NONE, because those are the only two shapes the
    `fields` row can leave in the store: `plugins/fields.solve_job`
    solves every plane and publishes the three together under one
    revision, and `store.page_plane_fields` reads Nones only before a
    page's first solve — which is what `None` here means, and where
    every earlier run of this fixture measured.  C and M print in
    register, so their injected fields say exactly that: zero delta,
    which `page_map.plane_delta_dots` evaluates to a zero offset and
    `color_region_anchor.features_at` then reads at the pose itself,
    point for point.  Measured inert as well as argued — the ablation
    reads off 50140 / a4b 50283 / margin +143 either way (2026-09-12).
    """
    if not channel.starved_shift_px:
        return None
    shift_dots = starved_shift_dots(row, channel)
    return tuple(
        injected_field(plane, row.tiles_yx,
                       shift_dots if plane == STARVED_PLANE else 0.0)
        for plane in range(3))


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
        density[..., STARVED_PLANE] *= np.repeat(
            np.repeat(per_tile, TILE_CELLS, axis=0), TILE_CELLS, axis=1)
    side = cells * PPC
    image = np.full((side + 2 * MARGIN_PX, side + 2 * MARGIN_PX, 3),
                    PAPER_LEVEL / 255.0, np.float64)
    # The planes are laid down in PIXEL space and mixed there, so one of
    # them can be printed out of register before the mix — which is what
    # a printer's plane-to-plane error does and what a page field
    # corrects. Ink pushed past the rendered area's right edge is lost;
    # that edge is where this fixture stopped rendering a 10x10-tile
    # page, not a paper edge, and the strip lost is `starved_shift_px`
    # wide -- 2 px, a THIRD of a cell at the shipped shift (measured:
    # one cell column is touched, nothing a cell wide is lost), the
    # same strip for both arms.
    dots = np.repeat(np.repeat(density, PPC, axis=0), PPC, axis=1)
    if channel.starved_shift_px:
        dots[..., STARVED_PLANE] = shifted_x(dots[..., STARVED_PLANE],
                                             channel.starved_shift_px)
    block = 1.0 - dots @ np.asarray(channel.mix, np.float64).T
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
