# Experiment 024 — certified-feedback receiver

**Status: E024.0 implemented; own-branch and union-seeded real-sheet
factorials both passed, 2026-07-16.**

E024 should be the first receiver generation in which a successful LDPC
decode changes how the original scans are interpreted.

The central idea is:

> CRC-certified tiles become dense, exact printed-cell labels; those labels
> revise nearby detector and pose hypotheses on the original pixels; revised
> evidence supersedes its parent; only changed unresolved tiles are decoded;
> new certificates seed the next generation.

This is the clean successor to E018's repass experiment, built on E023b's
much richer state and stricter evidence accounting.

E024 remains **LDPC-and-below**. It does not perform fountain/RaptorQ
accounting, decide whether a volume is recoverable, or define a session
completion condition.

The remainder of this document records the design rationale. The implemented
resolution is:

- an append-only E024 overlay over an immutable, externally referenced E023b
  state;
- four registered profiles: `control`, `recal`, `refine`, and `combined`;
- exact certificate-to-printed-label regeneration;
- weighted dense PAVA plus ordered-context recalibration;
- bounded angle/phase pose search with the generation-zero detector frozen
  exactly in the pose-only arm;
- same-pose recalibration fallback in `combined`, so it is a true 2×2 arm;
- one comparable owner-ranking scale: unweighted loss on the fixed E023b
  pilot-validation sites;
- conservative ownership-decision dependencies, target-safe predecessor
  fallback, and one contribution per physical capture;
- changed-target-only max-60 decoding followed by max-150 union retry;
- synchronous generation barriers and a persisted terminal fixed point;
- streamed window labels, cached page maps/keystreams, tile-sliced evidence,
  generic old/new scan projections frozen per generation, with target-safe
  predecessor-walk projections recomputed only when dependencies require
  them.

Production code lives in
[`src/paperholo/feedback.py`](../../src/paperholo/feedback.py),
[`src/paperholo/feedbackstate.py`](../../src/paperholo/feedbackstate.py), and
[`run_e024.py`](run_e024.py). Invocation examples are in
[`HOWTO.md`](HOWTO.md); measured results are recorded in
[`QUALIFICATION.md`](QUALIFICATION.md).

## 1. Recommendation in one page

E024.0 should be a targeted, synchronous, generation-based feedback
experiment over a frozen E023b state. It should not rerun the entire
E021 → E022 → E023b chain.

The first qualification should isolate the two mechanisms that E018 repass
combined:

| arm | pose | detector |
|---|---|---|
| control | generation-0 pose | generation-0 detector |
| recal | unchanged | certified-label recalibration |
| refine | bounded certified-label pose refinement | generation-0 detector |
| combined | bounded pose refinement | certified-label recalibration |

The proposed feedback action is:

1. freeze the current certificate set;
2. regenerate exact physical ink labels from those certificates;
3. find unresolved tiles and the existing windows that can affect them;
4. build target-safe detector and/or pose revisions;
5. accept revisions only through held-out labels and the inherited
   discrete-placement contract;
6. re-freeze one observation per physical capture and page cell;
7. retry only unresolved tiles whose legal evidence digest changed;
8. commit all newly certified tiles together;
9. begin another generation only if the new certificates make new revisions
   possible.

The generation barrier is important. Certificates produced during a
generation cannot train another revision until the next generation. This
makes the result independent of tile/region processing order and prevents
same-round self-support.

E024.0 should stay deliberately local:

- no E021 re-segmentation;
- no unrestricted E022 page search;
- no free-form warp or global bundle adjustment;
- no altered LDPC/CRC acceptance;
- no use of uncertified LDPC beliefs as labels.

Those are later experiments, not hidden parts of the first loop.

## 2. Why this is worth doing

E018 proved the basic mechanism on real scans. Its feedback repass moved a
four-scan state from 197 to 216 certified tiles, reached a fixed point in
three rounds, and produced zero wrong certifications over the audited
certified field.

E018 also exposed the right target class: many failed tiles were below the
ordinary LDPC BER cliff overall, but their errors formed spatially clustered,
confidently wrong regions. More BP cannot correct a systematically wrong
local observation as efficiently as revisiting the local pose/calibration on
the glass.

E023b now provides a much cleaner substrate:

