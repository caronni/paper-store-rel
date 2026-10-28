# Color-uplift design and implementation review

Review target: commit **64ddea17aca2503b93459504c154976093f6eeaa** on branch **color-uplift**

Comparison base: **af920291b157da5cc8eb7f964a044692ff431dc6**

Review date: **2026-08-10**

Disposition: **Request changes**

## Executive assessment

This is promising work with a real result. The final matrix reports 12,516
certified tiles versus 10,706 in the archived runs, a net gain of 1,810
(+1,813/−3, +16.9%), five byte-verified closes, and the first reported paper
recovery of xerox c2-cmy7. The measurement record is unusually candid about
negative experiments, noisy timing, memory consumption, physical-corpus limits,
and the extra CRC exposure. The full test suite is also green.

I nevertheless would not merge this commit as currently implemented and
qualified. There are four code-path correctness problems:

1. Supplemental lanes are suppressed precisely when the prior certificate
   frontier is empty, even though U(off) and U(a3) do not require certificates.
2. Force-null and custom stack configuration change the algorithm without
   changing durable policy or attempt identity.
3. Iterative demapping can execute up to three CRC checks while durable
   accounting records at most the final one.
4. A5 context is fitted and gated in unconditioned evidence space but can be
   emitted after A4b conditioning, so the fitted model is not necessarily the
   deployed composition.

There are also three qualification blockers:

1. A2/PK6 is still absent even though the plan and normative design say the
   complete program landed.
2. The measured +28.6% demap cost exceeds B2 as written; the final report creates
   an exception after the result and then calls the pre-registered bar met.
3. The full-run harness copies the pinned TIFF hash into output without binding
   the decoded TIFF to that hash.

The evidence supports continuing the uplift, but it does not yet support the
current claim that only an adoption ruling remains. My recommended path is a
small correctness and qualification packet before any architecture cleanup:
fix the four code defects, make the evidence chain self-authenticating, state
the honest B2 disposition, and either land PK6 or formally remove it from this
campaign. Then rerun the affected hermetic and full-decode gates.

Priority labels in this review mean:

- **P1:** must be fixed or explicitly resolved before this change is merged or
  enabled.
- **P2:** high-priority follow-up or explicit rollout decision; may become P1
  depending on the supported operating envelope.
- **P3:** maintainability or documentation issue that should be scheduled.

## Scope and method

The branch is large: 77 files and approximately 29,830 additions / 572
deletions relative to the merge base. I reviewed the production color path,
shared LDPC path, scheduler and resume policy, qualification harness, campaign
plan, normative receive design, and the final measurement report. I also traced
the K path where this change claims exact non-interference.

Validation performed:

- Full receiver suite:

      PYTHONDONTWRITEBYTECODE=1 env/bin/python -m pytest -p no:cacheprovider --basetemp /tmp/paper-color-uplift-full-pytest tests/holo -q

  Result: **1,180 passed, 37 skipped**, with nine expected provisional-receiver
  warnings, in 403.62 seconds.

- Focused changed/core coverage: **289 passed**.
- Integration/session/runtime coverage: **59 passed**.
- Independent focused color/LDPC coverage: **167 passed**.
- Diff hygiene: git diff --check is clean.
- Local semantic probes for the empty-frontier lane, force-null identity, and
  iterative-CRC sequence described below.
- Cross-check of the locally available final artifacts against the tables in
  [COLOR-UPLIFT-MEASUREMENTS.md](COLOR-UPLIFT-MEASUREMENTS.md): the eight totals,
  24 U-lane certificates, timing splits, content fingerprints, and zero
  disagreements in 69,066,304 audited cells agree.

I did not rerun the multi-hour physical qualification matrix or operate the
scanner/printer hardware. The committed branch does not contain the final
run artifacts needed to reproduce those results from the tree alone.

## What the design gets right

Several choices should survive the required fixes.

- **Authority is explicit.** The KnownField boundary, certified-only masks,
  deterministic fitting, and refusal vocabulary are materially better than
  allowing provisional estimates to leak into authority.
- **Existing certificates are protected.** The per-address retirement law and
  exact-null behavior make supplemental attempts additive with respect to the
  certificate set. Tests around fully certified pages and arm suppression are
  strong.
- **The campaign discarded ideas that lost.** The margin-gated erasure arm,
  per-plane K port, and other measured-negative variants are retired rather than
  rationalized.
