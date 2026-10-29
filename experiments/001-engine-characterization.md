# Experiment 001 — engine characterization (protocol)

Goal: measure the actual channel before designing against it (DESIGN.md §3, §11.1).
Scratch sheets only; fiducials and test patterns are allowed here.

1. **Native grid.** Print 1-dot-wide line pairs at 1/2/3/4-dot pitch per plane.
   Loupe/scan: which pitch survives? Determines true addressable grid (many "1200 dpi"
   color engines are 600 dpi native) and sets the cell size parameter.
2. **Dot fidelity.** Print known pseudorandom 1-bit patches per plane at candidate cell
   sizes (2x2, 3x3, 4x4). Scan at 4800 dpi, correlate against ground truth, record raw
   BER per plane -> feeds ChannelParams and the LDPC rate ladder.
3. **Dot gain + PSF.** Checkerboards and isolated dots; fit gain and Gaussian sigma.
4. **Plane registration.** Temporary cross fiducials in C/M/Y at page corners+center;
   measure inter-plane offset field (expect ~1-2 dots of 600 dpi class, slowly varying).
5. **MIC hunt.** Print a blank page in *color* mode; scan blue channel at high gain /
   inspect with blue LED. Map the yellow tracking-dot tile (period, density).
6. **Banding.** Uniform 50% field; FFT rows for periodic gain ripple.
7. Record everything in this file's RESULTS section + commit scan hashes.

## RESULTS

### Run 001.0 — resolution probe (2026-07-03)
- **Engine:** HP Color LaserJet Pro MFP M281fdw
- **Path:** CUPS queue `HP_Color_LaserJet_MFP_M281fdw__<host>_`, sent raw
  (`lpr -o raw`), bypassing driver colour management (DESIGN.md §2.4).
- **Media:** plain office A4 (scratch sheet — confirm/replace for archival runs).
- **Stimulus:** `experiments/001-engine-characterization/probe1.ps`
  sha256 `ca69e189075dd68c019d7e337a90705c4fbf45b16c15b9aa84daae6365a22a4b`.
  One page: 600- and 1200-dpi 1-on/1-off stripe blocks, both axes, painted from a
  1200-ppi imagemask source; requested `/HWResolution [1200 1200]` (guarded).
- **Read:** by eye + loupe (no scan this run).
- **Result:** 600-dpi blocks crisp in **both** axes; 1200-dpi blocks printed
  **white/unresolved** in both axes. RIP clamped the 1200 request to 600 and the
  sub-grid stripes dropped (matches the clamp simulation).
- **Conclusion:** engine is **600×600 dpi native** — no fast-scan (horizontal) or
  process-direction (vertical) addressability beyond 600, and no axis asymmetry.
  Corroborates the PPD, which advertises `HWResolution [600 600]` only.
- **Decision:** lock `HW_DPI = 600`. No change to DESIGN.md §8 capacity tables or
  cell-size profiles (all already specified on a 600-dot grid). The 1200-probe on
  the full characterization sheet (step 1 / page 5) is now expected to read blank
  and serves only as re-confirmation.
- **SUPERSEDED by run 001.1:** the scan (`scans/test-scan-1.png`, 1200 dpi) shows
  the by-eye reading was wrong on both counts. (a) The "crisp" 600 blocks are
  in fact SOLID BLACK slabs (ink 0.96–0.98) — 1-on/1-off at 600 dpi collapses,
  see 001.1. (b) The 1200 blocks are not "grey/white": requesting
  `/HWResolution [1200 1200]` produced *corrupted raster placement* — the 1200-V
  block printed displaced by ~(+31, −40) mm and truncated to 25.4x16.8 mm
  (ink 0.97), the 1200-H block vanished entirely. The interpreter accepts the
  request (the `stopped` guard does not fire) and then mis-rasterises.
  **Rule: never request HWResolution other than [600 600] on this engine.**

### Run 001.1 — min-feature / polarity / dot-gain probe (2026-07-04)
- **Engine/path/media:** as 001.0. **Stimulus:** `experiments/001-engine-characterization/build/linetest.ps` (regenerate: `gen_linetest.py`)
  sha256 `9f6e16714787267da6cc17f442001b4382074e5136b465469bfec3637cb9499d`
  (22 K-plane patches: lone dot/hole, 1-dot lines at 0/45/90/135 deg both
  polarities, Nyquist both axes both polarities, 1–4 dot width ladder).
