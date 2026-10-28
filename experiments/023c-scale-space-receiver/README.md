# Experiment 023c — coarse-to-fine scale-space receiver

**Status (2026-07-17): production cascade built and single-capture
qualified on one HP-1200 scan in each of the C3 and C2 formats.**

E023c is the production coarse-to-fine entry point for E021, E022, and
E023b.  It takes each physical scan at its true native resolution, derives a
short ladder of lower-resolution views directly from that immutable raster,
and processes the ladder from roughly two scan pixels per printed cell to
native resolution.

The goal is intentionally narrow: recover as many payload tiles as possible
with a simple, deterministic acquisition pipeline.  A lower level supplies
cheap geometry and certified facts to the next level; a finer level always
has to pass the normal gates against its own pixels.  Correlated scale views
never masquerade as independent scans.

On the qualified HP C3/1200 capture, the automatic 2 → 3 → 6 ppc cascade
recovers **754** ground-truth-correct certificates with no conflicts.  It is
a strict +7-certificate superset of the qualified-code 2 → 6 control and a
+24-certificate superset of the historical native E023b result.  See
[`RESULTS.md`](RESULTS.md) for cost and scope.

The additional HP C2/1200 2 → 4 ppc run recovers **1,438** correct,
conflict-free certificates: 1,363 useful fountain symbols and 75 inert edge
addresses.  It reaches rank 737/737 and verifies the 192,160-byte payload
SHA.  These are two format-specific single-capture results, not a
cross-scanner or cross-print claim.

The normative algorithm and state contract are in [DESIGN.md](DESIGN.md).
Measured but unbuilt placement/frontier improvements are kept separately in
[FUTURE_WORK.md](FUTURE_WORK.md), so they cannot be mistaken for current
receiver behavior.

## Receiver ownership

E023c changes orchestration, not the responsibilities of the lower layers:

| layer | responsibility |
|---|---|
| E021 | segment the current scale raster into candidate regions |
| E022 | fit poses, identify pilot windows, and enforce current-pixel pilot gates |
| E023b | sample payload, run context/PAVA, freeze one-owner evidence, and certify LDPC+CRC tiles |
| E023c | construct the scale ladder, carry bounded hints forward, maintain independent scale lanes, union certificates, persist/resume, and optionally test volume completion |

One physical capture is completed coarse-to-fine before the next capture is
admitted:

```text
native capture
    |
    +-- direct area view at lowest useful ppc
    |       E021 -> E022 -> E023b lane -> certificate barrier
    |
    +-- direct area view at next ppc
    |       lower hints + prior certificates
    |       E021 -> E022 -> bounded pose refine -> E023b lane -> barrier
    |
    `-- native view
            lower hints + prior certificates
            E021 -> E022 -> bounded pose refine -> E023b lane -> barrier
                    |
                    `-- optional real fountain reconstruction + SHA check
```

Every derived view is made directly from the native raster.  Views are never
resized from an earlier view, so rounding and blur cannot accumulate through
the ladder.

## Scale ladder

Resolution is expressed as scan pixels per printed cell (ppc):

```text
native_ppc = native_dpi * cell_factor / 600
```

The automatic schedule begins at exactly `--minimum-ppc` when the source can
support it, approximately doubles through inexpensive area reductions, and
always ends at native resolution.  It prefers exact integer box factors when
that does not make the ladder unnecessarily sparse.  Examples for the
default minimum of 2 ppc are:

| print | scan | automatic ppc ladder |
|---|---:|---|
| 2c | 1200 dpi | 2, 4 |
| 3c | 1200 dpi | 2, 3, 6 |
| 3c | 4800 dpi | 2, 4, 8, 12, 24 |
| 3c | 600 dpi | 2, 3 |

If native resolution is already at or below the requested floor, only the
native level is used.  E023c never upsamples.  An explicit increasing ladder
may be supplied with `--ppc-levels`; native ppc is appended if omitted.

