from __future__ import annotations

import hashlib
import struct

import numpy as np
import pytest

from holo.receive.evidence_blocks import (
    EvidenceBlock,
    EvidenceOrigin,
    TileAttemptView,
    _block_from_rows,
    block_from_rows,
    blocks_by_address,
    evidence_arity,
    merge_block_sets,
    tile_attempt_view,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _origin(label: str = "placement") -> EvidenceOrigin:
    return EvidenceOrigin(label, 7, 0.125, (_sha(f"{label}/dependency"),))


def _block(
    source: str,
    kind: str,
    rows: list[tuple[int, object, EvidenceOrigin]],
) -> EvidenceBlock:
    return block_from_rows(
        _sha(source), "native", 3, (4, 5), rows, kind=kind)  # type: ignore[arg-type]


def _rehash(body: bytes) -> bytes:
    return body + hashlib.sha256(body).digest()


def test_k_wire_format_and_attempt_surface_remain_exact() -> None:
    origin = EvidenceOrigin(
        "placement-a", 7, 0.125, (_sha("dep"),))
    block = _block_from_rows(
        _sha("source"), "native", 3, (4, 5), (
            (0, struct.pack("<f", -0.0), origin),
            (17, struct.pack("<f", 1.0 / 3.0), origin),
            (4095, struct.pack("<f", -2.5), origin),
        ))
    encoded = block.to_bytes()

    assert len(encoded) == 739
    assert block.block_id == (
        "4d3b18d2c6e497da75df5e0c5b1d9536"
        "3ed22dc613b8c6a6278d838292638615"
    )
    assert hashlib.sha256(encoded).hexdigest() == (
        "09c0cd5f5a301023ec0fe262145dbd9f"
        "d4e2d150a8ce29b51705b4bab2863d68"
    )
    assert encoded.startswith(b"holo/e023b/evidence-block/v4\x00")
    assert block.kind == "k"
    assert block.arity == 1
    assert block.printed_llr().shape == (3,)
    assert block.cell_tensor().shape == (64, 64)
    assert block.observed_cells().sum() == 3
    assert block.observed_cells().ravel()[0]
    assert not block.observed_cells().flags.writeable

    decoded = EvidenceBlock.from_bytes(encoded)
    view = tile_attempt_view((decoded,))
    assert decoded == block
    assert view.kind == "k"
    assert view.arity == 1
    assert view.llr_cells_f64.shape == (64, 64)
    expected = np.zeros((64, 64), np.float64)
    expected += block.cell_tensor()
    assert view.llr_cells_f64.tobytes() == expected.tobytes()


@pytest.mark.parametrize(("kind", "arity"), (("cmy7", 6), ("cmy8", 3)))
def test_color_blocks_round_trip_exact_cell_tensors(
    kind: str,
    arity: int,
) -> None:
    first = np.linspace(-1.25, 2.5, arity, dtype=np.float64)
    second = np.zeros(arity, np.float32)
    block = _block(
        f"{kind}/source", kind, [
            (9, first, _origin("first")),
            (4011, second, _origin("second")),
        ])

    assert evidence_arity(kind) == arity
    assert block.kind == kind
    assert block.arity == arity
    assert block.n_observed == 2
    assert block.printed_llr().shape == (2, arity)
    assert block.cell_tensor().shape == (64, 64, arity)
    assert np.array_equal(
        block.cell_tensor().reshape(4096, arity)[9],
        first.astype(np.float32),
    )
    assert np.array_equal(
        block.cell_tensor().reshape(4096, arity)[4011], second)
    assert block.observed_cells().ravel()[4011]
    assert np.count_nonzero(block.cell_tensor().reshape(4096, arity)[4011]) == 0
    assert not block.cell_tensor().flags.writeable

    encoded = block.to_bytes()
    decoded = EvidenceBlock.from_bytes(encoded)
    assert decoded == block
    assert decoded.to_bytes() == encoded
    assert encoded.startswith(
        f"holo/e023b/evidence-block/{kind}-v1".encode())


def test_cmy8_one_physical_union_feeds_all_three_streams() -> None:
    first = _block(
        "capture-a", "cmy8", [
            (0, (1.0, 2.0, 3.0), _origin("a0")),
            (4, (0.0, 0.0, 0.0), _origin("a4")),
        ])
    second = _block(
        "capture-b", "cmy8", [
            (0, (0.5, -2.0, 4.0), _origin("b0")),
            (5, (-1.0, -2.0, -3.0), _origin("b5")),
        ])
    view = tile_attempt_view((second, first))

    assert view.components == (first, second)
    assert view.kind == "cmy8"
    assert view.arity == 3
    assert view.observed_cells().ravel()[[0, 4, 5]].all()
    assert view.observed_cells().sum() == 3
    assert np.array_equal(
        view.llr_cells_f64.reshape(4096, 3)[0], (1.5, 0.0, 7.0))

    assert merge_block_sets((first,), (second, first)) == (first, second)


def test_address_index_reuses_one_validated_frontier_partition() -> None:
    first = _block(
        "capture-a", "cmy8",
        [(0, (1.0, 2.0, 3.0), _origin("a"))],
    )
    second = _block(
        "capture-b", "cmy8",
        [(0, (4.0, 5.0, 6.0), _origin("b"))],
    )
    other = block_from_rows(
        _sha("capture-c"),
        "native",
        3,
        (4, 6),
        [(0, (7.0, 8.0, 9.0), _origin("c"))],
        kind="cmy8",
    )

    indexed = blocks_by_address((second, other, first), lane_id="native")

    assert indexed == {
        (3, 4, 5): (second, first),
        (3, 4, 6): (other,),
    }
    with pytest.raises(
            ValueError, match="duplicate source component for tile"):
        blocks_by_address((first, first))


def test_observation_bitmap_not_score_values_controls_cmy7_pack_eligibility(
) -> None:
    zero = np.zeros(6, np.float32)
    complete = _block(
        "complete", "cmy7",
        [(flat, zero, _origin(f"p{flat}")) for flat in range(4)])
    incomplete = _block(
        "incomplete", "cmy7",
        [(flat, zero, _origin(f"q{flat}")) for flat in range(3)])

    assert complete.observed_cells().ravel()[:4].all()
    assert complete.observed_cells().sum() == 4
    assert np.count_nonzero(complete.cell_tensor()) == 0
    assert not incomplete.observed_cells().ravel()[:4].all()


@pytest.mark.parametrize("kind", ("k", "cmy7", "cmy8"))
def test_builder_rejects_bad_shapes_nonfinite_and_invalid_slots(
    kind: str,
) -> None:
    arity = evidence_arity(kind)
    valid = np.zeros(arity, np.float32)
    origin = _origin()

    bad_values = (
        np.zeros((arity, 1), np.float32),
        np.zeros(arity + 1, np.float32),
        np.asarray(["0"] * arity),
        np.full(arity, np.nan),
        np.full(arity, np.inf),
        np.full(arity, 1e300),
    )
    for values in bad_values:
        with pytest.raises(ValueError):
            _block("bad-values", kind, [(0, values, origin)])
    for flat in (-1, 4096, True, 1.5, np.int64(1)):
        with pytest.raises(ValueError):
            _block("bad-flat", kind, [(flat, valid, origin)])
    with pytest.raises(ValueError, match="unique"):
        _block(
            "duplicate", kind,
            [(0, valid, origin), (0, valid, origin)])

    with pytest.raises(ValueError, match="kind"):
        block_from_rows(
            _sha("bad-kind"), "native", 0, (0, 0),
            [(0, (0.0,), origin)], kind="rgb")  # type: ignore[arg-type]


def test_color_parser_rejects_tamper_wrong_kind_nonfinite_and_truncation(
) -> None:
    block = _block(
        "parse", "cmy8",
        [(11, (1.25, 2.5, 3.75), _origin("parse"))])
    encoded = block.to_bytes()

    tampered = bytearray(encoded)
    tampered[-40] ^= 1
    with pytest.raises(ValueError, match="content SHA-256"):
        EvidenceBlock.from_bytes(bytes(tampered))

    body = encoded[:-32]
    unknown = body.replace(
        b"holo/e023b/evidence-block/cmy8-v1\x00",
        b"holo/e023b/evidence-block/other-v1\x00", 1)
    with pytest.raises(ValueError, match="unknown binary format"):
        EvidenceBlock.from_bytes(_rehash(unknown))

    wrong_kind = body.replace(b"cmy8-v1", b"cmy7-v1", 1)
    with pytest.raises(ValueError):
        EvidenceBlock.from_bytes(_rehash(wrong_kind))

    vector = np.asarray((1.25, 2.5, 3.75), dtype="<f4").tobytes()
    assert body.count(vector) == 1
    nonfinite = body.replace(
        vector,
        np.asarray((np.nan, 2.5, 3.75), dtype="<f4").tobytes(),
        1,
    )
    with pytest.raises(ValueError, match="finite"):
        EvidenceBlock.from_bytes(_rehash(nonfinite))

    with pytest.raises(ValueError):
        EvidenceBlock.from_bytes(_rehash(body[:-1]))


def test_attempt_rejects_mixed_kinds_wrong_shapes_and_nonfinite() -> None:
    cmy7 = _block(
        "mixed-cmy7", "cmy7",
        [(0, np.zeros(6), _origin("cmy7"))])
    cmy8 = _block(
        "mixed-cmy8", "cmy8",
        [(0, np.zeros(3), _origin("cmy8"))])
    with pytest.raises(ValueError, match="mix evidence kinds"):
        tile_attempt_view((cmy7, cmy8))

    for tensor in (
        np.zeros((64, 64), np.float64),
        np.full((64, 64, 6), np.nan),
    ):
        with pytest.raises(ValueError):
            TileAttemptView((cmy7,), tensor)



def test_same_physical_key_cannot_hold_two_kinds_or_contents() -> None:
    source = _sha("one-source")
    origin = _origin("one-origin")
    cmy7 = block_from_rows(
        source, "native", 0, (0, 0),
        [(0, np.zeros(6), origin)], kind="cmy7")
    cmy8 = block_from_rows(
        source, "native", 0, (0, 0),
        [(0, np.zeros(3), origin)], kind="cmy8")
    changed = block_from_rows(
        source, "native", 0, (0, 0),
        [(0, np.ones(6), origin)], kind="cmy7")

    assert merge_block_sets((cmy7,), (cmy7,)) == (cmy7,)
    with pytest.raises(ValueError, match="conflicting contents"):
        merge_block_sets((cmy7,), (cmy8,))
    with pytest.raises(ValueError, match="conflicting contents"):
        merge_block_sets((cmy7,), (changed,))
