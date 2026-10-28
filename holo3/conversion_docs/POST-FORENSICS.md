# POST-FORENSICS — adjudication of the post-batch parity runs

Read-only forensics over `run-{2,3,4,5,6,7}` (baseline) and
`post-{2,3,4,5,6,7}` (post) in this directory. No decodes were run, no
files outside this note were written, git was used read-only. Every
number below is either streamed from the run dirs' own
`events.jsonl` / `report.json` / `post-ledger.jsonl`, or read from
`<checkout>/holo3` at the tree that produced the post
runs. Claims that are inference rather than measurement are tagged
INFERRED in place; claims the artifacts cannot settle are tagged UNKNOWN.

Five volumes completed and closed VERIFIED byte-exact against their
expected payload sha. Step 4 (`xerox c2-cmy8`) was killed at the RSS
ceiling twice and measures nothing.

---

## 0. The correction that reframes the whole batch

**PARITY.md's headline finding is false, and it is a defect in the
analyzer, not in the receiver.**

PARITY.md:448 reads:

> **The refinement rows adopted nothing, on any volume.** Across the five
> completed volumes `refine` fired 717 times, `refine.color` 3899 times
> and `revisit` 593 times, producing 0 `route=refine` poses -- zero,
> everywhere.

The counter behind it is `analyze_post.py:213`:

```python
adoptions = post["pose_routes"].get("refine", 0)
```

`pose_routes` is built by counting `PoseCommitted` events by route. That
event is constructed at exactly one site in the production tree —
`holo3/plugins/place.py:776` — inside the place accept path. The
refinement adoption path never reaches it. An adopted revision is folded
by `engine.py:645-655`:

```python
def _fold_refine_outcome(self, fact) -> tuple[bool, tuple[FactKey, ...], str]:
    if not fact.revision.adopted:
        return True, (), "other"
    placement = self._placements[fact.window_id]
    revised = refine.revised_placement(placement, fact.revision)
    _changed, keys, _kind = self._fold_placement(revised)
    self._births(revised)
    return True, keys, "pose"
```

which folds a `Placement` and returns kind `"pose"` **without appending
any event**. Both refinement plugins return an empty events tuple
(`refine.py:602`, `color_refine.py:359`). So `route="refine"` cannot
appear in `events.jsonl` on any volume at any adoption rate — the
counter is structurally pinned at zero.

The real channel is `JobDone.n_poses`. `engine.py:341-372` `_merge`
increments `n_poses` once per folded fact whose kind is `"pose"`, and
`_fold_refine_outcome` returns `"pose"` if and only if
`revision.adopted`. A refinement job returns exactly one `RefineOutcome`
fact, so `n_poses ∈ {0,1}` **is** the adoption bit.

Verified two independent ways — `report.json` `plugin_rows[].poses`, and
summing `JobDone.n_poses` over the refinement rows in `events.jsonl`.
Both agree exactly, and `grep -c '"route": "refine"'` is 0 in all five:

| run | row | fires | adopted | rate |
|---|---|---:|---:|---:|
| run-2 | refine | 106 | **28** | 26.4% |
| post-2 | refine | 406 | **97** | 23.9% |
| post-3 | refine.color | 161 | **121** | 75.2% |
| run-5 | refine | 144 | **63** | 43.8% |
| post-5 | refine | 311 | **95** | 30.5% |
| post-6 | refine.color | 788 | **527** | 66.9% |
| post-7 | refine.color | 2950 | **1631** | 55.3% |

**The batch's "0 for 5209" decomposes into two entirely different
findings:**

- refinement (`refine` + `refine.color`): **2,471 adoptions on 4,616
  fires = 53.5%** — misreported, never zero;
- `revisit`: **0 adoptions on 593 fires** — genuinely zero, and honest
  (§A.3).

Three downstream statements inherit the defect and must be retracted with
it: the "runaway signature" call on steps 6 and 7, the
`colour_lane_churn.pathological: true` flags (computed at
`analyze_post.py:230` as `colour_fires >= 200 and adoptions == 0`), and
PARITY.md:450's "with zero refinement adoptions the events in hand do not
isolate what re-fired those extra scans."

Re-scoring is a text edit against `n_poses`; it needs no decodes.

---

## A. THE ZERO-ADOPTION VERDICT

**Verdict: HONEST REFUSAL — but the question as posed rests on a false
premise for every volume where a refinement row fired at all. There was
no zero to adjudicate.** The one real defect is in the measurement
(§0). The gates themselves behave as designed.

### A.1 Why the refusals are honest, not a stuck gate

Four independent lines, none of which depends on the broken counter.

