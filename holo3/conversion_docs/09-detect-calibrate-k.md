# 09 — K-path cell readout: sampling, PAVA calibration, ctx detector, LLR

Sources pinned at worktree eeeed7a. Paths relative to
<checkout>. This subsystem is the numerical evidence
boundary of the receiver: it turns (raster + committed window pose) into
calibrated per-cell LLRs and one frozen owner per payload cell. Raw
detector scores never cross this boundary as evidence. Everything colour
(QDA heads, cmy7 calibrated head, multi-state ctx matrix, demapiter3) is
a SEPARATE distill; this spec is the grey/K luma path, which is also the
per-plane skeleton the colour path composes over.

Naming note: the task-order phrase "16-context detector" is the LEGACY
paperholo per-cell detector (2^4 neighbour contexts); it was NEVER ported.
The surviving arm is E023b's `ctx-pava-v1`: NINE ordered bins (0..8
eight-neighbour ink count) plus the protected bin −1. holo re-derived the
mask protection from E023b instead of porting paperholo's (e018 branch
record; `src/holo/receive/detect.py` context bin −1).

## 1. Purpose, inputs, outputs

Inputs (per window job; all immutable snapshots):
- `PlaneRaster`: per-plane u8 mmap view; `crop_luma(y0,y1,x0,x1) ->
  float32 (H,W)`. One ordinary decode state freezes ONE dpi per capture;
  never raw + its own decimation together.
- `Window` + committed `Pose`: page `int`, `rot_k in {0,1,2,3}`,
  `page_origin_yx (int,int)`, local affine (2x2 float64 matrix +
  origin_yx float64, `pitch_px float`), audited local cells
  `int64 (N,2)` (unique, in-window), region index, patch ordinal `int`.
- `region_pitch_px: float` — median of `pose.pitch_px` over ALL of the
  region's placed windows (payload + label rows pooled;
  `_payload_sampling._region_pitch`). A reduction computed once per
  region BEFORE window jobs are scheduled; part of the job input.
- Reference labels from the format subsystem (04):
  `reference_values int8 (N,)` — printed bit 0/1 at word/filler sites,
  −1 at cargo. NEVER re-derived here; one pinned function
  (`_payload_sampling.format_reference_values:282-310`) both place and
  payload call.

Outputs:
- Per window: `WindowEvidence` (see §6) — scores float32, PAVA knots/probs
  float64, marginal + printed LLR float32, accepted/refusal, heldout
  logloss float64.
- Per (capture-lane, region): ctx decision — offsets float64 (9,),
  adopted bool, reason str (event only, no durable record).
- Per capture-lane: `OwnedPageEvidence` — one owner per payload cell:
  page, cells int32 row-major, printed_llr float32, owner window index.

## 2. Algorithm

### 2a. Sampling one window (per-crop float32)

Constants: `APERTURE_CELLS = 0.7`, `SCORE_SPREAD_FLOOR = 1e-6` (both
`_payload_sampling.py:36-37`).

1. Map local audited cells to page cells: `rotated_points(local,
   (sy,sx), rot_k)` (exact integer np.rot90 map,
   `_payload_sampling.py:56-72`) + `page_origin_yx`; keep rows inside the
   page; scan points = `pose.points(local.astype(float64))` (affine:
   `grid @ matrix.T + origin`). Row order = the window's authoritative
   page-cell order (v1 aligns via flattened `y*width+x` keys,
   `_window_rows`; holo3 can simply emit cells already in that order).
2. Crop: project the window's 4 cell-corner points through the pose;
   `halo = ceil(0.7 * region_pitch_px) + 2`; clip to raster. Read
   `raw = crop_luma(...)` as float32.
3. Filter ONCE per crop: `filtered = ndimage.uniform_filter(raw,
   size=max(1, round(0.7 * region_pitch_px)), mode="nearest")`.
   `fill = float(np.median(raw))`.
4. Sample: `means = ndimage.map_coordinates(filtered,
   (points - (y0,x0)).T, order=1, cval=fill).astype(np.float32)`. Points
   outside `[0, raster_dim-1]` are a refusal (mis-posed window), not a
   clamp.
