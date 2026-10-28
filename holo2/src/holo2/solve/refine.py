"""RF1: the certificate-labeled bounded pose revision (H5 P4).

The census's RF1 row (PROVIDERS §4) as a pull-model provider family: ONE
bounded pose revision per eligible (window, pose), fitted against labels
reconstructed from the committed certificate frontier, adopted only on
v1's held-out gain gate and v1's two pilot non-regression gates. The
arithmetic is ``src/holo/receive/certified_refine.py``'s, constant for
constant — bounds +-0.15 deg and +-0.25 cell, a fixed two-stage grid
(coarse 0.15/0.25, fine 0.05/0.0625), the block-stripe cargo holdout,
the deterministic site caps, the weighted log-loss and the contrast
objective. None of it is re-derived here and none of it is tuned.

WHAT IS PROPOSED, AND WHAT IS NOT (the pull model's own shape). An
adopted revision writes a NEW ``PoseRecord`` at a NEW pose key — the
pose's identity IS its affine (``keys.POSE_SPEC``), so a revised pose is
an ORDINARY pose, not a mutation and not a new record kind. The standing
pose REMAINS: nothing is retracted, no certificate moves, no evidence is
rewritten, and readers re-arm through the staleness they already have
(the window's pose collection versions on the new member). Done is
inviolable in the strongest available sense — this family cannot express
a write that touches a certificate.

WHICH OF AN EXTENT'S POSES THE REST OF THE TREE READS is not this
family's business and never was: since W3 it is
``tilemap.StoreIndex.live_pose`` — "the latest committed pose for that
extent wins" (RULING I3) — a read-time derivation the consumers share.
What IS this family's business is not manufacturing poses nobody asked
for, and that is the guard in :meth:`PoseRefineWorker.run`.

NO POSE SPAM, AND NO THRESHOLD (RULING I4/I4a, 2026-08-23). Two
mechanisms and deliberately no third:

* the NO-OP GUARD — a revision whose canonical affine equals the
  standing live pose is not committed, and one that equals an earlier,
  superseded pose of the same extent is reported separately and not
  committed either. A window revised twice to the same answer holds ONE
  revision;
* the TOP PRICE (``COST_REFINE`` = 200) — the family fires only when
  nothing cheaper is ready.

Re-arm stays per (pose, certificate-frontier version) exactly as built:
**k = 1**, every new certificate in reach re-arms, no "≥ k new
certificates" tightening. That is the user's own ruling and it is a
ruling about evidence — W2 measured the poses-per-extent distribution
(max 2, every pose fired once) and the no-op share (0 of 545 adopted
revisions) with revisions unread; W3 does not pre-empt what a productive
run will show.

A REVISION IS NEVER ITSELF ELIGIBLE, and since F2a (2026-08-23) that is
a STATED clause rather than an accident of the tree. Eligibility is
derived from EVIDENCE (:func:`reaches` groups the observation pieces by
the pose that produced them), and through F1 a revision had none —
nothing re-sampled through it, so it could not be a subject. F2a's
re-sample emitter (:mod:`holo2.solve.resample`) gives it evidence, so
the clause is now :attr:`Reach.revised`: an extent that already carries
a revision offers no subject at all, neither the revision nor the parent
that produced it. The fit's baseline therefore stays the geometry its
evidence was actually sampled at — the property the score convention
below rests on — and an extent holds at most two committed poses, which
is what lets :mod:`holo2.solve.generation` name "the newest pose that
has pieces" without a commit ordinal.

ELIGIBILITY IS THE E024 LESSON, AND IT IS NEW WORK. e024 measured
post-cascade broad feedback as near-worthless: refinement pays at the
margins or not at all. So a pose is offered a revision only where its
REACH TOUCHES UNCERTIFIED RESIDUE — a pose whose every observed tile is
already certified has nothing to buy, and mints no descriptor at all.
The reach is derived, never recorded: a pose's evidence pieces name the
tiles it observed (``keys.EVIDENCE_SPEC`` carries page/ty/tx/stream), and
the tile map says which of those are certified. Facts derive work, so
this is a provider-side derivation over the index and not a durable fact
anybody has to maintain. ``src/holo`` has no such K-path gate (the census
row says so); this is holo2's.

THE SECOND HALF OF ELIGIBILITY is not a policy choice but the algorithm's
own precondition: RF1 labels from CERTIFIED cargo, so a pose with no
certified tile in reach has no label channel and would refuse on v1's
own ``insufficient_payload_train`` floor. That refusal is CHEAP but not
free, so the reach test asks for both — some certified material to learn
from, some uncertified material to gain on. Both halves read the same one
derivation (:func:`reach`), which is what keeps them one idea.

PRICED AT THE TOP, NOT GATED (W3, RULING I2, the user's ruling of
2026-08-23). ``COST_REFINE`` is **200** — above ``COST_PLACE_COLD_REST``
(150), the dearest tier any other family DECLARES — so a revision fires
only when nothing cheaper is ready. "After the ladder" is therefore an
EMERGENT property of the pull model, not a phase, not a barrier and not
a settled-frontier rule anybody has to enforce.

WHERE THAT PROPERTY HOLDS, EXACTLY (W3 review, 2026-08-23; the full
ladder is in ``engine.recipe``'s comment on ``COST_REFINE``). A
descriptor's price is its entry plus a lane term, and the two families
carry DIFFERENT lane terms: refine adds ``LANE_COST_PER_RUNG`` (2) per
rung, a cold pass adds ``COLD_COST_PER_RUNG`` (20). Refine therefore
outranks every tier's declared cost, every ORDINARY pass at every depth,
and cold through rung 2 — and is overtaken by ``cold_rest`` from rung 3
(210 > 206) and ``cold_live`` from rung 4 (220 > 208), both reachable on
a 4800-dpi capture. On the two deepest cold rungs a revision preempts a
cold sweep that is still ready; the price is PROVISIONAL and that
inversion is the open half of it. The two-sided
eligibility gate below STAYS: it is the algorithm's own precondition and
e024's measured law, not an artificial one. Calibration's entry landed at
15 because a first fit must precede the decodes it improves; this one
lands at 200 for the opposite reason — a revision is worth asking for
only once everything cheaper has drained, which is exactly when the
certificate frontier is richest and the residue is smallest.

THE SCORE CONVENTION, AND WHY IT DIFFERS FROM v1 (read this before
comparing the two trees). holo2 calibrates on NEGATED RAW LUMA:
``place_shared`` emits ``scores = -means`` and fits the marginal PAVA on
that scale, so a committed ``CalibrationRecord``'s knots live there. v1
normalises first — ``(midpoint - raw) / spread`` — and its nodes live on
THAT scale. The two are related by a positive affine map, so the PAVA is
the same monotone map either way; what matters is that a refine must
score through the convention its own knots were fitted under. This module
therefore uses ``-means`` for the baseline AND for every candidate, which
buys a property v1 cannot state: the baseline logits this fire computes
are, cell for cell, the LLRs the evidence pieces already carry — both are
``calibration.llr(-means)`` through the same frozen record. Using v1's
normalisation here would be a bug, not a carry.

WHAT IS REPLAYED FROZEN. Generation-zero calibration, exactly as the
census row says (``certified_refine:677-702``): the pose's evidence cites
a ``CalibrationRecord`` by key, that record is FROZEN (F-08), and its
params blob holds the PAVA knots and probabilities. ``detect.Calibration``
also wants ``n_search``, which the params blob does not carry — so it is
RECONSTRUCTED as the smallest integer admitting the stored probabilities
(:func:`replay_calibration`). That is sound rather than approximate:
``Calibration.llr`` reads only knots and probabilities, so every legal
``n_search`` yields bit-identical logits, and the reconstruction exists
only to satisfy a constructor's support check.

NO CONTEXT ARM HERE. v1's refine carries a ``ContextDecision`` because
v1's generation-zero detector may already be the ctx profile. holo2's
never is: the ctx correction applies at DECODE ASSEMBLY (H5 P1,
``calibration.apply_component_context``), so an evidence piece's stored
LLR is always the MARGINAL one and ``certified_refine``'s
``_fixed_detector_logits`` reduces to its marginal branch. That is a
consequence of P1's design sentence, not a simplification of the carry.

QUARANTINE. A condemned pose never labels and never seeds a revision:
:func:`is_quarantined` is asked at expansion AND inside the fire, the
same predicate the consult, the payload read-set and the calibration pool
already read. The certificate frontier itself is NOT filtered — done is
inviolable and a condemned pose is a judgement about geometry, which is
P2's ruling and stands unchanged here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core import (AttemptIdentity, ExpansionRequest, FootingId,
                    ProgressSink, ResourceKey, SolveView, WorkDescriptor,
                    WorkResult, Write)
from ..format import TILE_CELLS, FormatRowSpec, TileFormat, tile_format_for
from . import detect
from .certified_labels import CertifiedLabelSource
from .keys import (COLLECTION_CERTIFIED, EVIDENCE_KEY_PARTS, KIND_EVIDENCE,
                   KIND_POSE, KIND_WINDOW, POSE_KEY_PARTS, WINDOW_KEY_PARTS,
                   parse_evidence_key, parse_window_key, tile_key)
from .place_model import PlacementConfig
from .place_tiers import LANE_COST_PER_RUNG
from .quarantine import is_quarantined
from .records import (CalibrationRecord, EvidenceObservation, PoseRecord,
                      unpack_observed_cells)
from .reference import ReferenceFieldProvider, V1ReferenceField
# The carried arithmetic, RE-EXPORTED on purpose (``refine_fit``'s own
# docstring says why): the split was a file-cap seam, not a second
# address. New code may import from either.
from .refine_fit import (ANGLE_COARSE_STEP_DEG, ANGLE_FINE_STEP_DEG,
                         ANGLE_LIMIT_DEG, BLOCK_CELLS, MIN_CERTIFIED_BLOCKS,
                         MIN_HELDOUT_GAIN, MIN_PAYLOAD_TRAIN,
                         MIN_PAYLOAD_VALIDATION, MIN_POSE_PILOTS,
                         MIN_TRAIN_PER_CLASS, MIN_VALIDATION_PER_CLASS,
                         OUTCOME_ADOPTED, OUTCOME_REFUSED_PREFIX,
                         PHASE_COARSE_STEP_CELLS, PHASE_FINE_STEP_CELLS,
                         PHASE_LIMIT_CELLS, PILOT_MISMATCH_SLACK,
                         POSE_SITE_CAP_TRAIN, POSE_SITE_CAP_VALIDATION,
                         SCORE_SPREAD_FLOOR, VALIDATION_MODULUS, RefineInput,
                         Revision, SegmentLabels, adoption_gate,
                         block_validation, block_weights, candidate_grid,
                         collect_labels, deterministic_cap, fine_grid,
                         local_segment, native_terms, pose_candidate,
                         pose_objective, propose, sample_at, select_best,
                         select_pose_sites, support_metrics, weighted_logloss)
from .view import PlaneView, as_plane

FAMILY_REFINE = "refine"

#: The census row's route name (PROVIDERS RF1: pose / ``refine-k`` /
#: certificate-frontier id).
ROUTE_REFINE_K = "refine-k"

# --------------------------------------------------------------- the reach

@dataclass(frozen=True)
class Reach:
    """What one pose observed, and how much of it is already done.

    Derived from the pose's evidence keys and the tile map — never
    recorded. ``pieces`` are the pose's observation keys in sorted order;
    ``certified``/``open`` partition the tiles they name.
    """

    pieces: tuple[ResourceKey, ...]
    certified: tuple[ResourceKey, ...]
    open: tuple[ResourceKey, ...]
    #: THIS EXTENT ALREADY CARRIES A REVISION (F2a, 2026-08-23): its
    #: window holds more than one committed pose. See :attr:`eligible`.
    revised: bool = False

    @property
    def eligible(self) -> bool:
        """Three clauses: something to gain on, something to learn from,
        and no revision standing on this extent already.

        The e024 gate is ``open`` — a pose whose supported extent is
        fully certified has nothing left to buy. The ``certified`` half
        is the algorithm's own precondition: certified cargo IS RF1's
        label channel, so a pose with none would walk the whole grid only
        to refuse on the carried payload-train floor.

        ``revised`` IS "A REVISION IS NEVER ITSELF ELIGIBLE", MADE
        STRUCTURAL (F2a, ruling J2-3; C4 §3.3(7)). Through F1 that
        property held by ACCIDENT: eligibility is derived from evidence,
        a revision had none, so it could not be a subject. F2a's
        re-sample gives it evidence, so the accident is gone and the
        property has to be spelled — and it is spelled over the EXTENT
        rather than over the pose, which also stops the parent proposing
        a SECOND revision off its own now-superseded evidence. One
        window, at most two committed poses, and that bound is what
        :mod:`holo2.solve.generation` reads "the newest pose that has
        pieces" off ``live_poses`` alone rather than off a commit
        ordinal. MEASURED NULL on the corpus: A2 counted 269/272 revised
        windows on the two real sheets and never a third pose, and the
        W2 resume measured max 2 with every pose firing once. Lifting
        the bar is a measurement (does a chain of two bounded ±0.25-cell
        revisions beat one?), and it owes ``generation`` an ordinal.
        """
        return bool(self.open) and bool(self.certified) and not self.revised


def pose_evidence_keys(plane: PlaneView,
                       pose_id: ResourceKey) -> tuple[ResourceKey, ...]:
    """The observation pieces standing on one pose, sorted.

    A pose does not index its pieces (the arrow runs the other way,
    §5.4), so this is the one-pass grouping ``calibration`` pays too. It
    is paid per pose per expansion, which is why :func:`reach` takes the
    whole index once and the provider walks it in a single sweep
    (:func:`reaches`) rather than calling this per candidate.
    """
    return tuple(sorted(
        key for key in plane.index().evidence_footings
        if key.kind == KIND_EVIDENCE and len(key.parts) == EVIDENCE_KEY_PARTS
        and ResourceKey(KIND_POSE,
                        key.parts[EVIDENCE_KEY_PARTS - POSE_KEY_PARTS:])
        == pose_id))


def reaches(plane: PlaneView) -> dict[ResourceKey, Reach]:
    """Every EVIDENCE-OWNING pose's reach, in ONE pass over that index.

    "Evidence-owning", not "live" (W3 review, 2026-08-23): the grouping
    is by evidence, and since W3 the pose that owns an extent's evidence
    is precisely the one a revision has SUPERSEDED — ``live`` is now a
    term of art for ``StoreIndex.live_pose`` and does not mean this
    one.

    Expansion runs on every refresh, so the shape that matters is the
    sweep: one walk of the evidence index groups pieces by pose, and one
    tile-map lookup per piece partitions them. Quarantined poses and
    quarantined pieces are dropped here — a condemned placement neither
    seeds a revision nor contributes a reach — which is the same
    predicate at the same boundary ``calibration.pool_members`` uses.
    """
    index = plane.index()
    grouped: dict[ResourceKey, list[ResourceKey]] = {}
    for key in index.evidence_footings:
        if key.kind != KIND_EVIDENCE or len(key.parts) != EVIDENCE_KEY_PARTS:
            continue
        if is_quarantined(plane.record(key)):
            continue
        pose = ResourceKey(KIND_POSE,
                           key.parts[EVIDENCE_KEY_PARTS - POSE_KEY_PARTS:])
        record = index.poses.get(pose)
        if record is None or is_quarantined(record):
            continue
        grouped.setdefault(pose, []).append(key)
    out: dict[ResourceKey, Reach] = {}
    for pose, keys in grouped.items():
        pieces = tuple(sorted(keys))
        certified: list[ResourceKey] = []
        open_tiles: list[ResourceKey] = []
        for key in pieces:
            _footing, page, ty, tx, stream, _pose = parse_evidence_key(key)
            target = tile_key(page, ty, tx, stream)
            record = index.tiles.get(target)
            (certified if record is not None and record.certified
             else open_tiles).append(target)
        window = ResourceKey(KIND_WINDOW, pose.parts[:WINDOW_KEY_PARTS])
        # CONDEMNED POSES DO NOT COUNT AS A GENERATION (F2a review fix,
        # 2026-08-23): both loops above filter ``is_quarantined``, and
        # W5 commits the decoded side of a contradiction "as a pose BORN
        # QUARANTINED", so a two-entry ``poses_by_window`` need not mean
        # this extent carries a revision. Counting it would make the
        # window permanently ineligible for RF1 while only one geometry
        # actually stands. Defensive: ``windows_three_plus_poses`` is 0
        # on both real states, and no live path to it was found.
        out[pose] = Reach(pieces, tuple(sorted(set(certified))),
                          tuple(sorted(set(open_tiles))),
                          sum(1 for other
                              in index.poses_by_window.get(window, ())
                              if not is_quarantined(
                                  index.poses.get(other))) > 1)
    return out


def reach(plane: PlaneView, pose_id: ResourceKey) -> Reach:
    """One pose's reach — the per-fire spelling of :func:`reaches`."""
    return reaches(plane).get(pose_id, Reach((), (), ()))


