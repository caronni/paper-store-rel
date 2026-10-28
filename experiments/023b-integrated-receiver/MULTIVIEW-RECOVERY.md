# E023b multi-view recovery note

**Status: measured exploration, 2026-07-16.**

This note studies two related questions:

1. when the max-150 BP retry should be spent; and
2. how native and decimated rasterizations of the same scanner captures may
   be used together without pretending that they are independent evidence.

The boundary remains LDPC-and-below.  Nothing here introduces fountain-code
rank, completion, or a stop condition.

## 1. Main result

Among the methods tested on this six-capture field, the best result treats
native and decimated inputs as two correlated decode hypotheses, not as
twelve independent scans and not as one prematurely fused likelihood field.

For the qualified six-capture field, the conflict-checked union of the two
`ctx-pava-v1` + max-150 BP certificate sets gives:

| result | certified tiles |
|---|---:|
| decimated branch | 757 |
| native branch | 752 |
| common to both | 740 |
| decimated only | 17 |
| native only | 12 |
| certificate union | **769** |

All 769 tiles are ground-truth correct in the frozen qualification.  The
union gains 12 certificates over the best single branch and leaves 36 of the
805 non-degenerate tiles uncertified.

The two branches spend 1,101 and 1,125 CRC-bearing decoder calls.  Counting
all 2,226 calls gives the conservative union bound
`2226 / 2^32 = 5.1828e-7`; this bound does not assume that the two views are
independent.

The original arm qualification is reproduced by
`qualify_e023b_arms.py`; its generated report lives under the intentionally
ignored `build/` directory.  The checked-in cross-view overlap, fusion,
paired-observation, and post-blind correctness record is
[`MULTIVIEW-QUALIFICATION.json`](MULTIVIEW-QUALIFICATION.json), with SHA-256
`5360094049676f36f5e73d8eddbe0522b2891b083f91a0cfa4538274781c54fc`.
Reproduce it with:

```text
env/bin/python \
  experiments/023b-integrated-receiver/qualify_e023b_multiview.py
```

## 2. BP scheduling

The ordinary end-only `--bp-retry` spends max-150 BP on the latest failed
evidence frontier.  Retrying after every scan additionally tries historical
prefixes before later evidence replaces them.

| footing / detector | final-only: cert / calls / iterations | after every scan: cert / calls / iterations |
|---|---:|---:|
| decimated / PAVA | 747 / 1,127 / 63,417 | **748** / 1,270 / 108,459 |
| decimated / context | **757** / 1,101 / 57,544 | **757** / 1,241 / 101,340 |
| native / PAVA | **747** / 1,151 / 67,418 | **747** / 1,308 / 117,217 |
| native / context | **752** / 1,125 / 62,246 | **752** / 1,274 / 109,222 |

Calls and iterations are cumulative whole-session totals, including ordinary
max-60 attempts.

The checked scheduling record is
[`bp_schedule_report.json`](bp_schedule_report.json), SHA-256
`dd3d89b3d583f1c3191b8983f3f24e603998791e96e445e5ce352f01d31479af`.
Reproduce it with:

```text
env/bin/python \
  experiments/023b-integrated-receiver/qualify_e023b_bp_schedule.py
```

The only net gain is decimated-PAVA tile `(0,28,11)`.  There are no lost,
changed, or wrong certificates.  Both context certificate sets are identical
between schedules, as is their 769-tile cross-view union.

Thus final-only retry is not universally maximal, but it is the better
choice for the measured best method: retrying every prefix costs 140--157
extra CRC-bearing calls and roughly 44,000--50,000 extra iterations per
branch with no context-arm gain.

The one-tile counterexample occurs because more LLR evidence is not
monotonically better for iterative decoding.  An earlier prefix can avoid a
later localized error pattern or trapping basin.

A cleaner future maximum-recovery scheduler would not automatically retry
every failed tile after every scan.  After ingestion, it would take only the
tiles still uncertified at the final frontier and replay their retained
historical evidence identities under max-150, with explicit attempt/CRC
provenance.  This residual history sweep should preserve the useful prefix
opportunity while avoiding retries for tiles that later certify normally.
It requires a new ledgered action; current `--bp-retry` intentionally does
not search history.