**(a) The adoption rates are high and volume-appropriate.** 24%–75%. A
stuck gate, an always-empty reach, or empty labels would produce zero or
near-zero everywhere. `refine.color` on step 3 adopted three fits in
four.

**(b) An empty reach cannot reach a fit at all.** The crop-free
pre-gates live in `prepare_refine` / `prepare_color_refine` and return
`None`; `engine.py:335-336` then does a bare `continue`, so **no job is
submitted and no `JobDone` is written**. Every counted fire therefore
already passed "has placement, has evidence, has certified cargo in
reach, is not certified-complete, is not a duplicate attempt." The
console's frontier-job figure equals the `JobDone` count exactly on
step 2 (12,681 / 15,991), confirming fires are jobs-only.

**(c) The non-adoptions paid full search cost.** A support-gate bail
returns before the candidate grid; an adoption can only be reached after
it. Across all five volumes the adopted and non-adopted cpu
distributions are indistinguishable, and the non-adopted median is
consistently *higher*:

| volume | adopted median (s) | not-adopted median (s) | non-adoptions below cheapest adoption |
|---|---:|---:|---:|
| post-2 (refine) | 0.1904 | 0.1956 | no cheap population (13/309 below adopted p5 vs 5.2% expected) |
| post-3 (refine.color) | 0.1934 | 0.2031 | 0 of 40 |
| post-5 (refine, 200×200 class) | 0.1921 | 0.1960 | 0 of 204 |
| post-6 (refine.color) | 0.2090 | 0.2192 | 1 of 1319 below 0.05 s |
| post-7 (refine.color) | 0.1878 | 0.1963 | 1 of 1319 below 0.05 s |

A post-5 `calibrate` job, which uses the same crop machinery, costs
0.0218 s — an order of magnitude below the observed 0.19 s refinement
jobs. INFERRED (cost shape, not a reason string): essentially every
non-adoption ran the complete coarse+fine grid and was refused at a
terminal gate, not at a label/support pre-gate.

**(d) Two of the three terminal outcomes are not failures at all.**
Reading `refine.py:483-505`, after the grid the only three non-adopting
returns are:

```python
if pose == base_pose:
    return Revision(False, "active_pose_selected", ...)
...
if not adoption_gate(base_loss, loss, base_pilot_mismatch, pilot_mismatch,
                     base_raw_mismatch, raw_mismatch):
    return Revision(False, "pose_gate_failed", None, *best, base_loss, loss, ...)
affine = native_terms(pose, cells, source_per_output)
if affine == tuple(float(term) for term in placement.native_affine):
    return Revision(False, "unchanged_affine", None, *best, base_loss, loss, ...)
```

`active_pose_selected` means the search re-selected the pose already in
force. `unchanged_affine` means the winning affine equals the standing
one. Neither is a rejection — both are *"the pose is already right."*
Only `pose_gate_failed` is a real quality refusal. On a sheet that is
90–99% certified before the refinement wave starts, a large
"non-adoption" fraction is the expected and correct behaviour of a lane
that has little left to improve. **How the 45% splits across those three
is UNKNOWN** and is the one instrumentation gap worth closing (§E.2).

### A.2 The genuine instrumentation gaps

Two, both narrow and both cheap:

1. **`Revision.reason` is computed and thrown away.** The dataclass
   (`refine.py:102-111`) carries `reason`, `baseline_logloss`,
   `candidate_logloss` and `candidates`. Eleven exact strings exist in
   the two plugins (`refine.py:212,219,225,426,485,499,503`;
   `color_refine.py:122,129,135,205,219,276,290,297`). The job returns
   an empty events tuple and `_fold_refine_outcome` drops the whole
   fact for non-adopted revisions. No `Event` dataclass in `data.py`
   carries it. The refusal histogram is therefore **unbuildable from
   any run dir in this batch** — not missed, structurally absent.

2. **Prepare-stage refusals leave no trace whatsoever.** `engine.py:334-339`
   does `if job is None: continue` — before `worker.attempts += 1`, so
   not even the attempt counter moves. On step 3 at least 437 of 589
   placed windows (74%) never got a fit and nothing records why; on
   step 7 the floor is 780 of 3,156. Both are per-window floors, not
   per-wake counts; the true count is unrecoverable by construction.

### A.3 `revisit` — the one genuinely zero row, and it is honest

593 fires, 0 adoptions, 0 certificates, ~31 cpu s total across the batch.
This is correct behaviour, not a dead lane:

- On colour volumes it is inert by construction: `revisit.py:137-144`
  retires the worker as soon as a placement exists for a non-K family,
  so only the never-placed arm can run.
