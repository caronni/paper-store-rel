"""Format-truth site geometry for the colour lane.

Pure helpers split out of color_region.py when the merge of the pooled-ctx
and plane-fields branches pushed it past the 1000-line seam signal: cargo
site/cell masks, suppressed tile codes, the emission mask and the
certified projection. No store access, no state.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from ..data import Certificate
from ..format import keystream, pilots, tile_codec
from ..format.identity import HW_DPI, Family, FormatRow, SiteGeometry

TILE: int = pilots.TILE_CELLS
TileKey = tuple[int, int, int, str]
Projection = tuple[np.ndarray, np.ndarray]

def cell_dots_of(row: FormatRow) -> int:
    return int(row.pitch_in * HW_DPI)


def cargo_site_mask(geometry: SiteGeometry) -> np.ndarray:
    mask = np.zeros(tile_codec.N_CELLS, dtype=bool)
    mask[np.asarray(geometry.payload_flat, np.int64)] = True
    return mask


def cargo_cell_mask(site_mask: np.ndarray,
                    page_cells_yx: np.ndarray) -> np.ndarray:
    cells = np.asarray(page_cells_yx, np.int64)
    local = (cells[:, 0] % TILE) * TILE + cells[:, 1] % TILE
    return site_mask[local]


def cargo_row_indices(geometry: SiteGeometry,
                      page_cells_yx: np.ndarray) -> np.ndarray:
    return np.flatnonzero(
        cargo_cell_mask(cargo_site_mask(geometry), page_cells_yx)
    ).astype(np.int32, copy=False)


def suppressed_tile_codes(
    row: FormatRow,
    certificates: Mapping[TileKey, Certificate],
    page: int,
) -> np.ndarray:
    streams_by_tile: dict[tuple[int, int], set[str]] = {}
    for cert_page, ty, tx, stream_id in certificates:
        if cert_page != page:
            continue
        streams_by_tile.setdefault((ty, tx), set()).add(stream_id)
    wanted = {fact.stream_id for fact in row.streams}
    codes = sorted(
        ty * row.tiles_yx[1] + tx
        for (ty, tx), names in streams_by_tile.items()
        if wanted <= names)
    return np.asarray(codes, np.int64)


def emission_mask(row: FormatRow, page_cells_yx: np.ndarray,
                  suppressed_codes: np.ndarray) -> np.ndarray:
    cells = np.asarray(page_cells_yx, np.int64)
    tile_codes = (
        (cells[:, 0] // TILE) * row.tiles_yx[1] + cells[:, 1] // TILE)
    return ~np.isin(tile_codes, suppressed_codes, assume_unique=False)


def certified_projection(
    row: FormatRow,
    geometry: SiteGeometry,
    page: int,
    ty: int,
    tx: int,
    certificates: Mapping[TileKey, Certificate],
) -> Projection | None:
    present = tuple(
        fact for fact in row.streams
        if (page, ty, tx, fact.stream_id) in certificates)
    if not present:
        return None
    counter = row.tile_counter(page, ty, tx)
    bits = np.zeros((TILE, TILE, 3), np.uint8)
    known = np.zeros((TILE, TILE, 3), np.bool_)
    word = geometry.word_cells_yx
    dust = geometry.extra_cells_yx
    word_states = pilots.color_word_states(row.seed, (counter,))[0]
    dust_states = pilots.dust_state_values(
        row.seed, (counter,), row.dust_base_cycle, row.n_dust)[0]
    bits[word[:, 0], word[:, 1]] = tile_codec.states_to_planes(
        word_states)
    bits[dust[:, 0], dust[:, 1]] = tile_codec.states_to_planes(
        dust_states)
    known[word[:, 0], word[:, 1]] = True
    known[dust[:, 0], dust[:, 1]] = True
    payload_flat = np.asarray(geometry.payload_flat, np.int64)
    order = keystream.color_cell_permutation(
        row.seed, counter, row.payload_cells)
    flat_bits = bits.reshape(tile_codec.N_CELLS, 3)
    flat_known = known.reshape(tile_codec.N_CELLS, 3)
    if row.family is Family.CMY7:
        certificate = certificates[(page, ty, tx, "main")]
        bank = row.streams[0].rung_children
        n_transmitted = tile_codec.bank_transmitted_bits(bank)
        sequential_states = tile_codec.cmy7_encode_payload(
            np.asarray(certificate.user_bits, np.uint8), bank,
            keystream.cmy7_interleave_permutation(
                row.seed, counter, n_transmitted),
            keystream.cmy7_dither_bits(row.seed, counter, n_transmitted))
        flat_bits[payload_flat] = tile_codec.states_to_planes(
            sequential_states[order])
        flat_known[payload_flat] = True
    else:
        for fact in present:
            certificate = certificates[(page, ty, tx, fact.stream_id)]
            n_transmitted = tile_codec.bank_transmitted_bits(
                fact.rung_children)
            sequential = tile_codec.encode_frame(
                np.asarray(certificate.user_bits, np.uint8),
                fact.rung_children)
            sequential ^= keystream.cmy8_dither_bits(
                row.seed, fact.stream_id, counter, n_transmitted)
            flat_bits[payload_flat, fact.plane] = sequential[order]
            flat_known[payload_flat, fact.plane] = True
    return bits, known
