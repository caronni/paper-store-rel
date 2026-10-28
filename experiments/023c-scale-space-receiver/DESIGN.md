# E023c production cascade design

**Implementation contract, revision 1 (2026-07-17).**

This document specifies the clean E023c receiver implemented by
`run_e023c.py`.  Normative language describes the current receiver unless a
section explicitly says “future” or “E024”.  This contract is independent of
any one measured scan; the checked single-capture evidence is recorded in
`RESULTS.md` and `E023C-CASCADE-HP1200.json`.

## 1. Objective and non-objectives

E023c maximizes conflict-free, syndrome+CRC-certified payload recovery from
one or more physical scan captures.  It exploits the empirical fact that
the existing segmentation, placement, sampling, calibration, and nonlinear
LDPC path extracts complementary results at different raster scales even
though deterministic decimation creates no new physical information.

The intended algorithm is a small monotone cascade:

1. begin at the lowest physically useful scale, normally two scan pixels per
   printed cell;
2. run the ordinary E021/E022/E023b path on those pixels;
3. commit only authenticated poses, bounded losing hypotheses, and certified
   payload facts at a barrier;
4. use those facts as proposals or exact labels at the next scale;
5. repeat until native resolution or optional verified volume recovery.

The following are non-objectives:

- changing the printed format;
- treating scale views as independent captures;
- summing or averaging LLRs across scale lanes;
- accepting a lower-scale placement without current-raster validation;
- recursive image resizing;
- using fountain symbol count as an LDPC stop oracle;
- a full feedback/replay fixed point (E024);
- a new PSF/EWA/Jacobian-shaped payload sampler in this revision.

## 2. Layer boundaries

E023c is an orchestration layer.  Numerical ownership remains clear:

- **E021** detects payload regions in the current scale raster.
- **E022** searches pilot windows, fits affine poses, resolves discrete
  page/address/orientation, and enforces pilot acceptance gates on current
  pixels.
- **E023b** converts accepted placements to payload evidence, applies the
  selected detector (including context/PAVA), freezes one owner per physical
  capture and cell, and performs LDPC syndrome+CRC attempts.
- **E023c** derives scale views, orders barriers, transfers bounded hints,
  offers an optional certificate-labelled pose proposal, keeps decoder lanes
  independent, unions certificates, persists state, and observes optional
  volume completion.

E021 is unchanged.  E022 has one default-preserving extension: an optional
`lower_hints` route plus the fitted-pose audit needed to retain a bounded
losing tail.  With the default empty hint sequence, standalone E022 follows
the same numerical path and configuration schema.  E023c otherwise calls the
ordinary production route through E023b-compatible objects.

## 3. Identities and terminology

- A **physical capture** is one scanner acquisition.  It has a stable,
  user-supplied `capture_id` and authenticated source identity.
- A **level** is one target ppc in the frozen scale plan.
- A **view** is the deterministic raster for one `(capture, level)`, always
  derived directly from that capture's native raster.
- A **lane** is one persistent E023b `ReceiverSession` for one scale level.
  It accumulates independent physical captures at that scale.
- A **barrier** is the atomic completion of one `(capture, level)`.
- A **certificate** is a tile payload that has passed LDPC syndrome and CRC.
- The **portfolio** is the conflict-checked union of certificates from all
  lanes.
- The **NeedMap** is the residual acquisition frontier derived from the
  format atlas, latest pilot state, lane tile states, and portfolio.

The same physical `capture_id` is used as E023b's scan-voter identity in
every scale lane.  A view has separate source and level provenance, but it
does not acquire a new vote identity.

## 4. Scale-space construction

### 4.1 Native sampling and automatic schedule

For a format with `cell_factor = c` and a scan at `native_dpi`:

```text
native_ppc = native_dpi * c / 600
```

The default floor is 2 ppc.  If `native_ppc <= floor`, the schedule contains
only native.  Otherwise `auto_ppc_levels()`:

1. starts at the exact floor;
2. advances approximately by powers of two;
3. prefers target levels corresponding to integer native box divisors when
   they give a healthy ladder;
4. removes duplicates and keeps strict increasing order;
5. always appends exact native ppc.

There is no upsampling.  An explicit `--ppc-levels` list is parsed as exact
rationals, deduplicated, sorted increasingly, rejected if any value exceeds
native, and completed by appending native if needed.

The frozen scale plan belongs to the state envelope.  Resume cannot alter it.

### 4.2 Direct-native area resampling

Let

