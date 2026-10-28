# 07 — Placement + addressing (plugins/place)

Distilled from holo2 `solve/{words,place_model,place_admission,place_job,
place_sched,place_slot,place_tiers,place_shared,place_subdivide,place_cold,
cold,placement,pose_audit(partial),plans,geometry,tilemap(partial)}.py` and
v1 `src/holo/receive/place.py` + `receive/placement/reference.py`.
Paths below are relative to `<checkout>`.

## 1. Purpose, inputs, outputs

Purpose: given a surveyed region (cell lattice + support mask) and per-window
fitted poses/samples (from the pose plugin), decide WHERE each observation
window sits on the printed page — page index, rot90 orientation, integer page
origin — through a ladder of routes (chain consult, address-word decode, wide
consult + regional affine, cold FFT correlation), admit only addresses that
clear the qualified E022 bars, refine+audit them, and commit poses. Drive the
whole thing with a cost-tiered frontier loop until no window offers work.

Inputs (all immutable snapshots at job build):
- `Window`: `extent_cells: tuple[int,int,int,int]` half-open (cy0,cx0,cy1,cx1)
  in the capture-cell lattice; `supported_cells: int`; `depth: int` (0 laid
  out, 1 corner child); `lane_depth: int` (0 = coarsest rung of its capture).
