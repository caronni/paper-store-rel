"""The recipe: orchestration policy as typed data (DESIGN §9).

An ordered list of typed constants — no DSL, no config file, no runtime
construction from strings. The recipe's ENTRIES land in
``SessionIdentity`` as data (the hash-free identity law, 2026-08-11), so
a policy change forks the lineage by VALUE instead of relying on a
hand-bumped label somebody has to remember to move; ``label`` is display
and binds nothing. A recipe declares exactly one close consult: it
carries that entry's gate, while the consult's *timing* is the
orchestrator's (``engine/DESIGN.md``). That entry names no provider
family — since worklist B12 the close is the engine's terminal consumer,
handed in by the composition root — so it is policy data only.

Recipe v1 encodes the measured priors of §9: STREAMING INGEST first (H4,
2026-08-17 — a declared scan becomes capture facts as ordinary work, priced
below everything because it is what creates everything), then the cheapest
PAYLOAD recovery (measured 2026-08-17: behind placement it starved on a
large domain and both feedback loops stalled — see ``COST_PAYLOAD``), then
placement, coarse before finer, with the two dear placement tiers gated
behind global dryness, and a close consult that preempts everything.

WHAT THE COARSE LANES ACTUALLY MINT (corrected 2026-08-17, H4-LANES)
--------------------------------------------------------------------
This docstring used to say "the coarse lanes mint ~95% of certificates".
That number is a SYNTHETIC ARTIFACT and is withdrawn: its sole source is
a 2026-07-31 non-closing A/B (575 of 604 tiles at 41.3% payload
coverage), which is not a decode and not a sheet. The measured record on
REAL captures is a wide range, and its low end is the interesting half:

* **27.0%** — hp ``c3-cmy8`` (docs/COLOR-UPLIFT-MEASUREMENTS §9.8);
* **46–54%** — xerox ``c3-cmy7`` (same, §13.5);
* **55.4%** — e029's K sheet, where the coarse lane ALONE could not close
  the volume: 1,075 certificates against K = 1,356, so the second lane
  was load-bearing rather than a mop-up (experiments/029-holo-v1-first-
  print.md);
* **89–92%** — the e023c HP sheets (experiments/023c, RESULTS).

So coarse-first is a COST argument (a coarse pass is cheap, and its
certificates delete finer work through the §6 done projection), never a
yield prediction. The lanes are extra decoding trajectories in both
directions — cross-lane certificate exclusivity is bidirectional on every
measured pair — which is why stage 2's default reading set is the whole
ladder and not the finest rung.

FOOTING PROGRESSION IS PRICING, NOT GATING (user ruling, 2026-08-17).
What changed at that ruling was the MECHANISM. A finer-footing window
used to wait for a ``quiescent`` gate that refused to enumerate it while
anything cheaper was in play; it now enumerates as soon as its geometry
exists, exactly like a coarse one, and its passes carry a LANE TERM —
``2`` per rung from the coarsest, declared beside the tier table in
``solve.place_sched`` — which is strictly smaller than the gap between
adjacent tiers, so it reorders within a rung and never across one. Cost
competes globally, so "exhaust the sheet before specializing" is a
property of the one order rather than a rule some entry is exempted from.
The gate it replaces was assistant machinery from recipe v0 whose
justification (hints follow enumeration order) died with the pull model:
hints are gone, and a consult reads committed poses whatever order it
fires in.

**Since H4 W2 the entries also carry PRICES**, and the ``place`` entries
carry nothing else that matters: placement work no longer arrives as
descriptors at all (``solve.place_sched``, the pull model), so those two
entries say WHICH footings may enter the scheduling set, while the
ordering of the work itself is the source's per-tier cost plus that
premium. That is why both spellings of the scale live in this module.
"""
from __future__ import annotations

from dataclasses import dataclass

# Task classes (§9). Six are live since H5 P4 brought RF1's refinement
# family up (P1 brought calibration); the rest of §9's list arrives with
# its family.
TASK_INGEST = "ingest"
TASK_PLACE = "place"
TASK_PAYLOAD = "payload"
TASK_CALIBRATION = "calibration"
TASK_REFINE = "refine"
TASK_CLOSE = "close_consult"