There is no reason to rerun E021, E022, context, or payload sampling merely
because BP certifies another tile.  E023b has no upward feedback edge today.
That changes only with a future E024 generation that deliberately uses
leave-target-out certified labels.

## 3. What combination is honest

The native TIFF and its 3x-decimated TIFF came from the same physical scanner
capture.  Their noise, dust, pose, and most pixel information are correlated.
Giving them different capture ids and adding their LLRs as though they were
two independent scans would overstate the evidence.

Certificate union has different semantics:

1. each branch builds one legal likelihood sum over the six physical
   captures;
2. each branch independently proposes LDPC payload bits;
3. syndrome plus CRC either certifies or rejects that proposal;
4. a tile certified by either branch is retained;
5. if both branches certify the same tile, their payload bits must agree
   exactly or recovery stops with a fatal integrity error.

This is a small correlated-hypothesis list decoder.  Correlation can reduce
the incremental yield, but it does not turn either branch's evidence into an
independent vote.  Every decoder/CRC exposure is still counted.

E023b's ordinary session correctly refuses the naive alternative: one DPI is
frozen in the envelope and a repeated physical `capture_id` cannot be summed
again.  The certificate union therefore lives above two ordinary E023b
states rather than weakening that invariant.

The union bundle is terminal and intentionally compact.  Retain both source
states as the authoritative window/emission evidence for replay and future
E024 feedback; regenerate the bundle whenever either state changes.

## 4. Why the recoveries differ

The disagreement is structured and arises before as well as inside LDPC.

### 4.1 Geometry and photometry prefer different scales

The native footing accepted 481 placed windows versus 462 for decimated.
Together with the contiguous native-exclusive run around row 13, this is
consistent with a geometry/coverage advantage in several fragments; the
current experiment does not by itself isolate placement from sampling.

On the qualification-only ground-truth read, decimated PAVA is the stronger
photometric view on pair-matched common payload observations: its BER is
`1.8002%` versus `2.4135%` native.  This is consistent with the earlier
per-footing held-out-pilot calibration result, although those pilot supports
are not a pair-matched common-position metric.

Decimation is not merely deletion of pixels.  Its antialiasing aperture
changes edge phase, local contrast, aliasing, and the effective cell sample.
It can improve likelihood calibration even while native resolution finds
more placements and covers more cells.

### 4.2 The views are strongly correlated but locally complementary

Across 6,049,897 payload observations common to paired native/decimated
captures under PAVA:

- LLR Pearson correlation is `0.9697`;
- hard decisions disagree on `2.2842%`;
- both views are wrong on `0.9647%`;
- decimated alone is wrong on `0.8355%`;
- native alone is wrong on `1.4488%`.

Thus most evidence is shared, but tens of thousands of local decisions are
correct in only one view.  Those differences are large enough to move
near-threshold LDPC tiles into different basins.

Context + PAVA reduces paired hard disagreement from `2.2842%` to `1.6935%`,
about 25.9%, which is further evidence that the context correction is doing
useful photometric regularization.  It cannot, however, make the two
scale-specific placement and coverage fields identical.

### 4.3 Exclusive certificates cluster

The view-exclusive tiles are not IID scatter.  Examples in the final
context+BP union include:

- native-only runs at row 13, columns 14--18, and row 18, columns 16--18;
- decimated-only clusters at row 7, columns 17/19/20, and row 27,
  columns 13--15/20/22.

The coherent runs point away from random CRC accidents and toward local
E021/E022 boundaries, accepted placements, owner choice, coverage, and error
topology.

### 4.4 LDPC makes small upstream differences nonlinear

Certificate recovery is not determined by scalar BER alone.  Error topology,
erasures, reliability ordering, short cycles, trapping sets, and the BP
trajectory all matter.  A lower aggregate BER therefore need not imply that
one view certifies a strict superset of the other.

There is also deliberate path dependence.  E023b retains an earlier valid
syndrome+CRC certificate and does not let later, noisier evidence revoke it.
Consequently an individual scan or an earlier evidence prefix can certify a
tile that the final aggregate would not decode from scratch.

The complete combined sets are still 96.23% Jaccard-overlapping
(`740 / 769`).  It is the marginal recovery tail, not the whole page, that is
strikingly complementary.

