# PHASED-SCHEDULE — the v0.33 phased session schedule (design + execution plan)

Status: **adopted design (user ruling 2026-07-31), implementation in
progress**. RECEIVE-DESIGN v0.33 is the normative amendment; this document is
the full design record and execution plan, in the DIAG-IMPROVEMENTS.md mold.
Provenance: the 2026-07-31 cold-deferral reopening dialogue (PLACEMENT-
IMPROVEMENTS §1.4b) plus an eight-area verified read of the receiver
(session workflow `phased-schedule-understand`, 8 agents, file:line-pinned;
raw reports preserved in the session transcript).

## 0. Essence

Reorder the receive session from capture-major depth-first to **rung-major
breadth-first with a deferred costly tail**: all captures sweep each ladder
rung together, cheap routes only; all expensive placement work (remaining-slot
word sweeps, cold FFT searches, cold-refusal subdivision) parks durably into
per-capture per-lane **mop-up levels** `M(Lk)` declared in the scale plan and
executed last as a session-wide priced, EV-ordered, close-preemptible tail.
Admission bars, budgets, floors, per-route domains, and rival sets are
UNCHANGED — the amendment moves *when* work runs and lets the verified close
decide *whether the remainder still matters*.

Why (measured anchors): coarse lanes mint 95% of certificates (575/604 fresh
A/B); both qualified sheets closed at the first coarse barrier; one avoided
cold is worth 30–48 s at production page domains but only 1–3 s at one page
(vs a 2.8 s rest sweep — the PLACEMENT-IMPROVEMENTS §3.5 inversion); the
~150 s three-way-residual
is rest-ahead-of-cheap-cold ordering; a verified close is already terminal
mid-ladder (close preemption is existing semantics, maximized not invented).

## 1. Decisions (D1–D21; D1–D19 corrected 2026-07-31 by a four-lens
adversarial review — 16 verified defects folded in, marked "adversarial
review" inline; D20 adjudicated 2026-08-02)

- **D1 Phase driver.** The runtime's capture loop (`_execute_receive`) and
  discovery's per-branch inner loop are replaced by a session phase driver:
  captures advance together through the **ascending union of their ladders'
  target-ppc values** (rung correspondence is by ppc, never ordinal — ladders
  differ across native DPIs), then the mop-up tail runs. The per-capture
  prefix law is untouched; the phase cursor is **derived** from per-capture
  prefix lengths (argmin over plans), never stored.
- **D2 Multi-ACTIVE captures.** The three single-ACTIVE gates (ingest
  `runtime.py:265`, commit `session.py:296`, discovery ordering
  `discovery.py:662/699/731`) are replaced by: any number of ACTIVE captures
  while the session is OPEN; a resume request must include **every** ACTIVE
  capture (supersets fine); new captures may join at any barrier boundary.
- **D3 Plan shape.** `scale_plan(dpi, cell_dots)` stays a pure function and
  now returns `[L0..Ln, M(L0)..M(Ln)]` — one mop-up entry per ladder lane,
  after native, coarse→fine. `LaneSpec` gains `mopup_of: str | None`. The
  linear parent-chain rule is unchanged. M-lane ids `m{index:02d}-…`;
  `validate_lane_request` binds M(Lk) to Lk's exact transform.
- **D4 Evidence-lane split identity.** A level's **evidence lane** is
  `mopup_of or lane_id`. Evidence keying moves to the evidence lane: block
  keys and content addresses, frontier selection, attempt/divergence lane
  binding, quarantine (accumulates by union across the base and mop-up levels
  of one evidence lane). Plan identity, artifact ids, and durable-id
  namespaces stay on the unique plan `lane_id` (no id collisions).
  NORMATIVE COROLLARY (adversarial review): **one evidence lane is one
  patch-ordinal namespace.** A parked window keeps its base-pass ordinal;
  an M-level address run mints new ordinals strictly above the evidence
  lane's durable maximum — derivable as 1 + max over the lane's pose
  `patch_id`s, parked `patch_ordinal`s, and quarantine contributor ids —
  and the barrier refuses an M-level delta whose new ordinals collide with
  the base level's durable ids. Without this rule the quarantine union
  misattributes integers across the two address runs (false evidence
  rejection at the M barrier, retroactive load refusal of valid states).
  CLARIFICATION (2026-08-02): the refusal's collision set is the base
  pass's ACCEPTED and QUARANTINED ordinals only — it binds freshly-minted
  M-level ordinals. A parked window's own ordinal is deliberately NOT in
  that set: its parked row retires at the very same barrier, and its
  re-use is exactly what the first clause mandates. The shipped watermark
  check (session.py) implements this narrow reading; the broad reading
  would forbid the rule's own first clause.