- losslessly packed E021 region masks;
- complete E022 placements, redundant poses, and losing-hypothesis ledger;
- generation-0 raw cell means for every placed window;
- non-owner window evidence;
- exact source TIFF identities and poses;
- calibrated emissions and owner lineage;
- evidence-addressed LDPC attempts;
- CRC-certified user bits and rates.

The remaining E023b failures also suggest two distinct jobs:

- `attempted_failed` tiles are plausible detector/pose/owner clientele;
- `below_attempt_floor` and unobserved cut-line tiles need new coverage or
  placement and belong mainly to a later dense-field acquisition arm.

The first experiment should measure those jobs separately.

## 3. What E024 inherits as hard law

### 3.1 Certified-only firewall

Only syndrome+CRC-certified payload bits may become payload labels.
Uncertified hard decisions, BP marginals, and decoder extrinsic LLRs do not
cross the E024.0 feedback boundary.

For a certified tile, the authoritative value remains:

```text
(tile address, LDPC rate, certified user payload bits)
```

The complete codeword is regenerated, shortened slots are handled through
the format mapping, and payload bits are XORed with the page keystream to
recover physical printed ink values. These labels are never persisted as
fabricated raw observations or infinite LLRs.

### 3.2 Supersede, never sum

A revised sample comes from the same physical capture as its parent. It is an
alternative interpretation, not new evidence.

The independent evidence unit is:

```text
(capture_id, page, payload_index)
```

For each such key, at most one baseline or feedback revision contributes an
LLR. Independent capture IDs may still be summed in the ordinary way.

This rule also covers:

- recalibrating the same raw means;
- re-sampling after a pose change;
- overlapping windows from one scan;
- native and decimated views of one physical capture.

### 3.3 Monotone certificates

Certified tiles are terminal:

- their bits never change;
- they are never demoted;
- routine decoding never spends another attempt on them;
- a conflicting certificate for the same tile is fatal.

A feedback generation may only add certificates or leave the set unchanged.

### 3.4 Existing gates remain in charge

Feedback is allowed to propose better evidence. It is not allowed to weaken
placement admission, bounded-LLR rules, LDPC syndrome checks, or CRC.

A rejected feedback candidate contributes exactly its parent evidence.

### 3.5 Generation 0 remains immutable

E024 should import an E023b state as an immutable generation-0 artifact,
recording both its complete-file SHA-256 and authoritative semantic digest.
The original E023b state bytes should remain available unchanged; E024's
revision graph is an overlay, not an in-place schema mutation.

## 4. E024.0 algorithm

### 4.1 Import and freeze the starting frontier

The initial entry point should be a state-only post-pass, conceptually:

```text
run_e024.py --fresh --from-e023b e023b.pkl \
  --profile combined --state e024.pkl
```

Starting as a separate post-pass keeps qualification clean, as E018 did, but
without E018's destructive state surgery. Once the algorithm is qualified it
can become the composition root for new scan ingestion.

At the start of one feedback action, freeze:

- the scan/capture frontier;
- all current certificate IDs and dependency closures;
- all unresolved target states;
- the feedback profile/configuration;
- the active evidence projection.

The resulting generation ID is content-addressed. A first no-work evaluation
commits one terminal fixed-point generation so the decision is durable;
repeating that fixed point is an exact no-op.

### 4.2 Export the certified label field

For every current certificate:

1. regenerate its LDPC codeword from certified user bits and rate;
2. discard shortened/off-page slots;
3. map codeword slots to page payload indices;
4. apply the payload keystream to recover printed ink values;
5. retain the source certificate ID for every exported label.

Known pilot labels remain legal and independent of payload certification.

The useful density difference is large: a certified 64×64 payload tile
provides thousands of local labels, versus the sparse pilot field used by
E022. The algorithm must nevertheless treat spatial blocks/tiles, not
individual neighboring cells, as the units of validation confidence.

### 4.3 Plan targets from the unresolved frontier

For each non-degenerate unresolved tile, build a work item containing:

- its current state and latest max-60/max-150 attempts;
- covering generation-0 windows and retained non-owner evidence;
- adjacent certified-label support in each window;
- current informative coverage and contributing captures.

E024.0 revisits only existing accepted windows. It prioritizes:

1. `attempted_failed` tiles with dense nearby labels;
2. `below_attempt_floor` tiles for which owner reconsideration or a bounded
   pose change can add already-audited cells;
3. everything else as measured deferred clientele.

Scheduling order is only a performance hint. All decisions use the same
frozen generation frontier.

