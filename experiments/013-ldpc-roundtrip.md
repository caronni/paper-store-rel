# Experiment 013 — the first decoded bits (Layer 3 LDPC, sim, zero print)

**2026-07-08.** Every density number before this experiment was an MI proxy.
Here user bits ride ldpc.encode_page → compose_page (layout_version 3) → the
measured channel → the fully blind receiver → per-tile e-IRA LDPC decode →
CRC-32 certification, and only certified bits count. Harness:
analyze_e013.py (--quick smoke 37 s; full 351 s); report
build/e013_report.json. Codec-level frontiers + construction provenance:
docs/FEC-DESIGN.md v0.2 + the ldpc.py docstring (normative). Suite 208.

## Headline: first certified-bits densities (fully blind, 600×600-cell
interior windows, print seeds {0,1,2}, 72 complete 64-cell tiles each)

| rate | blind tiles ok | net certified b/mm² | footing tiles ok |
|---|---|---|---|
| r0550 (0.547) | 181/216 (84%) | 21.8 | 216/216 |
| r0625 (0.625) | 178/216 (82%) | 24.7 | 216/216 |
| **r0700 (0.703)** | **189/216 (88%)** | **29.7** | 186/216 (see F2) |
| r0775 (0.781) | 154/216 (71%) | 27.0 | 206/216 |
| r0850 (0.859) | 145/216 (67%) | 28.1 | 136/216 |

**Net decoded optimum ≈ r0700.** CORRECTION (013.1, same day): the 29.7
b/mm² window number UNDER-CREDITS — it divides complete-tile bits by the
full window area while excluding the window-edge tiles (18% of payload
cells) from the numerator; a measurement-window artifact, not a page cost.
**Page-level honest numbers: 40.8 b/mm² at 100% certification (measured
page capacity 2,189,231 bits / 53,720 mm²), 35.7 b/mm² at the measured
87.5% tile success** — 75% of the sim blind-MI ceiling (47.5 incl.
pilots). Waterfall: warp-present-vs-warp-free −13% (013.2 RELABEL: this is
NOT a "blindness" tax — the measured blind-vs-footing gap on clean
fragments is +0.37 pp; the line bundles (a) irreducible warp physics —
sub-pixel phase precession from the +0.62% y-scale, period ≈54 cells ≈ one
tile, a TESTABLE F1 band candidate; (b) localized slip-boundary damage;
(c) F2 detector/content artifact leakage, which exists at geometry=False
too and is mislabeled as geometry here), rate+CRC −14% (mostly TAIL-forced
margin), tile failures −12.5% (tail damage, F1) — the bands are charged
twice; fixing F1/F2 projects r0775 × ~98% ≈ 45 b/mm² = 95% of the blind
ceiling (ESTIMATE). The designed-unbuilt lever for the tile-failure line:
CERTIFIED-TILE DECISION FEEDBACK (LAYERS F4/F10) — each certified tile =
3,983 perfect anchor cells; at 87.5% certification every failed tile is
surrounded; loop = certify -> re-template local warp/detector -> resample
-> re-decode (turbo-equalization shape). Queued with F1.
F9 integrity: **zero wrong-payload certifications** across every decode in
the run (1000+ tile decodes incl. adversarial), 0/72 certifications under a
corrupted address hypothesis, and the codeword-substitution gauntlet
(valid-other-codeword flips, syndrome-invisible by construction) was caught
by CRC 300/300.

## Findings

**F1 — Tile success is governed by banded error TAILS, not mean BER.** The
BSC frontier says r0700 carries a flat 3.5% channel at ~98.5% tile success;
the blind pipeline delivers 88% at a 2.4–3.3% window mean. Error maps show
fixed-position horizontal bands (present across print seeds ⇒ deterministic)
plus seed-dependent vertical streaks at 5–9% local BER; tiles overlapping a
band fail, everything else decodes in ~3 iterations. Mean BER lies; the
spatial tail sets the rate. This is exactly the measurement per-tile coding
exists to expose, and it redirects the next effort: fix/erase the bands
(LLR down-weighting of low-quality regions, PAVA recal) rather than buy
blanket rate margin.

**F2 — Detection BER is CONTENT-dependent at the ~1 pp level (open
mechanism).** A/B on the identical channel draw (same window, same print
seed, geometry=False): random-payload page 1.95% hard BER vs LDPC-framed
page 2.88%, with a content×seed hot column (6.45% vs 2.75% at tile-col 11,
gone at print seed 1). Each rate row above is a different page, so this
injects page-to-page variance (visible as the non-monotonic footing column).
Suspect: content coupling through lock_grid's decision-directed refinement
or the self-clock phase profiles. Does NOT affect certification (F9 clean);
does cost rate margin. → queued probe (z-item), mechanism unidentified.

**F3 — Naive multi-scan LLR summation is NOT robust to per-scan slip
variance (negative result).** Adversarial print seed 314, 3 scans: singles
56/72, 56/72, 69/72 certified; 3-scan LLR SUM = 57/72 — *worse than the best
single scan*. Mechanism: a slipped region contributes confidently-wrong
LLRs that poison the sum (the 012 hard-majority result, 5.80→2.12% bit BER,
survived because majority voting is bounded per scan). The designed fix is
already in PILOTS-DESIGN role (d): per-scan/per-region combining weights
from pilot agreement — unimplemented. Until then, per-scan decode + take
any certified tile (tile-level union: 70/72 here) strictly beats LLR
summation.

**F4 — The erasure/coverage curve matches the codec frontier** (confetti
middle regime, PILOTS-DESIGN §14): partial tiles at 70–95% coverage decode
0/3 at r0700 (30% erasures exceed its budget, as capacity arithmetic
demands) and **3/3 at r0550**; both rates die below 70% coverage.
Fragment-tile recovery = lower ladder rungs, quantified.

## Decisions folded in (user, this session)

- Data-tile size and pilot period/density stay INDEPENDENT knobs (the
  tile=60 alignment option rejected; shortening absorbs the misalignment).
- Shortening, not puncturing, for pilot displacement; CRC-32 stays the
  certification gate (F9 measured basis above).

## Caveats

- Sim-only, single sim-day channel state; rate recommendation (r0700 for
  density, r0550 for fragment robustness) is the SIM ladder — hardware rates
  wait for e012-sheet scans and multi-sheet minima (doctrine).
- Per-rate pages differ in content ⇒ F2 variance is folded into the ladder
  numbers; a content-controlled re-run is cheap once F2's mechanism is
  found.
- Window area includes pilots; net numbers are end-to-end honest (certified
  user bits / total printed area).

## Run table

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 013.0 | 2026-07-08 | analyze_e013.py full (rate ladder ×3 seeds, erasure bins, F9, multiscan) | build/e013_report.json | deterministic mod timings |
| 013.0 | 2026-07-08 | certification probes: independent H·c=0 all rates; valid-codeword substitution 300/300 CRC-caught | — | — |