# ------------------------------------------------- generation-zero replay

def replay_calibration(plane: PlaneView, window_id: ResourceKey,
                       calibration_id: ResourceKey
                       ) -> detect.Calibration | None:
    """The frozen generation-zero PAVA of one window, or None.

    ``n_search`` is reconstructed rather than read — see the module
    docstring. The smallest integer admitting the stored probabilities is
    ``ceil(1/pmin) - 2`` where ``pmin`` is the tightest bound the
    probabilities themselves imply; ``Calibration.llr`` never reads it,
    so every legal choice gives bit-identical logits and this one is
    merely the one that always constructs.
    """
    record = plane.record(calibration_id)
    if not isinstance(record, CalibrationRecord):
        return None
    params = np.asarray(plane.read_array(record.params_ref), np.float64)
    if params.ndim != 2 or params.shape[0] != 2 or params.shape[1] < 1:
        return None
    knots, probabilities = params[0], params[1]
    edge = float(min(probabilities.min(), 1.0 - probabilities.max()))
    if not np.isfinite(edge) or edge <= 0.0:
        return None
    n_search = max(1, int(np.ceil(1.0 / edge)) - 2)
    while n_search > 1 and 1.0 / (n_search + 2.0) > edge:
        n_search += 1
    return detect.Calibration(str(window_id), knots, probabilities, n_search)


