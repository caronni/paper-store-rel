# PAYLOAD-IMPROVEMENTS — E023b/E023c payload + fountain stage: verified findings & discussion

> **EXECUTION (2026-08-02).** The adjudicated rulings in §13/§13a are
> being executed per docs/PAYLOAD-REWORK-PLAN.md (the adopted order;
> deviation needs a recorded reason). Landed so far on the
> `payload-rework` branch: phase 0 `bfda48a` (pool-law oracle, D5
> materialization pins, decomposition harness), phase 1 `a1d8fbc` (the
> pool law L1–L6, K + color — RECEIVE-DESIGN v0.35), phase 2 `5dac537`
> (close/D8 repair + plumbing collapse + D5 counter — v0.36), phase 3
> `5c65683` (mint-once, stat-memo re-auth, raster lifetime, blob cache,
> K/color vectorization — v0.37). Phase 4 (dead code, doc truth,
> structure) landed as v0.38; phase 5 (ruled numerics) v0.39; phase 6
> (color parity) v0.40; phase 7 (test-strategy redesign — the §8
> coverage batch, battery retirements, bounded phased e2e, curated slow
> lane) v0.41. The §4 doc-truth rows below were executed 2026-08-02
> (v0.38 clause B) — the row text stays as the findings record.

Status: **discussion, not normative** (2026-08-01). Findings first: nothing
here is an amendment or a fix. Every doc-vs-code divergence below is reported,
not resolved — resolving toward either side needs a user ruling (several are
requested in §11). Every numerical change needs its own exactness fixture;
result-affecting items need a RECEIVE-DESIGN amendment. PLACEMENT-IMPROVEMENTS
is the template and the precedent.

Provenance: the 2026-08-01 payload-stage verified read — 11 module-family
readers + 7 adversarial lenses over all ~13k payload-stage lines (everything
after placement/address: payload evidence, calibration/detection, LDPC
certification, barrier commit of payload facts, certified refinement, fountain
solve), then 15 adversarial verification batches re-reading every pin; plus a
measured-record supplement over docs/PAYLOAD-MEASUREMENTS.md (§1.3/§5 entry
points) with its own adversarial verifier. 158 raw findings → 143 deduped →
**136 confirmed/adjusted, 0 refuted, 5 growth-audit-duplicate status rows**,
plus 8 confirmed measured-record findings (MR-01..08) and 283 clean-bill
entries. IDs below (`reader:NN`, `MR-NN`) key the full verified detail; the
durable summary is the `holo-payload-audit` memory.

Standing constraints that bind everything here:

- Certification chain, CRC/SHA gates, one-owner, bounded-LLR, complete-domain
  and calibrate-or-refuse rules are non-negotiable; no finding proposes
  weakening any of them. No confirmed finding can mint wrong bytes — every
  correctness item below is a refusal/yield/diagnostics/identity defect
  behind the CRC/SHA wall.
- Waste items must be exact-preserving (result-identical) with a fixture, per
  the §5.3-style caching allowance and the hoist precedent.
- The kiss validation-boundary ruling governs interior-check findings; the
  re-authentication law (§8) gates the re-auth family (§7 below).

## 1. The region pool law — refined-reuse × terminal-skip × D7 labels
(the flagship correctness family; ONE design ruling resolves all of it)

Since c7aa340 (2026-07-29) the K sampler skips any window whose payload cells
all lie on certified tiles (`_window_all_terminal`, _payload_windows.py:746-751)
— per WINDOW, inside mixed regions. That change, the v0.34 D7 label machinery,
and the §7 refined-reuse path now disagree with each other and with §8.2 about
one question: **who belongs in a region's pitch pool and fit population**. Five
confirmed findings are facets of that one unanswered pool law:

- **1.1 (payload-windows:03, doc-vs-code, major)** §8.2:1013-1016 still
  promises the region-granular conservative cut ("every patch in a mixed
  region remains available as calibration/context for its unresolved
  neighbour"); the shipped skip is window-granular and drops the certified
  sibling's word/filler observations from the pooled ctx fit. Ledger v0.15
  records the region-granular form; v0.16 claims "semantics identical"; no
  doc or memory records the window-granular form — the only record is the
  c7aa340 commit message (measured basis: 99.4% post-calibration discard,
  identical certificates, byte-identical recovery). Aperture is NOT affected
  (pitch at :739 still pools skipped windows); the divergence is the
  fit-population sentence. Code is the intended side; §8.2 owes the amendment.
- **1.2 (lens-e023:01, divergence-e023, major)** The same skip is the one
  **unrecorded algorithmic divergence from E023b**: the historical receiver
  (experiments/023b ALGORITHM-ARMS.md §3.3) pooled search-parity pilot
  samples from all non-refused windows — certified-complete windows
  contributed. The skip also covers D7 `label_placements` (:741), so a label
  wholly on certified tiles silently leaves the label pool too.
- **1.3 (payload-windows:01 + refinement:03, correctness, major)** The
  refined-reuse path computes `_region_pitch`/`_filter_signature` over a pool
  that EXCLUDES the gen-0-terminal windows gen-0's pitch included
  (_payload_windows.py:556-570 deletes them; :646-649 pools the remainder),
  and the conservative-resample guard compares reduced-baseline vs
  reduced-refined — never against the true gen-0 signature — so an integer
  (halo, aperture) flip between the two pool medians is invisible. Breaches
  the pinned v0.34 rule "the region crop pitch pools placements UNION labels
  — the single-pass aperture". Sibling (refinement:01, major): certified
  refinement's replay pool (`prepare_region_image`, certified_refine.py:243/254,
  fed promoted-only from production.py:904-910) omits labels and skipped
  windows the gen-0 pool contained; there an integer flip fails the
  `np.array_equal` replay gate (certified_refine.py:742-749) and raises an
  uncaught **RefinementIntegrityError** — a deterministic fail-closed brick.
