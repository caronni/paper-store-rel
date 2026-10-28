# 06 — Capture intake + survey (functional spec for holo3)

Sources distilled: `holo2/src/holo2/capture/{ingest,scan,footing_raster,
scale_space,survey,_survey_tensor,lattice,records}.py`,
`src/holo/receive/{survey,scale_space,cascade,production(survey stage),
runtime(capture drive)}.py`, memories `e023b-integrated-receiver`,
`e023c-scale-space-receiver`, `e021-payload-regions`, CLAUDE.md channel facts.

## 1. Purpose, inputs, outputs

Purpose: turn operator-declared scan files into (a) immutable per-plane u8
rasters at every rung of a per-capture scale ladder, mmap-openable by any
worker, and (b) one E021 survey per capture: payload regions (block-constant
support masks in native pixels) plus one platen-wide printed-pitch vote.
Everything downstream (place/pose/detect) reads only these products.

Inputs (CLI):
- scan paths: single-page TIFF (preferred; memory-mapped via tifffile) or
  PNG/other via PIL. Accepted pixel forms: 2-D grey u8, 3-D RGB u8
  (H,W,3). The whole acceptance corpus is u8 (verified: xerox 4800 grey
  56128x40832 u8, xerox 4800 RGB u8, sheet I 2400 RGB u8). RGBA/CMYK/
  multi-page: not supported.
- `--dpi FLOAT` — operator-declared true scanner DPI, one value for the
  whole run (one ordinary state freezes one DPI; see §4).
- format identity (row/`--format`) supplies `pitch_in: Fraction` (printed
  cell pitch in inches; c-class pitch is `Fraction(c,600)`) and the codec
  family (K / cmy7 / cmy8).

Outputs (per capture, all under the disposable run dir):
- `Capture`: capture_id = SHA-256 hex of the encoded file bytes (THE
  acquisition identity), dpi: float, shape_px: (int,int) native (h,w),
  channels: 1|3, platen_backing: float, levels: tuple[Level,...].
- Per level, per plane: one `.npy` file, u8, C-order, 2-D. Grey capture:
  plane `g`. RGB capture, colour family: planes `r`,`g`,`b` (scan
  channels, NOT printed inks — see §3). K family additionally gets one
  derived luma plane `y` per sub-native level (native K luma is computed
  at crop time from the channel planes, never stored — storing u8 would
  re-round).
- `CaptureSurvey`: regions tuple[Region,...] sorted by descending
  area_mm2, pitch_class: Fraction|None, pitch_px: float|None (median
  measured), votes (diagnostic).
- Diag events: capture.open{sha,dpi,shape,channels},
  survey.complete{n_regions,pitch_class,pitch_px}, level.derived{label}.

## 2. Algorithm

### 2.1 Ingest one scan
1. sha256 the encoded file bytes in 4 MiB (1<<22) chunks → capture_id.
2. Decode: `.tif/.tiff` → tifffile single page `asarray(out="memmap")`;
   else PIL (set `Image.MAX_IMAGE_PIXELS = None` while decoding). Squeeze
   (H,W,1)→(H,W). Require u8 grey or u8 RGB.
3. Write native planes: grey → one `g.npy`; RGB → split channels into
   `r.npy`,`g.npy`,`b.npy` (each `np.ascontiguousarray(a[...,k])`).
   Workers reopen with `np.load(mmap_mode="r")`.
4. platen_backing = `float(np.median(concat of four 32-px border strips
   of the native luma)))`, border = min(32, h, w); luma per §2.2. Used by
   place to fill unsupported pixels.
5. Duplicate sha in one run = the same capture: keep the first, drop the
   repeat (holo1: exact duplicate is a no-op).

### 2.2 Luma (the E021/E018 photometric law)
- Native luma crop of an RGB capture: `(R + G + B)` accumulated in
  float32, `/ 3` — bit-equal to
  `pixels[...,:3].mean(axis=2, dtype=np.float32)` on interleaved data.
  Grey: `astype(np.float32)`. This equal-channel mean IS the K plane's
  registered photometry; do not invent luminance weights.
