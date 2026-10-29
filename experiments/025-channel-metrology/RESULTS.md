# E025 results

## Forward layout-v2 synthetic preflight

The live E025 pages were rendered through Ghostscript at 600 dpi and analyzed
through the same public commands intended for physical scans.

### Monochrome page

- one page;
- 51 deterministic channel fields;
- 136 typed physical probes;
- approximately 4.5 MB PostScript;
- four full-width K profiles and one feed-direction K profile share space with
  five position-permuted tone-response strips;
- the K tone model was full-rank with zero monotonic violations; maximum
  authored profile span was below 0.0004 coverage;
- all matched C2 solid/diagonal/horizontal/vertical motif and C1xC2/C2xC1
  aspect fields recovered exactly;
- both K C2 LDPC coupons (`r0550`, `r0775`) recovered exactly;
- C2/C3/C4/C6 clean-render fields had zero held-out error;
- C1 at one scan pixel per authored dot showed the intended sampling stress;
- a payload-safe rectangle was derived from edge canaries rather than assumed.

### Color page

- one page;
- 47 deterministic channel fields;
- 200 typed physical probes;
- approximately 14.6 MB PostScript;
- top-solid and bottom-mid-tone full-width K/Y/M/C profiles, paired response
  strips, and four feed-direction profiles were all analyzed;
- all ten paper witnesses and all nine K/C/M/Y registration stations resolved;
- synthetic relative plane registration measured 0.012 mm RMS and 0.017 mm
  maximum (render/sampling floor, not a hardware claim);
- all four tone models were full-rank with zero monotonic violations;
- both KCMY4 one-hot C2 fields recovered at full two-bit mutual information;
- both print-time strips independently CRC-decoded;
- all C2 CMY8 edge canaries recovered cleanly after full-period local phase
  refinement;
- all 18 per-level coupon words across `r0550`, `r0700`, and `r0775`
  recovered exactly;
- the clean synthetic payload-safe rectangle measured 209×296 mm;
- every typed morphology/frequency probe was resolved;
- the sequential CMY8 OPM arm failed badly under Ghostscript while the exact
  DeviceCMYK-image arm passed, validating emission path as candidate identity.

The earlier analyzer pass bounded local phase to ±0.24 cell, inherited from an
older central-field assumption. Bottom/right color canaries then showed
nonmonotonic clean-render errors and could not bracket the page. This was not
paper clipping: the phase estimates sat on the search boundary. E025 now
searches/refines over almost a full cell period. The canaries then recover
cleanly. This dead end is retained because edge fields are exactly where a
global corner affine is least entitled to dictate lattice phase.

Full-page color content also defeated global-threshold machine-strip discovery
on a 300-dpi registration thumbnail. Registration-guided local strip crops at
an independently bounded 600-dpi working scale now decode both placements and
remain memory-safe for 4800-dpi source scans.

### Automated verification

- `tests/test_e025.py`: 10 passed;
- `tests/test_metrology.py tests/test_e025.py`: 14 passed;
- every new physical target is asserted through its analyzer output;
- motif/aspect/constellation fields use the normal held-out QDA path rather
  than a visual-only test;
- direct Ghostscript proofs and one-page A4 PDF conversion pass for both jobs.
- current repository validation at the 2026-07-17 wrap-up collected 659
  tests.  The sandboxed full run reported 652 passed, 1 skipped, and six
  diagnostic-web tests denied permission to bind ephemeral localhost ports;
  those exact six passed when rerun with loopback permission.  The earlier
  stale E023c qualification/fingerprint failures are resolved.

`py_compile` and `git diff --check` pass.

## Physical status

The first forward layout-v2 pair was sent to the home HP Color LaserJet Pro
MFP M281fdw (`<host>`) on 2026-07-17 at 14:35 CEST. Both transfers used
the verified raw PostScript path, TCP port 9100, as separate one-page jobs:

| physical copy ID | kind | bundle | requested grid | PostScript SHA-256 |
|---|---|---|---|---|
| `e025-m281-20260717-bw-01` | K-only | `6c72e2abb746` | 600x600 | `185068666b120442cb97463bae56496f4e15353e18fc8f1105305b7c67d90fbb` |
| `e025-m281-20260717-color-01` | color | `568b4e0c9ab5` | 600x600 | `b5d6a4f6e65b60b2e5da2d3912dec95187c57de8bb4847bd82e8dee163bfefd3` |

