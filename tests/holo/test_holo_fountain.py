"""fountain-v2 core: round trips, per-page block assignment, the crop
battery (the occupancy property the 2026-07-19 review found missing in
v1), reserve scaling, conflict fatality, determinism vs the pure-Python
keystream spec, and promise-grade capacity arithmetic."""


import hashlib

import numpy as np
import pytest

from holo.core import capacity
from holo.core import fountain as fnt
from holo.core import keystream_spec as ref

SEED = b"holo/v1/test/fountain"
GOLDEN_ASSIGNMENT_99083 = (
    "a3db8e1013db2216c7c84791b7f463f0264970ba084f8e1ae7d8b7e207c58227"
)


def _pack(src_bits):
    return np.packbits(np.asarray(src_bits, np.uint8), axis=1)


def _roundtrip(code, src_bits, esis_kept):
    """Feed the kept ESIs' symbols through a fresh Decoder; return the
    solved source bits or None."""
    packed = _pack(src_bits)
    dec = fnt.Decoder(code)
    for esi in esis_kept:
        dec.add_symbol(int(esi), code.encode_symbols(packed, [int(esi)])[0])
    return dec.try_solve()


def test_roundtrip_single_block():
    rng = np.random.default_rng(1)
    k, s, tpp = 300, 257, 128               # odd S exercises the packing tail
    code = fnt.VolumeCode(k, s, SEED, tiles_per_page=tpp)
    assert code.n_blocks == 1 and code.k_per_block == (300,)
    src = rng.integers(0, 2, size=(k, s)).astype(np.uint8)
    packed = _pack(src)
    n_esi = 3 * tpp                          # 3 pages, source + repair
    syms = code.encode_symbols(packed, np.arange(n_esi))
    # every source row appears verbatim at exactly one ESI
    src_at = {}
    for esi in range(n_esi):
        r = code.source_row_of(esi)
        if r is not None:
            src_at.setdefault(r, esi)
    assert len(src_at) == k
    for r, esi in src_at.items():
        assert np.array_equal(syms[esi], src[r])
    # decode from a random K+16 subset spanning source AND repair
    pick = rng.permutation(n_esi)[:k + 16]
    out = _roundtrip(code, src, pick)
    assert out is not None and np.array_equal(out, src)


def test_systematic_fast_path_no_ge(monkeypatch):
    rng = np.random.default_rng(2)
    k, s, tpp = 300, 257, 300
    code = fnt.VolumeCode(k, s, SEED, tiles_per_page=tpp)
    src = rng.integers(0, 2, size=(k, s)).astype(np.uint8)
    # page 0 is exactly K tiles: every source row present, no repair
    monkeypatch.setattr(fnt, "_ge_solve_gf2", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("GE must not run on the systematic fast path")))
    out = _roundtrip(code, src, range(tpp))
    assert out is not None and np.array_equal(out, src)


def test_block_split_and_contiguous_layout():
    code = fnt.VolumeCode(40_000, 8, SEED, tiles_per_page=1872)
    assert code.n_blocks == 3                     # ceil(40000/16384)
    assert code.k_per_block == (13334, 13333, 13333)
    assert sum(code.k_per_block) == 40_000
    # blocks own CONTIGUOUS source ranges (not strided)
    assert code.block_offsets == (0, 13334, 26667)


def test_per_page_quota_is_exact_and_shuffled():
    code = fnt.VolumeCode(40_000, 8, SEED, tiles_per_page=1872)
    b = code.n_blocks
    for page in range(6):
        q = code.quotas(page)
        assert int(q.sum()) == 1872              # exact partition
        assert q.max() - q.min() <= 1
        block_of, _ = code.page_assignment(page)
        assert np.array_equal(np.bincount(block_of, minlength=b), q)
    # placement is shuffled, not blockwise-contiguous by local index
    block_of, _ = code.page_assignment(0)
    assert not np.array_equal(block_of, np.sort(block_of))


def test_block_assignment_golden():
    """Domain 8 plus stable tie-breaking pins the full assignment map."""
    code = fnt.VolumeCode(99_083, 8, SEED, tiles_per_page=1872)
    assert code.n_blocks == 7
    digest = hashlib.sha256()
    for page in (0, 1, 105):
        block_of, row_of = code.page_assignment(page)
        digest.update(np.asarray(block_of, dtype="<i4").tobytes())
        digest.update(np.asarray(row_of, dtype="<i8").tobytes())
    assert digest.hexdigest() == GOLDEN_ASSIGNMENT_99083


