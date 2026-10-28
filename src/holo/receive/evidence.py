"""Lean durable records for Track-3 payload evidence and certification.

Numerical payload observations live only in immutable content-addressed
``EvidenceBlock`` values.  The ledger deliberately does not retain sampled
windows, calibration arrays, scan points, or one Python object per cell.
E023b identities are the exact ordered content-addressed block tuples named
by each attempt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .evidence_blocks import EvidenceBlock
from .payload_model import DivergenceRecord


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _identity(label: str, value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")


def _sha256(label: str, value: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")


def _nonnegative(label: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _unique(label: str, values: tuple[str, ...], *, hashes: bool = False
            ) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    for value in values:
        _sha256(label, value) if hashes else _identity(label, value)


class AttemptState(str, Enum):
    BELOW_ATTEMPT_FLOOR = "below_attempt_floor"
    ATTEMPTED_FAILED = "attempted_failed"
    CERTIFIED = "certified"


class AttemptStage(str, Enum):
    SCAN = "scan"
    UNION = "union"
    RETRY150 = "retry150"


def certificate_work_index(
    rows: Iterable["TileCertificateRecord"],
) -> dict[tuple[int, int, int, str], str]:
    """Index certified work and fail closed on a same-stream contradiction."""
    output: dict[tuple[int, int, int, str], str] = {}
    for row in rows:
        if not isinstance(row, TileCertificateRecord):
            raise TypeError("certificate work index contains a foreign record")
        previous = output.setdefault(row.work_key, row.certificate_id)
        if previous != row.certificate_id:
            raise ValueError(
                "conflicting certificates for one tile stream")
    return output


@dataclass(frozen=True, slots=True)
class TileAttemptRecord:
    """Causal attempt facts at one physical-tile/logical-stream coordinate.

    ``stream_id`` is deliberately the final, defaulted field so the
    established K construction surface remains source-compatible.  Its
    persisted value is nevertheless authoritative: K and CMY7 use
    ``"main"`` while CMY8 uses ``"C"``, ``"M"``, or ``"Y"``.
    """

    attempt_id: str
    source_sha256: str
    lane_id: str
    page: int
    tile_yx: tuple[int, int]
    stage: AttemptStage
    state: AttemptState
    n_informative: int
    n_iters: int
    syndrome_ok: bool | None
    crc_ok: bool | None
    component_block_ids: tuple[str, ...]
    dependency_certificate_ids: tuple[str, ...]
    certificate_id: str | None = None
    stream_id: str = "main"
    child_outcomes: tuple[tuple[int, bool], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stage, AttemptStage):
            raise TypeError("attempt stage must be AttemptStage")
        if not isinstance(self.state, AttemptState):
            raise TypeError("attempt state must be AttemptState")
        for label, value in (("attempt id", self.attempt_id),
                             ("lane id", self.lane_id),
                             ("stream id", self.stream_id)):
            _identity(label, value)
        _sha256("attempt source SHA-256", self.source_sha256)
        for label, value in (("page", self.page),
                             ("n_informative", self.n_informative),
                             ("n_iters", self.n_iters)):
            _nonnegative(label, value)
        if (not isinstance(self.tile_yx, tuple) or len(self.tile_yx) != 2
                or any(type(value) is not int or value < 0
                       for value in self.tile_yx)):
            raise ValueError("tile coordinate must be non-negative integers")
        if any(value is not None and type(value) is not bool
               for value in (self.syndrome_ok, self.crc_ok)):
            raise ValueError("attempt flags must be booleans")
        if not isinstance(self.child_outcomes, tuple):
            raise TypeError("attempt child outcomes must be a tuple")
        for row in self.child_outcomes:
            if (not isinstance(row, tuple) or len(row) != 2
                    or type(row[0]) is not int or row[0] < 0
                    or type(row[1]) is not bool):
                raise ValueError(
                    "child outcomes must be (non-negative iterations, "
                    "syndrome boolean) pairs")
        if self.child_outcomes:
            if sum(row[0] for row in self.child_outcomes) != self.n_iters:
                raise ValueError(
                    "attempt iterations differ from child outcomes")
            if self.syndrome_ok is not all(
                    row[1] for row in self.child_outcomes):
                raise ValueError(
                    "attempt syndrome differs from child outcomes")
        _unique("attempt component block ids", self.component_block_ids,
                hashes=True)
        _unique("attempt dependency ids", self.dependency_certificate_ids,
                hashes=True)
        if not self.component_block_ids:
            raise ValueError(
                "attempt needs one exact block per physical acquisition")
        if (self.stage is AttemptStage.SCAN
                and len(self.component_block_ids) != 1):
            raise ValueError("scan attempt needs exactly one capture component")
        if (self.stage is AttemptStage.UNION
                and len(self.component_block_ids) < 2):
            raise ValueError("union attempt needs at least two capture components")
        if self.certificate_id is not None:
            _sha256("certificate id", self.certificate_id)
        if ((self.state is AttemptState.CERTIFIED)
                != (self.certificate_id is not None)):
            raise ValueError("attempt certificate/state disagree")
        if self.state is AttemptState.BELOW_ATTEMPT_FLOOR:
            valid = (not self.decoder_invoked and self.n_iters == 0
                     and self.syndrome_ok is None
                     and self.crc_ok is None)
        elif self.state is AttemptState.ATTEMPTED_FAILED:
            if self.syndrome_ok is False:
                # The established K decoder always evaluates and records CRC,
                # even when its syndrome fails.  The color frame decoder
                # stops before CRC when any child syndrome fails, and its
                # non-empty child ledger is the durable proof of that path.
                # PER PASS, since the CMY7 outer loop exists: what this
                # record carries is the FINAL pass's CRC state, so a
                # ``None`` here says that pass stopped at the syndrome —
                # not that the attempt never invoked the CRC (an iterated
                # attempt may have reached it on an earlier pass, bounded
                # by DEMAP_ITERATIONS; MEASUREMENTS §13.8).
                crc_failure_state = (
                    self.crc_ok is None
                    if self.child_outcomes
                    else type(self.crc_ok) is bool
                )
            else:
                crc_failure_state = self.crc_ok is False
            valid = (self.decoder_invoked
                     and self.syndrome_ok is not None
                     and crc_failure_state)
        else:
            valid = (self.decoder_invoked
                     and self.syndrome_ok is True and self.crc_ok is True)
        if not valid:
            raise ValueError(f"inconsistent {self.state.value} attempt")

    @property
    def decoder_invoked(self) -> bool:
        return self.state is not AttemptState.BELOW_ATTEMPT_FLOOR

    @property
    def work_key(self) -> tuple[int, int, int, str]:
        return (self.page, *self.tile_yx, self.stream_id)


@dataclass(frozen=True, slots=True)
class TileCertificateRecord:
    """Certified bits at one canonical physical-tile/logical-stream address.

    The flat counter and bit length derive from that address and the active
    format row; the minting attempt and dependency links remain provenance.
    """

    certificate_id: str
    page: int
    tile_yx: tuple[int, int]
    packed_user_bits: bytes
    origin_attempt_id: str
    dependency_certificate_ids: tuple[str, ...] = ()
    stream_id: str = "main"

    def __post_init__(self) -> None:
        _sha256("certificate id", self.certificate_id)
        _nonnegative("page", self.page)
        if (not isinstance(self.tile_yx, tuple) or len(self.tile_yx) != 2
                or any(type(value) is not int or value < 0
                       for value in self.tile_yx)):
            raise ValueError("tile coordinate must be non-negative integers")
        if (not isinstance(self.packed_user_bits, bytes)
                or not self.packed_user_bits):
            raise ValueError("certificate must contain packed user bits")
        _identity("origin attempt id", self.origin_attempt_id)
        _identity("stream id", self.stream_id)
        _unique("certificate dependency ids",
                self.dependency_certificate_ids, hashes=True)

    @property
    def work_key(self) -> tuple[int, int, int, str]:
        return (self.page, *self.tile_yx, self.stream_id)


@dataclass(frozen=True, slots=True)
class PayloadArtifact:
    """Barrier summary (kiss): certificates by id, the rest by count.

    Attempt and divergence ledgers are not persisted (recompute over
    ledger); evidence blocks are persisted only while their tile lacks a
    full certificate set, so id-lists here would dangle. Counts keep the
    barrier auditable without referential ceremony.
    """

    payload_id: str
    address_id: str
    certificate_ids: tuple[str, ...] = ()
    n_blocks: int = 0
    n_attempts: int = 0
    n_divergences: int = 0

    def __post_init__(self) -> None:
        _identity("payload id", self.payload_id)
        _identity("address id", self.address_id)
        _unique("certificate ids", self.certificate_ids)
        for label, value in (("block count", self.n_blocks),
                             ("attempt count", self.n_attempts),
                             ("divergence count", self.n_divergences)):
            _nonnegative(label, value)


@dataclass(frozen=True, slots=True)
class PayloadProduct:
    artifact: PayloadArtifact
    blocks: tuple[EvidenceBlock, ...]
    attempts: tuple[TileAttemptRecord, ...]
    certificates: tuple[TileCertificateRecord, ...] = ()
    divergences: tuple[DivergenceRecord, ...] = ()
    # D5 drop tally (2026-08-02 ruling, docs/CANARY-D5-DISAGREEMENTS.md):
    # mop-up observations dropped at committed cells (expected geometry)
    # and, among them, the winner flips — the two-view consistency
    # canary.  Folds into SessionCounters at the barrier; never gates.
    mopup_dropped_observations: int = 0
    mopup_winner_flips: int = 0

    def __post_init__(self) -> None:
        if (self.artifact.certificate_ids
                != tuple(value.certificate_id for value in self.certificates)
                or self.artifact.n_blocks != len(self.blocks)
                or self.artifact.n_attempts != len(self.attempts)
                or self.artifact.n_divergences != len(self.divergences)):
            raise ValueError("payload artifact does not name exactly its records")
        for label, value in (
                ("dropped-observation", self.mopup_dropped_observations),
                ("winner-flip", self.mopup_winner_flips)):
            if type(value) is not int or value < 0:
                raise ValueError(f"payload {label} count must be >= 0")
        if self.mopup_winner_flips > self.mopup_dropped_observations:
            raise ValueError(
                "payload winner flips cannot exceed dropped observations")


__all__ = [
    "AttemptStage", "AttemptState", "DivergenceRecord",
    "PayloadArtifact", "PayloadProduct",
    "TileAttemptRecord", "TileCertificateRecord", "certificate_work_index",
]