- **Scan:** `scans/test-scan-2.png`, flatbed 1200 dpi grey. Registered to
  manifest: 17/17 blobs, scale (+0.05%, −0.28%) — the −0.28% process-direction
  shrink is real paper shrinkage from fusing.
- **Measured** (interior ink fraction, threshold 128; nominal in parens):
  - lone 1-dot ink: **0.000** (0.007) — isolated single dots DO NOT PRINT.
  - lone 1-dot hole: closed (1.000 vs 0.993).
  - 1-dot ink lines, pitch 6: 0 deg **0.047** (0.167) — single-scanline lines
    barely develop, fragmented dashes; 90 deg 0.210 (+26% gain); 45/135 deg
    0.182/0.152. Strong H/V development anisotropy, diagonals intermediate.
  - 1-dot white lines, pitch 6: all orientations ≤ sub-threshold traces
    (0.99–1.00 vs 0.833) — 1-dot white features are erased by gain.
  - Nyquist 1-on/1-off at 600: **solid black both axes** (bow 0.997/0.999;
    wob 0.841/0.888 vs 0.500). 42 um white gaps close completely.
  - Width ladder (V lines): ink width 1→1.26, 2→2.88, 3→3.84, 4→5.00 dots
    (edge gain ~+0.4 dot for >=2-dot lines, less for 1-dot: under-development).
    White width 1→~0, 2→0.67, 3→2.36, 4→3.76 dots.
- **Conclusions:**
  1. The engine is 600-addressable but NOT 600-usable for alternating binary:
     the binding constraint is the **minimum white feature (~3 dots)**, not black.
  2. **cell=1 dead; cell=2 marginal** (a lone white cell in a black
     neighbourhood mostly closes: 2-dot white keeps 1/3 of its width);
     **cell=3 (200 cpi) is the reliable floor** — matches the DESIGN.md §8
     nominal profile. Aggressive cell=2 profile likely unusable on this engine
     without shaped ink (§4.4) + soft decoding.
  3. Dot gain is strongly positive (dark-biased) and **anisotropic**; the
     channel simulator's ChannelParams needs: asymmetric gain, worse
     process-direction MTF, and a development-threshold nonlinearity (thin
     features die entirely rather than print faint).
  4. Scan at 2400 dpi (4 samples/dot) for the full 001 run; 1200 is adequate
     for ink-fraction stats but marginal for PSF fitting.
- **Artifacts:** `analyze_linetest.py` (this directory) (registration by translation
  voting + FFT orientation/period + ink fractions), measurements + zoom crops regenerate into `build/`. Known stimulus bug (cosmetic): patch labels sit 1 mm into
  the patch below (pitch 14 mm vs label at +15 mm) — fix before reprinting.

### Runs 001.2 (lpr -o raw) + 001.3 (nc to port 9100) — feature grid (2026-07-04)
- **Stimulus:** `build/gridtest.ps` (regenerate: `gen_gridtest.py`) sha256 `904a5393...3fe30` (5 families x
  cells 1-4 + encode c2/c3 + 5 fiducial crosses + orientation square).
  Printed twice: `lpr -o raw` -> `scans/test-scan-gridtest.png`; `nc <host>
  9100` -> `scans/test-scan-gridtest-direct.png` (both scans 1200 dpi grey).
- **ANALYSIS RETRACTIONS (recorded deliberately — two false alarms):**
  1. *"140/212 lpi halftone screen"* — misread. The measured peaks are the
     checkerboard's OWN fundamental/harmonics (n=2 checker: 106 lpi @ 45 deg,
     212 @ 135); a gain-collapsed checker mimics a clustered-dot screen both
     visually and spectrally. Honest test (vlines_n3 spectrum, peaks off the
     pattern axis): **no off-axis peaks on either print — no screen, both
     prints went through the raw path.** The lpr-nondeterminism claim is
     withdrawn; both transports produced equivalent sheets (BER within noise).
  2. *"+0.23% page rescale = driver re-render"* — the day-to-day scale swing
     (-0.28% vs +0.23%) is within paper hygroexpansion (0.1-0.8%, §3), not a
     rendering difference.
  Port 9100 (`scripts/print_plane.sh`) stays the canonical path anyway: it
  removes CUPS as a variable, which this episode showed is worth doing.
