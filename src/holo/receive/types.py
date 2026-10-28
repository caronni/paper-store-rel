"""Durable vocabulary for the production receive pipeline.

The records in this module are the values allowed to cross an E023c
retention barrier.  Numerical work arrays stay inside their owning stage;
the compact facts needed to resume, audit, combine acquisitions, and close a
volume are explicit immutable records.  In particular there is no generic
mapping for stage state and no cross-resolution likelihood value.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TypeAlias

import numpy as np

from ..core import bch
from .lane_uplift import (  # noqa: F401  (re-exported lane vocabulary)
    UPLIFT_ARMS,
    UPLIFT_LANE_PREFIX,
    parse_uplift_lane_id as _parse_uplift,
    uplift_lane_id,
)


Scalar: TypeAlias = str | int | float | bool | None
Affine6: TypeAlias = tuple[float, float, float, float, float, float]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _identity(label: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _name(label: str, value: str) -> str:
    if not isinstance(value, str) or _NAME_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must match {_NAME_RE.pattern!r}")
    return value


def _sha256(label: str, value: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase SHA-256")
    return value


def _finite(label: str, value: float) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _nonnegative(label: str, value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _positive(label: str, value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _affine(value: Affine6) -> None:
    if len(value) != 6 or any(not math.isfinite(float(row)) for row in value):
        raise ValueError("affine must contain six finite values")
    a, b, _c, d, e, _f = (float(row) for row in value)
    if a * e - b * d == 0.0:
        raise ValueError("affine linear map must be non-singular")


def _unique(label: str, values: tuple[str, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    for value in values:
        _identity(label, value)


class Stage(str, Enum):
    INGEST = "ingest"
    SURVEY = "survey"       # E021
    ADDRESS = "address"     # E022
    PAYLOAD = "payload"     # E023b
    SCHEDULE = "schedule"   # E023c barriers
    CLOSE = "close"


LANE_STAGES = (Stage.SURVEY, Stage.ADDRESS, Stage.PAYLOAD)


class Disposition(str, Enum):
    COMPLETE = "complete"
    REFUSED = "refused"


class CloseStatus(str, Enum):
    OPEN = "open"
    VERIFIED = "verified"
    INTEGRITY_FAILURE = "integrity_failure"
    UNSUPPORTED = "unsupported"


class EventAuthority(str, Enum):
    """Whether an observer event describes working or retained facts."""

    TRANSIENT = "transient"
    COMMITTED = "committed"


@dataclass(frozen=True, slots=True)
class EventContext:
    """Stable interpretation and active capture/lane observer envelope."""

    qualification_status: str | None = None
    qualification_notes: tuple[str, ...] = ()
    format_id: str | None = None
    receiver_policy_id: str | None = None
    page_domain: tuple[int, ...] = ()
    source_sha256: str | None = None
    lane_id: str | None = None
    parent_lane_id: str | None = None
    level_ordinal: int | None = None
    levels_total: int | None = None
    ppc: tuple[int, int] | None = None
    effective_dpi: float | None = None
    # Exact native-px-per-view-px ratio of the lane whose raster this
    # event's geometry was measured in (``LaneSpec.native_per_view``).
    # M/R levels copy their base lane's value verbatim (cascade
    # ``_scale_plan``), so an observer can lift any lane's pixel
    # geometry into ONE capture-native frame without knowing which
    # rung emitted it -- see diag/viewer's pane-A normalization.
    native_per_view: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("qualification status", self.qualification_status),
            ("format id", self.format_id),
            ("receiver policy id", self.receiver_policy_id),
            ("lane id", self.lane_id),
            ("parent lane id", self.parent_lane_id),
        ):
            if value is not None:
                _identity(label, value)
        if any(not isinstance(note, str) or not note
               for note in self.qualification_notes):
            raise ValueError("qualification notes must be non-empty strings")
        if (self.source_sha256 is not None
                and _SHA256_RE.fullmatch(self.source_sha256) is None):
            raise ValueError("event source SHA must be lowercase SHA-256")
        if (len(set(self.page_domain)) != len(self.page_domain)
                or any(type(page) is not int or page < 0
                       for page in self.page_domain)):
            raise ValueError("event page domain must be unique and non-negative")
        for label, value in (
            ("level ordinal", self.level_ordinal),
            ("level total", self.levels_total),
        ):
            if value is not None:
                _nonnegative(label, value)
        if (self.ppc is not None
                and (len(self.ppc) != 2
                     or any(type(value) is not int or value < 1
                            for value in self.ppc))):
            raise ValueError("event ppc must be a positive integer fraction")
        if self.effective_dpi is not None:
            _finite("event effective dpi", self.effective_dpi)

    def to_dict(self) -> dict[str, object]:
        return {
            "qualification_status": self.qualification_status,
            "qualification_notes": list(self.qualification_notes),
            "format_id": self.format_id,
            "receiver_policy_id": self.receiver_policy_id,
            "page_domain": list(self.page_domain),
            "source_sha256": self.source_sha256,
            "lane_id": self.lane_id,
            "parent_lane_id": self.parent_lane_id,
            "level_ordinal": self.level_ordinal,
            "levels_total": self.levels_total,
            "ppc": None if self.ppc is None else list(self.ppc),
            "effective_dpi": self.effective_dpi,
        }


@dataclass(frozen=True, slots=True)
class Detail:
    name: str
    value: Scalar

    def __post_init__(self) -> None:
        _name("detail name", self.name)
        if isinstance(self.value, float):
            _finite("detail value", self.value)
        if not (self.value is None or isinstance(
                self.value, (str, int, float, bool))):
            raise TypeError("detail values must be JSON scalar values")


@dataclass(frozen=True, slots=True)
class StageDecision:
    stage: Stage
    disposition: Disposition
    reason: str = ""

    def __post_init__(self) -> None:
        if self.stage not in LANE_STAGES:
            raise ValueError("decision stage is not a lane stage")
        if not isinstance(self.reason, str):
            raise TypeError("decision reason must be text")
        if self.disposition is Disposition.REFUSED:
            if not self.reason.strip():
                raise ValueError("a refused stage must explain itself")
        elif self.reason:
            raise ValueError("a completed stage cannot carry a refusal reason")


@dataclass(frozen=True, slots=True)
class CaptureInput:
    source: str | Path | np.ndarray
    dpi: float
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.source, np.ndarray):
            if self.source.ndim not in (2, 3) or self.source.size == 0:
                raise ValueError("capture array must be non-empty grey or RGB")
        elif (not isinstance(self.source, (str, Path))
              or not str(self.source)):
            raise ValueError("capture source must be a non-empty path or array")
        if _finite("capture dpi", self.dpi) <= 0:
            raise ValueError("capture dpi must be positive")
        if (self.expected_sha256 is not None
                and _SHA256_RE.fullmatch(self.expected_sha256) is None):
            raise ValueError("expected_sha256 must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class LaneSpec:
    """Stable exact-rational identity of one correlated scale lane.

    ``mopup_of`` (v0.33) marks a mop-up plan entry: it names the ordinary
    ladder lane whose deferred costly placement work this level executes.
    Evidence identity keys on :attr:`evidence_lane_id`, so a mop-up level's
    blocks, attempts, divergences, and quarantine share its base lane's
    evidence axis while plan identity and durable-id namespaces keep the
    unique plan ``lane_id``.

    ``refine_of`` (v0.42) marks a refinement plan entry ``R(Lk)``: it names
    the ordinary ladder lane whose committed accepted poses this level
    refines against the full accumulated certificate frontier.  Unlike a
    mop-up level, a refinement level owns its OWN evidence namespace —
    ``evidence_lane_id`` stays the R lane's own ``lane_id`` (only
    certificates cross lanes; LLRs never cross correlated views, so there
    is no supersession of base blocks).  The raster/transform binding is
    the base lane's exactly like a mop-up (:attr:`base_lane_id`).

    A SUPPLEMENTAL lane (PK4.3, ``U(Lk, arm)``, :mod:`lane_uplift`) is
    the fourth class and carries no new persisted field: its ``lane_id``
    IS its declaration, so :attr:`uplift_of` and :attr:`arm_override`
    are derived exactly as ``base_lane_id`` is.  It binds its base
    lane's transform and committed poses like a refinement level and
    owns its own evidence namespace, but refines no pose: it re-runs the
    payload transaction over that domain with ONE campaign arm forced,
    and §6.3's per-address retirement law bounds it to the uncertified
    residue.  A level is exactly one of ordinary / mop-up / refinement /
    supplemental.
    """

    lane_id: str
    target_ppc_num: int
    target_ppc_den: int
    native_per_view_num: int
    native_per_view_den: int
    parent_lane_id: str | None = None
    mopup_of: str | None = None
    refine_of: str | None = None

    def __post_init__(self) -> None:
        _identity("lane_id", self.lane_id)
        for num, den, label in (
            (self.target_ppc_num, self.target_ppc_den, "target_ppc"),
            (self.native_per_view_num, self.native_per_view_den,
             "native_per_view"),
        ):
            _positive(f"lane {label} numerator", num)
            _positive(f"lane {label} denominator", den)
            if math.gcd(num, den) != 1:
                raise ValueError(f"lane {label} ratio must be reduced")
        if self.parent_lane_id is not None:
            _identity("parent_lane_id", self.parent_lane_id)
            if self.parent_lane_id == self.lane_id:
                raise ValueError("a lane cannot be its own parent")
        if self.mopup_of is not None and self.refine_of is not None:
            raise ValueError(
                "a lane is exactly one of ordinary, mop-up, or refinement")
        if self.mopup_of is not None:
            _identity("mopup_of", self.mopup_of)
            if self.mopup_of == self.lane_id:
                raise ValueError("a mop-up lane cannot serve itself")
        if self.refine_of is not None:
            _identity("refine_of", self.refine_of)
            if self.refine_of == self.lane_id:
                raise ValueError("a refinement lane cannot serve itself")
        # PK4.3: a supplemental lane declares itself in its id, so the
        # exclusivity rule is checked against the derived class too.
        if (_parse_uplift(self.lane_id) is not None
                and (self.mopup_of is not None or self.refine_of is not None)):
            raise ValueError(
                "a supplemental lane is neither a mop-up nor a refinement")

    @property
    def evidence_lane_id(self) -> str:
        """The lane identity that evidence keys on (v0.33/v0.42).

        A mop-up level joins its base lane's evidence axis; refinement and
        supplemental levels keep their own (only certificates cross
        correlated lanes).
        """
        return self.mopup_of if self.mopup_of is not None else self.lane_id

    @property
    def uplift_of(self) -> str | None:
        """The ordinary lane this SUPPLEMENTAL lane serves, else ``None``.

        Derived from the lane id, so a plan read back from durable state
        declares exactly what the plan builder minted (PK4.3).
        """
        parsed = _parse_uplift(self.lane_id)
        return None if parsed is None else parsed[0]

    @property
    def arm_override(self) -> str | None:
        """The forced campaign arm of a supplemental lane, else ``None``.

        One of :data:`UPLIFT_ARMS`, and the ONLY legal source of an arm
        override: lane-scoped configuration carried by the lane's own
        identity, never ambient process state.
        """
        parsed = _parse_uplift(self.lane_id)
        return None if parsed is None else parsed[1]

    @property
    def base_lane_id(self) -> str:
        """The ordinary ladder lane whose exact raster this level uses.

        Ordinary levels are their own base; mop-up, refinement and
        supplemental levels bind to their named base lane's transform
        (same exact-rational derivation, pooled raster reuse).
        """
        if self.mopup_of is not None:
            return self.mopup_of
        if self.refine_of is not None:
            return self.refine_of
        uplift = self.uplift_of
        return self.lane_id if uplift is None else uplift

@dataclass(frozen=True, slots=True)
class SupportRun:
    """One true row-major run in an E021 support grid."""

    start: int
    length: int

    def __post_init__(self) -> None:
        _nonnegative("support run start", self.start)
        _positive("support run length", self.length)


@dataclass(frozen=True, slots=True)
class SurveyRegionRecord:
    region_id: str
    capture_id: str
    lane_id: str
    origin_yx: tuple[int, int]
    extent_yx: tuple[int, int]
    support_step_px: int
    support_shape_yx: tuple[int, int]
    support_runs: tuple[SupportRun, ...]
    area_mm2: float
    median_tensor_score: float

    def __post_init__(self) -> None:
        for label, value in (("region_id", self.region_id),
                             ("lane_id", self.lane_id)):
            _identity(label, value)
        _sha256("region capture id", self.capture_id)
        if any(type(row) is not int or row < 0 for row in self.origin_yx):
            raise ValueError("region origin must be non-negative integers")
        if any(type(row) is not int or row < 1 for row in self.extent_yx):
            raise ValueError("region extent must be positive integers")
        _positive("support step", self.support_step_px)
        rows, columns = self.support_shape_yx
        _positive("support rows", rows)
        _positive("support columns", columns)
        area = rows * columns
        previous_end = -1
        for run in self.support_runs:
            if run.start <= previous_end or run.start + run.length > area:
                raise ValueError("support runs overlap or exceed their grid")
            previous_end = run.start + run.length - 1
        if _finite("region area", self.area_mm2) <= 0:
            raise ValueError("region area must be positive")
        _finite("median tensor score", self.median_tensor_score)


@dataclass(frozen=True, slots=True)
class SurveyArtifact:
    survey_id: str
    region_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity("survey_id", self.survey_id)
        _unique("region ids", self.region_ids)


@dataclass(frozen=True, slots=True)
class PoseRecord:
    """Accepted pose in one canonical coordinate convention.

    ``native_affine`` is the row-major 2x3 map from absolute page-cell
    ``(y, x)`` coordinates to authenticated native-source pixel centres.
    ``rot90`` records the resolved orientation already embodied in that map;
    ``cell_origin_yx`` scopes the placed patch, it is not an affine origin.

    The ``window_*``/``lane_pose_*``/``segment_*`` fields (v0.33 D7) are
    the exact lane-frame re-sampling carrier, mirroring
    :class:`ParkedWindowRecord`: the canonical native affine rounds once
    on conversion and cannot re-derive the lane sample bit-exactly, so a
    mop-up level reconstructing this window as a calibration label reads
    the fitted lane pose verbatim.
    """
    pose_id: str
    capture_id: str
    lane_id: str
    region_id: str
    patch_id: int
    placement_outcome: str
    page: int
    cell_origin_yx: tuple[int, int]
    native_affine: Affine6
    rot90: int
    quality: float
    window_id: int
    window_origin_yx_px: tuple[int, int]
    window_shape_yx_cells: tuple[int, int]
    window_depth: int
    lane_pose_origin_yx: tuple[float, float]
    lane_pose_jacobian: tuple[float, float, float, float]
    lane_pose_phase_yx: tuple[float, float]
    lane_pose_pitch_px: float
    lane_pose_angle_deg: float
    segment_support_cells: int
    segment_phase_contrast: float
    segment_pitch_yx_px: tuple[float, float]
    segment_orthogonality_error_deg: float
    dependency_certificate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (("pose_id", self.pose_id),
                             ("lane_id", self.lane_id),
                             ("region_id", self.region_id)):
            _identity(label, value)
        _sha256("pose capture id", self.capture_id)
        _nonnegative("pose patch id", self.patch_id)
        if self.placement_outcome not in {"accepted", "redundant"}:
            raise ValueError(
                "pose placement outcome must be accepted or redundant")
        _nonnegative("page", self.page)
        if any(type(row) is not int for row in self.cell_origin_yx):
            raise ValueError("cell origin must contain integers")
        _affine(self.native_affine)
        if self.rot90 not in (0, 1, 2, 3):
            raise ValueError("rot90 must be 0, 1, 2, or 3")
        _finite("pose quality", self.quality)
        _nonnegative("pose window id", self.window_id)
        if any(type(row) is not int or row < 0
               for row in self.window_origin_yx_px):
            raise ValueError("pose window origin must be non-negative ints")
        if any(type(row) is not int or row < 1
               for row in self.window_shape_yx_cells):
            raise ValueError("pose window shape must be positive ints")
        _nonnegative("pose window depth", self.window_depth)
        for label, rows in (("pose lane origin", self.lane_pose_origin_yx),
                            ("pose lane phase", self.lane_pose_phase_yx),
                            ("pose segment pitch", self.segment_pitch_yx_px)):
            if len(rows) != 2 or any(
                    not math.isfinite(float(row)) for row in rows):
                raise ValueError(f"{label} must contain two finite values")
        if len(self.lane_pose_jacobian) != 4 or any(
                not math.isfinite(float(row))
                for row in self.lane_pose_jacobian):
            raise ValueError(
                "pose lane jacobian must contain four finite values")
        if _finite("pose lane pitch", self.lane_pose_pitch_px) <= 0:
            raise ValueError("pose lane pitch must be positive")
        _finite("pose lane angle", self.lane_pose_angle_deg)
        _nonnegative("pose segment support", self.segment_support_cells)
        _finite("pose segment contrast", self.segment_phase_contrast)
        _finite("pose segment orthogonality",
                self.segment_orthogonality_error_deg)
        _unique("pose dependency ids", self.dependency_certificate_ids)

@dataclass(frozen=True, slots=True)
class PoseProposal:
    """Spatially scoped accepted-pose fact in native coordinates.

    The affine has the same absolute-page-cell to native-pixel-centre
    convention as :class:`PoseRecord`; ``rot90`` records the discrete E022
    orientation already embodied by it.  A proposal belongs only to its
    source lane.  Any later lane may convert the native geometry into its own
    view and revalidate it against fresh pixels.
    """
    proposal_id: str
    capture_id: str
    source_lane_id: str
    page: int
    rot90: int
    native_search_origin_yx: tuple[int, int]
    native_search_extent_yx: tuple[int, int]
    native_pose_origin_yx: tuple[float, float]
    native_affine: Affine6
    dependency_certificate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (("proposal_id", self.proposal_id),
                             ("source_lane_id", self.source_lane_id)):
            _identity(label, value)
        _sha256("proposal capture id", self.capture_id)
        _nonnegative("page", self.page)
        if self.rot90 not in (0, 1, 2, 3):
            raise ValueError("rot90 must be 0, 1, 2, or 3")
        if any(type(row) is not int or row < 0
               for row in self.native_search_origin_yx):
            raise ValueError("proposal origin must be non-negative integers")
        if any(type(row) is not int or row < 1
               for row in self.native_search_extent_yx):
            raise ValueError("proposal extent must be positive integers")
        if (len(self.native_pose_origin_yx) != 2 or any(
                not math.isfinite(float(row))
                for row in self.native_pose_origin_yx)):
            raise ValueError("proposal pose origin must contain two finite values")
        _affine(self.native_affine)
        _unique("proposal dependency ids", self.dependency_certificate_ids)


@dataclass(frozen=True, slots=True)
class LosingHypothesis:
    """Spatially scoped rejected candidate retained for exact revisit."""

    hypothesis_id: str
    capture_id: str
    lane_id: str
    region_id: str
    page: int
    page_origin_yx: tuple[int, int]
    rot90: int
    native_search_origin_yx: tuple[int, int]
    native_search_extent_yx: tuple[int, int]
    native_pose_origin_yx: tuple[float, float]
    native_affine: Affine6
    mismatch: float
    validation: float
    search_support: int
    validation_support: int
    dependency_certificate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (("hypothesis_id", self.hypothesis_id),
                             ("lane_id", self.lane_id),
                             ("region_id", self.region_id)):
            _identity(label, value)
        _sha256("hypothesis capture id", self.capture_id)
        _nonnegative("page", self.page)
        if any(type(row) is not int for row in self.page_origin_yx):
            raise ValueError("page origin must contain signed integers")
        if self.rot90 not in (0, 1, 2, 3):
            raise ValueError("rot90 must be 0, 1, 2, or 3")
        if any(type(row) is not int or row < 0
               for row in self.native_search_origin_yx):
            raise ValueError("hypothesis origin must be non-negative integers")
        if any(type(row) is not int or row < 1
               for row in self.native_search_extent_yx):
            raise ValueError("hypothesis extent must be positive integers")
        if (len(self.native_pose_origin_yx) != 2 or any(
                not math.isfinite(float(row))
                for row in self.native_pose_origin_yx)):
            raise ValueError(
                "hypothesis pose origin must contain two finite values")
        _affine(self.native_affine)
        _finite("hypothesis mismatch", self.mismatch)
        _finite("hypothesis validation", self.validation)
        _nonnegative("hypothesis search support", self.search_support)
        _nonnegative("hypothesis validation support", self.validation_support)
        _unique("hypothesis dependency ids",
                self.dependency_certificate_ids)


@dataclass(frozen=True, slots=True)
class ParkedWindowRecord:
    """Compact durable placement work parked for the capture's mop-up level.

    v0.33: geometry and route facts only — no pixels, no sampled evidence.
    The mop-up level re-materializes the lane raster (exact-area derivation
    from native) and re-samples bit-exactly from the fitted pose persisted
    here plus the region record's support; ``cell_pitch_px`` and
    ``lattice_f`` carry the two processing-order-dependent survey
    transients that re-derivation cannot reproduce.  ``origin_yx_px`` is
    region-crop-relative, matching the live ``PoseWindow`` convention;
    ``pose_origin_yx`` is absolute lane-view pixels.
    """

    parked_id: str
    capture_id: str
    lane_id: str
    region_id: str
    region_index: int
    window_id: int
    origin_yx_px: tuple[int, int]
    shape_yx_cells: tuple[int, int]
    depth: int
    support_estimate: float
    pose_origin_yx: tuple[float, float]
    pose_jacobian: tuple[float, float, float, float]
    pose_phase_yx: tuple[float, float]
    pose_pitch_px: float
    pose_angle_deg: float
    support_cells: int
    phase_contrast: float
    pitch_yx_px: tuple[float, float]
    orthogonality_error_deg: float
    patch_ordinal: int
    attempted_routes: tuple[str, ...]
    cell_pitch_px: float
    lattice_f: tuple[float, float, float, float] | None

    def __post_init__(self) -> None:
        for label, value in (("parked_id", self.parked_id),
                             ("lane_id", self.lane_id),
                             ("region_id", self.region_id)):
            _identity(label, value)
        _sha256("parked capture id", self.capture_id)
        _nonnegative("parked region index", self.region_index)
        _nonnegative("parked window id", self.window_id)
        if any(type(row) is not int or row < 0 for row in self.origin_yx_px):
            raise ValueError("parked origin must be non-negative integers")
        if any(type(row) is not int or row < 1
               for row in self.shape_yx_cells):
            raise ValueError("parked shape must be positive integers")
        _nonnegative("parked depth", self.depth)
        if _finite("parked support estimate", self.support_estimate) < 0:
            raise ValueError("parked support estimate must be >= 0")
        for label, rows in (("parked pose origin", self.pose_origin_yx),
                            ("parked pose phase", self.pose_phase_yx),
                            ("parked pitch pair", self.pitch_yx_px)):
            if len(rows) != 2 or any(
                    not math.isfinite(float(row)) for row in rows):
                raise ValueError(f"{label} must contain two finite values")
        if len(self.pose_jacobian) != 4 or any(
                not math.isfinite(float(row)) for row in self.pose_jacobian):
            raise ValueError("parked jacobian must contain four finite values")
        if _finite("parked pose pitch", self.pose_pitch_px) <= 0:
            raise ValueError("parked pose pitch must be positive")
        _finite("parked pose angle", self.pose_angle_deg)
        _nonnegative("parked support cells", self.support_cells)
        _finite("parked phase contrast", self.phase_contrast)
        _finite("parked orthogonality error", self.orthogonality_error_deg)
        _nonnegative("parked patch ordinal", self.patch_ordinal)
        if not self.attempted_routes or any(
                not isinstance(row, str) or not row
                for row in self.attempted_routes):
            raise ValueError("parked attempted routes must be non-empty")
        _unique("parked attempted routes", self.attempted_routes)
        if _finite("parked cell pitch", self.cell_pitch_px) <= 0:
            raise ValueError("parked cell pitch must be positive")
        if self.lattice_f is not None:
            # The region's 2x2 reciprocal-fundamental matrix, row-major.
            # Components may legally be ~0 or negative (shear/rotation);
            # only finiteness is checkable here.
            if len(self.lattice_f) != 4 or any(
                    not math.isfinite(float(row)) for row in self.lattice_f):
                raise ValueError(
                    "parked lattice seed must contain four finite values")


@dataclass(frozen=True, slots=True)
class BchConflictRecord:
    """Durable contradictory decode and its selected E022 contributors.

    Page/tile plus the active format row supply the expected counter.
    """

    page: int
    tile_yx: tuple[int, int]
    decoded_counter: int
    errors: int
    erasures: int
    contributor_patch_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        _nonnegative("BCH conflict page", self.page)
        if (len(self.tile_yx) != 2
                or any(type(value) is not int or value < 0
                       for value in self.tile_yx)):
            raise ValueError(
                "BCH conflict tile coordinates must be non-negative integers")
        _nonnegative("BCH conflict decoded counter", self.decoded_counter)
        _nonnegative("BCH conflict errors", self.errors)
        _nonnegative("BCH conflict erasures", self.erasures)
        if self.erasures > bch.N_WORD:
            raise ValueError(
                "BCH conflict erasures exceed the transmitted word")
        if 2 * self.errors + self.erasures > 2 * bch.T:
            raise ValueError(
                "BCH conflict corrections exceed the decoder budget")
        contributors = tuple(self.contributor_patch_ids)
        if not contributors:
            raise ValueError("BCH conflict needs a placement contributor")
        if contributors != tuple(sorted(set(contributors))):
            raise ValueError(
                "BCH conflict contributor patch ids must be sorted and unique")
        if any(type(value) is not int or value < 0 for value in contributors):
            raise ValueError(
                "BCH conflict contributor patch ids must be non-negative")

    @property
    def observed_sites(self) -> int:
        return bch.N_WORD - self.erasures


@dataclass(frozen=True, slots=True)
class AddressArtifact:
    address_id: str
    survey_id: str
    pose_ids: tuple[str, ...]
    proposal_ids: tuple[str, ...] = ()
    loser_ids: tuple[str, ...] = ()
    bch_conflicts: tuple[BchConflictRecord, ...] = ()
    parked_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identity("address_id", self.address_id)
        _identity("survey_id", self.survey_id)
        for label, rows in (("pose ids", self.pose_ids),
                            ("proposal ids", self.proposal_ids),
                            ("loser ids", self.loser_ids),
                            ("parked ids", self.parked_ids)):
            _unique(label, rows)
        keys = tuple(
            (row.page, row.tile_yx[0], row.tile_yx[1])
            for row in self.bch_conflicts)
        if keys != tuple(sorted(set(keys))):
            raise ValueError(
                "address BCH conflict words must be sorted and unique")

    @property
    def quarantined_patch_ids(self) -> tuple[int, ...]:
        return tuple(sorted({
            patch_id
            for conflict in self.bch_conflicts
            for patch_id in conflict.contributor_patch_ids
        }))


@dataclass(frozen=True, slots=True)
class SurveyProduct:
    artifact: SurveyArtifact
    regions: tuple[SurveyRegionRecord, ...]
    transient: object | None = field(
        default=None, repr=False, compare=False,
        metadata={"persist": False})

    def __post_init__(self) -> None:
        if self.artifact.region_ids != tuple(row.region_id for row in self.regions):
            raise ValueError("survey artifact does not name exactly its regions")


@dataclass(frozen=True, slots=True)
class AddressProduct:
    artifact: AddressArtifact
    poses: tuple[PoseRecord, ...]
    proposals: tuple[PoseProposal, ...] = ()
    losers: tuple[LosingHypothesis, ...] = ()
    parked: tuple[ParkedWindowRecord, ...] = ()
    transient: object | None = field(
        default=None, repr=False, compare=False,
        metadata={"persist": False})

    def __post_init__(self) -> None:
        pairs = (
            (self.artifact.pose_ids, tuple(row.pose_id for row in self.poses)),
            (self.artifact.proposal_ids,
             tuple(row.proposal_id for row in self.proposals)),
            (self.artifact.loser_ids,
             tuple(row.hypothesis_id for row in self.losers)),
            (self.artifact.parked_ids,
             tuple(row.parked_id for row in self.parked)),
        )
        if any(expected != actual for expected, actual in pairs):
            raise ValueError("address artifact does not name exactly its records")


@dataclass(frozen=True, slots=True)
class RefineAddressPlan:
    """Typed transient product of an R- or U-level address stage.

    PK4.3: a SUPPLEMENTAL level's address stage mints the same shape and
    for the same reason — it commits no records and hands the payload
    leaf the base lane's committed references.  ``base_lane_id`` is then
    ``context.lane.uplift_of`` and the leaf refines no pose; everything
    else below reads identically.

    THE STAGE-B/C CONTRACT.  Stage A ships the empty shape: the durable
    ``AddressProduct`` around it carries no records (nothing new is
    committed by an R-level address until the codec refinement leaves
    land), and this transient plan carries the base-lane references those
    leaves will consume:

    - ``base_lane_id``: the ordinary ladder lane ``Lk`` this ``R(Lk)``
      level refines (== ``context.lane.refine_of``).
    - ``poses``: ``Lk``'s committed :class:`PoseRecord` rows for this
      capture (accepted AND redundant — both trained the pooled fit;
      base-quarantined placements excluded at the evidence-context seam,
      stage C); the
      refinement candidate inventory.  These are REFERENCES to durable
      base-lane records — an R-level never re-mints them; adopted
      refined poses are minted under the R lane's own id namespace.
    - ``regions``: ``Lk``'s durable survey regions (the region-coupled
      context needed by any adopted window's re-fit).
    - ``certificates``: the full accumulated certificate frontier at this
      barrier (certificates are the only evidence that crosses lanes).

    Stage B/C fill: per-window eligibility (NeedMap prunes certified
    addresses; windows whose uncertified remainder is empty contribute
    nothing), the codec refinement leaves over eligible windows, adopted
    refined poses, and the payload delta covering ONLY affected regions
    (adopted windows + their region-coupled context).  No adoptions =>
    the payload stage stays an empty delta and the barrier commits
    cheaply.
    """

    base_lane_id: str
    poses: tuple[PoseRecord, ...]
    regions: tuple[SurveyRegionRecord, ...]
    certificates: tuple[TileCertificateRecord, ...]


@dataclass(frozen=True, slots=True)
class CloseRecord:
    status: CloseStatus = CloseStatus.OPEN
    certificate_frontier_sha256: str | None = None
    payload_sha256: str | None = None
    payload_length: int | None = None
    metadata_version: int | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, CloseStatus):
            raise TypeError("close status must be CloseStatus")
        if not isinstance(self.reason, str):
            raise TypeError("close reason must be text")
        for label, value in (
            ("certificate frontier", self.certificate_frontier_sha256),
            ("payload SHA", self.payload_sha256),
        ):
            if value is not None and _SHA256_RE.fullmatch(value) is None:
                raise ValueError(f"{label} must be lowercase SHA-256")
        if self.payload_length is not None:
            _nonnegative("payload length", self.payload_length)
        if self.metadata_version is not None:
            _nonnegative("metadata version", self.metadata_version)
        payload_identity = (self.payload_sha256, self.payload_length)
        if any(value is None for value in payload_identity) and any(
                value is not None for value in payload_identity):
            raise ValueError("payload identity must be wholly present or absent")
        if self.status is CloseStatus.OPEN:
            if (self.certificate_frontier_sha256 is not None
                    or any(value is not None for value in payload_identity)
                    or self.metadata_version is not None or self.reason):
                raise ValueError("an open close record must be empty")
        elif self.certificate_frontier_sha256 is None:
            raise ValueError("a terminal close record needs its certificate frontier")
        if self.status is CloseStatus.VERIFIED:
            if any(value is None for value in payload_identity):
                raise ValueError("verified close needs complete payload identity")
            if self.reason != "":
                raise ValueError("verified close cannot have a failure reason")
        if self.status is CloseStatus.INTEGRITY_FAILURE:
            if any(value is not None for value in payload_identity):
                raise ValueError(
                    "integrity failure cannot have payload identity")
            if not self.reason:
                raise ValueError("integrity failure needs a reason")
        if self.status is CloseStatus.UNSUPPORTED:
            if (any(value is not None for value in payload_identity)
                    or self.metadata_version is None or not self.reason):
                raise ValueError(
                    "unsupported close needs version/reason and no payload")


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Detached observer value; never persisted in authoritative state."""

    sequence: int
    name: str
    stage: Stage
    capture_id: str | None = None
    message: str = ""
    details: tuple[Detail, ...] = ()
    authority: EventAuthority = EventAuthority.TRANSIENT
    state_sha256: str | None = None
    context: EventContext = EventContext()
    snapshot: object | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _nonnegative("event sequence", self.sequence)
        _name("event name", self.name)
        if type(self.stage) is not Stage:
            raise TypeError("event stage must be exact")
        if self.capture_id is not None:
            _identity("capture_id", self.capture_id)
        if type(self.authority) is not EventAuthority:
            raise TypeError("event authority must be exact")
        if type(self.context) is not EventContext:
            raise TypeError("event context must be exact")
        if (self.state_sha256 is not None
                and _SHA256_RE.fullmatch(self.state_sha256) is None):
            raise ValueError("event state_sha256 must be lowercase SHA-256")
        names = tuple(row.name for row in self.details)
        if len(names) != len(set(names)):
            raise ValueError("event detail names must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "name": self.name,
            "stage": self.stage.value,
            "capture_id": self.capture_id,
            "message": self.message,
            "details": {row.name: row.value for row in self.details},
            "authority": self.authority.value,
            "state_sha256": self.state_sha256,
            "context": self.context.to_dict(),
        }


