"""RF1's carried arithmetic: v1's bounded pose revision, transcribed.

Split out of ``refine.py`` at H5 P4 when the family passed the 1000-line
cap, and the seam is a functional one rather than a convenient one — the
same cut ``keys.py`` and ``families.py`` took out of ``records.py``. What
a REVISION IS lives here: v1's constants, its two-stage grid, its
deterministic holdout and site caps, its contrast objective, its weighted
log-loss and its three-part adoption gate, plus the window-local geometry
they are all expressed in. How holo2 SCHEDULES one — the eligibility
derivation, the generation-zero replay, the worker and the provider —
lives in ``refine.py``. The dependency runs refine -> refine_fit and
never back, which is what makes this module readable against
``src/holo/receive/certified_refine.py`` side by side, with nothing about
descriptors or stores in the way.

``refine.py`` re-exports every name below, deliberately and for the
reason ``records.py`` re-exports ``keys.py``: a seam taken for a line cap
must not become a second address every caller has to learn.

NOTHING HERE IS TUNED. Every constant is v1's, and
``tests/holo2_oracles/test_oracle_refine.py`` byte-compares each function
against the private v1 function it was carried from. The constants are
RE-DECLARED rather than imported because production holo2 may not import
``src/holo`` (the import firewall); that oracle is what keeps the
re-declaration honest.

THE ONE THING THAT IS NOT v1's is the SCORE CONVENTION, and it is holo2's
rather than a divergence: ``place_shared`` emits ``scores = -means`` and
fits the marginal PAVA on that scale, so a committed calibration's knots
live there and :func:`propose` scores baseline and candidates alike
through ``llr(-means)``. v1 normalises to ``(midpoint - raw) / spread``
first, because ITS nodes live on that scale. Each tree must read the map
its own knots were fitted under; using v1's normalisation here would be a
bug. The gain is an invariant v1 cannot state — the baseline logits this
computes ARE the LLRs the evidence pieces already carry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import ndimage

from . import detect
from .place_model import AffinePose, PoseSegment, PoseWindow
from .place_shared import compose_from_native, compose_to_native
from .reference import ReferenceFieldProvider

# ---------------------------------------------------------------------------
# THE CARRIED CONSTANTS — ``certified_refine`` verbatim, name for name.
#
# They are re-declared rather than imported because production holo2 may
# not import ``src/holo`` (the import firewall); ``tests/holo2_oracles/
# test_oracle_refine.py`` pins each one against v1's own module, so a
# drift is a test failure rather than a silent fork.
#
# NOT to be confused with ``PlacementConfig.refine_*``, which bounds
# E022's own placement-time pose refinement (``pose_audit``). The two
# happen to share the fine steps; they are different fits at different
# times against different labels, and this family owns these.
# ---------------------------------------------------------------------------

BLOCK_CELLS = 16
VALIDATION_MODULUS = 4
MIN_PAYLOAD_TRAIN = 64
MIN_PAYLOAD_VALIDATION = 32
MIN_TRAIN_PER_CLASS = 20
MIN_VALIDATION_PER_CLASS = 10
MIN_CERTIFIED_BLOCKS = 4
MIN_POSE_PILOTS = 30
MIN_HELDOUT_GAIN = 1e-4
PILOT_MISMATCH_SLACK = 0.005
ANGLE_LIMIT_DEG = 0.15
ANGLE_COARSE_STEP_DEG = 0.15
ANGLE_FINE_STEP_DEG = 0.05
PHASE_LIMIT_CELLS = 0.25
PHASE_COARSE_STEP_CELLS = 0.25
PHASE_FINE_STEP_CELLS = 0.0625
POSE_SITE_CAP_TRAIN = 2048
POSE_SITE_CAP_VALIDATION = 1024
SCORE_SPREAD_FLOOR = 1e-6

#: Spend outcomes. ``adopted`` is the only one that writes geometry;
#: every refusal COMMITS ITS REASON as the outcome, so the ledger's
#: per-outcome counts say why a pose declined a revision.
OUTCOME_ADOPTED = "adopted"
OUTCOME_REFUSED_PREFIX = "refused_"


# ------------------------------------------------------- the carried labels

@dataclass(frozen=True)
class SegmentLabels:
    """Pilot and certified-cargo labels for one pose, v1's own shape.

    ``rows`` indexes into the pose's sampled cell list; the rest is
    ``certified_refine.SegmentLabels`` field for field, minus the
    certificate-id column holo2 does not need (the frontier version is
    already the descriptor's spend identity).
    """

    rows: np.ndarray
    page_cells_yx: np.ndarray
    values: np.ndarray
    validation: np.ndarray
    weights: np.ndarray
    is_pilot: np.ndarray
    block_ids: np.ndarray

    @property
    def train(self) -> np.ndarray:
        return ~self.validation


def block_validation(page: int, cells_yx: np.ndarray) -> np.ndarray:
    """v1's deterministic cargo-holdout stripe (``_block_validation``).

    Carried WITH its ruling: the historical E024 x coefficient 9176 was
    congruent to 0 mod the modulus, degenerating the partition into
    y-only bands; all three coefficients are odd here, so the held-out
    blocks form diagonal stripes and every axis-aligned run of four
    blocks holds exactly one. Same stripe fraction, same determinism.
    """
    block = np.asarray(cells_yx, np.int64) // BLOCK_CELLS
    token = page * 104729 + block[:, 0] * 1009 + block[:, 1] * 9177
    return (token % VALIDATION_MODULUS) == 0


def block_weights(block_ids: np.ndarray) -> np.ndarray:
    """One block's labels share one unit of weight (``_block_weights``)."""
    ids = np.asarray(block_ids, np.int64)
    if ids.size == 0:
        return np.zeros(0, np.float64)
    _unique, inverse, counts = np.unique(
        ids, return_inverse=True, return_counts=True)
    return 1.0 / counts[inverse].astype(np.float64)


def collect_labels(page: int, page_cells_yx: np.ndarray,
                   base: ReferenceFieldProvider,
                   enriched: ReferenceFieldProvider) -> SegmentLabels:
    """Join format-known pilots and certified printed cargo.

    v1's ``collect_segment_labels``, with holo2's two reference fields
    standing in for its ``reference_values``/frontier join: the BASE
    field's site mask is exactly v1's ``reference >= 0`` (format-known,
    the pilot half), and the ENRICHED field's extra sites are exactly
    v1's certified cargo (``reference < 0`` at a cell whose tile is
    certified). The values come from the enriched field either way, so a
    certificate that disagreed with the format at a known site has
    already been refused upstream (``certified_labels`` raises).

    Pilots take v1's site parity ``(131y + 17x) & 1``; cargo takes the
    block stripe. The block ids separate the two populations by the same
    ``10**12`` offset v1 uses, so a pilot block and a cargo block never
    share weight.
    """
    cells = np.asarray(page_cells_yx, np.int64)
    base_page = base.page(page)
    rich_page = enriched.page(page)
    known = rich_page.sites[cells[:, 0], cells[:, 1]]
    pilot = base_page.sites[cells[:, 0], cells[:, 1]] & known
    cargo = known & ~pilot

    pilot_rows = np.flatnonzero(pilot)
    cargo_rows = np.flatnonzero(cargo)
    rows = np.concatenate((pilot_rows, cargo_rows)).astype(np.int64)
    selected = cells[rows]
    values = rich_page.values[selected[:, 0], selected[:, 1]].astype(np.uint8)
    pilot_cells = cells[pilot_rows]
    cargo_cells = cells[cargo_rows]
    validation = np.concatenate((
        ((pilot_cells[:, 0] * 131 + pilot_cells[:, 1] * 17) & 1).astype(bool),
        block_validation(page, cargo_cells)))
    is_pilot = np.concatenate((np.ones(pilot_rows.size, bool),
                               np.zeros(cargo_rows.size, bool)))
    by = selected[:, 0] // BLOCK_CELLS
    bx = selected[:, 1] // BLOCK_CELLS
    block_ids = (is_pilot.astype(np.int64) * 10**12
                 + page * 10**9 + by * 10**4 + bx)
    weights = np.zeros(rows.size, np.float64)
    weights[~validation] = block_weights(block_ids[~validation])
    weights[validation] = block_weights(block_ids[validation])
    return SegmentLabels(rows, selected, values, validation, weights,
                         is_pilot, block_ids)


def support_metrics(labels: SegmentLabels) -> tuple[bool, str, dict[str, int]]:
    """v1's ``_support_metrics``: the five carried floors, in order."""
    payload = ~labels.is_pilot
    payload_train = int(np.count_nonzero(payload & labels.train))
    payload_validation = int(np.count_nonzero(payload & labels.validation))
    blocks = int(np.unique(labels.block_ids[payload]).size)
    counts = {"n_payload_train": payload_train,
              "n_payload_validation": payload_validation,
              "n_certified_blocks": blocks}
    if payload_train < MIN_PAYLOAD_TRAIN:
        return False, "insufficient_payload_train", counts
    if payload_validation < MIN_PAYLOAD_VALIDATION:
        return False, "insufficient_payload_validation", counts
    train_values = labels.values[labels.train]
    valid_values = labels.values[labels.validation]
    if min(int(np.count_nonzero(train_values == 0)),
           int(np.count_nonzero(train_values == 1))) < MIN_TRAIN_PER_CLASS:
        return False, "train_class_starved", counts
    if min(int(np.count_nonzero(valid_values == 0)),
           int(np.count_nonzero(valid_values == 1))) < MIN_VALIDATION_PER_CLASS:
        return False, "validation_class_starved", counts
    if blocks < MIN_CERTIFIED_BLOCKS:
        return False, "insufficient_certified_blocks", counts
    return True, "", counts


def deterministic_cap(positions: np.ndarray, cells_yx: np.ndarray,
                      cap: int) -> np.ndarray:
    """v1's ``_deterministic_cap``: hash-ordered, seedless, reproducible."""
    rows = np.asarray(positions, np.int64)
    if rows.size <= cap:
        return rows
    coords = np.asarray(cells_yx, np.int64)[rows]
    token = (coords[:, 0].astype(np.uint64) * np.uint64(11400714819323198485)
             ^ coords[:, 1].astype(np.uint64) * np.uint64(14029467366897019727))
    return rows[np.argsort(token, kind="stable")[:cap]]


def select_pose_sites(labels: SegmentLabels, validation: bool) -> np.ndarray:
    """v1's ``select_pose_sites``: retain all pilots, hash-cap cargo."""
    side = labels.validation if validation else labels.train
    cap = POSE_SITE_CAP_VALIDATION if validation else POSE_SITE_CAP_TRAIN
    positions = np.flatnonzero(side)
    pilots = positions[labels.is_pilot[positions]]
    cargo = positions[~labels.is_pilot[positions]]
    cargo = deterministic_cap(cargo, labels.page_cells_yx,
                              max(cap - pilots.size, 0))
    selected = np.concatenate((pilots, cargo))
    return selected[np.argsort(labels.rows[selected], kind="stable")].astype(
        np.int64, copy=False)


# --------------------------------------------------------- the carried fit

def pose_candidate(base: AffinePose, dtheta_deg: float, du_cells: float,
                   dv_cells: float) -> AffinePose:
    """v1's ``_pose_candidate``, on holo2's structurally identical pose.

    A rotation about the pose's OWN ORIGIN composed with a translation
    expressed in cells through the base Jacobian. The origin is therefore
    load-bearing: this family builds a WINDOW-LOCAL pose whose origin is
    the observed extent's corner (:func:`local_segment`), which is where
    v1's segment-local pose has it. Pivoting a page-frame affine here
    would turn a 0.15-degree rotation into a translation of many cells at
    the window — the bound would be respected in the term and violated in
    the geometry.
    """
    angle = np.deg2rad(float(dtheta_deg))
    rotation = np.asarray(((np.cos(angle), np.sin(angle)),
                           (-np.sin(angle), np.cos(angle))), np.float64)
    jacobian0 = base.matrix()
    jacobian = rotation @ jacobian0
    origin = (np.asarray(base.origin_yx, np.float64)
              + jacobian0 @ np.asarray((du_cells, dv_cells), np.float64))
    pitch_y = float(np.hypot(*jacobian[:, 0]))
    pitch_x = float(np.hypot(*jacobian[:, 1]))
    angle_deg = float(np.degrees(np.arctan2(jacobian[0, 1], jacobian[1, 1])))
    return AffinePose(
        (float(origin[0]), float(origin[1])),
        tuple(tuple(float(value) for value in row) for row in jacobian),
        base.phase_yx, 0.5 * (pitch_y + pitch_x), angle_deg)


def pose_objective(means: np.ndarray, values: np.ndarray,
                   weights: np.ndarray) -> float:
    """v1's ``_pose_objective``: weighted paper/ink separation over spread.

    Raw luma only — no calibration enters the candidate RANKING at all,
    which is why the winner this grid selects is convention-free and
    compares byte-exactly against v1's on identical pixels.
    """
    raw = np.asarray(means, np.float64)
    labels = np.asarray(values, np.uint8)
    weight = np.asarray(weights, np.float64)
    paper, ink = labels == 0, labels == 1
    if not paper.any() or not ink.any():
        return -np.inf
    mean_paper = float(np.sum(weight[paper] * raw[paper])
                       / np.sum(weight[paper]))
    mean_ink = float(np.sum(weight[ink] * raw[ink]) / np.sum(weight[ink]))
    center = float(np.sum(weight * raw) / np.sum(weight))
    spread = max(float(np.sum(weight * np.abs(raw - center)) / np.sum(weight)),
                 SCORE_SPREAD_FLOOR)
    return (mean_paper - mean_ink) / spread


def weighted_logloss(logits: np.ndarray, values: np.ndarray,
                     weights: np.ndarray) -> float:
    """v1's ``_weighted_logloss``."""
    x = np.asarray(logits, np.float64)
    y = np.asarray(values, np.float64)
    w = np.asarray(weights, np.float64)
    losses = np.logaddexp(0.0, x) - y * x
    return float(np.sum(w * losses) / np.sum(w))


def adoption_gate(baseline_loss: float, candidate_loss: float,
                  baseline_pilot_mismatch: float,
                  candidate_pilot_mismatch: float,
                  generation0_raw_pilot_mismatch: float,
                  candidate_raw_pilot_mismatch: float) -> bool:
    """v1's ``_adoption_gate``: held-out gain AND two pilot non-regressions.

    All three, unweakened: a strict held-out gain of at least
    ``MIN_HELDOUT_GAIN``, a CALIBRATED pilot mismatch no worse than the
    baseline's by more than the slack, and a RAW pilot mismatch no worse
    than generation zero's by more than the slack. The third is
    deliberately detector-free — it is what stops a candidate buying
    log-loss by moving the geometry somewhere the luma no longer
    separates pilots at all.
    """
    return bool(candidate_loss + MIN_HELDOUT_GAIN < baseline_loss
                and candidate_pilot_mismatch
                <= baseline_pilot_mismatch + PILOT_MISMATCH_SLACK
                and candidate_raw_pilot_mismatch
                <= generation0_raw_pilot_mismatch + PILOT_MISMATCH_SLACK)


def candidate_grid() -> tuple[tuple[float, float, float], ...]:
    """The COARSE stage's keys — v1's ``np.arange`` triple product.

    Published because the two-stage structure is the carried algorithm
    and its coarse half is pose-independent, so an oracle can compare the
    enumeration itself rather than only its winner.
    """
    angles = np.arange(-ANGLE_LIMIT_DEG, ANGLE_LIMIT_DEG + 1e-12,
                       ANGLE_COARSE_STEP_DEG)
    phase = np.arange(-PHASE_LIMIT_CELLS, PHASE_LIMIT_CELLS + 1e-12,
                      PHASE_COARSE_STEP_CELLS)
    return tuple((float(dtheta), float(du), float(dv))
                 for dtheta in angles for du in phase for dv in phase)


def fine_grid(best: tuple[float, float, float]
              ) -> tuple[tuple[float, float, float], ...]:
    """The FINE stage's keys around one coarse winner — v1's own clipping.

    Every fine step is re-tested against the LIMIT, not against the
    coarse winner: that is what makes a proposal outside +-0.15 deg or
    +-0.25 cell impossible by construction rather than by a later check.
    """
    angles = np.arange(best[0] - ANGLE_COARSE_STEP_DEG,
                       best[0] + ANGLE_COARSE_STEP_DEG + 1e-12,
                       ANGLE_FINE_STEP_DEG)
    du = np.arange(best[1] - PHASE_COARSE_STEP_CELLS,
                   best[1] + PHASE_COARSE_STEP_CELLS + 1e-12,
                   PHASE_FINE_STEP_CELLS)
    dv = np.arange(best[2] - PHASE_COARSE_STEP_CELLS,
                   best[2] + PHASE_COARSE_STEP_CELLS + 1e-12,
                   PHASE_FINE_STEP_CELLS)
    out: list[tuple[float, float, float]] = []
    for dtheta in angles:
        if abs(dtheta) > ANGLE_LIMIT_DEG + 1e-12:
            continue
        for one in du:
            if abs(one) > PHASE_LIMIT_CELLS + 1e-12:
                continue
            for other in dv:
                if abs(other) <= PHASE_LIMIT_CELLS + 1e-12:
                    out.append((float(dtheta), float(one), float(other)))
    return tuple(out)


def select_best(candidates: dict[tuple[float, float, float],
                                tuple[float, float]],
                keys: Iterable[tuple[float, float, float]]
                ) -> tuple[float, float, float]:
    """v1's ``select_best``: max contrast, ties by loss then by smallness."""
    rows = tuple(keys)
    maximum = max(candidates[key][0] for key in rows)
    near = [key for key in rows if maximum - candidates[key][0] <= 1e-9]
    return min(near, key=lambda key: (candidates[key][1],
                                      sum(value * value for value in key),
                                      tuple(abs(value) for value in key), key))


# ------------------------------------------------------------- the geometry

@dataclass(frozen=True)
class RefineInput:
    """Everything one revision reads, gathered before any arithmetic."""

    page: int
    segment: PoseSegment
    local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray
    baseline_means: np.ndarray
    calibration: detect.Calibration
    filtered: np.ndarray
    crop_yx: tuple[int, int]
    backing: float


def local_segment(native_affine: tuple[float, ...], frame, page_cells: np.ndarray,
                  ) -> tuple[PoseSegment, np.ndarray]:
    """A WINDOW-LOCAL pose over one pose's observed page cells.

    Two conversions, both exact. The durable affine is native-frame and
    page-cell indexed; ``compose_from_native`` restates it in the rung's
    pixels (the frame the prepared plane is in), and the local frame
    re-origins it at the observed extent's corner so
    :func:`pose_candidate` pivots where v1 pivots. Local cell ``(i, j)``
    is page cell ``(cy0 + i, cx0 + j)``, so the correspondence is a pure
    translation and no resampling is implied by it.
    """
    terms = compose_from_native(tuple(native_affine), frame)
    matrix = np.asarray(terms, np.float64).reshape(2, 3)
    linear = matrix[:, :2]
    corner = page_cells.min(axis=0).astype(np.int64)
    origin = linear @ corner.astype(np.float64) + matrix[:, 2]
    local = (page_cells - corner).astype(np.int64)
    shape = tuple(int(value) for value in (local.max(axis=0) + 1))
    pitch = 0.5 * (float(np.hypot(*linear[:, 0]))
                   + float(np.hypot(*linear[:, 1])))
    pose = AffinePose(
        (float(origin[0]), float(origin[1])),
        tuple(tuple(float(value) for value in row) for row in linear),
        (0.0, 0.0), pitch,
        float(np.degrees(np.arctan2(linear[0, 1], linear[1, 1]))))
    window = PoseWindow(0, 0, (0, 0), (shape[0], shape[1]))
    return (PoseSegment(window, pose, int(local.shape[0]), 0.0,
                        (float(np.hypot(*linear[:, 0])),
                         float(np.hypot(*linear[:, 1]))), 0.0),
            local)


def sample_at(filtered: np.ndarray, crop_yx: tuple[int, int], backing: float,
              pose: AffinePose, local_cells: np.ndarray) -> np.ndarray:
    """v1's ``_sample``: order-1 interpolation through the one aperture.

    The same primitive ``pose_fit.sample_segment`` reads production
    evidence through — ``map_coordinates(order=1)`` over the prepared
    region's single box-filtered plane, with the platen backing as the
    out-of-crop fill — so a candidate is scored on exactly the pixels a
    committed pose would be.
    """
    points = pose.points(np.asarray(local_cells, np.float64))
    local = points - np.asarray(crop_yx, np.float64)
    return np.asarray(ndimage.map_coordinates(filtered, local.T, order=1,
                                              cval=backing), np.float64)


# --------------------------------------------------------------- the fire

@dataclass(frozen=True)
class Revision:
    """One fire's verdict: adopted geometry or a reason, plus its numbers."""

    adopted: bool
    reason: str
    affine: tuple[float, ...] | None = None
    dtheta_deg: float = 0.0
    du_cells: float = 0.0
    dv_cells: float = 0.0
    baseline_logloss: float | None = None
    candidate_logloss: float | None = None
    candidates: int = 0


def propose(data: RefineInput, labels: SegmentLabels, frame) -> Revision:
    """The bounded search and the three gates — v1's ``refine_segment``.

    Ordering is v1's: floors first, then the pilot-count floor, then the
    two-stage grid, then the gates. A refusal at any step returns a
    reason and NO geometry, and the caller commits that reason as the
    spend's outcome.
    """
    supported, reason, _counts = support_metrics(labels)
    if not supported:
        return Revision(False, reason)
    train = select_pose_sites(labels, validation=False)
    valid = select_pose_sites(labels, validation=True)
    train_pilots = train[labels.is_pilot[train]]
    valid_pilots = valid[labels.is_pilot[valid]]
    if (train_pilots.size < MIN_POSE_PILOTS
            or valid_pilots.size < MIN_POSE_PILOTS):
        return Revision(False, "insufficient_pose_pilot_validation")

    segment, local = data.segment, data.local_cells_yx
    train_local = local[labels.rows[train]]
    train_values = labels.values[train]
    train_weights = labels.weights[train]
    valid_rows = labels.rows[valid]
    valid_values = labels.values[valid]
    valid_weights = labels.weights[valid]
    pilot_rows = labels.rows[valid_pilots]
    pilot_values = labels.values[valid_pilots]

    # THE SCORE CONVENTION (module docstring): holo2's PAVA was fitted on
    # negated raw luma, so that is the scale every logit here is taken
    # on — baseline and candidate alike.
    def logits_of(means: np.ndarray) -> np.ndarray:
        return np.asarray(data.calibration.llr(-np.asarray(means, np.float64)),
                          np.float64)

    base_logits = logits_of(data.baseline_means)
    base_loss = weighted_logloss(base_logits[valid_rows], valid_values,
                                 valid_weights)
    base_pilot_mismatch = float(np.mean(
        (base_logits[pilot_rows] > 0.0) != (pilot_values > 0)))
    midpoint = float(np.median(data.baseline_means))
    base_raw_mismatch = float(np.mean(
        (data.baseline_means[pilot_rows] < midpoint) != (pilot_values > 0)))

    candidates: dict[tuple[float, float, float], tuple[float, float]] = {}

    def score(dtheta: float, du: float, dv: float) -> None:
        # v1 rounds the KEY to 12 decimals before the dedup lookup: the
        # fine stage re-derives coarse offsets through ``np.arange``, and
        # two spellings of one offset must be one candidate.
        key = (round(float(dtheta), 12), round(float(du), 12),
               round(float(dv), 12))
        if key in candidates:
            return
        pose = pose_candidate(segment.pose, *key)
        means = sample_at(data.filtered, data.crop_yx, data.backing, pose,
                          train_local)
        contrast = pose_objective(means, train_values, train_weights)
        loss = weighted_logloss(
            data.calibration.llr(-means), train_values, train_weights)
        candidates[key] = contrast, loss

    for row in candidate_grid():
        score(*row)
    coarse = select_best(candidates, tuple(candidates))
    for row in fine_grid(coarse):
        score(*row)
    best = select_best(candidates, tuple(candidates))

    pose = pose_candidate(segment.pose, *best)
    if pose == segment.pose:
        return Revision(False, "active_pose_selected",
                        baseline_logloss=base_loss, candidates=len(candidates))
    means = sample_at(data.filtered, data.crop_yx, data.backing, pose, local)
    logits = logits_of(means)
    loss = weighted_logloss(logits[valid_rows], valid_values, valid_weights)
    pilot_mismatch = float(np.mean(
        (logits[pilot_rows] > 0.0) != (pilot_values > 0)))
    raw_mismatch = float(np.mean(
        (means[pilot_rows] < midpoint) != (pilot_values > 0)))
    adopted = adoption_gate(base_loss, loss, base_pilot_mismatch,
                            pilot_mismatch, base_raw_mismatch, raw_mismatch)
    if not adopted:
        return Revision(False, "pose_gate_failed", None, *best,
                        base_loss, loss, len(candidates))
    return Revision(True, OUTCOME_ADOPTED, native_terms(pose, data, frame),
                    *best, base_loss, loss, len(candidates))


def native_terms(pose: AffinePose, data: RefineInput, frame
                 ) -> tuple[float, ...]:
    """A revised LOCAL pose, back in the durable native page-cell frame.

    :func:`local_segment`'s two conversions run backwards: re-origin from
    the observed extent's corner to page cell (0, 0), then restate the
    rung's pixels as native ones. What a ``PoseRecord`` carries is always
    native and always page-indexed, so a revision is indistinguishable
    from a first fit at the record level — which is the whole point of
    proposing a pose rather than a patch.
    """
    linear = pose.matrix()
    corner = data.page_cells_yx.min(axis=0).astype(np.float64)
    offset = np.asarray(pose.origin_yx, np.float64) - linear @ corner
    return compose_to_native(
        (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
         float(linear[1, 0]), float(linear[1, 1]), float(offset[1])), frame)




__all__ = [
    "ANGLE_COARSE_STEP_DEG", "ANGLE_FINE_STEP_DEG", "ANGLE_LIMIT_DEG",
    "BLOCK_CELLS", "MIN_CERTIFIED_BLOCKS", "MIN_HELDOUT_GAIN",
    "MIN_PAYLOAD_TRAIN", "MIN_PAYLOAD_VALIDATION", "MIN_POSE_PILOTS",
    "MIN_TRAIN_PER_CLASS", "MIN_VALIDATION_PER_CLASS",
    "PHASE_COARSE_STEP_CELLS", "PHASE_FINE_STEP_CELLS", "PHASE_LIMIT_CELLS",
    "PILOT_MISMATCH_SLACK", "POSE_SITE_CAP_TRAIN", "POSE_SITE_CAP_VALIDATION",
    "OUTCOME_ADOPTED", "OUTCOME_REFUSED_PREFIX",
    "SCORE_SPREAD_FLOOR", "VALIDATION_MODULUS", "RefineInput", "Revision",
    "SegmentLabels", "adoption_gate", "block_validation", "block_weights",
    "candidate_grid", "collect_labels", "deterministic_cap", "fine_grid",
    "local_segment", "native_terms", "pose_candidate", "pose_objective",
    "propose", "sample_at", "select_best", "select_pose_sites",
    "support_metrics", "weighted_logloss",
]
