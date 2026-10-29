# Experiment 017 — ARCH-C: the color channel (cmy8-c3, layout_version 4)

**2026-07-10.** Build + certification campaign for the CMY color channel
per docs/COLOR-DESIGN.md (decisions D1–D7) and PILOTS-DESIGN §16.
Everything up to the print is zero-toner: probes on archived color
scans, sim gates, sha-gated stimulus. Hardware legs are pre-registered
below and OWNED BY THE USER (hardware.md).

## Zero-print probes (P1–P6, archived 1200 dpi scans — pessimistic footing)

Probe scripts + structured result JSONs: experiments/017-color-channel/
probes/ (durable copy, exp-010 precedent; the .npz feature caches stay in
the gitignored main-tree scratch/ — regenerable from the archived scans).
Results table filled from the probe fleet run of 2026-07-10:

| probe | question | result (2 px/dot footing, real toner) | consequence |
|---|---|---|---|
| P1 | Stage-A luma margin per word rendering | fixed CM wins: AltaLink 0.72% / home 6.4% median at the Stage-A statistic; TRIPLE loses on M281 (10.1 vs 5.8% — re-screen renders 3-ink LIGHTER than CM); keystream 2-ink mix 5–9× worse; any-ink dead; starved-Y leaves W/CM margin UNMOVED. Site-population GMM fit recovers oracle ±0.5 pp (all-cells fit costs up to 2×) | **word dark = fixed CM**; **Stage-A GMM fit on word-site population** |
| P2 | luma lattice lock vs the screens | screen decoys never capture (contrast ~6); AltaLink composite locks K-class (16/16); M281 re-screen ATTENUATES the c3 cell line ~3× → blind pitch ID fails 75% of tiles at 1200 dpi. Home-flatbed COLOR mode lays an 11.3 px comb (instrument fact — never acquire from it) | M281 color decode needs Canon 8 px/dot footing (or per-plane-channel lock); screen-notch OFF the critical path |
| P3 | dust density + features | 0.25% already ≤Δ0.03 b/cell both engines (knee ~0.1%); periodic placement FREE; grey 4th feature +0.041 home / −0.023 office (replicates 004.0 + 007.8) | dust FROZEN 0.5% (18/tile, pure-quota 3); features chosen at decode time by dust cross-validation |
| P4 | per-plane registration | M281 C-plane x-shift −1.33 dots (constant, print-frozen — 89% of budget if unsampled); Y−C dy −2.55 mean, −0.71 linear drift; v1 global+linear residuals ≤0.67 home / ≤0.91 office dots vs 1.5 budget; ~100–200 anchors saturate; home-Y anchor yield 15–25% | D5 CONFIRMED; AltaLink non-smooth dx flagged for any future c2-color |
| P5 | per-level rates | C 5.3/M 4.3/Y 8.9% home; C 2.9/M 2.8/Y 6.4% office (cross-tile QDA); r0550 100% yield C+M both engines; Y r0550 = 89.6% home (fountain-absorbable vs 80% need); net projection 91–103 b/mm² measured / 108–117 Canon-est; 0 wrong certifies in 4320 decodes | rungs FROZEN C r0550 / M r0550 / Y r0547 |
| P6 | 7-vs-8 states | AltaLink uniform-8 2.208 beats best-7 2.138; home triple toxic but 84% of penalty on its own 12.5% of cells (~30% own-BER); flag-and-erase fallback = 0.375 b/cell | 8-state STANDS; pack7 not built (3-condition revisit clause in COLOR-DESIGN §3) |

Full structured results: probes/probe17_{dust,fit,level_rates}_report.json,
probes/probe17_p6_*.json + per-sheet reads in probes/probe17_out/.

## Pre-registered decode protocol (hardware, when printed)

Scan: Canon 4800 dpi **RGB** (enhancements off), 2–3 re-placed scans;
pre-decimation to 2400 dpi allowed (016.2-equivalent footing, declared).
Decode: `page_decode(..., align_to_field=True, detector QDA/dust,
calibrate=True)` per scan → per-level `decode_tiles` at the frozen rungs
→ `certified_results` → level-stratified `volume_decode` → data sha must
equal the gen_e017 golden.

ENVELOPE (PASS): byte-exact volume from ≤3 RGB scans of the M281 print.
MARGINAL: ≥60% of (tile,level) symbols certified but volume under-ranked
(rate-rung finding — re-rung, no format retraction). FAIL below that.
RETRACTION RULE: if pilot-word acquisition itself fails on a clean scan
(Stage A yield ≪ the K-page class) that is a §16 pilot finding — check
pilot-cell BER vs co-located payload BER first (fold-artifact check,
014.1); pilot BER > 20% on a clean scan ⇒ revisit the composite screen's
effect on the luma word channel before anything else.

## Hardware queue (user; in order of information-per-sheet)

1. **Zero-print first: Canon 4800 RGB rescans of EXISTING color sheets**
   — e004 finalists (home M281) + one office color sheet (e006c or
   e004-office if printed). Moves every P# anchor from the 2 px/dot
   flatbed footing to the real footing (014.2: footing flips verdicts;
   c2-K went 7.9→2.6%). Re-run P1/P2/P5 on these scans; re-freeze rungs
   if warranted (gen_e017 regenerates, layout_version stays 4 — rungs
   are volume parameters, not page format).