- Colour-lane luma (survey/address on colour rungs): mean of the three
  STORED per-channel rung planes in float32 (decimate-then-mean, matching
  holo1 `ColorScaleRaster.crop_luma`), which is NOT mean-then-decimate.
- K-lane sub-native luma (E018 frozen order, byte-law): from the native
  channels compute `(R+G+B)` in float64 `/3` (equal to
  `block[...,:3].mean(axis=2)`), `astype(np.float32)`, THEN box-mean.

### 2.3 Scale ladder (auto_ppc_levels — copy, do not re-derive)
Constants: `_MINIMUM_PPC = Fraction(2)`.
1. `native_ppc = Fraction(dpi_as_decimal_string) * pitch_in` (floats go
   through `Fraction(str(float(v)))` — NEVER `Fraction(float)`; binary
   expansion forks the ladder). Use the holo2 pitch form, not
   src/holo's `cell_dots * dpi / 600` (identical wherever pitch = c/600;
   the 600 hardcode is the retired engine-grid assumption).
2. If `native_ppc <= 2`: ladder = (native_ppc,).
3. Else start at 2 and repeat: `divisor = ceil(native/(2*current))`;
   `following = native if divisor <= 1 else native/divisor`; if
   `following <= current`: `following = native`; append. Ends AT native
   exactly once, never upsamples. Examples: c2@2400 → 2,4,8; c2@4800 →
   2,4,8,16; c3-cmy7@2400 → 2,4,6,12; c3@1200 → 2,3,6.
4. Per level: `scale = native_ppc / ppc` (= source pixels per output
   pixel, a Fraction ≥ 1; on this corpus always an INTEGER factor),
   `dpi_level = ppc / pitch_in`, label `l{index:02d}-{ppc}ppc-{dpi}dpi`
   (Fractions rendered `num-den` when den≠1).
5. Output length per axis: `len * den // num`; incomplete trailing
   pixels are DISCARDED. Pixel-centre map: `source = scale*(view+0.5) -
   0.5`; affine columns scale by `1/scale`, translation
   `(t+0.5)/scale - 0.5` (copy AreaPixelTransform verbatim — every pose
   crossing levels goes through it).

### 2.4 Rung derivation (native → decimated, ALWAYS; never level-from-level)
Every sub-native plane is derived directly from the native plane with the
frozen E018 u8 integer-box kernel (`_uint8_integer_box_rows` semantics):
1. For factor f, complete output rows y0:y1, full output width W:
   `block = src[y0*f:y1*f, :W*f]` (2-D u8 plane) → `astype(float32)` →
   `reshape(rows, f, W, f).mean(axis=(1,3))` (float32 accumulation) →
   `.round()` (round-half-to-even) `.clip(0,255).astype(uint8)`.
2. Full-width rows only — narrow x-slices change float32 tie rounding
   (documented in the source). Row-chunk it (holo1 used at most
   `max(1, 256//f)` output rows per chunk; any row chunking is
   value-neutral) straight into the target `.npy` opened as a w+ memmap.
3. K family on RGB: apply §2.2's float64 RGB mean BEFORE the float32 box
   mean, store one `y.npy` per sub-native level. Colour family: run the
   kernel independently per channel plane (`area_decimate_rgb_into`
   semantics) → `r,g,b.npy` per level. Native level stores no derived
   copy (native IS the scan).
4. The rational/non-u8 kernels (exact int64 overlap numerators,
   ties-to-even `_round_ratio_int64`, python bigint fallback, float64
   separable path) are only reachable off the u8/integer-factor corpus —
   see open question Q1 before dropping.

### 2.5 Level frames (footing-frame arithmetic, exact integers)
For mapping native-denominated survey geometry into a rung with
`scale = p/q`:
- pitch in rung px: `native_pitch_px * q / p` (float; exact at native).
- native bbox → rung pixels wholly inside it: first kept `ceil(y0*q/p)`,
  one past last `floor(y1*q/p)`; empty → the region has no pixels at
  this rung.
- support at rung pixel j: centre = `(p*(2j+1) - q) // (2*q)` (integer
  arithmetic), supported iff the native pixel containing that centre is
  supported (same centre rule place uses one level up).

