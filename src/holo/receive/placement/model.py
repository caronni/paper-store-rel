"""Typed records and explicit attempt budgets for production E022.

E022-v2's measured 30-site floor remains the qualified minimum.  Holo's
larger search domains additionally apply e026's information-theoretic
identifiability lower bound.  Neither bound is misrepresented as a tail bound
for the weighted mismatch statistic; the declared false-accept target still
requires the v1 null and physical qualification named by HOLO-DESIGN 9.3.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

import numpy as np

from ...core import bch

PointYX: TypeAlias = tuple[float, float]
CellYX: TypeAlias = tuple[int, int]
MAX_LOWER_HINTS = 8


HISTORICAL_MIN_SUPPORT = 30
"""Qualified E022-v2 floor for each disjoint parity population.

The score is an evidence-weighted mismatch, not a Binomial hard-error count.
Consequently neither ``alpha`` nor a hard-BER tail may honestly be used to
derive its acceptance floor without a new weighted-statistic qualification.
"""

GATE_TRUE = 0.20
GATE_DECOY = 0.20
GATE_GAP = 0.08
VALIDATION_TRUE = 0.24
"""Exact strict E022-v2 placement bars (2026-07-14)."""


@dataclass(frozen=True, slots=True)
class PlacementGate:
    """Coupled placement-admission bars with explicit provenance.

    The four values form one qualified decision rule; production must never
    mix values from independently named profiles.  The historical E022 rule
    remains the default for differential tests, while a future v1 production
    profile must carry its own frozen identifier.
    """

    search_true: float
    rival_decoy: float
    minimum_gap: float
    validation_true: float
    qualification_id: str

    def __post_init__(self) -> None:
        for label, value in (
            ("search_true", self.search_true),
            ("rival_decoy", self.rival_decoy),
            ("validation_true", self.validation_true),
        ):
            value = float(value)
            if not 0.0 < value < 0.5 or not math.isfinite(value):
                raise ValueError(f"{label} must be finite and in (0, 0.5)")
            object.__setattr__(self, label, value)
        gap = float(self.minimum_gap)
        if not 0.0 <= gap < 0.5 or not math.isfinite(gap):
            raise ValueError("minimum_gap must be finite and in [0, 0.5)")
        object.__setattr__(self, "minimum_gap", gap)
        if (not isinstance(self.qualification_id, str)
                or not self.qualification_id):
            raise ValueError("gate qualification_id must be non-empty")


HISTORICAL_E022_GATE = PlacementGate(
    GATE_TRUE,
    GATE_DECOY,
    GATE_GAP,
    VALIDATION_TRUE,
    "paperholo/e022-v2/session-gap-gate",
)

# v0.30: identical numeric bars, but the decoy/gap arithmetic evaluates
# WHOLE-WORD rival mismatches (both parity classes), restoring the d=27
# floor against cross-page tile-lattice aliases whose search-class
# mismatch is structurally sub-0.20 at complete domains
# (docs/FULL-DOMAIN-RIVAL-ANALYSIS.md).  A distinct identity because the
# decision RULE changed; the historical row stays above as the recorded
# pre-v0.30 reference.
V1_WHOLEWORD_RIVAL_GATE = PlacementGate(
    GATE_TRUE,
    GATE_DECOY,
    GATE_GAP,
    VALIDATION_TRUE,
    "holo-v1/e022-v2-wholeword-rival/session-gap-gate",
)


def identifiability_support_floor(
    hypotheses: int, max_true_error_rate: float
) -> int:
    """Return e026's ``ceil(log2(H) / (1 - h2(BER)))`` lower bound.

    This is the site-count identifiability law recorded in HOLO-DESIGN 9.3
    and e026.2.  It is a necessary information bound, not a family-wise
    false-accept certificate and not a model of the weighted gate statistic.
    """
    domain = _positive_int("hypotheses", hypotheses)
    error = float(max_true_error_rate)
    if not 0.0 <= error < 0.5 or not math.isfinite(error):
        raise ValueError("max_true_error_rate must be in [0, 0.5)")
    if domain == 1:
        return 0
    entropy = (
        0.0 if error == 0.0
        else -error * math.log2(error) - (1.0 - error) * math.log2(1.0 - error)
    )
    return int(math.ceil(math.log2(domain) / (1.0 - entropy)))


def _positive_int(label: str, value: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)) or int(value) < 1:
        raise ValueError(f"{label} must be a positive integer")
    return int(value)


@dataclass(frozen=True, slots=True)
class AttemptBudget:
    """Auditable complete-domain envelope for one search class.

    ``max_hypotheses`` is an upper bound, never a work limiter: an invocation
    whose complete domain is larger refuses before searching rather than
    selecting a prefix.  Each disjoint parity population must meet the larger
    of E022-v2's measured 30-site floor and e026's attempt-domain/BER-derived
    identifiability floor.

    ``familywise_false_accept`` is an explicit target and audit field.  It is
    deliberately absent from the floor formula: the record supplies no proved
    mapping from alpha to the weighted mismatch/rival decision, and structured
    v1 BCH fields are not Bernoulli(1/2).  Meeting that target remains a fresh
    v1 null/physical qualification duty, not arithmetic performed here.
    """

    max_hypotheses: int
    familywise_false_accept: float
    max_true_error_rate: float
    qualification_id: str
    gate: PlacementGate = HISTORICAL_E022_GATE
    support_margin_sites: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "max_hypotheses",
            _positive_int("max_hypotheses", self.max_hypotheses),
        )
        alpha = float(self.familywise_false_accept)
        error = float(self.max_true_error_rate)
        if not 0.0 < alpha < 1.0 or not math.isfinite(alpha):
            raise ValueError("familywise_false_accept must be in (0, 1)")
        if not 0.0 <= error < 0.5 or not math.isfinite(error):
            raise ValueError("max_true_error_rate must be in [0, 0.5)")
        if not isinstance(self.qualification_id, str) or not self.qualification_id:
            raise ValueError("qualification_id must name the gate provenance")
        if not isinstance(self.gate, PlacementGate):
            raise TypeError("gate must be a PlacementGate")
        margin = self.support_margin_sites
        if (isinstance(margin, (bool, np.bool_))
                or not isinstance(margin, (int, np.integer))
                or int(margin) < 0):
            raise ValueError("support_margin_sites must be a non-negative integer")
        object.__setattr__(self, "support_margin_sites", int(margin))

    @property
    def min_support(self) -> int:
        """Effective floor for each independent search/validation parity."""
        return max(
            HISTORICAL_MIN_SUPPORT,
            identifiability_support_floor(
                self.max_hypotheses, self.max_true_error_rate
            ) + self.support_margin_sites,
        )

    @property
    def search_min_support(self) -> int:
        return self.min_support

    @property
    def validation_min_support(self) -> int:
        return self.min_support


@dataclass(frozen=True, slots=True)
class PlacementBudgets:
    """Separate complete-domain envelopes for each placement route.

    ``lower`` is deliberately optional so standalone E022 is numerically
    unchanged.  Supplying lower-scale hints without this explicit aggregate
    route budget is an error rather than a hidden expansion of ``local``.
    """

    cold: AttemptBudget
    local: AttemptBudget
    lower: AttemptBudget | None = None


HintKind: TypeAlias = Literal["accepted", "runner_up"]


@dataclass(frozen=True, slots=True)
class PlacementHint:
    """Search-only continuation geometry expressed in the current raster.

    ``page_to_scan_affine`` is row-major 2x3 and maps canonical absolute page
    cell centres ``(y, x)`` to current-raster pixel centres.  ``rot_k`` records
    the discrete orientation already embodied by that affine; only the target
    patch's integer origin is derived afresh.  The half-open scan box scopes
    the physical component this hint may seed.  No pixels, bits, target pose,
    or acceptance result crosses the boundary. ``patch_id`` links a hint in
    an :class:`AddressResult` to the attempted E022 patch that emitted it; it
    is absent on geometry imported from an earlier lane.
    """

    hint_id: str
    page: int
    rot_k: int
    page_to_scan_affine: tuple[float, float, float, float, float, float]
    scan_bbox_yxyx: tuple[float, float, float, float]
    scan_pose_origin_yx: PointYX
    kind: HintKind = "accepted"
    search_mismatch: float = 0.0
    validation_mismatch: float = 0.0
    patch_id: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.hint_id, str) or not self.hint_id:
            raise ValueError("hint_id must be a non-empty string")
        if isinstance(self.page, (bool, np.bool_)) or not isinstance(
                self.page, (int, np.integer)) or int(self.page) < 0:
            raise ValueError("hint page must be a non-negative integer")
        if self.rot_k not in (0, 1, 2, 3):
            raise ValueError("hint rot_k must be 0, 1, 2, or 3")
        affine = np.asarray(self.page_to_scan_affine, np.float64)
        bbox = np.asarray(self.scan_bbox_yxyx, np.float64)
        pose_origin = np.asarray(self.scan_pose_origin_yx, np.float64)
        if affine.shape != (6,) or not np.isfinite(affine).all():
            raise ValueError("hint affine must contain six finite values")
        matrix = affine.reshape(2, 3)[:, :2]
        if abs(float(np.linalg.det(matrix))) <= 1e-12:
            raise ValueError("hint affine must be invertible")
        if (bbox.shape != (4,) or not np.isfinite(bbox).all()
                or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]):
            raise ValueError("hint scan bbox must be finite and non-empty")
        if pose_origin.shape != (2,) or not np.isfinite(pose_origin).all():
            raise ValueError("hint pose origin must contain two finite values")
        if self.kind not in ("accepted", "runner_up"):
            raise ValueError("hint kind must be accepted or runner_up")
        for label, value in (
            ("hint search mismatch", self.search_mismatch),
            ("hint validation mismatch", self.validation_mismatch),
        ):
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"{label} must be finite and non-negative")
        if self.patch_id is not None:
            if isinstance(self.patch_id, (bool, np.bool_)) or not isinstance(
                    self.patch_id, (int, np.integer)) or int(self.patch_id) < 0:
                raise ValueError("hint patch_id must be a non-negative integer")
            object.__setattr__(self, "patch_id", int(self.patch_id))

    def affine(self) -> np.ndarray:
        return np.asarray(self.page_to_scan_affine, np.float64).reshape(2, 3)


@dataclass(frozen=True, slots=True)
class PlacementConfig:
    """The frozen E022-v2 window, sampler, refinement, and audit policy.

    A placement window owns one independently fitted affine pose.  The
    200-cell span, 40-cell overlap, and one level of four 70-cell-or-larger
    corner retries are the measured E022 geometry; characterization
    metrology does not participate in receiver window sizing.
    """

    window_cells: int = 200
    overlap_cells: int = 40
    subdivide: bool = True
    min_window_cells: int = 70
    erode_cells: int = 2
    pitch_tolerance: float = 0.06
    shear_tolerance_deg: float = 3.0
    aperture_cells: float = 0.7
    phase_step_cells: float = 0.125
    spectral_px: int = 2048
    min_spectral_periods: int = 12
    neighbor_radius_cells: int = 3
    consistency_cells: int = 2
    allow_overhang: bool = True
    refine: bool = True
    refine_angle_deg: float = 0.15
    refine_angle_step_deg: float = 0.05
    refine_phase_cells: float = 0.25
    refine_phase_step_cells: float = 0.0625
    refine_min_total_sites: int = 60
    refine_min_sites_per_parity: int = 20
    refine_heldout_degrade: float = 0.005
    audit_bad: float = 0.35
    audit_good: float = 0.20
    audit_min_sites: int = 15
    audit_post_bar: float = 0.25
    # PLACEMENT-IMPROVEMENTS §3.5 (v0.33): at or below this declared page
    # count a cold sweep prices below one remaining-slot word sweep, so
    # the cold runs first and rest-decode follows only on its refusal.
    # Scheduling data, not identity (G2); both routes still run before
    # any window gives up.
    cold_first_max_pages: int = 1

    def __post_init__(self) -> None:
        for name in ("aperture_cells", "phase_step_cells"):
            if not math.isfinite(float(getattr(self, name))) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.window_cells < 16:
            raise ValueError("window_cells must be >=16")
        if not 0 <= self.overlap_cells < self.window_cells:
            raise ValueError("overlap must be smaller than the window span")
        if self.erode_cells < 0 or self.neighbor_radius_cells < 0:
            raise ValueError("erosion/radius cannot be negative")
        if self.min_window_cells < 1:
            raise ValueError("minimum retry window must be positive")
        if (
            self.refine_angle_deg < 0 or self.refine_angle_step_deg <= 0
            or self.refine_phase_cells < 0 or self.refine_phase_step_cells <= 0
            or self.refine_min_total_sites < 1
            or self.refine_min_sites_per_parity < 1
            or self.refine_min_total_sites
            < 2 * self.refine_min_sites_per_parity
            or self.refine_heldout_degrade < 0
        ):
            raise ValueError("invalid pose-refinement policy")

@dataclass(frozen=True, slots=True)
class AffinePose:
    """Cell coordinates to native scan pixels for one E022 window."""

    origin_yx: PointYX
    jacobian_yx: tuple[tuple[float, float], tuple[float, float]]
    phase_yx: PointYX
    pitch_px: float
    angle_deg: float

    def __post_init__(self) -> None:
        matrix = np.asarray(self.jacobian_yx, np.float64)
        values = np.concatenate([
            np.asarray(self.origin_yx), matrix.ravel(),
            np.asarray(self.phase_yx), np.asarray([self.pitch_px, self.angle_deg]),
        ])
        if matrix.shape != (2, 2) or not np.isfinite(values).all():
            raise ValueError("pose contains non-finite or malformed geometry")
        if self.pitch_px <= 0 or float(np.linalg.det(matrix)) <= 0:
            raise ValueError("pose pitch and determinant must be positive")

    def matrix(self) -> np.ndarray:
        return np.asarray(self.jacobian_yx, np.float64)

    def points(self, cells_yx: np.ndarray) -> np.ndarray:
        cells = np.asarray(cells_yx, np.float64)
        return cells @ self.matrix().T + np.asarray(self.origin_yx)


@dataclass(frozen=True, slots=True)
class PoseWindow:
    """One independently fitted E022 observation window."""

    window_id: int
    region_index: int
    origin_yx_px: tuple[int, int]
    shape_yx_cells: tuple[int, int]
    depth: int = 0
    support_estimate: int = 0


@dataclass(frozen=True, slots=True)
class PoseSegment:
    """Authoritative fitted pose, including losing-address windows."""

    window: PoseWindow
    pose: AffinePose
    support_cells: int
    phase_contrast: float
    pitch_yx_px: PointYX
    orthogonality_error_deg: float


@dataclass(frozen=True, slots=True)
class CandidateScore:
    page: int
    origin_yx: CellYX
    rot_k: int
    search_mismatch: float
    validation_mismatch: float
    search_errors: int
    validation_errors: int
    search_support: int
    validation_support: int
    soft_z: float
    passes: bool
    route: str


@dataclass(frozen=True, slots=True)
class PilotObservation:
    """Selected pilot bit/evidence read retained for BCH voting."""

    page: int
    tile_yx: CellYX
    site_index: int
    bit: int
    evidence: float
    scan_id: str
    patch_id: int | None = None


@dataclass(frozen=True, slots=True)
class PlacedSegment:
    segment: PoseSegment
    page_origin_yx: CellYX
    rot_k: int
    audited_cells_yx: np.ndarray = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        cells = np.array(self.audited_cells_yx, dtype=np.int32, copy=True)
        if cells.ndim != 2 or cells.shape[1:] != (2,):
            raise ValueError("audited_cells_yx must be shaped (n,2)")
        cells.flags.writeable = False
        object.__setattr__(self, "audited_cells_yx", cells)


@dataclass(frozen=True, slots=True)
class PlacedPatch:
    patch_id: int
    region_index: int
    component: int
    route: str
    candidate: CandidateScore
    runner_ups: tuple[CandidateScore, ...]
    segment: PlacedSegment
    observations: tuple[PilotObservation, ...]
    redundant: bool
    page_cells_yx: np.ndarray = field(repr=False, compare=False)
    inherited_hint_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.segment, PlacedSegment):
            raise TypeError("placed patch segment must be PlacedSegment")
        if (self.inherited_hint_id is not None
                and (not isinstance(self.inherited_hint_id, str)
                     or not self.inherited_hint_id)):
            raise ValueError("inherited hint id must be non-empty text")
        if any(row.patch_id != self.patch_id for row in self.observations):
            raise ValueError(
                "placed patch contains a pilot observation with another owner")
        cells = np.array(self.page_cells_yx, dtype=np.int32, copy=True)
        if cells.ndim != 2 or cells.shape[1:] != (2,):
            raise ValueError("page_cells_yx must be shaped (n,2)")
        cells.flags.writeable = False
        object.__setattr__(self, "page_cells_yx", cells)


@dataclass(frozen=True, slots=True)
class UnresolvedPatch:
    patch_id: int
    region_index: int
    reason: str
    best: CandidateScore | None


WindowOutcome: TypeAlias = Literal[
    "pose_refused",
    "insufficient_support",
    "unresolved",
    "audit_refused",
    "accepted",
    "redundant",
    "parked",
]


@dataclass(frozen=True, slots=True)
class ParkedWindowFacts:
    """v0.33 phase-1 fall-through window, projected for durable parking.

    Geometry, fitted pose, and route facts only; the mop-up level
    re-samples pixels bit-exactly from these plus the region record.
    ``lattice_f`` is the region's 2x2 reciprocal-fundamental matrix as
    four row-major floats (None when the region never seeded one).
    """

    region_index: int
    window: PoseWindow
    segment: PoseSegment
    patch_id: int
    attempted_routes: tuple[str, ...]
    cell_pitch_px: float
    lattice_f: tuple[float, float, float, float] | None


@dataclass(frozen=True, slots=True)
class WindowAttempt:
    """Semantic ledger row for every E022 observation window attempted."""

    region_index: int
    window: PoseWindow
    outcome: WindowOutcome
    attempted_routes: tuple[str, ...]
    patch_id: int | None = None
    segment: PoseSegment | None = None
    candidate: CandidateScore | None = None
    reason: str = ""
    component: int | None = None
    predicted_origin_yx: CellYX | None = None
    predicted_residual_cells: float | None = None
    bch_errors: int | None = None
    rival: CandidateScore | None = None

    def __post_init__(self) -> None:
        if self.outcome not in (
            "pose_refused", "insufficient_support", "unresolved",
            "audit_refused", "accepted", "redundant", "parked",
        ):
            raise ValueError("invalid E022 window outcome")
        if not isinstance(self.reason, str):
            raise TypeError("window-attempt reason must be text")
        if any(not isinstance(route, str) or not route
               for route in self.attempted_routes):
            raise ValueError("attempted routes must be non-empty strings")
        if self.patch_id is not None and self.patch_id < 0:
            raise ValueError("window-attempt patch id cannot be negative")
        if self.component is not None and self.component < -1:
            raise ValueError("window-attempt component cannot be below -1")
        if self.predicted_residual_cells is not None and (
            not math.isfinite(float(self.predicted_residual_cells))
            or float(self.predicted_residual_cells) < 0.0
        ):
            raise ValueError("predicted residual must be finite and non-negative")
        if self.bch_errors is not None and self.bch_errors < 0:
            raise ValueError("BCH correction count cannot be negative")


@dataclass(frozen=True, slots=True)
class KnownWord:
    page: int
    tile_yx: CellYX
    expected_counter: int
    decoded_counter: int | None
    errors: int | None
    erasures: int
    contributor_patch_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        contributors = tuple(self.contributor_patch_ids)
        if contributors != tuple(sorted(set(contributors))):
            raise ValueError(
                "known-word contributor patch ids must be sorted and unique")
        if any(type(value) is not int or value < 0 for value in contributors):
            raise ValueError(
                "known-word contributor patch ids must be non-negative integers")
        if (self.decoded_counter is None) != (self.errors is None):
            raise ValueError(
                "known-position word decode and correction count must coexist")
        if (type(self.erasures) is not int
                or not 0 <= self.erasures <= bch.N_WORD):
            raise ValueError(
                f"known-position word erasures must be in [0, {bch.N_WORD}]")

    @property
    def observed_sites(self) -> int:
        return bch.N_WORD - self.erasures

    @property
    def certified(self) -> bool:
        return (
            self.decoded_counter is not None
            and self.decoded_counter == self.expected_counter
        )

    @property
    def conflict(self) -> bool:
        return (
            self.decoded_counter is not None
            and self.decoded_counter != self.expected_counter
        )


def quarantined_patch_ids(words: tuple[KnownWord, ...]) -> tuple[int, ...]:
    """Return the unique placements selected into contradictory BCH words."""
    return tuple(sorted({
        patch_id
        for word in words if word.conflict
        for patch_id in word.contributor_patch_ids
    }))


def promoted_continuation_hints(
    hints: tuple[PlacementHint, ...],
    words: tuple[KnownWord, ...],
) -> tuple[PlacementHint, ...]:
    """Remove every continuation proposal owned by a quarantined placement."""
    quarantined = frozenset(quarantined_patch_ids(words))
    return tuple(hint for hint in hints if hint.patch_id not in quarantined)


@dataclass(frozen=True, slots=True)
class AddressResult:
    placements: tuple[PlacedPatch, ...]
    unresolved: tuple[UnresolvedPatch, ...]
    words: tuple[KnownWord, ...]
    region_states: tuple[tuple[int, str], ...]
    hypotheses_evaluated: int
    continuation_hints: tuple[PlacementHint, ...] = ()
    attempts: tuple[WindowAttempt, ...] = ()
    parked_windows: tuple[ParkedWindowFacts, ...] = ()
    label_placements: tuple[PlacedPatch, ...] = ()

    def __post_init__(self) -> None:
        patch_ids = tuple(row.patch_id for row in self.placements)
        if len(patch_ids) != len(set(patch_ids)):
            raise ValueError("address result repeats an accepted patch id")
        parked_ids = tuple(row.patch_id for row in self.parked_windows)
        if (len(parked_ids) != len(set(parked_ids))
                or set(parked_ids) & set(patch_ids)):
            raise ValueError(
                "parked windows collide with accepted patch ids")
        # v0.33 D7: label placements are base-pass windows reconstructed
        # for M-level calibration pooling only — never owners, never
        # observation sources, and id-disjoint from this pass's work.
        label_ids = tuple(row.patch_id for row in self.label_placements)
        if (len(label_ids) != len(set(label_ids))
                or set(label_ids) & set(patch_ids)
                or set(label_ids) & set(parked_ids)):
            raise ValueError(
                "label placements collide with this pass's patch ids")
        if any(row.observations for row in self.label_placements):
            raise ValueError(
                "label placements must not carry observations")
        quarantined = frozenset(self.quarantined_patch_ids)
        if any(word.conflict and not word.contributor_patch_ids
               for word in self.words):
            raise ValueError(
                "conflicting known-position word has no placement contributor")
        if not quarantined.issubset(patch_ids):
            raise ValueError(
                "known-position conflict names an unknown accepted patch")
        if any(hint.patch_id in quarantined
               for hint in self.continuation_hints):
            raise ValueError(
                "quarantined placement leaked into continuation hints")

    @property
    def quarantined_patch_ids(self) -> tuple[int, ...]:
        return quarantined_patch_ids(self.words)

    @property
    def payload_placements(self) -> tuple[PlacedPatch, ...]:
        """Placements allowed to produce payload LLRs or pose refinement."""
        quarantined = frozenset(self.quarantined_patch_ids)
        return tuple(row for row in self.placements
                     if row.patch_id not in quarantined)

    @property
    def observations(self) -> tuple[PilotObservation, ...]:
        return tuple(obs for placed in self.placements for obs in placed.observations)
