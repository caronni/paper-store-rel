"""Family ``place``: ONE job — a ready window, one pass, what is true now.

H4 W2, the pull model (H4-W2-PLAN, "THE PULL MODEL — 2026-08-16
redesign, RULED"). Package 2 gave the family two descriptor routes and a
durable hint record pushed between them; this replaces both with the
user's own model: **the scheduling set is all windows minus the finished
ones; each window has an "I am ready" bit; a worked window atomically
clears its bit, takes what it knows, and does its job.** The routes
unify — one job, whose ladder is decided by what is TRUE at fire time
rather than by which descriptor was minted:

    empty consult -> word;  ping -> ring consult;
    worklist-dry re-pass -> wide consult;  last -> cold, in two flavours.

WHY THIS IS THE SAME ALGORITHM, CHEAPER
---------------------------------------
Nothing carried moved. The seeded 49-hypothesis local search, the fit,
the whole-word rival gate, the straddle audit and the shared emission
block are the same functions the two descriptor routes called, in the
same order, with the same numbers. What died is the DURABLE half: a hint
is a scheduling annotation, not a fact, and promoting one to a record
bought an improve-only law at the wall, a concurrent-merge collision, a
ring-key identity binding and a subscription per neighbour. Here the
window asks the committed-pose index itself, at the moment it fires, so
nothing can be stale and nothing needs retaining.

THE LADDER, AS BUILT
--------------------
1. **Lazy covered-exit.** The §6 done projection is asked FIRST, before
   any pixel: a window whose whole supported extent certified through
   NEIGHBOURS' poses retires with its reason and leaves the set. Done
   does not imply placed (windows overlap), which is why this exit is
   not merely "exit by placed" — and it is what stops an unplaced window
   in a recovered area from consulting forever.
2. **The consult** (:func:`consult`) — the committed poses this window
   can see, extrapolated here through package 2's prediction arithmetic
   (``place_shared.predict_from_page_affine``), sorted by the ratified
   distance, truncated to :data:`CONSULT_KEEP`, minus the window's TRIED
   set. Ring-scoped by default (the eight lattice neighbours plus the
   coarser-footing donors that cover this window); page-wide at the wide
   tier.
3. **The seeds, in order**, each through ``pose_audit.local_search`` on
   one shared score memo (v1's ``_chain_search``: nearest first, stop at
   the first acceptance).
4. **The word stage, if and only if the consult came up EMPTY** — the
   centre slots first, the rest slots on a later pass. That staging used
   to be a durable ``SLEEPING`` record between two descriptors; it is now
   the scheduler's in-memory stage memory, and this job is told which
   stage it may spend.
5. **The wide tier** adds the regional-affine seed (ruling R-B) to a
   page-wide, distance-ranked anchor list: the gap-jumping case where
   per-anchor extrapolation has decayed but the page-average warp is
   still good (the sparse/confetti regime).
6. **The cold pair** (W4) is the last rung, and a pass runs it only when
   the scheduler CLAIMED it as cold — the flavour arrives on the job, its
   page set is derived here at fire time (:meth:`WindowJob._cold_pages`),
   and the carried FFT kernel proposes a seed pose that the ordinary
   ``place_addressed`` block then refines, re-reads and audits from
   pixels. Cold never commits a pose of its own, which is what keeps the
   transform arithmetic scheduling-class rather than evidence-class
   (``place_cold``).
7. **Subdivision** (W3) is not a step of this job and spends nothing
   here: the job's business is one rectangle, and when the ladder above
   leaves that rectangle dormant on one of v1's eligible refusals
   (:data:`SUBDIVISION_REFUSALS`) the SCHEDULER adds four corner
   windows to its set. What this module owns is the vocabulary — which
   refusals v1 sent to subdivision, and which it did not. Since W4 that
   vocabulary is v1's again: subdivision sits BEHIND the cold pair, not
   beside the wide tier (see :data:`SUBDIVISION_REFUSALS`).

THE FLOOR IS THE TRIED SET (ruling Q1)
--------------------------------------
The rival gate's declared domain prices this window's CUMULATIVE
distinct hypotheses — ``49 x (tried + offered)``, and nothing else
(:func:`pass_budget`). It is honest BECAUSE fires are deterministic:
repeating an identical hypothesis on identical pixels is the same trial,
not a new one, so de-duplicating by candidate is the true count and a
bare pass counter would price re-tries as new information. The derived
support floor grows with the domain (L7b), never shrinks, and is never
truncated to fit. A Stage-A term used to ride here too; it derived a
floor of 31 where v1 derives 30, and it was WITHDRAWN for v1 parity on
2026-08-18 (:func:`pass_budget` carries the derivation and the v1
citations).

WHAT THIS JOB WRITES
--------------------
Facts only, and only when it has one: a pose plus its evidence and
calibration (through the ONE shared emission block), the window's own
outcome record, and R5's lattice seed when this window's fit measured a
better one. **A failed pass writes NOTHING** — no no-op commit, no
scheduling state, no spend row. Readiness, the tried set, the stage
memory and the priority are the scheduler's, in memory, and a resume
rebuilds the set and re-tries at worst (Q1/Q4).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from ..capture import FootingFrame
from ..core import AttemptIdentity, Lease, ProgressSink, ResourceKey, SolveView
from ..core import WorkResult, Write, require_finite_positive
from ..format import FormatRowSpec, TileFormat
from . import place_cold, pose_audit
from .geometry import WINDOW_STEP_CELLS, apply_affine, invert_affine
from .lattice_seed import lattice_seed_key
from .place_model import AttemptBudget, PlacementConfig, WordAttemptBudget
from .place_shared import (donor_sources, emit_placement, place_addressed,
                           predict_from_page_affine, ring_targets,
                           sample_window)
from .place_tiers import COLD_TIERS
from .resample import resample_window
from .placement import REFUSAL_POSE, ROUTE_WORD, decode_word_address
from .words import SlotStage
from .plans import WindowPlan
from .pose_fit import AddressPatch
from .quarantine import OUTCOME_CONTRADICTION, is_quarantined
from .records import PoseRecord, WindowRecord, WindowStatus
from .reference import V1ReferenceField
from .view import PlaneView, as_plane

#: The route label the seeded search scores under. It is v1's ``chain``
#: because the KERNEL is v1's chain kernel and the label rides into
#: ``CandidateScore.route`` as provenance — the differential harness
#: compares both trees under this exact string.
ROUTE_CONSULT = "chain"

#: How many steers one consult keeps, before the tried set is subtracted.
#: Carried from package 2's ``MAX_HINT_ENTRIES`` (itself from v1's donor
#: portfolio cap ``place_model.MAX_LOWER_HINTS``) — the same number, now
#: a truncation of a fire-time query instead of a retention policy.
CONSULT_KEEP = 8

#: The wide tier's nearest-K. The same 8, deliberately: what widens at
#: that tier is the DISTANCE admitted (any, page-wide) and not the
#: portfolio size, so one number governs both and a measurement that
#: moves it moves one row.
WIDE_ANCHORS = 8

#: The one outcome the SCHEDULER reads by name: a pass whose ping offered
#: nothing this window had not already tried. It spent no tier, so the
#: scheduler must let it fall to its next one rather than sleep on a
#: tombstoned queue entry (``place_sched.settle``) — one word, spelled
#: once, because two files share it.
NOTHING_TO_TRY = "nothing_to_try"

#: The word route's refusal, spelled once because the stage rides its
#: tail and :data:`SUBDIVISION_REFUSALS` has to enumerate the results.
NO_WORD_CANDIDATE = "no_word_candidate"

#: The route label a COLD acceptance rides into ``route_taken`` (W4). It
#: is v1's own name for the tier, so the differential harness's census
#: reads one word across both trees.
ROUTE_COLD = "correlation"

#: THE COLD REFUSAL, with the flavour on its tail for the same reason the
#: word refusal carries its stage: which page set was swept and came back
#: empty-handed is what an operator reads. It IS a subdivision refusal —
#: it is v1's :1495 site, the one that reaches ``refuse_unplaced`` — and
#: :data:`SUBDIVISION_REFUSALS` enumerates it per flavour.
COLD_REFUSED = "cold_refused"

#: The refusals that subdivide THE MOMENT THEY LAND, before any cold pass
#: (v1's two direct sites, :1244 and :1173 — see
#: :data:`SUBDIVISION_REFUSALS`). Neither window has a correlation left
#: to run: one never fitted a pose, and the other spent its address on an
#: audit that refused it.
SUBDIVISION_DIRECT: frozenset[str] = frozenset({
    REFUSAL_POSE,
    "straddle_audit_refused",
})

#: THE SUBDIVISION-ELIGIBLE REFUSALS (W3/PL5), TRANSCRIBED FROM v1.
#:
#: v1 calls ``subdivide_into_pending`` from exactly three places in
#: ``src/holo/receive/place.py`` (at 594a465, the port's own base):
#:
#: * **:1244** — ``attempt_cheap``: ``fit_window_pose`` returned ``None``.
#:   The window's own fit refused, so no route ever ran. Here that is
#:   :data:`~holo2.solve.placement.REFUSAL_POSE`, the ONE eligible refusal
#:   that reaches this job from outside its ladder.
#: * **:1173** — ``finalize_accept``: ``_finalize_patch`` returned no
#:   placement, i.e. the bounded refinement plus the binomial-impurity
#:   straddle audit refused an address the search had already accepted
#:   (v1's ``audit_refused``). Here: ``straddle_audit_refused``.
#: * **:1126** — ``refuse_unplaced``, reached from ``run_cold`` at
#:   :1495 when the LAST tier refused. In v1 that call site is behind
#:   the correlation and NOWHERE ELSE: a window that exhausts the cheap
#:   ladder is DEFERRED to cold, and only cold's own refusal quarters it.
#:
#: W4 RESTORES THAT ORDER (the 2026-08-18 ruling). W3 wired the trigger
#: to the ladder's exhaustion refusals — ``wide_refused``,
#: ``consult_refused``, ``no_word_candidate_*`` — because cold did not
#: exist yet and dormancy was the only spelling of "everything cheaper
#: failed". Now it does exist, so those three spellings are GONE from
#: this set and the wide-exhausted window escalates to its own cold
#: tiers instead; the cold refusal below is what quarters it. Cold needs
#: no consult seed, so the :data:`NOTHING_TO_TRY` window that used to
#: strand at wide has somewhere to go as well.
#:
#: WHAT v1 DELIBERATELY DOES NOT SUBDIVIDE ON, and neither does this:
#: ``placement.REFUSAL_SUPPORT`` (v1 :1259-1271 returns without a
#: call — too few supported sites is a statement about how much paper is
#: under the rectangle, and quartering it can only take away more), and
#: the retiring refusals, which leave the set outright.
#:
#: The set is only half the trigger. The other half is WHERE it fires:
#: the scheduler subdivides on an eligible refusal that leaves the
#: window DORMANT, and it offers the cold pair FIRST
#: (``place_sched.settle``, and the ruling it cites).
SUBDIVISION_REFUSALS: frozenset[str] = SUBDIVISION_DIRECT | frozenset(
    f"{COLD_REFUSED}_{flavor}" for flavor in COLD_TIERS)

#: The regional-affine candidate's stable name (ruling R-B). The affine
#: terms ride in the id because the fit MOVES as poses land, and a
#: re-fitted regional affine is genuinely a new hypothesis — while an
#: unchanged one is genuinely the same trial and must not be re-priced.
REGIONAL_SEED = "regional-affine"


# ------------------------------------------------------- the ratified distance
#
# The consult's SORT KEY, and the scheduler's priority (R-A). Ratified by
# the user 2026-08-16 as the hint state's score and KEPT when that record
# died: the pull model deleted the durable hint, not the currency it was
# scored in. It lives here because the consult is what computes it now —
# ``place_sched`` imports it from the job for the same reason it imports
# :class:`WindowJob`.
#
# Plain scaled distance, ONE currency, no class prefix: centre-to-centre
# cells at the CONSULTING footing over the window stride, so an adjacent
# window scores exactly 1.0 and a pose inherited from a coarser footing at
# the same location exactly 0.0 — the strongest steer there is. That is
# what makes a cross-footing donor outrank a stride-distant neighbour
# without a class to say so, and it is why v1's chain-before-donor ladder
# ORDER is deliberately not reproduced.
#
# Cells, not pixels, and at the consulting footing: a window's extent is
# named in the capture-cell lattice, which is a property of ``(capture,
# region)`` and is SHARED by every footing of that capture (``geometry``
# convention 2), so a donor from a coarser footing of the same capture
# needs no conversion at all and "colocated" is exactly colocated. There
# is no ring across captures, so nothing here ever converts.


def window_centre_cells(extent_cells: tuple[int, int, int, int]
                        ) -> tuple[float, float]:
    """The midpoint of a half-open ``(cy0, cx0, cy1, cx1)`` extent."""
    return ((extent_cells[0] + extent_cells[2]) / 2.0,
            (extent_cells[1] + extent_cells[3]) / 2.0)


def hint_distance(source_centre_cells: tuple[float, float],
                  hinted_centre_cells: tuple[float, float],
                  stride_cells: float) -> float:
    """Centre-to-centre cells over the window stride — the whole score.

    Both centres are in the CONSULTING window's cell frame (see above).
    The two anchors the ruling names are EXACT, not approximate: one
    stride apart scores 1.0 (``hypot(s, 0) == s`` for every finite ``s``,
    and ``s / s == 1.0``), and the same location scores 0.0.
    """
    require_finite_positive(stride_cells, "stride_cells")
    return math.hypot(hinted_centre_cells[0] - source_centre_cells[0],
                      hinted_centre_cells[1] - source_centre_cells[1]
                      ) / float(stride_cells)


@dataclass(frozen=True)
class Seed:
    """One hypothesis this window may be tested against, and where from.

    ``candidate_id`` is the tried set's element: a source POSE key for an
    extrapolated anchor (a pose predicts one frame, so the same source
    arriving twice is the same trial) and the regional fit's own terms
    for R-B's extra candidate.
    """

    candidate_id: str
    page: int
    distance: float
    affine: tuple[float, ...]

    def order_key(self) -> tuple[object, ...]:
        """SMALLEST is best: distance, then values — never arrival order."""
        return (self.distance, self.candidate_id, self.affine)


# ------------------------------------------------------------- the consult

def _anchor_plans(view: PlaneView, plan: WindowPlan, *,
                  wide: bool) -> tuple[WindowPlan, ...]:
    """The windows whose poses may steer this one, at this pass's reach.

    Ring reach is package 2's geometry read in the consulting voice: the
    eight lattice neighbours on this footing (adjacency is symmetric, so
    ``ring_targets`` answers both voices) plus the coarser-footing
    windows that cover this one (``donor_sources``, the donor direction
    inverted). Wide reach is every window of this region on every footing
    of the capture — the distance ranking below is what makes "nearest-K
    at any distance" out of it.
    """
    if not wide:
        return (*ring_targets(view, plan), *donor_sources(view, plan))
    others: list[WindowPlan] = []
    for footing_id in view.footing_ids("all"):
        others.extend(
            candidate for candidate in view.window_plans(footing_id)
            if candidate.region_id == plan.region_id
            and candidate.capture_sha256 == plan.capture_sha256
            and candidate.window_id != plan.window_id)
    return tuple(others)


def consult(view: PlaneView, plan: WindowPlan, row: FormatRowSpec, *,
            wide: bool = False) -> tuple[Seed, ...]:
    """What the committed poses around this window predict FOR it.

    The pull model's step (b), and the whole reason no hint is durable:
    every input is read at fire time, so a seed cannot be stale, cannot
    need retaining, and cannot be improved-in-place by a concurrent
    writer. The sort key is the ratified distance — centre-to-centre
    cells at the hinted footing over the window stride, so an adjacent
    window scores 1.0 and a colocated donor from a coarser footing scores
    0.0, the strongest steer there is (:func:`hint_distance` above,
    ratified 2026-08-16 and kept when its record died).

    Truncation is the ruling's own order — sort, keep
    :data:`CONSULT_KEEP`, and let the CALLER subtract its tried set — so
    the portfolio a window may ever try is bounded by what it can see and
    not by how often it has been woken.
    """
    here = window_centre_cells(plan.extent_cells)
    stride = float(WINDOW_STEP_CELLS)
    index = view.index()
    seeds: list[Seed] = []
    for anchor in _anchor_plans(view, plan, wide=wide):
        distance = hint_distance(
            window_centre_cells(anchor.extent_cells), here, stride)
        # ONE STEER PER ANCHOR WINDOW: its LIVE pose (tilemap choice 8,
        # RULING I3, 2026-08-23). An anchor that RF1 has revised carries
        # two committed poses; offering both would spend two of the
        # ``CONSULT_KEEP`` slots on one neighbour and weight it twice in
        # a ranking whose whole content is "one prediction per nearby
        # window". And WHICH of the two won a distance tie was an
        # unpredictable property of the affine's digits, since
        # ``Seed.order_key`` breaks on the id — the ruling removes the
        # question rather than resolving it in either direction (the
        # first wording of this comment claimed the stale one always
        # won; W3 review, 2026-08-23).
        pose_id = index.live_pose(anchor.window_id)
        if pose_id is None:
            continue
        pose = view.record(pose_id)
        if not isinstance(pose, PoseRecord):
            continue
        if is_quarantined(pose):
            # W5's never-return, in the pull model's own voice: v1
            # removed a quarantined placement's continuation HINTS
            # (``promoted_continuation_hints``); here there are no
            # hints to remove, so the filter sits on the query that
            # replaced them. A condemned pose is retained as a
            # record and never offered as a steer, ever again.
            continue
        if pose.page not in row.page_domain:
            continue
        seeds.append(Seed(str(pose_id), pose.page, distance,
                          tuple(pose.native_affine)))
    seeds.sort(key=Seed.order_key)
    return tuple(seeds[:(WIDE_ANCHORS if wide else CONSULT_KEEP)])


def regional_seed(view: PlaneView, plan: WindowPlan,
                  row: FormatRowSpec) -> Seed | None:
    """R-B: ONE extra candidate, the least-squares affine over the region.

    v1's regional fit, resurrected as a fire-time query. Every committed
    pose of the region contributes its window's four extent corners as
    (page cell, native pixel) correspondences — the pose says where the
    page sits under those pixels — and one affine is fitted through all
    of them. What it rescues is the case per-anchor extrapolation cannot:
    a window far from every placed neighbour, where each individual
    prediction has decayed but the page-average warp is still good (the
    sparse/confetti regime).

    ONE page: poses of different pages are different frames and pooling
    them would fit a correspondence that exists nowhere. The region's
    majority page wins, lowest index breaking a tie, which is the page a
    gap-jumping window is overwhelmingly likely to be on.

    ``None`` where there is nothing to average — fewer than TWO placed
    windows on the region's majority page, or a degenerate system
    (numpy's own rank test). Two is the floor by argument, not by
    arithmetic: one pose's four corners determine an affine exactly, so
    a "regional" fit over one window IS that window's pose, which the
    consult already offered as a seed of its own. A refusal here costs
    the wide pass one candidate and nothing else.
    """
    region = view.region(plan.region_id)
    if not region.schedulable or region.lattice is None:
        return None
    lattice = region.lattice
    index = view.index()
    by_page: dict[int, list[np.ndarray]] = {}
    for anchor in _anchor_plans(view, plan, wide=True):
        # The four corners are the ANCHOR's, not the pose's: one window,
        # one set of native pixels, and since choice 8 exactly one pose
        # supplies the correspondence for them.
        cy0, cx0, cy1, cx1 = anchor.extent_cells
        corners_y = np.asarray([lattice.centres_y(cy0, cy0 + 1)[0],
                                lattice.centres_y(cy1 - 1, cy1)[0]],
                               np.float64)
        corners_x = np.asarray([lattice.centres_x(cx0, cx0 + 1)[0],
                                lattice.centres_x(cx1 - 1, cx1)[0]],
                               np.float64)
        native_y = np.repeat(corners_y, 2)
        native_x = np.tile(corners_x, 2)
        # One window, one set of corners, ONE pose: the live one (tilemap
        # choice 8). A revised anchor contributed its four corners TWICE
        # before this, which double-weights that window in a least-squares
        # fit whose premise is one correspondence set per placement.
        pose_id = index.live_pose(anchor.window_id)
        if pose_id is not None:
            pose = view.record(pose_id)
            if not isinstance(pose, PoseRecord):
                continue
            if is_quarantined(pose):
                continue      # W5: a condemned pose steers nothing, here either
            if pose.page not in row.page_domain:
                continue
            page_y, page_x = apply_affine(
                invert_affine(pose.native_affine), native_y, native_x)
            by_page.setdefault(int(pose.page), []).append(
                np.stack([page_y, page_x, native_y, native_x], axis=1))
    if not by_page:
        return None
    page = min(by_page,
               key=lambda candidate: (-len(by_page[candidate]), candidate))
    if len(by_page[page]) < 2:
        return None
    rows = np.concatenate(by_page[page], axis=0)
    design = np.stack([rows[:, 0], rows[:, 1],
                       np.ones(rows.shape[0], np.float64)], axis=1)
    solution, _residuals, rank, _singular = np.linalg.lstsq(
        design, rows[:, 2:4], rcond=None)
    if int(rank) < 3:
        return None
    terms = (float(solution[0, 0]), float(solution[1, 0]),
             float(solution[2, 0]), float(solution[0, 1]),
             float(solution[1, 1]), float(solution[2, 1]))
    if not bool(np.isfinite(terms).all()):
        return None
    return Seed(f"{REGIONAL_SEED}/{terms}", page, float("inf"), terms)


# -------------------------------------------------------------- the budget

def pass_budget(budget: AttemptBudget, *, tried: int,
                offered: int, words_spent: int) -> AttemptBudget:
    """Q1's floor: this window's CUMULATIVE distinct hypotheses, priced.

    ``budget.max_hypotheses`` is the qualified per-seed search shape (49 =
    ``(2r+1)^2``); a window's statistical domain is that shape times every
    DISTINCT candidate it has ever tried or is about to try. The derived
    support floor is a function of that number
    (``AttemptBudget.min_support``), so the gate tightens as a window
    accumulates trials and never loosens — the
    gate-constants-vs-construction-floors discipline, with the tried set
    as the honest counter.

    V1 PARITY (user ruling 2026-08-18, "we want parity to v1"). The domain
    is ``49 x candidates`` and NOTHING else, because that is v1's own
    per-route arithmetic on every route this one pooled budget replaces:

    * chain — ``holo/receive/place.py:217`` ``_chain_budget`` declares
      ``per_anchor * n_anchors`` with ``per_anchor = (2r+1)**2``, and
      ``place.py:195`` (inside ``_chain_search``) is its only caller.
      Pooled ``candidates`` is the tried-set spelling of ``n_anchors``:
      same shape, same single term.
    * word — ``place.py:1344`` hands ``_word_route`` ``budgets.local``
      UNMODIFIED, so the per-candidate scoring at ``place.py:438`` runs at
      ``max_hypotheses = 49``. v1 never adds the Stage-A domain to a
      placement ``AttemptBudget``: Stage A is priced in its OWN currency,
      the single-word union bound at ``holo/receive/words.py:78``
      (``WordAttemptBudget.random_union_bound``) against
      ``familywise_false_accept`` — a false-accept budget, not the
      identifiability site count that ``min_support`` derives.

    WITHDRAWN DEVIATION (W2 Q1, withdrawn 2026-08-18): a
    ``+ word_units * words_spent`` term used to sit in ``domain``. At the
    production Stage-A domain of 147,456 phases, two spent stages put the
    domain at 294,961 — past the 250,530 knee where
    ``ceil(log2 D / (1 - h2(0.08)))`` crosses 30 -> 31. ``min_support``
    then stopped being pinned at ``E022_SUPPORT_FLOOR_SITES`` and a window
    supported at EXACTLY the 30-site floor, which v1 admits because the
    comparison is ``>=``, was refused. Its direction was a BAR — it
    refused what v1 admitted; it never bought an extra attempt.

    ``words_spent`` still rides the id, so an admission record reads back
    which word stages the pass had spent even though they no longer price
    it.
    """
    candidates = max(1, int(tried) + int(offered))
    domain = budget.max_hypotheses * candidates
    return replace(
        budget, max_hypotheses=max(budget.max_hypotheses, int(domain)),
        qualification_id=(f"{budget.qualification_id}/pull-{candidates}"
                          f"-candidates-{int(words_spent)}-words"))


# ----------------------------------------------------------------- the job

class WindowJob:
    """One ready window, one pass: consult, search, word, emit."""

    def __init__(self, plan: WindowPlan, spec: TileFormat, row: FormatRowSpec,
                 *, wide: bool, stage: SlotStage | None,
                 tried: frozenset[str], words_spent: int,
                 config: PlacementConfig, budget: AttemptBudget,
                 word_budget: WordAttemptBudget,
                 reference: V1ReferenceField,
                 cold: str | None = None,
                 cold_budget: AttemptBudget | None = None,
                 resample: bool = False) -> None:
        self.plan = plan
        self.wide = wide
        self.stage = stage
        #: THIS PASS IS A RE-READ, not a placement (F2a, ruling J2-3).
        #: The window is already placed and its live pose has never been
        #: sampled through; the whole pass is
        #: :func:`holo2.solve.resample.resample_window`, which consults
        #: nothing, searches nothing and proposes no geometry.
        self.resample = resample
        #: WHICH COLD FLAVOUR THIS PASS IS, or ``None`` for every other
        #: tier (W4). The scheduler decides it; the page set it implies is
        #: derived HERE, at fire time, from the view this pass reads.
        self.cold = cold
        self._spec = spec
        self._row = row
        self._tried = tried
        self._words_spent = words_spent
        self._config = config
        self._budget = budget
        self._cold_budget = cold_budget
        self._word_budget = word_budget
        self._reference = reference
        #: What the scheduler folds back in at :meth:`settle` time: the
        #: candidates this pass consumed and the word stage it spent.
        self.tried_now: tuple[str, ...] = ()
        self.stage_spent: SlotStage | None = None
        self.wide_spent = False
        #: The cold flavour this pass actually SPENT. It is not simply
        #: ``cold``: a flavour whose set was empty after the tried-set
        #: subtraction swept nothing, and a pass that never reached its
        #: sweep (its own fit refused) spent nothing either.
        self.cold_spent: str | None = None
        #: The residency this pass declares while it runs (M5) — read by
        #: the engine when it arms the job, released when it disarms.
        self.leases: tuple[Lease, ...] = ()
        #: WHICH half of the ladder produced this pass's address, for the
        #: observers that attribute a pose to a route (the differential
        #: harness's census). Provenance only — nothing schedules on it,
        #: and it is not durable, because a route is no longer an
        #: identity here: one job, two ways of reaching an address.
        self.route_taken: str | None = None

    # -- read-set ----------------------------------------------------------

    def read_keys(self, view: SolveView) -> tuple[ResourceKey, ...]:
        """ONE key: R5's lattice seed. Not a subscription — an ARBITER.

        A descriptor worker declares the keys whose versions ARE its
        attempt identity, so the wall can refuse a second spend and the
        table can wake it when one moves. This job needs neither: it
        spends nothing, it runs because a flag was set, it reads whatever
        is committed at the moment it fires, and a failed pass leaves no
        durable trace to be idle against. What used to be a subscription
        is the ping, and what used to be spend-once is the ready bit plus
        the tried set (``place_sched``).

        The seed is the exception, and it is here for the reason package
        2 bound its hint ring: **a worker that may WRITE a key whose
        transition law can REFUSE must bind that key's version.** R5's
        law is "a lattice seed is replaced only by a better-supported
        source", the write is a read-modify-write computed in the fire,
        and two windows fitting at once both read "no seed" — so without
        this binding the loser proposes a worse seed and the wall raises
        a ``CommitRefusal`` that is not a ``CertificateConflict``, which
        ends the run. MEASURED, not feared: the spine fixture died
        exactly this way at four workers (standing 39,896 cells,
        refusing 39,748) before the key was bound.

        With it bound the same race is the engine's ordinary staleness
        path — the loser's identity no longer binds at admission, its
        proposal is discarded as waste, and its window is simply
        claimable again. One key, O(1), and it is the key this fire
        already reads.
        """
        as_plane(view)
        return (lattice_seed_key(self.plan.footing_id, self.plan.region_id),)

    # -- the fire ----------------------------------------------------------

    def run(self, view: SolveView, identity: AttemptIdentity,
            progress: ProgressSink) -> WorkResult:
        plane = as_plane(view)
        plan = self.plan
        progress.emit(1, "window-gate")
        if plane.window_is_done(plan):
            # (a) THE LAZY COVERED-EXIT. Asked before a pixel is read and
            # before a seed is derived: the cheapest possible answer to
            # "is there anything to do here", and the one that retires a
            # window nobody will ever pose. It comes FIRST for the
            # re-read too: a window whose every tile is certified has
            # nothing a fresh reading could buy.
            return self._retire(plane, "done_covered")
        if self.resample:
            # (a') THE RE-READ (F2a). Everything below this line is about
            # finding an address; this window has one, committed, and the
            # only question is what its pixels say through the LIVE pose.
            # THE FUNCTION, not the module (F2a review fix,
            # 2026-08-23): ``resample`` is also this job's own flag, so
            # a module import under that name is shadowed by the
            # constructor's parameter and the next line in ``__init__``
            # that wanted the module would silently get a bool.
            return resample_window(
                plane, plan=plan, row=self._row, reference=self._reference,
                config=self._config, progress=progress)
        if plane.poses_of_window(plan.window_id):
            # Placed while this pass was being scheduled. Not a defect:
            # the scheduler's exit is a set membership, and a window can
            # only be claimed once, so this is the resume/replay path.
            return WorkResult(outcome="settled_placed", retire=True)
        seeds = self._seeds(plane)
        will_word = not seeds and self.stage is not None
        cold_pages = self._cold_pages(plane)
        if not seeds and not will_word and not cold_pages:
            self.wide_spent = self.wide
            # A COLD FLAVOUR WITH NOTHING LEFT TO SWEEP IS SPENT, and that
            # is not ruling 2's skip: the skip belongs to a flavour never
            # OFFERED because its whole page set was empty, which never
            # reaches this job. Here the flavour was offered and every page
            # in it is already in this window's tried set, so the answer
            # cannot change and the window must fall to its next tier
            # rather than be offered this one forever.
            self.cold_spent = self.cold
            if self.cold is not None:
                # ... and it answers with cold's OWN refusal rather than
                # with ``NOTHING_TO_TRY``, because the two words mean
                # different things to the scheduler since W4: this flavour
                # came back empty-handed, which is a subdivision trigger
                # (v1's :1495), while ``NOTHING_TO_TRY`` says a PING was
                # spent and no tier was.
                return WorkResult(outcome=self._refusal(()))
            return WorkResult(outcome=NOTHING_TO_TRY)
        budget = pass_budget(
            self._budget,
            tried=len(self._tried), offered=len(seeds),
            words_spent=self._words_spent + int(will_word))
        sampled = sample_window(plane, plan, config=self._config,
                                progress=progress)
        writes = sampled.seed_writes
        if sampled.patch is None or sampled.region is None:
            assert sampled.refusal is not None
            if sampled.retire:
                return self._retire(plane, sampled.refusal)
            # NOT durable and NOT charged: a window whose own fit refused
            # tried no hypothesis, so nothing joins its tried set and its
            # stage memory does not move. A better lattice seed re-arms it
            # (``place_sched`` pings a region whose seed improved).
            return WorkResult(outcome=sampled.refusal, writes=writes)
        assert sampled.frame is not None      # it rides every sampled patch
        address = self._search(sampled.patch, sampled.frame, seeds, budget,
                               progress)
        if address is not None:
            self.route_taken = ROUTE_CONSULT
        if address is None and will_word:
            assert self.stage is not None
            decoded = decode_word_address(
                sampled.patch, self._spec, self._row, stage=self.stage,
                word_budget=self._word_budget, budget=budget,
                reference=self._reference, progress=progress,
                config=self._config,
                batched_sweep=self._config.batched_word_sweep)
            self.stage_spent = self.stage
            if decoded is not None:
                address = (decoded.page, decoded.rot_k, decoded.origin_yx)
                self.route_taken = ROUTE_WORD
        # THE LAST RUNG (W4). It is reached only on a claim the scheduler
        # priced as cold, so it never competes with the two above for a
        # pass — and the address it may propose goes through exactly the
        # same refinement and audit as every other route's, under the
        # budget its own domain was declared at.
        if address is None and cold_pages:
            assert self._cold_budget is not None
            self.tried_now += tuple(place_cold.cold_tried_id(page)
                                    for page in cold_pages)
            self.cold_spent = self.cold
            address = place_cold.cold_address(
                sampled.patch, self._reference, cold_pages,
                self._cold_budget, config=self._config, progress=progress)
            if address is not None:
                self.route_taken = ROUTE_COLD
                budget = self._cold_budget
        self.wide_spent = self.wide
        if address is None:
            return WorkResult(outcome=self._refusal(seeds), writes=writes)
        page, rot_k, origin_yx = address
        placed = place_addressed(
            sampled.region, sampled.patch, page=page,
            page_origin_yx=origin_yx, rot_k=rot_k, reference=self._reference,
            config=self._config, budget=budget, progress=progress,
            frame=sampled.frame)
        if placed is None:
            # NOT retired (the default): v1 sent a centre candidate that
            # failed the straddle audit straight to subdivision and never
            # to the rest sweep. This ``WorkResult`` carries no ``retire``,
            # so the pull job's ladder re-arms the window instead and it
            # climbs to its next unspent word stage (``place_sched.settle``)
            # — REST becomes eligible here where v1 never offered it. Same
            # Stage-A domain, same gates re-cleared on the rest pass; the
            # statistical envelope is unaffected, only the route widens.
            return WorkResult(outcome="straddle_audit_refused", writes=writes)
        pose = PoseRecord(window_id=plan.window_id,
                          footing_id=plan.footing_id, page=page,
                          native_affine=placed.affine)
        emission = emit_placement(
            plane, row=self._row, plan=plan, pose=pose, placement=placed,
            provider=self._reference, progress=progress)
        if emission.outcome == OUTCOME_CONTRADICTION:
            # W5. The placement emitted NO evidence; what it proposes is
            # the durable fact plus the condemnation of the standing
            # side, and the pose it would have committed is committed
            # BORN QUARANTINED so the fact's contributor set names a
            # record (``quarantine``). The window is terminal: its own
            # words contradicted its own geometry, so re-running the
            # same rectangle over the same pixels can only say it again.
            return WorkResult(
                outcome=emission.outcome, retire=True,
                writes=(writes + emission.writes
                        + (Write(pose.resource_key(),
                                 replace(pose, quarantined=True)),)
                        + self._window_write(plane, WindowStatus.RETIRED,
                                             emission.outcome)))
        if not emission.accepted:
            return WorkResult(outcome=emission.outcome, writes=writes)
        return WorkResult(
            outcome="accepted",
            writes=(writes + emission.writes
                    + self._window_write(plane, WindowStatus.ACTIVE)),
            blobs=emission.blobs)

    # -- the ladder --------------------------------------------------------

    def _seeds(self, view: PlaneView) -> tuple[Seed, ...]:
        """Step (b): consult, truncate, subtract what this window tried."""
        offered = list(consult(view, self.plan, self._row, wide=self.wide))
        if self.wide:
            extra = regional_seed(view, self.plan, self._row)
            if extra is not None:
                offered.append(extra)
        return tuple(seed for seed in offered
                     if seed.candidate_id not in self._tried)

    def _cold_pages(self, view: PlaneView) -> tuple[int, ...]:
        """THE COLD CONSULT: this flavour's pages, minus the swept ones.

        The same shape as :meth:`_seeds` and for the same reason — every
        input is read at the moment the fire runs, so the set cannot be
        stale and nothing about it is retained. What the flavour names is
        derived from the committed poses (``place_cold.live_pages``); what
        this window has already paid for is subtracted from it.

        THE DEDUP IS PER PAGE (the ruled granularity). The two flavours
        partition the domain at any one instant, so a live sweep and a
        rest sweep are naturally disjoint — but ``live`` GROWS, so a page
        swept under rest can turn up in a later live set, and without this
        subtraction the window would pay for the same page twice. It is
        honest for the same reason the seed tried-set is: fires are
        deterministic, so re-sweeping a page with the same patch is the
        same trial, not a new one.
        """
        if self.cold is None:
            return ()
        pages = place_cold.cold_pages(
            self._row, self.cold, place_cold.live_pages(view))
        return tuple(page for page in pages
                     if place_cold.cold_tried_id(page) not in self._tried)

    def _search(self, patch: AddressPatch, frame: FootingFrame,
                seeds: tuple[Seed, ...],
                budget: AttemptBudget, progress: ProgressSink,
                ) -> tuple[int, int, tuple[int, int]] | None:
        """v1's ``_chain_search`` over this pass's seeds, best first.

        One memo for the whole pass, as v1 keeps one per patch: the
        neighbourhoods of two seeds overlap heavily, and a repeated probe
        is the same question about the same pixels. Every seed offered is
        CHARGED to the tried set whether or not the search reached it —
        a seed the loop stopped short of is one this window will offer
        itself again on its next pass only if it is still visible, and
        pricing it now is the conservative direction.

        ``frame`` is THIS window's rung. Every seed's affine is
        native-frame (that is what a committed pose is), and the patch's
        own pose is in the rung's pixels, so the prediction converts once
        per seed — the identity at the native rung, which is why a
        single-lane run's search is the search it always was.
        """
        if not seeds:
            return None
        self.tried_now = tuple(seed.candidate_id for seed in seeds)
        memo = pose_audit.ScoreMemo(self._reference)
        for seed in seeds:
            rot_k, predicted = predict_from_page_affine(
                seed.affine, patch.frame_pose, patch.shape_yx, frame)
            outcome = pose_audit.local_search(
                patch, seed.page, rot_k, predicted, budget, memo,
                sample_key=0, config=self._config, route=ROUTE_CONSULT)
            if outcome.accepted:
                assert outcome.best is not None
                progress.emit(1, "consult-search")
                return (seed.page, rot_k, outcome.best.origin_yx)
        progress.emit(1, "consult-search")
        return None

    def _refusal(self, seeds: tuple[Seed, ...]) -> str:
        """The outcome vocabulary, one word per thing that was attempted.

        Four words, because the ladder can only produce four: the word
        stage runs IF AND ONLY IF the consult came up empty (step (d)), so
        "the consult and the word both refused" is not a pass this job can
        make and is not a word this vocabulary has. A cold pass is claimed
        as cold and spends only its sweep, so it answers for itself —
        naming the FLAVOUR, because which page set came up empty-handed is
        the thing an operator would want to read.
        """
        if self.cold_spent is not None:
            return f"{COLD_REFUSED}_{self.cold_spent}"
        if seeds:
            return "wide_refused" if self.wide else "consult_refused"
        return f"{NO_WORD_CANDIDATE}_{self.stage_spent}"

    # -- the durable outcome -----------------------------------------------

    def _retire(self, view: PlaneView, reason: str) -> WorkResult:
        """A terminal verdict about the WINDOW: durable, and an exit.

        ``retire`` is what the scheduler reads to drop this window from
        the set (``place_sched.settle``), so the outcome record and the
        set membership move together, in that order — the record first,
        because it is the only half that survives the process.
        """
        return WorkResult(
            outcome=reason, retire=True,
            writes=self._window_write(view, WindowStatus.RETIRED, reason))

    def _window_write(self, view: PlaneView, status: WindowStatus,
                      reason: str | None = None) -> tuple[Write, ...]:
        """The window's own outcome record — placed-by, or retired(reason).

        Written on the two OUTCOMES only (v5): the window population is
        read off these records (the differential harness's census, the
        observer's rows), so a placed window that appeared in neither
        would be invisible, while a window merely being worked on carries
        no durable state at all any more.
        """
        record = WindowRecord(
            footing_id=self.plan.footing_id, region_id=self.plan.region_id,
            extent_cells=self.plan.extent_cells, status=status,
            retired_reason=reason)
        if view.record(self.plan.window_id) == record:
            return ()
        return (Write(self.plan.window_id, record),)


__all__ = [
    "COLD_REFUSED", "CONSULT_KEEP", "NOTHING_TO_TRY", "NO_WORD_CANDIDATE",
    "REGIONAL_SEED", "ROUTE_COLD",
    "ROUTE_CONSULT", "ROUTE_WORD", "SUBDIVISION_DIRECT",
    "SUBDIVISION_REFUSALS", "Seed",
    "WIDE_ANCHORS", "WindowJob", "consult",
    "hint_distance", "pass_budget", "regional_seed", "window_centre_cells",
]