# Footing selectors (§9 ``footing_selector``), resolved by the plane
# (``solve.SessionPlane.footing_ids``); the engine only names them.
FOOTING_COARSEST = "coarsest"
FOOTING_FINER = "finer"
FOOTING_ALL = "all"

# THE READING SET (H4-LANES stage 1, 2026-08-17): which of a capture's
# footings actually PLACE. It is a different question from the footing
# SELECTOR above — that one says which footings a recipe entry offers the
# scheduler, this one says which of them are read at all — and until this
# wave it was not a question anybody could answer as policy: the
# scheduler carried a hard "the finest rung and nothing else" and exited
# every other footing's windows permanently
# (``place_shared.working_footing_id``, tolerated at H3bis and never
# ratified). It is DATA on the entry now, which is what makes it forkable
# by value: the entries land in ``SessionIdentity``, so a run that starts
# reading two rungs is a different lineage from one that read one, and
# the store says so at open instead of reinterpreting the state.
#
# ``finest`` is v1's own reading of the measured target (~8 px/dot,
# CLAUDE.md channel facts / e016.2 / e012.3) against a ladder that never
# upsamples: "as close to 8 px/dot as the capture allows" always resolves
# to the finest rung. ``all`` is the cascade — coarse lanes are extra
# decoding trajectories, not merely cheap first passes (H4-LANES's
# measured corrections) — and SINCE STAGE 2 IT IS THE DEFAULT, which is
# the wave. ``finest`` did not become unsayable, it became a thing a run
# has to SAY: the narrow policy is the one that needs declaring, and a
# lineage built under it says so in its own identity.
READING_FINEST = "finest"
READING_ALL = "all"

# The entry gate, for queue-scheduled work only: ``always`` enumerates on
# every refresh, and since the 2026-08-17 ruling it is the WHOLE work
# vocabulary. The ``quiescent`` gate that used to hold footing progression
# closed is deleted, not deprecated — progression is priced (module
# docstring), and a vocabulary of one is what says so at the type level.
GATE_ALWAYS = "always"

# The close entry's gate says whether the orchestrator may consult mid-run:
# ``count_ready`` does, and is what every recipe declares. ``exhaustion``
# is NOT an entry gate — no recipe declares it, and its live job is to
# name the one final consult ``--complete`` defers to (the gate the
# orchestrator consults its terminal consumer under, B12).
GATE_COUNT_READY = "count_ready"
GATE_EXHAUSTION = "exhaustion"

# The vocabularies a recipe may name. Unvalidated, an unknown gate degrades
# silently to "always" and an unknown footing selector resolves to no
# footings at all, forever and without a word.
_WORK_GATES = frozenset({GATE_ALWAYS})
_CLOSE_GATES = frozenset({GATE_COUNT_READY, GATE_EXHAUSTION})
_FOOTING_SELECTORS = frozenset({FOOTING_ALL, FOOTING_COARSEST, FOOTING_FINER})
_READING_SETS = frozenset({READING_FINEST, READING_ALL})


