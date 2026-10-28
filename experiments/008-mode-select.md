# Experiment 008 — MSEL-1: portable mode-selection sheet

**Question.** Given a NOVEL printer with unknown properties: print ONE
portable two-page job as-raw-as-possible, scan it at 1200 dpi on a KNOWN
scanner, run ONE analyzer — and get back the printer's RECOMMENDED OPERATING
MODES selected from the measured portfolio: (i) a ROBUST K mode, (ii) a
HIGH-DENSITY K mode, (iii) a CMY mode (or a "mono engine / CMY unusable"
verdict) — each with the raw numbers and a provisional rate suggestion.

MSEL-1 generalizes DISC-1 (exp 007, which *discovers* the channel — native
dpi, driver path, morphology) into an instrument that *selects modes*. It
deliberately does NOT probe resolution (`/HWResolution` never appears in the
job — that is DISC-1 page 2's role); MSEL-1 measures the **device-default
render path**, which 007.6 showed is the only PS-reachable grid on at least
one major engine class (AltaLink: fixed-600, all requests refused) and the
best-behaved grid on the other (M281: granted-1200 y-stretches the raster).

**Artifact.** `gen_msel1.py` → `build/msel1.ps` (TWO pages, A4,
LanguageLevel 2 portable) + `build/msel1_manifest.json` +
`build/msel1_gt/*.npy`. SEED `paper-store/exp008-msel1`, byte-identical
regeneration, sha-gated. Page 1 carries EVERYTHING decision-critical
(portfolio + adequacy + emission probes + crosstalk + quiet zone); page 2 is
a **K-only** position-replica page (extra K statistics + the color-content
MIC control per 007.8-C1: on engines that lay tracking dots on color pages,
page 2's quiet zone stays clean — the p1-vs-p2 quiet-zone pair replicates
the gating discrimination on the novel printer). Both pages are
duplex-tolerant: own strips + corner marks + plus lattice + END sentinel.

Portability discipline (disc1 idioms, verbatim where possible):
LanguageLevel 2 only; NO `/HWResolution` operation anywhere in the job;
`PageSize [595 842]` inside a stopped guard only; >= 12 mm margins (no
margin probes here — DISC-1 measured <=4 mm on both engines; MSEL keeps the
conservative envelope); strips module = max(3, floor(dpi/100)) dots (fits
the page down to 300 dpi defaults; stripdec self-scales); device query +
payload + strips stream before any inline-data bitmap; masks small→large;
`put_cmyk_bitmap` composites after all masks; END sentinel last-in-page.

## Page-1 block inventory (positions in mm, top→bottom, x/y = top-left)

| block | where | measures |
|---|---|---|
| header labels | y 12–25 | J/S/regen bootstrap + print/scan protocol |
| machine strips 1/2 | y 18.0 / 276.0, x 12 | print-time self-report (LL, RD, RE, PS, IB, PR, V, RV, SN); exp002 LAY=1 format, stripdec-compatible; the RD/RE echo IS the "what grid am I on" datum since MSEL requests nothing |
| corner marks | centers (14.7, 195.3) x (14.7, 282.3) | chiral rotation/mirror + global affine (gen_calpage geometry, byte-identical) |
| plus-mark lattice | 25.4 mm grid, free space | absolute inch scale + warp field |
| K portfolio P1 | y 27, x 13/35/57/79/101/123, 20x20 each | pf1: c2, c3, c4, c5, c6 binary PN fields + RLL i2w3 free-form (all clean K masks) |
| CMY portfolio P1 | y 52, x 13 / 39, 24x30 each | pf1: A3 7-state CMY c3 + A4 {7+K} 8-state c4 (put_cmyk composites; the composite channel — screened on M281-class, clean on AltaLink-class — is part of the mode) |
| per-plane minis P1 | y 52, x 65/78/91, 12x12 | isolated C, M, Y c3 clean masks — the per-plane fallback numbers |
| emission probe pair | y 68, x 65 (P0) / x 88 (P3), 18x8 | P0 = put_cmyk C+M overlapping solids vs P3 = sequential imagemasks + setoverprint + OPM-1 (002.1 paths): overlap preserved-vs-knockout per path + screen fingerprint discriminate the engine's composite class |
| crosstalk row | y 52 x 110–146 (clean C/M/Y/K solids 8x8), y 52 x 148 paper gap, y 62 x 110–137 (cmyk-path CM/CY/MY 8x8) | density/unmix anchors; mono-engine gate; Y-health gate |
| MIC quiet zone | (170, 52) 26x26 | tracking-dot hunt on the COLOR page (pair with page 2's) |
| morphology minis | y 86, x 13–139, 6x6 each | line ladders 1–4 dots H/V, checker 1/2, white holes 1–4 (min-white), 1-on/1-off Nyquist gratings H/V, iso-dot grid @8-pitch |
| tone mini-wedge | y 86, x 141–192, 6x6 | seeded random-dot 10/30/50/70/90% + solid + paper gap |
| K portfolio P2 | y 98, x 13..143 | pf2: c2..c6 + RLL replica (fresh rng labels) — within-page position variance |
| CMY portfolio P2 | y 123, x 13 / 39 | pf2: A3 + A4 replica |
| per-plane minis P2 | y 123, x 67/81/95 | iso2 C/M/Y c3 |
| RLL big anchor | (111, 123) 30x30 | B2 dot-statistics anchor (B2 is the measured cross-engine rate-ladder anchor, 82–86 b/mm²) |
| K portfolio P3 | y 159, x 13/35/57/79 | pf3: c2, c3, c4 + RLL (third position) |
| scanner-adequacy block | y 159, x 103..165 | adq: known-content K c3 (14x14), K c2 (14x14), 2-on/2-off gratings H+V (8x8), high-entropy 1-dot field (10x10, JPEG canary) — see criteria table below |
| CMY portfolio P3 | y 185, x 13 / 39 | pf3: A3 + A4 (third position) |
| END sentinel | y 280.4 | "END <jobid> exp008 msel1" — stream completeness, LAST element |

## Page-2 block inventory (K-ONLY page)

| block | where | measures |
|---|---|---|
| header labels / strips / corners / plus lattice / sentinel | as page 1 | self-contained; strip payload preamble `PHCAL1;PG=2;` |
| K portfolio P4 | y 27, x 13..143 | p2pf1: c2..c6 + RLL (fourth position, duplex back side if the engine duplexes) |
| K big anchors | y 52, x 13 / 57 (40x40) + x 101 (38x38 RLL) | p2big: c2, c3, RLL at ~4x the P-field area — tight single-position CIs (RLL capped at 38 mm = 898 dots: the row-DP sampler's exact-count float path tops out at 900-dot rows) |
| MIC quiet zone (K-only control) | (147, 52) 26x26 | pairs with page-1 quiet zone: lattice on p1 but not p2 ⇒ color-content-gated MIC (007.8-C1 discrimination, portable) |
| morphology minis replica | y 99, x 13–139 | position/back-side morphology check |
| K portfolio P5 | y 112, x 13/35/57/79 | p2pf2: c2, c3, c4 + RLL (fifth position) |

## Area math (page budget)

Content bounds 12–198 x 12–285 mm (>=12 mm margins, unknown printable area).
Field sizes were set so binomial counting noise is well below the decision
thresholds (sigma_pp = 100*sqrt(p(1-p)/N)):

| field | size | cells (N) | sigma at working point |
|---|---|---|---|
| K c2 20x20 mm | 472² dots | 236² = 55 696 | ±0.14 pp @ 12% |
| K c3 20x20 | 157² | 24 649 | ±0.11 pp @ 3% |
| K c4 20x20 | 118² | 13 924 | ±0.08 pp @ 1% |
| K c5 / c6 20x20 | 94² / 78² | 8 836 / 6 084 | ±0.08 / ±0.09 pp @ 0.5% |
| RLL 20x20 (dots) | — | 222 784 | ±0.07 pp @ 13% |
| A3 24x30 (7 states) | 189x236 | 44 604 (≈6 372/state) | MI ±≈0.01 b/cell class |
| A4 24x30 (8 states) | 141x177 | 24 957 (≈3 120/state) | — |
| adequacy c3 / c2 14x14 | 110² / 165² | 12 100 / 27 225 | ±0.20 pp @ 5% / ±0.23 @ 18% |
| iso C/M/Y c3 12x12 | 94² | 8 836 | ±0.21 pp @ 4% |
| p2 big c2 / c3 (40x40), RLL (38x38) | — | 222 784 / 99 225 cells; 806 404 dots | ±0.07 / ±0.05 / ±0.05 pp |

Position replication: c2/c3/c4 at **5 positions** (3 on p1, 2 on p2), plus
the p2 big c2/c3 pair (6 scored rows for c2/c3, 5 for c4); c5/c6 at 3
positions; RLL at 5 positions + 2 big anchors (7 rows); A3/A4 at 3
positions (page 1 only — page 2 stays K-only by design). All decisions
run on WORST-position numbers (the within-job proxy for the multi-sheet
minima doctrine; 001/004 measured real within-page position variance).
Every 10k-cell field buys ±0.1–0.2 pp; the position spread, not counting
noise, is the expected dominant uncertainty.

## PRE-REGISTERED decision rules (written before the analyzer; the analyzer
implements EXACTLY these — any deviation is a bug or a logged amendment)

Tier vocabulary (from the cross-engine record: c2-class 11–14% marginal +
day-fragile on both engines; c3-class 2–3.7% solid; c1/beyond-Nyquist dead):
**solid < 1%, marginal 1–8%, fragile 8–20%, dead >= 20%** (raw hard cell BER).

R1. **K statistics.** Per cell size c in {2,3,4,5,6}: worst-position raw
    hard BER over ALL scored positions and pages (big fields included).
    Footing: marks-affine + per-field GT-template phase lock + GT-ink-quantile
    threshold ("discovery grade" — the 007.6 median-rule floor bug is
    avoided by the quantile rule; numbers are ~1–2 pp pessimistic vs the v4
    tracker at c2 on warped sheets).
R2. **ROBUST-K** = the LARGEST portfolio cell whose worst-position BER
    < 0.5% (= the 1% solid-tier boundary with a 2x margin). If none passes
    at 0.5%, the largest cell with worst < 1% is reported with a
    "reduced-margin" flag; if none, verdict "no robust K mode in portfolio —
    extend the ladder or reject the engine".
R3. **DENSE-K** = argmax over cells with worst-position BER < 8% (the
    marginal/day-fragile tier is EXCLUDED per 004.0 day-2 evidence) of
    density-weighted capacity proxy (1 − H2(BER_worst)) x (600/(25.4 c))²
    b/mm². Whenever c2 lands in [8%, 20%) the analyzer prints the excluded
    c2 upside line (what B1-class context detection + LDPC might recover)
    so the exclusion is visible, not silent.
R4. **RLL / B2 anchor** (reported, not a selected mode): dot BER + proxy
    b/dot = H_sampler x (1 − H2(dot BER)) (the 003.0 analyze_modprobe
    formula), x 558 dots/mm². Null control for constrained fields uses the
    field's OWN lag-8 decorrelation as the expectation (run-correlated GT:
    the shifted-GT null is ≈0.487, not 0.500). Compare against the 82–86
    b/mm² cross-engine band — a large deviation flags an unusual dot
    channel.
R5. **CMY decision chain** (color scan required; else "needs color scan"):
    a. MONO GATE: plane selectivity(P) = D_primary(P) − mean(D_other-two)
       on the clean-mask solids (C in r, M in g, Y in b). If selectivity
       < 0.10 for ALL of C, M, Y → **"mono engine / CMY unusable"**, stop.
    b. Y-HEALTH GATE: D_b(Y solid) >= 0.5 x D_r(C solid). (C is the
       yardstick, not M: the M→g crosstalk gain 1.31 makes M an inflated
       reference. Calibration: M281 healthy Y reads ratio ≈0.68, starved-Y
       ≈0.33 — the 0.5 boundary splits the measured pair.)
    c. A3 GATE: worst-position A3 MI >= 1.0 b/cell (within-field
       checker-split QDA on per-cell CORE density features, rgb-only per
       007.8-C2 — core = cell trimmed by cp//3 px per side, density =
       -log10(refl): the LAYERS.md CellFeatures currency; label:
       within-field split, NOT cross-page footing) AND Y healthy
       → **CMY mode = A3 7-state c3**, with the channel class attached:
       "unscreened-composite" vs "screened-composite" from the screen-FFT
       hunt (analyze_disc1 band/off-axis machinery; classifier = off-axis
       peak > 50x the median of its OWN +-8-lpi radial annulus — annulus
       normalization is immune to radially-colored noise floors; the 007.6
       band-median ratio and its 300x threshold are kept per peak as the
       real-scan-calibrated diagnostic) + the P0/P3 emission verdicts
       (overlap preserved-vs-knockout per path).
    d. PER-PLANE FALLBACK: else if >= 2 of the three isolated-plane c3
       minis have worst-position BER < 10% → "per-plane clean-mask CMY c3"
       (failing plane de-weighted; numbers per plane attached).
    e. else **"CMY unusable on this engine/scanner path"**.
R6. **Rate suggestions** (every one labeled PROVISIONAL-SINGLE-SHEET):
    K modes: 0.85 x (1 − H2(BER_worst)) b/cell (85% of hard-BER capacity —
    a placeholder discount until the M2 ladder is measured); CMY: 0.85 x
    worst-position MI. Final ladders are set on MULTI-SHEET MINIMA (007.9);
    MSEL-1 numbers from one sheet+day are mode SELECTORS, not rate setters.
R7. Every reported number carries the footing label (geometry, training)
    and the scanner-adequacy verdict of the scan that produced it.

Pre-registered SIM expectation (M0 gate, M281 simulator defaults,
geometry=False sim-genie footing): robust-K = c4-or-larger (the largest
qualifying cell — expected c5 or c6), dense-K = **c3** (sim c2 ≈ 15% =
excluded fragile tier; sim c3 ≈ 3.5%), CMY = **A3-7st-c3, screened-class**
(sim MI >= 1.0 through the 165-lpi rescreen + measured crosstalk compose;
sim Y-health ratio ≈ 0.68 via the crosstalk diagonal). A run that selects
anything else fails the gate.

Pre-registered HARDWARE envelopes (M281 home reference, would-be run):
c2 11–16%, c3 2–5%, c4 0.2–2%, c5/c6 < 1.5%, RLL 12–17% dots; A3 MI 1.3–2.0
b/cell screened-class; adequacy: all checks pass on the home flatbed.
Outside = finding, not failure.

## Scanner-adequacy block + criteria (pre-registered)

The sheet carries a compact self-test region (page 1, y 159, x 103–165) so
that ANY (sheet, scanner) pair yields a scanner verdict alongside the
printer verdict:

| check | statistic | pass criterion | failure meaning |
|---|---|---|---|
| self-ID | strips CRC (stripdec) | >= 1 of 2 strips CRC-ok per page | geometry/sampling/compression too poor even for coarse modules |
| solid-class decode | adq/k_c3 hard BER (known content, 12 100 cells) | < 5% | scanner NOT adequate for archive recovery at any mode |
| marginal-class decode | adq/k_c2 hard BER (27 225 cells) | < 18% | c2-class (B1) modes unusable through this scanner |
| sampling | 2-on/2-off grating contrast (H and V), fraction of ideal fundamental | >= 0.20 both axes | effective sampling below ~2 px/dot at the print grid (px/cell ladder floor, 007.3) |
| compression | 8-px blockiness ratio on the high-entropy field AND high-pass noise std in the quiet zone | ratio < 1.25 AND std >= 1.0 grey counts | block-coded (JPEG-class) scan path: <5-dot features erased, context detectors MISFIRE (007.2) — hard/global detection only, expect ~+6 pp at c2-class |

**Verdict rule:** "scanner adequate for archive recovery at mode M" iff
strips pass AND adq-c3 < 5% AND sampling passes — and additionally, for
c2-class M, adq-c2 < 18% AND compression passes. A compressed-path scan
downgrades the K recommendation footing but does not invalidate solid-tier
modes (007.2 addendum: JPEG costs little at RLL/c3-class features).
If quiet-zone noise std < 0.5 counts the compression check returns
INDETERMINATE (synthetic render or heavily post-processed scan).

## Transfer-standard doctrine

Any characterized MSEL-1 sheet + its reference scan on a KNOWN scanner is a
**printer-independent scanner characterization standard** (the 007.2
same-sheet-pair method: rescanning the SAME physical sheet on scanner B and
differencing against the scanner-A reference factors the printer out
entirely). Operationally: (1) keep every printed MSEL-1 sheet and its home
1200-dpi reference scans (grey + color, sha256 in the run log); (2) to
characterize a new scanner, rescan any archived MSEL-1 sheet there and run
the analyzer on both scans — the adequacy-block deltas (c3/c2 BER shift,
grating contrast, blockiness, noise floor) ARE the scanner
characterization; (3) the pre-registered adequacy criteria then apply to
the new scanner directly. MSEL-1 sheets double as this standard the moment
their reference scan exists; no extra printing is ever needed for
scanner-side questions (007.9 doctrine: scan-side questions are free).

## Print protocol (portable — NOT scripts/print_plane.sh unless the target IS the home M281)

1. ONE job, TWO sheets (or one duplexed sheet — fine, scan both sides), A4,
   plain paper. Take `build/msel1.ps` (sha256 in the manifest; regenerate
   with `gen_msel1.py` if in doubt — byte-identical).
2. Most-raw path available, in order: raw queue (`lp -d <queue> -o raw`),
   direct 9100 (`nc <host> 9100 < msel1.ps`), else any PostScript driver at
   100% scale / no fit-to-page / default quality.
3. **Hand-note in pen on sheet 1**: printer model, queue/driver, path used,
   date. Mark page 2 "p2" if its header is illegible.
4. Loupe check: strips top+bottom on BOTH pages, both END sentinels present.
5. Log the run below (date, engine, media, path, oddities, sha of the .ps).

## Scan protocol

1. KNOWN scanner (home flatbed = the characterized reference), both pages:
   1200 dpi GREY (K portfolio + adequacy) and 1200 dpi COLOR (page 1: CMY
   portfolio, crosstalk, emission probes, MIC hunt), descreen/sharpen/
   auto-contrast OFF, flat, all four edges in frame. Never mix grey/color
   for absolute y (002.0b).
2. Multi-scan option: 3–4 re-placed passes per page (004.0b/006.1 lever) —
   score each, combine later; MSEL's decisions use single-scan numbers.
3. Scans into `scans/` (untracked), sha256 in the run log. Suggested names:
   `msel1-<printer>-p<1|2>-<grey|color>.png`.
4. Analyze: `env/bin/python analyze_msel1.py --grey1 <p1-grey>
   [--color1 <p1-color>] [--grey2 <p2-grey>] [--json out.json]`.

## Pre-flight (gates any print) — GREEN 2026-07-07, 9 tests, ~24 s

`pytest -q tests/test_msel1.py` (also standalone-runnable):
1. byte-identical regeneration (sha gates reuse);
2. portable stream structure: LL2, Clean7Bit, %%Pages: 2, exactly ONE
   guarded PageSize request, ZERO /HWResolution-setting operations
   (currentpagedevice READS only), masks before composites, both sentinels
   last-in-page, P3 carries setoverprint + guarded OPM, <= 16 MB;
3. manifest geometry: bounds, per-page disjointness with composite/pair
   grouping, labels clear;
4. GT integrity (>= 60 files, shapes, state grids);
5. gs pnggray -r600 pixel-exact: pf1/k_c2/c3/c6, pf1/k_rll, adq/k_c3,
   adq/entropy, morph/chk1 (p1) + p2big/k_c3, p2pf1/k_c2, p2/morph/chk2;
6. gs tiffsep -r600 pixel-exact: pf1/a3_c3 C/M/Y + em/p0_cm C/M;
7. stripdec round-trip on 1200-dpi renders, both pages (p1 plain
   PHCAL1;LAY=1 payload; p2 PHCAL1;PG=2 preamble; J/S/PS fields);
8. FULL analyzer on the clean 1200 grey renders: corner-mark registration
   (residual 0.00 dots, 39+49 landmarks), 4/4 strips CRC, 23 K rows + 7
   RLL rows all < 0.5% with null controls ok, robust=c6 (full margin),
   dense=c2 (rule monotonicity: a perfect channel legitimately unlocks
   c2), CMY="needs color scan", adequacy solid-class pass + compression
   INDETERMINATE (synthetic render, as specced);
9. M0 SIM GATE (measured M281 simulator, geometry=False sim-genie
   footing): sim c2 13.7% (fragile, excluded, upside note printed), c3
   2.9%, c4-c6 ~0%, RLL 12.2% -> robust=c6 (c4-or-larger ✓), dense=c3 ✓,
   A3 through rescreen+crosstalk compose: MI 1.139 b/cell, screen hunt
   finds 164.7 lpi @ 14.0° (annulus-rel 5.9e4; unscreened control reads
   12 — classifier clears both ways), Y-health ratio 0.680 healthy ->
   CMY=A3-7st-c3 screened-class ✓. The pre-registered recommendation
   comes out exactly.

## Limitations (stated up front)

- SINGLE-SHEET, SINGLE-DAY: every recommendation is PROVISIONAL. Day/
  consumable variance is the dominant unmeasured axis (004.0 day-2 c2
  regression; 007.9: one different-day reprint batch is the closure);
  within-page position spread (5 K positions, 3 CMY positions) is the
  built-in proxy, not a substitute.
- Discovery-grade decode (marks-affine + phase lock): ~1–2 pp pessimistic
  at c2-class vs the v4/strip-tracked pipeline; c2 tier calls near the 8%
  boundary should be re-run through the v4 path before acting.
- The composite channel class (screened/unscreened) rides on the FFT hunt
  band 110–320 lpi calibrated on the M281 positive control; an exotic
  screen outside that band would be missed (the P0/P3 emission pair is the
  independent cross-check). The annulus-relative classifier threshold (50x)
  is validated both ways on the measured SIMULATOR only — the first real
  MSEL run should confirm it against the 007.6 band-median record (both
  ratios are reported per peak).
- MI from within-field checker splits is mildly fold-optimistic vs
  cross-page training (004.0 measured the gap at Δ0.03 b/cell — small, but
  the label matters).
- No resolution probing: engines whose default grid is NOT their best grid
  (none measured so far) would need DISC-1 first. Protocol: on a brand-new
  engine print DISC-1 + MSEL-1 together; DISC-1 answers "what is it",
  MSEL-1 answers "how should we drive it".

## Run log

- 2026-07-07 — sheet built + preflight green (9 tests, full repo suite 90
  green). `build/msel1.ps` sha256
  `4c7d40f92c1627abf205f305c11b5fde193a752f8a9e543ec4b4bafc8be604da`
  (5 447 934 bytes, 206 patches: 127 p1 + 79 p2, 80 plus marks).
  Build notes: p2big RLL sized 38x38 (900-dot sampler cap); A3 detector
  upgraded to core-density features during preflight (sim MI 0.970 -> 1.139
  b/cell — whole-cell means left the screened-sim A3 just under the
  pre-registered 1.0 floor; the fix is a detector improvement, not a
  threshold move); screen classifier switched to annulus normalization
  after the band-median ratio false-alarmed on the simulator's
  radially-colored noise floor (unscreened control 3698x band-median vs
  12x annulus). NOT yet printed.

- (next: print on a novel engine per the protocol above; also worth a
  home-M281 shakedown print — it validates the whole loop against the
  known channel and its sheets become the first transfer standard.)
