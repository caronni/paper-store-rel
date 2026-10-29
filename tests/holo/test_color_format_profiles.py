"""Frozen provisional color profiles, p120 furniture, and row identity."""
from __future__ import annotations

from collections import Counter
import hashlib
from types import MappingProxyType

import numpy as np
import pytest

from holo.core import channel, keystream
from holo.format import pilots
from holo.format.descriptor import CODINGS, get_coding
from holo.format.lattice import parse_format_id
# Frozen singletons are module-private (FORMAT-SPACE P1); the
# format-law pins reach them through the public catalog.
CMY7_P120_V0 = CODINGS["c2-cmy7-p120-v0"].codec
CMY8_P120_V0 = CODINGS["c2-cmy8-p120-v0"].codec
from holo.format.registry import (
    DEFAULT_DISCOVERY_ROW_IDS,
    FORMAT_ROWS,
    get_format_row,
    registered_format_rows,
)


COLOR_CODING_IDS = (
    "c2-cmy7-p120-v0",
    "c3-cmy7-p120-v0",
    "c2-cmy8-p120-v0",
    "c3-cmy8-p120-v0",
)

COLOR_ROW_IDS = (
    "c2-cmy7-p120-v0@3328x2304",
    "c3-cmy7-p120-v0@2240x1536",
    "c2-cmy8-p120-v0@3328x2304",
    "c3-cmy8-p120-v0@2240x1536",
)

P120_SITE_GOLDENS = {
    "word": "cf0d835ffed25402287d2066c71df537"
            "fe227630ced2fe53388eb17dc49f7e08",
    "dust": "cc6f32e5cdfb336e82b1cf0bc050b10"
            "d66dfdb7ff455bb7a81fd26ee7fe41aed",
    "payload": "361489054477d2df0300d1886f84946d"
               "d43ae080cac0f0941711b5ab1c624584",
}