### 2.6 Survey (E021, once per capture, on the NATIVE raster)
Constants: SURVEY_CELL_UM=340.0, DENSITY_MIN=5, MIN_AREA_MM2=9.0,
C_SNAP_TOLERANCE=0.04, SUPPORT_HOLE_RADIUS_CELLS=3.0,
REFINE_BOUNDARY_SURVEY_CELLS=2, REFINE_VALLEY_FRACTION=0.65,
REFINE_VALLEY_RUN=3, REFINE_VALLEY_MIN_SPAN_FRACTION=0.25,
REFINE_VALLEY_HALO_SURVEY_CELLS=1, REFINE_TILE_CELLS=128,
REFINE_TILE_HALO_CELLS=4, survey probe ladder PITCH_PROBES_PX =
(2,3,4,6,8,12,16,24,32,48,64,96,128) (the survey's OWN 13-entry list —
lattice.py's 9-entry default is not the one used here).
Tensor constants (_survey_tensor): WORK_CELL_PX=4.0,
DERIVATIVE_CELLS=0.22, TENSOR_CELLS=0.30, TENSOR_TILE_CELLS=256.
Lattice constants: CONTRAST_FLOOR=30.0, MEASURE_WINDOW_PX=2048,
RATIO_TOLERANCE=0.08, DEDUPE_TOLERANCE=0.02, radial floor 0.01 (reject
periods > 100 px).

1. `px_per_mm = dpi/25.4`; `survey_pitch_px = 0.340mm * px_per_mm`.
   `tensor_geometry(cell_px)`: decimation = max(1, round(cell_px/4.0));
   work_pitch = max(1, round(cell_px/decimation)); native step =
   decimation*work_pitch. Refuse (empty survey) if min(shape) <
   4*survey_pitch_px.
2. Whole-platen activity score: tile the output grid in 256-cell tiles
   with halo = ceil((int(4*deriv_sigma+0.5) + int(4*tensor_sigma+0.5)) /
   work_pitch) cells; per tile crop luma, block-mean by `decimation`
   (float32, trailing partials dropped), then the structure tensor:
   deriv_sigma = max(0.6, 0.22*pitch_work), gaussian d/dx and d/dy
   (order (0,1)/(1,0), mode nearest) each MULTIPLIED by deriv_sigma;
   tensor_sigma = max(1.0, 0.30*pitch_work); smooth gx², gy², gxgy;
   minor eigenvalue sqrt(max(0, (trace − sqrt((jxx−jyy)² + 4 jxy²))/2));
   box-mean by `work_pitch` → one float32 score per step-px cell. Tiles
   are pure over frozen bytes and write disjoint slices — parallel-safe.
3. Threshold: log-space Otsu — v = log1p(score) finite values; if empty
   or max ≤ 0 → inf (no components). histogram 256 bins, between-class
   variance argmax over centres[:-1], threshold = expm1(centre). (The
   one E021 correction: guards the zero-plane arbitrary-range case.)
4. Active mask: score > threshold AND 3x3 neighbour count (uint8
   convolve, constant 0 boundary, self included) >= 5. Label
   (4-connectivity default), drop components with area <
   9.0 mm² (cell area = (step_px/px_per_mm)²).
5. Pitch vote per component, largest activity first: crop = component
   bbox in native px; skip if min side < 32 px; if min side > 2048 take
   the central 2048x2048; luma per §2.2 (u8 corpus: no /256 branch).
   `measure_cell_pitch`: for each probe with min side >= 8*probe,
   band-limited (±1 octave) gradient-comb estimate — float64 image,
   np.gradient, hypot, subtract mean, 2-D Hanning, |rfft2|, radial
   eligibility, argmax peak; contrast = peak / median of >0 in-band bins
   (subsampled to ≤65536); keep lines with contrast ≥ 30, dedupe within
   2%, choose the LARGEST pitch for which every other strong line is an
   integer division within 8%·k (harmonic-consistency rule — the
   strongest peak is routinely a harmonic; never take argmax-contrast
   first), courtesy fallback max-contrast. Candidate lines = strong
   lines + the chosen fundamental; snap each: candidate pitches =
   CANDIDATE_PITCHES_IN = (1/600, 1/300, 1/200, 1/150) inch UNION the
   declared row's pitch (append + sort only when it is not already a
   member — the H1(b) "ask what the producer knows" rule); snapped iff
   relative error of pitch_px vs `float(pitch)*dpi` ≤ 0.04, nearest
   first-wins; the component votes its largest SNAPPED pitch.
