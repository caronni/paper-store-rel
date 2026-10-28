# E025 design — physical-channel metrology

E025 is a reusable measurement system for printer, scanner, and complete
paper-channel paths. It is not a payload format and it is not a large FEC
demo. Its job is to expose the physical channel cleanly enough that a later
format can make a conservative density and code-rate decision.

The live E025 design intentionally has no compatibility layer for the earlier
LDPC-atlas implementation. That artifact remains recoverable from Git history.
Keeping two incompatible measurement models behind one command would make the
new reports harder to interpret and maintain.

## 1. Three questions, three claims

The same instrument supports three distinct operations:

1. **Emitter characterization.** Print E025 on the printer/path/media/
   consumable state under test and scan it with the best declared reference
   scanner. The result belongs to that complete footing; it is not an
   intrinsic printer constant.
2. **Sensor characterization.** Take one already characterized physical E025
   sheet and scan that same piece of paper on each target scanner/mode. A
   separately printed copy does not factor out printer variation.
3. **Pipeline feasibility.** Print and scan E025 through the exact intended
   job path. This confirms that the current paper and consumable state still
   support the selected channel and gives a low-value receiver hint.

Emitter, sensor, and pipeline reports use the same evidence currency but may
not be silently substituted for one another.

## 2. Evidence hierarchy

E025 deliberately orders its evidence from physical to derived:

1. print-time interpreter/device readback;
2. physical ink reach and payload-safe printable extent;
3. pose, scale, skew, local warp, and transport residuals;
4. tone, color, frequency, morphology, and microprint response;
5. exact seeded state fields with full held-out cell evidence;
6. small real house-LDPC compatibility coupons;
7. profile policy and capacity recommendation.

An upper layer may summarize a lower layer, but it may not erase it. In
particular, a decoded LDPC word does not reveal whether errors arose from dot
gain, phase, color crosstalk, clipping, or a spatial burst. The exact seeded
fields remain the primary channel observation; FEC is a downstream
confirmation that the production code and decoder behave consistently with
that observation.

### 2.1 Area priority law

Page area is assigned by expected decision value per square millimetre:

| priority | evidence | area decision |
|---:|---|---|
| 1 | payload frontier, printable extent, registration, paper white | preserve or place in otherwise empty gutters |
| 2 | large balanced C1/C2 channel populations | retain the largest statistical fields |
| 3 | fixed-level/tone response, geometry, morphology | share footprints and use typed compact probes |
| 4 | matched symbol/aspect and color-constellation factorials | replace duplicated coarse controls |
| 5 | coarse C4/C6 margin checks and alternate emission paths | keep only enough population for a stable estimate |
| 6 | FEC confirmation | two words per level/rate; never expand into an atlas |

This law drove layout v2. The old tone ramps were split inside their existing
footprint, blank gutters became background/registration/feed witnesses, and
duplicate coarse-cell area became C2 motif/aspect and KCMY4 evidence. Large
C1/C2 PRND fields and edge arms did not shrink. Nothing was added merely
because it looked informative; every printed target has a numerical analyzer.

## 3. Two one-page jobs

Color lasers can choose a different rendering, speed, registration, or
screening path as soon as CMY appears. E025 therefore emits two independent
one-page jobs:

- `hp-m281-bw`: true K-only operation;
- `hp-m281-color`: a color job with K controls plus C/M/Y and mixed-state
  evidence.

Combining them would save one sheet but destroy the most important control.
There is no reason to spend more than these two sheets for the initial
characterization: the page is densely packed with independent instruments.

## 4. Grid, c factor, and physical pitch remain separate

Every channel field records:

```text
(authored dpi_x, authored dpi_y, c_x, c_y,
 exact alphabet, exact symbol shape, exact emission path)
```

The physical cell pitch is:

```text
pitch_x_mm = 25.4 * c_x / dpi_x
pitch_y_mm = 25.4 * c_y / dpi_y
```

`300/c1`, `600/c2`, `1200/c4`, and `2400/c8` have the same nominal
physical pitch but are different printer experiments. A RIP may preserve the
finer authored path, resample it, or collapse it. E025 prints matched-pitch
controls across addressing grids so the measured result answers that question.

