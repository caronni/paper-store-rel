# FAMILIES-AUDIT — scheduling data families, read-only audit for D6

Read-only audit of the descriptor engine as it stands at `c7142f3`
(`holo3/engine.py`, `engine_types.py`, every plugin descriptor + its
`reads`/`eligible`/`retire`/`tier`/`premium`/`prepare`). Input to the D6
review; nothing here is ratified and no production file was touched.

Every claim is tagged **[V]** verified by reading the code named, or
**[I]** inferred (arithmetic, or a consequence I did not run).

**Cardinality provenance.** Numbers come from the six parity harvests in
`_distill/verify/parity/run-{2..7}` (`report.json` + `events.jsonl`).
Those runs are dated 2026-08-28 22:47 and PREDATE the descriptor engine
(`29c34c2`, 2026-08-29 02:09), so their *plugin job counts* are the old
coarse-plugin accounting, not per-row descriptor counts. Domain
cardinality (captures, levels, regions, windows, poses, tiles,
certificates) is engine-independent and is used as such. **[V]**

Reference sheet throughout = e029 (run-2): 1 capture, 1 region, **4
levels**, 1 page, 53x37 = **1,961 tiles**, 1 stream, support 8,030,805
cells, **1,325** place workers fired, **1,319** poses, **1,222**
calibrate subjects, **1,940** certificates, 13,834 jobs. Sheet I
(run-7): 3 captures, 3 regions, **3 levels**, 1,961 tiles x **3
streams** = 5,883 addresses, **3,396** poses, **5,326** certificates,
243,240 jobs. **[V]**

---

## 1. THE KEY FAMILY TABLE

`FactKey` vocabulary is closed at 8 families (`engine_types.KEY_KINDS`).
"Touched by" = folds in `engine.py` that return the key; "subscribed by"
= `reads` functions that emit it. **[V]** for the whole table.

| family | store cells it stands for | touched by (condition) | subscribed by (`reads`) | cardinality e029 / sheet I |
|---|---|---|---|---|
| `("window", wid)` | `_windows`, `_ordinal_wid` | `_fold_window` (first sight only) | **NOBODY** | 1,325 / ~3,400 |
| `("pose", wid)` | `_placements`, `_pose_gen`, `_page_cells` | `_fold_placement` (always), `_fold_refine_outcome` (adopted) | place (ring neighbours, all levels), calibrate (own), refine (own), refine.color (own) | 1,319 / 3,396 |
| `("evidence", wid)` | `_evidence` | `_fold_evidence` (scores/printed_llr/accepted/ctx_adopted changed) | refine (own), revisit (own, placed only) | 1,222 / n-a (colour) |
| `("region", cid, li, ri)` | `_region_pitch`, `_region_ctx` | `_fold_placement` (pooled pitch *value* changed), `_fold_evidence` (`from_ctx=False`), `_fold_ctx_outcome` (offsets/adopted/reason changed) | calibrate, ctx, revisit | **4** / **9** |
| `("lattice_seed", cid, li, ri)` | `_lattice_seeds` | `_fold_lattice_seed` (better support, or tie broken on `rows.tobytes()`) | place (own region) | 4 / 9 |
| `("lane", cid, li, page)` | *(no cell of its own)* | `_fold_placement`, `_fold_evidence`, `_fold_color_row`, **`_fold_certificate` (fans to every lane on the page)** | tiles.freeze (all pages), color (own), revisit (unplaced, all pages) | **4** / **9** |
| `("tile", page, ty, tx)` | `_certificates`, `_equations` | `_fold_certificate` (new address) | refine (reach at birth), refine.color (reach at birth), revisit (reach at birth, placed) | 1,961 / 1,961 |
| `("tile_evidence", page, ty, tx, cid, li)` | `_tile_evidence` (cell key also carries `arm`) | `_fold_tile_evidence` (epoch advanced), `_fold_attempt` (retry armed -> touches each component) | tiles.scan (own), tiles.union (all captures), tiles.retry (source) | <=7,844 / <=17,649 |

### Flags

**K1. `("window", wid)` is touched by nobody's subscriber — dead key.**
`_fold_window` returns it; no `reads` function in any plugin mentions
`KEY_WINDOW` (grep over `plugins/*.py` confirms only `engine.py` uses
it). Births carry the window signal instead. **[V]** — delete.

**K2. No family is unsubscribed-and-untouched; the imbalance is all in
breadth.** Five of eight are exact-ish; `region` and `lane` are the two
overloaded families, and every content digest in the build sits on a
subscriber of one of them (see §3). **[V]**

