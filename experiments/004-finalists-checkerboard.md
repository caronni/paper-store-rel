# Experiment 004 — finalists checkerboard (M2 four-cell matrix head-to-head)

**Question.** Which cell of the M2 modulation matrix delivers the most
bits/mm² on this engine, measured position-fairly on ONE sheet, and does the
screened color alphabet survive cross-region training (the QDA-fold-optimism
caveat)? Four candidates, two tracks:

| cell | construction | channel | pre-registered envelope (see below) |
|---|---|---|---|
| A3 | 7-state CMY alphabet {W,C,M,Y,CM,CY,MY}, cell=3 (002.2) | screened composite (put_cmyk_bitmap) | same-fold MI 1.48 ± 0.15 b/cell; cross-tile-trained reported alongside (first measurement) |
| A4 | {7+K} 8-state alphabet, cell=4 (002.2) | screened composite | same-fold MI 1.98-2.36 b/cell |
| B1 | K solid cells, cell=2, incumbent construction | clean K imagemask | hard 10.5-12.5%; ctx 4.3-5.6%; recal MI 0.70-0.85 b/cell (003.0a: 4.59% / 0.785) |
| B2 | K 2-D RLL i2w3 free-form (003.0) | clean K imagemask | naive rank-threshold dot BER 12-15% (003.0: 13.1%) |

**Sheet.** `gen_e004.py` → `build/e004.ps` (sha-gated; regenerates
byte-identically). 8×8 grid of 21×30 mm tiles, 16 per class, each class exactly
2× per grid row and 2× per grid column (cyclic base + seeded row/column
permutations) — position fairness in BOTH page axes by construction; a
half/half or banded layout would bake the measured position variance (Y
drift −4.9 dots to page bottom, c3 2.1→3.74% best→conservative) into the
verdict. Tile gaps 2.5 mm (region disjointness: 002.2 measured clean masks +
screened composites coexisting on one page); 49 gap-crossing plus marks + 4
chiral corners + default-lattice extras = 52 landmarks; reference row (clean
K/C/M/Y solids + cmyk-path C,M,Y,CM,CY,MY solids) at y 280; END sentinel.
Emission: ALL clean-path imagemasks stream first, then the 32 cmyk-image
composites, sentinel last. Fiducials allowed: scratch sheet, not archival
(DESIGN R3 untouched).

**Pre-flight (gates the print).** `pytest tests/test_e004.py`:
byte-identical regeneration; geometry/bounds/rect-disjointness; 4×16 balance
(2 per row/col per class); emission-path separation ≥1.5 mm between screened
and clean rects; gs pnggray 600 dpi pixel-exact GT for B1/B2 tiles; gs
tiffsep 600 dpi pixel-exact per-plane GT for A3/A4 tiles (gs does not screen
— the addressed bitmaps must render exactly); measured-channel simulator
smoke on a B1 tile. NOTE the preflight caught a simulator fidelity bug: the
M0-fold-in's binary 3×3 white-closing filled 31% of a c2 field (sim BER 43%
vs hardware 11.1%); softened to full-fill-below-2-dots (sim c2 → 15.0%, c3
3.56% vs hardware 3.74% anchor). 2-dot-white context-dependent attenuation
stays an open simulator TODO (motif library is the data source).

## Protocol (single sheet, printed ONCE)

1. Print: `../../scripts/print_plane.sh build/e004.ps` (raw 9100 path,
   explicit user authorization required in-session). Log sha + bytes below.
2. Scan A (B-tile decode): 1200 dpi GREY, flat, 0°, descreen/sharpen/
   auto-contrast OFF, all four corner marks in frame.
3. Scan B (A-tile decode): 1200 dpi COLOR, same placement rules.
4. Optional scan C/D: repeat with the page rotated 90° (process direction on
   the CCD axis — 002.0b protocol, measured +1.3-2.0 pp on K).
5. Scans into `scans/`, sha256-referenced here. Never mix grey/color scans
   for absolute y (002.0b: mode-dependent y scale).

## Analysis plan (per tile, then per class)

- Registration: corner + plus-mark affine (cal_core manifest swap), then the
  v4 stepped-warp pipeline per tile; genie sync via known PN is the primary
  scoring mode (this validates CHANNEL numbers, not acquisition).
