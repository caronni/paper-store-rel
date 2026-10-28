"""P1 pins for the pooled multistream fountain (CMY8-POOLING-PLAN).

Three families:

* the FORMAT-FORK GUARD — the generalized ``VolumeCode`` at
  ``n_streams=1`` is bit-identical to the frozen fountain-v2 assignment,
  pinned against a verbatim pre-change oracle (the cold-search-precedent
  pattern: the old derivation lives here as the test-local reference);
* the stream-exact assignment law (quota values/sums, per-block counts,
  consecutive rows, complete source coverage, the deterministic
  dead-plane arithmetic) plus frozen pooled-assignment digests;
* the three-tier pooled capacity predicate and ``pooled_max_k_for_pages``
  (truth table, tier-2 strengthening, page-inflation documentation —
  whether tier 3 participates is the caller's dial POLICY, pinned in
  gen.plan (``enforce_plane_tier``) — and the
  reserve/capacity/compute parity corners with the documented numbers
  from docs/CMY8-POOLED-FOUNTAIN.md §2.3).
"""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

import holo.core.fountain as fnt
from holo.core import capacity
from holo.core.keystream import DOMAIN_BLOCK_ASSIGN, keys64

SEED = b"pooled-fountain-p1-test-seed"


# ------------------------------------------------------------------ oracle

def _oracle_quotas(t: int, b: int, page: int) -> np.ndarray:
    """Verbatim pre-generalization fountain-v2 per-page quota rule."""
    base, rem = divmod(t, b)
    q = np.full(b, base, dtype=np.int64)
    if rem:
        q[(np.arange(b) - page) % b < rem] += 1
    return q


def _oracle_assignment(code: fnt.VolumeCode, n_pages: int
                       ) -> list[tuple[np.ndarray, np.ndarray]]:
    """Verbatim pre-generalization single-stream page assignment."""
    t, b = code.tiles_per_page, code.n_blocks
    cum = np.zeros(b, np.int64)
    out = []
    for page in range(n_pages):
        keys = keys64(code.seed, DOMAIN_BLOCK_ASSIGN, 0, page,
                      np.arange(t, dtype=np.int64), 0)
        order = np.argsort(keys, kind="stable")
        block_of = np.empty(t, dtype=np.int64)
        block_of[order] = np.repeat(np.arange(b, dtype=np.int64),
                                    _oracle_quotas(t, b, page))
        row_of = np.empty(t, dtype=np.int64)
        for blk in range(b):
            idx = np.flatnonzero(block_of == blk)
            row_of[idx] = cum[blk] + np.arange(idx.size, dtype=np.int64)
        cum = cum + _oracle_quotas(t, b, page)
        out.append((block_of, row_of))
    return out


@pytest.mark.parametrize("k_total,tpp", [(99_083, 1872), (40_000, 840)])
def test_single_stream_assignment_bit_identical_to_oracle(k_total, tpp):
    code = fnt.VolumeCode(k_total, 8, SEED, tiles_per_page=tpp)
    assert code.n_streams == 1 and code.symbols_per_page == tpp
    reference = _oracle_assignment(code, 6)
    for page in range(6):
        block_of, row_of = code.page_assignment(page)
        ref_block, ref_row = reference[page]
        np.testing.assert_array_equal(block_of, ref_block)
        np.testing.assert_array_equal(row_of, ref_row)


