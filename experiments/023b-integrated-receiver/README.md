# Experiment 023b — integrated E021 → E022 → payload/LDPC receiver

**Status: E023b.0 BUILT AND QUALIFIED 2026-07-15; E023b.1 ALGORITHM ARMS,
BP-SCHEDULING, AND CORRELATED-VIEW RECOVERY QUALIFIED 2026-07-16.**

E023 remains the frozen, qualified experiment. E023b starts with a clean
entry point and composes the same qualified lower-layer algorithms into one
persistent, multi-scan receiver session.

Its boundary is deliberately the same as E023's:

> E023b ends with honest per-LDPC-tile outcomes and the evidence needed to
> explain or revisit them. It does not perform fountain/RaptorQ accounting,
> decide whether a volume is recoverable, or define a session stop condition.

`score_e023b.py` is an optional read-only evaluator above that boundary. It
may compute fountain rank for an emitted test volume, but it does not mutate
receiver state or move rank/completion into the E023b algorithm.

The first build is an architectural correction, not a new detector arm. It
must preserve E021, E022 v2.2, and the qualified E023 payload algorithm before
any decoder experiment is admitted.

## 1. User-facing contract

For concise command examples covering baseline PAVA, adaptive BP,
context + PAVA, the combined arm, appending scans, and the exact six-scan
highest-recovery invocation, see [`HOWTO.md`](HOWTO.md).

The preregistered detector/decoder arm design and promotion record are in
[`ALGORITHM-ARMS.md`](ALGORITHM-ARMS.md).

The measured native/decimated overlap, correlation-safe certificate union,
fusion experiments, and scale-space follow-ups are documented in
[`MULTIVIEW-RECOVERY.md`](MULTIVIEW-RECOVERY.md).

The optional single-state volume scorer contract is [`SCORE.md`](SCORE.md).
The pinned [`018b-take-1.sh`](018b-take-1.sh) driver runs the existing four
native E018b cases through context+PAVA, final BP, diagnostics, and scoring.

The design-only successor proposed by the multiview result is
[`../023c-scale-space-receiver/README.md`](../023c-scale-space-receiver/README.md).
It moves native/derived views inside one physical-capture transaction while
retaining a bounded likelihood portfolio rather than prematurely averaging
correlated evidence.

The user invokes E023b directly with one or more TIFFs:

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  scan-1.tiff scan-2.tiff \
  --dpi 4800 --format e018-v3-c3 --pages 0 \
  --capture-groups capture-a,capture-b \
  --state experiments/023b-integrated-receiver/build/session.pkl \
  --diag
```

`--capture-groups` is required for ingestion. Each value names one physical
scanner capture. Independent captures get different ids; TIFFs derived from
the same capture must repeat an id, which E023b refuses to sum twice. The
explicit declaration is intentional: file hashes cannot prove physical
independence for crops, resamples, or metadata-only rewrites.

The same state can be extended by later invocations. A single invocation with
TIFFs `A B C` must have the same authoritative result as three invocations
with `A`, then `B`, then `C`. Each TIFF is one atomic transaction and may
contain scraps from any of the session's legal pages.

E023b.1 adds two explicit, versioned algorithm controls without changing the
default E023b.0 numerical path. Select context + PAVA when creating a state:

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  scan-1.tiff scan-2.tiff \
  --dpi 4800 --format e018-v3-c3 --pages 0 \
  --capture-groups capture-a,capture-b \
  --state experiments/023b-integrated-receiver/build/context-session.pkl \
  --detector-profile ctx-pava-v1 --diag
```

The detector profile is frozen in that state. After ingestion, spend the
separate adaptive-BP action with no TIFF arguments:

```text
env/bin/python experiments/023b-integrated-receiver/run_e023b.py \
  --dpi 4800 --format e018-v3-c3 --pages 0 \
  --state experiments/023b-integrated-receiver/build/context-session.pkl \
  --detector-profile ctx-pava-v1 --bp-retry --diag
```

Repeating the second command without new evidence is a byte-identical no-op.
For the default `pava-v1` profile, omit `--detector-profile` in both commands.

The session envelope freezes:

- format id, seed, page geometry, pilot layout, and legal page set;
- input DPI/footing and the independent-evidence policy;
- LDPC rate and detector profile;
- E021, E022, payload-sampler, and state-schema versions/configuration hashes.

