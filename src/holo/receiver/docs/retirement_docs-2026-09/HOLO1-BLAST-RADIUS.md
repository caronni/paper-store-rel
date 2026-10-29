# holo1 (`src/holo/receive`) blast radius — Gate E input

Tree: `d3ce0d6` (branch `receiver-retirement`), 2026-09-05. Supersedes
`claude-plan.md` Appendix D (measured at `4e6ec3e`, before holo2's deletion,
the cmy8 column-group merge, and the analyzer W7 wave). Every count below
was run on this tree with the command shown; nothing was edited, moved, or
deleted to produce it. Read-only census only.

Headline: **152 files import `holo.receive`** (any `from holo.receive`,
`import holo.receive`, dotted `holo.receive.`, or `importorskip("holo.receive…")`),
plus **1 file** (`tests/holo/test_characterize_boundaries.py`) that names
`"holo.receive"` only as a firewall string, never an import. `src/holo/cli.py`
is the only non-`receive` file under `src/holo` that imports it, and only
function-locally.

Commands used throughout (run from `<checkout>`):
```
git grep -lE "from holo\.receive|import holo\.receive|holo\.receive\.|importorskip\(.holo\.receive" -- '*.py' | grep -v '^src/holo/receive/' | grep -v '^env/'
```

## 1. Importers (152 files import `holo.receive`; +1 firewall-string file)

| group | files | test/callable count |
|---|---|---|
| `src/holo/cli.py` | 1 | n/a (CLI) |
| `tests/holo/*` | 92 (+1 firewall-string) | 902 test functions in the 80 `test_*.py` files; 12 more are non-collected helper/bench modules |
| `measure/*` | 47 | n/a (never pytest-collected) |
| `src/holo/receiver/*` | 11 | 3 drift-lane test modules + 8 historical `verify/` scripts |
| `experiments/*` | 1 | n/a (one-off census script) |
| `analyzer/*` | 0 | — confirmed clean, see 1f |
| **total** | **152** | |

### 1a. `src/holo/cli.py` (1 file)

