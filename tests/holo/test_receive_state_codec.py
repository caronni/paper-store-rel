"""State-codec persist exactness: blob cache + single payload serialization.

PAYLOAD-REWORK-PLAN 3.6 / growth-audit row 3 pins.  The naive pre-change
encoder (re-serialize + re-compress every block, dump the payload twice) is
kept here as the test-local oracle; the production codec must stay
byte-identical to it (the test_cold_search_exactness precedent).
"""
from __future__ import annotations

import base64
import hashlib
import zlib
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from typing import Any

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.receive import state_codec
from holo.receive.evidence_blocks import (
    EvidenceBlock,
    EvidenceOrigin,
    _block_from_rows,
)
from holo.receive.session import (
    STATE_MAGIC,
    STATE_SCHEMA_VERSION,
    SessionState,
)
from holo.receive.state_codec import (
    authoritative_state_sha256,
    canonical_bytes,
    encode_typed,
    load_typed,
    load_typed_with_digest,
    save_typed,
    save_typed_with_digest,
)


# --------------------------------------------------------------------------
# The naive pre-change encoder, verbatim: per-persist blob re-serialization
# and a payload dumped once for the digest preimage and once for the
# envelope.  Kept as the oracle; never optimize this copy.
# --------------------------------------------------------------------------

def _naive_blob_inline(value: Any) -> dict[str, Any]:
    identity = value.block_id
    data = value.to_bytes()
    packed = base64.b64encode(zlib.compress(data, 6)).decode("ascii")
    return {"sha256": identity, "size": len(data), "data": packed}


def _naive_encode(value: Any) -> Any:
    if is_dataclass(value):
        output: dict[str, Any] = {}
        for row in fields(value):
            if not row.metadata.get("persist", True):
                continue
            item = getattr(value, row.name)
            if row.metadata.get("blob_items", False):
                output[row.name] = [_naive_blob_inline(item_row)
                                    for item_row in item]
            else:
                output[row.name] = _naive_encode(item)
        return output
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, tuple):
        return [_naive_encode(row) for row in value]
    return value


def _naive_state_file_bytes(value: Any, *, magic: str,
                            schema: int) -> tuple[bytes, str]:
    payload = _naive_encode(value)
    digest = authoritative_state_sha256(payload, magic=magic, schema=schema)
    envelope = {
        "magic": magic, "schema_version": schema,
        "state_sha256": digest,
        "state": payload,
    }
    return canonical_bytes(envelope), digest


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_blob_cache():
    state_codec._blob_cache.clear()
    yield
    state_codec._blob_cache.clear()


def _block(tile_yx: tuple[int, int], seed: int) -> EvidenceBlock:
    origin = EvidenceOrigin(f"{'b' * 64}/native/patch-{seed}", seed, 0.25)
    rows = tuple(
        (flat, np.float32(0.5 + flat + seed).tobytes(), origin)
        for flat in range(3))
    return _block_from_rows("b" * 64, "native", 0, tile_yx, rows)


def _session_state() -> SessionState:
    spec = make_spec("c3-r0550")
    state = SessionState.create(
        spec.spec_id, "qualification/state-codec-v1", (0, 1))
    return replace(
        state, blocks=(_block((0, 0), 1), _block((0, 1), 2),
                       _block((1, 0), 3)))


class _Mood(Enum):
    CALM = "calm"
    STORM = "storm"


@dataclass(frozen=True)
class _StressLeaf:
    name: str
    weight: float


@dataclass(frozen=True)
class _StressState:
    title: str
    mood: _Mood
    seed: bytes
    knees: tuple[int, ...]
    leaves: tuple[_StressLeaf, ...]
    note: str | None
    flag: bool
    blocks: tuple[EvidenceBlock, ...] = field(
        default=(), metadata={"blob_items": True})
    scratch: int = field(default=0, metadata={"persist": False})


_STRESS_MAGIC = 'stress-µ "magic"'
_STRESS_SCHEMA = 7