6. Global pitch: majority over component votes; a tie → no pitch
   (None); pitch_px = median of the winners' measured px; if a class
   won but no px measured, pitch_px = float(class)*dpi. LAW: the
   measured pitch_px steers survey refinement ONLY; geometric truth
   downstream is always `pitch_in * dpi` from the declared row
   (don't-measure-known-quantities: page-fit pitch wanders, 5.92 vs
   6.00).
7. Boundary refinement per component (only when pitch_px is known):
   halo = round(max(2*pitch_px, px_per_mm)); skip if refined extent <
   4*pitch_px. Build the fine grid at step from
   tensor_geometry(pitch_px); base = coarse support (hole-fill radius
   max(1, 3.0*pitch_px/survey_step)) resampled by the centre rule;
   domain = dilate(2)−erode(2) boundary band ∪ coherent valleys (score ≤
   0.65·median, opened with 3-long line/diagonal structures, components
   with max side ≥ max(3, ceil(0.25·min(component shape))), dilated 1);
   select 128-cell tiles touching the domain, dilate selection 3x3;
   re-score each selected tile with a 4-cell halo via the same tensor on
   exact native crops; re-threshold (log-Otsu over known cells), keep
   active components touching base; merge: candidate = base ∪
   (active∧known), replace inside domain∧known by active, re-add
   base-enclosed holes; relabel, drop < 9 mm², hole-fill radius
   3.0*pitch_px/step; emit refined regions (origin, fine step, extent
   clipped at raster bounds, median score over evidence cells). A
   component whose refinement yields nothing falls back to its coarse
   support at survey_step.
8. Region admission = survived area floor after refinement. Output
   Region: origin_yx (native px, ≥0), step_px, cells (2-D bool, ≥1 true),
   extent_px (clips last row/col at capture edge), area_mm2 (exact,
   counting clipped edge cells), median_tensor_score. Sort descending
   area. A capture with pitch_class None admits regions but schedules no
   windows (place refuses; the survey never invents a pitch).

### 2.7 Cascade / when a level opens (scheduling FUNCTION for engine.py)
- Cost tiers, coarse→fine: tier(level k) < tier(level k+1); within one
  tier all captures interleave (holo1 D1/D2 rung-major: every capture's
  2-ppc work precedes anyone's 4-ppc work — coarse rungs are ~1/16 the
  pixels and their certificates suppress fine work).
- A level's jobs become eligible when its plane files exist (intake
  derives the whole sub-native ladder up front, ~1/3 extra pixels
  total) AND the same capture's previous level has quiesced: no eligible
  job of the coarser level remains in the frontier. No persistent
  barrier object, no journal — quiescence of the in-memory worklist IS
  the barrier.
- What crosses a level boundary: certificates (authoritative; a
  certified tile key gates out every finer-level payload attempt on any
  capture — the residual-NeedMap law, measured −40% CRC calls at equal
  yield); committed poses cross as HINTS re-validated against the
  current rung's raster (never as facts); calibration/LLR evidence
  NEVER crosses (levels of one capture are correlated views; summing
  them double-counts — e023b law).
- A refusal at one level (survey empty, no addressable window) is
  recorded and the cascade proceeds finer — coarse failure is normal
  for damaged captures.
- Tried-set floor: a job key = (window, level, evidence-epoch of the
  facts it reads); once fired it re-enters only when a fact in its read
  set changed (new neighbouring certificate, new pose, new calibration
  epoch). Mop-up/refine/uplift passes are the payload/refine specs'
  business; intake's only duty is that base-level rasters remain
  openable by label for the whole run (files in the run dir — trivially
  true).