2. **e017 ARCH-C print on the home M281** (MIC-free engine — anonymity
   preserved; the AltaLink print is the engine-2 comparison, carries
   tracking dots): `lpr -o raw` or print_plane.sh per 016.1 precedent.
3. Canon RGB scans → blind decode → **first color-certified bits**.
4. Engine-2 comparison print + starved-consumable monitoring via the
   dust canary over time.

## Run table

| run | date | action | artifact | sha256 |
|---|---|---|---|---|
| 017.0 | 2026-07-10 | probes P1–P6 (zero print) + full implementation + sim gates | probes/ JSONs + this build | see the P1–P6 table above + IMPL-1/2/3 sections below |
| 017.1 | 2026-07-10 | ARCH-C sheet BUILT + gated (IMPL-4, zero print) | build/e017.ps | d99ea1c50d40fd81389fc356cf0157f7d03cac33ecb347014b32e9f33c6652b3 |
| 017.2 | 2026-07-10 | P1 site-fit rule WIRED into acquire Stage A/B + post-fold (zero print, decoder axis; suite 306) | src/paperholo/acquire.py, tests/test_color_sitefit.py | n/a (no stimulus) |
| 017.3 | 2026-07-10 | 22-finding adjudication round applied (zero print, decoder axis + docs; see 017.3 below) | acquire/fountain/tests/docs | n/a (no stimulus) |
| 017.4 | 2026-07-10 | P1/P2/P5 re-anchored on the FIRST Canon 4800 dpi RGB color scan (hp-e004 finalists sheet, home-M281 print; zero print — scripts scratch/probe17_canon_*.py, results scratch/probe17_out/canon-*.json) | scratch/hp-e004-finalists-first-print-canon-4800 (6,875,455,728 bytes, 40832x56128 RGB8 TIFF) | e1f14f1c57ffcefeac25d66a236bdadf01765454893d152856dcfefca360b4ba |
| 017.5 | 2026-07-10 | e017 PRINTED on the home M281 (Y-starved state, GO per 017.4) + first Canon 4800 RGB scan; FIRST HARDWARE DECODE FAILED (see 017.6) | scratch/hp-e017-arch-c-canon-4800rgb (6,875,455,728 bytes) | 907e67519875b904f1ac9ccaf2c09e637c4fa1659edcce45787cd140ef12bac4 |
| 017.6 | 2026-07-10 | 017.5 failure dissected (zero print): PAVA cross-fit scale bug FOUND + FIXED in acquire (regression test added, suite 328); residual attributed CHANNEL-side (8-state on the Y-starved M281; per-state confusion + word-channel comparison below) | src/paperholo/acquire.py, tests/test_e017.py, scratch/e017dbg_*.py + scratch/e017dbg_real-center.json | n/a (no stimulus) |

## 017.1 — ARCH-C build (IMPL-4: integration + the e017 sheet, 2026-07-10)

**Frozen-constant reconciliation (P1/P3/P5 results applied to the format
before the golden froze):**
- `compose.RENDER_DARK` flipped `"CMY"` → `"CM"` (P1 measured freeze; the
  constant existed for exactly this flip). The IMPL-1 provisional 120-cell
  page sha moved a29983ef… → 66f72134… (deliberate, this entry is the log).
- formats registry row `e017-v4-cmy8` dust 24/tile (provisional) →
  **18/tile = 0.5%, pure_quota 3** (P3 freeze).
- **Y rung "r0547" resolved by MINTING it**: k is Z-quantized (Z=64), so a
  rung targeting rate 0.547 snaps to the SAME k=2240 as r0550 (whose true
  rate already is 0.5469) — `LDPC_LADDER["r0547"] = LdpcSpec("r0547", 2240)`
  is the 0.547-target floor twin with its OWN seed label = an independent
  parity structure (girth>4, restart 0, BSC p=0.055 behavior matches its
  rate class; golden-anchored in test_ldpc alongside the frozen five, which
  are UNCHANGED). No coding-rate gain over r0550; a genuinely lower Y rung
  (k=2176 = 0.531) is a frozen-constants-pass decision — flagged open.

**e017 ARCH-C sheet (gen_e017.py → build/e017.ps, sha above, 30.2 MB):**
A4 e012 geometry at layout_version 4 (2220×1500 cells, cmy8-c3, v4 words
CM-rendered, dust 18/3), single-page level-stratified fountain volume:
**484,214 data bytes** (sha 19a5cc15…), per level C/M/Y = r0550/r0550/r0547,
S = 2064 bits, K/N = 626/782 = 0.800 each (782 interior 64-cell tiles),
**net 72.1 b/mm² at the provisional rungs** (vs 55.1 certified K-c2; the
91–103 COLOR-DESIGN projection assumes the measured-yield rungs, not the
conservative floor — the Canon-footing re-freeze is the upside lever).