A TIFF whose SHA-256 is already committed is a true authoritative no-op: no
new scan id, decode attempt, rewritten attempt ledger, or tile-state change.
A mismatch in the frozen envelope refuses and asks for another state.

E021 and E022 remain independently runnable tools. E023b is the composition
root; it does not absorb or fork their algorithms.

## 2. One scan transaction

The transaction has a hard barrier between completing pilot placement for the
whole TIFF and authoritative payload/LDPC processing.

```text
validate + hash TIFF
        |
        v
E021 whole-scan survey
        |
        v
E022 one scan-wide search_survey call
  (per-region diagnostic callbacks)
        |
        v
explicit final pilot/BCH frame
        |
        v
payload work plan + per-region/window evidence
        |
        v
freeze one owner per scan/page/payload cell
        |
        v
per-scan LDPC -> changed cross-scan union -> divergence
        |
        v
atomic scan commit
```

### 2.1 E021: one whole-TIFF survey

Run `platen.detect_payload_regions()` exactly once for the TIFF. Retain the
complete `PayloadSurvey`, not just region count, estimated pitch, and `c`.
E024 will need exact region support; masks should therefore be stored
losslessly in packed or compressed form together with their bounding boxes.

Publish an `e021_complete` diagnostic frame before E022 starts.

### 2.2 E022: one scan-wide call, not one fresh call per scrap

Call `pilotsearch.search_survey()` once with the full E021 survey. It already
orders regions largest-first and owns scan-wide pending-site accounting,
anchor reuse, redundant-placement decisions, pilot-observation aggregation,
and the retry ledger.

Use `on_region(result, region_index)` for the requested per-scrap updates.
Calling E022 independently with a fresh `SearchResult` for each scrap would
change the algorithm: it would lose same-scan pilot completion, change which
placements are marked redundant, and discard shared pending masks.

At each callback:

- pane A shows the current TIFF and the completed/active E021 regions;
- pane B shows committed prior placements plus the current partial scan;
- pane C shows the committed pilot map plus current partial observations;
- pane D keeps committed LDPC state and may overlay only provisional geometric
  reach from the completed region.

Prior scans may appear in the combined diagnostic view, but they do not guide
the new scan's initial E022 placement. Poses always remain scan-local.

### 2.3 The explicit pilot-final barrier

The last E022 region callback is not the final E022 result.
`search_survey()` calls `decode_known_tiles()` only after the region loop and
then returns. E023b must therefore publish a distinct `pilot_final` frame
after the return:

1. retain the complete scan-local `SearchResult`;
2. combine committed and current pilot observations by absolute address;
3. run the same final known-position BCH evaluation used by E022;
4. fail closed if the qualified zero-contradiction invariant is violated;
5. render panes A/B/C exactly as the final E022 session would render them.

Panes B and C stay on that final, scan-refined state while pane D advances
through payload processing. This is the final-pilot-sheet view that current
E023 lacks.

### 2.4 Why LDPC waits for all scraps in the TIFF

Payload calibration itself is local: the qualified detector calibrates per
window, so no whole-scan radiometric "uniform field" is required. The scan
barrier is nevertheless important for three concrete reasons:

- different scraps in one TIFF can provide complementary cells to the same
  LDPC tile;
- the one-owner rule cannot be finalized until every covering window in the
  scan is known;
- region-wise decoding would create avoidable attempts, spend extra CRC
  false-accept budget, and make outcomes depend on region order.

E023b.0 therefore finishes E022 for all scraps, publishes `pilot_final`, and
then collects payload evidence region by region. A later performance-only
pipeline may sample completed regions during E022, because their accepted
poses do not change, but it must preserve the same scan-final ownership and
LDPC barrier byte-for-byte.

## 3. The payload/LDPC job in detail

The payload stage is split into pure planning, immutable observation, a
scan-local reduction, and decode scheduling. Current E023's monolithic
`emit_scan()` should not be copied as the orchestration interface.

### 3.1 Build a geometric work plan

Consume every gated E022 `PlacedWindow`, including `redundant=True` records.
`PlacedWindow.page_cells_yx` is the authoritative audited core; E023b invents
no new erosion policy.

For every core page cell:

1. map it through `compose.payload_index_map()`;
2. discard pilot cells and off-page cells;
3. map the remaining payload index to `(page, tile_y, tile_x)`;
4. record geometric coverage and the contributing region/window.