- **1.4 (payload-windows:02 + refinement:02, correctness, major)** Gen-0
  terminal-gates LABELS out of the region fit (:741→:746-751); the
  refined-reuse path re-samples every label of an affected region with NO
  terminal check (:662-668). The two production passes therefore disagree
  under any nonempty terminal set with an affected labeled region — a silent
  break of the §7 "numerical identity, not an approximation" contract
  (payload.py:279; RECEIVE-DESIGN:763). **Which side is right is genuinely
  open**: D7's text ("restoring the pooled per-region label population",
  PHASED-SCHEDULE:126) and v0.34's ungated "re-derives them for affected
  regions" support the UN-gated reading, under which gen-0's terminal-gating
  of labels (detect-k:05: at M-levels, base-accepted windows whose tiles
  certified in the interim contribute no labels — thinning the restored
  population exactly where D7 matters) is the defect and the refined path is
  accidentally right. Related pin (payload-windows:09, supervisor-verified):
  the reuse path reads only `baseline_address.label_placements`
  (_payload_windows.py:617); nothing reads the refined address's labels.
- **1.5 (payload-windows:08, correctness, note)** An all-reference window's
  region-context contribution flips on the existence of ANY certificate —
  a knife-edge of the same skip predicate (_payload_windows.py:189-194).

RESOLUTION SHAPE (ruling requested, §11.1): state the pool law once —
(a) pitch/filter-signature pool membership (gen-0 currently: everything;
refined/replay currently: survivors only); (b) fit-population membership for
placements (window-granular skip: keep and amend §8.2, or revert to
region-granular); (c) fit-population membership for labels (terminal-gated or
not — one answer for gen-0, refined-reuse, and M-levels). Then make all three
paths implement the one law. GATE (§12.1): whatever the ruling, the pooled
oracle fixture must gain terminal-set and refined-path cases — today
`test_split_region_fit_equals_pooled_oracle` passes no terminal set and never
touches the refined path (tests/holo/test_phased_schedule.py:386), which is
why all of §1 shipped green.

## 2. D8 / deferred-close diagnostics crash cluster (one wrong variable)

- **2.1 (production-drivers:01 = fountain-close:01, correctness, major —
  found independently twice)** Both `metadata_progress` thunks feed RAW
  `TileCertificateRecord` rows (no `.counter`/`.metadata_bit`) where
  `CertifiedStreamSymbol` is required: the D8 gated-skip lambda closes over
  `context.state.certificates` (production.py:1160-1163) although `_gated`
  already RECEIVES the converted rows as a parameter, and the deferred-close
  snapshot does the same (runtime.py:554-558). `metadata_from_certificates`
  reads the missing attributes unconditionally (fountain_close.py:176/179) →
  guaranteed AttributeError once ≥1 certificate exists. Every consumer
  swallows it: cli.py:343-349/:381-387 → the D15 parked-inventory shortfall
  and D16 surplus epilogues silently vanish on the normal NOT-RECOVERED
  ending; under --diag, observer.py:310-317 sets `_snapshots_failed` on the
  first builder exception → **every later pane snapshot for the run is
  refused**. On the real corpus all 16 checks were count-gated, so every
  barrier hit this path. Breaks v0.32 ledger item (5) and PHASED-SCHEDULE §5b
  deviation 4 as recorded. Tests green because fixtures use zero-cert states,
  duck rows, or headless runs. Diagnostics lane only — no durable-state risk.
- **2.2 (fountain-close:02, correctness, minor)** With a non-empty want_more
  baseline, a NON-raising metadata-terminal state (malformed/unsupported)
  reaches `_counts` → `VolumeCode(None, …)` → TypeError (fountain.py:423),
  contradicting `_gated`'s own docstring promise that metadata-terminal
  states consult.
- **2.3 (fountain-close:05 + lens-doc-v33:03, correctness/display, minor)**
  The gated-skip snapshot carries count-only progress WITHOUT the
  `deferred_counts` marking — once 2.1 is fixed, rows.py's non-deferred
  branch would print fake "rank 0/needed" and the CLI shortfall epilogue
  would overstate (sum of all needed) — fix together with 2.1.
- **2.4 (lens-doc-v33:06, doc-vs-code, minor)** D8 is declared "(ordinary
  mode only)" but the count gate lives in `ProductionClose.process` with no
  mode awareness: the one `--complete` final close and terminal replays pass
  through `_gated` too. Durably identical (a skip returns the retained OPEN
  close), but the final CloseProgress degrades to count-only and inherits
  2.3's display defects.
- **2.5 (lens-doc-v33:09, doc-vs-code, note)** v0.34's "a VERIFIED run now
  discloses masked wrong certificates" holds only for the FIRST verifying
  run: reproduction paths (runtime.py:737-755) never populate
  `close_progress_sink`, so reruns of a terminal state print no surplus
  epilogue although they recompute the audit.

## 3. Color-path divergences (D7 unwired; calibration docs stale)

- **3.1 (color-payload:01, doc-vs-code, major)** **D7 label re-sampling is
  not wired into the color payload path.** The codec-independent address
  stage mints `label_placements` at every M-level (place.py:1378-1388/1532)
  and the c2-cmy7 real corpus paid the measured +22 s reconstructing them —
  then `collect_color_evidence` iterates only `payload_placements`
  (color_payload.py:613); the only label consumers are the K paths. D7/v0.34
  are codec-unscoped and §5b's "complete" deviation list records no color
  exclusion. Consequence: a color M-level's QDA/PAVA fit and region pitch
  pool only mop-up windows; `_fit_detector` refuses on uncovered states with
  labels available and dropped. Also falsifies the §5a-bis parenthetical
  "payload 550.3 vs 545.8 (pooled labels slightly cheaper)" — pooling is not
  wired for that codec. Ruling §11.3: wire labels into the color fit/pitch,
  or record the color scoping in §5b + v0.34 (and correct §5a-bis).
