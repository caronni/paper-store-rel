# E023b.1 algorithm arms: adaptive BP and context + PAVA

Status: frozen before qualification; implemented and qualified 2026-07-16.
Sections 1--4 are the preregistered specification and were not retuned after
the result was read.  E023b.0 remains the qualified orchestration and
numerical baseline described by `README.md`.

The experiment is a 2 x 2 factorial:

| detector | decoder | short name |
|---|---|---|
| `pava-v1` | baseline BP only | baseline |
| `pava-v1` | baseline BP, then explicit adaptive retry | BP |
| `ctx-pava-v1` | baseline BP only | context |
| `ctx-pava-v1` | baseline BP, then explicit adaptive retry | combined |

Neither arm changes E021 segmentation, E022 placement, the LDPC code, the
rate, the attempt floor, the CRC certificate, scan independence, or the
one-owner-per-scan rule.  Fountain/rank/stopping logic remains out of scope.

## 1. State and compatibility rules

The detector profile is frozen in the receiver-session envelope.  A state
cannot append scans under a different detector profile.  The profile is also
recorded in the scan record.  Rows from adopted context regions carry
`ctx-pava-v1`; a rejected region deliberately retains exact `pava-v1` rows,
with the selected profile and rejection decision retained by the scan and
`ContextFit` sidecar.  The ordinary loader continues to fail closed across
implementation or schema changes, including changes to the production E023b
entry-point harness.

The two detector profiles are:

- `pava-v1`: the exact qualified E023/E023b.0 window-mean -> per-window PAVA
  path;
- `ctx-pava-v1`: `pava-v1` followed by the bounded, held-out-gated context
  correction in section 3.

Adaptive BP is deliberately an explicit state action, not part of the scan
ingestion profile.  The action can be invoked repeatedly; an unchanged
evidence identity spends no second attempt.  This avoids making every
intermediate acquisition prefix pay the extended decoder cost and makes the
operator's decision to spend additional CRC exposure visible in the ledger.

Qualification may read the frozen E023b.0 rich states only through a
qualification-only loader pinned to their complete file SHA-256 and legacy
implementation fingerprint.  Production loading is not weakened.  The
stored raw means, page coordinates, poses, and pilot labels are sufficient
for exact same-pose recalibration; changing a pose would still require the
source TIFF.

## 2. Adaptive BP retry

### 2.1 Baseline attempt

The normal decoder remains byte-identical:

- normalized min-sum, `alpha = 0.8`, at most 60 iterations;
- after syndrome failure, one fresh exact sum-product pass at at most 60
  iterations;
- unchanged shortening, attempt floor, syndrome, CRC, and extraction rules.

Its ledger profile is `<rate>/decode_tile-max60-alpha0.8`.

### 2.2 Retry frontier

The explicit retry action visits tiles in sorted `(page, tile_y, tile_x)`
order.  A tile is eligible exactly when:

1. its current state is `attempted_failed`;
2. its most recent invoked baseline attempt for the current evidence frontier
   also ended `attempted_failed`;
3. no max-150 attempt with that evidence digest has already been ledgered.

The most recent invoked baseline attempt is authoritative because E023b's
append schedule ends each scan with the changed full-prefix union when one
exists.  The retry reconstructs exactly the contributing scan or union named
by that attempt; it does not choose a post-hoc scan subset.

Qualification-hardening clarification: “current evidence frontier” means the
newest transaction-final baseline *evaluation*, whether or not it invoked the
decoder.  Eligibility does not search backward through a newer below-floor
evaluation to find an older failure.  With two or more contributing scans,
the transaction-final row is the full-prefix union, never the intermediate
current-scan row.  State validation derives that frontier from the frozen scan
records and rejects reordered or omitted rows before a retry can run.

### 2.3 Retry decoder and ledger

The retry calls the same `decode_tile` with `max_iters = 150` and
`alpha = 0.8`.  Thus its worst case is 150 min-sum plus 150 sum-product
iterations, not 150 total.  It is a new decoder/CRC exposure with profile
`<rate>/decode_tile-max150-alpha0.8`, the same evidence digest and capture
provenance, and stage `retry150`.