- **D5 Block supersession (extension-only).** An M-level delta may replace a
  live block at its evidence-lane key **iff** the replacement's observed-cell
  set is a strict superset agreeing exactly (mask and values) on every
  previously-observed cell. Committed cells are never revised — mop-up
  contributes only cells absent from the base block. This preserves the
  boundary cells of partially-covered tiles, which a tile-granular
  "previously-unowned only" rule would silently forfeit. STATED DEPARTURE
  (adversarial review): ownership across the base/mop-up split is decided
  by **pass order**, not by one pooled owner competition — committed cells
  stay with their base-pass owner even where the mop-up window's held-out
  logloss would have won a pooled freeze; §6.1's "windows compete, they do
  not sum" binds within one pass. Likewise per-region `ctx-pava-v1`
  calibration pools are per-pass; D7's label re-sampling recovers the
  pooled population at the M-level. (As shipped 2026-08-01,
  RECEIVE-DESIGN v0.35 pool law: certified-complete and zero-payload
  windows also stay in the pooled fit and pitch populations as label
  rows, in every pass — §8.2 L1–L6.)
  AS SHIPPED, MATERIALIZED (d2e5281 + v0.36): a colliding fresh block is
  REWRITTEN into the legal superset rather than merely validated —
  `supersede_with_committed`/`apply_mopup_supersession` carry every
  committed cell over verbatim (bytes, values, origin rows; the base
  owner wins any cell collision), admit only strictly novel cells from
  the fresh block, and emit nothing when nothing is novel — so the
  barrier validator is satisfied by construction. A fresh observation at
  a committed cell is dropped and tallied (v0.46, replacing ruling
  11.2's byte-inequality form — the drop is expected overlap geometry,
  never an alarm by count; docs/CANARY-D5-DISAGREEMENTS.md): the durable
  `SessionCounters.mopup_dropped_observations` counts every drop and
  `mopup_winner_flips` counts the drops whose implied cell decision
  (K sign / CMY7 W-relative state / CMY8 plane pattern —
  `winner_codes`) differs from the committed owner's — the two-view
  consistency canary for misplaced mop-up windows (advice only, never a
  gate; threshold doctrine post-08-04 lands on the flip rate). VALIDATOR
  PRECISION: the shipped validator is stricter than "(mask and values)"
  above — it also requires exact per-committed-cell ORIGIN-ROW equality;
  its value agreement is numeric (`np.array_equal`), so a hand-built
  superseding block could flip a committed −0.0 to +0.0, passing
  validation while changing the content address — unreachable from
  production wiring, which copies committed bytes verbatim.
- **D6 ParkedWindow record** (schema receiver 22→23, discovery 8→9): per
  parked window — base plan lane id, durable region reference, window ints
  (window_id, region_index, origin px, shape cells, depth, support
  estimate), the fitted pose floats (AffinePose + PoseSegment stats), patch
  ordinal, `attempted_routes`, and the region-scoped survey transients
  `cell_pitch_px` (float) and `lattice_f` — the region's **2×2
  reciprocal-fundamental matrix as four row-major floats** (or None), the
  value `fit_window_pose` seeds; a scalar cannot carry the
  rotation/shear/anisotropy that the weak-fundamental retry arm and
  `jacobian_from_reciprocal` consume, and its components may legally be
  ≈0 or negative (finite-only validation). **No pixels, no sample data** —
  sampling re-derives bit-exactly from the re-materialized lane raster
  (`prepare_region`/`sample_segment` are pure functions of raster bytes +
  persisted geometry; the lattice seed and pitch are persisted because
  they are processing-order-dependent). Dropped: `tried_anchor_ids`
  (mop-up anchor space is fresh; re-paying a 49-score probe is cheap),
  `sample_key` (freshly assigned), and — adversarial review — the
  originally-drafted `word_declared`/`word_rest_done` booleans: rest
  sweeps are M-level-visit-transient work, so neither flag can ever be
  durably true/varying; the declared-once accounting (D13) is structural,
  not a stored bit. The committing `AddressArtifact` names its
  newly-parked ids; the M(Lk) barrier retires its (capture, lane) parked
  rows; a parked row whose M-level already committed is a structural load
  error (mirror of the pending-block invariant).
- **D7 M-level execution.** Survey artifact: empty mint (its address's poses
  legally reference the base level's durable regions — region validation is
  global). Address: re-materialize the Lk raster (deterministic exact-area
  derivation from native), re-sample parked windows, hint inventory =
  **all accepted PoseRecords of this capture across all lanes PLUS the
  capture's LosingHypothesis rows** (runner class, the ordinary 6+2
  portfolio semantics — without this the loser-revisit channel would
  become globally unreachable, since v0.33 moves every cold, the sole
  loser mint, to M-levels), converted through native affines (a
  mop-up-only selector; ordinary lanes keep nearest-productive-prior-lane),
  ranked nearest-first into the ordinary 8-hint portfolio per window;
  routes: hint transport → remaining-slot word decode (visit-transient
  rest state, best-supported first) → cold, under D9's price rule; chain
  among mop-up acceptances with re-pass; cold-refusal subdivision
  (children seeded from the persisted `lattice_f` matrix; their fresh
  patch ordinals obey the D4 watermark). The M-level runs the ordinary
  known-position final-word evaluation and §5.4 conflict firewall **once,
  over its own level's final words** (per-level firewall; cross-level raw
  reads are never pooled — see the §5.4 amendment); its quarantine unions
  into the evidence lane per D4. Calibration/context: the M-level
  re-samples its evidence lane's base-accepted windows as
  **calibration and context labels only** (poses are durable, sampling is
  pure), restoring the pooled per-region label population that the
  pass split would otherwise halve; the owner freeze stays restricted to
  the mop-up's own windows and uncommitted cells (D5). (As shipped
  2026-08-01, v0.35 pool law: those label rows are never terminal-gated,
  and certified-complete/zero-payload payload windows route through the
  same label channel — §8.2 L2–L4; K shipped stage 1a (full-window label
  rows), color shipped stage 1b (furniture-site label rows into the
  QDA/PAVA fit and pitch pool) in the same pass.) Payload: ordinary
  v0.28 SCAN/UNION over mop-up placements at the base lane's aperture,
  blocks under D4/D5; retry150 confined to the M-level's own work (no
  cross-barrier baselines — attempt lineage is delta-local by design).