## 3. Where plane separation happens
NOT here. Intake planes are SCAN channels (r,g,b) — aligned, identically
decimated. Printed-ink planes (C,M,Y) exist only as detector outputs: the
colour head samples all three channel planes per cell and estimates
per-plane ink presence statistically (QDA/calibrated heads, spec 0x of
the detect subsystem). Rationale: ink↔channel is not a pixel transform
(cross-coupling, per-state calibration), and per-channel geometry must
stay independently addressable for the plane_fields/color_field ARMS
(dial-off; every colour close predates them) — their API need from
intake: (a) per-channel crop access at every level, (b) the exact
AreaPixelTransform of the level so a per-plane pose delta expressed in
native dots maps into rung px, (c) nothing else. Do not bake any
channel mixing into stored planes.

## 4. Measured-channel invariants that MUST survive
- One ordinary state freezes one DPI (e023b): one run, one --dpi for
  all scans — a corrected DPI is a different interpretation of the
  evidence, not a resume.
- Never raw+decimated of the same capture as two inputs (e018/e023b):
  derived copies are correlated evidence with different shas; only the
  ladder may decimate. Duplicate-sha input = same capture.
- Rungs derive native→decimated, never level-from-level: ppc is the
  cross-capture correspondence; recursive resizing accumulates rounding
  and forks evidence identity.
- The frozen E018 u8 operation order (float32 box mean, .round(),
  full-width rows): byte-law pinned by goldens; a one-ULP change forks
  every decimated observation.
- Ladder starts at 2 ppc: the coarse rung is where most certificates
  are born (e023c: 671/754 and 1310/1438 at the coarsest level) — do
  not "optimize" it away because native looks better.
- Canon 4800 optics ceiling ≈ 860 dpi information (knife-edge MTF10 ≈
  17 lp/mm, e028): native 4800 adds sampling, not information — the
  ladder's coarse rungs are near-lossless, which is WHY the cascade
  pays; legacy paperholo receivers get 1600-decimated files, holo runs
  its own ladder from native. 8px/dot ~halves BER vs 2px/dot: sampling,
  not the detector, sets the floor — u-lanes bind to the FINEST rung.
- Equal-channel-mean luma is the registered K photometry (E021).
- LLRs never sum across correlated views; independent captures may sum
  calibrated LLRs only after the ctx detector de-correlates (F1∘F6
  law) — enforced in detect, enabled here by honest capture identity.
- Survey pitch snap tolerance 4% with candidate classes ≥25% apart:
  every accept is unambiguous; refusing an out-of-set measurement is
  correct (a lattice no row spells decodes nothing).
- Declared pitch joins the candidate set (H1(b)): a survey that was
  told the answer must not discard it.
- Region admission floors (9 mm², 5-of-9 density) are the qualified
  E021 numbers; the log-Otsu zero-plane guard is a real incident fix.

## 5. DROP (aggressive)
- All of records.py: KeySpec/ResourceKey/RecordFamily machinery, commit
  wall, transition freezes (F-08/Q2 refusals), collections, scan_key/
  attachment_key, blob sidecar + staged blobs, SupportRun RLE.
- IngestWorker / capture_facts-vs-ingest_capture split / spend ledger /
  empty-read-set doctrine — holo3 intake is a plain function called at
  startup, one capture at a time (memory budget: the survey transient
  is ~8x raster; one in flight).
- verify_source_unchanged, stat-memo re-authentication, SourceId
  post_init validation, _freeze_native/borrowed-array copies, luma_max
  scan + the /256 16-bit branch, non-finite scans, shape/dtype guard
  towers (charter: no defensive guards; u8 in, u8 out).
- footing_raster content-addressed digest names, FOOTING_FORMAT tag,
  .partial temp-and-replace, stands()/size-completeness, reuse-only
  open path — run dir is a disposable cache; simple names
  `{sha12}/l{level}-{plane}.npy`, rebuilt every run.
- DerivedLanePool + WeakKeyDictionary + LazyDerivedRaster deferral +
  release bookkeeping; ScaleRaster/ColorScaleRaster wrapper classes and
  their re-validation — a PlaneRaster is a path + shape + an mmap open.
- LaneSpec plan records, M/R/U empty survey mints, SurveyArtifact/
  region_id strings, per-lane survey (§2.6 runs once per capture),
  survey transient=persist metadata, diagnostics beyond the three
  events in §1.
