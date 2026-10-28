from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo3.format import fountain, keystream

from holo3.tests import _h3_support

# hand-copied second copy of tests/holo/test_holo_fountain.py
SEED = b"holo/v1/test/fountain"
GOLDEN_ASSIGNMENT_99083 = (
    "a3db8e1013db2216c7c84791b7f463f0264970ba084f8e1ae7d8b7e207c58227"
)


def test_block_size_cap_is_frozen():
    assert fountain.BLOCK_K_MAX == 16384
    assert fountain.n_blocks_for(1) == 1
    assert fountain.n_blocks_for(16384) == 1
    assert fountain.n_blocks_for(16385) == 2
    assert fountain.n_blocks_for(99083) == 7
    assert fountain.n_blocks_for(40000) == 3


def test_block_assignment_golden():
    code = fountain.VolumeCode(99083, 8, SEED, 1872)
    assert code.n_blocks == 7
    digest = hashlib.sha256()
    for page in (0, 1, 105):
        block_of, row_of = code.page_assignment(page)
        digest.update(np.asarray(block_of, dtype="<i4").tobytes())
        digest.update(np.asarray(row_of, dtype="<i8").tobytes())
    _h3_support.assert_golden("assignment 99083", digest.hexdigest(),
                              GOLDEN_ASSIGNMENT_99083)


def test_blocks_own_contiguous_source_ranges():
    code = fountain.VolumeCode(40000, 8, SEED, 1872)
    assert code.n_blocks == 3
    assert code.k_per_block == (13334, 13333, 13333)
    assert sum(code.k_per_block) == 40000
    assert code.block_offsets == (0, 13334, 26667)
    assert max(code.k_per_block) - min(code.k_per_block) <= 1


@pytest.mark.parametrize("k_total,tiles_per_page", [
    (40000, 1872), (99083, 1872), (300, 128), (17000, 49), (1, 64),
])
def test_per_page_quota_is_an_exact_partition(k_total: int,
                                              tiles_per_page: int):
    code = fountain.VolumeCode(k_total, 8, SEED, tiles_per_page)
    for page in range(4):
        quota = code.quotas(page)
        assert int(quota.sum()) == tiles_per_page
        assert int(quota.max()) - int(quota.min()) <= 1
        block_of, _row_of = code.page_assignment(page)
        assert np.array_equal(
            np.bincount(block_of, minlength=code.n_blocks), quota)


def test_page_assignment_rows_are_dense_within_each_block():
    code = fountain.VolumeCode(40000, 8, SEED, 1872)
    seen: dict[int, list[int]] = {b: [] for b in range(code.n_blocks)}
    for page in range(3):
        block_of, row_of = code.page_assignment(page)
        for block, row in zip(block_of.tolist(), row_of.tolist()):
            seen[block].append(row)
    for block, rows in seen.items():
        assert sorted(rows) == list(range(len(rows)))


def test_assignment_is_shuffled_not_blockwise_contiguous():
    code = fountain.VolumeCode(40000, 8, SEED, 1872)
    block_of, _row_of = code.page_assignment(0)
    assert not np.array_equal(block_of, np.sort(block_of))


def test_pooled_esi_is_counter_times_streams_plus_stream_index():
    code = fountain.VolumeCode(40000, 40, SEED, 64, n_streams=3)
    assert code.n_streams == 3
    assert code.symbols_per_page == 64 * 3
    block_of, row_of = code.page_assignment(1)
    assert block_of.size == row_of.size == 192
    for counter in range(64):
        for stream in range(3):
            esi = 64 * 3 + counter * 3 + stream
            assert code.block_row_of(esi) == (
                int(block_of[counter * 3 + stream]),
                int(row_of[counter * 3 + stream]))


def test_pooled_one_stream_is_bit_identical_to_the_single_stream_form():
    pooled = fountain.VolumeCode(40000, 64, SEED, 737, n_streams=1)
    plain = fountain.VolumeCode(40000, 64, SEED, 737)
    assert pooled.symbols_per_page == plain.symbols_per_page
    assert pooled.k_per_block == plain.k_per_block
    assert pooled.block_offsets == plain.block_offsets
    for page in range(4):
        pooled_block, pooled_row = pooled.page_assignment(page)
        plain_block, plain_row = plain.page_assignment(page)
        assert np.array_equal(pooled_block, plain_block)
        assert np.array_equal(pooled_row, plain_row)
        assert pooled_block.dtype == plain_block.dtype
        assert pooled_row.dtype == plain_row.dtype


