# analyzer — operator's manual

The analyzer is a standalone research instrument that attacks the residue
of a finished holo3 decode: every tile-stream the production receiver left
uncertified.  It re-reads those tiles' pixels with a wider battery of
unmixing, registration, calibration and decoding arms than production
carries, and mints a certificate only when a hard vector satisfies every
parity check of the tile's code and its CRC-32 — the same gate production
uses, so its certificates are production's certificates.  It changes
nothing under `holo3/`, `src/` or `measure/`: holo3 code is called, and the
analyzer's harvest goes back to production through a snapshot a `--resume`
reads.

Design: `analyzer/DESIGN.md`.  Build record and dated changelog:
`analyzer/PLAN.md` (§6).  Measurement records: `GAPS-2026-09-03.md` (the C
parity gap), `FIELD2-2026-09-03.md` (the page field), `REVIEW-2026-09-03.md`.

---

## 1. Footing

Run everything from the repo root, as a module, with the root virtualenv —
free-threaded CPython 3.14 (`python3.14t`), threads and no processes,
because the snapshot is loaded once per process and shared:

```
env/bin/python -m analyzer --help
```

On machine 4 the venv is named `env314t`; substitute it everywhere below:

```
env314t/bin/python -m analyzer --help
```

Nothing is installed — `analyzer/`, `holo3/` and `measure/` import from the
repo root.  Tests:

```
env/bin/python -m pytest analyzer/tests -q
env/bin/python -m pyflakes analyzer/
```

Artefacts land in `--out` (default `scratch/analyzer/<run dir name>`).
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
    --src-run-dir <volume>/holo3-H7-run \
    --out scratch/analyzer/H7-mirror \
    --tiff-dir scratch
```

`argv`, `report.json`, `events.jsonl` and `facts.npz` are copied when
absent.  `report.json` is the checked-against truth (capture ids,
`levels_ppc`, `shape_yx`); a disagreement REFUSES.  Idempotent: a complete
capture directory is skipped without hashing.  Sequential by ruling, not by
limitation — one capture holds its whole native raster (sheet I's 4800 is
6.8 GB) and the memory budget forbids doubling that.

Cost: 18 s and 2.4 GB peak for sheet J's single 28064×20416×3 capture.

### 2.2 Census — coverage, bands, residue (no pixels)

```
env/bin/python -m analyzer census \
    --run-dir scratch/analyzer/H7-mirror \
    --out scratch/analyzer/H7
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
env/bin/python -m analyzer census --run-dir scratch/J-run.54028 \
    --format-ref L:c2-cmy8-r0547@53x37 --out scratch/analyzer/J
```

### 2.3 Controls (a run without them is not a result)

```
env/bin/python -m analyzer controls \
    --run-dir scratch/analyzer/H7-mirror \
    --parity 100 --null 5 --frame-null 3 --withhold-run-mints \
    --out scratch/analyzer/H7-controls
```

Exit 1 when any control's `passes` is False.  See §5 for how to read them.

### 2.4 The pass

The everyday configuration is the `everything` profile — every arm on every
lane, all four rules, the full ladder, the wide halo, and the re-roll across
the unselected arms at L0–L2:

```
env/bin/python -m analyzer ladder \
    --run-dir scratch/analyzer/H7-mirror \
    --targets residue \
    --profile everything \
    --fixed-point --max-generations 8 \
    --workers 8 \
    --out scratch/analyzer/H7-pass3
