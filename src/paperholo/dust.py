"""Layer 2b — training dust for color pages (PILOTS-DESIGN §16.3, D3).

A second known-value cell population overlaid on layout_version-4 (cmy8)
pages, carrying NO message bits. Consumed post-lock, site-gated, it supplies
(i) the labeled training set for the 8-class detector (blind-EM is measured
dead: LOOP-C 0.999 vs furniture-QDA 1.456 b/cell), (ii) per-plane
registration from pure-plane dust centroids (D5), (iii) PAVA calibration
labels per level, (iv) a per-plane consumable canary.

FORMAT-AXIS DERIVATION (frozen once gen_e017 pins its golden):

- POSITIONS are TILE-PERIODIC: one set of in-tile (y, x) cell offsets,
  identical in every pilot tile of every page. Drawn from
  rng(seed, b"dust-sites-v4") by an explicit integers-only partial
  Fisher-Yates over the tile's NON-PILOT cells in raster order (pilot
  sites are excluded by construction; the draw consumes exactly
  sites_per_tile integers), then sorted to raster order — the canonical
  dust site index. Periodicity is load-bearing: the LDPC shorten-mask
  derivation stays modulo-based and fountain symbol sizes stay
  deterministic (COLOR-DESIGN D3 rejects Poisson dust for exactly this).

- VALUES are APERIODIC (R3: positions may repeat, values must not): the
  per-tile state vector is drawn from
  rng(seed, b"dust-states-v4" + page_le32 + tile_le32), tile = the
  ABSOLUTE pilot-tile index ty*tiles_x + tx on that page. States are
  3-bit CMY combos, state = C + 2*M + 4*Y (bit l = level l ink,
  level order C, M, Y — matches compose's cell_values level order).
  A deterministic fix-up pass guarantees >= pure_quota sites of each
  pure-plane state (C=1, M=2, Y=4) per tile: reassignment victims are
  taken from a Fisher-Yates permutation drawn from the SAME generator
  right after the states, skipping sites whose current state is a pure
  state at-or-below its own quota. Encoder and receiver re-derive the
  identical assignment from (seed, page, tile) alone.

All integer draws pass an explicit dtype (the 012.3 incident rule).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import pilots
from .modulation import rng

DUST_SITES_LABEL: bytes = b"dust-sites-v4"
DUST_STATES_LABEL: bytes = b"dust-states-v4"
# pure-plane states under state = C + 2*M + 4*Y (level order C, M, Y)
PURE_STATES: tuple[int, int, int] = (1, 2, 4)
N_STATES = 8


@dataclass(frozen=True)
class DustLayout:
    """Format-axis dust parameters (density is frozen by probe P3)."""

    sites_per_tile: int
    pure_quota: int          # min sites per pure plane state per tile
    version: int = 4

    def __post_init__(self) -> None:
        if self.version != 4:
            raise ValueError(f"dust exists from layout_version 4 on, "
                             f"got {self.version}")
        if self.sites_per_tile < 1:
            raise ValueError("sites_per_tile must be >= 1")
        if self.pure_quota < 0:
            raise ValueError("pure_quota must be >= 0")
        if 3 * self.pure_quota > self.sites_per_tile:
            raise ValueError(
                f"pure_quota {self.pure_quota} x 3 pure states exceeds "
                f"sites_per_tile {self.sites_per_tile}")


def _fisher_yates(g: np.random.Generator, n: int) -> np.ndarray:
    """Explicit integers-only permutation (frozen derivation — the ldpc.py
    precedent: Generator.permutation's stream is not numpy-guaranteed)."""
    pi = np.arange(n, dtype=np.int64)
    for i in range(n - 1, 0, -1):
        j = int(g.integers(0, i + 1, dtype=np.int64))
        pi[i], pi[j] = pi[j], pi[i]
    return pi


def dust_positions_tile(pilot_layout: "pilots.PilotLayout",
                        dust_layout: DustLayout, seed: bytes) -> np.ndarray:
    """(M, 2) int64 in-tile (y_cell, x_cell) dust positions, raster-sorted.

    SAME for every tile (tile-periodic). Excludes pilot sites by
    construction: the draw runs over the tile's non-pilot cells in raster
    order via a partial Fisher-Yates from rng(seed, b"dust-sites-v4")
    (exactly M integer draws, explicit dtype)."""
    p = pilot_layout.period_cells
    m = dust_layout.sites_per_tile
    pos = pilots.site_positions_tile(pilot_layout, seed)
    pilot_flat = pos[:, 0] * p + pos[:, 1]
    candidates = np.setdiff1d(np.arange(p * p, dtype=np.int64), pilot_flat)
    n = candidates.size
    if m > n:
        raise ValueError(f"sites_per_tile {m} exceeds the {n} non-pilot "
                         f"cells of a {p}x{p} pilot tile")
    g = rng(seed, DUST_SITES_LABEL)
    # partial Fisher-Yates: first m entries are a uniform m-subset in
    # uniform order; we only keep the SET (raster-sorted below)
    cand = candidates.copy()
    for i in range(m):
        j = int(g.integers(i, n, dtype=np.int64))
        cand[i], cand[j] = cand[j], cand[i]
    chosen = np.sort(cand[:m])                    # canonical raster order
    return np.stack([chosen // p, chosen % p], axis=1).astype(np.int64)


def dust_site_mask(shape_cells: tuple[int, int],
                   pilot_layout: "pilots.PilotLayout",
                   dust_layout: DustLayout, seed: bytes) -> np.ndarray:
    """Boolean dust-site mask over a page cell grid (exact multiples of
    period_cells — same scope rule as pilots.pilot_site_mask)."""
    h_cells, w_cells = shape_cells
    p = pilot_layout.period_cells
    if h_cells % p or w_cells % p:
        raise ValueError(
            f"shape_cells {shape_cells} must be exact multiples of "
            f"period_cells {p}")
    pos = dust_positions_tile(pilot_layout, dust_layout, seed)
    tile = np.zeros((p, p), dtype=bool)
    tile[pos[:, 0], pos[:, 1]] = True
    return np.tile(tile, (h_cells // p, w_cells // p))


def dust_states_tile(dust_layout: DustLayout, seed: bytes, page: int,
                     tile_index: int) -> np.ndarray:
    """(M,) uint8 states in [0, 8) for ONE tile, aligned with
    dust_positions_tile's raster-sorted site order.

    Draw: g = rng(seed, b"dust-states-v4" + page_le32 + tile_le32);
    states = g.integers(0, 8, M, dtype=uint8); then the deterministic
    pure-quota fix-up (module docstring). tile_index = ty*tiles_x + tx
    (absolute pilot-tile index on the page)."""
    if page < 0 or tile_index < 0:
        raise ValueError("page and tile_index must be >= 0")
    m = dust_layout.sites_per_tile
    q = dust_layout.pure_quota
    g = rng(seed, DUST_STATES_LABEL + page.to_bytes(4, "little")
            + tile_index.to_bytes(4, "little"))
    states = g.integers(0, N_STATES, size=m, dtype=np.uint8)
    if q == 0:
        return states
    perm = _fisher_yates(g, m)          # drawn AFTER the states (frozen order)
    counts = np.bincount(states, minlength=N_STATES).astype(np.int64)
    for pure in PURE_STATES:
        for i in perm:
            if counts[pure] >= q:
                break
            s = int(states[i])
            if s == pure:
                continue
            # never rob a pure state at-or-below its own quota
            if s in PURE_STATES and counts[s] <= q:
                continue
            counts[s] -= 1
            states[i] = pure
            counts[pure] += 1
        if counts[pure] < q:            # unreachable given __post_init__
            raise AssertionError("pure-quota fix-up failed")
    return states


def dust_states_page(shape_cells: tuple[int, int],
                     pilot_layout: "pilots.PilotLayout",
                     dust_layout: DustLayout, seed: bytes, page: int
                     ) -> np.ndarray:
    """(3, Hc, Wc) uint8 per-plane ink bits (level order C, M, Y), defined
    only at dust cells (zero elsewhere — combine with dust_site_mask).

    Positions are tile-periodic; VALUES are keyed by (seed, page, absolute
    tile index) and never repeat (R3)."""
    h_cells, w_cells = shape_cells
    p = pilot_layout.period_cells
    if h_cells % p or w_cells % p:
        raise ValueError(
            f"shape_cells {shape_cells} must be exact multiples of "
            f"period_cells {p}")
    pos = dust_positions_tile(pilot_layout, dust_layout, seed)
    tiles_y, tiles_x = h_cells // p, w_cells // p
    out = np.zeros((3, h_cells, w_cells), dtype=np.uint8)
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            states = dust_states_tile(dust_layout, seed, page,
                                      ty * tiles_x + tx)
            ys = ty * p + pos[:, 0]
            xs = tx * p + pos[:, 1]
            for level in range(3):
                out[level, ys, xs] = (states >> level) & 1
    return out
