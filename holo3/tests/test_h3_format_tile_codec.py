from __future__ import annotations

import hashlib
import math
import zlib

import numpy as np
import pytest

from holo3.format import identity, keystream, pilots, tile_codec as tc
from holo3.lib.ldpc import CODES, LLR_CLIP
from holo3.plugins import tiles

from holo3.tests import _h3_support

# hand-copied second copy of tests/holo/test_channel_mapper.py
CMY7_CODEBOOK_SHA256 = (
    "c39e6cc5fd9d4637202aedf2e40db4ad"
    "0487ee3acf493700cea1d175a4dcd229"
)

P100 = b"holo/v1/sites/p100"
P120 = b"holo/v1/sites/p120"
K_ROW_SEED = b"holo/v1/c3-r0550/2240x1536"
CMY7_BANK: tc.Bank = (("r0550", 0), ("r0625", 677), ("r0625", 677))
CMY8_BANK: tc.Bank = (("r0550", 120),)


def test_frozen_constants():
    assert tc.N_CELLS == 4096
    assert tc.CRC_BITS == 32
    assert tc.PLANE_ORDER == ("C", "M", "Y")
    assert tc.CMY7_BITS_PER_PACK == 11
    assert tc.CMY7_CELLS_PER_PACK == 4
    assert tc.CMY7_N_CANDIDATES == 2048
    assert tc.DEMAP_ITERATIONS == 3


def test_the_executed_bp_parameters_are_named_and_have_no_defaults():
    assert tiles.BP_ALPHA == 0.8
    assert tiles.BASELINE_BP_MAX_ITERS == 60
    assert tiles.RETRY_BP_MAX_ITERS == 150
    assert tiles.max_iters_for("scan") == 60
    assert tiles.max_iters_for("union") == 60
    assert tiles.max_iters_for("retry150") == 150
    with pytest.raises(TypeError):
        tc.decode_tile(np.zeros(4096), "r0550", np.arange(100), 1, 0)


def test_cmy7_codebook_golden_and_natural_radix_layout():
    book = tc.CMY7_CODEBOOK
    assert book.shape == (2048, 4) and book.dtype == np.uint8
    assert not book.flags.writeable
    _h3_support.assert_golden(
        "CMY7_CODEBOOK",
        hashlib.sha256(book.tobytes(order="C")).hexdigest(),
        CMY7_CODEBOOK_SHA256)
    for word in (0, 1, 6, 7, 342, 2047):
        digits = [(word // divisor) % 7 for divisor in (343, 49, 7, 1)]
        assert list(book[word]) == digits
    assert int(book.max()) == 6


def test_cmy8_state_plane_mapping_is_an_exhaustive_bijection():
    states = np.arange(8, dtype=np.uint8)
    planes = tc.states_to_planes(states)
    expected = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
                           [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]],
                          dtype=np.uint8)
    assert np.array_equal(planes, expected)
    assert np.array_equal(tc.planes_to_states(planes), states)
    grid = states.reshape(2, 4)
    assert tc.states_to_planes(grid).shape == (2, 4, 3)
    assert np.array_equal(
        tc.planes_to_states(tc.states_to_planes(grid)), grid)


def test_cmy7_map_is_the_codebook_lookup_of_an_msb_first_word():
    rng = np.random.default_rng(11)
    bits = rng.integers(0, 2, size=(7, 11)).astype(np.uint8)
    mapped = tc.cmy7_map(bits)
    assert mapped.shape == (7, 4) and mapped.dtype == np.uint8
    for index in range(7):
        word = int("".join(str(int(b)) for b in bits[index]), 2)
        assert list(mapped[index]) == list(tc.CMY7_CODEBOOK[word])


def test_crc32_bits_matches_the_standard_check_value():
    payload = np.unpackbits(np.frombuffer(b"123456789", dtype=np.uint8))
    crc = tc.crc32_bits(payload)
    assert crc.shape == (32,) and crc.dtype == np.uint8
    assert int("".join(str(int(b)) for b in crc), 2) == 0xCBF43926
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, size=2108).astype(np.uint8)
    expected = zlib.crc32(np.packbits(bits).tobytes()) & 0xFFFFFFFF
    assert int("".join(str(int(b)) for b in tc.crc32_bits(bits)), 2) \
        == expected


