# 08 — Pose + refinement (functional spec for holo3)

Sources: `holo2/src/holo2/solve/{pose_fit,pose_audit,geometry,refine,refine_fit,prepared}.py`,
`src/holo/receive/certified_refine.py`, `place_model.py`/`place_admission.py` (constants),
`place_shared.py` (frames), `color_field.py`+`plane_fields.py` (ARM seam), REASONING-LOG +
e024 memory.

## 1. Purpose, inputs, outputs

Four receiver functions: window pose FIT (blind lattice + phase, per window/footing,
plane-common); the CELL READ (one order-1 interpolation through the pose over the one
filtered plane); the POSE AUDIT (binomial-impurity change-point straddle trimming a
window's bad edge); REFINEMENT, two kinds — (a) placement-time bounded 7x9x9 refinement
against the reference field (E022), (b) certified-feedback refinement RF1 (coarse+fine
grid against pilot + certified-cargo labels, adopt on held-out gain).

WHAT A POSE IS. `Pose` (frozen): `origin_yx: (float, float)` — native pixels of
window-local cell (0,0); `jacobian_yx: 2x2 float` — cells -> pixels, columns = (vertical,
horizontal) cell steps, det > 0; `phase_yx: (float, float)` (sub-cell phase the fit chose,
in [0.5, 1.5)); `pitch_px: float` = 0.5*(|col0|+|col1|); `angle_deg: float` =
degrees(atan2(J[0,1], J[1,1])). `matrix() = np.asarray(jacobian_yx, f64)`;
`points(cells) = cells @ matrix().T + origin_yx` (f64). Coordinates are y,x everywhere.

FRAMES (geometry.py conventions 1-4, keep verbatim):
- native capture pixels; cell (cy,cx) and pixel (y,x) both name the CORNER of a half-open
  unit interior. Durable page pose = row-major 2x3 terms (a,b,c,d,e,f):
  y = a*cy + b*cx + c, x = d*cy + e*cx + f. `invert_affine` via 2x2 inverse,
  offset = -inv @ t; refuses det == 0.
- capture-cell lattice: pose-free window-naming grid, origin = region support bbox
  corner, step = exact rational pitch (`pitch_in_vote * dpi_true`) — NEVER a measured
  pitch. Window extents `(cy0,cx0,cy1,cx1)` half-open in this lattice.
- footing (rung) frame: rung pixel j = area mean of native [j*s,(j+1)*s); affine pixel-side
  rescale law `out = s*(in + 1/2) - 1/2` applied to linear terms AND offset, computed
  in Fraction end-to-end, one float rounding per term, identity at s == 1
  (place_shared._rescale_pixels:253-280; compose_to_native/compose_from_native:281-308).
- window-local frame (RF1): re-origin the rung affine at the observed extent's MIN cell
  corner; local cell (i,j) = page cell (cy0+i, cx0+j) — pure translation.

Inputs: `PlaneRaster` (u8 mmap, `crop_luma -> f32`), `SupportMask` (block-grid bool,
bbox, step_px, rasterize_crop), declared exact pitch per footing, `PlacementConfig`
values (below), reference field (place plugin: `page(p) -> (values u8 HxW, sites bool HxW)`),
certificates (tiles plugin, with printed 64x64 field re-encode), calibration
(`llr(scores) -> f64`, calibrate plugin).

Outputs: `PreparedRegion` (pixels product), `WindowFit` (pose or refusal + lattice seed),
`WindowSample` (means/mask/bits/evidence/midpoint), audit mask + refusal, refinement
outcomes (new pose, deltas, held-out numbers), RF1 `Revision` (native 6-term affine or
refusal reason).

## 2. Algorithms, every constant

### 2.1 Constants table (all literals in holo3; no admission-table indirection)

Placement/fit (place_model.py:307-345, place_admission.py:60-79):
window_cells=200, overlap_cells=40 (step 160), layout_min_window_cells=8,
subdivision min_window_cells=70, subdivision_max_depth=1, pitch_tolerance=0.06,
shear_tolerance_deg=3.0, aperture_cells=0.7, phase_step_cells=0.125, spectral_px=2048,
min_spectral_periods=12, neighbor_radius_cells=3, consistency_cells=2,
support floor sites=30 (per parity class), gates search_true=0.20, validation_true=0.24,
rival_decoy=0.20, minimum_gap=0.08 (gates/rival belong to the place spec; listed for
completeness of AttemptBudget).
E022 refine: refine_angle_deg=0.15 step 0.05, refine_phase_cells=0.25 step 0.0625
(7x9x9 = 567 hypotheses), refine_min_total_sites=60, refine_min_sites_per_parity=20,
refine_heldout_degrade=0.005.
Audit: audit_min_sites=15, audit_bad=0.35, audit_good=0.20, audit_post_bar=0.25,
min_support=30 per parity.
Evidence: LLR clip +-8.0, scale *2.0, evidence = -tanh(llr/2) f32, spread floor 1e-6,
phase coverage >0.9 with >=16 selected, sample coverage >0.85.
RF1 (refine_fit.py:64-88 == certified_refine.py:45-64): BLOCK_CELLS=16,
VALIDATION_MODULUS=4, MIN_PAYLOAD_TRAIN=64, MIN_PAYLOAD_VALIDATION=32,
MIN_TRAIN_PER_CLASS=20, MIN_VALIDATION_PER_CLASS=10, MIN_CERTIFIED_BLOCKS=4,
MIN_POSE_PILOTS=30, MIN_HELDOUT_GAIN=1e-4, PILOT_MISMATCH_SLACK=0.005,
ANGLE_LIMIT_DEG=0.15, ANGLE_COARSE_STEP_DEG=0.15, ANGLE_FINE_STEP_DEG=0.05,
PHASE_LIMIT_CELLS=0.25, PHASE_COARSE_STEP_CELLS=0.25, PHASE_FINE_STEP_CELLS=0.0625,
POSE_SITE_CAP_TRAIN=2048, POSE_SITE_CAP_VALIDATION=1024, SCORE_SPREAD_FLOOR=1e-6.
Stripe hash: token = page*104729 + by*1009 + bx*9177; held out iff token % 4 == 0
(9177, NOT the historical 9176 — 9176 = 0 mod 4 degenerates to y-bands; ruling 10.5).
Pilot parity: ((131*y + 17*x) & 1) — validation where 1. Block ids:
is_pilot*10**12 + page*10**9 + by*10**4 + bx. Cap hash (uint64):
y*11400714819323198485 ^ x*14029467366897019727, stable argsort, first `cap`.
Grid epsilons: np.arange upper bound +1e-9 (E022 refine), +1e-12 (RF1 grids and clip
tests); candidate dedup key = round(v, 12). Zoom peak: span_bins=1.5, grid=13,
parabola denominator guard 1e-12, clip +-0.5. Spectral band = 0.22 relative.
Platen backing border_px=32. Prepared band = 32 MiB rows.

### 2.2 Prepared region (the pixels every fit and read address)

1. `platen_backing(raster)` = median f32 luma of the four 32-px border strips
   (pose_fit.py:294-304).
2. Per (capture, region, footing): clip the support bbox to the raster; refuse if empty
   or no supported cell. `filled = where(support, crop_luma, backing)` f32;
   `aperture = max(1, int(round(0.7 * pitch_px)))`; `filtered =
   ndimage.uniform_filter(filled, size=aperture, mode="nearest")` — EXACTLY ONE aperture
   op per region; every phase/read below addresses `filtered`; no rotated/decimated
   working raster is ever built. `support` kept as f32 so coverage reads through the
   same interpolator (pose_fit.py:307-340).
3. Build ONCE per (capture, region, footing), STREAMING into three f32 files; every
   worker maps them read-only (`np.memmap` mode="r"). Fill/support bands are pointwise;
   the aperture band carries a halo of aperture//2 rows each side, keeping only the
   interior (uniform_filter1d accumulates in double => band interior bit-identical to
   the whole-array filter; prepared.py:356-418). Rationale: per-fire rebuild of a
   4800-dpi region is ~8 GB/array — SIGKILLed workers on the 64 GB machine. holo3 names:
   `<rundir>/prepared/<capture>-<region>-<footing>.{filled,filtered,support}.f32`,
   temp-write + os.replace, run dir disposable.

### 2.3 Window layout + subdivision

1. `window_starts(n_cells)` in the CAPTURE-CELL frame: () if n < 8; (0,) if n <= 200;
   else range(0, n-200+1, 160) with the last start REPLACED/APPENDED so the final window
   ends flush at n-200 (flush-shift ruling — a clipped last window wastes tiles;
   geometry.py:241-297). Starts are cell indices; pixel origin = round(start * pitch)
   at the call site (individually quantised).
2. Subdivision (one level): children exist iff config.subdivide and depth < 1;
   side = max(70, min(h, w)//2); refuse if side >= min(h, w); four corners in order
   TL, TR, BL, BR: (0,0), (0,w-side), (h-side,0), (h-side,w-side); pixel origins via
   bare round(offset * pitch) (pose_fit.py:746-813). Children may overlap mid-window —
   correct, not a defect (70 is the smallest window E022 fits).

### 2.4 Window pose fit (fit_window_pose, pose_fit.py:567-669)

1. Crop `region.image[wy : wy+round(cells_y*prior), wx : wx+round(cells_x*prior)]`;
   refuse if min(shape) < 4*prior. Centre-crop to at most 2048 px per side (spectral cap).
2. If min(spectral.shape) >= 12*prior (full-size window): blind fit
   `lattice_reciprocal(spectral, prior)`:
   a. gradient = hypot(*np.gradient(f32 image)), mean-subtracted, times outer Hanning
      windows (f32) (pose_fit.py:387-393).
   b. rfft2 magnitude; keep radial band |f| in centre*(1 +- 0.22) around centre=1/prior;
      first peak = argmax; second peak = argmax restricted to angular distance
      > pi/2 - 20deg from the first; refuse if either bin is <= 0.
   c. zoom-refine each peak: local DTFT on a 13x13 grid spanning +-1.5 bins
      (ey/ex complex64, response = |ey @ g @ ex.T| with LEFT-TO-RIGHT association),
      argmax + 1-D parabolas per axis (guard 1e-12, clip +-0.5) (pose_fit.py:345-384).
   d. normalize: row with |f_y| >= |f_x| is "vertical"; flip signs so vertical[0] >= 0,
      horizontal[1] >= 0; stack rows (pose_fit.py:396-405).
3. Gate the Jacobian J = inv(freqs): pitch_y and pitch_x within +-6% of prior,
   |orthogonality error| <= 3 deg, det(J) > 0 (pose_metrics: pitch = hypot of columns,
   angle = atan2(h[0], h[1]) deg, orth = angle(v) - 90 - angle, wrapped to (-180,180]).
4. If the blind fit fails the gates: RETRY with `prior_f` = the region's lattice seed if
   one exists, else the declared axis-aligned [[1/prior,0],[0,1/prior]] — skip the coarse
   argmax, zoom-refit both rows locally, re-apply IDENTICAL gates (the c2 weak-x-decoy
   arm; pose_fit.py:408-466 with prior_f).
5. Edge window (min(spectral.shape) < 12*prior): its ONLY fit is the seed matrix
   through the same gates; no self-measurement.
6. Seed protocol (v1's region-shared mutable made explicit): a fit RETURNS the seed it
   used or freshly measured; the seed is established AFTER the geometric gates and
   BEFORE phase (a geometrically sound window helps edge windows even if its phase is
   inconclusive); a region that has a seed keeps it. `unconditioned_seed` is reported
   only when the fit did not consult the incoming seed; the merge thread keeps, per
   (footing, region), the unconditioned seed of the best-SUPPORTED window (R5,
   order-independent — never first-wins under threads).
7. Phase (_fit_phase, pose_fit.py:489-561): stride = max(1, round(max(cells)/40));
   grid = meshgrid(arange(0,cy,stride), arange(0,cx,stride), ij). midpoint = median of
   `filtered[wy:py1:4, wx:px1:4]` under support>0.5 (refuse if empty). Offsets =
   arange(0.5, 1.5-1e-9, 0.125) -> 8x8 hypotheses; for each, points =
   (grid + phase) @ J.T + [wy,wx]; means/coverage via map_coordinates order=1
   (cval = backing / 0.0); score = mean |means - midpoint| over coverage > 0.9 iff
   >= 16 selected else -inf; argmax + guarded parabolas (finite neighbours only) *
   phase_step. Refuse if best is -inf.
8. Pose: origin = region_offset + [wy,wx] + J @ phase_yx; build Pose; segment carries
   support_cells, phase_contrast, (pitch_y, pitch_x), orth error.

### 2.5 The cell read (sample_segment + median_radiometrics, pose_fit.py:674-716)

1. grid = all (cy,cx) of the window; points = grid @ pose.matrix().T + (origin - region
   offset); means = map_coordinates(filtered, order=1, cval=backing) f32;
   coverage same through support; mask = coverage > 0.85; refuse if none.
2. midpoint = median(means[mask]); spread = max(mean |means[mask] - midpoint|, 1e-6);
   llr = clip((midpoint - means)/spread, -8, 8) * 2.0; evidence = -tanh(llr/2) f32,
   zeroed off-mask; bits = (means < midpoint) u8. This is ADDRESSING evidence only —
   payload detection recalibrates (PAVA/ctx) in the detect plugin; the median is the
   contrast midpoint, never the payload split point.
3. Optional per-cell offsets door (ARM seam, see section 6/plane_fields): the points
   array accepts an additive per-cell (N,2) pixel delta per plane before interpolation;
   None => bit-identical to today.

### 2.6 E022 placement-time refinement (refine_patch_pose, pose_audit.py:668-780)

Runs on one ACCEPTED window (address known). Inputs: prepared region, window sample,
reference provider, page, page origin, rot_k.
1. Correspondence: `fragment_reference_sites(mask, provider, page, origin, rot_k)`
   (pose_audit.py:450-486): rot90 the mask by rot_k, overlap-slice against the page,
   select reference.sites & mask; return local (unrotated) points, expected bits, and
   absolute page points, with rotation inverted THROUGH AN INDEX ARRAY so correspondence
   order is preserved (index = -1 fill, np.rot90(index, -rot_k), order = values at
   nonzero).
2. Floors: total sites >= 60; site parity (131y+17x)&1 on ABSOLUTE coords; train = ~parity,
   heldout = parity; each >= 20.
3. expected_sign = 1 - 2*expected (FLOAT64 — deliberately not the scorer's f32);
   midpoint = median(sample.means[sample.mask]).
4. evaluate(da, dy, dx): J = R(da) @ J0 with R = [[cos, sin], [-sin, cos]] (y/x
   convention); base = origin - region offset + J0 @ [dy, dx]; means =
   map_coordinates(filtered, (points_f64 @ J.T + base).T, order=1, cval=backing);
   margin = mean((midpoint - means[train]) * -expected_sign[train]);
   heldout_mismatch = mean((means[heldout] < midpoint) != (expected[heldout] > 0)).
5. Baseline = evaluate(0,0,0) — its OWN call, never folded into the grid: the grid's
   nominal zero is -0.15 + 3*0.05 = 2.78e-17, a different hypothesis.
6. Grid: angles = arange(-0.15, 0.15+1e-9, 0.05); phases = arange(-0.25, 0.25+1e-9,
   0.0625); scan order (angle, dy, dx), winner = strictly-greater margin, first wins.
   BUILD THE BATCHED FORM ONLY (pose_audit.py:571-665): stack all 567 hypotheses'
   coordinates, ONE map_coordinates, margins/heldout as last-axis means over
   C-contiguous (H, N); winner = 0 if isnan(margins[0]) else nanargmax (first-occurrence
   tie rule == scalar strict->). Bit-identical by three measured clauses: J depends on
   angle alone and base on phase alone so the matmul factors exactly; order=1 is
   pointwise per coordinate; last-axis reductions are the same pairwise f64 sums.
7. Adopt iff heldout_after <= baseline_heldout + 0.005. Rebuild: J = R(da) @ J0;
   origin += J0 @ [dy, dx]; pitch/angle from the three pose_metrics expressions
   (orthogonality discarded); phase_yx unchanged; then RE-READ via sample_segment
   (2.5) and return the refreshed sample + deltas + heldout before/after.

### 2.7 Pose audit (audit_segment, pose_audit.py:785-887)

1. Correspondence over the accepted CORE mask; wrong = bits[local] != expected (f64);
   parity as in 2.6.
2. If sites < 2*15: keep all, refused iff either parity class < 30.
3. Four passes over axes (0, 1, 0, 1): stable-argsort active sites by that coordinate;
   `_best_change_point` scans split in [15, n-15), skipping ties in the sorted
   coordinate, minimising n_lo*p_lo*(1-p_lo) + n_hi*p_hi*(1-p_hi) via a cumulative-sum
   array, strict-< first-wins; cut = mean of the two straddling coordinates. Apply iff
   bad_rate > 0.35 and kept_rate < 0.20; edge = int(np.ceil(cut)); zero the bad side of
   `good` (rows for axis 0, cols for axis 1); keep &= good at sites. Stop early when
   active < 30.
4. residual = mean(wrong[keep]) (1.0 if empty); refused iff either parity class of keep
   < 30 or residual > 0.25. Return (good mask, refused, kept, residual).

### 2.8 Certified-feedback refinement RF1 (refine_fit.py whole file; v1 original
certified_refine.py:735-931)

Per eligible (window, pose), one bounded revision:
1. Labels (collect_labels, refine_fit.py:140-186): pilots = base field sites (format-known),
   cargo = enriched-field extra sites whose tile is CERTIFIED (values = certificate's
   re-encoded printed 64x64 field; a certificate disagreeing with the format at a known
   site is refused upstream). Pilot validation = (131y+17x)&1; cargo validation = the
   diagonal stripe (2.1). Weights: one unit per block, computed separately over train
   and validation populations (block_weights = 1/count via np.unique inverse).
2. Support floors in ORDER: payload_train >= 64, payload_validation >= 32, train classes
   >= 20 each, validation classes >= 10 each, certified blocks >= 4; then pose-site
   selection (all pilots + hash-capped cargo to 2048/1024, reorder by row stable) and
   pilot floors: train pilots >= 30 AND validation pilots >= 30. Each failure returns its
   reason string as the outcome.
3. Window-local geometry (local_segment, refine_fit.py:402-432): restate the durable
   native affine in the footing's pixels (compose_from_native), re-origin at the observed
   extent's min-cell corner. THE PIVOT IS LOAD-BEARING: pose_candidate rotates about the
   pose's OWN origin; a page-frame pivot turns 0.15 deg into many cells of translation.
4. Baseline: sample the pose's observed cells (sample_at = map_coordinates order=1 over
   the SAME prepared filtered plane, cval=backing, f64 out); logits = calibration.llr on
   the convention the knots were fitted under (see open question 1); base_loss =
   weighted_logloss over validation; base_pilot_mismatch = mean((logits>0) != (value>0))
   on validation pilots; midpoint = median(baseline means); base_raw_mismatch =
   mean((means < midpoint) != (value>0)) on validation pilots.
5. Search: coarse grid = arange(+-0.15 step 0.15) x arange(+-0.25 step 0.25)^2 (27);
   fine grid around the coarse winner at steps 0.05 / 0.0625, every value re-clipped against
   the LIMIT +1e-12 (out-of-bound impossible by construction); candidate key rounded to
   12 decimals for dedup. Per candidate on the TRAIN sites: contrast =
   pose_objective = (weighted mean paper luma - weighted mean ink luma) / max(weighted
   MAD about the weighted centre, 1e-6), -inf if a class is empty (raw luma only —
   ranking is calibration-convention-free); loss = weighted_logloss(llr, train).
   weighted_logloss = sum(w * (logaddexp(0, x) - y*x)) / sum(w).
6. select_best: max contrast, candidates within 1e-9 of it tie-broken by
   min (loss, sum of squares of the key, tuple of abs values, key).
7. If the winner reproduces the current pose exactly: refuse "active_pose_selected".
   Else resample ALL observed cells at the winner, recompute validation loss and the two
   pilot mismatches; adoption_gate = (cand_loss + 1e-4 < base_loss) AND
   (cand_pilot_mismatch <= base_pilot_mismatch + 0.005) AND (cand_raw_mismatch <=
   base_raw_mismatch + 0.005) — the third is detector-free on purpose (stops buying
   log-loss by moving where luma no longer separates pilots).
8. On adoption: convert back to the durable native page-cell 6-term affine
   (native_terms: un-origin from the corner, compose_to_native) and commit a NEW pose
   for the window (the old one is simply superseded — "latest pose wins" at read time);
   do not commit if the affine equals the standing pose. Then RE-READ the window's cells
   through the new pose (2.5) and let ordinary payload attempts re-run over the fresh
   evidence — the revision is a proposal; the payload rerun proves or discards it.
   No route re-scoring, no word decode, no consult on the re-read.

### 2.9 Refine scheduling function (holo3 frontier terms)

Refine is the LAST cost tier: it runs only when every cheaper stage (survey, place,
words, payload attempts) has drained. Eligibility per pose, derived fresh each pass:
(a) >= 1 tile in its observed reach is CERTIFIED (label channel exists), (b) >= 1 is
uncertified (something to buy), (c) the window does not already carry a revision (never
refine a revision; measured max 2 poses/extent, chains unmeasured). Tried-set floor:
one attempt per (pose, certificate-set-at-attempt); re-attempt only if new certificates
landed in that pose's reach since. Loop: run a refine pass over all eligible poses ->
re-read adopted windows -> re-run payload over the residue -> repeat while a pass
adopted >= 1 revision AND the rerun minted >= 1 new certificate. THE KNEE (e024,
measured): after a full scale-space cascade, broad affine feedback has sharply
diminishing returns (refine beat control by ~+2..5 tiles of 757-772); expect one or
two productive passes, never iterate to convergence.

## 3. Copy-vs-rewrite table

COPY-AND-STRIP (hard-won numerics; keep every dtype, rounding idiom, epsilon, order):
| what | from |
|---|---|
| zoom DTFT peak + parabola | holo2/src/holo2/solve/pose_fit.py:345-384 |
| windowed gradient, reciprocal normalize | pose_fit.py:387-405 |
| lattice_reciprocal incl. prior_f arm | pose_fit.py:408-466 |
| jacobian_from_reciprocal, pose_metrics | pose_fit.py:469-486 |
| _fit_phase (stride law, 8x8, parabolas) | pose_fit.py:489-561 |
| fit_window_pose flow + gates + seed protocol | pose_fit.py:567-669 |
| median_radiometrics (bounded evidence) | pose_fit.py:674-686 |
| sample_segment | pose_fit.py:689-716 |
| subdivision extents/children | pose_fit.py:746-813 |
| platen_backing, prepare_region values | pose_fit.py:294-340 |
| streaming banded build + halo rule | prepared.py:356-423 |
| affine terms/invert/apply/shift | geometry.py:105-143, 218-223 |
| window_starts flush-shift | geometry.py:241-297 |
| pixel-frame rescale (Fraction law) | place_shared.py:253-308 |
| site parity, fragment_reference_sites | pose_audit.py:247-253, 450-486 |
| _rotation_2x2, batched refine scan | pose_audit.py:491-497, 571-665 |
| refine_patch_pose (baseline+gate+rebuild) | pose_audit.py:668-780 |
| _best_change_point, audit_segment | pose_audit.py:785-887 |
| RF1 constants block | refine_fit.py:64-88 (== certified_refine.py:45-64) |
| block_validation/weights, collect_labels | refine_fit.py:116-186 |
| support_metrics, deterministic_cap, select_pose_sites | refine_fit.py:189-238 |
| pose_candidate, pose_objective, weighted_logloss | refine_fit.py:244-302 |
| adoption_gate, candidate_grid, fine_grid, select_best | refine_fit.py:305-382 |
| local_segment, sample_at, propose, native_terms | refine_fit.py:387-574 |

REWRITE LEAN (semantics kept, machinery dropped): prepared naming/doors (simple
deterministic filenames, no digest, no open-without-raster), region/window plumbing,
seed reduction at the merge thread (R5 best-supported), refine eligibility + pass loop
(plain functions over holo3 state, replacing refine.py's Reach/provider/worker/read_keys
entirely), certificate-labels join (frontier = a plain dict (page,ty,tx)->printed field
snapshot; no frontier_id/canonicality dance), the re-read after adoption (resample.py's
EFFECT: sample superseded cells at the live pose, re-emit evidence + fresh window
calibration — none of its journal/marker text).

## 4. Measured-channel invariants that MUST survive

- prior_f retry arm in the lattice fit: c2's x fundamental is 8-10x weaker than y; the
  blind argmax locks speckle decoys and the (correct) gate then blocks every placement
  route (2026-07-30 root cause).
- Never measure known pitch: pitch prior is format+dpi truth (exact rational); estimators
  fit channel wander as scale (measured 5.92 vs true 6.00); gates are +-6% AROUND the
  declared prior.
- Whole-cell-blind objectives: fit/phase objectives read contrast (|means - midpoint|),
  never expected content — content-aware fitting lost whole-cell consistency (Track-3 P1).
- Median != split point: the median is the contrast midpoint and evidence normalizer;
  the class-mean midpoint as a DETECTOR read 9.8% where a fitted threshold read 0.04% —
  payload decisions go through calibration, never this midpoint.
- Spread is inverted — score class SEPARATION: raw spread of sampled means anti-correlates
  with fit quality; hence phase score = mean|means-midpoint| and pose_objective =
  (paper-ink)/spread, both maximised.
- Bounded evidence: clip +-8, *2, -tanh(llr/2) — the 018.7 LLR honesty bug; unbounded
  LLRs poison LDPC.
- One 0.7-cell box aperture, order-1 reads on THE one filtered plane, no second
  resampling ever (a rotated/decimated intermediate erases the c2 margin).
- Coverage 0.9/16-site phase floor and 0.85 sample mask; 30-sites-per-parity support
  floor everywhere a mismatch is trusted.
- Refinement bounds +-0.15 deg / +-0.25 cell with held-out gain 1e-4 and TWO pilot
  non-regressions incl. the detector-free raw clause — e024's guard against feedback
  circularity buying log-loss with geometry.
- Baseline (0,0,0) evaluated outside the grid (grid zero = 2.78e-17 is a different pose).
- Window-local pivot for pose_candidate (page-frame pivot violates the bound in geometry
  while respecting it in the term).
- Diagonal-stripe holdout, all-odd coefficients (9177): x-degenerate holdout
  over-represents y-correlated pose error.
- Flush-shifted last window (a clipped last window addresses tiles with a third less
  evidence or drops rows entirely — wasted tiles ruling).
- Refine only at the margins (e024): eligibility gated to poses touching uncertified
  residue; post-cascade broad feedback is near-worthless.
- Seed before phase; seeded region never re-seeds; full-size windows always self-measure.

## 5. DROP (aggressively)

- All pull-model machinery: providers, WorkDescriptor/ResourceKey/read_keys, wakes,
  spend identities, COST_REFINE ladder + lane premiums, Reach dataclass, quarantine
  threading, ProgressSink quanta, outcome-string ledger (plain reason strings on the
  Revision suffice).
- All resume/journal/replay: prepared digests, open_prepared_region, .partial recovery
  beyond temp+rename, journal-verified re-earn, PoseRecord keying, live_pose staleness
  derivations, and certified_refine's whole RefinementIntegrityError battery
  (`_request_rows`, retained-raw-luma byte replay, reference re-derivation) — holo3
  recomputes fresh, nothing to replay.
- v1 CertificateFrontier ceremony: frontier_id sha, canonicality checks,
  dependency_certificate_ids threading, MappingProxy, _readonly freezing, every
  __post_init__ shape/type police in the refine dataclasses.
- The scalar refine scan + batched_refine dial (build batched only), measure/
  equivalence harnesses, OR-9 admission-datum table (_carried_int), structural
  Protocols, SegmentSampler TypeAlias, ScoreMemo counters, the two-way no-op-guard
  vocabulary (just never commit an unchanged affine), pose-spam metrics,
  replay_calibration's n_search reconstruction (holo3's calibration carries what
  llr needs).
- v1's ContextDecision arm inside refine: ctx applies at decode assembly; refine always
  uses marginal logits (holo2 ruling, carried). SUPERSEDED 2026-09-04 by
  retirement_docs-2026-09/RULINGS.md D3: the arm IS ported, behind
  `--refine-gate {context,marginal}` with context the default. The two losses the
  adoption gate compares (v1's `_fixed_detector_logits` call sites, base and winning
  candidate) ride the region's adopted nine-bin offsets re-binned over that pose's own
  cells; the candidate search still ranks on the marginal fit, as v1's does; a window
  whose own evidence carries no adopted context is the marginal path by construction;
  and `--refine-gate marginal` reproduces this bullet's behaviour exactly. A/B on the
  degraded and local-patch K sims: identical certificates, fires and adoptions.
- AddressPatch wrapper properties, refresh_address_patch identity check, refinement
  provenance fields beyond the four numbers used.

## 6. Data-structure needs (src/holo/receiver/data.py)

Consumed: `Capture` (id, sha, shape_px, dpi_true), `PlaneRaster` (u8 mmap + crop_luma
-> f32), `SupportMask` (cells bool, step_px, bbox, rasterize_crop), `Window`
(window_id int, region_index int, origin_yx_px (int,int), shape_yx_cells (int,int),
depth int, support_estimate int), footing frame (Fraction scale + native shape),
reference page (values u8, sites bool), calibration handle, certificates
(page, ty, tx, stream, printed 64x64 u8, source tag — refine treats all sources alike).

Produced:
- `PreparedRegion`: region_index, y0, x0, image f32 (mmap), filtered f32 (mmap),
  support f32 (mmap), backing float, pitch_prior float, aperture_px int. Per plane for
  colour (plane-native; one prepared triple per (capture, region, footing, plane)).
- `LatticeSeed`: four float64, row-major (2,2) reciprocal; round-trips losslessly.
- `Pose` (above), `PoseSegment`: window, pose, support_cells int, phase_contrast float,
  pitch_yx_px (float,float), orthogonality_error_deg float.
- `WindowFit`: segment | None, lattice_seed | None, unconditioned_seed | None.
- `WindowSample`: segment, means f32 (cy,cx), mask bool, bits u8, evidence f32,
  midpoint float.
- Audit result: good mask bool (cy,cx), refused bool, kept int, residual float.
- `RefineOutcome` (E022): sample, delta_angle_deg, delta_phase_yx, heldout_before/after.
- `Revision` (RF1): adopted bool, reason str, native affine 6-tuple | None, deltas,
  baseline/candidate logloss, candidate count.

Threading: PreparedRegion arrays are read-only mmaps — free to share. A window fit /
sample / audit / refine job is pure over (prepared view, window, pose snapshot,
reference snapshot, certificate snapshot, config). STATEFUL/SHARED things the contract
must make a snapshot or a reduction: (1) the region lattice seed — jobs take a seed
snapshot and return measured seeds; merge thread reduces per (footing, region) by
best-supported window; (2) the pose table — single-writer; a window's live pose = the
latest committed for that extent; (3) the certificate frontier consumed by a refine
pass — an immutable snapshot taken at pass start (facts merged serially anyway).

ARM API needs (dial-off; the colour closes predate them — NOT core):
- plane_fields / color_field: the cell read (2.5) and RF1's sample_at must accept an
  optional per-plane per-cell additive pixel offset array ((N,2) f64, already rotated
  into the local frame, clamped upstream). The arm computes offsets from a tile-space
  field lookup (local affine = translation delta dots + 2x2 jacobian dots-per-cell about
  the row centre, clamp max_delta_dots, rot_k-inverse rotate; color_field.py:602-661).
  None per plane => byte-identical path (null-proven on main).
- colour refine (src/holo color_refine): same two-stage grid + gate on per-plane summed
  logloss; synthetic-only qualification — slot in later behind the same plugin API,
  do not build for acceptance.

## 7. Pitfalls / incidents

- H4 W1a SIGKILL: preparing per fire rebuilt three ~8 GB arrays; exit 137 at workers
  4/8 on 64 GB. Prepare once, memmap read-only, banded build with the aperture halo.
- 2026-07-30 c2 placement root cause: the ported fit DROPPED the prior_f arm; every
  route refused. The retry arm is byte-identical whenever the blind fit succeeds.
- 9176 -> 9177: an unremarked historical coefficient was = 0 mod the modulus; archaeology
  found no rationale; fixed for health with an identity bump. Independent splits need
  independent BITS — two different odd-coefficient linear forms of (y,x) are the SAME
  &1 hash (track-2 incident: certification silently empty).
- The batched phase grid: built, bit-identical, 1.07x, DELETED. Do not reopen without
  changing the stride law; the refine grid is the one that batches (567 re-sampling
  hypotheses vs 128 x 1,600-point reads).
- np.arange epsilon discipline: +1e-9 (E022) vs +1e-12 (RF1) upper bounds and the
  +1e-12 limit clips are load-bearing — candidate sets change size otherwise; the RF1
  dedup requires round(key, 12) because the fine grid re-derives coarse offsets.
- Rounding idioms are not interchangeable: int(round()) (half-to-even) for pixel
  extents, bare round() in subdivision corners, int(np.ceil(cut)) at the audit edge,
  argsort(kind="stable") wherever order feeds a first-wins scan.
- Score-convention trap: refine logits must go through the convention the calibration
  knots were FITTED under (v1: (midpoint-raw)/spread; holo2: llr(-means)). Mixing them
  is a bug no synthetic test catches quickly.
- v0.42 regression (still open in v1): moving refinement behind --refine cost flagless
  gates its certificates. holo3: refinement is core and always on; no flag.
- Batching lesson: _fit_phase batching was built, proved bit-identical, measured 1.07x,
  DELETED (stride law pins ~1,600 points/call); the REFINE grid is the one that batches
  (1.9x). Do not reopen without changing the stride law.
- Plane-fields W6: per-PAGE adoption misfit made one band worse; per-block adoption is
  owed — reason the arm stays dial-off.
- Do not double-read one physical capture (raw + its decimation) into one state; a pose
  is per (capture, footing) and one ordinary state freezes one DPI (enforced upstream,
  but poses are where a breach would be silent).

## 8. Open questions for the contract author

1. Score convention for RF1: does holo3's calibrate plugin fit PAVA on -means (holo2
   convention; then refine's baseline logits == the stored evidence LLRs, a checkable
   invariant) or on (midpoint-raw)/spread (v1)? The refine spec follows whichever the
   calibrate spec picks; it must be one convention everywhere.
