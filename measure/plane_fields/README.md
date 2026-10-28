# measure/plane_fields — the PLANE-FIELDS measurement instruments

**Nothing here is a test and nothing here runs under `pytest`.**
`measure/` is outside `testpaths`; these entry points open multi-GB
archived states, take minutes to hours, and read physical scans.

User ruling, 2026-08-21: *measurement-instrument code must not live in
`tests/` or `scratch/`.* This package is that home, on the
`holo2/measure/` precedent. It was `tests/holo/_plane_fields_harness/`
(the leading underscore existed only to dodge pytest collection) plus two
figure scripts that had been left in `scratch/plane-fields/gt-affine/`.

Line doc: `docs/PLANE-FIELDS.md` (v0.10+, governing). Nothing here is
imported by `src/holo` — every module is a READ-ONLY consumer of the
production receiver seams, in the `_color_uplift_harness` mould. None of
them writes a state or a scan, and none calls `save_session`; the one
exception by design is `qualify_sheet_i`, which *creates its own* fresh
state under `scratch/plane-fields/qual/` and never touches an archived
one.

## How to run anything here

`measure` goes on the path, `plane_fields` is the package, and every
module imports its siblings **relatively** — so `-m plane_fields.<entry>`
is the only supported invocation (a by-path run cannot resolve the
relative imports):

```
cd <repo>          # or a plane-fields worktree
PYTHONPATH=src:measure env/bin/python -m plane_fields.<entry> [flags]
```

`src` is on the path because neither `holo` nor `paperholo` is
pip-installed (CLAUDE.md env honesty). `render_panels` is the one entry
that needs no `src` (pure PIL/numpy).

## The instruments

### `field_from_certs` — W0/V0, the blind per-plane field

Builds the per-plane translation-delta field for a colour receive state
from **certificates + committed poses + the archived scan alone** — no
page GT sidecar, no fitted global affine, no receiver code changed — and
scores it against the supervised `regmap-gt` sinusoid (e033 §033.4). The
pre-registered V0 gate is Spearman ≥ 0.7 on `dY_rel_x` per tile column,
period within ±20%, amplitude within a factor 2. **V0 PASSED at +0.997.**

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.field_from_certs \
    [--capture {1,2,3}] [--workers 8] [--limit N] \
    [--bandwidth-tiles 2.0] [--tag I] [--figures-only]
```

Inputs (all read-only): the ARCHIVED sheet-I state
`scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/receive.state`, the
three 2400 dpi Canon TIFFs `scratch/xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi{,-displaced,-displaced2}.tiff`
(sha-checked against `scratch/xerox-v1-20260818/scan-shas.txt`), and
`scratch/xerox-v1-20260818/regmap-gt/per-column.json`.
Outputs: `scratch/plane-fields/field-from-certs-<tag>.json`,
`plane-fields-<tag>.png`, `comparison-<tag>.png`. Committed facts of the
archived state are cached under `scratch/plane-fields/cache/`.

### `qualify_sheet_i` — W6/V4, sheet I decoded fresh with the dial ON

Drives a FULL fresh decode of sheet I with the plane-fields dial on and
scores it against the pre-registered bar (PRIMARY: median Y residue over
the twelve dead-band columns ≤ 5/53; measured 24/53 = **FAILED**, with
+252 certificates and a BYTE-EXACT close — see §6.4). Declares
`run_refine=True` deliberately, because the e033 §033.3 baseline it is
scored against did (`--refine` is required for any field activity at
all).

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.qualify_sheet_i \
    [--dial {on,off}] [--workers N] [--captures 3] [--out-dir DIR]
```

Inputs: the three sha-pinned 2400 dpi captures (the receiver verifies
each `expected_sha256` itself); format `L:c2-cmy8-r0700-p120-x1@3392x2368`;
the dial-off baseline comes from the cached `StateFacts` and from
experiments/033 §033.4, never from re-opening the archived state.
Outputs, all under `scratch/plane-fields/qual/`: `receive.state` (the W6
state every later instrument reads), `events.jsonl`, `qual-<dial>.json`,
`residue-comparison-<dial>.png`.

### `swim_pilot` — §6.5.5a SWIM CHARTER feasibility pilot