The page-level `/HWResolution` request is separate again. The manifest retains
authored grids and the requested grid; the machine strip records default and
effective readback; only scanned recovery establishes useful addressability.

Printers between 300 and several thousand dpi are supported by choosing a
primary authored grid and comparison grids. The c factor is scaled for the
matched-pitch controls rather than copied blindly from a 600-dpi assumption.

## 5. Page anatomy

### 5.1 Redundant machine self-report

Two thin `PHCAL1/LAY=1` strips carry a 390-byte CRC-protected payload generated
inside the printer at print time. The payload includes:

- deterministic E025 bundle ID and public seed;
- page kind and authored/requested grids;
- language level;
- default and effective `/HWResolution`;
- `/PageSize` and `/ImagingBBox`;
- duplex/tumble and process color model where exposed;
- product, interpreter version/revision, and serial number where exposed.

The strip format reuses the proven E002 decoder, but no active resolution
enumeration is performed on a science page. Guarded `setpagedevice` trials can
alter the very path being measured; active discovery remains a separate job.

Readback is provenance, not physical truth. A printer can echo a request while
resampling the bitmap.

### 5.2 Physical printable extent

Each edge has solid 1.5 mm ticks whose outer gaps are:

```text
0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 8, 10 mm
```

These bracket where ink can physically appear. Each gap occupies a different
along-edge station, so a clipped tick is not hidden behind another mark.

`/ImagingBBox` is retained beside this measurement but never substitutes for
it. It may be null, nominal, driver-derived, or simply wrong.

### 5.3 Payload-safe extent

Physical ink reach is insufficient for capacity. A clipped or phase-damaged
random field can be unusable even when a solid square survives.

Each edge therefore also carries independently seeded C2 canaries at gaps
0.5, 1.5, 2.5, 3.5, 5, 7, and 10 mm. The monochrome page uses the K channel;
the color page uses exact CMY8 states. An edge margin is accepted only at the
smallest gap whose canary and every more-inboard canary satisfy BER and MI
limits relative to the same candidate in the page interior.

The four conservative margins define the measured payload-safe rectangle.
Capacity arithmetic uses this rectangle, not nominal A4 and not the solid-tick
boundary.

### 5.4 Pose, skew, warp, and transport

Four chiral corner marks establish orientation and the global affine. Sparse
internal plus marks expose residual local warp after that affine. Long 3-on/
3-off horizontal and vertical phase rails expose transport residuals along x
and y.

This is deliberately redundant:

- corner geometry measures global pose, scale, rotation, and shear;
- internal landmarks reveal non-affine displacement;
- phase rails reveal coherent local transport changes that isolated landmarks
  can miss.

### 5.5 Tone, uniformity, and controlled paper

Layout v1 repeated a left-to-right tone ramp. That measured transfer but
aliased requested coverage with horizontal position: the faint left side could
not independently measure cross-page uniformity.

Layout v2 shares each existing rail footprint between two instruments:

- a true full-width fixed-level profile;
- a thin response strip containing paper, 10%, 25%, 50%, 75%, 90%, and solid
  segments in station-dependent permutations.

The monochrome page has four horizontal K stations at 100%, 50%, 75%, and 25%
plus a vertical 50% station. The color page has top 100% and bottom 50% K/Y/M/C
profiles, paired top/bottom response permutations, and narrow 50% K/Y/M/C
feed-direction profiles in the right gutter. Mid-tone profiles use a fixed
seeded dot population balanced along the measured axis; the report retains
the authored coverage profile as a stimulus-noise floor.

Ten declared no-ink witnesses sample paper/background across both pages. The
analyzer fits scanner/paper R/G/B shading versus page x/y rather than treating
unregistered whitespace as a reference.

Together these separate tone response, horizontal uniformity, feed-direction
variation, and background shading. Absolute optical density still depends on
the declared scanner footing.

### 5.6 Color-plane registration

The color page places nine compact registration stations in three otherwise
empty row gutters and three x positions. Each station has spatially separated
K/C/M/Y crosses. Separating the crosses avoids ambiguous overprinted color;
the analyzer measures each plane's centroid residual after the common corner
affine, then subtracts the local K residual from C/M/Y. It reports every vector,
RMS displacement, and maximum displacement.