def test_a_colour_stream_shuffles_in_its_own_keystream_domain():
    plain = fountain.VolumeCode(40000, 64, SEED, 737)
    main = fountain.VolumeCode(40000, 64, SEED, 737, stream_id="main",
                               fountain_aux=0)
    cyan = fountain.VolumeCode(40000, 64, SEED, 737, stream_id="C",
                               fountain_aux=1)
    assert not np.array_equal(plain.page_assignment(0)[0],
                              main.page_assignment(0)[0])
    assert not np.array_equal(main.page_assignment(0)[0],
                              cyan.page_assignment(0)[0])
    assert main.fountain_row_domain == keystream.DOMAIN_COLOR_FOUNTAIN_ROW
    assert plain.fountain_row_domain == keystream.DOMAIN_FOUNTAIN_ROW
    assert cyan.stream_aux == 1


def test_the_identity_aux_is_honoured_not_re_derived_from_the_stream_name():
    misnamed = fountain.VolumeCode(4000, 64, SEED, 737, stream_id="Y",
                                   fountain_aux=1)
    cyan = fountain.VolumeCode(4000, 64, SEED, 737, stream_id="C",
                               fountain_aux=1)
    assert misnamed.stream_aux == 1
    assert np.array_equal(misnamed.page_assignment(0)[0],
                          cyan.page_assignment(0)[0])


def test_dropping_one_stream_leaves_the_remaining_quotas_partitioning():
    code = fountain.VolumeCode(40000, 40, SEED, 64, n_streams=3)
    per_stream = [code.quotas(2, stream) for stream in range(3)]
    for quota in per_stream:
        assert int(quota.sum()) == 64
    without_y = per_stream[0] + per_stream[1]
    assert int(without_y.sum()) == 128
    assert int(without_y.min()) > 0