- Exact per-job event attribution (a job's events are appended
  immediately before its own `JobDone`) shows **every** revisit fire on
  steps 3, 5 and 6 emitted exactly one `WindowSettled` with
  `state='consult_refused'` and nothing else — 37/37, 33/33, 82/82.
- On step 2, two exact identities prove all 124 went down the ring-pass
  placement branch and none down calibrate: post `WindowSettled` 1051 −
  place-jobs-with-no-pose 927 = 124; and post `CalibrateAdopted` 6781 =
  calibrate 6714 + ctx 67, residual 0.

It is cheap, honest, ineffective mop-up on residues that were already
exhausted. It costs nothing and yields nothing.

### A.4 Reconciling "53 of 58 colour misses = missing refinement lane"

`holo3/SCHEDULE.md:116` records the prior attribution:

> The colour refinement lane v1 ran on every colour close is now the
> `refine.color` row (v1's `color_refine` numerics carried verbatim; the
> gap forensics attributed 53 of 58 colour-volume misses to its absence).

**Reconciled, with a partial verdict and one confound that prevents
closing it.**

The lane now exists and adopts heavily. Its arrival is associated with a
large net recovery of colour misses against holo1:

| volume | holo1 misses, baseline | holo1 misses, post | refine.color adoptions |
|---|---:|---:|---:|
| step 3 c3-cmy7 | 4 | **0** (exact parity) | 121 |
| step 6 c2-cmy7 | 22 | **26** (worse) | 527 |
| step 7 sheet I | 104 | **34** | 1631 |
| **total** | **130** | **60** | **2279** |

So the direction of the prior attribution is supported — colour misses
against the reference reader more than halved on the volumes where the
lane fired. But it is **not** vindicated as a sufficient explanation,
for three reasons:

1. **Step 6 went backwards** (22 → 26) *while* adopting 527 poses. If
   the missing lane were the binding constraint, this volume should have
   improved.
2. **On two of three colour volumes the majority of gains provably
   predate any adoption.** Step 3: at the first `refine.color` adoption
   (event idx 9,563) the post run already held 789 certificates — more
   than the baseline's *final* 786 — so at most 22 of 29 gains can be
   lane-attributable and **at least 7 provably are not**. Step 6: 12 of
   17 gains certified before the lane's first fire at event line
   71,324, four of them on their first attempt in the first 1% of the
   run.
3. **The confound: this batch changed more than one variable.** The same
   tree also un-gated retries at close-readiness, split the single
   `tiles` row into `scan`/`retry`/`freeze`, and put `lane_generation`
   on colour rows. Nothing in the events separates those from the lane.

The prior "53 of 58" figure also comes from a different gap-forensics
corpus than these baselines (whose colour misses total 130), so the two
are not numerically commensurable — only the direction is.

**Status: PARTIALLY SUPPORTED, NOT CLOSED.** The lane is real, adopts,
and on step 7 carries the batch's cleanest causal signature (§C).
It is not the whole explanation, and step 6 is an outright
counterexample. Left OPEN, and §E.3 gives the measurement that would
close it.

---

## B. THE LOSSES

54 lost tiles across three volumes. **Not one of them is a scheduling
defect.** In every single case the post run attempted the tile *more*
times than the baseline needed, at both stages, right to the end of the
run. The searched-for pattern — a tile the baseline won that post never
attempted with equivalent inputs — **does not occur anywhere in this
batch.**

### B.1 e029 HP K (step 2) — 2 losses, both ty=42

Independently re-derived from `TileOutcome` rows in both trees:

| tile | baseline | post |
|---|---|---|
| (42,12) | 25 attempts, **certified** at event 28260, bp_iters **17** | **57 attempts** (29 scan + 28 retry), 0 certified, last attempt at event 55141 of 55147 |
| (42,15) | 7 attempts, **certified** at event 21781, bp_iters **22** | **57 attempts** (29 scan + 28 retry), 0 certified, last attempt at event 55137 of 55147 |

Every post attempt saturated its budget (120 on scan, 300 on retry).
Both tiles were still being attempted in the final dozen events.

`ty=42` is the worst row on the sheet in **both** runs — rank 1 of 53 by
`attempted_failed` (476 baseline, 953 post). That is the documented HP
M281 weak-horizontal-line banding recorded for e029 in CLAUDE.md.

**Class: channel marginality, plus an evidence/calibration difference.**
Post did strictly more work on both tiles and never got evidence the
LDPC could close on, while the baseline closed them in 17 and 22
iterations. Note (42,15) diverges *early* — the baseline won it on its
5th scan attempt at event 21,781, and post's first refinement adoption
anywhere is at event 49,114 — so refinement cannot be the cause on that
one.