For ~10 uncertified `(tile, stream)` slots it produces three independent
per-plane offset estimates — neighbour-interpolated (the W4 tier-i
probe), the swept SWIM offset, and own-furniture NCC — and a decode
verdict for each. Acceptance is the ORDINARY certificate gate, never a
score.

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.swim_pilot \
    [--tiles 10] [--clear-band-targets N] [--reproduction-controls N] \
    [--fit-radius R] [--grid-max/--grid-step ...] [--no-grid2d] \
    [--spot-checks N] [--lane ID] [--seed S] [--rebuild-cache] [--tag v1]
```

Inputs: the W6 state `scratch/plane-fields/qual/receive.state`, the same
three sha-verified captures, the regmap-gt sidecar. The live
`scratch/xerox-v1-20260818/I-multi-pf` state directory is refused by
construction (`_swim_inputs.refuse_forbidden`) — a second receiver may be
writing there. Outputs: `scratch/plane-fields/swim-pilot/swim-pilot-<tag>.json`
plus `offsets-<tag>.png` / `cliff-<tag>.png`; the state's committed facts
cache to `scratch/plane-fields/swim-pilot/cache/`. The cache can be
rebuilt on its own with `-m plane_fields._swim_inputs`.

### `gt_affine` — the SUPERVISED AFFINE CEILING

Sheet I closed VERIFIED, so the exact printed cells are known. This fits
the best possible per-plane sampling affine (6 dof per tile/plane/capture)
against that truth and reports what error survives — the ceiling of any
registration-based correction, which splits the swim's ~10% floor between
unmodelled geometry, photometry and irreducible noise.

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.gt_affine \
    [--tiles N] [--reference-tiles N] [--coarse-max/--coarse-step ...] \
    [--polish-radius/--polish-step ...] [--permutations N] \
    [--fit-radius R] [--lane ID] [--seed S] [--tag v1]
```

Inputs: the W6 state, the three captures, and the swim's own
`scratch/plane-fields/swim-pilot/swim-pilot-final.json`.
Output: `scratch/plane-fields/gt-affine/gt-affine-<tag>.json`.

### `detector_residue` — P2: recut bins, direction, per-state contrast

The three measurements docs/INDEPENDENT-PLANES §6 P2 asks for, in ONE
pass over the three captures (placing the committed poses and fitting the
restricted region is the expensive part and is shared):

* **E1 RECUT-BINS REFIT** — each of the six dead-band tiles and two
  reproduction controls decoded at its `gt-affine-final2.json` 6-dof
  affine plus BER polish, twice: through the FROZEN detector (`gt_affine`'s
  own arm) and through a FULL REFIT of the restricted region with that
  tile sampled at the correction. Settles how much of the dead-vs-control
  detector gap was frozen-fit artifact.
* **E2 DIRECTIONAL-NEIGHBOUR STRATIFICATION** — pure re-analysis at the
  fitted geometry: Y cells split by whether the neighbour in the
  direction of the fitted Y translation carries C/M ink, with the
  UPSTREAM neighbour as the falsifier and the SAME cell as reference.
* **E3 PER-STATE Y CONTRAST** — Y ink/white separation conditional on the
  same cell's (C, M) state, on dead tiles and certified clean-column
  reference tiles (the mix-compression question).

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.detector_residue \
    [--fit-radius R] [--workers N] [--no-refit] [--limit N] [--captures N]