def test_single_stream_encode_bit_identical_to_oracle():
    k_total, tpp, s = 40_000, 840, 8
    code = fnt.VolumeCode(k_total, s, SEED, tiles_per_page=tpp)
    rng = np.random.default_rng(7)
    src = fnt.pack_source(rng.bytes(k_total * s // 8), k_total, s)
    reference = _oracle_assignment(code, 3)
    esis = np.asarray([0, 1, 839, 840, 1200, 2519], dtype=np.int64)
    symbols = code.encode_symbols(src, esis)
    for n, esi in enumerate(esis):
        page, local = divmod(int(esi), tpp)
        b, r = reference[page][0][local], reference[page][1][local]
        assert code.block_row_of(int(esi)) == (int(b), int(r))
        kb = code.k_per_block[int(b)]
        if r < kb:
            expected = fnt.unpack_rows(
                src[code.block_offsets[int(b)] + int(r)], s)[0]
        else:
            coefficients = fnt.fountain_rows_bits(
                SEED, int(b), [int(r)], kb)[0]
            sel = np.flatnonzero(coefficients)
            acc = np.bitwise_xor.reduce(src[code.block_offsets[int(b)]
                                            + sel], axis=0)
            expected = fnt.unpack_rows(acc, s)[0]
        np.testing.assert_array_equal(symbols[n], expected)


def test_pooled_rejects_v0_stream_keying_and_bad_counts():
    with pytest.raises(ValueError, match="pooled"):
        fnt.VolumeCode(300, 8, SEED, tiles_per_page=64,
                       stream_id="C", fountain_aux=1, n_streams=3)
    with pytest.raises(ValueError):
        fnt.VolumeCode(300, 8, SEED, tiles_per_page=64, n_streams=0)


# ------------------------------------------- stream-exact assignment law

def _pooled_fixture(k_meta=30_000, tpp=1872, n=3, s_bits=8):
    return fnt.VolumeCode(n * k_meta, s_bits, SEED,
                          tiles_per_page=tpp, n_streams=n)


def test_pooled_quota_law_and_per_block_counts():
    code = _pooled_fixture()
    t, b, n = code.tiles_per_page, code.n_blocks, code.n_streams
    floor_q = t // b
    for page in range(4):
        block_of, row_of = code.page_assignment(page)
        assert block_of.shape == (t * n,)
        for stream in range(n):
            quota = code.quotas(page, stream)
            assert quota.sum() == t
            assert set(np.unique(quota)) <= {floor_q, floor_q + 1}
            seg = block_of[stream::n]
            counts = np.bincount(seg, minlength=b)
            np.testing.assert_array_equal(counts, quota)
        # per-(page, block) rows are consecutive within each stream
        # segment by construction; check block totals meet the floor.
        totals = np.bincount(block_of, minlength=b)
        assert int(totals.min()) >= n * floor_q


def test_pooled_rotation_balances_and_n1_reduction():
    code = _pooled_fixture(k_meta=30_000, tpp=1000, n=3)
    b = code.n_blocks
    rem = code.tiles_per_page % b
    if rem:
        # across b consecutive (page, stream) segments every block gets
        # the remainder bonus exactly rem times in total
        bonus = np.zeros(b, dtype=np.int64)
        for seg in range(b):
            page, stream = divmod(seg, code.n_streams)
            bonus += code.quotas(page, stream) - (code.tiles_per_page // b)
        assert set(bonus.tolist()) == {rem}
    single = fnt.VolumeCode(40_000, 8, SEED, tiles_per_page=840)
    np.testing.assert_array_equal(single.quotas(5),
                                  single.quotas(5, 0))


def test_pooled_source_rows_complete_and_unique():
    code = _pooled_fixture(k_meta=9_000, tpp=840, n=3)   # k_total=27000
    seen: list[int] = []
    page = 0
    while len(seen) < code.k_total:
        block_of, row_of = code.page_assignment(page)
        for local in range(code.symbols_per_page):
            b, r = int(block_of[local]), int(row_of[local])
            if r < code.k_per_block[b]:
                seen.append(code.block_offsets[b] + r)
        page += 1
        assert page < 64, "source rows must appear within the first pages"
    assert sorted(seen) == list(range(code.k_total))


def test_pooled_dead_plane_removes_exactly_the_stream_quota():
    """The deterministic plane tier's arithmetic on the real assignment."""
    code = _pooled_fixture(k_meta=30_000, tpp=1872, n=3)
    b = code.n_blocks
    floor_q = code.tiles_per_page // b
    dead = 2                                     # Y
    for page in range(3):
        block_of, _ = code.page_assignment(page)
        for blk in range(b):
            total = int((block_of == blk).sum())
            dead_count = int((block_of[dead::3] == blk).sum())
            np.testing.assert_array_equal(
                dead_count, code.quotas(page, dead)[blk])
            assert total - dead_count >= 2 * floor_q


GOLDEN_POOLED_C2_GEOMETRY = (
    "5585d90353d35b9402baba017290ebf129e8de4ba93e296f6ceafa9eb82a9de0")
GOLDEN_POOLED_C3_GEOMETRY = (
    "82fc1a44e5492e0ff5c825d2126c7022d0bdd00d743f420155e6f8ce0138cae2")


@pytest.mark.parametrize("tpp,golden", [
    (1872, GOLDEN_POOLED_C2_GEOMETRY),
    (840, GOLDEN_POOLED_C3_GEOMETRY),
])
def test_pooled_assignment_digest_frozen(tpp, golden):
    """Freeze the pooled assignment derivation per row geometry.

    Test seed, k_meta=20,000: covers multi-block, remainder rotation and
    both geometries. The row-seed goldens (compose GT) land with P3;
    this digest pins the DERIVATION itself.
    """
    code = fnt.VolumeCode(60_000, 8, SEED, tiles_per_page=tpp,
                          n_streams=3)
    digest = hashlib.sha256()
    for page in range(4):
        block_of, row_of = code.page_assignment(page)
        digest.update(np.asarray(block_of, dtype="<i4").tobytes())
        digest.update(np.asarray(row_of, dtype="<i8").tobytes())
    assert digest.hexdigest() == golden


def test_pooled_roundtrip_byte_exact_and_dead_plane_decode():
    """Small pooled end-to-end: full solve, then a Y-dead solve at
    q<=2/3-headroom (the close-level companion of the P5 gate)."""
    k_meta, tpp, n, s = 700, 210, 3, 16          # k_total=2100, B=1
    code = fnt.VolumeCode(n * k_meta, s, SEED, tiles_per_page=tpp,
                          n_streams=n)
    rng = np.random.default_rng(11)
    payload = rng.bytes(n * k_meta * s // 8)
    src = fnt.pack_source(payload, n * k_meta, s)
    n_pages = 6                                  # 3780 symbols total
    esis = np.arange(n_pages * tpp * n, dtype=np.int64)
    symbols = code.encode_symbols(src, esis)

    dec = fnt.Decoder(code)
    for esi in range(code.k_total + 40):         # any prefix with margin
        dec.add_symbol(int(esis[esi]), symbols[esi])
    out = dec.try_solve()
    assert out is not None
    np.testing.assert_array_equal(
        np.packbits(out.reshape(-1)), np.frombuffer(payload, np.uint8))

    dead = fnt.Decoder(code)
    for esi in esis:
        if int(esi) % n == 2:                    # Y erased everywhere
            continue
        dead.add_symbol(int(esi), symbols[int(esi)])
    out = dead.try_solve()
    assert out is not None, "dead plane must be survivable at this fill"
    np.testing.assert_array_equal(
        np.packbits(out.reshape(-1)), np.frombuffer(payload, np.uint8))


# --------------------------------------------- pooled capacity predicate

def test_pooled_capacity_three_tiers_truth_table():
    t, n = 840, 3
    # all three tiers pass (B=1: k+16 <= 12,600; 9,016 <= 5*3*840;
    # 9,016 <= 10*2*840)
    assert capacity.pooled_page_capacity_sufficient(
        9_000, t, 10, 0.5, n_streams=n)
    # plane tier binds ALONE: q=0.9, P=10, k=17,000 (B=2, largest+r=8,517;
    # page 9*3*420=11,340 ok; plane 10*2*420=8,400 < 8,517)
    assert not capacity.pooled_page_capacity_sufficient(
        17_000, t, 10, 0.9, n_streams=n)
    # ... and the SAME dial passes once pages inflate — which side of
    # that a caller wants is dial policy (gen.plan), not predicate
    # arithmetic.
    assert capacity.pooled_page_capacity_sufficient(
        17_000, t, 12, 0.9, n_streams=n)
    # global tier binds: 16,800+16 > floor(0.5*10*840*3) = 12,600
    assert not capacity.pooled_page_capacity_sufficient(
        16_800, t, 10, 0.5, n_streams=n)
    # vacuous K and stream-count validation
    assert capacity.pooled_page_capacity_sufficient(0, t, 1, 0.5, n_streams=n)
    with pytest.raises(ValueError):
        capacity.pooled_page_capacity_sufficient(100, t, 1, 0.5, n_streams=1)


def test_pooled_page_tier_uses_stream_exact_floor():
    """Tier 2 is the stream-exact strengthening L*n*(T//B), NOT the
    weaker naive L*floor(n*T/B) (design §2.2 scope note): T=100, B=8
    separates them (36 vs 37 per page), and this witness satisfies the
    naive bound while violating the exact one."""
    t, n, q, p = 100, 3, 0.6246, 650
    k = 119_848              # B=8, largest=14,981, r=19
    b = fnt.n_blocks_for(k)
    r = capacity.rank_reserve_for(b)
    largest = -(-k // b)
    kept = capacity.retained_pages(p, q)
    assert (b, largest + r, kept) == (8, 15_000, 406)
    assert largest + r <= kept * ((t * n) // b)     # naive bound holds
    assert largest + r > kept * (n * (t // b))      # exact bound violated
    assert k + b * r <= capacity.source_budget(p * t * n, q)   # tier 1 holds
    assert largest + r <= p * (n - 1) * (t // b)          # tier 3 holds
    assert not capacity.pooled_page_capacity_sufficient(
        k, t, p, q, n_streams=n)


def test_pooled_page_inflation_documents_policy_boundary():
    """Tier 3 grows with P, so ENFORCING it above the plane ceiling
    fills only ~(n-1)/n however many pages are inflated — which is why
    the planner drops it there and reports the tier absent instead
    (dial policy, gen.plan; ruling 2026-08-14), never predicate
    arithmetic."""
    t, n = 840, 3
    q = 0.9                                     # far above (n-1)/n
    k = capacity.pooled_max_k_for_pages(t, 40, q, n_streams=n)
    assert k > 0
    assert capacity.pooled_page_capacity_sufficient(k, t, 40, q, n_streams=n)
    # the enforced volume is really ~2/3 full, not q-full: k << q*total
    assert k <= (n - 1) * 40 * t
    # dropping the tier is what fills to the true dial
    assert capacity.pooled_max_k_for_pages(
        t, 40, q, n_streams=n, enforce_plane_tier=False) > (n - 1) * 40 * t


def test_pooled_max_k_multiple_of_streams_and_matches_predicate():
    t, n = 1872, 3
    for n_pages, q in ((1, 0.5), (3, 0.5), (7, 0.65), (12, 0.35)):
        k = capacity.pooled_max_k_for_pages(t, n_pages, q, n_streams=n)
        assert k % n == 0
        if k:
            assert capacity.pooled_page_capacity_sufficient(
                k, t, n_pages, q, n_streams=n)
            assert not capacity.pooled_page_capacity_sufficient(
                k + n, t, n_pages, q, n_streams=n)


def test_pooled_reserve_capacity_compute_parity_corners():
    """The corrected §2.3 parity record, pinned with documented numbers.

    B_pooled = ceil(3*k_meta/16384) is within {3B-2, 3B-1, 3B} of the
    -v0 total 3*B_v0; total reserve is pooled <= -v0 ALWAYS; the
    documented k_meta=16385 example reads 72 vs 114; every
    k_meta <= 5461 pools into ONE solve (vs three)."""
    for k_meta in (1, 918, 5461, 5462, 16_384, 16_385, 30_000, 60_000):
        b_v0 = fnt.n_blocks_for(k_meta)
        b_pooled = fnt.n_blocks_for(3 * k_meta)
        assert 3 * b_v0 - 2 <= b_pooled <= 3 * b_v0
        reserve_v0 = 3 * b_v0 * capacity.rank_reserve_for(b_v0, solves_per_block=3)
        reserve_pooled = b_pooled * capacity.rank_reserve_for(b_pooled)
        assert reserve_pooled <= reserve_v0
    assert fnt.n_blocks_for(3 * 5461) == 1          # one solve regime
    assert fnt.n_blocks_for(3 * 5462) == 2
    assert fnt.n_blocks_for(3 * 918) == 1           # e032's k_meta class
    k = 16_385
    assert (fnt.n_blocks_for(3 * k)
            * capacity.rank_reserve_for(fnt.n_blocks_for(3 * k))) == 72
    assert (3 * fnt.n_blocks_for(k)
            * capacity.rank_reserve_for(fnt.n_blocks_for(k), solves_per_block=3)
            ) == 114
    # capacity corner on the real c2 geometry at q=0.5 (documented in
    # the design note): pooled never beats 3x per-stream by more than
    # the reserve saving, and the corner deficit stays <= ~0.1%.
    t, n_pages, q = 1872, 12, 0.5
    v0_total = 3 * capacity.max_k_for_pages(t, n_pages, q, n_streams=3)
    pooled = capacity.pooled_max_k_for_pages(t, n_pages, q, n_streams=3)
    assert abs(pooled - v0_total) <= max(64, v0_total // 500)
