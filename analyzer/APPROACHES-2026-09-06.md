# The third-layer C line — every approach, in isolation and in composition (W8, 2026-09-06)

Design document for wave W8 of the analyzer, on branch `analyzer-w8`.  It
answers one request: enumerate every approach identified for sheet H's
residual C plane, mark what each is (built / measured / new / lead / not
built), give each an isolation command and name the compositions it
belongs to, and specify what this wave builds.  The measured record it
rests on is `analyzer/MEASUREMENTS-2026-09-06-C-THIRD-LAYER.md` (cited as
MEAS §n); the reference implementations of every measurement are the
truth-reading scripts in `measure/c-third-layer-20260906/`, which stay
outside the package by design.

Nothing here changes DESIGN.md's rulings.  Where a proposal needs one it
says so (§4.0), and §5 lists what is deliberately left unbuilt.  This is
the revision after the three-lens review (blindness, feasibility,
completeness); every finding is dispositioned in §7, and §6 is the
record of what the runs actually measured.

## 0. What was measured, and why this wave exists

Sheet H (`L:c2-cmy8-r0850-p120-x1@3392x2368`, AltaLink print, 13 Canon
captures at 1200/2400/4800 dpi) is read to 5,580 of 5,883 tile-streams in
the newest production run (`scratch/holo3-H-with-facts-7-run.32018`, close
verified, sha `0ad329fb…`).  What remains is C in the dead band (tile
columns 30–31) and scattered Y.  MEAS §1 measured WHERE the C decision
fails: a C cell whose siblings M and Y are both inked is read 2–4× worse
than any other C cell, sheet-wide (band 0.214, marginal 0.133, live 0.106
against 0.05–0.07 for every other sibling state), while M under C+Y is the
best-read state on the sheet (0.020).  MEAS §2 placed the loss in the
pixels rather than the receiver: raw red-as-K 0.268, `subtract+offset`
0.214, `head` 0.215, `conditional` 0.228, `subtract+affine` 0.217 on the
band's M+Y cells — registration moves every other state by ~0.005 and
leaves this one alone.  MEAS §3 showed the mechanism: the third toner
layer on an M+Y pile has NO dot core (a flat red deficit at ~60 % of a
single layer's strength, spread over the cell and its surround — radial
profile 0.472 → 0.470 from centre to 13 px, against 0.359 → 0.450 for C on
paper), so the 0.7-cell box aperture reads it at 60 % strength and the
error on M+Y cells FALLS with the number of C-inked neighbours (isolated C
on a pile is the worst case, 0.33).  No existing arm touches it.

MEAS §4–§5b measured what compensates, every number truth-scored and
tile-parity cross-validated: (1) a learned linear discriminant over the
raw 24×24-px red patch at 4800 dpi, per lane, per plane, per sibling
state (shrinkage 1e-2 after standardisation) reads the band's M+Y cells at
0.149 against the box mean's 0.208 in a single lane; trained ONLY on the
certified edge tiles of the same lane (what a halo supplies) and applied
to a dead tile with no label from it, 0.203 → 0.119 single lane and
0.191 → 0.062 combined over the lanes — the filter's residual errors are
capture noise and average out where the box mean's are print-frozen; the
ordinary cells gain too (certified tiles 0.075 → 0.028); the permutation
control reads 0.46; per-LANE training is what matters (pooled across lanes
only 0.196).  (2) Self-training on the tile's own M+Y population adds a
little (0.119 → 0.114).  (3) A decoder-feedback proxy (25 % of the tile's
cells labelled by BP) adds more (0.085 single, 0.049 combined).  (4) The
arm's LLRs are OVER-confident on M+Y cells (|L| 2–4 claims 5.8 %, measures
15.7 %) and UNDER-confident elsewhere (slope ≈ 1.3); a per-(lane,
sibling-state) Platt fitted blind on certified neighbours takes the band's
combined error 0.088 → 0.076 and R 0.797 → 0.836, the per-(lane, state,
context) oracle 0.059.  (5) A blind per-(tile, lane, state) two-Gaussian
mixture on the red channel helps only the band's M+Y cells (0.219 → 0.190)
and is worse elsewhere.  Every per-state mechanism needs certified
siblings: true in the band (cargo cleanable 1.0 on 64 of 100 dead-band C
rows), false on the open live/marginal C tiles whose Y is open too
(cleanable 0.0 on 27 of 33 live rows).  This wave turns (1)–(5) into arms,
branches, a rule and two rungs of the analyzer, blind by construction,
each reachable alone and inside the union.

Two facts about the measurement's ESTIMATOR matter for reading every
number below, and the first draft of this document glossed both.  The
0.119 was fitted on WHOLE certified edge tiles (tx 29 and 32, all their
in-tile cells, no fold split, floor 300 labels per (lane, state)); a
halo-48 footprint at tx = 30 spans page-x 1872–2032, reaches 48 of tile
29's 64 columns and cannot reach tile 32 at all, and fits on its fit fold
only.  And the 0.062 / R 0.956 "combined" figures are a clipped sum over
the 4800 lanes with a per-tile even/odd Platt (`analyze_combined.py`) —
the offline `score` tool scores each lane on its own and has no combined
number.  §3 reads every run against the estimator that produced its
reference number, and no MEAS number is a gate on its own (§4).

### 0.1 Conventions used below

- **Sibling state** of a cell for target plane p: `left, right =
  spectral.siblings_of(p)` (ascending), `s = bits[:, left] + 2·bits[:,
  right]`, valid where `frame.siblings` (both siblings known), −1
  otherwise.  For C: 0 blank, 1 M, 2 Y, 3 M+Y; for M: 0, C, Y, C+Y; for Y:
  0, C, M, C+M.  State 3 is "both siblings inked" in every plane — the
  convention `oracle.py:314-318` and the measurement scripts use.
- **Blindness** (DESIGN §0.1): a run may fit on format furniture, certified
  neighbours' projected cells, the metadata bit, and — new in W8 — the
  tile's own confident cells (P2) and the decoder's confident extrinsic
  bits (P3), each recorded as such in the blind detail.  Decoder pseudo
  labels travel ONLY as a typed `PseudoLabels(source=…)` value built by
  the feedback rung; `evidence_for` refuses anything else at that door,
  the CLI refuses the reserved knob names, and the truth-reading `score`
  tool refuses a config that carries them (§4.0 ruling 8).  The target
  plane's OWN known bit never restricts a cell's hypothesis (the head-arm
  comment, `unmix.py:345-354`).  Certification is syndrome + CRC only;
  every CRC consult is charged to the exposure ledger.  Every composition
  runs DESIGN §8's controls (`null_arm`, `frame_null`, `parity_sample`)
  before its numbers are recorded — the blind twin of MEAS §5b's
  permutation control is `frame_null` (shifted certificates: wrong labels
  AND wrong sibling states) plus the unit test that shuffles the fit-fold
  labels and expects the discriminant to collapse.
- **Folds** (DESIGN §4.8): fit trains maps and filters, search scores
  registration searches, select chooses among arms and fits the
  combination rules.  W8 adds a ruling (§4.0 ruling 7): a FITTED score
  changes the fold contract — the PAVA map may not see the discriminant's
  own training rows, so the patch family CROSS-FITS inside the fit fold
  (two halves by `fold_hash` under a salted seed; each half scored by the
  other half's filter; PAVA and every search objective see only
  out-of-fold scores on fit-fold rows; the full-fit filter scores every
  other row).  Pseudo labels (P2, P3) join the FIT set only.  What is
  byte-identical with and without them: `label_rows`, `label_values`,
  `label_discriminating`, `label_state`, and the fact that no pseudo cell
  is ever a select-fold label row (pseudo rows are in-tile cargo, label
  rows are known cells).  `label_llr` is a held-out VIEW of whatever map
  the arm produced and moves with it; the feedback rung therefore
  recombines under the round-0 label view, so the combination
  coefficients never see a decoder-shaped LLR (§4.0 ruling 9).
- **Commands.**  Every BLIND run is on the newest production run dir; a
  `score` runs against the run dir its ledger was produced from (DESIGN's
  physical-evidence rule ties a ledger to its run), which for the C
  ledgers is `scratch/analyzer/H14-union`.  The prefixes below are used in
  the tables; §3 spells the runs that matter in full.

```
RUN=scratch/holo3-H-with-facts-7-run.32018
PY="PYTHONPATH=src:. env314t/bin/python"
LADDER="$PY -u -m analyzer ladder --run-dir $RUN --targets \"list scratch/analyzer/W8/C-open.list\" --workers 14"
SCORE="$PY -m analyzer score --ledger scratch/analyzer/ledgers-C/H14-C.jsonl --payload scratch/analyzer/H14-pass1/payload.bin --gt-dir scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm --run-dir scratch/analyzer/H14-union --workers 14"
CONTROLS="$PY -u -m analyzer controls --run-dir $RUN --workers 14"
BYSTATE="$PY measure/c-third-layer-20260906/bystate.py --level 3"
```

  `LADDER` is the blind pass (certificates, the ledger's stream × band
  table, leave-one-out attribution, the select-fold comparisons); `SCORE`
  is the offline truth-scored cell error of ONE arm on the 156 C rows of
  the H14 ledger (100 dead / 23 marginal / 33 live; per sibling state via
  `by_sibling_state`, per lane); `score.md` pools every lane and has no
  band axis, so the band × state × lane numbers of §3 are read from
  `score.jsonl` by `bystate.py` (truth-side, legitimate offline; B1 gives
  it `--level 3` = the 4800 lanes only, MEAS §4/§5b's population).
  `CONTROLS` is DESIGN §8's instrument.  One analyzer process at a time.
- **Knobs.**  `--knob KEY=VALUE` (JSON value, else string) lands in B1 on
  `ladder`, `read`, `controls` and `score` — every knob-carrying run of §3
  needs it, so it is the first item's, not the last's.  Reserved names
  (`pseudo_labels`, `refit`, `sibling_state`, `disagree`, `ctx_offsets`,
  `ctx_state_adopted`) are refused at the CLI; those are derived inside
  `blind_key` and assigned unconditionally.  B5 adds `--ctx-mode`,
  `--no-reroll`, and makes explicit `--arms/--rules/--rungs` WIN over a
  profile's lists (§4.5); until B5 an isolation inside a profile is
  spelled without `--profile`.

## 1. The enumeration

Columns: **id** | **mechanism** | **hook** (module/function) | **labels
and blindness** | **status** | **measured so far** | **isolation** (the
exact flags on `LADDER` / `SCORE`) | **compositions** (§2).

### 1a. Unmixing modes (existing; `unmix.UNMIX_MODES`, `unmix.unmix_score`)

| id | mechanism | hook | labels / blindness | status | measured | isolation | compositions |
|---|---|---|---|---|---|---|---|
| U1 `raw` | channel t absorbs; plane presence = centred red (for C) ÷ own shift | `spectral.plane_score(MODE_RAW)` via `unmix_score` | mix fit on regressors (three planes known); no per-cell labels | built | band M+Y 0.268 (MEAS §2), the worst arm | `LADDER --arms "raw+committed"`; `SCORE --arms "raw+committed"` | X5 (in DEFAULT_ARMS), X6 |
| U2 `project` | GLS annihilating both siblings; the paired control for `subtract` | `spectral.plane_score(MODE_PROJECT)` | as U1 | built | — | `--arms "project+committed"` | X5, X6 |
| U3 `subtract` | per-cell sibling subtraction where both siblings known | `spectral.plane_score(MODE_SUBTRACT)` | siblings' known bits only | built; THE default (`subtract+offset`) | band M+Y 0.214, other states 0.05–0.07 (MEAS §1) | `--arms "subtract+offset"` (the pinned default; every other run's control) | every X |
| U4 `global` | `subtract` on the lane-scope mix (12-tile deterministic sample, memoised) | `unmix.lane_mix`, `unmix_score("global")` | as U3, lane-scope regressors, target tile excluded | built | — | `--arms "global+offset"` | X5, X6 |
| U5 `head` | the analyzer's own 8-state classifier, two-of-three relaxation; only siblings restrict hypotheses | `unmix._head_score` | siblings only (the circularity comment) | built | band M+Y 0.215 (MEAS §2) | `--arms "head+offset"` | X5, X6 |
| U6 `conditional` | empirical per-sibling-state cluster centres on the fit fold; model fallback under `MIN_PER_CLASS`; `project` where siblings unknown | `unmix._conditional_score` | fit-fold labels per state; the template for P1's ladder | built | band M+Y 0.228 (MEAS §2) — per-state CENTRES on the box mean do not help; the loss is spatial, not spectral | `--arms "conditional+offset"` | X5, X6 |

### 1b. Registration arms (existing; `arms.REGISTER_ARMS`, `arms.register`)

| id | mechanism | hook | labels / blindness | status | measured | isolation | compositions |
|---|---|---|---|---|---|---|---|
| R1 `committed` | the snapshot's pose | `sample.read_rgb` at offset 0 | none | built | — | `--arms "subtract+committed"` | X5, X6 |
| R2 `offset` | blind separable 2-D grid, x ±2 dots then y ±1, step 0.25 (26 reads), objective `fold_logloss` on the SEARCH fold | `arms._search_offset`, `_loss_of` | search-fold labels; fit-fold PAVA inside the objective | built; default | registration moves every state ~0.005 except M+Y (MEAS §2) | `--arms "subtract+offset"` | every X |
| R3 `field` | committed + the snapshot's plane-field delta (page frame); collapses explicitly to committed | `arms.register("field")` | none | built | — | `--arms "subtract+field"` | X5, X6 |
| R4 `field+offset` | R3 then R2 | same | as R2 | built | — | `--arms "subtract+field+offset"` | X5, X6 |
| R5 `affine` | the swim's `local_affine.search` with the correlation-ratio objective (independent of the unmix mode); scored on its own fold | `arms._affine_arm`, `_correlation_score` | search fold; NOTE `_correlation_score` calls `unmix_score` without `fit_mask` (arms.py:417) for `conditional` — a PRE-EXISTING gap, left as is this wave (a fix changes `conditional+affine`'s output and is its own item) | built | band M+Y 0.217 (MEAS §2) | `--arms "subtract+affine"` | X4, X5, X6 |
| R6 `smooth` | per-lane 1-D support-normalised smoothing of R2's solutions over page x; Y only | `arms.smooth_offsets` (deleted) | none | **RETIRED 2026-09-12 (page-field plan A3)** — it was a field keyed by lane and stream with the PAGE dropped from its key, so on a duplex sheet it merged two physical faces; `subtract+smooth` sat in `DEFAULT_ARMS` for sheet J's 1 h 50 m default battery (nothing was corrupted: +39, killed before output) | — | `--arms "subtract+smooth"` now raises `ArmError`; the name is gone from `REGISTER_ARMS` | was in X5, X6 |
| R7 `word` | hard-read the isolated plane at the committed pose, verify the 100-site colour word blind, fit the tile's per-plane pose from 120 sites; C/M only | `arms.word_pose` | furniture only | built | 3 of 4 certified C tiles decode blind (DESIGN §4.6) | `--arms "subtract+word"` | X5, X6 |
| R8 `field2` | the POOLED FURNITURE page field (one fit per page-plane over every lane, certificate-free, generation-invariant) | `field2.field_for(anchors="furniture")` | furniture anchors only | built; since 2026-09-12 (A2) the ONLY `field2` — its rules are its own (clamp `field2.BOUND_DOTS`, the `no_support` refusal), not production's retired floor and clip, and the standalone fit runs for every (page, plane) the run names, M and a duplex page 1 included | Y R +0.0169 at +2.7 SE; strict subset on certificates over 60 tiles (FIELD2-2026-09-03); against production on sheet H, median \|Δx\| C 0.109 / M 0.121 / Y 0.122 dots (PAGE-FIELD-PLAN §B) | `--arms "subtract+field2"` | X5, X6 |
| R9 `field2+offset` | R8 + the NARROW ±1-dot grid around the field's centre | same + `_search_offset(x_range=NARROW)` | as R2 | built | in `everything`; on sheet J `patch+field2+offset` took 25 first-success / 11 only-this-arm and `subtract+field2+offset` 2 / 2 (`J-CONFETTI-2026-09-10.md` §3) | `--arms "subtract+field2+offset"` | X5, X6 |
| R10 `field2c` | the certificate-anchored per-lane page field (a refit per lane per generation) | `field2.field_for(anchors="certified")` (deleted) | certified projections | **RETIRED 2026-09-12 (page-field plan A2)** — the analyzer's last lane-keyed field, and the one whose absence from `controls.FIELD_ARMS` was a latent withholding hazard; 0 first-success on sheet J | was in `everything+field2` only | `--arms "subtract+field2c"` now raises `ArmError` | was in X5, X6 |
| R11 `field2c+offset` | R10 + narrow grid | same | as R2 | **RETIRED 2026-09-12 with R10** | 0 first-success on sheet J | `--arms "subtract+field2c+offset"` now raises `ArmError` | was in X5, X6 |

`parse_arm` partitions at the FIRST `+`, so every P1 head combines with
every R arm automatically once the head is in `UNMIX_MODES`
(`patch+field2+offset` → `("patch", "field2+offset")`).  `select_arm`'s
nested-CV refusal list names only `offset`/`field+offset` today, so
`field2+offset`, `field2c+offset`, `affine` and `word` report a
search-fold minimum as nested CV — B1 widens the tuple to every searching
arm (a pre-existing gap the patch arms would otherwise inherit).

**The roster since 2026-09-12** (the page-field plan's A2/A3/A6; this
enumeration keeps its rows as the record, but three of them no longer
name a live arm).  `arms.REGISTER_ARMS` is `committed`, `field`,
`offset`, `field+offset`, `affine`, `word`, `field2`, `field2+offset` —
`smooth`, `field2c` and `field2c+offset` are gone, and
`calibrate.SEARCHED_REGISTER_ARMS` lost `field2c+offset` with them.  Two
tables key off that roster and both are walked, never spelled by literal:
`arms.FIELD_SOURCE`, which is TOTAL over it — `certified` for the
production `field` family, `furniture` for the `field2` family, `none`
for `committed`, `offset`, `affine` and `word` — is how
`controls.FIELD_ARMS` finds the arms a withholding control must refuse,
over the default battery, every profile's roster and an operator's own
`--arms` battery at call time; and `arms.FIELD_COLLAPSE` (`field` →
`committed`, `field+offset` → `offset`) is what a production `field` arm
BECOMES where the standing field reads zero over the cells it read, so
the row is renamed rather than paid for twice.

### 1c. Context modes (existing; `calibrate.CTX_MODES`)

| id | mechanism | hook | labels / blindness | status | measured | isolation | compositions |
|---|---|---|---|---|---|---|---|
| K1 `none` | no context correction | `calibrate.calibrate(ctx_mode="none")` | — | built | — | `--ctx-mode none` (B5 flag; today `AnalyzerConfig(ctx_mode=…)`) | control |
| K2 `ctx-known` | 9-bin correction where all eight neighbours are KNOWN | `_known_neighbour_bins`, `_apply_context` | halo labels | built | — | `--ctx-mode ctx-known` | — |
| K3 `production` | production's provisional-ink bins (`llr > 0` of the target plane), `context_decision` on fit, validated on search, offsets forced non-increasing | `_production_bins`, `_apply_context` → holo3 `pava._ordered_context_offsets` | fit/search-fold halo labels | built; default (RULED 2026-09-03) | Y re-derived 0/5 without it | default | every X |
| K4 `page` | `PageContext` fitted once per (lane, page, stream) | `arms.page_context`, `_apply_page_context` | 12-tile sample, target excluded | built | — | `--ctx-mode page` | — |
| K5 `local5` | 9-bin fit over the 5×5 neighbourhood blended with the footprint's own by support, re-gated | `arms.local_context`, `_apply_local_context` | 24 neighbour tiles, target excluded | built, not default, no flag | for label-starved bands | `--ctx-mode local5` | optional on any X |

### 1d. Combination rules (existing; `combine.RULES`)

| id | mechanism | hook | labels / blindness | status | measured | isolation | compositions |
|---|---|---|---|---|---|---|---|
| S1 `sum` | equal-weight sum of the de-duplicated lanes | `combine.combine` | none | built | the workhorse rule | `--rules sum` | every X |
| S2 `best` | the one lane with the lowest select-fold loss | `_select_loss` | select-fold labels | built | the only rule that restricts to one capture (README §7) | `--rules best` | every X |
| S3 `platt` | non-negative per-lane weights minimising select-fold log loss (L-BFGS-B); refuses below 40 discriminating minority labels or < 2 lanes → `sum` | `_platt_weights`, `_discriminating_minority` | select fold | built | — | `--rules platt` | every X |
| S4 `corr` | one scale 1/√(1+(L−1)ρ) from the class-centred error correlation | `_error_correlation` | select fold | built | ρ = 0.55 uncentred on independent lanes (the reason for centring) | `--rules corr` | every X |
| S5 `normalized` | mean over lanes | `combine` | none | built, not in DEFAULT_RULES | — | `--rules normalized` | — |
| DC disjoint-capture rule | a second `best` over the complement of the first certificate's captures, or a re-roll restricted to lanes it did not use — the only way the corroboration half of DESIGN §5 can ever fire | a new rule / a re-roll filter over `contributing_captures` | select fold | DESIGN §13 lead, NOT built (§5) | `independent_agreement` ≥ 2 has fired on no real row | — | X5+ |

Leave-one-out over rules is EXACT in the ledger's attribution
(`all_rules=True`, `ledger.attribution`); a new rule (D1) appears in the
tables automatically.

### 1e. Ladder rungs (existing; `ladder._run_rungs`)

| id | mechanism | hook | blindness | status | measured | isolation | compositions |
|---|---|---|---|---|---|---|---|
| L0 `prod60` | bit-exact `cmy8_decode_stream` at 60 + a diagnostic `mother.bp` that must agree | `_rung_production` | gate = syndrome + CRC, charged | built | 254 of sheet H's 508 (DESIGN §6) | `--rungs L0` | every X |
| L1 `prod150` | same at 150 | same | same | built | — | `--rungs "L0,L1"` | every X |
| L2 `bp` | damped@300 λ0.5, layered@300 λ0.7 (measured variants) | knob `L2` (variant dicts) | same | built | damped 151 + layered 65 of 508 | `--rungs L2`; variants `--knob 'L2=[{"mode":"damped","iters":300,"lam":0.5}]'` | every X |
| L4 `flip` | entry at the fewest-unsat L2 state; blind gate unsat ≤ 12; singles over 24 then pairs over 8 at ±LLR_KNOWN; every candidate gated and charged; `certified_list` | `_rung_flip`, `_flip_source` | list rung, quarantined from the zero-wrong claim | built | 11/59 synthetic, 2 on H per pass | `--rungs "L2,L4"` | every X |
| L3 `ctx-iterate` | APPLY mode: the footprint's offsets re-applied at bins from the decoder's clipped extrinsic; ≤ 3 rounds; abort on LLR growth without unsat gain | `_rung_ctx_iterate`, `_ctx_shift` | needs `ctx_offsets` (9-vector); exact only for a POOLED correction — refuses `state_context_adopted` when C2 adopted a per-state residual in a contributing lane (B2) | built; certified nothing yet | — | `--rungs "L1,L3"` | every X (refuses under C2 where adopted) |
| L7a `erase-disagree` | erase (factor) the least-agreeing cells from `Combined.agreement`, capped at n−k−margin | `_rung_erase_disagree` | needs ≥ 2 lanes | built; certified nothing yet | — | `--rungs "L1,L7a"` | every X |
| L7b `erase-runs` | erase contiguous runs of low-\|posterior\| positions (quantile 0.10) | `_rung_erase_runs` | — | built; certified nothing yet | — | `--rungs "L1,L7b"` | every X |
| L5 `osd` / L6 `perturb` | ordered-statistics / seeded restarts | stubs raise `DeferredRung` | — | DEFERRED (DESIGN §6.1) | H's shoulder is inside L4's reach | — | — |
| DM defect map → erasures | oracle-guided discovery of clustered wrong cells (fibres, splatter), then a BLIND anomaly detector against the local model marks them erased — the L7 producer DESIGN §13 still owes | a producer for L7a's `factor`/positions | blind detector | DESIGN §13 lead, NOT built (§5); C3 is a different, state-keyed producer and does not disposition it | — | — | — |

Leave-one-out over RUNGS is a lower bound (the ladder stops at the first
certificate); isolate a rung by `--rungs` subsets.

### 1f. Drivers, profiles, controls and offline tools (existing)

