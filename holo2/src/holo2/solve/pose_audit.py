"""Score, audit, refine, harvest: the E022 placement decision kernel.

Ported from ``src/holo/receive/placement/search.py`` at 594a465 (the
score/audit/refine/harvest half; the cold-correlation half is
``solve/cold.py``'s), refactored per H4-PLAN R4 — **arithmetic exact,
code holo2's own**.  This is W0 sub-wave A2.  Nothing imports it yet; W0
changes no behaviour.

What lives here is the decision kernel a placement route runs once it has
a pose and an address hypothesis:

* :class:`ScoreMemo` — the parity-split weighted-mismatch scorer, with
  v1's invocation-scoped, full-key, no-eviction memo.  The memo stays an
  explicit OBJECT the caller owns and hands to a route: a module-level
  cache would outlive an invocation, and its key would then have to carry
  the sample identity the caller already knows (feedback:
  ask-what-the-producer-knows).
* :func:`parity_mask` / :data:`WHOLE_WORD_PARITY` — the frozen E022 split
  and the sentinel that turns it off.
* :func:`local_search` / :func:`predict_from_anchor` — the chain route's
  affine transport and its bounded neighbourhood.
* :func:`refine_patch_pose` — E022's bounded pose refinement.
* :func:`fragment_reference_sites` / :func:`audit_segment` /
  :func:`observations_for_segment` — the correspondence set, the
  binomial-impurity straddle audit over it, and the pilot reads harvested
  under the audited core.

**Arithmetic deliberately NOT touched** (the R4 checklist, per idiom):

* :meth:`ScoreMemo.parity_score`'s per-call re-casts — ``evidence`` to
  ``float32``, ``bits`` to ``uint8``, ``mask`` to ``bool``,
  ``expected_sign`` to ``float32`` — so the correlation and weight sums
  are numpy's pairwise float32 reduction, not a float64 promotion, and
  ``z``'s ``np.sqrt`` is the one float64 step v1 has.
* ``int(np.ceil(cut))`` at the audit change-point edge (never ``np.rint``,
  never ``round``), and ``np.argsort(kind="stable")`` for the coordinate
  order it cuts on.
* ``int(round(...))`` in :func:`predict_from_anchor` — numpy's
  half-to-EVEN rounding of a ``float64``, which is what the exact-half
  offsets a rot90 transport produces land on.
* :func:`refine_patch_pose`'s ``float64`` ``expected_sign`` (a different
  dtype from the scorer's, on purpose), its
  ``np.arange(-a, a + 1e-9, step)`` grid bounds, and its strict-``>``
  first-wins scan over that grid in (angle, dy, dx) order —
  :func:`_scalar_refine_scan`, lifted out of the function body verbatim
  when the batched twin arrived, and unchanged in it.
* :func:`local_search`'s candidate order — built ``dy`` outer, ``dx``
  inner, then sorted on ``(-soft_z, origin_y, origin_x)`` by Python's
  stable sort.
* The straddle audit's four-pass ``(0, 1, 0, 1)`` axis schedule and its
  strict-``<`` first-wins impurity scan.

**R4 freedoms taken** (code only, all arithmetic-identical):

* v1's per-axis change-point scan is :func:`_best_change_point`; its two
  copies of the ``(131*y + 17*x) & 1`` site parity are
  :func:`_site_parity`; and :func:`refine_patch_pose`'s two verbatim
  copies of the small-angle rotation matrix are :func:`_rotation_2x2`.
* ``HISTORICAL_MIN_SUPPORT`` is A1's ``E022_SUPPORT_FLOOR_SITES``, and
  the ``min_support`` validation dance is A1's ``_int_at_least`` (a
  same-package private helper, which the layering law allows; it moved
  with the OR-9 table to ``place_admission`` at the cap split — its
  message reads ``... must be an integer >= 1`` where v1 said ``... must
  be a positive integer``; text, not arithmetic).
* :func:`observations_for_segment` builds A1's
  :class:`~holo2.solve.place_model.PilotObservation`: ``scan_id`` is
  ``capture_id``, and ``patch_id`` is GONE with v1's patch ordinals — so
  the observation carries no back-reference and the caller's provenance
  is the pose key plus ``MintRef.contributors``.
* ``pose_metrics``'s four returns are three inlined scalars in
  :func:`refine_patch_pose`: only pitch_y, pitch_x and the angle build the
  refined :class:`~holo2.solve.place_model.AffinePose`, and the fourth
  (the orthogonality error) is a FIT diagnostic this kernel discards.  The
  three expressions are ``pose_metrics``' own, verbatim.

**The refinement's two arms** (H4 W2-EXIT parallelism line, first card).
The 7x9x9 grid has TWO implementations of one arithmetic, chosen by
:attr:`~holo2.solve.place_model.PlacementConfig.batched_refine`:
:func:`_scalar_refine_scan` (the original, default, and oracle) issues
one ``map_coordinates`` and two ``np.mean`` per hypothesis;
:func:`_batched_refine_scan` issues one of each for the whole grid.  They
are bit-identical by construction — see that function's docstring for the
clause-by-clause argument and its winner-selection semantics — and the
population evidence is ``holo2/measure/refine_equivalence.py``, which is
NOT a collected test and is run by path.

The switch reaches no other kernel, and :func:`local_search` is the
reason worth stating: its 49 hypotheses are a bounded sweep of the
ORIGIN, not of the pose, so all 49 read the SAME window sample through
:class:`ScoreMemo` — there is no interpolation in it at all, and hence no
batched sampler to drop out of it.  A grid that re-samples is the only
kind this trick applies to, and the refinement is the only such grid in
this module.

**Cross-worker seams — RECONCILED by W0-B** (H4-PLAN §3-W0-B; W0-A2 built
this module in parallel with the pose-fit, reference and cold ports):

* The five structural Protocols are gone.  Nominal imports now:
  :class:`~holo2.solve.reference.ReferencePage` and
  :class:`~holo2.solve.reference.ReferenceFieldProvider`
  (``solve/reference.py``), :class:`~holo2.solve.pose_fit.SegmentSample`,
  :class:`~holo2.solve.pose_fit.AddressPatch` and
  :class:`~holo2.solve.pose_fit.PreparedRegion` (``solve/pose_fit.py``) —
  no signature changes.
* ``sample_segment`` still arrives as the injected ``resample`` callable
  (:data:`SegmentSampler`, generic in the region type so a caller keeps
  its own): W1 binds the call site, not this reconcile.
* ``overlap_slices`` and ``rotation_affine`` are imported from
  ``solve/reference.py``; this module's private duplicates are deleted.
* :class:`SearchOutcome` stays declared HERE, and cold and the word
  route both import it from this module; ``solve/cold.py``'s
  field-for-field duplicate is deleted.
* ``observations_for_segment`` still takes ``family_seed`` as an explicit
  keyword — the provider-surface question this note flagged stays open.

NOT PORTED from ``search.py``, and why:

* ``correlate_patch``, ``_ColdMapGeometry``, ``_cold_map_geometries``,
  ``_signed_search_field``, ``_page_candidate_map`` — the Lane-C cold
  search, ``solve/cold.py``'s (H4-PLAN W4).
* ``_rival_gate`` — the rival bar has exactly one consumer, and it is
  ``correlate_patch``.  It goes to ``solve/cold.py`` with its caller (the
  rule ITSELF lands in W5/L8 with the whole-word gate; A1 already carries
  both :class:`~holo2.solve.place_model.PlacementGate` rows).
  :data:`WHOLE_WORD_PARITY` stays HERE because it is
  :meth:`ScoreMemo.parity_score`'s own sentinel — the scorer is what
  interprets it; cold imports it from this module.
* ``hypothesis_count`` — A1 declared it in ``place_model`` (pure
  attempt-domain arithmetic the budget algebra owns).
* ``from .. import _parallel`` — v1's cold-path worker-count hatch.  H4
  ruled the pool is the engine's (`_parallel` is a declared adaptation in
  the cold wave); nothing in THIS half of search.py touched it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypeAlias, TypeVar

import numpy as np
from scipy import ndimage

from ..core import ResourceKey
from ..format import pilots
from .place_admission import _int_at_least
from .place_model import (E022_SUPPORT_FLOOR_SITES, HISTORICAL_E022_GATE,
                          AffinePose, AttemptBudget,
                          CandidateScore, CellYX, PilotObservation,
                          PlacementConfig, PlacementGate, PoseSegment)
from .pose_fit import AddressPatch, PreparedRegion, SegmentSample
from .reference import (ReferenceFieldProvider, ReferencePage,
                        overlap_slices, rotation_affine)

def rival_gate(best_mismatch: float, rival_mismatch: float,
               gate: PlacementGate = HISTORICAL_E022_GATE) -> bool:
    """Exact rival bar: strict decoy, inclusive qualified gap.

    Both inputs are WHOLE-WORD mismatches since v0.30 (all overlap
    sites, both parity classes): the decoy bar restores the d=27
    argument against tile-lattice aliases, whose search-class mismatch
    is structurally below 0.20 at complete domains while their
    whole-word mismatch is >= 0.27.  The numeric bars are unchanged.

    It lives HERE since H4 W5 (L8), with the rest of the shared
    placement kernel, because the rule change gave it a second consumer:
    the cold route asks it of its map tops (``cold.correlate_patch``)
    and the word route asks it of its decoded candidates
    (``placement.decode_word_address``).  One bar, one arithmetic, two
    rival sets.
    """
    return (rival_mismatch > gate.rival_decoy
            and rival_mismatch - best_mismatch >= gate.minimum_gap)


WHOLE_WORD_PARITY = 2
"""``parity_score`` sentinel: score ALL overlap sites, both parity classes.

