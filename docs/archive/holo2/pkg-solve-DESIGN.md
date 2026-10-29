# solve — DESIGN

Placement, payload, projection: the algorithms. solve turns pixels plus
format truth into proposals — cell/pixel geometry, the word-grid placer,
the photometric calibration fits, the per-tile certification chain, the
tile-map projection that says what is already done, and the providers
that expand all of it into schedulable work. Imports `core`, `format`,
`capture`.

Constitution: `holo2/docs/DESIGN.md`. Provider census (every future
consumer/producer of the work protocol, written down before the protocol
froze): `PROVIDERS.md` — **read it before adding a family**. Public
surface + rationale: the `__init__.py` docstring.

## Purpose

Three things, and the machinery between them:

1. **geometry** — `geometry` (cell↔pixel lattices), `plans` (region
   lattices and the pose-free window plan), `plane` (the derived world a
   session schedules over, and what a worker sees);
2. **proposals** — `place_sched` + `place_job` (the pull model's
   scheduling set and its one job: real pixels → poses) on the ported
   E022 kernel (`pose_fit`, `pose_audit`, `words`, `reference`,
   `place_model`) plus `place_shared` and `placement`'s shared
   vocabulary, `payload` (frozen evidence → certificates; named
   `payload_h3bis` until the W6 lineage fork) on
   `tiles` + `detect`, `close` (the volume close as the engine's TERMINAL
   CONSUMER, B12). `toys` — the H2 architecture proof — was DELETED at
   H4 W1b (H4-PLAN R11); the rendered-fixture real-family rigs in
   `holo2/measure` (and the distilled `holo2/measure/verdicts`) are the
   architecture proof now;
3. **the logical authority** — `records` (the tile map and everything
   around it) and `tilemap` (its indexes and the §6 done projection).

## Public surface

`holo2.solve.__all__`, pinned by `holo2/tests/test_surfaces.py`. Since
B4 it carries no exception type (`TileMapError` is raised and handled
inside solve) and no interior geometry: `SessionPlane`, `CaptureView`,
`PlaneView`, `RegionView`, `WindowPlan` and their builders came off,
because the engine receives the plane as `core.SolveView` and never
looks inside — which is exactly why nothing outside solve ever imported
their classes. `toys` came off with them in B4 (not production surface)
and was deleted outright at H4 W1b.
`solve` is imported by `diag` (read-only) and by the composition root;
the engine never imports it.

## Owned record families (R3) — most of the data model

| family | kind | version | invariant |
|---|---|---|---|
| `TileRecord` (+ `MintRef`) | `tile` | **4** | the logical authority. Certified content never changes, and `observed_by`/`baselined` only GROW — a certified tile still gains observing footings, because done projection needs every committed observation of a certified key. Registered WITH the family (`_tile_transition`), so the commit layer applies L5 without knowing what a certificate is. v2: `MintRef` names the ROUTE and the decoder profile that minted the certificate (required, never empty); `baselined` = the footings whose scan ran a decoder here and failed — the durable per-footing fact the retry route derives from (same version: same conceptual round, no committed state carried the earlier v2 shape). v3: `MintRef.attempt_digest` deleted — a digest of an identity the spend row's own values already name (F-27). **v4 (2026-08-14, F-06's last residue): `state` deleted.** The enum carried nothing the other fields cannot: `certified` is a PROPERTY (`minting is not None`), the eligibility domain is "a record exists and is not certified", ADDRESSED is the record existing, and retry eligibility has gated on `baselined` since 2026-08-11. The monotone-state half of the transition law went with it (constructively true), and the three named constructors collapsed into one merge, `carry_tile`. `TileState` survives in `tilemap` as DISPLAY vocabulary. F-07's relational half (2026-08-13): a certified tile DECLARES its minting pose and every contributor as references the wall requires to exist — below a certificate nothing is declared, since footing ids are not keys |
| `PoseRecord` | `pose` | **5** | committed geometry = trust tier 2. Its window, its page and its affine ARE its identity (`pose_key`, the affine terms as `repr(float)`); `page` is validated against the session's declared page domain at composition time, and the footing it names must be its window's. F-07 relational (2026-08-13): declares its WINDOW — the placement fire that accepts a pose writes the window record in the same batch, or it already stands. **v4 (2026-08-15, H4 W1)**: the affine is CANONICAL — six native-pixel decimals and no negative zero, applied at construction (`canonical_affine_terms`), so the key and the value it names cannot disagree and the fitter's noise terms (measured max 9.74e-7) collapse instead of minting distinct keys. Canonicalisation, not deduplication: equivalent-fit jitter (1.2e-3) is orders above any addressing-safe quantum. **v5 (2026-08-18, H4 W5): `quarantined`** — the first non-identity field this family has had, so the transition law it went four versions without is now WRITTEN (`_pose_transition`): the marking may go `False -> True`, once, and nothing else about a committed geometry may move under its name. A marked pose is RETAINED as a record (the contradiction fact names it, and an audit reads it back) and never offered by a consult. `tilemap.project_done` deliberately does NOT read it — done pixels are certificate-backed, so a condemnation moves none of them and the F-23 cache key stands unamended (ruling 1, pinned in `tests/solve/test_quarantine.py`) |
| ~~`HintState` (+ `HintEntry`)~~ | ~~`hint`~~ | — | **DELETED, not deprecated** (H4 W2's pull model, ruled and swept 2026-08-16; ruling Q7, "aggressively trash what doesn't fit"). §5.3's candidate facts were a durable record for one day: one state per window, a retention law at the wall, source poses declared, structural because a chain descriptor existed only where one did. The insight that killed it is the user's — **a hint is a scheduling annotation, not a fact** — and promoting one to a record is what bought the improve-only law, the concurrent-merge collision, the ring-key identity binding and a subscription per neighbour. What the record CARRIED all survives as arithmetic: the ratified distance is `place_job.hint_distance` (the consult's sort key and the scheduler's priority, anchors unchanged — adjacent exactly 1.0, colocated donor exactly 0.0), the top-few truncation is `place_job.CONSULT_KEEP = 8`, and the portfolio is recomputed at every fire from the committed poses, so nothing can be stale and nothing needs retaining. The kind is unregistered: a state written before the sweep refuses at open (R3-lawful, DESIGN §8). |
| `WindowRecord` | `window` | **5** | one working set of cells on one footing, and what BECAME of it. Footing, region and extent ARE its identity (`window_key`); the record carries no id field and the family validates the agreement. F-08 (2026-08-13): RETIRED is terminal with an immutable reason (`_window_transition`), and the reason rides exactly the RETIRED status, checked at construction. **v5 (2026-08-16, H4 W2's pull model, ruling Q2): the status vocabulary is OUTCOMES only.** PENDING and SLEEPING are gone with the scheduling they described — readiness, the tried set, the stage memory and the priority are the scheduler's, in memory (`place_sched`), and nothing durable says a window is being worked on. ACTIVE is written by the fire that PLACES the window (the population the census and the observer read is these records), so the only lawful move left is ACTIVE -> RETIRED, and in practice even that does not happen: a placed window leaves the scheduling set. v3: `routes_spent`/`RouteSpend` deleted — §5.3 declared a per-window spend projection that NO layer ever wrote (the one writer in the tree was a test fixture) while the durable ledger held the authority; a projection, if ever wanted, is a read over the ledger, not a stored field that changes on every re-arm. F-07 relational (2026-08-13): declares its REGION — windows are planned off durable regions, and the reference makes that ordering law |
| `EvidenceObservation` | `evidence` | **4** | the durable payload atom. Footing IS in the key, and exactly ONE pose — whose own key rides in the pose's place, so the geometry a piece was read under is readable off the key. Carries `observed_ref`, the packed cell bitset. F-08 (2026-08-13): content FROZEN under its key (`_evidence_transition`) — a lawful re-fire re-derives equal bytes (§9 determinism), and H5's re-score semantics, if any, arrive as a declared amendment. F-07 relational (2026-08-13): declares its POSE and its CALIBRATION — the provenance a certificate inherits, so a piece may not cite a fit nobody committed. **v4 (2026-08-18, H4 W5): `quarantined`, and the DECLARED AMENDMENT the F-08 note above promised.** A write that sets the marking and moves nothing else is lawful — a condemnation is a judgement ABOUT the piece, not a revision OF it, so the LLRs, the observed mask and the calibration stay as frozen as they ever were. The write is also W5's whole staleness mechanism (ruling 3): it bumps the key's version, so an in-flight payload attempt that named this piece dies at the wall's existing check. `payload.route_evidence_keys` drops a marked piece from the READ-SET, which is what makes the exclusion total rather than cosmetic. **The amendment's SECOND instance (F1, 2026-08-23, ruling J2-2): the DERIVATION moved.** `observed_ref` now packs the tile mask AND its one-cell context halo — 577 bytes where it was 512 — so the same (raster, pose, calibration) does not re-derive the same bytes across the F1 line. No version bumps: the blob is SHAPE-VERSIONED BY LENGTH and leading-bit compatible (the tile mask is still bits 0..4095, so every reader but `records.unpack_piece_halo` is untouched), a 512-byte and a 577-byte piece are both lawful content under one key family, and what enforces no-rewrite is EXISTENCE — `place_shared` proposes a piece only where `view.record(key) is None`, so a pre-F1 piece is never re-derived. A resumed pre-F1 state may hold both shapes on one tile; the freeze takes such a component back to tile-scoped bins whole |
| `LabelPool` | `pool` | 1 | a calibration reduce's scope descriptor. F-08 (2026-08-13): grow-only at the wall (`_pool_transition`) — §6.2's "label pools that only grow" is now law, stated before its CA1–CA7 writers exist. F-07 relational (2026-08-13): DECLARES NO REFERENCES — a transition law constrains a STANDING record and can be stated blind, but a reference law constrains a writer's batch shape, and its members are window keys, which are plans long before they are records |
| `LatticeSeedRecord` | `seed` | 1 | H4 W1/R5: one reciprocal lattice seed per (footing, region), sourced from the best-supported window's UNCONDITIONED fit. v1 kept this as first-fit-wins shared mutable state (`RegionContext.lattice_f`), which made small-window poses depend on fit ORDER; the transition law here admits a replacement only from a better-supported source, ranked `(-support, window)` — v1's own wave-front key — so the standing record is the maximum of the proposal set whatever the schedule. Declares its REGION and deliberately not its source window: the fit that measures a seed may be the one that then refuses its own phase objective and writes no window record at all |
| `WordContradiction` | `contradiction` | 1 | H4 W5/L8: a legally decoded address word at a KNOWN position naming a tile its geometry did not. v1's `BchConflictRecord` as a durable record, keyed on the contradicted POSITION AT ONE FOOTING (ruling 4's (capture, footing) scope, made structural) and carrying BOTH sides' full contributor sets in `MintRef.contributors`' shape — the placements whose reads formed the word, and the placements that already assert the position. COMPLETE AT MINT, so the family is FROZEN (`_contradiction_transition`): both sides are known at reduce time and a write that revised one would be out-voting the containment after the fact. Declares BOTH sides' poses as references, which is also what makes the born-quarantined decoded side lawful in one batch. Its consumer is `solve/quarantine.py`; its jurisdiction is UNCERTIFIED material only |
| `CalibrationRecord` | `calibration` | **2** | a fit plus its held-out gate verdict (adopted / refused with reason). Scope + algorithm + the parameters' blob content address ARE its identity, so two different fits of one window are two calibrations and identical ones are one. F-08 (2026-08-13): FROZEN incl. the verdict (`_calibration_transition`) — adopt-or-refuse is never out-voted after the fact. F-07 relational (same day): declares its SCOPE, whatever kind it is (a window today, a pool when the reduce lands) |

solve publishes `record_families(page_domain)` rather than a plain
tuple: the pose validator is bound to the session's declared page domain
at composition time.

### The tile map

One record per `(page, ty, tx, stream)`, allocated lazily over the
declared page domain — a key with no record occupies no storage.

- **the record's presence is the addressing fact**: at least one
  committed pose covers the tile in some capture. A **scheduling fact**,
  never an evidence weight (L4);
- **the mint is the certificate**: `TileRecord.certified` derives from
  `minting`, and certification is terminal PER WORK KEY. Streams are
  separate work keys, so a CMY8 tile with only C certified is NOT done
  and its pixels are not done-projectable;
- conflicting certified bits are fatal (L5).

#### The tile map is the tree's ONE commutative family (H4 W2, ruling 1)

`join_tiles` is its algebra, declared to the wall as the record
registry's fourth hook (`merge`, after validate/transition/references)
and applied by `core.commit` against the record the store holds when a
proposal lands. `carry_tile` — the write every worker makes — is that
same function with the caller's gain expressed as a record, so "the fire
and the wall run one algebra" is an identity in the code rather than two
implementations that have to agree.

**Why a join is lawful where compare-and-swap was not.** `observed_by`
and `baselined` union; certified content is carried verbatim. ⊔ is
therefore idempotent, commutative and associative, and a fire's snapshot
always sits BELOW what stands now, so `current ⊔ proposal` is the same
value from any snapshot. A proposal is its own operation input — nothing
extra crosses the wall, no delta encoding, no "what I gained" channel.
On the serial lane the store still holds the snapshot the fire read, so
`current ⊔ proposal` IS the proposal: the batch commits and IDENTIFIES
exactly as proposed, and the whole ruling is a no-op there.

**What compare-and-swap was manufacturing.** A placement fire's tile
indices are search OUTPUT — a pose says which tiles it covers only once
it has run — so they cannot be in a read-set and no staleness test ever
protected them. Two consequences, both live before this landed: a bare
observation proposed against a snapshot that a certificate then landed
on reached `_tile_transition` and raised `certified content may not
change`, killing a lawful run with `CloseRecord(integrity_failure)`; and
two fires that each joined a footing onto one snapshot silently kept only
the last, with no refusal and no counter. Both are passing tests now
(`tests/engine/test_pool.py`, `tests/core/test_merge.py`).

**What stays fatal.** Two certified contents for one tile that DISAGREE:
a join that cannot join has nothing to return, and a certificate is never
voted on (L5). The check lives inside the join and raises the same
`CertificateConflict` the transition raised, so the orchestrator's
terminal-fact path is reached unchanged.

**The one relaxation, and why.** Two AGREEING certificates. Concurrency
made it reachable — two routes on one work key can both decode the same
bits, naming different attempts in their `MintRef` — and that is
corroboration, not contradiction. So the certified CONTENT (symbol bits
and metadata bit) is what must agree, the standing mint keeps the
provenance, and the loser's observation still merges in. Before the pool
the loser was discarded on the tile key's version, which is precisely the
guard this hook replaces.

**Composition with the transition law.** The family declares BOTH hooks.
The wall joins first and then adjudicates the JOINED record, so
`_tile_transition` stopped being the law a racing proposal trips over and
became the join's POST-CONDITION — the auditor for a merge that lost a
monotone member or edited terminal content. On a correct join it can
never fire, which is what a post-condition is for; `test_merge.py`
fault-injects a broken merge to show it is live, not decorative.

**The staleness projection.** A key the wall joins is projected out of
both sides of the admission-time identity comparison
(`CommitEngine.is_current`) — there is nothing for a fire to be stale
about. The DURABLE spend identity is untouched: what a worker read is
still what it spent, so a later gain on a joined key re-arms it through
the ordinary idle test. Only the admit-or-discard decision moved.

`TileState` (UNKNOWN / ADDRESSED / ATTEMPTED / CERTIFIED) is what the
OPERATOR reads — the tiles row and pane B's chips — and lives in
`tilemap` with the other derived views (tile family v4). `tile_state`
derives it: absence is UNKNOWN, a mint is CERTIFIED, and ATTEMPTED is
the spend ledger's payload CRC exposure on the key
(`payload.attempted_work_keys`) or a failed baseline standing on
the record. Nothing schedules on it.

### Evidence, and why multi-pose tiles are first-class

A tile's pieces come from several poses in two ways: window overlap (by
design), and the confetti regime — the tile physically split across
scraps with unrelated locations and orientations (e018 recovered
byte-exact volumes from real scissors sessions). The per-cell pose map is
necessary but never stored densely: it is `{pose → observed-cell
subset}`, materialised per-cell only transiently inside the ownership
freeze.

