# 10 — Colour cell readout (cmy7/cmy8 heads, features, calibration, LLR production)

Authority: src/holo ONLY (holo2 has no colour channel). Cross-referenced against
docs/COLOR-UPLIFT-PLAN.md + docs/COLOR-UPLIFT-MEASUREMENTS.md (PK-FINAL §14).
All paths relative to <checkout>.

## 1. Purpose, inputs, outputs

Purpose: turn one aligned RGB capture lane + BCH-promoted window placements +
the accumulated certificate set into (a) per-cell colour evidence rows
(cmy7: six W-relative state logits; cmy8: three calibrated C/M/Y LLRs), and
(b) per-tile per-stream LDPC attempts that mint stream certificates.

Inputs (per region job):
- RGB raster: `crop_native(r0,r1,c0,c1) -> (H,W,3) u8` (or u16), one aligned
  channel-preserving lane per (capture, DPI). Colour lanes are built with
  `area_decimate_rgb` (scale_space.py:714-773) — the SAME spatial transform
  as the K luma lane, applied per channel, NO luma projection. Native u8
  values; divisor probe (step C4) normalizes.
- Placements: tuple of PlacedPatch (E022 windows) with committed pose
  (`pose.points(local_yx)->scan_yx`, `pose.pitch_px`, `pose.matrix()`),
  grouped by (region_index, page); plus label placements (D7) and
  certified-complete windows as label-only rows.
- FormatSpec: codec_family (CMY7|CMY8), seed, family_seed, layout
  (tiles_yx, cells_yx), cell_dots, stream_profiles/stream_ids, payload_cells,
  tile_counter/tile_address.
- Certificates: all prior-barrier TileCertificateRecords (source-tagged in
  holo3), indexed by (page, ty, tx).

Outputs:
- Per window: `(N,2) int32 page_cells_yx` + `(N,A) float32 evidence_values`,
  A = 6 (cmy7) or 3 (cmy8); all finite. Plus per-region facts (fit losses,
  head/ctx verdicts, residuals) as diag events.
- Per (page): one-owner frozen evidence -> per-tile evidence blocks:
  observed 4096-bit bitmap + float32 LLR rows, kind in {"cmy7","cmy8"},
  arity {6,3} (evidence_blocks.py:38 `_ARITIES`).
- Per attempt: TileAttemptRecord + optional stream certificate
  (certified user bits; cmy7 stream "main", cmy8 streams "C"/"M"/"Y").

Sign/level conventions (frozen): LLR = log P(ink) − log P(no ink), positive
is ink. cmy7 evidence = six state log scores for states 1..6 (C,M,CM,Y,CY,MY)
relative to W=0 (implicit zero column). State id = C + 2M + 4Y. Plane order
C,M,Y everywhere.

## 2. Algorithm

### A. Region assembly + pool law (color_payload.py:97-551)
1. Index certificates by address; compute `fully_certified_addresses` =
   tiles with EVERY stream certified (color_pool.py:42-61).
2. Group payload placements by (region_index, page); sort patches by
   patch_id ascending. Label placements grouped alongside.
3. Per window compute emission mask: cell kept iff its tile has >=1 open
   stream (color_pool.py:64-80); payload-cargo mask from
   `pilots.color_payload_cell_indices(family_seed)` (4096-slot mask).
4. Region wholly terminal (no open payload cell in any window) -> skip all
   image work (pool-law L1).
5. Certified-complete windows and D7 label placements become LABEL ROWS:
   furniture sites only (word+dust), join the region fit + pitch pool, never
   emit/own (color_anchoring.py:175-224). Pitch = median `pose.pitch_px`
   over placements UNION label placements.
6. Known field per payload window (known_field.py:162-252): format furniture
   (word/dust states from pilots) overlaid with certified-component
   projections (color_projection.py:131-207 re-encodes each certificate's
   frame and scatters its plane's bits through the address-keyed cell
   permutation). CMY8 certificate labels ONLY its own plane; cmy7 owns all
   three. A cell with all three components known resolves a state; else
   state -1. Projections memoized per (address, certificate-id set).

### B. Reference states (color_anchoring.py:83-145)
7. Per family seed, build the (64,64) site lookup: word sites 0..99, dust
   sites 100..119, payload -1 (`pilots.color_site_cells_yx`). Per tile
   counter: `pilots.color_word_states(seed,[counter])` and
   `pilots.dust_state_values(seed,[counter],codec)` give exact printed
   states. Kind codes: 0 word, 1 dust, -1 payload.

