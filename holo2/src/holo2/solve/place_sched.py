"""The placement scheduler: a monotone set, a flag each, priced tiers.

H4 W2's pull model (H4-W2-PLAN, "THE PULL MODEL — 2026-08-16 redesign,
RULED"). This is the engine's SECOND work source (``core.WorkSource``):
the descriptor path still serves payload and the close, and placement
work comes from here — an in-memory set of windows, each with a ready
bit, a tried set, a stage memory and a priority, none of it durable.

WHY IN MEMORY IS THE RIGHT PLACE (the user's argument, adopted)
---------------------------------------------------------------
**placed is MONOTONE.** A pose is identity-frozen, certificates are
terminal, and the §6 done projection only grows, so this set only ever
SHRINKS — a window leaves by being placed or by being covered, and never
comes back. A monotone set with a per-member dirty bit is exactly the
shape where weak synchronisation is provably enough: a race costs one
spurious pass, never a lost one. Everything the wall holds is a fact
(poses, evidence, certificates, the window's own outcome record);
readiness, seed lists, priorities and the tried set are DERIVED, and a
resume rebuilds the set from the store — plans minus placed minus
covered, all ready, tried empty — and re-tries at worst. Waste, never
wrongness (Q1).

THE MONOTONE-GROWTH AMENDMENT (W3 subdivision, and TERMINATION)
---------------------------------------------------------------
The set is no longer monotone-shrinking: it GROWS BY SUBDIVISION, and
only by subdivision. A window that has exhausted its ladder on one of
v1's eligible refusals (:data:`~holo2.solve.place_job.SUBDIVISION_REFUSALS`)
adds four corner windows to this set — ordinary members, named by their
extents, consulting the same committed poses, carrying their own tried
sets. Since W4 that exhaustion means what it means in v1: the COLD PAIR
refused, not the wide consult (:meth:`PlacementScheduler.settle`).
Termination stands, and it is bounded arithmetic rather than a hope:

* a window subdivides **at most once** (``Slot.subdivided``);
* a child is admitted at ``depth + 1`` and
  :data:`~holo2.solve.pose_fit.SUBDIVISION_MAX_DEPTH` is 1, so children
  never subdivide further — the growth is one generation deep;
* the kernel refuses to halve below the 70-cell floor
  (``PlacementConfig.min_window_cells``), so a small window has no
  children at all;
* every member, child or not, still leaves only by being placed or
  covered, and every member's ladder is still finite.

So the set is bounded by ``plans + 4 x plans`` in the worst case and by
"plans" in every healthy run, and the argument above — a race costs one
spurious pass — is untouched, because a child is a member like any
other from the moment it is admitted.

THE ARGUMENT STAYS HERE, THE MECHANISM DOES NOT (H4 W6's cap seam). The
three growth functions themselves live in
:mod:`holo2.solve.place_subdivide`; this paragraph is about the SET, so
it stays with the set, and that module points back at it. Everything
else in this file shrinks the set.

THE FLAG PROTOCOL, WHICH IS THE CORRECTNESS ARGUMENT
-----------------------------------------------------
Two orderings, and they are the whole of it:

* **commit, THEN ping.** :meth:`PlacementScheduler.settle` runs after the
  pose is durable, so a neighbour woken by it consults an index that
  already holds that pose.
* **test-and-CLEAR, THEN consult.** :meth:`PlacementScheduler.claim`
  clears the ready bit before the fire reads anything, so a pose that
  commits DURING the pass re-sets the bit and buys another pass.

Together they make a lost wake impossible. Take any commit C of a pose
and any pass P of a neighbour: either P's claim happened before C's ping,
in which case the ping finds the bit clear and sets it — P re-runs with C
visible — or the claim happened after the ping, in which case the claim
cleared a bit that had already been set and P's own consult reads C
directly, because C committed before it pinged. There is no third
interleaving, and neither branch depends on how long P runs.

Single ownership is the same bit read the other way: a claim clears
``ready`` and raises ``in_flight``, and :meth:`peek`/:meth:`claim` both
refuse an in-flight window, so one window has at most one owner at a
time. A ping that arrives mid-flight is not lost either — it sets the bit
under the running fire, and :meth:`settle` re-enqueues on the way out.

TIERS ARE PRICES, NOT LADDERS (Q3+Q6)
--------------------------------------
The cost table itself lives in :mod:`holo2.solve.place_tiers` — it grew
to a subject of its own at W4 — and this module is what READS it: six
priced classes with their gates and two rung terms, against a monotone
set with a flag each. The order is **payload** < ring consult < word
centre < word rest < wide consult < cold live < cold rest, and the
expensive tiers are gated behind global dryness ("if we devolve into
'let's run a cold search on everything remaining' before all payload is
decoded, we are going to burn ourselves"). The lane term
(:data:`LANE_COST_PER_RUNG`) retired the engine's ``quiescent`` gate: a
finer-footing window enters as soon as its geometry does and pays a
little more for every tier it runs, resolved ONCE at admission, so
coarse-before-fine EMERGES from one priority order instead of a barrier
arranging it.

Within a tier, ready windows order by their best AVAILABLE seed distance
and then round-robin (ruling R-A): Dijkstra-flavoured frontier growth
along the most confident edges, with an ordinal tie-break so nothing
starves. Available, not merely pinged — a window admitted beside poses
that already stand (a resume, a finer-footing entry) is offered what a
ping would have offered it, at the door (:meth:`_consider`).

COLD, IN TWO FLAVOURS PER RUNG (W4, the 2026-08-17 ruled shape)
---------------------------------------------------------------
The tier that was declared-and-unbuilt is LIVE, as two rows rather than
one: :data:`TIER_COLD_LIVE` correlates the window's patch against the
pages this session already has a committed pose on, and
:data:`TIER_COLD_REST` against the declared page domain minus those. The
two sets PARTITION the domain, are derived at fire time and stored
nowhere, and generalise the e029 scheduler observation ("--page 0 for
single-sheet volumes would collapse the 133-page cold domain") from an
operator flag into a question the session can answer itself: ask what the
producer knows.

Three properties, and each is arithmetic rather than machinery:

* **Above everything else, and ascending without interleaving.** Every
  cold price clears the wide tier at its deepest lane (140 > 128), live
  precedes rest inside a rung, and cold's own rung term is big enough
  that ``rest(d) < live(d + 1)`` — so the sheet's cheap questions are
  exhausted at every rung before the next rung's are asked. The price IS
  the policy: a coarse rung's colds failing gates, terminates and parks
  NOTHING, because failure at a rung implies nothing about finer ones.
* **Children run it too, at the premium** (the 2026-08-18 reversal —
  "we implement src/holo, algorithmically; the thing we change is
  scheduling and orchestration"). v1's children reached the cold route
  in the main pass, so holo2's do: a child's colds are 145 + 20d and
  155 + 20d, which sit INSIDE their rung's pair rather than crossing
  into the next one. The parent's own full-extent cold is unchanged and
  still arms when every child has failed — "failed" now meaning the
  children exhausted their own colds as well.
* **An empty page set is skipped costlessly and never terminally**
  (ruling 2). The offer itself asks (:meth:`Slot.tier`), so a flavour
  with nothing to sweep is not offered, nothing is marked, and the next
  offer asks again — "it might fill later", with no re-arm machinery.

Quarantine (W5) is absent by plan, not by omission.
"""
from __future__ import annotations

