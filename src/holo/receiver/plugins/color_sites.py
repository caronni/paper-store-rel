"""Format-truth site geometry for the colour lane.

Pure helpers split out of color_region.py when the merge of the pooled-ctx
and plane-fields branches pushed it past the 1000-line seam signal: cargo
site/cell masks, suppressed tile codes, the emission mask and the
certified projection. No store access, no state.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from ..data import Certificate
from ..format import keystream, pilots, tile_codec
from ..format.identity import (HW_DPI, Family, FormatRow, SiteGeometry,
                               StreamFact)

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


#: A tile is suppressed only when EVERY required stream is certified.
#: A cmy8 tile with two of three planes certified keeps emitting, which
#: is what lets the third plane certify later.
#: 11-colour-planes-ctx.md:169-171.
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


#: One certified stream's transmitted bits in the codec's SEQUENTIAL
#: order: the frame re-encoded from the certificate's user bits, XOR the
#: stream's dither -- a toner stream's presence bits, a label stream's
#: label bits.  What the demap reads; the cell permutation is the
#: caller's.
def certified_stream_bits(row: FormatRow, fact: StreamFact, counter: int,
                          certificate: Certificate) -> np.ndarray:
    sequential = tile_codec.encode_frame(
        np.asarray(certificate.user_bits, np.uint8), fact.rung_children)
    sequential ^= keystream.cmy8_dither_bits(
        row.seed, fact.dither_aux, counter,
        tile_codec.bank_transmitted_bits(fact.rung_children))
    return sequential


#: The one consistency rule, cmy8's and cmy's: a cell's ALLOWED states
#: are the alphabet's states whose bit on every certified stream is the
#: certified bit there, and a plane is KNOWN where every allowed state
#: agrees on it, at the agreed value.  `certified` pairs a stream's
#: column in `tile_codec.stream_bits(row)` with its sequential bits.  A
#: cmy8 toner stream knows its own plane and nothing else; a cmy label
#: stream knows only true zeros (hi 0: C and M, hi 1: Y; lo 0: C and Y,
#: lo 1: M); both label streams know the state.
def _consistent_planes(row: FormatRow,
                       certified: Sequence[tuple[int, np.ndarray]],
                       ) -> tuple[np.ndarray, np.ndarray]:
    table = tile_codec.stream_bits(row)
    n_cells = int(np.asarray(certified[0][1]).size)
    allowed = np.ones((n_cells, table.shape[0]), np.bool_)
    for column, bits in certified:
        allowed &= table[None, :, column] == np.asarray(bits)[:, None]
    count = allowed.sum(axis=1, keepdims=True)
    ones = allowed.astype(np.int64) @ tile_codec.plane_bits(row).astype(
        np.int64)
    known = ((ones == 0) | (ones == count)) & (count > 0)
    return (known & (ones > 0)).astype(np.uint8), known


#: A cmy7 certificate owns the whole physical state; a cmy8 or cmy
#: certificate labels ONLY what its own stream implies through the
#: consistency rule -- certifying C is never authority for M or Y, and
#: a cmy label stream never knows a plane as 1 on its own.  Per-plane
#: graceful degradation starts here.
#: 10-colour-heads.md:65-66.
def certified_projection(
    row: FormatRow,
    geometry: SiteGeometry,
    page: int,
    ty: int,
    tx: int,
    certificates: Mapping[TileKey, Certificate],
) -> Projection | None:
    present = tuple(
        (column, fact) for column, fact in enumerate(row.streams)
        if (page, ty, tx, fact.stream_id) in certificates)
    if not present:
        return None
    counter = row.tile_counter(page, ty, tx)
    bits = np.zeros((TILE, TILE, 3), np.uint8)
    known = np.zeros((TILE, TILE, 3), np.bool_)
    word = geometry.word_cells_yx
    dust = geometry.extra_cells_yx
    word_states = pilots.color_word_states(row.seed, (counter,), row)[0]
    dust_states = pilots.dust_state_values(row.seed, (counter,), row)[0]
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
    elif row.family in (Family.CMY8, Family.CMY):
        payload_bits, payload_known = _consistent_planes(row, tuple(
            (column, certified_stream_bits(
                row, fact, counter,
                certificates[(page, ty, tx, fact.stream_id)]))
            for column, fact in present))
        flat_bits[payload_flat] = payload_bits[order]
        flat_known[payload_flat] = payload_known[order]
    else:
        raise KeyError(row.family)
    return bits, known