### C. Sampling / base features (color_sampling.py, _payload_sampling.py:36)
8. APERTURE_CELLS = 0.7. `aperture = max(1, round(0.7*pitch_px))` box
   (uniform) filter per RGB channel, mode="nearest", float32.
9. Window crop halo = `ceil(1.5*pitch_px)+3`; points-crop halo =
   `ceil(0.7*pitch_px)+2`. One native read per window feeds BOTH the
   divisor probe and base features.
10. Divisor: 255.0 if max raw value over all region crops > 1.5 else 1.0;
    filtered /= divisor. (u8 input -> reflectance in [0,1], white high.)
11. Feature = bilinear sample (`map_coordinates`, order=1, mode="nearest")
    of the filtered image at each cell's scan point, per channel ->
    `(N,3)` float64 R,G,B means. These are the QDA features (base arm A0).

### D. Registration (A1) (color_anchoring.py:227-608, color_registration.py)
12. Blind per-plane detector over ALL region features
    (color_detect.py:90-142): normalize `(hi-mean)/max(hi-lo,1e-6)` with
    (lo,hi) = 2%/98% quantiles (ink now high); 2-component 1-D EM, init
    mu=(0.1,0.9), sigma=(0.15,0.15), 40 iters, sigma floor 1e-3, converge
    |dmu|<1e-4; order mu ascending; LLR = logN(hi) − logN(lo). Confident =
    |LLR| >= BLIND_CONFIDENT_LLR = 2.0. Known cells overwrite detected bits
    and are always confident.
13. Anchor candidates per plane: known-INK cells on the search side of the
    site split `((131*y + 17*x) & 1) == 0`, bucketed word/dust/certified
    (0/1/2); per bucket, canonical (page,y,x) order, budget
    _ANCHOR_BUDGET_PER_KIND = 512 selected by equal-width bin left edges.
14. Per anchor: 3x3 neighbourhood template from detected bits (centre
    forced ink=1, weight 1.0; neighbour weight 1.0 if confident else 0.05;
    skip if any neighbour missing or template constant). Rectify at
    _RECTIFIED_PX_PER_DOT = 2 px/print-dot: sample a
    `(3*cell_px + 2*max_shift)^2` window along the pose,
    `cell_px = 2*spec.cell_dots`, `max_shift = max(2, round(5*cell_px/6))`
    (_ANCHOR_MAX_SHIFT_PX = 5). Template = kron(1 − bits, ones(cell_px)).
    Weighted sliding NCC (color_anchoring.py:227-277) + parabolic subpixel
    peak (clip ±0.5). Reject quality < _ANCHOR_MIN_Q = 0.10. Offset
    returned in print dots (dx,dy)/2.
15. Fit per-plane residual `delta(y) = (dx0+dx1*y, dy0+dy1*y)` in
    page-y-fraction (color_registration.py:94-175): <8 valid anchors ->
    zero model; <16 anchors or y-span <0.15 -> median constant only; else
    Theil–Sen slope over pairs with |dy_frac|>0.05, median intercept,
    inliers = |resid| <= 0.5 dot, >=8 inliers -> LSQ refit on inliers.
    Constants: COLOR_ANCHOR_MIN 8, COLOR_SLOPE_MIN 16,
    COLOR_SLOPE_MIN_SPAN 0.15, COLOR_ANCHOR_INLIER 0.5.
16. Corrected features (arm A1): per plane, scan points shifted by
    `(residual.offsets(y_frac)[:, ::-1] / cell_dots) @ pose.matrix().T`;
    resample as in C. A proposal leaving the raster -> A1 ineligible for
    that window set (`corrected = None`).

### E. Ownership + split (color_fitting.py:259-315)
17. Deduplicate known cells (state >= 0) across windows by ascending
    patch_id, first window wins, key (page,y,x); canonical sorted key
    order. Carries (window_ordinal, row_index, state, kind) per owner.
18. Fit split: search side = `((131*y + 17*x) & 1) == 0` on page coords.
    Sparse-state repair: for any state with >=2 rows all on one side, move
    its canonical first row to the empty side. (&2 of the same hash =
    head sub-split; &4/&8 = A4b reveal field; &12 mask.)

### F. Region detector fit (color_fitting.py:318-410, color_detect.py)
19. Both split sides must cover every state (7 or 8) else region refuses.
20. QDA (fit on SEARCH side; color_detect.py:214-325), equal-prior,
    full-covariance with shrinkage: pooled = within-class scatter /
    max(n−K,1) + ridge, ridge = 1e-6 * max(trace(pooled)/D, 1e-12) * I
    (QDA_RIDGE = 1e-6); per class a = min(1,(D+2)/n_k),
    S_k = (1−a)*S_ML + a*pooled + ridge (pooled ALREADY contains one
    ridge — preserve the double-ridge detail). Cholesky per class;
    log-density score = −0.5||L^-1(x−mu)||² − 0.5 logdet. Empty class ->
    pooled stand-in + `degenerate` flag. Collapse guard: pooled-whitened
    mean distance < 0.5 + sqrt(D*(1/n_l+1/n_r)) (QDA_COLLAPSE_DIST=0.5)
    -> the differing planes are `clipped_planes`.