### 4.4 Target-safe evidence views

Feedback evidence must be legal for the particular tile being decoded.

Every revision carries the exact transitive set of certificates used for:

- calibration;
- pose refinement;
- gating;
- owner selection;
- search-space or pending-mask pruning.

When gathering evidence for target tile `T`, a revision is illegal if its
dependency closure contains `T`. The resolver walks back through that
cell's revision predecessors until it finds the newest legal value; if none
exists, that capture/cell is an erasure.

This handles the indirect cycle:

```text
A labels a revision that certifies B
B labels a later revision that tries to certify A
```

The latter revision carries `A` in its transitive closure and cannot be used
for `A`.

Target-specific resolution is preferable to globally deleting a useful
revision. The ordinary old/new projection is cached once per scan and
generation. If an active revision depends on the target, the resolver walks
that lineage and recomputes only the target-safe projection on demand.

### 4.5 Recal arm: same-pose certified-label calibration

The lowest-cost feedback arm does not reread the TIFF. It replays E023b's
retained raw means at the generation-0 pose.

Recommended model:

1. retain E023b's robust normalized darkness score;
2. fit a monotone PAVA calibration using SEARCH pilots plus legal certified
   payload labels;
3. fit the existing nine-bin context residual on the same legal training
   field;
4. validate on disjoint pilot parity plus whole held-out certified tiles or
   spatial blocks;
5. adopt only when block-weighted held-out loss improves.

This is the clean place to learn whether context correction “falls out
naturally.” Dense payload labels may:

- make context offsets substantially more stable;
- reveal a better local context correction than pilot-only fitting;
- make the separate context arm redundant;
- or show that context and feedback address different error classes.

The experiment should measure this, not assume it.

Dense labels must not create arbitrarily loud LLRs. Use the existing
bounded-PAVA discipline and a frozen feedback confidence cap/effective
sample-size rule. Thousands of correlated cells in one tile are not
thousands of independent calibration trials.

After every accepted recalibration, re-run deterministic owner selection
over all retained window evidence for that scan. This allows a previously
non-owner window to become the best calibrated observation without creating
another physical vote.

### 4.6 Refine arm: bounded certified-label pose refinement

Pose refinement rereads the exact original TIFF after rechecking its SHA,
size, shape, and dtype.

E024.0 should vary only the local degrees of freedom already exercised by
E022 refinement:

- sub-cell translation/phase;
- small rotation correction.

Keep page, orientation, and the existing affine neighborhood fixed. Do not
fit free shear, elastic warps, or a page-wide bundle adjustment yet.

Use pilots plus legal certified payload labels in the robust refinement
objective. Page, orientation, integer origin, BCH result, placement mismatch,
rival/gap result, and audited core are frozen from the already-admitted E022
placement. E024 does not claim to rediscover those discrete facts. It
rechecks:

- E022's hard pilot-mismatch rule on the authoritative-core pilot population
  against the immutable generation-zero threshold;
- allowed pose delta inside E022's registered refinement box;
- dense held-out log loss on independent spatial blocks;
- pilot train/validation support, retaining all pilot sites even when dense
  payload sites are capped.

Only a pose-changing arm re-samples the TIFF. In the pose-only arm, the
generation-zero detector score/logit path is replayed exactly. The combined
arm fits the registered dense detector and may fall back to the exact frozen
detector when the learned detector refuses an otherwise admitted pose.

### 4.7 Combined arm

The combined arm performs bounded pose refinement and then certified-label
PAVA/context calibration on the newly sampled means.

It is important to keep the four-arm factorial. E018 measured the bundle,
but did not isolate whether its gain came from geometry, detector
recalibration, or their interaction.

### 4.8 Freeze active evidence

Construct every accepted `WindowRevision` before changing active state.

For each scan/capture:

1. choose the active legal revision for each target and window lineage;
2. freeze one owner per page payload cell using the held-out score;
3. produce at most one LLR per `(capture, page, payload_index)`;
4. preserve untouched generation-0 cells byte-for-byte;
5. record cell-granular predecessor/supersession patches.

Cell-granular supersession matters. A new window may improve only part of an
old observation, and the unrevised remainder must survive exactly.

### 4.9 Decode the changed frontier

Compute evidence digests from the resolved per-capture revision IDs and
numeric LLR vectors. Only unresolved tiles whose legal evidence digest
changed are eligible.