- **3.2 (color-upstream:01, doc-vs-code, major)** CMY8 component PAVA
  calibrates on dust PLUS prior-certified complete-state payload
  (color_fitting.py:160; policy id `dust20-priorcert-`, color_payload.py:67)
  — sanctioned by RECEIVE-DESIGN:624-625 — but COLOR-INTEGRATION-DESIGN:653
  ("Calibration rows are dust only.") and HOLO-DESIGN:1382-1383 ("component
  PAVA uses DUST ROWS ONLY") still say dust-only. A doc-compliance edit
  would silently change every CMY8 evidence value under the unchanged
  policy family. Code is the intended side; both docs owe amendments.
- **3.3 (color-upstream:03, correctness, minor)** The sparse-state repair
  (canonical first row moved across the parity split) is invisible to two
  consumers that reuse RAW parity: `_window_loss` (scores a
  moved-into-training row as held-out; primary owner-freeze sort key) and
  the registration anchor filter (admits a row moved out to held-out).
  Confined to the one-tile repair case; exact format labels; CRC downstream.
- **3.4 (color-payload:10 + engine-records:06, correctness, note)**
  `alpha0.8` is rendered into every durable attempt identity from
  `tiles.BP_ALPHA`, but no decode call (K or color) ever passes alpha — both
  ride `decode()`'s own default. Two unlinked constants must stay equal for
  attempt identities to describe the executed decoder. Non-semantic
  hardening: thread `alpha=tiles.BP_ALPHA` or assert equality.
- **3.5 (production-drivers:05, doc-vs-code, minor)** The color driver omits
  `payload.retry_complete` and the `payload.owner_frozen` snapshot required
  of every payload lane by §10.4.
- **3.6 (color-payload:11, doc-vs-code, note)** §7 certified pose refinement
  is codec-unscoped in the doc; the color payload stage has none. Record the
  scoping or schedule the port. EXECUTED v0.40 (plan 6.1, ruling 10.6): the
  port — `color_refine.py`, COLOR-INTEGRATION-DESIGN §5.5, policy
  `provisional-v6-refine`.
- **3.7 (fountain-close:06, doc-vs-code, note)** BlockStatus docstring says
  CMY7 leaves `stream_id` None; code labels CMY7 rows "main".

## 4. Doc-truth alignment (amendments owed; code is the right side unless noted)

- **4.1 (lens-doc-s6:01, major)** The shipped **D5 materialization**
  (d2e5281: `supersede_with_committed`/`apply_mopup_supersession`,
  evidence_blocks.py:517-556) is recorded NOWHERE normative: §6.1:570-573,
  the v0.33 row, and D5 all still state the strict validation-only contract,
  and §5b claims a complete deviation list that omits it. Substantively:
  (a) a mop-up observation at a committed cell — agreeing or DISAGREEING —
  is silently dropped (:544-545) with no counter, event, or divergence row
  (pre-materialization a disagreement crashed the barrier); (b) a
  non-superset colliding block is constructed into a superset instead of
  refused; (c) nothing-novel emits nothing. The barrier validator survives
  but is satisfied by construction. Owed: ledger row, D5 mechanism note,
  §5b entry, and a ruling (§11.2) whether discarded disagreeing
  observations should be counted/reported.
- **4.2 (session-payload:01, major)** §8 still lists deleted
  `session_replay.py` (:789), calls load "a full causal replay" (:839 — load
  is structural validation by the kiss-5 ruling), and retains "attempt
  records … divergence records" in the durable-state list (:866 — they fold
  to counters and are never persisted; requirement 5). A §8 implementer
  would persist forbidden ledgers. (HOLO-SOFTWARE-ARCHITECTURE.md:274/280
  stale too.)
- **4.3 (MR-01 = lens-efficiency:02, major)** PAYLOAD-MEASUREMENTS.md:143-144
  asserts a D8 certificate-conversion memo "per ProductionClose instance"
  that does not exist at HEAD or in any commit — the record's own
  "file:line-verified" charter is violated. Fix the sentence or build the
  (result-identical) memo. Also MR-02: the fountain knee pin drifted to
  fountain.py:15-16.
- **4.4 (evidence-blocks:03, minor)** The supersession validator is STRICTER
  than D5's "(mask and values)": it also requires exact per-committed-cell
  origin-row equality (evidence_blocks.py:512-514). Code right; text short.
  Sibling note (evidence-blocks:08): value agreement is numeric
  (`np.array_equal`), so a hand-built superseding block may flip a committed
  −0.0 to +0.0 (changing content address) — unreachable from production
  wiring; note for the doc.
- **4.5 (engine-records:02, minor)** §6.3 step 3 erases nonexistent
  "metadata sites" (K has none at erasure time) and the informative-bit
  floor's position differs from the listed order.
- **4.6 (lens-doc-s6:03 + color-payload:03, minor)** §6.4 says the color
  fork's four named files are "deleted"; all four exist as the shipped color
  modules (~1.76k lines) — the DOWNSTREAM fork was deleted, the files
  renamed roles. §6.4's BUILD STATUS also names `production._KPayloadLeaf`,
  which no longer exists. Sibling (color-payload:02, minor): §6.4's "exists
  exactly once" overstates — the one-owner freeze and the frontier→block
  converter exist twice (K + color) with near-verbatim group-by logic.