This produces a `TileWorkPlan`, an upper bound before detector calibration.
Tiles are classified as payload-bearing candidates, zero-capacity
`degenerate` tiles, or geometrically untouched. Already-certified tiles are
not scheduled for ordinary BP again, but their new observations are retained
for divergence and future feedback.

"Potential tile" controls decode work; it must not prune the cells used to
estimate a window's median/spread or its pilot calibration. Such pruning would
silently change the qualified detector.

### 3.2 Produce immutable per-window evidence

Group placements by E021 region and make one extent-bounded prefilter for each
region. For every placed window in that region, preserve E023's qualified
path:

1. invert the stored rotation/origin to recover local authoritative-core
   cells;
2. sample each core cell through the stored affine pose from the original
   TIFF, using the aperture-0.7-cell uniform prefilter and order-1 read;
3. compute the ink-positive score
   `(median(cell_means) - cell_mean) / mean_absolute_deviation`;
4. regenerate the window's pilot labels from the format seed;
5. use the deterministic search-parity labels for PAVA and the disjoint
   validation parity for held-out log-loss;
6. calibrate-or-refuse when either class or the held-out set is too small;
7. apply the bounded PAVA LLRs to every core cell;
8. retain payload cells and descramble them into payload-bit LLR sign.

Each `WindowEvidence` stores a stable placement id, page/payload indexes,
raw cell means, derived scores, calibration nodes, emitted LLRs, label counts,
held-out score, refusal reason, and source-region/pose lineage. Non-owner
evidence is retained; current E023 discards too much of it for E024.

Pane D may show the region currently being sampled, provisional emitted
coverage, and calibration refusals. None of these temporary states mutates a
durable `TileRecord`.

### 3.3 Freeze one physical vote per scan

Only after all window evidence exists, choose exactly one owner for every
`(page, payload_index)` in the TIFF:

- lowest held-out log-loss wins;
- a stable full-placement id is the deterministic tie-break;
- a refused window emits no vote;
- overlapping windows from the same physical TIFF never become independent
  votes.

The result is an immutable `ScanEmission`, partitionable by LDPC tile. The
owner identifier must remain resolvable to its `WindowEvidence`, not merely a
fragile list ordinal.

This freeze is the first point at which pane D may label a tile
`below_attempt_floor` or `attempt-ready`: before ownership, informative
coverage is only provisional.

### 3.4 Stage 1: independent current-scan decoding

For each touched, still-uncertified tile in deterministic page/tile order:

1. gather its 4096 logical LLR slots; missing values remain exact erasures;
2. apply `ldpc.tile_shorten_mask()`;
3. classify zero user capacity as `degenerate`;
4. compute `k_eff = k_bits - n_shortened` and
   `n_informative = count(nonzero LLR on non-shortened slots)`;
5. if `n_informative < k_eff`, record `below_attempt_floor` without invoking
   BP and without spending CRC exposure;
6. otherwise run the qualified LDPC decoder;
7. accept only its syndrome-plus-CRC verdict;
8. retain certified user bits, rate, iterations, and exact evidence
   provenance.

The durable tile states remain E023's honest set:

```text
unobserved | below_attempt_floor | attempted_failed | certified | degenerate
```

Certification is terminal for the production scheduler. Later independent
evidence is compared cheaply against the deterministic re-encoding and
recorded as divergence; E023b does not claim to detect a second conflicting
certificate while also skipping all certified tiles. A separate
qualification/corroboration mode may deliberately re-decode certified tiles,
but that is not routine session work.

### 3.5 Stage 2: changed cross-scan union only

For still-uncertified tiles affected by the new scan, sum at most one owned
LLR per independent physical scan and payload cell. Never sum two derived
versions of the same capture as if they were independent.

An attempt is identified by:

```text
(page/tile, stage, decoder profile, evidence digest)
```

The union evidence digest is derived from the session-ordered constituent
per-scan tile-evidence digests. Therefore:

- one-scan union identical to Stage 1 is skipped;
- an unchanged resume cannot repeat a failed attempt;
- a failed tile is retried only after genuinely new evidence arrives;
- changing decoder policy deliberately creates a new attempt identity.

Stage 2 runs after every completed scan, even when several TIFFs were supplied
in one command. This makes CLI batching irrelevant. It intentionally explores
scan-prefix unions that old E023, which ingests all new scans and unions only
once at the end, may not explore. Qualification must treat any additional
certificate as a preregistered scheduling difference, require zero wrong
certifications, and preserve all qualified E023 certificates and bits.
Acquisition order remains part of the append-only session history; arbitrary
permutation invariance is not claimed.