from .evidence import (  # noqa: E402  (re-exported receive vocabulary)
    AttemptStage,
    AttemptState,
    DivergenceRecord,
    PayloadArtifact,
    PayloadProduct,
    TileAttemptRecord,
    TileCertificateRecord,
    certificate_work_index,
)
from .evidence_blocks import (  # noqa: E402
    EvidenceBlock,
    EvidenceOrigin,
)


__all__ = [
    "LANE_STAGES", "AddressArtifact", "AddressProduct", "BchConflictRecord",
    "Affine6",
    "AttemptStage", "AttemptState", "CaptureInput",
    "CloseRecord", "CloseStatus", "Detail",
    "Disposition", "DivergenceRecord", "EventAuthority",
    "EventContext", "EvidenceBlock",
    "EvidenceOrigin",
    "LaneSpec",
    "LosingHypothesis",
    "PayloadArtifact", "PayloadProduct",
    "PoseProposal", "PoseRecord",
    "RefineAddressPlan",
    "RuntimeEvent", "Scalar", "Stage",
    "StageDecision", "SupportRun", "SurveyArtifact", "SurveyProduct",
    "SurveyRegionRecord", "TileAttemptRecord", "TileCertificateRecord",
    "UPLIFT_ARMS", "UPLIFT_LANE_PREFIX",
    "certificate_work_index", "uplift_lane_id",
]
