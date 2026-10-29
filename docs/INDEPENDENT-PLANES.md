# Independent colour planes — state of understanding and staged work

Version 0.6 — 2026-09-04. Status: SYNTHESIS + STAGING, code-agnostic.
(v0.6: §H's per-plane-rung item points at the 2026-09-04 column-group
pool, docs/CMY8-COLUMN-GROUPS.md — the width-class block is ruled and
built for src/holo generation + holo3; the lever row is not printed.)
(v0.5: §2.13 adds E9, the K instance of local-vs-page-global calibration
— 0 certificates on the complete e029 residue at two lanes, page-global
the best arm, and the shipped per-window threshold measured as noise
about a page-global one. `measure/calibration/`.)
(v0.4: §2.9b supersedes §2.9's framing — the probe pass's REACH was the
label-only predicate, not the template width; §4.G and §6/P2b amended.)
(v0.3: §2.8 records P1 + P2 as executed on branch independent-planes;
§3, §4.E/§4.I and §6 amended from those measurements.)
(v0.2: completeness pass against the recapitulating discussion — added
the swim's failing-plane-only scope, the dust verdict update, the
neighbour-estimator attenuation caveat, the review's C-target
correction, run 2's footing vs §033.6, the scope caveat on "capped",
plane-aware addressing as an avenue, adoption granularity, a
dispositions list, the no-bolt-on rule, and build discipline for P5.)
Governing line doc for what was built: docs/PLANE-FIELDS.md (v0.13); this
document records what the 2026-08-21/22 measurement campaign taught, what
it falsified, and what the work is now, in priority order. Nothing here
is built; every measurement cited was recomputed by an independent
adversarial review (§2.6) unless marked *estimate* or *inferred*.

Sources of record: experiments/033 (§033.4 the Y sinusoid), PLANE-FIELDS
§6 (V0/W6), scratch/plane-fields/{swim-pilot,gt-affine}/ (artifacts),
measure/plane_fields/README.md (instruments + their confirmed caveats),
the 2026-08-22 review workflow journal (14 agents, 10 verifications, 0
refuted).

---

## 1. The problem in one paragraph

cmy8 prints three planes on the same 2-dot cells. The receiver poses a
*window* once and samples all three planes through that pose. On the
AltaLink, the Y plane's x-registration wanders as a ~100 mm-period
sinusoid (0.83 dot peak) while C/M stay near the word-fitted pose, so in
the sinusoid's extremes Y is sampled 0.6–0.75 dot off its ink — the
"dead bands" of sheet I. PLANE-FIELDS built a per-plane registration
field to correct that. It recovered +252 (3 captures) and later +90
(4th capture) certificates and closed byte-exact, but the dead bands did
not fill. This document is about why, and what follows.

---

## 2. What we measured

### 2.1 The registration itself (e033, V0)
- Sheet I Y-plane x-offset: sinusoid, 0.83 dot peak, ~100 mm period,
  Spearman +0.80 against the certificate residue; toner mass,
  modulation, PSD uniform ⇒ detector-frozen, not ink-frozen.
- V0: a blind field from certificates + committed poses reproduced the
  supervised sinusoid (Spearman +0.997, period 100.2 mm, amplitude
  0.935). The field CAN see the displacement where it has evidence.

### 2.2 The field in production (W6, live runs)
- W6 (3×2400 dpi, dial ON): pre-registered bar FAILED — dead-band
  median Y residue 24/53 vs ≤5/53 — but +252 certificates (5549; Y
  1444→1629), page residue 517→332, C residue 66→2, close byte-exact.
  Bands 1+2 collapsed; band 3 got WORSE (108→127) under all-or-nothing
  per-page adoption; column 8 (zero Y evidence) 53→46 = extrapolation
  limit.
- Live run 1 (single 2400 capture, stock `--refine`): 5164 certs; uF
  adopted C,M only — Y refused (§6.5.4a/b: the shrinkage target).
- Live run 2 (+4800 capture, 4 captures): 5639/5883 slots = 244 open;
  `u03-field-16ppc-4800dpi` adopted C,M,**Y** — first Y adoption — Y rms
  0.441 dot (0.32 when refused); coverage 99.6%; 256 probe sites / 768
  probes; canary 37.8% (unexplained). **Bands persist by eye.**
  Confounded: 16 px/cell footing AND a 5164-certificate prior state
  changed together. NOT the fresh, dial-off 4800 mechanism run that
  e033 §033.6 registered ("bands persist") — the capture joined a
  field-enabled multi-capture state; §033.6 is corroborated, not
  formally scored.

### 2.3 The swim pilot (measure/plane_fields/swim_pilot.py)
10 residue (tile, plane) targets (6 dead-band Y, 3 clear Y, 1 C) + 2
*reproduction controls* (certified tiles with only their Y certificate
withheld, so they present exactly as residue tiles).
- Controls: fail at δ=0, CERTIFY under per-plane translation; certified
  band 3 grid steps = 0.25 dot wide; real certificate ids, CRC good.
- Residue: 0/10 certify at ANY of 85 candidate offsets (17 in x, 68 in
  x,y) — under neighbour-derived, own-furniture, or swim estimates.
  SCOPE: only the FAILING plane was swum (its siblings were already
  certified and conditioning); a joint three-plane wiggle was never
  run. For Y the oracle is payload LDPC+CRC alone (words are Y-white,
  so Y cannot self-address); C/M per-channel word decode was not
  exercised.
- Ground truth (cells re-derived from the closed payload, validated
  cell-exact on 24 certified tiles): the decode gate is a knife edge at
  ~7.6% cell error and NOT a pure BER threshold — worst certified
  7.67%, best failed 7.57% (they overlap). Translation takes the dead
  band from 17.5% → 10.8%; still 1.3–1.8× above the gate.
- Estimators vs the BER-optimal offset: neighbour-interpolated ratio
  0.93 (mean error 0.12 dot); supervised regmap-gt 1.47; own-furniture
  (Y = ~14 dust cells) 2.33. All three reproduce the sinusoid
  (Spearman +0.97 / — / +0.82). CAVEATS (review): a ratio just under 1
  is what an ATTENUATING interpolator predicts (inverse-distance over
  ~32 mm of a ~100 mm-period field), not proof of unbiasedness, and the
  per-tile SE is ~0.15 dot against a 0.25–0.73 dot signal; the
  own-furniture CONTROL rows were contaminated (the withheld certificate
  leaked a full-tile template), the target rows stand.