The artifacts were regenerated from the committed layout-v2 emitter and
preflighted as one A4 page each immediately before transmission. The loaded
stock was user-supplied A4; exact weight/brand and consumable levels were not
recorded and must remain `unknown/current` rather than inferred. Print-time
device readback is carried by both machine strips.

The Canon reference captures are:

| physical copy ID | capture | mode | raster | capture SHA-256 |
|---|---|---|---|---|
| `e025-m281-20260717-bw-01` | `e025-hp-canon-4800-grey-page-1.tiff` | 4800-dpi 8-bit grey | 40832x56128 | `4fdd6f2663221625d5954f659e792f111c4729d2ecf3c8af546bf6f9d8c06c22` |
| `e025-m281-20260717-color-01` | `e025-hp-canon-4800-color-page-2.tiff` | 4800-dpi 8-bit RGB | 40832x56128 | `4b82a52ab1809c8c4a5ef37895fdd62b7870a78bba51f863bcb878de839b9b2e` |

Both captures are uncompressed, full-page, memory-mappable TIFFs. The final
analysis semantic digests are `2d1ec646...c6d846` for K and
`a1f093db...9e2ed` for color. The grey and RGB modes are deliberately kept as
separate emitter profiles; scanner mode is part of the footing.

### Device and geometry

Both redundant machine strips independently pass CRC on both sheets and
agree on bundle/page identity. The live interpreter reports the HP M281fdw,
PostScript language level 3, firmware/version `3017` revision `1`, requested,
default, and effective resolution `600x600`, simplex, a 595x842-point page,
null `/ImagingBBox`, and `DeviceRGB` process model. The K-only scientific
content remains K-only; the process-model readback is provenance, not proof
of toner use.

The mono sheet was scanned at 180 degrees and the color sheet upright; both
register without mirroring. Measured scale is +0.096/+0.118% (x/y) for mono
and +0.121/+0.152% for color relative to nominal. Corner-fit RMS is about
0.13 mm. Sparse internal-mark residuals are 0.096 mm RMS / 0.260 mm maximum
for mono and 0.087 / 0.204 mm for color. The phase rails retain strong local
correlation while their best phase moves from -6 to +6 authored dots. A
single global pose is therefore adequate for finding fields but not for
scoring periodic microstructure without local phase alignment.

Solid ticks put the conservative physical-ink boundary at 3.5-4.0 mm on all
four edges across the pair, consistent with the earlier M281 observation.
Several outer mono bottom/right and color top/left ticks fall partly outside
the scanner raster; they are recorded as `unobservable`, never as printer
absence. The C2 payload arms do not yield a complete monotone rectangle. Mono
brackets only the right edge (7 mm under the strict contiguous rule); color
brackets only the bottom edge (3.5 mm). Capacity therefore remains unresolved
rather than reverting to an assumed page rectangle.

### K-only channel

Large solid-cell fields show a sharp physical and spatial frontier:

| field | held-out BER | MI (bit/cell) |
|---|---:|---:|
| C1 middle | 34.21% | 0.074 |
| C2 top / middle / bottom | 19.08 / 18.19 / 13.43% | 0.299 / 0.318 / 0.432 |
| C3 top / bottom | 11.40 / 0.125% | 0.491 / 0.986 |
| C4 middle | 0.014% | 0.998 |
| C6 bottom | 0% | 1.000 |

Thus C4 is the clean conservative solid-cell arm on this copy. C3 is highly
promising but not page-stationary; C2 remains detector/code dependent. The
compact C2 production coupons happened to occupy a favorable region:
`r0550` has 4.59% raw BER and recovers 2/2 exactly; `r0775` has 4.30% and also
recovers 2/2. This proves compatibility, not page-wide BLER: two words at one
location cannot override the 13-19% large-field results or the failed top
controls.

The matched motif arm is informative. At the same C2 pitch, solid and
diagonal marked cells score 15.16% and 14.42% BER, while horizontal-half and
vertical-half motifs improve to 9.14% and 8.96%. The rectangular C1xC2 and
C2xC1 cells score 23.08% and 30.49%, exposing orientation anisotropy. These
motifs deserve coded follow-up but are not qualified by the existing solid-C2
coupon.

