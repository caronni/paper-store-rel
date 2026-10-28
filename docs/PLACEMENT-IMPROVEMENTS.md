# PLACEMENT-IMPROVEMENTS — E022/ADDRESS efficiency & propagation ideas

Status: **discussion, not normative** (2026-07-31). RECEIVE-DESIGN v0.20 remains
the placement spec. Nothing here is an amendment; every result-affecting item
below requires its own RECEIVE-DESIGN amendment plus comparative qualification
before implementation, and every caching item requires a hoist-style
result-exact fixture (the 12P→4P+8 cold-map hoist is the precedent — and its
post-hoist full-domain rerun is still owed, RECEIVE-DESIGN §12.1 item 2).

Provenance: the 2026-07-30/31 placement design review (12-agent verified read
of the ADDRESS stage; findings in the session memory `holo-placement-audit`)
plus the user dialogue of 2026-07-31. Constants cited below were verified
against source and the live registry on 2026-07-31.

Standing constraints that shape everything here (RECEIVE-DESIGN §5.2/§5.3):

- Evidence from the current pixels may **reorder** work (scheduling), never
  **narrow** a declared domain, lower a floor, weaken a gate, or truncate the
  rival set. The complete-domain discipline is not negotiable.
- Caching/batching is sanctioned "only while preserving exact scores,
  candidate ordering, and acceptance".
- The cold rival gate needs the best rival from the **complete** domain, so a
  single `correlate_patch` call can never early-exit on a partial page sweep.

## 1. Scheduling family — make cold correlation rare

Cold should fire roughly once per disconnected physical piece per lane; every
additional cold call is a scheduling failure, not a cold-search deficiency.
These items reduce cold *invocations*; §2 reduces cold *cost*.

All of them are result-affecting in bookkeeping (route labels, component
inheritance, redundancy-marking order via `observed_sites` fill order) while
leaving every admission bar unchanged — amendment + comparative qualification
required. The umbrella is the parked kiss-branch item "frontier scheduler with
measured cold-search mechanism" (`.claude/memories/holo-v1-kiss-branch.md`).

### 1.1 Wave-front window ordering

`layout_pose_windows` orders windows richest-support-first; a window far from
every anchor can be processed before the neighbours that would have chained
it. A wave-front order (expand from accepted placements by adjacency, seeded
by the richest window) maximizes chain applicability. Interacts with 1.3;
either subsumes much of the other.

### 1.2 Nearest-first anchor ordering in `_chain_search`