| id | mechanism | hook | status | measured | isolation | compositions |
|---|---|---|---|---|---|---|
| RR re-roll | after the selected arm's ladder fails, every unselected arm's evidence gets its own combination per rule at `reroll_rungs`; `certifying_arm = reroll:<arm>` | `combine.reroll_sets`, `fixedpoint.blind_key` | built, default ON | ~240 of H's 508 (DESIGN §6.2) | `--no-reroll` (B5) is the control; on = the per-arm attribution channel (`certifying_arm` reaches the ledger from B1) | every X |
| RR2 the PLACEMENT | an arm named in `reroll_only_arms` is computed inside the re-roll block and NOWHERE else: a key the battery closes never pays for it, and it can never be a selection candidate, so it cannot displace an arm measured against the pinned default.  It amends the union ruling on WHO PAYS, not on what may be added (DESIGN §6.2) | `AnalyzerConfig.reroll_only_arms`, `reroll_battery_for`, `fixedpoint.blind_key`'s re-roll block; header `reroll_only_arms`, row `reroll.deferred` | BUILT (B8; the CLI door `--reroll-only-arms` B5) | untested on paper | the same profile with and without the flag: the difference is the placement's yield, and in certificates it cannot be negative | X10, X11 |
| PR1 `wide-halo` | halo 48/48/32 | `PROFILES` | built | +3/−1 on H's C sample (failed the no-regression gate) | `--profile wide-halo` | in X1–X5 |
| PR2 `battery` | all rules and rungs, reroll on | `PROFILES` | built | 7 of 11 missed keys at 4× cost | `--profile battery` | — |
| PR3 `split-branches` | the pre-amendment two-population calibration (`branches="subtract"`, no starved fallback) | `PROFILES` | built | control only | `--profile split-branches` | control |
| PR4 `everything` | every default arm + `field2` arms, all rules, full ladder, halo 48/48/32, reroll L0–L2 | `PROFILES` | built | the union ruling (DESIGN §6.2) | `--profile everything` | ⊂ X5 |
| PR5 `everything+field2` | PR4 + `field2c` arms | `PROFILES` | **RETIRED 2026-09-12 (page-field plan A2)**, with the two `field2c` arms it existed for; `everything+patch` (and `everything+patch+pure` through it) is REBASED on `everything` and differs from its old roster by exactly those two arms | — | `--profile everything+field2` now exits on `KeyError: unknown profile` | was ⊂ X5 |
| X6 fixed point | the cascade: every certificate re-targets its 8 neighbours and sibling streams; each generation re-attacks with the enlarged frame | `fixedpoint.run`, `_retarget` | built | +52 of 331 (I), 234 of 508 (H) | `--fixed-point --max-generations 8` | X6 |
| CT controls | DESIGN §8: `null_arm` (donor pixels ≥ 8 tiles away climb the FULL ladder at the same knobs), `frame_null` (certificates shifted → wrong labels AND wrong sibling states; `matches_production` reported), `parity_sample` (≥ 80 % per stream), `positive_control`, `stratified_holdout` | `controls.py`; `analyzer controls --run-dir … [--profile …] [--arms/--rules/--rungs] [--knob …]` (B1 gives it `--knob`) | built | "a run without these is not a result" | `CONTROLS --profile <p> --null 5 --frame-null 3 --parity 100`; the K rows of §3 | every X, before its numbers are recorded |
| PV1 whole-page plane view | holo3's own placement/refine/swim/region-ctx/union/cascade on an emitted unmixed C plane | `planeview/` (`analyzer emit-plane`, `analyzer plane-view-decode`) | built and RUN — a MEASURED NEGATIVE | 1,632 C certified from scratch, zero plane-view-only certificates, 122 production C tiles missed, cols 30–31 0/0 (DESIGN §13) — the only other approach ever run on exactly this residue | `$PY -m analyzer emit-plane …` then `plane-view-decode …` (cli.py) | — |
| PV2 seeded plane views | seed the plane view with every known certificate of the stream so holo3's cascade works the residue only | `planeview/` + `--holo3-option --max-pages 1` | owed (DESIGN §13; the unseeded run's 787 `cold_rest` windows, 12–15 h projected, are the reason) | — | `plane-view-decode` with the seed option (cli.py) | — |
| T-score | offline truth-scored cell error / d′ / AUC / R of ONE arm per (lane, row), by sibling state; PER LANE — there is no combined-lane number in the scorer (`evidence_for_row` scores each lane on its own; `waterfall_rows` reports the BEST lane's R) | `score.evidence_for_row`, `oracle.score_evidence` | built | the door every single-lane MEAS number came through; the combined-lane numbers came through `measure/…/analyze_combined.py` over the per-cell dumps | `SCORE --arms "<arm>" [--knob …]` (B1) | measurement |
| T-union / T-export | union base run dir; facts snapshot with the analyzer's certificates for a holo3 resume | `unionbase`, `export_facts` | built | H14-union = the previous base (5,579) | README §2.5/§2.7 | after a pass |
| T-close | `close_volume` on the union; `--localize` names a poisoned symbol | `close` | built | H verified 0.66 s | `analyzer close --run-dir $RUN --localize` | after a pass |
| T-read / T-report | `read` (evidence without a ladder — it ladders under a profile, README §7) and `report` | `cli` | built | — | README §2 | — |

### 1g. New in W8

Label supply, measured from the census columns of the H14-C ledger
(`known_cells_in_halo`, computed at `HALO_CELLS["C"]` = 16 — `cli._census`
does not pass the run's halo): dead median 1,768 (p10 529, min 232),
marginal 2,511 (min 1,027), live 2,759 (min 1,472).  The halo-48 ring is
4.2× the halo-16 ring in area, so a dead-band footprint at halo 48 holds
of order 7,000 known cells, ≈ 3,500 on the fit fold, ≈ 800 per sibling
state — and word sites (100/tile, states {0, 3} of the eight) feed only
sibling states 0 and 1 of C, so states 2 and 3 are labelled by certified
projections and ~13 dust cells per tile alone.  At 8 samples per cell (144
features) that is ≈ 5 labels per feature for the state-3 filter; at 16
(576 features) ≈ 1.4.  The measurement's own floor was 300 labels at 576
features (n/p ≈ 0.5) and produced the 0.119; the ridge (λ = 1e-2 after
standardisation) is what makes n < p well posed, and ruling 7 (cross-fit)
is what makes the calibration honest at any n/p.  ~~S12 sweeps the floor
so it is pinned by measurement, not taste~~ — WITHDRAWN by the
self-discovery ruling (§4.0): S12 is a measurement on one sheet (§6.2,
and it is confounded), and B7 replaced the count with an admission on the
tier's own cross-fit numbers.

| id | mechanism | hook | labels / blindness | status | measured (truth, offline) | isolation | compositions |
|---|---|---|---|---|---|---|---|
| **P1** `patch` | per (lane, plane, sibling-state) linear discriminant over the pose-resampled raw patch (window 1.5 cells, `patch_samples_per_cell` samples per cell, red only), standardised shrinkage-LDA λ = 1e-2, threshold at the class-mean midpoint; CROSS-FIT inside the fit fold (ruling 7); every population's score scaled by its own out-of-fold sd so the pieces share one scale; ladder per-state → state-agnostic (B3) → `subtract`; presence high = ink | NEW `analyzer/patch.py` (`patch_score`), dispatched from `arms.evidence_for` at the `unmix_score` seam; `Crops.raw_rgb` (opt-in `keep_raw`), `Read.points_yx`/`linear_by_owner` | fit-fold labels of the footprint (the supply above): certified neighbours' projections, dust, metadata cell — word sites are EXCLUDED from the per-state fits (one target class per state at a word site) and reported; states from `frame.siblings`; NEVER the target plane's own bit; detail `patch_labels_from="halo"` | BUILT (B1) | band M+Y 0.208 → 0.149 single lane (tile-parity CV); halo-trained on whole edge tiles, no target label: 0.203 → 0.119 single, 0.191 → 0.062 combined (the combined figure is `analyze_combined.py`'s, reproducible only through the S9 dump route); ordinary cells 0.075 → 0.028; permutation control 0.46 (MEAS §4, §5b).  **MEASURED BLIND on sheet H 2026-09-06 (§6): 96 certificates of 153 open C rows against the pinned default's 0, 0 wrong; the select fold adopted it over the default on 527 of 531 dead-band (lane, row) pairs; truth-scored dead-band M+Y 0.2428 -> 0.1620 (16 samples/cell), 7 of 7 lanes past 2 SE in every band** | `LADDER --arms "patch+offset" --halo-cells 48 --out …/I1`; `SCORE --arms "patch+offset" --halo-cells 48` (read with `BYSTATE`) | X1–X6 |
| P1a red-only | `patch_channels="r"` (the measured variant) | `PatchSpec.channels=(0,)` | as P1 | BUILT (B1, the inherited fallback) | the MEAS numbers | default | X1–X6 |
| P1b RGB | `patch_channels="rgb"`: 3× features | `PatchSpec.channels=(0,1,2)` | as P1 | BUILT (B1, a knob) | untested (QDA on RGB box means 0.194 vs red threshold 0.208, MEAS §4 — a small spectral term exists) | `--arms "patch+offset" --knob patch_channels=rgb` | variant of X1 |
| P1c `rings` | radial-mean features (one per 1/S-cell ring) instead of pixels — the cheap, shift-robust variant | NEW mode `"rings"` in `patch.py` | as P1 | BUILT (B3) | **MEASURED S4 (§6.2): a NEGATIVE on the state it was meant for.** Dead-band M+Y 0.2428 -> 0.2627, 0 of 7 lanes falling and 7 of 7 RISING; ordinary states improve (dead R 0.748 -> 0.712 is worse overall).  Radial means average away exactly the flat-vs-dot distinction MEAS §3 measured | `--arms "rings+offset"` — S4 | X5 (in the battery) |
| P1d state-agnostic | one filter over all labelled cells regardless of state, for cargo whose siblings are unknown (the open-Y live/marginal tiles) and for states under the floor; its OWN floor knob | `patch.py` tier 2, `patch_min_labels_agnostic` (default 200) | as P1, state ignored | BUILT (B3; B1 fell straight to `subtract`, which is what S1 measured) | **MEASURED S10 (§6.2), and it decomposes the tier ladder**: alone (per-state floor forced to infinity) it takes dead-band M+Y 0.2428 -> 0.2313 (3 of 7 lanes) but the LIVE band 0.1009 -> 0.0729 (7 of 7).  So the agnostic tier is what fixed S1's live regression, and the per-state tier is the M+Y mechanism | `--knob patch_min_labels_per_state=1000000` forces it everywhere (the agnostic floor is separate, so this isolates P1d and not P1f) — S10 | X1–X6 on open-Y tiles |
| P1e window | `patch_window_cells` 1.5 (measured) / 1.0 / 2.0 | `PatchSpec.window_cells` | — | BUILT (B1, a knob) | 1.5 measured; 2.0 needs the grown `bound_dots` (B1 grows the crop by the half-window) | `--knob patch_window_cells=2.0` — S1d | variant |
| P1f fallback | `subtract` where nothing fits (a state under `patch_min_labels_per_state` = 200 or min class < `MIN_PER_CLASS` = 25, and the agnostic tier under its own floor), and for rows outside the crop | `spectral.plane_score(MODE_SUBTRACT)` | — | BUILT (B1) | — | recorded per cell in `patch_fallback_cells`; `--knob patch_min_labels_per_state=1000000 --knob patch_min_labels_agnostic=1000000` forces it | — |
| P1g train scope | `patch_train_scope="footprint"` (default) or `"local5"`: the 5×5 neighbourhood's own certified cargo via `unmix._sample_frame`, features memoised per (lane, tile) with a row cap and an LRU bound — the estimator closest to the measurement's (whole edge tiles of the same lane) | `patch.local_patch_labels`, memo in `inputs._cache` | neighbour tiles' full certificates; target tile excluded | BUILT (B3) | per-lane training 0.119 vs pooled-across-lanes 0.196 (MEAS §5b): the scope stays per lane | `--knob patch_train_scope=local5` — S11 | X5 option |
| P1h cross-fit | the fold ruling made mechanism: fit-fold labels split in halves by `fold_hash(cells, seed ^ CROSSFIT_SALT)`, each half scored by the other's filter, PAVA/search objectives see only out-of-fold scores; the in-sample vs cross-fit fit-fold error gap is a ledger column | `patch.crossfit_scores`; detail `patch_fit_error_insample`, `patch_fit_error_crossfit` | — | BUILT (B1, always on) | the measurement never calibrated in-sample (tile parity, Platt on other tiles); this is what lets its numbers transfer | `patch_fit_error_*` on every patch row; no off switch | X1–X6 |
| **P2** self-training | after the halo fit, pseudo-label the tile's own CARGO cells (per state where known, else all; never a row that is `frame.known` in the target plane — the metadata cell) from the `patch_selftrain_keep` = 0.6 most confident by \|score\| percentile, weight 2.0, `patch_selftrain_rounds` = 4 refits; deterministic (percentile threshold, no RNG) | `patch.patch_score(extra_labels=…)`, rounds inside | the tile's own confident cells, recorded `patch_labels_from="halo+self"`, `pseudo_source="self"`; fit set only | BUILT (B3) | 0.119 → 0.114 single, 0.062 → 0.060 combined (MEAS §5b): small.  **MEASURED S2 (§6.2): small and REAL** — dead 0.0704 -> 0.0654 err, R 0.847 -> 0.855, M+Y 0.1659 -> 0.1639, and 7 of 7 lanes past 2 SE against S0 in both the dead and the live band.  The best row at 8 samples per cell | `--arms "patch+offset" --knob patch_selftrain_rounds=4` — S2 | X2–X6 |
| **P3** `L3f` decoder-feedback refit | a rung after BP fails: confident extrinsic bits (\|extrinsic\| ≥ `refit_confidence_llr` = 4.0, index 0 excluded) become a typed `PseudoLabels(source="decoder")` at their page cells; the chosen lanes' evidence is recomputed with them (patch filter refit; PAVA refit when `refit_calibration`), recombined under the rule with the ROUND-0 label view (coefficients unchanged), BP runs again; `refit_rounds` = 2; a per-key budget `refit_max_evidence` = 26 evidence recomputations; every consult charged; stops on a certificate, no unsat gain, or the budget | NEW `analyzer/refit.py` (`rung_feedback`, `refit_evidence`); `ladder._run_rungs` dispatch; `fixedpoint.blind_key` binds `rule_knobs["refit"]`; the `pseudo_labels` door in `arms.evidence_for` accepts only `PseudoLabels` | BP's own extrinsic, recorded `pseudo_source="decoder"`, `n_pseudo_labels`; fit set only; `frame.known` never written | BUILT (B4) | proxy (25 % true bits, weight 3): 0.085 single, 0.049 combined (MEAS §5b) — the blind rung's yield may differ.  **MEASURED BLIND I6 (§6.1): it certifies.**  153 open C rows, `subtract+offset,patch+offset` with `branches=state` and the ladder L0,L1,L2,L3f: **102 certificates, 0 wrong**, and `L3f.r0` is the first-success rung on 31 of them — with L4, L3 and L7 absent from that ladder, against 96 for the same two arms WITH those rungs and without L3f (I2).  563 L3f rows ran, 43 certified, 190 exited `syndrome_failed`, 332 refused; only 2 rows ever reached round 1 | `LADDER --arms "subtract+offset,patch+offset" --rungs "L0,L1,L2,L3f" --knob refit_rounds=2` — I6 | X3, X4, X6 (X5 only with an explicit `--rungs`, cost) |
| **C1** `branches="state"` | one PAVA map + own standardisation per sibling state (s0–s3) plus `other` where siblings unknown; the per-state TRAIN sets exclude word-site rows (dust kept) and report furniture vs cargo counts; starved states priced by the pooled map (`branch_fallback`) | NEW `analyzer/statecal.py` (`state_branch_masks`, `state_fit_masks`); `calibrate.branch_masks` dispatch; `covered_cells` follows; `BRANCH_*` constants move to `types.py` (no import cycle) | fit/search-fold labels per state | BUILT (B2) | per-(lane, state) Platt blind: band combined 0.088 → 0.076, R 0.797 → 0.836 (MEAS §4) | `LADDER --arms "subtract+offset" --knob branches=state` — I3; `SCORE … --knob branches=state` — S7 | X1–X6 |
| **C2** `ctx_state=True` | after the pooled context fit, a per-state 9-bin correction with production's solver and floors (80/20 search, 40/10 validation), pooled offsets where a state refuses; publishes the pooled 9-vector under `ctx_offsets` (`pooled_ctx_offsets` keeps its contract) and `ctx_offsets_by_state` (4×9) beside it; the second `apply_context_offsets` pass re-clamps adopted states at ±12 (documented); L3 refuses on a row where a state was adopted | `statecal.apply_state_context`; `calibrate.calibrate(ctx_state=)`; `Combined.ctx_state_adopted` | halo labels per state × bin | BUILT (B2) | per-(lane, state, context) oracle 0.059 vs 0.066 per-(lane, state) (MEAS §4) | `--knob branches=state --knob ctx_state=true` — S8/I3 | X1–X6 |
| **C3** `L7c` state-targeted erasure | erase (factor `erase_factor` = 0) the cells of sibling state `erase_state` = 3 with \|L\| < `erase_tau` = 2.0, least confident first, capped at n−k−margin; below-floor reproduced | `ladder._rung_erase_state` (twin of L7a, in ladder.py); `rule_knobs["sibling_state"]` from `blind_key` | the sequential sibling-state vector (from the frame, no decoder output) | BUILT (B2) | untested; the over-confidence on M+Y is what it targets | `--rungs "L0,L1,L2,L7c"` — I5 | X1–X6 (own name, NOT under the `L7` alias) |
| **D1** `platt-state` | pooled Platt weights first, then per sibling state where the state's OWN min(n0, n1) on the select fold ≥ 40 (not the degenerate discriminating-minority count); `llr = Σ_s [state==s]·(w_s@stack) + [state<0]·(w_pooled@stack)`; `Combined.coefficients` = pooled, `coefficients_by_state` added; `contributing_captures` = the UNION of supports over the pooled vector and every per-state vector | `combine.combine(rule="platt-state", sibling_state=)`, `statecal.state_platt_weights`; `calibrate` publishes `label_state`; `controls` hands the state too | select fold per state | BUILT (B2) | the "final per-tile Platt" of MEAS §5 is its offline stand-in | `--rules "sum,platt,platt-state"` — I4 | X1–X6 |
| **M1** `mixture` | blind per-(tile, lane, state) two-Gaussian mixture on the red channel (deterministic init at the 30th/70th percentiles, 20 EM steps) for state-3 cells only; `subtract` elsewhere | NEW mode `"mixture"` in `patch.py` | the tile's own state-3 population; no labels | BUILT (B3, supplemental) | band M+Y 0.219 → 0.190, worse elsewhere (MEAS §4).  **MEASURED S5 (§6.2) and it reproduced its own offline prediction almost exactly**: dead M+Y 0.2428 -> 0.2170 with 7 of 7 lanes past 2 SE, and 0 of 7 in the live band (+0.000 to +0.003).  A label-free supplement that helps ONLY the three-ink cells of the dead band | `--arms "mixture+offset"` — S5 | X5 (in the battery; it is expected to lose the select-fold comparison and be reached through the re-roll, and a supplemental arm of this shape is exactly what the PLACEMENT, P0d, was later built for) |
| **A7** aperture | `aperture_cells` (0.7 = production; 0.5 and 1.0 measured) and `aperture_kind` `box`/`gaussian` on the crop filter at 16 px/cell; defaults byte-identical; the crop halo grows with BOTH width and kind (a gaussian truncates at 4σ) | `sample.open_crops(aperture_cells=, aperture_kind=)`, knob read in `evidence_for` | none | BUILT (B3) | untested; the flat-deficit profile PREDICTS a smaller aperture loses and a wider one gains on M+Y (MEAS §3) — S6 measures it | `--arms "subtract+offset" --knob aperture_cells=0.5`, `=1.0`, `--knob aperture_kind=gaussian` — S6 | variant |
| A7b deconvolution | a Wiener deconvolution from the sheet's own certified edges (MTF10 ≈ 860 dpi) before sampling | a sheet-wide PSF, `sample._filtered_rgb` | certified edges | DESIGN §13 lead, NOT built (§5) — the patch filter is a learned aperture and contains a linear deconvolution of the patch | — | — | — |
| **E2** patch-objective search | `patch_search_mode="patch"`: the OFFSET GRID evaluated under the patch objective (26 extractions + fits per lane, cross-fit each); default `"subtract"` searches under `subtract` and applies the patch at the winner (exact for a linear filter, 1 extraction).  The affine swim and the word pose ALWAYS search under `subtract` for patch modes (their objectives run over fit ∪ search rows, half in-sample for a fitted score) | `arms._search_offset`/`_loss_of` take `context=(crops, read, lfp, folds, spec)`; `_affine_arm`/`word_pose` substitute `subtract` for a patch mode | search fold | BUILT (B3) | untested | `--arms "patch+offset" --knob patch_search_mode=patch` — S3 | X4 option (offset grid only) |
| **P0** the pure path | the page-field pose with NO search (`patch+field2`, which collapses to the committed placement where no field covers the tile), the B1 filter trained over the 5x5 neighbourhood's certified cells, and ONE error rate per (lane, plane, sibling state) as the log-odds — `llr = sign(score - threshold) * log((1-e)/e)`, `e` clamped to [0.01, 0.45].  **F2 (2026-09-06, rulings R2/R3 on §6.5): `e` is the TILE'S OWN.**  The discriminant's scores on the tile's cargo cells of that state are two populations in the code's own proportion (the keystream whitens the cargo, so the priors are 1/2 and 1/2 and FIXED); an equal-prior two-Gaussian fit on them (percentile init, 50 EM steps, no RNG — `patch`'s mixture recipe with the priors held) gives the error of the hard decision at the threshold on exactly the cells being decoded.  The halo's cross-fit held-out error (half A's class-mean midpoint prices half B and vice versa) is a FLOOR — `e = max(e_self, e_halo)` — never the price; the threshold is the halo's midpoint (the discriminant's own centring) and the fit's own boundary is published beside it.  A state whose halo cannot measure a floor takes the pooled halo's threshold and floor (a pool of KNOWN-state rows only, §6.8); a state with too few cargo cells to fit its own populations takes the TILE-POOLED self fit at its own threshold — smeared across the states, so pessimistic, and still the tile's; a cell whose SIBLING STATE IS UNKNOWN is an ERASURE (LLR 0, counted), priced by nothing and counted into nothing.  NO PAVA, no context, no Platt, no refit between the filter and BP.  The user's question: "we already have every tile addressed, the correct page field and mostly correct poses per plane - there is no justification for pushing that through PAVA, ctx, Platt; just try it out either way" | NEW `analyzer/pure.py` (`pure_llr`, `measure`, `self_fit`, `error_at`), knob `calibration=pure`; it publishes the same `label_*` arrays, so `select_arm` and the rules are unchanged | the tile's own cargo SCORES (no label, no fold) for the price; the 5x5 neighbourhood's certified cells + the tile's certified SIBLING planes (never the target plane's own bit), fit fold only, for the floor and the threshold; `pure_price_by_state` (self / floor / adopted), `pure_price_source`, `pure_error_by_state` with BOTH halves' rates, `pure_erased_cells`, `pure_unknown_state_cells` in the blind detail | BUILT (B6), RE-PRICED (F2) | untested on paper as re-priced — §6.5's smoke ran the halo-priced B6 version (1 of 8 dead-band rows, the defect §6.7 records); synthetic: a 5/15/25 % Bayes overlap on the tile is read within 0.02/0.03/0.04 with the halo at 1 %, a permuted filter reads its own tile at 0.29-0.36 and is capped, and unknown-state cells leave at LLR 0 | `--profile pure`; the control is the SAME arms/halo/knobs/rules/rungs through the map (`--knob calibration=pava`) | X7-X9 |
| P0a `pure_soft` | the log-odds scaled by the standardised score clipped at 3 sd — a magnitude, not just a sign | `pure.pure_soft` | as P0 | BUILT (B6, a knob) | untested | `--profile pure --knob pure_soft=true` | variant of X7 |
| P0b the error band | `e` clamped into [`pure_error_floor`, `pure_error_ceiling`]: a population that measures 0 errors on a few hundred rows has not proven certainty (the floor caps \|llr\| at log 99), one at the ceiling has not proven a direction (0.20 nats, what a collapsed filter is worth) | `PureSpec` | — | BUILT (B6); NOT a sheet-H number - a refusal to over-claim, pinned by tests at both ends | untested | `--knob pure_error_floor=0.02` | variant of X7 |
| **P0c** `pure` as an unmix MODE | the knob `calibration=pure` prices whatever arm carries it; the MODE makes the pure path an ARM — `pure+committed` computes bit for bit the score `patch+committed` computes and differs in the single stage between the detector and BP, so the two can sit in ONE battery and be arbitrated by the select fold, and the ledger attributes the winner by name | `pure.is_pure` gained an arm-scoped door beside B6's knob-scoped one; `"pure"` in `unmix.UNMIX_MODES`, so `parse_arm` takes `pure+<any register arm>` | as P0 | BUILT (B8) | untested on paper | `--arms "patch+committed,pure+committed"` (one battery, the select fold decides) | X10, X11 |
| **P0d** the PLACEMENT (`reroll_only_arms`) | an arm computed inside the RE-ROLL block and nowhere else: a key the battery closes never pays for it, and it can never be a selection candidate, so it cannot displace an arm that was measured against the pinned default.  The user's ruling: "only run it after the other pass has done its job — in case it does show incremental gains".  It amends the union ruling on WHO PAYS, not on what may be added (DESIGN §6.2) | `AnalyzerConfig.reroll_only_arms` + `reroll_battery_for`; `fixedpoint.blind_key`'s re-roll block; header `reroll_only_arms`, row `reroll.deferred`, `certifying_arm = "reroll:<arm>"` | none of its own | BUILT (B8; the CLI door `--reroll-only-arms` B5) | untested on paper | `--profile patch-refit --reroll-only-arms "pure+committed,pure+field2"` against the same profile without it: the difference is the placement's yield and cannot be negative in certificates | X10, X11 |
| **P0e** the resampler economy | the `auto` walk's repeated extractions removed EXACTLY, not approximately: `inside_mask` (which rows fit the crop is arithmetic on the extreme offsets, IEEE addition being monotone in its addend), `FeatureBank` (a narrower window is a centred SLICE of a wider one at the same sampling; `r` is the leading block of `rgb`; `rings` is a matrix multiply), and `Moments`/`fit_from_moments` (the normal equations are additive over disjoint row sets and sliceable in the feature axis, so one Gram per (population, cross-fit half) prices every window, both channel sets, both feature kinds and every shrinkage) | NEW `analyzer/patchcache.py`; `autoknobs.fit_from_moments` | none | BUILT (B8) | synthetic: 27 extractions -> 4, 22.7 M resampled points -> 5.8 M, 2.50 s -> 1.12 s at 144 features (the smallest case, where the samples axis collapses); with nothing `auto` the module is B1/B3's own path, byte-identical (pinned).  `map_coordinates` deliberately NOT replaced: a hand bilinear measured 2.1x faster but is not bit-identical and every number on disk was read through it | the byte-identity pins in `test_analyzer_patch.py` / `test_analyzer_autoknobs.py`; on paper, the wall of any patch run | all |

### 1h. DESIGN §13 leads (cheap, untried) and the leads that compose with W8