- **4.7 (engine-records:01 + production-drivers:06 + evidence-core:01,
  minor)** D18 recorded the `payload_engine.py` stale-comment fix as done;
  the comment still states the pre-v0.28 SCAN contract — now wrong twice
  (v0.28 + v0.33 evidence lanes).
- **4.8 (lens-doc-v33:04, minor)** PHASED-SCHEDULE D13 still says
  "`word_declared` rides the parked row"; D6 dropped the field (code agrees
  with D6).
- **4.9 (lens-doc-v33:05, minor)** D14c "rest sweeps report per-rotation"
  heartbeats are cold-only in code; unrecorded in §5b.
- **4.10 (session-payload:02, note)** D4's watermark refusal clause, read
  broadly, forbids the parked-ordinal re-use its own first clause mandates;
  code implements the sane narrow reading (freshly-minted ordinals only,
  parked excluded from the collision set, session.py:451-461). One
  clarifying sentence owed.
- **4.11 (lens-doc-s6:05/06, notes)** §6.3 attributes the certification
  chain + per-tile re-encode to tiles.py (enforced across engine/records);
  §6.1/§6.3's no-op and at-most-one-CRC rules read as if a durable
  spend-once ledger existed — attempt ledgers are deliberately
  invocation-local (recorded kiss ruling); determinism, not a ledger,
  delivers the intent on resume.
- **4.12 (lens-doc-s6:02, minor)** §6.1 "They consume only
  `AddressResult.payload_placements`" is stale post-D7 (label_placements is
  a second consumed input).
- **4.13 (production-drivers:08, note)** The K retry report conflates
  "eligible" with "attempted". (fountain-close:07, minor): the multistream
  rank-reserve generalization (16 + bit_length(B·n_streams − 1)) is live but
  absent from HOLO-DESIGN F8/§7.2. (evidence-blocks:09, note): §6.1
  "bounded float32 LLRs" is enforced at emission; block-boundary checks are
  finite-only. (MR-08, note): §1.1's "+22 s = labels + parked re-sampling"
  is interpretation, not measured decomposition; D7 label cost also recurs
  under mopup.payload; the timer seam itself is honest.
- **4.14 (lens-doc-v33:08, note)** The D15 parked-inventory epilogue is
  silently unavailable in discovery mode.

## 5. Dead code & rubble (deletion batch candidates; grep-verified zero
production callers unless noted)

- **5.1 The ScaleCascadeScheduler cluster (production-drivers:02 +
  refinement:05 + lens-dead:06 + lens-kiss:04, major)**: the pre-v0.33
  scheduler is exported dead code that **IndexErrors on the current doubled
  plan** (iterates the plan incl. M-entries but indexes `schedule.levels`,
  cascade.py:346-347) — and the slow qualification battery's restart case
  still drives it (_qualify_production_roundtrip.py:123/138): the resumed
  state was created under the cascade-composed policy id and must refuse at
  runtime.py:429-430, so **the slow qualification battery cannot pass
  post-v0.33** (fast suite never covered it). Also ~90-line
  ScaleRaster/ColorScaleRaster copy-paste. Contra the no-legacy ruling; not
  on the §5b deviation list.
- 5.2 Pre-unification/pre-KISS residue: `EvidenceDoctrineError` zero raise
  sites (evidence-core:02); `evidence.unresolved_stream_ids` duplicated by
  CertificateStore (evidence-core:03); `blocks_for_address` + both
  `stream_llr` methods test-only (evidence-blocks:06); two kiss-5-orphaned
  validators + a dead helper in session.py (session-payload:03);
  `ContextFit.apply`/`node_llrs`/`clamp` + triplicated clip kernel
  (detect-k:02); `SharedAffine`/`fit_shared_affine`/`ColorRegistration`
  test-only (color-upstream:04); `COLOR_DETECTOR_PROFILE`,
  `normalize_rgb`/`rgb_features` (color-upstream:05); unreachable
  best-anchor tie-break (color-upstream:06); three dead imports in
  color_divergence.py (color-payload:07); `CertificateStore.fork`,
  `tiles.CRC_FALSE_ACCEPT` (engine-records:03 + lens-dead:01/03 — the
  §10.7 CRC-accounting report it fed is unimplemented);
  `tiles.attempt_floor` re-implemented inline in both leaves, its diag
  parameter computed then del'ed (lens-dead:04);
  `records.attempt_view_from_record` (lens-dead:01);
  `tiles.CertificateIntegrityError` half-remaining from the TileCertificate
  era (lens-dead:02); CloseResult's seven convenience properties +
  `CertifiedStreamSymbol.address` (lens-dead:07); evidence-side dead symbols
  incl. a documented compatibility alias — contra "no shims"
  (lens-dead:08 + evidence-blocks:07); `SegmentRefinement.target_raw_means`
  (refinement:08); production-wiring-constant branches (PAVA collection
  mode, defaulted-None arms, `existing_ids`, no-op
  `deduplicate_divergences` wrapper — lens-dead:10); stale
  `-> TileCertificate` annotation in test_receive_close.py (lens-dead:11);
  `FormatSpec` annotated but never imported in production.py
  (production-drivers:09, supervisor-verified — latent under
  `from __future__ import annotations`).
- 5.3 Duplicated micro-helpers (lens-dead:12): `_stream_profile` clone,
  unreachable getattr default, **five copies** of the length-framed SHA
  framer.
- 5.4 Status corrections to RECEIVER-GROWTH-AUDIT (lens-dead:13 +
  session-payload:08): "close_count_ready unused by ProductionClose" is
  stale (D8 shipped it); the bottom-line K SCAN crash is fixed (9c9e66d).

## 6. Cycle waste — exact-preserving hoists (each needs its fixture)