- Secondary metric on every tile: blind pipeline (lattice-FFT + blind
  detector) as an M1 rehearsal — report, don't gate.
- A3/A4: QDA on per-plane-aligned densities; report MI twice per tile:
  same-tile-fold (comparable to 002.2) and CROSS-TILE-trained (train on the
  other 15 tiles of the class — the honest number the fold-optimism caveat
  demands). BA capacity on the pooled confusion; per-state accuracies (watch
  the Y-bearing states and the A4 K symbol).
- B1: v4 hard (median rule), 16-context detector, monotone (PAVA) LLR
  recalibration — split-half within tile AND the frozen 001.4-fitted map
  (cross-sheet transfer replication, 003.0a).
- B2: rank-threshold dot BER at the construction prior + context model;
  motif-library branch metrics stay M2 (no trellis gate here).
- Per-class position maps: BER/MI vs (row, col) — the class-balance design
  makes these directly comparable; also per-tile r(y) step catalogs (fresh
  scanner steps expected every scan; 18.63 mm comb fixed).

## Success/abort criteria

- Sheet-level: ≥60 of 64 tiles register and decode (fiducial or plus-mark
  loss ⇒ investigate scan, not reprint); END sentinel present.
- Per envelope above: a class landing OUTSIDE its envelope is a FINDING
  (position variance or stationarity), not a failure — log it.
- The M2 decision input: cross-tile-trained A3/A4 MI vs B1 recal MI vs B2
  proxy, all in bits/mm² with the same genie-sync footing.

## Pre-print verification (004.0, four independent auditors)

Adversarial audit before the single authorized print: (1) render fidelity —
all 176 GT crops pixel-exact at 600 dpi (32 B tiles pnggray + Black-sep
cross-check; 32 A tiles x all planes via tiffsep), corner/plus/ref rects all
inked and pure; (2) PS stream — sha/bytes match, one page, forbidden
operators absent (setoverprint/Separation/DeviceN/sethalftone/settransfer),
HWResolution requests [600 600] only inside a stopped guard, 92 imagemasks +
38 cmyk images exactly as manifest-derived, sentinel last, max single object
0.34 MB; (3) statistics — class balance re-derived, all 16 B2 GTs re-checked
i2w3 with an independent run-length scanner (0 violations), B1 cells solid,
A-state uniformity + plane-regeneration exact, rect disjointness clean;
(4) repo/docs — no sha-gated generator or psgen/pilots/modulation touched,
cross-doc jobid/sha consistent.

One finding WAIVED with rationale: the page frame is /PageSize [595 842]
(integer points; 600 dpi raster 4958x7017, true A4 would be 4960x7016).
This is the SAME frame as every printed sheet in 001-003 (verified in
calpage.ps and modprobe.ps) and the frame all engine facts were measured
under; registration is mark-based affine so the absolute frame drops out;
the 2.3-dot difference is in empty right margin (content ends ~140 dots
short of it). Changing the frame inside the modulation-comparison experiment
would break one-variable-at-a-time for zero measurement benefit. Revisit
only at a layout-version bump.

## Run log

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 004.0 | 2026-07-05 | generated e004.ps (LAY=1, J=670730cb), preflight 6/6 + full suite 55 passed | build/e004.ps (14.37 MB, 213 patches) | c5c35d94c0940b82a612dc48c7721130240709cce094a3438fce790d08f9ca68 |
| 004.0 | 2026-07-05 | four-auditor pre-print gate: 3x pass clean, 1 finding waived (page frame, see above) | — | — |
| 004.0 | 2026-07-05 00:55 | PRINTED, one sheet (explicit user authorization this session): HP CLJ M281fdw "<host>", raw JetDirect 9100 via scripts/print_plane.sh, 14,371,995 bytes sent, sha confirmed at send; job requests [600 600] + Duplex false; media = tray stock (note grade here if not the usual) | build/e004.ps | c5c35d94c0940b82a612dc48c7721130240709cce094a3438fce790d08f9ca68 |

