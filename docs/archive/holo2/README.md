# holo2's documents of record

holo2, retired 2026-09-05, was the dataflow receiver rewrite that lived in
`holo2/`: one commit wall with optimistic transactions, journal-authoritative
state with dispatch markers, and the pull model for placement (H4 through W2
merged 2026-08-16, the catch-up wave 2026-08-22). It never decoded colour.
holo3 superseded it.

These 31 files (22,899 lines) were moved here by `git mv` at **39df5cf**;
nothing in them was edited, so every blob is byte-identical to its
pre-move blob and `git log --follow <file>` reaches its whole history.
The tree itself was deleted at **a805888** — `holo2/`, `tests/holo2_oracles/`,
`confetti2.py`, the holo2 legs of the angle-residue instruments and the
freeze script, plus holo2's rows in `pyproject.toml` and `conftest.py`.

Any holo2 file that is not in this directory is reachable only from history:
`git show 06a8129:holo2/<path>` (06a8129 = 39df5cf^, the last tree with holo2
intact). Paths written `holo2/...` inside these documents name the tree as it
stood then, not anything that exists now.

Two pointers outside this directory:

- `holo3/retirement_docs-2026-09/HOLO2-MAP.md` — the mechanism-by-mechanism
  map, one row per holo2 mechanism that changes what a decode does, with its
  holo3 counterpart, a reader/refuter/second-lens verdict, and a ruling.
- `holo3/retirement_docs-2026-09/DELETION-LOG.md` §"Phase 3" — the record of
  the archive and the deletion, with the file counts and the gate outputs.

## The files

### Designs

| file | was | what it holds |
|---|---|---|
| `DESIGN.md` | `holo2/docs/DESIGN.md` | the constitution, v0.2 — laws L1–L15 and the glossary; draft, never adopted |
| `pkg-core-DESIGN.md` | `holo2/src/holo2/core/DESIGN.md` | facts, storage, commit, identity, the work protocol — the algorithm-free machine |
| `pkg-capture-DESIGN.md` | `holo2/src/holo2/capture/DESIGN.md` | rasters, footings, survey: opening an acquisition and writing the facts that follow |
| `pkg-format-DESIGN.md` | `holo2/src/holo2/format/DESIGN.md` | printed-format v1 truth — addressing, coding, close |
| `pkg-solve-DESIGN.md` | `holo2/src/holo2/solve/DESIGN.md` | placement, calibration, certification, tile-map projection, the providers |
| `pkg-engine-DESIGN.md` | `holo2/src/holo2/engine/DESIGN.md` | session lineage, recipe, orchestrator — protocols, gates, routes and prices |
| `pkg-diag-DESIGN.md` | `holo2/src/holo2/diag/DESIGN.md` | the observer: status service, panes, published artifacts |
| `PROVIDERS.md` | `holo2/src/holo2/solve/PROVIDERS.md` | the solve-side provider census, written before the work protocol was frozen |
| `ENGINEERING.md` | `holo2/docs/ENGINEERING.md` | how work landed in holo2 — the durable working rules, not the design |
| `CAPABILITIES.md` | `holo2/docs/CAPABILITIES.md` | one coarse row per capability: designed / implemented / verified / deferred |

### Measurements

| file | was | what it holds |
|---|---|---|
| `MEASUREMENTS.md` | `holo2/docs/MEASUREMENTS.md` | the recorded numbers: the H3 orchestrator bench, the H3bis real-capture gate record, the standing health ledger |
| `measurements-h3.json` | `holo2/docs/measurements-h3.json` | the H3 bench's machine-readable corpus and results |
| `measure-README.md` | `holo2/measure/README.md` | the measurement drivers — the verdicts gate, four equivalence harnesses, the done-gate and parity instruments |
| `H4-measurements/README.md` | `holo2/measure/H4-measurements/README.md` | provenance for the H4 benchmark drivers and outputs, preserved when the 312 GB demo scratch was trashed |
| `H4-measurements/reports/holo2-measure-w1exit-REPORT.md` | same, `holo2/measure/...` | the W1-exit measurement chain on the real sheet |
| `H4-measurements/reports/holo2-measure-w2exit-REPORT.md` | same | the W2-exit battery — the pull model's wall, commits and context switches |
| `H4-measurements/reports/holo2-cards-measure-REPORT.md` | same | the post-parallelism-cards re-measure plus the commit-path profile |
| `H4-measurements/reports/holo2-gil-diagnosis-REPORT.md` | same | why the worker pool bought no wall time: per-kernel GIL-free fractions |

