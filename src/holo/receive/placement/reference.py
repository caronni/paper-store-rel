"""Cold-legal v1 reference-field provider.

Every label comes from the production format implementation: exact-100
family sites, real BCH counter words, the row's periodic word scramble, and
absolute-address filler values when a future density rung enables them.  The
provider is complete from those predictable format values alone; it has no
certified-payload or feedback input.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ...core import keystream
from ...format import pilots
from ...format.descriptor import FormatSpec
from ...format.profiles import Family


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
    return np.frombuffer(
        contiguous.tobytes(), dtype=np.dtype(dtype)
    ).reshape(contiguous.shape)


@dataclass(frozen=True, slots=True)
class ReferencePage:
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
    spec: FormatSpec

    def page(self, page: int) -> ReferencePage: ...


class V1ReferenceField:
    """Exact v1 pilot field with full-key, no-eviction memoization.

    The cache key contains the complete printed interpretation.  The finite
    format counter domain bounds the dictionary; no memory-policy limit can
    thrash repeated/local scoring or alter the searched page set.
    """

    def __init__(self, spec: FormatSpec) -> None:
        self.spec = spec
        self._pages: dict[
            tuple[bytes, bytes, int, tuple[int, int], int, int], ReferencePage
        ] = {}
        self._sites: np.ndarray | None = None

    def _key(self, page: int) -> tuple[bytes, bytes, int, tuple[int, int], int, int]:
        return (
            self.spec.seed,
            self.spec.family_seed,
            int(self.spec.plane),
            tuple(self.spec.layout.cells_yx),
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
                f"page {page} outside addressable range 0..{self.spec.max_pages - 1}"
            )
        key = self._key(page)
        cached = self._pages.get(key)
        if cached is None:
            cached = self._generate(page)
            self._pages[key] = cached
        return cached

    def _generate(self, page: int) -> ReferencePage:
        tiles_y, tiles_x = self.spec.layout.tiles_yx
        height, width = self.spec.layout.cells_yx
        color = self.spec.codec_family in (Family.CMY7, Family.CMY8)
        if color:
            word_cells, filler_cells = pilots.color_site_cells_yx(
                self.spec.family_seed)
        else:
            word_cells, filler_cells = pilots.site_cells_yx(
                self.spec.family_seed, self.spec.n_filler)
        tile_indices = np.arange(tiles_y * tiles_x, dtype=np.int64)
        tile_y = tile_indices // tiles_x
        tile_x = tile_indices % tiles_x
        counters = page * (tiles_y * tiles_x) + tile_indices
        words = pilots.word_values(
            self.spec.seed,
            counters,
            pilots.PLANE_K if color else self.spec.plane,
        )

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
            if color:
                # Placement operates on equal-channel luma.  Under the
                # provisional ideal subtractive renderer its pinned 50/50
                # blind split is exactly states with at least two ink
                # components versus W/single-ink states.
                states = pilots.dust_state_values(
                    self.spec.seed, counters, self.spec.codec)
                ink_count = np.asarray(
                    (0, 1, 1, 2, 1, 2, 2, 3), np.uint8)
                values[filler_y, filler_x] = (
                    ink_count[states] >= 2
                ).astype(np.uint8)
            else:
                # keystream.bits returns one flat vector over its raveled
                # broadcast addresses; restore the (tiles, F) index shape.
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
        tiles_y, tiles_x = self.spec.layout.tiles_yx
        height, width = self.spec.layout.cells_yx
        if self.spec.codec_family in (Family.CMY7, Family.CMY8):
            word_cells, filler_cells = pilots.color_site_cells_yx(
                self.spec.family_seed)
        else:
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
    points = np.asarray(points_yx, np.int64)
    matrix, translation = rotation_affine(rot_k, shape)
    return np.rint(points @ matrix.T + translation).astype(np.int64)
