# 13 — Orchestration + diag + CLI (engine.py, diag/, cli.py)

Distilled from: holo2/src/holo2/engine/{orchestrator,recipe,replay,observe,worklist}.py,
holo2/src/holo2/cli.py, holo2/src/holo2/diag/{status.py,panes/*},
src/holo/receive/{runtime,production,cascade,close_progress}.py,
src/holo/cli.py, src/holo/receive/diag/*.

## 1. Purpose + inputs/outputs

Purpose: drive one multi-capture decode from scan files to verified payload,
with a live observer that never touches the run. Three deliverables:
`src/holo/receiver/engine.py` (frontier loop + merge + accounting), `src/holo/receiver/diag/`
(event-fed A–D panes + six-row status + stdlib HTTP viewer), `src/holo/receiver/cli.py`
(decode only).

Inputs (CLI):
- `SCAN...` positional paths (TIFF/PNG; any count >= 1).
- `--dpi FLOAT` repeated, one per scan, operator-declared TRUE dpi. Never
  guessed, never defaulted (misdeclared-dpi incident e033: survey said c4,
  spec said c2 — clean refusal is the required behaviour).
- Format identity, exactly one route:
  `--format ID` (v2 id `c2-cmy8-r0700@53x37` or fossil `L:c2-r0700@3392x2368`),
  or legacy `--coding ID --printer ID` (needed for e029's probe-row geometry
  `c2-r0700` + `hp-m281-ink`, deliberately absent from FORMAT_ROWS).
- `--pages N` (int, default 1), `--out FILE` (required; refused if exists),
  `--workers N` (int, default 1), `--refine` (bool), `--no-close` (bool),
  `--complete` (bool), `--diag PORT` (int; absent = no viewer),
  `--run-dir DIR` (scratch cache; default under tempfile; disposable).

Outputs:
- Payload bytes written atomically to `--out`; sha256 hex printed.
- Exit 0 = VERIFIED, 2 = open/not recovered, 1 = error/refusal.
- stderr: format line, six-row status block, per-plugin accounting table.
- With `--diag PORT`: `http://127.0.0.1:PORT/` (shell), `/status` (JSON),
  `/frame/<page>.png` (one composed frame per page, 4 panes).

Engine API (library path, what cli.py calls):
`decode(request: DecodeRequest, plugins: tuple[Plugin, ...], events: EventLog)
-> RunResult` where RunResult = {status: str, payload: bytes|None,
sha256: str|None, certified: int, plugin_rows: tuple[PluginRow, ...]}.

## 2. Algorithm

### 2a. The measured pass structure of BOTH trees (what holo3 must reproduce)

holo1 (src/holo — the only tree that ever closed colour; runtime.py:441-884,
cascade.py:611-712):
1. Resolve FormatSpec (--format resolver total over L:/legacy/catalog/v2;
   or state's own id — holo3 drops the state route). Build pipeline:
   Survey, Address, Payload (K or Color by Family), PhasedScheduler, Close.
2. Open every capture (sha256, facts: dpi/dtype/shape/channels); duplicate
   sha = skip; conflicting metadata for same sha = refuse.
3. Per capture build the scale plan (cascade.scale_plan): ordinary L-levels
   = the ppc ladder coarse->fine (auto rungs; c3@4800 lays 2/4/8/12/24
   px/cell, c2@4800 five rungs), then M (mop-up) levels one per base lane,
   then R (refine) levels, then for colour the supplemental U tail
   (arms off/a3/a4b, +field when dialed; a3/a4b coding-aware — a4b only
   with sibling streams). Flag bound (runtime.py:247-276): default stops
   before the first M; `--mopup` through M; `--refine` = whole plan.
4. Phase driver (runtime.py:696-756): RUNG-MAJOR — for each ordinary rung
   ppc ascending (coarsest first), advance every capture one level at that
   rung; then the TAIL loop: repeatedly advance the max-EV pending slot,
   EV = (lane_class, parked_support_weight, -position) with class
   M=1 > R=0 > U=-1, i.e. all mop-ups session-wide, then all refines
   (each R sees the maximal certificate frontier), then u-lanes (they read
   the residue, so last). Mop-up weight = sum of parked support_cells.
5. One level = one scheduler.process: `level.open` event; materialize the
   derived lane raster (exact area-decimation of native, pooled per
   invocation, LAZY for M/R/U — an ineligible level never reads pixels);
   build the evidence context (committed poses/proposals/losers/parked/
   certificates from ALL prior levels and captures); run the 3-stage lane
   SURVEY -> ADDRESS -> PAYLOAD, any stage may REFUSE (level retained as
   refused, ladder proceeds finer); commit ONE atomic barrier (validate
   delta, append level, per-barrier close.check unless deferred, save
   state + digest). Payload stage internal order (production_payload):
   plan -> sample -> calibrate (ctx+PAVA) -> one-owner freeze ->
   blocks -> scan attempts (max60 BP) -> union with prior calibrated
   evidence -> count-gated preclose -> selective retry150 -> complete.
6. Close: per-barrier count-gated check (close_count_ready = counting
   projection; full GF(2) solve only when reach makes terminal possible);
   `--complete` defers the ONE close to bounded exhaustion; `--no-close`
   never enters the close layer (and detaches a terminal state — resume
   concept, drop). VERIFIED = payload sha matches envelope; stop.

holo2 (engine/ — K only, journal-authoritative; orchestrator.py): one
cost-ordered fixpoint instead of phases. Recipe v1 order: ingest(10) ->
calibration(15) -> payload(20+lane) -> placement tiers (pull source) ->
refine(200) -> close consult (preempts everything). Every commit wakes
subscribers; spend-once identity + staleness re-derivation make pooled
commits safe; `--workers 1` deterministic. Placement tiers: ring 40,
word-centre 60, word-rest 80, wide 120, cold-live 140, cold-rest 150;
lane premium 2/rung, cold rung term 20/rung, child premium 5; gated tiers
(wide/cold) admitted only when nothing cheaper is ready OR in flight
anywhere. Re-work aging: re-attempt price = max(base, 90+5*(n-1))+premium.

### 2b. The holo3 engine loop (the lean synthesis — numbered, buildable)

State (all main-thread-owned): `frontier` = min-heap of
(cost:int, seq:int, plugin:str, subject:Subject); `inflight`:
dict[Future, (plugin, subject, cost)]; `tried`: dict[(plugin, subject) ->
facts_version:int]; `attempts`: dict[(plugin, subject) -> int];
`facts_version`: dict[Subject -> int]; the Facts store (poses, words,
certificates, calibration, metadata, fountain counters); `events` list.

1. Intake: for each (scan, dpi) convert once to per-plane u8 `.npy` in the
   run dir; sha256 the source; duplicate sha = drop with `capture.open`
   noting duplicate. One capture = one dpi = one ladder of footings
   (the e023b law: one ordinary state freezes one DPI; NEVER enqueue a raw
   scan and its own decimation as two captures).
2. Seed the frontier: per capture push survey (tier SURVEY=10); after
   survey facts land, the merge pushes per-region calibrate (15), per
   window-and-footing place jobs at their tier, per addressed-tile payload
   jobs (20 + 2*footing_depth), refine subjects (200). Cost table
   (copy holo2's re-spaced scale verbatim, they are ratified orders):
   INGEST/SURVEY 10, CALIBRATE 15, PAYLOAD 20, PLACE_RING 40,
   PLACE_WORD_CENTRE 60, PLACE_WORD_REST 80, PLACE_WIDE 120,
   COLD_LIVE 140, COLD_REST 150; LANE_COST_PER_RUNG 2, COLD_COST_PER_RUNG
   20, CHILD_PREMIUM 5, REWORK_BASE 90, REWORK_STEP 5, REFINE 200.
   price(first) = tier + premium; price(re-attempt n>=1) =
   max(tier, 90 + 5*(n-1)) + premium. Coarse rungs first WITHIN a tier via
   the lane premium; ALL rungs place and decode (H4-LANES: coarse lanes are
   extra decoding trajectories — measured coarse-cert share 27–92%, e029's
   coarse lane alone could not close).
3. Loop (ThreadPoolExecutor, max_workers=N; N=1 runs the same code path):
   a. FILL: while len(inflight) < N: peek cheapest head. PAGE-DOMAIN
      2026-09-01: the cost>=120 dryness gate is DELETED; an idle worker
      takes the cheapest ready job. Cold is last by price (250/260).
      (Was: GATING — a job with cost >= 120 admitted only if no cheaper
      job is ready or in flight.)
      TRIED-SET FLOOR: skip (pop, count idle) if
      tried.get((plugin,subject)) == facts_version[subject] — the job
      would read exactly what it already read. Otherwise record
      tried[(plugin,subject)] = facts_version[subject], attempts += 1,
      submit `plugin.run(snapshot, subject)` where snapshot = immutable
      refs (plane mmaps, frozen pose/calibration/certificate views).
   b. WAIT for FIRST_COMPLETED; MERGE on the main thread: fold the job's
      Facts (certificates, poses, words, metadata equations, fountain
      symbols, calibration sufficient-statistics reductions) into the
      store; append its events; add its PluginRow deltas (jobs+1,
      cpu_seconds += result.cpu_s, certificates += n_new). Certificates
      are commutative facts — payload identical for any worker count.
   c. WAKE: for every subject whose consumable facts changed (window
      neighbours of a new pose, tiles under a revised pose, region pool of
      a new label, residue of a new certificate), bump
      facts_version[subject] and push (plugin, subject) at its CURRENT
      price (re-work ordinal from `attempts`). Nothing is ever refused —
      hopeless keys just get dearer (L7; the OR-5 lesson: 61 BP re-runs on
      one key — cap rejected, price instead; the 256-fires tripwire is
      dropped, the growing band bounds churn by construction).
   d. CLOSE CONSULT (skip under --no-close; defer to exhaustion under
      --complete): after each merge that added certificates, if the count
      gate passes (every fountain block's have >= needed AND metadata
      trusted: rank 24/24 from >= 48 distinct certified equations), run
      the full solve. VERIFIED -> cancel pending futures (close preemption
      = the biggest scheduling win, 3.7x measured), let started jobs
      finish unread, return. Cheap counting progress (K, per-block
      have/needed, metadata rank) is refreshed for the observer on every
      consult either way.
   e. Exhaustion: frontier empty and nothing in flight -> one final close
      attempt (observation only under --no-close) -> return OPEN or
      VERIFIED.
4. `--refine` gates the refine plugin and every dial-off arm (u-lanes,
   plane_fields, color_field) exactly as holo1's plan-prefix law: without
   it those subjects are never seeded. Refine eligibility stays two-sided
   (e024): certified material in reach AND uncertified residue in reach.
5. CLI epilogue: print six rows, plugin table, then on VERIFIED write the
   payload atomically (tempfile + flush + fsync + os.link no-overwrite +
   parent-dir fsync — copy holo1's block), print
   `VERIFIED <n> bytes sha256 <hex> -> <out>`.

### 2c. Diag (event-consumer only; never reads engine state)

Event flow: merge thread appends frozen event dataclasses to a plain list;
diag holds an integer cursor and folds `events[cursor:len]` into its
accumulators on demand (append-only list + monotone cursor is
thread-correct under free-threading without locks). A failure anywhere in
diag is swallowed to one stderr line; it can never change payload or exit
code (L12).

LEAN EVENT LIST (name -> payload fields; all frozen dataclasses in data.py):
- `run.open` — format_id:str, pages:int, tiles_yx:(int,int),
  stream_ids:tuple[str,...], n_captures:int, workers:int
- `capture.open` — capture:str(sha12), dpi:float, shape_yx:(int,int),
  channels:int, duplicate:bool
- `survey.done` — capture, n_regions:int, regions:tuple[RegionMark,...]
  (region_id, origin_yx, shape_cells, pitch_px, support_cells),
  preview:np.ndarray|None (block-mean grey, <=512 px long side), decim:int
- `pose.committed` — capture, footing_id:str, region_id:str,
  extent_cells:(4 ints), page:int, route:str("word"|"chain"|"cold"),
  mismatch:float, accepted:bool
- `window.settled` — capture, footing_id, region_id, extent_cells,
  state:str("posed"|"retired"|"parked"|"done")
- `calibrate.adopted` — capture, pool_id:str, classes:int, floors_met:bool
- `tile.outcome` — page:int, ty:int, tx:int, stream:str, source:str
  (producing plugin — the certificate source tag), result:str
  ("certified"|"failed"|"floor"), bp_iters:int
- `job.done` — plugin:str, subject:str, cost:int, cpu_s:float,
  n_certificates:int, n_poses:int, n_words:int
- `close.check` — certified:int, symbols_used:int, k_total:int|None,
  metadata_rank:int, metadata_counters:int,
  blocks:tuple[CloseBlock,...] (stream_id|None, block, have, needed,
  rank, solved), status:str
- `run.done` — status:str, payload_sha256:str|None, bytes:int|None,
  certified:int

PANE MAPPING (one composed PNG frame per page, four panes in a row under
fixed headings — the v1 §10.3.1 shape both trees kept):
- A CAPTURE (scan space): survey regions tinted by hue over the decimated
  underlay (1/99 percentile stretch, then 0.55+0.45*clip toward white so
  overlays stay legible); support edge in BLUE; window rectangles from
  `window.settled` (pending grey outline, posed GREEN, retired ORANGE,
  parked amber solid (210,130,35), done CYAN dashed — paint order
  retired<posed<done so the strongest claim wins on overlap); fed by
  capture.open + survey.done + pose.committed + window.settled.
- B PAGE (tile map): per work key one box split into per-stream segments,
  chips UNKNOWN=bg / ADDRESSED=pale blue / ATTEMPTED=amber /
  CERTIFIED=green, evidence count printed (min(count,999)); fed by
  pose.committed (addressed reach) + tile.outcome. This absorbs holo1's
  pane C word map: a word-solved tile is ADDRESSED, its conflicts a red
  chip note.
- C ENGINE: frontier depth by tier band, in-flight, tried/idle counts,
  and THE PER-PLUGIN ACCOUNTING ROWS (plugin | jobs | cpu_s | certs |
  poses | words) as bars scaled to the block max; fed by job.done. This is
  holo2's pane C re-aimed at the toolbox doctrine (per-tool accounting,
  one certificate pays).
- D CLOSE: verified phrase / close status, certified count, K
  symbols_used/k_total, metadata rank m/24, per (stream,block) bar
  have/needed with rank, GREEN when solved; fed by close.check + run.done.

SIX-ROW STATUS BLOCK (fixed shape; a value becoming known must not move a
row; NEVER print zero where the fact is unavailable — say
"unavailable before survey"):
1. `format   <id> · <ty>x<tx> tiles · <n> pages · streams C,M,Y · PROVISIONAL`
2. `capture  <n> ingested · <sha12>… · regions <n> · support <cells>`
3. `frontier ready <n> [by tier] · in flight <n> · tried <n> · workers <n>`
4. `work     jobs <n> · cpu <s> · certs by plugin [p:<n>,...]`
5. `tiles    UNKNOWN n · ADDRESSED n · ATTEMPTED n · CERTIFIED n`
6. `close    <status> · K <used>/<total> · metadata rank <m>/24 · blocks <s>/<n>`

HTTP viewer (stdlib, daemon thread, loopback only): routes `/` (static
shell polling /status 1/s and refetching the frame when `revision` moved),
`/status` (JSON: rows, revision=len(events), catalog, plugin rows),
`/frame/<page>.png` (composed on demand, cached keyed by (page,
revision)). Host-header check against {127.0.0.1, localhost, [::1]}
(DNS-rebinding refusal); `Cache-Control: no-store`; HTTP/1.0;
port-in-use -> one stderr line, run unaffected. Pane geometry: pane
width 520, height = clamp(width*ty/tx, 0.5w, 2w); title bar
max(18, clamp(9..15, round(w*0.032))+9). At run end compose+pin the final
frame of every posed page BEFORE the server stops, and write
`report.json` + final frames into the run dir.

## 3. Copy-vs-rewrite table

COPY-AND-STRIP (hard-won numerics / careful mechanics; strip comments,
guards, compat):
- holo2/src/holo2/engine/recipe.py:177-291,376-420 — the cost scale
  constants + `work_price` (values verbatim; ratified orders).
- holo2/src/holo2/diag/panes/paint.py:1-293 — palette, Pane/TileGrid
  drawing primitives, `compose`, `mask_edge`, `resize_mask`.
- holo2/src/holo2/diag/panes/render.py:59-77,150-185 — TILE_CHIPS map,
  `pane_size` clamp math, underlay canvas + 1/99 stretch.
- holo2/src/holo2/diag/status.py:394-517,578-589 — `_Handler`/
  `DiagServer`/`serve` HTTP skeleton (loopback allowlist, no-store,
  respond plumbing).
- src/holo/cli.py:697-728 — atomic no-overwrite payload publication
  (tempfile+fsync+link+dir-fsync).
- src/holo/receive/production.py:75-97 — `_survey_preview` block-mean
  strip decimation (bounded RAM; feeds pane A's underlay event).
- src/holo/receive/close_progress.py:12-44,70-119 — CloseBlockProgress /
  CloseProgress field shapes (data.py types; drop validators).
- src/holo/receive/diag/presentation.py:19-46 — operator palette +
  12-hue table + word erasure budget 26 (display classification).

REWRITE LEAN (shape reference only):
- holo2 orchestrator.py (966 ln) -> the ~150-line loop of §2b (fill/
  admit/merge/wake/consult; no identity, no spends, no wall).
- holo2/status.py:300-391 + src/holo/receive/diag/rows.py — six-row block
  (new merged row set above).
- holo2/panes/model.py — pane model becomes event-fed accumulators (no
  store index, no plane binding, no duck-typed quack).
- src/holo/receive/runtime.py phase driver -> the frontier seeds + cost
  premiums reproduce rung-major/tail ordering as pricing, not phases.
- src/holo/cli.py argparse decode surface -> the §1 flag set.

## 4. Measured-channel invariants that MUST survive

- One capture = one declared DPI = one footing ladder; never raw +
  decimated of the same capture as two captures (e018/e023b: duplicated
  physical evidence corrupts union statistics).
- Multi-capture union only AFTER per-capture ctx calibration (F1∘F6 law:
  equal-weight combining LOSES to best-single until the ctx detector
  de-correlates print-frozen context bias).
- All rungs decode, coarse first (H4-LANES: cross-lane certificate
  exclusivity is bidirectional; e029's coarse lane alone was 55.4%).
- Payload undercuts every placement tier (2026-08-17 starvation: 2,529
  ready workers, 431 fires, ZERO tiles attempted with payload priced
  above placement — both feedback loops dormant).
- Wide/cold/refine gated behind global dryness — SUPERSEDED PAGE-DOMAIN
  2026-09-01: dryness deleted; cold_live/cold_rest 250/260 (last by
  price); idle worker takes the cheapest ready job.
- Refine after the ladder by PRICE 200, two-sided eligibility (e024:
  refinement pays at the margins or not at all).
- Mop-up class before refine before u-lanes (v0.42: every refine sees the
  maximal certificate frontier; u-lanes read the residue).
- Re-work priced into the unbounded 90+5*(n-1) band, never refused, never
  capped (no-ceilings ruling; OR-5).
- Close preemption on VERIFIED (3.7x); count-gate before any full solve;
  metadata trust = rank 24 from >= 48 distinct certified equations.
- Never print zero where the fact is unavailable (six-row rule).
- Diag failures inert: no diag path may change payload, status, or exit
  code; event payloads are values, panes advisory.
- --dpi operator-declared per scan, no invented defaults (venv/CLI
  hygiene ruling; e033 misdeclared-dpi refusal).

## 5. DROP (aggressive, by name)

holo2 engine: the journal + Store + commit wall (CommitBatch/Write/
SpendProposal/Subscription/spend-once ledger), read-set attempt identity +
staleness re-derivation (`_is_current`, stale_discards), wakes-by-
subscription (M4), replay.py ENTIRE (audit + crash recovery + markers +
ReplayCursor), snapshot.py's CommitLedger/WorkLedger bookkeeping split,
frontier.py descriptor minting/declines/re-offer, worklist.py, LeaseBook
residency, FireCountTripwire + max_fires_per_worker=256, Recipe/
RecipeEntry/SessionIdentity/POLICY_ID (policy-as-identity — holo3 has no
lineage), RecordRegistry/record-family composition, WorkSource protocol +
PlacementScheduler pull machinery (pings, ready flags, GATED marks —
subsumed by the frontier + tried-set), open_session/SessionContext,
`--state-dir`, resume identity peeks (`_peek*`, `_require_agreement`,
`_declared_pages`), F-12 source-change advisory + baseline stats,
publish_once/EXIT_REFUSED_OUTPUT/EXIT_TERMINAL taxonomy, the
"SUPERSEDED close" stderr choreography, snapshot_every/trace_sample_every.

holo1 runtime: SessionState persistence + digests + load/save +
append_level_barrier + SessionIndex.accept + `_runtime_validation`
(validate_* family), discovery mode ENTIRE (DiscoveryReceiveRequest,
state magics, candidate rows), CaptureStatus/ACTIVE-resume duties,
apply_close/detach_close/`_replay_deferred_close`/verified-resume
reproduction, EventAuthority COMMITTED/TRANSIENT split,
snapshot_factory pass-through machinery + `_diagnostic_snapshots` +
isolate_adapter, per-barrier state fsync, `--mopup` flag (mop-up becomes
ordinary re-priced frontier work), `--source-sha256`, `--profile-timing`
+ TimingObserver (job.done cpu_s subsumes it), `--diag-interval` throttle
+ `--diag-panel-width`, diag/seed.py (resume pane seeding), diag/
field_stats jsonl replay, diag/filesystem.py DirectoryIdentity binding,
transport.py CurrentFiles atomic-replace directory (HTTP + end-of-run
artifacts suffice), the D15/D16 epilogue family (parked inventory,
pending-refinement, mopup-drops prints; keep only the close-shortfall
line and the surplus audit note inside close.check), stage.open/
stage.refused ceremony per lane (one job.done carries the outcome).

## 6. data.py needs (this subsystem)

Consumes: Capture (capture_sha12, dpi_true, shape_yx, channels,
plane_paths: tuple[Path,...]); frozen snapshots handed to jobs (PlaneView
mmaps, Pose/Calibration/Certificate tuples) — defined by the stage specs;
Certificate MUST carry `source: str` (producing plugin/arm) — pane C and
the accounting rows key on it.

Produces/owns:
- Event types of §2c (RunOpen, CaptureOpen, SurveyDone, PoseCommitted,
  WindowSettled, CalibrateAdopted, TileOutcome, JobDone, CloseCheck,
  RunDone) — frozen dataclasses, plain scalars/tuples/np arrays.
- `PluginRow` {plugin:str, jobs:int, cpu_seconds:float, certificates:int,
  poses:int, words:int} — the reduction pane C and the terminal table print.
- `CloseBlock` {stream_id:str|None, block:int, have:int, needed:int,
  rank:int, solved:bool} (K/CMY7 leave stream_id None).
- `RunResult` {status, payload:bytes|None, sha256, certified, plugin_rows}.
- `Job` protocol shape for engine.py: plugin.name:str;
  plugin.run(snapshot, subject) -> JobResult{facts, events, cpu_s}.

Stateful/shared (contract must make these snapshot or reduction):
frontier heap, tried dict, attempts dict, facts_version dict, PluginRow
tallies, close counters — ALL main-thread-only, mutated at merge.
Event list: append-only main thread, cursor-read diag thread. Calibration
evidence: worker-side sufficient statistics (quantized histograms),
merged main thread — never raw per-cell dumps. cpu_s measured inside the
job via time.thread_time() delta (pure, returned as data).

## 7. Pitfalls / incidents

- Payload-starvation (H4, 2026-08-17): pricing placement under payload on
  a large domain gave 0 tiles attempted after 431 fires. Keep payload
  cheapest recovery.
- OR-5 runaway: one key ran 61 BP attempts / 11,820 iterations. A ceiling
  was proposed and REJECTED (narrows the domain); the re-work price band
  is the ruled fix. Do not reintroduce caps (no-ceilings ruling).
- Two counters named "commits" disagreed by the ingest commits in holo2's
  rows (471 vs 472). One owner per number: PluginRow tallies are the only
  job counts; len(events) the only revision.
- holo1 v0.42 replacement_address: e023c may revise pose geometry from
  certificates mid-lane; whatever pass structure holds, a revised pose
  must supersede the generation-zero one in the same merge, or tiles
  decode against stale geometry.
- Diag on the run's thread: v1 measured status publish 0.3-0.5 ms vs
  61-118 ms frame renders — never render on the merge thread; compose
  only on HTTP demand / at end.
- Pane A coordinate frames (RECEIVE-DESIGN v0.47 scars): M/R levels emit
  their BASE lane's pixel coordinates; normalize every geometry event to
  capture-native pixels AT EMISSION (events carry native px), one
  transform in the renderer. Region ordinals were lane-relative — use
  globally unique region_ids in events, never positional indexes.
- Frame revision must be work-counted (len(events)), never wall time —
  a frame per poll re-renders idle sessions.
- Underlay memory: cap preview at <=512 px long side, block-mean in
  strips (production.py:75-97); holo2's alternative pulled multi-GB scans
  for thumbnails and needed a 200M-pixel refusal.
- Duplicate scan paths / same sha twice on the CLI: fold to one capture,
  say so; two DPIs for one sha = refuse.
- Discovery-tier ordering does NOT predict receiver outcome (e032
  inversion): never wire any channel-tier heuristic into scheduling.
- 64 GB machine: one production decode at a time (a 4800 colour decode is
  ~22 GB). No engine-side guard — but the run dir must hold plane .npy
  once, not per worker (mmap views).

## 8. Open questions for the contract author

1. `--complete` semantics without resume: keep as "defer the one close to
   exhaustion" (measurement mode alongside --no-close), or drop and keep
   only default-greedy + --no-close?
2. Post-mortem `events.jsonl` in the run dir (~30 lines to write): keep
   or is the HTTP/report.json surface enough?
3. Diag default: viewer only when `--diag PORT` given (proposed), vs
   holo2's ruled always-on endpoint (2026-08-09) at a default port (8024)?
4. Are the supplemental u-lane arms (off/a3/a4b) load-bearing for the
   acceptance-#6 cmy7 close (686,859 B), or did head+ctx-matrix+demapiter3
   close it alone? Decides whether u-lanes ship behind `--refine` for
   acceptance or stay pure dial-off arms.
5. Pane C = engine/accounting view (proposed, holo2 shape) with word
   states folded into B — or does the operator want holo1's BCH word-site
   map back as a pane? (It was the addressing-debug workhorse on colour.)
6. Confirm adopting holo2's cost numbers verbatim for a tree with no
   descriptors (they are "provisional orders" there); renumbering is free
   now and never again.
7. Wake granularity: per-subject facts_version bumps need a neighbour
   relation (window adjacency, region pools, tile reach). Which stage spec
   owns publishing that relation — place, or a shared geometry module?
8. Arm API: is `--refine` the ONLY dial (holo1 precedent), or do arms get
   a `--arm NAME` repeatable flag for A/B runs (plane_fields, color_field,
   u-lane selection)?