Ranked by expected effect on the measured 532–550 s payload bucket
(PAYLOAD-MEASUREMENTS §1.3 — the largest numerical bucket on real color
material) and the close path:

- **6.1 (lens-efficiency:04, major)** K per-cell Python loops the color path
  already vectorized: `CaptureEvidence.__post_init__` per-cell validation
  (payload_model.py:341-353; color twin vectorized) paid up to 3× per K lane
  (gen-0, refined, prune-rebuild); `freeze_capture_evidence` per-cell dict
  (payload.py:150-171; color uses int64 keys + `np.unique`); shared per-row
  block encoding constant (evidence_blocks.py:837-840 + color rows) — the
  repo's own comment class measured these loops as having "dominated
  receiver time".
- **6.2 (lens-efficiency:03, major)** FOUR full certificate-set
  SHA-validation passes per color payload barrier (collect → restore_store →
  preclose → close), with preclose converting BEFORE its own emptiness check
  (production_color.py:287-293) — ~38.7k conversions over the 16-barrier
  real corpus. Fix: per-certificate_id memo (records immutable,
  content-addressed) + move the tuple after the emptiness short-circuit.
  Same family: MR-03 (fresh VolumeCode per count-gate consult, twice per
  stream), fountain-close:03 (gated barriers still pay O(C) conversion +
  repeated metadata GF(2) + VolumeCode), fountain-close:04
  (`_build_stream_decoder` validates every certificate once per stream — 3×
  on CMY8 closes).
- **6.3 (lens-efficiency:05, minor)** A parked-empty M-level still pays the
  full derived-raster materialization (~6.3 GB native read at 4800 dpi) —
  all four downstream consumers provably no-op (cascade.py:439 materializes
  before any stage can observe parked-emptiness).
- **6.4 (refinement:06, minor)** `refine_address_once` eagerly
  LDPC-re-encodes EVERY prior certificate at EVERY payload lane, before its
  own empty-domain early-out (certified_cascade.py:133/168); consumption is
  sparse — lazy per-consulted-address materialization is identity-preserving.
  Same kernel (engine-records:04, minor): `certificate_divergence`
  re-encodes the printed field once per (certificate, block) PAIR instead of
  once per certificate — 3-4 identical re-encodes per new certificate per
  barrier at the multi-scan knee.
- 6.5 Smaller confirmed hoists: `apply_region_context` per-cell Python
  tuple/dict physical ids — exact `np.unique`/`searchsorted` replacement
  (payload-windows:05); production always discards `fit_calibration`'s
  held-out loss and overrides `fit_context`'s adoption/losses — detect
  computes dead weight (detect-k:01 + lens-e023:03); double window crop +
  twice-computed ownership/split per color region (color-upstream:07); PAVA
  maps fit for planes the QDA guard zeroes (color-upstream:10); p120
  furniture geometry re-derived per call — no color analog of the K
  geometry caches (color-payload:04); divisor probe re-reads window crops,
  emission mask computed twice (color-payload:06); owner provenance
  replayed twice on immutable data (color-payload:05); interior
  re-verification on the hot attempt path (view double-sum + block
  double-hash + per-barrier cert re-validation — engine-records:05,
  overlaps growth-audit A4).
- 6.6 (lens-doc-s6:07, minor) The engine's advisory preclose is wired for
  color only: on a closing capture, K spends the full retry150 frontier of
  dead work the preclose would suppress. Faithful to history (policy ids
  differ); wiring K's preclose is a ruling-sized change (§11.6).
- 6.7 Growth-audit status refresh (lens-efficiency:06 + duplicates): rows
  1/2/4 FIXED in 9c9e66d (dead index deleted, lazy k-v1-only delta index,
  persist size prefilter); row 3 persist re-encode STILL OPEN — and the
  phased schedule doubled the barrier count, so its cost doubled; A3 triple
  SHA + double body serialization on load and A4 TileAttemptView double-sum
  STILL TRUE (anchors drifted ~+15 lines); A5 unchanged — the D8 gate does
  not gate the per-barrier `certificate_for_close` conversion.

## 7. Memory + re-authentication (the measured-record family; design-gated)

- **7.1 (MR-04 = lens-efficiency:01, major)** The +6.7 GiB phased peak-RSS
  delta ≈ ONE retained native mapping (6,496 MiB = 96.9%): the D10 pool
  holds BOTH captures' fully-touched 6.34 GiB TIFF mmaps for the whole
  invocation (runtime.py:455-496, no release path) while the capture-major
  baseline scoped one raster per capture (f3711ea `_run_capture` local).
  M-level re-materialization is per-visit-freed (≤1.6 GiB, both arms); D7
  label churn is window-scale. This CLOSES PAYLOAD-MEASUREMENTS §5 item 1
  analytically. Reductions (madvise-class residency hints, per-phase
  release+reopen) are exact-preserving but D10-gated (§11.7);
  `verify_source_unchanged` streams via buffered reads, not the mapping, so
  residency release cannot interact with the re-auth law.
- **7.2 (MR-05, major)** Of the two §5a-bis re-auth candidates, the
  stat-keyed memo (ii) touches scan.py only, reuses the stat tuple
  `open_capture` already computes and DISCARDS (scan.py:328/342-348), keeps
  a per-barrier detector, and saves ~267 s on the real corpus vs ~115 s for
  driver-advance batching (i), which leaves covered barriers detector-less.
  Caveat for the ruling: against a deliberate size+mtime_ns-forging rewrite,
  (ii) never detects while (i) detects late — dominance is not total across
  threat models. Both remain explicit-§8-amendment-gated; mutate-then-revert
  between barriers is missed by both AND by today's scheme.