# ---------------------------------------------------------- the cost scale
#
# ONE ORDER ACROSS EVERY SOURCE (H4 W2, rulings Q3+Q6). Tiers are not
# per-window ladders climbing alone: a class opens when everything cheaper
# is globally dry, and "cheaper" includes pending payload, because a
# certificate creates a done-exit that DELETES placement work outright.
# The user's words: "if we devolve into 'let's run a cold search on
# everything remaining' before all payload is decoded, we are going to
# burn ourselves." AMENDED 2026-08-17: payload does not merely gate the
# DEAR tiers, it undercuts every placement rung (see ``COST_PAYLOAD``).
#
# The placement half of this scale is declared again on solve's side
# (``solve.place_sched.PLACEMENT_TIERS``, with each row's provenance)
# because neither package may import the other, and a data test pins the
# two spellings equal (``tests/engine/test_cost_vocabulary.py``, which
# pins the payload interleave below with them) — the same wall-crossing
# discipline the close consult's three modes use. PROVISIONAL, like every
# other scheduling number here: these are ORDERS, ratified by the ruling,
# and the wave's measurement battery runs at its end.
#
# RE-SPACED ONCE, WITH THE LANES (H4-LANES stage 2, the plan's normative
# table). The old scale (5/8/10/20/30/50/60 with a flat premium of 1) had
# no room between payload and the ring tier for a LANE-priced payload
# attempt, and the lane term has to fit inside every gap without ever
# reaching across one. Everything is multiplied by four and the premium
# becomes ``2`` per rung, which buys a five-rung ladder (c3 at 4800:
# 2/4/8/12/24) a maximum lane term of 8 and still leaves the smallest
# inter-tier gap, 20, more than twice that — with room reserved for W3's
# child premium on top (``solve.place_sched.CHILD_PREMIUM``, LIVE since
# W3 subdivision, stacked onto the lane term at admission). ONE
# re-spacing, one lineage fork, landing with the lanes so the fork
# carries its reason.
#: INGEST IS THE CHEAPEST THING THERE IS (H4 streaming ingestion).
#: It is admitted ahead of placement because it is the work that CREATES
#: all other work: no capture, no regions; no regions, no windows; no
#: windows, nothing to place, decode or close. Pricing it below the ring
#: tier is what makes a pooled run overlap the next survey with placement
#: on the capture that just landed, and its RAM transient needs no gate
#: to stay bounded — the provider's derivation chain admits scan N+1 only
#: once scan N's record stands, so one survey is in flight at a time
#: whatever the pool width (``solve.ingest``).
COST_INGEST = 10
#: CALIBRATION SITS BETWEEN INGEST AND PAYLOAD (H5 P1, the plan's own
#: number). A region's ctx fit is what turns the payload family's
#: marginal LLRs into calibrated ones AT ASSEMBLY, so it must run before
#: the tiles it improves are decoded: at 15 it undercuts payload's base
#: (20) on every lane, and a region's tiles decode CALIBRATED the first
#: time instead of marginal-then-re-arm. A premature fit refuses cheaply
#: on the carried pool floors (``detect``: 80 search / 20 per class /
#: 40 validation / 10 per class). REFITS are re-work by construction:
#: the fit descriptor spends at the wall exactly as payload's do, so the
#: ``work_price`` ordinal lifts every re-fit into the re-work band (90+)
#: and a region refit follows a BATCH of new labels, never each label —
#: nothing here special-cases aging.
COST_CALIBRATION = 15
#: PAYLOAD IS THE CHEAPEST RECOVERY (user ruling, AMENDED 2026-08-17). It
#: sat at 40 — above every ordinary placement rung — from H4 W2 until a
#: real nine-platen run showed what that costs on a LARGE domain: 2,529
#: ready workers, 1,287 of them armed payload, and after 431 fires ZERO
#: tiles attempted and zero certified, because placement work on a sheet
#: that size never dries. Both feedback loops are dormant in that state —
#: no certificate means no close preemption, and no certificate means no
#: done pixels, so coverage stays 0.0% and not one placement window ever
#: exits. So the order is INGEST, then the cheapest payload recovery,
#: then placement (coarse, then finer at its premium), with wide and cold
#: gated behind global dryness. ONE constant, deliberately: more payload
#: types are coming and each will declare its own price beside this one,
#: but none exists today and a scale with a single member does not need a
#: table. The Q3+Q6 ruling it refines is UNCHANGED in substance — a
#: certificate deletes placement work outright, which is exactly why the
#: work that mints certificates should not queue behind it.
#:
#: IT CARRIES THE LANE TERM TOO since H4-LANES stage 2: an attempt on a
#: footing at depth ``d`` costs ``20 + 2*d``, so the cheapest evidence a
#: coarse lane produced is decoded before a finer lane's — and the whole
#: family still undercuts every placement rung at the deepest realistic
#: ladder (``20 + 2*4 == 28 < 40``). The per-descriptor half of that is
#: ``WorkDescriptor.premium``; this constant is its base.
COST_PAYLOAD = 20
COST_PLACE_RING = 40
COST_PLACE_WORD_CENTRE = 60
COST_PLACE_WORD_REST = 80
COST_PLACE_WIDE = 120
#: COLD, IN TWO FLAVOURS PER RUNG (H4-W4, the 2026-08-17 ruled shape).
#: ``live`` correlates against the pages this session already has a
#: committed pose on; ``rest`` against the declared page domain minus
#: those. Live is the cheaper of the pair by 10 because its sweep is
#: over the pages the session has already proved are on the platen,
#: while rest is the full-sweep flavour and pays for it.
COST_PLACE_COLD_LIVE = 140
COST_PLACE_COLD_REST = 150