v0.30 whole-word rival evaluation.  The d=27 address-code floor binds full
words; the parity split can concentrate a cross-page alias's difference
codeword into as few as 7 of 45 search-class bits (measured family floor
0.156 — docs/FULL-DOMAIN-RIVAL-ANALYSIS.md), so decoy questions are asked
on the whole word while the winner's own admission remains parity-split.
"""


# ------------------------------------------------------ cross-worker seams

ContextT = TypeVar("ContextT", bound=PreparedRegion)

SegmentSampler: TypeAlias = Callable[
    [ContextT, PoseSegment], SegmentSample | None]
"""``pose_fit.sample_segment``, injected into the refiner.

Generic in the region type (bound to
:class:`~holo2.solve.pose_fit.PreparedRegion`) so a caller keeps its own
subtype: the sampler is contravariant in it.
"""


# ---------------------------------------------------------- what it returns

@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """One route's complete admission decision, as the gate reached it."""

    accepted: bool
    best: CandidateScore | None
    runner_ups: tuple[CandidateScore, ...]
    hypotheses: int
    reason: str
    predicted_origin_yx: CellYX | None = None
    predicted_residual_cells: float | None = None
    bch_errors: int | None = None
    support_floor: int = E022_SUPPORT_FLOOR_SITES
    rival: CandidateScore | None = None
    # Set only by the word route: the (tile_y, tile_x) whose BCH word the
    # seeder decoded to produce this address (v0.43 pane-C authority
    # tri-state).  Diagnostic provenance only — never read by admission.
    word_tile_yx: CellYX | None = None