### K-parity

| file | was | what it holds |
|---|---|---|
| `kparity/K-PARITY-STATE.md` | `holo2/docs/kparity/K-PARITY-STATE.md` | the campaign's state at the stop (2026-08-28) — what is in main, what stayed on the branch, what was discarded |
| `kparity/DIVERGENCE-LEDGER.md` | same | the 59-row "we implement v1" audit, each row with measured impact and a package assignment F1–F10 |
| `kparity/K-PARITY-CATALOG-draft.md` | same | the Wave-1 mechanism book: 101 K-path mechanisms with both trees' file:line. Draft, lead-skimmed only |
| `kparity/RULINGS.md` | same | the binding rulings §A–§N.1 for the catch-up and K-parity campaigns |
| `kparity/wave1-instruments.patch` | same | the four finished Wave-1 instrument commits, parked as a patch rather than merged |

### Plans and records

| file | was | what it holds |
|---|---|---|
| `WORKPLAN.md` | `holo2/docs/WORKPLAN.md` | build order, gates and the F-01…F-24 hardening rows with their dispositions |
| `H4-PLAN.md` | `holo2/docs/H4-PLAN.md` | the real-placement campaign, rulings R1–R10 |
| `H4-W2-PLAN.md` | `holo2/docs/H4-W2-PLAN.md` | the hints wave, redesigned mid-flight into the pull model, with its exit measurements |
| `H4-LANES-PLAN.md` | `holo2/docs/H4-LANES-PLAN.md` | the multi-resolution ladder's return, and the two rulings that came with it |
| `H5-PLAN.md` | `holo2/docs/H5-PLAN.md` | real payload plus calibration scopes, under the standing "algorithmically, v1 parity" law |
| `CATCHUP-PLAN.md` | `holo2/docs/CATCHUP-PLAN.md` | the wave that brought holo2 to FORMAT-SPACE parity, `--no-close` and the pyflakes gate |
| `CATCHUP-SUMMARY.md` | `holo2/docs/CATCHUP-SUMMARY.md` | the same wave in two pages, for a reader who forgot everything |
| `STEP-BACK-ROUND.md` | `holo2/docs/STEP-BACK-ROUND.md` | the proposed-never-scheduled isolation pass, with its scheduling-tax census |

## The yield digest

The numbers holo2 measured that nothing outside it recorded. Each is quoted
from the archived copy at the line given.

**The re-read (RF1).** With the ownership freeze and the re-read both in,
re-sampling a superseded pose through the live pose bought **+27 certificates
on e029** (1,911 → 1,938) and **+32 on xerox** (1,882 → 1,914) against the same
refine-off baselines — at **+112% wall on e029** (1,127 → 2,385 s) and
**+386% on xerox** (719 → 3,494 s), single runs each
(`MEASUREMENTS.md:1129-1130`; `WORKPLAN.md:578-580`, which adds that whether
that price is acceptable is a user ruling).

**The done gate.** v1's 48.6% pixel-gated share is the census PREDICTION
(`measure-README.md:430`) and "a SIMULATED counterfactual, not a realized
rate" (`:435`). holo2's realized rate on two fresh `--complete` states is
**45/1,273 (3.5%) on e029 and 42/1,324 (3.2%) on xerox** (`measure-README.md:477`),
recorded there as a lower bound. The two are not a ratio — different receivers,
different denominators.