## 5. Fusion experiment

We also tested legal one-vote-per-capture fusions.  For a cell observed in
both views, these form one composite LLR whose view weights sum to one; a
cell present in only one view uses that view.  The six resulting
per-capture fields are then added in the ordinary independent-capture way.

With context + PAVA:

| fused candidate | max-60 | after max-150 BP |
|---|---:|---:|
| equal convex mean | 759 | 763 |
| lower held-out-pilot-loss view | 757 | 761 |
| prefer decimated, fill missing coverage from native | 755 | 761 |

All fused certificates were ground-truth correct.  More importantly, every
one was already present in the 769-tile branch certificate union.  The best
fusion is a strict subset, missing six union certificates.  PAVA-only fusion
has the same qualitative result and adds no certificate beyond the union.

Therefore none of these cell-level fusion rules is promoted from this
experiment: each is more coupled, can average away a useful view-specific
hypothesis, and produced no new certificate on this field.  This result does
not rule out a better preregistered fusion rule on a different acquisition.

## 6. Low-complexity next experiments

The measurements point to the following order.

1. **Keep the two view branches and union certificates.**  This is the
   measured, monotone, low-complexity gain.
2. **Keep a very small CRC-gated candidate portfolio for unresolved tiles.**
   View-specific evidence prefixes are more promising than broad parameter
   searches because prefix path dependence is already observed.  Every
   candidate must have a stable identity and count its CRC exposure.
3. **Build a single-input scale-space receiver.**  Start from native TIFFs,
   derive the antialiased 1600-dpi view internally, run placement at both
   scales, map accepted poses into one physical coordinate system, and keep
   near-tie geometry.  This combines native's coverage advantage with
   decimated photometry without inventing extra captures.
4. **Use held-out pilots to choose geometry/photometry across views.**  The
   existing held-out log-loss machinery can select an aperture or owner
   locally without ground truth.
5. **Apply E024 feedback separately.** E024.0 now uses CRC-certified
   codewords as dense, leave-target-out labels for local pose, calibration,
   context, or owner reconsideration. This is where a new LDPC certificate
   can naturally change lower-layer processing. The feedback graph tracks
   the windows and neighboring tiles affected by each accepted correction
   and reprocesses a local dependency queue instead of blindly rerunning the
   whole page. See `../024-feedback-receiver/README.md`.

The first scale-space qualification should isolate causes rather than add all
of these choices at once:

1. hold placements/owners fixed and compare native versus decimated
   photometric sampling;
2. hold the sampler fixed and compare native versus decimated placement
   fields;
3. then allow both geometry and sampler to vary.

That factorial tells us whether the next gain belongs mainly in E021/E022
acquisition or in payload likelihood construction.

The tempting larger search space—many resize kernels, weights, BP settings,
and placement variants—should not be opened all at once.  The spatial
clusters give a better experimental target: preserve a small number of
geometry/aperture hypotheses exactly where the current winner-take-all
decision is unstable, then let LDPC+CRC adjudicate them.

That follow-up is registered as the design-only
[`E023c capture-scoped scale-space receiver`](../023c-scale-space-receiver/README.md).
Its central rule is one physical-capture transaction with a bounded
geometry/sampler hypothesis list; deterministic views never become
independent evidence.

## 7. E023c factorial outcome

The preregistered NN/DD/ND/DN causal arm has now been run. Its full checked
record is
[`E023c RESULTS.md`](../023c-scale-space-receiver/RESULTS.md).

The same-view NN=752, DD=757, and union=769 anchors reproduce exactly.
Crossing geometry and sampler raises the conflict-free, ground-truth-correct
union to 772:

- DN contributes `(0,7,18)` and `(0,27,21)`;
- ND contributes `(0,21,16)`.

The main measured effect follows the geometry field: box3 geometry improves
certificate count and BER under both native and box3 sampling. Native
sampling under box3 geometry has the lowest aggregate BER, so the result
does not support “decimated pixels are simply better.” It supports keeping
a bounded set of geometry/pose/owner hypotheses alive until LDPC+CRC.

Four full lanes roughly double decoder work for the three-tile gain. The
next low-complexity scheduler should therefore run NN+DD first and restrict
DN, then ND, to the unresolved tail.