### 3.6 Post-certification divergence and commit

Re-encode each newly certified tile and compare only newly available scan
evidence with its transmitted payload bits. Append the divergence result;
do not recompute or overwrite all history.

Then atomically commit the entire TIFF transaction: survey, pilot result,
window evidence, frozen scan emission, attempt records, certificates, and
diagnostic/report summary. If processing fails before commit, the prior
session remains valid and the TIFF is recomputed on the next invocation. In a
multi-TIFF command, each successfully completed TIFF commits independently.

## 4. Four-pane diagnostics

E023b's diagnostic is a read-only observer. Its failure disables diagnostics
and never aborts or changes acquisition/decoding. `--diag` on and off must
produce byte-identical authoritative state.

The four panes are:

- **A — scan space:** the current TIFF, E021 regions, active region, and E022
  outcome per completed region;
- **B — page placement:** accepted/redundant window support in canonical page
  coordinates, with prior-scan and current-scan provenance distinguished;
- **C — pilot state:** addressed pilot sites/tiles and the true final
  known-position BCH state;
- **D — payload/LDPC:** committed tile state plus a separate transient work
  overlay for the current scan.

Pane D's transient overlay may use:

```text
candidate outline -> sampling -> emitted coverage -> attempt-ready -> decoding
```

The committed fill remains the five-state E023 map. Provisional coverage must
not be painted as a provisional CRC success/failure. Useful deterministic
milestones are:

```text
scan_open
e021_complete
e022_region_complete × N
pilot_final
payload_plan
payload_region_emitted × N
scan_owner_frozen
ldpc_batch × M
union_complete
scan_committed
```

The implementation renders the first attempt in a stage, every 40th attempt,
and the final `union_complete` state rather than 700–900 frames. It currently
recomposes A/B/C for those diagnostic frames; caching the frozen
post-`pilot_final` panes is a safe observer-only performance optimization, not
part of receiver state or qualification.

Status metadata includes scan and region progress, current phase, page,
placement/pilot counts, complete-grid LDPC state counts, new attempts, and
CRC exposure. It contains no fountain or volume-completion fields.

For multiple legal pages, B/C/D must be page-filtered. The live viewer should
offer page tabs; deterministic artifacts may write one page image per
milestone or a contact sheet. Pane A remains the common physical scan. No
renderer may silently hardcode page 0 or overlay placements from different
pages.

Frames continue monotonically across invocations, but frame numbering and
observer metadata are not part of the authoritative receiver state.

## 5. Persistent state and the E024 substrate

The state is a versioned receiver session, not an E022 pickle plus a thin
E023 pickle joined by list position.

### 5.1 Fixed envelope

Retain exact format/seed/spec geometry, legal pages, DPI/footing, LDPC rate,
algorithm/config hashes, sampler aperture, PAVA split/version, decoder
profile, and independent-evidence policy. A page rate should be represented
by page even if all current pages use the same registry rate.

### 5.2 Per-source-scan record

Retain:

- stable scan id, resolved/remappable path, SHA-256, size, image shape, bit
  depth, DPI, and capture/evidence-group identity;
- the exact E021 survey with losslessly packed region masks;
- the complete E022 `SearchResult`: accepted and redundant placements, poses,
  audited cores, pilot observations, final BCH state, region states,
  `window_audit`, and best losing hypotheses/retry ledger;
- immutable generation-0 `WindowEvidence` for every placed window;
- the frozen `ScanEmission` and its owner-to-window map;
- phase timings and parent/config digests.

Keeping baseline raw cell means makes same-pose detector recalibration
replayable without resampling. The source TIFF and exact pose remain necessary
for a future pose change.

### 5.3 Tile and attempt ledgers

Each `TileRecord` retains its current honest state, certified user bits and
rate, best coverage, divergence observations, certificate provenance, and an
append-only list of attempts.

Each `TileAttempt` retains stage, evidence identity, contributing
scan/window/owner ids, `k_eff`, informative count, decoder profile,
syndrome/CRC verdict, iterations, and result. Below-floor evaluations are
ledgered as scheduling decisions but are not decode attempts or CRC exposure.

### 5.4 Future feedback revisions