```

Inputs: the W6 state, the three sha-verified captures, and
`scratch/plane-fields/gt-affine/gt-affine-final2.json` (the geometries
under test — its state sha and lane are asserted against this run's).
Outputs under `scratch/plane-fields/p2/`: `e1-refit.json`,
`e2-directional.json`, `e3-state-contrast.json`, `e1-refit.png`,
`e2-directional.png`. `REPORT.md` and both figures are then regenerated
from those JSONs by `-m plane_fields._residue_report` — every number in
the report is read out of the artifacts at render time, never
transcribed. ONE capture's raster is resident at a time (`gt_affine`
held all three and peaked at 16.6 GB; this peaks near 10).

### `state_context` — P2b: E3' per-state, E4 the Y-context circularity

The two cheap discriminators docs/INDEPENDENT-PLANES §6 P2b asks for, in
ONE pass, at **E1's REFIT footing** (the restricted region re-fitted with
each target tile sampled at its `gt-affine-final2.json` 6-dof affine plus
BER polish, so registration, QDA/PAVA and the A5 bins all see the
corrected geometry):

* **E3' PER-STATE PRODUCTION vs ORACLE** — per eight-state class: the
  QDA's TRAINING count `n_k`, the covariance shrinkage
  `a_k = min(1, (D+2)/n_k)` it implies, the state's Y moments, the PAVA
  calibration and held-out validation populations, and — on the six dead
  tiles, the two reproduction controls and the certified clean-column
  references — the production head's Y error CONDITIONAL on the GT state
  of the same cell against a per-(C, M)-stratum ORACLE threshold on the
  same samples. Plus A3's per-window verdict split dead vs clean (A3 is
  override-only in production, so that table is what the `u-a3`
  supplemental lane WOULD find — a diagnostic, never a report of the
  archived decode).
* **E4 THE Y-CONTEXT CIRCULARITY TEST** — A5's ink map rebuilt with
  ground-truth columns: (a) baseline, (b) Y = GT, (c) C,M = GT (the
  METHOD CONTROL — both are certified on these tiles, so it must move
  almost nothing), (d) all three. Two arms each: swap the bins only, and
  swap the bins and refit the curve on them.

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.state_context \
    [--fit-radius R] [--workers N] [--limit N] [--captures N] [--from-raw]
```

Outputs under `scratch/plane-fields/p2/e3e4/`: `raw.json` (written before
any reduction runs — the P2 rule), `e3prime.json`, `e4.json`,
`tables.txt`, `e4-ber.png`, `e4-ber-head.png`. ONE capture's raster is
resident at a time.

Four gates the run asserts rather than assumes: the instrument's rebuild
of A5's bins at configuration (a) must be **bit-identical** to the ones
the ladder itself produced (a `RuntimeError` otherwise); every KNOWN
cell's exact bits must equal the printed truth; a configuration must
leave every column it did not override bit-identical; and configuration
(a) must reproduce E1's refit arm out of `p2/e1-refit.json`.

### `pose_writer` — P5: what a POSE WRITER would yield, in certificates

docs/COMPOSITE-POSE-DESIGN.md §6 splits every probe measurement two ways:
the PER-PLANE part feeds the printer field, the PLANE-COMMON part feeds
the window POSE. Only the first half has a consumer. This instrument
measures what building the second half would buy, on the W6 sheet-I
state, in the only currency the receiver has — CERTIFICATES — over EVERY
open `(tile, stream)` slot (334: Y 332, C 2), union over the three
2400 dpi captures, accepted by the ordinary gate.

Six sampling configurations, all through the one production seam
(`offsets_override`), so the baseline carries the same float32 rounding
the corrected arms do:

| | configuration | plane-common sampling | per-plane sampling |
| --- | --- | --- | --- |
| (i) | `committed` | the arm's own zero | the arm's own zero |
| (ii) | `field` | the field's | the field's |
| (iii) | `field+pose-t` | field + window translation | the field's |
| (iv) | `field+pose-affine` | field + window local affine | the field's |
| (v) | `field-diff` | the arm's own zero | the field's, differential |
| (vi) | `field-diff+pose-t` | window translation | the field's, differential |

(v) and (vi) exist because the shipped field is fed each plane's FULL
local offset and its prediction therefore already carries a page-smoothed
plane-common component; they are declared in the run's own bar file
BEFORE the measurement and are reported apart from the pre-registered
clause. The **BOTH FOOTINGS** rule: every configuration is scored through
the frozen detector AND through an E1 REFIT of the whole region at the
corrected geometry (registration, QDA/PAVA and the A5 bins all recut).

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.pose_writer \
    [--captures 1,2,3] [--limit-slots N] [--lane ID] \
    [--affine-prior-edge-dots 0.25] [--min-affine-sites 6] \
    [--no-refit] [--no-verify-sign] [--no-ber] [--workers N] [--tag v1]
