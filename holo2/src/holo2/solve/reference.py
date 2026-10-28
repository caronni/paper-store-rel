"""Cold-legal v1 reference field: what the pilot lattice PRINTS, per page.

Ported from ``src/holo/receive/placement/reference.py`` at 594a465,
refactored per H4-PLAN R4 — the code is holo2's own, the ARITHMETIC is
v1's exactly.  W0 sub-wave A2; nothing imports it yet.

Every label comes from the production format implementation: exact-100
family sites, real BCH counter words, the row's periodic word scramble,
and absolute-address filler values when a future density rung enables
them.  The provider is complete from those predictable format values
alone; it has no certified-payload or feedback input, which is what makes
it legal for a cold correlation over an unaddressed page.

NOT PORTED — the CMY7/CMY8 codec branch (v1 reference.py:112-120,
:145-156, :173-180).  v1 asks ``spec.codec in (CMY7_P120_V0,
CMY8_P120_V0)`` and then reads ``pilots.color_site_cells_yx`` and
``pilots.dust_state_values``, mapping the eight ink states to the
provisional 50/50 luma split ``ink_count[state] >= 2``.  Both of those
pilot functions are on holo2's declared NOT_CARRIED colour surface and
arrive with the colour leaves (H7); ``format.TileFormat`` is K by
construction (``format_v1``'s "the color rows are NOT here"), so the
branch has no reachable predicate to test.  This module is therefore
K-ONLY: ``colour`` is not a runtime state here, it is an absent feature,
and the H7 wave restores the branch together with the surface it needs.

TileFormat adaptation (v1's ``FormatSpec`` nests page geometry under
``spec.layout``): ``spec.layout.tiles_yx`` -> ``spec.tiles_yx`` and
``spec.layout.cells_yx`` -> ``spec.cells_yx``.  ``seed``, ``family_seed``,
``plane``, ``n_filler`` and ``max_pages`` are already on TileFormat's
surface under v1's own names, so every other read is unchanged — and the
cache key still contains the complete printed interpretation.

R4 freedoms exercised (code only): none beyond the elision above and the
adaptation — the module is small, and its immutability contract
(``_immutable``'s base-chain ownership rule) is the reason it exists in
this shape.

Arithmetic deliberately NOT touched: the site/word/filler index algebra
(``tile_y[:, None] * TILE_CELLS + cells[None, :, 0]``), the flat counter
``page * tiles_per_page + tile_index``, ``np.rint(...).astype(np.int64)``
in :func:`rotate_points` (NOT ``int(round(...))``, NOT
``int(np.ceil(...))`` — three different functions), the exact ``rot90``
affines with their ``width - 1``/``height - 1`` translations, and
:func:`overlap_slices`' half-open clipping.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..format import TileFormat, keystream, pilots

_PageKey = tuple[bytes, bytes, int, tuple[int, int], int, int]


def _immutable(value: np.ndarray, dtype: np.dtype | type,
               *, reuse: bool = False) -> np.ndarray:
    """Return bytes-backed immutable storage, optionally reusing such input.

    NumPy's write flag alone is not an ownership guarantee: a read-only view
    may still have a mutable base.  Reuse is therefore limited to arrays whose
    base chain terminates in immutable ``bytes`` storage created by this
    module.  Every other input is defensively copied.
    """
    array = np.asarray(value, dtype=dtype)
    base: object | None = array
    while isinstance(base, np.ndarray) and base.base is not None:
        base = base.base
    bytes_backed = isinstance(base, bytes)
    if (reuse and bytes_backed and array.flags.c_contiguous
            and not array.flags.writeable):
        return array
    contiguous = np.ascontiguousarray(array, dtype=dtype)
    out: np.ndarray = np.frombuffer(
        contiguous.tobytes(), dtype=np.dtype(dtype)
    ).reshape(contiguous.shape)
    return out


@dataclass(frozen=True, slots=True)
class ReferencePage:
    """One page's printed pilot values and the site mask they live on."""

    page: int
    values: np.ndarray
    sites: np.ndarray

    def __post_init__(self) -> None:
        values = _immutable(self.values, np.uint8)
        # A provider may safely share its bytes-backed, page-invariant site
        # mask across every page.  Values remain page-owned.
        sites = _immutable(self.sites, bool, reuse=True)
        if values.shape != sites.shape or values.ndim != 2:
            raise ValueError("reference values/sites must be equal 2-D shapes")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "sites", sites)


class ReferenceFieldProvider(Protocol):
    """What a search needs of a reference field: its format, and pages."""

    spec: TileFormat

    def page(self, page: int) -> ReferencePage: ...