ROW_VALUE_GOLDENS = {
    "c2-cmy7-p120-v0@3328x2304": (
        "9a8b7c9d8ff92a8cc5b141669f7831af"
        "4d3b5992b6b7bfd610431e5805648ba7",
        "f396f407fb9a04518014e839722f2868b"
        "ae99c764c968bb5a26a6d754fec2885",
    ),
    "c3-cmy7-p120-v0@2240x1536": (
        "ae44b7bd66dbee275789a3fa724f980e"
        "aa308836cc3042cbbd4d524a897be0da",
        "a45d2b909f4f4af45b4ef4665be1df33"
        "cc123a66ce29157d5580f230fa896cb1",
    ),
    "c2-cmy8-p120-v0@3328x2304": (
        "f4f109aa169b9190c1bdbb3892bdcab1"
        "5c20f20f70003c1202c22fde870550a8",
        "fdbf79ffee96249328ecf9eefe133559a"
        "fff6f1e813c54dfd597c2bad21d082e",
    ),
    "c3-cmy8-p120-v0@2240x1536": (
        "8399bdfc726020a0f732006a919e34b9"
        "0be98df8504bbe1b507828debab1035b",
        "cb416e9d935a4594f4fb9d267c8f943a"
        "8bfc95d6689ffb225f5fcee55886c122",
    ),
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_color_profiles_are_one_immutable_catalog_with_k_defaults():
    assert isinstance(CODINGS, MappingProxyType)
    assert isinstance(FORMAT_ROWS, MappingProxyType)
    assert DEFAULT_DISCOVERY_ROW_IDS == (
        "c2-r0550@3328x2304",
        "c2-r0700@3328x2304",
        "c3-r0550@2240x1536",
    )
    assert tuple(row.spec_id for row in registered_format_rows()) == \
        DEFAULT_DISCOVERY_ROW_IDS

    for coding_id, row_id in zip(
            COLOR_CODING_IDS, COLOR_ROW_IDS, strict=True):
        assert get_coding(coding_id) is CODINGS[coding_id]
        assert get_format_row(row_id).coding is CODINGS[coding_id]
        assert registered_format_rows((row_id,))[0].spec_id == row_id
    with pytest.raises(TypeError):
        CODINGS["new"] = CODINGS["c2-r0550"]  # type: ignore[index]


def test_c2_c3_share_codec_facts_but_not_physical_identity():
    cmy7_c2 = get_coding("c2-cmy7-p120-v0")
    cmy7_c3 = get_coding("c3-cmy7-p120-v0")
    cmy8_c2 = get_coding("c2-cmy8-p120-v0")
    cmy8_c3 = get_coding("c3-cmy8-p120-v0")

    assert cmy7_c2.codec is cmy7_c3.codec is CMY7_P120_V0
    assert cmy8_c2.codec is cmy8_c3.codec is CMY8_P120_V0
    assert cmy7_c2.cell_dots == cmy8_c2.cell_dots == 2
    assert cmy7_c3.cell_dots == cmy8_c3.cell_dots == 3
    assert get_format_row(COLOR_ROW_IDS[0]).seed != \
        get_format_row(COLOR_ROW_IDS[1]).seed
    assert all(get_coding(coding_id).family_seed == b"holo/v1/sites/p120"
               for coding_id in COLOR_CODING_IDS)


def test_profile_alphabets_streams_and_fec_arithmetic_are_exact():
    assert channel.STATE_NAMES == (
        "W", "C", "M", "CM", "Y", "CY", "MY", "CMY")
    assert CMY7_P120_V0.state_names == channel.STATE_NAMES[:7]
    assert CMY8_P120_V0.state_names == channel.STATE_NAMES
    assert CMY7_P120_V0.word_states == CMY8_P120_V0.word_states == (0, 3)
    assert CMY7_P120_V0.payload_cells == CMY8_P120_V0.payload_cells == 3976
    assert CMY7_P120_V0.evidence_values_per_cell == 6
    assert CMY8_P120_V0.evidence_values_per_cell == 3

    cmy7 = CMY7_P120_V0.streams
    assert CMY7_P120_V0.stream_ids == ("main",)
    assert cmy7[0].fountain_aux == keystream.COLOR_STREAM_MAIN
    assert tuple((child.code_id, child.shortened_info_tail)
                 for child in cmy7[0].fec.children) == (
        ("r0550", 0), ("r0625", 677), ("r0625", 677))
    assert tuple(child.active_information_bits
                 for child in cmy7[0].fec.children) == (2240, 1883, 1883)
    assert tuple(child.transmitted_bits
                 for child in cmy7[0].fec.children) == (4096, 3419, 3419)
    assert cmy7[0].fec.transmitted_bits == 10934
    assert cmy7[0].user_bits == 5974 and cmy7[0].symbol_bits == 5973

    cmy8 = CMY8_P120_V0.streams
    assert CMY8_P120_V0.stream_ids == ("C", "M", "Y")
    assert tuple(stream.fountain_aux for stream in cmy8) == (1, 2, 3)
    assert tuple(stream.fec.children[0].code_id for stream in cmy8) == (
        "r0550", "r0550", "r0547")
    assert all(stream.fec.children[0].shortened_info_tail == 120
               for stream in cmy8)
    assert all(stream.fec.transmitted_bits == 3976
               and stream.user_bits == 2088
               and stream.symbol_bits == 2087
               for stream in cmy8)


def test_p120_site_partition_and_golden_vectors():
    family = b"holo/v1/sites/p120"
    word, dust = pilots.color_site_cells_yx(family)
    payload = pilots.color_payload_cell_indices(family)
    word_flat = word[:, 0] * 64 + word[:, 1]
    dust_flat = dust[:, 0] * 64 + dust[:, 1]

    assert word.shape == (100, 2)
    assert dust.shape == (20, 2)
    assert payload.shape == (3976,)
    assert np.all(np.diff(dust_flat) > 0)
    assert np.unique(np.concatenate((word_flat, dust_flat, payload))).size \
        == 4096
    assert _sha(word.astype(">u2").tobytes()) == P120_SITE_GOLDENS["word"]
    assert _sha(dust.astype(">u2").tobytes()) == P120_SITE_GOLDENS["dust"]
    assert _sha(payload.astype(">u2").tobytes()) == \
        P120_SITE_GOLDENS["payload"]


def test_word_and_dust_value_vectors_and_quotas():
    counters = (0, 1, 2)
    for row_id in COLOR_ROW_IDS:
        row = get_format_row(row_id)
        words = pilots.color_word_states(
            row.seed, (0, 1, (1 << 18) - 1), row.codec)
        dust = pilots.dust_state_values(row.seed, counters, row.codec)
        word_golden, dust_golden = ROW_VALUE_GOLDENS[row_id]
        assert set(np.unique(words)) <= {0, 3}
        assert _sha(words.tobytes()) == word_golden
        assert _sha(dust.tobytes()) == dust_golden
        for counter, states in zip(
                (0, 1, (1 << 18) - 1), words, strict=True):
            assert pilots.decode_color_word(
                states, row.seed, row.codec) == counter

        if row.codec is CMY7_P120_V0:
            assert all(Counter(states) == Counter({
                1: 4, 2: 4, 4: 4, 5: 4, 6: 4,
            }) for states in dust)
            assert not np.any(dust == int(channel.CMYState.CMY))
        else:
            missing = (1, 2, 4, 5, 6, 7)
            for counter, states in zip(counters, dust, strict=True):
                counts = Counter(states)
                assert all(counts[state] >= 3 for state in missing)
                assert counts[missing[(2 * counter) % 6]] >= 4
                assert counts[missing[(2 * counter + 1) % 6]] >= 4
                assert sum(counts.values()) == 20


def test_color_dust_refuses_nonphysical_counters():
    row = get_format_row(COLOR_ROW_IDS[0])
    for counter in (-1, 1 << 18):
        with pytest.raises(ValueError, match="counter out of range"):
            pilots.dust_state_values(row.seed, [counter], row.codec)


def test_registered_words_cross_reject_every_wrong_row():
    """Pairwise row scrambling rejects this frozen 64-counter battery."""
    rows = tuple(FORMAT_ROWS.values())
    counters = np.arange(64, dtype=np.int64)
    for source in rows:
        values = pilots.word_values(source.seed, counters, source.plane)
        assert all(
            pilots.decode_word(value, source.seed, source.plane) == counter
            for counter, value in zip(counters, values, strict=True)
        )
        for target in rows:
            if target is source:
                continue
            assert all(
                pilots.decode_word(value, target.seed, target.plane) is None
                for value in values
            ), f"{source.spec_id} was accepted as {target.spec_id}"


# ------------------------------------------------------------------ cmy

#: sha256 of the word states at counters (0, 1, 2**18 - 1) and of the
#: dust states at (0, 1, 2) — the cmy counterpart of ROW_VALUE_GOLDENS:
#: word '1' C, word '0' the domain-9-keyed W or Y, dust the per-tile
#: balance law (docs/CMY-DESIGN.md §2.5, R3 as amended, R10).
CMY_ROW_VALUE_GOLDENS = {
    "c3-cmy-r0850@35x24": (
        "ce0f256dca8ad132d19c2fe7a7ccdc81"
        "73fe815d9359dd62e8ebb966eca41847",
        "9dc50ad3885377d16be97d29983cf6bd"
        "b5396cea86d0b905903d40627ee3aa93",
    ),
    "c2-cmy-r0775x0700@53x37": (
        "2b1f93d2642af5abe20de93f1a320946"
        "85b99e7b820a684354a54f58796e2de6",
        "94f29c3074c69b0812d4f868130ce59d"
        "d444f40e08073761f80473a4f8184e34",
    ),
    "c2-cmy-r0700-p300@10x10": (
        "6500c91f7479a8ae36e8d3c3251a693a"
        "367e65f9eedcad030b2cdccefa14679a",
        "5d7623b7c43f484fd80bf10b5942335d"
        "c01079e1e08c6160776e3d3012f53f69",
    ),
}
W, C, M, Y = (int(channel.CMYState[name]) for name in "WCMY")


@pytest.mark.parametrize("row_id", sorted(CMY_ROW_VALUE_GOLDENS))
def test_cmy_word_and_dust_value_vectors(row_id):
    spec = parse_format_id(row_id)
    words = pilots.color_word_states(
        spec.seed, (0, 1, (1 << 18) - 1), spec.codec)
    dust = pilots.dust_state_values(spec.seed, (0, 1, 2), spec.codec)
    assert (_sha(words.tobytes()), _sha(dust.tobytes())) == \
        CMY_ROW_VALUE_GOLDENS[row_id]
    assert set(np.unique(words)) <= {W, C, Y}
    assert set(np.unique(dust)) <= {W, C, M, Y}
    assert dust.shape == (3, spec.n_dust)


def test_cmy_words_round_trip_and_survive_a_dead_y_but_not_a_dead_c():
    spec = parse_format_id("c2-cmy-r0775x0700@53x37")
    counters = np.arange(64)
    words = pilots.color_word_states(spec.seed, counters, spec.codec)
    values = pilots.word_values(spec.seed, counters)
    assert np.array_equal(words == C, values == 1)
    dead_y = np.where(words == Y, W, words).astype(np.uint8)
    dead_c = np.where(words == C, W, words).astype(np.uint8)
    for counter in counters:
        for states in (words, dead_y):
            assert pilots.decode_color_word(
                states[counter], spec.seed, spec.codec) == counter
        assert pilots.decode_color_word(
            dead_c[counter], spec.seed, spec.codec) is None
    magenta = words[5].copy()
    magenta[np.flatnonzero(magenta == W)[0]] = M
    assert pilots.decode_color_word(magenta, spec.seed, spec.codec) is None


def test_cmy_word_keys_start_at_the_rows_own_dust_count():
    for row_id, n_dust in (("c2-cmy-r0700-p101@10x10", 1),
                           ("c2-cmy-r0700@10x10", 20)):
        spec = parse_format_id(row_id)
        assert spec.n_dust == n_dust
        for counter in (0, 7, 99):
            words = pilots.color_word_states(
                spec.seed, [counter], spec.codec)[0]
            zero = pilots.word_values(spec.seed, [counter])[0] == 0
            for keyed_at, expect in ((n_dust, True), (21 - n_dust, False)):
                yellow = keystream.color_word_zero_mask(
                    spec.seed, counter, keyed_at)
                assert np.array_equal(words == Y, zero & yellow) is expect


def _supply(n_c: int, n_w: int, n_y: int) -> np.ndarray:
    return np.asarray([C] * n_c + [W] * n_w + [Y] * n_y, dtype=np.uint8)


# The balance law on hand-built word supplies (design §2.5, R3): each dust
# site to the lowest running total, ties M, Y, W, C.  The expected supply
# (C 50, W 25, Y 25) gives R3's p120/p150/p200/p300 multisets; the probe
# row's Y-poorest tile (Y 12) splits M 16 / Y 4 (running totals 16 : 16).
@pytest.mark.parametrize("supply,n_dust,fill,multiset", [
    ((50, 25, 25), 20, [M] * 20, {M: 20}),
    ((50, 38, 12), 20, [M] * 12 + [M, Y] * 4, {M: 16, Y: 4}),
    ((50, 15, 35), 20, [M] * 15 + [M, W] * 2 + [M], {M: 18, W: 2}),
    ((50, 25, 25), 50, [M] * 25 + [M, Y, W] * 8 + [M],
     {M: 34, Y: 8, W: 8}),
    ((50, 25, 25), 100, None, {M: 50, Y: 25, W: 25}),
    ((50, 25, 25), 200, None, {M: 75, Y: 50, W: 50, C: 25}),
])
def test_cmy_dust_balances_the_tiles_word_supply(supply, n_dust, fill,
                                                 multiset):
    got = pilots._balance_dust(_supply(*supply), n_dust)
    assert got.dtype == np.uint8 and got.shape == (n_dust,)
    if fill is not None:
        assert got.tolist() == fill
    assert dict(Counter(got.tolist())) == multiset


def test_the_probe_rows_furniture_record():
    """c2-cmy-r0775x0700@53x37, page 0, measured 2026-10-11 over the
    format law: the per-tile word '0' count, its Y and W shares, and how
    many tiles keep twenty M against the split ones."""
    spec = parse_format_id("c2-cmy-r0775x0700@53x37")
    counters = np.arange(spec.tiles_per_page)
    words = pilots.color_word_states(spec.seed, counters, spec.codec)
    dust = pilots.dust_state_values(spec.seed, counters, spec.codec)
    n_zero, n_y, n_w = ((words != C).sum(1), (words == Y).sum(1),
                        (words == W).sum(1))
    assert (n_zero.min(), n_zero.max()) == (36, 65)
    assert (n_y.min(), n_y.max(), n_w.min(), n_w.max()) == (12, 40, 14, 39)
    shapes = Counter(tuple(sorted(Counter(tile.tolist()).items()))
                     for tile in dust)
    assert shapes == {
        ((M, 20),): 1772,
        ((M, 19), (Y, 1)): 84, ((W, 1), (M, 19)): 52,
        ((M, 18), (Y, 2)): 26, ((W, 2), (M, 18)): 19,
        ((M, 17), (Y, 3)): 3, ((W, 3), (M, 17)): 3,
        ((M, 16), (Y, 4)): 2,
    }
    poorest = int(np.argmin(n_y))
    assert Counter(dust[poorest].tolist()) == {M: 16, Y: 4}


def test_cmy_codec_refuses_a_dust_cycle() -> None:
    """cmy dust is the per-tile balance law (design §2.5, R3 as amended): a cycle would be silently ignored."""
    from dataclasses import replace
    from holo.format.families import cmy_codec
    with pytest.raises(ValueError, match="balance law"):
        replace(cmy_codec(("r0700", "r0700")), dust_base_cycle=(2, 4))