Three back-mapping rules use three different pose sets, and confusing
them is a correctness bug:

- **decode assembly** — the per-cell freeze winners (where a two-scrap
  tile becomes one codeword);
- **done projection** — the LIVE pose of every window that observed the
  key, winners and losers alike (they are different WINDOWS; the live
  pose is per window — see "the live pose of an extent" below);
- **label reconstruction** — the consuming window's own pose, never the
  minting pose (the KnownField/D7 rule).

Union accumulators key on `(page, ty, tx, stream, ppc)`; only equal-ppc
views of DISTINCT captures combine. Footing-in-key makes an illegal
cross-aperture sum unrepresentable rather than validated (L2).

## The laws solve enforces, and where

| law | where |
|---|---|
| **L2** LLR hygiene | `detect` emits bounded calibrated LLRs; the union RUNG exists only where ≥2 distinct captures observed the key at one ppc (`payload.union_tags`), so an illegal sum has no descriptor to run under |
| **L3a** one GENERATION per (tile, window) | F2a (2026-08-23, ruling J2-3): once a window's pose is revised and the re-read has sampled through the revision, the tile carries TWO generations of pieces. Only the newest that HAS pieces is decoded (`solve/generation.live_generation`, applied at `payload._pieces` and `calibration._pieces_by_pose`) — v1's lane separation (`payload_engine.py:181-182` refuses evidence from another lane) reproduced without lanes. Nothing is retracted: the superseded pieces stay committed, stay in the attempt's READ-SET, and stop owning cells. It is deliberately NOT the read-set's own rule, because a read-set may not shrink (`core.identity.fold_refusal`) — MEASURED: putting it there refused a real spend on the verdicts corpus. It is NOT `index.live_pose` either, which would delete the 4,392 / 4,117 pieces the archived states hang on non-live poses; on every state written before F2a the reduction is the identity |
| **L3** one owner per cell per (capture, footing) | the ownership freeze in `payload`, ordered by v1's key since F1 (2026-08-23, ruling J2-1 "we implement v1"): the covering window's CONTEXT-CORRECTED held-out log-loss — published per member window by the pool's ctx fit — then the pose id as the DECLARED tie-break (v1's is the E022 patch ordinal, which is arrival order and not rebuildable). Ordering by the pose id alone was a fixed GEOMETRIC preference and cost 27 e029 + 27 xerox certificates, MEASURED. Still never the evidence's own value: the loss is an out-of-sample fit statistic over cells whose values the FORMAT fixes (F-09) |
| **L4** trust tiers | a fire-time consult steers (`place_job`, nothing durable), `PoseRecord` places, `TileRecord.CERTIFIED` labels — tier 1 lost its record at H4 W2 and kept its place in the ladder |
| **L5** certificates | `tiles.attempt_k_tile` — zero syndrome AND CRC, minted through a recorded attempt with committed geometry |
| **L6** no self-training | labels come from prior commits only; an uncertified payload decision labels nothing |
| **L7a** complete-domain budgeting — ENFORCED | the word route freezes its whole declared domain before a pixel is read (`words.stage_a_hypotheses` for one nominal window, checked in `stage_a`, refusing rather than searching a prefix) and `PlacementBudgetPolicy.resolve` derives every route budget from the format, the page domain and the frozen E022 geometry |
| **L7b** derived floors — ENFORCED on the word route (H4 W1) | admission is `AttemptBudget.min_support`, the OR-9 derivation `max(E022_SUPPORT_FLOOR_SITES, identifiability_support_floor(H, BER) + margin)` applied to EACH disjoint parity population, and the window lattice is the table's measured E022 geometry (200 cells / 40 overlap / 70 minimum) rather than the H2 spine's 256/128/one-tile. `placement_h3bis.SUPPORT_FLOOR = 0.9` died with its module, and `toys.TOY_SUPPORT_FLOOR` died with `toys` at W1b — the OR-9 table still NAMES both, because the table is a record of what it retires |
| **L8** rival gates & quarantine — PARTLY ENFORCED (H4 W1) | first-hit-wins is GONE with `wordgrid`: every decoded word is a hypothesis that must clear the coupled E022 bars on two disjoint parity populations under `V1_WHOLEWORD_RIVAL_GATE` and then survive the straddle audit before any evidence is written. What is still owed is the rival ARITHMETIC itself (the 0.176 lesson's whole-word decoy/gap evaluation, which has exactly one consumer — `cold._rival_gate`) and the PL7 quarantine reduce: both W5 |
| **L14** channel gate ≠ receiver | nothing here consults a discovery tier |

## The live pose of an extent (W3, 2026-08-23)

> **"The latest committed pose for that extent wins."** — the user's
> ruling, RULING I3, and it is the whole rule.

RF1 (`--refine`, on by default since W3) makes a window carry more than
one committed pose: an adopted revision is a NEW `PoseRecord` at a new
key and nothing is retracted, marked, mutated or deleted — the journal
only grows. So "the pose of this window" became a question, and the
answer is a READ-TIME DERIVATION, never a record and never a status:
`tilemap.StoreIndex.live_poses` maps a window key to the LAST pose
committed for it, maintained per commit and rebuilt from the store's
first-write order (`core.store.Store._frame` frames its rows unsorted so
that order survives a resume). One derivation, one spelling
(`StoreIndex.live_pose` / `live_poses_of_region`); no consumer scans the
pose collection to find it.

**The same derivation, twice more** (F2a review, 2026-08-23), because a
sorted view cannot answer a question about ORDER and two consumers now
ask one: `StoreIndex.live_context_fits` is the LATEST-committed adopted
ctx fit of a pool (C4 §3.3(5): *"the CURRENT fit is the one just
fitted"* — after a re-read a pool carries two adopted fits over an
identical search population, and ranking them by population alone left
the decode's choice to a content address), and
`StoreIndex.evidence_by_pose` reverses §5.4's arrow (a piece names its
pose; nothing named a pose's pieces) so the re-read door stays O(1) and
the re-read FIRE stops walking the whole evidence index once per fire.
Both are maintained per commit and rebuilt from first-write order, like
`live_poses` and for the same reason.

Who reads it, and who deliberately does not:

- **the §6 done projection** (`plane_views._project`, `diag.panes.model`)
  — one pose per posed window. The union of an extent's poses would let
  a revision spend pixels it never sampled: measured on the two real
  sheets at +860 done cells (e029) and +588 (Xerox) for revisions
  carrying ZERO evidence (W2, 2026-08-23). What "latest" does NOT buy
  (W3 review, 2026-08-23): the projection maps the window's whole extent
  through the live pose and consults no evidence, so with a revision live
  the geometry sampled nothing and a boundary cell can change done status
  in EITHER direction. The union's unbounded over-claim is gone; a
  boundary sliver bounded by refine's search box remains, UNMEASURED —
  and it is asymmetric in consequence, since `place_sched` retires a
  window `done_covered` permanently;
- **the consult and the regional affine** (`place_job`) — one steer per
  anchor window, so a revised neighbour cannot take two of the eight
  `CONSULT_KEEP` slots or weigh twice in the least-squares fit;
- **not the PLACED test** (`place_sched._consider`, `place_job.run`):
  "has this window been posed at all" is a presence question and every
  pose answers it;
- **not `place_cold.live_pages`**: a revision carries its parent's page,
  so the page set is the same set either way;
- **not the calibration pool** (`calibration.pool_members`). The pool is
  EVIDENCE-scoped and affine-blind — a member contributes the cells its
  evidence pieces name and only `pose.page` is read off the pose — so a
  revision contributes nothing to a fit whether or not it is a member,
  and narrowing membership to live poses would drop the one member that
  carries cells. What a revision does do here is bump
  `region_pose_collection_key`'s version and re-arm the fit, which is
  the coarse wake that family already accepts. **What the fit reduces
  over IS live-generation-filtered** (`calibration._pieces_by_pose`), and
  since the F2a review (2026-08-23) the fit also subscribes to
  `region_evidence_collection_key` — because a RE-READ moves pieces
  without moving a pose, and v1 replays the affected region's coupled fit
  after re-sampling (C4 §3.3(5)). Without that key the fit that stood was
  the one fitted when the REVISION committed, i.e. before the revision
  owned a single piece.

Quarantine is NOT filtered by the derivation: a condemned pose is still
the extent's latest committed geometry, and the three readers that must
refuse one (consult, payload read-set, calibration pool) ask
`quarantine.is_quarantined` themselves.

## §6 — done-pixel projection (the design's own primitive)

Per capture, done-pixels = union over the **live** pose of every posed
window of the footprints of {supported cells of the pose whose work key
is CERTIFIED}, projected through that pose's committed affine. Derived on demand from
certificates + poses, **never persisted**; represented cell-granular,
never as a native-resolution bitmap. The live pose is the pose the
projection is TAKEN AT, not necessarily the pose that spent the pixels:
a revision re-projects its window's already-certified tiles through an
affine that observed nothing, which can add and remove boundary cells
alike (bounded by the search box, unmeasured — `tilemap.project_done`
carries the argument).

- **The gate**: a window whose supported extent is contained in its
  capture's done set is never created, posed, searched or woken.
  Payload-neutral by construction.
- **DONE is passive, not inert**: done pixels stay readable as sampling
  context and halo, and fully-done windows may serve label duty through
  committed-pose reconstruction — they never host fresh work.
- **DONE is a scheduling fact only — it deletes nothing.** Retention is
  uniform; there is no certify-triggered data lifecycle.
- **Per-capture asymmetry, self-extinguishing**: a tile certified from
  capture A is pixel-done in A only. B's first window over an
  all-certified area runs placement normally; the moment its pose
  commits, the region's remaining windows retire. Cost is O(first
  anchors per region), not O(region).
- **Refinement rides the closure test**: a refine worker is eligible
  only where its reach touches uncertified residue (e024's measured
  verdict — indiscriminate post-acquisition refinement ≈ zero yield).

Cache key today: the pair of monotone counts the projection is a
function of (committed poses, certified work keys). R3 made it sound for
the page dependency by storing `page` on the pose; F-08 (2026-08-13)
made it sound, full stop — every input to the projection is now
identity-frozen or transition-frozen at the wall, so a fact can never
move without moving a count.

W3 keeps it sound with revisions in play, and the argument is one line:
the projection is now a function of the LIVE pose of each window, and a
live pose can only move when a NEW pose commits, which is the only way
the committed-pose count can move either. So the same pair of monotone
counts still separates every state the projection could differ in — no
new cache term, and no revision that quietly reuses a stale done map.

## Worker families

The routes, their identities, inputs, outputs and proposed spend
granularity are enumerated per provider in **`PROVIDERS.md`** — PL1–PL7
placement, PY1–PY5 payload, CA1–CA8 calibration, RF1–RF2 refinement,
CL1–CL2 close, CP1–CP2 capture, OB1–OB3 observers, which is 27 rows of
its protocol table (the three observers share one). What follows is only
what the census does not say.

**PL1–PL7's DESCRIPTOR rows are superseded** (H4 W2, 2026-08-16): since
the pull model placement mints no descriptors at all, so those rows
describe routes, identities and spend granularities that no longer exist.
The algorithms they name are all still here — they became the ladder of
one job (below). The census correction is W2's own exit item.

**Window geometry is v1's** (user correction 2026-08-09; the LAYOUT
aligned to v1 by ruling 2026-08-15, H4-PLAN R12 addenda — "it has good
reason, and we don't want to waste tiles"). Fixed nominal size and step
off OR-9 (`WINDOW_CELLS = 200`, `WINDOW_STEP_CELLS = 160`; the H2 spine's
256/128 are retired), support clipped by the region mask, refusal
subdivision at capped depth — and the last window of an axis SHIFTED
FLUSH against the far edge rather than clipped there, which is
`pose_fit.layout_pose_windows`' own enumeration read in the capture-cell
frame (`geometry.window_starts`). Every window is therefore a full
200-cell square except on an axis shorter than one window, and v1's
8-cell sliver rule (`layout_min_window_cells`) is the only floor the
layout can reach.

That ruling closed the measured hole this paragraph used to name: the
clipped lattice sized its edge windows by whatever the region left over
— 193 and 131 cells on the differential's own arms — and then dropped
anything under `min_window_cells = 70`, so v1's constant was refusing
a 64-cell-span window whose ~4,096 supported cells clear the
30-cells-per-parity floor easily (the 8 mm scrap rung failing on a
constant). A flush lattice never produces the remainder in the first
place. What holo2 still changes is the ADMISSION side — creation
thresholds and support floors derived from the algebra per actual window
support (L7), replacing flat constants; the layout's own drop rule is
just "the region supports no cell of this window", counted exactly
rather than estimated off a `[::4, ::4]` subsample as v1 does.

**A lattice change is a WINDOW FAMILY bump** (window family **v4**, no
field changed). A window is named by its extent, so a build that lays a
different lattice mints a different POPULATION of names, and the states
written under the previous one are not this build's. Measured before the
bump, resuming across the change on a 515-cell region: the store came out
holding BOTH lattices — nine clipped windows plus five flush ones, the
four clipped edge windows inert forever while their band was re-fitted
under new names. R3's ruling settles it (refuse loudly by manifest, leave
the bytes INTACT, re-decode from the captures), and only a manifest move
produces that; verified end to end — a v3 state refuses at open with
`WindowRecord: state v3 != build v4`, and the journal, cache and blob
sidecar are byte-identical afterwards (the refused open does leave the
advisory `lock` file behind — `Store.open` releases it on a journal
error but not on a manifest one; harmless residue, a dead pid's lock is
taken over silently).

