# K-vs-color label sampling shape split — measured analysis (A3)

Status: **measured analysis, not normative; ruling pending.** No
production code changed by this record. The RECEIVE-DESIGN §8.2 and
COLOR-INTEGRATION-DESIGN §5.3 amendments proposed in §7 await the user
ruling and are NOT part of this commit.

Provenance: PAYLOAD-REWORK-PLAN addendum **A3** (chip `task_45921656`),
re-evaluating the pool-law Phase-1 decision (RECEIVE-DESIGN v0.35, commit
`a1d8fbc`) to ship one label LAW (L1–L6) with two per-channel sampling
SHAPES — K label rows sample the full window; color label rows are sparse
furniture-site rows. The user reserved this debate in the pool-law ruling
("same solution for b/w and color … to be debated if cmy8 is different").
Date: 2026-08-02.

## 1. Tree-state attribution

Every number below is pinned to a commit:

- Eval worktree branched from `main` @ `784dba3` (RECEIVE-DESIGN v0.44,
  color R-lane audited committed-pose domain). Chain: `175f492`
  (measurement scaffolding only; `src/` byte-identical to `784dba3`) →
  `93ad243` (the candidate-(a) measurement patch, §appendix). The branch
  and worktree were removed after harvest; the patch survives verbatim in
  the appendix.
- Color baseline arm: worktree HEAD `175f492`. Candidate-(a) arm:
  worktree HEAD `93ad243`. Raw JSONs (`color-baseline-wt.json`,
  `color-fullrows-wt.json`) in `scratch/label-shape-eval/`.
- K-side results were measured in the main tree at `316572f`;
  `git diff 316572f..784dba3` over the four files that carry the K
  mechanism (`_payload_sampling.py`, `_payload_context.py`, `detect.py`,
  `_payload_reuse.py`) is empty, so they stand for `784dba3` unchanged.
- An earlier color baseline ran while another session was editing the
  main tree and is attributable to no single commit; it matches the
  pinned baseline on every headline metric (172 regions, 1390 patches,
  604 certificates, 39 adopted) but the `-wt` files are the citable
  record.
- CPU discipline: other jobs ran concurrently, so arms are compared on
  CPU seconds (`time.process_time` + rusage; per-stage
  `timing.processor_seconds` for attribution). In both runs cpu ≈ wall
  (1537.3/1532.1 s and 1550.6/1542.5 s), so the wall-anchored
  event-delta decomposition happens to be trustworthy here, but it is
  marked indicative-only in the JSONs.

## 2. Rationale verification — both hold at `784dba3`

- **K full-window** (`_payload_sampling.py`): certified-complete windows
  route through the full-window label path because the K context fit
  (`_payload_context.apply_region_context` over
  `detect.context_neighbour_counts`) requires each label site's complete
  8 payload-cell neighbourhood, and full-window keeps the label row
  byte-equal to the pooled-oracle payload row (pinned in
  `tests/holo/test_pool_law_oracle.py`).
- **Color sparse** (`color_anchoring._label_site_rows`): furniture-site
  rows (word/dust only, no payload sampling, no projection build); the
  QDA fit is per-cell with no neighbourhood mask; `_fit_registration`
  excludes label rows because sparse rows have no complete 3×3 in-row
  neighbourhoods for the NCC anchor leaf. The v0.42–v0.44 rework did not
  change any of this.
- **Refinement of the anchor-loss story**: open windows ALREADY
  contribute prior-certificate payload components as anchor candidates
  (COLOR-INTEGRATION-DESIGN §5.3 "pre-lane certificate" class). The L2
  anchor loss is confined to certified-COMPLETE windows in mixed
  regions.
- **Corrected reading of the sparse saving**: what color's sparse shape
  saves is the sampled points, fit rows, and anchor workload — NOT the
  window crop+filter. Label patches still pay the native crop: the
  region divisor probe and the sparse rows' features read every
  placement's crop (`_window_raw_crops` over patches ∪ label patches),
  so the crop cost is shape-independent. The same is true on the K side
  (the sites span the window, so the crop bounding box cannot shrink) —
  this bounds what EITHER unification direction can save or cost.

## 3. Candidate (a): color adopts full-window label rows — MEASURED

Real corpus `scratch/c2-cmy7-hp-nominal-canon4800-q070-max-20x2-20260731-155516`
(HP c2 print, Canon 4800 scans, 2 captures), `run_mopup=True`,
`run_refine=False` (the PAYLOAD-MEASUREMENTS §6 "no-refine" arm), 16
barriers. Patch: certified-complete windows and D7 label placements
build K-parity full rows (states + `_known_components` projection
overlay + neighbour rows) and join both the QDA fit and
`_fit_registration`.