Recommended E024.0 schedule:

1. ordinary max-60 BP on changed per-scan evidence where useful;
2. ordinary max-60 BP on the changed independent-capture union;
3. explicit max-150 BP over the resulting changed failed frontier.

Unlike blind retry after every original scan, the residual E024 frontier is
small and every new certificate can unlock the next feedback generation.
The max-150 step should still be separately ledgered so its cost and unique
gain remain measurable.

Identical numeric evidence plus the same decoder profile receives at most one
CRC-bearing attempt, regardless of how many lineages happen to recreate it.

### 4.10 Commit at a generation barrier

All revisions and attempts are built on a private fork. Only after every
target has been evaluated are new certificates committed together.

The next generation may use those new labels. The current one may not.

A feedback action reaches its local fixed point when it creates no new
certificate, or when its new certificates expose no further reachable
candidate windows. Accepted revisions and patches from the terminal
generation remain recorded, but without a changed certificate frontier they
cannot train a distinct next generation.

This is an algorithmic idempotence rule, not a fountain/session completion
condition. A later independent scan or a different registered feedback arm
can reopen the receiver.

## 5. Persistent revision graph

E024 should replace E018's `repassN/...` observation-name surgery with
explicit append-only entities.

### 5.1 Top-level session

Conceptually:

```text
E024Session
  immutable external E023b reference + hashes
  generation records
  evidence revisions
  cell supersession patches
  interned dependency sets
  certificate records
  E024 tile attempts
  active head generation
```

Production state has one head and no in-file branching. Experimental arms
use separate state files.

### 5.2 Generation record

Each generation records:

- stable generation ID and ordinal;
- parent generation;
- frozen label-frontier IDs/digest;
- complete active-revision projection;
- accepted/rejected revision IDs;
- cell patch IDs;
- tile attempt IDs;
- new certificate IDs;
- final active-projection digest.

The first no-work action creates one empty terminal generation. This records
the evaluated frontier and makes every later invocation byte-exactly
idempotent.

### 5.3 Certificate record

A logical certificate ID should be:

```text
H(format, seed, page, tile, rate, packed certified user bits)
```

The origin attempt is provenance, not identity. Same tile and same bits is
the same certificate; different bits or rate for one tile is fatal.

A certificate stores:

- tile/rate/user bits;
- origin attempt;
- birth generation;
- exact transitive dependency set.

Baseline E023b certificates have empty feedback dependencies.

### 5.4 Evidence revision

Every revision stores:

- stable revision and placement IDs;
- generation, capture, scan, placement ordinal, and page;
- one active-lineage parent revision;
- exact label uses and roles;
- transitive dependency-set ID;
- pose and sampled page cells;
- raw means and emitted payload indices/LLRs;
- detector/config identity;
- train/held-out metrics and gate audit;
- accepted/refused outcome.

Baseline lineage derives from the E023b placement ID. E024.0 revises only
those existing windows; it does not create retry windows or new coverage.

### 5.5 Cell patch

The authoritative active projection is reconstructed from generation zero
plus each generation's active revision IDs and stored revision emissions.
An append-only patch is the compact replay-audit sidecar for the cells whose
owner/projection changed:

```text
(generation, scan, capture, page, payload indices,
 previous owner ordinals, new owner ordinals,
 previous/new projection digests)
```

Patches do not carry replacement LLRs and are not independently sufficient
to reconstruct evidence. Their cell/owner arrays and old/new projection
digests must exactly match replay from the authoritative revision graph.

### 5.6 Attempt record

An E024 tile attempt extends E023b's ledger with:

- generation ordinal;
- target tile;
- decoder profile;
- numeric evidence digest;
- per-capture component digests;
- input revision IDs;
- dependency-set ID;
- ordinary coverage/iteration/syndrome/CRC accounting.

Attempt identity is based on target, decoder profile, and numeric evidence,
not merely generation number.

## 6. Transaction and integrity rules

Each feedback generation is atomic; a multi-generation invocation checkpoints
each completed generation and is resumable:

1. validate the current state structurally on a private runtime fork;
2. derive its frontier/action ID;
3. return an exact no-op if the persisted head is already a fixed point;
4. freeze labels;
5. build/gate all revisions;
6. resolve owners and cell patches;
7. decode changed targets;
8. append certificates and dependency closures;
9. validate the completed private generation;
10. checkpoint state/report through atomic replacement;
11. continue from that checkpoint if another feedback generation is exposed.

