# Experiment 021 — PAYLOAD-REGIONS

**Stage 0 only: platen scan → candidate payload regions + one global c +
optional angle hints.**

Status: **021.6 coarse-authoritative boundary/gap refinement implemented and
strictly qualified 2026-07-16.** The 021.4 reset and 021.5 support-mask
semantics remain the foundation; 021.6 replaces their native-pixel
refinement skip. The forensic review that forced the reset is preserved
verbatim in `experiments/021-payload-regions/deficiency_findings.txt`.

## 1. User-fixed intent

Input:

- one grey platen scan;
- its true scanner DPI.

Output:

- independent candidate payload-region masks and bounding boxes;
- one common `c` for the platen;
- one approximate angle hint per region, or `None`;
- an annotated PNG showing every returned bbox and exact emitted mask contour.

All scraps on one platen are assumed to have the same `c`. In paper-store,
`c` means 600-dpi print dots per cell, so scanner-space pitch determines it:

```
c = measured_cell_pitch_px * 600 / scan_dpi
```

The 600-dpi print grid is a frozen engine/format fact, not a hidden caller
parameter. If the evidence does not select one integer c, e021 returns
`c_dots=None`.

Explicitly outside e021:

- pilot sites and values;
- BCH decoding and tile addresses;
- sub-cell lattice lock;
- LDPC/payload detection;
- claims that a returned candidate is valid payload.

Those belong to the separate e022 pass. E021 never invokes them.

## 2. Semantics

There is one type of returned object: **candidate region**.

There are no `confident`/`marginal` tiers. The retired tiers mixed two
incompatible meanings: texture strength and spectral pitch availability.
They also allowed scanner-border junk to leave the API under the same
`PayloadRegion` name as real pieces. E021 now makes the honest statement:
every returned region is worth scanning for pilot tiles; only e022 can
validate it.

The emitted mask is a **search-support envelope**, not the raw thresholded
texture activity. Coarse accepted support is authoritative in the interior.
Pitch-scale evidence may sharpen its exterior, complete support, or open an
exterior-connected separating gap; fine tensor silence alone may not carve
an enclosed hole. Larger voids already present in the coarse support remain
open as useful erasure geometry. Raw activity remains the evidence used for
detection, scoring and component ownership, but is not part of the public
API.

## 3. Minimal pipeline

### 3.1 Coarse tensor survey

The retained e020 core is the minor eigenvalue of the local gradient
structure tensor:

```
J = G_sigma * [[Ix², IxIy], [IxIy, Iy²]]
score = sqrt(lambda_min(J))
```

`lambda_min` is high only where contrast varies in two dimensions. Flats and
isolated paper/backing edges are rejected by the statistic itself, regardless
of rotation.

One physical survey scale is used: 340 µm. Random binary payload leaks down
the spectrum, so the coarse scale still sees finer c1/c2/c3 lattices; unlike a
fine detector it also sees coarse c8/c12. Qualification tests c1, c2, c3, c8
and c12 rather than treating this as an assertion.

The 340 µm value is converted through the caller's true scan DPI. It is
16.063 scanner pixels at 1200 dpi and 64.252 scanner pixels at 4800 dpi.
Those are scan pixels, not 600-dpi printer dots. The tensor front end
decimates by 4 and 16 respectively, leaving about four working samples per
survey cell and native output steps of 16 and 64 pixels. Thus both scans use
the same physical detector footing rather than selecting a DPI-specific
algorithm.

The score threshold is one scan-adaptive value: a log-space Otsu split.
021.4 initially retained the old low-tail floor as `max(floor, Otsu)`;
strict qualification showed that it returned zero regions on both real
payload-dominated full sheets. The floor was deleted rather than bypassed by
another dominance branch. Blank/noise/edge controls independently gate
whether Otsu alone is permissive.

A 5-of-9 density condition rejects isolated responses. Components below
9 mm² are excluded. There is no weak tier, hysteresis growth, border
demotion, dominance/full-sheet branch, or print-level grey threshold.