# -------------------------------------------------------------- the worker

class PoseRefineWorker:
    """ONE bounded pose revision for ONE pose: gather, search, gate, commit."""

    task_class = FAMILY_REFINE

    def __init__(self, pose_id: ResourceKey, base: ReferenceFieldProvider,
                 labels: CertifiedLabelSource, config: PlacementConfig
                 ) -> None:
        self.pose_id = pose_id
        # BOTH fields, because the pilot/cargo split IS the difference
        # between them: the base field's sites are v1's format-known
        # labels, and whatever the enriched field adds is v1's certified
        # cargo. Holding the base separately keeps that derivation a
        # subtraction rather than a second notion of "known".
        self._base = base
        self._labels = labels
        self._config = config

    @property
    def route(self) -> str:
        return ROUTE_REFINE_K

    def read_keys(self, view: SolveView) -> tuple[ResourceKey, ...]:
        """The pose, and the certificate frontier. Nothing else re-arms.

        * the POSE key — a condemnation marks the record (pose family
          v5), so a quarantine mid-flight kills the revision at the
          wall's existing staleness check, exactly as it kills a
          calibration fit;
        * ``COLLECTION_CERTIFIED`` — the certificate-frontier version,
          which IS the second half of the census's spend identity
          (PROVIDERS RF1: one spend per (pose, certificate-frontier
          version)). A new certificate is new label material and new
          residue accounting; nothing else about this fire's inputs can
          move, because evidence is frozen and the pose's affine is its
          own name.

        It is the GLOBAL collection rather than a reach-scoped one, and
        deliberately: a reach-scoped certified membership would be a new
        durable mechanism, while the re-work band already absorbs the
        churn a coarse wake buys (the argument ``calibration`` makes at
        length for the same key). The cost of the coarseness is
        descriptor arming, not spends — an unchanged reach re-derives the
        same refusal for the same reason.
        """
        return (COLLECTION_CERTIFIED, self.pose_id)

    def run(self, view: SolveView, identity: AttemptIdentity,
            progress: ProgressSink) -> WorkResult:
        plane = as_plane(view)
        # §10.3 has no silent stages, and this fire's cheapest paths are
        # REFUSALS — an ineligible reach, a detached capture, an
        # unreplayable calibration — every one of which returns before a
        # pixel is read. So the arming quantum is reported first, exactly
        # as the calibration fit reports its own.
        progress.emit(1, "arm")
        gathered = self._gather(plane, progress)
        if isinstance(gathered, str):
            return WorkResult(outcome=OUTCOME_REFUSED_PREFIX + gathered)
        data, labels, frame = gathered
        progress.emit(1, "refine-gathered")
        verdict = propose(data, labels, frame)
        progress.emit(1, "refine-searched")
        if not verdict.adopted or verdict.affine is None:
            return WorkResult(outcome=OUTCOME_REFUSED_PREFIX + verdict.reason)
        index = plane.index()
        pose = index.poses[self.pose_id]
        revised = PoseRecord(window_id=pose.window_id,
                             footing_id=pose.footing_id, page=pose.page,
                             native_affine=verdict.affine)
        key = revised.resource_key()
        # THE NO-OP GUARD (RULING I4, 2026-08-23): a revision whose
        # canonical affine equals the standing LIVE pose is not committed.
        # A pose IS its affine, so re-proposing one is a no-op rather than
        # a second record, and the canonical rounding
        # (POSE_TERM_DECIMALS) is what can make a sub-quantum revision
        # collapse onto the geometry it started from.
        #
        # THE TEST IS LIVENESS, NOT IDENTITY (W3 review, 2026-08-23). The
        # worker always fits from the SUBJECT pose — the parent that owns
        # the evidence — so once an extent carries a revision the subject
        # is no longer live, and a fit that returns to the subject's own
        # geometry is a search that MOVED AWAY AND CAME BACK. That is the
        # oscillation ``pose_already_stands`` exists to make visible, so
        # ``key == self.pose_id`` must fall through to it rather than be
        # folded into "unmoved" ahead of it.
        if key == index.live_pose(pose.window_id):
            return WorkResult(outcome=OUTCOME_REFUSED_PREFIX + "pose_unmoved")
        if plane.record(key) is not None:
            # The same guard's other half, reported SEPARATELY because it
            # says something different: the search landed on an EARLIER
            # revision of this extent, one the live pose has since moved
            # past. Committing nothing is right either way (the record
            # stands, and a pose is its affine), but a run where this
            # count climbs is a search oscillating between two answers,
            # which the ``pose_unmoved`` count cannot show.
            return WorkResult(
                outcome=OUTCOME_REFUSED_PREFIX + "pose_already_stands")
        return WorkResult(outcome=OUTCOME_ADOPTED,
                          writes=(Write(key, revised),))

    # -- internals ---------------------------------------------------------

    def _gather(self, plane: PlaneView, progress: ProgressSink
                ) -> tuple[RefineInput, SegmentLabels, object] | str:
        """Read every input, or name the first one that is missing."""
        pose = plane.index().poses.get(self.pose_id)
        if pose is None or is_quarantined(pose):
            # NAMES THE SUBJECT POSE, not ``StoreIndex.live_pose`` (W3
            # review, 2026-08-23): the descriptor's own subject is gone
            # or condemned. The string is recorded in spend rows on
            # archived states, so it is annotated rather than renamed.
            return "no_live_pose"
        found = reach(plane, self.pose_id)
        if not found.eligible:
            # Three clauses, three words. ``revised`` is F2a's: this
            # extent already carries a revision, so nothing here is a
            # subject any more. Reachable only by a race (expansion
            # mints no descriptor for an ineligible reach), and it is
            # named rather than folded into the residue reason so a
            # spend row says which clause closed the door.
            if found.revised:
                return "extent_already_revised"
            return ("no_uncertified_residue" if not found.open
                    else "no_certified_labels")
        window = ResourceKey(KIND_WINDOW,
                             self.pose_id.parts[:WINDOW_KEY_PARTS])
        footing_id, region_id, _extent = parse_window_key(window)
        if not plane.has_region(region_id) or not plane.has_footing_pixels(
                footing_id):
            return "no_pixels"
        prepared = plane.prepared_region(plane.region(region_id),
                                         config=self._config,
                                         footing_id=footing_id)
        frame = plane.footing_frame(footing_id)
        if prepared is None or frame is None:
            return "no_pixels"
        cells, calibration_id = self._observed(plane, found.pieces)
        if not cells.size:
            return "no_observed_cells"
        calibration = replay_calibration(plane, window, calibration_id)
        if calibration is None:
            return "no_generation_zero_calibration"
        segment, local = local_segment(pose.native_affine, frame, cells)
        means = sample_at(prepared.filtered, (prepared.y0, prepared.x0),
                          prepared.backing, segment.pose, local)
        progress.emit(1, "refine-sampled")
        labels = collect_labels(pose.page, cells, self._base,
                                self._labels.field(plane))
        data = RefineInput(pose.page, segment, local, cells, means,
                           calibration, prepared.filtered,
                           (prepared.y0, prepared.x0), prepared.backing)
        return data, labels, frame

    @staticmethod
    def _observed(plane: PlaneView, pieces: tuple[ResourceKey, ...]
                  ) -> tuple[np.ndarray, ResourceKey | None]:
        """The pose's observed cells in ABSOLUTE page coordinates.

        The same reconstruction ``calibration._member_cells`` makes, and
        for the same reason: pieces are per (tile, pose) and tiles are
        disjoint, so the union is duplicate-free and its order is the
        sorted piece order. The calibration id rides along because every
        piece of one pose cites the SAME window fit — the emission stages
        it once (``place_shared.emit_placement``) — so the first is the
        pose's generation-zero calibration.
        """
        rows: list[np.ndarray] = []
        calibration_id: ResourceKey | None = None
        for key in pieces:
            observation = plane.record(key)
            if not isinstance(observation, EvidenceObservation):
                continue
            if calibration_id is None:
                calibration_id = observation.calibration_id
            observed = unpack_observed_cells(
                plane.read_array(observation.observed_ref),
                (TILE_CELLS, TILE_CELLS))
            ys, xs = np.nonzero(observed)
            rows.append(np.stack((ys + observation.ty * TILE_CELLS,
                                  xs + observation.tx * TILE_CELLS),
                                 axis=1).astype(np.int64))
        if not rows:
            return np.zeros((0, 2), np.int64), calibration_id
        return np.concatenate(rows), calibration_id