- **Qualification observes mission-level outcomes.** Full decodes, exact output
  hashes, every-certificate ground-truth projection, named losses, and no-op
  controls are the correct classes of evidence.
- **The measured gain is substantial.** In particular, the xerox c2-cmy7 close
  falsifies a pessimistic expectation in a useful way. That is a reason to fix
  the branch, not a reason to relax its contracts.
- **The report exposes limitations.** It calls out the single-sheet nature of
  the corpus, provisional status, 40–42 GiB peaks, noisy CPU measurements, and
  up to three CRC exposures. The review findings below mainly concern where the
  implementation and final adjudication do not yet honor those disclosures.

## Blocking correctness findings

### P1. Supplemental lanes incorrectly require a non-empty prior certificate frontier

**Evidence**

[production_color.py](../src/holo/receive/production_color.py#L527-L538)
returns an empty payload when any of these are true: no poses, no prior
certificates, or every span is certified. Its comment says these are the R
leaf's exact pixel-free pre-gates.

That gate is not valid for every U arm:

- U(off) fits from committed furniture and requires no certified sibling.
- U(a3) likewise does not need a prior certificate frontier.
- U(a4b) does need sibling authority, but already has an arm-specific arity and
  KnownField gate.

A local probe constructed a valid RefineAddressPlan with poses and regions but
an empty certificates tuple. The scheduled U(off) leaf produced zero blocks,
zero attempts, and zero events. Calling placement and color-evidence collection
on the same input produced one placement, one window, one page, and one region.
This does not prove that the omitted evidence would certify a tile, but it proves
that the scheduler suppresses a valid recovery opportunity before inspecting
the raster.

**Impact**

The change loses yield on zero-frontier captures, which are among the difficult
inputs the uplift is meant to recover. It also violates the stated reachable-set
law: the reachable set is not exactly the uncertified residue if all residue is
discarded when no certificate exists yet.

**Required change**

Make the pre-gates arm-specific:

- Every U arm may require poses and non-full completion.
- U(off) and U(a3) must not require plan.certificates.
- U(a4b) should rely on its own certified-sibling/arity predicate.

Add production-level tests with poses plus an empty frontier for both U(off) and
U(a3), and assert that the raster/evidence path runs. Retain the existing tests
for no poses and fully certified pages.

### P1. Force-null and StackConfig are outside durable policy and attempt identity

**Evidence**

[color_stack.py](../src/holo/receive/color_stack.py#L203-L256) reads
HOLO_COLOR_STACK_FORCE_NULL from process-global environment state at execution
time. [color_attempts.py](../src/holo/receive/color_attempts.py#L60-L72) changes
the cmy7 demap count from three to one based on that ambient value.
[production_color.py](../src/holo/receive/production_color.py#L448-L512) also
allows a public stack_config and skips U lanes under force-null while exposing a
fixed class-level policy ID.

Attempt IDs are minted in
[color_attempts.py](../src/holo/receive/color_attempts.py#L265-L310) from fields
defined in [records.py](../src/holo/receive/records.py#L95-L123). They include
FEC limits and alpha, but not effective demap count, force-null mode, or the full
stack algorithm configuration.

A direct cmy7 probe used the same failing tile under normal and force-null modes:

- Both executions minted the same attempt ID.
- Normal mode certified after 225 accumulated BP iterations.
- Force-null mode failed after 217 iterations and minted no certificate.

Thus one content identity denotes two algorithms and two outcomes.
Runtime validation also consults the current environment when checking iteration
counts rather than a profile stored with the attempt.

There is an important scope nuance: failed attempts are invocation-local and
restore reconstructs state primarily from certificates, so this is not a claim
that every historical failed-attempt row is revalidated after restart. The
identity collision is still real, and live certificates or committed U barriers
can be produced under a mode that the durable policy cannot distinguish.
Process-global reads also make concurrent in-process runs unsafe.

The harness compounds this: it sets the environment when force-null is requested
but does not clear or reject an inherited value when force-null is false. A
candidate/false run can therefore execute the null algorithm while being labeled
candidate.

**Impact**

Resume equivalence, comparison labels, attempt deduplication semantics, and
concurrent execution all depend on behavior that is not captured by policy
identity. The statement that force-null is exactly the pre-campaign receiver is
only defensible for a fresh, isolated harness process with a controlled
environment.

**Required change**

Replace ambient reads with an immutable explicit ReceiverMode/DecodeProfile
carried from request construction to the leaf. Derive both receiver policy ID
and attempt decoder identity from every behavior-affecting field, including
effective demap count and complete StackConfig tokens.

Prefer making force-null a test-only, non-resumable execution profile with a
separate state namespace. If it remains production-reachable, it needs its own
policy ID and an explicit CLI/API setting. Reject custom StackConfig values
unless their complete semantic token participates in identity.

Add tests for:

- normal versus null identity;
- inherited environment mismatch;
- resume across mode/config mismatch;
- two concurrent receivers with different profiles;
- null U-barrier state followed by a live invocation.

### P1. Iterative demapping loses CRC exposure history

**Evidence**

[color_tile.py](../src/holo/core/color_tile.py#L192-L214) replaces outcome on
each inner decode and sums only child BP iteration counts. The returned
FrameDecodeOutcome contains the final pass's crc_invoked/crc_ok fields.
[color_attempts.py](../src/holo/receive/color_attempts.py#L169-L197) extracts
and persists only those final facts. Session counters in
[session_model.py](../src/holo/receive/session_model.py#L300-L307) increment
decoder_calls once per outer attempt.

A stubbed sequence of:

1. syndrome-clean, CRC-failed, five iterations; then
2. syndrome-failed, no CRC, seven iterations

returned 12 iterations but crc_invoked=false and crc_ok=None. An actual CRC
exposure disappeared. Similarly, two CRC failures followed by success appear as
one successful CRC exposure.

This conflicts with the receiver's published calls × 2^-32 integrity accounting
and with the report's own acknowledgement that one attempt can invoke the CRC up
to three times. Zero wrong certificates across 69 million audited cells is
excellent regression evidence, but cells are correlated within frames and zero
observations are overwhelmingly expected at a 2^-32 tail. It cannot replace an
exact frame/CRC exposure count.

**Impact**

The reported integrity union bound may undercount exposures by up to 3×, and
FrameDecodeOutcome's meaning of crc_ok=None no longer describes the outer
attempt. This is a receiver-wide integrity-accounting contract, not only a
diagnostics bug.

**Required change**

Add an exact crc_invocations or crc_exposures count to the outer outcome and
accumulate it across every inner decode. Preserve it through TileAttemptRecord,
StageTally/session counters, diagnostics, JSON, and the published union-bound
calculation. Keeping an ordered per-pass summary would also make failures
auditable, but the exact count is the minimum.

Do not silently reinterpret decoder_calls if it intentionally means outer
attempts; add a separate counter with an explicit unit. Version durable/report
schemas and policy where required.

Add tests for CRC-fail → syndrome-fail, CRC-fail → CRC-fail → success, and
three syndrome-clean CRC failures.

### P1. A4b and A5 are fitted in a different composition from production emission

**Evidence**

A4b attaches selected_fit.conditioned in
[color_stack.py](../src/holo/receive/color_stack.py#L728-L806). A5 then builds
neighborhood bins at
[color_stack.py](../src/holo/receive/color_stack.py#L832-L836) using
selected_fit.evidence(features) without the row's KnownField mask and bits.

[color_fitting.py](../src/holo/receive/color_fitting.py#L86-L95) delegates that
call to evidence_with_divisor, and the CMY8 conditioned marginal is applied only
when a known mask is supplied
([color_fitting.py](../src/holo/receive/color_fitting.py#L149-L187)).
Production emission does supply certified masks and bits
([color_payload.py](../src/holo/receive/color_payload.py#L851-L865)).

Known bits overwrite only their own plane signs during neighborhood construction
([color_neighbourhood.py](../src/holo/receive/color_neighbourhood.py#L124-L130)).
Conditioning on a certified sibling can still flip an unknown plane, which can
change that unknown plane's contribution to neighboring bins. Consequently A5's
training population, context gate, and fitted state can differ from the evidence
space on which the deployed A4b+A5 transform operates.

The implementation comment says A5 corrects what A4b leaves, but numeric
application is effectively context correction followed by conditioned
marginalization while fitting/gating does not represent that same composition.
There is no test combining a sign-changing A4b case with A5.

**Impact**

The adoption gate is not necessarily evaluating the deployed transform. This can
invalidate exact-null reasoning, select a context model for the wrong bins, or
make a fitted improvement turn into an emission regression.

**Required change**

First choose and document the normative order:

- If the intended stack is A4b → A5, make neighborhood binning, fit population,
  gate, and emission row-aware and pass the identical certified-only mask/bits
  through every stage.
- If the intended stack is A5 → A4b, state that explicitly and requalify that
  composition rather than describing A5 as correcting A4b's residual.

Add a focused composition test where conditioning flips an unknown plane, changes
a neighbor bin, and verifies that fitting/gating and final emitted evidence use
the same bins and order.

## Blocking scope and qualification findings

### P1. A2/PK6 is declared complete but is not implemented

**Evidence**

The plan says every program packet landed and only the user adoption ruling
remains ([COLOR-UPLIFT-PLAN.md](COLOR-UPLIFT-PLAN.md#L1-L8)). The program names
P5 per-window plane-registration residuals, schedules PK6, and normative
[RECEIVE-DESIGN.md](RECEIVE-DESIGN.md#L680-L704) defines A2.

The production stack says that rung is still owed, accepts residuals as an
unread argument, and deletes it
([color_stack.py](../src/holo/receive/color_stack.py#L82-L85),
[color_stack.py](../src/holo/receive/color_stack.py#L545-L592)).
The live policy token also lacks the promised winreg-const-shrink8 segment.

**Impact**

This is more than stale prose: the normative algorithm, campaign scope, policy
identity, and completion status disagree. A reviewer cannot tell whether A2 was
deliberately dropped, accidentally omitted, or still required for the intended
harmonization.

**Required resolution**

Either:

1. implement PK6, bind it to policy identity, and run its specified full-decode
   gate; or
2. formally defer A2/P5 and remove it from the normative stack, current program,
   diagnostics promises, policy-token description, and completion claim.

Do not call the original program fully landed while this decision is unresolved.

### P1. B2 failed as written; the final adjudication is a post-result amendment

**Evidence**

The pre-registered B2 language in
[COLOR-UPLIFT-PLAN.md](COLOR-UPLIFT-PLAN.md#L402-L407) defines the primary
metric as replay-path CPU versus a fresh same-epoch baseline, with color ≤ +10%
and K ≤ +5%. The bar does not exclude decoder work.

PK8 measures 2,636 seconds live versus 2,050 seconds force-null on cmy7:
**+28.6%**. The final report classifies iterative demapping as new decoding work
outside B2 and concludes that no bar failed
([COLOR-UPLIFT-MEASUREMENTS.md](COLOR-UPLIFT-MEASUREMENTS.md#L3187-L3206)).
Git history shows the bar language predates this result; the exception is not
part of the quoted criterion.

Iterative demapping is inner work in ordinary tile attempts, not a separately
scheduled operator lane. It may be a good purchase—the yield evidence suggests
that it is—but a useful result does not retroactively satisfy a different bar.

The same section contains a smaller arithmetic error: −14.3% is inside a ±15%
noise band, while +18.7% is outside it; the prose says the reverse.

**Impact**

This weakens the campaign's decision discipline and obscures the actual product
tradeoff. It also makes future pre-registration less credible if a missed bar
can be reclassified after unblinding.

**Required resolution**

Choose one honest disposition:

- mark B2 **FAILED as written**, then make an explicit adoption waiver based on
  the measured yield and total cost; or
- label B2 **amended after measurement**, identify the approving decision and
  rationale, and rerun a prospectively defined cost gate if “met” status is
  required.

In either case, report whole-invocation latency, CPU, memory, and CRC exposure as
the operator-visible budget. Standard-ladder versus supplemental-tail splits are
useful attribution, but they do not replace the total SLO.

### P1. Full qualification does not bind the decoded TIFF to its pinned hash

**Evidence**

[ab_runner.py](../measure/_color_uplift_harness/ab_runner.py#L574-L605) loads
provenance and constructs CaptureInput with a path and DPI but without
expected_sha256. It then copies the provenance digest into the result header.
[runtime.py](../src/holo/receive/runtime.py#L509-L517) rejects a source mismatch
only when expected_sha256 is supplied.

Therefore a changed or replaced TIFF can be decoded while the output JSON still
claims the pinned digest. A separate manual provenance-verify step reduces the
probability of this failure but does not close the time-of-check/time-of-use gap
or make the runner comparable by construction.

**Impact**

The principal full-decode qualification artifact can misidentify its input. That
breaks chain of custody for the most important evidence in this change.

**Required change**

Pass the provenance digest as CaptureInput.expected_sha256 and record the digest
actually verified at ingestion. Refuse before creating state or expensive work
on mismatch. Add a test that mutates/replaces the file after provenance loading
and proves the full runner fails without writing a valid result.

## High-priority design and rollout findings

### P2. The change harmonizes the color ladder, not color and B/W calibration

The design goal needs a sharper statement. The plan says “one unified color
calibrated-evidence stack” and normative design explicitly leaves K unmigrated.
Production still dispatches K and color to separate processors
([production.py](../src/holo/receive/production.py#L773-L805)). KnownField is
called kind-neutral but embeds three C/M/Y components and color anchoring, then
the payload boundary explodes it into private parallel arrays.

What is harmonized today:

- downstream session, attempt, certificate, and barrier machinery;
- the color arms' fit/refusal/event vocabulary;
- selected primitives reused from the K implementation.

What is not harmonized:

- sampling and photometric calibration;
- component/authority representation;
- context-stage interfaces;
- codec capability and lane registration;
- policy derivation.

That may be the correct transitional boundary, especially because perturbing the
certified K path is risky. It does not satisfy a literal reading of “harmonize
processing of color and B/W inputs.”

**Recommended architecture**

Avoid a wholesale rewrite in this patch. After the correctness packet:

1. Introduce a component-arity-neutral KnownField/EvidenceBatch carrying site
   keys, provenance, masks, and values through stage boundaries.
2. Move codec capabilities, lane families, and semantic policy tokens into one
   profile registry. Generic scheduler code should not special-case k-v1 or
   assume every non-K codec is color.
3. Define a small EvidenceStage protocol with explicit proposal, fit population,
   gate, and emitted-space contracts. Make composition order testable.
4. Adapt the current K and color paths behind that interface, retaining exact
   differential tests against K goldens.
5. Migrate K internals only after exact numerical equivalence is established.

This gets genuine harmonization without making K absorb the campaign's
experimental color semantics.

### P2. Global scheduler v4 invalidates old K states despite an unchanged K plan

[cascade.py](../src/holo/receive/cascade.py#L620-L622) bumps the scheduler policy
globally. K schedules no U lanes, and a probe confirmed that the old and new K
plans are equal, but [runtime.py](../src/holo/receive/runtime.py#L473-L477)
rejects the old policy ID. Existing K sessions must therefore restart even
though their schedule and outputs are unchanged.

At 4800 DPI those restarts can mean hours and approximately 40 GiB of memory.
This is an operational compatibility break hidden behind a color-only feature.

Derive scheduler identity from the codec's actual capability/plan token, preserve
the v2 identity for unchanged K plans, or provide a narrowly verified migration
that proves the committed plan prefix is identical. Add an archived or synthetic
old-K resume test.

### P2. --refine silently acquired an expensive supplemental tail

[runtime.py](../src/holo/receive/runtime.py#L246-L275) makes run_refine execute
the complete plan, including U(off/a3/a4b). CLI help still describes ordinary,
mopup, and refinement levels
([cli.py](../src/holo/cli.py#L926-L930)).

The final measurements price the U tail at 0–31% of the archived ladder for 24
certificates across the matrix, with some total rows at +28.0% and +40.4%.
Certificate monotonicity does not imply latency, resource, or integrity-exposure
monotonicity.

Prefer a provisional explicit uplift tier/flag whose value is persisted and
policy-bound. If product semantics require one no-knob refine operation, update
the CLI and operator docs and obtain an explicit whole-invocation SLO decision.
Either way, add a CLI contract test.

### P2. Shared LDPC paths compute extrinsics even when callers discard them

[decode.py](../src/holo/core/ldpc/decode.py#L103-L139) always computes and
allocates L − total extrinsic LLRs; plain decode discards the result.
[frame.py](../src/holo/core/ldpc/frame.py#L203-L221) always calls decode_soft,
including when want_extrinsic=false.

K, CMY8, and ordinary one-pass color decodes now pay this O(number of bits)
subtraction/allocation. Output bits may remain exact, but the K execution path is
not “untouched code,” so its +15.4%/−11.0% cross-epoch timings cannot be treated
as a pure machine-noise ruler.

Make extrinsic computation conditional in the LDPC leaf and keep plain decode on
the old allocation path. Then rerun a same-tree K timing comparison, or stop
using K timing as evidence that this branch has no shared-path cost.

### P2. Qualification artifacts are numerically cross-checkable locally but not reproducible from the commit

The report cites runs/* artifacts that are absent from the reviewed Git tree.
The external files available in this worktree corroborate the published
numbers, so this is not an allegation that the table was fabricated. It is a
chain-of-custody and reproducibility problem.

Related harness gaps:

- The full runner records Git identity once but no before/after content
  fingerprint. Replay detects drift but still writes a result and exits
  successfully.
- The primary full JSON classifies U timing as base timing.
- Certificate rows are serialized without lane IDs, so the published 24 U-lane
  certificates require an external derivation.
- The final lane, stage-time, set-difference, and tree-fingerprint derivations
  have no committed generator.
- Arm labels are arbitrary text and comparisons do not bind effective mode,
  capture digest, policy, tree, or StackConfig.
- Approximately 6,400 lines of harness Python have no collected pytest tests.

Make the harness emit authoritative lane kind, per-lane time, certificate
attribution, effective config, verified input digest, and before/after code
fingerprints directly. Treat any drift as a void/nonzero result. Commit a compact
final manifest containing hashes, sizes, policy/config IDs, and the essential
score/set-difference summaries; large raw artifacts may remain external if their
content-addressed location is recorded. Add hermetic unit tests for comparison
compatibility and derived totals.

### P2. Empty audits are reported as truth-path validated

[gt_score.py](../measure/_color_uplift_harness/gt_score.py#L367-L436)
correctly requires cells_compared > 0 in one command, but the state/run commands
only check disagreement == 0. The hp-c2-cmy7 row has zero certificates and zero
cells yet reports truth_path_validated=true. The report then says all eight truth
paths were validated.

This does not invalidate the row's zero-certificate result or the other seven
audits. Use one shared validity predicate and report not-applicable/false when
there are no certificates. Also fail if nonzero certificates unexpectedly yield
zero audited cells.

### P2. The supported memory envelope is not enforced

Every 4800-DPI final row peaks around 40.3–42.2 GiB; the 2400-DPI canary is about
12.8 GiB. The report suggests the peak is largely the finest existing rung, so
this is not necessarily a regression caused by the uplift. It is still a
deployment constraint.

Bulk retention is visible in all raw window crops, all submitted futures/results,
and simultaneous crop/base/corrected feature tuples
([color_sampling.py](../src/holo/receive/color_sampling.py#L170-L186),
[_parallel.py](../src/holo/receive/_parallel.py#L88-L107),
[color_payload.py](../src/holo/receive/color_payload.py#L759-L804)).

Before normal operator use, add a memory estimate/admission check and a bounded
in-flight concurrency policy. Then investigate streaming crops and a two-pass
fit/emission design. Correct the stale comment in color_stack.py that still
attributes a +34% peak to feature tuples after the measurement report retracts
that diagnosis.

## Smaller issues

### P3. Reserved U-lane syntax should fail closed

The parser treats malformed IDs beginning with the reserved u prefix as ordinary
lanes. Persisted plans reduce immediate exploitability, but a reserved namespace
should reject malformed entries rather than silently changing their semantics.
Add negative parser tests and fail closed.

### P3. Private cross-module types are de facto public interfaces

color_stack imports private row, detector-fit, owner-selection, and fit helpers
from neighboring modules. Several new modules are just below 1,000 lines, and
fit_region_stack owns roughly 300 lines of orchestration. The numerical line cap
is satisfied, but the boundaries are not stable.

Promote the intended shared records to named public contracts and split stage
orchestration by behavior, not only by file length. This fits naturally with the
EvidenceStage follow-up above.

### P3. Schedule documentation is stale

[PHASED-SCHEDULE.md](PHASED-SCHEDULE.md#L394-L430) still describes the older
U(a3/a4b), scheduler-v3 design rather than U(off/a3/a4b), coding-aware removal,
and scheduler v4. Update it or mark it explicitly superseded. Reconcile the
other contradictory state-compatibility claims at the same time.

### P3. Full-mode diagnostics remain snapshot-starved

The measurement report already acknowledges that the observer wrapper cannot
provide the intended full-mode snapshots. This appears diagnostic-only and does
not invalidate certificates, but it should remain an explicit follow-up rather
than disappear at campaign close.

## Test gaps to close

The production test suite is large and healthy; the missing tests are concentrated
at newly composed boundaries:

| Boundary | Required regression |
|---|---|
| U-lane scheduling | Poses plus empty certificate frontier reaches U(off) and U(a3) evidence collection |
| Receiver identity | Normal/null/custom configurations have distinct policy and attempt identities |
| Resume | Mode mismatch and old-K scheduler behavior are deterministic and intentional |
| Iterative demap | Exact CRC exposure counts for mixed three-pass outcomes |
| A4b + A5 | Conditioning-induced sign/bin change uses identical fit, gate, and emission space |
| Provenance | Full runner refuses a TIFF whose bytes do not match the pinned digest |
| Harness | U time/cert attribution reconcile to totals without external scripts |
| Ground truth | Empty certificate audit is N/A; nonempty certificates cannot audit zero cells |
| CLI | --refine/uplift behavior and cost tier are discoverable and policy-bound |
| Shared LDPC | No extrinsic allocation/work when want_extrinsic is false |

## Suggested landing sequence

### Packet 1: correctness and identity

Fix the empty-frontier pre-gate, explicit receiver mode/config identity, CRC
exposure accounting, A4b/A5 composition, and lazy LDPC extrinsics. Add the
boundary tests above. This packet should not change the already demonstrated
fit constants unless the A4b/A5 correction requires it.

### Packet 2: qualification integrity

Bind TIFF provenance in the full runner, make tree drift fatal, emit lane
attribution directly, fix empty-audit truth status, and publish a compact
content-addressed final manifest. Rerun the affected full rows from an immutable
worktree.

### Packet 3: scope and rollout decision

Resolve PK6/A2, state B2 honestly, choose explicit versus implicit uplift-tail
semantics, set the supported memory envelope, and decide old-K state migration.
The adoption record should approve total invocation cost and exact CRC exposure,
not only certificate monotonicity.

### Packet 4: architecture follow-up

Only after the result is stable, introduce the codec-capability registry,
component-neutral authority/evidence types, and explicit stage-composition
protocol. Preserve K bit-for-bit through adapters and differential tests.

## Questions for the author/approver

1. Was A2/PK6 intentionally dropped? If yes, what decision superseded the
   normative design and why is the plan still marked complete?
2. Does “harmonize color and B/W” mean a common downstream ledger, one color
   calibration ladder that borrows K primitives, or a genuinely common
   calibration/evidence architecture?
3. Is up to three CRC exposures per attempt formally accepted in the system
   integrity budget? What durable counter will support that budget?
4. Was the +28.6% demap cost explicitly waived after B2 missed, or is the claim
   that decoder work was always outside B2? Please point to the pre-measurement
   ruling if the latter.
5. Is force-null intended to be test-only? If so, why can production behavior
   still depend on ambient process state?
6. Was invalidation of all pre-v4 K session states intentional and operationally
   approved?
7. Is the U tail intended to be mandatory whenever an operator asks for refine,
   despite the measured 0–31% tail cost, or should it be a provisional tier?
8. What minimum RAM is supported for 4800-DPI operation, and where should a run
   refuse rather than risk host-wide pressure?
9. Where are the authoritative final artifacts expected to live, and what is
   the retention/content-addressing policy?

## Merge gate

I would reconsider approval when all of the following are true:

- [ ] U(off) and U(a3) operate with an empty prior certificate frontier.
- [ ] Every behavior-affecting receiver setting is explicit and identity-bound.
- [ ] Exact CRC exposures are durable and drive the integrity bound.
- [ ] A4b/A5 fit, gate, and emission composition are identical and tested.
- [ ] A2/PK6 is implemented and qualified or formally removed/deferred.
- [ ] B2 is recorded as failed, amended, or prospectively rerun—without calling
      the original criterion met by reinterpretation.
- [ ] Full qualification cryptographically binds the TIFF actually decoded.
- [ ] Shared K/CMY8 paths do not pay unused extrinsic work.
- [ ] K state compatibility and U-tail operator semantics are explicit.
- [ ] Essential final evidence is reproducible from a committed manifest and
      tested derivation path.
- [ ] Affected full-decode rows are rerun from an immutable tree, with exact
      input, code, policy, lane attribution, output, and CRC-exposure identity.

Subject to those changes, the measured yield makes this a strong candidate for a
flagged/provisional rollout followed by an independent physical holdout across a
new sheet/day/toner/scanner epoch. The present eight captures are valuable
existence and regression evidence, but not yet a population-level calibration
claim.

---

## Disposition (2026-08-10, lead + user adoption ruling)

Every load-bearing finding was reproduced or refuted first-hand against the
tree before disposition (verify-review-claims doctrine; three of the review's
probes reproduced verbatim, one micro-benchmark, full B2 git archaeology).
Companion records: MEASUREMENTS §14.10, RECEIVE-DESIGN v0.54, PLAN v1.10.

| Finding | Verified verdict | Disposition |
|---|---|---|
| P1 empty-frontier U-lane gate | CONFIRMED (spec+code co-defect; measured corpus loss zero — hp c2-cmy7 is cell-level dead under both configurations) | **FIXED** — arm-split pre-gate + pin test + v0.54 amendment + policy token bump; control re-run scheduled post-merge (user ruling) — **done 2026-08-10, prediction met** (u-lanes ran and refused, address ledger identical to the digit, 0 certificates; MEASUREMENTS §14.10 + Run ledger `pkfinal-repin`) |
| P1 force-null / StackConfig identity | CONFIRMED mechanics; P1 overstated (sanctioned contract; attempts non-durable; certificates content-bound) | **FIXED narrowly** — demap count minted into cmy7 decoder identity; harness refuses inherited env; full ReceiverMode framework declined |
| P1 CRC exposure history | CONFIRMED mechanics; "hidden hole" refuted (§13.8 registered it; no published number wrong; bound not computed anywhere in-tree) | **Docs fixed** — union bound restated ×DEMAP_ITERATIONS for cmy7 (v0.54), docstrings scoped; exact counting deferred (user ruling: narrow) |
| P1 A4b/A5 composition | PARTLY — real (conditioned∘A5 never gated; zero tests on combined branch); bin-divergence mechanism wrong (bins frozen at fit, reused at emission) | **Comment corrected + directed test added**; refit-order change deferred unless u-a4b is promoted |
| P1 A2/PK6 declared complete | CONFIRMED (independently found by the lead's own audit) | **Formally deferred** (user ruling) to a measure-first line; PLAN v1.10 + v0.54 strike; suggested task filed |
| P1 B2 post-hoc adjudication | CONFIRMED — exclusion written ~12 h post-measurement, inverting PK4.3's own scope; §14.5 noise prose also wrong | **Recorded FAILED AS WRITTEN; waiver ratified by user adoption ruling 2026-08-10**; §14.5/§14.6/§14.6a rewritten |
| P1 TIFF binding in full runner | CONFIRMED in committed code; operationally closed by pkfinal drivers (8/8 verify logs) for the §14 rows | **FIXED** — expected_sha256 threaded in run_full |
| P2 LDPC extrinsic waste / "K untouched" | PARTLY — code fact true; consequence REFUTED (0.86 µs vs 1.06–57 ms/decode, ≤0.1%, bit-identical over 200 decodes; the +15.4/−11.0 straddle refutes the mechanism) | **No code change** (declined as churn); §14.6a wording corrected |
| P2 scheduler v4 orphans K states | PARTLY — mechanics true; marginal invalidation set EMPTY (no v3 state exists on disk; pre-branch states already v2-orphaned) | **No code change** (hand-bump doctrine stands); scope sentences corrected in v0.54 + PHASED-SCHEDULE |
| P2 --refine U tail / empty audits / lane attribution / drift-exit-0 | CONFIRMED (all small; §14 numbers unaffected — external derivations were correct) | **FIXED** — CLI help, truth-path vacuity predicate, u-lane classification + per-cert lane ids, derivation scripts committed |
| P2 memory envelope | CONFIRMED as deployment constraint (not a campaign regression) | **Deferred** — admission check is a deployment-epoch item; stale +34% comment fixed |
| P3 u-prefix parser fail-open | REFUTED as defect — documented, test-pinned, fails in the safe direction | No change |
| P3 PHASED-SCHEDULE / diag snapshot starvation | CONFIRMED | Supersession note added; snapshot starvation stays a recorded P8 follow-up |

The review's Packet 4 (codec-capability registry, component-neutral evidence
types, stage-composition protocol) is out of this campaign's lane by standing
user ruling — it is recorded as input to the separate harmonization line the
user opens. The review's closing recommendation — a physical holdout across a
new sheet/day/toner/scanner epoch before any population-level claim — is
adopted as the natural first act of the next print day.