- Session/state: resume, duplicate-capture conflict taxonomy,
  CaptureStatus, page-domain validation, capture-groups, defer-close
  plumbing, event authority tiers, snapshot factories.
- Rational Rational|str coercion surface: dpi is float, pitch_in is
  Fraction from the format row; `_fraction(str(float))` survives only
  at the native_ppc seam.
- Multi-page TIFF handling, PIL mode zoo beyond L/RGB, Pillow limit
  lock (set once at import).

## 6. holo3/data.py needs
- Capture: capture_id (str sha256), path (Path), dpi (float),
  shape_px (int,int), channels (1|3), platen_backing (float),
  levels (tuple[Level,...]), plane_dir (Path).
- Level: index (int), ppc (Fraction), scale (Fraction — native px per
  level px), shape_px (int,int), label (str).
- PlaneRaster: capture_id, level_index, plane (Literal
  "g","r","b","y"...; grey scan uses "g"), path, shape_px; `open() ->
  np.ndarray` (np.load mmap_mode="r"). Workers each open their OWN
  view (free-threading refcount contention).
- Region: capture_id, origin_yx (int,int native px), step_px (int),
  cells (read-only bool ndarray), extent_px (int,int), area_mm2
  (float), median_tensor_score (float).
- CaptureSurvey: capture_id, regions (tuple[Region,...]),
  pitch_class (Fraction|None), pitch_px (float|None).
- Consumed downstream: place needs Region + Level frames + declared
  pitch; detect needs PlaneRaster crops per channel; certificates carry
  source tag = producing plugin (intake produces none).
- Stateful/shared: intake writes files + Capture/Survey facts —
  run it serially in the main thread before the frontier starts (or as
  tier-0 jobs whose results merge single-writer). Tensor tiles inside
  survey are pure/disjoint if parallelized. Everything else here is
  immutable after intake.

## 7. Pitfalls / incidents
- Fraction(float) forks the ladder (holo2 C3 review fix): 0.1 becomes a
  huge binary ratio → different ppc levels → different geometry. Always
  Fraction(str(float(v))) at the dpi seam; pitch_in arrives exact.
- Misdeclared DPI (e033): survey voted c4 while the spec said c2 —
  clean refusal, not a decode attempt. Keep the one comparison: if
  pitch_class is not None and differs from the declared row's pitch,
  refuse the run naming both. Cheap, catches wrong --dpi (a 2x dpi
  error maps the measured pitch to a different class).
- Strongest spectral line is routinely a harmonic (E021/E022): the
  harmonic-consistency largest-credible-pitch rule is load-bearing; a
  "cleaner" argmax re-implementation votes 2x pitch on c3 sheets.
- Log-Otsu zero-plane: numpy's arbitrary histogram range on a flat
  score minted a negative threshold and a phantom full-page component.
- Narrow-x float32 tie rounding in the u8 box path: decimate full
  output rows only.
- e018 find_objects/segment bug + E021.6: full-area fine segmentation
  once replaced coarse support and punched holes in real regions — the
  refinement is boundary/valley-scoped ON PURPOSE (coarse-authoritative
  interior).
- Scanner JPEG (AltaLink default) erases <5-dot features and misfires
  context detectors on block boundaries — corpus doctrine: only
  lossless Canon captures; scanner JPEG == scan+encode, nothing to
  "characterize" here. Home flatbed COLOR lays an 11.3 px comb — never
  a colour source. These are operator doctrine, not code.
- Survey cost trap (kiss note in lattice.py): a naive 512·probe FFT
  window is quadratic; the bounded 2048 central crop is the affordable
  form. Do not "improve" coverage.
- pyflakes the tree (PLANE-FIELDS: first sweep caught 2 real bugs).

## 8. Open questions for the contract author
- Q1: may holo3 hard-commit intake to u8 + integer box factors and drop
  the exact-rational int64 / bigint / float64 decimation kernels
  entirely (~200 lines)? Every acceptance scan is u8 and every
  auto-ladder factor on integer-dpi Canon scans is an integer; the
  rational path is dead code unless a future dpi/pitch combo makes
  native_ppc odd at the 2-ppc rung (e.g. any dpi where dpi*pitch is
  not even).