- **Decoder progression on encode patches (raw BER vs ground truth), user's
  eyeball ("I can map each pixel by eye") correctly flagged v1 as broken:**
  | decoder | alignment | c3 (200cpi) | c2 (300cpi) |
  |---|---|---|---|
  | v1 | global affine + translation | 0.213 / 0.217 | 0.175 / 0.216 |
  | v2 | + per-patch 4-corner affine  | 0.173 / 0.120 | 0.143 / 0.136 |
  | v3 | + dense warp field (poly2)   | 0.056 / **0.047** | 0.131 / **0.122** |
  (cups / direct). Warp field within one 40 mm patch spans **~4 dots in y**,
  poly-fit residual 0.16-0.21 dots. Most decode loss was alignment, not channel.
- **Error-map structure (c3):** sparse isolated errors (~1-3%) + a dense
  horizontal ERROR BAND mid-patch + one at the bottom edge = discrete
  process-direction transport steps that a smooth warp model cannot follow —
  the §3 banding term, photographed. True cell-flip BER outside bands ~1-3%.
- **Conclusions:**
  1. **cell=3 works**: 4.7% raw with a still-naive decoder; well inside the
     soft-LDPC envelope (§6). Expect ~2-3% once sync handles transport steps.
  2. **cell=2 is genuinely marginal but not dead**: 12.2% raw; needs the full
     soft pipeline (LLRs + 2-D equalization) and a low-rate inner code; net
     density win over cell=3 only ~1.4x — decide after M2 measurements.
  3. The sync layer (§5) must model **piecewise/stepped warp**, not smooth-only
     (lattice tracking per band); simulator ChannelParams gains a transport-step
     term alongside gain/PSF/banding.
  4. Fiducial layout lesson: 4-corners+center is 180-deg symmetric — the
     orientation square is REQUIRED for automatic registration (bit us once).
- **Artifacts:** decoder progression consolidated into `scanlab.py` (register/
  warp/decode) + `analyze_gridtest.py` in this directory; overlays + error maps
  regenerate into `build/analysis-<scan>/`. The v1/v2 scripts were superseded
  and deleted; their numbers are recorded above.

### Run 001.4 — decoder v4: stepped warp + blind soft output (2026-07-04, analysis-only)
- **No new print or scan.** Re-analysis of the 001.2/001.3 sheets
  (`scans/test-scan-gridtest-direct.png` = port 9100, `scans/test-scan-gridtest.png`
  = cups). One parameter set, chosen once, run identically on both scans; v3
  baselines reproduced exactly before any change (0.0474/0.0556 c3,
  0.1221/0.1314 c2). Deterministic: repeated runs byte-identical. ~12 s/scan.
- **CORRECTIONS to the 001.2/001.3 entry (retraction discipline):**
  1. *"error band at the bottom edge = transport step"* — mostly a decoder
     artifact, not channel. v3's window grid stopped 64 dots short of the patch
     bottom and the poly2 extrapolated; edge-flush window rows alone recover
     0.5/0.8pp (direct/cups) and delete the bottom band. A real, smaller step does exist near the
     patch bottom (+0.32 dots at y=832 direct; +0.61 at y=720 cups), so the
     channel claim survives in weakened form.
  2. *"poly-fit residual 0.16-0.21 dots"* — that figure described the **c2**
     patch. The **c3** patch's poly2 y-residual RMS was 0.37-0.40 dots with
     ±0.75-dot systematic (sawtooth) structure: v3 was losing alignment margin
     across the whole patch, not just in the visible bands — which is why its
     out-of-band row floor (2.2-2.5%) exceeded the true floor (1.6%).