**Gates (tests/test_e017.py, all PASS first run):**
- determinism + golden ps/data shas; gen spec == registry row (D7).
- gs tiffsep per-plane pixel-exact (6660×4500 dots ×3), K separation empty.
- **THE GATE — clean-channel coded round-trip, FULLY BLIND, byte-exact:**
  e017-class 300-cell page (identical format constants), clean crosstalk
  render (planes_to_rgb_refl, zero noise), ONE crop → blind
  formats.page_decode (luma identify → dust-QDA → per-level PAVA) →
  decode_tiles at the frozen rungs → all 48 interior (tile,level) symbols →
  fountain volume_decode → **9,912 bytes byte-exact**; volume-F6 stop
  correct.
- REAL e017 page, one interior 600-cell window via the registry row:
  blind acquire, **216/216 fully-covered (tile,level) certified, 447,996
  user bits byte-exact vs the fountain frame**.
- sim-noise leg (print_scan_cmy clean_mask = AltaLink-class, geometry off,
  full develop/PSF/mottle/crosstalk/sensor noise), SCOPE-DECLARED: level
  BER **C 2.63 / M 3.04 / Y 4.76%** (declared band [0.05, 12]% per level;
  the numbers first logged here, 2.42/3.07/4.64, were pre-017.2 — the
  site-fit Stage-A wiring moved the deterministic read, re-measured
  2026-07-10), **36/36 fully-covered (tile,level) certified, all
  byte-exact, zero wrong certifications**. KNOWN SIM RESIDUAL: the
  committed color sim's per-LEVEL reliability order is INVERTED vs
  hardware (sim Y strongest; the Y-weakness mechanisms — 224 lpi
  clean-path texture, dev raggedness — are M0 TODOs); per-level
  conclusions come from HARDWARE only, sim tests assert ceilings never
  orderings (provenance: simulator.CMY_RESCREEN_SIGMA_FRAC,
  COLOR-DESIGN §3). The M281 screened path is OUT OF SIM SCOPE at 2 px/dot
  (P2: re-screen attenuates the c3 luma line ~3×) — hardware verdict =
  Canon 8 px/dot RGB scans (pre-registered above).

Open items after 017.1: (0) COLOR-DESIGN D4's "features chosen at decode
time by dust cross-validation" is NOT implemented — v1 ships a manual
`color_features` knob defaulting to "rgb" (the AltaLink winner; a
home-M281 decode on the default leaves P3's measured +0.041 b/cell on
the table). Deviation made explicit in D4 2026-07-10; the CV chooser
(leave-tile-out on dust labels, record cdiag["features_cv"]) composes
with the cross-fit calibration split when built;
(i) rung re-freeze from the Canon RGB rescan leg
(rungs are volume parameters — regenerate + golden bump, layout stays 4);
(ii) ~~the P1 Stage-A rule "pinned 2-GMM fit on the gathered WORD-SITE
population" NOT yet wired into acquire's Stage A~~ **WIRED 2026-07-10
(017.2, zero print, decoder axis only): on n_levels==3 specs every
pilot-word bit read is site-population-fit** — Stage A gathers z-levels per
phase hypothesis and fits a row-vectorized pinned 2-GMM per hypothesis
(acquire._site_fit_words / _fit_gmm_z_rows), Stage B re-thresholds the
visible sites under the candidate address (one pooled fit), and after
acceptance ONE site-population fit serves slip votes / anchor templates /
the post-fold word certification (_site_fit_cell_bits;
diagnostics["word_detector"]="site_fit"; detector="ctx" gated K-only — the
16-context all-cells re-fit would reintroduce the mis-threshold). K path
byte-identical (z_grid never constructed for n_levels==1; suite 306 green
incl. all frozen v2/v3 goldens + e011/e012/e014/e016 regressions).
MEASURED: constructed mostly-ink luma window (bimodal ink pack, CM in the
light cluster — tests/test_color_sitefit.py) reads 22.1% word-site BER
all-cells vs 0.0% site-fit; site-fit Stage A decodes 4/4 windows at
n_err=0 where all-cells scrapes 1 window at n_err=12; FA structure
preserved (wrong seed 0 candidates, rot90 ×3 no acceptance, wrong-phase
descrambled balance 0.496 over 3599 hypotheses; e2e wrong seed fails at
stage_a). Wall time on the 240-cell test pages: color RGB e2e 2.09→3.07 s
(1.47×), color grey 150-cell-window crop 1.06→2.07 s (1.94×), K page
1.41→1.40 s (1.00×) — under the 2.5× budget; the added cost is the
per-hypothesis EM in Stage A, one vectorized pass over (≤3600, ~100);
(iii) a true
sub-r0550 Y rung (k=2176) if the Canon leg still shows Y-yield pressure;
(iv) full-A4 blind page_decode of a clean e017 render = experiment-script
workload (decode_e017 tooling), not built tonight.

## 017.3 — adjudication round (2026-07-10, zero print)

22 review findings verified against the code and adjudicated (majors
fixed; the full finding list lives in the session record). Decoder-axis
changes (format untouched — all frozen goldens byte-identical):

- **fit_qda collapse gate made sampling-noise-aware**: the per-pair bar
  is now QDA_COLLAPSE_DIST + sqrt(d·(1/n_i + 1/n_j)) — the expected
  whitened distance between SAMPLE means of truly collapsed classes. At
  realistic window label counts (~35–55/class) the fixed 0.5 bar missed
  ~12% of true collapses (review Monte Carlo), always on the unsafe
  (unclipped) side.
