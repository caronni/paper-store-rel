# Experiment 003 — modulation probes (protocol)

Goal: one A4 scratch sheet that measures, on the real M281 channel, the four
inputs the next modulation decision needs: (H1) whether the RIP's
contone/screening path triggers on REGION overlap of mask objects or only on
DOT overlap — i.e. whether dot-disjoint multi-plane imagemask content stays on
the bit-faithful clean path (002.1 P1 fields were screened even at non-knocked
dots; 002.2 reproduced it in Separation spaces; dot-disjoint emission is the
one untested corner); (H2) whether a sparse C subchannel placed in white voids
of a K field perturbs K development, and whether the C marks survive; (H3)
whether 2-D run-length-constrained K fields (dot-addressed, no cells) are
readable at 2 scan px/dot — the density upside over cell=3 if ISI, not
addressing, is the binding constraint; (H4) a motif survival library (micro
ink/white features with randomized surrounds) to seed trellis branch metrics
for a future 2-D-constrained decoder. Scratch sheet: fiducials allowed
(DESIGN.md R3 exempt). Exploratory w.r.t. DESIGN.md §4 — no amendment
proposed until measured.

## Hypotheses

- **H1 (screening trigger):** dot-disjoint multi-plane content stays clean.
  Discriminators (002.1 canary-A machinery): screen-family disk excess
  (165/212/224 lpi) on D1/D2/D5 at the D4/S1 clean bar vs the D3/D6
  screened controls; per-plane BER vs the D4 halves; knockout miss-rate
  split (vacuous at dot level by construction — any C/M loss at "overlap
  regions" is a region-level effect). D2 additionally separates
  object-count/complexity triggering from bbox-overlap triggering.
- **H2 (white-void C subchannel):** K BER on S2 == K BER on S1 (identical K
  field, same sheet; gate: |ΔBER| within same-sheet position variance, no
  systematic K miss increase near marks), C-mark recovery rate from GT
  positions, screening bar on S2/S3 vs S1. S3 = colored-pilot demo at
  pilot_sites density (2.44% of cells).
- **H3 (constrained fields at the dot grid):** per-field raw BER/MI at
  1200 dpi scan (2 px/dot) with a matched-filter/threshold per-dot decode
  and with a 3x3-context soft decode; compare information per areal dot:
  K1/K2/K3 sampler entropy × (1 − H2(BER)) style bounds vs the same-sheet
  c2/c3 incumbents (K4, 0.85–0.88 bits/cell ÷ 9 dots at c3 from 002).
  Death is a datum: if 200-dpi-scale features in K2 (white>=2) close up
  (001: min white ~3), the K2-vs-K1 delta measures exactly that.
- **H4 (motif library):** per-motif survival/response statistics (detection
  rate, area/flux response, centroid bias) from >=120 instances each, ink
  motifs 2x2/2x3/3x2/2x4/4x2/L/T and white holes 2x2/2x3/3x3/1x3/3x1 in
  4-dot ink pads → branch metrics for a trellis/context equalizer.

## Artifacts (regenerate byte-identically; sha256 gates reuse)

- `003-modulation-probes/gen_modprobe.py` → `build/modprobe.ps` (4.06 MB),
  `build/modprobe_manifest.json`, `build/modprobe_gt/*.npy` (41 files).
  SEED `paper-store/exp003-modprobe`, LAY=1, jobid `75004840`.
  - `modprobe.ps` sha256 `95d7f593137596837d599df5422b92590e440e895456a9fd4e758fbd7a51f304`
  - `modprobe_manifest.json` sha256 `c7fcdb6e0413db26eb6bb823a03212624f6156b4ac1d5b4da243e2d1ce96c445`
- Registration: EXACT calpage chiral corner marks + plus lattice (58 marks);
  cal_core registers by manifest swap. 100 patch entries.
- Preflight (gates the print): `env/bin/pytest -q tests/test_modprobe.py` —
  determinism ×2, exact 2-D run-length verification, S2/S3 void+clearance
  checks, D-group content identity, geometry/labels/stream order, gs pnggray
  GT crops + tiffsep separations (all pixel-exact, incl. the 13,225 D2
  per-cell masks), byte-identity pins for gridtest/calpage/composite_probe/
  overlap2.

## Page inventory (mm, top-left origin)

| block | x | y | content |
|---|---|---|---|
| header | 16 | 6.5–14 | title 7 pt + regen/scan line 5 pt |
| corner marks | (10,10) (200,10) (200,288) (10,288) | | chiral 1/2/3/4 satellites, calpage-identical |
| K1 K2 K3 | 14 / 40 / 66 | 20 | 2-D RLL K fields 22×22, ink>=2 & white>=3 / 2 / 4 (both axes, border runs included) |
| K4 | 92 / 110 | 20 | encode c2, c3 incumbents 14×14 (gen_gridtest construction, exp-003 seed) |
| quiet zone | 132 | 20 | 20×20 blank (white ref + spectra noise floor) |
| D1 D2 D3 | 14 / 36 / 58 | 52 | SAME {W,C,M} c3 field 18×18: whole-field mask pair / 13,225 per-cell masks (2.46 MB PS) / cmyk-image control |
| D4 | 80 + 89.9 | 52 | C-only left / M-only right halves of the same state field, disjoint rects, 1 mm gap |
| D5 D6 | 104 / 128 | 52 | SAME {W,C,M,Y,K} c3 field 20×20: 4 dot-disjoint whole-field masks / cmyk-image control |
| M motifs | 14–98.5 (6 cols) | 80 + 95 | 12 patches 12×12: 132 instances each, 20-dot lattice ±1 jitter, 50% c3 background, 4-dot clearance; white motifs in 4-dot solid pads |
| S1 S2 S3 | 110 / 134 / 158 | 80 | i2w3 field 20×20 bare / IDENTICAL field + 557 C 2×2 marks in 4×4-white voids (of 1114 eligible, seeded 50%) / 50% c3 field + 601 C pilots in 4×4-dot voids at interior pilot_sites |
| END sentinel | 18–60 | 286.5 | 2.5 mm K square + `END 75004840` — LAST element in stream |

Stream order: labels → ALL single-plane imagemask content → put_cmyk_bitmap
controls (D3, D6) → END sentinel. No Separation/DeviceN (002.2 closed that).

## Constrained-sampler entropy (measured at generation, in the manifest)

Row-by-row sampler, each row uniform (completion-counting DP) given the
vertical run forcing; NOT the 2-D maxentropic measure, so delivered entropy is
measured, not assumed. `sampler` = exact Σ log2(#row completions)/dots;
`ctx` = 4-neighbor causal context-model estimate (upper-bound-ish: 4 neighbors
under-capture the constraint memory). Theory ballpark for these 2-D
constraints ~0.4–0.55 bits/dot; 1-D (2,∞)×(3,∞) capacity is 0.611.

| field | constraint | sampler b/dot | ctx b/dot | ink frac | vs c3 incumbent (b/areal-dot) |
|---|---|---|---|---|---|
| K1 | ink>=2 white>=3 | 0.3501 | 0.6634 | 0.415 | c3 K = 0.85/9 = 0.094 |
| K2 | ink>=2 white>=2 | 0.4450 | 0.7755 | 0.499 | — |
| K3 | ink>=2 white>=4 | 0.2950 | 0.5765 | 0.358 | — |
| S1/S2 | ink>=2 white>=3 | 0.3501 | 0.6582 | 0.415 | — |

Even at 50% raw BER-equivalent losses, K1's 0.35 b/dot is ~2–4× the c3
incumbent's areal rate — IF the fields decode at 2 px/dot (H3, the question).

## Physical run protocol (hardware rules apply — ask user first)

1. Preflight green (`pytest -q`, 47 tests), sha256 of modprobe.ps matches the
   value above (regenerate to check; sha gates reuse).
2. USER prints ONE sheet, raw path only: `lpr -o raw build/modprobe.ps` or
   `../../scripts/print_plane.sh build/modprobe.ps` (port 9100). No driver
   color management. Loupe-check before scanning: K1/K2/K3 texture visibly
   coarser than e2/e3; C marks visible inside S2/S3 white voids; D1 vs D3
   comparison by eye (screening shows as regular texture).
3. Scan: flatbed 1200 dpi RGB, sheet FLAT at 0° (no rotation), descreen /
   sharpen / auto-contrast OFF, full page including all four corner marks.
   Save to `scans/`, record filename + sha256 here.
4. Log the run below: date, engine, media, driver path, settings, scan
   sha256. One variable at a time — this sheet is one print, one scan.

## Analysis plan (analyzer to be written against the manifest)

- Register via cal_core manifest swap (4 corners + 58 plus marks).
- H1: canary-A spectra per D patch/channel; clean bar from D4 + S1 + quiet
  zone; BER D1/D2/D5 vs D4 halves; verdict per the 002.1 decision rule.
- H2: K BER S2 vs S1 (same field!); per-mark C detection (blue/red channel
  contrast at GT positions vs 557 shifted-control positions); K miss rate
  within 2 dots of marks vs far field.
- H3: per-dot decode of K1/K2/K3 at 2 px/dot (hard threshold + 3×3 context
  model); report per-constraint BER, MI, and net b/areal-dot vs K4 e2/e3
  decoded with scanlab v4.
- H4: per-motif detection/flux/centroid tables with bootstrap CIs; publish
  as `build/motif_library.json` for the trellis work.

## RESULTS

### Run 003.0 — modulation probe sheet (2026-07-04, print done, scan pending)

| field | value |
|---|---|
| sheet | `build/modprobe.ps`, sha256 `95d7f593137596837d599df5422b92590e440e895456a9fd4e758fbd7a51f304`, jobid `75004840`, seed `paper-store/exp003-modprobe`, manifest `c7fcdb6e...ce96c445` |
| printed | 2026-07-04 21:01, `lpr -o raw` (queue HP_Color_LaserJet_MFP_M281fdw__<host>_, job -88) — printed by Claude with explicit one-page user authorization |
| media | same 90 g/m² ECF office stock as 002.x |
| preflight | 47/47 tests; constraints assert-verified both axes; all four prior-sheet pins intact; gs pnggray + tiffsep pixel-exact incl. all 13,225 D2 per-cell masks |
| contents | K: RLL fields i2w3/i2w2/i2w4 + c2/c3 incumbents; M: 12 motifs x 132 instances; D: dot-disjoint emission probes D1-D6 (H1 screening trigger); S: white-void C subchannel A/B (557 marks) + colored-pilot demo (601 pilots) |
| sampler entropy | i2w3 0.3501 b/dot, i2w2 0.4450, i2w4 0.2950 (exact row-completion count; ctx-model upper estimates 0.58-0.78) |
| scan | `scans/test-scan-modprobe.png`, RGBA 1200 dpi, sha256 `a5de3fe82e2dc2baf89557bf2fa74c906ab094773c6a361fd29877773049e963` |

#### H1 — screening trigger on dot-disjoint multi-plane emission (THE headline)

**screening trigger = REGION-overlap: D1 screened, D2 (13,225 objects) screened, D5 (4-plane) screened; D3/D6 cmyk controls screened (positive control good)**

Screen-family disk excess (dB; hit bar = max(12, GT floor+6), strong bar 18 — 002.1 gates verbatim). Same-sheet clean bar (D4 + K4 + S1): none (clean); cross-sheet b bar (002.1 Y-plane texture): 165·b, 224·b.

| emission | patch | ch | 165 lpi | 212 lpi | 224 lpi | beyond bar |
|---|---|---|---|---|---|---|
| D1 | D1_C | r | 22.9 (9.7) | 8.5 (10.0) | 11.3 (14.6) | 165·g, 165·r |
| D1 | D1_M | g | 21.7 (10.2) | 10.6 (11.3) | 10.4 (10.2) | 165·g, 165·r |
| D2 | D2_C | r | 23.5 (9.7) | 10.3 (10.0) | 12.8 (14.6) | 165·r |
| D2 | D2_M | g | 17.7 (10.2) | 10.0 (11.3) | 12.8 (10.2) | 165·r |
| D3 | D3_C | r | 22.7 (9.7) | 8.4 (10.0) | 13.1 (14.6) | 165·g, 165·r |
| D3 | D3_M | g | 21.9 (10.2) | 9.3 (11.3) | 8.5 (10.2) | 165·g, 165·r |
| D4 | D4_C | r | 7.6 (10.0) | 8.9 (10.1) | 11.1 (5.2) | — |
| D4 | D4_M | g | 8.0 (11.4) | 11.5 (11.9) | 10.0 (7.1) | — |
| D5 | D5_C | r | 16.2 (7.8) | 19.4 (8.2) | 14.2 (9.5) | 165·g, 212·b, 212·g, 212·grey, 212·r |
| D5 | D5_M | g | 20.6 (9.8) | 22.2 (10.0) | 16.0 (9.1) | 165·g, 212·b, 212·g, 212·grey, 212·r |
| D5 | D5_Y | b | 13.0 (9.2) | 19.9 (9.5) | 14.0 (9.1) | 165·g, 212·b, 212·g, 212·grey, 212·r |
| D5 | D5_K | grey | 17.8 (10.6) | 21.7 (10.6) | 15.8 (9.9) | 165·g, 212·b, 212·g, 212·grey, 212·r |
| D6 | D6_C | r | 16.8 (7.8) | 21.4 (8.2) | 14.3 (9.5) | 165·g, 165·grey, 212·b, 212·g, 212·grey, 212·r |
| D6 | D6_M | g | 22.6 (9.8) | 22.0 (10.0) | 15.0 (9.1) | 165·g, 165·grey, 212·b, 212·g, 212·grey, 212·r |
| D6 | D6_Y | b | 15.2 (9.2) | 21.4 (9.5) | 13.7 (9.1) | 165·g, 165·grey, 212·b, 212·g, 212·grey, 212·r |
| D6 | D6_K | grey | 19.6 (10.6) | 22.7 (10.6) | 15.7 (9.9) | 165·g, 165·grey, 212·b, 212·g, 212·grey, 212·r |

(family excess with each patch's own GT-spectrum floor in parens; all three family points verified off the c3 cell lattice, so no 002.2-style aliasing at c3.)

Per-plane BER, fixed-rate threshold at the construction prior (1/3 for CM fields, 1/5 for 5-state), GT-aware nulls:

| patch | ch | BER | Δ vs D4 half | miss/fa split note | null (exp) |
|---|---|---|---|---|---|
| D4_C | r | 0.0169 | — | single-plane ref | 0.449 (0.449) |
| D4_M | g | 0.0088 | — | single-plane ref | 0.455 (0.453) |
| D1_C | r | 0.0251 | +0.0082 | fa@other-ink 0.024 vs white 0.011 | 0.448 (0.450) |
| D2_C | r | 0.0254 | +0.0084 | fa@other-ink 0.024 vs white 0.010 | 0.449 (0.450) |
| D3_C | r | 0.0226 | +0.0057 | fa@other-ink 0.021 vs white 0.010 | 0.449 (0.450) |
| D5_C | r | 0.1231 | +0.1062 | fa@other-ink 0.100 vs white 0.004 | 0.321 (0.321) |
| D6_C | r | 0.1256 | +0.1086 | fa@other-ink 0.103 vs white 0.001 | 0.322 (0.321) |
| D1_M | g | 0.0534 | +0.0446 | fa@other-ink 0.082 vs white 0.003 | 0.446 (0.447) |
| D2_M | g | 0.0459 | +0.0371 | fa@other-ink 0.073 vs white 0.002 | 0.448 (0.447) |
| D3_M | g | 0.0377 | +0.0289 | fa@other-ink 0.061 vs white 0.001 | 0.449 (0.447) |
| D5_M | g | 0.1218 | +0.1131 | fa@other-ink 0.098 vs white 0.011 | 0.323 (0.321) |
| D6_M | g | 0.1316 | +0.1229 | fa@other-ink 0.107 vs white 0.010 | 0.320 (0.321) |
| D5_Y | b | 0.2481 | — | fa@other-ink 0.186 vs white 0.058 | 0.322 (0.326) |
| D6_Y | b | 0.2497 | — | fa@other-ink 0.193 vs white 0.039 | 0.322 (0.326) |
| D5_K | grey | 0.0818 | — | fa@other-ink 0.068 vs white 0.003 | 0.320 (0.319) |
| D6_K | grey | 0.0765 | — | fa@other-ink 0.064 vs white 0.002 | 0.321 (0.319) |

5-state QDA head-to-head (W,C,M,Y,K at c3; features = per-plane-aligned densities D_r/D_g/D_b [+ D_grey K-aligned]):

| field | acc (4-feat) | MI 3-feat | MI 4-feat | BA cap | best-4 subset | null ok |
|---|---|---|---|---|---|---|
| D5 | 0.886 | 1.321 | 1.677 | 1.695 | 1.601 {C,M,Y,K} | True |
| D6 | 0.901 | 1.368 | 1.737 | 1.751 | 1.638 {C,M,Y,K} | True |

Leaderboard: D5 (dot-disjoint masks) MI4 1.677 vs D6 (cmyk) 1.737 vs 002.2 screened c3 printed-7-state 1.479 / best-5-subset 1.372 → D5 clean AND beats screened c3: **False**.

#### H2 — white-void C subchannel

- K dot-BER S1 0.1276 vs S2 0.1404 (Δ +0.0128; position-variance scale 0.0031 → within variance: False); discordant dots S1-only 11628 vs S2-only 14478 of 222784.
- K miss near marks (Chebyshev ≤2): S2 0.2521 vs far 0.1644; S1 control at the SAME sites 0.2670 vs 0.1473. Mechanism reading: the near-mark delta is -0.0149 (S2 not worse at marks) while the FAR-field delta is +0.0172 and the b-channel (C-blind) shows the same global shift — so NO local development coupling at marks; the global Δ is a position/field effect, not a C effect (single replicate — needs a repeat to close). Note void-adjacent K ink misses at ~25–27% in BOTH fields vs ~15% far-field: enforced white voids cost their K neighbors dearly (001 anisotropy), C presence irrelevant.
- C-mark recovery 556/557 (99.8%) at s = D_r − max(D_g,D_b) > 0.034 (S1-null median + 4σ); FP on S1 same-coords 0.0000, shifted-coords null 0.0898; min signal − thr = -0.005.
- K-channel blindness: S2 K dot-BER grey 0.1404 vs b-channel 0.1416 (S1 b control 0.1301).
- Screening S2 − S1 family delta (dB): grey 165 -0.7 212 -0.8 224 +0.2; r 165 -0.1 212 -0.8 224 +1.3.
- S3 pilots: 601/601 recovered at the S2 threshold; K data-cell BER 0.0289 (pilot-margin cells 0.0744, clear 0.0266) vs same-sheet K4/encode_c3 0.0253; chroma d' pilot-vs-white 4.7, pilot-vs-ink 3.1, min margin -0.589 (negative: the 601-pilot minimum sits below the max of ~24k data cells; blind per-cell FP at the S2 threshold: K-ink cells 0.265, white 0.024 — pilot detection must stay site-gated, not free-running).

#### H3 — 2-D RLL constrained K fields at the dot grid

| field | constraint | sampler b/dot | dot BER | miss / fa | MI hard b/dot | rate proxy b/dot | b/mm² | null (exp) |
|---|---|---|---|---|---|---|---|---|
| K1 | i2w3 | 0.3501 | 0.1306 | 0.157 / 0.112 | 0.423 | 0.154 | 86 | 0.444 (0.435) |
| K2 | i2w2 | 0.4450 | 0.1804 | 0.181 / 0.180 | 0.319 | 0.142 | 79 | 0.503 (0.505) |
| K3 | i2w4 | 0.2950 | 0.1142 | 0.160 / 0.089 | 0.436 | 0.144 | 80 | 0.407 (0.407) |
| K4/encode_c2 | c2 solid cells | 1/cell | 0.1110 (cell) | — | 0.497/cell | 0.124 | 69 | 0.501 (0.500) |
| K4/encode_c3 | c3 solid cells | 1/cell | 0.0253 (cell) | — | 0.830/cell | 0.092 | 51 | 0.506 (0.500) |

Run survival (fraction of GT maximal runs decoded fully intact, both axes; the '2-runs and 3-runs die where?' table):

| field | ink L=2 | ink 3 | ink 4 | ink ≥7 | white 2 | white 3 | white 4 | white ≥7 |
|---|---|---|---|---|---|---|---|---|
| K1 | 0.62 | 0.63 | 0.56 | 0.54 | — | 0.64 | 0.61 | 0.53 |
| K2 | 0.56 | 0.57 | 0.54 | 0.51 | 0.54 | 0.60 | 0.59 | 0.57 |
| K3 | 0.62 | 0.63 | 0.57 | 0.50 | — | — | 0.66 | 0.51 |

Rate-proxy caveat (honest): dot errors are ISI-correlated (run survival above), so sampler_entropy × (1 − H2(BER)) is an ESTIMATE pending trellis/context detection (M2), not a measured capacity.

#### H4 — motif survival library (→ `build/motif_library.json`)

detect = flux above the context-null (erased/filled level in the 4-dot band below the feature) + 4 robust σ — same rule as the H2 C-mark detector; survive = flux_norm ≥ 0.5 (development strength).

| motif | kind | area | detect | survive | flux mean±σ | centroid (dy,dx) | ctx-null flux |
|---|---|---|---|---|---|---|---|
| ink_2x2 | ink | 4 | 1.000 | 0.220 | 0.457±0.052 | (-0.11,-0.08) | 0.151 |
| ink_2x3 | ink | 6 | 1.000 | 0.545 | 0.497±0.059 | (-0.13,-0.14) | 0.150 |
| ink_3x2 | ink | 6 | 1.000 | 0.705 | 0.527±0.057 | (-0.20,-0.08) | 0.155 |
| ink_domino_h | ink | 8 | 1.000 | 0.712 | 0.531±0.062 | (-0.16,-0.15) | 0.139 |
| ink_domino_v | ink | 8 | 1.000 | 0.947 | 0.574±0.045 | (-0.21,-0.12) | 0.181 |
| ink_l_tromino | ink | 12 | 1.000 | 1.000 | 0.603±0.045 | (-0.32,-0.05) | 0.192 |
| ink_t_tetromino | ink | 16 | 1.000 | 0.985 | 0.650±0.059 | (+0.04,-0.14) | 0.159 |
| white_2x2 | white_hole | 4 | 0.023 | 0.000 | 0.135±0.033 | (-0.15,-0.13) | 0.082 |
| white_2x3 | white_hole | 6 | 0.485 | 0.000 | 0.221±0.047 | (-0.19,-0.11) | 0.086 |
| white_3x3 | white_hole | 9 | 0.970 | 0.000 | 0.330±0.050 | (-0.29,-0.19) | 0.078 |
| white_slot_h | white_hole | 3 | 0.212 | 0.000 | 0.101±0.033 | (-0.17,-0.11) | 0.039 |
| white_slot_v | white_hole | 3 | 0.167 | 0.000 | 0.118±0.041 | (-0.36,-0.13) | 0.069 |

#### Caveats (facts, not editorializing)

- Fixed-rate detector: decoded ink fraction is pinned at the construction prior per patch — BERs are rank-threshold BERs; a blind-threshold decoder would need the prior from elsewhere (it has it: the constraint/alphabet is a design constant).
- Null controls for structured/asymmetric fields are judged against the GT-derived expected level (RLL autocorrelation at shift 8, 2p(1−p) for 1/3- and 1/5-ink planes), not the flat 0.50 of 001/002.
- No same-sheet single-plane Y or K-in-color-field screening reference: the b-channel bar is CROSS-SHEET (002.1 P4 {165|b, 224|b}); D5/D6 Y-plane spectra are judged against it.
- QDA MI carries the cal_color interleaved-fold optimism bias; D5-vs-D6 and vs-002.2 comparisons share the bias (like-for-like).
- H3 rate proxies assume BSC error scaling; ISI correlation is measured and reported but not modeled. Trellis detection (M2) is the follow-up.
- Single sheet, single scan, one page position per config; same-sheet position variance visible as K1-vs-S1 BER spread (0.0031).
- S3 pilot-void margins eat the left column/top row of right/below-neighbor cells; their BER is reported split (margin vs clear) rather than corrected.
- Quiet-zone off-lattice max reads 22/21/21 dB (r/g/b) from banding-type lines at ~(0, ±0.13) and (±0.75, 0) cyc/dot — NOT at screen-family points (family disks in the quiet zone read 8–10 dB = chance), so family verdicts are unaffected.
- The S2 shifted-coordinate mark null trips at 9.0%: shifted windows can land on OTHER marks (557 marks pepper the field) — the clean no-C null is FP@S1 same-coords (0.0000).
- H4 context nulls sit 1–2 dots from the feature and the pad/clear edge (the context band is only 4 dots) — they carry residual PSF spill; small-motif flux distributions are UNIMODAL (see library percentiles): weak development, not stochastic death, so 'survive' is a threshold statement, 'detect' the presence statement.

---

## 003.0a — B1 (c2-K + 16-context) reanalysis of K4/encode_c2 (2026-07-05, zero-paper)

Analyzer: `analyze_k4e2_context.py` -> `build/k4e2_context_report.json`. Same
scan as 003.0 (`test-scan-modprobe.png`, 1200 dpi COLOR, sha a5de3fe8...),
registration affine reused from `modprobe_report.json`; v4 `decode_cells`
(genie-warp, soft stage on). Motivation: the M2 four-cell matrix amendment —
c2-context (B1) was measured only on the 001.4 gridtest pair and never at an
independent sheet position; its LLRs were known-miscalibrated (tails ~150x).
New here: monotone (PAVA) LLR recalibration, split-half within-patch
(checkerboard cell split, leakage-free) and CROSS-SHEET (mapping fitted on the
001.4 `reliability_ctx` deciles, applied unmodified).

| metric | value | reference |
|---|---|---|
| hard BER (v4 median) | 0.1109 | 003.0 report 0.1110; 001.4 0.1116-0.1141 — REPLICATES |
| 16-context BER | **0.0459** | 001.4 grey-scan 0.0496-0.0541; this is a COLOR scan (expected penalty did not materialize) |
| BSC proxy from ctx BER | 0.731 b/cell = **102.0 b/mm2** | pre-registered success bar was >=90 |
| MI ctx raw (uncalibrated) | 0.467 b/cell = 65.2 b/mm2 | 001.4-class miscalibration confirmed |
| MI ctx recal, split-half | **0.785 b/cell = 109.4 b/mm2** | leakage-free within-patch |
| MI ctx recal, cross-sheet | 0.775-0.778 b/cell = 108.1-108.5 b/mm2 | fitted on 001.4 tables only — recal TRANSFERS across sheets/days |
| null (GT shifted 7 rows) | 0.493 | ok |

Reading: B1 confirms at the independent position with NO position haircut at
c2 (contrast c3's 2.1->3.74% best->conservative spread), and the monotone
recalibration closes the LLR gap: recalibrated soft MI EXCEEDS the BSC hard
proxy (0.785 > 0.731, as soft should) and the mapping fitted on a different
sheet/day reproduces the split-half value within 0.01 b/cell. **B1 now leads
the measured board: ~102-109 b/mm2, clean carbon-black path, existing
detector** (A-c3 91.7 QDA-fold-optimistic; B2-naive 86). Caveats: still
genie-warp (blind sync remains M1's burden); single patch (27,225 cells);
recalibrated LLRs not yet pushed through an LDPC (M2).
