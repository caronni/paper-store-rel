"""Page composition: symbols + pilots + metadata -> cell field -> dots.

The v1 assembly (HOLO-DESIGN §4, §6): every 64x64-cell tile carries its
address word at the 100 family sites, its LDPC codeword on the remaining
cells through the per-tile affine slot permutation, and one metadata bit
as the first LDPC user bit. Payload-carrying cells are scrambled with the
row's absolute-address keystream; site cells carry their own scrambled
values. ESI = tile counter (all tiles bear symbols).
"""
from __future__ import annotations

import numpy as np

from ..core import keystream
from ..core.ldpc import tile as ldpc_tile
from ..format import metadata, pilots
from ..format.descriptor import FormatSpec
from ..format.profiles import Family


def compose_page_cells(spec: FormatSpec, page: int, symbols: np.ndarray,
                       k_total: int, version: int = 0) -> np.ndarray:
    """One page's cell field, shape layout.cells_yx, uint8 0/1 (ink=1).

    symbols: (tiles_per_page, S) uint8 — the fountain symbols whose ESIs
    are this page's tile counters, in tile-raster order.
    """
    if spec.codec_family is not Family.K:
        raise ValueError("compose_page_cells is the established K leaf")
    # Geometry from the identity, never from a page layout: the cell
    # field exists before any sheet is chosen, and a v2 row's dot grid is
    # an emission fact (paper x engine dpi), FORMAT-SPACE §7.
    h_cells, w_cells = spec.cells_yx
    tys, txs = h_cells // 64, w_cells // 64
    n_tiles = tys * txs
    if symbols.shape != (n_tiles, spec.symbol_bits):
        raise ValueError(f"symbols shape {symbols.shape} != "
                         f"{(n_tiles, spec.symbol_bits)}")
    meta = metadata.encode_metadata(version, k_total)
    site_flat = pilots.site_cell_indices(spec.family_seed, spec.n_filler)
    word_cells = pilots.word_site_cells_yx(spec.family_seed)
    _, filler_cells = pilots.site_cells_yx(spec.family_seed, spec.n_filler)
    t_slots = spec.n_transmitted_slots

    counters = np.array([spec.tile_counter(page, ty, tx)
                         for ty in range(tys) for tx in range(txs)],
                        dtype=np.int64)
    meta_bits = metadata.tile_bits(meta, counters)
    a_all, b_all = keystream.slot_perm_params(spec.seed, counters, t_slots)
    words = pilots.word_values(spec.seed, counters, spec.plane)

    field = np.zeros((h_cells, w_cells), dtype=np.uint8)
    site_mask_tile = np.zeros(4096, dtype=bool)
    site_mask_tile[site_flat] = True

    for idx, c in enumerate(counters):
        ty, tx = idx // txs, idx % txs
        user = np.empty(spec.tile_user_bits, dtype=np.uint8)
        user[0] = meta_bits[idx]
        user[1:] = symbols[idx]
        cells = ldpc_tile.encode_tile(user, spec.rate_id, site_flat,
                                      int(a_all[idx]), int(b_all[idx]))
        tile = cells.reshape(64, 64).copy()
        tile[word_cells[:, 0], word_cells[:, 1]] = words[idx]
        if filler_cells.size:
            fy, fx = filler_cells[:, 0], filler_cells[:, 1]
            abs_y = ty * 64 + fy
            abs_x = tx * 64 + fx
            tile[fy, fx] = keystream.bits(
                spec.seed, keystream.DOMAIN_FILLER_VALUES, spec.plane,
                page, abs_y, abs_x)
        field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = tile

    # payload scramble on non-site cells only (absolute cell coordinates)
    scramble = keystream.payload_bits(spec.seed, spec.plane, page,
                                      (h_cells, w_cells))
    page_site_mask = np.tile(site_mask_tile.reshape(64, 64), (tys, txs))
    field ^= scramble & ~page_site_mask
    return field


def cells_to_dots(field_cells: np.ndarray, cell_dots: int) -> np.ndarray:
    """Solid-cell expansion: each cell becomes a cell_dots^2 dot block."""
    return np.kron(field_cells,
                   np.ones((cell_dots, cell_dots), dtype=np.uint8))