- **PAVA calibration cross-fitted**: with ≥2× the label bar the per-level
  calibration scores come from a 2-fold cross-fit (each dust half scored
  by a QDA trained on the other half + pilots; payload model keeps all
  labels) — the previous scheme scored the QDA's own training dust
  (in-sample = over-confident LLRs at the LDPC input). Below the bar the
  in-sample fallback is recorded as cdiag["pava_in_sample"]=True.
- detector="ctx" on color pages now records what actually ran
  (diag["detector"]=site_fit/global + ctx_skipped_color) instead of
  reporting ctx that never runs.
- fountain.tiles_to_symbols validates the level bound before
  symbol_bits_level (contracted ValueError, not IndexError).
- New tests: v2↔v4 word cross-rejection (the C_v4==C_v3⊂C_v2 nesting
  cell that was untested) + color-page-vs-full-K-registry acquire-level
  rejection (same seed, reverse D7 direction); tiles_to_symbols level
  guard. Suite 306 → 311 green (+2 cross-format here, +3 confetti-fixture
  tests riding the main merge; all K goldens byte-identical).
- Docs sync: IMPL-2/IMPL-3 log entries added (the calibration event was
  code-comment-only); sim per-level INVERSION caveat propagated to this
  log + COLOR-DESIGN §3; D4 amended with the explicit v1
  features-knob deviation (open item 0); PILOTS-DESIGN §16.3 density
  corrected to the frozen 0.5%/18-per-tile (the 0.75% upper end was the
  retired 24/tile provisional); gen_e017 docstring 840→782 interior
  tiles; simulator/test_color_sim provenance numbers re-anchored to the
  committed construction (1.760–1.766, 4 seeds; clean 2.466); sim-noise
  leg numbers in 017.1 updated to the post-017.2 read (2.63/3.04/4.76);
  LAYERS.md v0.3 with the layout_version-4 registry rows; probe17 fleet
  (scripts + report JSONs) copied durable into probes/.
- Housekeeping: worktree fast-forwarded onto main f2cbe3d (confetti
  fixture — zero file overlap with this branch; full suite green
  co-resident).

## IMPL-2 — color simulator calibration (M0 fold-in, 2026-07-10)

The measured event the CMY_RESCREEN_SIGMA_FRAC code comment records,
logged here per doctrine (truth lives in the experiment log):

- **CMY_RESCREEN_SIGMA_FRAC = 0.30 FROZEN 2026-07-10**, calibrated
  against the CAL-1 002.0 8-state c3 composite genie anchor (measured
  1.76 b/cell). Regenerable in-repo footing (tests/test_color_sim._page
  + _genie_qda_read: 120×120-cell page, cross-half QDA on full-cell-mean
  RGB): **sim soft-MI 1.760–1.766 across 4 seeds** — same construction,
  same engine, genie footing. (The original calibration probe read
  1.77–1.78 on a scratch-script footing not kept in-repo; the committed
  construction is the durable anchor.) Single-anchor calibration —
  honest scope: one sheet, one engine, one day.
- The K screened path keeps the uncalibrated 0.5·period default (never
  hardware-anchored; msel1's M0 gate pins its behavior — regression
  test test_rescreen_default_is_frozen_k_behavior).
- **KNOWN RESIDUAL: the sim's per-level reliability order is INVERTED
  vs hardware** — sim level BER ~19.2/16.6/12.2% C/M/Y (Y strongest) vs
  measured 6.3/10.2/15.9% (Y weakest). The Y-weakness mechanisms
  (224 lpi clean-path Y texture, development raggedness) are declared
  M0 TODOs. Per-level conclusions (rungs, orderings) come from hardware
  only; sim tests assert ceilings, never orderings.
- Regime gates frozen in tests/test_color_sim.py: screened [1.5, 2.05]
  b/cell (reads ~1.76; uncalibrated screen 1.23 and accidentally-clean
  ~2.47 both FAIL), clean-path [2.2, 2.85] (reads 2.466 vs the
  JPEG-taxed engine-2 floor anchor 2.208).

## IMPL-3 — receiver color stage (decode axis, 2026-07-10)

The acquire.py color wiring the code comments cite as IMPL-3 (built with
IMPL-1, measured via the 017.1 gates + test_color_receiver): rgb=
threading on the luma frame, dust-trained 8-class full-covariance QDA →
per-level LLRs (D4), per-plane offset models from pure-plane dust
anchors (D5, Theil-Sen + inlier refine), PAVA per level on dust labels,
per-level keystream descramble at absolute coords; color payload runs
only AFTER the post-fold word gate; grey scans return
color_payload_pending. Guards: rgb-on-K-spec refused, frame mismatch
refused, label starvation fails the window cleanly (page_decode skips).

## IMPL-1 build notes (format axis / write side, 2026-07-10)

