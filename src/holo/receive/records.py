"""Adapters between E023b numerical objects and compact durable records.

Durability ends at :class:`EvidenceBlock`: full sampled windows and per-cell
owner objects are transient calibration details. This module verifies that
every attempt still has its exact content-addressed components and vector.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .payload_model import DivergenceRecord

from ..format.descriptor import FormatSpec
from ..format.profiles import Family, StreamProfile
from . import tiles
from .tiles import CertificateConflict
from .evidence import (
    AttemptStage,
    AttemptState,
    TileAttemptRecord,
    TileCertificateRecord,
)
from .evidence_blocks import (
    EvidenceBlock,
    TileAttemptView,
    tile_attempt_view,
)
from .fountain_close import CertifiedStreamSymbol


def _unpack_user_bits(
    packed_user_bits: bytes,
    profile: StreamProfile,
) -> np.ndarray:
    if not isinstance(packed_user_bits, bytes):
        raise TypeError("packed_user_bits must be bytes")
    expected_bytes = (profile.user_bits + 7) // 8
    if len(packed_user_bits) != expected_bytes:
        raise ValueError("certificate packed user bits differ from stream")
    if profile.user_bits % 8 and (
            packed_user_bits[-1] >> (profile.user_bits % 8)):
        raise ValueError("certificate packed user-bit padding is nonzero")
    return np.unpackbits(
        np.frombuffer(packed_user_bits, np.uint8),
        bitorder="little",
    )[:profile.user_bits]


def _record_user_bits(
    record: TileCertificateRecord,
    spec: FormatSpec,
) -> np.ndarray:
    return _unpack_user_bits(
        record.packed_user_bits,
        spec.stream_profile(record.stream_id),
    )


def stream_certificate_identity(
    spec: FormatSpec,
    page: int,
    tile_yx: tuple[int, int],
    stream_id: str,
    packed_user_bits: bytes,
) -> str:
    """THE certificate identity, every codec (family unification 2026-07-30).

    Binds the exact format row, physical address, logical stream, FEC bank,
    bit count, and certified packed user bits.  The printed field is a
    deterministic function of these, so it adds nothing to the identity;
    where printed cells are consumed they are re-encoded and checked there.
    """
    profile = spec.stream_profile(stream_id)
    if type(page) is not int or page < 0:
        raise ValueError("certificate page must be a non-negative integer")
    if (not isinstance(tile_yx, tuple) or len(tile_yx) != 2
            or any(type(value) is not int or value < 0 for value in tile_yx)):
        raise ValueError("certificate tile coordinate is invalid")
    expected_counter = spec.tile_counter(page, *tile_yx)
    if spec.tile_address(expected_counter) != (page, *tile_yx):
        raise ValueError("certificate address lies outside the format")
    _unpack_user_bits(packed_user_bits, profile)
    return tiles.sha256_parts_be(
        b"e023c/stream-certificate/v1",
        spec.spec_id.encode("utf-8"),
        bytes(spec.seed),
        repr((page, *tile_yx)).encode("ascii"),
        stream_id.encode("ascii"),
        profile.fec.profile_id.encode("utf-8"),
        str(profile.user_bits).encode("ascii"),
        packed_user_bits,
    )


def stream_attempt_identity(
    spec: FormatSpec,
    address: tuple[int, int, int],
    stream_id: str,
    stage: AttemptStage,
    component_block_ids: tuple[str, ...],
    demap_iterations: int | None = None,
) -> str:
    """Derive the exact row/stage decoder identity for one stream attempt.

    ``demap_iterations`` names how many demap<->BP exchanges the CMY7 leaf
    was allowed inside this ONE attempt (color-uplift P3, RECEIVE-DESIGN
    §6.2a).  That count IS part of the decoder — a one-iteration attempt
    and a three-iteration attempt run different algorithms over the same
    evidence — so it belongs in the decoder id, and a force-null attempt
    can never collide with a live one.  This module stays environment-free:
    the caller reads ``color_attempts.effective_demap_iterations()`` and
    passes the value.  ``None`` (and every non-CMY7 codec) mints exactly
    the historical identity.
    """
    profile = spec.stream_profile(stream_id)
    max_iters = (
        tiles.RETRY_BP_MAX_ITERS
        if stage is AttemptStage.RETRY150
        else tiles.BASELINE_BP_MAX_ITERS
    )
    if spec.codec_family is Family.K:
        decoder_id = tiles.decoder_profile(
            spec.rate_id, max_iters, tiles.BP_ALPHA)
    else:
        decoder_id = (
            f"{profile.fec.profile_id}/decode_frame-max{max_iters}-"
            f"alpha{tiles.BP_ALPHA:g}"
        )
        if (demap_iterations is not None
                and spec.codec_family is Family.CMY7):
            decoder_id = f"{decoder_id}-demap{int(demap_iterations)}"
    return tiles.attempt_identity(
        address,
        stage.value,
        decoder_id,
        component_block_ids,
        stream_id=stream_id,
    )


def validate_attempt_record_identity(
    record: TileAttemptRecord,
    spec: FormatSpec,
    demap_iterations: int | None = None,
) -> None:
    expected = stream_attempt_identity(
        spec,
        (record.page, *record.tile_yx),
        record.stream_id,
        record.stage,
        record.component_block_ids,
        demap_iterations=demap_iterations,
    )
    if record.attempt_id != expected:
        raise ValueError("attempt id differs from its stream provenance")


def validate_certificate_record(
    record: TileCertificateRecord,
    spec: FormatSpec,
) -> None:
    """Validate row/stream width, address, padding, and content identity."""
    _record_user_bits(record, spec)
    counter = spec.tile_counter(record.page, *record.tile_yx)
    if spec.tile_address(counter) != (record.page, *record.tile_yx):
        raise ValueError("certificate address lies outside the format")
    expected = stream_certificate_identity(
        spec,
        record.page,
        record.tile_yx,
        record.stream_id,
        record.packed_user_bits,
    )
    if record.certificate_id != expected:
        raise ValueError("certificate id differs from certified stream bits")


def certificate_for_close(
    record: TileCertificateRecord,
    spec: FormatSpec,
) -> CertifiedStreamSymbol:
    """Reconstruct the exact close input from one durable certificate.

    One family, one shape: every codec closes over
    :class:`CertifiedStreamSymbol` (K/CMY7 on stream ``"main"``).
    """
    validate_certificate_record(record, spec)
    user = _record_user_bits(record, spec)
    return CertifiedStreamSymbol(
        counter=spec.tile_counter(record.page, *record.tile_yx),
        page=record.page,
        ty=record.tile_yx[0],
        tx=record.tile_yx[1],
        stream_id=record.stream_id,
        symbol=user[1:],
        metadata_bit=int(user[0]),
    )


def certificate_record_from_user_bits(
    spec: FormatSpec,
    *,
    page: int,
    tile_yx: tuple[int, int],
    stream_id: str,
    user_bits: np.ndarray,
    origin_attempt_id: str,
    dependency_certificate_ids: tuple[str, ...] = (),
) -> TileCertificateRecord:
    """Construct a content-addressed certificate record (every codec)."""
    profile = spec.stream_profile(stream_id)
    raw = np.asarray(user_bits)
    if raw.shape != (profile.user_bits,) or raw.dtype.kind not in "buif" \
            or not np.isfinite(raw).all() or not np.isin(raw, (0, 1)).all():
        raise ValueError(
            f"{stream_id} user_bits must be finite bits with shape "
            f"({profile.user_bits},)")
    packed = np.packbits(
        raw.astype(np.uint8, copy=False),
        bitorder="little",
    ).tobytes()
    identity = stream_certificate_identity(
        spec, page, tile_yx, stream_id, packed)
    return TileCertificateRecord(
        certificate_id=identity,
        page=page,
        tile_yx=tile_yx,
        packed_user_bits=packed,
        origin_attempt_id=origin_attempt_id,
        dependency_certificate_ids=dependency_certificate_ids,
        stream_id=stream_id,
    )


# Mint-once printed-field cache (rework Phase 3.2, refinement:06 +
# engine-records:04): the printed field is a pure function of the
# certificate identity (which binds spec_id, seed, address, stream, and the
# certified user bits), so each certificate LDPC-re-encodes at most once per
# process.  ~4 KB per certificate — negligible at the measured corpus scale.
_PRINTED_CELLS_CACHE: dict[str, np.ndarray] = {}


def printed_cells_from_record(
    record: TileCertificateRecord,
    spec: FormatSpec,
) -> np.ndarray:
    """Re-encode the complete printed 64x64 field from durable truth.

    The printed field (word/filler sites and page scramble included) is a
    pure function of the certified user bits and the address; consumers
    that compare against physical observations (divergence, certified
    refinement) derive it here on demand.  Minted once per certificate_id
    and served read-only thereafter (records immutable, content-addressed;
    validation runs at the mint).
    """
    cached = _PRINTED_CELLS_CACHE.get(record.certificate_id)
    if cached is not None:
        return cached
    if spec.codec_family is not Family.K or record.stream_id != "main":
        raise ValueError(
            "full printed-field reconstruction is the established K leaf")
    validate_certificate_record(record, spec)
    n_user_bits = spec.tile_user_bits
    user = np.unpackbits(
        np.frombuffer(record.packed_user_bits, np.uint8),
        bitorder="little")[:n_user_bits]
    counter = spec.tile_counter(
        record.page, record.tile_yx[0], record.tile_yx[1])
    a_t, b_t = tiles._slot_permutation(  # one internal receive boundary
        spec.seed, counter, spec.n_transmitted_slots)
    cells = tiles._reencode_printed_cells(
        spec, counter, record.page, *record.tile_yx, user, a_t, b_t)
    cells = np.frombuffer(  # immutable: every consumer shares one mint
        np.ascontiguousarray(cells).tobytes(), dtype=cells.dtype,
    ).reshape(cells.shape)
    _PRINTED_CELLS_CACHE[record.certificate_id] = cells
    return cells


class CertificateStore:
    """Stream-aware certified truth plus the invocation-local attempt ledger.

    One store serves every codec (family unification 2026-07-30): work is
    keyed by ``(page, ty, tx, stream_id)``; a certificate conflict is a
    differing ``packed_user_bits`` at one key and is fatal, never voted.
    Attempt history is invocation-local — resumes re-attempt uncertified
    streams and the CRC gates correctness.
    """

    def __init__(self, spec: FormatSpec) -> None:
        if not isinstance(spec, FormatSpec):
            raise TypeError("CertificateStore requires a FormatSpec")
        self._spec = spec
        self._streams = tuple(spec.stream_ids)
        self._certificates: dict[
            tuple[int, int, int, str], TileCertificateRecord] = {}
        self._attempts: list[TileAttemptRecord] = []
        self._attempt_ids: set[str] = set()

    @property
    def spec(self) -> FormatSpec:
        return self._spec

    def add(self, record: TileCertificateRecord) -> bool:
        """Store one certificate; True when new, False on an identical
        duplicate; CertificateConflict on differing certified content."""
        if not isinstance(record, TileCertificateRecord):
            raise TypeError("store accepts TileCertificateRecord only")
        validate_certificate_record(record, self._spec)
        previous = self._certificates.get(record.work_key)
        if previous is not None:
            if previous.packed_user_bits == record.packed_user_bits:
                return False
            raise CertificateConflict(
                f"conflicting certified content at {record.work_key} — "
                "mixed sheets or an upstream fault")
        self._certificates[record.work_key] = record
        return True

    def record_attempt(
        self,
        record: TileAttemptRecord,
        certificate: TileCertificateRecord | None,
    ) -> bool:
        """Record one evaluation; True only when a new certificate enters.

        Replaying an existing attempt id is a true no-op (the E023b
        collision scope); an attempt at an already-certified work key is
        refused before evaluation by the scheduler and ignored here.
        """
        if not isinstance(record, TileAttemptRecord):
            raise TypeError("store accepts TileAttemptRecord only")
        if (certificate is None) != (record.certificate_id is None):
            raise ValueError("attempt record and certificate disagree")
        if record.attempt_id in self._attempt_ids:
            return False
        if record.work_key in self._certificates:
            return False
        certified_new = False
        if certificate is not None:
            if certificate.certificate_id != record.certificate_id:
                raise ValueError("attempt names a different certificate")
            certified_new = self.add(certificate)
        self._attempts.append(record)
        self._attempt_ids.add(record.attempt_id)
        return certified_new

    def attempts(self) -> tuple[TileAttemptRecord, ...]:
        return tuple(self._attempts)

    def certificates(self) -> tuple[TileCertificateRecord, ...]:
        return tuple(
            row for _key, row in sorted(self._certificates.items()))

    def unresolved_streams(
        self, address: tuple[int, int, int]) -> tuple[str, ...]:
        return tuple(
            stream_id for stream_id in self._streams
            if (*address, stream_id) not in self._certificates)

    def __contains__(self, address: object) -> bool:
        """True when EVERY stream of this tile address is certified."""
        return not self.unresolved_streams(address)  # type: ignore[arg-type]

    def __len__(self) -> int:
        return len(self._certificates)




def certificate_divergence(
    blocks: "Iterable[EvidenceBlock]",
    certificates: Iterable[TileCertificateRecord],
    spec: FormatSpec,
) -> tuple[DivergenceRecord, ...]:
    """Audit compact observations against certified truth (non-gating).

    ONE pairing loop for every codec; the per-codec comparison kernel is
    the only branch (K: re-encoded printed field vs scalar LLR sign;
    CMY7/CMY8: certified color projection — a detector-side leaf).
    """
    from .payload_model import DivergenceRecord, divergence_identity

    rows = tuple(sorted(
        blocks,
        key=lambda row: (
            row.source_sha256, row.lane_id, row.address, row.block_id)))
    by_address: dict[tuple[int, int, int], list] = {}
    for block in rows:
        by_address.setdefault(block.address, []).append(block)
    if spec.codec_family is Family.K:
        def counts(block, record):
            printed = printed_cells_from_record(record, spec)
            flat = block.observed_flat().astype(np.int64, copy=False)
            expected = printed.reshape(-1)[flat].astype(bool, copy=False)
            observed = block.printed_llr() > 0.0
            return int(flat.size), int(
                np.count_nonzero(observed != expected))
    else:
        from .color_divergence import color_divergence_counts

        def counts(block, record):
            return color_divergence_counts(block, record, spec)
    ordered = tuple(sorted(
        certificates,
        key=lambda row: (*row.work_key, row.certificate_id)))
    prior: set[str] = set()
    output: list = []
    for record in ordered:
        address = (record.page, *record.tile_yx)
        for block in by_address.get(address, ()):
            identity = divergence_identity(
                record.certificate_id, block.block_id)
            if identity in prior:
                continue
            n_observed, n_disagree = counts(block, record)
            output.append(DivergenceRecord(
                identity, record.certificate_id, block.block_id,
                n_observed, n_disagree))
            prior.add(identity)
    return tuple(output)


def restore_store(
    spec: FormatSpec,
    certificates: "Iterable[TileCertificateRecord]",
) -> CertificateStore:
    """Rebuild the store from durable certificates alone (kiss).

    Attempt history is not persisted; a resumed lane simply re-attempts
    its uncertified streams (recompute over ledger — CRC gates correctness).
    """
    store = CertificateStore(spec)
    for row in certificates:
        store.add(row)
    return store


__all__ = [
    "CertificateConflict", "CertificateStore",
    "printed_cells_from_record",
    "certificate_divergence",
    "certificate_for_close", "certificate_record_from_user_bits",
    "restore_store", "stream_attempt_identity",
    "stream_certificate_identity",
    "validate_attempt_record_identity", "validate_certificate_record",
]
