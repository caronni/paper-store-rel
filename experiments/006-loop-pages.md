# Experiment 006 — loop pages (full-area layer-1 measurement, BW + C)

**Question.** The retrieval-loop headline numbers: verified LAYER-1 yield of
a full page per profile — marks+strips registration (no genie, no pilots),
blind detection, multi-scan protocol — for the two champions: B1 c2-K
(LOOP-K) and the 7-state c3 CMY alphabet (LOOP-C). Plus the probe row that
retires or promotes the remaining b/w modulation ideas.

**Sheets** (`gen_e006.py`, sha-gated, byte-identical regeneration; preflight
`tests/test_e006.py` 6/6 + full suite 62 passed):

- `build/e006bw.ps` — jobid 3c687565, 5.90 MB, sha 797232ee1a51a3c8…
  All-K clean masks (only composites: the 6 cmyk ref solids). 17 sync
  strips (3-row known c2, full width, 360-dot pitch from y=472); bands
  0-9 = B1 c2 payload (27,863 mm²); bands 10-12 = B2 i2w3 (8,359 mm²;
  NOTE: sampler transposed for width>900 — constraint verified both axes,
  but run-orientation statistics differ from 003/004 fields; BER
  comparability carries that caveat, entropy 0.322 b/dot in manifest);
  bands 13-15 probes: i3w3 (599 mm²), fill75 c2 (599 mm²), anisotropic
  2×3 + 3×2 cells (749 mm²), 3-level grey c3+c4 (597 mm²); band 16 canary
  (B1 + RLL + K/C/M/Y solids + paper); E004-style refs row; 4 chiral
  corners; END sentinel.
- `build/e006c.ps` — jobid a64487e9, 25.52 MB, sha 15e27c95d81c7a0f…
  Same skeleton; bands 0-15 = 7-state c3 alphabet via put_cmyk_bitmap
  (44,581 mm²; bands 0/7/15 manifest-flagged "training" — identical
  construction, flag only); strips/canary/refs identical to BW.

**Registration/decode plan**: corners → affine; strip tracker
(`strip_tracker.py`, validated on the measured simulator: 98% window lock,
print-frozen wander recovered through 4 synthetic scans) → absolute
(dy,dx) anchors at 360-dot pitch; payload sampled at strip-interpolated
offsets; B1 blind ctx + frozen PAVA recal; B2 fixed-rate + run stats; A3
blind-EM (crosstalk-centroid init) + cross-band QDA; multi-scan LLR/residual
combining per 004.0b.

## Pre-registered envelopes (from 001-005 measured record)

| target | single scan | multi-scan (3-4) |
|---|---|---|
| B1 bands ctx BER | 6-9% (day-state) | 4.5-6.5% |
| B1 recal MI | 0.66-0.75 b/cell | 0.75-0.82 |
| B2 bands dot BER | 12.5-15% (orientation caveat) | 11-13% |
| A3 bands MI (cross-band QDA / blind-EM) | 1.7-2.0 / -0.07 | +0.03-0.08 vs single |
| strip-tracked vs genie gap | ≤0.5 pp (B1), ≤0.1 b/cell (A3) | — |
| i3w3 probe | dot BER 8-13%, ZERO 2-run dropouts by construction | — |
| fill75 probe | fa(white→ink) BELOW adjacent B1 bands if the toner-mass hypothesis holds; miss may rise | — |
| aniso 2×3 vs 3×2 | BER between c2/c3 classes; V>H asymmetry between the two orientations | — |
| grey3 c3/c4 | MI ≤ same-cell binary (falsification patch; expect level drift sensitivity) | — |

Outside-envelope = finding, not failure. Headline deliverable: bits/page at
layer 1 per profile (calibrated MI × area), with the multi-scan ladder.

## Protocol