21. cmy7: relative scores = `scores[:,1:] − scores[:,:1]` (6 cols). A
    degenerate/collapsed cmy7 region REFUSES (raises -> region rejected).
22. cmy8: marginal LLR per plane = logsumexp(scores[ink states]) −
    logsumexp(scores[non-ink]) (color_detect.py:400-472); clip to
    ±DEGENERATE_LLR_CLIP = 2.0 on degenerate/clipped planes. Dust PAVA
    calibration fitted IN-SAMPLE on the dust+certified population
    (kinds==1 | kinds==-1; BCH word EXCLUDED), scored by the full fitted
    QDA (never a foreign QDA — E017.5 scale-mismatch law):
    - support qualification per plane (color_detect.py:777-842): each
      binary class >=6 labels (CMY8_CALIBRATION_MIN_CLASS_LABELS) AND >=2
      distinct QDA states with >=3 labels each
      (MIN_STATES_PER_CLASS=2, MIN_LABELS_PER_STATE=3); unsupported plane
      -> neutral map, emitted LLR exactly 0.0 (graceful degradation —
      component-local erasure, never an arbitrary raw marginal).
    - PAVA map (color_detect.py:575-667): stable-sort scores; equal scores
      pooled BEFORE isotonic (tie-pool); class-balanced weights
      (pos*N/(2*n1), neg*N/(2*n0)); stack-based pool-adjacent-violators on
      group means; node score = weighted mean score of block; clamp
      probabilities to [pmin, 1−pmin], pmin = 1/(N+2); E017.6 anchor:
      if nodes straddle score 0 with probs straddling 0.5, insert node
      (0.0, 0.5). Apply: linear interp of probability then logit.
23. Held-out loss (region gate currency): mean multinomial NLL of
    softmax(QDA scores) on the held-out side; plus word-only and dust-only
    legs (inf when empty). cmy7 additionally carries the held-out
    population (relative scores, states, site keys) for the head.

### G. The arm ladder (color_stack.py:549-911) — run per region, in order
24. A0 vs A1: fit detector on base and (if eligible) corrected features;
    adopt A1 iff the THREE-WAY gate passes: total held-out NLL strictly
    better by 1e-9 AND word leg not worse (+1e-9 slack) AND dust leg not
    worse (STACK_GATE_SLACK = 1e-9). Loser's feature tuple is dropped.
25. A4 — cmy7 calibrated head (CORE; color_calibration.py). Fit on the
    QDA's held-out side, sub-split by `(131y+17x)&2 == 0` -> cal_search /
    cal_validation. Model: s' = a*s + b, one scale a in [0.01,10]
    (HEAD_SCALE_MIN/MAX), six offsets, W logit pinned 0. Class-balanced
    multinomial NLL (weights 1/count per represented state, normalized to
    mean 1 — color_calibration.py:138-163); damped projected Newton with
    exact gradient/Hessian (lines 188-284): max 50 iters, grad tol 1e-10,
    Levenberg damping 1e-12*max(1,trace) escalating x1000 to 1e-8 on
    singular solve, 40-step halving line search, box-projected KKT norm.
    Floors: every state >=10 in cal_search (HEAD_MIN_SEARCH_PER_STATE),
    validation >=40 total and >=3 per state. Adoption gate 1: strict
    class-balanced validation-NLL improvement > 1e-9 over identity.
    Adoption gate 2 (satfloor30, PK3.1): pre-head deployment saturation —
    fraction of EMITTED payload cells whose L-inf divisor
    max(1, max|s|/20) exceeds 1 — must be >= HEAD_SATURATION_FLOOR = 0.30
    (color_stack.py:249, 390-416). Either refusal -> no head, literal
    pre-head path.
