# Holo printer discovery and calibration

Status: implemented current contract, 2026-07-24. Synthetic plumbing and
PostScript preflight are qualified; no new printer has a hardware claim until
its own sheets are run.

This is a scratch-sheet measurement instrument. It is not a payload format,
not a receiver mode, and not a compatibility layer for E025 or the retired
Track-2 charsheet. The implementation lives only in `holo.characterize`.
Production generation and reception neither call it nor provide algorithms to
it. `holo.cli` is only the composition root that routes the `discover`
command.

## 1. Experiment audit and design rulings

The current page was designed after an explicit audit of the older printer
experiments, especially E007/DISC-1 and E025. Their source and results remain
evidence, but none of their emitter, analyzer, transport, manifest, or tests
is a compatibility input to this implementation.

The useful E025 idea was its print-time self-report. It retained language
level, default and effective `/HWResolution`, `/PageSize`, `/ImagingBBox`,
duplex/tumble, `/ProcessColorModel`, and product, interpreter
version/revision, and serial where the interpreter exposed them. E007 showed
why the default path must be printed before any resolution experiment:
guarded `setpagedevice` trials can be refused, echoed, resampled, or change
the rendering path. DISC-1's active 300/600/1200/2400 enumeration therefore
does not belong on a characterization science page. The default v2 pair
requests no `/HWResolution`; an optional request produces a new, explicitly
different footing.

The audit also recovered diagnostics that the first clean rebuild had made
too small or had omitted:

- wide, windowed local phase recovery and x/y transport rails, prompted by
  E025's measured +1.30 to +2.28-cell offsets and within-field drift;
- chiral corners plus internal geometry marks, with physical scale and
  non-affine residuals reported separately;
- a same-sheet scanner standard containing known c3 and c2 fields, horizontal
  and vertical g2 patterns, a high-entropy block, and a controlled quiet
  patch;
- per-grid, per-plane g1 and g2 rulers in both orientations, isolated dots,
  and line-pair response;
- the complete physical edge-tick ladder and independent stress/robust
  payload canaries;
- typed line, dot, white-hole, checker, slanted-edge, tone-response,
  full-profile, and morphology measurements with their numerical traces.

The audit did not justify restoring rate atlases, LDPC/FEC coupons, receiver
demonstrations, active mode enumeration, old identity panels, or visual-only
motif collections. Those answer different questions or consume area without
improving the discovery decision.

## 2. Claims and stages

The instrument makes two deliberately different measurement claims:

1. **Discovery** measures one exact printer/path/request/media and
   scanner/mode footing. It returns provisional viable authored-grid and cell
   candidates, physical diagnostics, and explicit refusals.
2. **Calibration** reprints a bounded shortlist with new copy seeds and
   position-balanced replicas. It estimates worst position within a copy and
   minima across declared print sessions.

A **same-sheet scanner comparison protocol** is also possible: analyze the
same physical sheet under separate scanner footings and compare the two
reports' capture, geometry, quiet-zone, tone, and candidate results. There is
no cross-scanner aggregation command or combined qualification verdict.

One default-request B/W and color pair discovers the default render path. It
does not enumerate hidden device modes. A non-default `/HWResolution` request
is a separate bundle and evidence footing; accepted/read-back resolution is
never physical truth.

Every result is supervised channel metrology. Known ground truth may be used
for local pose and detector training on declared populations. No number is a
blind production-receiver claim.

## 3. Dependency boundary

The package may use NumPy, SciPy, Pillow, `tifffile` for verified/memory-mapped
TIFF capture access, and its own minimal one-page PostScript writer. If
`tifffile` is unavailable, TIFF input is refused explicitly rather than
silently losing page/color/memory guarantees.
It must not import experiment modules or `holo.gen` (nor `holo.receive`,
which was retired 2026-09-05 at `284ae3e` — the firewall test dropped that
member the same day). No file under these protected paths is changed by this
work:

```
src/holo/core
src/holo/devices
src/holo/format
src/holo/gen
src/paperholo
confetti.py
pyproject.toml
```

The operator interface is:

```
./confetti.py discover emit ...
./confetti.py discover analyze ...
./confetti.py discover calibrate ...
./confetti.py discover combine ...
./confetti.py discover candidates
```

There is one current schema and one current implementation. Old E025 and
Track-2 manifests are rejected rather than upgraded.

## 4. Evidence and truth hierarchy

The report keeps three kinds of fact distinct:

1. **Authored intent** is the current page identity and candidate registry.
2. **Interpreter self-report** records what the PostScript path said before
   and after the guarded page request. It is provenance and an aggregation
   footing, not proof of native DPI, printable extent, or usable symbols.
3. **Physical measurements from the scanned sheet** are authoritative for
   scale, addressability, usable cell size, geometry, tone, registration,
   scanner adequacy, and physical or payload-safe reach.

A request, read-back value, driver label, or manufacturer specification can
never override the measured sheet. Conversely, the analyzer does not discard
self-report merely because it is not physical truth: unexpected changes in
that provenance prevent unrelated calibration copies from being combined.

### 4.1 Candidate identity

Candidate identity never collapses these axes:

```
(B/W-or-color page path, authored dpi_x, authored dpi_y, c_x, c_y,
 alphabet, planes, symbol shape, emission path, request footing)
```

Discovery's complete candidate set is implied by the one current schema.
Calibration carries only its one-to-eight explicit candidate codes. The
analyzer regenerates the complete canonical page after reading the compact
identity; a manifest is optional and, when supplied, is an independent
content-binding check.

The canonical serialization behind every semantic digest and seed label
(`model.canonical_bytes`) is format-axis: sorted keys, compact separators,
`ensure_ascii=True` (the emitted PostScript job must be pure ASCII),
`allow_nan=False`, ASCII encoding, no trailing newline. The layout digest
it produces is printed in HCAL-R1 bytes 20:36 — changing the contract is a
layout bump, never a casual edit; the page-digest goldens pin it.

### 4.2 Compact print-time report

Two thin, widely separated `HCAL-R1` strips replace the former three adjacent
fixed-format identity panels. Both carry the same 160-byte, CRC-protected
report with row sync, per-byte parity, row XOR, opposed clocks, border, and
quiet modules. Separation provides damage redundancy without paying three
times for verbose static content.

The scan-side reader is expected to spend that redundancy, not merely count
it. A module is read through a narrow sub-pixel aperture at the cell centre,
because a cell-wide aperture integrates a blurred neighbour's ink and closes
one-module white gaps; each module's distance to the slicer is its
reliability. Per-byte parity then corrects the least reliable module of an
odd-parity byte, and a surviving row XOR rewrites the row's least reliable
data byte. Both corrections are single deterministic hypotheses, so one
strip still presents exactly one payload to the CRC: the CRC and the
cross-strip consensus remain the sole acceptance gates, and an undecodable
strip is still refused.

The retained static identity is exactly:

- current report version, discovery/calibration stage, and B/W/color kind;
- request code, requested x/y resolution, and copy index;
- up to eight candidate codes for calibration (the discovery set is
  schema-implied and therefore not repeated);
- the first 128 bits of the canonical layout SHA-256.

The live PostScript portion adds:

- interpreter language level;
- default `/HWResolution` captured before the page-device request;
- effective `/HWResolution`, `/PageSize`, and `/ImagingBBox` captured after
  the guarded request;
- duplex, tumble, and process color model;
- product, interpreter version/revision, and serial number where exposed;
- explicit availability/truncation flags and a per-impression nonce.

The nonce binds the two strips to one interpreter run. String lengths are
bounded and unavailable values remain explicitly unavailable. Static identity
and live readback share one integrity envelope, but the JSON keeps
`page_identity`, `machine_report`, and `device_footing` separate so provenance
cannot masquerade as channel measurement. Calibration aggregation binds all
stable self-report fields and excludes only the per-impression nonce from the
device-footing digest.

Chiral corner satellites provide all eight rotation/mirror states before the
strips are rectified. The two valid strips must agree. If the regenerated
layout, the strips, or a supplied manifest disagree, analysis refuses.

Every stochastic field is seeded by `(schema, stage, kind, copy, field_id)`.
Two copies therefore differ in all statistical content. Outputs are
content-addressed and are never silently overwritten.

## 5. Discovery pages

The emitter writes two separate one-page PostScript jobs. They are separate
because the presence of color can change an engine's speed, screening,
registration, tracking marks, and even its handling of K.

### 5.1 Common furniture and diagnostics

Both pages contain:

- four chiral corners and internal plus marks;
- two separated compact HCAL-R1 strips and a short human header;
- controlled paper witnesses and a quiet zone;
- scanner c3/c2, g2 H/V, and entropy controls;
- x/y phase rails and internal affine-residual marks;
- full physical-ink ticks and separately scored stress/robust payload
  canaries;
- an annotation box and end sentinel.