```text
s = native_ppc / target_ppc = p / q
```

be native pixels per output pixel.  Every output view is computed from the
immutable native array, never from a previously reduced view.  In continuous
pixel-boundary coordinates, output pixel `j` integrates native support

```text
[j*s, (j+1)*s]
```

and divides by the exact support area.  Only complete output pixels are
emitted; partial bottom/right pixels are discarded.  The rational separable
implementation is chunk-invariant and bounded-memory.

For integer `s`, the implementation preserves the E018 integer box operation
order and byte convention.  For non-integer `s`, uint8 grey/RGB input uses
exact integer overlap numerators, an explicit overflow guard, and exact
ties-to-even output rounding.  Other numeric dtypes use the same deterministic
support geometry with float64 accumulation.  Neither path uses PIL's
scale-dependent resize heuristics.

Each materialized view is content-addressed by source hash and level, and its
hash/size are stored with the completed level and lane scan.

### 4.3 Coordinate and pose transfer

Array coordinates refer to pixel centres.  For one axis:

```text
native = s * (view + 0.5) - 0.5
view   = (native + 0.5) / s - 0.5
```

For an affine pose transferred from native to a target view:

```text
origin_view = (origin_native + 0.5) / s - 0.5
J_view      = J_native / s
pitch_view  = pitch_native / s
```

The inverse transfer multiplies the Jacobian and pitch by `s` and applies the
inverse half-pixel origin transform.  Phase, canonical page address, and
orientation do not change.  Lower-to-finer transfer is always composed
through native coordinates; it never relies on accumulated floating-point
ratios between adjacent views.

The Jacobian is therefore already used in E023c for exact pose-coordinate
transfer.  It is not yet used to define an anisotropic payload integration
footprint; that remains a separately measurable sampler experiment.

## 5. Capture and barrier ordering

Captures are serialized.  For capture `i`, all scheduled levels run in
strict coarse-to-fine order before capture `i+1` is admitted.  At a level:

1. fork the last committed outer state;
2. materialize the view directly from native;
3. derive continuation hints from the nearest productive committed lower
   level;
4. snapshot the current certificate portfolio as the input frontier;
5. run E021 and E022 on the current view;
6. build an ordinary generation-0 E023b scan record;
7. optionally propose and gate certificate-driven continuous pose changes;
8. if any proposal is adopted, rebuild the scan record from current pixels;
9. apply the final record to this scale's independent E023b lane, skipping
   globally certified tile keys;
10. optionally run max-150 BP on that changed lane frontier;
11. synchronize attempts, dependencies, pilot knowledge, and newly certified
    tiles into the outer state;
12. optionally test real volume completion;
13. atomically commit the level and capture state.

Provisional work is not authoritative.  A crash before step 13 leaves the
last valid barrier available for deterministic replay.

The dependency order is lexicographic `(capture ordinal, scale ordinal)`.
Every dependency of a new attempt or certificate must have been born at a
strictly earlier barrier.  Same-level feedback is forbidden by construction.

## 6. Lower-level pilot continuation

### 6.1 Accepted placements

Each accepted E022 placement at a lower level becomes a
`lower_accepted` proposal.  The pose is mapped lower-view → native → target
view with the exact transform above.  Canonical page, address, and
orientation are retained as a hypothesis, not asserted as truth.

### 6.2 Bounded runner-up ledger

E022 records algorithm-consumed `window_audit` diagnostics for unresolved
windows.  E023c reifies at most two best losing candidates per region by
default.  A candidate must contain a complete fitted pose and discrete
address hypothesis.  Ranking is deterministic: held-out validation mismatch,
fit mismatch, then support.

These `lower_runner_up` proposals keep a small useful tail without carrying
an unbounded placement graph.  `window_audit` is included in the authoritative
semantic digest because changing it can change later search.

### 6.3 Current-pixel gate

Continuation hints enter E022's search route only.  E021 still segments the
current raster.  E022 refits each proposed route and applies all ordinary
current-raster support, mismatch, rival, validation, and address gates.  A
hint cannot mint a placement or pilot vote on its own.

The runner searches committed prior results from nearest to farthest and
selects the first one that yields hints.  Consequently, a blank or
unproductive intermediate scale cannot erase an older useful route.

## 7. Payload processing and bounded pose refinement

E023b first creates a normal generation-0 scan record using the selected
detector profile.  This preserves ordinary sampling, context/PAVA,
one-owner, and evidence bookkeeping even when no feedback proposal is
eligible.