| metric | baseline `175f492` | full rows `93ad243` | delta |
|---|---|---|---|
| CPU total | 1537.3 s | 1550.6 s | +13.3 s (+0.9%) |
| payload stage CPU | 532.5 s | 568.5 s | +36.1 s (+6.8%) |
| … of which mopup payload | 58.7 s | 85.7 s | +27.0 s (+46%) |
| certificates | 604 | 604 | **0** |
| close status | open | open | — |
| regions / patches | 172 / 1390 | 172 / 1390 | 0 |
| fit population (train+heldout) | 8,389,778 | 12,712,504 | 1.52× |
| registration adopted | 39/172 | 42/172 | +3 net (7 on / 4 off) |
| total anchors (all regions) | 79,268 | 99,757 | +26% |
| heldout logloss Δ (172 co-fit regions) | | | median +0.00000, mean +0.005, min −0.233, max +0.760 |

Readings:

- Certified-complete windows DO occur throughout the ladder (fit
  population 1.52×; single regions grew e.g. 8,346→90,908 and
  11,710→181,233 train sites) — the shape choice is genuinely exercised
  — yet restoring them changed nothing downstream: same 604
  certificates, same open close, byte-identical region/patch inventory.
- The adoption changes are all-or-nothing gate flips (anchors 0→~1000 or
  the reverse) and BIDIRECTIONAL: 7 on, 4 off. Two flips-on made
  held-out loss substantially WORSE (0.110→0.870, 0.0096→0.0176); one
  clearly better (0.646→0.413). Median loss delta over all 172 co-fit
  regions is exactly 0. This is gate noise around a threshold, not a
  systematic registration-quality improvement.
- **Anchor-starvation re-read**: the 133/172 zero-anchor baseline
  regions are regions where adoption was REFUSED and `PlaneResidual`
  reports the zero fallback — gate-refused, not candidate-starved.
- **Small stakes on this footing**: where registration IS adopted, the
  corrections are tiny — adopted per-plane intercepts have median
  max-abs 0.025 dots (baseline; 0.024 candidate; max 0.272/0.184).
- The cost concentrates exactly where certificates are dense (mopup
  payload +46% CPU). With `run_refine=True`, the R lanes replay
  certificate-rich regions and would bear this bucket
  disproportionately.
- Instrument note: `calibration_labels` is a CMY8-only counter (the CMY7
  QDA branch reports 0 structurally) — do not read it as "no label
  contribution" on a CMY7 corpus.

## 4. Candidate (b): K adopts sparse site+halo label rows — MEASURED

Synthetic pool-law-oracle fixture geometry (128×128-cell window,
8 px/cell), main tree @ `316572f` (K files unchanged through `784dba3`).
Raw JSON: `scratch/label-shape-eval/k-sparse-differential.json`.

- **Cost**: full label row 14.4 ms vs sparse 10.0 ms — only ~31% saved,
  NOT the naive site ratio. The crop+filter (8.7 ms) dominates and is
  shape-independent; per-site sampling and PAVA calibration are already
  cheap (0.45 ms + 5.2 ms full). The halo requirement keeps 3,458 of
  16,384 cells (400 site cells + 8-neighbourhoods) — the ~9×-sites
  estimate describes the kept-cell ratio, not the achievable saving.
- **Exactness**: on the synthetic window the sparse row was end-to-end
  byte-identical (decision id, offsets, printed LLRs; marginal-LLR max
  |Δ| = 0.0; site-level PAVA is order-invariant) — BUT the `_scores`
  normalization population measurably moves: spread 102.946 → 102.135
  (the midpoint happened to coincide at 232.0). On real noisy data the
  median/spread shift WILL perturb LLRs, so byte-equality to the pooled
  oracle dies, breaking the v0.34/v0.35 exactness instrument
  (`test_pool_law_oracle.py` byte-equality pins) and forcing a K policy
  bump plus a new sparse `_WindowRows` shape.
- K label rows are rare (mixed-region certified-complete windows only)
  and the K sampler is the cheap part. Breaking the exactness discipline
  for ~4 ms on rare rows is rejected.

## 5. Third option: anchor-only certified-window participation

