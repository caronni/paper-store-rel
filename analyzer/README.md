# analyzer — operator's manual

The analyzer is a standalone research instrument that attacks the residue
of a finished holo3 decode: every tile-stream the production receiver left
uncertified.  It re-reads those tiles' pixels with a wider battery of
unmixing, registration, calibration and decoding arms than production
carries, and mints a certificate only when a hard vector satisfies every
parity check of the tile's code and its CRC-32 — the same gate production
uses, so its certificates are production's certificates.  It changes
nothing under `src/holo/receiver/`, `src/` or `measure/`: holo3 code is called, and the
analyzer's harvest goes back to production through a snapshot a `--resume`
reads.

Design: `analyzer/DESIGN.md`.  Build record and dated changelog:
`analyzer/PLAN.md` (§6).  Measurement records: `GAPS-2026-09-03.md` (the C
parity gap), `FIELD2-2026-09-03.md` (the page field), `REVIEW-2026-09-03.md`,
`MEASUREMENTS-2026-09-06-C-THIRD-LAYER.md` (the three-ink state).  The W8
wave in one page — what was built, what it cost, what it did:
`W8-2026-09-06.md`; its working spec, run matrix and full trial record:
`APPROACHES-2026-09-06.md`.  The sheet-J confetti ladders in one page —
two batteries, +156 handed back, and what a capture was worth:
`J-CONFETTI-2026-09-10.md`.

---

## 1. Footing

Run everything from the repo root, as a module, with the root virtualenv —
free-threaded CPython 3.14 (`python3.14t`), threads and no processes,
because the snapshot is loaded once per process and shared:

```
env/bin/python -m analyzer --help
```

The venv is `env/`, the free-threaded 3.14.7 (CLAUDE.md, Venvs); a
machine that still carries `env314t/` is meant to migrate to a GIL-free
`env/`, and every command below is spelled for `env/`.

Nothing is installed — `analyzer/`, `src/holo/receiver/` and `measure/` import from the
repo root.  Tests:

```
env/bin/python -m pytest analyzer/tests -q -n 8
env/bin/python -m pyflakes analyzer
```

`python -m analyzer` NEEDS `PYTHONPATH=src:.` — `pyproject.toml`'s
`pythonpath` is a pytest setting and reaches nothing else; a bare
`env/bin/python -m analyzer --help` dies on `from holo.receiver
import data` (measured 2026-09-07, main tree).  The same prefix serves
the `measure/` scripts of §2.9.  Set it once per shell:
`export PYTHONPATH=src:.` — every chain script in
`<evidence>/analyzer/W8/logs/` does exactly that.

Artefacts land in `--out`, which every subcommand requires.
Every subcommand prints the numbers it measured; nothing important is
hidden in a file only.  Redirect a long run through `python -u` — with
stdout to a file, Python block-buffers it, so a `ladder` that has been
working for 40 minutes shows an EMPTY log until it exits and the header
line (`targets N arms …`) never arrives when you want it.  Progress goes
to **stderr**, so a log that should hold it needs `2>&1` before the
`| tee`.

**One analyzer at a time, and never beside a holo3 decode.**  A sheet-H
pass peaks near 50 GB of resident memory on a 64 GB machine.  Check `ps`
before launching.

---

## 2. The loop

```
   holo3 decode  ──►  run dir  ──►  mirror ──►  census ──► ladder ──► close
                                                              │          │
                                                              ▼          ▼
                                                        export-facts   payload.bin
                                                              │          │
                                     union-base ◄─────────────┤          │
                                          │                   │          │
                                          ▼                   ▼          ▼
                                   next ladder pass    holo3 --resume   score
```

Steps 2.1–2.3 are setup, 2.4–2.6 are the pass, 2.7–2.9 are what you do with
its harvest.

### 2.1 Mirror the run dir (only if its rasters are remote)

An analyzer pass reads a run dir's `<sha12>/l{NN}-{r,g,b}.npy` rasters
directly.  When those live on a network mount, rebuild them locally from
the capture TIFFs the source `argv` names — `intake.ingest_capture` is
called, so the rasters come out byte-identical to production's (measured on
sheet J: all nine rasters `np.array_equal` to production's):

```
env/bin/python -m analyzer mirror \
    --src-run-dir <evidence>/holo3-H7-run \
    --out build/analyzer/H7-mirror \
    --tiff-dir <evidence>
```

`argv`, `report.json`, `events.jsonl` and `facts.npz` are copied when
absent.  `report.json` is the checked-against truth (capture ids,
`levels_ppc`, `shape_yx`); a disagreement REFUSES.  Idempotent: a complete
capture directory is skipped without hashing.  Sequential by ruling, not by
limitation — one capture holds its whole native raster (sheet I's 4800 is
6.8 GB) and the memory budget forbids doubling that.

Cost: 18 s and 2.4 GB peak for sheet J's single 28064×20416×3 capture.

### 2.1a Converting an archived pre-W2 snapshot (the A0 recipe)

**A page-field receiver snapshot is read directly here.**  Since A1
(2026-09-12, `040f466c`) `inputs.py` keys `PlaneField` by `(page, plane)`
and nothing else, and the production `field` arms apply the published
delta unrotated — a page-axis vector through the receiver's own mapping.
Nothing has to be stripped to run a pass on a current run dir.

What still cannot be read is the other direction.  An ARCHIVED snapshot
written before the receiver's W2 re-key carries the ten-field per-lane
`PlaneField`, and `snapshot.read` refuses it with `TypeError:
PlaneField.__init__() got an unexpected keyword argument 'capture_id'`.
There is no version stamp either way (`snapshot.py` says so out loud), so
the refusal arrives as an exception rather than a verdict.

The conversion is two commands and no new instrument.  Germano's
tag-based filter (`util/strip_page_fields.py`, main `efc839e5`,
`DROP = {PlaneField, EvidenceRevision}`) removes the old facts without
importing either receiver version and streams the array blob through
untouched; `measure/page_field/convert.py` appends post-W2
`data.PlaneField` and `data.EvidenceRevision` facts, writes with
`snapshot.write`, reads back, and asserts `export_facts.fact_digests`
over every NON-field fact is IDENTICAL — which is the whole claim it
makes:

```
env/bin/python util/strip_page_fields.py \
    <evidence>/J-run.54028/facts.npz \
    -o build/J-run.54028.page-field/facts.stripped.npz

PYTHONPATH=src:. env/bin/python -m measure.page_field.convert append \
    --facts build/J-run.54028.page-field/facts.stripped.npz \
    --out build/J-run.54028.page-field/facts.npz \
    --format L:c2-cmy8-r0547@53x37 \
    --scan <evidence>/xerox-canon-1.9-J-c2-cmy8-r0547-confetti-2400-1a.tiff \
    --dpi 2400
```

`--fields-json` is the other source: a `measure/page_field` product
solved from this archive, and costing a file read instead of a solve.
Four gates bind it (review 2026-09-13, F5 — a count census is size, not
identity): the product's grid must equal the declared format's and the
page's `tiles_yx` with page and plane ids in range; every capture in its
`evidence_revision_by_capture` must be one the archive declares; its
`folded_facts` must be present, non-empty and equal to the snapshot's
Placement/Certificate census; and its `format_ref` must resolve to the
declared seed.  Either way the declared `--format` is checked against the
run's own journal before anything is opened — a format id IS the AES
seed, and the 2026-09-02 re-key gave one spelling to two rows.  The
manifest records `conversion_route` (`fields-json` or `solve`) beside the
archive's own `route`; the solve route refuses a pre-existing
`convert-planes` work dir and removes only the one it created (F2).

**The original run dir is NEVER touched.**  A converted corpus is a
SIBLING run dir `RUN.page-field/`, built by hand as a symlink farm over
every file of the original but the snapshot, carrying its own
`facts.npz`, the stripped intermediate beside it, and a
`facts.npz.convert.json` manifest.  Converting in place would turn main's
eight sheet-J tests red until this branch merges: main's fixture guard
catches the pre-W2 `TypeError` and skips on it, and it does not catch the
`AttributeError` an appended corpus raises under main's per-capture
reader.

**The three corpora converted 2026-09-12.**  Each manifest is the recipe
log — source, format ref, folded census, field revision, observations,
and the non-field digest the read-back asserted:

