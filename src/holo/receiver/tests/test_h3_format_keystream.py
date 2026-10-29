from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from holo.receiver.format import keystream as ks

from holo.receiver.tests import _h3_support

GOLD_SEED = b"holo/v1/c2-r0550/3328x2304"
CMY7_SEED = b"holo/v1/c2-cmy7-p120-v0/3328x2304"
CMY8_SEED = b"holo/v1/c2-cmy8-p120-v0/3328x2304"

# hand-copied second copy of tests/holo/test_keystream.py::GOLDEN
K_GOLDEN = {
    "payload-256": "cf3943f45be5b668fb87799bafa71df2"
                   "bf858eb2fb06fb6df03498501069b78f",
    "pilot-values-100": "cfa8f309811d523137b3ff9805ae5d75"
                        "5b1ebf55017d67d0429de870f792cb4e",
    "slot-perm-16": "025219fdc0b082e73e389d8640b9b30c"
                    "79eff8bf48bc3963f92490cbe57a4b18",
    "block-assign-1872": "5f5da9ce386c164d2f106e4a2f02ecf"
                         "b8b521435e95962c46217498c6d3a62ec",
}

# hand-copied second copy of tests/holo/test_color_keystream.py::GOLDEN
COLOR_GOLDEN = {
    "dust7": "f454421b950594c4bad72de50a263054"
             "fb54e49166781f05091b3867e0f5572d",
    "interleave7": "c079b62c9111d9aa315a228eb008bf30"
                   "f0e40fc2bca2f15ca4732bb7f9bf9749",
    "dither7": "672f8829da7ad3d132bc53d18d24b9cd"
               "268c5c5a712203e096878bb22d114f70",
    "cells7": "8ef4ba2dd223d1429da125eb3a733dfa"
              "f9f6f905df5bac18a54eb4d75230fbf1",
    "fountain7": "ddfaf7eaf161dc3f4efc549e04ab3bf4"
                 "dd4e5b83eb4f80eba26dbcc88678740c",
    "assign7": "1d68dbee18ae61203c797e8af2ced258"
               "609edc265f521751593770ef33a656e5",
    "dither8C": "8b92725e1a94f62cb3d6be1b1c78bcf"
                "572bc357ba8d5b2a45d6a1692aa0019b2",
    "dither8M": "df52c7ed7fcd2758efd87046cccb2ed48"
                "ded83ae66b626e0825c62d74056311a",
    "dither8Y": "efb928e2ff61a100e3359fb5fe6c3cc2"
                "33a3ed41da52f1409d749ea734bf798a",
    "fountain8C": "d259036b559223df48ec539c5ccca67e6"
                  "a88cc459f6bb7ae683af55be44520d9",
    "assign8C": "47422e1901ba42c72d33cf440d1d06299"
                "81ae24c4c94a43552ae768f325a7399",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_domain_table_is_frozen_one_through_fifteen():
    _h3_support.assert_golden("K domains", (
        ks.DOMAIN_PAYLOAD, ks.DOMAIN_PILOT_VALUES, ks.DOMAIN_FILLER_VALUES,
        ks.DOMAIN_PILOT_SITES, ks.DOMAIN_FILLER_SITES, ks.DOMAIN_SLOT_PERM,
        ks.DOMAIN_FOUNTAIN_ROW, ks.DOMAIN_BLOCK_ASSIGN), tuple(range(1, 9)))
    _h3_support.assert_golden("colour domains", (
        ks.DOMAIN_COLOR_DUST_ORDER, ks.DOMAIN_CMY7_INTERLEAVE,
        ks.DOMAIN_CMY7_DITHER, ks.DOMAIN_COLOR_CELL_ORDER,
        ks.DOMAIN_CMY8_DITHER, ks.DOMAIN_COLOR_FOUNTAIN_ROW,
        ks.DOMAIN_COLOR_BLOCK_ASSIGN), tuple(range(9, 16)))
    assert ks.PLANE_K == 3
    _h3_support.assert_golden("stream aux", (
        ks.COLOR_STREAM_MAIN, ks.COLOR_STREAM_C, ks.COLOR_STREAM_M,
        ks.COLOR_STREAM_Y), (0, 1, 2, 3))
    _h3_support.assert_golden("COLOR_STREAM_AUX", dict(ks.COLOR_STREAM_AUX),
                              {"main": 0, "C": 1, "M": 2, "Y": 3})


@pytest.mark.parametrize("seed", [
    GOLD_SEED, CMY7_SEED, CMY8_SEED,
    b"holo/v2/c2-cmy8-r0700@53x37", b"holo/v1/sites/p100",
    b"holo/v1/sites/p120", b"",
])
def test_kdf_is_the_first_sixteen_bytes_of_a_prefixed_sha256(seed: bytes):
    key = ks.kdf(seed)
    assert key == hashlib.sha256(b"holo/v1|" + seed).digest()[:16]
    assert len(key) == 16


# frozen 2026-08-29: the derived AES-128 key of each shipped row seed
KDF_GOLDEN = {
    GOLD_SEED: "0654a714aeb3f2999349bf72d0d3f163",
    CMY7_SEED: "b50b01df7555293b69bc36bbcb615fef",
    CMY8_SEED: "4140e82ec433e0378047ae5531700cdc",
}


@pytest.mark.parametrize("seed", sorted(KDF_GOLDEN))
def test_kdf_anchor_for_the_golden_row_seed(seed: bytes):
    _h3_support.assert_golden(
        f"kdf({seed.decode()})", ks.kdf(seed).hex(), KDF_GOLDEN[seed])
    assert ks.kdf(seed).hex() == hashlib.sha256(
        b"holo/v1|" + seed).digest()[:16].hex()
    assert len(set(KDF_GOLDEN.values())) == len(KDF_GOLDEN)


@pytest.mark.parametrize("key_hex,plain_hex,cipher_hex", [
    ("000102030405060708090a0b0c0d0e0f",
     "00112233445566778899aabbccddeeff",
     "69c4e0d86a7b0430d8cdb78070b4c55a"),
    ("2b7e151628aed2a6abf7158809cf4f3c",
     "3243f6a8885a308d313198a2e0370734",
     "3925841d02dc09fbdc118597196a0b32"),
])
def test_fips_197_appendix_vectors_witness_the_primitive(
        key_hex: str, plain_hex: str, cipher_hex: str):
    encryptor = Cipher(algorithms.AES(bytes.fromhex(key_hex)),
                       modes.ECB()).encryptor()
    assert encryptor.update(bytes.fromhex(plain_hex)).hex() == cipher_hex


def test_blocks_is_aes128_ecb_of_the_counter_under_the_derived_key():
    major = np.array([0, 7, 1 << 23], dtype=np.int64)
    u = np.array([0, 4095, (1 << 32) - 1], dtype=np.int64)
    v = np.array([1, 2, 3], dtype=np.int64)
    counters = ks.counters(ks.DOMAIN_FOUNTAIN_ROW, 0, major, u, v)
    encryptor = Cipher(algorithms.AES(ks.kdf(GOLD_SEED)),
                       modes.ECB()).encryptor()
    expected = np.frombuffer(encryptor.update(counters.tobytes()),
                             dtype=np.uint8).reshape(-1, 16)
    got = ks.blocks(GOLD_SEED, ks.DOMAIN_FOUNTAIN_ROW, 0, major, u, v)
    assert np.array_equal(got, expected)
    assert np.array_equal(
        ks.bits(GOLD_SEED, ks.DOMAIN_FOUNTAIN_ROW, 0, major, u, v),
        expected[:, 0] >> 7)
    keys = ks.keys64(GOLD_SEED, ks.DOMAIN_FOUNTAIN_ROW, 0, major, u, v)
    assert keys.dtype == np.uint64
    assert [int(k) for k in keys] == [
        int.from_bytes(row[:8].tobytes(), "big") for row in expected]


def test_counter_block_layout_is_domain_aux_major3_u4_v4():
    block = ks.counters(7, 3, 0x0A0B0C, 0x01020304, 0xF0E0D0C0)
    assert block.shape == (1, 16)
    assert block.dtype == np.uint8
    _h3_support.assert_golden(
        "counter bytes", block[0].tobytes().hex(),
        "0703" "0a0b0c" "01020304" "f0e0d0c0" "000000")


def test_counters_broadcasts_scalars_against_arrays():
    got = ks.counters(1, 3, 2, np.arange(5), 0)
    assert got.shape == (5, 16)
    assert np.array_equal(got[:, 8], np.arange(5, dtype=np.uint8))
    assert set(np.unique(got[:, 0])) == {1}
    assert set(np.unique(got[:, 1])) == {3}


C7_REFUSALS = [
    ((1, 0, 1 << 24, 0, 0), "counter field major out of range"),
    ((1, 0, -1, 0, 0), "counter field major out of range"),
    ((1, 0, 0, 1 << 32, 0), "counter field u out of range"),
    ((1, 0, 0, -1, 0), "counter field u out of range"),
    ((1, 0, 0, 0, 1 << 32), "counter field v out of range"),
    ((1, 0, 0, 0, -1), "counter field v out of range"),
    ((300, 0, 0, 0, 0), "domain/aux out of range"),
    ((-1, 0, 0, 0, 0), "domain/aux out of range"),
    ((1, 256, 0, 0, 0), "domain/aux out of range"),
    ((1, -1, 0, 0, 0), "domain/aux out of range"),
]


@pytest.mark.parametrize("args,reason", C7_REFUSALS)
def test_c7_out_of_range_addresses_refuse_and_never_wrap(args: tuple,
                                                        reason: str):
    with pytest.raises(ValueError, match=reason):
        ks.counters(*args)
    with pytest.raises(ValueError, match=reason):
        ks.blocks(GOLD_SEED, *args)


def test_the_extreme_in_range_address_is_accepted():
    edge = ks.counters(255, 255, (1 << 24) - 1, (1 << 32) - 1,
                       (1 << 32) - 1)
    assert edge[0].tobytes().hex() == "ffff" + "ff" * 11 + "000000"


@pytest.mark.parametrize("name", sorted(K_GOLDEN))
def test_k_keystream_golden_vectors(name: str):
    if name == "payload-256":
        value = np.packbits(ks.bits(GOLD_SEED, ks.DOMAIN_PAYLOAD, 3, 0, 0,
                                    np.arange(256))).tobytes()
    elif name == "pilot-values-100":
        value = np.packbits(ks.bits(GOLD_SEED, ks.DOMAIN_PILOT_VALUES, 3, 0,
                                    np.arange(100), 0)).tobytes()
    elif name == "slot-perm-16":
        a, b = ks.slot_perm_params(GOLD_SEED, np.arange(16), 4096 - 100)
        value = a.tobytes() + b.tobytes()
    else:
        value = ks.keys64(GOLD_SEED, ks.DOMAIN_BLOCK_ASSIGN, 0, 139,
                          np.arange(1872), 0).astype(">u8").tobytes()
    _h3_support.assert_golden(name, _sha(value), K_GOLDEN[name])


def _color_vector(name: str) -> bytes:
    if name == "dust7":
        return ks.color_dust_permutation(CMY7_SEED, 123).astype(
            ">u2").tobytes()
    if name == "interleave7":
        return ks.cmy7_interleave_permutation(CMY7_SEED, 123).astype(
            ">u2").tobytes()
    if name == "dither7":
        return np.packbits(ks.cmy7_dither_bits(CMY7_SEED, 123),
                           bitorder="big").tobytes()
    if name == "cells7":
        return ks.color_cell_permutation(CMY7_SEED, 123).astype(
            ">u2").tobytes()
    if name == "fountain7":
        return np.packbits(ks.color_fountain_rows_bits(
            CMY7_SEED, "main", 7, [0, 5, 99], 257),
            axis=None, bitorder="big").tobytes()
    if name == "assign7":
        return ks.color_block_assign_keys(
            CMY7_SEED, "main", 3, np.arange(17)).astype(">u8").tobytes()
    if name.startswith("dither8"):
        return np.packbits(ks.cmy8_dither_bits(CMY8_SEED, name[-1], 123),
                           bitorder="big").tobytes()
    if name == "fountain8C":
        return np.packbits(ks.color_fountain_rows_bits(
            CMY8_SEED, "C", 7, [0, 5, 99], 257),
            axis=None, bitorder="big").tobytes()
    return ks.color_block_assign_keys(
        CMY8_SEED, "C", 3, np.arange(17)).astype(">u8").tobytes()


@pytest.mark.parametrize("name", sorted(COLOR_GOLDEN))
def test_colour_keystream_golden_vectors(name: str):
    _h3_support.assert_golden(name, _sha(_color_vector(name)),
                              COLOR_GOLDEN[name])


@pytest.mark.parametrize("stream,aux", [
    ("main", 0), ("C", 1), ("M", 2), ("Y", 3), (0, 0), (1, 1), (3, 3)])
def test_named_and_numeric_streams_address_the_same_aux(stream, aux: int):
    assert np.array_equal(
        ks.cmy8_dither_bits(CMY8_SEED, stream, 7, 64),
        ks.bits(CMY8_SEED, ks.DOMAIN_CMY8_DITHER, aux, 7,
                np.arange(64, dtype=np.int64), 0))
    assert np.array_equal(
        ks.color_fountain_rows_bits(CMY8_SEED, stream, 5, [7], 300),
        np.unpackbits(ks.blocks(
            CMY8_SEED, ks.DOMAIN_COLOR_FOUNTAIN_ROW, aux, 5,
            np.repeat(7, 3), np.arange(3)).reshape(1, 48),
            axis=1, bitorder="big")[:, :300])
    assert np.array_equal(
        ks.color_block_assign_keys(CMY8_SEED, stream, 3, [0, 1, 17]),
        ks.keys64(CMY8_SEED, ks.DOMAIN_COLOR_BLOCK_ASSIGN, aux, 3,
                  [0, 1, 17], 0))


def test_streams_are_independent_of_each_other():
    dithers = [ks.cmy8_dither_bits(CMY8_SEED, s, 123) for s in "CMY"]
    assert all(bits.shape == (3976,) and bits.dtype == np.uint8
               for bits in dithers)
    assert not np.array_equal(dithers[0], dithers[1])
    assert not np.array_equal(dithers[0], dithers[2])
    assert not np.array_equal(dithers[1], dithers[2])
    rows = [ks.color_fountain_rows_bits(CMY8_SEED, s, 7, [0, 5], 257)
            for s in "CMY"]
    assert all(value.shape == (2, 257) for value in rows)
    assert not np.array_equal(rows[0], rows[1])
    assert not np.array_equal(rows[1], rows[2])


@pytest.mark.parametrize("size", [0, 1, 5, 20])
def test_dust_permutation_is_an_exact_bijection(size: int):
    perm = ks.color_dust_permutation(CMY7_SEED, 261143, size)
    assert perm.dtype == np.int64 and perm.shape == (size,)
    assert np.array_equal(np.sort(perm), np.arange(size))


@pytest.mark.parametrize("function,size", [
    (ks.color_dust_permutation, 20),
    (ks.cmy7_interleave_permutation, 10934),
    (ks.color_cell_permutation, 3976),
])
def test_item_permutations_are_bijections_separated_by_tile_counter(
        function, size: int):
    first = function(CMY7_SEED, 123, size)
    assert np.array_equal(np.sort(first), np.arange(size))
    assert np.array_equal(first, function(CMY7_SEED, 123, size))
    assert not np.array_equal(first, function(CMY7_SEED, 124, size))


def test_payload_bits_is_the_row_major_bit_draw_over_the_cell_grid():
    plane_bits = ks.payload_bits(GOLD_SEED, ks.PLANE_K, 0, (3, 5))
    assert plane_bits.shape == (3, 5) and plane_bits.dtype == np.uint8
    yy = np.repeat(np.arange(3), 5)
    xx = np.tile(np.arange(5), 3)
    assert np.array_equal(
        plane_bits.reshape(-1),
        ks.bits(GOLD_SEED, ks.DOMAIN_PAYLOAD, ks.PLANE_K, 0, yy, xx))
    assert not np.array_equal(
        plane_bits, ks.payload_bits(GOLD_SEED, ks.PLANE_K, 1, (3, 5)))
    assert not np.array_equal(
        plane_bits, ks.payload_bits(GOLD_SEED, 0, 0, (3, 5)))


@pytest.mark.parametrize("n_cols", [1, 127, 128, 129, 4001])
def test_fountain_rows_bits_widths_come_from_whole_keystream_words(
        n_cols: int):
    rows = np.array([0, 3, 4095], dtype=np.int64)
    got = ks.fountain_rows_bits(GOLD_SEED, 63, rows, n_cols)
    assert got.shape == (3, n_cols) and got.dtype == np.uint8
    n_words = -(-n_cols // 128)
    blk = ks.blocks(GOLD_SEED, ks.DOMAIN_FOUNTAIN_ROW, 0, 63,
                    np.repeat(rows, n_words),
                    np.tile(np.arange(n_words), rows.size))
    expected = np.unpackbits(blk.reshape(3, n_words * 16), axis=1,
                             bitorder="big")[:, :n_cols]
    assert np.array_equal(got, expected)


@pytest.mark.parametrize("bound", [2, 6, 7, 49, 64, 100, 256])
def test_bounded_draws_are_in_range_and_deterministic(bound: int):
    us = np.array([0, 1, 42, 99, 100000], dtype=np.int64)
    got = ks.bounded_draws(GOLD_SEED, ks.DOMAIN_PILOT_SITES, us, bound)
    assert got.dtype == np.int64 and got.shape == us.shape
    assert int(got.min()) >= 0 and int(got.max()) < bound
    assert np.array_equal(
        got, ks.bounded_draws(GOLD_SEED, ks.DOMAIN_PILOT_SITES, us, bound))
    assert not np.array_equal(
        got, ks.bounded_draws(GOLD_SEED, ks.DOMAIN_FILLER_SITES, us, bound))


def test_bounded_draws_rejects_the_biased_tail_of_the_byte_range():
    bound = 7
    limit = 256 - (256 % bound)
    assert limit == 252
    us = np.arange(4096, dtype=np.int64)
    drawn = ks.bounded_draws(GOLD_SEED, ks.DOMAIN_PILOT_SITES, us, bound)
    first_bytes = ks.blocks(GOLD_SEED, ks.DOMAIN_PILOT_SITES, 0, 0, us,
                            0)[:, 0].astype(np.int64)
    accepted = first_bytes < limit
    assert np.array_equal(drawn[accepted], first_bytes[accepted] % bound)
    assert accepted.sum() < us.size


def test_bounded_draws_runaway_raises_at_the_declared_retry_cap(monkeypatch):
    calls: list[int] = []

    def all_ones(seed, domain, aux, major, u, v):
        u = np.asarray(u, dtype=np.int64).ravel()
        calls.append(int(u.size))
        return np.full((u.size, 16), 255, dtype=np.uint8)

    monkeypatch.setattr(ks, "blocks", all_ones)
    with pytest.raises(RuntimeError, match="bounded_draws rejection runaway"):
        ks.bounded_draws(GOLD_SEED, ks.DOMAIN_PILOT_SITES, [0, 1], 7)
    assert len(calls) == 65


def test_slot_perm_runaway_raises_at_the_declared_retry_cap(monkeypatch):
    calls: list[int] = []

    def all_ones(seed, domain, aux, major, u, v):
        u = np.asarray(u, dtype=np.int64).ravel()
        calls.append(int(u.size))
        return np.full((u.size, 16), 255, dtype=np.uint8)

    monkeypatch.setattr(ks, "blocks", all_ones)
    with pytest.raises(RuntimeError, match="slot_perm_params rejection "
                                           "runaway"):
        ks.slot_perm_params(GOLD_SEED, [0, 1], 3996)
    assert len(calls) == 65


@pytest.mark.parametrize("n_slots", [3996, 3976, 10, 2])
def test_slot_perm_params_are_coprime_and_generate_a_bijection(
        n_slots: int):
    counters = np.array([0, 1, 7, 1871, 261143], dtype=np.int64)
    a, b = ks.slot_perm_params(GOLD_SEED, counters, n_slots)
    assert a.dtype == np.int64 and b.dtype == np.int64
    assert a.shape == b.shape == counters.shape
    j = np.arange(n_slots, dtype=np.int64)
    for index in range(counters.size):
        assert math.gcd(int(a[index]), n_slots) == 1
        assert 0 <= int(b[index]) < n_slots
        mapped = (int(a[index]) * j + int(b[index])) % n_slots
        assert np.array_equal(np.sort(mapped), j)


def test_slot_perm_params_depend_on_the_tile_counter():
    a, b = ks.slot_perm_params(GOLD_SEED, np.arange(64), 3996)
    assert len({(int(x), int(y)) for x, y in zip(a, b)}) > 1
    other_a, other_b = ks.slot_perm_params(CMY8_SEED, np.arange(64), 3996)
    assert not (np.array_equal(a, other_a) and np.array_equal(b, other_b))
