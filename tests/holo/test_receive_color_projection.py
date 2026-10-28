"""Differential tests for certified color component projection."""
from __future__ import annotations

import dataclasses
import itertools

import numpy as np
import pytest

from holo.core import channel
from holo.format import metadata, pilots
from holo.format.registry import get_format_row
from holo.gen.color_compose import compose_color_tile
from holo.receive.color_projection import project_certified_color_tile
from holo.receive.records import certificate_record_from_user_bits


CMY7_ROWS = (
    "c2-cmy7-p120-v0@3328x2304",
    "c3-cmy7-p120-v0@2240x1536",
)
CMY8_ROWS = (
    "c2-cmy8-p120-v0@3328x2304",
    "c3-cmy8-p120-v0@2240x1536",
)


def _fixture(spec, address=(0, 1, 2), seed=741):
    counter = spec.tile_counter(*address)
    rng = np.random.default_rng(seed)
    symbols = {
        profile.stream_id: rng.integers(
            0, 2, profile.symbol_bits, dtype=np.uint8)
        for profile in spec.stream_profiles
    }
    k_total = 837
    metadata_bit = metadata.tile_bit(
        metadata.encode_metadata(0, k_total), counter)
    records = {
        profile.stream_id: certificate_record_from_user_bits(
            spec,
            page=address[0],
            tile_yx=address[1:],
            stream_id=profile.stream_id,
            user_bits=np.concatenate((
                np.asarray([metadata_bit], dtype=np.uint8),
                symbols[profile.stream_id],
            )),
            origin_attempt_id=f"synthetic-{profile.stream_id}",
        )
        for profile in spec.stream_profiles
    }
    tile = compose_color_tile(
        spec, counter, symbols, k_total=k_total)
    return records, channel.states_to_planes(tile)


def _furniture_mask(spec):
    word, dust = pilots.color_site_cells_yx(spec.family_seed)
    mask = np.zeros((64, 64, 3), dtype=np.bool_)
    mask[word[:, 0], word[:, 1]] = True
    mask[dust[:, 0], dust[:, 1]] = True
    return mask


@pytest.mark.parametrize("row_id", CMY7_ROWS)
def test_cmy7_certificate_reconstructs_complete_generator_tile(row_id):
    spec = get_format_row(row_id)
    records, expected = _fixture(spec)
    record = records["main"]

    projection = project_certified_color_tile(
        (record,), spec, (0, 1, 2))

    assert np.array_equal(projection.component_bits, expected)
    assert projection.known_mask.all()
    assert projection.dependency_certificate_ids == (
        record.certificate_id,)
    assert not projection.component_bits.flags.writeable
    assert not projection.known_mask.flags.writeable


@pytest.mark.parametrize("row_id", CMY8_ROWS)
@pytest.mark.parametrize(
    "subset",
    tuple(
        tuple(stream for stream, enabled in zip(
            ("C", "M", "Y"), selection, strict=True) if enabled)
        for selection in itertools.product((False, True), repeat=3)
    ),
)
def test_cmy8_every_certificate_subset_knows_only_owned_payload_components(
    row_id, subset,
):
    spec = get_format_row(row_id)
    records, expected = _fixture(spec)
    selected = tuple(records[stream] for stream in subset)

    projection = project_certified_color_tile(
        reversed(selected), spec, (0, 1, 2))

    expected_mask = _furniture_mask(spec)
    payload = pilots.color_payload_cell_indices(spec.family_seed)
    flat_mask = expected_mask.reshape(4096, 3)
    for stream in subset:
        flat_mask[payload, spec.stream_ids.index(stream)] = True
    assert np.array_equal(projection.known_mask, expected_mask)
    assert np.array_equal(
        projection.component_bits[expected_mask],
        expected[expected_mask],
    )
    assert not projection.component_bits[~expected_mask].any()
    assert projection.dependency_certificate_ids == tuple(sorted(
        records[stream].certificate_id for stream in subset))


@pytest.mark.parametrize("row_id", CMY7_ROWS + CMY8_ROWS)
def test_empty_projection_contains_exact_furniture_only(row_id):
    spec = get_format_row(row_id)
    _records, expected = _fixture(spec)
    projection = project_certified_color_tile((), spec, (0, 1, 2))
    furniture = _furniture_mask(spec)

    assert np.array_equal(projection.known_mask, furniture)
    assert np.array_equal(
        projection.component_bits[furniture], expected[furniture])
    assert not projection.component_bits[~furniture].any()
    assert projection.dependency_certificate_ids == ()


def test_projection_refuses_wrong_row_address_stream_and_padding():
    spec = get_format_row(CMY7_ROWS[0])
    records, _expected = _fixture(spec)
    record = records["main"]

    with pytest.raises(ValueError, match="certificate id"):
        project_certified_color_tile(
            (record,), get_format_row(CMY7_ROWS[1]), (0, 1, 2))
    with pytest.raises(ValueError, match="another physical tile"):
        project_certified_color_tile(
            (record,), spec, (0, 1, 3))
    with pytest.raises(ValueError, match="not declared"):
        project_certified_color_tile(
            (dataclasses.replace(record, stream_id="C"),),
            spec,
            (0, 1, 2),
        )

    corrupted = bytearray(record.packed_user_bits)
    corrupted[-1] |= 0x80
    with pytest.raises(ValueError, match="padding"):
        project_certified_color_tile(
            (dataclasses.replace(
                record, packed_user_bits=bytes(corrupted)),),
            spec,
            (0, 1, 2),
        )


def test_projection_refuses_two_valid_certificates_for_one_stream():
    spec = get_format_row(CMY8_ROWS[0])
    records, _expected = _fixture(spec)
    first = records["C"]
    user = np.zeros(spec.stream_profiles[0].user_bits, dtype=np.uint8)
    second = certificate_record_from_user_bits(
        spec,
        page=first.page,
        tile_yx=first.tile_yx,
        stream_id="C",
        user_bits=user,
        origin_attempt_id="contradictory-valid-certificate",
    )
    assert first.certificate_id != second.certificate_id

    with pytest.raises(ValueError, match="conflicting certificates"):
        project_certified_color_tile(
            (first, second), spec, (0, 1, 2))


def test_projection_accepts_an_exact_duplicate_without_duplicate_dependency():
    spec = get_format_row(CMY8_ROWS[0])
    records, _expected = _fixture(spec)
    record = records["M"]
    projection = project_certified_color_tile(
        (record, record), spec, (0, 1, 2))
    assert projection.dependency_certificate_ids == (
        record.certificate_id,)