Below-floor and degenerate tiles are never retried.  A retry may only leave a
tile failed or produce the ordinary syndrome+CRC certificate.  Existing
certificates are terminal and are never revisited.  Conflicting
certifications remain fatal.  Re-running the action without new evidence is
an authoritative byte-for-byte no-op.

## 3. `ctx-pava-v1`

This is the registered E023 context-threshold idea, not a port of the older
16-context GMM/ICM detector.  It is deliberately one-shot and low-dimensional.

### 3.1 Baseline window calibration

For every accepted E022 window, run `pava-v1` first, unchanged:

1. sample the authoritative core through the stored affine pose;
2. compute `score = (median(mean) - mean) / mean_abs_deviation`;
3. fit PAVA on SEARCH-parity pilot labels;
4. obtain bounded physical-value log likelihood ratios `L0`;
5. measure baseline log loss on VALIDATION-parity pilot labels.

Any window refused by baseline calibrate-or-refuse remains refused.  Context
never creates an alternative uncalibrated emission mode.

### 3.2 Provisional neighborhood

For each authoritative core cell, locate its eight immediate page-grid
neighbors by absolute page coordinate.  Context is valid only when all eight
neighbors occur in the same window core.  Otherwise the cell keeps `L0`.

For a valid cell, provisional neighbor bits are `L0 > 0` and

```
n = number of provisional ink neighbors, 0 <= n <= 8.
```

The field is computed once.  Corrected decisions are never fed back into the
neighbor count in this arm.

### 3.3 Region-pooled ordered-logit correction

For each `(scan, region)` independently, pool SEARCH-parity pilot samples
from its non-refused windows.  Page-coordinate parity keeps every duplicate
observation of one physical pilot on the same side of the train/validation
split, so overlap cannot leak its label across the split.  Eligibility and
class-support counts use unique physical `(page, y, x)` pilots.  In the fit
and held-out gate, all observations of one physical pilot have total weight
one (`1 / multiplicity` per observation); this retains the independently
calibrated window observations without allowing overlap density to dominate
the objective.  If those observations occupy different neighbor-count bins,
their unit weight is divided across those bins, so persisted per-bin support
is an effective (possibly fractional) unique-pilot count.  Raw observation
counts are persisted separately.

Fit nine additive logit offsets `tau[0] ... tau[8]` to minimize pooled
training logistic loss of

```
L = L0 + tau[n]
```

subject to:

```
tau[0] >= tau[1] >= ... >= tau[8]
-4 <= tau[n] <= 4
```

The direction is physical: an inkier neighborhood may only move a central
cell toward white relative to the marginal detector.  The ordered logistic
fit uses deterministic generalized pool-adjacent-violators blocks.  Each
original bin receives one synthetic label-0 and one synthetic label-1 sample
at baseline logit zero before pooling; this fixed symmetric prior shrinks
sparse bins toward zero and prevents infinite offsets.  A block optimum is
the unique clipped root where predicted ones equal observed ones, solved by
fixed-tolerance bisection.

The model is eligible only with at least 80 context-valid SEARCH samples,
including at least 20 examples of each central value, and at least 40
context-valid VALIDATION samples, including at least 10 of each value.

### 3.4 Held-out gate and emission

Compute pooled VALIDATION log loss with baseline `L0` and candidate
`L0 + tau[n]`.  Adopt the region model only when the candidate loss is
strictly lower.  Otherwise return the baseline WindowEvidence for the entire
region exactly, including its owner scores and payload LLRs.

When adopted:

- cells without a complete neighborhood retain `L0`;
- corrected physical-value LLRs are clipped to `[-12, 12]`;
- each window's held-out log loss is recomputed from its corrected values and
  remains the ownership score;
- payload descrambling and scan ownership then proceed unchanged.

Persist the detector profile, the nine offsets, fit/gate support, baseline
and candidate held-out losses, context-valid coverage, and adoption verdict.
Stored raw means and authoritative page coordinates remain the replay
substrate.  Scores and PAVA nodes are retained derivations: replay recomputes
and validates them through the same post-sampling implementation used during
live emission.

### 3.5 Honesty boundary