@pytest.mark.parametrize("rate_id,n_sites,capacity", [
    ("r0550", 100, 2108), ("r0547", 100, 2108), ("r0625", 100, 2428),
    ("r0700", 100, 2748), ("r0850", 120, 3368), ("r0550", 120, 2088),
])
def test_tile_capacity(rate_id: str, n_sites: int, capacity: int):
    assert tc.tile_capacity(rate_id, n_sites) == capacity
    assert capacity == CODES[rate_id].k_bits - 32 - n_sites


@pytest.mark.parametrize("rate_id,shorten", [
    ("r0550", 0), ("r0550", 100), ("r0550", 120), ("r0700", 100),
    ("r0625", 677),
])
def test_transmitted_positions_drop_the_shortened_information_tail(
        rate_id: str, shorten: int):
    code = CODES[rate_id]
    positions = tc.transmitted_positions(rate_id, shorten)
    assert positions.dtype == np.int64
    assert positions.size == code.n_bits - shorten
    assert np.all(np.diff(positions) > 0)
    dropped = set(range(code.n_bits)) - set(positions.tolist())
    assert dropped == set(range(code.k_bits - shorten, code.k_bits))


def _k_tile_params(n_tiles: int = 12):
    site_flat = pilots.site_cell_indices(P100, 0)
    slot_a, slot_b = keystream.slot_perm_params(
        K_ROW_SEED, np.arange(n_tiles, dtype=np.int64), 3996)
    return site_flat, slot_a, slot_b


def test_cell_map_is_the_keyed_permutation_of_the_non_site_cells():
    site_flat, slot_a, slot_b = _k_tile_params(2)
    nonsite = np.setdiff1d(np.arange(4096), site_flat)
    assert np.array_equal(tc.cell_map(site_flat, 1, 0), nonsite)
    first = tc.cell_map(site_flat, int(slot_a[0]), int(slot_b[0]))
    second = tc.cell_map(site_flat, int(slot_a[1]), int(slot_b[1]))
    assert np.array_equal(np.sort(first), nonsite)
    assert np.array_equal(np.sort(second), nonsite)
    assert not np.array_equal(first, second)
    assert math.gcd(int(slot_a[0]), nonsite.size) == 1


def test_cell_map_needs_a_coprime_multiplier_to_stay_a_bijection():
    site_flat, _a, _b = _k_tile_params(1)
    nonsite = np.setdiff1d(np.arange(4096), site_flat)
    assert nonsite.size == 3996 and nonsite.size % 2 == 0
    degenerate = tc.cell_map(site_flat, 2, 0)
    assert degenerate.size == 3996
    assert np.unique(degenerate).size == 1998
    assert not np.array_equal(np.sort(degenerate), nonsite)


def test_encode_tile_writes_only_non_site_cells():
    site_flat, slot_a, slot_b = _k_tile_params(1)
    rng = np.random.default_rng(5)
    user = rng.integers(0, 2, size=2108).astype(np.uint8)
    cells = tc.encode_tile(user, "r0550", site_flat, int(slot_a[0]),
                           int(slot_b[0]))
    assert cells.shape == (4096,) and cells.dtype == np.uint8
    assert not cells[site_flat].any()
    assert cells[np.setdiff1d(np.arange(4096), site_flat)].any()


def _clean_llr(cells: np.ndarray, magnitude: float = 4.0) -> np.ndarray:
    return (2.0 * cells.astype(np.float64) - 1.0) * magnitude


def test_tile_round_trip_is_clean_and_reports_its_gates():
    site_flat, slot_a, slot_b = _k_tile_params(1)
    rng = np.random.default_rng(6)
    user = rng.integers(0, 2, size=2108).astype(np.uint8)
    cells = tc.encode_tile(user, "r0550", site_flat, int(slot_a[0]),
                           int(slot_b[0]))
    ok, decoded, n_iters, syndrome_ok, crc_ok = tc.decode_tile(
        _clean_llr(cells), "r0550", site_flat, int(slot_a[0]),
        int(slot_b[0]), tiles.max_iters_for("scan"), tiles.BP_ALPHA)
    assert ok and syndrome_ok and crc_ok
    assert n_iters == 0
    assert np.array_equal(decoded, user)