- 7.3 Instruments (MR-06/MR-07, minor): payload-bucket decomposition via
  milestone wall-bucketing over the existing payload.* events (zero code
  for sampling+calibration+ctx / block build / BP+CRC split; two optional
  event details for the exact intra-region split); RSS attribution via a
  sampler thread + (capture, lane, stage) tag from the existing observe()
  callback — psutil is NOT in env and `memory_maps()` is unsupported on
  macOS, so the file-backed/anonymous split needs footprint/vmmap; the
  runner's `/2**20` is darwin-only-correct (Linux ru_maxrss is KiB).

## 8. Coverage gaps & battery debt (ranked by risk)

- **8.1 (evidence-blocks:01 + evidence-core:06, major)** The D5
  materialization layer — day-old code guarding committed-evidence
  integrity, whose collision path "no synthetic corpus reached" — has ZERO
  direct tests (only the validator is pinned). Failure modes are
  barrier-crash-class on real corpora mid-session.
- **8.2 (lens-coverage:02, major)** The 16-case runtime battery
  (`_qualify_runtime_fixtures.qualify_runtime` — re-auth refusal, source
  mutation, duplicate-capture no-op, SCAN-current-acquisition refusal
  directions…) has been orphaned from pytest since kiss commit e3026f1
  (underscore filename, __main__-only; no fast-test equivalents for the
  named guards). It was silently maintained through v0.33 — someone is
  paying its upkeep and nothing runs it.
- **8.3 (lens-coverage:03, major)** The D8 want_more shortfall baseline,
  rewound/foreign reset, and resume degradation have NO pins — the sole D8
  gate test never lets `close_volume` run, so `_note` never executes; even
  the measured runs never exercised the baseline (16/16 count-gated;
  synthetic verified at its single solve). A baseline defect would silently
  end a solvable session OPEN — the exact forfeit class the B-withdrawal
  analysis exists to prevent.
- **8.4 (lens-coverage:04, major)** The K one-owner freeze (compete-not-sum,
  heldout-then-ordinal) has no direct pin — the only test references build
  the EXPECTED side of byte-equality with the same function
  (differential-cancellation trap); color has a dedicated pin.
- **8.5 (lens-coverage:05 + detect-k:07, major)** detect.py — the
  self-declared numerical evidence boundary (calibrate-or-refuse floors,
  CTX_LLR_CLAMP, held-out strict improvement) — has no unit test file;
  every §6.2 K rule rides integration only; the measured-channel stress
  gate is slow-only.
- 8.6 (production-drivers:02) The slow qualification battery restart case is
  BROKEN post-v0.33 (§5.1) — the battery cannot pass; repair or re-scope.
  Sibling debt (lens-coverage:10): the 5-case roundtrip battery is
  slow-gated AND pathological (>20 min), so its unique pins never run.
- 8.7 (lens-coverage:06/07/08, minor) retry150's mandatory-schedule pin is
  slow-only; new-capture-new-frontier and the K cost-law negative are
  untested; D4 patch-ordinal collision refusal and all five parked-row
  structural load refusals unpinned; §7 adoption gate pinned only
  incidentally, K feedback ordering has no negative pin. Also
  session-payload:04, payload-windows:04, refinement:04 (v0.34 label-pooling
  arm has no differential test — folds into §12.1).
- 8.8 (lens-coverage:11, note) Payload null-battery blueprint (the E022
  49-null analog): surviving missing axes are payload-stage wrong-keystream
  nulls and state-tamper nulls; the sibling-coding null exists at the
  placement stage. (session-payload:05/06, notes: parked-lane accept/load
  asymmetry — save_session's default validation masks it; fresh-vs-fresh
  ordinal duplicates unenforced on conflict-free addresses — trust-boundary
  hole consistent with the kiss ruling, record as accepted or close.)
- 8.9 (engine-records:07, note) `record_attempt` ignores, rather than
  conflict-checks, a certificate at an already-certified work key —
  unreachable under production wiring (engine gates + barrier fatal);
  defense-in-depth observation.

## 9. KISS / rococo verdict

**The architecture is sound; the rubble is real but peripheral.** The
stream-generic engine (§6.4) held up under adversarial reading: one records
family, one identity/minting, one schedule, one close-input shape, one
divergence pairing loop — the fork deletion was genuine (with the two
recorded "exists twice" exceptions in 4.6). No unhealthy generic
abstractions, no protocol sprawl, no speculative generality were found in the
payload stage; the confirmed KISS findings are of the opposite, mundane kind
— residue, duplication, and two oversized files:

- **9.1 (lens-kiss:02 + production-drivers:04, major)** production.py is
  1250 lines vs the CLAUDE.md ≤1000 rule; `ProductionPayload.process` is
  ~278 lines/seven stages with nested closures; the mop-up/base address
  branches duplicate ~80 lines including a literal repeated
  callbacks-install triple, and address.final's 8-detail emission exists
  three times (verified not yet drifted). Clean seams exist:
  survey/address/payload/close are already class-bounded —
  `production_address.py` + `production_payload.py` is the natural split.
  Sibling: _payload_windows.py at 996 lines holds three concerns
  (sampling/calibration, context fit, refined reuse) with repeated
  parity/logloss boilerplate (payload-windows:07).
- 9.2 (lens-kiss:05, minor) Six unforced ducktyping/getattr-with-default
  sites where the typed record exists (engine's untyped decode return and
  bare `list` certificates; `_certificate_stream_id`'s dead "main" default
  on the validated type; close_progress parameter typing…). Also
  evidence-core:08 (bare-tuple mop-up surfaces).
- 9.3 (lens-kiss:09, minor) `BlockStatus` vs `CloseBlockProgress`:
  field-identical mirror dataclasses + a copy function (keep the stricter
  validation + `rank_shortfall` if merged).