#: COLD'S OWN RUNG TERM, and it is NOT the lane term (H4-W4). Every
#: other tier adds ``2`` per rung: a seeded search is 49 hypotheses
#: whatever the lane, so the term is a tie-break that orders coarse
#: before fine WITHIN a tier. Cold's cost is an FFT over the page's
#: cell lattice plus a per-page inverse transform, and a finer rung
#: buys a strictly worse deal for the same transform — so the rung is a
#: real price here rather than a tie-break, and the pair's own 10-point
#: gap has to sit INSIDE one rung step. 20 per rung is what makes
#: ``rest(d) < live(d+1)``: the pairs ascend and never interleave, so
#: the sheet's cheap questions are exhausted at every rung before the
#: next rung's are asked.
COLD_COST_PER_RUNG = 20

#: What a placement ENTRY declares. Placement work is priced per TIER by
#: the source that owns it (plus the footing premium), so an entry's cost
#: reaches nothing the pull model schedules: it is the price a DESCRIPTOR
#: would carry if some other provider ever mints one on this family. BOTH
#: place entries declare the cheapest tier — with the quiescent gate gone
#: there is no longer anything for a dearer entry price to mean, and the
#: finer entry declaring the WIDE tier (how "later" used to be spelled)
#: would now simply misprice such a descriptor.
COST_PLACE_ENTRY = COST_PLACE_RING

#: THE RE-WORK BAND (user rulings, 2026-08-19 — H5-PLAN "RE-WORK AGING",
#: which REPLACES the OR-5 ceiling recommendation). The OR-5 census found
#: that nothing bounds re-arming: the worst work key ran 61 BP attempts
#: for 11,820 iterations — 6.2x one full walk of its own ladder — and
#: never certified (MEASUREMENTS "OR-5"). A per-key CEILING was proposed
#: and REJECTED, on L7 grounds: current evidence may reorder work, never
#: narrow a domain, and a cap narrows one. What was ruled instead is the
#: windows' own coalescing discipline translated into PRICING — one term
#: in the price function, read from the spend ledger's per-key attempt
#: count.
#:
#: A FIRST attempt prices exactly as it always did (payload 20 + 2d;
#: payload-first stands and the 2026-08-17 starvation lesson is not
#: relitigated). A RE-attempt prices into this band, which sits BELOW
#: WIDE (ruled): the first re-attempt costs ``REWORK_BASE`` + its own
#: lane term, i.e. 90–98 — dearer than every word pass, cheaper than the
#: wide consult — so a failed tile's re-decode fires only once the
#: cheaper bands have drained. That buys maximal accumulated evidence
#: per attempt and confines churn to the price-level tail: v1's
#: lane-barrier coalescing, recovered with no barrier, no generation and
#: no gate.
REWORK_BASE = 90

#: WHAT ONE MORE PRIOR ATTEMPT ADDS, and it is deliberately UNBOUNDED —
#: the horizon, not the wall. ``REWORK_BASE + REWORK_STEP*(n-1)`` reaches
#: ``COST_PLACE_WIDE`` exactly at the 7th re-attempt and
#: ``COST_PLACE_COLD_LIVE`` at the 11th, so a hopeless key's re-attempts
#: eventually price past cold and are held by the dryness gate to the very
#: end. Nothing is ever REFUSED — the cap the user rejected re-emerges as
#: a price a domain never truncates, the L7-respecting form of the idea.
#:
#: 5 is the child premium's value and for the same reason: it must
#: reorder ordinals within the band without making an ordinal a tier of
#: its own. It is therefore SMALLER than the lane span (8 at the deepest
#: realistic ladder), so a deep first re-attempt can outrank a shallow
#: second one — the same deliberate non-claim the child premium makes
#: against the lane term, and the cascade's own law rather than a leak.
#: "We'll measure and rebalance, optimizing for QUICKEST CLOSE, when the
#: time comes" (ruled): both numbers are PROVISIONAL orders, like every
#: other number in this scale.
REWORK_STEP = 5

