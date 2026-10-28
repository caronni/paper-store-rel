# TOOLBOX-INVENTORY — every mechanism that ever paid, priced for an additive box

Version 0.2 — 2026-08-23. Status: **INVENTORY, code-agnostic, NOT
NORMATIVE.** Nothing here amends a design doc; nothing here is a build
order. It is the catalogue a future holo2 "toolbox" scheduler would shop
from, with each item's measured yield, its measured loss, its cost, its
prerequisites and its isolation notes.
(v0.2: §6.13 stops being UNMEASURED — the K instance was run over e029's
complete residue, INDEPENDENT-PLANES §2.13.)

Scope: RECEIVER-axis mechanisms. Format-axis and discovery-axis items are
listed in §9/§10 for completeness and are explicitly **outside** the box.

Sources of record, cited per entry: docs/INDEPENDENT-PLANES.md v0.5,
docs/PLANE-FIELDS.md v0.13, docs/COMPOSITE-POSE-DESIGN.md,
docs/COLOR-UPLIFT-MEASUREMENTS.md §1–§15, docs/COLOR-UPLIFT-PLAN.md §8,
docs/RECEIVE-DESIGN.md v0.57, docs/PLACEMENT-IMPROVEMENTS.md,
docs/PAYLOAD-IMPROVEMENTS.md, docs/DONE-GEOMETRY.md,
docs/PHASED-SCHEDULE.md, docs/PILOTS-DESIGN.md §15.9,
experiments/014, 018, 023b, 023c, 024, 029–033, the `.claude/memories`
line records, and holo2/docs/DESIGN.md §3a/§6.8/§6.9 + the H4/H5 plans
(the last **only** to mark what holo2 already has, so this inventory does
not re-propose it).

---

## 1. Doctrine — what the box is, and the four conditions

**The idea, in the user's terms.** Stop trying to find the one correction
that fixes a page. Build instead a LARGE DISCRETE SET of attempt
generators — dozens of small, independent, mostly-cheap ways of producing
one more hypothesis about one residue slot — and schedule them over a
complete capture's residue. Each generator is gated by the certificate:
an attempt that certifies is taken, an attempt that fails changes
nothing. **Any tool that recovers even one payload tile has paid its
price.** The question stops being "does this mechanism beat the
incumbent?" and becomes "does this mechanism ever, anywhere, produce a
certificate the incumbent does not?" — a strictly easier question, and
one the record shows we have repeatedly answered YES for mechanisms we
then discarded because they lost an adoption comparison they were never
required to win.

Four conditions make that sound. They are not style; each of them is the
disposition of a specific measured failure in this project's record.

**(1) ADDITIVE, NEVER REPLACING.** A tool proposes an extra attempt at a
residue slot. It never removes, replaces or displaces the attempt the
incumbent path would have made. This is the single line that separates
almost every measured negative in the record from an untested positive.
The two sharpest cases:

- The **pose writer** (INDEPENDENT-PLANES §2.11) was measured over all
  334 open slots of the sheet-I state and lost 5 of 5 certificates with
  +2.1 pp cell BER — *as a REPLACEMENT of the sampling geometry*. The
  measurement says so in its own words: "attempts only add, but these are
  alternative sampling GEOMETRIES, each producing its own evidence set. A
  receiver that ATTEMPTED both would union them; a pose WRITER replaces
  the geometry, and the replacement loses."
- The **A5 multi-state context matrix** (COLOR-UPLIFT-MEASUREMENTS §11.6)
  gained 255 addresses corpus-wide and lost 6 — and the six were
  diagnosed as re-timing, i.e. tiles the *old configuration* would have
  certified at a lane the new configuration reaches differently. The fix
  the project found was not a better arm: it was to SCHEDULE the
  displaced configuration too (§11.10, the `u-off` baseline lane). That
  is condition (1) discovered the expensive way.

**(2) THE CERTIFICATE GATE CARRIES THE WEIGHT.** In an additive box the
only thing standing between "many attempts" and "wrong bytes" is the
certificate. The empirical record is extraordinarily strong — **0 wrong
certificates in 69,066,304 audited cells** across the whole colour-uplift
campaign (COLOR-UPLIFT-MEASUREMENTS §14.2), 0 in every tier all campaign,
0 across every plane-fields run. But the record is empirical, and the
receiver's status is still **PROVISIONAL** (RECEIVE-DESIGN §12; §14.8:
"the physical/null false-accept gate, the BER envelope and the support
margins are still unfrozen"). **A box of N tools multiplies the number of
CRC exposures by roughly N, on the same denominator.** The project has
already registered one such multiplication explicitly and priced it — the
cmy7 demap loop's "per-attempt CRC exposure rises from one to at most
DEMAP_ITERATIONS — a 3x undetected-error budget on the same denominator"
(RECEIVE-DESIGN §6.2a, PK8/PK9). A toolbox turns that from a registered
compromise into the design's central assumption. **Therefore: freezing
the physical/null false-accept qualification stops being housekeeping and
becomes a PREREQUISITE of the box.** It is the one item in this document
that is not optional and not a tool.

**(3) COST ORDERS THE BOX, AND IT IS LEARNED FROM ACCOUNTING.** With
correctness delegated to the gate, the only remaining question is what to
run next, and the answer is expected certificates per second. The record
already prices work in exactly this currency where it bothered to:
`timing.processor_seconds` per stage from the runtime's own events
(RECEIVE-DESIGN §10.6; the profiling doctrine in CLAUDE.md), per-lane CPU
splits (COLOR-UPLIFT-MEASUREMENTS §14.5), per-probe milliseconds
(INDEPENDENT-PLANES §2.9/§2.9c), per-certificate marginal cost
(§13.5: "the third iteration buys 15 more certificates for 338 s of CPU
(22.5 s each) against the second's 24 for 478 s (19.9 s each)"). Two
consequences: costs in this document are stated in the units the record
measured, never invented; and a tool's cost is a MEASURED, UPDATED
quantity in the running system, not a constant chosen at design time —
the project's whole experience with swept constants (§12 R1/R2: two
successive applicability floors, neither of which separated help from
harm, retired) says a scheduler that learns cost from its own accounting
is the only kind that will not need a third floor.

**(4) TOOLS ARE JUDGED ON COMPLETE RESIDUES, NEVER ON HAND-PICKED TILES
OR INVENTED BARS.** Every yield number that survived this project's own
review was measured over a complete, declared population; every number
that had to be retracted was measured over a selected one. The record's
own warnings, verbatim in substance: the six dead tiles and two controls
are OUTCOME-SELECTED, "they are where the residue is" (§2.10, §2.12); a
one-tile smoke showed the soft column at 91–101% of the oracle and the
eight-tile set showed 40%, "recorded because it is exactly the error the
eight-tile set exists to catch" (§2.12); a two-lane library unit read +19
on xerox c2-cmy8 and the full twelve-lane replay finished at net −5, so
"only full-lane-set runs are evidence of yield" for conditioning-class
arms (RECEIVE-DESIGN §6.2a, tier-law amendment). And the corollary about
BARS: the ≤5/53 dead-band bar was written before the mechanism was
measured and was later shown unreachable by ANY geometry
(INDEPENDENT-PLANES §2.4, §4.L) — "pilot-before-wave (caught an
unreachable bar for hours of compute)" vs "charter-before-measurement
(the ≤5/53 bar)" is the record's own works/doesn't-work row (§5). In an
additive box the bar is fixed and needs no invention: **strict superset
plus at least one certificate on a complete residue.**

**What the four conditions buy.** Monotonicity by construction. The
supplemental-lane law already states the mechanism in law:
"*An arm that cannot prove universal non-regression is not gated — it is
SCHEDULED*… the per-address retirement law makes it MONOTONE BY
CONSTRUCTION… It can therefore only ADD. **No adoption gate, no
applicability floor; the zero-wrong-certificate audit remains the only
bar.**" (RECEIVE-DESIGN §6.2a, PK4.3). The toolbox is that law taken to
its limit: not two supplemental arms behind a ladder, but a box of them
over the residue, ordered by learned cost.

**What the box does NOT solve.** Two measured limits bound it, and both
must be stated up front or the box will be oversold:

- **The frontier cannot roll back.** A supplemental lane "restores the
  CONFIGURATION, not the HISTORY" — three of the six stranded addresses
  in §11.11 were certified at exactly the footing the restoring lane runs
  at and were still not recovered, because by then the known-cell field
  carried 794 / 5,460 certificates where the baseline's own lane saw
  ~668 / ~5,100, so a different model was fitted. "Recovering an address
  whose certification depended on a SMALLER prior set would mean rolling
  the frontier back, which is the one thing §6.3 forbids."
- **Some residue is not attempt-limited.** Sheet I's 334 open slots sit
  at 11–18% cell error against a gate near 7.6% (INDEPENDENT-PLANES
  §2.11); the supervised affine CEILING on the dead band is 9.70%, still
  ~0.7 pp short (§2.4). No scheduler reaches those with geometry. The box
  is a yield instrument, not a physics instrument.

**How to read an entry.** Each tool carries: what it does · where
measured (doc §, date) · measured yield AND where it lost · why it is
parked/discarded · whether it is ADDITIVE as an extra attempt · cost ·
prerequisites · holo2 isolation notes · priority guess.

*Additive* takes three values:
- **yes** — the tool produces an extra attempt at a slot; the incumbent
  attempt is untouched; a union of certificates is the natural
  composition.
- **needs union-of-attempts** — the tool as measured REPLACED something
  (a geometry, a calibration, an ink map); it can be additive only if the
  scheduler runs both and unions the results. Every "measured negative as
  a replacement, untested as an attempt" item lives here.
- **evidence-level: keeps original attempt** — the tool does not generate
  an attempt at all; it improves the evidence a later attempt reads
  (fields, probes, anchors, calibration furniture). These are shared
  state, not box items, and they must be gated separately because they
  can regress a slot that would otherwise have certified.

*Priority* is a guess at yield-per-cost, graded **A** (build early; a
measured certificate at low cost), **B** (measured signal, cost known,
needs one measurement to place it), **C** (plausible, unmeasured, cheap
to try), **D** (record-only; keep the knowledge, do not build).

---

## 2. What holo2 already has (do not re-propose)

Read from holo2/docs/DESIGN.md and the H4/H5 plans. Listed so the box's
entries can name their scheduler hook instead of inventing one.

**Built and merged in holo2** (everything through H5 EXIT is on main —
`9d5a54d` H4 EXIT, `940b5b6` H5 EXIT; *note: CLAUDE.md's holo2 bullet is
STALE, it still says "H4 THROUGH W2 MERGED"*): the commit wall with
publication-order law; optimistic transactions with a declared
commutative merge for the tile carry; dispatch/start markers and
journal-authoritative state; continuous admission; **the pull model** —
in-memory monotone worklist, one-bit wakes with the commit-then-ping /
test-and-clear-then-consult orderings, fire-time consult
(`CONSULT_KEEP = 8`, plus a WIDE tier of 8 nearest page-wide anchors and
one regional-affine seed), and the tried-set floor
(`49 × (tried + offered)`); **global cost tiers in one total order**
(payload < ring < word-centre < word-rest < wide < cold-live <
cold-rest), gated tiers with instantaneous dryness; the per-window
unified job; **footing progression as PRICE, not gate**
(`LANE_COST_PER_RUNG = 2`); streaming ingestion as descriptor work;
**window subdivision** (depth 1, 70-cell floor, child premium +5, ordinary
members of the same set); **park/defer verified SUBSUMED** (a
ladder-exhausted window goes dormant; three wake channels — ring, donor,
seed — and nothing polls); **cold search** (`cold_live`/`cold_rest` per
rung, page set derived at fire time, and cold NEVER commits a pose — it
proposes a seed the ordinary fit revalidates); **quarantine + the
whole-word rival gate**; **aging / the re-work band** — the price
function's third term, an ordinal, `max(base, 90 + 5·(n−1)) + premium`,
unbounded, crossing wide at the 7th re-attempt and cold at the 11th;
**done-pixel projection and the done gate** (DONE-GEOMETRY, realized:
derived on demand, never persisted, cell-granular, and DONE deletes
nothing); close preemption with incremental consult; spend-once with
read-set-as-identity and a ledger that folds to the latest; collections,
re-offerable declines, leases, staged blobs. Calibration: **CA2 region
context calibration is LIVE**; **CA1 certified-label enrichment is BUILT
but DIALLED DEFAULT-OFF — measured +68% cost, zero yield**; **RF1
certified pose refinement is BUILT but DIALLED OFF** with two rulings
owed.

**Named in holo2 but not built:** deciders (eligibility/desirability;
*deciders reorder and park, never forbid*); block-level DONE; compaction;
**CA8 — the supplemental-lane law as a RECIPE capability, an arm that
cannot prove universal non-regression scheduled over the uncertified
residue, monotone by per-address retirement.** *CA8 is the closest thing
in the tree to this document's toolbox, and it is where the box belongs.*
Also unbuilt: CA1's per-window PAVA provider, CA3–CA7 (the colour arms),
RF2, lease admission control, the loser-revisit channel, the live
progress channel.