@dataclass(frozen=True, slots=True)
class WindowRefinementOutcome:
    """The re-sampled window a bounded pose refinement produced."""

    sample: SegmentSample
    delta_angle_deg: float
    delta_phase_yx: tuple[float, float]
    heldout_before: float
    heldout_after: float


# ------------------------------------------------------------- the parities

def parity_mask(
    shape: tuple[int, int], origin_yx: tuple[int, int], parity: int
) -> np.ndarray:
    """Frozen E022 split ``(131*y + 17*x)&1 == parity``."""
    height, width = shape
    y0, x0 = origin_yx
    rows = (np.arange(height, dtype=np.intp) + (y0 & 1)) & 1
    cols = (np.arange(width, dtype=np.intp) + (x0 & 1)) & 1
    mask: np.ndarray = (rows[:, None] ^ cols[None, :]) == int(parity)
    return mask


def _site_parity(absolute_yx: np.ndarray) -> np.ndarray:
    """The same frozen split, read off absolute page coordinates."""
    parity: np.ndarray = (
        (absolute_yx[:, 0] * 131 + absolute_yx[:, 1] * 17) & 1
    ).astype(bool)
    return parity


# ---------------------------------------------------------------- the score

class ScoreMemo:
    """Invocation-local, full-key, no-eviction memo for repeated probes.

    The memo is the CALLER's: one route invocation builds one, hands it to
    the primitives it calls, and drops it.  The key carries the complete
    probe identity (sample, page, origin, orientation, parity class), so
    nothing about a hit depends on when it was taken.
    """

    def __init__(self, provider: ReferenceFieldProvider) -> None:
        self.provider = provider
        self._scores: dict[
            tuple[int, int, int, int, int, int],
            tuple[float, int, int, float],
        ] = {}
        self.requests = 0
        self.hits = 0

    def parity_score(
        self,
        sample_key: int,
        evidence: np.ndarray,
        bits: np.ndarray,
        mask: np.ndarray,
        page: int,
        origin_yx: tuple[int, int],
        rot_k: int,
        parity: int,
    ) -> tuple[float, int, int, float]:
        """Return weighted mismatch, hard errors, support, and soft z."""
        key = (
            int(sample_key), int(page), int(origin_yx[0]), int(origin_yx[1]),
            int(rot_k) % 4, int(parity),
        )
        self.requests += 1
        cached = self._scores.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        reference: ReferencePage = self.provider.page(page)
        observed = np.rot90(np.asarray(evidence, np.float32), rot_k)
        hard = np.rot90(np.asarray(bits, np.uint8), rot_k)
        keep = np.rot90(np.asarray(mask, bool), rot_k)
        slices = overlap_slices(
            origin_yx, observed.shape, reference.values.shape
        )
        if slices is None:
            result = (1.0, 0, 0, -np.inf)
            self._scores[key] = result
            return result
        page_y, page_x, frag_y, frag_x = slices
        selected = reference.sites[page_y, page_x] & keep[frag_y, frag_x]
        if parity != WHOLE_WORD_PARITY:
            selected &= parity_mask(
                selected.shape,
                (int(page_y.start or 0), int(page_x.start or 0)),
                parity,
            )
        support = int(selected.sum())
        if support == 0:
            result = (1.0, 0, 0, -np.inf)
            self._scores[key] = result
            return result
        expected_bits = reference.values[page_y, page_x][selected]
        observed_evidence = observed[frag_y, frag_x][selected]
        expected_sign = 1.0 - 2.0 * expected_bits.astype(np.float32)
        weights = np.abs(observed_evidence)
        correlation = float(np.sum(expected_sign * observed_evidence))
        total_weight = float(weights.sum())
        mismatch = (
            (total_weight - correlation) / (2.0 * total_weight)
            if total_weight > 0.0 else 1.0
        )
        observed_bits = hard[frag_y, frag_x][selected]
        errors = int(np.count_nonzero(observed_bits != expected_bits))
        z = correlation / np.sqrt(max(total_weight, 1e-9))
        result = (float(mismatch), errors, support, float(z))
        self._scores[key] = result
        return result

    def candidate(
        self,
        sample_key: int,
        evidence: np.ndarray,
        bits: np.ndarray,
        mask: np.ndarray,
        page: int,
        origin_yx: tuple[int, int],
        rot_k: int,
        budget: AttemptBudget,
        route: str,
    ) -> CandidateScore:
        """Score both parity classes and apply the coupled admission bars."""
        floor = budget.min_support
        search = self.parity_score(
            sample_key, evidence, bits, mask, page, origin_yx, rot_k, 0
        )
        validation = self.parity_score(
            sample_key, evidence, bits, mask, page, origin_yx, rot_k, 1
        )
        passes = (
            search[2] >= floor
            and validation[2] >= floor
            and search[0] < budget.gate.search_true
            and validation[0] < budget.gate.validation_true
        )
        return CandidateScore(
            int(page), (int(origin_yx[0]), int(origin_yx[1])),
            int(rot_k) % 4,
            search[0], validation[0], search[1], validation[1],
            search[2], validation[2], search[3], passes, route,
        )