def test_the_llr_sign_convention_is_positive_means_a_printed_one():
    site_flat, slot_a, slot_b = _k_tile_params(1)
    rng = np.random.default_rng(7)
    user = rng.integers(0, 2, size=2108).astype(np.uint8)
    cells = tc.encode_tile(user, "r0550", site_flat, int(slot_a[0]),
                           int(slot_b[0]))
    inverted = tc.decode_tile(
        -_clean_llr(cells), "r0550", site_flat, int(slot_a[0]),
        int(slot_b[0]), tiles.max_iters_for("scan"), tiles.BP_ALPHA)
    assert inverted[0] is False
    assert inverted[1] is None


# shape frozen from tests/holo/test_receive_tiles.py's r0550 cliff; the
# counts are re-measured under env314t (2026-08-29), never ported
R0550_CLIFF = {0.0: 12, 0.02: 12, 0.06: 12, 0.08: 8, 0.25: 0}


def test_the_r0550_cliff_is_monotone_with_zero_wrong_certificates():
    _h3_support.skip_unless_slow_lane("the 60-decode r0550 cliff ladder")
    site_flat, slot_a, slot_b = _k_tile_params(12)
    seeder = np.random.default_rng(20260829)
    users = [seeder.integers(0, 2, size=2108).astype(np.uint8)
             for _ in range(12)]
    cells = [tc.encode_tile(users[index], "r0550", site_flat,
                            int(slot_a[index]), int(slot_b[index]))
             for index in range(12)]
    yields: dict[float, int] = {}
    for fraction in (0.0, 0.02, 0.06, 0.08, 0.25):
        rng = np.random.default_rng(1234)
        certified = 0
        for index in range(12):
            llr = _clean_llr(cells[index])
            llr[rng.random(llr.shape) < fraction] *= -1.0
            ok, decoded, _iters, _syn, crc_ok = tc.decode_tile(
                llr, "r0550", site_flat, int(slot_a[index]),
                int(slot_b[index]), tiles.max_iters_for("scan"),
                tiles.BP_ALPHA)
            if not ok:
                assert decoded is None
                continue
            assert crc_ok
            certified += 1
            assert np.array_equal(decoded, users[index])
        yields[fraction] = certified
    _h3_support.assert_golden("r0550 cliff", yields, R0550_CLIFF)
    counts = [yields[f] for f in (0.0, 0.02, 0.06, 0.08, 0.25)]
    assert counts == sorted(counts, reverse=True)


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + float(np.log(np.exp(values - maximum).sum()))


def _demap_oracle(rel: np.ndarray,
                  prior: np.ndarray | None = None) -> np.ndarray:
    n_packs = rel.shape[0]
    out = np.zeros((n_packs, 11), dtype=np.float64)
    for pack in range(n_packs):
        metric = np.zeros(2048, dtype=np.float64)
        for word in range(2048):
            total = 0.0
            for cell in range(4):
                state = int(tc.CMY7_CODEBOOK[word, cell])
                total += 0.0 if state == 0 else float(rel[pack, cell,
                                                          state - 1])
            if prior is not None:
                for bit in range(11):
                    if (word >> (10 - bit)) & 1:
                        total += float(prior[pack, bit])
            metric[word] = total
        for bit in range(11):
            mask = ((np.arange(2048) >> (10 - bit)) & 1).astype(bool)
            out[pack, bit] = (_logsumexp(metric[mask])
                              - _logsumexp(metric[~mask]))
            if prior is not None:
                out[pack, bit] -= float(prior[pack, bit])
    return out


def test_cmy7_soft_demap_matches_a_brute_force_oracle():
    rng = np.random.default_rng(20260829)
    rel = rng.normal(0.0, 2.0, size=(3, 4, 6))
    got = tc.cmy7_soft_demap(rel)
    assert got.shape == (3, 11)
    assert np.allclose(got, _demap_oracle(rel), rtol=0, atol=1e-9)


def test_cmy7_soft_demap_with_a_prior_returns_extrinsic_only():
    rng = np.random.default_rng(4242)
    rel = rng.normal(0.0, 1.5, size=(2, 4, 6))
    prior = rng.normal(0.0, 1.0, size=(2, 11))
    got = tc.cmy7_soft_demap(rel, prior)
    assert np.allclose(got, _demap_oracle(rel, prior), rtol=0, atol=1e-9)
    assert not np.allclose(got, tc.cmy7_soft_demap(rel), atol=1e-6)


