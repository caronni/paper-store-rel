"""Provisional CMY7/CMY8 tile and page composition.

This is the color counterpart of :mod:`holo.gen.compose`, kept separate so
the established K numerical path remains unchanged.  It owns only the join
between row-declared fountain symbols and a canonical physical state field:

* one addressed metadata bit is prepended to every logical stream — the
  SAME bit on -v0 rows, one DISTINCT per-stream equation on pooled -v1
  rows (equation_index = counter*n_streams + stream_idx, §13.35);
* the row-selected color tile codec produces sequential payload states;
* a row/address-keyed permutation places those states on the 3,976 payload
  cells; and
* the exact W/CM word and known-state dust overwrite their p120 furniture.

Rendering is a later, lossless projection from state IDs to C/M/Y presence
planes.  Scanner colors and detector calibration do not belong here.
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from ..core import channel, color_tile, keystream
from ..format import metadata, pilots
from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from .compose import cells_to_dots


def _symbol(
    values: np.ndarray,
    width: int,
    stream_id: str,
) -> np.ndarray:
    raw = np.asarray(values)
    if raw.shape != (width,):
        raise ValueError(
            f"{stream_id} symbol shape {raw.shape} != ({width},)")
    if raw.dtype.kind not in "buif" or not np.isfinite(raw).all() \
            or not np.isin(raw, (0, 1)).all():
        raise ValueError(f"{stream_id} symbol must contain finite 0/1 values")
    return raw.astype(np.uint8, copy=False)


def _symbols_for_tile(
    spec: FormatSpec,
    symbols_by_stream: Mapping[str, np.ndarray],
) -> tuple[np.ndarray, ...]:
    if not isinstance(symbols_by_stream, Mapping):
        raise TypeError("symbols_by_stream must be a mapping")
    expected = spec.stream_ids
    supplied = tuple(symbols_by_stream)
    if set(supplied) != set(expected) or len(supplied) != len(expected):
        raise ValueError(
            f"{spec.codec_id} needs streams {expected}, got {supplied}")
    return tuple(
        _symbol(
            symbols_by_stream[stream.stream_id],
            stream.symbol_bits,
            stream.stream_id,
        )
        for stream in spec.stream_profiles
    )


def _payload_states(
    spec: FormatSpec,
    counter: int,
    user_bits: tuple[np.ndarray, ...],
) -> np.ndarray:
    if spec.codec_family is Family.CMY7:
        bank = spec.stream_profiles[0].fec
        return color_tile.cmy7_encode_payload(
            user_bits[0],
            bank,
            keystream.cmy7_interleave_permutation(
                spec.seed, counter, bank.transmitted_bits),
            keystream.cmy7_dither_bits(
                spec.seed, counter, bank.transmitted_bits),
        )
    if spec.codec_family is Family.CMY8:
        banks = {
            stream.stream_id: stream.fec
            for stream in spec.stream_profiles
        }
        users = dict(zip(spec.stream_ids, user_bits, strict=True))
        dithers = {
            stream.stream_id: keystream.cmy8_dither_bits(
                spec.seed,
                stream.stream_id,
                counter,
                stream.fec.transmitted_bits,
            )
            for stream in spec.stream_profiles
        }
        return color_tile.cmy8_encode_payload(
            users, banks, dithers)
    raise ValueError(f"{spec.codec_id}: not a provisional color codec")


def _color_geometry(
    spec: FormatSpec,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    payload_cells = pilots.color_payload_cell_indices(spec.family_seed)
    word_cells, dust_cells = pilots.color_site_cells_yx(spec.family_seed)
    word_flat = word_cells[:, 0] * 64 + word_cells[:, 1]
    dust_flat = dust_cells[:, 0] * 64 + dust_cells[:, 1]
    return payload_cells, word_flat, dust_flat


def _metadata_bits_for_tile(
    spec: FormatSpec,
    word: np.ndarray,
    counter: int,
) -> tuple[int, ...]:
    """One metadata bit per stream codeword of one tile.

    -v0 rows replicate the counter's equation across every stream
    (bit-identical to the historical single-bit path); pooled -v1 rows
    carry one DISTINCT equation per stream at
    ``equation_index(counter, s, n)`` (design §2.4).
    """
    n = len(spec.stream_profiles)
    if spec.pooled_fountain:
        bound = metadata.max_equation_index(n)
        return tuple(
            metadata.tile_bit(
                word,
                metadata.equation_index(counter, stream, n),
                max_index=bound,
            )
            for stream in range(n)
        )
    return (metadata.tile_bit(word, counter),) * n


def _compose_validated_tile(
    spec: FormatSpec,
    counter: int,
    symbols: tuple[np.ndarray, ...],
    metadata_bits: tuple[int, ...],
    geometry: tuple[np.ndarray, np.ndarray, np.ndarray],
    word_states: np.ndarray,
    dust_states: np.ndarray,
) -> np.ndarray:
    users = tuple(
        np.concatenate((
            np.asarray([bit], dtype=np.uint8),
            symbol,
        ))
        for bit, symbol in zip(metadata_bits, symbols, strict=True)
    )
    sequential = _payload_states(spec, counter, users)
    if sequential.shape != (spec.payload_cells,):
        raise AssertionError(
            f"{spec.codec_id}: codec emitted {sequential.shape}, expected "
            f"({spec.payload_cells},)")

    payload_cells, word_flat, dust_flat = geometry
    placed = sequential[
        keystream.color_cell_permutation(
            spec.seed, counter, spec.payload_cells)
    ]
    tile = np.zeros(64 * 64, dtype=np.uint8)
    tile[payload_cells] = placed
    tile[word_flat] = word_states
    tile[dust_flat] = dust_states
    return tile.reshape(64, 64)


def compose_color_tile(
    spec: FormatSpec,
    counter: int,
    symbols_by_stream: Mapping[str, np.ndarray],
    k_total: int,
    version: int = 0,
) -> np.ndarray:
    """Compose one addressed 64x64 canonical color-state tile."""
    if spec.codec_family not in (Family.CMY7, Family.CMY8):
        raise ValueError(f"{spec.codec_id}: not a provisional color codec")
    symbols = _symbols_for_tile(spec, symbols_by_stream)
    word = metadata.encode_metadata(version, k_total)
    word_states = pilots.color_word_states(spec.seed, [counter])[0]
    dust_states = pilots.dust_state_values(
        spec.seed, [counter], spec.codec)[0]
    return _compose_validated_tile(
        spec,
        counter,
        symbols,
        _metadata_bits_for_tile(spec, word, counter),
        _color_geometry(spec),
        word_states,
        dust_states,
    )


def compose_color_page_cells(
    spec: FormatSpec,
    page: int,
    symbols_by_stream: Mapping[str, np.ndarray],
    k_total: int,
    version: int = 0,
) -> np.ndarray:
    """Compose one page of canonical color states.

    Each mapping value has shape ``(tiles_per_page, stream_symbol_bits)``.
    The physical tile counter and page raster order are the same as K.
    """
    if not isinstance(symbols_by_stream, Mapping):
        raise TypeError("symbols_by_stream must be a mapping")
    expected = spec.stream_ids
    supplied = tuple(symbols_by_stream)
    if set(supplied) != set(expected) or len(supplied) != len(expected):
        raise ValueError(
            f"{spec.codec_id} needs streams {expected}, got {supplied}")
    matrices: dict[str, np.ndarray] = {}
    for stream in spec.stream_profiles:
        raw = np.asarray(symbols_by_stream[stream.stream_id])
        shape = (spec.tiles_per_page, stream.symbol_bits)
        if raw.shape != shape:
            raise ValueError(
                f"{stream.stream_id} symbols shape {raw.shape} != {shape}")
        if raw.dtype.kind not in "buif" or not np.isfinite(raw).all() \
                or not np.isin(raw, (0, 1)).all():
            raise ValueError(
                f"{stream.stream_id} symbols must contain finite 0/1 values")
        matrices[stream.stream_id] = raw.astype(np.uint8, copy=False)

    # Geometry from the identity, never from a page layout (see
    # compose.compose_page_cells): dots are an emission fact.
    h_cells, w_cells = spec.cells_yx
    tys, txs = h_cells // 64, w_cells // 64
    field = np.empty((h_cells, w_cells), dtype=np.uint8)
    counters = np.asarray([
        spec.tile_counter(page, ty, tx)
        for ty in range(tys)
        for tx in range(txs)
    ], dtype=np.int64)
    word = metadata.encode_metadata(version, k_total)
    n_streams = len(expected)
    if spec.pooled_fountain:
        # one DISTINCT equation per stream (design §2.4), shape (T, n)
        metadata_bits = metadata.tile_bits(
            word,
            metadata.equation_indices(counters, n_streams),
            max_index=metadata.max_equation_index(n_streams),
        )
    else:
        # -v0: the counter's equation replicated across the streams —
        # bit-identical to the historical single-bit path
        metadata_bits = np.repeat(
            metadata.tile_bits(word, counters)[:, None], n_streams, axis=1)
    geometry = _color_geometry(spec)
    word_states = pilots.color_word_states(spec.seed, counters)
    dust_states = pilots.dust_state_values(
        spec.seed, counters, spec.codec)
    for local in range(spec.tiles_per_page):
        ty, tx = divmod(local, txs)
        counter = int(counters[local])
        tile_symbols = tuple(
            matrices[stream_id][local] for stream_id in expected)
        tile = _compose_validated_tile(
            spec,
            counter,
            tile_symbols,
            tuple(int(bit) for bit in metadata_bits[local]),
            geometry,
            word_states[local],
            dust_states[local],
        )
        field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = tile
    return field


def color_cells_to_dot_planes(
    field_states: np.ndarray,
    cell_dots: int,
) -> np.ndarray:
    """Canonical state field -> solid-cell C/M/Y device-dot planes."""
    planes = channel.states_to_planes(field_states)
    return np.stack(
        tuple(cells_to_dots(planes[..., plane], cell_dots)
              for plane in range(3)),
        axis=-1,
    )