| converted corpus | source of the field | appended | field revision | observations C/M/Y | non-field facts, digest |
|---|---|---|---|---|---|
| `<evidence>/J-run.54028.page-field` (the fixtures' J) | solve, 1 capture at 2400, `L:c2-cmy8-r0547@53x37`, both faces | 6 `PlaneField`, 2 `EvidenceRevision` | page 0 591, page 1 891 | page 0 222/222/151, page 1 197/198/121 | 3,280, `e38fb0c7…` |
| `<evidence>/J-run.52093.page-field` | solve, same capture and ref, page 0 only | 3 + 1 | page 0 591 | 222/222/151 | 2,389, `5d08f913…` |
| `<evidence>/analyzer/H7-mirror.page-field` | READ from `page-field-20260908/H-w8/estimate/fields.json` — the W8 solve of this exact input, `L:c2-cmy8-r0850-p120-x1@3392x2368`, 7 captures | 3 + 7 | 41906 | 13,679/13,726/13,644 | 24,463, `7ffd5e37…` |

`EvidenceRevision` is appended with the field — from the solve, or from
the product's `evidence_revision_by_capture` — so a converted corpus is a
faithful receiver-resume base, which a stripped one measurably is not
(the history below).

**Cost, as run 2026-09-12.**  The strip is ~14 s on sheet H — 0.264 GB/s
over the 3.810 GB array blob it streams through — and imports nothing.
The sheet-J solve-and-append took 82.6 s of wall and 3.1 GB peak for the
two-face run (`J-run.54028`) and 48.7 s / 2.8 GB for the one-face run
(`J-run.52093`), one 2400 capture each; sheet H's field is a FILE READ,
so no raster is opened for it, and the write, read-back and digest round
trip over the 412 MB snapshot took 116.6 s and 16.2 GB peak.  Reading
the converted `H7-mirror` afterwards costs what any H snapshot read
costs — 4.4 s and 11.8 GB peak (§2.5).

**What needs nothing.**  `<evidence>/I-single-w8.run.51556` is already
post-W2 production (one 2400 capture of sheet I; 3 `PlaneField` keyed
`(page, plane)`, 1 `EvidenceRevision`).  `angle-residue/*`,
`local-ab/runs/*` and `page-domain-qual/*` carry zero `PlaneField` and
load unchanged.  `H7-mirror-union`, `H-export*` and `w7-e2e/*` get one
strip command each if a phase replays one; none is scheduled.

**Reading the H examples below.**  `<evidence>/analyzer/H7-mirror` and the
run dirs built from it are pre-W2 archives: they are spelled that way
here because that is what the measured runs read, and on this tree the
readable corpus is the converted sibling `H7-mirror.page-field`.
Substitute it — or convert the run dir the example names — before
running any of them.

**History — what the strip ALONE cost, measured on sheet J 2026-09-09.**
This is the record of why the append half exists, not a live procedure.
The strip took 12,388 facts to 12,374: six `PlaneField` (2 pages × 3
planes) and eight `EvidenceRevision` (4 captures × 2 pages), the whole
delta, and the output came out 17.6 % LARGER (82,773,943 → 97,367,683 B)
because the identical 767,676,081-byte blob is recompressed at
`compresslevel=1`.  With `plane_fields` empty every production-field
lookup returned `None`, so `subtract+field` and `subtract+field+offset`
ran for nothing — 0 of that run's 156 certificates, while the analyzer's
own `field2` arms, which it fits itself, minted 27.  And `export-facts`
writes the base snapshot's fact tuple verbatim, so the export inherited
the amputation (12,374 + 156 = 12,530 facts, no `PlaneField`, no
`EvidenceRevision`): the resumed receiver re-solved its page fields from
nothing — 871.8 of that run's 20,898.9 cpu-s — and its per-page evidence
revisions came back LOWER than the run that produced them (9,118 → 8,977
and 8,602 → 8,276), which is the regression `EvidenceRevision` exists to
prevent.  The rule that survives: never hand a stripped export back as
the only copy.

### 2.1b The page field, and the two field families

The receiver publishes ONE registration displacement field per printed
face and plane, in page axes and printed dots.  The analyzer READS it and
publishes none; its door back to production stays a certificate door.
Two arm families ride on that, and they compete on the select fold like
any other pair:

- **`field`, `field+offset`** — the production field.  Certificate-fed BY
  CONSTRUCTION (every page field is solved from certified templates plus
  furniture), applied unrotated, and gated on nothing.  Where the
  standing field reads exactly zero over every observed cell of the
  footprint, halo included (the per-owner affine is fitted over them —
  review F4), the arm COLLAPSES by name to `committed` / `offset`
  (`field_reason "field_reads_zero_here"`, `field_collapse_over
  "observed"`, `register_arm_effective`); where no field stands at all
  the reason is `no_field`.  No published field on the record has a zero
  tile (the prior extrapolates where no evidence reached), so the
  collapse fires only when no field stands.  `field_uncertainty_dots`
  and `field_ordinal` are recorded beside it and gate nothing; the crop
  is grown by the field's own reach over the footprint
  (`field_reach_dots`, review F3) and every successful read records
  `read_headroom_px`, its distance from the crop edge.
- **`field2`, `field2+offset`** (and `patch+field2*`, `pure+field2`) —
  the analyzer's OWN pooled fit, one per (page, plane) over every lane of
  the page, from word and dust anchors alone.  Certificate-free, so the
  withholding controls ADMIT it; it refuses by name
  (`field2_reason "no_support"`) outside its furniture coverage, because
  nothing pulls it to the pose.  Its rules are its OWN since 2026-09-12 —
  the clamp is `field2_kernel.BOUND_DOTS` (2.0 dots, unchanged in value,
  argued on field2's terms and REPORTED when it bites, `clamped_tiles` /
  `clamped_supported_tiles`), and the "publishable" report against
  production's retired quarter-dot floor is gone.

The withholding controls (§5) refuse the production family
UNCONDITIONALLY, and they find it by WALKING `arms.REGISTER_ARMS` through
`arms.FIELD_SOURCE` — which is total over that roster (`certified` for
the production family, `furniture` for the `field2` family, `none` for
`committed`, `offset`, `affine` and `word`) — over the default battery,
every profile's roster and an operator's own `--arms` battery at call
time.  An arm added to a battery is therefore refused the day it is
added, not the day someone edits a literal.

**Producing the analyzer's side of the comparison.**  A pass that runs a
`field2` arm fits the field in flight and writes what it fitted beside its
ledger as `field2.json` — one row per (page, plane) its own arms actually
fitted, read back from the memo and never refitted, each carrying
`production_field_ordinal`, the revision of the production `PlaneField`
that STOOD for that (page, plane) in the pass's inputs (only the `field`
arms consume it; a row it could not fit names `fit_refused` and
`compare.py` skips it).  That file is the consistency check
of what THIS pass read (`compare.py --fields <production> --analyzer
<field2.json>`); the STANDALONE measurement is
`sweeps/field2_paper.py --phase C`, one pooled fit per (page, plane) for
every stream the run names and every live page, written as `phase-C.json`
in the schema `measure/page_field/compare.py --analyzer` reads.  Since
2026-09-12 it takes its corpus on the command line — `--run-dir`,
`--gt-dir`, `--format` (the fossil id a re-keyed archive needs) and
`--out`, so a re-run on a converted corpus writes BESIDE the 2026-09-03
products instead of over them.  Since 2026-09-13 (review F10/F11) the
product carries `run_dir`, `format_ref` and `mm_per_tile` in its header,
phase D reads the phase-C product from the same `--out` and refuses one
whose run identity differs (the unlabelled 2026-09-03 product only under
`--allow-unlabelled-phase-c`), and the millimetre scale comes from the
loaded row (12 tiles are 65.0 mm at c2 and 97.5 mm at c3):

```
PYTHONPATH=src:. env/bin/python -m analyzer.sweeps.field2_paper --phase C \
    --run-dir <evidence>/analyzer/H7-mirror.page-field \
    --workers 8 --out build/analyzer/sweeps/field2-page-field

PYTHONPATH=src:. env/bin/python -m measure.page_field.compare \
    --fields <evidence>/page-field-20260908/H-w8/estimate/fields.json \
    --analyzer build/analyzer/sweeps/field2-page-field/phase-C.json \
    --out build/analyzer/sweeps/field2-page-field/compare-vs-H-w8.json
```

`compare.py` is the ONLY comparator — the analyzer imports nothing from
`measure/` and scores nothing against a published `PlaneField` itself.
Measured 2026-09-12: sheet H, 22 lanes × 250 tiles × three planes, 318 s
wall / 1,444 cpu-s / 36.7 GB peak at 8 workers (the memory doctrine's 4
workers halves that); the converted one-capture sheet J, 3 lanes × 250
tiles × three planes × two faces, 229 s / 10 GB at 4 workers.  A (page,
plane) the fit cannot stand on names itself `fit_refused` and
`compare.py` skips it.