| file | kind | what it uses | Phase-4 disposition |
|---|---|---|---|
| `src/holo/cli.py` | CLI composition root | `cmd_decode` (lines 383-784) imports, ALL function-local: `holo.receive` top-level symbols (`CaptureInput`, `DiscoveryReceiveRequest`, `ProvisionalReceiverWarning`, `ReceiveRequest`, `run_discovery_receive`, `run_receive`, `close_volume` — no, that's a test import, ignore), `holo.receive._parallel` (`set_worker_count`), `holo.receive.discovery_state` (`DISCOVERY_MAGIC`, `state_file_magic`), `holo.receive.production.production_pipeline`, `holo.receive.session.{STATE_MAGIC,load_session}`, `holo.receive.diag.timing.{TimingObserver,render_timing_table}`, `holo.receive.diag.ReceiveDiagnostics`, `holo.receive.diag.field_stats.{FieldStats,replay_jsonl_row}`. `main()` (line 784) routes `discover` to `holo.characterize.__main__` (line 790) before argparse even runs, and dispatches `{registry,fit,capacity,generate,decode}` to `cmd_registry/cmd_fit/cmd_capacity/cmd_generate/cmd_decode` (line 1000-1001) — verified zero module-level `from holo.receive` / `import holo.receive` anywhere in the file (first 58 lines checked). The "cold format discovery" path (`discovery_mode` when neither `--coding` nor `--format` is given) lives entirely inside `cmd_decode`, not as a separate CLI verb. | REWRITE (4.1): `decode`/its diag flags forward to `holo.receiver.cli`; `registry\|fit\|capacity\|generate\|discover` stay untouched. |

### 1b. `tests/holo/*` (92 importers + 1 firewall-string file = 93; 1552 tests collected in `tests/holo` total, `env/bin/python -m pytest tests/holo --collect-only -q`)

**(a) Receiver-only — DELETE. 70 `test_*.py` files, 832 test functions** (each file's count from `pytest <file> --collect-only -q`):
`test_cli_close_shortfall.py`(2) `test_close_schedule.py`(14) `test_close_surplus_audit.py`(9) `test_cold_search_exactness.py`(16) `test_color_calibration.py`(43) `test_color_conditioning.py`(41) `test_color_context.py`(17) `test_color_detector.py`(17) `test_color_field.py`(30) `test_color_field_arm.py`(8) `test_color_locality.py`(20) `test_color_ncc_fft.py`(17) `test_color_registration.py`(3) `test_color_stack.py`(17) `test_color_uplift_lanes.py`(19) `test_detect_unit.py`(22) `test_diag_timing.py`(4) `test_diag_viewer.py`(31) `test_field_stats_diag.py`(34) `test_mint_once_payload.py`(8) `test_no_close.py`(4) `test_parallel_exactness.py`(11) `test_payload_nulls.py`(5) `test_payload_unification.py`(15) `test_phased_roundtrip_e2e.py`(1) `test_phased_schedule.py`(11) `test_placement_fold_regression.py`(2) `test_placement_frontier.py`(4) `test_placement_null_battery.py`(2) `test_placement_null_battery_extended.py`(13) `test_placement_policy_golden.py`(8) `test_plane_field_pose_regression.py`(20) `test_plane_fields.py`(13) `test_pool_law_oracle.py`(8) `test_receive_bch_quarantine.py`(10) `test_receive_bounded_sampling.py`(7) `test_receive_close.py`(5) `test_receive_color_attempts.py`(24) `test_receive_color_divergence.py`(5) `test_receive_color_evidence_blocks.py`(12) `test_receive_color_payload.py`(20) `test_receive_color_projection.py`(25) `test_receive_color_reference.py`(4) `test_receive_color_refine.py`(15) `test_receive_color_runtime_validation.py`(6) `test_receive_color_sampling_adversarial.py`(11) `test_receive_color_scale.py`(5) `test_receive_dependency_lineage.py`(5) `test_receive_discovery.py`(23) `test_receive_discovery_integrity.py`(16) `test_receive_e021_real_qualification.py`(4) `test_receive_ingest.py`(23) `test_receive_multicapture_k.py`(1) `test_receive_observer.py`(3) `test_receive_plan_prefix.py`(6) `test_receive_policy_detach.py`(14) `test_receive_production_color.py`(11) `test_receive_production_policy.py`(1) `test_receive_qualification.py`(21) `test_receive_raster_pool.py`(4) `test_receive_reauth_memo.py`(6) `test_receive_reference_filler.py`(1) `test_receive_refine_lane.py`(3) `test_receive_refined_reuse.py`(6) `test_receive_small_scrap.py`(1) `test_receive_state_codec.py`(4) `test_receive_stream_state.py`(12) `test_receive_tiles.py`(8) `test_retry_eligibility.py`(3) `test_supersession_materialization.py`(18).
Plus **12 non-`test_` helper/bench modules**, never pytest-collected directly (imported by the files above, or stand-alone benchmark drivers with 0 test-file importers): `_bench_full_domain_rival.py`, `_bench_label_shape_color.py`, `_bench_label_shape_k.py`, `_bench_parallel_ab.py`, `_bench_payload_decomp.py`, `_bench_phased.py`, `_bench_placement.py`, `_bench_real_corpus.py`, `_color_stack_fixtures.py`, `_e023c_fixtures.py`, `_qualify_e021_real.py`, `_qualify_runtime_fixtures.py`. Cross-checked: none of the 8 RE-HOME or 2 REWRITE files below import any of these 12 (`_qualify_runtime_fixtures.py` is used by `test_trust_boundaries.py`, but only by its receiver-only test functions, which the REWRITE trims away).

**(b) Format-law tests importing the receiver only for a helper/fixture — RE-HOME. 8 files, 46 tests:**

| file | kind | what it uses (the helper to re-home onto) | Phase-4 disposition |
|---|---|---|---|
| `test_lattice_receive.py` (4) | b | `production_pipeline`, `run_receive`/`ReceiveRequest`, `CaptureInput`, `SessionStatus` — asserts format-identity totality + a v2-seeded sheet decodes byte-exact | RE-HOME onto holo3 |
| `test_backbone_payload_gates.py` (3) | b | same `production_pipeline`/`run_receive` helper — the per-coding real-payload net, CLAUDE.md's acceptance checkpoint | RE-HOME |
| `test_measured_channel_gate.py` (4) | b | same helper, through the measured M281 channel simulator ("simulation before toner") | RE-HOME |
| `test_metadata_close.py` (7) | b | `holo.receive.fountain_close` only | RE-HOME |
| `test_pooled_close.py` (7) | b | `production_close`, `close_progress.CloseBlockProgress`, `fountain_close`, `records.certificate_record_from_user_bits`, `runtime.CloseContext`, `types.CloseRecord` | RE-HOME |
| `test_word_route_widening.py` (6) | b | `placement.defaults.PROVISIONAL_V1_PLACEMENT_POLICY`, `placement.model.PlacementConfig`, `placement.policy.PlacementDomainEnvelope`, `words.{WordAttemptBudget,stage_a,stage_a_hypotheses}` | RE-HOME |
| `test_pooled_dead_plane_gate.py` (2) | b | same `production_pipeline`/`run_receive` helper | RE-HOME |
| `test_color_software_qualification.py` (13) | b | `holo.receive.session.load_session` only | RE-HOME |

**(c) Mixed (part law, part receiver-only) — REWRITE. 3 files, 29 tests:**

| file | kind | what it uses | Phase-4 disposition |
|---|---|---|---|
| `test_canonical_sigmoid.py` (5) | c | one law half (`test_canonical_sigmoid_values_pinned`, `test_legacy_paperholo_used_scipy_expit_and_is_ulp_close`) vs. one receiver half (`from holo.receive.detect import _solve_offset`; `test_no_scipy_expit_in_receive_or_core`, `test_detect_source_carries_the_canonical_form`, `test_solve_offset_shortcuts_and_bisection_pinned`) | REWRITE — trim to the core-law half |
| `test_trust_boundaries.py` (19) | c | 3 pyflakes-gate tests (`test_undefined_name_checker_semantics_on_inline_snippets`, `test_no_undefined_names_across_src_holo`, `test_no_undefined_names_across_measure_instruments`) that stay, vs. 16 receiver-state/session fast-pin tests (imports `holo.receive.{tiles,cascade,diag,evidence_context,runtime,scan,session,session_validation,state_codec,types,placement.defaults,production,evidence_blocks}`) that are receiver-only | REWRITE — keep the pyflakes gate, drop the rest (per Appendix D's own framing) |
| `test_characterize_boundaries.py` (5, firewall-string only — does **not** import `holo.receive`) | — | `PRODUCTION_PACKAGES = ("core","devices","format","gen","receive")` and `CHARACTERIZE_FORBIDDEN` include the string `"holo.receive"`; verified these tests would keep PASSING even after deletion (`_production_sources()` does `(HOLO_ROOT/"receive").rglob("*.py")`, which is simply empty on a missing directory — no exception) — this is a hygiene rewrite, not a required fix | REWRITE — drop `"receive"`/`"holo.receive"` from the two tuples |

### 1c. `measure/*` (47 files)

| package | files | docstring (first line) | reads archived `.state`? |
|---|---|---|---|
| `measure/plane_fields/` | 27 of 39 `.py` files (`_affine_fit.py _context_gt.py _context_loop.py _context_loop_run.py _density.py _gt_affine_run.py _inputs.py _pose_apply.py _pose_probe.py _probe.py _residue_run.py _selfcheck.py _state_context_run.py _state_tables.py _swim_inputs.py _swim_probes.py _swim_region.py _swim_setup.py _swim_truth.py detector_residue.py extract_panels.py field_from_certs.py gt_affine.py pose_writer.py probe_density.py qualify_sheet_i.py swim_pilot.py`) | "PLANE-FIELDS instruments — the W0/V0, W6, swim and GT-affine drivers." | yes: `_inputs.py`, `_swim_inputs.py`, `_swim_setup.py` call `holo.receive.session.load_session` / `state_codec` directly |
| `measure/_color_uplift_harness/` | 9 (`ab_runner.py feature_library.py gt_score.py patch_runner.py pkfinal_lanes.py regmap.py replay.py sims.py state_cache.py`) | "Color-uplift campaign harness (PK0) — never pytest-collected." | yes: `gt_score.py`, `pkfinal_lanes.py`, `replay.py`, `state_cache.py` |
| `measure/calibration/` | 3 (`_arms.py _inputs.py _run.py`) | "E9 — LOCAL vs PAGE-GLOBAL detector calibration, as additive attempts." | yes: `_inputs.py` |
| `measure/ysampler/` | 2 (`anchor_supply.py composition.py`) | "Y-anchor sampler instruments — the ink-free anchor supply measurement." | not directly (no `session`/`state_codec` import found) |
| `measure/crop_parity/` | 1 (`_state.py`) | "Reading a holo1 `receive.state` cheaply — certificates and poses." | yes, with its own cheap direct-JSON reader; falls back to `from holo.receive.session import load_session  # main tree` (line 141) only when the cheap path can't handle it |
| `measure/parity/` | 1 (`extract_holo1_certs.py`) | "Extract the certified tile set from a holo1 receive.state, cheaply." (no package `__init__.py` exists) | yes, same pattern: own cheap reader + `from holo.receive.session import load_session` fallback (line 185) |
| `measure/` (top-level scripts) | 4 (`calibrate_stage_profile.py ctx_equivalence.py pava_benchmark.py pava_equivalence.py`) | none — no module docstring on any of the four; `calibrate_stage_profile.py` and `pava_benchmark.py` and `pava_equivalence.py` do `from holo.receive import detect as oracle` and compare it against `holo.receiver.lib.pava`/`holo.receiver.data.Placement`; `ctx_equivalence.py` compares `holo.receiver.plugins.color_region_ctx` against a fixture, importing `holo.receive` only transitively via its `ctx_fixture` helper | no |

Reading archived v1 `.state` files is possible only through `src/holo/receive/state_codec.py` (encode/decode) and `session.py` (`load_session`/`save_session`, which call `state_codec`) — **ten measure modules do this directly**: `measure/_color_uplift_harness/{gt_score,pkfinal_lanes,replay,state_cache}.py`, `measure/calibration/_inputs.py`, `measure/crop_parity/_state.py`, `measure/parity/extract_holo1_certs.py`, `measure/plane_fields/{_inputs,_swim_inputs,_swim_setup}.py`. After Phase 4 deletes `state_codec.py`/`session.py`, every archived v1 `.state` file (including sheet I's 2.85 GB state) becomes **unreadable** by anything in this tree unless one of these readers is preserved — this is squarely a Gate E decision (see §9). It is lower-stakes than it looks: the certificate sets these instruments actually consume were already frozen at Phase 0 into `src/holo/receiver/docs/retirement_docs-2026-09/holo1-certificates/` (28 JSON files + `INDEX.md`), so a reader that speaks the frozen-certificate format may already satisfy every one of these ten modules without needing `state_codec.py` at all — that substitution was not checked module-by-module here.

### 1d. `src/holo/receiver/*` (11 files)

**Drift lanes — 3 test modules** (`src/holo/receiver/tests/test_h3_drift_declared.py`, `test_h3_drift_kernels.py`, `test_h3_drift_receiver.py`): see §6.

**`src/holo/receiver/docs/conversion_docs/verify/` — 8 of its 25 scripts import `holo.receive`** (`verify_calibrate.py verify_color_model.py verify_color_refine.py verify_color_region.py verify_lib_kernels.py verify_placement.py verify_refine.py verify_tiles.py`). This directory is documented as "a historical record" that stays untouched. It already is one: **5 of the 25 scripts currently do `import holo2...` / `from holo2...`** (`verify_bch.py verify_intake_survey.py verify_lib_kernels.py verify_placement.py verify_refine.py`) and are therefore **already non-executable** since holo2 was deleted at `a805888` — nobody has run them since, and nothing in CI collects them (they are not under `tests/`, not `test_*.py`). Phase 4 will make 5 more of them non-executable this same way (`verify_calibrate.py verify_color_model.py verify_color_refine.py verify_color_region.py verify_tiles.py` — the 8 `holo.receive` importers minus the 3 that already fail on the `holo2` import first: `verify_lib_kernels.py`, `verify_placement.py`, `verify_refine.py`). Net effect: 10 of 25 `verify/` scripts unrunnable after Phase 4 (up from 5 today), all silent (nothing collects or runs this directory), consistent with its "historical record, stays" disposition.

### 1e. `experiments/*` (1 file)

`experiments/029-holo-v1-first-print/census_done_geometry.py` — per Phase 4.3, stays with a header note naming the last sha that runs it (not deleted, not re-homed; a frozen one-off census script).

### 1f. `analyzer/*` — zero direct importers, confirmed clean

`analyzer/truth.py`'s `_install_holo1()` (line 90) is the "holo1 GT reconstruction" bridge the task asked about. It does **not** import anything under `src/holo/receive`:
```python
def _install_holo1() -> Any:
    from measure.yask import _paths
    _paths.install_src()
    from measure.crop_parity import _gt
    return _gt
```
`measure/crop_parity/_gt.py` re-encodes the recovered payload through **generation** arithmetic only (`gen/compose.compose_page_cells`, `metadata.tile_bits`, `VolumeCode.encode_symbols` — `holo.core`/`holo.format`/`holo.gen`, all of which stay). `measure/yask/_paths.py` only ever puts `<worktree>/src` on `sys.path` for that same generation import; grepped for any `holo.receive` reference anywhere under `measure/yask/` — none. So Phase 4 does not touch analyzer's GT path at all. One curiosity worth a footnote: `measure/yask/_paths.py`'s docstring says "the holo3 branch's worktree deletes ~1,600 lines under `src/holo/receive`; this one does not" — no branch named `holo3` currently exists (`git branch -a` lists `main`, `receiver-retirement`, `receiver-retirement-pre-rebase`, `analyzer-w7`); this is either stale terminology from an earlier working arrangement or a forward reference to whichever worktree eventually executes Phase 4. It does not affect the finding above (no import exists either way), so it is a documentation nit, not a Gate E blocker.

### 1g. Anything else — wiring only, no other Python importers

`scripts/`, `util/`, `pyproject.toml`, `conftest.py` carry no Python import of `holo.receive`. Two shell scripts do invoke the CLI path that reaches it — see §8.

## 2. `src/holo/receive` itself

88 files, **41,711 lines** (`find src/holo/receive -name '*.py' | xargs wc -l`), against `src/holo`'s non-`receive` total of **25,293 lines** (`core/format/gen/qualification/devices/characterize` + `cli.py`/`cli_gen.py`) — `receive/` is 62% of the package by line count. Largest modules: `place.py` (1,710), `placement/search.py` (1,099), `diag/viewer.py` (996), `types.py` (992), `runtime.py` (990), `color_stack.py` (949), `certified_refine.py` (947), `evidence_blocks.py` (938). Sub-packages: `receive/diag/` (12 files — the `--diag` live-viewer stack), `receive/placement/` (7 files — cold search + word placement), plus 69 flat modules (color stack, payload/evidence/close machinery, discovery, state I/O).

**Blocks a clean delete?** No. Confirmed by `git grep -l "holo\.receive" -- 'src/holo/*.py' 'src/holo/core/*.py' 'src/holo/format/*.py' 'src/holo/gen/*.py' 'src/holo/qualification/*.py' 'src/holo/characterize*'`: the only hit outside `receive/` itself is `src/holo/cli.py`, and every one of its `holo.receive` imports is function-local inside `cmd_decode` (§1a). `core/format/gen/qualification/devices/characterize` are receiver-free.

## 3. `confetti.py` surface

`./confetti.py --help` (`env/bin/python confetti.py --help`, matches the source read of `src/holo/cli.py:784-1001`):
```
usage: holo [-h] {registry,fit,capacity,generate,decode,discover} ...
```
- `registry | fit | capacity | generate` → generation code (`holo.gen`/`holo.format`/`holo.devices`), unaffected by Phase 4.
- `decode` → `cmd_decode`, which imports `holo.receive` exclusively (function-local); carries `--scan/--state/--mopup/--refine/--diag*/--profile-timing`, and the cold-discovery branch (no separate CLI verb — triggered when neither `--coding` nor `--format` is given and the state file isn't already an exact-session `STATE_MAGIC`; routes to `run_discovery_receive` against `holo.receive.discovery`/`discovery_state`). Phase 4.1 replaces this whole command body with a forward to `holo.receiver.cli`.
- `discover` → `holo.characterize.__main__` (line 790), intercepted before argparse even builds — an isolated instrument, no coupling to `receive/`. Unaffected by Phase 4 (this is the "cold format discovery" the plan already ruled to archive **for later port**, not delete — its actual code lives inside `src/holo/receive/{discovery.py,discovery_state.py}` (860+395 = 1,255 lines) plus the `discovery_mode` branch of `cmd_decode`, NOT under `holo.characterize` — `discover` the CLI verb is a *different*, already-isolated instrument that the plan does not touch).
- `confetti3.py` (`./confetti3.py …` → `holo.receiver.cli.main`) already exists as the holo3-native spelling and needs no change.

## 4. `tests/holo` — what breaks

`env/bin/python -m pytest tests/holo --collect-only -q` → **1552 tests collected**.
Of these, **902 test functions in 80 `test_*.py` files literally `import holo.receive...`** and would raise `ImportError`/`ModuleNotFoundError` the moment `src/holo/receive` is deleted (per-file counts in §1b). Breakdown of the 902: **832 in the 70 receiver-only files** (straight deletion), **46 in the 8 RE-HOME files** (must move onto a src/holo/receiver/format-law helper before deletion or these regress from "passing" to "gone"), **24 in the 2 REWRITE/mixed files** (`test_canonical_sigmoid.py` 5, `test_trust_boundaries.py` 19). `test_characterize_boundaries.py`'s 5 tests do **not** break (§1b(c) — confirmed by reading `_production_sources()`, which globs a possibly-missing directory without raising).

## 5. `measure/` instruments — full detail in §1c

Ten modules across five packages read archived v1 `.state` files directly via `holo.receive.session.load_session` (or `state_codec` beneath it): `measure/_color_uplift_harness/{gt_score,pkfinal_lanes,replay,state_cache}.py`, `measure/calibration/_inputs.py`, `measure/crop_parity/_state.py`, `measure/parity/extract_holo1_certs.py`, `measure/plane_fields/{_inputs,_swim_inputs,_swim_setup}.py`. Two of these (`crop_parity/_state.py`, `parity/extract_holo1_certs.py`) implement their **own** cheap direct-JSON state reader as the primary path (avoiding `load_session`'s ~7x memory blowup from decompressing every evidence block) and only fall back to `holo.receive.session.load_session` for cases their fast path can't handle — so they are not fully independent of `state_codec.py` today, but they demonstrate the frozen-certificate substitute is plausible (§1c, §9).

## 6. holo3 drift lanes

`env/bin/python -c '...'` running the suite's own `_importorskip_targets()` logic (from `src/holo/receiver/tests/test_h3_conventions.py:414-431`) against the four `test_h3_drift_*.py` modules gives, **measured on this tree**:

| module | total importorskip targets | of which `holo.receive.*` |
|---|---|---|
| `test_h3_drift_declared.py` | 4 | 0 |
| `test_h3_drift_format.py` | 15 | 0 |
| `test_h3_drift_kernels.py` | 8 | 5 |
| `test_h3_drift_receiver.py` | 19 | 15 |
| **total** | **46** | **20** |

`N_DRIFT_MODULES = 4`, `N_DRIFT_TARGETS_FLOOR = 45` (both in `test_h3_conventions.py:414-419`) — 46 ≥ 45, consistent; the comment's own arithmetic ("55 before suite-prep minus ten holo2 ones = 45") checks out against this measurement.

`PRESERVATION.md` §4's Phase-4 recipe (prepared, not applied) says:
- **§4a** — run the whole slow lane once pre-deletion, then the receiver-numerics node ids alone (~54 in `test_h3_drift_receiver.py`, ~7 in `test_h3_drift_kernels.py`, the 7 `CONSTANT_PAIRS` rows in `test_h3_drift_declared.py`), record pass+sha. Not yet run (this census is read-only).
- **§4b** — `test_h3_drift_kernels.py` declared targets drop from **8 to 3** after Phase 4 (`holo.core.bch`, `holo.core.ldpc.construct`, `holo.core.ldpc.decode` survive) — **matches this tree exactly** (measured 8 total, 5 receive, 3 non-receive).
- **§4c** — `test_h3_drift_receiver.py`: PRESERVATION.md states "eighteen declared targets... fourteen... `holo.receive.*`", but this tree measures **19 declared / 15 receive** (file unchanged since `PRESERVATION.md`'s own commit `8a78519` — `git diff 8a78519 HEAD -- src/holo/receiver/tests/test_h3_drift_receiver.py` is empty, so this is a counting correction, not drift). Four survivors named — `holo.format.fossils`, `holo.format.metadata`, `holo.format.resolve`, `holo.gen.compose` — are unaffected by the off-by-one and still hold.
- **§4d** — `test_h3_drift_declared.py`'s `CONSTANT_PAIRS` table has **16 rows today** (verified by reading the tuple at lines 244-260); the 7 rows naming a `holo.receive.*` target (lines 254-260: `pava`/`detect`, `calibrate`/`detect`, `color_model`/`color_calibration`, `color_model`/`color_detect`, `color_refine`/`color_refine`, `refine`/`certified_refine`, `tiles`/`tiles`) are exactly the ones §4d says to drop; the remaining **9 rows** (lines 245-253, all `holo.core`/`holo.format`) match §4d's stated post-Phase-4 count precisely, including the column-group merge's added `(holo.receiver.format.fountain, holo.core.column_groups)` pair.
- **§4e** — new floor 15(format)+3(kernels)+4(declared)+4(receiver)=**26**, `N_DRIFT_MODULES` stays 4; or, if `test_h3_drift_receiver.py` is deleted outright instead of trimmed, floor **22** / `N_DRIFT_MODULES` 3. Both arithmetic paths are unaffected by the §4c off-by-one (they rest on "4 survivors", not the total).
- **§4f** — `FIREWALL_ALLOWLIST` actually lives in `src/holo/receiver/tests/test_h3_hygiene.py` (not `test_h3_conventions.py`, though that file is one of the 8 allowlisted names), verified at lines 23-32: 8 entries, matches PRESERVATION's description (`_h3_sims.py`/`conftest.py`/`test_h3_page_domain.py` build sims with `holo.gen`/`holo.format` and stay; the four drift modules stay for the reasons above; `test_h3_conventions.py` keeps its entry, reworded).

**Conclusion: §4's recipe holds on the current tree** except the one off-by-one in §4c's prose (18/14 → measured 19/15), which does not change any of §4e's arithmetic. Safe to apply as written, with that one correction.

## 7. Docs

`git grep -lE "src/holo/receive|holo\.receive|confetti\.py decode" -- 'docs/*.md'` → **28 files**, of which **14 are already-archived `docs/archive/holo2/*.md`** (Phase 3 leftovers, out of scope — they cite the receiver only in passing historical prose) and **16 are live**:

| doc | hits | normative or log |
|---|---|---|
| `docs/RECEIVE-DESIGN.md` | 6 | **normative** — gets the retirement header (4.4) |
| `docs/HOLO-DESIGN.md` | 2 | **normative** — receiver clauses need editing |
| `docs/LAYERS.md` | 1 | **normative** — registry rows reference the receiver |
| `docs/COLOR-UPLIFT-MEASUREMENTS.md` | 10 | **normative** (named in the task) |
| `docs/COLOR-UPLIFT-PLAN.md` | 8 | **normative** |
| `docs/COLOR-UPLIFT-REVIEW.md` | 24 | **normative** |
| `docs/PLANE-FIELDS.md` | 0 by this exact grep, **12 by a broader `receive` substring search** | **normative** — talks about "the receiver" and `receive/plane_fields.py` in prose throughout (§6.2, W0-W6 workplan) but never spells `holo.receive` or `src/holo/receive` literally; needs the same inline-note treatment even though the literal grep misses it |
| `docs/HOLO-SOFTWARE-ARCHITECTURE.md` | 33 | log — §4 → holo3 per 4.4 |
| `docs/CHARACTERIZE-DESIGN.md` | 2 | log |
| `docs/CHARACTERIZE-WORKPLAN.md` | 1 | log |
| `docs/CMY8-POOLING-PLAN.md` | 1 | log |
| `docs/COMPOSITE-POSE-DESIGN.md` | 1 | log |
| `docs/FORMAT-SPACE.md` | 1 | log |
| `docs/FULL-DOMAIN-RIVAL-ANALYSIS.md` | 1 | log |
| `docs/LABEL-SAMPLING-SHAPE-ANALYSIS.md` | 3 | log |
| `docs/PRINT-DAY.md` | 1 | log |
| `docs/RECEIVER-GROWTH-AUDIT.md` | 10 | log (its entire subject is the receiver) |

`CLAUDE.md`: 0 hits on the literal 3-pattern grep, but `confetti.py registry \| capacity \| generate \| decode \| discover \| characterize` appears at line 421-422, and the "**Receiver status: PROVISIONAL**" bullet Phase 4.4 targets is now at **line 538** (not `:477-481` — the cmy8 column-group merge shifted it, as the plan itself anticipated). `README.md`: 0 hits on the literal grep but is saturated with prose about "the receiver"/`holo.cli decode` (lines 12-15, 99, and ~15 more below — this is the doc Phase 4.4 names first).

`src/holo/receiver/**/*.md`: **43 files**, split cleanly: **14 in `src/holo/receiver/docs/conversion_docs/*.md`** (the numbered conversion chapters — a deliberate by-design comparison record, stays per the plan) and **29 in `src/holo/receiver/docs/retirement_docs-2026-09/*.md`** (this campaign's own working papers — `RULINGS*.md`, `HOLO1-MAP.md`, `PORT-BRIEFS/*`, `PRESERVATION.md`, `GATE-*-BRIEF.md`, `seeds/*` — these are the campaign's own record, not "docs that need editing," they're already about the retirement). `experiments/**/*.md`: **0 hits**.

Three dangling holo3 doc-pointer comments named in Phase 4.4 (`src/holo/receiver/plugins/color_conditioning.py:5`, `src/holo/receiver/plugins/color_photometry.py:3-4`, `src/holo/receiver/diag/fields_pane.py:5`) were confirmed present and unchanged — each cites `docs/RECEIVE-DESIGN.md` or `docs/COLOR-UPLIFT-PLAN.md`/`docs/PLANE-FIELDS.md` by section in a docstring, not a code import; they need the pointer-target rewrite once those docs gain retirement headers, per the existing plan.

## 8. Wiring

- `pyproject.toml`: `testpaths = ["tests", "analyzer/tests"]`, `pythonpath = ["src"]` — no `holo2` remnant (confirmed: Phase 3 already removed those two lines), and **no `src/holo/receiver/tests` entry either** — holo3's suite is invoked separately (`env/bin/python -m pytest src/holo/receiver/tests`), so nothing here needs to change for Phase 4 beyond what §10 Phase 4 already anticipates (none, in fact — `testpaths`/`pythonpath` don't name `receive` specifically).
- root `conftest.py`: only exports `PYTHONPATH` for `src/`; no receiver-specific logic.
- `scripts/demo.sh`: already migrated to holo3 (`./confetti3.py decode`, per the Gate D brief's 2026-09-04 commit `3bbd951`/`144b22f`) — confirmed, no `holo.cli decode` call remains.
- **`scripts/run_c2_cmy7_hp_canon_chain.sh`** and **`scripts/run_c2_r0700_hp_flatbed_chain.sh`** still directly invoke `env PYTHONPATH=src "$PYTHON" -m holo.cli decode --state "$RUN_DIR/receive.json" ...` (lines 103/147/164) — **this is a new finding, not named in Appendix D or claude-plan.md §10's wiring checklist**. These are one-off hardware-chain drivers (named after specific print/scan combinations, presumably historical run scripts for e030-class experiments), not part of any currently-enforced gate, but they will silently break (`holo.cli`'s `decode` subcommand forwarding to holo3, or the module simply not routing this way) once Phase 4.1 lands. Needs a Gate E decision: rewrite to `confetti3.py decode`, or archive alongside the experiment logs they belong to.
- `util/`: no `holo.receive` reference anywhere (`regen_holo_ldpc_data.py`, `scrap_pack*.py` touch only `holo.core.ldpc`/generation, which stay).

## 9. Decisions Gate E must take

1. **State-reader preservation.** Ten `measure/` modules across five packages read archived v1 `.state` files via `holo.receive.session.load_session`/`state_codec.py` (§1c, §5); deleting `receive/` makes every archived `.state` file (including sheet I's 2.85 GB) unreadable from this tree unless a reader survives. Mitigating fact: the certificate sets these instruments actually need were already frozen at Phase 0 (`holo1-certificates/*.json`, 28 files) — it was not checked module-by-module whether the frozen-certificate format already satisfies all ten, so this is a real open question, not a rubber stamp.
2. **`measure/crop_parity/_state.py` and `measure/parity/extract_holo1_certs.py`** each implement a cheap direct-JSON reader as their PRIMARY path and only fall back to `holo.receive.session.load_session` in cases their fast path can't handle (§1c) — if that fallback path is ever exercised in practice, deleting `session.py` silently narrows what these two tools can read, with no test currently pinning how often the fallback fires.
3. **Two extra test files exercise `discovery.py`/`discovery_state.py`** beyond the two Phase 4.2 already names for archival (`test_receive_discovery.py`, `test_receive_discovery_integrity.py`): `test_receive_bch_quarantine.py` has a dedicated `test_discovery_load_rejects_derived_bch_nonconflict` test importing `holo.receive.discovery`/`discovery_state` directly, and `test_receive_policy_detach.py` exercises `DISCOVERY_MIGRATIONS` from `discovery_state.py`. Phase 4.2's archival checklist needs these two extra sites accounted for (extract the discovery-dependent test functions into the archived discovery test module, or accept their coverage is lost).
4. **Two hardware-chain shell scripts** (`scripts/run_c2_cmy7_hp_canon_chain.sh`, `scripts/run_c2_r0700_hp_flatbed_chain.sh`) still call `holo.cli decode` directly (§8) — not in any existing checklist. Rewrite to `confetti3.py decode`, or archive with their experiments.
5. **`docs/PLANE-FIELDS.md`** discusses the receiver throughout in prose ("the receiver", `receive/plane_fields.py`) without ever spelling `holo.receive`/`src/holo/receive` literally (§7) — a literal grep for the retirement misses it; it needs the same inline-note treatment as `docs/RECEIVE-DESIGN.md` by hand, not by grep.
6. **`test_characterize_boundaries.py`'s firewall strings** (`PRODUCTION_PACKAGES`, `CHARACTERIZE_FORBIDDEN`) would keep passing silently-degraded after deletion rather than failing (§1b(c), §4) — confirm the REWRITE happens anyway for hygiene, since nothing forces it.
7. **`src/holo/receiver/docs/conversion_docs/verify/`** will have 10 of its 25 scripts non-executable after Phase 4 (up from 5 today, already broken by holo2's deletion) — confirm this "historical record, stays, read-only" disposition is still acceptable now that the count is known precisely (§1d).
8. **`measure/yask/_paths.py`'s docstring** references "the holo3 branch's worktree" deleting `src/holo/receive` — no such branch exists today (§1f); low-priority hygiene, but worth a one-line fix so a future reader isn't confused about which worktree it means.

## 10. Deltas vs Appendix D

| Appendix D (measured at `4e6ec3e`) | this census (measured at `d3ce0d6`) | why |
|---|---|---|
| `holo2` still live, blast radius listed alongside holo1's | holo2 fully deleted (Phase 3 closed at `d3ce0d6`, confirmed `git log` shows `a805888`→`d3ce0d6`) | Phase 3 executed since Appendix D was written; moot for Gate E |
| `measure/plane_fields` — 29 files | **27 files** (verified against `4e6ec3e` too — same 27 then; `git diff 4e6ec3e HEAD -- measure/plane_fields/` is empty) | counting correction, not code drift: `context_loop.py`/`state_context.py` mention `"holo.receive worker threads"` only in a `--help` string, never an import — Appendix D's tally over-counted these two |
| `measure/*` total importers — 49 | **47** | same 2-file correction, propagated |
| `PRESERVATION.md` §4c: `test_h3_drift_receiver.py` "18 declared targets, 14 `holo.receive.*`" | measured **19 / 15** | the file is byte-identical to `PRESERVATION.md`'s own commit (`8a78519`) — a counting slip in the prose, not drift; §4e's floor arithmetic (26/22) is unaffected because it rests on "4 survivors," not the total |
| 92 `tests/holo` importers + 1 firewall-string file | same: **92 + 1**, byte-for-byte the same set | `git diff --name-status 4e6ec3e HEAD -- tests/holo/` shows only `test_column_groups.py` added (new, does not import `holo.receive`) — the receiver-importer set is untouched by the intervening column-group merge and analyzer wave |
| `src/holo/cli.py` "function-local, decode/diag only" | confirmed unchanged | — |
| no mention of `scripts/run_c2_cmy7_hp_canon_chain.sh` / `run_c2_r0700_hp_flatbed_chain.sh` | **new finding**: both still call `holo.cli decode` directly | not wired into the plan's checklist at all before this census (§8, §9.4) |
| no mention of the two extra discovery-dependent test files | **new finding**: `test_receive_bch_quarantine.py`, `test_receive_policy_detach.py` also exercise `discovery.py`/`discovery_state.py` | §9.3 |
| `src/holo/receiver/docs/conversion_docs/verify/` "imports both by design" (13 files) | precise count now: **25 scripts total, 5 already broken on `holo2`, 8 import `holo.receive` (3 overlap with the already-broken 5)** | Appendix D's "13" undercounted the directory (25 `.py` files exist) and didn't distinguish already-broken from still-live; §1d, §9.7 |
| no `docs/PLANE-FIELDS.md` citation (didn't match the literal grep) | flagged as a normative doc that discusses the receiver in prose only | §7, §9.5 |
