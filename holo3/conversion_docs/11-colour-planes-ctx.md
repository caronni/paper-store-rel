# 11 — Colour plane structure + context

Sources pinned at worktree eeeed7a; paths relative to
<checkout>. Scope: the region-level colour machinery
between "windows placed, RGB sampled" and "per-cell evidence handed to the
tile decoder": format-truth anchoring, ownership + the deterministic fit
split, per-plane registration residuals (A1), the region arm ladder
(StackConfig), the MULTI-STATE CONTEXT MATRIX (A5 — the campaign's largest
yield), the §8.2 pool-law primitives, and the §6.2a supplemental-arm API
shape. The QDA/PAVA detector, cmy7 head fit, and demapiter3 are the
colour-detect/calibration distill's; this spec names their interfaces
exactly where the ladder calls them.

## 1. Purpose, inputs, outputs

Purpose: for one (capture, page-region) at one footing, fit the colour
evidence model on format-known + certified cells, choose among gated
correction arms, and emit bounded per-cell evidence for every payload cell
still in an open tile.

Inputs (per region-fit job; all snapshots, job is pure):
- `row_tuple: tuple[WindowRows, ...]` — placed windows (E022 poses), one
  entry per window (fields in §6).
- per-window `features: (N,3) float64` — RGB reflectance means sampled at
  cell centres from the RawRGBRaster through the window pose (sampling
  leaf's job); plane order R,G,B in the feature vector, C/M/Y in evidence.
- `family: cmy7 | cmy8` (from FormatRow), `cell_dots: int`,
  `layout.cells_yx`, `layout.tiles_yx`, `seed`, `family_seed`,
  `stream_ids` (format distill).
- certificate snapshot: certified (page,ty,tx,stream) set + per-cell known
  component bits (the KnownField the payload stage derives).
- `StackConfig` (frozen; §2.E) and optional `arm: None|"off"|"a3"|"a4b"`.

Outputs:
- selected region model (`ColorQDAModel` + for cmy8 a `CMY8Detector`),
  optional `Cmy7Head`, optional `ContextHead` + per-row context bins,
  chosen feature tuple.
- per-row emitted evidence: cmy7 = `(N,6)` float64 W-relative state logits
  bounded L∞≤20; cmy8 = `(N,3)` float64 per-plane LLRs (positive = ink),
  masked to open tiles by the emission mask.
- per-arm accounting counters (jobs, cpu-seconds, curves adopted,
  certificates later attributed via the certificate source tag).

## 2. Algorithm

### A. Format-truth anchoring (color_anchoring)

1. Site lookup, one `(64,64) int16` table per family_seed: word/dust cells
   from `pilots.color_site_cells_yx(family_seed)` (p120: 100 word sites →
   indices 0..99, 20 dust sites → 100..119, payload = −1). Cache per seed.
2. `color_reference_states(page, cells_yx)`: for each cell, local =
   `(y%64, x%64)`; site index from the table; payload → state −1 kind −1.
   Known sites: tile counter = `spec.tile_counter(page, y//64, x//64)`;
   word states = `pilots.color_word_states(seed,(counter,))[0][site]`
   (kind 0); dust states =
   `pilots.dust_state_values(seed,(counter,),codec)[0][site-100]` (kind 1).
   State bit law: bit k of state s = `(s>>k)&1`, k=0 C, 1 M, 2 Y (uint8;
   `states_to_planes`/`planes_to_states`, core/channel.py:129-141). cmy7 =
   states 0..6 (7=CMY absent); cmy8 = 0..7. W = 0.
3. Certified payload cells get their state (kind stays −1) and their known
   component bits/mask filled from the certificate snapshot before any fit
   (partially certified: mask true only on certified planes, state −1).
4. Label-site rows (`_label_site_rows`, color_anchoring.py:175-224): a
   certified-complete window or a label placement joins the region fit
   with ONLY its word/dust sites — no payload rows, no emission. `None`
   when a window covers no format-known site.

### B. Ownership + deterministic split (color_fitting.py:259-315)

1. Deduplicate known cells (state ≥ 0) across windows by canonical key
   `(page, y, x)`; iterate windows in ascending `patch_id`, first wins.
2. Sort keys ascending; produce `window_ordinals, row_indices, states,
   kinds, keys, search` aligned arrays (`_OwnerSelection`), plus
   `gather(features_tuple, dtype)` = select each row's value from its
   owning window's array.
3. Split: `search = ((131*y + 17*x) & 1) == 0`; held-out = complement.
   Sparse-state repair: any state with ≥2 rows all on one side moves its
   canonical FIRST row to the empty side. (The `&2` sub-split belongs to
   the cmy7 head fit; `&12` reveal codes to the A4b arm.)

### C. Per-plane registration (A1; color_anchoring + color_registration)

What the paper closes needed of plane pose: ONE shared window pose (E022)
plus, per plane p ∈ {C,M,Y}, a residual
`delta_p(y) = (dx0+dx1*y, dy0+dy1*y)` in print dots, y = page-cell-row /
`layout.cells_yx[0]` ∈ [0,1]. Nothing finer is core (A2/regmap =
CLOSED-negative; the Y sinusoid is the plane_fields ARM's business).

1. Blind bits for templates: `blind_component_bits`
   (color_detect.py:90-140): per plane, normalize by 2%/98% quantiles
   (range floor 1e-6), 2-Gaussian EM with pinned 0.5 mixing, µ init
   (0.1,0.9), σ init 0.15 floor 1e-3, ≤40 iters, stop at Δµ<1e-4; LLR sign
   positive-is-ink. Confidence = |LLR| ≥ `BLIND_CONFIDENT_LLR = 2.0`.
   Known component bits overwrite detected bits, confidence → True.
2. Anchor candidates, per plane: cells on the SEARCH side with known ink
   in that plane (`mask & bits & search`), bucketed 0 word / 1 dust /
   2 certified-payload; dedup per canonical key.
3. Budget: per bucket, sort keys canonically; if > 512
   (`_ANCHOR_BUDGET_PER_KIND`) take left edges of 512 equal-width bins
   (`i*len//512`) — replay-stable, no RNG.
4. Per anchor, `_measure_anchor` → `_rectified_ncc`
   (color_anchoring.py:280-380): 3×3 neighbourhood template (skip if any
   neighbour missing), bits from detected, weight 1.0 confident / 0.05
   not, centre forced bit=1 weight=1, refuse a flat template. Rectify at
   `_RECTIFIED_PX_PER_DOT = 2` px/dot: `cell_px = 2*cell_dots`;
   `max_shift = max(2, round(5*cell_px/6.0))` (`_ANCHOR_MAX_SHIFT_PX=5`);
   sample the plane through the pose (`ndimage.map_coordinates`, order 1,
   nearest), template = `kron(1-bits, ones(cell_px,cell_px))`. Sliding
   weighted NCC (`_xcorr_offset_ncc`, :227-277): weighted-centred window
   and template, eps 1e-9 in the norms; argmax + per-axis parabolic
   refinement clipped ±0.5 (denominator guard 1e-12). Offset returned in
   PRINT DOTS `(dx,dy)` (÷2). Quality gate `_ANCHOR_MIN_Q = 0.10`.
5. Fit per plane, per component x and y (`_fit_component`,
   color_registration.py:94-137): valid = finite ∧ quality>0. <8 valid
   (`COLOR_ANCHOR_MIN`) → zero model. <16 (`COLOR_SLOPE_MIN`) or page span
   <0.15 (`COLOR_SLOPE_MIN_SPAN`) → median constant, slope 0. Else
   Theil–Sen: median pairwise slope over pairs with |Δy|>0.05; intercept =
   median(v − slope·y); inliers = |resid| ≤ 0.5 (`COLOR_ANCHOR_INLIER`);
   if ≥8 inliers refit plain LSQ on them, else keep the medians.
   `n_anchors = min(n_x, n_y)`; `supported = n_anchors ≥ 8`.
6. Apply (`_features_with_page_fraction`, color_anchoring.py:556-608):
   `offset_xy = intercept + y_frac*slope` per row; `local_delta_yx =
   offset_xy[:, ::-1] / cell_dots`; `scan_delta = local_delta @
   pose.matrix().T`; resample each plane at `scan_points + delta` (shared
   filtered crop, map_coordinates order 1). ANY corrected point outside
   the raster ⇒ the whole corrected arm is ineligible (`corrected=None`)
   — the shared pose remains usable. KEEP the `offsets_override` seam: an
   arm (plane_fields) may pass per-plane `(N,2)` dot offsets that replace
   the residual prediction for that plane; `None` = historical branch.

### D. The arm ladder (color_stack.py:549-911, rewrite lean)

Order is law: A0/A1 choice → [A3 arm-only] → A4 head (cmy7) → [A4b
arm-only] → A5 context LAST (it corrects what the region emits). Every
adoption uses THE THREE-WAY GATE: candidate total held-out loss strictly
better by `1e-9` (`STACK_GATE_SLACK` = `HEAD_GATE_SLACK` = 1e-9) AND word
leg not worse (+1e-9) AND dust leg not worse. Every refusal is an EXACT
NULL: the predecessor's own array objects, never an identity transform.

1. Fit detector on base features; fit on corrected features iff
   `corrected is not None`; adopt corrected via the three-way gate on the
   detector's held-out losses (word=kind 0, dust=kind 1). Drop the loser.
2. A4 (cmy7 only, core): fit the head on the selected fit's held-out
   population (calibration distill); if the head's own gate accepts, apply
   the SATURATION FLOOR: fraction of emitted payload cells whose PRE-head
   divisor `max(1, max|rel_scores|/20) > 1` must be ≥
   `HEAD_SATURATION_FLOOR = 0.30` (color_stack.py:390-416; measured on
   the population the region will EMIT — payload rows, emission mask
   applied). Below floor → head refused (temperature 1.0). Unmeasured
   sentinel −1.0.
3. A5 (§2.F below) with `ContextConfig`; hoist the two count floors
   (`label_floor_refusal`: search count ≥ 80 known cells, held-out ≥ 40)
   BEFORE building the region ink map (holo1 noted this hoist as owed —
   do it).
4. Emission composition per payload row (`evidence_with_divisor`,
   color_fitting.py:86-214 — copy the ORDER exactly):
   - cmy7: `rel = qda_log_scores(model, f)[:,1:] − [:, :1]` → head.apply →
     context.apply_states(rel, bins) → `divisor = max(1,
     max|rel|/CMY7_RELATIVE_SCORE_BOUND=20.0)` per cell, uniform scaling
     (preserves all orderings and signs) — the bound is the LAST op.
   - cmy8: `scores = qda_log_scores` (8 cols) → context.apply_states →
     `cmy8_marginal_llrs` (per plane, logsumexp over states with bit k on
     minus off) → if qda degenerate or plane clipped, clip ±2.0
     (`DEGENERATE_LLR_CLIP`) → per-plane PAVA calibration `llrs()` →
     unsupported plane emits exactly 0.0. There is NO ±12 clamp in the
     colour path — `CTX_LLR_CLAMP=12.0` is K's marginal-locus kernel only.
5. Emission mask (color_pool.py:64-91): tile code = `(y//64)*tiles_x +
   x//64`; suppress cells in tiles whose every required stream is
   certified (`fully_certified_color_addresses`, :42-61: address ∈
   certificates with all `spec.stream_ids` present, fail-closed on
   same-stream contradiction). Payload cargo cells:
   `pilots.color_payload_cell_indices(family_seed)` as a 4096-bool mask
   indexed by `(y%64)*64 + x%64`.

### E. StackConfig (frozen record, the ONLY tunables)

`context: ContextConfig(variant="matrix", min_search=80,
min_search_per_class=20, min_validation=40, min_validation_per_class=10,
max_labels=40_000, sweeps=3)`; `head_saturation_floor=0.30`;
`window_photometry: prior_labels=20.0` (arm-only). Threaded explicitly
job→fit; no environment reads anywhere (holo1's FORCE_NULL env hatch is
dropped; a baseline dial, if kept, is a CLI flag that sets
variant="off" + no head + no arms).

### F. THE MULTI-STATE CONTEXT MATRIX (A5 — copy numerics exactly)

One monotone 9-bin curve per (state-column, plane): correction
`score_s += Σ_k f_{s,k}(count_k)`, count_k = 8-neighbour ink count in
plane k, applied at the STATE locus before marginalization (cmy8) /
before the L∞ bound (cmy7).

1. Region ink map (color_neighbourhood.py:90-156): per window in ascending
   patch_id order, provisional ink = cmy8: component LLR > 0; cmy7:
   `plane_marginals(augment(six logits)) > 0` where `augment` prepends
   W's zero logit and `plane_marginals` = logsumexp(states with bit) −
   logsumexp(without) (:66-87). EXACT BITS WIN: known cells use
   `known_component_bits`, never the detector. Evidence is produced per
   row via the selected fit (post-head for cmy7) and dropped immediately.
   Concatenate all windows; dedup by `y*width + x` (`np.unique`
   return_index/inverse — first occurrence in patch-id order wins).
2. Counts (detect.py:280-315, copy): dense bounding grid, 3×3 ones kernel
   with centre 0, `ndimage.convolve` mode constant; valid ⇔ all 8
   neighbours present. Bins = counts 0..8, invalid → −1
   (`N_CONTEXT_BINS=9`; detect.py:318-340 semantics). Scatter back to
   per-row `(N,3) int8` in the caller's row order.
3. Populations: gather features and bins through the ownership; fit on the
   SEARCH side, gate on held-out. Scores at the locus: cmy8 =
   `qda_log_scores` (N,8); cmy7 = augment(post-head relative scores)
   (N,7), reference column 0 pinned (curves fitted for columns 1..S−1
   only → offsets width S−1=6; cmy8 fits all 8). Weights =
   `class_balanced_weights(states)` (color_calibration.py:138-163: every
   represented state equal total mass, normalized to mean 1) — computed
   ONCE per side over the full population.
4. Coordinate ascent, `sweeps=3`, state-major plane-minor order, running
   scores updated on BOTH sides as curves adopt; a sweep with no adoption
   breaks early; a later sweep must NOT erase an earlier adopted verdict
   (setdefault on refusal). (color_context.py:449-513.)
5. One curve (`_fit_one_curve`, :516-587):
   a. rows = fit-side rows with bin ≥ 0 in this plane; floors: rows ≥ 80,
      min(positives=count(state), rest) ≥ 20; validation rows ≥ 40,
      per-class ≥ 10; refuse → curve exactly zero.
   b. subsample rows > `max_labels=40_000` by deterministic stride
      `linspace(0, n−1, limit).astype(int64)` (`stride_select`); refuse
      if the subsample lost a class.
   c. one-vs-rest logit `l = score_s − logsumexp(score_{j≠s})`
      (color_neighbourhood.py:166-176 — EXACT binary reduction of the
      multinomial coordinate step).
   d. `ordered_offsets` (:179-235, copy): walk bins 0..8 if the state
      PRINTS plane k (`bit_k(s)=1`, direction non-increasing — bleed
      over-evidences ink) else 8..0 (non-decreasing); per bin append two
      ghost observations (llr 0.0, labels {False,True}, weight
      `CTX_BIN_PRIOR=1.0`); block optimum = `_solve_offset`
      (detect.py:402-447, copy verbatim): target = Σ w·labels, TWO-BRANCH
      sigmoid (`1/(1+exp(−x))` for x≥0, `exp(x)/(1+exp(x))` else — the
      project-canonical sigmoid, v0.39 ruling; NEVER scipy expit),
      bisection on [−4, 4] (`CTX_OFFSET_LIMIT=4.0`) to
      `CTX_ROOT_TOL=1e-12`; merge adjacent blocks while
      `blocks[-2].offset < blocks[-1].offset` and re-solve pooled.
   e. zero-anchor (:238-252): subtract the class-balanced weighted mean of
      `offsets[bins]` over the fit rows — SHAPE only (level is the
      head's/QDA's job; anchoring preserves monotonicity).
   f. per-curve gate: on the DISJOINT held-out rows (same stride cap),
      class-balanced binary NLL of `logit + curve[bins]` vs incumbent
      logit must improve strictly by 1e-9; else refuse to exact zero.
6. cmy8: zero out (offsets + applied flags) every plane the detector
   erases (`supported_planes`), after fitting. No curve adopted anywhere
   → no head, emit the literal pre-A5 arrays.
7. Region gate, in the EMITTED space (:693-717, 753-801): incumbent vs
   candidate on the held-out population — cmy8: apply `emitted_llrs`
   (marginal + degenerate clip + PAVA per supported plane), per-plane
   binary NLL against printed bits `state_bits(8)[state]`, concatenated
   over supported planes, class-balanced by bit; cmy7: multinomial NLL of
   `augment(head-corrected scores)`, balanced by state. Three legs:
   total / word (kind 0) / dust (kind 1); adopt iff total −1e-9 better and
   both legs not worse; an unmeasured leg (sentinel −1.0) never refuses.
8. Apply (`apply_states`, :253-283): pad a tenth all-zero bin column;
   gather `delta = Σ_k padded[:, k, bin_k]` with bin −1 mapped to the zero
   slot — a cell with an incomplete neighbourhood receives exactly zero.
   Bins ride the region result (computed once); head and bins travel
   together or not at all.

### G. Supplemental-arm API (§6.2a SCHEDULE LAW — API shape only)

An arm that cannot prove universal non-regression is never gated into the
core ladder: it is SCHEDULED, additively, on the residue. holo3 contract:

- Arms = plugins beside the core stages, dial-off by default. Known arms:
  `off` (re-run the pre-campaign A0/A1 skeleton on the residue — the
  re-timing safety net), `a3` (per-window photometric maps,
  color_locality.py — constants: prior_labels 20.0, halo pool weight 1.0,
  min search labels 40, min states 3 [W + ≥2 inked], min heldout 20, gate
  slack 1e-9, variance floor 1e-12, adaptive halo = own bbox dilated by
  own height/width per side, own labels first, pool only on starvation),
  `a4b` (KnownField-conditioned marginals), `plane_fields`/`color_field`
  (per-plane offset override via the §2.C seam + `_rectified_ncc` probe
  blocks — the NCC block edge is a parameter for exactly this caller).
- SCHEDULING FUNCTION: arm lanes run after the core frontier reaches
  fixed point at the finest footing, in the order off → a3 → a4b; an arm
  job's domain is the UNCERTIFIED residue at its start (pool-law emission
  mask makes a certified address unreachable by construction — monotone,
  no adoption gate, the zero-wrong audit is the only bar). Gating: every
  arm needs poses + a nonempty residue; a4b additionally needs a certified
  frontier (conditioning is vacuous without one — the v0.54 zero-frontier
  fix). Tried-set floor: key (region, arm, residue-digest); never re-fire
  on identical inputs.
- The forced arm is an EXPLICIT job parameter (never ambient/env). Forcing
  a lane does not bypass the arm's own per-window/per-stratum pre-gates;
  a4b's forced lane alone stops consulting its region comparison.
- Per-arm accounting: certificates carry the producing plugin+arm as
  source tag; engine tallies jobs/cpu-seconds/certs per tag.
- Recorded asymmetry to preserve: A5 bins and fit population are cut
  UNCONDITIONED (never through A4b); the conditioned∘A5 composition exists
  only inside the a4b lane, bounded by the residue.

## 3. Copy-vs-rewrite table

| What | Source (file:lines) | Verdict |
|---|---|---|
| `_solve_offset` (canonical sigmoid + bisection) | src/holo/receive/detect.py:402-447 | COPY verbatim |
| `context_neighbour_counts` (dense conv) | detect.py:280-315 | COPY, strip guards |
| `context_bins` semantics (0..8, −1) | detect.py:318-340 | rewrite lean, keep mapping |
| `ordered_offsets` directional PAVA + ghost prior | color_neighbourhood.py:179-235 | COPY |
| `anchor_curve` zero-anchoring | color_neighbourhood.py:238-252 | COPY |
| `one_versus_rest`, `plane_marginals`, `augment`, `provisional_ink`, `state_bits`, `stride_select` | color_neighbourhood.py:44-176 | COPY, strip guards |
| `region_context_bins` (dedup order, exact-bits-win, evidence dropped per row) | color_neighbourhood.py:90-156 | COPY-AND-STRIP |
| `_fit_matrix_curves` + `_fit_one_curve` | color_context.py:449-587 | COPY-AND-STRIP (drop ContextCurve records → counters) |
| `ContextHead.apply_states` + `_bin_index` (tenth zero column) | color_context.py:253-283 | COPY |
| `emitted_llrs` + `_region_losses` + `_balanced_mean`/`_binary_nll`/`_multinomial_nll` | color_context.py:406-433, 728-801 | COPY-AND-STRIP |
| `label_floor_refusal` hoist | color_context.py:594-607 | rewrite (2 lines) |
| `class_balanced_weights` | color_calibration.py:138-163 | COPY |
| `_fit_component` + `fit_plane_residual` (Theil–Sen exact historical, E017/D5) | color_registration.py:94-175 | COPY, strip validation |
| `PlaneResidual` | color_registration.py:50-91 | rewrite as plain dataclass |
| `_xcorr_offset_ncc`, `_rectified_ncc`, `_measure_anchor` | color_anchoring.py:227-380 | COPY (keep block-edge parameter for the field arm) |
| `_fit_registration` anchor harvest + budget | color_anchoring.py:415-553 | COPY-AND-STRIP (drop RegistrationAnchors entirely) |
| `_features_with_page_fraction` (+ offsets_override seam) | color_anchoring.py:556-608 | COPY |
| `_color_site_lookup` + `color_reference_states` | color_anchoring.py:83-145 | COPY (pilots draws = format law, format distill) |
| `_neighbor_rows` 3×3 index table | color_anchoring.py:148-172 | COPY |
| `_owner_selection` + `_deterministic_fit_split` ((131,17)&1 + sparse repair) | color_fitting.py:259-315 | COPY |
| `_OwnerSelection.gather` | color_fitting.py:235-256 | COPY |
| `evidence_with_divisor` composition ORDER + `pre_head_saturation_counts` | color_fitting.py:86-214 | COPY the op order exactly; strip A4b branch to the arm |
| `blind_component_bits` EM | color_detect.py:90-140 | COPY |
| ladder orchestration + `_improves` + `deployment_saturation` | color_stack.py:374-416, 549-911 | REWRITE lean (order + gates only) |
| pool-law primitives | color_pool.py:29-91 | rewrite lean (trivial), keep fail-closed cert index |
| A3 fit machinery (arm) | color_locality.py:313-618 | park for the arm build; constants tabled in §2.G |
| holo2 SessionPlane / generations / pins | holo2/src/holo2/solve/plane.py (whole) | DROP — journal-era machinery; keep only "per-plane read-only mmap views" as an idea |

## 4. Measured-channel invariants that MUST survive

- Two-branch canonical sigmoid, bisection tol 1e-12, offset limit ±4 —
  the fitted curves' values ARE these numerics (v0.39 ruling; expit
  diverges 1-3 ulp on negatives).