def _source(k: int, s_bits: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(
        0, 2, size=(k, s_bits)).astype(np.uint8)


def _generator_row(code: fountain.VolumeCode, esi: int) -> np.ndarray:
    block, row = code.block_row_of(esi)
    k_block = code.k_per_block[block]
    if row < k_block:
        out = np.zeros(k_block, dtype=np.uint8)
        out[row] = 1
        return out
    if code.stream_id is None:
        return keystream.fountain_rows_bits(code.seed, block, [row],
                                            k_block)[0]
    return keystream.color_fountain_rows_bits(
        code.seed, code.stream_aux, block, [row], k_block)[0]


def _symbol(code: fountain.VolumeCode, source: np.ndarray,
            esi: int) -> np.ndarray:
    block, _row = code.block_row_of(esi)
    offset = code.block_offsets[block]
    rows = source[offset:offset + code.k_per_block[block]]
    coefficients = _generator_row(code, esi).astype(bool)
    if not coefficients.any():
        return np.zeros(code.s_bits, dtype=np.uint8)
    return np.bitwise_xor.reduce(rows[coefficients], axis=0).astype(np.uint8)


def _naive_ge(rows: list[np.ndarray], values: list[np.ndarray],
              k: int) -> tuple[int, np.ndarray | None]:
    masks = [int("".join(str(int(b)) for b in row[::-1]), 2) for row in rows]
    vals = [value.copy() for value in values]
    pivot_of: dict[int, int] = {}
    for index in range(len(masks)):
        row = masks[index]
        value = vals[index]
        while row:
            pivot = (row & -row).bit_length() - 1
            if pivot not in pivot_of:
                pivot_of[pivot] = index
                masks[index] = row
                vals[index] = value
                break
            other = pivot_of[pivot]
            row ^= masks[other]
            value = value ^ vals[other]
        else:
            masks[index] = 0
            vals[index] = value
    rank = len(pivot_of)
    if rank < k:
        return rank, None
    out = np.zeros((k, values[0].size), dtype=np.uint8)
    for column in range(k - 1, -1, -1):
        index = pivot_of[column]
        accumulated = vals[index].copy()
        mask = masks[index] & ~(1 << column)
        while mask:
            bit = (mask & -mask).bit_length() - 1
            accumulated ^= out[bit]
            mask &= mask - 1
        out[column] = accumulated
    return rank, out


@pytest.mark.parametrize("dropped", [(), (0,), (0, 5, 17), (3, 4, 5, 6)])
def test_try_solve_agrees_with_a_naive_ge_oracle(dropped: tuple):
    k, s_bits, tiles_per_page = 100, 17, 64
    code = fountain.VolumeCode(k, s_bits, SEED, tiles_per_page)
    assert code.n_blocks == 1
    source = _source(k, s_bits, 20260829)
    esis = [esi for esi in range(150)
            if code.block_row_of(esi)[1] not in dropped]
    decoder = fountain.Decoder(code)
    rows = []
    values = []
    for esi in esis:
        symbol = _symbol(code, source, esi)
        assert decoder.add_symbol(esi, symbol)
        rows.append(_generator_row(code, esi))
        values.append(symbol)
    solved = decoder.try_solve()
    rank, oracle = _naive_ge(rows, values, k)
    assert rank == k
    assert oracle is not None and np.array_equal(oracle, source)
    assert solved is not None and np.array_equal(solved, source)
    status = decoder.block_status()
    assert status == (
        fountain.BlockStatus(0, k, len(esis), k, k, True, 0, 1, k),)
    assert status[0].short == 0


def test_a_rank_deficient_set_reports_its_shortfall_and_solves_nothing():
    k, s_bits, tiles_per_page = 100, 17, 64
    code = fountain.VolumeCode(k, s_bits, SEED, tiles_per_page)
    source = _source(k, s_bits, 4242)
    decoder = fountain.Decoder(code)
    esis = list(range(60))
    for esi in esis:
        decoder.add_symbol(esi, _symbol(code, source, esi))
    assert decoder.try_solve() is None
    (status,) = decoder.block_status()
    assert (status.block, status.needed, status.have, status.solved) == (
        0, k, len(esis), False)
    assert status.rows == len(esis) and status.rank is None
    assert status.short == k - len(esis) and status.groups_open == 1
    oracle_rank, oracle = _naive_ge(
        [_generator_row(code, esi) for esi in esis],
        [_symbol(code, source, esi) for esi in esis], k)
    assert oracle is None and oracle_rank == status.rows


def test_the_systematic_fast_path_never_invokes_gaussian_elimination(
        monkeypatch):
    k, s_bits = 64, 24
    code = fountain.VolumeCode(k, s_bits, SEED, tiles_per_page=k)
    source = _source(k, s_bits, 7)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("GE must not run on the systematic fast path")

    monkeypatch.setattr(fountain, "_ge_solve_gf2", forbidden)
    decoder = fountain.Decoder(code)
    for esi in range(k):
        assert code.block_row_of(esi)[1] < k
        decoder.add_symbol(esi, _symbol(code, source, esi))
    solved = decoder.try_solve()
    assert solved is not None and np.array_equal(solved, source)


def test_repair_rows_come_from_the_fountain_row_keystream():
    k, s_bits = 100, 17
    code = fountain.VolumeCode(k, s_bits, SEED, tiles_per_page=64)
    items = []
    for esi in range(150):
        block, row = code.block_row_of(esi)
        items.append((row, esi))
    items.sort()
    decoder = fountain.Decoder(code)
    packed = decoder._packed_generator_rows(
        0, [(row, esi, 0, s_bits) for row, esi in items])
    got = fountain._unpack_bits_2d(packed, k)
    expected = np.stack([_generator_row(code, esi) for _row, esi in items])
    assert np.array_equal(got, expected)
    assert sum(1 for row, _esi in items if row >= k) >= 10


def test_a_conflicting_symbol_at_one_esi_is_fatal():
    code = fountain.VolumeCode(64, 24, SEED, tiles_per_page=64)
    source = _source(64, 24, 8)
    decoder = fountain.Decoder(code)
    symbol = _symbol(code, source, 3)
    assert decoder.add_symbol(3, symbol) is True
    assert decoder.add_symbol(3, symbol) is False
    conflicting = symbol.copy()
    conflicting[7] ^= 1
    with pytest.raises(fountain.FountainIntegrityError,
                       match="conflicting certified values at ESI 3"):
        decoder.add_symbol(3, conflicting)
    assert issubclass(fountain.FountainIntegrityError, ValueError)


def test_block_status_counts_arrivals_per_block():
    code = fountain.VolumeCode(20000, 16, SEED, tiles_per_page=64)
    assert code.n_blocks == 2
    source = _source(20000, 16, 9)
    decoder = fountain.Decoder(code)
    for esi in range(128):
        decoder.add_symbol(esi, _symbol(code, source, esi))
    assert decoder.try_solve() is None
    status = decoder.block_status()
    assert len(status) == 2
    assert sum(block.have for block in status) == 128
    assert not any(block.solved for block in status)
    assert tuple(block.needed for block in status) == code.k_per_block


def test_unpack_rows_is_the_inverse_of_the_symbol_packing():
    rng = np.random.default_rng(21)
    bits = rng.integers(0, 2, size=37).astype(np.uint8)
    assert np.array_equal(
        fountain.unpack_rows(np.packbits(bits), 37), bits.reshape(1, 37))