def test_added_pages_help_all_blocks_uniformly():
    """The false v1 claim, made true: extra pages add repair to EVERY
    block by its quota, never just to finished blocks."""
    code = fnt.VolumeCode(40_000, 8, SEED, tiles_per_page=1872)
    b = code.n_blocks
    per_page = np.zeros(b, dtype=np.int64)
    for page in range(3):
        block_of, _ = code.page_assignment(page)
        per_page += np.bincount(block_of, minlength=b)
    # each block accrued ~ 3 * 1872 / B tiles, spread <= number of pages
    assert per_page.max() - per_page.min() <= 3


# Real multi-block volumes at max page count, sized by the planner, at
# the exact q we ship. These are the cases v1's `block = ESI mod B`
# starved (16/32 blocks lost by a half-page column crop at q=0.5).
CROP_CASES = [
    # (tiles_per_page, tiles_yx, n_pages, q)  -> multi-block volumes
    (1872, (52, 36), 140, 0.5),
    (840, (35, 24), 312, 0.5),
]


def _volume(tpp, n_pages, q, s=64):
    n = n_pages * tpp
    k = capacity.max_k_for(n, q)
    code = fnt.VolumeCode(k, s, SEED, tiles_per_page=tpp)
    assert code.n_blocks > 1                  # exercise the block machinery
    return code, k, s


def _occupancy(code, esis):
    return np.bincount([code.block_row_of(int(e))[0] for e in esis],
                       minlength=code.n_blocks)


@pytest.mark.parametrize("tpp,tiles_yx,n_pages,q", CROP_CASES)
def test_crop_whole_page_loss_guaranteed(tpp, tiles_yx, n_pages, q):
    """Deterministic tier: any set of whole pages down to q of the volume
    gives every block >= K_b (v1's mapping violated this)."""
    code, k, s = _volume(tpp, n_pages, q)
    keep = int(np.ceil(q * n_pages))
    esis = np.arange(keep * tpp)              # first `keep` pages
    have = _occupancy(code, esis)
    assert np.all(have >= np.array(code.k_per_block)), \
        "whole-page crop starved a block"


@pytest.mark.parametrize("tpp,tiles_yx,n_pages,q", CROP_CASES)
def test_crop_column_strip_occupancy(tpp, tiles_yx, n_pages, q):
    """Probabilistic tier: the exact half-page column strip that starved
    v1 now clears every block's quota at q plus a small margin."""
    tys, txs = tiles_yx
    code, k, s = _volume(tpp, n_pages, q)
    cols = -(-txs * 6 // 10)                  # left 60% of columns, all pages
    esis = [p * tpp + ty * txs + tx
            for p in range(n_pages) for ty in range(tys)
            for tx in range(cols)]
    have = _occupancy(code, esis)
    frac = len(esis) / (n_pages * tpp)
    assert np.all(have >= np.array(code.k_per_block)), \
        f"column strip ({frac:.2f} of tiles) starved a block"


def test_crop_random_subset_at_q_plus_margin():
    """Random exact-q+ε subsets clear every block (concentration), where
    v1 failed 0/2000 at exact q."""
    code, k, s = _volume(1872, 140, 0.5)
    n = 140 * 1872
    rng = np.random.default_rng(11)
    need = int(np.ceil(0.52 * n))             # q + 2% margin
    for _ in range(20):
        esis = rng.permutation(n)[:need]
        assert np.all(_occupancy(code, esis) >= np.array(code.k_per_block))


def test_small_multiblock_roundtrip_byte_exact():
    """A 2-block volume decoded whole from a whole-page crop — the full
    encode->decode path, not just occupancy."""
    tpp = 512
    code = fnt.VolumeCode(600, 40, SEED, tiles_per_page=tpp)
    assert code.n_blocks == 1                 # 600 < 16384
    # force 2 blocks with a tiny BLOCK_K_MAX-independent construction:
    code2 = fnt.VolumeCode(20_000, 24, SEED, tiles_per_page=tpp)
    assert code2.n_blocks == 2
    rng = np.random.default_rng(5)
    src = rng.integers(0, 2, size=(20_000, 24)).astype(np.uint8)
    n_pages = 60                              # 60*512 = 30720 >= K + reserve
    keep = 50                                 # 50/60 pages ~ 0.83
    esis = np.arange(keep * tpp)
    assert np.all(_occupancy(code2, esis) >= np.array(code2.k_per_block))
    out = _roundtrip(code2, src, esis)
    assert out is not None and np.array_equal(out, src)


def test_conflict_is_fatal_duplicate_is_noop():
    code = fnt.VolumeCode(300, 32, SEED, tiles_per_page=128)
    src = np.random.default_rng(9).integers(0, 2, (300, 32)).astype(np.uint8)
    sym = code.encode_symbols(_pack(src), [0])[0]
    dec = fnt.Decoder(code)
    assert dec.add_symbol(0, sym) is True
    assert dec.add_symbol(0, sym) is False           # identical duplicate
    with pytest.raises(fnt.FountainIntegrityError):
        dec.add_symbol(0, sym ^ 1)                   # conflicting value


def test_skip_ge_below_kb(monkeypatch):
    """A block below K_b symbols must not even attempt elimination."""
    code = fnt.VolumeCode(300, 16, SEED, tiles_per_page=128)
    src = np.random.default_rng(3).integers(0, 2, (300, 16)).astype(np.uint8)
    monkeypatch.setattr(fnt, "_ge_solve_gf2", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("GE attempted below K_b")))
    dec = fnt.Decoder(code)
    for esi in range(100):                            # far below K=300
        dec.add_symbol(esi, code.encode_symbols(_pack(src), [esi])[0])
    assert dec.try_solve() is None