### B.2 xerox c2-cmy7 (step 6) — 39 losses

The largest loss population, and the only volume that regressed against
holo1 (22 → 26).

- Every one of the 39 was attempted **144–146 times** in post (72–73
  scan + 72–73 retry, one pair per freeze epoch), always
  `attempted_failed`, **never once `below_attempt_floor`** — so
  informative-cell support was always adequate; these are convergence
  failures, not support failures. 5,620 attempts for zero certificates.
- 27 of the 39 saturated the BP iteration cap on **every single
  attempt** — the evidence was never close.
- Their first post attempts land at event lines 3,194–7,429, long
  before the refinement lane's first fire at line 71,324. **Refinement
  is ruled out as the cause.**

**Population shape — this is the key evidence.** Of the 158 tiles the
baseline certified at attempt ≥ 5, post lost 27 (**17.1%**). Of the 882
it certified on the first look, post lost 3 (**0.34%**). The loss is
concentrated almost entirely in the marginal population, and the gains
come out of the same pool — lost and gained tiles share columns
tx = 1, 17, 27, 28, 30, 34, with tx=30 alone contributing 7 lost and 9
gained.

**Class: a marginal population being re-shuffled, not a degradation.**

**The three exceptions are the real lead.** (0,19,17), (0,23,2) and
(0,37,3) were certified by the baseline on their **first look**
(bp_iters 776 / 671 / 453, event lines 4902 / 5236 / 6417). Post failed
the same first look at essentially the same run position (lines 5165 /
5497 / 6674) and 143 more after it. Those are not marginal tiles.
Something hands those three addresses materially worse cell values from
the first freeze epoch onward. If one root cause is chased, chase these.

### B.3 sheet I pooled CMY8 (step 7) — 13 losses

- All 13 attempted **778–801 times**, roughly half of those *before* the
  first adoption at idx 515,243. None ever hit `below_attempt_floor`.
- **11 of 13 are the Y stream** — the weak plane on this sheet.
- 3 of 13 are tiles holo1 also reads, so they are a genuine regression
  against the reference reader. The other 10 are holo3's beyond-holo1
  fringe, which *grew* 133 → 176 across the change.
- The same fringe flipped both ways: the columns that lost (tx 9, 10,
  16, 17, 19, 27, 28, 29) are the columns that gained most
  (tx 30:14, 19:12, 27:11, 11:10, 29:10, 31:9), and the volume gained
  100 Y tiles while losing 11.

**Class: channel marginality on the weak plane, under a different
evidence realisation.**

### B.4 The only scheduling defect in the batch is in the BASELINE

Step 5 is the mirror image and it is worth recording as such. Its three
*gains* are scheduling wins, because the **baseline's** retry lane died:

- The baseline's last `tiles/retry150` attempt is at ordered position
  11,653 of 19,899 (59% of the run). The baseline crossed
  `k_total = 1356` (close-count-ready) at position 11,609 — **44 ordered
  items earlier**. The retry lane went silent within 44 events of the
  volume becoming closeable and never fired again.
- Two of the three recovered tiles — (23,34) and (52,0) — had **zero
  `tiles/retry150` attempts ever** in the baseline. Those are literally
  "never tried."
- The winners converged at 78, 102 and 217 iterations, every one above
  the scan stage's 60-per-hypothesis budget, so an ordinary scan on the
  same LLRs could not have closed them. INFERRED from
  `BASELINE_BP_MAX_ITERS`/`RETRY_BP_MAX_ITERS` plus the reported
  `n_iters`.

So the post tree fixed a real baseline starvation bug. That is a
genuine, well-evidenced win and the clearest causal story in the batch.

### B.5 The assumption every mechanism claim above depends on — and it is untested

Every "the post tree never reproduced the baseline's favourable evidence
snapshot" claim silently assumes the receiver is **run-to-run
deterministic**, so that a difference in outcome implies a difference in
the tree. **That assumption is not established, and the engine is
timing-dependent by construction.**

`engine.py:196-203`:

```python
executor = ThreadPoolExecutor(max_workers=self._request.workers)
...
done, _pending = wait(set(self._inflight), return_when=FIRST_COMPLETED)
```

`wait(..., FIRST_COMPLETED)` returns a *set* whose membership depends on
wall-clock completion order. Facts are then merged one at a time, and
the folds are order-sensitive: freeze epochs bump, `_fold_tile_evidence`
(`engine.py:657-668`) accepts only rows with a strictly higher epoch,
and `arms_retry` fires off whatever `AttemptFact` happens to land. Two
runs of the *same* tree can therefore attempt the same tile against
different evidence epochs.