| 004.0 | 2026-07-05 | scanned 1200 dpi COLOR flat 0° (single scan; grey B-tile scan still available as an upgrade) | scans/finalists.png (9920x14028 RGBA) | a9148acc5d7a47b409f96122e0bdd90e7ef455362020e0650c37208cdea7ccf6 |
| 004.0 | 2026-07-05 | analyzed: analyze_e004.py -> build/e004_report.json; registration 56/56 landmarks, rms 1.53 dots, px/dot 2.0005/2.0073 | build/e004_report.json | — |
| 004.1 | 2026-07-06 | CROSS-ENGINE: e004.ps (same sha) printed on the Xerox AltaLink C8245 (raw 9100, user, office), home-flatbed 1200 color single scan, analyze_e004.py UNMODIFIED (home report backed up + restored byte-identical). A3 2.150 b/cell = 133.3 b/mm² NEW RECORD; A4 2.685 = 93.6; B1 ctx 5.48% / 106.1 (miss halved; page-edge penalty absent → was M281 print-side); B2 13.65% / 83.1 = cross-engine stationary. No class MIN moves. Full results + caveats: experiments/007-office-disc.md 007.6 | scans/xerox-e004-finalists-hp-scan.png -> build/e004_report_xerox.json | 862fb8a8… |

## RESULTS (004.0 — one sheet, day 2, genie-synced, color-mode scan)

Leaderboard, bits/mm² (this sheet; prior-sheet numbers in parentheses):

| cell | headline metric | b/mm² | envelope verdict |
|---|---|---|---|
| **A3 7st-c3** | **cross-TILE-trained MI 1.896 b/cell** (same-fold 1.925, tiles 1.80-2.03) | **117.6** | ABOVE (env 1.33-1.63; matches 002.0's high side 1.89 — 002.2's 1.48 was the low side) |
| B1 c2-K | ctx BER 8.15% (6.0-12.0% across tiles); recal MI 0.665, frozen-map 0.656 | 92.8 | BELOW (day-1: 4.6-5.4% ctx, 0.785 recal = 109) |
| A4 {7+K}-c4 | cross-tile MI 2.458 (same-fold 2.495) | 85.7 | above (env 1.98-2.36) |
| B2 RLL-i2w3 | dot BER 13.83% (13.0-15.0), rate 0.147 b/dot | 82.2 | IN (003.0: 13.1%, 0.154) |

Findings:

1. **The fold-optimism caveat is cleared at genie-sync footing: cross-tile
   training costs A3 only Δ0.03 b/cell** (1.925 → 1.896; A4 2.495 → 2.458).
   Training on 15 tiles and decoding the 16th — fully independent cells,
   positions, and local channel — holds the alphabet's MI. The QDA transfer
   question that hung over every 002.x color number is answered (what
   remains is blind-sync + LDPC-through, i.e. M1/M2, not training leakage).
2. **A3 is the measured ceiling: 117.6 b/mm² cross-tile-trained** — but with
   the largest sheet-to-sheet swing on record (1.48 on the 002.2 sheet vs
   1.90 here vs 1.89 on 002.0). Same-position-day variance within this sheet
   is small (1.80-2.03); the big axis is sheet/day.
3. **B1 regressed on day 2 and the mechanism is identified: white-cell
   closure, page-edge-structured.** Worst tile T00: fa(white→ink) 15.4% vs
   miss 7.4%; best tile T14 balanced (5.8/6.2). Rows 0/7 and col 0 are worst
   (ctx by row: 9.8/6.9/7.2/7.2/9.5/7.3/7.2/10.2%). c2's 2-dot whites sit at
   the development margin, so day/position density drift hits it 2x harder
   than anything else on the sheet — c2 is the channel's canary. Day-1
   (003.0a K4/e2): 4.59% ctx / 0.785 recal; today 8.15% / 0.665.
4. **B2 is the stationarity champion**: level (13.8% vs 13.1%), rate proxy
   (0.147 vs 0.154 b/dot) AND error structure (miss-dominant, the void tax:
   miss 16.7% vs fa 11.8%) all replicate day-1 within noise. The i2w3
   constraint holds its floor while everything around it moves.
5. Scanner/geometry: registration clean everywhere (56/56 landmarks, rms
   1.53 dots); color-scan y/x scale ratio +0.34% (mode-dependent axis, in
   family with 002.0b).