5. Scores (v0.39 ruling 10.2 — float32-native, EVERY constant spelled
   `np.float32` so weak-scalar promotion cannot re-widen):
   `midpoint = float32(median(means))`;
   `spread = max(float32(mean(|means - midpoint|)), float32(1e-6))`;
   `scores = (midpoint - means) / spread`  (larger = more ink).

The aperture/halo integers derive from the REGION-pooled median pitch,
not the window's own — bit-exactness of the pooled aperture across a
region is pinned (`_filter_signature`, v0.33 D7).

### 2b. Per-window PAVA calibration (`pava-v1`)

Constants: `CAL_MIN_PER_CLASS = 10`, `CAL_MIN_HELDOUT = 10`
(`detect.py:31-32`).

6. `known = reference_values >= 0`. Site parity on ABSOLUTE page cells:
   `parity = ((131*y + 17*x) & 1)` — identically `(y+x) & 1` (131, 17
   odd; holo2 `place_shared.py:113-116`). SEARCH = `known & ~parity`
   (even), HELDOUT = `known & parity` (odd). Pick ONE spelling in
   holo3/lib and use it everywhere.
7. Site ids: `page*H*W + y*W + x` int64 (overflow-checked); unique
   within each side, disjoint across sides by construction.
8. Gates, in order: `min(n_search_0, n_search_1) < 10` → refuse
   `search_class_starved`; `n_heldout < 10` → refuse `heldout_starved`.
   A refused window emits NO evidence rows (it may still serve as a ctx
   label row only if accepted — refused windows never enter any fit).
9. Fit = exact stack-PAVA (`detect._pava_nodes:211-239`): stable argsort
   of scores; sweep labels merging adjacent blocks while
   `vals[-2] >= vals[-1]` (ties pool); per block knot = mean of the
   block's scores, prob = `clip(block_mean_label, pmin, 1-pmin)` with
   `pmin = 1/(n_search + 2)`.
10. LLR map: `p = np.interp(scores, knots, probs)`;
    `llr = log(p/(1-p))` (`detect.py:161-170`). np.interp's rightmost
    equal-knot behaviour is part of the pinned result — keep np.interp.
    BOUNDED BY CONSTRUCTION: `|llr| <= log(n_search + 1)`
    (`clamp_for`, `detect.py:118-124`) — the 018.7 bounded-LLR
    invariant; no explicit clip exists or is needed on the marginal.
11. `marginal_llr = float32(llr(scores))` over all sampled cells;
    `heldout_logloss = -mean(y ln p + (1-y) ln(1-p))` float64 over the
    HELDOUT sites (probabilities are clipped so logs are finite;
    `_payload_sampling.py:384-388`).
12. WINDOW IDENTITY IS LOAD-BEARING: a calibration maps exactly the
    window it was fitted on; never apply one window's map to another's
    scores (e017 PAVA cross-fit bug).

### 2c. Region ctx detector (`ctx-pava-v1`), one fit per (capture-lane, region)

Constants (`detect.py:34-43`): `N_CONTEXT_BINS = 9`,
`CTX_OFFSET_LIMIT = 4.0`, `CTX_LLR_CLAMP = 12.0`, `CTX_BIN_PRIOR = 1.0`,
`CTX_MIN_SEARCH = 80`, `CTX_MIN_SEARCH_PER_CLASS = 20`,
`CTX_MIN_VALIDATION = 40`, `CTX_MIN_VALIDATION_PER_CLASS = 10`,
`CTX_ROOT_TOL = 1e-12`.