def test_all_equal_state_scores_are_an_exact_erasure():
    rel = np.zeros((2, 4, 6), dtype=np.float64)
    got = tc.cmy7_soft_demap(rel)
    assert np.array_equal(got, np.zeros((2, 11)))


def test_extreme_finite_scores_take_the_log_domain_fallback():
    rel = np.full((2, 4, 6), -400.0, dtype=np.float64)
    rel[1, 2, 3] = -1.0
    got = tc.cmy7_soft_demap(rel)
    assert np.all(np.isfinite(got))
    assert np.allclose(got, _demap_oracle(rel), rtol=0, atol=1e-6)
    naive_one = np.exp(np.full(1024, -1600.0))
    assert float(naive_one.sum()) == 0.0


def _cmy7_frame_inputs():
    seed = b"holo/v1/c2-cmy7-p120-v0/3328x2304"
    order = keystream.cmy7_interleave_permutation(seed, 17, 10934)
    dither = keystream.cmy7_dither_bits(seed, 17, 10934)
    return order, dither


def test_cmy7_encode_demap_round_trip_certifies_from_ideal_states():
    order, dither = _cmy7_frame_inputs()
    rng = np.random.default_rng(9)
    user = rng.integers(0, 2, size=5974).astype(np.uint8)
    states = tc.cmy7_encode_payload(user, CMY7_BANK, order, dither)
    assert states.shape == (3976,) and int(states.max()) <= 6
    scores = np.full((3976, 6), -12.0, dtype=np.float64)
    for cell in range(3976):
        state = int(states[cell])
        if state:
            scores[cell, state - 1] = 12.0
    observed = np.ones(3976, dtype=bool)
    llrs = tc.cmy7_demap_payload(scores, observed, CMY7_BANK, order, dither)
    assert llrs.shape == (10934,)
    ok, children, crc_invoked, crc_ok, decoded, _soft = tc.decode_frame(
        llrs, CMY7_BANK, tiles.max_iters_for("scan"), tiles.BP_ALPHA)
    assert ok and crc_invoked and crc_ok
    assert len(children) == 3
    assert all(syndrome_ok for _n_iters, syndrome_ok in children)
    assert np.array_equal(decoded, user)


def test_cmy7_unobserved_packs_contribute_zero_llr():
    order, dither = _cmy7_frame_inputs()
    rng = np.random.default_rng(10)
    user = rng.integers(0, 2, size=5974).astype(np.uint8)
    states = tc.cmy7_encode_payload(user, CMY7_BANK, order, dither)
    scores = np.zeros((3976, 6), dtype=np.float64)
    for cell in range(3976):
        state = int(states[cell])
        if state:
            scores[cell, state - 1] = 9.0
    observed = np.ones(3976, dtype=bool)
    observed[0] = False
    llrs = tc.cmy7_demap_payload(scores, observed, CMY7_BANK, order, dither)
    packs = llrs[order].reshape(994, 11)
    assert np.array_equal(packs[0], np.zeros(11))
    assert np.count_nonzero(packs[1:]) > 10000
    observed_all = tc.cmy7_demap_payload(
        scores, np.ones(3976, dtype=bool), CMY7_BANK, order, dither)
    assert np.count_nonzero(observed_all[order].reshape(994, 11)[0]) == 11
    assert np.array_equal(packs[1:], observed_all[order].reshape(994, 11)[1:])


def test_cmy7_iterated_decode_with_one_iteration_is_plain_decode_frame():
    order, dither = _cmy7_frame_inputs()
    rng = np.random.default_rng(12)
    user = rng.integers(0, 2, size=5974).astype(np.uint8)
    states = tc.cmy7_encode_payload(user, CMY7_BANK, order, dither)
    scores = np.full((3976, 6), -10.0, dtype=np.float64)
    for cell in range(3976):
        state = int(states[cell])
        if state:
            scores[cell, state - 1] = 10.0
    observed = np.ones(3976, dtype=bool)
    llrs = tc.cmy7_demap_payload(scores, observed, CMY7_BANK, order, dither)
    direct = tc.decode_frame(llrs, CMY7_BANK, 60, tiles.BP_ALPHA)
    once = tc.cmy7_iterated_decode(
        llrs, scores, observed, CMY7_BANK, order, dither, 60,
        tiles.BP_ALPHA, demap_iterations=1)
    assert once[0] == direct[0] is True
    assert once[1] == direct[1]
    assert np.array_equal(once[4], direct[4])
    three = tc.cmy7_iterated_decode(
        llrs, scores, observed, CMY7_BANK, order, dither, 60,
        tiles.BP_ALPHA, demap_iterations=tc.DEMAP_ITERATIONS)
    assert three[0] and np.array_equal(three[4], user)
    assert three[5] is None