- Class-balanced weights in every colour fit/gate — furniture is ~45% W /
  ~39% one dust state; unweighted objectives fit the prior, not the
  channel (PK3, measured: offsets land within 0.3 of log-prior).
- Zero-anchored, sign-read-off monotone curves — unanchored curves
  re-prior the detector; the direction comes from the state's plane bit,
  never fitted (keeps the family a strict generalization of K's).
- Three-way gate (total 1e-9 / word / dust) + exact-null refusals —
  what kept 0 wrong certificates in 69M audited cells.
- CONTEXT_SWEEPS=3 with per-sweep re-gating — one sweep measured short of
  the family's own optimum (softmax renormalization couples the steps).
- Bin −1 ⇒ exactly zero correction — cells without a full 8-neighbourhood
  keep uncorrected evidence (K's rule; reach is a capture property).
- Region-wide deduplicated ink map, patch-id-first-wins, exact bits win —
  cross-window correctness is why the colour ctx out-yields K's
  per-window form; iteration-order independence is replay law.
- cmy7 L∞=20 uniform per-cell divisor as the LAST op — order-preserving
  bounded durable evidence; head+context apply BEFORE it.
- Head saturation floor 0.30 on the DEPLOYMENT population — the furniture
  gate alone adopts where the head strictly loses certificates (l00,
  sign test p=3.6e-77); the floor value sits mid-band of a measured gap
  (coarse lanes ≤0.221, helped lanes ≥0.455).
- Theil–Sen + 0.5-dot inlier LSQ ladder with the 8/16/0.15 floors — the
  exact fit every colour close ran; plane-differential registration is
  real (τ 0.1–0.3 dots) and this residual is the part the closes needed.
- Search-side-only anchors, replay-stable 512/kind budget — anchors must
  not read held-out cells (gate integrity) and must not draw RNG.
- (131y+17x)&1 split with deterministic sparse-state repair — a one-tile
  p120 region must still fit its dust states.
- Discovery/characterize tiers never predict receiver outcomes (e031;
  e032 ordering inversion) — no gate in this subsystem may consume them.

## 5. What to DROP

- ALL __post_init__ validation, readonly-array freezing, shape/type
  guards, refusal-reason string vocabularies (keep a small int enum or
  plain counters for diag events).
- ContextSummary / ContextCurve / ContextFit publication records,
  WindowPhotometrySummary, ConditioningSummary, summarize_* — replace
  with a handful of counters on the diag event.
- Policy tokens (`policy_token` properties), identity segments, swept-
  constant publication — holo3 has one frozen config.
- `FORCE_NULL_ENV` and every environment read; `force_null_enabled`.
- `RegistrationAnchors` and the whole PK6/A2 per-anchor return
  (color_anchoring.py:383-412, 526-547) — the line is CLOSED-negative.
- `cert_population_preview` (P6 report-only) and its 250_000 cap.
- The retired per-plane K context port (already deleted; do not
  resurrect), `apply_context_offsets`/`CTX_LLR_CLAMP` on the colour path.
- `ArmFeatures` memory-ownership holder — plain locals + `del` (the +34%
  RSS claim was RETRACTED; keep only "drop the loser").
- A4b conditioning machinery from the CORE build (arity census,
  populations, strata) — arm-lane plugin later; the closes don't need it.
- A3 window-map fitting from the CORE ladder (override-only law) — arm
  plugin later.
- holo2 plane.py entirely: generations, pins, views locks, blob locks, fd
  budgets, attach-by-reopen, duplicate-scan resolution, done-projection
  caching, observer summaries — no resume, no journal in holo3.
- `ContextObservations` (K-shaped site-id/conflict validation) — colour
  populations are plain arrays.
- Emission-mask `assume_unique` micro-tuning debates; heldout-population
  attachment gymnastics (carry it as a plain field on the fit result).

## 6. Data-structure needs (holo3/data.py)

- `WindowRows` (frozen, per placed colour window): `patch_id: int`,
  `page: int`, `local_cells_yx: (N,2) int64`, `page_cells_yx: (N,2)
  int64`, `scan_points_yx: (N,2) float64`, `states: (N,) int8` (−1
  unknown; certified payload cells filled), `furniture_kind: (N,) int8`
  (−1 payload / 0 word / 1 dust), `known_component_bits: (N,3) uint8`,
  `known_component_mask: (N,3) bool`, `neighbor_indices: (N,9) int32`,
  pose ref (2×3 affine matrix + `points()`).
- `PlaneResidual`: `intercept_xy: (2,) float`, `slope_xy: (2,) float`,
  `n_anchors: int` — one per plane, three per region per capture.
- `OwnerSelection`: six aligned arrays (§2.B) + `gather`.
- `ContextHead`: `offsets: (C,3,9) float64`, `applied: (C,3) bool`
  (C=6 cmy7 / 8 cmy8); rides with per-row `(N,3) int8` bins.
- `Cmy7Head` (from calibration distill): scale + 6 offsets, `apply()`.
- `RegionColorModel` (the job result): QDA model (+CMY8Detector), head,
  context head+bins, chosen feature tuple ref, per-arm counters.
- `Certificate.source: str` — producing plugin/arm tag (per-arm
  accounting and the additive-arm audit hang off it).
- `StackConfig` / `ContextConfig` as in §2.E.
- Threading: the region fit is ONE pure job over snapshots (certificate
  set, KnownField bits, StackConfig); its outputs are facts merged
  single-writer. The region ink map and all fit populations are job-local.
  Feature tuples are the largest transient (one (N,3) float64 per window)
  — never share them across jobs; per-worker mmap plane views only.

## 7. Pitfalls / incidents

- e012/012.3: never hand-roll seeded draws; pilots word/dust states come
  from the format module, never retyped (a missing dtype forks the
  stream).
- The uplift target's "print-frozen" 18% cell error was DETECTOR-frozen:
  the xerox c2-cmy7 close came entirely from cell readout (head + ctx
  matrix + demapiter3) with the address ledger identical — do not skimp
  on §2.F numerics; they ARE acceptance 6.
- e032 ordering inversion + e031: channel-tier numbers must never gate or
  predict; only the three-way held-out gates rule.
- Per-plane K port retirement mechanism: one curve per plane spends
  itself on the label-dominant population (83-84% word) and the dust leg
  refuses — if a builder "simplifies" the matrix to per-plane curves the
  yield vanishes; the per-STATE factorization is the arm.
- PK4 lesson for any pooling: a neighbour's cells are evidence about the
  NEIGHBOUR (halo axis monotone against pooling weight) — own labels
  first everywhere.
- A4 head furniture gate alone is insufficient (l00: adopted while
  strictly losing certificates) — the saturation floor is not optional.
- Sweeps interact through softmax renormalization; running scores must be
  updated on BOTH populations as curves adopt, or the gates measure a
  model that is never emitted.
- `evidence_of(ordinal)` results must be dropped per row inside the ink
  map — holding all rows' float evidence at once was the colour path's
  largest possible allocation (memory budget: one production decode at a
  time on the 64 GB machine).
- Editing the anchoring numerics invalidated recorded feature libraries
  in holo1 — in holo3 the equivalent rule: §2.C/§2.F copied blocks are
  frozen; a "cleanup" that moves a float is a silent yield change only a
  full re-decode would catch.
- The Y plane at fine pitch can be dust-only and 9-22% saturated (PK6):
  expect zero Y anchors on some engines; the zero-model fallback (not a
  refusal) is what keeps the region decodable.
- M281 Y-starvation (e017/e030) is a consumable/engine fact: cmy8's
  per-plane independence + dead-plane tier is why cmy8 closes where cmy7
  dies; nothing in this subsystem may assume three live planes
  (supported_planes gating everywhere).

## 8. Open questions for the contract author

1. Refit cadence: holo1 refit the region stack per lane as certified
   labels grew. In holo3's frontier loop, when does a region-fit job
   re-fire — on a threshold of new certified labels in the region, per
   rung, or both? (Affects the tried-set key: residue digest vs label
   count.)
2. Are the u-lane arms (off/a3/a4b) required for ANY acceptance target,
   or is the arm API + accounting hooks enough for v1? (The plan says
   head+ctx+demapiter3 are core for acceptance 6; confirm the archived
   closes' certificate sets did not lean on u-lane certificates.)
3. `CONTEXT_MAX_LABELS=40_000` is a CPU bound on the Python bisection,
   and the "no ceilings" doctrine dislikes evidence caps. Keep the cap
   (measured-faithful), or vectorize `_solve_offset` batch-wise and drop
   it? (Dropping changes fitted curves on label-rich lanes — a yield
   re-verification, not a free win.)
4. Where does the certified-payload label ingestion live — does the
   payload/tiles plugin fill `states`/`known_component_*` on WindowRows
   before the region job, or does the region job read the certificate
   snapshot itself? (Single derivation wanted; producer knows it.)
5. cmy7 head boundary: fit lives in the calibration distill; the
   saturation floor and its deployment population live here. Confirm the
   floor stays in the ladder (this spec) and the head fit exports
   `(head, reason)` only.
6. plane_fields/color_field arm: is the `offsets_override` seam +
   parametric NCC block the whole required API, or does the arm also need
   the region fit to re-run under overridden features (i.e. an arm-scoped
   A0/A1-style refit)?
7. Baseline dial: keep any force-null equivalent at all (useful for
   differential debugging), or is `variant=off` + no-head config enough?
8. Emission suppression: apply the fully-certified-tile mask inside the
   region job from its snapshot (stale by one merge wave, monotone-safe),
   or at merge time? Snapshot-side is pure and cheap; confirm.
