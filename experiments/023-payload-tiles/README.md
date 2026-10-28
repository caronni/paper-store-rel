# Experiment 023 - PAYLOAD TILE DECODING on the e022 pose foundation

**Status: BUILT + QUALIFIED 2026-07-15 (both pre-registered gates PASS on
BOTH footings — section 7). Design converged 2026-07-14 after FOUR review
rounds: round 1 (findings F1-F8, section 6.1; the F1 seam fix — e022 v2.2
records redundant placements — implemented and tested), round 2 (external
review, findings R1-R7 + an E023.0 recommendation list, section 6.2),
round 3 (detector simplification: single-arm PAVA, calibrate-or-refuse,
context-binned-PAVA contingency, section 6.3), round 4 (contract
precision: score convention, gate denominator 641, attempt-floor rename,
persistence/diagnostic seams, section 6.4).**
Converged in the design session recorded in `docs/REASONING-LOG.md`
(Session 2026-07-14, e023 design + review rounds); this README is the
normative experiment design. Decoder-axis only, zero print, no format
change (no layout_version bump).

Deliverable: for every LDPC tile with enough placed coverage, decoded and
CRC-certified payload bits, plus honest measurement of what certified and
why. NOT volume recovery: no fountain-symbol accounting, no rank checks, no
feedback loop (the substrate for the later loop is recorded, the loop is
not built).

E022 answers "where does each region lie in a legal page's pilot field, and
what local map samples its cells from the original scan?" E023 answers:

> Which LDPC tiles can be decoded correctly from the payload cells those
> poses reach, and how do we know without ground truth?

## 1. Design decisions (converged)