The lightweight runtime validation keeps an in-flight private fork practical.
At every durable save/load boundary, validation reconstructs generation zero
and exactly replays every production generation, projection, attempt,
certificate, and fixed-point decision, then requires the final authoritative
digest to match. A crash before one checkpoint leaves the preceding
generation intact.

Loading or commit must fail closed if:

- the generation-0 blob/hash/digest changes;
- an embedded certificate-union root does not replay type-strictly through
  the fingerprinted merger, the selected baseline is not an exact source
  artifact, or an external certificate differs from its proven row;
- an ID or dependency closure does not recompute;
- a child uses same-generation or future labels;
- a certifying dependency closure contains its target;
- one tile has conflicting certified bits;
- a certified tile is demoted or routinely decoded again;
- a patch crosses capture/page boundaries or names the wrong predecessor;
- two active values exist for one capture/page/cell;
- two views of one capture enter the independent-capture sum;
- a refused revision becomes active;
- stored pose/detector/emission algebraic replay differs, including the exact
  retained generation-zero score/logit path;
- candidate discovery, a refused decision, decode scheduling, or the
  persisted fixed-point reason differs under sequential production replay;
- a source TIFF identity or metadata changes when a pose arm needs to reread
  it;
- source pixels needed for a pose change do not match their SHA;
- identical numeric evidence/profile spends another CRC attempt;
- a below-floor decision is counted as a decoder/CRC exposure;
- diagnostic activity changes authoritative state.

## 7. Native/decimated shared truth

Native and decimated LLRs remain correlated alternatives and must not be
summed as independent scans.

Certificates are different: once a tile is syndrome+CRC-certified, its
logical printed values are page-global truth. A certificate recovered by the
decimated branch may legally supervise neighboring native pixels, and vice
versa.

This suggests a useful qualification axis:

| label seed | meaning |
|---|---|
| own branch | only certificates already recovered on this footing |
| multiview union | the current conflict-checked 770-certificate E021.6 native/decimated union |

Target leave-out still applies. If the union already contains a certificate
for tile `T`, then `T` is imported as generation-zero truth and is not
counted as an E024 feedback recovery. That certificate may train revisions
for neighboring unresolved tiles, but no revision that depends on `T` may
causally support certifying `T` again.

The clean order is:

1. qualify E024.0 independently on each footing;
2. run the best feedback arm with own-branch versus union label seeding;
3. keep the two evidence branches separate;
4. conflict-check and union only their final certificates.

The historical E023c factorial separately qualified NN/DD/ND/DN at
752/757/749/756 and a correct all-four union of 772, but it is not a drop-in
E024 seed. It ran from
byte-pinned legacy E023b.0 state-v1 footings before E021.6, and its checked
report does not persist packed per-tile certificates or certifying-attempt
ledgers. Current E024 requires the exact selected E021.6 source artifact
inside a canonically replayable trust root.

The completed own-branch E024 `refine`/`combined` union also has 772
certificates, but it is a different frontier. The two qualified sets overlap
on 770 tiles: E023c alone has `(0,21,16)` and `(0,27,21)`, while E024 alone
has `(0,7,22)` and `(0,27,12)`. Their observer-audited set union is 774
correct tiles. A usable import of that legacy result therefore requires a blind E023c rerun with a
replayable lane-certificate exporter and a conflict-checked composite bundle
that also contains the exact current E021.6 footings. Converting the report
alone is insufficient.

The current production E023c cascade has a different, stronger footing: its
authenticated state embeds the complete current-schema E023b session for
every scale lane. The retained experimental adapter
[`e023c_e024_bridge.py`](e023c_e024_bridge.py) can export those sessions
without altering the
cascade, construct their exact union with the official E023b merger, run one
independent union-seeded E024 state per lane, and audit the final portfolio.
Only syndrome+CRC certificates cross correlated lanes; their LLRs are never
summed. This is safe experimental composition, not yet an integrated
production E023c→E024 entry point or a backward-replay loop.
The focused contract and commands are in
[`E023C-BRIDGE.md`](E023C-BRIDGE.md).

### 7.1 HP E018b current-stack validation

The compact retained machine record is
[`HP-E018B-QUALIFICATION.json`](HP-E018B-QUALIFICATION.json). It separates
raw LDPC certificates from fountain-useful symbols:

| format / generation-zero route | LDPC start → final | useful start → final |
|---|---:|---:|
| C3 / native E023b+BP | 730 → 734 | 709 → 712 |
| C3 / production E023c 2→3→6 | 754 → 754 | 731 → 731 |
| C2 / native E023b+BP | 1,416 → 1,423 | 1,358 → 1,358 |
| C2 / production E023c 2→4 | 1,438 → 1,439 | 1,363 → 1,364 |

Native C3 adds three useful tiles and one inert edge tile. Native C2 adds
seven certificates, but every one is a column-34 edge address outside the
fountain-symbol domain. After E023c, C3 gains nothing and C2 gains one useful
tile `(0,18,26)`.

The post-E023c cost makes the conclusion identifiable. Across the three C3
lanes, E024 accepts 24 revisions, changes 250,806 cells, and spends 58 CRC
calls / 12,180 BP iterations for zero gain. Across two C2 lanes it accepts
102 revisions, changes 1,696,545 cells, and spends 461 CRC calls / 96,682 BP
iterations for one tile. In both formats the standalone E023b→E024 final set
is a strict subset of the E023c→E024 final set.

The standalone v1 audits are historical unbound observers. The post-E023c
v2 audits are `QUALIFIED_BOUND`: exact adopted exports and official-union
sources bind to every baseline/state/report, all non-truth inputs are
replayed and frozen before hashed ground truth, generation-zero certificates
are neither lost nor changed, start/final unions are conflict-free, and
every final certificate is correct. Their hashes are `2b70cdaa...75a4` (C3)
and `8f54ac71...11f2` (C2). The result supports
keeping affine `refine` as a bounded tail experiment, while prioritizing a
seam-aware piecewise-pose plus explicit support-revision arm for the next
distinct mechanism.

## 8. Diagnostics

E024 reuses E023b's four-pane renderer and adds an E024 generation/profile/
certificate/revision/CRC footer. During an in-flight attempt it renders:

- the source scan that supplied the per-scan attempt, or a relevant revised
  scan for a union attempt;
- the explicit provisional active-revision map used by that decode;
- the working tile state and active-target highlight in Pane D.

Committed-generation frames render the committed head. This distinction is
important: diagnostics never substitute the previous head for evidence that
is being decoded.

The JSON report and state carry the detailed causal data—revision IDs, label
uses, dependency sets, old/new projection digests, pose/support/loss/gate
metrics, attempts, BP iterations, and certificate births. A richer clickable
overlay for those fields remains a diagnostic presentation improvement, not
an algorithm or accounting dependency.

The viewer remains observer-only. Diagnostic failures cannot affect a
feedback transaction.

## 9. Qualification design

### 9.1 Primary factorial

Run the four E024.0 arms on both frozen footings:

- decimated 1600 dpi;
- native 4800 dpi.

Use `ctx-pava-v1 + BP` as the primary starting state.

Ground truth is opened only after every blind arm has produced compact
certificate-bit and non-ground-truth accounting records.

E024.0's first real-sheet qualification runs the full 2×2 mechanism
factorial on the `ctx-pava-v1 + BP` substrate. Regenerating and repeating the
entire experiment on a `pava-v1 + BP` substrate is explicitly deferred as a
substrate-control follow-up; it is not silently counted as part of the
current result.

The completed own-branch factorial found:

| footing | control | recal | refine | combined |
|---|---:|---:|---:|---:|
| decimated | 757 | 758 | **759** | 759 |
| native | 757 | 757 | **762** | 761 |

All certificates were correct, monotone, and conflict-free. `refine` is the
best own-branch arm: it equals or exceeds `combined` on both footings while
doing less work. Merging the two `refine` outputs produces an exact,
conflict-free 772-certificate union, two beyond the 770-certificate
generation-zero union. Full accounting and exact recovered tile addresses
are in [`QUALIFICATION.md`](QUALIFICATION.md).

The separately qualified 770-certificate seed makes the operational result
cleaner:

| footing | control | recal | refine | combined |
|---|---:|---:|---:|---:|
| decimated + union seed | 770 | 770 | **772** | 772 |
| native + union seed | 770 | 770 | 770 | 770 |

Thus the maximum measured persistent state is produced by importing the
trusted 770-certificate union into the decimated footing and running
`refine`. It recovers `(0,7,18)` and `(0,7,22)` and reaches the exact same
certificate set and bits as the merged own-branch `refine` result. Native
feedback adds no global certificate once the decimated branch's 13 exclusive
certificates are already seeded.