- **D8 Close-attempt schedule** (ordinary mode only). Clause precedence
  first: **the metadata-terminal carve-out precedes every other clause** —
  any metadata-terminal state (inconsistent, unsupported, malformed)
  consults immediately, at any rank, count, or gate state, so terminal
  states always materialize (a metadata conflict is detectable at two
  counters, long before trust; gating it behind trust would burn the tail
  and end OPEN instead of INTEGRITY_FAILURE). Otherwise the per-barrier
  close runs iff `close_count_ready` holds — metadata trusted AND every
  (stream, block) has distinct certified ESIs ≥ K_b (count gate; skipping
  is exact: a block below count cannot be at rank) — AND, when a prior
  attempt this invocation returned want_more, every then-rank-short
  (stream, block) has gained ≥ **its then-reported shortfall** in distinct
  ESIs since that attempt. **There is no surplus buffer** (the drafted
  B=2 was withdrawn on adversarial review): rank gain is bounded by
  distinct-ESI gain, so the exact shortfall baseline already skips every
  attempt that provably cannot verify while never skipping one that
  could — no verify is delayed or forfeited (any B>0 can skip the
  session's final barrier on a closable frontier, permanently, and
  creates open-but-solvable states that §8.1's ordinary load-reproduction
  contract refuses as corruption; B=0 keeps every ordinary open record
  numerically open by construction). The baseline is
  invocation-transient by design: after crash/resume the gate degrades to
  the count gate alone — one conservative GE — never to a skip. "Stop
  starting new costly work" needs no separate rule: certificates change
  only at barriers, each gated barrier immediately answers, and a
  verified close is terminal for the driver.
- **D9 Priced tail.** Tail visits M-levels across captures by parked EV
  (support-weighted, descending; ties by request order), within a capture in
  plan order. EV weights use the persisted sampled `support_cells`, never
  the layout `support_estimate` (subdivision children carry estimate 0 —
  the layout number would rank child-dominated damaged material last,
  exactly backwards). At the cold boundary inside a visit,
  **PLACEMENT-IMPROVEMENTS §3.5 lands here**:
  cold-first iff the declared cold domain's page count ≤
  `cold_first_max_pages` (policy datum, default 1); else rest-first. The
  v0.29 no-cold-while-undecoded-slots invariant re-scopes to the M-level
  visit, subject to that small-domain inversion. Preemption granularity is
  the M-level visit (stages are uninterruptible; per-cold preemption would
  need per-item payload commits — rejected, artifact model).
- **D10 Raster pool.** Native rasters are opened once per invocation and held
  across phases (mmap TIFFs; PNG stays in RAM — noted memory cost);
  per-barrier source re-authentication unchanged (v0.37: its detector is
  the stat memo, RECEIVE-DESIGN §8).  v0.37 extends the pool to DERIVED
  lanes: each derived scale raster is streamed once into a file-backed
  temp mmap and retained per (capture, lane label, derivation kind) for
  the invocation (`cascade.DerivedLanePool`, released by the runtime at
  drive end), so an M-level visit reuses its base visit's bit-exact
  derivation instead of re-reading native; a parked-empty M-level defers
  derivation entirely behind a metadata-complete lazy stand-in (no
  production consumer reads pixels there — PAYLOAD-IMPROVEMENTS 6.3).
- **D11 COMPLETE semantics unchanged** (CORRECTED 2026-08-02 by D20).
  `len(levels) == len(plan)` including
  M-levels (and, since v0.42, R-levels). A verified-preempted session
  legally leaves ACTIVE captures
  (already a legal terminal shape). ~~`--complete` therefore runs the full
  tail — exactly its exhaustive-harvest meaning.~~ CORRECTION (D20):
  `--complete` governs exactly one thing — deferring fountain
  checks/solves to the end of the invocation's flag-bounded plan prefix —
  and never did imply the lane families; the tail runs under the
  invocation-only `--mopup`/`--refine` flags, and a `--complete` run
  without them legally ends OPEN with parked lane families, resumable.
  Duplicate short-circuit
  unchanged. CLI gains a derived presentation status "swept, mop-up pending"
  (no durable field).
- **D12 Identity.** Scheduler id `holo/phased-session/rung-major-v1`
  (bumped to `rung-major-v2-r-lanes` by D20, 2026-08-02; to
  `rung-major-v3-u-lanes` by the PK4.3 supplemental-lane law,
  2026-08-08 — see D21 below);
  ProductionAddress policy id hand-bumped → `v6-phased-schedule`; golden
  pins updated as part of the amendment. Every pre-v0.33 state refuses
  (plan change + schema bump; no migration, by doctrine). Route labels,
  component inheritance, attempt identities, and redundancy bookkeeping
  diverge from any capture-major replay — the two schedulers' states are
  deliberately not byte-comparable.