Shipped: pilots v4 (`pilot-values-v4` label; word = LUMA object, plane "K"
enforced; sites/code/counter = v3 verbatim), `paperholo/dust.py`
(tile-periodic positions via partial Fisher-Yates over non-pilot cells,
`dust-sites-v4`; aperiodic per-tile states `dust-states-v4` + page_le32 +
tile_le32, state = C + 2M + 4Y, deterministic pure-quota fix-up),
compose cmy8-c3 (3-level cell_values/plane_bits, per-level plane
keystreams C/M/Y = "CMYK".index 0/1/2, RENDER_DARK="CMY", dust rendered,
capacity excludes pilot+dust), composite emission (ONE put_cmyk_bitmap,
e004 idiom; per-plane GT + per-plane manifest patches w/ composite_of),
ldpc dust-aware shortening + level-aware encode_page/decode_page_tiles
(lists of 3), fountain level-stratified volumes (S_level per rung;
data partition = cumulative-floor proportional split; repair-row label
gains a level byte ONLY for n_levels>1; symbols keyed (level,block,i)),
encodings row cmy8-c3 (kind cell_mlc; symbol-domain scramble + --emit
refuse), formats row e017-v4-cmy8 (dust 24/3600 = 0.67%, pure_quota 3,
PROVISIONAL until P3), interim acquire guard (v4 hypothesis acquires on
luma, payload slots empty until IMPL-3).

Decisions beyond the written contract (audit list): (1) v4 keystream
plane hard-enforced "K"; (2) dust positions raster-sorted canonical
order; (3) quota fix-up victim rule (perm drawn after states, never robs
a pure state at/below its own quota); (4) fountain level byte in repair
labels; (5) FormatDescriptor grew a `dust` field (spec() must build a
valid v4 ComposeSpec); (6) kcell at layout_version 4 refused (D7);
(7) provisional page sha pinned in tests/test_color_format.py
(a29983ef…) — final anchor freezes at gen_e017. Suite: 257 green
baseline (3 baseline fails were a missing gitignored build/ dir) →
277 green after (+20 color tests; 3 non-golden tests extended for the
new registry entries; v2/v3 format goldens untouched).

## 017.4 — RESULTS: Canon 4800 RGB re-anchor (first color scan through the Canon, 2026-07-10)

**Zero print.** The hardware-queue item-1 leg, first sheet: Canon 4800 dpi
RGB scan of the e004 finalists checkerboard (home-M281 print — the SAME
sheet behind every home-flatbed P# anchor, so all deltas are pure scanner/
footing; user note: possible in-place Y starvation is print-frozen and
identical on both scans). Scripts scratch/probe17_canon_{prep,p2,artifacts,
p5,p5_verbatim,p1}.py; structured results scratch/probe17_out/canon-*.json
(gitignored, regenerable from the scan + this registration). Scan sha256
verified tonight = the run-table value. TIFF is uncompressed single-strip
(memmap-friendly); all work tile-wise, file never loaded whole.

**Scan facts / registration** (probe17_canon_prep.py): cal_core registration
on a 4x box-decimation (aperture-honest): upright, unmirrored, 56/56
landmarks, residual RMS 1.449 dots (flatbed same sheet: 1.527 — the residual
is print-frozen warp, not scanner); landmark max 5.36 dots (flatbed 2.99;
dense per-tile warp absorbs it — per-square poly2 residual RMS measured
0.14-0.35 dots in the P5 decodes, flatbed class). Native scale x 8.0101 /
y 8.0059 px/dot (+0.126%/+0.073% vs nominal; the home flatbed's y ran
+0.37% — Canon near-isotropic, consistent with 012.3).

**Instrument (Canon COLOR path, first characterization data — in passing,
not the owed full protocol):** blank-margin spectral sweeps find a y
(transport-axis) comb at **60.68 px** (harmonic family 121.4/481.9 px),
equal in all three channels, **RMS amplitude 0.49 grey levels ~ 0.2% of
paper white** — cosmetic; it never appears in any tile's credible
spectral-line list (gradient-domain contrast far below floor). x axis:
mm-scale illumination ripples (682.7 px at 1.4 grey RMS, 80.3 px at 0.39)
and a coherent 2.96 px micro-periodic at 0.015 grey RMS (negligible).
**NO analog of the home flatbed color mode's acquisition-breaking 11.3 px
comb.** Verdict: the Canon color path is clean at detection-relevant
amplitudes on this scan.

**P2-Canon (THE GO/NO-GO): GO — the Canon footing resurrects M281 composite
luma acquisition, and the mechanism is a CLEAN SPECTRUM, not a stronger
cell line.** 8 position-spread A3 tiles (T03/T05/T10/T27/T44/T52/T73/T75),
footings by box-mean decimation of the native 24 px/cell crops; baseline =
the same-sheet 1200 dpi flatbed read (probes/probe17_out/e004-home.json:
blind strict pitch ID 2/16, format-path 4/16, cell_tight contrast median
14.7 — the flatbed's 11.36 px comb harmonic at 5.68 px out-contrasts the
lattice and breaks the integer-ratio fundamental selection).

| footing (px/cell) | strict pitch ID | format-path ID | cell_tight contrast med (range) | mcp contrast med | lock in-capture | lock err med v/u, worst |
|---|---|---|---|---|---|---|
| 24.0 native | 5/8 | **8/8** | 17.4 (8.3-34.7) | 43 | 8/8 | 0.74/0.29%, 2.50% |
| 12.0 | 7/8 | **8/8** | 17.8 (9.0-34.8) | 82 | 8/8 | 0.34/0.27%, 2.45% |
| 8.0 (scannorm canonical, least-resample) | 5/8 | **8/8** | 17.5 (9.2-34.4) | 87 | 8/8 | 0.52/0.26%, 2.24% |
| 6.0 | 7/8 | 7/8 | 17.0 (9.0-32.4) | 87 | 8/8 | 0.51/0.22%, 4.00% |