# ------------------------------------------------------- the chain route

def predict_from_anchor(
    anchor_pose: AffinePose,
    anchor_shape: tuple[int, int],
    anchor_origin_yx: tuple[int, int],
    rot_k: int,
    target_pose: AffinePose,
    target_shape: tuple[int, int],
) -> CellYX:
    """Transport a target patch through an accepted full affine anchor."""
    delta_pixels = (
        np.asarray(target_pose.origin_yx) - np.asarray(anchor_pose.origin_yx)
    )
    delta_cells = np.linalg.solve(anchor_pose.matrix(), delta_pixels)
    matrix, anchor_translation = rotation_affine(rot_k, anchor_shape)
    _, target_translation = rotation_affine(rot_k, target_shape)
    origin = (
        matrix @ delta_cells + anchor_translation - target_translation
        + np.asarray(anchor_origin_yx, np.float64)
    )
    return int(round(origin[0])), int(round(origin[1]))


def local_search(
    patch: AddressPatch,
    page: int,
    rot_k: int,
    predicted: tuple[int, int],
    budget: AttemptBudget,
    memo: ScoreMemo,
    *,
    sample_key: int,
    config: PlacementConfig,
    route: str = "chain",
) -> SearchOutcome:
    """Full bounded neighborhood; no prefix/probe-count shortcut."""
    radius = config.neighbor_radius_cells
    hypotheses = (2 * radius + 1) ** 2
    if hypotheses > budget.max_hypotheses:
        return SearchOutcome(
            False, None, (), hypotheses, "attempt_budget_exceeded",
            support_floor=budget.min_support,
        )
    candidates = [
        memo.candidate(
            sample_key, patch.evidence, patch.bits, patch.mask,
            page, (predicted[0] + dy, predicted[1] + dx), rot_k,
            budget, route,
        )
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
    ]
    candidates.sort(key=lambda row: (
        -row.soft_z, row.origin_yx[0], row.origin_yx[1]
    ))
    if not candidates or not np.isfinite(candidates[0].soft_z):
        return SearchOutcome(
            False, None, tuple(candidates), hypotheses,
            "insufficient_support",
            support_floor=budget.min_support,
        )
    best = candidates[0]
    residual = max(
        abs(best.origin_yx[0] - predicted[0]),
        abs(best.origin_yx[1] - predicted[1]),
    )
    accepted = best.passes and residual <= config.consistency_cells
    return SearchOutcome(
        accepted, best, tuple(candidates[1:]), hypotheses,
        "accepted" if accepted else "local_validation_failed",
        predicted_origin_yx=predicted,
        predicted_residual_cells=float(residual),
        support_floor=budget.min_support,
    )


