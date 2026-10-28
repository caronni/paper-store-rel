"""PLANE-FIELDS W4: WHICH certified cells a probe correlates, and where.

Split out of :mod:`holo.receive.color_field` at the seam the line cap
named (memory ``feedback-line-cap-is-a-seam-signal``): that module owns
the FIELD -- evidence, posterior, adoption, the registration seam -- and
this one owns the PROBE.  A probe is three decisions and nothing else:
which window offers it, which certified cells make its template, and
which of those cells carry weight.

DENSITY IS A GEOMETRY, NEVER A BUDGET (user ruling 2026-08-22: "we don't
do ceilings here -- if the ceiling reduces yield it is wrong, and if
having no ceiling does not increase yield we should not be doing the
thing at all").  Every mode probes every eligible certified tile; they
differ in the SHAPE of the template each tile contributes.

The measured record for the square densities is INDEPENDENT-PLANES §2.9
(E5); the TILE_FRAGMENT mode's is §2.9b (E5b).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

import numpy as np
from scipy import ndimage

from ..format.layout import TILE_CELLS
from .color_projection import CertifiedColorProjection
from .placement.model import PlacedPatch


class ProbeMode(Enum):
    """How a certified-complete tile is sampled by the W4 pass.

    ``WHOLE_TILE``
        One probe per fully-certified tile, template = that tile's ENTIRE
        64x64 re-encoded certified cells, per plane.  The V0 instrument's
        template (``measure/plane_fields/_probe.py``).
    ``BLOCK_PER_BIN``
        One ``probe_block_cells`` square per FIELD BIN -- the finest
        position the field can represent.  The 2026-08-22 P1 build.
    ``EVERY_BLOCK``
        Every eligible ``probe_block_cells`` square.  Overlapping blocks
        sharpen bins the pass already covers rather than reaching new
        ones; it is the density LADDER's top rung, not a production
        recommendation.
    ``TILE_FRAGMENT``
        One probe per (certified tile, covering window) PAIR, template =
        every cell of that tile which lies inside that window's audited
        cells, weighted 1 inside and 0 out.  The 2026-08-23 build, and
        the answer to the user's correction of E5: "when you have a
        certified tile, each window that covers this tile (fully or
        partially) can profit from the pose/field measurement -- it's
        like feeding back a pose."  **THE SHIPPED DENSITY** since the
        2026-08-23 ruling (§2.9c): one measurement serves the per-plane
        field and the plane-common pose residual, and the pose half is
        the one a 5x5 block cannot carry.

    E5 MEASURED THE FIRST THREE (INDEPENDENT-PLANES §2.9; archived W6
    sheet-I state, capture 1, lane ``l02-8ppc-2400dpi``,
    ``measure/plane_fields/probe_density.py``).  The whole tile is the
    more PRECISE probe -- its per-probe agreement with the supervised
    regmap-gt measurement is three times tighter than a 5x5 block's --
    and it reached only 516 of the 1,628 certified tiles, because a
    SQUARE template must lie wholly inside ONE window and the windows are
    200x200 cells and not tile-aligned.  E5b (§2.9b) removes exactly that
    constraint: a fragment does not need the whole tile inside one
    window, it takes whatever part of the tile the window covers.
    """

    WHOLE_TILE = "whole-tile"
    BLOCK_PER_BIN = "block-per-bin"
    EVERY_BLOCK = "every-block"
    TILE_FRAGMENT = "tile-fragment"


@dataclass(frozen=True, slots=True)
class ProbeWindow:
    """One window offered to the W4 probe pass.

    Deliberately NOT a ``_Rows``: a certified-complete window is
    label-only under the pool law, so its ``_Rows`` carries the sparse
    furniture sites alone.  The probe needs the window's FULL audited
    cell alignment (``_window_rows`` output) to find the cells that lie
    inside a certified tile, so the caller hands those arrays over
    directly.

    EVERY window is offered, label-only AND mixed (INDEPENDENT-PLANES
    §4.G, ruling 2026-08-23).  A mixed window's fully-certified tiles are
    exactly as certified as a label-only window's, and the window that
    covers them is exactly as posed; refusing them was an artefact of
    where the probe pass was first plumbed in, not a property of the
    evidence.
    """

    patch: PlacedPatch
    page: int
    local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray

    def row_lookup(self) -> np.ndarray:
        """``(height, width)`` row index per local cell, ``-1`` absent."""
        local = np.asarray(self.local_cells_yx, np.int64)
        lookup = np.full(
            (int(local[:, 0].max()) + 1, int(local[:, 1].max()) + 1),
            -1, np.int64)
        lookup[local[:, 0], local[:, 1]] = np.arange(local.shape[0])
        return lookup


@dataclass(frozen=True, slots=True)
class _ProbeSite:
    """One eligible probe location (canonical order).

    ``local_y0``/``local_x0`` are the template's TOP-LEFT local cell and
    ``height_cells``/``width_cells`` its extent; ``centre_page_yx`` is the
    template's exact page-cell CENTRE, the position its evidence is
    scattered at.  Storing the corner rather than a centre CELL is what
    lets an EVEN edge -- the 64-cell whole tile -- share this path with
    the odd ones.

    ``dense`` says whether every cell of that rectangle is present, on
    one certified tile and fully known: true for the SQUARE densities, by
    construction of :func:`_square_sites`.  A TILE_FRAGMENT rectangle is
    the bounding box of the covered part of a tile, which may clip a
    neighbour's cells at a corner, so its template carries a WEIGHT mask.
    """

    page: int
    page_y: int
    page_x: int
    window_ordinal: int
    local_y0: int
    local_x0: int
    centre_page_yx: tuple[float, float]
    height_cells: int
    width_cells: int
    dense: bool = True

    @property
    def address(self) -> tuple[int, int, int]:
        """The ``(page, tile_y, tile_x)`` this site's template is GT for."""
        return (self.page, self.page_y // TILE_CELLS,
                self.page_x // TILE_CELLS)

    @property
    def centre_local_yx(self) -> tuple[float, float]:
        return (self.local_y0 + 0.5 * (self.height_cells - 1),
                self.local_x0 + 0.5 * (self.width_cells - 1))


def meets_extent_floor(mask: np.ndarray, min_edge_cells: int) -> bool:
    """The TILE_FRAGMENT eligibility floor, on any cell mask.

    At least ``min_edge_cells`` of span on EACH axis and at least
    ``min_edge_cells ** 2`` cells in total -- see
    :func:`_tile_fragment_sites` for why both halves are identifiability
    and not thrift.
    """
    ys, xs = np.nonzero(mask)
    if not ys.size or ys.size < min_edge_cells * min_edge_cells:
        return False
    return bool(int(ys.max()) - int(ys.min()) + 1 >= min_edge_cells
                and int(xs.max()) - int(xs.min()) + 1 >= min_edge_cells)


def probe_sites_for_window(
    window: ProbeWindow,
    window_ordinal: int,
    mode: ProbeMode,
    certified: Callable[[tuple[int, int, int]], bool],
    tiles_x: int,
    *,
    block_cells: int,
    bins_per_tile: int,
) -> list[_ProbeSite]:
    """Every site one declared density places inside one window."""
    if mode is ProbeMode.TILE_FRAGMENT:
        return _tile_fragment_sites(
            window, window_ordinal, certified, tiles_x,
            min_edge_cells=block_cells)
    edge = TILE_CELLS if mode is ProbeMode.WHOLE_TILE else int(block_cells)
    return _square_sites(
        window, window_ordinal, edge, certified, tiles_x, bins_per_tile,
        one_per_bin=mode is not ProbeMode.EVERY_BLOCK)


def _square_sites(
    window: ProbeWindow,
    window_ordinal: int,
    block_cells: int,
    certified: Callable[[tuple[int, int, int]], bool],
    tiles_x: int,
    bins_per_tile: int,
    *,
    one_per_bin: bool = True,
) -> list[_ProbeSite]:
    """The square densities' probe blocks inside one window.

    A block is eligible when its whole ``block_cells`` square of LOCAL
    cells is present in the window's audited rows AND lands on a single
    tile whose every stream is certified -- so the projection is exact GT
    over the entire template.  That eligibility rule is also what bounds
    a square density's REACH: the wider the template, the more of the
    window it needs, and a template as wide as a tile needs the whole
    tile inside one window (E5, :class:`ProbeMode`).

    What bounds the pass is GEOMETRY, in two dials the caller sets from
    :class:`ProbeMode`: the block EDGE, and whether overlapping candidates
    collapse to one survivor per FIELD BIN (``one_per_bin``, the finest
    POSITION the field can represent) or all of them are kept.  At the
    64-cell edge exactly one candidate exists per tile -- a 64-cell square
    wholly inside one 64-cell tile IS that tile -- so the whole-tile mode
    needs no separate selection rule.

    Why a bin and not a cell (``BLOCK_PER_BIN``).  The retired
    256-per-region ceiling did its damage SPATIALLY: measured on the W6
    sheet-I state, 256 of the 1,628 fully-certified tiles were probed and
    the other five sixths of the decoded sheet stayed UNCOVERED -- exactly
    the evidence the field is short of.  One-per-bin closes that.  The
    blocks it does not visit are the ones that OVERLAP a block it did:
    they sharpen a bin the pass already covers instead of reaching a bin
    it does not.  ``EVERY_BLOCK`` keeps them; E5 measured what that buys
    (nothing: 4,550x the probes, within 0.008 dot).
    """
    local = np.asarray(window.local_cells_yx, np.int64)
    page = np.asarray(window.page_cells_yx, np.int64)
    if not local.size:
        return []
    row_of = window.row_lookup()
    if min(row_of.shape) < block_cells:
        return []
    tile_code = np.full(row_of.shape, -1, np.int64)
    tile_code[local[:, 0], local[:, 1]] = (
        (page[:, 0] // TILE_CELLS) * tiles_x + (page[:, 1] // TILE_CELLS))
    present = row_of >= 0
    whole = ndimage.minimum_filter(
        present, size=block_cells, mode="constant", cval=False)
    low = ndimage.minimum_filter(
        np.where(present, tile_code, np.int64(1 << 40)),
        size=block_cells, mode="constant", cval=np.int64(1 << 40))
    high = ndimage.maximum_filter(
        np.where(present, tile_code, np.int64(-1)),
        size=block_cells, mode="constant", cval=np.int64(-1))
    eligible = whole & (low == high)
    ys, xs = np.nonzero(eligible)
    if not ys.size:
        return []
    indices = row_of[ys, xs]
    page_yx = page[indices]
    tiles_x_index = page_yx[:, 1] // TILE_CELLS
    tiles_y_index = page_yx[:, 0] // TILE_CELLS
    codes = tiles_y_index * tiles_x + tiles_x_index
    # One certification lookup per COVERED TILE, not per candidate cell.
    allowed = np.asarray(sorted(
        int(code) for code in np.unique(codes)
        if certified((
            window.page,
            int(code) // tiles_x, int(code) % tiles_x))), np.int64)
    if not allowed.size:
        return []
    rows = np.flatnonzero(np.isin(codes, allowed))
    if not rows.size:
        return []
    if one_per_bin:
        # One survivor per field bin: nearest the bin centre, ties by page
        # position, so the choice is a function of the geometry alone.
        selected = page_yx[rows]
        bin_y = (selected[:, 0] * bins_per_tile) // TILE_CELLS
        bin_x = (selected[:, 1] * bins_per_tile) // TILE_CELLS
        cells_per_bin = float(TILE_CELLS) / bins_per_tile
        distance = (
            (selected[:, 0] + 0.5 - (bin_y + 0.5) * cells_per_bin) ** 2
            + (selected[:, 1] + 0.5 - (bin_x + 0.5) * cells_per_bin) ** 2)
        order = np.lexsort(
            (selected[:, 1], selected[:, 0], distance, bin_x, bin_y))
        keys = (bin_y[order] << np.int64(32)) | bin_x[order]
        opens = np.ones(keys.size, np.bool_)
        opens[1:] = keys[1:] != keys[:-1]
        rows = rows[order][opens]
    # The block's exact page-cell CENTRE from its two opposite corners:
    # a rot90 maps the local square to a page square, so the corner
    # midpoint is the centre whatever the orientation, at every parity of
    # the edge (an odd block reproduces "centre cell + 0.5" exactly).
    offset = block_cells // 2
    corner_low = page[row_of[ys[rows] - offset, xs[rows] - offset]]
    corner_high = page[
        row_of[ys[rows] - offset + block_cells - 1,
               xs[rows] - offset + block_cells - 1]]
    centres = 0.5 * (corner_low + corner_high).astype(np.float64) + 0.5
    return [
        _ProbeSite(
            window.page, int(page_yx[row, 0]), int(page_yx[row, 1]),
            window_ordinal, int(ys[row]) - offset, int(xs[row]) - offset,
            (float(centres[ordinal, 0]), float(centres[ordinal, 1])),
            block_cells, block_cells)
        for ordinal, row in enumerate(rows)
    ]


def _tile_fragment_sites(
    window: ProbeWindow,
    window_ordinal: int,
    certified: Callable[[tuple[int, int, int]], bool],
    tiles_x: int,
    *,
    min_edge_cells: int,
) -> list[_ProbeSite]:
    """One site per (certified tile, this window) -- however it is clipped.

    The square densities ask "does a template of edge E fit wholly inside
    this window and this tile?" and a tile that straddles a window
    boundary answers no at every E wide enough to be precise.  This asks
    the other question: "what part of this tile does this window cover?",
    and correlates exactly that.  Straddling tiles are therefore measured
    ONCE PER WINDOW that covers them, which is the point -- each of those
    windows carries its own pose, and each of them can profit from the
    measurement.

    ELIGIBILITY (the only floor, and it is a CORRECTNESS floor, not a
    budget).  A fragment must span at least ``min_edge_cells`` cells on
    EACH axis and hold at least ``min_edge_cells ** 2`` present cells --
    one 5x5 block probe's worth of structure per axis, and in total.
    Both halves are identifiability, not thrift:

    * the template is piecewise constant per CELL (``np.kron`` of the
      cell bits), so a fragment one cell wide has literally zero
      horizontal gradient inside it and its ``dx`` would be pure noise --
      the NCC would return whatever the search window's edge effects
      say.  The per-axis span is what makes each axis identifiable at
      all;
    * the cell count is :attr:`ProbeMode.BLOCK_PER_BIN`'s whole template
      -- the density the receiver shipped on until 2026-08-23, and the
      smallest sample the field has measured evidence for.  E5 measured
      25 cells to be reliable on this channel (0 of 6,117 measurements
      below the 0.30 NCC floor); accepting a fragment SMALLER than that
      would put evidence into the field that is weaker than any the
      field has ever been fed, which is a correctness statement about
      the sample, not a cost one.

    Nothing else is refused.  There is no cap on the number of fragments,
    no cap per window, no cap per tile.
    """
    local = np.asarray(window.local_cells_yx, np.int64)
    page = np.asarray(window.page_cells_yx, np.int64)
    if not local.size:
        return []
    row_of = window.row_lookup()
    present = row_of >= 0
    codes = ((page[:, 0] // TILE_CELLS) * tiles_x
             + (page[:, 1] // TILE_CELLS))
    tile_code = np.full(row_of.shape, -1, np.int64)
    tile_code[local[:, 0], local[:, 1]] = codes
    sites: list[_ProbeSite] = []
    for code in np.unique(codes):
        address = (window.page, int(code) // tiles_x, int(code) % tiles_x)
        if not certified(address):
            continue
        mask = present & (tile_code == code)
        if not meets_extent_floor(mask, min_edge_cells):
            continue
        ys, xs = np.nonzero(mask)
        local_y0, local_y1 = int(ys.min()), int(ys.max())
        local_x0, local_x1 = int(xs.min()), int(xs.max())
        height = local_y1 - local_y0 + 1
        width = local_x1 - local_x0 + 1
        page_yx = page[row_of[ys, xs]]
        # A rot90 maps the LOCAL bounding box onto the PAGE bounding box
        # (min/max commute with an axis permutation and a sign flip), so
        # these four extrema ARE the corners of the local rectangle and
        # their midpoint is its centre -- the same identity the square
        # path uses, without needing the corner cells to be present.
        page_y0, page_y1 = int(page_yx[:, 0].min()), int(page_yx[:, 0].max())
        page_x0, page_x1 = int(page_yx[:, 1].min()), int(page_yx[:, 1].max())
        sites.append(_ProbeSite(
            window.page, page_y0, page_x0, window_ordinal,
            local_y0, local_x0,
            (0.5 * (page_y0 + page_y1) + 0.5,
             0.5 * (page_x0 + page_x1) + 0.5),
            height, width,
            dense=bool(mask[local_y0:local_y1 + 1,
                            local_x0:local_x1 + 1].all()),
        ))
    return sites


def probe_template(
    window: ProbeWindow,
    site: _ProbeSite,
    projection: CertifiedColorProjection,
    *,
    min_edge_cells: int = 0,
) -> tuple[np.ndarray, np.ndarray] | None:
    """``(h, w, 3)`` exact printed presence and its ``(h, w)`` weights.

    Read through the window's own local->page row alignment, so the
    template sits on the same lattice the rectified sampler walks.  A
    DENSE site (every square density) keeps the historical contract
    exactly: all cells present, all cells known, or no template at all.
    A clipped fragment instead carries weight 0 on the cells that are
    absent, belong to another tile, or are not known -- which the
    weighted NCC excludes from mean, norm and numerator alike -- and
    re-checks :func:`meets_extent_floor` on what survives, because a
    projection with unknown cells can thin a geometrically fine fragment
    below the identifiability floor.
    """
    page = np.asarray(window.page_cells_yx, np.int64)
    block = window.row_lookup()[
        site.local_y0:site.local_y0 + site.height_cells,
        site.local_x0:site.local_x0 + site.width_cells]
    shape = (site.height_cells, site.width_cells)
    if block.shape != shape:
        return None
    present = block >= 0
    if site.dense and not bool(present.all()):
        return None
    cells = page[np.where(present, block, 0).ravel()]
    tile_y, tile_x = site.address[1], site.address[2]
    inside = (
        present.ravel()
        & (cells[:, 0] // TILE_CELLS == tile_y)
        & (cells[:, 1] // TILE_CELLS == tile_x))
    rows = cells[:, 0] % TILE_CELLS
    columns = cells[:, 1] % TILE_CELLS
    known = projection.known_mask[rows, columns].all(axis=1) & inside
    if site.dense:
        if not bool(known.all()):
            return None
        weights = np.ones(shape, np.float64)
    else:
        surviving = known.reshape(shape)
        if not meets_extent_floor(surviving, min_edge_cells):
            return None
        weights = surviving.astype(np.float64)
    bits = np.asarray(
        projection.component_bits[rows, columns], np.float64
    ).reshape(*shape, 3)
    return bits, weights


def template_is_flat(bits: np.ndarray, inside: np.ndarray) -> bool:
    """No ink contrast inside the weighted cells -> nothing to correlate."""
    values = bits[inside]
    return bool(values.size == 0 or values.min() == values.max())


__all__ = [
    "ProbeMode",
    "ProbeWindow",
    "TILE_CELLS",
    "meets_extent_floor",
    "probe_sites_for_window",
    "probe_template",
    "template_is_flat",
]