#: POSE RE-WORK IS THE DEAREST WORK THERE IS (W3, RULING I2, the user's
#: ruling of 2026-08-23). Every other family enters the re-work band by
#: AGING: a first attempt prices at its own class and
#: :func:`work_price`'s ordinal lifts the repeats. A certificate-labeled
#: pose revision has no such first-attempt reading — it is re-work by
#: definition, because it revises geometry that already committed, on
#: labels that only exist because tiles under that geometry already
#: certified. So the ENTRY prices directly, and it prices at the TOP of
#: the scale: **above ``COST_PLACE_COLD_REST`` (150), the dearest tier
#: any other family DECLARES.**
#:
#: WHERE THAT IS TRUE AND WHERE IT IS NOT — the arithmetic, stated
#: because the first wording of this comment overstated it (W3 review,
#: 2026-08-23). A placement descriptor's price is not its tier's cost:
#: ``place_sched.WindowPlan.price`` adds ``row.rung_cost * lane_depth``
#: plus ``CHILD_PREMIUM``, and cold's rung term is ``COLD_COST_PER_RUNG``
#: = 20, ten times the ordinary lane term. A refine descriptor carries
#: the ORDINARY term (``LANE_COST_PER_RUNG`` = 2, ``solve.refine``), so
#: the two ladders converge and then cross:
#:
#:     depth       0    1    2    3    4
#:     refine    200  202  204  206  208
#:     cold_live 140  160  180  200  220
#:     cold_rest 150  170  190  210  230   (+5 for a child)
#:
#: So refine outranks **every tier's declared cost**, **every ordinary
#: pass at every lane depth** (the dearest is wide at 120 + 8 + 5 = 133)
#: and **every cold pass through rung 2** — and is OVERTAKEN by
#: ``cold_rest`` from rung 3 and by ``cold_live`` from rung 4. That is
#: reachable rather than hypothetical: ``MAX_LANE_DEPTH`` is 4 and
#: ``auto_ppc_levels`` lays c2 at 4800 dpi (both real captures) as five
#: rungs, c3 at 4800 as 2/4/8/12/24. The ruled PROPERTY — "a revision
#: fires only when nothing cheaper is ready" — therefore holds against
#: the whole ordinary ladder and the shallow cold rungs, and INVERTS on
#: the two deepest cold rungs, where a refine descriptor is admitted
#: while a deep cold sweep is still ready. OPEN for the user, with the
#: number he named on one side of it: keeping 200 accepts that
#: inversion (a deep cold sweep is desperate work, and nothing is
#: refused — only ordered); making the property unconditional wants
#: ``COST_REFINE`` at 240, above ``max(row.cost + row.rung_cost *
#: MAX_LANE_DEPTH + CHILD_PREMIUM)`` = 235. Pinned either way in
#: ``tests/engine/test_cost_vocabulary.py``, which asserts the crossover
#: depths explicitly so a reprice cannot pass silently.
#:
#: WHY THE TOP, AND WHAT IT REPLACES. "After the ladder" is what
#: refinement wants and a PHASE is how v1 got it — refine ran after a
#: barrier, over a settled certificate frontier. holo2 has no barriers by
#: design, and the ruling refuses to invent one: **RF1 is PRICED, not
#: gated.** At 200 a revision fires only when nothing cheaper is ready
#: (up to the crossover above), so "after the ladder" is an EMERGENT
#: property of the pull model rather than a rule anybody has to enforce
#: or a phase anybody can get wrong.
#: The two-sided eligibility gate (``solve.refine``: uncertified residue
#: in reach AND certified material in reach, e024's measured law) STAYS —
#: it is not artificial, it is what the algorithm needs to run at all.
#:
#: WHAT THE AGEING TERM DOES AT 200: nothing, for a long time.
#: :func:`work_price` lifts a re-attempt to ``max(base, REWORK_BASE +
#: REWORK_STEP*(n-1))``, which reaches 200 exactly at the 23rd re-fire
#: and first EXCEEDS it at the 24th. So an AGED payload or placement
#: re-attempt does cross this entry from its 24th re-fire on — the band
#: is designed to grow without bound (:func:`work_price`) — and what the
#: entry sits past unconditionally is every other family's FIRST-ATTEMPT
#: price. That is the honest reading of the ordinal here, and it is why
#: this number and not the ordinal is what orders refinement.
#:
#: Calibration's entry (15) is the mirror image and the comparison is the
#: point: a ctx fit must run BEFORE the decodes it improves, so it
#: undercuts payload; a pose revision is worth asking for only AFTER the
#: cheaper bands have drained, which is precisely when the certificate
#: frontier that labels it is richest and the uncertified residue it
#: gains on is smallest. Same one price function, opposite ends of it.
#:
#: THE LINEAGE FORK: recipe entries bind the session identity BY VALUE
#: (``engine.records.SessionIdentity``), so moving this number forks the
#: lineage for FRESH runs. States written under 90 keep the recipe they
#: recorded and are resumed by the build that wrote them, not by this
#: one; the label moves once, here.
#:
#: PROVISIONAL, like every number in this scale. The e024 verdict bounds
#: the appetite rather than the price: refinement pays at the margins or
#: not at all, and the ELIGIBILITY gate (``solve.refine``) is what
#: expresses that — the price only says when.
COST_REFINE = 200