E023b performs no feedback and stores one immutable baseline generation. Its
rich scan/window/attempt records are the migration substrate for E024;
E023b.1's v2 schema does **not** pretend to contain E024's revision graph
already. That
schema migration must add explicit generation ids, parents, active revisions,
certificate dependencies, and stable feedback-derived window ids while
preserving generation 0 byte-for-byte.

E024 must also enforce these rules:

- feedback-derived evidence records the certificate ids used as labels;
- multiple derivations of one physical sample share a capture id and
  supersede rather than sum;
- dependency records support leave-target-out processing so a tile cannot
  certify itself through labels descended from its own certificate.

Certified user bits plus LDPC rate remain the logical source of truth; the
codeword and physical payload labels are regenerated deterministically and
are never written back as fabricated raw LLRs.

## 6. Shared-code boundary

E023b should depend on library primitives, not reach through experiment
runners or private rendering helpers as current E023 does.

The clean refactor is:

- keep `platen.detect_payload_regions()` and
  `pilotsearch.search_survey()` as the E021/E022 algorithms;
- extract E022's immutable multi-scan pilot combination into a shared pure
  helper used by both `session_e022.py` and E023b;
- split payload decoding into `plan`, `emit_window/region`,
  `freeze_scan_emission`, and pure `attempt_tile` boundaries;
- extract reusable A/B/C rendering from `run_e022.py` and compose pane D in
  E023b without importing a CLI script or private `_panel_*` functions;
- keep the diagnostic server a byte-and-metadata sink that owns no receiver
  state.

This makes E023b the only orchestrator while E021, E022, and payload/LDPC
remain testable independently.

## 7. Qualification gates

E023b is not promoted until all of the following pass:

1. On the frozen E018 footings, E021 and E022 v2.2 region states, placements,
   pilot observations, and combined BCH results match their qualified runs.
2. Generation-0 `WindowEvidence` and frozen per-scan owner emissions match the
   qualified E023 algorithm exactly.
3. Every qualified E023 certificate and its user bits is reproduced, with
   zero wrong certifications. Any extra prefix-union certificate is reported
   separately and must also be ground-truth correct.
4. `A B C` in one command equals three ordered invocations in authoritative
   state, tile outcomes, attempts, and bits.
5. Refeeding an existing SHA is byte-identical and spends zero attempts.
6. A failed union is not retried until its evidence digest changes.
7. `--diag` on/off is state-identical; diagnostic failure is harmless; frames
   contain no future-scan state.
8. The explicit `pilot_final` frame matches E022's final pilot view and remains
   visible while D advances.
9. Multiple legal pages remain separate in state, attempts, and every pane.
10. Native and decimated/derived footings cannot accidentally enter the same
    independent-evidence sum.
11. Crash injection before a TIFF commit preserves the prior session; retry
    produces the same result as an uninterrupted transaction.
12. Reloading persisted state is sufficient to reproduce one baseline window
    calibration, one tile attempt, and the provenance of every certificate
    without hidden process memory.

Only after these architectural gates pass may E023b compare adaptive BP,
context-conditioned calibration, erasure elimination, or another detector/
decoder algorithm. Those are separate preregistered arms, not silent changes
inside the integration rewrite.

### 7.1 Qualification record

`qualify_e023b.py` pins the frozen E022, E023, and ground-truth hashes. Its
replay-only mode now reports `REPLAY PASS (RAW INTEGRATION SKIPPED)` and cannot
satisfy the full raw gate. The full 2026-07-15 run passed every replay and raw
gate:

| footing | frozen E023 cert / calls | E023b cert / calls | final non-cert states | extra prefix-union certificates |
|---|---:|---:|---|---|
| decimated 1600 dpi | 741 / 1,024 | **742 / 1,076** | 51 failed, 12 below floor, 35 degenerate | `(0,16,18)` |
| native 4800 dpi | 740 / 1,037 | **742 / 1,098** | 53 failed, 10 below floor, 35 degenerate | `(0,8,1)`, `(0,8,2)` |

All historical certificates retain byte-identical user bits. All three extra
certificates are ground-truth correct; there are zero wrong certificates in
either footing. The CRC false-accept exposure bounds are `2.5053e-7` and
`2.5565e-7`. Prefix totals match the preregistration exactly:

```text
decimated: 179/236, 202/338, 333/499, 337/536, 730/1000, 742/1076
native:    178/238, 198/348, 321/513, 332/561, 721/1030, 742/1098
```