Where the law lives: `analyzer/DESIGN.md` §15 (what the field means on
this side of the certificate door), `analyzer/PAGE-FIELD-PLAN.md` (the
workplan, its invariants and every measured number in §B),
`docs/PAGE-FIELD-DESIGN.md` v0.6 (the receiver's design of record), and
`FIELD2-2026-09-03.md` (the `field2` estimator's own measurement record).

### 2.2 Census — coverage, bands, residue (no pixels)

```
env/bin/python -m analyzer census \
    --run-dir build/analyzer/H7-mirror \
    --out build/analyzer/H7
```

Writes `census.jsonl` (one row per `(page, ty, tx, stream)`) and
`census-rank.json`, and prints every residue row with its band and its
label counts.  Read three things off it:

- **coverage** — a tile no accepted placement's footprint intersects gets
  the verdict `uncovered` and is never a target;
- **bands** — per stream, over covered columns only: a column with fewer
  than 12 covered tiles is `unclassified`; `dead` when the exact
  Clopper–Pearson upper bound (α = 0.05) of the certified fraction is below
  0.25, `marginal` below 0.75, `live` at or above it.  `band_any` is the
  cross-stream union (on sheet H, C, M and Y fail in the same columns);
- **the rank cross-check** — `report.json`'s close rank against the same
  rank re-derived.  A disagreement is a finding, not a warning.

A sheet with a fossil format id needs `--format-ref`; sheet J's own
`RunOpen` descrambles the sheet to coin flips without raising:

```
env/bin/python -m analyzer census --run-dir <evidence>/J-run.54028.page-field \
    --format-ref L:c2-cmy8-r0547@53x37 --out build/analyzer/J
```

The run dir is the CONVERTED sibling (§2.1a): `<evidence>/J-run.54028` is a
pre-W2 archive and `snapshot.read` refuses it on this tree.

Measured on the sheet-J chain of 2026-09-09, where six launches went at the
same run dir: the fossil was already right, and none of the three failures
was about it.  The receiver run itself declared
`--format L:c2-cmy8-r0547@53x37`, so the ladder header's
`provenance.format_ref_override` recorded `{run_open:
L:c2-cmy8-r0547@53x37, used: L:c2-cmy8-r0547@53x37}` and `export-facts`
recorded `format_ref_from "--format-ref"` — the operator passed it anyway,
which is the right habit on a fossil sheet, not a redundancy.  What cost
three launches was a FLAG NAME: `--generations 10`, then `--generation 10`
twice, each dying on `analyzer: error: unrecognized arguments`, printed by
the TOP-LEVEL parser, so the error names neither `ladder` nor the flag that
was meant.  The flag is `--max-generations N` (§2.4).  The launch before
those three carried no generation flag at all, printed `generations <=1` on
its first line exactly as R1 intends, and was killed 32 s in at 10/2,688.

### 2.3 Controls (a run without them is not a result)

```
env/bin/python -m analyzer controls \
    --run-dir build/analyzer/H7-mirror \
    --parity 100 --null 5 --frame-null 3 --withhold-run-mints \
    --out build/analyzer/H7-controls
```

Exit 1 when any control's `passes` is False.  See §5 for how to read them.

### 2.4 The pass

The everyday configuration is the `everything` profile — every arm on every
lane, all four rules, the full ladder, the wide halo, and the re-roll across
the unselected arms at L0–L2:

```analyzer-cmd
env/bin/python -m analyzer ladder \
    --run-dir <evidence>/analyzer/H7-mirror.page-field \
    --targets residue \
    --profile everything \
    --fixed-point --max-generations 8 \
    --workers 8 \
    --out build/analyzer/H7-pass3
```

Either flag turns the cascade on, and they are ORTHOGONAL (ruling R1,
2026-09-06):

| flags | generations |
|---|---|
| neither | ONE — the default, and what every pass in the record ran |
| `--max-generations N` | up to N, stopping the moment a generation re-attacks nothing |
| `--fixed-point` | to convergence, under the default cap (8) |
| `--checkpoint-minutes M` | rewrite `checkpoint.json` every M minutes (30; 0 off) — since 2026-09-13 |
| `--progress-every N` | a progress line every N keys (50; 0 keeps the generation lines only) |
| both | to convergence, bounded by N |

A cap is a BOUND, never a demand for N generations of work, so
`--max-generations 3` on a residue that converges in two runs two.  The
ledger header carries both values (`max_generations`, `fixed_point`) and
the reason the pass stopped (`stop_reason`: `fixed point`, `cap
reached` — which cap is what `max_generations` and `fixed_point` say,
since the driver cannot tell a spelled `--max-generations 1` from the
default — or `interrupted`, the stop door further down), and the pass
prints its cap on the first line —
before R1, `--max-generations N` without `--fixed-point` was silently
discarded and the pass ran one generation (APPROACHES §6.5).  The cascade
was worth +52 of 331 certificates on sheet I's first-run residue and 234
of 508 on sheet H's.  `--profile` is applied after the other flags and
records itself in the ledger header as `knobs_from = "profile:<name>"`.

**A killed pass writes NOTHING — the door or nothing.**  `_out_dir(args)` is
called only after `fp.run` RETURNS (`cli.py`, `_pass`), and the stop door
writes the ledger, the close and the export through that same path, so a
pass that is killed rather than stopped leaves no directory at all and its
certificates are gone.  Measured twice on sheet J: the default battery's
last line is `2470/2688 done, +39 certified, 2.7 s/key, elapsed 1:50:23` and
there is no ledger, no close and no export anywhere for it; the all-arms
battery on the already-closed ten-capture run ended at `350/2740 done, +51
certified, 22.4 s/key, elapsed 2:10:36` and left only its `-input/`
directory.  Neither log carries the door's `stop: signal N …` line (further
down this section), which is how you tell a hard kill from an orderly stop.
4 h 01 m of work and 90 certificates.  So: stop a long pass with ONE ctrl-C
and let it linger, never `kill -9`, and never close the terminal it runs in.

**`everything+field2` is RETIRED (2026-09-12, page-field plan A2)**, and
so are the two `field2c` arms it existed for — the certificate-anchored
PER-LANE page-field fit, a refit per lane per generation.  The page-field
design abolishes the lane-keyed field on both sides of the certificate
door: `field2` is now the pooled furniture fit alone, one per (page,
plane), and it is in `everything`.  Naming the retired profile exits on
`KeyError: unknown profile`; the two profiles built on it
(`everything+patch`, and `everything+patch+pure` through it) are rebased
on `everything` and differ from their old rosters by exactly those two
arms.  The sheet-J and sheet-H records keep their batteries by NAME — see
`J-CONFETTI-2026-09-10.md` §3, where `field2c` took 0 first-success.

The fit worker count no longer needs an operator: `field2_fit_workers` is
published from the pass's own `--workers` by `fixedpoint._knobs_for`
(2026-09-12, A2), so the lazy pooled fit threads per lane instead of
holding the first target that needs it for about six minutes (Y, 22
lanes) while every other worker waits on its key lock.  An explicit
`--knob field2_fit_workers=N` still wins.

Other profiles: `wide-halo` (halo 48/48/32 — the highest-yield single
change measured, not adopted as default because it lost one tile on the
sample it was chosen from), `battery`, `split-branches` (the pre-amendment
calibration, for a control run that wants it).

**The W8 profiles** (the third-layer C line; `APPROACHES-2026-09-06.md`
is the design and `DESIGN.md` §14 the record).  `patch` is the patch
discriminant beside the pinned default, with per-sibling-state
calibration branches, the per-state context, the `platt-state` rule and
the `L7c` rung; `patch-self` adds self-training on the tile's own
population; `patch-refit` adds the decoder-feedback rung `L3f`;
`patch-affine` adds the affine arms; `everything+patch` is the union —
every `everything` arm plus the `patch`, `rings` and `mixture`
heads (it was built on `everything+field2` until that profile retired).
All five carry the wide halo, which the patch filter needs for its
labels.

```
env/bin/python -m analyzer ladder … --profile everything+patch …
```

**The pure path** (`pure`, `pure-self`, `pure-refit`) is the other end of
the same lever.  Every tile is already addressed, the page field is
known and the per-plane poses are mostly right, so the pure path takes
the field pose with NO offset search (`patch+field2`, which collapses to
the committed placement where no field covers the tile), trains the
patch filter over the 5×5 neighbourhood's certified cells, and then
skips the whole calibration stage: one error rate `e` per sibling state
becomes the log-odds `log((1−e)/e)` directly, with no PAVA, no context
correction, no Platt and no refit between the filter and BP.  Since F2
(2026-09-06) **the tile prices itself**: `e` is the error of the hard
decision at the threshold under an equal-prior two-Gaussian fit on the
filter's scores over the tile's OWN cargo cells of that state (the
keystream makes the cargo's prior 1/2 and 1/2, so the priors are held,
not fitted; percentile init, 50 EM steps, no RNG), and the halo's
held-out error — measured on the two cross-fit halves the filter is
fitted on, half A's threshold pricing half B and vice versa — is a FLOOR
under it, never the price (a certified neighbour's cells are easier than
a dead-band tile's cargo).  The adopted `e` is clamped into [0.01,
0.45].  A cell whose sibling state is unknown is an ERASURE (LLR 0,
counted); a state whose halo cannot measure a floor takes the pooled
halo's threshold and floor.  One rule (`sum`), no re-roll, `ctx_mode =
none`.  `pure-refit` keeps its profile but is recommended by nothing
since F2 — the price comes from the tile, and the rung has nothing to
add to it.

**The pure path PLACED behind the patch battery** (`patch-then-pure`,
`everything+patch+pure`, W8 B8).  The pure calibration is worth trying on
the keys the patch battery leaves open and is worth nothing on the ones
it closes, so these two profiles are their parents (`patch-refit`,
`everything+patch`) with `pure+committed` and `pure+field2` placed in the
RE-ROLL ONLY.  A `pure+…` arm computes EXACTLY the score its `patch+…`
twin computes — same filter, same knobs, same halo — and differs from it
in the calibration alone, so a gain is attributable to that and nothing
else.  A placed arm is not in the battery: it is never computed for the
selection, it cannot be the arm the select fold picks, and on a key the
battery certifies it is never computed at all.  When it wins, the ledger
says `certifying_arm = "reroll:pure+committed"`; the header lists
`reroll_only_arms` and the row's `reroll.deferred` names what was placed.

```
env/bin/python -m analyzer ladder … --profile patch-then-pure …
```

**`--reroll-only-arms ARM[,ARM]` places any arm behind any battery**
without writing a profile (W8 B5) — the one-pass door to the mechanism
above.  It obeys the precedence rule like every other explicit flag, so
it also overrides a profile that already places something:

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "band:dead+stream:C" --profile patch-refit --reroll-only-arms "pure+committed,pure+field2" --workers 14 --out build/analyzer/W8/X10
```

Read it against the same profile WITHOUT the flag: the difference is the
placement's yield, and in certificates it cannot be negative.

**The two-pass form** is the same idea spent differently, and it is what
to reach for when the pure path wants knobs of its own (a different
train scope or sampling): run the patch profile, then put the `pure`
family on exactly the keys it left open.

```
env/bin/python -m analyzer ladder --run-dir <run> --targets residue    --profile patch-refit --workers 14 --out <dir>/pass1
env/bin/python -m analyzer ladder --run-dir <run> --targets "open-after <dir>/pass1/ledger.jsonl" --profile pure --workers 14 --out <dir>/pass2
```

**Precedence (W8).**  A profile supplies what the operator did NOT say.
An explicit `--arms`, `--rules`, `--rungs`, `--halo-cells`, `--ctx-mode`,
`--no-reroll` or `--reroll-only-arms` WINS over the profile's own value,
so one arm can be isolated inside a profile's knobs:

```
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "band:dead+stream:C" --profile patch --arms "patch+offset" --workers 14 --out build/analyzer/W8/isolated
```

The header then says `knobs_from = "profile:patch+cli"` and records the
arms, rules, rungs, halo, ctx mode, re-roll, the placed arms and the knob
VALUES, so a pass is reproducible from its own first line.  (Before W8
the profile silently overrode the flags.)  `--knob KEY=VALUE` is
repeatable, is JSON when it parses and a string when it does not, lands
after the profile so the operator's value wins, and refuses the six
derived names the driver assigns itself (`pseudo_labels`, `refit`,
`sibling_state`, `disagree`, `ctx_offsets`, `ctx_state_adopted`).

**Everything nameable is checked before the run dir is opened.**  A
malformed `patch_*` or `pure_*` knob, and since W8 B5 a misspelled arm,
rule or rung as well, exits 2 on the command line with `KNOB REFUSED` or
`NAME REFUSED`.  Each of those names used to be checked deep inside the
pass — an arm at the first `evidence_for`, a rung inside a worker at the
first key, a rule at the first `combine` — so a typo cost a fourteen-
worker run its whole wall.  The rung name space is `types.KNOWN_RUNGS`
(`L0 L1 L2 L3 L3f L4 L5 L6 L7 L7a L7b L7c`), and a test reads
`ladder._run_rungs`' own dispatch chain so the list cannot drift from it.

**The knobs a run chooses for itself.**  Under the ruling of 2026-09-06
("if a run can discover its own truth for the paper-print-scanner-scan
object at hand, it should"), the patch family's geometry knobs take the
value `"auto"`, and `"auto"` is what the `patch` and `pure` profiles
ask for.  A candidate set is walked on the SEARCH fold, per (lane,
plane, sibling state) and per tile, by the same paired standard-error
test `select_arm` uses for arms; the choice and every candidate's
held-out loss are recorded in the row's blind detail (`auto_choices`,
`auto_losses`, `auto_refused`, `patch_auto_walk_fold`), and where that
fold cannot tell the candidates apart the run keeps the inherited value.
(The SEARCH fold, not the select fold — a knob walk minimises, and the
select fold has to stay a fold no search has touched, or `select_arm`'s
paired test and `platt`'s lane weights are read off a minimum; review
2026-09-06.  An auto arm forfeits `nested_cv_logloss` for the same
reason a searching register arm does.)

| knob | candidates | inherited fallback |
|---|---|---|
| `patch_samples_per_cell` | 8, 16 (capped at the lane's native pitch) | 8 |
| `patch_window_cells` | 1.0, 1.5, 2.0 | 1.5 |
| `patch_channels` | `r`, `rgb` | `r` |
| `patch_features` | `pixels`, `rings` | `pixels` |
| `patch_shrinkage` | 1e-3, 1e-2, 1e-1 | 1e-2 |
| `aperture_cells` | 0.5, 0.7, 1.0 | 0.7 (production's box) |
| `patch_min_labels_per_state`, `patch_min_labels_agnostic` | not a count at all: the tier is admitted when its own out-of-fold error beats the population's majority rate by more than two standard errors, AND its optimism does not exceed the advantage it bought, AND the score its cells would otherwise carry does not beat it by more than the same margin | 200 |

An explicit value still wins (`--knob patch_samples_per_cell=16`), which
is how every isolation run of `APPROACHES` §3 is spelled.  What is NOT
auto is anything that names what is being measured rather than how well:
the unmix mode, the register arm, `patch_train_scope`,
`patch_selftrain_rounds`, the fallback mode.

**How the walk decides — three operator knobs**
(`HALO-CHANNEL-2026-09-07.md`, the six-cell halo × channel matrix and its
two ledgers).  The table above says WHAT is measured; these three say HOW
the run reads it, and none of them is `"auto"`-able for that reason — a
rule cannot be chosen by the rule it defines.  **Two of the three ship
ON**, by the pre-registered isolation of `HALO-CHANNEL` §4.6 (measured
2026-09-07 on 153 open C tile-streams at ONE code state; 843
certificates checked, 0 wrong, 0 false accepts): the franchise **net
+4** (+5/−1), the direction **net +6** (+7/−1), the weighting −3 and
refused.  Each shipped mechanism is a CROSSING, not a containment, and
of the gate's three clauses only clause 1 (zero wrong, zero false)
applied to them and passed — clauses 2 and 3 failed and are
dispositioned in `HALO-CHANNEL` §5.1.  Naming all three at their first
value below restores the pre-change walk's RULES; W4's nested ridge
lands unconditionally and is named separately.

| knob | values | ships | what it changes |
|---|---|---|---|
| `walk_weighting` | `none`, `cargo` | `none` — −3 alone, and exactly 0 gained / 0 lost over the shipped pair (§5.5) | W1 — the walk's held-out losses are importance-weighted so the halo's histogram over (sibling state, incumbent difficulty) matches the TARGET TILE's own cargo.  The halo's cells are 4.3–4.8× easier than the dead band's three-ink cargo, so the objective was priced on the wrong population — the same defect the pure path had fixed in `583b482` |
| `walk_franchise` | `inherit`, `pooled` | **`pooled`** (+4) | W2 — a population whose own search fold cannot carry the vote takes the POOLED (state-agnostic) walk's discovery instead of the module constant.  At halo 16, 674 of 3,186 three-ink populations (21 %) never voted and `auto_choices` recorded the pin as if it were a choice |
| `walk_direction` | `adopt-if-better`, `nested-richer` | **`nested-richer`** (+6) | W3 — on the NESTED channel axis (`r` is literally `rgb`'s first 144 columns) the richer candidate is adopted unless the leaner one clears the bar.  Channel axis only: window and samples keep ties-to-inherited |

The ledger says which happened, per population: `auto_source`
(`own` / `pooled` / `inherited`) and `auto_verdicts` (the paired test
itself) are what make a VOTE countable apart from an INHERITANCE,
`labels_per_feature_chosen` divides by the width the population was
actually fitted at rather than the inherited one, `shrinkage_fitted` is
the ridge it was actually fitted at, and `auto_detail.loss_population`
names the population the published losses are the mean over (the halo's
own labels, or those labels weighted onto the cargo under W1).

One change is NOT a knob and lands unconditionally: the REGULARISER left
the coordinate order and became an inner minimisation under every
candidate, so no candidate is judged at another candidate's ridge (it
used to be walked last, which meant the channel axis was always judged at
the inherited ridge and the richer model could only ask for more ridge
after it had already lost the vote).  A run that NAMES `patch_shrinkage`
is unaffected.  **The ridge a population chooses is the ridge it is
fitted at** — that was the point of the change and it was not true of
the code until `3a661fe`, when a review found the winner published in
every ledger and discarded before the fit; `shrinkage_fitted` is the
field that pins the two together (`HALO-CHANNEL` §5.5).

**The halo is an operator axis, not a knob.**  `--halo-cells 48` sets all
three planes (48/48/48); `--halo-cells C=48,M=48,Y=32` names them, and the
named spelling must name every plane.  The two are different runs, and
`wide-halo` is the second — the header carries `halo_from` beside
`knobs_from` so a run whose only CLI word was `--halo-cells` no longer
reads as knob-pinned.

**The one exception, and why.**  The `pure`, `pure-self`, `pure-refit`,
`patch-then-pure` and `everything+patch+pure` profiles NAME
`patch_samples_per_cell` at 16 rather than leaving it auto.  Every other
axis a population may choose is a column SLICE of the widest one, so the
5×5 neighbourhood's rows (`patch_train_scope="local5"`, harvested once
before any population has chosen) serve every candidate — but a coarser
SAMPLING moves every sample position and is a different grid, not a
slice, so a chosen 8 would throw those rows away.  The pin is the pure
path's premise held in place, not a value read off a sheet; it is the
only knob in `_PURE_KNOBS` that is not `"auto"`, and a drift guard in
`test_analyzer_docs.py` keeps this paragraph and the code together.

Smoke a configuration with `--limit N` before committing hours to it.

**What you see while it runs** (STDERR, since 2026-09-04 — the first machine 4
pass printed its header line and then nothing for its whole length; a
plain `| tee` captures stdout only and misses every line below — use
`2>&1 | tee run.log`):

```
targets 429  arms 14  rules ('sum', 'best', 'platt', 'corr')  rungs (...)  workers 14
ledger: <out>/ledger.jsonl (header written; rows land as each generation folds); mints: <out>/mints.jsonl; checkpoint every 30 min …
generation 0: 429 pending (0 re-attacks), certificates so far 0, elapsed 0:00:00, peak RSS 6.10 GB
  generation 0: 50/429 done, +4 certified (9 mints), 41.3 s/key, elapsed 0:34:25, remaining ~4:21:00, peak RSS 18.72 GB (last (0, 3, 17, 'Y'))
  generation 0: 100/429 done, +9 certified (17 mints), 38.9 s/key, elapsed 1:06:58, remaining ~3:33:10, peak RSS 21.40 GB (last (0, 4, 2, 'C'))
  …
generation 0 done: +37 certificates (total 37), 2 refused, 2:41:05, peak RSS 24.9 GB
generation 1: 88 pending (61 re-attacks), certificates so far 37, elapsed 2:41:05
  …
pass done: 41 certificates over 3 generation(s) in 3:02:44; writing the ledger
```

Since 2026-09-13 the pass writes as it goes (`MEMORY-2026-09-13.md`): the
ledger's header is on disk before the first key, each row lands as its
generation folds, every certificate lands in `mints.jsonl` the moment a
worker wins it, and `checkpoint.json` is rewritten at the first key or
generation boundary after every 30 minutes
(`--checkpoint-minutes M`, 0 off) with the generation, the key counts,
the exposure accounting and the memory line. A killed pass therefore
keeps its mints and its folded rows; recovery is `export-facts --ledger
<out>/mints.jsonl` into a new base, `union-base`, and the same pass
again (the operator line at the start prints the recipe). `mints` on a
tick counts certificates won so far in the running generation;
`+certified` counts the ones folded.

`s/key` is wall time per finished key over the generation, so with 14
workers it is roughly 14 times a key's own cost; `remaining` is that rate
extrapolated over the keys still pending in THIS generation, and says
nothing about the generations the cascade will add; `peak RSS` is the
process's high-water mark (`ru_maxrss`), which is what a memory kill is
about.  The first key that needs the page field blocks about six
minutes before the first tick (`--progress-every N` sets the tick
cadence, 50 by default; 0 keeps the generation lines only).  **SIGUSR1** (`kill -USR1 <pid>`) or **ctrl-T**
(SIGINFO, macOS/BSD) prints a status line at any moment:

```
status: generation 0, 133/429 done, certificates 12 (+12 this generation), exposure 3,904 distinct, elapsed 1:31:02
```

**Ctrl-C (or SIGTERM) is the stop door** (2026-09-07), the one holo3's
engine has: it asks for an ORDERLY stop rather than killing the pass.
A key no worker has started yet is skipped — it stays open and
un-attempted, and produces no row — the keys in flight finish, their
rows fold as they always would, and the ledger is written through the
same code path as an ordinary end, with `stop_reason = interrupted` and
two extra header counts, `keys_done` and `keys_skipped` — key ATTEMPTS
claimed and attempts turned away, not distinct keys: a cascade
re-attacks a key, and a re-attack REPLACES that key's row rather than
adding one, so `n_rows` beside them is what counts keys.  `ledger.md`
carries a `stopped` row saying the same, so a stopped pass cannot be
read as an exhausted one.  The status doors keep answering during the
drain.  A SECOND ctrl-C restores the
handler that was there before, so a third one kills the pass and its
ledger with it.

```
stop: signal 2 — the keys in flight finish, the rest stay open, and the ledger, the close and the facts are written; again to restore the default handler
stop: close open over 5731 certificates (312 from this pass); payload not written
stop: facts /path/out/facts.npz — 5419 + 312 = 5731 certificates
```

After the ledger, an interrupted pass runs the next two steps of the
operator's loop for you: the close (`close.json`, and `payload.bin` when
the volume verifies) and `export-facts` (`facts.npz` + its manifest,
from the run's own snapshot and this ledger), so a stopped pass hands
back everything an exhausted one would have.  Each step prints its
outcome and neither can cost the other: a close short of K and an absent
snapshot are RECORDED refusals, not exceptions.  At a normal end nothing
changed — the close as always, and no `facts.npz`.

Outputs in `--out`: `ledger.jsonl` (one row per tile-stream ATTEMPT, with
nested per-(lane, arm), per-rule and per-rung records, a header first and
a footer last — a re-attacked key appends a new row and every reader
takes the last per key; §4), `mints.jsonl` (one row per certificate, as
won), `checkpoint.json`, `field2.json` (§2.1b), `ledger.md` (the
summary), `close.json`, `payload.bin` when the close recovers bytes, and
two PNG maps per plane (`--no-maps` to skip). An existing ledger or mint
file in `--out` is kept aside as `.bak`, never overwritten.

### 2.5 The incremental pass

A second pass should not re-earn the first pass's certificates, and it must
not re-copy tens of gigabytes of rasters to say so.  Build a run dir that
SYMLINKS the base run's rasters and `events.jsonl`, copies `report.json`
and `argv`, and takes an exported snapshot as its `facts.npz`:

```
env/bin/python -m analyzer export-facts \
    --snapshot build/analyzer/H7-mirror/facts.npz \
    --ledger build/analyzer/H7-pass3/ledger.jsonl \
    --out build/analyzer/H-export5/facts.npz

env/bin/python -m analyzer union-base \
    --run-dir build/analyzer/H7-mirror \
    --facts build/analyzer/H-export5/facts.npz \
    --out build/analyzer/H7-mirror-union
```

`union-base` verifies that every capture id the facts name is one
`report.json` declares, and that every declared capture has a raster
directory; both refuse before writing.  That check is not ceremony: a
snapshot holds POSES, and a pose applied to another capture's pixels
produces evidence that looks fine and means nothing.  It costs one
`snapshot.read` (11.8 GB peak on H, 4.67 s); `--no-verify-facts` skips it
and says so in the record.  The facts file is SYMLINKED — deleting or
rewriting `--facts` afterwards breaks every run dir built from it.

Then the pass, targeted at what the union leaves open:

```analyzer-cmd
env/bin/python -m analyzer ladder \
    --run-dir build/analyzer/H7-mirror-union \
    --targets "open-after <evidence>/analyzer/H7-pass5/ledger.jsonl" \
    --profile everything \
    --fixed-point --workers 8 \
    --out build/analyzer/H7-pass6
```

`open-after LEDGER[,LEDGER]` selects the covered, uncertified keys after
the union of those ledgers AND the run's own facts.  On a union base the
second half is already true, so the flag is what makes a pass targetable
from ledgers that have not been exported yet.

### 2.6 The close

```
env/bin/python -m analyzer close \
    --run-dir build/analyzer/H7-mirror-union \
    --localize \
    --out build/analyzer/H7-close
```

Add `--ledger L.jsonl` to fold a ledger's certificates in without exporting
them first.  A `ladder` pass runs the close itself and writes the same
files; this command is for closing a union that was assembled some other
way, or for re-closing with `--localize`.

Exit 0 only on a VERIFIED close.  What "verified" means is §6.  The
recovered bytes are written to `<out>/payload.bin` with their sha in
`close.json` — that file is what makes an offline `score` possible against
a payload nobody handed the instrument.

`--localize` turns an inconsistent fountain from a verdict into named keys
and closes on the survivors.  `--no-consistency` skips the check; do not,
unless you are timing something.

Measured on sheet H's union base: verified, k_total 5,277, 5,437 symbols,
160 redundant, 0 inconsistent in 0.66 s, metadata rank 24, payload
2,220,921 B, sha `0ad329fb796d…` — byte-identical to the 2026-08-18
emission.  6.4 s wall, 11.8 GB peak, essentially all of it the snapshot
read.

### 2.7 Give the harvest back to production

`export-facts` writes a NEW snapshot: the base snapshot's fact tuple
verbatim with the analyzer's certificates appended, so a holo3 `--resume`
can use certificates the analyzer minted — their labels join neighbouring
known frames, their bits reach the close.

```
env/bin/python -m analyzer export-facts \
    --snapshot build/analyzer/H7-mirror/facts.npz \
    --ledger build/analyzer/H7-pass3/ledger.jsonl \
    --ledger <evidence>/analyzer/H7-pass5/ledger.jsonl \
    --out build/holo3-H-analyzer-facts-4/facts.npz
```

Rows with verdict `certified` and `certified_list` are folded (the list
rungs are counted separately; `--no-list-rungs` drops them).  Keys the
snapshot already certifies are skipped and counted.  Duplicates across
ledgers take the FIRST ledger's bits; a DISAGREEMENT of user bits — ledger
against ledger, or ledger against snapshot — is a hard refusal.  Before
writing, the fountain consistency check runs on the union and REFUSES on a
poisoned symbol, naming the disagreeing keys and pointing at
`close --localize`.  `<out>.manifest.json` records input and output
sha256s, the ledgers' shas, their run-level exposure copied from the
headers, and the counts by stream, rung and generation.  It is
timestamp-free.  `--dry-run` prints the manifest and writes nothing.

Certificate `source` is spelled `analyzer/<certifying rung>`, e.g.
`analyzer/L2:damped@300`.  Nothing on the resume path parses a source
string, so the `:` and `@` are safe and the spelling names the rung that
paid for the bits.

**The caveat that matters:** a resume from the exported snapshot must
declare the SAME captures the base snapshot's poses were fitted on.  Export
from the base snapshot of the run you intend to resume, and never pair one
run's snapshot with another run's ledger.

Sheet I, measured: 5,880 + 3 = 5,883 certificates, 0 already certified,
output 227.8 MB, 75 s and 8.6 GB peak (the write's DEFLATE is nearly all of
it); 4.8 s and 6.6 GB for `--dry-run`.

### 2.8 Resume production from it

The same decode command the run dir's own `argv` records, with `--resume`
pointed at the exported snapshot.  For sheet H:

```
env/bin/python -m holo.receiver decode \
    <evidence>/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-1200dpi-a.tiff \
    <evidence>/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-1200dpi-b.tiff \
    <evidence>/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-2400dpi-a.tiff \
    <evidence>/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-2400dpi-b.tiff \
    <evidence>/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-4800dpi-a.tiff \
    <evidence>/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-4800dpi-b.tiff \
    <evidence>/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-4800dpi-c.tiff \
    --dpi 1200 --dpi 1200 --dpi 2400 --dpi 2400 \
    --dpi 4800 --dpi 4800 --dpi 4800 \
    --format L:c2-cmy8-r0850-p120-x1@3392x2368 \
    --max-pages 1 \
    --plane-fields --complete --workers 14 \
    --out build/holo3-H8.bin \
    --run-dir build/holo3-H8-run \
    --diag 8023 --snapshot-every 30 \
    --resume build/holo3-H-analyzer-facts-4/facts.npz
```

`--format` is mandatory and must be the sheet's fossil id (an earlier Hend
run was killed because it lacked one).  `--max-pages 1` is what keeps a
single-page sheet out of a 133-page cold-placement domain — the plane-view
run that ran 4.5 h and died in the cold endgame is the lesson.  `--diag
PORT` on every long run.

**The operator's doors** (commit `dc47bc8`), all served at the loop top
where the store is consistent:

- `--snapshot-every MINUTES` (default 30, `0` = off) writes a safety
  `facts.npz` on a cadence.  Without it, `facts.npz` is written only at
  RunDone and a kill loses everything.
- `kill -USR1 <pid>` dumps the facts on demand and prints the status rows.
- ctrl-T (SIGINFO, macOS) prints the status rows.
- ctrl-C / SIGTERM ask for an ORDERLY stop: the loop breaks at the next
  consistent point and every product the run would have written at
  exhaustion is written.  A second ctrl-C restores the default handler, so
  a third one kills.

A signal that lands while the loop waits takes effect at the next completed
job.

### 2.9 Score — offline, after the fact

Scoring against a payload is not part of a run.  The analyzer never opens a
payload while it decides anything; `score` is the one door that does, and
it decodes nothing.

```
env/bin/python -m analyzer score \
    --ledger build/analyzer/H7-pass3/ledger.jsonl \
    --ledger <evidence>/analyzer/H7-pass5/ledger.jsonl \
    --payload build/analyzer/H7-close/payload.bin \
    --out build/analyzer/H7-score
```

`--payload` may be the emitted payload or the one a close recovered — the
envelope verified it either way.  The full configuration adds the
generation dir (which sha-gates the payload against its manifest and
supplies the emitted per-cell field for the cell-level splits) and the run
dir (which recomputes the default arm's evidence, blind, through the same
`arms.evidence_for` the run called, for R, cell error, d′, AUC, the splits,
capture agreement and the waterfall):

```
env/bin/python -m analyzer score \
    --ledger <evidence>/analyzer/H7-pass4/ledger.jsonl \
    --payload <evidence>/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm/payload-counting.bin \
    --gt-dir <evidence>/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm \
    --run-dir build/analyzer/H7-mirror-union \
    --limit 3 --maps \
    --out build/analyzer/H7-score-full
```

2026-10-09: after the evidence cleanup the `--gt-dir` is a directory you build. The published
archive carries a sheet's `manifest.json` and `payload-counting.bin` under
`<root>/paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/<sheet>/emission/` and its
PostScript under `…/<sheet>/jobs/page000.ps`, but not its `page000_gt.npy` (tier delete, the
`*_gt.npy` rule): copy the manifest into a directory and write the GT beside it with
`env/bin/python util/ps_gt.py …/<sheet>/jobs/page000.ps --out DIR/page000_gt.npy
--expect-sha256 <the manifest's pages[0].gt_sha256>` (`analyzer/truth.py` reads both from
`--gt-dir`; `--payload` takes the published `payload-counting.bin` directly).

`--limit` bounds the evidence recomputation only; certificates and rungs
are always all of them.  The CLI exits 2 on any `wrong` or `false_accept`,
with every disagreeing key named in `score.md`.

The reader is streaming (`read_header` + `iter_rows`): a first cut that
materialised rows reached 26 GB of RSS before it was killed, because sheet
H's passes are 2.6–5.8 GB of JSON each and five together are 18 GB.

`score` also takes `--arms` (the FIRST arm named is the one whose
evidence is recomputed and scored) and, since W8, `--knob`, so ONE arm
at ONE knob setting can be scored offline against the payload without a
blind pass.  It has no `--profile`: a profile is a decision
configuration, and `score` decides nothing.

```analyzer-cmd
env/bin/python -m analyzer score --ledger <evidence>/analyzer/ledgers-C/H14-C.jsonl --payload <evidence>/analyzer/H14-pass1/payload.bin --gt-dir <evidence>/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm --run-dir <evidence>/analyzer/H14-union --arms "patch+offset" --halo-cells 48 --knob patch_samples_per_cell=16 --workers 14 --out build/analyzer/W8/S1b
```

Read that output by (band, sibling state) with the truth-side script the
W8 measurements used — it lives under `measure/`, outside the package,
because it opens the scorer's payload-derived splits:

```
PYTHONPATH=src:. env/bin/python measure/c-third-layer-20260906/bystate.py \
    --level 3 build/analyzer/W8/S1b/score.jsonl
PYTHONPATH=src:. env/bin/python measure/c-third-layer-20260906/paired_bystate.py \
    --level 3 --band dead --state 3 \
    <evidence>/analyzer/W8/S0/score.jsonl build/analyzer/W8/S1b/score.jsonl
```

`--level 3` restricts the aggregation to the 4800-dpi lanes; the paired
script pairs two score runs over the same (lane, row) pairs and prints
the delta with its standard error per lane.

**`PYTHONPATH=src:.` is needed for EVERYTHING here, the package
included** — measured 2026-09-06 (§6.5 of `APPROACHES-2026-09-06.md`,
where a `score` launched without it died in 0.33 s).  `pyproject.toml`'s
`pythonpath` is a **pytest** setting and nothing else reads it, so a bare
`python -m analyzer` finds the `analyzer` package (the repo root is on
`sys.path`) and then fails on `analyzer/close.py`'s `from holo.receiver
import data` with `ModuleNotFoundError: No module named 'holo'`.  Most
commands in this file are printed WITHOUT the prefix for width; export it
once per shell — `export PYTHONPATH=src:.`, which is what every chain
script under `<evidence>/analyzer/W8/logs/` does in its own first lines — or
put it in front of each one.  (An earlier version of this paragraph
claimed the package did not need it; it does.)

---

### 2.10 Isolating one approach

Every mechanism the analyzer carries can be run ALONE, and the W8 design
document (`APPROACHES-2026-09-06.md`) is the enumeration: §1 is every
approach with its isolation flags, §2 the compositions, §3 the run
matrix and §6 what each run measured.  The commands below are complete —
copy them, they parse (a test harvests every `analyzer-cmd` block in
this file and runs it through the parser).

The target lists come from the census, and since W8 the band ∧ stream ∧
siblings conjunction has a grammar, so the common populations need no
list file:

```analyzer-cmd
env/bin/python -m analyzer census --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --out build/analyzer/W8/census
```

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "band:dead+stream:C+siblings:M,Y" --arms "subtract+offset" --halo-cells 48 --workers 14 --out build/analyzer/W8/I0
```

`band:dead+stream:C+siblings:M,Y` is the population where every
per-sibling-state mechanism can fire (both sibling planes certified);
`stream:C+siblings:M` is the other half, where the state is unproven and
only the state-agnostic tier and the `subtract` fallback carry the arm.
`--targets "list FILE"` still takes an explicit list of
`page,ty,tx,stream` lines, and a key not in the census is silently
dropped — the census's printed counts are the check.

One arm, alone (the patch discriminant against the pinned default):

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "stream:C" --arms "patch+offset" --halo-cells 48 --workers 14 --out build/analyzer/W8/I1
```

Two arms, so the select fold's paired comparison and the re-roll
attribution appear on every row (`_selected`, `certifying_arm`):

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "stream:C" --arms "subtract+offset,patch+offset" --halo-cells 48 --workers 14 --out build/analyzer/W8/I2
```

One calibration change, alone (per-sibling-state branches and the
per-state context on the DEFAULT arm — no patch anywhere):

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "stream:C" --arms "subtract+offset" --halo-cells 48 --knob branches=state --knob ctx_state=true --workers 14 --out build/analyzer/W8/I3
```

One rule, one rung: `--rules "sum,platt,platt-state"` isolates the
state-conditional combination (leave-one-out over rules is EXACT in the
ledger's attribution), `--rungs "L0,L1,L2,L7c"` the state-targeted
erasure, `--rungs "L0,L1,L2,L3f"` the decoder-feedback refit:

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "stream:C" --arms "subtract+offset,patch+offset" --halo-cells 48 --knob branches=state --rungs "L0,L1,L2,L3f" --knob refit_rounds=2 --workers 14 --out build/analyzer/W8/I6
```

A composition, and the same composition without the attempt-count
channel (the re-roll), which is what says how much of a profile's yield
is the mechanism and how much is more rolls of the same dice:

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "stream:C" --profile patch --workers 14 --out build/analyzer/W8/X1
```

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "stream:C" --profile patch --no-reroll --workers 14 --out build/analyzer/W8/I8
```

The pure path, against the same rows:

```analyzer-cmd
env/bin/python -m analyzer ladder --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "stream:C" --profile pure --workers 14 --out build/analyzer/W8/P0
```

And the controls, which are not optional (§5, DESIGN §8) — note that
every control draws its DONORS from production certificates, so point
them at certified rows of the regime you want controlled, never at the
residue:

```analyzer-cmd
env/bin/python -m analyzer controls --run-dir <evidence>/holo3-H-with-facts-7-run.32018 --targets "list <evidence>/analyzer/W8/C-dead-certified.list" --profile patch --null 5 --frame-null 3 --parity 100 --workers 14 --out build/analyzer/W8/K1
```

After every blind pass, score its certificates against the payload; 0
wrong is the invariant every tier has held:

```analyzer-cmd
env/bin/python -m analyzer score --ledger build/analyzer/W8/X1/ledger.jsonl --payload <evidence>/analyzer/H14-pass1/payload.bin --out build/analyzer/W8/X1-score
```

---

## 3. Time and memory

Measured on sheet H — 1,000 residue tile-streams, seven captures, 25,040
facts, on a 64 GB machine.

| step | wall | peak RSS |
|---|---|---|
| `mirror` (sheet J, one 2400 capture) | 18 s | 2.4 GB |
| `census` | seconds | one snapshot (~12 GB on H, 6.5 GB on I) |
| `ladder` pass 1 (rungs L0,L1,L2, rules sum/best, 8 workers) | 59 min | 19 GB footprint |
| `ladder --profile everything` (pass 3) | 3.8 h | 44.6 GB |
| `ladder --profile everything+field2` (pass 4) — the profile RETIRED 2026-09-12, the number kept as the record | 3.5 h | 48.6 GB |
| `ladder` incremental on a union base (pass 5) | 3.6 h | 51.3 GB |
| `union-base` (with the verifying read) | 4.7 s | 11.8 GB |
| `close --localize` | 6.4 s | 11.8 GB |
| `export-facts` (sheet I, full write) | 75 s | 8.6 GB |
| `export-facts --dry-run` | 4.8 s | 6.6 GB |
| `score`, five H ledgers (18 GB JSON), no run dir | 183 s | 0.52 GB |
| `score --run-dir --gt-dir --limit 3` | 52 s | 11.9 GB |
| `emit-plane`, seven captures | 101 s | 18 GB |

The floor everywhere is one `snapshot.read`.  The pass profiles sit on top
of it with per-thread memos, so the everything profiles land near 45–51 GB
— which is the whole reason for the one-at-a-time rule.  `score` without a
run dir is the one command that costs nothing: it holds one ledger row at a
time.

**Thirteen captures, measured in W8** (2026-09-06, machine 4, 128 GB, the
`<evidence>/holo3-H-with-facts-7-run.32018` run dir; every wall below is
`/usr/bin/time -l` around one process at 14 workers).  The table above
was measured with SEVEN captures, and the patch arm keeps a RAW crop
beside the filtered one, so both numbers were re-measured before the
union runs were scheduled:

| step | wall | peak RSS |
|---|---|---|
| `score --run-dir --gt-dir --arms "subtract+offset" --halo-cells 48` (156 C rows) | 7.9 min | 35.4 GiB |
| `score … --arms "patch+offset" --halo-cells 48` | 9.7 min | 35.5 GiB |
| `score … --arms "patch+offset" --knob patch_samples_per_cell=16` | 14.5 min | 35.4 GiB |
| `ladder --arms "subtract+offset" --halo-cells 48` (153 rows, 1 generation) | 105 s | 36.0 GiB |
| `ladder --arms "patch+offset" --halo-cells 48` | 93 s | 35.3 GiB |
| `ladder --arms "subtract+offset,patch+offset" --halo-cells 48` | 148 s | 35.3 GiB |

The patch arm costs about 10 % more wall than the box mean at 8 samples
per cell and about 55 % more at 16, and its raw crop is NOT what
dominates the footprint — the snapshot is.

Rough per-unit cost: about 1.0 s per (key, lane) for the full battery.

**Per key on sheet J** (2026-09-09/10, machine 4 at 14 workers, four 2400-dpi
captures of a duplex confetti sheet, 2,688 residue targets): the default
battery 2.7 s/key; `everything+patch+pure` 7.9 s/key over the same
seed-ordered keys; the same battery on the TEN-capture base 22.4 s/key,
2.8 × the four-capture price, with generation 0 alone projecting ~14 h 52 m
more at the point it was killed.  A pass's own `seconds` is **WALL, not
CPU** — `fixedpoint.py:900` sets it from `time.perf_counter()` over the
whole pass — and the analyzer records no CPU total anywhere, so it must
never be added to a receiver run's cpu column; that pass's wall, and the
estimate of machine 4 CPU behind it, are in `J-CONFETTI-2026-09-10.md` §5.

---

## 4. Reading the ledger

`ledger.md` is the report; `ledger.jsonl` carries everything.  The columns
worth looking at first:

**Identity and census.** `page`, `ty`, `tx`, `stream_id`, `esi`; `covered`;
`certified_by_production` and `source`; `band` and `band_any`;
`neighbours_certified`, `siblings_certified`, `known_cells_in_halo`,
`n_discriminating_labels` (labels whose sibling state differs from the
target's — the binding resource, and what blind selection is gated on);
`production_attempts` from `events.jsonl` when present; `metadata_known`.

**Outcome.** `verdict` — a run can only produce `open`, `certified` and
`certified_list` (the scorer owns `wrong`, `false_accept` and
`unscoreable`); `certifying_rung`, `certifying_rule`, `certifying_arm`
(`reroll:<arm>` when a re-roll won, which is the only way to read the
attempt-count gap off the ledger); `generation` and `predecessors`
(`predecessors` is a superset — it includes failed re-attack triggers).

**Evidence.** `rungs["user_bits"]` for a certificate;
`rungs[…]["detail"]["hard_packed_b64"]` — the packed exit hard vector,
kept by default, 683 chars per rung — which is everything the offline
scorer needs that only the run can produce.  `diag` is blind bookkeeping:
seconds, lanes, refusal, attempts.  (It was called `oracle` and held the
ground-truth side table until the 2026-09-04 ruling; the name went with the
scores.)

**Agreement.** `diag["independent_agreement"]`, `n_certificate_claims`,
`contradiction`.  The header gains `n_corroborated` and `n_contradictions`;
the stream×band table gains `corroborated` and `contradicted` columns and
the summary an `## Independent agreement` section.

**The file's shape, since 2026-09-13.** Line 1 is the header with
`partial: true`; the last line is a footer — the final header, `partial:
false`, with `n_rows`, `n_certified`, `generations_run`, `stop_reason`,
the exposure totals; a file with no footer is a pass that never returned
and every reader says so (`ReadStats.partial`, `truncated_lines`). Rows
carry `row_seq`; a re-attacked key has more than one and the LAST wins
(`ledgerio.iter_rows_latest`), which `report`, `score`, `export-facts` and
`close` all apply. `mints.jsonl` beside it is a ledger in miniature — the
same header, one row per certificate with its certifying rung under
`rungs`, a footer with `n_mints` — and every door that takes `--ledger`
takes it.

**Header.** seed, workers, arms, rules, rungs, `ctx_mode`, `halo_cells`,
`targets_from`, `knobs_from`, `non_blind`, `generations_run`,
`exposure_distinct` and `exposure_expected_false` — and, since W8, the
knob VALUES (`knobs`), `reroll` and `reroll_rungs`, so two passes that
differ only in a knob are distinguishable on disk, plus the generation
bound and its outcome (`max_generations`, `fixed_point`, `stop_reason`;
§2.4).

**The blind patch/pure detail** (W8, on every `(lane, arm)` row of a
patch or pure arm; counts and small dicts only, never a filter's
weights): `patch_states` per sibling state (`n_fit_0`, `n_fit_1`,
word/dust/cargo counts, `fitted`, `labels_per_feature`),
`patch_fit_error_insample` vs `patch_fit_error_crossfit` (the optimism
of the fit, the two numbers the tier admission reads),
`patch_fallback_cells` / `patch_agnostic_cells` / `patch_outside_cells`,
`patch_labels_from` (`halo`, `halo+self`, `halo+bp`), `auto_choices` and
`auto_losses` (what the run chose for itself, and what every candidate
cost on the select fold), `branches` per state with `branch_fallback`,
`ctx_state_*`, `platt_state_refused`, and for the pure path
`pure_price_by_state` (per state: `self` — the tile's own overlap,
`floor` — the halo's held-out error, `adopted`), `pure_price_source`
(`self`, `floor`, or `floor:<why no self fit>`), `pure_error_by_state`
(the adopted price) with both cross-fit halves under
`pure_populations`, `pure_threshold_by_state`, `pure_fallback_states`
(states the POOLED halo priced — a pool of known-state rows only, and
never a state that priced no cell), `pure_erased_cells`,
`pure_unknown_state_cells`, `pure_floor_only_cargo_cells` (cargo cells
whose state had no self fit at all, not even the tile-pooled one) and
`pure_self_excluded_cells` (rows the decoder's pseudo labels trained the
filter on, subtracted from the self population).

The summary's certificate attribution is given three ways: the **order-free
union** as the headline, first-success marginals in the pinned order, and
leave-one-out.  Leave-one-out over RULES is exact (the driver runs every
rule's ladder even after one certifies); over RUNGS it is a LOWER BOUND,
because the ladder stops at the first certificate and a later rung was
never attempted.

Bits wrong, the soft information rate and the waterfall are NOT in the
ledger.  They are offline columns; `analyzer score` computes them from the
packed hard vectors the ledger carries.

`report` re-renders a summary from an existing ledger:

```
env/bin/python -m analyzer report <evidence>/analyzer/H7-pass5/ledger.jsonl
```

---

## 5. The controls, and how to read parity

Four instruments, each answering a different way of being wrong.  Each is
reported with a **power denominator** — the same tiles decoded truthfully —
so "zero certificates" cannot be a claim about a battery that certifies
nothing anyway.

- **Null arm.**  The pixels of a tile at least eight tiles away (beyond the
  registration period), read at THIS tile's address, climbing the full
  ladder at the same knobs.  Any certificate is `wrong`.  Its consults and
  its predicted false count are reported beside the live totals.
- **Frame null.**  The right pixels and the right address, but the
  certified frame contributions taken from another tile.  Must certify
  nothing extra.
- **Positive control.**  Withhold real certificates — the run's own late
  mints from `events.jsonl` (`--withhold-run-mints`; an empty set is a hard
  error), or `--withhold-keys FILE`, or `--withhold-source` with the real
  `tiles/<stage>` strings — and try to win them back with the frame and
  the pooled context rebuilt without them, and with the production
  `field` arms REFUSED outright (§2.1b: a page field is certificate-fed
  by construction, so there is no rebuilding it blind; the analyzer's own
  furniture-fitted `field2` arms stay in).  Leave-one-out,
  stratified by source and band, Clopper–Pearson intervals, pre-registered
  bar (≥ 70% recovered in each stratum of ≥ 20 keys).
- **Stratified holdout** (`--holdout-stratified "Y:tiles/planek150=60,
  C:tiles/local150=20"`).  Production certificates withheld by (stream,
  source) in a deterministic seeded sample, all at once, attacked in ONE
  pass with no cascade.  Reports the recovered fraction per (stream,
  source, band) with exact intervals and the misses' minimum-unsat
  distribution.

**Parity** is the acceptance gate and the one that needs interpreting.
`--parity N` takes at least N production-certified tiles per stream,
stratified by band, and re-derives them with the DEFAULT arm
(`subtract+offset` with production's context) at L0/L1, the `sum` rule
only, and **re-roll OFF** — because a parity number measures what ONE
configuration re-derives, and spending the rest of the battery would make
the bar pass by changing the question.  The bar is ≥ 80% per stream.

Two things to read:

1. **`n_disagreeing_with_production` must be 0.**  Every re-derived
   certificate must equal production's own bits for that key.  That is not
   ground truth — it is leg 4 of the correctness argument, two independent
   paths certifying the same tile bit-for-bit.  A disagreement fails the
   control and is a finding.
2. **A rate below the bar is not automatically a capability failure.**
   Measured on sheet H's 60-tile C sample: the default gets 49/60 (81.7%);
   the whole 12-arm battery with all rules and the full ladder gets 56/60
   — and the recoveries are R moves of +0.005 to +0.018, a different halo
   or a different unmix head nudging a tile across the BP waterfall edge.
   Production won those tiles by throwing six tools and hundreds of
   attempts at each (one of them took 362 recorded attempts).  The C gap on
   H is an **attempt-count gap**, not a capability gap.  Sheet I is
   100/100/100 and sheet H's M is 20/20 because those planes are not in the
   waterfall regime.

For scale: parity 300 on sheet I with the default arm gives C 100/100, M
99/100, Y 100/100; without the blind offset and production's context it
gives C 50, M 60, Y 25.  The offset and the context are not optional
extras — they are what makes the plane read certify at all.

---

## 6. What "certified" means, and what verifies a close

**A certificate is a hard vector that satisfies every parity check of the
tile's code AND its CRC-32.**  Nothing else ever becomes one.  Any decoder
may PROPOSE — production BP, the analyzer's damped/offset/layered min-sum,
an enumerated flip hypothesis — but only syndrome+CRC certifies.
Bit-exactness is a law of the encoder, the keystream, the permutation and
the gate, never of the decoder.

**The gate has a price, and it is stated.**  Every CRC consultation costs
2⁻³².  Candidates are de-duplicated by codeword hash; exposure is the count
of DISTINCT codewords consulted, reported per run as `exposure_distinct`
and `exposure_expected_false`.  The run refuses to exceed E[false] ≤ 0.01
(about 4.3 × 10⁷ distinct consultations).  The CRC never enters any
elimination or reliability computation.  Sheet H's pass 3 spent 505
distinct consultations for 508 certificates: E[false] 1.2 × 10⁻⁷.

Certificates from a **list** rung (L4–L6) get the distinct verdict
`certified_list`.  They mint, cascade, reach the close and export like any
other — but every count that includes them is quarantined from a zero-wrong
CLAIM until the run's exposure is stated beside it.

**A close verifies on the envelope.**  The payload envelope is
`{sha256}{len:4B BE}{data}`, so a volume that closes has already checked
its own contents against a digest the EMITTER wrote inside the volume.
`close_volume` reports `verified` exactly when that check passed; the
analyzer consults no generation manifest and opens no payload during a run.

**The envelope is not the whole proof, and here is the measured reason.**
`fountain._ge_solve_gf2` eliminates rows past the rank to zero on the left
and never re-reads their right-hand sides, so a contradictory system
returns a solution at full rank and raises nothing; `Decoder._solve_block`
additionally short-circuits when all k systematic rows are present and
never consults a repair row at all.  Consequence, measured on sheet I: **a
poisoned REPAIR symbol leaves the close VERIFIED** — envelope passes,
payload byte-exact, and the volume still carries a certificate that cannot
have come from it.  The close cannot see it because it never reads it.

So the close runs a **fountain consistency check** (on by default): it
solves the source block exactly as `close_volume` does and re-encodes every
certified symbol from that solution through holo3's own generator rows.
With `have` symbols and K source rows, `have − K` of those comparisons are
free evidence — a basis row reproduces itself by construction and proves
nothing.  A clean check with `n_redundant` large is the truth-free
statement that every certificate the close consumed is right.  Sheet I:
5,883 symbols, K 5,277, 606 redundant, 0 inconsistent, 0.29 s.  Sheet H:
5,437 symbols, 160 redundant, 0 inconsistent, 0.66 s.

`--localize` turns the inconsistent case into named keys — when the
poisoned symbol is outside the SOLVE BASIS.  Measured end to end on sheet
H's union base (2026-09-04), by flipping three user bits of one
certificate in a copy of the run's `facts.npz`:

- the highest-esi repair symbol `(0, 52, 36, Y)` — outside the basis: the
  consistency check names exactly it (1 inconsistent of 160 redundant, 3
  bits), `localize` accuses it directly in 2 solves / 2.4 s, and the close
  on the 5,436 survivors is VERIFIED on sha `0ad329fb796d…`, exit 0;
- a repair symbol the solver RECRUITED into the basis (446 of H's 5,883
  symbols are missing, so repair rows are load-bearing): the source
  itself is wrong, 78 of the 160 redundant rows disagree by 3 bits each,
  and `localize` REFUSES — "the poisoned source row has no systematic
  certificate … finding it would cost O(K) solves and is not attempted",
  `poisoned_keys` empty, close `integrity_failure`, exit 2.  On sheet I,
  where the systematic rows are all present, the same class of poison is
  localizable by column consensus; on a below-K sheet like H it is not.
  An honest refusal, and a real limit of the tool.

Measured on sheet I: a poisoned repair symbol (3 bits) is caught, named,
localized in 2 solves / 0.51 s, corrected byte-exact, close verified.  A poisoned
systematic symbol (5 bits), where `close_volume` alone returns
`integrity_failure` with no key: 310 of 606 redundant rows disagree on one
common error pattern, consensus names the column with
`false_candidate_bound = 2.5e-90`, localized in 2 solves / 1.60 s,
corrected byte-exact, close verified on the emitted sha.

**In short, four things stand behind a certificate, none of them ground
truth:** the syndrome+CRC gate with its priced exposure; the payload
envelope's own sha at the close; the fountain's over-determination above K;
and two independent paths certifying one tile bit-for-bit.  Scoring against
a payload is an offline tool that works against any payload we hold —
including one the close itself recovered.  On sheet H that is not a
hypothetical: the five H ledgers scored against the payload the close
recovered from the union base, with no generation dir and nothing handed to
the instrument, give 1,025 certificates checked, 0 wrong, 0 false accepts.

---

## 7. Known limits

- **cmy8 only.**  Per-plane independent LDPC is what makes a plane
  decodable alone; cmy7 packs jointly and is out of scope.  The analyzer
  says so at startup.
- **L5 (ordered-statistics decoding) and L6 (perturbation restarts) are
  not built.**  The deciding measurement is the blind unsatisfied-check
  histogram at exit, published by every pass.  On sheet I it was bimodal —
  1,595 rung outcomes at unsat 0 → 590, 1–49 → 0, 50–99 → 3, ≥100 → 1,002
  — so a few-error rung had nothing to work on.  On sheet H it is not: 222
  exits at 5–9 and 234 at 10–49 out of 7,369, which is why **L4 (flip) was
  built** and does certify, thinly (2 on H's pass 2, 2 on pass 3).  L5/L6
  stay deferred until a histogram asks for them.
- **Memory.**  One analyzer at a time, never beside a holo3 decode.
- **The orderly stop is BUILT** (2026-09-07, `analyzer/stopdoor.py`;
  owed since 2026-09-04).  SIGINT/SIGTERM stop the pass at the next
  consistent point and the ledger is written with
  `stop_reason = interrupted` plus `keys_done`/`keys_skipped`, followed
  by the close and the exported snapshot (§2.4).  The readers honour it
  by construction: they read ROWS, an unreached key simply has none, and
  none of them validates `stop_reason`.  Two things are still true.  The
  LINGER: the pool finishes the keys already handed to workers, so the
  process runs on for about one key's time after the interrupt.  And the
  SCOPE — the door is the LADDER's (`ladder`, `read`), because it arms
  only where a pass has a progress sink; `analyzer controls` calls
  `fp.run` with none, so a `--null 300` or `--parity` run still loses
  its work on ctrl-C, exactly as this bullet used to say for every pass.
- **`field2_fit_workers` is WIRED** (2026-09-12, page-field plan A2; it
  used to default to 1 and hold the first target that needed the lazy
  pooled fit for ~6 minutes while every other worker waited on its key
  lock).  `fixedpoint._knobs_for` publishes the pass's own `--workers`
  into the knob bag, so the fit threads per lane by default; an explicit
  `--knob field2_fit_workers=N` still wins.  The lane reads share one
  process-wide bound (`field2.read_slots`), so concurrent (page, plane)
  fits cannot multiply the worker count.  The peak RSS of a sheet-H
  battery under all that is UNMEASURED — the 44.6 GB in §3 was read with
  the fit single-threaded, and one `/usr/bin/time -l` around the next H
  battery is what settles it.
- **A profile's knob DICT has no door.**  `--ctx-mode`, `--no-reroll`,
  `--reroll-only-arms` and every library knob are reachable
  (`--knob KEY=VALUE`), but the *composition* of a profile can only be
  replaced knob by knob.
- **`read` is documented as "the evidence stage only (no ladder)" and is
  not.**  `--rungs` is forced empty, but the re-roll path carries its own
  `reroll_rungs` (`L0`, `L1`), so re-roll rules ladder anyway — 72 rung
  outcomes in the blind histogram on a two-target smoke.  It is yield, not
  waste; the doc line is what is wrong.  `read` is also the one place the
  W8 precedence rule does not apply to `--rules`/`--rungs`: the command
  itself forces them, a `--profile` still overrides that, and an explicit
  `--rules`/`--rungs` on `read` is not re-applied over the profile
  (`--no-reroll` is the flag that actually silences `read`'s ladder).
- **The `auto` knobs cost wall time, and the patch family is
  RESAMPLER-bound.**  A full-auto `patch_score` walks the axes on the
  select fold per (lane, plane, state, tile).  B8's exact economies
  (bounds by arithmetic, a narrower window as a slice of a wider one, one
  Gram per population and half) took the synthetic world from 27
  extractions to 4 and 2.50 s to 1.12 s — about 5× a named spec rather
  than 10×, on the SMALLEST case, where the sampling axis collapses.  The
  floor underneath is `map_coordinates` at ~5.6 M points/s: one
  full-footprint extraction at 576 features is 2.6 s of resampling
  whatever else is removed, so 13 lanes × 2 patch arms is not a
  constant-factor problem.  Cost is not a constraint on a few hundred
  tiles (the ruling of 2026-09-06 says so), but it is why a union pass
  under `everything+patch` is priced in hours and an isolation run names
  its knobs explicitly.
- **A placed arm runs under the RUN's knob bag.**  `--reroll-only-arms`
  and the `*+pure` profiles place an arm in the re-roll; they cannot give
  it knobs of its own.  A pure path that wants a different train scope or
  sampling needs the two-pass `open-after` form (§2.4).
- **`score` counts a key once per ledger that carries bits for it**, so a
  tile certified in two passes appears twice in
  `n_certificates_checked` (1,794 rows → 1,025 checked on H).  Defensible,
  and now documented.
- **The corroboration half of independent agreement cannot fire with the
  current rule set.**  Independence is disjoint physical captures; of the
  five rules only `best` restricts to one capture and the other four use
  all of them, so `best`'s capture set is always a subset.  Measured on
  H7-pass3: 211 of 508 certified rows (41.5%) had two or more rules
  certify — the contradiction check's live population — and 0 carried a
  pair on disjoint captures.  The contradiction half is live now; the
  corroboration half needs a rule that certifies on a disjoint capture
  subset.
- **Historical contradiction incidence is unmeasurable.**  A row records
  `rungs["user_bits"]` once, for the certifying rule only; what a second
  rule's certificate said was never written down.  Only passes from here
  on can answer it.
- **The sheet-I fixture corpus MOVED** (2026-09-12, page-field plan
  A1b).  `/tmp/I/holo3-I-resume-3-run` is gone for good — it lived in
  `/tmp` — and 43 tests were dark behind `@needs_i_run` on main
  `83564aed` for that reason: every test of `score`'s `--run-dir`
  evidence leg, of `controls`, and of the export's real-snapshot half.
  `_analyzer_fixtures.I_RUN_DIR` now names
  `<evidence>/I-single-w8.run.51556`, a post-W2 sheet-I PRODUCTION run
  (e037's one 2400 capture; argv `--format
  L:c2-cmy8-r0700-p120-x1@3392x2368`, rasters, and three `PlaneField`
  facts keyed `(page, plane)` with `uncertainty_dots` — the fact the old
  corpus predates).  It is a DIFFERENT population (5,861 certificates
  against 5,880, one capture against four), so every literal those tests
  pin is re-pinned against it and carries the old number beside it.
  `<evidence>/analyzer/I-resume3/ledger.jsonl` survives, so the offline
  tests never depended on either.