If the input portfolio contains certified tiles, E023c regenerates their
exact printed payload labels from format seed, keystream, shortening mask,
and certified user bits.  For each accepted placement:

1. collect labelled cells overlapping that window;
2. use E024's bounded pose-only fitter to create a proposal;
3. require its existing eligibility, training, and held-out adoption gates;
4. retain the original pose if any gate fails;
5. if adopted, alter only continuous affine pose;
6. preserve discrete page, origin, orientation, and pilot evidence;
7. resample and redetect the payload once from the current view pixels.

The level dependency set is the conservative union of certificates whose
printed labels contributed to an adopted refinement.  It is interned in the
outer state and bound to the resulting attempt/certificate provenance.

This is a single forward opportunity, not iteration.  It uses only the
portfolio present at level entry, so a certificate produced at this level
cannot influence another window in the same level.

## 8. Scale-lane isolation

Each scale has one lane identity derived from `(level_id, lane_kind,
parent)`.  The current design uses one `primary` lane per level.  It is not
capture-scoped: subsequent independent captures at the same scale extend the
same E023b session and may legitimately combine evidence there.

The following are forbidden across scale lanes:

- LLR addition or averaging;
- hard-decision voting;
- treating view support as another physical pilot vote;
- copying an uncertified tile outcome;
- reusing a decoder state as a finer lane's initial state.

The complete E023b lane session remains persisted, including scan records,
E021 survey, E022 result and audit, immutable window evidence, owners, decoder
tile states, and attempt ledger.  This provides replay substrate without
changing E023b's numerical semantics.

Within a lane, E023b stops spending decoder work on already lane-certified
or degenerate tiles.  On application of a new scale-level record, E023c also
passes the global certified tile frontier as `skip_tiles`: a certificate is
already final for the global objective, although the complete frozen scan
record remains available for replay and future analysis.

## 9. Certificate-only portfolio

Only E023b outcomes in state `certified` enter the portfolio.  Certificate
identity binds format/seed through the state envelope and binds tile key,
rate/bit capacity through the decoder configuration, and exact user bits
through the certificate digest.

Merging follows two rules:

1. same tile and bit-exact payload: retain one certificate and union lane,
   attempt, source, and dependency provenance;
2. same tile and differing payload: raise a fatal integrity error.

There is no “best” conflicting certificate.  CRC collision or state
corruption must be visible rather than resolved heuristically.

Each synchronized attempt records its birth capture/level/lane, stage,
decoder profile, iterations, syndrome/CRC result, evidence identity, actual
contributing physical capture ids, per-scan tile-evidence digests, and
dependency-set id.  Repeated aggregate hashes are not substituted for real
contributors.

## 10. Residual NeedMap

NeedMap is a logical derived view, not an independently mutable persistent
object.  At a committed barrier it can be reconstructed from:

- the known format/page tile atlas;
- `certificate_union` as the authoritative solved payload set;
- per-lane E023b tile state (`certified`, `attempted_failed`,
  `below_attempt_floor`, `degenerate`, or unseen);
- the latest committed combined pilot summary (`unseen`, `addressed`,
  `solved`, and conflict state);
- optional fountain block rank/shortfall as completion metadata only.

This separation prevents two solved-set authorities from drifting.

The current receiver deliberately does not use the payload NeedMap as a hard
spatial crop for E021/E022.  There are three reasons:

1. pilot/pose need and payload-tile need are different fields;
2. acquisition windows overlap, so a solved tile may anchor or validate an
   unresolved neighbour;
3. an independent capture at the same lane can improve a previously failed
   tile even where another lane certified nearby material.

The derived NeedMap is used for residual accounting, pane-D diagnostics,
certificate skip decisions, qualification, and optional completion.  Safe
priority scheduling or hard pruning can be evaluated later against this
canonical frontier without changing what “solved” means.

## 11. State envelope and authoritative digest

The E023c schema begins at version 1 and intentionally offers no compatibility
with the earlier factorial prototype.  A state envelope freezes:

- algorithm and schema id;
- format id, format seed, LDPC rate, selected pages, native DPI;
- exact ordered `ScaleSpec`s and resampler ids;
- detector profile and complete E022 search-configuration digest;
- run-policy digest (lower hints, runner-up bound, forward refinement, BP
  retry policy);
- optional manifest hash;
- implementation hashes for E023c, feedback, fountain, scorer, and the
  transitive E021/E022/E023b numerical closure.