| id | mechanism | hook | labels / blindness | status | measured | isolation | compositions |
|---|---|---|---|---|---|---|---|
| **T1** temperature ladder | scale the combined LLR by t before BP (multi-lane sums on a print-frozen channel are over-confident); an L2 variant field `temperature` | `ladder._run_rungs` L2 branch: `to_mother(llr_seq·t)`, rung label `L2:damped@300@t0.8` | none | BUILT (B4) | **MEASURED I7 (§6.1): 0 certificates** on the 153 open C rows — but the arm was the pinned default, which mints 0 there anyway (I0), so I7 measures that T1 does not RESCUE a channel the detector cannot read, and says nothing about T1 over a patch channel | `--rungs "L0,L1,L2" --knob 'L2=[{"mode":"damped","iters":300,"lam":0.5,"temperature":0.8},{"mode":"damped","iters":300,"lam":0.5,"temperature":1.25}]'` — I7 | X5 option |
| **T2** pose-list decoding | decode at the top-3 offsets of the search (3 consults per tile) | `register` would return several reads; `_search_offset(profile=True)` already has the losses | search fold | lead, NOT built (§5) | untried | — | — |
| **J1** joint three-stream turbo | where C and Y are both open (the open live/marginal C tiles), feed each stream's clipped extrinsic as SOFT siblings into the other's unmixing/patch state and iterate the decodes | a two-key rung over `(ty, tx, "C")` and `(…, "Y")`; `patch.py` would take soft states | decoder extrinsic of the sibling stream | lead, NOT built (§5); the mechanism that would give P1's per-state tier something on the 27/33 live rows whose Y is open | untried | — | X3+ |
| **N1** neighbourhood colour head | the 8-state mixture fitted on 5×5 tiles with per-context means, shrunk to a lane-page prior | `unmix._head_score` + the `local_context` memo | 24 neighbour tiles | lead, NOT built | untried | — | X5 |
| **N2** full neighbour-interaction context | 256-context (or 3×3 linear) toner model instead of 9 bins; unknown neighbours from the extrinsic (turbo) | `calibrate._apply_context` successor | halo labels | lead, NOT built; the measured "error falls with more C-inked neighbours" (MEAS §3) is the case the non-increasing 9-bin solver cannot express | untried | — | X1+ |
| **R12** per-channel registration | sample R, G, B at their own positions (e033's Canon R−G lateral CA, odd-symmetric) | `sample.read_rgb` per channel | labels | lead, NOT built | untried | — | X4+ |
| **MF** M's page field | `field2` is fitted for C and Y; M is unfitted and `head+field2+offset` untested | `field2.field_for` for plane 1 | furniture anchors | **CLOSED 2026-09-12** by the page-field plan's A2/A5 — `sweeps/field2_paper.phase_c` lost its `("Y", "C")` hardcode and fits one pooled field per (page, plane), M included.  Production's M is `−C` to the bit under the gauge, so an independently fitted M IS the first M reference the receiver did not make, and it is the gauge's first test on paper outside the receiver's own suite | sheet H, production vs `field2` M: median \|Δx\| 0.121 / \|Δy\| 0.093 dots, Spearman 0.659, sinusoid amplitude 0.187 (production) against 0.190 (analyzer) at 17.10 against 17.00 tiles — the sinusoid is NOT common-mode and the gauge does not distort it; sheet J carries M on both faces.  PAGE-FIELD-PLAN §B | `--phase C` on a converted corpus (README §2.1b) | X5+ |

### 1i. Format-axis and physical items — enumerated for the record, NOT built

| id | mechanism | why it is on the list | status |
|---|---|---|---|
| F1 C one rung down | the C plane's third-layer loss is sheet-wide (~0.10–0.21 on a quarter of its cells), so C wants the rung margin as much as Y (MEAS §6) | format axis: new row, layout bump | not built |
| F2 a cmy8-presence row that never prints CMY | cmy7's state set with cmy8's independent per-plane codec: the three-ink state disappears | new row; coding work | not built |
| F3 a modulation constraint against isolated C dots on M+Y | targets the worst case (isolated C on a pile, 0.33) | coding-theory work | not built |
| F4 Y at r0775 | the column-group pool already rules r0850×r0850×r0775 (CLAUDE.md) | printed on a future sheet | not built |
| F5 lower q | ink density dial; q 0.9 on sheet H | next print day | not built |
| F6 targeted evidence: more 4800 captures, crosswise sheets, 4800 strips of the marginal regions, 16-bit linear output for faint Y | e034: one added 4800 capture bought 14 of the last 17; the patch filter's residual errors are capture noise and average out (MEAS §5); DESIGN §13's "targeted evidence" row (the Hend snapshot's six extra lanes are the nearest instance) | physical | not run |
| F7 the toner order check | is C really laid third? (MEAS §3 mechanism, unverified) | discovery print | not run |

## 2. The compositions

Profiles are the composition door (`types.PROFILES`, `with_profile`); a
profile records itself in the ledger header as `knobs_from =
"profile:<name>"`, and from B1 the header also carries `knobs`, `reroll`
and `reroll_rungs`, so knob-only variants (X1 vs X2) are distinguishable
on disk.  `subtract+offset` stays FIRST in every profile so `select_arm`'s
default (the pinned arm) is unchanged.  `L7c` and `L3f` are their own rung
names — neither rides the `L7` alias, so no existing profile changes
behaviour.  ~~There is no reroll-only arm list: every arm in `arms` is a
selection candidate, and the re-roll takes the sets the selection did not
use.~~ — the second sentence stands, the first is SUPERSEDED by B8: an
arm named in `AnalyzerConfig.reroll_only_arms` is PLACED, computed inside
the re-roll block and nowhere else, and can never be a selection
candidate (X10/X11 below).  The header carries `reroll_only_arms`,
`--reroll-only-arms ARM[,ARM]` is the one-pass door, and an arm is a
candidate unless it is placed.

```python
_PATCH_ARMS = ("patch+offset", "patch+committed")
_STATE_KNOBS = {"branches": "state", "ctx_state": True}

PROFILES["patch"] = {                                         # X1
    "arms": ("subtract+offset",) + _PATCH_ARMS,
    "rules": DEFAULT_RULES + ("platt-state",),
    "rungs": ("L0", "L1", "L2", "L4", "L3", "L7", "L7c"),
    "reroll": True, "reroll_rungs": ("L0", "L1", "L2"),
    "halo_cells": {"C": 48, "M": 48, "Y": 32},
    "knobs": dict(_STATE_KNOBS)}
PROFILES["patch-self"] = {**PROFILES["patch"],                # X2
    "knobs": {**_STATE_KNOBS, "patch_selftrain_rounds": 4}}
PROFILES["patch-refit"] = {**PROFILES["patch-self"],          # X3
    "rungs": ("L0", "L1", "L2", "L4", "L3", "L3f", "L7", "L7c"),
    "reroll_rungs": ("L0", "L1", "L2"),                       # L3f NOT in the re-roll (cost; B4)
    "knobs": {**_STATE_KNOBS, "patch_selftrain_rounds": 4,
              "refit_rounds": 2, "refit_max_evidence": 26}}
PROFILES["patch-affine"] = {**PROFILES["patch-refit"],        # X4
    "arms": ("subtract+offset",) + _PATCH_ARMS + ("patch+affine",
                                                  "subtract+affine")}
PROFILES["everything+patch"] = {                              # X5
    "rules": DEFAULT_RULES + ("platt-state",),
    "arms": PROFILES["everything+field2"]["arms"] + _PATCH_ARMS
            + ("patch+field2+offset", "patch+affine", "rings+offset",
               "mixture+offset"),
    "rungs": ("L0", "L1", "L2", "L4", "L3", "L7", "L7c"),
    "reroll": True, "reroll_rungs": ("L0", "L1", "L2"),
    "halo_cells": {"C": 48, "M": 48, "Y": 32},
    "knobs": {**_STATE_KNOBS, "patch_selftrain_rounds": 4}}
```

The profiles AS BUILT differ from the sketch above in one way, and it is
the self-discovery ruling: every geometry knob of the patch family is
`"auto"` in `_STATE_KNOBS`, not a number.  They differ in a SECOND way
since 2026-09-12 (page-field plan A2/A3): the sketch's
`PROFILES["everything+field2"]["arms"]` reads
`PROFILES["everything"]["arms"]` today — the base profile retired with
the two `field2c` arms — and `DEFAULT_ARMS`, which `everything` is built
from, no longer carries `subtract+smooth`.  So `everything+patch` and
`everything+patch+pure` are three arms lighter than the rosters the
sheet-H and sheet-J records were minted under, and `types.py` says so at
the collapsed literal.  And the pure path (P0) has three profiles of its
own — X7, X8, X9:

```python
_PURE_ARMS = ("patch+field2", "patch+committed")   # no offset search
_PURE_KNOBS = {"calibration": "pure", "patch_train_scope": "local5",
               **_AUTO_PATCH_KNOBS, "patch_samples_per_cell": 16}

PROFILES["pure"] = {                                          # X7
    "arms": _PURE_ARMS, "rules": ("sum",),
    "rungs": ("L0", "L1", "L2"), "reroll": False, "ctx_mode": "none",
    "halo_cells": {"C": 48, "M": 48, "Y": 32}, "knobs": dict(_PURE_KNOBS)}
PROFILES["pure-self"] = {**PROFILES["pure"],                  # X8
    "knobs": {**_PURE_KNOBS, "patch_selftrain_rounds": 4}}
PROFILES["pure-refit"] = {**PROFILES["pure-self"],            # X9
    "rungs": ("L0", "L1", "L2", "L3f")}
```

`subtract+offset` is deliberately ABSENT from the pure arms: the pinned
default is measured by every other profile, and the point of this one is
the pure path alone, so `select_arm` falls back to the first arm named.
`patch_samples_per_cell` is the ONE axis left named (at 16) in this
family, because `patch_train_scope="local5"` extracts the neighbourhood's
rows through one grid before any per-population choice exists, and a
chosen geometry of another width cannot use them (`n_local_dropped`
records it).

And the pure path is also PLACED behind a patch battery — X10, X11 — so
it is paid for only on the keys the battery could not close:

```python
_PURE_REROLL_ARMS = ("pure+committed", "pure+field2")

PROFILES["patch-then-pure"] = {**PROFILES["patch-refit"],      # X10
    "reroll_only_arms": _PURE_REROLL_ARMS}
PROFILES["everything+patch+pure"] = {**PROFILES["everything+patch"],
    "reroll_only_arms": _PURE_REROLL_ARMS}                    # X11
```

`pure` is an unmix MODE, not only the `calibration=pure` knob, and that
is what makes X10/X11 possible: `pure+committed` computes EXACTLY the
score `patch+committed` computes and differs from it in one stage, so a
placed pure arm is an ARM the ledger attributes (`certifying_arm =
"reroll:pure+committed"`), not a second pass with a different knob bag.
The knobs of a placed arm are the run's, though — a pure path that wants
knobs of its own (`patch_train_scope=local5`, its own sampling) needs the
TWO-PASS form instead, which is the same evidence in a different order:

```
LADDER --profile patch-refit           --out …/pass1
LADDER --profile pure --targets "open-after …/pass1/ledger.jsonl" --out …/pass2
```

(`PROFILES` is a dict literal today; the entries that reference earlier
ones are assigned after the literal, or the literal is rebuilt from
module-level dicts — B3's choice, pinned by the parse test.)

| composition | profile | what it adds over the previous | isolation of its own contribution |
|---|---|---|---|
| **X1** patch + C1 + C2 + D1 | `patch` | the patch arm (per-state, halo-trained, cross-fit) beside the default, per-state calibration branches and per-state context, the `platt-state` rule; `L7c` at the end of the ladder | vs `LADDER --halo-cells 48 --arms "subtract+offset" --rules "sum,best,platt,corr,platt-state" --rungs "L0,L1,L2,L4,L3,L7,L7c" --knob branches=state --knob ctx_state=true` (same knobs, no patch arm: C1+C2+D1 alone) and vs `LADDER --halo-cells 48 --arms "subtract+offset,patch+offset,patch+committed"` (patch arm alone, pooled calibration) — spelled without `--profile` until B5's precedence rule lands |
| **X2** = X1 + P2 | `patch-self` | four self-training rounds on the tile's own population | vs X1; `n_pseudo_labels`, `patch_labels_from` on every patch row |
| **X3** = X2 + P3 | `patch-refit` | the `L3f` rung in the main ladder (not the re-roll) | vs X2; `L3f.r*` rows in `rungs`, first-success by rung, consults, `refit_evidence_used` |
| **X4** = X3 + affine | `patch-affine` | `patch+affine` and `subtract+affine` in the battery (the swim searches under `subtract`, the patch is applied at the winner; `--knob patch_search_mode=patch` puts the OFFSET grid under the patch objective — E2 never reaches the swim) | vs X3 |
| **X5** the union | `everything+patch` | every `everything+field2` arm (read `everything` since 2026-09-12 — PR5) plus the patch family (`patch`, `rings`, `mixture` heads) in the battery — and therefore in the re-roll set when they lose the selection — per-state calibration/rule, self-training on; `L3f` by `--rungs "L0,L1,L2,L4,L3,L3f,L7,L7c"` when wanted (cost) | leave-one-out over rules (exact), `certifying_arm` per row and `first_success_by_arm` (B1 writes both), `--rungs` subsets; the pre-W8 baseline is the rows themselves — every row on `C-open.list` survived every prior pass including the `everything+field2` passes that built H14-union (5,579) and the newest run (5,580), so every X5 certificate is new; X0 (`--profile everything+field2` on the same list) is an OPTIONAL paired control |
| **X6** the fixed point | any profile + `--fixed-point --max-generations 8` | the cascade: every certificate enlarges its neighbours' halos, re-fitting their filters, branches and fields | generation column on every row; `predecessors` |
| **X7** the pure path | `pure` | the page-field pose with no search, the `local5`-trained filter, and (since F2) the TILE'S OWN error rate as the log-odds, floored by the halo's held-out error — no PAVA, no context, no Platt, no refit, one rule, no re-roll; unknown-state cells erased | vs the SAME arms/halo/knobs/rules/rungs through the MAP (`--knob calibration=pava`): the control isolates the calibration stage and nothing else.  `pure_price_by_state` (self / floor / adopted) and `pure_price_source` per state, `pure_error_by_state` with both cross-fit halves, `pure_fallback_states`, `pure_erased_cells`, `pure_unknown_state_cells` |
| **X8** = X7 + P2 | `pure-self` | self-training on the tile's own population, under the pure calibration | vs X7 |
| **X9** = X8 + P3 | `pure-refit` | `L3f` under the pure calibration (the rung refits the filter, and the floor is re-measured with it).  **NOT RECOMMENDED since F2** (§4.0 amendment 15, R3 "why do we need refit??"): the price comes from the tile's own scores, which the rung cannot improve on; the profile stays runnable as a record | vs X8; `L3f.r*` rows |
| **X10** patch, then pure | `patch-then-pure` | X3's battery and ladder, with `pure+committed` and `pure+field2` PLACED in the re-roll: a key the battery closes never pays for them, and they can never win the select fold | vs X3 on the same list — the difference IS the placement's yield, and it cannot be negative in certificates.  `certifying_arm = "reroll:pure+*"`, `reroll.deferred` (absent on every row the battery closed), the header's `reroll_only_arms`, and the wall against X3's |
| **X11** the union, then pure | `everything+patch+pure` | X5's twenty-two arms with the same two placed behind them | vs X5; the same readings.  This is the composition that answers "does the pure calibration find anything twenty-two calibrated arms could not?" at the cost of the re-roll alone |

## 3. The run matrix (sheet H, `scratch/holo3-H-with-facts-7-run.32018`)

**Read this table as a PLAN, and §6 as the RECORD.**  Every S-, I-, K-
and X-row below is a MEASUREMENT ON ONE SHEET: it decides nothing, pins
nothing and promotes nothing (the self-discovery ruling in §4.0, and
CLAUDE.md's rule that ladders are set on multi-sheet minima).  What the
runs that were actually made measured — with the wall, the peak RSS and
the code each one imported — is §6; what is still queued is §6.4.  The
"expected reading" column below is what each row was to be read FOR, not
a result.

Rules of the road: ONE analyzer process at a time (a score is 45 GB, a
pass with 14 workers about the same — and the 48.6 GB README §3 peak was
measured with SEVEN captures; this run has thirteen, so B1 records the
peak RSS of S1 and I1 before X5 is scheduled); the per-lane `field2` fit
blocks the first key that needs it for ~6 minutes (only when field2 arms
are in the battery); a pass writes its ledger at the fixed point only (no
orderly stop).  Walls below are estimates from the measured 41 s/key wall
at 14 workers for the 14-arm `everything` profile (README §2.4) and the
10–15 minute score runs of MEAS; they are per generation and say nothing
about the cascade's later generations.  Every row names the build item
whose acceptance it is charged to, or OPTIONAL.

**Total wall, serialised under the one-process rule**: R1 ≈ 7 h (22 score
runs), R2 ≈ 5 h (12 passes and controls), R3 ≈ 13–16 h — about 26 h.  The
MANDATORY subset (every acceptance gate of B1–B5): S0, S1, S1b, S7, S8,
S12, I3, I4, I5, I6, K1, K2, K3, X1, X2, X3, X5 ≈ 12 h.

**R0 — the target lists (once).**  The census defines the targets; the
band ∧ stream conjunction has no grammar until B5, so write list files:

```
$PY -m analyzer census --run-dir $RUN --out scratch/analyzer/W8/census
$PY - <<'EOF'
import json
rows=[json.loads(l) for l in open('scratch/analyzer/W8/census/census.jsonl')][1:]
rows=[r for r in rows if r.get('type')=='row' and r['covered'] and not r['certified_by_production']]
for name, pick in (('C-open',  lambda r: r['stream_id']=='C'),
                   ('C-dead',  lambda r: r['stream_id']=='C' and r['band']=='dead'),
                   ('C-dead-sibs', lambda r: r['stream_id']=='C' and r['band']=='dead' and set(r['siblings_certified'])=={'M','Y'}),
                   ('Y-open',  lambda r: r['stream_id']=='Y')):
    keys=[r for r in rows if pick(r)]
    open(f'scratch/analyzer/W8/{name}.list','w').write(''.join(f"{r['page']},{r['ty']},{r['tx']},{r['stream_id']}\n" for r in keys))
    print(name, len(keys))
EOF
```

Expected: ~155 open C rows (~100 dead, of which ~64 with M and Y both
certified; ~23 marginal; ~33 live, 27 of them with Y open) and ~148 Y.
`C-dead-sibs` is where every per-state mechanism can fire (cargo cleanable
1.0); `C-open` minus it is where only the state-agnostic tier and the
`subtract` fallback carry the patch arm.  A `list FILE` key absent from
the census is silently dropped — the printed counts are the check.

**R1 — isolation, offline (truth-scored cell error by sibling state; no
certificates, no exposure).**  These reproduce MEAS §4's table for the
BLIND arm and decide the defaults B1 leaves open.  Readings: `BYSTATE
<out>/score.jsonl` prints error by (band, state) per 4800 lane; `score.md`
is the pooled, band-less summary.  S1's reference (0.119) is a 4800-lane,
per-lane number on whole edge tiles; S1 is read on the same lanes, per
lane, as a DELTA against S0 on the same rows.

| run | command | wall | what it says | charged to |
|---|---|---|---|---|
| S0 control | `SCORE --arms "subtract+offset" --halo-cells 48 --out scratch/analyzer/W8/S0` | 10–15 min | the arm's band M+Y ≈ 0.214 (all lanes; MEAS §1's own pooled figure) and ≈ 0.208 on the 4800 lanes re-derived at halo 48 (the halo changes the mix and the PAVA; must match MEAS within noise); every existing arm's score unchanged = the H14 numbers | B1 |
| S1 P1 | `SCORE --arms "patch+offset" --halo-cells 48 --out …/S1` | 15–25 min | band M+Y error on the 4800 lanes, per lane, paired against S0 over tiles: the acceptance is a fall > 2 SE; the level is REPORTED against 0.119 with the estimator difference stated; `patch_states` per (lane, state), `patch_fallback_cells`, `patch_fit_error_insample` vs `_crossfit`; peak RSS | B1 |
| S1b samples | `… --arms "patch+offset" --halo-cells 48 --knob patch_samples_per_cell=16 --out …/S1b` | 20–30 min | 8 vs 16 samples per cell (144 vs 576 features at 4800).  ~~pins the default~~ — WITHDRAWN (§4.0): it MEASURES the axis; the axis became `"auto"` in B7 and 8 stays only as the inherited fallback.  Measured: §6.2 | B1 |
| S1c RGB | `… --knob patch_channels=rgb --out …/S1c` | 20–30 min | P1b | B3 |
| S1d window | `… --knob patch_window_cells=2.0 --out …/S1d` | 20–30 min | P1e (the crop grows with the window) | B3 |
| S2 P2 | `… --knob patch_selftrain_rounds=4 --out …/S2` | +20 % | vs S1: expect ≤ 0.005 (MEAS §5b) | B3 |
| S3 E2 | `… --knob patch_search_mode=patch --out …/S3` | 3–5× S1 | does the patch objective move the offset, and does it help M+Y?  `patch_search_fits` | B3 |
| S4 rings | `SCORE --arms "rings+offset" --halo-cells 48 --out …/S4` | 15 min | P1c vs S1 | B3 |
| S5 mixture | `SCORE --arms "mixture+offset" --halo-cells 48 --out …/S5` | 15 min | M1: band M+Y ≈ 0.190, worse elsewhere (MEAS §4) — a pin, not a hope | B3 |
| S6 aperture ×3 | `SCORE --arms "subtract+offset" --halo-cells 48 --knob aperture_cells=0.5 --out …/S6a`; `=1.0` → S6b; `--knob aperture_kind=gaussian` → S6c | 15 min each | A7: the predicted loss at 0.5 and gain at 1.0 on M+Y, measured | B3 |
| S7 C1 | `SCORE --arms "subtract+offset" --halo-cells 48 --knob branches=state --out …/S7` | 15 min | per-state calibration alone: R on the band's rows vs S0 (0.797 → 0.836 is MEAS §4's blind Platt; PAVA per state should land near it); `branches.s3` acceptance and the word-site exclusion counts | B2 |
| S8 C1+C2 | `… --knob branches=state --knob ctx_state=true --out …/S8` | 15 min | the context axis per state (oracle 0.059); `ctx_state_reason` per state (the production floors at the dead-band minimum) | B2 |
| S9 X1 evidence, combined | `$PY measure/c-third-layer-20260906/dump_cells.py patch+offset scratch/analyzer/W8/S9-cells.npz '{"branches":"state","ctx_state":true}'` then `$PY measure/c-third-layer-20260906/combine_blind.py scratch/analyzer/W8/S9-cells.npz` | 30 min | the combined-lane error and R per tile (clipped sum over the 4800 lanes, per-tile even/odd Platt — `analyze_combined.py`'s estimator) against MEAS §5's 0.062 / 0.956 median (dead band): the number that says whether the band's tiles cross R = 1.  The `score` tool is per lane and cannot produce it; `dump_cells.py` takes the knobs as JSON argv[3] (B3 extends it) and `combine_blind.py` is `analyze_combined.py`'s combination over a per-lane LLR dump (truth-side, under `measure/`) | B3 |
| S10 agnostic | `SCORE --arms "patch+offset" --halo-cells 48 --knob patch_min_labels_per_state=1000000 --out …/S10` | 20 min | P1d alone (the agnostic tier's own floor stays at 200): the ordinary-cell gain without per-state filters — what the open-Y tiles get | B3 |
| S11 local5 scope | `… --knob patch_train_scope=local5 --out …/S11` | 30–40 min | P1g: the estimator closest to the measurement's (the neighbourhood's whole certified tiles, per lane) — vs S1 | B3 |
| S12 floor sweep ×3 | `… --knob patch_min_labels_per_state=200 / 600 / 1200 --out …/S12a-c` | 20 min each | at what label supply the per-state tier pays.  ~~pins the floor~~ — WITHDRAWN (§4.0), and the two rows that ran are CONFOUNDED because B3's agnostic tier moved with the floor (§6.2); B7 replaced the count with a statistical admission | B1 |

**R2 — isolation, blind (certificates).**  On `C-open.list` (~155
targets), single generation unless said.  The ledger's stream × band table
(`ledger.md` "Stream x band") gives rows/certified per (C, band); the
`_selected` block on every row gives the paired select-fold comparison
patch-vs-default per lane; `attribution` gives leave-one-out by rule and,
from B1, first-success by arm.  The K rows are DESIGN §8's controls; a
composition's numbers are not recorded in PLAN §6 before its K row has
run.

| run | command | wall | expected reading | charged to |
|---|---|---|---|---|
| I0 control | `LADDER --arms "subtract+offset" --halo-cells 48 --out …/I0` | ~10 min | the default alone: ~0–2 certificates (these rows survived every pass) | B1 |
| I1 P1 | `LADDER --arms "patch+offset" --halo-cells 48 --out …/I1` | ~15–20 min | the one arm's certificates by band; `patch_states` per (lane, state) on every row; the C-dead-sibs rows are where the per-state tier fired; peak RSS | B1 |
| I2 P1 vs default, selected | `LADDER --arms "subtract+offset,patch+offset" --halo-cells 48 --out …/I2` | ~25 min | `_selected[lane].comparisons["patch+offset"].adopted` per lane (2-SE paired test on the select fold) — the blind quality signal; re-roll attribution `certifying_arm = reroll:patch+offset` vs `subtract+offset` | B1 |
| I3 C1+C2 | `LADDER --arms "subtract+offset" --halo-cells 48 --knob branches=state --knob ctx_state=true --out …/I3` | ~10 min | per-state calibration on the default arm: `branches.s3.accepted`, `ctx_state_adopted`, `branch_fallback` counts (expect the pooled fallback on the 36 dead rows with only M certified); L3's `state_context_adopted` refusals | B2 |
| I4 D1 | `LADDER --arms "subtract+offset,patch+offset" --halo-cells 48 --knob branches=state --rules "sum,platt,platt-state" --out …/I4` | ~25 min | `leave_one_out_by_rule["platt-state"]`, `only_by_rule`; `platt_state_refused` per row (the select-fold floor of 40 per class per state); `contributing_captures` under the union rule | B2 |
| I5 C3 | `LADDER --arms "subtract+offset,patch+offset" --halo-cells 48 --knob branches=state --rungs "L0,L1,L2,L7c" --out …/I5` | ~25 min | first-success by rung `L7c`; `n_erased`, `n_state_cells` on its rows | B2 |
| I6 P3 | first `LADDER --limit 10 …` to measure the wall, then `LADDER --arms "subtract+offset,patch+offset" --halo-cells 48 --knob branches=state --rungs "L0,L1,L2,L3f" --knob refit_rounds=2 --out …/I6` | ~40 min (measured on the 10 first) | `L3f.r0/r1` rows: `n_pseudo`, unsat at entry vs exit, consults, `refit_evidence_used` against the budget; certificates first-success `L3f` | B4 |
| I7 T1 | `LADDER --arms "subtract+offset" --halo-cells 48 --rungs "L0,L1,L2" --knob 'L2=[{"mode":"damped","iters":300,"lam":0.5,"temperature":0.8},{"mode":"damped","iters":300,"lam":0.5,"temperature":1.25}]' --out …/I7` | ~10 min | unsat at exit vs t in the blind histogram; certificates | B4 |
| I8 no-reroll control | `LADDER --profile patch --no-reroll --out …/I8` | ~30 min | what X1 mints WITHOUT the attempt-count channel | B5 |
| K1 controls, patch | `CONTROLS --targets "list scratch/analyzer/W8/C-dead-sibs.list" --profile patch --null 5 --frame-null 3 --parity 100 --out …/K1` | ~40 min | `null_arm`: 0 certificates on donor pixels under the patch arms and per-state machinery; `frame_null`: 0 certificates with shifted certificates (wrong labels AND wrong sibling states), `matches_production` reported; `parity_sample` ≥ 80 % per stream under `--profile patch`; `pseudo_source`/`patch_labels_from` on the control rows | B3 |
| K2 controls, refit | `CONTROLS --targets "list scratch/analyzer/W8/C-dead-sibs.list" --profile patch-refit --null 5 --frame-null 3 --parity 0 --out …/K2` | ~40 min | the same under `L3f` (the null arm hands no `refit` closure and must see `no_refit`; `frame_null` runs the real `blind_key` and DOES bind it): 0 certificates; the null arm's exposure denominator with the extra consults | B4 |
| K3 parity, everything+patch | `CONTROLS --profile everything+patch --parity 100 --null 0 --frame-null 0 --out …/K3` | ~1 h | `parity_sample` ≥ 80 % per stream under the union profile | B5 |

**R3 — compositions.**

| run | command | wall | reading | charged to |
|---|---|---|---|---|
| X1 | `LADDER --profile patch --out …/X1` | ~35–45 min | stream × band; `certifying_arm` split and `first_success_by_arm`; leave-one-out by rule incl. `platt-state`; first-success by rung incl. `L7c`; peak RSS | B3 |
| X2 | `LADDER --profile patch-self --out …/X2` | ~45 min | vs X1 | B3 |
| X3 | `LADDER --profile patch-refit --out …/X3` | ~1 h (bounded by `refit_max_evidence`; I6's `--limit 10` wall × 15 is the estimate) | vs X2; `L3f` first-success and its consults in `exposure_distinct` | B4 |
| X4 | `LADDER --profile patch-affine --out …/X4` | ~1.3 h | vs X3 | B4 |
| X0 (OPTIONAL) | `LADDER --profile everything+field2 --out …/X0` | ~3 h | the paired pre-W8 union on the same list; expected 0–2 (the rows survived the passes that built the base).  No X0 result is anywhere in this record, and it is UNRUNNABLE since 2026-09-12: the profile retired with `field2c` (PR5).  The paired control in that shape today is `--profile everything` | — |
| X5 | `LADDER --profile everything+patch --out …/X5` | ~3–4 h per generation (21 arms; +6 min field2 fit at the first key) | the union: rules exact, `certifying_arm`, `first_success_by_arm`; the baseline argument of §2 | B5 |
| X6 | `LADDER --profile everything+patch --fixed-point --max-generations 8 --out …/X6` | X5 + the cascade (re-attacks are neighbours: expect 1–3 more short generations) | generation column; `predecessors`; then `analyzer close --localize` and `export-facts` for the resume | B5 (if the user rules it) |
| X10 | `LADDER --profile patch-then-pure --out …/X10` | X3 + the re-roll's share of two more arms (paid only on the keys X3 could not close) | vs X3 on the SAME list: the difference IS the placement's yield.  `certifying_arm = "reroll:pure+*"`; `reroll.deferred` must be ABSENT from every row the battery closed; the header's `reroll_only_arms` | B5 |
| X11 | `LADDER --profile everything+patch+pure --out …/X11` | X5 + the same | vs X5; "does the pure calibration find anything twenty-two calibrated arms could not?" at the cost of the re-roll alone | B5 |
| X10a (the TWO-PASS form) | `LADDER --profile patch-refit --out …/pass1` then `LADDER --profile pure --targets "open-after …/pass1/ledger.jsonl" --out …/pass2` | the sum of the two | the same evidence in a different order — and the form to use when the pure path wants knobs of its own (a placed arm runs under the RUN's knob bag) | B5 |
| Y | `$PY -u -m analyzer ladder --run-dir $RUN --targets "list scratch/analyzer/W8/Y-open.list" --profile everything+patch --workers 14 --out …/Y5` | ~3 h | the other half of the residue: does the per-state machinery move Y (its state 3 = C+M) | B5 |
| P0 | `LADDER --profile pure --out …/P0` | ~20 min | the pure path on `C-open.list`: certificates, `certifying_arm`, `pure_error_by_state` per (lane, state) with both cross-fit halves, `pure_fallback_states` / `pure_erased_cells` / `pure_unknown_state_cells` (the pure path's COVERAGE is the thing to watch on the open live/marginal C rows, where Y is open and the sibling state is unproven), and the `_selected` comparison `patch+field2` vs `patch+committed` | B6 |
| P0M | the SAME arms/halo/knobs/rules/rungs through the MAP (`--knob calibration=pava`, spelled in flags) | ~20 min | THE control for P0: it isolates the calibration stage and nothing else.  Caveat stated in the chain's own header — `--profile` sets `reroll: False` for `pure` and the flag-spelled control runs with the default re-roll ON, so the control is given an advantage the pure path lacks and a P0 win over P0M is conservative | B6 |
| P0-dead | `LADDER --targets "band:dead+stream:C+siblings:M,Y" --profile pure --out …/P0-dead` | ~10 min | the pure path where every per-state population HAS its labels (the conjunction grammar B5 added spells this population without a list file); the paired comparison against `--profile patch` on the same rows is the pure-vs-map question with the detector held fixed | B6 |
| K6 | `CONTROLS --profile pure --null 5 --frame-null 3 --parity 100 --out …/K6` | ~40 min | the pure path's control: 0 certificates on donor pixels and on shifted frames, parity ≥ 80 % per stream.  Before any P0 number is recorded | B6 |

**The generation flags in these rows (R1, 2026-09-06).**  `--fixed-point
--max-generations 8` in X6 means what it always meant — converge, bounded
at 8 — but the two are now ORTHOGONAL (§6.6): `--max-generations N` alone
is a legal bounded cascade (up to N generations, stopping early the
moment one re-attacks nothing), and `--fixed-point` alone converges under
the default cap.  Any row here may be given a cap on its own — a shorter
X6 is `--max-generations 2` — and the ledger header says which bound
ended the pass (`stop_reason`).

After every blind pass: `SCORE --ledger <pass>/ledger.jsonl --out …` scores
its certificates against the payload (0 wrong is the invariant every tier
has held) and its `L3f`/`L7c` rungs' packed hard vectors.

## 4. The W8 build spec

Five items, built in order on `analyzer-w8`, each committed with its tests
green (`env314t/bin/python -m pytest analyzer/tests -q -n 8`: the 459 +
new pass, 69 skips unchanged) and `pyflakes analyzer` silent.  Every
mechanism lands in a NEW module — `arms.py` (1198) and `field2.py` (1149)
are over the cap and take dispatch lines only; `calibrate.py` (849),
`combine.py` (636), `ladder.py` (776), `fixedpoint.py` (840), `sample.py`
(411), `unmix.py` (447) have room for their dispatch.  Every new module is
automatically a root of the blindness closure test
(`test_analyzer_fixedpoint.py::test_no_module_reachable_from_a_run_command_imports_truth_or_oracle`)
and may import numpy/scipy, `holo.receiver.*` and the analyzer's run-side
modules, never `truth`/`oracle`/`score`; `patch.py`/`statecal.py` must not
import `arms`/`unmix` (cycle), and `statecal.py` must not import
`calibrate` (cycle: calibrate dispatches into statecal; the branch
constants both need move to `types.py`).  No RNG anywhere: percentile
thresholds and `calibrate.fold_hash` only.  One spelling for every
signature; where a later item extends a function it repeats the full
signature.

### 4.0 Rulings this spec proposes (for the user; the build follows them unless overruled)

**THE SELF-DISCOVERY RULING (Germano, 2026-09-06), which overrules parts
of this section and is binding on every builder and reviewer after it:**

> "even the existing pins / defaults are not well grounded.  if a run can
> discover its own truth for the paper-print-scanner-scan object at hand,
> it should!  not really a build job."

Consequences, in force from B7:

1. **No default, floor or knob value is pinned or re-pinned from sheet
   H's sweeps.**  S1b, S12, S6, S1c, S1d and every other S-run are
   MEASUREMENTS ON ONE SHEET, recorded as such in §6 and never promoted
   (CLAUDE.md: ladders on multi-sheet minima; a single sheet is
   existence and regression evidence).  Ruling 4 below and the "S12 pins
   the floor" clause are **WITHDRAWN** — struck through, not deleted.
2. **Every knob of the patch family and the per-state calibration that a
   run can choose from the sheet itself takes the value `"auto"`, and
   `"auto"` is the default in the W8 profiles.**  The run picks, per
   (lane, plane, sibling state) and per tile, among a small candidate set
   on the SELECT fold — DESIGN §4.8's own arbitration, the paired
   standard-error test `select_arm` already does for arms — records the
   choice and every candidate's held-out loss in the blind detail, and
   falls back to the INHERITED value (production's aperture, the lane's
   native pitch, the a-priori floor) when the select fold cannot
   discriminate.  Candidate sets, fallbacks and what is deliberately not
   auto: README §2.4 and DESIGN §14.4.  `patch_min_labels_per_state` is
   not a count any more: a tier is admitted when its own out-of-fold
   error beats the population's majority rate by more than the same
   standard-error multiple AND its optimism does not exceed the
   advantage it bought.  Cost is not a constraint (a few hundred tiles).
3. **The acceptance gates keep only their REGRESSION meaning** — the new
   arm does not lose certificates the default arm had, and zero wrong
   under the offline scorer.  No gate is a tuning target.

1. `patch+offset` SEARCHES the offset grid under `subtract` and applies
   the patch at the winning pose (`patch_search_mode="subtract"`,
   default); the patch objective (E2) is the knob value `"patch"` and
   reaches the OFFSET GRID ONLY.  The affine swim (`_affine_arm`,
   `_correlation_score`) and the word pose (`word_pose`) ALWAYS evaluate
   `subtract` for a patch mode: their objectives run over fit ∪ search
   rows and would be half in-sample for a fitted score.  `_correlation_score`
   is otherwise untouched (its missing `fit_mask` for `conditional` is a
   recorded pre-existing gap; fixing it changes `conditional+affine`).
2. P3 is a LADDER RUNG (`L3f`) with a `refit` closure knob bound per rule
   in `blind_key` — the rung contract (a pure function of its knobs)
   holds, the pixels stay behind the closure.  It is bounded by
   `refit_rounds` AND a per-key evidence budget `refit_max_evidence`, and
   it is NOT in the re-roll's rung list by default.
3. `L7c` lives in `ladder.py` (a 40-line twin of L7a using its private
   helpers); `L3f` in `refit.py` with a function-local import from
   `ladder`; per-state calibration in `statecal.py`; the patch family in
   `patch.py`.  Neither new rung joins the `L7` alias or `DEFAULT_RUNGS`.
4. ~~`patch_samples_per_cell` defaults to 8, capped at the lane's native
   pitch (144 features at 2400/4800, 36 at 1200); 16 reproduces the
   measured 576-feature filter at 4800.  S1/S1b decide; the floor
   `patch_min_labels_per_state` (200) is pinned by S12; the default is
   re-pinned from those measurements in B5.~~  **WITHDRAWN** by the
   self-discovery ruling above: a sweep on one sheet may not pin a
   default.  8 and 200 remain as the INHERITED FALLBACK — what a run uses
   when its own select fold cannot tell the candidates apart — and both
   axes are `"auto"` in the W8 profiles.  S1, S1b and S12 stand as
   measurements (§6) and decided nothing.
5. CLI: `--knob KEY=VALUE` (JSON value, else string) on `ladder`, `read`,
   `controls`, `score` lands in B1 (every knob-carrying run needs it);
   reserved knob names are refused there.  B5: `--ctx-mode`; `--no-reroll`;
   explicit `--arms/--rules/--rungs` WIN over a profile's lists (a profile
   supplies what the operator did not say); the conjunction grammar.
   The header records `knobs`, `reroll`, `reroll_rungs` and `row_to_dict`
   writes `certifying_arm` from B1.
6. Sibling states use `spectral.siblings_of(plane)` ascending, `s = left +
   2·right`, in every module (one helper, `statecal.sibling_state`,
   created in B1).
7. **A fitted score changes the fold contract.**  The patch family
   cross-fits inside the fit fold: fit-fold labelled rows are split into
   halves A/B by `fold_hash(page_cells_yx, seed ^ CROSSFIT_SALT) < 0.5`;
   filter_A (fitted on A) scores B and filter_B scores A, so every
   fit-fold labelled row carries an OUT-OF-FOLD score; the full filter
   (A ∪ B) scores every other row (cargo, search, select).  PAVA, the
   context fit and every search objective see only those scores.  The
   in-sample vs cross-fit fit-fold error is published
   (`patch_fit_error_insample`, `patch_fit_error_crossfit`).  Pseudo rows
   (P2, P3) join the training set of both halves and the full fit.
8. **Pseudo labels are typed.**  `types.PseudoLabels(source, cells_yx,
   bits, weights)` (frozen) is the only value the `pseudo_labels` door
   accepts; `refit.confident_pseudo_labels` builds `source="decoder"`,
   P2 builds `source="self"` inside `patch_score` (no door).  The CLI
   refuses the reserved names; `score.evidence_for_row` raises on
   `pseudo_labels`/`refit` in `config.knobs`; `blind_key` assigns every
   derived knob unconditionally and refuses a config that names one.
9. **The feedback rung never reshapes the combination.**  `refit_evidence`
   recombines with `combine.combine(new, rule, labels=<the round-0 label
   view>)`, so the rule coefficients are the deterministic function of
   the same select-fold view and come out identical; `label_rows`,
   `label_values`, `label_discriminating`, `label_state` are byte-identical
   with and without pseudo rows; `label_llr` is a held-out view of the
   refitted map and is allowed to move.
10. **L3 is exact for a pooled correction only.**  `Combined.ctx_state_adopted`
    = any contributing lane adopted a per-state context; the L3 rung
    refuses `state_context_adopted` on such a row.  `combine.pooled_ctx_offsets`
    keeps reading the pooled 9-vector.
11. **Per-state anything excludes word sites from its TRAIN set** (a
    word site carries one target class per sibling state), keeps dust,
    and reports furniture vs cargo counts per state.  Pooled fits keep
    word sites (unchanged).
12. **BLAS is single-threaded per worker.**  `analyzer/__main__.py` sets
    `VECLIB_MAXIMUM_THREADS`, `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS` to
    `1` before numpy is imported when they are unset (the worker pool is
    the parallelism; numpy here is Accelerate); a repeatability test pins
    `np.array_equal` across two in-process patch scores.
13. **`Crops.raw_rgb` is opt-in** (`keep_raw`), set only for patch modes
    and the aperture path; `extract` is chunked (4,096 rows) so its
    transient stays under ~40 MB per call.
14. **THE PURE PATH IS A NAMED PATH, not a default** (the user, 2026-09-06):

    > "we already have every tile addressed, the correct page field and
    > mostly correct poses per plane — there is no justification for
    > pushing that through PAVA, ctx, Platt; just try it out either way."

    So P0 exists: the page-field pose with no search, the filter trained
    over the 5×5 neighbourhood's certified cells, and the filter's own
    held-out error rate as the log-odds, with nothing between it and BP.
    "Either way" is the design: it ships as `pure`/`pure-self`/`pure-refit`
    beside the map, its control is the SAME configuration through the map,
    and what it measures is what the calibration stage is worth.  No
    default moves.
15. **F2 AMENDMENT (2026-09-06, after the first trial, §6.5) — the pure
    path prices ITSELF** (the user's rulings, verbatim intent: R2
    "cells with unknown sibling state obviously are erasures / ie
    uncounted"; R3 "why do we need refit??").  Ruling 14's mechanism
    said "the filter's own held-out error rate as the log-odds", and the
    trial showed what that number is on a dead-band tile: the halo's
    error, ~3 %, on cells that measure ~15 % — a certified neighbour's
    cells are EASIER than the tile's cargo, so the halo's number is a
    floor, not an estimate.  In force from F2: (a) a cell whose sibling
    state is unknown is an ERASURE — LLR 0, counted in
    `pure_erased_cells` / `pure_unknown_state_cells`, priced by nothing
    (the `other` population and its pooled fallback are gone) and
    COUNTED into nothing either — the follow-up review found such rows
    still in the pooled halo, which is the population every starved
    state's threshold and floor come from, and took them out (§6.8);
    (b) a
    known state is priced by the TILE — the equal-prior two-component
    fit on the discriminant's scores over the tile's own cargo cells of
    that state, the error of the hard decision at the threshold — with
    the halo's cross-fit held-out error as a FLOOR (`e = max(e_self,
    e_halo)`, then the clamp); (c) **the pure-refit recommendation is
    WITHDRAWN**: no refit inside the pure path, nothing fitted between
    the discriminant and BP (no PAVA, no context, no Platt, no refit).
    `pure-refit` (X9) remains a runnable profile for the record and is
    recommended by nothing in this document; `pure` (X7) is the pure
    path's profile of record.  §6.5's SM2 numbers are the halo-priced
    B6 path's and stand as its record; the re-priced path has not run on
    paper (§6.7).  Self-discovery (the ruling at the head of this
    section) is what this is: the price is discovered on the object at
    hand, per tile and per state, and no number in it is a pin.

### B1 — the patch module, raw crops, dispatch, arm names, the knob door, ledger keys, tests

Files: NEW `analyzer/patch.py`, NEW `analyzer/statecal.py` (the state
helper only), NEW `analyzer/tests/test_analyzer_patch.py`; edits
`analyzer/types.py` (Crops, Read), `analyzer/sample.py` (`open_crops`,
`read_rgb`), `analyzer/unmix.py` (`UNMIX_MODES`, `unmix_score`),
`analyzer/arms.py` (≤ 15 lines), `analyzer/calibrate.py` (the nested-CV
tuple, 1 line), `analyzer/cli.py` (`--knob`), `analyzer/score.py`
(reserved-knob refusal, 3 lines), `analyzer/fixedpoint.py` (`_header`, 3
lines), `analyzer/ledger.py` (`row_to_dict`, `attribution`, ledger.md, ≈
25 lines), `analyzer/__main__.py` (BLAS pin), `analyzer/tests/
test_analyzer_arms.py` (exclude the context modes from the no-context
enumeration), `test_analyzer_cli.py`, `test_analyzer_ledger.py`,
`measure/c-third-layer-20260906/bystate.py` (`--level`).

**types.py** — `Crops` gains a LAST defaulted field `raw_rgb: np.ndarray |
None = None` (uint8 `(h, w, 3)`, divide lazily by `divisor`); `Read`
gains `points_yx: np.ndarray | None = None` (`(n, 2)` level pixels of the
POSED cell centres, NaN unobserved) and `linear_by_owner: Mapping[int,
np.ndarray] | None = None` (owner index → `anchor.pose_linear(terms)`, the
2×2 cell→pixel map in (y, x)).  Added, never renamed.

**sample.py** — `open_crops(lane, lfp, *, bound_dots, cell_dots, keep_raw:
bool = False) -> Crops` keeps `raw` on the `Crops` only when `keep_raw`;
`read_rgb` fills `points_yx=moved` and `linear_by_owner` from the loop it
already runs (lines 373–382); the two refusal constructors keep `None`.
Byte-identical `values_rgb` for every existing arm (pinned).

**statecal.py** (B1's part): `N_STATES = 4`, `STATE_UNKNOWN = -1`,
`sibling_state(frame: KnownFrame, plane: int) -> np.ndarray` (int8 `(n,)`,
−1 where `~frame.siblings`; `left, right = spectral.siblings_of(plane)`;
`s = bits[:, left] + 2·bits[:, right]`).  Imports numpy and
`holo.receiver.lib.spectral` only.

**patch.py** — blind, < 700 lines:

```python
PATCH_MODES: tuple[str, ...] = ("patch",)          # B3 adds "rings", "mixture"
DEFAULT_WINDOW_CELLS = 1.5; DEFAULT_SAMPLES_PER_CELL = 8
DEFAULT_SHRINKAGE = 1e-2; DEFAULT_MIN_LABELS_PER_STATE = 200
DEFAULT_MIN_LABELS_AGNOSTIC = 200; CROSSFIT_SALT = 0x57383143; EXTRACT_CHUNK_ROWS = 4096

@dataclass(frozen=True)
class PatchSpec:
    window_cells: float = 1.5
    samples_per_cell: int = 8
    channels: tuple[int, ...] = (0,)
    shrinkage: float = 1e-2
    min_labels_per_state: int = 200
    min_labels_agnostic: int = 200
    min_per_class: int = spectral.MIN_PER_CLASS         # 25
    fallback_mode: str = spectral.MODE_SUBTRACT
    search_mode: str = "subtract"
    selftrain_rounds: int = 0; selftrain_keep: float = 0.6; selftrain_weight: float = 2.0
    train_scope: str = "footprint"
    exclude_word_sites: bool = True

def spec_from_knobs(knobs: Mapping[str, Any]) -> PatchSpec      # patch_window_cells, patch_samples_per_cell, patch_channels ("r"|"rgb"), patch_shrinkage, patch_min_labels_per_state, patch_min_labels_agnostic, patch_search_mode, patch_selftrain_*, patch_train_scope, patch_exclude_word_sites
def spec_key(spec: PatchSpec) -> tuple                          # hashable, for memo keys
def grid_cells(spec: PatchSpec, pitch_px_level: float) -> np.ndarray   # (P*P, 2) offsets in CELLS (y, x): S = min(samples_per_cell, round(pitch)), P = round(window*S), u_j = (j+0.5)/S - window/2
def extract(crops: Crops, points_yx: np.ndarray, linear_by_owner: Mapping[int, np.ndarray], owner_index: np.ndarray, rows: np.ndarray, grid: np.ndarray, channels: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]
    # (len(rows), P*P*len(channels)) float32 features and a (len(rows),) bool `inside`;
    # per owner, in chunks of EXTRACT_CHUNK_ROWS rows: pix = points[i] + grid @ L_owner.T  (grid is (y, x); NO axis reversal — shifted_points reverses because ITS delta is (x, y));
    # local = pix - (y0, x0); inside iff every sample in [0, h-1] x [0, w-1]; the bounds check comes FIRST, a clamp is never silent;
    # map_coordinates(raw[..., ch].astype(float32) / divisor, local.T, order=1) into the preallocated output slice — the arithmetic of color_region_anchor.rectified_ncc, a reuse
@dataclass(frozen=True)
class Discriminant: mu; sd; w; threshold; n_0; n_1; scale        # scale = the sd of the population's out-of-fold fit scores (ruling 7 + one shared scale)
def fit_discriminant(X, y, weights=None, *, shrinkage) -> Discriminant
    # analyze_selftrain.fit_lda verbatim: weighted mean/sd standardisation (sd + 1e-6), t = +-1,
    # solve ((Xs*w).T @ Xs + lam*I) v = (Xs*w).T @ t, threshold = midpoint of the class-mean scores
def apply_discriminant(X, d) -> np.ndarray                        # (((X - mu)/sd) @ w - threshold) / scale; high = ink
def crossfit_scores(X, y, weights, half: np.ndarray, *, shrinkage) -> tuple[np.ndarray, Discriminant]
    # half = fold_hash(cells[rows], seed ^ CROSSFIT_SALT) < 0.5; fits A on ~half, scores B, and vice versa -> out-of-fold scores on every training row; returns them and the FULL fit (whose scale is the OOF sd)
def pseudo_rows(fp: TileFootprint, pseudo: PseudoLabels) -> tuple[rows, bits, weights]   # (B4) page cells -> footprint rows (flat key searchsorted); cells outside the footprint dropped
def patch_score(spec: PatchSpec, plane: int, frame: KnownFrame, mix: PlaneMix, crops: Crops, read: Read, lfp: LaneFootprint, folds: Folds, *, extra_labels: tuple[rows, bits, weights] | None = None) -> tuple[np.ndarray, dict]
```

`patch_score` (ONE signature, used verbatim by unmix, arms and the tests):
labels = `frame.known[:, plane] & lfp.observed & folds.fit` (fit fold
ONLY); `state = statecal.sibling_state(frame, plane)`; per-state train
rows additionally exclude `frame.furniture_kind == 0` (word sites) when
`spec.exclude_word_sites` — dust and cargo projections stay; features are
extracted once for the labelled rows and for every observed row at the
read's pose; per state `s` in 0..3 with `n_s ≥ min_labels_per_state` and
`min(n_0, n_1) ≥ min_per_class`: `crossfit_scores` on the labelled rows of
state `s` (plus `extra_labels` rows of that state, weighted, in every
fit), the OOF scores are written at the fit-fold rows and the full fit
scores the remaining observed rows of state `s`; rows whose state is −1
or whose state refused → `fallback_mode` via `spectral.plane_score(mix,
read.values_rgb, frame.bits, frame.known, plane, MODE_SUBTRACT)` in B1 (B3
inserts the state-agnostic tier), that population scaled by the sd of its
own fit-fold labelled scores; rows not `inside` the crop → fallback too.
Output `(score (n,) float64, detail)`; NaN where unobserved; every
population on the shared unit scale (DESIGN §4.7's B12 note, restated in
the module docstring; C1's per-state branches are the natural companion).
Detail (scalars and small dicts ONLY — nothing array-valued reaches
`Evidence.blind`): `patch_window_cells, patch_samples_per_cell, patch_px,
patch_features, patch_channels, patch_shrinkage, patch_fit_fold="fit",
patch_labels_from="halo", patch_states={s: {n_fit_0, n_fit_1, n_fit_word,
n_fit_dust, n_fit_cargo, fitted, n_scored, labels_per_feature}},
patch_agnostic_cells, patch_fallback_cells, patch_outside_cells,
patch_search_mode, patch_fit_error_insample, patch_fit_error_crossfit,
patch_crossfit_halves=(n_A, n_B)`.  The target plane's own bit is used
ONLY as the label of fit-fold rows; a test flips the search/select-fold
bits and the scores must not move; a second test shuffles the fit-fold
labels and expects held-out d′ ≈ 0 with `fitted` still True (the blind
twin of MEAS §5b's permutation control).

**unmix.py** — `UNMIX_MODES += patch.PATCH_MODES` (import `patch`);
`unmix_score(mode, target_plane, mix, values_rgb, frame, *, fit_mask=None,
context=None)` where `context = (crops, read, lfp, folds, spec)`; `mode in
PATCH_MODES` → `patch.patch_score(spec, target_plane, frame, mix, crops,
read, lfp, folds)[0]`; `UnmixError("patch modes need a read context")` when
`context is None` — no silent fallback.

**arms.py** (≤ 15 lines): `_loss_of` gains `crops` and passes
`context=(crops, read, lfp, folds, spec)` when the mode is a patch mode and
the spec's `search_mode == "patch"`, else evaluates `subtract` (ruling 1);
`_affine_arm` and `word_pose` substitute `"subtract"` for a patch mode
before anything else (ruling 1) — `_correlation_score` is not edited;
`evidence_for`: `keep_raw = unmix_mode in PATCH_MODES`, `bound += 0.5 *
spec.window_cells * cell_dots` for patch modes (the crop margin: 12 px at
4800 for a 1.5-cell window, inside the 34-px halo; 16 px for 2.0), and at
the `unmix_score` seam branches to `patch_mod.patch_score(spec, plane,
frame, mix, crops, read, lfp, folds)` directly so its detail reaches
`blind.update`.  `parse_arm` needs nothing.

**calibrate.py** — `select_arm`'s `searched` tuple becomes `("offset",
"field+offset", "field2+offset", "field2c+offset", "affine", "word")`
(every arm that minimises the search fold; a pre-existing gap the patch
arms would inherit), pinned by a test that walks `REGISTER_ARMS`.

**cli.py** — `--knob KEY=VALUE` (`action="append"`) on `ladder`, `read`,
`controls`, `score`: VALUE parsed as JSON when it parses, else the string
(`branches=state`, `ctx_state=true`, `patch_shrinkage=0.01`,
`L2=[{...}]`); merged into `config.knobs` AFTER a profile so the
operator's knob wins; `knobs_from` becomes `"profile:<name>+cli"` /
`"cli"`; the reserved names `pseudo_labels, refit, sibling_state,
disagree, ctx_offsets, ctx_state_adopted` are refused with a message.
`score.evidence_for_row` raises `ValueError` when `pseudo_labels` or
`refit` is in `config.knobs`.

**fixedpoint.py / ledger.py** — `_header` adds `knobs` (jsonable),
`reroll`, `reroll_rungs`; `row_to_dict` writes `certifying_arm`;
`attribution` adds `first_success_by_arm` and `only_by_arm` (from
`certifying_arm`, `reroll:<arm>` counted under the arm) and `ledger.md`
gets an "Arms" table beside "Rules" and "Rungs".

**`__main__.py`** — ruling 12's environment pin before the first numpy
import.

**bystate.py** — `--level N` restricts the aggregation to lanes at that
level (3 = 4800); prints per-lane rows beside the pooled (band, state)
table.

**Tests** (`test_analyzer_patch.py`, synthetic).  A new helper
`_state_raster(kernels, pitch_px, cells_yx_shape) -> (rasters, bits)` in
the test module paints one kernel per sibling state at every cell of a
small synthetic page (flat-deficit kernel for state 3, dot cores
elsewhere) and returns the matching three-plane bits; `Lane`, `KnownFrame`
and the footprint are built from it (the `test_analyzer_sample` fixtures
cannot express this stimulus and are reused only for their `Placement`
shape):
`test_grid_is_window_times_samples_per_cell_capped_at_native_pitch`;
`test_extract_recovers_the_checkerboard_under_an_off_diagonal_pose` (a
`native_affine` with real off-diagonal terms / rot_k 1: the sample at
grid offset (+1 cell, 0) reads the cell BELOW and (0, +1 cell) the cell to
the RIGHT, distinctly — a transposed grid fails);
`test_extract_refuses_outside_the_crop_and_never_clamps`;
`test_extract_is_chunked_and_identical_to_one_shot`;
`test_discriminant_matches_the_measurement_recipe` (against a 30-line
in-test port of `fit_lda` on a fixed matrix, `allclose` 1e-9);
`test_crossfit_scores_are_out_of_fold_on_every_training_row` (a filter
fitted on half A never scores a row of A);
`test_patch_score_fits_per_state_and_falls_back_to_subtract_where_starved`
(per-state d′ > box mean d′; the starved state's rows equal
`plane_score(subtract)` up to the shared scale);
`test_patch_score_reads_only_fit_fold_labels_and_never_the_targets_own_bit`;
`test_shuffled_fit_labels_collapse_the_discriminant` (held-out d′ ≈ 0,
`fitted` True);
`test_word_sites_are_excluded_from_per_state_fits_and_counted`;
`test_populations_share_one_scale` (per-population OOF sd ≈ 1);
`test_patch_score_is_repeatable_in_process` (`np.array_equal` twice, and
under a 4-thread pool);
`test_unmix_score_dispatches_patch_and_refuses_without_context`;
`test_read_carries_the_pose_and_crops_keep_the_raw_pixels_only_when_asked`;
`test_every_existing_arm_is_byte_identical_with_raw_crops_off_and_on`
(`read_rgb` values before/after, `np.array_equal`);
`test_patch_detail_carries_no_arrays`;
`test_patch_arms_parse_and_affine_and_word_search_under_subtract`
(`patch+offset`, `patch+committed`, `patch+field2+offset`, `patch+affine`,
`patch+word`; the substituted mode is recorded as
`register_objective_mode="subtract"`);
`test_nested_cv_is_refused_for_every_searching_register_arm`.  In
`test_analyzer_arms.py::test_unmix_modes_rank_the_way_the_measured_ladder_says`
exclude `mode in ("global",) + patch.PATCH_MODES`.  `test_analyzer_cli.py`:
`test_knob_values_parse_as_json_then_string`,
`test_reserved_knob_names_are_refused`,
`test_score_refuses_a_config_carrying_pseudo_labels_or_refit`;
`test_analyzer_ledger.py`: `test_certifying_arm_round_trips_through_the_ledger`,
`test_attribution_by_arm_counts_rerolls_under_their_arm`,
`test_the_header_records_knobs_reroll_and_reroll_rungs`.

**Acceptance**: lane green, pyflakes clean; `S0`, `S1`, `S1b`, `S12`, `I0`,
`I1`, `I2` of §3 run (one at a time) and reported in PLAN §6: on the 4800
lanes, per lane, S1's band M+Y error is below S0's on the same rows,
paired over tiles at > 2 SE (the level is reported against 0.119 with the
estimator difference of §0 stated, not gated); the 8-vs-16 verdict; the
floor from S12; every existing arm's offline score on the same ledger
unchanged (S0 = the H14 numbers); the peak RSS of S1 and I1 at 13
captures recorded.

### B2 — per-state calibration, state × context, `platt-state`, `L7c`, the state in controls, tests

Files: `analyzer/statecal.py` (grows), NEW
`analyzer/tests/test_analyzer_statecal.py`; edits `types.py` (the
`BRANCH_*` constants move here; `Combined.coefficients_by_state`,
`Combined.ctx_state_adopted`), `calibrate.py` (≈ 30 lines), `combine.py`
(≈ 40), `ladder.py` (≈ 50), `fixedpoint.py` (≈ 15), `controls.py` (≈ 6),
`arms.py` (2 lines: `ctx_state`, nothing else), `analyzer/tests/
test_analyzer_gaps_fix.py` (`_FakeInputs._cache`, `_reroll_world`).

**Import direction** (the cycle finding): `BRANCH_CLEANABLE`, `BRANCH_OTHER`,
`BRANCH_ALL` move from `calibrate.py:96-98` to `types.py`; `calibrate.py`
re-exports them for its callers; `statecal.py` imports numpy,
`holo.receiver.lib.spectral`, `holo.receiver.lib.pava`,
`holo.receiver.plugins.calibrate`, `holo.receiver.plugins.tiles`,
`holo.receiver.format.keystream`, `.types` — and NOTHING from `.calibrate`
or `.combine` (`state_platt_weights` takes the pooled fitter as a
callable argument).  `calibrate` and `combine` import `statecal`.  Pinned:
the closure test asserts `statecal` reaches neither `calibrate` nor
`combine`.

```python
BRANCH_STATE = "state"; STATE_BRANCHES = ("s0", "s1", "s2", "s3")
PLATT_STATE_MIN_PER_CLASS = 40          # the state's OWN classes, NOT the discriminating minority (degenerate per state)
def state_branch_masks(frame, plane, usable) -> dict[str, np.ndarray]     # {"s0".."s3": siblings & usable & (state==s), BRANCH_OTHER: usable & ~siblings}  — the SCORING masks
def state_fit_masks(frame, plane, usable, *, exclude_word_sites=True) -> dict[str, np.ndarray]   # the TRAIN masks: the same minus furniture_kind == 0 rows in the s* branches (ruling 11); BRANCH_OTHER unchanged
def apply_state_context(llr, bins, state, frame, plane, folds, usable) -> tuple[np.ndarray, dict]
    # per state s: context_decision on labels & (state==s) split fit/search (production floors 80/20, 40/10); apply_context_offsets(llr, where(state==s, bins, -1), offsets_s) where adopted; the input llr elsewhere
    # NOTE apply_context_offsets clamps at ±CTX_LLR_CLAMP (12): a state adopted where the pooled pass refused is newly clamped from LLR_CLIP (20) to ±12 — documented, pinned
    # detail: ctx_offsets_by_state (4 x 9, None where refused), ctx_state_adopted (4), ctx_state_reason (4), ctx_state_fit_labels (4), ctx_state_any_adopted (bool)
def state_platt_weights(stack, values, state, *, pooled_fit: Callable) -> tuple[np.ndarray, dict[int, np.ndarray] | None, dict]
    # pooled_fit(stack, values) first; per state with min(n0, n1) >= PLATT_STATE_MIN_PER_CLASS its own; detail platt_state_refused {s: reason}, platt_state_weights {s: tuple}
def sequential_state(frame, fp: TileFootprint, row, geometry, key) -> np.ndarray
    # (payload_cells,) int8: the in-tile scatter of state+1 through tiles._sequential_payload (dense 64x64 via (y%64)*64 + x%64, observed = in_tile), decoded -1..3; lane-independent
```

**calibrate.py**: `branch_masks(frame, target_plane, mode, usable)`
dispatches `mode == BRANCH_STATE` to `statecal.state_branch_masks` BEFORE
the two-population test (`covered_cells` follows for free); the per-branch
loop trains on `state_fit_masks(...)[name] & labels_all & folds.fit` when
`mode == BRANCH_STATE` (scoring masks unchanged), and
`detail["branches"][name]` gains `n_fit_word, n_fit_dust, n_fit_cargo`;
`calibrate(score, frame, target_plane, lfp, folds, *, branches="auto",
ctx_mode="none", page_context=None, local_context=None,
starved_fallback=STARVED_FALLBACK, stream_id=None, ctx_state: bool =
False, pseudo: PseudoLabelsRows | None = None)` (`pseudo` is B4's): after
the pooled context stage and only for `ctx_mode in ("production", "page",
"local5")`, `if ctx_state:` → `statecal.apply_state_context(...)`, detail
merged, `ctx_offsets`/`ctx_adopted` UNCHANGED (the pooled 9-vector and
verdict, consumed by `combine.pooled_ctx_offsets`); publish `label_state =
sibling_state(frame, plane)[rows]` beside `label_rows` (one more int8
array on the select fold, lane-independent) and `ctx_state_any_adopted`.
`arms.evidence_for` passes `ctx_state=bool(knobs.get("ctx_state",
False))`.

**combine.py**: `RULES += ("platt-state",)`; `combine(evidence, rule,
folds=None, *, labels=None, lane_ppc=None, agreement_threshold=…,
sibling_state: np.ndarray | None = None)`; `_label_view` also returns
`label_state` from `kept[0]` at the intersected rows (the way
`_discriminating_minority` reads `kept[0]`), and the `labels=` override
becomes a 4-tuple `(rows, llr_stack, values, state)`; the `platt-state`
branch: refuse to `platt` when `sibling_state is None`
(`platt_state_refused="no_sequential_state"`) or when the pooled Platt
refuses; else `statecal.state_platt_weights(stack, values, state,
pooled_fit=_platt_weights)`, and `llr = Σ_s [sibling_state == s]·(w_s @
stack_seq) + [sibling_state < 0 or s refused]·(w_pooled @ stack_seq)`.
`Combined.coefficients` = pooled weights (`pooled_ctx_offsets` keeps its
contract); `Combined.coefficients_by_state: tuple[tuple[float, ...] |
None, ...] | None = None` and `Combined.ctx_state_adopted: bool = False`
(any KEPT lane with a non-zero coefficient — pooled or per-state — whose
`blind["ctx_state_any_adopted"]` is true) (added, never renamed);
`combine_detail` carries both and `platt_state_refused`.
`contributing_captures(detail)` = the union of supports over
`coefficients` and every `coefficients_by_state[s]` (so a lane whose
pooled weight sits on the 0 bound while its state-3 weight is non-zero
COUNTS, and `independent_agreement` does not over-count).

**ladder.py**: `_rung_erase_state(llr_seq, row, key, bank, exposure,
knobs, metadata_bit) -> RungResult` ("L7c"): `state = knobs.get(
"sibling_state")` → refuse `no_sibling_state`; positions = `(state ==
knobs.get("erase_state", 3)) & (|llr_seq| < knobs.get("erase_tau", 2.0)) &
(llr_seq != 0)`; empty → refuse `no_state_cells`; order by `|llr_seq|`
ascending, cap `n − bank_active_bits − margin` (L7a's arithmetic), factor
`knobs.get("erase_factor", 0.0)`, below-floor exactly as L7a, then
`to_mother` + `_decode_and_gate("L7c", iters=knobs["iters"] (150),
"minsum-then-sp")`; detail `n_state_cells, n_erased, cap, erase_state,
erase_tau, erase_factor, bank_active_bits, n_observed`.  Dispatch `elif
name == "L7c"` before the `else: raise`.  NOT in `DEFAULT_RUNGS`, NOT in
`RUNG_ALIASES["L7"]`.  L3 (`_rung_ctx_iterate`) gains one refusal at its
head: `knobs.get("ctx_state_adopted")` → `state_context_adopted` (ruling
10), recorded in DESIGN §6's L3 row.

**fixedpoint.py** (`blind_key`): after `folds`, build the frame ONCE per
key (`frame_mod.known_frame(inputs, certs, footprint, key,
metadata_known=..., metadata_bit=...)` — the projections are memoised by
certs token, so this is cheap) and `state_seq = statecal.sequential_state(
frame, footprint, inputs.row, inputs.geometry, key)`; a module-level
helper `sequential_state_for(inputs, certs, key, halo, *, metadata_known,
metadata_bit) -> np.ndarray` does exactly that so `controls` can call it;
pass `sibling_state=state_seq` to every `combine_mod.combine` call (rule
loop and re-roll); derived knobs are ASSIGNED, not `setdefault`ed:
`rule_knobs["ctx_offsets"]`, `["disagree"]`, `["sibling_state"]`,
`["ctx_state_adopted"] = combined.ctx_state_adopted`; `blind_key` refuses
(`refusal="reserved_knob:<name>"`) a config whose `knobs` names any of
them; record `out["diag_state"] = {"n_state3": int, "n_state_known": int}`
(merged into `row.diag` by `run`), never the vector.  The AST pin on
`blind_key` (no `truth`/`oracle` names) holds.

**controls.py**: `_decode_at` (line 215) computes the donor's state via
`fp.sequential_state_for(...)` and passes `sibling_state=` to `combine`;
`null_arm`/`frame_null` reach `blind_key` and get it for free; a
`platt-state` rule in a controls run therefore runs the profile it names.

**Tests**: `test_analyzer_gaps_fix._FakeInputs` gains `self._cache: dict
= {}`; `_reroll_world` monkeypatches `fp.frame_mod.known_frame` (a
synthetic frame from `build_frame`) and `fp.statecal.sequential_state`
so the four existing `blind_key` tests keep running without pixels.
`test_analyzer_statecal.py` (on `test_analyzer_calibrate._synthetic_frame`
extended with four per-state score offsets and a `furniture_kind` column,
`tests/_synthetic.build_frame` + `through_cells` for the sequential
scatter, `test_analyzer_ladder.broken()` for L7c):
`test_sibling_state_convention_is_left_plus_two_right_ascending_minus_one_unknown`;
`test_statecal_imports_neither_calibrate_nor_combine`;
`test_state_branches_fit_one_map_per_state_with_own_standardisation`;
`test_state_fit_masks_exclude_word_sites_keep_dust_and_a_word_only_class_is_refused`;
`test_a_starved_state_is_priced_by_the_pooled_map_and_recorded`;
`test_covered_cells_agrees_with_calibrate_under_state_branches`;
`test_state_context_keeps_the_pooled_nine_vector_under_ctx_offsets`
(`pooled_ctx_offsets` accepts the row unchanged; `ctx_offsets_by_state` is
4×9; the pooled-refused / state-adopted case is clamped at ±12);
`test_state_context_refuses_per_state_below_the_production_floors_and_says_so`;
`test_l3_refuses_when_a_state_context_was_adopted`;
`test_platt_state_floor_is_the_states_own_minority_not_the_discriminating_count`;
`test_platt_state_applies_per_state_weights_and_pooled_elsewhere_and_publishes_both`;
`test_platt_state_without_a_sequential_state_falls_back_to_platt`;
`test_contributing_captures_is_the_union_over_pooled_and_state_supports`
(pooled w_l = 0, w_{s=3,l} > 0 → the capture counts);
`test_sequential_state_matches_the_cell_the_ladder_grid_names` (via
`ladder._cell_grid`);
`test_l7c_erases_state_cells_below_tau_within_the_cap`,
`test_l7c_reproduces_the_below_floor_refusal`,
`test_l7c_refuses_without_a_state_vector_or_without_state_cells`,
`test_l7c_is_direct_for_both_classifiers` (`oracle.is_direct`,
`score._is_list_rung`);
`test_blind_key_hands_the_state_to_combine_and_the_ladder_and_assigns_derived_knobs`
(`_reroll_world` + a spy on `combine`'s kwarg; a config naming
`sibling_state` is refused);
`test_controls_decode_at_hands_the_state_to_combine`;
`test_calibrate_publishes_label_state_on_the_select_fold`.

**Acceptance**: lane green; `S7`, `S8`, `I3`, `I4`, `I5` of §3 run and
recorded (per-state branch acceptance counts and word-site exclusion
counts on the C-dead-sibs rows, the pooled fallback on the M-only rows,
the state-3 R movement against MEAS §4's 0.797 → 0.836, `platt-state`'s
leave-one-out and refusals, `L7c`'s first-success).

### B3 — self-training, `rings`, the state-agnostic tier, `mixture`, aperture, E2, local5 scope, profiles, controls, tests

Files: `analyzer/patch.py` (+ tiers, modes, rounds, the local5 loader),
`analyzer/sample.py` (aperture), `analyzer/arms.py` (3 lines: aperture
knobs into `open_crops`; the local5 loader call), `analyzer/unmix.py`
(`PATCH_MODES` grows), `analyzer/types.py` (PROFILES,
`STREAM_ONLY_ARMS`), `measure/c-third-layer-20260906/dump_cells.py`
(knobs as JSON argv[3]), NEW `measure/c-third-layer-20260906/combine_blind.py`;
tests in `test_analyzer_patch.py`, `test_analyzer_gaps_fix.py` (profiles),
`test_analyzer_sample.py` (aperture).

- **State-agnostic tier (P1d)**: between per-state and `subtract`: one
  discriminant on ALL fit-fold labelled rows (state ignored; word sites
  kept — every state is present) when their count ≥
  `spec.min_labels_agnostic` (its OWN floor, knob
  `patch_min_labels_agnostic`, default 200) and both classes ≥
  `min_per_class`; cross-fit like every tier; scores every observed row
  whose state is −1 or whose state refused; `patch_agnostic_cells` counts
  them.  `patch_min_labels_per_state=1000000` therefore isolates P1d.
- **P2 self-training**: after the halo fit (per state, or agnostic), for
  `selftrain_rounds` rounds: the in-tile CARGO rows of that population —
  `fp.in_tile & fp.cargo & usable & inside & population & ~frame.known[:,
  plane]` (the metadata cell is never a pseudo row) — with `|score| ≥
  percentile(|score|, 100·(1 − keep))` become pseudo-labels `bit = score >
  0`, weight `selftrain_weight`, refit with them appended (halo labels
  weight 1) through the same cross-fit, rescore; deterministic; detail
  `patch_labels_from="halo+self"`, `pseudo_source="self"`,
  `patch_self_rounds`, `patch_self_cells`.  Pseudo rows never touch
  `frame` and never reach `calibrate`'s label arrays (they are cargo, not
  `known`).
- **`rings` (P1c)**: mode `"rings"`: features = per-channel mean over
  rings of width 1/S cell in radius from the cell centre (P/2 features per
  channel), same discriminant and ladder; `patch_features="rings"`.
- **`mixture` (M1)**: mode `"mixture"`: for state-3 cells, the two-Gaussian
  EM on the red channel of the tile's own state-3 population (init at the
  30th/70th percentiles, 20 steps, deterministic), score = log-ratio
  (high = ink) scaled by its own sd; every other cell `subtract`; refuse
  (fallback) below 100 state-3 cells.
- **A7 aperture**: `open_crops(lane, lfp, *, bound_dots, cell_dots,
  keep_raw=False, aperture_cells=anchor.APERTURE_CELLS,
  aperture_kind="box")`; defaults call `anchor.filtered_rgb` (byte-
  identical); otherwise `sample._filtered_rgb(raw, pitch, divisor,
  aperture_cells, kind)` (uniform, or `gaussian_filter` with σ =
  aperture·pitch/2.355 — the box's equivalent FWHM); the crop halo is a
  function of BOTH: `ceil(aperture_cells·pitch·(1.7 if kind == "gaussian"
  else 1.0)) + 2` (a gaussian truncates at 4σ ≈ 1.7·FWHM, so the default
  width already needs 19 px against `points_halo`'s 14).  Knobs
  `aperture_cells`, `aperture_kind` read in `evidence_for`; `Crops` records
  `aperture_cells`, `aperture_kind`.
- **E2**: `patch_search_mode="patch"` makes `_loss_of` evaluate the patch
  score on the offset grid (B1's context branch; cross-fit per pose);
  count `patch_search_fits` in the register detail.  The swim and the
  word pose stay under `subtract` (ruling 1).
- **local5 train scope (P1g)**: `patch_train_scope="local5"`: labels from
  the 24 neighbourhood tiles' own certified cargo via
  `unmix._sample_frame(inputs, certs, fp, forbidden=(ty, tx))` read at the
  committed pose (the `lane_mix` loop), features extracted PER TILE and
  memoised in `inputs._cache["patch_local_labels"]` keyed `(lane_id,
  stream, frame._certs_token(inputs, certs), page, (n_ty, n_tx),
  spec_key)` — one entry per (lane, TILE), shared by every target whose
  neighbourhood holds that tile; each entry holds at most
  `PATCH_LOCAL_MAX_ROWS_PER_TILE = 512` labelled rows chosen by
  `fold_hash` rank (deterministic) in float32 (295 KB at 144 features,
  1.2 MB at 576); the store is an LRU capped at `PATCH_LOCAL_MAX_ENTRIES =
  512` entries AND, since §8's finding 7 widened the harvest geometry, at
  `PATCH_LOCAL_MAX_BYTES = 512 MB` per process (both stated in the module
  docstring and pinned by a test that inserts 600 entries).  The fit is
  still per target tile (footprint labels + the memo's rows, cross-fit by
  `fold_hash`); the loader is `patchlocal.local_patch_labels(inputs,
  certs, key, lane, spec, unmix_mode=…, footprint_cells_yx=…) ->
  PatchLabels` called from `evidence_for`.
- **Profiles** of §2: `patch`, `patch-self`, `patch-refit` (B4 fills its
  rung; B3 registers the name with `L3f` absent from `reroll_rungs`),
  `patch-affine`, `everything+patch`; `STREAM_ONLY_ARMS["patch+word"] =
  ("C", "M")`.
- **measure/**: `dump_cells.py` takes an optional JSON knob dict as
  argv[3] (`AnalyzerConfig(knobs=...)`); NEW `combine_blind.py` = the
  combination of `analyze_combined.py` (clipped sum over the 4800 lanes,
  per-tile even/odd Platt, R from the state-reweighted mean information)
  over a per-lane LLR dump of ANY arm — the S9 route.

Tests: `test_self_training_is_deterministic_bounded_and_never_labels_a_known_row`
(rounds 0 vs 4: `label_rows/label_values/label_discriminating` identical,
the metadata row never a pseudo row, `patch_self_cells` ≤ keep·cargo);
`test_the_agnostic_tier_fires_where_siblings_are_unknown_and_has_its_own_floor`;
`test_rings_are_more_shift_robust_than_pixels` (a 1-px shift moves ring
features less, in norm);
`test_mixture_scores_state3_cells_only_and_refuses_small_populations`;
`test_default_aperture_is_byte_identical_and_a_gaussian_is_not_and_the_halo_grows_with_kind`
(the filtered value at a crop-boundary cell is unaffected by content
outside the crop);
`test_patch_search_mode_patch_evaluates_the_grid_under_the_patch_objective_and_not_the_swim`
(count `patch_search_fits`; `patch+affine` records
`register_objective_mode="subtract"`);
`test_local5_memo_is_per_lane_and_tile_row_capped_and_lru_bounded`
(key shape, 512-row cap, 600 inserts → 512 entries, the target tile
excluded);
`test_the_patch_profiles_parse_keep_the_default_first_and_nest`
(`patch ⊂ patch-self ⊂ patch-refit ⊂ patch-affine` on arms/rungs;
`everything+field2 ⊂ everything+patch`; every arm parses; `L3f` absent
from every `reroll_rungs`; `knobs_from`).

Acceptance: lane green; `S1c`, `S1d`, `S2`, `S3`, `S4`, `S5`, `S6` (×3),
`S9`, `S10`, `S11`, `K1`, `X1`, `X2` of §3 run and recorded — K1 (0
certificates on `null_arm` and `frame_null`, parity ≥ 80 %) BEFORE X1/X2's
numbers enter PLAN §6.

### B4 — the decoder-feedback rung `L3f`, the typed pseudo-label door, T1, tests

Files: NEW `analyzer/refit.py`, NEW `analyzer/tests/test_analyzer_refit.py`;
edits `types.py` (`PseudoLabels`), `ladder.py` (dispatch `elif name ==
"L3f"` with a function-local `from . import refit`, + the `temperature`
field in the L2 branch), `fixedpoint.py` (bind the closure, ≈ 10 lines),
`arms.py` (the `pseudo_labels` door → `patch.pseudo_rows`, ≈ 6 lines),
`calibrate.py` (`pseudo=` parameter, ≈ 15 lines), `patch.py`
(`extra_labels` from the door; `patch_labels_from="halo+bp"`), `types.py`
(`PROFILES["patch-refit"]` rungs and knobs).

**types.py**: `@dataclass(frozen=True) class PseudoLabels: source: str;
cells_yx: np.ndarray (m,2) int64; bits: np.ndarray (m,) uint8; weights:
np.ndarray (m,) float64` with `source in ("decoder",)` asserted in
`__post_init__` (P2's `"self"` labels never leave `patch_score`).
`PseudoLabelsRows = tuple[rows, bits, weights]` is the footprint-row form
`pseudo_rows` returns.

**refit.py** (blind; imports numpy, `.mother`, `.types`, `.combine`,
`.arms` at module level, `.ladder` INSIDE functions):

```python
DEFAULT_ROUNDS = 2; DEFAULT_CONFIDENCE_LLR = 4.0; DEFAULT_WEIGHT = 3.0; DEFAULT_MAX_EVIDENCE = 26
def confident_pseudo_labels(current_seq, posterior_seq, row, key, *, tau, metadata_bit) -> PseudoLabels
    # extrinsic = clip(posterior_seq - clip(current, ±LLR_CLIP), ±LLR_CLIP) exactly as ladder L3 (ladder.py:371-374);
    # confident = |extrinsic| >= tau & current != 0 (observed); index 0 excluded when metadata_bit is not None;
    # cells = ladder._cell_grid(row, key)[confident] + (ty*64, tx*64); bit = extrinsic > 0 (sequential positive = ink AS PRINTED, the frame's own convention); source = "decoder"
def refit_evidence(inputs, certs, key, halo, knobs_by_lane, evidence_set, rule, sibling_state, label_view, budget: list[int], pseudo: PseudoLabels) -> Combined | None
    # budget = [remaining]; for each item while budget[0] > 0: arms.evidence_for(inputs, certs, key, inputs.lane(item.lane), item.arm, halo_cells=halo, knobs={**knobs_by_lane[item.lane], "pseudo_labels": pseudo}); budget[0] -= 1; keep usable; None if none or budget exhausted before the first;
    # combine.combine(new, rule, labels=label_view, sibling_state=sibling_state)   — the ROUND-0 label view (ruling 9): coefficients identical, decoder-shaped LLRs never reach a rule fit
def rung_feedback(llr_seq, row, key, bank, exposure, knobs, metadata_bit, states) -> list[RungResult]
    # refuse "no_refit" without knobs["refit"]; entry = ladder._flip_source(states) or its own 150-iter decode;
    # per round r < refit_rounds: pseudo = confident_pseudo_labels(...); refuse "no_confident_bits" when empty;
    # combined = knobs["refit"](pseudo); refuse "refit_failed" when None, "refit_budget_exhausted" when the budget is 0; current = combined.llr_sequential;
    # mother = to_mother(current, row, key, metadata_bit); result, out = ladder._decode_and_gate(mother, bank, exposure, f"L3f.r{r}", iters=knobs["iters"] (150), mode="minsum-then-sp",
    #     extra={"round": r, "n_pseudo": m, "tau": tau, "weight": w, "unsat_entry": entry_unsat, "n_observed": ..., "refit_evidence_used": ...}, keep_hard=knobs["keep_hard"]); stop on certificate;
    # abort "no_unsat_gain" when out.unsat >= previous round's; the gate's exposure_exceeded refusal stops the rung
```

**fixedpoint.blind_key**: keep `knobs_by_lane[lane.lane_id] = knobs`
while building the battery; per key one `budget = [int(knobs.get(
"refit_max_evidence", DEFAULT_MAX_EVIDENCE))]` shared by every rule and
re-roll set (a per-KEY bound: with 4 rules and 13 lanes one round is 13
recomputations, so 26 = two rounds of one rule, or one round of two);
in the rule loop `rule_knobs["refit"] = functools.partial(
refit_mod.refit_evidence, inputs, certs, key, halo, knobs_by_lane,
tuple(chosen), rule, state_seq, combine_mod._label_view(chosen), budget)`;
in the re-roll loop the same with `evidence_set` (bound, but `L3f` is not
in the default `reroll_rungs`).  The closure captures the generation's
`snapshot_certs` object (memo hits) and mutates nothing but the budget.

**arms.evidence_for**: `pseudo = knobs.get("pseudo_labels")` → refuse
`refusal="pseudo_labels:not_typed"` unless `isinstance(pseudo,
PseudoLabels)`; after `known_frame`, `rows, bits, weights =
patch_mod.pseudo_rows(fp, pseudo)` (dropping rows that are `frame.known[:,
plane]` — a label beats a pseudo); handed to
`patch_score(extra_labels=(rows, bits, weights))` for patch modes and to
`cal.calibrate(..., pseudo=(rows, bits, weights))` when
`knobs.get("refit_calibration", True)`; `blind["n_pseudo_labels"]`,
`blind["pseudo_weight"]`, `blind["pseudo_source"] = pseudo.source`.
`frame.known` is never written (the DESIGN §4.5 assertion stays exactly as
it is).

**calibrate.calibrate(..., pseudo=None)**: per branch, the PAVA training
set becomes the halo `train` rows plus the pseudo rows inside the branch's
mask, each replicated `round(weight)` times with the pseudo bit as its
value (`_pava_nodes` is unweighted); the floors and every `n_labels*`
count stay on the halo labels alone; `detail["n_pseudo_fit"]` per branch;
`label_rows`, `label_values`, `label_discriminating`, `label_state` are
byte-identical with and without `pseudo` (pseudo rows are cargo, never
select-fold label rows); `label_llr` is the held-out view of the refitted
map.

**T1**: in the L2 branch, `t = float(spec.pop("temperature", 1.0))`;
`mother = to_mother(llr_seq * t, ...)` per variant (the shared mother is
built per variant when any variant carries a temperature); label
`f"L2:{mode}@{iters}" + (f"@t{t:g}" if t != 1.0 else "")`; `extra["temperature"]`.

**Tests** (`test_analyzer_refit.py`, on `tests/_synthetic`: `build_frame`,
`channel_llr`, `near_codeword_llr`; the crc32 spy of
`test_analyzer_ladder.py:349-362`):
`test_l3f_refuses_without_a_refit_closure` (and the `controls` null arm,
which hands no closure, sees `no_refit`);
`test_confident_bits_map_through_the_cell_grid_and_exclude_index_0`;
`test_pseudo_bits_are_printed_domain_bits` (a posterior of ±20 at the
printed bits yields pseudo bits equal to `through_cells(frame)` at the
named cells);
`test_the_door_refuses_an_untyped_pseudo_label_and_records_the_source`;
`test_l3f_runs_bounded_rounds_and_stops_on_a_certificate` (a stub closure
returning `channel_llr` at a lower error on the pseudo cells: round 1
certifies where L1 did not);
`test_l3f_aborts_without_unsat_gain`;
`test_l3f_stops_at_the_evidence_budget_and_says_so`;
`test_l3f_charges_every_distinct_codeword_once`;
`test_l3f_is_direct_for_both_classifiers`;
`test_pseudo_labels_leave_the_select_fold_arrays_and_no_pseudo_cell_is_a_label_row`
(`label_rows/label_values/label_discriminating/label_state` byte-identical
with and without `pseudo`; `set(label_rows) ∩ set(pseudo rows) = ∅`);
`test_refit_recombines_under_the_round0_label_view_so_coefficients_do_not_move`;
`test_pseudo_labels_never_touch_frame_known`;
`test_calibrate_pseudo_rows_join_the_fit_fold_by_integer_weight_and_leave_the_floors`;
`test_blind_key_binds_a_refit_closure_per_rule_with_one_budget_per_key`
(`_reroll_world` + a spy);
`test_temperature_scales_the_channel_and_labels_the_variant`.

Acceptance: lane green; `I6` (the `--limit 10` wall first), `I7`, `K2`,
`X3` and `X4` of §3 run and recorded (consults per `L3f` round in
`exposure_distinct`, `n_pseudo` per round, `refit_evidence_used`,
first-success by rung; K2's 0 certificates before X3's numbers enter PLAN
§6).

### B5 — wiring: CLI precedence and flags, conjunction grammar, README, DESIGN v0.4 §14, PLAN §6, APPROACHES finalization

Files: `analyzer/cli.py`, `analyzer/residue.py` (`target_rows`),
`analyzer/README.md`, `analyzer/DESIGN.md`, `analyzer/PLAN.md`, this
file; tests in `test_analyzer_cli.py`, `test_analyzer_residue.py`,
`test_analyzer_docs.py` (new).

- `--ctx-mode {none,ctx-known,production,page,local5}`; `--no-reroll`.
- Precedence: `_config` applies the profile, then re-applies any of
  `--arms/--rules/--rungs/--halo-cells` the operator gave explicitly
  (`args.<x> is not None`) — explicit flags win; README §2.4 says so.
- `residue.target_rows` accepts a `+` conjunction: `band:dead+stream:C`,
  `stream:C+siblings:M,Y`.
- README: §2.4 the new profiles and the precedence rule; §2.9 `score
  --knob`; a new §2.10 "Isolating one approach" pointing at this file's
  §1/§3, with every command spelled IN FULL inside fenced blocks tagged
  ```` ```analyzer-cmd ```` (no shell variables, no ellipses); §7 drops
  the "no knob door" limit and records the 13-capture peak RSS.  The
  parse test harvests ONLY `analyzer-cmd` blocks from README (this file's
  §3 rows use the §0.1 prefixes and are not harvested).
- DESIGN.md → v0.4: new **§14 "The third-layer C line (W8)"**: the
  measured mechanism (one paragraph citing MEAS), the patch family as an
  arm (§4.6 gets the `patch`/`rings`/`mixture` rows), per-state
  calibration/context as §4.7 amendments (incl. the ±12 re-clamp and the
  word-site exclusion), `platt-state` in §5 (with the union
  `contributing_captures`), `L3f` and `L7c` rows in the §6 rung table
  (status "BUILT, measured in PLAN §6 <date>") and L3's
  `state_context_adopted` refusal, the rulings of §4.0 above (the fold
  contract for a fitted score under §4.8), and §13's table re-tabled:
  patch discriminant → "BUILT (W8)"; temperature ladder → BUILT; pose
  list, joint turbo, neighbourhood head, full context, per-channel
  registration, disjoint-capture rule, defect map, deconvolution, seeded
  plane views, M's page field → status with the §5 reason; the
  format/physical items as leads with "not built".
- PLAN §6: `### 2026-09-06 — W8: the third-layer C line` with what was
  built (B1–B5), every §3 run's numbers (each read against the estimator
  named in §3), the controls rows, and the deviations (none from §1.2's
  contract expected; the `_sequential_payload` call is reused, not
  forked).
- This file: the status column of §1 updated from "new-W8" to
  "BUILT/measured <number>" per row; §3 becomes the record of the runs
  that were made.

Tests: `test_explicit_arms_win_over_a_profile_and_the_header_says_so`,
`test_target_conjunction_grammar` (`band:dead+stream:C`),
`test_readme_analyzer_cmd_blocks_parse` (every `analyzer-cmd` block's
lines through `build_parser().parse_args`).

Acceptance: lane green; `I8`, `K3`, `X5`, `Y` (and `X6` if the user rules
it) run and recorded; the docs cite the numbers actually measured, nothing
projected.

**AS BUILT (2026-09-06).**  All of the above landed, with three
refinements and one deviation worth naming.  (a) The precedence set is
wider than the spec's four flags: `--ctx-mode` and `--no-reroll` win over
a profile too, and `EXPLICIT_OVER_PROFILE` in `cli.py` is the one table
that says so.  (b) `knobs_from` becomes `profile:<name>+cli` when EITHER
an explicit flag or a `--knob` overrode the profile, not only for knobs.
(c) The knob bag is validated through `pure.spec_from_knobs` as well as
`patch.spec_from_knobs`, so a malformed `pure_*` knob is refused before
the run dir is loaded.  (d) DEVIATION: `read` is the one command where an
explicit `--rules`/`--rungs` is NOT re-applied over a profile — the
command itself forces them to `("sum",)` / `()` as a command-level
override, a profile has always overridden that, and re-applying the
operator's value there would silently change what `read` means (README §7
records it beside the existing `read`-ladders-anyway limit).  The
conjunction grammar also grew a third atom, `siblings:<S,...>`, matching
the row's certified-sibling SET, so the population every per-state
mechanism needs is `band:dead+stream:C+siblings:M,Y` — no list file.
The acceptance runs `I8`, `K3`, `X5`, `Y` are queued behind the other
chains (§6.4), not run: the machine was serialised for the whole build
day.

## 5. Deliberately not built this wave, and why

- **T2 pose-list decoding**: `register` returns ONE `Read`; a list of
  reads changes the arm contract (`Evidence` per pose) and the re-roll is
  already the attempt-count channel; measure X1–X3 first — if the band's
  tiles sit at R ≈ 0.95–1.0 (MEAS §5's 0.956 median), attempts matter and
  T2 is next.
- **J1 joint three-stream turbo**: a two-key rung with soft sibling
  states into `patch.py`; it is the mechanism for the 27/33 live C rows
  whose Y is open (where every per-state tier is empty), but it needs the
  Y side of the residue measured under X5 first (the §3 `Y` run) — if Y
  closes there, the C∧Y-open set shrinks to nothing and J1 is moot.
- **N1 neighbourhood head, N2 full neighbour-interaction context, R12
  per-channel registration**: DESIGN §13 leads that do not address the
  measured mechanism (a spatial, third-layer loss); each is a lane-scope
  fit that the patch filter's per-lane, per-state discriminant already
  contains a linear version of (N2's "context" is the surround of the
  patch).  Re-examine after S1/S9 say what the patch filter leaves.
- **DC the disjoint-capture rule**: a yield-and-evidence proposal for the
  corroboration half of DESIGN §5, not a repair of the measured
  mechanism; it composes with D1 (whose union `contributing_captures` is
  the accounting it would need) and is next after X5 shows what the
  patch family's certificates lean on.
- **DM defect map → erasures**: the L7 producer DESIGN §13 owes; C3 is a
  state-keyed producer for a different, measured failure (over-confidence
  on M+Y) and does not disposition it.  Needs its own oracle-guided
  discovery pass first.
- **A7b deconvolution**: a sheet-wide Wiener PSF from certified edges; the
  patch discriminant is a learned aperture and already contains a linear
  deconvolution of the 1.5-cell patch, so A7b is re-examined only if the
  `rings`/`patch` window sweeps (S1d) say the loss is wider than the
  patch.
- **PV2 seeded plane views**: owed since DESIGN §13; the unseeded plane
  view was a measured negative on exactly this residue (cols 30–31 0/0),
  so a seeded run is worth its 12–15 h only after the patch family has
  shown what the band's C looks like to a filter that reads it.
- **MF M's page field**: no M row is in the residue; owed as before.
- **C2 with an unconstrained per-state solver**: the per-state context
  reuses production's non-increasing solver; the measured "error falls
  with more C-inked neighbours" wants a non-monotone correction.  That is
  a new mechanism (N2's direction), not a knob; recorded, not built.
- **A per-(key, lane) crops/mix cache for the refit**: `refit_evidence`
  recomputes each lane's evidence from the crop up; a cache that lets a
  refit pay only for the score+calibrate legs needs a seam in `arms.py`
  (over the cap).  The budget and the re-roll exclusion bound the cost
  instead; I6's `--limit 10` wall decides whether the cache is next.
- **A combined-lane R in the `score` tool**: the scorer is per lane by
  design (DESIGN §7); the combined estimator stays a measure-side script
  (`combine_blind.py`) over a per-cell dump.
- **L5/L6**: still deferred behind the unsat histogram (DESIGN §6.1).
- **A patch filter in `evidence.blind`**: never — the ledger is 2.4 GB for
  156 rows today; only counts and small dicts are published.
- **The format-axis items F1–F3 and the physical items F4–F7**: rows,
  modulation constraints and prints are a print-day's work under
  `.claude/rules/hardware.md`, not the analyzer's; they are on the list so
  the next print day starts from MEAS §6.
- **A `pilot-first`-style rewrite of the sampler**: the per-plane
  registration line (PLANE-FIELDS) and E2's patch-objective search are
  where registration for C is measured; nothing here changes holo3.

## 6. The record — what the runs measured (2026-09-06)

**Every number here is a MEASUREMENT ON ONE SHEET.**  Sheet H is one
print, one engine, one scanner, thirteen captures; CLAUDE.md's rule
stands (ladders on multi-sheet minima, single sheets are existence and
regression evidence), and the self-discovery ruling of §4.0 adds the
rest: nothing below re-pins a default, and no gate here is a tuning
target.  The full narrative of the wave is `PLAN.md` §6 dated
2026-09-06.

**One analyzer process at a time**, so the runs were serialised through
chained scripts under `scratch/analyzer/W8/logs/` (`chain.sh` ->
`chain-b3.sh` -> `chain-b4.sh` -> `chain-b6.sh` -> `chain-b5.sh`, each
started by a watcher only when no `python -m analyzer` and no earlier
chain is alive).  The tree kept moving under that queue, so **the code
each run imported is part of its identity** — a process reads the `.py`
files as they were when it started.  Recorded per run below.

### 6.1 Blind, on sheet H's own residue (the certificates)

153 open C rows (`C-open.list` from the census: covered, not certified by
production), halo 48, one generation, 13 captures, 14 workers, single
arm lists spelled without a profile.

| run | arms | certificates | by band (dead/marg/live of 98/23/32) | wall | peak RSS | code |
|---|---|---|---|---|---|---|
| I0 | `subtract+offset` | **0** | 0 / 0 / 0 | 105 s | 36.0 GiB | B3 |
| I1 | `patch+offset` | **96** | 47 / 20 / 29 | 93 s | 35.3 GiB | B3 |
| I2 | both | 96 | 47 / 20 / 29 | 148 s | 35.3 GiB | B3 |
| I6 | both, `branches=state`, rungs L0,L1,L2,**L3f** | **102** | 53 / 19 / 30 | 319 s | 35.6 GiB | B4 |
| I7 | `subtract+offset`, T1 temperatures 0.8 / 1.25 | **0** | 0 / 0 / 0 | 118 s | 36.0 GiB | B4 |

`SCORE --ledger <pass>/ledger.jsonl` against the payload: **96 checked,
0 WRONG, 0 false accepts** on I1 and on I2; **102 checked, 0 wrong, 0
false accepts** on I6.  These rows survived production's whole run and
every prior analyzer pass, including the `everything+field2` passes that
built H14-union (5,579) and the newest run (5,580), so every certificate
is new.

**I6 is the decoder-feedback rung's first blind evidence, and it
certifies.**  `L3f.r0` is the FIRST-SUCCESS rung on 31 of its 102 rows —
with L4, L3 and L7 absent from that ladder, and against 96 for the same
two arms WITH those three rungs and without L3f (I2).  Across all four
rules 563 `L3f.r0` rows ran, 43 certified, 190 exited `syndrome_failed`
and 332 refused (overwhelmingly `no_confident_bits`, which is what B4's
fixture probe predicted for a residue that mostly sits far above the
waterfall); only 2 rows ever reached round 1.  Two cautions: the 31 is an
UPPER bound on the rows that needed L3f (with `all_rules` on, the driver
takes the first certificate in rule order, so a row whose `sum` ladder
reached L3f is credited to it even if `platt`'s L0 would have closed it),
and I6 moved three things at once against I2 — the rung list, the
`branches=state` knob and `refit_rounds` — so the +6 is a composite.  The
clean isolation is `--rungs "L0,L1,L2"` against `--rungs "L0,L1,L2,L3f"`
on one list, and it has not been run.

I7 measures the temperature ladder on the PINNED DEFAULT arm, which mints
0 certificates on this list anyway (I0).  Its 0 therefore says T1 does
not rescue a channel the detector cannot read; it says nothing about T1
over a patch channel, which is the run that is owed.

Attribution on I1/I2 (exact over rules, `all_rules=True`):
first-success `sum` 43, `platt` 41, `best` 10, `corr` 2; leave-one-out
`sum` 96, `best` 95, `corr` 94, `platt` 69 — `platt` is the rule 27 rows
had ONLY.  By rung: L0 92, L1 1, `L2:layered@300` 3 — ordinary production
decoders on a better-read channel, not an exotic rung.  By arm on I2:
`patch+offset` first-success 96, only-by-arm 95, via re-roll 0.

The BLIND quality signal (no truth in it): I2's select-fold paired test
adopted `patch+offset` over the pinned default on **527 of 531**
dead-band (lane, row) pairs, 134 of 135 marginal, 202 of 203 live;
selection refused for want of minority labels on 39 dead pairs.  The
published optimism of the fit is small and in the honest direction —
fit-fold error in-sample 0.0205 vs cross-fit 0.0296 (dead),
0.0229/0.0297 (marginal), 0.0146/0.0188 (live).  Label supply at halo 48:
~6.5 labels per feature per state (min 1.8) at 8 samples per cell, all
four states fitted on 524 of 570 dead (lane, row) pairs.

### 6.2 Offline, truth-scored, by (band, sibling state)

`analyzer score --arms <arm> --halo-cells 48` over the 156 C rows of the
H14-C ledger, read with `bystate.py --level 3` (the 4800-dpi lanes =
MEAS §4/§5b's population).  Median over rows of the per-row cell error:

| run | arm / knob | code | dead err | dead R | dead M+Y | marg M+Y | live M+Y | wall | RSS |
|---|---|---|---|---|---|---|---|---|---|
| S0 | `subtract+offset` (control) | B1 | 0.1040 | 0.748 | 0.2428 | 0.1400 | 0.1009 | 7.9 min | 35.4 GiB |
| S1 | `patch+offset` @ 8 samples/cell | B1 | 0.0915 | 0.755 | 0.1835 | 0.1298 | 0.1234 | 9.7 min | 35.5 GiB |
| S1b | `patch+offset` @ 16 | B1 | 0.0704 | 0.844 | 0.1620 | 0.0928 | 0.0707 | 14.5 min | 35.4 GiB |
| S1r | `patch+offset` @ 8 + the agnostic tier | B7 (mixed) | 0.0704 | 0.847 | 0.1659 | 0.0938 | 0.0715 | 10.4 min | 34.9 GiB |
| S12b | as S1r, per-state floor 600 | B3 | 0.0714 | 0.840 | 0.1690 | 0.0934 | 0.0711 | 10.1 min | 35.0 GiB |
| S12c | as S1r, per-state floor 1200 | B3 | 0.0895 | 0.777 | 0.2231 | 0.0982 | 0.0708 | 10.4 min | 34.9 GiB |
| S10 | as S1r, per-state floor ∞ (the AGNOSTIC tier alone) | B3 | 0.0919 | 0.773 | 0.2313 | 0.1042 | 0.0729 | 14.9 min | 33.9 GiB |
| S2 | as S1r + 4 self-training rounds | B3 | **0.0654** | **0.855** | **0.1639** | **0.0929** | **0.0714** | 54.7 min † | 28.8 GiB |
| S3 | as S1r + the patch-objective offset search (`patch_search_mode=patch`) | post-`903f71a` | 0.0698 | 0.847 | 0.1599 | 0.0913 | 0.0692 | 205.5 min ‡ | 20.6 GiB |
| S11 | as S1r + the 5×5 train scope (`patch_train_scope=local5`) | post-`903f71a` | 0.0861 | 0.784 | 0.1912 | 0.1328 | 0.0887 | 47.3 min ‡ | 33.1 GiB |
| S4 | `rings+offset` (radial means) | B3 | 0.1035 | 0.712 | 0.2627 | 0.1301 | 0.0970 | 9.8 min | 35.4 GiB |
| S5 | `mixture+offset` (label-free, state 3 only) | B3 | 0.0931 | 0.762 | 0.2170 | 0.1318 | 0.1025 | 9.0 min | 35.5 GiB |

† S2's wall is CONTENDED and is not comparable with the rest: three other
analyzer processes ran beside it (54.7 min real against 23.6 min of CPU;
every other row here had the machine).  It is recorded because the wall
is part of a run's identity, not because it measures anything.

‡ S3 and S11 are the last two rows of the S-series and the only two
here on the FAR side of `903f71a`, the review-fix commit that rewrote
`patch.py` at 18:27 on 09-06 (S11 finished 22:00, S3 at 01:26 the next
morning; every other row in the table ran before it).  Their isolations
stand — each is one `--knob` against the same fixed score command — but a
delta read against S1r crosses a code boundary, and nothing in the record
re-ran S1r on the far side.  Both walls are contended (S3 205.5 min real
against 126.5 min of CPU, S11 47.3 min against 25.7 min) and neither
measures anything; the CPU is the comparable cost, and S3's is the number
that matters: **7,591 CPU s against S1r's 614, 12 ×**, because
`patch_search_mode=patch` refits the filter at all 26 offset-grid points
instead of applying it once at the winner.  On these seven 4800-dpi lanes
S3 buys a tie with the control (dead err 0.0698 against 0.0704, R 0.847
both, M+Y 0.1599 against 0.1659) for that 12 ×, and **S11 is worse than
the control on every column** — of the `as S1r …` rows it shows the
largest regression in the marginal and live bands (M+Y 0.1328 against
S1r's 0.0938, and 0.0887 against 0.0715), while on dead err and dead R
it still reads better than S0, S1, S4, S5, S10 and S12c: the comparison
that holds is S11 against S1r, not S11 against the table.  Both
directions are the ones `W8-2026-09-06.md` §3.1 reaches pooled over all
thirteen lanes (0.164 and 0.192 M+Y at R 0.846 and 0.797), so neither is
an artefact of the lane population.  `local5` being the scope the whole
`pure` family pins is §6.10's second, independent reason to expect that
path's gap.

The acceptance is the PAIRED delta against S0 per lane over the same
(lane, row) pairs (`paired_bystate.py --level 3 --band <b> --state 3`),
and it is MET:

| comparison | dead | marginal | live |
|---|---|---|---|
| S0 -> S1 | **7 of 7 lanes past 2 SE** (−0.030 to −0.069, z −2.7…−7.4) | 0 of 7 (neutral) | 0 of 7 — a REGRESSION (+0.018 to +0.026) |
| S0 -> S1b | **7 of 7** (−0.052 to −0.093, z −5.8…−12.1) | — | **7 of 7** (−0.019 to −0.042) |
| S0 -> S1r | **7 of 7** (−0.052 to −0.091, z −5.7…−11.5) | — | **7 of 7** (−0.018 to −0.042) |
| S0 -> S2 | **7 of 7** (−0.045 to −0.093, z −4.4…−9.7) | — | **7 of 7** (−0.019 to −0.042, z −4.3…−7.5) |
| S0 -> S10 | 3 of 7 (−0.002 to −0.030) | — | **7 of 7** (−0.016 to −0.038, z −4.8…−7.3) |
| S0 -> S5 | **7 of 7** (−0.014 to −0.030, z −4.4…−8.5) | — | 0 of 7 (+0.000 to +0.003) |
| S0 -> S4 | 0 of 7 — a REGRESSION (+0.008 to +0.034, z +1.8…+7.8) | — | 3 of 7 (−0.003 to −0.009) |

**S10 decomposes the tier ladder, and it corrects the confounded
reading above.**  With the per-state floor at infinity only the
state-agnostic filter fits, and it takes the LIVE band's three-ink cells
0.1009 -> 0.0729 (7 of 7 lanes) while barely moving the dead band's
(0.2428 -> 0.2313, 3 of 7).  So the two tiers do different jobs: the
agnostic tier is what fixed S1's live-band regression, and the per-state
tier is the dead band's M+Y mechanism (S1r's further 0.2313 -> 0.1659 is
its alone).  Neither is sufficient; the ladder is.

**S4 is a clean negative and the sharpest confirmation of the mechanism
in the whole record.**  Radial means read the dead band's three-ink cells
WORSE than the box mean does (0.2428 -> 0.2627, 7 of 7 lanes rising)
while improving the ordinary states — which is exactly what a
shift-robust feature must do to a signal whose whole content is the
difference between a flat deficit and a dot core (MEAS §3).  The cheap
variant is cheap because it throws away the thing being measured.

**S5 reproduced its own offline prediction.**  The blind two-Gaussian
mixture, with no labels at all, moves the dead band's M+Y 0.2428 ->
0.2170 (7 of 7 lanes) and the live band not at all (0 of 7, +0.000 to
+0.003) — against MEAS §4's offline 0.219 -> 0.190 for the same
mechanism.  A supplemental arm of precisely this shape (wins on one
population, neutral elsewhere, cannot win a select fold) is what the
placement (P0d) was later built to carry.

**The wave's most useful negative is S1's live-band regression.**  On the
open live C rows the Y stream is open too, so the sibling state is
unproven for most of the tile; B1's per-state-only ladder fell straight
to `subtract` there, and ONE pooled PAVA map over two differently-scaled
populations reads worse than either alone.  Two independent changes fix
it and both fix it in every band — more samples per cell (S1b) and B3's
state-agnostic tier (S1r).  So the per-state tier is not the mechanism by
itself: it is the mechanism plus a scale problem, and a tier that covers
every cell is what makes it safe.

**S12 is CONFOUNDED and pins nothing.**  Under B3's code a state that
refuses no longer falls to `subtract` but to the agnostic tier, so
S12b/S12c moved the floor AND the tier together.  What survives is a
direction: the per-state filters do pay where they have labels (floor
1200 is clearly worse than 200/600), and one well-fed agnostic filter at
8 samples per cell reads about as well as four per-state filters at 16.
The floor-pinning clause of ruling 4 is withdrawn (§4.0); B7 replaced the
count with an admission on the tier's own cross-fit numbers.

### 6.3 Synthetic, in the test suite (the controls that do not need paper)

Pinned by tests, printed with `-s`: per-state held-out d' of the patch
filter 14.69 / 13.57 / 4.92 (states 0/1/3) against the box mean's 8.85 /
9.22 / 4.07; with the axes chosen by the run itself 15.09 / 14.56 / 5.16;
the agnostic tier on unproven-state three-ink cells 5.01 (auto 5.40)
against 3.91.  The permutation controls: shuffled fit-fold labels take
the discriminant's d' to −0.06 / −0.07 / +0.12 with `fitted` still True,
and under B7's admission every tier is REFUSED
(`crossfit_no_better_than_majority`) and the tile falls back to
`subtract`.  On a synthetic page that paints a 1.5-cell FLAT deficit for
sibling state 3 and a half-cell DOT for every other state — with nothing
telling it which is which — the run comes back with window 2.0 for state
3 and 1.0 for states 0 and 1: MEAS §3's mechanism, rediscovered blind.
The pure path's own control: pure select log loss 0.0240 against the PAVA
map's 0.0335 on the same scores.

### 6.3a The controls

**K2** (`controls --profile patch-refit`, 8 min, 17.6 GiB, B4 code) —
`null_arm` 0 certificates over its trial (the donor's pixels shifted 8
tiles; the truthful key certifies, the shifted one reaches unsat 25 and
never gates), `frame_null` 0 (the donor's frame shifted; truthful
certifies, null does not).  Both PASS.  **Its power denominator is 1**:
the run drew one trial of each because the `--targets` list it was given
holds few certified rows of the regime, so K2 is a smoke of the control
path under the patch profile, not a bound.  K1 (the same controls under
`--profile patch`, 100 parity + 5 null + 3 frame-null on the dead band's
CERTIFIED rows) and K3 (parity under the union profile) are the rows that
carry the statistics, and neither had run.

### 6.4 What has NOT run

At the last update of this document the serial queue had reached S2 in
`chain-b3.sh` (S1c, S1d, S6a–c, S11, S3, the S9 dump and K1 still owed),
X3 in `chain-b4.sh` (X4, X1, X2 owed), P0 in `chain-b6.sh` (P0M, P0S, P0R
owed), and `chain-b5.sh` (I8, K3, X5, Y5) had not started.  So: every
COMPOSITION (X1–X5, X7–X11), the aperture and channel isolations
(S1c, S1d, S3, S6a–c, S9, S11), the per-state calibration rows (I3–I5),
I8, the Y list and X6 are owed; the two statistical controls (K1, K3)
RAN on 2026-09-06/07 (§6.9) — on the certified dead-band rows, since
the controls cannot draw donors from a residue list.
X10/X11 — the placement — were specified after every chain was written
and are in none of them.

**No composition's numbers enter `PLAN.md` §6 before its K row has run**
(DESIGN §8: a run without controls is not a result).  §6.1's and §6.2's
isolation evidence needs no composition and stands on its own; K2 is a
control on the path those isolations used, at power 1.

Since that list was written, §6.5 has run X1 and P0 on an EIGHT-ROW
sub-list of the dead band, not on `C-open.list`; the full-list X1, X2,
P0M and every other owed row above stays owed.

**Superseded in part.**  Most of that queue has since drained.  The
offline isolations all ran and are reported in §6.2 and in
`W8-2026-09-06.md` §3.1 — S1c, S1d, S3, S6a–c, S10, S11, S12b–c, and the
S9 cell dump (`W8/S9-cells.npz`, whose combined-lane step is the part
still owed).  §6.9 ran K1, K3, H48, X10 and the re-priced pure path;
§6.10 ran the full-list X1, X2, X3, X4, P0, P0S and P0R plus the
`everything+patch` fixed point.  Read §6.10's closing list, not this
paragraph's, for what is left — and read its code-window paragraph
before treating any pair of those runs as an A/B.

### 6.5 First trial (2026-09-06) — the smoke runs

Three runs made after the chains above, on HEAD `903f71a` (B1–B8 plus the
review fixes).  **The machine was CONTENDED throughout** — four to nine
other `python -m analyzer` processes from `chain-b3/b4/b5/b6` held it,
load average 37 → 90 on sixteen cores — so **every wall below is a wall
under contention and measures nothing but itself** (the S2 precedent);
peak RSS and every count and error rate are unaffected.  Memory was
checked before each start (`vm_stat`: 63–68 GB free + inactive against
the 45 GB bar of the 2026-09-06 parallel ruling).  One sheet, eight
tiles: this trial pins nothing, promotes nothing and had no controls of
its own when it was written (K1 and K3 have since run — §6.9).

**The list.**  Eight open C rows of the dead band, `tx` 30 and 31, spread
over `ty`, every one with BOTH siblings certified — the `C-dead-sibs`
population, where every per-state mechanism can fire.  Built from the
census of §3's R0 and written to
`scratch/analyzer/W8-smoke-C-dead-8.list`:
`(0,1,30) (0,8,31) (0,13,30) (0,17,31) (0,26,31) (0,33,31) (0,43,30)
(0,48,31)`, all stream C.

**SC1 — `patch+offset` truth-scored at the DEFAULT halo, over BOTH C
ledgers.**  This is S1's arm at a footing no row of §6.2 has: halo 16
(the `HALO_CELLS` default for C) instead of the profiles' 48, both
`H13-C` and `H14-C` (172 rows against §6.2's 156), and HEAD's `"auto"`
knobs instead of B1's pins.

```
PYTHONPATH=src:. env314t/bin/python -m analyzer score \
    --ledger scratch/analyzer/ledgers-C/H13-C.jsonl \
    --ledger scratch/analyzer/ledgers-C/H14-C.jsonl \
    --payload scratch/analyzer/H14-pass1/payload.bin \
    --gt-dir scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm \
    --run-dir scratch/analyzer/H14-union --arms "patch+offset" \
    --workers 14 --out scratch/analyzer/W8-score-C-patch
```

39.1 min (contended), peak RSS 27.4 GiB, 172 rows, 14 certificates
checked, **0 wrong, 0 false accepts**.  Median over rows of the per-row
cell error (`bystate.py`):

| lanes | band | err_med | R_med | state0 | M only | Y only | M+Y |
|---|---|---|---|---|---|---|---|
| 4800 only (`--level 3`) | dead | 0.0611 | 0.896 | 0.0491 | 0.0455 | 0.0366 | **0.1518** |
| | marginal | 0.0490 | 0.941 | 0.0510 | 0.0483 | 0.0381 | 0.0845 |
| | live | 0.0386 | 0.985 | 0.0425 | 0.0569 | 0.0384 | 0.0601 |
| all 13 | dead | 0.0689 | 0.867 | 0.0496 | 0.0476 | 0.0390 | **0.1707** |
| | marginal | 0.0453 | 0.957 | 0.0520 | 0.0488 | 0.0391 | 0.0812 |
| | live | 0.0382 | 0.990 | 0.0392 | 0.0528 | 0.0350 | 0.0644 |

Paired per lane against the S0 control (`paired_bystate.py --level 3`),
over the 928 shared (lane, row) pairs:

| state | dead | marginal | live |
|---|---|---|---|
| 3 (M+Y) | **7 of 7** (−0.0475…−0.1135, z −5.0…−12.7) | **7 of 7** (−0.0195…−0.0521) | **7 of 7** (−0.0290…−0.0438) |
| 0 (blank) | **7 of 7** (−0.0120…−0.0220) | 6 of 7 (−0.0128…−0.0270) | **7 of 7** (−0.0109…−0.0237) |

**S1's live-band regression is gone at this footing**: live M+Y 0.1009 →
0.0601, 7 of 7 lanes, where B1's halo-48, 8-sample S1 had made it worse.
And paired against the halo-48 patch rows of §6.2 on the same lanes and
rows, the default-halo run is the BETTER of the two on the dead band's
three-ink cells — S1 6 of 7 lanes, S1b 4 of 7, S1r 4 of 7, S2 4 of 7,
none the other way — putting the pooled level-3 figure at 0.1518 against
their 0.1620–0.1835 and the control's 0.2428.  **This is a direction, not
an isolation**: halo, code generation and ledger set all differ between
SC1 and S1r, and the honest reading is only that *the wide halo is not
what carries the offline gain* — B7's self-chosen geometry at halo 16
reads the band at least as well as B1/B3's pinned geometry at halo 48.
The clean isolation (one score at halo 48 on HEAD, or one at halo 16 with
the B1 pins) has not been run.

**SM1 — the X1 composition on those eight rows** (`--profile patch`).

```
PYTHONPATH=src:. env314t/bin/python -u -m analyzer ladder \
    --run-dir scratch/holo3-H-with-facts-7-run.32018 \
    --targets "list scratch/analyzer/W8-smoke-C-dead-8.list" \
    --profile patch --max-generations 2 --workers 14 \
    --out scratch/analyzer/W8-smoke-patch
```

**8 of 8 certified**, 0 refused, one generation, 1,139.8 s of pass (18:59
of generation, 20.6 min of process), peak RSS 22.2 GiB.  `analyzer score
--ledger` against the payload: **8 checked, 0 wrong, 0 false accepts**.
The pass's own close is **VERIFIED** on 5,588 certificates (5,580 from
production + these 8), payload sha `0ad329fb…` = the emission's.

Attribution: first-success by rule `sum` 7, `platt` 1, and leave-one-out
8 for every rule (no rule was needed alone); by rung **L0 8** with
leave-one-out 1, so L0 carried seven of the eight; by arm `patch+offset`
8 and `patch+committed` 8 first-success, `subtract+offset` **0**, via
re-roll 0.  One row was corroborated by two independent captures.
Unsatisfied checks at exit: 34 of 79 rung outcomes reached **zero**.

Blind readings (`ledger_patch_readings.py --level 3`): the select fold
adopted `patch+offset` over the pinned default on **45 of 45** (lane,
row) pairs with 0 refusals; all four per-state tiers fitted on all 45;
fallback fraction median 0.000 and outside median 0.0000 (no cell fell
back to `subtract`); fit-fold error in-sample 0.0109 against cross-fit
0.0226 — optimism small and in the honest direction; label supply 6.4–6.9
per feature per state (min 2.6).

What B7's self-discovery chose, over the 89 (lane, row) pairs of the pass
(the walk runs per population, per tile, on the search fold):

| population | window 1.0 / 1.5 / 2.0 | red / rgb | 8 / 16 samples |
|---|---|---|---|
| state 0 | 11 / 71 / 7 | 50 / 39 | 87 / 2 |
| state 1 | 3 / 68 / 18 | 45 / 44 | 84 / 5 |
| state 2 | 6 / 68 / 15 | 49 / 40 | 80 / 9 |
| **state 3 (M+Y)** | 3 / 69 / 17 | **28 / 61** | 88 / 1 |
| agnostic | 0 / 44 / 35 | 7 / 72 | 76 / 3 |

Shrinkage 1e-2 on ~80 % of every population.  **The three-ink state is
the one that reaches for the other two channels** — 69 % rgb against
44–49 % for the states with at most one sibling — which is S1c's question
(`patch_channels=rgb`) answered per population by the run itself, and it
is what MEAS §3's mechanism predicts: where the red channel's deficit is
flat and diffuse, the M and Y channels are what say a pile is there.  The
agnostic tier takes the widest window most often (2.0 on 35 of 79).

**`--max-generations 2` was INERT here**: `max_generations` was 1 unless
`--fixed-point` was given (`cli.py:468`), so both passes here are single
generations and X6 — the cascade — is still unmeasured.  That silent
override is FIXED — §6.6, the user's ruling R1 — and a re-run of these
two commands now runs the two generations they asked for.

**SM2 — the PURE path on the SAME eight rows** (`--profile pure`, the
same command otherwise, `--out scratch/analyzer/W8-smoke-pure`).

**1 of 8 certified**, 5,726.0 s of pass (1:37:53 of process — the
contention, plus the `field2` fit, `patch_samples_per_cell=16` and the
`local5` harvest), peak RSS 44.5 GiB.  Its one certificate is `(0,33,31)`
— the row with the most certified neighbours (5) — `sum`/`L0`, both arms;
1 checked, **0 wrong**.  Unsat at exit: **1 of 29** rung outcomes reached
zero, against the patch pass's 34 of 79.

The pure path's own diagnostics say why, and they say it without truth:

| pure reading, 45 level-3 (lane, row) entries | s0 | s1 | s2 | s3 | other |
|---|---|---|---|---|---|
| `pure_error_by_state` (median) | 0.0304 | 0.0282 | 0.0251 | **0.0309** | 0.0294 |
| `pure_n_labels_by_state` (median) | 921 | 922 | 937 | 995 | **0** |

`pure_fallback_states = ["other"]` on **all 45** entries, and that
population is a median of **7,471 cells with zero labels**, priced by the
pooled `all`.  So the pure path hands BP a log-odds of
log(0.97/0.03) ≈ 3.5 for the band's three-ink cells, whose measured error
on the same sheet is **0.152** (SC1 above) — the filter's held-out error
on the certified NEIGHBOURHOOD is not its error on a dead-band tile, and
MEAS §5's "trained on certified tiles and applied to the band: M+Y 0.196"
already said so.  The calibration stage the pure path removes is exactly
what re-prices that gap; on this population removing it costs seven of
eight certificates.

**What SM1-vs-SM2 does NOT isolate**: `patch` ran five rules, three arms,
seven rungs and the re-roll; `pure` ran one rule, two arms, three rungs
and no re-roll.  The difference is the PROFILE, not the calibration — the
isolations are P0M (the same arms and knobs through the PAVA map) and
X10/X11 (the pure arms placed behind the battery), and neither has run on
this list.  What the trial does establish is that the pure path is not a
drop-in replacement for the patch battery on the dead band's C rows, and
that its own published error rates are the place to look first.

**`pure-refit` was NOT run.**  Its condition was that the first two
passes be quick; they were 39.1 + 20.6 + 97.9 minutes on a machine
running four to nine other analyzer processes.

**Artefacts**: `scratch/analyzer/W8-score-C-patch/`,
`scratch/analyzer/W8-smoke-patch/` (+ `-score`),
`scratch/analyzer/W8-smoke-pure/` (+ `-score`),
`scratch/analyzer/W8-smoke-C-dead-8.list`, logs under
`scratch/analyzer/W8-smoke-logs/` and
`scratch/analyzer/W8-smoke-patch.log`.

### 6.6 F1 — the generation cap made orthogonal (2026-09-06)

The user's ruling R1, verbatim intent: *"--max-generations without fixed
point: those two are orthogonal options."*  What the smoke found (§6.5)
was not a wrong number but a silent one — `cli.py` set
`max_generations=1` unless `--fixed-point` came too, so a spelled
`--max-generations 2` was discarded without a word and X6 went
unmeasured on a pass that had asked for it.

Built (`cli._generation_cap`, `fixedpoint.run`):

| flags | cap | what runs |
|---|---|---|
| neither | 1 | one generation — every pass in the record so far |
| `--max-generations N` | N | up to N, stopping early the moment a generation re-attacks nothing |
| `--fixed-point` | `AnalyzerConfig.max_generations` (8) | to convergence under the library's default cap |
| both | N | the cap bounds the convergence |

A cap is a BOUND, not a demand: the driver already stopped when a
generation certified nothing or re-attacked nothing, and that early stop
is what the cap now bounds rather than replaces.  Two consequences on
disk and on stderr, both aimed at the silence:

- the ledger header carries BOTH values — `max_generations` (the cap the
  pass ran under) and `fixed_point` (whether the operator asked for
  convergence) — plus `stop_reason`, one of `fixed point` (a generation
  re-attacked nothing: the pass is COMPLETE) or `cap reached` (the cap
  spent with a re-attack still pending; WHICH cap is what the two header
  values say — a third reason, `single generation`, was retired in the
  follow-up review because nothing in the driver can tell a spelled
  `--max-generations 1` from the one-generation default).  **A third
  value has since joined them**: `interrupted`
  (`stopdoor.STOP_INTERRUPTED`, the stop door of `259c183`), written when
  ctrl-C or SIGTERM ended the pass in order — the keys in flight finished
  and the rest stayed open — and carried beside two extra header counts,
  `keys_done` and `keys_skipped`, so a stopped pass cannot be read as an
  exhausted one.  The full enumeration is therefore `fixed point`, `cap
  reached`, `interrupted`;
- the pass's first line prints `generations <=N`, and a cap below 1 is
  REFUSED (`GENERATIONS REFUSED`, exit 2) rather than run as zero
  generations.

Nothing about a generation's work changed, so no measured number in §6
moves.  The run-matrix rows that spell `--fixed-point --max-generations
8` (§2, §3) still mean exactly what they meant; what is new is that the
cap alone is now a legal, honest way to spell a bounded cascade.  Tests:
`test_analyzer_cli.py` (the four flag combinations, the default cap
taken from `AnalyzerConfig`, the refusal) and `test_analyzer_fixedpoint.py`
(the synthetic cascade: N generations under a cap of N, an early stop
under a cap of 8, and each `stop_reason`).

### 6.7 F2 — the pure path re-priced (2026-09-06, after the smoke)

What SM2 measured was the halo-priced B6 path, and its own blind
diagnostics named the defect (§6.5): `e` came from the certified
neighbourhood, whose cells are easier than a dead-band tile's cargo, and
the unknown-state population — a median 7,471 cells with zero labels —
was priced by the pooled `all`.  The user's rulings on that record (R2:
unknown-state cells are erasures, uncounted; R3: no refit — the price
comes from the tile) are §4.0 amendment 15, and `analyzer/pure.py` was
rebuilt to them: the price per state is the equal-prior two-Gaussian
fit's error at the threshold on the tile's own cargo scores, the halo's
held-out error is a floor, unknown-state cells leave at LLR 0 and are
counted, and the blind detail says which bound (`pure_price_by_state`:
self / floor / adopted; `pure_price_source`).  The §8 disposition
"unknown-state cells PRICED rather than erased — FIXED as a record, not a
behaviour" is SUPERSEDED by R2: it is a behaviour now.

Synthetic, in the suite (`test_analyzer_pure.py`, F2 block): a tile
overlapping at a known Bayes error of 5 / 15 / 25 % with the halo at ~1 %
is priced at its own error within 0.02 / 0.03 / 0.04 (fixed-prior EM at
50 steps; 20 steps, `patch`'s count, read 15 % as 17-19 %, which is why
the count was raised); a well-separated tile prices at the halo floor,
whether the floor is the 1 % clamp or a halo that measures 10 %; a filter
trained on permuted labels reads its own tile at 0.29-0.36 per state
(near chance, without a label) and the halo's chance floor caps it at
0.45; on the synthetic pixel world the three-ink state's self price is
0.0078 against 0.0091 counted offline on the same cargo cells; permuting
the target bits of every cargo cell, or re-drawing the folds, moves the
self fit by nothing (it reads scores only).  One sheet, zero paper runs:
the re-priced path had not run on the eight-row list when this was
written, and its reading was to be `pure_price_by_state` on those 45
(lane, row) entries, where the self price on the dead band's three-ink
cells should sit near the 0.15 the sheet measures instead of the halo's
0.03.  It has now run (P0-fixed, §6.9): the fallback is gone and the
three-ink price rose 0.0309 -> 0.0402, but the self fit reads 0.031
where the sheet measures 0.15, so the prediction in this paragraph
FAILED and the yield did not move (1 of 8, the same row).

Record of the build: the P0 row (§1g), the X7/X9 rows (§2) and §4.0's
amendment 15 were in the working tree when F1's commit `74e2668` took
`analyzer/APPROACHES-2026-09-06.md`, so those three edits ride in that
commit; this note, the README and DESIGN paragraphs, `pure.py` and its
tests are F2's own.

### 6.8 Follow-up review dispositions (2026-09-06)

Two lenses (blindness+correctness, conventions) reviewed F1 (`74e2668`)
and F2 (`583b482`).  Both found the lane green, pyflakes clean, the
commits explicit-path and trailered, R1's four flag combinations exact
and F2 blind on the decoded cells.  Every finding, and what became of it:

- **[major] the POOLED halo still counted unknown-state labelled rows**
  (`pure.py`, `pooled = measure(..., train, ...)`) — **FIXED**.  R2 takes
  those cells out of the decode; it takes them out of the PRICING too,
  and the pool is what every `pure_fallback_states` state's threshold and
  floor come from.  In production such a row carries a different
  discriminant's score (`patch.fallback_population`, another scale), so
  on the open-Y / dead-band tile where a state's halo starves — exactly
  where the fallback fires — the sign threshold was being pulled by
  non-filter scores.  Reproduced on the R2 fixture before the fix (pooled
  `n_labels` 745 vs 491 known-state rows; shifting only the unknown-state
  rows' scores by +5 moved the pooled threshold 0.0 → 1.71 and its error
  0.01 → 0.45).  The pool is now `train & (state >= 0)`, pinned two ways:
  `pure_pooled.n_labels` equals the per-state label sum, and shifting
  those rows' scores moves the pooled threshold, error and count by
  nothing (`test_the_pooled_halo_counts_no_unknown_state_row_either`).
  The §6.7 and amendment-15 wording that said the fallback "is gone" is
  corrected above: it was gone for the decoded cells only.
- **[minor] empty states listed as pooled fallbacks** — **FIXED**.  A
  state owning zero cells of the tile now records `priced_by=None` /
  `price_source=None` and never enters `pure_fallback_states` (that
  diagnostic was the §6.5 signal, so it may not count states that priced
  nothing).  Pinned by
  `test_a_state_that_owns_no_cell_of_the_tile_claims_no_price`.
- **[minor] a state with 2..99 cargo cells priced at the halo floor at
  full weight** — **FIXED, and by mechanism rather than a note**.  That
  is §6.5's defect in miniature (the halo's number is a floor, not an
  estimate).  A state whose own cargo is too small to fit now takes the
  TILE-POOLED self fit (all known-state cargo as one population) read at
  its own threshold: pooling smears the components by the per-state
  offsets, so it reads the overlap pessimistically and can only RAISE the
  price above the floor.  When the tile itself cannot be fitted the floor
  is all there is, and the ledger now says how much of the tile that
  covered (`pure_floor_only_cargo_cells`).  Pinned by
  `test_a_state_too_small_to_fit_takes_the_tiles_pooled_self_price`.
- **[minor] `pure-refit` let the self price read pseudo-trained cells
  (R3)** — **FIXED** without retiring the profile: `arms` now passes the
  decoder's pseudo ROWS to `pure_llr` (never as labels — there is no map
  to refit), which subtracts them from the self population, so the price
  is read only on cells the filter never saw.  `pure_self_excluded_cells`
  records how many.  Pinned by
  `test_pseudo_trained_rows_are_subtracted_from_the_self_population`
  (the price equals the one measured with those rows deleted from the
  tile).  `pure-refit` stays runnable and recommended by nothing.
- **[minor] `single generation` claimed a distinction the driver cannot
  make** — **FIXED by retiring the reason**.  An explicit
  `--max-generations 1` and the one-generation default reach the loop
  identically, so `stop_reason` is now `cap reached` in both and the
  header's `max_generations` / `fixed_point` say which cap it was.  R1's
  semantics were verified exact by both lenses and are unchanged.
- **[minor] the shuffled-label test does not by itself catch a leak** —
  **FIXED as a record**: the claim moved to where it is proved.  The leak
  detector is the cargo permutation in
  `test_the_self_fit_has_no_labels_and_no_fold_in_it`; the shuffled test
  says the price COLLAPSES with the filter, which is its own claim.
- **[minor] R1's "a cap below one is refused" held only at the CLI** —
  **FIXED**: `AnalyzerConfig.__post_init__` refuses `max_generations < 1`,
  so `fixedpoint.run` can no longer be handed a cap that runs zero
  generations and then writes `generations_run: 1`.  Pinned by
  `test_a_cap_below_one_is_refused_by_the_config_not_run_as_zero`.

Nothing measured moved at the time of these fixes: SM2's rerun was
still owed and was still the reading of the re-priced path (§6.7).  It
ran on 2026-09-07 as P0-fixed (§6.9), with the major fix in it.  Lane
670 passed / 69 skipped.

### 6.9 Follow-up runs (2026-09-06/07)

The five runs the smoke owed — K1, K3, H48, X10 and SM2's rerun on the
re-priced pure path — plus the two control runs those first two turned
into.  (This is the section the task called §6.6; that number was
already F1's, so the follow-up runs are §6.9.)  Every run below is the
same one sheet and, for the blind passes, the same eight dead-band C
rows as §6.5: **it pins nothing and promotes nothing.**  Artefacts under
`scratch/analyzer/W8-followup/<name>`, logs and per-run
`HEAD`/wall/exit metadata under `scratch/analyzer/W8-followup/logs/`.

| run | commit at launch | wall | result |
|---|---|---|---|
| K1 — `controls --profile patch`, targets the **open** dead-8 list | `ac3b7fc` | 41 s | **REFUSED**: `ControlError: parity_sample: no production certificate to draw` |
| K1-certified — the same on `W8/C-dead-certified.list` | `ac3b7fc` | 28 min 33 s | null 0/1, frame-null 0/1, **parity C 0 of 8** (bar 0.8) → `CONTROLS FAILED: ['parity']`; 0 disagreeing with production |
| K1-power — null + frame-null at full sample, `--parity 0` | `47aebcc` | 3 h 00 m | **null arm 0 certificates in 8 trials, frame null 0 in 8**, power denominator 8/8, exposure 8, E[false] 1.9e-9 |
| K3 — `controls --profile patch-refit`, the open dead-8 list | `259c183` | 12 s | **REFUSED**, same reason |
| K3-certified — the same on `W8/C-dead-certified.list` | `259c183` | 9 min 34 s | null 0/1, frame-null 0/1, **parity C 0 of 8 — bit-for-bit K1-certified's**; 0 disagreeing |
| H48 — `score --arms "patch+offset" --halo-cells 48`, SC1's footing | `3e178f0` | 11 min 53 s | 172 rows, 14 certificates checked, **0 wrong, 0 false accepts**; dead-band M+Y 0.1640 against SC1's 0.1518 |
| X10 — `ladder --profile patch-then-pure`, 1 generation | `3e178f0` | 5 min 05 s (+1 s score) | **8 of 8 certified**, 0 wrong; **the placed pure arms never fired** (`reroll.deferred` absent from every row, `via re-roll` 0) |
| P0-fixed — `ladder --profile pure`, 1 generation | `3e178f0` | 14 min 40 s (+1 s score) | **1 of 8 certified** — unchanged from §6.5's SM2 — 0 wrong; the same row `(0,33,31)` |

Peak RSS: K1 16.7, K1-certified 20.2, K1-power 17.6, K3 17.6,
K3-certified 20.3, H48 35.4, X10 23.4, **P0-fixed 72.0 GiB**.

**Two conditions before any wall above is read as a cost.**  First, the
machine: K1, K1-certified and K1-power ran beside the user's own H16
pass and two measurement-chain ladders (the S2/§6.5 precedent — those
three walls measure nothing but themselves), and by K3 the machine had
largely emptied, which is most of why H48 took 11.9 min where SC1's
identical-shape score took 39.1.  Second, the tree: another builder was
committing to `analyzer-w8` throughout, so each run records its own
launch `HEAD`.  `analyzer/` is byte-identical between `ac3b7fc` and
`47aebcc` (that commit is `measure/` only), and — the one that matters
for H48 — the whole `patch+offset` score path (`patch.py`,
`calibrate.py`, `statecal.py`, `unmix.py`, `autoknobs.py`, `score.py`)
has not changed since `903f71a`, the HEAD SC1 ran on; the single
`arms.py` delta in that window passes `pseudo_rows` into `pure_llr` and
touches no map path.  `259c183`/`3e178f0` (the stop door) rewrote
`fixedpoint.py`, `cli.py` and `ledger.py`, so X10 and P0-fixed ran a
driver SM1 and SM2 did not; the arm, filter and calibration modules they
exercise are the same ones.

**K1 and K3 — the controls, and why the list refused them.**  Both
control commands, pointed at `scratch/analyzer/W8-smoke-C-dead-8.list`
as asked, refuse in seconds and refuse correctly: that list is the
RESIDUE, and every control in DESIGN §8 draws its donors from PRODUCTION
CERTIFICATES — the null arm shifts a certified tile's pixels, the frame
null shifts a certified tile's frame, parity re-derives certificates —
so eight open rows leave all three nothing to draw and `parity_sample`
raises before the other two are even reached.  The applicable footing is
the README's own K1 line: the certified rows of the same regime,
`scratch/analyzer/W8/C-dead-certified.list` (eight production-certified
C rows of the dead band, `tx` 30/31).  There the null arm and the frame
null pass under both profiles, and **parity fails, 0 of 8, in every one
of its three configurations** — `subtract+offset`/production,
`subtract+committed`/ctx-none and `head+offset`/production alike, with
(a fourth, `patch+offset`/production, was added to
`controls.PARITY_CONFIGURATIONS` on 2026-09-07 in consequence of this
run: none of the three could read tiles the patch family certifies, so
the 0 of 8 measured the control's coverage as much as the run's parity;
the gate remains the default arm, and the new configuration is reported
beside it.  **It ran the same day — §6.11's R4 — and it re-derives 7 of
8 under `patch` and 8 of 8 under `patch-refit`, clearing the 0.8 bar in
both, while the gate still fails at 1 of 8.  So the suspicion above is
now measured: the 0 of 8 was the control's coverage.**  Two caveats
R4 also measured: the old three read 1, not 0, at the profiles' new
halo of 16, and parity is no longer profile-independent, because
`patch+offset` reads the patch knobs that `patch-refit` changes)
`n_disagreeing_with_production` 0 throughout (nothing was re-derived
wrongly; nothing was re-derived at all).  That is not a new failure:
README §5 already reads sheet H's C parity as an ATTEMPT-COUNT gap
(49/60 stratified for the default arm against 56/60 for the whole
battery), and this sample deliberately selects the hardest eight rows on
the sheet — the dead band's own certificates, which production won with
six tools and hundreds of attempts each.  Restricted to that regime the
attempt-count gap is total.  The reading to keep is the pairing: **on
the dead band the default single configuration re-derives none of
production's certificates, and the battery certifies eight of eight open
rows beside them** (SM1, X10).  Note also that parity is
profile-independent by construction — `parity_sample` replaces arms,
rules and rungs with `PARITY_CONFIGURATIONS` and turns the re-roll off —
and K3-certified's numbers came back identical to K1-certified's, which
is the measured version of that claim rather than the argued one.

**K1-power — the control that carries weight.**  `--null 5
--frame-null 3` is one trial per stream, and a null arm with a power
denominator of 1 says almost nothing, so K1 was re-run at
`--null 24 --frame-null 24` over the same eight certified rows: **8
trials each, 0 certificates each, all 8 truthfully certifying**, donor
`min_unsat` 14–100, exposure 8 distinct consultations for E[false]
1.9 × 10⁻⁹.  The patch battery, the per-state machinery and the whole
ladder, run on another tile's pixels at this tile's address, certify
nothing.  It cost 3 h for 16 decodes (≈ 11 min each, against SM1's 2.4
min average) and the reason is structural: a truthful decode STOPS at
its first certificate, a null decode never stops, so a control exhausts
every arm, rule, rung and the re-roll on every key.  That is the price
of control power on this profile, and it is why K3's high-power arm is
owed rather than run.

**H48 — the halo isolated, and the wide halo loses.**  SC1 (§6.5) read
the default halo 16 as at least as good as the pinned halo 48 on the
band's three-ink cells but called it *"a direction, not an isolation"*,
because halo, code generation and ledger set all differed.  H48 is that
score re-run with **only `--halo-cells 48` changed** — same two C
ledgers, same run dir, same gt dir, same arm, and (per the drift check
above) the same score-path code.  Pooled over the 4800 lanes: dead-band
M+Y **0.1518 → 0.1640**, dead all-cell 0.0611 → 0.0704, R_med 0.896 →
0.843; marginal M+Y 0.0845 → 0.0812; live M+Y 0.0601 → 0.0670.  Paired
per lane (`paired_bystate.py --level 3 --state 3`), halo 48 against halo
16 over ~1,014 shared (lane, row) pairs: on the **dead** band it is
WORSE on 5 of 7 lanes beyond 2 SE (z +4.3, +4.2, +3.4, +2.4, and two
lanes flat) and better on exactly one (z −5.3); on **live** worse on 3
of 7 beyond 2 SE and better on none; on **marginal** no lane moves.  So
the wide halo is not merely failing to carry the offline gain — on the
population this wave exists for it costs about a point of cell error and
half a point of R.  The 48 in the `patch`, `patch-refit` and `pure`
profiles is B1's pin, not a measured choice, and this is the first run
that puts a number on it.  One sheet, one arm: it is a candidate for
B7's self-discovery treatment (a per-population halo chosen on the
search fold), not a new default.

**X10 — the placement's yield on this list is exactly zero, for the
reason the row predicted.**  `patch-then-pure` is the `patch-refit`
battery with `pure+committed` and `pure+field2` placed in the re-roll
(`reroll_only_arms` in the header), so they are computed only for a key
the battery could not close.  It closed all eight — **8 of 8 certified,
0 wrong, 0 false accepts**, exposure 8 for E[false] 1.9 × 10⁻⁹ — and
therefore `reroll.deferred` is absent from every row and `via re-roll`
is 0 for every arm: the pure arms were never computed.  §3's X10 row
asked for exactly this check and it holds.  Two second-order readings.
The composition is not SM1's: `patch-then-pure` carries `L3f` and the
self-training/refit knobs that `patch` does not, and two of the eight
rows — `(0,13,30)` and `(0,17,31)` — first-succeed at **`L3f.r0`**
instead of L0/`platt`, so the decoder-feedback rung is doing real work
on this list where §6.5's battery reached the same eight by other means.
And the pass took 4.8 min against SM1's 19.0, which is the
empty machine, not the profile.  What X10 does NOT measure is the pure
path's placed yield — for that it has to run on a list the battery
cannot close, which is the honest form of the X10 question and is owed.

**P0-fixed — the re-priced pure path: the defect is gone, the yield is
not.**  This is SM2's rerun after F2 and the follow-up review's major
fix, on the same eight rows, and it certifies **1 of 8** — the same row
`(0,33,31)`, at L0/`sum`, 0 wrong — against the patch battery's 8 of 8.
The re-pricing did do what it was built to do.  On §6.5's own footing
(`patch+committed`, the 45 level-3 entries):

| level-3 median | s0 | s1 | s2 | s3 (M+Y) | other |
|---|---|---|---|---|---|
| SM2 `pure_error_by_state` | 0.0304 | 0.0282 | 0.0251 | 0.0309 | 0.0294 |
| P0-fixed `pure_price_by_state.floor` | 0.0304 | 0.0282 | 0.0251 | 0.0309 | — |
| P0-fixed `…self` | 0.0059 | 0.0057 | 0.0035 | 0.0306 | — |
| P0-fixed `…adopted` | 0.0326 | 0.0292 | 0.0269 | **0.0402** | — |
| `pure_price_source` = self (of 45) | 2 | 2 | 2 | **19** | — |

`pure_fallback_states` is **empty on all 45 entries** (it was `["other"]`
on all 45), `pure_erased_cells` is a median of **7,471** with
`pure_cargo_erased_cells` **0** — the unknown-state population that SM2
priced through the pooled `all` map now leaves at LLR 0 and is counted,
and not one cargo cell was erased to get there.  The floor column
reproduces SM2's numbers exactly, which is the proof that SM2's whole
price WAS the halo; the tile's own fit binds on the three-ink state 19
times of 45 against 2 for every other state, i.e. the mechanism fires
precisely on the population it was designed for; and the adopted
three-ink price rises 30 % (0.0309 → 0.0402), against 4–7 % elsewhere.
**And it is still not enough.**  The sheet measures 0.15–0.16 on those
same cells (SC1, H48 above), so BP is still handed |L| ≈ log(0.96/0.04)
≈ 3.2 where the honest figure is ≈ 1.7, and the unsatisfied-checks
histogram barely moves (0-bucket 1 of 29 in both; mass shifts from
100–499 into 50–99).  The finding is therefore sharper than SM2's and it
is about the ESTIMATOR, not the plumbing: an equal-prior two-component
fit on the tile's own scores reads a 15 % overlap as 3 %, because when
the filter is this weak the two components it finds are not the two
classes.  The synthetic block of §6.7 measured that estimator against
KNOWN 5/15/25 % overlaps and it was within 0.03 — on paper, on the dead
band's three-ink cells, it is out by 5×.  That is the next question for
the pure path and it is now a specific one: the halo floor and the
self fit disagree by 5× with the truth on the same side, so a price the
tile can pay has to come from something other than the score
distribution's shape alone.  P0-fixed also cost **72.0 GiB peak** on an
otherwise idle machine (SM2 measured 44.5 under contention) — the
`local5` harvest at 16 samples per cell is the most expensive
configuration in the wave and the one-at-a-time rule applies hardest to
it.

**What these eight runs leave owed.**  K3's high-power null/frame-null
(the 3 h price above is why it did not run beside K1's); the X10
question on a list the battery cannot close; a parity sample large
enough to put an interval under "the dead band re-derives none" (n = 8
gives a 95 % upper bound of 0.37); and, for the pure path, an estimator
for its own error that is not the two-component fit.  None of the above
changes a default and none of it is a promotion.

### 6.10 The full-list compositions, the pure path and the fixed point

The rows §6.4 listed as owed have run.  X1–X4 and the three pure
profiles all went over the FULL `scratch/analyzer/W8/C-open.list` — the
153 open C rows of `holo3-H-with-facts-7-run.32018`, halo 48, one
generation, 14 workers — not §6.5's eight-row sub-list, and the
`everything+patch` fixed point went over the whole 200-row residue.
`W8-2026-09-06.md` §3.2 carries the same runs priced in CPU seconds;
what follows is §6.1's shape — the band split and the verification
score — so the two tables answer different questions about one set of
runs.  Same sheet, same day: **it pins nothing and promotes nothing.**

| run | profile | certificates | by band (dead/marg/live of 98/23/32) | checked | wrong | wall | peak RSS | code |
|---|---|---|---|---|---|---|---|---|
| X1 | `patch` | **127** | 73 / 23 / 31 | 127 | **0** | 1 h 04 | 42.2 GiB | B5 |
| X2 | `patch-self` (X1 + self-training) | 122 | 69 / 22 / 31 | 122 | 0 | 1 h 21 | 33.7 GiB | B5 |
| X3 | `patch-refit` (X2 + `L3f`) | 127 | 73 / 23 / 31 | 127 | 0 | 1 h 49 | 36.1 GiB | B4 |
| X4 | `patch-affine` (X3 + affine) | **128** | 74 / 23 / 31 | 128 | 0 | 4 h 04 | 33.6 GiB | B4 |
| P0 | `pure` | 50 | 16 / 14 / 20 | 50 | 0 | 2 h 13 | 65.6 GiB | B6 |
| P0S | `pure-self` | 39 | 14 / 12 / 13 | 39 | 0 | 3 h 15 | 63.6 GiB | B6 |
| P0R | `pure-refit` | 38 | 25 / 8 / 5 | 38 | 0 | 2 h 42 | 77.0 GiB | B6 |
| SM1 = §6.5's smoke | `patch`, the 8-row dead sub-list | 8 of 8 | 8 / – / – | 8 | 0 | 21 min | 22.2 GiB | B5 |
| SM2 = §6.5's smoke | `pure`, the same 8 | 1 of 8 | 1 / – / – | 1 | 0 | 98 min | 44.5 GiB | B6 |
| H16 | `everything+patch`, `--fixed-point`, the WHOLE 200-row residue | **200 of 200** | C 6 live + 45 marg; Y 52 live + 97 marg | 200 | 0 | 4 h 51 | — | B5 |

SM1/SM2 are §6.5's two runs repeated here for one reading of the ladder,
not new runs; H16 has no `/usr/bin/time` wrapper, so its RSS is unknown
and its CPU is the estimate `W8-2026-09-06.md` §3.3 marks as an estimate.
X1's `— (unscored)` is now spent: scored 2026-09-07 against
`H14-pass1/payload.bin`, **127 checked, 0 wrong, 0 false accepts**, and
P0S and P0R were scored the same way in the same minute.  With those
three, **every blind pass of this wave now carries a verification score
and every one of them is zero wrong.**

**WHICH PAIRS ARE ACTUALLY A/B, and which are not.**  `chain-b4.sh` ran
these four back to back in one serial sequence — X3 15:43–17:32, X4
17:32–21:36, X1 21:36–22:40, X2 22:40–00:01 (from the `.err` mtimes and
each run's own wall) — against a worktree another builder was committing
to, and **`903f71a`, the review-fix commit that rewrote `patch.py` (521
lines), `autoknobs.py`, `calibrate.py`, `combine.py`, `statecal.py`,
`refit.py` and `arms.py`, landed at 18:27, DURING X4's four-hour run.**
So X3 and X4 loaded their code before that rewrite and X1 and X2 after
it.  The consequences, and they are not what
`W8-2026-09-06.md` §3.2 says (see the correction below):

- **X3 → X4 (affine) is clean**: consecutive, both pre-`903f71a`.
- **X1 → X2 (self-training) is clean**: both post-`903f71a`; the only
  commit between them, `ac3b7fc` at 22:02, touches `pure.py`, the
  `pure_llr` `pseudo_rows` argument in `arms.py`, the `stop_reason`
  string and a `max_generations` guard — nothing on the patch decision
  path, and neither run uses a `pure+*` arm.
- **X3 against X1 or X2 is NOT an A/B at all**: the patch filter itself
  was rewritten between them.

Read that way, three readings survive and one does not:

- **Self-training COSTS certificates on the full list.**  X2 is X1 plus
  four self-training rounds and nothing else, and it mints 122 against
  127 — five fewer, for 1.21 × the CPU (33,475 against 27,744).  §6.2's
  S2 measured self-training as a small REAL offline gain (dead-band
  M+Y 0.1659 → 0.1639, 7 of 7 lanes past 2 SE against S0), so this is a
  clean instance of the wave's own warning: an offline cell-error gain
  is not a certificate gain, and here it is a certificate LOSS.  The
  loss is in the dead band (69 against 73) and the marginal (22 against
  23), which is where the tile's own confident cells are least
  trustworthy to pseudo-label from.
- **`L3f`'s contribution in this composition is NOT MEASURED here.**
  X3 mints 127 and X2 mints 122, but the two ran on different patch
  filters, so the +5 cannot be attributed to the rung.  That X3 and X1
  land on the same 127 band for band (73/23/31) across a filter rewrite
  is a curiosity, not a measurement.  `L3f`'s blind evidence remains
  §6.1's I6-vs-I2 (+6 on a three-rung ladder, one code state), and the
  isolation on the full ladder — `patch-self` against `patch-refit` at
  one HEAD — is now an OWED run, not a reported one.
- **Affine adds one, and the price is the whole run.**  X4 = X3 +
  affine, consecutive and on the same code: 128 against 127, +1 in the
  dead band, for 62,152 CPU s against 36,838 — 1.69 ×.  This is the
  cleanest A/B of the four and it is the one behind
  `W8-2026-09-06.md` §4's affine sentence.  e037's sheet-I chain
  (`experiments/037-sheet-i-single-capture.md`) is NOT a second
  measurement of it: there `patch+affine` was first-success on 13 of 19
  with no affine-off arm run.
- **The three pure rows are three different `pure.py`s, and are not a
  variant ladder.**  Same clock treatment as the X rows, and it is worse
  here: P0 ran 15:26–17:39 (so it loaded its code before `b68d21c`'s
  memoization at 16:38 — the "un-memoized" of §3.2 — and before
  `903f71a`), P0S 19:23–22:38 (post-`903f71a`, but **`583b482`, F2, which
  rewrote 333 lines of `pure.py` to price the tile from its own cargo,
  landed at 21:36 DURING it**), and P0R 22:38–01:20 (post-F2 and
  post-`ac3b7fc`'s R3).  So P0 = un-memoized halo-priced, P0S =
  halo-priced, P0R = tile-priced: **50, 39 and 38 are three
  implementations on one list, not `pure` against `pure-self` against
  `pure-refit`.**  What survives is the level — the pure path mints
  38–50 where the patch battery mints 122–128, on every code state it
  has had — and one shape worth a look when an isolation does run: P0R
  does not lose uniformly, it MOVES, 16 → 25 in the dead band while
  collapsing 20 → 5 in the live band.  §6.9's P0-fixed is the only
  controlled pure datum on the re-priced path (1 of 8, identical to
  SM2's), and §6.7's finding — that the two-component estimator misreads
  the three-ink overlap by 5× — is the mechanism to look at before
  anyone reads any of this as progress.  A one-HEAD `pure` /
  `pure-self` / `pure-refit` sweep on `C-open.list` is OWED.

**A correction to `W8-2026-09-06.md` §3.2.**  That section says "I6 and
X3 ran before the review fixes of `903f71a` …; X1 and X4 ran after
them."  X1 did; **X4 did not** — it started at 17:32, fifty-five minutes
before that commit, and the commit landed inside its run.  The
correction makes §4's affine number BETTER, not worse: X3 and X4 are
consecutive on one code state, so the +1-for-1.69× A/B is clean, which
is exactly what §4 leans on.  What it takes away is the X1-vs-X3
comparison in the same paragraph ("X1 … certifies the same 127 as X3 for
75 % of X3's CPU"): those two ran on different patch filters, so the CPU
ratio is real and the equality of the counts is not an isolation.

What §6.4 still owes after this section: X5, X6, X7–X9, X11, I3, I4, I5,
the Y list, S9's combined-lane dump, K3's high-power arm (§6.9), and two
isolations this section could not supply — `patch-self` against
`patch-refit` at one HEAD (the `L3f` question), and the three pure
profiles at one HEAD.  **Both ran on 2026-09-07 at `cddcb87`; §6.11.**

### 6.11 The one-HEAD isolations (2026-09-07)

Ten runs, all at **`cddcb87`**, all on the SAME 153 rows, all one
generation, all `--workers 14`, and the HEAD did not move between the
first launch (08:01) and the last (10:26) — which is the whole point of
the wave.  §6.10 could not read X2 against X3 or the three pure profiles
against each other because the runs that would have been those
isolations straddled `903f71a`; these are those isolations, plus the RGB
one §5 listed as owed.  Same sheet, same day, single sheet: **it pins
nothing and promotes nothing.**

**A naming caution.**  §3's run matrix already uses `R1`/`R2`/`R3` for
its three GROUPS of runs (offline, blind, compositions).  The `R1`–`R4`
below are the 2026-09-07 task's own run names and always carry a suffix
(`R1-self`, `R2-refit`, `R3-rgb`, `R4-patch`); nothing here renames
anything in §3.

**Two things about HEAD that the numbers below are not comparable
across.**  `cddcb87` dropped the patch family's wide halo, so every run
here carries `{'C': 16, 'M': 16, 'Y': 32}` where X1–X4 and P0/P0S/P0R
carried 48/48/32 — the profiles' own default, taken deliberately (the
task's instruction was to respect the new pin, and the isolations are
each internally one code state and one halo).  So an R-row is read
against the other R-rows, never against an X- or P-row.

**That halo pin was re-examined the same day and STANDS** (§6.12,
`HALO-CHANNEL-2026-09-07.md`).  R3-auto's 115 against X1's 127 was the
contradiction that opened the question, and it was a real one: the
offline isolation `cddcb87` was made on ran the RED channel set only.
The halo × channel matrix settles it at certificate level — **at a fixed
channel set the wide halo loses in BOTH columns** (red 109 → 104, rgb
128 → 127) at 4.3× the CPU and +8 GiB, exactly as §6.9's offline row
said; the one column where 48 wins is `auto`, by 12, and that +12 is the
WALK's franchise and bar, not filter quality.  With the walk repaired
the halo-16 run reaches 127.  Nothing here promotes the pin — one sheet
— and the halo remains an operator axis, not a run's own choice.  And
`cddcb87` added `patch+offset`/production to
`controls.PARITY_CONFIGURATIONS`, which is what R4 exists to read.

**The target list.**  The task named `--targets residue`; on this base
that is **303 rows** (C 153 + Y 150), not 153, because the residue is
both streams.  The 153-row list every W8 I- and X-pass used is
`scratch/analyzer/W8/C-open.list`, and it is EXACTLY the C half of that
residue (verified set-equal against a `census` of the base before the
wave launched).  Every run below therefore used `--targets "list
scratch/analyzer/W8/C-open.list"`, and every ledger header says
`n_rows 153`.

**The commands.**  Each ladder pass is the line below with `<profile>`
and `<out>` filled from the table, wrapped in `/usr/bin/time -l`, run
one at a time behind a machine gate (at most one other heavy analyzer
process, ≥ 45 GB free+inactive) by
`scratch/analyzer/W8-owed/run-wave.sh`:

    PYTHONPATH=src:. env314t/bin/python -m analyzer ladder \
        --run-dir scratch/holo3-H-with-facts-7-run.32018 \
        --profile <profile> [--knob patch_channels=rgb|r] \
        --targets "list scratch/analyzer/W8/C-open.list" \
        --workers 14 --out scratch/analyzer/W8-owed/<out>

with NO `--fixed-point` and no `--max-generations` — one generation, as
X2/X3 effectively ran — and NO `--halo-cells`, so each profile takes the
halo `cddcb87` gave it.  Each was then scored offline, light:

    … -m analyzer score --ledger <out>/ledger.jsonl \
        --payload scratch/analyzer/H14-pass1/payload.bin \
        --out <out>-score

(no `--run-dir`, no `--gt-dir`: certificates against the payload and
nothing else).  R4 is:

    … -m analyzer controls --run-dir scratch/holo3-H-with-facts-7-run.32018 \
        --targets "list scratch/analyzer/W8/C-dead-certified.list" \
        --profile patch|patch-refit --null 5 --frame-null 3 \
        --parity 100 --workers 14 --out scratch/analyzer/W8-owed/R4-…

| run | profile / knob | certs | checked | wrong | CPU s | CPU s/tile | par. | wall | peak RSS |
|---|---|---|---|---|---|---|---|---|---|
| R1-self | `patch-self` | 110 | 110 | **0** | 6,059 | 39.6 | 7.2 | 14 m 00 | 37.7 GiB |
| R1-refit | `patch-refit` | **113** | 113 | **0** | 8,681 | 56.7 | 7.3 | 19 m 56 | 38.0 GiB |
| R2-pure | `pure` | 8 | 8 | **0** | 9,474 | 61.9 | 5.9 | 26 m 48 | 70.8 GiB |
| R2-self | `pure-self` | 11 | 11 | **0** | 13,662 | 89.3 | 8.6 | 26 m 37 | 75.9 GiB |
| R2-refit | `pure-refit` | **19** | 19 | **0** | 16,153 | 105.6 | 11.1 | 24 m 12 | 78.3 GiB |
| R3-red | `patch --knob patch_channels=r` | 109 | 109 | **0** | 3,178 | 20.8 | 11.1 | 4 m 45 | 32.5 GiB |
| R3-auto | `patch` (the profile's own `auto`) | 115 | 115 | **0** | 4,849 | 31.7 | 12.2 | 6 m 37 | 37.4 GiB |
| R3-rgb | `patch --knob patch_channels=rgb` | **128** | 128 | **0** | 8,217 | 53.7 | 12.8 | 10 m 43 | 39.6 GiB |
| R4-patch | `controls --profile patch` | — | — | — | 421 | — | 2.1 | 3 m 16 | 20.2 GiB |
| R4-refit | `controls --profile patch-refit` | — | — | — | 464 | — | 2.0 | 3 m 49 | 20.2 GiB |

Every ladder row was scored offline against
`scratch/analyzer/H14-pass1/payload.bin` (`analyzer score`, no
`--run-dir`, no `--gt-dir`): **eight passes, 613 certificates checked,
0 wrong and 0 false accepts**, and every one of the eight wrote a close
whose `payload_sha256` is `0ad329fb…` = the emission's, `verified:
true`.  Contention: the user's own X11 (`everything+patch+pure`) held
the machine for R1-self, R1-refit, R2-pure and part of R2-self and then
finished, which is the whole of why parallelism runs 5.9–8.6 in the
first four rows and 11.1–12.8 in the last four.  The CPU column does not
move with it.  R3-auto is one run beyond the four the task named, added
because it is the third point of R3's own question and costs 6 minutes.

**R1-self against R1-refit — `L3f` in composition, finally isolated:
+3 for 1.43 × the CPU.**
`patch-self` and `patch-refit` differ in exactly two things: the rung
list gains `L3f`, and the knobs gain `refit_rounds 2` /
`refit_max_evidence 26`.  Nothing else moves — the two runs'
`auto_choices` come back identical state for state and count for count
(agnostic 2046 r / 1146 rgb, state0 2885/277, state1 2793/337, state2
2888/304, state3 2721/465 in both), which is the measured version of
"the patch filter is the same one".  **110 → 113, and R1-self's set
is a STRICT SUBSET of R1-refit's**: the three added are all dead-band,
`(0,2,30,C)`, `(0,28,30,C)` and `(0,39,31,C)`, and `L3f.r0` is the
first-success rung on 25 of the 113.  So the rung reaches deep into the
run — a quarter of the certificates come out of it first — while its
marginal contribution is three.  §6.1's I6-vs-I2 measured +6 on a
three-rung ladder; on the full battery it is +3, for 8,681 CPU s against
6,059.  Both readings are now one-HEAD.

**The R2 family — the three pure profiles at one HEAD, and the ladder
is MONOTONE.**  `pure` 8 ⊂ `pure-self` 11 ⊂ `pure-refit` 19, each a strict
subset of the next, at 9,474 / 13,662 / 16,153 CPU s.  §6.10's 50/39/38
descent was three different `pure.py`s and a wider halo; read at one
code state the family's own knobs both help: self-training +3 (the
opposite sign to what it does on the patch battery, X1 → X2's −5), L3f
+8 with `L3f.r0` first-success on 8 of the 19.  **What does not change
is the level**, and that is the finding to keep: 8–19 against the patch
battery's 109–128 on the same 153 rows, the same halo, the same
afternoon.  The cost question the task asked — what the pure path costs
after B8's memoization — is answered too: **9,474 CPU s where P0 spent
43,102**, 4.5 × cheaper, though a halo change rides along in that ratio.
Memory did not come down with it: 70.8–78.3 GiB peak, the most expensive
configurations in the wave, and `pure-refit`'s 78.3 GiB is a new high
for the analyzer.

**The R3 family — RGB isolated under a full blind pass, and RGB WINS
by 19.**  The
S1r → S1c offline row (three-ink cell error 0.171 → 0.127) had never
been seen as certificates; here it is, on one code state, one knob
changed: **`patch_channels=r` 109, `patch_channels=rgb` 128**, and the
red set is a STRICT SUBSET of the RGB set — 19 added, 13 of them
dead-band, 4 marginal, 2 live (bands 64/18/27 → 77/22/29) — for 8,217
CPU s against 3,178, **2.59 ×**.
That is the largest single-knob certificate gain the wave has measured,
and it agrees in sign and roughly in scale with the offline row.
**And the self-discovery is leaving most of it on the table.**  R3-auto,
the same profile with `patch_channels: auto`, mints 115 — six above red,
thirteen below RGB, and not nested with either (it has one certificate
RGB does not).  The `auto_choices` of every auto run at this HEAD say
why: pooled over 153 rows × lanes, the search picks **red 85 % of the
time on the three-ink state** (rgb 15 %) and 89–91 % on the ordinary
states; at halo 48, X1's rows picked **rgb 63 %** on that same state.
So the halo change did not just move cell error — it flipped what the
per-population search believes, and at 16 it believes the wrong thing on
the population this whole line exists for.  W8 §4 called RGB "the right
answer without labels"; at HEAD the search no longer finds it.  That is
a specific, cheap follow-up (the objective the channel axis is scored
under, on the search fold, at halo 16) and it is NOT a proposal to pin
`rgb`: one sheet, one stream, no promotion.

**The R4 pair — the fourth parity configuration re-derives what the
other three cannot, and the gate still fails.**  Same eight production-certified
dead-band C rows as K1-certified/K3-certified
(`scratch/analyzer/W8/C-dead-certified.list`), `--null 5 --frame-null 3
--parity 100`, both profiles.  Null and frame-null PASS in both (0
certificates in 1 trial each, both truthfully certifying, donor
`min_unsat` 52–78).  Parity, per configuration, re-derived of 8:

| configuration | `--profile patch` | `--profile patch-refit` |
|---|---|---|
| `subtract+offset`/production — **the gate** | 1 (0.125) | 1 (0.125) |
| `subtract+committed`/ctx-none | 0 | 0 |
| `head+offset`/production | 1 (0.125) | 1 (0.125) |
| **`patch+offset`/production (new at `cddcb87`)** | **7 (0.875)** | **8 (1.000)** |

`n_disagreeing_with_production` is 0 in all eight cells.  **The gate
still FAILS** — `passes: false`, `CONTROLS FAILED: ['parity']`, exit 1 —
because the gate is the default arm and 0.125 is under the 0.8 bar.  But
the new configuration clears the bar in both profiles, which settles
what §6.9 could only suspect: the 0 of 8 was measuring THE CONTROL'S
COVERAGE, not the run's parity.  On the hardest eight tiles on the
sheet, an arm that can read them re-derives seven or eight of
production's certificates; the ones that cannot, cannot.
Two second-order readings.  The old three now read **1** where
K1-certified read 0 — the halo the profile carries reaches
`parity_sample`'s config, so at 16 the default arm re-derives one row it
could not at 48; that is a knob difference, not a code fix.  And
**parity is no longer profile-independent**: K1-certified and
K3-certified came back bit-for-bit identical because every configuration
in the table then ignored the patch knobs, whereas `patch+offset` does
not — `patch-refit` carries `patch_selftrain_rounds 4`, and that is the
whole of the 7 → 8.  The claim in §6.9's parity paragraph holds for the
three old configurations and no longer holds for the table as a whole.

Artefacts: `scratch/analyzer/W8-owed/<run>/` (ledger, close, maps),
`<run>-score/`, per-run `HEAD`/wall/exit in
`scratch/analyzer/W8-owed/logs/<run>.meta`, `/usr/bin/time -l` in
`<run>.err`, the machine gate's own log in `logs/gate.log`, and the
runner plus the two comparison scripts (`certdiff.py`, `autochan.py`) in
`scratch/analyzer/W8-owed/` (retired 2026-10-09; their result stands above).

### 6.12 The halo x channel matrix, the walk, and the ridge (2026-09-07)

The follow-up §6.11 named as "a specific, cheap question" — why the
channel search flips its answer when the halo moves — asked, answered,
built, isolated and reviewed the same day.  The governing document is
`analyzer/HALO-CHANNEL-2026-09-07.md`; this section is the run record.
**Same sheet, same day, single sheet: it pins nothing and promotes
nothing** (§4.0 ruling 1).

Every ladder pass below is the same line, one at a time behind the
machine gate (at most one other heavy analyzer/receiver process, >= 45 GB
free+inactive), `/usr/bin/time -l` kept, `git rev-parse HEAD` recorded at
launch AND at exit (identical in all sixteen), no `--fixed-point`, one
generation:

    PYTHONPATH=src:. env314t/bin/python -u -m analyzer ladder \
        --run-dir scratch/holo3-H-with-facts-7-run.32018 --profile patch \
        [--halo-cells 48] [--knob <one knob>] \
        --targets "list scratch/analyzer/W8/C-open.list" \
        --workers 14 --out <out>

and every one scored offline and light against
`scratch/analyzer/H14-pass1/payload.bin` (no `--run-dir`, no `--gt-dir`).

#### (a) The matrix — halo x channel, in certificates

| halo (C) | `patch_channels=r` | `auto` (the profile) | `patch_channels=rgb` |
|---|---|---|---|
| **16** (the default since `cddcb87`) | **109** (64d/18m/27l), 3,178 CPU s | **115** (68d/19m/28l), 4,849 | **128** (77d/22m/29l), 8,217 |
| **48** (`--halo-cells 48`) | **104** (53d/22m/29l), 13,678 | **127** (73d/23m/31l), 24,628 | **127** (74d/23m/30l), 35,272 |

**710 certificates checked over the six, 0 wrong, 0 false accepts**,
every close `verified` at the emission's sha.  (HALO-CHANNEL §1 first
said 971; that was §6.11's eight R-rows plus these three halo-48 cells,
and it is corrected there.)  The three halo-16 cells
are §6.11's `R3-*` NOT re-run: `git diff --name-only cddcb87..HEAD --
'*.py'` was EMPTY at the time, so they are at that code state byte for
byte.  Peak RSS 32.5 / 37.4 / 39.6 GiB at halo 16 against 37.5 / 46.9 /
47.1 at halo 48 — the wide halo's two expensive cells sit barely above
the gate's own 45 GB floor, so this matrix cannot be run two at a time.

What it settles, in one line each: **RGB beats red at BOTH halos** (+19
at 16, strictly; +23 at 48 via `auto`), so the channel axis is not a
halo artefact; **the wide halo LOSES at a fixed channel set** (109 ->
104, 128 -> 127) at 4.3x the CPU, which is the certificate-level version
of §6.9's H48 offline isolation and means `cddcb87` was right on the
evidence it was made on; and **the wide halo WINS by 12 for `auto`
alone** — the one column the halo helps is the one that runs.  Exactly
two of the fifteen pairs are containments; thirteen are crossings.
Six-way: **intersection 89, union 135 of 153**, and no single cell
reaches the union.

#### (b) Why `auto` moves — the two ledgers, one definition throughout

Over the 3,538 (row, lane) patch evidence blocks in EACH `auto` ledger:

* **the franchise.**  `patch._choose_axes` refused the walk below
  `SELECT_MIN_MINORITY` and returned the module constants, and
  `auto_choices` recorded that as a choice.  At halo 16, **674 of 3,186
  three-ink populations (21 %) never voted**; at halo 48, two.  So
  §6.11's "the search picks red 85 % of the time on the three-ink state"
  decomposes as 2,047 votes plus 674 inheritances, and is corrected
  here.
* **the bar.**  Adoption is a paired test at 2 SE, and SE ∝ n^(-1/2)
  while the walk's fold carries 4.6x more labels at halo 48 — a bar
  2.15x lower for the same effect.  On the three-ink state the walk
  measures `rgb` better at BOTH halos (median gain +0.0091 at 16,
  +0.0281 at 48) and **refuses it on 1,033 of 2,512 walked populations
  at halo 16**.
* **the population.**  The walk scores held-out loss on the halo's own
  search labels, whose cross-fit error is 0.0356 (halo 16) / 0.0202
  (halo 48) on the three-ink state, against the dead band's three-ink
  cargo at 0.152-0.171 — **4.3-4.8x easier than the cargo it prices**.
  Two filters that differ by 4.4 points of cargo cell error and 19
  certificates differ by 0.009 nats there.  This is §4.0 ruling 15 /
  DESIGN §14.5's F2 defect one level up.

So the halo's certificate value at HEAD is **not a data-budget effect on
the filter — it is an effect on the CRITERION and the FRANCHISE**, and
the finding is that the walk, not the halo, is the thing to fix.

#### (c) The ruling, and the isolation it pre-registered

The halo does NOT become an auto axis and no labels-per-feature floor is
adopted (HALO-CHANNEL §3(a)): the best cell in the matrix runs at 0.77
labels per parameter, so every floor the matrix can reach is refuted;
growing the halo to afford a model takes 128 to 127 for 4.3x the
machine; and the halo DEFINES the row set, so two halo candidates have
no common evaluation population and cannot be paired at all.  Instead
three named changes to the walk, all on the SEARCH fold, all behind
operator knobs, plus one that is not a knob (the regulariser becomes an
inner minimisation under every candidate).  Pre-registered isolation,
same base, same list, halo 16, at `8356aae`:

| run | knobs | certified | checked | wrong | false | CPU s |
|---|---|---|---|---|---|---|
| N0 | none | 118 | 118 | 0 | 0 | 9,315 |
| N1 | `walk_weighting=cargo` | 115 | 115 | 0 | 0 | 9,328 |
| N2 | `walk_franchise=pooled` | 122 | 122 | 0 | 0 | 9,227 |
| N3 | `walk_direction=nested-richer` | 124 | 124 | 0 | 0 | 10,549 |
| N4 | all three | 127 | 127 | 0 | 0 | 10,454 |
| A-red | `patch_channels=r` | 109 | 109 | 0 | 0 | 5,424 |
| A-rgb | `patch_channels=rgb` | **128** | 128 | 0 | 0 | 21,422 |

The two anchors came back BIT-IDENTICAL to `R3-red`'s 109 and
`R3-rgb`'s 128, which is what lets the matrix be read against this wave.
Gate clause 1 (zero wrong / zero false) passed everywhere; clauses 2 and
3 FAILED as written and are dispositioned in HALO-CHANNEL §5.1.  The
franchise ships (**net +4**, +5/-1) and the direction ships (**net +6**,
+7/-1) — each a crossing, not a containment; the weighting is refused
(-3 alone, a strict subset).

#### (d) The two runs that came after the isolation

**`FIXED-auto`** (`d35e73d`) is the configuration `--profile patch`
actually produces — the shipped pair without the refused weighting —
which the N0-N4 set did not contain: **127 certified, 0 wrong**, and its
key set is **EQUAL to N4's**, so `walk_weighting=cargo` over the shipped
defaults is exactly 0 gained / 0 lost.  That corrects HALO-CHANNEL
§5.2's attribution (the "+4/-1 in composition" was W1 and W2 together,
since N3 has no franchise) and discharges §5.4's reversal clause on a
run that ships.

**`RIDGE-auto`** (`3a661fe`) is the same configuration after an
independent review found that **W4's chosen regulariser never reached
the fitted filter**: `autoknobs.choose` minimised it inside every
candidate and published it in `auto_choices`, and `patch._population`
then fitted through `spec.shrinkage`, the inherited constant.  Probed on
the `World` fixture: the walk chose {0.1, 0.01, 0.01, 0.001} and every
deployed fit ran at 0.01.  Fixed, with a test that fails on the pre-fix
tree; re-measured as a one-variable isolation against `FIXED-auto`:

| run | knobs | certified | dead/marg/live | checked | wrong | false | CPU s | peak GiB |
|---|---|---|---|---|---|---|---|---|
| `FIXED-auto` (ridge discarded) | none | 127 | 76/22/29 | 127 | 0 | 0 | 10,416 | 38.0 |
| `RIDGE-auto` (ridge applied) | none | **127** | 76/22/29 | 127 | 0 | 0 | **10,357** | 38.6 |
| `A-rgb` (ridge discarded) | `patch_channels=rgb` | 128 | 77/22/29 | 128 | 0 | 0 | 21,422 | 40.0 |
| `RIDGE-rgb` (ridge applied) | `patch_channels=rgb` | **126** | 74/22/30 | 126 | 0 | 0 | 21,216 | 39.9 |

**On `auto` the count holds and the SET crosses**: +`(0,33,30,C)`,
-`(0,38,30,C)`, both dead-band, at −0.6 % CPU.  `(0,33,30,C)` is
**outside the six-way matrix union** (135 -> 136 with it) and outside
N0-N4 and both anchors — the first certificate in the wave minted by the
filter being FITTED differently rather than CHOSEN differently.  The
walk itself did not move (channel histograms within twelve blocks,
refusal counts identical, `labels_per_feature_chosen` identical to two
decimals), which is the expected shape: every candidate was already
compared at its own ridge, so the choice was right and the deployment
was wrong.  What did move is where the certificates arrive: **L0 carries
124 of the 127 against 118**, and the two-arm rule
`patch+committed|patch+offset` carries 111 against 84.

**The pinned column was re-run too, and it LOSES two** (`A-rgb` 128 ->
`RIDGE-rgb` 126: +`(0,35,4,C)` live, -`(0,19,30)`, -`(0,38,30)`,
-`(0,45,30)`, all dead).  So the repair is +0 on `auto` and **-2 on
pinned rgb**, and at the repaired code state the two cells to read
against each other invert the old ordering: **`RIDGE-auto` 127 against
`RIDGE-rgb` 126 — the self-discovering walk one certificate AHEAD of the
hand-pinned channel set, at 49 % of its CPU, crossing it.**  §5's
headline had been "127 of the pinned cell's 128, strictly inside it".
Why the pinned column loses dead-band tiles is NOT measured: 22 % of its
three-ink populations are now fitted at the underdetermined rung 1.0 and
46 % at 0.1, where every one used to be fitted at the inherited 0.01, so
the regulariser is now chosen by the same objective §6.12(b) measures as
4.3-4.8x easier than the cargo.  That is a hypothesis from the
histograms; the discriminating run is W1 over the repaired tree.

Nine other review findings were verified and dispositioned in
HALO-CHANNEL §5.5; the ones that changed mechanism are W1's weights
reaching the inner ridge, the `DIRECTION_KEEP` zero-variance edge, and
the cargo bins derived per walking population.  All three are inert
under the shipped defaults, so **N1 and N4 measured a half-applied
weighting** and any re-basing of W1 starts from `3a661fe`.

**What this wave may not be read as.**  An R- or W-row is never read
against an X- or P-row (`cddcb87`'s halo boundary, §6.11).
`--halo-cells 48` sets all THREE planes, so the new headers say
`{'C':48,'M':48,'Y':48}` where X1's `wide-halo` profile said 48/48/32 —
inert on this all-C list, not inert for a Y-plane or mixed re-run, and
repaired by the per-plane spelling `--halo-cells C=48,M=48,Y=32`.
H48-auto's `knobs_from` reads `profile:patch+cli` because `--halo-cells`
sets `said_it`; `halo_from` now separates the two.  The six `score.md`
files are offline and light, so **this record carries no offline
cell-error column** for any of these knobs.  And H48-auto's certified
set being bit-identical to X1's 127 is a cross-code coincidence worth
knowing and NOT a measurement — §6.11 forbids that reading and nothing
here rests on it.

Artefacts: `scratch/analyzer/W8-halo/` (the halo-48 cells, `FIXED-auto`,
`run-halo.sh`, `run-fixed.sh`, `matrix.py`, `fixedmatrix.py`,
`matrix.txt`, `fixed-matrix.txt`), `scratch/analyzer/W8-walk/` (N0-N4,
the anchors, `run-walk.sh`, `walkmatrix.py`),
`scratch/analyzer/W8-ridge/` (`RIDGE-auto`, `run-ridge.sh`,
`ridgematrix.py`, `matrix.txt`), and under each a `logs/` with
`/usr/bin/time -l`, per-run `HEAD`/wall/exit, and the machine gate's own
log.  (The runners and matrix readers retired 2026-10-09; their result stands above.)

## 7. Review dispositions (2026-09-06)

Three lenses reviewed the first draft.  Every finding is listed; ACCEPTED
ones name where the document changed, REJECTED or PARTIAL ones carry the
reason.

**Blindness lens.**

- In-sample PAVA on the discriminant's own training rows — ACCEPTED as
  ruling 7 (cross-fit inside the fit fold; the gap column
  `patch_fit_error_*`).  PARTIAL on its floor clause: a floor of ≥ 5 ×
  features is REJECTED — the measurement's own floor was 300 labels at
  576 features (n/p ≈ 0.5) and produced the 0.119; the ridge makes n < p
  well posed and the cross-fit makes the calibration honest at any n/p;
  the floor is pinned by the S12 sweep instead.
- The select-fold invariant false as specified — ACCEPTED as ruling 9
  (round-0 label view in the refit's recombination; `label_llr` declared
  a held-out view that moves; the tests rewritten to what is true).
- No blind null control scheduled — ACCEPTED: CT row in §1f, K1–K3 in §3
  charged to B3/B4/B5, the shuffled-fit-label unit test in B1, `frame_null`
  named as the blind twin of the permutation control.
- Affine objective half in-sample under `patch_search_mode=patch` —
  ACCEPTED as ruling 1's strict form (the swim and word pose always
  search under `subtract`; E2 is the offset grid only); the `conditional`
  `fit_mask` gap is recorded as pre-existing and NOT fixed this wave
  (fixing it changes `conditional+affine`, a separate item).
- Leg-4 capture accounting under `platt-state` / L3 under C2 — ACCEPTED:
  `contributing_captures` is the union of supports; L3 refuses
  `state_context_adopted` (ruling 10) rather than shifting a per-state
  residual it cannot see.
- The pseudo-label door unguarded — ACCEPTED as ruling 8 (`PseudoLabels`
  typed; CLI reserved names; `score` refuses).
- Derived-knob precedence — ACCEPTED: assigned unconditionally in
  `blind_key`, a config naming one is refused, the CLI rejects the names.
- Word furniture skews per-state fits — ACCEPTED as ruling 11 (word
  sites excluded from per-state TRAIN sets, dust kept, counts reported, a
  word-only class refused).
- P2 can pseudo-label the metadata cell — ACCEPTED (`~frame.known[:,
  plane]` in P2's candidate mask, pinned).

**Feasibility lens.**

- calibrate ↔ statecal import cycle — ACCEPTED: `BRANCH_*` move to
  `types.py`; `statecal` imports nothing from `calibrate`/`combine`
  (`state_platt_weights` takes the pooled fitter as an argument); pinned
  by the closure test.
- The local5 memo unbounded — ACCEPTED with a different shape: per
  (lane, TILE) entries (shared across targets), 512-row cap by `fold_hash`
  rank, LRU of 512 entries, resident bound stated and pinned.  The
  lane-scope 12-tile sample variant is REJECTED: the measurement trained
  on the band's EDGE tiles (the neighbourhood), and a page-wide sample is
  a different estimator.
- README/APPROACHES parse test cannot pass — ACCEPTED in scope: the test
  harvests only README blocks tagged `analyzer-cmd`, spelled in full;
  §3's prefixed rows are not harvested.
- B1's 0.119 not like-for-like — ACCEPTED: §0 states the estimator
  difference; the acceptance is a paired delta against S0 on the 4800
  lanes per lane; `local5` (the closest estimator) gets S11 in B3;
  `footprint` stays B1's default.
- Heterogeneous score scale under one pooled map — ACCEPTED: every
  population scaled by its own out-of-fold fit-fold sd inside
  `patch_score`; C1 named as the companion.
- `_FakeInputs` without `_cache` — ACCEPTED: `_cache` added,
  `_reroll_world` monkeypatches `known_frame`/`sequential_state`,
  `test_analyzer_gaps_fix.py` in B2's file list.
- `Crops.raw_rgb` unconditional — ACCEPTED as ruling 13 (`keep_raw`
  opt-in; peak RSS recorded in B1's acceptance).
- L3f cost unbounded — ACCEPTED: `refit_max_evidence` budget per key,
  `L3f` out of `reroll_rungs` by default, `--limit 10` wall before I6.
  The per-(key, lane) crops cache is deferred (§5) — `arms.py` is over
  the cap and the measured wall decides.
- `extract` transient — ACCEPTED (4,096-row chunks; ruling 13).
- The rot_k-2 test cannot see a transposed grid — ACCEPTED (off-diagonal
  pose, asymmetric assertions).
- The named fixtures cannot express the stimulus — ACCEPTED
  (`_state_raster` budgeted in B1).
- The second `apply_context_offsets` re-clamps — ACCEPTED (documented,
  pinned).
- The nested-CV tuple — ACCEPTED, moved into B1 with a test over
  `REGISTER_ARMS`.
- `platt-state` degrades silently in `controls` — ACCEPTED
  (`fixedpoint.sequential_state_for` shared with `controls._decode_at`).
- The gaussian halo — ACCEPTED (halo a function of width AND kind).
- BLAS determinism — ACCEPTED as ruling 12 (Accelerate here; per-worker
  single-threaded BLAS pinned in `__main__`, repeatability test).
- Two spellings of `patch_score` and a throwaway profile — ACCEPTED (one
  signature; `--knob` moved into B1 so no temporary `PROFILES` entry
  exists; the S9 route is a `measure/` driver).

**Completeness lens.**

- The `controls` family absent — ACCEPTED (see the blindness item; CT
  row, K1–K3, `read`/`report` in §1f).
- Seven DESIGN §13 leads dropped — ACCEPTED: PV1/PV2 in §1f, DC in §1d,
  DM in §1e, A7b in §1g, targeted evidence merged into F6, MF in §1h;
  each with a status and a §5 disposition.
- S0/S1 population mismatch, no band axis in `score.md` — ACCEPTED
  (`bystate.py --level 3`; S1 read per lane on the 4800 lanes as a delta;
  B1's acceptance reworded).
- S9's combined-lane R does not exist in the scorer — ACCEPTED via the
  measure route (`dump_cells.py` with knobs + `combine_blind.py`); P1's
  status column says the combined figure is reproducible only that way.
  Extending the scorer is REJECTED for this wave (§5: per lane by design).
- Twelve unowned runs, no wall budget — ACCEPTED (every row charged or
  marked OPTIONAL; total and mandatory subset stated).
- `score` has no `--profile` — ACCEPTED by moving `--knob` into B1.
- P1d's isolation fires P1f — ACCEPTED (`patch_min_labels_agnostic`; S10,
  S11 added).
- P3/M1 composition claims — ACCEPTED (columns corrected; "reroll-only"
  dropped).
- The label supply overstated — ACCEPTED (§1g preamble with the census
  numbers; S12 floor sweep).
- `certifying_arm` not on disk before B5, no by-arm attribution —
  ACCEPTED (both moved into B1).
- X5 has no paired baseline — ACCEPTED by saying the argument out loud in
  §2; X0 listed as OPTIONAL.
- A7 measured only wider — ACCEPTED (0.5 added to A7 and S6).
- The "Commands" sentence — ACCEPTED (scoped to blind runs vs scores).

## 8. Code review dispositions (2026-09-06, on `38b1819..efaa20b`)

Four reviewers read the whole wave diff.  Every finding below was
verified against the code before it was acted on; the lane is green (652
passed, 69 skipped) and pyflakes is clean at the fix commit.  One
reviewer claim was found overstated and is marked as such.

**Majors.**

1. *P3's decoder rows are scored IN-SAMPLE by the filter and those scores
   then train the PAVA map* (`patch.py`, `patchfit.py`, `autoknobs.py`,
   `arms.py`, `calibrate.py`) — **FIXED**, three ways.  `fit_population`
   takes `extra_half` and cross-fits the pseudo rows like any other
   training row, so a pseudo cell carries an OUT-OF-FOLD score
   (`n_extra_out_of_fold`, substituted in `_population`); the map-side
   door `refit_calibration` now defaults to False for a patch mode and
   True for a box arm, where the map is the only place a pseudo label can
   act; and P2's self-training pool excludes the decoder's cells so one
   belief cannot be counted twice.  Pinned: a RANDOM pseudo bit is
   reproduced at its own cell at 0.505 (chance), against 0.613 with the
   rows left `always`.
2. *The local5 harvest hands the filter the target footprint's own
   search- and select-fold cells* (`patchlocal.py`) — **FIXED**.
   `local_patch_labels` takes the target footprint's page cells and drops
   every harvested row inside it at assembly (`searchsorted` on the flat
   page key, target-dependent, so the per-tile memo is untouched);
   `patch_local_rows_dropped_footprint` is published.  Nothing that could
   legitimately be trained on is lost: the footprint's own fit-fold rows
   are already the halo training set, so the drop also removes a
   double-count.
3. *The select fold both chooses the patch family's knobs and arbitrates
   among arms* (`patch.py`, `autoknobs.py`, `calibrate.py`) — **FIXED**
   by moving the walk onto the SEARCH fold, which DESIGN §4.8 reserves
   for within-arm searches.  `_choose_axes` and `choose_aperture` score
   candidates on `folds.search`; the selection row set is fit ∪ search;
   `select_arm` refuses `nested_cv_logloss` for a winner with non-empty
   `auto_choices` (`winner_chose_its_own_knobs_on_the_search_fold`), the
   same guard `SEARCHED_REGISTER_ARMS` gives a searching register arm.
   Pinned: permuting every select-fold label leaves `auto_choices` and
   `auto_losses` byte-identical.  ONE test pin moved with it — state 0 in
   B7's synthetic world keeps the inherited 1.5 window instead of
   adopting 1.0, because the 1.0 candidate does not clear 2 SE on the
   search fold; the claim under test (the WIDE window for the coreless
   state, never wider than inherited for a dot state) is unchanged.
4. *L3's round-0 label view can hand `combine` a stack with fewer rows
   than lanes* (`refit.py`) — **FIXED**.  `_label_view_for` keys `take`
   by lane off the NEW kept list and returns `None` when de-duplication
   promoted a coarser level the round-0 view never carried; the round is
   then refused instead of raising inside a worker (`platt`) or silently
   attributing one lane's losses to another (`best`).
5. *L3 is guarded against a per-state CONTEXT but not against per-state
   PLATT WEIGHTS* (`combine.py` → `fixedpoint.py` → `ladder.py`) —
   **FIXED**.  A new reserved knob `state_weighted` is assigned from
   `combined.coefficients_by_state` and L3 refuses it with its own reason
   (`state_weighted_combination`), so the ledger separates D1's case from
   C2's.  `Combined.ctx_state_adopted` keeps its meaning.
6. *`autoknobs.admit` never compares a tier to the tier it displaces* —
   **FIXED, with a calibration the reviewer did not specify.**  `admit`
   takes `own_losses` / `alternative_losses` (both from the new
   `crossfit_losses`, whose PAVA map is cross-fit on the filter's own
   halves) and refuses a tier the alternative BEATS by more than
   `SELECT_SE_MULTIPLE` standard errors.  The test runs in that direction
   on purpose: the reviewer's form (adopt only on a proven gain) hands
   every tie to `subtract` and would turn the patch arm into the box arm
   on the majority of populations — the arm choice is `select_arm`'s job,
   one level up.  The alternative offered is the `subtract` fallback:
   exactly what the cells would carry for the last tier, and the honest
   floor for an earlier one (the agnostic tier is fitted after the
   per-state ones and cannot be quoted at their admission).
7. *Any auto choice off the inherited geometry silently discards the 5×5
   neighbourhood labels* (`patchlocal.py`, `patch.py`, `patchcache.py`) —
   **FIXED**.  The harvest is cut at the WALK's widest geometry
   (`patchspec.walk_geometry`, shared with `patch_score`), and each
   population slices its chosen candidate out of it with the new
   `patchcache.derive_block` / `axes_key` / `block_width`.  Measured on
   B7's synthetic world: the four populations choose windows 1.5 / 1.0 /
   2.0 / 2.0 and all four use the neighbourhood rows, 5,046 used and 0
   dropped.  `patch_samples_per_cell` remains the one axis a choice can
   still drop — a coarser sampling moves every sample position and is a
   different grid, not a slice — which is why `_PURE_KNOBS` names it, and
   README §2.4 and `types.py` now say exactly that (see the minors).
   The local5 store is now bounded by BYTES as well as by entries
   (`PATCH_LOCAL_MAX_BYTES`, 512 MB/process): 512 entries × 6.3 MB at the
   widest 4800-dpi geometry would have been 3.2 GB per worker.

**Minors.**

- Duplicate `RESERVED_KNOBS` in `cli.py`; `score.py` refusing only two of
  the names — **FIXED**: `cli` imports the tuple from `types`, `score`
  loops over it, and a test asserts the CLI's copy IS `types`'.
- `combine.py`'s `rows` rebound to a boolean mask inside the per-state
  loop — **FIXED** (renamed `where`).
- `combine._label_view` recomputing `values` per lane — **FIXED** (read
  once, from the first lane, like `state` and the discriminating flags).
- `FeatureBank.CACHE_ENTRIES`' memory arithmetic stated at 576 features
  while the walk can ask for 3,072 — **FIXED**: a `CACHE_BYTES` cap
  (192 MB) evicts alongside the entry cap and the comment states the
  worst case the candidate set permits.
- The blind detail's flat geometry fields report the INHERITED values
  under `auto` — **FIXED with a smaller form than proposed**:
  `patch_geometry_scope` (`inherited` / `per_population`) says which
  field to read, and `auto_choices` already carries the per-population
  values.  The suffixed pair was refused because it puts five more
  numbers per population in every ledger row.
- `aperture_cells="auto"` inert on a non-patch arm and buying the raw
  crop anyway — **FIXED**: refused explicitly with
  `auto_refused = {"tile": "not_a_patch_mode"}` and the crop opened
  without `keep_raw`.
- `patchlocal` re-implementing the sibling-state convention inline
  (ruling 6) — **FIXED**: `statecal.sibling_state_of(bits, known, plane)`
  is the seam; `sibling_state(frame, plane)` is one line on top of it.
- README/DESIGN claiming the `pure` profiles ask for `auto` on every
  patch geometry knob while `_PURE_KNOBS` pins
  `patch_samples_per_cell: 16` — **FIXED IN BOTH DIRECTIONS**: finding 7
  removed the pin's original reason (window/channels/features no longer
  drop the rows), the pin STAYS for the sampling axis alone, and README
  §2.4, `types.py` and a new drift guard in `test_analyzer_docs.py` now
  say so together.
- `patch_labels_from` claiming `local5` when every population dropped the
  rows — **FIXED**: the claim is made on `patch_local_rows_used`, which
  is published beside `patch_local_rows_dropped`.
- `patch-then-pure` running the placed `pure+*` arms through
  `platt`/`platt-state`/`best` against DESIGN §14.6's attribution claim —
  **FIXED IN THE PROSE, not the code**: a `reroll_only_rules` field would
  cut the placed arms from five rolls to one, i.e. buy the attribution
  with yield.  DESIGN §14.6 and `types.py` now say the gain is
  attributable to the pure calibration AS COMBINED BY THAT PROFILE'S
  RULES, and name `PROFILES["pure"]` (`rules: ("sum",)`) and the two-pass
  form as the isolations.
- Unknown-state cells PRICED rather than erased in the pure path —
  **FIXED as a record, not a behaviour**: `pure_other_priced_by` and
  `pure_other_cells` are published, so an open-Y tile reads apart from
  one where the state was known.  The generalisation itself is the more
  honest rule and B6 recorded it deliberately.
- DESIGN §0.4's line cap stated unconditionally while `arms.py` and
  `field2.py` are over it — **FIXED**: §0.4 records the two exceptions,
  the dispatch-only rule for them, and where W8's mechanism actually
  lives.  `patch.py` itself went past the cap under these fixes and was
  SPLIT: the knob layer is `patchspec.py` (a move, every name
  re-exported), leaving `patch.py` under the cap.
- `refit.DEFAULT_CONFIDENCE_LLR = 4.0` has no `"auto"` value and B4's
  handoff proposes re-pinning it from sheet H's I6 quantiles —
  **REJECTED as a defect; RECORDED as owed.**  4.0 is an inherited
  fallback like every other module constant, and nothing in this wave
  re-pinned it; giving τ an `"auto"` derived from the rung's own
  extrinsic distribution is NEW MECHANISM (a build item for the next
  wave, and the right answer to the re-pin the ruling forbids), not a
  review fix.  The rung already publishes `extrinsic_q50/q90/q99/max` on
  every round, which is the evidence that item starts from.

**Overstated.**

- One reviewer read `select_arm`'s hazard as "the select fold now BOTH
  chooses the knobs and arbitrates the arms, with no guard anywhere".
  The direction is right and it is fixed above, but `_choose_axes` was
  already deliberately blind to the local5, pseudo and self-training rows
  (`patch.py`'s own comment), so the walk was never a vote about the
  extra label sets — the leak was the fold, and only the fold.

**Not a review finding, fixed in passing.**

- `test_analyzer_progress.py::test_the_driver_reports_each_generation_through_the_sink`
  pinned the pass's WALL TIME (`0:00:00`) inside an exact-string
  assertion and failed 2 runs in 3 on the pre-fix tree.  The sentence is
  pinned, the clock is matched by shape.