Every element has an exact physical rectangle. Layout construction rejects
overlap and out-of-page elements.

The physical edge gaps are `0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 8,
10 mm`. Payload canaries independently test `0.5, 1.5, 2.5, 3.5, 5, 6.5, 8,
10 mm` on all four edges. Solid ink reach never substitutes for the
candidate-specific safe rectangle.

### 5.2 B/W discovery

The B/W page contains:

- large balanced K fields at three equal-physical-pitch rungs for each
  supported authored grid: 300, 600, 1200, 2400, and 1200x2400;
- compact frontier fields that test finer and coarser cells not covered by
  those matched-pitch rungs;
- explicit g1/g2 H/V grid rulers, dots, and line pairs for every grid, so
  physical scale and addressability are not inferred from BER alone;
- K c2 stress and c3 robust edge canaries with independent interior
  references;
- compact line, dot, white-hole, checker, slanted-edge, and morphology
  diagnostics;
- distributed fixed-tone and permuted response patches;
- controlled multilevel K fields whose exact sub-dot patterns are candidate
  identity;
- diagonal, horizontal-half, and vertical-half c2 symbols, plus c2x3 and
  c3x2 aspect controls at the 600 grid.

The discovery report lists every tested `(dpi_x, dpi_y,c_x,c_y)` rather than
reducing the page to one advertised DPI. The current registry contains 34
B/W candidates.

### 5.3 Color discovery

The color page contains:

- same-page K and paper controls;
- pure C/M/Y fields at matched physical pitches across authored grids;
- stress K/C/M/Y controls on the 600-class footing;
- exact CM4, triple-free CMY7, and CMY8 fields at stress and robust rungs on
  every authored grid;
- a K/C/M/Y one-hot control and a matched alternate-overprint-path control;
- separate K/C/M/Y g1/g2 H/V rulers, dots, and line pairs for every authored
  grid;
- a 3x3 distributed K/C/M/Y registration system;
- per-plane tone and selectivity anchors;
- four geometry- and PRN-matched screening controls plus a color quiet zone
  for tracking-mark evidence;
- CMY7 c2/c3 edge canaries with exact-candidate interior references.

Triple-free CMY7 is printed directly. Its performance is never inferred by
subsetting CMY8. At 600/c3, direct `DeviceCMYK-image` CMY7/CMY8 is compared
with sequential overprint (`OPM1`), so a density recommendation can account
for the emission path rather than silently treating paths as equivalent. The
current registry contains 52 color candidates.

The separate screening control holds the deterministic PRN bits and physical
geometry fixed across C imagemask, C-only `DeviceCMYK-image`, overlapping C+M
`DeviceCMYK-image`, and overlapping C+M sequential OPM1 patches. This permits
two path-only comparisons, one with C alone and one with C+M overlap. A third
comparison changes C to C+M while holding the direct DeviceCMYK path fixed;
the report labels that result as a plane-content difference, not a path
effect.

For each patch the analyzer compares observed power with the exact authored
PRN spectrum. A robust radial transfer fit absorbs ordinary resolution
falloff, after which the report gives authored/observed correlation,
off-ground-truth excess energy, and the strongest residual frequency and
angle. `summary.diagnostics.screening` reports only descriptive matched-control
deltas. It does not pronounce a universal printer screen or attribute a
stable path mechanism without repeat prints.

## 6. Calibration pages

Calibration accepts a discovery summary or an explicit bounded candidate
list. Candidate IDs come from the fixed current registry and are carried as
an explicit sorted set in HCAL-R1.

Each selected candidate appears at six Latin-square-assigned positions with a
fresh copy seed. The page retains identity, geometry, scanner-adequacy,
paper, tone, per-carried-plane authored-grid rulers, and edge references for
the selected smallest- and largest-pitch candidates, but does not repeat the
discovery zoo. A page refuses more candidates than its published area budget.

Within one copy, recommendation statistics use the worst position. Across
copies, they use the worst copy, under the strict unknown policy (ruling
2026-07-30): a candidate unmeasurable in any combined copy aggregates to an
unknowable worst case and is not recommendable — unmeasurability correlates
with badness, so silently dropping a copy would be anti-conservative. The
combined row reports `n_copies`/`n_measured` explicitly. Every
observed-vs-expected census in the report speaks one vocabulary
(`status: complete|incomplete` with `missing`/`duplicated`/`unexpected`
role lists always present). The report/summary schemas are v3;
v2 reports are rejected, never upgraded. Copies printed in one session measure content
and sheet variation but do not count as independent day/consumable sessions.

