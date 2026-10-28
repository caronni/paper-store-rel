"""P2 pins for the pooled -v1 format layer (CMY8-POOLING-PLAN).

Covers the appended rows, the per-stream metadata equation law (incl.
the mandatory bound widening and BOTH trust-floor variants — 16 healthy
tiles, ~24 dead-plane tiles), and the pooled source mapping's canonical
gates plus its byte-equivalence with the -v0 stream-major padded stream.
"""
from __future__ import annotations

import numpy as np
import pytest

from holo.core import fountain
from holo.format import envelope, metadata, streamset
from holo.format.descriptor import CODINGS, Coding, get_coding
# Frozen singletons are module-private (FORMAT-SPACE P1); the
# format-law pins reach them through the public catalog.
CMY7_P120_V0 = CODINGS["c2-cmy7-p120-v0"].codec
CMY8_P120_V0 = CODINGS["c2-cmy8-p120-v0"].codec
from holo.format.registry import (
    DEFAULT_DISCOVERY_ROW_IDS,
    FORMAT_ROWS,
    get_format_row,
)

V1_ROW_IDS = ("c2-cmy8-p120-v1@3328x2304", "c3-cmy8-p120-v1@2240x1536")


# ------------------------------------------------------------------- rows

def test_v1_rows_appended_catalog_only_and_v0_untouched():
    for row_id in V1_ROW_IDS:
        row = get_format_row(row_id)
        assert row.pooled_fountain and row.n_streams == 3
        # identical tile codec => receiver payload dispatch unaffected
        assert row.codec is CMY8_P120_V0
        assert row.symbol_bits == 2087
        v0 = get_format_row(row_id.replace("-v1@", "-v0@"))
        assert not v0.pooled_fountain
        assert v0.codec is row.codec
        assert row.seed != v0.seed          # implicit signaling separates
        assert row_id not in DEFAULT_DISCOVERY_ROW_IDS
    assert DEFAULT_DISCOVERY_ROW_IDS == (
        "c2-r0550@3328x2304",
        "c2-r0700@3328x2304",
        "c3-r0550@2240x1536",
    )
    for coding_id in ("c3-r0550", "c2-r0550", "c2-r0700"):
        assert not get_coding(coding_id).pooled_fountain
    assert not CODINGS["c2-cmy7-p120-v0"].pooled_fountain


def test_pooled_coding_requires_multi_stream_codec():
    with pytest.raises(ValueError, match="at least two streams"):
        Coding("bad-pooled", cell_dots=2, rate_id=None, n_filler=20,
               codec=CMY7_P120_V0, pooled_fountain=True)


# ------------------------------------------------- metadata equation law

def test_equation_index_law_and_bounds():
    assert metadata.equation_index(12_345, 0, 1) == 12_345   # n=1 identity
    assert metadata.equation_index(0, 0, 3) == 0
    assert metadata.equation_index(1000, 2, 3) == 3002
    assert metadata.max_equation_index(1) == metadata.MAX_COUNTER
    assert metadata.max_equation_index(3) == 3 * metadata.MAX_COUNTER
    with pytest.raises(ValueError):
        metadata.equation_index(0, 3, 3)
    with pytest.raises(ValueError):
        metadata.equation_index(metadata.MAX_COUNTER, 0, 3)
    with pytest.raises(ValueError):
        metadata.max_equation_index(0)
    with pytest.raises(ValueError):
        metadata.max_equation_index(64)      # exceeds nonzero LFSR states


def test_pooled_indices_need_the_widened_bound():
    """Pooled indices exceed 2^18: the widening is mandatory, and the
    frozen default bound still refuses them (K call sites untouched)."""
    word = metadata.encode_metadata(0, 918)
    index = metadata.equation_index(metadata.MAX_COUNTER - 1, 2, 3)
    bound = metadata.max_equation_index(3)
    with pytest.raises(ValueError):
        metadata.tile_bit(word, index)
    assert metadata.tile_bit(word, index, max_index=bound) in (0, 1)
    with pytest.raises(ValueError):
        metadata.tile_bits(word, np.asarray([index]))
    got = metadata.tile_bits(word, np.asarray([index]), max_index=bound)
    assert got.shape == (1,)
    with pytest.raises(ValueError):
        metadata.decode_metadata([(index, 0)])
    # single-stream coefficient values are a strict prefix of the wide
    # table: the widening cannot move K's equations
    np.testing.assert_array_equal(
        metadata.coefficient_masks(np.arange(64)),
        metadata.coefficient_masks(np.arange(64), max_index=bound))


def _pooled_observations(word, counters, streams=(0, 1, 2), n=3):
    bound = metadata.max_equation_index(n)
    for counter in counters:
        for stream in streams:
            index = metadata.equation_index(counter, stream, n)
            yield index, int(metadata.tile_bit(word, index,
                                               max_index=bound))


def test_pooled_trust_floor_sixteen_healthy_tiles():
    word = metadata.encode_metadata(0, 2754)   # k_meta = 3*918
    bound = metadata.max_equation_index(3)
    ok = metadata.decode_metadata(
        _pooled_observations(word, range(100, 116)), max_index=bound)
    assert ok.ok and ok.k == 2754 and ok.version == 0
    assert ok.n_unique_counters == 48
    short = metadata.decode_metadata(
        _pooled_observations(word, range(100, 115)), max_index=bound)
    assert not short.ok and short.check_shortfall == 3