**The interface a tool plugs into.** Two admission sources compared BY
COST at every step: `Provider` (descriptor path, repetition bounded by a
durable spend row) and `WorkSource` (pull path, repetition bounded by the
flag protocol and the source's own tried set). A `WorkDescriptor` carries
family, **subject — any resource key, not necessarily a tile** — route,
scope (which carries `arm`), leases and premium. A `Worker` declares
`read_keys` (which IS its identity) and `run(...) -> WorkResult`; it
proposes, never commits, never mutates, never reads a clock. A `Decline`
carries `wake_on` keys, empty meaning permanent. Adding a tool means
adding a recipe entry — and **recipe entries are lineage identity BY
VALUE**, so a new entry, a moved gate or a changed price refuses resumed
states at open.

**Cost, and the gap this document's condition (3) has to close.**
`work_price(base, premium, prior_attempts)` is the one price function;
`TierPrice` rows carry their own provenance. But the numbers are ORDERS,
not measurements — the tier table says so in its own words, "PROVISIONAL,
all of it" — and **there is no per-attempt cost estimator and no cost
feedback loop**; the health-ledger-fed cost tables are exactly the
unbuilt DECIDERS. What DOES exist and is directly usable: `SpendRecord.
attempts`, **`SpendRecord.exposures` — monotone CRC false-accept draws,
summed page-wide**, per-source counters, and lease residency. The
exposure counter is the natural home for condition (2)'s accounting.

**Residue, concretely.** There is no single residue object: the tile map
(presence = addressed, minting = certified) with incrementally maintained
open/certified partitions; the done-pixel projection per capture; the
in-memory placement scheduling set; `TileRecord.baselined` (the durable
"a decoder ran here and failed" fact the retry route derives from); the
spend ledger's attempt ordinal; and the close's per-(stream, block)
distinct-ESI counters.

**"Hints are scheduling annotations, never facts" — concretely.** The
hint record families were DELETED, not deprecated; hint distance is
arithmetic recomputed at every fire from committed poses; **nothing about
placement scheduling is durable**; and **a failed pass writes NOTHING** —
no no-op commit, no spend row, no subscription.

**What holo2 does NOT have, and what a tool must not touch.** No colour
at all (CMY7/CMY8 rows are declared, nothing decodes them; the colour
leaves arrive with H7) — and therefore **no field machinery of any kind**:
no per-plane registration fields, no per-cell local affines. The import
firewall is absolute (holo2 imports nothing from `src/holo`,
`src/paperholo` or `experiments/`; a carry is a copy with a declared
adaptation, pinned by an oracle outside the tree). The layering DAG is
`core ← format ← solve`, `core ← capture ← solve`, `core ← engine`, with
the engine importing `core` only. Record ownership belongs to the writing
package, and a new or changed family refuses every existing state dir
loudly, leaving the bytes intact. No clocks, no RNG, deterministic
iteration, ≤1000 lines/file, a new third-party import needs a user
ruling. The §6.8 pixel doctrine binds every sampling tool: raw captures
memory-mapped and never loaded; consumers read through views, never
copies; anything genuinely region-scale exists only under the engine's
leases, "and is not to be imitated ad hoc". Laws a tool cannot bend: L2
(footing is in the key), L3 (one owner per cell per (capture, footing);
no evidence VALUE enters owner selection), L5 (certificates never voted),
**L6 (no self-training — labels only from prior commits)**, **L7 (current
evidence may reorder work but never narrow a domain, lower a floor, or
truncate a rival set)**, L8 (rival gate + quarantine).

**One scope tension to rule on, stated plainly.** holo2's standing
algorithmic ruling is "*we implement src/holo, algorithmically — the
thing we change is scheduling and orchestration*", and its step-back
round records "**NOT a candidate: changing what work exists** … bounded
to scheduling cost, never reach". A toolbox is by definition new reach.
CA8 already contemplates arms as recipe capabilities, so the door exists —
but **the box needs an explicit scope ruling before it is built in
holo2**, or it will violate a law the tree currently enforces.

---

## 3. Acquisition & addressing

### 3.1 Multi-slot Stage A (word-route widening)
**What.** A 200-cell window contains nine full 64-cell address slots;
sweep all of them (staged: centre first, widen on failure) instead of
only the historical centre slot, so the algebraic route seeds where it
previously fell through to correlation.
**Measured.** PLACEMENT-IMPROVEMENTS §3.1–3.3 + Execution status
(2026-07-31; RECEIVE-DESIGN v0.22/v0.26/v0.29). Declared 147,456
hypotheses/window under the α = 1e-3 union-bound ceiling of 581,074
(three-row envelope 442,368 → 7.6e-4; a fourth row refuses at
construction). Synthetic A/B, byte-identical inputs: **route substitution
perfect — old 19 word + 32 cold seeds, new 51 word + 0 cold**, at
**exactly invariant yield (604 certificates, same tiles, same bits)**.
**Where it lost:** the up-front all-slot sweep cost **+267 s address CPU
(+21%)**, cured by staging (3,627 → 794 ms per word-succeeding window);
and the fixture is coverage-limited at 41.3% payload area and cannot
close, so the yield invariance is not evidence that widening never adds.
**Additive:** yes — more decode attempts at the same window, each priced
by the existing union bound.
**Cost.** ~2.8 s of 8-slot decode per word-dead window ahead of a cold
that costs only ~1–3 s at a single-page domain (the measured residual
that motivated cost-aware ordering).
**Prereq.** a false-accept budget that prices the widened hypothesis
count — which exists.
**holo2.** Present as the word-centre / word-rest tiers.
**Priority.** — (already had).

### 3.2 Erasure-aware word decoding (known-position rung)
**What.** Errors-and-erasures BCH decoding of an address word where part
of the word is missing — acceptance `2e + f ≤ 2t`, i.e. within-budget
uniqueness — so a fragment carrying only part of a pilot word can still
self-address.
**Measured.** experiments/014 §014.5 item 1. **9,120 decodes** (76 real
pilot tiles × 6 visibility fractions × edge/random cuts × 2 detectors).
With ctx-class bits: **q = 0.80 → 96.1%, 0.85 → 98.7%, 0.90 → 100%**.
With global-detector bits: **dead below 0.80 (0–2.6%), 77.6% at 0.85,
92.1% at 0.90** — the rung REQUIRES the better detector. Edge-geometric
and random cuts are indistinguishable at ctx. **Zero wrong-address
decodes in all 9,120 trials.** q = 0.70 (f = 30 > 26) refuses outright,
as it must. **Where it lost:** nothing measured — but the SEARCH half is
gated: the built code's own docstring pins it, "*Known-position decoding
only: hypothesis SEARCH must not use erasures until the Stage-A
false-accept budget is re-derived for reduced-support words.*"
**Status.** BUILT and carried into holo for known-position reads.
**Additive:** yes.
**Cost.** two trials per erasure fill; negligible beside a cold search.
**Priority.** — (already had) for known-position; see 3.3 for the parked
half.

### 3.3 Erasure-aware Stage A (cold/search-side erasure decoding)
**What.** Extend the erasure rung to the SEARCH route, so windows whose
slots are 74–89 cells visible can seed instead of falling through to
correlation.
**Measured.** PLACEMENT-IMPROVEMENTS §3.4 — PARKED by user reservation
2026-07-31. Yield UNMEASURED. The blocker is exact and named: "the
disjoint-sphere union bound must be redone — sphere volume grows with
erasure count, making the per-phase false-accept probability
phase-dependent". Reopening trigger recorded: physical-v1 confetti
showing word refusals dominated by 74–89-visible slots.
**Additive:** yes, and it is the single cheapest way to convert a cold
search into an algebraic one on damaged material.
**Cost.** one decode per phase hypothesis, as today, over a larger
hypothesis count.
**Prereq.** **the re-derived false-accept budget** — which is exactly the
qualification condition (2) says the box makes load-bearing. These two
items should be done together.
**holo2.** Word tier; no new machinery, a wider hypothesis set and a new
budget.
**Priority.** B — unmeasured, but it is a named conversion of the box's
most expensive tier (cold) into its cheapest (word), and its blocker is
work the box needs anyway.

### 3.4 Later-lane address recovery with calibrated scores
**What.** Re-attempt words that failed at their own lane using the
CALIBRATED evidence stack's scores plus margin-based erasure decoding
(`2t + e < 27` halves the cost of low-confidence sites), late in the
session when calibration exists.
**Measured.** COLOR-UPLIFT-PLAN §8, address-phase candidates
(2026-08-09 audit), ranked (1) of three. **UNMEASURED.** Design
constraints recorded: it respects the bootstrap (lane 0 stays blind) and
the l00 lesson (uncalibrated margins at coarse footings are exactly the
unreliable ones). Value case named as fragments/slivers and marginal
channels, **NOT** the healthy corpus (which addresses at ≥99% footprint).
**Additive:** yes — it re-attempts words the ladder already refused.
**Cost.** UNMEASURED; the shape is one decode per failed word per late
lane.
**Prereq.** the calibrated stack (so, a late lane); the erasure budget of
3.3.
**Priority.** C — unmeasured, but it is the natural companion to 3.3 and
its clientele (scraps, marginal channels) is precisely where the box's
value case lives.

### 3.5 Per-channel / plane-aware word matching (A.2, R3)
**What.** Read the address word per colour channel at per-plane offsets
(R→C/W, G→M/W) instead of on luma only, so a C–M desync that breaks luma
addressing does not kill the window; and feed the fine offsets the word
solve measures BACK as field evidence instead of discarding them.
**Measured.** INDEPENDENT-PLANES §4.A.2 + PLANE-FIELDS §2 beat 2/6.
**Near-zero payoff on sheet I** — words are W/CM, the C/M differential is
0.1–0.3 dot, and the word footprint is 99.8% even on the FAILED cmy7
sheet. Its value is declared for thin footings (4 px/cell at 1200 dpi),
scraps and worse engines, where the d = 27 margin shrinks —
**UNMEASURED there**. COMPOSITE-POSE-DESIGN §6 records that word solves
measure a fine offset and today **DISCARD** it.
**Additive:** yes for the read (an extra addressing attempt per channel);
**evidence-level** for the reverse flow.
**Cost.** a per-pixel RGB→CMY derivation and one matched filter per
channel — "nothing more" (PLANE-FIELDS §2 beat 10).
**Prereq.** a plane-aware sampling seam at the ADDRESS stage, which does
not exist today (the field enters ONE seam, payload sampling).
**holo2.** Blocked on colour (H7).
**Priority.** C — free evidence and a design-coherence win; a yield item
only in the marginal regimes, which are exactly the regimes the box is
for.

### 3.6 Comb — cyclostationary cell-clock phase per plane (tier iii)
**What.** The printed payload is dense stationary noise whose PRINT is
cyclostationary at the cell rate; squared/highpassed, each channel's edge
energy carries a spectral comb at the cell frequency whose local Fourier
phasor gives that plane's amplitude and phase per block —
**registration evidence that needs no decoded tiles and no furniture.**
**Measured.** PLANE-FIELDS §2 beats 4–6, §4 V1; INDEPENDENT-PLANES §4.F.
**UNMEASURED — V1 was never run.** Its charter role was made empirically
concrete by W6: column 8 (zero Y evidence) went 53 → 46 while bands 1+2
collapsed, and "zero-evidence bands defeat extrapolation" is the measured
cause (PLANE-FIELDS §6.4 cause 1). **Where it lost its priority:** the
charter role is obsolete — dead-band registration IS measurable today
(neighbour estimator r ≥ 0.9) and registration alone does not close them
(INDEPENDENT-PLANES §4.F). DEMOTED to "a scrap-recovery feature, behind
the detector line".
**Additive:** evidence-level — it feeds a field, it does not attempt.
**Cost.** UNMEASURED; phase precision scales with block area, and band
edges (not the 100 mm period) are the binding constraint (PLANE-FIELDS §5
item 2). Crosstalk needs a 3×3 phasor unmix or Y's phase is biased ~0.1
cell.
**Prereq.** none — this is its whole point: dense payload, no furniture,
no decode.
**holo2.** Blocked on colour; the K instance (n = 1) is buildable.
**Priority.** C for genuinely evidence-free material (small scraps,
zero-certificate columns), D as a dead-band strategy.

### 3.7 Swim rescue tier (R0.5) — per-window/per-scrap plane swimming for ACQUISITION
**What.** When acquisition itself fails because C and M landed on
different phases, swim C/M poses on their own per-channel word channels
(bounded local search, d = 27-gated) and take Y relatively from pooled
dust or the comb; certificate-gated, residue-scheduled.
**Measured.** PLANE-FIELDS §6.5.2 + §2 beat 14. **UNMEASURED.** The
argument on record for why PK6's negative does not apply: "rescue on dead
windows anchored by strong per-channel words is the opposite regime from
free corrections on working windows estimated from weak anchors".
**Additive:** yes — certificates gate everything, so a rescue on dead
windows cannot regress; and swum scraps then feed the field, "the rescue
bootstraps the pooling it could not wait for".
**Cost.** the swim's cost (5.1) × the number of dead windows.
**Prereq.** 3.5 (per-channel words) for the C/M half.
**Priority.** C — unmeasured, but it is the acquisition-side twin of the
box's canonical tool and it targets the one regime (small scraps) where
the record has no other answer.

### 3.8 Dust as independent placement-validation bits
**What.** Use the ~56 bits/tile of known dust content as an independent
check on a placement, rather than as registration anchors.
**Measured.** COLOR-UPLIFT-PLAN §8 address candidate (2). Explicitly
**"no yield change, but tightens the STILL-UNFROZEN physical/null
false-accept qualification"**. Complements PLANE-FIELDS §2 beat 18's
verdict that dust is functionally demoted as a registration anchor and
retained as calibration bootstrap and cold verification content.
**Additive:** neither — it is a GATE ingredient.
**Priority.** B **as qualification work, not as a tool** — it feeds
condition (2), which the box needs.

---

## 4. Placement & pose

### 4.1 Frontier scheduler — wave-front order, nearest-first anchors, deferred cold
**What.** Order windows by expansion from accepted placements rather than
by static support; try chain anchors nearest-first; when a window's cheap
routes fail, PARK it rather than paying cold immediately, and re-sweep the
parked set after any acceptance anywhere in the region.
**Measured.** PLACEMENT-IMPROVEMENTS §1.1–1.3 + Execution status
(2026-07-31, RECEIVE-DESIGN v0.23). Synthetic word-killed two-window
fragment: **2/2 accepted with 0 cold searches vs 1** under the sequential
ladder; each saved cold is a full 4P+8-FFT sweep, **~12 s/window at
production scale**. Clean fragment: 0 colds, 0 deferrals — no overhead
path. **Where it lost:** nothing measured; the census that would price it
on REAL material (§5.1: how many cold acceptances had a later-accepted
same-region window in chain range) is still owed.
**Status.** BUILT in holo1. **Additive:** yes — pure reordering, admission
arithmetic untouched (§5.3: evidence may reorder work, never narrow a
domain or lower a floor).
**Cost.** Negative (saves colds). **Prereq.** none.
**holo2.** Superseded there by the pull model; do not re-propose.
**Priority.** — (already had).

### 4.2 Cold-search exact-cost family — FFT caching and batching
**What.** Cache the kernel transform across the page loop and the padded
page transform across windows; compute the second peak only for the
winning map.
**Measured.** PLACEMENT-IMPROVEMENTS §2.1–2.3 + Execution status.
Bit-identical by fixture. **1.33× / 1.55× / 1.65× at P = 4/16/64**,
growing with P toward a ~2.4× FFT-count asymptote (the doc's earlier "~3×"
was a count-based upper bound, not a measurement). Winner-only second peak
saves 1,247 multi-MB copies on a full 312-page C3 sweep. **Where it lost:**
§2.4 stacked page batching REJECTED — strided-batch FFT kernels are not
provable bit-identical by fixture.
**Additive:** yes (exactness by construction). **Cost.** negative.
**Priority.** — (already had); the *lesson* transfers: a speedup that
cannot be proven exact does not ship.

### 4.3 Correlation placer for scraps (the F13 matched filter)
**What.** FFT matched-filter search of a fragment's detected pilot field
against the seed-predicted page-wide pilot field, support-aware, over all
offsets and all four rotations — it places (and rotates) a scrap that
carries no complete address word.
**Measured.** experiments/014 §014.5 items 2–4. Genie bits, FULL-page
hypothesis space, 5 positions × {4,5,6,8,10} mm × 2 detectors:
**placement CORRECT 100% at every size including 4 mm**; the gate
**PASSES 5/5 at ≥ 5 mm and correctly REFUSES all 4 mm** (rivals dip to
0.103–0.115 under the 0.20 bar at ~60-site support — "honest ambiguity,
not a miss"). Worst correct-placement mismatch 0.086; min rival at ≥5 mm
0.211; **rotation recovery 3/3**; wrong-seed null refused at the d-spectrum
floor (0.267); wrong-region pending mask refused. ISOLATED end-to-end
(own pitch, own lattice lock, ctx detect, place): 6/8/10 mm **5/5 each
placed + gated + correct** (placed-bits BER 0.3–2.7%); 5 mm 5/5 correct,
4/5 gated. Fresh-window validation on a scan whose constants were set
elsewhere: **6/6 correct, mismatch 0.007–0.021, rivals 0.271–0.302**.
Gate constants FROZEN at true < 0.15, rivals > 0.20.
**Where it lost:** below 5 mm it refuses (correctly); and its guarantee
rests on the code's own distance spectrum — see 4.6.
**Cost.** **~0.73 s/fragment** for the whole 7.3 M-offset × 4-rotation
search with a cached field; pruning to a region gives the same answer.
Memory needed a fix: the naive form retained ~167 MB of score maps per
(page, rot); streaming top-2-with-shoulder made it byte-identical at
**peak 786 → 272 MB**.
**Additive:** yes — it is a placement PROPOSAL that must pass the same
gates.
**Status.** BUILT in paperholo. **NOT PRESENT IN holo** — holo's placement
is page-window pose placement, a different mechanism; confetti
correlation placement is a paperholo-only capability today.
**holo2.** Would be a new tier below cold (or a cold flavour); it needs
the prepared-region view and a lease, nothing else. Must not commit a
pose — propose a seed the ordinary fit revalidates, exactly as holo2's
cold route already does.
**Priority.** A **for scrap material** — a measured 100%-correct,
sub-second placement route for pieces that cannot self-address, and the
capability is currently missing from the production tree.

### 4.4 The anchor-graph bundle (padded correlation, mask-aware windows, ID retry, ID-window folding, angle sweep)
**What.** Five changes shipped as one placement chain: (a) padded
correlation so page-edge pieces whose derotated array overhangs the field
are not excluded by construction; (b) a mask-aware window grid
(quarter-stride, mask-snapped) instead of bbox-anchored tiling; (c) ID
retry at top-coverage windows; (d) folding a successful ID-window decode
instead of discarding it; (e) a multi-angle placement retry seeded from
the measured angle, plus window-split above the rigid-model span.
**Measured.** experiments/018 §018.3, A/B on the 189-piece carve fixture,
identical inputs. Baseline: **264 symbols at canvas 1, closes at 443,
178/189 pieces (94%)**. Anchor chain: **325 symbols at canvas 1 (+23%),
closes at 512, 189/189 pieces (100%), 0 failed**; volume byte-exact both
ways. **GT audit: 189/189 observations inside their source rects, 0
misplaced, 0 duplicate claims.** Component evidence: (a) a piece whose
true origin was 85 cells past the feasible maximum, with only 497 of 44k
core cells actually off-page, places at z 25.1 / 0.139 mismatch;
(b) 0/6 bbox windows sat at 35–62% mask coverage against a ~0.7 pass
boundary — 3 mask-aware windows gave 5 tiles / 2 symbols; (c) "centre ID
on ink" was REFUTED as a rule (a piece decoded at 0.518 ink coverage
while another failed at 1.000); (d) an ID window that succeeded at 8/9
words was being thrown away.
**Where it lost:** review found a real crash class (mask-filtered grid on
images narrower than one window — the ≥26 mm-long / <25.4 mm-wide strip).
**Additive:** yes — each is an extra placement attempt.
**Cost.** UNMEASURED per-piece; the sweep multiplies the placer's 0.73 s
by the angle candidates.
**Priority.** A for scrap material — the largest single-build placement
gain in the record (+23% symbols at canvas 1, 94% → 100% of pieces).

### 4.5 Sub-window / quadrant placement (the rigid-model coherence limit)
**What.** When a piece is too large for one rigid pose, place its
quadrants or sub-windows independently.
**Measured.** experiments/018 §018.2 and §018.9. A 1518 mm² piece at
−11.8° localizes correctly (z 14.9 vs rival 6.1) and is **refused at
mismatch 0.349** — and **even at its best angle the full-piece rigid
mismatch floors at 0.248**, because a 47 mm piece with a −0.31% y-scale
exceeds the rigid model's coherence length. **Quadrant-scale placement
plus the existing refine chain: 4/4 quadrants pass at 0.043–0.101 and 12
symbols certify against 0 in production.** A second piece at +39.25°:
its own 150-cell sub-windows place at 0.094 while the whole 396-cell
piece floors at 0.263; the split did not engage because the core-cell
threshold vetoed it, and at a lower threshold it converts (0.156 win /
0.180 gap, 6 virgin tiles, origin corroborated three ways).
**Where it lost:** the bare threshold change cost **−14% emission** on
the fixture, which is why the disposition is a whole-first-THEN-split
ORDERING rather than a lower constant — DEFERRED to a carve-fixture A/B.
**Additive:** yes, and the deferral is itself a condition-(1) lesson: as
an ORDERING (try whole, then split) it is additive; as a THRESHOLD it
replaces and loses.
**Cost.** one extra placement per sub-window.
**Priority.** A — 12 certified symbols against 0, on material the whole-
piece model provably cannot represent.

### 4.6 The d = 27 spectrum floor (gate arithmetic every placement tool inherits)
**What.** The decoy-rejection margin available to any correlation
placement is the address subcode's own minimum distance.
**Measured.** experiments/014 §014.4 Finding 2 + the 2026-07-29
correction. The pre-registered decoy bar (> 0.35) **FAILED everywhere,
including the controls that self-address by word decode** — an internal
contradiction that meant the GATE CONSTANT was broken, not the data. The
true minimum is **d = 27 EXACTLY** (exhaustive Gray walk over all 262,143
nonzero counter XORs; spectrum 27:3, 28:8, 31:119, 32:247), and it is
physically reachable — one tile ROW down is d = 27. The measured decoy
band 0.257–0.342 brackets the d = 27 prediction 0.267–0.293 at working
BERs. **The rival-bar margin above the floor is 0.07, not 0.12.**
**Why it is in this inventory.** It is the record's cleanest instance of
condition (4)'s corollary: a bar invented above what the code's algebra
permits will fail on good data. Any additive placement tool's rival bar
must be set from the spectrum, not from a round number.
**Priority.** — (law, not a tool).

### 4.7 Certified refinement (forward, decode-gated)
**What.** Re-fit a window's pose using exact printed cells reconstructed
from prior certificates as labels, adopt only on held-out improvement
without furniture regression, and re-attempt the residue at the refined
pose.
**Measured.** RECEIVE-DESIGN §7; experiments/024 (QUALIFICATION.md,
README §7.1); DONE-GEOMETRY §8a. **On its own footing it is the measured
winner of a 2×2 factorial**: own-branch decimated **757 → 759** (+2),
own-branch native **757 → 762** (+5), merged own-branch union **772
(+2 over the 770 generation-zero union)**; union-seeded decimated
**770 → 772**. Every one of the eight arms: **wrong / lost / changed
certificates 0 / 0 / 0**, each reaching a no-new-certificate fixed point
in generation 2. Bounds are tight by design — **±0.15° and ±0.25 cell,
coarse-to-fine**, with page, orientation, integer origin, BCH result and
audited core all frozen, and the generation-zero detector path replayed
exactly. **Where it lost — and this is the load-bearing number for a
toolbox: after the E023c scale cascade the return collapses.** C3 after
the cascade: **0 gain** for 24 accepted revisions / 250,806 changed cells
/ 58 CRC calls / 12,180 BP iterations. C2 after the cascade: **+1 useful
tile** for 102 accepted revisions / 1,696,545 changed cells / 461 CRC
calls / 96,682 BP iterations. Standalone C2 "gained" 7 LDPC certificates
that were **all outside the fountain domain — +0 useful**. The e024 log's
own conclusion: "E023c performs most of the recoverable work here, and
broad affine feedback after it has sharply diminishing return… the
evidence favours **bounded seam-aware piecewise pose and explicit support
revision** over another indiscriminate global feedback pass". Also
refused: the BACKWARD fixed-point (RECEIVE-DESIGN §7, "negligible benefit
at substantial cost"). On the e029 c2 ink page the DONE-GEOMETRY census
found refine lanes are the only lanes the done gate never touches
(r00–r03 = 0), i.e. refine work is by construction aimed at uncertified
material.
**Additive:** yes — a refined pose is an extra attempt; the original
placement remains when adoption fails ("otherwise the original placement
remains").
**Cost.** One resample of the windows whose sampling transform changed
plus a re-run of regional context; refine is a lane, priced like a lane.
**Prereq.** certified labels (so it is worthless on lane 0), committed
poses.
**holo2.** Wants the certificate carry and the per-window job; must not
mutate committed poses of other windows.
**Priority.** A **where the cascade has not already run**; **C as a
post-cascade pass** — the measured post-E023c yield is 0 and 1 tile at
tens of thousands of BP iterations, which is exactly the kind of
cost-per-certificate a learned scheduler should demote automatically
rather than a human deleting the tool.

### 4.8 Per-window pose refinement, plane-common affine (avenue D)
**What.** Widen certified refinement's model from translation-ish bounds
to a full plane-COMMON local affine per window, decode-gated.
**Measured.** INDEPENDENT-PLANES §2.4 (2026-08-23): the supervised
per-window Jacobian is the ONLY dof that won a certificate the translation
did not — **page-corner tile (0,0)/C, 11.95% → 4.97% cell error,
certified**. The Jacobian is plane-COMMON (Y's scale_y deviates from the
C/M mean with sd 0.024% against a 0.274% common term, ×11; rotation and
shear never exceed 0.07°), so this belongs to the shared pose and not to a
per-plane field. **Where it lost:** value is concentrated where the shared
pose extrapolates worst — page edges, stitched windows — a small
population; and §2.11 measured the per-window local affine against
translation-only in the DECODE and found them indistinguishable
(14.65% vs 14.67% cell BER, **0 certificates either way**), even though
the affine wins 77–80% of windows on leave-one-site-out prediction error
(0.27 → 0.23 dot, median edge displacement 0.24–0.30 dot).
**Parked because.** The certified-probe ROUTE into it is a measured
negative (§4.6 below); what survives is the original form: a pose
improvement selected by a DECODE-gated objective, never by an NCC
residual (INDEPENDENT-PLANES §4.D).
**Additive:** yes — one more candidate pose per window, gated by the
decode.
**Cost.** UNMEASURED as a widened search; the existing refine grids
(0.15°, 0.25 cells) are the cost anchor.
**Prereq.** certified labels; a bounds/model change in the placement
layer.
**holo2.** Placement-layer only; must not read or write field state.
**Priority.** B — one measured certificate, tiny population, and the
population is nameable in advance (corners, edges, stitched windows),
which makes it cheap to schedule narrowly.

### 4.9 Certified-footprint deprioritization (address-space)
**What.** Deprioritize — never skip — windows whose predicted page
footprint lands entirely on certified tiles.
**Measured.** PLACEMENT-IMPROVEMENTS §1.4. NOT BUILT ("needs cross-lane
certificate context at ADDRESS"). Superseded in concept by DONE-GEOMETRY,
which inverts the projection direction and gets an EXACT, pose-free test
instead of a prediction (DONE-GEOMETRY §2).
**Additive:** scheduling only. **Priority.** D — subsumed; build §9.4
instead.

### 4.10 Pose writer from certified probes (COMPOSITE-POSE writer (b))
**What.** Every certified probe splits into a per-plane part and a part
all three planes share; feed the shared part back as a correction to that
window's committed pose.
**Measured.** INDEPENDENT-PLANES §2.11 (2026-08-23), over **all 334 open
(tile, stream) slots** of the sheet-I W6 state, three 2400 dpi captures
unioned, on BOTH a frozen-detector and an E1-refit footing. The residual
is real and self-consistent: quality-weighted magnitude median
**0.174 / 0.173 / 0.181 dot**, p90 0.30–0.33, max 0.87–1.20; and the sign
check is clean — translating each window's pose by its own estimate
collapses the residual **0.174 → 0.0019 dot, reduced in 100% of windows,
all three captures**. And the decode says no: pre-registered bar ≥ 5 slots
beyond the field-only arm or ≥ 0.5 pp dead-band BER reduction; measured
**−1 slot and −1.75 pp (frozen), −5 slots and −2.13 pp (refit)** —
**FAILED on both clauses, in the wrong direction**; on the refit footing
the pose arm loses all five slots the field arm won and returns none.
The damage is LINEAR in the correction: **+9.55 pp per dot** (frozen,
r +0.44), **+9.27 pp per dot** (refit), zero crossing at the origin — and
worst exactly where the writer's evidence is best (over the 72 slots whose
covering windows are self-consistent: 13.79% → 17.29%, +3.50 pp).
**Why.** Two measured mechanisms: the field is already fed each plane's
FULL local offset and absorbs a quarter to three quarters of the
plane-common residual (regression slope 0.25–0.75 by axis and capture,
correlation 0.42–0.72), so a writer stacked on it double-counts; removing
the double-count by construction (the differential arms) cuts the harm by
about two thirds and never reaches the baseline. The underlying reason is
in COMPOSITE-POSE-DESIGN §6: NCC magnitudes are calibrated to
DECODE-OPTIMAL rather than physical offsets, and that calibration error
CANCELS between planes (differential use survives) and does not cancel in
plane-common use.
**Additive:** **needs union-of-attempts.** The measurement is explicit
that it tested a REPLACEMENT. As a tool — "also sample this window at
committed-pose + residual, and attempt" — it is untested, and the numbers
say what to expect: at the 0.174-dot median it would mostly fail, and it
would cost one extra attempt per slot to find the few where it does not.
**Cost.** The probe pass is already paid (§8.3); applying and attempting
is one extra sampling + decode per residue slot in the covered windows.
**Prereq.** the probe pass; a sampling seam that accepts a per-window
override without writing it back.
**holo2.** Must not write `PoseRecord`; it is an attempt-time override
only. That is exactly the isolation §2.9c's three-layer pose regression
already pins in holo1.
**Priority.** C — cheap to try as a pure attempt, measured hostile as a
write. Do not resurrect the writer form.

### 4.11 Seam-aware piecewise pose + explicit support revision
**What.** Learn a capture-local seam-likelihood field from straddle cuts,
held-out pilot residuals, between-window pose residuals and certified
labels; split only CROSSING windows into at most two supported children;
fit and gate an independent bounded local pose per side; re-admit
censored cells only through an explicit versioned support extension.
**Measured.** experiments/024 FURTHER-WORK-PERIODIC-SEAMS.md.
**UNMEASURED as a mechanism** — but the residue it targets is measured
and is strikingly non-random: on the native HP-1200 c2 scan (~4 px/cell)
pilot acquisition collapses **approximately every sixth 60-cell pilot row
= a 360-cell cadence = 720 printer dots = 1,440 scan pixels = 30.48 mm**,
payload failures form near-solid horizontal bands at the same cadence,
**101 of 449 accepted placements were cut by the existing straddle
audit**, and the Canon-4800 scan of the SAME print certifies 1,815 of
1,819 nondegenerate tiles while all 782 HP certificates are a strict
subset of the Canon ones. The c3 take at ~6 px/cell degrades less at
corresponding heights. Errors are approximately symmetric between bit
directions — "more consistent with phase, blur, or piecewise geometry
than with a simple detector-threshold bias".
**Attribution is OPEN and the log insists on it:** do NOT hard-code the
cadence or identify it with the known 18.63 mm CCD comb or the stochastic
transport steps without measurement; four attribution experiments are
pre-registered (translated and 180°-rotated rescans, exact 4×4
box-average of the 4800 to 1200, original TIFF strip metadata, a
noncommensurately shifted diagnostic reprint).
**Additive:** yes — extra child poses, gated as usual; the support
revision half is evidence-level and needs its own version.
**Cost.** UNMEASURED. It splits only crossing windows, so it is bounded
by the straddle population (101/449 on that capture).
**Prereq.** the attribution experiments; a support-extension record.
**holo2.** Subdivision already exists as the growth mechanism; this is a
seam-INFORMED subdivision plus a per-side pose, so the machinery is
mostly there. It must not silently reinterpret an existing audited core.
**Priority.** B — the e024 record names it the successor to global
feedback ("the next mechanism with a distinct error model and
identifiable value"), and its target population is measured and large.

### 4.12 Backward fixed-point / arbitrary revision loop (E024 form)
**What.** Iterate placement and payload to a fixed point, revising earlier
decisions.
**Measured.** RECEIVE-DESIGN §7: "the experiments measured negligible
benefit at substantial cost". State seams for a future separately designed
pass are preserved.
**Additive:** no — revision is the opposite of additive, and §6.3's
per-address retirement law forbids frontier rollback.
**Priority.** D — record only.

---

## 5. Sampling geometry

### 5.1 Translation swim — per-plane 1-D closer, decode-gated
**What.** For one residue (tile, plane), search a small set of per-plane
translation candidates and attempt the decode at each; the certificate is
the sole acceptance.
**Measured.** INDEPENDENT-PLANES §2.3 (2026-08-22, sheet I, 10 residue
targets + 2 reproduction controls). **The mechanism is proven:** the two
controls — certified tiles presented as residue with only their Y
certificate withheld — FAIL at δ = 0 and **CERTIFY under per-plane
translation**, with real certificate ids and good CRC, and the certified
band-3 grid steps are **0.25 dot wide**. **Where it lost:** the residue is
**0 of 10 at ANY of 85 candidate offsets** (17 in x, 68 in x,y), under
neighbour-derived, own-furniture or swim estimates. Ground truth says why:
translation takes the dead band from **17.5% → 10.8%** cell error against
a gate at ~7.6% — still 1.3–1.8× above it — and the full supervised
affine only reaches 9.70% (§2.4). SCOPE caveat: only the FAILING plane was
swum; a joint three-plane wiggle was never run, and C/M per-channel word
decode was never exercised.
**Cost.** ~100 s setup per capture, **~0.8 s per candidate**; a
hint-seeded 1-D closer **≈ 4 s/tile** ⇒ ~20 min for a whole sheet
(§2.3). With a field hint the blind 2-D search shrinks ~170 → ~9
candidates (PLANE-FIELDS §2 beat 16).
**Additive:** **yes** — this is the canonical box tool. Failed searches
change nothing; the certificate gate is "immune to the multiple-testing
scale, monotone by construction" (PLANE-FIELDS §2 beat 16).
**Prereq.** a sampling seam that takes a per-plane offset override; a
calibrated detector (the oracle cannot gate its way out of uncalibrated
LLRs — beat 18); a field or neighbour hint to centre the search.
**holo2.** Needs: per-slot job scheduling, an offsets override at
sampling, certificate commit. Must not: write poses, write the field
before the certificate lands (successful swim offsets are tier-(i) field
evidence AFTER the fact).
**Priority.** A for K/C/M and for scrap rescue; **B for sheet-I-class dead
Y**, where the ceiling says it cannot reach. The honest reading of §2.3 is
that the closer is a general-purpose tool that this particular residue is
out of range of — not a failed tool.

### 5.2 Refit at corrected geometry (recut bins)
**What.** After moving a tile's sampling geometry, re-fit the registration,
the detector and the context bins at the NEW geometry instead of reusing
bins cut at δ = 0.
**Measured.** INDEPENDENT-PLANES §2.8 E1 (2026-08-22, union of 3 captures,
ground truth): dead tiles **−0.96 pp** (sd 0.50, 6/6 tiles, 24/24 rows
same sign) against controls −0.26 pp; the dead−control gap **2.85 → 2.15
pp** — ~25% of it was frozen-fit artifact, 75% is not. **Dead-band tile
(29,8) CERTIFIES under the refit** (syndrome + CRC ok, ordinary union
stage, 99 iterations, 331 → 312 wrong cells). **Where it lost:** this is
the supervised CEILING moving, not a receiver; and it re-inverted the
gate interval a third time (certified at 7.85% while another tile failed
at 7.70%).
**Additive:** yes — a refit produces a different attempt at the same slot.
**Cost.** Substantial: E1-class refits ran 33 min / peak 13.2 GB for a
restricted region over three captures (§2.8 P2); E4's per-tile refits ran
62 min / 14.8 GB for eight tiles × three captures (§2.10). A production
form would refit ONCE per capture per geometry family, which is what
E8's G2 did ("ONE refit per capture serves all eight tiles because the
field is tile-blind", §2.12).
**Prereq.** a geometry change worth refitting for; the seam that lets a
refit see the corrected sampling.
**holo2.** Wants a per-region detector fit that can be re-run over an
overridden geometry, isolated from the committed evidence blocks.
**Priority.** B — real, sign-consistent, and its cost is the reason to
schedule it per-capture rather than per-tile.

### 5.3 Footing upgrade (px/cell) as a tool
**What.** Add a capture at a finer native footing, or run an existing
capture at a finer px/cell rung.
**Measured.** INDEPENDENT-PLANES §2.2 run 2: adding a 4800 dpi capture to
the sheet-I state took certificates 5,549 → **+90** (5,639/5,883 slots)
and produced the **first Y adoption** of the field (Y rms 0.441 dot,
coverage 99.6%). §3.4: "More resolution does not fill the bands … Same-
footing repeat scans are print-frozen; **footing UPGRADES still pay.**"
The 018 operational rule and CLAUDE.md's channel facts agree from the
other side: 8 px/dot roughly halves BER vs 2 px/dot on the Canon.
**Where it lost:** the bands persist; and run 2 is CONFOUNDED (16 px/cell
footing AND a 5,164-certificate prior state changed together), so it
corroborates rather than scores the registered 4800 mechanism run.
**Additive:** yes — a new capture is new evidence and its attempts union.
**Cost.** A scan and a whole lane; the most expensive tool in the box.
**Prereq.** physical access to the sheet (or an archived finer scan).
**Priority.** B — high yield per capture, but it is not schedulable
compute; it is an operator action.

### 5.4 Multi-scan union and the aperture asymmetry
**What.** Decode the same sheet from several captures and union the
certificates; and keep BOTH the coarse (decimated) and fine (native)
apertures, because they certify different tiles.
**Measured.** PLACEMENT-IMPROVEMENTS §1.4a, all uncensored measurements:
coarse-only **15/671 C3** and **19/1310 C2** (5 fountain-useful) vs
fine-only standalone; the 2→6 endpoint control shows the finest lane
genuinely attempting and LOSING 7 tiles the 3-ppc lane certifies; E023b
multiview **decimated-only 17 vs native-only 12 of a 769 union**.
Mechanism on record: the decimation aperture improves photometry
(**pair-matched PAVA BER 1.80% decimated vs 2.41% native over 6.0M
cells**), coarse geometry accepts more placements on intact sheets, and
LDPC/BP nonlinearity clusters exclusive tiles in row bands. CLAUDE.md's
multi-scan law (F1∘F6, replicated 3×): equal-weight COMBINING loses to
best-single on a global detector, and WINS after the ctx detector
de-correlates context bias; re-place the sheet between scans; **3–4
scans/sheet is the knee**; never double-count a raw capture and its own
decimation in one state.
**Where it lost:** sample-level multi-capture FUSION is "Not pursued" —
the print-frozen floor caps the gain at the scan-noise share and the union
has most of it (INDEPENDENT-PLANES §4.K).
**Additive:** yes, by construction — this IS the union-of-attempts
pattern, already law.
**Cost.** one lane set per capture.
**Priority.** — (already had); listed because the box's composition rule
is this law generalized. Re-placement between scans is now ALSO the
identifiability doctrine (COMPOSITE-POSE-DESIGN §5).

### 5.5 Multi-footing baseline restoration
**What.** When a configuration change re-times the cascade and strands
addresses that the old configuration certified at a COARSER rung, restore
the old configuration at THAT rung, not only at the finest.
**Measured.** COLOR-UPLIFT-MEASUREMENTS §11.11 (2026-08-09): of six
stranded addresses, the two on xerox c3-cmy7 were lost purely to FOOTING
(certified by the baseline at **6 ppc** and **4 ppc**, while the
supplemental form binds to the finest rung, 12 ppc). "**Multi-footing
u-off — one baseline lane per rung, or one bound to the rung the address
was lost from — is the named next candidate, deferred by ruling.**"
**Where it lost:** UNMEASURED as built; the other three misses are HISTORY
(frontier growth), which no schedulable lane can undo.
**Additive:** yes.
**Cost.** one supplemental lane per rung over the residue — the residue
price, per rung.
**Prereq.** a supplemental-lane mechanism bound to a chosen rung.
**Priority.** B — 2 measured addresses on one corpus, at a lane's price;
the general form ("restore any displaced configuration at its own
footing") is what makes an additive box safe against re-timing.

### 5.6 Retained geometry × sampler hypothesis list on the unresolved tail
**What.** Instead of averaging views or freezing one globally preferred
sampler, keep a tiny CRC-gated list of (geometry, sampler) hypotheses and
run them on the unresolved tail only.
**Measured.** experiments/024 README §10 (E024.3) — the arm itself is
**UNMEASURED**, but the evidence behind it is not. The four-lane
NN/DD/ND/DN resampling factorial measured **NN 752 / DD 757 / ND 749 /
DN 756, all-four union 772 — three correct tiles beyond the 769 two-view
baseline** at "4,470 CRC calls and 242,555 BP iterations, about twice
NN+DD". The structure of that result is the recommendation: **box3
geometry is better under both samplers** (so geometry dominates), while
**DN has the lowest BER, DD the best single-lane count, and ND retains
one unique tile** — sampler choice still has local interactions. Named
order for the tail: "DN then ND".
**Where it lost:** as a full factorial it doubles the work for 3 tiles;
the four-lane report is also DEMOTED as a qualification artifact (legacy
pre-E021.6 footings, no packed per-tile rows).
**Additive:** yes — extra sampling hypotheses, certificate-gated.
**Cost.** measured at full factorial: ~2× the two-view cost for +3.
Restricted to the unresolved tail it is far less, UNMEASURED.
**Prereq.** the tail (so, late scheduling); a sampler switch at the
sampling seam.
**Priority.** B — 3 measured certificates, and the restriction that makes
it cheap (tail only) is exactly what the box does natively.

### 5.7 The intermediate scale rung
**What.** Insert a middle footing in the coarse-to-fine ladder rather
than jumping from coarsest to finest.
**Measured.** e023c. Same code, same source, same policy: the 2 → 6
ENDPOINT control reaches **747 correct certificates** (1,056 CRC calls,
69,613 BP iterations, 1,171 attempt records) from an identical
671-certificate coarse anchor; the automatic 2 → 3 → 6 ladder is a
**strict superset — seven correct additions, no loss, no bit conflict** —
at **+11.0% CRC calls, +33.5% BP iterations, +12.8% attempt records**.
**Where it lost:** nothing; the recorded limit is only that it does not
prove 2 → 3 → 6 globally optimal.
**Additive:** yes, and measured as a strict superset — the cleanest
example in the record of a tool that pays for itself under the box's own
bar.
**Cost.** ~+11–34% of the cascade's decode work for +7 tiles.
**holo2.** Footing is already a PRICE rather than a gate, so extra rungs
are a recipe question, not a scheduler question.
**Priority.** A — measured strict superset at a known, modest price.

---

## 6. Calibration & detector

### 6.1 The context (ctx) detector — and the sampling law that governs it
**What.** Condition the ink/white decision on the cell's neighbourhood
context instead of on a global bimodal threshold, undoing the
development-driven white-closure bias.
**Measured.** experiments/014 §014.2. The largest detector lever in the
record: window BER **7.89% (baseline) → 7.10% (flattened, global) →
1.93% with ctx = "the lever: ~3.5× on every scan"**; wired-path
replication across three scans **2.58 / 2.42 / 2.20%**. Discriminating
tests: context-structured continuum damage **6.84% → 3.67%**; i.i.d.
flips give exact ctx/global parity (no gain, by construction); within-
class bimodal damage defeats it (terminal closures are unrecoverable).
The error taxonomy it attacks: of 6,899 errant cells, **53% white-closure
false alarms** (fully-surrounded whites close at 98.7%, open whites at
0.0%), 38% ink erosion.
**Where it lost — and this is a LAW for the box, not a footnote.** The
ctx gain is **SAMPLING-dependent, not engine-dependent**: 3.5× at
16 px/cell, **~nil at 8 px/cell** on the c3 footing (experiments/018
branch record), and the original "ctx rescue fails on the AltaLink"
verdict was a 2 px/dot artifact. **Any detector-class tool in the box
must carry its px/cell regime as part of its identity**, and the
scheduler must be allowed to learn that a tool is worthless at one
footing and decisive at another.
**Additive:** evidence-level — it changes what the attempt reads.
**Status.** ADOPTED, hard-wired in production.
**Priority.** — (already had); the regime law is the transferable part.

### 6.2 Mask-aware context detection for scraps
**What.** Give the z-normalization, the class fit and the context
re-estimation an explicit validity mask, so backing pixels around a scrap
never enter the statistics and a cell without a complete on-mask
neighbourhood is not context-corrected.
**Measured.** PILOTS-DESIGN §15.9 + experiments/018 branch record
(branch `pilot-first-receiver`, NOT MERGED). **It works as a detector:**
on a backing-polluted grid (4,900 core cells against ~14,700 backing
cells sitting dead-centre between the classes) naive context is driven to
a coin flip (BER > 0.30) while mask-aware context recovers below 0.20 and
never loses to blind. **It is not the confetti lever:** the real-scan A/B
reads **ctx+PAVA 35 certified against recal's 35 — gains 3 tiles, loses
3**, and the per-window BER move 0.224 → 0.214 is the PAVA-vs-Gaussian
calibration, not a context gain. Worse, the means grid the context stage
REQUIRES regressed placement **42 → 35** and introduced a wrong-placement
poison. Mechanism of the null: the 8 px/cell footing (see 6.1).
**Where the gap actually is:** upstream — whole-window sub-cell phase
lock produces cleaner means than correlation placement plus point
sampling on the same piece (**0.035 vs 0.09**); the word path read 110
against the pilot-first path's 35. "**Sampling/lock quality is the next
lever, not the detector.**"
**Status.** In holo the protection was RE-DERIVED rather than ported: any
cell lacking a complete 8-neighbourhood is marked context-invalid
(bin −1) — "structurally stronger than a mask argument — holo's detector
never sees a dense grid containing backing". **OPEN and explicitly not a
claim: the colour/QDA path was never audited for backing exposure.**
**Additive:** evidence-level.
**Priority.** D as a yield tool at 8 px/cell; **B as an audit** — the
colour path's backing exposure is unexamined and cheap to check.

### 6.3 The bounded-LLR invariant (calibrate or bound, never raw)
**What.** No raw detector score crosses an API boundary: every emitted
LLR is either calibrated or rescaled into the calibrated range.
**Measured.** experiments/018 §018.7. The defect: a label-count gate let
uncalibrated scores through whenever a window decoded few pilot tiles —
raw scores reach **~5e5** against a calibrated ceiling of ~6.8, a
**~70,000× voice imbalance**, and **it self-selects for garbage** (drift →
fewer decodes → fewer labels → uncalibrated → the worst windows shout
loudest). Measured combined |LLR| max **692,895**. The fix (lower the
label floor to 60, where the isotonic clamp makes small maps
self-limiting, and rescale below it under a hard cap): **181 → 190
symbols (+9), certified 188 → 197, |LLR| max 692,895 → 22.9**. The gain
distribution confirms the mechanism — neutral on a single scan
(magnitude is irrelevant to a sign), **+8/+8/+9 once the union
combines**. An interim combine-side clip that bought +7 tiles was
**RETIRED as symptom-hiding**.
**Why it is in this inventory.** A box of N tools all writing evidence
into one union is exactly the configuration this bug exploited. **The
invariant is a precondition of the box, not a tool.**
**Priority.** — (invariant; already law in holo).

### 6.4 Dense certified-label re-derivation ("repass"), and its trust gating
**What.** Use certified tiles as dense truth labels (~40× pilot density)
to refit a window's geometry and detector, re-sample from the original
glass, gate, supersede at cell granularity, and iterate to a fixed point.
**Measured.** experiments/018 §018.6 and §018.8. **v1, gated to
correlation-placed pieces: fixture +2 conversions; REAL STATE 0.** Not a
correctness failure — a **regime mismatch**: the anchor-graph word path
had become so strong (10/10 tiled, 0 placed) that it structurally starved
v1's clientele. **v1.1-a, un-gated to word-path pieces by EXCLUSION
rather than inclusion** (word evidence is higher-trust where it certified
and measured-bad inside failed tiles, so supersede there and only there):
**197 → 216 certified tiles (+19), 190 → 208 symbols (+18), fixed point
at round 3, 0 wrong in 850,177 GT-audited certified cells**, reproduced
identically on a live state. **v1 on that same regime converted 0 — the
un-gating IS the yield.** The exclusion form also frees never-observed
gap cells (6 low-coverage page-edge tiles gained first coverage), though
gap coverage alone converted nothing yet.
**Where it lost:** cost — it re-segments every piece every round,
O(rounds × scans × pieces), ~15 min for 3 rounds × 4 scans; the
failed-piece retry path fired 0 times (segmentation is deterministic, so
a driver-failed piece re-fails); and its scope is explicit: "**a
per-scan-set margin extractor, not a volume-closer**" — the deficit
exceeded any refit pool, and coverage is the volume lever. Also: the
synthetic fixture CANNOT host the conversion bar (calibration removes
every uniform degradation; within-window drift does not exist in a rigid
render), so this arm can only be measured on real captures.
**Additive:** needs union-of-attempts in principle (it supersedes an
evidence value) — but the record's own resolution is the additive one:
supersede only inside FAILED tiles, protect the certified cells, and the
result is monotone. That is condition (1), discovered independently.
**Prereq.** certified labels; a per-cell supersession record; **and the
label-pairing correctness the log had to fix — dense labels were once
paired in the wrong raster order, ~49% mislabeled, and the conversions
before the fix "had come from the geometry refit alone"**.
**holo2.** L6 (no self-training) permits this exactly as written: labels
come from prior commits. CA1's certified-label enrichment is the holo2
analogue and is **BUILT and DIALLED OFF at +68% cost / zero yield** —
which is a different regime, not a refutation, and is worth re-measuring
under the exclusion form.
**Priority.** A on scrap/multi-scan material (+19 tiles, 0 wrong,
measured on a real state); C on intact single-capture sheets.

### 6.5 A3 — per-window photometric maps
**What.** Fit a per-RGB-channel gain+offset per window toward the region
model's class means on that window's own labelled cells, and read the
window's payload through it.
**Measured.** COLOR-UPLIFT-MEASUREMENTS §5–§7, §10. **Ladder-side, on the
capture it was built for (hp c3-cmy8): +46 (C 620 → 667) at PK4, and a
floor-0 harvest of +73 gained / 11 lost = +62.** Halo axis monotone
(**+14.7 / +9.0 / +5.7 addresses for halo weight 0.25 / 0.5 / 1.0, and
own-window-only +27** on the same unit) — a neighbour's cells are
evidence about the NEIGHBOUR's photometry. **Residue-side, as a
supplemental lane: +6 on hp c3-cmy8, +7 on xerox c2-cmy8, 0 on xerox
c3-cmy7, every one of them a NEW address (`re_timed = 0`).**
**Where it lost.** At 2 ppc it COSTS certificates, cleanly attributable:
the first barrier reads **329 against 333** with the arm as the only
difference. It lost 2 addresses against the archived set, both at page
column 0. It **can fire on noise alone** — on a null twin with zero
gradient, 13/64 windows accepted at noise std 0.22 and 22/64 at 0.30,
both gates adopting. It moved another arm's swept floor onto measurement
noise. Peak RSS **+34–37%** on both cmy8 captures. And **two successive
applicability floors failed to separate help from harm** — the raw
dispersion floor (the damaging lane carries the corpus MAXIMUM while the
lane it helps most is near the bottom) and the normalized variance ratio
(**refusing every harm lane needs > 31.12; keeping every help lane needs
≤ 2.09 — contradictory by 15×**). Both RETIRED.
**Resolution.** The arm is **override-only and scheduled**, not gated:
"its LADDER-side gain waits for the payload→raw-pixel channel model…
and its RESIDUE-side gain is claimable now through its u-lane".
**This is the single clearest precedent for the whole toolbox.**
**Additive:** yes, in the u-lane form.
**Cost.** CPU flat (one extra fit per window); the lane costs what a
residue costs (~300–350 s wall per lane on these captures); memory is the
real price.
**Priority.** A in the residue form (measured, monotone, cheap-ish);
D as a ladder default.

### 6.6 A4 — the cmy7 calibrated head with a deployment-population floor
**What.** A scalar-temperature + per-offset head fitted on held-out
scores, applied only where the region's own deployment population
saturates the LLR bound at ≥30% pre-head.
**Measured.** COLOR-UPLIFT-MEASUREMENTS §4.5.1/§4.5.2: **734 against the
archived 720 — +14 gained, 0 lost, a strict SUPERSET.** The floor is
load-bearing: the held-out furniture gate alone was measured adopting
into a lane the head strictly loses.
**Where it lost:** the floor's value is not robust — A3 lowers the
pre-head saturation in every lane and flipped one lane's verdict, so
"the two arms are not independent and the floor is now perched on
measurement noise".
**Additive:** yes as measured (strict superset).
**Priority.** — (adopted). The transferable lesson is that a
DEPLOYMENT-population gate worked where two FIT-population gates failed.

### 6.7 A4b — KnownField-conditioned marginalization
**What.** Restrict a cell's state marginalization to the subset
consistent with certified SIBLING planes.
**Measured.** COLOR-UPLIFT-MEASUREMENTS §9–§10. **Ladder-side: an exact
end-to-end null on the uplift target (663 cert-for-cert, even under
maximal conditioning) and net −5 on xerox c2-cmy8** (5 gained, 10 lost,
nine at the finest lane); the "+19" a two-lane library sweep measured
decomposed into 1 new address and 18 re-timings. **Residue-side, forced
in its own lane: +1 M on hp c3-cmy8 and +2 on xerox c2-cmy8** —
6,324,708 arity-1 and 176,666 arity-2 marginals conditioned to convert
one tile.
**Where it lost and why:** the cost concentrates in exactly the strata
fed by cert-cross material, and severity scales with how SELECTIVE the
certification was (conditioning on the easiest 3% of a page vs 64%); a
material SIZE floor cannot separate them because on one capture the
harmful strata are the material-rich ones. The named next candidate — a
cert-versus-masked BALANCE rule — is **not sweepable from this corpus**.
**A registered compromise that the box inherits:** cert-cross strata are
selection-biased toward clean tiles while deployment targets are the hard
remainder; the masked-furniture floor is the spatially unbiased
mitigation.
**Additive:** yes in the lane form. **Cost:** ~350 s wall per lane; a
single-stream coding has nothing to condition on and its lane is a
measured guaranteed zero (98 blocks / 185 attempts / 0 certificates /
70 s), which is why the plan filters it per coding.
**Priority.** C — 3 certificates corpus-wide for two lanes; it earns its
place in a box precisely because a box does not have to justify it
against an incumbent, but a cost-ordered scheduler should rank it last.

### 6.8 A5 — the multi-state context matrix (the campaign's largest move)
**What.** A monotone 9-bin curve per (state, plane) applied to the QDA's
own state scores — a per-STATE factorization of the neighbourhood
correction.
**Measured.** COLOR-UPLIFT-MEASUREMENTS §11. **hp c3-cmy8 663 → 796
(C 620 → 740, M 43 → 56): +127 gained / 1 lost.** xerox c2-cmy8 +86 with
the close still byte-exact; xerox c3-cmy7 +37. Adopted in all seventeen
lanes. **And it is CHEAPER than the arm-free ladder: −8.6% CPU against
its own force-null, −5.3% and −7.1% on the other captures, with peak RSS
1–1.4 GiB LOWER** — certificates arriving at coarse lanes retire more
retry work than the fit costs. Specimen tier: +16, zero losses.
**Where it lost:** six addresses corpus-wide (2/1/3) certify in the
baseline and not in the candidate, against 255 gained — a 42:1 ratio, and
diagnosed as RE-TIMING (each lost tile was certified by the baseline at a
LATER lane whose residue the candidate changes), not evidence damage. The
discriminating test is owed. **Its yield is concentrated at the COARSEST
rung** (l00 gives +72 / +80 / +410 of the totals), which is why a
supplemental-lane form of it would deliver almost none of the gain.
**Additive:** as measured, no — it is a ladder-wide evidence change. It
becomes additive only with the displaced configuration ALSO scheduled,
which is precisely what the project then did (§9.2).
**Priority.** — (adopted); listed because it is the record's proof that
the largest wins are not residue-side, and a box that only ever runs on
the tail will miss them.

### 6.9 The per-plane K context port (A5's losing arm)
**Measured.** COLOR-UPLIFT-MEASUREMENTS §11.2/§11.4, §12 R7. **An exact
null in 17 of 17 lanes on the uplift target, cert-for-cert, at 8,648 s of
CPU spent to refuse.** Mechanism, and it is the part worth keeping: one
curve per plane is spent on the population that DOMINATES the labels —
83–84% word — so it improves the word leg by .09–.19 nats, damages the
dust leg by .04–.20, and the three-way gate refuses it; the matrix's
per-state factorization serves word and dust at once.
**Priority.** D — record only. The lesson (a correction fitted on a
population that is not the deployment population will trade legs) is the
same one A3's gates taught.

### 6.10 Iterative demapping inside one attempt (cmy7)
**What.** Let the joint pack demapper and the frame decoder exchange
extrinsics up to three times INSIDE one attempt, stopping at the CRC.
**Measured.** COLOR-UPLIFT-MEASUREMENTS §13. Simulation: **p\* 0.015 →
0.0225 (2 iterations) → 0.0275 (3)**, with every tested p at or above
baseline in tiles-CRC (+1, 0, +105, +322, +454, +478, +477, +268). Paper:
**xerox c3-cmy7 771 → 810, +39 gained, ZERO lost, strict SUPERSET**, and
**39 of the 69 standing uncertified tiles = 56.5% of the tail**; an exact
no-op on both cmy8 captures, asserted not assumed.
**Where it lost:** cost — **+21% wall and +45% CPU** on the real capture,
because the receiver's payload work is dominated by tiles that FAIL and a
failing tile now pays up to three inner decodes; the sim's worst case is
+148% BP work at a p where every tile fails anyway. Marginal cost per
certificate is flat (22.5 s vs 19.9 s each), so 3 is where a bar sat, not
a knee. **And it raises the per-attempt CRC exposure from one to three on
the same denominator** — registered, with the wrong-certificate audit as
its only guard.
**Additive:** yes — the CRC stop means a tile that certifies immediately
pays nothing.
**Priority.** A for its coding; and it is the box's clearest cost model —
self-limiting, priced per certificate, exposure-multiplying.

### 6.11 Margin-gated pack erasure — MEASURED NEGATIVE
**Measured.** COLOR-UPLIFT-MEASUREMENTS §13.3. **B8 NOT MET on both
clauses: 0/20 all-pass at the bar point and 365/480 = thirty-six tiles
BELOW baseline**; in combination with iteration it is negative
(grid CRC total 788 → 651). Mechanism: pack semantics are
all-or-nothing, so erasing one low-margin slot costs eleven code bits to
save one cell, and iteration re-reads that slot from its ten siblings
instead of discarding them. RETIRED the day it was measured; the margin
primitive survives.
**Priority.** D — record only. (Note the contrast with 5.x's union
erasure split, where erasure is the RIGHT currency because the cells are
independent.)

### 6.12 Per-state / stratum-exact thresholds and the head's own deficit
**What.** Correct the detector per (C, M) state rather than marginally.
**Measured.** INDEPENDENT-PLANES §2.8 E3 and §2.10 E3′. E3 measured a
per-state (C,M)-conditional threshold worth **~4.0 pp (dead) / 5.1
(controls) / 4.5 (references)** — and that claim was **RETRACTED as a
lever**: the baseline it beat is a single threshold the production head
does not use. E3′ then priced the shipped head against a per-stratum
oracle and the head **WINS at every band** (−3.84 / −5.25 / −6.34 pp).
The real deficit is confined to three states — **011 (MY), 111 (CMY) and
marginally 101 (CY) — which carry 58.8% of the dead tiles' Y errors on
37.5% of their cells**; putting exactly those three at their own oracle
rate is worth **−1.68 pp (dead) / −1.13 (control) / −0.20 (reference) per
capture, arithmetic on the table, not a decode**. The thin-label premise
was falsified: every state is fitted on **117,054–138,365 labels**, so
the shrinkage term is inert (a_k 3.6–4.3e-05) — on a 94%-certified sheet
the certified payload feeds every Y-bearing class.
**Where it lost:** the deficit is present on the controls at half
strength and graded by tile difficulty, not by band membership — it is
not the unattributed 2.15 pp.
**Additive:** evidence-level.
**Cost.** UNMEASURED (no arm exists).
**Priority.** B — a named, measured, state-localized 1.7 pp with no arm
built for it.

### 6.13 Local vs page-global calibration ("E9") — NOW MEASURED
*(this entry read UNMEASURED at v0.1; the K instance was measured
2026-08-23, INDEPENDENT-PLANES §2.13, `measure/calibration/e9_k.py`.)*
**What.** Refit the marginal detector head on a LOCAL label population
— the window containing a residue tile plus a halo — using certified
cells as labels, and re-attempt; with a page-global refit as the control
that separates "local" from "refit at all".
**Measured, K instance.** e029's complete 21-tile residue, two ladder
lanes, arm R reproducing the archived evidence BIT-EXACTLY (72,158 and
74,664 cells). **ZERO certificates, every arm, both lanes, all 21
tiles** — it does not pay under this document's own bar. And the arm
ORDER is `page-global > 2-window halo > 1-window halo > window-only >
incumbent` at both lanes: the global refit is the best arm, at a fifth
of the halo's CPU. Page-wide cell error **5.627 % → 4.922 % (l00) and
2.249 % → 1.849 % (l01)** for one extra fit per lane; mean residue ΔBER
−0.99 / −1.17 pp; 0.7–3.0 s per attempt.
**Where it lost, and why.** The gain lands on the page EDGES (−1.8 to
−2.3 pp at tile column 0) and is almost absent on the development
banding that is 9 of the 21 tiles (−0.26 to −0.37 pp). The fitted
decision threshold makes the cause explicit: the shipped 423-label
per-window head scatters ±0.11–0.13 with **no spatial structure at all**
(|Spearman| ≤ 0.08 on either page axis), and with 900–1300× more labels
the same windows collapse to ±0.012–0.019 around the page-global value,
with the row-42 band reading 0.0015 away from the rest of the page.
The per-window head is not tracking a toner field; it is adding noise
about a page-global one, and banding modulates class SEPARATION rather
than the decision point.
**Additive:** evidence-level (it improves what a later attempt reads);
never `+`.
**Cost.** One PAVA fit per lane in the global form (33–46 s/lane
including re-attempts), against 53–125 s for the halo forms; certified
labels must already exist, so it is a late-frontier tool.
**Prereq.** certified-label projection (`records.printed_cells_from_
record`); note the LLR-bound interaction — a `pava-v1` map's bound is
`log(n_fit + 1)`, which passes `CTX_LLR_CLAMP = 12` once the fit
population exceeds ~163k labels and then makes `WindowEvidence` refuse
context-invalid cells.
**Rename.** What paid is DENSE CERTIFIED LABELS (6.4's mechanism), not
LOCALITY. Read this entry as the page-global-refit item.
**Priority.** **D as a certificate tool** (measured 0/21); **B as
evidence** in the global form — the cheapest page-wide cell-error gain
in this document, unmeasured on colour.
**Owed.** the 8/16 ppc lanes (out of the run's memory budget: ~13 GB and
31 GB peak RSS per lane) and the colour instance.

### 6.14 Blind EM calibration (the dust-obsolescence test)
**What.** Calibrate the 8-state detector without dust exemplars, using
the fact that the payload is keystream-BALANCED over the eight states, so
the mixture is identifiable (words anchor W/CM, absorption structure
labels the rest).
**Measured.** PLANE-FIELDS §2 beat 18. **UNMEASURED**, and explicitly
testable on archived data against dust-seeded calibration; the named risk
case is the collapse regimes (screened mush). Its importance is
structural: "the 8-state detector must calibrate before any LDPC attempt
can converge at any pose — **the oracle cannot gate its way out of
uncalibrated LLRs**". That sentence is a hard constraint on every
oracle-gated tool in this box.
**Additive:** evidence-level.
**Priority.** C as a yield item; **B as insurance** — it is the only
route to a calibrated detector where furniture is absent, which is the
scrap regime.

---

## 7. Context (the neighbourhood model)

### 7.1 The Y-context circularity, priced with an oracle
**What.** A5's context bin for plane Y is built from Y's own PROVISIONAL
decisions — circular exactly where those decisions are worst.
**Measured.** INDEPENDENT-PLANES §2.10 E4 (2026-08-23). Handing the ink
map Y's PRINTED bits is worth **−2.43 pp on the dead tiles** and flips
**three of six dead tiles to CERTIFIED** (joining a fourth) — the largest
detector-side effect the campaign has measured, **2.5× the recut-bins
refit**. The method control is exact: giving C and M their truth
reproduces the baseline to every digit on all eight tiles. Cause: Y's
provisional ink disagrees with the printed field on **5.31–5.49%** of
cells (against C 0.027–0.046% and M exactly 0.000%), and replacing that
one column moves **42–66%** of a target tile's context bins.
**Where it lost:** it closes **NONE** of the dead-vs-control gap — the
controls move −2.45 pp, so the effect is SHEET-WIDE, not band-specific.
And it is an ORACLE: a receiver cannot know Y's printed bits.
**Priority.** — (measurement, not a tool); it sets the ceiling for 7.2.

### 7.2 One fixed-point context iteration (the realizable form)
**What.** Decode, rebuild the neighbourhood ink map from the decoder's
own FINAL decisions, re-decode.
**Measured.** INDEPENDENT-PLANES §2.12 E8 (2026-08-23), nine
configurations at TWO geometries (supervised and production-like), with
(a)/(b) reproducing E4 at max |gap| 0.0. **One iteration is worth −1.07
pp on the dead tiles and −1.57 on the controls = 44% / 64% of the oracle,
and essentially the same at the production-like geometry (−1.06 /
−1.58), with the regression controls moving −0.01 pp — it is not bought
from anywhere.**
**Where it lost:** it fails the pre-registered bar (≥50% of the oracle,
or any dead tile certified at the production geometry) — **no candidate
certifies a single dead tile at G2**, and the one marginal baseline
certificate is LOST at G1 because "the certificate is not monotone in
cell BER". A ~1 pp mean improvement is not the ~3 pp these tiles need.
**Additive:** **needs union-of-attempts** — as measured it REPLACES the
decode. As a tool it is exactly additive: attempt at the incumbent ink
map, then attempt again at the once-iterated one, union the certificates.
**The bar it failed is an adoption bar; under the box's bar it is a
regression-free extra attempt that moves a third to two thirds of a
measured 2.4 pp.**
**Cost.** one extra decode per slot, plus one ink-map rebuild per
capture. E8's own runs: 8,875 s for eight tiles × three captures × nine
configurations at two geometries — but that is an instrument, not the
arm.
**Prereq.** the decoder's final per-cell decisions; a context stage that
accepts an overridden ink column.
**holo2.** CA2 (region context calibration) is live and is the natural
host; the iteration must not write anything (L6: labels from prior
commits only — a within-attempt iteration is inside one attempt, which
the soft-iteration law already permits).
**Priority.** **A** — the single strongest case in this whole inventory
for the box's premise: measured, reproducible at the production geometry,
regression-free, and rejected only by an invented threshold.

### 7.3 Iterating a second time — measured dead end
**Measured.** §2.12: (e2) drops to **25% / 24%** of the oracle at G1 and
**18% / 37%** at G2. It is not converging — the first step moves
18.5–19.9% of the lattice's Y bins and the second still moves
13.8–15.0%. "Hard message passing on a loopy neighbourhood graph with no
damping, behaving exactly as that predicts."
**And the sharpest finding under it: the most ACCURATE ink map is not the
best decode.** (e2)'s column is the closest to truth of all
(**4.70% wrong at G1 and 3.01% at G2 against the baseline's 5.13% /
3.66%**) and decodes WORSE than the one iteration whose column is worse
than the baseline's. What the decoder is sensitive to is a SUM over eight
neighbours, and the error structure of that sum is not a function of the
per-cell hit rate.
**Additive:** yes as a third attempt — and it did keep one marginal
certificate that (e1) lost.
**Priority.** C — cheap as an extra attempt, worthless as a replacement,
and a standing warning against optimizing a proxy.

### 7.4 The soft (posterior-weighted) context column
**Measured.** §2.12 (h): carries the IDENTICAL hard decisions to one
iteration and **ties it — 7.767 vs 7.671 at G1, 9.335 vs 9.318 at G2**,
inside the tile-to-tile spread. The estimator argument says it should win
(a sum of eight MAP decisions is not the MMSE estimate of their sum);
measured, it does not, because **it over-shrinks — it concentrates the
lattice MORE than the oracle does** (bin 4 at 29.1% against the oracle's
27.0% and the baseline's 24.6%). *A one-tile smoke had shown it at
91–101% of the oracle against 63%; that was outcome selection, "recorded
because it is exactly the error the eight-tile set exists to catch".*
**The unbuilt rung the numbers point at:** a **CALIBRATED soft column** —
temperature fitted so the expected count matches the truth's dispersion
instead of over-shrinking — plus a **confidence GATE** (leave low-|LLR|
neighbours at "no valid context" rather than at a half). Both are one
leaf, receiver-axis only, no format change. **UNMEASURED.**
**Priority.** **B** — named, small, and the only remaining lever on the
largest measured detector-side effect.

### 7.5 Consensus context across captures — measured worse
**Measured.** §2.12 (g): a consensus column built from all three
captures' summed post-context LLRs (2.73 M page cells) reaches **36% /
57% of the oracle against one capture's own 44% / 64%**, at both
geometries. "The ink map has to describe THAT capture's neighbourhood
optics; pooling three captures' decisions makes a better estimate of the
PAGE and a worse descriptor of the capture."
**Priority.** D — measured negative, and a useful reminder that not every
quantity pools across captures.

### 7.6 Dropping the self-reference — the sharp negative
**Measured.** §2.12 (f) and (z). Building Y's bin from the count of
neighbours carrying C-or-M ink, with Y's self-reference removed, lands
**on top of switching the neighbourhood term OFF entirely** (+1.72 vs
+1.77 pp on dead tiles; +4.55 vs +4.60 on the references). **The
non-circular model class carries no usable information at all.** The
shipped term is itself worth about −1.8 pp, so no candidate is "winning
by blunting it". **The circularity cannot be removed by dropping the
self-reference — only by estimating it better.**
**Priority.** D — record only, and it closes off the obvious "just make
it non-circular" proposal.

### 7.7 Context-conditional LLR attenuation / erasure treatment
**What.** The detector KNOWS which cells are unreliable and PAVA cannot
express it (one monotone map of the marginal LLR, so a
context-conditional bias survives calibration — signature: "identical
marginal d′, fewer certificates"). LDPC prefers erasures to confident
errors.
**Measured.** INDEPENDENT-PLANES §4.E item (4): **UNBUILT, UNMEASURED
against production.** The supporting facts are measured: errors carry
their own warning (**median |LLR| 1.58 on errant cells vs 4.29 on correct
ones**, experiments/014 §014.2), and on the e018 real state **|LLR| on
wrong cells summed to 2444 against 1580 on right cells** — confidently
wrong, LDPC poison. The union erasure split measured **2.6% erased →
0.98% silent against 1.37% hard** (experiments/014 §014.2 ladder).
**Additive:** evidence-level (it changes the LLRs an attempt reads), so
it must be an extra ATTEMPT with attenuated LLRs beside the plain one.
**Cost.** one extra decode per slot.
**Prereq.** a per-cell reliability signal the detector already has.
**Priority.** **B** — described as "cheap and aligned with the
bounded-LLR invariant", supported by two independent measurements of
confidently-wrong cells, and never built.

### 7.8 An anisotropic context model
**What.** The current cross-plane context is an isotropic 0–8 neighbour
ink COUNT with the own cell excluded; same-cell crosstalk lives only in
the state means, evaluated at three DIFFERENT per-plane sampling
positions. With a 0.7-cell aperture, a 0.5–1.0 dot relative displacement
slides it 36–71% of its width toward one neighbour — **the leakage
becomes anisotropic and neighbour-sourced, which neither term can
express.**
**Measured.** INDEPENDENT-PLANES §2.6 (mechanism READ from the code,
confidence ~95% as a model-class limit, ~60% as the explanation of the
residual gap). The directional stratification test (§2.8 E2) found the
anisotropy REAL — downstream-neighbour C/M ink costs +2.2 pp on dead
tiles, upstream −0.0 — but **present at full strength on the controls
(+2.0), with one control out-splitting four of six dead tiles**. Not
band-specific. Value against PRODUCTION: **UNMEASURED**.
**Additive:** evidence-level.
**Cost.** a detector model-class change with its own qualification.
**Priority.** C — real mechanism, unmeasured lever, and the one item here
whose cost is a qualification rather than compute.

### 7.9 ISI equalization over the 2–3-cell blur support — DEMOTED by measurement
**Measured.** INDEPENDENT-PLANES §3.9, E6 (2026-08-23). The premise was
"Y is optically soft" (structure smears 2–3 cells, peak |r| C 0.771 vs Y
0.57). E6 killed it: on the healthy-toner AltaLink the four inks are one
club — **σ M 37.7 / C 37.3 / K 36.8 / Y 34.8 µm** — while the same code
reads **Y 46.0 / K 39.6 / C 38.1 / M 36.8** on the depleted-cartridge
M281; the stable statistic (Y against its own sheet's K/C/M mean) is
**+7.7/+7.7/+10.5 µm on the M281 and −2.5/−2.2/−3.0 on the AltaLink**.
And blue is the scanner's SHARPEST channel (σ_B 0.937 × σ_G on y,
Δσ² −50.4 ± 8.1 µm², two sheets agreeing at −51.0 / −49.7; lateral CA
≤0.005 dot in x). **"ISI equalization is therefore NOT a lever on this
engine."**
**Priority.** D on this engine; re-measure per engine before reopening.

---

## 8. Evidence & shared state (fields, probes, anchors)

Everything in this section is **evidence-level**: it does not generate an
attempt, it changes what a later attempt reads. That makes these items
the box's shared state, and it makes them the one class that can REGRESS
a slot that would otherwise have certified — which is exactly what W6's
band 3 did. They need their own gating discipline (per-block adoption,
or attempt-both-and-union), separate from the tools.

### 8.1 The per-plane registration field
**What.** A nonparametric per-plane translation-delta vector field over
tile space, built from certified-tile probes plus word/dust anchors,
smoothed, and applied at the colour readout seam as a per-cell local
affine composed onto the committed pose.
**Measured.** PLANE-FIELDS §6.4 (W6) + RECEIVE-DESIGN §9b +
INDEPENDENT-PLANES §2.1/§2.2. **V0 PASSED**: a blind field from
certificates and committed poses reproduced the supervised sinusoid at
**Spearman +0.997, period 100.2 mm, amplitude 0.935**. **W6 (sheet I,
3×2400, dial ON): +252 certificates (5,297 → 5,549; Y 1,444 → 1,629),
page residue 517 → 332, C residue 66 → 2, M 3 → 0, close VERIFIED
byte-exact.** A fourth capture added **+90** and produced the first Y
adoption. Probe pass at real-capture scale: 16,125 measurements /
5,376 sites in 42.7 s + 0.052 s solve, coverage ≥ 0.98.
**Where it lost.** The pre-registered dead-band bar FAILED (median Y
residue **24/53 vs ≤ 5/53**), and the band structure is the finding:
band 1 164 → 121, band 2 189 → **62**, **band 3 108 → 127 — WORSE**;
column 8 (zero Y evidence) 53 → 46. Three measured causes: zero-evidence
bands defeat extrapolation; **adoption is all-or-nothing per page**, so a
smooth field fitting two extrema and misfitting the third is applied
everywhere; and the baseline carried a tree-drift confound. Two further
limits: an unnoticed effect is that the field is also correcting scanner
CA (C residue 66 → 2 was not the design intent), and the whole apparatus
is "a payload-lane bolt-on [that] reaches too little — one seam, one
lane, per (capture, lane), rebuilt from zero each time, blind to
addressing".
**Additive:** evidence-level. Under the box's rules the right form is
**attempt at the committed pose AND at the field-corrected pose, union
the certificates** — which makes band 3's regression structurally
impossible and retires the adoption machinery entirely.
**Cost.** the probe pass (8.2/8.3) plus a solve of ~0.05 s.
**Priority.** A **as an attempt generator** (its +252 is real and its
only measured harm is an adoption artifact); B as an adopted default.

### 8.2 Offering the probe pass EVERY window (the mixed-window predicate)
**What.** Let certified tiles inside windows that still owe payload work
be probed, instead of only tiles inside fully-solved ("label-only")
windows.
**Measured.** INDEPENDENT-PLANES §2.9b (E5b, 2026-08-23). **The biggest
single item on the owed list, and it was one moved statement:** dropping
the predicate costs **3.3 seconds** and buys **+603 certified tiles
reached (1,025 → all 1,628)**, field-bin coverage **0.813 → 0.997**,
column Spearman vs ground truth **+0.9265 → +0.9711**, per-tile residual
MAD **0.217 → 0.163 (−25%)**, and M across the 0.25-dot adoption cliff
(median magnitude 0.2454 → 0.2775): adoption C,Y → **C,M,Y**.
**Where it lost:** nothing. It also RETRACTED the previous section's
framing — the reach limit was the label-only predicate, not the template
width.
**Priority.** — (shipped); recorded because it is the record's best
example of a starvation rule costing 37% of the evidence for nothing.

### 8.3 Probe density and the tile-centric probe
**Measured.** INDEPENDENT-PLANES §2.9 / §2.9b / §2.9c. Three densities on
the same footing: a 5×5 block per field bin, a whole-tile square, and a
tile-FRAGMENT (every cell of a certified tile inside one covering
window). **For the FIELD they tie** once reach is equalized — per-tile
MAD 0.163 / 0.164 / 0.168 and Spearman +0.9711 / +0.9701 / +0.9699 —
because the field POOLS: 11,510 noisy samples are as good as 3,804 tight
ones. **Per PROBE they do not**: MAD **0.245 (5×5) vs 0.093 (whole tile)
vs 0.112 (fragment)**, same bias, so it is variance not aim. Cost per
probe **0.60 / 18.04 / 12.12 ms** before the FFT rewrite, **and 3.86 ms
for the fragment after it (×2.73, 121.2 s → 44.4 s per capture-lane)**,
with equivalence measured to **3.4e-15 dot over 682 recorded numeric
leaves**. Exhaustive density (every block) is a null: **4,550× more
probes landing within 0.008 dot**.
**Where the precision matters:** only for consumers that cannot pool —
the pose writer (refused, §4.10) and a cross-capture field (unbuilt). At
the 5×5 density only **9% of windows are self-consistent about their
plane-common residual** against 46% at a whole tile.
**Priority.** — (shipped at the fragment density). The transferable
finding is that **precision that pooling can manufacture is not worth
paying for**; the box should ask that question of every evidence tool.

### 8.4 Neighbour-derived per-plane offsets (the cheap hint)
**Measured.** INDEPENDENT-PLANES §2.3. Against the BER-optimal offset,
the neighbour-interpolated estimator lands at **ratio 0.93 (mean error
0.12 dot)** and reproduces the sinusoid at **Spearman +0.97** — inside
the 0.25-dot certified band. **The caveat is on the record and matters:**
a ratio just under 1 is what an ATTENUATING interpolator predicts
(inverse-distance over ~32 mm of a ~100 mm-period field), not proof of
unbiasedness, and the per-tile standard error is ~0.15 dot against a
0.25–0.73 dot signal.
**Additive:** evidence-level (a hint that seeds 5.1).
**Cost.** negligible.
**Priority.** A **as a search seed** — it is what turns the swim's blind
~170-candidate 2-D search into ~9.

### 8.5 Dust as a hint (never a correction)
**Measured.** INDEPENDENT-PLANES §2.3, superseding PLANE-FIELDS beat 18's
"demoted, not deleted". **Y dust is NOT noise — it carries the sinusoid
at ρ +0.82 — but it overstates magnitude ~2.3× and lands OUTSIDE the
0.25-dot acceptance band on both controls.** Same for every direct-NCC
estimator: NCC measures where the ink physically landed, while the
decoder's optimum is smaller because the detector's calibration absorbs
part of the displacement (*inferred*). **A field trained on NCC anchors
will over-correct** — the candidate mechanism for band 3's harm.
**Dust's load-bearing residue is elsewhere:** it is the CALIBRATION
BOOTSTRAP (the only cold exemplars of the six non-word states) plus cold
verification content, plus integer disambiguation.
**Priority.** — (hint role only). The overshoot constant is a measured
property of the detector and must be re-measured when the detector
changes.

### 8.6 The shrinkage target (shrink to zero, not to a cross-plane mean)
**Measured.** INDEPENDENT-PLANES §2.8 P1. The old law pulled each plane
toward a precision-weighted cross-plane mean in which C and M CANCEL, so
the "common field" ≈ Y/3 — Y was shrunk toward a third of itself exactly
when its evidence was thin, which is also what pushed it under the
adoption threshold. Under the corrected law (each plane an independent
posterior about the natural zero), measured on 1,869 certified-tile probe
rows while thinning Y's evidence: **Y rms GROWS where the old law shrank
it (1/10 evidence 0.28 → 0.37 dot; 1/40 0.27 → 0.45), Y adoption FLIPS ON
at the thin densities where a live run refused it, and M flips too** (its
median sat at 0.2487, a hair under the 0.25 cliff), with the field's
column profile against the sinusoid unchanged to five decimals (+0.9609).
**Priority.** — (fixed). Recorded because "the pane and the refusal were
the same finding seen twice" is a good argument for per-plane visibility
in any diagnostic the box grows.

### 8.7 Per-block adoption
**What.** Apply an evidence correction where it is measured to be right
and withhold it where it is not, at block granularity instead of per
page.
**Measured.** PLANE-FIELDS §6.4 cause 2, §6.5.1; INDEPENDENT-PLANES
§4.B.2. **UNMEASURED as built.** Its target is exact: band 3's 108 → 127
regression under all-or-nothing per-page adoption.
**Additive:** it makes an evidence tool safer; the box's own answer
(attempt both, union) makes it unnecessary for yield — but per-block
adoption is still the right thing for a DEFAULT-ON field.
**Priority.** B if the field is ever adopted by default; C if the box
runs it as an attempt.

### 8.8 The differential-only field
**Measured.** INDEPENDENT-PLANES §2.11 configurations (v)/(vi). Removing
the plane-common part by construction is **slightly WORSE than the full
field** (13.53% vs 12.93% cell BER over all 334 slots frozen; 13.70 vs
13.06 on the dead 310) though it does cut the pose writer's harm by about
two thirds. **1 certificate vs the field's 1** frozen; refit (vi)
recovers 2 of the 5 slots (ii) won.
**Priority.** D — the full field dominates it.

### 8.9 The window pose residual (measured, never applied)
**Measured.** INDEPENDENT-PLANES §2.9b/§2.9c/§2.11. Every certified probe
splits into a per-plane part (which the field consumes) and a
plane-common part which is **that window's own committed pose seen
through certified ground truth**: median **0.174–0.200 dot**, p90
0.30–0.33, max 0.87–1.20, recorded per window and **applied nowhere**.
Feeding it back is measured negative (§4.10). What remains true and
unused: it is a per-window QUALITY signal — a window whose sites agree
(17% at the shipped density, 46% at whole-tile) is a window whose pose is
trustworthy, and a scheduler could use that to order refinement work
without ever applying the correction.
**Priority.** C — as a scheduling signal only. Never as a write.

### 8.10 The registration-anchor field corpus (A2's residue)
**Measured.** COLOR-UPLIFT-MEASUREMENTS §15; the PK6/A2 line record. The
ARM is closed as a measured negative (the pre-registered four-clause gate
failed on all four captures, each on a different leg). What survives and
is directly reusable: **a 2.27 M-anchor field corpus over 61 lanes and 4
captures, every one cert-exact to the qualification matrix**, plus its
instrument. Measured content: plane-differential structure is REAL at
**τ ≈ 0.1–0.3 dots**, clears the shrinkage-MSE bound on the primary
capture, survives 8-cell min-separation thinning — but is predominantly
smooth and plane-common; own-window reach on the residue is **C 20.8% /
M 16.0% / Y 0%**, and **Y anchors are unmeasurable at fine pitch**
(dust-only supply, 9–22% correlation-edge saturation). Anchor errors
correlate ρ̄ ≈ 0.3–0.44 out to 12 cells, so **density buys little**
(n_eff ~2–4 per window).
**The two routings the data supports** — region-field enrichment for the
smooth differential, pose-refinement coupling for the common mode — are
"answerable substantially from the archived NPZs before any new code".
**Priority.** B **as analysis** (no replays needed), D as the specced arm.

### 8.11 Certified tiles as calibration furniture over done regions
**What.** Probe fully-certified tiles for registration and calibration
evidence — including a certified re-encode probe grid for a NEW capture
over regions that are already done, which otherwise produce no attempts,
no anchors and no probes at all.
**Measured.** INDEPENDENT-PLANES §4.G. The mixed-window half is DONE
(§8.2, +603 tiles for 3.5 s). The **new-capture-over-done-regions half is
UNBUILT and UNMEASURED**, and it is a real hole: the done gate correctly
suppresses payload work there, and with it every by-product.
**Ruling on record, which the box should inherit verbatim:** *"we don't
do ceilings here. If the ceiling reduces yield, it's wrong. If having no
ceiling does not increase yield, then maybe we should not do the thing at
all."*
**Cost.** measured at the shipped density: **0.60 ms/probe, 6.9 s for a
full page at one capture and lane over ALL windows**; the cost grows with
the done fraction, which is why the pass "must now justify itself by
MEASURED YIELD… or be removed".
**Priority.** B — the only evidence source that scales UP as a sheet
gets solved, and the one the done gate currently starves.

### 8.12 Certified-label enrichment as evidence (holo2's CA1)
**Measured.** holo2 H5 P2: BUILT, oracle-pinned, and **DIALLED
DEFAULT-OFF on a measured +68% cost for zero yield**. Note the contrast
with §6.4, where the same idea (certified labels as dense supervision)
bought +19 tiles — under a different regime (scraps, multi-scan,
supersede-inside-failed-tiles-only) and with a geometry refit attached.
**Priority.** C — re-measure under the exclusion form before concluding.

---

## 9. Scheduling

### 9.1 The supplemental-lane law (the box's own ancestor)
**What.** An arm that cannot prove universal non-regression is not gated
— it is SCHEDULED, as its own lane after the standard ladder, where the
per-address retirement law makes it monotone by construction.
**Measured.** RECEIVE-DESIGN §6.2a (PK4.3);
COLOR-UPLIFT-MEASUREMENTS §10. **+16 certified tiles across the corpus
(hp c3-cmy8 +7, xerox c2-cmy8 +9, xerox c3-cmy7 +0), 0 lost, 0 wrong, and
`re_timed = 0` on EVERY u-lane** — the retirement law showing through: a
supplemental lane cannot attempt a certified address, so unlike the
ladder-side numbers it cannot manufacture a gain out of a re-timing.
Force-null is exact: 720/720 certificate-ID identical, and the u-lanes
cost **0.0 s and emit not one event**.
**Where it lost.** Cost: **+15–23% CPU** on top of the ladder, and the
lane's price scales with the RESIDUE (cheapest where the residue is
smallest: 246 pairs ≈ 300 s/lane; dearest where it is largest: 1,756
pairs ≈ 350 s/lane at 24 ppc). One structural waste was measured twice
before being filtered: a single-stream coding schedules a
sibling-conditioning lane that cannot fire — **98 blocks / 185 attempts /
0 certificates / 70 s wall**. And the binding structural limit: **it
binds to the FINEST ordinary rung**, which is right for an ARM and wrong
for a CONFIGURATION (§5.5), and which means an arm whose yield is
concentrated at the COARSEST rung delivers almost none of it there
(§6.8).
**Priority.** — (adopted, and it is the box's template). Its verdict row
is the doctrine in one line: **"NOTHING IS PROPOSED FOR ADOPTION, because
nothing needs to be — that is the law's whole point: a scheduled arm has
no adoption question."**

### 9.2 The supplemental BASELINE lane (schedule the displaced configuration)
**What.** When an arm changes the ladder, also schedule the OLD
configuration over the residue.
**Measured.** COLOR-UPLIFT-MEASUREMENTS §11.10/§11.11. Cost: **108 s /
686 s / 392 s CPU** on the three captures; in-flight proof that it really
is the pre-campaign path (the arms' diagnostic keys are ABSENT).
**Yield: one of six stranded addresses recovered** — 3 certificates on
one capture, 1 of them new. The five misses split into two named
mechanisms: **FOOTING** (two tiles certified by the baseline at 6 ppc and
4 ppc while the lane binds to 12 ppc — fixable, see §5.5) and **HISTORY**
(three certified at exactly the right footing and still not recovered,
because by then the frontier carried 794 / 5,460 certificates where the
baseline's own lane saw ~668 / ~5,100, so a DIFFERENT model was fitted).
**"A supplemental baseline lane restores the CONFIGURATION, not the
HISTORY"**, and recovering the rest would need frontier rollback, which
is forbidden.
**Priority.** A — cheap, sound, and it is the structural answer to
re-timing, which is the only way an additive box can lose tiles.

### 9.3 Done-geometry (retire work that provably cannot pay)
**What.** Project each certificate's tile through its own committing pose
to exact capture pixels at certification time; a window whose supported
extent lies entirely inside the done set is never posed, searched or
scheduled. Pose-free, prediction-free, exact.
**Measured.** DONE-GEOMETRY §8a, census on the e029 ink page (zero
print, every approximation biased AGAINST gating): **719 of 1,479
committed placements (48.6%) pixel-gated**. Per level: l02 and l03
**236/315 = 75% each** — that pair spent 630 placements to mint 11
certificates; the tail level **243/279 = 87%, with 398/440 windows,
136/160 priced colds and 136/160 rest-word decodes gateable, to mint 2
certificates**; refinement lanes **0** — the gate never touches live
refinement work. **Gated windows minted zero certificates — provable, not
merely observed.** Motivating magnitudes from the same line: 48.2% of
lane time went to zero-yield lanes; open-domain cold ≈ 12 s/window.
**Where it does not apply:** at 54.8% frontier density it gates almost
nothing (it is a high-density instrument, decisive from ~98%); the
fragment/confetti census is still owed; and "**done ≠ exhausted**" — a
certificate-only mask never stops work on hopeless material.
**The cost it charges, which the box must price:** it is deliberately NOT
evidence-neutral. Done windows currently serve as label rows and as the
healthiest slice of the winner-flip canary; gating them changes label
provenance and removes that canary slice.
**Additive:** it is the box's only legitimate SUBTRACTION, because it
subtracts work that provably cannot produce a certificate.
**holo2.** BUILT (§2).
**Priority.** — (built in holo2); the open pieces are the erasure
extension ruling and the fragment census.

### 9.4 The phased session schedule and the priced tail
**What.** Rung-major breadth-first over all captures with cheap routes
first, durable parked rows, per-capture mop-up levels, and an EV-ordered,
close-preemptible costly tail.
**Measured.** PHASED-SCHEDULE (D1–D21, all implemented). Real-corpus wall
decomposition: address work is **RELOCATED, not added** (627.6 vs 649.5 s
across the two arms; +22 s for label reconstruction and parked
re-sampling), and the whole +169 s wall delta was **eight extra
source re-authentications** at ~19.1 s per 6.8 GB hash — since fixed by a
stat-keyed memo. The tail's cold boundary is cost-aware: cold-first when
the declared domain prices below one rest sweep, rest-first otherwise
(30–48 s per avoided cold at large page domains, but the single-page
decode is the common production case).
**Priority.** — (built). It is the existing proof that EV-ordering a tail
is compatible with complete-domain discipline.

### 9.5 Residual scheduling (NeedMap) — suppress redundant attempts
**Measured.** e023c: a pre-NeedMap two-level state produced **the exact
same 747 keys and bits** using **1,758 CRC calls, 81,271 BP iterations and
1,874 records**; residual scheduling removes **39.9% of CRC calls, 14.3%
of BP iterations and 37.5% of attempt records without changing the
answer**. Consequence the box inherits: marginal counts are order-
dependent, because suppression means a later capture is offered less.
**Priority.** — (built, and it is the retirement law the u-lane form
depends on).

### 9.6 BP retry as an idempotent scheduled stage
**Measured.** e023b/e023c. Explicit max-150 retry is **+5 certificates on
both footings over the calibrated baseline (742 → 747)**, and with the
context detector 749 → 757 (decimated) / 746 → 752 (native). On the
two-capture reference, **774 retry calls add 37 certificates**. Repeating
it on the same evidence frontier is a byte-identical no-op.
**Where the schedule matters:** retrying after EVERY scan rather than at
the end gained **only one tile** while costing **140–157 extra CRC calls
and ~44k–50k extra iterations per branch** — final-only is the default.
Note for the box: that is a cost-ORDERING result, not a zero-yield one.
The mechanism did win a tile.
**Priority.** — (built); the +1-tile-for-50k-iterations row is a good
calibration point for what "acceptable cost" should mean.

### 9.7 Certificate union across correlated views — and the capture-identity law
**Measured.** e023b: **decimated 757, native 752, shared 740,
decimated-only 17, native-only 12, union 769, all GT-correct**, with 36
of 805 nondegenerate tiles unresolved. The law that makes it safe:
**LLRs may never be summed across correlated views; only CRC-certified
bits union, fatally on conflict.** Independent captures may sum;
**derived rasters of one physical capture must share a capture identity —
"never count native and decimated views as two scans in one state"**.
The operational form on the confetti line is blunter: feed the decimated
scans only, one global dpi, never raw and decimated together.
**Priority.** — (law). Every combining tool in the box inherits it.

### 9.8 The adaptive scan loop
**Measured.** experiments/014 §014.2: asks for another physical scan
while tiles are uncertified AND the last scan gained coverage or
confidence. Live on the real scans: **ask → ask (+158k cells) → ask
(+18k) → STOP on an exact duplicate**. Its v1 confidence metric was
**duplicate-gameable** (a sum, not a per-cell mean) and was fixed before
commit.
**Priority.** B — the box's natural top-level controller for the one
"tool" whose cost is human (5.3), and the duplicate-gameability bug is
the kind a learned cost model would reproduce.

### 9.9 Off-line scoring of an unfinished session
**Measured.** e023c: read the authenticated certificate union, attach a
manifest, run the production fountain decode and the length/sha gate,
mutate nothing — **809 LDPC certificates, 784 useful symbols, rank
737/737, 192,160 bytes, SHA PASS** on a session that still had pending
work. "This is a verified recovery, not an exhaustive yield result", and
an under-ranked state is honestly OPEN.
**Priority.** — (built, outside the algorithm boundary). Relevant to the
box because it decouples "did we get the volume?" from "did every tool
run?", which is what lets a box run long without blocking delivery.

---

## 10. Format-side levers (listed, and OUT of the receiver toolbox)

These change what is printed. None of them can help a sheet already in
the world, which is the box's whole clientele. They are here because they
compete for the same yield and because two of them are cheap.

- **CMY word states.** Print words in all three inks; acquire on luma
  exactly as today; then locate C, M **and Y** by per-channel matched
  filter against a KNOWN template — **~100 high-contrast known cells per
  tile against ~10 dust cells**, and Y never needs to decode, so zero
  error budget is spent. Measured, engine-dependent: the M281 triple is
  WORSE (luma 73 vs 65; Stage-A 10.1% vs 5.8%) because ANY plane overlap
  triggers its contone re-screen — but those figures are inside the
  consumable-confounded set, and the mechanism predicts starvation
  EXAGGERATES the penalty; **the AltaLink triple is marginally BETTER
  (0.92% vs 1.04%)** and no re-screen was measured there. Costs: a format
  fork, and **nothing for the printed A–I corpus**. Cheap to express
  post-FORMAT-SPACE as a generation token. Discriminating test: one
  characterization patch carrying both renderings, next print day.
  (PLANE-FIELDS §6.5.5b; INDEPENDENT-PLANES §4.H.)
- **Per-plane LDPC rungs** (Y at a lower rung than C/M): ~7% page
  capacity for ~4 pp of Y margin (*estimate*); blocked by the generator's
  width-class law, and useless without registration correction alongside
  (uncorrected 17–20% exceeds even the lower rung).
- **Fountain quota skew toward Y:** the quota law is UNIFORM BY
  CONSTRUCTION, so this is a fountain-law fork, not a knob.
- **Y at c3 (mixed pitch): DOMINATED** — 56% of Y's cells lost before
  coding (~19% of page capacity) plus lattice/addressing surgery, against
  ~7% for a rung step.
- **Rotating word ink across planes:** parked — it spends word contrast
  on the weakest channel; CMY word states add a plane at every site
  instead and are strictly better.
- **The rung replay table** (useful yields at r0550/r0625/r0700/r0775/
  r0850 = C2 1,730/1,730/1,723/1,695/1,555 and C3 782/775/771/768/756):
  **NON-REPRODUCIBLE exploratory evidence** — no script, seed or decoder
  schedule was retained. Treat as a hypothesis that r0700 is the knee,
  never as qualification; rebuild it deterministically before any format
  decision rests on it.
- **Page-fill / margin extent:** c3 +3.3% and c2 +4.7% at the 64-quantum
  (+9.6% if a margin-ladder probe blesses ~4.9 mm) — the biggest capacity
  item of its session, parked behind payload-safe edge canaries that do
  not exist even for current c2 edges.
- **Format A/B (100-site vs ~114-site pilot filler):** 2.44% vs 2.78%
  filler density; the deciding grain sweep has **not been run** —
  UNMEASURED.
- **The 8 mm scrap rung:** measured negative as written (window span 64
  cells against a 70-cell minimum plus support floors; clean-render c3
  floors at 24 mm = 4/4 contained tiles, 16 mm = 1/1, 8.1 mm placement
  fails). It needs the derived-floor and window/step reconciliation work
  first.
- **Deleting dust:** economics say no — dust costs 0.5% of capacity, and
  removing it means a new coding AND a new site family with an unmeasured
  placement lineage. The interesting follow-up is the blind-calibration
  measurement (§6.14), not the removal.
- **The rank reserve rule**, which prices every yield claim: about 16
  recovered rows beyond K gives a random-row rank-failure scale of 2⁻¹⁶,
  so a hard recovery promise from physical fraction q sets
  **K ≤ floor(q·N) − 16**. Nominal capacity tables do not subtract it.

---

## 11. Discovery-side (also out of the box, and one of them is a law)

- **Discovery tiers are hard-decision CHANNEL numbers, not receiver
  performance.** The e031/e032 pair is definitive: the same-day discovery
  sheet ranked one coding BETTER than another, and the payload outcome
  INVERTED it — the coding the sheet called fragile at 12.17% closed
  VERIFIED while the one it ranked at 7.74% failed on both engines.
  **Rank rungs and detect dead ones; never predict recoverability.**
  A toolbox scheduler must therefore learn its costs and yields from
  DECODE accounting, never from a discovery statistic.
- **Unpool the planes in colour candidate tiers:** the pooled 12.17%
  contained Y ≈ 17% and C ≈ 5% and did not say so. A verdict-layer
  change, free.
- **A full-page per-plane registration track on discovery sheets** (which
  may carry fiducials): would have measured the Y sinusoid on the FIRST
  AltaLink pair instead of two print days later. Three x-columns cannot
  sample a ~100 mm period — the discovery sheet's own current design is
  the reason.
- **Per-ink PSF from the K-edge channel-ratio method** on every discovery
  sheet (§7.9's numbers): it converted "Y is optically soft" from a
  receiver hypothesis into a measured CONSUMABLE fact in one afternoon,
  with no hardware.
- **Position and motif dependence within one sheet** are measured and
  large (solid c2 BER 19.08% top / 18.19% middle / 13.43% bottom; c3
  11.40% top vs 0.125% bottom; half-cell motifs ~9% against solid
  ~14–15%). A scheduler that knew this would order work by position; no
  such consumer exists.

---

## 12. NOT in the box — with reasons

**Replacement-only (they lose because they REPLACE; some may return as
attempts).**
- The **pose writer** as a write to committed poses: −5 certificates,
  +2.1 pp BER, harm linear in the correction at +9.3 pp/dot (§4.10). May
  return only as an attempt-time override.
- The **backward fixed-point / arbitrary revision loop**: negligible
  benefit at substantial cost, and revision contradicts the retirement
  law (§4.12).
- **Per-tile best-scan selection** across scans at c2: 7.50% vs 7.24% for
  equal-weight — "1–2 word decodes per tile is too noisy a quality
  signal". The equal-weight sum, ordered after the context detector, is
  the law.
- The **consensus context column** across captures: 36%/57% against one
  capture's own 44%/64% (§7.5).
- The **differential-only field**: strictly worse than the full field
  (§8.8).
- **Sample-level multi-capture fusion**: the print-frozen floor caps the
  gain at the scan-noise share, and the certificate union already has
  most of it.
- **Margin-gated pack erasure**: −36 tiles at the bar point, negative in
  combination with iteration (§6.11).
- The **per-plane context port**: an exact null in 17 of 17 lanes at
  8,648 s of CPU (§6.9).
- **Genie-geometry rescue** for sub-grain windows: blind = full-tile =
  genie at all 15 windows — geometry was exonerated and the failure is
  word incompleteness.
- The **±8 combine-side LLR clip**: bought +7 tiles and was retired as
  symptom-hiding once the source defect was fixed (§6.3). A box must not
  re-adopt a symptom fix because it "pays".
- **Two A3 applicability floors** and **A4b's park flag**: no statistic
  separated help from harm; the answer was scheduling, not a constant.
- **The `means_at_zero` requirement** that a context stage imposes on a
  correlation-placed piece: it regressed placement 42 → 35 and introduced
  a wrong-placement poison — a detector requirement that costs placement
  quality is not additive.

**Already in holo2 — do not re-propose.** Window subdivision; quarantine
and the whole-word rival gate; re-work aging; the pull model with
one-bit wakes, fire-time consult and the tried-set floor; global cost
tiers with gating and instantaneous dryness; cold search per rung that
proposes rather than commits; park/defer (subsumed); done-pixel
projection and the done gate; close preemption; the commit wall,
commutative tile merge, dispatch markers and journal-authoritative
replay; footing as a price; streaming ingestion. (§2.)

**Dominated or subsumed.**
- **Certified-footprint deprioritization** in address space — subsumed by
  done-geometry, which is exact and pose-free (§4.9).
- **Whole-tile square probes** and **every-block probes** for the FIELD:
  the first halves reach for no field gain, the second is a null at
  4,550× the probes (§8.3).
- **The E024 `combined` and `recal` profiles**: the factorial interaction
  is −1 on both footings, and `combined` loses a certificate `refine`
  keeps, for more work (§4.7's family).
- **Coarse-lane skipping** (deferring or skipping cold at coarse lanes):
  adjudicated payload-unsafe on measured bidirectional exclusivity —
  coarse-only 15/671 and 19/1310 against fine-only, and both qualified
  sheets closed AT THE FIRST COARSE BARRIER.
- **Occupied-page-area exclusion and page-recency narrowing of the cold
  domain**: adaptive narrowing, forbidden by L7, and the floor payoff is
  logarithmic anyway (halving a 312-page domain moves the floor 55 → 53).
- **Context-PAVA at the word layer**: a deliberate evidence-boundary
  placement (the word sites are the calibrator's training labels), and
  the d = 27 margin leaves nothing to gain — 1,780 historical reads, 0
  conflicts.
- **Stacked-batch cold FFT**: rejected because it is not provably
  bit-identical by fixture, not because it is slow.
- **A2 as specced** (per-window plane registration from own-window
  anchors): closed as a measured negative; holo2's own capability note
  says "do not build". Its CORPUS is reusable (§8.10).
- **The comb as a critical path** and **6-dof per-plane anything**: the
  Jacobian is plane-common by a factor of 11, and registration alone does
  not close the dead bands.
- **"More same-footing scans" as a Y strategy**: print-frozen. Footing
  UPGRADES still pay (§5.3).

---

## 13. The box, in one table

Priority is a yield-per-cost GUESS, graded A–D as defined in §1. "Yield"
quotes the best measured evidence for that tool; **UNMEASURED** means no
number exists anywhere in the record. Additive class: **+** = additive as
written · **∪** = needs union-of-attempts (it was measured as a
replacement) · **E** = evidence-level (keeps the original attempt).

| # | Tool | Layer | Add | Measured yield (and where it lost) | Cost | Pri |
|---|---|---|---|---|---|---|
| 7.2 | One context-map fixed-point iteration | context | ∪ | −1.07 pp dead / −1.57 control = **44% / 64% of the oracle**, regression-free, same at the production geometry; **0 dead tiles certified at G2** | 1 extra decode/slot + 1 ink-map rebuild/capture | **A** |
| 5.1 | Translation swim (hint-seeded 1-D closer) | sampling | + | controls **certify** under a 0.25-dot band; **residue 0/10 at 85 offsets** (dead band 17.5→10.8% vs a ~7.6% gate) | ~0.8 s/candidate; **≈4 s/tile** seeded; ~100 s setup/capture | **A** (K/C/M, scraps) · B (dead Y) |
| 4.3 | Correlation placer for scraps | placement | + | **100% correct at every size incl. 4 mm**; gate passes 5/5 at ≥5 mm, refuses 4 mm; 6/6 on a fresh window | **0.73 s/fragment**, 272 MB peak | **A** (scraps) |
| 4.4 | Anchor-graph bundle (overhang, mask windows, ID retry/fold, angle sweep) | placement | + | **264→325 symbols at canvas 1 (+23%)**, closes 443→512, **178/189 → 189/189 pieces**, 0 misplaced | UNMEASURED per piece | **A** (scraps) |
| 4.5 | Sub-window / quadrant placement | placement | + | **12 symbols vs 0**; 4/4 quadrants at 0.043–0.101 where the whole piece floors at 0.248 | 1 placement per sub-window | **A** |
| 5.7 | Intermediate scale rung | sampling | + | **+7 certificates, strict superset, no conflict** vs the endpoint control | +11% CRC, +33.5% BP | **A** |
| 6.4 | Dense certified-label re-derivation, un-gated by exclusion | calib+geom | ∪ | **+19 tiles / +18 symbols, 0 wrong in 850,177 cells**; the gated v1 converted **0** on the same state | ~15 min for 3 rounds × 4 scans; re-segments every round | **A** (scraps/multi-scan) |
| 6.10 | Iterative demapping inside one attempt | detector/codec | + | **+39, ZERO lost, strict superset**; **56.5% of the standing tail**; exact no-op on the other coding | **+21% wall / +45% CPU**; 3× CRC exposure | **A** |
| 8.1 | Per-plane field, run as an ATTEMPT | evidence | ∪ | **+252** certs (Y 1,444→1,629), close byte-exact; **+90** on a 4th capture; band 3 **worse** under per-page adoption | probe pass + 0.05 s solve | **A** |
| 8.4 | Neighbour-derived offset hint | evidence | E | ratio **0.93** to the BER-optimal offset (SE ~0.15 dot; attenuation caveat) | negligible | **A** (seed) |
| 9.1 | Supplemental-lane scheduling (the box's template) | scheduling | + | **+16 corpus, 0 lost, 0 wrong, `re_timed`=0**; force-null exact | **+15–23% CPU**; price ∝ residue | **A** |
| 9.2 | Schedule the DISPLACED configuration too | scheduling | + | **1 of 6** stranded addresses recovered; the other 5 diagnosed (footing / history) | 108–686 s CPU/lane | **A** |
| 4.7 | Certified refinement (forward) | pose | + | +2 / +5 own-branch, **772 union**, 0 wrong; **after the cascade: 0 (C3) and +1 useful (C2)** at 12k–97k BP iterations | 12 TIFF reads, ~338 s at the best recipe | A pre-cascade · **C** post |
| 6.5 | A3 per-window photometry, residue form | calibration | + | **+6 / +7 / 0** new addresses, `re_timed`=0; ladder-side +62 came with 11 losses; **fires on noise** (13/64 windows) | CPU flat; **RSS +34%**; lane ≈300–350 s | **A** (residue) · D (ladder) |
| 3.3 | Erasure-aware Stage A (search side) | addressing | + | **UNMEASURED**; the known-position rung is 96.1/98.7/100% at q .80/.85/.90 with **0 wrong in 9,120** | 1 decode/hypothesis over a larger set | **B** |
| 4.8 | Per-window plane-common affine, decode-gated | pose | + | **1 certificate** (page corner 11.95→4.97%); affine vs translation is decision-irrelevant elsewhere (0 certs either way) | UNMEASURED | **B** |
| 4.11 | Seam-aware piecewise pose + support revision | pose | + | **UNMEASURED**; target measured: 360-cell/30.48 mm failure cadence, **101/449 placements straddle-cut** | bounded by the straddle population | **B** |
| 5.2 | Refit at the corrected geometry | sampling | + | **−0.96 pp** dead (6/6 tiles, 24/24 rows same sign), **1 dead tile certifies**; gap 2.85→2.15 pp | per-capture refit; instrument runs were 33–62 min | **B** |
| 5.3 | Footing UPGRADE (finer px/cell) | sampling | + | **+90** certs and the first Y adoption; same-footing repeats are print-frozen | a scan + a lane (operator action) | **B** |
| 5.5 | Multi-footing baseline restoration | scheduling | + | **2 named addresses** lost purely to footing | one lane per rung | **B** |
| 5.6 | Geometry × sampler hypotheses on the tail | sampling | + | **+3** tiles at full factorial (union 772 vs 769); DN lowest BER, ND one unique | ~2× at full factorial; tail-only UNMEASURED | **B** |
| 6.12 | Stratum-exact correction on the 3 Y-inked-with-sibling states | detector | E | **−1.68 pp dead / −1.13 control per capture** (arithmetic); those 3 states carry **58.8% of errors on 37.5% of cells** | UNMEASURED (no arm) | **B** |
| 6.14 | Blind EM calibration (no dust) | detector | E | **UNMEASURED**; identifiable by construction (keystream-balanced states) | UNMEASURED | **B** (insurance) |
| 7.4 | Calibrated soft context column + confidence gate | context | ∪ | **UNMEASURED**; the uncalibrated soft column TIES the hard one and over-shrinks past the oracle (bin 4 29.1% vs 27.0%) | one leaf; 1 extra decode | **B** |
| 7.7 | Context-conditional LLR attenuation / erasure | context | ∪ | **UNMEASURED vs production**; supported by median abs-LLR 1.58 on wrong cells vs 4.29 on right ones, and 2.6% erased → 0.98% silent vs 1.37% hard | 1 extra decode/slot | **B** |
| 8.10 | Region-field enrichment from the archived anchor corpus | evidence | E | analysis only: τ 0.1–0.3 dot real, smooth, plane-common; **2.27 M anchors already banked** | no replays needed | **B** (analysis) |
| 8.11 | Certified furniture over DONE regions (new capture) | evidence | E | mixed-window half **+603 tiles for 3.5 s**; the done-region half **UNMEASURED** | **0.60 ms/probe**, 6.9 s/page/lane | **B** |
| 9.8 | Adaptive scan loop | scheduling | — | live: ask → +158k → +18k → **STOP on a duplicate** | trivial | **B** |
| 3.8 | Dust as independent placement-validation bits | qualification | — | **no yield by design**; it tightens the unfrozen false-accept gate | trivial | **B** (prerequisite work) |
| 6.2 | Backing/mask exposure audit of the colour detector path | detector | — | **UNMEASURED and explicitly unexamined**; the K path was fixed, the QDA path never audited | cheap | **B** (audit) |
| 8.7 | Per-block adoption of an evidence correction | evidence | — | **UNMEASURED**; target is band 3's 108 → 127 | small | **B** if default-on · C if attempted |
| 3.4 | Later-lane address recovery with calibrated scores | addressing | + | **UNMEASURED**; value case named as scraps/marginal channels | UNMEASURED | **C** |
| 3.5 | Per-channel (plane-aware) word matching | addressing | + | near-zero on the healthy corpus (99.8% word footprint); **UNMEASURED** where it is meant to pay | one matched filter per channel | **C** |
| 3.6 | Comb (cyclostationary cell-clock phase) | acquisition | E | **UNMEASURED (V1 never run)**; the only evidence source needing no decoded tiles | UNMEASURED; block-size limited | **C** (scraps) · D (dead bands) |
| 3.7 | Swim rescue tier for acquisition failures | acquisition | + | **UNMEASURED** | swim cost × dead windows | **C** |
| 4.10 | Pose-residual sampling as an EXTRA attempt | pose | ∪ | as a WRITE: **−5 certs, +2.1 pp, +9.3 pp/dot**; as an attempt: untested | 1 extra sample+decode per covered slot | **C** |
| 6.7 | A4b sibling-conditioned marginalization, lane form | calibration | + | **+1 M and +2** corpus-wide, from 6.5 M conditioned marginals | ~350 s/lane; zero on single-stream codings | **C** |
| 6.13 | Local vs page-global calibration (E9), K instance | calibration | E | **0 certificates on a complete 21-tile residue, two lanes**; page-global is the BEST arm; page cell error 5.63→4.92% / 2.25→1.85% for one fit; misses the banding (−0.3 pp) and helps the edges (−2 pp) | 0.7–3.0 s/attempt; 33–46 s/lane global, 53–125 s halo | **D** (certificates) · **B** (evidence, global form) |
| 7.3 | A second context iteration as a third attempt | context | + | 25%/24% of the oracle (half of one iteration's), **but it kept a marginal certificate the first lost** | 1 more decode | **C** |
| 7.8 | Anisotropic context model | context | E | mechanism real (+2.2 pp downstream cost) but **sheet-wide**; value vs production **UNMEASURED** | a model-class change + its qualification | **C** |
| 8.9 | Window pose residual as a SCHEDULING signal | evidence | — | measured (median 0.174–0.200 dot; 17–46% of windows self-consistent), never applied | free (already collected) | **C** |
| 8.12 | Re-measure certified-label enrichment under the exclusion form | evidence | E | holo2 measured **+68% cost, zero yield**; §6.4 measured +19 in another regime | a re-measurement | **C** |

**Everything graded D is in §12.**

---

## 14. What the box needs before it is built, and what this document is not

**Four prerequisites, in order.**

1. **Freeze the physical/null false-accept qualification.** Condition (2)
   is not rhetoric: the receiver is PROVISIONAL, the BER envelope and
   support margins are unfrozen, and the box multiplies CRC exposures by
   roughly the number of tools. The record already carries the accounting
   primitive (a monotone per-page exposure counter) and one named,
   yield-free way to tighten the gate (§3.8). The erasure-search budget
   (§3.3) is the same work seen from the other side.
2. **Per-tool attribution.** "Which tool won which certificate, at what
   cost" is not currently derivable: certificates carry a minting route,
   but there is no cost-per-certificate accounting and **no cost feedback
   loop anywhere** — holo2's cost tiers are declared orders, and the
   health-ledger-fed cost tables are the unbuilt deciders. Condition (3)
   is a build item, not a policy.
3. **A holo2 scope ruling.** holo2's standing rule is that it changes
   scheduling and orchestration, "never reach", and its step-back round
   explicitly excludes "changing what work exists". CA8 already
   contemplates arms as recipe capabilities, so the shape exists — but
   the box IS new reach, and it needs the ruling before it is built
   there.
4. **Colour in holo2 (H7)** for roughly half of this inventory. Nothing
   in holo2 decodes colour today and there is no field machinery of any
   kind; the K-only half of the box (placement, swim on K, context
   iteration on K, refinement, scheduling) can be built first.

**Three honest limits on the numbers in this document.**

- **Single sheets.** Almost every yield figure here is ONE physical
  capture of ONE printed sheet decoded from an archived scan. That makes
  them existence and regression evidence — this receiver reads this sheet
  at least this well — and **not ladder promotion**. Rate, margin, coding
  and engine calls go on multi-sheet minima.
- **Outcome selection.** The plane-fields numbers rest on six dead tiles
  and two control tiles chosen because that is where the residue is, with
  n = 2 physical controls; the certified references are carried precisely
  because they are NOT outcome-selected. Pooled tile × capture rows are
  descriptive, not inferential.
- **Regime dependence is the rule, not the exception.** The context
  detector is worth 3.5× at 16 px/cell and nothing at 8; the same repass
  machinery converted 0 tiles and then 19 depending on which pieces it
  was offered; an arm read +19 on two lanes and net −5 on twelve. **Every
  entry in this box should carry its regime in its identity, and the
  scheduler should be allowed to learn that a tool is dead in one regime
  and decisive in another** — which is the strongest single argument for
  the box over a fixed ladder.

**What this document is not.** It is not an amendment, not a build order,
and not a promise that any UNMEASURED entry will pay. It is the
catalogue, with the record's own numbers attached, so that the next
decision about what to build is made against measurements rather than
against memory.
