# HOLO2-CAPABILITIES — designed / implemented / verified / deferred

One coarse row per capability, so a leaf author can tell an H3bis
convenience from a core contract at a glance (the review's suggestion;
`H3BIS-ARCHITECTURE-REVIEW.md` §"Documentation and implementation
alignment"). Rows are capabilities, never feature-atoms — if a row needs
splitting to stay true, split it; if it needs a paragraph, it belongs in
the owning package's `DESIGN.md` instead.

Reading the columns:

- **designed** — where the contract is written. `D` = root
  `DESIGN.md`; a package name = that package's `DESIGN.md`.
- **implemented** — the module that does it today, or `—`.
- **verified** — the strongest evidence that exists: `oracle` =
  byte-compared against `src/holo` outside the tree; `real` = the H3bis
  real-sheet gate; `spine` = the synthetic end-to-end; `unit` = module
  tests only; `—` = nothing.
- **deferred** — the phase that owns the rest, per `WORKPLAN.md`. Where
  a deferred cell names a defect (`F-nn`, `D-n`), the live entry is the
  owning package's TO-FIX ledger; `DESIGN.md` §15 indexes the rest.

Status of the whole table: **PROVISIONAL** (L15). Nothing below is
qualified; "verified" means a recorded gate, never a promotion.

| capability | designed | implemented | verified | deferred |
|---|---|---|---|---|
| capture ingest + source authentication | `capture` §L1 | `capture/scan.py`, `capture/ingest.py` | oracle + real | re-auth of later pixel-derived commits (F-12) → H3.5 |
| footing ladder (exact-area apertures) | `capture` | `capture/scale_space.py` | oracle + real | — |
| payload-region survey / segmentation | `capture` | `capture/survey.py`, `lattice.py`, `_survey_tensor.py` | oracle + real (36/36 correct pitch votes on confetti) | — |
| region lattice + window plan | `solve` | `solve/plans.py`, `solve/geometry.py` | spine + real | OR-9's measured E022 lattice (200/40/70) since H4 W1 |
| ~~placement — word-seeded, single route~~ | `solve` (H3bis-grade) | `solve/wordgrid.py`, `placement_h3bis.py` | real (1,359 certs, byte-identical) | DELETED 2026-08-15 (H4 W1) |
| placement — staged word route (PL3) | `solve` | `solve/placement.py`, `place_shared.py`, `lattice_seed.py` over the W0 kernel | real (rendered corpus byte-exact, clean + warped + measured-e032 channel + oblong + rot180 + coverage ramp) | H4 W1 BUILT 2026-08-15 |
| placement — remaining production routes (chain / lower-hint / cold / subdivision / quarantine) | `solve/PROVIDERS.md` PL1/PL2/PL4–PL7 | ALL LANDED, none as a provider: chain+lower-hint are the one job's CONSULT tier (`place_job.consult`), cold is two priced tiers (`place_cold.py`, `place_tiers.py`) over the untouched `cold.py` kernel, subdivision is the scheduling set's own growth (`place_subdivide.py`), quarantine is a reduce inside the emitting fire (`quarantine.py`) | real (the verdicts' five shared decodes: channel, banded, partial, streaming, subdivision) | H4 W2–W5 BUILT; the exit numbers are WORKPLAN §H4 EXIT |
| photometric calibration — per-window PAVA marginal | `solve` §CA1 | `solve/detect.py` | oracle + real | — |
| calibration — scope framework (window / halo / region, held-out gates) | `solve/PROVIDERS.md` CA1–CA7 | — | — | H5 |
| calibration — colour stack (A0–A5, u-lane arms) | `solve/PROVIDERS.md` CA3–CA8 | — | — | H7 |
| payload certification, K (LDPC + CRC) | `format`, `solve` | `format/ldpc/`, `solve/tiles.py`, `payload.py` | oracle + real | — |
| payload — per-route attempts (SCAN / UNION / RETRY150 as spendable descriptors) | `solve/PROVIDERS.md` PY1–PY3 | `solve/payload.py` (one descriptor / read-set / spend / attempt per route; retry gated on the per-footing `baselined` fact) | unit + spine + real | per-key attempt ceiling (OR-5) → H5 |
| CRC exposure counted per lineage (L5 false-accept budget) | `D` §L5, review P1 | `SpendRecord.exposures` (monotone fold counter) summed by `payload.crc_exposure` + `SessionPlane.crc_exposure` (snapshot) | unit + real | — |
| multi-capture union (F1∘F6) | `solve`, `D` §L2 | `union` route, minted only where ≥2 distinct captures share a ppc | spine (2 captures) | H5 |
| printed-format identity (v2 grammar + `L:` catalogue) | `format`, `docs/FORMAT-SPACE.md` | `format/lattice.py` (pitch registry, `CodingParams`, canonical spelling, `parse_format_id`/`make_format`), `format/fossils.py` (twelve byte-matched legacy identities, each with a literal `spec_id`/seed and an import-time self-check against the recipe's own derivation), `format/resolve.py` (`resolve_format_ref`: `L:<id>` byte-matched, else the v2 grammar — the bare-legacy route is DELETED, RULINGS G1) | oracle (`test_oracle_lattice.py`: canonical id, v2 seed, family seed and every K codec fact member-by-member, over all three families and every registered pitch class; the twelve fossils through the `L:` route on both sides) + real (`L:c2-r0700@3392x2368` — both hardware-certified K volumes — resolves and reaches pixels through `--format`) | all six `LADDER` rungs build; r0850 is named by the catalogued colour sheet `L:c2-cmy8-r0850-p120-x1@3392x2368` (e033 sheet H) and by `c2-k-r0850@76x53` in the oracle battery, while r0547/r0625/r0775 are carried but as yet unnamed by any identity; every registered pitch class c1–c4 and every lawful rational builds (C3b, H1(a) — no scope refusal remains) |
| colour codings (CMY7 joint, CMY8 per-plane streams) | `format`, `D` glossary | **identities nameable and rows buildable at the format layer** (C2, 2026-08-22, RULINGS G2): `format/families.py` mints the codec facts and `registry_rows.make_format` the row — streams, fountain domains, derived codec/bank ids, dust furniture, pooled outer code — for every lawful cmy7/cmy8 identity, and the twelve-entry legacy catalogue carries the printed colour sheets. **Codecs refuse FATALLY until the colour port**: `tile_format_for` raises "colour codecs arrive with the colour port" (refusal F1), which every decode composition hits in a provider constructor | the FORMAT facts vs `src/holo`, member by member (`test_oracle_lattice.py`); nothing decoded | H7 |
| tile map (per-stream terminality) | `solve` | `solve/records.py`, `tilemap.py` | spine + real | `ATTEMPTED`/`ADDRESSED` as derived views (F-06 residue; the retry route gates on `baselined`) → H3.5 |
| done-pixel projection + the window gate | `solve` §6 | `solve/tilemap.py`, `solve/plane.py` | spine + real | OR-1/2/3/4; per-region done summary (OR-7) → H4 |
| refinement — RF1, pose revision (live-pose consumers, priced, no-op guarded) + F2 re-read | `solve/PROVIDERS.md` RF1; RULINGS §I (I2–I4a), §J (F1 ownership, F2 re-read) | `solve/refine.py` (`PoseRefineProvider`), `solve/tilemap.py` (`live_poses`/`live_pose`/`live_poses_of_region`, the read-time derivation every consumer now reads), `solve/resample.py` (F2's priced re-read, `RESAMPLE_TIER = COST_REFINE = 200`), `solve/generation.py` (two generations, no more), the F1 ownership key in `payload.py` (context-corrected held-out log-loss, window-scoped, tie-broken on pose id) | real (both K sheets; W2/W3/W4 pre-F1/F2 measured no positive yield three ways (+0/+0/−1), then the F1+F2 parity re-run on tree `01541a5`, 2026-08-24) | **LIVE-DEFAULT, priced 200** (`COST_REFINE`, above `cold_rest`=150); `revise=True` is the shipped default. **Measured yield on paper, F1+F2 re-run vs the refine-off baseline: +27 certificates on e029, +32 on xerox** (e029 1,911→1,938; xerox 1,882→1,914 — F1's ownership rescue plus F2's re-read closed 60 of the 83 gap tiles the W4 line measured, e029/xerox individually still 2/16 short of the v1 anchors 1,940/1,930). Cost: **+112% wall on e029** (1,127→2,385 s), **+386% wall on xerox** (719→3,494 s), commits +19%/+57%, single runs each (the refine-off baselines built their prepared planes inside those walls; F1+F2 runs adopted theirs, so the true multiple is larger still). **The price/dial question is CLOSED (RULINGS §L1, user, 2026-08-24): `revise=True` stays the default, at `COST_REFINE` as built — "it earned its keep"; under the default K-stop policy the close preempts it.** RF2 and any further refine mechanism remain unbuilt → H4/H7 |
| fountain + metadata close, verified stop | `format` §L9 | `format/fountain_close.py`, `solve/close.py` | oracle + real | surplus-audit doctrine (Q10) → H3.5 |
| durable store, commit, spend-once, resume | `D` §6.2–6.3 + `core` | `core/store.py`, `commit.py`, `identity.py` | unit + spine + real | spend fold (D1–D3), persistence engine (F-16), single-writer (F-19), atomicity (F-18) → H3.5 |
| record registry + manifest schema identity | `D` §6.4 + `core` | `core/registry.py` | unit + the R3 schema break | key⇔record identity + relational checks (D4 = F-07/F-08) → H3.5 |
| work protocol (providers, descriptors, declines, leases) | `core`, `solve/PROVIDERS.md` §8 | `core/work.py`, `core/view.py`, `solve/view.py` | unit only, and narrower than this row once claimed — `tests/engine/test_provider_protocol.py` pins M2 re-offerable declines, M3 provider-minted subjects and M5 lease residency over a fixture provider; `tests/core/test_work.py` pins the `ExpansionRequest.mint` seam. NO in-tree check verifies the `Provider` protocol itself: the conformance battery (`measure/_provider_kit.py`, applied by `test_provider_contracts.py`) was deleted with the measure cleanup, and `core/work.py`'s own docstring records the claim as unheld ("no in-tree `isinstance(..., Provider)` check remains") | bind/execute split (F-02); leases have no admission control (M5) → H3.5/H4 |
| trace + replay (free run ⇒ byte-identical envelope) | `D` §6.5 | `core/trace.py`, orchestrator replay mode | unit + M-3.1 | durable trace cursor (F-24 = D5a) → H3.5 |
| concurrency (thread pool, deterministic reduction) | `engine`, `D` §6.3 | `engine/orchestrator.py` | M-3.3 + spine at 1/2/4/8/12 | fairness, cancellation, incremental reduction (F-22) → H3.5 |
| recipe policy as typed data | `engine` | `engine/recipe.py` (`RECIPE_V1`; the `RECIPE_V0_PHASED` measurement arm lived in the H3 bench, retired with the toys at H4 W1b — M-3.5 stands as history) | M-3.5 | prices carry no live knobs until there is a cold route to price |
| deciders (eligibility / desirability split) | `D` §7 | — | — | post-refactor; H3.5 rules the shape |
| block-level DONE (zero-close-value parking) | `D` §7 | — | — | with the deciders |
| observer surface (status, panes, artifacts, always-on) | `diag`, `D` §6.6 | `diag/status.py`, `diag/panes/` | unit + e2e + user-watched real runs | live progress publication (F-22.3 = D5b) → H3.5; the dead `declined_done_gate` pane key (DG-1) CLOSED by WP-5/1 |
| no-silent-stages contract | `D` §6.6 | `core/work.py` (`MAX_WORK_UNITS`, `check_progress`) | unit | tripwire on the slow fixtures for word/cold → H4, sampling/decode → H5 |
| CLI surface (`--scan/--dpi`, `--workers`, `--state-dir`, `--output`, `--complete`, `--no-close`, `--diag-port`, `--format/--pages`) | `WORKPLAN` H0/H3bis; `--no-close` user ruling 2026-08-22 (OR-13); `--format` user ruling 2026-08-22 (RULINGS G6) | `cli.py` | ARGUMENTS pinned (`holo2/tests/test_cli_surface.py`); exit codes 0/2/3/4 pinned there too; the close-policy axis pinned as an outcome table (`holo2/tests/engine/test_close_policy.py`); and since C5 the flag reaches a PAYLOAD — one argv, a format id, exit 0, byte-exact (`holo2/measure/verdicts/test_operator_path.py`), which the stubbed-decode pins cannot say | `--format ID` replaced `--coding/--tiles-y/--tiles-x` at C5: one identity (v2 id or `L:<id>`), no geometry/printer/paper argument, optional on a resume (the state names its own sheet, `Store.peek_identity`) and refused BY NAME when it disagrees. snapshot cadence OR-6 RULED 512 (2026-08-12, W-B/B11; `core/store.py DEFAULT_SNAPSHOT_EVERY`); output race F-25 (S2) CLOSED by WP-5/15 |
| CLI launcher (`./confetti2.py`) | `WORKPLAN` H0 | `confetti2.py` | UNTESTED — no test executes the launcher | mode + shebang fixed by WP-5/2 (was mode 644 with `#!/usr/bin/env python3`, an interpreter with no scipy); a launcher test needs a subprocess and the repo venv |
| incremental capture attachment / resume with new captures only | `capture` | `attachment_key` + decline-with-wake | unit | catalogue/interpretation split (F-05 = D5c, `capture` + `solve`) → H3.5 |
| health sentinels (cost, memory, yield, coverage) | `MEASUREMENTS` §HEALTH | wall + RSS pins | pinned | bench comparison mode, coverage reporting |
| discovery (multi-row) | `D` §11 out of scope | — | — | not scheduled |
| generation, characterize, printing | out of scope — `src/holo` owns them | — | — | never |

## Two standing honesty notes

1. **"Verified" is per capability, not per receiver.** The real-sheet
   gate verifies the composed path on ONE sheet with H3bis-grade
   placement and detection. It does not verify the production placement
   routes, the calibration scope framework or any colour coding. The
   colour row moved from "does not exist" to "names and builds, never
   decodes" at C2 (2026-08-22); the distance between those two is the
   whole colour port, and no number here has been measured against a
   colour sheet by holo2.
2. **A row that is implemented and unverified is a row to distrust.**
   Where the table says `unit`, the evidence is that the module does
   what its author believed; it is not evidence about paper.