class V1ReferenceField:
    """Exact v1 pilot field with full-key, no-eviction memoization.

    The cache key contains the complete printed interpretation.  The finite
    format counter domain bounds the dictionary; no memory-policy limit can
    thrash repeated/local scoring or alter the searched page set.
    """

    def __init__(self, spec: TileFormat) -> None:
        self.spec = spec
        self._pages: dict[_PageKey, ReferencePage] = {}
        self._sites: np.ndarray | None = None

    def _key(self, page: int) -> _PageKey:
        return (
            self.spec.seed,
            self.spec.family_seed,
            int(self.spec.plane),
            self.spec.cells_yx,
            int(self.spec.n_filler),
            int(page),
        )

    def page(self, page: int) -> ReferencePage:
        if (
            isinstance(page, (bool, np.bool_))
            or not isinstance(page, (int, np.integer))
        ):
            raise TypeError("page must be an integer")
        page = int(page)
        if not 0 <= page < self.spec.max_pages:
            raise ValueError(
                f"page {page} outside addressable range "
                f"0..{self.spec.max_pages - 1}"
            )
        key = self._key(page)
        cached = self._pages.get(key)
        if cached is None:
            cached = self._generate(page)
            self._pages[key] = cached
        return cached

    def _generate(self, page: int) -> ReferencePage:
        tiles_y, tiles_x = self.spec.tiles_yx
        height, width = self.spec.cells_yx
        word_cells, filler_cells = pilots.site_cells_yx(
            self.spec.family_seed, self.spec.n_filler)
        tile_indices = np.arange(tiles_y * tiles_x, dtype=np.int64)
        tile_y = tile_indices // tiles_x
        tile_x = tile_indices % tiles_x
        counters = page * (tiles_y * tiles_x) + tile_indices
        words = pilots.word_values(self.spec.seed, counters, self.spec.plane)

        values = np.zeros((height, width), np.uint8)
        word_y = tile_y[:, None] * pilots.TILE_CELLS + word_cells[None, :, 0]
        word_x = tile_x[:, None] * pilots.TILE_CELLS + word_cells[None, :, 1]
        values[word_y, word_x] = words

        if filler_cells.size:
            filler_y = (
                tile_y[:, None] * pilots.TILE_CELLS
                + filler_cells[None, :, 0]
            )
            filler_x = (
                tile_x[:, None] * pilots.TILE_CELLS
                + filler_cells[None, :, 1]
            )
            # keystream.bits returns one flat vector over its raveled
            # broadcast addresses; restore the (tiles, F) index shape.
            # (v1's latent defect here — surfaced by the W0 differential
            # — was fixed on main in 6a1a982 and ported the same day.)
            values[filler_y, filler_x] = keystream.bits(
                self.spec.seed,
                keystream.DOMAIN_FILLER_VALUES,
                self.spec.plane,
                page,
                filler_y,
                filler_x,
            ).reshape(filler_y.shape)
        return ReferencePage(page, values, self._site_mask())

    def _site_mask(self) -> np.ndarray:
        """Return the immutable page-invariant v1 site geometry."""
        cached = self._sites
        if cached is not None:
            return cached
        tiles_y, tiles_x = self.spec.tiles_yx
        height, width = self.spec.cells_yx
        word_cells, filler_cells = pilots.site_cells_yx(
            self.spec.family_seed, self.spec.n_filler)
        tile_indices = np.arange(tiles_y * tiles_x, dtype=np.int64)
        tile_y = tile_indices // tiles_x
        tile_x = tile_indices % tiles_x
        sites = np.zeros((height, width), bool)
        word_y = tile_y[:, None] * pilots.TILE_CELLS + word_cells[None, :, 0]
        word_x = tile_x[:, None] * pilots.TILE_CELLS + word_cells[None, :, 1]
        sites[word_y, word_x] = True
        if filler_cells.size:
            filler_y = (
                tile_y[:, None] * pilots.TILE_CELLS
                + filler_cells[None, :, 0]
            )
            filler_x = (
                tile_x[:, None] * pilots.TILE_CELLS
                + filler_cells[None, :, 1]
            )
            sites[filler_y, filler_x] = True
        cached = _immutable(sites, bool)
        self._sites = cached
        return cached


def overlap_slices(
    origin_yx: tuple[int, int],
    fragment_shape: tuple[int, int],
    page_shape: tuple[int, int],
) -> tuple[slice, slice, slice, slice] | None:
    """Clip a possibly overhanging rotated fragment against a page."""
    origin_y, origin_x = origin_yx
    height, width = page_shape
    frag_height, frag_width = fragment_shape
    page_y0, page_x0 = max(0, origin_y), max(0, origin_x)
    page_y1 = min(height, origin_y + frag_height)
    page_x1 = min(width, origin_x + frag_width)
    if page_y0 >= page_y1 or page_x0 >= page_x1:
        return None
    return (
        slice(page_y0, page_y1),
        slice(page_x0, page_x1),
        slice(page_y0 - origin_y, page_y1 - origin_y),
        slice(page_x0 - origin_x, page_x1 - origin_x),
    )


def rotation_affine(
    rot_k: int, shape: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    """``np.rot90`` mapping ``rotated = S @ original + t``."""
    height, width = shape
    rot_k = int(rot_k) % 4
    if rot_k == 0:
        return np.eye(2), np.zeros(2)
    if rot_k == 1:
        return (
            np.array([[0.0, -1.0], [1.0, 0.0]]),
            np.array([width - 1.0, 0.0]),
        )
    if rot_k == 2:
        return -np.eye(2), np.array([height - 1.0, width - 1.0])
    return (
        np.array([[0.0, 1.0], [-1.0, 0.0]]),
        np.array([0.0, height - 1.0]),
    )


def rotate_points(
    points_yx: np.ndarray, shape: tuple[int, int], rot_k: int
) -> np.ndarray:
    """Map integer page points through ``np.rot90``'s own affine."""
    points = np.asarray(points_yx, np.int64)
    matrix, translation = rotation_affine(rot_k, shape)
    rotated: np.ndarray = np.rint(
        points @ matrix.T + translation).astype(np.int64)
    return rotated


__all__ = [
    "ReferenceFieldProvider", "ReferencePage", "V1ReferenceField",
    "overlap_slices", "rotate_points", "rotation_affine",
]