import heapq

from ..core import ResourceKey, SolveView, SourceJob, WorkResult
from ..format import FormatRowSpec, tile_format_for
from .geometry import WINDOW_STEP_CELLS
from .lattice_seed import KIND_LATTICE_SEED, LatticeSeedRecord
from . import place_cold
from .place_job import (NOTHING_TO_TRY, SUBDIVISION_DIRECT, WindowJob,
                        consult, hint_distance, window_centre_cells)
from .place_model import PROVISIONAL_V1_PLACEMENT_POLICY, PlacementConfig
from . import place_subdivide
from .place_shared import (READING_ALL, donor_targets,
                           pixel_work_is_attachable, reading_set_places,
                           ring_targets)
from .placement import FAMILY_PLACE, STAGE_CENTRE, STAGE_REST
from .place_slot import ColdOffer, Slot
from .place_tiers import (CHILD_PREMIUM, COLD_COST_PER_RUNG, COLD_TIERS,
                          LANE_COST_PER_RUNG, MAX_LANE_DEPTH, PLACEMENT_TIERS,
                          RESAMPLE_TIER, TIER_COLD_LIVE, TIER_COLD_REST,
                          TIER_PRICE, TIER_RESAMPLE,
                          TIER_RING, TIER_WIDE, TIER_WORD_CENTRE,
                          TIER_WORD_REST, TierPrice)
from .plans import WindowPlan
from .quarantine import is_quarantined
from .records import WindowRecord, WindowStatus
from .reference import V1ReferenceField
from .view import PlaneView, as_plane
from . import words

#: A new lineage of its own: the source replaces two providers, and the
#: id forks resumable state by design (WORKPLAN:335-338).
SOURCE_ID = "place-pull-v1"

#: WHY A WINDOW ON A LANE THIS RUN DOES NOT READ LEFT THE SET. It was
#: ``not_the_working_footing`` while the reading was a hard max over ppc
#: and every rung but one was exited; stage 2 made the reading declared
#: policy AND made the whole ladder the default, so both halves of the
#: old name are now false — there is no "working footing", and being
#: outside the set is the rare case rather than the universal one. The
#: reason names the policy that excluded it, which is the thing an
#: operator would have to change.
EXIT_OUTSIDE_READING_SET = "outside_the_reading_set"

#: THE EXIT A PLACED WINDOW LEAVES UNDER, spelled once (F2a review fix,
#: 2026-08-23) because three sites now write it: the ordinary placed
#: branch of :meth:`PlacementScheduler._consider`, the accepted-pass
#: settle, and the RE-READ settle — which restores it rather than
#: overwriting it, since the re-read door is a clause on this exit and
#: not a verdict about the rectangle. ``place_subdivide.EXIT_SERVED``
#: and ``verdicts/test_honesty.py`` both read the string, so a fourth
#: spelling is a silent census break.
EXIT_PLACED = "placed"

#: Re-exported for the surface's sake: it went to ``place_subdivide``
#: with the reader it exists for (H4 W6's growth-half seam).
EXIT_SERVED = place_subdivide.EXIT_SERVED