### 9.2 Hard gates

1. Generation-0 E023b state and certificates reproduce exactly.
2. Every certificate is ground-truth correct.
3. No existing certificate changes value or is lost.
4. No certifying dependency closure contains its target.
5. Same-capture parents and revisions are never summed.
6. Rejected candidates produce byte-identical parent evidence.
7. Identical evidence/profile receives one attempt.
8. Save/reload and split invocation are authoritative-digest identical.
9. Repeating a fixed-point action is a byte-identical no-op.
10. A fully certified/no-work fixture commits one terminal generation, after
    which repetition is an exact no-op.
11. Diagnostic on/off produces identical authoritative state.
12. Injected direct and transitive dependency cycles fail closed.
13. Crash before commit preserves the previous generation.

### 9.3 Measurements

For every arm report, with per-generation counts where available:

- certified tile count and exact set/bit digests;
- unique new certificates and factorial interaction;
- gains grouped by generation-zero tile state;
- changed cells and aggregate owner-change counts;
- accepted/refused revisions and refusal reasons;
- detector support ranges and held-out log-loss improvements;
- actual pose-delta distribution and E022 pilot-gate margins;
- dependency-set size/depth;
- max-60/max-150 calls, iterations, and CRC false-accept budget;
- runtime and source-image decodes (file-identity hashing is additional);
- gain by generation and fixed-point depth.

The important comparison is unique recovery, not the naive sum of detector
and pose gains.

## 10. Staged extensions

A concrete seam-aware composition of E024.1 and E024.2, motivated by the
periodic HP-1200 E018b failure bands, is recorded as non-normative further
work in
[`FURTHER-WORK-PERIODIC-SEAMS.md`](FURTHER-WORK-PERIODIC-SEAMS.md).

### E024.1 — dense-field placement retry

Revisit E022's recorded best losing hypotheses and unresolved slivers, but
only inside a bounded neighborhood justified by the generation-0 proposal.

Score candidates using pilots plus legal certified payload labels. A
partial-BCH errors-and-erasures read at a predicted address may confirm a
hypothesis with a quantified false-accept budget; it is never a payload label
source.

This is likely the main coverage-recovery arm for below-floor cut-line tiles.
It stays separate from E024.0 so pose/calibration gains remain identifiable.

### E024.2 — boundary/core-halo recovery

Allow a revised window to emit additional cells near the generation-0
audited core only when:

- the original E021 mask supports them;
- source pixels are present;
- dense held-out labels validate the local pose/detector;
- the extension is explicitly versioned and measured.

Do not silently reinterpret E023b's authoritative core. Support expansion is
a new arm.

### E024.3 — local scale/aperture hypotheses

Use certified labels to select native versus antialiased sampling, or retain
a tiny CRC-gated list of aperture hypotheses for unresolved tiles.

E023c found box3 geometry better under both samplers, while sampler choice
still had local interactions: DN had the lowest BER, DD the best single-lane
count, and ND retained one unique tile. Preserve a small targeted
geometry×sampler list through LDPC—especially DN then ND on the unresolved
tail—instead of averaging views prematurely or encoding one globally
preferred sampler.

### Later — LDPC-extrinsic turbo feedback

LDPC extrinsic beliefs could eventually re-enter detection, but this is a
different honesty regime. It uses uncertified beliefs and needs strict
extrinsic-message accounting to prevent double counting.

Build and qualify the certified-only loop first.

### Probably later or never

- global elastic bundle adjustment;
- unrestricted page-wide placement search each generation;
- full E021 re-segmentation every round;
- large decoder/pose/aperture parameter portfolios;
- treating feedback fixed point as session completion.

## 11. What not to copy from E018

E018 proved the mechanism but also recorded several architectural traps:

- route-based scheduling missed the real clientele: its first repass touched
  correlation-placed pieces while almost all marginal failures sat under the
  word path;
- string-based `repassN/keep/...` lineage caused matcher and round-collision
  bugs;
- destructive drop/re-add risked losing untouched evidence and quality
  metadata;
- include-only failed-tile masks discarded newly obtainable gap coverage;
- re-segmenting every scan every round was expensive and produced no useful
  “failed piece second chance” on the real state;
