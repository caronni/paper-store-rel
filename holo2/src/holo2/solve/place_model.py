"""Placement admission types: gates, budgets, config, pose vocabulary.

Ported from ``src/holo/receive/placement/{model,policy,defaults}.py`` at
594a465, refactored per H4-PLAN R4 — arithmetic exact, code holo2's own.
This is W0 sub-wave A1: the foundation the H4 placement kernel waves
(pose fit, pose audit, cold, words) and the family-``place`` provider
consume.  Nothing imports it yet; W0 changes no behaviour.

**Split at the cap** (the batched-Chien card, H4 W2-EXIT parallelism
line).  This file reached exactly 1000 lines, and the standing rule reads
a cap as a seam signal — split, never squeeze.  The seam was already
written into the file's own section rules, so
:mod:`~holo2.solve.place_admission` now holds WHAT the admission numbers
are (the carried constants, the three validators, the two derived bounds
:func:`~holo2.solve.place_admission.identifiability_support_floor` and
:func:`~holo2.solve.place_admission.hypothesis_count`, and
:data:`~holo2.solve.place_admission.OR9_FLOORS` itself), while this file
keeps the TYPES that consume them.  Every one of those names is
re-exported here, verbatim and unwrapped: the split moved text, not
addresses, and no importer or test changed a line.  The OR-9 ruling's
own statement moved with the table; read it there.

R4 freedoms exercised (code only): v1's three-clause
``isinstance(..., (int, np.integer))`` validation dance, repeated at
eight sites, is one helper (:func:`_int_at_least`) — its explicit
``np.bool_`` arm went, because ``np.bool_`` is an instance of neither
``int`` nor ``np.integer`` and the call still raises; the two alias
properties ``search_min_support``/``validation_min_support`` collapse
into :attr:`AttemptBudget.min_support`, whose docstring says what they
said; ``HISTORICAL_MIN_SUPPORT`` -> :data:`E022_SUPPORT_FLOOR_SITES` and
``GATE_TRUE``/``GATE_DECOY``/``GATE_GAP``/``VALIDATION_TRUE`` ->
``GATE_SEARCH_TRUE``/``GATE_RIVAL_DECOY``/``GATE_MINIMUM_GAP``/
``GATE_VALIDATION_TRUE`` (each spelled like the :class:`PlacementGate`
field it sets); ``PilotObservation.scan_id`` -> ``capture_id``, minus
its ``patch_id`` back-reference; the subdivision depth cap was a bare
literal (``geometry.py:572``) and is now a table row; ``defaults.py``'s
two private constants are public, because the table names them.

Arithmetic deliberately NOT touched: the entropy expression and its
``error == 0`` special case, ``int(math.ceil(...))`` (never ``np.rint``,
never ``int(np.ceil(...))`` — three different functions),
:func:`hypothesis_count`'s integer overhang counting, ``math.ldexp`` for
the word sphere probability (never a division), ``float64`` throughout
:class:`AffinePose`, the ``sorted(..., key=row_id)`` tie-break in
:meth:`PlacementDomainEnvelope.resolve`, and every qualification-id
string — an audit identity is data, so the budget route keys stay v1's
``cold``/``local``/``lower`` even though holo2's ruled route names are
``cold``/``chain``/``lower_hint``.

NOT PORTED from those three modules, and why:

* ``PlacementHint`` / ``HintKind`` / ``promoted_continuation_hints`` —
  lane-crossing continuation geometry.  holo2's footings own cross-lane
  transport, and since H4 W2's pull model holo2 has NO durable hint at
  all: a window consults the committed poses around it at fire time
  (``place_job.consult``), so a steer is never a record.
* ``ParkedWindowFacts`` — PL6 is a scheduling STATE in holo2, not a
  durable park record (H4-PLAN W3, census PL6).
* ``KnownWord``, ``quarantined_patch_ids`` — the PL7 quarantine reduce
  lands in W5 with ``MintRef.contributors`` as the contributor set.
* ``PlacedSegment``, ``PlacedPatch``, ``UnresolvedPatch``,
  ``WindowAttempt``, ``WindowOutcome``, ``AddressResult`` — ``place.py``'s
  dissolved ladder orchestration and its patch-ordinal minting; a holo2
  provider proposes ``PoseRecord`` + ``EvidenceObservation`` + a spend,
  and ``WindowRecord`` carries the outcome.
* ``PlacementConfig.cold_first_max_pages`` — route ORDERING for the
  dissolved ladder (``place.py:1630``); holo2 prices routes by
  eligibility, so a cold-first knob has nothing to order.
* ``words.stage_a_hypotheses`` — the Stage-A domain count is word-grid
  geometry (its slot grid is the decoder's), so it stays with the words
  wave and reaches the policy as the ``word_hypotheses`` argument: the
  policy is DATA, never a caller-supplied function (``policy.py``'s own
  doctrine).

Two names arrive here that H4-PLAN §2's module map lists elsewhere,
declared so no second copy can appear: :func:`hypothesis_count` (v1
``placement/search.py:211``) is pure attempt-domain arithmetic the budget
algebra owns, so the cold wave imports it from here; and
:class:`WordAttemptBudget` (v1 ``words.py:33``) is a budget, so this is
its home and the words wave imports it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np

from ..core import ResourceKey, require_sorted_unique
from ..format import FormatRowSpec, bch, pilots
# The OR-9 table, the two derived bounds and the three validators moved
# to ``place_admission`` when the 1000-line cap bit (the batched-Chien
# card's seam split); they are RE-EXPORTED here so that every importer in
# the tree — and every test — keeps naming ``place_model`` exactly as
# before.  This module is still the constants' address; it is no longer
# their text.
from .place_admission import (E022_LAYOUT_MIN_WINDOW_CELLS,  # noqa: F401
                              E022_MIN_WINDOW_CELLS, E022_OVERLAP_CELLS,
                              E022_SUBDIVISION_MAX_DEPTH,
                              E022_SUPPORT_FLOOR_SITES, E022_WINDOW_CELLS,
                              GATE_MINIMUM_GAP, GATE_RIVAL_DECOY,
                              GATE_SEARCH_TRUE, GATE_VALIDATION_TRUE,
                              MAX_LOWER_HINTS, OR9_FLOORS, PROVISIONAL_ALPHA,
                              PROVISIONAL_CHANNEL_BER_ENVELOPE,
                              PROVISIONAL_SUPPORT_MARGIN_SITES, AdmissionDatum,
                              DatumOrigin, admission_datum, hypothesis_count,
                              identifiability_support_floor)
# The three validators are this module's own tools, not part of the
# re-exported surface: a caller that needs one names its new home
# (``pose_audit`` does).
from .place_admission import _identity, _int_at_least, _ratio  # noqa: F401

PointYX: TypeAlias = tuple[float, float]
CellYX: TypeAlias = tuple[int, int]


# --------------------------------------------------------------- the gate

@dataclass(frozen=True, slots=True)
class PlacementGate:
    """Coupled placement-admission bars with explicit provenance.

    The four values form one qualified decision rule; production must
    never mix values from independently named profiles.  The historical
    E022 rule remains the default for differential tests, while a
    production profile carries its own frozen identifier.
    """

    search_true: float
    rival_decoy: float
    minimum_gap: float
    validation_true: float
    qualification_id: str

    def __post_init__(self) -> None:
        for label in ("search_true", "rival_decoy", "validation_true"):
            object.__setattr__(self, label, _ratio(
                label, getattr(self, label), high=0.5))
        object.__setattr__(self, "minimum_gap", _ratio(
            "minimum_gap", self.minimum_gap, high=0.5, include_zero=True))
        _identity("gate qualification_id", self.qualification_id)


HISTORICAL_E022_GATE = PlacementGate(
    GATE_SEARCH_TRUE,
    GATE_RIVAL_DECOY,
    GATE_MINIMUM_GAP,
    GATE_VALIDATION_TRUE,
    "paperholo/e022-v2/session-gap-gate",
)

# v0.30: identical numeric bars, but the decoy/gap arithmetic evaluates
# WHOLE-WORD rival mismatches (both parity classes), restoring the d=27
# floor against cross-page tile-lattice aliases whose search-class
# mismatch is structurally sub-0.20 at complete domains
# (docs/FULL-DOMAIN-RIVAL-ANALYSIS.md).  A distinct identity because the
# decision RULE changed; the historical row stays above as the recorded
# pre-v0.30 reference.  H4 W5 (L8) is where the rule itself lands.
V1_WHOLEWORD_RIVAL_GATE = PlacementGate(
    GATE_SEARCH_TRUE,
    GATE_RIVAL_DECOY,
    GATE_MINIMUM_GAP,
    GATE_VALIDATION_TRUE,
    "holo-v1/e022-v2-wholeword-rival/session-gap-gate",
)


# ------------------------------------------------------------- the budgets

@dataclass(frozen=True, slots=True)
class AttemptBudget:
    """Auditable complete-domain envelope for one search class.

    ``max_hypotheses`` is an upper bound, never a work limiter: an
    invocation whose complete domain is larger refuses before searching
    rather than selecting a prefix.  Each disjoint parity population must
    meet the larger of E022-v2's measured 30-site floor and e026's
    attempt-domain/BER-derived identifiability floor.

    ``familywise_false_accept`` is an explicit target and audit field.  It
    is deliberately absent from the floor formula: the record supplies no
    proved mapping from alpha to the weighted mismatch/rival decision, and
    structured v1 BCH fields are not Bernoulli(1/2).  Meeting that target
    remains a fresh v1 null/physical qualification duty, not arithmetic
    performed here.

    The ``gate`` default is v1's: the HISTORICAL gate, not the whole-word
    rival gate production runs under.  A caller that means production
    passes :data:`V1_WHOLEWORD_RIVAL_GATE` (as
    :class:`PlacementBudgetPolicy` always does).
    """

    max_hypotheses: int
    familywise_false_accept: float
    max_true_error_rate: float
    qualification_id: str
    gate: PlacementGate = HISTORICAL_E022_GATE
    support_margin_sites: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_hypotheses", _int_at_least(
            "max_hypotheses", self.max_hypotheses, 1))
        object.__setattr__(self, "familywise_false_accept", _ratio(
            "familywise_false_accept", self.familywise_false_accept,
            high=1.0))
        object.__setattr__(self, "max_true_error_rate", _ratio(
            "max_true_error_rate", self.max_true_error_rate, high=0.5,
            include_zero=True))
        _identity("qualification_id", self.qualification_id)
        if not isinstance(self.gate, PlacementGate):
            raise TypeError("gate must be a PlacementGate")
        object.__setattr__(self, "support_margin_sites", _int_at_least(
            "support_margin_sites", self.support_margin_sites, 0))

    @property
    def min_support(self) -> int:
        """The derived OR-9 floor, in sites.

        One number, applied to EACH independent parity population: the
        search parity and the held-out validation parity are separately
        floored by it (v1 spelled that as two alias properties).
        """
        return max(
            E022_SUPPORT_FLOOR_SITES,
            identifiability_support_floor(
                self.max_hypotheses, self.max_true_error_rate
            ) + self.support_margin_sites,
        )


@dataclass(frozen=True, slots=True)
class PlacementBudgets:
    """Separate complete-domain envelopes for each placement route.

    Field names are v1's route keys, which are also the strings the
    qualification ids are composed from: ``local`` is the holo2 ``chain``
    route (PL1) and ``lower`` the ``lower_hint`` route (PL2).  ``lower``
    is deliberately optional so a standalone run is numerically
    unchanged: supplying lower-scale hints without this explicit aggregate
    route budget is an error rather than a hidden expansion of ``local``.
    """

    cold: AttemptBudget
    local: AttemptBudget
    lower: AttemptBudget | None = None


@dataclass(frozen=True, slots=True)
class WordAttemptBudget:
    """Complete multi-slot domain and single-word union-bound declaration.

    A word of ``pilots.N_WORD_SITES`` bits lies within radius ``bch.T`` of
    one of the ``2**pilots.COUNTER_BITS`` pad-valid counter codewords with
    probability ``2**COUNTER_BITS * sum(C(N,i), i=0..T) / 2**N``.  For
    ``H`` declared phase hypotheses the conservative family-wise bound is
    ``H*p``.  The declared domain may exceed the phases physically
    attempted (trailing slots admit fewer fitting phases than the uniform
    per-slot declaration); the union bound only requires the declaration
    to dominate the attempts.  The receiver does not narrow this declared
    domain or assume independence between overlapping phases.
    """

    max_hypotheses: int
    familywise_false_accept: float
    qualification_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_hypotheses", _int_at_least(
            "max_hypotheses", self.max_hypotheses, 0))
        object.__setattr__(self, "familywise_false_accept", _ratio(
            "familywise_false_accept", self.familywise_false_accept,
            high=1.0))
        _identity("qualification_id", self.qualification_id)
        if self.random_union_bound > self.familywise_false_accept:
            raise ValueError(
                "declared Stage-A domain exceeds its false-accept spend: "
                f"bound={self.random_union_bound:.3g}, "
                f"alpha={self.familywise_false_accept:.3g}"
            )

    @property
    def single_word_probability(self) -> float:
        sphere = sum(math.comb(pilots.N_WORD_SITES, errors)
                     for errors in range(bch.T + 1))
        return math.ldexp(float(sphere),
                          pilots.COUNTER_BITS - pilots.N_WORD_SITES)

    @property
    def random_union_bound(self) -> float:
        return min(1.0, self.max_hypotheses * self.single_word_probability)


# ------------------------------------------- window, sampler, audit policy

@dataclass(frozen=True, slots=True)
class PlacementConfig:
    """The frozen E022-v2 window, sampler, refinement, and audit policy.

    A placement window owns one independently fitted affine pose.  The
    200-cell span, 40-cell overlap, and one level of four 70-cell-or-
    larger corner retries are the measured E022 geometry (each a row in
    :data:`OR9_FLOORS`); characterization metrology does not participate
    in receiver window sizing.
    """

    window_cells: int = E022_WINDOW_CELLS
    overlap_cells: int = E022_OVERLAP_CELLS
    subdivide: bool = True
    min_window_cells: int = E022_MIN_WINDOW_CELLS
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
    #: Run the bounded refinement's 7x9x9 grid as ONE stacked
    #: interpolation instead of 567 scalar ones — two bit-identical arms
    #: (``pose_audit``'s two ``*_refine_scan``; evidence
    #: ``measure/refine_equivalence.py``). ON by user ruling 2026-08-17
    #: (1.9x kernel, bit-identical); the scalar arm stays as the oracle.
    batched_refine: bool = True
    #: Run Stage A's BCH word sweep through the batched twin
    #: (``format/bch_batch.py``) instead of the carried scalar
    #: ``bch.decode_many`` — same five acceptance rules, same row order,
    #: bit-identical outputs, with BOTH per-candidate loops — the Chien
    #: search and Berlekamp-Massey — evaluated as arrays over the whole
    #: candidate block instead of once per candidate.  The sweep measured
    #: ~72% of all receiver CPU (the GIL diagnosis), of which the Chien
    #: loop was 30.0% and BM the other 25.1%.  Evidence:
    #: ``measure/bch_equivalence.py``.  ON by user ruling 2026-08-17
    #: (serial 1.63x, bit-identical on 382k rows), and the LOCKSTEP BM
    #: card then took the same arm from 106 to 36 ms at H=4096 and its
    #: GIL-free fraction from 0.15 to 0.95; the carried scalar path is
    #: THE ORACLE and stays reachable.
    batched_word_sweep: bool = True
    # (There is no ``batched_fit_phase`` row: the window fit's stacked
    # phase grid was built, proved bit-identical and DELETED 2026-08-17 —
    # 1.07x on a kernel worth 3.9% of the serial wall, because the
    # objective's own stride pins every call at ~1,600 points whatever
    # the window size.  ``pose_fit``'s module docstring carries the
    # refutation and its numbers; the arm itself survives as a source
    # reconstruction in ``measure/fit_phase_equivalence.py``.)
    audit_bad: float = 0.35
    audit_good: float = 0.20
    audit_min_sites: int = 15
    audit_post_bar: float = 0.25

    def __post_init__(self) -> None:
        for name in ("aperture_cells", "phase_step_cells"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
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


# ------------------------------------------------ what the kernel produces

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
            np.asarray(self.phase_yx),
            np.asarray([self.pitch_px, self.angle_deg]),
        ])
        if matrix.shape != (2, 2) or not np.isfinite(values).all():
            raise ValueError("pose contains non-finite or malformed geometry")
        if self.pitch_px <= 0 or float(np.linalg.det(matrix)) <= 0:
            raise ValueError("pose pitch and determinant must be positive")

    def matrix(self) -> np.ndarray:
        return np.asarray(self.jacobian_yx, np.float64)

    def points(self, cells_yx: np.ndarray) -> np.ndarray:
        cells = np.asarray(cells_yx, np.float64)
        points: np.ndarray = (
            cells @ self.matrix().T + np.asarray(self.origin_yx))
        return points


@dataclass(frozen=True, slots=True)
class PoseWindow:
    """One independently fitted E022 observation window.

    ``window_id`` is the FIT-LOCAL ordinal v1 mints when it lays a region
    out (and increments for subdivision children) — never a holo2
    ``WindowId``; the provider maps a window to its durable key.
    """

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
    """One scored placement hypothesis, as the gate saw it."""

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
    """Selected pilot bit/evidence read retained for BCH voting.

    ``capture_id`` is v1's ``scan_id`` under holo2's word for it.

    ``pose_id`` is v1's ``patch_id`` back-reference under holo2's
    provenance vocabulary (H4 W5): the reduce below needs to name WHO
    contributed a read, and holo2 names a placement by its pose key
    rather than by a patch ordinal.  A1 dropped the field because the
    reduce that reads it was deferred to this wave; it comes back
    spelled the way ``MintRef.contributors`` spells provenance.
    ``None`` is a read nobody attributed — a harness's, never
    production's — and it simply contributes no contributor.
    """

    page: int
    tile_yx: CellYX
    site_index: int
    bit: int
    evidence: float
    capture_id: str
    pose_id: ResourceKey | None = None


@dataclass(frozen=True, slots=True)
class KnownWord:
    """One known-position word read, as the W5 reduce returns it.

    v1 ``placement/model.py:547-589``, carried whole.  The position is
    KNOWN — a placement already said which tile sits here — so the read
    is a CHECK, not a search: ``certified`` is the check passing,
    ``conflict`` is a legal decode that names a DIFFERENT tile, and a
    failure to decode at all is neither (v1's "failures never veto
    placement").

    ``contributors`` is v1's ``contributor_patch_ids`` under holo2's
    pose-key provenance: the placements whose reads were SELECTED into
    the vote that produced ``decoded_counter``.  Sorted and unique,
    which is :class:`~holo2.solve.records.MintRef`'s own contributor
    shape.
    """

    page: int
    tile_yx: CellYX
    expected_counter: int
    decoded_counter: int | None
    errors: int | None
    erasures: int
    contributors: tuple[ResourceKey, ...] = ()

    def __post_init__(self) -> None:
        require_sorted_unique(self.contributors, "KnownWord.contributors")
        if (self.decoded_counter is None) != (self.errors is None):
            raise ValueError(
                "known-position word decode and correction count must coexist")
        if not 0 <= self.erasures <= bch.N_WORD:
            raise ValueError(
                f"known-position word erasures must be in [0, {bch.N_WORD}]")

    @property
    def observed_sites(self) -> int:
        return bch.N_WORD - self.erasures

    @property
    def certified(self) -> bool:
        return (self.decoded_counter is not None
                and self.decoded_counter == self.expected_counter)

    @property
    def conflict(self) -> bool:
        return (self.decoded_counter is not None
                and self.decoded_counter != self.expected_counter)


# -------------------------------------------------------------- the policy

@dataclass(frozen=True, slots=True)
class PlacementDomainEnvelope:
    """Frozen receiver-wide hypothesis counts shared by every row branch.

    A branch still searches only its own complete row domain.  The larger
    counts here make every branch's admission record account for the union
    of all rows which the discovery receiver promised to trial.
    """

    row_ids: tuple[str, ...]
    cold_hypotheses: int
    local_hypotheses: int
    lower_hypotheses: int
    word_hypotheses: int

    def __post_init__(self) -> None:
        if (not self.row_ids or tuple(sorted(self.row_ids)) != self.row_ids
                or len(set(self.row_ids)) != len(self.row_ids)):
            raise ValueError(
                "receiver-wide row ids must be sorted, unique, and non-empty")
        for label in ("cold_hypotheses", "local_hypotheses",
                      "lower_hypotheses", "word_hypotheses"):
            _int_at_least(label, getattr(self, label), 1)

    @property
    def policy_id(self) -> str:
        """Readable page-domain identity (data, not code — G2 allows it)."""
        return (
            "holo/e022-receiver-wide-domain/kiss-v1/"
            f"rows={','.join(self.row_ids)}"
        )

    @classmethod
    def resolve(
        cls,
        rows: tuple[tuple[FormatRowSpec, tuple[int, ...]], ...],
        config: PlacementConfig,
        *,
        word_hypotheses_per_row: int,
    ) -> "PlacementDomainEnvelope":
        """Union the declared domains of every row the receiver trials.

        ``word_hypotheses_per_row`` is the Stage-A count for a
        ``window_cells``-square patch (``words.stage_a_hypotheses``): the
        same shape for every row, so v1's per-row product is exact here.
        """
        if not rows:
            raise ValueError("receiver-wide domain needs at least one row")
        if type(config) is not PlacementConfig:
            raise TypeError(
                "receiver-wide domain needs an exact PlacementConfig")
        word_per_row = _int_at_least(
            "word_hypotheses_per_row", word_hypotheses_per_row, 1)
        ordered = tuple(sorted(rows, key=lambda item: item[0].row_id))
        row_ids = tuple(row.row_id for row, _pages in ordered)
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("receiver-wide domain repeats a format row")
        patch_shape = (config.window_cells, config.window_cells)
        cold = 0
        for row, pages in ordered:
            _check_page_domain(row, pages, "discovery page domain")
            cold += hypothesis_count(
                patch_shape,
                row.cells_yx,
                len(pages),
                allow_overhang=config.allow_overhang,
            )
        local_per_row = (2 * config.neighbor_radius_cells + 1) ** 2
        return cls(
            row_ids,
            cold,
            local_per_row * len(ordered),
            local_per_row * MAX_LOWER_HINTS * len(ordered),
            word_per_row * len(ordered),
        )


def _check_page_domain(row: FormatRowSpec, pages: tuple[int, ...],
                       label: str) -> None:
    """Refuse an empty, repeating, or out-of-row page domain."""
    if (not pages or len(set(pages)) != len(pages)
            or any(type(page) is not int or not 0 <= page < row.n_pages
                   for page in pages)):
        raise ValueError(f"{row.row_id} has an invalid {label}")


@dataclass(frozen=True, slots=True)
class PlacementBudgetPolicy:
    """One immutable, auditable placement-admission contract.

    Search-domain sizes remain derived from the actual format, page
    domain, lower-hint inventory, and frozen E022 geometry.  The fields
    here are the coupled statistical choices which cannot be inferred from
    those facts.  The policy is DATA, not a caller-supplied function: its
    durable identity is derived from every result-affecting field, so
    changing a gate, error envelope, support margin, or false-accept
    declaration necessarily changes the receiver policy recorded by the
    session.
    """

    qualification_id: str
    familywise_false_accept: float
    max_true_error_rate: float
    gate: PlacementGate
    support_margin_sites: int
    word_familywise_false_accept: float
    word_qualification_id: str

    def __post_init__(self) -> None:
        _identity("placement qualification id", self.qualification_id)
        object.__setattr__(self, "familywise_false_accept", _ratio(
            "placement familywise false-accept target",
            self.familywise_false_accept, high=1.0))
        object.__setattr__(self, "max_true_error_rate", _ratio(
            "placement maximum true-error rate", self.max_true_error_rate,
            high=0.5, include_zero=True))
        if type(self.gate) is not PlacementGate:
            raise TypeError("placement gate must be an exact PlacementGate")
        object.__setattr__(self, "support_margin_sites", _int_at_least(
            "placement support margin", self.support_margin_sites, 0))
        object.__setattr__(self, "word_familywise_false_accept", _ratio(
            "word familywise false-accept target",
            self.word_familywise_false_accept, high=1.0))
        _identity("word qualification id", self.word_qualification_id)

    @property
    def policy_id(self) -> str:
        """Hand-bumped semantic identity (ground rule G2).

        Constants are data, not identity: editing a numeric field does not
        invalidate existing state by itself.  When the placement POLICY
        semantics change, bump the version literal here by hand — that is
        the whole mechanism, exactly as G2 intended.
        """
        return f"{self.qualification_id}/kiss-v1"

    def resolve(
        self,
        row: FormatRowSpec,
        pages: tuple[int, ...],
        n_lower: int,
        config: PlacementConfig,
        *,
        word_hypotheses: int,
        domain_envelope: PlacementDomainEnvelope | None = None,
    ) -> tuple[PlacementBudgets, WordAttemptBudget]:
        """Derive complete-domain budgets without truncating any search."""
        if not isinstance(row, FormatRowSpec):
            raise TypeError("placement budget needs a FormatRowSpec")
        _check_page_domain(row, pages, "page domain")
        if type(config) is not PlacementConfig:
            raise TypeError("placement budget needs an exact PlacementConfig")
        lower_count = _int_at_least("lower-hint count", n_lower, 0)
        # Zero is legal: a patch too small for one Stage-A slot declares
        # an empty word domain, exactly as v1's WordAttemptBudget allows.
        word_h = _int_at_least("word hypotheses", word_hypotheses, 0)
        if (domain_envelope is not None
                and type(domain_envelope) is not PlacementDomainEnvelope):
            raise TypeError(
                "placement domain envelope must be immutable declarative data")
        patch_shape = (config.window_cells, config.window_cells)
        cold_h = hypothesis_count(
            patch_shape,
            row.cells_yx,
            len(pages),
            allow_overhang=config.allow_overhang,
        )
        local_h = (2 * config.neighbor_radius_cells + 1) ** 2

        route_domains = {
            "cold": cold_h,
            "local": local_h,
            "lower": local_h * lower_count,
        }
        if domain_envelope is not None:
            if row.row_id not in domain_envelope.row_ids:
                raise ValueError(
                    "placement format is outside the receiver-wide domain")
            actual_domains = (
                ("cold", cold_h, domain_envelope.cold_hypotheses),
                ("local", local_h, domain_envelope.local_hypotheses),
                (
                    "lower",
                    local_h * lower_count,
                    domain_envelope.lower_hypotheses,
                ),
                ("word", word_h, domain_envelope.word_hypotheses),
            )
            for route, actual, admitted in actual_domains:
                if admitted < actual:
                    raise ValueError(
                        f"receiver-wide {route} domain does not cover "
                        "the actual format hypotheses")
            route_domains.update({
                "cold": domain_envelope.cold_hypotheses,
                "local": domain_envelope.local_hypotheses,
                "lower": domain_envelope.lower_hypotheses,
            })

        def attempt(route: str) -> AttemptBudget:
            return AttemptBudget(
                route_domains[route],
                self.familywise_false_accept,
                self.max_true_error_rate,
                (
                    f"{self.qualification_id}/{route}"
                    if domain_envelope is None
                    else f"{self.qualification_id}/{route}/"
                         f"{domain_envelope.policy_id}"
                ),
                gate=self.gate,
                support_margin_sites=self.support_margin_sites,
            )

        budgets = PlacementBudgets(
            attempt("cold"),
            attempt("local"),
            (None if lower_count == 0
             else attempt("lower")),
        )
        word = WordAttemptBudget(
            (
                word_h
                if domain_envelope is None
                else domain_envelope.word_hypotheses
            ),
            self.word_familywise_false_accept,
            (
                self.word_qualification_id
                if domain_envelope is None
                else f"{self.word_qualification_id}/"
                     f"{domain_envelope.policy_id}"
            ),
        )
        return budgets, word


# ---------------------------------------------- the operational instance
# v1 defaults.py: operational but unqualified format-v1 placement
# defaults.  These are the exact historical E021--E023c stand-ins
# previously used only by synthetic qualification.  Making them
# operational does not turn them into production evidence: the runtime
# marks the resulting pipeline PROVISIONAL and warns on every run until
# the outstanding physical/null and complete-domain yield duties are
# frozen.

PROVISIONAL_V1_PLACEMENT_POLICY = PlacementBudgetPolicy(
    qualification_id=(
        "candidate/holo-v1-e026+e022/requires-physical-null"),
    familywise_false_accept=PROVISIONAL_ALPHA,
    max_true_error_rate=PROVISIONAL_CHANNEL_BER_ENVELOPE,
    gate=V1_WHOLEWORD_RIVAL_GATE,
    support_margin_sites=PROVISIONAL_SUPPORT_MARGIN_SITES,
    word_familywise_false_accept=PROVISIONAL_ALPHA,
    word_qualification_id=(
        "holo-v1/e022-single-word-multi-slot-union-bound"),
)

V1_PRODUCTION_QUALIFICATION_NOTES = (
    "the v1 physical/null false-accept gate, channel-BER envelope, and "
    "support safety margin still require frozen qualification",
    "the 0.176 complete-domain rival refusal was diagnosed as a "
    "parity-concentrated cross-page alias and the v0.30 whole-word rival "
    "gate restores the d=27 floor (synthetically verified); real-capture "
    "full-domain yield and resource profile remain unqualified",
)


__all__ = [
    "AdmissionDatum", "AffinePose", "AttemptBudget", "CandidateScore",
    "CellYX", "DatumOrigin", "E022_LAYOUT_MIN_WINDOW_CELLS",
    "E022_MIN_WINDOW_CELLS",
    "E022_OVERLAP_CELLS", "E022_SUBDIVISION_MAX_DEPTH",
    "E022_SUPPORT_FLOOR_SITES", "E022_WINDOW_CELLS",
    "GATE_MINIMUM_GAP", "GATE_RIVAL_DECOY", "GATE_SEARCH_TRUE",
    "GATE_VALIDATION_TRUE", "HISTORICAL_E022_GATE", "KnownWord",
    "MAX_LOWER_HINTS",
    "OR9_FLOORS", "PROVISIONAL_ALPHA",
    "PROVISIONAL_CHANNEL_BER_ENVELOPE",
    "PROVISIONAL_SUPPORT_MARGIN_SITES",
    "PROVISIONAL_V1_PLACEMENT_POLICY", "PilotObservation",
    "PlacementBudgetPolicy", "PlacementBudgets", "PlacementConfig",
    "PlacementDomainEnvelope", "PlacementGate", "PointYX", "PoseSegment",
    "PoseWindow", "V1_PRODUCTION_QUALIFICATION_NOTES",
    "V1_WHOLEWORD_RIVAL_GATE", "WordAttemptBudget", "admission_datum",
    "hypothesis_count", "identifiability_support_floor",
]