To be precise about what is and is not deterministic: the *selection*
rules are total orders and are sound — `_evidence_rank`
(`tiles.py:193-195`) breaks epoch ties on `observed_flat.tobytes()` and
`values.tobytes()`, and `component_signature` sorts. So a given store
state yields a deterministic choice. What is **not** deterministic is
which store state a given tile fires against.

The step-6 population statistics are exactly the signature of a
coin-flip on marginal tiles (17.1% loss among late certifiers vs 0.34%
among first-look certifiers), and byte-exact closure on all five
volumes is consistent with either reading.

**Status: UNKNOWN, and it is the cheapest thing in this batch to
settle (§E.1).** Until it is settled, no per-tile root-cause hunt on the
39 or the 13 is warranted — a re-run of the same tree might produce a
comparable churn on its own.

---

## C. THE GAINS

The question as posed ("gains with no adoptions") is void for three of
five volumes. Taking each on its own evidence:

### C.1 Step 2 — there are no gains to explain

Every post certificate corresponds to a baseline certificate. The
per-tile cross-tab: 1885 scan→scan, 31 scan→retry, 3 retry→scan, 19
retry→retry, 2 lost. The headline "+28 retry" is **re-attribution, not
yield** — retries now fire earlier and 4.7x more often, so the retry
path wins the race on tiles both paths can do. The ordinary scan row
*lost* 30 certificates (1918 → 1888).

### C.2 Step 5 — scheduling, and it is proven

All three gains minted by `tiles/retry150`, on a lane the baseline had
starved (§B.4). This is the batch's best-supported gain mechanism.
Supporting detail: 42 / 24 / 11 *earlier* retry attempts on those same
three tiles each exhausted 300 iterations and failed, so it is not
merely "more tries" — only the final evidence epoch converged, and each
winner sits immediately downstream of a `tiles.freeze` which itself sits
immediately downstream of a refinement adoption, three times out of
three. CIRCUMSTANTIAL: the events carry no fact lineage, so adjacency is
the strongest available evidence; nothing contradicts it.

### C.3 Step 7 — the refinement adoptions, with the batch's cleanest signature

Best-supported mechanism, and here the events do isolate it well:

- The post run was **certificate-dead through its whole middle** —
  roughly 25 certificates across the 400,000 events from idx 100,000 to
  500,000.
- The refinement wave fires at idx 515,243–702,434 (1,631 adoptions).
- The first colour-model rebuild after the first adoption lands at idx
  **515,534 — 291 events later**; the first `tiles.freeze` at 515,535.
- Certificates then resume after the 400,000-event drought.
- 124 distinct tiles were first certified after the first adoption; **96
  of them (77%) are new versus the baseline**, out of 126 total gains.

The chain is readable in the source: `_fold_refine_outcome` →
`_fold_placement` bumps `store._pose_gen[wid]` and returns
`[(KEY_POSE, wid), (KEY_LANE, cap, level, page)]`; `color_region`'s
prepare-stamp includes `pose_gen`, so a bump forces a colour-model
rebuild; new `ColorEvidenceRow`s wake `tiles.freeze`, which emits
`TileEvidence` at a higher epoch, which wakes `tiles.scan/union/retry`
through `KEY_TILE_EVIDENCE`.

Gains are overwhelmingly Y (100 of 126; Y 1470 → 1559), the weak plane —
consistent with a registration-pose correction being what the Y plane
needed.

### C.4 Steps 3 and 6 — UNKNOWN, honestly

- **Step 3**: 29 gains, 0 losses, exact holo1 parity. Bounded: **at
  most 22 refinement-attributable, at least 7 provably not** (at the
  first adoption post already held 789 certs vs the baseline's final
  786). The 7 certified on the first or third lane freeze epoch,
  thousands of events before any refinement job existed. `tiles.retry`
  minted **zero** certificates here and cannot re-arm scan
  (`arms_retry` re-arms the retry worker off its own `AttemptFact`,
  never the scan worker) — so retry un-gating is ruled out too.
  **What produced the early-epoch difference is UNKNOWN.**