def _stress_state() -> _StressState:
    return _StressState(
        title='holo "state" \\ codec\nμπ😀 end\ttab',
        mood=_Mood.STORM,
        seed=bytes(range(17)),
        knees=(0, 3, 2**40),
        leaves=(_StressLeaf("a", 0.1), _StressLeaf("µ", 1e300),
                _StressLeaf("z", -0.0)),
        note=None,
        flag=True,
        blocks=(_block((2, 2), 9),),
        scratch=99,
    )


# --------------------------------------------------------------------------
# Pins
# --------------------------------------------------------------------------

def test_persisted_session_bytes_match_naive_oracle(tmp_path) -> None:
    state = _session_state()
    path = tmp_path / "session.json"
    changed, digest = save_typed_with_digest(
        path, state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    assert changed
    naive_bytes, naive_digest = _naive_state_file_bytes(
        state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    assert path.read_bytes() == naive_bytes
    assert digest == naive_digest
    # Second persist rides the warm blob cache; bytes must not move.
    again = tmp_path / "again.json"
    assert save_typed(
        again, state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    assert again.read_bytes() == naive_bytes


def test_envelope_splice_is_byte_identical_on_adversarial_values(
    tmp_path,
) -> None:
    state = _stress_state()
    path = tmp_path / "stress.json"
    changed, digest = save_typed_with_digest(
        path, state, magic=_STRESS_MAGIC, schema=_STRESS_SCHEMA)
    assert changed
    naive_bytes, naive_digest = _naive_state_file_bytes(
        state, magic=_STRESS_MAGIC, schema=_STRESS_SCHEMA)
    assert path.read_bytes() == naive_bytes
    assert digest == naive_digest
    loaded = load_typed(
        path, _StressState, magic=_STRESS_MAGIC, schema=_STRESS_SCHEMA)
    assert loaded == replace(state, scratch=0)


def test_blob_cache_serializes_and_compresses_once_per_block(
    tmp_path, monkeypatch,
) -> None:
    blocks = (_block((0, 0), 1), _block((0, 1), 2))
    state = replace(_session_state(), blocks=blocks)

    to_bytes_calls: list[str] = []
    original_to_bytes = EvidenceBlock.to_bytes

    def counting_to_bytes(self: EvidenceBlock) -> bytes:
        to_bytes_calls.append(self.block_id)
        return original_to_bytes(self)

    compress_calls: list[int] = []
    original_compress = zlib.compress

    def counting_compress(data: bytes, level: int = -1) -> bytes:
        compress_calls.append(len(data))
        return original_compress(data, level)

    monkeypatch.setattr(EvidenceBlock, "to_bytes", counting_to_bytes)
    monkeypatch.setattr(zlib, "compress", counting_compress)

    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    _, digest_one = save_typed_with_digest(
        first, state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    _, digest_two = save_typed_with_digest(
        second, state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    assert digest_one == digest_two
    assert first.read_bytes() == second.read_bytes()
    # ONE serialization + ONE compression per block across BOTH persists.
    assert sorted(to_bytes_calls) == sorted(row.block_id for row in blocks)
    assert len(compress_calls) == len(blocks)

    # The cache is bounded by the live block set of the latest persist.
    shrunk = replace(state, blocks=blocks[:1])
    assert save_typed(
        tmp_path / "three.json", shrunk,
        magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    assert set(state_codec._blob_cache) == {blocks[0].block_id}


def test_roundtrip_digest_matches_authoritative_sha256(tmp_path) -> None:
    state = _session_state()
    path = tmp_path / "session.json"
    changed, digest = save_typed_with_digest(
        path, state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    assert changed
    loaded, loaded_digest = load_typed_with_digest(
        path, SessionState, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION)
    assert loaded_digest == digest
    assert loaded == state
    assert authoritative_state_sha256(
        encode_typed(loaded), magic=STATE_MAGIC,
        schema=STATE_SCHEMA_VERSION) == digest