# ------------------------------------------------------- the correspondence

def fragment_reference_sites(
    mask: np.ndarray,
    provider: ReferenceFieldProvider,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Local points, expected bits, and absolute page points under a pose."""
    reference: ReferencePage = provider.page(page)
    rotated_mask = np.rot90(np.asarray(mask, bool), rot_k)
    slices = overlap_slices(
        origin_yx, rotated_mask.shape, reference.values.shape
    )
    if slices is None:
        empty = np.zeros((0, 2), np.int64)
        return empty, np.zeros(0, np.uint8), empty
    page_y, page_x, frag_y, frag_x = slices
    selected_rotated = np.zeros(rotated_mask.shape, bool)
    selected_rotated[frag_y, frag_x] = (
        reference.sites[page_y, page_x] & rotated_mask[frag_y, frag_x]
    )
    ry, rx = np.nonzero(selected_rotated)
    absolute = np.stack([
        ry + int(origin_yx[0]), rx + int(origin_yx[1])
    ], axis=1)
    expected = reference.values[absolute[:, 0], absolute[:, 1]]
    # Invert the rotation while preserving correspondence order.
    index = np.full(rotated_mask.shape, -1, np.int64)
    index[ry, rx] = np.arange(ry.size)
    unrotated = np.rot90(index, -rot_k)
    local_y, local_x = np.nonzero(unrotated >= 0)
    order = unrotated[local_y, local_x]
    return (
        np.stack([local_y, local_x], axis=1),
        expected[order],
        absolute[order],
    )


# ----------------------------------------------------------- the refinement

def _rotation_2x2(delta_angle_deg: float) -> np.ndarray:
    """E022's small-angle pose rotation, in the sampler's y/x convention."""
    angle = np.deg2rad(delta_angle_deg)
    return np.array([
        [np.cos(angle), np.sin(angle)],
        [-np.sin(angle), np.cos(angle)],
    ])


def _scalar_refine_scan(
    config: PlacementConfig,
    evaluate: Callable[[float, float, float], tuple[float, float]],
) -> tuple[float, float, float, float, float] | None:
    """E022's 7x9x9 grid, one hypothesis at a time — THE ORACLE.

    Lifted out of :func:`refine_patch_pose` verbatim, at its original
    indentation, when the batched twin arrived: three inline ``np.arange``
    calls, a strict-``>`` first-wins scan in (angle, dy, dx) order.  It is
    the reference the twin is measured against and it is not to be
    tidied, factored or re-expressed — including the two ``np.arange``
    expressions it shares in substance with :func:`_refine_grids`.
    """
    best: tuple[float, float, float, float, float] | None = None
    for delta_angle in np.arange(
        -config.refine_angle_deg,
        config.refine_angle_deg + 1e-9,
        config.refine_angle_step_deg,
    ):
        for delta_y in np.arange(
            -config.refine_phase_cells,
            config.refine_phase_cells + 1e-9,
            config.refine_phase_step_cells,
        ):
            for delta_x in np.arange(
                -config.refine_phase_cells,
                config.refine_phase_cells + 1e-9,
                config.refine_phase_step_cells,
            ):
                margin, heldout_mismatch = evaluate(
                    float(delta_angle), float(delta_y), float(delta_x)
                )
                if best is None or margin > best[0]:
                    best = (
                        margin, float(delta_angle), float(delta_y),
                        float(delta_x), heldout_mismatch,
                    )
    return best


def _refine_grids(
    config: PlacementConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """The refinement scan's angle axis and its shared phase axis.

    Spelled out for the BATCHED twin alone.  :func:`refine_patch_pose`'s
    scalar loop keeps its three ``np.arange`` calls inline and verbatim
    because that loop is the twin's ORACLE, and an oracle nobody
    refactored is the stronger one; the price is that the two ``arange``
    expressions live in two places.  The guard against drift is
    ``holo2/measure/refine_equivalence.py``, which runs both arms over a
    population of rendered windows and compares winners AND scores
    bit-for-bit — one changed bound and it fails on the first window.

    ``delta_y`` and ``delta_x`` are drawn from the same bounds and the
    same step, so one array serves both; the scalar loop builds it twice
    and gets two equal arrays.
    """
    angles = np.arange(
        -config.refine_angle_deg,
        config.refine_angle_deg + 1e-9,
        config.refine_angle_step_deg,
    )
    phases = np.arange(
        -config.refine_phase_cells,
        config.refine_phase_cells + 1e-9,
        config.refine_phase_step_cells,
    )
    return angles, phases


def _batched_refine_scan(
    context: PreparedRegion,
    pose: AffinePose,
    points: np.ndarray,
    midpoint: float,
    train: np.ndarray,
    heldout: np.ndarray,
    expected: np.ndarray,
    expected_sign: np.ndarray,
    angles: np.ndarray,
    phases: np.ndarray,
) -> tuple[float, float, float, float, float]:
    """The scalar grid loop's whole 7x9x9 sweep, as five array calls.

    Same arithmetic, one shape.  The scalar path issues one
    ``map_coordinates`` and two ``np.mean`` per hypothesis — 567 of each
    per placed window, over a correspondence set MEASURED at 972-987
    sites on the e028 sheet, which is a size where numpy is dispatch
    overhead and (measured, the GIL diagnosis) the single largest
    contention site in the worker pool.  This computes every hypothesis's
    sample coordinates as one stacked array, reads them with ONE
    interpolation, and scores them with two reductions.  The stack is the
    one cost it adds: ``567 x N x 2`` float64, ~8.9 MB at that N, per
    call and per thread.

    **Why it is bit-identical, not merely close** (each clause measured
    on this numpy/scipy before it was relied on):

    * ``jacobian`` is a function of the ANGLE alone and ``base`` of the
      PHASE pair alone, so the scalar path's
      ``points @ jacobian.T + base`` factors exactly into one ``(N, 2)``
      matmul per angle plus a broadcast add of one ``(2,)`` vector per
      phase.  Both halves are the scalar path's own expressions on the
      scalar path's own operands, in its own order.
    * ``map_coordinates`` at ``order=1`` does no prefilter and no
      cross-point work: each output point is a function of its own
      coordinate pair, so batching the coordinate array cannot move a
      bit.  Output dtype follows the input (``float32`` planes), exactly
      as per-call.
    * Both reductions run along the LAST axis of a C-contiguous
      ``(H, ...)`` array, which is the same per-row pairwise ``float64``
      summation numpy already ran per iteration.  The held-out mean is
      over booleans and is exact at any order regardless.

    **Winner semantics.**  The scalar loop seeds ``best`` with the first
    hypothesis and replaces on strictly-greater (``margin > best[0]``),
    so ties keep the EARLIER hypothesis in flattened (angle, dy, dx)
    order — which is exactly ``argmax``'s first-occurrence rule.  The one
    place the two rules part company is ``NaN``: ``argmax`` propagates it
    and would return the first ``NaN``, where the scalar loop's ``>``
    is false against a ``NaN`` challenger and false against a ``NaN``
    incumbent, i.e. a ``NaN`` wins only by being FIRST.  That is
    unreachable here (the interpolated planes are finite by
    construction), and it is still reproduced below rather than
    assumed away.
    """
    jacobian0 = pose.matrix()
    origin = (
        np.asarray(pose.origin_yx, np.float64)
        - np.array([context.y0, context.x0], np.float64)
    )
    local = points.astype(np.float64)
    rotated = np.stack([
        local @ (_rotation_2x2(float(delta_angle)) @ jacobian0).T
        for delta_angle in angles
    ])                                                    # (A, N, 2)
    phase_pairs = np.stack(
        np.meshgrid(phases, phases, indexing="ij"), axis=-1
    ).reshape(-1, 2)                                      # (P, 2), dy outer
    bases = np.stack([
        origin + jacobian0 @ np.array([float(delta_y), float(delta_x)])
        for delta_y, delta_x in phase_pairs
    ])                                                    # (P, 2)
    scan_points = rotated[:, None, :, :] + bases[None, :, None, :]
    hypotheses = angles.size * phase_pairs.shape[0]
    means = ndimage.map_coordinates(
        context.filtered,
        scan_points.reshape(hypotheses, local.shape[0], 2).transpose(2, 0, 1),
        order=1, cval=context.backing,
    )                                                     # (H, N)
    margins = np.mean(
        (midpoint - means[:, train]) * -expected_sign[train], axis=1
    )
    heldout_mismatches = np.mean(
        (means[:, heldout] < midpoint) != (expected[heldout] > 0), axis=1
    )
    winner = 0 if np.isnan(margins[0]) else int(np.nanargmax(margins))
    angle_index, phase_index = divmod(winner, phase_pairs.shape[0])
    return (
        float(margins[winner]),
        float(angles[angle_index]),
        float(phase_pairs[phase_index, 0]),
        float(phase_pairs[phase_index, 1]),
        float(heldout_mismatches[winner]),
    )


def refine_patch_pose(
    context: ContextT,
    patch: AddressPatch,
    provider: ReferenceFieldProvider,
    page: int,
    patch_origin_yx: tuple[int, int],
    rot_k: int,
    config: PlacementConfig,
    *,
    resample: SegmentSampler[ContextT],
) -> WindowRefinementOutcome | None:
    """Run E022's bounded pose refinement on one accepted window.

    ``resample`` is ``pose_fit.sample_segment`` (the cross-worker seam in
    the module docstring): the refiner optimises the pose on a held-out
    parity split and then re-reads the window through it.
    """
    if not config.refine:
        return None
    sample = patch.sample
    points, expected, absolute = fragment_reference_sites(
        sample.mask, provider, page, patch_origin_yx, rot_k,
    )
    if not expected.size:
        return None
    if expected.size < config.refine_min_total_sites:
        return None
    parity = _site_parity(absolute)
    train = ~parity
    heldout = parity
    if (
        int(train.sum()) < config.refine_min_sites_per_parity
        or int(heldout.sum()) < config.refine_min_sites_per_parity
    ):
        return None
    expected_sign = 1.0 - 2.0 * expected.astype(np.float64)
    midpoint = float(np.median(sample.means[sample.mask]))

    def evaluate(
        delta_angle_deg: float, delta_y: float, delta_x: float
    ) -> tuple[float, float]:
        rotation = _rotation_2x2(delta_angle_deg)
        pose = sample.segment.pose
        jacobian0 = pose.matrix()
        jacobian = rotation @ jacobian0
        base = (
            np.asarray(pose.origin_yx, np.float64)
            - np.array([context.y0, context.x0], np.float64)
            + jacobian0 @ np.array([delta_y, delta_x])
        )
        scan_points = points.astype(np.float64) @ jacobian.T + base
        means = ndimage.map_coordinates(
            context.filtered, scan_points.T, order=1,
            cval=context.backing,
        )
        margin = float(np.mean(
            (midpoint - means[train]) * -expected_sign[train]
        ))
        heldout_mismatch = float(np.mean(
            (means[heldout] < midpoint) != (expected[heldout] > 0)
        ))
        return margin, heldout_mismatch

    _, baseline_heldout = evaluate(0.0, 0.0, 0.0)
    # The BASELINE above keeps its own ``evaluate`` call under BOTH arms
    # and is deliberately not folded into the batch: the grid's nominal
    # zero is ``-0.15 + 3*0.05 = 2.78e-17``, not ``0.0``, so (0, 0, 0) is
    # a genuinely different hypothesis from every point on the grid.
    best: tuple[float, float, float, float, float] | None
    if config.batched_refine:
        angles, phases = _refine_grids(config)
        best = _batched_refine_scan(
            context, sample.segment.pose, points, midpoint, train, heldout,
            expected, expected_sign, angles, phases,
        )
    else:
        best = _scalar_refine_scan(config, evaluate)
    if best is None:
        return None
    _, delta_angle_deg, delta_y, delta_x, heldout_after = best
    if heldout_after > baseline_heldout + config.refine_heldout_degrade:
        return None
    base_pose = sample.segment.pose
    jacobian0 = base_pose.matrix()
    jacobian = _rotation_2x2(delta_angle_deg) @ jacobian0
    origin = (
        np.asarray(base_pose.origin_yx, np.float64)
        + jacobian0 @ np.array([delta_y, delta_x])
    )
    # pose_metrics' three used scalars, verbatim; its fourth (the
    # orthogonality error) is a fit diagnostic this kernel discards.
    pitch_y = float(np.hypot(*jacobian[:, 0]))
    pitch_x = float(np.hypot(*jacobian[:, 1]))
    pose_angle = float(
        np.degrees(np.arctan2(jacobian[0, 1], jacobian[1, 1]))
    )
    pose = AffinePose(
        (float(origin[0]), float(origin[1])),
        (
            (float(jacobian[0, 0]), float(jacobian[0, 1])),
            (float(jacobian[1, 0]), float(jacobian[1, 1])),
        ),
        base_pose.phase_yx,
        float(0.5 * (pitch_y + pitch_x)),
        pose_angle,
    )
    refined = resample(context, replace(sample.segment, pose=pose))
    if refined is None:
        return None
    return WindowRefinementOutcome(
        refined, delta_angle_deg, (delta_y, delta_x),
        baseline_heldout, heldout_after,
    )


# ---------------------------------------------------------------- the audit

def _best_change_point(
    coordinates: np.ndarray, errors: np.ndarray, min_sites: int
) -> tuple[float, float, float] | None:
    """Purest binomial-impurity straddle split of one sorted axis.

    Returns ``(low_rate, high_rate, cut)`` for the split minimising
    ``n_low*p_low*(1-p_low) + n_high*p_high*(1-p_high)``, first-wins on an
    exact tie, skipping splits that would cut a tied coordinate.  ``None``
    when no admissible split exists.
    """
    cumulative = np.concatenate([[0.0], np.cumsum(errors)])
    best: tuple[float, float, float, float] | None = None
    size = coordinates.size
    for split in range(min_sites, size - min_sites):
        if coordinates[split] == coordinates[split - 1]:
            continue
        low = cumulative[split] / split
        high = (cumulative[size] - cumulative[split]) / (size - split)
        impurity = (
            split * low * (1.0 - low)
            + (size - split) * high * (1.0 - high)
        )
        if best is None or impurity < best[0]:
            best = (
                float(impurity), float(low), float(high),
                float(0.5 * (coordinates[split - 1] + coordinates[split])),
            )
    if best is None:
        return None
    return best[1], best[2], best[3]


def audit_segment(
    sample: SegmentSample,
    core: np.ndarray,
    provider: ReferenceFieldProvider,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
    config: PlacementConfig,
    *,
    min_support: int = E022_SUPPORT_FLOOR_SITES,
) -> tuple[np.ndarray, bool, int, float]:
    """E022-v2 binomial-impurity change-point straddle audit."""
    floor = _int_at_least("audit min_support", min_support, 1)
    points, expected, absolute = fragment_reference_sites(
        core, provider, page, origin_yx, rot_k
    )
    parity = _site_parity(absolute)

    def below_population_floor(selected: np.ndarray) -> bool:
        return (
            int(np.count_nonzero(selected & ~parity)) < floor
            or int(np.count_nonzero(selected & parity)) < floor
        )

    if points.shape[0] < 2 * config.audit_min_sites:
        support = int(points.shape[0])
        selected = np.ones(support, bool)
        return (
            np.asarray(core, bool), below_population_floor(selected),
            support, 0.0,
        )
    wrong = (
        sample.bits[points[:, 0], points[:, 1]] != expected
    ).astype(np.float64)
    good = np.asarray(core, bool).copy()
    keep = np.ones(points.shape[0], bool)
    for axis in (0, 1, 0, 1):
        active = np.flatnonzero(keep)
        if active.size < 2 * config.audit_min_sites:
            break
        order = np.argsort(points[active, axis], kind="stable")
        coordinates = points[active, axis][order]
        change_point = _best_change_point(
            coordinates, wrong[active][order], config.audit_min_sites
        )
        if change_point is None:
            continue
        low, high, cut = change_point
        bad_low = low > high
        bad_rate, kept_rate = (low, high) if bad_low else (high, low)
        if not (bad_rate > config.audit_bad and kept_rate < config.audit_good):
            continue
        edge = int(np.ceil(cut))
        if axis == 0:
            if bad_low:
                good[:edge, :] = False
            else:
                good[edge:, :] = False
        else:
            if bad_low:
                good[:, :edge] = False
            else:
                good[:, edge:] = False
        keep &= good[points[:, 0], points[:, 1]]
    kept = int(keep.sum())
    residual = float(wrong[keep].mean()) if kept else 1.0
    refused = (
        below_population_floor(keep)
        or residual > config.audit_post_bar
    )
    return good, refused, kept, residual


# -------------------------------------------------------------- the harvest

def observations_for_segment(
    sample: SegmentSample,
    audited: np.ndarray,
    provider: ReferenceFieldProvider,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
    *,
    capture_id: str,
    family_seed: bytes,
    pose_id: ResourceKey | None = None,
) -> tuple[PilotObservation, ...]:
    """Retain every authoritative pilot bit/evidence read under the core.

    ``pose_id`` is v1's ``patch_id`` back-reference (H4 W5): the reduce
    that consumes these rows names a contributor by its POSE key, and
    the caller that knows the pose is the emission block. ``None`` is a
    harness's harvest — the rows are still lawful, they simply
    contribute no contributor.
    """
    local, _expected, absolute = fragment_reference_sites(
        audited, provider, page, origin_yx, rot_k
    )
    if not local.size:
        return ()
    site_positions = pilots.word_site_cells_yx(family_seed)
    site_index = {
        (int(row[0]), int(row[1])): index
        for index, row in enumerate(site_positions)
    }
    rows: list[PilotObservation] = []
    for point, page_point in zip(local, absolute, strict=True):
        page_y, page_x = int(page_point[0]), int(page_point[1])
        tile_y, site_y = divmod(page_y, pilots.TILE_CELLS)
        tile_x, site_x = divmod(page_x, pilots.TILE_CELLS)
        word_index = site_index.get((site_y, site_x))
        # Future filler labels participate in Lane C but are not BCH word
        # observations; their calibration path will consume them separately.
        if word_index is None:
            continue
        local_y, local_x = int(point[0]), int(point[1])
        rows.append(PilotObservation(
            int(page), (tile_y, tile_x), word_index,
            int(sample.bits[local_y, local_x]),
            float(sample.evidence[local_y, local_x]),
            str(capture_id), pose_id,
        ))
    return tuple(rows)


__all__ = [
    "WHOLE_WORD_PARITY", "ScoreMemo", "SearchOutcome", "SegmentSampler",
    "WindowRefinementOutcome", "audit_segment", "fragment_reference_sites",
    "local_search", "observations_for_segment", "parity_mask",
    "predict_from_anchor", "refine_patch_pose", "rival_gate",
]