def work_price(base_cost: int, premium: int, prior_attempts: int) -> int:
    """THE PRICE FUNCTION: what one descriptor is queued at, right now.

    Three terms, and the whole scale is here rather than spread across
    the two admission paths:

    * ``base_cost`` — the recipe ENTRY's declared price for this class of
      work (what the entry knows);
    * ``premium`` — the LANE TERM this particular attempt carries
      (``WorkDescriptor.premium``: which rung of a capture's ladder it
      reads, the one thing an entry cannot know);
    * ``prior_attempts`` — the RE-WORK ORDINAL (H5, 2026-08-19), read from
      the descriptor's own durable spend row. Zero on a first attempt, and
      then this function is the identity on ``base + premium``: first-attempt
      behaviour is untouched everywhere, by construction rather than by
      inspection.

    A re-attempt is LIFTED into the re-work band — ``max`` rather than an
    addend, so the term can only ever make work dearer, and a family
    whose own class already prices above the band keeps its own price. The
    lane term rides on top either way: a re-attempt over a fine rung still
    costs more than the same re-attempt over a coarse one.

    WHY IT IS NOT A CAP. The band grows without bound in the ordinal, so
    a key that keeps failing keeps getting dearer and eventually sits
    past cold, where the dryness gate holds it to the very end. Nothing
    is refused and no domain is narrowed (L7); what changes is only
    WHEN — which is exactly what a price is allowed to change.

    Family-blind, and that is the ruled scoping rather than an accident:
    the ordinal is a SPEND-LEDGER quantity, and the placement source
    spends nothing at the wall (its repetition is bounded by the ready
    bit and its own tried set), so placement takes no term without a
    single word of family knowledge here. Ingest cannot take one either —
    its worker retires and declares an empty read-set, so it can never
    re-arm. What is left is exactly the ruling's list: payload
    re-attempts, and the calibration/pose re-work families H5 adds.
    """
    if prior_attempts < 1:
        return base_cost + premium
    return max(base_cost,
               REWORK_BASE + REWORK_STEP * (prior_attempts - 1)) + premium


@dataclass(frozen=True)
class PriceTable:
    """Policy data a task class is priced with (§8.1, §9)."""

    # Observability tripwire, not a semantic bound (§7): a worker whose
    # read-set churns legitimately re-arms many times, so this is set well
    # above the wake-graph's expected depth and exists to make a
    # non-converging fixpoint loud instead of slow.
    max_fires_per_worker: int = 256