Only known pilot labels train or gate this forward arm.  Payload ground truth
is qualification-only.  CRC-certified payload labels are reserved for a
future explicitly versioned feedback generation with leave-target-out
dependencies; they are not silently consumed here.

## 4. Qualification and promotion gates

The frozen decimated-1600 and native-4800 E023b states form the two footings.
For every factorial arm report:

- prefix and final tile-state counts;
- baseline and retry decoder calls and total BP iterations;
- CRC false-accept exposure;
- exact in-memory certificate comparisons and persisted certificate-bit
  digests, new/lost/changed certificates, and GT wrong count;
- emitted-cell BER overall and by ink-neighbor count;
- held-out log loss, context fit/adoption counts, and valid-context coverage;
- unique gains of BP and context, rather than a naive sum.

Hard gates:

1. `pava-v1` reproduces the qualified E023b.0 emissions and outcomes exactly;
2. every certificate in every arm is GT-correct and no baseline certificate
   changes value;
3. detector/profile state survives save/reload and raw-evidence replay;
4. diagnostic on/off and duplicate input remain state-identical;
5. BP retry is idempotent and spends exactly one new attempt per eligible
   evidence identity;
6. a failed context gate is byte-identical to the baseline region;
7. focused E021--E023b tests and the complete repository suite pass.

Promotion is deliberately separate from implementation.  BP is judged by
unique certified-tile gain per added attempt/iteration.  Context is judged by
certificate yield and held-out calibration as well as BER; a BER-only win is
recorded but does not automatically make it the production default.

## 5. Qualification result

`qualify_e023b_arms.py` replays the raw means in the two byte-pinned E023b.0
states, runs the frozen 2 x 2, and opens the byte-pinned printed ground truth
only after all four blind outputs have been reduced to compact snapshots.
It separately reports numerical gates and the process/repository gates that
the numerical runner cannot execute.  The final qualification combined that
report with the focused contracts and complete repository suite.

| footing | baseline | BP | context | combined | emitted BER, PAVA -> context |
|---|---:|---:|---:|---:|---:|
| decimated 1600 dpi | 742 | 747 | 749 | **757** | 1.9179% -> **1.3509%** |
| native 4800 dpi | 742 | 747 | 746 | **752** | 2.6440% -> **1.8757%** |

All certificates in all eight runs are ground-truth correct, and no common
baseline certificate changes value.  On the decimated footing, context gains
eight baseline certificates and loses one, for a net gain of seven; the
combined arm gains sixteen and loses that same one, for a net gain of
fifteen.  On native, context gains four with no loss and combined gains ten
with no loss.  The explicit BP retry adds five certificates on each PAVA
footing; after context it adds eight decimated and six native certificates.
The factorial interaction in certified yield is +3 and +1 respectively, so
the combined result is not merely the union of the two independent gains.

BP's additional cost on PAVA is 51 calls / 14,731 decoder iterations
(decimated) and 53 / 15,518 (native).  Context changes which baseline tiles
reach or converge in BP, so its baseline call counts are 1,057 versus 1,076
decimated and 1,076 versus 1,098 native.  All 70 eligible region fits adopt on
both footings.  Weighted held-out pilot log loss improves from 0.08147 to
0.05698 decimated and 0.09690 to 0.07480 native; complete-neighborhood
coverage is 97.16% and 97.23%.  Context changes the frozen owner observation
on 8.00% and 8.58% of emitted cells respectively.

The two footings are different rasterizations of the same six physical
captures, not independent acquisitions.  That makes the agreement useful but
not two independent generalization trials.  The result therefore promotes BP
as an explicit, idempotent action and keeps `ctx-pava-v1` as a clean opt-in
profile pending a fresh acquisition.  `pava-v1` remains the default because
the context arm trades away one decimated baseline certificate even while it
wins strongly in net yield, BER, and held-out calibration.  The combined arm
is the best measured configuration when that trade is accepted.

The ignored machine-readable record is
`build/qualify_arms_report.json`.  Reproduce it with:

```text
env/bin/python experiments/023b-integrated-receiver/qualify_e023b_arms.py
```

This result remains strictly at the LDPC-and-below boundary.  It does not add
or infer a fountain-code, rank, completion, or stop condition.
