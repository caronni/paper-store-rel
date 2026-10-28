"""Phase 3 (PAYLOAD-REWORK-PLAN 3.1/3.2/3.3, clause B) exactness pins.

Mint-once in the evidence-block family, the printed-field cache, the
certified-cascade empty-domain hoist, and the color preclose emptiness
short-circuit.  Each pin keeps the naive computation as a test-local
oracle and asserts byte-identity (the test_cold_search_exactness
precedent); tamper refusal at the durable load boundary is re-pinned
because the interior re-hash it used to shadow is gone.
"""
from __future__ import annotations

import base64
import hashlib
import zlib
from types import SimpleNamespace

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.format.registry import get_format_row
from holo.receive import (
    certified_cascade,
    production_color,
    state_codec,
    tiles,
)
from holo.receive.certified_refine import CertificateFrontier
from holo.receive.color_payload import ColorCaptureEvidence
from holo.receive.evidence_blocks import (
    EvidenceBlock,
    EvidenceOrigin,
    block_from_rows,
    tile_attempt_view,
)
from holo.receive.evidence_context import EvidenceContext
from holo.receive.payload_model import CaptureEvidence, EvidenceSource
from holo.receive.placement.model import AddressResult
from holo.receive.records import (
    certificate_divergence,
    certificate_record_from_user_bits,
    printed_cells_from_record,
)
from holo.receive.runtime import LaneContext
from holo.receive.scan import open_capture
from holo.receive.session import CaptureFacts
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    LaneSpec,
    Stage,
    SurveyArtifact,
    SurveyProduct,
)


LANE = "l00-2ppc-600dpi"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _origin(label: str) -> EvidenceOrigin:
    return EvidenceOrigin(f"{_sha(label)}/{LANE}/patch-0", 0, 0.125)


def _k_block(source: str, address=(0, 0, 0), flats=(3, 9, 40)):
    origin = _origin(source)
    return block_from_rows(
        source, LANE, address[0], address[1:],
        ((flat, np.asarray([1.5], np.float32), origin) for flat in flats),
        kind="k")