**The preempted close.** holo2 recovered **465,580 bytes with 1,359
certificates**, byte-identical to v1's recovery of the same volume, which v1
needed **1,930** for (`MEASUREMENTS.md:602`). The file states the thesis at
`:617-619`: v1 ran twelve levels plus mop-up and refinement tails to full
harvest; holo2 stopped the moment the fountain could solve.

**Ownership.** Replacing holo2's contested-cell ranking — `pose_id` order, a
fixed geometric preference — with v1's context-corrected held-out log-loss
tie-broken on pose id rescued **26–29/30 e029 and 27/48 xerox tiles, with zero
regressions in 1,910 + 1,882** (`kparity/DIVERGENCE-LEDGER.md:65`). The controls
make it causal: reversed order scores 4/30 and regresses 64, a hash coin 20/30,
and holo2's own pose-id order **0/30 — worse than random**. The correction has
to be applied at window scope; holo2 applied it at decode assembly, with bins
"from the assembled 64×64 component's own observed mask" (`:66`), which put
6.15% of cells in the unusable bin against 1.56–2.11% window-scoped.

**The ranked K gaps**, `kparity/DIVERGENCE-LEDGER.md` §3, in the ledger's own
order:

| # | package | state |
|---|---|---|
| F1 | the freeze (rows 1, 2, 20, 21, 25, 40, 42) | landed — ownership key plus window-scoped context (`:172`; `kparity/K-PARITY-STATE.md:32-35`) |
| F2 | the re-read (`:202`) | **F2a** — re-samples a superseded pose's residue through the live pose — landed; **F2b**, same-capture cross-rung pooling, is labelled new work and "REFUSED, not owed" (`CATCHUP-PLAN.md:576`; the two that landed are F1 and F2a, `:573`) |
| F3 | RF1's gate and its inputs (rows 5, 12, 54) | not built; depends on F1's per-(pose, pool) field (`:241`) |
| F4 | placement admission parity (rows 8, 17, 18, 23, 24) | not built — the rival bar, lattice quantisation, seed rule, straddle re-arm (`:252`) |
| F5 | the label channel and the refused fit (rows 9, 10, 44) | not built; covered windows retire unposed and contribute no labels (`:266`) |
| F6 | scheduling completeness (rows 15, 16, 38) | not built — the exhaustion round, loser-hypothesis seed, wide-tier counters (`:280`) |
| F7 | the per-rung window lattice phase (row 6) | gated: a fresh-state change, two measurements owed first (`:292`) |
| F8 | the word-pool firewall (rows 19, 22) | gated on a pooled-vs-per-pose rerun; measured inert, **0 conflicts in 21,079 / 21,508 evidence records** (`:83`, `:314`) |
| F9 | provenance, audit, operator surface (rows 26, 27, 28, 31, 32) | no yield; not built (`:317`) |
| F10 | pins only (rows 37–39, 41, 43, 45–56, watch rows 29, 30) | oracle and differential pins, no behaviour change (`:327`) |

## The doc-vs-code contradictions the map recorded

Five, from `holo3/retirement_docs-2026-09/HOLO2-MAP.md` — three of them in
holo3's own documentation, two in holo2's:

- **placement-26** (`:1205`) — holo3's own spec "still SAYS the tiers should be
  gated; the gate was deleted at d399ba3."
- **evidence-ownership-13** (`:2002`) — holo2's `DESIGN.md:670-676` says
  "scale_space's memmap arm has no production caller to flip" and "derived
  footings hold no pixels in this tree", but `capture/ingest.py:302` called, on every ingest given a directory (`:301`, `if directory is not None`),
  `derive_footing_rasters` on every ingest, writing into a `w+` memmap.
- **dryness-01** (`:4296`) — holo2's `DESIGN.md:265` "still calls cold 'gated on
  quiescence', which is wrong twice over" — the quiescent gate was deleted and
  replaced by the dryness gate.
- **refinement-15** (`:2945`) — holo3's `API.md:415-416` "still describes
  place.done_covers as 'the in-job done-gate consult over the projection the
  engine hands in via WindowPass.done_cells'", a field `WindowPass` does not
  have; separately `tiles.done_covers` has no production caller at all.
