"""Typed receiver composition model.

Pure lane/close/schedule/pipeline contracts — the request, context,
output, and result shapes every receiver composition agrees on.
:mod:`holo.receive.runtime` executes these contracts; processors and
schedulers implement the protocols declared here.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable, Protocol, TypeAlias

import numpy as np

from holo.format.descriptor import FormatSpec

from .close_progress import CloseProgress
from .evidence_context import EvidenceContext
from .observer import (
    ReceiverQualificationStatus,
    validate_qualification as _validate_qualification,
)
from .scale_space import AreaPixelTransform
from .scan import Raster
from .session import (
    BarrierDelta,
    CaptureFacts,
    CaptureRecord,
    CaptureStatus,
    LevelRecord,
    SessionState,
    SessionStatus,
    authoritative_sha256,
    certificate_frontier_sha256,
)
from .types import (
    LANE_STAGES,
    AddressProduct,
    CaptureInput,
    CloseRecord,
    CloseStatus,
    Detail,
    Disposition,
    EventAuthority,
    LaneSpec,
    PayloadProduct,
    Stage,
    StageDecision,
    SurveyProduct,
)


class RasterView(Protocol):
    dpi: float
    shape: tuple[int, int]
    luma_max: float

    @property
    def source_sha256(self) -> str: ...

    @property
    def native_dtype(self) -> object: ...

    def crop_native(self, r0: int, r1: int, c0: int, c1: int) -> object: ...
    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> object: ...
@dataclass(frozen=True, slots=True)
class LaneRequest:
    spec: LaneSpec
    raster: RasterView = field(repr=False, compare=False)
@dataclass(frozen=True, slots=True)
class LaneContext:
    stage: Stage
    lane: LaneSpec
    spec: FormatSpec
    raster: RasterView = field(repr=False, compare=False)
    capture: CaptureFacts
    evidence: EvidenceContext
    _observer_enabled: Callable[[], bool] = field(repr=False, compare=False)
    _snapshots_enabled: Callable[[], bool] = field(repr=False, compare=False)
    _emit: Callable[..., None] = field(repr=False, compare=False)
    _isolate: Callable[[str, Callable[[], None]], None] = field(
        repr=False, compare=False)
    _defer_fountain_close: bool = field(
        default=False, repr=False, compare=False)

    def progress(self, name: str, *, message: str = "",
                 details: tuple[Detail, ...] = (),
                 snapshot_factory: Callable[[], object] | None = None) -> None:
        if any(row.name == "lane.id" for row in details):
            raise ValueError("lane.id is supplied by the runtime")
        self._emit(
            name, self.stage, capture_id=self.capture.source_sha256,
            message=message,
            details=(Detail("lane.id", self.lane.lane_id),) + details,
            snapshot_factory=snapshot_factory,
        )

    def observe(self, name: str, callback: Callable[[], None]) -> None:
        self._isolate(name, callback)

    @property
    def observer_enabled(self) -> bool:
        return bool(self._observer_enabled())

    @property
    def snapshots_enabled(self) -> bool:
        return bool(self._snapshots_enabled())

    @property
    def defer_fountain_close(self) -> bool:
        return bool(self._defer_fountain_close)

    @property
    def pixel_transform(self) -> AreaPixelTransform:
        """Exact native-source to current-lane pixel-centre transform."""
        return AreaPixelTransform(Fraction(
            self.lane.native_per_view_num,
            self.lane.native_per_view_den))

    def native_to_lane_points(self, points_yx: np.ndarray) -> np.ndarray:
        return self.pixel_transform.source_to_view_points(points_yx)

    def lane_to_native_points(self, points_yx: np.ndarray) -> np.ndarray:
        return self.pixel_transform.view_to_source_points(points_yx)

    def native_to_lane_affine(self, affine: np.ndarray) -> np.ndarray:
        """Convert a canonical page-cell->native affine for this lane."""
        return self.pixel_transform.source_to_view_affine(affine)

    def lane_to_native_affine(self, affine: np.ndarray) -> np.ndarray:
        """Canonicalize a page-cell->lane affine before persistence."""
        return self.pixel_transform.view_to_source_affine(affine)
@dataclass(frozen=True, slots=True)
class LaneStageOutput:
    decision: StageDecision
    product: SurveyProduct | AddressProduct | PayloadProduct | None = None
    replacement_address: AddressProduct | None = None

    def __post_init__(self) -> None:
        complete = self.decision.disposition is Disposition.COMPLETE
        if complete != (self.product is not None):
            raise ValueError("complete stage must return exactly one product")
        if self.replacement_address is not None:
            if (
                self.decision.stage is not Stage.PAYLOAD
                or not complete
                or not isinstance(self.product, PayloadProduct)
            ):
                raise ValueError(
                    "only a completed payload stage may replace address geometry"
                )
            if self.product.artifact.address_id != (
                self.replacement_address.artifact.address_id
            ):
                raise ValueError(
                    "replacement address differs from the payload dependency"
                )


def _component_policy_id(label: str, component: object) -> str:
    identity = getattr(component, "policy_id", None)
    if not isinstance(identity, str) or not identity:
        raise ValueError(
            f"receiver {label} component needs a stable policy id")
    return identity


class SurveyProcessor(Protocol):
    policy_id: str
    stage: Stage
    def process(self, context: LaneContext) -> LaneStageOutput: ...
class AddressProcessor(Protocol):
    policy_id: str
    stage: Stage
    def process(self, context: LaneContext,
                survey: SurveyProduct) -> LaneStageOutput: ...
class PayloadProcessor(Protocol):
    policy_id: str
    stage: Stage
    def process(self, context: LaneContext, survey: SurveyProduct,
                address: AddressProduct) -> LaneStageOutput: ...
@dataclass(frozen=True, slots=True)
class LaneAlgorithms:
    survey: SurveyProcessor
    address: AddressProcessor
    payload: PayloadProcessor

    def __post_init__(self) -> None:
        processors = (self.survey, self.address, self.payload)
        if tuple(getattr(row, "stage", None) for row in processors) != LANE_STAGES:
            raise ValueError("lane algorithms are not in causal order")
        if any(not callable(getattr(row, "process", None))
               for row in processors):
            raise TypeError("every lane algorithm must be callable")
        for label, processor in zip(
                ("survey", "address", "payload"), processors, strict=True):
            _component_policy_id(label, processor)
@dataclass(frozen=True, slots=True)
class LaneExecution:
    decisions: tuple[StageDecision, ...]
    survey: SurveyProduct | None = None
    address: AddressProduct | None = None
    payload: PayloadProduct | None = None

    def __post_init__(self) -> None:
        stages = tuple(row.stage for row in self.decisions)
        if not stages or stages != LANE_STAGES[:len(stages)]:
            raise ValueError("lane decisions are not a causal prefix")
        products = (self.survey, self.address, self.payload)
        for index, decision in enumerate(self.decisions):
            if (decision.disposition is Disposition.REFUSED
                    and index != len(self.decisions) - 1):
                raise ValueError("only the terminal stage may stop")
        expected_products = tuple(
            index < len(self.decisions)
            and self.decisions[index].disposition is Disposition.COMPLETE
            for index in range(len(products))
        )
        if tuple(product is not None for product in products) != expected_products:
            raise ValueError(
                "lane products must exactly match completed stage decisions")
        if self.disposition is Disposition.COMPLETE:
            if stages != LANE_STAGES:
                raise ValueError("complete lane lacks payload product")

    @property
    def disposition(self) -> Disposition:
        return self.decisions[-1].disposition

    def durable(self) -> tuple[LevelRecord, BarrierDelta]:
        """Materialize a terminal level record and its exact typed delta."""
        level = LevelRecord(
            survey=None if self.survey is None else self.survey.artifact,
            address=None if self.address is None else self.address.artifact,
            payload=None if self.payload is None else self.payload.artifact,
        )
        delta = BarrierDelta(
            regions=() if self.survey is None else self.survey.regions,
            poses=() if self.address is None else self.address.poses,
            proposals=() if self.address is None else self.address.proposals,
            losers=() if self.address is None else self.address.losers,
            parked=() if self.address is None else self.address.parked,
            blocks=() if self.payload is None else self.payload.blocks,
            attempts=() if self.payload is None else self.payload.attempts,
            certificates=(() if self.payload is None
                          else self.payload.certificates),
            divergences=(() if self.payload is None
                         else self.payload.divergences),
            mopup_dropped_observations=(
                0 if self.payload is None
                else self.payload.mopup_dropped_observations),
            mopup_winner_flips=(
                0 if self.payload is None
                else self.payload.mopup_winner_flips),
        )
        return level, delta


class CloseProcessor(Protocol):
    policy_id: str
    def process(self, context: "CloseContext") -> "CloseExecution": ...


@dataclass(frozen=True, slots=True)
class CloseContext:
    spec: FormatSpec
    state: SessionState

    @property
    def certificate_frontier_sha256(self) -> str:
        return certificate_frontier_sha256(self.state.certificates)


@dataclass(frozen=True, slots=True)
class CloseExecution:
    """Durable close identity plus transient verified payload bytes."""

    record: CloseRecord
    payload: bytes | None = None
    progress_factory: Callable[[], CloseProgress] | None = field(
        default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.record.status is CloseStatus.VERIFIED:
            if not isinstance(self.payload, bytes):
                raise ValueError("verified close must return transient payload")
            if (len(self.payload) != self.record.payload_length
                    or hashlib.sha256(self.payload).hexdigest()
                    != self.record.payload_sha256):
                raise ValueError("transient payload differs from close identity")
        elif self.payload is not None:
            raise ValueError("only verified close may return payload bytes")
        if self.progress_factory is not None and not callable(
                self.progress_factory):
            raise TypeError("close progress factory must be callable")

    def diagnostic_progress(self) -> CloseProgress | None:
        if self.progress_factory is None:
            return None
        progress = self.progress_factory()
        if type(progress) is not CloseProgress:
            raise TypeError("close progress factory returned a foreign value")
        return progress

LaneRunner: TypeAlias = Callable[[LaneRequest, EvidenceContext], LaneExecution]
BarrierCommit: TypeAlias = Callable[[LevelRecord, BarrierDelta], SessionState]
EvidenceBuilder: TypeAlias = Callable[[LaneSpec], EvidenceContext]


@dataclass(frozen=True, slots=True)
class ScheduleContext:
    spec: FormatSpec
    native: Raster = field(repr=False, compare=False)
    facts: CaptureFacts
    existing_capture: CaptureRecord | None
    run_lane: LaneRunner = field(repr=False, compare=False)
    evidence_for: EvidenceBuilder = field(repr=False, compare=False)
    commit: BarrierCommit = field(repr=False, compare=False)
    _emit: Callable[..., None] = field(repr=False, compare=False)
    _stop_requested: Callable[[], bool] = field(repr=False, compare=False)

    def progress(self, name: str, *, message: str = "",
                 details: tuple[Detail, ...] = (),
                 authority: EventAuthority = EventAuthority.TRANSIENT,
                 snapshot_factory: Callable[[], object] | None = None) -> None:
        self._emit(name, Stage.SCHEDULE,
                   capture_id=self.facts.source_sha256,
                   message=message, details=details, authority=authority,
                   snapshot_factory=snapshot_factory)

    @property
    def stop_requested(self) -> bool:
        return bool(self._stop_requested())


class MultiresScheduler(Protocol):
    policy_id: str
    def process(self, context: ScheduleContext) -> None: ...


_SEMANTIC_COMPONENT_LABELS = (
    "survey", "address", "payload", "scheduler", "close",
)
_SEMANTIC_POLICY_PREFIX = "holo/track3/kiss-v1/"


def _semantic_pipeline_policy_id(
    components: tuple[tuple[str, str], ...],
) -> str:
    """Content identity for one complete receiver composition."""
    if tuple(label for label, _identity in components) != (
            _SEMANTIC_COMPONENT_LABELS):
        raise ValueError("receiver semantic components are incomplete")
    if any(not isinstance(identity, str) or not identity
           for _label, identity in components):
        raise ValueError("receiver semantic component id must be non-empty")
    # Readable composition, no hash (G2): the state records exactly which
    # semantic components produced it, and a human can read the answer.
    joined = ";".join(f"{label}={identity}" for label, identity in components)
    return f"{_SEMANTIC_POLICY_PREFIX}{joined}"


def parse_pipeline_policy_id(policy_id: str) -> dict[str, str]:
    """The exact inverse of :func:`_semantic_pipeline_policy_id`.

    "Readable composition, no hash" is only worth its width if something
    reads it: :func:`session.policy_detach` decides what one archived
    state owes today by comparing the five component identities, never
    the joined string.  Total round trip or refusal — a foreign, hashed
    or truncated id raises instead of yielding a partial parse, because a
    detach that cannot classify the change cannot be safe.
    """
    if (not isinstance(policy_id, str)
            or not policy_id.startswith(_SEMANTIC_POLICY_PREFIX)):
        raise ValueError(
            "receiver policy id is not a kiss-v1 semantic composition")
    components: dict[str, str] = {}
    for chunk in policy_id[len(_SEMANTIC_POLICY_PREFIX):].split(";"):
        label, separator, identity = chunk.partition("=")
        if not separator or not identity or label in components:
            raise ValueError(
                "receiver policy id has an unreadable component "
                f"{chunk[:40]!r}")
        components[label] = identity
    if tuple(components) != _SEMANTIC_COMPONENT_LABELS:
        raise ValueError(
            "receiver policy id does not name exactly the five semantic "
            f"components in order: {tuple(components)}")
    return components


@dataclass(frozen=True, slots=True)
class ReceivePipeline:
    lanes: LaneAlgorithms
    scheduler: MultiresScheduler
    close: CloseProcessor
    page_hypotheses: tuple[int, ...] | None = None
    qualification_status: ReceiverQualificationStatus = field(kw_only=True)
    qualification_notes: tuple[str, ...] = field(
        default=(), kw_only=True)

    def __post_init__(self) -> None:
        _validate_qualification(
            self.qualification_status, self.qualification_notes)
        if not isinstance(self.lanes, LaneAlgorithms):
            raise TypeError("receive pipeline needs complete lane algorithms")
        if not callable(getattr(self.scheduler, "process", None)):
            raise TypeError("receive pipeline needs a scheduler")
        if not callable(getattr(self.close, "process", None)):
            raise TypeError("receive pipeline needs a close processor")
        if self.page_hypotheses is not None and (
                not self.page_hypotheses
                or any(type(page) is not int or page < 0
                       for page in self.page_hypotheses)
                or len(set(self.page_hypotheses))
                != len(self.page_hypotheses)):
            raise ValueError(
                "pipeline page hypotheses must be unique nonnegative ints")
        address = self.lanes.address
        address_pages = getattr(address, "page_hypotheses", None)
        if (hasattr(address, "page_hypotheses")
                and address_pages != self.page_hypotheses):
            raise ValueError(
                "pipeline page domain differs from its address processor")
        # Validate every identity now; ``policy_id`` remains a pure projection
        # and can never become stale after a dataclass replacement.
        _ = self.policy_id

    @property
    def policy_id(self) -> str:
        component_objects = (
            self.lanes.survey, self.lanes.address, self.lanes.payload,
            self.scheduler, self.close,
        )
        components = tuple(
            (label, _component_policy_id(label, component))
            for label, component in zip(
                _SEMANTIC_COMPONENT_LABELS,
                component_objects,
                strict=True,
            )
        )
        return _semantic_pipeline_policy_id(components)


@dataclass(frozen=True, slots=True)
class ReceiveRequest:
    """One receive invocation.

    ``run_mopup``/``run_refine`` (v0.42) are invocation-only scheduling
    flags — like ``defer_fountain_close`` they are absent from the
    semantic policy and every schema.  They select how far this
    invocation may drive each capture's plan prefix: default = the
    ordinary ladder only (stop before the first M entry); ``run_mopup``
    extends through the M-levels (stop before the first R entry);
    ``run_refine`` extends through everything — by the plan-prefix law
    this necessarily includes any pending M-levels.  Committed prefixes
    are always honored; a resume with different flags continues
    monotonically.
    """

    spec: FormatSpec
    captures: tuple[CaptureInput, ...]
    state_path: str | Path | None = None
    page_hypotheses: tuple[int, ...] | None = None
    defer_fountain_close: bool = False
    run_mopup: bool = False
    run_refine: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.spec, FormatSpec):
            raise TypeError("receive spec must be a FormatSpec")
        if not self.captures:
            raise ValueError("receive request needs at least one capture")
        if type(self.defer_fountain_close) is not bool:
            raise TypeError("defer_fountain_close must be bool")
        if type(self.run_mopup) is not bool:
            raise TypeError("run_mopup must be bool")
        if type(self.run_refine) is not bool:
            raise TypeError("run_refine must be bool")
        if self.page_hypotheses is not None:
            pages = tuple(dict.fromkeys(self.page_hypotheses))
            if (not pages or any(type(page) is not int
                                 or not 0 <= page < self.spec.max_pages
                                 for page in pages)):
                raise ValueError("page hypotheses must be unique legal pages")
            if pages != self.page_hypotheses:
                raise ValueError("page hypotheses must not repeat")


@dataclass(frozen=True, slots=True)
class CaptureRun:
    source_sha256: str
    status: CaptureStatus
    barriers_committed: int = 0
    state_changed: bool = False


@dataclass(frozen=True, slots=True)
class ReceiveResult:
    state: SessionState
    captures: tuple[CaptureRun, ...]
    state_changed: bool
    observer_failures: tuple[str, ...] = ()
    payload: bytes | None = None
    qualification_status: ReceiverQualificationStatus = field(kw_only=True)
    qualification_notes: tuple[str, ...] = field(
        default=(), kw_only=True)
    authoritative_digest: str | None = field(
        default=None, kw_only=True, repr=False, compare=False)
    close_progress_factory: Callable[[], "CloseProgress | None"] | None = field(
        default=None, kw_only=True, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_qualification(
            self.qualification_status, self.qualification_notes)
        if (self.close_progress_factory is not None
                and not callable(self.close_progress_factory)):
            raise TypeError("close progress factory must be callable")
        if (self.authoritative_digest is not None
                and (not isinstance(self.authoritative_digest, str)
                     or len(self.authoritative_digest) != 64
                     or any(char not in "0123456789abcdef"
                            for char in self.authoritative_digest))):
            raise ValueError("result authoritative digest must be SHA-256")

    @property
    def verified(self) -> bool:
        return self.state.status is SessionStatus.VERIFIED

    def close_progress(self) -> "CloseProgress | None":
        """Materialize the last live close's detached progress, if any.

        Presentation-only advice (requirement 8): counts and ranks are never
        a success condition, and durable state cannot reconstruct them.
        """
        if self.close_progress_factory is None:
            return None
        progress = self.close_progress_factory()
        if progress is not None and type(progress) is not CloseProgress:
            raise TypeError("close progress factory returned a foreign value")
        return progress

    @property
    def authoritative_sha256(self) -> str:
        return (self.authoritative_digest
                if self.authoritative_digest is not None
                else authoritative_sha256(self.state))