- `AddressPatch` (pose plugin's product for one window): `means: f64[H,W]`
  (cell-centre luma reads), `mask: bool[H,W]` (sampled/supported),
  `core: bool[H,W]` (mask eroded 2, fallback to mask if empty),
  `bits: u8[H,W]` = `means < midpoint`, `evidence: f32[H,W]` =
  `-tanh(clip((midpoint-means)/spread, -8, 8))` with `spread =
  max(mean(|means-midpoint|), 1e-6)`, zeroed outside mask (bounded evidence:
  ink ⇒ negative), `midpoint: float` = median of means under mask,
  `frame_pose: AffinePose` (window-cell → rung-pixel).
- Reference field (format side): per page `values: u8[cells_y, cells_x]`
  (expected pilot bit at every site cell), `sites: bool[cells_y, cells_x]`
  (page-invariant site mask = 100 word cells + filler/dust cells per tile).
  See §2.0 for the colour rule.
- Format row: `cells_yx`, `tiles_yx`, `page_domain: tuple[int,...]`,
  `seed`, `family_seed`, `plane`, `max_pages`.
- Committed poses (for consult/done), lattice seed, tile-certification state
  (for done gating).

Outputs (facts, merged single-writer):
- `Pose`: `{window_id, page: int, native_affine: tuple[float,...] (6 terms,
  page-cell-EDGE → native-pixel), route: str}` — one per placed window.
- `AcceptedPlacement` handed to calibrate/detect: `{page, rot_k,
  page_origin_yx, scores: f64[H,W] = -means (negated luma, window-local,
  unrotated), observed: bool[H,W] = audited core, sample}`.
- Lattice-seed proposal (even on refusal), window outcome events, counters.

## 2. Algorithm

### 2.0 Reference field (COLOUR-LOAD-BEARING — v1 is the authority)
`src/holo/receive/placement/reference.py:83-189`. Addressing runs ONCE per
capture on the LUMA plane, for K and colour alike. Per page: counters =
`page*tiles + tile_index`; word cells from `word_site_cells_yx(family_seed)`
(100 sites, quota-grid draw); K rows: filler cells
`site_cells_yx(family_seed, n_filler)`, filler values =
`keystream.bits(seed, DOMAIN_FILLER_VALUES, plane, page, y, x)`.
COLOUR rows (cmy7/cmy8): sites = `color_site_cells_yx(family_seed)` (100 word
+ 20 dust); word values use `pilots.word_values(seed, counters, PLANE_K)` —
the K-plane scramble, NOT the row's plane — and dust reference bit =
`ink_count(state) >= 2` with `ink_count = (0,1,1,2,1,2,2,3)[state]` (the
pinned 50/50 blind luma split under the ideal subtractive renderer). The page
cache key is `(seed, family_seed, plane, cells_yx, n_filler, page)`.

### 2.1 Window layout
`geometry.window_starts` (`holo2/.../geometry.py:241-297`):
`WINDOW_CELLS = 200`, `OVERLAP = 40`, `STEP = 160`,
`LAYOUT_MIN = 8` (axis shorter than 8 cells → no windows).
Starts along an axis of n cells: `()` if `n < 8`; `(0,)` if `n <= 200`; else
`range(0, n-200+1, 160)` plus, when the last start ≠ `n-200`, the FLUSH-SHIFTED
final start `n-200` (full-size window ending flush; never a clipped remainder).
Enumerate y-outer/x-inner; drop windows with zero supported cells (exact count
on the region support grid, NOT a `[::4,::4]` estimate); the window's durable
id is `(footing, region, extent)`; sort plans by id.

### 2.2 Support floors and domains (the admission algebra)
Constants (`place_admission.py:60-84`): `E022_SUPPORT_FLOOR_SITES = 30` (per
DISJOINT parity population), gates `search_true = 0.20`, `rival_decoy = 0.20`,
`minimum_gap = 0.08`, `validation_true = 0.24`, `ALPHA = 1e-3`,
`BER_ENVELOPE = 0.08`, `support_margin = 0`.
- `identifiability_support_floor(H, ber)` = `0` if H==1 else
  `int(math.ceil(log2(H) / (1 - h2(ber))))`, `h2(0)=0`. Exactly
  `int(math.ceil(...))` — never np.rint / int(np.ceil(...)).
- `min_support(H)` = `max(30, floor(H, 0.08) + 0)`, applied to EACH parity
  class separately.
- `hypothesis_count(frag_shape, page_shape, pages, allow_overhang=True)`
  (`place_admission.py:144-171`): sum over 4 rot90s of
  `(Hp+hf-1)*(Wp+wf-1)` (overhang) else `max(0,Hp-hf+1)*max(0,Wp-wf+1)`,
  times pages. A domain larger than declared REFUSES; never search a prefix.
- Route domains: chain/word score at `49 = (2*3+1)^2` per candidate; cold at
  `hypothesis_count((200,200), cells_yx, len(pages))` (cold min_support lands
  ≈54-55/parity on an A4 multi-page domain — the cold module comment's "55").
- `pass_budget` (`place_job.py:460-510`): a window's cumulative domain is
  `49 * max(1, len(tried) + len(offered))` and NOTHING else. Do NOT add the
  Stage-A word domain (withdrawn deviation: at 147,456-phase Stage A two spent
  stages crossed the 250,530 knee where min_support flips 30→31 and refused a
  30-site window v1 admits).

### 2.3 The parity-split scorer (ScoreMemo)
`pose_audit.py:235-368`. Frozen split `(131*y + 17*x) & 1` over ABSOLUTE page
coords; on a window slice it reduces to `((y+y0)&1 ^ (x+x0)&1) == parity`
(131, 17 both odd). `WHOLE_WORD_PARITY = 2` sentinel = all sites.
`parity_score(page, origin, rot_k, parity)`:
1. rot90 evidence(f32)/bits(u8)/mask(bool) by rot_k; clip fragment to page
   (`overlap_slices`); no overlap → `(1.0, 0, 0, -inf)`.
2. `selected = sites & mask (& parity_mask unless whole-word)`;
   `support = selected.sum()`; 0 → `(1.0, 0, 0, -inf)`.
3. `expected_sign = 1 - 2*expected_bits (f32)`; `corr = Σ sign*evidence`
   (float32 pairwise sums — do not promote to f64);
   `W = Σ|evidence|`; `mismatch = (W - corr) / (2W)` (1.0 if W==0);
   `errors = count(hard_bits != expected)`; `z = corr / sqrt(max(W, 1e-9))`
   (the one f64 step).
Memo: invocation-local dict keyed `(sample, page, oy, ox, rot_k%4, parity)`;
one memo per window pass; never module-global.
`candidate(...)` passes iff `search_support >= min_support AND
validation_support >= min_support AND search_mismatch < 0.20 AND
validation_mismatch < 0.24`.
Rival gate (`pose_audit.py:154-172`): `rival_mismatch > 0.20 AND
rival_mismatch - best_mismatch >= 0.08`; both WHOLE-WORD since v0.30 (the
d=27 floor: a cross-page alias can concentrate its difference codeword into
7/45 search-parity bits, measured family floor 0.156).

### 2.4 Bounded local search (chain kernel)
`pose_audit.py:395-445`. `radius = neighbor_radius_cells = 3` → 49 candidates
`(pred_y+dy, pred_x+dx)`, dy outer, dx inner; sort stable on
`(-soft_z, origin_y, origin_x)`; refuse `insufficient_support` if best z is
-inf; accept iff `best.passes AND Chebyshev(best.origin - predicted) <=
consistency_cells = 2`, else `local_validation_failed`.

### 2.5 Neighbour prediction (frame bridge)
`place_shared.py:252-407`, exact-rational, COPY:
- Pose convention: holo2 affines map page-cell EDGES → pixels; v1 maps cell
  CENTRES. Composition (`page_affine_terms`): `linear = M @ R_k.T`,
  `offset = pose_origin - linear @ (rot_translation + page_origin)
  - linear @ (0.5, 0.5)`; append rung→native rescale
  `out = s*(in + 1/2) - 1/2` per pixel axis via exact `Fraction` arithmetic,
  one float rounding per term (identity at s=1).
- Inverse (`predict_from_page_affine`): bring anchor affine down to this rung;
  recover rot_k = argmin over k of `||M_target @ R_k.T - A[:, :2]||_F` (exact:
  candidates 90° apart; a wrong pick just fails the gates); page-centre offset
  `A[:,2] + A[:,:2] @ (0.5,0.5)`; solve for page at local zero; subtract the
  rotation translation; `int(round(...))` half-to-even (exact-half offsets from
  rot90 transport land on it).
- Consult distance (`place_job.py:248-268`): centre-to-centre CELLS over
  `stride = 160`: adjacent window = 1.0, colocated coarser-rung donor = 0.0
  (what lets a donor outrank a stride-distant neighbour with no class label).

### 2.6 Stage A — the address-word sweep
`words.py:177-385`. Per orientation rot_k∈0..3 over the rotated bits/mask:
- Slot grid: all full 64-cell slots, `(extent-64)//64 + 1` per axis, row-major.
- Declared per-slot phase capacity `min(64, H-63) * min(64, W-63)` (uniform;
  over-declares trailing slots — union bound only needs declared ≥ attempted).
  `stage_a_hypotheses` = Σ over 4 rots of `n_slots * capacity`
  (200×200 → 9*4096*4 = 147,456; 70×70 → 7*7*4 = 196).
- Centre slot = argmin over slots of
  `|sy*64 + 64 - H/2| + |sx*64 + 64 - W/2|`, tie by slot tuple (float H/2!).
  Stage `"centre"` sweeps only it; `"rest"` the others; `"all"` everything.
- Gather one slot: phases (0..row_lim-1)×(0..col_lim-1) with
  `row_lim = min(64, H-base_y-63)`; indices
  `base + phase[:,None] + positions[None,:,axis]` where positions =
  `word_site_cells_yx(family_seed)` (100,2); reshape (n_phases, 100);
  origins via `repeat`/`tile` (row-major phase order).
- Decode: `decode_many(words ^ value_scramble_bits(seed, plane))` — plane is
  the ROW's plane for K, and PLANE_K for colour rows (§2.0). Use the batched
  BCH twin (lib/bch batch): this sweep measured ~72% of ALL receiver CPU;
  batched arm 1.63×, GIL-free fraction 0.95, bit-identical to the scalar.
- Per phase, in order: visibility floor — strict `visible < 90` (of 100)
  refuses THAT PHASE only (never a window-wide mask gate); then the three
  legality gates IN ORDER (`words.py:303-331`): (a) five-zero pads —
  `message[18:23].any()` refuses; (b) counter = 18 bits MSB-first;
  `(page, ty, tx) = spec.tile_address(counter)`; `page >= max_pages` refuses;
  (c) `errors > T = 13` refuses. `page_origin = (ty*64 - oy, tx*64 - ox)`.
- Global trial order: sort candidates by `(errors, slot_index, rot_k,
  phase_index)` — errors-first, deterministic value tie-breaks.
- Budget refusal FIRST: if `stage_a_hypotheses(shape) >
  max_word_hypotheses` return no candidates (`attempt_budget_exceeded`).
  `max_word_hypotheses` from the union bound: `p_word = ldexp(Σ_{i=0..13}
  C(100,i), 18-100)` (use math.ldexp, never division); require
  `H * p_word <= 1e-3`.

### 2.7 Word admission
`placement.py:101-255` (holo2 W5 shape). For each candidate in the global
order whose page ∈ page_domain: score via `memo.candidate(...,
pass_budget, route="word")`; first PASSING candidate is the winner; then the
whole-word rival bar: rival set = (other decoded candidates, deduped — same
page+rot within Chebyshev radius 3 of the winner is the SAME answer) ∪ (the
winner's own (origin, rot) on EVERY other declared page — the cross-page
alias population the word decode cannot see). Empty rival set →
`rival_gate(search_parity_mismatch, 1.0)`. Else `rival =
min(whole_word_mismatch over rivals)` vs winner's whole-word mismatch.
Rival-bar failure refuses the WINDOW's word pass (return None, not next
candidate). A failed candidate is one-way evidence; it never vetoes anything.
(v1 has no word rival bar — see open question Q1.)

### 2.8 Cold correlation
`cold.py:160-637` — THE STRICTEST EXACTNESS CONTRACT IN THE TREE; copy
whole, strip docstrings only. Preserved verbatim (each proven load-bearing):
padded shape `next_fast_len(n+m-1, True)` per axis + `full[kh-1:h, kw-1:w]`
valid slice (bit-identical to `scipy.signal.fftconvolve`); degenerate
<2-cell-axis fallback to direct fftconvolve (`kernel_rfft is None`);
`np.rint(...).astype(np.int32)` for search support; z map =
`soft_corr / sqrt(weight)` under errstate with -inf fill on ineligible;
strict `>` winner replacement (first-on-tie in caller page order then
orientation order); kernel `(observed*keep)[::-1,::-1]`; absolute search
parity `parity_mask(sites.shape, (0,0), 0)`; page-invariant site/weight/
eligibility maps hoisted out of the page loop; per-invocation transform cache
keyed `(page, pad_y, pad_x, fshape)`; the page-invariance `np.array_equal`
check on every page's sites (raise on mismatch). Flow: geometries per rot
(pad = shape-1 when overhang; else skip oversize rot), `eligible =
(search_support >= min_support) & (weight > 0)`; RESULT-EXACT EARLY-OUT: if
no orientation has any eligible origin, refuse `insufficient_support` before
any page FFT (measured: 70-cell children each paid a full 312-page sweep
before dying at the 55/parity floor). Sweep pages sequentially; keep one
top per (page, rot) map and only the running winner's z map; second peak =
argmax after blanking winner's ±3-cell (radius=neighbor_radius_cells)
neighbourhood in place; rival set = losing map tops + winner map's second
peak, deduped by identity and by same-page/rot Chebyshev ≤ 3; score winner
via memo.candidate(route="correlation"), runners as "correlation_runner_up";
winner must pass (`winner_failed_heldout_gate` else); whole-word decoy =
min whole-word mismatch over runners (1.0 if none, best_whole = search
mismatch then); `rival_gate` decides. Page-domain validation: integers only,
order-preserving dedupe, non-empty. No fft workers knob; kernels serial.

### 2.9 Address → placement (shared tail for every route)
`place_shared.py:558-604`. On an accepted `(page, rot_k, origin)`:
1. Bounded pose refinement (pose plugin's kernel, `pose_audit.py:668-780`):
   grid angle ±0.15° step 0.05 (7) × phase ±0.25 cells step 0.0625 (9×9);
   needs ≥60 sites total, ≥20 per parity; baseline (0,0,0) evaluated
   separately (grid "zero" is 2.78e-17); adopt only if heldout mismatch ≤
   baseline + 0.005; adopt refined sample only if `mask.sum() >= 30`;
   re-derive the address core (erode 2).
2. Straddle audit (`pose_audit.py:785-887`): binomial-impurity change-point
   over the audited correspondence set; axis schedule `(0,1,0,1)`; per split
   min `n_lo*p_lo*(1-p_lo) + n_hi*p_hi*(1-p_hi)`, strict `<` first-wins,
   skip cuts on tied coordinates, `audit_min_sites = 15` on each side; cut a
   side only when `bad_rate > 0.35 AND kept_rate < 0.20`; edge =
   `int(np.ceil(cut))`; sort with `np.argsort(kind="stable")`. Refuse when
   either parity population of the kept set < `min_support` or residual error
   rate > `0.25`.
3. Emit `AcceptedPlacement`: `scores = -means` (negated luma — the polarity
   PAVA and the tile chain require), `observed = audited core`,
   `affine = page_affine_terms(pose, shape, rot_k, origin, frame)`.
Audit refusal → `straddle_audit_refused` (subdivides; v1 :1173).

### 2.10 The unified per-window job (word/chain/wide/cold = ONE job)
`place_job.py:515-845`, restated for holo3's frontier loop. A claimed window
runs one pass with inputs `(wide: bool, stage: centre|rest|None,
cold: live|rest|None, tried: frozenset[str])`:
1. DONE GATE first, before any pixel: retire `done_covered` if every
   SUPPORTED cell of the extent is already done (§2.12).
2. Already placed → retire.

**AMENDED 2026-08-31 — steps 1 and 2 are not steps of the pass.** Both
moved up to the scheduler door (`place_sched.place_retire_cause`, which
`engine._fill` consults before `descriptor.prepare`), so a done or placed
window is retired before its job is ever built and the pass never sees
one. The copy that stayed inside `run_window_pass` was therefore
UNREACHABLE, and its zero firings across 1.9 M events of four real-sheet
runs were read as a dead gate. It is deleted; `WindowPass` carries no
done input. See §2.12's amendment for the evidence that the door itself
is alive.
3. `seeds = consult(...) minus tried`. Consult = one Seed per visible anchor
   window's LIVE pose (page ∈ domain), sorted by `(distance, candidate_id,
   affine)` — values, never arrival order — truncated to `CONSULT_KEEP = 8`
   (ring reach: the 8 lattice neighbours by START-INDEX adjacency on this
   footing — computed on the region's window-start lattice, NOT on surviving
   plans — plus coarser-rung windows containing this extent). Wide pass:
   every window of the region at any distance, keep nearest
   `WIDE_ANCHORS = 8`, plus the REGIONAL SEED: least-squares 6-term affine
   over all committed poses of the region's majority page (ties → lowest
   page), each anchor contributing its four extent-corner (page-cell,
   native-px) correspondences through its live pose inverse; require ≥2
   windows, lstsq rank 3, finite terms; `candidate_id =
   f"regional-affine/{terms}"`, distance = inf. Seed candidate_id = the
   source pose id (one steer per anchor: its LIVE pose only — two poses of
   one anchor would double-weight it and tie-break unpredictably).
4. `will_word = (not seeds) and stage is not None`.
   `cold_pages = pages(flavour) minus {p: "cold-page/p" in tried}` where
   live = pages holding a committed pose ∩ domain, rest = domain − live
   (partition; dedup per PAGE across flavours because live grows).
5. Nothing at all to do → outcome `nothing_to_try` (a spent ping; fall to
   next tier) or `cold_refused_<flavour>` when this WAS a cold claim.
6. `budget = pass_budget(local_49, tried, offered)`; sample the window (pose
   plugin: fit, sample, propose lattice seed EVEN ON REFUSAL, refuse
   `pose_refused` (no charge, seed ping can revive) or
   `insufficient_support` if `mask.sum() < 30`).
7. CHAIN: for each seed nearest-first, predict `(rot_k, origin)` via §2.5 and
   run the 49-search; stop at first acceptance. ALL offered seeds are charged
   to tried whether reached or not (conservative). One ScoreMemo per pass.
8. Else WORD (only when the consult offered NOTHING — the ladder's word
   clause): §2.6/§2.7 at the given stage; charge the stage.
9. Else COLD (only when claimed as cold): §2.8 over cold_pages; charge the
   page ids; accepted → route "correlation".
10. Any address → §2.9; audit refusal does NOT retire (the window re-arms and
    may still climb to an unspent word stage — deliberate holo2 deviation:
    REST becomes reachable after a failed centre acceptance).
11. Acceptance → commit pose + placement product; failure writes NOTHING
    durable (no spend rows, no scheduling state).
Refusal vocabulary (window outcomes the scheduler reads):
`pose_refused`, `insufficient_support`, `consult_refused`, `wide_refused`,
`no_word_candidate_{centre|rest}`, `straddle_audit_refused`,
`cold_refused_{cold_live|cold_rest}`, `nothing_to_try`, `accepted`.
Every one of them is a REFUSAL that leaves the window live. Leaving the
frontier is not an outcome of the pass: it is a `WindowRetired` carrying
the door's `cause` — `placed`, `exhausted` or `done_covered`
(amended 2026-08-31; `done_covered` left the settle vocabulary with the
unreachable pass-side copy).

### 2.11 Scheduling FUNCTION (frontier loop — no pull machinery)
Per-window in-memory state: `{tried: set[str], centre_spent, rest_spent,
wide_spent, cold_armed, cold_live_spent, cold_rest_spent, subdivided,
children, cold_parked, depth, lane_depth, offered: float|None, ordinal}`.
Tier of a window (first match; None = dormant):
`offered is not None → ring` | `not centre_spent → word_centre` |
`not rest_spent → word_rest` | `not wide_spent → wide` |
`cold_armed and flavour non-empty and unspent → cold_live then cold_rest`.
Price = `tier_cost + rung_term * lane_depth + (5 if depth else 0)` with
costs ring 40, word_centre 60, word_rest 80, wide 120, cold_live 140,
cold_rest 150; rung_term = 2 for ordinary tiers (a tie-break: coarse before
fine WITHIN a tier), 20 for the cold pair (a real price: rest(d)=150+20d <
live(d+1)=160+20d, so a rung's two colds drain before the next rung's).
Priority within the frontier: `(price, offered_distance (inf if none),
ordinal)` — Dijkstra-flavoured growth from accepted placements along the
most confident edges, round-robin tie-break. GATING: wide and both colds are
gated — offer them only when nothing cheaper is ready anywhere AND payload
work has drained (payload prices below ALL placement tiers; measured
amendment: interleaving payload above wide starved 1,287 armed payload
workers behind a never-drying placement domain).
After each ACCEPTED pose: offer its distance to the 8 ring neighbours and to
finer-rung windows its extent contains (`offered = min(offered, d)`); after a
lattice-seed improvement: re-offer every dormant window of that (footing,
region). TRIED-SET FLOOR (ruling Q1): fires are deterministic, so repeating
an identical hypothesis on identical pixels is the same trial — dedup by
candidate id; the budget prices `49 × distinct candidates ever offered`, the
derived floor only grows, and nothing is ever truncated to fit.
Subdivision: on `pose_refused` or `straddle_audit_refused` immediately
(v1 :1244/:1173); every other exhausted window arms its cold pair FIRST and
subdivides only on the cold refusal (v1 :1495 order). `insufficient_support`
NEVER subdivides (less paper cannot help). A window whose own fit refused
does not arm cold (no patch to correlate; only a better seed revives it).
Children (`pose_fit.py:746-785`): at most one level; side =
`max(70, min(h,w)//2)`; refuse if side ≥ min(h,w); corners TL,TR,BL,BR;
drop unsupported corners; children run the full ladder incl. cold at +5.
Parent afterlife: when all children exited and none `placed`/`done_covered`
→ arm the parent's cold on its FULL extent (correlation wants area).
(AMENDED 2026-08-31: the built check is `placed` alone, because
`done_covered` is no longer a child OUTCOME — a done child leaves through
the scheduler door instead, and counts as settled. The parent it re-arms
is caught by its own door consult at the next pop, so this costs one
wasted repush and never a wasted pass. Left as measured behaviour, not
changed: tightening it is a scheduling change owing its own gates.)
Cold flavour with an empty page set: skipped costlessly, never marked spent
(it may fill later); a flavour offered but fully deduped by tried IS spent.
Termination: set grows only by subdivision (one generation, ≥70-cell floor);
every member's ladder is finite.

### 2.12 Certified-done gating
`tilemap.py:693-747, 750-823`. A tile is done when EVERY stream of its
(page, ty, tx) work key is certified. Done projection per region: for each
posed window's LIVE pose (never the union of generations — measured
over-claim +860/+588 cells on the two real sheets), map the extent's lattice
cell CENTRES through the inverted native affine → page cells → `floor //64`
tiles; mark done where the tile grid is fully certified AND the cell is
supported. `covers(extent)` = extent has ≥1 supported cell AND all supported
cells done. Memoise on `(n_poses, n_certified)` — both monotone. Asked at
admission and again first thing in every fire.

**AMENDED 2026-08-31 — one door, and it is alive.** Asked ONCE per pop,
at `engine._fill`'s `descriptor.retire` consult, which runs before
`prepare`; the second ask inside the pass was unreachable and is gone
(§2.10). The door is now legible: `WindowRetired.cause` names the clause
(`placed` / `exhausted` / `done_covered`), so a run's suppressions can be
counted from its own event stream.

Measured, sheet I 2026-08-31 (`measure/donegeo_realstate.py`, read-only
over the archived snapshots and events): on the resume-2 run the gate
suppressed **240 of the 302 windows the input state left unplaced**, none
of which fired a single job, and the re-derived verdict agreed with the
run's behaviour on all 302 in both directions (0 false, 0 missed); the
resume-3 run reproduces it exactly. All 62 survivors were blocked by the
same 16 tiles still open in some stream (C 3, Y 14): every one carries at
least one open cell, median 63, range 3 to 3,875, inside extents of
9,387 to 40,000 supported cells — one open cell is enough, and for half
of them that is what it came down to. The AND across streams is what
binds, exactly as specified.

WHERE IT CANNOT BITE, measured on the same day. On a run that starts
cold, placement finishes before certification starts: **97.6% of the
seven-capture sheet-H stack's 9,866 place cpu-s and 98.8% of the
four-capture run's 4,551 were spent while ZERO tiles were done in all
three streams** (and while at most ~100 of 1,961 were certified in ANY
single stream). No sharpening of this gate — per-stream, per-lane or
otherwise — could have touched that bill; there was nothing certified to
gate on. The leftover windows those runs end with sit on ground the
capture had already POSED, not ground already CERTIFIED: a
placement-coverage gate, which is a different mechanism and a design
ruling, not this one. Its opportunity is measured for the record —
5,031 cpu-s (51% of place) on sheet-H max-stack, 2,096 (46%) on
sheet-H mixed, 722 (91%) on sheet-I first, 395 (47%) on sheet-I
resume-3 — as a naive upper bound only: a suppressed coarse-lane pose
may be the seed a neighbour needed.

## 3. Copy vs rewrite

| Source (file:lines) | Verdict |
|---|---|
| `holo2/src/holo2/solve/cold.py:160-637` (geometries, signed field, page map, sweep, correlate_patch) | COPY-AND-STRIP — bit-exact FFT contract |
| `holo2/src/holo2/solve/words.py:177-385` (slot geometry, gather, gates, sweep, sort) | COPY-AND-STRIP — format-law word decode |
| `holo2/src/holo2/solve/pose_audit.py:154-183` (rival_gate, WHOLE_WORD_PARITY), `:235-252` (parities), `:257-368` (ScoreMemo), `:395-445` (local_search), `:450-486` (fragment_reference_sites), `:785-887` (audit) | COPY-AND-STRIP — the decision kernel |
| `holo2/src/holo2/solve/pose_audit.py:571-780` (batched refine + refine_patch_pose) | COPY-AND-STRIP (batched arm only; scalar oracle lives in _distill/verify) — belongs to the pose plugin but placement's tail calls it |
| `holo2/src/holo2/solve/place_shared.py:252-407` (frame bridge incl. Fraction rescale), `:412-417` (address_core), `:558-604` (place_addressed) | COPY-AND-STRIP — exact-rational + half-cell convention |
| `holo2/src/holo2/solve/place_admission.py:122-171` (identifiability floor, hypothesis_count) + constants `:60-84` | COPY values/arithmetic; drop table/validators |
| `holo2/src/holo2/solve/geometry.py:241-316` (window_starts, tile_of_cell, contains_rect) | COPY-AND-STRIP — flush-shift ruling |
| `holo2/src/holo2/solve/plans.py:127-217` + `pose_fit.py:746-785` (layout, children) | REWRITE LEAN keeping enumeration order + zero-support drop |
| `holo2/src/holo2/solve/placement.py:101-255` (decode_word_address, _rivals, _rival_bar) | COPY-AND-STRIP (pending Q1) |
| `holo2/src/holo2/solve/place_job.py:248-268` (hint_distance), `:375-455` (regional_seed), `:460-510` (pass_budget) | COPY arithmetic, strip |
| `holo2/src/holo2/solve/place_job.py:515-845` (WindowJob ladder) | REWRITE LEAN as one function (§2.10) |
| `holo2/src/holo2/solve/place_sched.py`, `place_slot.py`, `place_subdivide.py` | REWRITE LEAN as §2.11 (keep tier order/prices/gating; drop flag protocol, heap tombstones, pings, resample tier) |
| `holo2/src/holo2/solve/place_tiers.py:79-240` | COPY the numbers as module constants |
| `holo2/src/holo2/solve/place_cold.py:97-133` (live/rest partition, cold_tried_id) | REWRITE LEAN (~20 lines); drop leases/keys |
| `holo2/src/holo2/solve/tilemap.py:693-747,750-823` (tile_done, done grid, covers, project_done) | COPY arithmetic, rewrite around holo3 data |
| `src/holo/receive/placement/reference.py:83-189` (V1ReferenceField page gen) | COPY-AND-STRIP — the colour luma reference rule |
| `src/holo/receive/place.py` (survey drive, hints, mopup, park) | DO NOT PORT — superseded by §2.10/2.11; keep only as ordering authority (:1244/:1173/:1495) |
| `holo2/.../words.py:457-547` (known_position_words) | DROP (quarantine consumer; see §5) |

## 4. Measured-channel invariants that MUST survive
- d=27 whole-word rival evaluation (decoy > 0.20, gap ≥ 0.08 on ALL sites):
  the parity split can hide a cross-page alias in 7/45 search bits (0.156
  family floor); whole-word restores the code's algebra.
- Stage A per-phase `< 90/100` visibility floor, never a window-wide mask
  gate: one damaged corner must not refuse a window with a pristine slot.
- 30 sites per DISJOINT parity population + e026 `ceil(log2 H/(1-h2(BER)))`
  floor growing with the cumulative domain: the identifiability law measured
  in e026.2; never truncate a domain to pass.
- Complete-domain discipline: an invocation whose domain exceeds its
  declaration refuses rather than searching a prefix (E022-v2 qualification).
- Cold FFT bit-exactness vs `fftconvolve` (padding, slicing, rint, -inf
  fill, strict-> tie rule): the cached-transform path was qualified only as
  bit-identical; any drift voids the zero-wrong record.
- Cold eligibility early-out is RESULT-exact (eligibility page-invariant);
  without it subdivision children pay full multi-page sweeps (measured).
- Flush-shifted window lattice: clipped remainders wasted tiles (measured on
  451/545-cell axes); the last window is full-size ending flush.
- `insufficient_support` never subdivides; `pose_refused` and
  `straddle_audit_refused` subdivide immediately; everything else correlates
  before quartering (v1's three call sites, restored at holo2 W4).
- Frontier order = nearest accepted pose first: hygroexpansion ~0.3% ⇒
  ~0.5 cells per 160-cell stride — chain predictions only survive the ±2-cell
  consistency gate short-range.
- Stage-A domain never priced into the placement support floor (the 30→31
  knee refused a v1-admitted window).
- Gated dear tiers (wide/cold) behind global dryness: measured payload
  starvation (1,287 armed workers, 0 tiles after 431 fires) forced payload
  below all placement tiers; cold-on-everything before payload drains burns
  the session.
- Done projection through the LIVE pose only (union over-claimed +860/+588
  unspent cells); done ≠ placed (windows overlap) — the done gate is what
  retires an unplaced window in a recovered area.
- One steer per anchor window; all orderings on VALUES (distance, id,
  affine / errors, slot, rot, phase) so worker count and arrival order can
  never move a result.
- float32 pairwise sums in the scorer, f64 only at z's sqrt; `int(round())`
  half-to-even in prediction; `int(math.ceil())` in the floor; stable sorts.

## 5. DROP (aggressively)
- ALL pull-model machinery: ready bits, in-flight flags, ping/wake protocol,
  heap tombstones, `_seed_ping`, ColdOffer re-enqueue sweeps, ordinals-as-
  wakes. holo3's frontier loop just recomputes tier+priority per iteration.
- Resume/journal/replay: markers, WindowRecord/WindowStatus durable outcomes,
  `settled_placed` replay path, `_placed_pose`/`_reviewed` re-read memory,
  EXIT ledgers. Run dir is disposable.
- The resample/re-read tier (F2a) and RF1 coupling — refine is a plugin;
  if it revises poses it owes its own re-read (Q4).
- Quarantine + contradiction: `word_verdict`, `known_position_words`,
  `PilotObservation` harvest, born-quarantined poses, never-return filters
  (measured: 1,780 known-position reads, 0 conflicts across both real
  sheets). Keep only if Q6 says otherwise.
- Reading sets / `working_footing_id` policy plumbing (`reading_set_places`);
  holo3 fixes the ladder in the contract (Q3).
- Leases, ResourceKeys, transactions, `pixel_work_is_attachable`, M12
  decline-and-sleep, ProtocolViolation taxonomy, ProgressSink heartbeats
  (keep plain counters + one event per window outcome for diag).
- `PlacementDomainEnvelope` (receiver-wide domain union), qualification-id
  strings, AdmissionDatum/OR9 table, dataclass validators (`_ratio`,
  `_int_at_least`, post_inits), `AttemptBudget`/`PlacementGate` as classes —
  constants + two pure functions suffice.
- v1 hint records (`PlacementHint`, lower-hint ranking `place.py:147-182`,
  accepted/runner ledgers, `promoted_continuation_hints`), park/mopup
  phases, `cold_first_max_pages` inversion (priced tiers subsume it, Q7),
  component bookkeeping, WindowAttempt/AddressResult shapes, all `_emit`
  detail plumbing.
- The scalar BCH sweep and scalar refine arms (oracles live as verify
  scripts under `_distill/verify/`, never in holo3/).

## 6. holo3/data.py needs (plane-native)
Consumes: `Capture`/`PlaneRaster` (per-plane u8 mmap; placement reads the
LUMA plane), `Region` (`region_id`, cell lattice: origin, pitch, shape_cells,
`support: bool[cells]`), `Window` (id = (footing, region, extent_cells);
extent, supported_cells, depth, lane_depth), pose-plugin products
(`AddressPatch` fields as §1), `FormatRow` (cells_yx, tiles_yx, page_domain,
seed, family_seed, plane, max_pages, stream_ids), tile certification state
(per (page, ty, tx): set of certified streams).
Produces: `Pose {window_id, page:int, native_affine:tuple[float,...]x6
(page-cell-edge→native-px), route:str}`; `AcceptedPlacement {page:int,
rot_k:int, page_origin_yx:(int,int), scores:f64[H,W], observed:bool[H,W],
sample:ref}` (calibrate/detect consume; certificates minted downstream carry
`source="place"`); `LatticeSeed {footing, region, rows, support_cells}` with
the merge law "better-supported source wins"; events
`WindowOutcome {window_id, outcome:str, route:str|None, tier:str,
hypotheses:int}` + per-plugin counters.
Threading: a window pass is a pure job over `(patch, seeds, cold_pages,
tried, budget, reference)` — snapshot ALL of it at claim. Shared/stateful
things and their holo3 treatment: ScoreMemo → job-local; cold PageTransforms
→ job-local (per invocation, as carried); reference-field page cache →
per-worker (deterministic regeneration; or precompute the domain's pages
once); live_pages + done projection → recompute in the merge thread, memoised
on (pose count, cert count); the LATTICE SEED is the one read-modify-write —
make it a merge-side reduction (proposals ride results; single writer applies
supersedes), which dissolves the race holo2 needed key-binding for (measured:
4-worker CommitRefusal crash before the bind). Scheduler state (tried sets,
stage flags) is main-thread-only; fold `tried_now`/`stage_spent`/
`cold_spent`/`wide_spent` from the returned job.

## 7. Pitfalls / incidents
- Half-cell convention fork: holo2 affines map cell EDGES, v1 cell CENTRES;
  the `-A@(0.5,0.5)` term and its inverse are the difference between working
  and a silent half-cell error everywhere downstream.
- Rung rescale must be exact-rational (`Fraction`): `out = s*(in+1/2)-1/2`;
  float-composed scales drift across a page.
- `np.rot90` sense is load-bearing everywhere (gather, scorer, emission);
  page orientation = `np.rot90(x, rot_k)`, inversion via index arrays
  (`fragment_reference_sites`) preserving correspondence order.
- The word-sweep budget arithmetic uses `math.ldexp` (2^-82 underflows naive
  division orderings); sphere via `math.comb`.
- Stage A trailing slots physically admit fewer phases than declared — the
  gather uses `_slot_phase_shape`, the declaration `_slot_phase_capacity`;
  swapping them either reads out of bounds or under-declares.
- Ring neighbours from the START-INDEX lattice, not surviving plans: deriving
  adjacency from existing plans silently promotes two-steps-away windows
  where one was dropped; edge rings are asymmetric (flush shift) by design.
- `regional_seed`: one page per fit (poses of different pages pool to a
  correspondence that exists nowhere); one live pose per anchor (a revised
  anchor once contributed corners twice, double-weighting the lstsq).
- Cold winner map second-peak: blank in place ONLY because the map is never
  consulted afterwards; the transient winner_z=None case (superseded before
  a page's tops are exhausted) must be reproduced.
- Straddle-audit `int(np.ceil(cut))` and `argsort(kind="stable")`: rint or
  unstable sort moves cut edges on real sheets.
- Audit refusal must NOT retire the window (holo2 deliberately lets it climb
  to word-rest); but it DOES subdivide when the window then goes dormant.
- The done gate can slightly over/under-claim near tile boundaries after a
  pose revision (~3 cells measured) — `done_covered` retirement is permanent;
  acceptable, documented, do not "fix" by unioning generations.
- e022/e026 gate-constants-vs-construction-floors: a should-pass control
  failing a pre-registered bar means the gate is broken, not the data —
  never patch bars to fit (memory: gate-constants-vs-construction-floors).
- Channel gate ≠ receiver (e031/e032): discovery tier numbers must never
  gate placement decisions; the ordering even INVERTED on e032.
- Don't measure known quantities: predictions come from format truth +
  committed poses, never from re-fitted page pitch (5.92-vs-6.00 incident).

## 8. Open questions for the contract author
1. Word-route rival bar: v1 (the colour-close authority) accepts the first
   candidate passing the coupled parity gates; holo2 W5 adds the whole-word
   rival bar + cross-page rival set. Recommend holo2's (restores d=27; only
   binds on multi-page domains) — but acceptance sheets 3-7 closed under
   v1's rule; confirm no yield regression on the declared page domains used.
2. Confirm the repo-wide pose affine convention = holo2 cell-edge native-
   frame (done projection and tile map in this spec assume it).
3. Footing ladder: does holo3 run the full multi-rung cascade (lane_depth
   pricing, donor consult, rung rescale) from day one, or single decimated
   footing per capture first? Affects §2.5/§2.11 scope; holo1's colour
   closes used the scale-space cascade.
4. Who owes the re-read after a pose revision if the refine plugin adopts
   one (dropped F2a tier)? If refine never revises committed poses in holo3,
   nothing is owed.
5. Colour addressing: confirm holo3 keeps v1's one-luma-addressing-pass
   (PLANE_K word values, ink_count>=2 dust reference) with poses shared by
   all plane views downstream — vs any per-plane addressing ambition
   (INDEPENDENT-PLANES is an ARM; its API need: arms may ask for per-plane
   pose DELTAS on top of the shared pose, so `Pose` should be referenceable
   per plane without forking the placement record).
6. Drop quarantine/contradiction entirely (0/1,780 measured)? If a vestige
   is wanted, the cheapest honest form is a diag-only counter, not a gate.
7. Confirm dropping v1's `cold_first_max_pages` small-domain inversion
   (priced tiers already run word_rest(80) before cold(140+)).
8. Page domain for each acceptance target (single-page volumes collapse the
   cold domain and empty the cross-page rival set): confirm decodes declare
   the true domain from the format row, not `--page` operator flags.
9. plane_fields/color_field ARMs: they consume committed poses + certified
   tiles and (when dialed on) supply per-cell local affines at SAMPLING time
   — placement itself needs no hook beyond exposing `Pose` + the audited
   observed mask; confirm the arm API attaches at detect/refine, not here.