def test_repair_rows_match_reference_spec():
    code = fnt.VolumeCode(300, 8, SEED, tiles_per_page=128)
    # find a repair ESI in block 0 and check coefficients vs the spec
    esi = next(e for e in range(1000) if code.source_row_of(e) is None
               and code.block_row_of(e)[0] == 0)
    b, r = code.block_row_of(esi)
    row = code.generator_row(esi)
    assert row.shape == (300,) and set(np.unique(row)) <= {0, 1}
    assert np.array_equal(row, code.generator_row(esi))       # deterministic
    for j in (0, 1, 137, 298, 299):
        assert int(row[j]) == ref.fountain_coeff_bit(SEED, b, r, j)
    assert 100 < int(row.sum()) < 200                         # dense ~K/2
    # a different seed forks the stream
    other = fnt.VolumeCode(300, 8, b"holo/v1/other", tiles_per_page=128)
    assert not np.array_equal(row, other.generator_row(esi))


def test_reserve_scales_with_block_count():
    assert capacity.rank_reserve_for(1) == 16
    assert capacity.rank_reserve_for(2) == 17
    assert capacity.rank_reserve_for(32) == 21     # 16 + ceil(log2 32)
    assert capacity.rank_reserve_for(48) == 22     # 16 + 6


def test_three_stream_reserve_covers_all_stream_blocks():
    assert capacity.rank_reserve_for(1, solves_per_block=3) == 18
    assert capacity.rank_reserve_for(2, solves_per_block=3) == 19
    assert capacity.rank_reserve_for(32, solves_per_block=3) == 23
    assert capacity.rank_reserve_for(32) == 21
    with pytest.raises(ValueError):
        capacity.rank_reserve_for(1, solves_per_block=0)


def test_max_k_for_arithmetic():
    # small: budget 50, one block, reserve 16 -> K = 34
    assert capacity.max_k_for(100, 0.5) == 34
    assert capacity.max_k_for(32, 0.5) == 0
    # sweep: maximality + the reserve-scaled feasibility invariant
    def reserve_cost(k):
        nb = fnt.n_blocks_for(k)
        return capacity.rank_reserve_for(nb) * nb if nb else 0

    for n in (17, 100, 16_384, 32_768, 262_080):
        for q in (0.3, 0.5, 0.75, 1.0):
            k = capacity.max_k_for(n, q)
            budget = capacity.source_budget(n, q)
            assert k + reserve_cost(k) <= budget           # feasible
            assert (k + 1) + reserve_cost(k + 1) > budget  # maximal


def test_three_stream_capacity_uses_stronger_reserve():
    one = capacity.max_k_for_pages(840, 20, 0.5)
    three = capacity.max_k_for_pages(840, 20, 0.5, n_streams=3)
    assert 0 < three < one
    assert capacity.page_capacity_sufficient(
        three, 840, 20, 0.5, n_streams=3)
    assert not capacity.page_capacity_sufficient(
        three + 1, 840, 20, 0.5, n_streams=3)