- **Step 6**: 17 gains against 39 losses. Refinement **ruled out for 12
  of 17** (certified before the lane's first fire), plausible for 3,
  ruled out for 2 more. Six gains certified at attempt 1–9 while the
  baseline failed 47–48 attempts on the same address — extra attempts
  cannot explain a win on attempt 1, so the tile decode input itself
  differed from the run's first minutes. The post tree is not better or
  worse early; it is **different** early.

### C.5 The hard limit on all of it

No event links a certificate to the fact that woke it. `TileOutcome`
carries only `(page, ty, tx, stream_id, source, result, bp_iters)` — no
`n_informative`, no owning window, no pose, no colour-row generation, no
epoch. `AttemptFact` carries `n_informative` and components but is a
fact, never an event. And `_fold_certificate` independently appends a
`KEY_LANE` key for every lane on the page, so **each new certificate
re-arms colour and freeze on its own** — the split between
refinement-driven and certificate-driven re-freezes is **UNKNOWN** and
cannot be recovered from these run dirs at any effort.

---

## D. MEMORY

### D.1 The measurements, with their instruments

| step | volume | raster floor | baseline peak | instrument | post peak | instrument | delta | free RAM before |
|---|---|---:|---:|---|---:|---|---:|---:|
| 2 | e029 HP K | 2.83 GiB | 12.75 | getrusage (exact) | 15.35 | ps @5 s (floor) | +2.60 (+20%) | 49.8 |
| 3 | xerox c3-cmy7 | 2.22 GiB | 15.82 | getrusage (exact) | **39.44** | ps @5 s (floor) | **+23.62 (+149%)** | 47.3 |
| 4 | xerox c2-cmy8 | 8.50 GiB | 45.95 | getrusage (exact) | **≥60.51 KILLED** | ps @5 s (floor) | ≥+14.6 (≥+32%) | 44.6 / 55.9 |
| 5 | xerox c2-K | 2.83 GiB | 14.05 | getrusage (exact) | 12.60 | ps @5 s (floor) | −1.45 | 52.3 |
| 6 | xerox c2-cmy7 | 8.50 GiB | 56.34 | getrusage (exact) | 57.96 | ps @5 s (floor) | +1.62 (+2.9%) | 48.0 |
| 7 | sheet I cmy8 | 6.30 GiB | 47.86 | ps @5 s | 48.09 | ps @5 s | +0.23 (+0.5%) | 50.8 |

**Only step 7 is instrument-comparable.** On steps 2–6 the baseline is
an exact `getrusage(RUSAGE_CHILDREN).ru_maxrss` high-water mark
(`run_harvest.py:100-101`) and the post is a 5-second `ps` sample
maximum (`post_harvest.py:45,83,140`). A poll can only *miss* a peak, so
every post figure is a **lower bound** and every delta in that table is
**understated**. `step7-ledger.jsonl` records the magnitude directly:
"sampler is known to under-read: step 6 getrusage 56.34 GiB vs
ps-sampled 47.6 GiB" (that was a 30 s sampler; 5 s is better but still
one-sided).

This materially weakens two conclusions the per-volume extracts drew:

- **Step 6's "+2.9%, essentially flat" is exact-vs-sampled** and is a
  floor, not a measurement. The volume rode within 0.04 GiB of the
  58 GiB kill line on a downward-biased instrument.
- **Step 5's apparent −10% improvement is unsupportable.** The only
  defensible statement is "no evidence of an RSS increase on step 5."

### D.2 Where the growth is NOT

Three candidate mechanisms are ruled out by measurement:

**Not the mmapped raster floor.** I diffed the plane caches: the raster
sets are **byte-identical between baseline and post on every volume** —
same files, same sizes (step 2/5 four K levels 2.83 GiB; step 3 twelve
RGB levels 2.22 GiB; step 4/6 twelve RGB levels 8.50 GiB; step 7
twenty-seven levels across three captures 6.30 GiB). Both runs ingested
the same captures at the same levels. The floor is common and cannot
explain any delta.

**Not retained per-attempt state.** Attempt-key growth does not track
RSS growth at all:

| step | baseline TileOutcome | post | attempts ratio | RSS ratio |
|---|---:|---:|---:|---:|
| 2 | 7,375 | 17,261 | 2.34x | 1.20x |
| 3 | 3,399 | 6,534 | **1.92x** | **2.49x** |
| 5 | 7,218 | 9,900 | 1.37x | 0.90x |
| 6 | 17,197 | 51,052 | **2.97x** | **1.03x** |
| 7 | 238,701 | 446,525 | 1.87x | 1.005x |

Step 6 tripled attempts for +3%; step 3 didn't quite double for +149%.
And step 7 holds 446,525 attempts at 48 GiB while step 6 holds 51,052 at
58 GiB — 9x the attempt keys at 10 GiB *less*. A dict of ~450k small
tuples is a few hundred MB at most. The per-attempt store growth the
extracts inferred is real but is not the GiB-scale driver.

