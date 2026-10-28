"""New color domains: reference parity, bijections, and frozen vectors."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo.core import keystream as prod
from holo.core import keystream_spec as ref


CMY7_SEED = b"holo/v1/c2-cmy7-p120-v0/3328x2304"
CMY8_SEED = b"holo/v1/c2-cmy8-p120-v0/3328x2304"

GOLDEN = {
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


def test_color_domain_and_stream_constants_equal_reference():
    names = (
        "DOMAIN_COLOR_DUST_ORDER",
        "DOMAIN_CMY7_INTERLEAVE",
        "DOMAIN_CMY7_DITHER",
        "DOMAIN_COLOR_CELL_ORDER",
        "DOMAIN_CMY8_DITHER",
        "DOMAIN_COLOR_FOUNTAIN_ROW",
        "DOMAIN_COLOR_BLOCK_ASSIGN",
        "COLOR_STREAM_MAIN",
        "COLOR_STREAM_C",
        "COLOR_STREAM_M",
        "COLOR_STREAM_Y",
    )
    assert tuple(getattr(prod, name) for name in names[:7]) == \
        tuple(range(9, 16))
    assert tuple(getattr(prod, name) for name in names[7:]) == \
        tuple(range(4))
    for name in names:
        assert getattr(prod, name) == getattr(ref, name)
    # The K domain surface remains frozen at 1..8.
    assert (
        prod.DOMAIN_PAYLOAD,
        prod.DOMAIN_PILOT_VALUES,
        prod.DOMAIN_FILLER_VALUES,
        prod.DOMAIN_PILOT_SITES,
        prod.DOMAIN_FILLER_SITES,
        prod.DOMAIN_SLOT_PERM,
        prod.DOMAIN_FOUNTAIN_ROW,
        prod.DOMAIN_BLOCK_ASSIGN,
    ) == tuple(range(1, 9))


def test_reference_matches_each_color_draw_form():
    tile = 123
    for index in (0, 1, 17, 10933):
        if index < 20:
            got = prod.keys64(
                CMY7_SEED, prod.DOMAIN_COLOR_DUST_ORDER, 0, tile, index, 0)
            assert int(got[0]) == ref.color_dust_order_key(
                CMY7_SEED, tile, index)
        got = prod.keys64(
            CMY7_SEED, prod.DOMAIN_CMY7_INTERLEAVE, 0, tile, index, 0)
        assert int(got[0]) == ref.cmy7_interleave_key(
            CMY7_SEED, tile, index)
        assert int(prod.bits(
            CMY7_SEED, prod.DOMAIN_CMY7_DITHER, 0, tile, index, 0)[0]) == \
            ref.cmy7_dither_bit(CMY7_SEED, tile, index)
        if index < 3976:
            got = prod.keys64(
                CMY7_SEED, prod.DOMAIN_COLOR_CELL_ORDER, 0, tile, index, 0)
            assert int(got[0]) == ref.color_cell_order_key(
                CMY7_SEED, tile, index)

    for stream, aux in (("C", 1), ("M", 2), ("Y", 3)):
        for index in (0, 1, 3975):
            assert int(prod.cmy8_dither_bits(
                CMY8_SEED, stream, tile, 3976)[index]) == \
                ref.cmy8_dither_bit(CMY8_SEED, aux, tile, index)

    for stream, aux in (("main", 0), ("C", 1), ("M", 2), ("Y", 3)):
        got = prod.color_fountain_rows_bits(
            CMY8_SEED, stream, 7, [5], 257)[0]
        for column in (0, 1, 127, 128, 256):
            assert int(got[column]) == ref.color_fountain_coeff_bit(
                CMY8_SEED, aux, 7, 5, column)
        keys = prod.color_block_assign_keys(
            CMY8_SEED, stream, 3, np.asarray([0, 1, 17]))
        for local_tile, key in zip((0, 1, 17), keys, strict=True):
            assert int(key) == ref.color_block_assign_key(
                CMY8_SEED, aux, 3, local_tile)


def test_permutations_are_exact_bijections_and_address_separated():
    cases = (
        (prod.color_dust_permutation, 20),
        (prod.cmy7_interleave_permutation, 10934),
        (prod.color_cell_permutation, 3976),
    )
    for function, size in cases:
        first = function(CMY7_SEED, 123)
        assert first.dtype == np.int64 and first.shape == (size,)
        assert np.array_equal(np.sort(first), np.arange(size))
        assert np.array_equal(first, function(CMY7_SEED, 123))
        assert not np.array_equal(first, function(CMY7_SEED, 124))
    assert prod.color_dust_permutation(CMY7_SEED, 123, 0).size == 0


def test_stream_dithers_and_fountain_draws_are_independent():
    dithers = tuple(
        prod.cmy8_dither_bits(CMY8_SEED, stream, 123)
        for stream in ("C", "M", "Y")
    )
    assert all(bits.shape == (3976,) and bits.dtype == np.uint8
               for bits in dithers)
    assert not np.array_equal(dithers[0], dithers[1])
    assert not np.array_equal(dithers[0], dithers[2])
    assert not np.array_equal(dithers[1], dithers[2])
    rows = tuple(
        prod.color_fountain_rows_bits(CMY8_SEED, stream, 7, [0, 5], 257)
        for stream in ("C", "M", "Y")
    )
    assert all(value.shape == (2, 257) for value in rows)
    assert not np.array_equal(rows[0], rows[1])
    assert not np.array_equal(rows[1], rows[2])


def test_color_keystream_golden_vectors():
    vectors = {
        "dust7": prod.color_dust_permutation(
            CMY7_SEED, 123).astype(">u2").tobytes(),
        "interleave7": prod.cmy7_interleave_permutation(
            CMY7_SEED, 123).astype(">u2").tobytes(),
        "dither7": np.packbits(
            prod.cmy7_dither_bits(CMY7_SEED, 123),
            bitorder="big").tobytes(),
        "cells7": prod.color_cell_permutation(
            CMY7_SEED, 123).astype(">u2").tobytes(),
        "fountain7": np.packbits(prod.color_fountain_rows_bits(
            CMY7_SEED, "main", 7, [0, 5, 99], 257),
            axis=None, bitorder="big").tobytes(),
        "assign7": prod.color_block_assign_keys(
            CMY7_SEED, "main", 3, np.arange(17)
        ).astype(">u8").tobytes(),
        "dither8C": np.packbits(
            prod.cmy8_dither_bits(CMY8_SEED, "C", 123),
            bitorder="big").tobytes(),
        "dither8M": np.packbits(
            prod.cmy8_dither_bits(CMY8_SEED, "M", 123),
            bitorder="big").tobytes(),
        "dither8Y": np.packbits(
            prod.cmy8_dither_bits(CMY8_SEED, "Y", 123),
            bitorder="big").tobytes(),
        "fountain8C": np.packbits(prod.color_fountain_rows_bits(
            CMY8_SEED, "C", 7, [0, 5, 99], 257),
            axis=None, bitorder="big").tobytes(),
        "assign8C": prod.color_block_assign_keys(
            CMY8_SEED, "C", 3, np.arange(17)
        ).astype(">u8").tobytes(),
    }
    assert {name: _sha(value) for name, value in vectors.items()} == GOLDEN


@pytest.mark.parametrize("function", [
    prod.color_dust_permutation,
    prod.cmy7_interleave_permutation,
    prod.cmy7_dither_bits,
    prod.color_cell_permutation,
])
def test_color_draws_refuse_negative_or_noninteger_sizes(function):
    with pytest.raises(ValueError, match=">= 0"):
        function(CMY7_SEED, 0, -1)
    with pytest.raises(TypeError, match="integer"):
        function(CMY7_SEED, 0, True)


def test_stream_helpers_refuse_unknown_or_wrong_streams():
    with pytest.raises(ValueError, match="known"):
        prod.cmy8_dither_bits(CMY8_SEED, "main-ish", 0)
    with pytest.raises(ValueError, match="1..3"):
        prod.cmy8_dither_bits(CMY8_SEED, "main", 0)
    with pytest.raises(ValueError, match="0..3"):
        prod.color_block_assign_keys(CMY8_SEED, 4, 0, [0])
    with pytest.raises(TypeError, match="stream ID"):
        prod.color_fountain_rows_bits(CMY8_SEED, None, 0, [0], 1)