The raw gate rehashed all 12 TIFFs and established exact source identities,
E021 summaries, timing-free E022 results, reduced emissions, stored-evidence
re-freezes, decode scans, tile outcomes, and attempt/provenance ledgers. The
authoritative semantic digests are:

```text
decimated f98e70abed821f612a2636d1c0a5347365bff8457996a06ba756e8f55323414b
native    859827533f8d6f1bcd9257e9db7baafc779ba0f125b344ddb2999edf83016849
```

The real decimated six-TIFF run took 627 s wall time; native took 861 s. The
retained raw-evidence states are intentionally large (620 MiB and 1.2 GiB), a
cost paid for E024 replayability rather than hidden process state. Refeeding a
committed decimated TIFF preserved the 650,054,933-byte state's SHA-256 and
mtime exactly and spent zero attempts. Focused E021--E023b tests passed 60/60;
the complete repository suite passed 419/419 in 824.76 s.

This correctness-first version revalidates every committed scan derivation on
load, apply, and save, so validation work across many sequential appends is
quadratic in scan count. That is measured and acceptable for the qualified
six-scan field, but should be replaced before very large sessions by pinned
per-record canonical hashes (plus an authenticated aggregate and periodic full
audit). Likewise, `--diag` currently recomposes panes A--C for each frame;
observer-only pane caching is a future performance optimization. Neither
optimization requires changing the numerical pipeline or persisted meaning.

One E018b C2 full-sheet run exposed a separate E022 implementation cost:
`_score_known()` used to construct the frozen parity split over the complete
3300x2220-cell page for every local origin probe. A local anchor attempt tests
up to 49 neighboring origins plus validation, and a large region can try a
growing list of prior anchors, making this page-sized allocation pathological.
The 2026-07-16 correction constructs exactly the same
`(131*y + 17*x) & 1` split only over the page/fragment overlap. It changes no
gate, candidate, anchor ordering, or persisted meaning. The focused real
HP-C2 rejected-anchor probe fell from 0.837 s to 0.095 s (8.8x).

The complete rerun also incorporated E021.6's independently qualified
coarse-authoritative boundary/gap mask. The old E021 mask had two regions,
including one nested artifact, and 449 fragmented placements; E021.6 emits
one region and 294 placements. Held-out context validity rises 0.908→0.979.
Measured stage times are E021 4.27 s and E022 44.42 s, versus 11.59 s and
400.12 s in the first take. First-pass certificates rise 741→1392; the
scorer sees 1356/1734 fountain symbols, rank 737/737, and verifies the
192,160-byte payload SHA without BP retry. The parity correction is a
numerical-semantic no-op and accounts for E022 runtime; the support and
certificate change is E021 geometry. Detector provenance:
`experiments/021-payload-regions.md` §11.

The ignored `build/qualify_report.json` is the machine-readable record. Run:

```text
env/bin/python experiments/023b-integrated-receiver/qualify_e023b.py
```

### 7.2 E023b.1 BP and context + PAVA arms

The frozen design, constants, honesty boundary, factorial measurement, and
promotion decision are in `ALGORITHM-ARMS.md`. In brief, E023b.1 adds:

- an explicit, idempotent max-150 BP retry over only the current failed
  evidence frontier;
- a one-shot nine-bin ordered-logit context correction, trained only on
  SEARCH pilots and admitted only by disjoint VALIDATION-pilot log loss;
- state-v2 detector/profile and context-fit provenance plus exact raw-mean
  replay validation.

The certificate yields were 742 / 747 / 749 / 757 for baseline / BP /
context / combined on decimated, and 742 / 747 / 746 / 752 on native. Context
reduced emitted-cell BER from 1.9179% to 1.3509% and from 2.6440% to 1.8757%,
while improving weighted held-out log loss on both footings. All certificates
were ground-truth correct and no common baseline value changed. BP is promoted
as an explicit action; context remains opt-in pending a genuinely independent
capture because these two footings derive from the same physical scans and
the decimated context arm loses one baseline certificate while gaining eight.

The numerical record is `build/qualify_arms_report.json`; reproduce it with:

```text
env/bin/python experiments/023b-integrated-receiver/qualify_e023b_arms.py
```