**Not worker-proportional allocation.** Step 4 breached at 60.51 GiB on
`--workers 8` and again at 60.24 GiB on `--workers 6` — a 25% cut in
concurrency moved the peak by 0.27 GiB (0.4%). The engine is a single
`ThreadPoolExecutor` in one process (`engine.py:196`), so `--workers`
bounds in-flight jobs, not retained state or resident pages. **The
prescribed reduced-worker fallback cannot rescue step 4 on this
machine.**

### D.3 Where it probably is — and why the artifacts cannot close it

The peaks sort cleanly by raster class rather than by volume size:
2.83 GiB floor → 12–15 GiB peaks; 6.30 → ~48; 8.50 → 46–60. Peak RSS
runs roughly 4.5–7x the raster floor, i.e. the colour lane's transient
working set over full-page RGB crops dominates, not anything retained.

But **the growth is only visible where there was room for it.** Compare
each post peak to the free RAM before its step: steps 6 and 7 peaked at
57.96 and 48.09 against 48.0 and 50.8 GiB free — at or past the
free-RAM line, where macOS reclaims clean file-backed mmap pages rather
than letting RSS grow. Step 3 peaked at 39.44 against 47.3 free — the
only colour volume with real headroom, and the only one that shows the
growth undistorted at 2.49x.

INFERRED, not measured: **the volumes that "didn't grow" are the ones
that had no room to grow**, and the cross-volume growth series is not a
comparable measurement.

Against that sits the worker-count evidence, which rules out
*worker-proportional* allocation. The two reconcile only if colour
concurrency is habitually below the worker cap — plausible, since the
frontier is a cost-ordered heap and cheap tiles work preempts, but
**not measured**. Tiers (`engine_types.py:12-23`) are priority, not
concurrency caps.

**Verdict for D: the growth locus is UNDERDETERMINED by the artifacts on
disk.** Ruled out: raster residency, attempt-key retention,
worker-proportional allocation. Still standing: concurrent colour-lane
working sets at a concurrency below the cap, and retained colour/evidence
structures. Phase attribution is **NOT DERIVABLE** for any volume — no
event dataclass in `data.py` carries a timestamp, and the ledgers persist
only a scalar peak per step plus `RSS_KILL` lines. Any phase claim would
be invented.

### D.4 Is step 4's 60 GiB the same growth or its own problem?

**The same growth, landing on the class that starts highest — not its
own problem.**

- Step 4 is in the **same raster class as step 6**: single 4800-dpi RGB
  capture, twelve levels, 8.50 GiB floor, byte-identical file sets.
- Its baseline was **45.95 GiB — 10.4 GiB *below* step 6's 56.34** and
  it completed fine. It is not an intrinsically outsized volume.
- It then grew by **≥14.6 GiB (≥32%)** to breach at 60.51. Apply
  step 3's undistorted 2.49x colour-lane growth factor to any part of a
  46 GiB baseline and the ceiling is passed trivially.
- Its kill is the batch's only *unbiased* observation of post growth on
  a large colour volume, precisely because it ran until it hit a hard
  limit instead of being quietly throttled by memory pressure.

The likelier reading is the reverse of the batch's framing: step 4 is
not the anomaly, it is the volume that had enough headroom (44.6 GiB
free) to reveal how much post actually wants — and steps 6 and 7 hid the
same appetite behind page reclaim.

---

## E. RECOMMENDED NEXT MEASUREMENTS

Ordered by value per cost. The first two need no decodes at all.

### E.1 Re-score the batch off `JobDone.n_poses` — zero cost, do first

Change `analyze_post.py:213` to read `report.json`'s
`plugin_rows[].poses` (or sum `JobDone.n_poses` over the refinement
rows). Re-run the analyzer over the existing run dirs.

**Settles:** whether *any* refinement conclusion in PARITY.md survives.
Retracts the "adopted nothing, on any volume" headline, the two
`pathological` flags, and the "cannot isolate what re-fired those scans"
open question. **No decodes, no hardware, a text edit.**

### E.2 Run one volume twice on the same tree — the determinism control

Re-run **step 5** (cheapest completed volume: 554.7 s wall, 12.6 GiB
peak, well inside headroom) a second time on the unchanged post tree.
Diff the certified tile sets and the `TileOutcome` attempt records.

**Settles the question that gates everything in §B:** is the receiver
run-to-run deterministic? If post-vs-post churn is comparable in
magnitude to the baseline-vs-post churn, then a large share of step 6's
39 losses / 17 gains and step 7's 13 losses is **noise, not a tree
change**, and no per-tile root-cause hunt is warranted. If it is
byte-identical, every mechanism claim in §B is on solid ground and the
three step-6 first-look losses become a hard defect signal.