1. Print each page ONCE via the raw path (user-authorized this session).
2. Scans, enhancements OFF, 1200 dpi: BW page → 3-4 GREY scans (flat,
   flat-displaced, 180°, flat repeat); C page → 3-4 COLOR scans (same
   placements). Grey and color are separate transport passes (004.0b) —
   never mix modes within one decode.
3. Analysis: 006.0 analyzer (to be built on the scans) per the plan above.

## Run log

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 006.0 | 2026-07-05 | generated both pages, preflight 6/6, suite 62 passed | build/e006bw.ps, build/e006c.ps | 797232ee…, 15e27c95… |
| 006.0 | 2026-07-05 | two-auditor print gate: BOTH PASS, zero blocking (all 40 BW GT crops + all 16x3 C-band separations bit-exact; stream discipline verified; one cosmetic label-descender note) | — | — |
| 006.0 | 2026-07-05 ~22:30 | PRINTED e006bw.ps, one sheet (user-authorized): <host> raw 9100 via print_plane.sh, 5,900,887 bytes, sha confirmed at send | build/e006bw.ps | 797232ee… |
| 006.0 | 2026-07-05 ~22:31 | PRINTED e006c.ps, one sheet (same authorization): 25,521,346 bytes, sha confirmed at send | build/e006c.ps | 15e27c95… |
| 006.3 | 2026-07-06 | CROSS-ENGINE: both loop pages printed on the Xerox AltaLink C8245 (raw 9100, user, office) + home-flatbed 1200 single scans; stock 006 pipelines. HEALTHY LOOP-C NUMBER: 1.442 b/cell = 89.4 b/mm² loop-legal; LOOP-BW strips-alone ctx 7.32% / MI 0.680 = 94.8 b/mm² (best legal B1 on record); genie-training parity replicates on engine 2; blind-EM dead even furniture-init → receiver = furniture-QDA, no EM; aniso probe FLIPS (wide beats tall). Full results + caveats: experiments/007-office-disc.md 007.6 | scans/xerox-loop-c-hp-scan.png, scans/xerox-loop-bw-hp-scan.png | 1dccecf5…, fdc06f55… |

---

## 006.1 — E006-BW first legal layer-1 run (2026-07-05 late, 4 scans)

Scans: 006bw-scan-1-color (f80936b7…), -2-bw (82af6b70…), -3-bw (14acb3b2…,
placement identical to 2), -4-bw (d4ff514e…, re-placed). Analyzer
`analyze_e006bw.py` → `build/e006bw_report.json`. Pipeline: corners-only
affine (refine=False — cal_core's ≥6-landmark refinement doesn't apply to
strip pages), 17-strip tracker (lock 1.00 on every scan), strip-interpolated
sampling, blind detection throughout, frozen 001.4 recal map. Genie column
computed per band on s2 for the legality gap.

**Headline: strips-alone geometry costs +5.82 pp ctx BER vs genie (band
range +0.83 to +15.95).** The best bands are already at genie; the worst
cross violent step regions where linear interpolation between 15.24 mm
strips leaves ~1-dot mid-gap residual — exactly the between-strip
self-clock/DP refinement stage the tracker design reserved. That stage is
the next build; strips-alone is NOT the final legal number.

| metric | s2 (grey, single) | 3 grey | +color (4) |
|---|---|---|---|
| B1 ctx | 13.59% | 12.65% | 12.64% |
| B1 recal MI → b/mm² | 0.489 → 68.2 | 0.521 → 72.6 | 0.527 → 73.5 |
| RLL dot BER | 15.99% | 14.91% | 14.37% |

(All carry the strips-alone warp handicap; genie-class geometry on this
sheet would put single-scan B1 ctx at ~7.8%.)