```

`--fixed-point` is what turns the cascade on (without it `max_generations`
is 1, and the cascade was worth +52 of 331 certificates on sheet I's
first-run residue and 234 of 508 on sheet H's).  `--profile` is applied
after the other flags and records itself in the ledger header as
`knobs_from = "profile:<name>"`.

`everything+field2` adds the certificate-anchored per-lane page-field arms
(`field2c`) on top.  They are the expensive ones — a refit per lane per
generation — which is why they have their own profile name:

```
env/bin/python -m analyzer ladder … --profile everything+field2 …
```

If you run `everything+field2`, pass the fit worker count too; the lazy
pooled fit otherwise blocks the first target that needs it for about six
minutes (Y, 22 lanes) while every other worker waits on its key lock.
There is no CLI flag for it yet — it is a library knob
(`knobs={"field2_fit_workers": N}`), which is a gap, not a design.

Other profiles: `wide-halo` (halo 48/48/32 — the highest-yield single
change measured, not adopted as default because it lost one tile on the
sample it was chosen from), `battery`, `split-branches` (the pre-amendment
calibration, for a control run that wants it).

Smoke a configuration with `--limit N` before committing hours to it.

**What you see while it runs** (stderr, since 2026-09-04 — the first machine 4
pass printed its header line and then nothing for its whole length):

```
targets 429  arms 14  rules ('sum', 'best', 'platt', 'corr')  rungs (...)  workers 14
generation 0: 429 pending (0 re-attacks), certificates so far 0, elapsed 0:00:00
  generation 0: 10/429 done, +1 certified, 41.3 s/key, elapsed 0:06:53, remaining ~2:53:00 (last (0, 3, 17, 'Y'))
  generation 0: 20/429 done, +2 certified, 38.9 s/key, elapsed 0:12:58, remaining ~2:39:10 (last (0, 4, 2, 'C'))
  …
generation 0 done: +37 certificates (total 37), 2 refused, 2:41:05
generation 1: 88 pending (61 re-attacks), certificates so far 37, elapsed 2:41:05
  …
pass done: 41 certificates over 3 generation(s) in 3:02:44; writing the ledger
```

`s/key` is wall time per finished key over the generation, so with 14
workers it is roughly 14 times a key's own cost; `remaining` is that rate
extrapolated over the keys still pending in THIS generation, and says
nothing about the generations the cascade will add.  The first key that
needs the page field blocks about six minutes, single-threaded, before
the first tick (`--progress-every N` sets the tick cadence; 0 keeps the
generation lines only).  **SIGUSR1** (`kill -USR1 <pid>`) or **ctrl-T**
(SIGINFO, macOS/BSD) prints a status line at any moment:

```
status: generation 0, 133/429 done, certificates 12 (+12 this generation), exposure 3,904 distinct, elapsed 1:31:02
```

There is no stop door.  Ctrl-C ends the pass with NOTHING written — the
ledger is produced only when the fixed point is reached — and the pool
first finishes the keys already handed to workers, so the process lingers
for one key's time after the interrupt.  A stop that wrote the partial
ledger is a separate line of work (§7).

Outputs in `--out`: `ledger.jsonl` (one row per tile-stream, with nested
per-(lane, arm), per-rule and per-rung records, and a header), `ledger.md`
(the summary), `close.json`, `payload.bin` when the close recovers bytes,
and two PNG maps per plane (`--no-maps` to skip).

### 2.5 The incremental pass

A second pass should not re-earn the first pass's certificates, and it must
not re-copy tens of gigabytes of rasters to say so.  Build a run dir that
SYMLINKS the base run's rasters and `events.jsonl`, copies `report.json`
and `argv`, and takes an exported snapshot as its `facts.npz`:

```
env/bin/python -m analyzer export-facts \
    --snapshot scratch/analyzer/H7-mirror/facts.npz \
    --ledger scratch/analyzer/H7-pass3/ledger.jsonl \
    --out scratch/analyzer/H-export5/facts.npz

env/bin/python -m analyzer union-base \
    --run-dir scratch/analyzer/H7-mirror \
    --facts scratch/analyzer/H-export5/facts.npz \
    --out scratch/analyzer/H7-mirror-union
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

```
env/bin/python -m analyzer ladder \
    --run-dir scratch/analyzer/H7-mirror-union \
    --targets "open-after scratch/analyzer/H7-pass5/ledger.jsonl" \
    --profile everything+field2 \
    --fixed-point --workers 8 \
    --out scratch/analyzer/H7-pass6
```

`open-after LEDGER[,LEDGER]` selects the covered, uncertified keys after
the union of those ledgers AND the run's own facts.  On a union base the
second half is already true, so the flag is what makes a pass targetable
from ledgers that have not been exported yet.

### 2.6 The close