13. Pool the region's ACCEPTED windows (payload rows + label rows) in
    ascending patch-ordinal order — the exact single-pass order
    (`_payload_context.py:203-211`). Per window:
    - `marginal` float64 (from that window's own calibration);
    - provisional ink = `marginal > 0.0`;
    - `counts, valid = context_neighbour_counts(page_cells, ink)`
      (`detect.py:280-315`): dense bounding-grid convolution with the
      3x3 ones kernel, centre 0, `mode="constant", cval=0`; a cell is
      `valid` iff all 8 neighbours are OBSERVED cells of this window.
      Duplicate page cells within one window are an error.
    - bin = count where valid, else −1 (`context_bins:318-340`).
      **Bin −1 = the mask protection**: window edge, support-mask edge,
      any unobserved neighbour. Bin −1 cells are excluded from BOTH fit
      populations and are NEVER corrected at apply.
14. Split: SEARCH = `known & ~parity & valid`, VALIDATION =
    `known & parity & valid` (same parity as §2b — reuse, don't re-cut).
15. Physical site ids ACROSS the region's windows: dense lexicographic
    `(page, y, x)` rank over the union (`_physical_cell_ids:119-162`).
    Duplicate observations of one physical site get weight
    `1/multiplicity` (`ContextObservations.weights`); a site with
    conflicting labels is an error; class support counts UNIQUE sites.
16. Floors, in order (unique-site counts): search total < 80 →
    `insufficient_search_support`; per-class < 20 →
    `search_class_starved`; validation total < 40 →
    `insufficient_validation_support`; per-class < 10 →
    `validation_class_starved`. Empty side → same cascade
    (`_partial_context_decision:70-116`, only the reason matters in
    holo3).
17. Fit (`_ordered_context_offsets:450-484`): for bin b = 0..8, block =
    that bin's (llr, label, weight) rows PLUS two prior
    pseudo-observations (llr 0.0, labels {False, True}, weight
    `CTX_BIN_PRIOR = 1.0` each). Block offset solves weighted
    `sum(w * sigmoid(llr + off)) = sum(w * label)` by bisection on
    `[-4, 4]` to `CTX_ROOT_TOL = 1e-12`, boundary and exact-zero
    shortcuts first (`_solve_offset:402-447`). THE CANONICAL SIGMOID is
    the two-branch form (`1/(1+exp(-x))` for x>=0, `exp(x)/(1+exp(x))`
    otherwise); `scipy.special.expit` is BANNED (1–3 ulp divergence on
    ~45% of negative inputs; v0.39 ruling 10.3). Generalized PAVA: merge
    the last two blocks while `offset[-2] < offset[-1]`, re-solving over
    the concatenation — offsets end non-increasing in bin index (more
    ink neighbours never push toward ink).
18. Adoption gate: weighted validation logloss
    (`_logloss:395-399` — `mean_w(logaddexp(0, ±llr))`) of
    `marginal + offsets[bin]` must be STRICTLY `<` baseline. Not
    adopted → the region's windows keep their exact marginal objects
    (identity, not a copy).
19. Apply on adoption, per window
    (`apply_context_offsets:547-562`):
    `out[valid] = clip(marginal[valid] + offsets[bin[valid]], -12.0,
    +12.0)`; bin −1 keeps the marginal untouched. This clip is the ONE
    place a bounded-LLR clamp is explicit. Store
    `printed_llr = float32(out)` and OVERWRITE `heldout_logloss` with
    the corrected window's unweighted heldout loss
    (`_binary_logloss` over `heldout & known`, no validity filter, no
    dedup — `_payload_context.py:284-295`); that number is the
    ownership rank key.

### 2d. Ownership freeze (per capture-lane)

20. `payload_cell_mask` (format 04: site-kind lookup < 0) restricts each
    accepted window to cargo cells (`payload.py:65-69`).
21. Candidates iterate in ascending `(heldout_logloss, patch_ordinal)`;
    the FIRST candidate observing a physical page cell owns it
    (`freeze_page_owners`, `payload_model.py:305-368`: per page,
    concatenate flattened `y*W+x` keys in candidate order; `np.unique`
    first-occurrence = owner; ascending keys = row-major cell order).
    Refused windows never compete. Deterministic and independent of
    worker count because the sort key is data, not arrival order.
22. Downstream (payload plugin, separate spec) slices owned cells into
    64-cell tiles and unions across captures — the multi-capture union
    happens AFTER ctx de-correlation, never on raw scores.

### 2e. Re-sample at a refined pose

When refine commits a revised pose for a window: re-run §2a–2b for the
SAME cell set at the new pose, REPLACE the window's evidence (single
generation — holo3 keeps only the latest per window), then the region's
ctx fit and the capture's freeze are stale and re-run at the next
frontier fixed point. Never let parent and revision rows coexist in one
ctx fit (F2a lesson: one physical site twice at half weight each = a
population that exists nowhere). Order within a fixed point: samples →
ctx refit → freeze → payload.

## 3. Copy-vs-rewrite

COPY-AND-STRIP (bit-exact numerics; drop docstrings, dataclass
validation, identity plumbing):

| What | Source | Fate |
|---|---|---|
| `_pava_nodes` stack-PAVA | src/holo/receive/detect.py:211-239 | COPY verbatim |
| `clamp_for` bound | detect.py:118-124 | COPY (diag only) |
| interp+logit LLR map | detect.py:161-170 | COPY (as free function) |
| `fit_calibration` gates/order | detect.py:242-277 | COPY logic, strip dataclasses |
| `context_neighbour_counts` | detect.py:280-315 | COPY (keep duplicate-cell check) |
| `context_bins` | detect.py:318-340 | COPY, strip float coercion |
| site weights / unique support | detect.py:381-392 | COPY |
| `_logloss` weighted | detect.py:395-399 | COPY |
| `_solve_offset` + canonical sigmoid | detect.py:402-447 | COPY verbatim |
| `_ordered_context_offsets` | detect.py:450-484 | COPY verbatim |
| `apply_context_offsets` | detect.py:547-562 | COPY verbatim |
| `fit_context` floors + strict gate | detect.py:565-626 | COPY logic, strip ContextFit validation |
| APERTURE/SPREAD constants | _payload_sampling.py:36-37 | COPY |
| `rotated_points` | _payload_sampling.py:56-72 | COPY |
| `_window_crop` numbers | _payload_sampling.py:197-221 | COPY (halo/aperture/median-fill) |
| `_sample_rows` | _payload_sampling.py:235-247 | COPY |
| `_region_pitch` | _payload_sampling.py:250-255 | COPY |
| `_scores` float32 discipline | _payload_sampling.py:323-338 | COPY verbatim |
| heldout-loss spelling | _payload_sampling.py:384-388 | COPY |
| `_physical_cell_ids` | _payload_context.py:119-162 | COPY (int64 fast path only; drop tuple fallback) |
| ctx pool/apply loop order | _payload_context.py:165-296 | COPY flow, strip ContextDecision records |
| `_binary_logloss` | _payload_context.py:59-67 | COPY |
| `payload_cell_mask` | src/holo/receive/payload.py:65-69 | COPY |
| freeze candidate order | payload.py:116-160 | COPY the sort key |
| `freeze_page_owners` | src/holo/receive/payload_model.py:305-368 | COPY |

REWRITE LEAN (behaviour only, none of the code): `_window_rows`
validation tower (holo3 windows arrive well-formed from place);
`_calibrate`'s WindowEvidence construction; `sample_and_calibrate`'s
region bookkeeping + `_parallel.ordered_map` (engine job model replaces
it); label-only routing (`_window_label_only`) if kept (§8 Q6).

REFERENCE ONLY (holo2; do not copy the pull machinery): holo2 solve/
detect.py is a character-identical carry of src/holo detect — use src/
holo as the single copy source. `ctx_apply.window_context_bins:176-203`
and the piece-halo machinery exist only because holo2 stores evidence
per TILE; holo3 stores per WINDOW, so window-scope binning is free —
DROP halos entirely. `place_shared.emit_placement:840-939` shows the
alternative raw `-means` score convention and `(y+x)%2==0` split (same
split, different score affine) — do NOT mix conventions; holo3 uses the
v1 `_scores`. `resample.resample_window:201-266` = the re-read flow
distilled in §2e. `pose_fit.median_radiometrics:674-686` (±8 clip, ×2,
tanh evidence) and `sample_segment:689-716` (coverage > 0.85) belong to
the PLACE/pose subsystem, not here.

## 4. Measured-channel invariants that MUST survive

- **Bounded LLR** (018.7): PAVA `pmin = 1/(n+2)` bounds `|llr| <=
  log(n+1)`; ctx apply clamps at ±12. An unbounded LLR once flipped a
  close — a single confident-wrong cell must never dominate a tile.
- **ctx bin −1 mask protection**: incomplete 8-neighbourhood is never
  fitted on and never corrected — the E023b re-derivation is what made
  ctx safe on fragments/support edges (e018 mask-aware-ctx negative).
- **Strict held-out adoption (`<`, never `<=`)**: the ctx arm
  self-disables where it cannot help; this is the defence against JPEG
  block artifacts (the legacy 16-context detector misfired on AltaLink
  scanner JPEG) and against coarse sampling.
- **ctx gain is SAMPLING-dependent — 3.5x at 16px/cell vs ~nil at
  8px/cell** (e018/pilot-first branch): a weak ctx result on a coarse
  footing is upstream lock/sampling, not a detector bug; do not chase
  detector work there.
- **Per-window calibration, per-region ctx, per-capture freeze scope**:
  pooling marginal labels across windows or ctx labels across regions is
  the leak the explicit identities exist to prevent (detect.py preamble).
- **Duplicate physical sites weigh ONE in ctx fits**; a label site never
  appears in both SEARCH and its own VALIDATION (parity disjointness).
- **Multi-scan law (F1∘F6)**: equal-weight combining LOSES to
  best-single on a global detector; union only after per-capture ctx
  de-correlation. Never raw + its decimation of one capture in a state.
- **Cell readout is where colour yield lives** (colour-uplift: xerox
  c2-cmy7's 18% cell error was DETECTOR-frozen, not print-frozen; the
  whole close came from readout, address ledger identical) — the K
  skeleton must keep the per-plane seams the colour head plugs into.
- **Day/density canary: nothing survives in receive.** The 004.0 c2
  whites canary is a print-side/characterize instrument. Receive's
  surviving observables are per-window `heldout_logloss`, calibration
  refusal counts by reason, and ctx adoption/reason per region — emit
  them as diag events; they never gate anything beyond their own
  registered thresholds above.

## 5. DROP (aggressively)

- All journal/resume/records machinery: `CalibrationRecord`,
  `LabelPool`, `HeldoutGate`, params-blob layout, content-addressed fit
  identities, `published_losses`/`member_digest` 52-bit digests,
  adopted-fit ranking (`ctx_apply.adopted_context_fit`), pool keys/
  scopes/providers, `COLLECTION_CERTIFIED` re-arm plumbing — holo3
  recomputes fits in-run; the live fit is the only fit.
- Piece halos (`pack_piece_observation`, `ring_masks`,
  `window_context_bins`, `apply_component_context`'s mask/bins
  plumbing): window-native evidence makes tile-boundary bin −1 a
  non-problem (v1 scope by construction; the 6.15%-vs-1.56% halo fix
  was a holo2-only artefact).
- `ContextDecision` durable records and `sha256_parts_le` decision ids —
  a diag event carries the same fields.
- The validation towers: `readonly_array`, `_identity`, `_binary`,
  `_site_ids` checks, every `__post_init__` in detect.py, `_window_rows`'
  eleven refusals, `PlacementModelError` taxonomy. Keep exactly two
  checks as behaviour (not guards): duplicate page cells within one
  window (feeds the conv), and conflicting labels at one site id (a
  format/GT bug that must not be averaged over) — both can live in the
  fit functions as they do now.
- `_parallel.ordered_map`, region_progress callbacks, terminal-address
  threading through the sampler (see §8 Q6), included_patch_ids
  filtering, `detector_profile` switching (holo3 always runs
  PAVA-then-ctx; "PAVA only" is ctx-not-adopted).
- holo2's `CtxFitWorker`/provider/descriptor/spend machinery whole
  (calibration.py:560-826), `resample.py`'s outcome vocabulary, and the
  F1 member-window-loss blob (`window_loss` sibling fallback) — holo3
  refits before it freezes, so the stale-loss problem cannot exist.
- The overflow tuple fallback in `_physical_cell_ids` (pragma-no-cover
  beyond any addressable geometry).

## 6. Data-structure needs (holo3/data.py)

Consumes: `Capture` (capture_id, dpi, plane set), `PlaneRaster` (u8 mmap,
crop_luma), `Window` (capture_id, plane, region_index, patch_ordinal
int, extent), `Pose` (page, rot_k, page_origin_yx, affine matrix +
origin float64, pitch_px), `FormatRow`/`SiteGeometry` (04), certificate
index (for terminal gating, Q6).

Produces:
- `WindowEvidence` (frozen): window key (capture_id, plane, region_index,
  patch_ordinal); page int; `page_cells_yx int32 (N,2)` (authoritative
  order); `scores float32 (N,)`; `reference_values int8 (N,)`;
  `knots float64 (K,)`, `probs float64 (K,)`, `n_search int`;
  `marginal_llr float32 (N,)`; `printed_llr float32 (N,)` (== marginal
  when ctx not adopted — may alias); `accepted bool`,
  `refusal_reason str`; `heldout_logloss float64 | None`;
  `ctx_adopted bool`. `raw_means float32` optional (diag only).
- `RegionCtx` (frozen, per capture-lane × region): offsets float64 (9,),
  adopted, reason, per-bin support int64 (9,)×2 (diag).
- `OwnedPageEvidence` (frozen): page, `cells_yx int32` row-major,
  `printed_llr float32`, `owner_window int32`, `owner_row int32`.
- Events: `window_calibrated` (accepted, reason, n_search, heldout_loss),
  `ctx_fitted` (region, adopted, reason, baseline/candidate loss),
  `owners_frozen` (cells, windows). Certificates minted downstream carry
  `source="k-readout"`-style plugin tags per the charter.

Stateful/shared, for the contract: (a) `region_pitch_px` — reduction
over the region's committed poses; freeze it into the window-job input.
(b) The ctx fit — a reduction over the region's complete accepted-window
set; run as one pure job per region over a snapshot taken at frontier
fixed point (merge discards the result if the set moved). (c) The freeze
— serial in the single-writer merge (cheap: one unique per page). (d)
`_site_lookup`-style site tables — build once at startup, read-only.
Everything else is a pure window job.

Scheduling function (frontier, no pull machinery): tier 1 = sample+
calibrate each newly-posed window (fires once per (window, pose);
tried-set floor = the pose identity — a (window, pose) pair never
re-samples); tier 2 = region ctx fit, armed when the region's accepted
set changed since its last fit, at most once per fixed-point sweep; tier
3 = re-sample at a revised pose (expensive; after cheaper tiers drain —
holo2 priced it 200 vs placement's base for the same reason); freeze runs
whenever any of the above committed, before payload attempts.

Arms API (dial-off; the colour closes predate them): `plane_fields`/
`color_field` need (i) a hook to displace `scan_points_yx` per plane
BEFORE step 4's map_coordinates (pose composed with a per-plane delta
field), and (ii) re-entry into §2e's replace-and-refit flow. Keep the
sampler's point-generation a separable function so an arm can wrap it
without touching the filter/score/PAVA chain. u-lane arms schedule on
the residue AFTER the core freeze (§6.2a schedule law) — they consume
`WindowEvidence` + `OwnedPageEvidence`, never reach inside.

## 7. Pitfalls / incidents

- **018.7 LLR honesty**: hand-computed LLRs once escaped the bound;
  every LLR must trace to PAVA-pmin or the ±12 ctx clamp.
- **e017 receiver cross-fit**: PAVA applied across windows — the decode
  failed before the (real) channel problem was even visible.
- **012.3 / never hand-roll seeded draws**: labels come from the format
  module's generators; a retyped draw (missing dtype=) forks the stream.
- **Canonical sigmoid**: expit diverges 1–3 ulp on negatives; bisection
  masks it numerically but it is a bit-level fork vs the pinned oracle.
- **np.interp equal-knot behaviour** (rightmost wins) is part of the
  pinned calibration output — do not "optimize" to searchsorted.
- **float32 weak-scalar re-widening**: a bare Python float in `_scores`
  silently promotes the whole chain to float64 (v0.39 found it; spell
  np.float32).
- **F2a double-count**: parent + revision rows in one ctx fit; holo3
  replaces evidence per window, never accumulates generations.
- **holo2 stale-fit incidents** (measured: 0/6 re-read windows ranked,
  fits that never saw live pieces): ordering ctx-refit BEFORE freeze
  within a fixed point is what makes the whole class unrepresentable.
- **e025 geometry artifacts**: a spike in `search_class_starved` /
  refusals usually means a mis-posed window, not a bad print — verify
  pose before writing channel conclusions.
- **Pooled-aperture bit-exactness**: the region's filter integers come
  from the pooled median pitch including label rows; computing it from
  payload rows only shifts the aperture by 1px on some regions and
  un-pins the scores.
- **Emission-refusal couples pose**: in holo2 a calibration-refused
  window commits no pose either (place_shared:886-895). holo3 must
  decide the same explicitly: a window that cannot calibrate contributes
  no evidence AND its pose earns no neighbour trust (place spec owns the
  consequence; flag it in the contract).
- **JPEG captures**: scanner JPEG erases <5-dot features and paints
  block boundaries the ctx conv reads as structure; the strict adoption
  gate is the only defence — never weaken it to `<=` or a tolerance.

## 8. Open questions for the contract author

1. Scores convention: v1 `_scores` float32 `(mid−means)/spread`
   (recommended — holo1 is the parity target and every acceptance close
   used it) vs holo2's raw `−means`. Affinely equivalent through PAVA
   but not bit-identical; pick one and pin it against the v1 oracle.
2. Parity spelling: `(131*y+17*x)&1` vs the equal `(y+x)&1` — one
   spelling in holo3/lib; which?
3. Per-window crop+filter (v1, bounded memory, refilters overlaps) vs
   per-region prepared plane (holo2, one filter, ~region-sized float32
   ×2). Plan says per-crop float32; confirm for 4800-dpi colour captures
   under the 64 GB / one-decode budget.
4. Ctx fit job placement: pure job over a region snapshot (merge
   discards on staleness) vs serial in the merge thread. Snapshot job
   recommended; needs a "region accepted-set version" int in data.py.
5. §2e replace semantics: confirm holo3 keeps ONLY the latest evidence
   per window (no generations, no quarantine ladder) and that refine's
   contradiction handling (quarantine subsystem in holo2) is entirely
   the refine/place plugins' problem — this subsystem sees only
   replace.
6. Pool law L2/L4 (label-only windows, terminal-address gating,
   `_window_label_only`): keep (saves owner rows and attempts on nearly
   -closed sheets, needs the certificate index threaded into this
   stage), or simplify to always-sample + drop done tiles at payload
   assembly? Simplification changes no bits of any close but changes
   late-run cost.
7. Heldout-loss spelling: v1 computes the marginal loss from
   probabilities and the ctx-corrected loss from LLRs (mathematically
   equal paths, different rounding). Unify on the LLR spelling, or keep
   both spellings to preserve exact rank-key ties?
8. Region identity for ctx pooling across scale lanes: v1 pools per
   (source sha, lane, region) — confirm holo3's lane/footing notion
   keys the ctx fit and that cross-lane pooling stays forbidden (the
   multi-state ctx matrix, which DOES pool across states, arrives as
   the colour-core/arm with its own spec).
9. Does the colour path reuse this spec's freeze
   (`freeze_page_owners` is already the shared K/colour one-owner
   core in v1) — i.e. should freeze live in holo3/lib rather than the
   K plugin?