Same-8-tiles flatbed cell_tight median 14.65 — **the narrow-band cell-line
contrast is FOOTING-INVARIANT (~15-18 median at every footing): the ~3x
M281 re-screen attenuation of the c3 luma cell line is PRINT-frozen.** The
rescue is that the Canon spectrum carries no comb, so every credible line
is lattice-family (cell, cell/2, dot, cell-diagonal) or the 165 lpi screen,
and the formats-registry integer-multiplier arbitration recovers the cell
pitch on 24/24 tile-footings at >=8 px/cell. Weak tiles (cell_tight < 13:
T05/T73/T75) pick a HARMONIC (cell/2) or the cell-DIAGONAL (cell/sqrt2,
folded 45-degree line) or the screen line as the wide-band fundamental —
strict ID fails there but the format path recovers all except T05 at the
6 px footing (only screen + diagonal credible there). Receiver note filed:
the diagonal line does NOT integer-divide the cell pitch — a sqrt2-family
multiplier in the formats hypothesis enumeration would close the T05@6px
case; not built tonight. Lock errors all within the +-4% capture band
(worst 4.0% = T05@6px, at the edge) vs flatbed mislocks to +6%.

**P5-Canon: per-level rates ~HALVE vs the flatbed anchors — and the
decomposition says it is mostly the SCANNER, not the raw px/dot.** All 16
A3 tiles, cross-tile QDA, genie warp (dense-warp v4 verbatim, estimated on
the 4x-dec crops — offsets are in dots, footing-invariant), 6x6
interior-grid cell means sampled from BOTH footings with the SAME warp
(footing = the only variable). Verbatim anchor-construction control
(probe17_canon_p5_verbatim.py, quarter-point sampling) matches the dual-
footing dec leg within 0.04 pp on every level — construction validated.

| level | flatbed 1200 (anchor) | Canon dec 2 px/dot | Canon NATIVE 8 px/dot | native tile range | native MI cal (fb) |
|---|---|---|---|---|---|
| C | 5.27% | 2.77% (verbatim) / 2.81 (dual) | **2.56%** | 1.99-3.01% | 0.895 (0.797) |
| M | 4.27% | 2.25 / 2.29 | **2.05%** | 1.28-3.27% | 0.909 (0.831) |
| Y | 8.85% | 5.29 / 5.23 | **4.93%** | 3.00-6.91% | 0.811 (0.684) |

7-state cross-tile acc 0.9104 native (0.9033 dec). Scanner swap at the SAME
2 px/dot footing: -47/-47/-40% relative; native footing adds another
-8/-9/-6% relative. The 017.0 halved-error Canon-ESTIMATE is CONFIRMED in
total (pred C 2.64/M 2.14/Y 4.43 vs measured 2.56/2.05/4.93; Y slightly
under-delivers) but its mechanism was mis-attributed — the win is Canon
optics/noise/comb-free capture, available already at a 2 px/dot decimation
of the 4800 scan. Y stays the weak level (ordering preserved, miss-dominant
1.7:1). Per-tile BER correlates flatbed-vs-Canon at r = 0.76/0.91/0.98
(C/M/Y) — position variance is print-frozen, no scan-side stationarity
alarm. LDPC rung overlay (measured split-half-calibrated LLRs on real
ladder codewords, 144 4096-cell blocks/level, ZERO wrong decodes anywhere,
both legs both footings):

| rung | C nat | M nat | Y nat | (flatbed Y anchor) |
|---|---|---|---|---|
| r0550 | 1.000 | 1.000 | 1.000 | 0.896 |
| r0625 | 1.000 | 1.000 | 0.993 | 0.646 |
| r0700 | 1.000 | 1.000 | 0.896 | 0.222 |
| r0775 | 1.000 | 1.000 | 0.556 | 0.000 |
| r0850 | 0.757 | 0.785 | 0.028 | 0.000 |

**Rung consequence (RECOMMENDATION, not a freeze — one scan of one sheet of
one engine on one day; conservative doctrine = multi-sheet minima):** this
sheet SUPPORTS C r0700 / M r0700 / Y r0625 (net 117.3 b/mm2 at the P5
accounting: rate x CRC x pilot/dust/edge furniture, no fountain factor —
squarely inside the 017.0 "Canon-est 108-117"). Recommended re-freeze
candidate with one rung of margin on every level: **C r0625 / M r0625 /
Y r0550 = net 103.6 b/mm2** (vs the frozen floor 94.5; on the e017 page as
built, x0.800 fountain K/N). By the 013/016 BER-class gates the measured
levels read C 2.56 (r0700-class) / M 2.05 (r0700-class) / Y 4.93
(r0550-class, r0625 = the this-sheet stretch). HOLD the re-freeze until
the xerox-e004 Canon rescan (engine 2) and ideally a second-day scan;
rungs are volume parameters (gen_e017 regen + golden bump, layout stays 4).

