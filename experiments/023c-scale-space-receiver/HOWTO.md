# E023c production receiver how-to

`run_e023c.py` is the production E023c entry point. It ingests each native
physical capture once, derives a deterministic coarse-to-fine scale ladder
directly from that immutable raster, and runs the E021/E022/E023b acquisition
and payload path at every level. Lower levels may guide later levels, but a
derived view is never treated as another independent capture. Only
syndrome-and-CRC-certified payloads enter the cross-scale portfolio.

Run all commands below from the repository root with the repository Python
environment.

## Start a session

Every input image needs a stable, unique physical-capture ID. For one capture:

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  scratch/scans/c3-hp-1200-a.tiff \
  --dpi 1200 \
  --format e018b-v3-c3 \
  --pages 0 \
  --capture-groups c3-hp-1200-a \
  --state scratch/e023c/session.pkl \
  --out scratch/e023c/final.png \
  --report scratch/e023c/report.json \
  --diag scratch/e023c/diag \
  --diag-port 8023 \
  --diag-interval 3 \
  --fresh
```

`--dpi` is the true resolution of the supplied native scan, not the
resolution of the first derived view. `--pages` is a comma-separated list of
logical printed pages. `--fresh` deliberately starts a new state; omit it to
resume one.

For several independent physical captures, list images and IDs in the same
order:

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  scratch/scans/c3-hp-1200-a.tiff \
  scratch/scans/c3-hp-1200-b.tiff \
  scratch/scans/c3-hp-1200-c.tiff \
  --capture-groups c3-hp-1200-a,c3-hp-1200-b,c3-hp-1200-c \
  --dpi 1200 \
  --format e018b-v3-c3 \
  --pages 0 \
  --state scratch/e023c/session.pkl \
  --out scratch/e023c/final.png \
  --report scratch/e023c/report.json \
  --diag scratch/e023c/diag \
  --fresh
```

The number of IDs must equal the number of images, and IDs must be unique
within an invocation. The receiver completes or checkpoints one capture's
scale transaction before admitting the next capture. Scale views of the same
image retain that capture ID and are alternative decoding hypotheses, not
extra votes.

## Scale schedule

The default automatic schedule starts at `--minimum-ppc 2`, chooses a short
sequence of healthy intermediate resolutions, and always ends with the exact
native raster. PPC means scan pixels per printed cell. Typical automatic
examples are:

```text
C2 at 1200 dpi: 2, 4 ppc
C3 at 1200 dpi: 2, 3, 6 ppc
C3 at  600 dpi: 2, 3 ppc
```

If native sampling is already at or below the requested floor, the schedule
contains only native. Every non-native level is area-decimated directly from
native; levels are never recursively resized.

Use `--ppc-levels` to register an explicit experiment:

```sh
  --ppc-levels 2,3,9/2
```

Positive rational values are accepted, values above native PPC are rejected,
duplicates are removed, and native PPC is appended if omitted. `--minimum-ppc`
is ignored when an explicit ladder is supplied. The exact ordered ladder,
transforms, and resampler are pinned in the persistent state.

## Recovery modes and stopping

Without a manifest, E023c has no volume oracle and therefore processes every
planned level and capture. A manifest enables an early stop, but only after
the real fountain reconstruction succeeds and the reconstructed byte length
and SHA-256 match the registered volume. Rank, symbol count, or LDPC
certificate count alone never stops the receiver. A solvable reconstruction
with a length or SHA mismatch is a fatal integrity error.

A normal verified-recovery run is:

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  scratch/scans/c3-hp-1200-a.tiff \
  --capture-groups c3-hp-1200-a \
  --dpi 1200 \
  --format e018b-v3-c3 \
  --pages 0 \
  --manifest \
    experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_manifest.json \
  --state scratch/e023c/session.pkl \
  --out scratch/e023c/final.png \
  --report scratch/e023c/report.json \
  --diag scratch/e023c/diag \
  --fresh
```

The manifest must describe the exact format, layout, encoding, seed, rate,
geometry, and complete logical-page set selected by the command.

### Score an existing manifest-less state

Acquisition may deliberately start without a manifest and later stop before
all captures or scale levels are exhausted.  Certificate count alone does not
prove fountain recovery: edge certificates may be fountain-inert, and the
remaining symbols may be rank-deficient.  Audit the current immutable
certificate union with the matching emitted-sheet manifest:

```sh
env/bin/python experiments/023c-scale-space-receiver/score_e023c.py \
  scratch/e023c/session.pkl \
  experiments/018b-payload-sheet/build/e018b-c2-424e41a28257_manifest.json \
  --out scratch/e023c/fountain-score.json \
  --recovered-out scratch/e023c/recovered.bin