- **D13 Word-domain vocabulary.** A window's Stage-A domain is declared once
  per window **lifetime**, at the level that first samples it — a
  structural fact derivable from the causal record, not a stored bit (the
  originally-drafted `word_declared` flag was dropped from the parked row
  by D6; code agrees with D6); M-level rest decodes add zero
  declared hypotheses; subdivision children declare their own as today.
- **D14 Diag.** (a) Session phase: a scheduler-emitted phase event + an
  `EventContext` field; shown at the lane-row phase tail (`rung 2ppc ·
  capture 2/3`, `mop-up tail · 14 parked`), format row unchanged. (b) Pane-A
  chips gain the plan-level digit and a distinct parked-for-mop-up overlay
  state (v0.31 escalation ladder extended); per-chip digit omission below
  fit (outline kept) — the pane-wide one-font blanking rule is wrong for
  data-dependent chip sizes. (c) Heartbeats: `address.cold_progress` from a
  new optional callback in the cold page loop, count-bounded to ≤64
  emissions per sweep (every ⌈P/64⌉ pages — count-based bounding is the only
  §10.6-compliant form; headless runs skip callback construction); AS
  SHIPPED heartbeats are COLD-ONLY — the drafted per-rotation rest-sweep
  heartbeat was never wired and `address.cold_progress` is the only
  heartbeat family (§5b deviation 7); heartbeats are never milestones and
  never snapshot. Phase string shows `cold 47/312`. (d) AS IMPLEMENTED
  (superseding the drafted `mopup.*` family): M-levels are ordinary
  levels to the observer — they report through the ordinary
  survey./address./payload. families under their own unique lane ids
  (per-lane `address.final` finality holds structurally; the mop-up
  survey.complete carries `survey.mopup_of`); parked chips freeze their
  emitted geometry at parking time, survive lane/barrier/final resets,
  and retire when the committed state no longer carries their rows —
  geometry is never approximated from durable records alone. (e)
  EXECUTION NOTE: the diag split (rows.py / transport.py /
  presentation.py) merged first; this work landed on that layout.
- **D15 Epilogue.** Parked-inventory report derived from **durable state**
  (works on cold resume — a deliberate new durable-advice row in the §10.7
  availability table): parked counts per (capture, lane) + support
  distribution. Shown on NOT-RECOVERED and on OPEN ends with a pending tail;
  the v0.21 rescan hint becomes conditional ("N parked windows have not been
  attempted; the mop-up tail may close without rescanning"). Exit code stays
  2; a distinct code for tail-pending is an open refinement. AS SHIPPED
  (recorded 2026-08-02, lens-doc-v33:08): the epilogue derives from
  `SessionState.parked` and is silently UNAVAILABLE in discovery mode —
  `DiscoveryState` exposes no parked inventory, so the CLI's
  `getattr(state, "parked", ())` finds nothing on discovery runs.
- **D16 Integrity finding — SEPARATE RULING OWED (not in v0.33).** The
  payload GF(2) solver, unlike the metadata solver, never checks
  surplus-equation consistency: a wrong certificate in a dependent row is
  silently masked; in a pivot it produces a terminal, immutable,
  unlocalizied integrity-failure brick (measured on a K=12 probe: 0/16
  corruptions detected pre-SHA). Recommended follow-up: report-only
  post-solve surplus re-encode audit at close time (observation-only; also
  covers the systematic fast path where repair rows are never consulted);
  fatal-vs-quarantine semantics need an explicit doctrine ruling
  ("certified disagreement is integrity-fatal" vs adjudication).
- **D17 Discovery.** Branch-major outer loop preserved (plans differ per
  row); within each branch the phased driver runs over that branch's
  captures (inner loop restructured to one multi-capture phased call).
  Cross-branch rung interleaving: future option, not v0.33.
- **D18 Housekeeping in the same amendment.** Stale schema sentence (§8 said
  19; code was 22 → now 23/9); doc title v0.31 → v0.33; `--complete` help
  and §8.1 lane-shaped wording; `place.py:193` "historical insertion order"
  docstring; `payload_engine.py:162` stale "K passes the whole frontier"
  comment. Post-review additions: §6.1's "capture-major scheduling"
  retention attribution, §10.4's retired `payload.color.*` event block +
  the missing v0.33 families, §12.1 item 2's stale "GATE DECISION
  PENDING" (v0.30 executed it), §3's flow lines (count-gated close;
  "next level" may be a mop-up), bare "§3.5" citations qualified to
  PLACEMENT-IMPROVEMENTS, HOLO-DESIGN §9.2's state brace list, and the
  §10.7 availability table row D15 claims (now actually added).