def test_color_fountain_domains_separate_streams_and_leave_k_default():
    k, s, tpp = 300, 17, 128
    default = fnt.VolumeCode(k, s, SEED, tiles_per_page=tpp)
    streams = tuple(
        fnt.VolumeCode(
            k,
            s,
            SEED,
            tiles_per_page=tpp,
            stream_id=stream,
            fountain_aux={"main": 0, "C": 1, "M": 2, "Y": 3}[stream],
        )
        for stream in ("main", "C", "M", "Y")
    )
    repair_esi = 3 * tpp
    rows = [code.generator_row(repair_esi) for code in (default,) + streams]
    assert len({row.tobytes() for row in rows}) == 5

    assignments = [
        fnt.VolumeCode(
            20_000,
            1,
            SEED,
            tiles_per_page=tpp,
            stream_id=stream,
            fountain_aux={"main": 0, "C": 1, "M": 2, "Y": 3}[stream],
        ).page_assignment(0)[0]
        for stream in ("main", "C", "M", "Y")
    ]
    assert len({assignment.tobytes() for assignment in assignments}) == 4
    with pytest.raises(ValueError, match="unknown color fountain stream"):
        fnt.VolumeCode(
            k, s, SEED, tiles_per_page=tpp,
            stream_id="K", fountain_aux=0)
    with pytest.raises(ValueError, match="requires both"):
        fnt.VolumeCode(
            k, s, SEED, tiles_per_page=tpp, stream_id="main")
    with pytest.raises(ValueError, match="requires both"):
        fnt.VolumeCode(
            k, s, SEED, tiles_per_page=tpp, fountain_aux=0)
    with pytest.raises(ValueError, match="fountain_aux must be 1"):
        fnt.VolumeCode(
            k, s, SEED, tiles_per_page=tpp,
            stream_id="C", fountain_aux=2)


@pytest.mark.parametrize(
    ("stream_id", "stream_aux"),
    (("main", 0), ("C", 1), ("M", 2), ("Y", 3)),
)
def test_color_volume_code_matches_reference_domains(
    stream_id: str,
    stream_aux: int,
):
    # Repair coefficients are compared to the pure-Python format mirror.
    code = fnt.VolumeCode(
        300,
        8,
        SEED,
        tiles_per_page=128,
        stream_id=stream_id,
        fountain_aux=stream_aux,
    )
    esi = next(
        value for value in range(1000)
        if code.source_row_of(value) is None)
    block, row = code.block_row_of(esi)
    coefficients = code.generator_row(esi)
    for column in (0, 1, 127, 128, 299):
        assert int(coefficients[column]) == \
            ref.color_fountain_coeff_bit(
                SEED, stream_aux, block, row, column)

    # Block assignment is compared from raw reference keys, including the
    # stable local-tile tie breaker and exact page quota partition.
    tpp, page = 17, 2
    assignment_code = fnt.VolumeCode(
        20_000,
        1,
        SEED,
        tiles_per_page=tpp,
        stream_id=stream_id,
        fountain_aux=stream_aux,
    )
    block_of, _row_of = assignment_code.page_assignment(page)
    local = np.arange(tpp, dtype=np.int64)
    keys = np.asarray([
        ref.color_block_assign_key(
            SEED, stream_aux, page, int(tile))
        for tile in local
    ], dtype=np.uint64)
    order = np.lexsort((local, keys))
    expected = np.empty(tpp, dtype=np.int64)
    expected[order] = np.repeat(
        np.arange(assignment_code.n_blocks, dtype=np.int64),
        assignment_code.quotas(page),
    )
    assert np.array_equal(block_of, expected)


@pytest.mark.parametrize("stream_id", ("main", "C", "M", "Y"))
def test_color_fountain_repair_roundtrip(stream_id: str):
    rng = np.random.default_rng(109)
    k, s, tpp = 300, 31, 128
    code = fnt.VolumeCode(
        k,
        s,
        SEED,
        tiles_per_page=tpp,
        stream_id=stream_id,
        fountain_aux={"main": 0, "C": 1, "M": 2, "Y": 3}[stream_id],
    )
    source = rng.integers(0, 2, (k, s), dtype=np.uint8)
    kept = rng.permutation(3 * tpp)[:k + 20]
    assert any(code.source_row_of(int(esi)) is None for esi in kept)
    solved = _roundtrip(code, source, kept)
    assert solved is not None
    assert np.array_equal(solved, source)