- **pricing-02** (`:4624`) — `13-engine-diag-cli.md:118` "still declares
  COLD_LIVE 140 / COLD_REST 150 ... 'verbatim'; the tree has 250/260 and no
  rework term."

## The test-basename rule, superseded

holo2 carried a repo-wide guard that no two test modules under `testpaths`
share a basename. Its reason, in its own words: pytest's prepend import mode —
"which holo2's own suite needs, since it imports `conftest` and `_srctree` as
siblings" — puts each test file's directory on `sys.path` and imports by
basename alone, "so one shared name anywhere under `testpaths` aborts the WHOLE
repo's collection", and only a full-repo run ever sees it
(`git show 06a8129:holo2/tests/test_conventions.py:279-290`). holo3 owns the
rule now, widened to import names across every collected root:
`holo3/tests/test_h3_conventions.py:134`,
`test_pytest_import_names_are_unique_across_every_collected_root`.

## Three sentences from files that went to history

Not archived, quoted here because nothing else carries them.

- The journal snapshot cadence, a mechanism holo3 does not have —
  "**RULED 2026-08-12: 512 + fsync** — ≈ once a minute at measured real-sheet
  commit rates (10/s), clock-free" (`06a8129:holo2/docs/HARDENING-WORKLIST.md:960-961`).
- Germano's architecture ruling of 2026-08-10 — "each subsystem is a
  quasi-independent library in one repo — reviewable alone, replaceable alone,
  with LOCAL design authority (its own DESIGN.md in-folder)"
  (`06a8129:holo2/docs/REFACTOR-WORKPLAN.md:17-19`).
- The F-16 figure that made whole-envelope persistence a blocker: "an 8.05 MB
  envelope and roughly 2,119 commits; 98.1% of wall in per-commit snapshots;
  per-commit snapshotting 57x slower than close-only"
  (`06a8129:holo2/docs/H3BIS-ARCHITECTURE-REVIEW.md:394-396`). That is the
  small-scale version of the real-sheet measurement in `WORKPLAN.md:299`, which
  is archived here: at 3,408 commits, 6,105 records and 2,251 spend rows, the
  journal came to 217.3 KB and the cache to 20.1 MB against the envelope's
  475.9 MB.

## Runtime footnote

Not a yield number. holo2 measured its worker pool's **thread Amdahl ceiling at
≈ 1.01× — "the pool is AT its ceiling"** (`MEASUREMENTS.md:2162`), because every
hot kernel but `ldpc.decode_soft` held the GIL for its whole run. That is the
diagnosis holo3 answered by moving to free-threaded CPython, where the
acceptance bar is **≥ 3× wall-clock speedup at `--workers 8` against
`--workers 1` on one real sheet with identical payload bytes**
(`holo3/conversion_docs/00-plan.md:93-94`; `holo3/API.md:832-834`, which notes
the workers-8 certificate set is race-dependent so only the payload is
compared). That is the bar, not an achieved multiple: no byte-identical
free-threaded decode or wall is pinned anywhere
(`holo3/retirement_docs-2026-09/ARTEFACTS.md:841`).

## Where the src/holo-vs-holo2 divergence record lives now

`tests/holo2_oracles/` is gone with the tree, so the surviving statement of
what the two generations deliberately disagreed about is
`docs/CMY8-COLUMN-GROUPS.md`. §6 (`:344-353`) records that the v1 receiver gets
no message of its own for an uneven cmy8 triplet — it fails on
`common_user_bits`, "stream user widths differ" — that holo2's own refusal
stays, that `test_oracle_lattice.py` moved the triplet from the shared refusals
to `INTENDED_DIVERGENCES`, and that `test_oracle_close.py` declares the fountain
and streamset carries `ORIGIN_MOVED`. The same thing is ruling 7 in §9
(`:473-478`): scope is src/holo generation plus the holo3 receiver, the v1
receiver and holo2 untouched, no refusal message either. §8's qualification
checklist names the oracle's `INTENDED_DIVERGENCES` among the pins
(`:440`).