```

This scorer is read-only with respect to receiver state: it neither resumes
unfinished captures nor changes the registered state envelope.  It accepts a
manifest that was not registered during acquisition, checks the format, LDPC
rate, and logical pages against the state, then invokes the same production
fountain decoder, reconstructed-length check, and SHA-256 check used by the
in-run completion policy.  Exit 0 means `RECOVERED + SHA PASS`; exit 4 means
the volume is still open; exit 3 means reconstruction occurred but failed an
integrity check; configuration or state errors exit 2.  Recovered bytes are
written only when the fountain decoder returns a payload.

For the maximum-recovery measurement, continue through native even if the
volume is already verified and use the deeper per-frontier BP retry:

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  scratch/scans/c3-hp-1200-a.tiff \
  --capture-groups c3-hp-1200-a \
  --dpi 1200 \
  --format e018b-v3-c3 \
  --pages 0 \
  --manifest \
    experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_manifest.json \
  --detector-profile ctx-pava-v1 \
  --complete \
  --bp-retry \
  --state scratch/e023c/max/session.pkl \
  --out scratch/e023c/max/final.png \
  --report scratch/e023c/max/report.json \
  --diag scratch/e023c/max/diag \
  --fresh
```

`--complete` changes only the stopping request: it does not create a new
evidence lane or weaken certificate checks. `--bp-retry` asks every scale
whose certificate frontier changed to retry its remaining LDPC failures with
the bounded 150-iteration profile. It is intentionally explicit because it
costs more decoder work.

### Worked C2 two-capture maximum-recovery run

This is the exact 2026-07-17 offset-rescan-first protocol retained in
[`RESULTS.md`](RESULTS.md). It exhausts both 2 → 4 ppc ladders even though
the payload verifies during the first capture's coarse level:

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  scratch/e018b/hp-e018b-c2-hp-1200-page-2nd.png \
  scratch/e018b/hp-e018b-c2-hp-1200-page.tiff.png \
  --dpi 1200 \
  --format e018b-v3-c2 \
  --pages 0 \
  --capture-groups c2-hp-1200-rescan-offset,c2-hp-1200-original \
  --manifest \
    experiments/018b-payload-sheet/build/e018b-c2-424e41a28257_manifest.json \
  --detector-profile ctx-pava-v1 \
  --complete \
  --bp-retry \
  --state scratch/e023c-c2-hp-1200-two-capture/session.pkl \
  --out scratch/e023c-c2-hp-1200-two-capture/final.png \
  --report scratch/e023c-c2-hp-1200-two-capture/report.json \
  --diag scratch/e023c-c2-hp-1200-two-capture/diag \
  --diag-port 8023 \
  --panel-width 600 \
  --fresh
```

Capture order is part of the protocol. Marginal certificate counts are
order-dependent because the residual NeedMap skips keys certified by an
earlier barrier; do not interpret the second capture's 346 additions as its
standalone yield. Views derived from each scan share that scan's physical
capture ID and remain correlated alternative hypotheses.

The existing production qualifier can be used as a read-only numerical and
ground-truth probe of this retained state:

```sh
env/bin/python \
  experiments/023c-scale-space-receiver/qualify_e023c_cascade.py \
  scratch/e023c-c2-hp-1200-two-capture/session.pkl \
  experiments/018b-payload-sheet/build/e018b-c2-424e41a28257_manifest.json \
  --ground-truth \
    experiments/018b-payload-sheet/build/e018b-c2-424e41a28257_gt/K__e018b_c2_424e41a28257_field.npy \
  --ground-truth-sha256 \
    5c3d8553af9f24c02043668e13009c7b3fff058848ac02c37d3da4b4724688c6 \
  --diag scratch/e023c-c2-hp-1200-two-capture/diag \
  --baseline scratch/e023b-c2-hp-1200-two-capture/session.pkl \
  --label hp-c2-1200-two-capture-audit \
  --out scratch/e023c-c2-hp-1200-two-capture/qualification.json
```

Exit status 3 is expected. The frozen qualifier is intentionally
single-capture-only, so `exactly_one_capture` and its conditional
completed-level gate are false. Its core certificate, truth, state,
diagnostic, baseline, completion, fountain, and SHA gates pass; its displayed
scope and per-level feedback summaries retain single-capture presentation
semantics and must not be interpreted as multi-capture totals. Do not publish
that probe as `QUALIFIED_SINGLE_CAPTURE` or change the existing qualifier
merely to make it pass. The compact raw run report retained in Git is
[`E023C-C2-HP1200-TWO-CAPTURE-RUN.json`](E023C-C2-HP1200-TWO-CAPTURE-RUN.json).

## Resume, including exhaustive continuation

Repeat a command without `--fresh` to resume its atomic state. Images may be
omitted: unfinished capture paths are stored in the state and their bytes and
metadata are verified before work continues.

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  --dpi 1200 \
  --format e018b-v3-c3 \
  --pages 0 \
  --manifest \
    experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_manifest.json \
  --state scratch/e023c/session.pkl \
  --out scratch/e023c/final.png \
  --report scratch/e023c/report.json \
  --diag scratch/e023c/diag
```

An early-stopped state can later be driven through its skipped levels by
adding `--complete`:

```sh
env/bin/python experiments/023c-scale-space-receiver/run_e023c.py \
  --dpi 1200 \
  --format e018b-v3-c3 \
  --pages 0 \
  --manifest \
    experiments/018b-payload-sheet/build/e018b-c3-012d9e3ae693_manifest.json \
  --complete \
  --state scratch/e023c/session.pkl \
  --out scratch/e023c/final.png \
  --report scratch/e023c/report.json \
  --diag scratch/e023c/diag
```

`--complete` is deliberately not part of the numerical state envelope, so it
may be added for this continuation. All numerical options that *are* pinned
must still match the original command. In particular, repeat `--bp-retry` if
the state was created with it. A manifest is pinned too: repeat the same one
on resume, and do not try to add a stop oracle to a manifest-free state.

If a stored source moved, supply its new path with the same capture ID. The
receiver accepts the relocation only when the source bytes, size, raster
shape, dtype, DPI, and capture identity still agree. Re-submitting an already
exhausted capture is an exact no-op. Do not use `--fresh` unless discarding the
old transaction is intentional.

## Controlled ablations

These switches are for separate experiments, each with its own state file:

- `--no-lower-hints` disables pose/address continuation from productive lower
  levels.
- `--no-runner-ups` carries only accepted lower-level placements, not the
  bounded retained runner-up hypotheses.
- `--no-forward-refine` disables refinement of later sampling geometry from
  already certified payloads.
- `--no-bch-first` disables the BCH-first pilot acquisition route.
- `--detector-profile NAME` selects a registered payload detector; the
  production default is `ctx-pava-v1`.
- `--ppc-levels ...` replaces the automatic scale-selection policy.
- Omitting `--bp-retry` measures the normal bounded decoder path.

The scale plan, format and pages, DPI, detector profile, pilot-search
configuration, manifest identity, continuation/runner-up/refinement/retry
policy, implementation fingerprints, and evidence policy are all pinned in
the state envelope. A mismatch fails closed instead of silently changing an
experiment during resume. Output, report, cache, diagnostic path, diagnostic
port, render interval, panel width, and `--complete` are observer or execution
choices and may change between invocations.

Source-level diagnostics instrumentation is covered by those implementation
fingerprints even when equivalence tests prove it numerically neutral.
Consequently, states made before the live window/attempt diagnostics revision
cannot be resumed with this revision: start a fresh state and keep the old
state/report as pinned historical evidence. Do not edit or repin a state to
bypass this check.

## State, cache, report, and diagnostics

- `--state` is the authoritative, atomically replaced receiver transaction.
  It contains capture identities, every registered scale lane, attempts,
  dependencies, conflict-checked certificates, checkpoints, and completion
  records.
- `--cache-dir` selects the derived-view PNG cache. The default is next to
  the state with a `-views` suffix. Cached views are exact, direct-from-native
  products and are recorded by content identity; they are not authoritative
  evidence by themselves.
- `--report` writes a compact JSON observer report after commits. If omitted,
  it uses the `--out` name with a `.json` suffix.
- `--out` writes the final four-pane diagnostic view. For multiple logical
  pages, their page frames are stacked into one PNG.
- `--diag DIR` publishes progressive per-page frames, JSON sidecars, a live
  status page, scale-ladder state, active work, and the final
  `session_complete` frame. `--diag` without a value uses the experiment's
  build directory. `--diag-port` selects the live server port,
  `--diag-interval` sets the maximum transient PNG refresh rate in seconds
  (default `3`), and `--panel-width` controls diagnostic layout.

The browser deliberately has a faster text path and a bounded image path.
Its status/header advances for every E022 window stage and every LDPC/BP
attempt. Full pilot combination and four-pane PNG rendering happen at the
selected interval, plus causal milestones and the first window/attempt. Thus
the header may be a fraction of a second newer than the image; lowering
`--diag-interval` trades receiver wall time for more animation, while `0`
renders every event and is intended only for small diagnostic fixtures.
The interval begins when the preceding PNG render finishes, so a slow render
cannot cause every immediately following event to render too.

During E022, pane A outlines the active scan window in cyan and, after the
local FFT/phase fit, draws the two fitted Jacobian basis axes. The header
reports region, window/queue ordinal, subdivision depth, route, anchor count,
angle, pitch, and terminal outcome. Pane B outlines a current canonical-page
candidate in magenta once one exists. Context/PAVA and certificate-driven
pose refinement get their own status records. During payload decoding, pane D
retains the geometric work-plan overlay and marks the latest completed LDPC
attempt; the header reports coverage, informative samples, effective checks,
BP iterations, state, syndrome, and CRC. `status.json` exposes the same
detached metadata for automated observation.

Diagnostics and final-image delivery are observers. A disk or live-server
failure is reported but does not roll back a valid receiver commit. The state
and its authoritative digest, not a PNG or JSON observer artifact, decide
what was recovered.

Production qualification is documented in
[`QUALIFICATION.md`](QUALIFICATION.md).