# ------------------------------------------------------------- the provider

class PoseRefineProvider:
    """One descriptor per ELIGIBLE (window, pose) — the e024 gate as expansion.

    PROVIDERS RF1 as a provider: subject = the pose key, route =
    ``refine-k``, scope = the footing (pixels are read through a rung),
    premium = that footing's lane term. The certificate-frontier half of
    the census's spend identity is the worker's read-set
    (:meth:`PoseRefineWorker.read_keys`), so a new certificate re-arms
    the descriptor and an unchanged frontier is idle by the ordinary
    spend-once test.

    ELIGIBILITY IS EXPANSION (§3a): a pose whose reach is fully certified
    mints NOTHING — not a descriptor that declines, not a worker that
    refuses. That is the e024 lesson expressed where it costs least, and
    it is why this family is invisible on material that certifies
    cleanly.

    THE FAMILY IS LIVE BY DEFAULT since W3 (``revise=True``, the user's
    ruling of 2026-08-23, RULING I2). ``revise=False`` is retained as a
    dial — it mints nothing at all, so a run that binds it costs no
    descriptor, no spend and no wake — and it is what a DIAL-OFF CONTROL
    arm binds when a measurement has to attribute a change to this family
    (W2's ``measure/rf1_resume.py --no-revise``, without which Xerox's
    +163 payload attempts would have been read as RF1's).

    THE TWO RULINGS THAT GATED IT, AND HOW THEY WERE ANSWERED. H5 P4 left
    RF1 built-and-off pending two decisions nobody had made:

    * the BARRIER TRANSLATION. v1 refines against "the accumulated
      certificate frontier from PRIOR BARRIERS ONLY"
      (``certified_refine.CertificateFrontier``) — a post-barrier pass
      over a SETTLED frontier — and holo2 has no barriers by design.
      ANSWERED BY PRICE, not by a phase (RULING I2): at ``COST_REFINE`` =
      200, above every other family's dearest tier, a revision fires only
      when nothing cheaper is ready, so "after the ladder" is emergent.
      At H5 P4's 90 it fired as soon as the word bands drained, which is
      why the question looked like it needed a barrier;
    * WHETHER ONE WINDOW MAY CARRY MORE THAN ONE COMMITTED POSE.
      ANSWERED YES (RULING I3): it may, nothing is retracted, and "the
      latest committed pose for that extent wins" is a read-time
      derivation at the consumers (``tilemap.StoreIndex.live_pose``).

    WHAT THE H5 P4 MEASUREMENT SAID, kept because the record keeps
    failures: the plan expected the eligibility gate to make RF1 a no-op
    on the synthetic corpus, on the ground that those pages certify
    fully. They do — but only at the END. MID-RUN every committed pose
    has both certified tiles (labels) and uncertified ones (residue), so
    the gate is open for most of a run. With ``revise=True`` the verdicts
    wall then went 30 of 39 green and **9 moved** (durability 3, honesty
    1, seeded 3, v1-parity 2) — no wrong certificate and no moved close,
    every one of the nine the same structural collision: a corpus that
    asserted one pose per window extent. Those assertions are re-pinned
    as ONE LIVE POSE per extent, which is the ruling, not a loosening.
    """

    family = FAMILY_REFINE
    sources: tuple[str, ...] = ("pose", "tile")

    PROVIDER_ID = "refine-pose-v1"

    def __init__(self, row: FormatRowSpec, *,
                 provider_id: str = PROVIDER_ID,
                 config: PlacementConfig | None = None,
                 revise: bool = True) -> None:
        self.provider_id = provider_id
        self.spec: TileFormat = tile_format_for(row)
        self._config = config or PlacementConfig()
        self.revise = revise
        # ITS OWN label source, and always the enriched one: certified
        # cargo IS this family's label channel, so the P2 dial that makes
        # enrichment optional for CA2 has no meaning here. The instance
        # owns P2's two mint-once caches (per certificate, per frontier),
        # so a growing frontier costs one re-encode per NEW certificate
        # across every revision this provider ever mints.
        self._base: ReferenceFieldProvider = V1ReferenceField(self.spec)
        self._labels = CertifiedLabelSource(self._base)

    def expand(self, view: SolveView,
               request: ExpansionRequest) -> tuple[WorkDescriptor, ...]:
        if not self.revise:
            return ()
        plane = as_plane(view)
        out: list[WorkDescriptor] = []
        for pose_id, found in sorted(reaches(plane).items()):
            if not found.eligible:
                continue
            footing_id = FootingId(pose_id.parts[0])
            out.append(request.mint(
                FAMILY_REFINE, pose_id, ROUTE_REFINE_K,
                profile=str(footing_id),
                premium=LANE_COST_PER_RUNG * plane.footing_depth(footing_id)))
        return tuple(out)

    def worker(self, view: SolveView,
               descriptor: WorkDescriptor) -> PoseRefineWorker:
        return PoseRefineWorker(descriptor.subject, self._base, self._labels,
                                self._config)


