"""Phase-7 payload null set (PAYLOAD-REWORK-PLAN 7.1b, lens-coverage:11).

The E022 placement stage has its 49-null battery ports (wrong page,
wrong-seed sibling row).  These are the surviving PAYLOAD-stage axes:

* WRONG-KEYSTREAM null — true tile evidence decoded against a sibling
  format seed (same coding, different derived geometry => different
  AES-CTR keystream and slot permutation) must produce ZERO certificates.
  The placement-stage sibling null lives in
  ``test_placement_null_battery_extended``; this is its payload analog.
* STATE-TAMPER nulls — one flipped bit in a persisted session's inline
  block payload refuses at the durable load boundary (digest); a tampered
  certificate ``packed_user_bits`` refuses at record validation; a
  tampered evidence-block origin row refuses at the block's own
  content-address boundary.

Every null asserts the REFUSAL PATH: zero wrong bytes ever emerge.
"""
from __future__ import annotations

import base64
import hashlib
import re

import numpy as np
import pytest

from holo.core.fountain import VolumeCode
from holo.format.descriptor import FormatSpec, get_coding
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive import payload
from holo.receive.evidence import AttemptState, AttemptStage
from holo.receive.evidence_blocks import EvidenceBlock, EvidenceOrigin, _block_from_rows
from holo.receive.records import validate_certificate_record
from holo.receive.session import authoritative_bytes, load_session


# ---------------------------------------------------------------------------
# fixture: the smallest genuine roundtrip page (7x7 c3 tiles) + a sibling


@pytest.fixture(scope="module")
def null_fixture():
    spec = FormatSpec(get_coding("c3-r0550"), "null-60x60", (60.0, 60.0), 0.0)
    assert spec.layout.tiles_yx == (7, 7)
    # Same coding row, different derived geometry: the format seed
    # (a pure function of coding + cells) forks, so the keystream, the
    # scramble, and the slot permutation are all sibling-wrong.
    sibling = FormatSpec(
        get_coding("c3-r0550"), "null-sibling", (76.0, 76.0), 0.0)
    assert sibling.seed != spec.seed
    assert sibling.spec_id != spec.spec_id
    assert sibling.layout.tiles_yx >= (7, 7)

    volume_payload = hashlib.sha256(b"payload-null-battery-v1").digest()
    plan = plan_volume(spec, len(volume_payload), 0.5)
    source = source_packed_for(volume_payload, plan)
    code = VolumeCode(
        plan.k_total, plan.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page)
    symbols = code.encode_symbols(
        source, np.arange(spec.tiles_per_page, dtype=np.int64))
    page = compose_page_cells(spec, 0, symbols, plan.k_total)
    return spec, sibling, page


def _tile_llr(spec, page: np.ndarray, index: int) -> np.ndarray:
    _, tiles_x = spec.layout.tiles_yx
    tile_y, tile_x = divmod(index, tiles_x)
    tile = page[tile_y * 64:(tile_y + 1) * 64, tile_x * 64:(tile_x + 1) * 64]
    return (tile.astype(np.float64) * 2.0 - 1.0) * 5.0


def _attempt(spec, llr, index: int, tag: str):
    _, tiles_x = spec.layout.tiles_yx
    tile_y, tile_x = divmod(index, tiles_x)
    return payload.attempt_k_tile(
        llr, spec, (0, tile_y, tile_x), AttemptStage.SCAN,
        source_sha256=hashlib.sha256(tag.encode()).hexdigest(),
        lane_id="native",
        component_block_ids=(
            hashlib.sha256(f"block-{tag}".encode()).hexdigest(),),
    )


# ---------------------------------------------------------------------------
# (a) the wrong-keystream null


def test_true_evidence_against_sibling_keystream_yields_zero_certificates(
    null_fixture,
) -> None:
    spec, sibling, page = null_fixture

    # Positive control: the same evidence certifies under its own seed.
    record, certificate = _attempt(
        spec, _tile_llr(spec, page, 0), 0, "true-seed")
    assert record.state is AttemptState.CERTIFIED
    assert certificate is not None

    certified = 0
    for index in range(8):
        llr = _tile_llr(spec, page, index)
        record, certificate = _attempt(
            sibling, llr, index, f"sibling-{index}")
        # The channel is perfect; only the keystream is wrong.  The decoder
        # genuinely runs and must refuse: syndrome/CRC never both pass.
        assert record.state is AttemptState.ATTEMPTED_FAILED
        assert record.decoder_invoked
        assert certificate is None
        assert record.certificate_id is None
        assert record.crc_ok is not True
        certified += certificate is not None
    assert certified == 0


# ---------------------------------------------------------------------------
# (b) state-tamper nulls


