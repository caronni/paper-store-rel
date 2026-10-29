# LIFECYCLE — the generic engine, narrow keys, one lifecycle per row

Branch `sched-lifecycle`, base `840a97ca`; plan
`LIFECYCLE-PLAN-2026-09-21.md`, analysis
`LADDER-RECONSIDERATION-2026-09-20.md`. Germano's mandate, 2026-09-20:
*"clean up the engine special cases, make sure that there are narrow
subscribable keys, and have the right lifecycle for the plugins and
workers according to the design intent."* Prices do NOT move (his
exclusion), the residue-rung ORDER is not decided here. **ALL THREE
STAGES LANDED, then §1a's amendment**; the per-row table is API.md §6b.

## 1. Stage 1 — the engine went generic

| # | mechanism | before | after |
|---|---|---|---|
| 1 | `descriptor.retire` | `bool`; place's CAUSE re-asked inside the engine behind `worker.plugin == "place"` | `str \| None` — the cause, or None while the row lives. The engine tallies it for EVERY row and never reads it |
| 2 | seat / retire events | `WindowScheduled` / `WindowRetired`, place only | `WorkerSeated(plugin, subject, stage, cost)` / `WorkerRetired(plugin, subject, cause)` for every row; the window views filter `plugin == "place"` |
| 3 | read-set re-derivation | `_touch` tested `fact_key[0] == KEY_POSE_AFFINE and fact_key[1] == worker.subject` | `PluginDescriptor.rederive_on`, declared by `refine`, `refine.color` (their reach) and `place` (its children) — **gone the same day, §1a**: reads are fixed at birth |
| 4 | the retire door | consulted at the POP only | consulted at the PUSH first, then at the pop |
| 5 | `tiles.uplift.retire` | `not eligible` — false again whenever a window left the page | its monotone half, `page_done`; the window test stays in `eligible` |
| 6 | subdivision, afterlife, ladder climb | `engine._subdivide` / `_afterlife` / `_place_repush`, calling `engine._repush` / `_bookmarks` back from the fold | `_Folds` methods. `place` READS its own `place_stage` key, so the climb is an ordinary wake; the afterlife is the parent's subscription to its children (**§1a**: the quartering became a RUNG and the afterlife a store-routed key) |
| 7 | the place SETTLE key | the parent watched each child's `place_stage`, which fires on every rung spent | `KEY_PLACE_SETTLED`, emitted only when `placed` or `retired` moves — **retired in §1a**, when the parent stopped subscribing to its children at all |
| 8 | who retires a subdivided parent | `engine._place_repush` withheld `state.retired` from a parent that had JUST quartered itself, and latched on the next spent settle | the same, in the fold — a fresh subdivision returns early, the settle after it latches. `place_sched.afterlife_owed` holds the BOOKMARK meanwhile (the latch was unconditional until the stage-2 review; §4b B1) |
| 9 | the word-route tally | `engine._merge` read `fact.route == place.ROUTE_WORD` | `_fold_placement` returns the accounting family `pose_word` |

## 1a. THE AMENDMENT — reads are fixed at birth (same day)

Germano, on reading stage 1: *"the question is what leads us to
cleaner, more efficient and easier to understand code."* Applied: a
worker's declared reads are its TRUE INPUTS and are FIXED AT BIRTH,
and every derived relation — which tiles a window reaches, which parent
a child's settling concerns — is the STORE's, which routes a change to
the key its owner already holds.

| # | mechanism | stage 1 | the amendment |
|---|---|---|---|
| A1 | growing a live worker's reads | `rederive_on` + `engine._rederive` / `_rederive_reads`, one `reads()` call per wake of a declared kind | DELETED, with both declarations. The ONE path is `engine._births` extending a standing bookmark when its BIRTH FACT is folded again — generic, already in the tree, and the honest statement of the fact: a re-placed window has a new reach and possibly a new page. `refine` / `refine.color` are born by `Placement` and every adopted revision folds one (`_fold_refine_outcome` calls `_births` itself), so they lose nothing. Keys a row no longer needs are KEPT rather than pruned — over-declaring costs a wake, under-declaring loses a re-arm — and go at retire. Both halves benched on `refine` in `test_h3_store_wakes` |
| A2 | subdivision | the place-outcome FOLD computed `child_windows` and ingested the four `Window` facts — a fold that creates facts | a RUNG. `place.stage_of` answers `subdivide` exactly where the fold quartered (ARMED by the two direct refusals, LAZY once every rung is spent), evaluated at the POP like any other rung, so a seed that arrived meanwhile is seen first — RING outranks it. `prepare` returns a pixel-free job: the four children, then the outcome that marks the parent. The child `Window` CARRIES its parent's id, so `_fold_window` links both ends and a resume rebuilds the relation the old `_subdivide` never restored. The ladder never offers the rung to a window under the subdivision floor |
| A3 | the afterlife | the parent subscribed to each child's `KEY_PLACE_SETTLED` | the STORE routes: `_settle_child` writes the settle into the PARENT's state and emits the parent's OWN `place_stage` key — the one it has read since birth — when the last child settles without a pose, or when one places and cancels the afterlife. `afterlife_owed` reads that state alone and walks nothing. Nothing read `place_settled` after that, so it left the vocabulary: **18 key kinds** (19 since 2026-10-03: `window_done`, 56928c45) |

