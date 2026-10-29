"""Color generator composition from symbols to canonical device planes."""
from __future__ import annotations

from dataclasses import replace
import hashlib

import numpy as np
import pytest

from holo.core import channel, color_tile, keystream
from holo.format import metadata, pilots
from holo.format.lattice import parse_format_id
from holo.format.registry import get_format_row
from holo.gen.color_compose import (
    _color_geometry,
    color_cells_to_dot_planes,
    compose_color_tile,
)


COLOR_ROWS = (
    "c2-cmy7-p120-v0@3328x2304",
    "c3-cmy7-p120-v0@2240x1536",
    "c2-cmy8-p120-v0@3328x2304",
    "c3-cmy8-p120-v0@2240x1536",
)


def _symbols(spec, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    return {
        stream.stream_id: rng.integers(
            0, 2, stream.symbol_bits, dtype=np.uint8)
        for stream in spec.stream_profiles
    }


def _sequential_payload(spec, counter: int, tile: np.ndarray) -> np.ndarray:
    payload_cells = pilots.color_payload_cell_indices(spec.family_seed)
    placed = tile.reshape(-1)[payload_cells]
    order = keystream.color_cell_permutation(
        spec.seed, counter, spec.payload_cells)
    sequential = np.empty_like(placed)
    sequential[order] = placed
    return sequential


def _relative_scores(states: np.ndarray, n_states: int) -> np.ndarray:
    scores = np.full((states.size, n_states - 1), -24.0)
    nonwhite = states != 0
    scores[np.flatnonzero(nonwhite), states[nonwhite] - 1] = 24.0
    return scores


@pytest.mark.parametrize("row_id", COLOR_ROWS)
def test_color_tile_furniture_partition_and_projection(row_id: str):
    spec = get_format_row(row_id)
    counter = 137
    tile = compose_color_tile(
        spec, counter, _symbols(spec, 11), k_total=321)
    assert tile.shape == (64, 64) and tile.dtype == np.uint8
    assert int(tile.max()) < len(spec.codec.state_names)

    word, dust = pilots.color_site_cells_yx(spec.family_seed)
    assert np.array_equal(
        tile[word[:, 0], word[:, 1]],
        pilots.color_word_states(spec.seed, [counter], spec.codec)[0],
    )
    assert np.array_equal(
        tile[dust[:, 0], dust[:, 1]],
        pilots.dust_state_values(spec.seed, [counter], spec.codec)[0],
    )
    payload = pilots.color_payload_cell_indices(spec.family_seed)
    furniture = np.concatenate((
        word[:, 0] * 64 + word[:, 1],
        dust[:, 0] * 64 + dust[:, 1],
    ))
    assert np.unique(np.concatenate((furniture, payload))).size == 4096

    dots = color_cells_to_dot_planes(tile, spec.cell_dots)
    assert dots.shape == (
        64 * spec.cell_dots, 64 * spec.cell_dots, 3)
    assert np.array_equal(
        dots[::spec.cell_dots, ::spec.cell_dots],
        channel.states_to_planes(tile),
    )
    for dy in range(spec.cell_dots):
        for dx in range(spec.cell_dots):
            assert np.array_equal(
                dots[dy::spec.cell_dots, dx::spec.cell_dots],
                channel.states_to_planes(tile),
            )


#: The furniture density axis on the WRITER side.  ``p`` is the number of
#: site cells a tile spends on furniture — 100 indexed word sites plus
#: ``p - 100`` dust — so the payload is the remaining ``4096 - p`` cells.
#: p120 is the printed case and the only one the old `_color_geometry`
#: could compose: it called ``pilots.color_payload_cell_indices`` /
#: ``color_site_cells_yx``, which hardcode 20 dust, so every other lawful
#: p died in `compose_color_page_cells` with a shape mismatch between the
#: states the codec produced (4096 - p) and the 3,976 cells the helper
#: offered.  cmy8 admits p in [101, 2206]; these are p101 (a single dust
#: cell — the floor), p120, p172 and p300, plus one uneven rung triplet
#: to show the column-group pool re-partitions under a new p.
P_AXIS_ROWS = (
    "c2-cmy8-r0550-p101@10x10",
    "c2-cmy8-r0550@10x10",                    # p120, the printed density
    "c2-cmy8-r0550-p172@10x10",
    "c2-cmy8-r0550-p300@10x10",
    "c2-cmy8-r0700x0700x0547-p300@10x10",     # uneven triplet x p300
)


@pytest.mark.parametrize("format_id", P_AXIS_ROWS)
def test_color_geometry_partitions_the_tile_at_any_furniture_density(
    format_id: str,
):
    """The writer's furniture comes from the row, not from a constant.

    `_color_geometry` hardcoded 20 dust until 2026-09-16, so every
    density but the printed p120 died in `compose_color_page_cells` with
    a shape mismatch.  This pins the partition itself — word sites,
    dust, payload — against what the row declares, then composes a tile
    through the public path to show the furniture lands where the
    partition says it does.
    """
    spec = parse_format_id(format_id)
    payload_cells, word_flat, dust_flat = _color_geometry(spec)

    assert word_flat.size == pilots.N_WORD_SITES == 100
    assert dust_flat.size == spec.n_dust
    assert payload_cells.size == spec.payload_cells == 4096 - 100 - spec.n_dust
    everything = np.concatenate((word_flat, dust_flat, payload_cells))
    assert np.array_equal(np.sort(everything), np.arange(4096))

    word, dust = (pilots.word_site_cells_yx(spec.family_seed),
                  pilots.dust_site_cells_yx(spec.family_seed, spec.n_dust))
    assert np.array_equal(word_flat, word[:, 0] * 64 + word[:, 1])
    assert np.array_equal(dust_flat, dust[:, 0] * 64 + dust[:, 1])

    counter = 137
    tile = compose_color_tile(
        spec, counter, _symbols(spec, 11), k_total=321)
    assert np.array_equal(
        tile[word[:, 0], word[:, 1]],
        pilots.color_word_states(spec.seed, [counter], spec.codec)[0])
    assert np.array_equal(
        tile[dust[:, 0], dust[:, 1]],
        pilots.dust_state_values(spec.seed, [counter], spec.codec)[0])


@pytest.mark.parametrize("row_id", COLOR_ROWS[:2])
def test_cmy7_composed_tile_decodes_to_exact_user_frame(row_id: str):
    spec = get_format_row(row_id)
    counter, k_total = 91, 987
    symbols = _symbols(spec, 23)
    tile = compose_color_tile(spec, counter, symbols, k_total)
    sequential = _sequential_payload(spec, counter, tile)
    assert not np.any(sequential == int(channel.CMYState.CMY))

    bank = spec.stream_profiles[0].fec
    outcome = color_tile.cmy7_decode_payload(
        _relative_scores(sequential, 7),
        np.ones(spec.payload_cells, dtype=np.uint8),
        bank,
        keystream.cmy7_interleave_permutation(
            spec.seed, counter, bank.transmitted_bits),
        keystream.cmy7_dither_bits(
            spec.seed, counter, bank.transmitted_bits),
    )
    expected = np.concatenate((
        np.asarray([
            metadata.tile_bit(
                metadata.encode_metadata(0, k_total), counter)
        ], dtype=np.uint8),
        symbols["main"],
    ))
    assert outcome.ok
    assert np.array_equal(outcome.certified_user_bits, expected)


@pytest.mark.parametrize("row_id", COLOR_ROWS[2:])
def test_cmy8_composed_tile_decodes_each_stream_independently(row_id: str):
    spec = get_format_row(row_id)
    counter, k_total = 91, 987
    symbols = _symbols(spec, 29)
    tile = compose_color_tile(spec, counter, symbols, k_total)
    sequential = _sequential_payload(spec, counter, tile)
    presence = channel.cmy8_inverse(sequential)
    llrs = {
        stream_id: np.where(presence[:, plane], 24.0, -24.0)
        for plane, stream_id in enumerate(channel.PLANE_ORDER)
    }
    dithers = {
        stream.stream_id: keystream.cmy8_dither_bits(
            spec.seed, stream.stream_id, counter,
            stream.fec.transmitted_bits,
        )
        for stream in spec.stream_profiles
    }
    banks = {
        stream.stream_id: stream.fec for stream in spec.stream_profiles
    }
    outcomes = color_tile.cmy8_decode_payload(
        llrs, banks, dithers)
    meta = metadata.tile_bit(
        metadata.encode_metadata(0, k_total), counter)
    for stream in spec.stream_profiles:
        outcome = outcomes[stream.stream_id]
        expected = np.concatenate((
            np.asarray([meta], dtype=np.uint8),
            symbols[stream.stream_id],
        ))
        assert outcome.ok
        assert np.array_equal(outcome.certified_user_bits, expected)


def test_color_tile_vectors_are_deterministic_and_row_separated():
    digests = []
    for row_id in COLOR_ROWS:
        spec = get_format_row(row_id)
        tile = compose_color_tile(
            spec, 17, _symbols(spec, 71), k_total=333)
        digests.append(hashlib.sha256(tile.tobytes()).hexdigest())
    assert len(set(digests)) == len(COLOR_ROWS)
    assert digests == [
        # Frozen after independent furniture/codec decode checks above.
        "a706940c23fa77bd910edd68240f7b9e"
        "628abeb4a4a7e4ecfdcb9b05c1d42b83",
        "9d7bb74ea92f5ea5d7729a7ea5f349b"
        "69ad1cec046a2b67753f6ae2ef81413d0",
        "6acad6f753d582d59b05d3719348a3c4"
        "7510652b26dfebb3c59204c412abcaec",
        "512a9bb866d4f5c8dc0584e56eb9ff23"
        "4808cceab3f7353c80bd6bab04520943",
    ]


def test_color_composer_refuses_k_and_wrong_stream_shapes():
    k = get_format_row("c3-r0550@2240x1536")
    with pytest.raises(ValueError, match="not a provisional color codec"):
        compose_color_tile(
            k, 0, {"main": np.zeros(k.symbol_bits, dtype=np.uint8)}, 1)

    cmy8 = get_format_row("c3-cmy8-p120-v0@2240x1536")
    symbols = _symbols(cmy8, 31)
    symbols.pop("Y")
    with pytest.raises(ValueError, match="needs streams"):
        compose_color_tile(cmy8, 0, symbols, 1)


@pytest.mark.parametrize("row_id", (COLOR_ROWS[0], COLOR_ROWS[2]))
def test_color_composer_dispatches_value_equal_codec_by_stable_id(
    row_id: str,
) -> None:
    canonical = get_format_row(row_id)
    copied_codec = replace(canonical.codec)
    assert copied_codec == canonical.codec
    assert copied_codec is not canonical.codec
    copied = replace(
        canonical, coding=replace(canonical.coding, codec=copied_codec))
    symbols = _symbols(canonical, 41)

    expected = compose_color_tile(canonical, 19, symbols, k_total=7)
    actual = compose_color_tile(copied, 19, symbols, k_total=7)

    np.testing.assert_array_equal(actual, expected)