### 3.2 One global c

Pitch is measured from the full bbox of each sufficiently large survey
component using `scannorm.measure_cell_pitch`. Full bboxes supply enough
periods for coarse c; an inscribed-square measurement was tested and failed
on a held-out rotated c12 field because only ~4 periods remained.

Each component contributes at most one vote:

1. inspect all credible wide-band spectral lines;
2. map each line to `c = pitch_px * 600 / scan_dpi`;
3. retain integer c values within 4%;
4. select the largest such c for that component, preserving the cell
   fundamental over its harmonics.

The platen c is the unique modal vote. A tie returns `None`; mixed-c platens
are outside contract and explicitly qualify as an honest refusal. The
reported scanner-space cell pitch is the median pitch among votes for the
winning c.

This global consensus removes the conceptual error in 021.0: individual
regions do not mint authoritative c values. A diagonal c3/√2 line does not
land within the integer-c bar and cannot vote.

### 3.3 Pitch-matched boundary refinement

When global c exists, E021 evaluates pitch-scale evidence where it can change
geometry rather than rerunning a full-area segmentation and replacing the
coarse result.

The refinement domain is the union of:

- a two-survey-cell band on both sides of the coarse support boundary;
- coherent low-score valleys that may hide a survey-fused material gap.

A valley starts below 65% of the component's median coarse score, must survive
a three-cell line opening in a horizontal, vertical or diagonal direction,
and must span at least 25% of the component's shorter dimension. This rejects
isolated random-payload lows while retaining the qualified 0.4 mm separating
stripe.

The domain is projected onto the measured-pitch grid and covered by aligned
128×128-payload-cell tiles with a four-cell tensor halo. Adjacent tiles are
included so thresholding and the 5-of-9 density condition are seam-safe. One
adaptive threshold is computed over all scored tiles for the component.
Tensor-filter temporaries are bounded by tile size; global refinement state
is one score/mask grid at measured-pitch resolution. Work is reported in
pitch-grid cells. There is no native-raster pixel cutoff and therefore no
HP-versus-Canon refinement branch.

Fusion is deliberately asymmetric:

- positive pitch-scale evidence may add support wherever it was measured;
- negative evidence may retract support only in the boundary/gap domain;
- an enclosed fine-level loss that was coarse-supported is restored;
- an exterior-connected false corridor remains open and may split one coarse
  component into independent refined regions.

If pitch is unavailable, the component is too small for the measured pitch,
or no tile produces usable evidence, the conservative coarse support is
emitted. There is no crop-specific field fraction, grow/erode recipe or
component confidence reclassification.

### 3.4 Candidate support reconstruction

The structure tensor is deliberately flat-blind. Uniform runs, one-direction
transitions and locally weak toner therefore make many small false holes
inside genuine payload. E022 needs a simple region in which to slide pilot
tiles; it must not inherit those score-level holes as erasures.

For each connected component, e021 floods background from a one-cell false
padding border. False cells not reachable from that border are enclosed
holes; false cells connected to the border remain exterior:

```
padded = pad(activity, False)
outside = propagate(border_seed, mask=~padded)
holes = ~outside & ~activity
```

For each enclosed hole, e021 measures the maximum inscribed radius on the
tensor grid. Holes with radius ≤3 payload cells are included in support;
larger holes remain open. The bound is pitch-scaled onto the actual detector
grid, with one detector sample as the minimum fillable unit. This operation
cannot connect two components or alter the component's outer boundary. It is
performed before native-pixel rasterization, so it is cheap.

This is intentionally different from 021.1's retired “fill holes below
9 mm²” detector heuristic. The new rule follows detector resolution rather
than area: the measured dropout class is filled, while burns, stickers and
torn-out interiors larger than that class remain honest erasures. The
activity-mask score still determines whether the component exists.

### 3.5 Optional angle hint

Angle is measured **after** global c, separately on every final region. It is
not inherited from a parent survey component.

The known common pitch is probed on two interior window scales. A hint is
emitted only when:

- both measurements retain the known pitch within 4%; and
- their mod-90 angles agree within 2°.

Otherwise the hint is `None`. Thin regions naturally return `None`. The two
scale agreement replaces the retired absolute spectral-contrast gate and
prevents the 021.3 c3/√2 diagonal capture from becoming a confidently wrong
hint. The interior centre is found on a one-sample-per-cell version of the
mask; doing hole-fill/EDT on native block-replicated masks was geometrically
redundant and made the six real platens take about 12 minutes. The optional
hint refuses above 16 million samples on that measured-cell mask, not above a
native-pixel count. All qualified full pages are about 7.5 million samples;
the bound therefore exercises both HP and Canon while limiting the EDT's
actual allocation. It has no effect on masks, c or E022 correctness.

## 4. API

`paperholo.platen.detect_payload_regions(image, dpi=...)` returns:

```
PayloadSurvey(
    regions=tuple[PayloadRegion, ...],
    c_dots=int | None,
    cell_pitch_px=float | None,
    pitch_votes=tuple[(c, pitch_px), ...],
    diagnostics=dict,
)
```

Each `PayloadRegion` contains:

- native-pixel `(y0, x0, h, w)` bbox;
- bbox-local native-pixel boolean mask;
- physical area;
- `angle_hint_deg: float | None`;
- median tensor score.

The CLI:

```
env/bin/python experiments/021-payload-regions/analyze_e021.py \
    <scan> --dpi <true-dpi> [--out output.png]
```

draws every candidate bbox in orange and the emitted mask contour in pale
blue `(150, 200, 235)`. The title reports the platen-wide c and measured
pitch. There is no tier coloring.

## 5. What was deleted

The reset deletes, rather than renames:

- confident/marginal tiers and their colors;
- the permissive marginal admission path;
- per-region c and pitch;
- radial-spectrum pitch fallback;
- scanner-border special-case demotion;
- texture-dominance/full-page special branch;
- sub-grain classification;
- absolute crop standard-deviation gate;
- size-bounded detector hole filling (replaced by topology-defined output
  support reconstruction);
- field-median refinement threshold;
- 256-pixel minimum pitch window that contradicted thin-region geometry;
- mixed-c qualification, except as an expected global-c refusal;
- bbox-overlap-only tests and vacuous loops.

The superseded 019 variance detector remains in `segment.py` only for its
historical experiment and existing receiver callers; e021 does not use it.

## 6. Qualification contract

`tests/test_e021.py` and `qualify_e021.py` enforce:

- exact candidate count, not “at least one overlap”;
- Hungarian one-to-one truth assignment;
- per-region pixel-mask IoU;
- zero extras and zero misses;
- correct one global c;
- every non-None angle hint must be accurate;
- at least one angle hint must be exercised (no vacuous success);
- white paper margins excluded on dark backing;
- every emitted support mask has zero fill-eligible enclosed holes;
- a topology fixture fills a small internal hole while preserving both a
  concavity connected to the exterior and a larger enclosed void;
- healthy and faint fields both retained;
- 0.4 mm separated fields remain independent;
- payload-dominated platen plus adjacent piece remains independent;
- thin payload ribbon remains a separate region and returns no fake angle;
- blank paper, 1-D edges and scanner noise return zero regions;
- mixed-c platen returns regions but refuses global c;
- 8/16-bit scale invariance and input guards;
- annotated-PNG smoke test.

The exact-mask fixtures use untouched 300-series seeds. The c matrix covers
c1/c2/c3/c8/c12 at rotations 10–40°. The real run separately checks all six
e018 confetti platens against physical piece counts and the e016/e017 full
sheets against their known c. Real masks are not called ground truth.

The qualification report stores raw counts and every matched IoU, not only a
pass boolean.

## 7. Constants and scope