Source records bind path, file hash/size, raster shape/dtype, native DPI, and
physical capture id.  A moved source may replace its path at resume only
after its bytes and metadata authenticate as the same source.

The authoritative digest recursively covers semantic dataclass fields,
mappings, arrays, and opaque lane objects.  Algorithm-consumed nested state,
including `SearchResult.diagnostics["window_audit"]`, is semantic.
Explicitly marked observer fields such as rendered diagnostics and timings
are non-semantic.

Validation replays structural invariants:

- scale plan strict order and native final level;
- unique source and capture identities;
- capture/level/checkpoint status consistency;
- lane identity, parent closure, and lane semantic digest;
- attempt/certificate origin and evidence identity;
- dependency existence, acyclicity, and earlier-barrier order;
- certificate union conflicts and frontier replay;
- latest pilot state from the latest committed barrier;
- explicit early-stop/skipped tails.

State is written by serializing a validated snapshot to a temporary file in
the destination directory, flushing and `fsync`ing it, atomically replacing
the target.  Load rejects a bad schema, envelope, stored digest, lane digest,
or invariant.

## 12. Resume and idempotency

On invocation, persisted unfinished captures are scheduled before any new
capture.  A capture transaction may be `pending`, `in_progress`, `exhausted`,
or `early_stopped`; individual finer levels after verified recovery are
explicitly `skipped_volume_verified`.

An exact already-exhausted capture is an exact no-op.  A previously verified
capture is also a no-op unless `--complete` is requested.  In complete mode,
skipped levels become pending and are reconstructed from the authenticated
stored source path, or from an explicitly supplied replacement with the same
identity.  Completed lower levels and lanes are not replayed.

A new capture cannot be appended while an earlier transaction is unfinished.
This keeps the dependency barrier total order simple and makes one multi-scan
invocation equivalent to repeated one-capture invocations under the same
envelope.

## 13. Optional real fountain completion

The manifest is an optional outer observer and policy oracle.  It must match
the exact registered format/layout/encoding/rate and cover all requested
volume pages.  After each committed candidate frontier, completion code:

1. validates the certified tile's page, key, bit length, and symbol capacity;
2. extracts its genuine fountain symbols;
3. invokes the production volume decoder;
4. reports each block's rank and shortfall;
5. verifies reconstructed byte length and SHA-256.

Early stop is legal only after step 5 succeeds.  Merely having enough symbols
or full apparent rank is not sufficient.  If reconstruction claims success
but the expected SHA fails, the run terminates with a fatal integrity error.

Without a manifest there is no outer stop and every scale/capture is
scheduled.  With a manifest, default mode stops after verified recovery and
marks the remaining levels explicitly skipped.  `--complete` records the
verification but continues through native.  No fountain rank, shortfall,
decoded byte, or failure mode changes pilot or LDPC acquisition.

## 14. Diagnostic semantics

Diagnostics reuse the E022/E023b four-pane language and add scale/portfolio
metadata:

- pane A: current view and E021 segmentation;
- pane B: current accepted E022 placement/pose state;
- pane C: combined pilot sheet across lanes and physical captures;
- pane D: current lane payload/LDPC state, global certificate portfolio,
  residual state, and optional volume progress.

Pane C groups/deduplicates by physical capture.  Seeing one pilot in several
deterministic views is view support, not several independent votes.  Solved
and conflicted states are computed from the combined observation set so a
tile cannot be double-counted into an impossible negative addressed total.

The live publisher emits complete page frames at the following semantic
milestones, and also exposes transient status between them:

```text
level_open
e021_complete
e022_window_progress     [transient: open, pose, route, refine, terminal]
e022_region_complete
pilot_level_final
context_region_complete
pose_refine_window_progress
payload_region_emitted
level_owner_frozen
ldpc_attempt             [transient]
bp_retry_attempt         [transient]
bp_retry_complete
fountain_check
level_complete
capture_committed
session_complete
```

Window snapshots are detached observer values, not additions to
`SearchResult` or `window_audit`. They carry the active scan bounds, fitted
origin/Jacobian/angle/pitch/phase, placement candidate, attempted address
routes, and queue/anchor counts. Pane A overlays the active source window and
the two fitted lattice basis vectors; pane B overlays the current canonical
candidate. Attempt snapshots identify the latest pane-D tile and expose only
the already-recorded decoder metrics. Because the observer callback follows
the evaluation barrier, this marker is the latest completed attempt rather
than a claim about a decoder concurrently executing in another thread.

