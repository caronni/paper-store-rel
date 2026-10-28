# Experiment 002 — self-describing calibration page (protocol)

Goal: one A4 sheet that characterizes ANY Level-2 engine — full ChannelParams +
modulation recommendation from a single print + scan — and that describes itself
at print time (device query -> text + 2 machine strips), so a bare scan decodes
without the repo. Scratch sheet: fiducials/test structure allowed (DESIGN.md R3
exempt). Implements the arbitrated three-lens panel design (postscript
implementability / channel measurement / scan analyzability).

## Artifacts (regenerate byte-identically; sha256 gates reuse)

- `002-calibration-page/gen_calpage.py` -> `build/calpage.ps`,
  `build/calpage_manifest.json`, `build/calpage_gt/*.npy`.
  SEED `paper-store/exp002-calpage`, LAY=1, jobid = sha256(SEED+"/layout1")[:8]
  = `2b7b26b5`. Default `--hwres 600`; only regenerate at another value AFTER a
  first sheet's strip reports a different granted resolution.
- `002-calibration-page/stripdec.py` — reference strip decoder (pure numpy):
  border find -> clock-pair sampling -> parity/row-XOR/CRC -> key=value dict.
  Handles 0/180 deg; for the rotated scan B, rotate back before decoding.
- Preflight (gates the print, CLAUDE.md sim-before-toner):
  `env/bin/pytest -q tests/test_calpage.py` — determinism, occupancy/label
  geometry, gs render at 600+1200 dpi with both strips CRC-validated, and
  pixel-exact ground-truth crops.

## Page inventory (mm, top-left origin; 220 patches, ~5.2 MB PS)

| block | x | y | content |
|---|---|---|---|
| human text | 16–196 | 6.5–19.3 | title, 3x130 B payload echo, scan protocol (print-time) |
| corner marks | (10,10) (200,10) (200,288) (10,288) | | chiral: 1/2/3/4 satellites TL/TR/BR/BL, 3-dot cross 60-dot arms |
| machine strip #1 | 8–191.9 | 20–22.8 | 724x11 modules, 5x78 B payload + CRC-16/CCITT-FALSE |
| top ruler | 10–198.3 | 25.5–28.1 | 0.1" ticks, inch indices 0–7 (1 start + 4 bit + parity modules) |
| left ruler | 6–9.5 | 30–271.5 | same, vertical, indices 0–9 |
| phase strip | 10.5–15.5 | 30–271.8 | K 3-on/3-off horizontal lines -> transport function |
| bands K/C/M/Y | 18–184 | 30/58/86/114 (+28) | 17x 8mm structural (lines H/V p1-4, checker n1-4, dots n1-2, holes n1-3); densities 10–90 c3, solid, encode c1 8/c2 12/c3 14/c4 12 mm, slant-edge 12 |
| reg quads x5 | 191–197.4 | 30/86/142/198/254 | K cross + C/M/Y at +5 mm offsets |
| overlay solids | 18–124 | 143.5 | C M Y K CM CY MY CMY KCMY, 10 mm |
| canaries | 128–179 | 143.5 | setgray 0.75/0.50/0.25 refs; 1-dot phase pairs V+H |
| fields row | 18–144 | 157.5 | 8-state CMY 20, 16-state CMYK 20, mlvl K+C 15 ({0,3,6,9}/9), K c3 ref 18, CMY c2 18 |
| probe row | 18–159 | 181.5 | CMY c3 composite 25; rectfill-vs-imagemask checker n3 + 2-dot lines; quiet zone 28x28 (MIC hunt); aggressive: C/M Nyquist combs + 1-dot grids C/M/Y |
| big fields | 18–188 | 213.5 | K 50% c3 warp 60x60; CMY mottle 40; Y stress (c3 20, 30/70%, 1-dot HV); K banding 20x113.4 (y 159.5–272.9) |
| bootstrap text | 82–166 | 256.7–263.4 | strip format + seed + decoder pointers, 5 pt |
| machine strip #2 | 8–191.9 | 279.5–282.3 | identical payload |
| END sentinel | 18–60 | 286.5–289.3 | 2.5 mm K square + "END 2b7b26b5" — LAST element in stream |
| plus lattice | 25.4 mm grid | | 8 marks in residual whitespace (occupancy-checked) |

Cuts (channel-lens priority order; recorded in the manifest): verniers;
multilevel M+Y; bottom cell=3 replicas + K 40x40 rehearsal; C/M/Y banding
strips; orientation triangles; top (fast-axis) phase strip; 1200-grid stripe
probes; encode c1/c4 downsized to 8/12 mm (c2 >= 12, c3 >= 14 kept full size).

Payload deviation from the panel design: the `G=<date>` field is omitted — a
date literal breaks byte-identical regeneration (CLAUDE.md determinism); print
dates live in this log's run entries instead.

