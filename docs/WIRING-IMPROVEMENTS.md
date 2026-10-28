# WIRING-IMPROVEMENTS — runtime/scheduler wiring layer: verified findings & discussion

Status: **discussion, not normative** (2026-08-02). Findings first: nothing
here is an amendment or a fix. Every item needs a user ruling before code
(adjudication requests in §12); waste items are measure-first gated (§13).
PLACEMENT/PAYLOAD-IMPROVEMENTS are the template and the precedent.

Provenance: the 2026-08-02 wiring-layer verified read — addendum chip **A2**
of docs/PAYLOAD-REWORK-PLAN.md (user request: "the wiring needs major
simplification, while continuing to allow the staging/multi-lane/mop-up
functionality — but those, i think, are conceptually simple"). Reviewed at
HEAD `d81999d` on main (payload-rework fully merged; its worktree deleted;
R-lanes D20 stages A+B landed `dcd2025`/`6d21aa6`). One reader, full-file
reads with call-graph verification greps over: runtime.py (904),
runtime_model.py (518), cascade.py (581), session.py (792),
session_model.py (347), _runtime_validation.py (262), discovery.py (860),
discovery_state.py (379), evidence_context.py (196), types.py (893), the
production.py composition (~120 of 818), plus scan.py/records.py spot
verification. Governing texts read first: RECEIVE-DESIGN §8/§8.1/§8.2,
PHASED-SCHEDULE D1–D20 + §5b fidelity audit + friction ledger,
PAYLOAD-REWORK-PLAN, the kiss validation-boundary ruling
(.claude/memories/holo-v1-kiss-branch.md).

Standing constraints that bind everything here:

- **Every D1–D20 semantic is preserved.** Rung-major drive, per-capture
  plan-prefix law with its three enforcement points (§5b: barrier ordinal
  derived at session.validate_barrier, runtime.run_lane, runtime.commit),
  multi-ACTIVE resume duty, close preemption, flag bounds, evidence-lane
  split, the authority rule (§8: scheduler receives the capture prefix and
  a runtime-owned barrier callback, returns nothing; cursor derived, never
  stored). Nothing below proposes weakening any of them.
- The kiss validation-boundary ruling governs every duplicate-check finding
  (trust boundaries + measured-doctrine guards only; interior verification
  = types + tests; durable-record walls stay). The mint-once ruling governs
  every identity-recompute finding ("recomputation on unchanged content:
  never").
- The frontier scheduler is parked TOP-DOWN work; nothing here reopens
  scheduling policy. The payload stage (everything behind the processors)
  was audited separately (PAYLOAD-IMPROVEMENTS) and is not re-read here.
- Waste items must be exact-preserving with a fixture or A/B, per the
  hoist precedent; hot-path pruning only after harness measurement.

## 1. The shape census (user question: "how many context/product/record
shapes exist between raster-in and barrier-committed?")

Transient, on the exact-session path, in causal order:

| # | Shape | Home | Role |
|---|---|---|---|
| 1 | `CaptureInput` | types.py:216 | request row |
| 2 | `Raster` (+`RasterSource`) | scan.py | authenticated native view |
| 3 | `CaptureFacts` | session_model.py:187 | identity quintuple |
| 4 | `_CaptureSlot` | runtime.py:268 | invocation slot (raster+plan+bound) |
| 5 | `LaneSpec` | types.py:236 | plan entry (durable vocabulary) |
| 6 | `ScheduleContext` | runtime_model.py:311 | scheduler seam (4 callables) |
| 7 | `ScaleSchedule`/`ScaleLevel` | scale_space | scheduler-side geometry |
| 8 | `ScaleRaster`/`ColorScaleRaster`/`LazyDerivedRaster` | cascade.py | lane raster views |
| 9 | `LaneRequest` | runtime_model.py:70 | (lane, raster) pair |
| 10 | `EvidenceContext` | evidence_context.py:23 | durable rows for one lane |
| 11 | `LaneContext` | runtime_model.py:74 | stage seam (4 callables + transforms) |
| 12 | `LaneStageOutput` | runtime_model.py:137 | decision + product |
| 13 | `SurveyProduct`/`AddressProduct`/`PayloadProduct` | types.py:724+ | artifact + rows + transient |
| 14 | `LaneExecution` | runtime_model.py:202 | stage triple carrier |

then the durable seam: `LevelRecord` + `BarrierDelta` (session_model.py:93,
207) minted by `LaneExecution.durable()` (runtime_model.py:233-256),
committed into `CaptureRecord`/`SessionState` under a transient
`SessionIndex` (session.py:95), reported as `CaptureRun`/`ReceiveResult`.
Close adds `CloseContext`/`CloseExecution`/`CloseRecord`/`CloseProgress`.
Discovery wraps the whole thing again (`DiscoveryReceiveRequest/Result`,
`DiscoveryState`, `DiscoverySurvey`).

Verdicts:

- **Most shapes earn their keep.** The durable/transient split is doctrine
  (§8); products→(LevelRecord, BarrierDelta) is the one projection that
  strips stage transients before the barrier — that is its value, keep it.
  `LaneContext` and the processor protocols have six direct stage-level
  test constructors (test_mint_once_payload.py:349,
  test_receive_production_color.py:226, test_close_schedule.py:349,
  test_receive_color_refine.py:382, test_receive_production_policy.py:42,
  test_receive_refine_lane.py:182) — a real API, not ceremony.
- **1.1 (minor) Capture identity is copied across four shapes and compared
  field-wise in three places.** The quintuple (sha, dpi, dtype, shape,
  channels) lives in `RasterSource`→`CaptureFacts` (runtime.py:139-144
  `_facts`) →`CaptureRecord` (session_model.py:199-203 `as_record`), and is
  compared field-by-field in `_metadata_matches` (runtime.py:147-152),
  `_bind_facts` (session.py:546-552), and discovery_state.py:220-232 —
  three hand-rolled comparators for one concept. `_facts` itself is
  duplicated verbatim (runtime.py:139-144 vs discovery.py:328-336).
- **1.2 (minor) `LaneRequest` is a two-field pair** whose only production
  consumer immediately isinstance-checks and unpacks it
  (_runtime_validation.py:32-35). It exists as the scheduler→runtime
  plugin-boundary token; whether that token earns a shape is a ruling call
  (§12.4).
- **1.3 (note) `LaneExecution` has exactly one consumer** of its product
  fields: `durable()` at the single scheduler call site (cascade.py:566).
  It is the refusal-prefix validator (runtime_model.py:208-227), which is
  real; the shape could still merge with `durable()`'s output if the
  scheduler seam slims (§5).

## 2. One wall per check — the commit-path duplicate validation family
(major; the direct answer to "which validation happens twice across the
runtime/session seam")

Every barrier commit runs TWO validation stacks over the same delta along
ONE call path (`commit` closure → `append_level_barrier` →
`SessionIndex.validate_barrier`):

- **2.1 Page domain ×2.** runtime.py:579-580
  (`_validate_page_domain_records(delta, …)`) then session.py:314-324 (the
  delta page loop over the same six row groups). BCH-conflict domain ×2:
  runtime.py:581-582 vs session.py:325-329.
- **2.2 Attempt identity ×2.** runtime.py:584 → `_validate_attempts` →
  `validate_attempt_record_identity` (_runtime_validation.py:87) per
  attempt; then session.py:384-385 → `_validate_stream_record`
  (session.py:170-171) → the same `validate_attempt_record_identity`.
- **2.3 Certificate identity ×2 — a digest recompute both times.**
  runtime.py:585 → `validate_certificates` (_runtime_validation.py:59-62)
  → `validate_certificate_record` (records.py:141-158, which recomputes
  `stream_certificate_identity` — the content-addressed id); then
  session.py:480-481 → `_validate_stream_record` → the same function.
  Under the mint-once ruling ("recomputation on unchanged content:
  never") this is the exact pattern phase 3.1 deleted from the payload
  stage; the runtime/session seam evidently survived the 9.4-GO-WIDENED
  sweep.
- **2.4 Plan equality ×2.** cascade.py:523-524 (`existing.plan != plan` in
  the scheduler) and session.py:279-280 (`existing.plan != plan` →
  `CaptureConflictError` in `validate_barrier`).
- **2.5 The asymmetry that shows the missing law.** Blocks are
  format-bound ONLY on the runtime side (runtime.py:583 →
  `validate_blocks_for_spec`, incl. the per-block
  `format_reference_values` reconstruction); attempts/certificates are
  format-bound on BOTH sides; graph/ownership/supersession checks live
  only on the session side. There is no stated rule for which seam owns
  which check — the duplicates are the residue of not having one.

RESOLUTION SHAPE (ruling §12.1): state the wall law once — the
`SessionIndex` delta validation is the durable-boundary wall and owns
graph + format binding for everything crossing the barrier; the runtime's
four pre-checks (runtime.py:579-585) either move wholly into it (blocks'
format binding joins the session side) or are deleted as interior
duplicates. One check per fact per barrier. Kiss measurement context:
validation was ~4-5% of a real decode (kiss memory), and the phased plan
doubled barrier count — worth one wall, not two.

## 3. Load/resume validates everything twice (major)

An exact-session resume from a state file runs the full-state validation
stack twice and builds two `SessionIndex`es:

- `load_session(_with_digest)` → `validate_session` (session.py:646-687):
  `SessionIndex(state, validate=True)` (structural pass incl. per-
  certificate `_validate_stream_record`, session.py:214-215) plus
  `validate_state_for_spec` (session.py:662-664; certificates again at
  _runtime_validation.py:259).
- Then `_execute_receive` runs `_validate_state_for_spec(state, spec)`
  AGAIN (runtime.py:463) and builds a SECOND index
  (`SessionIndex(state, …, validate=False)`, runtime.py:464).

Net on one resume: full format pass ×2, certificate identity ×3 (once
structural, twice format), `SessionIndex` construction ×2, and
`validate_state_for_spec`'s per-capture `scale_plan` + `ScaleSchedule.auto`
re-derivation ×2 (_runtime_validation.py:240-243). Discovery multiplies
it: `validate_discovery` already ran `validate_session` per branch at root
load (discovery_state.py:198-202), then every branch drive repeats the
runtime pair (runtime.py:463-464 per `_execute_receive` call,
discovery.py:791). The load wall is doctrine and stays; the second and
third passes are interior duplicates along a single call path.
RESOLUTION SHAPE (ruling §12.2): the loader returns its validated index
(or `_execute_receive` trusts the validated state and builds only the
index); exactly one full pass at the durable boundary.

## 4. Discovery re-opens and re-hashes every source per branch (major,
waste; doc-vs-code against D10)

`open_capture` streams a full SHA-256 at every open (scan.py:343-377,
`_sha256_file` at :355). One discovery invocation over B branches opens
each capture: once to authenticate (`_capture_facts`, discovery.py:339-346),
once to survey on first sight (`_survey_capture`, discovery.py:349-357),
and once PER BRANCH DRIVE (`_execute_receive` → runtime.py:498), i.e.
2+B hashes per capture instead of one. Measured anchor: one hash of a
6.8 GB scrap TIFF costs ~19.1 s (PHASED-SCHEDULE §5a-bis); a 3-branch
discovery resume pays ~95 s per capture in pure re-hashing. D10 says
"native rasters are opened once per invocation and held across phases" —
the exact-session driver honors it (`_CaptureSlot.raster`); the discovery
driver predates the phrasing and violates its spirit (each branch's slot
opens its own). The v0.37 stat-memo does not help: it accelerates
re-authentication on an already-open `Raster`, not fresh opens.
RESOLUTION SHAPE (ruling §12.3): one authenticated `Raster` per source per
discovery invocation, shared across branch drives (pass rasters or a
source→Raster pool into `_execute_receive`; the derived-lane pool already
keys off the native raster object, so sharing also lets branches of equal
geometry reuse derivations). Exact-preserving; A/B gate in §13.1.

## 5. The scheduler seam after D1 (moderate)

D1 moved iteration into the runtime; what remains behind the
`MultiresScheduler` protocol is a one-level executor
(`PhasedSessionScheduler.process`, cascade.py:518-574, ~57 lines) with one
production implementation and one fixture stub
(_qualify_runtime_fixtures.py:421). The protocol itself earns its keep
(the stub-driven runtime tests and the §8 authority firewall are real);
the shapes around it carry avoidable weight:

- **5.1 The scheduler re-derives the plan every advance.**
  cascade.py:519-521 (`ScaleSchedule.auto` + `_scale_plan`) because
  `ScheduleContext` (runtime_model.py:311-333) does not carry the plan the
  runtime already derived at ingest (runtime.py:530) and holds in the slot
  it builds the context FROM (runtime.py:552-655). The lane the scheduler
  picks is then re-derived twice more inside the same advance (run_lane
  runtime.py:557-561, commit runtime.py:574-578) — those two plus
  session.validate_barrier are the ruled §5b enforcement trio and stay;
  the scheduler-side re-derivation + its plan-equality check
  (cascade.py:523-524) are the fourth and fifth derivations of the same
  fact in one advance. Purity is not at stake — the plan is a pure
  function either way; carrying it in `ScheduleContext` is a cache.
- **5.2 `slot_context(slot)` rebuilds the context and its four closures on
  every advance** (runtime.py:668) — allocation noise, not cost; but it is
  why the scheduler cannot hold anything and must re-derive.
- **5.3 The no-op snapshot stub.** `_scale_diagnostic_snapshot`
  (cascade.py:38-45) is a kept no-op fed to a `snapshot_factory`
  (cascade.py:533-534) — dead diagnostic residue ("no dead code").

## 6. Per-barrier O(state) rebuilds (measure-first; no ruling requested yet)

- `SessionIndex.accept` rebuilds the capture map, the quarantine index
  (over every level of every capture, session.py:76-92), the block and
  parked maps, and the derived frontier/certificate indexes
  (`merge_block_sets` + `certificate_work_index`) at EVERY barrier
  (session.py:527-543); `append_level_barrier` separately rebuilds
  `live_blocks` and the certified set over all state certificates
  (session.py:574-586). The growth audit already trimmed one such member
  (the divergence index, session.py:142-147 comment); the rest are
  candidates only after a decomposition measurement — the phased plan
  doubled barrier count, so the constant matters more than it did.
- Discovery re-encodes and re-hashes the ENTIRE root state (all branches)
  at every branch barrier (`persist_child` → `persist_root` →
  `save_discovery_with_digest`, discovery.py:780-789, 458-480). States are
  compact by design; still O(all branches) JSON per barrier — measure
  before touching.

## 7. Driver structure (minor; readability, not semantics)

The two drivers are closure nests: `_execute_receive` is 425 lines
(runtime.py:429-854) with the barrier transaction as a ~80-line `commit`
closure inside `slot_context` (runtime.py:570-650); `run_discovery_receive`
is 433 lines (discovery.py:420-853) with seven nested closures, `state`
rebound through a `nonlocal` in `persist_root` (discovery.py:458-480) and
read back by a stop lambda (discovery.py:798-800). The phase driver core
itself is genuinely ~30 lines (rungs loop runtime.py:696-712 + EV tail
:714-726) — the user's instinct that staging/multi-lane/mop-up is
"conceptually simple" is confirmed by the code; the bulk is ingest
bookkeeping, the persist triple, and event emission. Named shapes for the
barrier transaction and the persist policy would shrink both files without
touching semantics; this is the same judgment call as 9.1 was for
production.py (ruled GO there).

## 8. Trivia batch (minor; one sweep, suite-green gated — the 9.6 mold)

- `_facts` duplicated verbatim (runtime.py:139-144, discovery.py:328-336);
  three field-wise capture-facts comparators (§1.1).
- `_load_or_create`'s defer fork duplicates the call with/without one
  kwarg (runtime.py:117-129); same fork shape in discovery load
  (discovery.py:427-435). `defer_fountain_validation=request.…` collapses
  each to one call.
- The three-way persist branch (`persist_state` / `state_path` /
  digest-only) is duplicated between `commit` (runtime.py:625-632) and
  `_finalize_deferred_close` (runtime.py:336-343).
- `close_progress_sink` is a mutable list-of-one-callable threaded through
  four sites (runtime.py:484, 318-319, 608, 826, 852-853) — a cell hack
  standing in for a return value.
- `ScaleRaster`/`ColorScaleRaster` are ~90-line mirror twins
  (cascade.py:48-137 vs 140-229: identical validation, `contains`,
  `crop_native`, `_release`; only ndim checks and `crop_luma` differ),
  with a THIRD copy of `contains` in `LazyDerivedRaster`
  (cascade.py:459-465). Same mold as the ruled BlockStatus/
  CloseBlockProgress merge (9.3-GO).
- `_scale_diagnostic_snapshot` no-op (§5.3).
- `label_poses: tuple = ()` is a bare-tuple annotation on the otherwise
  fully-typed `EvidenceContext` (evidence_context.py:39; should be
  `tuple[PoseRecord, ...]`) — ducktyping-sweep residue.
- The `"region-"` id-suffix parse (`rsplit("region-", 1)`) exists at four
  sites (place.py mopup_survey/place_mopup labels/place_refine
  ~633/695/808, production.py:257-261) — one helper owns the convention.

## 9. File-size and vocabulary notes

- **place.py is 1712 lines** against the ≤1000 CLAUDE.md rule —
  pre-existing, address-stage (adjacent scope; the 9.1 split ruling
  covered production.py/_payload_windows.py only). Flagged for the
  placement owner; natural seams exist (mop-up/refine drives vs the
  E022 engine).
- runtime.py at 904 is near the limit and would cross it if §12.1 moves
  checks INTO it — another reason the wall belongs on the session side.
- types.py (893) mixes the durable-record vocabulary with the
  observer/event vocabulary (`RuntimeEvent`/`EventContext`/`Detail`,
  types.py:115-194) — note only; a split is not requested.

## 10. What a minimal wiring would look like (rebuilt today, semantics
identical)

Answering the review question directly; every D1–D20 semantic and all
three §5b enforcement points survive:

1. **Ingest**: one authenticated `Raster` per source per invocation,
   shared with discovery branches (§4); `CaptureFacts` gains the one
   comparator everything uses (§1.1).
2. **Slot/scheduler seam**: `ScheduleContext` carries the slot's plan (the
   scheduler keeps its `CaptureRecord.plan` conflict check as the durable
   wall and stops re-deriving, §5.1); `LaneRequest` folds into
   `run_lane(lane, raster, evidence)` or stays as the plugin token
   (ruling); the protocol layer stays.
3. **Stages**: unchanged (`LaneContext`, products, `LaneStageOutput` are
   earning their keep; six test files construct them directly).
4. **Barrier**: ONE wall — `SessionIndex.validate_barrier` owns graph AND
   format binding; the runtime's pre-check block (runtime.py:579-585) is
   deleted; blocks' format binding moves into the wall (§2.5). The
   commit transaction becomes a named object shared by the barrier and
   deferred-close paths, absorbing the persist triple and the
   close-progress cell (§7, §8).
5. **Load**: the loader's validated pass is THE pass; `_execute_receive`
   receives (state, digest, index) and validates nothing it did not
   change (§3).
6. **Estimate**: net −300 to −500 lines across runtime/session/discovery/
   cascade, two fewer shape-hops per barrier, one fewer full-state pass
   per resume, and (with §4) B−1 fewer 19-second hashes per capture per
   discovery resume — with zero schema, policy-id, or golden movement.

## 11. Explicitly NOT reopened

D1–D20 and the §5b fidelity deviations (all deliberate, recorded); the
friction-ledger resolutions; the pool law (§8.2 L1–L6); the D8 close-gate
placement inside ProductionClose (ruled = document, v0.36); the D15
discovery-epilogue gap (recorded as shipped); the frontier scheduler
(parked top-down); characterize-trio trim (user-word gated); the
validation-boundary doctrine itself; every payload-stage family
(PAYLOAD-IMPROVEMENTS §1–§10); the M-level diagnostics fix trio
(`316572f`/`9a7046d`/`d81999d`, this session — A1 closed).

## 12. Adjudication requests (rulings needed before any fix)

1. **The wall law** (§2): one owner per check at the barrier — proposal:
   the SessionIndex delta wall owns graph + format; the runtime pre-check
   block is deleted; blocks' format binding moves session-side. Decides
   2.1-2.5.
2. **Load single-pass** (§3): loader hands its validated index to the
   runtime; delete the second `validate_state_for_spec` + second index
   build. (Discovery branches inherit the same rule.)
3. **Discovery raster pool** (§4): one open+hash per source per
   invocation, shared across branches; D10 wording extended to discovery.
   Gate: §13.1 A/B.
4. **Scheduler seam shapes** (§5): plan into `ScheduleContext`; keep the
   protocol; `LaneRequest` inline vs keep as token; delete the no-op
   snapshot stub.
5. **Trivia batch GO** (§8) incl. the ScaleRaster-twins merge and the
   `label_poses` typing fix.
6. **Driver structure** (§7): named barrier-transaction/persist shapes for
   runtime.py + discovery.py (the 9.1 precedent applied to the drivers) —
   or ruled as acceptable as-is.
7. **place.py 1712 lines** (§9): assign to the placement track (split
   ruling there), or accept an exemption row.

## 13. Measure-first gates (before building)

1. **Discovery open-count A/B** (§4): count `open_capture` calls and wall
   per branch on the real corpus (instrumented single run, never pytest);
   expected: 2+B → 1 hash per capture, −(B+1)×19 s per 6.8 GB capture.
2. **Barrier decomposition** (§6): per-barrier `SessionIndex.accept` +
   `append_level_barrier` + root re-encode seconds on the real-corpus
   fixture before touching any rebuild.
3. **Validation share re-measure** (§2/§3): re-run the kiss 4-5%
   validation-share measurement after the wall law lands, same harness,
   to record the reclaimed share (expected: roughly half of it).