def _count_sha256(monkeypatch) -> list:
    calls: list = []
    real = hashlib.sha256

    def counting(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha256", counting)
    return calls


# --- 3.1: block digest minted once, identical via both paths --------------


def test_block_digest_minted_once_and_naive_oracle_identical(
        monkeypatch) -> None:
    source = _sha("mint-once-digest")
    origin = _origin(source)  # built outside the counting window
    rows = tuple(
        (flat, np.asarray([1.5], np.float32), origin) for flat in (3, 9, 40))
    calls = _count_sha256(monkeypatch)
    block = block_from_rows(source, LANE, 0, (0, 0), rows, kind="k")
    # ONE digest computation at the authoritative construction site
    # (the old shape hashed a second, rebuilt body in ``__post_init__``).
    assert len(calls) == 1
    # Naive oracle: an independent re-serialization of the stored fields
    # (``to_bytes`` rebuilds the body) hashes to the minted digest.
    encoded = block.to_bytes()
    assert hashlib.sha256(encoded[:-32]).digest() == block.content_sha256

    calls.clear()
    decoded = EvidenceBlock.from_bytes(encoded)
    # The durable boundary verifies ONCE and passes the digest through.
    assert len(calls) == 1
    assert decoded == block
    assert decoded.to_bytes() == encoded


def test_load_boundary_still_refuses_tamper() -> None:
    encoded = _k_block(_sha("tamper-boundary")).to_bytes()
    tampered = bytearray(encoded)
    tampered[len(encoded) // 2] ^= 1
    with pytest.raises(ValueError, match="content SHA-256"):
        EvidenceBlock.from_bytes(bytes(tampered))


def test_state_blob_load_single_sha_and_tamper_refusal(monkeypatch) -> None:
    """A3 collapse: one digest pass per inline blob at state load."""
    block = _k_block(_sha("state-blob-single-sha"))
    raw = block.to_bytes()

    def _inline(identity: str, data: bytes) -> dict:
        return {
            "sha256": identity,
            "size": len(data),
            "data": base64.b64encode(zlib.compress(data)).decode("ascii"),
        }

    annotation = tuple[EvidenceBlock, ...]
    calls = _count_sha256(monkeypatch)
    (decoded,) = state_codec._decode_blob_items(
        [_inline(block.block_id, raw)], annotation, "pin")
    assert len(calls) == 1  # from_bytes boundary only, no pre-hash
    assert decoded == block

    tampered = bytearray(raw)
    tampered[len(raw) // 2] ^= 1
    with pytest.raises(ValueError, match="inline blob is invalid"):
        state_codec._decode_blob_items(
            [_inline(block.block_id, bytes(tampered))], annotation, "pin")
    with pytest.raises(ValueError, match="content address changed"):
        state_codec._decode_blob_items(
            [_inline(_sha("wrong-manifest-identity"), raw)],
            annotation, "pin")


# --- 3.1: view component sum minted once, identical -----------------------


def test_view_sum_minted_once_and_naive_oracle_identical(monkeypatch) -> None:
    blocks = (
        _k_block(_sha("view-sum-a")),
        _k_block(_sha("view-sum-b"), flats=(3, 9, 41)),
    )
    naive = np.zeros((64, 64), np.float64)
    for row in blocks:
        naive += row.cell_tensor()

    calls: list = []
    real = EvidenceBlock.cell_tensor

    def counting(self):
        calls.append(self.block_id)
        return real(self)

    monkeypatch.setattr(EvidenceBlock, "cell_tensor", counting)
    view = tile_attempt_view(blocks)
    # Each component materializes its tensor ONCE (the old shape summed
    # again inside ``__post_init__`` for an equality check).
    assert sorted(calls) == sorted(row.block_id for row in blocks)
    assert view.llr_cells_f64.tobytes() == naive.tobytes()
    assert view.llr_cells_f64.dtype == naive.dtype
    assert view.llr_cells_f64.shape == naive.shape


# --- 3.2: printed-field mint-once cache -----------------------------------


def _fresh_certificate(spec, tile_yx, label: str):
    profile = spec.stream_profiles[0]
    rng = np.random.default_rng(
        int.from_bytes(hashlib.sha256(label.encode()).digest()[:4], "big"))
    return certificate_record_from_user_bits(
        spec,
        page=0,
        tile_yx=tile_yx,
        stream_id="main",
        user_bits=rng.integers(0, 2, profile.user_bits, dtype=np.uint8),
        origin_attempt_id=_sha(f"attempt-{label}"),
    )


def _naive_printed(spec, record) -> np.ndarray:
    """Test-local oracle: the pre-cache re-encode, computed fresh."""
    user = np.unpackbits(
        np.frombuffer(record.packed_user_bits, np.uint8),
        bitorder="little")[:spec.tile_user_bits]
    counter = spec.tile_counter(record.page, *record.tile_yx)
    a_t, b_t = tiles._slot_permutation(
        spec.seed, counter, spec.n_transmitted_slots)
    return tiles._reencode_printed_cells(
        spec, counter, record.page, *record.tile_yx, user, a_t, b_t)


def test_printed_field_cache_identity_and_once_per_certificate(
        monkeypatch) -> None:
    spec = make_spec("c3-r0550", "default")
    record = _fresh_certificate(spec, (0, 1), "printed-cache-pin")
    naive = _naive_printed(spec, record)

    calls: list = []
    real = tiles._reencode_printed_cells

    def counting(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(tiles, "_reencode_printed_cells", counting)
    first = printed_cells_from_record(record, spec)
    assert len(calls) == 1
    assert first.tobytes() == naive.tobytes()
    assert first.dtype == naive.dtype and first.shape == naive.shape
    second = printed_cells_from_record(record, spec)
    assert second is first  # the identical array, minted once
    assert len(calls) == 1
    with pytest.raises(ValueError):
        first[0, 0] = 1  # served read-only


def test_divergence_and_frontier_reencode_once_per_certificate(
        monkeypatch) -> None:
    spec = make_spec("c3-r0550", "default")
    record = _fresh_certificate(spec, (0, 2), "divergence-once-pin")
    naive = _naive_printed(spec, record)
    address = (0, 0, 2)
    flats = (3, 9, 40)
    blocks = tuple(
        _k_block(_sha(f"divergence-source-{index}"), address, flats)
        for index in range(3))

    calls: list = []
    real = tiles._reencode_printed_cells

    def counting(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(tiles, "_reencode_printed_cells", counting)
    rows = certificate_divergence(blocks, (record,), spec)
    # Once per CERTIFICATE, not once per (certificate, block) pair.
    assert len(calls) == 1
    assert len(rows) == 3
    # Naive per-pair oracle: LLR +1.5 reads printed=1; disagreements are
    # the printed-0 cells among the observed flats.
    expected_disagree = int(np.count_nonzero(
        naive.reshape(-1)[np.asarray(flats)] == 0))
    for row in rows:
        assert row.n_observed == len(flats)
        assert row.n_disagree == expected_disagree

    frontier = CertificateFrontier.from_certificates(spec, (record,))
    assert len(calls) == 1  # the eager frontier loop hits the same mint
    assert frontier.tiles[0].printed_cells.tobytes() == naive.astype(
        np.uint8).tobytes()


# --- 3.2: empty-promoted refinement builds no frontier --------------------


def test_refine_empty_promoted_builds_no_frontier(monkeypatch) -> None:
    spec = make_spec("c3-r0550", "default")
    record = _fresh_certificate(spec, (0, 3), "empty-promoted-pin")
    address = AddressResult((), (), (), (), 0)
    generation0 = CaptureEvidence(
        EvidenceSource(_sha("empty-promoted-capture"), LANE),
        spec.spec_id, (), (), ())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("empty-promoted lane built a frontier")

    monkeypatch.setattr(
        certified_cascade, "CertificateFrontier",
        SimpleNamespace(from_certificates=forbidden))
    result = certified_cascade.refine_address_once(
        None, address, generation0, spec, (record,))
    assert result.address is address
    assert result.summaries == ()
    assert result.patch_dependencies == ()


# --- 3.3: color preclose emptiness short-circuit --------------------------


def test_color_preclose_emptiness_short_circuits_conversion(
        monkeypatch) -> None:
    """A certificate-less color preclose converts NOTHING: the emptiness
    check now precedes ``certificate_for_close`` (the old shape converted
    the full prior-certificate set first)."""
    spec = get_format_row("c2-cmy7-p120-v0@3328x2304")
    source = _sha("color-preclose-empty")
    # A prior certificate at the block's address: the tile is already
    # fully certified, so no attempts run and the leaf mints nothing.
    prior = certificate_record_from_user_bits(
        spec,
        page=0,
        tile_yx=(0, 0),
        stream_id=spec.stream_ids[0],
        user_bits=np.zeros(spec.stream_profiles[0].user_bits, np.uint8),
        origin_attempt_id=_sha("color-preclose-prior-attempt"),
    )
    block = _color_block(spec, source)
    empty = ColorCaptureEvidence(
        EvidenceSource(source, LANE), spec.spec_id, block.kind, (), (), ())
    monkeypatch.setattr(
        production_color, "collect_color_evidence",
        lambda *_args, **_kwargs: empty)
    monkeypatch.setattr(
        production_color, "color_blocks_from_frontier",
        lambda *_args, **_kwargs: (block,))

    def forbidden(name):
        def raiser(*_args, **_kwargs):
            raise AssertionError(f"{name} consulted on an empty preclose")
        return raiser

    monkeypatch.setattr(
        production_color, "certificate_for_close",
        forbidden("certificate_for_close"))
    monkeypatch.setattr(
        production_color, "close_count_ready",
        forbidden("close_count_ready"))
    monkeypatch.setattr(
        production_color, "close_volume", forbidden("close_volume"))
    monkeypatch.setattr(
        production_color, "attempt_color_tile",
        forbidden("attempt_color_tile"))

    events: list = []
    raster = open_capture(np.zeros((2, 2, 3), np.uint8), 600.0)
    facts = CaptureFacts(
        source, raster.dpi, raster.source.dtype, raster.source.shape,
        raster.source.channels)
    context = LaneContext(
        Stage.PAYLOAD,
        LaneSpec(LANE, 2, 1, 1, 1),
        spec,
        raster,
        facts,
        EvidenceContext(certificates=(prior,)),
        lambda: True,
        lambda: False,
        lambda name, *_args, **kwargs: events.append(
            (name, kwargs.get("details", ()))),
        lambda _name, callback: callback(),
        False,
    )
    survey = SurveyProduct(SurveyArtifact("survey-empty", ()), ())
    address_state = AddressResult((), (), (), (), 0)
    address = AddressProduct(
        AddressArtifact("address-empty", "survey-empty", (), ()), (), (),
        transient=address_state)
    execution = production_color.ProductionColorPayload().process(
        context, survey, address)
    product = execution.product
    assert product is not None
    assert product.attempts == ()
    assert product.certificates == ()
    details = dict(
        (row.name, row.value)
        for name, rows in events if name == "payload.complete"
        for row in rows)
    assert details["color.preclose_attempted"] is False
    assert details["color.terminal_close"] is False


def _color_block(spec, source: str, address=(0, 0, 0)):
    from holo.format import pilots

    origin = _origin(source)
    payload_flats = pilots.color_payload_cell_indices(spec.family_seed)
    values = np.asarray((2.0, -1.0, 0.5, 1.5, -0.5, 0.25))
    return block_from_rows(
        source, LANE, address[0], address[1:],
        ((int(flat), values, origin) for flat in payload_flats),
        kind="cmy7")