## 7. Analyzer contract

### 7.1 Hard gates

Analysis produces a structured page-level refused report, rather than
crashing or inventing measurements, when any of these fail:

- fewer than three identified corners;
- HCAL-R1 CRC/framing and consensus across valid strip placements;
- compact printed identity, regenerated layout, and supplied-manifest binding;
- required infrastructure visibility;
- color page supplied as a non-color scan;

Candidate-local failures remain explicit without destroying unrelated
evidence. Insufficient measured samples/cell produces `unmeasurable`; failed
local pose certification produces `geometry_uncertified`; and missing or
failed exact references suppress only the dependent edge/capacity claim.
Clipped content is `unobservable`, never interpolator-clamped evidence.

### 7.2 Geometry

Corner marks yield orientation, mirror state, global affine, absolute scale,
and scan samples per layout dot. Internal marks report residuals.

Every statistical field is split into roughly 4.7 mm physical windows. Each
window solves local phase from its **fit** population over a ±2.6-cell wide
search that covers the multi-cell offsets observed by E025, then must pass an
independent **certification** population. Composite color fields solve
separate C, M, and Y offsets before joint classification. An unresolved
window remains in the report but contributes no candidate qualification.
Candidate qualification is deliberately local-tail conservative: both the
whole-field Wilson upper bound and the worst measured window's Wilson upper
bound must remain below 8%. A clean page average therefore cannot hide a
collapsed transport band.

For a binary plane, the phase fit also learns the realizable density threshold
that minimizes fit-population classification error. It does not assume that
the midpoint of the two class medians is valid. The learned threshold is then
frozen and evaluated on the independent certification population.

### 7.3 Statistical isolation

Element-global coordinate hashes create four disjoint, spatially mixed
populations:

1. geometry/phase fit;
2. geometry/phase certification;
3. detector training;
4. untouched reporting.

The analyzer asserts disjointness, coverage, state support, and row/column
mixing. Report cells never select geometry, detector, candidate, or threshold.

The declared portable detector is regularized QDA over native-reflectance
density features. Reports retain confusion matrices, per-level error,
empirical mutual information, class errors, sample counts, window
overdispersion, worst-window error and confidence bound, geometry adequacy,
and measured samples/cell. Native scan dtype and capture bytes are retained
as footing; there is no capture-wide percentile normalization on the
numerical path.

### 7.4 DPI and scanner decisions

True scanner DPI is required. For each authored grid the report combines:

- absolute printed scale;
- H/V ruler and grating response;
- measured samples/cell;
- held-out performance at each printed cell size;
- equal-physical-pitch comparisons with lower authored grids.

Ruler gates are candidate-specific: a candidate is eligible only when every
plane it uses passes both ruler orientations. A sharp K ruler therefore
cannot certify C/M/Y addressability.

The scanner-adequacy verdict separately requires the controlled quiet patch,
c3/c2 transfer blocks, both g2 orientations, and the entropy block to be
present and numerically healthy. This distinguishes an inadequate capture
footing from a printer candidate that genuinely collapsed.

Terms are intentionally conservative:

- `scaled`: physical scale differs materially from the authored grid;
- `unmeasurable`: the scanner footing provides fewer than four measured
  samples/cell for a graded result;
- `collapsed`: held-out error is at least 20%;
- `fragile`: 8–20%;
- `marginal`: 1–8%;
- `solid`: below 1%.

“Four measured samples per cell” means the affine-measured scan-pixel area of
the cell (`samples_x × samples_y`), while both axis values remain in the
report.

The report names the highest useful authored grid on this exact request
footing and the smallest tested usable cell at every grid. It does not call
that grid a manufacturer-native resolution.

### 7.5 Edge and capacity decisions

Physical ink reach and payload-safe reach remain separate. Edge qualification
requires:

- a healthy exact-candidate interior reference;
- complete stress and robust arms;
- all more-inboard gaps to pass;
- conservative Wilson upper bounds;
- full scan visibility.

At each gap there is one arm for each of the two extreme carried candidates;
the gap index is not replicated evidence.

An incomplete edge yields no rectangle. Capacity is reported only for the
measured rectangle and only as raw and empirical-information density.
Production furniture, coding, fountain recovery, and archive lifetime remain
outside this instrument.

## 7b. Margin/verdict amendments (2026-08-04, report schema v4)