### Color channel

Color C2 is not viable under the current independent-cell QDA footing. Pure
K/C/M/Y C2 fields score 39.73/48.75/35.03/31.71% BER. CM4 C2 scores 31.78%
with 0.204 bit/cell MI; CMY8 C2 scores 35.89-36.05% with about 0.20 bit/cell;
KCMY4 C2 is better but still 26.37-26.55% with 0.40-0.44 bit/cell. All 18
per-plane C2 coupon attempts over `r0550`, `r0700`, and `r0775` fail.

C3 is the clear color frontier: CM4 C3 scores 5.97% BER and 1.376 bit/cell,
or 85.34 empirical information bits/mm2; CMY8 C3 scores 8.45% and 1.920
bit/cell, or 119.02 bits/mm2. This is the highest information-density arm on
the two pages, but it has no matching C3 production coupon and only one
physical field/copy, so it is a follow-up candidate rather than a qualified
format.

The registration stations explain much of the C2 collapse. CMY relative to
local K is 0.0486 mm RMS (1.15 600-dpi dots) and 0.1179 mm maximum (2.78
dots). Mean C displacement is +0.42/+0.68 dot, M +0.13/-0.01, and Y
+0.28/-0.86, with material station-to-station variation. Those offsets are a
large fraction of, or greater than, a two-dot cell. The sequential OPM C2 arm
is not rescued physically: its 35.67% BER is similar to exact DeviceCMYK C2,
although its measured MI is somewhat higher. The synthetic OPM failure was
therefore path-specific, not a universal ordering.

### Tone, morphology, and profiles

All K/C/M/Y tone models are rank 9, monotone, and have zero monotonic
violations. The fixed bars vindicate their page budget: mono solid K has a
0.130 density p95-p05 span (21.8% of its mean). On the color page the solid
K/Y/M/C spans are 7.3/16.9/13.4/12.9% of mean; midtone K/Y/M/C spans are
21.9/36.3/11.7/18.2%. A single linear page slope would miss this nonlinear
variation. Y is optically the weakest response through this Canon footing.
Paper-white residual shading is about 0.4-0.5% RMS.

After bounded local translation alignment, 28/32 mono and 26/32 color
morphology probes resolve. One-dot isolated marks, one-dot holes, and one-dot
checkerboards fail on both operating paths; K one-dot vertical grating fails
on mono and both K one-dot grating orientations fail on color. Two-dot and
larger dots/holes and the assigned two-dot-or-larger gratings generally pass.
One-dot microtext has about 25% dot error despite positive correlation; it is
detectable, not a comfortable payload primitive.

Separate survey emitter profiles were built because grey and RGB are distinct
scanner footings. Both correctly return no qualified candidate: the payload-
safe rectangle is incomplete, one physical sheet is only survey evidence,
K C2's coupons conflict with poor page-wide same-candidate evidence, and the
best color C3 candidate has no exact coupon. The useful ranking is retained:
CMY8 C3 (119.02 bits/mm2), CM4 C3 (85.34), K C2 half-cell motifs (about
79-80, uncoded local evidence), and clean solid K C4 (34.81).

### Real-scan analyzer corrections

The first physical pass exposed three synthetic-hidden dead ends:

1. A wholly outside edge tick raised an exception; partially outside ticks
   could inherit interpolator edge clamping. Edge ticks now carry scan-visible
   fraction and become `unobservable` unless their full footprint is present.
2. Periodic morphology was scored at global affine phase. A half-period local
   warp could reverse correlation despite a crisp grating. The scorer now
   maximizes non-wrapped overlap over a bounded integer translation, records
   that translation, and does not search the invariant grating axis.
3. Payload canaries used every same-candidate PRND field as the interior
   baseline, including deliberately stressed equal-grid controls. The
   baseline is now the designated `role=channel` population; fallback and
   exact reference field IDs are explicit.

The primary field samples, held-out BER/MI, and FEC outcomes are unchanged by
these corrections. `tests/test_metrology.py tests/test_e025.py` now passes
14/14.

The previously printed LDPC-atlas pair belongs to the superseded
implementation and remains documented in Git history; it is not a live E025
input contract.

## 2026-07-18 — analyzer geometry audit (WORKPLAN-analyzer-v2 Phases A/B)