- 9.4 (lens-kiss:07, minor) Interior defensive validation duplicated along
  single call paths (certified_addresses re-validated twice downstream of
  its mint; ~20-line isinstance preambles duplicated across the two
  samplers), contra the validation-boundary ruling.
- 9.5 (lens-kiss:08, minor) `collect_color_evidence`'s
  `fully_certified_addresses` parameter: the callee re-derives the only
  legal value and equality-checks it against the caller's — delete the
  parameter or trust it.
- 9.6 (lens-kiss:10 + color-upstream:08/09 + refinement:09 +
  evidence-core:05, notes) Merged trivia: constant `max(1,64)`, pointless
  if/else call fork, evidence-arity map ×3, PLANE_ORDER ×3, four
  read-only-array idioms, bare `pitch` names vs the units convention
  (breaches in _payload_windows and color paths), positional 17-arg
  constructions, per-cell `__post_init__` revalidation ×3 per lane.
- 9.7 (color-payload:09, note) `COLOR_PAYLOAD_POLICY_ID` derives part of its
  identity from a live constant — hand-bumped identity doctrine says spell
  it literally.

## 10. E023b/E023c divergence register (user question: "algorithmic
divergences from e023b/e023c")

The placement-audit's "functionally complete port" claim HOLDS at algorithm
granularity for the payload stage, with these confirmed divergences:

| # | Divergence | Status |
|---|---|---|
| 10.1 | Window-granular NeedMap skip in mixed regions (c7aa340) — historical E023b pooled ctx samples from ALL non-refused windows incl. certified-complete | **UNRECORDED** — only ruling is a commit message; §1 above |
| 10.2 | Score-path precision: holo computes median/spread/score arithmetic in float64 then quantizes to float32; legacy was float32-native end-to-end (detect-k:04 — reader's direction corrected by verifier) | note; PAVA rank-order effects only at ties |
| 10.3 | Manual two-branch sigmoid vs scipy expit in offset bisection — **measured NOT bit-identical**: 1-ulp differences on ~45% of negative inputs (detect-k:06) | note; convergence-tolerance-masked; unrecorded |
| 10.4 | detect.py's internal logloss/adoption verdicts are decorative — every production caller recomputes via the historical float path (lens-e023:03) | faithful-by-override; small dead work (6.5) |
| 10.5 | Cargo holdout stripes y-only (bx coefficient 9176 ≡ 0 mod 4) — historical quirk faithfully preserved (refinement:07) | faithful; note |
| 10.6 | No color §7 certified refinement (3.6) | EXECUTED v0.40 — ported (plan 6.1) |
| 10.7 | Scheduling-layer divergences (attempt identities, route labels, component inheritance) | RULED — D12 |
| 10.8 | BP150 role, retry eligibility chain, multiview-union-at-certificates, LLR lane isolation, one-vote-per-capture, E024 exclusion | PORTED-FAITHFUL (clean bill, 283 entries) |

## 11. Adjudication requests (rulings needed before any fix)

1. **The pool law** (§1): one statement covering pitch/filter-signature
   pool membership, placement fit-population granularity (window vs region),
   and label terminal-gating — binding gen-0, refined-reuse, replay, and
   M-levels equally. Decides payload-windows:01/02/03/09,
   refinement:01/02/03, detect-k:05, lens-e023:01.
2. **D5 disagreement disclosure** (4.1): should a mop-up observation that
   DISAGREES with a committed cell be counted/reported (divergence-style)
   rather than silently dropped?
3. **Color D7 scoping** (3.1): wire labels into the color fit/pitch, or
   record the exclusion in §5b + v0.34 and correct §5a-bis.
4. **§8.2 amendment** (1.1/10.1): adopt the window-granular cut into §8.2
   with its measured basis, or revert to the documented region-granular cut.
5. **D8 diagnostics repairs** (§2): the AttributeError wiring fix (2.1) is
   bug-fix-shaped; 2.2-2.4 need display-semantics decisions
   (deferred_counts marking on gated skips; --complete final-close gate
   passthrough; reproduction-path epilogue).
6. **K advisory preclose** (6.6): wire it (policy-id bump) or record the
   asymmetry as intended.
7. **D10 residency** (7.1) and the **§8 re-auth candidate** (7.2) — both
   explicit-amendment-gated; the review recommends (ii) with the
   threat-model caveat on the table.
8. **Battery repair** (8.2/8.6): re-wire qualify_runtime into pytest (or
   record its retirement); fix or re-scope the broken restart case +
   ScaleCascadeScheduler deletion (5.1).
9. **production.py / _payload_windows.py splits** (9.1) — mechanical,
   1000-line-rule-driven; approve the seams.
10. **Dead-code deletion batch** (§5.2-5.3) — one sweep, suite-green gated.
11. **BP_ALPHA threading** (3.4) — thread or assert; non-semantic.
12. **Doc-truth batch** (§4, remaining rows) — one amendment pass over
    RECEIVE-DESIGN §6/§8/§8.2 wording, PHASED-SCHEDULE D4/D13/D14c/§5b,
    PAYLOAD-MEASUREMENTS §3, COLOR-INTEGRATION-DESIGN:653,
    HOLO-DESIGN:1383, HOLO-SOFTWARE-ARCHITECTURE.

## 12. Measure-first gates (before building)

1. **Pooled-oracle fixture with terminal sets + refined path** — the gate
   for every §1 fix; today's oracle passes no terminal set, which is why
   the whole family shipped green.
2. **D5 materialization unit fixtures** (8.1) before any supersession-area
   change.
3. **Payload-bucket decomposition instrument** (7.3) before optimizing the
   532-550 s bucket (6.1/6.5) — per the profiling doctrine, single-decode
   harness, never pytest.
4. **RSS falsifier arm** (7.3): one A/B run with per-capture raster scoping
   restored confirms MR-04's attribution before any D10 amendment.
5. Every §6 hoist lands with its own result-exactness fixture (the
   cold-search hoist precedent).

## 13a. Rulings received (2026-08-01, SECOND user pass — adjudication
essentially complete; docs/PAYLOAD-REWORK-PLAN.md is the adopted execution
order)

