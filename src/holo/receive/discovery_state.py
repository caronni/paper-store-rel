"""Durable receiver-wide format discovery state.

The exact-row receiver deliberately keeps format-specific evidence in a
single namespace.  Discovery therefore owns one root state containing
isolated exact-row branches instead of adding a format dimension to every
pose, observation, certificate, and close record.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

from ..format.layout import VALID_CELL_DOTS
from ..format.registry import get_format_row
from .placement.policy import PlacementDomainEnvelope
from .session import (
    CaptureFacts,
    CaptureStatus,
    SessionState,
    SessionStatus,
    validate_session,
)
from .state_codec import (
    authoritative_state_sha256,
    encode_typed,
    load_typed,
    load_typed_with_digest,
    save_typed,
    save_typed_with_digest,
)


DISCOVERY_MAGIC = "holo-receive-discovery"
DISCOVERY_SCHEMA_VERSION = 12   # nested SessionState policy lineage (v0.59)

# A discovery state IS a tuple of ordinary session branches, so a session
# field-set change is a discovery wire change too — and lifts the same
# additive way (``session.STATE_MIGRATIONS``, ``state_codec._migrated``).
DISCOVERY_MIGRATIONS = {
    11: lambda document: {
        **document,
        "branches": [{**branch, "policy_lineage": []}
                     for branch in document["branches"]],
    },
}


class DiscoveryStatus(str, Enum):
    OPEN = "open"
    VERIFIED = "verified"
    INTEGRITY_FAILURE = "integrity_failure"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class DiscoverySurvey:
    facts: CaptureFacts
    c_dots: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.facts, CaptureFacts):
            raise TypeError("discovery survey facts must be CaptureFacts")
        if self.c_dots is not None and self.c_dots not in VALID_CELL_DOTS:
            raise ValueError(
                f"discovery c must be one of {VALID_CELL_DOTS} or absent")


@dataclass(frozen=True, slots=True)
class DiscoveryState:
    discovery_policy_id: str
    requested_row_ids: tuple[str, ...]
    domain_envelope: PlacementDomainEnvelope
    branches: tuple[SessionState, ...]
    surveys: tuple[DiscoverySurvey, ...] = ()

    def __post_init__(self) -> None:
        if (not isinstance(self.discovery_policy_id, str)
                or not self.discovery_policy_id):
            raise ValueError("discovery policy id must be non-empty")
        candidate_row_ids = self.candidate_row_ids
        if (not candidate_row_ids
                or tuple(sorted(candidate_row_ids)) != candidate_row_ids
                or len(set(candidate_row_ids)) != len(candidate_row_ids)):
            raise ValueError(
                "candidate rows must be sorted, unique, and non-empty")
        if (not self.requested_row_ids
                or tuple(sorted(self.requested_row_ids))
                != self.requested_row_ids
                or len(set(self.requested_row_ids))
                != len(self.requested_row_ids)
                or not set(candidate_row_ids).issubset(
                    self.requested_row_ids)):
            raise ValueError(
                "requested rows must be canonical and contain active rows")
        if self.domain_envelope.row_ids != candidate_row_ids:
            raise ValueError("discovery domain names another candidate set")
        for row_id in self.requested_row_ids:
            get_format_row(row_id)
        survey_ids = tuple(row.facts.source_sha256 for row in self.surveys)
        if (len(set(survey_ids)) != len(survey_ids)
                or tuple(sorted(survey_ids)) != survey_ids):
            raise ValueError(
                "discovery surveys must be canonically ordered and unique")

    @classmethod
    def create(
        cls,
        discovery_policy_id: str,
        domain_envelope: PlacementDomainEnvelope,
        branches: tuple[SessionState, ...],
        *,
        requested_row_ids: tuple[str, ...] | None = None,
    ) -> "DiscoveryState":
        ordered = tuple(
            sorted(branches, key=lambda row: row.format_row_id))
        return cls(
            discovery_policy_id,
            (
                tuple(row.format_row_id for row in ordered)
                if requested_row_ids is None
                else tuple(sorted(requested_row_ids))
            ),
            domain_envelope,
            ordered,
        )

    @property
    def candidate_row_ids(self) -> tuple[str, ...]:
        return tuple(row.format_row_id for row in self.branches)

    def branch(self, row_id: str) -> SessionState:
        try:
            return next(
                row for row in self.branches
                if row.format_row_id == row_id
            )
        except StopIteration:
            raise KeyError(f"unknown discovery branch {row_id!r}") from None

    def survey(self, capture_id: str) -> DiscoverySurvey | None:
        return next((
            row for row in self.surveys
            if row.facts.source_sha256 == capture_id
        ), None)

    def candidate_complete(self, source_sha256: str, row_id: str) -> bool:
        branch = self.branch(row_id)
        survey = self.survey(source_sha256)
        capture = branch.capture(source_sha256)
        spec = get_format_row(row_id)
        return (
            (
                survey is not None
                and survey.c_dots is not None
                and survey.c_dots != spec.cell_dots
            )
            or branch.status is not SessionStatus.OPEN
            or (
                capture is not None
                and capture.status is CaptureStatus.COMPLETE
            )
        )

    @property
    def round_complete(self) -> bool:
        return all(
            self.candidate_complete(
                survey.facts.source_sha256,
                branch.format_row_id,
            )
            for survey in self.surveys
            for branch in self.branches
        )

    @property
    def selected_row_id(self) -> str | None:
        recognized = tuple(
            row.format_row_id for row in self.branches
            if row.certificates
        )
        return recognized[0] if len(recognized) == 1 else None

    @property
    def status(self) -> DiscoveryStatus:
        recognized = tuple(
            row for row in self.branches if row.certificates)
        if len(recognized) > 1:
            return DiscoveryStatus.INTEGRITY_FAILURE
        if len(recognized) == 1 and self.round_complete:
            return DiscoveryStatus(recognized[0].status.value)
        return DiscoveryStatus.OPEN

    @property
    def decoder_invocations(self) -> int:
        """Receiver-wide count across every isolated exact-row branch."""
        return sum(
            branch.counters.decoder_calls for branch in self.branches)

def validate_discovery(
    state: DiscoveryState,
    *,
    defer_fountain_validation: bool = False,
) -> None:
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    if not isinstance(state, DiscoveryState):
        raise TypeError("discovery state must be typed")

    for branch in state.branches:
        validate_session(
            branch,
            defer_fountain_validation=defer_fountain_validation,
        )
        spec = get_format_row(branch.format_row_id)
        pages = branch.page_hypotheses
        if pages is not None and (
                not pages
                or len(set(pages)) != len(pages)
                or any(type(page) is not int
                       or not 0 <= page < spec.max_pages for page in pages)
                or (len(pages) == spec.max_pages
                    and pages == tuple(range(spec.max_pages)))):
            raise ValueError(
                "discovery branch has a noncanonical page domain")
        for capture in branch.captures:
            survey = state.survey(capture.source_sha256)
            if survey is None:
                raise ValueError(
                    "discovery branch contains an unsurveyed capture")
            facts = survey.facts
            if (
                capture.source_sha256,
                capture.dpi,
                capture.dtype,
                capture.shape_yx,
                capture.channels,
            ) != (
                facts.source_sha256,
                facts.dpi,
                facts.dtype,
                facts.shape_yx,
                facts.channels,
            ):
                raise ValueError(
                    "discovery branch capture differs from root survey facts")
            if (survey.c_dots is not None
                    and survey.c_dots != spec.cell_dots):
                raise ValueError(
                    "discovery branch retained a capture excluded by "
                    "native survey c")


def authoritative_discovery_sha256(
    state: DiscoveryState,
    *,
    validate: bool = True,
    defer_fountain_validation: bool = False,
) -> str:
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    if validate:
        validate_discovery(
            state,
            defer_fountain_validation=defer_fountain_validation,
        )
    return authoritative_state_sha256(
        encode_typed(state),
        magic=DISCOVERY_MAGIC,
        schema=DISCOVERY_SCHEMA_VERSION,
    )


def save_discovery(
    path: str | Path,
    state: DiscoveryState,
    *,
    validate: bool = True,
    defer_fountain_validation: bool = False,
) -> bool:
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    validator = (
        (lambda value: validate_discovery(
            value, defer_fountain_validation=True))
        if validate and defer_fountain_validation
        else validate_discovery if validate
        else None
    )
    return save_typed(
        path,
        state,
        magic=DISCOVERY_MAGIC,
        schema=DISCOVERY_SCHEMA_VERSION,
        validate=validator,
    )


def save_discovery_with_digest(
    path: str | Path,
    state: DiscoveryState,
    *,
    validate: bool = True,
    defer_fountain_validation: bool = False,
) -> tuple[bool, str]:
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    validator = (
        (lambda value: validate_discovery(
            value, defer_fountain_validation=True))
        if validate and defer_fountain_validation
        else validate_discovery if validate
        else None
    )
    return save_typed_with_digest(
        path,
        state,
        magic=DISCOVERY_MAGIC,
        schema=DISCOVERY_SCHEMA_VERSION,
        validate=validator,
    )


def load_discovery(
    path: str | Path,
    *,
    defer_fountain_validation: bool = False,
) -> DiscoveryState:
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    validator = (
        (lambda state: validate_discovery(
            state, defer_fountain_validation=True))
        if defer_fountain_validation else validate_discovery
    )
    return load_typed(
        path,
        DiscoveryState,
        magic=DISCOVERY_MAGIC,
        schema=DISCOVERY_SCHEMA_VERSION,
        validate=validator,
        migrations=DISCOVERY_MIGRATIONS,
    )


def load_discovery_with_digest(
    path: str | Path,
    *,
    defer_fountain_validation: bool = False,
) -> tuple[DiscoveryState, str]:
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    validator = (
        (lambda state: validate_discovery(
            state, defer_fountain_validation=True))
        if defer_fountain_validation else validate_discovery
    )
    return load_typed_with_digest(
        path,
        DiscoveryState,
        magic=DISCOVERY_MAGIC,
        schema=DISCOVERY_SCHEMA_VERSION,
        validate=validator,
        migrations=DISCOVERY_MIGRATIONS,
    )


def state_file_magic(path: str | Path) -> str:
    """Read only the envelope discriminator used for CLI resume routing."""
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read receive-state envelope") from exc
    if not isinstance(envelope, dict) or not isinstance(
            envelope.get("magic"), str):
        raise ValueError("receive state has no valid magic")
    return envelope["magic"]


__all__ = [
    "DISCOVERY_MAGIC",
    "DISCOVERY_MIGRATIONS",
    "DISCOVERY_SCHEMA_VERSION",
    "DiscoveryState",
    "DiscoveryStatus",
    "DiscoverySurvey",
    "authoritative_discovery_sha256",
    "load_discovery",
    "load_discovery_with_digest",
    "save_discovery",
    "save_discovery_with_digest",
    "state_file_magic",
    "validate_discovery",
]
