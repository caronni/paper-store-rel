# HOLO2-DESIGN v0.2 — the constitution

Status: **DRAFT.** H0–H3bis executed; the R0–R4 refactor executed
(`REFACTOR-WORKPLAN.md`). Not yet normative — adoption is a user
declaration at H8 (the format-freeze rule applies to design adoption
too). Until then `docs/RECEIVE-DESIGN.md` remains the receiver contract
of record and `src/holo` the receiver of record.

Scope: **receiver only, printed format v1 unchanged.** Generation,
format anchors, keystream, goldens, registries and the characterize
instrument stay in `src/holo`. holo2 must decode what holo generates,
byte-exactly, or refuse honestly.

**This document is the constitution.** It holds the vision, the two
truth planes, the laws, the vocabulary, the contracts that cross package
boundaries, and pointers. Subsystem rulings live in subsystem docs:

| package | doc | owns |
|---|---|---|
| `core` | [`src/holo2/core/DESIGN.md`](../src/holo2/core/DESIGN.md) | facts, storage, commit, identity, the work protocol |
| `format` | [`src/holo2/format/DESIGN.md`](../src/holo2/format/DESIGN.md) | printed-format v1 truth: addressing, coding, close |
| `capture` | [`src/holo2/capture/DESIGN.md`](../src/holo2/capture/DESIGN.md) | rasters, footings, survey — the physical plane |
| `solve` | [`src/holo2/solve/DESIGN.md`](../src/holo2/solve/DESIGN.md) | placement, payload, projection, the tile map |
| `engine` | [`src/holo2/engine/DESIGN.md`](../src/holo2/engine/DESIGN.md) | session lineage, recipe, orchestrator |
| `diag` | [`src/holo2/diag/DESIGN.md`](../src/holo2/diag/DESIGN.md) | the observer surface |

Module docstrings across the tree cite this document's **v0.1** section
numbers; §13 is the forwarding table.

Companions: `ENGINEERING.md` (how work lands), `CAPABILITIES.md`
(designed / implemented / verified / deferred),
`solve/PROVIDERS.md` (the 27-row provider census), `MEASUREMENTS.md`
(the recorded numbers), `WORKPLAN.md` (build order),
`H3BIS-ARCHITECTURE-REVIEW.md` (the adversarial review awaiting
adjudication).

Known defects live in ledgers, not in prose: each package's DESIGN.md
ends in a **TO-FIX** table, and §15 here is the system ledger for what
crosses packages or owns no package.

---

## 1. Why restart (the two-paragraph case)

The v1 receiver serializes what is actually a partial order, and does
bulk work whose uselessness is knowable in advance: the e029 ink page
spent 630 placements at l02/l03 to mint 11 certificates, with **48.6% of
committed placements provably pixel-gateable** at lane start
(DONE-GEOMETRY §8a, measured, zero-print); 48.2% of lane time went to
zero-yield lanes (kiss profiling, measured, synthetic); the parallel
scaffold existed but the control loop was serial, so no speedup was ever
recorded. holo2 replaces the control plane with a dataflow that (a)
never schedules work whose inputs are unchanged, (b) never schedules
work whose supported pixels are already done, and (c) runs independent
work items concurrently — carrying the evidence laws and the numerics
leaves over unchanged.