def test_stream_count_validation_is_not_budget_dependent():
    with pytest.raises(ValueError, match="n_streams"):
        capacity.max_k_for(0, 0.5, n_streams=0)
    with pytest.raises(ValueError, match="n_streams"):
        capacity.page_capacity_sufficient(0, 10, 1, 0.5, n_streams=0)
    with pytest.raises(TypeError, match="n_streams"):
        capacity.max_k_for_pages(10, 1, 0.5, n_streams=True)


def test_whole_page_capacity_regressions():
    assert not capacity.page_capacity_sufficient(99_083, 1872, 106, 0.5)
    assert capacity.page_capacity_sufficient(99_083, 1872, 107, 0.5)
    assert capacity.max_k_for_pages(1872, 106, 0.5) == 98_924
    assert not capacity.page_capacity_sufficient(98_925, 1872, 106, 0.5)
    assert not capacity.page_capacity_sufficient(157_041, 1872, 120, 0.7)
    assert capacity.page_capacity_sufficient(157_041, 1872, 121, 0.7)


def test_fixed_page_feasibility_is_nonmonotone_across_block_counts():
    assert not capacity.page_capacity_sufficient(179_521, 840, 307, 0.7)
    assert capacity.page_capacity_sufficient(180_225, 840, 307, 0.7)
    assert capacity.max_k_for_pages(840, 307, 0.7) == 180_276
    assert not capacity.page_capacity_sufficient(180_277, 840, 307, 0.7)


def test_worst_retained_pages_clear_each_block_with_reserve():
    cases = ((99_083, 1872, 107, 0.5),
             (157_041, 1872, 121, 0.7),
             (180_225, 840, 307, 0.7))
    for k_total, tiles_per_page, n_pages, q in cases:
        n_blocks = fnt.n_blocks_for(k_total)
        reserve = capacity.rank_reserve_for(n_blocks)
        worst_have = (capacity.retained_pages(n_pages, q)
                      * (tiles_per_page // n_blocks))
        largest_block = -(-k_total // n_blocks)
        assert worst_have >= largest_block + reserve


def test_pack_source_matches_stream_bit_order():
    k, s = 30, 47
    stream = bytes(range(k * s // 8 - 5))     # fits inside K*S bits
    packed = fnt.pack_source(stream, k, s)
    assert packed.shape == (k, -(-s // 8))
    # reference: MSB-first flat unpack, row-major slice
    flat = np.unpackbits(np.frombuffer(stream, np.uint8))
    ref_rows = np.zeros((k, s), np.uint8)
    ref_rows.reshape(-1)[:flat.size] = flat[:k * s]
    got = fnt.unpack_rows(packed, s)
    assert np.array_equal(got, ref_rows)


def test_pack_source_chunked_matches_unchunked(monkeypatch):
    # Pin the chunk-walking branch of the shared pack_bit_slice kernel
    # against the single-chunk result: a mid-byte chunk start must not
    # change a single bit of the K path's printed-format mapping.
    k, s = 61, 13                              # 793 bits, chunks land mid-byte
    stream = bytes((i * 37 + 5) & 0xFF for i in range(k * s // 8 - 3))
    unchunked = fnt.pack_source(stream, k, s)
    monkeypatch.setattr(fnt, "CHUNK_BITS", 29)
    chunked = fnt.pack_source(stream, k, s)
    assert np.array_equal(chunked, unchunked)


def test_payload_bytes_and_validation():
    assert capacity.payload_bytes(130_528, 2_107) == (130_528 * 2_107) // 8
    assert capacity.payload_bytes(3, 5) == 1
    with pytest.raises(ValueError):
        capacity.payload_bytes(1, 0)
    with pytest.raises(ValueError):
        capacity.max_k_for(100, 0.0)
    with pytest.raises(ValueError):
        fnt.VolumeCode(0, 8, SEED, tiles_per_page=128)
    with pytest.raises(ValueError):
        fnt.VolumeCode(300, 8, SEED, tiles_per_page=0)
    code = fnt.VolumeCode(300, 257, SEED, tiles_per_page=128)
    with pytest.raises(ValueError):        # wrong packed source shape
        code.encode_symbols(np.zeros((299, 33), np.uint8), [0])
    dec = fnt.Decoder(code)
    with pytest.raises(ValueError):
        dec.add_symbol(-1, np.zeros(257, np.uint8))
    with pytest.raises(ValueError):        # wrong symbol width
        dec.add_symbol(0, np.zeros(9, np.uint8))