2. Confirm holo3 ships BOTH refinements: E022 placement-time refine (config.refine
   True in the qualified chain) and RF1 over the residue. Any acceptance target known
   to require RF1 specifically (e029 full-harvest used it; the colour closes did not)?
3. Lattice-seed reduction: R5 best-supported-window (order-independent, recommended
   for --workers N == 1 parity) vs v1 first-fit-wins. Byte-parity with holo1 closes is
   at the payload level, but pin the choice.
4. window_starts frame: holo2's cell-frame starts (individually quantised) diverge from
   v1's pixel-frame lattice at non-integral pitch BY DESIGN. Acceptance replays holo1
   closes — confirm the cell frame is holo3 law and payload-level parity is the bar,
   not window-level.
5. Re-read after adoption: engine contract without wakes — does the pass loop (2.9)
   re-run payload over ALL tiles touched by re-read windows, or is a dirty-tile set
   threaded through the frontier? (Simplest correct: dirty set.)
6. Prepared-plane disk budget: 12 B per region pixel per footing per plane (~24 GB at
   4800 dpi grey). Which footings/planes get prepared triples is the scale-space spec's
   call — confirm intake builds lazily per (footing, plane) on first window.
7. The per-cell offset door signature in data.py (per-plane (N,2) f64 pixel deltas at
   the sampling seam) — bless it now so the plane-fields arm needs no core edit later.
8. Colour: poses are plane-COMMON (fit on the survey/geometry plane) with per-plane
   deltas as an arm — confirm no per-plane pose fitting in core (PK6/A2 measured
   negative; the Y sinusoid line is the arm's business).