### 5.7 Frequency, morphology, and microprint

Typed small probes include:

- horizontal and vertical 1-on/1-off through 4-on/4-off gratings;
- isolated horizontal and vertical lines of width 1–4 authored dots;
- isolated ink dots and white holes of size 1–4 dots;
- one- and two-dot checkerboards;
- raster microtext at stroke widths 1–4 dots;
- 5-degree and 45-degree slanted edges.

The color page rotates these probes through K/C/M/Y. Ground truth is exact and
the analyzer reports dot error, density separation, and correlation rather
than just a visual label.

### 5.8 Large deterministic state fields

Seeded, nearly exactly balanced fields are the primary information-channel
evidence. The K page gives most area to distributed C1/C2/C3 fields, with
smaller C4/C6 controls. It adds a matched C2 factorial of solid, diagonal,
horizontal-half, and vertical-half marked-cell motifs and C1xC2 versus C2xC1
rectangular cells. The color page measures pure K/C/M/Y C2 fields, CM4 and
exact CMY8 at C2/C3, matched-pitch grid controls, the alternate CMY8 OPM path,
and a two-bit one-hot K/C/M/Y constellation. Coarse C3 and alternate-path
fields are intentionally smaller than the high-value C2 populations.

The fixed public seed is:

```text
paper-store/e025/channel-metrology-v2
```

It never depends on a payload or file hash. Every field has a distinct label
and ground-truth digest.

### 5.9 Small FEC confirmation coupons

The K page carries C2 coupons at `r0550` and `r0775`. The color page carries
exact CMY8 C2 coupons at `r0550`, `r0700`, and `r0775`. Each coupon has an
independent calibration prefix and two real 4096-bit house codewords per
declared level.

These coupons answer “does this actual code/decoder agree with the raw channel
measurement?” They do not by themselves estimate a production BLER to tight
confidence. Profile reports preserve that limitation.

Rates are not columns and are not tied to a fixed x position. The old
rate-by-x atlas confounded code rate with horizontal printer/scanner variation
and spent the largest area on the coarsest modes. E025 rejects that layout.

## 6. Analyzer contract

### 6.1 Registration and strips

The analyzer creates a memory-safe page thumbnail for corner registration and
uses registration-guided local strip crops. A 4800-dpi TIFF therefore does not
need to be loaded in full merely to decode a 3 mm strip.

### 6.1a Geometry modes (v2 field, v3 window)

The analyzer has two geometry contracts. `--geometry field` (default) is the
original: one global corner affine plus ONE constant sub-cell phase per field,
searched over +/-0.48 cell. `--geometry window` is the 2026-07-18 replacement:
each field is tiled into ~96-cell windows, each window solves its own phase
with a wide UNCLAMPED first search and then a chained local search seeded from
the previous locked window, and each window certifies its lock on the phase
split before it is trusted.

The field mode is retained because it is the footing every number before
2026-07-18 was measured on, not because it is adequate. It is not: measured on
the first physical pair, the true lattice phase leaves the +/-0.48 box
(grid-control/600-c2 needs +1.30..+1.60 cell, colour pure/C/c2 +1.64..+2.28)
and DRIFTS within a single field (spatial/top/c3 ramps -0.43 -> +0.80 cell),
so fields of small cells read at or near chance while their ink is intact.
Re-sampling the same pixels per window took spatial/top/c3 from 11.40% to
0.44% and grid-control/600-c2 from 43.04% to 3.86%. See RESULTS.md
"analyzer geometry audit" for the retractions this forced.

Two rules make the windowed mode safe to compare against the old one:

* **Fallback.** A window that cannot solve its own geometry is sampled at the
  whole-field phase, so window mode is a strict superset of field mode and can
  never be worse for want of a seed.
* **No cherry-picking.** Headline statistics cover every validation cell,
  including cells in windows that refused; locked-only statistics are reported
  separately and `scan_adequate` is false when no window locked.

The search is supervised — it maximises class separation against phase-split
labels, which is what resolves the integer-cell ambiguity a label-free lattice
search would leave open. That is legitimate for an instrument whose stimulus is
known by construction, and it is deliberately an upper bound: it measures what
the CHANNEL carries, not what a blind receiver recovers. A receiver-legality
claim still needs that receiver's own arm (section 9).