Transient text status is updated on every event. Combined-pilot construction,
four-pane composition, PNG encoding, and persistence are wall-clock throttled
(three seconds by default), with forced renders at semantic milestones and
the first fitted E022 pose (or terminal refusal) and first LDPC result. The
interval is anchored after render completion, so a render slower than the
interval cannot make every following callback immediately eligible. The
throttle is an observer policy and is not in the state envelope. Observer
wall time, including snapshot construction, is excluded from recorded
numerical timings, and enabling diagnostics cannot alter queue order,
placement gates, evidence, attempts, certificates, or authoritative state.

Page tabs are independent and frame metadata includes level, ppc, effective
DPI, capture, stage, pilot totals, lane totals, global certificates, and
completion state.  File and HTTP publication are best-effort observers.  An
observer exception cannot mutate, abort, or roll back the receiver.  The JSON
report is rebuilt directly from committed state.  When `--out` is requested
and the retained scan/view path remains readable, the final PNG is likewise
rebuilt even when live diagnostics were disabled, failed, or the invocation
performed no numerical work.

## 15. E024 boundary and retained replay surface

E023c's certificate-labelled refinement is a bounded forward edge:

```text
earlier committed certificate -> finer-level pose proposal -> one gated pass
```

E023c does not:

- send a new finer-level certificate back to a completed lower level;
- iterate generations until a fixed point;
- retrain context/PAVA or payload detector parameters from decoded truth;
- reopen segmentation globally;
- invalidate descendants and dependency-replay them after an ancestor
  changes;
- use fountain feedback to request acquisition.

Those operations belong to E024.  To make them possible without weakening
current semantics, E023c retains exact dependencies, source/view identity,
opaque per-scale E023b sessions, immutable window evidence, accepted poses,
and the bounded `window_audit` loser ledger.  E024 can therefore select and
replay a dependency cone rather than rediscovering provenance.

## 16. Failure policy

The following are fatal, not warnings:

- state envelope or implementation mismatch;
- source identity change under an existing capture id;
- derived-view identity mismatch;
- duplicate physical capture in one lane;
- cross-scale certified-bit conflict;
- missing or future-barrier dependency;
- lane or authoritative digest mismatch;
- manifest/format mismatch;
- fountain reconstruction with wrong expected SHA.

Ordinary E021/E022 refusal, lack of pose-refinement labels, LDPC failure, a
below-floor tile, and an ineligible BP retry are normal residual states.  They
remain visible in the NeedMap/report and are carried to the next independent
opportunity.

## 17. Qualification contract and status

The production qualification establishes, without using ground truth in
acquisition:

- direct-native scale bytes and exact coordinate round trips;
- serial/restart equivalence and duplicate no-op behavior;
- current-pixel refusal despite an attractive lower hint;
- nearest productive lower-hint fallback and bounded runner-up behavior;
- no same-level certificate feedback;
- per-scale LLR isolation and same-capture anti-double-counting;
- bit-exact conflict-free certificate union;
- atomic state and semantic tamper rejection;
- manifest stop only after real decode plus SHA;
- `--complete` continuation to native;
- diagnostics on/off and observer-failure equivalence;
- all certified payloads correct against truth after the blind run;
- recovery, exclusive-set, decoder-cost, and state comparisons for
  every level and the final portfolio;
- a current-code endpoint control with the same source and policy, so the
  intermediate scale's marginal benefit is not inferred from a historical
  implementation.

The checked 2026-07-17 HP C3/1200 result passes every gate for its pinned
`bdc9c54` implementation closure.  The automatic 2 → 3 → 6 ppc cascade
certifies 754 correct, conflict-free tiles.  It is a strict seven-tile
superset of the then-current 2 → 6 endpoint control and a 24-tile superset
of the historical 730-certificate native E023b state.  The real fountain
decoder reconstructs and hashes the expected payload.  This is a
single-capture architectural and numerical qualification, not a claim of
cross-scanner, cross-print, or schedule-optimal generalization.

The live-observer revision described above deliberately changes the pinned
E023c/E022 source fingerprints.  Diagnostics-on/off, observer-failure, and
fixed-clock byte-equivalence tests show that it does not change numerical
decisions, but the old blind states remain historical evidence rather than a
qualification of the new fingerprint.  Fresh blind C2/C3 states and controls
are required before `current_implementation_matches_state` can pass again;
the qualification guard and old reports must not be repinned by hand.

Historical NN/DD/ND/DN factorial counts in `E023C-QUALIFICATION.json`
describe the superseded prototype, not this cascade.