- **v4 changes** (consolidated into `scanlab.py::decode_cells`, one code path
  serves v3 regression mode and v4):
  1. window grid 128x64 dots, step 64x32, plus edge-flush rows/cols (no cell
     outside measurement support);
  2. step-preserving y-warp: per-window-row median of the poly2 y-residuals,
     linearly interpolated across cell centres, added to the poly field. dx
     stays poly2 (no vertical bands observed — fast-scan axis has no steps);
  3. blind soft output: 20th/80th-percentile level fields over an 11x51-cell
     footprint (narrow in y — tracks banding), z = (W-m)/(W-B), 2-component
     Gaussian EM with weights pinned 0.5/0.5 (the scrambler fixes density;
     freeing pi made the c2 fit drift without settling), per-cell LLRs;
  4. decision-directed 16-context detector (4-neighbour pattern, per-context
     EM from cells with all-confident neighbours, 2 ICM iterations, global
     fallback below 200 cells or unseparated classes);
  5. diagnostic-only (NOT in the correction path): residual y-profile r(y) at
     1-cell-row resolution from full-width row-band correlation, plus a
     transport-step catalog (|diff of median-filtered r| > 0.25 dots).
  GT is used for registration templates and scoring ONLY (genie-synced raw
  numbers, as before); every decision statistic is estimated blind.
- **Decoder progression, raw BER vs ground truth (direct / cups):**
  | decoder | detection | c3 (200cpi) | c2 (300cpi) |
  |---|---|---|---|
  | v3 (001.3)   | median threshold      | 0.0474 / 0.0556 | 0.1221 / 0.1314 |
  | v4 hard      | median threshold      | **0.0203 / 0.0223** | 0.1116 / 0.1141 |
  | v4 soft      | LLR sign, global GMM  | 0.0166 / 0.0184 | 0.1106 / 0.1135 |
  | v4 context   | LLR sign, 16-context  | **0.0015 / 0.0026** | **0.0496 / 0.0541** |
  c3 clustering 40% -> 6%/9% vs 8%/9% random expectation: the error bands are
  gone, not thinner. Band accounting (definition pinned: rows with >1.5x the
  v3 mean row error rate): those rows held 61/62% of v3's c3 errors and still
  hold 28/34% of v4's — but of 4.3x fewer errors; the only coherent survivor
  is a 6-7-row remnant on the mid-patch double step, worth ~0.2pp.
  The GMM decision boundary beats the 50%-pinned median by 0.3-0.4pp on c3
  because the dark-biased channel broadens the white class (sigma 0.25 vs
  0.12) — variance-aware thresholding is free capacity.
- **Context detector is the surprise result.** Corrections are physics-shaped,
  both polarities: white cells in inky contexts (partial closure, mean GT ink
  neighbours 3.6-3.8 vs 2.0 baseline) and lone ink cells in white contexts
  (under-development, 0.7) — i.e. much of what 001.1/001.3 booked as erasure
  floor retains separable reflectance once class statistics are conditioned on
  the neighbourhood. c2's residual 5% is then dominated by true full closures
  + the step band (band rows hold 36-44% of remaining errors).
  **Calibration caveat:** NO LLR family is LDPC-ready yet. c2 context LLRs are
  badly overconfident (MI 0.27/0.17 bits/cell despite the better hard BER —
  fully-closed whites draw large wrong-sign LLRs). The global-GMM LLRs are the
  better-calibrated of the two but still miscalibrated at the extremes: per the
  reliability tables (`*_v4_metrics.json`), mid-deciles run 2.5-5x
  underconfident and tail deciles up to ~70x (c3) / ~150x (c2) overconfident —
  the Gaussian tails understate closure events. Both families need a monotone
  recalibration (per-|LLR|-bin empirical remap, blind via decision counts)
  before feeding LDPC at M2. c3 context MI itself is fine (0.97/0.95).
- **Soft-decision headline (global GMM, blind):**
  - c3: MI 0.920 / 0.905 bits/cell; confident BER 0.0054/0.0069 at 5%
    uncertain, 0.0033/0.0042 at 10% (context: 0.0002-0.0005 at 5-10%).
  - c2: MI 0.548 / 0.526 bits/cell; confident BER 0.0620/0.0651 at 15%
    uncertain, 0.0406/0.0434 at 25% (context: 0.023-0.031).