### 6.2 Disjoint channel populations

For every deterministic field, flattened row-major cell indices are split:

| index mod 8 | role |
|---|---|
| 0 | phase selection |
| 1,2,3 | QDA training |
| 4,5,6,7 | held-out validation |
| FEC suffix | codeword evidence only |

Phase is refined locally over almost a complete cell period. This matters at
page edges: a corner affine is a pose model, not a local lattice-phase oracle.
The aperture adapts to measured scan samples per cell.

The report retains state confusion, per-level BER, MI, measured samples/cell,
phase, aperture, and exact LDPC outcomes. An optional trace directory writes
one compressed NPZ per field with every true state, predicted state, split,
feature vector, state score, and bit LLR. This is the preferred input for later
detector research.

### 6.3 Probe scoring

Physical probes are scored in their own units:

- ticks: normalized coverage and present/partial/absent status;
- fixed-level profiles: full density series, RMS and robust span, alongside
  the authored-coverage series;
- tone response: a categorical coverage curve plus independently fitted x/y
  density slopes and residual RMS;
- controlled paper: local R/G/B statistics and a page-x/page-y shading fit;
- plane registration: each cross centroid and CMY-minus-K displacement at
  nine stations, with RMS and maximum displacement;
- morphology/frequency: dot-level error, separation, correlation, and
  resolved status;
- plus marks: residual displacement after global affine;
- phase rails: local phase-residual series along the transport axis.

No LDPC statistic stands in for these measurements.

Shape, aspect, constellation, and emission-path factorials use the same
disjoint phase/train/validation QDA contract as the large fields. Their rows
are additionally grouped under `candidate_factorials`; no special-case visual
judgment is needed.

### 6.4 Capacity

For a measured payload-safe width `W` and height `H`:

```text
nx = floor(W / pitch_x_mm)
ny = floor(H / pitch_y_mm)
cells = nx * ny

raw_bits = cells * alphabet_bits_per_cell
empirical_information_bits = cells * minimum_heldout_MI_bpc
coded_bits = cells * sum(confirmed_rate_per_level)
```

The coded number is explicitly before production furniture and outer fountain
overhead. The generator's 10 mm capacity table is planning only; the analyzer
replaces it with the measured rectangle.

## 7. Profiles and decisions

Profiles retain physical-sheet diversity. Survey, production, and archive
policies differ in required sheet count, worst BER, MI fraction, and exact FEC
coupon diversity. A compatibility coupon must recover exactly before its rate
can be recommended, but even a passing coupon is labelled as a small
confirmation sample.

Scanner comparison requires exact field-set equality on the same physical
`sheet_id`. Repeated scans are useful sensor evidence but are not independent
printer trials.

A pipeline profile may emit an advisory receiver hint containing candidate,
rate, measured margins, and scanner sampling. It may never weaken placement,
bounded-LLR, LDPC, fountain, or payload-CRC gates.

## 8. Rejected shortcuts and dead alleys

The following choices were considered or built and are now rejected:

1. **A five-rate LDPC matrix as the whole experiment.** It measured decoder
   outcomes but obscured physical causes, tied rate to x, and allocated area
   in proportion to coarse-cell physical size.
2. **Equal codeword counts for every c factor.** This gave C6 the largest
   real estate while the C1/C2 frontier received tiny strips—the inverse of
   useful statistical allocation.
3. **Encoding runs instead of known random states.** Runs are useful as typed
   morphology probes, not as a substitute for balanced spatial channel
   evidence.
4. **Trusting `/HWResolution` or `/ImagingBBox`.** Both are interpreter
   claims; neither proves physical addressability or printable extent.
5. **Collapsing grid and c into pitch before measurement.** Equal nominal
   pitch can traverse different RIP paths.
6. **One candidate per sheet.** Exact identity is a field property; one page
   has ample room for many independent fields.
7. **Mixing monochrome and color on one page.** This destroys the K-only
   operating-path control.
8. **Training on tested codewords.** The detector populations and FEC suffix
   are disjoint.
9. **Using a nearby alphabet or emission path.** CMY7 cannot calibrate CMY8;
   DeviceCMYK image and OPM are separate candidates.