def test_pooled_trust_floor_dead_plane_needs_24_tiles():
    """Y dead: every third index punctured — consecutive-rank is gone,
    the 48-equation floor binds at 24 tiles (design §2.4)."""
    word = metadata.encode_metadata(0, 917)
    bound = metadata.max_equation_index(3)
    ok = metadata.decode_metadata(
        _pooled_observations(word, range(24), streams=(0, 1)),
        max_index=bound)
    assert ok.ok and ok.k == 917
    assert ok.n_unique_counters == 48
    short = metadata.decode_metadata(
        _pooled_observations(word, range(23), streams=(0, 1)),
        max_index=bound)
    assert not short.ok and short.check_shortfall == 2


def test_pooled_distinct_vs_replicated_equation_density():
    """-v0 replication: three same-counter copies are ONE equation; the
    pooled distinct indexing yields three."""
    word = metadata.encode_metadata(0, 555)
    counter = 4242
    replicated = metadata.decode_metadata(
        [(counter, int(metadata.tile_bit(word, counter)))] * 3)
    assert replicated.n_unique_counters == 1
    bound = metadata.max_equation_index(3)
    distinct = metadata.decode_metadata(
        _pooled_observations(word, [counter]), max_index=bound)
    assert distinct.n_unique_counters == 3


def test_pooled_inconsistent_equation_is_fatal():
    word = metadata.encode_metadata(0, 777)
    bound = metadata.max_equation_index(3)
    rows = list(_pooled_observations(word, range(48)))
    index, bit = rows[7]
    rows.append((index, bit ^ 1))
    bad = metadata.decode_metadata(rows, max_index=bound)
    assert bad.inconsistent and not bad.ok


# ------------------------------------------------- pooled source mapping

def _cmy8_stream_set() -> streamset.StreamSet:
    return streamset.StreamSet(tuple(
        (stream.stream_id, stream.symbol_bits)
        for stream in CMY8_P120_V0.streams))


def test_pooled_pack_matches_stream_major_padded_stream():
    payload = bytes(range(256)) * 41                     # 10,496 B
    stream_set = _cmy8_stream_set()
    k_meta, pooled_rows = streamset.pooled_pack_payload(payload, stream_set)
    v0 = streamset.pack_payload(payload, stream_set)
    assert k_meta == v0.k_total                          # same canonical K
    assert pooled_rows.shape[0] == 3 * k_meta
    s_bits = streamset.pooled_symbol_bits(stream_set)
    pooled_flat = fountain.unpack_rows(pooled_rows, s_bits).reshape(-1)
    v0_flat = np.concatenate([
        fountain.unpack_rows(stream.rows, stream.symbol_bits).reshape(-1)
        for stream in v0.streams])
    np.testing.assert_array_equal(pooled_flat, v0_flat)  # same padded bits


def test_pooled_unwrap_round_trip_and_canonical_gates():
    payload = b"pooled fountain round trip payload" * 99
    stream_set = _cmy8_stream_set()
    k_meta, rows_packed = streamset.pooled_pack_payload(payload, stream_set)
    s_bits = streamset.pooled_symbol_bits(stream_set)
    rows = fountain.unpack_rows(rows_packed, s_bits)
    assert streamset.pooled_unwrap_solved(rows, stream_set, k_meta) \
        == payload
    with pytest.raises(streamset.StreamSetIntegrityError,
                       match="noncanonical"):
        padded = np.concatenate(
            [rows, np.zeros((3, s_bits), np.uint8)], axis=0)
        streamset.pooled_unwrap_solved(padded, stream_set, k_meta + 1)
    corrupt = rows.copy()
    corrupt[0, :8] ^= 1                                  # SHA header bits
    with pytest.raises(streamset.StreamSetIntegrityError,
                       match="verification failed"):
        streamset.pooled_unwrap_solved(corrupt, stream_set, k_meta)
    dirty = rows.copy()
    dirty[-1, -1] = 1                                    # padding bit
    with pytest.raises(streamset.StreamSetIntegrityError,
                       match="padding"):
        streamset.pooled_unwrap_solved(dirty, stream_set, k_meta)


def test_pooled_symbol_bits_is_the_widest_stream_and_the_envelope_law_follows():
    """A column-group pool (docs/CMY8-COLUMN-GROUPS.md §3.4): one symbol
    width — the widest stream's — and an envelope of k_total = n * k_meta
    rows of it, whatever the narrower streams carry per tile."""
    uneven = streamset.StreamSet((("C", 9), ("M", 9), ("Y", 8)))
    assert streamset.pooled_symbol_bits(uneven) == 9
    for length in (0, 1, 36, 999):
        expected = -(-(length + envelope.OVERHEAD_BYTES) * 8 // (3 * 9))
        assert streamset.pooled_source_symbol_count(length, uneven) \
            == expected
        k_meta, rows = streamset.pooled_pack_payload(bytes(length), uneven)
        assert k_meta == expected and rows.shape == (3 * k_meta, 2)
    payload = b"column groups" * 40
    k_meta, packed = streamset.pooled_pack_payload(payload, uneven)
    rows = fountain.unpack_rows(packed, 9)
    assert streamset.pooled_unwrap_solved(rows, uneven, k_meta) == payload


def test_pooled_k_meta_matches_v0_common_k_arithmetic():
    stream_set = _cmy8_stream_set()
    for length in (1, 36, 5_973, 718_413):
        wrapped_len = length + envelope.OVERHEAD_BYTES
        expected = -(-wrapped_len * 8 // stream_set.total_symbol_bits)
        assert streamset.source_symbol_count(length, stream_set) == expected
        k_meta, _rows = streamset.pooled_pack_payload(
            bytes(length), stream_set)
        assert k_meta == expected