def test_bank_arithmetic_matches_the_identity_stream_facts():
    row = identity.resolve_format_ref("L:c2-cmy7-p120-v0@3328x2304")
    assert row.streams[0].rung_children == CMY7_BANK
    assert tc.bank_user_bits(CMY7_BANK) == row.streams[0].user_bits == 5974
    assert tc.bank_transmitted_bits(CMY7_BANK) == 10934
    assert tc.bank_active_bits(CMY7_BANK) == 5974 + 32
    assert 10934 % tc.CMY7_BITS_PER_PACK == 0
    assert 10934 // tc.CMY7_BITS_PER_PACK * tc.CMY7_CELLS_PER_PACK == 3976
    cmy8 = identity.resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
    assert cmy8.streams[0].rung_children == CMY8_BANK
    assert tc.bank_user_bits(CMY8_BANK) == 2088
    assert tc.bank_transmitted_bits(CMY8_BANK) == 3976


def test_cmy8_presence_planes_round_trip_per_stream():
    seed = b"holo/v1/c2-cmy8-p120-v0/3328x2304"
    rng = np.random.default_rng(13)
    banks = (CMY8_BANK, CMY8_BANK, (("r0547", 120),))
    users = tuple(rng.integers(0, 2, size=2088).astype(np.uint8)
                  for _ in range(3))
    dithers = tuple(keystream.cmy8_dither_bits(seed, stream, 23, 3976)
                    for stream in ("C", "M", "Y"))
    states = tc.cmy8_encode_payload(users, banks, dithers)
    assert states.shape == (3976,) and int(states.max()) <= 7
    presence = tc.states_to_planes(states)
    for plane in range(3):
        llrs = (2.0 * presence[:, plane].astype(np.float64) - 1.0) * 8.0
        ok, _children, _invoked, crc_ok, decoded, _soft = \
            tc.cmy8_decode_stream(llrs, banks[plane], dithers[plane],
                                  tiles.max_iters_for("scan"),
                                  tiles.BP_ALPHA)
        assert ok and crc_ok
        assert np.array_equal(decoded, users[plane])


def test_cmy8_dither_is_undone_by_sign_flipping_not_by_bit_flipping():
    seed = b"holo/v1/c2-cmy8-p120-v0/3328x2304"
    rng = np.random.default_rng(14)
    user = rng.integers(0, 2, size=2088).astype(np.uint8)
    dither = keystream.cmy8_dither_bits(seed, "C", 23, 3976)
    assert int(dither.sum()) > 0
    frame = tc.encode_frame(user, CMY8_BANK)
    presence = frame ^ dither
    llrs = (2.0 * presence.astype(np.float64) - 1.0) * 8.0
    ok, _children, _invoked, _crc, decoded, _soft = tc.cmy8_decode_stream(
        llrs, CMY8_BANK, dither, 60, tiles.BP_ALPHA)
    assert ok and np.array_equal(decoded, user)
    wrong = tc.cmy8_decode_stream(llrs, CMY8_BANK,
                                  np.zeros_like(dither), 60, tiles.BP_ALPHA)
    assert wrong[0] is False and wrong[4] is None


def test_decode_frame_reports_a_child_syndrome_failure_before_the_crc():
    rng = np.random.default_rng(15)
    user = rng.integers(0, 2, size=2088).astype(np.uint8)
    frame = tc.encode_frame(user, CMY8_BANK)
    llrs = (2.0 * frame.astype(np.float64) - 1.0) * 8.0
    llrs[:400] *= -1.0
    ok, children, crc_invoked, crc_ok, decoded, _soft = tc.decode_frame(
        llrs, CMY8_BANK, 60, tiles.BP_ALPHA)
    assert not ok and not crc_invoked
    assert crc_ok is None and decoded is None
    assert children[0][1] is False


def test_llr_clip_is_the_declared_extrinsic_bound():
    assert LLR_CLIP == 20.0