- DUST VERDICT UPDATED (vs PLANE-FIELDS beat 18 "demoted, not
  deleted"): Y dust is NOT noise — it carries the sinusoid at ρ +0.82
  — but overstates magnitude ~2.3× and lands outside the 0.25-dot
  acceptance band on both controls. A hint, never a correction.
- All DIRECT-NCC estimators (dust, regmap-gt) overshoot: NCC measures
  where the ink physically landed; the decoder's optimum is smaller
  because the detector's calibration absorbs part of the displacement
  (*inferred*) — a field trained on NCC anchors will over-correct
  (candidate band-3 harm mechanism; §8).
- Cost: ~100 s setup per capture, ~0.8 s per candidate; a hint-seeded
  1-D closer ≈ 4 s/tile ⇒ ~20 min for a whole sheet.

### 2.4 The supervised ceiling (measure/plane_fields/gt_affine.py)
Per (tile, plane, capture), a full 2-D affine (translation + 2×2
Jacobian) fitted AGAINST the true printed cells — the ceiling on any
registration-based correction.
- Dof ladder, dead band (6 tiles), mean Y cell error:
  δ=0 17.47% → swim 1-D 10.84% → 2-dof fit 10.75% → 6-dof affine
  10.30% → + BER-direct polish **9.70%**. Translation is ~95% of what
  geometry buys. Zero dead-band tiles certified at any geometry; the
  best misses the gate by ~0.7 pp.
- All targets 14.99 → 10.24 → 9.66 → 8.99 → 8.34%. Four tiles certified
  under the ceiling, incl. page-corner (0,0)/C 11.95% → 4.97%, the only
  certificate the Jacobian dof won (where the shared window pose
  extrapolates worst).
- **The Jacobian is plane-COMMON.** Y's scale_y deviates from the C/M
  mean with sd 0.024% against a 0.274% common term (×11); rotation and
  shear never exceed 0.07°. Only TRANSLATION has a per-plane part as
  large as the shared part (0.307 vs 0.260 dot). Opening the Jacobian
  does not move the translation (r = 0.9988).
- Separation at the fitted pose (Y): d′ dead 1.81, controls 1.82,
  certified clean-column reference 1.88 ± 0.08; C 3.3–3.5, M ~3.0 on the
  same pixels. Oracle-threshold Y error 16–18% EVERYWHERE on the sheet.
  Production detector: 11.4% (dead) vs 8.2% (controls); per-stratum
  oracle 13.2% vs 12.3%. Review correction: the reported CLEAR-band
  group mixed in the one C-plane target; Y-only, clear-band d′ is 1.85
  and detector error 8.68% — the clear-vs-dead separation gap was that
  single row.
- **Status of the ceiling: an UPPER BOUND.** The review confirmed three
  confounds: the fit optimizes partial NCC, not BER (a 2-dof BER polish
  beat the 6-dof NCC optimum by 0.6 pp; no 6-dof BER search was run);
  the detector's context bins were cut at δ=0 — where dead tiles are
  11–22% wrong and controls ~8% — and reused at every candidate, so the
  staleness is correlated with the very grouping compared; the refit
  spot-check was ranked onto the certified controls only, and was a
  no-op on A0-arm captures. The "detector-created ~2.3 pp" reading is
  therefore a HYPOTHESIS, additionally weakened by outcome-selected
  groups and n = 2 control tiles.
- **Scope of every "capped" statement:** six dead-band tiles, one lane
  (8 px/cell), one sheet (I, r0700), one engine state (AltaLink,
  2026-08-05/06 toner). Sheet H (r0850) and other engines may sit
  elsewhere on the same curve; §7 is the first out-of-sample test.

### 2.5 Dead cells vs ground truth (the figure)
- Yellow ink is PRESENT and PLACED: a fit-free pixel-domain
  cross-correlation of the raw blue channel against the truth map peaks
  at −0.566…−0.574 on all four tiles (control included), at +3 px
  (+0.75 dot) on the two dead tiles — independently confirming the
  fitted offsets and the sinusoid.
- Y is OPTICALLY SOFT sheet-wide: structure smears ~2–3 cells; peak
  |r| C 0.771, M ~0.72, Y 0.57. A plane property, not a band property.
- Dead rows and the certified control are visually indistinguishable
  in pixels, sampled values and class histograms; the control's ORACLE
  error (17.8%) is worse than two dead tiles' (16.1, 16.4%) — and it
  certifies. No halftone grid (no plane-overlap re-screen, as e031).
- Same pixels, tile (14,9): C reads at 0.28% error, d′ 4.07; Y at ~10%.

### 2.6 The adversarial review (2026-08-22)
- Every reported number reproduced from the artifacts (one rounding:
  0.84 pp, not 0.9). Units, frames, rot_k: correct.
- Mechanism READ from the detector code: Y's cross-plane context is an
  isotropic 0–8 neighbour ink COUNT (own cell excluded); same-cell
  crosstalk lives only in the 8-state QDA means, evaluated on three
  samples taken at DIFFERENT per-plane positions; the sampling aperture
  is 0.7 cell = 1.4 dots, so a 0.5–1.0 dot relative displacement slides
  it 36–71% of its width toward one neighbour — the leakage becomes
  anisotropic and neighbour-sourced, which neither term can express.
  Correcting geometry refreshes the numbers, not the model class. PAVA
  is one monotone map of the marginal LLR, so a context-conditional bias
  survives calibration: the signature "identical marginal d′, fewer
  certificates". Y's own context column is derived from Y's provisional
  decisions — circular exactly in the dead bands.
- Confirmed production defects: the cross-plane shrinkage target
  (C/M antisymmetry cancels in the signed pooled mean ⇒ Y shrunk toward
  ~Y/3 when its evidence is thin); an uncovered plane inherits the other
  planes' field as its own; `done_tiles` only marks tiles in
  certified-complete windows (budget-0 ⇒ all black); the live status-row
  F fold never renders (same bug class as the fixed FieldStats); a
  shell test asserts the removed aspect-ratio and passes on a comment;
  band arrows capped on an anisotropic grid; no legend.
- Confirmed instrument caveats: recorded in measure/plane_fields/README.


### 2.8 P1 + P2 executed (2026-08-22, branch `independent-planes`)

**P1 — confirmed defects fixed** (suite 1396 passed / 46 skipped; policy
id bumped to `…planefield-zeroshrink-allprobes`; dial-off byte-identical):
- Shrinkage law: each plane an independent posterior about the NATURAL
  ZERO; no cross-plane term; uncovered plane = zero. Measured on sheet
  I's 1,869 certified-tile probe rows while thinning Y's evidence —
  Y rms GROWS under the new law exactly where the old one shrank it
  (1/10 evidence 0.28 → 0.37 dot; 1/40 0.27 → 0.45), **Y adoption flips
  on** at the thin densities where live run 1 refused it, M flips too
  (its median sat at 0.2487, a hair under the 0.25 cliff); the field's
  column profile vs the sinusoid unchanged to 5 decimals (+0.9609) at
  full evidence, better as it thins. NOTE: the V0 instrument scores raw
  per-column medians and never exercised `PlaneDeltaField` — its
  +0.997 was not a solver test; the solver was tested directly.
- Probe pass: the 256-site cap DELETED (§4.G ruling). Implemented as one
  probe per field bin (deterministic, resolution-matched) —
  1,154–1,318 sites / 3,462–3,954 probes per (capture, lane) vs 256/768,
  at 0.8–4.2 ms/probe = 3–17 s. **Earns its existence**: field from the
  no-probe support (29% of tiles, open windows) → Y coverage 0.18,
  Spearman +0.3–0.5; with every probe → Y coverage 0.99, Spearman +0.96.
  The DENSITY ruling that was pending here is now measured — §2.9.
- `done_tiles` from the certificate authority, page-aware rows; the F
  status fold live (FieldStats dual path collapsed to the producer's
  event); per-plane certificate/open counts in the epilogue and on the
  LDPC row; E-band legend; per-axis arrow cap (a y-arrow spans 2 rows,
  not 12); the stale aspect-ratio assertion now asserts absence.

**P2 — instrument fixes** (A0-arm refit reaches every arm about its own
zero and RAISES if features did not move; control certificate leak
closed; `null_proof` measures both arms; per-cell affine refit seam
through QDA/PAVA/A5 bins; `_selfcheck.py`; driver writes `raw.json`
before any reduction). Run: 33 min, peak 13.2 GB, tree `fd7beae`,
state `9514d618…`, read-only.

**E1 recut-bins refit** (union of 3 captures, ground truth):
dead tiles −0.96 pp (sd 0.50, 6/6 tiles, 24/24 rows same sign) vs
controls −0.26 pp; the dead−control gap 2.85 → **2.15 pp** — ~25% of
it was frozen-fit artifact, 75% is not. **Dead-band tile (29,8)
CERTIFIES under the refit** (`48aa9a83…`, syndrome+CRC ok, ordinary
union stage, 99 iterations, 331 → 312 wrong cells) — the supervised
CEILING moving, not a receiver; and the gate interval inverts again
(certified at 7.85% while (31,15) failed at 7.70%). Frozen arm
reproduces gt-affine-final2's polish BER to 0.0000 pp on every tile.

**E2 directional stratification — prediction FAILED.** The anisotropy
is real (downstream-neighbour C/M ink costs +2.2 pp on dead tiles,
upstream −0.0) but controls show it at full strength (+2.0) and one
control out-splits four of six dead tiles. Not band-specific.

**E3 per-state Y contrast — mix compression CONFIRMED, sheet-wide.**
Y's ink/white separation under same-cell M collapses to 0.51–0.56× its
on-white value — equally on dead tiles (0.557), controls (0.510) and
clean references (0.518). A perfect same-cell (C,M)-conditional
threshold is worth ~4.0 pp (dead) / 5.1 (controls) / 4.5 (references);
the directional stratum ~1 pp.

**Blue-channel scanner characterization (I.3)** — from the existing
e028 knife-edge (luma MTF10 17.8 lp/mm, reproduces the record) and the
e028 colour sheet's K edges (channel RATIOS cancel toner/paper): **B is
the SHARPEST channel** (σ_B 0.86–0.97 × σ_G; R is the soft one);
lateral CA ≤0.005 dot in x, a constant ~0.03–0.04 dot R−B spread in y
(CIS line timing, inferred) — ~2% of the 0.83-dot Y excursion and not a
sinusoid. Y's 2–3-cell smear cannot come from a ~45 µm blue LSF. Ink
arm (scanner removed in quadrature): σ **Y 51 > K 46 > C 43 > M 25 µm**
— consumable-confounded (M281, low colour toner); replicate on the
AltaLink e031 sheet, no hardware needed. Package `measure/scanner/`.
**E6 REPLICATED IT (2026-08-23, `measure/scanner/ink_psf.py`; targets
located from the page plan + report affine, so ONE code path reads both
sheets; `scratch/plane-fields/p2/scanner/e031/`): Y's breadth was the
CARTRIDGE.** On the healthy-Y AltaLink the four inks are one club —
σ **M 37.7 / C 37.3 / K 36.8 / Y 34.8 µm** — against the same code's
e028 **Y 46.0 / K 39.6 / C 38.1 / M 36.8**; the stable statistic, Y
against its own sheet's K/C/M mean, is **+7.7/+7.7/+10.5 µm on the M281
and −2.5/−2.2/−3.0 on the AltaLink** under sRGB / gamma-2.2 / no-decode.
The M281's Y 2-dot bars are at once the narrowest and faintest on their
page (FWHM 98.9 vs K's 119.1 µm, peak 0.43 vs 0.61) — thin ragged
development, not scatter. Two numbers above are CORRECTED: the ink σ
supersede "Y 51 > K 46 > C 43 > M 25" (that estimator read a 563 µm
"rise" off a mottle bump inside the yellow plateau, and counted a
patch's interior density ramp as edge width; `analyze_edge` now has an
opt-in fitted-plateau + outward-crossing path, `blue_mtf` byte-identical
under it), and **σ_B 0.86–0.97 × σ_G becomes 0.937 on y (Δσ² −50.4 ±
8.1 µm², the two sheets independently −51.0 / −49.7) and UNRESOLVED on x
(−3.7 ± 47.3)**. The 0.86 end was a MODEL DEFECT the replication test
found: `compare_channels` fits `ln(ratio) = −2π²Δσ²f²` with no constant
term, right for an edge (each channel's ESF is plateau-normalized, so
the ratio is 1 at DC) and wrong for a line (`line_metrics` normalizes by
the PEAK, so the DC ratio is the channels' ink CONTRAST ratio). The
M281's slightly warm K reads 4.5 % weaker in R than in G and the fit had
nowhere to put that constant but the slope — cross-bar R **+102 / B
−107 µm²** against e031's +4 / −33. With `allow_intercept` the sheets
agree (R −5.9/−6.1, B −12.8/−9.5) and **every family replicates**; B is
sharper than G in all of them on both sheets, largest at the widest LSF
window, which is what the self-test's window bias predicts. B-sharpest /
R-broadest stands; luma MTF10 17.82 lp/mm reproduces the record.
**Per-plane registration, from the discovery sheet itself:** the
analyzer's ~115 µm "plane offset" is mostly the authored 4/8/12 mm
K→plane baseline times a local page-scale residual (±6 µm/mm,
column-structured and repeating down all three rows; the centre column's
+6 appears on BOTH engines). Regressing the offsets ON that baseline
leaves the AltaLink's three colour planes sharing ONE line — displaced
from K by (+6.3 ± 2.5, +18.4 ± 2.0) µm = (0.15, 0.44) dot, fit residual
2.2–3.6 µm, i.e. **no plane-specific offset at all**; the M281 does not
fit that model (residual 15.1 µm) because **its Y plane sits −73.3 µm =
−1.7 dot from K in the process direction** (C +28.1, M +9.4) — a second
mechanism behind e030's Y-empty CMY8 failure, alongside the starved
cartridge. Estimator controlled against a half-max midpoint (agrees to
≤2.6 µm). Three x-columns cannot sample e033's ~100 mm sinusoid: W11
item 2 stands.

**Verdict of P2:** geometry ~half of the dead-band penalty; the
frozen-fit artifact ~a quarter of the remainder; the context
anisotropy and the mix compression are REAL but SHEET-WIDE, present at
full strength on tiles that certify — they are not why these columns
are dead. **After geometry and refit, 2.15 pp of dead-vs-control gap is
unattributed.** CORRECTION (same day, user's question): E3's "~4–5 pp"
is the gain of a per-state threshold over a SINGLE threshold on the raw
Y value — a baseline the production detector is already past (it is an
8-state full-covariance QDA with per-state means and shrunk per-state
covariances, marginalized then PAVA-calibrated: production 8.2% on the
controls vs the per-stratum oracle's 12.3%). The PHYSICAL finding
stands (Y under same-cell M keeps ~0.5× its on-white separation,
everywhere); the claim that this is an unclaimed detector lever does
NOT. The open quantity is narrower: the production head's PER-STATE
error vs the per-state oracle, with n_k and the covariance-shrinkage
factor a_k = min(1,(D+2)/n_k) per state — and, in dead bands with no
certified Y, whether the Y-bearing states (labelled by ~20 dust cells
per tile; words show only states 000/110) are thinly fitted (E3′).

### 2.9 E5 — the probe-DENSITY ruling (2026-08-22)

The §2.8 pending ruling, measured through the PRODUCTION pass itself
(`ProbeMode` enum; `measure/plane_fields/probe_density.py`, read-only)
on the W6 qualification state, capture 1, lane `l02-8ppc-2400dpi`
(8 px/cell, finest ordinary), 143 certified-complete windows of 330
placements, probes only (no anchors), truth = regmap-gt per column.
Artifacts `scratch/plane-fields/p2/e5/`.

| whole sheet | A block/bin 5×5 | B whole-tile 64×64 | C every block 5×5 |
|---|---|---|---|
| sites | 2,039 | 593 | 4,597,156 |
| **certified tiles reached** | **1,025 / 1,628** | **516 / 1,628** | 1,025 / 1,628 |
| probes | 6,117 | 1,779 | 13,791,468 |
| wall (one capture, lane) | **3.4 s** | 30.9 s | ~82 min *EXTRAPOLATED* |
| ms/probe | **0.56** | 17.39 | 0.355 *(measured on the stratum)* |
| field bin coverage | **0.813** | 0.642 | — |
| column Spearman vs GT | **+0.9265** | +0.9070 | — |
| per-TILE residual vs GT, MAD | 0.217 (n 1,595) | **0.202** (n 1,259) | — |
| below the 0.30 NCC floor | **0 of 6,117** | **0 of 1,779** | 0 |

C's wall is the ONLY extrapolated number: 13,791,468 probes (the exact
site census × 3 planes) at its measured 0.355 ms/probe. It was run on a
48-tile stratum, not the sheet.

**A STAYS.** B is not cheaper and not better on the sheet: 31× per probe,
9× wall, and HALF the reach. The reach is the mechanism and it is
geometric — an eligible block must lie wholly inside ONE window's
audited cells and wholly inside ONE certified tile, and the committed
windows are 200×200 cells and not tile-aligned, so a template as wide as
a tile fits only where a 64-aligned tile lands inside a window.

What B genuinely wins, and it is real: **a whole-tile probe is 2.4–3×
more precise than a 5×5 probe** — `dY_rel_x` against the supervised
column value, on the 280 tiles both densities reach: per SITE A bias
+0.080 sd 0.249 MAD 0.231 dot (480 sites) vs B +0.089 sd **0.084** MAD
**0.081** (280 sites); per TILE (A pooled over its 1.71 sites/tile)
A MAD 0.196 vs B **0.081**. Same bias, so it is variance, not aim. On a
48-tile stratum where reach is equalised by construction, B is duly the
better field (residual MAD 0.175 vs 0.189; Spearman +0.9428 vs +0.8952).
It does not survive contact with the whole sheet, where A's extra 509
tiles win.

The 25-cell-vs-4,096-cell template worry does not bite: quality medians
C 0.769/0.745, M 0.736/0.709, Y 0.612/0.586 (A/B) and **the floor
rejects nothing at either density**; no probe went off-raster either.

B's one whole-sheet win is ADOPTION (C,M,Y vs A's C,Y) and it is the
0.25-dot cliff again, not a density verdict: A's M median magnitude is
**0.2454**, refused by 0.0046 dot; B's is 0.2711. B also carries 1.7×
A's posterior sd on every plane, having a third of the samples.

C is the null result: **4,550× more probes than B on the same 48 tiles**
(696,455 vs 153, 247 s vs 3.0 s), landing within 0.008 dot of it
(stratum residual MAD 0.167 vs 0.175, Spearman +0.9312 vs +0.9428).
There is nothing above the whole-tile rung.

FOLLOW-UP, measured but NOT built: the whole tile where the whole tile
is available and a 5×5 block everywhere else would buy B's precision on
516 tiles and A's reach on the other 509 for ~12 s. One predicate in
`_probe_sites`; it needs its own measurement.

**RETRACTED 2026-08-23 by §2.9b** — everything above is arithmetically
correct and the framing is wrong. §2.9 read reach and precision as a
TRADE the pass has to make, and its follow-up proposed switching between
two generators to get both. Neither is a property of the design: both
are properties of the two GENERATORS E5 happened to compare, and both
dissolve when the generator changes. See §2.9b.

### 2.9b E5b — the TILE-CENTRIC probe, and what E5 was really measuring
*(2026-08-23; `measure/plane_fields/probe_density.py`; artifacts
`scratch/plane-fields/p2/e5b/`)*

THE USER'S CORRECTION, verbatim: *"when you have a certified tile, each
window that covers this tile (fully or partially) can profit from the
pose/field measurement — it's like feeding back a pose."*

E5 compared two WINDOW-centric generators. Both ask *does a template of
edge E fit wholly inside one window and one certified tile?* — so a tile
that straddles a window boundary is refused at every E wide enough to be
precise, and a window that still owes payload work is not asked at all.
E5b keeps the footing (W6 qualification state `9514d618…` VERIFIED,
capture 1, lane `l02-8ppc-2400dpi` at 8 px/cell, probes only, no
anchors, truth = regmap-gt per column, 330 placements over 1,628
fully-certified tiles of 1,961) and changes the question to the
tile-centric one, in two independent steps:

* **predicate (i) dropped**: EVERY window is offered to the pass, mixed
  as well as label-only (§4.G). A fully certified tile inside a window
  that still owes payload work is exactly as certified, and the window
  covering it is exactly as posed. 143 of the 330 windows are
  label-only; **603 certified tiles are reachable only through the other
  187**.
* **F = `TILE_FRAGMENT`**: one probe per (certified tile, covering
  window) PAIR, template = every cell of that tile inside that window's
  audited cells, weight 1 inside and 0 out. Its only floor is
  identifiability — `probe_block_cells` of span on each axis and
  `probe_block_cells²` cells in total, one shipped 5×5 probe's worth,
  re-checked on the cells that survive the projection's known mask.

**Reach is not a density property.** At `bins_per_tile = 1` a field bin
IS a tile, so A and F place the SAME 3,837 sites — one per (tile, window)
pair. They differ only in the size of the template at each. Once
predicate (i) is dropped, A and F reach **all 1,628** certified tiles,
where on the E5 footing A itself reached 1,025 (63% of the sheet). The
two predicates are separable and both bite: the label-only rule costs A
603 tiles and B 654; the square-template rule costs B a further 458. E5
reported B's reach as "half" — half of A's footing, which was itself two
thirds of the sheet.

| whole sheet, ALL windows | A block/bin 5×5 | B whole-tile 64×64 | F tile-fragment |
|---|---|---|---|
| sites | **3,837** | 1,268 | **3,837** |
| probes | 11,510 | 3,804 | 11,511 |
| template cells, median | 25 | 4,096 | 2,752 |
| **certified tiles reached** | **1,628 / 1,628** | 1,170 / 1,628 | **1,628 / 1,628** |
| wall (one capture, lane) | **6.9 s** | 68.6 s | 139.4 s |
| ms/probe | **0.60** | 18.04 | 12.12 |
| field bin coverage | **0.997** | 0.995 | **0.997** |
| column Spearman vs GT | **+0.9711** | +0.9701 | +0.9699 |
| per-TILE residual vs GT, MAD | **0.163** (n 1,955) | 0.164 (n 1,951) | 0.168 (n 1,955) |
| adoption | C,M,Y | C,M,Y | C,M,Y |
| below the 0.30 NCC floor | 0 | 0 | 0 |

The same three on the E5 LABEL-ONLY footing, which reproduces §2.9 digit
for digit (A 2,039 sites / 6,117 probes / coverage 0.813 / +0.9265 / MAD
0.217; B 593 / 1,779 / 0.642 / +0.9070 / 0.202 — the harness is faithful
to the measurement it is superseding):

| label-only footing | A | B | F |
|---|---|---|---|
| certified tiles reached | 1,025 | 516 | 1,025 |
| wall | 3.6 s | 32.1 s | 72.3 s |
| field bin coverage | 0.813 | 0.642 | 0.813 |
| column Spearman | +0.9265 | +0.9070 | +0.9220 |
| per-TILE MAD | 0.217 | 0.202 | 0.227 |
| adoption | C,Y | C,M,Y | C,Y |

**THE WIN IS PREDICATE (i), NOT THE TEMPLATE.** For A, dropping it costs
3.3 seconds and buys +603 tiles, coverage 0.813 → **0.997**, Spearman
+0.9265 → **+0.9711**, per-tile MAD 0.217 → **0.163** (−25%), and M
across the 0.25-dot adoption cliff (median magnitude 0.2454 → 0.2775):
C,Y → **C,M,Y**. E5's "B's one whole-sheet win is ADOPTION" evaporates —
on the full window set every density adopts all three planes.

**The field was REACH-limited, not precision-limited.** With reach
equalised, a 25-cell template and a 4,096-cell one produce fields that
agree to 0.005 dot of per-tile MAD and 0.0012 of Spearman. B's genuine
per-probe precision advantage — E5 measured it and it is real — does not
propagate, because the field POOLS: A's smoothed posterior over 11,510
noisy samples is as good as B's over 3,804 tight ones.

Per-probe, on the 400 tiles all three densities reach (matched stratum,
`dY_rel_x` against the supervised column value):

| per probe | A | B | F |
|---|---|---|---|
| three-plane sites | 718 | 400 | **828** |
| template cells, median | 25 | 4,096 | 2,304 |
| bias | +0.037 | +0.044 | +0.049 |
| sd | 0.254 | **0.088** | 0.110 |
| MAD | 0.245 | **0.093** | 0.112 |
| per-TILE MAD | 0.229 | **0.093** | 0.101 |
| q median C / M / Y | .764/.731/.603 | .742/.711/.577 | .745/.713/.580 |
| below the 0.30 floor | 0 of 2,517 | 0 of 1,221 | 0 of 2,517 |

So F IS the thing §2.9's follow-up wanted and could not see how to
build: **whole-tile-class precision (MAD 0.112 vs B's 0.093, vs A's
0.245) at block-per-bin reach**, and it needs no hybrid predicate — it
needs the tile-centric question. It just turns out the FIELD had no use
for it.

**THE WINDOW POSE RESIDUAL — measured, and never applied.** Every probe
splits into a per-plane part, which is what the field consumes, and a
part all three planes share. The shared part is not a registration
difference at all: it is that WINDOW's own committed pose, seen through
certified ground truth. Recorded per window in its own LOCAL frame
(`WindowPoseResidual`, `plane_fields.pose_residual_*`), applied nowhere
— feeding it back is P5 writer work (COMPOSITE-POSE-DESIGN §6, where
plane-common belongs to word solves and pose refinement).

| plane-common residual, all windows | A | B | F |
|---|---|---|---|
| windows measured | 329 | 314 | 329 |
| magnitude, median | 0.200 | 0.190 | 0.184 |
| magnitude, p90 / max | 0.461 / 0.940 | 0.376 / 0.722 | 0.376 / 0.944 |
| within-window spread, median | 0.264 | **0.099** | 0.187 |
| windows whose sites AGREE (spread < ½ magnitude) | 9% | **46%** | 17% |

There IS a pose correction sitting there: a median window is off by
**0.18–0.20 print dots** plane-common, p90 0.38, worst 0.94 — the same
order as the 0.25-dot cliff the field's own adoption gate is built on.
But whether a window's tiles AGREE about it is entirely a template-size
question: at 25 cells the site-to-site scatter (0.264) exceeds the
signal and only 9% of windows are self-consistent; at a whole tile the
scatter collapses to 0.099 and 46% are. **A pose writer must not be fed
by the shipped 5×5 density.** F sits between, because its fragment sizes
do (median 2,304–2,752 cells, p10 704).

**VERDICT — the default STAYS `BLOCK_PER_BIN`.** The pre-registered bar
was "F beats A on coverage AND Spearman AND per-tile MAD"; F ties
coverage, loses Spearman by 0.0012 and per-tile MAD by 0.005, at 20× the
wall. Nothing about the field justifies the template. What ships from
E5b is the PREDICATE: every window, mixed included, which is free and
carries the whole measured gain. `TILE_FRAGMENT` stays in the tree
because it is the density a POSE writer wants and the density a
cross-capture field wants — both of which want per-measurement precision
that pooling cannot manufacture — and because it is the only one that
has both properties at once.

*Caveat on the wall times: two unrelated decodes were running on this
machine throughout. The numbers are comparable WITHIN this run — every
run here shares the load — and not against §2.9's. The run itself is
valid: `receiver_tree_sha256` is identical at entry and exit (an earlier
attempt VOIDED itself when the tree moved mid-run, and was discarded).*

### 2.9c The flip, its pose regression, and the FFT
*(user rulings 2026-08-23; `measure/plane_fields/probe_density.py`,
artifacts `scratch/plane-fields/p2/e5c/`)*

**THE FLIP.** `PlaneFieldConfig.probe_mode` now defaults to
`TILE_FRAGMENT`. §2.9b ruled on the FIELD, found a tie, and left the
default alone; the ruling changes what the pass is FOR — **one
measurement per (certified tile, covering window) serving BOTH** the
per-plane field and the plane-common pose feedback (still measured,
still not applied). The field half ties. The pose half does not, and it
is the half a 25-cell template cannot carry: at the 5×5 density the
site-to-site scatter (0.264 dot) exceeds the signal (0.184–0.200) and
only 9% of windows are self-consistent.

Dial OFF is untouched — a `None` config constructs no builder and never
consults the density. **Dial ON behaviour changes** and there is NO
policy-id bump (that rule was under discussion; settled 2026-08-23 —
§6 P3, RECEIVE-DESIGN §9c: a bump is no longer an orphaning event, so
the honest bump is now the cheap option): an archived colour state
resumed with `--refine` under the field arm collects a different probe
set than it would have before.

**THE POSE REGRESSION.** The probe pass is downstream of placement and
the plane-common residual is reported, never applied, so a density
change must not move one committed pose. Three layers, all pinned
(`tests/holo/test_plane_field_pose_regression.py`):

* **dial OFF** — every byte-identity pin stands: the null proof's
  certificate digest and close sha, `test_payload_nulls`,
  `test_color_field_arm`, the seven-coding gate net;
* **dial ON, same geometry either way** — the pass writes back nothing
  it was handed (poses and pixels digested before and after); the `uF`
  lane, the one production lane that turns the dial on, commits no pose
  and no replacement address at either density *while its field evidence
  demonstrably differs* (the plane-common spread collapses 50×, E5b's
  sheet-I finding reproduced on a fixture whose truth is known); and a
  whole dial-ON decode lands on byte-identical `PoseRecord` rows,
  placement ledger, certificates and close;
* **the residual recovers what it claims** — synthetic captures with a
  KNOWN plane-common shift, under every `rot_k` and through label-only,
  mixed and clipped windows, report that shift in the window's LOCAL
  frame with the right sign (expected value from an independently
  written rotation, not from `_rotate_delta_xy`); and a capture
  displaced per PLANE (C `+d`, M `−d`, Y 0) reports no plane-common
  shift while the field carries the whole of it.

On the W6 state itself the qualification state's sha (`9514d618…`) is
identical before and after every run below: the pass reads committed
poses, it never writes them.

**RE-MEASURED ON W6** — same footing as E5b (state `9514d618…` VERIFIED,
capture 1, lane `l02-8ppc-2400dpi`, probes only, truth = regmap-gt),
both densities, all 330 windows:

| whole sheet, all windows | A block/bin | **F tile-fragment (SHIPPED)** |
|---|---|---|
| sites / probes | 3,837 / 11,510 | 3,837 / 11,511 |
| template cells, median | 25 | 2,752 |
| certified tiles reached | 1,628 / 1,628 | 1,628 / 1,628 |
| field bin coverage | 0.997 | 0.997 |
| column Spearman vs GT | +0.9711 | +0.9699 |
| per-TILE residual vs GT, MAD | 0.163 | 0.168 |
| adoption | C,M,Y | C,M,Y |
| pose residual, magnitude median | 0.200 | **0.184** |
| pose residual, within-window spread | 0.264 | **0.187** |
| windows whose sites AGREE | 9% | **17%** |

Every digit is §2.9b's, unchanged — the field tie is confirmed, and the
pose gap is the whole reason for the flip.

**THE FFT.** The rectified NCC's correlation search was a sliding-window
view: materialize every candidate patch and contract three `einsum`s
over them, O(shifts × template). It is now three FFT correlations — `A =
Σ P·Tw`, `S1 = Σ P·w`, `S2 = Σ P²·w`, two images and two kernels
transformed once each, three products sharing one inverse — at the
WINDOW's own transform length, which is exact for the valid region
because circular wrap lands strictly before its first index. The window
is centred first: the NCC is invariant to that and the raw second moment
is not. No runtime switch; the sliding form survives only as the test
oracle.

A/B on the same tree with the one function swapped, same machine, same
load window (one unrelated decode running throughout — these numbers are
comparable to each other, not to §2.9b's):

| one (capture, lane), 11,511 probes | sliding | FFT | |
|---|---|---|---|
| **F tile-fragment**, ms/probe | 10.53 | **3.86** | **×2.73** |
| **F tile-fragment**, wall | 121.2 s | **44.4 s** | |
| A block/bin, ms/probe | 0.557 | 0.478 | ×1.17 |
| A block/bin, wall | 6.4 s | 5.5 s | |

The 5×5 density barely moves, and that is the finding under the
headline: at 25 cells the correlation is not the cost — the rectified
resampling and the `np.kron` template are. At a whole tile it is, which
is exactly where the shipped density lives.

**Equivalence, measured, not asserted.** Site and probe counts are
identical (3,837 / 11,511 both), and over the 682 recorded numeric
leaves of the run — coverage, per-plane rms/peak, every column profile,
every Spearman, the per-tile GT residual, the whole pose-residual
summary — **the worst disagreement is 3.4e-15 dot**. Coverage and the
Spearman coefficients are bit-identical. Nothing crossed the 0.30
quality floor differently. Against the sliding oracle on randomized
synthetic templates the integer peak is identical in every case
(`tests/holo/test_color_ncc_fft.py`).

### 2.10 E3′ + E4 — the head's own per-state numbers, and the Y-context loop
*(2026-08-23; `measure/plane_fields/state_context.py`, artifacts
`scratch/plane-fields/p2/e3e4/`; the §6 P2b discriminators)*

**Footing.** E1's REFIT arm, tile for tile: the restricted region (91–97
windows, radius 3) re-fitted with the target tile sampled at its
`gt-affine-final2.json` 6-dof affine plus BER polish, so the
registration fit, the QDA/PAVA stack and the A5 context bins all see the
corrected geometry. Three 2400 dpi captures, lane `l02-8ppc-2400dpi`,
one capture resident at a time; 62 min, peak RSS 14.8 GB.

Four things the run ASSERTS rather than assumes, all passed:
configuration (a) reproduces E1's refit union cell error on all eight
tiles with **max |gap| 0.0** (every digit); the instrument's rebuild of
A5's ink map at (a) is **bit-identical** to the one the ladder itself
produced, on all 24 (tile, capture) fits; every KNOWN cell's exact bits
equal the printed truth (10,135,988 cells, 0 mismatches); and every
configuration leaves the bin columns it did not override bit-identical,
24 of 24.

#### E3′ — per-state production vs oracle

| state (C-M-Y) | n_k | a_k | dead: n · prod · oracle · gap | control: prod · oracle · gap | reference: prod · oracle · gap |
|---|---|---|---|---|---|
| 000 (W) | 138,365 | 3.6e-05 | 8,907 · 6.84 · 14.71 · −7.86 | 2.73 · 9.16 · −6.44 | 2.63 · 9.22 · −6.59 |
| 100 (C) | 117,513 | 4.3e-05 | 8,877 · 9.74 · 19.24 · −9.50 | 5.51 · 16.75 · −11.24 | 6.60 · 14.13 · −7.53 |
| 010 (M) | 117,462 | 4.3e-05 | 8,952 · 6.70 · 21.87 · −15.17 | 4.68 · 23.42 · −18.74 | 3.22 · 19.32 · −16.09 |
| 110 (CM) | 137,157 | 3.7e-05 | 9,078 · 4.21 · 12.09 · −7.87 | 2.50 · 10.91 · −8.40 | 1.85 · 10.03 · −8.18 |
| 001 (Y) | 117,598 | 4.3e-05 | 8,940 · 4.73 · 8.41 · −3.68 | 3.78 · 10.49 · −6.71 | 0.64 · 5.39 · −4.74 |
| **101 (CY)** | 117,802 | 4.2e-05 | 9,075 · 11.23 · 10.95 · **+0.29** | 10.60 · 11.01 · −0.41 | 3.45 · 9.41 · −5.96 |
| **011 (MY)** | 117,227 | 4.3e-05 | 8,736 · 18.31 · 12.33 · **+5.98** | 14.78 · 11.65 · **+3.12** | 7.25 · 10.98 · −3.73 |
| **111 (CMY)** | 117,054 | 4.3e-05 | 9,003 · 16.67 · 9.39 · **+7.28** | 13.58 · 7.62 · **+5.95** | 9.31 · 7.75 · **+1.56** |
| **whole tile** | | | **9.78 · 13.60 · −3.84** | **7.31 · 12.56 · −5.25** | **4.39 · 10.73 · −6.34** |

Percent, per capture, pooled over 18 dead / 6 control / 18 reference
(tile, capture) rows = 6 / 2 / 6 physical tiles. `prod` is the
calibrated head's own hard Y decision; `oracle` is the best threshold on
the raw Y channel fitted PER (C, M) STRATUM with full knowledge of the Y
bits, so a stratum's two states are that one threshold's two class
errors. The block path and this direct-head column agree to every
printed digit on all 24 rows.

**(1) Are the Y-bearing states thinly labelled? NO, and not by two
orders of magnitude.** Every state is fitted on 117,054–138,365 training
labels, so `a_k = min(1, (D+2)/n_k)` is 3.6–4.3e-05 — the shrinkage term
is inert, no state carries the "fully shrunk to pooled" warning, and the
QDA runs on essentially pure per-state ML covariances everywhere. The
premise was right about FURNITURE and wrong about the population: words
really do show only 000 and 110 (41,769 / 40,294 labels) and dust really
is ~2,750 per inked state — but the region's owner population is
1,957,392 cells, of which ~232,000 PER STATE are prior-barrier CERTIFIED
payload cells. Sheet I is 94 % certified, so a dead-band region's
Y-bearing classes are as well fed as its W class, and the PAVA
calibration population (dust + certified, 1,875,329 labels) with them.
`n_k` and `a_k` are pure functions of the ownership split, so this is
identical for every arm and every refit of one capture.

The model also already CARRIES the mix compression §2.8 measured: the
per-state Y means give an ink/white gap of 0.1790 on white and 0.0930
under same-cell M — a ratio of **0.520**, reproducing E3's 0.51–0.56×
out of the head's own parameters (C 0.812, CM 0.756).

**(2) Does the window-photometry gate fail preferentially in dead-band
windows? NO — the opposite, in all three captures.** A3 is
OVERRIDE-ONLY in production (`color_stack`: reachable only from the
`u-a3` supplemental lane), so no lane in this state ever fitted a window
map; this is a diagnostic of what that lane would find.

| capture | clean: windows / adopted | dead: windows / adopted | dead n_own | clean n_own |
|---|---|---|---|---|
| 269d8… | 37 / 7 (18.9 %) | 44 / 20 (45.5 %) | 6,132 | 4,155 |
| a4106… | 36 / 4 (11.1 %) | 44 / 15 (34.1 %) | 6,326 | 3,152 |
| 36b90… | 47 / 12 (25.5 %) | 44 / 15 (34.1 %) | 6,444 | 4,852 |

Dead-band windows adopt a map more often, carry ~1.5× the own labels,
and are the ONLY band whose mean held-out NLL gain is positive
(+0.015 … +0.062, against −0.011 … −0.048 clean and ~−0.003 mixed).
Every refusal is `validation_gate_failed` except three
`heldout_starved` windows in one capture. Whatever binds in the dead
bands, it is not that this gate refuses there.

**(3) Where is the production-vs-oracle gap, and is it band-specific?**
The head is BELOW the per-stratum oracle at every band (−3.84 / −5.25 /
−6.34 pp), so a per-(C, M) threshold on the raw channel is a WEAKER
baseline than the shipped head, not a ceiling it fails to reach —
§2.8's retraction holds band by band. The deficit that does exist is
confined to three states, and they are the Y-INKED-WITH-A-SIBLING half
of the alphabet: 011 (MY), 111 (CMY) and marginally 101 (CY). Those
three carry **58.8 % of the dead tiles' Y errors on 37.5 % of their
cells**; everywhere else the head beats the oracle by 3.7–15.2 pp.
Putting just those three states at their own oracle rate would be worth
**−1.68 pp (dead) / −1.13 (control) / −0.20 (reference)** *per capture,
arithmetic on this table, not a decode*. So: state-specific and real,
but present on the controls at roughly half strength and graded by the
tiles' overall difficulty (dead 9.78 > control 7.31 > reference 4.39)
rather than by band membership. Not the 2.15 pp.

#### E4 — the Y-context circularity test

| configuration | dead | control | gap (pp) | closed (pp) | certified d / c |
|---|---|---|---|---|---|
| (a) baseline (provisional ink) | 8.744 | 6.590 | **+2.155** | — | 1 of 6 / 2 of 2 |
| **(b) Y ink column = GT** | **6.317** | **4.137** | **+2.180** | **−0.025** | **4 of 6** / 2 of 2 |
| (c) C,M columns = GT *(method control)* | 8.744 | 6.590 | +2.155 | 0.000 | 1 of 6 / 2 of 2 |
| (d) all three = GT | 6.317 | 4.137 | +2.180 | −0.025 | 4 of 6 / 2 of 2 |

Union cell error over the three captures, percent, `bins` arm. Per tile:

| tile | band | (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|
| 14,9 | dead | 9.23 | **6.16 CERT** | 9.23 | 6.16 CERT |
| 23,18 | dead | 8.00 | **5.51 CERT** | 8.00 | 5.51 CERT |
| 29,8 | dead | 7.85 CERT | 5.56 CERT | 7.85 CERT | 5.56 CERT |
| 31,15 | dead | 7.70 | **5.86 CERT** | 7.70 | 5.86 CERT |
| 34,27 | dead | 10.24 | 7.19 | 10.24 | 7.19 |
| 47,28 | dead | 9.46 | 7.62 | 9.46 | 7.62 |
| 15,7 | control | 6.84 CERT | 4.55 CERT | 6.84 CERT | 4.55 CERT |
| 24,20 | control | 6.34 CERT | 3.72 CERT | 6.34 CERT | 3.72 CERT |

**The method control is exact.** (c) reproduces (a)'s union error on all
eight tiles to every digit and its certification exactly; (d) equals (b)
the same way. C and M are certified on these tiles and their provisional
ink disagrees with the printed field on 0.027–0.046 % of the region's
cells (M: exactly 0.000 %), so handing the ink map their truth moves
0.15 % of C bins region-wide and 0.0 % on the target tiles. The
instrument contributes nothing of its own.

**The accounting of the 2.15 pp: NONE of it closes.** (b) moves the
dead tiles **−2.427 pp** and the controls **−2.452 pp** — the gap goes
2.155 → 2.180, wider by 0.025. The pre-registered prediction's SECOND
branch is the one that fired: the circularity moves dead and control
tiles equally, so **it is not band-specific and it is not the
unattributed residual**. §2.8's 2.15 pp survives E4 intact.

**What it is instead: the largest detector-side effect this campaign has
measured.** −2.43 pp on the dead tiles is 2.5× the recut-bins refit's
−0.96 pp (§2.8 E1), and it flips **three of the six dead tiles to
CERTIFIED** — (14,9), (23,18) and (31,15) join (29,8); only (34,27) and
(47,28) stay out. It is sheet-wide because its cause is: Y's provisional
ink disagrees with the printed field on **5.31–5.49 %** of the
restricted region's cells in every capture, against C 0.027–0.046 % and
M 0.000 %, and replacing that one column moves **42–66 %** of a target
tile's Y context bins. Refitting A5's curves on the corrected bins
(`bins+head` arm) adds a further 0.02 pp dead / 0.08 control, and at
configuration (a) it reproduces the incumbent head's union error on all
eight tiles exactly — the refit machinery is a null where it must be.

**What this licenses.** (b) is an ORACLE — a receiver cannot know Y's
printed bits — so it measures the SIZE of the loop, not an available
gain, exactly as the supervised affine measures a ceiling. The
realizable forms it points at, NONE built and NONE measured: a
confidence-gated ink map (trust provisional ink only above an |LLR|
floor and leave the rest uncorrected — K's `-1` "no valid context" is
already the vocabulary); ONE fixed-point iteration (decode, rebuild the
ink map from the decision, re-decode), which the per-address retirement
law would make monotone inside a supplemental lane; or an ink map built
from certificates alone where coverage allows. The honest prior is that
each recovers a FRACTION of the 2.43 pp: the cells whose provisional ink
is wrong are exactly the cells the detector is least sure about, which
is what makes them cheap to identify and hard to fix from inside the
same decision.

**Caveats.** The six dead tiles and two controls are OUTCOME-SELECTED
(they are where the residue is) and the controls are n = 2 physical
tiles; the certified references are not outcome-selected and are carried
for that reason. E3′ pools (tile × capture) rows as if independent —
three captures of one physical tile are not, and `n_tiles` sits next to
`n_rows` in every pooled row. The geometry under every number here is
SUPERVISED (fitted against the printed truth): a ceiling, not a
receiver. Reference tiles are suppressed by the emission mask, so their
production column is the head's unemitted output at the reference's own
fitted affine on the FROZEN detector — E3's footing for those tiles, not
E1's refit. A3's table describes an arm that does not run on any lane in
this state. The run's peak RSS was 14.8 GB against a ~13 GB working
budget (64 GB machine, 44 GB free/inactive throughout, no swap
pressure); the git HEAD moved under the run (E6 and §2.11 landed) but
the load-bearing identity, the content hash of `src/holo`, did not
(`31b92b3c…` before and after).

### 2.11 The POSE WRITER, measured in certificates — MEASURED NEGATIVE
*(2026-08-23; `measure/plane_fields/pose_writer.py`, artifacts
`scratch/plane-fields/p2/pose-writer/`; the P5 bar for
COMPOSITE-POSE-DESIGN §6 writer (b))*

§2.9b measured a per-window plane-common residual and applied it
nowhere; §2.9c flipped the shipped density BECAUSE that half is the one a
5×5 template cannot carry. This is the measurement that half was flipped
for: what feeding it back to the window pose WOULD yield, in
certificates.

**Footing.** W6 qualification state `9514d618…` VERIFIED, 5,549
certificates; all **334 open `(tile, stream)` slots** (Y 332, C 2) over
333 tiles; three archived 2400 dpi captures unioned; lane
`l02-8ppc-2400dpi`; `TILE_FRAGMENT` probes only, no anchors (E5/E5b/E5c's
footing); ONE payload region per capture fitted over ALL of its
placements (330 / 330 / 327), no restriction radius. Six sampling
configurations, every one of them — the baseline included — through the
SAME production `offsets_override` seam, so the seam's own float32
rounding is not inside the difference. Both a FROZEN-detector and an E1
REFIT footing (registration, QDA/PAVA and the A5 bins recut at the
corrected geometry, every window of the region, per capture per
configuration). Runtime 3,400 s, peak RSS 13.96 GB, one
raster resident at a time. `receiver_tree_sha256` identical at entry and
exit.

| | plane-common sampling | per-plane sampling |
|---|---|---|
| (i) `committed` | the arm's own zero | the arm's own zero |
| (ii) `field` | the field's | the field's |
| (iii) `field+pose-t` | field + window translation | the field's |
| (iv) `field+pose-affine` | field + window local affine | the field's |
| (v) `field-diff` | the arm's own zero | the field's, differential |
| (vi) `field-diff+pose-t` | window translation | the field's, differential |

**THE RESIDUAL.** Per capture, over 329/329/326 windows: quality-weighted
translation magnitude median **0.174 / 0.173 / 0.181 dot**, p90 0.30–0.33,
max 0.87 / 0.85 / 1.20; production's median form 0.184 / 0.184 / 0.176
(the instrumented collector reproduces `WindowPoseResidual` on every
window to **0.0 dot** — asserted, not assumed, or the run stops);
within-window spread 0.19 / 0.18 / 0.16; sites AGREE in 17 / 17 / 16% of
windows. §2.9c reproduced. Label-only and mixed windows carry the same
magnitude (0.173–0.186 vs 0.169–0.180); mixed windows carry fewer sites
(median 9–10 vs 12–16), and **only a mixed window can win a slot** —
187 / 175 / 176 of the 330.

**THE SIGN CHECK.** Every window's pose translated by its own estimate
and the whole probe pass re-run: magnitude median **0.174 → 0.0019 dot**
(0.0019 / 0.0019 / 0.0022 across the three), collapse ratio 0.011–0.012,
reduced in **100%** of windows, all three captures.
The correction does exactly what it claims, in the right frame and with
the right sign. It is a control, not a validation: a correction equal to
a probe-side BIAS would also make the probe's own residual vanish.

**THE TABLE** — certificates / mean ground-truth cell BER, over all 334
slots and over the 310 dead-band ones:

| | (i) committed | (ii) field | (iii) +pose t | (iv) +pose affine | (v) diff field | (vi) diff+pose t |
|---|---|---|---|---|---|---|
| frozen, all 334 | 3 / 18.07% | **1 / 12.93%** | 0 / 14.67% | 0 / 14.65% | 1 / 13.53% | 0 / 14.26% |
| frozen, dead 310 | 3 / 18.49% | **1 / 13.06%** | 0 / 14.81% | 0 / 14.82% | 0 / 13.70% | 0 / 14.43% |
| E1 refit, all 334 | — | **5 / 11.11%** | 0 / 13.22% | — | — | 2 / 12.31% |
| E1 refit, dead 310 | — | **3 / 11.19%** | 0 / 13.32% | — | — | 1 / 12.43% |

**The pre-registered bar** (written to `v1-bar.json` before the first
measurement ran): ≥ 5 slots beyond (ii), or a ≥ 0.5 pp dead-band BER
reduction. Measured: **−1 slot** and **−1.75 pp** (frozen), **−5 slots**
and **−2.13 pp** (refit). **FAILED on both clauses, in the wrong
direction.** The trade is not neutral: on the refit footing (iii) loses
all five slots (ii) won and returns none.

*Strict superset is NOT automatic here, and the brief's expectation that
it would be is worth correcting: attempts only add, but these are
alternative sampling GEOMETRIES, each producing its own evidence set. A
receiver that ATTEMPTED both would union them; a pose WRITER replaces the
geometry, and the replacement loses.*

**THE INVERSION — the damage is linear in the correction's own size.**
Regressing the per-slot BER change on the mean plane-common residual of
the slot's covering windows: **+9.55 pp per dot** frozen (r +0.44),
**+9.27 pp per dot** refit (r +0.37), zero crossing at +0.03 / −0.01 dot.
By residual bin (frozen, (ii) → (iii)):

| residual, dots | < .12 | .12–.18 | .18–.24 | .24–.32 | > .32 |
|---|---|---|---|---|---|
| slots | 50 | 94 | 84 | 67 | 39 |
| (ii) field | 12.29% | 12.12% | 12.74% | 14.22% | 13.90% |
| (iii) +pose t | 12.76% | 12.88% | 14.46% | 17.30% | 17.32% |

And the worst stratum of all is the one where the writer's evidence is
BEST: over the 72 slots whose covering windows are self-consistent,
13.79% → **17.29%** (+3.50 pp) frozen, 11.80% → **15.85%** (+4.05 pp)
refit. A correction that does most harm where its own sites agree most is
carrying a systematic component, not noise. The region's held-out
log-loss says the same at the detector level: 0.753/0.771/0.759 at the
arm's zero → **0.613/0.619/0.617** under the field → **0.684/0.685/0.670**
once the pose is added.

**TRANSLATION vs AFFINE — statistically real, decision-irrelevant.** The
per-window local affine (ridge-shrunk toward identity, 0.25-dot
edge-displacement prior; median shrinkage 0.68–0.84, so the data, not the
prior, is setting it) beats translation-only on **77 / 80 / 80% of
windows** by LEAVE-ONE-SITE-OUT prediction error, 0.27 → 0.23 dot,
with a median edge displacement of 0.24–0.30 dot — as large as the
translation itself. In the decode the two are indistinguishable:
14.67% vs 14.65%, 0 certificates either way.

**WHY — the field already carries it.** The premise of writer (b) is that
the plane-common half of every probe is currently discarded. It is not:
`add_certified_probes` feeds the field each plane's FULL local offset, so
the field's prediction contains that half, pooled over tile space.
Measured per window, as the plane-common CHANGE configuration (ii) makes
to the sampling against the translation a writer would add on top:
magnitude median **0.146 / 0.149 / 0.120 dot** against the pose's 0.169 /
0.171 / 0.180; regression slope of field-common on pose **0.46/0.64,
0.44/0.75, 0.36/0.25** (x/y per capture — a quarter to three quarters,
median ~0.45); correlation 0.64/0.67/0.64 in x and 0.42/0.72/0.65 in y.
So (iii) applies roughly half of the correction twice. Removing that
by construction — the differential arms (v)/(vi), declared before the
run and outside the pre-registered clause — cuts the
harm by about two thirds (slope +9.55 → **+3.24** pp/dot frozen, +9.27 →
+3.15 refit; refit (vi) recovers 2 of the 5 slots) and never reaches (ii).
Double-counting is an aggravating factor, not the cause.

**What residual magnitude would have been needed?** None. The harm is
proportional to the correction with a POSITIVE slope of ~9.5 pp/dot
(~3.2 pp/dot with the double-count removed) and a zero crossing at the
origin; halving the residual halves the harm, and only zero is harmless.
Passing the bar needed a slope of the opposite sign, which no magnitude
of this residual delivers.

**VERDICT — writer (b) is MEASURED NEGATIVE on this sheet.** The
plane-common part of a certified probe is NOT the covering window's pose
error in any sense the decoder can use: it is self-consistent (the sign
check), it is partly already applied (the field absorbs a quarter to
three quarters of it), and applying the rest moves the sampling away
from what certifies. On this sheet the committed poses are better than
the probes say they are. COMPOSITE-POSE-DESIGN §6 now records that its
(b) row is measured and refused at this evidence tier; §6's own warning
is the
explanation — magnitudes from direct NCC are calibrated to DECODE-OPTIMAL
rather than physical offsets, and the plane-DIFFERENTIAL use of that
number survives the calibration error (it cancels between planes) while
the plane-COMMON use does not.

**Caveats.** One sheet, one engine, one lane; the certificate counts are
tiny (0–5 of 334) because this residue sits at 11–18% cell error against
a gate near 7.6%, so the BER clause is what decided the bar and the
certificate clause is nearly unresolvable at this footing — the frozen
(i)-over-(ii) 3-vs-1 is that noise plus the frozen detector's own
penalty for any change of geometry, and the refit footing (5 for (ii),
nothing lost) is the number to read. Anchors are not collected, so (ii)
is the field from probes alone rather than production's `uF` arm in full.
The refit corrects payload windows only; label rows stay at the arm's
zero. Slot rows pool tile × capture through the union, as everywhere else
here (README caveat 7).

### 2.12 E8 — the NON-ORACLE Y-context loop, at two geometries
*(2026-08-23; `measure/plane_fields/context_loop.py`, artifacts
`scratch/plane-fields/p2/e8/`; the §2.10 E4 follow-up)*

§2.10 priced the Y-context circularity with an ORACLE and licensed
nothing: a receiver cannot know Y's printed bits. E8 asks what a receiver
CAN take — same eight tiles, same three sha-pinned captures, same lane
`l02-8ppc-2400dpi`, seven non-oracle estimates of that one ink column,
run at TWO geometries.

**Footing.** **G1** is E4's, exactly: one refit PER TILE at that tile's
supervised 6-dof affine plus BER polish, the restricted region's
registration, QDA/PAVA stack and A5 bins all recut. **G2** is
PRODUCTION-like: the committed pose plus the field the shipped
`TILE_FRAGMENT` probe pass builds, applied to every payload window
through the `offsets_override` seam the `uF` arm samples at — no
supervision anywhere, and ONE refit per capture serves all eight tiles
because the field is tile-blind. 8,875 s, peak RSS 13.97 GB, one capture
resident at a time; `receiver_tree_sha256` `31b92b3c…` identical at entry
and exit.

Four things the run ASSERTS rather than assumes, all passed: (a) and (b)
at G1 reproduce E4's union cell error on all eight tiles at **max |gap|
0.0** over 16 comparisons; the instrument's lattice rebuild of A5's ink
map at (a) is **bit-identical** to the ladder's own on every refit (or
the run stops); every KNOWN cell's exact bits equal the printed truth;
and G2's field reproduces §2.11's report to every printed digit (rms C
0.41533332 / M 0.35762739 / Y 0.37601003, held-out log-loss 0.753 → 0.615).

#### The configurations, both geometries (`bins` arm, union over 3 captures)

| | dead (sd) | control (sd) | Δdead | Δcontrol | % of oracle d/c | ref Δ | cert d/c |
|---|---|---|---|---|---|---|---|
| **G1 — E1 refit (supervised)** | | | | | | | |
| (a) baseline | 8.744 (1.04) | 6.590 (0.36) | — | — | — | — | 1/2 |
| (b) Y = GT *(oracle)* | 6.317 (0.89) | 4.137 (0.59) | −2.43 | −2.45 | 100 / 100 | −0.01 | **4**/2 |
| (c) C,M = GT *(control)* | 8.744 | 6.590 | **+0.00** | **+0.00** | 0 / 0 | +0.00 | 1/2 |
| (z) Y term OFF *(control)* | 10.501 (0.65) | 8.161 (0.12) | +1.76 | +1.57 | −72 / −64 | +4.61 | 0/0 |
| (e1) 1 iteration | **7.671** (0.92) | **5.018** (0.09) | **−1.07** | **−1.57** | **44 / 64** | −0.01 | 0/2 |
| (e2) 2 iterations | 8.128 (0.77) | 5.998 (0.55) | −0.62 | −0.59 | 25 / 24 | −0.00 | 1/2 |
| (f) self-column removed | 22.938 | 22.422 | +14.19 | +15.83 | −585 / −646 | +17.25 | 0/0 |
| (g) 3-capture consensus | 7.868 (0.88) | 5.181 (0.18) | −0.88 | −1.41 | 36 / 57 | −0.01 | 0/2 |
| (h) soft column | 7.767 (1.01) | 5.181 (0.18) | −0.98 | −1.41 | 40 / 57 | −0.01 | 0/2 |
| **G2 — production-like (field)** | | | | | | | |
| (a) baseline | 10.375 (1.74) | 6.615 (0.68) | — | — | — | — | 0/2 |
| (b) Y = GT *(oracle)* | 7.512 (1.66) | 4.125 (0.78) | −2.86 | −2.49 | 100 / 100 | −0.01 | **3**/2 |
| (c) C,M = GT *(control)* | 10.375 | 6.615 | **+0.00** | **+0.00** | 0 / 0 | +0.00 | 0/2 |
| (z) Y term OFF *(control)* | 11.846 (1.64) | 8.501 (0.04) | +1.47 | +1.89 | −51 / −76 | +4.05 | 0/0 |
| (e1) 1 iteration | **9.318** (1.59) | **5.030** (0.53) | **−1.06** | **−1.58** | **37 / 64** | −0.01 | 0/2 |
| (e2) 2 iterations | 9.872 (1.67) | 5.684 (0.96) | −0.50 | −0.93 | 18 / 37 | −0.01 | 0/2 |
| (f) self-column removed | 23.013 | 21.039 | +12.64 | +14.42 | −441 / −579 | +15.85 | 0/0 |
| (g) 3-capture consensus | 9.478 (1.67) | 5.194 (0.45) | −0.90 | −1.42 | 31 / 57 | −0.01 | 0/2 |
| (h) soft column | 9.335 (1.62) | 5.332 (0.11) | −1.04 | −1.28 | 36 / 52 | −0.01 | 0/2 |

Percent, n = 6 dead / 2 control PHYSICAL tiles (18 / 6 tile × capture
rows through the union). The reference column is the head's unemitted Y
decision on six certified clean-column tiles — 516,176 cells over 24 rows
at G1, 64,522 over 3 at G2 — and is a REGRESSION control: those tiles are
emission-suppressed and can never mint a certificate.

**The pre-registered bar** (written to `e8-bar.json` before the first
capture was opened): ≥ 50 % of the oracle gain at G1 with no reference
regression, OR any dead tile certified at G2. Measured: the best
configuration reaches **44 % (dead) / 64 % (control)** and **no candidate
certifies a single dead tile at G2**. **FAILED on both clauses** — but
failed with a real, reproducible, regression-free partial gain, which is
a different thing from §2.11's failure.

**(1) A third to a half of the loop closes with no truth at all.** One
fixed-point iteration — decode, rebuild Y's ink column from the decoder's
own FINAL decisions, re-decode — is worth **−1.07 pp on the dead tiles
and −1.57 on the controls** at G1 and essentially the same at G2 (−1.06 /
−1.58). The references move −0.01 pp: this is not bought from anywhere.
§2.10's honest prior ("each recovers only a FRACTION") is confirmed, and
the fraction is 44 % / 64 %.

**(2) Iterating again gives half of it back, and it is not converging.**
(e2) drops to 25 % / 24 % at G1 and 18 % / 37 % at G2. The second step is
not a small correction on the first: a → e1 moves **18.5–19.9 %** of the
lattice's Y bins (G1) and e1 → e2 still moves **13.8–15.0 %**; on the ink
itself 4.7–5.1 % then 3.6–3.9 %. Three quarters of the first step's
motion is repeated on the second. Hard message passing on a loopy
neighbourhood graph with no damping, behaving exactly as that predicts.

**(3) The most ACCURATE ink map is not the best decode.** Measured
against the printed field, (e2)'s Y column is the closest of all —
**4.70 % wrong at G1 and 3.01 % at G2, against the baseline's 5.13 % /
3.66 %** — and it decodes WORSE than (e1), whose column is *worse than the
baseline's* at G1 (5.23 %). Column accuracy does not rank the
configurations. What the decoder is sensitive to is the bin, i.e. a SUM
over eight neighbours, and the error structure of that sum is not a
function of the per-cell hit rate.

**(4) The soft column ties the hard one.** (h) carries the IDENTICAL hard
decisions to (e1) — same sign, same 5.23 % / 3.40 % column — and differs
only in that each neighbour contributes its posterior instead of a
committed 0/1. The estimator argument says this should win (the sum of
eight MAP decisions is not the MMSE estimate of their sum). Over eight
tiles it does not: 7.767 vs 7.671 at G1, 9.335 vs 9.318 at G2 — inside
the tile-to-tile spread. *A one-tile smoke had shown (h) at 91–101 % of
the oracle against (e1)'s 63 %; that was outcome selection on tile
(14,9), where (h) does win 6.72 vs 7.07. Recorded because it is exactly
the error the eight-tile set exists to catch.* The bin histogram says
why the ceiling is there: (h) concentrates the lattice MORE than the
oracle does (bin 4 at 29.1 % against the oracle's 27.0 % and the
baseline's 24.6 %) — it over-shrinks. A calibrated (temperature-fitted)
posterior is the obvious unbuilt next rung.

**(5) The consensus is WORSE than each capture's own decision.** (g)
reaches 36 % / 57 % against (e1)'s 44 % / 64 %, at both geometries, on a
consensus built from all three captures' summed post-context Y LLRs
(2.73 M page cells). The ink map has to describe THAT capture's
neighbourhood optics; pooling three captures' decisions makes a better
estimate of the PAGE and a worse descriptor of the capture.

**(6) The two controls do their job, and (f) is the sharp negative.**
(c) reproduces (a) to every digit at both geometries. (z) — Y's bins set
to `-1`, which `apply_states` corrects by exactly zero, so A5's Y
NEIGHBOURHOOD TERM is switched off and C's and M's stand — costs **+1.76
pp dead / +1.57 control and +4.6 pp on the references**. So the shipped Y
term is worth about −1.8 pp and no candidate here is "winning by blunting
it". And (f), Y's bin built from the count of neighbours carrying C-or-M
ink with Y's self-reference removed, lands **on top of (z)** (+1.72 vs
+1.77 pp dead, `bins+head`; +4.55 vs +4.60 on the references): the
non-circular model class carries **no usable information at all**. The
circularity cannot be removed by dropping the self-reference — only by
estimating it better.

**(7) The certificate is not monotone in cell BER.** At G1 the candidates
LOSE the baseline's one dead certificate — (29,8), which (a) wins at 99
LDPC iterations and (h) fails at a *lower* 7.62 % — while (e2), with a
worse mean, keeps it at 39 iterations. At G2 the oracle certifies three
dead tiles ((23,18), (31,15), (34,27)) and every candidate certifies
none. A ~1 pp mean improvement is simply not the ~3 pp these tiles need,
and on the one marginal tile the changed error pattern went the other
way. The controls certify under every configuration at both geometries.

**What this licenses.** Nothing to ship, and one line worth continuing:
the loop is REAL, PARTLY CLOSABLE and REGRESSION-FREE at a third to two
thirds, its damage is in the SUM rather than the per-cell decision, and
the two obvious cheap variants (iterate again, drop the self-column) are
measured dead ends. The unbuilt rung the numbers point at is a CALIBRATED
soft column — (h) with a temperature fitted so the expected count matches
the truth's dispersion instead of over-shrinking past the oracle — plus a
confidence GATE (leave low-|LLR| neighbours at `-1` rather than at 0.5).
Both are one leaf (`color_neighbourhood.provisional_ink` returning an
occupancy instead of a bool; `detect.context_bins` already accepts and
rounds floats), receiver-axis only, no format change.

**Caveats.** One sheet, one engine, one lane. The six dead tiles and two
controls are OUTCOME-SELECTED (they are where the residue is) and the
controls are n = 2 physical tiles; the certified references are not
outcome-selected and are carried for that reason. Rows pool tile ×
capture through the union, and three captures of one physical tile are
not independent — `n_tiles` sits next to `n_rows` everywhere. G1's
geometry is SUPERVISED (a ceiling); G2 changes the SAMPLING only, and
still fits the detector over E1's restricted region rather than
production's whole payload region, which is what keeps G1 and G2 a
one-variable comparison and what stops G2 from being a production run.
G2's field is built from probes alone (no anchors), so it is §2.11's
configuration (ii) rather than the `uF` arm in full, and the refit
corrects payload windows only — label rows stay at the arm's zero.
Configuration (h) makes the ink map soft, not the CORRECTION:
`ContextHead.apply_states` takes `int8` bins, so interpolating A5's
per-bin offsets between integer bins is a detector change this instrument
is forbidden to make, and the expected count is rounded onto A5's own
nine bins instead. Configurations (f) and (h) REDEFINE what a Y bin
means, so `bins+head` is their faithful arm and `bins` is carried only
for continuity with E4's table. The consensus in (g) is built from the
same three captures it is then used on.

### 2.13 E9 — LOCAL vs PAGE-GLOBAL calibration, on the K residue
*(2026-08-23; `measure/calibration/e9_k.py`, artifacts
`scratch/plane-fields/p2/e9/`; the TOOLBOX-INVENTORY §6.13 entry, which
carried no number at all — "named in the brief; there is no E9 in the
record … UNMEASURED")*

**Why this subject.** §2.10 E3′ found the page-global head beating a
per-stratum oracle everywhere except the Y-sibling states — on the
AltaLink, whose toner is uniform. E9's premise is the opposite regime:
uneven toner. e029 is the project's cleanest case of it. The first
physical holo-v1 print, `c2-r0700@3392x2368` on the HP M281 at the
`hp-m281-ink` geometry, one Canon 4800 grey scan, closed **VERIFIED**
(465,580 B) with **1940/1961** tiles, and the e029 log attributes its
**21** residual failures to HP weak-horizontal-line development banding
(the interior row-42 band) plus the two extreme columns. If a local
calibration ever pays, it pays here.

**Footing.** Per ladder lane the instrument re-derives the archived
committed poses through `place.place_committed` (the production R-level
inventory), samples and calibrates through
`payload.collect_capture_evidence`, fits and gates the region context arm
through `_payload_context.apply_region_context`, freezes ownership,
materializes tile blocks and runs `payload.attempt_k_tile` at both K
stages. Nothing is re-implemented; the archived state is opened
read-only and never written, and every attempt is EXTRA beside the
archived one. Two lanes, `l00-2ppc-600dpi` and `l01-4ppc-1200dpi`, the
complete residue (21 of 21), 651 s wall, peak RSS 5.6 GB.

**What the production K head actually is** (read from the tree, since the
brief asked and no doc says it in one place):

| stage | granularity | population |
|---|---|---|
| score transform (`_payload_sampling._scores`) | **per WINDOW** | that window's own median + mean-abs-deviation |
| marginal `pava-v1` (`_calibrate` → `detect.fit_calibration`) | **per WINDOW** | that window's own FORMAT-KNOWN cells, SEARCH half of the `(131y+17x)&1` parity — median **423** labels here (`n_filler = 0`, so BCH word sites only) |
| context `ctx-pava-v1` (`apply_region_context`) | **per REGION** | every window of the region, same format-known labels, adopted only on a strict weighted held-out gain |

Each ladder lane on this capture has exactly ONE region covering the
sheet, so the shipped granularity is **photometry per window,
calibration per window, context page-global** — and neither head has
ever seen a certified payload cell as a label.

**The arms.** Each changes exactly one thing, the marginal head's label
population: `R` = the incumbent recipe; `W` = window-only scope with
certified payload cells added as labels; `H1`/`H2` = the same labels
pooled over a 1- and 2-window-extent halo; `G` = one fit over every
window of the lane. `W` vs `R` isolates *do certified labels help*;
`H1/H2/G` vs `W` isolates *does a WIDER population help*; `G` vs `H2` is
the locality question itself.

**Reproduction control: exact.** Arm R's blocks are **bit-identical to
the archived evidence on every residue tile** — 72,158/72,158 cells at
l00 and 74,664/74,664 at l01 (and, in the prototype, 73,795 at l02 and
78,726 at l03), context offsets included. The truth path is validated
before use: the `page000_gt.npy` sidecar matches
`records.printed_cells_from_record` on all 1940 certificates,
**7,946,240 cells, 0 mismatches**.

#### The arm table, complete residue (21 tiles), both lanes

| arm | labels/fit | halo (windows) | certs l00 | certs l01 | mean ΔBER vs R, l00 | l01 | page cell BER l00 | l01 | CPU/attempt l00 · l01 |
|---|---|---|---|---|---|---|---|---|---|
| R | 423 | 1 | **0** | **0** | — | — | 5.627 % | 2.249 % | 0.74 · 1.02 s |
| W | 19,208 | 1 | **0** | **0** | −0.16 pp | −0.16 pp | 5.311 % | 1.909 % | 0.79 · 1.07 s |
| H1 | 217k / 336k | 15 / 25 | **0** | **0** | −0.79 pp | −1.04 pp | 4.953 % | 1.874 % | 1.26 · 2.08 s |
| H2 | 389k / 561k | 28 / 42 | **0** | **0** | −0.96 pp | −1.09 pp | 4.921 % | 1.859 % | 1.73 · 2.98 s |
| **G** | 3.0M / 4.0M | all | **0** | **0** | **−0.99 pp** | **−1.17 pp** | **4.922 %** | **1.849 %** | 0.79 · 1.10 s |

**ZERO certificates, every arm, both lanes, all 21 tiles.** Under the
box's own bar — *strict superset plus at least one certificate on a
complete residue* — **E9 has not paid.** Cost is not the obstacle: an
arm costs 0.7–3.0 s per attempt and 33–125 s per lane, so
cost-per-certificate is undefined (∞) rather than expensive.

**And the ordering is the interesting part: `G > H2 > H1 > W > R` at both
lanes.** The page-global refit is the best arm — better than every local
one, at a fifth of H2's CPU because it fits once. Locality is not merely
unhelpful, it is the part that costs: going from a 2-window halo to the
whole page is worth another −0.03 / −0.08 pp and saves 40–80 s. §2.10
E3′'s "the page-global head beats the per-stratum alternative" now
reproduces on the K instance, on the uneven-toner engine that was E9's
own best case.

#### The spatial story: the arms miss the band

Mean ΔBER against arm R, by the e029 log's own failure geography:

| group | n | R BER l00 · l01 | ΔW | ΔH1 | ΔH2 | ΔG (l00 / l01) |
|---|---|---|---|---|---|---|
| extreme column 0 | 7 | 17.40 · 14.87 % | −0.45 / −0.18 | −1.79 / −1.94 | −1.85 / −2.07 | **−1.81 / −2.30** |
| extreme column 36 | 4 | 11.17 · 11.89 % | −0.19 / −0.53 | −0.13 / −1.46 | −0.75 / −1.45 | −0.96 / −1.41 |
| **interior row-42 band** | 9 | 15.08 · 11.41 % | +0.10 / +0.01 | −0.19 / −0.20 | −0.30 / −0.24 | **−0.37 / −0.26** |
| interior singleton | 1 | 12.59 · 10.59 % | −0.40 / −0.08 | −1.08 / −0.65 | −1.18 / −0.58 | −1.05 / −0.60 |

The gain concentrates on the **page edges** (−1.8 to −2.3 pp at column 0)
and is nearly absent on the **banding**, which is the dominant residue
(9 of 21 tiles) and the thing E9 was aimed at. A calibration arm helps
where the page is dark at its margin; it does not help where the engine
laid a weak line.

#### The calibration delta — the toner field, made visible in the fit

`t50` is the score at which a window's fitted map crosses P(ink) = 0.5,
i.e. that window's own decision threshold in its own normalized units.

| arm | labels/fit | t50 sd, l00 · l01 | Spearman(Δ vs G, page row) | (page column) |
|---|---|---|---|---|
| R (production) | 423 | **0.1283 · 0.1077** | +0.028 / −0.075 | −0.075 / +0.048 |
| W | 19,208 | 0.0546 · 0.0425 | +0.041 / −0.039 | +0.053 / +0.090 |
| H1 | 217k / 336k | 0.0208 · 0.0152 | +0.040 / −0.190 | +0.450 / +0.028 |
| H2 | 389k / 561k | **0.0186 · 0.0121** | +0.203 / −0.235 | +0.543 / −0.023 |
| G | 3.0M / 4.0M | 0 (one fit) | — | — |

**The shipped per-window threshold scatters ±0.11–0.13 with NO spatial
structure whatsoever** (|Spearman| ≤ 0.08 against either page axis, both
lanes) — it is a 423-label estimate, and its page-to-page variation is
overwhelmingly estimation noise. Give the same windows 900–1300× more
labels and the threshold field collapses to **±0.012–0.019 around the
page-global value**: whatever real spatial variation the decision
threshold has, it is 6–9× smaller than the noise the incumbent fit adds
on top of it. That is the E9 premise measured directly, and it is
inverted — *the per-window head is not tracking a toner field, it is
adding noise about a page-global one.* (H1/H2 pool overlapping windows,
so their scatter is suppressed by shared data as well as by count; the
collapse is an upper bound on the field, not a √n law.)

The residual field that survives at H1/H2 is real but small and is an
EDGE effect, not a band effect: at l00 the heavily-labelled t50 reads
−0.0872 in column 0 against −0.0531 in the interior and −0.0421 in
column 36 (Spearman vs column +0.54), while the row-42 band reads
**−0.0525 against −0.0540 for the rest of the page — a difference of
0.0015, i.e. none.** l01 agrees (band −0.0853 vs rest −0.0836; column 0
−0.0921 vs interior −0.0823). The banding does not move the threshold,
which is why no threshold arm touches it: development banding modulates
the class SEPARATION, not the decision point.

#### What the residue is actually limited by

`k_eff_bits = 2780` of 3996 payload cells. Two tiles at l00 —
(42,6) and (42,7), both at 1998 observed cells — are
`below_attempt_floor` in every arm: no calibration can help a tile the
windows never covered. Two more, (42,3) at 3.60 % and (42,4) at
**2.36 %** cell BER, are attempted and fail with ~900 cells unobserved.
The residue is a mixture of **coverage-bound** and **separation-bound**
tiles; it is not calibration-bound, and the best any arm reaches on a
fully-covered tile is 7.91 % ((42,11), H2, l01) against a gate estimated
near 7.6 % (§2.7).

**One declared deviation.** A `pava-v1` map's LLR bound is
`log(n_fit + 1)`: 6.2 at production's 423 labels, but past
`detect.CTX_LLR_CLAMP = 12` at 10^4–10^6 labels, at which point
`WindowEvidence` refuses the row for any cell with no valid context
neighbourhood (`apply_context_offsets` clamps only the cells it
corrects). The instrument clamps the fitted probability NODES to that
range once, at the fit. It is an exact no-op for arm R — the bit-exact
reproduction proves it — and touches 342–630 nodes in the other arms.

**Caveats.** (1) Two lanes, not four: with the native capture released
after decimation, one lane's peak RSS is 3.2 GB at 2 ppc, 5.2 GB at
4 ppc, **~13 GB at 8 ppc and 31 GB at 16 ppc**, because
`placement.geometry.prepare_region` materializes five region-sized
float32 arrays; the finer lanes were out of this run's memory budget.
The archived per-lane residue BER says l02/l03 are 1–2 pp better than
l01 on most residue tiles, so a finer-lane repeat is the one owed
extension — but it would have to find 2–4 pp, and these arms move 1.
(2) At l00 three residue tiles' archived blocks carry mop-up cells this
reproduction does not ((22,0) +4, (22,36) +2, (42,7) +999 — the m00
level shares l00's evidence lane id); l01 is complete and exact on all
21. (3) One capture, one sheet, one engine: this is an existence
measurement on the residue, not a population claim. (4) The run used
`src/holo` pinned at `e8cd0bb` (content sha `2c57bd82…`) because a
concurrent worker held uncommitted edits in the shared worktree; the
whole detector/payload/placement/format/core path is byte-identical
between `e8cd0bb` and today's HEAD `0a62a8e` (only session/state-codec/
runtime-policy files moved), and the l00 lane was re-run against HEAD's
own tree afterwards and reproduced **every printed digit** of the arm
table plus the bit-exact reproduction control.

**Disposition.** E9, K instance: **MEASURED NEGATIVE as a certificate
tool** — 0 of 21 at two lanes, at 0.7–3.0 s per attempt. It is a
**measured positive as EVIDENCE**: the page-global refit on certified
labels is worth **−0.71 pp (l00) / −0.40 pp (l01) of page-wide cell
error** for one extra fit per lane, and 19 of 20 attemptable residue
tiles improve at l00. It belongs in a toolbox as `E` (evidence-level,
keeps the original attempt), never as `+`, and its name should change:
what pays is DENSE CERTIFIED LABELS (§6.4's mechanism), not LOCALITY.
TOOLBOX-INVENTORY §6.13 is re-priced from this measurement.

### 2.7 Confidence
| claim | confidence |
|---|---|
| the numbers above | ~95% (independently recomputed) |
| Y ink present and placed in dead bands | ~95% (fit-free) |
| Y runs at near-zero margin sheet-wide on this engine/format | ~90% |
| dead bands are not PURELY geometric | ~70% (ceiling is an upper bound; run 2 corroborates through the real pipeline) |
| the anisotropic-context mechanism as a model-class LIMIT | ~95% (read) |
| …as the EXPLANATION of the residual gap | ~60% (untested) |
| mix-compression (Y under M worse than Y on white) | inferred, unmeasured |
| the Y-context circularity is worth ~2.4 pp of cell error | ~95% (§2.10 E4: measured through the certificate gate, method control exact) |
| …and is NOT band-specific (closes 0 of the 2.15 pp) | ~90% (n = 2 control tiles is the weak leg) |
| the QDA's Y classes are well-fed on a 94%-certified sheet | ~99% (n_k is a count, not an estimate) |
| blur split toner-scatter vs scanner blue optics | unmeasured |
| r0550-class gate ≈ 11–12% | *estimate* from the r0700 gate + capacity ratio |
| local calibration wins 0 of 21 K residue tiles (§2.13) | ~95% (complete residue, two lanes, reproduction bit-exact) |
| page-global ≥ every local scope on this page | ~90% (two lanes agree; one sheet) |
| the shipped per-window threshold is mostly estimation noise | ~85% (the H1/H2 collapse is an upper bound on the field, not a √n proof) |
| …and the row-42 banding is not a threshold effect at all | ~90% (0.0015 in t50, both lanes, and the arms' smallest ΔBER group) |

---

## 3. Conclusions

1. **Y is a zero-margin plane on this engine at r0700.** Raw per-cell
   Y error is 16–18% everywhere; context + 3-capture union reach ~8%;
   the gate is ~7.6%. "Healthy" Y columns clear the bar by a fraction
   of a point. Dead bands are where two extra impairments spend margin
   that never existed.
2. **Dead bands = geometry (~half) + frozen-fit artifact (~a quarter
   of the rest) + 2.15 pp UNATTRIBUTED.** Registration is worth
   19.6% → 10.0%; a refit at the corrected geometry closes one dead tile
   (29,8) under supervision and ~1 pp on the others; what remains is
   NOT ink absence, NOT context anisotropy and NOT mix compression —
   both of those are present at full strength on tiles that certify
   (§2.8) — **and NOT the Y-context circularity either**: E4 (§2.10)
   handed A5's ink map Y's printed bits and the gap went 2.155 → 2.180.
   Four mechanisms have now been offered the 2.15 pp and all four are
   sheet-wide. **The residue has no band-specific explanation yet**, and
   the next candidate should be sought among quantities that are
   themselves band-structured (the Y-plane registration SINUSOID's
   second-order effects: per-cell sampling-phase variation inside a
   tile, and the ink-side asymmetry a 0.6–0.75 dot offset leaves after
   the offset itself is corrected).
3. **The per-plane field should be translation-only; everything
   affine belongs to the window pose.** The Jacobian is plane-common
   (×11). "Extend the field to 6 dof" is off the list; "refine the
   shared pose per window" is on it (the corner certificate).
4. **More resolution does not fill the bands** (4800 capture: +90
   certificates, first Y adoption, bands persist). Same-footing repeat
   scans are print-frozen; footing UPGRADES still pay.
5. **The field pays, but as a payload-lane bolt-on it reaches too
   little**: one seam, one lane (uF), per (capture, lane), rebuilt from
   zero each time, blind to addressing, starved by the pool law where
   the sheet is best (solved tiles ⇒ label-only ⇒ no anchors; probes
   budgeted at 256 sites).
6. **The format prices three planes equally against an unequal
   channel.** Per-plane rate allocation is the root-level lever; the
   pooled fountain already absorbs Y losses for CORRECTNESS (sheet I
   closed with 244 open slots) — tile-level Y resurrection is a
   capacity/margin question.
7. **Discovery had both facts and did not say them** (§4.I).
8. **Mix compression is a sheet-wide PHYSICAL fact, already modelled:**
   Y-under-M keeps 0.51–0.56× its on-white separation everywhere, and
   the production head (8-state full-covariance QDA) already carries a
   class per state. E3's "4–5 pp" was measured against a single-
   threshold baseline production does not use — RETRACTED as a lever
   claim; the per-state production-vs-oracle gap is the open number (E3′).
9. **Y's weakness on the AltaLink is CONTRAST and CROSSTALK, not blur
   (corrected by E6, 2026-08-23):** blue is the Canon's sharpest
   channel (σ_B 0.94 × σ_G, offset ≤0.04 dot) AND the AltaLink's Y ink
   is as sharp as K/C/M (34.8 vs 36.8–37.7 µm); the e028 "broad Y" was
   the M281's depleted cartridge (46.0 µm, with thin faint lines).
   Sheet I's Y d′ 1.8 is yellow's weak blue-channel absorption plus M
   crosstalk — the mix compression the QDA already carries (0.52× from
   its own means). ISI equalization is therefore NOT a lever on this
   engine; the printer frame's photometric sibling is demoted to
   "measure per engine" (W11 item 3). The M281 additionally carries a
   −1.7-dot process-direction Y offset from K (a second e030 mechanism).
10. **Process:** the plane-fields campaign assumed dead-Y was a
   registration problem and built before measuring what binds. The
   pilot-before-wave order caught it cheaply the second time; keep that
   order.

---

## 4. Avenues, with + / −

### A. The sheet-level field service (first-class, not bolt-on)
**2026-09-08 — §4.A is SUPERSEDED by `docs/PAGE-FIELD-DESIGN.md`**, which
is the design of record for the field and is BUILT in the receiver on
branch `page-field-receiver` (commits `4d89686f` (W1) through the W9 landing of 2026-09-12 — `4d89686f^..page-field-receiver`, W1–W9 — merged to main 2026-09-12).
Two of this avenue's premises did not survive: the identity is per
PRINTED FACE, not per sheet (sheet J's two duplex faces measured
different fields inside one capture), and "many writers of differing
quality" is now three attributed evidence TIERS pooled by weighted
median — lane fits and addressing residuals are deleted, not ranked.
The rest of the avenue landed as written: one object, many readers, all
of them through one mapping (`lib/page_map`). The measured argument
below stays as the record.

One per-plane TRANSLATION field per sheet in print-dot tile space, with
many writers (every lane of every capture; word/dust anchors; certified
probes; addressing residuals; successful closer offsets) and many
readers (payload sampling, word reading, cold search, per-lane residue
passes, diag). Three frames: sheet differential (print-frozen) /
capture pose / lane decimation.
- + every other avenue below plugs into it once instead of re-plumbing
  the seam; + cross-rung and cross-capture hinting fall out (the
  posterior already accepts a prior mean); + kills the default-flip
  proof (see B).
- − a holo1 retrofit cuts across payload sampling, addressing, cascade,
  state and diag — the sprawl the kiss cleanup removed; − holo2 has no
  colour yet. **WHERE is a ruling** (§6 P3): design holo2-shaped, build
  a thin measured instance in holo1 (landing-zone doctrine), port as
  doctrine. Holo2 was retired 2026-09-05 without ever gaining colour or
  this port.

**A.2 — plane-aware addressing (the address/payload disparity).**
Today the field enters ONE seam (payload sampling); word decode, word
validation, placement refinement, the correlation lane and cold search
all sample plane-blind, and address-stage word solves DISCARD the fine
offsets they measure.
- + on thin footings (4 px/cell 1200 dpi), scraps and worse engines the
  d = 27 word margin shrinks and per-channel word reads at per-plane
  offsets (the R3 addressing-rescue thrust) become load-bearing; + the
  reverse flow (addressing residuals → field) is free evidence.
- − near-zero payoff on sheet I (words W/CM, Y-white; C/M differential
  0.1–0.3 dot; 99.8% word footprint even on the failed cmy7 sheet).
  Design-coherence now; a yield item only in marginal regimes.

### B. Per-lane supplemental field pass (the §6.2a schedule law)
Vanilla lane → refresh field → field-corrected pass over that lane's
residue → next lane.
- + monotone by construction (certificate gate only adds) — W6's band-3
  regression cannot recur, the strict-superset proof becomes
  bookkeeping; + cost ∝ residue; + the closer (C) is one more arm in
  the same pass.
- − lane 1 has no certificates (thin field) — start from lane 2 or seed
  from the sheet field; − more field reports per capture (diag).
- **B.2 adoption granularity** (per-block / per-region-and-plane, not
  per-page) is RETAINED as a yield item: B makes a misfit harmless, it
  does not make it useful — band 3 still wants the correction applied
  where it is right and withheld where it is not.
- **Rule (agreed 2026-08-22): no further yield work on the bolt-on.**
  B, C, G are built on A, not on the payload-lane arm.

### C. The closer: translation-only, hint-seeded swim (charter RE-SCOPED)
- + mechanism proven (controls certify at 0.25-dot precision); + ~4 s
  per tile hint-seeded; + harvests the just-outside-window tail the
  adoption granularity misses; + its wins are tier-(i) evidence.
- − it does NOT reach the dead bands (§2.3/2.4). DROPPED from the
  ratified charter: the 6-dof per-plane search (plane-common Jacobian ⇒
  modelling noise) and the ≤5/53 bar (unreachable by any geometry).
  New bar: strict superset + measured yield.

### D. Per-window pose refinement (plane-common affine)
- + the corner tile's certificate (11.95% → 4.97%) came only from this;
  + it is a `certified_refine` bounds/model question in the placement
  layer, not field work.
- − value concentrated where the shared pose extrapolates (page edges,
  stitched windows); small population.
- **The CERTIFIED-PROBE route into D is a measured negative (§2.11).**
  Feeding a window the plane-common part of its own certified probes
  costs 5 of 5 certificates and +2.1 pp of cell BER, and the harm scales
  with the correction (+9.3 pp per dot). What survives is D's original
  form: a pose improvement selected by a DECODE-gated objective
  (`certified_refine`), never by an NCC residual.

### E. The detector line (where the dead-band residue now lives)
In order: (1) refit with bins recut at the corrected pose on dead
tiles (after fixing the instrument's A0-arm no-op) — settles how much of
the gap is frozen-fit artifact; (2) directional-neighbour stratification
of the Y residual — settles the anisotropic-crosstalk mechanism (pure
re-analysis); (3) per-state Y contrast table from the calibrated heads
— settles mix-compression; then, as indicted: (4) context-conditional
LLR attenuation / erasure treatment (PAVA cannot; the detector KNOWS
which cells are unreliable; LDPC prefers erasures to confident errors);
(5) an anisotropic context model; (6) ISI equalization over the 2–3-cell
blur support.
- MEASURED 2026-08-22 (§2.8): (1) is worth ~1 pp on dead tiles (and
  one supervised certificate); (2)'s mechanism is real but sheet-wide
  (~1 pp); (3) confirms mix compression, sheet-wide — but against a
  single-threshold baseline the 8-state QDA already beats (§2.8
  correction); (4)/(5)'s value vs PRODUCTION is unmeasured.
- MEASURED 2026-08-23 (§2.10): E3′ prices the head against a per-(C, M)
  oracle — it WINS at every band except the three Y-inked-with-a-sibling
  states, where a stratum-exact correction is worth −1.68 pp (dead) /
  −1.13 (control) per capture, arithmetic. E4 prices the Y-context
  CIRCULARITY at **−2.43 pp on the dead tiles and three of six flipped
  to certified** — the largest detector-side number this campaign has,
  and SHEET-WIDE (controls −2.45). This is where the detector line's
  prize actually is, and it is item (4)'s neighbourhood: the ink map,
  not the LLR. The realizable versions — confidence-gated ink map, one
  fixed-point iteration, certificates-only ink map — are unbuilt and
  unmeasured, and each recovers only a fraction by construction.
- MEASURED 2026-08-23 (§2.12): E8 built and priced the realizable
  versions. **One fixed-point iteration is worth −1.07 pp dead / −1.57
  control = 44 % / 64 % of the oracle**, regression-free, and the same at
  the PRODUCTION-like geometry (−1.06 / −1.58). It fails the
  pre-registered 50 % bar and certifies no dead tile at G2. Iterating
  twice gives half of it back and does not converge; the three-capture
  consensus is worse than each capture's own decision; a SOFT column ties
  the hard one; and Y's self-column cannot be dropped — a bin built from
  C-or-M neighbours is worth exactly as much as switching A5's Y term
  OFF, i.e. +1.7 pp. The unbuilt rung is a CALIBRATED soft column plus a
  confidence gate, one leaf, receiver axis only.
- + (1)–(3) cost no toner and no new state; + (4) is cheap and aligned
  with the bounded-LLR invariant.
- − (5)/(6) are detector model-class changes with their own
  qualification; − magnitude of the prize is exactly what (1)–(3)
  measure.

### F. Comb (tier-iii) — DEMOTED
- + still the only evidence in genuinely evidence-free regimes: column
  8, small scraps.
- − its charter role (registration evidence for dead bands) is
  obsolete: dead-band registration is measurable today (neighbour
  estimator r ≥ 0.9) and registration alone does not close them. A
  scrap-recovery feature, behind E.

### G. Certified tiles as calibration furniture
- + exact ground truth, cheap NCC, feeds pose AND field; + fixes the
  solved-tile starvation; + prerequisite for B to be strong early and
  for new captures over done regions (which otherwise produce no
  attempts, no anchors, no probes).
- Concretely: probe fully-certified tiles inside MIXED windows (the
  per-tile refuse-partial rule stays); NO BUDGET — the 256-site cap is
  deleted (ruling 2026-08-22: "we don't do ceilings here. if the
  ceiling reduces yield, it's wrong. if having no ceiling does not
  increase yield, then maybe we should not do the thing at all");
  a certified-re-encode probe grid per new capture over done regions.
- **MIXED WINDOWS DONE 2026-08-23** (§2.9b): `color_payload` offers
  every window to the pass. +603 certified tiles, coverage 0.813 →
  0.997, Spearman +0.9265 → +0.9711, per-tile MAD 0.217 → 0.163, and M
  across the adoption cliff — for 3.5 s. This was the biggest single
  item on the list and it was one moved statement.
- − probe cost grows with the done fraction (0.60 ms/probe measured at
  the shipped density, 6.9 s for a full page at one capture and lane
  over ALL windows; §2.9b) — and the pass must now justify itself by
  MEASURED YIELD (field quality with vs without probes; certificates at
  the P5 bar), or be removed.
- DENSITY ruled by measurement 2026-08-22 (§2.9) and RE-ruled 2026-08-23
  (§2.9b): one 5×5 block per field bin STAYS. The template's width is a
  reach constraint only for a SQUARE template that must fit inside one
  window; the tile-centric `TILE_FRAGMENT` has no such constraint and
  reaches every certified tile at whole-tile-class per-probe precision.
  The field does not want it (reach-limited, not precision-limited); a
  POSE writer will (§2.9b's plane-common table: 46% of windows
  self-consistent at a whole tile, 9% at 5×5). Default FLIPPED to
  `TILE_FRAGMENT` 2026-08-23 (§2.9c) for that pose half — and **§2.11
  then measured the pose half itself and refused it**. The flip's field
  half still ties, so the shipped density stands on the tie plus the
  cross-capture pooling case, not on the pose writer any more.

### H. Format-side Y pricing
- **Per-plane LDPC rungs** (Y r0550, C/M r0700): + same lattice, words,
  tile grid; + ~7% page capacity for ~4 pp Y margin (*estimate*);
  − blocked by the gen-v1 width-class law (width-heterogeneous generator
  needed — RULED + BUILT 2026-09-04: the column-group pool,
  docs/CMY8-COLUMN-GROUPS.md, built with Y at r0547 (the same width as
  r0550), `c2-cmy8-r0700x0700x0547@53x37` pinned by goldens, not
  printed); − needs registration
  correction alongside (uncorrected 17–20%
  exceeds even r0550).
- **Fountain quota skew toward Y**: + no LDPC change; − the quota law is
  UNIFORM BY CONSTRUCTION (`quota_b(p,s) = T//B + rotation`, so page
  loss degrades proportionally) — a fountain-law fork, not a knob.
- **CMY word states**: + Y addressing evidence and Y anchors at word
  sites (today Y-white ⇒ Y unmeasurable at words); − M281 re-screen
  risk (toner-confounded numbers); one-patch test next print day.
- **Y at c3 (mixed pitch)**: DOMINATED — 56% of Y's cells lost before
  coding (~19% of page capacity) plus lattice/addressing/esi surgery,
  vs ~7% for a rung step. Uniform c3-cmy8 already exists for the
  rocksolid end.

### I. Discovery / characterize (CHARACTERIZE-WORKPLAN W11, noted)
- Unpool the planes in colour candidate tiers (cmy8-c2's pooled 12.17%
  contained Y ≈ 17% / C ≈ 5% and did not say it — verdict-layer change).
- A full-page per-plane registration track on discovery sheets (R3
  permits fiducials there) — would have measured the sinusoid on the
  first AltaLink pair.
- Blue-channel scanner characterization — DONE 2026-08-22 (§2.8,
  `measure/scanner/`): B sharpest, CA ≤0.04 dot; Y softness is toner-
  side. Third W11 item that follows: per-INK PSF/σ from the K-edge
  channel-ratio method on every discovery sheet (Y 51 > K 46 > C 43 >
  M 25 µm on the M281 sheet, consumable-confounded; replicate on e031).

### J. K instance — NOT NOW
No measured K failure is registration-shaped (e029: development
banding + extreme columns); K has no crosstalk, no pooling pathology,
d′ far from any cliff; the plane-generic code already runs n = 1
bit-identically. Revisit on a K sheet with pose-shaped residue; cheap
insurance = one read-only field-enabled pass over archived e029 scans.

### K. Not pursued
Sample-level multi-capture fusion (print-frozen floor caps the gain at
the scan-noise share; the union has most of it); 6-dof per-plane
anything; comb as critical path; "more scans" as a Y strategy.

### L. Dispositions of the previous owed list (PLANE-FIELDS §6.4/§6.5)
| item | disposition |
|---|---|
| V1 comb | demoted → F (scraps / evidence-free zones) |
| per-block adoption | retained → B.2 |
| `--plane-fields` flag → default flip w/ superset proof | subsumed by B (superset by construction); the flag itself is a CLI nicety, low |
| full swim (6-dof per-plane, ≤5/53 bar) | re-scoped → C; 6-dof and the bar DROPPED |
| likelihood surrogate choice (charter) | MOOT for a decode-gated, hint-seeded 1-D closer (~13–17 candidates); the pilot's mean-\|LLR\| surrogate measured unfaithful (rails at the grid edge, peaks past the certified band) |
| cross-capture pooling / three-frame factorization | absorbed → A (the sheet field IS the pooling) |
| same-tree dial-off control | EXPIRED — merge done; run 2 + the ceiling corroborate independently |
| shrinkage-target fix | CONFIRMED (review) → P1 |
| V5 (sheet H + 4800) | 4800: done via run 2 (not the registered fresh run, §2.2); H: running, §7 |
| K instance (§3b) | deferred → J |
| CA calibration (Canon R−G) | folded into I.3 (per-channel scanner characterization, B channel first) |
| blind-EM dust-calibration test | unchanged, low — dust is a hint (§2.3), calibration bootstrap role stands |
| per-leg adoption Details | subsumed by per-plane visibility (P1) |
| CMY-words one-patch test | retained → H / P6 |
| RECEIVE-DESIGN amendment | landed at merge (v0.57 §9b); A will need its own |

---

## 5. What works / what doesn't

| works (measured) | doesn't (measured) |
|---|---|
| blind field reproduces the sinusoid where evidence exists (V0) | field fills dead bands (W6, run 2) |
| per-plane translation flips fail → certificate (controls) | any translation certifies a dead-band tile |
| neighbour-derived offsets land inside the certified band (ratio 0.93, SE ~0.15 dot — attenuated, not proven unbiased) | direct NCC as a correction magnitude (×1.5–2.3 overshoot) |
| Jacobian wins page-corner tiles via the SHARED pose | per-plane Jacobian (plane-common ×11) |
| footing upgrade 8 → 16 px/cell (+90, first Y adoption) | more same-footing scans (print-frozen) |
| pooled fountain closes with 244 open Y slots | Y at r0700 with margin (d′ 1.8 vs gate) |
| certified probes as field evidence (W4) | …past 256 sites, or inside mixed windows |
| pilot-before-wave (caught an unreachable bar for hours of compute) | charter-before-measurement (the ≤5/53 bar) |
| dense certified labels as calibration evidence (−0.4 to −0.7 pp page-wide, one fit) | LOCAL calibration (0/21 certificates; page-global is the best arm) |

---

## 6. Action items — priority order (staged)

**P0 — record.** This document; PLANE-FIELDS.md pointer (done with
this commit); memory. DONE.

**P1 — DONE 2026-08-22 on `independent-planes`** (§2.8). Was:
shrinkage target (shrink-to-zero / leave-one-out / drop cross-plane
pooling — pick by the Y-adoption flip test: adding captures must grow Y
arrows, not shrink them); uncovered-plane inheritance (natural zero per
plane); the dead F status fold; `done_tiles` to all fully-certified
tiles + page-aware; the stale shell test; the E-band legend and the anisotropic arrow cap;
**per-plane certificate/residue splits in the epilogue and the
six-row stats** (cheap, and every Y-vs-C question this week needed a
multi-GB state load without it); the instrument's A0-arm refit no-op
and control-certificate leak (prerequisites for P2).

**P2 — DONE 2026-08-22** (§2.8; H still running). Was:
E(1) recut-bins refit on the six dead tiles; E(2) directional
stratification; E(3) per-state Y contrast; I(3) blue-channel MTF from
existing scans; READ the H run against §7. Output: how much of the
dead-band residue the field service can claim vs the detector line —
this decides whether the context model is inside A's scope.

**P2b — new cheap discriminators from P2's residue**: **E3′ DONE
2026-08-23 (§2.10) — the per-state production-vs-oracle table: the
thin-label premise is FALSIFIED (n_k 117k–138k per state, a_k 3.6–4.3e-05,
the shrinkage term inert; the certified-payload population feeds every
Y-bearing class), the A3 gate does NOT fail preferentially in dead bands
(it adopts there 34–45 % against 11–26 % clean), and the head sits BELOW
the per-stratum oracle at every band except in the three
Y-inked-with-a-sibling states, which carry 58.8 % of the dead tiles'
errors on 37.5 % of their cells and are present on the controls at half
strength**; **E4 DONE 2026-08-23 (§2.10) — the Y-context circularity is
REAL and LARGE (−2.43 pp dead, three of six dead tiles flip to
CERTIFIED) but SHEET-WIDE: it moves the controls −2.45 pp, so it closes
NONE of the 2.15 pp dead-vs-control gap, which survives intact. The
method control (C,M = GT) is exact to every digit. Follow-up, unbuilt:
confidence-gated ink map / one fixed-point iteration / certificates-only
ink map**; **E8 DONE 2026-08-23 (§2.12) — the NON-oracle loop, nine
configurations at BOTH the supervised and the production-like geometry,
(a)/(b) reproducing E4 at max |gap| 0.0: ONE fixed-point iteration
closes 44 % (dead) / 64 % (control) of the oracle with no reference
regression and holds at the field geometry, but FAILS the pre-registered
50 %-or-a-G2-certificate bar. Second iteration halves the gain and does
not converge; consensus over three captures is worse than each capture's
own decision; a soft (posterior-weighted) column ties the hard one and
over-shrinks past the oracle; dropping Y's self-column is worth exactly
as much as switching A5's Y term off (+1.7 pp). Unbuilt rung: a
CALIBRATED soft column plus a confidence gate**; **E5 DONE 2026-08-22 (§2.9) — the density ruling is
measured: block-per-bin stays, whole-tile is 3× more precise per probe
but reaches half the sheet, every-block buys nothing**; **E5b DONE
2026-08-23 (§2.9b) — the reach half of that was the LABEL-ONLY
predicate, not the template: offering the pass every window buys +603
tiles, MAD 0.217 → 0.163 and full C,M,Y adoption for 3.5 s;
`TILE_FRAGMENT` built and measured, default unchanged**; **E5c DONE
2026-08-23 (§2.9c) — the ruling flips the default TO `TILE_FRAGMENT`
(one measurement serving field AND pose feedback), with its three-layer
pose regression, and the rectified NCC's search becomes FFT correlation:
the shipped density costs 10.53 → 3.86 ms/probe, 121 → 44 s per
(capture, lane), field and pose outputs within 3.4e-15 dot**; **E7 DONE
2026-08-23 (§2.11) — the P5 bar for COMPOSITE-POSE-DESIGN §6 writer (b),
run over all 334 open slots on both a frozen and an E1-refit footing:
MEASURED NEGATIVE, −5 certificates and +2.1 pp cell BER, harm linear in
the correction at +9.3 pp/dot and worst where the writer's own sites
agree; the field already absorbs a quarter to three quarters of the
plane-common residual, and removing that double-count cuts the harm by
two thirds without reaching the baseline**; E6 replicate the per-ink PSF
on the AltaLink e031 sheet.
All no-toner.

**P3 — rulings** (yours): WHERE to build A — **RULED 2026-08-22: the
composite-pose unification executes in src/holo as a null-proof
refactor; holo2 takes the concept as doctrine (docs/COMPOSITE-POSE-
DESIGN.md §8)** — holo2 was retired 2026-09-05 without doing so; Y
pricing (per-plane rungs vs quota fork vs
CMY words — or accept fountain absorption at lower q); policy-id
archive compatibility (every arm change orphans archived colour states)
— **BOTH HALVES DONE 2026-08-23.** *Plan half* (ruling "do the prefix
repair"): an archived plan that is an exact prefix of today's now loads
and resumes into exactly the appended lanes (RECEIVE-DESIGN v0.58 §8;
measured read-only over the whole archive — all 16 states load, every
colour one a prefix of 1 lane (PK-FINAL) or 3–4 (pre-campaign), sheet I
included). *Id half* (ruling "unlock that gate"): a state minted under
an older receiver policy no longer refuses — `policy_detach`
DERIVES the continuation (RECEIVE-DESIGN v0.59 §9c). The policy id's
five readable components make the change classifiable, so the detach is
per segment, not wholesale: certificates and captures always kept
(gate-verified against the FORMAT, never against a policy), regions and
word-validated poses kept unless their own segment moved, a moved
`payload` segment drops the evidence pools, a moved `address` segment
drops the search state (and clears the ids the retained artifacts
named), close/counters/BCH-quarantine kept — a quarantine is a REFUSAL,
and "when in doubt, drop" governs yield, never refusals. The previous
id lands in `SessionState.policy_lineage` (schema 26, wall-clock free;
schema 25 lifts through one additive migration, because orphaning the
archive to record that it is not orphaned would defeat the ruling), and
one `PolicyDetachWarning` + `session.policy_detach` event announce it.
Refused and named: a moved `survey` segment (its region ledger is named
by every retained level artifact) and any non-kiss-v1 id. **No flag** —
the behaviour is ruled. This is what makes P5's bar ("strict superset +
measured yield on archived sheet I") reachable at all: the A refactor
bumps the `address` segment, which is now a detachable change instead of
an orphaning one.

**P4 — design doc for A** — **OPENED 2026-08-22: docs/COMPOSITE-POSE-
DESIGN.md v0.1** (user design: printer field ∘ paper pose ∘ scanner
field; invariance classes = pooling rules; identifiability table;
residual attribution; identity-first null-proof build plan; seam
inventory appendix). B, G, C, D, A.2 are consumers built on it.

**P5 — build**, after P2 informs scope: A → B → G → C → D, each with
the pre-registered bar "strict superset + measured yield on archived
sheet I", per-plane residue in the epilogue/diag as the instrument.

**Build discipline for P5** (the review's confirmed systemic patterns,
stated once so they are not repeated): validate approximations on the
subpopulation they STRESS, not the one where they are benign (the refit
spot-check landed only on controls; null_proof short-circuited on A0
captures); fix the CLASS, not the observed instance (FieldStats fixed,
field_view left broken; `done_tiles` fixed one black tile); optimize
the DECISION metric, not a proxy (NCC vs certification — the charter's
own lesson, unapplied to its instrument); pin contracts from the
PRODUCER (the Details-vehicle bug); compare matched groups, not
outcome-selected ones; count physical tiles, not tile×capture rows.

**P6 — print-day items**: CMY-words one-patch; the physical holdout
epoch (colour-uplift); W11 discovery sheets on the AltaLink.

Housekeeping outside this line: push (main is 36+ ahead of origin);
fossil sunset; corpus re-decode sweep.

---

## 7. Pre-registered prediction — sheet H (r0850, 7 captures, running)

Stated before either of us reads the result. H's gate is tighter than
I's (r0850 vs r0700; *estimate* ~4.5–5% vs 7.6%). Clean-column Y on
this engine reaches ~8% after everything. Therefore: **Y fails broadly
on H even in clean columns; C and M mostly hold; the close depends on
whether the fountain's uniform quota tolerates a near-dead Y stream at
q = 0.9.** Secondary: the 1200 dpi captures (4 px/cell) contribute
little or nothing to Y. If H returns healthy Y, §3.1 is wrong somewhere
important and P2 must find where before P4.

**SCORED 2026-08-23 — PREDICTION CONFIRMED.** Sheet H, first decode
(one 2400 dpi capture, `--refine --no-close`, main at the P1 merge;
state H-multi-pf, capture 68c16fcb…, done at the uF lane): certificates
**4,092 / 5,883 — C 1,663/1,961 (85%), M 1,891/1,961 (96%), Y
538/1,961 (27%)**; 1,791 LDPC failures. Y fails broadly; C and M hold.
Sheet I's single-capture run 1 reached 5,164 total. CAVEATS: one
capture, one footing, first read; the per-column pattern (bands vs
uniform) and the close are unread; a fresh decode on post-E5c main
(TILE_FRAGMENT, all windows, natural-zero shrinkage) is the next data
point. The zero-margin analysis (§3.1) survives its first out-of-sample
test: at r0850 Y is not marginal, it is mostly gone.

---

## 8. Open questions

- Run 2's 37.8% mop-up winner-flip canary — expected for a 16 px/cell
  view re-observing 8 px/cell commitments, or a misplacement? Unread.
- How much of "Y is soft" is yellow toner scatter vs the Canon's blue
  channel (I.3 answers this from existing scans).
- Whether the field should carry a per-ENGINE prior (the AltaLink
  sinusoid may be a transport property with stable period) — only after
  W11.2 measures a second sheet's phase.
- Whether the anchor magnitudes should be calibrated to decode-optimal
  rather than physical offsets (the NCC overshoot finding) — a cheap
  regression on the existing pilot artifacts would answer it.