- Q2: survey cadence — holo1 surveyed per ordinary LANE on the lane's
  raster; holo2 ruled once-per-capture at native (this spec). Regions
  then reach coarse levels through the centre-rule frame map instead of
  a fresh coarse survey: not bit-identical region geometry to holo1's
  colour closes (certificates, not regions, are law — but confirm this
  is an accepted divergence for acceptance runs 3–7).
- Q3: does the plan's "per-plane u8 .npy" include the derived K-luma
  rungs as materialized planes (this spec: yes, `y.npy` per sub-native
  level) while native K luma stays a crop-time float32 mean? Storing a
  u8 native luma would change values vs the E021 contract.
- Q4: who owns the mop-up (M) semantics in holo3 — a distinct pass per
  level after native, or does the frontier's fact-driven re-eligibility
  subsume it (holo2's pull model did)? Intake is indifferent; the level
  list it hands the engine should not encode M/R/U rows.
- Q5: platen_backing consumer check — if holo3 place samples windows
  straight from plane mmaps (no prepared-plane files), backing is
  needed at window sampling for unsupported fill; confirm it stays a
  Capture scalar (median over four 32-px borders) and nothing hashes it.
- Q6: multi-capture with mixed declared DPIs — refuse outright (this
  spec's reading of one-state-one-DPI) or allow per-capture DPI as
  holo1 mechanically did? All acceptance decodes are single-DPI.
- Q7: is the declared-vs-voted pitch-class refusal (§7, e033) wanted in
  the no-guards charter, and does a pitch_class=None survey refuse the
  run or proceed (holo1: regions unschedulable ⇒ decode dies later with
  zero certificates; a decode with a declared row could also proceed on
  declared truth alone)?
- Q8: RGB scans decoded as K family (none in acceptance): keep the
  §2.2/§2.4 K-on-RGB luma path, or refuse K decodes of RGB captures?

## Copy-vs-rewrite table
COPY-AND-STRIP (bit-exact format law or hard-won numerics; strip
docstrings/guards only, never arithmetic):
| what | source |
|---|---|
| native_pixels_per_cell + auto_ppc_levels (pitch form) | holo2/src/holo2/capture/scale_space.py:95–159 |
| AreaPixelTransform (centre/affine maps, output_shape) | holo2/src/holo2/capture/scale_space.py:162–243 |
| _source_interval + frozen u8 box rows | holo2/src/holo2/capture/scale_space.py:332–360 |
| chunk iterator + area_decimate_into (+_rgb_into) | holo2/src/holo2/capture/scale_space.py:666–743,765–803 |
| exact int64/rational/float fallbacks (pending Q1) | holo2/src/holo2/capture/scale_space.py:363–548,551–663 |
| structure tensor (geometry, minor-eigen, halo, tiling) | holo2/src/holo2/capture/_survey_tensor.py:27–213 |
| lattice estimate + measure_cell_pitch | holo2/src/holo2/capture/lattice.py:25–228 |
| E021 survey: constants→survey_raster (Otsu, components, votes, refinement, SupportMask) | holo2/src/holo2/capture/survey.py:70–139,142–231,306–898 |
| candidate_pitches + CANDIDATE_PITCHES_IN | holo2/src/holo2/capture/survey.py:89–126 |
| _raw_luma / tiff+PIL load / sha256 chunk hash | holo2/src/holo2/capture/scan.py:73–77,267–283,286–349 |
| platen_backing | holo2/src/holo2/capture/ingest.py:166–191 |
| FootingFrame maps (pitch_px, extent, support centre rule) | holo2/src/holo2/capture/footing_raster.py:280–363 |

REWRITE LEAN: open/ingest driver (§2.1), plane .npy writer/opener, ladder
derivation loop (§2.4 orchestration around the copied kernels), Region/
Capture dataclasses (§6), survey once-per-capture wrapper + region tuple,
level frame construction, the three diag events, the rung-major frontier
tiers (§2.7). Reference-only (do not copy): src/holo/receive/cascade.py
(lane plan/pool machinery), runtime.py capture drive, production.py
survey stage, holo2 ingest.py workers/records.