**The one new price literal** is `STAGE_COST['subdivide'] = 40`, equal
to `STAGE_COST[ring]` by construction — the mandate excludes inventing
prices, and the rung fires once per window for microseconds. It is SEATED
three times in one colour sim and FIRES in none of the eight arms
(MEASURED §4.1; the "27 seats, fires" first written here was an over-claim,
corrected 2026-10-03); the sims' closes are byte-identical with the rung
in the ladder. On paper it first fired on the J run of 2026-09-24 (325
fires, 1,279 children, 216 placed — MEASURED §5). **`place.py` split at its own seam** (1015 lines):
`place` is the placement LAW, `place_pass` the JOB it schedules.

**A sleeping window still quarters**, and the dormancy compensation
STAYS — one statement now, not a count. `pose_refused` arms the rung
and sleeps in one fold, so the quartering is work the window HOLDS:
`dormant()` is False while it is owed, the sleeper takes that rung, and
the stamp moves with the fold's own key so the sleep resumes. Deleting
it reproduces the colour-sim livelock, whose cause — `place` reading
its own key (§1 row 6) — this amendment does not touch.

## 2. Stage 2 — the verdict became a fact with a key

| # | mechanism | before | after |
|---|---|---|---|
| 10 | `tiles.py` | 947 lines, decode and scheduling in one file | split at the format/scheduling seam: `tiles` (the format law) + `tiles_sched` (the three ordinary payload rows). Byte-neutral |
| 11 | `_fold_attempt` | emitted NO key — a verdict woke nobody, so the residue ladder existed only at BIRTH | emits `KEY_ATTEMPT` = `(page, ty, tx, stream_id, stage, lane)` — with `place_settled` gone the same day the vocabulary stood at 18 kinds (19 since 2026-10-03's `window_done`) |
| 12 | `AttemptFact` | said what happened, not what it read | carries `generation` — the tile-lane counter the decode read, reported back by the job. Not snapshotted, defaulted to 0 |
| 13 | the tile-lane counter | did not exist | `_tile_lane_generation`, bumped by `_fold_evidence` / `_fold_color_row` over the UNION of the old and new cover, and `_union_generation` beside it, one per FOOTING, bumped the same way. Both DERIVED, no snapshot field |
| 14 | `tiles.retry.reads` | literally `_scan_reads(...)` — the chain head's own read set, at the same price | ONE key: its own baseline verdict. `eligible` requires that verdict failed AND at the lane's CURRENT generation, so it fires at most once per generation. (The clause "never concurrently with scan on the same cut" first written here was an OVER-CLAIM: a scan woken on a stale evidence key re-read the identical cut beside the retry; since 2026-10-03 `prepare_scan` skips a cut whose every pending stream already holds a verdict at the current generation, 162f1227) |
| 15 | `tiles.local` subject | per tile-STREAM, while the work — the covering windows' whole colour head — is per tile-LANE | `(page, ty, tx, ppc)`: one build, every armed stream decoded off it, each stopping at its own first certificate |
| 16 | `tiles.local/planek/swim` reads | the evidence rows and colour rows of every covering window — `tiles.scan`'s reads | their own arming VERDICTS, plus the page field, the neighbourhood's certificates, and (planek, swim) the per-window `pose_affine` they sample through. *Dated note 2026-10-18 (SCHED-LIFECYCLE-REVIEW-2026-10-17 §4): since `162f1227` (2026-10-03) the verdicts read are the chain head's only — scan and union, `local_ctx.READ_STAGES`; a retry150 failure arms all three and a local150 failure arms `tiles.swim` only (through the footing ledger), waking nothing — and `tiles.local`'s colour arm reads `pose_affine` too* |
| 16b | what ARMS `tiles.local` | nothing to read: the bookmark was born by the failure and lived until a certificate | `store.attempt_ever_failed` — the same franchise, now a monotone ledger beside the last-write-wins verdict. Only a certificate takes a stream out (§4b B3). *Dated note 2026-10-18: arming reads `store.attempt_ever_failed_at_footing` since `9b67d896` (2026-10-03, a failure outlives its lane's place in the cover); the narrow `attempt_ever_failed` ledger was written and read by nothing after that and was deleted 2026-10-18 (SCHED-LIFECYCLE-REVIEW-2026-10-17 D11)* |
| 17 | `tiles.swim` and `lane_poses` | the page-wide lane-pose key, 5,880 subscribers, 74.8 % of sheet H's wakes for 19 fires | gone; `_fold_placement` emits `pose_affine` at the same site under the same test, so it is the same wake at four keys |
| 18 | `revisit` | an 18th row, measured inert twice | DELETED. With it `REARM_PLUGINS`, the single-writer check's one exemption, and the last plugin name in `engine.py` |
| 19 | terminal facts | a fold that emitted no key was invisible | `descriptor.TERMINAL_FACTS` — five types with a reason each; anything else emitting no key fails the build |

**INV-G1**, the invariant the narrowed reads rest on: every
`_advance_tile_lanes` call sits inside a fold that ALSO emits a key
`tiles.scan` subscribes to over the same cover, so a generation never
moves with the chain head asleep. Pinned on all three bump paths.

## 3. Retire causes, per row

Every row's causes are API.md §6b's `retire cause(s)` column. Five
rows never retire (`calibrate`, `ctx`, `color`, `color.pooled_ctx`,
`fields`): a later pose, evidence set or observation can always change
what they publish, so they leave the frontier through `stage() -> None`
and the version floor.

**Monotonicity is the precondition**, because retire is consulted at
every WAKE: a clause that can go false again kills a live row at the
first wake that samples it high (`tiles.uplift`'s was narrowed to
`page_done` for this, `tiles.retry`'s stopped being `not eligible`).
`test_h3_lifecycle` drives a rising frontier past the rows a K bench with
one PLACED window can arm and asserts each answer latches; since
2026-10-03 (349eee50) a colour bench and a pose revision drive it too,
and the one clause that was NOT monotone — `done_covered` under a pose
revision — is no longer a retire cause (56928c45; §8).

## 4. Deviations from the plan, with the argument

| # | item | what was done, and why |
|---|---|---|
| D-a | plan §2.6: `rederive_on=(KEY_ATTEMPT,)` on the residue rows | **NOT declared** — `_births` already does it (born by AttemptFact, every cover change re-fires the chain head, whose fresh verdict re-births the row and appends the keys). §1a made that argument the whole law |
| D-b | plan §2.2: `tiles.uplift` reports its generation | **NOT threaded.** It is the one LANE-PAGE row and one fire decodes many tiles, so there is no single counter for the job to report. No row has `uplift_a3`/`uplift_a4b` in its arming stages, so no verdict of its is ever compared by generation. Commented at the call site; the targets already walk per tile if that changes |
| D-c | plan §2.4 `afterlife_due` as a stage predicate (stage 1) | Not built that way — the store flips the flags (§1a: in `_settle_child`) and `ladder_stage` reads them. What the review made necessary is the RETIRE half, `place_sched.afterlife_owed` |
| D-d | the price block's home in the `tiles` split | `PAYLOAD_COST`, `RUNG_COST`, `PRICES` and `STAGE_PAYLOAD` moved to `tiles_sched` with the rows that charge them; the decode budgets (`BASELINE_BP_MAX_ITERS`, `RETRY_BP_MAX_ITERS`, `BP_ALPHA`) stayed in `tiles`, where they are decoder identity |

The plan's own NINE deviations are argued in its §D1–D9. **D1**
(subdivision stays in the fold) is **SUPERSEDED by §1a**, which takes
D1's own recommended alternative: a job cannot decide the lazy case, a
STAGE evaluated at the pop can. **D4**, "settled" is read off
`WindowState` alone, so a child the done gate retired does not count.
**D5**, `place` does NOT subscribe to certificates: 1.9–5.9 M wakes per
candidate key, each paying an O(330) `stage()`, and a wake retires
nothing on its own. **D6/D7**, `revisit`'s two relations are DELETED,
not re-expressed (the calibrate half cannot work — 0 adoptions in 601
fires; the place half's cheapest honest form is a region-anchors key at
231 k wakes against nothing it ever returned). **D9**, the residue rows
keep BIRTH on all three arming stages.

## 4b. The stage-2 review (2026-09-21), applied

Three blocking findings, all fixed and pinned. *Dated note 2026-10-18:
B2 was fixed and PROBED here, not pinned; B2 pinned 2026-10-18 by
`test_h3_store_wakes.py::test_the_footing_counter_bumps_once_per_lane_event_and_never_falls`
(SCHED-LIFECYCLE-REVIEW-2026-10-17 R5, `e7462c20`).*

| # | finding | disposition |
|---|---|---|
| B1 | `_settle_ladder` dropped base's `if state.children: return` guard, so a parent that quartered itself latched `retired` on the FIRST spent settle. `place.stage_of` answers STAGE_RING again the moment `untried_consult` is non-empty, so base still gave that parent one more ring pass when a neighbour placed later and offered it a new seed; the branch closed that door for ever. Strictly yield-losing, and the in-code justification named a base behaviour the base source does not have | **FIXED**: base's nesting restored verbatim — a fresh subdivision returns, the next spent settle latches. Pinned by `test_a_fresh_subdivision_keeps_the_parent_one_more_ring_pass`, which drives both halves and `_place_eligible` with them |
| B2 | `store.union_generation` summed the per-lane counters over the CURRENT cover and claimed monotonicity. It is not monotone: a lane leaving takes its whole term with it. Two `eligible` predicates compare it with `==`, so a stale verdict could look current again on a different component set | **FIXED**: `_union_generation` is a maintained cell, bumped once per lane event by `_advance_tile_lanes`, monotone by construction. Probed on the K bench, the reviewer's own sequence: accept / re-fit / refused-re-fit reads 1 → 2 → **3** where base read 1 → 2 → 0 |
| B3 | `tiles.local`'s arming demanded a FAILED verdict at the CURRENT generation. `_attempt_latest` keeps ONE verdict per (stage, lane), so a chain head regressing to `below_attempt_floor` de-armed the rung PERMANENTLY — `_local_retire` is certificate-only, so the bookmark lived on, never eligible, never retired. Measured on the traced sheet-H run: 2,667 such transitions, 7 uncertified tile-streams ending the run in that state. §4's D9 refuses exactly this hazard on the birth path and the eligibility path re-created it | **FIXED**: arming reads `store.attempt_ever_failed`, a monotone ledger — base's franchise exactly (born by the failure, lives until the certificate). Pinned by `test_only_a_certificate_takes_a_stream_out_of_the_residue`, which drives FAILED → generation bump → BELOW_FLOOR and asserts the rung stays armed. *Dated note 2026-10-18: the ledger arming reads is `store.attempt_ever_failed_at_footing` since `9b67d896` (2026-10-03); the narrow one named here was deleted 2026-10-18 (SCHED-LIFECYCLE-REVIEW-2026-10-17 D11), and the pin's control half now shows the hole through the current-cover enumeration* |

Non-blocking, **applied**: the generation is stamped PER ATTEMPT SET
(`local_ctx.Generations`, inert today); `covering_window_ids` skips a
window-less ordinal instead of raising on the ENGINE thread; dormancy
counts only `place`'s OWN-subject key; INV-G1's test drives all three
bump paths; the tally pins with `==`.

Non-blocking, **declined, with the reason**: (a) *`_settle_ladder`
relies on `if moved:`* — a fold that moved nothing bumps no version, so
base's unconditional push was popped and skipped by the version floor.
(b) *`_fold_attempt` adopts on a generation change* — real engine-thread
cost, named for the acceptance stage. (c) *retire-at-push consults the
done gate on every place wake* — §7.1. (d) *INV-G1 binds HISTORICAL
reads* — true, §7.9.

## 4c. The amendment's review (2026-09-21), applied

**GO**, no blocking finding: the re-birth path probed as the exact
replacement for `rederive_on` (a window re-placed onto another page
extends `refine`'s reads and `_index` before `_touch` runs), the
afterlife driven through all 24 permutations of the four children's
settle order to one identical end state, and nothing outside the dated
records naming `rederive` or `place_settled`. Three non-blocking
findings, all **applied** — each is this amendment's own mandate:

| # | finding | disposition |
|---|---|---|
| N1 | `place.subdivides()` and `NEVER_SUBDIVIDES` are dead — no production path consults either — and this commit made the predicate's declared law wrong in LETTER: it still called `cold_refused_*` the subdividing outcomes, while the shipped law is ARMED by `SUBDIVISION_DIRECT`, else LAZY through a spent ladder (any outcome). A test pinned the dead predicate | **DELETED**, both, with `test_subdivision_is_armed_only_by_the_declared_outcomes`. `place.stage_of` is the whole law and there is no second copy to keep in step; `SUBDIVISION_DIRECT` stays — it is what the fold reads — and carries the comment. Nothing lost: the fold's branches are pinned over its own AST by `test_the_store_folds_only_outcomes_the_placement_pass_can_produce`, and `stage_of` by its table |
| N2 | the subdivide rung had no test through `_fill` — both lifecycle tests call `prepare_place` directly, so nothing drove the new stage through the pop gauntlet (`retire`-at-pop, the version floor, `eligible`, the re-pricing compare) | **ADDED**: `test_the_subdivide_rung_seats_and_fires_through_the_engine_s_fill` seats the spent window through `_push_worker`, drives one `_fill`, and merges the job — four `Window` facts, both ends of the parent link, one `WorkerSeated place/subdivide`. Refuted: with `stage_of`'s lazy branch returning None it fails |
| N3 | `_births` could re-subscribe a RETIRED bookmark — the `standing is not None` branch did not test `standing.retired`, so a later fold of its birth fact put fresh keys back in `_index` after `_retire_worker` had dropped them. Harmless (`_touch` skips retired rows) but index growth that never goes, and the one case where API.md's *"they go when the row retires"* was false in the letter | **FIXED**: one `if standing.retired: continue`, after the trace's birth count (the fact did arrive). Pinned by `test_a_retired_row_takes_no_new_keys_from_a_later_re_birth` |

**Declined, with the reason.** N4 (informational): at
`WINDOW_STEP_CELLS=160` an appended tail start can put two parents'
quarters at the same extent, `_fold_window` refuses the duplicate, and
that parent's afterlife fires on three children — base behaved
identically, the amendment makes the parent link DURABLE so live and
resumed runs agree, and the window plan's geometry is a measured
question, not a review repair. And the stale `_rederive_reads` citation
in `retirement_docs-2026-09/RULINGS-holo2-draft.md`: a dated draft of a
retired receiver's rulings, conclusion unchanged, and a dated record
keeps its day's spelling.

**The engine's one remaining special case is the fountain close
consult** (`engine.run` → `_close_consult`): a verified close preempts
everything, is not a row, and is consulted out of band after any merge
that grew the certificate set. `engine.py` spells no plugin name and no
`KEY_*` constant at all.

## 5. Measured

Stage 3 ran the acceptance; every reduction, run dir by run dir, is in
`LIFECYCLE-MEASURED-2026-09-21.md`.  §5.1 and §5.2 are the STAGES
against base `840a97ca`; §5.3 is §1a's amendment against `677a7171`,
which is those arms' own tip. **Same payload, every time**: all
eight stage-3 sim decodes (K and colour, one and four workers, base and
branch) close VERIFIED with their emission's sha; at one worker the
trees are job-for-job identical and stage 2's table reproduced to the
unit (K 1,247 → 1,005 wakes, colour subscriptions 4,367 → 2,575), job
cpu flat to 0.5 %. The sims cannot show this work's target:
`tiles.local` never fires on them.

**Lanes** after the measurement: receiver fast 1,986 passed / 315
skipped / 1 xfailed, slow 2,267 / 34 / 1, repo suite 1,520 / 113; after
§1a 1,988 / 315 / 1, 2,269 / 34 / 1, 1,520 / 113; after §4c 1,989 /
315 / 1, 2,270 / 34 / 1, 1,520 / 113 (one dead pin out, two in), the
slow lane cold at 58 s with every close still byte-exact.  After §5.3's
measurement, unchanged: 1,989 / 315 / 1, 2,270 / 34 / 1, 1,520 / 113,
receiver pyflakes clean.

### 5.1 Sheet H, the bounded A/B — M1–M6

One 2400 capture of the e033 r0850 print, 12 workers, traced, ONE
SIGINT at 480 s, idle machine, arms back to back
(`scratch/lifecycle-20260921/H-base.50441`, `-branch.50857`).

| # | at the 480 s bound | base | branch |
|---|---|---|---|
| M1 | certificates (C / M / Y); jobs; job cpu | 2,142 (598 / 1,326 / 218); 40,978; 4,379.7 s | 2,118 (575 / 1,325 / 218); 41,330; 4,397.9 s |
| M3 | `place.stage` / `place.retire` cpu; main thread fill / push / touch; busy | 13.8 s (45,358 calls) / 36.7 s (4,773); 128.3 / 22.7 / 9.5; 195.8 s | 10.3 s (24,316) / **56.8 s (25,028)**; 93.2 / **67.6** / 1.9; 199.4 s |
| M4 | same-cut repeats (stream aware) | 23,712, 17,239 concurrent | 25,599, 15,515 — **retry→scan 4,268 → 442** |
| M5 | WAKES; to swim / planek / local | 6,151,946; 5,231,316 / 376,214 / 401,341 | **1,038,131 (−83.1 %)**; 384,651 / 360,178 / 181,431 |
| M5 | **sibling head fits** | 447 local fires / 180 tile-lanes, **152 for >1 stream** | 43 / 29, **0** |
| M6 | windows retired; max frontier; subscriptions | **0**; 54,733; 3,220,478 | **712**, every one `placed`; 38,258; 2,024,359 |

*Dated note 2026-10-18 on M4: "stream aware" is WRONG; the numbers
stand. `measure/sched_trace/report.py` joins on `input_digest_bare`,
which carries no stream, so the join is stream-blind and the
retry→retry repeats (MEASURED §2.7, 15,516 on the branch) are
sibling-stream pairs — 0 same-subject pairs of 15,955 when re-joined
per subject on 2026-10-17 (SCHED-LIFECYCLE-REVIEW-2026-10-17 §4).*

1. **The wake storm is gone; the main-thread bill did not move** (busy
   195.8 → 199.4 s): `retire` at the push costs `place` +20 s of done
   projection where `fill` saved 35, and a third off the frontier with
   712 windows retired buys it. The sibling fit is gone at an unchanged
   0.801 → 0.804 cpu-s per fire (447 → 43 fires).
2. **The 24-certificate gap (−1.1 %) does not separate the arms**: at
   420 s they read 2,118 and 2,114, inside the 5–7 noise band. The
   deficit is C (−23); the candidate is `refine.color`, 981 → 368 fires
   for 180.9 → 60.4 cpu-s. Named, not explained.
3. **Who mints moved, and retry became nearly barren** (MEASURED §2.8):
   2,706 cpu-s at 99.8 % zero-yield where base's 2,264 were 91 %, for
   the same certificate total — a PRICE and ORDER question, measured.

### 5.2 Sheet I, the canary to close — M7, M8

The capture e037 read, 12 workers, untraced, each arm detached
(`scratch/lifecycle-20260921/I-base.51123`, `-branch.52339`).

| # | | base | branch |
|---|---|---|---|
| M7 | close; certificates | VERIFIED `2445b95d…` = the emission; 5,279 | VERIFIED `2445b95d…`; 5,277 |
| M7 | wall; job cpu | 2,005 s; **22,334.6 s** | 1,982 s; **18,980.8 s (−15.0 %)** |
| M8 | `tiles.local` jobs / cpu / certs; certs scan / retry | 8,989 / 17,429.8 s / 770; 3,782 / 727 | 6,809 / 13,599.8 s / 700; 4,467 / 110 |

**This is the result that matters**: the same page, the same payload
byte for byte, 23 s sooner and for **3,354 fewer cpu-seconds** — all of
it `tiles.local` (78 % of the base decode), 2,180 fewer fires at an
unchanged 1.94 → 2.00 cpu-s each. `place` published 973 poses on BOTH
arms; neither fired planek or swim.

### 5.3 The amendment's own A/B — pre `677a7171` vs post

§5.1 and §5.2 measured the STAGES against base `840a97ca` and predate
§1a; this closes open item 9. PRE is `677a7171`, code-identical to the
tip those arms ran on; POST is the branch after §1a and §4c. Full
reduction: MEASURED §4.

**Same payload, every time, again**: all eight sim decodes (K and
colour, one and four workers, both trees) close VERIFIED with their
emission's sha, and **at one worker the two trees do the same work job
for job** — every fire counter, every wake kind, every certificate by
minting row, every retire cause equal, K and colour alike. The
four-worker arms differ by the ordinary race in both directions.

| # | | pre | post |
|---|---|---|---|
| A1 | sim w1, K and colour | job-for-job identical, VERIFIED | identical, VERIFIED |
| A2 | sim subscriptions (K w1 / colour w1) | 596 / 2,575 | **314 / 2,440** |
| A3 | sim bookmarks, colour w1 | 186 | **174** — 12 children never minted |
| A4 | sheet H, `place.reads` CALLS | 5,916 / 6,198 | **990 / 990** = the birth count |
| A5 | sheet H, `place.retire` cpu; main `push`; busy | 67.3–72.7 s; 78.8–84.1; 209.4–215.1 | **57.0–58.8; 69.0–69.8; 201.2–201.3** |
| A6 | sheet H, `pose_affine` wakes | 34,607 / 38,092 | **27,182 / 28,066** |
| A7 | sheet H, certificates at 480 s | 2,133 / 2,122 (and §5.1's 2,118) | 2,118 / 2,118 |
| A8 | sheet H, windows retired `placed` | 712 / 712 | 712 / 712 |

1. **A4 IS the amendment.** `rederive_on=(KEY_PLACE_STAGE,)` ran
   `place`'s read derivation on every ladder wake; birth-fixed reads run
   it once per birth, and 990 is how many births there are.
   `refine.color.reads` 2,054–2,128 → 933–945 the same way. The saving
   lands in `push`, almost entirely in `place.retire`'s share — fewer
   place wakes and retire calls (A4/A6). The attribution first written
   here, "a parent that no longer subscribes to its children", was
   WRONG: sheet H has no parents and no children, and
   `place_retire_cause`'s cost does not depend on the read set; the
   per-call drop is unexplained (re-review 2026-10-03). Total wakes, keys, subscriptions, frontier
   and job cpu are FLAT inside the pre tree's own spread.
2. **The bound cannot separate the trees on yield, and now we know by
   how much it cannot.** Two arms per tree were run; with §5.1's
   branch arm that is THREE runs of the PRE code, reading 2,118 /
   2,122 / 2,133 — **a 15-certificate spread on identical code, which
   is the entire pre/post gap**. §5.1's 5–7 band is a flat-stretch
   band and does not hold on this front. POST is the reproducible one:
   post-a and post-b agree to the certificate, to the plane and to the
   minting row. UNSEPARATED, and sheet I is still the yardstick.
3. **The quartering is lazy now, and that is all the sims show of it.**
   Colour w1's 12 missing bookmarks are three parents SEATED at the
   `subdivide` rung whose verified close preempts them, so the children
   are never born; nothing else moved (`place` fires 27 → 27, same
   payload). No `subdivide` rung FIRES in any arm, and **sheet H never
   subdivides at all** — 278 window keys, 712 placed, no
   `place_settled` on either tree. The rung's price on paper stays
   unmeasured. *Dated note 2026-10-18: "seated three times" is a LOWER
   BOUND — `WorkerSeated` is emitted only when a NEW seat is minted, a
   wake at an unchanged price keeps the standing seat (`seat_stands`),
   and ring = subdivide = 40, so a ring → subdivide change on a standing
   seat is not counted
   (SCHED-LIFECYCLE-REVIEW-2026-10-17 D8).*

## 6. Recorded losses

- **`revisit`'s place arm** — "a window of my region got placed and
  offers me a seed, and I am not one of its ring eight". 0 adoptions in
  601 fires, two corpora. Reopenable, at a region-anchors key.
- **`place`'s done-gate read** (D5). A page that certifies after
  placement has gone quiet retires nothing until the frontier drains;
  e036's idle run (6,164 of 18,256 `done_covered`) drained, and
  retire-at-push took sheet H from 0 retirements to 712. *Dated note
  2026-10-18: since `56928c45` (2026-10-03, §8) a done window NEVER
  retires — the gate suppresses through `worker_stage` (no stage, no
  seat) and `(window_done, wid)` lifts it when a pose revision re-opens
  the window; the 712 above were all `placed`.*

## 7. Open

1. **The measurement stage RAN** (§5). Left open by it: whether the
   non-monotone done projection retires a window on a transient (no
   `done_covered` on either arm, its +20 cpu-s price now known) —
   ANSWERED 2026-10-03: it could (the J run retired 44, 19 of them with
   an overlapping anchor refined afterwards), and the gate is no longer
   a retire cause (56928c45, §8); the C
   deficit at the H bound; planek/swim, which fired on neither sheet;
   and the K path on paper, unmeasured as it was before this work.
2. **Prices and the residue ORDER are unmeasured** and excluded by the
   mandate — LADDER-RECONSIDERATION §7.3 is the campaign, §5.1's barren
   `tiles.retry` its strongest exhibit.
3. **`tiles.local` fires are dearer and rarer at an unchanged price**,
   so its effective ladder position moved although the literal did not:
   sheet I, 2,180 fewer fires, 3,830 fewer cpu-s, 70 fewer own certs.
4. **`color`'s assembly/refit duality** — one row, two kinds of work
   under one bookmark, priced off a store cell. Noted, not changed.
5. **A subdivided parent with a done-gate-retired child is
   UNRETIRABLE**, and §1a does not change it: that child never settles
   in the store either, so `afterlife_owed` stays true and
   `place_retire_cause` never reaches `exhausted` — a live, stage-less
   bookmark, bounded at one predicate per wake. The cheap fix costs up
   to four done projections per place wake. Open.
6. **The `n_words` hole in `_fold_refine_outcome`** is documented, not
   closed: a word-route refinement has never counted, faithfully to
   base, and changing it would move a published tally.
7. **`pose.SUBDIVISION_MAX_DEPTH > 1`** would let a child that
   subdivided block its parent's afterlife for ever. Unreachable at
   depth 1, commented at the constant.
8. **INV-G1 binds the DECLARED reads**, and since §1a that is the only
   kind: the engine never prunes `worker.reads`, so a tile that LEAVES
   a cover keeps its historical wake — the stage-1 hazard (a
   re-derivation pruning `tiles.scan`'s reads) is now unreachable.
9. **The amendment was measured against `677a7171`** — §5.3, sims and
   a two-arm-per-tree sheet H. Two of this item's three worries are
   answered: the unpruned refine reaches cost NOTHING on paper (they
   were LARGER than the birth reaches, so `pose_affine` wakes fell a
   fifth), and the read-derivation saving is exact (`place.reads`
   6,198 → 990 = the births). The third STANDS: the quartering's own
   price is unmeasured, because the `subdivide` rung is seated three
   times in one colour sim, fires in none of the eight, and no sheet in
   this record — H, I or J — had subdivided a window when this was
   written. CORRECTED 2026-10-03: the J run of 2026-09-24 (3 captures,
   de567456) fired the rung 325 times — 1,279 children, 216 placed,
   afterlife 0 of 319, which §8 shows is structural — MEASURED §5.

## 8. 2026-10-03 — the repair wave, after the external review and the re-review

Main (42b56722, 41 commits) merged in at a7e41f2d, clean. Then eleven
commits, each one stage, each green on the receiver fast lane at
`-n 2` (a sheet recovery held the machine); the slow lane and the
default suite ran at the end. Every sim payload sha is unchanged (K
59495601d00f, colour ddf7acebcd86, groups 68e69038d474 / b0246ed26c3e,
p-axis dc0e2136dd4e / c5f6c8726177); no `assert_measured` pin moved.

| sha | what changed | measured on the sims |
|---|---|---|
| 037440da | `_fold_evidence` applies the region's ADOPTED correction at its head to an incoming uncorrected accepted row, so a re-fit over unchanged evidence stores identical and folds as nothing; `_fold_ctx_outcome` stores the decision first and re-corrects the rows STANDING at merge (never the prepare-time rows — the overwrite race the review found); the not-adopting and held re-folds are gone; `CtxOutcome` lost `inputs`/`outputs` (two empty wire fields keep old snapshots readable both ways — *dated note 2026-10-18: true for `CtxOutcome` only; `Window.parent`, on the wire since `b0fa4651` (2026-09-21), makes a snapshot of this tree unreadable by every tree before `b0fa4651`, `42b56722` included: the older decoder passes wire names as kwargs. One-way, no shim, the owner's call; SCHED-LIFECYCLE-REVIEW-2026-10-17 D5*); `region_pitch` emits only when calibrate's sampling pair (halo, aperture) changes — the pitch enters sampling nowhere else | serial K sims: calibrate fires 29→10 (k-w1), 112→26 (k-mixed-w1), 52→14 (k-local-patch-w1); retry 25→22, 33→26; scan 99→96, 122→113; K serial certificates 48, colour 81, unchanged |
| 9b67d896 | a FOOTING ledger beside the narrow one: a failure arms its tile-lane after its lane leaves the cover (`store.attempt_ever_failed_at_footing`; `armed_streams` asks it) | fast lane; no pin moved |
| 50a7395e | `tiles.swim` subjected per tile-lane `(page, ty, tx, ppc)`: one three-plane search and head read, one verdict per armed stream, retire when no stream is uncertified; a trace digest on its fires. The plan's §2.5 sentence that swim's search was per-stream was FALSE (planek's is) | fast lane; the colour sims fire swim 0 times |
| c078d307 | the residue rows are born by `WindowEvidence` and `ColorEvidenceRow` too (`local_ctx.COVER_BIRTH_FACTS`): a new covering lane's verdicts, pose and reach EXTEND a standing armed bookmark's reads — the reach hole; the same-outcome re-arm is NOT deleted (owner's ruling) | fast lane |
| 56928c45 | `done_covered` is no retire cause: `worker_stage` returns None while the window is fully done; the store memoises the unplaced verdict and, on a pose revision in the region, re-judges only the windows it had called done and emits `(window_done, wid)` for one that re-opened — the 19th key family, read by `place` from birth. Both remaining causes (`placed`, `exhausted`) are monotone; retire-at-push is safe | fast lane; the multires union census holds at the slow lane |
| 0fd1a7a7 | `measure/h3_repricing.py` imports `holo.receiver` from the chosen tree and refuses any other BEFORE the decode (`sys.modules["holo3"]` and the inert `--tree` were the review's tool defect); the last `-m holo3` spellings in `measure/` | pyflakes clean |
| 1d5f7a81 | `place` sleeps on a refused pass only if nothing woke it mid-flight (the engine exposes the merging job's bookmark generically; `store_folds` reads no bookmark by plugin name any more); an afterlife that buys no rung re-latches its parent, which retires `exhausted` instead of staying subscribed for ever (J's "afterlife 0 of 319" was this) | fast lane |
| 80194fac | an orderly stop DRAINS: no new jobs, every in-flight job merged, the close consulted, then `_finish`; a second signal abandons (stderr says so; a third kills); a resume whose folded certificates already verify consults once after replay | fast lane; MEASUREMENT PROTOCOLS with "one SIGINT at N s" now count the in-flight jobs' certificates — not comparable one-to-one with records before this sha |
| 162f1227 | residue rows READ only the chain head's verdicts (`READ_STAGES` = scan, union; retry stays an ARMING stage); `prepare_scan` skips a cut every pending stream already holds a verdict for at the current generation; `HOLO3_COLOR_ROW_ADOPT` is recorded (`RunOpen.color_row_adopt`, a line in the run dir's `tree` record, a stderr banner when not `last`) and the fixture builder REFUSES it; planek/swim stamp a one-component verdict with its LANE's generation; `tiles.local`'s colour arm reads the covering windows' `pose_affine` (it samples through them — an under-declared read) | fast lane; no serial fire count moved (the residue rows fire 0 on the clean sims) |
| 349eee50 | the engine-generic laws read the AST (string constants against every key kind and plugin name; `.reads(`/`.subjects_of(` outside `_births`; structural push/pop exits; no fold reads a bookmark by plugin name); 114 receiver-axis pins left `assert_golden` for `assert_measured` with a dated ledger, values unchanged (63 printed-format goldens stay); the retire latch is driven on a colour bench and by a pose revision | fast lane 2,091 passed |

Final lanes at 349eee50: receiver fast 2,091 passed / 315 skipped /
1 xfailed (27.7 s at `-n 2`); receiver slow, cold, 2,372 passed / 34
skipped / 1 xfailed (168.7 s); default repo suite 1,520 passed / 113
skipped (49.7 s); pyflakes clean. The widened matrix was NOT run.

Still open after the wave: a real full-extent cold pass after a lazy
quartering (the afterlife now only wakes; behaviour addition, owner's
ruling); a parent whose child is done-SUPPRESSED (not settled) is still
unretirable, as §7.5 said of the retired child; deleting the
same-outcome re-arm (study ruling 11(2), second half) and the honest
colour generation (11(1)); prices and the residue order; the first
real-sheet measurement of the cover-birth cost (c078d307), of 037440da
on a paper K sheet, and of the batched swim on J; the widened matrix.
*Dated note 2026-10-18: the branch as merged (`9b7e9b82`) was reviewed
in [SCHED-LIFECYCLE-REVIEW-2026-10-17.md](SCHED-LIFECYCLE-REVIEW-2026-10-17.md)
— twelve defects (D1–D12), the records against the code (§4) — and
repaired on branch `sched-review-repairs` (its §7, R1–R6b): the armed
quartering no longer lost to `insufficient_support`, union's
same-generation skip, the fixture cache without the plane scratch, the
trace pin's OFF arm, B2 pinned, the dead lane ledger deleted and these
records brought to the code. What that review leaves open is its §6.*