Integer reductions reproduce the E018 box-reduction operation order.  Other
ratios use a deterministic separable rational-area integrator; uint8 inputs
use exact overlap numerators and exact ties-to-even rounding.  Pixel-centre
and affine-pose transforms are exact rational transforms, including the
half-pixel offset; see [DESIGN.md](DESIGN.md#coordinate-and-pose-transfer).

## What crosses a level barrier

Three different objects cross from a completed lower level to a finer one:

1. Accepted E022 poses, transformed through native coordinates.
2. At most two authenticated losing address/pose candidates per unresolved
   region by default.  These come from E022's `window_audit` replay ledger.
3. Globally certified payload tiles, used both as an already-solved frontier
   and, where sufficient, as exact printed labels for bounded pose
   refinement.

The nearest productive lower level is preferred.  An empty intermediate
level does not erase a useful older hint.

All hints are proposals.  E021 still segments the current view and E022
still refits and validates against current pixels.  A retained losing
candidate cannot create a placement by itself.  Certificate-driven
refinement may alter only continuous pose; page, address, orientation, and
pilot evidence remain frozen, and the refined pose must pass the existing
training/held-out gates before E023b resamples the current view.

## Independent scale lanes and certificate union

There is one persistent E023b receiver lane per ppc level.  Independent
physical captures accumulate within the same lane.  Deterministic scale
views of one capture use the same physical `capture_id` and are never summed
as independent LLR observations.

Scale lanes meet only at the certificate boundary:

- a tile must pass LDPC syndrome and CRC in its own lane;
- equal certificates merge their lane/capture provenance;
- conflicting certified bits for one tile are fatal;
- uncertified hard decisions and LLRs never cross lanes.

This keeps the useful list-decoder property of native/decimated branch union
without inventing independence between correlated rasters.

The receiver also maintains a logical residual **NeedMap**.  Its payload
solved set is the authoritative certificate union; pilot needs come from the
latest committed pilot summary.  The NeedMap is derived at barriers rather
than stored as a second source of truth.  In the current implementation it
drives accounting, diagnostics, completion, and decoder skip decisions.  It
does not hard-mask E021/E022 page search: solved payload can still anchor an
unresolved neighbour, pilot/pose need is not identical to payload need, and
windows overlap.

## State, replay, and resume

`--state` is an authoritative, atomic checkpoint, not a result cache.  The
clean E023c schema is intentionally incompatible with the earlier factorial
prototype.  It records, among other things:

- exact format, seed, pages, native DPI, ppc plan, detector profile, search
  policy, optional manifest identity, and numerical implementation hashes;
- source hash, size, raster identity, true DPI, path, and physical capture id;
- every capture/level status and barrier checkpoint;
- complete opaque E023b lane sessions, including E021/E022 replay substrate;
- attempt provenance, contributing physical captures and evidence digests;
- certificate dependencies and the conflict-checked global union;
- verified volume-completion state, if requested.

Writes use a same-directory temporary file, `fsync`, and atomic replacement.
Loads authenticate the envelope, semantic state digest, lane digests, and
cross-object invariants.  Algorithm-consumed diagnostics such as E022's
`window_audit` are semantic.  Observer-only diagnostic frames and timings
are explicitly excluded.

An exact duplicate capture is a no-op.  On restart, persisted unfinished
captures are resumed before new captures are admitted.  If a manifest caused
an early stop, `--complete` can resume the skipped finer levels from the
stored source path without re-supplying the image (or from a replacement path
whose bytes authenticate to the same source).

Dependencies obey a strict barrier rule: a level may depend only on
certificates committed at an earlier `(capture, scale)` position.  Same-level
results cannot feed themselves.

## Optional completion policy

Without `--manifest`, E023c exhausts every scheduled level and capture.  With
a compatible manifest it performs a read-only completion check after each
level:

1. validate every certified tile and its symbol capacity;
2. extract the actual fountain symbols;
3. invoke the real fountain decoder;
4. record rank and shortfall per block;
5. accept completion only when reconstructed length and SHA-256 match.

Symbol count or apparent rank alone is not a stop condition.  A recovered
volume with the wrong digest is a fatal integrity error.  Normal mode marks
remaining levels `skipped_volume_verified` after verified recovery;
`--complete` continues through native resolution.  Fountain state never
feeds pilot, pose, payload, or LDPC acquisition.

`score_e023c.py` applies this same production decoder and integrity gate to
the certificate union of an existing state, including a state acquired
without a registered manifest or stopped with unfinished captures.  It is a
read-only outer-layer audit and cannot resume or mutate acquisition.  See
`HOWTO.md` for its command and exit-status contract.

## Diagnostics

`--diag [DIR]` starts the same live four-pane receiver view used by E022/E023b,
extended with scale and portfolio state:

- **A** — current derived raster and E021 regions;
- **B** — current E022 placements and pose state;
- **C** — final/accumulating pilot sheet, grouped by physical capture so
  multiple scale views do not count as independent votes;
- **D** — current payload/LDPC work plus the global certified portfolio and
  volume progress.

Frames are published at level-open, E021 completion, each E022 region,
pilot-final, payload emission, owner freeze, BP batch, fountain check, level
commit, capture commit, and session completion.  Page tabs remain separate.
Diagnostics are observer-only: rendering or HTTP failure cannot change or
roll back authoritative state.  When `--out` is requested and the retained
scan/view path remains readable, the final PNG is rebuilt from committed
state even for a no-op/resume invocation and even when live diagnostics are
off.

## Basic invocation

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  scan-a.tiff scan-b.tiff \
  --dpi 1200 \
  --format e018b-v3-c2 \
  --pages 0 \
  --capture-groups scan-a,scan-b \
  --state scratch/e023c/session.pkl \
  --out scratch/e023c/final.png \
  --report scratch/e023c/report.json \
  --diag scratch/e023c/diag \
  --diag-port 8023
```

Useful experimental controls are:

- `--ppc-levels 2,3,6` — explicit ladder; native is appended if necessary;
- `--minimum-ppc 2` — automatic ladder floor;
- `--no-lower-hints` — remove accepted and runner-up continuation hints;
- `--no-runner-ups` — keep accepted lower placements but remove losing
  candidates;
- `--no-forward-refine` — disable certificate-driven pose refinement;
- `--bp-retry` — run a max-150 retry on each changed per-scale lane frontier;
- `--manifest MANIFEST.json` — enable real outer-volume verification;
- `--complete` — continue to native after verified recovery;
- `--fresh` — start a new incompatible state at the requested path.

The envelope authenticates policy choices, so changing numerical options
requires a fresh state rather than silently mixing runs.

## Qualification status

The cascade has unit and integration coverage for scale construction,
coordinate transforms, current-pixel gates, lane isolation, residual
scheduling, certificate union, state authentication/resume, completion
policy, and diagnostic observer semantics.  The checked real-scan report is
[`E023C-CASCADE-HP1200.json`](E023C-CASCADE-HP1200.json): all 754
certificates match frozen printed truth, the actual fountain payload and SHA
verify, the automatic schedule strictly supersets its qualified-code endpoint
control, and the final diagnostic frame authenticates the committed state.

The checked numerical reports are frozen to run commit `bdc9c54`.  Later
commit `5ee753a` adds live observer callbacks and changes exactly three
full-source fingerprints.  Tests pin that delta and prove observer-on/off
timing and authoritative-state parity; this is compatibility evidence, not a
fresh blind numerical qualification.  Any additional fingerprint delta
requires review or rerun.

The additional checked C2 report is
[`E023C-CASCADE-HP1200-C2.json`](E023C-CASCADE-HP1200-C2.json): the automatic
2 → 4 ppc schedule contributes 1,310 + 128 = 1,438 certificates, all correct
and conflict-free; the real fountain decode and payload SHA verify.  The
pre-retention audit bytes had SHA-256
`1be5d720da62e8b1352f43873597855a99343f86a34f5b6cff123481b68405a9`.
That source audit's observer-only scope text incorrectly named C3. The
profile-aware checked C2 report corrects the label without changing the
state/numerical result and has SHA-256
`574f44c141e70c1fe7a806a9e20dfa4650e592242e6a98adc1b3197257474d6d`.

This qualifies one HP 1200-dpi physical capture in each of C3 and C2.  It
does not claim cross-scanner, cross-print, 600-dpi, or multi-capture
generalization.  The read-only qualifier opens truth only after acquisition
and certificates are frozen.

## Legacy factorial artifacts

The first E023c implementation tested a different, bounded NN/DD/ND/DN
geometry-versus-sampler factorial.  It was useful causal evidence, but it is
not this receiver and its results are not qualification anchors for the
coarse-to-fine cascade.

The following files are retained as historical evidence:

- `qualify_e023c.py`
- `E023C-QUALIFICATION.json`
- `SERIAL-PARALLEL.json`

Production cascade code is `run_e023c.py`, `scale_space.py`, `cascade.py`,
`cascade_state.py`, `completion.py`, and `e023c_diag.py`; its qualification
entry point is `qualify_e023c_cascade.py`.  [HOWTO.md](HOWTO.md) documents
production invocations rather than the legacy factorial.

## E024 boundary

E023c performs one bounded forward pose-refinement opportunity at a finer
level using certificates from an earlier barrier.  It does not run a
fixed-point feedback loop, replay lower levels, recalibrate detectors from
decoded payload, or globally resegment after feedback.  The state preserves
the dependency graph, raw lane sessions, and losing-candidate audit needed
to investigate those operations cleanly in E024.

An experimental retained adapter at
`experiments/024-feedback-receiver/e023c_e024_bridge.py` now demonstrates a
safe post-pass composition: export the complete embedded E023b lanes, build
their exact conflict-checked certificate union with the official merger, run
one independently persisted union-seeded E024 state per scale lane, and
audit the final portfolio.  Scale-view LLRs are never combined.  On the HP
captures this changes C3 754→754 and C2 1,438→1,439, the latter by one useful
tile `(0,18,26)`.  Both v2 audits are `QUALIFIED_BOUND` with exact
export/official-union/baseline binding, all non-truth inputs replayed and
frozen before hashed ground truth, and zero conflict/wrong gates; hashes are
`2b70cdaa...75a4` (C3) and `8f54ac71...11f2` (C2).  This is measured
experimental plumbing, not an integrated
E023c→E024 production mode or a backward replay loop.
Adapter contract and commands:
`experiments/024-feedback-receiver/E023C-BRIDGE.md`.