Zero print, zero scan: everything below re-analyses the two existing Canon
captures. The physical evidence is unchanged; what changed is the instrument.

### CORRECTION — most small-cell "channel" numbers above are analyzer artifacts

The 2026-07-17 section reports a K/colour channel measured through ONE global
corner affine plus ONE constant sub-cell lattice phase per field, with the
phase search clamped to +/-0.48 cell. That geometry model is falsified on this
capture pair, and the fields it fails on are exactly the small-cell fields the
density decisions depend on. Re-sampling **the same pixels** with a per-window
phase, changing nothing else:

| field | published (v2) | per-window (v3) | factor |
|---|---:|---:|---:|
| `spatial/top/c3` | 11.40% | **0.44%** | 26x |
| `grid-control/600-c2` | 43.04% | **3.86%** | 11.1x |
| `grid-control/2400-c8` | 44.07% | **5.18%** | 8.5x |
| `spatial/middle/c2` | 18.19% | **5.09%** | 3.6x |
| `spatial/top/c2` | 19.08% | **6.30%** | 3.0x |
| `spatial/bottom/c2` | 13.43% | **5.04%** | 2.7x |
| `factor/shape/solid-c2` | 15.16% | **6.12%** | 2.5x |
| `spatial/middle/c4` (control) | 0.014% | 0.000% | clean either way |
| `spatial/bottom/c6` (control) | 0.000% | 0.000% | clean either way |

Colour page, same treatment (state error for the multi-ink rows):

| field | published (v2) | per-window (v3) | windows locked |
|---|---:|---:|---:|
| `pure/C/c2` | 48.75% | **5.18%** | 21/21 |
| `pure/K/c2` | 39.73% | **4.48%** | 21/21 |
| `pure/M/c2` | 35.03% | **11.85%** | 21/21 |
| `pure/Y/c2` | 31.71% | 22.51% | 9/21 |
| `states/middle/cm4-c2` | 31.78% | 22.00% | 31/54 |
| `states/bottom/cmy8-c3` | 8.45% | 7.40% | 8/8 |
| `states/middle/cmy8-c2` | 35.89% | refuses (35.89% fallback) | **0/54** |
| `fec/cmy8-c2/r0550` | 46.94% | refuses (46.94% fallback) | **0/3** |

The split is clean and mechanistic: **single-plane** fields recover by 3-9x,
**multi-ink composite** fields barely move and the 8-state c2 field cannot lock
a single window. That is the per-plane registration limit, not the channel —
and the instrument now says so instead of reporting 35.89% as a measurement.

Consequently the following published claims are **RETRACTED**:

1. "C3 is highly promising but not page-stationary" (11.40% top vs 0.125%
   bottom, a 90x spatial ratio). Measured per-window, top c3 is **0.44%** and
   bottom c3 is **0.00%**. There is no 90x page gradient; there was a drifting
   sampling phase.
2. "Equal-pitch grid controls read 39-46%", which invited a RIP-behaviour
   reading. All four are geometry: 600-c2 3.86% and 2400-c8 5.18%.
3. "K C2 is strongly position-dependent, 13.4-19.1% raw BER". The three
   spatial c2 fields land at **5.04 / 5.09 / 6.30%**, i.e. a 1.25x spread, not
   1.42x on top of a 3x inflated base. K c2 on this print is a ~5-6% channel.
4. "Colour C2 is not viable under the current independent-cell QDA footing.
   Pure K/C/M/Y C2 fields score 39.73/48.75/35.03/31.71%." Per-window they
   score **4.48 / 5.18 / 11.85 / 22.51%**. Single-plane colour at c2 IS viable
   on this engine; what is not viable is the 8-state CMY composite at c2, and
   the measured reason is plate registration, not the channel. This reverses a
   decision-relevant conclusion: per-plane colour c2 is worth pursuing.
5. The RESULTS ranking that put "clean solid K C4 34.81 bits/mm2" above K C2
   was computed on the inflated c2 numbers and must be recomputed before any
   ranking is quoted.

The **coupon-vs-field contradiction is resolved**: the v2 report noted that
`fec/c2/r0550` recovered 2/2 words at 4.59% while the surrounding large c2
fields read 13-19% and called that "compatibility proof, not page-wide BLER".
The coupons were right. They are small (21.7 x 3.4 mm), so one constant phase
nearly suffices; the large fields drift out from under theirs. Per-window, the
big c2 fields sit at 5.04-6.30% against the coupon's 4.59% — a 1.1-1.4x gap
instead of 3-4x.