Implementation deviation from the panel PS design (measured, gs 10.07): the
ELEM guard must NOT `grestoreall initgraphics` — grestoreall unwinds to the
pre-setpagedevice gstate and silently reverts the device (page came out
Letter-sized). ELEM is `mark exch gsave stopped grestore cleartomark`; every
element instead starts with `initmatrix` (DOTSPACE) so leaked CTM state cannot
displace later elements. Second observation: gs invoked with `-rN` keeps N dpi
(the job's HWResolution request does not downgrade it) while PageSize IS
honored — RD/RE in the strip record exactly this.

## Physical run protocol (hardware rules apply — ask user first)

1. Preflight green (`pytest -q`), sha256 of calpage.ps recorded below.
2. Print ONE sheet: `../../scripts/print_plane.sh build/calpage.ps`
   (JetDirect 9100 only; never CUPS/lpr). Loupe-check strip #1 modules and the
   1-dot regimes before trusting anything downstream.
3. Scan A: flatbed 1200 dpi, RGB (48-bit if the driver allows), descreen /
   sharpen / auto-contrast OFF, full page including paper edges and all four
   corner marks. Save to `scans/`, record sha256.
4. Scan B: same settings, sheet rotated 90 deg on the platen (printer-vs-
   scanner anisotropy separation). Optional scan C at +24 h (hygroexpansion).
5. `python stripdec.py ../../scans/<scanA>.png` — both strips must decode with
   CRC ok; RD/RE/PR are the engine fingerprint. Log the decoded payload here.
6. One variable at a time: one sheet per (engine, media). Log every run below:
   date, engine, media, driver path, settings, scan filenames + sha256.

## RESULTS

### Run 002.0 — CAL-1 first print + full analysis (2026-07-04)

#### Run header

| field | value |
|---|---|
| date printed | 2026-07-04 (confirmed; scans same day 13:50/13:53) |
| engine | HP Color LaserJet Pro MFP M281fdw ("<host>") — confirmed from the sheet itself: machine-strip payload `PR=HP Color LaserJet MFP M281fdw`, fw `V=3017`, `RV=1`, `SN=-1`, `LL=3`, both strips CRC-16 ok, payload == printed header echo |
| media | plain office A4, 90 g/m², white, inkjet/copier grade, ECF (elemental-chlorine-free; NOT ISO 9706 archival stock — scratch-sheet appropriate, user-confirmed) |
| driver path | **`lpr -o raw`** (CUPS raw queue — user-confirmed), NOT port 9100. Acceptable for this scratch sheet: canary G + strip fingerprint prove the PS executed on the device interpreter, and 001.3 established transport equivalence. Port 9100 stays canonical for data sheets. |
| job | `calpage.ps`, sha256 `39ce59e51e70690896e23fc414e4c77af83ede923818d2acd41a1ba24241534b`, jobid `2b7b26b5`, seed `paper-store/exp002-calpage`, LAY=1 |
| HWRes | requested 600x600, granted 600x600 (strip `RE`), **measured 600x600** (2.000 scan px/dot + ruler scale — truth hierarchy satisfied) |
| scan 1 | `scans/test-scan-calpage-bw.png` grey 8-bit 1200 dpi, sha256 `aa1dff262688244148c1f895878fec9d96ae27cbe894e922195288c4a4e323de` |
| scan 2 | `scans/test-scan-calpage-color.png` RGBA 1200 dpi, sha256 `2bbb87042851dae071bcf197adc1152a979f8cf170019499898ab1795930a9f6` |
| analyzer | `analyze_calpage.py` (cal_core + 5 family modules), report `build/calpage_report.json`, overlays `build/analysis-calpage/` (29 decode-error maps + 2 registration maps), 72 s, exit 0 |
| discipline | 67 BER-style null controls, all in [0.488, 0.512] (gate 0.50±0.02); 10 canary verdicts, each with statistic + control |

#### Registration / geometry

- 17/17 landmarks locked on both scans; residual RMS 1.79 (grey) / 1.90 (color) dots, max 3.3–3.6 dots (coherent transport warp at y≈177 mm, not misregistration).
- Scale x/y = 0.99991 / 1.00183 (anisotropy 1.0019), skew 0.175°, rotation 0.361°. Margins (upper bounds): L 6.0 / T 7.4 / R 7.4 / B 6.4 mm. Ruler index decode 18/18, shifted-position control 0/18.
- Transport: 52 steps (8.6/40 mm), sizes 0.25–1.95 dots (median 0.52), 49/52 replicated in both strip halves — same regime as 001.4. Dominant y-structure is 80/60-mm transport wander (~1.4 dots), NOT density banding.
- Banding: bounded NULL (strongest candidate SNR 3.17 inside permutation-control null; amp upper bound 0.003 D).
- Plane offsets vs K are DRIFT MODELS, not scalars: Y worst, dy −0.5 → −4.9 dots top→bottom (slope −1.9 dots/100 mm); M range −2.6…+1.1; C within ±1.1.

#### Structural (per plane; K on grey scan, C/M/Y on color r/g/b)

| plane | min feature (strict/detect, dots) | gain H/V/2D (dots/edge) | PSF σx/σy (dots, coarse) | Dmax (imagemask path) |
|---|---|---|---|---|
| K | –/3 (white n≤3 keeps <50% area) | +0.29/+0.38/+0.28 | 1.06/1.02 | ≥1.53 (scanner-floor-limited) |
| C | –/3 | +0.59/+0.72/+0.44 | 0.95/1.02 | 1.15 |
| M | 3/3 | +0.09/+0.25/+0.21 | 1.14/1.15 | 2.40 |
| Y | –/– (thin features under-develop) | +0.00/−0.25/−0.06 | 1.17/1.38 | 0.77 |

Dmax provenance (verify-pass correction): measured on the per-plane band solids
(imagemask, bit-faithful). The overlay-row K solid (composite contone path)
reads ≥2.15–2.40 — the re-screened path lays down denser K than raw 1-bit,
consistent with canary A.

All 7 cross-checks against 001.1 K numbers consistent → CAL-1 validated as an instrument.

#### Modulation matrix (hard BER, scanlab v4, 001.4-comparable)

| plane (scan) | c1 | c2 | c3 | c4 | c3 MI bits |
|---|---|---|---|---|---|
| K (bw) | 31.7% | 13.1% | **3.74%** | 2.84% | 0.85 |
| C (color/r) | 34.0% | 15.1% | **3.57%** | 2.45% | 0.78 (hard; soft miscalibrated) |
| M (color/g) | 32.6% | 14.1% | **3.81%** | 1.33% | 0.88 |
| Y (color/b) | 37.7% | 19.5% | **7.18%** | 2.90% | 0.75 |

- K c3 18×18 mm ref patch: 2.58% (001.4: 2.0–2.2%) — same regime, real within-page position variance; no stationarity alarm.
- Composite c3 (3-plane, **screened channel — see canary A**): C 8.8%, M 11.8%, Y 24.0%.
- First color-plane data: C and M match K at cell=3; Y is the weak plane and collapses inside the composite.

#### Alphabet / unmix

- CMY unmix cond(A) = **2.45** (gate 8) — unmix feasible; crosstalk matrix + Dmax now measured (fit on solids; sub-additivity at stacked solids documented).
- 8-state CMY c3: MI 1.76/3.0 bits. 16-state CMYK: MI 1.16 < 8-state → **V-CMYK16 rejected**, K stays a separate binary plane (K-vs-CMY Mahalanobis d=8.3 at cell 3).
- 4-level multilevel: K 0.89, C 0.81 of 2.0 bits, below 1.15×MI2 gate → **rejected**; binary cells stand.

#### Canary table

| letter | canary | verdict | evidence (statistic vs control) |
|---|---|---|---|
| A | screening | **FAIL** | 28.5 dB plane-angle screen peaks in composite (put_cmyk_bitmap) patches; single-plane imagemask patches clean (ctrl bar 6 dB) |
| B | contone_fingerprint | pass | device screen 156 lpi only in setgray patches; imagemask excess 9.8 dB vs 10.6 dB chance floor |
| C | toner_save | pass | K Dmax(grey) 1.33 ≥ 1.1; solid texture 7.9 dB vs quiet-zone 7.6 dB |
| D | resolution clamp (structural + clamp_phase) | indeterminate ×2 | pitch-2 gratings develop to mush (001.1 Nyquist closure) — clamp undecidable on this engine, instrument proven on coarser pitches |
| E | rescale (transport + canary) | pass ×2 | scale dev ≤0.19%, inside hygro envelope; uniformity control clean |
| F | RET/edges | pass | width-excess slope −0.047 dots/dot (2SE 0.055), ESF overshoot 0.021 |
| G | interpreter | pass | 2/2 strips CRC ok; 13/13 fields match header echo; jobid+seed match manifest |
| + | MIC hunt | pass | no yellow-specific periodic structure (blue z=10.2 vs red control z=10.4); STRENGTHENED by the v2 point-process hunt below |

#### Recommendation (§11 decision logic)

- Per plane, cell=3, binary: K R=0.67 (ref patch supports 0.75), C R=0.67, M R=0.67, Y R=0.55.
- Simultaneous CMY: **no-as-printed** — cond passes, but composite path is re-screened by the RIP (canary A), so composite BER (Y unusable at 24%) is an upper bound on the raw channel.
- Estimates (advisory): composite-as-measured 62 bits/mm² (~0.43 MB/side); isolated-plane ceiling 117 bits/mm² (~0.81 MB/side); excludes outer-code + infrastructure overhead.

#### Deviations / findings that need action

1. **§2.4 raw-path violation on composites (canary A, project-wide):** the M281 RIP re-screens DeviceCMYK 1-bit `image` output (`put_cmyk_bitmap`) with plane-angle clustered screens (~165 lpi ±14°, ~212 lpi 45°), while single-plane `imagemask` output is bit-faithful. Every composite/state/overlay patch measured a screened channel. Proposed: DESIGN.md §2.4 amendment + psgen change (per-plane imagemask separations with explicit overprint, or setcolorspace path proven clean), then re-run the composite families.
2. Composite decode used raw r/g/b channels; the measured crosstalk matrix was NOT applied. Re-decode composites on unmixed densities before concluding the composite tax.
3. K/C strict min-white-feature undefined (survives detection at n=3 but <50% flux area) — decision logic consumed the 'detect' tier; DESIGN §11 rule may need a tier annotation.
4. C-plane soft stage miscalibrated on the r channel (ber_llr 5.1% > hard 3.6%) — trust C hard BER; scanlab GMM z-fit on r needs a look before M2.

#### Addendum 002.0a — MIC hunt v2 (user-prompted, 2026-07-04)

Germano spotted yellow dots by eye on cyan patches (e1, o1, sl) — correctly.
Point-process re-analysis of the color scan (page-wide detector: blue-channel
drop >28 counts with red+green unchanged, blob 4-100 px; sensitivity proven by
an injection control — 30/30 synthetic 70-count dots recovered on real
quiet-zone paper, 0 false alarms):

- **Blank paper is clean**: 0 dots in the quiet zone (647 mm^2), 0 in the white
  margins; 10 specks across ~5,700 mm^2 of all unprinted area (0.002/mm^2).
  A MIC pattern tiles blank paper by design — **no MIC on this page** at a
  sensitivity well below published MIC visibility.
- **The dots are real but content-borne**: density by hosting toner —
  pure C 0.223/mm^2, C+M 0.079, pure M 0.020, pure K 0.001 (visibility-limited
  on K). Y-containing fields read 3.2-5.5/mm^2 = the detector correctly seeing
  LEGITIMATE yellow cells (validation, not contamination).
- **Morphology**: at a dot, R and G RISE (+20/+37 counts) while B falls (-69):
  yellow toner with locally displaced cyan — a toner-transfer event, not data.
- **No lattice**: pairwise-difference histogram peaks only near zero lag
  (clumping, NN median ~0.7 mm); no repeated tile vector out to 17 mm.

Verdict: **no MIC; sparse yellow-developer scatter that rides on toner,
preferentially cyan (~0.22/mm^2 ≈ 0.35% of c3 cells hosting a speck)**.
Channel impact: blue-channel-only, sparse — absorbable noise for Y-plane
detection, invisible to C detection (red channel). Logged as a channel fact;
possible causes (Y-into-C developer cross-contamination vs transfer-belt
scavenging) not distinguishable from one page — recheck on the 002.1 sheet.

### Addendum 002.0b — scan B: same sheet rotated 90°, two partial halves (2026-07-04)

#### Run header

| field | value |
|---|---|
| scans | `test-scan-calpage-color-quer-top.png` sha256 `7b6a19cc714f9a86…` (2026-07-04 16:46); `test-scan-calpage-color-quer-bot.png` sha256 `a95b2bcb89fdb5e1…` (2026-07-04 16:48) |
| geometry | SAME CAL-1 sheet as 002.0, rotated 90° on the platen ~3 h after scan A (2026-07-04 13:53); two overlapping halves (A4 297 mm > platen crosswise) |
| analyzer | `analyze_scanb.py` (partial-tolerant wrapper over cal_core; cal_core unmodified), report `build/scanb_report.json`, 24 s |
| discipline | no per-half parameter tuning; every decode with null control; every comparison with stated uncertainty |

#### Partial-page registration (design goal: fragment recovery — first hardware test)

- Orientation from chiral marks alone: top half TL(1)+TR(2), rot90_ccw=3 (≙ 270° ccw to upright); bottom half BR(3)+BL(4), rot90_ccw=1. 2-adjacent-corner bootstrap (similarity_2corner), mirror excluded by satellite inward diagonals.
- Landmark affine: top 12/12 locked, residual RMS 1.46 dots (max 2.17); bottom 13/13, RMS 1.47 (max 2.20). Gate < 4 dots: both PASS.
- Overlap consistency (8 landmarks seen by BOTH halves through two independent placements + registrations): disagreement RMS 1.34 dots, max 2.2 dots (upper bound — includes real local warp).

#### Scale anisotropy separation (the headline)

Log-domain split of page-axis scale into printer/paper (travels with the page) vs scanner axis (stays with the scanner); gauge: scanner mean scale ≡ nominal. Observations: scan A color affine + both scan-B halves; scanner-y measurements carry the measured scan-to-scan repeatability σ=0.16% (scan A grey-vs-color y-scale pair; scanner-x pair repeats to <0.01%).

| | printer/paper | scanner |
|---|---|---|
| page-x | +0.316% ± 0.049% | s_x -0.308% ± 0.047% (axis under page-x in scan A) |
| page-y | +0.090% ± 0.049% | s_y +0.308% ± 0.047% (axis under page-y in scan A) |

- Printer anisotropy p_y−p_x = -0.226% ± 0.030%; scanner anisotropy s_y−s_x = +0.616% ± 0.094%. **002.0's "page-y measures longer" was the scanner, not the print: the printer actually prints page-y ~0.23% SHORT of page-x.**
- Sharpest cut (scanner-x/CCD-axis observations only, immune to transport jitter): -0.223% ± 0.032% (B_top_page_y vs A_page_x); -0.230% ± 0.040% (B_bot_page_y vs A_page_x).
- Shear: scan A +0.175° vs scan B -0.188°/-0.178° in the page frame — magnitude preserved, sign flipped by the 90° rotation ⇒ the skew is a SCANNER-frame property too.
- Single-s_y model residuals ≤ 0.035% across the three color-mode scans; the grey-mode scan-A pass differed by 0.22% in s_y ⇒ scanner-y scale is mode-dependent and drifts scan-to-scan. Absolute print scale along page-y should only ever be measured with that axis on scanner-x.
- CONFOUND (stated, not fitted): 3 h between scans ⇒ hygro drift ±~0.04% (001: ±0.3%/day), anisotropic in general — indistinguishable from scanner anisotropy here; quoted σ exclude it.

#### PSF / gain frame separation

- Slant-edge σ (page frame; q = σ_y²−σ_x²): printer part = (q_A+q_B)/2 travels with the page, scanner part = (q_A−q_B)/2 must be plane-independent — spread over planes 0.052 dots² around mean 0.093 dots².
  - K: σ(A)=(1.094, 1.082), σ(B)=(1.135, 0.99) dots → printer -0.167, scanner +0.141 dots²
  - C: σ(A)=(0.945, 1.017), σ(B)=(0.91, 0.967) dots → printer +0.124, scanner +0.017 dots²
  - M: σ(A)=(1.143, 1.148), σ(B)=(1.153, 1.095) dots → printer -0.061, scanner +0.072 dots²
  - Y: σ(A)=(1.173, 1.384), σ(B)=(1.206, 1.308) dots → printer +0.398, scanner +0.142 dots²
- Grating gain H/V (dots/edge, page frame — Murray-Davies means, first-order scanner-MTF-invariant):
  - K: top H=0.037 V=0.176; scan_A H=0.287 V=0.377; scan_A_color_luma_control H=0.098 V=0.185
  - C: top H=0.561 V=0.694; scan_A H=0.588 V=0.721
  - M: top H=0.044 V=0.231; scan_A H=0.089 V=0.251
  - Y: top H=-0.105 V=-0.256; bot H=-0.087 V=-0.275; scan_A H=0.001 V=-0.249
- K channel control (verify-before-concluding): scan A's reported K (grey scan) reads gain H/V 0.287/0.377, but K re-measured on scan A's COLOR-scan luma reads H/V 0.098/0.185 and slant σ (1.094, 1.082) — the apparent K gain drop in scan B is the measurement channel (bw grey vs color luma), not the printer. All K A-vs-B comparisons above use the channel-matched control; V−H ordering survives in the page frame in both scans (development anisotropy travels with the page).

#### Transport wander attribution

In scan B the phase strip lies along scanner-x (CCD axis — no transport), so r_B(y_page) is print-frozen structure; scan A's r(y) contained printer + scanner-y transport entangled.

| comparison | shared range | corr (detrended) | amp ratio B/A | steps matched |
|---|---|---|---|---|
| top vs scan A | [32.8, 207.6] mm | 0.929 | 0.852 | 4/39 (new in B: 6) |
| bot vs scan A | [89.7, 269.0] mm | 0.883 | 0.843 | 3/34 (new in B: 7) |
| top vs bot (both scanner-x) | [89.7, 207.6] mm | 0.966 | rms diff 0.344 dots | — |

- 80.5/60.4 mm wander (fixed-period LSQ over the shared window): A {'80.48mm': {'amp_dots': 0.964, 'phase_deg': 89.8}, '60.36mm': {'amp_dots': 1.145, 'phase_deg': -107.4}} vs B {'80.48mm': {'amp_dots': 0.991, 'phase_deg': 74.3}, '60.36mm': {'amp_dots': 1.141, 'phase_deg': -106.0}} (top half); see report for bottom. Amplitude and phase reproduce ⇒ the dominant wander is PRINT-FROZEN (printer transport), not scanner.
- The step catalog does NOT reproduce: only 4/39 (top) and 3/34 (bot) of scan A's steps appear in B ⇒ the bulk of 002.0's "52 transport steps" (and by extension the 001.4 catalog, same scanner) were FLATBED-SCANNER transport artifacts, not printer steps. Full unreproduced list in `scanb_report.json`.
- Steps scan B itself sees: 6 (top) / 6 (bot) in the overlap, of which 0 replicate across the two independent placements — NO print-frozen step survives the cross-placement test: the print-frozen transport is smooth (wander), not stepped.
- **Verify-pass addendum — the scanner steps split in two:** mapped through the affines, all 20 of scan B's own "steps" sit on ONE comb at fixed scanner-x = 14.1 + n·18.63 mm (both halves, common phase, uniform ~−0.9 dot) — a deterministic CCD/CIS chip-joint fixed pattern, calibratable once per scanner. The scanner model is therefore: (i) deterministic x-axis FPN comb (18.63 mm pitch), (ii) stochastic y-axis transport steps (the 001.4/002.0 catalogs), (iii) unstable, mode-dependent y scale. Scan A's 4/39 + 3/34 step "matches" are chance-level (~2.6/39 expected) — the retraction is strengthened, not weakened.

#### Spot decode through the rotated partial pipeline (registration-quality proof)

| patch | scan A ref | top half | bottom half |
|---|---|---|---|
| K/encode_c3 | 4.46% (color, contract) / 3.74% (bw) | 2.45% (Δ-2.01 pp, null 0.509) | — |
| C/encode_c3 | 3.57% (color/r) | 2.31% (Δ-1.26 pp, null 0.500) | — |
| encode_K_ref | 2.58% (bw) | 2.58% (Δ-0.00 pp, null 0.501) | 2.06% (Δ-0.52 pp, null 0.500) |

Gate: BER ≤ scan-A ref + 1 pp, one-sided — misregistration can only RAISE BER; two-sided Δ quoted per cell. encode_K_ref sits in the overlap row — decoded through BOTH halves' independent registrations (top-vs-bot Δ 0.52 pp). Decodes IMPROVE with the process direction on the CCD axis — scanner-y transport contributes measurably to scan-A BER.

#### What this changes (follow-ups)

1. **Retraction-grade correction to the transport picture (001.4 + 002.0, same scanner):** the "52 discrete transport steps" are flatbed-SCANNER transport events, not printer physics — they fail both the rotation test (4/39, 3/34 reproduced) and the cross-placement test (0 replicated). The print-frozen printer transport is the smooth 80.5/60.4 mm wander (~1 dot). The sync layer must STILL handle stepped warp — every scan through this flatbed carries fresh y-transport steps, plus a deterministic 18.63 mm x-axis chip-joint comb that a per-scanner calibration can remove — but ChannelParams should attribute steps+comb to the SCANNER model and wander to the PRINTER model. Propose CLAUDE.md engine-facts update.
2. 002.0's `geometry.scale_xy` (and canary E inputs) are scanner-dominated on the y axis; absolute print scale must be referenced to scanner-x. Printer prints page-y -0.23% relative to page-x (hygro-confounded at ±0.04%).
3. Y's large PSF σ_y anisotropy travels with the page ⇒ printer development, as suspected; scanner MTF anisotropy is small (+0.093 ± 0.052 dots²).
4. Partial-page registration from 2 adjacent chiral corners is PROVEN on real hardware (this was a fragment-recovery design goal): 1.34-dot cross-half consistency, decode at scan-A quality through both partial registrations.
5. Consider scanning data sheets with the process direction along scanner-x where the format allows (or accepting two-pass rotated scans): K c3 2.45% vs 3.74–4.46%, C 2.31% vs 3.57%.

#### Addendum 002.0c — alphabet optimization on the measured confusion matrices (2026-07-04)

Blahut-Arimoto + exhaustive subset search over the 002.0 8-state/16-state
confusion matrices (analysis only, `calpage_report.json` data; QDA fold
optimism and the screened composite path apply to all numbers equally):

- 8-state channel capacity **1.893 bits/cell**; uniform-8 delivers 1.757.
  The optimal input puts **ZERO weight on CMY** (triple stack = 300% coverage,
  most-confused symbol): the best uniform 7-symbol alphabet
  **{W,C,M,Y,CM,CY,MY} reaches 1.890 bits/cell** — capacity, for free, by
  dropping one symbol. Best smaller sets: 6 -> {W,C,M,Y,CM,MY} 1.807;
  4 -> {W,Y,CY,MY} 1.623.
- 16-state channel: best 8-subset **{W,C,M,Y,CM,CY,MY,K} = 1.801 bits/cell** —
  K works as a 9th-ish symbol (pure K vs CMY-stack d_M=8.3) even though full
  V-CMYK16 stays rejected; K-MIXTURES are what kill it.
- Per-label-bit view (MLC framing): independent hard decisions on C/M/Y
  presence bits give 0.521+0.458+0.420 = 1.40 bits/cell on the SAME field —
  joint 3-D density classification is worth **+0.36 bits/cell** over
  per-plane thresholding. Y-presence is the weakest label bit (err 0.138),
  so Imai-Hirakawa multilevel coding with per-label rates reproduces the
  §2.6/§7.3 unequal-protection ladder inside the alphabet view.
Comparison anchors (same cell=3, this engine): clean single-plane binary
~0.9-0.96 bits/cell; screened-composite per-channel hard ~1.25-1.40.
Follow-up for the next sheet: 7-state and {7+K} fields at cell=3/4/6 (screen
period ~3.6 dots aliases against 3-dot cells; averaging should lift MI at 4/6).

#### What feeds ChannelParams next (M4 → M2)

From `calpage_report.json` `channel_params.*`, simulator-ingestible: per-plane PSF σ, edge gain H/V/2D, dev thresholds (both tiers), TVI/TRC curves, mottle σ_D vs coverage, scan noise (white-model residuals), banding = bounded null, transport-step catalog (52 steps, 001-compatible), plane-offset drift models, crosstalk matrix + cond. Then: fold into `paperholo.channel.simulator` ChannelParams; M2 soft-LDPC per-plane rate ladder on sim + these numbers; composite re-measurement after the §2.4 fix decides simultaneous-CMY.

### Run 002.1 — composite-emission probe (2026-07-04)

#### Run header

| field | value |
|---|---|
| date printed + scanned | 2026-07-04 |
| engine | HP Color LaserJet Pro MFP M281fdw ("<host>") — no machine strips on this quick probe (by design); printed header echo checked by eye |
| media | plain office A4, 90 g/m², white, inkjet/copier grade, ECF (elemental-chlorine-free; NOT ISO 9706 archival stock — scratch-sheet appropriate, user-confirmed) |
| driver path | `lpr -o raw` (scratch-sheet precedent of 002.0; canonical 9100 path not used for this sheet) |
| job | `composite_probe.ps`, sha256 `58637ad3773315451f0a585bf4419ea395ac36baba5215f5ed04880102086cdd`, jobid `ef68aa50`, seed `paper-store/exp002-composite-probe`, LAY=1 |
| scan | `scans/test-scan-composite-probe.png`, RGBA 1200 dpi, sha256 `c0187114827938058bf11d2c1b5c4cd0710ca2566e74b424fff547b0d7c05a8a` |
| analyzer | `analyze_composite_probe.py` → `build/composite_probe_report.json`, 52 s, exit 0 |
| registration | 69/69 landmarks (4 corners + 65 plus), residual RMS 1.40 dots; rot 0.377°, px/dot 1.99868/2.00864 (y scale +0.43%, hygro envelope); ruler_check reports the expected KeyError (no rulers on this page) |
| discipline | identical analysis parameters across P0–P4 (no per-variant tuning); 23 v4 field decodes, all 23 null controls in [0.496, 0.507] (gate 0.50±0.02); P0 = known-screened positive control, P4 + quiet zone = control bar |

Content check: per-plane GT byte-identical across P0–P3 (asserted); each row
differs ONLY in emission path (P0 `put_cmyk_bitmap` composite image; P1
sequential per-plane `imagemask`; P2 +`true setoverprint`; P3 +OPM 1; P4
single-plane references). Paint order C→M→Y.

#### Discriminator 1 — screening (canary-A spectra, screen-family disk excess, dB)

Families: 165 lpi ±14° and 212 lpi 45° = the device contone screen set measured
in 002.0; 224 lpi ±26.6° = (±1/3,∓1/6) cyc/dot, NEW (see finding 2). Table
shows max disk excess over the variant's patches per scan channel; hit bar =
max(12 dB, GT floor+6); GT chance floors 7–13 dB, quiet-zone bar 8–12 dB.
**P4 baseline (screened at same bar): {165|b, 224|b} — the Y-plane texture.**

| variant | 165 r | 165 g | 165 b | 212 r | 212 g | 212 b | 224 r | 224 g | 224 b | screened beyond P4 bar |
|---|---|---|---|---|---|---|---|---|---|---|
| P0 cmyk image | **22.5** | **23.3** | 16.5 | **22.9** | **24.9** | **21.6** | 12.5 | 11.8 | 10.4 | 165\|rg + 212\|rgb |
| P1 masks | **25.6** | **26.5** | 20.8 | **18.1** | 17.1 | **18.4** | **24.2** | **25.4** | 22.7 | 165\|rg(b) + 212\|rb + 224\|rg |
| P2 + setoverprint | **25.5** | **28.0** | 19.9 | 17.3 | **18.2** | 16.8 | **23.1** | **26.1** | 22.2 | 165\|rg(b) + 212\|g + 224\|rg |
| P3 + OPM 1 | **24.1** | **27.7** | 20.6 | 13.7 | 15.4 | 13.6 | **21.4** | **23.7** | 20.4 | 165\|rg(b) + 224\|rg |
| P4 single refs | 10.2 | 9.8 | **20.6** | 9.7 | 9.1 | 13.8 | 8.0 | 12.7 | **23.0** | (baseline) |

- P0 fails exactly like 002.0 canary A (positive control good): contone screen
  set 165+212, plus 441-lpi dot-grid sidebands of the 165 screen; no 224.
- **P1/P2/P3 are ALSO re-screened**: the 165 family appears in their C and M
  separations (r/g) at 20–28 dB where P4 ref_C/ref_M read 9.8–10.2 dB. Even
  the NON-knocked top plane (M in field_cm, painted last, full content)
  carries the M screen at 20.0–22.8 dB → the surviving content of overlap
  regions goes through a screened contone path too.

#### Discriminator 2 — knockout (err split by other-plane GT; solids by density)

Miss rate = P(decoded 0 | GT ink 1), split at overlap (later-painted plane(s)
ink=1) vs clear sites. Gate: knockout if miss@overlap ≥0.40 and ≥3× clear.

| variant | C under M (field_cm) | C under M∪Y (field_cmy) | M under Y (field_cmy) | CM-solid D_r | presence_C (r-density arithmetic) | solid verdict |
|---|---|---|---|---|---|---|
| P0 | 0.099 / 0.003 | 0.107 / 0.000 | 0.222 / 0.003 | 0.699 | **+0.56** | both inks present |
| P1 | **0.610** / 0.000 | **0.542** / 0.000 | **0.730** / 0.000 | 0.051 | **−0.00** | C knocked out |
| P2 | **0.610** / 0.000 | **0.542** / 0.000 | **0.702** / 0.000 | 0.050 | **−0.00** | C knocked out |
| P3 | **0.603** / 0.000 | **0.547** / 0.000 | **0.722** / 0.000 | 0.053 | **−0.00** | C knocked out |

References: D_r C100 = 1.163, D_r M100 = 0.053; P1–P3 CM solids read D_r
0.050–0.053 = exactly M100 → **the C plate is EMPTY under M** (gs P1
prediction `C sep == C&~M` confirmed on the real RIP for P1 AND P2 AND P3).
P0 presence_C 0.56 (sub-additive stacked solids, as documented in 002.0) =
both inks. The eyeball pre-read ("P1/P2/P3 CM solids look magenta-only") is
confirmed and quantified.

P2/P3 vs P1 — any overprint effect at all? All discriminators identical
within noise (BER deltas ≤0.013, miss rates ±0.03, presence_C identical). The
single observed difference: P3's CM-solid D_g = 2.07 vs 2.40 for P1/P2/P4-M100
(2.40 = scanner-floor cap) — one patch, direction "slightly lighter M at the
overlap", NOT overlap preservation (its C plate is still empty). Verdict:
`setoverprint`/OPM are accepted (job printed) but functionally **ignored**.

#### Discriminator 3 — per-plane hard BER vs P4 references (same scan)

| patch | P0 | P1 | P2 | P3 | P4 ref |
|---|---|---|---|---|---|
| field_cm C (r) | 6.14% | 31.9% | 31.8% | 31.3% | 4.48% |
| field_cmy C (r) | 9.75% | 43.1% | 43.2% | 43.1% | 4.48% |
| field_cm M (g) | 5.54% | 6.69% | 6.84% | 6.67% | 4.55% |
| field_cmy M (g) | 12.6% | 37.9% | 36.7% | 37.6% | 4.55% |
| field_cmy Y (b) | 20.1% | 17.1% | 17.8% | 18.2% | 8.27% |

- P0's composite tax in the CMY field — C +5.3, M +8.1 points — reproduces
  002.0's composite measurement (C +5.2, M +8.0) almost exactly; Y +11.8 here
  vs +16.8 there (smaller patch, position variance). Same screened channel.
- Y (top plane, never knocked out) inflates to 17–20% in ALL variants via
  b-channel false positives over C/M ink (fa@overlap 0.27 vs 0.003 clear,
  miss flat) — crosstalk, not knockout; the 002.0 unmix TODO applies.
- Among the knocked-out variants P1–P3, nothing reaches the +0.02 gate of P4
  (closest: field_cm M at +0.021). P0's field_cm C (+0.017) and M (+0.010) do
  sit inside the per-patch gate — but P0 fails qualification on screening.

#### Verdict (protocol decision rule)

**NO variant qualifies.** P0 = screened composite (bit-unfaithful, overlap
preserved). P1 = P2 = P3 = full knockout of every earlier plane under every
later plane AND re-screening of the surviving content — worst of both, and
`setoverprint`/OPM have no measurable effect on this RIP. Adopted path: none.

Consistent mechanistic reading (interpretation, not a measurement): the M281
RIP composites overlapping paint at the object level in an opaque contone
space — a later `imagemask` erases earlier plane content under its mask
regardless of overprint state — and regions touched by overlapping objects
are then re-screened with the device screen set; only non-overlapping
single-plane `imagemask` output stays on the bit-faithful 1-bit fast path.

### Finding 2 (new channel fact, needs follow-up): Y-plane 224 lpi texture

Single-plane Y `imagemask` fields carry a narrowband (±1/3,∓1/6) cyc/dot =
224 lpi ±26.6° (rational tangent 1/2) structure: P4/ref_Y 23.0 dB here, and
the SAME statistic on the 002.0 CAL-1 color scan reads 21.1–23.5 dB on
Y/encode_c3 + Y_encode_c3 (C/M imagemask fields: 8.5–9.4 dB = chance floor).
So it is a pre-existing Y-plane property of the imagemask path — 002.0 canary
A only spectrum-checked K+M and could not see it — NOT an overlap-path
effect. Note the put_cmyk_bitmap composites do NOT show it (10.4–11.7 dB on
both sheets), and a Y contone screen at HP's conventional ~0°/200 lpi would
sit exactly ON the cell=3 lattice bins (1/3, 0), invisible to every
off-lattice statistic in this suite. Open question: is the Y plane
re-screened even on the imagemask path (candidate explanation for Y's higher
base BER, 7.2–8.3% vs C/M 3.6–4.6%)? Discriminating test: a Y-plane pattern
whose spectrum avoids the lattice, or a cell=4/cell=5 Y field (moves the
lattice off 224's alias partners).

#### DESIGN consequence — §2.4 amendment needed; option space (no decision here)

§2.4's raw-path assumption ("bitmap reaches the engine bit-faithfully") holds
ONLY for non-overlapping single-plane `imagemask` content (with the Y-plane
224-lpi caveat above). For overlapping CMY planes the measured options are:

- **(a) Separation-colorspace probe** (protocol fallback a): one more scratch
  sheet emitting `[/Separation /Cyan ...] setcolorspace` paint — preserves
  overlap in gs even at OPM 0; unknown on the real RIP. Cheapest next
  hardware step; keeps the simultaneous-CMY door open.
- **(b) Keep `put_cmyk_bitmap` and model the screened channel as measured**:
  P0/002.0 numbers stand — C ~9–10%, M ~12–13%, Y ~20–24% at cell=3 in the
  3-plane field. Y is likely below any useful inner-code operating point;
  this fallback probably forfeits simultaneous CMY (§11 decision reopens on
  these numbers).
- **(c) Layout-level plane exclusivity**: never overlap planes spatially
  (per-region single-plane imagemask stays on the clean path). Zero RIP risk,
  but caps areal density at the isolated-plane ceiling and reopens the
  §10.2/§11 capacity trade — a DESIGN-level discussion, not an emission fix.

Whichever option is chosen, DESIGN.md §2.4 needs an amendment describing what
the RIP actually does (object-level opaque compositing + re-screening of
overlaps; overprint controls ignored), and the composite/state/overlay
families of gen_calpage stay on hold until the emission path is settled.

### Run 002.2 — overlap-fidelity 2 + screened-channel cell sweep (2026-07-04)

| field | value |
|---|---|
| sheet | `build/overlap2.ps`, sha256 `9908e7ffd04f598ecdf54487f068f792e387f530225fe0400adfbd845b836f5f`, jobid `f8e2bf4d`, seed `paper-store/exp002-overlap2`, manifest sha `a1aaf85e...` |
| printed | 2026-07-04 18:15, `lpr -o raw` (queue HP_Color_LaserJet_MFP_M281fdw__<host>_, job -87) — printed by Claude with explicit one-page user authorization |
| media | same 90 g/m² ECF office stock as 002.0/002.1 |
| contents | Block A (screened cmyk-image path): 7-state {W,C,M,Y,CM,CY,MY} fields c3/c4/c6, {7+K} c4, 3-plane 50% composites c4/c6, single-plane mask refs C/M/Y/K c4 + K c6. Block B (stream tail, guarded): S1 Separation-space masks + setoverprint, S2 +OPM dance, S3 DeviceN 3-comp image — per-plane content byte-identical across S1-S3 |
| preflight | 35/35 tests; zero verifier findings; gs tiffsep: Block A + S1/S2/S3 all pixel-exact per plane (gs honors Separation overprint WITHOUT OPM — the 002.1 P2 mechanism does not apply to Separation spaces); pins gridtest/calpage/composite_probe intact |
| decision rule | adopt first S-variant that is screen-free + knockout-free + BER ≈ mask refs on PAPER; separately: alphabet MI at c4/c6 vs the c3 1.76/1.89 baseline (screen-averaging hypothesis) |
| scan | `scans/test-scan-overlap2.png`, RGBA 1200 dpi, sha256 `19e58f247c31faf7e55a2a1aa303f2e8cafb22c64a150bfe2b66b146e588be62` |

#### Block B — S-variant verdict (002.1 decision rule, same gates)

| variant | screened beyond A4 bar | worst miss@ovl / clear | CM solid r-med (presC-D) | max BER Δ vs 002.1 P4 c3 (C/M/Y) | qualifies |
|---|---|---|---|---|---|
| S1 | 165lpi_pm14deg·g, 165lpi_pm14deg·r, 224lpi_pm27deg·g, 224lpi_pm27deg·r | 0.719 / 0.000 | 222.1 (-0.00) | +0.376/+0.326/+0.094 | False |
| S2 | 165lpi_pm14deg·g, 165lpi_pm14deg·r, 224lpi_pm27deg·g, 224lpi_pm27deg·r | 0.735 / 0.000 | 220.8 (-0.00) | +0.376/+0.332/+0.105 | False |
| S3 | 165lpi_pm14deg·g, 165lpi_pm14deg·r, 212lpi_45deg·b, 212lpi_45deg·g | 0.160 / 0.016 | 49.8 (+0.55) | +0.080/+0.058/+0.115 | False |

Anchors (002.1 sheet, same scanner+day, CROSS-SHEET): CM-solid r-median knockout 219–220, overlap-preserved (P0) 49.5, C100 17.0, M100 218.6; P4 c3 refs BER C 0.0448 / M 0.0455 / Y 0.0827.
A4 clean-ref screening bar (this sheet): ['165lpi_pm14deg|b', '212lpi_45deg|r', '224lpi_pm27deg|b']. NOTE (verify pass): the 212|r entry in this bar is a CELL-LATTICE ALIAS, not a device screen — the 212-lpi family point (0.25, 0.25) cyc/dot is a c4 lattice bin, and the A4 refs are c4. The S fields are c3 (all three families off-lattice), so S-variant judgments are unaffected; S3's 212|r (21.2 dB) is real screen structure swallowed by the aliased bar — it does not change any verdict (S3 is screened via 165|rg + 212|gb).
Decision: adopted = **None**. S1 = S2 = knockout + re-screen (the 002.1 P1–P3 failure, now reproduced in Separation color spaces; setoverprint/OPM again without effect). S3 reproduces the P0 channel almost exactly (solid r-median 49.8 vs P0 49.5, presC +0.55 vs +0.56; field BERs within ~2.8 pp of the P0 anchors): DeviceN-image = put_cmyk_bitmap, one more emission path with the same RIP behavior, not a new channel.

#### Block A — alphabet sweep (screened cmyk-image path)

| field | cell | states | acc | MI uniform | BA capacity | best-subset (same size as 002.0 comparisons) | null ok |
|---|---|---|---|---|---|---|---|
| A1/state7_c3 | c3 | 7 | 0.724 | 1.479 | 1.484 | 1.478 ({W,C,M,Y,CM,CY,MY}) | True |
| A1/state7_c4 | c4 | 7 | 0.845 | 1.980 | 1.987 | 1.980 ({W,C,M,Y,CM,CY,MY}) | True |
| A1/state7_c6 | c6 | 7 | 0.995 | 2.759 | 2.759 | 2.759 ({W,C,M,Y,CM,CY,MY}) | True |
| A2/state8k_c4 | c4 | 8 | 0.840 | 2.074 | 2.210 | 2.070 ({W,C,M,Y,CM,CY,MY,K}) | True |

c3 stationarity: measured 7-state c3 MI 1.479 vs 002.0's best-7 1.890 (Δ -0.411, tol ±0.08) → DOES NOT replicate. (002.0's number is a subset computation on a printed 8-state field; here the 7-state alphabet is printed directly.)

#### Composites c4/c6 — raw channel vs unmixed (crosstalk matrix applied; the 002.0/002.1 TODO)

| field | plane | v4 raw BER | rigid raw BER | unmixed BER | v4 MI | unmixed MI | same-sheet clean ref BER (c4) |
|---|---|---|---|---|---|---|---|
| A3/comp_c4 | C | 0.0402 | 0.0435 | 0.0436 | 0.759 | 0.742 | 0.0239 |
| A3/comp_c4 | M | 0.0472 | 0.0556 | 0.0832 | 0.727 | 0.587 | 0.0308 |
| A3/comp_c4 | Y | 0.1437 | 0.1500 | 0.0791 | 0.411 | 0.601 | 0.0329 |
| A3/comp_c6 | C | 0.0222 | 0.0041 | 0.0050 | 0.847 | 0.957 | 0.0239 |
| A3/comp_c6 | M | 0.0214 | 0.0146 | 0.0252 | 0.851 | 0.830 | 0.0308 |
| A3/comp_c6 | Y | 0.0548 | 0.0719 | 0.0182 | 0.695 | 0.869 | 0.0329 |

002.0 c3 composite anchors (cross-sheet): C 8.8% / M 11.8% / Y 24.0%.

#### Screen tax vs cell size (family disk excess − own GT floor, dB)

| patch | ch | 165 lpi | 212 lpi¹ | 224 lpi² |
|---|---|---|---|---|
| A1/state7_c3_C | r | 15.8 | 16.1 | 1.9 |
| A1/state7_c3_M | g | 18.8 | 14.4 | 6.9 |
| A1/state7_c3_Y | b | 13.1 | 14.2 | 6.9 |
| A1/state7_c4_C | r | 17.2 | 13.1 | 5.8 |
| A1/state7_c4_M | g | 18.2 | 14.9 | 8.7 |
| A1/state7_c4_Y | b | 15.4 | 9.9 | 8.7 |
| A1/state7_c6_C | r | 19.6 | 16.0 | 7.8 |
| A1/state7_c6_M | g | 20.6 | 16.0 | 12.3 |
| A1/state7_c6_Y | b | 15.5 | 13.4 | 4.4 |
| A2/state8k_c4_C | r | 17.5 | 14.9 | 2.7 |
| A2/state8k_c4_M | g | 16.9 | 14.7 | 6.1 |
| A2/state8k_c4_Y | b | 11.2 | 14.8 | 5.0 |
| A2/state8k_c4_K | grey | 15.3 | 21.0 | 4.8 |
| A3/comp_c4_C | r | 15.3 | 14.0 | -0.2 |
| A3/comp_c4_M | g | 16.9 | 14.0 | 1.9 |
| A3/comp_c4_Y | b | 10.2 | 13.2 | 1.4 |
| A3/comp_c6_C | r | 14.4 | 11.1 | 0.5 |
| A3/comp_c6_M | g | 14.4 | 12.3 | 4.3 |
| A3/comp_c6_Y | b | 6.5 | 7.9 | -2.5 |
| A4/ref_C_c4 | r | 0.1 | 16.3 | -0.2 |
| A4/ref_M_c4 | g | -0.3 | 5.4 | 1.4 |
| A4/ref_Y_c4 | b | 9.4 | 9.5 | 11.7 |
| A4/ref_K_c4 | grey | -1.1 | 2.8 | -0.6 |
| A4/ref_K_c6 | grey | 0.5 | -1.3 | 2.4 |

¹ 212-family readings on c4 patches are cell-lattice-aliased ((0.25, 0.25) cyc/dot is a c4 lattice bin) — discount them. ² 224-family readings on c6 patches likewise ((1/3, 1/6) is a c6 lattice bin). The 165 family is off-lattice at c3, c4 AND c6.

Reading: the 165-lpi screen tax does NOT shrink with cell size (13–21 dB at every cell size, all planes) — the RIP screen structure persists; what improves is the DECODE, which averages more screen periods per cell (7-state acc 0.72 → 0.84 → 0.99, MI 1.48 → 1.98 → 2.76 across c3/c4/c6).

#### Bottom line — bits/cell on this engine (input to the modulation decision)

| configuration | cell | bits/cell | bits/mm² | source |
|---|---|---|---|---|
| clean single-plane K binary | c3 | 0.850 | 52.7 | 002.0 CAL-1 (cross-sheet anchor) |
| clean single-plane C binary | c3 | 0.780 | 48.4 | 002.0 CAL-1 (cross-sheet anchor) |
| clean single-plane M binary | c3 | 0.880 | 54.6 | 002.0 CAL-1 (cross-sheet anchor) |
| clean single-plane Y binary | c3 | 0.750 | 46.5 | 002.0 CAL-1 (cross-sheet anchor) |
| clean single-plane C binary | c4 | 0.845 | 29.5 | this sheet, A4 mask ref |
| clean single-plane M binary | c4 | 0.811 | 28.3 | this sheet, A4 mask ref |
| clean single-plane Y binary | c4 | 0.797 | 27.8 | this sheet, A4 mask ref |
| clean single-plane K binary | c4 | 0.856 | 29.9 | this sheet, A4 mask ref |
| clean single-plane K binary | c6 | 0.828 | 12.8 | this sheet, A4 mask ref |
| screened 7-state alphabet (uniform) | c3 | 1.479 | 91.7 | this sheet, QDA MI |
| screened 7-state alphabet (BA capacity) | c3 | 1.484 | 92.0 | this sheet, BA on QDA confusion |
| screened 7-state alphabet (uniform) | c4 | 1.980 | 69.1 | this sheet, QDA MI |
| screened 7-state alphabet (BA capacity) | c4 | 1.987 | 69.3 | this sheet, BA on QDA confusion |
| screened 7-state alphabet (uniform) | c6 | 2.759 | 42.8 | this sheet, QDA MI |
| screened 7-state alphabet (BA capacity) | c6 | 2.759 | 42.8 | this sheet, BA on QDA confusion |
| screened 8-state {7+K} alphabet (uniform) | c4 | 2.074 | 72.3 | this sheet, QDA MI |
| screened 8-state {7+K} alphabet (BA capacity) | c4 | 2.210 | 77.1 | this sheet, BA on QDA confusion |
| screened binary composite CMY (sum, raw channels) | c3 | 1.252 | 77.6 | 002.0 composite BER -> 1-H2 (cross-sheet, derived) |
| screened binary composite CMY (sum, raw channels) | c4 | 1.897 | 66.1 | this sheet, v4 hard MI |
| screened binary composite CMY (sum, unmixed) | c4 | 1.929 | 67.3 | this sheet, rigid unmix decode |
| screened binary composite CMY (sum, raw channels) | c6 | 2.393 | 37.1 | this sheet, v4 hard MI |
| screened binary composite CMY (sum, unmixed) | c6 | 2.655 | 41.2 | this sheet, rigid unmix decode |

#### Caveats (facts, not editorializing)

- QDA MI values carry the cal_color interleaved-fold optimism bias (spatially adjacent cells in train and test); comparisons across cell sizes/fields share the bias, absolute values are upper-ish.
- Field-to-field spread on ONE sheet is large: the best-7 subset MI inside A2/state8k_c4 reads 2.208 vs the printed A1/state7_c4 field's 1.980 — same alphabet, same cell size, same sheet → ~±0.2 bits position/field variance at c4. The c3-vs-002.0 delta (−0.41) exceeds this scale but must be read against it; the c3 per-plane BERs (C 11.1 / M 14.7 / Y 27.0%) are uniformly worse than 002.0's composite c3 (8.8/11.8/24.0) — a real channel/position difference, not an analysis artifact (all warp locks 98–242/242, nulls pass).
- A2 {7+K} with the K-aligned grey density added as a 4th feature: MI 2.364 (acc 0.904) vs 2.074 on 3 features; the 3-feature BA capacity puts ZERO weight on K (best-7 2.208). K earns its 8th-symbol place only if the decoder measures a grey/K feature.
- BA capacity and best-subset numbers are computed ON the QDA confusion — they inherit that optimism and assume the confusion is the channel.
- Single sheet, single scan, day-1 numbers (printed+scanned 2026-07-04); no aging, no hygro cycle, one page position per config.
- Block B BER bar is CROSS-SHEET (002.1 P4 refs; this sheet has no c3 single-plane refs) — same scanner+day, but sheet-to-sheet variance is not separated. Solids anchors likewise cross-sheet.
- Y-plane numbers through the screened path remain crosstalk-inflated on the raw b channel and entangled with the pre-existing Y 224-lpi texture (002.1 finding 2); unmixed decode addresses the crosstalk part only.
- lpr -o raw transport (scratch-sheet precedent 002.0/002.1); port 9100 remains canonical for data sheets.