The final provenance-complete replay took 1,100.61 s and produced a
757,236-byte report with SHA-256
`9f5763d72577d44dfa3df4d3b82fe8396b9133afedcec5a7e6af4269f2649071`.
The report embeds matching hashes for its qualification harness, production
entry point, detector, receiver, and frozen design, and audits raw versus
effective support in every context bin.

This qualification does not introduce fountain/rank/completion logic or a
stop condition.

The external promotion gates were run separately from the deliberately
numerical-only report: the focused E023--E023b contracts passed 41/41, the
historical E023b replay gate passed both footings, and the complete repository
suite passed 431/431 in 849.73 s. These include live diagnostic isolation,
duplicate-input identity, profile save/reload/raw replay, exact failed-context
fallback, retry idempotence, one exposure per evidence identity, and
adversarial missing/reordered-frontier rejection.

### 7.3 BP scheduling and correlated raster views

A supplemental qualification compared one final max-150 retry with max-150
after every scan prefix.  Only decimated PAVA gained a final tile
(`(0,28,11)`, 748 rather than 747).  Both context arms had identical
certificate sets under the two schedules, and their native/decimated union
remained exactly 769.  Prefix retry spent 140--157 more CRC-bearing calls and
roughly 44,000--50,000 more BP iterations per branch.  Final-only retry
therefore remains the recommended schedule for the best measured arm.

Native and decimated TIFFs are correlated views of six physical captures,
not twelve independent scans.  Running two ordinary context+BP branches and
unioning only their conflict-checked certificates gives 769 tiles: 740
shared, 17 decimated-only, and 12 native-only.  All are ground-truth correct.
Legal one-vote-per-capture cell fusions reached at most 763 and added no
certificate beyond the branch union.

[`merge_e023b.py`](merge_e023b.py) implements the terminal
certificate-boundary union without weakening the receiver's duplicate-capture
or single-DPI invariants.  It validates current states, capture alignment,
tile capacity, certificate bits, and exact certifying-attempt provenance;
conflicting certificates are fatal.  See [`HOWTO.md`](HOWTO.md) and
[`MULTIVIEW-RECOVERY.md`](MULTIVIEW-RECOVERY.md) for commands, measurements,
and the scale-space follow-up.

The correlated-view numerical record is
[`MULTIVIEW-QUALIFICATION.json`](MULTIVIEW-QUALIFICATION.json), SHA-256
`5360094049676f36f5e73d8eddbe0522b2891b083f91a0cfa4538274781c54fc`;
reproduce it with:

```text
env/bin/python \
  experiments/023b-integrated-receiver/qualify_e023b_multiview.py
```

The BP scheduling record is
[`bp_schedule_report.json`](bp_schedule_report.json), SHA-256
`dd3d89b3d583f1c3191b8983f3f24e603998791e96e445e5ce352f01d31479af`;
reproduce it with:

```text
env/bin/python \
  experiments/023b-integrated-receiver/qualify_e023b_bp_schedule.py
```

Neither qualification changes E021, E022, the production E023b numerical
path, or the fountain/rank/stop boundary.

## 8. Decisions and non-goals

Decided for E023b.0:

- E023 is preserved as the qualified reference; E023b is a new entry point.
- One whole-scan E021 call and one whole-scan E022 call per TIFF.
- Per-scrap diagnostics, but a scan-final ownership and LDPC barrier.
- The exact qualified E023 detector/decoder path before any algorithm arm.
- Stage 1 plus changed Stage 2 after every scan transaction.
- Certified tiles are terminal for routine BP; divergence remains live.
- Rich immutable generation-0 evidence is retained for E024.
- Proper four-pane, causal, multi-page diagnostics.

Decided for E023b.1:

- Preserve `pava-v1` as the exact default and freeze a detector profile per
  state.
- Offer `ctx-pava-v1` as the measured, pilot-only context arm rather than
  silently changing the baseline detector.
- Keep extended BP as an explicit state action with its own attempt identity,
  provenance, CRC exposure, diagnostics, and idempotence contract.
- Retain raw means and fit sidecars needed to replay this generation and to
  build E024's future leave-target-out feedback graph.

Explicitly out of scope:

- fountain/RaptorQ symbols, rank, archive assembly, completion, or stopping;
- E024's certified-feedback re-placement/recalibration loop itself;
- joint placement of independently ambiguous scraps;
- treating derived images of one capture as independent evidence;
- algorithm changes justified only by the orchestration rewrite.