@dataclass(frozen=True)
class RecipeEntry:
    """One §9 entry: task class x footing selector x prices x gate x arm.

    ``cost`` is this entry's place in the ONE global order (H4 W2): the
    queue pops the cheapest ready worker across every source. It is data
    on the entry, so it travels into ``SessionIdentity`` with everything
    else and a re-priced policy refuses a state built under the old one
    instead of silently reinterpreting it.

    ``arm`` (R1/M9) is the recipe-supplied override a provider stamps into
    every descriptor it mints for this entry. It exists as DATA on the
    entry — never as an ambient flag — because an override that does not
    ride the descriptor cannot be read back from a resumed state, and its
    spends would collide with the un-overridden ones. Empty means "the
    provider's own default"; the consumers arrive with the calibration
    providers (H4/H5).

    A ``quiesces`` flag rode here from the streaming-ingestion build until
    the 2026-08-17 pricing ruling. It existed only to keep a queued
    acquisition from holding the quiescent gate closed (measured: a
    two-capture decode admitted its FIRST window only after the LAST scan
    had been surveyed, because the working footing of every registry row
    is a finer lane and the finer entry was the gated one). With the gate
    deleted there is nothing for a work class to be exempt FROM, so the
    field went with it rather than surviving as an unread setting.
    """

    task_class: str
    footing_selector: str
    gate: str
    cost: int
    prices: PriceTable = PriceTable()
    arm: str = ""
    #: THE READING SET (H4-LANES stage 1): which of a capture's footings
    #: this entry's work actually reads pixels through. Data, so it forks
    #: the lineage by value like every other field here; meaningful on
    #: the placement entries, where the pull model consults it at
    #: admission (``solve.place_sched``). STAGE 2 FLIPPED THE DEFAULT to
    #: the whole ladder: the cascade is the receiver now, and a run that
    #: wants one lane declares it — which is the right way round, since
    #: the narrow policy is the surprising one and a lineage built under
    #: it should say so in its own identity rather than by omission.
    reading_set: str = READING_ALL

    @property
    def label(self) -> str:
        """DISPLAY only: what a descriptor records as its provenance.

        The entry IS its own identity (it is data, and it travels into
        ``SessionIdentity`` as data); this is the readable stamp a
        descriptor carries, and nothing compares two of them for anything
        but a log line.
        """
        return (f"{self.task_class}/{self.footing_selector}/{self.gate}"
                + (f"/{self.arm}" if self.arm else ""))