class PlacementScheduler:
    """Family ``place``, as a ``core.WorkSource``: the pull model's set."""

    family = FAMILY_PLACE

    def __init__(self, row: FormatRowSpec, *, source_id: str = SOURCE_ID,
                 config: PlacementConfig | None = None,
                 reading_set: str = READING_ALL) -> None:
        self.source_id = source_id
        #: WHICH RUNGS THIS RUN PLACES (H4-LANES stage 1). Composed from
        #: the recipe (``cli.real_source``), so the value rides
        #: ``SessionIdentity`` with the entries and a run under a
        #: different reading is a different lineage. It is a constructor
        #: argument rather than an ``admit`` one because it is a property
        #: of the RUN: two placement entries may not disagree about it,
        #: and ``engine.recipe.Recipe`` refuses a pair that does.
        self.reading_set = reading_set
        self.row = row
        self.spec = tile_format_for(row)
        self.config = config or PlacementConfig()
        self.reference = V1ReferenceField(self.spec)
        # The qualified per-seed search shape and the Stage-A ceiling,
        # frozen before a pixel is read (L7a). ``n_lower`` is 0 because
        # there is no separate donor route to budget — one job, one
        # currency, and a donor is an entry in the same portfolio.
        self.budgets, self.word_budget = (
            PROVISIONAL_V1_PLACEMENT_POLICY.resolve(
                row, row.page_domain, 0, self.config,
                word_hypotheses=words.stage_a_hypotheses(
                    (self.config.window_cells, self.config.window_cells))))
        self._slots: dict[ResourceKey, Slot] = {}
        #: Windows that LEFT the set. Membership is monotone, so this is
        #: also the admission filter that keeps a refresh O(plans) in
        #: dictionary lookups rather than in done projections.
        self._exited: dict[ResourceKey, str] = {}
        self._claimed: dict[ResourceKey, WindowJob] = {}
        self._heap: list[tuple[int, float, int, ResourceKey]] = []
        self._ordinal = 0
        #: The windows that SUBDIVIDED, in birth order — the down-pointing
        #: half of the parent's afterlife. A child's outcome is read
        #: through this list rather than through a parent pointer, which
        #: is what keeps "the reference only ever points down" true of the
        #: scheduler as well as of the records.
        self._parents: list[ResourceKey] = []
        #: W4's shared derivation, handed to every slot (:class:`ColdOffer`).
        self._cold_offer = ColdOffer()
        #: The memo the live-page derivation is cached on: the COMMITTED
        #: POSE COUNT, which is monotone (a pose is identity-frozen), so
        #: an equal count means an equal set. Exactly the discipline the
        #: §6 done projection caches under, for the same reason — this is
        #: asked at every door and the answer is a scan of the pose index.
        self._live_memo: tuple[int, frozenset[int]] = (-1, frozenset())
        #: WHAT THE SCHEDULER HAS ALREADY ACCOUNTED FOR, per window that
        #: LEFT the set placed: the live pose at the moment it left (F2a).
        #: It is the anti-spin half of the re-read — a window is offered
        #: a re-read once per live pose, whether that read emitted or
        #: refused, and never again for the same geometry.
        self._placed_pose: dict[ResourceKey, ResourceKey | None] = {}
        #: The committed pose COUNT at the last re-read review. A live
        #: pose can only move when a pose commits, so an equal count
        #: means an equal answer for every window — the same exactness
        #: argument :meth:`live_pages` memoises under, and what keeps
        #: the review off the ordinary refresh path entirely.
        self._reviewed: dict[str, int] = {}
        self._counts: dict[str, int] = {
            "entered": 0, "placed": 0, "retired": 0, "passes": 0,
            "pings": 0, "abandoned": 0, "subdivided": 0, "cold_parked": 0,
            "cold_armed": 0, "cold_fired": 0, "resampled": 0}

    # -- membership --------------------------------------------------------

    def admit(self, view: SolveView, *, entry: int, selector: str) -> None:
        """Enter the windows one recipe entry's footings make eligible.

        Called from the engine's ordinary refresh, beside provider
        expansion, and since the 2026-08-17 pricing ruling under NO gate
        at all: a finer-footing entry admits its windows the moment their
        geometry exists, exactly like a coarse one. Coarse-before-fine
        did not go away, it became a price — each window carries
        :data:`LANE_COST_PER_RUNG` times its RUNG DEPTH on every tier it
        will ever pay, resolved here off the plane's own ladder rather
        than from the selector that happened to reach it (so a run under
        ``FOOTING_ALL`` prices each window by the lane it is on, and a
        five-rung ladder orders five ways rather than two).

        The three permanent refusals the word provider used to make are
        made here, once per window, and remembered in ``_exited`` — a
        window on a lane this run does not read (rare since stage 2 made
        the whole ladder the default, and a declared policy rather than a
        computed one either way), a window whose verdict is already
        standing (placed or retired: the RESUME REBUILD, which is why
        nothing about readiness needs to be durable), and a done-covered
        window, which §6 says is never created, never posed and never
        woken. An unattached capture is the one refusal that is NOT
        permanent: it enters nothing and re-asks at the next refresh,
        which is what M12's decline-and-sleep did.
        """
        plane = as_plane(view)
        self._refresh_cold_offer(plane)
        poses = len(plane.index().poses)
        review = self._reviewed.get(selector) != poses
        for footing_id in plane.footing_ids(selector):
            lane_depth = plane.footing_depth(footing_id)
            for plan in plane.window_plans(footing_id):
                if plan.window_id in self._slots:
                    continue
                if plan.window_id in self._exited:
                    if not review or not self._needs_resample(
                            plane, plan.window_id):
                        continue
                    # THE ONE PLACE A WINDOW COMES BACK (F2a, RULING I3:
                    # "when a better pose comes in, the old one goes out
                    # the door and the tile/window wakes up again"). See
                    # :meth:`_needs_resample` for what bounds it.
                    del self._exited[plan.window_id]
                self._consider(plane, plan, entry, lane_depth=lane_depth)
        self._reviewed[selector] = poses

    def _consider(self, view: PlaneView, plan: WindowPlan,
                  entry: int, depth: int = 0,
                  *, lane_depth: int = 0) -> None:
        if not pixel_work_is_attachable(view, plan, config=self.config):
            return                       # M12: no verdict without pixels
        if not reading_set_places(view, plan, self.reading_set):
            # DECLARED policy, and since stage 2 the RARE branch: the
            # default reading set is the whole ladder, so this fires only
            # for a run that declared ``finest`` (or composed a scheduler
            # by hand with a reading nobody implements). The name moved
            # with the meaning — there is no working footing any more.
            self._exited[plan.window_id] = EXIT_OUTSIDE_READING_SET
            return
        if view.poses_of_window(plan.window_id):
            # THE "PLACED" EXIT IS NOW "PLACED, AND ITS LIVE POSE HAS
            # BEEN READ" (F2a, ruling J2-3). A window whose latest
            # committed geometry nothing has sampled through owes a
            # re-read: it enters the set as a re-read slot instead of
            # leaving it. The predicate is a property of the STORE, not
            # a memory, so it answers the same on a resume — which is
            # how the archived states, where 269/272 revised windows
            # carry zero evidence on the live pose, get their re-read.
            if (self._needs_resample(view, plan.window_id)
                    and not view.window_is_done(plan)):
                self._enter(view, plan, entry, lane_depth, depth,
                            resample=True)
                return
            self._exited[plan.window_id] = EXIT_PLACED
            self._placed_pose[plan.window_id] = view.index().live_pose(
                plan.window_id)
            return
        record = view.record(plan.window_id)
        if (isinstance(record, WindowRecord)
                and record.status is WindowStatus.RETIRED):
            self._exited[plan.window_id] = record.retired_reason or "retired"
            return
        if view.window_is_done(plan):
            self._exited[plan.window_id] = "done_covered"
            return
        self._enter(view, plan, entry, lane_depth, depth)

    def _enter(self, view: PlaneView, plan: WindowPlan, entry: int,
               lane_depth: int, depth: int, *,
               resample: bool = False) -> None:
        """Admit one window to the set, priced and offered.

        Split out of :meth:`_consider` at F2a so the re-read door and the
        placement door share ONE construction: the same slot, the same
        ordinal, the same enqueue, and the same R-A peek — a re-read slot
        simply carries the bit that makes :meth:`Slot.tier` answer with
        the re-read tier and nothing else.
        """
        self._ordinal += 1
        slot = Slot(plan, entry, self._ordinal, lane_depth, depth,
                     resample=resample, cold_offer=self._cold_offer)
        # R-A AT THE DOOR. A ping is not the only way a window can have a
        # seed available: a resume rebuilds the set beside poses that
        # already stand, and a finer-footing entry admits into a
        # page others have been placing. Such a window is offered exactly
        # what a ping would have offered it — the nearest committed pose it
        # can see — so it prices at the ring tier and orders by distance
        # like everyone else instead of entering at the word tier in
        # arrival order. The peek is the fire's own consult (nearest
        # first), so "best available" means the same thing in both places.
        # ...but NOT for a re-read: its address is committed, so a seed
        # is not an offer to it and ``tier`` would ignore one anyway.
        # Skipping the peek also skips the consult it costs.
        if not resample:
            seeds = consult(view, plan, self.row)
            if seeds:
                slot.offered = seeds[0].distance
        self._slots[plan.window_id] = slot
        self._counts["entered"] += 1
        self._enqueue(slot)

    # -- the re-read (F2a) -------------------------------------------------

    def _needs_resample(self, view: PlaneView,
                        window_id: ResourceKey) -> bool:
        """Does this window's LIVE pose owe a re-read? (Ruling J2-3.)

        Four clauses, and the last one is the whole anti-spin story:

        * its live pose owns NO EVIDENCE, and some OTHER pose of the same
          extent DOES — which is exactly and only what an adopted
          revision looks like before anything has sampled through it.
          Both halves matter: the first says the live geometry is unread,
          the second says there is a generation to replace, and a fire
          without one would refuse ``nothing_superseded`` after paying
          for a pass. Eligibility is expansion (§3a), so the fire's own
          precondition is asked at the door. Both are O(1) membership
          tests on the index (``evidence_by_pose``, ``poses_by_window``);
        * its live pose is not CONDEMNED, AND NEITHER IS THE GENERATION
          IT WOULD REPLACE — W5's never-return, asked here as it is
          asked at the consult, the payload read-set and the calibration
          pool. The second half is the F2a review fix (2026-08-23):
          ``quarantine._geometry_side`` reaches poses only THROUGH their
          pieces, so a revision committed before a contradiction owns no
          piece, is never condemned, and stands as the extent's live
          pose while its parent and every one of the parent's pieces
          are marked. Without this clause that window opens the door,
          the fire reads the condemned cells back and emits FRESH,
          unquarantined pieces at the live pose — a certificate minted
          from material W5 condemned as mis-addressed, which is exactly
          what W5 exists to prevent. ``quarantine``'s law is
          one-way: *"never rehabilitated … recovery is fresh-evidence-
          only (L8)"*. Unobserved on either sheet (L8 records 1,780
          known-position reads and 0 conflicts), so this is the
          invariant being kept, not a measured loss;
        * the scheduler has not already ANSWERED for this geometry
          (:attr:`_placed_pose`). A re-read retires whether it emitted or
          refused, so without this clause a refusal — a window whose
          re-sampled calibration will not fit, say — would be re-offered
          on every review forever.

        TERMINATION, stated because a set that grows needs one. A window
        re-enters at most once per LIVE POSE PER SESSION; a live pose
        moves only when RF1 commits a revision; RF1 commits at most one
        revision per extent (``refine.Reach.revised``, the same package)
        and none at all where the affine is unmoved (the I4 no-op
        guard). So the re-entries a run can make are bounded by the
        number of extents, and the monotone argument this module's
        header makes — a race costs one spurious pass, never a lost one
        — is untouched.

        PER SESSION IS EXACT, and the review made it explicit rather
        than leaving the paragraph claiming a durability it does not
        have (2026-08-23). :attr:`_placed_pose` is in-memory, and a
        re-read that REFUSED emits nothing, so on the next RESUME the
        live pose still owns no evidence and the window is offered one
        more re-read. That is one extra pass per refusing window per
        resume — waste, never a spin, and the same class as this
        module's own "a race costs one spurious pass, never a lost
        one". A re-read that EMITTED is durable: its pieces put the live
        pose in ``evidence_by_pose``, so the first clause closes the
        door for good. Making a refusal durable means reading a
        ``resample_refused_*`` exit off the window record the way
        :meth:`_consider` reads ``WindowStatus``; the census on both
        real sheets is 239/239 and 255/255 ``resampled`` with no
        refusals, so nothing is paying for it today.
        """
        index = view.index()
        live = index.live_pose(window_id)
        if live is None or live in index.evidence_by_pose:
            return False
        pose = index.poses.get(live)
        if pose is None or is_quarantined(pose):
            return False
        if not any(pose_id in index.evidence_by_pose
                   and not is_quarantined(index.poses.get(pose_id))
                   for pose_id in index.poses_by_window.get(window_id, ())):
            return False
        return self._placed_pose.get(window_id) != live

    # -- the cold offer (W4) -----------------------------------------------

    def live_pages(self, view: PlaneView) -> frozenset[int]:
        """:func:`place_cold.live_pages`, memoised on the POSE COUNT.

        The derivation itself belongs to the cold module (the fire uses
        the same one); what belongs here is that this scheduler asks it at
        every door and the answer is a scan of the whole pose index. The
        memo is exact because the index is monotone — more poses is the
        only way this answer can move, so equal counts cannot hide a
        different set. It is the same discipline the §6 done projection
        caches under, for the same reason.
        """
        poses = view.index().poses
        if self._live_memo[0] != len(poses):
            self._live_memo = (len(poses), place_cold.live_pages(view))
        return self._live_memo[1]

    def _refresh_cold_offer(self, view: PlaneView) -> None:
        """Re-derive which cold flavours have anything to sweep (ruling 2).

        Called at every door the scheduler holds a view — admission,
        claim, settle — so a flavour skipped for an empty set is re-offered
        the moment the set fills, with nothing remembered in between.

        WHEN THE ANSWER MOVES, THE ARMED SLOTS ARE RE-ENQUEUED. A slot's
        heap entry is validated against its CURRENT ``sort_key`` and
        dropped on a mismatch (:meth:`peek`), which is safe only because
        every path that leaves a window ready re-enqueues it — and a
        flavour appearing or vanishing changes exactly that key. The sweep
        is O(slots), and it is provably rare: live only grows, so this
        tuple changes at most twice in a run.
        """
        live = self.live_pages(view)
        flavors = tuple(
            flavor for flavor in COLD_TIERS
            if place_cold.cold_pages(self.row, flavor, live))
        if flavors == self._cold_offer.flavors:
            return
        self._cold_offer.flavors = flavors
        for slot in self._slots.values():
            if slot.cold_armed and slot.ready and not slot.in_flight:
                self._enqueue(slot)

    def _arm_cold(self, slot: Slot) -> bool:
        """THE LADDER'S LAST ESCALATION: this window may now correlate.

        Returns whether this call ARMED the window, which is what
        :meth:`settle` reads to decide the alternative: a dormant window
        that cannot correlate — because it never fitted a pose, or
        because it has already spent both flavours — is a window whose
        ladder is over, and that is where subdivision goes.

        Called from the two places a window's ladder genuinely runs out —
        a dormant pass, and a parent whose children have all failed
        (:meth:`_review_parents`, the ruled afterlife). Both are "nothing
        cheaper will ever answer for this rectangle", which is the bar the
        ruling puts cold behind.

        EVERY WINDOW ARMS, CHILDREN INCLUDED (the 2026-08-18 reversal:
        "children get the cold treatment as well — we implement src/holo
        algorithmically, the thing we change is scheduling and
        orchestration"). v1 ran its children through the cold route in
        the main pass, so a child that exhausts its ladder here reaches
        the same tier its v1 counterpart did, at its rung's price plus
        the child premium. The parent's own full-extent cold is
        unaffected and still arms from :meth:`_review_parents` — "all
        children failed" simply now means they exhausted their colds too.

        A WINDOW WHOSE OWN FIT REFUSED DOES NOT ARM, and that bar is
        ``wide_spent`` rather than a bookkeeping nicety. Such a window is
        dormant with its word tiers still unspent, so "its ladder ran
        out" is true only in substance — but the substance is what
        matters here, and it cuts the other way too: EVERY tier opens
        with the same ``sample_window`` call, cold included, so a window
        that could not be sampled has no patch to correlate and arming it
        would buy a fire that refuses at exactly the same line. It stays
        dormant until a better lattice seed re-arms it, which is the one
        thing that can change that answer.
        """
        if slot.cold_armed or not slot.wide_spent:
            return False
        slot.cold_armed = True
        self._counts["cold_armed"] += 1
        self._wake(slot)
        return True

    # -- the queue ---------------------------------------------------------

    def peek(self) -> SourceJob | None:
        """The cheapest ready job, tombstones dropped, nothing consumed.

        Lazy deletion: a slot's key moves when a better ping arrives and
        dies when it is claimed, so the head is validated against the
        slot's CURRENT key and a mismatch is dropped. Dropping is safe
        because every path that leaves a window ready re-enqueues it
        (:meth:`settle`, :meth:`_wake`).
        """
        while self._heap:
            entry = self._heap[0]
            slot = self._slots.get(entry[3])
            if (slot is None or not slot.ready or slot.in_flight
                    or slot.sort_key() != entry[:3]):
                heapq.heappop(self._heap)
                continue
            return self.job(slot.window_id)
        return None

    def job(self, subject: ResourceKey) -> SourceJob | None:
        """What one NAMED window offers right now, consuming nothing.

        :meth:`peek` is this over the heap's head; replay calls it with
        the window a recorded start marker names, because the ready order
        at that instant was the live schedule's and the record already
        says which window won it (H4 W2, the marker ruling). The tier is
        the slot's own, so the price and the gate are identical whichever
        door the job came through.
        """
        slot = self._slots.get(subject)
        if slot is None or not slot.ready or slot.in_flight:
            return None
        tier = slot.tier()
        if tier is None:
            return None                      # dormant: nothing on offer
        return SourceJob(cost=slot.price(tier), entry=slot.entry,
                         subject=subject, gated=TIER_PRICE[tier].gated)

    def claim(self, view: SolveView, subject: ResourceKey) -> WindowJob | None:
        """TEST-AND-CLEAR, then bind — the flag protocol's second half.

        The clear happens HERE, before the job exists and long before it
        consults anything, so a pose committed from this moment on wakes
        this window again instead of racing its read. ``in_flight`` is the
        single-ownership half: a ping may set the bit under a running
        fire, but nothing may claim the window twice.
        """
        slot = self._slots.get(subject)
        if slot is None or not slot.ready or slot.in_flight:
            return None
        self._refresh_cold_offer(as_plane(view))
        tier = slot.tier()
        if tier is None:
            slot.ready = False
            return None
        slot.ready = False
        slot.in_flight = True
        slot.offered = None
        cold = tier if tier in COLD_TIERS else None
        job = self._job_for(slot, tier, cold)
        self._claimed[subject] = job
        self._counts["passes"] += 1
        if cold is not None:
            self._counts["cold_fired"] += 1
        return job

    def _job_for(self, slot: Slot, tier: str,
                 cold: str | None) -> WindowJob:
        """Bind one claimed slot's worker, and declare what it will hold.

        THE LEASE IS DECLARED HERE, not in the fire (M5): the engine takes
        a worker's leases when it ARMS the job and releases them when it
        disarms, so residency has to be knowable before the fire runs. The
        weight is this flavour's page set at claim time — which is an
        upper bound on what the fire actually sweeps, because the fire
        subtracts the window's own tried pages from it. Conservative in
        the direction an admission gate would need.
        """
        job = WindowJob(
            slot.plan, self.spec, self.row,
            wide=(tier == TIER_WIDE), cold=cold,
            resample=(tier == TIER_RESAMPLE),
            stage=None if tier in (TIER_WIDE, TIER_RESAMPLE, *COLD_TIERS)
            else slot.stage,
            tried=frozenset(slot.tried), words_spent=slot.words_spent,
            config=self.config, budget=self.budgets.local,
            cold_budget=self.budgets.cold,
            word_budget=self.word_budget, reference=self.reference)
        if cold is not None:
            pages = place_cold.cold_pages(
                self.row, cold, self._live_memo[1])
            extent = slot.plan.extent_cells
            job.leases = (place_cold.cold_lease(
                place_cold.cold_transform_key(
                    self.reference, pages,
                    (extent[2] - extent[0], extent[3] - extent[1])),
                len(pages)),)
        return job

    # -- the wall's other side ---------------------------------------------

    def settle(self, view: SolveView, subject: ResourceKey,
               result: WorkResult | None) -> None:
        """The pass landed (or was abandoned): fold it in, then PING.

        Called after the commit, which is the ordering the whole
        correctness argument rests on. What it folds in is the pass's own
        record of what it consumed — the candidates it tried and the word
        stage it spent — because that is the honest count and the job is
        the only thing that knows it.

        ``result is None`` is the abandoned fire (a cancelled pool slot, a
        replay proposal dropped past the recorded tail): nothing was
        learned and nothing is charged, so the window simply becomes
        claimable again.
        """
        job = self._claimed.pop(subject, None)
        slot = self._slots.get(subject)
        if job is None or slot is None:
            return
        slot.in_flight = False
        if result is None:
            self._counts["abandoned"] += 1
            self._wake(slot)
            self._review_parents()
            return
        plane = as_plane(view)
        self._refresh_cold_offer(plane)
        slot.tried.update(job.tried_now)
        if job.stage_spent == STAGE_CENTRE:
            slot.centre_spent = True
        elif job.stage_spent == STAGE_REST:
            slot.rest_spent = True
        slot.wide_spent = slot.wide_spent or job.wide_spent
        # A COLD FLAVOUR THAT FIRED IS SPENT, exactly like every other
        # tier, and that is what bounds the pair: a window runs live once
        # and rest once and is then done with correlation. It does NOT
        # contradict ruling 2 — what that ruling protects is the flavour
        # that was never offered because its page set was empty, and such
        # a flavour never reaches this line at all.
        if job.cold_spent == TIER_COLD_LIVE:
            slot.cold_live_spent = True
        elif job.cold_spent == TIER_COLD_REST:
            slot.cold_rest_spent = True
        # R5 rides the WRITES, not the outcome, so the seed wake is asked
        # on EVERY path that can carry one — before the two that leave the
        # set. An accepted pass is the likeliest superseder there is (its
        # fit measured the support the seed is ranked by), and its ring
        # ping reaches only the ring: a dormant window a gap away from it
        # would otherwise never learn that the seed under it moved.
        self._seed_ping(plane, result)
        if slot.resample:
            # A re-read answers for ONE (window, live pose) and leaves,
            # emitted or refused (``resample.OUTCOME_*`` all retire). The
            # geometry it answered for is recorded so the review does not
            # offer it again; a LATER revision moves the live pose and
            # re-admits the window on its own merits.
            #
            # IT LEAVES UNDER THE EXIT IT ALREADY HELD (F2a review fix,
            # 2026-08-23). The re-read door is a CLAUSE ON the placed
            # exit (:meth:`_consider`: the branch it displaced writes
            # exactly ``"placed"``), so the window's answer about its
            # rectangle is unchanged by having been re-read — and the
            # exit reason is read as that answer elsewhere:
            # ``place_subdivide.child_verdict`` asks whether the reason
            # is in ``EXIT_SERVED``, so writing ``"resampled"`` here
            # flipped a corner child that HAD placed to "failed", and
            # four such children cold-park and arm a parent whose whole
            # area was served. The exit census reads it the same way
            # (``verdicts/test_honesty.py``: every exit is an admission
            # verdict or a stood-down reason). The fire's own outcome is
            # not lost — it is the attempt's outcome in the spend row,
            # and the count below is its census.
            self._placed_pose[subject] = plane.index().live_pose(subject)
            self._exit(subject, EXIT_PLACED)
            self._counts["resampled"] += 1
            # NO PING, and that is not an omission. A ping is one accepted
            # POSE offering itself to the windows it can steer; a re-read
            # commits no pose — the geometry it read was committed (and
            # pinged) when the window was placed, and revised by a family
            # that pings nobody. MEASURED: pinging here woke the
            # subdivision arm's dormant parent for three passes that
            # offered it a seed it had already tried
            # (``consult_refused``, then two ``nothing_to_try``), which
            # is exactly the "waste, never wrongness" a ping with nothing
            # to offer buys.
            self._review_parents()
            return
        if result.outcome == "accepted":
            self._placed_pose[subject] = plane.index().live_pose(subject)
            self._exit(subject, EXIT_PLACED)
            self._counts["placed"] += 1
            self._ping(plane, slot.plan)
            self._review_parents()
            return
        if result.retire:
            self._exit(subject, result.outcome)
            self._counts["retired"] += 1
            self._review_parents()
            return
        advanced = (bool(job.tried_now) or job.stage_spent is not None
                    or job.wide_spent or job.cold_spent is not None
                    or result.outcome == NOTHING_TO_TRY)
        if advanced or slot.ready:
            # A pass that learned something climbs to its next tier; one
            # that learned nothing (its own fit refused, so no hypothesis
            # was tested) goes DORMANT rather than re-arming, or the
            # window would spin on the same refusal. ``slot.ready`` is the
            # ping that arrived mid-flight: it is re-enqueued here, which
            # is where a lost wake would otherwise live.
            #
            # NOTHING TO TRY is the third case and it re-queues too: the
            # claim spent the PING (a ping whose seeds this window had all
            # tried), not a tier, so the slot still owns an unspent tier
            # while its heap entry is a tombstone. Re-arming cannot spin —
            # the tier it falls to is the once-only wide pass, which
            # charges itself and then goes dormant through ``_enqueue``.
            self._wake(slot)
        if not slot.ready:
            # DORMANT: every cheaper way to place this rectangle WHOLE has
            # failed. WHAT HAPPENS NEXT IS v1'S OWN ORDER, RESTORED AT W4
            # (the 2026-08-18 ruling — "we implement src/holo,
            # algorithmically; the thing we change is scheduling and
            # orchestration"). v1 has three subdivision call sites and
            # two of them fire STRAIGHT OFF the refusal — a window whose
            # pose never fitted (:1244) and one whose straddle audit
            # refused an address it had already accepted (:1173) — while
            # the third is behind the correlation (``run_cold`` ->
            # ``refuse_unplaced``, :1495 -> :1126). So: those two quarter
            # the window now, and every other exhausted window escalates
            # to its OWN cold pair first and quarters on cold's refusal.
            #
            # W3 wired the trigger here, at the wide refusal, because cold
            # did not exist yet; that spelling is gone (the three ladder
            # refusals left ``place_job.SUBDIVISION_REFUSALS`` with it).
            #
            # ``_arm_cold`` carries the rest of the bar and reports it: a
            # window that cannot be sampled has no patch to correlate, and
            # one that has spent both flavours has no correlation left —
            # both fall through to the same line, which is exactly what
            # "cold refused, now quarter it" means.
            if (result.outcome in SUBDIVISION_DIRECT
                    or not self._arm_cold(slot)):
                self._subdivide(plane, slot, result.outcome)
        self._review_parents()

    def counters(self) -> dict[str, int]:
        """What the observer reads (L12): derived, never state."""
        return dict(self._counts, windows=len(self._slots),
                    ready=sum(1 for slot in self._slots.values()
                              if slot.ready and not slot.in_flight),
                    in_flight=sum(1 for slot in self._slots.values()
                                  if slot.in_flight))

    # -- the pings ---------------------------------------------------------

    def _ping(self, view: PlaneView, plan: WindowPlan) -> None:
        """One accepted pose offers itself to the windows it can steer.

        The ring at its own footing plus the finer-footing windows its
        extent covers (``place_shared``'s geometry, in the pushing voice),
        and only windows still IN the set: a window that left has nothing
        to be woken for. The offered distance is the ratified score, which
        is what makes a colocated donor outrank a stride-distant
        neighbour without a class prefix to say so (R-A).
        """
        here = window_centre_cells(plan.extent_cells)
        stride = float(WINDOW_STEP_CELLS)
        for target in (*ring_targets(view, plan), *donor_targets(view, plan)):
            slot = self._slots.get(target.window_id)
            if slot is None:
                continue
            self._counts["pings"] += 1
            self._wake(slot, hint_distance(
                here, window_centre_cells(target.extent_cells), stride))

    def _seed_ping(self, view: PlaneView, result: WorkResult) -> None:
        """R5, kept alive without a subscription: a better lattice seed.

        A window whose own fit refused tested no hypothesis and went
        dormant; the one thing that can change that answer is the
        per-(footing, region) lattice seed improving under it, which used
        to reach it as a version bump on a key in its read-set. With no
        read-sets on this path, the writer's own commit is what carries
        it: a pass that superseded the seed wakes the region's windows,
        which is the same order-independence in the same one place.
        """
        seeds = [write.record for write in result.writes
                 if write.key.kind == KIND_LATTICE_SEED
                 and isinstance(write.record, LatticeSeedRecord)]
        for record in seeds:
            for slot in self._slots.values():
                if (slot.plan.footing_id == record.footing_id
                        and slot.plan.region_id == record.region_id
                        and not slot.ready):
                    self._wake(slot)

    # -- subdivision, and the parent's afterlife (W3/PL5) -------------------
    # The bodies live in ``solve/place_subdivide.py`` (the file-cap seam,
    # taken where the tree already cuts): everything else here SHRINKS the
    # set, and growth is a subsystem of its own with a vocabulary — corner
    # children, parents, a corner's verdict, the afterlife of a window
    # whose corners did no better than it did — that the flag protocol,
    # the tiers and the heap never read. The three entry points stay as
    # methods so the call sites above, and their pins, are unchanged.
    # ``Slot`` deliberately did NOT move with them: it is what the heap,
    # the ladder and the price are written over.

    def _subdivide(self, view: PlaneView, slot: Slot, outcome: str) -> None:
        """The ladder's last escalation: four corner windows, no spend."""
        place_subdivide.subdivide(self, view, slot, outcome)

    def _review_parents(self) -> None:
        """What a child's exit means to the window that computed it."""
        place_subdivide.review_parents(self)

    def _child_verdict(self, child_id: ResourceKey) -> bool | None:
        """Did this child SERVE its area — ``None`` while it is still trying."""
        return place_subdivide.child_verdict(self, child_id)

    # -- interior ----------------------------------------------------------

    def _wake(self, slot: Slot, distance: float | None = None) -> None:
        """Set the flag (raising the priority if a seed came with it)."""
        if distance is not None:
            slot.offered = (distance if slot.offered is None
                            else min(slot.offered, distance))
        if not slot.ready:
            slot.ready = True
            self._ordinal += 1
            slot.ordinal = self._ordinal      # round-robin: to the back
        if not slot.in_flight:
            self._enqueue(slot)

    def _enqueue(self, slot: Slot) -> None:
        if slot.tier() is None:
            slot.ready = False                # dormant: nothing left to try
            return
        cost, distance, ordinal = slot.sort_key()
        heapq.heappush(self._heap, (cost, distance, ordinal, slot.window_id))

    def _exit(self, subject: ResourceKey, reason: str) -> None:
        """Out of the set for good — the monotone half of the model."""
        self._slots.pop(subject, None)
        self._exited[subject] = reason


__all__ = [
    "CHILD_PREMIUM", "COLD_COST_PER_RUNG", "COLD_TIERS",
    "EXIT_OUTSIDE_READING_SET", "EXIT_PLACED", "EXIT_SERVED",
    "LANE_COST_PER_RUNG",
    "MAX_LANE_DEPTH", "PLACEMENT_TIERS", "PlacementScheduler",
    "RESAMPLE_TIER", "SOURCE_ID", "TIER_COLD_LIVE", "TIER_COLD_REST",
    "TIER_PRICE", "TIER_RESAMPLE", "TIER_RING", "TIER_WIDE",
    "TIER_WORD_CENTRE", "TIER_WORD_REST", "TierPrice",
]