**P1-Canon: the W-vs-CM word-site luma margin is mostly PRINT-frozen —
modest scanner gain, negligible footing gain.** 16 A3 tiles, same warp
machinery, luma reduction vs the C|M|Y union GT, probe17_stagea_luma
statistics verbatim: native oracle median 4.56% / worst-tile 7.38% (T73);
pinned-2-GMM site-population median 4.85% / worst 7.45% (flatbed: oracle
5.15/8.45, sites 5.45/8.51; Canon dec leg sits between at 4.98/7.60).
Site-fit tracks oracle within 0.3 pp (P1's Stage-A rule replicates at the
real footing); the all-cells fit penalty shrinks to ~0.1 pp here (was up
to 2x on the flatbed) — the wired site-fit remains the right default.
Word-fail, exact binomial (100,23) t=13: median tile 3.4e-4, worst tile
1.6e-2 — Stage-A word acquisition comfortably inside budget everywhere,
worst tile included. Nulls (rolled GT) 0.494-0.505 on every tile/footing.

**Caveats, honestly:** single scan / single sheet / single day / one engine
(home M281 print); genie warp + cross-tile QDA footing (the blind pipeline
adds dust-label starvation, offset-field and PAVA-survivorship costs —
same footing as the 017.0 anchors, so deltas are commensurable); LDPC
yields are overlay-on-real-LLRs, not a blind page decode; the P2 tile set
is 8 of 16 (spread pick), P5/P1 use all 16; instrument sweep is one strip
pair, not the owed Canon characterization protocol (rotated-scan
attribution, MTF, step catalog still pending); the flatbed-vs-Canon "dec"
comparison shares the Canon's optical chain (a 2 px/dot decimation of a
4800 dpi capture has better effective MTF than a native 1200 dpi flatbed
pass — that IS the measured scanner effect, stated as such).

## 017.6 — first hardware decode FAILED; PAVA wiring bug found + fixed; residual is the channel (2026-07-10, zero print)

**017.5 decode, honest numbers (driver `decode_e017.py`, footing as frozen:
3x3 box decimate to 1600 dpi = 8 px/cell, 600-cell windows, align_to_field,
global detector, rgb features, PAVA on):** acquisition HEALTHY — 14/15
windows, pitch 8.000 px, geomY confirmed, orientation/counter unanimous,
pilot_ber_est 8.04%, coverage 94.7%. Payload detection CATASTROPHIC and
level-order INVERTED vs the same-day 017.4 anchors: **C 15.66% (anchor
2.56), M 22.05% (anchor 2.05), Y 26.57% (anchor 4.93)**. Certified interior
symbols C 378 / M 25 / Y 5 of 782 (need 626/level); volume NOT decoded
(deficits 248/601/621). Report: build/e017_scan_report.json (017.5 state);
state pickle build/e017_state.pkl is from the buggy receiver — any re-decode
must use `--fresh`.

**Receiver defect found (clean-render forensics; scripts
scratch/e017dbg_{repro,dissect,crossfit,scales,ablate,fullpage,native,
sampling}.py; retired 2026-10-09, the result stands in this entry):** the driver selftest had already recorded the smoking gun —
window (4829,509) of the CLEAN full-page render reads C 0.00 / M 50.03 /
Y 49.96% (deterministic, window-specific; page-wide selftest M/Y 3.98/3.97%
= one latched window averaged over 15). Ablation ladder on that window:
dust labels 1800/1800 == GT; zero-offsets -> 0/0/0; calibrate=False ->
0/0/0; genie dust labels -> still 50/50. The defect is the PAVA block in
`acquire._color_payload_stage`, TWO coupled wiring errors:

1. **Cross-fit scale mismatch (the latch).** The calibration map was fit on
   2-fold CROSS-FITTED dust scores (each dust half scored by a QDA trained
   on the other half) and then applied to FULL-model payload scores. QDA
   level-LLR magnitudes are covariance-determined and differ arbitrarily
   between fits — measured 100-1000x on the clean render (half-model nodes
   at +-1.9e17 vs full-model payload cloud at +-3e14, level M). The
   interpolated p=0.5 crossing (midpoint of the two block means, -5.7e15
   for M / +5.5e15 for Y) landed entirely OUTSIDE the payload score cloud
   -> every cell mapped to one side -> constant pre-descramble bit ->
   payload = keystream = exactly 50% BER. C survived by luck (its midpoint
   fell inside the bimodal gap). The map is only meaningful on the score
   axis it is applied to; **cross-fit PAVA is RETIRED WITH DATA** — scores
   are now the full model's own in-sample dust LLRs (the known 014.2
   over-confidence direction, 0.03-0.06, bounded by the 1/(n+2) clamp;
   `pava_in_sample` in diagnostics).
2. **Degenerate-map boundary displacement.** With perfectly separated
   calibration data PAVA collapses to 2 nodes and the interpolated boundary
   sits at the block-mean midpoint — systematically displaced from the
   model's own decision boundary (score 0) because 8-state marginal LLR
   side-clusters have unequal magnitudes; after fix (1) alone the clean
   left-edge window still read M 12.57%. Fix: a (0, 0.5) node is anchored
   into the map when score 0 falls inside a node gap and the insertion is
   monotone (no-op where the empirical map has resolution around 0).