The second case is cognitive, and it is equal (user ruling 2026-08-14):
the v1 tree grew past what any collaborator — human or AI — can hold.
Guard mass, doc strata and dual-generation branching spend a session's
working context on archaeology before its first productive edit, and
the measured consequence is that defects cluster at plumbing edges
while core mechanisms land flawless (the cmy8-pooling record: a
bit-exact scheduler generalization beside an untouched consumer file
from the plan's own list). holo2 therefore restarts toward **component
isolation and abstraction over accretion**: packages behind narrow
contracts, each owning its DESIGN.md, sized so the whole system fits
one working context and any single package fits comfortably — because a
collaborator who can hold the piece in their head works at the level of
the pooling scheduler, and one who cannot works at the level of its
plumbing. Less bloat is not tidiness; it is what keeps the AI at full
capability on this code. L16/L17 are this paragraph as law.

## 2. The two truth planes

1. **Physical plane** — per capture: an authenticated raster (SHA-256
   identity), its survey products (scrap regions, support masks, integer
   cell-pitch vote), and its pixels. Multiple captures per session are
   normal; they may come from different scanners at different DPI.
2. **Logical plane** — one **tile map** per session: every
   `(page, tile_y, tile_x, stream)` work key of the declared page
   domain, with its state, provenance and (eventually) certified bits.

Solving is the construction of correspondences between the planes:
committed poses map windows of physical pixels onto logical addresses;
certificates project logical done-ness back onto per-capture physical
pixels. Everything else — windows, workers, calibration pools, the
recipe — is machinery ("by convention", user ruling 2026-08-09) and
carries no truth of its own.

Ingest/segmentation and fountain/metadata close are **imported problems
with existing good solutions**, carried from `src/holo` as leaves,
outside the core redesign.

## 3. Glossary

Vocabulary drift costs more than it looks like it does. These are the
words; a synonym in new prose is a defect.

- **capture** — one authenticated physical acquisition. Source SHA-256
  is the identity; DPI is operator-declared. Derived rasters of one
  capture are never independent evidence.
- **footing** — `(capture, aperture)`: a specific pixels-per-cell view
  of one capture, derived exact-area from native. **The unit of LLR
  comparability.** Footings of one capture are correlated; footings of
  different captures are independent. Footings correspond ACROSS
  captures by ppc value.
- **lane** — v1's word for a scheduling stratum. **Retired.** holo2 has
  footings, recipe entries and routes; the word survives only in quoted
  measured history (the u-lane law, v1 lane counts).
- **region** — one surveyed connected scrap area on one capture.
- **window** — a variable-size working set of cells on one footing; the
  placement work unit. Named by what it IS: `(footing, region, extent)`.
- **tile / work key** — `(page, ty, tx, stream)`. The payload work unit
  and the atom of the logical plane.
- **stream** — one independently coded payload channel within a format
  row: the granularity of LDPC certification and of fountain
  `(stream, block)` accounting. K rows have one per tile; CMY7 one
  (joint base-7 packing, all-or-nothing); CMY8 three (independent
  per-plane presence codewords). **Terminality is per stream.**
- **plane**, three distinct senses, always disambiguated in prose:
  *truth plane* (§2, physical vs logical); *colour plane* (C/M/Y, a
  format concept); *the session plane* (`solve.plane.SessionPlane`, the
  derived world a session schedules over, handed to the engine as
  `core.SolveView` — which is why B4 took the class off solve's public
  surface). Never write "plane" bare where two could be meant.
- **coding** — a printed registry row: alphabet, rate and geometry
  family (`c2-r0700`, `c2-cmy8-p120-v0`). The word "codec" has THREE
  senses in this repo; always write the qualified name, never the bare
  word: the **record codec** is `core.codec`, the receiver-internal
  canonical record serializer; the **payload-engine family** is
  `format`'s `codec_id` (`k-v1`, `cmy8-presence-p120-v0`) — a
  printed-format identity, baked into volumes on paper and never
  renameable on the format axis; and the original prohibition stands: a
  printed row (a *coding*) is never a "codec" of either kind
  (`registry_rows.py` teaches the collision at the code site).
- **provider** — declares a task family, the frontier resources it
  expands from, and the descriptor scheme it mints; yields workers.
- **descriptor** — `(recipe entry, family, subject, route, scope)`. The
  **route** is one way of attempting the subject (chain / lower_hint /
  word / cold / scan /
  union / retry150 / …). The **scope** is the footing, pool, arm or
  incumbent the attempt runs under. One route = one descriptor = one
  spend; there are no ladders (see the model of computation below).
- **worker** — one schedulable computation bound to a descriptor, with a
  declared read-set.
- **read-set / attempt identity** — the exact keyed inputs a worker
  consumes, bound to their versions at read. The read-set IS the
  identity.
- **spend** — a durable `(worker, route, identity, outcome)` record. A
  spend is what makes an attempt happen at most once.
- **resource** — a keyed, versioned durable value. The resource table is
  the wake/subscription index (transient); the records are the state.
- **collection** — a versioned membership resource (`collection:
  certified`, `collection:evidence/<key>`, …). Subscribing to a
  collection is how a worker names facts whose ids do not exist yet.
- **recipe** — the declarative orchestration policy: which task classes
  run on which footings under which prices and gates.
- **lineage** — one durable state and its resumes. Versions and spend
  records are meaningful within a lineage and under trace replay;
  cross-lineage comparisons are content-level only.
- **trace** — the disposable, observer-side ordering record.
- **placed** — a window whose address question is answered: its audited
  pose is committed. Placed is not finished (anchors, labels, possible
  refinement remain); windows end placed or retired(reason), never
  "failed". DONE is a tile word, not a window word.
- **done** — a scheduling fact: a certified work key's pixels are spent
  in the captures that observed it. DONE deletes nothing.

## 3a. The model of computation

Everything schedulable follows one chain; nothing else is mechanism:

**facts make work derivable; gates make it eligible; prices order it;
spends make it happen once; terminality makes it stop.**

AMENDED H4 W2 (2026-08-16, §6.9): placement work is admitted from a
second, declared WORK SOURCE — an in-memory scheduler whose readiness
and steering are DERIVED state, never facts — interleaved with the
descriptor path in one global cost order. The chain above still
governs everything durable; what changed is that not every unit of
work is a descriptor.

There is no allocation and no kickoff. Ingest/segmentation commits
capture and region FACTS; each commit bumps a collection; providers are
pure functions from fact-frontiers to descriptors, re-expanded whenever
a source frontier moves. On a resume the same facts derive the same
work; nothing about the work list is stored.

AMENDED FOR STREAMING INGESTION (2026-08-17): **ingest is WORK, not an assembly phase.**
It used to run to completion before the orchestrator existed — a session
opened by surveying every declared scan, so nine platens paid for nine
surveys before anything was placed. It is now one spendable descriptor
per DECLARED SCAN (identity: the resolved path and the operator's DPI,
`capture.scan_key`), minted one at a time — scan N+1 exists only once
scan N's capture record stands, which caps the survey's ~8x-raster
transient at one in flight with no gate mechanism at all — and the fire
proposes exactly the facts assembly used to commit while the plane takes
its raster by REOPENING the file on the committing thread (workers
propose, the main thread owns state, untouched). Two consequences are
visible in the durable record: an ingest leaves a SPEND row, which is
what lets a resumed session skip a survey it has already paid for; and
the ingest entry used to declare that its work does not QUIESCE, because
an acquisition is not on the footing-progression axis the quiescent gate
ordered — counting it there held every finer-footing window closed until
the last scan had been read, which is the assembly behaviour this
replaced.

AMENDED 2026-08-17 (the pricing ruling): that exemption is gone with the
gate it was an exemption from. **Footing progression is PRICING, not
gating.** A finer-footing window enumerates into the scheduling set the
moment its geometry exists, exactly like a coarse one, and its passes
carry a small FOOTING PREMIUM on top of their tier — data beside
`solve.place_sched`'s tier table, strictly smaller than the spacing
between adjacent tiers, so it reorders within a rung and never across
one. "Exhaust the sheet before specializing" is therefore a property of
the one global cost order rather than a rule some entry is exempted
from, and the finer window that never needed working exits by the §6
coverage rule instead of by never having been born. The `quiescent` gate
and `RecipeEntry.quiesces` are DELETED; the work-gate vocabulary is one
value wide.

AMENDED 2026-08-17, same ruling day and same lineage fork: **payload is
the cheapest recovery**, below every placement rung (`COST_PAYLOAD` 8,
between ingest 5 and ring 10). Measured on a real nine-platen run with
payload at 40: 2,529 ready workers, 1,287 of them armed payload, and
after 431 fires zero tiles attempted and zero certified — placement on a
domain that size never dries, so payload above it never runs, and
without a certificate neither close preemption nor done coverage ever
arms. Eager enumeration of finer footings makes that worse, not better,
which is why the two rulings land together. The ruled order is ingest,
the cheapest payload recovery, placement (coarse, then finer at its
premium), and the two dear placement tiers still gated behind global
dryness.

AMENDED 2026-08-19 (H5, the RE-WORK AGING rulings): **the price function
gains a third term, and it is an ORDINAL.** A descriptor's first attempt
prices exactly as above; a RE-attempt prices into a re-work band —
`REWORK_BASE + REWORK_STEP*(n-1)`, 90 and 5, where `n` is the attempt
count its own durable spend row holds (`engine.recipe.work_price`, read
at the wake). The band sits below the wide consult, so a failed tile's
re-decode fires only once the cheaper bands have drained: maximal
accumulated evidence per attempt, and v1's lane-barrier coalescing
recovered with no barrier, no generation and no gate. It is not a cap —
the OR-5 census found nothing bounds re-arming (worst key: 61 attempts,
11,820 BP iterations, never certified) and a CEILING was proposed and
REJECTED, because L7 lets current evidence reorder work and never narrow
a domain. The ordinal is unbounded instead, crossing wide at the 7th
re-attempt and cold at the 11th, so a hopeless key's re-work is held by
the dryness gate to the very end and nothing is ever refused: the cap
re-emerges as a horizon. Scoping needs no family knowledge — the ordinal
is a spend-ledger quantity, and a work SOURCE spends nothing, so
placement takes no term by construction. MEASURED at landing
(MEASUREMENTS, OR-5 addendum): the worst key 61 → 22 attempts and
11,820 → 4,260 iterations, pooled BP attempts −47%, the same 160
certificates and the same three byte-exact volumes.

**There are no ladders.** v1's stage sequences (scan-then-union-then-
retry; chain-then-word-then-cold; mop-up; refinement phases) were
containers the barrier architecture needed. Here every one of them is
a set of independently priced, eligibility-gated descriptors over one
subject, and the observed cheap-first ordering is EMERGENT: a union
cannot fire before a second capture exists; a retry cannot fire before
its baseline failed; cold is gated on quiescence and priced high;
terminality suppresses whatever remains. Sequence is never a
mechanism. Writing a sequencer is a defect.

**Worker granularity law.** A worker is one SPENDABLE ATTEMPT — it has
a read-set identity, a spend, an outcome. Computations inside a fire
(the BCH decoder, PAVA fitting, the BP kernel, samplers) are
libraries, not workers. A computation is promoted to its own worker
exactly when: (a) its output is a durable versioned resource other
workers subscribe to (calibration reducers), or (b) it is a distinct
CRC/false-accept exposure needing its own spend (payload attempts per
profile), or (c) it has independent cost worth pricing and deferring
(cold; staged word scopes). Otherwise it stays fused inside a fire.