### Mechanism, measured

Two distinct failures, both geometric, both invisible to a Ghostscript render:

* **Static offset outside the search box.** `grid-control/600-c2` needs
  phase_y **+1.30..+1.60 cells** (stable across all 20 bands) and colour
  `pure/C/c2` needs **+1.64..+2.28 cells**, against a +/-0.48-cell clamp.
* **Drift within one field.** `spatial/top/c3` ramps smoothly **-0.43 ->
  +0.80 cell** top to bottom; no constant phase can track it, so the field
  bands between locked and lost. Measured per-field phase spans are
  0.30-2.49 cells.

The analyzer reports the enabling arithmetic against itself: `corner_fit_rms_px`
24.166 = 3.02 authored dots at 8 px/dot = **1.51 c2 cells**, and the internal
warp marks reach 6.07 dots. Cells at c4/c6 absorb 3 dots (0.75 / 0.50 cell) and
read clean; c2 and c1 cannot and do not.

Adversarial checks that survived (the refuter scripts were retired 2026-10-09; the numbers
below are the record):

* **Not density banding.** Inside a 41%-BER band of `spatial/top/c2`, cells
  whose four neighbours all match them read 0.0019 (white) / 0.0222 (ink),
  rising monotonically to 0.934 at four differing neighbours. A development
  band cannot leave 99.8% of uniform-neighbourhood cells correct.
* **Direction-selective, and the direction is predicted.** The sign of the
  measured per-band phase error predicts WHICH y-neighbour contaminates,
  r = +0.80..+0.99 across five fields.
* **Above-chance wrong reads.** `pure/K/c2` and `grid-control/600-c2` read
  78-84% wrong when the row above disagrees and 1.7-2.5% wrong when it agrees.
  No channel mechanism produces systematically above-chance errors; sampling
  the adjacent cell does.
* **Not calibration.** Refitting QDA per band at the unchanged field phase buys
  <=1.1pp and is negative on `grid-control/600-c2`; adding per-band PHASE to
  the same fields is what moves them.
* **Dose-response exists** against the directly measured per-band phase error,
  r(band BER, |delta phase_y|) = 0.68-0.99.

### Carve-outs — where the channel really is the channel

Not everything was geometry, and these three results stand:

1. **c1 is genuinely dead.** Per-window phase removes only ~18% of
   `spatial/middle/c1`'s error (34.21% -> 30.65%, and only 24 of 99 windows
   lock). Error persists at uniform neighbourhoods and is ink-loss dominant —
   the documented "isolated 1-dot marks do not print".
2. **The colour multi-ink fields are NOT analyzer-geometry-dominated.**
   Per-window phase moves `cmy8-c3` only 8.45% -> 7.40% and cannot lock a
   single window of `cmy8-c2` or the CMY8 coupons, against 3-9x recoveries on
   every single-plane field. The residual is consistent with the measured
   CMY-minus-K registration of 0.0486 mm RMS / 0.1179 mm max = 0.57 / 1.39 c2
   cells: a **per-plane** offset that no single lattice phase can serve, since
   one window cannot be in phase with three plates at once. Still geometric in
   kind, but print-side, and it needs the per-plane arm (not built). Until then
   the colour composite c2 numbers are registration-limited, not channel
   measurements, and the analyzer refuses them.
3. **A real c2 white-closure floor of ~3-6% exists** and has the right physics:
   after per-window phase the c2 fields sit at 5.0-6.3%, matching the coupons,
   and coupon error is class-asymmetric (white:ink 2.95-3.16) and
   content-dependent — the opposite signature to the banded fields, which are
   class-symmetric (1.00-1.22).

### Withdrawn supporting statistics (methodology audit)

Two statistics used while building the case do NOT survive audit and must not
be cited:

* **"38 of 51 fields sit on the +/-0.48 clamp, therefore the affine is
  systematically wrong" is WITHDRAWN.** Fields with no recoverable signal at
  all (median separation 0.014) clamp at the same rate as fields with signal
  (0.44 vs 0.48 per axis), so the clamp measures the score surface, not the
  registration. It also carries a code-level bias: the v2 coarse sweep visits
  (0, -0.2, +0.2, -0.4, +0.4) under a strict `>`, so ties keep the first,
  negative, candidate — -0.48 appears 62 times against +0.48 35 times, and
  121 of 196 axes are negative (p = 0.0012). The v3 search resolves ties toward
  the seed instead; the v2 estimator is left untouched and the bias is recorded
  here as a known defect of the legacy arm.
* **The per-field "signature" labels in `scratch/e025/phase_a_verdicts.json`
  are not admissible.** `block_spread` is an extreme-value statistic over
  hundreds of blocks; eight chance-BER fields were labelled
  "strong-spatial-structure" while being pure binomial noise (chi2/dof
  0.95-1.21). The defensible statistic is overdispersion: the six fields the
  diagnosis rests on run chi2/dof **18-74** and contain 36-203 blocks of 200+
  validation cells incompatible with their field mean at p < 1e-6, while every
  chance-BER field contains exactly zero such blocks.
* Related bookkeeping note: those block maps were scored on STATE error, which
  differs from the reported per-level bit BER in 43 of 98 fields by up to 0.393
  absolute. Colour signatures were therefore adjudicated on a different
  quantity than the headline BER; the LLR-derived bit BER reproduces the
  report exactly (max abs diff 0.0).
* One unexplained observation left open: `color/pure/Y/c2` shows a 10pp
  split-code dependence (phase 0.3913 / train 0.2919 / validation 0.3171). No
  other field deviates beyond three decimals. Worth resolving before any Y
  number is quoted.

### What shipped (analyzer v3, opt-in)

`analyze_e025.py --geometry window [--window-cells N]`, report schema
`paper-store/e025/analysis/v3-window`:

* per-window phase, wide **unclamped** first search then a chained local search
  seeded from the previous locked window, with a wide re-search when a chained
  seed fails to lock (transport discontinuities);
* per-window QDA, with lock certified on the PHASE split — the validation split
  never influences pose, phase, model or the accept/refuse decision;
* **fallback contract**: any window that cannot solve its own geometry (too few
  labelled cells, a missing state, a failed lock) is sampled at the v2
  whole-field phase, so windowed mode is a strict superset of field mode. This
  was added after measurement: without it, coupon fields whose calibration
  prefix does not reach every window fell back to phase (0,0) and regressed
  from 4.59% to 19.43%. Post-fix, no field is worse than field mode.
* headline statistics cover **all** validation cells (unresolved regions carry
  the fallback), so a field can never be flattered by scoring only the regions
  that locked; locked-window-only statistics are reported separately, and
  `scan_adequate` is false when nothing locked.

Legacy regression: re-running `--geometry field` after the change reproduces the
committed report with **0 changed numerical leaves and 0 removed keys** (7,697
leaves; 138 added `geometry_mode` provenance keys only).

Two new tests pin the fix rather than merely exercising it:

* `test_window_geometry_reports_contract_and_never_loses_to_field_mode` —
  contract keys present, window counts reconcile, headline population is the
  full validation set, and window BER <= field BER on a clean render.
* `test_window_geometry_recovers_a_field_that_constant_phase_cannot` — injects
  a page-height sine of +/-4 authored dots (no linear component for the corner
  affine to absorb) giving ~1.6 c2 cells of drift across the target field but
  only ~0.17 cell within a 48-cell window. The test FAILS if the warp does not
  first degrade field mode, then requires window mode to halve the damage. This
  is the miniature of the simulator truth harness the workplan still owes
  (Phase D): the first version of this test used a 1.5-px wobble, which stayed
  inside the 2-px cell and produced 0.0000 BER — a reminder that a warp test
  must be sized against the CELL, not against pixels.

Full repository suite: **659 passed** before the new tests.

Honest limits of the new arm: the phase search is **supervised** (it maximises
class separation against phase-split labels), which is legitimate for a
metrology instrument whose ground truth is known by construction and is what
breaks the mod-1-cell ambiguity — but it is an upper bound on what a blind
receiver recovers, and it is not a receiver-legality claim. Per-plane colour
offsets, the payload-safe extent re-derivation, the simulator truth harness and
the detector ladder (workplan Phases C/D/E) are NOT done.