Anchors are currently tried in **acceptance order** (docstring: "historical
insertion order", place.py:193), with one fixed ±3-cell gate regardless of
distance. Warp arithmetic: pitch/hygroexpansion error of 0.1–0.3% costs
~0.2–0.5 cells over one 160-cell stride (inside the 7×7 box) but ~2–5 cells
across a region (at or beyond the gate) — far anchors mostly waste their 49
scores. Nearest-first is strictly better in expectation and mirrors what
`_rank_lower_hints` already does for cross-lane hints (Euclidean sort,
place.py:146). Result-affecting: changes which anchor accepts first, hence
component inheritance.

### 1.3 Deferred cold search (user proposal, 2026-07-31)

When the route ladder falls through chain/lower/word, do not run cold
immediately: push the window (with its sampled patch) onto a deferred queue
and continue. Later cheap acceptances create anchors that may place deferred
windows by chain on a re-pass. Sketch:

1. Pass 1 per window: pose fit → sample → chain → lower → word; fall-through
   defers instead of cold. (Pose-refusal subdivision unchanged; cold-refusal
   subdivision moves to the final phase, and children then enter the cheap
   ladder first — they see the full anchor inventory, an improvement.)
2. When the queue drains: sweep deferred windows through chain again. The
   `ScoreMemo` makes re-passes nearly free — predictions from already-tried
   anchors are memo hits; only new anchors add 49 scores each. Stage-A word
   results are deterministic per patch: do not re-run them.
3. When a full sweep accepts nothing: run cold on the best deferred window
   (highest support). On acceptance, go to 2 (the new anchor may chain the
   rest). On refusal, subdivide as today. Repeat until the deferred set is
   empty. Termination: every cycle either accepts a window or spends one cold
   + subdivision, and depth is capped at 1.

Accounting stays exact: the chain domain is already declared as
49 × anchors-actually-tried and its floor grows with the inventory (floor
stays 30 until 5,113 anchors), so re-passes are priced by the existing rule.

**Measure before building** (§5 below): the win exists only where cold
currently runs on windows that a *later* same-region acceptance could have
chained. On clean material the support-descending order already front-loads
likely word-decode seeders, and the word route needs no anchors — so the
saveable-cold census may be small. The existing `WindowAttempt` ledger
answers this from past runs without new instrumentation.

### 1.4a Cross-lane cold deferral — ADJUDICATED PAYLOAD-UNSAFE as sketched
(user question + evidence review, 2026-07-31)

Proposal: skip cold at coarse lanes entirely; let the finest lane run the
colds (same cell-domain FFT cost, better evidence). REJECTED on measured
payload-domain evidence — the placement-statistic argument is right but the
payload channel disagrees:

- Every independent (uncensored) measurement shows BIDIRECTIONAL partial
  overlap of certified-tile sets across scales: coarse-only 15/671 C3 and
  19/1310 C2 (5 fountain-useful) vs fine-only standalone; the 2→6 endpoint
  control shows the finest lane genuinely attempting and LOSING 7 tiles the
  3-ppc lane certifies; E023b multiview: decimated-only 17 vs native-only
  12 of a 769 union. Mechanism on record: the decimation aperture improves
  photometry (pair-matched PAVA BER 1.80% decimated vs 2.41% native over
  6.0M cells), coarse geometry accepts more placements on intact sheets,
  and LDPC/BP nonlinearity clusters exclusive tiles in row bands.
- Seed amplification: placements are overwhelmingly chained (143 = 1 seed
  + 142 chain on the C3 baseline), so one skipped cold seed forfeits a
  region's entire coarse lane — payload births, lower-hints to finer
  lanes, and certificate pose refinement (50/142, 43/142 adopted) at once.
- Both qualified sheets closed the fountain AT THE FIRST COARSE BARRIER;
  deferring coarse work delays exactly that close.
- Fresh synthetic confirmation (2026-07-31 A/B run 1): coarse lane minted
  575/604 certificates (95%); finer lanes rescued 29; the residual is
  coverage-limited (failed tiles median 1563/3976 informative cells,
  1642/1700 below_attempt_floor), not evidence-limited.

The payload-safe form, if the real-material census ever justifies revisit:
skip coarse cold AND append a trailing coarse mop-up lane to the scale
plan — it inherits the fine lanes' accepted poses as ordinary lower-hints
(49-score local searches replace the cold) and harvests coarse-aperture
payload for still-needed tiles. Costs an extra lane pass and still delays
close; not built. Honest gaps: no cold-route-specific ablation exists in
the record; per-region exclusivity under selective skip and the whole
confetti regime are unmeasured.

### 1.4b Reopening record (2026-07-31 user session) — the selective question

The user deliberately reopened §1.4a's adjudication. Outcome of the
dialogue: §1.4a's whole-lane adjudication STANDS as written — every
measurement above answers "is the coarse LANE's produce dispensable?" (no)
— but none of it is conditioned on the cold route specifically, and on
current code (v0.23 frontier + v0.26/v0.29 word reach) colds on clean
material are already nearly extinct (synthetic A/B: 19 word + 32 cold →
51 word + 0 cold seeds). The live question is confined to word-dead
material (small fragments, damaged slots, confetti — unmeasured), and a
deferral with a structurally guaranteed mop-up is a scheduling reorder,
not the adjudicated permanent skip. Further findings of the dialogue:
"after all pages" is not a meaningful deferral axis (cold is page-atomic —
one FFT pass sweeps every declared page), but "after all scanned pages
(captures) are ingested" is, and it is law-compatible at capture
granularity; the coarse-first ladder is also cold-count-optimal (hint flow
follows lane order) and the measured photometry direction (decimated PAVA
BER 1.80% vs native 2.41%) contradicts the "better evidence at fine"
premise, so skip-without-mop-up can DOUBLE per-region cold count.
Resolution: the phased session schedule (RECEIVE-DESIGN v0.33,
docs/PHASED-SCHEDULE.md) — cheap evidence globally first, costly placement
work globally last, EV-ordered, close-preemptible. Census still owed
post-08-04: per-region coarse-payload exclusivity under selective skip,
the confetti regime, and the offline cold-necessity counterfactual
(remove cold-descended certificates from recorded sessions; does rank
still complete?).

### 1.5 Phased session schedule — ADOPTED as RECEIVE-DESIGN v0.33

The umbrella design that subsumes §1.3's within-region deferral, §1.4a's
payload-safe mop-up shape, §1.4b's session axis, and §3.5's price rule:
rung-major breadth-first phase 1 (all captures, cheap routes only),
durable ParkedWindow rows, per-capture mop-up levels M(Lk) at the base
lane's evidence identity, a priced close-preemptible tail, and the
count-gated close-attempt schedule. Normative text: RECEIVE-DESIGN v0.33
ledger row; full design + frictions + execution plan:
docs/PHASED-SCHEDULE.md (decisions D1–D18).

### 1.4 Certified-footprint deprioritization

Deprioritize (never skip at the admission level) windows whose *predicted*
page footprint — via anchor transport — lands entirely on certified tiles.
The certified-tile complement (NeedMap) is already the authority downstream
(`unresolved_region_patch_ids`, `_prune_certified_k_owners`); this only moves
that knowledge earlier as a scheduling signal.

## 2. Cold-search exact-cost family — when cold does run

All four preserve exact scores/ordering/acceptance by construction and fall
under §5.3's caching allowance; each still needs a result-exact fixture.

- **2.1 Winner-only second peak.** Every map currently pays a full `z.copy()`
  + second argmax (search.py:397), but only the winning map's second is ever
  used. Keep tops; recompute the second for the one winning map. Saves 1,247
  multi-MB copies on a full 312-page C3 sweep.
- **2.2 Kernel-side FFT caching.** `fftconvolve` recomputes the
  `soft_kernel` transform on every call; it is page-invariant per
  orientation. Hoist it across the page loop.
- **2.3 Page-side FFT caching across windows.** Every full window is exactly
  200×200 cells, so the overhang padding — and hence the padded
  `expected_sign × search_sites` array per (page, rot) — is
  window-independent. Its forward transform caches across every cold call in
  the lane. 2.2 + 2.3 together drop each (page, rot, window) trial from two
  forward FFTs + one inverse to ~one inverse: ~3× on the dominant term,
  compounding across windows.
- **2.4 Stacked page batching.** Batch the P per-page soft convolutions as
  one 3-D stacked FFT — same math, vectorized.

## 3. Word-route family — let algebra preempt the FFT more often

Stage A is the anchor-free seeder; every extra decode chance directly removes
a potential 1,256-FFT cold call. The α = 1e-3 union-bound ceiling admits up
to 581,074 phase hypotheses; a window currently spends 16,384.

- **3.1 Multi-slot Stage A.** A 200-cell window has 9 full 64-cell slots;
  sweeping all of them is ≤147,456 hypotheses — still under the ceiling, and
  priced exactly by the existing `WordAttemptBudget` construction-refusal.
- **3.2 Loosen the window-wide mask gate.** `bch_min_mask_fraction = 0.82`
  over the whole eroded core kills the route for a window with one damaged
  corner even when the centre slot is pristine; the per-phase ≥90/100
  visibility floor already protects each attempt.
- **3.3 Global errors-first candidate ordering.** Candidates are currently
  errors-sorted within an orientation but orientations are concatenated, so a
  13-error rot0 seed is tried before a 0-error rot1 seed (words.py:168-222).
  Sort globally.
- **3.4 Erasure-aware Stage A — PARKED (user reservation, 2026-07-31).**
  Would extend cold decoding to 74–89-visible slots (the known-position rung
  already decodes with 2e + f ≤ 26), but the disjoint-sphere union bound must
  be redone — sphere volume grows with erasure count, making the per-phase
  false-accept probability phase-dependent. The user is not convinced the
  complexity is warranted; do not pursue without a new measured driver
  (e.g. physical-v1 confetti showing word refusals dominated by 74–89-visible
  slots).

## 4. Considered and adjudicated — do not reopen without new evidence

- **Occupied-page-area exclusion from the cold domain**: unsound at ADDRESS
  (adjacent windows overlap 40 cells by design; the multi-scan doctrine
  deliberately revisits page areas; redundant placements are the dedupe
  mechanism) and it is adaptive narrowing, which §5.3 forbids. The floor
  payoff is logarithmic and negligible anyway: halving the 312-page C3 domain
  moves the floor 55 → 53; excluding 90% reaches only 49, versus 41 for
  authoritative single-page narrowing. The sound form of "done areas" already
  exists downstream as certified-tile NeedMap pruning.
- **Page-recency narrowing of cold**: §5.3 ruling — seen pages may schedule,
  never shrink the domain/floor/rival set; and cold structurally cannot
  early-exit (complete rival set). Page order inside one call changes only
  exact-tie breaks.
- **Seen-page fast lane**: doc-permitted as proposal-only (must still pay the
  full-floor decision); unbuilt; largely subsumed by §1.
- **Counter stride invariant** (`c(ty+1,tx) − c(ty,tx) = tiles_x`):
  documented not-built; bounded pruning/scheduling evidence only
  (RECEIVE-DESIGN §5.3).
- **ctx-PAVA at the word layer**: deliberate evidence-boundary placement —
  the word sites are the calibrator's *training labels*, the firewall must
  run before payload calibration exists (causality), and the d=27/t=13
  margin leaves nothing to gain (1,780 historical reads, 0 conflicts).
  Conditional reopening trigger: physical-v1 c2 multi-scan word
  refusals/conflicts clustering in closure-dominated contexts.
- **Same-capture geometric exclusivity** (two placements claiming the same
  page cells with incompatible poses is not geometrically checked at
  ADDRESS): noted as an asymmetry; the dangerous case is covered by the BCH
  conflict firewall and the payload divergence audit. No action.

## 5. Measurement prerequisites (before building §1)

1. **Cold-invocation census** from existing `WindowAttempt` ledgers: how many
   cold calls per run; of the cold *acceptances*, how many had a
   later-accepted same-region window within chain-transport range (the
   deferral-saveable set); route mix per material class (full sheet vs
   confetti, c2 vs c3). If the saveable set is ~0, §1.3 adds complexity for
   nothing and §1.1/1.2 carry the value.
2. **Post-hoist full-domain wall-time/RSS rerun** (owed, §12.1 item 3) — the
   baseline any §2 speedup must be measured against.
3. The **0.176 rival-gate refusal** on the complete 312-page C3 domain
   (§12.1 item 2) — any scheduling change must not obscure this open
   admission question; it is a gate calibration issue, not an efficiency one.

## Ranking (expected value, 2026-07-31 view)

1. §1 scheduling family — biggest expected reduction in cold invocations;
   gate-neutral; blocked on the §5.1 census.
2. §2 FFT caching/batching — ~3×+ on cold when it runs; lowest risk
   (exactness by construction, fixture-provable).
3. §3.1–3.3 word-route widening — cheap, fully priced, directly preempts cold.
4. §3.4 erasure Stage A — parked.

## Execution status (2026-07-31, RECEIVE-DESIGN v0.22 + v0.23)

- §1.1–1.3 EXECUTED (v0.23, user override of the census gate — measure on
  synthetics instead): wave-front window order, nearest-first anchors,
  region-wide deferred cold with chain re-pass. Behavior pinned by
  `tests/holo/test_placement_frontier.py`; measured on the synthetic
  word-killed two-window fragment (`tests/holo/_bench_placement.py`):
  2/2 accepted with **0 cold searches vs 1 under the sequential ladder**
  (each saved cold is a full 4P+8-FFT sweep — ~12 s/window at production
  scale per the kiss-branch measurement). The clean fragment runs 0 colds,
  0 deferrals — no overhead path. §1.4 NOT built (needs cross-lane
  certificate context at ADDRESS; revisit with the real-corpus census).
- §2.1–2.3 EXECUTED: winner-only second peak + hoisted rfftn kernel/page
  transforms, bit-identical (pinned by
  `tests/holo/test_cold_search_exactness.py` against a verbatim legacy
  reimplementation). **Measured** (`_bench_placement.py`, qualification
  geometry): 1.33×/1.55×/1.65× at P=4/16/64, growing with P toward the
  ~2.4× FFT-count asymptote — the doc's earlier "~3×" was the count-based
  upper bound, not a measurement. §2.4 REJECTED: strided-batch FFT kernels
  are not provable bit-identical by fixture. Cross-call page-transform
  caching noted as a future option (needs an eviction-policy decision).
- §3.1–3.3 EXECUTED: multi-slot Stage A (declared 147,456/window;
  envelope 442,368 → 7.6e-4 < α; a fourth 200-cell row refuses at
  construction), `bch_min_mask_fraction` deleted, global errors-first
  ordering; word gate identity
  `holo-v1/e022-single-word-multi-slot-union-bound`
  (`tests/holo/test_word_route_widening.py`).
- §3.4 remains parked (user ruling).
- SYNTHETIC A/B COMPLETE (2026-07-31, c2-cmy7 hp/canon chain, byte-identical
  inputs): yield exactly invariant (604 certificates, same tiles, same
  bits, rank 604/1294 both revisions — the fixture is coverage-limited at
  41.3% payload area and cannot close); route substitution perfect (old:
  19 word + 32 cold seeds; new: 51 word + 0 cold — frontier deferral +
  multi-slot reach eliminated every cold search); cost regression found
  and fixed: the all-slot up-front sweep cost +267 s address CPU (+21%),
  cured by v0.26 staged Stage A (centre slot first, widen on failure;
  3,627 -> 794 ms per word-succeeding window). Real-corpus comparative
  qualification still owed before any freeze; the census (§5.1) remains
  the deferral-value calibration on real material.

## Three-way cost measurement + the remaining recoverable slice
(2026-07-31 evening; byte-identical synthetic chain; address-stage CPU)

| | v0.21 (old) | v0.24 (regression) | v0.31 (current) |
|---|---:|---:|---:|
| address total | 493 s | 783 s | 647 s |
| all stages | 1243 s | 1511 s | 1394 s |

v0.26+v0.29 recovered ~50% of the v0.24 word-sweep regression. The
~150 s residual over v0.21 decomposes into: (a) rest-sweeps at the cold
boundary — ~75 word-dead windows each pay ~2.8 s of 8-slot decode ahead
of a cold that costs only ~1-3 s at the single-page domain (the v0.26
lesson one level down: the ordering is domain-size-blind); (b) the
whole-word rival scoring surcharge per cold run. NOTE: the single-page
decode is the COMMON production case; the widened machinery pays off
decisively only at large page domains (30-48 s per avoided cold).

QUEUED (§3.5, amendment-sized): **cost-aware ordering at the cold
boundary** — when the declared cold domain prices below one rest sweep,
run the cold first and rest-decode only on refusal; large domains keep
rest-first. Both routes still run before any window gives up, so reach
and accounting are untouched. EXECUTING as part of RECEIVE-DESIGN v0.33's
priced tail (docs/PHASED-SCHEDULE.md D9; `cold_first_max_pages` policy
datum, default 1).

Also measured 2026-07-31: the slow lane's only pathological test is
test_receive_qualification.py::test_provisional_production_roundtrip
(>2h40 pre-v0.29; still >20 min on v0.30 — lazy staging is NOT the full
story; no historical timing baseline exists under HOLO_RUN_SLOW_TESTS).
Next instrument per the profiling doctrine: one qualifier arm with
per-stage processor_seconds from events, never pytest timing.
