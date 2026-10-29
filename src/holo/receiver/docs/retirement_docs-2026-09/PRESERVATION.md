# Preservation — what is saved where, and what stays in history only

Companion to `DELETION-LOG.md`: that file records what was removed and the
counts around it; this one records where the removed thing's evidence now
lives. Started at Phase 2 step 2.3 (suite preparation); the archive census
of §3.1 and the capability notes the maps ask for (`HOLO1-MAP.md`
`extra-01`, the ysampler README, `HOLO_COLOR_STACK_FORCE_NULL`'s three call
sites, `survey.full_support`) are still owed and land here.

---

## 1. Frozen holo2 oracles — the format-law pins that moved into holo3

`holo2/` is a second, independently written implementation of the printed
format. Five legs of holo3's drift lanes used it as a live oracle for
format LAW. Those legs now carry holo2's own values as frozen literals
inside `src/holo/receiver/tests`, so the law is pinned exactly as before with no
import of the retiring tree. **The values are identical to what the live
comparison asserted** — this is a re-homed oracle, not a re-frozen golden.

Provenance: every literal was read from the holo2 tree at **`4e6ec3e`** by
`measure/h3_freeze_holo2_pins.py`, which builds its corpora by importing
the drift-test module itself — so a checkout that still has holo2
reproduces the literals exactly, including on a later tree. That driver
imports holo2 and therefore **dies with it: add it to the Phase 3.2
removal list** next to `measure/angle_residue_h2.py`.