Keep sparse label rows for the fit; additionally admit the
certified-complete windows' projected components into the §5.3
anchor-candidate pool (the "pre-lane certificate" class already does
exactly this for OPEN windows; the existing 512-candidates-per-class
budget prices it; the closed windows' native crops are already read for
the sparse label rows, so the extra cost is only the bounded NCC
measurements).

Evaluated against the §3 data: the loss regressions among the flips-on
implicate the FIT-population change (certified states shifting the QDA),
not the anchors — anchor-only participation would leave every held-out
loss byte-stable while restoring the candidates, at ~zero CPU. But the
same data shows nothing to fix today: no adoption refusal on this corpus
is attributable to missing certified-window anchors, and adopted
corrections are ~0.025 dots. **Designated post-08-04 lever**: revisit if
hardware/confetti corpora (the plan's deferred confetti-regime label
check) show genuinely furniture-poor certified areas where registration
is refused for lack of candidates.

## 6. Recommendation: keep the split — one law, two shapes

- Candidate (a) buys nothing measurable (0 certificate delta, adoption
  noise, loss a wash) for +7% payload-stage CPU concentrated where
  certificate-dense sessions spend their time, and re-pays the
  c7aa340-class sampling the skip deliberately saved.
- Candidate (b) saves ~4.4 ms per rare K label row at the price of a
  calibration-population perturbation on real data, retired
  byte-equality pins, a new row shape, and a K policy bump.
- The recorded L2 consequence (certified color windows contribute no NCC
  anchors) is measured to be inconsequential on the real corpus, and the
  §5 anchor-only option is the designated lever if that ever changes.
- The original "same solution for b/w and color" ruling is honored at
  the LAW level (L1–L6 identical); the shape difference is a per-channel
  implementation detail forced by each detector's actual input contract
  (ctx neighbourhood mask vs per-cell QDA).

## 7. Consequences per path (for the ruling)

| path | consequences |
|---|---|
| **KEEP (recommended)** | Doc-only. RECEIVE-DESIGN §8.2 L2: state the shape split is permanent with this record as the measured basis (ledger row, no policy bump). COLOR-INTEGRATION-DESIGN §5.3: one sentence that certified-complete windows contribute no anchor candidates by measured decision, anchor-only extension on record. No oracle changes, no code. |
| unify on (a) | Color policy bump `provisional-v8-r-lane` → v9 (fit populations + registration inputs change ⇒ decode-relevant; old states refuse). `test_pool_law_oracle.py` L6 pin: certified-window fit contribution 360 → 4336 on the oracle fixture. §8.2 L2 rewrite (drop the furniture-site clause) + v0.35 ledger correction note + PAYLOAD-MEASUREMENTS addendum + §5.3 registration paragraph update. Re-measure R-lane cost before committing (this eval ran `run_refine=False`). |
| unify on (b) | REJECTED. Would need: K policy bump, sparse `_WindowRows` shape, pooled-oracle byte-equality pins retired for tolerance pins (an exactness-discipline break needing its own ruling), ctx-fit population re-golden — for ~4 ms per rare label row. |

These amendments await the user ruling; none is part of this commit.

## 8. Honest limits

- One footing only: HP c2 print / Canon 4800 scans, CMY7. No CMY8
  corpus, no office-engine print, no confetti-regime material.
- The corpus is non-closing and coverage-limited (close stays `open` at
  604 certificates in every arm) — a corpus that closes near the
  boundary could in principle react to registration changes this one
  absorbs.
- `run_refine=False`: R-lane behavior under candidate (a) is priced by
  extrapolation (certificate-dense replay), not measured.
- CPU-seconds comparison under concurrent machine load; the event-delta
  decomposition buckets are wall-anchored and indicative only (mitigated
  here by cpu ≈ wall in both runs).
- K exactness was measured on the synthetic oracle fixture only; the
  real-noise LLR perturbation is inferred from the measured
  normalization-population shift, not measured directly.

## 9. Reproduction