**The two codes.** Addresses and payload are different codes with
different deciders, and confusing them confuses everything:
ADDRESSES are BCH (127,50,t=13)->(100,23), d=27 — algebraic,
hard-decision, one-shot, no iteration budgets; decoded by placement's
word route; validity = decode within t plus the audit gates. PAYLOAD
is LDPC — belief propagation, budgeted (bp60 baseline, bp150 retry);
bp60/bp150 are decoder PROFILES on payload attempt descriptors, an
axis of attempt-space, never worker types and never placement
concerns. Certificates (zero syndrome AND CRC) exist only on the
payload side.

**Tiles pre-exist; windows animate them.** The tile map is the
declared page domain: every work key exists logically before any
pixel is read, and a tile's address is intrinsic (its key IS the
address). A placed window contributes correspondence: its pose maps
pixels onto some of those addresses, flips them ADDRESSED, and
attaches pose-borne evidence pieces. Tiles are never spawned, own no
pose (several poses may observe one tile — overlap, torn scraps; the
per-cell freeze picks owners at attempt time), and are never refined
— poses are refined; tiles are re-attempted when evidence improves
and are immutable once certified.

The lifecycle in one line: window placed -> tiles ADDRESSED ->
payload attempts (per evidence-set x profile, each a spend) ->
certificate -> tile DONE -> projection retires windows over those
pixels -> fountain solvable -> verified stop preempts everything.

## 4. Design laws

Carried from the measured record; a holo2 build that violates one of
these is wrong even if its yield looks good. Statements are compressed;
the cited source is authoritative. Each package's DESIGN.md says which
of these it enforces and in which module.

L1  **Capture identity & independence.** Source SHA-256 is the sole
    acquisition identity; derived/re-encoded rasters are not receiver
    inputs; only distinct physical acquisitions are independent (one scanner run = one file; feeding a derived copy of a capture violates this operator trust boundary — no machinery guards it).
    (RECEIVE-DESIGN §8 binding rules; e023b §7.3.)
L2  **LLR hygiene.** Calibrated LLRs combine by summation only across
    captures within one footing-equivalent evidence lane; never across
    correlated footings of one capture; never raw/uncalibrated; always
    bounded at emission. (LAYERS LLR row; 018.7; e023b.)
L3  **One owner per cell per (capture, footing).** Overlapping windows
    compete for cell ownership; they never sum. (e023b §3.3.)
L4  **Trust tiers.** Candidate facts steer search only; committed
    (audited) geometry places and anchors; certified content labels,
    suppresses, conditions. Soft evidence iterates only inside one
    attempt; only certified knowledge crosses attempts.
    (RECEIVE-DESIGN v0.50 §6.2a; color-uplift campaign.)
L5  **Certificates.** Zero LDPC syndrome AND CRC-32, minted through a
    recorded attempt with committed geometry; monotone; conflicts are
    terminal integrity failures, never voted. False-accept budget per
    attempt ≈ 2⁻³²; attempt spend is bounded by spend-once, and since the
    payload family mints one spend per ROUTE (2026-08-11) the exposure a
    lineage actually took is a COUNT — a monotone per-row counter the
    ledger fold accumulates, exact even when a later outcome overwrites
    the row (`solve.payload.crc_exposure`).
L6  **No self-training.** Uncertified payload decisions never label
    anything; certificates label only from prior commits (no
    same-attempt feedback). (RECEIVE-DESIGN §6.2/§7; e024.)
L7  **Complete-domain budgeting.** Every search route freezes its
    complete hypothesis domain H_r and per-parity support floor
    n_r = max(30, ceil(log2(H_r)/(1−h2(p_max))) + margin) before reading
    pixels; current-pixel evidence may reorder work, never narrow a
    domain, lower a floor, or truncate a rival set. Floors are
    **derived from the algebra per window size**, never fixed constants.
    (RECEIVE-DESIGN §5.3; e026; gate-constants-vs-construction-floors.)