**Cold search stays per-window work** with its expensive shared state
managed as a leased resource, not by batching. Concurrency rule:
interference independence — two colds may run concurrently iff neither
lies inside the other's chain-interference footprint, selected as a
greedy independent set, best-supported first. The radius is DERIVED
(warp drift 0.2–0.5 cells per 160-cell stride against the ±3-cell chain
gate ⇒ transport dies beyond ~6–15 strides) and pinned as policy data;
tuning it trades wasted colds against idle workers, never correctness.

**Payload is eager by default** — no global placement→payload barrier.
An attempt binds the exact frozen evidence identity it read; later
windows change the frontier, which is a new identity, which re-arms the
worker. Spend-once makes the eager schedule safe; monotone certificates
make early wins final.

**The close consult is incremental** (P3-1, ruled 2026-08-12, built
2026-08-13). `VolumeClose` keeps `_CloseState` — in-memory, derived,
DISPOSABLE — so a consult pays O(new certificates), not O(all): an
incremental GF(2) eliminator mirrors the carried metadata elimination
(the word is UNIQUE at rank 24, so later equations check, never revise —
a contradiction is L5-terminal, and the 48-distinct floor is the
false-accept budget of ≥24 surplus parity checks); the carried
`decode_metadata` is called ONCE at the trust transition and stays the
interpretation authority; per-(stream, block) distinct-ESI counters run
through `format.volume_code_for` (built once per stream at K-trust);
zero payload-symbol blob reads happen before a close attempt; and once
count-ready, a re-close runs only when a block the last attempt could
not solve gained a distinct symbol (exact — solved blocks stay solved —
never a heuristic). Every durable outcome is still the carried
`close_volume` on the full set. Consult MODES (`observe`/`close`/
`final`) are the engine's vocabulary; `--complete` observes mid-run
(counting stays live) and decides once at the end. Equivalence with the
carried gate is pinned at every prefix by
`holo2/tests/solve/test_close_state.py`.

**One descriptor per route** (2026-08-11, revised same day on the
adversarial review). `scan` per RESIDENT footing with evidence, `union`
per ppc two DISTINCT captures reached, `retry150` per footing in the
key's `baselined` set — the durable per-footing fact that THIS footing's
scan ran a decoder and failed (the tile-level ATTEMPTED state cannot
say which, and gating on it armed BP-150 on unbaselined footings; a
below-floor scan now writes neither). Route ORDER is not scheduled —
eligibility is the whole mechanism, because an attempt that may not run
yet has no descriptor — and an attempt that loses the race to a
certificate fires once, reads CERTIFIED, grows the certified record's
`observed_by` (done projection needs every committed observation, §6)
and retires without touching a decoder. The consequence the review
asked for: every decoder run flags `WorkResult.exposure`, the ledger
folds it into a monotone per-row counter, and `crc_exposure` SUMS the
counters — exact under outcome overwrites, where the first cut's
latest-outcome filter silently lost the exposure of every attempt that
later re-fired into `already_certified`. A stale-discarded proposal
never lands (its writes are dropped, so its CRC test could not have
accepted anything into state) and is deliberately not counted.