```
env/bin/python -m analyzer close \
    --run-dir scratch/analyzer/H7-mirror-union \
    --localize \
    --out scratch/analyzer/H7-close
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
    --snapshot scratch/analyzer/H7-mirror/facts.npz \
    --ledger scratch/analyzer/H7-pass3/ledger.jsonl \
    --ledger scratch/analyzer/H7-pass5/ledger.jsonl \
    --out <volume>/holo3-H-analyzer-facts-4/facts.npz
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
env/bin/python -m holo3 decode \
    scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-1200dpi-a.tiff \
    scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-1200dpi-b.tiff \
    scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-2400dpi-a.tiff \
    scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-2400dpi-b.tiff \
    scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-4800dpi-a.tiff \
    scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-4800dpi-b.tiff \
    scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-4800dpi-c.tiff \
    --dpi 1200 --dpi 1200 --dpi 2400 --dpi 2400 \
    --dpi 4800 --dpi 4800 --dpi 4800 \
    --format L:c2-cmy8-r0850-p120-x1@3392x2368 \
    --max-pages 1 \
    --plane-fields --complete --workers 14 \
    --out scratch/holo3-H8.bin \
    --run-dir scratch/holo3-H8-run \
    --diag 8023 --snapshot-every 30 \
    --resume <volume>/holo3-H-analyzer-facts-4/facts.npz
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
    --ledger scratch/analyzer/H7-pass3/ledger.jsonl \
    --ledger scratch/analyzer/H7-pass5/ledger.jsonl \
    --payload scratch/analyzer/H7-close/payload.bin \
    --out scratch/analyzer/H7-score
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
    --ledger scratch/analyzer/H7-pass4/ledger.jsonl \
    --payload scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm/payload-counting.bin \
    --gt-dir scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm \
    --run-dir scratch/analyzer/H7-mirror-union \
    --limit 3 --maps \
    --out scratch/analyzer/H7-score-full
```

`--limit` bounds the evidence recomputation only; certificates and rungs
are always all of them.  The CLI exits 2 on any `wrong` or `false_accept`,
with every disagreeing key named in `score.md`.

The reader is streaming (`read_header` + `iter_rows`): a first cut that
materialised rows reached 26 GB of RSS before it was killed, because sheet
H's passes are 2.6–5.8 GB of JSON each and five together are 18 GB.

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
| `ladder --profile everything+field2` (pass 4) | 3.5 h | 48.6 GB |
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

Rough per-unit cost: about 1.0 s per (key, lane) for the full battery.

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

**Header.** seed, workers, arms, rules, rungs, `targets_from`,
`knobs_from`, `non_blind`, `generations_run`, `exposure_distinct` and
`exposure_expected_false`.

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
env/bin/python -m analyzer report scratch/analyzer/H7-pass5/ledger.jsonl
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
  `tiles/<stage>` strings — and try to win them back with the frame, the
  plane fields and the pooled context rebuilt without them.  Leave-one-out,
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
- **No orderly stop.**  A pass writes its ledger at the fixed point only;
  ctrl-C loses everything the generation so far minted.  holo3's engine
  has the SIGINT/SIGTERM door (facts written, run finished as `open`);
  the analyzer has only the STATUS doors (SIGUSR1, ctrl-T).  Building the
  stop means writing a partial ledger with a header that says so, which
  the readers (`close --ledger`, `export-facts`, `score`) would then have
  to honour — not built, 2026-09-04.
- **`field2_fit_workers` has no CLI flag** and defaults to 1; inside a
  `fixedpoint` run the lazy pooled fit blocks the first target that needs
  it for ~6 minutes.  So do `--reroll` and `--ctx-mode local5`, which exist
  as config knobs only.
- **`read` is documented as "the evidence stage only (no ladder)" and is
  not.**  `--rungs` is forced empty, but the re-roll path carries its own
  `reroll_rungs` (`L0`, `L1`), so re-roll rules ladder anyway — 72 rung
  outcomes in the blind histogram on a two-target smoke.  It is yield, not
  waste; the doc line is what is wrong.
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
- **The sheet-I run dir `/tmp/I/holo3-I-resume-3-run` is gone** (it lived
  in `/tmp`).  46 of the suite's 48 skips are its — every test of `score`'s
  `--run-dir` evidence leg, of `controls`, and of the export's real-snapshot
  half.  `scratch/analyzer/I-resume3/ledger.jsonl` survives, so the offline
  tests still run.  Rebuilding the dir needs a holo3 resume.