L8  **Rival gates & quarantine.** Whole-word rival evaluation over the
    complete domain (the 0.176 lesson, FULL-DOMAIN-RIVAL-ANALYSIS); a
    legally decoded word contradicting accepted geometry quarantines its
    contributing placements (never rehabilitated; recovery is
    fresh-evidence-only). Expected silent: 1,780 known-position reads on
    record, 0 conflicts (measured).
    **BUILT IN H4 W5** (2026-08-18, H4-W5-PLAN's rulings). The rival bar
    is `pose_audit.rival_gate`, now asked by BOTH routes — the cold
    route of its map tops and the word route of its decoded candidates
    (`placement._rival_bar`), whose rival set is the other decoded
    candidates plus the winner's own geometry on every other declared
    page, which is the population the 0.176 diagnosis named. The
    quarantine is `solve/contradiction.py` (the fact) plus
    `solve/quarantine.py` (its consumer), with three rulings as code:
    DONE IS INVIOLABLE — jurisdiction is uncertified material only and
    `project_done` never reads the marking, so a condemnation moves zero
    coverage and the F-23 cache key stands unamended; scope is per
    (capture, footing), never softly compared across; and the
    condemnation IS the staleness bump on the condemned keys, so no new
    never-return mechanism exists.
L9  **Metadata & close.** Metadata trusts at GF(2) rank 24 AND ≥48
    distinct certified counters; verified stop = canonical envelope +
    SHA-256 + minimal-K + zero-padding, total or nothing. Counts are
    advice. (RECEIVE-DESIGN §9.)
L10 **Batching invariance (content level).** Same captures, any
    batching/order across invocations of one lineage ⇒ same certificate
    set and same recovered bytes. Cost accounting may be order-
    dependent; certificates may not. (e023b §1; e023c.)
L11 **Determinism split.** Per-item determinism is mandatory: same
    inputs ⇒ same proposal, all numerics seeded, no unseeded RNG,
    thread-count-invariant reductions. Scheduling order is free.
    (Keystream doctrine; 012.3.)
L12 **Observer boundary.** Diagnostics, traces and viewers are strictly
    downstream; headless runs read no clocks; observer failure cannot
    touch receiver state. (RECEIVE-DESIGN §10.)
L13 **Validation at trust boundaries only.** Interior correctness is
    types + tests; walls exist at ingest identity, evidence combination,
    certificate conflict, and commit atomicity — and are kept cheap by
    making illegal states unrepresentable. (kiss validation-boundary
    ruling, HOLO-DESIGN §2.)
L14 **Channel gate ≠ receiver.** Discovery/characterize tiers rank rungs
    and detect dead ones; they never gate or predict receiver outcomes
    (e031/e032 inversion, measured).
L15 **Status honesty.** Everything here is PROVISIONAL until a recorded
    qualification; every run says so. Availability is not qualification.
    (RECEIVE-DESIGN §12.)
L16 **One-context complexity budget.** The system — its normative
    surface and the causal chain from format string to printed dot —
    must fit one working context. Complexity beyond a single
    collaborator's view converts engineering into archaeology and
    concentrates defects at the plumbing edges (measured: the cmy8
    pooling campaign's defects clustered exactly where checklist mass
    exhausted attention, while its core mechanism was flawless).
    Structural corollaries: alias tables over registries, one mechanism
    over parallel paths, one normative doc per track, git history as
    the archaeology so living docs stay lean. (User ruling 2026-08-14.)
L17 **Guard economy.** Guards are priced by regime. Frozen/printed
    surfaces get bright-line identity anchors — oracles and goldens
    whose movement means fork, kept rare so movement stays alarming.
    Provisional surfaces get OUTCOME gates only: tests of what the
    feature does, never of how. Constructively-true arithmetic is not
    pinned (don't measure known quantities); corner-number pins wait
    for freeze; refusals defend only constructible states — the code
    path is defined by the format string. Over-guarding erodes the
    guards that matter: routine pin-editing is the habit that one day
    eats a real fork. Goldens on unprinted rows are tripwires (stop,
    decide, re-freeze deliberately), never fork-lines — freeze is
    user-declared. (User rulings 2026-08-14;
    gate-constants-vs-construction-floors; format-freeze-user-declared.)

## 5. Architecture

```
captures ──ingest──▶ survey (regions, masks, c-vote)      [capture]
                          │
                          ▼
              ┌─────────────────────────┐
              │  resource table (RAM)   │  key → (value, version, subs)
              │  = wake/idle index      │  rebuilt from state on resume
              └─────────────────────────┘
   placement workers      calibration reduces      payload workers
   (windows; poses via     (pools over window       (work keys; LDPC
    chain/hint/word/cold)   observations)            on frozen evidence)
              \                  │                  /          [solve]
               ▼                 ▼                 ▼
              ┌─────────────────────────┐
              │  commit layer (serial,  │  transactional append +
              │  transactional)         │  snapshot; versions bump
              └─────────────────────────┘  iff content changed  [core]
                          │                        │
                          ▼                        ▼
              tile map + records (authority)   trace (observer,
                          │                     ordering + samples)
                          ▼
              done-pixel projection per capture (derived)
                          │
                          ▼
              close state (K per block/stream, metadata rank)
                          │
                verified stop  ──▶  payload bytes (SHA-verified)
```

Workers run concurrently and propose; the commit layer applies proposals
serially and transactionally (the only serial point); changed keys wake
subscribed workers; the orchestrator decides which ready workers run
under the active recipe. Quiescence of all workers across all recipe
entries = session exhaustion; verified close at any commit preempts
everything (the measured 3.7× prize).

**The layering law.** Packages form a DAG:

```
core ← format ← solve                    diag observes all
core ← capture ← solve                   cli composes all
core ← engine
```

The DAG and its exceptions are DATA in `holo2/tests/test_layering.py`;
exceptions may only ever shrink, and both lists have been EMPTY since
R2. Cross-package imports go through the target package's `__init__`
surface (`__all__`, pinned in `test_surfaces.py`, and since B4 that
surface is exactly what the tree consumes — a name joins it in the same
diff as the first cross-package import of it); underscore modules
are package-private; each package declares its exception types and
cross-package code catches only declared ones, DECLARED being derived
from `__all__` (`test_error_taxonomy.py`), so a type with no
cross-package handler is not on a surface; there are no cross-package
globals —
composition happens in `cli.py` alone. Tests mirror the package tree and
obey the same DAG, with one named widening (`TEST_WIDENING`: engine
tests may import `format` and `solve` fixtures).

## 6. Cross-cutting contracts

These bind every package. Their mechanisms live in `core`; their
consequences are everyone's.

**6.1 Identity is the defining values, never order-derived.** A window IS
`(footing, region, extent)`, a pose IS its window plus its parameters, a
region IS its capture plus its support grid, a work descriptor IS
`(family, subject, route, scope)` — kept STRUCTURED, as `ResourceKey`
parts or as typed fields, never digested and never flattened into a
delimited string. No acceptance counters, no watermark ordinals (the v1
practice that makes traces non-portable), and since 2026-08-11 no id
digests either (the law restated below). This is what makes traces
replayable, subscriptions rebuildable, and spend-once meaningful across
resume — and what makes injectivity a property of the construction
rather than of a hash's luck.

**6.2 Read-sets, versions, spend-once — one mechanism** (detail in
`core/DESIGN.md`). `AttemptIdentity = tuple of (key, version-at-read)`;
a `(worker, route, identity)` is attempted at most once; idleness is an
integer compare. Versions are issued by the commit authority and are
durable, so identities are stable across resume and under replay.
Termination follows: monotone facts strictly grow and are bounded;
non-monotone fits are versioned by label pools that only grow; a
no-new-durable-fact cycle leaves every version unchanged and goes quiet
in one round.

**6.3 Commit is the single serial point.** Transactional batches
{writes, spends, wakes}, applied serially; versions bump iff content
changed; the trace is appended; snapshots follow policy. Resume is
O(state). In-flight work lost to a crash was never durable and simply
re-arms — which is why L10 holds.

**6.4 The record registry is the schema contract.** Each package
declares its record families (kind, version, structural validator,
transition law, collection membership, structural-or-not); the
composition root builds one registry, and its **manifest** — every
family name and version — is the store's schema identity. A state whose
manifest is not the build's is refused at open, naming the families that
moved. A subsystem schema change is a local diff plus a version bump,
never core surgery. Three packages publish `RECORD_FAMILIES` as a
constant and `solve` publishes `record_families(page_domain)` as a
function on purpose, not by oversight: only solve's families are
page-domain-parameterized (its structural validator keeps a committed
pose inside the domain the lineage declared), so solve alone cannot know
its own families until the session names a printed row.

**6.5 Trace and replay.** The trace is an observer-side, disposable,
append-only record of commit ORDERING plus sampled content digests (the
determinism auditor for L11 under parallel execution). Two consumers:
*replay mode* — the orchestrator consumes a recorded ordering instead of
the live queue, so any past run reproduces exactly; *pinned traces* —
qualification fixtures pin an ordering, and an answer-preserving change
must replay it byte-identically. Canonical mode ≡ replay of the pinned
trace; there is no separate canonical scheduler. Semantic changes
regenerate and re-pin, and are qualified at content level.

**6.6 No silent stages — a contract, not a lesson.** No leaf may process
more than a bounded work quantum between observer events. Quanta are
work-counted, never clock-based, so headless timing neutrality holds and
an attached observer adds wall time and nothing else. Enforced in
`core/work.py` and by a tripwire on the slow fixtures.

**6.7 Recipes and policy identity.** Policy is typed data, not a DSL —
so the identity IS that data. `SessionIdentity` carries the recipe's
entries (task classes, footing selectors, gates, prices, arms) and the
ORDERED provider ids, and a resume compares the whole value: a moved
gate, a changed price or a re-ordered provider binding refuses at open
instead of silently reinterpreting a resumed state. No hand-bumped
`recipe_id` to forget to bump; the recipe keeps a `label` for display
and it binds nothing. (What still under-binds is algorithm/decoder
VERSIONS and material numerical constants — review F-14's remaining
half, owned by `engine`.)

**6.8 Validation walls.** Illegal states unrepresentable where possible;
walls only at: ingest (capture identity binding, re-authentication);
evidence combination (structurally keyed — footing is IN the key; the
residual dynamic check is calibration-identity match at emission);
certificate conflict and metadata consistency; commit atomicity
(spend ⇔ outcome). Everything else is types, tests and the sampled trace
auditor.

### Cross-cutting contracts — three laws added 2026-08-11 (user rulings)

**The publication-order law.** A commit derives and validates its
COMPLETE delta — records, key↔record agreement, collections, blob
references — before mutating anything; store and derived views publish
as one act; nothing fallible runs after durable publication. A refused
commit leaves no durable trace. (Closes the P0 poison class:
HARDENING-SYSTEMIC-REVIEW P0-1.)

**The identity law, restated hash-free.** A durable identity IS its
defining values, kept structured: window = (footing, region, extent);
pose = window + parameters; region = (capture, origin, step); work
descriptor = (family, subject key, route, scope) as a tuple, never
flattened to a delimited string (flattening is where injectivity died).
Session identity carries the structured recipe/provider/format data and
compares by value. Hashing exists only where it is the mechanism: blob
content addresses, the source-file SHA, the trace audit. No task
numbers, no id digests.

**BUILT** (conceptual round item 2, 2026-08-11; `schema_version` 4, and
every earlier state refuses at open). The key IS the id: the record
families that carried an id field carry the values instead and rebuild
their key from them (`resource_key()`), and four of them now validate
that agreement at the commit wall and at load. Every kind has a FIXED
arity, so an embedded id occupies a known slice of its container's parts
and a concatenation cannot be re-cut — injectivity by construction, with
the review's own collision pairs pinned as tests
(`tests/core/test_identity_law.py`, `tests/solve/test_key_injectivity.py`).
`WorkId` is a structure (family, subject, route, scope), which closes
HARDENING-SYSTEMIC-REVIEW P1 "work identity is non-injective"; the
provider identity keeps its ORDER, which is the first-wins arbitration
order, and refuses a duplicated provider id at composition (P1's second
half). Region ids also lost the mask digest that used to disambiguate
two components sharing one bounding box — see `capture`'s ledger.
Deliberately NOT changed: `footing_id` is still a delimited string with
a 12-hex-truncated capture sha (capture's F-26, hygiene, and it moves
every evidence key when it moves).

**The store-trust doctrine.** Incompleteness is a failed transaction
and is caught transactionally (atomic replace, torn-tail truncation).
Auditing the integrity of our own durable store beyond transaction
completeness is a losing game and is not played: no verify-on-read
walls accrete. Files do not corrupt; they are complete or they are a
failed transaction.

### 6.8 The pixel ground-truth path (user architecture, 2026-08-15)

Adopted in discussion during W1 after two memory kills (the record is
in MEASUREMENTS, "the memory kills and their attribution"), and now
doctrine. Three stages, three laws:

1. **Raw captures are memory-mapped, never loaded.** The scan file is
   immutable ground truth read through the OS page cache
   (`capture/scan.py` already does this: `asarray(out="memmap")`).
   File-backed clean pages are evictable and cost no anonymous memory.
2. **Prepared regions are derived ground truth: built once, immutable,
   file-backed.** Per (footing, region): the region-extent float32
   with every unsupported pixel filled by the region's platen-backing
   scalar — byte-identical to v1's `prepare_region` output. Built
   streaming (row-chunked, never a second full-size temporary) into a
   memmap in session scratch; DISPOSABLE derived cache, never durable
   state (a deterministic function of capture sha + footing + region +
   mask + scalar; rebuild-or-reuse on reopen). The platen-backing scalar
   is v1's own: a median over the raster's four 32-px border strips,
   computed once per CAPTURE for the session, generation-independent
   (the build's one discovery: no full-region statistic exists in
   either tree — the borders are the population, unsupported pixels
   only ever consume the value).
3. **Consumers read through views, never copies.** A pose is an affine
   into the prepared frame; a fire holds zero-copy views plus its own
   window-sized working arrays and nothing region-sized. Anything
   genuinely region-scale to COMPUTE (the cold correlation's transform
   cache) exists only under the engine's leases — that machinery
   arrives with the cold route and is not to be imitated ad hoc.

Why it is law and not preference: at one capture the violation cost
two SIGKILLs on a 64 GB machine (a ~8 GB anonymous prepare per fire,
times the pool); at archive scale (hundreds of captures) only
file-backed derived data keeps residency an OS paging concern instead
of an architecture concern.

Conformance inventory (2026-08-16, re-verified against the tree): raw
rasters CONFORM (mmap at ingest); prepared regions CONFORM (the W1a
store); placement fires CONFORM (views only); payload fires CONFORM —
the payload family reads no pixels at all, and the per-tile cell reads
it consumes are the placement fire's own sample of the prepared plane
(`place_shared.emit_placement`), so the pre-doctrine crop the earlier
inventory named died with `placement_h3bis` at W1a. The step is
therefore taken, not scheduled, and the raw raster is an INGEST and
PREPARATION INPUT: `capture.ingest.platen_backing`'s four border strips
(once per capture, at ingest, and RECORDED — 2026-08-17) and the
streaming build, plus the attachment gate. Diag frame renders
EXEMPT (small, observer-side).

**The prepared plane is the durable pixel** (2026-08-17). Because no fire
reads a raster, the pixels a resume needs are the `<state-dir>.prepared`
files, and those survive a crash. Everything their name is a function of
is now durable too — the backing scalar was the last hold-out and joined
`CaptureRecord` — so `plane.prepared_region` has a REUSE-ONLY door
(`prepared.open_prepared_region`, no `Raster` argument) and the M12 gate
answers "attachable" on either source, raster first. A session with no
raster can open what exists and can never build what does not; reading a
size-checked file this session did not write is safe because a re-earn
verifies every batch id against the journal, so a stale plane refuses
loudly instead of certifying quietly.

The inventory is no longer prose alone. `test_conventions
.test_raw_pixel_reads_stay_on_the_prepared_path` holds the entitled
modules as data — the raster exposes pixels through `crop_luma` /
`crop_native` and nothing else, so the allowlist is exact — and
`test_prepared_evidence_e2e.py` (last at `holo2/measure/`, deleted with
the measure cleanup; this byte-identity comparison has no surviving
holder — history has the driver) pinned the CONSEQUENCE: one clean
render, every word-route fire run twice, and the staged evidence (LLR
plane, observed bitset, pose, calibration) byte-identical whether the
pixels came from the prepared store or from `prepare_region` off the raw
raster.

Derived footings hold no pixels in this tree: a `FootingSpec` is
`(id, ppc, capture)`, ingest "does not manufacture decimated footings"
(`capture/scan.py`), and placement reads the NATIVE footing, which is
the mapped one — so `scale_space`'s memmap arm has no production
caller to flip. Ingest's cost is a transient PEAK, not residency: the
carried E021 survey materialises one float32 feature-luma crop per
bounded tile, and peak process RSS runs ~8x the native raster's bytes
before falling back to the memmap plus the support masks once the
survey returns (fixture-scale, 268 MB raster: 61 MB before, 2,157 MB
peak, 517 MB after). The tile's own side is `TENSOR_TILE_CELLS`, a
declared work-set control with no effect on the output. Whether that
peak is worth banding is a survey question, not a footing-residency
one, and it wants the real sheet's before/after.

### 6.9 The pull scheduler and the wall's two amendments (H4 W2, 2026-08-16)

Normative detail: `H4-W2-PLAN.md` ("THE PULL MODEL — RULED" + the two
concurrency rulings), `solve/DESIGN.md` (the scheduler and the job),
`engine/DESIGN.md` (the scheduling contract), `core/DESIGN.md` (the
merge hook). This section is the constitution-level summary.

**The pull scheduler (the user's design).** Hints are not facts —
they are scheduling annotations, and nothing about placement
scheduling is durable. One in-memory worklist per session: windows
exit by PLACED or by COVERED (done does not imply placed —
overlap lets a window's extent certify through neighbours' poses),
readiness is one bit, an acceptance pings its ring and its covered
finer windows, and a worked window CONSULTS the committed poses at
fire time — extrapolate, sort by the ratified distance, truncate,
minus its in-memory tried set, whose size prices the rival gate's
floor. The routes are one per-window job: empty consult -> word;
ping -> ring consult; dry -> wide consult (nearest-K + the
regional-affine seed) -> cold (W4). Tiers compete in ONE global cost
order with payload, dear tiers gated on instantaneous dryness.
Resume re-derives everything from the store; a crash loses no
scheduling state because there is none. AMENDED at W3: the set was
monotone-SHRINKING and now GROWS by subdivision and by nothing else —
a window that exhausts its ladder on one of v1's eligible refusals
adds its four corner windows as ordinary members, at a small child
premium so the sheet is exhausted before anything specializes.
Termination is bounded arithmetic (at most once per window, depth cap
1, the 70-cell floor), and the growth is invisible to the durable
state: children get ordinary window records and no lineage field
(`solve/DESIGN.md`, the monotone-growth amendment).

**Wall amendment 1 — the commutative merge (the fourth registry
hook).** A family may declare `merge(key, current, proposed)`;
the wall applies it against the record it CURRENTLY holds, as the
serial section's first act — an atomic fetch-and-union, not a lock
on any worker. The tile family declares its carry algebra (observer
union, monotone flags, certified content verbatim; two DISAGREEING
certified contents remain fatal, checked inside the merge; two
agreeing ones corroborate). The post-merge record is journaled, so
replay re-applies verbatim; version validation is projected out for
merge-declared kinds only — everything decision-shaped keeps
compare-and-swap. The system named honestly: optimistic
transactions with the wall as manager; merge-declared kinds are its
commutative-update statements.

**Wall amendment 2 — start markers (journal schema 7).** Every
dispatched pass appends a payload-free marker whose POSITION in the
journal is the snapshot prefix the fire saw; markers fold to
nothing. Replay and crash recovery are marker-driven: launch the
named pass at its marker against the store as of that position,
reap at its commit; a marker with no commit is a non-committing
pass everywhere, including the crashed tail — it rebuilds in-memory
scheduling state and invents no commit. Pooled recorded orderings
replay exactly in the constructed-mechanism pin; the real-stack
residue (a pass's in-memory reads happen at run time, not dispatch)
is scoped honestly in `core/journal.py`, with
freeze-consult-at-dispatch as the known fix — which is also what
would make placement fires process-shippable (the parallelism
line, MEASUREMENTS "H4 W2 EXIT" row: vectorize -> free-threaded
experiment -> stateless process pool; thread ceiling under the GIL
measured 1.01x).

## 7. Direction recorded, not built

**Deciders** (user proposal 2026-08-10; implementation post-refactor).
The recipe's gates and prices generalize: the orchestrator collects work
descriptors and offers them to one or more DECIDERS, which answer
"reasonable to do?" and "at what cost?"; the orchestrator ranks, parks
and resumes on those verdicts. This is the eligibility/desirability
split — LAW (spend-once, done-gate, residue-targeting, interference)
stays in engine and commit and is never decider business; DESIRABILITY
is decider policy, tunable and measurement-fed (route cost tables from
the health ledger; VALUE signals such as per-`(stream, block)` close
shortfall, so work feeding a rank-short block outranks work feeding a
surplus one).

**Block-level DONE** is its negative half (user 2026-08-10): once a
`(stream, block)` is SOLVED — rank-complete per the last consult;
count + surplus is only the proxy between consults — work whose sole
product is another symbol for it has zero close value and parks, unless
its residual value terms pay: calibration labels and halos for live
neighbours, chain anchors, and done-projection retirement (a cheap
certificate that erases a window's future search can be net-positive
with zero close value). Recorded cost: suppressed surplus certificates
shrink the surplus audit's sample; a bounded audit-sample knob is the
mitigation.

Constraints on any implementation: deciders reorder and park, **never
forbid** (L7 verbatim; decider-parked work is reported parked, not
exhausted, and is always resurrectable), and verdicts are pure functions
of committed state — never of queue timing or clocks (replay,
confluence). Lineage of the idea: v1's `tail_ev`, the priced cold
boundary, DONE-GEOMETRY §6's "priced exhausted state… always
resurrectable", D8's count gate — all point solutions of this shape.

**The migration endgame** (user, 2026-08-14). When `src/holo`'s
generation and format tracks migrate in, holo2 is a CLEAN BREAK, not an
accretion. Keep only the current decoders — K, CMY8-v1 (pooled), and a
CMY7 revision on the same spine — and only c2/c3 cell sizes. Exactly
ONE fountain symbol scheduler: the pooled multistream form, with K as
its `n_streams=1` identity (the pooling campaign's bit-identity proof
is the migration bridge, not merely a fork guard). Printer profiles
become aliases to `{tx×ty}` geometries; codec profiles (max, resilient,
…) become aliases to coder/decoder + rung + q tuples; registries
collapse into tables of names, shrinking the format kernel toward the
R3 printed preface BOOTSTRAP-DESIGN wants anyway. The `-v0` per-stream
colour fountain paths are DELETED here, not carried: **the archive
contract attaches to READERS, not to living code** — `src/holo` remains
the legacy reader for every printed `-v0` sheet, exactly as `paperholo`
reads printed v2–v4 today. Append-only is a within-generation rule;
between generations the break is clean. Promises follow the same
economy: the planner REPORTS which promise tiers a volume carries at
its dial (the 2026-08-14 dial ruling — report, don't refuse); q is
operator authority.

**"only c2/c3 cell sizes" IS SUPERSEDED — THERE IS NO PITCH SCOPE**
(RULINGS H1(a), 2026-08-22 evening: "why don't you want to support the
c4 line? the c4 format is just `1i150-k-r0550@26x18`"; the ruling reads
"every registered pitch class (c1..c4) and every lawful rational
builds"). The route there ran through C3 (RULINGS G4), which restated
the sentence above as a pitch set `format_v1.SCOPE_PITCHES = {1/300,
1/200}` inch — a CELL SIZE was never a receiver concept, being a dot
count that needs the dpi of an engine this receiver never observes — and
then the set had nothing left to defend: px/cell is `pitch_in x
dpi_true` at any pitch, and nothing below the survey's candidate set is
c2/c3-specific. A refusal whose remaining ground is "holo2 has never
read one of those" is guard mass over a measured fact (L17, P11).

**C3b executed it** (2026-08-22): `SCOPE_PITCHES` and `scope_refusal`
are DELETED with both refusal sites (`format_v1._k_coding`,
`registry_rows.FormatRowSpec.__post_init__`), the H4 row of
`test_format_lattice`'s catalogue and its `HOLO2_SCOPE_REFUSALS`, and
`test_oracle_lattice.SCOPE_REFUSALS` — whose five ids
(`c4-k-r0550@26x18`, `c1-k-r0700@10x10`, `1i400-k-r0700@40x28` and the
two colour twins) moved up into `K_BUILDABLE`/`COLOUR_BUILDABLE`, where
every codec fact is compared member by member against `src/holo`'s own
answer. e033 sheet A's `L:c4-r0550@1664x1152` landed in the same
package as the twelfth fossil: the printed sheet is keyed by the v1
seed, and its v2 twin `c4-k-r0550@26x18` seeds under `holo/v2/` — one
physical format, two keystreams. The clean-break intent of §7 is
untouched; what went is a refusal, not a capability.

## 8. Freshness doctrine

Nothing here is final and nothing is owed backwards compatibility.

- No shims, no compatibility layers, no dead code, no "legacy" branches.
- Pre-freeze schema rule: a breaking change refuses old states loudly,
  naming the record family that moved. No migration decoders.
- Re-encoding durable data is permitted as a deliberate, bigger step —
  say so, do it once, and re-earn the gate that proves it (the
  e018b/e023c → `src/holo` precedent).
- Delete transient scaffolding when its phase ends.

The operational form of the same rule is `ENGINEERING.md`.

## 9. What is deliberately absent

No barrier lanes, no rung-major driver, no per-lane evidence namespaces
as *schedule* (footing tags carry the evidence identity instead), no
durable placement audit (a committed pose is its own witness; gate
parameters are policy data), no automatic evidence pruning at
certification (DONE schedules, never deletes), no event-sourced state
(the store is the authority; the trace documents ordering), no
migration/compat decoders.

**Corrected 2026-08-10 (R4).** Two statements this section used to make
were not true of the implementation and are withdrawn:

- *"no durable attempt ledger (spends fold, as in v1-kiss)"* — the
  spend ledger is durable and complete: every `(worker, route,
  identity)` is retained in the envelope forever, with its outcome
  string. That is what makes idleness survive resume, and it is also
  the deviation D1 (spends were supposed to FOLD to the latest identity
  per `(worker, route)`; versions are monotone, so nothing else is
  reachable) — §15, owned by `core`. Per-route provenance stopped being
  a gap on 2026-08-11: the payload family mints one spend per route, so
  the ledger names the route and the certificate names the decoder that
  ran (`MintRef.route` / `decoder_profile`), and L5's false-accept
  exposure is countable off the ledger. What is still absent is a
  durable ledger of attempt PROFILES beyond those — the residue of
  F-06, owned by `solve`.
- *"a canonical-JSON envelope, cheap to snapshot"* — measured, it is
  not: 128–279 ms per snapshot of an 8.05 MB envelope, 98.1% of wall at
  per-commit cadence (MEASUREMENTS M-3.4). The premise it lost was
  "stays small": D1 is what made the envelope grow without bound, so
  the fold is the repair and the snapshot mechanism is not (§15, D3).

If space pressure ever measurably binds, the one sound relief is
**compaction** (explicit, user-invoked, never a certification side
effect): evict a tile's blob-backed observation pieces only when the
tile AND every tile any still-fireable calibration scope could reach
from it are DONE (the closure radius is per quantity — one-cell halo for
K ctx, 8-neighbourhood for the colour matrix, the whole region for
region-pooled fits). Eviction, not destruction: pieces are deterministic
functions of (raster, pose, calibration record). Certified bits,
metadata bits, poses, windows and calibration records are never evicted.

## 10. Qualification (bars, not predictions)

- **Ground truth**: format v1 goldens and `src/holo` generation; frozen
  synthetic corpora; the real print-day captures with verified payloads
  (e029 c2-r0700 465,580 B; e032 c2-cmy8 718,413 B, c2-r0700 465,580 B,
  c3-cmy7 301,600 B) — holo2 must recover the same bytes from the same
  scans.
- **Bars**: zero wrong certificates, always; certificate-set parity or
  better vs `src/holo` on the same captures (yield = certified tiles);
  byte-equality for carried leaves on shared fixtures; pinned-trace
  byte-equality for answer-preserving changes; wall/CPU against the
  measured v1 anchors — noting that no real-volume wall exists for v1,
  so the honest comparison is counts plus holo2's own first-ever walls,
  labeled as such.
- **Status**: PROVISIONAL until the user declares otherwise; every run
  warns (L15).

## 11. Out of scope

Format changes of any kind; generator/characterize work; discovery mode
(multi-row) — the exact row an operator names with `--format` first
(`--coding` until C5, 2026-08-22); GPU; distributed execution;
the paperholo legacy reader; promotion of any constant to "qualified".

## 12. Open rulings — the index

Adjudication happens in the owning package's doc, which carries the
argument and the evidence. This table is the map.

| OR | subject | owner |
|---|---|---|
| OR-1 | done-projection erasure extension | `solve` |
| OR-2 | label channel for fully-done windows | `solve` |
| OR-3 | flip-canary sampling over done windows | `solve` |
| OR-4 | tile-map gate vs region-granular L1 | `solve` |
| OR-5 | eager-payload BP budget / per-key ceiling | `solve` |
| OR-6 | snapshot cadence, fsync, trace retention | `core` |
| OR-7 | subscription radius (done-gate vs chain-hint) — motivating measurement recorded 2026-08-12 (wave-2 HEALTH row: whole-region radius costs 23.27 wakes/commit and doubles placement identities under B7's collections; the true dependency is the geometric overlap neighborhood) | `solve` |
| OR-8 | worker pool: threads vs processes | `engine` |
| OR-9 | window split policy + snippet floors table | `solve` |
| OR-10 | quarantine scope in the dataflow model | `solve` |
| OR-11 | cold cache grace period; child zero-padding | `solve` |
| OR-12 | **CLOSED (R3)** — RegionRecord carries its capture parent and support-grid geometry | `capture` |
| OR-13 | **CLOSED (2026-08-22, user ruling + the lead's added rule)** — the CLOSE-POLICY AXIS: greedy / `--complete` / `--no-close` are three points on one dimension, so the pair is legal and redundant. `--no-close` never enters a deciding consult mode, the fold SKIPS the close record (a read-time policy: the journal is never rewritten), the session ends OPEN and exits `EXIT_OPEN` with no fountain-shortfall claim. Rules: *a close is terminal only while it is the last word* (a close with commits after it is SUPERSEDED — dropped at the fold under every policy, recomputed and APPENDED by the next closing run); an `integrity_failure` close is neither skipped nor superseded and refuses by name; a `--replay` runs under the close policy its journal was recorded under. Crosses `core` (the fold), `engine` (the policy + the replay contract) and `cli` (the flag + the epilogue) | `engine` |

The adversarial review's findings (F-01…F-26) are mapped to owning
packages in `WORKPLAN.md`; each package's DESIGN.md carries the ones it
owns, with what R1–R3 already closed.

## 13. Section map (v0.1 → v0.2)

Module docstrings across the tree cite v0.1 section numbers by the
hundred. They are not rewritten — this is the forwarding table, and a
citation of the form "DESIGN §5.4" resolves through it. New prose cites
the package doc directly.

| v0.1 | now |
|---|---|
| §0 why restart | §1 |
| §1 two truth planes | §2 |
| §2 vocabulary | §3 (glossary) |
| §3 design laws L1–L15 | §4 (unchanged, same names) |
| §4 architecture overview | §5 |
| §5 data model | each package's "Owned record families" |
| §5.1 session / captures | `engine` (`SessionIdentity`), `capture` (`CaptureRecord`, `FootingSpec`) |
| §5.2 the tile map | `solve` |
| §5.3 physical-plane records | `capture` (`RegionRecord`), `solve` (pose / hint / window) |
| §5.4 evidence | `solve` |
| §5.5 attempts, spends, close | `core` (spend ledger, `CloseRecord`), `solve` |
| §5.6 resource table + store | `core` |
| §6 done-pixel projection | `solve` §6 |
| §7 read-sets, spend-once, idleness | §6.2 + `core` |
| §8 worker families | `solve` + `solve/PROVIDERS.md` |
| §8.1 placement / cold | `solve` + PROVIDERS PL1–PL7 |
| §8.2 window geometry, derived floors | `solve` |
| §8.3 payload workers | `solve` + PROVIDERS PY1–PY5 |
| §8.4 calibration scopes | `solve` + PROVIDERS CA1–CA7 |
| §9 orchestrator + recipe | `engine`; the deciders stay here at §7 |
| §10.1 execution and commits | §6.3 + `core`, `engine` |
| §10.2 identity discipline | §6.1 |
| §10.3 trace, replay, diagnostics | §6.5, §6.6 + `core`, `diag` |
| §10.4 deliberately absent | §9 (two claims corrected there) |
| §11 validation model | §6.8 + each package's walls |
| §12 qualification | §10 |
| §13 carry-over inventory | each package's "Carried leaves" |
| §14 out of scope | §11 |
| §15 open rulings | §12 (index) + the owning package |
| §16 references | §14 |

## 14. References

DONE-GEOMETRY.md (census §8a); PLACEMENT-IMPROVEMENTS.md;
PHASED-SCHEDULE.md (D1–D20); RECEIVE-DESIGN.md v0.49–v0.51;
RECEIVER-GROWTH-AUDIT.md; WIRING-IMPROVEMENTS.md;
PAYLOAD-MEASUREMENTS.md; CANARY-D5-DISAGREEMENTS.md;
LABEL-SAMPLING-SHAPE-ANALYSIS.md; FULL-DOMAIN-RIVAL-ANALYSIS.md;
`.claude/memories/{e021,e023b,e023c,e024,holo-v1-kiss-branch}.md`;
experiments/029, 030, 031, 032.

## 15. TO-FIX — the system ledger

Known defects, one line each. **D-n** are the deviations from the
founding design dialogue (coordinator's audit 2026-08-10, authoritative);
**F-nn** are the adversarial review's findings, carrying its severity
scale (BLOCKER / HIGH / MEDIUM); **S-n** are cross-cutting items with no
single owning package. Detail lives in the owning package's own TO-FIX
ledger — this table is the map, as §12 is the map for rulings. A row
leaves the ledger when the defect is gone, and says CLOSED with what
closed it until the next re-cut.

| id | defect | source | owner | sev |
|---|---|---|---|---|
| D1 | CLOSED (WP-1) — the ledger folds to the latest identity per `(worker, route)` with an `attempts` counter and a read-set-shrink refusal; schema 3, old states refuse. Was: every historical identity retained as full tuples | audit 2026-08-10; `core/identity.py`; F-16 | `core` | BLOCKER (scale) |
| D2 | CLOSED with D1 (WP-1) — the retained-row residue folded; the live identity was already O(1) since R1/M11 | audit 2026-08-10; `solve/close.py`; F-16 | `core` | BLOCKER (scale) |
| D3 | D1+D2 broke the envelope's "stays small" premise, and the whole-envelope snapshot is what M-3.4 priced; the fold restores the design, delta frames are then optimization, not rescue | audit 2026-08-10; MEASUREMENTS M-3.4; F-16 | `core` | BLOCKER (scale) |
| D4 | MECHANISM CLOSED (conceptual round item 1) — RecordFamily.validate is key-aware at commit AND load; publication-order law in force (full-delta prevalidation, atomic store+table publication, F-18 closed structurally). Identity half CLOSED 2026-08-13 (F-07's cheap half, with F-11): NINE adopters — every family that can prove its own name — on one published `core.require_own_key`; the two abstainers say why (a tile carries no component of its work key, a close is the keyless singleton) and a hint proves the source half of the two its key names. Residue: relational checks absent (F-07 residue, core ledger) | audit 2026-08-10; F-07/F-08 | `core` | BLOCKER |
| S6 | CLOSED (conceptual round item 2) — the identity law is built: ids are their defining values as structured keys, `WorkId` is a structure, the provider identity is ordered and duplicate-refusing, `SessionIdentity` binds recipe entries + provider ids by value. Was: HARDENING-SYSTEMIC-REVIEW P1, work identity non-injective (kind drop + unescaped join) and provider identity erasing the order that decides arbitration | review P1; `core/keys.py`, `core/work.py` | `core` + `engine` | HIGH |
| D5a | the trace is not bound to a durable checkpoint: no durable cursor, and at `snapshot_every > 1` it can describe commits the envelope does not hold | F-24 | `core` | MEDIUM |
| D5b | "no silent stages" (§6.6) is a bound, not a live signal — progress accumulates privately and publishes at fire end | F-22.3 | `core` (mechanism), `diag` (surface) | HIGH |
| D5c | resume with only a new capture fails on the older capture's footing metadata | F-05 | `capture` + `solve` | BLOCKER |
| S1 | CLOSED (WP-2 + sweep) — format's class renamed `CertifiedSymbolConflict` via a declared carry adaptation (oracle RENAMED_SYMBOLS row); stale references swept from solve/tiles comment + oracle comment | F-11 | `core` + `format` | HIGH |
| S2 | CLOSED (WP-5/15) — `write_payload` creates its temp EXCLUSIVELY (`mkstemp`) in the target's own directory, fsyncs the file, publishes with `os.link` (atomic, and it refuses an existing target, so no-overwrite is the filesystem's guarantee and not a check with a race behind it), then fsyncs the directory. Was: `exists()` then `replace()` through a SHARED `.partial` name two runs on one `--output` could hand each other half-written, and no fsync at all | F-25 | `cli` | MEDIUM |
| S3 | the bare CLI still runs `snapshot_every = 1` (57x the close-only wall, M-3.4); every recorded real run passed 512 through the API knob | OR-6 | `cli`, ruling `core` | — |
| S4 | per-package coverage is reported nowhere — `pytest-cov` is still absent from the venv | MEASUREMENTS §COVERAGE | tooling | — |
| S5 | CLOSED — both ruled 2026-08-12 (worklist B14). **Q1: VERY in-tree only** — provider genericity is a complexity bound (narrow interfaces, uniform observable behaviour, each family independently reasoned about, debugged and optimized), not an external marketplace; third-party providers are unpromised and protocol slack serving only them is deleted. **Q9: confirmed as built** — provenance is the minting attempt (route + decoder + pose) plus its declared `MintRef.contributors`, never an accumulating supporter set; L5 makes the first certificate terminal and race-losers contribute observations only | review §Questions | user | — |

**D1's fix direction is RULED** (audit, 2026-08-10): fold to the latest
identity per `(worker, route)`, plus counters. **No digests** — a
digest-based compaction was proposed and explicitly retracted; versions
stay the identity mechanism. F-16's SQLite/WAL recommendation is
therefore **not adopted**: the fold restores the founding design first,
and only a measurement taken after it may reopen the storage engine.

D3's only measured prices are M-3.4's, taken on the 100-tile toy corpus
(8.05 MB envelope, 128–279 ms per snapshot, 98.1% of wall per-commit).
**No real-page snapshot cost is recorded in this tree** — the R3-exit
real run wrote 4,006 commits at `snapshot_every = 512` and its snapshot
share was not separated. Any per-commit figure at page scale is an
extrapolation until someone measures it, and it should be labelled one.
