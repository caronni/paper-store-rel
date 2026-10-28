"""Exact-oracle tests for common-K stream-major source mapping."""
from __future__ import annotations

import math

import numpy as np
import pytest

from holo.core import channel, fountain
from holo.format import envelope, streamset


def _byte_bits(data: bytes) -> list[int]:
    """Independent, deliberately bit-at-a-time MSB-first oracle."""
    return [
        (byte >> (7 - bit)) & 1
        for byte in data
        for bit in range(8)
    ]


def _packed_bits(data: bytes, n_bits: int) -> list[int]:
    return [
        (data[position // 8] >> (7 - position % 8)) & 1
        for position in range(n_bits)
    ]


def _source_bits(packed: streamset.PackedSource) -> list[int]:
    return fountain.unpack_rows(
        packed.rows, packed.symbol_bits
    ).reshape(-1).tolist()


def _solved(
    packed: streamset.PackedSourceSet,
) -> list[tuple[str, np.ndarray]]:
    return [
        (
            item.stream_id,
            fountain.unpack_rows(item.rows, item.symbol_bits),
        )
        for item in packed.streams
    ]


def _oracle_solved(
    wrapped: bytes,
    layout: streamset.StreamSet,
    k_total: int,
) -> list[tuple[str, np.ndarray]]:
    flat = _byte_bits(wrapped)
    capacity = k_total * layout.total_symbol_bits
    flat.extend([0] * (capacity - len(flat)))
    result: list[tuple[str, np.ndarray]] = []
    offset = 0
    for stream_id, width in layout.streams:
        n_bits = k_total * width
        rows = np.asarray(
            flat[offset:offset + n_bits], dtype=np.uint8
        ).reshape(k_total, width)
        result.append((stream_id, rows))
        offset += n_bits
    assert offset == capacity
    return result


def _set_global_bit(
    solved: list[tuple[str, np.ndarray]],
    layout: streamset.StreamSet,
    k_total: int,
    position: int,
) -> None:
    offset = 0
    for index, (_stream_id, width) in enumerate(layout.streams):
        stream_bits = k_total * width
        if position < offset + stream_bits:
            local = position - offset
            solved[index][1][local // width, local % width] = 1
            return
        offset += stream_bits
    raise AssertionError("test bit is outside the stream set")


def test_stream_set_is_ordered_unique_and_validated():
    layout = streamset.StreamSet((("C", 5), ("M", 7), ("Y", 9)))
    assert layout.streams == (("C", 5), ("M", 7), ("Y", 9))
    assert layout.stream_ids == streamset.CMY8_STREAM_ORDER
    assert layout.symbol_widths == (5, 7, 9)
    assert layout.total_symbol_bits == 21

    with pytest.raises(ValueError, match="must not be empty"):
        streamset.StreamSet(())
    with pytest.raises(ValueError, match="duplicate"):
        streamset.StreamSet((("C", 5), ("C", 7)))
    with pytest.raises(ValueError, match="non-empty strings"):
        streamset.StreamSet((("", 5),))
    with pytest.raises(ValueError, match="positive"):
        streamset.StreamSet((("C", 0),))
    with pytest.raises(TypeError, match="integers"):
        streamset.StreamSet((("C", True),))
    with pytest.raises(TypeError, match="pair"):
        streamset.StreamSet((("C", 5, "extra"),))


@pytest.mark.parametrize(
    ("widths", "payload"),
    [
        ((5, 7, 9), bytes(range(29))),
        # The provisional p120 CMY8 source width.  Odd K puts both C/M and
        # M/Y boundaries off-byte; even K still exercises 2087-bit rows.
        ((2087, 2087, 2087), bytes((i * 73 + 11) & 0xFF
                                   for i in range(2_041))),
    ],
)
def test_pack_and_reassemble_match_independent_bit_oracle(
    widths: tuple[int, int, int],
    payload: bytes,
    monkeypatch: pytest.MonkeyPatch,
):
    # Tiny chunks force row/chunk and byte-boundary crossings without a
    # payload-sized temporary, while the expected result is bit-at-a-time.
    # The packer reads fountain.CHUNK_BITS (shared kernel); the reassembly
    # walkers still read streamset._CHUNK_BITS — patch both.
    monkeypatch.setattr(fountain, "CHUNK_BITS", 37)
    monkeypatch.setattr(streamset, "_CHUNK_BITS", 37)
    layout = streamset.StreamSet(tuple(zip(
        streamset.CMY8_STREAM_ORDER, widths, strict=True
    )))
    wrapped = envelope.wrap(payload)
    got = streamset.pack_source(wrapped, layout)
    expected_k = math.ceil(len(wrapped) * 8 / sum(widths))
    assert got.k_total == expected_k
    assert streamset.source_symbol_count(len(payload), layout) == expected_k
    assert tuple(item.stream_id for item in got.streams) == \
        streamset.CMY8_STREAM_ORDER

    reference = _byte_bits(wrapped)
    reference.extend(
        [0] * (expected_k * sum(widths) - len(reference))
    )
    offset = 0
    for item, width in zip(got.streams, widths, strict=True):
        assert item.symbol_bits == width
        assert item.rows.shape == (expected_k, math.ceil(width / 8))
        stream_bits = expected_k * width
        assert _source_bits(item) == reference[offset:offset + stream_bits]
        if width % 8:
            unused_mask = (1 << (8 - width % 8)) - 1
            assert not np.any(item.rows[:, -1] & unused_mask)
        offset += stream_bits
    assert offset == len(reference)

    reassembled = streamset.reassemble_solved(
        _solved(got), layout, got.k_total
    )
    assert _packed_bits(reassembled, len(reference)) == reference
    assert streamset.unwrap_solved(
        _solved(got), layout, got.k_total
    ) == payload


def test_bits_walk_both_sides_of_every_stream_boundary():
    layout = streamset.StreamSet((("C", 5), ("M", 7), ("Y", 9)))
    n_bytes = 80
    k_total = math.ceil(n_bytes * 8 / layout.total_symbol_bits)
    boundaries = (
        0,
        k_total * 5 - 1,
        k_total * 5,
        k_total * (5 + 7) - 1,
        k_total * (5 + 7),
        n_bytes * 8 - 1,
    )

    for position in boundaries:
        raw = bytearray(n_bytes)
        raw[position // 8] |= 1 << (7 - position % 8)
        packed = streamset.pack_source(raw, layout)
        flat = [
            bit
            for source in packed.streams
            for bit in _source_bits(source)
        ]
        assert packed.k_total == k_total
        assert sum(flat) == 1
        assert flat[position] == 1

        rebuilt = streamset.reassemble_solved(
            _solved(packed), layout, k_total
        )
        assert _packed_bits(rebuilt, k_total * 21) == flat

    # The last *capacity* bit is padding for this byte stream.  Reassembly
    # still preserves it exactly; the verified inverse rejects it below.
    solved = [
        (stream_id, np.zeros((k_total, width), dtype=np.uint8))
        for stream_id, width in layout.streams
    ]
    _set_global_bit(
        solved, layout, k_total, k_total * layout.total_symbol_bits - 1
    )
    rebuilt = streamset.reassemble_solved(solved, layout, k_total)
    assert _packed_bits(
        rebuilt, k_total * layout.total_symbol_bits
    )[-1] == 1


def test_one_stream_mapping_is_fountain_pack_source_equivalent():
    layout = streamset.StreamSet((("main", 47),))
    payload = bytes((i * 19 + 3) & 0xFF for i in range(151))
    wrapped = envelope.wrap(payload)
    got = streamset.pack_source(wrapped, layout)
    expected = fountain.pack_source(wrapped, got.k_total, 47)

    assert len(got.streams) == 1
    assert np.array_equal(got.streams[0].rows, expected)
    solved = [("main", fountain.unpack_rows(expected, 47))]
    assert streamset.unwrap_solved(solved, layout, got.k_total) == payload


def test_cmy8_joined_fountain_streams_close_one_envelope():
    widths = (2087, 2087, 2087)
    layout = streamset.StreamSet(tuple(zip(
        channel.PLANE_ORDER, widths, strict=True)))
    payload = bytes((index * 37 + 9) & 0xFF for index in range(2_041))
    packed = streamset.pack_payload(payload, layout)
    assert packed.k_total >= 2

    solved: list[tuple[str, np.ndarray]] = []
    esis = np.arange(24, dtype=np.int64)
    for source, stream_aux in zip(
            packed.streams, (1, 2, 3), strict=True):
        code = fountain.VolumeCode(
            packed.k_total,
            source.symbol_bits,
            b"holo/v1/cmy8-joined-test",
            tiles_per_page=8,
            stream_id=source.stream_id,
            fountain_aux=stream_aux,
        )
        assert any(code.source_row_of(int(esi)) is not None for esi in esis)
        assert any(code.source_row_of(int(esi)) is None for esi in esis)
        symbols = code.encode_symbols(source.rows, esis)
        decoder = fountain.Decoder(code)
        for esi, symbol in zip(esis, symbols, strict=True):
            decoder.add_symbol(int(esi), symbol)
        source_bits = decoder.try_solve()
        assert source_bits is not None
        solved.append((source.stream_id, source_bits))

    assert streamset.unwrap_solved(
        solved, layout, packed.k_total) == payload
    with pytest.raises(ValueError, match="expected 3"):
        streamset.unwrap_solved(
            solved[:-1], layout, packed.k_total)


def test_inverse_refuses_wrong_order_shapes_and_values():
    layout = streamset.StreamSet((("C", 5), ("M", 7), ("Y", 9)))
    packed = streamset.pack_payload(b"shape and order", layout)
    solved = _solved(packed)
    k_total = packed.k_total

    with pytest.raises(ValueError, match="expected 'C'"):
        streamset.reassemble_solved(
            [solved[1], solved[0], solved[2]], layout, k_total
        )
    with pytest.raises(ValueError, match="expected 3"):
        streamset.reassemble_solved(solved[:-1], layout, k_total)

    wrong_k = [(name, rows.copy()) for name, rows in solved]
    wrong_k[0] = ("C", wrong_k[0][1][:-1])
    with pytest.raises(ValueError, match="shape"):
        streamset.reassemble_solved(wrong_k, layout, k_total)

    packed_rows = [(name, source.rows) for (name, _), source in zip(
        solved, packed.streams, strict=True
    )]
    with pytest.raises(ValueError, match="shape"):
        streamset.reassemble_solved(packed_rows, layout, k_total)

    nonbinary = [(name, rows.copy()) for name, rows in solved]
    nonbinary[1][1][0, 0] = 2
    with pytest.raises(ValueError, match="only 0/1"):
        streamset.reassemble_solved(nonbinary, layout, k_total)

    nonfinite = [
        (name, rows.astype(np.float64)) for name, rows in solved
    ]
    nonfinite[2][1][0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        streamset.reassemble_solved(nonfinite, layout, k_total)

    with pytest.raises(TypeError, match="integer"):
        streamset.reassemble_solved(solved, layout, True)
    with pytest.raises(TypeError, match="StreamSet"):
        streamset.pack_source(envelope.wrap(b"x"), (("C", 5),))


def test_verified_inverse_checks_envelope_canonical_k_and_zero_tail():
    layout = streamset.StreamSet((("C", 5), ("M", 7), ("Y", 9)))
    payload = b"three independent close gates"
    wrapped = envelope.wrap(payload)
    packed = streamset.pack_source(wrapped, layout)
    solved = _solved(packed)
    capacity_bits = packed.k_total * layout.total_symbol_bits
    used_bits = len(wrapped) * 8
    assert used_bits < capacity_bits
    assert streamset.unwrap_solved(
        solved, layout, packed.k_total
    ) == payload

    bad_padding = [(name, rows.copy()) for name, rows in solved]
    _set_global_bit(
        bad_padding, layout, packed.k_total, capacity_bits - 1
    )
    with pytest.raises(
        streamset.StreamSetIntegrityError, match="nonzero bits"
    ):
        streamset.unwrap_solved(
            bad_padding, layout, packed.k_total
        )

    overlong_k = packed.k_total + 1
    overlong = _oracle_solved(wrapped, layout, overlong_k)
    with pytest.raises(
        streamset.StreamSetIntegrityError, match="noncanonical"
    ):
        streamset.unwrap_solved(overlong, layout, overlong_k)

    damaged = [(name, rows.copy()) for name, rows in solved]
    # Flip one digest bit while leaving the canonical tail untouched.
    damaged[0][1][0, 0] ^= 1
    with pytest.raises(
        streamset.StreamSetIntegrityError, match="verification failed"
    ):
        streamset.unwrap_solved(damaged, layout, packed.k_total)


def test_verified_inverse_does_not_count_storage_only_final_bits():
    # A 293-bit source occupies 37 packed bytes.  For this payload the last
    # three envelope bits happen to be zero, so ordinary byte-level envelope
    # verification can succeed even though those bits were never encoded.
    # The exact-capacity gate must still reject it before canonical-K.
    layout = streamset.StreamSet((("main", 293),))
    wrapped = envelope.wrap(b"\x00")
    assert len(wrapped) * 8 == 296
    solved = _oracle_solved(wrapped, layout, 1)
    assert envelope.unwrap(
        streamset.reassemble_solved(solved, layout, 1)
    ) == b"\x00"
    with pytest.raises(
        streamset.StreamSetIntegrityError, match="exact.*capacity"
    ):
        streamset.unwrap_solved(solved, layout, 1)


def test_source_pack_validation():
    layout = streamset.StreamSet((("C", 5), ("M", 7), ("Y", 9)))
    with pytest.raises(ValueError, match="must not be empty"):
        streamset.pack_source(b"", layout)
    with pytest.raises(TypeError, match="bytes-like"):
        streamset.pack_source("not bytes", layout)
    with pytest.raises(TypeError, match="integers"):
        streamset.source_symbol_count(True, layout)