Caveats: genie-warp throughout (blind sync = M1's burden); B tiles decoded
from the COLOR scan — the grey scan of the same sheet is a pending free
upgrade (003.0a saw no c2 color penalty, but this sheet's edge tiles might);
single day-2 sheet; A-tile MI is QDA-confusion MI, not yet LLR/LDPC-graded;
the A position map in the report pools A3+A4 (flat by row; per-class split
is a report TODO).

Addendum (2026-07-05, zero-paper): adding a GREY-channel 4th feature
(C-plane-aligned) to the A3 QDA measured **+0.034 to +0.086 b/cell same-fold
on 4 tiles** (T03 2.014→2.079, T10 1.797→1.882, T44 1.829→1.863, T73
1.951→2.036) — a free detector-side gain (~+4 b/mm²); fold into the M2
A-track detector. Distinct from adding K as an 8th SYMBOL at c3, which
002.0c measured as a net loss (best 8-subset {7+K} = 1.801 vs 7-state 1.890
on the 002.0 16-state c3 field).

M2 reading (decision input, not the decision): A3 has the highest measured
ceiling and now survives honest training; its risk axis is sheet/day
variance and Y-entanglement. B2 has the lowest ceiling of the four today
but the tightest variance and the trellis upside (111-139 projected). B1's
c2 fragility is now measured, not suspected — its 99-109 b/mm² day-1 class
needs the day-2 8.15% explained (density drift?) before it can anchor a
format. A4 is the stable middle of track A. The rate ladder should be set
on multi-sheet mins, not single-sheet bests — this sheet is the second
point of every curve.

---

## 004.0a — layer-1 legality sprint (2026-07-05, zero paper)

Goal: how much comes back at LAYER 1 ALONE — marks-only registration, blind
detection, no upper-layer help; GT as measuring instrument only. Modules
built: `dd_warp.py` (self-clocked band-profile warp tracker: §5.1 lattice
phase in inverse-affine dot coordinates, DP total-variation branch
selection, mark-residual anchors), `trellis_b2.py` (row/column BCJR over
the i2w3 5-state chain + ISI-cancelling turbo variant), `blind_alphabet.py`
(uniform-weight EM-GMM initialized from crosstalk-predicted centroids).

Findings (each measured on scans/finalists.png):

1. **B1 warp legality: the self-clocked tracker MATCHES-OR-BEATS genie on
   interior tiles** — T14 hard 10.45% legal vs 11.76% genie (the band
   profile tracks finer than the 2-square genie stitch). It FAILS on the
   page-edge tiles (33-45%): the top row sits in the scanner's transport-
   acceleration zone (true warp span ~8 dots measured by GT-xcorr bands)
   and day-2 white closure thins the lattice line exactly there. At c2,
   scanner steps (<=1.95 dots) exceed cell/2, so branch choice needs the
   anchors+DP — which holds interior but not under edge conditions. Lock
   domain: interior; M1 fix paths: finer bands, per-class-bias-aware
   cross-tile pooling (naive pooling measured WRONG: per-plane registration
   biases corrupt the consensus — kept in module docstring).
2. **B2 trellis: machinery validated, real-channel gain ~ZERO, and the
   mechanism is measured.** Synthetic i2w3 at matched raw BER: naive 13.3%
   -> trellis 3.6% (the BCJR is correct and strong). Real tile: 13.7% ->
   13.6%. Cause: run-length-resolved analysis shows **18.5% of 2-dot ink
   runs drop out ENTIRELY** (mostly-missed; vs 2.4% of 6+ runs) — the
   dominant errors are CONSTRAINT-CONSISTENT feature dropouts, invisible to
   an RLL trellis with additive-noise emissions. **The 111-139 b/mm2
   trellis projection is INVALIDATED in its naive form.** Revised upside
   paths: (a) motif-level emissions (score 'run attenuated vs absent' with
   the 003 flux distributions — most 2-runs are partially visible, mean
   miss 29% != dropout 18.5%); (b) modulation-side: i3w3 (design the
   fragile 2-run out; untested in 003 — motivated now). ISI-cancelling
   turbo (3x3 decision-directed taps + local-median background) also ~0
   gain — same reason. B2 self-clock sync is impossible at 2 px/dot
   (dot lattice at Nyquist): its warp legality needs E005 sync strips.
3. **A3 blind-training gap is SMALL: 0.065-0.098 b/cell** (blind-EM
   1.699-1.949 vs labeled QDA 1.797-2.014 on identical genie-warp features,
   4 tiles). Layer-1-legal A3 detection stands at ~1.8 b/cell ~= 112 b/mm2
   class, before any decoded-tile bootstrap. **A3's crown survives blind
   detection.**
4. **A-tile warp legality is the open item**: per-plane self-clock on
   r/g/b channels collapses (MI 0.48-0.52) — the 165 lpi screen structure
   contaminates the phase spectrum and C/M/Y lattices ride their own
   registration offsets vs the K-frame anchors. Fix path: screen-notched
   phase estimation + DISC-prior per-plane offsets. Engineering, not
   physics.

Layer-1 legal scoreboard today: B1 legal ~= genie on interior tiles (day-2
level ~93 b/mm2 with day fragility); A3 legal detection ~112 b/mm2 on
genie warp, warp-legal pending screen-aware tracking; B2 legal number
pending E005 strips, trellis upside pending motif emissions or i3w3;
A4 same machinery as A3, not separately swept.

---

## 004.0b — Phase-0 rescans: multi-scan combining, scan mode, rotation (2026-07-05 evening)

Five scans of the SAME (unmoved/re-placed) day-2 print; `phase0_rescans.py`
-> `build/phase0_report.json`. Scans + sha256: finalists-1-col
(76490f20...), finalists-1-bw (7b366809..., placement identical to 1-col),
finalists-2-col (f80c1501..., displaced), finalists-3-col (c4534c20..., 90
deg, top part), finalists-4-col (41a7b993..., 180 deg). All genie-warp,
B-track (scan-side levers at fixed footing).

1. **Scan-mode mechanism settled: 'bw' is a SEPARATE physical transport
   pass, not a transform of the color acquisition.** Identical placement,
   yet y-scale differs by -0.205% (x identical to 5 decimals = same CCD
   optics) and the stochastic transport-step catalogs match 0/7. The
   never-mix-modes rule now has its mechanism.
2. **Grey beats color at c2/dot level**: B1 ctx 7.18% (bw) vs 8.37% (col);
   B2 13.31% vs 14.07% — the 003.0a "no c2 color penalty" was
   patch-specific; at sheet level grey is worth ~1 pp.
3. **Multi-scan soft combining WORKS — the biggest free lever measured
   yet** (B1: summed blind ctx LLRs; B2: averaged MAD-normalized
   residuals):

   | scans | B1 ctx | B1 recal MI -> b/mm2 | B2 BER -> b/dot -> b/mm2 |
   |---|---|---|---|
   | 1col | 8.37% | 0.655 -> 91.4 | 14.07% -> 0.145 -> 80.9 |
   | +2col | 7.04% | 0.713 -> 99.4 | 12.67% -> 0.158 -> 88.3 |
   | +4col180 | 6.35% | 0.744 -> 103.8 | 11.92% -> 0.166 -> 92.4 |
   | +1bw | **5.99%** | **0.754 -> 105.2** | **11.77% -> 0.167 -> 93.3** |

   Four scans restore the day-2 sheet to its day-1 class (105 vs 109
   b/mm2) purely scan-side, and give **B2 its best number ever measured
   (93.3 vs day-1 86)**. Diminishing returns after 3-4 scans.
4. 180-deg scan alone is slightly WORSE (8.75%) — rotation relocates the
   transport-acceleration zone onto the other page edge; as a diversity
   member it still helps the combination.
5. 90-deg partial scan: registration FAILED (2 corner marks visible, need
   >=3 for orientation+mirror) — the rotated-gain question at c2 stays
   open; 2-corner+plus-lattice registration support is a small cal_core
   item, or scan the bottom part as a companion.

Reading: the retrieval loop should budget 3-4 scans per sheet as standard
protocol — it is the cheapest +12-15% on record, it stacks with everything
else, and it requires zero new hardware or printing.