This is the highest-value measurement in the batch and it is one cheap
decode. **Nothing else in §B or §C should be chased before it.**

### E.3 Emit the refusal reason, then re-run one colour volume

Two small edits: (a) have the refinement jobs return a `RefineRevision`
event carrying `Revision.reason`, `baseline_logloss`,
`candidate_logloss` and `candidates` on **both** branches; (b) add a
counter for `prepare_*_refine` returning `None`
(`engine.py:334-339` currently `continue`s silently).

Then re-run **step 3** (1,242 s, the cheapest colour volume).

**Settles:** the refusal histogram §A could only bound by cost —
specifically whether the ~45% non-adoption rate is mostly
`active_pose_selected` / `unchanged_affine` (**"the pose is already
right"**, i.e. the lane correctly finding nothing to improve) or
`pose_gate_failed` (**a real quality rejection**). Those two readings
have opposite implications for whether the lane is tuned correctly.
Also converts the ≥437-of-589 pre-gate floor into an exact count.

### E.4 The three step-6 first-look losses — crop-sized

`(0,19,17)`, `(0,23,2)`, `(0,37,3)`. Baseline certified each on its
first look at bp_iters 776 / 671 / 453; post failed 144 attempts each.
Decode a crop containing just those three tiles under both trees.

**Settles:** whether a specific tree change hands those addresses worse
cell values from the first freeze epoch, versus the trajectory
nondeterminism of E.2. **Run this only after E.2** — if the receiver is
nondeterministic, this crop measures nothing. Given E.2 comes back
deterministic, this is the batch's single best root-cause lead, and it is
crop-sized.

### E.5 Log an RSS time series with timestamps

Have the sampler persist every sample with its timestamp (it already
takes them at 5 s; it discards all but the max), and put a timestamp on
`data.py`'s event dataclasses. Then re-run **step 3** — the one colour
volume with headroom, where growth is undistorted by page reclaim.

**Settles:** the phase attribution §D calls NOT DERIVABLE, and
discriminates the two surviving mechanisms — a transient colour-lane
working set (peak co-located with colour job bursts) versus retained
store growth (monotone ramp). Also puts both sides of every future
comparison on **one** instrument, which steps 2–6 currently are not.

### E.6 Two cheap hygiene fixes worth folding into E.3

- **Put every plugin on `time.thread_time()`.** `color_region.py`
  (647/667/761/813) and `tiles.py:414` use `time.process_time()`
  (whole-process, all 8 threads) while `refine`, `color_refine`,
  `place_sched`, `calibrate` and `survey` use `time.thread_time()`. This
  is why step 7's `color` row reports 358,581 s of "CPU" against a
  13,580 s wall and appears to be 87% of the run. **Plugin cpu_seconds
  are currently not comparable across rows** and no cost-targeting
  decision should be made on that column until they are.
- **Put `n_informative` and the component `(capture, level, arm, epoch)`
  tuple on `TileOutcome`.** This is the single field set that would make
  per-certificate attribution possible and would close §C.5
  permanently.

### E.7 One volume-specific note, not a measurement

`tiles.retry` is pure cost on step 3 — 2,694 attempts, zero
certificates, and it structurally cannot re-arm the scan row. But it
minted 50 / 21 / 13 / 99 on steps 2 / 5 / 6 / 7. If a wall/RSS knob is
wanted it is the first candidate, but it is a **per-volume call, not a
global one**.

---

## Appendix — what these run dirs can never answer

Recorded so the next round does not re-derive it:

- **Refinement refusal reasons.** Computed as eleven exact strings,
  discarded at `engine.py:649-650`. No event carries them.
- **Prepare-stage refusal counts.** `engine.py:334-339` `continue`s
  before `worker.attempts += 1`. Unrecoverable by construction, not
  merely unlogged.
- **Per-certificate attribution.** No event links a certificate to the
  fact that woke it; `_fold_certificate` independently re-arms colour
  and freeze, so refinement-driven and certificate-driven re-freezes are
  indistinguishable.
- **Memory by phase.** No timestamps on any event; ledgers keep a scalar
  peak.
- **Which pose was live at a tile attempt.** Not recorded anywhere.

Method note worth keeping: exact per-plugin event attribution needs no
new instrumentation. `engine._merge` appends a job's own events and
*then* its `JobDone`, so the event buffer preceding each `JobDone`
belongs to that job. That is how the revisit refusal histograms in §A.3
were established exactly rather than inferred. A cheap self-check that
the attribution is sound: `CalibrateAdopted` reason `'accepted'` should
equal the calibrate job count and `'adopted'` the ctx job count, with
residual 0.