**The placement family is ONE JOB pulled from a scheduling set** (H4 W2,
the pull model — `H4-W2-PLAN.md`, "THE PULL MODEL — 2026-08-16 redesign,
RULED"). It replaces the two descriptor routes and the durable hint
record below with the user's own model: *the scheduling set is all
windows minus the finished ones; each window has an "I am ready" bit; a
worked window atomically clears its bit, takes what it knows, and does
its job.* Placement work does not arrive as descriptors at all — it comes
from the engine's second admission source (`core.WorkSource`), which
`solve.place_sched.PlacementScheduler` implements and the composition
root binds beside the providers.

*The set* (`place_sched.py`). One `Slot` per window (`place_slot.py`
since F2a, when the ladder grew a tier that is not a placement rung),
none of it durable: a `ready` flag, an `in_flight` flag, the TRIED set,
the word-stage memory (`centre_spent`/`rest_spent`/`wide_spent`) and the
best distance a ping has OFFERED since the last claim. Membership is
MONOTONE — a pose is identity-frozen and the §6 done projection only
grows — so the set only ever shrinks, by `placed` or by a retirement,
and a window that leaves never comes back.

**AMENDED AT F2a (2026-08-23, ruling J2-3 / RULING I3).** One window DOES
come back, once per LIVE POSE: the `placed` exit is now "placed, AND its
live pose has been read", so a window whose latest committed geometry
nothing has sampled through re-enters as a RE-READ slot
(`solve/resample.py`, PROVIDERS PY6) — the ruling's own sentence, "when
a better pose comes in, the old one goes out the door and the tile/window
wakes up again". The monotone argument survives because the re-entries
are BOUNDED: RF1 commits at most one revision per extent
(`refine.Reach.revised`) and none at all where the affine is unmoved, and
the scheduler answers each geometry once PER SESSION, whether the
re-read emitted or refused — an emitted one is durable (its pieces close
the door's first clause), a refused one is offered once more on the next
resume, which is waste and never a spin.

That is exactly the shape where weak synchronisation is
provably enough: a race costs one spurious pass, never a lost one. A
resume rebuilds the whole set from the store (plans, minus placed, minus
retired, minus done-covered, minus any rung outside the run's declared
READING SET — which since H4-LANES stage 2 is the whole ladder by
default, so that last term is usually empty), all ready,
tried empty — so losing the tried set costs re-tries, which is waste,
never wrongness, and the rival gate's floor restarts per session exactly
as v1's did.

*The monotone-GROWTH amendment* (W3/PL5, and the set's termination
argument in its amended form). The set grows by SUBDIVISION and by
nothing else. A window that has exhausted its ladder on one of v1's
subdivision-eligible refusals (`place_job.SUBDIVISION_REFUSALS`, below)
adds four corner windows to this set — ordinary members, named by
`window_key` from their own extents, consulting the same committed
poses, carrying their own tried sets, entering through the same
admission door. Termination stands as bounded arithmetic: a window
subdivides at most once (`_Slot.subdivided`), a child is admitted at
`depth + 1` and `SUBDIVISION_MAX_DEPTH` is 1 so the growth is ONE
generation, the carried kernel refuses to halve below the 70-cell floor,
and every member — child or not — still leaves only by placed or
covered. The set is therefore bounded by `plans + 4 × plans` in the
worst case and by `plans` in every healthy run, and the weak-
synchronisation argument above is untouched, because a child is an
ordinary member from the moment it is admitted.

*The eligible refusals are v1's, transcribed* (`place_job`). v1 calls
`subdivide_into_pending` from exactly three places in
`src/holo/receive/place.py`: :1244 (the window's own `fit_window_pose`
refused, so no route ever ran), :1173 (the refinement + straddle audit
refused an address the search had accepted), and :1126 via `run_cold`
at :1495 (the LAST tier refused). Here those are `pose_refused`,
`straddle_audit_refused`, and whichever refusal the ladder's last pass
made. `insufficient_support` is the refusal v1 reaches and deliberately
does NOT subdivide on (:1259-1271 returns without a call): too little
paper under the rectangle is not a reason to ask for a quarter of it.
The set is half the trigger; the other half is DORMANCY — every cheaper
way of placing the window whole having failed, which for a window that
got that far is the wide consult refusing, and for a window whose own
fit refused is the first pass, because every tier opens with the same
sample and would refuse identically.

*The child premium, and the parent's afterlife.* A child pays
`CHILD_PREMIUM` (5) on top of its parent's lane term, which under one
global cost order is the user's ruling as arithmetic: at any rung, every
whole window is cheaper than every child — exhaust the sheet before
specializing. NO LINEAGE FIELD (ruled): children get ordinary
`WindowRecord`s at placement or retirement and nothing names a parent;
the reference only points DOWN, from the parent's scheduler slot to the
child ids it computed, in memory. A child's exit (placed, covered, or
exhausted-and-dormant) is read from above, and when every child has
failed the parent escalates to COLD — which runs on the parent's FULL
extent, since correlation wants area (`_Slot.cold_parked`, the bit W4
turned into the tier's admission). AMENDED at W4 (2026-08-18), when
subdivision moved BEHIND cold to restore v1's own order: an ordinary
parent has already run its cold pair by the time its corners report, so
the park is normally a counter, and the escalation still ARMS a real
correlation for the one family quartered before it reached a cold tier
(v1 `place.py:1173`, the straddle-audit refusal). Resume persists nothing: a resumed parent re-runs its
ladder and re-subdivides, the kernel is a pure function of the parent's
extent so the SAME child names come back, fired children are found by
their own extent-named records and unfired ones re-enter. Waste at
worst, never wrongness.

*The flag protocol, which is the correctness argument.* Two orderings,
and they are the whole of it: **commit, THEN ping** (`settle` runs after
the pose is durable, so a woken neighbour consults an index that already
holds it — the engine's half of this is `_commit` → `_settle`), and
**test-and-CLEAR, then consult** (`claim` clears the ready bit before the
job exists, so a pose committed during the pass re-sets the bit and buys
another pass). Take any commit C and any pass P of a neighbour: either
P's claim happened before C's ping — the ping finds the bit clear and
sets it, P re-runs with C visible — or the claim happened after the ping,
and P's own consult reads C directly, because C committed before it
pinged. There is no third interleaving, and neither branch depends on how
long P runs. `in_flight` is the same bit read the other way: `peek` and
`claim` both refuse an in-flight window, so one window has at most one
owner, and a ping arriving mid-flight is re-enqueued by `settle` on the
way out.

Two of `settle`'s duties are asked on EVERY path, including the two that
leave the set. **R5's seed wake** rides the WRITES, not the outcome: the
pass that first fits a region is its likeliest seed superseder and is
usually also the pass that is ACCEPTED, so a region wake conditioned on
failure loses exactly the wake that matters — a window a gap away, whose
own fit refused and which no ring ping reaches, would sleep through the
seed that fixes it. **A pass with nothing to try** (its ping offered only
candidates already in the tried set) spent the PING and no tier, so it
falls to its next tier rather than going dormant behind a queue entry the
ping already invalidated; it cannot spin, because the tier it falls to
charges itself once.

*The job's ladder* (`place_job.py`), decided by what is TRUE at fire time
rather than by which descriptor was minted: (a) the LAZY COVERED-EXIT —
the §6 projection is asked before a pixel is read, and a window whose
whole supported extent certified through NEIGHBOURS' poses retires with
its reason; (b) the CONSULT — the committed poses this window can see,
extrapolated through `place_shared.predict_from_page_affine`, sorted by
the ratified distance, truncated to 8, minus this window's tried set;
(c) each seed through the carried 49-hypothesis `pose_audit.local_search`
on one shared score memo, nearest first, stopping at the first
acceptance; (d) the WORD STAGE if and only if the consult came up EMPTY —
centre slots first, rest slots on a later pass, the staging that used to
be a durable `SLEEPING` record now the scheduler's in-memory stage
memory; (e) the WIDE tier, which widens the consult to nearest-K anchors
at ANY distance page-wide and adds ONE extra candidate, the least-squares
REGIONAL AFFINE over every committed pose of the region's majority page
(ruling R-B) — the gap-jumping case where per-anchor extrapolation has
decayed but the page-average warp is still good. The regional fit needs
at least TWO placed poses by argument, not by arithmetic: one pose's four
corners determine an affine exactly, so a "regional" fit over one window
IS that window's pose, which the consult already offered.

*Tiers are prices, not ladders* (rulings Q3+Q6). `PLACEMENT_TIERS`
declares the cost of each with its provenance, and the same scale is
spelled on the engine's side (`engine.recipe`'s `COST_PLACE_*`) with a
data test pinning the two equal (`tests/engine/test_cost_vocabulary.py`,
which pins the payload interleave with them) — the wall-crossing
discipline the close consult's three modes use. The order is
**payload** < ring consult < word centre < word rest < wide consult <
**cold live < cold rest** — the pair W4 built, one flavour per rung
(live = the pages this session already holds a committed pose on, rest =
the declared domain minus those). The literal numbers are NOT restated
here: they were re-spaced by H4-LANES stage 2 and again by the cold
pair, and `solve/place_tiers.py` is their one home, with each row's
provenance beside it. AMENDED
2026-08-17: payload used to sit at 40, between word rest and wide, and a
real nine-platen run measured it starving there — 1,287 armed payload
workers, zero tiles attempted after 431 fires, because placement on a
domain that size never dries, and with no certificate neither close
preemption nor done coverage ever arms. It now undercuts every placement
rung, the finer ones' premium included. Payload
competes in the SAME global order because its certificates DELETE
placement work outright, and the two
expensive tiers are GATED — admissible only when nothing cheaper is ready
or in flight anywhere. Dryness is INSTANTANEOUS, not final: the tier
opens when nothing cheaper is ready or armed at this moment and
re-evaluates as the queues move, because bounded waste beats a finality
condition that deadlocks. Within a tier, ready windows order by their
best AVAILABLE seed distance and then round-robin (ruling R-A):
Dijkstra-flavoured frontier growth along the most confident edges, with
an ordinal tie-break so nothing starves. AVAILABLE, not merely pinged: a
window admitted beside poses that already stand — every window of a
resume, and a finer-footing entry admitting into a page others have been
placing — is offered at the door what
a ping would have offered it (`_consider`'s consult peek), or the whole
resumed page would enter blind, at the word tier, in arrival order.

*Footing progression is a price too* (user ruling, AMENDED 2026-08-17;
RE-SPACED at H4-LANES stage 2). `LANE_COST_PER_RUNG` is the second
number in that table: a window pays its tier's cost PLUS `2` for every
rung it sits above its capture's COARSEST, resolved ONCE at admission
from the plane's own ladder (`admit`, through
`PlaneView.footing_depth`), never from a branch at fire time and never
from the selector that happened to reach it. It replaces the engine's
`quiescent` gate, which used to keep the finer entry's windows OUT of
this set entirely while anything cheaper was in play; they now enter as
soon as their geometry exists. It also replaces the flat premium of 1
that landed with the ruling: a flat offset can only say "finer", while a
depth term says WHICH rung, which is what makes coarse-before-fine hold
sheet-wide across a five-rung ladder rather than only between two
classes. The whole scale was re-spaced by four in the same commit to
make room (tiers 40/60/80/120/140, payload 20, ingest 10), so the term
at the deepest realistic ladder — 8, plus the 5 of the child premium
(RESERVED here, WIRED at W3: a subdivision child pays it on top of its
parent's lane term, so the two stack) — stays strictly below the
smallest inter-tier gap of 20. It
therefore reorders WITHIN a rung and never across one: a finer ring pass
still beats every word pass, a finer word-centre pass still beats every
wide pass, and payload's place in the order is untouched (it carries the
same term, and `20 + 2*4 < 40`). The finer window that never needed
working still exits by coverage: at admission if it is already done, and
otherwise at the head of its first pass, before a pixel is read
(`place_job`'s covered exit).

*The floor is the TRIED set* (ruling Q1). The rival gate's declared
domain prices this window's CUMULATIVE distinct hypotheses — `49 x (tried
+ offered)`, and nothing else (`place_job.pass_budget`). It is honest
BECAUSE fires are deterministic: repeating an identical hypothesis on
identical pixels is the same trial, not a new one, so de-duplicating by
candidate is the true count, and a bare pass counter would price re-tries
as new information. The derived support floor grows with the domain
(L7b), never shrinks, and is never truncated to fit.

**PARITY RESTORATION (user ruling 2026-08-18, "we want parity to v1").**
As written at W2 this pooled budget also added *the Stage-A domain of
every word stage the window had spent*. It had no v1 counterpart: v1
declares the placement domain PER ROUTE and never folds Stage A into one
— `_chain_budget` (`holo/receive/place.py:217`) declares `49 x n_anchors`
for the chain route, and `_word_route` (`place.py:394`, called at
`place.py:1344`) is handed `budgets.local` UNMODIFIED, i.e. 49, because
Stage A is priced in its own currency, the single-word union bound
(`holo/receive/words.py:78`) against `familywise_false_accept`, and not
in the identifiability site count `min_support` derives. At the
production Stage-A domain (147,456 phases) that term put a
two-stages-spent pass at a domain of 294,961, past the 250,530 knee where
`ceil(log2 D / (1 - h2(0.08)))` crosses 30 -> 31, so the derived floor
read **31 where v1 reads 30 on every route**. Its DIRECTION was a **bar,
never an extra attempt**: `min_support` is compared `>=` against a
window's supported sites, so the deviation REFUSED a window supported at
exactly the 30-site `E022_SUPPORT_FLOOR_SITES` that v1 admits. The term
is WITHDRAWN; the domain is `49 x candidates` on every path, which equals
v1's arithmetic with no word stage spent, with the centre stage spent,
and with both spent. Pinned in
`tests/solve/test_place_job.py` — the three paths against hand-derived v1
literals, and a support-exactly-30 window admitted on each.

*What crosses the wall.* Facts only, and only when the job has one: a
pose plus its evidence and calibration through the ONE shared emission
block, R5's lattice seed when this window's fit measured a better one,
and the window's own OUTCOME record — `WindowRecord` **v5**, placed-by or
retired(reason), every scheduling status shed (ruling Q2). **A failed
pass writes NOTHING** — no no-op commit, no spend row, no subscription —
so the ordering journal stays a record of the work that PRODUCED
something, which is what makes replay in that order re-derive every
consult (ruling Q4). The one key the job DOES bind is R5's lattice seed,
because it is a read-modify-write whose transition law can refuse: bound,
a concurrent loser gets the engine's ordinary stale discard instead of a
fatal `CommitRefusal` (measured: the spine fixture died exactly that way
at four workers before the key was bound).

*Two exits, defended against the obvious simplification.* Done does not
imply placed: windows overlap, so a window's whole supported extent can
certify through its neighbours' poses, and the two-sheet fixture ends
with windows done-covered and never posed. Exit-by-done is what stops an
unplaced window in a recovered area from burning consults forever;
exit-by-placed hands the window to the payload family for good. Both
stand.

*Deleted, not deprecated* (ruling Q7, "aggressively trash what doesn't
fit"): the `HintState` and `DoneSummary` families, their laws, their
subscriptions and the ring-key identity binding. No hint ever crosses the
wall — a hint is a scheduling annotation, not a fact, and promoting one
to a record is what bought the improve-only law at the wall, the
concurrent-merge collision, the ring-key binding and a subscription per
neighbour.

Verdicts: `holo2/tests/solve/test_place_sched.py` (the model at unit
scale) and `holo2/measure/verdicts/` (five verdicts over three shared
decodes — byte-exactness, pose-for-pose parity with v1, crash-cut
re-earn and a pixel-free resume, the seeded-search migration on a banded
page, and close honesty on a partial volume).

**SUPERSEDED by the pull model above (H4 W2, 2026-08-16). Text kept: it
is the before-picture the wave's measurements are against, and the
batteries in `holo2/measure/` still assert it.**
*The placement family has TWO accepting routes* (H4 W2): `word`, which
seeds a page from no prior geometry, and `chain`, which places a window
from the hints an acceptance PUSHED at it (R10 — nobody subscribes to a
neighbourhood). They share everything downstream of the address: the
window preamble, the refine/audit block, and the emission, which is also
where the push itself lives, so a route cannot emit evidence and forget
to steer its neighbours. The chain descriptor READS six singular keys and
its eligibility is a hint state, so the pull-era neighbourhood is gone;
the §6 done gate moves to MINT-time for that route until item 7's
per-region done summary gives the fire an O(1) key. It also BINDS the
hint keys it may write — its own ring — because a read-modify-write whose
key is unbound turns a concurrent pusher into a wall REFUSAL instead of a
stale discard (measured: a pooled fixture decode died on exactly that).
That binding is the wave's one open shape question: R10's own wording
says the wall should DROP a weaker write, which the registry cannot do
today, and the alternative is to move the push onto a cheap descriptor of
its own whose read-set these keys are. Two poses for one window are impossible rather than merely
unlikely: both routes name `collection:poses/<window>`, so a pose landing
mid-fire invalidates the other route's identity (§7's re-derivation), and
a pose already standing settles it at the gate.

**SUPERSEDED with the paragraph above (H4 W2, 2026-08-16): route order is
now a global price table, and placement mints no descriptors to order.
Text kept as the before-picture.**
*Route order is the queue's tie-break UNTIL PRICES* (H4 W2, item 8):
chain is the cheaper route and is tried first where a hint exists, which
today needs no mechanism — a chain descriptor exists only where a hint
does (eligibility is expansion, §3a), and among one window's descriptors
the ready heap orders by `WorkId`, where `chain` sorts before `word`.
H4-W2-PLAN item 8 replaces that accident-of-alphabet with a global price
table the heap orders by; when it lands, this paragraph becomes a row in
it — and it has one measured thing to fix. The tie-break only decides
between descriptors that BOTH EXIST, and a chain descriptor is minted at
an enumeration of the `place`/finer entry, which is `quiescent`: it is
skipped whenever an earlier entry (payload) has work in play, so on a
page where the word route succeeds everywhere, chain is not minted until
the queue drains and every window is already posed (measured on the
rendered fixtures: nine word acceptances, then nine chain fires that all
settle). Where it MATTERS the ordering still works — a window whose word
centre stage refused goes SLEEPING, and at the next enumeration its chain
descriptor sorts ahead of its `rest` descriptor and gets first refusal
(measured: 4 of 9 windows placed by chain on the banded arm). Prices are
what let the cheap route be tried first everywhere, not only where the
gate happens to open.

**Two-stage cold is a PRICE refinement, not a mechanism** (PL4 note,
recorded 2026-08-11 from the founding dialogue): when cold search
arrives (H4), a window may carry TWO cold descriptors — scope =
addressed-pages (cheap: the page set word placement has already pinned
collapses the search) and scope = remaining-pages (expensive, parked
behind quiescence pricing). Both are ordinary eligibility-gated
descriptors; admission floors and the rival set stay full-domain (the
0.176 lesson). No sequencing machinery follows from this — it is two
prices on two scopes.

**Calibration scope is per quantity** (verified against `detect.py` and
the color-uplift worktree): geometry and photometrics per window fed
from own(+halo) anchors and shrunk toward the region prior; detector
state models at the finest scope whose label mass supports the parameter
count, arbitrated by held-out gates (adopt-or-refuse, never guess);
label growth over passes may legitimately afford finer scopes later.

**CA2 IS LIVE (H5 P1, 2026-08-18 — `solve/calibration.py`; the census
row's BUILT stamp in `PROVIDERS.md` §3 is the full record).** The
load-bearing sentences, stated once here: evidence pieces keep their
calibrated MARGINAL LLRs forever; the region ctx correction applies at
DECODE ASSEMBLY (`payload.RealPayloadWorker._decoder_input`), each
footing's frozen component corrected over the cells each region's poses
own BEFORE any cross-capture sum (footing-scoped, so L2 holds by
construction); a refused fit leaves the marginal path untouched — with
no adopted fit the component is the SAME array object, so the refused
path is bit-for-bit the pre-H5 path; and a payload decode subscribes to
its OWN tile's evidence plus exactly ONE region-scoped key, the pool's
calibration collection, versioned on ADOPTION only (user-confirmed
scoping law). Refits are re-work by construction: the fit descriptor
spends at the wall, so `engine.recipe.work_price` lifts every re-fit
into the band and a refit follows a BATCH of new labels (measured on the
channel-arm probe: three fits per decode, first at 15, the rest priced
90+, every one refusing on the held-out gate at this sampling — the
e018 branch record's ctx-is-sampling-dependent finding, reproduced by
the gate doing its job).

## Measured facts solve relies on

- **The done gate has a census, not a hope**: 48.6% of committed
  placements are provably pixel-gateable session-wide on the e029 ink
  page, 75% at the two fine ordinary lanes, 85–90% of the `--complete`
  tail (DONE-GEOMETRY §8a, measured, zero-print). Fragment/confetti
  census still owed.
- **Word staging pays**: centre slot first, widen on failure —
  3,627 → 794 ms per word-succeeding window (v0.26 lesson).
- **The cost asymmetry behind eagerness**: BP+CRC totalled ~38 s on the
  real color corpus against hundreds of seconds of placement; one
  BP-150 retry costs 121.3 ms/tile; retry-always bought 1 tile per
  branch for ~50k BP iterations.
- **Decimated aperture photometry is better**: pair-matched PAVA BER
  1.80% vs 2.41% native.
- **Cold is expensive and shareable**: the full 312-page domain
  transform cache is ~7.6 GiB plus ~1.1 GiB reference pages, 47.9 s per
  patch; at P=1 it is ~1–3 s/window.
- **Wrong pooling is the cautionary case**: the pooled-per-plane K port
  was adopted in 0 of 17 lanes for 8,648 s CPU; e025 refused CMY8-at-c2
  on per-plane registration.
- **The real channel does not sit on the nominal pitch**: the H3bis
  first attempt made 0 word decodes in 101 s; v1's committed poses said
  the real pitch was 16.18/16.10 px/cell against a fixed 16.00. The fix
  added a ±1.2% scale sweep plus adjacent-tile growth probes.
  **HONESTY NOTE**: single-variable attribution of that fix is NOT
  established (a fixed sweep tolerates ±1.5% synthetically), so which
  term of the real error stack crossed the line is unknown; the refusal
  notes are self-diagnosing so a recurrence answers itself
  (`holo2/docs/MEASUREMENTS.md` §H3bis).
- **The result**: 1,359 certified tiles recovered 465,580 bytes
  byte-identical to v1's recovery of the same sheet — against v1's 1,930
  certificates for the same volume. That is eager close preemption, not
  a better detector; the algorithms here are H3bis-grade.

## Open rulings LOCAL to solve

(`holo2/docs/DESIGN.md` §12 keeps the index; defects are the TO-FIX
ledger below, not here.)

- **OR-1** done-projection erasure extension — full tile rect through
  the certifying pose vs audited-cells-only. Must be ruled, not
  defaulted.
- **OR-2** label channel for fully-done windows (committed-pose
  reconstruction recommended).
- **OR-3** flip-canary sampling rate over done windows, and its ordering
  with the D5 threshold doctrine (the uninterpreted 21.5% ink-page flip
  datum stands as a warning).
- **OR-4** whether the tile-map gate subsumes region-granular L1, or
  both remain (defense in depth vs one-concept-one-implementation).
- **OR-5** eager-payload BP budget: attempts per key per session under
  re-arming frontiers. MEASUREMENTS answers the schedule half (KEEP
  EAGER) and explicitly not the ceiling — it was measured on a decoder
  that never failed, so H4/H5 owe that number.
- **OR-7** subscription radius. **RESOLVED BY DELETION** (2026-08-16,
  H4 W2's pull model, ruling Q7): the question priced a radius for
  placement subscriptions, and placement subscribes to nothing any more
  — the ping is the message and the §6 projection is asked at fire time
  (`place_job.run`'s first gate). The `DoneSummary` family this item
  recommended building was deleted with `HintState` in the same sweep,
  so the recommendation is withdrawn rather than deferred. The MEASURED
  half stands as a record: the done-gate/sibling subscription's radius
  (M-3.2) is a different dependency from the chain hint's 6–15 strides,
  and it was never right to set one from the other.
- **OR-9** window split policy and the snippet floors table (derived,
  L7) — needs the algebra worked and pinned as data.
- **OR-10** quarantine scope in the dataflow model (contributor-scoped
  promotion firewall; mechanism identical to v1, wiring new).
- **OR-11** transform-cache grace period, and whether subdivision
  children zero-pad into the full-window cache shape.
- **PROVIDERS.md §9** carries 18 adjudication items — spend granularity
  per provider (Q5), refinement as provider vs recipe phase, the u-lane
  as a recipe capability, whether A2 (declared, never built) stays in
  the roster. Design questions with no code behind them yet, and exactly
  the kind of ruling that should land in this folder.

## TO-FIX — solve's ledger

**F-nn** = the adversarial review with its severity scale; **D-n** = the
founding-design deviations indexed in `holo2/docs/DESIGN.md` §15.
Adjudication is H3.5's.

| id | defect | where | sev |
|---|---|---|---|
| F-09 | **CLOSED (2026-08-12, W-B B6 — RULED "must be fixed")** — the ownership freeze read `LLR == 0` as "this pose did not observe this cell", which is false for a cell scored exactly at the decision boundary (PAVA emits zero at p = 0.5), so an observed neutral cell could be reassigned to a later pose and owner selection depended on the evidence's own value. `_Piece` now carries the piece's durable `observed` mask (`EvidenceObservation.observed_ref`, unpacked in `_pieces`) and the freeze is `take = piece.observed & ~owned` — **the contested cell's own value never decides who owns it**. (AMENDED 2026-08-23, F1 review, ruling J2-1: the row used to read "no evidence value enters owner selection anywhere", which stopped being true when the freeze took v1's key. The ranking statistic IS a statistic of the evidence — an out-of-sample held-out log-loss, read only at sites whose values the FORMAT fixes, published by the pool's ctx fit before any payload decision. That is the distinction L3 draws; F-09's own property, the per-cell one, is untouched.) Decoder input semantics are otherwise identical: an owned cell scored 0.0 stays 0.0 (the erasure the carried chain expects), and a cell no piece observed is 0.0 too, with the returned piece's own mask telling the two apart. Yield moves down-or-flat by construction (the forfeited borrows were the illegal ones; union and retry are the lawful recovery paths); the real-sheet certificate delta is evidence the integrator records, not the gate | `payload.py` `_freeze`, `_Piece`, `_pieces` (`toys.py` carried the same repair and was deleted at W1b) | CLOSED |
| F-05 / D5c | **CLOSED 2026-08-12 (worklist B9, RULED "build it").** `open_plane` now CATALOGUES every capture the store knows and this invocation was not handed (`capture.catalog`), so footings, regions and lattices come back BY RECORD and a resume needs zero SCANS to carry a decode forward — the proof is a volume closed byte-exact with no scan declared (`holo2/measure/verdicts/test_durability.py`). The frontier's `has_footing`/`has_region` questions stand and are what the providers compose with; PIXEL work declines with a wake on `attachment_key` instead of raising. The rule: **an attached capture's fresh survey wins over its durable regions**. **AMENDED 2026-08-17**: "no pixels" was too strong a reading of "no scan". A placement fire reads the region's PREPARED plane and never a raster (§6.8/W1a), and those files live beside the state directory and survive a crash — they were merely unnameable, because the backing scalar in their digest was a session computation recorded nowhere. It rides `CaptureRecord` v3 now, so `prepared_region` has a reuse-only door and `pixel_work_is_attachable` admits on EITHER source (raster asked first, so an attached session is untouched). The wake story is unchanged and that is structural, not lucky: a prepared plane only ever appears through a session that HAD the raster, so within one run the second source cannot arrive after the gate said no | `plane.py` `open_plane`, `has_region()`, `prepared_region`; `prepared.open_prepared_region`; `place_shared.pixel_work_is_attachable` | — |
| F-06 | **CLOSED for the per-route half (2026-08-11, revised same day)** — one descriptor, read-set, spend and attempt per route (`scan` per resident footing, `union` per ≥2-capture ppc, `retry150` per footing in the key's `baselined` set — the review killed the ATTEMPTED-gated form, which armed BP-150 on unbaselined footings); `MintRef` gained `route` + `decoder_profile` (tile family v2) and CRC exposure is a monotone per-row counter the fold accumulates (`SpendRecord.exposures`), summed by `crc_exposure` — exact under outcome overwrites, where the first cut's latest-outcome filter lost landed exposure. Was: one fire, one route, one spend hiding up to five CRC tests. **CLOSED 2026-08-14** by the residue: `TileRecord.state` deleted (tile family v4) — `ATTEMPTED`/`ADDRESSED` are derived views now, off the spend ledger and the record's presence, and `TileState` is display vocabulary in `tilemap` | `payload.py`; `records.py`; `tilemap.py` | — |
| F-27 | **CLOSED (2026-08-12)** — `MintRef.attempt_digest` is DELETED (tile family **v3**), and `core.identity.identity_digest` with it: it was written at every mint and read nowhere, while the spend row `(payload, work key, route, scope)` already NAMES the attempt structurally (the hash-free identity law, root DESIGN §6). ~19 fixture sites shortened by one argument; no production reader existed to migrate | `records.MintRef` | CLOSED |
| F-28 | **CLOSED (2026-08-16, H4 W2 ruling 1 — the fix this row named, built).** Commit-time JOIN semantics for the tile family: the record registry gained a fourth hook (`merge`), the tile family declares `join_tiles`, and the wall re-applies a proposal against what it holds instead of version-validating that key. Races fold into monotone merges exactly as this row predicted; the wasted re-arm it describes is gone with them (a joined key no longer decides a discard, `CommitEngine.is_current`). What the row did NOT anticipate is that the same staleness lean was also load-bearing for CORRECTNESS: a placement fire's tile writes were never bindable at all, so a certificate landing under one made `_tile_transition` end the run as an integrity failure, and concurrent observation gains were silently last-write-wins. Both are pinned as passing tests. The core concept change it flagged is the registry hook, argued in "The tile map is the tree's ONE commutative family" above | `records.join_tiles`; `core/registry.py`; `core/commit.py` `_settle_merges` | CLOSED |
| — | per-(tile,footing)/(tile,ppc) evidence collections: **REFUTED as measured-inert (2026-08-12)** — on the production shape of the day (one capture ⇒ one reading lane) the finer collection was key-for-key identical to the per-tile one, and even the two-capture spine saved 0 fires / 0 decodes / 0 stale discards. **The premise moved at H4-LANES stage 2** (a capture has several reading lanes now), so the measurement is stale rather than wrong: RE-MEASURE before re-deriving. The wake amplification (16.93/commit on the real sheet) still lives in the placement family's wake graph — OR-7/decider territory | survey 2026-08-12, premise superseded 2026-08-17 | CLOSED (negative), re-open on measurement |
| — | placement's re-offerable decline (`Decline("capture not attached", wake_on=(attachment_key(...),))`) sleeps on a `KIND_ATTACHMENT` key nothing writes DURING a run: attachment still happens at composition, so the wake fires BETWEEN runs (re-invoke with the file and the parked windows mint workers), not within one. B9 made that path load-bearing rather than dead — it is now the ordinary state of a resume handed fewer captures than the store holds. Un-parking WITHIN a run stays unbuilt until a provider writes such a key (H3's mid-session attach) | `placement_h3bis.py`; engine `_absorb` | ADVISORY |
| F-04 | **CLOSED (2026-08-17, W3/PL5) — and not the way this row expected.** Subdivision landed with NO provider and no descriptor: the pull model made it the scheduling set's own last escalation, so a child is four more MEMBERS of an in-memory set, named by `window_key` from its extent like every window (`place_subdivide.subdivide`, ex-`place_sched._subdivide` — moved at W6's cap seam; `plans.child_window_plans`). The row's premise — that child windows need a durable subject to be expressible — was descriptor-era; what they actually needed was a name, which the hash-free identity law already gave them. `SubjectSpec` is therefore still unminted, and its ADVISORY row below is amended rather than closed | `place_sched.py`; `plans.child_window_plans` | CLOSED |
| F-17 | **CLOSED (2026-08-17) — the fix this row named, built and measured.** `SessionContext.apply` hands `CommitResult.changed_keys` to `plane.invalidate`, which ADVANCES the store index into the next generation (`StoreIndex.updated`: copy-on-write, eager, on the committing thread) instead of dropping it; `StoreIndex.build` survives as the resume seed and as THE ORACLE. Four more derived surfaces moved with it: the per-cell certificate map the §6 done grid projects (choice 6, killing 421 k `tile_done` key builds), the parsed footing of every evidence key (choice 6), the two work-key partitions `open_tiles`/`certified_tiles` (choice 7 — filter-and-sort over the whole tile map at every read), and, provider-side, the H3bis payload frontier, memoized per work key on the IDENTITY of the objects the index hands out (`RealPayloadProvider.expand`). MEASURED gen-clean serial, VERIFIED byte-identical with the schedule UNCHANGED (1357 certified / 1918 commits / 2323 fires — the anchor's exactly): **209.7 → 127 s (1.65x)**; W4 **145.3 → 57 s (2.55x)**, thread ceiling **1.44 → 2.23x**; REAL SHEET serial **258 → 125 s (2.07x)**, certified 1358 = the serial pin. Profiled main-thread CPU 350 → 143 s: `_refresh` 206.6 → 14.1 s cum, `expand` 191.5 → 8.0, `StoreIndex.build` 143.9 → ~0, `parse_key` 12.42 M → 36 k calls, `ResourceKey.__lt__` 88.9 M → 16.4 M. Equivalence is a by-path harness that builds the oracle beside the maintained index at EVERY commit of four real decodes, re-derives every expansion with an empty memo, and carries three fault injections that must bite | `plane.invalidate`, `_DerivedViews.advance_index`; `tilemap.StoreIndex.updated`; `payload.RealPayloadProvider.expand`; harness `holo2/measure/index_equivalence.py` | CLOSED |
| — | **THE POOL-THREAD LAZY-INDEX-BUILD RACE — dispositioned, not fixed (2026-08-18, H4 W6).** The review's pre-existing note (MEASUREMENTS, F-17's "ONE FINDING": the observer's private per-render `StoreIndex.build` "with a documented retry for *a dict mutated under the observer while the committer worked*"). WHAT IT REFERS TO, generalised: `StoreIndex.build` reads the LIVE store — `Store.keys()` then one `store.get` per key — from whichever thread first touches a generation, while the main thread commits. **NARROWED TWICE SINCE, and the observer half is GONE**: F-17's second residual replaced the observer's rebuild+retry with the plane's maintained index, and the eager advance runs on the committing thread, so the from-scratch build survives only as the SEED — reached when `advance_index` returns `None`, which in production means "nobody asked this generation for an index" (`changed_keys` is never `None` on the commit path). **STILL LIVE, MEASURED**: patching the builder over `holo2/tests` counts **149 builds, 22 of them on a pool thread** — the seed path really is touched off the main thread. **TWO HAZARDS, both dispositioned.** (1) *Iteration crash* — `keys()` is `tuple(sorted(self._entries))`, and on this build (CPython **3.14.6, GIL enabled**) the key materialisation is a single C-level loop: 300 `sorted()` calls against a thread churning the dict raised nothing. The premise IS the GIL, so **the free-threaded 3.14t card (H4-PLAN banked card 3) inherits this as a prerequisite**, not as a footnote. (2) *Torn read* — the per-key `get` loop is Python-level, so a build spanning a commit mixes generations and can hand a reader an index NEWER than its own pin. That is precisely what the pre-F-17 build always did (`_DerivedViews`' own docstring says so) and §7 already prices it: the identity re-derivation at the wall discards a proposal whose read-set moved. **Waste, never wrongness** — and the containment, if the free-threaded card ever makes it wrongness, is to seed on the committing thread or to give `Store` a snapshot read; unwarranted today, since the profile puts the surviving build at ~0 | `plane_views._DerivedViews.index`; `tilemap.StoreIndex.build`; `core.store.Store.keys` | ADVISORY |
| F-23 | **CLOSED with F-08 (2026-08-13).** The DONE cache key is the pair of monotone counts (committed poses, certified keys); R3 closed the page dependency, and the residue was "a fact replaced under its own key changes no count". No such replacement exists any more: a pose is identity-frozen (every field is in or pinned to its key), certified tile content is L5-frozen, and the geometry a pose stands on (window extent, region grid, capture dpi) is key-named or transition-frozen — so the counts ARE a sound cache key, by wall-enforced construction rather than convention. H4 W-S wave 1 moved the cache into `_DerivedViews` (one immutable generation per commit): the key is unchanged and is now the INHERITANCE test — a new generation carries the done map forward iff the counts match | `plane.py` `_DerivedViews._done_table`; §6 above; core F-08 | CLOSED |
| F-15 | `TileMap.counts()` counts only materialised rows, so UNKNOWN is always underreported for a lazy logical domain: report full-domain counts, or rename them `materialized_counts` and publish the logical cardinality beside them | `tilemap.py` `counts` | HIGH |
| F-10 | **CLOSED (R3)** — `PoseRecord` v2 carries `page`, validated in-domain by the family's structural validator (the gate registers only when the session declares a non-empty page domain) | `records.PoseRecord`, `_page_domain_validator` | HIGH |
| F-02 (solve half) | **CLOSED (2026-08-18, H4 W6) — the narrower typed read this row asked for, built, and the property deleted.** `SessionPlane.store` handed anything holding a plane the whole `Store` through a read-only-by-convention property, wider than `PlaneView` declares (which names no store at all). Two of the four reads the row counted had already gone: F-17's second residual replaced the observer's two private `StoreIndex.build`s with the plane's maintained index (`_ctx.index()`, 2026-08-17). The remaining two became three narrow reads on the plane — `commit_seq` (the frame revision, work-counted, never a clock), `close_record()` (one durable record by key) and `attempted_work_keys()` (the ATTEMPTED key set; the counting rule stays the payload family's, and the plane's own tile tally now asks the same method, so the chips and the tiles row cannot come to differ). `PaneSource`'s duck-type gate asks for those three by name instead of for `store`. Relocation only: same information, same values, no new derivation and no schedule change; the plane's own internals read `self._store` as they always did. The bind/execute half of F-02 (`core/DESIGN.md`) is a separate row and is untouched | `plane.SessionPlane` `commit_seq`/`close_record`/`attempted_work_keys`; `diag/panes/model.py` `PaneSource` | CLOSED |
| — | **CLOSED (2026-08-12, W-B B7 — RULED "take it, carefully and completely")** — `collection:poses/<window>` had zero subscribers while `RealPlacementWorker.read_keys` enumerated `pose_key(pose_id)` per sibling: a read-set that provably could not name a pose that did not exist yet, which is the hole M4 collections exist to close. The worker now names `pose_collection_key(...)` for its own window and for every sibling window of the region — O(siblings) keys instead of O(siblings × poses) — and still reads the pose RECORDS through the view at fire time (`_settled`, the §6 gate): the collection is the identity, the records are the values. The systematic rule the ruling recorded: a future fact with an a-priori knowable name is subscribed DIRECTLY and arrives as a bump off `ABSENT_VERSION` (the seed hint); a future fact whose NAME IS ITS UNKNOWN VALUES — a pose key, since the hash-free identity law — is subscribed through its structurally named collection. Placement no longer leans on the orchestrator's commit-time read-set re-derivation (`_is_current`) to notice a sibling's first pose. This MOVES declared read-sets, hence §7 identities and the lineage (pre-freeze, deliberate); no record shape changed, so no schema bump. `PROVIDERS.md` §8.4's M4 consumer column now has its first placement subscriber | `records.pose_collection_key`; `placement_h3bis.read_keys` | CLOSED |
| — | `LabelPool` — **declared, unbuilt**: the family is registered and validated, and no production writer or reader exists (`PROVIDERS.md` §8.4: the calibration providers that would own it "do not exist yet"). **KEPT** under the B8 principle (RULED 2026-08-12): declared-but-unbuilt durable surface stands iff a scheduled owner exists AND the shape traces to measured doctrine — here **CA1–CA7 (H5) owns it**, the member set is forced by the reduce's scope, and `label_site_count_by_kind` is the one adaptable field. Without an owner it would be deleted, as `RouteSpend` was (window family v3) | `records.LabelPool` | ADVISORY |
| — | `SubjectSpec` — **declared, unbuilt**: the R1 subject surface plus its subject collections exist so expansion resumes across a subdivision, and no production provider mints one. **KEPT** under the same B8 principle. AMENDED 2026-08-17: PL5 owned it and DID NOT USE IT — subdivision shipped as a scheduler escalation over in-memory members, so nothing about resuming across a subdivision needs a durable subject (a resumed parent re-subdivides and the kernel names the same children). It is now owned by nothing; the shape is the M3 durable-subject contract, with `parameters` as the provider-owned adaptable field | `records.SubjectSpec` | ADVISORY |
| — | **PROVENANCE CORRECTION (documentation, not behaviour).** `place_job.regional_seed`'s docstring calls the least-squares regional affine "v1's regional fit, resurrected as a fire-time query" — verified wrong. `np.linalg.lstsq` appears exactly once in all of `src/holo/receive/` (`color_registration.py`, a photometric per-plane offset fit, not a placement-pose geometry one), and no least-squares affine over accepted/committed poses exists anywhere in v1's `place.py`/`search.py`. `regional_seed` is HOLO2-ORIGINAL — v1-inspired by the gap-jumping motivation (ruling R-B), not ported. Left for the owner of `place_job.py` to correct the docstring (out of this work package's ownership) | `place_job.py regional_seed` | ADVISORY |
| — | **RECORD HONESTY (documentation, not behaviour).** W2's external review is recorded (`H4-W2-PLAN.md`, "W2 EXIT") as "34 confirmed findings fixed" — that aggregate was never itemized anywhere in this tree. Only the individually named fixes (F-17, F-28, the B-rulings above, and their kin) are independently verifiable against this ledger; the count is conversational history, not a durable record. Stated so it is never mistaken for one — not reconstructed | `H4-W2-PLAN.md` W2 EXIT | ADVISORY |
| — | **CLOSED (2026-08-18) — v1 PARITY DEVIATION, WITHDRAWN on the user's ruling "we want parity to v1".** W2's pooled pass budget added the Stage-A domain of every spent word stage (`49 x (tried + offered) + 147456 x words_spent`) to the placement `AttemptBudget`. v1 has no such term on any route: `_chain_budget` (`holo/receive/place.py:217`) declares `49 x n_anchors`, and `_word_route` (`place.py:1344`) is handed `budgets.local` = 49 UNMODIFIED, Stage A being priced by its own union bound (`holo/receive/words.py:78`) against `familywise_false_accept` rather than by the identifiability site count. Two spent stages put the domain at 294,961, past the 250,530 knee of `ceil(log2 D / (1 - h2(0.08)))`, so the derived floor read **31 where v1 reads 30**. **DIRECTION: a BAR, not an extra attempt** — `min_support` is compared `>=` against supported sites, so it REFUSED windows supported at exactly the 30-site `E022_SUPPORT_FLOOR_SITES` that v1 ADMITS (and it bit every pass after both stages were spent, wide and cold included, not only the rest-word pass). Now `49 x candidates` on every path = v1's arithmetic on all three | `place_job.pass_budget`; Q1 text above; pins `tests/solve/test_place_job.py` | CLOSED |

## In-band sentinel audit (2026-08-12, W-B B6-AUDIT)

F-09 was one instance of a CLASS: a value read back as MEANING where the
sentinel is also a legal measurement (`0` / `0.0` / `()` / `None`
standing for "absent" in a domain that can measure exactly that). The
ruling asked for the class, not the instance, so every such read in
`solve/` and `capture/` was walked (grep-driven over `== 0`, `== 0.0`,
`!= 0`, `is None`, `== ()`, `.any()` guards, then read in context) and
classified as one of:

* **structure-derived** — the sentinel is placed by geometry or by the
  format at addresses known independently of any pixel, so no
  measurement can produce it ambiguously;
* **documented convention** — the sentinel is the domain's declared
  spelling and the docstring says so at the site;
* **typed out-of-band** — absence has its own value outside the measured
  domain (`int | None`), which is the pattern the rest should converge on;
* **F-09 sibling** — fix, or a TO-FIX row here.

| site | reads | classification | verdict |
|---|---|---|---|
| `payload._freeze` | `gap = owner == 0.0` as "unobserved" | **was the F-09 sibling** | **FIXED** — ownership is `piece.observed & ~owned`; no evidence value in owner selection |
| `placement._place` / `place_shared._tile_slice` | `observed` = the AUDITED core, sliced per tile | structure-derived | safe — sampler coverage, the erosion, and the straddle audit's own verdict; no score value participates (W1: the mask was `valid & inside & supported` while the stand-in sampled per tile) |
| `place_shared._tile_writes` | LLR left 0.0 outside `observed` | structure-derived + durable mask beside it | safe — the pair (`llr_ref`, `observed_ref`) is what makes the freeze's fix expressible; the at-rest, real-run pin (`holo2/measure/test_real_e2e.py`, mask ⊇ nonzero LLRs) was deleted with the measure cleanup and has no surviving holder — history has the driver — but the per-tile mechanism claim stands, pinned by `holo2/tests/solve/test_placement.py::test_a_partly_observed_tile_carries_its_mask_and_nothing_else` |
| `tiles._validated_llr_cells` / `_informative_count` | `0.0` IS the erasure spelling; `x != 0.0` counts informative cells | documented convention (and a CARRIED leaf, AST-pinned) | safe — a cell at p = 0.5 carries literally zero information for BP, so the `k_eff` floor counting it as non-informative is exact, not a conflation |
| `tiles._descramble_validated` | site cells forced to `0.0` | structure-derived | safe — the addresses come from the format's site mask, not from the pixels (the ruling's own example) |
| `records.TileRecord.metadata_bit` | `None` vs `0` | typed out-of-band | safe, and the pattern to copy — `close.certified_symbols` refuses a CERTIFIED record whose bit is `None` instead of reading a bit that was never decoded |
| `records.MintRef.contributors` | `()` = "the primary witness is the whole set" | documented convention | safe — `route` disambiguates structurally (scan/retry150 never have components, union always does) |
| `records.TileRecord.observed_by` / `baselined` | `()` = no member yet | structure-derived (monotone sets grown at the commit wall) | safe — empty IS the fact, and the transition rule forbids losing members |
| `payload.crc_exposure` | `not spend.exposures` skips the row | documented convention | safe — a zero counter means no decoder ran (below-floor), the total is a sum so the skip is arithmetically inert, and `spends` is DEFINED as rows carrying exposure |
| `plans.window_plans_for` | `supported == 0` skips a window | structure-derived | safe — a count over the support mask; zero supported cells is the measurement |
| ~~`wordgrid._refine*`~~ | `spread[spread == 0.0] = 1.0` | documented convention (numeric guard) | RETIRED with the module (H4 W1). The carried kernel's equivalent is `pose_fit.median_radiometrics`' `max(spread, 1e-6)` floor, which the row below covers |
| `geometry` affine guards | `determinant == 0.0` | documented convention (numeric guard) | safe — degeneracy refusal, not absence |
| `capture/records.RegionRecord.pitch_in_vote` | `Fraction \| None` | typed out-of-band | safe, and the pattern to copy — the survey's honest "no credible pitch" instead of a fabricated 0 (L4) |
| `capture/survey` refinement | `labels[...] != 0`, `touching != 0` | structure-derived | safe — scipy's background-label convention; and the boundary scores travel with their own `known` mask, so an unmeasured cell is never a zero score |
| `capture/scale_space` resamplers | `active = overlaps != 0` | structure-derived | safe — a zero overlap weight contributes nothing by arithmetic |
| `capture/_survey_tensor`, `capture/scan` | `size == 0` / empty `(0, 0)` returns | documented convention | safe — emptiness, not a zero-filled measurement |
| `core.identity.ABSENT_VERSION = 0` | "this key is not committed" | **VERIFIED out-of-band** | safe — commit assigns `store.version(key) + 1` (`core/commit.py`), so the first durable version is 1, and the store REFUSES a loaded `version < 1` (`core/store.py`). Version 0 is unreachable for a committed record, which is what makes subscribing to a not-yet-existing key legal |
| `core.trace` `sample_every=0` | sampling off | documented convention | safe — stated at `core/trace.py`'s module docstring; `N > 0` samples |
| `core.work.Decline(wake_on=())` | a permanent refusal | documented convention | safe — stated at the field ("an empty `wake_on` is permanent and says so") |

**TO-FIX (documentation, not behaviour)**: `solve/records.py`'s R3 header
still says "**The freeze still keys on zero** — fixing that is integrity
semantics and belongs to the review round". That round has happened; the
sentence is stale as of this audit and is left for the owner of that file
to correct (it was outside this work package's ownership).

No other F-09 sibling was found in `solve/` or `capture/`.

## The pixel ground-truth path — solve's half (2026-08-15)

Root DESIGN §6.8 is the doctrine; solve realizes stages 2 and 3. The
prepared-region store (built by the W1 memory fix) owns: the
region-scalar memo (the platen-backing median over the raster's four
border strips — per CAPTURE, once per session, generation-INDEPENDENT — raster and
mask are immutable, so a generation-keyed rebuild would be a
per-commit full-region pass, the exact cost class this doctrine
removes) and the build-once streaming memmap prepared planes fires
read through. Placement fires hold views + window-sized working
arrays only; the whole-region float32 exists exactly once per
(footing, region), file-backed, disposable. The payload family reads
no pixels at all: `payload` consumes committed
`EvidenceObservation` blobs, and the per-tile cell reads inside them
are the placement fire's own `sample_segment` of the prepared plane,
scattered into tiles by `place_shared.emit_placement`. The raw crop
that inventory once named was `placement_h3bis`'s per-tile sampler and
died with it at W1a, so the "scheduled switch" is TAKEN — pinned
byte-identically against `prepare_region` off the raw raster in
`holo2/measure/test_prepared_evidence_e2e.py` (deleted with the measure
cleanup; the byte-identity comparison itself has no surviving holder —
history has the driver), and held in place by the entitled-module
allowlist in `test_conventions.test_raw_pixel_reads_stay_on_the_prepared_path`,
which still stands. Region-scale
COMPUTE (cold's transform cache) waits for the engine's leases (its
own wave) — nothing else may hold region-scale anonymous memory.

## Carried leaves

| leaf | from | adaptation |
|---|---|---|
| tile decode chain | `src/holo/receive/tiles.py` | unchanged semantics (descramble → perm → LDPC → CRC) |
| PAVA + ctx detector | `src/holo/receive/detect.py` | scope framework; H3bis uses the marginal arm only |
| pose fit / sample / layout | `placement/geometry.py` + `placement/reference.py` | **PORTED W0 2026-08-15 per H4-PLAN R4** → `pose_fit.py` + `reference.py` (K-only, colour elided H7): refactored along holo2's seams, arithmetic exact, behaviourally pinned (6,082-comparison differential, byte-exact, zoom-refit + edge-seed arms exercised); v1's mutable `RegionContext.lattice_f` became the explicit `LatticeSeed` parameter/return (R5's storable form); first consumers of `place_model.OR9_FLOORS` |
| score / audit / refine / harvest | `placement/search.py` | **PORTED W0** → `pose_audit.py` (698-comparison differential; memo caller-owned; ceil edge, stable argsort, tie-breaks preserved) |
| cold correlation kernel | `placement/search.py` | **PORTED W0** → `cold.py` (BIT-IDENTICAL differential incl. v1 at workers 1-8; `_parallel` fan-out flattened sequential per the declared precedent; `set_workers` dropped; page-transform cache caller-owned — W4's lease seam) |
| word stage-A decode | `words.py` | **PORTED W0** → `words.py` (33-fixture differential, content+order; `known_position_words`/quarantine → W5 with R7(b)'s stable sort) |
| placement model / budgets / gates | `placement/{model,policy,defaults}.py` | **PORTED W0-A1** → `place_model.py`: OR-9 floors as data (15 rows, one derived), v1 qualification-id strings kept verbatim (audit identity) |
| colour leaves | merged main only | H7; do not fork pre-merge colour |

`wordgrid` and `placement_h3bis` — holo2-original H3bis-grade placement,
a word-seeded page-wide sweep adequate for an intact, well-scanned sheet
— are DELETED (2026-08-15, H4 W1). The ported kernel's own provider
(`placement.WordPlacementProvider`, census PL3) runs in their place, with
`place_shared` holding what every future route of the family shares: the
M12 attachment gate, the window→page frame bridge, and the inline
marginal-PAVA calibration + per-tile evidence emission the H3bis worker
carried inline (H5/CA1 lifts the calibration half out).

**Carried consequence, on record for H5/CA1**: because calibration is
still inline, a calibration refusal in `emit_placement` drops the whole
emission — including the pose this same window's straddle audit already
accepted (`place_shared.py`, the `fit.accepted` guard). Poses on
calibration-poor edge windows are therefore lost outright today, not
merely uncalibrated; the coverage and any future refinement that pose
would otherwise have fed never happens. Splitting calibration into its
own provider (H5/CA1) is also what lets an accepted pose commit
independent of how its calibration fares.
