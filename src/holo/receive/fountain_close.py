"""Receiver back end, stage 2: certified tiles -> verified payload bytes.

RECEIVE-DESIGN §2.9. Pure: certificates in, bytes out.

    certified metadata bits -> the 24-bit word -> K
      -> fountain-v2 decode (ESI = tile counter), PER-BLOCK
      -> envelope unwrap
      -> VERIFIED STOP: sha256(data[0:len]) must match the header.

Two doctrines are load-bearing here:

* THE STOP IS THE SHA, NEVER A COUNT (HOLO-DESIGN §7.1). Rank, symbol
  counts and block status are diagnostics and scheduling advice; they
  never declare success. A stream that solves but fails its digest
  yields payload=None / verified=False — a failed volume, never a
  partial one, and never bytes handed onward.
* ALL ACCOUNTING IS PER BLOCK (fountain-v2, §7.2). The promise is per
  block, so ``CloseResult`` reports exact per-block rank shortfalls; a
  global symbol count is duplicate-gameable (measured, F6) and would call a
  volume finished while one block still lacks rank.

Certified equations that DISAGREE are integrity-fatal, never voted
(HOLO-DESIGN §6.2/§6.3): every side carries a CRC-32 certificate, so an
inconsistent system is mixed sheets or an upstream fault, not noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Iterable, Literal

import numpy as np

from ..core import fountain
from ..format import envelope, metadata, streamset
from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from .close_progress import (
    CloseBlockProgress, CloseMetadataProgress, CloseProgress,
    CloseSurplusInconsistency)
from .tiles import CertificateConflict
from .types import CloseRecord, CloseStatus as DurableCloseStatus

SUPPORTED_METADATA_VERSIONS = frozenset({0})


class MetadataIntegrityError(ValueError):
    """Certified metadata equations disagree -- mixed sheets or a fault."""

    def __init__(self, message: str, diagnostics: dict) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


@dataclass(frozen=True, eq=False, slots=True)
class CertifiedStreamSymbol:
    """THE certified value consumed by metadata/fountain close (every codec).

    Reconstructed from a content-addressed :class:`TileCertificateRecord`
    by :func:`~holo.receive.records.certificate_for_close`; the record's
    re-encode integrity gate runs there.  The physical tile is shared,
    while ``stream_id`` selects its independent certified metadata/symbol
    equation (K/CMY7 use ``"main"``).
    """

    counter: int
    page: int
    ty: int
    tx: int
    stream_id: str
    symbol: np.ndarray
    metadata_bit: int

    def __post_init__(self) -> None:
        integers = (
            ("counter", self.counter),
            ("page", self.page),
            ("ty", self.ty),
            ("tx", self.tx),
            ("metadata_bit", self.metadata_bit),
        )
        for label, value in integers:
            if isinstance(value, (bool, np.bool_)) or not isinstance(
                    value, (int, np.integer)):
                raise TypeError(f"{label} must be an integer")
            if int(value) < 0:
                raise ValueError(f"{label} must be non-negative")
            object.__setattr__(self, label, int(value))
        if self.metadata_bit not in (0, 1):
            raise ValueError("metadata_bit must be 0 or 1")
        if not isinstance(self.stream_id, str) or not self.stream_id:
            raise ValueError("stream_id must be a non-empty string")
        raw = np.asarray(self.symbol)
        if raw.ndim != 1 or raw.dtype.kind not in "buif" \
                or not np.isfinite(raw).all() \
                or not np.isin(raw, (0, 1)).all():
            raise ValueError("symbol must be a finite one-dimensional bit vector")
        packed = np.ascontiguousarray(raw, dtype=np.uint8).tobytes()
        object.__setattr__(
            self, "symbol",
            np.frombuffer(packed, dtype=np.uint8),
        )



def _validate_close_certificate(
    cert: object,
    spec: FormatSpec,
    *,
    require_symbol: bool,
) -> None:
    """Bind one certified stream symbol to ``spec`` (one family, one shape)."""
    if not isinstance(cert, CertifiedStreamSymbol):
        raise TypeError("close consumes CertifiedStreamSymbol only")
    stream_id = cert.stream_id
    profile = spec.stream_profile(stream_id)
    expected = spec.tile_counter(cert.page, cert.ty, cert.tx)
    if cert.counter != expected:
        raise ValueError(
            f"certificate counter {cert.counter} addresses another tile")
    if require_symbol and cert.symbol.shape != (profile.symbol_bits,):
        raise ValueError(
            f"{stream_id} certificate symbol has shape "
            f"{cert.symbol.shape}, expected ({profile.symbol_bits},)")


# --------------------------------------------------------------- metadata

def metadata_from_certificates(certs: Iterable[CertifiedStreamSymbol],
                               spec: FormatSpec
                               ) -> tuple[int | None, int | None, dict]:
    """(version, k_total, diagnostics) from the certified metadata bits.

    Each tile donates one addressed GF(2) equation selected by its full tile
    counter. Equations are CRC-certified, so an inconsistent system raises
    :class:`MetadataIntegrityError`; certified evidence is never out-voted.

    Returns (None, None, diagnostics) when the word is incomplete,
    malformed, or names an unsupported payload interpretation.  The
    one-bit metadata field can represent versions 0 and 1, but this receiver
    implements fountain-v2 version 0 only; accepting a structurally valid
    future version through today's decoder would silently reinterpret data.
    """
    observations: list[tuple[int, int]] = []
    n_certs = 0
    by_stream = (
        None
        if spec.codec_family is Family.K
        else {stream_id: 0 for stream_id in spec.stream_ids}
    )
    pooled = spec.pooled_fountain
    stream_index = (
        {stream_id: index
         for index, stream_id in enumerate(spec.stream_ids)}
        if pooled else None
    )
    # The metadata channel consumes only the certified counter and bit
    # (records were validated where they were reconstructed); the strict
    # symbol-shape gate belongs to the fountain consumers below.  Pooled
    # rows observe one DISTINCT equation per stream at
    # equation_index(counter, stream, n) (design §2.4); every other row
    # observes the counter's equation exactly as before.
    for cert in certs:
        stream_id = cert.stream_id
        bit = int(cert.metadata_bit)
        if bit not in (0, 1):
            raise ValueError(f"metadata bit {bit} is not a bit")
        if pooled:
            assert stream_index is not None
            observations.append((
                metadata.equation_index(
                    cert.counter, stream_index[stream_id],
                    spec.n_streams),
                bit,
            ))
        else:
            observations.append((cert.counter, bit))
        n_certs += 1
        if by_stream is not None:
            by_stream[stream_id] += 1

    md = metadata.decode_metadata(
        observations,
        max_index=(metadata.max_equation_index(spec.n_streams)
                   if pooled else metadata.MAX_COUNTER))
    diag: dict = {
        "n_certificates": n_certs,
        "n_metadata_observations": md.n_observations,
        "n_unique_metadata_counters": md.n_unique_counters,
        "metadata_rank": md.rank,
        "metadata_rank_shortfall": md.rank_shortfall,
        "metadata_check_shortfall": md.check_shortfall,
        "metadata_inconsistent": md.inconsistent,
        "decoded_version": md.version,
        "decoded_k": md.k,
        "ok": False,
        "reason": md.reason,
        "state": "incomplete",
        "supported_versions": sorted(SUPPORTED_METADATA_VERSIONS),
    }
    if by_stream is not None:
        diag["n_certificates_by_stream"] = by_stream
    if md.inconsistent:
        diag["state"] = "integrity_failure"
        raise MetadataIntegrityError(
            md.reason or "metadata equations inconsistent", diag)
    if not md.ok:
        diag["state"] = (
            "incomplete" if md.rank_shortfall or md.check_shortfall
            else "malformed")
        return None, None, diag
    if md.version not in SUPPORTED_METADATA_VERSIONS:
        diag["reason"] = f"unsupported metadata version {md.version}"
        diag["state"] = "unsupported"
        return None, None, diag
    diag["ok"] = True
    diag["state"] = "ready"
    if pooled:
        # The 18-bit field carries k_meta on a pooled row; the fountain
        # consumers below work in symbol space (k_total = n * k_meta).
        diag["decoded_k_meta"] = md.k
        return md.version, spec.n_streams * md.k, diag
    return md.version, md.k, diag


def metadata_progress(certs: Iterable[CertifiedStreamSymbol],
                      spec: FormatSpec) -> CloseProgress:
    """The §10.4 deferred-close projection: K plus count-only block reach.

    K is the 18-bit field of the metadata word, recovered by the rank-24
    GF(2) solve above — it is a property of the certified LDPC metadata
    channel, not of the fountain solve, and is therefore known long before
    (and independently of) any close.  Block rows carry distinct-ESI counts
    from :func:`distinct_esi_block_counts`, which instantiates no decoder and
    generates no coefficient rows; ``rank`` is 0 and ``solved`` False because
    nothing computed them, and the returned progress carries
    ``count_only=True`` so every view reports them as deferred rather than
    as zero (the close snapshot's ``deferred_counts`` marking derives from
    this flag).

    Never authoritative, and never raising into the observer path: an
    integrity failure is reported as the inconsistent metadata state.
    """
    certs = tuple(certs)
    try:
        _version, k_total, diag = metadata_from_certificates(certs, spec)
    except MetadataIntegrityError as exc:
        diag = exc.diagnostics
        k_total = None
    blocks: tuple[CloseBlockProgress, ...] = ()
    if k_total is not None:
        if spec.pooled_fountain:
            # one pooled block space; rows carry no stream label
            blocks = tuple(
                CloseBlockProgress(block, needed, have, 0, False)
                for block, needed, have in pooled_distinct_esi_block_counts(
                    certs, spec, k_total))
        else:
            rows: list[CloseBlockProgress] = []
            for profile in spec.stream_profiles:
                stream_id = profile.stream_id
                counters = tuple(
                    cert.counter for cert in certs
                    if spec.codec_family is Family.K
                    or cert.stream_id == stream_id)
                rows.extend(
                    CloseBlockProgress(
                        block, needed, have, 0, False,
                        stream_id=(None if spec.codec_family is Family.K
                                   else stream_id))
                    for block, needed, have in distinct_esi_block_counts(
                        counters, spec, k_total, stream_id))
            blocks = tuple(rows)
    return CloseProgress(
        k_total, sum(row.have for row in blocks), blocks,
        CloseMetadataProgress(
            int(diag.get("metadata_rank", 0)),
            int(diag.get("metadata_rank_shortfall", metadata.METADATA_BITS)),
            int(diag.get("metadata_check_shortfall",
                         metadata.MIN_METADATA_EQUATIONS)),
            bool(diag.get("metadata_inconsistent", False)),
            int(diag.get("n_unique_metadata_counters", 0)),
        ),
        count_only=True,
    )


# ------------------------------------------------------------ volume close

CloseStatus = Literal["open", "verified", "integrity_failure",
                      "unsupported"]


@dataclass(frozen=True)
class CloseResult:
    status: CloseStatus
    payload: bytes | None
    k_total: int | None
    blocks: tuple[CloseBlockProgress, ...] = ()
    symbols_used: int = 0
    reason: str | None = None
    metadata_version: int | None = None
    diagnostics: dict = field(default_factory=dict)
    # D16 report-only post-solve surplus audit: certified symbols of
    # SOLVED blocks that disagree with re-encoding the solved sources.
    # Pure observation — never consulted by status, payload, or the
    # durable CloseRecord mapping below.
    surplus_inconsistencies: tuple[CloseSurplusInconsistency, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in ("open", "verified", "integrity_failure",
                               "unsupported"):
            raise ValueError(f"unknown close status {self.status!r}")
        if (self.status == "verified") != (self.payload is not None):
            raise ValueError("only a verified close result may carry payload")
        if any(type(row) is not CloseSurplusInconsistency
               for row in self.surplus_inconsistencies):
            raise TypeError("close result contains a foreign surplus entry")

    @property
    def verified(self) -> bool:
        return self.status == "verified"



def _build_decoder(certs: Iterable[CertifiedStreamSymbol], spec: FormatSpec,
                   k_total: int) -> tuple[fountain.Decoder, int]:
    """Decoder loaded with every certificate's symbol at ESI = counter.

    A conflicting value at one ESI raises fountain.FountainIntegrityError
    from inside add_symbol — the same fatal class as CertificateConflict,
    reached when certificates arrive from a caller that did not go
    through CertificateStore.
    """
    if len(spec.stream_profiles) != 1:
        raise ValueError("_build_decoder requires a one-stream format")
    profile = spec.stream_profiles[0]
    code = _volume_code(spec, profile.stream_id, k_total)
    dec = fountain.Decoder(code)
    n_used = 0
    for cert in certs:
        _validate_close_certificate(cert, spec, require_symbol=True)
        if cert.stream_id != profile.stream_id:
            raise ValueError("one-stream close received another stream")
        if dec.add_symbol(cert.counter, cert.symbol):
            n_used += 1
    return dec, n_used


def _build_stream_decoder(
    certs: Iterable[CertifiedStreamSymbol],
    spec: FormatSpec,
    k_total: int,
    stream_id: str,
) -> tuple[fountain.Decoder, int]:
    """One stream's decoder over already-validated certificates.

    :func:`close_volume` validates every certificate exactly once before
    building the per-stream decoders (a per-stream validation pass would
    re-validate each certificate once per stream — three times on CMY8).
    """
    code = _volume_code(spec, stream_id, k_total)
    dec = fountain.Decoder(code)
    n_used = 0
    for cert in certs:
        if cert.stream_id != stream_id:
            continue
        if dec.add_symbol(cert.counter, cert.symbol):
            n_used += 1
    return dec, n_used


def _volume_code(
    spec: FormatSpec,
    stream_id: str,
    k_total: int,
) -> fountain.VolumeCode:
    """Construct the one authoritative ESI-to-fountain-block mapping."""
    if spec.pooled_fountain:
        raise ValueError(
            "pooled rows have one stream-mixed code; use _pooled_volume_code")
    profile = spec.stream_profile(stream_id)
    color_args = (
        {}
        if spec.codec_family is Family.K
        else {
            "stream_id": stream_id,
            "fountain_aux": profile.fountain_aux,
        }
    )
    return fountain.VolumeCode(
        k_total,
        profile.symbol_bits,
        spec.seed,
        tiles_per_page=spec.tiles_per_page,
        **color_args,
    )


def _pooled_volume_code(spec: FormatSpec,
                        k_total: int) -> fountain.VolumeCode:
    """The one pooled ESI-to-block mapping of a -v1 row (design §2.1)."""
    return fountain.VolumeCode(
        k_total,
        spec.symbol_bits,
        spec.seed,
        tiles_per_page=spec.tiles_per_page,
        n_streams=spec.n_streams,
    )


def _pooled_esi(spec: FormatSpec, stream_index: dict[str, int],
                cert: CertifiedStreamSymbol) -> int:
    """esi = counter * n_streams + stream_idx (design §2.1)."""
    return cert.counter * spec.n_streams + stream_index[cert.stream_id]


def pooled_distinct_esi_block_counts(
    certs: Iterable[CertifiedStreamSymbol],
    spec: FormatSpec,
    k_total: int,
) -> tuple[tuple[int, int, int], ...]:
    """(block, needed, have) over the pooled symbol space, count-only.

    The pooled twin of :func:`distinct_esi_block_counts`: distinct
    (stream, counter) pairs map through the one pooled code; no decoder,
    no rank, no coefficient rows.
    """
    code = _pooled_volume_code(spec, k_total)
    stream_index = {
        stream_id: index
        for index, stream_id in enumerate(spec.stream_ids)
    }
    have = np.zeros(code.n_blocks, dtype=np.int64)
    for esi in {_pooled_esi(spec, stream_index, cert) for cert in certs}:
        block, _row = code.block_row_of(esi)
        have[block] += 1
    return tuple(
        (block, int(code.k_per_block[block]), int(have[block]))
        for block in range(code.n_blocks)
    )


def distinct_esi_block_counts(
    counters: Iterable[int],
    spec: FormatSpec,
    k_total: int,
    stream_id: str,
) -> tuple[tuple[int, int, int], ...]:
    """Return ``(block, needed, have)`` without decoder/rank/solve work.

    Distinct ESIs are assigned through :func:`_volume_code`, the receiver's
    sole authoritative ESI-to-block mapping.  This helper is intentionally
    count-only so deferred-close diagnostics cannot accidentally construct a
    decoder or generate fountain coefficient rows.
    """
    code = _volume_code(spec, stream_id, k_total)
    have = np.zeros(code.n_blocks, dtype=np.int64)
    for counter in set(counters):
        block, _row = code.block_row_of(int(counter))
        have[block] += 1
    return tuple(
        (block, int(code.k_per_block[block]), int(have[block]))
        for block in range(code.n_blocks)
    )


def close_count_status(
    certs: Iterable[CertifiedStreamSymbol],
    spec: FormatSpec,
) -> tuple[bool, dict[tuple[str, int], int] | None]:
    """(count-ready, per-(stream, block) distinct-ESI counts) in one pass.

    The v0.33 count gate's readiness verdict and, when metadata yields K,
    the exact distinct-ESI counts the D8 shortfall baseline compares
    against — computed together so one consult constructs at most ONE
    :class:`~holo.core.fountain.VolumeCode` per stream (the gate and the
    baseline previously each built their own).

    ``counts`` is ``None`` exactly on the metadata-no-K states: an
    inconsistent system (raising path), and the non-raising malformed /
    unsupported / incomplete forms.  All but ``incomplete`` are
    metadata-terminal and report ready=True so the caller consults —
    K is unknown there, so no block count exists and none may be built
    (a ``VolumeCode(None, ...)`` is a crash, never a gate).

    Readiness is a scheduling gate, never a stop condition: once metadata
    yields K, every stream must carry at least K distinct ESIs and every
    independently decoded block at least K_b.  Passing says nothing about
    generator rank or envelope SHA.
    """
    certs = tuple(certs)
    try:
        _version, k_total, diagnostics = metadata_from_certificates(
            certs, spec)
    except (CertificateConflict, MetadataIntegrityError):
        return True, None
    if k_total is None:
        return diagnostics["state"] != "incomplete", None

    ready = True
    counts: dict[tuple[str, int], int] = {}
    if spec.pooled_fountain:
        # one pooled block space; the baseline key names it "pooled"
        for block, needed, have in pooled_distinct_esi_block_counts(
                certs, spec, k_total):
            counts[("pooled", block)] = have
            if have < needed:
                ready = False
        return ready, counts
    for stream_id in spec.stream_ids:
        counters = {
            int(cert.counter)
            for cert in certs
            if cert.stream_id == stream_id
        }
        for block, needed, have in distinct_esi_block_counts(
                counters, spec, k_total, stream_id):
            counts[(stream_id, block)] = have
            if have < needed:
                ready = False
    return ready, counts


def close_count_ready(
    certs: Iterable[CertifiedStreamSymbol],
    spec: FormatSpec,
) -> bool:
    """Whether a full close can possibly become terminal by symbol count.

    This is a scheduling gate, never a stop condition.  Metadata terminal
    states deliberately return true so :func:`close_volume` can materialise
    their exact durable result.  See :func:`close_count_status` for the
    counting semantics; this is its readiness projection.
    """
    return close_count_status(certs, spec)[0]


def _block_statuses(
    dec: fountain.Decoder,
    stream_id: str | None = None,
) -> tuple[CloseBlockProgress, ...]:
    values = tuple(
        (
            int(row["block"]),
            int(row["needed"]),
            int(row["have"]),
            int(row["rank"]),
            bool(row["solved"]),
        )
        for row in dec.rank_status()
    )
    return tuple(
        CloseBlockProgress(*row, stream_id=stream_id) for row in values)


def _surplus_audit(
    audited_decoders: tuple[
        tuple[fountain.Decoder,
              dict[int, CertifiedStreamSymbol]], ...],
) -> tuple[CloseSurplusInconsistency, ...]:
    """D16 report-only surplus-consistency audit over SOLVED blocks.

    The payload GF(2) solve never checks dependent (surplus) equations,
    so a wrong certified symbol in a dependent row is silently masked
    and, in a pivot row, produces an unlocalized integrity failure.
    This re-encodes every certified symbol of every solved block from
    the solved source rows (the decoder owns the frozen row derivation)
    and names the disagreeing certificates.  Pivot rows re-encode
    consistent by construction, so every hit is surplus evidence; the
    systematic fast path's never-consulted repair symbols are covered.

    Each decoder arrives with its own decoder-ESI -> certificate map
    (counter for single-stream/-v0 codes; counter*n + stream for a
    pooled code), so the audit itself never rederives ESI conventions.

    PURE OBSERVATION: no solver state changes, no outcome authority, and
    a defect here may never alter a close — any failure reports nothing.
    """
    entries: list[CloseSurplusInconsistency] = []
    try:
        for dec, cert_of_esi in audited_decoders:
            for esi in dec.audit_solved_symbols():
                cert = cert_of_esi.get(esi)
                if cert is None:
                    continue
                entries.append(CloseSurplusInconsistency(
                    cert.stream_id, cert.counter,
                    cert.page, cert.ty, cert.tx))
    except Exception:
        # Zero-outcome-change constraint: the audit is advisory and must
        # never convert a decodable volume into an error.
        return ()
    return tuple(entries)


def close_volume(certs: Iterable[CertifiedStreamSymbol],
                 spec: FormatSpec) -> CloseResult:
    """Certified tiles -> verified payload bytes, or an honest failure."""
    certs = tuple(certs)
    try:
        version, k_total, diag = metadata_from_certificates(certs, spec)
    except (CertificateConflict, MetadataIntegrityError,
            fountain.FountainIntegrityError) as exc:
        diag = (dict(exc.diagnostics)
                if isinstance(exc, MetadataIntegrityError) else {})
        diag.update({
            "state": "integrity_failure", "phase": "metadata",
            "exception": type(exc).__name__, "reason": str(exc),
            "n_certificates": len(certs), "ok": False,
        })
        return CloseResult(
            status="integrity_failure", payload=None, k_total=None,
            reason=f"metadata integrity failure: {exc}", diagnostics=diag)
    if k_total is None:
        status: CloseStatus = (
            "open" if diag["state"] == "incomplete"
            else "unsupported" if diag["state"] == "unsupported"
            else "integrity_failure")
        return CloseResult(status=status, payload=None, k_total=None,
                           metadata_version=(
                               int(diag["decoded_version"])
                               if status == "unsupported"
                               and diag["decoded_version"] is not None
                               else None),
                           reason=f"metadata {diag['state']}: "
                                  f"{diag['reason']}",
                           diagnostics=diag)

    pooled_source: np.ndarray | None = None
    try:
        if spec.pooled_fountain:
            # ONE stream-mixed decoder (design §2.1); ESI = counter*n + s.
            for cert in certs:
                _validate_close_certificate(cert, spec, require_symbol=True)
            stream_index = {
                stream_id: index
                for index, stream_id in enumerate(spec.stream_ids)
            }
            code = _pooled_volume_code(spec, k_total)
            dec = fountain.Decoder(code)
            cert_of_esi: dict[int, CertifiedStreamSymbol] = {}
            n_used = 0
            for cert in certs:
                esi = _pooled_esi(spec, stream_index, cert)
                if dec.add_symbol(esi, cert.symbol):
                    n_used += 1
                cert_of_esi[esi] = cert
            pooled_source = dec.try_solve()
            blocks = _block_statuses(dec, None)
            solved_streams = ()          # pooled unwrap runs separately
            audited_decoders = ((dec, cert_of_esi),)
        elif len(spec.stream_profiles) == 1:
            dec, n_used = _build_decoder(certs, spec, k_total)
            source = dec.try_solve()
            blocks = _block_statuses(
                dec,
                None if spec.codec_family is Family.K
                else spec.stream_profiles[0].stream_id,
            )
            solved_streams = (
                () if source is None
                else ((spec.stream_profiles[0].stream_id, source),)
            )
            audited_decoders = ((
                dec, {cert.counter: cert for cert in certs}),)
        else:
            # Validate every certificate ONCE; the per-stream decoder
            # builders below only filter and load.
            for cert in certs:
                _validate_close_certificate(cert, spec, require_symbol=True)
            decoders = tuple(
                (
                    profile.stream_id,
                    *_build_stream_decoder(
                        certs, spec, k_total, profile.stream_id),
                )
                for profile in spec.stream_profiles
            )
            solved_rows = tuple(
                (stream_id, decoder.try_solve())
                for stream_id, decoder, _used in decoders
            )
            n_used = sum(used for _stream, _decoder, used in decoders)
            blocks = tuple(
                block
                for stream_id, decoder, _used in decoders
                for block in _block_statuses(decoder, stream_id)
            )
            solved_streams = tuple(
                (stream_id, source)
                for stream_id, source in solved_rows
                if source is not None
            )
            audited_decoders = tuple(
                (
                    decoder,
                    {cert.counter: cert for cert in certs
                     if cert.stream_id == stream_id},
                )
                for stream_id, decoder, _used in decoders
            )
    except (CertificateConflict, MetadataIntegrityError,
            fountain.FountainIntegrityError) as exc:
        failure_diag = dict(diag)
        failure_diag.update({
            "state": "integrity_failure", "phase": "fountain",
            "exception": type(exc).__name__, "reason": str(exc),
            "ok": False,
        })
        return CloseResult(
            status="integrity_failure", payload=None, k_total=k_total,
            metadata_version=version,
            reason=f"certified-symbol integrity failure: {exc}",
            diagnostics=failure_diag)
    surplus = _surplus_audit(audited_decoders)
    solved = (
        pooled_source is not None
        if spec.pooled_fountain
        else len(solved_streams) == len(spec.stream_profiles)
    )
    if not solved:
        short = sum(b.rank_shortfall for b in blocks)
        if spec.codec_family is Family.K or spec.pooled_fountain:
            # one code, one block space — no per-stream attribution
            return CloseResult(
                status="open", payload=None, k_total=k_total, blocks=blocks,
                symbols_used=n_used, metadata_version=version,
                reason=(
                    f"{len(tuple(b for b in blocks if not b.solved))} of "
                    f"{len(blocks)} blocks unsolved "
                    f"(at least {short} additional symbols required)"
                ),
                diagnostics=diag,
                surplus_inconsistencies=surplus,
            )
        unsolved_streams = tuple(
            stream_id for stream_id in spec.stream_ids
            if stream_id not in {row[0] for row in solved_streams}
        )
        return CloseResult(
            status="open", payload=None, k_total=k_total, blocks=blocks,
            symbols_used=n_used, metadata_version=version,
            reason=(f"{len(tuple(b for b in blocks if not b.solved))} of "
                    f"{len(blocks)} blocks unsolved "
                    f"(at least {short} additional symbols required; "
                    f"streams {unsolved_streams})"),
            diagnostics={**diag, "unsolved_streams": unsolved_streams},
            surplus_inconsistencies=surplus)

    if spec.pooled_fountain:
        assert pooled_source is not None
        layout = streamset.StreamSet(tuple(
            (profile.stream_id, profile.symbol_bits)
            for profile in spec.stream_profiles
        ))
        try:
            payload = streamset.pooled_unwrap_solved(
                pooled_source, layout, k_total // spec.n_streams)
        except streamset.StreamSetIntegrityError:
            payload = None
    elif len(spec.stream_profiles) == 1:
        src = solved_streams[0][1]
        stream = np.packbits(src.ravel()).tobytes()
        payload = envelope.try_unwrap(stream)
    else:
        layout = streamset.StreamSet(tuple(
            (profile.stream_id, profile.symbol_bits)
            for profile in spec.stream_profiles
        ))
        try:
            payload = streamset.unwrap_solved(
                solved_streams, layout, k_total)
        except streamset.StreamSetIntegrityError:
            payload = None
    if payload is None:
        # Rank was complete and every block solved, yet the digest fails:
        # the recovered stream is wrong (a CRC false accept, a mixed
        # volume, or a wrong K). Never a partial success, never returned.
        return CloseResult(
            status="integrity_failure", payload=None, k_total=k_total,
            blocks=blocks,
            symbols_used=n_used, metadata_version=version,
            reason="envelope verification failed (payload SHA-256 "
                   "mismatch or malformed header)",
            diagnostics=diag,
            surplus_inconsistencies=surplus)
    if spec.pooled_fountain:
        # pooled_unwrap_solved enforced the canonical minimal k_meta and
        # exact zero padding before returning bytes.
        canonical_k = k_total
        padding_nonzero = False
    elif len(spec.stream_profiles) == 1:
        canonical_k = envelope.source_symbol_count(
            len(payload), spec.stream_profiles[0].symbol_bits)
        padding_start = (envelope.OVERHEAD_BYTES + len(payload)) * 8
        padding_nonzero = bool(
            np.any(solved_streams[0][1].ravel()[padding_start:]))
    else:
        layout = streamset.StreamSet(tuple(
            (profile.stream_id, profile.symbol_bits)
            for profile in spec.stream_profiles
        ))
        canonical_k = streamset.source_symbol_count(len(payload), layout)
        # unwrap_solved already checked exact cross-stream padding.
        padding_nonzero = False
    if canonical_k != k_total or padding_nonzero:
        close_diag = {
            **diag,
            "canonical_k": canonical_k,
            "padding_nonzero": padding_nonzero,
        }
        reason = (
            f"metadata K {k_total} is noncanonical for envelope "
            f"(expected {canonical_k})"
            if canonical_k != k_total else
            "nonzero bits in canonical envelope padding")
        return CloseResult(
            status="integrity_failure", payload=None, k_total=k_total,
            blocks=blocks, symbols_used=n_used, metadata_version=version,
            reason=reason, diagnostics=close_diag,
            surplus_inconsistencies=surplus)
    return CloseResult(status="verified", payload=payload, k_total=k_total,
                       blocks=blocks, symbols_used=n_used,
                       metadata_version=version, diagnostics=diag,
                       surplus_inconsistencies=surplus)


def close_record_from_result(
    result: CloseResult,
    certificate_frontier_sha256: str | None,
) -> CloseRecord:
    """Map one numerical close result to its exact durable state record."""
    if result.status == "open":
        return CloseRecord()
    if certificate_frontier_sha256 is None:
        raise ValueError("terminal close needs its certificate frontier")
    if result.status == "verified":
        assert result.payload is not None
        return CloseRecord(
            DurableCloseStatus.VERIFIED,
            certificate_frontier_sha256,
            hashlib.sha256(result.payload).hexdigest(),
            len(result.payload),
            result.metadata_version,
            "",
        )
    if result.status == "unsupported":
        if result.metadata_version is None:
            raise RuntimeError("unsupported close omitted its version")
        return CloseRecord(
            DurableCloseStatus.UNSUPPORTED,
            certificate_frontier_sha256,
            metadata_version=result.metadata_version,
            reason=(
                result.reason or "unsupported payload interpretation"),
        )
    return CloseRecord(
        DurableCloseStatus.INTEGRITY_FAILURE,
        certificate_frontier_sha256,
        metadata_version=result.metadata_version,
        reason=result.reason or "certified evidence failed closure",
    )


__all__ = [
    "CertifiedStreamSymbol",
    "CloseResult",
    "MetadataIntegrityError",
    "close_count_ready",
    "close_count_status",
    "close_record_from_result",
    "close_volume",
    "distinct_esi_block_counts",
    "metadata_from_certificates",
    "pooled_distinct_esi_block_counts",
]