**Probe verdicts (same-warp comparisons, valid despite the handicap):**
- **grey3 RETIRED, both cells** — exactly as the falsification envelope
  predicted: c3 acc 0.700 / MI 0.553 vs binary's ~0.97; c4 acc 0.860 /
  MI 0.925 of 1.585 (= 32 b/mm² < binary c4's 34). Level means separated
  (162/97/50 at c4) but the confusion kills it. Question closed with data.
- **i3w3 RETIRED** — dot BER 13.75% ≈ i2w3's, so the entropy cost dominates:
  0.2824 × (1−H₂(.1375)) = 0.120 b/dot = 67 b/mm² < i2w3's 82-class.
  Min-ink-3 does not pay on this engine.
- **aniso: V>H made quantitative** — 2×3 cells (tall) 11.69% vs 3×2 (wide)
  20.50% cell BER on identical warp. Tall-cell orientation is worth ~9 pp.
  2×3 even beats c2 on this warp (11.7 vs 13.6) — worth a refined-warp
  re-look, though its 93 cells/mm² ceiling limits the upside.
- **fill75: no closure benefit at this channel state** — 15.04% with
  fa ≈ miss (15.0/15.1), WORSE than B1 bands; today's print shows balanced
  errors (unlike E004-day2's fa-dominant closure), so the reduced-toner
  hypothesis remains untested against an actual closure day.
- **Placement diversity beats repetition**: adding the unmoved s3 to s2
  gained +0.005 MI; adding the re-placed s4 gained +0.027. Multi-scan
  protocol should MOVE the sheet between scans.

Next: between-strip refinement stage (self-clock DP anchored at adjacent
strips) → close the 5.8 pp gap → then the E006-C color run and the
committed layer-1 page numbers.

---

## 006.2 — E006-C first run: starved-Y channel sample + training-protocol validation (2026-07-06)

Scans: 006col-scan-1-bw (d15a8dcc…, grey), -2-col (dd14e5f8…), -3-col
(19530ebb…, unmoved), -4-col (ab61cdf0…, 180°). Analyzer
`analyze_e006c.py` → `build/e006c_report.json`. Registration clean on all
four (180° resolved by chiral corners); strip lock 1.00 everywhere.

**Architecture headline: the 3-training-band loop-legal protocol is at
GENIE-TRAINING PARITY** — TRAIN-QDA (fit only on the manifest-flagged bands
0/7/15, predict the other 13) vs CROSS-QDA (16-fold genie training):
Δacc +0.15 pp, ΔMI −0.002. The QDA fold-optimism saga is now closed at the
loop level: 2% of page area as training furniture buys full labeled-training
performance, blind.

**Channel headline: this is a STARVED-Y sample, and the alphabet paid.**
TRAIN MI 0.770 b/cell = 47.7 b/mm² (record low vs 1.48–1.90 on healthy
sheets). Cause measured, not guessed: Y ref-solid density 0.374 — HALF of
CAL-1's already-weakest dmax (0.772) — with a monotone fade down the page
(Y-state class-mean D_b 0.447→0.376, MY 0.558→0.457). C (1.13) and M (1.16)
are healthy; K 1.36. The three Y-bearing states collapse into their Y-less
neighbors. Canary K decodes (c2 14.9–16.1%) match the same-day BW sheet —
the K channel is unchanged; this is purely a Y consumable event.

**Blind-EM collapsed (0.554 MI, −0.22 vs TRAIN)** — the crosstalk-centroid
init is a CAL-1-era prior and the channel has drifted a consumable-change's
worth. Rule confirmed in the wild: EM initialization must come from
on-page training furniture (or a fresh CAL), never stale priors — exactly
the "re-run CAL on consumable change" doctrine, now with a measured failure
mode attached.

Multi-scan ladder (TRAIN): 0.770 → 0.774 → 0.798 MI (3 scans) = 49.5 b/mm².
Rotated-alone slightly worse (as on BW). Best band 1.003 / worst 0.444 —
the worst bands are the Y-starved bottom.

Disposition: page numbers NOT comparable to healthy-channel record; sheet
retained as a labeled degraded-channel robustness sample. LOOP-C re-measure
after Y cartridge replacement (reprint e006c.ps verbatim — sha-gated).