- **Inputs: original scans + e022 session state only; the recorded core is
  AUTHORITATIVE (R1).** Poses are full-scan subpixel maps;
  `PlacedWindow.page_cells_yx` is the audited eroded core, and e023 makes
  no mask policy of its own — no erode-depth knob, no ablation (depths
  below e022's erode-2 are unreachable from the state anyway). Caveat
  stated, not hidden: `pilotsearch._core` FALLS BACK to the un-eroded mask
  when erosion would empty it, so "every recorded cell is >= 2 cells
  interior" is not universal — thin-sliver windows can emit mask-edge
  cells whose prefilter reads include backing. Bounded (rare windows, few
  cells), CRC-guarded, and MEASURED in qualification: the rim-distance-
  conditioned BER report (vs GT) stays as a diagnostic that would inform
  any future e022 mask-policy change. No E021 re-run, no region masks
  otherwise: the sampling prefilter (aperture ~0.7 cell) cannot reach an
  eroded-core cell. Scans located via the state's `source_path`, verified
  by `source_sha256`.
  **(F1) e023 consumes ALL gated poses, including `redundant=True`
  placements** — payload need != pilot need; a window whose pilot sites
  were all already observed still carries payload coverage. e022 v2.2
  records those placements (pose + audited core, pilot emission
  suppressed, `STATE_VERSION` 3); pre-v2.2 states are an incomplete input
  and refuse.
- **Sampling = e022's own mechanism extended to payload cells (F4):** one
  `uniform_filter` prefilter per (scan, region-extent bbox) — the extent is
  the union of that region's pose-mapped window corners, no e021 mask
  needed — then one order-1 read per pose-mapped core cell
  (`AffinePose.points`), native footing, nothing resampled. The
  window-local core mask is rebuilt by inverting `rot_k`+origin from
  `page_cells_yx`.
- **Detector (S4 simplified per F3, calibration hardened per R2,
  single-arm per round 3, score pinned per round 4):** ONE detector, no
  A/B. The score is INK-POSITIVE and exactly specified:
  `score = (mid - cell_mean) / robust_spread` per window (window-median
  `mid` and spread over core cells — the e022 `sample_window` convention;
  increasing score = increasing P(bit=1), matching `pava_calibrate`).
  The spread division is itself convention-only: within a window it is a
  strictly monotone transform, so the calibrated output is unchanged —
  kept for e022 parity and cross-window diagnostics. Score ->
  **per-window PAVA calibration on search-parity pilot labels**
  (`acquire.pava_calibrate`/`apply_calibration` — the measured house
  method, ln(n+1) self-clamp) -> held-out honesty check (log-loss) on the
  disjoint validation parity. The previously planned Gaussian-LLR-as-score
  A/B arm is DELETED: monotone score transforms preserve PAVA's ordering
  and block structure (the round-4 correction: the mean-node + np.interp
  implementation does NOT exactly preserve interpolated probabilities, so
  the arms are near- but not mathematically identical), and the only
  systematic difference the Gaussian arm could add is its
  unequal-variance quadratic tails — exactly the model region R2
  distrusts. Direct darkness + PAVA is the simpler arm and keeps it.
  Emit bounded LLRs (LAYERS section 1 invariant). **Calibrate-or-refuse** (no
  below-floor down-scaling mode): a window whose search parity cannot
  populate both classes with ~10+ labels (constant frozen at build with
  its fixture) REFUSES emission — counted, erasures. The down-scaling
  rule was `acquire`'s compromise for zero-label word windows; e023
  windows carry >= 60-135 labels by construction of placement, so a
  label-starved window is pathological and refusal is the honest mode.
  Cross-window label pooling stays a CONTINGENCY; sub-placement slivers
  are retry-ledger / feedback clientele and are counted in the report.
  Descramble via the payload keystream (`compose` payload index map;
  GT-via-gen-module rule, 012.3). CONTINGENCY if the yield gate fails on
  detection grounds (round 3, replacing the vague "ctx at locked
  geometry" lever): **context-binned PAVA** — bin cells by ink-neighbor
  count from the window's own hard bits, pool labels per (scan, region)
  within bins, one isotonic map per bin (ctx+PAVA reduced to its actual
  content, context-conditional calibration, with no GMM/ICM port; 014.2
  precedent "per-context PAVA"). Decision instrument: the qualification
  report's context-conditioned error breakdown (below).
- **BCH = evidence + a FAIL-CLOSED INPUT-INTEGRITY PRECONDITION (F6/R5,
  renamed per round 4):** never a gate or weight on emission (one-way
  doctrine); refused/unattempted reads do nothing. `bch_ok` is a per-TILE
  verdict aggregated across windows and scans, so no "offending window"
  is identifiable — a contradictory decoded address at a placed position
  violates e022's qualified invariant (0 contradictions in ~1,780 reads)
  and aborts the run with a loud flag. Not mathematical proof of a bad
  pose; a precision-conservative fail-closed precondition on the input
  state.
- **Merge policy (F2 — the 013-measured doctrine, staged; owner metric
  per R2/E023.0):** within a scan, per cell, ONE vote — the covering
  window with the best held-out calibration quality, scored by
  validation-parity LOG-LOSS (hard wrong-rate is heavily tied at 60-135
  sites; PAVA supplies the probabilities). Across scans, STAGED:
  (1) decode each tile from each scan's own evidence and take any
  CRC-certified result (tile-level union — 013 measured it strictly
  beating naive LLR summation under a global detector); (2) only for
  tiles no scan certifies alone, attempt the cross-scan sum of calibrated
  LLRs; (3) the sum-vs-best ablation decides whether stage 2 earns
  permanence. HONESTY ACCOUNTING (E023.0-5): every decode attempt spends
  CRC false-accept budget — record the multiplied exposure
  (attempts x 2^-32) in the report; two CONFLICTING certifications of one
  tile are a fatal integrity event.
- **Decode scheduling (gate per E023.0-4, renamed per round 4):**
  tile-granular by construction (codeword = the 64x64 page tile via
  `ldpc.tile_shorten_mask`/`gather_tile_llrs`/`decode_tile`, missing cells
  = erasures, CRC-32 certifies). Attempt touched tiles after each scan's
  emission (live pane advances), full sweep at the end; failed tiles
  retried only when new observations arrive (monotone accumulation, no
  feedback loop). The only decode gate is the **ATTEMPT FLOOR
  n_informative >= k_eff**, computed BEFORE decoding from the shorten
  mask + nonzero-LLR count (not from the post-decode `TileResult`). It is
  a conservative floor, not a strict information bound — the CRC leaves
  the framed message k_eff - 32 degrees of freedom (on the completed
  decimated state the distinction decides nothing: 793 payload-bearing
  tiles clear both candidate floors, 12 clear neither — reviewer
  computation, round 4). The corresponding tile state is
  `below_attempt_floor`. The channel frontier — r0550's zero-BER erasure
  floor is ~55% coverage; the measured ~70% (013 F4) included ~3% BER on
  covered cells (coverage x (1 - h(p)) >= R) — is a DIAGNOSTIC/
  prediction, never a gate; e023 re-measures the coverage/certification
  curve on the real channel. Registered OPTIONAL
  item (from the RS-vs-LDPC challenge, 2026-07-14): a Gaussian-elimination
  erasure fallback for erasure-dominant tiles (BP first; GE on erasures
  treating observed hard bits as correct; CRC still the certificate) —
  build only if the measured curve shows a BP-vs-elimination gap near the
  floor. Code-family swaps (Reed-Solomon per tile) are answered by
  arithmetic in the log: hard-decision symbol-error inflation + the 2e+f
  half-distance tax price RS out at our BER; MDS erasure optimality
  already lives at the fountain layer.
- **Feedback substrate (recorded now, loop later; terminology per
  E023.0-6, wording per round 4):** per certified tile store the decoded
  **user payload bits + rate** + provenance (contributing scans/windows,
  iterations, coverage) — re-encoding determines all LOGICAL codeword
  bits; the physical feedback field maps the non-shortened slots through
  `_tile_payload_indices` (+ keystream), regenerates pilot cells
  independently from the seed, and ignores off-page slots. Never stored
  as pseudo-LLRs. Observations stay
  immutable (certification never overwrites; the F9 overlay lesson); raw
  sample means regenerate exactly from scans + poses. Substrate for the
  later loop = e022 state (poses, retry ledger) + e023 state
  (observations, certified payload bits). R7 limitation, stated:
  unresolved windows persist their best losing HYPOTHESIS (retry ledger),
  not a replayable pose — by design, since the section-9 retry
  re-invokes e022 and refits poses under the new constraints. Loop
  edges deferred, in value order: dense-certified-field placement of
  sub-floor slivers (~36x denser reference than the 2.8% pilot field);
  detector/pose refit on certified labels (repass family, F10/F15);
  partial-BCH errors-and-erasures confirmations at predicted addresses
  (quantified-FA yes/no on retry-ledger hypotheses, not a label source);
  F8 turbo behind the certified-only firewall (R1: only CRC-certified
  values feed back — uncertified beliefs never do).
- **Multi-page by construction:** all keys `(page, tile_y, tile_x)`,
  per-page LDPC rate lookup, legal page set from the e022 state envelope
  (e022 pages param, four-page battery; 016 page axis 0/40 wrong).
  Qualified single-page (e018) — the only real-scan substrate.
- **c-independent, single-level K-binary (F8):** everything parameterized
  by `FormatDescriptor` (`cell_dots`, spec, seed). **(F5) the LDPC rate is
  a format fact and lives on the registry row** (`ldpc_rate`, e018-v3-c3 ->
  r0550); a `--rate` CLI override exists for experiments only (a wrong
  rate silently certifies nothing — not a footgun to leave on a required
  flag). Scope: single-level K-binary formats in v1; the color v4 path
  (levels, dust training) is a later arm with its own detector story.
  Qualified against c3 like e022; e016-v3-c2 is a later arm.

## 2. Asks and preconditions

Preconditions:

- **e022 v2.2 session states (STATE_VERSION 3), BOTH footings** — the F1
  seam fix means the pre-existing STATE_VERSION-2 pickles are an
  incomplete e023 input (their redundant poses were never captured) and
  refuse cleanly. Both six-scan sessions must be re-run under v2.2
  (~5-10 min per footing, read-only over scans); the old decimated state
  (`build/session_state.pkl`, 121.7 MB, 6 scans, 925 tiles) remains the
  comparison record.
- All 12 e018 scans on disk (`scratch/e018/`): 6 native 4800 + 6 decimated
  1600 (verified 2026-07-14). Scans must stay at their recorded
  `source_path`s (or the driver grows a `--scan-root` remap — only if
  needed).
- Qualification GT: `experiments/018-confetti-c3-play/build/e018_gt/`
  (rendered field + manifest) — never regenerated from live gen code
  (the 018.7 drift rule).
- Frozen dependencies: `ldpc`/`pilots`/`place`/`compose` untouched
  (decoder-axis only); `pilotsearch` change limited to the v2.2 recording
  amendment; suite green.
- Zero print, zero scan — no hardware involvement; compute-only
  qualification. Build artifacts stay git-ignored.

Asks (user):

1. DONE (launched 2026-07-14 on user instruction, old v2 states cleared):
   the two v2.2 session re-runs — six decimated scans ->
   `build/session_state.pkl`, six native scans ->
   `build/session_native.pkl`. Record their numbers here when they land.
2. Module name `paperholo.payloaddec` unless another is preferred.

## 3. Deliverables

- `src/paperholo/payloaddec.py`: thin e023 aggregator — per-(scan, window)
  sampling + calibration + emission records with pose/window provenance;
  per-tile LLR union; `ldpc` decode + CRC; `TileOutcome` with the HONEST
  state set (R4, floor renamed round 4): `unobserved / below_attempt_floor
  / attempted_failed / certified / degenerate` — no "margin"/"marginal"
  (the codec exposes syndrome/CRC/iterations/n_measured/n_erased, NOT a
  posterior margin; "marginal" exists only in GT-based qualification
  analysis; margin exposure = optional later codec extension). Versioned
  state, refuses mismatched format/seed/pages/dpi (mirrors the
  `session_e022.py` envelope). Reuse at PRIMITIVE boundaries (R6):
  `ldpc.gather_tile_llrs`/`decode_tile`/`tile_shorten_mask` + the
  re-encode/known-cell primitives + `acquire.pava_calibrate`; NOT
  adopted: `tilemap.PageDecodeState` policy machinery (BCH-shaped merge
  weights, acquire-shaped observations; the staged per-scan-first policy
  does not fit its merge model, and two state machines feeding one
  decode is the mixed-provenance trap).
- `experiments/023-payload-tiles/run_e023.py`: consumes an e022 state
  (`--e022-state`), re-reads scans, emits + decodes incrementally, writes a
  JSON report + PNG; resumable e023 state. **`--diag [DIR]`** (default
  `build/session_diag`, port 8023) serves a localhost auto-refreshing view
  and writes numbered PNG frames after each ingested scan (+ union frame);
  read-only observer (`tests/test_e023_diag.py`).
- **Pane D**: LDPC tile map in the R4 states (`unobserved /
  below_attempt_floor / attempted_failed / certified / degenerate`), plus
  per-window payload-BER-vs-pilot-BER in the report; live diag via
  `e023_diag.py` (shipped 2026-07-15; additive, byte-identity preserved).
  Diagnostic-input seam (round 4): e023's own renderer draws the
  PAGE-SPACE panes (placements / pilot map / LDPC map) from state alone;
  the scan-space pane needs an E021 `PayloadSurvey`, which the e022 state
  does not retain — optional observer-only E021 replay if ever wanted,
  never a dependency.
- Measurement (the success bar, made NON-VACUOUS per R3; denominator
  pinned per round 4 and VERIFIED on the frozen state):
  **(a) zero wrong certifications** (GT audit vs `e018_gt`, qualification
  scaffolding only — never in the decode path);
  **(b) yield gate: >= 95% certification of the NONDEGENERATE tiles with
  >= 95% GEOMETRIC coverage on the frozen v2.2 decimated six-scan state —
  the denominator is 641 tiles** (geometric = pre-detector e022 core
  coverage of non-shortened slots; excludes the 35
  `tile_user_capacity == 0` degenerate tiles — 647 would wrongly include
  6 high-coverage degenerate ones; numbers independently recomputed
  2026-07-14). Coverage classes kept distinct throughout: GEOMETRIC
  (recorded core), EMITTED (post calibrate-or-refuse), INFORMATIVE
  (LLR != 0 at gather). Those tiles must decode: 016.2 measured 88.2%
  yield at the same rate on a channel ~3x worse (c2 at ~8.6% BER vs c3
  at 2-3%). Partial-coverage tiles are the frontier MEASUREMENT
  (coverage-vs-certification curve at r0550), reported, not gated.
  Comparison row, not a gate: the e018 receiver's 532 certified tiles
  (includes repass = the feedback loop e023 v1 deliberately lacks).
  Self-contained instruments first (production has no GT): syndrome + CRC
  together as the only certificate (013 measured why syndrome alone is
  not one); the divergence alarm (F8) = post-certification payload BER
  against certified values vs the pilot estimate; held-out calibration
  honesty (validation-parity log-loss); iterations + coverage accounting;
  CRC attempt-budget ledger; fatal-alarm flags. Plus the staged-merge
  ablation (stage-1 union vs cross-scan sum vs best-single), the
  CORE-EDGE-distance-conditioned BER diagnostic (R1; renamed round 4 —
  true scrap-rim distance would need the E021 mask the e022 state does
  not retain; core-edge distance is computable from placements alone and
  is the quantity that actually bounds the `_core`-fallback bleed), the
  CONTEXT-CONDITIONED error breakdown vs GT (round 3 — errors grouped by
  ink-neighbor count; the decision instrument for the context-binned-PAVA
  contingency), and the unresolved-sliver census (the feedback loop's
  clientele), on both footings' six-scan states.
- Tests (F7): primary fixtures construct a SYNTHETIC e022 STATE directly
  (known poses over a rendered page — pinning the ink-positive score
  convention, the keystream flip, and the slot-raster mapping byte-exact,
  the 012.3 incident class) — plus exactly ONE full-chain
  render -> e021 -> e022 -> e023 integration test. Unit tests:
  calibrate-or-refuse, the fail-closed contradiction abort, state
  envelope refusal (incl. STATE_VERSION 2 refusal), attempt-floor
  computed pre-decode, determinism. `qualify_e023.py` +
  README/DESIGN-NOTES updates per e022 convention.
- Persistence seam (round 4, minimal): distinct `--e022-state` (input,
  read-only) and `--state` (e023's own) arguments; the e023 state stores
  an ORDERED fingerprint of the upstream scans/results; resume =
  unchanged-prefix + append-only; any upstream mutation or reordering
  requires `--fresh`.

## 4. Key files leveraged

- `src/paperholo/pilotsearch.py` — `AffinePose`,
  `PlacedWindow.page_cells_yx`, `PilotTileEvidence`, `_rotated_points`
  inversion, sampling precedent (`prepare_region`/`sample_window`).
- `src/paperholo/ldpc.py` — untouched codec: shorten mask,
  `gather_tile_llrs` (0 = erasure), `decode_tile` (syndrome + CRC,
  `TileResult` with `n_measured`/`n_erased`/`n_iters`), rate ladder,
  re-encode.
- `src/paperholo/acquire.py` — `pava_calibrate`/`apply_calibration` (the
  isotonic house calibration, ln(n+1) self-clamp) reused at the primitive
  boundary.
- `experiments/022-pilot-tile-search/session_e022.py` — state envelope +
  `combine_results` provenance model to mirror.
- `compose` / `place.pilot_field` — payload index map, keystream signs,
  expected pilot labels.

## 5. Build order

0. DONE (F1): e022 v2.2 amendment — redundant placements recorded with
   full poses/cores, pilot emission suppressed, `redundant` region state,
   `STATE_VERSION` 3; tests extended. Session re-runs pending (ask 1).
1. `payloaddec` module: e023 state schema + pose-driven native sampling
   of audited-core cells (haloed region-extent prefilter + order-1 reads;
   core mask from `page_cells_yx` inversion; redundant placements
   included; recorded core authoritative).
2. Per-window detector + calibration: window mean -> PAVA on
   search-parity labels (validation-parity held-out log-loss), bounded
   LLRs, CALIBRATE-OR-REFUSE (no down-scaling mode, no A/B arm),
   keystream descramble.
3. Per-scan one-vote reduce (log-loss owner); STAGED decode (per-scan
   tile union first, cross-scan sum for stragglers; n_measured >= k_eff
   as the only gate; CRC attempt-budget ledger; conflicting
   certifications fatal); per-tile ldpc gather/decode/CRC with
   `TileOutcome` R4 states + certified USER PAYLOAD BITS + rate (feedback
   substrate); contradiction = fatal integrity alarm; touched-tile
   scheduling with retry-on-new-evidence.
4. `run_e023.py`: consume e022 state + sha-verified scans, incremental
   per-scan decode, resumable e023 state, JSON report; `ldpc_rate` from
   the format registry.
5. Pane D LDPC tile map (R4 states) in the e022 renderer + live diag
   observer integration.
6. Fixtures per F7: synthetic-e022-state unit fixtures (score-convention/
   keystream/slot-raster pins, calibrate-or-refuse, fail-closed
   contradiction abort, envelope refusal, pre-decode attempt floor,
   determinism) + one full-chain integration test.
7. `qualify_e023.py` on both v2.2 six-scan states: the two pre-registered
   gates (zero wrong certifications; >= 95% certification of the 641
   nondegenerate >= 95%-geometric-coverage tiles, frozen decimated
   state), coverage/certification curve, calibration honesty (held-out
   log-loss), staged-merge ablation, core-edge BER diagnostic,
   context-conditioned error breakdown, unresolved-sliver census;
   README + results log.

## 6. Design-review record (2026-07-14, pre-build)

### 6.1 Round 1 (F1-F8)

Adversarial review of this design against e021/e022, the measured record,
and the legacy receiver. Findings, all folded into the sections above:

- **F1 (defect, fixed):** `redundant_skipped` windows were gated
  placements whose poses were dropped — a payload-coverage hole (payload
  need != pilot need; single-scan sessions have no second chance). Fixed
  as e022 v2.2 + STATE_VERSION 3.
- **F2 (measured-record conflict):** defaulting to cross-scan LLR
  summation contradicted 013 (tile-level union strictly beat summation
  under a global detector; 014.2's sum-wins regime required ctx
  de-correlation). Default is now the staged policy.
- **F3 (over-engineering):** the 3-level hierarchical calibration
  defended a case the placement floor already excludes; reduced to one
  below-floor down-scaling rule, pooling demoted to contingency.
- **F4 (simplification):** prefilter per (scan, region-extent), not per
  window — fewer filters, exact e022 radiometric parity.
- **F5 (footgun):** LDPC rate moved from required CLI knob to the format
  registry row.
- **F6 (minimalism):** BCH-contradiction handling reduced to one branch
  (exclude + loud alarm), no state machinery for a 0-in-1,780 event.
- **F7 (test strategy):** synthetic-e022-state fixtures primary, one
  full-chain integration test — pins the sign/keystream/slot-raster
  classes without coupling every test to two upstream stages.
- **F8 (honesty):** scope stated as single-level K-binary; the divergence
  alarm defined post-certification (payload BER is not observable blind);
  the erode ablation acknowledged as one-sided (below erode-2
  unreachable from the state). (Superseded by R1: the ablation is now
  deleted entirely; the recorded core is authoritative.)

### 6.2 Round 2 (external review R1-R7 + E023.0 list; reviewed the
pre-round-1 commit d26beef — some findings arrived already fixed)

Reviewer audit numbers VERIFIED against the retained v2.1 decimated
state: 51 redundant-skipped windows, 96.1% accepted-core page coverage
(exact matches; all 840 LDPC tiles touched — own re-audit); the 828/840
n_measured >= k_eff figure is plausible and will be recomputed exactly by
the k_eff gate at build time.

- **R1 (High, ADOPTED — new catch):** the erosion contract was
  internally inconsistent: e023 consumed the already-eroded core yet
  proposed its own depth ablation, and `pilotsearch._core` falls back to
  the UN-eroded mask when erosion empties it, so ">= 2 cells interior" is
  not universal. Recorded core now authoritative; ablation deleted;
  rim-distance BER kept as a GT diagnostic only; fallback caveat stated.
- **R2 (High, ADOPTED):** bounded Gaussian model scores are not
  calibrated LLRs; plain summation was not justified by them. Detector
  path is now score -> per-window PAVA (the measured house calibration)
  -> held-out honesty; Gaussian-as-score = A/B arm. (The summation half
  had already been fixed by F2's staged policy.)
- **R3 (High, ADOPTED — sharpest catch):** "zero wrong certifications" +
  "certified == GT" is vacuously satisfiable by certifying nothing. Two
  pre-registered gates added: zero wrong certifications AND >= 95%
  certification on >= 95%-coverage tiles of the frozen decimated state
  (anchored on 016.2: 88.2% yield at the same rate on a ~3x worse
  channel). e018's 532 certified tiles = comparison row, not a gate
  (includes repass).
- **R4 (Medium, ADOPTED):** no posterior margin exists in `TileResult`;
  "margin/marginal" removed from v1; honest state set adopted
  (`unobserved / below_information_floor / attempted_failed / certified /
  degenerate`); "marginal" is GT-qualification vocabulary only.
- **R5 (Medium, ADOPTED):** `bch_ok` is per-tile aggregated — no window
  attribution exists, so F6's "exclude that window" was unimplementable.
  Contradiction = fatal e022-state integrity alarm; refusals do nothing.
- **R6 (Medium, ADOPTED as clarification):** reuse at primitive
  boundaries (`gather_tile_llrs`/`decode_tile`/re-encode/
  `pava_calibrate`); the thin-decoder option IS the design;
  `PageDecodeState` policy machinery stays out (staged per-scan-first
  does not fit its merge model; two state machines feeding one decode =
  the mixed-provenance trap).
- **R7 (Medium, half fixed / half push-back):** the "redundant candidates
  discarded" half was already fixed as e022 v2.2 (round 1 F1; the
  reviewer's 51-window audit confirms the magnitude). On persisting
  unresolved-window poses: NOT adopted — the section-9 retry re-invokes
  e022 and refits poses under new constraints by design; the retry ledger
  keeps the losing hypothesis, which is what a revisit needs. Stated as a
  limitation, no further STATE_VERSION bump.
- **E023.0 list:** adopted — haloed group crops (= F4), held-out
  log-loss owner selection (wrong-rate is tie-heavy at 60-135 sites),
  n_measured >= k_eff as the only decode gate (frontier expression
  demoted to diagnostic), CRC attempt-budget ledger + conflicting
  certifications fatal, "certified user payload bits + rate" terminology
  (re-encode regenerates codeword + CRC). "Accepted cores only" is
  superseded by v2.2 (redundant cores are equally gated and included).

### 6.3 Round 3 (user prompt: does ctx+PAVA fit? cleaner than an A/B?)

- **A/B arm DELETED by invariance:** isotonic (PAVA) calibration is
  invariant under strictly monotone transforms of the score axis, and the
  1-D 2-class Gaussian LLR is monotone in the window mean between the
  class means — the two arms could differ only through the
  unequal-variance quadratic TAILS, exactly the model region R2 already
  ruled untrustworthy. The A/B would have measured a distinction the
  design is committed to ignoring. One detector: window mean ->
  per-window PAVA.
- **Calibrate-or-refuse:** the below-floor down-scaling rule deleted —
  it was `acquire`'s compromise for zero-label word windows; e023
  windows carry labels by construction, so a label-starved window
  refuses (counted) instead of emitting through a second mode.
- **ctx+PAVA judged against the need:** its measured value is
  context-bias-dominated channels (c2 at fine sampling: 014.2 3.5x,
  e016 8.6% -> 2.1-4.9%); e023 v1 is c3 at subpixel poses where global
  detection measured 0.64-3.97% blind (012.3) and much of the residual
  is print-frozen terminal closure no detector recovers. Porting ctx
  would primarily import GMM/ICM + mask-handling complexity (round-4
  correction: not physical rectification per se) — including the
  uncalibrated-GMM score family round 2 removed. Contingency reworded to
  **context-binned PAVA** (ink-neighbor-count bins, labels pooled per
  (scan, region) within bins — 014.2's REGISTERED-not-measured
  "per-context PAVA"), triggered only if the yield gate fails on
  detection grounds AND the new context-conditioned error breakdown
  shows context-concentrated misses.

### 6.4 Round 4 (external re-review of the converged design): contract
precision, no design changes — CONVERGED

The reviewer's own verdict: "the staged E023 algorithm is elegant and
implementable as designed"; remaining items are wording/contract
precision. All adopted; state-audit numbers independently recomputed and
CONFIRMED (840 tiles: 35 degenerate, 641 nondegenerate at >= 95%
geometric coverage, 647 if the 6 high-coverage degenerate tiles were
wrongly included).

- **Score convention pinned:** `score = (mid - cell_mean) /
  robust_spread`, ink-positive, e022/`pava_calibrate` parity (the spread
  division is convention-only within a window — monotone, calibration
  unchanged).
- **PAVA rationale corrected:** monotone transforms preserve ordering and
  block structure but the mean-node + np.interp map is not exactly
  invariant (round 3's "identical at label points" overstated); the
  Gaussian-arm deletion stands on simplicity + distrusted tails.
- **Yield-gate denominator pinned:** 641 nondegenerate >= 95%-geometric-
  coverage tiles; geometric/emitted/informative coverage kept distinct.
- **Attempt floor renamed + pre-decode:** n_informative >= k_eff is a
  conservative attempt floor (CRC leaves k_eff - 32 degrees of freedom),
  computed from mask + nonzero LLRs BEFORE decode; state
  `below_attempt_floor`; decides nothing on the real state (793 clear
  both candidate floors, 12 neither — reviewer computation).
- **Persistence seam:** --e022-state vs --state, ordered upstream
  fingerprint, unchanged-prefix append-only resume, --fresh on mutation.
- **Diagnostic seam:** true scrap-rim distance needs the E021 survey the
  e022 state does not retain -> metric renamed CORE-EDGE distance
  (computable from placements; the quantity that actually bounds the
  `_core`-fallback bleed); e023 renders page-space panes only.
- **Renames/wording:** BCH contradiction = fail-closed input-integrity
  precondition (not "diagnostics only"); "all 4096 cells" ->
  logical-codeword wording; ctx-porting cost = GMM/ICM + mask complexity;
  two stale test descriptions fixed.
- **Reviewer retractions accepted:** PAVA-refit-on-all-labels withdrawn
  (search/validation split stands; no label-starved placements exist:
  min search-class count 16 decimated / 13 native); no first/second-take
  split for E023.0 (context-binned PAVA, if ever built, = E023.1 with
  separate evidence); GE stays parked; calibrate-or-refuse covers the
  label edge.

## 7. Build + measured results (2026-07-15)

Implementation: `src/paperholo/payloaddec.py` (thin aggregator over the
`ldpc` primitives + `acquire.pava_calibrate`; ~700 lines), driver
`run_e023.py`, qualification `qualify_e023.py`; `FormatDescriptor` gained
`ldpc_rate` (e016/e018 rows = r0550). Tests: `tests/test_e023.py` — 10
tests: rot90-inversion pin, full-coverage byte-exact certification (the
score/keystream/slot-raster pin against encode-side truth), rot90-window
certification, calibrate-or-refuse, pre-decode attempt floor,
version/contradiction refusals, conflicting-certification fatal,
append-only resume + fingerprint, determinism + state round-trip, and the
ONE full-chain render -> e021 -> e022 -> e023 test (certified == GT
through the real placement stack).

### 7.1 Qualification (both v2.2 six-scan states, `qualify_e023.py`)

| footing | certified | failed | below floor | degenerate | GATE (a) wrong | GATE (b) yield | user bits |
|---|---|---|---|---|---|---|---|
| decimated 1600 | **741**/840 | 52 | 12 | 35 | **0**/741 PASS | **629/641 = 98.1%** PASS | 1,528,105 |
| native 4800 | **740**/840 | 55 | 10 | 35 | **0**/740 PASS | **674/690 = 97.7%** PASS | 1,527,275 |

- **Both pre-registered gates PASS on both footings.** Gate (b)'s
  denominator is footing-specific by construction (geometric coverage of
  the recorded cores: 641 decimated / 690 native nondegenerate tiles at
  >= 95%).
- **Staged merge vindicated by the ablation:** staged 741 = stage-1
  per-scan union 657 + stage-2 cross-scan sum 84; sum-only 736 (loses 5
  tiles to correlated-evidence dilution); best-single-scan 340. The
  013-measured doctrine holds at this footing too, and stage 2 earns its
  place (84 tiles no scan certifies alone).
- **Comparison row:** the e018 receiver recovered 532 certified tiles
  from the same physical scans WITH repass (a feedback loop e023 v1
  deliberately lacks); e023 certifies **741 fully blind, forward-only**
  — +39% — and 741 >> the 396 fountain symbols the volume needs (not
  exercised here; volume assembly is a later stage).
- **Calibration honesty:** 462/481 windows calibrated, ZERO refusals
  (placement floor covers the label edge, as predicted); held-out
  log-loss median 0.086/0.098, p95 0.138/0.194.
- **Emitted-cell BER vs GT:** 1.92% decimated / 2.64% native — the known
  c3 channel; the decimated footing is radiometrically slightly better
  for PAYLOAD reads even though placement quality was footing-identical
  (e022 11.3). Honest note for the record: at the payload layer,
  decimate-first retains a small measured edge.
- **Core-edge distance BER** (the R1 diagnostic): d1 3.3% -> d6 1.4%
  (decimated) — a real but mild rim gradient; the recorded-core-
  authoritative decision stands, no erode revisit warranted.
- **Context breakdown** (the context-binned-PAVA decision instrument):
  the classic U-shape — BER 10.7% at 0 ink neighbors, 1.2% at 4, 9.9%
  at 8 (decimated) — i.e. isolated-cell white-closure/erosion physics,
  exactly the known channel. The contingency's trigger condition is NOT
  met (gates passed), so context-binned PAVA stays unbuilt; the
  instrument's finding is recorded for any future E023.1.
- **Divergence instrument** (production alarm, no GT): mean 2.5%/3.5%;
  a handful of tile x scan pairs read 0.3-0.4 against certified values
  (plus small-overlap noise up to 1.0 on <30-cell overlaps) — exactly
  the windows whose local emission was poor while better scans carried
  the tile; the alarm surfaces them without vetoing anything.
- **Honesty ledgers:** ~1,024/1,037 decode attempts = CRC false-accept
  budget 2.4e-7; zero fatal flags; sliver census 15/27 unresolved
  windows (7/18 with retry-ledger candidates) = the future feedback
  loop's clientele.

Reports: `build/qualify_report.json`, per-footing states/PNGs/JSONs
`build/e023_{decimated,native}.{pkl,png,json}` (git-ignored). One
qualification-script defect was caught BY gate (a) during the first run:
the GT loader indexed the e018 dot raster as cells (6660x4500 vs
2220x1500), flagging all 741 certifications wrong with emitted BER pinned
at 0.4999 — the vacuity-proof gate pair working as designed (the same run
that certifies byte-exact against the correctly decimated GT).

### 7.2 What v1 leaves open (registered)

- The 52/55 attempted_failed + 12/10 below-floor tiles are coverage-
  bound (cut lines), not detection-bound — the dense-certified-field
  feedback loop's clientele, together with the sliver census.
- Multi-page and c2 arms unmeasured (design supports both; e016 c2 needs
  the e022 c2 window arm first).
- Volume assembly (fountain) intentionally out of e023.
- **`--diag` live viewer** (2026-07-15): `e023_diag.py` + `run_e023.py
  --diag [DIR] [--diag-port 8023]` — localhost auto-refresh and numbered
  PNG frames after each ingested scan (+ union frame). Page-space panes
  A/B/D only (scan-space stays with e022). Read-only observer;
  `tests/test_e023_diag.py` proves byte-identical decode with the flag
  off. Ranked decoder improvements: `FUTURE_WORK.md`.
