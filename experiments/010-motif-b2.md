# Experiment 010 — motif-based B2 (i2w3) data mode: go/no-go

**Question.** B2 (K RLL i2w3) is our stationarity anchor (82–86 b/mm²
cross-engine) but is NOT data-bearing — the free-running sampler is a
sequential code that desyncs on one dot error, and 004.0a killed the trellis
(dominant error = constraint-*consistent* whole-feature dropout the trellis
can't flag). The proposed fix (agreed 2026-07-07): tile the field with
independent **B×B motif blocks**, each carrying one symbol = which of D legal
motifs it is — locality instead of sequential state. Because i2w3 is
**min-run-only**, juxtaposition closure is FREE (a block legal in isolation
stays legal under any tiling; runs only concatenate), so the dictionary is
exactly the border-legal B×B blocks and data = a random motif index per block.
No arithmetic coding, no cross-block state, no FEC at this layer.

Two pre-registered questions:
- **Q1 (capacity):** does a juxtaposition-closed dictionary clear the ~82–86
  b/mm² anchor?
- **Q2 (the load-bearing one):** does per-motif matched-filter detection
  RECOVER the whole-feature dropouts that killed the trellis, or does a
  dropped 2-dot ink run still flip one legal motif to another (the dropout
  twins)?

## Artifacts
- `motif_codec.py` — shared core: `build_dictionary(b)` (border-legal blocks,
  exact = the capacity DP), `symbols_to_field`, `dropout_pairs`,
  `block_legal`. Validated: dictionary counts match the DP; a 20×20-motif
  tiled field is globally i2w3-legal (closure confirmed).
- `gen_motif1.py` → `build/motif1.ps` (B=7, sha-gated) + manifest + GT: three
  regions — **main** (random over the full 1170 dictionary), **dropout**
  (only the 622 dropout-source motifs, 788 [i,j] twin pairs recorded),
  **control** (only the 548 dropout-immune motifs).
- `analyze_motif1.py` — corner registration, bilinear dot sampling, vectorized
  matched-filter detection, symbol-error / MI→b/mm² / dropout-twin-confusion,
  GO/NO-GO verdict, + a sim round-trip. `tests/test_motif1.py` (10, green).

## Results (2026-07-07) — VERDICT: **NO-GO** for the per-block motif frame

**Q1 capacity ceiling (combinatorial, exact):** legal-block count vs B →
b/dot = floor(log2 D)/B²:

| B | D (legal blocks) | bits | b/dot | b/mm² ceiling (perfect detect) |
|---|---|---|---|---|
| 4 | 2 | 1 | 0.062 | 35 |
| 6 | 116 | 6 | 0.167 | 93 |
| 7 | 1170 | 10 | 0.204 | **114** |
| 8 | 22992 | 14 | 0.219 | 122 |

At B=7 the *perfect-detection* ceiling (114) beats the anchor — so capacity is
not the naive blocker. But that ceiling assumes the alphabet is *decodable*.

**The killer (the real finding): the legal-motif set has minimum Hamming
distance 1.** At B=7, **792 pairs of legal motifs differ by a single dot**
(distance histogram 1:792, 2:2232, 3:3000, …). The dictionary is packed with
zero error-correction margin. Under a measured-B2 error model (whole-feature
2-dot-ink dropout at 004.0a's 18.5% + miss-dominant additive flips; applied
dot BER 0.074 — *below* the real 13%), full-dictionary matched-filter
detection gives **35% symbol error**, and — decisively for Q2 — **the dropout
twins are only 12.7% of the errors.**

**So Q2 is answered, but the hypothesis's framing was wrong.** The whole-block
matched filter *does* largely resist the specific 2-dot-run dropout (twins are
a minority of errors); the dropout mechanism 004.0a warned about is
**secondary**. The dominant obstacle is **generic min-distance-1 packing** —
which the dropout framing never anticipated. The measurement overturned the
premise.

**The distance-pruned-subcode escape hatch collapses too** (greedy packing,
B=7, 49 dots):

| min-dist | #motifs | b/dot | b/mm² ceiling | corrects |
|---|---|---|---|---|
| 2 | 826 | 0.184 | 102 | 0 dot-err |
| 4 | 400 | 0.163 | 91 | 1 |
| 6 | 168 | 0.143 | 80 | 2 |
| 8 | 108 | 0.122 | 68 | 3 |
| 12 | 41 | 0.102 | 57 | 5 |
| 16 | 19 | 0.082 | 46 | 7 |

At 13% dot BER over 49 dots (~6.4 expected flips) reliable hard per-block
decode needs min-dist > ~13 → ≤ ~46–57 b/mm² *ceiling*, already **below the
82–86 anchor** before decode losses. **Per-block hard coding cannot fight 13%
BER in 49 dots at any distance.** Soft-LLR→LDPC across the whole page is the
only real path — and it gains nothing from motif structure where neighbours
sit 1 dot apart (the matched-filter posterior is no more informative than the
raw dot for a min-dist-1 bit).

**Why the dev-simulator was inconclusive (diagnosed, not trusted):** the
measured M281 sim floods a motif field to **0.918 dot-fill / 49% per-dot BER
(3.7× the real i2w3 anchor)** because a motif field is wall-to-wall 2–3-dot
min-run features — exactly the sim's known-broken white-closure regime (the
open M0 fidelity gap: hard 2-dot-white closure measured wrong at c2, sim 43%
vs hw 11%). So the sim's 90% symbol error and its dropout-twin-share=0 are
**artifacts**; the combinatorial min-distance + measured-error model settled
the question instead.

## Consequences / record updates
- **No print needed.** The verdict is combinatorial (min-distance 1) +
  measured-error-model; a physical print cannot change the packing fact.
  motif1.ps is kept as a built, sha-gated instrument (regenerates
  byte-identical) should a future soft-LLR study want a real motif field, but
  no hardware run is warranted now.
- **B2 remains what we banked: the stationarity anchor (82–86 b/mm²) as a
  CHARACTERIZATION field, not data-bearing.** The CLAUDE.md "motif-emission
  bounded upside ~98 b/mm²" projection is REFUTED for the per-block
  independent-symbol frame — min-distance-1 packing caps a decodable subcode
  well below the anchor. Any data-bearing B2 future is soft-LLR→LDPC across
  the page (M2/M3), where the motif structure gives no leverage.
- Durable value produced: `motif_codec.py` (constrained-code enumeration +
  min-distance tooling) and the exact capacity/min-distance/subcode-frontier
  numbers above; reusable if constrained-code questions recur.

## Run log
- 2026-07-07 — built motif_codec + gen + analyzer + 10 tests (suite 110
  green). Capacity DP, min-distance, and measured-error-model analyses all
  zero-print. Verdict NO-GO; no hardware run. build/motif1.ps sha256
  646881cb79c5956644020bbeddcd6acd37fdc9c13f629212588b488a836368a8.