**K3. `place` subscribes NARROWER than its true input set — the one
under-declaration that can cost yield.** `_place_reads`
(place_sched.py:187) subscribes to the 8 ring-neighbour extents at every
level plus its own extent at other levels. But `untried_consult` ->
`anchors_of` (place_sched.py:34) returns **every placement in
(capture, region), all levels, all extents**, and `consult_seeds`
(place.py:347) keeps the nearest `CONSULT_KEEP=8` of them while
`regional_seed` (place.py:366) uses **all** of them. **[V]**
Consequence: a pose committed by a non-ring-neighbour window is a real
input to this worker's seed list and produces no wake. It is not merely
a lost wake — `worker_tier` returns `None` when the ladder is spent, and
`_push_worker` (engine.py:251) *returns without pushing* on a `None`
tier, so such a worker sits in the index with no queue entry and is
re-armed only by a subscribed key. A distant pose that would have
offered it a fresh seed never reaches it. **[I]** on the yield size;
the mechanism is **[V]**.

**K4. `place` consults certificates with no subscription.**
`prepare_place` and `ring_pass_job` call `tiles.done_cells`, which reads
`_certificates` and `_frames`. `reads_doc` says "done projection
consulted at fire", so this is deliberate — but it is an unsubscribed
input feeding a *retirement* decision (`state.retired = True` at
place_sched.py:151). **[V]**

**K5. `tiles.scan/union/retry` read `_certificates` in
`eligible`/`retire`/`_pending_streams` without subscribing to
`("tile",…)` — under-declared but sound**, because certificates are
monotone and can only *retire* these workers. A missed wake costs a
wasted pop, never a wrong answer. **[V]**