The first physical pair (experiment 028) plus the same-day forensic
session (docs/CHARACTERIZE-WORKPLAN.md) forced four normative changes.
Reports are schema/analyzer version 4; v3 reports remain readable
history but are refused by `verify_analysis_report`.

- **Registered tick verdicts (W1).** The v3 rule
  `solid_density_p05 >= paper + 0.05` demanded the whole nominal 28-dot
  window be ink (~1.4 dots displacement tolerance) while measured
  displacement is 1-3 dots; it failed 12 of 16 solidly printed 5-10 mm
  ticks on the e028 B/W sheet and is retired-with-reason.  Ticks are
  now graded on the ink coverage of a bounded-translation REGISTERED
  footprint (`probes._edge_tick_registration`): absent < 0.10, full
  >= 0.85, partial between; each tick records its ink fractions and
  displacement.
- **The print margin is the clip line (W2c; D1 dissolved by user
  ruling).** Partially printed ticks yield layout-referenced
  `clip_mm_estimate`s; per edge the analyzer reports
  `printable_clip_mm` (median of partial estimates, else the
  absent/full interval midpoint) with honest bounds.  Layout
  coordinates convolve the engine margin with the impression's
  print-to-paper registration; copy variance belongs to calibration.
- **Payload edge canaries are data, not verdicts (W3).**
  `passed`/`exact_references_ok`/`safe_gap_mm`/
  `safe_payload_rectangle_mm` are deleted: one interior worst-window
  tail could veto every edge product on the page (e028: candidate 4 at
  9.02% vs the 8% gate zeroed a ladder whose c3 arms read 1.5-1.8%
  Wilson upper at 5 mm+).  The curves keep per-gap error data plus
  `edge_penalty` against the interior reference and a descriptive
  `edge_flat_gap_mm`.  Capacity is a table parameterized by margin
  choice (`capacity_by_margin_mm`, standard margins + the measured
  clip); margin POLICY is a devices/profiles decision downstream.
- **Planning metrics (W4).** Candidate rows gain window-BER quantiles,
  per-state error rates, and tier definitions ride the summary;
  `rung_planning` maps quantiles onto the local e-IRA ladder constants
  as a labeled hard-decision ESTIMATE (tails price fountain overhead,
  never qualification).  The calibration shortlist collapses
  equal-pitch twins to one physical representative per club and
  surfaces club spread as position variance (e028: 300-c1 vs 600-c2
  straddled the 8% gate on the same 84.7 um channel).
- **New geometry evidence.** `registration_map` collects per-object
  displacements (ticks, patterns, plus marks); `geometry.paper_edges`
  locates physical paper edges where background is visible, separating
  print-to-paper registration from paper-on-platen placement (e028:
  content skewed ~0.3 deg on the sheet, paper flush).

## 8. Deliberate exclusions

The pages do not contain:

- an LDPC rate atlas or a code-rate recommendation;
- active resolution enumeration inside one science job;
- advertised/read-back DPI as authority;
- CMYK16, generic per-plane four-level alphabets, or a motif zoo;
- large RLL/trellis demonstrations;
- payload-generator or receiver replay;
- global-normalized-darkness detection;
- visual-only probes without a numerical analyzer.

Production compatibility coupons can be added later only through a separately
qualified adapter. They are not needed to answer the discovery question and
are excluded from the clean dependency boundary.

## 9. Qualification before hardware claims

The current automated battery covers:

- deterministic plans and independent copy seeds;
- overlap/page-bound/job-size refusal;
- default-request and separately identified requested footings;
- Ghostscript B/W and color round trips;
- manifestless HCAL-R1 identity under all rotations and mirrors;
- wrong-manifest, missing-end, blank, malformed-input, and non-color-scan
  refusal;
- all declared authored-grid plans, insufficient samples/cell, and scaled
  raster verdicts;
- RGB/CMYK and single-page/memory-bounded TIFF input contracts;
- per-plane rulers, color registration/selectivity, multilevel motifs, and
  skewed-density phase fitting;
- split nondegeneracy and conservative calibration copy/session aggregation.

Before a physical device profile is promoted, its recorded stress battery
must additionally cover:

- scan noise and crop variants;
- smooth warp, discrete y-step, and greater-than-half-cell per-plane offsets;
- validation-label noninterference;
- leading-edge degradation and dead-reference edge refusal;
- separately seeded copies across every claimed session/consumable footing.

Synthetic success qualifies software plumbing, not printer physics. A device
profile remains provisional until independently seeded sheets have been
printed and analyzed through a declared reference scanner.
