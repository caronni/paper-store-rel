"""Codec strictness and record invariants (DESIGN §5, §10.4).

The codec is the wall between durable bytes and typed state: it must
round-trip every record exactly, and refuse anything it does not
understand rather than guessing (no migration decoders).
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from holo2.core import codec
from holo2.core.records import BlobRef, MalformedKeyError, ResourceKey
from conftest import (POSE, WINDOW, CaptureRecord, FootingSpec, LabelPool,
                      PoseRecord, TileRecord, WindowRecord, evidence_key,
                      make_window, parse_evidence_key, parse_tile_key,
                      tile_key)

from conftest import sample_records


@pytest.mark.parametrize("key", sorted(sample_records()))
def test_every_record_round_trips(key: ResourceKey) -> None:
    record = sample_records()[key]
    encoded = codec.encode_dataclass(record)
    assert codec.decode_dataclass(type(record), encoded) == record


def test_a_typed_record_entry_carries_the_class_name() -> None:
    """``{type, value}``: the one spelling of "some record", tag included.

    ``encode_dataclass`` alone does not carry the class, so two record
    types with equal field values encode identically — which is why every
    durable and digested place that holds a polymorphic record (the
    envelope's entries, a proposed ``Write``, the trace's sampled output
    digest) goes through this helper instead of re-spelling the pair.
    """
    record = TileRecord()
    entry = codec.encode_typed_record(record)
    assert entry == {"type": "TileRecord",
                     "value": codec.encode_dataclass(record)}
    assert (codec.encode_typed_record(LabelPool("p", ()))["type"]
            == "LabelPool")


def test_canonical_json_is_deterministic_and_sorted() -> None:
    first = codec.canonical_json_bytes({"b": 1, "a": [2, 3]})
    second = codec.canonical_json_bytes({"a": [2, 3], "b": 1})
    assert first == second == b'{"a":[2,3],"b":1}'


def test_canonical_json_refuses_non_finite() -> None:
    with pytest.raises(ValueError):
        codec.canonical_json_bytes({"x": float("nan")})


@pytest.mark.parametrize("payload,message", [
    (b'{"a":1,"a":2}', "duplicate JSON key"),
    (b'{"x":NaN}', "not a number"),
    (b'{"x":Infinity}', "not a number"),
    (b'{"x":-Infinity}', "not a number"),
])
def test_the_read_path_refuses_what_the_write_path_cannot_emit(
        payload: bytes, message: str) -> None:
    """F-26 clause 1: strict on the way in, not only on the way out."""
    with pytest.raises(codec.CodecError, match=message):
        codec.parse_json_bytes(payload)


def test_enum_encodes_by_name_not_value() -> None:
    encoded = codec.encode_dataclass(make_window())
    assert encoded["status"] == "ACTIVE"


def test_fraction_round_trips_exactly() -> None:
    footing = FootingSpec("cap:8/3", Fraction(8, 3), "ab" * 32)
    encoded = codec.encode_dataclass(footing)
    assert encoded["ppc"] == [8, 3]
    assert codec.decode_dataclass(FootingSpec, encoded).ppc == Fraction(8, 3)


def test_unknown_field_refused() -> None:
    encoded = codec.encode_dataclass(TileRecord())
    encoded["invented"] = 1
    with pytest.raises(codec.CodecError, match="unknown field"):
        codec.decode_dataclass(TileRecord, encoded)


def test_missing_field_refused_even_when_it_has_a_default() -> None:
    encoded = codec.encode_dataclass(TileRecord())
    del encoded["metadata_bit"]
    with pytest.raises(codec.CodecError, match="missing field"):
        codec.decode_dataclass(TileRecord, encoded)


def test_wrong_type_refused() -> None:
    encoded = codec.encode_dataclass(TileRecord())
    encoded["observed_by"] = "cap:8/1"
    with pytest.raises(codec.CodecError):
        codec.decode_dataclass(TileRecord, encoded)


def test_unknown_enum_member_refused() -> None:
    encoded = codec.encode_dataclass(make_window())
    encoded["status"] = "SEMI_RETIRED"
    with pytest.raises(codec.CodecError, match="unknown member"):
        codec.decode_dataclass(WindowRecord, encoded)


def test_bool_is_not_an_int_field() -> None:
    encoded = codec.encode_dataclass(TileRecord())
    encoded["metadata_bit"] = True
    with pytest.raises(codec.CodecError):
        codec.decode_dataclass(TileRecord, encoded)


def test_key_round_trip_and_parsers() -> None:
    key = tile_key(3, 12, 40, "C")
    assert ResourceKey.from_json(key.to_json()) == key
    assert parse_tile_key(key) == (3, 12, 40, "C")
    evidence = evidence_key("cap:8/1", 3, 12, 40, "C", POSE)
    assert parse_evidence_key(evidence) == ("cap:8/1", 3, 12, 40, "C", POSE)
    with pytest.raises(MalformedKeyError):
        parse_tile_key(evidence)


def test_keys_sort_deterministically() -> None:
    keys = [tile_key(0, 0, 1, "K"), tile_key(0, 0, 0, "K"),
            evidence_key("f", 0, 0, 0, "K", POSE)]
    assert sorted(keys) == sorted(sorted(keys, reverse=True))


def test_set_shaped_tuples_must_be_sorted_and_unique() -> None:
    with pytest.raises(ValueError, match="sorted and unique"):
        TileRecord(observed_by=("b", "a"))
    with pytest.raises(ValueError, match="sorted and unique"):
        TileRecord(observed_by=("a", "a"))
    with pytest.raises(ValueError, match="sorted and unique"):
        LabelPool("p", (WINDOW, ResourceKey("window", ())))


def test_footings_must_ascend_in_ppc() -> None:
    with pytest.raises(ValueError, match="ascend in ppc"):
        CaptureRecord(
            source_sha256="ab" * 32, dpi_true=4800.0, shape_px=(10, 10),
            dtype="uint8", channels=1, platen_backing=200.0,
            footings=(FootingSpec("b", Fraction(8), "ab" * 32),
                      FootingSpec("a", Fraction(2), "ab" * 32)))


def test_affine_is_six_terms() -> None:
    with pytest.raises(ValueError, match="6 affine terms"):
        PoseRecord(WINDOW, "f", 0, (1.0, 0.0, 0.0))


def test_blob_ref_dtype_and_shape_come_as_a_pair() -> None:
    with pytest.raises(ValueError, match="come as a pair"):
        BlobRef("00" * 32, 4, dtype="<f4")