- **Transport-step catalogs** (r(y) diagnostic, |step| > 0.25 dots; y in patch
  dots, magnitude in dots):
  - c3 direct: (62, +0.28) (178, +0.25) (446, −0.86) (478, +1.50) (832, +0.32)
  - c3 cups:   (4, +0.40) (122, +0.25) (302, +0.29) (453, −0.50) (472, +0.37)
    (484, +1.08) (720, +0.61)
  - c2 direct: (81, +0.31) (93, +0.32) (145, +0.31) (179, +0.27) (315, +0.25)
  - c2 cups:   (57, −0.25) (88, +0.82) (97, +0.26)
  The big mid-patch double step lands at y≈446-484 on BOTH sheets (different
  prints!) — likely a fixed transport event, not stochastic; the small steps do
  not align across sheets. Check on the C/M/Y sheets before modelling.
  ChannelParams gains a piecewise-constant y-offset term: amplitude 0.25-1.5
  dots (typical 0.3), several events per 40 mm, at least one position-stable.
- **Conclusions:**
  1. **cell=3 alignment is solved at the instrument level**: 2.0-2.2% raw hard
     (the "expect ~2-3%" from 001.3 confirmed), 0.15-0.26% after the blind
     context detector — deep inside any §6 LDPC envelope.
  2. **cell=2 is more alive than 001.3 concluded**: the hard-decision anchor
     stays ~11%, but context detection reaches 5.0/5.4% blind — the closure
     loss is partly recoverable, not pure erasure. Decision still belongs to
     M2 (soft pipeline + shaped ink), now with measured LLR/MI inputs.
  3. **M1 carry-forward:** the sync layer must reproduce the r(y) tracking
     blind. Pilots are dense enough on paper: one per 6x6-cell block (~2.8%)
     puts ~17 known cells in every full-width 2-cell-row band of the c3 patch
     (σ ≈ 0.05 dots if pooled) — but that presumes addressing is already
     acquired; cold acquisition still sees the stepped warp. Alternatively the
     data lattice itself supports decision-directed row tracking (what v4 does,
     minus the genie). Verify at M1; else the rate ladder budgets ~0.5-1pp of
     band BER into the inner code. (Earlier phrasing conflated the site-pattern
     period P=64 cells with pilot spacing — the density argument above is the
     correct one.)
- **Artifacts:** `scanlab.py` (v4 decode + context detector + r(y)/step
  instrument), `analyze_gridtest.py` (v3-vs-v4 report); per patch and scan in
  `build/analysis-<scan>/`: error maps (v3 / v4 / v4+context), overlays,
  y-profile plot, `*_v4_metrics.json` (curves, reliability, GMM, steps).

- **CORRECTION from run 002.0b (2026-07-04, rotated-scan test):** the transport-step
  catalogs above are **flatbed-SCANNER transport artifacts**, not printer physics —
  they fail the rotation test (4/39, 3/34 reproduced; chance-level) and the
  cross-placement test (0/12 replicate). The "position-stable double step at
  y≈446-484 on both sheets" is stable in the SCANNER frame (both sheets were
  scanned in the same placement), not gear-fixed printing. The print-frozen
  transport is the smooth 80.5/60.4 mm wander (~1 dot). The v4 decoder's
  step-tracking remains necessary — every flatbed scan carries fresh steps —
  but the steps belong in the SCANNER model of ChannelParams. See
  experiments/002-calibration-page.md Addendum 002.0b.

## Addendum 2026-10-11 — the first print and test_pattern.ps

An unlogged early print, possibly the first, was `probe.ps`, a ~300-dpi probe sent on
2026-07-03 and deleted on 2026-07-04; the file exists nowhere and nothing of it is in
the evidence archive. `test_pattern.ps` (2026-07-03) is the owner's own fixed-up copy
of a pasted PostScript grid sample whose source is unstated (the sample that gave the
`/HWResolution` idea); it was never recorded as printed. It is published in the
evidence archive's paperholo-era release as
`001-engine-characterization/test-pattern/jobs/test_pattern.ps` (982 B, sha256
`5eabb5e359eaf09ccd47634c5d2230bd0f525dcbd185ef2f63d74f432a626be7`, class
job-unprinted). (evidence line, docs/EVIDENCE-ARCHIVE-2026-10-08.md §8a)