| constant | value | meaning |
|---|---:|---|
| print grid | 600 dpi | frozen paper-store definition of c |
| survey scale | 340 µm | one coarse physical search scale |
| tensor work sampling | 4 px/assumed cell | computational footing |
| derivative σ | 0.22 cell | tensor band selection |
| tensor σ | 0.30 cell | local 2-D support |
| density | 5 of 9 | isolated-response rejection |
| minimum area | 9 mm² | smallest emitted processing region |
| integer-c tolerance | 4% | scanner scale + spectral measurement |
| c range | 1–12 | current survey/format envelope |
| pitch probes | 2,3,4,6,8,12,16,24,32,48,64,96,128 px | wide-band scan ladder |
| pitch bbox minimum | 32 px | enough input for any spectral attempt |
| pitch FFT cap | 2048 px | inherited `scannorm` work bound |
| refinement halo | max(2 cells, 1 mm) | background evidence around seed |
| refinement minimum | 4 cells across | tensor support floor |
| refinement boundary band | 2 survey cells | exterior/material edge domain |
| gap-valley threshold | 0.65 × component median | candidate fused-gap evidence |
| gap-valley run/span | 3 survey cells / 25% of shorter component dimension | reject isolated payload lows |
| refinement tile / halo | 128 / 4 payload cells | bounded aligned tensor work |
| support-hole radius | 3 payload cells (pitch-scaled; min 1 detector sample) | fill measured λ_min dropout class; preserve larger voids |
| angle half-windows | 512 and 256 px | independent scale check |
| angle minimum | 8 measured cells across | spectral support floor |
| angle work cap | 16 M measured-cell samples | resolution-normalized optional hint bound |
| angle agreement | 2° | hint-or-None gate |

Physical/dimensionless units do not make constants self-justifying. Their
qualification rows are the justification; none are promoted as universal
printer facts.

## 8. Honest limits

- One c per platen is a contract. Mixed c returns `c=None`.
- A connected bridge of genuine 2-D texture can merge touching pieces.
  Qualification covers 0.4 mm gaps, not zero-gap overlap.
- Thin-region boundary uncertainty is about one cell. A four-cell-wide ribbon
  therefore has a lower fractional IoU bar (0.50) while retaining unique
  ownership.
- A region too small or spectrally weak to estimate angle returns `None`.
- Candidate masks are not payload validation. E022 may reject them all.
- c is tied to the frozen 600-dpi print grid. A future non-600 format needs a
  different descriptor/API, not a silent reinterpretation.
- The six e018 scans provide physical counts but no hand-annotated pixel masks.

## 9. Results

**021.4 reset, 2026-07-14: strict qualification 6/6 PASS in 292.5 s;
`tests/test_e021.py` 9/9 PASS.**

Exact held-out masks (zero extras, zero misses in every row):

| case | returned/truth | minimum matched IoU | global c |
|---|---:|---:|---:|
| white margin on dark backing | 1/1 | 0.944 | 3 |
| three independently rotated pieces | 3/3 | 0.944 | 3 |
| healthy + faint field | 2/2 | 0.888 | 3 |
| two fields separated by 0.4 mm | 2/2 | 0.941 | 3 |
| full sheet + side piece + 4-cell ribbon | 3/3 | 0.539 ribbon / >0.80 2-D | 3 |

Global-c matrix, held-out rotations:

| truth | result | measured scan pitch | mask IoU | angle error if emitted |
|---|---:|---:|---:|---:|
| c1 | c1 | 8.006 px | 0.950 | 0.096° |
| c2 | c2 | 16.006 px | 0.961 | 0.366° |
| c3 | c3 | 24.053 px | 0.950 | 0.238° |
| c8 | c8 | 63.969 px | 0.905 | 0.516° |
| c12 | c12 | 96.270 px | 0.810 | None (honest refusal) |

Null controls (blank platen, homogeneous paper, 1-D paper edges, noise)
returned zero regions. A two-piece c3+c6 out-of-contract platen returned both
regions but `c=None`, with both conflicting votes exposed.

Real 4800-dpi scans:

| scan | returned / physical pieces | c | pitch | angle hints |
|---|---:|---:|---:|---:|
| confetti-1 | 17/17 | 3 | 23.85 px | 17 |
| confetti-2 | 10/10 | 3 | 23.83 px | 9 |
| confetti-3 | 8/8 | 3 | 23.80 px | 5 |
| confetti-1 second take | 17/17 | 3 | 23.81 px | 17 |
| confetti-2 second take | 10/10 | 3 | 23.92 px | 10 |
| confetti-3 second take | 8/8 | 3 | 23.81 px | 5 |
| e016 full K sheet | 1/1 | 2 | 16.00 px | None (work cap) |
| e017 full CMY sheet | 1/1 | 3 | 23.81 px | None (work cap) |

The old “confetti-3 has seven physical pieces” record was wrong: it described
e019's accepted merge of two close scraps. The PNG and original dialogue show
eight physical pieces; 021.4 separates all eight on both takes.

Final sheet-1 CLI run: 17 candidates, c3 at 23.85 px, 17 angle hints, 35.8 s;
PNG `scratch/e021/e021-final-confetti-1.png`. The pale-blue contours are clean
at display scale; no tier/junk boxes remain.

### Iteration record

The first strict full run was **4/6**, not relabeled as success:

- confetti-3 returned 8 against the stale expected 7; inspection corrected
  the physical truth rather than changing the detector;
- both payload-dominated full sheets returned zero because the retained
  low-tail floor overrode Otsu; the floor was deleted, not bypassed with a
  dominance branch;
- Otsu then found one correct region/c on each full sheet, but unrestricted
  full-area pitch refinement exceeded 20 minutes; 021.4 introduced native-
  pixel skip caps as an emergency bound. Those caps remained through 021.5
  and are superseded by 021.6's tiled boundary/gap refinement;
- native-mask hole-fill/EDT for angle hints made six platens take ~12 minutes;
  moving this geometrically identical operation to one sample per cell cut
  sheet-1 to 35.8 s.

The report is `build/qualify_report.json` (git-ignored, regenerated by the
command above). At the 021.4 checkpoint, exact real pixel masks across
independent scanners/stocks were absent and E022 had not yet measured
candidate-to-pilot cost; later sections retain the resulting evidence.

## 10. 021.5 — bounded topology-defined support masks (2026-07-14)

User review of the final PNG correctly challenged the many tiny internal blue
contours. They were not independent regions: the renderer faithfully drew
every boundary of the raw tensor activity mask, including local λ_min
dropouts. Returning those holes would force e022 to solve irrelevant mask
semantics before it could search pilot tiles.

Pre-change measurement:

- strict white-margin fixture: raw IoU 0.943; topology fill 0.986;
- held-out rotated fixtures: 3.5–4.3% of the support was enclosed inactivity;
- real sheet 1 at one mask sample/cell: enclosed-hole fraction median 1.28%,
  maximum 3.61%; median largest hole 10 cells, maximum 48 cells versus 3600
  cells in one pilot tile.

A reviewer correctly objected that unconditional fill would hide genuinely
large burns, stickers or torn-out interiors, and proposed either increasing
tensor support or bounding cleanup in cells. Measured A/B:

- tensor support 0.30→0.60 cell reduced holes sharply and improved broad-mask
  IoU, but merged the qualified 0.4 mm pair; 1.0 and 1.5 cells also merged it
  and progressively degraded boundaries/ribbon IoU — root smoothing REJECTED;
- a maximum-hole-radius bound of 2 cells left one real 48-cell hole (radius
  2.24); radius 3 removed the complete measured dropout class;
- radius 3 and unconditional fill produced identical strict-fixture IoU and
  real counts, while radius 3 preserves every larger enclosed void.

The emitted `PayloadRegion.mask` is therefore the **bounded** topology-defined
search support from §3.4. Detection, scoring, connected components and c
voting still use raw activity. Support reconstruction occurs only after one
component has already been accepted, on its tensor grid, before native
rasterization.

Qualification additions:

- direct topology test: a small enclosed hole fills, an exterior-connected
  concavity and a larger enclosed void stay open, two components remain two;
- every exact-fixture support mask must contain zero fill-eligible holes;
- all six real confetti platens and both full sheets must contain zero
  fill-eligible holes at one sample per measured cell;
- white-margin IoU bar tightened from 0.90 to 0.97.

**Final 021.5 results: qualification 6/6 PASS in 146.8 s; unit tests 10/10;
full repository suite 375/375.**
Zero extras/misses and all c/angle results are unchanged. Mask quality improves:

| row | 021.4 min IoU | 021.5 min IoU |
|---|---:|---:|
| white margin | 0.944 | **0.988** |
| three rotations | 0.944 | **0.984** |
| healthy + faint | 0.888 | **0.987** |
| 0.4 mm gap | 0.941 | **0.985** |
| c1/c2/c3/c8/c12 | 0.950/0.961/0.950/0.905/0.810 | **0.990/0.979/0.973/0.924/0.854** |

Real outputs remain 17/10/8 pieces on both takes, all c3; e016/e017 remain one
c2/c3 region. Every real topology check reports zero fill-eligible holes.
Sheet 1 completes in 22.7 s and writes
`scratch/e021/e021-support-confetti-1.png`; its pale-blue contours now show
the useful outer support boundaries rather than thousands of internal score
pinholes.

## 11. 021.6 — coarse-authoritative boundary/gap refinement (2026-07-16)

The E018b C2 scanner pair exposed two coupled errors in the 021.5 refinement
contract.

First, a successful fine segmentation replaced the complete coarse region.
At the HP 1200-dpi C2 footing, the payload cell is only four scanner pixels.
The pitch-scale tensor therefore went quiet on many locally uniform or
one-directional payload runs and turned detector uncertainty into geometry:
the main support fraction fell to 0.8916 and a tiny second region appeared
entirely inside it. E022 saw only 449 fragmented placement windows, context
validity 0.908, and certified 741 of 1579 first-pass LDPC calls.

Second, the emergency refinement guard counted native bbox pixels before the
tensor's pitch-dependent decimation. The HP component contained 118.9 M
native pixels and refined; the physically equivalent Canon component
contained 1.91 G and skipped. Yet C2 uses decimation 1 at 1200 dpi and 4 at
4800 dpi, so both images reduce to essentially the same measured-cell
workload. The guard measured scanner resolution rather than algorithmic work.
The optional angle guard made the same mistake and was normalized at the same
time.

021.6 implements §3.3's boundary/gap tiles and removes both native-pixel
refinement caps. Measured on the E018b C2 scans:

| scan | survey scale | refinement tiles | scored / full pitch cells | E021 time | regions | main support |
|---|---:|---:|---:|---:|---:|---:|
| HP 1200 | 16.063 px | 178 | 2,514,601 / 7,560,873 (33.26%) | 4.6 s | 1 | 0.9888 |
| Canon 4800 | 64.252 px | 178 | 2,532,309 / 7,578,581 (33.41%) | 11.8 s | 1 | 0.9873 |

The small cell-count difference is ordinary scanner framing/scale, not a
code-path change. Both use the same 178 aligned refinement tiles. The Canon
run now also reaches the resolution-normalized angle arm; it returns 0.0°,
while HP returns 0.11°.

The original mask-quality matrix is unchanged: white margin 0.988, rotations
0.984, healthy+faint 0.987, qualified 0.4 mm gap 0.985, and
c1/c2/c3/c8/c12 0.990/0.979/0.973/0.924/0.854. The complete real
qualification remains 17/10/8 pieces on both confetti takes, one c2 and one
c3 full sheet, and zero fill-eligible holes. Resolution-normalized angle work
raises confetti-3 from 5 to 8 hints on both takes and gives the e016 c2 full
sheet one hint; e017 c3 still honestly returns `None`.

The exact HP E018b integration rerun used the already-committed E022
overlap-only parity optimization and the new E021 mask:

| measure | old E021 mask | 021.6 mask |
|---|---:|---:|
| E021 regions | 2 | 1 |
| E022 placements | 449 | 294 |
| held-out context validity | 0.908 | 0.979 |
| E021 time | 11.59 s | 4.27 s |
| E022 time | 400.12 s | 44.42 s |
| first-pass LDPC certificates | 741 / 1579 | 1392 / 1818 |
| fountain symbols | 741 / 1734 after BP | 1356 / 1734 without BP retry |
| final result | rank 737/737, SHA pass | rank 737/737, SHA pass |

The E022 timing reduction includes its semantics-preserving parity-allocation
fix. The certificate and symbol increase is the E021 support/placement
effect: the parity optimization changes no candidates, gates or numerical
scores. The 021.6 state recovers the 192,160-byte payload and verifies SHA-256
without adaptive BP.

Qualification after the change: **6/6 real+synthetic rows pass**; focused
unit tests are **13/13**. Added regressions pin DPI-normalized survey geometry,
enclosed-hole versus exterior-gap fusion, and the sub-survey 0.4 mm split.

### Rejected 021.6 alternatives

The final rule was not selected by inspection alone. The following
counterfactuals and intermediate implementations were measured and rejected.

**Disable refinement globally.** This is attractive for intact pages: forced
coarse-only E021 on the HP C2 scan took about 3.3 s, returned one region and
covered 0.9897 of its bbox. It also retained correct c/pitch on the synthetic
C2/C3 rows, and the full-sheet/ribbon plus null/mixed-c rows still passed.
But it weakened the general fragment contract:

| row | coarse only | qualified refinement |
|---|---:|---:|
| c2 mask IoU | 0.9195 | 0.9788 |
| c3 mask IoU | 0.9120 | 0.9727 |
| c12 mask IoU | 0.5779 | 0.8539 |
| 0.4 mm pair | 1 merged region, IoU 0.4733 | 2 regions, IoU 0.9854 |

Thus coarse-only is a useful intact-page diagnostic, not a valid replacement
for fragment boundary and separation work.

**Refine only the exterior band.** The qualified 0.4 mm pair is already one
solid component in the binary coarse mask, so no exterior-only operation can
discover its internal separation. Its coarse tensor score does retain a
long, low-valued stripe. That observation is why the final domain includes
coherent score valleys as well as the exterior band.

**Treat every three-cell low-score run as a possible gap.** The first valley
implementation did preserve all mask gates, but random payload interiors
produced 170 such runs on the HP page. Tile-neighbour closure then selected
396 tiles and scored 6,086,313 of 7,560,873 pitch cells (80.50%): correct,
but close to the full-area cost we were trying to remove. Requiring a
connected valley to span at least 25% of the component's shorter dimension
reduced HP to 178 tiles and 2,514,601 cells (33.26%) while retaining the
0.4 mm split.

**Permit fine evidence to act only inside the replacement domain.** The first
asymmetric-fusion implementation used fine evidence only where negative
boundary/gap replacement was allowed. That preserved C2/C3, but the sparse
C12 coarse support could not be completed and its IoU fell from 0.854 to
0.718. The final asymmetry is therefore one-way: positive fine evidence may
complete support anywhere in scored tiles, while negative evidence may
retract only inside the explicit boundary/gap domain.

**Tile arbitrary native 1000×1000 scan-pixel squares.** This was considered
for the long 1200/4800-dpi runs but rejected as the abstraction boundary:
native tiles represent different physical and payload-cell areas at each DPI,
and unaligned tensor filters create seam questions. The implemented
128×128 measured-pitch-cell tiles plus a four-cell halo are DPI-normalized
and align the resource bound with the actual computation.

**Repair holes only after pilot-confirmed placement.** Canonical page geometry
is useful after placement, but the HP run demonstrated that the bad mask had
already fragmented E022's search and context fit. Post-placement repair is
too late to recover work that the placement stage never attempted. E021 must
emit conservative search support; later known-format geometry may still
tighten sampling ownership.