- **D19 Parked vocabulary (adversarial review).** `WindowOutcome` gains
  `parked` and region terminality is re-derived: a phase-1 region with
  parked windows is NOT `unresolved` — that word stays bound to
  cold-refused-terminal; region-complete events and the §10.3.3
  piece-state vocabulary carry the parked state, and `address.final` at a
  phase-1 barrier is final for the level, not for the region's parked
  remainder. The §10.5 overlay-clearing rule exempts parked-for-mop-up
  chips (cleared at terminal resolution or their M-level's retirement).
- **D20 Refinement lanes R(Lk) + parking flags + the `--complete`
  correction (user rulings, adjudicated 2026-08-02; RECEIVE-DESIGN
  v0.42; resolves PAYLOAD-MEASUREMENTS §6's open ruling as option
  (a)-as-lane for K AND color).**
  Refinement moves out of the inline payload stages into REFINEMENT
  LANES: `scale_plan` (pure function, unchanged inputs) returns
  `[L0..Ln, M(L0)..M(Ln), R(L0)..R(Ln)]` — one R entry per ladder lane,
  after all M-levels, coarse→fine; `LaneSpec` gains
  `refine_of: str | None` mirroring `mopup_of`, and a level is exactly
  one of ordinary/mop-up/refine. R-LANE SEMANTICS: OWN evidence
  namespace — the R lane's blocks/attempts key on its own ordinary
  lane id, NOT the base evidence lane (only certificates cross lanes;
  LLRs never cross correlated views), so there is no supersession of
  base blocks and no new evidence law. The R(Lk) address takes the base
  lane Lk's committed accepted poses, refines each eligible window
  against the full accumulated certificate frontier (codec leaf), and
  its payload delta covers ONLY affected regions (windows with adopted
  poses + their region-coupled context); unaffected regions contribute
  NOTHING at the R barrier (their Lk evidence stands; NeedMap prunes
  certified addresses). No adoptions ⇒ empty delta, cheap barrier.
  R(Lk) binds to Lk's exact transform (`validate_lane_request` binds it
  exactly as it binds M(Lk); `LaneSpec.base_lane_id` names the raster
  binding), and R-levels always run behind the lazy raster stand-in —
  no eligible work (no certificates yet, or no uncertified tiles) means
  no raster materialization. FLAGS (invocation-only, scheduling-only,
  absent from policy/schema — the `--complete` family): `--mopup` and
  `--refine` on decode. Default invocation drives the plan through the
  ordinary ladder ONLY and stops before the first M entry; `--mopup`
  extends through M-levels, stopping before the first R entry;
  `--refine` extends through everything — BY THE PLAN-PREFIX LAW this
  necessarily includes pending M-levels. Verified-close preemption and
  stop_requested keep their existing precedence. Flags select how far
  the drive may proceed THIS invocation; committed prefixes are always
  honored; resume with different flags continues monotonically. Tail
  order: all M-levels run before any R-level session-wide (class-ranked
  tail EV), so every R(Lk) sees the maximal accumulated frontier.
  THE `--COMPLETE` CORRECTION (amends D11 and the former §8.1 wording):
  `--complete` governs EXACTLY ONE thing — whether fountain
  checks/solves are deferred until the work this invocation runs is
  exhausted (then one close). It does NOT imply `--mopup`/`--refine`
  and never did imply lane families; a `--complete` run without the
  lane flags legally ends OPEN with parked lane families and is
  resumable. CaptureStatus.COMPLETE still means every plan level
  committed (now incl. R-levels); a session that never runs the flags
  legally stays with ACTIVE captures; CLI epilogues advise the pending
  families by flag name (e.g. "mop-up tail parked: N windows
  (--mopup); refinement pending: M eligible lanes (--refine)").
  DISCOVERY: per-branch drives are flag-bounded identically; the
  deferred one-final-close fires when every candidate/acquisition pair
  is c-excluded, terminal, or has committed its flag-bounded prefix —
  the durable `round_complete`/status derivations stay full-plan and
  flag-free. IDENTITY: receiver schema 23→24, discovery 9→10,
  scheduler id `holo/phased-session/rung-major-v1` →
  `holo/phased-session/rung-major-v2-r-lanes`; ProductionAddress /
  payload policy ids bump in stages B/C when the codec refinement
  leaves land; every pre-existing state refuses; no migration; goldens
  and pins re-derived through the code, never hand-edited. STAGING:
  stage A (SHIPPED with this row) = plan shape, flags, parking,
  EMPTY R-level processors (survey = empty mint; address = empty
  durable product carrying the typed transient
  `production.RefineAddressPlan` base-lane references — the stage-B/C
  contract; payload = empty delta), epilogues, amendments, pin
  re-derivations; stages B/C = the K and color codec refinement leaves.
  Stage B (SHIPPED 2026-08-02) = the K leaf: RECEIVE-DESIGN v0.42
  clause (B) — `production_refine.process_refine_level` +
  `place.place_committed` + `payload.collect_refined_region_delta`;
  inline K refinement removed; K payload policy id
  `…-v11-f32-scores` → `…-v12-r-lane`.
  Stage C (SHIPPED 2026-08-02, corrected same day by RECEIVE-DESIGN
  v0.44): the color leaf's committed-pose domain is the SAME shared
  `place.place_committed` audited reconstruction as K — its short-lived
  geometry-only window-rectangle inventory kept off-support cells that
  crashed the real-corpus R delta on partial-coverage scrap
  (`COLOR_PAYLOAD_POLICY_ID` `provisional-v7-r-lane` →
  `provisional-v8-r-lane`).

- **D21 Supplemental lanes U(Lk, arm)** (color-uplift PK4.3, 2026-08-08;
  law text RECEIVE-DESIGN §6.2a, measured record
  COLOR-UPLIFT-MEASUREMENTS §10). A FOURTH lane class, COLOR ONLY:
  `scale_plan` becomes codec-aware and a color plan gains
  `[U(Ln, a3), U(Ln, a4b)]` after the whole `[L…, M…, R…]` sequence,
  both bound to the FINEST ordinary rung; K's plan is byte-identical to
  D20's. A u-lane binds its base lane's exact transform and committed
  poses like an R-level, owns its own evidence namespace, mints no pose,
  parks no window, and inherits the R leaf's pixel-free pre-gates
  verbatim — it refines nothing and instead re-runs the payload
  transaction over that domain with ONE campaign arm forced. It needs no
  adoption gate because §6.3's per-address retirement law bounds it to
  the uncertified residue, which makes its certificate delta
  non-negative by construction. TAIL ORDER: class rank −1, i.e. below
  refinement levels, so a u-lane runs after every lane that could still
  shrink the residue; it rides `--refine` (already "the whole plan") and
  gets no flag of its own, because a monotone lane gives an operator
  nothing to weigh. IDENTITY: the arm is spelled into the lane id
  (`u<NN>-<arm>-<ppc>ppc-<dpi>dpi`), so `LaneSpec` gains NO persisted
  field and every archived state still loads; scheduler id
  `rung-major-v2-r-lanes` → `rung-major-v3-u-lanes`, and
  `COLOR_PAYLOAD_POLICY_ID` gains `union-lanes-a3-a4b-v1`.
  **[SUPERSEDED IN PART — the entry above describes D21 as first landed.
  As shipped (PK5/PK-CLEAN/v0.54, 2026-08-09/10): the tail is
  `[U(Ln, off), U(Ln, a3), U(Ln, a4b)]` (u-off completes the union law),
  `cascade.uplift_arms_for_codec` filters it per coding (a single-stream
  coding drops a4b), the scheduler id is
  `rung-major-v4-u-lanes-codingaware` — whose bumps refuse pre-bump
  states of ALL codings, K included, the token being coding-independent
  — the policy token is `union-lanes-a3-a4b-off-v4-zerofrontier-codingaware`,
  and the "pre-gates verbatim" clause is corrected by RECEIVE-DESIGN
  v0.54: the pre-gates are ARM-SPLIT (only U(a4b) requires a certified
  frontier; U(off)/U(a3) run on a zero-frontier capture).]**

## 2. What is deliberately NOT changed

Admission bars, budgets, floors, per-route domains, rival sets, the complete-
domain discipline (§5.3), close authority at the barrier, §8.1's no-fountain-
consult-under---complete, the one-owner rule, LLR lane isolation, v0.28 SCAN
single-component minting, certificate dependency law, retry150 semantics,
CaptureStatus/LevelRecord derivations, and the no-migration doctrine.

## 3. Runtime model (both close modes)

(Since D20 the drive is additionally bounded by the invocation-only
`--mopup`/`--refine` flags — the "tail" below runs only as far as they
allow; `--complete` bounds nothing, it only defers the close.)

- **Without `--complete`**: the prize is close preemption. All captures'
  coarse cheap evidence lands before any fine lane or any cold; on
  multi-sheet intact sessions the session plausibly closes inside phase 1.0
  (today capture-major pays capture 1's entire ladder first — 1394 s
  all-stages on the synthetic chain). The tail runs only what the close
  still needs, best-EV first, and D8 keeps the multiplied barrier count
  cheap (count gate; no per-barrier GE until counts can possibly close).
- **With `--complete`**: no preemption; total declared work invariant. Wins
  change mechanism: maximal early certification → NeedMap pruning shrinks
  fine-lane and tail BP work; session-wide hint inheritance converts colds
  to 49-score searches; the batched cold tail amortizes reference-side
  work. EV order stops mattering for whether and keeps mattering for how
  few colds run.
- **Single-capture sessions on clean material** degenerate to today's
  v0.23/v0.29 ladder plus the price inversion and the D8 close gate; the
  plan grows with cheap no-op M-levels (the measured clean fragment
  parks nothing) and, since D20, with R-levels that stay flag-parked
  unless `--refine` is given. On damaged material the pass split changes ownership
  and calibration populations (D5), so "never worse" is NOT claimed a
  priori there — it is exactly what the §4 qualification bars gate.

## 4. Build gates and measurement plan

1. **Cold-necessity counterfactual** (offline, free, pre-08-04): from
   existing session states, remove cold-descended certificates and re-ask
   rank completeness — sizes the preemption prize per material class.
2. **WindowAttempt ledger census** (§5.1 of PLACEMENT-IMPROVEMENTS) on real
   corpus: colds per lane per material class; chain-reachable fraction.
3. **Synthetic A/B** (with implementation): phased vs capture-major (git
   worktree baseline), byte-identical inputs — certified-set comparison
   (**equality when nothing parks** — the clean-chain case; directional
   otherwise: coverage ≥ baseline, recovered-bytes equality whenever both
   arms verify — full equality is unachievable by construction once a
   window parks, because calibration pools, owner assignments, and
   attempt identities legitimately diverge), time-to-close, cold count
   per region, barrier count and close-attempt count (D8 gate
   effectiveness), peak RSS (raster pool + tail cache).
4. **Real-corpus comparative qualification post-08-04** (the freeze gate):
   intact sheets both engines, scissors confetti, 3–4-scan multi-capture;
   pre-registered bars — cold count per region must not increase, coverage
   under `--complete` ≥ baseline, time-to-close must drop on multi-sheet
   sessions; plus the §1.4b per-region coarse-payload exclusivity census
   and the confetti regime.

## 5a-bis. Real-corpus wall decomposition (2026-08-01, instrumented rerun)

Per-stage processor seconds (c2-cmy7 20x2 scrap corpus, both arms
sequential on this machine): survey 194.6 vs 196.2; address 627.6 vs
649.5 (329.5 base + 320.0 mop-up — cold/rest work RELOCATED, not added;
the +22 s is label reconstruction + parked re-sampling); payload 550.3
vs 545.8 (delta unattributed run-to-run variance — NOT "pooled labels":
the c2-cmy7 color payload stage consumed no labels at all until the
v0.35 pool law's stage 1b wired them; finding color-payload:01);
RUNTIME RESIDUAL 182.9 vs
332.5.  ATTRIBUTED EXACTLY by direct measurement: each scrap source is
a 6.8 GB TIFF and one SHA-256 pass costs ~19.1 s on this machine —
`verify_source_unchanged` re-streams the committing capture's file at
every retention barrier, so baseline pays 2 ingest + 8 barrier hashes
~= 190 s (measured residual 182.9) and phased pays 2 + 16 ~= 342 s
(measured 332.5).  The whole +169 s wall delta is EIGHT EXTRA 6.8 GB
SOURCE RE-AUTHENTICATIONS; persist/close machinery is a minor term at
this corpus size.  Any optimization is design-gated on the §8
re-authentication law (per-barrier source re-auth is an integrity
invariant, not a cache miss) — candidates for a future ruling: one
hash per driver advance covering consecutive same-capture barriers, or
a per-invocation hash memo invalidated on any observable file change;
both need explicit amendment, never silent weakening.  RULED AND
SHIPPED (v0.37, RECEIVE-DESIGN §8 amendment): candidate (ii), the
stat-keyed memo — ingest retains the verified (dev, ino, size,
mtime_ns) tuple, each retention barrier fstats and skips the re-stream
only on an exact match, ANY observable change escalates to the full
re-stream + SHA compare (memo refreshed only on a passing full check).
Per-barrier detection stands; on this corpus the eight extra
re-authentications and most of both arms' residual collapse to fstat
calls.  Candidate (i) is superseded (dominated on savings and detector
coverage; the deliberate-forge caveat is recorded in §8).

## 5b. Implementation-fidelity audit (2026-08-01, design vs shipped code)

Every decision D1–D19 is implemented; the deviations below are the
complete list, each deliberate and recorded.

**Does the session solve all ordinary lanes of all scanned pages before
any mop-up work?  YES — structurally, at two independent layers.**
(1) The phase driver's rung loop (`runtime._execute_receive`) advances a
slot only when its next plan entry has `mopup_of is None` and matches the
current ascending-ppc rung; the tail loop runs strictly after the rung
loop exhausts — so no M-level can START while ANY capture still has an
unexecuted ordinary lane, session-wide.  (2) Independently of the driver,
each capture's plan is `[L0..Ln, M(L0)..M(Ln)]` and the barrier ordinal
is derived from the retained prefix length at three enforcement points
(`session.validate_barrier`, `runtime.run_lane`, `runtime.commit`), so a
buggy driver could not commit a mop-up before that capture's ordinary
lanes.  Cold is page-atomic within a lane (one FFT pass sweeps every
declared page).  The two designed exceptions: a verified/terminal close
preempts everything remaining (the prize), and an operator stop request
ends the drive at the current barrier.  In discovery the guarantee holds
per branch (branches sequential; c-excluded captures never enter a
branch's request).

Recorded deviations from the design text:

1. **The `mopup.*` event family collapsed** (D14d): M-levels report
   through the ordinary survey./address./payload. families under their
   own unique lane ids — `address.final` finality per lane holds
   structurally, and the mop-up survey.complete carries
   `survey.mopup_of`.  §10.4 was amended to say exactly that.
2. **Preemption granularity is the M-level visit** (D9 as corrected):
   per-cold preemption inside a visit would need per-item payload
   commits — rejected with the artifact model.
3. **Cross-branch rung interleaving in discovery**: per-branch phased
   drives only, exactly as D17 scoped it; cross-branch stays a future
   option.
4. **D8 lives inside ProductionClose**, not the runtime: stub close
   processors in fixtures keep per-barrier semantics, and the schedule
   is close-policy behavior.  The close.check surplus/gate facts ride
   the CloseProgress snapshot rather than event details.  AS-SHIPPED
   COROLLARY (v0.36, ruled = document): D8's "(ordinary mode only)"
   header describes intent, not placement — the count gate therefore
   also runs at the one `--complete` deferred final consult and at
   terminal replays.  This is correct behavior, not a defect: a
   count-short final frontier provably cannot verify, so its gate skip
   returns the retained OPEN close unchanged and publishes COUNT-ONLY
   progress (`CloseProgress.count_only`; reach, never a fake rank),
   while terminal states always consult (verified/fountain-failure
   frontiers are count-complete by construction; metadata-terminal
   states take the precedence carve-out).  The pre-v0.36 display defect
   (raw-record progress crash + missing count-only marking on gated
   skips) is fixed and pinned (tests/holo/test_close_schedule.py).
5. **D10's memory caveat stands unmeasured** for PNG (in-RAM) sources ×
   many captures; mmap TIFFs are the production shape.  The real-corpus
   A/B measures RSS.
6. **D5 supersession is materialized, not validated-only** (recorded
   2026-08-02; shipped d2e5281, counter v0.36, counter REPLACED v0.46):
   colliding fresh blocks are rewritten into committed-verbatim-plus-
   novel supersets, dropped observations are tallied with their winner
   flips (`mopup_dropped_observations`/`mopup_winner_flips` — the
   v0.36 byte-inequality disagreement count was measured vacuous,
   docs/CANARY-D5-DISAGREEMENTS.md), and a nothing-novel collision
   emits nothing — see D5 "AS SHIPPED, MATERIALIZED".
7. **D14c heartbeats are cold-only**: the per-rotation rest-sweep
   heartbeat in the design text was never wired; `address.cold_progress`
   (count-bounded, cold page loop) is the only heartbeat family.

D20 stage-A note (2026-08-02): the §5b guarantee "all ordinary lanes of
all scanned pages before any mop-up work" now extends one class further —
no R-level can start while any capture still has an unexecuted M-level
within the invocation's flag bound (rung loop → mop-up tail → refinement,
class-ranked in one tail loop; per-capture plan-prefix law enforced at
the same three points).  The default invocation stops BEFORE the first
M entry, `--mopup` before the first R entry, `--refine` runs everything;
`session.phase` event kinds are unchanged (R-levels run inside the
"tail" phase).  R-levels report through the ordinary
survey./address./payload. families under their own lane ids, exactly as
D14d collapsed the M families.

## 6. Friction ledger (from the eight-area read — resolutions)

| Friction | Resolution |
|---|---|
| Single-ACTIVE invariant (3 gates) | D2 replacement rule |
| Scheduler contract per-capture, loop above it | D1 session phase driver owns iteration |
| Plan pure-function triple-check | D3 keeps purity; M-entries in the derivation; silent `zip` truncation in `validate_state_for_spec` fixed |
| Lane-id double duty (plan vs evidence) | D4 split identity via `mopup_of` |
| One-key-one-content vs late evidence | D5 extension-only supersession |
| LevelRecord causal chain at M-levels | D7 empty survey mint + global region references |
| Parked windows transient-only | D6 compact durable record; pixels re-derived |
| Nearest-lane-only hint selector | D7 mop-up-only all-lanes selector |
| Rank not expressible as K_b + buffer | D8 surplus-count form; B on re-attempts |
| Escalation-after-failed-verify impossible (terminal brick) | D8 escalates on want_more (recoverable), not on verify failure; brick surfaced as D16 |
| Per-barrier close cost under rung-major | D8 count gate (K path gains what color's preclose had) |
| §8.1 vs mid-session rank consult | D8 is count-only in gating, full close only when gate passes; `--complete` untouched |
| Ladders misalign across DPIs | D1 rung-by-ppc correspondence |
| Raster reopen cost | D10 pool |
| `--complete` forces the whole tail | D11 accepted at the time — CORRECTED by D20 (2026-08-02): the tail runs under `--mopup`/`--refine`; `--complete` only defers the close |
| Diag capture-scoped resets, chips vanish at barrier, silent spans | D14 |
| Epilogue live-only | D15 durable derivation |
| Declared-once word domain across barriers | D13 lifetime vocabulary |
| Redundancy/component divergence vs oracle | D12 accepted, not byte-comparable |
| Subdivision lattice_f order dependence | D6 persists the seed |

Adversarial-review additions (2026-07-31, four lenses, 16 verified defects):

| Defect | Resolution |
|---|---|
| Patch-ordinal collision across the two passes of one evidence lane | D4 watermark rule + M-barrier collision check |
| Any B>0 close buffer forfeits closable sessions terminally and breaks §8.1 load reproduction | D8: B withdrawn; exact per-(stream,block) shortfall baseline; resume degrades to count gate |
| Metadata-terminal states gated behind trust could never materialize | D8 precedence clause (carve-out first) |
| lattice_f is the 2×2 reciprocal matrix, not a scalar | D6 four row-major floats, finite-only |
| Loser/runner-up revisit channel globally unreachable (colds moved to M-levels) | D7 inventory includes LosingHypothesis rows |
| Base/mop-up pass split changes ownership + calibration semantics silently | D5 stated departure; D7 label-only re-sampling; §4.3 conditional-equality bar |
| Parked windows had no outcome/region-state vocabulary ("unresolved" would lie) | D19 |
| §5.4 run-once firewall unexecutable across the split | per-level firewall, quarantine unions on evidence lane (§5.4 amendment) |
| Draft `word_declared`/`word_rest_done` durably dead | D6 dropped both |
| Tail EV weight degenerate for subdivision children | D9 uses sampled support_cells |
| Doc contradictions left standing (§6.1 attribution, §10.4 event list, §10.5 clearing, §10.7 table, §12.1 staleness, §3 flow, bare §3.5 cites, HOLO-DESIGN §9.2) | D18 post-review additions |