@dataclass(frozen=True)
class Recipe:
    """An ordered orchestration policy. The entries ARE the identity."""

    label: str
    entries: tuple[RecipeEntry, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError("a recipe schedules at least one task class")
        if sum(entry.task_class == TASK_CLOSE
               for entry in self.entries) != 1:
            raise ValueError("a recipe declares exactly one close consult")
        for entry in self.entries:
            gates = (_CLOSE_GATES if entry.task_class == TASK_CLOSE
                     else _WORK_GATES)
            if entry.gate not in gates:
                raise ValueError(
                    f"{entry.task_class} entry names gate {entry.gate!r}; "
                    f"the vocabulary is {sorted(gates)}")
            if entry.footing_selector not in _FOOTING_SELECTORS:
                raise ValueError(
                    f"{entry.task_class} entry names footing selector "
                    f"{entry.footing_selector!r}; the vocabulary is "
                    f"{sorted(_FOOTING_SELECTORS)}")
            if entry.reading_set not in _READING_SETS:
                raise ValueError(
                    f"{entry.task_class} entry names reading set "
                    f"{entry.reading_set!r}; the vocabulary is "
                    f"{sorted(_READING_SETS)}")
        declared = {entry.reading_set for entry in self.entries
                    if entry.task_class == TASK_PLACE}
        if len(declared) > 1:
            raise ValueError(
                "a recipe declares ONE reading set for placement; got "
                f"{sorted(declared)} — which rungs are read is a property "
                "of the run, not of an entry that happened to admit a "
                "window first")

    @property
    def close_entry(self) -> RecipeEntry:
        return next(entry for entry in self.entries
                    if entry.task_class == TASK_CLOSE)

    @property
    def reading_set(self) -> str:
        """The rungs placement reads, as ONE answer for the whole run.

        The scheduler is composed once and admits from every placement
        entry, so it needs one value, and ``__post_init__`` is what makes
        asking for one honest: two placement entries disagreeing about
        which rungs are read is a recipe that cannot be executed, not a
        precedence puzzle for the composition root to solve. A recipe
        that schedules no placement answers with the default, because
        that is what a scheduler over no entries would read.
        """
        return next((entry.reading_set for entry in self.entries
                     if entry.task_class == TASK_PLACE), READING_ALL)

    def work_entries(self) -> tuple[RecipeEntry, ...]:
        """The queue-scheduled entries, in priority order."""
        return tuple(entry for entry in self.entries
                     if entry.task_class != TASK_CLOSE)


#: Recipe v1 (H4 W2, extended for streaming ingest, then for cheap
#: payload + priced footings, then for THE LANES): five priced entries,
#: and since 2026-08-17 no gate but ``always``. INGEST leads — the
#: declared scans become capture facts as work rather than as session
#: assembly, at the cheapest price in the order — and PAYLOAD is next,
#: undercutting every placement rung. Placement is the pull model's
#: scheduling set — the two ``place`` entries govern MEMBERSHIP (which
#: footings enter) and nothing else, because the source prices its own
#: tiers and adds the lane term; the close preempts everything.
#:
#: THE READING SET IS THE WHOLE LADDER (H4-LANES stage 2). Every rung of
#: every capture places, and the cascade v1 ran as an unconditional
#: barrier-separated sequence emerges from one cost order instead:
#: coarse windows are cheaper, so they run first; their certificates
#: project done pixels footing-blind, so the finer twins retire at
#: admission; the finer lanes then run the residue.
#:
#: ONE LINEAGE FORK for the wave, and the label moves with it once: the
#: entries ARE the identity, so the reading set and the re-spaced prices
#: are one whole-value mismatch against any state built before them.
RECIPE_V1 = Recipe(
    label="recipe-v1-h5-calibration",
    entries=(
        RecipeEntry(TASK_INGEST, FOOTING_ALL, GATE_ALWAYS, COST_INGEST),
        # H5 P1: the region ctx fit, priced between ingest and payload so
        # a pool that clears its floors is fitted before its tiles are
        # decoded. ONE lineage fork for the phase; the label above moved
        # with it, once.
        RecipeEntry(TASK_CALIBRATION, FOOTING_ALL, GATE_ALWAYS,
                    COST_CALIBRATION),
        RecipeEntry(TASK_PLACE, FOOTING_COARSEST, GATE_ALWAYS,
                    COST_PLACE_ENTRY),
        RecipeEntry(TASK_PAYLOAD, FOOTING_ALL, GATE_ALWAYS, COST_PAYLOAD),
        RecipeEntry(TASK_PLACE, FOOTING_FINER, GATE_ALWAYS,
                    COST_PLACE_ENTRY),
        # RF1's certificate-labeled pose revision, at the TOP of the
        # scale (see COST_REFINE) — dearer than cold rest, so it fires
        # only when nothing cheaper is ready and "after the ladder" needs
        # no phase. Its own eligibility gate is what keeps it silent on
        # material that certifies cleanly.
        RecipeEntry(TASK_REFINE, FOOTING_ALL, GATE_ALWAYS, COST_REFINE),
        RecipeEntry(TASK_CLOSE, FOOTING_ALL, GATE_COUNT_READY, COST_PAYLOAD),
    ),
)

#: THE FINEST-ONLY LINEAGE, kept as a NAMED configuration (H4-LANES stage
#: 2). Flipping a default must not delete the reading it replaced: the
#: finest rung alone is what every holo2 decode before this wave did, it
#: is the configuration v1's own placement is comparable against
#: (``measure/verdicts/test_v1_parity``), and it is the one a run reaches
#: for when a coarse lane is known to be worthless. It is the same
#: recipe with the placement entries' reading set moved, so it forks the
#: lineage by value like any other policy change and needs no label of
#: its own beyond this one.
RECIPE_V1_FINEST = Recipe(
    label="recipe-v1-lanes-finest-only",
    entries=tuple(
        RecipeEntry(entry.task_class, entry.footing_selector, entry.gate,
                    entry.cost, entry.prices, entry.arm, READING_FINEST)
        if entry.task_class == TASK_PLACE else entry
        for entry in RECIPE_V1.entries),
)

__all__ = [
    "COLD_COST_PER_RUNG",
    "COST_CALIBRATION", "COST_REFINE",
    "COST_INGEST", "COST_PAYLOAD", "COST_PLACE_COLD_LIVE",
    "COST_PLACE_COLD_REST", "COST_PLACE_ENTRY",
    "COST_PLACE_RING", "COST_PLACE_WIDE", "COST_PLACE_WORD_CENTRE",
    "COST_PLACE_WORD_REST",
    "FOOTING_ALL", "FOOTING_COARSEST", "FOOTING_FINER", "GATE_ALWAYS",
    "GATE_COUNT_READY", "GATE_EXHAUSTION", "PriceTable",
    "READING_ALL", "READING_FINEST",
    "RECIPE_V1", "RECIPE_V1_FINEST", "REWORK_BASE", "REWORK_STEP", "Recipe",
    "RecipeEntry", "TASK_CALIBRATION", "TASK_CLOSE",
    "TASK_INGEST", "TASK_PAYLOAD", "TASK_PLACE", "TASK_REFINE", "work_price",
]