Fix: src/paperholo/acquire.py `_color_payload_stage` (cross-fit block
deleted, `_anchor_zero` added). Regression:
tests/test_e017.py::test_e017_left_edge_window_pava_sign_safe replicates
the exact failing selftest window (field cells 540..1140 x -1..600 at
8 px/cell incl. the 5 px sub-cell crop offset) — FAILED pre-fix at M 50.03%
(and at M 12.57% with fix 1 alone), passes post-fix at **C/M/Y
0.000/0.000/0.000%**. Full suite **328 green** (8m13s) incl. K goldens and
the 012.3 e012-scan regression class. Docs updated: COLOR-DESIGN D4,
LAYERS.md cmy8-c3 registry row. Post-fix clean full-page sweep (all 15
selftest windows, e017dbg_fullpage.py): 13/15 exactly 0.00/0.00/0.00%,
win@(4829,4829) 0.08/0.10/0.11%, win@(9149,4829) 1.88/1.98/2.13% — the
last is a SPURIOUS per-plane offset fit on the clean render (fitted
global dy ~+1.15 dots where truth is 0; anchor-NCC outliers tilting the
Theil-Sen at that window) = a small separate offset-stage residual, noted
not chased (~0.14%/level page-wide vs the pre-fix 3.98%).

**Real-scan verification (central 600-cell window, shipped path):** before
C 13.32 / M 17.85 / Y 25.04% -> after **C 12.94 / M 17.89 / Y 25.08%**.
The receiver bug was REAL but SECONDARY on this scan (~0.4 pp here;
window-latching variability accounts for part of the page-wide 15.66/22.05
vs central 13.3/17.8 spread). Anchor-class BERs are NOT restored -> per
the pre-registered stop rule the full re-decode was NOT run; the residual
is attributed below.

**Residual attribution (ablation ladder + probes on the real central
window, scratch/e017dbg_real-center.json):** the residual is
CHANNEL-side, not receiver-side —
- labels exonerated: dust labels 1800/1800 == GT, pilot labels 10000/10000;
  genie-QDA (GT-trained, same window) 13.18/17.84/24.95 == dust-trained;
- registration exonerated at window scale: zero-offsets 13.37/17.92/26.23
  ~= as-fit; P4-pinned offsets WORSE (22.6 C) — the P4 e004-sheet offsets
  do not transfer to this print;
- receiver sampling exonerated: 2x2 +-0.25-cell house sampling vs the
  anchors' 6x6 +-0.375 grid = identical (12.83/17.59/26.06 vs
  12.72/17.60/26.01, genie cross-fit);
- in-sample 8-state ceiling on this window: 0.569 (holdout 0.565) — the
  FEATURES do not separate the states;
- per-GT-state level errors (6x6, genie): the CMY TRIPLE is catastrophic
  (state 7: C 24.8 / M 43.3 / Y 52.4%), multi-ink states degraded (CM: M
  25.6%; CY: Y 37.0%; pureY: Y 26.3%). The 017.4 anchors were measured on
  e004 A3 7-STATE fields (no triple) — P6's "home triple toxic" fact at
  full strength, now on 12.5% of cells by keystream uniformity, dragging
  neighbors;
- the print itself is degraded vs the anchor sheet: word channel (W vs CM,
  luma) 8.04% page-wide vs 017.4's median 4.85 / worst-tile 7.45%.

**Verdict: e017-as-built (uniform 8-state) on the CURRENT Y-starved M281 is
not decodable at the frozen rungs on M/Y; the 017.4 GO extrapolated 7-state
anchors to the 8-state alphabet.** C partially survives (378/626 needed).
Options, in measured-cheapness order: (a) print e017.ps verbatim on the
AltaLink (P6: uniform-8 MEASURED best on engine 2, 2.208 > best-7 2.138;
MIC caveat applies — AltaLink color sheets are not anonymous), (b) Y
cartridge swap + reprint (the standing M281 comparability item), (c)
multi-scan F6 passes on this sheet (expected insufficient at 13-25%
single-scan BER), (d) format-axis fallback: 7-state/triple-free or
triple-depopulated keystream = layout_version bump + P5-class re-anchor on
THIS engine state. Decision deferred to the user (hardware queue).

Artifacts: debug scripts scratch/e017dbg_*.py (repro/fullpage/ablate/
dissect/probe_stage/crossfit/native from the interrupted 017.5 session —
native's dec->native mapping leg is BROKEN, its native-footing numbers are
invalid; scales/sampling added this session; retired 2026-10-09, their result stands above); reports
scratch/e017dbg_real-center.json (ablation ladder verbatim). The selftest
report build/e017_selftest_report.json still carries the pre-fix latched
window (page M/Y 3.98/3.97%) — regenerate on the next driver run.

## Addendum 2026-10-09 — an unlogged capture

`scratch/hp-e017-arch-c-canon-4800rgb-take2.tiff` (6,875,455,728 B, mtime 2026-07-10 17:41), never logged
here; read by `experiments/021-payload-regions/qualify_e021.py`. sha256 from the raw-hash pass of 2026-10-09 (sha256 over the retained evidence):
`bb87b3790e4f6b549db0cb8537ecb36a4ac669cf961177a1970159a0668e48b5`.