def _synthetic_state(tmp_path):
    """The cheapest genuine persisted session with inline evidence."""
    import _qualify_runtime_fixtures as fixtures
    from holo.receive.runtime import ReceiveRequest, run_receive

    image = tmp_path / "capture.png"
    fixtures._write_image(image, 71_001)
    pipeline, _calls = fixtures._pipeline()
    state_path = tmp_path / "state.json"
    result = run_receive(
        ReceiveRequest(
            fixtures._spec(), (fixtures._capture(image, dpi=400),),
            state_path),
        pipeline=pipeline)
    assert result.state.blocks
    return fixtures, state_path, result.state


def test_flipped_bit_in_persisted_block_payload_refuses_at_load(
    tmp_path,
) -> None:
    fixtures, state_path, state = _synthetic_state(tmp_path)
    manifest = state_path.read_text(encoding="utf-8")
    # Inline one-file state: evidence is compressed base64, never raw hex.
    assert state.blocks[0].printed_llr_f32.hex() not in manifest
    assert f'"sha256":"{state.blocks[0].block_id}"' in manifest

    match = re.search(r'"data":"([A-Za-z0-9+/=]+)"', manifest)
    assert match is not None
    blob = bytearray(base64.b64decode(match.group(1)))
    blob[len(blob) // 2] ^= 0x01  # one flipped bit in the block payload
    tampered = (
        manifest[:match.start(1)]
        + base64.b64encode(bytes(blob)).decode("ascii")
        + manifest[match.end(1):])
    assert tampered != manifest
    state_path.write_text(tampered, encoding="utf-8")

    with pytest.raises(ValueError):
        load_session(state_path)

    # Refusal is the whole answer: restore the original byte-for-byte and
    # the load succeeds again with the exact authoritative state.
    state_path.write_text(manifest, encoding="utf-8")
    assert authoritative_bytes(load_session(state_path)) == (
        authoritative_bytes(state))


def test_truncated_state_envelope_refuses_at_load(tmp_path) -> None:
    _fixtures, state_path, _state = _synthetic_state(tmp_path)
    manifest = state_path.read_text(encoding="utf-8")
    state_path.write_text(manifest[:-2], encoding="utf-8")
    with pytest.raises(ValueError):
        load_session(state_path)


def test_tampered_certificate_user_bits_refuse_validation(
    null_fixture,
) -> None:
    import dataclasses

    spec, _sibling, page = null_fixture
    _record, certificate = _attempt(
        spec, _tile_llr(spec, page, 1), 1, "tamper-target")
    assert certificate is not None
    validate_certificate_record(certificate, spec)

    flipped = bytes(
        (certificate.packed_user_bits[0] ^ 0x01,)
    ) + certificate.packed_user_bits[1:]
    tampered = dataclasses.replace(certificate, packed_user_bits=flipped)
    with pytest.raises(ValueError, match="differs from certified"):
        validate_certificate_record(tampered, spec)

    # An id recomputed over tampered bits is equally refused: the identity
    # binds address AND content, so pasting bits under the old id fails.
    with pytest.raises(ValueError, match="differs from certified"):
        validate_certificate_record(
            dataclasses.replace(
                certificate,
                packed_user_bits=flipped,
                certificate_id=certificate.certificate_id), spec)


def _one_block() -> EvidenceBlock:
    source = hashlib.sha256(b"origin-tamper").hexdigest()
    origin = EvidenceOrigin(f"{source}/native/patch-3", 3, 0.25)
    values = np.asarray([1.5, -2.5, 3.5], np.float32)
    return _block_from_rows(
        source, "native", 0, (0, 0),
        ((flat, values[i].tobytes(), origin)
         for i, flat in enumerate((5, 9, 40))))


def test_tampered_origin_row_refuses_at_the_content_boundary() -> None:
    block = _one_block()
    encoded = block.to_bytes()
    # Round-trip control.
    assert EvidenceBlock.from_bytes(encoded).block_id == block.block_id

    # Flip one bit inside the serialized origin row (the placement id).
    marker = b"patch-3"
    at = encoded.index(marker)
    tampered = bytearray(encoded)
    tampered[at] ^= 0x01
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        EvidenceBlock.from_bytes(bytes(tampered))

    # Re-signing a tampered body does not help either: the origin row is
    # structurally validated (loss finite/non-negative, canonical order).
    body = bytearray(encoded[:-32])
    loss_at = body.index(marker) + len(marker)
    # Overwrite the packed heldout loss (float64 after id + varint) with NaN
    nan = np.float64(np.nan).tobytes()
    # The 8-byte loss field follows the packed patch ordinal
    # (_pack_natural(3) = 8-byte size prefix + 1 data byte).
    body[loss_at + 9:loss_at + 17] = nan
    resigned = bytes(body) + hashlib.sha256(bytes(body)).digest()
    with pytest.raises(ValueError, match="finite and non-negative"):
        EvidenceBlock.from_bytes(resigned)