Measured while proving the independence below: with `holo2/` moved aside,
the only holo3 test that fails is
`test_every_import_in_the_by_path_instrument_drivers_still_resolves`, and
it fails on four `measure/` drivers, never on anything in `src/holo/receiver/tests` —
`angle_residue_h2.py` (`holo2`, `holo2.solve`), `angle_residue_certs.py`
(`holo2.solve.keys`), `angle_residue_nyquist.py` (`holo2.solve`) and the
freeze driver above. The first three are already Phase 3.2's own line
("`measure/angle_residue_h2.py` and the holo2 legs of
`measure/angle_residue{,_census,_certs,_nyquist}.py`"); `angle_residue.py`
and `angle_residue_census.py` do NOT import holo2 and pass untouched. The
proof run moved all four aside with holo2, which is what Phase 3 does to
them.

| pin | where the literal lives now | what it pins |
|---|---|---|
| holo2's batch BCH decoder over the seeded corpus | `test_h3_drift_kernels.py` `HOLO2_DECODE_MANY` (digest, n_rows, n_decoded; keyed by corpus size so the oracle-sweep lane is pinned too) | the (127,50,t=13) address code's decode/refuse decision on 2,000 words fast / 200,000 under sweeps |
| holo2's `berlekamp_massey_many` + `chien_root_mask` on dirty syndromes | `test_h3_drift_kernels.py` `HOLO2_BATCH_INTERNALS` (two digests, n_dirty, n_kept) | the batch decoder's internals — the one leg with no v1 counterpart, so the frozen record is now the only second opinion |
| holo2's six LDPC mother-code JSON files | `test_h3_drift_declared.py` `HOLO2_LDPC_SHA256` | the frozen mother codes ARE the format; a copy that is not a copy is a fork |
| the twelve fossil seed byte strings holo2 kept | `test_h3_drift_declared.py` `HOLO2_FOSSIL_SEEDS` | the AES seed bytes of twelve printed identities (also feeds the `cmy8-v0-fossils-kept` and `sheet-j-v2-fossil` divergence rows) |
| holo2's `FAMILY_SEED_P100` / `FAMILY_SEED_P120` | `test_h3_drift_declared.py` `HOLO2_FAMILY_SEED_P100/P120` | the site-lattice seeds, across all three trees |

All five are asserted through `_h3_support.assert_golden`, whose message
already says a mismatch is a printed-format fork and never a test to
update. Both BCH tables are keyed by corpus size and **both keys are
verified against holo3 today**: the fast-lane pair by the ordinary slow
lane, and the widened pair (200,000 words / 8,192 syndrome rows) by one
`HOLO3_RUN_ORACLE_SWEEPS=1` run of the two tests, 2 passed in 41 s — so
the sweeps lane cannot later report a "format fork" that is really a bad
freeze.

## 2. One-time oracle records — holo2 receiver numerics

These legs compared holo3 against holo2's SOLVE/CAPTURE numerics
(geometry, decimation, certified refinement) — receiver behaviour, not
printed-format law. Per the plan they were run green once on the tree that
still had holo2, recorded here, and then removed. Every behaviour they
covered keeps its holo3-side unit coverage in `test_h3_lib_geometry.py`,
`test_h3_lib_decimate.py` and `test_h3_plugins_calibrate_refine.py`; what
is not reproducible after Phase 3 is the cross-tree agreement itself.

Run 2026-09-04 on `4e6ec3e` + this package's worktree, before the trim,
`HOLO3_RUN_SLOW_TESTS=1 env/bin/python -m pytest -q` on the named node ids:

| module | test functions selected | test ids | result |
|---|---|---|---|
| `test_h3_drift_kernels.py` | 11 (2 BCH + 4 geometry + 5 decimate) | 19 | **19 passed** |
| `test_h3_drift_receiver.py` | 8 refine tests | 25 | **25 passed** |
| `test_h3_drift_declared.py` | 8 (LDPC ×6, fossils, site seeds, 2 constant pairs, 3 divergence rows) | 13 | **13 passed** |

Removed after that run (holo2 was the only oracle in each):

- `test_h3_drift_kernels.py` — `test_geometry_affine_family_matches_holo2`,
  `test_geometry_rescale_and_compose_match_holo2_place_shared`,
  `test_geometry_window_layout_constants_and_starts_match_holo2`,
  `test_decimate_ppc_ladder_matches_holo2_scale_space`,
  `test_decimate_area_pixel_transform_matches_holo2`,
  `test_decimate_box_kernels_match_holo2_and_are_chunk_invariant` (6 ids),
  `test_decimate_rational_kernels_match_holo2_bit_exactly` (4 ids),
  `test_decimate_luma_matches_holo2_scan` — **16 test ids**. Also trimmed:
  the `tile_of_cell` tail of
  `test_geometry_site_hash_parity_and_rotation_match_the_v1_consumers`
  (the test keeps its v1 and self-contained legs).
- `test_h3_drift_receiver.py` —
  `test_refine_search_grid_and_tie_break_match_holo2` and
  `test_refine_collect_labels_matches_holo2_reference_join` (**2 ids**;
  both are wholly holo2 joins, and `candidate_grid`/`fine_grid`/
  `select_best`/`collect_labels` are covered by
  `test_h3_plugins_calibrate_refine.py`, including the no-certified-tile
  case). Six further refine tests kept their v1 legs and lost the holo2
  third term; `_make_labels` no longer builds a holo2 `SegmentLabels`.
- `test_h3_drift_declared.py` — the two `CONSTANT_PAIRS` rows against
  holo2 (`holo.receiver.lib.geometry` vs `holo2.solve.geometry`, 4 shared
  constants; `holo.receiver.plugins.survey` vs `holo2.capture.survey`, 15) —
  **2 ids**. `_still_diverges_envelope_folded_into_close` dropped its
  `holo2.format.envelope` `find_spec`; the divergence row now states that
  holo2 also had a separate envelope module at `4e6ec3e`.

### holo.receive legs — one-time records (Phase 4, 2026-09-05, tree f006abc)

(Correction applied at the trim, §4 APPLIED below: the receiver module has TWO reachable survivors, not three — `test_printed_cells_for_matches_the_v1_reencoder_and_refuses_a_fork`'s oracle was `holo.receive.tiles._reencode_printed_cells`, which went with the receiver; its fork refusal is asserted by `test_h3_plugins_tiles.py::test_printed_cells_for_refuses_a_forked_site_geometry`.)

Per §4a, run first on the pre-deletion tree, in-place before `src/holo/receive`
is deleted. Command actually run, serially:

```
HOLO3_RUN_SLOW_TESTS=1 env/bin/python -m pytest \
  src/holo/receiver/tests/test_h3_drift_receiver.py src/holo/receiver/tests/test_h3_drift_kernels.py \
  src/holo/receiver/tests/test_h3_drift_declared.py -v -p no:cacheprovider
```

All three modules together: **186 passed, 0 failed, 0 skipped, 0 errors**,
3.78 s. Full log:
`<tmp>

Of those 186, the rows below are the ones that import or declare a
`holo.receive` target (via the module's `importorskip` lines or a
`CONSTANT_PAIRS` row) — the legs §4b–§4d rule as one-time records. Rows that
rest only on a surviving target are not repeated here; they are named once,
by count, in the "surviving declared targets" paragraph below.

**`test_h3_drift_kernels.py`** — the 6 named in §4b plus the trimmed
`v1_sampling`/`v1_colcal` tail of the geometry test (its own `tile_of_cell`
and self-contained parity/hash asserts already went as the holo2 leg,
§2 above; this is its remaining `v1_consumers` leg):

| test function | ids | result |
|---|---|---|
| `test_pava_nodes_and_calibration_match_v1_detect` | 1 | passed |
| `test_pava_offset_solver_and_losses_match_v1` | 1 | passed |
| `test_pava_ordered_context_offsets_match_v1_detect` | 1 | passed |
| `test_pava_class_balanced_weights_match_v1_color_calibration` | 1 | passed |
| `test_geometry_site_hash_parity_and_rotation_match_the_v1_consumers` | 1 | passed |
| `test_owners_freeze_page_owners_matches_v1_payload_model` | 1 | passed |
| `test_owners_order_keys_reproduce_v1_on_the_key_sorted_list` | 1 | passed |
| **module total** | **7** | **7 passed** |

**`test_h3_drift_receiver.py`** — every test function except the three that
rest only on the four surviving targets
(`test_calibrate_row_identity_agrees_with_v1_resolution` and the
printed-cells/re-encoder pair, listed in the survivors paragraph below):

| test function | ids | result |
|---|---|---|
| `test_calibrate_site_lookup_and_reference_labels_match_v1_sampling` | 1 | passed |
| `test_calibrate_filler_branch_reference_labels_match_v1` | 1 | passed |
| `test_calibrate_region_pitch_matches_v1_sampling` | 3 | passed |
| `test_calibrate_window_sampling_matches_v1_payload_sampling` | 4 | passed |
| `test_calibrate_crop_luma_matches_the_v1_raster_laws` | 1 | passed |
| `test_calibrate_window_scores_edge_cases_match_v1` | 4 | passed |
| `test_calibrate_window_fit_matches_v1_detect_including_refusals` | 5 | passed |
| `test_calibrate_tiny_window_refuses_with_the_same_reason_as_v1` | 1 | passed |
| `test_calibrate_context_primitives_match_v1_detect` | 3 | passed |
| `test_calibrate_duplicate_page_cell_raises_on_both_sides` | 1 | passed |
| `test_calibrate_region_context_decision_matches_v1_fit_context` | 4 | passed |
| `test_calibrate_context_floor_cascade_names_its_reason` | 4 | passed |
| `test_calibrate_empty_context_sides_refuse_with_their_named_reasons` | 1 | passed |
| `test_calibrate_physical_cell_ids_match_v1_payload_context` | 1 | passed |
| `test_refine_constants_agree_with_v1` | 18 | passed |
| `test_refine_private_constants_match_the_frozen_second_copies` | 1 | passed |
| `test_refine_block_kernels_match_v1` | 1 | passed |
| `test_refine_support_metrics_and_caps_match_v1` | 1 | passed |
| `test_refine_pose_candidate_matches_the_v1_pose_model` | 1 | passed |
| `test_refine_objectives_match_v1` | 1 | passed |
| `test_refine_adoption_gate_matches_v1_and_every_clause_binds` | 1 | passed |
| `test_refine_context_gate_kernel_matches_v1_fixed_detector_logits` | 3 | passed |
| `test_refine_context_gate_baseline_call_matches_v1_end_to_end` | 1 | passed |
| `test_refine_without_an_adopted_context_v1_scores_the_marginal_fit` | 1 | passed |
| `test_color_blind_component_bits_match_v1_color_detect` | 1 | passed |
| `test_color_qda_fit_and_scores_match_v1_color_detect` | 1 | passed |
| `test_color_qda_degenerate_and_collapsed_paths_match_v1` | 1 | passed |
| `test_color_component_pava_matches_v1_color_detect` | 1 | passed |
| `test_color_cmy8_support_qualification_matches_v1_color_detect` | 1 | passed |
| `test_color_newton_head_solver_matches_v1_color_calibration` | 1 | passed |
| `test_color_class_balanced_weights_match_v1_color_calibration` | 1 | passed |
| `test_color_head_sub_split_matches_v1_color_calibration` | 1 | passed |
| `test_color_refine_floors_match_the_v1_colour_namespace` | 10 | passed |
| `test_color_refine_private_constants_match_v1` | 1 | passed |
| `test_k_tile_attempts_match_the_v1_attempt_records` | 1 | passed |
| `test_below_attempt_floor_matches_the_v1_refusal_and_never_arms_retry` | 1 | passed |
| `test_conflicting_certificate_mint_raises_integrity_error` | 1 | passed |
| `test_a3_constants_match_v1_color_locality` | 1 | passed |
| `test_a4b_constants_match_v1_color_conditioning` | 1 | passed |
| `test_a3_balanced_base_weights_match_v1_color_locality` | 1 | passed |
| `test_a3_weighted_affine_matches_v1_color_locality` | 1 | passed |
| `test_a4b_masking_and_pattern_kernels_match_v1_color_conditioning` | 1 | passed |
| `test_a4b_sibling_subset_marginals_match_v1_color_detect` | 1 | passed |
| **module total (43 functions)** | **91** | **91 passed** |

`test_conflicting_certificate_mint_raises_integrity_error` touches no v1
module at all (it is self-contained `holo.receiver.plugins.tiles` logic); it is
listed here anyway because §4c calls everything but the three survivors "a
one-time record" and does not carve this one out — worth a look at Phase 4
time in case it wants to move rather than delete.

**`test_h3_drift_declared.py`** — only
`test_no_undeclared_constant_divergence` touches a `holo.receive` target,
and only on 7 of its 16 `CONSTANT_PAIRS` ids (the seven §4d marks for
removal); its other 9 ids and every other function in this module rest on
`holo.core`/`holo.format` and are not one-time records (see the survivors
paragraph):

| test function | ids | result |
|---|---|---|
| `test_no_undeclared_constant_divergence` — `pava-vs-detect`, `calibrate-vs-detect`, `color_model-vs-color_calibration`, `color_model-vs-color_detect`, `color_refine-vs-color_refine`, `refine-vs-certified_refine`, `tiles-vs-tiles` | 7 | passed |
| **module total** | **7** | **7 passed** |

**Totals across the three modules: 51 test functions, 105 test ids, 105
passed, 0 failed** — the one-time record this subsection exists to make.

**Declared targets that survive Phase 4** (not recorded above — they keep
running after `src/holo/receive` is deleted, unaffected):

- kernels: `holo.core.bch`, `holo.core.ldpc.construct`, `holo.core.ldpc.decode`
  — the 16 BCH/LDPC test functions, 51 ids, all passed in this same run.
- receiver: `holo.format.fossils`, `holo.format.metadata`,
  `holo.format.resolve`, `holo.gen.compose` —
  `test_calibrate_row_identity_agrees_with_v1_resolution`,
  `test_printed_cells_for_reproduces_the_v1_emitted_page_slice`,
  `test_printed_cells_for_matches_the_v1_reencoder_and_refuses_a_fork`;
  3 ids, all passed.
- declared: the nine `holo.core`/`holo.format` `CONSTANT_PAIRS` rows (9 of
  `test_no_undeclared_constant_divergence`'s 16 ids) plus every other
  function in the module (the 7 `DECLARED_DIVERGENCES` rows, the LDPC
  digest ×6, the two fossil tests, the site-seed test); 27 ids, all passed.

Check against the run total: one-time-record ids (7 + 91 + 7 = 105) plus
surviving-target ids (51 + 3 + 27 = 81) = **186**, the run's own total —
every passing id this run produced is accounted for exactly once, either
above or in this paragraph.

## 3. Suite-shape repairs made in the same package

- `test_h3_conventions.py`: `EXTRA_PYTEST_ROOTS` no longer names
  `holo2/measure/verdicts`; the `test_roundtrip` duplicate-import row
  retired with it (that collision existed only because the verdicts gate
  was a collected root). The `conftest` row now matches the declared
  paths **that exist**, so the gate is true with holo2 present and gone;
  when Phase 3 drops `holo2/tests` from `pyproject.toml` the row's second
  path disappears on its own and the row can be deleted.
- The conftest-shadow pin is restated against the repo-root `conftest.py`
  (the non-package conftest that survives every phase) instead of holo2's.
- `test_v1_and_holo2_packages_import_from_their_pinned_source_trees` lost
  its holo2 half; the v1 half stays until Phase 4.
- The drift-target floor was re-derived: 55 declared targets before this
  package, minus the ten holo2 ones (5 kernels, 2 declared, 3 receiver),
  **= 45**, pinned as `N_DRIFT_TARGETS_FLOOR` with the arithmetic in the
  source. `N_DRIFT_MODULES` stays 4.
- `FIREWALL_ALLOWLIST`'s golden is unchanged: every allowlisted file still
  reaches across to `holo` (v1). Only its `test_h3_conventions.py`
  rationale string was corrected.

## 4. Phase-4 recipe for the `holo.receive` legs — PREPARED, NOT APPLIED

`src/holo/receive` lives until Phase 4 (`claude-plan.md` §10). When it
goes, the same treatment applies, with one difference: **nothing here is
format law**, so nothing is frozen — `holo.core` and `holo.format` stay
and keep every format pin alive. All of it is a one-time record.

**4a. Run first, on the pre-deletion tree** (`claude-plan.md` §10 step
4.3, which already requires it): the
whole slow lane, then the receiver-numerics node ids on their own, and
record module / count / pass in §2 above with the sha. ~54 ids in
`test_h3_drift_receiver.py` and ~7 in `test_h3_drift_kernels.py` plus the
7 `CONSTANT_PAIRS` rows in `test_h3_drift_declared.py`.

**4b. `test_h3_drift_kernels.py` — becomes one-time records:**
`test_pava_nodes_and_calibration_match_v1_detect`,
`test_pava_offset_solver_and_losses_match_v1`,
`test_pava_ordered_context_offsets_match_v1_detect`,
`test_pava_class_balanced_weights_match_v1_color_calibration`,
`test_owners_freeze_page_owners_matches_v1_payload_model`,
`test_owners_order_keys_reproduce_v1_on_the_key_sorted_list`. Trim
`test_geometry_site_hash_parity_and_rotation_match_the_v1_consumers` to
its self-contained parity/hash asserts (its `head_sub_split` and
`rotated_points` legs are v1-receive) — `rotated_points` and
`tile_of_cell` are covered by `test_h3_lib_geometry.py`, so deleting it
outright is also defensible; say which in the commit body. Declared
targets drop from 8 to **3** (`holo.core.bch`,
`holo.core.ldpc.construct`, `holo.core.ldpc.decode`). `bch_decode_corpus`
keeps using `v1_bch.encode` — `holo.core.bch` survives Phase 4 — so the
frozen BCH digests of §1 are unaffected; if it is ever swapped to
`h3_bch.encode`, the digests still hold, because
`test_bch_encode_matches_v1_on_seeded_messages` pins the two encoders
bit-identical.

**4c. `test_h3_drift_receiver.py` — almost the whole module.** Fourteen of
its eighteen declared targets are `holo.receive.*` (`detect`,
`_payload_context`, `_payload_sampling`, `payload`, `certified_refine`,
`color_detect`, `color_calibration`, `color_anchoring`, `color_refine`,
`tiles`, `evidence`, `placement.model`, plus the lazily skipped
`color_locality` and `color_conditioning`). Four survive:
`holo.format.fossils`, `holo.format.metadata`, `holo.format.resolve`,
`holo.gen.compose`. Keep the module with only the tests that rest on those
four (the printed-cells / re-encoder pair and the format-identity checks);
everything else is a one-time record. If the survivors are better re-homed
into `test_h3_drift_format.py`, delete the module instead and drop
`N_DRIFT_MODULES` to 3 and the allowlist golden by one name — that is a
census decision, not a law.

**4d. `test_h3_drift_declared.py`.** Seven `CONSTANT_PAIRS` rows go
(`lib.pava`/`plugins.calibrate` vs `holo.receive.detect`, `color_model` vs
`color_calibration` and vs `color_detect`, `color_refine` vs
`color_refine`, `plugins.refine` vs `certified_refine`, `plugins.tiles` vs
`tiles`), with `MIN_SHARED_CONSTANTS` trimmed in lockstep — the two tables
are asserted equal by
`test_declared_divergence_table_ids_are_unique_and_documented`. The
remaining rows are all `holo.core`/`holo.format` and stay — nine since the column-group merge (`2d56e5a`) added (`holo.receiver.format.fountain`, `holo.core.column_groups`) with its MIN_SHARED_CONSTANTS entry; re-derive the §4e floor from the tree at Phase 4, as §4e instructs. All four
declared importorskip targets survive.

**4e. The new floor.** Keeping the receiver module for its four
format/gen targets: 15 (`format`) + 3 (`kernels`) + 4 (`declared`) + 4
(`receiver`) = **26**; `N_DRIFT_MODULES` stays 4. If 4c deletes the
module instead, the floor is **22** and `N_DRIFT_MODULES` is 3. Re-derive
from the tree rather than trusting this line, and state the arithmetic in
the source comment as this package did.

**4f. `FIREWALL_ALLOWLIST`.** Shrink only if a file stops importing a
foreign tree. `_h3_sims.py`, `conftest.py` and `test_h3_page_domain.py`
build sims with `holo.gen`/`holo.format` and stay allowlisted;
`test_h3_conventions.py` keeps its v1 import-location pin only if that
pin still means something — after Phase 4 `src/holo` is the format
authority, so the pin should stay and be reworded, not deleted.

## §4 APPLIED — 2026-09-05, on the tree with the receiver already gone

The recipe above was written before the deletion; this is what it came to
when applied against the tree at `284ae3e`. Two places where the tree
disagreed with the recipe are marked **correction**.

**Kernels** (`test_h3_drift_kernels.py`, 599 → 436 lines, 23 → 16 test
functions, 58 → 51 ids). The six §4b functions and the geometry test are
gone; their record is §2 above. The geometry test was **deleted outright**
rather than trimmed: each of its self-contained legs is already asserted in
holo3's own unit lanes — the 131/17 lattice, its parity bit and the
head/reveal masks in `test_h3_lib_geometry.py`
(`test_site_hash_is_the_single_home_of_the_131_17_lattice`,
`test_site_parity_is_the_low_bit_of_the_same_hash`,
`test_the_head_and_reveal_masks_are_bits_of_the_same_hash`),
`rotated_points` there too, and `head_sub_split` as the second bit of the
site hash in `test_h3_plugins_color.py`. Declared targets 8 → 3; the
`h3_geom`/`h3_owners`/`h3_pava` imports and `LIB_SEED` went with them. The
frozen BCH digests are untouched and `bch_decode_corpus` still calls
`v1_bch.encode`.

**Receiver** (`test_h3_drift_receiver.py`, 1,161 lines, 46 test functions,
94 ids — **deleted**). §4c's second option was taken: only two of its tests
still had an oracle, so they folded into `test_h3_drift_format.py` and the
module went. `N_DRIFT_MODULES` 4 → 3.

- Folded: `test_printed_cells_for_reproduces_the_v1_emitted_page_slice`
  (unchanged, its `_sim_k_page` helper inlined) and
  `test_calibrate_row_identity_agrees_with_v1_resolution`, renamed
  `test_e029_row_identity_agrees_with_v1_resolution` — "calibrate" named
  the section it sat in, not what it checks, and the module it moved to
  already has a row-identity test over all fourteen fossils. It stays
  because it pins the top-level spec accessors (`spec.family_seed`,
  `spec.layout.cells_yx`) that the fossil test reaches by other paths.
  `holo.gen.compose` moved with them, so format's declared targets are
  15 → 16.
- **Correction to §2's survivors paragraph**: the third named survivor,
  `test_printed_cells_for_matches_the_v1_reencoder_and_refuses_a_fork`, is
  NOT reachable after the deletion. Its oracle is
  `holo.receive.tiles._reencode_printed_cells`, which went with the
  receiver; what remains of it is a fork refusal already asserted by
  `test_h3_plugins_tiles.py::test_printed_cells_for_refuses_a_forked_site_geometry`,
  on the same field with a different fork source. It is a one-time record
  (it passed in the §2 run), not a survivor. Two survivors, not three.
- `test_conflicting_certificate_mint_raises_integrity_error` **moved** to
  `test_h3_plugins_tiles.py` rather than being deleted, per §2's own note:
  it never had a v1 oracle. Worth recording for whoever prunes next: that
  module already asserts both halves of it
  (`test_merge_certificate_accepts_the_first_and_keeps_the_standing_source`
  and `test_merge_certificate_raises_on_conflicting_user_bits`), so the
  moved test is a walk of the whole mint boundary in one function, not new
  coverage.

**Declared** (`test_h3_drift_declared.py`, 364 → 356 lines, 34 → 27 ids).
The seven `holo.receive.*` `CONSTANT_PAIRS` rows and their seven
`MIN_SHARED_CONSTANTS` entries went together (the two tables are asserted
equal); nine `holo.core`/`holo.format` rows stay. All four declared
importorskip targets survive; no `DECLARED_DIVERGENCES` row named the
receiver.

**The floor, re-derived from the tree** (§4e): 45 declared targets before
this package − 5 (kernels 8 → 3) − 18 (the receiver module: 16 declared at
import plus the two the A3/A4b tests imported lazily) + 1 (`holo.gen.compose`
migrating with the folded test, format 15 → 16) = **23**, counted on the
tree by the census's own AST walk: format 16 + kernels 3 + declared 4.
`N_DRIFT_TARGETS_FLOOR` 45 → 23, `N_DRIFT_MODULES` 4 → 3, arithmetic in the
source comment. **Correction**: §4e predicted 22 for this path; it did not
allow for `holo.gen.compose` moving with the folded test.

**Conventions** (§4f). `test_the_v1_package_imports_from_its_pinned_source_tree`
kept, reworded: a dated comment says `holo` is now the format authority —
the generator that prints sheets and the law the drift lanes compare
against — so a `holo` resolved from outside this worktree's `src/` would
silently move the oracle.

**Hygiene** (§4f). `FIREWALL_ALLOWLIST` and its golden lost exactly one
name, `test_h3_drift_receiver.py`, because the file is gone; the other
seven entries all still import a foreign tree, and `FOREIGN_TREES` still
names `holo` because `src/holo` survives. `test_h3_plugins_tiles.py` did
not join the allowlist: the test that moved into it imports nothing
foreign.

**Runs.** Target modules (the five files above plus
`test_h3_plugins_tiles.py`): fast lane **106 passed, 199 skipped, 1.95 s**;
`HOLO3_RUN_SLOW_TESTS=1` **305 passed, 11.70 s**. The three drift modules
alone on the slow lane: **193 passed, 5.46 s** (kernels 51 + declared 27 +
format 115 — the 51 and 27 are exactly §2's "surviving declared targets"
counts, and 115 is format's 113 plus the two folded tests). Whole fast lane
`-n 8`: **1,850 passed, 346 skipped, 12.25 s**. pyflakes clean on every
file touched. `test_every_import_in_the_by_path_instrument_drivers_still_resolves`
passes — `measure/ctx_bench.py` was gone from the tree by the time this ran.
