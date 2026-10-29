# FEC-DESIGN — Layer 3, the inner code (M2)

**v0.2, 2026-07-08** (v0.1 same day; §Format corrected to as-built). Companion to DESIGN.md §6 (normative: LDPC per
64×64-cell tile, interior CRC, local-only interleaving) and PILOTS-DESIGN
v0.3 (the L2 system that feeds this layer its LLRs and addresses).
Status at writing: implementation in flight (src/paperholo/ldpc.py);
experiment 013 measures it. Numbers labeled MEASURED/ESTIMATE as usual.

## The one-page core

Layer 3 turns the blind receiver's per-cell LLRs into **certified clean
bits**, one codeword per geometric 64×64-cell tile:

1. **One mother code, shortened per tile.** QC-IRA LDPC, n = 4096 (one slot
   per tile cell, raster order). Slots that fall on pilot sites (110–118 per
   tile — the 60-vs-64 misalignment) or off the page edge are *shortened*:
   forced to 0 at encode, pinned at decode as known-0 (LLR −∞ in the house
   sign convention: positive = bit 1), never printed. One code
   absorbs all tile geometry; the shortening pattern is public and
   deterministic from (seed, page geometry, tile index).
2. **Per-tile framing = payload + CRC-32.** A CRC pass is the F9 event: it
   certifies the *whole hypothesis chain* — lattice lock, site phase,
   address counter, warp — that produced the samples ("pilots measure
   registration; codes certify it"). In fragment-pile recovery, one
   CRC-passing tile validates the placement of every fragment that
   contributed cells to it (PILOTS-DESIGN §14).
3. **Decode = normalized min-sum on blind GMM LLRs.** Three LLR classes:
   measured cells (finite), **missing cells = erasures (LLR 0)** — native
   here, closing the errors-only gap the confetti ladder depends on — and
   shortened (known-0, −∞). The decoder is a hybrid: normalized min-sum
   (α=0.8, scale-invariant fast path) with one sum-product retry on syndrome
   failure (measured: 4.0% → 1.6% BLER at the r0700 gate). Multi-scan combining = LLR summation before decode
   (LAYERS interface). PAVA recalibration hooks in iff the measured
   reliability curve says the GMM is off.
4. **Rates are a ladder of format entries** (registry keys, k snapped to
   circulant multiples): {0.547, 0.625, 0.703, 0.781, 0.859} of n = 4096.
   Doctrine unchanged: sim picks the sim recommendation; the hardware rate
   is set on multi-sheet minima from real scans (e012 onward).

Net decoded density at c3, the honest arithmetic this layer exists to
measure: 62.0 cells/mm² × 97.2% (pilots) × rate × (1 − CRC/k). At rate
0.703 that is ≈ 42 b/mm²; at 0.781 ≈ 47 — versus the 47–50 b/mm² *MI proxy*
for c3. The proxy-to-decoded gap is the implementation price, measured in
experiment 013 for the first time.

## Format constants (Layer-3 v1)

- Tile 64×64 cells, row-major tile grid, partial edge tiles allowed
  (shortened like pilots). **DECIDED (user, 2026-07-08): the data-tile size
  and the pilot period/density remain INDEPENDENT format knobs** — the
  tile=60 alignment option (one constant shortening pattern, 1:1
  pilot-word/data-tile locality) was considered and rejected: layer
  independence and free per-layer exploration outweigh the cosmetic
  uniformity; the shortening map is precisely the mechanism that makes the
  independence cheap (absorbs any P-vs-tile misalignment, measured
  110–118 pilots/tile today).
- Code (v0.2 AS-BUILT correction — the v0.1 literal construction was
  FALSIFIED during implementation, each variant built and measured; full
  provenance in the ldpc.py module docstring, which is normative for the
  derivation): **e-IRA**, n = 4096, Z = 64. H = [H_d | Π·accumulator]:
  QC H_d with ~30% heavy info columns (degree 10; 8/6 at r0775/r0850) and
  degree-3 remainder, a seeded Fisher–Yates row interleaver Π, and a
  BIT-SERIAL dual-diagonal accumulator. Greedy placement rules: distinct
  rows per column, per-column tap-gap weight floor ≥24 (single-info-bit
  codeword weight ≥25), exact QC 4-cycle rule, row-degree cap. All
  integers from modulation.rng(b"ldpc-v1/<rate_id>", b"eira-H/restartN").
  Why not the textbook forms (measured): block-circulant accumulators
  terminate parity runs at block granularity → weight-8..10 codewords →
  UNDETECTED syndrome-valid wrong decodes (6/200 at p=0.015); naive QC
  accumulator taps are chain-adjacent → weight-(d+2) codewords everywhere;
  uniform degree-3 waterfalls ~0.037 < the needed ~0.043. As-built DE
  threshold ≈ 0.046 at r0700. Golden-anchored (per-rate H edge-array
  sha256 + codeword vectors) in tests/test_ldpc.py — bump-don't-edit.
- CRC-32 (zlib) over the tile payload, MSB-first packing, big-endian
  trailer, inside the info bits.
- Payload stream = tiles' non-shortened codeword bits, slot raster order,
  tile-grid raster order — exactly fills compose's payload bijection
  (3,237,500 bits on the e012 page).
- **This is payload-interpretation format, not printed-bitmap format:**
  a layout_version-3 sheet is v3 regardless of whether its payload is raw
  random (e012 ARCH-1) or LDPC-framed; the FormatDescriptor's code_id field
  records which. No layout_version bump; registry entries like
  "v3 + ldpc-v1/r0703" name the full stack.

## Codec-level MEASURED (2026-07-08, pre-013)

BSC frontiers (BLER, 200 fixed-seed trials/point): r0550 clean at p=0.055;
r0625 0.5% at 0.045; **r0700 1.5–1.8% at p=0.035** (the blind-channel
design point), 0% at 0.025; r0775 0.5% at 0.020; r0850 3.5% at 0.010.
Erasure+error frontier: r0700 carries (20% erased, 0.5% flipped); the
confetti regime (20% + 2%) is capacity-infeasible at r0700 (0.687 < 0.703)
and lands on **r0550** (clean at 20%+2%, degrading at 30%+2%) — fragment
tiles ride lower rungs. Speed: 176 tiles/s whole-page decode incl. gather
(a page is 840 tiles ≈ 5 s). Certification: 0/500 garbage CRC false-passes,
0 wrong-payload certifications in every battery; residual low-weight
conspiracies (one measured weight-6 codeword at r0625) are exactly why
certification is CRC-gated, not syndrome-gated. Page user capacity at
r0700 = 2,189,231 bits = 267 KiB → **net ≈40.8 b/mm²** if the blind
channel sustains r0700 — experiment 013's question.

## Experiment 013 MEASURED (2026-07-08 — the first decoded bits)

Full numbers + findings: experiments/013-ldpc-roundtrip.md. Compressed:
net certified at r0700 through the fully blind pipeline: **page-level
35.7 b/mm² at the measured 87.5% tile success (40.8 at 100%)** — the
initially-published 29.7 was a window-edge accounting artifact (013.1
correction). Against the sim blind-MI ceiling (47.5 incl. pilots): −14%
rate+CRC (mostly tail-forced margin) and −12.5% tile failures — the BANDED
error tails (F1) are charged twice; fixing F1/F2 projects ≈45 b/mm²
(ESTIMATE). F9 integrity: 0 wrong certifications anywhere
incl. valid-codeword substitution 300/300 CRC-caught. Fragment regime:
partial tiles decode at r0550 down to ~70% coverage (F4, matches the codec
frontier). NEGATIVE result F3: naive multi-scan LLR summation loses to the
best single scan under slip variance — per-scan pilot-agreement weights
(PILOTS-DESIGN role d) are the designed, unimplemented fix; tile-level
union of per-scan decodes is the interim answer. OPEN F2: detection BER is
content-dependent (~1 pp, LDPC-framed vs random page, same channel draw) —
mechanism unidentified, suspect DD-refinement/self-clock content coupling.

## 2026-10-20 — the published v2 set SET-1 (branch `ldpc-ladder-v2`, NOT merged, nothing printed)

The owner adopted the leaderboard's picks as the v2 set: one code per
rung, every one S4-accepted under the as-built floor bar (undetected ≤
1e-4 per trial at the 1 % point and at +0.5 dB), selected across the
c2-accept, c3-search, c4-top and c5-mid records, locked by a manifest
and a test in `ladder2/codes/`, verified from the published files on
fresh seeds. SET-1 is the WORKING set: it is republished as the search
improves the rungs (no tag; the owner: "we aren't done yet"). Since
2026-10-21 it is selected under the corrected metrics (rank v3: every
near-tied contender of a rung decoded at one Es/N0 on one fresh 10⁵-trial
range, the floor bar on S4's and those counts pooled), which moved six
rungs; on 2026-10-23 campaign c6-low's ruled PBRL codes took the bottom
four rungs (−0.14 … −0.42 dB, at a third to a half of the iterations);
on 2026-10-24 campaign c7-top's word-gated lifts at the top four rungs
landed inside the tie window (the top sits 0.40–0.46 dB above the
finite-length limit) and three rungs moved on the pooled floor (rank
v4); the same day c8-low's z 32 PBRL codes took r0250 / r0203 by
0.08 / 0.06 dB at the floor bar's edge (19–20 undetected in 2 × 10⁵
against the bar's 20) and lost everywhere above. Gaps to Shannon at 1 %
BLER on the rung final: 0.715–0.812 dB from r0906 to r0625,
0.848–1.035 dB from r0547 to r0313, 1.107 / 1.216 dB at r0250 / r0203. The table and the selection rule:
docs/LDPC-LADDER-V2.md §1.2; the search behind it: §8.1. Single seed,
codec simulation only.

## 2026-10-19 MEASURED — the LDPC ladder v2 (branch `ldpc-ladder-v2`, NOT merged, nothing printed)

**Status.** A from-scratch twelve-rung ladder at n = 4096, k 3712 … 832
(r0906 … r0203, true-rate tokens in the `ldpc-v2/` namespace), every
code built by a controlled construction (PEXIT-profiled IRA, PBRL,
punctured XOR-state and near-regular families; QC-PEG + ACE lifting with
an exact pair-weight gate) and qualified in simulation under the
production decoder's bit-exact batched twin through a resumable S0–S4
campaign (11.3 M decodes). Design, workplan and the measured record:
docs/LDPC-LADDER-V2.md (§1.1 the measured table, §9 the rulings owed);
tooling and operator manual `ladder2/`; the codes `ladder2/codes/`
(`CODES.md`), the full tables `ladder2/results/c2-accept/TABLES.md`.
Codec simulation only, single seed, NO promotion; the frozen v1 ladder
stays the law for every printed sheet; integration is a later format
version.

- **Gaps to Shannon at 1 % BLER (BIAWGN, 60 + SP 60):** 0.73–0.80 dB at
  r0859–r0703 and r0906, 0.83–0.93 at r0625–r0469, 1.0–1.3 at
  r0406–r0313, 1.44 / 1.68 at r0250 / r0203; 0.41–0.52 dB from the
  finite-length normal approximation down to r0547, 0.55–1.12 below.
- **Against the frozen twins, measured like for like (the six frozen
  codes through the v2 protocol, `measure/ladder2-v1-twins/`, 2026-10-19;
  single frozen codes against best-of-many lifts):** 0.06–0.11 dB better
  at the three shared rates with a published v2 code (r0781 0.728 vs
  r0775 0.789; r0703 0.756 vs r0700 0.843; r0547 0.873 vs 0.981), and the
  best REFUSED v2 codes at the other two (r0859 0.747 vs r0850 0.812;
  r0625 0.827 vs 0.899). Under the v2 undetected bar (≤ 10 per 10⁵ at
  the 1 % point and at +0.5 dB) the frozen r0775 (11 / 6), r0625
  (41 / 32) and r0550 (181 / 89) are refused and r0850 passes at 9 / 5 —
  the printed-era codes sit in the floor regime the bar refuses on the
  v2 side; their undetected words are the recipe's weight-4–7 pair
  words, which the CRC-32 catches deterministically.
- **Floors:** the hard refusal is an undetected-decode RATE ≤ 1e-4 at
  the 1 % point and at +0.5 dB (10⁵ fresh trials each). It leaves four
  rungs (r0859, r0625, r0406, r0313) without an accepted code at
  11–50 per 10⁵; what the production CRC-32 makes of those decodes:
  every information pattern of weight ≤ 3 caught deterministically, ≤ 4
  where k − p ≤ 3000 (`ladder2/lib/crc_cover.py`, exact), the rest at
  1 − 2⁻³² under the random-CRC model (a heuristic; the words are not
  stored). The bar is the owner's ruling R3, priced per rung in the
  design with one explicit pick rule per option.
- **Decoder budget:** 150 iterations gain 0.19 / 0.12 / 0.35 dB at
  r0313 / r0250 / r0203 and ≤ 0.08 dB above — the bottom three rungs
  are where the 60-iteration budget costs (design §9 R6).

## 2026-09-30 MEASURED — the rung ladder re-measured, candidates below r0547, the construction search

**Status.** Codec-level simulation only: BSC, BIAWGN, iid erasure plus
flips, and confidently-wrong LLRs. The decoder is the production one or
its bit-exact batched twin.
- 200 trials per point, one construction draw per label; differences
  under ~0.02 p or 0.25 dB are noise.
- NO promotion; nothing minted; the rulings are the owner's.
- The record of record, with every table verbatim:
  docs/RUNG-LADDER-STUDY-2026-09-30.md.
- The evidence is in the gitignored scratch/rung-ladder-20260930/.
  (2026-10-09: code in measure/rung-ladder/, data in the evidence archive.)
  (2026-10-11: the data is in measure/rung-ladder/results/, not in the archive.)
  (2026-10-17: the non-reproducible remainder — confirm rows, the row union of
  every search stage, run log, pre-launch identity checks, probes — is in
  measure/rung-ladder/results/ too; its README dates the addition.)

- **The frozen ladder: gaps at 1 % BLER.**
  - BIAWGN: **0.85–1.21 dB** to Shannon (200-trial harness; **0.79–1.05 dB**
    on the 2026-10-01 5000-trial confirm, study §7.4).
  - BSC: **0.07–0.11 bit**. Harness p@1 %: r0547 0.065, r0625 0.050,
    r0700 0.036, r0775 0.021, r0850 0.008.
  - The 2026-07-08 points above stand. They were taken on the test's
    fixed-magnitude-4.0 LLRs; the harness uses log-LLRs.
  - For scale (inferred): the finite-blocklength penalty at n = 4096 is
    ~0.03 bit, or ~0.45 dB.
- **r0550 and r0547 are twins: the same k = 2240 rate, two independent
  draws** (`ldpc-v1/<token>`). They tie on the waterfall: BSC
  detected-only 0.062 vs 0.065, AWGN 1.09–1.21 vs 1.13 dB.
  - r0550 alone carries a **weight-6 codeword on two information bits
    (1157 + 1363)**, verified by encoding. r0547's two-info-bit minimum is
    12.
  - In the harness r0550 threw syndrome-valid wrong decodes, 22/3600 BSC
    and 8/2000 AWGN, where r0547 threw 0. **CRC-32 caught every one.**
  - The "clean at 0.055" above was measured on magnitude-4.0 seeds. The
    low-p 1/200 is one correlated trial repeated down a shared-seed grid.
    The floor has never been seen on paper.
  - Low-weight pair words come from the recipe, not this one draw: r0625
    6, r0775 5, r0850 4.
  - The owner, 2026-09-30: "rung 550 is totally meaningless (keep 547)".
    How that ruling is spelled is owed (study §3, §8 R2).
- **Candidates under the frozen recipe (BIAWGN gap at 1 %):**
  - k = 1664 (r0406): 1.30 dB
  - k = 1600: 1.25 dB
  - k = 1280 (r0313): 1.77 dB, or 1.37 dB with HEAVY_FRAC 0.5
  - k = 1216 (r0297): 1.90 dB
  - k = 1024: 3.06 dB, a floor artefact
- **The recipe's low-rate defect.** Below k ≈ 1300 the uniform row draw
  leaves **8–22 % of checks with no information edge**.
- **The construction search's trial (Tier A):**
  - **Balanced placement** of the information edges removes every
    info-free row, with zero restarts in 36/36 configs per k.
  - It buys **0.45–0.53 dB at k 1280/1216** and 0.16–0.18 dB at k
    1664/1600. The best gaps are 1.35 / 1.35 / 1.13 / 1.09 dB.
  - Seed spread is ~0.025 dB (median), against configuration effects up to
    0.5 dB.
  - Confidently-wrong LLRs at 0.5 % of cells wreck every code alike. That
    is a decoder-axis question.
  - Those were selection-trial numbers. The overnight run's 5000-trial
    fresh-seed confirmation (2026-10-01, study §7.4) found **0.25–0.51 dB**:
    gaps 1.03 / 1.11 / 1.29 / 1.26 dB at k 1664 / 1600 / 1280 / 1216
    (frozen-recipe baselines 1.35–1.77), hard gaps 0.079–0.092 bit; the
    frozen six read 0.79–1.05 dB and were not beaten; r0850 / r0775 / r0625
    / r0550 show syndrome-valid floors of 5 / 6 / 30 / 123 per
    30,000–60,000 trials there. None of the four winners loads in
    production (one heavy class, light degree 3; k 1216's ARA is n > 4096);
    the pair-weight screen does not predict cleanliness. Rulings R1–R10
    owed (2026-10-17).
- **Pair-weight floor.** A floor of 10 on the two-info-bit pair weight is
  too low: a k 1280 code threw 19/2500 wrong decodes on its weight-10 pair
  word. The search's floor is 16.
- **Puncturing.** Shortening beats every puncture variant measured.
  - punct_last's 200/200 failure is a **decoder-budget artefact**, not a
    code property: it decodes 20/20 noiseless at a 200 budget.
  - It keeps a residual under noise: r0547 p 0.06 decodes 18/20 at 200
    and 400 iterations.
  - punct_even costs 5/14/57 per 200 vs shorten's 0/2/6 at r0547.
  - Any puncture needs a new rung id.

## What experiment 013 measured (plan, for the record)

1. **The first decoded-bits numbers**: per-rate tile BLER and net decoded
   b/mm² through the fully blind pipeline (page-class windows, print seeds
   ×3), against the geometry-off footing and the MI proxy.
2. **Rate-ladder recommendation** for c3-class at sim day-0 state (hardware
   decision deferred to real scans per doctrine).
3. **Erasure curve**: tile success vs coverage fraction (fragment-tile
   overlap) — the quantitative backbone of the confetti middle regime.
4. **F9 integrity**: false-certify rate (CRC pass with wrong payload) over
   garbage/adversarial decodes — must be ~2⁻³² i.e. zero observed.
5. **Multi-scan**: LLR-sum combining gain vs the hard-majority gain measured
   in 011/012.

## Open questions (honest list)

1. LLR calibration: GMM LLRs are approximately calibrated; the reliability
   curve on the real channel (and the confidently-wrong tail from
   white-closure/slip events) is unmeasured — PAVA recal is the fallback,
   the 001.4 machinery exists.
2. The warp-slip error structure is bursty within a tile; min-sum assumes
   independence. Sim measures the actual loss; per-tile interleaving is
   deliberately absent (DESIGN §6) to preserve fragment locality.
3. c2/B1-class rates and the A3 color path (per-plane LLRs, MLC per label
   bit) are M2 scope but not v1 — binary c3 first, the measured base case.
4. Decoder is software min-sum; no throughput concern at archive scale
   (target ≥100 tiles/s; a page is ~840 tiles).