- dense labels were once paired in the wrong raster order;
- feedback initially amplified an upstream unbounded-LLR defect.

E024 should schedule by graph reachability from unresolved tiles, retain an
immutable revision graph, supersede at cell granularity, and keep bounded
held-out calibration in charge.

## 12. Suggested implementation seams

Keep E023b frozen and build E024 in new modules. The implemented public seams
are:

```text
paperholo.feedback
  export_certified_labels()
  fit_detector_revision()
  refine_pose_on_labels()
  resolve_target_evidence()
  run_feedback_generation()
  run_feedback()
  materialize_receiver_view()
  report_dict()

paperholo.feedbackstate
  E024Session
  GenerationRecord
  CertificateRecord
  EvidenceRevision
  CellPatch
  DependencySet
  FeedbackAttempt
```

Reuse:

- E021 masks and source identity from E023b;
- E022 accepted poses and refinement primitives;
- E023b raw window evidence and owner freeze semantics;
- `payloaddec.evaluate_tile()` and the existing LDPC implementation;
- the four-pane diagnostic framework.

Do not change E021 or E022 numerical behavior for E024.0. Extract shared pure
helpers where necessary, with exact pre/post compatibility gates.

## 13. Resolved implementation decisions

1. **Confidence:** dense recalibration clips base logits at 8 and context
   output at 8. The refine arm replays the E023b detector and its registered
   context clip exactly instead of silently substituting E024 caps.
2. **Validation:** deterministic whole spatial blocks provide independent
   train/validation groups; pilots remain a distinct confidence group.
3. **Support:** eligibility requires 64 payload training labels, 32 payload
   validation labels, at least 20 training and 10 validation labels from each
   class, and at least four spatial blocks. These constants are fingerprinted
   in `FeedbackConfig`.
4. **Ownership:** feedback candidates compete on the same fixed
   pilot-validation loss scale as E023b. Target resolution walks revision
   predecessors when necessary; ownership competition dependencies are
   conservatively included.
5. **BP:** changed evidence receives per-scan max-60, union max-60, then union
   max-150 only after an actual max-60 failure. Every numerical attempt is
   evidence-addressed and deduplicated.
6. **Base artifact:** E024 stores an external E023b reference bound by complete
   file SHA-256, size, authoritative digest, format, pages, rate, and ordered
   captures. Relocation is allowed only when all identities still match.
7. **Entry point:** E024.0 is deliberately a state-only post-pass. It does not
   alter E021, E022, or E023b behavior. Prefix-safe new-scan ingestion remains
   a later composition-root decision.
8. **Durable union trust:** a multiview seed is accepted only after exact,
   type-strict replay through the fingerprinted E023b merger. Its complete
   bytes are embedded in the E024 envelope. Every durable load invokes the
   proof and revalidates the embedded bytes, external rows, and selected
   baseline binding; after the first successful source replay for an exact
   union/merger/receiver hash key, later proofs in that process may use the
   successful proof cache.
9. **Durable production replay:** save/load reconstructs generation zero and
   sequentially re-executes candidate discovery, accepted and refused
   revisions, projections, patches, decode scheduling, certificates, and the
   terminal fixed-point decision.

## 14. References

- E023b feedback substrate and migration rules:
  [`../023b-integrated-receiver/README.md`](../023b-integrated-receiver/README.md)
- E023b context/BP design:
  [`../023b-integrated-receiver/ALGORITHM-ARMS.md`](../023b-integrated-receiver/ALGORITHM-ARMS.md)
- E023b multiview findings:
  [`../023b-integrated-receiver/MULTIVIEW-RECOVERY.md`](../023b-integrated-receiver/MULTIVIEW-RECOVERY.md)
- E023c scale-space qualification:
  [`../023c-scale-space-receiver/RESULTS.md`](../023c-scale-space-receiver/RESULTS.md)
- E018 repass implementation:
  [`../018-confetti-c3-play/repass.py`](../018-confetti-c3-play/repass.py)
- Feedback build discussion:
  [`../../docs/PILOTS-DESIGN.md`](../../docs/PILOTS-DESIGN.md)
- Layer/feedback registry:
  [`../../docs/LAYERS.md`](../../docs/LAYERS.md)
- Periodic seam observation, attribution tests, and bounded recovery sketch:
  [`FURTHER-WORK-PERIODIC-SEAMS.md`](FURTHER-WORK-PERIODIC-SEAMS.md)