- **§1 POOL LAW RESOLVED**: certified-complete windows in mixed regions do
  no payload work but become LABEL rows feeding the region fit ("mark as
  no-further-computation instead of deleting outright"); labels never
  terminal-gated in ANY path (the refined path's behavior was the right
  one; neither choice was ever substantiated/documented); zero-payload edge
  windows label-only always (delegated determination); pitch/signature pool
  identical in all paths ("fix it"); SAME LAW for K/CMY7/CMY8 (CMY8
  per-stream terminality nuance accepted); wholly-terminal regions still
  drop whole. Full L1–L6 statement in the plan, Phase 1.
- **SHA/identity RESOLVED**: format-level hashes keep; content-addressed
  identities keep (durable cross-process keys — Python id() ruled out by
  explanation; cheaper-hash migration not worth the identity churn);
  **recomputation on unchanged content: NEVER** (mint-once/store/trust);
  interior integrity via types/immutability/tests, not hashing.
- **Re-auth RESOLVED**: stat-memo candidate (ii) — "remember the fstat()
  block, be done"; §8 amendment in the same pass (plan 3.3).
- **Raster lifetime RESOLVED**: keep derived-lane memmaps for the whole
  invocation — "why re-derive?" (plan 3.4). RSS work deprioritized (7.3).
- **6.3/6.4/6.5/6.7 GO**; 6.4 with optional future blob-store paging.
- **6.6 GO**: K wires the same preclose code as color. Standing reminder
  re-affirmed: no backward compatibility, no shims, no legacy — version
  bumps are free.
- **10.2 GO — reversed from "keep"**: drop the float64 detour, go
  float32-native, re-pin ("pinned does not always mean good").
- **10.3 GO**: keep the manual sigmoid, document as canonical, verify used
  in all encodings.
- **10.5 GO**: adjust the holdout stripe coefficient for health unless
  archaeology finds a deliberate reason for the x-degenerate span.
- **10.6 GO**: color gets certified pose refinement too (plan 6.1).
- **11.2 UNDERSTOOD** (evidence-level, not certificate conflict): count the
  dropped disagreements; counts serve as a health canary; threshold
  doctrine post-08-04.
- **11.3 GO**: K/color divergence handling on shared paths as far as
  reasonable.
- **Tests RESOLVED** (section 5 + §8): full redesign — fast tests that do
  their job well + a few optional end-to-end/pathological cases with
  REASONABLE runtimes; pathological batteries retire, their guards port to
  fast pins (plan Phase 7).
- **retry150 timing**: question raised (defer until close-relevant?);
  disposition = wire K preclose first, measure residual retry spend, then
  decide tail-relocation (plan: Deferred).
- **User directive**: in-depth work plan REQUIRED before any execution
  ("we'd lose cohesion otherwise") → docs/PAYLOAD-REWORK-PLAN.md.

## 13. Rulings received (2026-08-01, first user pass — dialogue ongoing)

- **§9.1/9.2/9.3 GO** ("hammer time"): production.py + _payload_windows.py
  splits, ducktyping sweep, BlockStatus/CloseBlockProgress merge.
- **§9.4 GO, WIDENED**: interior-defensive-validation cleanup across ALL
  stages, not just payload ("even bigger hammer time").
- **§9.5 GO**: trust the `fully_certified_addresses` parameter (delete the
  re-derive-and-compare).
- **§9.6/9.7 GO**: trivia batch + policy-id literal.
- **§6.5 agreed**: algorithmic clarity first, then major cleanup.
- **§8 agreed in principle**: clean, comprehensive new test strategy (reuse
  some, rework others, trash some) AFTER the payload stage is understood and
  cleaned up. Slow-battery retirement question OPEN (user leaning retire).
- **§6.2/6.7 direction**: kill SHA recomputation throughout; user challenges
  hashing as an interior integrity mechanism entirely ("the code is not
  adversarial") — final shape pending the boundary-vs-interior explanation.
- **§1 pool law explicitly DEFERRED**: user cannot rule yet ("don't
  understand the space well enough"); explanatory pass owed and delivered in
  session; user's working hypothesis: certified-window skip is right, labels
  question open.
- EXECUTION SEQUENCING NOTE: the GO items above touch the same functions the
  §1 ruling will edit (production.py, _payload_windows.py); execution ordered
  after the pool-law + SHA rulings land to avoid double refactoring.

## Ranking (expected value, 2026-08-01 view)

1. §2.1 diagnostics crash fix — smallest fix, restores D15/D16 epilogues and
   all --diag snapshots on gated barriers (every real-corpus barrier today).
2. §1 pool-law ruling + fixture — the only family with silent cross-pass
   numerical divergence and a fail-closed brick on the production path.
3. §8.1-8.5 coverage batch — D5 materialization, orphaned runtime battery,
   D8 baseline, K one-owner, detect.py; cheap tests, all guarding
   crash/forfeit-class defects.
4. §6.1/6.2 hoists — the measured payload bucket and close path; exactness
   fixtures required.
5. §4 doc-truth batch + §5 deletion batch — reading-burden and
   record-integrity; zero numerical risk.
6. §7 memory/re-auth — biggest wall/RSS wins on real corpora, but both
   design-gated; instruments first.