```

Four things the run asserts rather than assumes. The instrumented probe
collector must reproduce the production pass EXACTLY (same windows, same
site counts, same per-window medians to 0.0 dot) or the run stops. No
configuration may be a silent no-op (`override_divergence`, pure
arithmetic on the override arrays). The SIGN CHECK re-runs the whole
probe pass with every window's pose translated by its own estimate: the
plane-common residual must collapse. And the null proof of the seam runs
per capture, on whichever arm the stack selected.

Outputs under `scratch/plane-fields/p2/pose-writer/`: `<tag>-bar.json`
(written before the first measurement — the pre-registration),
`<tag>.json`, `<tag>.png`. Inputs: the W6 state, the three sha-verified
captures, `recovered.bin` for the per-slot ground-truth cell BER. ONE
capture's raster is resident at a time.

### `_selfcheck` — the refit seam's synthetic checks

No state, no scan, no pixels: a made-up crop, pose and point set, and the
five assertions the 2026-08-22 review's two defects would have failed
(the A0 arm is untouched without an override; a zero override is the
identity; a per-plane constant delta and a per-cell affine both reach the
A0 arm and move only their own plane; a no-op refit RAISES).

```
PYTHONPATH=src:measure env/bin/python -m plane_fields._selfcheck
```

### `extract_panels` → `render_panels` — the dead-vs-GT figure pipeline

Two stages over ONE `gt_affine` result file. Stage 1 re-derives the same
targets on the same seed and the same restricted-region fit as
`_gt_affine_run.run`, so its numbers are the ones already in the result
JSON; stage 2 is pure PIL/numpy and touches neither state nor scan.

```
PYTHONPATH=src:measure env/bin/python -m plane_fields.extract_panels
PYTHONPATH=measure     env/bin/python -m plane_fields.render_panels
```

Stage 1 reads `scratch/plane-fields/gt-affine/gt-affine-final2.json` (the
filename is a module constant, `RESULTS`) and writes `panels.npz` +
`panels.json` beside it; stage 2 turns those into `dead-vs-gt.png`,
`dead-vs-gt-c-plane.png`, `dead-vs-gt-zoom.png` and one
`tile-<yy>-<xx>-<plane>.png` per panel tile.

## Module map

| module | role |
| --- | --- |
| `_inputs` | sha-validated read-only access to the ARCHIVED sheet-I state/scans; `StateFacts` cache; `tree_state`/`tree_moved` |
| `_probe` | the W4 tier-i NCC probe (re-encode a certificate, lock it against the scan) |
| `_figures` | W0 field/comparison figures |
| `_swim_inputs` | the same for the W6 QUAL state (`QualFacts`), plus `refuse_forbidden` and the plan-prefix tripwire |
| `_swim_setup` | target/control selection, lane choice, committed geometry, region rasters |
| `_swim_probes` | the two NCC estimators (neighbour-derived, own-furniture) |
| `_swim_region` | the per-candidate decode driver (`fit_region`, `override_offsets`, `base_features`, the refit seam + its tripwire) |
| `_swim_truth` | ground truth re-derived from the closed volume |
| `_swim_figures` | swim figures |
| `_affine_fit` | `TileSampler`, the affine fit and its statistics |
| `_gt_affine_run` | the `gt_affine` driver body (kept out of the CLI module) |
| `_residue_strata` | E2/E3 stratification (pure statistics, no pixels) |
| `_residue_run` | the `detector_residue` driver body |
| `_residue_figures` | the E1/E2 figures |
| `_residue_report` | `p2/REPORT.md` + both figures, regenerated from the result JSONs (`-m plane_fields._residue_report`) |
| `_state_tables` | E3' leaves: the per-state QDA/calibration/validation table, the per-stratum oracle, A3's per-window verdict by band |
| `_context_gt` | E4 leaves: A5's ink map rebuilt with GT columns, its null proof, the bin-change and ink-disagreement statistics, the context-head refit |
| `_state_context_run` | the `state_context` driver body |
| `_pose_probe` | the plane-COMMON half of the probe pass: per-site LOCAL offsets, the per-window translation and ridge-shrunk local affine, and the cross-check against `WindowPoseResidual` |
| `_pose_apply` | the six configurations at the `offsets_override` seam, the refit builder, the no-op tripwire, the field-vs-pose plane-common comparison, the union verdict and per-slot BER |
| `_pose_figures` | the P5 figure (residual, yield, BER-vs-residual, BER by band) |
| `_state_context_report` | the E3'/E4 JSONs, tables and figures |
| `_selfcheck` | synthetic checks for the refit seam (no state, no scan) |

## Verification this code still gets

The pyflakes undefined-name gate
(`tests/holo/test_trust_boundaries.py::test_no_undefined_names_across_measure_instruments`)
sweeps every `measure/**/*.py`. That gate exists because of exactly this
lineage: a PLANE-FIELDS W2 split left a `channel` import behind and the
`NameError` only fired hours into a live decode. Nothing else here is
automatically checked — no unit tests, no collection.

## KNOWN CAVEATS (recorded 2026-08-21 review — limitations, not bugs)

These are the confirmed limitations of the instruments as they stand.
They bound what the recorded numbers may be used to claim.

**Caveats 1–4 were FIXED on 2026-08-22** as the prerequisites for the P2
measurements (docs/INDEPENDENT-PLANES §6 P2); they are kept here, struck
through, because every number recorded in `swim-pilot-final.json` and
`gt-affine-final*.json` was produced BEFORE the fix and still carries
them. `p2/e1-refit.json` is the first artifact that does not.

1. ~~**The refit spot-check ranks certified rows first**~~, so the
   frozen-detector approximation was only ever validated on the two
   clear-band controls. FIXED: `refit_spot_check` now ranks dead-band
   targets first — the population the approximation stresses. `gt_affine`
   still has no refit path; `detector_residue` (E1) is that path.
2. ~~**The refit is a no-op on captures whose stack selected the A0
   arm**~~ (two of sheet I's three). FIXED: `fit_region` applies the
   correction to BOTH arms, each about its own zero, and
   `RefitDidNotReach` is raised if the SELECTED arm's features still
   equal that arm's zero. `null_proof` likewise no longer short-circuits
   to `True` on A0 — it measures, against `crop_features`, to a float32
   bar (the A0 seam crosses a crop boundary; the A1 seam must be exact).
   Synthetic coverage: `_selfcheck`.
3. ~~**A5 context bins are cut at delta = 0 and reused at every candidate
   geometry**~~, so their staleness correlates with the dead-vs-control
   grouping. STILL TRUE of the swim's per-candidate sweep and of
   `gt_affine` (both are frozen-detector by design — a refit per
   candidate is hours). E1 measures what that approximation costs, per
   tile, at the one geometry that matters.
4. ~~**The withheld control certificate leaks into the own-furniture
   estimator**~~. FIXED: `run_targets` builds both the probe template
   index and the certified-neighbour index from `fit_certificates`, so a
   withheld control presents to its own probe — and to its neighbours —
   exactly as a residue tile does.
5. **`GATE_BER = 0.0767` is a hard-coded scalar derived from two control
   tiles, and the measured interval is inverted** — the best FAILED
   candidate sat at 0.0757, below the worst CERTIFIED one at 0.0767. It
   is reported, never used to accept anything. P2's E1 widened the
   inversion a third time: tile (29,8) certified at 7.85 % union cell
   error while (31,15) failed at 7.70 %. The certificate gate is not a
   BER threshold; treat the constant as a landmark, never a predicate.
6. **The affine ceiling optimizes partial NCC, not BER.** The reported
   ~9.7% is therefore an upper bound on what that model achieves, not the
   model's optimum under the decode criterion.
7. **Summary statistics pool tile × capture as if independent**, and the
   compared groups are outcome-selected (certified vs not). Treat the
   pooled figures as descriptive, not inferential. `detector_residue`
   carries `n_tiles` (physical) next to `n_rows` (tile × capture) in
   every pooled table, and E2/E3 additionally pool a cell once per WINDOW
   that carries it — a cell under four windows contributes four rows.
8. **Sampling/ownership/provenance**: `TileSampler` clamps out-of-crop
   samples where production refuses them; the swim override can reshuffle
   window ownership; and the state-cache provenance check is
   size-checked, not sha-checked.

One more, from the move itself: a `StateFacts`/`QualFacts` pickle written
before 2026-08-21 names the old `_plane_fields_harness…` module path
inside it and can no longer be unpickled. Both cache readers treat that
as a MISS and rebuild (a ~200 s state re-read), never as a crash.
