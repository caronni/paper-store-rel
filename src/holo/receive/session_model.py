"""Durable receive-session state model.

Typed, validating records for the per-session ledger: capture facts and
level histories, the one-barrier delta shape, folded work counters, and
:class:`SessionState` itself.  Indexing, barrier validation, close
transitions, and persistence live in :mod:`holo.receive.session`.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .types import (
    LANE_STAGES,
    AddressArtifact,
    CloseRecord,
    Disposition,
    DivergenceRecord,
    EvidenceBlock,
    LaneSpec,
    LosingHypothesis,
    ParkedWindowRecord,
    PayloadArtifact,
    PoseProposal,
    PoseRecord,
    Stage,
    SurveyArtifact,
    SurveyRegionRecord,
    TileAttemptRecord,
    TileCertificateRecord,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_capture_facts(
    source_sha256: str,
    dpi: float,
    dtype_value: object,
    shape_yx: tuple[int, int],
    channels: int,
) -> None:
    if _SHA256_RE.fullmatch(source_sha256) is None:
        raise ValueError("capture source SHA is invalid")
    if (isinstance(dpi, bool) or not math.isfinite(dpi) or dpi <= 0):
        raise ValueError("capture dpi must be finite and positive")
    value = dtype_value
    if not isinstance(value, str) or not value:
        raise ValueError("capture dtype must be non-empty")
    try:
        dtype = np.dtype(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("capture dtype is invalid") from exc
    if (str(dtype) != value
            or not np.issubdtype(dtype, np.number)
            or np.issubdtype(dtype, np.complexfloating)
            or np.issubdtype(dtype, np.bool_)):
        raise ValueError("capture dtype must be canonical real numeric")
    if (len(shape_yx) != 2 or any(
            type(row) is not int or row < 1 for row in shape_yx)):
        raise ValueError("capture shape must contain positive integers")
    if type(channels) is not int or channels not in (1, 3):
        raise ValueError("capture channels must be 1 or 3")


class LevelStatus(str, Enum):
    COMPLETE = "complete"
    REFUSED = "refused"


class CaptureStatus(str, Enum):
    ACTIVE = "active"
    COMPLETE = "complete"


class SessionStatus(str, Enum):
    OPEN = "open"
    VERIFIED = "verified"
    INTEGRITY_FAILURE = "integrity_failure"
    UNSUPPORTED = "unsupported"


class CaptureConflictError(ValueError):
    """One authenticated source SHA was rebound to conflicting capture facts."""


@dataclass(frozen=True, slots=True)
class LevelRecord:
    survey: SurveyArtifact | None = None
    address: AddressArtifact | None = None
    payload: PayloadArtifact | None = None

    def __post_init__(self) -> None:
        if ((self.address is not None and self.survey is None)
                or (self.payload is not None and self.address is None)):
            raise ValueError("level artifacts must be a causal prefix")

    @property
    def stage_dispositions(
        self,
    ) -> tuple[tuple[Stage, Disposition], ...]:
        """Derive the operational stage view from the artifact prefix."""
        artifacts = (self.survey, self.address, self.payload)
        completed = sum(artifact is not None for artifact in artifacts)
        rows = tuple(
            (stage, Disposition.COMPLETE)
            for stage in LANE_STAGES[:completed]
        )
        if completed < len(LANE_STAGES):
            rows += ((LANE_STAGES[completed], Disposition.REFUSED),)
        return rows

    @property
    def status(self) -> LevelStatus:
        return (
            LevelStatus.COMPLETE
            if self.payload is not None
            else LevelStatus.REFUSED
        )


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    source_sha256: str
    dpi: float
    dtype: str
    shape_yx: tuple[int, int]
    channels: int
    plan: tuple[LaneSpec, ...]
    levels: tuple[LevelRecord, ...]

    def __post_init__(self) -> None:
        _validate_capture_facts(
            self.source_sha256, self.dpi, self.dtype,
            self.shape_yx, self.channels)
        if not self.plan:
            raise ValueError("a persisted capture needs a complete scale plan")
        lane_ids = tuple(row.lane_id for row in self.plan)
        if len(lane_ids) != len(set(lane_ids)):
            raise ValueError("capture scale plan has duplicate lane ids")
        for ordinal, lane in enumerate(self.plan):
            expected_parent = None if ordinal == 0 else self.plan[ordinal - 1].lane_id
            if lane.parent_lane_id != expected_parent:
                raise ValueError("scale plan must be one ordered parent chain")
        targets = tuple(
            row.mopup_of for row in self.plan if row.mopup_of is not None)
        if len(targets) != len(set(targets)):
            raise ValueError("one ordinary lane cannot have two mop-up lanes")
        refine_targets = tuple(
            row.refine_of for row in self.plan if row.refine_of is not None)
        if len(refine_targets) != len(set(refine_targets)):
            raise ValueError(
                "one ordinary lane cannot have two refinement lanes")
        # PK4.3: one ordinary lane MAY carry several supplemental lanes —
        # one per registered arm override — so the uniqueness key is the
        # (base, arm) pair, not the base alone.  Lane-id uniqueness above
        # already implies it; this states the intended invariant.
        uplift_targets = tuple(
            (row.uplift_of, row.arm_override) for row in self.plan
            if row.uplift_of is not None)
        if len(uplift_targets) != len(set(uplift_targets)):
            raise ValueError(
                "one ordinary lane cannot have two supplemental lanes for "
                "the same arm")
        for ordinal, lane in enumerate(self.plan):
            base = lane.mopup_of or lane.refine_of or lane.uplift_of
            if base is None:
                continue
            earlier_ordinary = {
                row.lane_id for row in self.plan[:ordinal]
                if row.mopup_of is None and row.refine_of is None
                and row.uplift_of is None
            }
            if base not in earlier_ordinary:
                raise ValueError(
                    "a mop-up, refinement or supplemental lane must follow "
                    "the ordinary lane it serves")
        if len(self.levels) > len(self.plan):
            raise ValueError("capture has more levels than its plan")
    @property
    def status(self) -> CaptureStatus:
        return (
            CaptureStatus.COMPLETE
            if len(self.levels) == len(self.plan)
            else CaptureStatus.ACTIVE
        )


@dataclass(frozen=True, slots=True)
class CaptureFacts:
    source_sha256: str
    dpi: float
    dtype: str
    shape_yx: tuple[int, int]
    channels: int

    def __post_init__(self) -> None:
        _validate_capture_facts(
            self.source_sha256, self.dpi, self.dtype,
            self.shape_yx, self.channels)

    def as_record(self, plan: tuple[LaneSpec, ...], level: LevelRecord
                  ) -> CaptureRecord:
        return CaptureRecord(
            self.source_sha256, self.dpi, self.dtype, self.shape_yx,
            self.channels, plan, (level,))


@dataclass(frozen=True, slots=True)
class BarrierDelta:
    regions: tuple[SurveyRegionRecord, ...] = ()
    poses: tuple[PoseRecord, ...] = ()
    proposals: tuple[PoseProposal, ...] = ()
    losers: tuple[LosingHypothesis, ...] = ()
    parked: tuple[ParkedWindowRecord, ...] = ()
    blocks: tuple[EvidenceBlock, ...] = ()
    attempts: tuple[TileAttemptRecord, ...] = ()
    certificates: tuple[TileCertificateRecord, ...] = ()
    divergences: tuple[DivergenceRecord, ...] = ()
    # D5 drop tally (2026-08-02 ruling, docs/CANARY-D5-DISAGREEMENTS.md):
    # mop-up observations dropped at committed cells by this barrier's
    # supersession pass, and the winner flips among them (the two-view
    # consistency canary).
    mopup_dropped_observations: int = 0
    mopup_winner_flips: int = 0


@dataclass(frozen=True, slots=True)
class StageTally:
    """Folded per-stage attempt counts (the persisted form of the ledger)."""

    evaluations: int = 0
    decoder_calls: int = 0
    bp_iterations: int = 0
    crc_ok: int = 0

    def __post_init__(self) -> None:
        for label in ("evaluations", "decoder_calls", "bp_iterations",
                      "crc_ok"):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise ValueError(f"stage tally {label} must be >= 0")

    def add(self, other: "StageTally") -> "StageTally":
        return StageTally(
            self.evaluations + other.evaluations,
            self.decoder_calls + other.decoder_calls,
            self.bp_iterations + other.bp_iterations,
            self.crc_ok + other.crc_ok)


@dataclass(frozen=True, slots=True)
class SessionCounters:
    """Durable work counters replacing the attempt/divergence ledgers."""

    scan: StageTally = StageTally()
    union: StageTally = StageTally()
    retry150: StageTally = StageTally()
    divergences: int = 0
    # D5 drop tally (2026-08-02 ruling, replacing the v0.36
    # byte-inequality canary; docs/CANARY-D5-DISAGREEMENTS.md): mop-up
    # observations dropped at committed cells (expected geometry) and
    # the winner flips among them (two-view consistency canary).
    # Advice only, never a gate; threshold doctrine post-08-04.
    mopup_dropped_observations: int = 0
    mopup_winner_flips: int = 0

    def __post_init__(self) -> None:
        if type(self.divergences) is not int or self.divergences < 0:
            raise ValueError("divergence count must be >= 0")
        for label, value in (
                ("dropped-observation", self.mopup_dropped_observations),
                ("winner-flip", self.mopup_winner_flips)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} count must be >= 0")
        if self.mopup_winner_flips > self.mopup_dropped_observations:
            raise ValueError(
                "winner flips cannot exceed dropped observations")

    def fold(
        self,
        attempts: tuple[TileAttemptRecord, ...],
        divergences: tuple[DivergenceRecord, ...],
        mopup_dropped_observations: int,
        mopup_winner_flips: int,
    ) -> "SessionCounters":
        for label, value in (
                ("dropped-observation", mopup_dropped_observations),
                ("winner-flip", mopup_winner_flips)):
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} fold must be >= 0")
        if mopup_winner_flips > mopup_dropped_observations:
            raise ValueError(
                "winner-flip fold cannot exceed dropped observations")
        deltas = {"scan": [0, 0, 0, 0], "union": [0, 0, 0, 0],
                  "retry150": [0, 0, 0, 0]}
        for row in attempts:
            tally = deltas[row.stage.value]
            tally[0] += 1
            tally[1] += int(row.decoder_invoked)
            tally[2] += row.n_iters
            tally[3] += int(row.crc_ok is True)
        return SessionCounters(
            self.scan.add(StageTally(*deltas["scan"])),
            self.union.add(StageTally(*deltas["union"])),
            self.retry150.add(StageTally(*deltas["retry150"])),
            self.divergences + len(divergences),
            self.mopup_dropped_observations + mopup_dropped_observations,
            self.mopup_winner_flips + mopup_winner_flips)

    @property
    def decoder_calls(self) -> int:
        return (self.scan.decoder_calls + self.union.decoder_calls
                + self.retry150.decoder_calls)


@dataclass(frozen=True, slots=True)
class SessionState:
    format_row_id: str
    receiver_policy_id: str
    page_hypotheses: tuple[int, ...] | None
    # Every receiver policy this session has previously run under, oldest
    # first (``session.policy_detach``, schema 26).  Wall-clock free: the
    # list order IS the sequence, and ``receiver_policy_id`` is the
    # current epoch.  The divergence audit and every counter apply per
    # epoch, so this is the record that says how many epochs there were.
    policy_lineage: tuple[str, ...] = ()
    captures: tuple[CaptureRecord, ...] = ()
    regions: tuple[SurveyRegionRecord, ...] = ()
    poses: tuple[PoseRecord, ...] = ()
    proposals: tuple[PoseProposal, ...] = ()
    losers: tuple[LosingHypothesis, ...] = ()
    parked: tuple[ParkedWindowRecord, ...] = ()
    blocks: tuple[EvidenceBlock, ...] = field(
        default=(), metadata={"blob_items": True})
    certificates: tuple[TileCertificateRecord, ...] = ()
    counters: SessionCounters = SessionCounters()
    close: CloseRecord = CloseRecord()

    def __post_init__(self) -> None:
        if not isinstance(self.format_row_id, str) or not self.format_row_id:
            raise ValueError("format_row_id must be non-empty")
        if (not isinstance(self.receiver_policy_id, str)
                or not self.receiver_policy_id):
            raise ValueError("receiver_policy_id must be non-empty")
        if any(not isinstance(row, str) or not row
               for row in self.policy_lineage):
            raise ValueError("policy lineage entries must be non-empty")
        if any(new == old for old, new in zip(
                self.policy_lineage, (*self.policy_lineage[1:],
                                      self.receiver_policy_id))):
            # A detach only ever appends the policy it is LEAVING, so no
            # two consecutive epochs can be the same id.  (A revert to an
            # older policy is legal and appends that id again — the
            # lineage is a history, not a set.)
            raise ValueError("policy lineage repeats a consecutive epoch")
        if self.page_hypotheses is not None:
            if (not self.page_hypotheses
                    or any(type(page) is not int or page < 0
                           for page in self.page_hypotheses)
                    or len(set(self.page_hypotheses))
                    != len(self.page_hypotheses)):
                raise ValueError(
                    "page_hypotheses must be unique non-negative ints"
                )
    @classmethod
    def create(
        cls,
        format_row_id: str,
        receiver_policy_id: str,
        page_hypotheses: tuple[int, ...] | None,
    ) -> "SessionState":
        return cls(
            format_row_id,
            receiver_policy_id,
            page_hypotheses,
        )

    @property
    def status(self) -> SessionStatus:
        return SessionStatus(self.close.status.value)

    def capture(self, source_sha256: str) -> CaptureRecord | None:
        return next((row for row in self.captures
                     if row.source_sha256 == source_sha256), None)