Corpus: `scratch/c2-cmy7-hp-nominal-canon4800-q070-max-20x2-20260731-155516`
(the 68.6 GB scan corpus's derived fixture; stays where it is). Raw
outputs and superseded runs: `scratch/label-shape-eval/`.

Color arms (run once per arm, sequentially, never in parallel; the
candidate arm needs the appendix patch applied):

    PYTHONPATH=src:tests/holo env/bin/python \
        tests/holo/_bench_label_shape_color.py run <corpus_dir> <arm> <out.json>

Region-by-region comparison (adoption flips, anchor support, held-out
loss deltas, fit population, per-lane table — the comparator lives in
the same file as the runner):

    PYTHONPATH=src:tests/holo env/bin/python \
        tests/holo/_bench_label_shape_color.py compare <a.json> <b.json>

K micro-bench + exactness differential (synthetic; no patch needed):

    PYTHONPATH=src:tests/holo env/bin/python \
        tests/holo/_bench_label_shape_k.py <out.json>

CPU-time discipline: the color runner records `cpu_s` (process time) and
`rusage_cpu_s` (utime+stime) beside wall and embeds the tree's HEAD sha
in each JSON; compare arms on CPU seconds, use per-stage
`timing.processor_seconds` for attribution, and treat the wall-anchored
decomposition buckets as indicative only under load.

## Appendix: the candidate-(a) measurement patch (worktree `93ad243`)

Measurement-only; never merged. Applied on `784dba3`-era
`color_payload.py` (post-v8 `fully_certified_color_addresses` split).

```diff
diff --git a/src/holo/receive/color_payload.py b/src/holo/receive/color_payload.py
index 74149da..bb3a0dd 100644
--- a/src/holo/receive/color_payload.py
+++ b/src/holo/receive/color_payload.py
@@ -721,16 +721,9 @@ def collect_color_evidence(
         payload_rows: list[_Rows] = []
         label_rows: list[_Rows] = []
         emission_by_row: list[np.ndarray] = []
-        for patch, aligned, is_open, emit in zip(
-                patches, aligned_rows, open_flags, emission_masks,
-                strict=True):
-            if not is_open:
-                # L2: certified-complete/zero-payload — label row only.
-                label_row = _label_site_rows(
-                    spec, page, patch, aligned, certificate_index)
-                if label_row is not None:
-                    label_rows.append(label_row)
-                continue
+
+        def _full_row(patch: PlacedPatch, aligned) -> _Rows:
+            # A3 MEASUREMENT ARM (a): K-parity full-window row.
             states, furniture_kind = color_reference_states(
                 spec, page, aligned.page_cells_yx)
             (
@@ -746,7 +739,7 @@ def collect_color_evidence(
                 certificate_index,
                 projection_cache,
             )
-            row = _Rows(
+            return _Rows(
                 patch,
                 aligned.local_cells_yx,
                 aligned.page_cells_yx,
@@ -758,15 +751,21 @@ def collect_color_evidence(
                 _neighbor_rows(aligned.local_cells_yx),
                 dependency_certificate_ids,
             )
+
+        for patch, aligned, is_open, emit in zip(
+                patches, aligned_rows, open_flags, emission_masks,
+                strict=True):
+            row = _full_row(patch, aligned)
+            if not is_open:
+                # A3 ARM (a): certified-complete window = FULL label row
+                # (joins fit + registration, never emits/owns).
+                label_rows.append(row)
+                continue
             payload_rows.append(row)
             emission_by_row.append(emit)
         for patch in label_patches:
-            # L3: D7 label placements are never terminal-gated.
-            label_row = _label_site_rows(
-                spec, page, patch, _window_rows(patch, spec),
-                certificate_index)
-            if label_row is not None:
-                label_rows.append(label_row)
+            # A3 ARM (a): D7 label placements full-window too.
+            label_rows.append(_full_row(patch, _window_rows(patch, spec)))
         payload_row_tuple = tuple(payload_rows)
         row_tuple = payload_row_tuple + tuple(label_rows)
         # Pool law L5: the region pitch (and the divisor scale probe) pools
@@ -791,12 +790,10 @@ def collect_color_evidence(
                 crops[int(row.patch.patch_id)], row, pitch_px, divisor)
             for row in row_tuple)
         del crops
-        # NCC anchors need complete 3x3 in-row neighbourhoods; a label
-        # row's sparse furniture sites have none, so payload rows alone
-        # carry the anchor workload (label rows would burn budget bins).
+        # A3 ARM (a): full label rows carry complete 3x3 neighbourhoods,
+        # so certified windows rejoin the anchor workload.
         residuals = _fit_registration(
-            raster, payload_row_tuple,
-            base_tuple[:len(payload_row_tuple)], spec)
+            raster, row_tuple, base_tuple, spec)
         corrected_rows = tuple(
             _features_with_page_fraction(
                 raster, row, residuals, spec, pitch_px, divisor)
```

Smoke check of the patch's semantics: the pool-law oracle L6 pin
(`test_law_l6_certified_color_window_is_label_contribution_not_payload`)
fails as expected under the patch, with the certified window's fit
population moving 360 (sparse furniture sites) → 4336 (full window with
projected components) — the intended semantic differential.
