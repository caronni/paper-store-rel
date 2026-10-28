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