# The family's own names, plus EVERY name ``refine_fit`` publishes — the
# re-export contract that module's docstring states, and it is
# load-bearing rather than decorative: the oracle reads all eighteen
# carried constants off THIS module by name
# (``test_oracle_refine.CARRIED_CONSTANTS``), which is what keeps the
# file-cap seam from becoming a second address.
__all__ = [
    "ANGLE_COARSE_STEP_DEG", "ANGLE_FINE_STEP_DEG", "ANGLE_LIMIT_DEG",
    "BLOCK_CELLS", "FAMILY_REFINE", "MIN_CERTIFIED_BLOCKS",
    "MIN_HELDOUT_GAIN", "MIN_PAYLOAD_TRAIN", "MIN_PAYLOAD_VALIDATION",
    "MIN_POSE_PILOTS", "MIN_TRAIN_PER_CLASS", "MIN_VALIDATION_PER_CLASS",
    "OUTCOME_ADOPTED", "OUTCOME_REFUSED_PREFIX", "PHASE_COARSE_STEP_CELLS",
    "PHASE_FINE_STEP_CELLS", "PHASE_LIMIT_CELLS", "PILOT_MISMATCH_SLACK",
    "POSE_SITE_CAP_TRAIN", "POSE_SITE_CAP_VALIDATION", "PoseRefineProvider",
    "PoseRefineWorker", "ROUTE_REFINE_K", "Reach", "RefineInput", "Revision",
    "SCORE_SPREAD_FLOOR", "SegmentLabels", "VALIDATION_MODULUS",
    "adoption_gate", "block_validation", "block_weights", "candidate_grid",
    "collect_labels", "deterministic_cap", "fine_grid", "local_segment",
    "native_terms", "pose_candidate", "pose_evidence_keys", "pose_objective",
    "propose", "reach", "reaches", "replay_calibration", "sample_at",
    "select_best", "select_pose_sites", "support_metrics", "weighted_logloss",
]