10. **Active printer-resolution enumeration on the science page.** A guarded
    request can still alter later rendering state.
11. **Treating the first surviving edge mark as payload-safe.** Solid ink
    reach and recoverable random cells are different boundaries.
12. **Letting the receiver hint become authority.** It remains disposable
    advice.
13. **Calling a monotone tone ramp a uniformity bar.** Tone and x position
    were aliased; layout v2 uses fixed profiles plus permuted response strips.
14. **Using uncontrolled whitespace as scanner white.** Background witnesses
    are now reserved and scored explicitly.
15. **Diagnosing composite color errors without plane registration.** CMYK
    cross-centroid stations now distinguish displacement from blur/confusion.
16. **Treating scanner crop as printer absence.** Near-edge targets can map
    partly outside an otherwise valid scan. Full-footprint visibility is now
    tested before scoring; clipped ticks are `unobservable`, not absent and
    not interpolation-clamped inward.
17. **Scoring periodic probes at global-affine phase.** The first physical
    phase rails move by up to six authored dots while retaining strong local
    correlation. Morphology therefore removes one bounded, non-wrapped local
    translation and reports it before judging modulation.
18. **Letting deliberately stressed controls define the payload baseline.**
    Equal-grid, shape, and emission-path controls answer separate questions.
    Edge canaries compare to designated `role=channel` interior fields; any
    fallback is explicit in the report.
19. **One constant lattice phase per field, clamped to half a cell.** Measured
    2026-07-18: the required phase leaves the box (up to +2.28 cells) and
    drifts within a field (up to 2.49 cells span), so whole fields of small
    cells read at chance while their ink is intact. Superseded by per-window
    phase; see 6.1a.
20. **Reading a coin-flip BER as a channel result.** A field whose geometry
    never locked has not measured anything. v2 reported 50% BER with
    `scan_adequate: true` because the adequacy test was only
    `isfinite(separation)`. v3 certifies a lock per window, on the phase split,
    and says so when it fails.
21. **Scoring only the regions that worked.** Excluding geometry-unresolved
    windows from a field's headline BER would report the instrument's best
    case as the channel. Headline statistics cover every validation cell;
    locked-only numbers are a separate, labelled row.
22. **Trusting the phase-clamp count as evidence of misregistration.** Fields
    with no recoverable signal clamp at the same rate as fields with signal
    (0.44 vs 0.48 per axis), so the statistic describes the score surface, not
    the page. The v2 sweep also had an order-dependent tie bias toward negative
    phases (-0.48 x62 vs +0.48 x35). Use overdispersion of the within-field
    error map instead (chi2/dof 18-74 on the affected fields, ~1 on
    chance-BER fields).

## 9. Deliberate limitations

- The current field detector is independent-calibration QDA, not E023b's
  production detector. A deployment claim for a particular receiver still
  needs that receiver arm.
- Windowed geometry is supervised and therefore an upper bound on the channel,
  not a blind-receiver result (6.1a).
- Windowed geometry solves ONE phase per window for the whole cell. The colour
  multi-ink fields need a PER-PLANE offset — the measured CMY-minus-K
  registration is 0.57-1.39 c2 cells — and that arm is not built, so colour
  c2/c3 multi-ink numbers remain registration-limited rather than
  channel-limited.
- Numbers published before 2026-07-18 were measured in field mode; small-cell
  fields among them are not comparable to v3 numbers and several are retracted
  in RESULTS.md.
- Two FEC words per level/rate are compatibility evidence, not a tight BLER
  estimate.
- Global affine plus local field phase and sparse warp instruments do not yet
  constitute a full non-rigid page tracker.
- One canary per gap is intentionally conservative but can be nonmonotone when
  along-edge channel quality varies. An unresolved rectangle is a valid
  result; no nominal fallback is permitted.
- A grey reference capture and an RGB reference capture are distinct scanner
  footings and cannot be merged into one emitter profile.
- Capacity is reported before production furniture and outer-code overhead.
- Scanner and printer contributions remain inseparable unless the same
  physical sheet is scanned through a declared reference and target path.

These limits are visible in reports rather than hidden behind a single
“maximum dpi” number.