**K6. `tiles.freeze` is the broadest over-subscription in the build.**
`_freeze_reads` (tiles.py:814) subscribes to `("lane", cid, li, page)`
for **every page**; `_fold_certificate` (engine.py:732) touches that key
for every lane on the page. So every certificate wakes every freeze
worker — and certificates are **not an input to freeze at all** (its
inputs are the lane's accepted `WindowEvidence` and `ColorEvidenceRow`).
e029: 1,940 certificates x 4 lanes = ~7,760 spurious wakes. **[V]**
Each resulting pop recomputes `_freeze_digest`, a sha256 over
`page_cells_yx` + `scores` + `printed_llr` of every accepted window in
the lane: at 200x200-cell windows that is ~1 MB/window, ~305 windows per
e029 lane, so **~300 MB hashed per freeze pop**. **[I]** (arithmetic;
the descriptor engine has no real-sheet run yet to measure it). This is
the single largest cost risk in the current wiring and the strongest
argument for D6.

**K7. `color` pays ~1,087 CPU-seconds per fire and subscribes to the
most overloaded key.** `_color_reads` is exactly `("lane", cid, li,
page)`, which conflates poses, K evidence, colour rows and certificates;
only poses and certificates are inputs (`prepare_color`,
color_region.py:854). Measured run-7: 151 colour fires for 164,076
CPU-s. **[V]** Every avoidable colour wake is ~18 CPU-minutes.

**K8. `revisit` subjects are enumerated per certificate over the whole
placement set.** `_revisit_subjects` (revisit.py:88) iterates
`sorted(store._placements)` computing `refine.reach_tiles(cells)` for
each, then iterates `sorted(store._windows)` — on every changed
certificate. e029: 1,940 x (1,319 + 1,325). **[V]** Bookmarks dedupe, so
this is cost, not wrongness — but `subjects_of` is on the merge thread.

**K9. `reads` is materialized once at birth (engine.py:291) and three
rows derive their key set from a pose.** refine, refine.color and
revisit build `("tile", page, ty, tx)` subscriptions from
`_page_cells[wid]` at birth. refine/refine.color retire on a revised
placement, so their reach is fixed for their whole life — sound. Revisit
does not: a pose revised by refine moves its reach and the subscription
does not follow. **[V]**

**K10. `("tile", …)` is coarser than its colour subscriber's input.**
`refine.color` uses `reach_streams` (color_refine.py:303), which is
per-`(page, ty, tx, stream)`; the key is per-tile. A sibling stream
certifying wakes the worker for a reach that did not change. Cheap here
(the attempt set catches it) but it is a genuine key/input mismatch.
**[V]**

---

## 2. THE WRITE FAMILY TABLE

Every `_`-prefixed mutable attribute on `_Engine`, its owner, and every
plugin function that reaches into it (owner + reader columns produced by
an AST pass over `plugins/*.py` attributing each `store._X` to its
enclosing function; **[V]**). "Guard" = what protects the cell from a
stale or out-of-order write.

| cell | owner (writer) | readers (prepare/reads/eligible/retire) | guard |
|---|---|---|---|
| `_captures`, `_levels` | `_fold_capture` | place`_place_reads`, survey`prepare`, tiles`_union_reads`/`_retry_reads`, calibrate/refine/color`prepare` | first-write-wins; frozen after `_start` |
| `_rasters`, `_planes_by_lane` | `_start` | survey`prepare`, `sampling_planes`/`rgb_planes` | frozen |
| `_row`, `_geometry`, `_lookup`, `_reference`, `_page_domain`, `_stream_index` | `__init__` | ubiquitous | frozen |
| `_surveys` | `_fold_survey` | survey`_survey_eligible`/`_retire` | one-shot via retire |
| `_frames` | `_fold_survey` | place x4, revisit`_revisit_place`, tiles`done_cells` | **bare**; safe only because survey is one-shot |
| `_plan_total` | `_fold_survey` | engine `_subdivide` | bare |
| `_windows`, `_ordinal_wid` | `_fold_window` | place`_place_stage`/`anchors_of`, revisit`_revisit_subjects`, tiles`prepare_freeze` | first-write-wins |
| `_placements` | `_fold_placement`, `_fold_refine_outcome` | **21 sites** across calibrate, color, color_refine, place_sched, refine, revisit, tiles | **bare** (last write wins) |
| `_pose_gen` | `_fold_placement` | place`anchors_of`, color`prepare_color` | monotone counter |
| `_page_cells` | `_fold_placement` | refine/color_refine/revisit `reads` + prepare | bare; aliased to `("pose", wid)` |
| `_region_pitch` | `_fold_placement` | calibrate`window_stamp`/`window_job`, refine`prepare` | value-compared before touching |
| `_live_pages` | `_fold_placement` | place`cold_pages_of` (cold ladder) | **BARE, NO KEY** — see W1 |
| `_lanes_on_page` | `_fold_placement` | revisit`_revisit_subjects`; engine `_fold_certificate` fan-out | **BARE, NO KEY** — see W2 |
| `_lattice_seeds` | `_fold_lattice_seed` | place`ring_pass_job` | support/bytes monotone merge |
| `_evidence` | `_fold_evidence` (both routes) | calibrate x3, refine x2, revisit x4, tiles`prepare_freeze` | change-predicate (4 of 17 fields) |
| `_region_ctx` | `_fold_ctx_outcome`, **and the bare `RegionCtx` branch** | revisit`_ctx_digest` | array-compare in one writer, **none** in the other |
| `_color_rows` | `_fold_color_row` | tiles`prepare_freeze` | `lane_generation` monotone + array-compare |
| `_color_models` | `_fold` RegionColorModel branch | **NOBODY** | dead cell — see W9 |
| `_tile_evidence` | `_fold_tile_evidence` | tiles`_lane_rows`/`_level_rows`/`_union_subjects` | epoch monotone |
| `_certificates` | `_fold_certificate` | 11 sites incl. `done_grid`, `done_cells`, all four tiles rows, refine, color, color_refine, revisit | append-only; conflict raises |
| `_equations` | `_fold_certificate` | engine close only | conflict raises |
| `_attempted` | **`tiles.prepare_scan`/`prepare_retry`** (a prepare, not a fold) | same | content key incl. evidence epochs |
| `_attempt_outcomes` | `_fold_attempt` | tiles`prepare_retry` | bare |
| `_freeze_epoch` | **`tiles.prepare_freeze`** (a prepare) | itself | monotone counter |
| `_done_grid_cache` | `tiles.done_grid` (a read path) | itself | keyed on `len(_certificates)` — sound (append-only) |
| `_done_cells_cache` | `tiles.done_cells` (a read path) | itself | keyed on `(len(poses), n_certs)` — **STALE after a pose revision**, see W10 |
| `_extra` | `_fold` catch-all | **NOBODY** | write-only sink — see W7 |
| `_bookmarks[..].stage` (WindowState) | `_fold_place_outcome`, `prepare_place`, `worker_tier`, `_afterlife`, `_place_repush`, `revisit._revisit_place` | place x5, revisit x2 | **BARE, NO KEY, cross-worker** — see W3 |
| `_bookmarks[..].stage` (stamps/sets) | calibrate, ctx, color, freeze, refine, color_refine, revisit prepares | own prepare only | the digests of §3 |
| `_account`, `_events`, `_n_certs_at_last_consult`, `_last_close` | engine | engine | n/a |

### Bare cells read by prepare/eligible functions (staleness-prone)

`_frames`, `_placements`, `_page_cells`, `_live_pages`, `_lanes_on_page`,
`_attempt_outcomes`, `_windows`, `_plan_total`, and the WindowState
stage. Of these only `_placements`/`_page_cells` are covered by a key
(`pose`); the rest have no key at all. **[V]**

---

## 3. STALENESS MECHANISM MAP

Three mechanisms are in use today. Per D6.6 the target is ONE — the
version floor over accessor change-detection — so the adjudication
column names **the honest key that replaces each digest**, or says
fire-time consult and shows the number that justifies it.

### Mechanism 1 — version floor (automatic)

`worker.tried_version == worker.version` at pop (engine.py:329), plus
`retire` before it and `eligible` after. Universal, already correct.
**[V]**

### Mechanism 2 — content digests / stamps (all to be deleted)

| site | what it hashes | compensates for | cost class | HONEST KEY that replaces it |
|---|---|---|---|---|
| `calibrate.prepare_window` (calibrate.py:658) | `(native_affine, region_pitch)` | `("region",…)` is touched by every sibling window's evidence, and `("pose", wid)` bumps on any Placement field | O(1) | **Split both**: `("pose_affine", wid)` (affine + pitch_px, value-compared) and `("region_pitch", cid, li, ri)` (scalar, value-compared). The stamp *is* those two values — with per-cell change-detection it becomes redundant, not merely cheaper. **[V]** |
| `calibrate.prepare_ctx` (calibrate.py:671) | sha256 over `window_id, page_cells_yx, scores, knots, probs, reference_values, accepted` of **every** evidence row in the region | `("region",…)` conflates pitch, sibling evidence and ctx's own output; a per-window `("evidence", wid)` subscription would make ctx wake on its **own** writes | O(rows x arrays); e029 ~305 windows x ~1 MB per region-level | **Split the evidence cell, not the key.** `apply_region_context` (calibrate.py:492-549) reads exactly `{accepted, scores, knots, probs, page_cells_yx, reference_values, patch_ordinal}` and writes exactly `{printed_llr, heldout_logloss, ctx_adopted}` — **zero overlap [V]**. So: `("evidence_fit", wid)` (ctx's inputs) and `("evidence_read", wid)` (ctx's outputs). ctx subscribes to fit only: no self-wake, no digest, and the `from_ctx` flag and the `is not` identity guard in `_fold_ctx_outcome` both disappear. Cardinality 1,222 fit-keys on e029 — one subscription per window on one region worker, same wake count as today. |
| `color_region.prepare_color` (color_region.py:863) | `(per-wid pose_gen tuple, certificate_digest(page))` | `("lane",…)` conflates poses / K evidence / colour rows / certificates | O(placements + certs on page) per pop; and the digest **cannot** suppress once any certificate has landed, so it is not what limits colour to 151 fires — the price ladder and rework aging are **[V]** | Two derived cells published by their producers: `("lane_poses", cid, li, page)` (tuple of `(wid, affine)`, value-compared) and `("page_certs", page)` (the page's certified address set / count). Both are exactly the stamp's two halves. Cardinality: 9 + 1 on sheet I. Fire count unchanged; ~18 CPU-min per fire means the *exactness* matters more than the saving. |
| `tiles.prepare_freeze` (tiles.py:629) | sha256 over `evidence_digest` of every accepted K row + every colour row in the lane | `("lane",…)` is touched by certificates, which are **not** an input to freeze | **~300 MB hashed per pop** (e029, **[I]**) x ~7,760 certificate-driven wakes | `("lane_evidence", cid, li)` — a derived generation counter bumped by the `evidence_*` and `color_row` accessors only. Fine per-window keys are the alternative (1,222 index entries per lane, identical wake count); the counter is O(1) index for the same behaviour, so **prefer the counter**. Certificates stop reaching freeze entirely. |
| `refine.prepare_refine` (refine.py:569) | `(certified_reach, evidence_digest, native_affine, route)` in an unbounded `worker.stage` set | its three subscriptions are already the three components; the digest exists because `_fold_evidence`'s change predicate is **narrower** than `evidence_digest` (W6) | O(window arrays) per pop | Nothing new — keep `("evidence_fit"/"evidence_read", wid)`, `("pose_affine", wid)` and the per-reach `("tile", …)` keys, and **fix the evidence accessor to compare every field its consumers read**. Then delete the attempt set. Behaviour note: the set also blocks A->B->A returns; the version floor does not. Certificate reach is monotone so A->B->A is impossible there **[V]**; an oscillating ctx adoption could re-fire refine once per oscillation, damped by rework pricing per D6.6. Flag for the review. |
| `color_refine.prepare_color_refine` (color_refine.py:334) | `(per-stream reach, native_affine, route)` | `("tile", page, ty, tx)` is coarser than the per-stream reach it keys on | O(certs on page) per pop | Make the tile family **per-stream**: `("tile", page, ty, tx, stream)`. Cardinality 1,961 -> **5,883** on sheet I (x3), ~21k -> ~63k index entries across refine-class subscribers **[I]** — trivially affordable, and it makes the subscription exact. Consumers wanting "any stream" over-declare across the 3 streams, which is safe by construction. |
| `revisit._revisit_calibrate` (revisit.py:50) | `("calibrate", window_stamp, cert_reach, ctx_digest)` | same coarseness as calibrate + refine combined | O(certs + ctx array) per pop | `("pose_affine", wid)` + `("region_pitch",…)` + `("region_ctx", cid, li, ri)` + the per-reach tile keys. All four exist once `region` is split; delete the set. |
| `tiles._pending_streams` / `prepare_retry` (tiles.py:710, 775) | `attempt_key(page, ty, tx, stream, stage, components)` into `_attempted` | nothing — this is an **idempotence floor**, keyed on evidence *epochs*, not a content hash | O(1) | **Keep.** D6.1 explicitly permits generation/epoch compare; this is that, not a digest. It is the tried-set floor for a subject whose identity is (tile, stream, evidence-set). |
| `tiles.done_grid` / `done_cells` caches (tiles.py:544, 567) | `len(_certificates)` / `(len(poses), n_certs)` | cache validity, not scheduling | O(1) check, O(page) rebuild | `done_grid` is sound (certificates append-only). `done_cells` is **not** — see W10; it must key on a pose *generation*, which `_pose_gen` already provides but `region_poses` drops. |

### Mechanism 3 — ad-hoc change checks inside folds

All **[V]**; all become accessor change-detection under D6.1.

- `_fold_evidence` (engine.py:604): `array_equal` on `scores`,
  `printed_llr` + `accepted`, `ctx_adopted`. **4 of 17 fields.**
- `_fold_ctx_outcome` (engine.py:636): `array_equal` on `ctx.offsets`
  + `adopted`, `reason`; plus the identity guard
  `self._evidence.get(before.window_id) is not before`.
- `_fold_color_row` (engine.py:694): `lane_generation` monotone reject,
  then `array_equal` on `values`, `page_cells_yx`.
- `_fold_placement` (engine.py:580): `pitch != standing_pitch` — the
  only place the region key is rationed.
- `_fold_lattice_seed` (engine.py:592): `support_cells` then
  `rows.tobytes()` tie-break (a byte-compare, but on a tiny array).
- `_fold_tile_evidence` (engine.py:664): `epoch` monotone.
- `_fold_certificate` (engine.py:713): `array_equal(user_bits)` —
  integrity, not staleness; keep.

### The mechanism that must SURVIVE (and is not a digest)

`ColorEvidenceRow.lane_generation` (data.py:174, set from
`worker.version` at color_region.py:875, enforced at engine.py:693) is
**not** a content digest — it is an in-flight generation guard: a job
prepared at version *v* must not overwrite state written from version
*v+1*. The version floor does not cover this, because the floor is about
*re-firing*, not about *merge order*. Under D6 this generalizes to: every
accessor write carries the version its job was prepared at, and the
accessor rejects writes older than the cell's generation. `_tile_evidence`'s
`epoch` and `_lattice_seed`'s support-monotone merge are the same class.
Keep all three; they are orthogonal to the digest deletion. **[V]**

---

## 4. MINIMALITY / SUFFICIENCY VERDICT

### The one law that explains every digest

**A content digest is the receipt for a key that is coarser than its
subscriber's input set.** All eight digest sites in §3 sit on a
subscriber of `("region",…)` or `("lane",…)` — the only two families
that carry more than one kind of change. Split those two and the digests
have nothing to compensate for. Conversely: **merging keys manufactures
digests**, which settles the per-`wid` triple question below. **[V]**

### Per-family verdict

- **`window`** — does not earn its place. Zero subscribers; births
  already carry the signal. **Delete.**
- **`pose`** — earns it, but is coarser than every subscriber. All four
  subscribers key on the affine (+pitch); `route` drives only
  `retire`. **Split** into `pose_affine` and `pose_route`;
  `_page_cells` rides `pose_affine` as a derived cell.
- **`evidence`** — earns it, and must be **split into `evidence_fit` /
  `evidence_read`**. This is the strongest structural finding in the
  audit: the fit/read partition is exactly the ctx read/write partition,
  measured off `apply_region_context` **[V]**, and it removes a digest, a
  boolean flag (`from_ctx`), an identity guard, and a latent self-wake
  cycle in one cut.
- **`region`** — does **not** earn its place as one family. It carries
  two unrelated quantities (pooled pitch, ctx offsets) written by two
  different folds and read by different subscribers. **Split** into
  `region_pitch` and `region_ctx`. Cardinality 4 / 9 — splitting costs
  nothing.
- **`lattice_seed`** — earns it. One writer, one subscriber, exact.
- **`lane`** — does **not** earn its place. Four unrelated touchers
  (poses, K evidence, colour rows, certificates) and three subscribers
  wanting different subsets; it is the reason freeze hashes 300 MB per
  pop and colour burns 18 CPU-minutes per avoidable fire. **Split** into
  `lane_evidence` (cid, li), `lane_poses` (cid, li, page) and
  `page_certs` (page).
- **`tile`** — earns it, but should become **per-stream**
  (`page, ty, tx, stream`) so `refine.color`'s subscription is exact.
  1,961 -> 5,883 keys on sheet I. **[I]** cost, trivial.
- **`tile_evidence`** — earns it exactly as it stands. The one family
  where the key is deliberately coarser than the cell (drops `arm`) and
  that coarsening is correct: arms are alternative evidence for one
  subject.

### Should any two merge?

**No — and specifically not the per-`wid` triple
(`window`/`pose`/`evidence`).** They have three different writers
(survey fold, place fold, calibrate fold) and disjoint subscriber
interest: calibrate wants pose only, ctx wants the fit half of evidence
only, refine wants both plus reach. A merged per-`wid` key would bump on
any of the three and every subscriber would need a digest to discover
which — i.e. it would recreate exactly what D6.6 deletes. The audit's
recommendation runs the other way: the schema should get **more**
families (13, below), not fewer. **[V]** by the digest law above.

### What is MISSING — signals smuggled through code paths

1. **`live_pages`** — the cold ladder's page split
   (`place.cold_flavour_pages`) is driven by a cell with no key. Needs
   `("live_pages",)` (or `("page_live", page)`). **[V]**
2. **`done` coverage** — place and revisit retire windows on
   `done_cells` with no subscription. Needs `("page_certs", page)` (or a
   per-region done generation). **[V]**
3. **WindowState** — `placed`/`retired`/`dormant`/`children` are read by
   *other* workers (`revisit._revisit_subjects`, `_afterlife` across
   siblings) yet live on a bookmark. D1 says "no domain state on
   workers, ever"; this is domain state. Promote to a cell with
   `("place_stage", wid)`. **[V]**
4. **`_repush` as a private wake edge** — `_afterlife` (engine.py:501),
   `_place_repush` (engine.py:506) and `prepare_place`
   (place_sched.py:157) call `store._repush` directly. Three wake edges
   invisible to the key graph. Two are re-pricing (legitimate, but they
   belong to the scheduler, not to a plugin's prepare); one
   (`_afterlife`) is a genuine cross-subject dependency —
   "all my children retired" — that deserves a key. **[V]**
5. **`lanes_on_page`** — decides which lane keys a certificate fans to,
   with no key of its own. **[V]**
6. **revisit's mode dispatch** — placed-vs-unplaced is smuggled through
   `wid in store._placements` in four separate functions
   (`prepare`, `subjects`, `reads`, `eligible`, `retire`). Two subjects
   kinds wearing one descriptor. **[V]**

### Proposed final schema for D6 (input to review, not ratified)

Thirteen key families, one line of rationale each:

| key | rationale |
|---|---|
| `("pose_affine", wid)` | the only pose fact anyone schedules on; kills the calibrate stamp |
| `("pose_route", wid)` | drives refine/refine.color retirement only; separating it stops route-only writes waking calibrate |
| `("place_stage", wid)` | WindowState is cross-read domain state; gives `_afterlife` a key instead of a `_repush` |
| `("evidence_fit", wid)` | ctx's exact input set; measured disjoint from its output set |
| `("evidence_read", wid)` | ctx's exact output set; freeze/refine read it; no self-wake |
| `("region_pitch", cid, li, ri)` | scalar, value-compared; the other half of the calibrate stamp |
| `("region_ctx", cid, li, ri)` | array cell, generation-compared; revisit's `_ctx_digest` |
| `("lattice_seed", cid, li, ri)` | unchanged; already exact |
| `("lane_evidence", cid, li)` | freeze's only true input; O(1) index, certificates stop reaching it |
| `("lane_poses", cid, li, page)` | colour's pose input; half the colour stamp |
| `("page_certs", page)` | colour's certificate input, the done projection, and both done caches' generation |
| `("tile", page, ty, tx, stream)` | per-stream so `refine.color`'s reach subscription is exact |
| `("tile_evidence", page, ty, tx, cid, li)` | unchanged; the one correct deliberate coarsening (drops `arm`) |
| `("live_pages",)` | the cold ladder's input; today a silent write |

Deleted: `("window", wid)`. Merged: none.

**Engine vocabulary note (D6 addendum 5).** Nothing above names a tier.
`TIER_RING`/`WORD_CENTRE`/`WIDE`/`COLD_*` and `STAGE_OF_TIER` are place's
ladder vocabulary and belong inside `place_sched`; the engine's schema is
keys + integers + the rework law. Today `place.TIER_COST` is consulted
inside `prepare_place` (place_sched.py:156) to compare a fresh tier
against the popped one — that comparison survives as a comparison of
`cost()` integers, entirely inside the plugin. `engine_types.TIER_COST`
and `TIER_*` should leave `engine_types` with the price scale (D6.4), and
diag labels become descriptor name + opaque stage. **[V]** that no other
plugin imports place's tier names (only `place_sched` and `place` do).

---

## 5. SILENT-WRITE FINDINGS (the important ones)

Folds whose mutations exceed their returned keys, plus the two structural
defects found alongside. Ordered by consequence.

**W1. `_live_pages` — written by `_fold_placement` (engine.py:569), no
key, read by the cold ladder.** `place_sched.cold_pages_of` ->
`place.cold_flavour_pages` partitions the page domain into live/rest by
this set, and the partition selects `TIER_COLD_LIVE` vs
`TIER_COLD_REST` — i.e. it changes both *pricing* and *what pages a cold
pass searches*. When the first placement on a page lands, every place
worker's cold ladder changes and nothing is touched. **[V]** mechanism;
**[I]** yield impact. Same class as the lane_generation incident.

**W2. `_lanes_on_page` — written by `_fold_placement` (engine.py:570),
no key, and it decides the certificate fan-out.** `_fold_certificate`
(engine.py:732) touches lane keys only for lanes *already recorded* on
that page. A lane whose first placement lands after certificates have
accumulated never receives those certificates' lane wakes; its colour
and freeze workers see them only on the next unrelated touch. Also read
by `revisit._revisit_subjects`. **[V]**

**W3. WindowState is mutated from six places with no key, and is
cross-read.** `_fold_place_outcome` (engine.py:520-552) sets
`tried/centre_spent/rest_spent/wide_spent/cold_*/retired/dormant`;
`_subdivide` sets `children`/`parent`; `_afterlife` flips
`retired`/`cold_armed`/`afterlife_used`; `prepare_place` and
`revisit._revisit_place` set `retired = True` from a *prepare*. These
are read by `revisit._revisit_subjects` (other subjects' `placed`) and
by `_afterlife` (siblings' `retired`/`placed`). Cross-worker state with
no wake edge. **[V]**

**W4. `_afterlife` un-retires a worker without re-registering its
subscriptions.** `_retire_worker` (engine.py:270) removes the worker
from `self._index` for every read key. `_afterlife` (engine.py:494-501)
sets `worker.retired = False` and `_repush`es — but never re-adds the
index entries. A resurrected parent window therefore gets exactly the one
pushed chance and is invisible to every future key touch. **[V]**;
damage bounded because `afterlife_used` makes it one-shot **[I]**.

**W5. `worker_tier` — a PRICING function — mutates domain state.**
`place_sched.worker_tier` (place_sched.py:179) sets
`state.dormant = False` before returning the tier. It is called from
`_push_worker` (engine.py:254), i.e. on every birth, every wake and
every repush. So *pricing a worker un-dormants it*, and a dormancy set
by `pose_refused` is cleared by any unrelated neighbour wake. **[V]**
Under D6.3's `cost(store, subject, stage)` this must become pure.

**W6. `_fold_evidence`'s change predicate is not a superset of its
consumers' digests.** The fold compares `scores`, `printed_llr`,
`accepted`, `ctx_adopted` (4 of `WindowEvidence`'s 17 fields) and stores
the new object either way (engine.py:610 runs before the early return).
`evidence_digest` additionally hashes `page_cells_yx`; the ctx digest
additionally hashes `knots`, `probs`, `reference_values`. A change
confined to those fields is stored and touches **nothing**, while a
consumer that later recomputes its digest sees a difference it was never
woken for. **[V]** on the field lists; **[I]** that it is reachable in
practice (pose changes normally move `scores` too, and refine also holds
a `pose` subscription). Structural, and precisely the class D6.1 closes.

**W7. The `_fold` catch-all silently swallows unknown facts.**
engine.py:409 appends to `_extra` and returns `changed=True, keys=()`;
`_extra` is never read anywhere in the tree. Any fact type not in the
`isinstance` chain vanishes with no error and no wake. **[V]** Should be
a hard error once accessors make the write set total.

**W8. The `data.RegionCtx` fold branch writes `_region_ctx` and touches
no key.** engine.py:401-404. No plugin emits a bare `RegionCtx` today
(only `CtxOutcome` carries one), so the branch is unreachable — but it
is live code that would silently desynchronize revisit's `_ctx_digest`
if a producer ever appeared. **[V]**

**W9. `_color_models` is written and never read.** engine.py:405-408
folds `RegionColorModel` into a dict no function in `holo3/` touches
(grep: two hits, both the write). Dead cell + keyless fold branch.
**[V]** `RegionColorModel` is really emitted (color_region.py:746, 791),
so this is a live fact stream terminating in a void.

**W10. `done_cells`'s cache key cannot see a pose revision.**
tiles.py:576-586 keys the cache on `(len(poses), n_certs)`; a refine
adoption replaces `_placements[wid]` in place, so **both are unchanged**
while the projection's inputs moved. Any `done_cells` consumer
(`prepare_place`'s `done_covers` retirement, `ring_pass_job`'s
`done_cells`, `revisit._revisit_place`) can act on a stale done map
until the next certificate. `_pose_gen` already exists and would fix it;
`region_poses` (tiles.py:554) drops it. **[V]** mechanism; **[I]**
exposure (a revision without any subsequent certificate).

**W11. Prepare functions write to the store.** `tiles.prepare_freeze`
bumps `_freeze_epoch`; `tiles._pending_streams`/`prepare_retry` add to
`_attempted`; `prepare_place`/`_revisit_place` set `state.retired`;
`worker_tier` clears `dormant`; every stamped prepare writes
`worker.stage`. Correct today only because prepare runs on the merge
thread — but it contradicts "every fire is pure over a snapshot" and
means `prepare` returning `None` is sometimes a state transition. **[V]**

**W12. `revisit` declares `produces=()` while emitting four fact types
from two other domains.** `prepare_revisit` returns
`calibrate.window_job` (emits `WindowEvidence`) or
`place_sched.ring_pass_job` (emits `Placement`, `LatticeSeed`,
`PlaceOutcome`). `check_single_writer` (engine.py:74) therefore sees
`WindowEvidence -> {calibrate}` and passes, while two descriptors write
the cell in fact. The startup invariant is satisfied by declaration, not
by behaviour. **[V]** Job accounting and diag attribution are likewise
wrong for revisit's fires. (`refine`/`refine.color` both producing
`RefineOutcome` is fine — the check's shared-prefix escape hatch covers
it deliberately.)

---

## 6. What this audit did NOT check

- No decode was run; no production file was modified.
- The descriptor engine has **no real-sheet run on record** — every
  parity artifact predates it. K6's 300 MB-per-pop and K7's per-fire
  cost are arithmetic and old-engine CPU respectively, not measurements
  of the current wiring. A single instrumented e029 run under the
  descriptor engine would settle both, and should probably precede D6.
- `holo2`/`src/holo` were not consulted; this is a holo3-internal audit.
