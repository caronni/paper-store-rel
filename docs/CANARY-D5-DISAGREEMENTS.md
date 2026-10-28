# D5 health-canary investigation — the 44,561 dropped disagreements

Status: **findings, not normative** (2026-08-02). Investigation of the
2026-08-02 R-lane qualification run's epilogue line (PAYLOAD-MEASUREMENTS
§7, run 2):

    mop-up supersession dropped 44561 DISAGREEING observation(s) at
    committed cells (health canary — possible placement/pose defect or
    physical drift; committed evidence unchanged)

Findings-first: no numerical change is made here; §6 lists the ruling
options with measured costs. Corpus:
`scratch/c2-cmy7-hp-nominal-canon4800-q070-max-20x2-20260731-155516`
(c2-cmy7, two 6.8 GB 4800-dpi scrap captures, page domain {0},
non-closing, 604 certificates). Probes and raw outputs:
`scratch/canary-probe/` (fixture probe, instrumented real-corpus rerun,
analyzer). Tree: probes ran at `fb6973e`; `git diff 648520c..5f7c24b --
src/holo` is EMPTY (the run-2 commit's receiver, byte-identical), and
the only later src change while this investigation ran is `a814539`
(diag viewer/seed — strictly-downstream observation, §10.1; line pins
below are current at `a814539`).

## 1. Verdict up front

The counter is **working as coded and the committed evidence is safe**,
but the leading hypothesis (M-level pool moves the integer aperture →
same-window re-observation differs at the byte level) is **NOT the
mechanism behind the 44.5k**. The dominant — structurally guaranteed —
mechanism is simpler:

> At an M-level, every fresh observation at a committed cell comes from
> a **different window** than the committed owner (per-pass owner
> competition, D5 stated departure; M placements are the previously
> PARKED windows, id-disjoint from the base pass's owners by the D4
> watermark; D7 labels never mint observations). A different window
> means a different origin row — and, through its own crop, `_scores`
> normalization, and per-region calibration, essentially always
> different float32 value bytes. `supersede_with_committed` counts a
> dropped cell as DISAGREEING when value bytes OR origin row differ
> (evidence_blocks.py:508-557), so **~100% of M-window overlap with
> committed coverage counts as disagreement, aperture or no aperture.**

The counter therefore measures *"how many committed cells did the
M-level's windows overlap"* — an expected-nonzero geometry fact on any
real corpus whose M-levels place windows into already-covered territory
— and not drift, and not a pose defect. The instrumented rerun (§4)
reproduces **exactly 44,561** on byte-identical src (determinism kills
drift), decomposes it as 100% different-window value disagreement with
0 aperture flips anywhere, and shows the same physical overlap counting
once per ladder lane (one parked window ≈ 17.5k of the 44.5k).
Synthetics report ~0 because their M-levels place nothing — verified:
the 128-cell parked-interrupt corpus resolves its parked window at the
finer ordinary lane and its M-levels commit zero placements
(`probe_e2e.py`), and the `_bench_phased` corpus verifies its close
before the tail so M-levels never run at all — not because
re-observation agrees.

The aperture mechanism itself is real physics-of-the-code (measured
below: a one-integer flip changes 99.5% of a window's sampled bytes),
and §6.1's normative sentence "same aperture, same frontier, same union
law" (RECEIVE-DESIGN:585-591) is currently **not a guaranteed
invariant** — the M pass derives its aperture from a different L5 pool
population than the base pass. On this corpus the pools moved the
median pitch but never across an integer boundary (census in §4), so no
mixed-aperture block exists here. That divergence is a doc-vs-code
finding (§5.2), not the canary's cause.

## 2. The machinery, pinned

- Counter: `supersede_with_committed` (evidence_blocks.py:508-557) —
  collision-skip branch compares `(value_bytes, EvidenceOrigin)` pairs;
  `prior != (value, origin)` increments (line 547). `EvidenceOrigin`
  carries `placement_id`/`patch_id`/`heldout_logloss`
  (evidence_blocks.py:88-124), i.e. window identity — so a different
  observing window disagrees **by origin alone**, values notwithstanding.
  The unit pins sanction exactly this
  (tests/holo/test_supersession_materialization.py:181-203 — "(b)
  base-owner-wins": fresh value agrees, origin differs → counted).
- Aggregation: `apply_mopup_supersession` (evidence_blocks.py:560-584);
  gated to M-levels with committed base blocks at
  production_payload.py:335-343 (K) and production_color.py:498-507
  (color, the path this corpus runs); folded into
  `SessionCounters.mopup_dropped_disagreements` (session.py:606,
  runtime_model.py:252); epilogue cli.py:402-421; diag LDPC row
  viewer.py:921.
- Who observes at committed cells: M placements = parked windows
  (re-using their base ordinals — never committed at base) plus
  subdivision children (fresh ordinals above the D4 watermark,
  evidence_context.py:109-119); base-accepted windows re-enter as D7
  **labels only** (evidence_context.py:123-126; label rows never own,
  block, or attempt — RECEIVE-DESIGN §8.2:1148-1151,
  color_payload.py:870, _payload_sampling.py:466-469). So the committed
  owner window is structurally never the fresh observer. Full-agreement
  drops (not counted) can only arise from deterministic re-runs of the
  same pass — crash/resume replays.
- Aperture derivation: the L5 pool median —
  `sample_and_calibrate`: `pitch_px = _region_pitch(patches +
  label_patches)` (_payload_sampling.py:448), color twin at
  color_payload.py:774-776; integer pair `(ceil(0.7·p)+2,
  max(1, round(0.7·p)))` at _payload_sampling.py:209/219 and
  color_anchoring.py:366/387. Base pass pool = base placements ∪ base
  label rows; M pass pool = M placements ∪ D7 labels — different
  populations by construction.

## 3. Fixture-scale reproduction (scratch/canary-probe/probe_fixture.py)

Real machinery end-to-end (place_survey → sample_and_calibrate →
apply_region_context → freeze → blocks_from_frontier →
apply_mopup_supersession), roundtrip fixture, one region, two
overlapping windows; base pass = window 0, M pass = window 1 as
placement + window 0 as D7 label (the v0.33 M shape):

- Pools: base 3.0000036 px/cell, M 3.0000014 px/cell — **integer pair
  (5, 2) in both passes, no flip**.
- Collisions 13,073 → dropped disagreements **13,073 (100%)**; all
  13,073 differ in **value bytes** (0 origin-only, 0 full-agreement).
  `apply_mopup_supersession` returns exactly collisions −
  full_agreements.
- Value deltas: median |Δ| 0.058 LLR, p90 1.15, max 1.85 — and **zero
  sign flips** over all 13,073 cells: the two windows agree on every
  cell's polarity. This is what healthy overlap disagreement looks
  like.
- The hypothesis's mechanism (a), isolated: the SAME window re-sampled
  through the production `_sample_window` at a pitch flipping the
  integer aperture 2→3 differs on **99.47%** of cells (median |Δ| 31
  raw-mean units); at a same-aperture pitch (+0.2%) it is
  **bit-identical**. Sampled values are a function of (raster bytes,
  pose points, integer aperture) — the halo integer only moves the crop
  origin, which the sampler compensates exactly.

So: no aperture change is needed to produce the counter's disagreements,
and an aperture change cannot reach the counter through same-window
re-observation (structurally impossible at M-levels). What an aperture
flip WOULD do is (i) resample D7 label rows differently than the base
pass sampled the same windows (fit-population fidelity, not counted
anywhere) and (ii) make the M windows' novel cells ride a different
filter than the block's committed cells (the mixed-aperture block of
hypothesis (c)).

## 4. Real-corpus attribution (instrumented rerun)

Instrumented fresh session (`scratch/canary-probe/probe_real.py`):
ordinary ladder + M-levels (run_mopup, no refine — R lanes own their
evidence namespace and never supersede: RECEIVE-DESIGN v0.42), hooks on
`supersede_with_committed` (per-cell decomposition) and
`collect_color_evidence` (exact per-(region, page) L5 pool + integer
pair, base and M passes), plus the event-side per-(capture, lane)
attribution. CPU 1584.4 s (hooks ≈ free vs the A3 baseline's 1537 s),
604 certificates, open, 16 barriers — and `src/holo` is byte-identical
from `648520c` (the run-2 commit) through this run's HEAD (`5f7c24b`),
so the numbers below are the run-2 numbers.

- **Exact reproduction: the session counter is 44,561** — identical to
  run 2's epilogue (R lanes add nothing, as designed). Three
  independent derivations agree exactly: the durable
  `SessionCounters.mopup_dropped_disagreements`, the hook's per-cell
  decomposition total, and the sum of the eight per-barrier
  `color.mopup_dropped_disagreements` details. Deterministic replay of
  the same capture bytes reproducing the same 44,561 kills "physical
  drift" outright.
- **Decomposition: 44,561 collisions → 44,561 value-differs (100%),
  0 origin-only, 0 full-agreement.** Every colliding cell was a
  different-window observation, exactly as the structural argument
  predicts. 43 colliding blocks; 32 extended with 11,700 novel cells,
  11 dropped as nothing-novel.
- **Per (capture, lane)**: every M lane of both captures contributes —
  capture `478b4625` m00/m01/m02/m03 = 6,562/6,048/8,723/8,150;
  capture `ada28085` = 4,768/3,320/3,326/3,664 (m00 also minted the
  +3 certificates, matching run 2's 601→604). The count multiplies
  down the ladder: the SAME physical overlap re-observes once per
  evidence lane — capture 478b's region 13 alone contributes ≈4.4k on
  each of the four lanes ≈ 17.5k (39% of the total) from ONE parked
  window overlapping five committed base windows per lane.
- **Aperture census: 0 integer flips across all 42 (lane, region,
  page) groups common to both passes.** Cross-pass pool-median deltas
  are ≤0.00113 px/cell; integer pairs identical at every footing —
  (4,1) @2ppc, (5,3) @4ppc, (8,6) @8ppc, (14,11) @16ppc. The L5 pool
  construction itself explains the stability: the M pool is the base
  population (as labels: 5–28 per region here) plus 1–4 new windows,
  so the median is anchored by the labels. 0% of disagreements lie in
  aperture-flipped regions.
- **Value character (the step-3 discriminator)**: per-block median
  |Δ| p50 = 5.48 (7-ary color scores; p10 2.9, p90 11.3, max 40 = the
  clamp scale); any-component sign flips 37.3%; **state-winner
  (argmax) flips 7.7%** of colliding cells. Against the clean-synthetic
  fixture's 0% flips, 7.7% winner disagreement is elevated but has a
  benign structural reading: M windows are by construction the base
  pass's WORST windows (they parked because every cheap route failed),
  so their detectors disagree with the committed owners exactly on
  marginal material. This flip rate — not byte inequality — is the
  statistic worth a post-08-04 threshold doctrine.

## 5. Findings

- **5.1 The canary's alarm text misattributes the dominant term.**
  cli.py:407-410 ("Systematic disagreement is a placement/pose-bug or
  physical-drift signal") and D5's framing assume re-observation should
  usually agree. At M-levels agreement at committed cells is
  structurally impossible except on crash-resume replays: different
  owner ⇒ different origin ⇒ counted, and different window ⇒ different
  bytes in practice. The counter's magnitude scales with M-placement
  overlap area, not with any defect. (The 018-class lesson applies: an
  alarm that fires on healthy material trains operators to ignore it —
  and this canary's real signal, sign-flip/winner-flip rates between
  overlapping windows, is currently not separated from the benign
  byte-inequality term.)
- **5.2 Doc-vs-code: §6.1's "same aperture" is not enforced.**
  RECEIVE-DESIGN:585-591 promises the mop-up contributes "exactly as a
  deferred second pass of that lane — same aperture, same frontier,
  same union law"; the v0.33 ledger row and PHASED-SCHEDULE D7 say
  "harvests payload at the base lane's aperture". Shipped code derives
  the M-pass aperture from the L5 pool over a DIFFERENT population
  (_payload_sampling.py:448, color_payload.py:774-776). The design
  already guards pool identity within a pass (L5; the refinement replay
  pins "generation zero's crop/filter policy exactly",
  certified_cascade.py:212-215) but makes no cross-pass claim. Measured
  on this corpus: 0 flips / 42 groups, cross-pass median deltas
  ≤0.00113 px/cell — the label-anchored M pool makes flips structurally
  unlikely, but the guarantee is population-contingent: a label-poor
  region flooded with pitch-skewed subdivision children (the
  damaged-material corner) is exactly where it would fail, silently.
  Note the D6 parked row already
  persists the base `cell_pitch_px` (types: ParkedWindowRecord) and the
  ADDRESS side of the M-level re-derives on the persisted base pitch;
  only the PAYLOAD-side pool is population-derived.
- **5.3 The v0.34 label bit-exactness pin under-claims its
  precondition.** test_phased_schedule.py:460-463 pins pose/audited
  cells/page footprint as "the complete determinants of payload
  sampling" — true only at a fixed region pool. Under a pool flip the
  reconstructed label row samples DIFFERENT values than the base pass
  sampled for the same window (measured §3: 99.5% of bytes). D7's
  "restoring the pooled per-region label population" then restores a
  population sampled through a different filter than the one the base
  fit consumed. Not reachable on this corpus (no flips, §4); latent
  otherwise.
- **5.4 Mixed-aperture extended blocks.** Hypothesis (c) is real but
  bounded: novel cells and committed cells of one extended block may
  ride different integer apertures if the pools flip. Census on this
  corpus: **zero** (no flips ⇒ all 32 extended blocks are
  same-aperture). Regardless of flips, extended blocks are
  already mixed-window and mixed-calibration by design (one owner per
  cell, per-pass fits); the LDPC decoder consumes per-cell LLRs and
  CRC/SHA still gate every mint — consistency/yield exposure only,
  never wrong bytes.
- **5.5 Bookkeeping.** PAYLOAD-IMPROVEMENTS' provenance note names the
  `holo-payload-audit` memory as the durable findings summary; no such
  memory exists under `.claude/memories/` (12 files checked). Broken
  reference, worth restoring or re-pointing.

## 6. Ruling options

> **RULED AND EXECUTED (2026-08-02, same day): option 1 as sharpened —
> "replace"** (RECEIVE-DESIGN v0.46). The byte-inequality count is
> deleted; `SupersessionDrops(dropped, winner_flips)` ships with the
> `winner_codes` conventions (K sign / CMY7 W-relative state / CMY8
> plane pattern), carriers renamed
> `mopup_dropped_observations`/`mopup_winner_flips`, schema 24→25 and
> discovery 10→11, no policy bumps. Pins re-derived; new positive
> control `test_winner_flip_rate_separates_misplaced_mopup_window`
> (correct pose ≤2% flips, 8-cell-misplaced ≥25%, identical dropped).
> Production confirmation on this corpus: dropped **44,561**
> (byte-identical to run 2), winner flips **2,383 (5.35%)** under the
> corrected convention (§4's hook argmax-over-6 read 7.7%;
> `confirm_real_report.json` is the citable record). Options 2 vs 3
> (the §5.2 aperture invariant) remain OPEN — not part of this ruling.
> Pre-existing c2 measured-channel gate failures found during
> qualification (verified identical at `a814539`, pre-change: flagless
> gates lost inline refinement when v0.42 moved it behind `--refine`)
> are recorded in the v0.46 ledger row as an open regression owed its
> own session.

1. **Split the counter's semantics** (recommended, diagnostics-lane):
   count value-level disagreement and origin-only separately, and
   surface the *discriminating* statistics — sign-flip (K) /
   state-winner-flip (color) rate and a delta-magnitude summary —
   instead of raw byte-inequality. The epilogue then says what it
   means: "M windows re-observed N committed cells; polarity conflicts
   M (x%)". Cost: counter surface + epilogue + SessionCounters schema
   bump (schema-refuse, no migration per doctrine); the D5 layer
   already computes both sides in the collision loop. This preserves
   ruling 11.2's intent (a real drift/pose canary) and stops the
   healthy-overlap term from swamping it.
2. **Pin the M-level payload aperture to the base pass** (makes §6.1's
   "same aperture" true): persist the base pass's per-(region, page)
   pool pitch (D6 already persists the region-scoped `cell_pitch_px`
   on parked rows; a region-level durable is the natural home) and
   have the M pass sample at it — labels then reconstruct bit-exactly
   in the strong sense and mixed-aperture blocks become structurally
   impossible, exactly like the R-lane replay pool (L5). Cost: schema
   +1 field, sampler plumbing, policy-id bump (aperture is
   decode-relevant), pool-oracle fixture arm. Zero effect on this
   corpus (no flips measured) — this buys the INVARIANT, not numbers.
3. **Amend §6.1/D7 instead**: state that the M pass samples at ITS OWN
   L5 pool (population-honest), that cross-pass aperture identity is
   NOT promised, and record the mixed-aperture block as legal (CRC/SHA
   gate correctness; blocks are already mixed-window). Cost: doc-only.
   Leaves 5.3's latent label-fidelity caveat standing (record it).
4. **Route M-level novel cells into separate blocks** (no supersession,
   sibling blocks per pass): rejected-shaped — it forks the
   one-key-one-content frontier law (D5 exists precisely to avoid
   this) and buys nothing the split counter doesn't.

Options 1 and (2 XOR 3) compose: 1 fixes the alarm; 2/3 decide the
aperture invariant. Threshold doctrine stays post-08-04 as ruled
(11.2), but option 1 changes WHAT the threshold will be set on — worth
deciding before hardware returns.

## 7. Reproduction

- Fixture probe: `PYTHONPATH=src env/bin/python
  scratch/canary-probe/probe_fixture.py`
- Tiny e2e (synthetic ~0 face): `PYTHONPATH=src:tests/holo
  env/bin/python scratch/canary-probe/probe_e2e.py`
- Instrumented real corpus: `PYTHONPATH=src:tests/holo env/bin/python
  scratch/canary-probe/probe_real.py <corpus> <out.json>` then
  `analyze_real.py <out.json>` (CPU-primary per the standing
  measurement rule; the probe is observer+monkeypatch only, no
  production code touched).