26. A5 — multi-state context matrix (CORE; color_context.py +
    color_neighbourhood.py + detect.py primitives). Skip when label floors
    fail (search < 80 or validation < 40 owners).
    a. Provisional ink map: per window, emitted evidence (post-head for
       cmy7) -> per-plane ink bool (cmy8: LLR>0; cmy7: equal-prior plane
       marginal of [0|s] > 0). Known bits OVERWRITE provisional ink.
    b. Region-wide dedup (ascending patch_id, first wins), dense-grid 3x3
       convolution for 8-neighbour ink counts + completeness
       (detect.py:280-316); bins 0..8, incomplete = -1
       (N_CONTEXT_BINS = 9).
    c. Fit per (state, plane) monotone curve on the label split: cmy7
       columns are states 1..6 (W pinned), cmy8 all 8. Direction read off
       the state's plane bit: prints plane k -> non-increasing; else
       non-decreasing (fit by walking bins in reverse). One-vs-rest logit
       `score_s − logsumexp(others)`; K's generalized PAVA over ordered
       blocks with the canonical two-branch sigmoid block solve
       (detect.py:402-449): bisection on [−4,+4] (CTX_OFFSET_LIMIT=4.0)
       to CTX_ROOT_TOL=1e-12, per-bin prior pseudo-labels {False,True}
       weight CTX_BIN_PRIOR=1.0. Zero-anchor: subtract the curve's
       class-balance-weighted mean over its own fit bins
       (color_neighbourhood.py:238-252).
       Per-curve floors (K's, per curve): search rows >=80, >=20 per class
       (CTX_MIN_SEARCH, CTX_MIN_SEARCH_PER_CLASS), validation >=40, >=10
       per class. Label cap 40,000 by deterministic linspace stride
       (CONTEXT_MAX_LABELS). Per-curve gate: strict (1e-9) class-balanced
       one-vs-rest held-out improvement.
    d. CONTEXT_SWEEPS = 3 coordinate-ascent sweeps, state-major
       plane-minor, running corrections applied to both populations;
       adopted curves accumulate; stop early when a sweep adopts nothing.
    e. Drop curves on unsupported cmy8 planes. No adopted curve -> no
       head. Region gate: three-way comparison in the EMITTED space
       (cmy8: per-plane binary NLL of marginal+clip+PAVA over printed
       bits; cmy7: joint multinomial of [0|s]), class-balanced;
       unmeasured leg (-1.0 sentinel) cannot refuse.
    f. Apply (color_context.py:253-271): scores += sum_k f_{s,k}(bin_k),
       bin -1 -> zero via a padded tenth column. cmy7: AFTER the head,
       BEFORE the bound. cmy8: on the 8 state scores BEFORE
       marginalization; then emit via marginal -> clip -> PAVA
       (`emitted_llrs`, color_context.py:728-750).
27. ARMS (dial-off; the four target closes need none of them adopted in
    the standard ladder — see §Load-bearing):
    - A3 window photometry (color_locality.py): per-window per-channel
      gain+offset toward region QDA class means; shrinkage prior 20
      effective labels; floors 40/3-states/20; per-window pre-gate +
      region three-way on a REFITTED QDA. API need: takes (model,
      selection, row_tuple, features, config) -> mapped feature tuple.
    - A4b KnownField-conditioned marginals (color_conditioning.py):
      sibling-restricted marginals (4v4/2v2/1v1) + (plane, pattern)-
      stratified PAVA; reveal field `(131y+17x)&12`. Measured net-negative
      to null on the corpus; u-lane-only in holo1.
    - plane_fields / color_field: seam = per-plane per-window
      `offsets_override (N,2)` replacing the PlaneResidual prediction in
      step 16 (color_anchoring.py:556-608 signature), fed by the
      RegistrationAnchors return of step 14-15 and certified-tile NCC
      probes. Colour closes predate it; dial-off.
28. Force-null: holo3 drops the env hatch entirely; the "off"
    configuration is simply arms-absent (A0/A1 only, demap_iterations 1
    never needed — ship 3).

### H. Emission + ownership + blocks
29. Per payload window, emit only cells under the emission mask; evidence
    from the selected fit:
    - cmy7: scores -> head.apply (if adopted) -> ctx.apply_states (if
      adopted) -> uniform L-inf bound: divisor = max(1, max|s|/20)
      per cell (CMY7_RELATIVE_SCORE_BOUND = 20.0, color_fitting.py:35,
      143-148); emit scores/divisor as float32 (6 cols). The bound is
      uniform per-cell scaling — preserves all state orderings and signs.
      Saturation canary = fraction with divisor > 1.
    - cmy8: (ctx-corrected) state scores -> marginal -> degenerate clip
      ±2.0 -> per-plane PAVA -> float32 (3 cols); unsupported plane
      exactly 0.0.
30. One-owner freeze per page (color_evidence.py:447-485 +
    payload_model.freeze_page_owners): candidates in ascending
    (window heldout_logloss, patch_id); first observer of a physical cell
    owns it; payload-cargo cells only; row-major cell order.
31. Blocks: per (source_sha256, lane, page, tile): 4096-bit observed
    bitmap + float32 rows (arity 6/3) + origin table. Same-lane
    multi-capture union = SUM of distinct captures' float64 vectors over
    the union bitmap (TileAttemptView components sorted by
    (source_sha256, block_id); one block per source; never the same
    physical capture twice).

### I. Attempts (color_attempts.py:217-367, core/color_tile.py, channel.py)
32. Invert placement: `physical = view.llr_cells_f64.reshape(4096,A)
    [payload_flat]`; `sequential[order] = physical` with
    `order = keystream.color_cell_permutation(seed, counter,
    payload_cells)`; same scatter for observed bits.
33. cmy7 (stream "main"):
    a. Pack geometry: 11 bits / 4 cells (CMY7_BITS_PER_PACK=11,
       CMY7_CELLS_PER_PACK=4); codebook = 2048 11-bit words -> 4
       MSB-first radix-7 digits (channel.py:52-76); 353 unused tuples
       never admitted.
    b. Support gate 1: pack complete iff all 4 slots observed; scatter
       `repeat(complete, 11)` through the inverse interleave
       (`code_support[interleave] = mapped_support`); every FEC child
       must carry >= its active_information_bits of support.
    c. Demap (color_tile.py:88-157): zero incomplete packs; signs =
       1−2*dither; exact 2048-candidate soft demap
       (channel.py:244-327): metric = sum of 4 per-cell state scores
       (W column = 0) [+ prior @ bits for iteration]; normalized
       exp-weights matmul against the candidate bit table; log ratio;
       row-local logaddexp fallback when a partition sum <=
       1024*float64.tiny; extrinsic = result − prior. Un-dither
       (multiply signs), scatter `code_llrs[order] = mapped`.
    d. Support gate 2: re-check per-child active-information floor on
       NONZERO demapped LLRs.
    e. demapiter3 (CORE; color_tile.py:160-214, DEMAP_ITERATIONS = 3):
       decode_frame(llrs, max_iters, alpha=0.8, want_extrinsic); while
       not ok and iterations remain: prior = clip(extrinsic, ±20)
       (LLR_CLIP = 20.0), re-demap with prior, decode again; stop on CRC
       success; per-child n_iters summed; no soft output escapes the
       attempt. max_iters = 60 baseline / 150 retry stage
       (tiles.py:54-56), BP_ALPHA = 0.8.
34. cmy8 (one stream per attempt): plane = stream index in
    spec.stream_ids; support = count(observed & sequential[:,plane] != 0)
    >= fec.active_information_bits; decode:
    `decode_frame(llrs * (1 − 2*dither), ...)` (color_tile.py:315-338).
    Attempting C never evaluates M or Y; per-plane graceful degradation
    ends here (a dead plane simply never certifies its stream).
35. Certificate: CRC-certified user bits -> stream certificate; attempt
    identity includes demap_iterations (distinct decoder = distinct
    attempt identity).

## 3. Copy vs rewrite

COPY-AND-STRIP (bit-exact format law or hard-won numerics; keep arithmetic
and constants verbatim, strip validation/docstrings):
| What | Where |
|---|---|
| CMY7 codebook/inverse/bit tables, cmy7_map/inverse | src/holo/core/channel.py:52-88,185-211 |
| cmy7_soft_demap incl. prior fold + underflow fallback | src/holo/core/channel.py:244-327 |
| states_to_planes/planes_to_states, state_score_margins | src/holo/core/channel.py:129-151,214-228 |
| cmy7 encode/demap/iterated decode, cmy8_decode_stream | src/holo/core/color_tile.py:68-236,315-338 |
| QDA fit (double ridge, shrinkage, collapse guard) | src/holo/receive/color_detect.py:214-325 |
| qda_log_scores, cmy7_relative_scores | src/holo/receive/color_detect.py:328-364 |
| cmy8 marginals + degenerate clip | src/holo/receive/color_detect.py:400-495 |
| PAVA map (tie-pool, class-bal, pmin, zero-node) + apply | src/holo/receive/color_detect.py:527-681 |
| cmy8 support qualification floors | src/holo/receive/color_detect.py:777-842 |
| blind 2-Gaussian EM component detector | src/holo/receive/color_detect.py:90-142 |
| head Newton (objective/Hessian/line search/box) | src/holo/receive/color_calibration.py:166-284 |
| class_balanced_weights, head_sub_split | src/holo/receive/color_calibration.py:138-163,296-307 |
| fit gates + floors of fit_cmy7_head (drop leak checks) | src/holo/receive/color_calibration.py:381-421 |
| owner selection + parity split + sparse repair | src/holo/receive/color_fitting.py:259-315 |
| detector fit incl. cmy8 calibration population rule | src/holo/receive/color_fitting.py:318-410 |
| evidence_with_divisor order-of-ops + L-inf bound | src/holo/receive/color_fitting.py:89-166 |
| three-way gate + deployment_saturation | src/holo/receive/color_stack.py:374-416 |
| ctx: one_versus_rest, ordered_offsets, anchor_curve | src/holo/receive/color_neighbourhood.py:159-252 |
| ctx: region bins (dedup + dense conv) | src/holo/receive/color_neighbourhood.py:90-156; detect.py:280-341 |
| ctx: _solve_offset (canonical sigmoid, bisection) | src/holo/receive/detect.py:402-449 |
| ctx: matrix sweeps + per-curve gate + apply | src/holo/receive/color_context.py:253-283,449-587,728-750 |
| NCC anchor (rectified frame, weighted NCC, parabola) | src/holo/receive/color_anchoring.py:227-350 |
| anchor candidate budget/selection + measure gate | src/holo/receive/color_anchoring.py:353-444 |
| plane residual Theil–Sen + inlier LSQ | src/holo/receive/color_registration.py:94-175 |
| corrected-point sampling (offsets -> pose -> resample) | src/holo/receive/color_anchoring.py:556-608 |
| aperture filter / crop / sample kernels | src/holo/receive/color_sampling.py:59-198 (+APERTURE_CELLS _payload_sampling.py:36) |
| reference states / site lookup | src/holo/receive/color_anchoring.py:83-145 |
| certified projection (furniture + per-stream re-encode) | src/holo/receive/color_projection.py:102-207 |
| known-rows derivation (drop _validate wall) | src/holo/receive/known_field.py:162-252 |
| sequential payload inversion + child support floors | src/holo/receive/color_attempts.py:149-215,237-263 |
| pool-law masks + fully-certified addresses | src/holo/receive/color_pool.py:29-90 |
| one-owner freeze ordering | src/holo/receive/color_evidence.py:447-485; payload_model.py:305-360 |

REWRITE LEAN:
- `collect_color_evidence` region loop (color_payload.py:97-551): keep the
  ordering (masks once, crops once, registration, ladder, emission), drop
  arm_override/StackConfig/plane-field threading into plain optional plugin
  hooks and the progress callbacks.
- `fit_region_stack` (color_stack.py:549-911): rewrite as a straight-line
  ladder A0/A1 -> A4 -> A5 with the copied gates; arms behind a simple
  `arms=(...)` parameter.
- ColorWindowEvidence/blocks/records: fold into holo3/data.py frozen
  dataclasses without __post_init__ validation walls.
- attempt orchestration (color_attempts.attempt_color_tile): keep gate ->
  demap -> decode flow, drop boundary-validation ceremony.
- Summaries (Region/Conditioning/Context/WindowPhotometry): replace with
  small diag event payloads (counts + reasons only).

## 4. Measured-channel invariants that MUST survive
- Equal-prior QDA, no class prior — payload symbols are uniform; furniture
  frequencies (45% W word bias) must not leak into evidence.
- Class balancing in EVERY colour fit and gate (PAVA, head, ctx, legs) —
  unweighted objectives fit the furniture log-prior, measured offsets ≈
  log(count_k/count_W) (MEASUREMENTS §4.1).
- cmy7 L-inf bound = uniform per-cell scaling at 20 — componentwise clipping
  reorders states and breaks the exact pack7 demapper's joint-logit contract.
- Head fitted on the QDA's HELD-OUT side only — the overconfidence is
  out-of-sample (19% saturation, wrong cells at median |s| 18.8/20).
- satfloor30 second gate — furniture-NLL gate alone adopted in a lane where
  the head strictly LOSES certificates (l00, sign test p=3.6e-77); the empty
  band 0.221-0.455 makes 0.30 drift-safe.
- Three-way gate (total strict, word+dust not worse, slack 1e-9) with
  BIT-EXACT fallback — a refused arm returns the SAME arrays, never an
  identity transform.
- ctx curves zero-anchored + direction from the state's plane bit — an
  unanchored curve re-priors the detector (A4's job); the per-plane K port
  is RETIRED (0/17 lanes: one curve per plane spends itself on 83% word).
- ctx bins cross-window over deduplicated region cells; known bits overwrite
  provisional ink; incomplete neighbourhood = bin -1 = never corrected.
- Canonical two-branch sigmoid in _solve_offset (NOT scipy expit) — 1-3 ulp
  divergence on negative inputs; one sigmoid site in the codebase.
- cmy8 PAVA scored by the SAME QDA that fits it (E017.5: a foreign score
  axis breaks the map); word sites stay OUT of PAVA; dust+certified in.
- Unsupported/degenerate cmy8 plane emits exactly 0.0 (erasure), clip ±2.0
  on degenerate planes — dead-Y closes (xerox c2-cmy8, sheet I Y bands)
  depend on erasures, not garbage LLRs.
- E017.6 (0, 0.5) PAVA anchor node — keeps QDA's decision boundary at
  score 0 under asymmetric score magnitudes.
- Sparse-state split repair — a one-tile p120 region can strand all three
  dust examples of a state on one parity; without repair cmy8 cannot fit.
- Registration is held-out gated against the shared pose and quality is a
  validity gate only (not a regression weight); zero model below 8 anchors.
- demapiter3 inside ONE attempt: extrinsic clipped ±20, no soft state
  escapes, n_iters summed; at 1 it is byte-identical to plain decode
  (xerox c3-cmy7 771 -> 810; l00 413 -> 500).
- Attempt support floors: complete-pack scatter through the REAL inverse
  interleave, then per-child nonzero-LLR floor (cmy7); per-plane nonzero
  floor (cmy8). Cheap gates before the expensive demap.
- Same-lane union = sum over DISTINCT captures; never raw + its decimation;
  one ordinary state freezes one DPI (engine-level, but emission relies on
  it: block identity is (source, lane, page, tile)).
- Owner rule (heldout_logloss, patch_id) ascending, first observer wins —
  deterministic ownership is what makes worker-count-independent merges
  possible.
- Divisor probe (255 vs 1) is REGION-pooled over the shared crops — a
  per-window divisor would split one region's photometric scale.

## 5. DROP (aggressively)
- HOLO_COLOR_STACK_FORCE_NULL env contract, effective_demap_iterations
  indirection, StackConfig sweep threading, policy-id string machinery
  (COLOR_PAYLOAD_POLICY_ID) and token generators.
- arm_override / UPLIFT_ARMS / u-lane scheduling law, R-lane and refine
  lineage plumbing (_refine/_uplift_window_dependencies), LaneContext.
- A4b conditioning (color_conditioning.py) as core — measured null-to-
  negative; keep only the sibling-allowed marginal kernel
  (color_detect.py:367-427) if the arm is ever rebuilt.
- All __post_init__ validation walls (readonly re-buffering, sha-format
  checks, provenance replay validation in ColorCaptureEvidence,
  known_field._validate, ConditioningPopulation checks, leak/overlap
  checks in fit_cmy7_head).
- Summary dataclasses with 15+ diagnostic fields; publish counts as events.
- cert_population_preview (P6 report-only), RegistrationAnchors persistence
  (keep the in-memory return only if the plane_fields arm is built),
  pre_head vs post_head double canary (keep one saturation number).
- Resume/journal/state-codec, mint-once module-global _PROJECTION_CACHE
  (replace with a per-run dict owned by the engine), verify_source_unchanged
  stat/sha re-authentication, quarantine/supersession machinery.
- The retired per-plane ctx K port, margin-gated pack erasure (P4),
  dispersion floors (dispfloor/normdisp), aggregate N>=300 calibration
  switch — all measured dead.
- cmy8_decode_payload convenience (all-streams); holo3 attempts one stream.

## 6. holo3/data.py needs (plane-native; certificates carry source tag)
Consumes: Capture (per-plane u8 mmap views + RGB accessor for colour lanes),
Window/Pose (patch_id, region_index, page, pitch_px, points(), matrix()),
FormatSpec fields listed in §1, certificate set indexed by address.
Produces / needs types:
- KnownRows: states i8 (N,), component_bits u8 (N,3), component_mask bool
  (N,3), furniture_kind i8 (N,), dependency ids.
- PlaneResidual: intercept_xy, slope_xy (f64 pairs), n_anchors int.
- ColorEvidenceRow (per window): page, page_cells_yx i32 (N,2),
  values f32 (N,A), heldout_logloss f64, patch_id, kind.
- EvidenceBlock: kind, address, observed bitmap (4096 bit), llr f32 rows,
  source tag; TileAttemptView = canonical component list + summed f64
  (64,64,A) tensor.
- Certificate: address, stream_id ("main"|"C"|"M"|"Y"), user_bits,
  origin attempt id, source tag (producing plugin).
- Fit snapshot passed to jobs: QDA (means (S,D), cholesky tuple, logdets,
  clipped_planes, degenerate), PAVA maps (score/prob nodes, n_labels),
  Cmy7Head (scale, offsets(6)), ContextHead (offsets (C,3,9), applied).
Thread notes: region jobs are pure over (raster mmap, placements, cert
snapshot); detector/head/ctx fits are region-local transients. Shared
state to make explicit: the projection memo (pure function of
(spec, address, cert-id set) — safe as a per-worker or merged cache), the
@cache site lookups (pure of family_seed — safe), and the certificate
frontier (snapshot per barrier; emission masks derive from it). Evidence
rows/blocks/attempts/certificates are FACTS for the single-writer merge.

## 7. Pitfalls / incidents
- E017.5: calibrating PAVA on scores from a different QDA than the one
  scoring at deploy time silently mis-scales LLRs — API couples them.
- E017.6: missing (0,0.5) anchor node moved the p=0.5 crossing off score 0.
- 018.7 LLR-honesty: every emitted LLR bounded (linf20 / PAVA clamp /
  clip 2.0); unbounded evidence forged certificates upstream in e018.
- e030/e032 ordering inversion: discovery-sheet channel tiers do NOT
  predict receiver recoverability (cmy7 ranked above cmy8, closed the
  other way) — never gate a decode path on characterize numbers.
- MEASUREMENTS §9.3: fitting a candidate calibration on a different
  population than the incumbent's turns the three-way gate into a
  comparison of fitting regimes (word leg optimistic, dust pessimistic).
- §7.7 retraction: the "+34% peak RSS from holding three feature tuples"
  was cross-run contention; the drop-when-consumed ownership rule is
  hygiene, not the peak. Peak is the finest rung's crops.
- Sheet-I Y dead bands are a printer Y-plane x-registration SINUSOID
  (0.83 dot, ~100 mm period) — a linear-in-y residual cannot absorb it;
  that is the plane_fields arm's territory, not a reason to bend A1.
- pyflakes undefined-name sweep caught 2 real bugs in this stack — keep
  the gate in holo3 acceptance.
- Anchor NCC at fixed 2 px/dot rectification: fit in PRINT-DOT units so
  the 0.5 inlier gate means the same at every DPI lane.
- The hash family 131y+17x is load-bearing four ways (&1 QDA split, &2
  head sub-split, &4/&8 reveal); two odd-coefficient linear forms mod 2
  are the SAME split — never "improve" the constants (012.3-class trap:
  copy, don't re-derive).
- int8 states with -1 sentinel: int64 costs 8x on million-cell pages and
  every consumer reads i8.

## 8. Open questions for the contract author
1. Close margin on xerox c2-cmy7: PK-FINAL 1,559 certs include +15 from
   the u03-a3 lane. Does the fountain close without them (1,544)? If not,
   holo3 needs a minimal "A3 pass over the residue" tier even though A3 is
   an arm. Recommend: verify during acceptance 6; build A3 as a dial-on
   plugin pass either way.
2. Where does the cmy7/cmy8 retry stage live in the frontier loop —
   is RETRY150 (max_iters 150) a cost tier of the same attempt plugin
   (recommended: one plugin, stage in the job key), and does the tried-set
   floor key on (address, stream, component-block-set, demap_iterations)?
   src/holo keys attempt identity on exactly that tuple.
3. Multi-capture colour: the campaign corpus is single-capture per colour
   volume except sheet I (three 2400 dpi captures). Confirm colour union
   semantics in holo3 = same-lane block sum per capture (K's F1-after-
   de-correlation law) with no per-capture reweighting — src/holo does a
   plain sum.
4. Label rows (pool law L2/L3): keep, or accept the fit-population change?
   They were live for all four target closes (policy v5-pool-law), so
   parity argues keep; they cost the label-row plumbing in §A5.
5. Does holo3 keep the per-region baseline fit alongside the selected fit
   (src/holo carries both for diagnostics only)? Recommend: drop, keep
   only the selected fit and its loss.
6. plane_fields arm API: is the RegistrationAnchors return (per-plane
   per-anchor offsets/quality/bucket) part of the frozen registration
   contract from day one, or added when the arm lands? It is free to
   produce (already computed) but is a second output type in data.py.
7. cmy8 emission stores PAVA-calibrated LLRs in blocks; attempts then only
   un-dither and BP. Confirm holo3 keeps calibration upstream of
   persistence (src/holo layout) rather than storing raw marginals.
8. The A5 ink map costs one full evidence pass per region even when the
   fit later refuses on count floors; src/holo hoists the two count floors
   (label_floor_refusal) but not the no-valid-bin check. Fine to keep the
   hoist only, or also require emitted-cell floor before binning?
