# COLOR-UPLIFT-MEASUREMENTS — the campaign's measured record

> The receiver these measurements were made on — the v1 receiver and its
> `measure/_color_uplift_harness` — was retired 2026-09-05 at `284ae3e`; this
> document is the measured record, historical from that sha (readable at
> `git show b167b9f:…`). holo3 carries the ported arms (`plugins/color_*`,
> `tiles.uplift`); the mechanism map is src/holo/receiver/docs/retirement_docs-2026-09/HOLO1-MAP.md.


Companion to `docs/COLOR-UPLIFT-PLAN.md` (v1.8) and RECEIVE-DESIGN §6.2a (v0.53).
Doctrine: CPU-seconds primary (shared machine, wall indicative); replays are
development signal, FULL decodes are the only qualification numbers; every table
names its arm commit. Run ledger at the end. Harness:
`measure/_color_uplift_harness/` (reproduction commands in module docstrings);
run artifacts under `scratch/color-uplift/{runs,cache,logs}/`.

## 1. Corpus and provenance (pinned 2026-08-07, PK0)

`measure/_color_uplift_harness/provenance.json` — sha256 for every tiff, state,
GT, payload and recovered.bin (37.9 GiB tiffs + 3.5 GB states hash in ~31 s);
tiff↔state↔emit pairing pinned; e030 cross-check 2/2 vs `scratch/e030/tiff-shas.txt`;
every harness run refuses on sha mismatch. Archived-flag extraction: `--complete`
is NOT uniform (hp-c2-cmy8 and hp-c3-cmy8 ran without it; replay honors this
per capture); hp-c2-k used no `--page` and is **multi-invocation — earlier flags
unrecoverable, row annotated not-flag-reproducible**; `--workers`/`--source-sha256`
unknown everywhere (CLI records no argv).

Baselines (archived states, never re-run): xerox c3-cmy7 720 certs VERIFIED
301,600 B; xerox c2-cmy8 5,370 certs VERIFIED 718,413 B; hp c3-cmy8 663 certs
(C620/M43/Y0) open; xerox/hp c2-K 1,930/1,940 certs VERIFIED 465,580 B;
xerox c2-cmy7 83 certs open; hp c2-cmy8 and hp c2-cmy7 0 certs (controls).

## 2. Harness validity (PK0 acceptance, measured 2026-08-07, arm 5f2b4b9)

Truth path: GT reproduces archived certified tiles at agreement **1.000000000**
(xerox c3-cmy7: 720 certs, 8,588,160 cells; hp c3-cmy8: 663 certs, 2,636,088
cells; K via `printed_cells_from_record` on hp-c2-k: 1,940 certs, agreement 1.0).

Baseline replay fidelity (force-null, committed-pose replay of the REAL
`ProductionColorPayload.process`, prior-barrier law; certificate-ID-set identity):

| capture | replayed/archived | streams | barriers matched | re-close | wall s | CPU s | peak RSS |
|---|---|---|---|---|---|---|---|
| xerox c3-cmy7 | **720/720, identical** | main 720 | 12/12, every lane delta 0 | 301,600 B byte-exact | 1,640 | 1,622 | 12.2 GiB |
| xerox c2-cmy8 | **5,370/5,370, identical** | C 1,776 / M 1,839 / Y 1,755 | 12/12 | 718,413 B byte-exact | 3,453 | 3,425 | 37.8 GiB |
| hp c3-cmy8 | **663/663, identical** | C 620 / M 43 | 15/15 | open (honest: ≥761 symbols short, streams M,Y) | 5,483 | 5,416 | 36.4 GiB |

Wrong certificates: **0** across every replay (bar B5 exercised). Attempts folded
match archived exactly (3,878 / 14,825 / 37,642). Diag viewer attached on all
three runs: zero decode impact (l00 cert set identical with/without observer).

Harness touches since PK0 (PK3): `full` mode gained the same `--diag/--diag-port/
--diag-dir/--diag-interval/--diag-panel-width` family replay already had — one shared
`ReceiveDiagnostics` wiring, the harness's own stage-timing observer chained FIRST so a
viewer fault cannot cost a run its timings, and `finalize()` written at the end.
`replay` gained `--workers N`, which calls `holo.receive._parallel.set_worker_count` —
the identical seam `confetti.py decode --workers` uses (cli.py:483), execution-only and
bit-identical at any count. Run JSONs now record `environment.workers_requested`,
`environment.HOLO_RECEIVE_WORKERS`, and a `diagnostics` block in both modes. The three
archived baselines above were NOT re-run.

For the §4.5.1 discriminating test `replay` additionally gained `--record-attempts`,
which writes each lane's own `TileAttemptRecord` rows (state, `n_iters`, `syndrome_ok`,
`crc_ok`, `n_informative`, per-child outcomes) into the run JSON — the payload stage's
own durable records, passed through untouched; retention is opt-in so established runs
keep their exact memory profile. `--lane` already existed. Note the barrier-order law
when reading a lane-restricted run: l00 conditions on nothing, so an l00-only replay
reproduces a full run's l00 exactly (verified both arms, §4.5.1); a LATER lane alone
would not.

Replay caveats (registered): replay lane CPU includes `place_committed`
reconstruction the archived runs charged to ADDRESS — arm-to-arm comparable,
not archived-payload-comparable (a `build_address_s` split lands with PK2;
the three baselines above stay as measured). Overnight concurrency: one big
replay (36–38 GiB RSS) + at most the c3-cmy7 canary (12 GiB). K has no replay
path (declined — campaign never touches K code); B2's K bar adjudicates on
full decodes vs archived events, cross-epoch noise acknowledged.

Measured context for B3 (from retained uncertified blocks, hp c3-cmy8):
three-plane aggregate error ~22–24%, stable across all 10 retained lanes;
with Y physically dead (toner epoch) this decomposes to a C/M tail of roughly
8–15% — the just-above-threshold regime P0/P9 target. PK10 stratum sizing
confirmed from the state: 663 certs on 632 distinct addresses ⇒ **C∩M = 31
tiles = 123,256 payload cells**; xerox c2-cmy8 provides Y|C / Y|M material:
**Y certified on 1,755 tiles** (plan v1.3 floor bound was ≥918).

## 3. B7/B8 baselines — PINNED (pre-candidate, 2026-08-07)

Protocol (`_color_uplift_harness/sims.py`, BASE_SEED 20260807, deterministic):
c2-cmy7 row, real format path, honest per-plane BSC LLRs; 24 tiles/batch,
20 seeds/point; a seed passes iff all 24 tiles certify; floor ≥19/20.

B7 (BSC only): baseline **p\* = 0.015**.

| p | seeds all-pass | tiles CRC | mean cell err |
|---|---|---|---|
| 0.010 | 19/20 | 479/480 | 2.8% |
| 0.015 | 20/20 | 480/480 | 4.2% |
| 0.020 | 0/20 | 375/480 | 5.6% |
| 0.0225 | 0/20 | 158/480 | 6.3% |
| 0.025 | 0/20 | 26/480 | 7.0% |
| 0.0275 | 0/20 | 2/480 | 7.6% |
| ≥0.030 | 0/20 | 0/480 | ≥8.3% |

**B7 candidate bar (PK8, pinned): p\* ≥ 0.025 under the identical protocol, and
no tested p regresses in tiles-CRC.** (Draft shape "baseline + 1 pt" applied to
the measured 0.015.)

B8 (BSC p + independent per-cell erasure f, CURRENT whole-pack demap semantics):

| point | seeds all-pass | tiles CRC |
|---|---|---|
| p=0.01, f=0.05 | 0/20 | 401/480 |
| p=0.01, f≥0.10 | 0/20 | 0/480 |
| p=0.02, f≥0.05 | 0/20 | 0/480 |

**B8 candidate bar (PK9, pinned): ≥19/20 all-pass at (p=0.01, f=0.05), and no
grid point's tiles-CRC below baseline.**

Accounting nit FIXED by the PK3 harness touch: `sims.py`'s `cpu_s` used to read the
parent thread only (~0, because every point runs in a pool CHILD) so wall_s (207 s at
8 workers) was the only honest cost. It now adds `RUSAGE_CHILDREN` and keeps the old
number beside it as `cpu_s_parent_only`; `workers` is recorded too. The pinned B7/B8
grids above are unaffected — the change is accounting, not protocol — but the
`sims-baseline.json` row's `cpu_s` stays 0 and is not comparable to future rows.

## 4. PK3 (P1) — the cmy7 head

Arm `cmy7cal-temp7-heldout-subsplit`. New module `src/holo/receive/color_calibration.py`;
integration in `color_fitting` (`_DetectorFit.cmy7_head`, `evidence_with_divisor`),
`color_stack` (arm A4 + the force-null contract) and `color_payload`
(`ColorRegionSummary` head fields + the saturation canary).

### 4.1 The class-balancing correction (MEASURED, a spec deviation)

The plan's P1 spec is "convex multinomial NLL over softmax([0, s'₁..s'₆])". Built
exactly that way and measured on an 8×8-tile synthetic cmy7 field, the head fits the
FURNITURE PRIOR into its offsets and makes payload evidence worse:

| population | W | states 1..6 |
|---|---|---|
| known furniture (the fit population) | 44.6% | 3.2% / 3.3% / 39.3% / 3.3% / 3.2% / 3.2% |
| payload cells (the deployment population) | 15.7% | 14.5% / 14.7% / 15.7% / 14.7% / 14.4% / 10.4% |

The fitted offsets came out at `[-2.37, -1.95, +0.10, -1.51, -1.92, -2.02]` against
furniture log-prior ratios `log(count_k/count_W)` of `[-2.64, -2.61, -0.13, -2.61,
-2.64, -2.65]` — the head WAS the prior, to within 0.3 nat. Payload argmax accuracy fell
0.9135 → 0.8814 and payload NLL rose 0.225 → 0.318 while the head's own held-out loss
improved, i.e. the gate could not see the damage.

The CMY7 QDA is equal-prior BY CONSTRUCTION (`color_detect.fit_equal_prior_qda`) because
payload symbols are uniform; an unweighted head silently undoes that. **Both the fit and
the adoption gate are therefore class-balanced** (`class_balanced_weights`, weights
normalized to mean 1 so a balanced population reproduces the unweighted objective
exactly) — the same reason the policy id has carried `classbal` since the CMY8 PAVA.
Pinned by `test_the_head_calibrates_instead_of_re_priorizing`. With balancing the head
refuses on every i.i.d. synthetic channel tried (nothing to fix) and adopts only where
the detector is genuinely overconfident.

### 4.2 Synthetic end-to-end (8×8 tiles, `build_head_fixture`)

Gaussian pixel noise cannot produce the corpus pathology — it is exactly what a QDA
models, so train and held-out rows stay i.i.d. and the head correctly refuses. What
does produce it is a HEAVY TAIL: whole cells knocked off their class (voids, specks,
registration slips) land in the wrong class with an enormous score, because a Gaussian
log-likelihood falls quadratically. Measured, force-null vs live, same fixture:

| channel (blur, pixel noise, mottle, outlier frac × scale) | head | 1/a | saturation | payload argmax | payload NLL |
|---|---|---|---|---|---|
| 0.5, 0.004, –, – (clean) | `validation_gate_failed` | 1.000 | 1.0000 → 1.0000 | — (evidence byte-identical) | — |
| 1.0, 0.02, –, 6% × 0.30 | **adopted** | 15.27 | 1.0000 → **0.2814** | 0.9860 → 0.9872 | 0.106 → **0.064** |
| 1.4, 0.04, 0.15, 8% × 0.35 | adopted | 6.42 | 0.9996 → 0.0000 | 0.9719 → 0.9723 | 0.216 → 0.122 |
| 1.0, 0.02, –, 12% × 0.40 | adopted | 7.86 | 0.9999 → 0.0000 | 0.9576 → 0.9581 | 0.336 → 0.179 |
| 1.6, 0.06, 0.20, 10% × 0.45 | adopted | 4.30 | 0.9719 → 0.0000 | 0.9498 → 0.9500 | 0.466 → 0.261 |

Every adopting row COOLS (1/a > 1), drops saturation, improves payload NLL, and does not
lose accuracy. The clean row is the protection case: the gate refuses and the emitted
evidence is byte-identical to force-null.

### 4.3 Optimizer differential

The damped projected Newton is differentiated against an inline optimizer that shares no
code with it — a dense 41-point geometric scale grid crossed with bisection coordinate
descent over the offsets, using only the SIGN of a one-dimensional derivative. MEASURED
on the n=700 synthetic set: at the Newton's own scale a 40-sweep coordinate descent
reproduces its objective to `0.0e+00` (bit-identical; 20 sweeps already reach 1.1e-9,
8 sweeps 2.6e-5 — the sweep count, not the grid, is the coarse scan's residual). No
scale on the whole [0.01, 10] box beats the Newton. Newton converges in 7 iterations.

### 4.4 The null path on real paper (xerox c3-cmy7, force-null, arm 2f8d62d tree)

`--force-null --workers 4 --close`: **720/720 certificates, certificate-ID set
IDENTICAL to the archived state (missing 0, extra 0)**, every lane delta 0, re-close
VERIFIED 301,600 B to the emitted payload sha, **wrong certificates 0 / 8,588,160 cells
compared (agreement 1.000000000)**. The policy bump and the whole head infrastructure
therefore preserve the null path exactly — which is what makes the force-null flag a
usable differential from here on.

Cost: wall 1,006 s (vs 1,640 s for the sequential diag-attached baseline) at
`--workers 4`, CPU 2,183 s, peak RSS 12.9 GiB — measured while the B6 control-pricing
full decode held one core and 19 GiB, so wall is indicative only.

**NEW MEASUREMENT — the saturation canary is far worse than the headline.** The
campaign's premise quotes 19% of cmy7 cells at the L∞ bound. Measured per lane on this
capture, with no head (the pre-P1 receiver exactly):

| lane | l00 | l01 | l02 | l03 | m00 | m01 | m02 | m03 | r00 | r01 | r02 | r03 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| saturated | 0.131 | 0.599 | 0.676 | 0.643 | 0.221 | 0.455 | 0.592 | 0.610 | 0.117 | 0.497 | 0.618 | 0.608 |

The 19% figure is roughly the FIRST (2 ppc) lane. Every finer-scale lane saturates 45–68%
of its emitted cells — i.e. at the sampling footings where color decoding actually
happens, most of the durable evidence is a clipped constant carrying only its sign
pattern. That is a much larger target than the plan registered, and it is measured on a
capture that nonetheless closes VERIFIED, so it is an evidence-quality fact, not a
recoverability prediction (channel-gate-not-receiver).

### 4.5 The head on real paper (xerox c3-cmy7, LIVE, arm 2f8d62d tree)

Same capture, same flags, head enabled. **727 certificates vs the archived 720**, close
re-VERIFIED 301,600 B byte-exact, and **wrong certificates 0 / 8,671,656 cells compared
(agreement 1.000000000)** — bar B5 clean on a strictly larger certificate set. Cost is
flat: wall 1,076 s vs 1,006 s and CPU 2,256 s vs 2,183 s force-null (+3%), peak RSS
13.1 GiB vs 12.9.

Address-level (certificate ids are lane-dependent, so addresses are the honest unit):
**12 addresses gained, 5 lost, net +7**; none of the 5 lost addresses certifies anywhere
else in the run, so they are real losses, not lane relocations.

The head was ADOPTED in all twelve lanes. Temperature (1/a) and the saturation canary:

| lane | l00 | l01 | l02 | l03 | m00 | m01 | m02 | m03 | r00 | r01 | r02 | r03 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1/a | 1.52 | 1.19 | 1.25 | 1.30 | 1.58 | 1.32 | 1.45 | 1.44 | 1.48 | 1.23 | 1.31 | 1.31 |
| sat before | .131 | .599 | .676 | .643 | .221 | .455 | .592 | .610 | .117 | .497 | .618 | .608 |
| sat after | .017 | .500 | .545 | .488 | .058 | .291 | .363 | .388 | .032 | .370 | .447 | .444 |
| Δcerts | −38 | +35 | 0 | +10 | 0 | +1 | 0 | 0 | +3 | −8 | +2 | +2 |

Three things to read here, in decreasing confidence:

1. **Real paper wants a MILD head.** Every lane cools, but only by 1.19–1.58× — the
   synthetic positive control needed 4–15×. The bound was not wildly wrong, it was
   somewhat wrong, everywhere, in the same direction.
2. **Saturation falls in every lane**, most at the coarse 2 ppc footings (0.131 → 0.017,
   0.117 → 0.032, 0.221 → 0.058) and by roughly a fifth at the fine ones. That is the
   arm doing exactly what it was built to do.
3. **The lane redistribution is larger than the net gain, and it is reading (b):
   at 2 ppc the head is a strict margin LOSS.** l00 loses 38 and l01 gains 35. The
   discriminating test (§4.5.1) has now been RUN: the head costs BP margin on 262 of
   the 295 tiles that survive at l00, so this is not a cooled lane politely declining
   marginal work — it is a uniform tax whose tail happens to fall off the cliff. "P1
   is +7 on this capture" is the claim; **"P1 improves the 2 ppc lane" is FALSIFIED**
   — the net gain comes entirely from the finer-sampled lanes.

### 4.5.1 The l00 discriminating test — VERDICT (b), adverse (arm 5e51bd8)

Arm identity: both runs recorded HEAD `5e51bd8` (the PK3 commit, which landed while
they were running) with `dirty: true` from harness/doc edits only — `git diff 5e51bd8
-- src/` is empty, so the decode-relevant tree is exactly 5e51bd8, i.e. the same tree
§4.5 above calls "2f8d62d tree".

Per-lane l00-only A/B on tile-level LDPC margins, both arms, same address set
(`replay --lane l00-2ppc-400dpi --record-attempts`, workers 4). Margin unit is the
attempt record's own `n_iters` — total BP iterations over the frame's 3 LDPC
children, each child summing BOTH passes of the hybrid decoder (normalized min-sum,
then one exact sum-product retry), so the exhaustion cap is 360 at `scan` and 900 at
`retry150`. Lower = more margin.

**Isolation is exact.** l00 is the first barrier and conditions on nothing, so the
l00-only replay reproduces the full run's l00 cert-for-cert in both arms: live
295/295, null 333/333. Evidence extent is identical per address across arms
(`n_informative` equal tile-by-tile) — the only thing that differs is the calibration.

| l00 | null (force-null) | live (head) |
|---|---|---|
| certificates | 333 | 295 |
| addresses gained vs the other arm | 38 | **0** |
| wall s / CPU s | 227 / 553 | 250 / 601 |

Cost caveat: the B6 control-pricing full decode was running (~100% of one core, ~17 GiB)
across part of both runs, so the timings above are indicative only. The VERDICT does not
depend on them — certificate sets and `n_iters` are deterministic and load-independent.

The live set is a **strict subset** of the null set: 295 in both, 38 lost, **nothing
gained**. Whatever the head buys on this capture, it buys none of it at 2 ppc.

**The 38 lost tiles were already marginal in both arms (answer: (ii)).** In the null
arm they certified at median `n_iters` 108 vs 14 for the 295 common tiles — and every
one of the 38 sits in the top 14% of the null lane's own BP-work distribution (median
percentile 94%, minimum 86%, **0 of 38 below the 75th percentile**). Three of them only
certified at `retry150` even in the null arm. These are not healthy tiles knocked off a
cliff; they are the lane's hardest tail.

**But the head taxes the survivors too, which is what makes it adverse.** Paired on the
295 tiles certified in BOTH arms:

| paired `n_iters` (live − null) | value |
|---|---|
| worse / better / unchanged | **262 / 1 / 32** |
| median Δ, mean Δ | +3, +4.9 |
| p10, p90, max | +0, +11, +52 |
| sign test, 263 discordant pairs | p = 3.6e-77 |

Stage-matched control (exactly one common tile certifies at a different stage in the
two arms, which could inflate its Δ): restricted to the 294 tiles that certify at
`scan` in BOTH arms the result is unchanged — 261 worse / 1 better / 32 unchanged,
median +3, mean +4.8, p = 7.1e-77.

and the tax **scales with difficulty**, which is exactly why the tail broke:

| null-arm `n_iters` band | 0–8 | 8–16 | 16–32 | 32+ |
|---|---|---|---|---|
| n tiles | 47 | 116 | 89 | 43 |
| mean Δ `n_iters` | +1.1 | +2.1 | +5.2 | **+15.9** |

So the 38 losses are not a separate phenomenon from the +4.9 mean tax — they are its
upper tail. Reading (a) is refuted as a *mechanism*: a lane that merely declined
marginal work would leave the comfortable tiles alone, and this one does not (262/295).

**The consequence is nonetheless mostly schedule, for this capture.** Of the 38, **35
are recovered downstream** (27 at l01, 4 at l02, 2 at r00, 1 at m01, 1 at r01) and **3
never certify anywhere** — and those 3 are 3 of the whole capture's 5 net address
losses. The cascade absorbs the damage; it does not prevent it.

**The mechanistic sting**: l00 is where the head applies its LARGEST correction of all
twelve lanes (1/a = 1.522) and wins its largest saturation drop (0.131 → 0.017), and it
is the one lane where it strictly loses certificates. Cooling and saturation are
therefore NOT sufficient adoption evidence — the §4.5 gate adopted in all twelve lanes
on exactly those two signals, and at 2 ppc they pointed the wrong way. A per-lane
margin check belongs in the adoption gate before P1 is proposed for qualification.

Registered caveat: a replay is development signal, and this one conditions on the
archived barrier order. The qualification number is a FULL decode (bar B2), not this.

### 4.5.2 PK3.1 — the saturation floor (the answer to §4.5.1)

**The ruling.** The head is fitted exactly as before and ADOPTED per region only
where the DEPLOYMENT population exhibits the pathology it treats: the pre-head
saturated fraction of the region's own emitted payload cells must reach
`color_stack.HEAD_SATURATION_FLOOR`. Refusal reason `saturation_below_floor`; below
the floor the emitted evidence is byte-identical to head-None (the R2 family,
extended). The signal is deployment-population, pre-decode (no BP feedback, no §6.2
loop) and cheap.

**Where the number comes from — a correction to the §4.5 canary's provenance.**
`color.cmy7_head.saturation_fraction` is measured at EMISSION, i.e. AFTER the head in
a live arm; §4.5's "sat before" row is the FORCE-NULL run's copy of it, not a pre-head
number computed inside the live run. The floor therefore needs a measurement the
receiver did not previously make: `color_stack.deployment_saturation` scores the
emitted payload cells through the selected arm's fit with NO head attached and counts
`divisor > 1` with the literal `evidence_with_divisor` expression. Cost, measured on
this machine: **1.03 CPU s per 3.23M cells** (one QDA scoring pass), paid only in a
region whose head already passed the furniture gate — zero under force-null, zero on
cmy8, zero where the head was refused upstream. The number is published as the new
diagnostic `color.cmy7_head.baseline_saturation_fraction`, so ONE live run now carries
the before/after pair §4.5 needed two runs for.

**The sweep.** Candidates 0.15 / 0.20 / 0.25 / 0.30 against the measured per-lane
pre-head saturations. Twelve lanes of xerox c3-cmy7 carry the sweep (the c2-cmy7
capture contributes one measured lane, .050 — see acceptance (c); its other eleven
are owed and cannot move the decision band they sit far below). The c3 distribution
has exactly one wide empty band:

| lane | r00 | l00 | m00 | *gap* | m01 | r01 | m02 | l01 | r03 | m03 | r02 | l03 | l02 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pre-head saturation | .117 | .131 | .221 | — | .455 | .497 | .592 | .599 | .608 | .610 | .618 | .643 | .676 |

Consequences per candidate, read off the ADDRESS ledger of the §4.5 live/null pair
(certificate counts are lane-conditional; addresses are the honest unit):

| floor | head OFF in | address gains forgone | address losses avoided | net |
|---|---|---|---|---|
| none (PK3) | — | — | — | **+7 measured** (12 gained, 5 lost) |
| 0.15 | l00, r00 | **0** | **4 of 5** (3 l00, 1 r00) | +11 predicted |
| 0.20 | l00, r00 | 0 | 4 of 5 | +11 predicted |
| 0.25 | l00, r00, m00 | 0 | 4 of 5 | +11 predicted |
| 0.30 | l00, r00, m00 | 0 | 4 of 5 | +11 predicted |

The load-bearing fact behind that "0" column: **not one of the twelve gained addresses
originates in a lane below 0.455.** They sit at l03 (5), r01 (3), l02 (2), l01 (1),
r03 (1). Four of the five lost addresses sit in lanes the floor switches off (l00 3,
r00 1); the fifth is at r01 (.497), which keeps its head.

**r00's "+3" is not a head gain** — the registered worry, and it dissolves on
inspection. r00's live arm certifies 3 more TILES than null, but 2 of the 3 are l00
losses relocating downstream (§4.5.1's cascade table: 2 of the 38 re-certify at r00),
and at ADDRESS level r00 gains exactly ZERO. The floor's measured r00 cost is 0
addresses, and switching the head off there also returns the 1 address r00 lost. m00
is the same story with less drama: 0 certificates in both arms, 0 addresses either
way, at the LARGEST correction of all twelve lanes (1/a = 1.583) — an unvalidated head
firing at full strength into a lane that has never shown it can use one.

All four candidates are therefore equivalent in measured consequence, and the choice
is made on MARGIN — which candidate sits deepest inside the empty band, so lane drift
cannot flip a rung:

| candidate | nearest measured lane below | nearest above | min margin |
|---|---|---|---|
| 0.15 | .131 (l00) | .221 (m00) | .019 |
| 0.20 | .131 (l00) | .221 (m00) | .021 |
| 0.25 | .221 (m00) | .455 (m01) | .029 |
| **0.30** | .221 (m00) | .455 (m01) | **.079** |

**HEAD_SATURATION_FLOOR = 0.30**, policy token
`cmy7cal-temp7-heldout-subsplit-satfloor30`. It is also the conservative direction: a
higher floor withholds the head more readily, and every measured benefit of the head
to date comes from lanes at .455 and above.

**Acceptance replays.** Three, reported in the order they were RUN — the l00 lane
first (it is the lane §4.5.1 convicted, and it is cheap), then the whole capture,
then the second capture. All are committed-pose replays: development signal, not
qualification (bar B2 is a FULL decode).

**Acceptance (b): l00 is restored EXACTLY (arm 4e60e1c tree, LIVE, `--lane
l00-2ppc-400dpi --record-attempts --workers 4`).** The lane the §4.5.1 test convicted:

| l00 | null (§4.5.1 reference) | LIVE with the floor |
|---|---|---|
| certificates | 333 | **333** |
| addresses gained / lost vs the null arm | — | **0 / 0** |
| head reason | `force_null` | **`saturation_below_floor`** |
| pre-head saturation the floor read | .131 (emitted canary) | **.131** (measured in-run) |
| emitted saturation / temperature (1/a) | .131 / 1.0 | .131 / **1.0** |
| attempt records (state, `n_iters`, `syndrome_ok`, `crc_ok`, `n_informative`) | 1,305 | **1,305, identical multiset** |

Two things are worth separating here. The certificate set is identical, and so is
**every one of the 1,305 attempt records** — same tiles, same BP iteration counts, same
outcomes. That is stronger than "the losses came back": it says the floor refusal is a
literal null down to the decoder's work, so the §4.5.1 margin tax (262 of 295 survivors
taxed, p=3.6e-77) is not reduced at l00, it is **absent** (0 of 333). It also
independently confirms the new measurement: the floor's in-run `.131` reproduces the
archived force-null canary to three decimals on a population of millions of cells.
Cost caveat: this ran beside the c2-cmy7 replay and the B6 control-price full decode,
so 319 s wall / 741 s CPU vs the null's 227 / 553 is not a cost comparison.

**Acceptance (a): the full capture — +14 addresses and NOTHING lost** (arm 4e60e1c
tree, LIVE, `--workers 4 --close`, xerox c3-cmy7):

| arm | certificates | addresses gained / lost vs null | wrong certs | close |
|---|---|---|---|---|
| null (force-null) | 720 | — | 0 | VERIFIED 301,600 B |
| PK3 head everywhere | 727 | 12 / 5 = **+7** | 0 | VERIFIED |
| **PK3.1 head + floor** | **734** | **14 / 0 = +14** | **0 / 8,755,152 cells (agreement 1.0)** | **VERIFIED 301,600 B** |

The certificate set is a strict SUPERSET of the archived 720 (missing 0, extra 14) —
where PK3's live arm was a 727-set that had *traded* 5 addresses away. Doubling the
net gain is the smaller half of the result; the honest headline is that the floor
removed the entire loss column.

| lane | l00 | l01 | l02 | l03 | m00 | m01 | m02 | m03 | r00 | r01 | r02 | r03 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| head | **OFF** | on | on | on | **OFF** | on | on | on | **OFF** | on | on | on |
| pre-head saturation | .131 | .599 | .674 | .646 | .225 | .468 | .592 | .610 | .141 | .500 | .621 | .608 |
| 1/a applied | 1.000 | 1.202 | 1.265 | 1.300 | 1.000 | 1.290 | 1.444 | 1.437 | 1.000 | 1.230 | 1.302 | 1.309 |
| certs vs null | +0 | +8 | −1 | +8 | +0 | +0 | +0 | +0 | +2 | −9 | +4 | +2 |

Three lanes refuse `saturation_below_floor` — exactly the three the sweep predicted,
at exactly the predicted margins. Two secondary facts worth keeping:

1. **The floor's input is stable across runs.** These pre-head saturations are
   re-measured on a DIFFERENT emitted population than §4.5's (l00 now certifies 38
   more tiles, so every later lane sees a different open set). Maximum drift versus
   the archived numbers: **0.024** (r00 .117 → .141), and every other lane moves by
   ≤0.013. The chosen floor's margin is 0.079, so the verdicts are not perched on
   measurement noise.
2. **l01's "+35" in §4.5 really was 27 relocations plus 8 gains** — predicted from
   the address ledger before this run, and measured here at exactly +8 with l00 whole.

Cost: wall 1,321 s / CPU 2,644 s / 13.3 GiB against the null's 1,006 / 2,184 / 12.9,
but two other heavy jobs shared the machine for the whole run (the c2-cmy7 replay and
the B6 control-price full decode), so this is NOT a cost measurement. The floor's own
priced cost is one extra QDA scoring pass per adopting region — 1.03 CPU s per 3.23M
cells measured directly, i.e. order 10 s across nine adopting lanes here.

**Acceptance (c): xerox c2-cmy7, the report-only negative (B4 class) — PARTIAL, one
lane.** The full 12-lane pass was attempted twice and is still owed: the force-null
pass reached lane 8 of 12 in ~4 h before its process was reaped by the harness
runner's background-task manager (no JSON written; not a decode fault), so the run
recorded here is the BOUNDED one — `--lane l00-2ppc-600dpi`, which the barrier-order
law makes exact for the first lane:

| xerox c2-cmy7, l00-2ppc-600dpi | value |
|---|---|
| certificates | **2** — identical to the archived state's own l00 (2) |
| head verdict | fitted, furniture gate PASSED, then **`saturation_below_floor`** |
| pre-head saturation | **0.0497** |
| emitted saturation / 1/a | 0.0497 / 1.000 (nothing applied) |
| wall / CPU (contended) | 723 s / 1,876 s, peak 10.8 GiB |

Two things this buys. First, it is the sweep's second capture, and it lands nowhere
near the decision band: c2-cmy7's coarse lane saturates **5%** of its emitted cells,
less than half of the lowest c3 lane, so the pooled measured distribution still has
its single empty band at .221 → .455 and 0.30 keeps its 0.079 margin. Second, it is
the pathology's most extreme form to date: the furniture gate ACCEPTED a head here,
on a population where 95% of the evidence is unclipped and honest — precisely the
regime §4.5.1 proved the head taxes. The floor withheld it, and the lane reproduces
the archived certificates exactly.

Still owed (report-only, no bar): the remaining eleven c2-cmy7 lanes, for the full
per-lane saturation table and a whole-capture delta against the 83-cert baseline.

### 4.6 cmy8 scope (CONFIRMED — the queued replays finished)

PK3 must be a STRICT no-op on cmy8: the head is gated on
`spec.codec is CMY7_P120_V0` in `color_stack.fit_region_stack`, and `_fit_detector`
does not even carry a held-out population for cmy8. Pinned in-suite by
`test_cmy8_regions_gain_no_head_and_no_new_diagnostics`,
`test_region_details_emit_head_keys_only_for_cmy7` and
`test_the_heldout_population_is_carried_for_cmy7_only`.

The two corpus confirmations were QUEUED at PK3's hand-off
(`scratch/color-uplift/logs/pk3-cmy8-noop.sh`, strictly sequential, 36–38 GiB each);
both have since COMPLETED and both are the expected strict no-op:

| capture | LIVE pk3 replay | certificate-ID set vs archived | wrong certs |
|---|---|---|---|
| xerox c2-cmy8 | 5,370 (C 1,776 / M 1,839 / Y 1,755) | **identical** (missing 0, extra 0) | 0 / 21,351,120 cells (agreement 1.0) |
| hp c3-cmy8 | 663 (C 620 / M 43) | **identical** (missing 0, extra 0) | 0 / 2,636,088 cells (agreement 1.0) |

Artifacts `runs/xerox-c2-cmy8-replay-pk3.json`, `runs/hp-c3-cmy8-replay-pk3.json` and
their `score-pk3-*.json`. No scope escape. PK3.1 does not widen the scope: the floor
lives inside the same `spec.codec is CMY7_P120_V0` branch, so cmy8 still never fits,
gates, or measures anything — pinned by the same three tests plus the extended
`test_cmy8_regions_gain_no_head_and_no_new_diagnostics` assertion that a cmy8 region's
`cmy7_baseline_saturation_fraction` stays the UNMEASURED sentinel.

## 5. PK4 (P0) — per-window photometric maps (arm A3)

`src/holo/receive/color_locality.py`; RECEIVE-DESIGN §6.2a + its PK4 amendment.
One gain and one offset per RGB channel per window (6 parameters), fitted by
class-balanced weighted least squares toward the INCUMBENT region QDA's class means
over the labelled SEARCH cells of window ∪ halo, shrunk toward identity, applied to
the incumbent arm's features, then offered to the standing three-way comparison on a
REFITTED region QDA. Two nested gates, both furniture populations: a per-window
pre-gate (PK3.1's lesson one level lower — a window's map must strictly improve the
incumbent model's class-balanced NLL on that window's OWN held-out labels) and then
the region-level arm gate. Kind-AGNOSTIC: the maps transform RGB features, so cmy8
regions fit them too. That is not a footnote — the uplift target IS a cmy8 capture,
and unlike A4 this arm is no cmy8 no-op.

### 5.1 The sweep — method

Grid pre-registered before any point ran: halo weight ∈ {0.25, 0.5, 1.0} ×
shrinkage prior λ0 ∈ {20, 40, 80}.

Measured on the UPLIFT TARGET itself rather than on the cheap canary, by exploiting
the barrier-order law: `--lane l00-2ppc-400dpi --lane l01-4ppc-800dpi` on hp-c3-cmy8
carries **494 of that capture's 663 certificates (74.5%)** and is EXACT — l00 is the
first barrier and conditions on nothing, l01 conditions on l00 alone, so a two-lane
replay reproduces a full run's first two barriers cert-for-cert. Confirmed before the
sweep: the force-null two-lane reference measures **179 + 315 = 494 (C 467 / M 27)**,
identical to the archived lanes, lane for lane and stream for stream
(`runs/hp-c3-cmy8-l0001-pk4-forcenull.json`).

Cost per point ≈ 500 s wall / 1,180 s CPU / 9.0 GiB at `--workers 4`, so the grid is
~75 min instead of the ~7.5 h a nine-point full-capture sweep would need. Each point
is a `--window-phot HALO,PRIOR` run: the harness exports
`HOLO_COLOR_WINDOW_PHOTOMETRY` and records it, and the receiver publishes the
EFFECTIVE pair per region (`color.window_maps.halo_weight` / `.prior_labels`), so a
swept run never leans on the policy token (which names the FROZEN pair) to say what
it ran.

Unit: ADDRESSES `(page, tile, stream)` against the force-null reference
(`_color_uplift_harness.address_delta`, new) — certificate counts cannot separate
"gained a tile" from "certified the same tile one barrier later".

### 5.2 The sweep table (hp c3-cmy8, l00+l01, address delta vs force-null)

| halo | λ0 | certs | C | M | gained | lost | **net** | l00 (acc/win, arm) | l01 (acc/win, arm) | CPU s |
|---|---|---|---|---|---|---|---|---|---|---|
| — (force-null) | — | 494 | 467 | 27 | — | — | — | no maps | no maps | 1,177 |
| **0.25** | **20** | **511** | **484** | 27 | 34 | 17 | **+17** | 16/69 refused | 45/129 **adopted** | 1,184 |
| 0.25 | 40 | 509 | 482 | 27 | 34 | 19 | +15 | 16/69 refused | 46/129 adopted | 1,148 |
| 0.25 | 80 | 506 | 479 | 27 | 32 | 20 | +12 | 18/69 refused | 47/129 adopted | 1,179 |
| 0.5 | 20 | 503 | 476 | 27 | 33 | 24 | +9 | 15/69 refused | 43/129 adopted | 1,146 |
| 0.5 | 40 | 505 | 478 | 27 | 30 | 19 | +11 | 16/69 refused | 44/129 adopted | 1,132 |
| 0.5 | 80 | 501 | 474 | 27 | 28 | 21 | +7 | 16/69 refused | 47/129 adopted | 1,129 |
| 1.0 | 20 | 498 | 471 | 27 | 28 | 24 | +4 | 15/69 refused | 43/129 adopted | 1,128 |
| 1.0 | 40 | 500 | 473 | 27 | 29 | 23 | +6 | 15/69 refused | 44/129 adopted | 1,110 |
| 1.0 | 80 | 501 | 474 | 27 | 28 | 21 | +7 | 15/69 refused | 45/129 adopted | 1,111 |

Five things this table says, in decreasing confidence:

1. **A3 moves the B3 target's C stream and nothing else.** Every point raises C
   (467 → 471–484) and every point leaves M at exactly 27. Y stays 0 (dead plane,
   toner epoch). The arm is not a wash and it is not a coin flip.
2. **The HALO axis carries the result and is monotone.** Row means +14.7 / +9.0 /
   +5.7 for halo 0.25 / 0.5 / 1.0. A neighbour's cells are evidence about the
   NEIGHBOUR's photometry; on this channel the drift the arm exists to track has
   structure at the window scale, so pooling harder dilutes exactly the signal being
   fitted. The λ0 axis is the weaker same-signed effect inside the winning row
   (17 > 15 > 12) and is within noise elsewhere (halo 1.0 reads 4 / 6 / 7).
3. **BOTH GATES ARE LIVE, and they disagree by lane.** At l00 (2 ppc) 15–18 windows
   earn a map at every point and the REGION gate refuses the arm at every point —
   l00's certificate set is therefore bit-identical to force-null in all nine runs.
   At l01 (4 ppc) 43–47 windows earn a map and the region gate adopts. The
   per-window pre-gate refuses the large majority everywhere (53/69 and 84/129 at
   the frozen point), all as `validation_gate_failed`: no window on this capture is
   label-starved, they simply cannot each show an improvement.
4. **The effect is largely constant-INSENSITIVE, and the constants move the tail.**
   24 addresses are gained by all nine points and 14 lost by all nine; the grid
   spans 36 ever-gained and 29 ever-lost. So the sweep is choosing a tail, not a
   mechanism.
5. **There is a real loss column at every point**, unlike PK3.1's floor, which
   removed one entirely. The frozen point trades 34 gained for 17 lost at l01 — all
   of it at l01, since l00 is an exact null. Whether the losses survive a full
   decode is a different question (PK3's §4.5.1 measured 35 of 38 l00 losses
   recovered downstream); §5.6's full-capture replay is what answers it.

### 5.3 The choice, and the boundary problem (OPEN, lead ruling requested)

**FROZEN: halo weight 0.25, λ0 = 20**, policy token
`winphot-gainoffset-halo025-shrink20`, generated from the constants themselves
(`WindowPhotometryConfig.policy_token`) so token and numbers cannot drift apart. It
is the best pre-registered point on the stated criterion (hp c3-cmy8 stream-cert
delta in the C direction), by +2 over its own row's next point and +6 over anything
outside that row.

**But the optimum sits ON the grid boundary in both coordinates, and one
out-of-grid probe says the boundary is not the optimum.** A tenth run — halo weight
**0.0**, i.e. own-window-only, λ0 = 20, run as a MECHANISM DIAGNOSTIC and NOT as a
candidate — measures:

| point | certs | C | gained | lost | net |
|---|---|---|---|---|---|
| halo 0.25, λ0 20 (frozen) | 511 | 484 | 34 | 17 | +17 |
| **halo 0.0, λ0 20 (out of grid)** | **521** | **494** | **45** | 18 | **+27** |

i.e. the monotone halo trend continues past the pre-registered floor, and on this
capture **the halo is a net harm**: dropping it entirely gains 11 more addresses for
one more loss. That is not a constant this packet may quietly adopt — RECEIVE-DESIGN
§6.2a states the A3 family as a "window+halo fit", so halo = 0 is a DESIGN change
(the neighbourhood pooling stops existing), not a swept value. Recorded here,
unadopted, with two candidate amendments for the lead:

(a) extend the grid downward ({0, 0.1, 0.25} × {10, 20, 40}) and re-freeze; or
(b) drop the halo from the A3 family and keep the machinery only as a knob for
    captures whose windows ARE label-starved (none on this corpus: every refusal
    here is `validation_gate_failed`, never a starvation reason — which is itself
    the reason the halo buys nothing here and might still matter on scrap/confetti
    material, where windows are small and furniture is scarce).

One caveat against over-reading the diagnostic: it is a single point on a single
capture's first two barriers, and the halo's designed purpose — making six
parameters identifiable where a window's own furniture cannot — is precisely what
this corpus never tests.

### 5.4 Cross-pathology synthetic — the law the arm is held to

A single fixture cannot state A3's law. A channel that adopts says nothing about
restraint; a channel that refuses says nothing about capability. So the guardrail is
a MATCHED PAIR from `_color_stack_fixtures.build_locality_fixture`, identical in
blur, noise, seeded field and tone, differing in exactly one thing — a spatially
varying gain (`ColorChannelParameters.gain_gradient`, new in
`qualification/color_synthetic.py`; the all-zeros default skips the multiplication
entirely, a bit-exact render no-op, pinned, so every pre-PK4 fixture is untouched).

| channel (blur 1.0, noise 0.10, paper 0.8, contrast 0.4, 8×8 tiles) | windows accepted | arm | region held-out NLL | head |
|---|---|---|---|---|
| gain gradient ((0.40,0),(0,0.40),(0.28,0.28)) | **41 / 64** | **ADOPTED** | 0.115003 → **0.015997** | adopted |
| the same channel, no gradient | **0 / 64**, all `validation_gate_failed` | not attempted | 0.000000 → 0.000000 | refused |

and on the null twin the emitted evidence is **bit-identical to the force-null
receiver's, window for window** — the head refuses there too, so that comparison is
A0/A1 against A0/A1 with nothing in between.

The tone is deliberately faint. At the full-contrast tone of the other fixtures the
seven classes sit a whole unit apart and a page-global QDA separates them through
any gain a valid gradient can apply, so no photometric arm — right or wrong — could
earn its gate. Faint ink is what makes a cross-window gain drift comparable to the
class spacing: with paper `p` and ink absorption `a`, a ±G ramp overlaps white with a
one-plane state page-wide once `G > a/(2p-a)` (= 1/3 here). That is the measured HP
regime this arm exists for, and the only regime in which the question has an answer.

### 5.5 R8 first observation — A3 CAN fire on noise alone (registered, not tuned)

Same null-twin channel, gradient still zero, noise swept:

| noise std | windows accepted | arm adopted | region held-out NLL |
|---|---|---|---|
| 0.10 | 0 / 64 | no | 0.000000 → 0.000000 |
| 0.15 | 0 / 64 | no | 0.000028 → 0.000025 |
| 0.22 | **13 / 64** | **yes** | 0.003960 → 0.003821 (−3.5%) |
| 0.30 | **22 / 64** | **yes** | 0.037475 → 0.035083 (−6.4%) |

At very low SNR the per-window fit starts absorbing the noise REALIZATION, and both
gates — which measure the same furniture population the map was fitted against
(registered compromise R6) — accept it. The improvements are marginal (3–6% of NLL,
against the gradient channel's 7.2×), so the signature is distinguishable, but the
mechanism is real: this is R8's "flag at first observation, don't pre-tune".
Recorded, NOT mitigated — the honest fix is P6 (certificate-fed populations), not a
constant chosen against a synthetic.

### 5.6 Acceptance replays — and the STOP: A3 costs addresses on xerox c3-cmy7

All replays at the frozen constants, `--workers 4 --close`, arm `pk4`
(tree = e4150a9 + this packet's uncommitted diff).

**(a) The null path is exact.** `--force-null`: **720/720, certificate-ID set
IDENTICAL to the archived state** (missing 0, extra 0), wrong certificates
**0 / 8,588,160 cells (agreement 1.000000000)**, re-close **VERIFIED 301,600 B**
against both the emitted payload sha and the archived recovered.bin. Cost 1,143 s
wall / 2,326 s CPU / 13.0 GiB (contended — the B6 control-price full decode held one
core throughout). So the whole A3 apparatus preserves the pre-PK4 receiver exactly,
which is what makes the differential below mean something.

**(b) LIVE — the bar is NOT met.** 736 certificates against PK3.1's 734, close
re-VERIFIED 301,600 B, wrong certificates **0 / 8,779,008 (agreement 1.0)**. But the
packet's bar was "≥734 with ZERO addresses lost", and:

| arm | certs | vs the archived 720 | vs PK3.1's 734 |
|---|---|---|---|
| PK3.1 (head + floor) | 734 | +14 gained, **0 lost** — a strict SUPERSET | — |
| **PK4 (head + floor + A3)** | **736** | **+18 gained, 2 LOST** — not a superset | **7 gained, 5 lost, net +2** |

Per lane, with each lane's head verdict and its A3 verdict:

| lane | PK4 | PK3.1 | archived | head (PK4) | pre-head sat: PK4 / PK3.1 | A3 windows |
|---|---|---|---|---|---|---|
| l00 2ppc | **329** | 333 | 333 | `saturation_below_floor` | .055 / .131 | 70/134 adopted |
| l01 4ppc | 276 | 277 | 269 | adopted | .462 / .599 | 89/136 adopted |
| l02 6ppc | 65 | 61 | 62 | adopted | .579 / .674 | 91/137 adopted |
| l03 12ppc | 26 | 22 | 14 | adopted | .557 / .646 | 85/137 adopted |
| m00 2ppc | 0 | 0 | 0 | `saturation_below_floor` | .068 / .225 | 103/158 adopted |
| m01 4ppc | 0 | 0 | 0 | **`saturation_below_floor`** | **.276 / .468** | 63/152 adopted |
| m02 6ppc | 0 | 0 | 0 | adopted | .390 / .592 | 72/148 adopted |
| m03 12ppc | 1 | 1 | 1 | adopted | .433 / .610 | 73/148 adopted |
| r00 2ppc | 8 | 7 | 5 | `saturation_below_floor` | .043 / .141 | 68/134 adopted |
| r01 4ppc | 21 | 19 | 28 | adopted | .338 / .500 | 53/136 adopted |
| r02 6ppc | **4** | 10 | 6 | adopted | .435 / .621 | 72/137 adopted |
| r03 12ppc | 6 | 4 | 2 | adopted | .471 / .608 | 73/137 adopted |

Three findings, in decreasing confidence.

1. **At 2 ppc, A3 costs certificates — cleanly attributable.** l00 is the first
   barrier (conditions on nothing, so its count is exact) and the head is OFF in
   BOTH arms there (`saturation_below_floor` in each). The only difference at l00 is
   A3, and l00 reads **329 against 333** in both PK3.1 and the archived state: −4.
   This is the §4.5.1 pattern repeating one arm lower — a treatment that improves
   furniture NLL at the coarsest sampling footing and pays for it in BP margin. PK3
   met this and PK3.1 answered it with a DEPLOYMENT-population floor; A3 has no
   such floor, and its region-level gate adopted at l00 here (on the cmy8 capture
   the same gate REFUSED at l00 — see §5.2 finding 3 — so the gate is not blind, it
   is just not sufficient).
2. **The two addresses lost against the archived baseline are both at page column
   0** — `(0, 6, 0)` and `(0, 15, 0)`, first certified at l00 and r00 in the null
   arm. Edge windows are where a per-window map has the least support and a
   one-sided halo; that is a HYPOTHESIS from two addresses, not a measurement.
3. **A3 invalidates PK3.1's swept floor margin — measured, and one lane already
   flipped.** Better-conditioned features produce less extreme QDA scores, so A3
   lowers the pre-head L∞ saturation in EVERY lane (column 5 above: .131→.055,
   .599→.462, .225→.068, .468→.276, .500→.338, …). PK3.1 chose 0.30 because the
   measured distribution had one wide empty band at .221–.455, giving a margin of
   .079/.155. Under A3 the distribution is
   {.043 .055 .068 .276 .338 .390 .433 .435 .462 .471 .557 .579} — the band is GONE,
   0.30 now sits between .276 and .338 (margin .024/.038), and **m01's head flips
   from `adopted` to `saturation_below_floor`**. The cmy7 head's constant was swept
   against a distribution this arm moves; the two arms are not independent and the
   floor is now perched on measurement noise.

**Bar verdict: FAILED.** "≥734" holds (736); "ZERO addresses lost vs the PK3.1 set"
does not (5 lost), and the certificate set is no longer a superset of the archived
one (2 lost). Reported here rather than worked around: the queued non-regression
replays were allowed to finish because they are read-only measurements the lead
asked for, but nothing is proposed for adoption.

### 5.7 THE B3 DATUM — hp c3-cmy8, the uplift target

The capture the campaign exists for. LIVE replay, frozen constants, against PK3's
run (which reproduced the archived 663 cert-for-cert, §4.6):

| | certificates | C | M | Y | close |
|---|---|---|---|---|---|
| archived / PK3 | 663 | 620 | 43 | 0 | open |
| **PK4 (A3)** | **709** | **667** | 42 | 0 | open |
| delta | **+46** | **+47** | −1 | 0 | — |

Address level: **54 gained (all C), 8 lost (7 C, 1 M), net +46.** Wrong certificates
**0 / 2,818,984 cells (agreement 1.000000000)**. The close stays OPEN and must — Y
never certifies on this Y-starved M281 print, so the fountain still binds on a dead
stream; A3 changes nothing about that and was never going to.

Against the plan's pre-registered expectation (§1: "M 43 → 100–300, C 620 → 650–750;
Y stays 0"), **C lands at 667, inside the registered band; M does not move** — which
is the honest outcome, because M's uplift was P9/PK10's mechanism (conditioning M on
certified C), not A3's.

| lane | PK4 | PK3 | A3 windows | note |
|---|---|---|---|---|
| l00 2ppc | 179 | 179 | 16/69, arm REFUSED | exact null, bit-identical set |
| l01 4ppc | **332** | 315 | 45/129 adopted | exact (priors identical), **+17** |
| l02 8ppc | 57 | 50 | 41/124 adopted | |
| l03 12ppc | 24 | 30 | 48/122 refused | conditional on l01/l02 |
| l04 24ppc | 25 | 26 | 40/112 adopted | |
| m00–m04 | 3/10/2/2/20 | 3/8/4/2/13 | 56–82 of 164–222 | m04 **+7** |
| r00–r04 | 2/18/9/19/7 | 2/10/4/9/8 | 17–45 of 69–129 | r01 **+8**, r03 **+10** |

Only l00 and l01 are clean comparisons (l00 conditions on nothing; l01's priors are
identical because l00 is an exact null). Everything below them sees a different open
set, so a per-lane minus sign there is a schedule fact, not a regression — the honest
whole-capture unit is the address ledger above.

**Cost, and a real regression.** Wall 2,928 s vs PK3's 2,910 s and CPU 6,713 s vs
6,723 s — flat, as the sweep predicted (the A3 fit is one extra QDA fit plus a 2×2
normal equation per window). But **peak RSS is 45.6 GiB against PK3's 34.1 GiB
(+34%)**: A3 holds a THIRD per-window feature tuple (the mapped one) alongside A0's
and A1's for the life of the region. On this machine that is 45.6 of 64 GiB for a
single lane — an operational ceiling, not a rounding error, and it is the one cost
the ladder's "≤4 QDA fits per region" budget did not account for.

### 5.8 B1 non-regression — xerox c2-cmy8 still CLOSES byte-exact

| | certificates | C | M | Y | close |
|---|---|---|---|---|---|
| archived / PK3 | 5,370 | 1,776 | 1,839 | 1,755 | VERIFIED 718,413 B |
| **PK4 (A3)** | **5,366** | 1,776 | 1,839 | **1,751** | **VERIFIED 718,413 B** |

**B1 HOLDS**: the recovered sha matches both the emitted payload and the archived
`recovered.bin`, and wrong certificates are **0 / 21,335,216 cells (agreement 1.0)**.

But it is NOT the exact-null this capture was under PK3: the certificate set moves by
**22 extra and 26 missing** for a net −4, entirely in the Y stream. A3 is
kind-agnostic and this is a healthy three-plane capture, so — unlike PK3 — it was
never going to be a no-op here; the plan's "no cert change by design" line applies to
exact-null adoptions, and A3 adopts. The close's surplus absorbed the loss. Cost:
2,530 s wall / 4,063 s CPU (PK3: 2,396 / 3,945) and again the memory story —
**46.2 GiB peak against 33.7 GiB**.

### 5.9 PK4 verdict

| bar / check | outcome |
|---|---|
| suite + backbone green, collect-only clean | **PASS** (1,081 passed / 37 skipped; seven-coding gate net 8/8; 1,118 collected) |
| force-null c3-cmy7 720/720 identical | **PASS** (missing 0, extra 0; re-close VERIFIED) |
| live c3-cmy7 ≥734 with ZERO addresses lost | **FAIL** — 736, but 5 lost vs PK3.1 and 2 lost vs the archived set |
| live hp-c3-cmy8 B3 movement, zero wrong | **PASS** — C 620 → **667**, M 43 → 42, 0 wrong |
| xerox c2-cmy8 closes byte-exact | **PASS** — VERIFIED 718,413 B (set moves −4) |
| zero wrong certificates anywhere (B5) | **PASS** — 0 across 8.59M + 8.78M + 2.82M + 21.34M cells |
| cost | CPU flat; **peak RSS +34–37% on both cmy8 captures** |

A3 is the largest measured uplift of the campaign so far on the target it was built
for (+47 C on hp c3-cmy8) and it violates the packet's own no-loss bar on the canary.
Both facts are the same mechanism seen from two channels, and the shape is PK3's
exactly: an arm that improves the furniture NLL everywhere, helps where the pathology
is severe, and taxes the coarse footings where it is not. **NOT PROPOSED FOR
ADOPTION** in this form; §5.3 and the packet report carry the three candidate
answers (a deployment-population gate for A3 in PK3.1's shape, the halo ruling, and
the floor re-sweep A3 forces on PK3.1).

## 6. PK4.1 — the lead's rulings on §5.3/§5.6, and what measuring them found

Four rulings were implemented (`src/holo/receive/color_locality.py`,
`color_stack.py`): (1) A3 gets a DEPLOYMENT-SHAPED region floor in PK3.1's shape,
gating on the per-region photometric DISPERSION of the fitted window maps;
(2) the halo becomes ADAPTIVE — own labels whenever they clear the fit floors,
neighbours pooled at weight 1.0 only on starvation — so the swept halo weight
leaves the family and the token becomes
`winphot-gainoffset-adaptivehalo-shrink20-dispfloor0p12`; (3) the two floors are
swept JOINTLY on the post-A3 landscape; (4) the ladder now CONSUMES its feature
tuples, dropping each the moment no arm can still select it.

### 6.1 The statistic, stated before it was measured

Per region, over the windows that EARNED a map (the pre-gate's accepted set), with
each window's effective label count as mass:

    dispersion_gain   = max over RGB of the mass-weighted stdev of the fitted g_c
    dispersion_offset = the same for the fitted o_c   (measured, published, UNGATED)

Fewer than two accepted maps cannot disagree, so the statistic is the UNMEASURED
sentinel (−1.0) rather than 0.0, and the floor refuses. A region below the floor
refuses A3 with `photometric_dispersion_below_floor` and the mapped feature arrays
are never allocated at all — the R3 exact null, now also a memory saving. The
statistic is computed from the fits alone: cheap, pre-decode, no BP feedback.

### 6.2 THE HARVEST — and the finding that inverts the ruling's premise

The floor's value cannot be chosen from a synthetic, so the arm was first run with
the floor at **0.0** (adopt wherever the pre-gate and the three-way gate agree,
i.e. PK4's policy with PK4.1's adaptive halo) and the per-region dispersion
published as a diagnostic. Full 12-lane LIVE replay, xerox c3-cmy7, λ0 = 20:

| lane | ppc | certs | archived | acc/ref | gain disp | offset disp | pre-head sat |
|---|---|---|---|---|---|---|---|
| **l00** | 2 | **330** | 333 | 71/63 | **0.0741** | 0.0410 | .054 |
| m00 | 2 | 0 | 0 | 102/56 | 0.0649 | 0.0363 | .081 |
| r00 | 2 | 8 | 5 | 73/61 | 0.0474 | 0.0240 | .043 |
| m02 | 6 | 0 | 0 | 76/72 | 0.0452 | 0.0258 | .411 |
| m01 | 4 | 0 | 0 | 62/90 | 0.0409 | 0.0242 | .298 |
| m03 | 12 | 1 | 1 | 72/76 | 0.0391 | 0.0230 | .436 |
| r02 | 6 | 5 | 6 | 69/68 | 0.0262 | 0.0141 | .446 |
| r01 | 4 | 19 | 28 | 62/74 | 0.0256 | 0.0166 | .344 |
| r03 | 12 | 6 | 2 | 74/63 | 0.0214 | 0.0129 | .486 |
| **l01** | 4 | **280** | 269 | 88/48 | **0.0184** | 0.0121 | .465 |
| l03 | 12 | 21 | 14 | 89/48 | 0.0166 | 0.0122 | .571 |
| l02 | 6 | 62 | 62 | 89/48 | 0.0164 | 0.0126 | .564 |

Whole capture: **732 certificates = 14 gained / 2 lost against the 720 null**
(the two lost are `(0,6,0)` and `(0,15,0)`, the same page-column-0 pair PK4 lost),
and **−2 against PK3.1's 734** (3 gained, 5 lost). Four windows POOLED a halo, all
at m00 — the first starvation this corpus has ever produced, and it appeared only
once the standing halo was removed.

**The finding: on this capture the dispersion signal runs the WRONG WAY for a
floor.** The lane A3 damages — l00, where it costs 3 certificates with every other
arm identical — carries the HIGHEST dispersion of all twelve (0.0741), and the two
lanes where A3 wins most (l01 +11, l03 +7) carry the LOWEST (0.0184, 0.0166). The
ordering is not lane-random either: it tracks SAMPLING. The three 2-ppc lanes hold
the top three dispersions (0.0741 / 0.0649 / 0.0474) and every 4–12-ppc l/r lane
sits at 0.016–0.026. That is the signature of ESTIMATION NOISE, not of photometric
drift: at 2 px/cell a window's own ~60 labels determine six parameters poorly, the
fitted maps scatter, and the scatter is largest exactly where PK3's §4.5.1 tax and
PK4's §5.6 damage live. Averaged over the three lane families the sampling
dependence is steep and then flat — which is what an estimation-noise term looks
like, and not what a photometric-drift term looks like:

| ppc | 2 | 4 | 6 | 12 |
|---|---|---|---|---|
| mean gain dispersion | **0.0621** | 0.0283 | 0.0293 | 0.0257 |

A floor ("adopt only where the maps disagree") therefore selects FOR the
noise-fitting regime on this capture; the discriminating direction here is a
CEILING.

### 6.3 The joint sweep — STOPPED: no feasible pair exists

The A3 axis is decided by two measured points, one per capture, and the sweep never
needed a grid to resolve them because they are on the wrong sides of each other.
The same two-barrier subset PK4 swept on (hp c3-cmy8 `l00+l01` = 494 of its 663
certificates, EXACT by the barrier-order law) was re-measured at floor 0.0 with the
adaptive halo:

| capture / lane | ppc | A3's measured effect | gain dispersion | what a FLOOR must do |
|---|---|---|---|---|
| hp c3-cmy8 l01 | 4 | **+27 addresses** (342 vs the 315 force-null) | **0.0601** | ADOPT ⇒ floor ≤ 0.0601 |
| hp c3-cmy8 l00 | 2 | exact null (region gate refuses on its own) | 0.0511 | — |
| xerox c3-cmy7 l00 | 2 | **−3 certificates** (330 vs 333) | **0.0741** | REFUSE ⇒ floor > 0.0741 |

**0.0741 > 0.0601, so the two requirements are contradictory and NO (floor, floor)
pair exists.** Every floor at or below 0.0601 keeps the hp gain and keeps the
c3-cmy7 l00 damage; every floor above 0.0741 restores l00 and withholds A3 from the
whole corpus, uplift included. Per the packet's own stop rule, the sweep is
reported, not forced.

**The full 15-lane hp run closes the door on a CEILING too.** Run to completion at
floor 0.0 (§6.7), hp c3-cmy8's per-lane gain dispersions span **0.0511 – 0.0855**,
and the arm gains addresses across that whole range (l01 0.0601 +27, r02 0.0524 +8,
m04 0.0746 +2, m00 0.0855 −1). The xerox c3-cmy7 lane A3 DAMAGES sits at 0.0741 —
**inside** that interval, not above it. So the two captures' distributions overlap
in the region that matters and no threshold in EITHER direction separates "helps"
from "hurts". The statistic is not merely mis-signed; on this corpus it is not a
separator at all.

Two subsidiary facts the same runs establish.

1. **The adaptive halo is worth MORE than PK4's swept halo, on PK4's own unit.**
   hp `l00+l01` reads **521 certificates (C 494 / M 27) = +27** against the 494
   force-null reference — reproducing PK4's out-of-grid halo-0 diagnostic
   (§5.3) EXACTLY, and beating the frozen halo-0.25 point's +17 by ten addresses.
   The halo ruling is therefore independently confirmed: pooling a neighbour's
   cells dilutes the signal, and the machinery is only needed for starvation
   (measured: 4 windows in one lane of the whole corpus, all at c3-cmy7 m00).
2. **The A4 axis never becomes decidable, and it does not need to.** The head
   floor's landscape depends on which lanes A3 adopts into, so it is a function of
   the unresolved A3 axis. Measured at floor 0.0 (A3 everywhere) the twelve
   pre-head saturations are {.043 .054 .081 | .298 .344 .411 .436 .446 .465 .486
   .564 .571}: the empty band is .081 → .298 and **the frozen 0.30 sits 0.002
   ABOVE .298** — m01 flips on a margin two thousandths wide, and the same lane
   measured .276 in PK4's arm, i.e. the input itself drifts by 0.022 between two
   runs of the same arm family. On that landscape the swept choice would be ~0.19
   (margins .109/.108). In the only state that is adoptable — A3 WITHHELD — the
   landscape is PK3.1's own and **HEAD_SATURATION_FLOOR = 0.30 keeps its swept
   0.079/0.155 margins unchanged**. So the constant does not move, and the reason
   it does not move is that the arm above it does not fire.

### 6.4 P6-as-gates PREVIEW (report-only, gates nothing)

Both of A3's furniture gates are a registered compromise whose named fix is P6
(certificate-fed populations). The counterfactual is cheap to measure rather than
argue about, because a region already CARRIES the P6 population: prior-barrier
certified payload cells enter `_OwnerSelection` with furniture kind `-1` (the
KnownField's `PROVENANCE_CERTIFIED` rows, complete-state only). So every run now
publishes `color.window_maps.cert_cells` and the incumbent/mapped class-balanced NLL
on exactly that population — the same comparison the region gate makes, on
deployment cells instead of furniture. Measured on the floor-0 harvests (the only
arm state in which a mapped model exists in every lane):

| capture | lane | cert cells | incumbent NLL | mapped NLL | P6 verdict | actual effect |
|---|---|---|---|---|---|---|
| xerox c3-cmy7 | **l00** | **0** | — | — | **CANNOT RULE** | **−3 certs (the damage)** |
| xerox c3-cmy7 | l01 | 1,299,313 | 0.1385 | 0.1317 | adopt | +11 |
| xerox c3-cmy7 | l02 | 1,466,430 | 0.1336 | 0.1281 | adopt | 0 |
| xerox c3-cmy7 | l03 | 1,359,195 | 0.1611 | 0.1556 | adopt | +7 |
| xerox c3-cmy7 | m00 | 44,847 | 0.2357 | 0.2156 | adopt | 0 |
| xerox c3-cmy7 | m01 | 17,415 | 0.2268 | 0.2135 | adopt | 0 |
| xerox c3-cmy7 | m02 | 12,034 | 0.2214 | 0.1946 | adopt | 0 |
| xerox c3-cmy7 | m03 | 11,915 | 0.2624 | 0.2339 | adopt | 0 |
| xerox c3-cmy7 | r00 | 1,242,045 | 0.5457 | 0.4792 | adopt | +3 |
| xerox c3-cmy7 | r01 | 1,239,057 | 0.2220 | 0.2094 | adopt | −9 |
| xerox c3-cmy7 | r02 | 1,028,269 | 0.1840 | 0.1734 | adopt | −1 |
| xerox c3-cmy7 | r03 | 837,600 | 0.1864 | 0.1776 | adopt | +4 |
| hp c3-cmy8 | l00 | **0** | — | — | **CANNOT RULE** | exact null |
| hp c3-cmy8 | l01 | **0** | — | — | **CANNOT RULE** | **+27 (the uplift)** |

**Reading, in decreasing confidence.**

1. **P6-as-gate-population does not subsume these per-arm floors — it cannot even
   be evaluated where they are needed.** The one c3-cmy7 lane A3 damages is l00,
   the FIRST barrier: it conditions on nothing, so by the prior-barrier law its
   certified population is empty and a P6 gate has no opinion at all. The
   applicability question is loudest exactly where P6 is structurally silent.
2. **On the uplift target the P6 population is empty in every measured lane, for a
   structural reason**: a cmy8 payload cell becomes a label only when ALL THREE
   plane streams certify its tile (`known_field`: `complete = known.all(axis=1)`),
   and on the Y-starved M281 print Y never certifies. So P6 on hp c3-cmy8 has zero
   cells wherever Y is dead — which is the whole capture. (The three-plane xerox
   c2-cmy8 capture is where a cmy8 P6 population can exist at all.)
3. **Where P6 CAN rule, it rules the same way the furniture gate does — adopt,
   everywhere, including in lanes that lose certificates.** All eleven c3-cmy7
   lanes with a population prefer the mapped model, r01 (−9 certificates) among
   them, and r00's margin is the largest of the twelve. So on this evidence P6
   would not have been a sharper applicability test; it would have been the same
   answer measured on a better population. That is a NEGATIVE for the "pull P6
   forward as the applicability fix" hypothesis, and it is one capture's evidence,
   not a law: P6's stated purpose is calibration material, and this preview only
   tests it as an ADOPTION GATE.

### 6.5 What the arm does in the tree, and why

A3 is NOT PROPOSED FOR ADOPTION (PK4's verdict stands, and PK4.1 did not overturn
it). The parked constant is chosen so the receiver's behaviour on the corpus is
exactly PK3.1's while the mechanism stays live and pinned:

| **A3_DISPERSION_FLOOR = 0.12 (PARKED)** | value | margin to the floor |
|---|---|---|
| highest dispersion measured on paper (xerox c3-cmy7 l00) | 0.0741 | **+0.046** |
| the uplift lane (hp c3-cmy8 l01, +27 addresses) | 0.0601 | +0.060 |
| synthetic UNIFORM-gain channel (must refuse) | 0.0359 | +0.084 |
| synthetic GRADIENT channel (must adopt) | **0.1709** | **−0.051** |

so the cross-pathology law is still exercised in-suite on every commit — the
gradient channel adopts, the uniform one refuses with
`photometric_dispersion_below_floor` and emits evidence bit-identical to the
force-null receiver — and no corpus region can adopt. This is a PARKED value, not
a swept one; it is named in the policy token like any other adoption condition
(`winphot-gainoffset-adaptivehalo-shrink20-dispfloor0p12`), so a decode still
declares which arm it ran. `HEAD_SATURATION_FLOOR` stays **0.30** with PK3.1's own
0.079/0.155 margins, because in the parked state the landscape it was swept on is
the landscape that exists (§6.3).

### 6.6 Acceptance

| bar / check | outcome |
|---|---|
| suite + backbone green, collect-only clean | **PASS** — 1,089 passed / 37 skipped; the slow-lane seven-coding gate net 8/8 (`HOLO_RUN_SLOW_TESTS=1`); 1,126 collected |
| force-null c3-cmy7 720/720 identical | **PASS** — cert-ID set IDENTICAL (missing 0, extra 0); wrong certs **0 / 8,588,160 cells (agreement 1.0)**; re-close VERIFIED 301,600 B against BOTH the emitted payload and the archived `recovered.bin`; 924 s wall / 2,035 s CPU / 12.9 GiB |
| LIVE c3-cmy7 ⊇ PK3.1's 734 AND ⊇ the archived 720 | **PASS** — **734 certificates, the SAME ADDRESS SET as PK3.1 (0 gained, 0 lost)**, and a strict superset of the archived 720 (14 extra, 0 missing); wrong certs **0 / 8,755,152 (agreement 1.0)**; close VERIFIED 301,600 B. Net vs the null: **+14, nothing lost** |
| LIVE hp-c3-cmy8 retains PK4's +46 | **NOT MET, BY CONSTRUCTION** — the parked floor withholds A3 here too, so the arm cannot pay (the run is PK3's 663 exactly). What it WOULD be worth was measured instead at floor 0.0 (§6.7's headline): **725 certificates, C 620 → 683, net +62 addresses** (73 gained all-C, 11 lost), wrong certs **0 / 2,882,600 (agreement 1.0)**, close still OPEN on the dead Y. That is **+35% on PK4's +46**, and it is the size of the prize a working applicability test would unlock |
| LIVE xerox c2-cmy8 closes byte-exact | **PASS**, and in the HARDER configuration (floor 0.0, A3 adopting in all twelve lanes): **VERIFIED 718,413 B byte-exact**, sha matching the emitted payload and the archived `recovered.bin`; wrong certs **0 / 21,295,456 (agreement 1.0)**; churn 20 gained / 34 lost = **−14** (C −1, M −3, Y −10) against the archived 5,370 |
| zero wrong certificates anywhere (B5) | **PASS** — 0 across 8.59M + 8.76M + 2.88M + 21.30M cells compared (agreement 1.000000000 on all four) |
| cross-pathology synthetics | **PASS** — the gradient channel adopts (dispersion 0.1709), the null twin refuses every window and stays bit-identical to force-null, and PK4.1's new UNIFORM-gain channel refuses AT THE FLOOR (0.0359) with evidence bit-identical to force-null. That third channel doubles as R8's measured MITIGATION: it is exactly §5.5's noise-driven acceptance, and the floor stops it |

**The l00 restoration, lane by lane.** The LIVE c3-cmy7 run reproduces PK3.1's table
row for row, including the three heads the saturation floor withholds and the
pre-head saturations it withholds them on:

| lane | l00 | l01 | l02 | l03 | m00 | m01 | m02 | m03 | r00 | r01 | r02 | r03 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **PK4.1** certs | **333** | 277 | 61 | 22 | 0 | 0 | 0 | 1 | 7 | 19 | 10 | 4 |
| PK3.1 certs | **333** | 277 | 61 | 22 | 0 | 0 | 0 | 1 | 7 | 19 | 10 | 4 |
| PK4 (A3 adopting) | **329** | 276 | 65 | 26 | 0 | 0 | 0 | 1 | 8 | 21 | 4 | 6 |
| pre-head saturation | .131 | .599 | .674 | .646 | .225 | .468 | .592 | .610 | .141 | .500 | .621 | .608 |

Every lane's A3 verdict is `photometric_dispersion_below_floor`; the head is
`saturation_below_floor` in l00/m00/r00 and adopted in the other nine, which is
PK3.1's verdict set exactly.

**Memory (ruling 4) — implemented and pinned, and MEASURED NOT TO MOVE THE PEAK.**
The ladder now consumes its arm tuples (`color_stack.ArmFeatures`): the A0/A1 loser
is dropped at the choice, A3's first two gates refuse without ever allocating a
mapped tuple, and the mapped tuple is dropped as soon as the region gate rules. The
contract is pinned in-suite (`test_the_ladder_consumes_its_feature_tuples`). The
measurement, on BOTH cmy8 captures in the arm-adopting configuration where PK4
measured its +34%:

| capture | PK3 (pre-A3) | PK4 (three tuples) | **PK4.1 (consumed)** |
|---|---|---|---|
| xerox c2-cmy8 | 33.7 GiB | 46.2 GiB | **46.2 GiB** |
| hp c3-cmy8 | 34.1 GiB | 45.6 GiB | **45.5 GiB** |

**No change on either.** The hp run settles the attribution: that capture has ZERO
certified payload cells (Y never certifies), so this packet's P6 preview costs
nothing there and cannot be masking the saving — the third feature tuple is
therefore NOT what set PK4's peak. Something else in the A3-adopting path does
(the refit's own transients and the decode phase are the candidates; nothing here
measures which). The ownership discipline is correct, cheap, and worth keeping, but
**PK4's "+34% is the third tuple" attribution is not supported and the ~38 GiB
target is not met**. The preview is separately BOUNDED now to a 250k-cell
deterministic stride (`CERT_PREVIEW_MAX_CELLS`) because on c2-cmy8 it scored 3–4M
cells per region for a report-only number (CPU 4,167 s vs PK4's 4,063 s). The
c3-cmy7 numbers move by nothing either way (12.9 GiB force-null, 12.8 GiB live,
against PK4's 13.0).

### 6.7 PK4.1 verdict

| ruling | outcome |
|---|---|
| 1. A3 dispersion floor (deployment-shaped, PK3.1's shape) | **BUILT, MEASURED, AND THE SIGNAL DOES NOT SEPARATE.** Raw map spread tracks estimation noise as strongly as photometric drift; the damaging lane's dispersion (0.0741) lies INSIDE the helping capture's range (0.0511–0.0855). No floor and no ceiling works. Parked at 0.12 so the mechanism stays pinned and the corpus stays PK3.1 |
| 2. Adaptive halo | **CONFIRMED, and worth more than the swept weight**: +27 vs +17 on PK4's own two-barrier unit (address-for-address identical to PK4's out-of-grid halo-0 probe), +62 vs +46 on the full uplift target. Starvation pooling is real but rare (4 windows on c3-cmy7, 51 on hp) |
| 3. Joint sweep | **STOPPED per the packet's own stop rule.** The A4 axis is a function of the unresolved A3 axis; in the parked state `HEAD_SATURATION_FLOOR = 0.30` keeps PK3.1's swept margins exactly |
| 4. Memory | **BUILT and pinned; MEASURED not to move peak RSS** (46.2/45.5 GiB vs PK4's 46.2/45.6). PK4's attribution of +34% to the third feature tuple is not supported |
| 5. P6-as-gates preview | **DELIVERED, and it is a NEGATIVE for pulling P6 forward as the applicability fix**: no population at all in the lane that needs gating (first barrier) or on the uplift target (Y dead ⇒ no complete states), and "adopt" everywhere it can rule, including in a lane that loses 9 addresses |

**What the campaign should take from this.** A3 is a real uplift — **+62 addresses
on the B3 target, the largest measured in the campaign** — held back by an
applicability test nobody has yet found: three candidate signals have now been
measured (furniture NLL at the window level, furniture NLL at the region level, map
dispersion) and a fourth previewed (certified-cell NLL), and none of them separates
the lanes A3 helps from the lanes it taxes. The one structural regularity in the
evidence is SAMPLING: A3's damage is concentrated at 2 ppc on both captures (xerox
l00 −3; hp l00 and r00 are the only two lanes where the standing three-way gate
refuses on its own), and the dispersion statistic is dominated by the same axis. The
next candidate is therefore a NORMALIZED statistic — the observed between-window
spread against the spread the fit's own residual noise predicts — which is exactly
the quantity that would tell a genuinely drifting page from a poorly sampled one.
It is named, not built.

## 7. PK4.2 — the NORMALIZED dispersion statistic: built, measured, and it does not separate either

§6.7 named the successor; this packet built it, measured it on both captures at
floor 0, and it fails the same test — differently, and in a way that says something
new about why A3 works at all.

### 7.1 The statistic, stated before it was measured

`src/holo/receive/color_locality.py`; RECEIVE-DESIGN §6.2a PK4.2 amendment. Per region,
over the windows that earned a map, per RGB channel `c`, with each window's effective
label count as mass `m_w` and shares `p_w = m_w / Σm`:

    observed_c  = Σ_w p_w (g_wc − ḡ_c)²                     ← PK4.1's raw numerator
    predicted_c = Σ_w p_w (1 − p_w) s_wc²                   ← its null expectation
    NORM        = median over c of  observed_c / predicted_c

`s_wc` is the standard error of that window's SHRUNK gain: the
heteroskedasticity-consistent (Huber–White) sandwich for the window's own weighted
least squares,

    Var(ĝ_c) = W/(W−2) · Σ_i w_i² (x_ic − x̄_c)² r_ic² / [Σ_i w_i (x_ic − x̄_c)²]²

scaled by the shrinkage factor `κ_w²` so numerator and denominator measure the same
quantity. Four choices, each for a reason:

1. **The robust sandwich, not `σ²/S_xx`.** The fit weights are CLASS-BALANCING weights,
   not replication counts, so the textbook homoskedastic-plus-frequency-weights formula
   understates the variance of a gain leveraged by a sparsely populated state — exactly
   the 2 ppc regime the statistic exists to detect. (In-suite the sandwich is pinned to
   reproduce the textbook value on a homoskedastic design, to ±10%.)
2. **`(1 − p_w)`** is what the estimated weighted mean absorbs; the expectation is exact,
   not simulated. A region carried by one dominant window predicts almost no spread,
   which is correct — one window cannot disagree with itself.
3. **The MEDIAN channel, not PK4.1's max.** A ratio has a denominator: one channel whose
   residuals happen to be small would dominate a maximum on arithmetic alone.
4. **Shrunk scale on both sides**, so the ratio measures the spread of the maps that are
   actually APPLIED against the noise in those same quantities.

1.0 is the no-structure null exactly. Fit-side only — window maps, their own residuals,
their own label mass — so it is pre-decode, conditions on no certificate, and a
deployment capture computes it before it decodes a tile. Published on every region as
`color.window_maps.norm_dispersion` with both square roots of the chosen channel beside
it (`.observed_dispersion` / `.predicted_dispersion`), so the ratio can be read rather
than believed; PK4.1's raw gain and offset spreads stay published, ungated.

### 7.2 Method, and the identity check that makes the numbers comparable

Both captures replayed LIVE at **both floors 0.0** (`--window-phot 20,0.0,0.0`) — the
only landscape on which the question has an answer, since a lane where A3 is withheld
has no fitted maps to measure. Sequential, `--workers 4`.

**The runs reproduce PK4.1's floor-0 harvests ADDRESS-FOR-ADDRESS**: xerox c3-cmy7
**732 certificates, certificate address set IDENTICAL** to `…-pk41-harvest`; hp c3-cmy8
**725 (C 683 / M 42), IDENTICAL** to `…-pk41-disp0`. That is the self-check that says
PK4.2 added a statistic and not a different map — the gain and offset expressions are
PK4's character for character, and the standard error is computed beside them.

### 7.3 THE TWO-CAPTURE TABLE — 27 lanes, sorted by the statistic

Cert delta is against each capture's own no-A3 reference (xerox: the PK4.1 force-null
720; hp: PK3's 663, which reproduced the archived state cert-for-cert).

| capture | lane | ppc | **norm** | observed | predicted | raw (PK4.1) | acc/ref | A3 verdict | labelled | **cert Δ** |
|---|---|---|---|---|---|---|---|---|---|---|
| xerox c3-cmy7 | r00 | 2 | **37.63** | 0.0412 | 0.0067 | 0.0474 | 73/61 | adopted | 1,339,671 | **+3** |
| xerox c3-cmy7 | r01 | 4 | **31.12** | 0.0243 | 0.0044 | 0.0256 | 62/74 | adopted | 1,336,941 | **−9** |
| xerox c3-cmy7 | r02 | 6 | **14.72** | 0.0175 | 0.0046 | 0.0262 | 69/68 | adopted | 1,126,728 | **−1** |
| xerox c3-cmy7 | l02 | 6 | **14.22** | 0.0154 | 0.0041 | 0.0164 | 89/48 | adopted | 1,564,889 | 0 |
| xerox c3-cmy7 | r03 | 12 | **11.86** | 0.0181 | 0.0052 | 0.0214 | 74/63 | adopted | 935,861 | **+4** |
| xerox c3-cmy7 | l03 | 12 | **11.84** | 0.0133 | 0.0039 | 0.0166 | 89/48 | adopted | 1,457,456 | **+7** |
| xerox c3-cmy7 | l01 | 4 | **10.74** | 0.0176 | 0.0054 | 0.0184 | 88/48 | adopted | 1,397,197 | **+11** |
| xerox c3-cmy7 | m00 | 2 | **3.78** | 0.0501 | 0.0258 | 0.0649 | 102/56 | adopted | 144,895 | 0 |
| hp c3-cmy8 | m04 | 24 | **3.73** | 0.0746 | 0.0387 | 0.0746 | 93/129 | adopted | 96,272 | **+2** |
| **xerox c3-cmy7** | **l00** | **2** | **3.26** | 0.0533 | 0.0295 | **0.0741** | 71/63 | adopted | 97,626 | **−3 (THE DAMAGE)** |
| hp c3-cmy8 | m01 | 4 | **3.19** | 0.0578 | 0.0324 | 0.0578 | 67/97 | adopted | 98,825 | **+1** |
| hp c3-cmy8 | l04 | 24 | **3.03** | 0.0643 | 0.0369 | 0.0643 | 49/63 | adopted | 85,022 | **−3** |
| hp c3-cmy8 | m02 | 8 | **3.00** | 0.0639 | 0.0369 | 0.0639 | 76/93 | adopted | 97,236 | **+3** |
| hp c3-cmy8 | m03 | 12 | **2.94** | 0.0665 | 0.0387 | 0.0665 | 80/91 | adopted | 96,673 | 0 |
| hp c3-cmy8 | m00 | 2 | **2.92** | 0.0751 | 0.0439 | 0.0855 | 94/121 | adopted | 77,701 | **−1** |
| hp c3-cmy8 | l03 | 12 | **2.79** | 0.0591 | 0.0354 | 0.0591 | 54/68 | adopted | 91,082 | **+3** |
| xerox c3-cmy7 | m01 | 4 | **2.67** | 0.0360 | 0.0220 | 0.0409 | 62/90 | adopted | 117,452 | 0 |
| hp c3-cmy8 | r01 | 4 | **2.65** | 0.0503 | 0.0309 | 0.0592 | 51/78 | adopted | 95,409 | **+8** |
| hp c3-cmy8 | r03 | 12 | **2.62** | 0.0497 | 0.0307 | 0.0579 | 49/73 | adopted | 91,082 | **+1** |
| **hp c3-cmy8** | **l01** | **4** | **2.52** | 0.0579 | 0.0364 | 0.0601 | 49/80 | adopted | 95,409 | **+27 (THE UPLIFT)** |
| xerox c3-cmy7 | m02 | 6 | **2.36** | 0.0314 | 0.0204 | 0.0452 | 76/72 | adopted | 112,114 | 0 |
| hp c3-cmy8 | r04 | 24 | **2.32** | 0.0554 | 0.0364 | 0.0554 | 46/66 | adopted | 85,022 | 0 |
| hp c3-cmy8 | r00 | 2 | **2.28** | 0.0518 | 0.0343 | 0.0587 | 22/47 | refused (3-way) | 55,314 | 0 |
| hp c3-cmy8 | l02 | 8 | **2.28** | 0.0557 | 0.0369 | 0.0557 | 48/76 | adopted | 92,213 | **+13** |
| xerox c3-cmy7 | m03 | 12 | **2.27** | 0.0305 | 0.0202 | 0.0391 | 72/76 | adopted | 111,761 | 0 |
| hp c3-cmy8 | r02 | 8 | **2.09** | 0.0446 | 0.0308 | 0.0524 | 53/71 | adopted | 92,213 | **+8** |
| hp c3-cmy8 | l00 | 2 | **1.86** | 0.0511 | 0.0375 | 0.0511 | 18/51 | refused (3-way) | 55,314 | 0 |

Whole-capture address ledgers, unchanged from §6.2/§6.6: xerox c3-cmy7 **+14 / −2 =
+12** against the 720 null (the two lost are the same page-column-0 pair `(0,6,0)` and
`(0,15,0)` PK4 and PK4.1 lost); hp c3-cmy8 **+73 / −11 = +62**, all gains in C.

### 7.4 SEPARATION VERDICT: none, and the requirement is contradictory by 15×

    a floor must be  > 31.12  to refuse EVERY lane A3 damages
    a floor must be <=  2.09  to keep   EVERY lane A3 helps on the uplift target

Even restricting the harm side to the ONE cleanly attributable lane — xerox c3-cmy7
l00, the first barrier, which conditions on nothing and where the head is off in both
arms, so its −3 is A3 and nothing else — the requirement is `> 3.26` against `≤ 2.09`.
And a floor at 3.26 keeps exactly **one of hp's fifteen lanes** (m04 at 3.73, worth +2
in the lane ledger) and refuses l01 (+27), l02 (+13), r01 (+8), r02 (+8), l03 (+3):
essentially the entire +62.

**The `observed` and `predicted` columns do not rescue it either.** xerox l00's observed
0.0533 sits inside hp's helping range 0.0446–0.0746, and its predicted 0.0295 sits
BELOW every hp lane's (0.0307–0.0439). Neither the numerator, nor the denominator, nor
their ratio, nor PK4.1's raw spread separates the two captures. That is four columns
from one family, all negative.

### 7.5 What the statistic DID fix, and the new confound that replaces it

This is not a null result with nothing in it.

1. **Within one capture the statistic is a genuine improvement, and PK4.1's diagnosis
   was right.** On xerox c3-cmy7 the raw spread put the damaged lane at the very TOP
   (l00, 0.0741, the corpus maximum) and the two best-gaining lanes at the very BOTTOM.
   Normalizing inverts that: l00 falls to 3.26, below seven of the twelve lanes, and the
   entire sub-4 band is {m03 2.27, m02 2.36, m01 2.67, l00 3.26, m00 3.78} — the
   damaged lane plus the four lanes that contribute one certificate between them. The
   sampling confound really is gone.
2. **Across captures a NEW confound replaces it: label mass.** A variance ratio is a
   DETECTION statistic — at a fixed true drift it grows with evidence — and measured,
   `spearman(norm, labelled population) = +0.73` pooled (+0.71 xerox, +0.53 hp), while
   `spearman(norm, cert delta) = −0.26` pooled: it still points the wrong way, just less
   emphatically than the raw statistic's −0.16 within hp. xerox c3-cmy7's late lanes
   carry **0.9–1.6 M** labelled cells (their prior-barrier certified payload cells become
   complete-state labels) and read 10.7–37.6; **every** lane of hp c3-cmy8 carries
   **55–99 k** — because its Y stream never certifies on the Y-starved M281 print, so no
   cell ever becomes a complete state — and the whole capture reads 1.86–3.73. The
   apparent clean band inside xerox c3-cmy7 is exactly the boundary between its
   certificate-fed lanes and its furniture-only ones. That is not a photometric fact.
3. **THE FINDING THAT MATTERS, and it is about A3, not about the statistic.** On the
   uplift target every lane's fitted maps disagree by only 1.9–3.7× what their own
   standard errors predict, i.e. hp c3-cmy8 carries no *resolvable* photometric drift at
   the window scale — and A3 still buys **+62 addresses, the largest measured uplift of
   the campaign**. So **A3's benefit does not require the pathology A3 was designed to
   treat to be detectable.** Whatever the arm is doing on that capture — plausibly
   better-conditioned per-window features producing a better region QDA refit, rather
   than tracking a real cm-scale mottle — it is not "correcting measured spatial drift".
   Every applicability test tried so far asks a version of "does this page exhibit the
   disease?", and the measured answer on the capture that benefits most is *not visibly*.
   That is why the family keeps failing, and it is a stronger statement than §6.7's.

### 7.6 The stop, and what is in the tree

**Per the packet's own stop rule the floor is NOT forced.** `A3_NORM_DISPERSION_FLOOR`
is **0.0 = ungated**; `A3_DISPERSION_FLOOR` stays **0.12 = parked**, so the receiver's
behaviour on the corpus is exactly PK3.1's, exactly as PK4.1 left it. No floor sweep was
run: the statistic is piecewise constant per lane, so every value inside a band buys the
same verdict set (PK3.1's lesson), and there is no band. No joint re-sweep with
`HEAD_SATURATION_FLOOR` was run either, for the same reason A3's own axis is undecided —
in the parked state the landscape the head's 0.30 was swept on is the landscape that
exists, with PK3.1's own 0.079/0.155 margins. (Recorded for whoever reopens this: the
floor-0 harvest re-measures the twelve pre-head saturations as
{.043 .054 .081 | .298 .344 .411 .436 .446 .465 .486 .564 .571}, reproducing §6.3's
two-thousandths margin at m01; and had a normalized floor near 6 been adoptable, the
resulting mixed landscape would have restored m01 to .468 and left 0.30 inside a
.225→.344 band at margins .075/.044 — narrower than PK3.1's, and a re-sweep would have
chosen ≈.285. None of that is adopted; it is the arithmetic a future packet does not
need to redo.)

What the tree gains is the mechanism, live and pinned: both statistics are published on
every region and in every run JSON, the sweep hatch takes a third field
(`--window-phot PRIOR,DISPFLOOR[,NORMFLOOR]`, two fields keeping PK4/PK4.1's meaning),
and the cross-pathology law now runs on FOUR synthetic channels instead of three —
gradient adopts, null twin fits nothing, uniform gain refuses, and PK4.2's new
noise-heavy no-drift channel refuses. That fourth channel is R8's mitigation made law:
at noise 0.30 with no gain at all, the raw spread reads **0.063 — LARGER than the
page-uniform channel's 0.036**, so a raw floor placed to refuse a uniform gain would
ADOPT pure noise; the normalized statistic reads **1.63 against the gradient channel's
21.7**, a 13× separation where the raw statistic's is 2.7×. On synthetics, where the
truth is known, the statistic works. On paper it is confounded.

### 7.7 Memory — the owed §6.6 question: **A3 never cost 12 GiB. The baseline was contended.**

PK4 recorded "peak RSS 45.6 GiB against PK3's 34.1 (+34%)" and attributed it to A3's
third feature tuple; PK4.1 dropped the tuple, measured no change, and left the cause
open. PK4.2 measured the cause, with a bounded instrument and then with the clock.

**(a) The discriminating run.** `scratch/color-uplift/pk42_memtrace.py` (retired 2026-10-09; it
ran only at b167b9f, its result stands below) replays ONE lane
with a 0.5 s sampler of `ru_maxrss` (monotone, so its steps localize the peak) and of
instantaneous RSS. The lane is hp c3-cmy8 `l04-24ppc-4800dpi` — a full-capture peak can
only be set in one of the three 4800-dpi lanes, and one costs 6 minutes instead of 47.
Run back to back on an idle machine:

| arm | certificates | wall | **peak RSS** |
|---|---|---|---|
| `--force-null` (no A3 at all) | 366 | 374 s | **41,097 MiB** |
| A3 adopting (floors 0/0, arm `adopted`, 48 maps) | 373 | 404 s | **41,091 MiB** |

**Six MiB apart — 0.01%.** A3 does not set the peak, and it does not move it.

**(b) One lane is the whole story.** That single lane's 41.1 GiB is 88–90% of the entire
15-lane run's 45.5–46.9 GiB, and it is *higher than PK3's whole 15-lane "no-A3" run*
(34.1 GiB). A number that a subset exceeds is not measuring the superset.

**(c) The clock explains the rest, completely.** `ru_maxrss` is resident memory, so on a
64 GiB machine it reports what the OS let the process keep, not what the process wanted.
The B6 control-price full decodes ran overnight; matching each run's wall time against
its artifact mtime:

| run | window | peak | machine |
|---|---|---|---|
| control-price hp c2-cmy7 (full) | 08-07 18:31 → 22:37 | 34,066 | — |
| control-price hp c2-cmy8 (full) | 08-07 22:37 → 08-08 02:49 | 43,512 | — |
| **PK3 xerox c2-cmy8** | 08-07 20:06 → 20:46 | **33,732** | **INSIDE the c2-cmy7 control-price window** |
| **PK3 hp c3-cmy8** | 08-07 20:46 → 21:35 | **34,122** | **INSIDE the same window** |
| PK4 hp c3-cmy8 | 08-08 03:02 → 03:51 | 46,725 | idle |
| PK4 xerox c2-cmy8 | 08-08 03:51 → 04:33 | 47,261 | idle |
| PK4.1 xerox c2-cmy8 | 08-08 05:35 → 06:18 | 47,318 | idle |
| PK4.1 hp c3-cmy8 | 08-08 06:50 → 07:38 | 46,590 | idle |
| PK4.2 hp c3-cmy8 | 08-08 08:46 → 09:34 | 46,862 | idle |

Both PK3 cmy8 replays ran concurrently with a full decode that itself held 34 GiB, and
they measured 33.7 and 34.1 GiB — two processes splitting 64 GiB. Every post-02:49 run
of both captures, across three arms and with A3 on or off, sits in a 46.6–47.3 GiB band.
**The PK3 baseline was memory-starved, so the "+34% from A3" was a contention artifact
from the start** — which is also why PK4.1's tuple fix could not move it, and why xerox
c3-cmy7 (whose PK3 replay ran at 19:47–20:05, likewise contended, but whose peak is
13 GiB and never came near the ceiling) showed no effect at all. The campaign's own
noise floor on this number was already visible and was read past: PK3 and the pre-PK2
baseline are cert-for-cert IDENTICAL computations on both cmy8 captures and their
recorded peaks differ by 3.1 and 5.0 GiB.

**(d) What the ~41 GiB of one 4800-dpi lane actually is** (from the trace, and NOT
attributed to any single array — that needs a `tracemalloc` run under
`np.lib.tracemalloc_domain`, which is the named next instrument): 0–22 s a smooth
~365 MiB/s ramp to 6.6 GiB (the native read of the 6.9 GB TIFF); +7.1 GiB at lane open
(→13.7); 44.8–46.4 s four ~2.6 GiB bursts 0.5 s apart (→26.7 — four workers inside the
payload stage's raster-side work); 46–150 s a smooth ~72 MiB/s accumulation of a further
6.8 GiB, **all of it RETAINED** (instantaneous RSS tracks the high-water exactly, so this
is working set, not churn) → 33.5 GiB; then a single **7.6 GiB transient over 1.5 s that
is released immediately afterwards and IS the peak**. So the shape is "one lane's
retained 33.5 GiB working set plus one short terminal spike", and the retained part is
full-resolution raster-side structure for a 24 px/cell 4800-dpi lane. Nothing in the arm
ladder appears in it, which the A/B above already proves the hard way.

**No fix applied.** The ≤20-line bar is not met by anything the evidence supports:
the peak-setting 7.6 GiB transient is unattributed, and the obvious candidate (popping
`window_raw_crops` entries as `crop_features` consumes them — the dict must be fully
materialized first because the region divisor probe needs a global maximum before any
crop can be filtered) is a guess this trace does not confirm. Recorded for whoever picks
it up. **The operational conclusion stands on its own: the ~46 GiB is what a 4800-dpi
lane costs, it is not an A3 regression, and the ~38 GiB "target" PK4.1 inherited from
PK4 was never a real number.**

### 7.8 PK4.2 verdict

| question | outcome |
|---|---|
| normalized statistic built, published beside the raw one | **DONE** — `color.window_maps.norm_dispersion` + `.observed_dispersion` + `.predicted_dispersion` + `.norm_dispersion_floor` on every region and every run JSON; raw kept |
| harvested on both captures at floor 0 | **DONE** — 12 + 15 lanes; both runs reproduce PK4.1's floor-0 address sets EXACTLY (732 and 725), so the numbers are comparable by construction |
| does it separate harm from help? | **NO.** Refusing every harm lane needs > 31.1; keeping every help lane needs ≤ 2.09. On the cleanest attribution alone it is > 3.26 vs ≤ 2.09, and a floor there keeps 1 of hp's 15 lanes |
| is it better than the raw statistic? | **YES within a capture, NO across them.** It removes the sampling inversion (xerox l00 goes from corpus-maximum to below-median) and acquires a label-mass confound in its place (spearman +0.73 with labelled population) |
| floor frozen? | **NO — the stop rule is honored.** `A3_NORM_DISPERSION_FLOOR = 0.0` (ungated), `A3_DISPERSION_FLOOR = 0.12` (parked), A3 NOT ADOPTED, corpus behaviour identical to PK3.1 |
| suite + cross-pathology synthetics | **PASS** — four channels; the new noise-heavy one is R8's measured mitigation and the case the raw statistic orders backwards |
| memory (the owed §6.6 question) | **ANSWERED, and PK4's premise is RETRACTED**: A3 does not set the peak (same lane, A3 on vs force-null: 41,091 vs 41,097 MiB, 0.01% apart), one 4800-dpi lane alone exceeds PK3's whole-capture figure, and PK3's cmy8 baselines were measured while a 34 GiB control-price decode ran concurrently. The "+34% from A3" was contention (§7.7) |
| non-regression at the PARKED constants | **PASS** — xerox c3-cmy7 force-null **720/720 cert-ID identical**, re-close VERIFIED 301,600 B; LIVE **734 = PK4.1's address set EXACTLY (0 gained / 0 lost)** and a strict superset of the archived 720; wrong certificates **0** across 8,588,160 + 8,755,152 cells |
| suite | **PASS** — 1,093 passed / 37 skipped, 1,130 collected; slow lane's backbone payload gates + bounded phased e2e green. `test_measured_channel_gate`'s two c2 rows FAIL and they fail IDENTICALLY on `7706ba7` with this packet's diff stashed — a pre-existing K-path failure PK4.2 neither causes nor fixes |

**What the campaign should take from this.** Stop looking for an applicability test that
asks whether the page is sick. Five signals have now been measured (per-window furniture
NLL, region furniture NLL, raw map dispersion, normalized map dispersion) and one
previewed (certified-cell NLL), and the reason none separates is now visible in the
data: **on the capture where A3 pays most, the pathology it treats is not measurable at
all.** The next honest question is not "which statistic detects drift?" but "what is A3
actually doing on hp c3-cmy8?" — and answering that needs the payload→raw-pixel channel
model the stack is declared a transitional form of (RECEIVE-DESIGN §6.2a), not a sixth
gate constant. **A3 waits for the pixel-loop channel model** — for its LADDER-side gain.
**AMENDED by PK4.3 (§10):** its RESIDUE-side gain is claimable NOW, via a
supplemental lane, and is measured at **+6 certificates on hp c3-cmy8, +7 on
xerox c2-cmy8 and 0 on xerox c3-cmy7, with ZERO addresses lost anywhere** —
because a suppression-protected lane needs no applicability statistic at all,
which is why five of them failing stopped mattering. What still waits for the
pixel loop is the +62: that number requires letting A3 rewrite lanes the
standard ladder already wins, and it is inseparable from the 11 losses and the
canary damage that parked the arm.

## 8. PK-L — the specimen patch tier and the feature library

Two new development tiers, both built on the existing harness and neither a
source of qualification numbers. New modules:
`_color_uplift_harness/{patch_corpus,patch_runner,feature_library}.py` plus the
committed `patch_manifest.json`; run artifacts under
`scratch/color-uplift/{patches,patch-runs,feature-library}/`.

### 8.1 The specimen corpus — a pathology becomes a regression test

A SPECIMEN is a tile neighbourhood plus a whole-tile halo cropped out of a
provenance-verified capture into a standalone mini-TIFF, mounted on a 3 mm
margin of the crop's own measured paper colour, and decoded by the production
receiver as a SCRAP: fresh state, `--page 0`, survey → placement → BCH word
solve → absolute addresses → the full multi-lane ladder. Tile-to-pixel location
comes from the archived state's committed `PoseRecord` native affines (four
nearest poses, clamp recorded). Extraction is sha-gated and content-keyed; the
set of ten regenerates deterministically in 10 s.

Ten specimens pinned at policy key `5db17f7dc5ca47ad` (HEAD 2d0ebc3, no
hatches): three l00-tax patches (§4.5.1 loss clusters), two A3-gain patches
(§5.7), the page-column-0 strip (§5.6), healthy c3-cmy7 and c2-cmy8 controls
(the latter certifies C/M/Y), the print-frozen c2-cmy7 negative control, and an
M-tail patch. Whole-corpus sweep 941 s wall; per patch 37–327 s.

Tier-validity facts: `outside_domain = 0` on every specimen (absolute addresses
solved from the crop alone land in the expected rectangles); wrong certificates
0 everywhere, agreement 1.000000000; the negative control certifies 0.

**THE l00 TAX REPRODUCES** (force-null vs `--head-satfloor 0.0`, ~90 s/pair):
l00tax-c: head adopted at pre-head sat .092, 1/a 1.635, l00 14→13, paired
n_iters 13 worse / 0 better (median +6, mean +17.5), p = 2.4e-4; l00tax-b:
9→8, 7/1/0, p = 0.070; l00tax-a: the head's own furniture gate refused and the
run is an exact null (20 tiles, all Δ=0). Combined over the adopting pair:
**20 worse / 1 better / 0 unchanged, p = 2.1e-5**, loss rate 2/23 = 8.7% vs the
capture's 11.4% — same sign, same difficulty scaling, cascade absorption
included, for ~90 s / 1.2 GiB against §4.5.1's 477 s wall / ~12 GiB replays.
A3 at patch scale reproduces its DAMAGE (a3gain-a l00 11→10 at floor 0) and
not its whole-page GAIN — use the tier for A3's damage, never to price its
benefit.

### 8.2 What the patch tier does NOT reproduce — measured, not assumed

`patch_runner divergence` (archived addresses restricted to the specimen
domain): corpus 207 archived vs 225 patch, 194 agree, Jaccard **0.815**; xerox
c3-cmy7 **0.911** (three specimens exact), hp c3-cmy8 **0.530** with the
divergence in the PATCH's favour — a3gain-a certifies 22 where the
whole-capture decode got 11 on the same tiles (a locally fitted 6×6-tile
region QDA on a photometrically drifting page — a different experiment, not a
broken one; registered as the leading post-referendum candidate: the honest
form of P0 may be a per-region page partition rather than per-window maps).
Even agreeing addresses frequently certify at a different barrier. **The tier
claims end-to-end regression and pathology development; quote patch DIFFS,
never patch levels.**

### 8.3 Pins and the compare workflow

`pin` keys each specimen's outcome by the FULL receiver policy id AND the
environment-hatch signature; `compare` diffs against the pin for the current
key, falling back loudly to the newest older pin (fired for real once: a
mid-session token change moved the key and the fallback said so; diff clean).
Re-pinning is an explicit command. Intended cadence: one compare sweep
(~16 min) after every packet merge — the per-specimen diff is review evidence.

### 8.4 The feature library — fidelity EXACT, and the win is memory

`dump` records the six raster-side seams (crop_features, window_raw_crops,
_fit_registration, _features_with_page_fraction, place_committed,
refine_color_address_once), content-addressed on each call's own inputs;
`run` serves them and opens NO raster. Validity invariants: a PRODUCER
identity (sha256 over the six shadowed modules' source — the arm ladder is
deliberately excluded; that is the point) and the PRIOR-BARRIER FRONTIER
check (a lane's features are valid only while the certificates minted before
it are unchanged; the run stops at the first diverging lane).

| unit | certs | fidelity | wall | CPU | peak RSS |
|---|---|---|---|---|---|
| xerox c3-cmy7, 12 lanes, parked | 734 | cert-ID set IDENTICAL to its replay, 12/12 lanes; superset of archived (+14/−0); wrong 0/8,755,152 | 1270→661 s | 2250→1365 s | 13.4→**2.9 GiB** |
| hp c3-cmy8 l00+l01 force-null | 494 (C467/M27) | exact | 544→390 s | 1098→885 s | 9.2→**1.7 GiB** |
| hp l00+l01, A3 floor 0 | 521, l01 342 | reproduces §6.3's +27 exactly; l00 bit-identical (frontier-confirmed) | 365 s | 848 s | 1.7 GiB |

**The honest headline is not the CPU** (sampling is 19–39% of a replay; QDA +
LDPC remain): a sweep point gains 1.3–1.9× CPU but **4.5–5.5× less memory** —
grid throughput rises ~6–8× BY CONCURRENCY (eight 1.7 GiB points fit where one
9–38 GiB replay ran alone). Tier law: the library gates ITERATION; a
committed-pose replay gates a MERGE; a FULL decode gates a BAR.

**LANE-SET TRUNCATION IS NOT NEUTRAL FOR A RE-TIMING ARM (PK10, measured — the
tier law's first real test, and it held).** A library unit is usually a LANE
SUBSET (`--lane l00 --lane l01`), which is safe for an arm whose effect is
local to the lane it fires in. It is NOT safe for an arm whose first-order
effect is to move certificates EARLIER: a two-lane window scores every
re-timing as pure gain and cannot see the compensation. Measured on
xerox c2-cmy8: the l00+l01 library read **+19 certificates at l01** and the
full twelve-lane replay reproduced that l01 figure EXACTLY, then lost nine
addresses at l03 — at the address level the +19 is **1 new address + 18
re-timings**, and the arm is net **−5**. The library was not wrong about what
it measured; it measured a quantity that does not extrapolate.

**Rule for the corpus:** for CONDITIONING-CLASS arms — anything that consumes
prior-barrier certificates, so that its benefit at lane N is partly other
lanes' work arriving sooner — only FULL-LANE-SET runs are evidence of yield.
Use the library exactly as PK10 did for everything else: it found the
material-symmetry bug, localised the dust mechanism per stratum and priced the
pre-gate tradeoff at ~8 minutes and 1.7 GiB a point, work that would have cost
eight replays and most of a day.

### 8.5 Shared-worktree contamination — two incidents, one law

A concurrent stash/pop and a concurrent commit both moved the worktree under
running jobs. Stash-window artifacts were discarded and re-run. The rule that
survives: **fingerprint the CONTENT, not the bookkeeping** — runs record
`receiver_tree_sha256` (every `src/holo/**/*.py`) + producer/arm identities at
entry AND exit; a moving tree voids the run loudly; pins carry their tree; a
library dumped on a moving tree is refused. All PK-L deliverables were
produced tree-stable.

## 9. PK10 (P9) — KnownField-conditioned marginalization, arm A4b

Arm: HEAD `aa58870`/`d14f686` + the PK10 diff. Every measurement below was
taken at `receiver_tree_sha256` `78eb0612…` (`arm_identity` `2da6a817…`,
`producer_identity` `cea2a6fd…`), the tree with A4b LIVE; the delivered tree is
`a7d347e6…`, which adds only the PARK (§9.11) and is byte-identical in
behaviour to the arm-never-built receiver. Every run records its tree at entry
AND exit and every one was tree-stable; `ab_runner` gained the same
`tree_state` fields the PK-L tiers carry, from the one implementation of them
(§8.5 norm).

**VERDICT UP FRONT: A4b is BUILT, INSTRUMENTED and PARKED BY FLAG.** It does
not earn adoption on this corpus — an exact end-to-end null on the uplift
target, net −5 addresses on the non-regression capture — and the reason it
parks by flag rather than behind a threshold is that no statistic separated the
lanes it helps from the ones it costs (§9.11).

### 9.1 What A4b does, and the three exact nulls it keeps

Per cell, a CMY8 component's marginal is taken over the state subset its
prior-barrier CERTIFIED siblings allow — 4-vs-4 with none known, 2-vs-2 with
one, 1-vs-1 with both — and read through a calibration stratified by
(plane, conditioning-pattern). Three nulls are structural, not gated:

1. **No certified sibling in the emitted population** ⇒ `no_conditioned_cells`,
   before any population is gathered or any map fitted. Measured on the
   FIRST BARRIER of both cmy8 captures (hp l00, xerox c2-cmy8 l00): the
   reason fires and the lane reproduces its archived certificate count
   exactly (179 and 3,596).
2. **CMY7 and K** never enter the module. Measured: xerox c3-cmy7's twelve
   lanes emit no `color.conditioning.*` key at all.
3. **Pattern ∅** is not refitted — it IS the incumbent detector's own map, so
   an unconditioned cell's evidence is byte-identical to today's.

Deliberate narrowing beyond the ruling: only CERTIFIED knowledge conditions an
emitted cell. Format furniture is known exactly and is still excluded, because
the certification chain erases furniture cells before any bit of them is used
(§6.3 step 3) — conditioning them would move every block digest for no decode.

### 9.2 The stratum populations, per capture (the two-source law, measured)

Cells per (plane, pattern) stratum as `cert-cross + masked-dust`; pattern
1 = {sib1}, 2 = {sib2}, 3 = {both}, siblings ascending.

| capture / lane | C1 | C2 | C3 | M1 | M2 | M3 | Y1 | Y2 | Y3 |
|---|---|---|---|---|---|---|---|---|---|
| hp c3-cmy8 l01 (priors = own l00, 179 certs) | 27681+3976 | 0+2390 | 0+4786 | 27681+3976 | 0+2390 | 0+4786 | 0+3976 | 0+2390 | 0+4786 |
| hp c3-cmy8 l00, priors SEEDED (663) | 89246+2294 | 0+1400 | 0+2779 | 89246+2294 | 0+1400 | 0+2779 | 0+2294 | 0+1400 | 0+2779 |
| xerox c2-cmy8 l01 (priors = own l00, 3,596 certs) | 42696+9173 | 16213+5548 | 267154+11059 | 42696+9173 | 73937+5548 | 267154+11059 | 16213+9173 | 73937+5548 | 267154+11059 |

The law reads exactly as designed. **Cert-cross is primary where dense and
absent where the sibling never certified**: on hp only C1/M1 carry cert
material (C is the only stream certifying early — the C∩M shape the plan
predicted), and every Y stratum is furniture-only. On xerox c2-cmy8 all nine
strata carry cert material because all three streams certify, and the region
hits `CONDITIONING_MAX_CERT_CELLS` (400,000 gathered of the ~1.5 M available).
**The masked-dust floor is present in all nine strata of every region** — that
is what it is for. Deployment side, same regions: hp l01 conditions
1,914,924 marginals at arity 1 and 41,250 at arity 2; xerox c2-cmy8 l01
conditions 7,908,674 and 2,559,895.

### 9.3 THE MATERIAL-SYMMETRY CORRECTION (measured, and it moved the verdict)

First implementation fitted the strata on the QDA's SEARCH-side word+dust and
gated on its held-out furniture. That is not a fair three-way gate:
`_fit_detector` calibrates the INCUMBENT cmy8 maps **in-sample on dust ∪
certified payload cells and keeps word out entirely**, so the candidate met an
optimistic rival on the gate's DUST leg and a pessimistic one on its WORD leg.
Measured on hp c3-cmy8 l01, the artifact was most of the signal:

| material | total | word | dust | region verdict |
|---|---|---|---|---|
| search-side word+dust (asymmetric) | .5030 → .4570 | .5149 → .4535 | .4449 → **.4681** | refused |
| incumbent's own population, stratified | .5030 → .4870 | .5149 → .4938 | .4449 → **.4532** | refused |

The dust regression fell by 64% (+.0233 → +.0083) and the refusal survived. The
material is now the incumbent's calibration population stratified — same cells,
same regime, one difference (the state subset and the pattern split) — which is
also what §6.2a's "the standing in-sample dust PAVA, pattern-stratified" says.

### 9.4 THE KILL TEST — hp c3-cmy8, maximal conditioning (l00+l01)

`--seed-archived-certificates` hands every lane the archived FINAL frontier as
priors (663 certs, C620/M43) — structurally unreachable in deployment, and a
CONTROLLED PAIR: both arms get the same priors, so the attemptable set and the
suppression are identical and A4b is the only difference. Feature-library tier,
frontier check reporting `--allow-stale-frontier` as expected (the shimmed
seams key on placements and features, not certificates, so every lookup hit).

| arm | new certificates | attempts | region verdict |
|---|---|---|---|
| A: seeded, force-null | **0** {} | 2,243 + 3,570 | — |
| B: seeded, A4b live | **0** {} | 2,243 + 3,570 | `region_gate_failed`, both lanes |

**VERDICT: null on certificates, and NOT null on evidence — the arm never
applied.** Both lanes refused at the standing three-way region gate on the
DUST leg while the other two legs improved substantially:

| lane | total | word | dust | strata adopted |
|---|---|---|---|---|
| l00 (seeded) | .5275 → .5095 | .5392 → .5160 | .46883 → **.47469** | 8/9 |
| l01 (seeded) | .5030 → .4879 | .5149 → .4950 | .44488 → **.45146** | 7/9 |

So the kill test's own question ("does the M stream gain under maximal
conditioning?") answers **no on hp**, but it cannot answer the mechanism
question, because the evidence the M stream would have consumed was never
emitted. Reported as the honest outcome it is: **the packet is not dead — it is
gate-blocked on the uplift target and alive on the other cmy8 capture (§9.5).**

### 9.5 The referendum numbers — xerox c2-cmy8 is where A4b pays

Feature-library tier, l00+l01, own accumulated certificates (no seeding).
l00 is the structural null on both captures; every delta below is l01's.

| capture / arm | l01 certs (archived 1,216 / 315) | total | word | dust | verdict |
|---|---|---|---|---|---|
| xerox c2-cmy8, A4b | **1,235 (+19)** | .25182 → .24590 | .25278 → .24603 | .24461 → .24353 | **adopted**, 8/9 strata |
| hp c3-cmy8, A4b | 315 (+0) | .5030 → .4870 | .5149 → .4938 | .4449 → .4532 | refused (dust) |

**+19 certified tiles at one barrier on xerox c2-cmy8** — with all three
furniture legs improving and zero wrong certificates. hp's l00+l01 is unchanged
at 494 (C 467 / M 27), i.e. an exact null, not a regression.

**AND THAT +19 DOES NOT SURVIVE THE FULL DOMAIN — §9.10 is the number that
counts.** The full 12-lane replay reproduces the l01 figure exactly (1,235 vs
1,216) and then loses nine addresses at l03: at the ADDRESS level, which is the
only honest unit here, the +19 is **1 genuinely new address and 18 re-timings**
of tiles the archived run certified later. The library tier measured two lanes
and could not see the compensation. Recorded as a tier-law finding, not an
excuse: **for a CONDITIONING arm a truncated lane set is not neutral**, because
conditioning's first-order effect is to move certificates EARLIER, and a
two-lane window scores that as pure gain. The library still gates iteration
correctly — it found the material-symmetry bug, the dust mechanism and the
pre-gate tradeoff for ~8 minutes a point — but its sign was overturned by the
replay, exactly as the tier law says it may be.

**LANES-TO-CLOSE: there is no room for a shift on this capture, measured.**
Solving the fountain over the archived frontier after each barrier,
xerox c2-cmy8 **already closes VERIFIED at l00**, its FIRST barrier, on 3,596
certificates — and l00 is precisely the lane where A4b is a structural null
(no prior-barrier certificate exists to condition on). Conditioning cannot
shorten a one-barrier close. Every certificate A4b adds at l01 and beyond is
therefore yield past the close, which is exactly the quantity the 2026-08-08
ruling says to count: certified tiles = yield, closes = mission events,
lanes-to-close = cost. On this corpus the cost metric is saturated and the
yield metric is the one that moves.

### 9.6 WHERE THE DUST COST LIVES — per-stratum legs, and R12 made visible

The packet added `color.conditioning.strata_deltas` (candidate − incumbent per
leg, per stratum) because a region number cannot say which stratum spent a
refusal. On hp c3-cmy8 l01 it localises the harm immediately:

| stratum | total | word | dust | cert material |
|---|---|---|---|---|
| C1 | −0.0364 | −0.0650 | **+0.0230** | 27,681 |
| M1 | −0.0042 | −0.0290 | **+0.0470** | 27,681 |
| C3 | −0.0660 | −0.0801 | +0.0007 | 0 |
| M3 | −0.0348 | −0.0413 | −0.0098 | 0 |
| Y3 | −0.0068 | −0.0224 | −0.0070 | 0 |

**The dust cost is concentrated in exactly the two strata fed by cert-cross
material** — R12's registered compromise, measured for the first time: tiles
certify BECAUSE they are easy, so a map fitted mostly on their cells is
miscalibrated for the harder dust it is then judged on. The seven
furniture-only strata span −0.0127 to +0.0070; the two cert-fed ones are
+0.0230 and +0.0470.

**And R12's severity scales with how SELECTIVE the certification was — which is
why it bites hardest on the uplift target.** Same statistic, other capture
(xerox c2-cmy8 l01): the cert-fed strata read +0.0034 / +0.0077 / +0.0033 /
+0.0072 against furniture-only ones at −0.0182 / −0.0194 — same sign, an order
of magnitude weaker. The difference is what "certified" selected. At hp l01 the
prior frontier is 179 certificates against ~5,900 tile-streams (3%), so a
cert-cross cell is a sample from the easiest 3% of the page; at xerox c2-cmy8
l01 it is 3,596 of ~5,616 (64%), which is barely a biased sample at all.

A material SIZE floor therefore cannot fix this: on hp the HARMFUL strata are
the material-rich ones (27,681 cert cells each) and the clean ones are the thin
furniture-only ones, so no threshold on count separates them — PK4.2's shape,
one arm over. The named next candidate is a cert-versus-masked BALANCE rule
(how much cert material may outvote the spatially unbiased floor), and it is
named, not built, and deliberately not swept from this data.

### 9.7 The three-way pre-gate — BUILT, MEASURED, NOT ADOPTED

If a stratum is a unit the ladder can drop on its own, should its pre-gate be
the standing three-way rule rather than A3's single strict improvement? Built
and measured on both captures. It is strictly more conservative (it can only
drop strata) and it drops the ones carrying the largest total and word gains,
because on this corpus the dust cost sits in the highest-value strata:

| capture | pre-gate | strata adopted | l01 certs | region verdict |
|---|---|---|---|---|
| xerox c2-cmy8 | single (A3's shape) | 8/9 | **1,235 (+19)** | adopted |
| xerox c2-cmy8 | three-way | 2/9 | 1,227 (+11) | adopted |
| hp c3-cmy8 | single | 7/9 | 494 (+0) | refused |
| hp c3-cmy8 | three-way | 2/9 | 494 (+0) | **adopted**, all legs better |

The three-way variant converts hp's refusal into an adoption worth ZERO
certificates and costs 8 of xerox's 19. Larger measured gain, no measured harm
either way, and A3's landed precedent — so **the single pre-gate ships and the
three-way variant is recorded, not adopted.** All three legs are measured and
published per stratum regardless; that diagnostic is what §9.6 is made of.

### 9.8 THE M NUMBER — hp c3-cmy8, full 15-lane replay

**M = 43. The bar (M > 43) is NOT met, and the arm is an exact end-to-end null:
663 certificates, C 620 / M 43, certificate-for-certificate identical to the
archived set, every lane matching its archived count.** Wrong certificates
0/2,636,088 (agreement 1.000000000); close still open (dead Y); 3,120 s wall /
7,046 s CPU / 42.6 GiB peak (contended — a specimen sweep shared the machine
for the first quarter of the run; PK4.2's comparable figure was 2,845 s /
46.9 GiB).

Every conditioned lane refused at the region gate, and the conditioning
opportunity was never small — this is a gate verdict, not a missing signal:

| lane | certs (= archived) | arity-1 marginals | arity-2 | strata adopted | verdict |
|---|---|---|---|---|---|
| l00 | 179 | 0 | 0 | — | `no_conditioned_cells` |
| l01 | 315 | 1,914,924 | 41,250 | 7/9 | `region_gate_failed` |
| l02 | 50 | 5,681,862 | 97,011 | 7/9 | `region_gate_failed` |
| l03 | 30 | 6,153,334 | 106,762 | 7/9 | `region_gate_failed` |
| l04 | 26 | 5,683,310 | 96,689 | 7/9 | `region_gate_failed` |
| m00 | 3 | 1,804,328 | 30,489 | 8/9 | `region_gate_failed` |
| m01–m04 | 8 / 4 / 2 / 13 | 0.23–1.18 M | 4,100–40,853 | 7/9 | `region_gate_failed` |
| r00 | 2 | 3,855,180 | 100,092 | 8/9 | `region_gate_failed` |
| r01–r04 | 10 / 4 / 9 / 8 | 6.2–7.2 M | 158,738–177,714 | 7/9 | `region_gate_failed` |

Fourteen refusals in a row on one capture, seven or eight strata passing their
own pre-gate every time, and up to 7.2 M conditioned marginals waiting behind
the gate. **On hp, A4b is not short of material; it is short of a dust leg.**

### 9.9 B1 NON-REGRESSION — xerox c2-cmy8, full 12-lane replay, and the
### number that decides the referendum

Close **VERIFIED 718,413 B byte-exact** (sha matches the emitted payload and the
archived `recovered.bin`); wrong certificates **0 / 21,331,240** (agreement
1.000000000); 2,532 s wall / 4,057 s CPU / 41.1 GiB peak (PK4.1's comparable
figure was 2,609 s / 46.2 GiB). Certificates 5,365 vs the archived 5,370.

**At the ADDRESS level — the only unit that separates "gained a tile" from
"certified the same tile one lane earlier" — the arm is NET NEGATIVE:**

| | count | where |
|---|---|---|
| addresses GAINED | **5** | C 4, Y 1 — at l01 (1), l03 (2), r03 (2) |
| addresses LOST | **10** | C 7, Y 3 — at **l03-16ppc-4800dpi (9)** and r01 (1) |
| net | **−5** | M unchanged at 1,839 |
| re-timed (same address, other barrier) | 50 | incl. **18 of l01's 19 extras** |

So the library's headline dissolves under the full domain: l01's +19 is one new
address plus eighteen tiles arriving earlier, and the finest lane then gives
back nine. **A4b as built LOSES certified tiles on the non-regression capture** —
PK4's failure shape exactly (`§5.6`: "the BAR FAILS: 5 addresses LOST"), and the
campaign has already ruled once on what that means for an arm.

Why the losses concentrate at l03-16ppc-4800dpi is a HYPOTHESIS, not a finding:
by that barrier the frontier is dense, so nearly every cell is conditioned and
the stratum maps — fitted heavily on cert-cross material — are applied to the
hard residual tiles they are least calibrated for (§9.6's R12 mechanism, now
costing certificates instead of dust nats). The discriminating test is a
per-stratum certificate attribution at l03, and it is owed, not done.

### 9.10 PK10 verdict

| question | outcome |
|---|---|
| kill test (hp, maximal conditioning) | **NULL on certificates** — and the arm never applied: both lanes refused at the region gate's dust leg with total/word improving by .015–.023 nats (§9.4) |
| THE M NUMBER (hp, bar M>43) | **M = 43, BAR NOT MET** — the 15-lane replay is cert-for-cert identical to the archived 663 because the region gate refused on all fourteen conditioned lanes (§9.8) |
| B1 non-regression close | **HOLDS** — xerox c2-cmy8 re-closes **VERIFIED 718,413 B byte-exact** (§9.9) |
| the referendum number, full domain | **NET −5 ADDRESSES on xerox c2-cmy8** (5 gained / 10 lost; the library tier's +19 at l01 is 1 new address + 18 re-timings). PK4's failure shape (§9.9) |
| **ADOPTION** | **NO — PARKED BY FLAG** (lead ruling 2026-08-08, §9.11). Exact null on the uplift target, net −5 on the non-regression capture, and no statistic separates the two, so `CONDITIONING_PARKED = True` short-circuits the arm before any fit and the token carries `parked0` |
| cmy7 strict no-op | **PASS** — live replay **734 certificate IDs, set-IDENTICAL to PK4.2's**; force-null **720/720 identical**; close VERIFIED 301,600 B both; zero `color.conditioning.*` keys on all 12 lanes |
| exact nulls | **PASS** — lane 0 on both cmy8 captures reproduces its archived count with `no_conditioned_cells`; force-null emits the default summary; unconditioned cells byte-identical (pinned) |
| wrong certificates | **0 EVERYWHERE** — 2,636,088 + 21,331,240 + 8,588,160 + 8,755,152 cells on the four replays, every library run, and all ten specimens; agreement 1.000000000; truth path validated on each |
| suite / backbone / collect-only | **PASS at the PARKED tree** — 1,133 passed / 37 skipped, 1,170 collected; backbone payload gates 3/3; `tests/holo/test_color_conditioning.py` is 40 of them, three of which are the park's own pins |
| specimen tier | **PASS, zero movement, twice** — 10/10 identical at the live tree and again at the parked one; 0 losses, 0 wrong certs |
| two-source provenance | **MEASURED, both sources present in every region** (§9.2); cert cap 400,000 reached on xerox c2-cmy8 |
| R12, the registered compromise | **NOW MEASURED, and it is the mechanism** — the dust cost is concentrated in the cert-fed strata and its severity scales with how selective the certification was (§9.6). The design has no rule for how much cert material may outvote the masked floor; that BALANCE rule, not a sixth size constant, is what the park waits for |
| tier law | **CONFIRMED THE HARD WAY** — the library gates iteration, the replay gates the merge, and here the replay reversed the library's sign. For arms whose first-order effect is certificate RE-TIMING, only full-lane-set runs are evidence (§9.5, §8.4) |

### 9.11 THE PARK — by flag, not by threshold (lead ruling 2026-08-08)

`color_conditioning.CONDITIONING_PARKED = True`. `color_stack` short-circuits
A4b **before** the arity census, the population gather and every fit — cheaper
than a gate refusal, and the strictest exact null available: the region summary
stays the default instance so not one `color.conditioning.*` key is emitted,
`selected_fit` is never rebound, and emission passes the same array objects the
arm-never-built receiver passed. The policy token carries the state:
`knownfield-conditioned-marginals-**parked0**`, GENERATED from the constant in
`satfloor30`'s pattern (0 = contributes nothing, 1 = live), so a decode's
declared identity can never claim conditioning the tree did not run, nor the
reverse. Pinned three ways in `test_color_conditioning.py`: parked ≡ the
arm-never-built path byte-for-byte on a capture where the unparked arm DOES
adopt (so the pin cannot pass vacuously), the short-circuit calls neither the
census nor the fitter, and the token digit tracks the constant
(`test_receive_color_refine.py`).

**Why a flag and not a floor.** A3 parks behind a threshold because a threshold
was at least measurable there. Here the harm tracks the SOURCE of a stratum's
material — cert-cross, whose selection bias scales with how selective the
certification was — and not any size, spread or ratio of it: on hp the harmful
strata are the material-RICHEST ones (§9.6). A constant chosen now would be
fitted to the very corpus that refused the arm.

**What the park waits for: the cert-versus-masked BALANCE rule** — how much
deployment-exact but selection-biased cert-cross material may outvote the
spatially unbiased masked-furniture floor. **That rule is NOT sweepable from
this corpus**: two cmy8 captures, and the statistic that would have to separate
them is confounded with how much of each page had already certified (hp l01
conditions on the easiest 3% of its page, xerox c2-cmy8 l01 on 64%).

**P9's remaining in-scope evaluation moved to PK4.3's supplemental-lane form** —
suppression-protected and monotone by construction, so it needed no gate at all,
and it measured forced conditioning on the residue. That was precisely the
question this packet's kill test could not reach: the seeded-frontier run
answered "no certificates" only because the region gate blocked the arm before
its evidence ever reached a decode (§9.4).

**ANSWERED (§10.6): M 43 → 44.** With the region gate forced
(`region_gate_forced`), 7 of 9 strata adopted and 6.5 M conditioned marginals on
the hp uplift target, forced conditioning converts exactly ONE M tile from the
residue — and it does so with the dust leg still regressing exactly as measured
here (.4487 → .4567, the cert-fed strata C1/M1 carrying it). PK10's null was a
gate verdict, and the signal behind that gate is one tile. **M's tail on this
sheet is not conditioning-limited; that is P9's final in-campaign answer.**

## 10. PK4.3 — the supplemental-lane law, and what scheduling the parked arms buys

The law is RECEIVE-DESIGN §6.2a (v0.51): *an arm that cannot prove universal
non-regression is not gated — it is SCHEDULED.* Both of this campaign's parked
arms now run as their own lane after the standard ladder, where §6.3's
per-address retirement law bounds them to the uncertified residue and makes them
monotone by construction. This section is what that bought, measured.

### 10.1 What the packet built, and the two facts that make it safe

`scale_plan` is codec-aware: a COLOR capture's plan gains `[U(Ln, a3),
U(Ln, a4b)]` after the whole l/m/r sequence, both bound to the FINEST ordinary
rung; K's plan is unchanged. A u-lane is the R leaf minus pose refinement plus
one forced arm — `place_committed` over the base lane's committed poses,
`collect_color_evidence(arm_override=…)`, the ordinary shared decode engine, its
own evidence namespace. `a3` zeroes A3's two parked dispersion floors; `a4b`
bypasses `CONDITIONING_PARKED` and the region adoption gate (measured §9.4/§9.8:
that gate, not the material, is what made A4b unreachable). Per-window and
per-stratum pre-gates stand in both.

**Fact 1 — the suppression law is the whole safety argument, and it is pinned.**
`_finish` restores the certificate store from the accumulated frontier before
the leaf runs, so `unresolved_streams` never offers a certified (address,
stream). `test_a_supplemental_lane_cannot_attempt_a_certified_address` asserts
it at the boundary on real fixture geometry: the attempted set and the certified
set are DISJOINT, and so are the minted and certified sets. Monotonicity is
therefore structural; every score below additionally asserts the superset
empirically (`address_delta`'s new `superset` field).

**Fact 2 — the u-lane's domain is its base lane's committed poses, so "the
residue" means "the residue that lane can reach".** Measured on the archived
states, taking each committed pose's page-cell span:

| capture | base lane | committed poses | tiles spanned | residue (tile, stream) pairs | reachable |
|---|---|---|---|---|---|
| hp c3-cmy8 | l04-24ppc-4800dpi | 112 | 800 / 840 | 1,857 | 1,756 (**94.6%**) |
| xerox c2-cmy8 | l03-16ppc-4800dpi | 309 | 1,871 / 1,872 | 246 | 246 (**100%**) |
| xerox c3-cmy7 | l03-12ppc-2400dpi | 137 | 830 / 840 | 120 | 112 (**93.3%**) |

This is a registered limit of the one-lane-per-arm choice, not a defect: the
finest rung is chosen without a sweep, and it happens to reach 93–100% of each
capture's residue. A u-lane at a coarser rung would reach a different (not
strictly larger) set; nothing here is tuned to make the number look good.

### 10.2 Method

Full committed-pose replays at the delivered constants, `--workers 4 --close`,
one at a time (§7.7: one 4800-dpi lane is the ~41 GiB class, so concurrency
would void the cost numbers). **The replay drives the PRODUCTION plan builder**
— `replay.replay_plan` calls `cascade.scale_plan` for the capture's coding and
requires the archived plan to be an exact PREFIX of it, driving the entries past
that prefix with a synthetic empty level. So u-lanes appear in a replay because
the receiver schedules them, never because the harness appended them, and a
change to the standard ladder stops the run instead of being re-indexed around.

**One run was VOIDED and re-run** (§8.5, the law's third incident and the first
self-inflicted one): a source edit during the first force-null replay moved
`src/holo`'s content hash between the run's entry and exit fingerprints, and the
runner said so — "THE TREE MOVED DURING THIS RUN — the result is VOID". Its
numbers are not quoted anywhere below; the whole chain was re-run on a frozen
tree. Every run quoted here is tree-stable at `receiver_tree_sha256`
`73cc0205…` (`arm_identity` `95ec93cf…`, `producer_identity` `669ea81f…`).

### 10.3 THE FOUR FIDELITY LINES — every bar met, and every u-lane cert is an ADD

| capture / arm | certificates | vs archived | vs the parked-tree baseline | close | wrong certs |
|---|---|---|---|---|---|
| xerox c3-cmy7, **force-null** | **720** | **IDENTICAL** (missing 0, extra 0) | — | **VERIFIED 301,600 B** | 0 / 8,588,160 |
| xerox c3-cmy7, LIVE | **734** | strict SUPERSET (+14, missing 0) | **0 gained / 0 lost vs PK10's 734** | **VERIFIED 301,600 B** | 0 / 8,755,152 |
| **hp c3-cmy8** (the uplift target) | **670 = C 626 / M 44 / Y 0** | strict SUPERSET (+7, missing 0) | **+7 / −0** | open (dead Y) | 0 / 2,663,920 |
| xerox c2-cmy8 (B1) | **5,379 = C 1,777 / M 1,841 / Y 1,761** | strict SUPERSET (+9, missing 0) | **+9 / −0** | **VERIFIED 718,413 B byte-exact** | 0 / 21,386,904 |

**Zero addresses lost on every capture — the superset is asserted in every
score** (`address_delta`'s new `superset` field), and every close that verified
before verifies now against BOTH the emitted payload sha and the archived
`recovered.bin`. Zero wrong certificates across **41,394,136 audited cells**,
agreement 1.000000000, truth path validated on each. The standard lanes are
untouched lane by lane: on both cmy8 captures every `l*`, `m*` and `r*` level
reproduces its ARCHIVED certificate count exactly, so the whole delta is the
supplemental tail.

**The adds, per lane and per stream — and every one of them is a NEW address:**

| capture | u-lane | arm verdict | blocks | attempts | certificates | new | re-timed |
|---|---|---|---|---|---|---|---|
| hp c3-cmy8 | `u04-a3-24ppc-4800dpi` | A3 **adopted** (floors 0; 49/112 windows earned maps; gain disp 0.0641, norm 3.01) | 798 | 3,269 | **6 (C 6)** | 6 | **0** |
| hp c3-cmy8 | `u04-a4b-24ppc-4800dpi` | A4b **`region_gate_forced`**, 7/9 strata | 798 | 3,262 | **1 (M 1)** | 1 | **0** |
| xerox c2-cmy8 | `u03-a3-16ppc-4800dpi` | A3 **adopted** (104/309 maps; gain disp 0.0353, norm 40.5) | 209 | 471 | **7 (M 2, Y 5)** | 7 | **0** |
| xerox c2-cmy8 | `u03-a4b-16ppc-4800dpi` | A4b **`region_gate_forced`**, 6/9 strata | 204 | 462 | **2 (C 1, Y 1)** | 2 | **0** |
| xerox c3-cmy7 | `u03-a3-12ppc-2400dpi` | A3 **adopted** (77/137 maps; gain disp 0.0248, norm 11.8) | 98 | 185 | **0** | 0 | 0 |
| xerox c3-cmy7 | `u03-a4b-12ppc-2400dpi` | A4b absent (cmy7 emits not one `color.conditioning.*` key) | 98 | 185 | **0** | 0 | 0 |

`re_timed = 0` everywhere is the retirement law showing through: a u-lane cannot
attempt a certified address, so unlike PK4's and PK10's headline numbers it
cannot manufacture a "gain" out of a re-timing. **+16 certified tiles across the
corpus, 0 lost, 0 wrong** — small, and every one of them real.

### 10.4 xerox c3-cmy7 — the structural-monotonicity proof, and A3's honest zero

The canary's live arm is **734 certificate IDs, set-IDENTICAL to PK10's and
PK4.2's** (0 gained / 0 lost), a strict superset of the archived 720, close
re-VERIFIED. That is the packet's required proof on real data, and it is the
first time in this campaign that A3 could be switched on for this capture
without the question "what did it cost?" — structurally, nothing.

**And A3 adds nothing here either.** The lane RAN: the dispersion floors were
zeroed, 77 of 137 windows earned maps, the region gate adopted, and 98 residue
blocks were attempted 185 times (max60 plus the full retry150 frontier). Zero
new certificates. PK4 measured "+7 gained / 5 lost" on this capture (§5.6) and
the u-lane form separates those two numbers cleanly: **A3's gains here were
re-decodes of tiles the standard ladder was already going to get, not
conversions of the residue.** An arm that only ever helps by displacing the
incumbent's own successes has nothing to give a suppression-protected lane —
which is exactly what the supplemental form exists to find out.

### 10.5 hp c3-cmy8 — THE uplift target

Standard ladder: **663, cert-for-cert the archived set.** Then:

| stage | certificates | C | M |
|---|---|---|---|
| archived / PK10 / this run's standard lanes | 663 | 620 | 43 |
| + `u04-a3` | 669 | **626** | 43 |
| + `u04-a4b` | **670** | 626 | **44** |

**C 620 → 626 (+6, all A3 on the residue), M 43 → 44 (+1, forced
conditioning).** The close stays OPEN and must — Y never certifies on this
Y-starved M281 print.

Against §5.7's PK4/PK4.1 numbers this is a different quantity and a much smaller
one, and the difference is the point: PK4.1's floor-0 harvest read **+73 gained
/ 11 lost = +62** by letting A3 rewrite the WHOLE ladder; the u-lane lets it
work only on what the ladder failed, and there it converts **6**. Both numbers
are real. The 62 is not available without also accepting the 11 losses and the
canary damage that parked the arm; the 6 is available for free.

### 10.6 THE M ANSWER — P9's final in-campaign number

**M = 44. Forced conditioning on the residue, with maximal priors, converts ONE
M tile.** The arm applied exactly as designed and the record says so: reason
`region_gate_forced`, 7 of 9 strata adopted, **6,324,708 arity-1 and 176,666
arity-2 marginals conditioned**, 111,064 cert-cross + 14,158 masked cells of
material. The region legs are published and reproduce §9.4/§9.8's mechanism
precisely — total .5006 → .4854 and word .5114 → .4911 both improve,
**dust .4487 → .4567 gets worse**, and the two strata fed by cert-cross
material (C1 +0.0211, M1 +0.0514 on the dust leg) are R12 again, unchanged.

So PK10's "no certificates" was indeed a gate verdict and not a missing signal —
but the signal behind the gate is **one tile**, not the 100–300 the plan
pre-registered for M. **This is the final in-campaign answer on P9 for this
corpus: M's tail on the hp sheet is not conditioning-limited.** Nothing here
argues for unparking A4b on the standard ladder; it argues that scheduling it
costs nothing and buys about one tile per cmy8 sheet.

One caveat, registered rather than glossed: the +1 M is the u-a4b LANE's add,
not proven to be the ARM's. That lane also re-decodes the residue through a
region model refitted on the residue's own population, and this corpus has no
control for that — force-null skips u-lanes by design, so there is no "u-lane
with the arm off". The discriminating test is a u-lane pair differing only in
the override, and it is **owed, not done**.

### 10.7 Cost

CPU-seconds primary. "standard lanes" is the run's own total minus its u-lanes,
i.e. the same 12/15-lane ladder the baseline ran.

| capture | standard lanes (this run) | baseline | u-lane pair | u-lane share | peak RSS |
|---|---|---|---|---|---|
| xerox c3-cmy7 force-null | 1,957 s CPU | 2,450 s (PK10) | **0.0 s** | **+0%** | 13,132 MiB |
| xerox c3-cmy7 live | 1,960 s | 2,146 s (PK10) | 288 s | **+14.7%** | 13,379 MiB |
| hp c3-cmy8 | 6,907 s | 7,046 s (PK10) | 1,489 s | **+21.6%** | 43,102 MiB |
| xerox c2-cmy8 | 4,034 s | 3,945 s (PK3, contended) | 924 s | **+22.9%** | 43,371 MiB |

Two readings, both stated because they answer different questions. **The arm
ladder's cost is unchanged**: standard-lane CPU sits at −9% / −2% /
+2% against the same-epoch baselines, inside B2's ±10%. **The supplemental tail
is new scheduled work and costs +15–23% CPU on top** — B2's bar was written for
an evidence-stack change and does not obviously bind a scheduling change, so the
number is reported for the lead's call rather than argued past. Peak RSS is
unmoved (§7.7 stands: the peak is one 4800-dpi lane, not the arm) — 43.1 GiB
here against PK10's 42.6 GiB on hp.

**A u-lane's price scales with the RESIDUE, not the page.** Cheapest where the
residue is smallest (xerox c2-cmy8: 246 pairs, ~300 s wall a lane) and dearest
where it is largest (hp c3-cmy8: 1,756 reachable pairs, ~350 s wall a lane at
24 ppc). One structural waste is measured and deliberately NOT fixed here: **a
cmy7 capture schedules a `u-a4b` lane whose arm cannot fire at all** (A4b is
cmy8-only), spending 70 s wall / 144 s CPU to re-decode the residue with the
standard ladder for a guaranteed zero. The fix is a per-coding arm-applicability
filter in the plan builder; that is a plan-shape change and therefore another
policy bump, so it is named here and left to a packet that is not also the one
measuring the arms.

### 10.8 The other gates

| gate | outcome |
|---|---|
| suite + collect-only | **PASS** — 1,147 passed / 37 skipped, 1,184 collected (PK10: 1,133 / 37 / 1,170; +14 = this packet's pins) |
| slow lane (`HOLO_RUN_SLOW_TESTS=1`) | backbone seven-coding gates + bounded phased e2e **PASS** (11 passed). `test_measured_channel_gate`'s two c2 rows FAIL and fail **identically at HEAD `1b44adf` with this packet's diff stashed** — reproduced, not assumed: a pre-existing K-path failure PK4.3 neither causes nor fixes (PK4.2 recorded the same) |
| specimen tier (10-specimen compare) | **PASS, zero movement** — 10/10 identical, 0 moved, 0 with losses, 0 wrong certificates, every run tree-stable. Both u-lanes ran on every specimen and added 0: a scrap's finest rung carries almost no prior frontier, which is the correct non-regression outcome. The compare fired its loud fallback (the policy key moved), so **re-pinning is owed at merge** |
| zero wrong certificates (B5) | **PASS** — 0 across 41.4 M cells on the four replays and 0 on all ten specimens |
| B1 closes | **PASS** — xerox c2-cmy8 718,413 B and c3-cmy7 301,600 B, both byte-exact against the emitted payload AND the archived recovered.bin |
| B6 addressing | **UNTOUCHED by construction** — the packet adds no addressing path, and a supplemental level that parks a window or mints a pose is refused at the barrier |

### 10.9 PK4.3 verdict

| question | outcome |
|---|---|
| does the law hold on real data? | **YES, structurally and empirically** — 0 addresses lost on all three live captures, `re_timed = 0` on every u-lane, and the suppression law pinned at the u-lane boundary (attempted ∩ certified = ∅) |
| force-null ≡ the pre-campaign receiver? | **EXACTLY** — 720/720 cert-ID identical, close VERIFIED, and the u-lanes cost **0.0 s** and emit not one event: they do not attempt at all |
| what does scheduling the parked arms buy? | **+16 certified tiles**: hp c3-cmy8 +7 (C 6 / M 1), xerox c2-cmy8 +9 (C 1 / M 2 / Y 6), xerox c3-cmy7 +0 |
| THE M NUMBER (P9's last question) | **M 43 → 44.** The arm applied (`region_gate_forced`, 7/9 strata, 6.5 M conditioned marginals) and converted ONE tile. P9 is answered: M's tail here is not conditioning-limited (§10.6) |
| A3's "waits for the pixel-loop" verdict | **AMENDED** (§7.8): its RESIDUE-side gain is claimable now via u-lanes — +6 on hp, +7 on xerox c2-cmy8, 0 on c3-cmy7. Its ladder-side +62 still waits for the pixel loop, because that number is inseparable from the losses that parked it |
| cost | standard ladder unchanged (−9% / −2% / +2% CPU); the tail adds +15–23% CPU and no RSS. One cmy7 lane is structural dead weight (§10.7) |
| adoption | **NOTHING IS PROPOSED FOR ADOPTION, because nothing needs to be** — that is the law's whole point: a scheduled arm has no adoption question. What is proposed and landed is the plan shape and the policy token |

## 11. PK5 (P2) — the neighbourhood corrector, and which of its two forms survives paper

Colour finally has a context model.  Two arms were BUILT behind one
interface and measured head to head: the user's multi-state **MATRIX**
(`score(s) += Σ_k f_{s,k}(count_k)`, a monotone 9-bin curve per state and
plane, applied to the QDA's own state scores) and the per-plane **PORT**
(K's `detect.fit_context` / `apply_context_offsets` verbatim on the
emitted marginals).  Nothing here is a synthetic verdict: the synthetics
rank the two arms one way and the captures rank them the other, which is
the §4.5.1 lesson arriving for the third time.

### 11.1 The synthetics — and why their ranking is not the answer

`_color_stack_fixtures.build_context_fixture` renders A5's disease with
NO extension to the qualification renderer: `blur_sigma` IS the
print/scan spread, and at 3.0 px against a 6 px cell a cell's aperture
mean carries a measurable fraction of each inked neighbour.  A second
axis — `subtractive_rgb` off the diagonal, so plane C's bleed lands in
the channel plane M is read from — is the pathology only the matrix can
express.  Both are pure fixture parameters; the identity mix renders
bit-for-bit what every earlier fixture rendered (pinned).

| channel (8×8 tiles, noise .01) | kind | matrix gain | port gain |
|---|---|---|---|
| blur 0.5 — CLEAN | cmy7 | REFUSED (18/18 curves fail their own gate) | REFUSED (3/3) |
| blur 0.5 — CLEAN | cmy8 | REFUSED (24/24) | region gate refuses (.0205 → .0205) |
| blur 3.0 | cmy7 | +0.164 | **+0.185** |
| blur 3.0 | cmy8 | +0.084 | **+0.084** |
| blur 3.0, cross-plane mix | cmy7 | +0.167 | **+0.186** |
| blur 3.0, cross-plane mix | cmy8 | +0.053 | **+0.070** |

On FIT LOSS the port wins or ties everywhere — including the channel
built to favour the matrix.  Two mechanisms, both measured rather than
argued: (i) K's offsets are unanchored, so the port's composition sum
carries a per-state LEVEL the zero-anchored matrix is forbidden — but
disabling the anchor as a diagnostic buys back only 1.7–3.9% of the gain,
so the level is not the story; (ii) the matrix is a coordinate ascent and
ONE sweep reaches only 77–81% of three sweeps' gain (six sweeps add
≤0.2%), which is where `CONTEXT_SWEEPS = 3` comes from.

### 11.2 THE HEAD-TO-HEAD AT l00 — the port never applies

Library tier, lane l00 only.  l00 conditions on NOTHING, so unlike every
later lane it is neither replay-optimistic nor a re-timing window — and
it is the 2 ppc lane §4.5.1 says to watch.

| capture | l00 OFF | l00 PORT | l00 MATRIX | matrix Δ |
|---|---|---|---|---|
| hp c3-cmy8 (uplift target) | 179 (C 169 / M 10) | **179 — identical** | **251 (C 238 / M 13)** | **+72 (+40%)** |
| xerox c3-cmy7 | 333 | **333 — identical** | **413** | **+80 (+24%)** |
| xerox c2-cmy8 | 3,596 (C 1109 / M 1319 / Y 1168) | **3,596 — identical** | **4,006** | **+410 (+11%)** |

Every port curve EARNS its own held-out gate and the REGION comparison
then refuses, always on the same leg:

| capture, l00 | arm | total | word | dust | verdict |
|---|---|---|---|---|---|
| hp c3-cmy8 | port | .5275 → .4200 | .5392 → **.3534** | .4688 → **.6734** | `region_gate_failed` |
| hp c3-cmy8 | matrix | .5275 → .5045 | .5392 → .5130 | .4688 → .4554 | `adopted`, 21/24 curves |
| xerox c3-cmy7 | port | .6103 → **.6139** | .5915 → **.4564** | .6178 → **.6769** | `region_gate_failed` |
| xerox c3-cmy7 | matrix | .6103 → .5474 | .5915 → .5288 | .6178 → .5549 | `adopted`, 17/18 |
| xerox c2-cmy8 | port | .3152 → .2515 | .3179 → **.2259** | .3015 → **.3451** | `region_gate_failed` |
| xerox c2-cmy8 | matrix | .3152 → .2840 | .3179 → .2881 | .3015 → .2670 | `adopted`, 24/24 |

**THE MECHANISM, and it is structural.**  The label population is 83–84%
WORD (hp l00 46,021 word / 9,293 dust; c3-cmy7 l00 81,331 / 16,295;
c2-cmy8 l00 176,154 / 35,246).  The port fits ONE curve per plane over
that pooled population, so it learns the BCH word's neighbourhood
statistics — a structured W/CM alphabet — and applies them to every cell:
word improves by .09–.19 nats and dust degrades by .04–.20, which is
exactly what the standing three-way gate exists to refuse.  The matrix
carries a curve per STATE, and word sites and dust sites ARE different
states, so it serves both at once: all three legs improve, the total by
LESS than the port's, and it passes.  The per-plane form is not a weaker
model here — its single degree of freedom per plane is spent by whichever
population is larger, and on this corpus that is always the word.

### 11.3 The full ladder — where the two arms converge, and what that costs

xerox c3-cmy7, full committed-pose replays, `--workers 4 --close`:

| arm | certificates | vs force-null | close | wall | CPU |
|---|---|---|---|---|---|
| force-null | **720** — every lane identical to the archive, u-lanes 0.0 s | — | VERIFIED 301,600 B | 893 s | 1,973 s |
| MATRIX | **771** | +53 / **−2** = +51 | VERIFIED | 962 s | **1,804 s (−8.6%)** |
| PORT | **772** | +55 / **−3** = +52 | VERIFIED | 1,039 s | 1,955 s (−0.9%) |

The two arms finish one certificate apart on the full ladder, and they
get there differently: the matrix takes its gain at l00 (333 → 413) and
the port takes NONE there and +88 at l01 (269 → 357).  Both lose a
handful of tiles the null arm caught at a LATER lane (matrix: l02 and
r01; port: three), and neither set is a strict superset — the arm moves
~50 tiles forward and the cascade's later lanes see a different residue.
Every lane's three legs improve wherever the arm adopts; the two lanes
that refuse (m02, m03) refuse on a dust leg that moves by +.0003 and
+.0007 nats, i.e. the gate is discriminating at the margin, not
rubber-stamping.

### 11.4 THE PORT ON THE UPLIFT TARGET — an exact null, in seventeen lanes

The two arms finishing one certificate apart on xerox c3-cmy7 is not the
head-to-head; it is the cheapest capture agreeing with itself.  The
uplift target settles it.  Full replay, port arm, same flags:

| hp c3-cmy8 | certificates | C | M | lanes where the arm adopted | CPU |
|---|---|---|---|---|---|
| PK4.3 (no context) | 670 | 626 | 44 | — | 8,396 s |
| **PORT** | **670 — cert-for-cert PK4.3** | 626 | 44 | **0 of 17** | 8,648 s (+3%) |
| **MATRIX** | **796** | **740** | **56** | **17 of 17** | 7,949 s (−5.3%) |

The port refuses `region_gate_failed` in every single lane of the
capture the campaign exists to move, and pays 8,648 s of CPU to do it.
That is the §11.2 mechanism at full-ladder scale: on a page whose labels
are 84% word, one curve per plane cannot improve the dust leg, and the
standing gate is not negotiable.

### 11.5 THE UPLIFT TARGET — hp c3-cmy8, and the campaign's largest move

Full committed-pose replay, `--workers 4 --close`, matrix arm:

| | archived | PK4.3 (the standing tree) | **PK5 matrix** |
|---|---|---|---|
| certificates | 663 | 670 | **796** |
| C | 620 | 626 | **740** |
| M | 43 | 44 | **56** |
| Y | 0 | 0 | 0 (dead plane) |
| wall / CPU / peak RSS | — | 3,714 s / 8,396 s / 43.1 GiB | 3,618 s / **7,949 s (−5.3%)** / 42.0 GiB |

Address level vs PK4.3: **127 gained (C 115 / M 12), 1 lost (C, tile
32/12), net +126.**  Bar B3 — `C > 620 AND M > 43` — is MET with the
largest margin the campaign has produced, and **M moves by 12** where
PK10's forced conditioning could move it by exactly 1 (§10.6).  The arm
ADOPTED in all seventeen lanes (14–22 of its 24 curves per lane), and the
l00 gain measured in the library reproduces EXACTLY in the full ladder
(251, +72).  Y stays 0: no context model creates a plane the toner never
printed.

### 11.6 THE FOUR FIDELITY LINES — B1 and B5 hold, B3 is met twice over

Every run below is a full committed-pose replay at the delivered
constants, `--workers 4 --close`, sequential, tree-stable on the §8.5
CONTENT fingerprint (`receiver_tree_sha256` 91b367ef…, `producer_identity`
017f1761…, `arm_identity` 1fc21520… identical at entry and exit; the
`status_sha256` field moved on two runs because this section was being
written, which is precisely the bookkeeping the law says not to test).
One honest footnote: after the last replay the delivered tree moved to
`8b7705f8…` for THREE docstring blocks, one comment block and one
import-line reorder in `color_stack.py` — no executable statement — and
the hp l00 library unit was re-run on the delivered tree to prove it
inert (251 certificates, C 238 / M 13, `lanes_differing_from_dump` empty:
the same number, cert for cert).

| capture / arm | certificates | vs PK4.3 (the standing tree) | close | wrong certs |
|---|---|---|---|---|
| xerox c3-cmy7, **force-null** | **720** | every lane identical to the archive; u-lanes 0.0 s, no `color.context.*` key anywhere | **VERIFIED 301,600 B** | 0 / 8,588,160 |
| xerox c3-cmy7, MATRIX | **771** | +39 / −2 = **+37** | **VERIFIED** | 0 / 9,196,488 |
| *(all three re-run on the extended `u-off` plan — §11.11; c2-cmy8 becomes 5,466 / −2)* | | | | |
| xerox c3-cmy7, PORT (the loser arm) | **772** | +40 / −3 = +37 | **VERIFIED** | 0 / 9,208,416 |
| hp c3-cmy8, PORT (the loser arm) | **670** | cert-for-cert PK4.3; the arm adopted in **0 of 17 lanes** | open | not audited (an exact null of an audited run) |
| **hp c3-cmy8** (uplift target), MATRIX | **796 = C 740 / M 56 / Y 0** | **+127 / −1 = +126** | open (dead Y) | 0 / 3,164,896 |
| xerox c2-cmy8 (B1), MATRIX | **5,465 = C 1801 / M 1867 / Y 1797** | +89 / −3 = **+86** | **VERIFIED 718,413 B byte-exact** | 0 / 21,728,840 |

**Zero wrong certificates across 52.9 M audited cells**, agreement
1.000000000, truth path validated on every run — bar B5 clean.  **Bar B1
holds**: both closes verify against the emitted payload sha AND the
archived `recovered.bin`.  **Bar B3 is met on both components** (C > 620
and M > 43) with the campaign's largest margin.

**AND THE SETS ARE NOT STRICT SUPERSETS.**  Two addresses on xerox
c3-cmy7, one on hp c3-cmy8, three on xerox c2-cmy8 — six tiles in the
whole corpus — certify in the baseline and nowhere in the candidate,
against 255 gained.  This is reported, not rounded away: it is the same
shape PK4's A3 was parked for (+7/−5), at a ratio of 42:1 instead of
1.4:1.  Mechanism, and it is a HYPOTHESIS: every lost tile was certified
by the baseline at a LATER lane (c3-cmy7: l02 and r01) in a cascade whose
earlier lanes now move ~50–130 tiles forward, so the later lanes face a
different residue and a different refinement domain — a re-timing side
effect, not measured evidence damage (every lane where the arm adopted
improved all three of its held-out legs).  The discriminating test — the
same two addresses decoded at the same lane under the same prior frontier
with the arm on and off — is OWED, and the committed-pose cascade cannot
produce it without a seeded-frontier harness.

### 11.7 Cost

| capture | PK4.3 CPU | PK5 matrix CPU | Δ | peak RSS |
|---|---|---|---|---|
| xerox c3-cmy7 | 2,248 s | **1,804 s** | **−19.8%** | 13.3 → 13.3 GiB |
| hp c3-cmy8 | 8,396 s | **7,949 s** | **−5.3%** | 43.1 → 42.0 GiB |
| xerox c2-cmy8 | 4,958 s | **4,608 s** | **−7.1%** | 43.4 → 42.2 GiB |

A5 is CHEAPER than the arm-free ladder on every capture, and B2's ≤+10%
colour budget is not touched.  The arm's own cost is real — one extra
evidence pass per region to build the ink map, plus up to 24 curve fits
capped at 40,000 labels each — and it is repaid several times over by
certificates arriving at coarse lanes, which retires their retry work:
xerox c3-cmy7's l00 spends 415 s where the force-null arm spends 473 s
for 80 fewer tiles.  (The force-null run on the same tree is 1,973 s, so
the matrix is −8.6% against its own null and −19.8% against the PK4.3
row, whose absolute numbers came from a different day's machine load.)

### 11.8 The specimen tier — five moved, all of them adds

`patch_runner compare` against the PK4.3 pin (the policy key moved with
the context token, so the fallback fired loudly and says so: the diff
mixes a policy change with any real regression).  Ten specimens, DIFFS
only per §8.2:

| specimen | pinned | PK5 | Δ | lost |
|---|---|---|---|---|
| l00tax-a / l00tax-c / edge-col0 / clean-cmy8 / frozen-cmy7 | 30 / 35 / 24 / 48 / 0 | identical | 0 | 0 |
| l00tax-b | 19 | 20 | **+1** | 0 |
| a3gain-a | 22 | 28 | **+6** | 0 |
| a3gain-b | 15 | 16 | **+1** | 0 |
| clean-cmy7 | 13 | 16 | **+3** | 0 |
| mtail-hp | 19 | 24 | **+5** | 0 |

**+16 across the corpus, ZERO losses on any specimen, zero wrong
certificates**, and the print-frozen negative control still certifies
nothing.  Five specimens are unmoved because a one-to-two-tile crop is
STARVED for this arm — its floors are K's, counted over a population a
patch does not have — which is also why the tier cannot price A5's
benefit, only detect its damage (§8.2's law, unchanged).

### 11.9 PK5 verdict

| question | outcome |
|---|---|
| which variant ships? | **THE MULTI-STATE MATRIX**, `ctxmatrix-9bin-zeroanchor-sweeps3-floors80-20-40-10`.  The per-plane K PORT is built, measured and NOT adopted |
| why, in one sentence? | the port's single curve per plane is spent on the population that dominates the labels — 83–84% WORD — so it improves word by .09–.19 nats, damages dust by .04–.20, and the standing three-way gate refuses it at every 2 ppc lane on all three captures; the matrix's per-STATE factorization serves word and dust at once and passes |
| is it only a coarse-lane arm? | on the fine-footing-rich cmy7 capture the two arms end one certificate apart (771 vs 772, 770 addresses in common) — the discriminators there are l00 (matrix +80, port 0) and CPU (−8.6% vs −0.9%).  On the uplift target the port is an exact null at l00 where the matrix pays +72 |
| the uplift | **hp c3-cmy8 663 → 796 (C 620 → 740, M 43 → 56)**, the campaign's largest; xerox c2-cmy8 5,370 → 5,465 with the close still byte-exact; xerox c3-cmy7 720 → 771 with the close still byte-exact |
| B5 | **0 wrong certificates / 52.9 M audited cells**, agreement 1.000000000, truth path validated on every run |
| cost | **negative**: −8.6% CPU against its own force-null on c3-cmy7, −5.3% on hp, −7.1% on xerox c2-cmy8, and peak RSS 1–1.4 GiB LOWER.  Certificates arriving at coarse lanes retire more retry work than the arm's own fit costs |
| the blemish | **six addresses across the corpus certify in the baseline and not in the candidate** (2 / 1 / 3) against 255 gained.  Not a strict superset, so under this campaign's own fidelity line the arm does not prove universal non-regression, and the disposition is the lead's (§11.6 names the owed discriminating test) |
| if the answer is SCHEDULE | recorded, with a structural caveat: the supplemental-lane form binds to the FINEST ordinary rung, and A5's yield is concentrated at the COARSEST (l00 gives +72 / +80 / +410 of the totals).  A u-lane A5 would deliver almost none of the measured gain — the u-lanes in these very runs minted 0 / 1 / 5, because the matrix had already taken the residue upstream |

### 11.10 THE LEAD RULING — the supplemental BASELINE lane, and the law it completes

The six stranded addresses are answered by v0.51's own tool pointed the
other way.  **An arm that cannot prove universal non-regression is
SCHEDULED — and so is the CONFIGURATION it replaced.**  A colour plan's
supplemental tail becomes

    [U(Ln, off), U(Ln, a3), U(Ln, a4b)]

whose new FIRST member runs the residue with every campaign arm DISABLED:
the pre-campaign evidence path, scheduled.  `arm_override='off'` is the
force-null ladder made lane-scoped (one flag, one meaning, no second
skeleton to keep in step), and it is ordered before the two arm overrides
so the OLD configuration completes its reachable set before either forced
arm reads what is left.

*Why this is the same law and not a new one.*  A ladder-configuration
change RE-TIMES the cascade: A5 moves 50–130 tiles to an earlier barrier,
so the later barriers face a different residue and a different refinement
domain, and a handful of tiles the old path would have certified are
stranded.  Nothing about that is evidence damage — it is scheduling — and
scheduling damage is repaired by scheduling.  The old path's tail is
monotone under exactly §6.3's per-address retirement law that makes every
u-lane monotone: `_finish` restores the store from the accumulated
frontier, `unresolved_streams` never offers a certified (address, stream),
and the lane can only ADD.  No gate, no floor, no applicability
statistic — the zero-wrong-certificate audit stays the only bar.  This is
the last piece of the union principle: **park, schedule the arm, and
schedule the configuration it displaced.**

Policy token `union-lanes-a3-a4b-off-v2` (decode-relevant for v1's own
reason: a state minted here schedules a lane a v1 state did not).  Pinned
in `test_color_uplift_lanes.py`: plan shape and ORDER, the identity round
trip, K still gains nothing, and — the new one — a u-off region's emitted
evidence is the force-null path's cell for cell on a channel where the
standard ladder is measurably not.

### 11.11 What the baseline lane recovered — one of six, and two mechanisms

Re-ran the three live replays on the extended plan (`u-off` first).  The
lane costs what a residue costs and it is auditable per lane: 118 blocks
in **108 s CPU** on xerox c3-cmy7, 3,041 attempts in **686 s** on hp
c3-cmy8, 300 in **392 s** on xerox c2-cmy8.  On every capture its
diagnostics show the arms ABSENT — no `color.context.*`, no
`color.window_maps.*`, no `color.conditioning.*` key, against the sibling
`u*-a3` lane's `adopted`/`adopted` on the same page — which is the
in-flight proof that `arm_override='off'` really is the pre-campaign
ladder and not an arm with its gate closed.

| capture | certificates | vs PK4.3 | u-off lane | close | wrong certs |
|---|---|---|---|---|---|
| xerox c3-cmy7 | **771** | +39 / −2 | 0 certs, 108 s | VERIFIED | 0 / 9,196,488 |
| hp c3-cmy8 | **796** (C 740 / M 56) | +127 / −1 | 0 certs, 686 s | open (dead Y) | 0 / 3,164,896 |
| xerox c2-cmy8 | **5,466** | +89 / **−2** | **3 certs (1 new)**, 392 s | **VERIFIED 718,413 B** | 0 / 21,732,816 |

**THE PER-ADDRESS ANSWER.**  Each stranded address, with the lane and
FOOTING that certified it in the baseline:

| capture | address | baseline lane (footing) | u-off lane | recovered? |
|---|---|---|---|---|
| xerox c3-cmy7 | (0, 12, 19, main) | `l02` — **6 ppc** | `u03-off` — 12 ppc | no — footing |
| xerox c3-cmy7 | (0, 29, 22, main) | `r01` — **4 ppc** | `u03-off` — 12 ppc | no — footing |
| hp c3-cmy8 | (0, 32, 12, C) | `u04-a3` — 24 ppc | `u04-off` — 24 ppc | no — history |
| xerox c2-cmy8 | (0, 2, 4, C) | `u03-a4b` — 16 ppc | `u03-off` — 16 ppc | **YES** |
| xerox c2-cmy8 | (0, 14, 23, C) | `l03` — 16 ppc | `u03-off` — 16 ppc | no — history |
| xerox c2-cmy8 | (0, 26, 3, C) | `l03` — 16 ppc | `u03-off` — 16 ppc | no — history |

**One of six, and the misses split cleanly into two mechanisms.**

*FOOTING (c3-cmy7, both).*  Those tiles were certified by the baseline at
a COARSER rung — 6 ppc and 4 ppc — than the finest ordinary rung the
supplemental form binds to.  §10.1's "finest rung, because the residue is
the hardest tiles and deserves the best evidence" is right for an ARM and
is precisely the wrong assumption for a CONFIGURATION: the configuration
being restored certified those tiles *somewhere else on the ladder*, and
one lane cannot restore a footing it never runs at.  **Multi-footing
u-off — one baseline lane per rung, or one bound to the rung the address
was lost from — is the named next candidate, deferred by ruling.**

*HISTORY (hp, and two of xerox c2-cmy8).*  These three were certified at
exactly the footing u-off runs at, and it still does not get them.  **A
supplemental baseline lane restores the CONFIGURATION, not the HISTORY.**
By the time u-off runs the KnownField carries 794 / 5,460 certificates
where the baseline's own lane saw ~668 / ~5,100; `build_known_rows` labels
more cells, `_owner_selection` and `_fit_detector` therefore fit a
DIFFERENT pre-campaign model, and the lane decodes the old arm path
conditioned on everything the new ladder has since certified.  That is
not a defect of the ruling — it is the price of the monotonicity that
makes it free (the store is restored from the ACCUMULATED frontier by
construction) — and no schedulable lane can undo it: recovering an
address whose certification depended on a SMALLER prior set would mean
rolling the frontier back, which is the one thing §6.3 forbids.

**So the acceptance is not met as stated** — the three sets are not
strict supersets (−2 / −1 / −2 against +255 gained) — and the honest
summary is that the baseline lane is *sound, cheap, and only partly
sufficient*: it converted the one address whose footing AND prior-set
both matched, it cost minutes, it lost nothing, and it made the corpus
position +250 / −5.  The remaining five are a scheduling artefact of the
ladder change, now diagnosed to two named mechanisms with one candidate
fix (multi-footing) and one impossibility (frontier rollback).

## 12. PK-CLEAN — THE RETIREMENT RECORD

The campaign built more than it kept.  This section is where the parts it
did NOT keep are buried with their cause of death, because a deletion
whose reason lives only in a diff is a fact the project has lost.  Every
row names the item, the measurement that killed it, and where the numbers
and the code still are.  **Nothing measured is lost**: the numbers are in
the sections above, the code is in git history at `9c897e7` and earlier,
and every retired item's MECHANISM sentence is repeated here so a future
packet does not have to re-derive it before deciding not to rebuild it.

The organising principle, stated once: **delete what is measured-dead or
superseded; keep every mechanism the u-lanes use, every law, and every
instrument.**  A3 and A4b are not deleted — they are the two arms the
supplemental-lane law exists for, and they still earn +16 certified tiles
across the corpus (§10.3).  What is deleted is everything built to decide
whether to run them in the STANDARD ladder, because §6.3, §7.4 and §9.11
measured that no such decision procedure exists on this corpus, and §10
replaced the question with scheduling.

### 12.1 The retirement table

| # | retired item | measured reason | evidence | code |
|---|---|---|---|---|
| R1 | `A3_DISPERSION_FLOOR` (0.12, parked) — A3's RAW region applicability floor, the mass-weighted stdev of the fitted per-window gains, max over RGB | **Does not separate.** Raw map spread tracks estimation NOISE at least as strongly as photometric drift: the lane A3 damages carries the corpus MAXIMUM (xerox c3-cmy7 l00, 0.0741) and the lane it helps most one of the lowest (hp c3-cmy8 l01, 0.0601 for +27 addresses). The damaging lane sits INSIDE the helping capture's whole range (0.0511–0.0855), so no floor AND no ceiling works | §6.2, §6.3 | `color_locality` |
| R2 | `A3_NORM_DISPERSION_FLOOR` (0.0, ungated) — the normalized variance-ratio successor, observed between-window gain spread over the spread the fits' own residuals predict, median RGB channel | **Does not separate either, by 15×.** Refusing every lane A3 damages needs a floor above 31.12; keeping every lane it helps on the uplift target needs at most 2.09. Even the ONE cleanly attributable harm lane needs > 3.26 against ≤ 2.09. It fixes PK4.1's within-capture sampling inversion and acquires a LABEL-MASS confound in its place (spearman(norm, labelled population) = +0.73 pooled) | §7.3, §7.4, §7.5 | `color_locality` |
| R3 | the Huber–White standard-error plumbing: `_weighted_affine`'s third return, `WindowMapFit.gain_variance`, `_predicted_variance`, `_normalized_ratio`, `_weighted_variance`, `_weighted_dispersion`, `map_dispersion`, `WindowMapDispersion`, `NORM_DISPERSION_MAX` | Built ONLY to compute R2. With R2 retired nothing reads a gain's sampling variance, and a per-window SE that no statistic consumes is cost with no consumer | §7.1, §7.2 | `color_locality` |
| R4 | the eight `color.window_maps.*` dispersion diagnostics keys (`gain_dispersion`, `offset_dispersion`, `norm_dispersion`, `observed_dispersion`, `predicted_dispersion`, `dispersion_floor`, `norm_dispersion_floor`) and their summary fields | Publications of R1–R3. `prior_labels`, the reason histogram, the accept/refuse/pooled counts and the `cert_*` P6 preview all STAY | §6.5, §7.6 | `color_locality`, `production_color` |
| R5 | `CONDITIONING_PARKED` (A4b's park FLAG) and the generated `parked0` policy fragment | **A flag is still something to flip.** The referendum's verdict stands (exact null on the uplift target, net −5 on the non-regression capture, no statistic separating them) but the arm is not parked — it CONTRIBUTES, from its own lane: +1 M on hp c3-cmy8, +2 certificates on xerox c2-cmy8. `parked0` said "contributes nothing", which stopped being true at PK4.3 | §9.10, §9.11, §10.3, §10.6 | `color_conditioning`, `color_policy` |
| R6 | A4b's un-forced REGION-GATE branch: `fit_conditioned_marginals(force_region_adoption=…)`, the `passed` computation, `CONDITIONING_REASON_REGION_GATE` | Unreachable once the arm is override-only: every caller is a forced lane. The three region legs are STILL measured and published on every fit — the verdict is always `region_gate_forced` and an auditor reads the legs — because §9.4/§9.8 measured that the gate, not the material, is what made the arm unreachable rather than unhelpful (dust-leg refusal at all fourteen conditioned lanes while total and word improved by .015–.023 nats) | §9.4, §9.8, §10.6 | `color_conditioning`, `color_stack` |
| R7 | the per-plane K PORT (`CONTEXT_VARIANT_PLANES`, `_fit_plane_curves`, `_plane_observations`, `_compose_plane_offsets`, `LOCUS_MARGINALS`, `ContextHead.apply_marginals`, the `ctxplanes-3x9-kport` token stem) | **An exact null in seventeen lanes**, on the capture the campaign exists to move: `region_gate_failed` in 17 of 17, cert-for-cert PK4.3's 670, and 8,648 s of CPU (+3%) spent to refuse. **THE MECHANISM, which is the part worth keeping: one curve per plane is spent on the population that DOMINATES the labels — 83–84% word — so it improves the word leg by .09–.19 nats, damages the dust leg by .04–.20, and the standing three-way gate refuses it; the matrix's per-STATE factorization serves word and dust at once and passes.** The `ContextHead` interface and the matrix variant STAY | §11.2, §11.4, §11.9 | `color_context`, `color_fitting` |
| R8 | the three SWEEP ENV HATCHES `HOLO_COLOR_WINDOW_PHOTOMETRY`, `HOLO_COLOR_HEAD_SATURATION_FLOOR`, `HOLO_COLOR_CONTEXT` | Not measured dead — SUPERSEDED. A production module that reads ambient process state depends on something no caller declared; the campaign already had the right pattern in `arm_override` (lane-scoped configuration, threaded explicitly). Replaced by one `color_stack.StackConfig`. `HOLO_COLOR_STACK_FORCE_NULL` STAYS: it is a contract, it can only REMOVE behaviour, and it must reach code paths no configuration object touches | §5.1 (the sweep that needed them), §10.2 | `color_locality`, `color_stack`, `color_context`, harness |
| R9 | the cmy7 `u-a4b` lane (per-coding plan filter) | **A guaranteed zero, measured TWICE before it was filtered.** A4b conditions on certified SIBLING planes and cmy7 is single-stream, so there is nothing to condition on: PK4.3's xerox c3-cmy7 run spent 98 residue blocks / 185 attempts / 70 s wall / 144 s CPU on it for 0 certificates and not one `color.conditioning.*` key (§10.3/§10.7); the PK5-era run, with `u-off` ahead of it taking part of the residue, spent 63 blocks / 118 attempts / 67.1 s wall / 121.9 s CPU for the same 0 (`runs/xerox-c3-cmy7-replay-pk5v2-matrix.json`) | §10.3, §10.7 | `cascade` |
| R10 | dead `validate_certificate_record` import in `color_payload` | Unused since the trust-boundary ruling moved validation to the records layer; `color_payload` was at its 1000-line ceiling carrying it | — | `color_payload` |

### 12.2 What the deletions changed, and what they could not

**The standard ladder's EVIDENCE is unchanged, by construction.** Both
retired arms were already exact nulls on every ordinary, mop-up and
refinement level — A3 refused at its parked floor, A4b short-circuited at
its park flag — so making them unreachable moves no byte.  What it does
move is COST: a standard lane no longer fits window maps it was always
going to discard, which is one QDA pass and one map fit per region
saved.  The three live replays are the proof and they are cert-ID
identical to the PK5-era results (§12.4).

**One thing the deletions could not do is change a certificate**, and the
acceptance was written to fail loudly if it did.  Everything retired was
provably unreachable at the point of deletion; a moved certificate would
have meant the reachability claim was wrong.

### 12.3 The one structural change: OVERRIDE-ONLY reachability

PK4.3 and PK5 scheduled A3 and A4b as supplemental lanes while ALSO
leaving them in the standard ladder behind an applicability floor and a
flag.  That is two answers to one question.  PK-CLEAN keeps the one the
corpus supports: `fit_region_stack` runs A3 **iff** `arm_override == 'a3'`
and A4b **iff** `arm_override == 'a4b'`.  There is no constant, no flag
and no environment variable that could engage either arm from an ordinary
lane — the reachability test IS the override argument — and that is pinned
with a spy on both fitters
(`test_the_standard_ladder_never_calls_either_arms_fitter`), on a fixture
where both arms DO fire under their own overrides, so it cannot pass
vacuously.

### 12.4 Acceptance

Every run below is a full committed-pose replay at the delivered
constants, `--workers 4 --close`, SEQUENTIAL, on one frozen tree —
`receiver_tree_sha256` `2dcec192…`, `producer_identity` `0baab08b…`,
`arm_identity` `934c9216…`, identical at entry and exit on all four
(`tree_stable` is asserted per run in the table).  The last replay
carried the live diagnostics viewer (`--diag --diag-port 8023`).

| bar / check | outcome |
|---|---|
| suite + backbone + collect-only | **PASS** — 1,161 passed / 37 skipped, **1,198 collected** (PK5: 1,207; the 9 net removed pins are listed in §12.6); backbone payload gates 3/3 |
| force-null replay, xerox c3-cmy7 | **PASS** — **720 certificates, cert-ID set IDENTICAL to the archived state** (missing 0, extra 0); wrong certs **0 / 8,588,160 cells** (agreement 1.000000000, truth path validated); re-close **VERIFIED 301,600 B** against BOTH the emitted payload and the archived `recovered.bin`; 916 s wall / 2,015 s CPU / 12,998 MiB. **The per-coding filter is visible here on a real capture: the cmy7 plan schedules TWO u-lanes (`u03-off`, `u03-a3`), not three — and force-null costs both 0.0 s, as it always did** |
| LIVE xerox c3-cmy7 | **PASS — 771, cert-ID set IDENTICAL to PK5's 771** (missing 0, extra 0); every standard lane reproduces its PK5-era count exactly; close **VERIFIED 301,600 B** (payload sha AND archived `recovered.bin`); wrong certs **0 / 9,196,488**; 959 s wall / **1,820 s CPU (PK5: 1,908 s, −4.6%)** / 13,324 MiB |
| LIVE hp c3-cmy8 (the uplift target) | **PASS — 796 = C 740 / M 56, cert-ID set IDENTICAL to PK5's 796**; every standard lane exact; u-lane certificates **0 / 2 / 0**, the PK5 values lane for lane; wrong certs **0 / 3,164,896**; close still open (dead Y); 4,127 s wall / 8,889 s CPU / 41,938 MiB |
| LIVE xerox c2-cmy8 (B1) | **PASS — 5,466 = C 1,802 / M 1,867 / Y 1,797, cert-ID set IDENTICAL to PK5's 5,466**; every standard lane exact; u-lane certificates **3 / 1 / 2**, the PK5 values lane for lane; close **VERIFIED 718,413 B byte-exact** (payload sha AND archived `recovered.bin`); wrong certs **0 / 21,732,816**; 3,308 s wall / 4,946 s CPU / 41,659 MiB |
| zero wrong certificates (B5) | **PASS — 0 across 42.7 M audited cells** on the four replays (8.59 + 9.20 + 3.16 + 21.73 M), agreement 1.000000000, truth path validated on each; and 0 on all ten specimens |
| 10-specimen compare | **PASS — 5 moved, 0 with losses, 0 wrong certificates**, agreement 1.0 and tree-stable on every specimen. The five movers and their sizes are PK5's §11.8 table specimen for specimen (l00tax-b +1, a3gain-a +6, a3gain-b +1, clean-cmy7 +3, mtail-hp +5 = **+16**), i.e. this tier ALSO shows PK-CLEAN moving nothing: the whole diff is PK5's, measured against the same PK4.3 pin. The pin fallback fired loudly on every specimen, as the packet predicted — the policy key moved from `2a350d17bc0b9766` to `a765f290bce6c978`. **Re-pinning is owed at merge** |

**THE HEADLINE, in one line: three live captures, 7,033 certificates, and
not one of them moved.** Everything this packet deleted was provably
unreachable, and the corpus proves it certificate-for-certificate.

Two honest cost notes. (i) The only SAME-EPOCH cost comparison in the set
is xerox c3-cmy7 (its force-null and live runs ran back to back on this
tree): **−4.6% CPU**, which is the standard ladder no longer fitting
window maps it was always going to discard, plus one fewer scheduled
lane. (ii) The two cmy8 captures read **+3.5%** and **−0.8%** CPU against
their PK5-era references, which are CROSS-EPOCH numbers on a shared
machine (the campaign's standing caveat, §7.7) and not a measurement of
this diff; the ladder strictly does less work than it did.

### 12.5 Which runs were reaped, and what that cost

Recorded because the campaign keeps hitting it (§ledger: PK3.1 lost a
4-hour xerox c2-cmy7 run the same way).

| run | fate | wall lost |
|---|---|---|
| harness selfcheck | killed BY ME — the tree was still moving and the §8.5 law would have voided it | ~10 min |
| acceptance chain, attempt 1 | killed BY ME at ~12 min — a source comment edit moved `src/holo` mid-run | ~12 min |
| acceptance chain, attempt 2 | killed BY ME at ~12 min — the final source comment pass | ~12 min |
| acceptance chain, attempt 3 | **REAPED by the harness background-task manager at ~50 min**, mid hp-c3-cmy8 (lane m04). Force-null and the c3-cmy7 live replay had already completed and their artifacts survived on disk; only the hp replay's progress was lost | ~35 min |
| acceptance chain, tail | **survived** — relaunched under `nohup`, disowned, reparented to init; it outlived a later task-manager teardown that killed the polling task around it | — |


### 12.6 Policy identity, the pins, and the collected count

    - …-shrink20-dispfloor0p12-normdisp0-cmy7linf20-…
    + …-shrink20-cmy7linf20-…
    - …-satfloor30-knownfield-conditioned-marginals-parked0-…
    + …-satfloor30-knownfield-conditioned-marginals-ulane-only-…
    - …-union-lanes-a3-a4b-off-v2-…
    + …-union-lanes-a3-a4b-off-v3-codingaware-…
    scheduler:
    - holo/phased-session/rung-major-v3-u-lanes
    + holo/phased-session/rung-major-v4-u-lanes-codingaware

`satfloor30` STAYS: PK3.1's floor is alive and earning, and only the way a
sweep reaches it changed.  Four fragments (`dispfloor`, `normdisp`,
`parked0`, `halo025`) name states the tree no longer has and are pinned as
FORBIDDEN SUBSTRINGS in `test_receive_color_refine`, so they cannot
reappear without someone rebuilding what killed them; the same pin asserts
`A3_DISPERSION_FLOOR`, `A3_NORM_DISPERSION_FLOOR` and
`CONDITIONING_PARKED` no longer exist as attributes.

**The pins.** Collected tests 1,207 -> **1,198** (net −9: 25 removed, 16
added).  Removed, by what they pinned: A3's retired statistics
(`map_dispersion_is_the_mass_weighted_gain_spread`,
`the_normalized_statistic_is_the_ratio_it_claims_to_be`,
`…_takes_the_MEDIAN_channel`, `the_gain_standard_error_tracks_the_fit_s_own_noise`),
its retired floors (`the_dispersion_floor_refuses_a_page_UNIFORM_gain`,
`the_gradient_channel_clears_the_floor_the_uniform_one_misses`,
`the_normalized_statistic_refuses_what_the_raw_one_cannot`), the retired
hatches (`the_sweep_hatch_moves_only_the_three_constants`,
`the_saturation_floor_hatch_moves_and_publishes_itself`,
`the_variant_hatch_parses_and_the_token_states_what_it_read`), A4b's
retired park (`parked_is_the_arm_never_built_path_bit_exact`,
`parked_short_circuits_before_any_population_is_gathered`,
`unparking_is_what_the_fixture_does`,
`forced_region_adoption_overrides_a_failing_gate`), the retired K port
(`the_clamp_kernel_never_runs_for_a_refused_plane`,
`the_per_plane_port_is_detects_own_fit_on_colour_marginals`, and four
`planes`-parametrized cross-pathology cases), and the two u-lane bypass
pins whose bypasses no longer exist.

Added, and the one that matters most:
**`test_the_standard_ladder_never_calls_either_arms_fitter`** — a counter
on BOTH `fit_window_photometry` and `fit_conditioned_marginals`, run on
the fixture where both arms fire under their own overrides, asserting the
standard ladder and `u-off` call neither and each u-lane calls exactly
one.  That is the override-only law made structural: it cannot be
satisfied by a constant set the right way.  Beside it:
`the_standard_ladder_never_fits_a_window_map` (A3's summary off its lane
is the DEFAULT instance, not a refusal record),
`the_standard_ladder_is_the_arm_never_built_path_bit_exact`,
`the_standard_ladder_gathers_no_population_at_all`,
`uplift_a3/a4b_is_the_only_way_the_arm_runs_at_all`,
`a_forced_lane_adopts_over_an_adverse_region_comparison`, the two
`the_module_reads_no_environment_variable` greps (color_locality,
color_context), and the `StackConfig` validation pins.

## 13. PK8/PK9 (P3/P4) — the cmy7 codec leaf, and the campaign's first bar met by a margin

Arm `cmy7-demapiter3`. New code is a soft-output seam in the frozen FEC
leaf (`ldpc/decode.decode_soft`, `ldpc/frame.decode_frame(want_extrinsic=)`),
an a-priori path in the pack7 mapper (`channel.cmy7_soft_demap(prior_bit_llrs)`,
`color_tile.cmy7_demap_payload(prior_code_llrs)`), the loop itself
(`color_tile.cmy7_iterated_decode`) and one pinned constant at the attempt
seam (`color_attempts.DEMAP_ITERATIONS`, read through
`effective_demap_iterations()` so force-null still means the pre-campaign
receiver). P4's seam was built here too and is RETIRED — §13.10.

### 13.1 What the two items are, and where the loop is allowed to live

**P3 (PK8) — BICM-ID.** pack7 maps eleven code bits to four state slots
through natural radix-7 digits: anti-Gray by construction, which is the
favourable case for iterative demapping, because a bit's own channel
evidence is weak while the pack's JOINT evidence given its ten siblings is
strong. The demapper folds a per-bit a-priori LLR vector into all 2,048
candidate metrics, the frame decoder returns its per-variable extrinsic
(posterior minus the clipped channel input) at the transmitted positions,
and the two exchange extrinsics until the CRC certifies or the iteration
budget runs out.

Two properties make the arm exact rather than approximate. The codebook
realizes ALL 2,048 eleven-bit patterns, so a prior with no channel evidence
factorizes exactly and its extrinsic is zero — an unobserved pack stays
silent no matter what the decoder believes, and the support gate that
counts nonzero LLRs cannot be fooled (the residual rounding is zeroed
explicitly, `color_tile.py`). And the demapper SUBTRACTS the prior it was
given, so nothing is double-counted.

The loop is legal exactly because it is confined: RECEIVE-DESIGN §6.2a
permits soft iteration ONLY inside one attempt. It runs inside
`attempt_color_tile`, produces one `TileAttemptRecord`, one attempt
identity, one retry150 spend, and no soft value survives the call
(`FrameDecodeOutcome.extrinsic_llrs` is dropped before the record is
built).

**P4 (PK9) — margin-gated pack erasures.** As BUILT and measured (the
seam is retired, §13.10): per slot, top1 minus top2 over the seven states
in the W-relative convention (state 0's implicit zero included); a slot
below the floor was erased into a COPY of the observation, before
`complete` was derived, so the structural pre-gate, the demapper and the
support floor saw one consistent set. The durable `n_informative` stayed
the PHYSICAL observed count — what the page delivered was never rewritten
by what the decoder chose to ignore — and with the seam gone both are
exactly their pre-PK9 selves again.

### 13.2 B7 — MET at three iterations

Protocol identical to the pinned baseline (`sims.py`, BASE_SEED 20260807,
24 tiles x 20 seeds, all-pass floor 19/20); the candidate arms run the
PRODUCTION functions, not a sim-side copy. The `baseline-repro` arm
(iters 1, floor 0) reproduces `sims-baseline.json` EXACTLY at all sixteen
grid points — seeds-all-pass, tiles-CRC and mean cell error to 1e-15 —
which is the harness fidelity control for this diff.

| p | baseline pass / CRC | iters 2 pass / CRC | iters 3 pass / CRC |
|---|---|---|---|
| 0.0100 | 19/20 · 479/480 | 20/20 · 480/480 (+1) | 20/20 · 480/480 (+1) |
| 0.0150 | 20/20 · 480/480 | 20/20 · 480/480 (+0) | 20/20 · 480/480 (+0) |
| 0.0200 | 0/20 · 375/480 | 20/20 · 480/480 (+105) | 20/20 · 480/480 (+105) |
| 0.0225 | 0/20 · 158/480 | 20/20 · 480/480 (+322) | 20/20 · 480/480 (+322) |
| 0.0250 | 0/20 · 26/480 | 18/20 · 478/480 (+452) | 20/20 · 480/480 (+454) |
| 0.0275 | 0/20 · 2/480 | 7/20 · 462/480 (+460) | 20/20 · 480/480 (+478) |
| 0.0300 | 0/20 · 0/480 | 0/20 · 345/480 (+345) | 17/20 · 477/480 (+477) |
| 0.0350 | 0/20 · 0/480 | 0/20 · 17/480 (+17) | 0/20 · 268/480 (+268) |
| **p\*** | **0.015** | **0.0225** | **0.0275** |

**B7 verdict, against the pinned language ("candidate p\* >= 0.025 under the
identical protocol, and no tested p regresses in tiles-CRC"): MET at
DEMAP_ITERATIONS = 3** — p\* = 0.0275 >= 0.025, and every one of the eight
tested p values is greater than or equal to baseline in tiles-CRC (+1, 0,
+105, +322, +454, +478, +477, +268). **NOT MET at 2** (p\* = 0.0225 < 0.025),
though 2 regresses nowhere either. The bar is met by one grid step, not
marginally: at 0.0275 the arm reads 480/480 against the baseline's 2/480,
and it is 0.030 (17/20, one short of the floor) that stops p\* going higher.

### 13.3 B8 — MET, and P4 is not what meets it

| point | baseline | floor .25 | floor 1.5 | iters 2 | iters 3 | iters 2 + floor .25 | iters 3 + floor .25 |
|---|---|---|---|---|---|---|---|
| p=.01,f=.05 | 0/20 · 401 | 0/20 · **365 (-36)** | 0/20 · **365 (-36)** | **20/20 · 480** | **20/20 · 480** | 20/20 · 480 | 20/20 · 480 |
| p=.01,f=.10 | 0/20 · 0 | 0/20 · 0 | 0/20 · 0 | 0/20 · 0 | 0/20 · **15** | 0/20 · 0 | 0/20 · 5 |
| p=.01,f=.20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p=.01,f=.30 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p=.02,f=.05 | 0/20 · 0 | 0/20 · 0 | 0/20 · 0 | 0/20 · 71 | 0/20 · **293** | 0/20 · 26 | 0/20 · 166 |
| p=.02,f=.10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p=.02,f=.20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| p=.02,f=.30 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| grid CRC total | 401/3840 | 365 | 365 | 551 | **788** | 506 | 651 |

**B8 verdict, against the pinned language (">=19/20 all-pass at (p=0.01,
f=0.05), and no grid point's tiles-CRC below baseline"): MET — by P3
alone, at iters 2 and at iters 3** (20/20 all-pass, 480/480, no point
below baseline). **P4 alone: NOT MET, twice over** — 0/20 at the bar point
and 365/480, thirty-six tiles BELOW baseline, so it fails the all-pass
clause and the no-regression clause independently.

**The joint sweep says the margin gate is never worth its cost.** Adding
floor .25 to iters 3 leaves the bar point unchanged (both already 480/480)
and LOSES elsewhere: 15 -> 5 at (p=.01,f=.10) and 293 -> 166 at
(p=.02,f=.05); grid total 788 -> 651. The two arms interact, and the
interaction is negative: an erased slot is eleven code bits the iteration
can no longer recover, and the iteration is better at re-reading a
low-margin cell than the gate is at deciding to throw it away.

**The declared floor grid has only two distinct arms, and that is a
property of the channel, not of the sweep.** In the honest per-plane BSC
the per-cell margin takes exactly two values: lambda(p) = log((1-p)/p)
when the observed bit pattern has a best state inside the seven-state
alphabet, and exactly 0 when all three planes read inked — CMY is not in
the alphabet, so its three two-plane explanations tie. Measured over the
whole grid: margins {0, lambda} with lambda in [3.317, 4.595], so every
floor in {0.25, 0.5, 1.0, 1.5} erases the identical set and only 0 differs.
Run at both ends (0.25 and 1.5) and confirmed: identical certificates,
identical 75,743 erased slots. The mask is monotone in the floor, so the
two interior points are pinned by the two measured ends rather than
skipped.

### 13.4 Cost — the loop is nearly free where it pays and bounded where it does not

BP iterations over the B7 grid (the honest work unit; the arms ran
different grid subsets so wall/CPU are not comparable across rows):

| p | baseline | iters 2 | iters 3 |
|---|---|---|---|
| 0.0100 | 10,178 | 10,182 (+0.0%) | 10,182 (+0.0%) |
| 0.0150 | 19,788 | 19,788 (+0%) | 19,788 (+0%) |
| 0.0200 | 71,662 | 72,327 (+0.9%) | 72,327 (+0.9%) |
| 0.0225 | 129,716 | 132,526 (+2.2%) | 132,526 (+2.2%) |
| 0.0250 | 163,152 | 171,160 (+4.9%) | 171,174 (+4.9%) |
| 0.0275 | 171,806 | 195,065 (+13.5%) | 195,364 (+13.7%) |
| 0.0300 | 172,796 | 241,520 (+40%) | 244,450 (+41%) |
| 0.0350 | 172,800 | 339,381 (+96%) | 428,656 (+148%) |

The CRC stop makes the cost self-limiting: a tile that certifies on the
first inner decode pays nothing, so in the operating region the arm is
within 1-5% of baseline BP work, and the 2.5x worst case is confined to a
channel where every tile fails anyway. Ceiling is DEMAP_ITERATIONS x the
existing two-pass budget, which is what the runtime attempt-work wall was
widened to (`_runtime_validation`, and only for the cmy7 codec).

### 13.5 Paper — xerox c3-cmy7, and the largest single-arm move on this capture

Committed-pose replays, `--workers 4 --close --diag` (port 8023), one at a
time; the tree was fingerprint-stable across every run
(`tree_state_before == tree_state_after`).

**THE NULL PIN (constants at 1 / 0.0, tree `4e5b9768eac1`).** force-null
xerox c3-cmy7: **720/720, certificate-ID set IDENTICAL to archived**
(missing 0, extra 0); wrong certificates **0 / 8,588,160** cells,
agreement 1.000000000; re-close **VERIFIED 301,600 B**, matching both the
emitted payload sha and the archived `recovered.bin`; 902 s wall /
1,992 s CPU / 13,463 MiB. The whole diff — a soft-output seam inside the
FROZEN FEC leaf, an a-priori path in the mapper, a loop and its constant
— is inert on real paper at its null, which is what makes
`DEMAP_ITERATIONS = 1` a truthful description of the pre-campaign
receiver. This pin covers the DIFF at the null; it does not cover the
SHIPPED tree's force-null behaviour, which is §13.11's job.

**THE CANDIDATE (DEMAP_ITERATIONS = 3).** LIVE xerox c3-cmy7:
**810 certificates against PK5/PK-CLEAN's 771 — +39 gained, ZERO lost,
a strict SUPERSET**; wrong certificates **0 / 9,661,680**, agreement
1.000000000; close **VERIFIED 301,600 B** (payload sha and archived
`recovered.bin`); 1,159 s wall / 2,636 s CPU / 13.5 GiB.

| lane | archived | PK-CLEAN | pk89iter3 |
|---|---|---|---|
| l00-2ppc-400dpi | 333 | 413 | **500** |
| l01-4ppc-800dpi | 269 | 280 | 239 |
| l02-6ppc-1200dpi | 62 | 43 | 27 |
| l03-12ppc-2400dpi | 14 | 19 | 15 |
| m01 / m02 / m03 | 0 / 0 / 1 | 1 / 0 / 3 | 3 / 2 / 0 |
| r00 / r01 / r02 / r03 | 5 / 28 / 6 / 2 | 2 / 1 / 6 / 3 | 4 / 6 / 8 / 6 |
| u03-off / u03-a3 | – | 0 / 0 | 0 / 0 |
| **total** | **720** | **771** | **810** |

The shape is RE-TIMING plus yield: l00 gains 87 at the coarsest rung,
and l01/l02 shed most of what they used to pick up there (280 -> 239,
43 -> 27) because those tiles are already certified. Net is still +39 and
the address set is a superset, so nothing was stranded — the loop reads a
tile at 2 ppc that the single-shot demapper needed 4 or 6 ppc for, and the
capture's hardest residue shrinks with it.

**TAIL CONVERSION.** The capture is 840 tiles. PK-CLEAN left 69
uncertified; pk89iter3 leaves **30**. The arm converts **39 of 69 =
56.5% of the standing tail** — more than the campaign expected of a codec
leaf, and it is the tail that fountain closure was already covering, so
the value is margin, not bytes: the close was VERIFIED before and after.

**COST.** +21% wall (959 -> 1,159 s) and +45% CPU (1,820 -> 2,636 s) at
equal memory. That is the real-capture version of the sim's cost law: the
receiver's payload work is dominated by tiles that FAIL, and a failing
tile now pays up to three inner decodes. The CRC stop keeps a certifying
tile at exactly its old cost.

**hp c3-cmy8 — THE STRICT NO-OP, asserted not assumed.** LIVE hp c3-cmy8
at DEMAP_ITERATIONS = 3: **796 certificates = C 740 / M 56, every lane
identical to PK-CLEAN's, 0 addresses gained and 0 lost, and the
certificate set against archived is the same object** (produced 796,
missing 0, extra 133, identical extra list). Wrong certificates
**0 / 3,164,896**, agreement 1.000000000; close still open on the dead Y
(2 of 3 blocks, >=748 symbols short) exactly as before. 4,442 s wall /
9,234 s CPU / 41.6 GiB against PK-CLEAN's 4,127 / 8,889 / 41.9 —
cross-epoch shared-machine noise on a code path the arm never enters,
which is the point: both seams live inside the CMY7 branch of
`attempt_color_tile`, and CMY8 goes through `cmy8_decode_stream`
untouched.

**xerox c3-cmy7 at TWO iterations — pricing the third.** Same protocol,
`DEMAP_ITERATIONS = 2`: **795 certificates (+24, zero lost, superset)**,
wrong certs 0 / 9,482,760, close VERIFIED 301,600 B, 1,083 s wall /
2,298 s CPU.

| arm | certs | vs PK-CLEAN | uncertified of 840 | wall s | CPU s |
|---|---|---|---|---|---|
| force-null (null constants) | 720 | — | 120 | 902 | 1,992 |
| PK-CLEAN LIVE (iters 1) | 771 | — | 69 | 959 | 1,820 |
| pk89iter2 | **795** | +24 / −0 | 45 | 1,083 | 2,298 |
| pk89iter3 | **810** | **+39 / −0** | **30** | 1,159 | 2,636 |

The third iteration buys 15 more certificates for 338 s of CPU (22.5 s
each) against the second's 24 for 478 s (19.9 s each) — the marginal cost
per certificate is essentially flat, so 3 is not a knee, it is where the
pre-registered bar sits. If the lead ever wants the cheaper arm, 2 is a
real point on the same curve; it just does not meet B7.

**B1 / R5 — xerox c2-cmy8 still CLOSES byte-exact.** The risk register puts
this capture in every packet's set, and it is the second independent CMY8
assertion of the no-op: **5,466 certificates = C 1,802 / M 1,867 / Y 1,797,
every lane identical to PK-CLEAN, 0 gained / 0 lost**, wrong certificates
**0 / 21,732,816**, and the close **VERIFIED 718,413 B** against both the
emitted payload sha and the archived `recovered.bin`. 3,345 s wall /
5,013 s CPU / 41.5 GiB against PK-CLEAN's 3,308 / 4,946 / 41.7 — and this
one ran beside the slow-lane suite, so even its 1.3% is contention, not
arm cost.

The four candidate replays ran on tree `101cade598e4` except this one, on
`ec0b667c451a`; the two differ only in comments (the constants' rationale
block and the policy segment's) — the executable content, including the
bumped token literal, is identical, and every run was fingerprint-stable
end to end.

### 13.6 The specimen tier — every specimen identical, and the re-timing visible inside them

Whole-corpus compare at the adopted constants (the policy bump moved the
key, so the run fell back LOUDLY to pin `a765f290bce6c978`, exactly as
§8.3 intends): **10/10 specimens `identical`, 0 moved, 0 lost, 0 wrong
certificates, agreement 1.000000000, `outside_domain` 0 everywhere.**
The arm is visible INSIDE a specimen without changing its total: l00tax-a
reads l00 24 -> 29 and l01 6 -> 1 for the same thirty certificates. That
is the whole-capture re-timing at patch scale, and it is the honest
reading of the tier — §8.2 says quote patch DIFFS, never patch levels, and
a 6x6-tile crop cannot show a tail conversion that lives in the page's
hardest thirty tiles.

### 13.7 What the n_iters semantics decision is, and the wall it moved

`TileAttemptRecord.n_iters` stays **the BP-iteration sum across ALL inner
decodes of the attempt** (per child, so the record wall's
`sum(child_outcomes) == n_iters` invariant is untouched, and the
CERTIFIED-requires-syndrome-and-CRC law is untouched). The alternative —
reporting only the last inner decode — would make an attempt's cost
accounting lie, and cost accounting is the reason §6.3 stores measured
iterations rather than the profile maximum.

That decision costs one runtime wall. `_runtime_validation.validate_attempts`
priced an attempt at exactly the two decoder passes: `child_iters <=
2 * expected_iters`, AND a failed child had to equal that bound exactly.
Both statements are consequences of the single-pass schedule, not of the
format. They are now `2 * expected_iters * effective_demap_iterations()`
**for the CMY7 codec only**, and the exactness rule survives only at one
iteration — above one, a child can carry a clean syndrome under one prior
and fail under the next, so its total is neither the budget nor a multiple
of it. The wall reads the EFFECTIVE budget, so a force-null run is priced
against the pre-campaign bound it actually executed. K and CMY8 read the
identical bound they always did.

### 13.8 Registered compromise: CRC exposures per attempt

One attempt now invokes CRC-32 up to `DEMAP_ITERATIONS` times instead of
once (only when every child syndrome is clean; the loop stops on the first
CRC pass). The undetected-error budget for one attempt therefore rises by
at most 3x, from ~2^-32 to ~3*2^-32 conditional on a syndrome-clean wrong
codeword. It is not a new KIND of exposure — the attempt identity, the
spend-once law and the retry150 ledger are unchanged, and no extra
certificate can be minted per attempt — but it is a real 3x on the same
denominator, and it belongs beside R6/R12 on the registered-compromises
ledger. Measured against it: **zero wrong certificates in every run of
this packet** — 8,588,160 + 9,482,760 + 9,661,680 + 3,164,896 +
21,732,816 + 8,588,160 = **61,218,472 certified cells** over six replays,
compared against ground truth at agreement 1.000000000, plus 0 across all
ten specimens.

Review addendum (2026-08-10): exposures are BOUNDED, not individually
counted — the durable record keeps only the final pass's `crc_invoked`/
`crc_ok`, so the union bound must be stated as
`decoder_calls x DEMAP_ITERATIONS x 2^-32` for cmy7-coded lanes
(RECEIVE-DESIGN §10.3.5, amended v0.54).  Exact per-attempt exposure
counting is deliberately NOT added (user ruling: narrow); the empirical
guard remains the wrong-certificate audit, and any promotion of the
receiver's qualification status must re-open this.

### 13.9 PK8/PK9 verdict

**PK8 (P3) ADOPTED at `DEMAP_ITERATIONS = 3`**, policy segment
`cmy7-demapiter3`. B7 MET (p\* 0.015 -> 0.0275 >= 0.025, no tested p
regressing); B8 also met by this arm alone. On paper: xerox c3-cmy7
771 -> **810** certificates, strict superset, zero lost, zero wrong, close
still VERIFIED byte-exact, 56.5% of the standing uncertified tail
converted, for +45% payload CPU at equal memory; hp c3-cmy8 a measured
strict no-op.

Every standing fidelity line holds: the force-null pin at the null tree
AND on the shipped tree (720/720 identical, lane for lane), B1 (xerox
c2-cmy8 closes VERIFIED 718,413 B), the B3 capture (hp c3-cmy8 identical
at 796 = C 740 / M 56), and B5 (**zero wrong certificates in 61,218,472
certified cells across six replays and ten specimens**). The v0.51
force-null contract is intact: `--force-null` still means exactly the
pre-campaign receiver, measured on the tree that ships (§13.11).

**PK9 (P4) NOT ADOPTED and RETIRED** (lead ruling, same day) — B8 NOT MET
on both clauses (0/20 all-pass and −36 tiles at the bar point), and
combined with P3 it only subtracts. The seam is deleted; §13.10 is its
retirement record.

### 13.10 PK9 RETIREMENT RECORD (§12 form)

| # | retired item | measured reason | evidence | code |
|---|---|---|---|---|
| R11 | P4's margin-gated pack erasure: `color_attempts.MARGIN_ERASURE_FLOOR`, `margin_erased_observed`, and the attempt-seam call that gated `complete` on a downgraded COPY of the observation | **B8 NOT MET on both clauses, and negative in combination.** At the bar point (p=0.01, f=0.05) it read 0/20 all-pass and 365/480 tiles — **36 BELOW baseline** — and it never helped at any grid point. **THE MECHANISM, which is the part worth keeping: the demapper's pack semantics are ALL-OR-NOTHING, so erasing one low-margin slot costs eleven code bits to avoid one uncertain cell — and P3 makes that trade worse, not better, because an iterated demap can re-read the uncertain cell from its ten siblings while an erased pack is gone. Measured jointly: iters 3 alone 788 tiles over the B8 grid, iters 3 + floor 0.25 only 651.** The arm becomes interesting again only if the mapper ever gains PARTIAL-pack semantics | §13.3 | `color_attempts` |

**Kept:** `channel.state_score_margins` — a clean primitive (top1 minus
top2 over the seven states, implicit W included), independently tested,
and the thing the degeneracy proof below rests on. **Kept in the
HARNESS:** `sims.py --erasure-floor` still runs the arm, three lines over
that primitive, so the retired sweep stays reproducible without keeping a
seam in production; re-running it reproduces §13.3 exactly (floor 0.25 and
floor 1.5 both 17/24 CRC and 369 erased slots on the first bar-point
batch, against floor 0's 18/24).

`n_informative` and the structural pre-gate revert to exactly their
pre-PK9 form: the physical observed count, and `complete` derived from the
caller's own observation with no copy in between.

### 13.11 The force-null invariant, restored and re-measured

v0.51 states that `--force-null` is EXACTLY the pre-campaign receiver.
A codec-leaf constant breaks that silently — the ladder would be nulled
while the leaf kept iterating — and the campaign's standing 720/720 guard
would have drifted without anything failing. `attempt_color_tile` now
takes its budget from `color_attempts.effective_demap_iterations()`, which
returns 1 when `color_stack.force_null_enabled()` is true. It asks
`color_stack` rather than the environment: PK-CLEAN's rule is ONE
sanctioned reader for the one surviving contract, and a second
`os.environ` call in a codec leaf would be the hatch that rule exists to
prevent. Like everything else force-null does, it can only REMOVE
behaviour.

Pinned twice. The unit pin counts DEMAPS on a tile built to fail its first
decode (`test_force_null_never_enters_the_iterated_path`): live it demaps
more than once, under force-null exactly once, and the durable record
falls back to the single-pass BP budget and validates against the
pre-campaign wall. The decisive pin is on paper, on the SHIPPED tree
(`DEMAP_ITERATIONS = 3`, not the null tree the earlier §13.5 pin used):

**force-null xerox c3-cmy7, shipped tree `4c3cd668d8ef`
(`DEMAP_ITERATIONS = 3`, policy id carrying `cmy7-demapiter3`): 720/720,
certificate-ID set IDENTICAL to archived (missing 0, extra 0), and
IDENTICAL LANE FOR LANE to the null-tree pin of §13.5 across all fourteen
lanes; wrong certificates 0 / 8,588,160, agreement 1.000000000; re-close
VERIFIED 301,600 B against both the emitted payload sha and the archived
`recovered.bin`; 937 s wall / 2,050 s CPU / 12.9 GiB against the null
tree's 902 / 1,992 / 13.2 — a 2.9% CPU difference on an execution path the
contract makes identical, i.e. epoch noise, and the honest read is the
certificate identity, not the seconds.**

## 14. PK-FINAL — THE QUALIFICATION MATRIX

The campaign's last measurement, and the only one that qualifies anything:
**eight candidate-final FULL decodes, one per corpus capture.**  Everything
before this section is replay, feature-library or sim tier.  A full decode
re-runs SURVEY, ADDRESS, payload, mop-up, refine and the supplemental tail
from raw pixels into a fresh state; a replay re-runs the payload side over
the archived run's committed geometry.  COLOR-UPLIFT-PLAN §4: *full decodes
only*.

### 14.1 Method, and what was held fixed

Arm `pkfinal`, tree `4577652` — receiver content hash `3838cccf30a6`,
producer `0baab08bc6a2`, arm `934c9216904a` — policy id
`…-winphot-gainoffset-adaptivehalo-shrink20-…-satfloor30-knownfield-conditioned-marginals-ulane-only-ctxmatrix-9bin-zeroanchor-sweeps3-floors80-20-40-10-union-lanes-a3-a4b-off-v3-codingaware-…-cmy7-demapiter3-preclose-selective-retry150`.

- `ab_runner full --capture … --arm pkfinal --diag --diag-port 8023`, one
  fresh state directory per capture under `<work>/full/<capture>-pkfinal/`;
  flags taken from `provenance.json` by the runner itself, **including the
  per-capture `--complete`** (deferred close on xerox c3-cmy7 / c2-cmy8 /
  c2-cmy7 / both K; per-barrier close preemption on hp c3-cmy8 / c2-cmy8).
- **Workers 8 via `HOLO_RECEIVE_WORKERS=8`.**  `full` mode has no
  `--workers` flag — it goes through `run_receive`, which reads the
  environment fallback of the same `_parallel` seam `confetti.py decode
  --workers` uses; the effective count is recorded in each run JSON
  (`environment.workers` = 8).  Execution-only, bit-identical at any count.
- `provenance verify --capture …` immediately before every run (all eight
  OK), and a §8.5 CONTENT fingerprint at entry AND exit of every run.
- Every run **detached under `nohup` and polled** (§12.5's rule).  It earned
  its keep again: a polling task was reaped mid-matrix and the decode under
  it never noticed.
- **Scheduling.** Sequential, one big at a time.  The packet's premise that
  the two K rows are "medium (~8–13 GiB)" is **WRONG for a full decode** —
  that figure is a replay peak.  Measured here, a 4800 dpi K sheet peaks at
  **40.3 GiB** (xerox) and **41.1 GiB** (hp), the same class as the colour
  bigs.  Only the 2400 dpi canary is genuinely medium (12.8 GiB).  The
  canary and xerox c2-K were run as a pair before that was known — 53 GiB
  combined worst case on a 64 GiB machine, inside the envelope but by less
  margin than intended, and recorded as a risk taken (§14.9).  Everything
  after ran strictly alone.
- **Elapsed:** 2026-08-09 22:36:32 → 2026-08-10 09:53:47, **11 h 17 min of
  clock** for 11 h 32 min of run wall (the one overlapping pair) and
  **86,272 s of process CPU**.  One overnight, not the two budgeted.
- **One tree event.** During the hp c3-cmy8 run, HEAD moved
  `4577652` → `b9ef24d` (the lead's docs-only plan-header commit, 9 lines in
  `docs/COLOR-UPLIFT-PLAN.md`, zero bytes of `src/`).  All three §8.5 content
  identities were byte-identical at entry and exit, so the run stands.  This
  is exactly the second incident type §8.5 was written for — *a git-shaped
  fingerprint gets this case wrong; the content hash gets it right* — and it
  is the first time the law has been exercised by another worker's commit
  rather than by the run's own author.

### 14.2 The eight rows

Certificates = decoded LDPC payloads = the campaign's yield unit (user ruling
2026-08-08).  `tiles` is the distinct-address count, which differs only where
a coding has three streams.  Wrong certificates are audited by
`gt_score run` through the production projection leaf on **every** certificate
of **every** row; truth path validated first on the seven rows that produced
certificates (row 8 produced none, so its truth flag is vacuous — the harness
predicate now reports vacuity explicitly; review disposition 2026-08-10).

| # | capture | certificates (by stream) | tiles | vs archived | close | wrong / audited | wall s | CPU s | peak RSS |
|---|---|---|---|---|---|---|---|---|---|
| 1 | xerox c3-cmy7 (2400 dpi) | **810** (main 810) | 810/840 | 720 → 810, **+91 / −1** | **VERIFIED 301,600 B**, sha == emitted payload AND archived `recovered.bin` | **0** / 9,661,680 | 2,073 | 4,775 | 12.8 GiB |
| 2 | hp c3-cmy8 | **796** (**C 740 / M 56** / Y 0) | 746/840 | 663 → 796, **+133 / −0, STRICT SUPERSET** | open — 2 of 3 blocks, ≥748 symbols short, streams (M, Y) | **0** / 3,164,896 | 6,433 | 14,481 | 41.6 GiB |
| 3 | xerox c2-cmy8 | **5,466** (C 1,802 / M 1,867 / Y 1,797) | 1,871/1,872 | 5,370 → 5,466, **+98 / −2** | **VERIFIED 718,413 B**, sha == emitted payload AND archived `recovered.bin` | **0** / 21,732,816 | 4,180 | 6,670 | 41.9 GiB |
| 4 | xerox c2-K | **1,930** (main) | 1,930/1,961 | 1,930 → 1,930, **certificate-ID set IDENTICAL** | **VERIFIED 465,580 B**, sha == emitted payload AND archived `recovered.bin` | **0** / 7,905,280 | 1,932 | 2,390 | 40.3 GiB |
| 5 | hp c2-K | **1,940** (main) | 1,940/1,961 | 1,940 → 1,940, **certificate-ID set IDENTICAL** | **VERIFIED 465,580 B**, sha == emitted payload AND archived `recovered.bin` | **0** / 7,946,240 | 2,376 | 9,118 | 41.1 GiB |
| 6 | xerox c2-cmy7 | **1,559** (main) | 1,559/1,872 | 83 → **1,559**, **+1,476 / −0, STRICT SUPERSET** | **VERIFIED 686,859 B**, sha == emitted payload (**no archived `recovered.bin` exists — this volume had never been recovered**) | **0** / 18,595,752 | 8,962 | 23,423 | 41.7 GiB |
| 7 | hp c2-cmy8 (B6 control) | **15** (C 15) | 15/1,872 | 0 → 15, **+15 / −0** | open — metadata coefficient rank **0 → 14** of 24 | **0** / 59,640 — **all fifteen adjudicated CORRECT** | 10,340 | 17,430 | 42.2 GiB |
| 8 | hp c2-cmy7 (B6 control) | **0** | 0 | 0 → 0 | open — no certificates | no certificates to audit (0 cells) | 5,235 | 7,986 | 41.6 GiB |
| | **total** | **12,516** (archived 10,706) | | **+1,813 / −3** | 5 verified closes, one of them new | **0 / 69,066,304** | **41,532** | **86,272** | ≤42.2 GiB |

Per-lane tables, the archived-vs-candidate address ledgers, the
archived-vs-candidate stage-CPU splits and the address-level gain/loss sets
are in `runs/{lanes,address,stagetime,setdiff}-pkfinal-<capture>.json`.

### 14.3 THE RESULT THE REPLAYS COULD NOT PREDICT — xerox c2-cmy7 CLOSES

`xerox-c2-cmy7` entered this campaign as the **print-frozen negative
control**: 83 certificates of 1,872 tiles (4.4%), "print-frozen 18% cell
error, 3× pack7 threshold, 4.3× lane-correlated", carried under bar B4 as
**report-only, no close expected**, and recorded in
`experiments/032-…` as one of the two volumes that **FAILED on BOTH
engines**.  e032 diagnosed the AltaLink copy precisely: addressing healthy
(99.8% footprint, 1,489 word matches) and **1,789 LDPC failures** — a
cell-level failure, not a geometry one.

The candidate-final full decode returns **1,559 certificates — 83.3% of the
page, a strict superset of the archived 83 — and the fountain CLOSES
VERIFIED at 686,859 bytes with the sha of the emitted payload.**

**This is a volume recovered from paper for the first time.**  Every other
close in this matrix reproduces a close that already existed; this one does
not.  It is also the cleanest possible statement of what the campaign built,
because e032's own diagnosis named the failing layer and the campaign's arms
are exactly that layer: the evidence stack (P1's cmy7 head, P2's multi-state
context matrix) and the codec leaf (P3's iterated pack7 demap).  The
addressing ledger is **identical to the archived run to the digit** (7,818
words, 7,139 certified, 32 unresolved, 1,120,290,105 hypotheses), so nothing
about the geometry changed — only what the receiver could read out of the
cells.

Lane shape, archived → candidate: l00 **2 → 751**, l01 **0 → 587**,
l02 4 → 57, l03 48 → 99, mop-up 0 → 8, refine 29 → 42, and the supplemental
`u03-a3` lane adds a further **15**.  Cost: standard-lane CPU
**7,494 s against the archived 9,550 s (−21.5%)** — the arms are cheaper
here than the arm-free ladder despite three demap iterations, because a tile
that certifies at 2 ppc never pays for the retry ladder above it.  The u-lane
tail adds 1,320 s.

Two honest qualifications.  **(a)** B4 declared this row report-only, so the
close is not a bar being met — it is a bar being overtaken, and the plan's
own language ("stays unrecoverable — measured") is now **falsified by
measurement**, which is the right way for it to die.  **(b)** One sheet, one
capture: this is existence evidence for the coding on this engine, not a
promotion of `c2-cmy7` to a usable rung.  e032's ordering-inversion finding
(the discovery sheet ranked cmy7-c2 ABOVE cmy8-c2, and the payload outcome
inverted it) is **not** overturned — both codings now recover on the
AltaLink, and the discovery ladder still failed to predict either.

### 14.4 What else the full decodes changed against the replay tier

**(a) The addressing path is provably untouched — the strongest form of B6.**
`address.final` is emitted by the address stage itself, once per lane, in
both epochs.  Read the archived ledger and the candidate ledger the same way
and they agree **to the digit** on every ordinary and mop-up lane of every
comparable capture:

| capture | words (arch / cand) | certified | unresolved | hypotheses identical |
|---|---|---|---|---|
| xerox c3-cmy7 | 3,529 / 3,529 | 3,317 / 3,317 | 18 / 18 | yes |
| hp c3-cmy8 | 5,181 / 5,181 | 2,253 / 2,253 | 379 / 379 | yes |
| xerox c2-cmy8 | 7,978 / 7,978 | 6,712 / 6,712 | 56 / 56 | yes |
| xerox c2-K | 8,519 / 8,519 | 7,117 / 7,117 | 82 / 82 | yes |
| xerox c2-cmy7 | 7,818 / 7,818 | 7,139 / 7,139 | 32 / 32 | yes |
| **hp c2-cmy8** (B6) | **3,796 / 3,796** | **86 / 86** | **5,139 / 5,139** | **yes** |
| **hp c2-cmy7** (B6) | **4,840 / 4,840** | **421 / 421** | **2,713 / 2,713** | **yes** |

(hp c2-K is excluded by construction: its archived state is
**multi-invocation** and only the last invocation's events survive, so its
archived ledger covers mop-up + refine alone.)  The only column that moves
is REFINE pose count, which is a payload-driven quantity: refine re-poses the
windows the ladder has not finished with, and a different certified frontier
leaves a different refine domain.  Seven of seven comparable captures,
including **both** B6 controls, are identical to the digit — on the controls
right down to the mop-up cold-search hypothesis counts
(45,914,336,898 / 28,830,049,888 / …).

**(b) The named-losses ledger shrinks from five to three.**  §11.11 named six
addresses the ladder change stranded, one of which `u-off` recovered.  Under
full decodes only **three** are lost:

| capture | address | §11.11 mechanism | full decode |
|---|---|---|---|
| xerox c3-cmy7 | (0, 12, 19, main) | FOOTING (baseline certified at l02, 6 ppc) | still lost |
| xerox c3-cmy7 | (0, 29, 22, main) | FOOTING (baseline r01, 4 ppc) | **RECOVERED** |
| hp c3-cmy8 | (0, 32, 12, C) | HISTORY | **RECOVERED** — hp is now a strict superset |
| xerox c2-cmy8 | (0, 14, 23, C) | HISTORY | still lost |
| xerox c2-cmy8 | (0, 26, 3, C) | HISTORY | still lost |

Both recoveries are real and both are explained by the same thing: a full
decode re-runs its own refine placement, so the refine domain and the pose
each stranded window gets are the *candidate's*, not the archived run's
replayed geometry.  The replay tier had to reuse archived poses and therefore
over-counted the stranding by two.  **Corpus position at the qualification
tier: +1,813 gained / −3 lost** (the two B6 controls contribute 15 of the
gains and none of the losses).

**(c) The K rows calibrate the cross-epoch CPU instrument, and it is ±15%.**
Both K decodes are **certificate-ID identical** to their archived states on a
code path the campaign never touches (`k-v1`; the colour stack is not
reachable).  Their full-decode CPU against archived `timing.processor_seconds`:

| capture | archived | candidate | delta | output |
|---|---|---|---|---|
| xerox c2-K | 1,630.9 s | 1,881.8 s | **+15.4%** | certificate-ID identical, address ledger identical |
| hp c2-K (mop-up + refine, the only comparable subset) | 2,022.3 s | 1,799.7 s | **−11.0%** | certificate-ID identical |

Same code, same bytes out, **−11% to +15% apart**.  That is the noise floor
of "full-decode CPU vs archived events", and every colour number below has to
be read against it.  (xerox c2-K additionally shared the machine with the
canary for the first 20 of its 32 minutes; hp c2-K ran alone.)

### 14.5 Cost, split honestly (bar B2's evidence)

`timing.processor_seconds` from the runtime's own `stage.complete` events,
same classifier applied to both epochs.  **Standard lanes** = the 12/15-lane
ladder the archived run also ran; **u-lanes** = the supplemental tail, which
the archived plan never scheduled and which is NEW SCHEDULED WORK, priced
separately per the lead's PK4.3 ruling (§10.7).

| capture | archived total | candidate standard lanes | Δ standard | candidate u-lanes | candidate total | Δ total |
|---|---|---|---|---|---|---|
| xerox c3-cmy7 | 1,587.6 s | 1,885.2 s | **+18.7%** | 147.0 s | 2,032.2 s | +28.0% |
| hp c3-cmy8 | 5,889.8 s | 5,044.7 s | **−14.3%** | 1,198.0 s | 6,242.7 s | +6.0% |
| xerox c2-cmy8 | 2,819.0 s | 3,082.4 s | **+9.3%** | 874.5 s | 3,956.9 s | +40.4% |
| xerox c2-cmy7 | 9,549.8 s | 7,493.5 s | **−21.5%** | 1,320.4 s | 8,813.9 s | −7.7% |
| hp c2-cmy8 (B6) | 13,719.7 s | 9,653.7 s | **−29.6%** | 465.6 s | 10,119.3 s | −26.2% |
| hp c2-cmy7 (B6) | 6,103.5 s | 5,092.1 s | **−16.6%** | 0.0 s | 5,092.1 s | −16.6% |
| xerox c2-K | 1,630.9 s | 1,881.8 s | +15.4% | — | 1,881.8 s | +15.4% |
| hp c2-K (comparable subset) | 2,022.3 s | 1,799.7 s | −11.0% | — | 1,799.7 s | −11.0% |

Read against the K rows' ±15% instrument noise: three rows are cheaper by
more than the noise (−21.5%, −29.6%, −16.6%), two sit inside it (−14.3%,
+9.3%), and one is **above** it — xerox c3-cmy7's **+18.7%**, which is the
demap-iteration cost B7 purchased showing up inside the ordinary lanes (the
same cost the replay-primary metric reads as +28.6%, §13.5/§13.11).  The
standard ladder elsewhere is unchanged or better; the canary's own row is
not, and B2's adjudication in §14.6 records that honestly.
The two B6 controls are the cleanest reading of all, because their arms
cannot fire: hp c2-cmy7 builds zero payload blocks anywhere, and its −16.6%
is pure epoch, which is the same statement the K rows make.  The one
unambiguous new cost is the supplemental tail: **0% to +31% of the archived
ladder**, and it is the tail that buys **24 certificates** (c3-cmy7 0,
hp c3-cmy8 2, xerox c2-cmy8 6, xerox c2-cmy7 15, hp c2-cmy8 1, hp c2-cmy7 0)
and, on hp c3-cmy8, part of the strict-superset property.  On hp c2-cmy7 the tail
costs **0.0 s and emits nothing** — a coding-aware plan with no residue to
work on, which is the u-lane law behaving as §10 says it must.

Peak RSS is unmoved by the arms and set by the finest rung, as §7.7 found:
40.3–42.1 GiB for every 4800 dpi capture regardless of coding or engine,
12.8 GiB for the 2400 dpi canary.

### 14.6 THE ADJUDICATION — bars B1 through B8

Bar language is quoted VERBATIM from COLOR-UPLIFT-PLAN §4.  **Summary: B1, B3,
B5, B6, B7, B8 MET.  B2 FAILED AS WRITTEN on the cmy7 canary** — +28.6% live
vs same-tree force-null against the +10% primary clause, the demap-iteration
cost B7 purchased; every other capture is inside the bar.  The lead's
"priced separately" reading in the first committed version of this section
was a post-result reclassification (the PK4.3 ruling it extended covered
scheduled u-lanes only, and predates PK8's measurement, which its own
rationale would have priced INSIDE B2); the external review
(COLOR-UPLIFT-REVIEW.md) called this correctly.  Recorded honestly: **B2
failed as written; a post-result amendment pricing B7-purchased decoder
iterations separately was proposed by the lead and RATIFIED by the user's
adoption ruling of 2026-08-10.**  B4 is report-only and the report is that
the control closed.  B5 — the campaign-stopping one — was never in danger.

| bar | verbatim language | measured | verdict | evidence |
|---|---|---|---|---|
| **B1** | "closes: xerox c2-cmy8 / c3-cmy7 / 2×K still close byte-exact." | xerox c2-cmy8 **VERIFIED 718,413 B**; xerox c3-cmy7 **VERIFIED 301,600 B**; xerox c2-K **VERIFIED 465,580 B**; hp c2-K **VERIFIED 465,580 B** — all four sha-matched against the emitted payload AND the archived `recovered.bin` | **MET** (4/4) | §14.2 rows 1/3/4/5 |
| **B2** | "cost (v1.1): **primary = replay-path CPU vs fresh same-epoch baseline replays** (color ≤ +10%, K ≤ +5%); full-decode CPU vs archived events is reported with machine-load context and acknowledged cross-epoch noisy." | see §14.6a below | **FAILED as written** — cmy7 canary +28.6% > +10% on the primary metric (demap cost is inseparable from it: force-null pins iterations to 1); all other captures inside the bar. **Waiver ratified by user adoption ruling 2026-08-10** (demap cost reclassified post-result as B7-purchased decoder work). K clause: secondary instrument measurably unfit (±15% ruler); treated as met on certificate-ID-identical output | §11.7, §10.7, §13.5, §13.11, §14.5 |
| **B3** | "uplift: hp c3-cmy8 **C > 620 AND M > 43** (bar); Y ≥ 1 = bonus not bar; close = stretch." | **C 740 > 620 ✓ AND M 56 > 43 ✓**, from THIS full decode; Y 0 (bonus not earned — toner epoch); close not reached (stretch not earned) | **MET, both components** | §14.2 row 2 |
| — | B3 adoption guidance (v1.1, "not a kill criterion"): "M ≥ 2× baseline (≥86) **or** a stage earns adoption by cost (≤ +5% CPU at any cert gain)" | M 56 < 86 — first clause NOT satisfied. Standard-lane CPU on hp c3-cmy8 is **−14.3%** at **+133 certificates** — second clause satisfied with margin | **guidance satisfied by the cost clause, not the M clause** | §14.5 |
| **B4** | "negative control: xerox c2-cmy7 report-only." | 83 → **1,559 certificates**, strict superset, **close VERIFIED 686,859 B** | **REPORT-ONLY — and the report is that the control closed.** The plan's "stays unrecoverable (measured)" expectation is falsified | §14.3 |
| **B5** | "**hard bar**: zero wrong certificates — every capture, arm, mode; one wrong cert stops the campaign." | **0 wrong certificates in 69,066,304 audited certified cells** across all eight qualification decodes, agreement 1.000000000, truth path validated on every one. Campaign cumulative: 0 in every packet's audit (PK8 61.2 M cells / 6 replays + 10 specimens; PK5 52.9 M; PK4.3 41.4 M; PK10, PK4.x, PK3, PK0 all 0) — **no wrong certificate has ever been produced by this campaign, in any tier** | **MET, no campaign stop** | §14.2, §13.8, §11.6, §10.8 |
| **B6** | "no-op/scope-leak control hinges on ADDRESSING STATS ONLY (footprint ±1pt, word-match counts) on hp c2-cmy7 AND hp c2-cmy8 — P0–PK10 never touch addressing. Certs appearing on hp c2-cmy8 are NOT a leak signal; B5's GT check adjudicates them and they are reported." | **hp c2-cmy7: the address ledger is IDENTICAL to archived line for line and total for total** (4,840 words, 421 certified, 808 placements, 2,713 unresolved, hypotheses to the digit), **0 certificates, 0 payload blocks built anywhere**, u-lanes 0.0 s. **hp c2-cmy8: the address ledger is IDENTICAL to archived to the digit** (3,796 words, 86 certified, 721 placements on the addressing lanes, 5,139 unresolved) — the only delta is 17 refine re-poses, which exist because there is now a certified frontier to refine around. Footprint follows the accepted-placement set and that set is unchanged, so **60.3% and 45.1% stand, delta 0.0 pt** (0 ≤ 1 pt). **15 certificates appeared on hp c2-cmy8 where archived had 0; per B6 v1.1 they are adjudicated by B5's GT check and REPORTED: all fifteen are CORRECT** (0 wrong / 59,640 cells, agreement 1.0) | **MET** — zero addressing-path movement on both controls | §14.4a, §14.2 rows 7/8 |
| **B7** | "(P3 sim) … **PINNED at p\* ≥ 0.025**; ADJUDICATED 2026-08-09: MET at three demap iterations (0.0275), NOT met at two (0.0225)." | p\* 0.015 → **0.0275** at `DEMAP_ITERATIONS = 3`; no tested p regressing in tiles-CRC (+1, 0, +105, +322, +454, +478, +477, +268) | **MET** (adjudicated §13.2; re-affirmed on paper by §14.3) | §13.2 |
| **B8** | "(P4 sim) … **PINNED at ≥19/20 all-pass at (p=0.01,f=0.05) with no grid point below baseline**; ADJUDICATED 2026-08-09: MET — but by P3, not by P4." | 20/20 all-pass, 480/480 at the bar point, no grid point below baseline — **by P3 alone**. P4 fails both clauses (0/20, −36 tiles) and is RETIRED | **MET by P3; P4 NOT MET and adopts nothing** | §13.3, §13.10 |

#### 14.6a B2 in full, because it is the one bar with two instruments

*Primary (the bar's own metric — replay CPU vs a same-epoch, same-tree
force-null replay).*  Measured per packet and unchanged by this matrix:
PK5's context matrix **−8.6% / −5.3% / −7.1%** (c3-cmy7 / hp c3-cmy8 /
xerox c2-cmy8, §11.7), PK-CLEAN **−9.7%** on c3-cmy7 (§12), PK4.3's standard
ladder **−9% / −2% / +2%** (§10.7).  Every one is inside "colour ≤ +10%", and
most are negative: the arms pay for themselves by retiring retry work.  The
single exception is PK8's codec leaf on the cmy7 capture — **+28.6% CPU**
(2,636 s live vs 2,050 s force-null, §13.11) — and on this number **B2 fails
as written**: force-null pins demap iterations to 1, so the primary metric
structurally contains the demap cost, and the bar text excludes nothing.
The PK4.3 "priced separately" ruling does not rescue it — that ruling
covered NEW SCHEDULED work (u-lanes force-null never attempts) and its own
rationale said B2 binds evidence-stack changes; a demap loop inside an
ordinary attempt is decoder work the bar was pointed at.  The cost split
below is therefore ATTRIBUTION, not adjudication — the demap row sits
outside B2 only by the post-result amendment the user ratified with the
2026-08-10 adoption ruling:

| cost class | what it is | measured | inside B2? |
|---|---|---|---|
| standard evidence stack (A3/A4/A4b/A5 ladder) | what B2 was written for | −9.7% … +2% replay-primary; −21.5% … +18.7% full-decode against a ±15% instrument | **YES** |
| u-lane supplemental tail (PK4.3) | new SCHEDULED work; force-null does not attempt it at all (0.0 s) | +15–23% replay (§10.7); **0% … +31%** of the archived ladder in full decodes | not a B2 quantity — priced, reported, yield-bearing (**24 u-lane certificates** across this matrix) |
| demap iterations (PK8) | new DECODING work inside one attempt, CRC-stopped | +28.6% on the cmy7 canary; a measured strict no-op on both cmy8 captures | **inside B2 as written (bar FAILS here)**; outside it only by the ratified post-result amendment — it is the arm B7 bought, and §14.3 is what it bought |

*Secondary (full-decode CPU vs archived events).*  Reported in §14.5 with the
K calibration.  **B2's K clause (≤ +5%) cannot be adjudicated by this
instrument**: the two K decodes are certificate-ID identical to their archived
states on a decode path whose only branch change is output-bit-identical and
measured at ≤0.1% CPU (one n-length extrinsic subtraction per decode,
benchmarked base-vs-branch at 0.86 µs against 1.06–57 ms/decode; review
verification 2026-08-10 — the earlier "code the campaign never touches"
wording here was wrong), and they read **+15.4%** and **−11.0%**.  A bar of ±5% measured with a ±15% ruler says nothing about the
receiver.  Recommendation for the ruling: **treat the K clause as MET on the
evidence that matters** — bit-identical output on an untouched path, on two
engines, at full-decode tier — and record the instrument as unfit rather than
the receiver as slow.

### 14.7 Campaign yield — pre-campaign to final

Yield = certified tiles = decoded LDPC payloads (user ruling 2026-08-08).
Archived column = the frozen `provenance.json` baselines (§1).

| capture | pre-campaign | final (full decode) | Δ | gained / lost |
|---|---|---|---|---|
| xerox c3-cmy7 | 720 | **810** | **+90** | +91 / −1 |
| hp c3-cmy8 | 663 (C 620 / M 43 / Y 0) | **796** (C 740 / M 56 / Y 0) | **+133** | +133 / −0 |
| xerox c2-cmy8 | 5,370 | **5,466** | **+96** | +98 / −2 |
| xerox c2-K | 1,930 | **1,930** | 0 | 0 / 0 (cert-ID identical) |
| hp c2-K | 1,940 | **1,940** | 0 | 0 / 0 (cert-ID identical) |
| xerox c2-cmy7 | 83 | **1,559** | **+1,476** | +1,476 / −0 |
| hp c2-cmy8 | 0 | **15** (C 15) | **+15** | +15 / −0 |
| hp c2-cmy7 | 0 | **0** | 0 | 0 / 0 |
| **corpus** | **10,706** | **12,516** | **+1,810** | **+1,813 / −3** |

**+16.9% more decoded LDPC payloads off the identical eight scans**, and the
distribution is nothing like the campaign's pre-registered expectation: the
uplift target contributed 133 of 1,813 gains, while 1,476 came from the
capture the plan called a print-frozen negative control.

**Named-losses ledger (the −3), complete:** xerox c3-cmy7 (0, 12, 19, main),
FOOTING — the baseline certified it at l02/6 ppc and the supplemental form
binds to the finest rung; xerox c2-cmy8 (0, 14, 23, C) and (0, 26, 3, C),
HISTORY — both were certified at exactly the footing `u-off` runs at, and a
supplemental baseline lane restores the CONFIGURATION, not the HISTORY
(§11.11).  Recovering them needs multi-footing `u-off` (named, deferred) or
frontier rollback (forbidden by §6.3).  Three losses against 1,813 gains, and
every one of the three is diagnosed.

**Volumes:** four closes reproduced byte-exact (301,600 / 718,413 /
465,580 ×2) and **one volume recovered that never had been (686,859 B)**.
Two volumes remain open and both for reasons the receiver cannot argue with:
hp c3-cmy8 needs ≥748 more symbols on a physically dead Y stream, and
hp c2-cmy8 reaches metadata rank 14 of 24 on a screened-mush page.

### 14.8 Honest limits

Single sheets.  Every row of this matrix is ONE physical capture of ONE
printed sheet, decoded from an archived scan; the campaign created no
physical data.  That makes these numbers **existence and regression
evidence** — this receiver reads this sheet at least this well, and does not
read it worse than the archived receiver did — and **not ladder promotion**:
no rate, margin, coding or engine call may move on them, because rate calls
go on multi-sheet MINIMA and there is exactly one sheet per row.  The
xerox c2-cmy7 close in particular says that `c2-cmy7` is recoverable on this
AltaLink print with this receiver; it does not make `c2-cmy7` a rung, and it
does not touch e032's finding that discovery tiers predict neither the level
nor the order of receiver outcomes.  **The receiver's qualification status is
unchanged: PROVISIONAL.**  The physical/null false-accept gate, the BER
envelope and the support margins are still unfrozen, every run in this matrix
emitted the provisional warning, and nothing here freezes them — the campaign
changes receiver POLICY, not the receiver's QUALIFICATION.  All hp Y facts
(hp c3-cmy8's Y 0, the blocked close) remain **toner-epoch confounded**: the
M281's yellow cartridge was marginal for e017/e030, so "Y is dead" is a
statement about that consumable state, not about the engine.  Finally, the
cross-epoch CPU column is a ±15% instrument (§14.4c) and no cost claim should
be read tighter than that.

### 14.9 Reap, waste, and deviations

| item | outcome |
|---|---|
| runs reaped | **none.** One polling task was killed by the background-task manager mid-matrix; the decode it watched was detached and finished normally. Zero decode wall lost |
| runs voided | none. All eight fingerprint-stable on the §8.5 content identities |
| HEAD moved under a run | once (hp c3-cmy8), docs-only, correctly ignored by the content law (§14.1) |
| deviation: `--workers 8` | delivered through `HOLO_RECEIVE_WORKERS=8`, because `full` mode exposes no `--workers` flag. Same seam, execution-only, recorded per run. NOT a code change |
| deviation: concurrency | rows 1 and 4 ran as a pair (see §14.1); everything else strictly sequential. Row 4's CPU is therefore contended and is the noisier of the two K calibration points |
| deviation: hp c2-K flags | `--page` is absent from its best-known flags, so the run used the **full 133-page cold hypothesis domain**, exactly as the archived (multi-invocation) run did. Its archived CPU baseline covers only the last invocation, so only mop-up + refine are comparable. Row annotated not-flag-reproducible, as provenance says |
| tree dirty during rows 7 and 8 | **by my own hand** — §14 was being written into `docs/COLOR-UPLIFT-MEASUREMENTS.md` while hp c2-cmy8 and hp c2-cmy7 ran, so their fingerprints record `dirty=True`. All three §8.5 CONTENT identities are byte-identical at entry and exit of both runs; `dirty` is git bookkeeping and is explicitly not the test. Recorded rather than hidden |
| observation: the two control archived states no longer load | `state_cache.build` on hp c2-cmy8 / hp c2-cmy7 raises `capture scale plan differs from format policy` — the campaign's coding-aware plan schedules u-lanes that a pre-campaign state's plan does not have. **This is the documented by-design refusal** (COLOR-UPLIFT-PLAN §2: "old states refuse resume by design"), it only ever bit these two because they are the only captures PK0 never cached, and it costs nothing: their archived certificate count is 0 by provenance, so the set difference is trivial and the B6 comparison runs off `events.jsonl`, which needs no state |
| observation (NOT fixed — outside this packet's scope) | **the harness's full-mode diag viewer is snapshot-starved.** `ab_runner.run_full` passes `run_receive` a plain chained function (`observe` then `diagnostics`); `EventSink._snapshot_capability` probes the OBSERVER for `wants_snapshot`/`wants_snapshots`, a plain function has neither, so the runtime never builds snapshots and the viewer's survey/placement panes and its `scraps`/`address` status rows stay empty for the whole run. `run_replay` passes the diagnostics object straight into `EventSink` and is unaffected; `cli.py` sets `observer = make_diagnostics(...)` directly and is unaffected. **Diagnostic-only** (RECEIVE-DESIGN §10 — strictly downstream, cannot change a decode) and it touched no number in this matrix, because every bar here is adjudicated from `events.jsonl`, the run JSON, the produced state and `gt_score`. It DOES mean the archived `status.json` footprint row and a candidate `status.json` footprint row are not the same quantity, which is why B6 is adjudicated on `address.final` instead. Owed as a P8 follow-up |

### 14.10 External review disposition (2026-08-10)

An external design+implementation review of the candidate (64ddea1 vs
af92029, "request changes") is committed as `docs/COLOR-UPLIFT-REVIEW.md`
with the verified disposition of every finding appended to it.  Every
load-bearing finding was reproduced or refuted first-hand before
disposition (verify-review-claims doctrine); three of the reviewer's probes
reproduced verbatim.  Actioned pre-merge in the review-response packet:
the zero-frontier u-lane gate (arm-split fix + pin test + §6.2a v0.54
amendment + policy token `union-lanes-…-v4-zerofrontier-…`), demap count
minted into cmy7 attempt identity, harness force-null env hygiene,
full-mode TIFF sha binding, truth-path vacuity predicate, u-lane
attribution in run JSON, the PK-FINAL derivation scripts committed, and
the §14.5/§14.6/§14.6a/§13.8 honesty amendments in this document —
including recording **B2 as FAILED AS WRITTEN with the waiver ratified by
the user's adoption ruling** (the review's central process finding,
correct).  Explicitly NOT actioned, with measured refutations: lazy LDPC
extrinsics (≤0.1% measured, bit-identical), per-coding scheduler identity
(v4's marginal invalidation set is empty; hand-bump doctrine stands), the
u-prefix parser (deliberate, pinned, safe direction).  Deferred with the
user's ruling: PK6/A2 (measure-first task in a new worktree), the
hp c2-cmy7 control re-run on main, exact CRC exposure counting, the memory
admission check, and the review's architecture packet (the separate
harmonization line).

Of these, the hp c2-cmy7 control re-run on main is DISCHARGED (2026-08-10,
arm `pkfinal-repin`, `a37caec` clean, tree stable): measured exactly as
predicted — U(off)/U(a3) now run and refuse at region fitting ("color
payload: detector has collapsed color support (Y)", uplift.payload 282.8 s
where the v3 gate spent 0.0 s and emitted nothing), the address ledger is
identical to archived and to the pre-merge candidate to the digit, and
certificates stay 0 with `truth_path_vacuous: true` — see the Run-ledger
row.

## 15. PK6/A2 MEASURE-FIRST — the per-window registration field, mapped before any arm exists

The deferred line's stage 1 (PLAN §8, user ruling 2026-08-10; the A2
[STRUCK v0.54] annotation in RECEIVE-DESIGN §6.2a authorizes exactly this
measurement).  Everything in this section is DEVELOPMENT SIGNAL from the
replay tier; nothing is a qualification number, and the outcome of the
pre-registered gate is a build/no-build RECOMMENDATION for the user's
ruling, never an adoption.

### 15.1 The return-only change and its null proof

`_fit_registration` now also returns the per-plane per-anchor NCC field
(`RegistrationAnchors`: page, cell_yx, window_index, offset_dots_xy,
quality, bucket — canonical key order; commit c0a9465).  The region fit
consumes byte-identical arrays; `anchor512-binleft` selection untouched;
production discards the field.  Null proofs, this tree:

- suite 1185 passed / 37 skipped;
- **10-specimen `patch_runner compare` vs the campaign pins under the
  UNCHANGED policy key: all 10 IDENTICAL, 0 wrong certificates, 0 moved,
  0 losses** (the cheapest true-null proof; pin key = policy id + hatches);
- instrumented replay of xerox c3-cmy7 l00 minted the identical 500
  certificates with and across instrument revisions.

The edit invalidates all recorded feature libraries by design
(`color_anchoring.py` is a PRODUCER module) — re-dump before any
library-tier work.

### 15.2 The instrument (dev tier)

`measure/_color_uplift_harness/regmap.py` (commit b67abd6): one
committed-pose LIVE replay per capture with read-only spies — production
anchor field captured at the `_fit_registration` seam, plus two
MEASUREMENT-ONLY re-measurement passes whose results production never
sees (`fit_plane_residual` stubbed; the production return is forwarded
verbatim, so the decode is bit-identical to an uninstrumented replay):
DENSE = bin-left at 4096/bucket (an exact superset of production's 512
picks), CENSUS = every word/dust candidate + seeded-capped certificate
bucket, on the first and last ordinary lanes.  Rejection accounting
(no-neighbourhood / uniform-bits / out-of-crop / low-quality, per lane ×
pass × plane) exists because the archived diags show whole-lane
zero-anchor fits on three of four captures.  Adversarial instrument
review executed the neutrality and gate-classification claims (identical
region outputs with and without spies; classification byte-exact against
`_measure_anchor` on four fixture variants).

### 15.3 THE PRE-REGISTERED ANALYSIS + GATE (committed before the primary capture's field was analyzed)

Implemented verbatim in `regmap_stats.py` + `regmap_analyze.py` from the
external stats review (whose two CRITICAL findings — the window-locked
sampling artifact of the unfiltered anchor crop, and the heteroscedastic
n_w↔σ_w anti-correlation that makes the naive permutation F non-exact —
shaped the design):

- residuals against the PRODUCTION fit; M0={1,y} deployed, M1={1,y,x}
  refit on window medians; gate on M1 residuals; NO |r|≤0.5 trim;
- whitening by (plane × bucket × quality-tercile) pooled within-window
  scale; per-window median + 1.4826·MAD; drop n_w<4; DerSimonian–Laird
  τ² over window medians with BOOTSTRAP median variances (the asymptotic
  π/2 formula under-covers: measured null q/df 1.43 ⇒ spurious LB>0;
  with bootstrap variances the 99% Q-profile lower bound is 0 on null);
- τ²_common / τ²_diff split; ρ(d) correlogram; τ at min-separation
  {0,2,4,8} cells; placebo = 200 seeded translations of the 160-cell
  window lattice (smooth field ⇒ placebo-typical; window-locked ⇒
  placebo-extreme); synchronized within-window bootstrap ×999 (observed
  from raw pools, null from centered pools, indices drawn once per
  plane-window and applied to both components);
- PRIMARY (one test, no correction): **xerox c2-cmy7, last archived
  ordinary lane, census pass, furniture buckets 0/1, min-separation 4,
  omnibus over the 6-vector** — the other three captures are
  replications, never a pass route;
- GATE (build A2 only if ALL hold): (i) placebo p<0.01 AND bootstrap
  p<0.01; (ii) ΔMSE = Σ_w u_w[(n_w²+2n_w·8)τ²_LB99 − n_w σ̂_w²]/(n_w+8)²
  > 0 with u_w = uncertified tiles; (iii) u-weighted RMS applied
  correction ≥ 0.03 cells (half `refine_phase_step_cells`); (iv)
  τ²_diff clears (ii) on its own.  Routing on failure: common-only ⇒
  pose refinement; phase-explained (G2) ⇒ sampler prefilter; M0−M1 ⇒
  region x-term.  Pre-gates G1 peak-lock KS, G2 phase, G3 saturation
  <2%, G4 reach (≥50% of uncertified mass in n_w≥8 windows), G5
  realized power.

**Calibration amendment (same day, still before the primary capture's
field existed).** A second independent verification pass executed the
analyzer against synthetic nulls and the c3-cmy7 smoke NPZ and found
three calibration defects, fixed in commit f54a03d before
xerox c2-cmy7 ran: (1) anchors are grouped by the RECORDED measuring
window, never a nearest-centre proxy (windows overlap; the proxy
contradicted the recorded identity for 21% of anchors and attenuated
τ up to 14%); (2) the placebo compares self-normalized grouping
z-scores — the raw standardized-Q sum is group-size dependent and made
gate (i) unfireable by construction (measured: even a strong synthetic
window lock never reached p<0.01); (3) τ² lower bounds use a
resampling-calibrated generalized-Q threshold plus the half-split
design effect (the χ² threshold had a measured 26% null false-positive
rate; within-window correlation reaches DEFF≈10 in the process
direction).  The bootstrap half of gate (i) is conservative by
construction (naive median resampling inflates the null ~1.4×) and is
left so.  Gate formulas and the primary designation are unchanged.

### 15.4 Measured fields (per capture)

(chain log `scratch/color-uplift/regmap/chain.log`; NPZ + analysis JSON
+ window-median PNGs under `scratch/color-uplift/regmap/`; analyzer
tree f54a03d)

**15.4.1 xerox c3-cmy7 (replication capture; 30 uncertified tiles).**
Full 14-lane instrumented LIVE replay, 2,024 s wall / 4,477 s CPU
contended, 411,160 anchor rows, 0 spy-pass failures; **810
certificates = the PK-FINAL LIVE number exactly** (arm-invariance of
the instrument on a full plan).  Findings:

- **The archived zero-anchor-lane anomaly does not reproduce.**  The
  archived diags showed `color.registration.*.anchors == 0` on 10/12
  lanes; the LIVE map measures healthy fields on all 14 lanes
  (production pass: 11–114 windows, median n_w 8–59 per plane).  The
  anomaly belonged to the pre-campaign code epoch, not the current
  anchoring path.
- **Window-scale structure is real and lane-persistent**: production
  τ_M0 (plane C, x) 0.37/0.41/0.39/0.25 dots on l00–l03 and 0.19–0.24
  on the r-lanes; σ ≈ 0.44–0.58 dots per anchor.  M1 ({1,y,x}) explains
  almost none of it — the field is not a linear ramp.
- **The mechanism splits, and mostly the wrong way for A2** (l03
  census): common-mode τ (x 0.195, y 0.137 dots) with process-direction
  design effect DEFF up to 11.5 — that is pose-scale, plane-COMMON
  structure whose home is pose refinement; the plane-DIFFERENTIAL x
  field is real (τ_diff 0.22–0.29 dots C/M/Y) but only C-x clears the
  diff ΔMSE (+0.07), M/Y go negative ⇒ **gate (iv) fails on this
  capture** (Σ ΔMSE_diff = −1.0).  G2 flags C-x as marginally
  phase-suspect (R² 0.39, permutation p 0.014) — part of the x field
  may be the sampler, not the engine.
- Primary-style omnibus at l03 (census, min-sep 4): bootstrap p 0.001,
  calibrated placebo p 0.0149 (z_true 57 vs placebo mean 10) — the
  structure at the fine lane IS window-locked, but the placebo misses
  the 0.01 bar with W=27 windows.  At l00 (W=114) the same test reads
  placebo-typical (smooth field) — window-locking emerges at the fine
  lanes, exactly where poses re-fit.
- Deployed: reach 1.00 (all 30 residue tiles sit in n_w≥8 windows at
  l03), per-axis RMS applied correction 0.056–0.090 cells (above the
  0.03 floor), total ΔMSE > 0 on all planes — but dominated by the
  common mode the arm is the wrong tool for.

**15.4.2 xerox c2-cmy7 — THE PRIMARY CAPTURE (313 uncertified tiles).**
Full 14-lane instrumented LIVE replay, 9,354 s wall / 24,083 s CPU,
622,869 anchor rows, 0 spy-pass failures; **1,559 certificates = the
campaign's terminal number exactly** (archived 83 → LIVE 1,559).
Pre-registered gate, scored as written:

- **(i) FAILS, narrowly**: bootstrap p 0.001 ✓; calibrated placebo p
  **0.0149** vs the 0.01 bar (z_true 33.4, placebo mean 3.6, placebo
  p99 32.5 — the true lattice sits AT the 99th percentile of
  translations, two of 200 exceed it).
- **(ii) PASSES**: ΔMSE total +36.2 (C +18.9 / M +12.1 / Y +5.2).
- **(iii) PASSES**: u-weighted per-axis RMS applied correction 0.036
  cells aggregate (0.030/0.036/0.041 per plane) vs the 0.03 floor.
- **(iv) PASSES**: ΔMSE_diff total **+21.7** (C +12.8 / M +9.1 /
  Y −0.1) — unlike the c3 replication, the PLANE-DIFFERENTIAL
  structure clears the MSE bound on its own here, dominated by the
  y component (τ²_diff_LB99 0.11/0.09 dots² on C/M at DEFF 7.7–8.4).
- **Pre-gate G4 (reach) FAILS DECISIVELY**: uncertified-tile mass in
  windows with own-window production n_w ≥ 8 is **C 20.8% / M 16.0% /
  Y 0.0%** vs the ≥50% bar; median own n_w on residue windows is 3–5.
  The residue lives exactly where furniture anchors are starved — the
  κ=8 fallback triggers where the arm is needed.  **G3 FAILS on Y**
  (9.3–9.8% of census anchors at the correlation-surface edge; Y's
  dust-only offsets are censored, its τ numbers untrustworthy).  G1:
  peak-lock KS 0.028–0.037 C/M, 0.063–0.065 Y (mild lattice pull,
  subdominant at the measured τ but real on Y).  G2 passes (phase R²
  ≤ 0.05 — the field is not the sampler's).  G5: ρ̄ 0.44 ⇒ n_eff 2.2
  per window at n=201 — τ_min 0.12 dots; the census sees the y
  differential (≈0.3 dots) comfortably, the x differential (≈0.15)
  marginally.
- Other measured facts: min-sep curve flat (structure survives 8-cell
  thinning — not shared-pixel correlation); common-mode τ x 0.13 /
  y 0.08 dots; differential τ x 0.21/0.12/0.21, y 0.14/0.12/0.09
  (C/M/Y).
- **POST-HOC diagnostic (NOT pre-registered, same NPZ): the spec's
  own(+halo) pooling changes the reach verdict entirely** — pooling
  production anchors over the A3 halo rule (bbox dilated by own
  height/width per side) lifts median residue-window n_w from 3–5 to
  **65–99** and reach(n≥8) to **1.000 on all three planes**.  A
  halo-pooled per-window constant is, operationally, a smoothed local
  field estimate over ~3 windows' scale — the regime the placebo
  already calls smooth — i.e. the reachable form of A2 collapses
  toward a field-model/region-enrichment design, not independent
  per-window constants.

**15.4.3 xerox c2-cmy8 (replication; 150 uncertified stream-slots, 1
empty tile).**  15-lane LIVE replay, 4,332 s wall, 671,207 anchor rows,
0 spy-pass failures; **5,466 certificates (C 1,802 / M 1,867 /
Y 1,797) = PK-FINAL exactly.**  Replication findings: omnibus at l03 —
bootstrap p 0.002 but placebo p **0.164** (z_true 28.4 vs placebo p99
123): on this capture the field is SMOOTH, not window-locked.  Reach:
C 0.457 / M 0.200 / Y 0.040 — the own-window arm is starved on the
residue here too.  Y saturation 12.6–16.0% (worst of the corpus so
far).  Differential τ replicates the primary's magnitudes (x
0.18–0.24, y 0.09–0.14 dots); ΔMSE_diff +3.2 C / +0.1 M / −1.4 Y.
Nothing here is a pass route (plan line 13); the replication is
consistent: real, largely smooth differential structure the specced
arm cannot reach.

**15.4.4 hp c3-cmy8 (replication; the charter's registration-immune
tails).**  18-lane LIVE replay, 5,999 s wall, 565,022 anchor rows, 0
spy-pass failures; **796 certificates (C 740 / M 56) = PK-FINAL
exactly** — four for four on instrument cert-exactness.  Omnibus at
l04: placebo p 0.005 (window-locked) but bootstrap p only 0.054 —
weak.  Reach is the corpus's best (C 0.65 / M 0.71) and it does not
help: **ΔMSE M −5.4 / Y −36.7 and ΔMSE_diff M −33.3 / Y −36.7** — the
arm would actively harm the M tail and the dead-Y stream, exactly the
"registration-immune tails" the deferral entry predicted.  Y anchor
saturation 20.8–21.9% (worst measured).  Only the 100-slot C tail
shows benefit (ΔMSE +31.4, diff +0.7).

### 15.5 verdict — THE GATE FAILS; THE LINE CLOSES AS A MEASURED NEGATIVE

Scored by `regmap_analyze verdict` (analyzer f54a03d) on the
pre-registered ALL-FOUR conjunction:

| capture | (i) placebo / bootstrap | (ii) ΔMSE | (iii) RMS cells | (iv) ΔMSE_diff | ALL-FOUR |
|---|---|---|---|---|---|
| **xerox c2-cmy7 (PRIMARY)** | **0.0149** / 0.001 | +36.2 | 0.0357 | +21.7 | **NO** |
| xerox c2-cmy8 | 0.164 / 0.002 | +9.3 | 0.0493 | +1.9 | NO |
| hp c3-cmy8 | 0.005 / **0.054** | −10.7 | 0.0266 | −69.2 | NO |
| xerox c3-cmy7 | 0.0149 / 0.001 | +9.8 | 0.0800 | −1.0 | NO |

The primary fails gate (i) (placebo 0.0149 > 0.01) and, independently,
pre-gates **G4** (reach C 20.8% / M 16.0% / Y 0% ≪ 50%) and **G3 on Y**
(9–22% saturation corpus-wide).  No capture passes all four; each
fails a DIFFERENT leg — the field is real but never simultaneously
window-locked, statistically decisive, plane-differential, and
reachable by the specced arm on the same capture.

**What the measurement established (the positive content of the
negative):**

1. **The mechanism is real at window scale.**  Plane-differential
   registration structure of τ ≈ 0.1–0.3 print dots exists on every
   capture (e025's refusal mechanism, now measured in situ), clears
   the shrinkage-MSE bound on the primary (+21.7), survives 8-cell
   min-separation thinning, and is not the sampler's phase (G2).
2. **It is predominantly SMOOTH, with a strong plane-common (pose)
   component.**  Placebo-typical at coarse lanes and on c2-cmy8;
   marginal (p 0.005–0.015) at fine lanes; process-direction design
   effects of 8–11 mark pose-scale correlation.  The pre-registered
   routing sends the common mode to POSE REFINEMENT and the smooth
   differential field to REGION-MODEL ENRICHMENT — not to independent
   per-window constants.
3. **A2-as-specced cannot reach the residue it exists for.**
   Own-window production anchors give median n_w 3–5 on residue
   windows (κ=8 fallback fires exactly where the arm is needed); the
   spec's own(+halo) pooling recovers reach 1.000 but converts the arm
   into a ~3-window-scale smoother — i.e. the reachable variant IS a
   field model, collapsing this line into the region-enrichment
   routing above.
4. **Y anchors are not currently measurable at fine pitch** (dust-only
   supply, 9–22% correlation-edge saturation, strongest peak-lock) — a
   sampler improvement (prefiltered anchor crop, wider search, or
   word-site Y ink in a future format) is prerequisite to ANY Y-side
   registration claim.
5. The archived whole-lane zero-anchor anomaly was an artifact of the
   pre-campaign epoch; the merged receiver measures anchors on every
   lane of every capture (61 lanes total, 0 spy-pass failures).

**DISPOSITION: A2 per-window plane-registration residuals is NOT
BUILT.  The PK6/A2 line is CLOSED as a measured negative** (the §8
deferral's own success criterion).  The two routings the data DOES
support are separate, future measure-first lines, both answerable
substantially from the archived regmap NPZs before any new code:
(a) region-field enrichment — an x-term / smooth nonlinear
plane-differential field in the region registration model (the M0→M1
delta measured here is small because the field is nonlinear; the
right basis is the next question); (b) per-window pose-refinement
coupling for the plane-common component.  Neither inherits A2's
charter or its struck token.

### 15.6 THE OWED SAMPLER REPAIR — the Y word lattice becomes measurable (2026-08-30)

Closing finding 4 named "a sampler improvement (prefiltered anchor
crop, wider search, or word-site Y ink in a future format)" as
prerequisite to ANY Y-side registration claim.  This is its first
half, on branch `ysampler-fix`.  Nothing here is an adoption: the
production residual fit is untouched and byte-identical.

**"Dust-only" was literal, and the cause is a POLARITY GATE.**
`format/pilots.py::color_word_states` renders the v1 colour word as
states {0, 3}; state 3 is C+M, so **no word site ever carries Y**.
`_fit_registration`'s candidate gate then demanded known INK at the
anchor centre, so every Y word site was a known cell the sampler
refused for its polarity alone.  Counted straight off the archived
NPZs — no new replay — Y word anchors are **0 on all four captures in
all three passes**, against C/M's thousands (census pass, fine lane):

| capture | C word / dust | M word / dust | Y word / dust |
|---|---|---|---|
| xerox c2-cmy7 (PRIMARY) | 36,595 / 5,889 | 36,762 / 5,825 | **0** / 8,647 |
| xerox c2-cmy8 | 32,824 / 6,827 | 32,868 / 6,720 | **0** / 9,086 |
| hp c3-cmy8 | 17,543 / 3,771 | 17,060 / 3,734 | **0** / 4,828 |
| xerox c3-cmy7 | 4,814 / 806 | 4,854 / 823 | **0** / 1,206 |

Bucket does not drive anchor quality — C and M read word ≈ dust ≈ cert
on both saturation and median NCC quality — so the Y word lattice was
withheld by the gate, not by the channel.

**The repair (`src/holo/receive/color_anchoring.py`).**
`_measure_anchor` loses `bits[1, 1] = 1` / `weights[1, 1] = 1.0`.  Both
were no-ops — the caller's gate guarantees a KNOWN centre, and
`_prepare_known_field` has already written the known value at
confidence 1.0 into `detected`/`confident` (pinned by
`test_known_centres_need_no_forced_bit_so_polarity_is_free`) — but the
forced ink polarity was what confined the kernel to inked centres.
`measure_ink_free_anchors` is then the MEASUREMENT-ONLY pass over
known ink-free centres, same kernel, same selection, same budget.
`_fit_registration` still consumes the known-ink population alone.

**Measured: one bounded specimen decode** (`frozen-cmy7`, cut from this
section's PRIMARY capture, `c2` = fine pitch; 7 region fits; 0
certificates / 0 wrong = its pinned outcome under all four recorded
pins, so the decode is the pinned one):

| plane | production word / total | ink-free word / total |
|---|---|---|
| C | 2,838 / 3,288 | 2,491 / 3,096 |
| M | 2,889 / 3,255 | 2,392 / 3,124 |
| **Y** | **0 / 622** | **3,430 / 3,827** |

Y anchor supply **×6.2**, and the word lattice — 100 sites per tile
against dust's 20, certificate-independent and residue-unbiased — goes
from nothing to Y's largest anchor class.  That is the supply half of
finding 4, closed.

**Null proof.** The same instrument, same specimen, run on the pre-fix
`color_anchoring.py` and on the repaired one: the production anchor
population is **BYTE-IDENTICAL, 7,165 rows, all three planes**
(C 3,288 / M 3,255 / Y 622 both trees; `np.array_equal` and equal
`tobytes()`).  Not just non-Y — nothing moves, so no policy id moves.
`tests/holo` green.

**The saturation half is NOT fixed, and the reason is now measured.**
The new Y word anchors read median NCC quality 0.668 and G3 saturation
0.164, against Y's production dust anchors at 0.834 / 0.119 — they do
not clear G3's 2% bar, and finding 4's "9–22% saturation" stands.  The
mechanism is the SEARCH RADIUS, which `_ANCHOR_MAX_SHIFT_PX = 5` sizes
for C/M.  Census offset magnitudes at the fine lane, against the radius
the sampler allows:

| capture (radius) | plane | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|
| xerox c2-cmy7 (±1.5) | C | 0.40 | 0.59 | 0.84 | 1.02 |
| | M | 0.37 | 0.53 | 0.75 | 0.95 |
| | **Y** | 0.55 | 0.84 | **1.20** | **1.50 = the wall** |
| hp c3-cmy8 (±2.5) | C | 0.81 | 1.24 | 1.79 | 2.50 |
| | **Y** | 0.96 | 1.95 | **2.50 = the wall** | 2.50 |

Y's spread is ~1.5× C/M's and reaches the censor from the 90th
percentile up; the AltaLink's own measured Y x-registration sinusoid
(0.83 dot peak, project-record) is 55% of the entire c2 search radius
before any pose error is added.  Giving Y the headroom C has
(radius / p95 ≈ 1.5) needs **at least** ≈ ±2.2 dots at c2 — a lower
bound, because Y's p95 is itself censored at the wall.
`_ANCHOR_MAX_SHIFT_PX`
is plane-common, so widening it moves C and M too and CANNOT be
null-proven at this tier — it is a measured, quantified proposal, not
a change.  On hp c3-cmy8 the saturation is additionally quality-driven
(saturated-anchor median quality 0.610 vs 0.757 clean; saturation by
quality quartile 0.296/0.299/0.165/0.074), which is the starved-Y
contrast the e030/e031 record already carries.

**What this unlocks.** §15.5's supported routing was region-field
enrichment, and its blocker on Y was supply, not model: the residue
windows that starved the own-window arm now have a dense, uniform,
certificate-independent Y anchor lattice to build a field on.  Feeding
these anchors to `fit_plane_residual` would move Y sampling on every
archived colour state and is a separate, policy-bumping adoption.

Caveats: one specimen, one capture, replay tier — development signal,
not a capture-level or population number.  Editing `color_anchoring.py`
invalidates every recorded feature library (§15.1's standing rule);
the libraries predate this change and must be re-dumped before any
library-tier comparison.  `regmap.py`'s rejection classifier still
mirrors the removed `bits[1, 1] = 1`; that mirror stays correct for the
ink population it observes and is stale only if the ink-free pass is
ever routed through it.  Artifacts:
`measure/ysampler/`, run JSON + anchor NPZs under `scratch/ysampler/`.

Run ledger appendix (all: mode replay+instrument, arm regmap, LIVE,
src tree c0a9465 / harness b67abd6 / analyzer f54a03d; artifacts
`scratch/color-uplift/regmap/`): xerox-c3-cmy7 2,024 s wall, 810
certs (=PK-FINAL); xerox-c2-cmy7 9,354 s, 1,559 (=); xerox-c2-cmy8
4,332 s, 5,466 (=); hp-c3-cmy8 5,999 s, 796 (=).  Cost columns in the
four run JSONs are instrumentation-inflated and labelled as such.

#### 15.6a AMENDMENT — the in-tree repair is REVERTED; the measurement moves to runtime composition (2026-08-31)

Everything above stands as measured.  What changed is *where the
ink-free kernel lives*.  Project-lead ruling: **src/holo's diff stays
zero — v1 measurement needs are met by runtime composition inside a
harness, never by tree edits.**  "Provably inert" is not the bar; the
bar is that the production tree does not move for a measurement.

Reverted verbatim to `165aa1a^1`: `src/holo/receive/color_anchoring.py`
(the forced ink centre `bits[1, 1] = 1` / `weights[1, 1] = 1.0` is back
in `_measure_anchor`, candidate enumeration and the NCC loop are inline
in `_fit_registration` again, and `_prepare_known_field` /
`_plane_candidates` / `_measure_plane_anchors` /
`measure_ink_free_anchors` are gone), and with it the two pins in
`tests/holo/test_receive_color_payload.py` that exercised the removed
function.  `git diff 165aa1a^1 HEAD -- src/holo` is **empty**;
`tests/holo` green at 1,465 passed / 46 skipped.

The measurement is re-expressed in `measure/ysampler/composition.py`,
built from production's own parts inside the harness process only:

* the candidate gate is inline, so the **rows** are substituted —
  `flip_known_component_bits` inverts known component bits at known
  sites only, which retargets the inline gate onto `mask & ~true_bits &
  search`, and the inversion is cancelled inside the one substituted
  function so the NCC template still sees the true field.  An exact
  involution over the only two readers of `known_component_bits` in
  that call tree, so selection, dedupe, budget, key order and
  `RegistrationAnchors` construction remain production's own code;
* the forced centre is lifted by substituting
  `color_anchoring._measure_anchor` for the duration of the pass, in
  the technique `_color_uplift_harness/regmap.py` already uses on these
  same seams; both substitutions are restored in `finally`.

**Numbers reproduced identically.**  The computation is the same
computation, so the harness reproduces the table above to the anchor
row — C 2,838/3,288 and 2,491/3,096, M 2,889/3,255 and 2,392/3,124,
**Y 0/622 and 3,430/3,827**, Y word quality 0.668 / G3 saturation
0.164.  The run additionally carries an IDENTITY CONTROL: the composed
kernel re-run with the polarity lift switched off, required to be
bit-identical to production's own return across all six
`RegistrationAnchors` arrays.  It passes on every region fit, which is
the null proof above re-derived per run instead of across two trees.

Consequences of the revert, recorded honestly:

* the two pins named above no longer exist, and `measure/` is outside
  `testpaths` — the no-op invariant has no standing pytest guard.  The
  identity control replaces it, but only when someone runs the
  instrument.  Two `ast`-level seam guards refuse the run outright if
  `_measure_anchor`'s body or `_fit_registration`'s inline gate has
  moved since the harness copied them;
* `regmap.py`'s rejection classifier mirrors `bits[1, 1] = 1`, which is
  again the production truth — the staleness caveat above is withdrawn;
* `color_anchoring.py` is byte-identical to the tree the recorded
  feature libraries were dumped against, so §15.1's re-dump caveat no
  longer applies to this line;
* the variant can be measured but never adopted from here.  Adoption,
  should it ever be ruled, is a tree change with its own policy-id bump.

Artifacts unchanged: `measure/ysampler/` (see its README, which leads
with the zero-diff rule), run JSON + anchor NPZs under
`scratch/ysampler/`.

## Run ledger

| date | arm (commit) | mode | capture/sim | outcome | artifact |
|---|---|---|---|---|---|
| 2026-08-10 | **pkfinal-repin** (`a37caec` main, tree `cef9b98039d3`, clean) | FULL, fresh state, workers 8, diag 8023 | hp c2-cmy7 | **B6 CONTROL RE-PINNED ON MERGED MAIN — the §14.10 deferred re-run, prediction met on all three counts.** U(off)/U(a3) now RUN and refuse: `payload.plan` on l03's 96 committed poses (prior certificates 0) → `payload.region` accepted=false, reason "color payload: detector has collapsed color support (Y)" → `payload.complete` 0 certificates; **uplift.payload 282.8 s (144.6 + 138.1) where v3's silent pre-gate spent 0.0 s and emitted nothing**; U(a4b) not scheduled (single-stream cmy7, codec-aware plan). Address ledger IDENTICAL to archived AND to the pre-merge candidate to the digit (4,840 words, 421 certified, 808 placements, 2,713 unresolved, mop-up hypotheses to the digit; u-lane `address.final` all-zero). **0 certificates**, close open, `truth_path_vacuous: true` (the c337a7a predicate), 0 wrong / 0 audited; standard-lane CPU −4.7% vs archived events. 6,262 s wall / 9,147 s CPU / 38.3 GiB | runs/hp-c2-cmy7-full-pkfinal-repin.json, runs/score-pkfinal-repin-…, runs/{lanes,address,stagetime}-pkfinal-repin-…, runs/treefp-pkfinal-repin-… |
| 2026-08-10 | pkfinal (same tree) | FULL, fresh state, workers 8, diag 8023 | hp c2-cmy7 | **B6 CONTROL, THE PURE NO-OP — 0 certificates, 0 payload blocks built on any lane, and the address ledger IDENTICAL to archived line for line AND total for total** (4,840 words, 421 certified, 808 placements, 2,713 unresolved, mop-up hypotheses to the digit). Both u-lanes cost **0.0 s** and emit nothing. 5,235 s wall / 7,986 s CPU / 41.6 GiB; standard-lane CPU −16.6% vs archived = pure epoch on a page the arms cannot reach | runs/hp-c2-cmy7-full-pkfinal.json, runs/address-pkfinal-… |
| 2026-08-10 | pkfinal (same tree) | FULL, fresh state, workers 8, diag 8023 | hp c2-cmy8 | **B6 CONTROL — addressing IDENTICAL to archived to the digit** (3,796 words, 86 certified, 721 addressing-lane placements, 5,139 unresolved; +17 refine re-poses, which exist only because there is now a frontier to refine around), so footprint holds at 45.1%, delta 0.0 pt. **15 certificates appeared where archived had 0 (C 15, one of them from `u03-a3`) and B5's GT check adjudicates all fifteen CORRECT** (0 wrong / 59,640 cells) — reported per B6 v1.1, not a leak signal. Close open at metadata rank 14/24. 10,340 s wall / 17,430 s CPU / 42.2 GiB | runs/hp-c2-cmy8-full-pkfinal.json, runs/score-pkfinal-…, runs/address-pkfinal-… |
| 2026-08-10 | **pkfinal** (`4577652`, tree `3838cccf30a6`) | **FULL**, fresh state, workers 8, diag 8023 | xerox c3-cmy7 | **THE CANARY, MET — 810 certificates, +91 / −1 vs the archived 720**; close **VERIFIED 301,600 B** (emitted-payload sha AND archived `recovered.bin`); wrong-cert **0 / 9,661,680**, agreement 1.0; lane for lane IDENTICAL to the PK8 replay (l00 500); address ledger identical to archived to the digit; 2,073 s wall / 4,775 s CPU / 12.8 GiB. The one loss is §11.11's l02/6 ppc FOOTING address (0,12,19) | runs/xerox-c3-cmy7-full-pkfinal.json, runs/score-pkfinal-…, runs/{lanes,address,setdiff,stagetime}-pkfinal-… |
| 2026-08-10 | pkfinal (same tree) | FULL, fresh state, workers 8, diag off (paired with the canary) | xerox c2-K | **B1 K — 1,930 certificates, CERTIFICATE-ID SET IDENTICAL to archived, lane for lane, address ledger identical line for line**; close **VERIFIED 465,580 B** (both shas); wrong-cert **0 / 7,905,280**; 1,932 s wall / 2,390 s CPU / **40.3 GiB** (a full decode of a 4800 dpi K sheet is NOT medium). +15.4% CPU vs archived events on bit-identical output = the cross-epoch instrument's noise, contended | runs/xerox-c2-k-full-pkfinal.json, runs/score-pkfinal-… |
| 2026-08-10 | pkfinal (same tree) | FULL, fresh state, workers 8, diag 8023 | hp c3-cmy8 | **THE B3 ADJUDICATION — 796 certificates = C 740 / M 56 / Y 0 over 746 tiles; bar C>620 ∧ M>43 MET on both components**; **+133 / −0 = STRICT SUPERSET** of the archived 663 (every archived certificate id reproduced); wrong-cert **0 / 3,164,896**; close still open (2 of 3 blocks, ≥748 symbols, streams M,Y); standard-lane CPU **−14.3%** vs archived with the u-lane tail at +1,198 s; 6,433 s wall / 14,481 s CPU / 41.6 GiB. HEAD moved under this run (docs-only, §8.5 content identities stable) | runs/hp-c3-cmy8-full-pkfinal.json, runs/score-pkfinal-…, runs/setdiff-pkfinal-… |
| 2026-08-10 | pkfinal (same tree) | FULL, fresh state, workers 8, diag 8023 | xerox c2-cmy8 | **B1 — close VERIFIED 718,413 B byte-exact** (emitted-payload sha AND archived `recovered.bin`); **5,466 certificates = C 1,802 / M 1,867 / Y 1,797**, +98 / −2 vs the archived 5,370, u-lanes 3 / 1 / 2 exactly as PK-CLEAN's replay; wrong-cert **0 / 21,732,816**; standard-lane CPU +9.3%, u-lanes +874 s; 4,180 s wall / 6,670 s CPU / 41.9 GiB. The two losses are §11.11's HISTORY pair | runs/xerox-c2-cmy8-full-pkfinal.json, runs/score-pkfinal-… |
| 2026-08-10 | pkfinal (same tree) | FULL, fresh state, workers 8, diag 8023, **full 133-page domain** | hp c2-K | **B1 K — 1,940 certificates, CERTIFICATE-ID SET IDENTICAL to archived, lane for lane**; close **VERIFIED 465,580 B** (both shas); wrong-cert **0 / 7,946,240**; 2,376 s wall / 9,118 s CPU / 41.1 GiB. Ran the archived run's own best-known flags (no `--page`), so the cold hypothesis domain is all 133 pages; the archived state is multi-invocation so only mop-up + refine are CPU-comparable — and there the candidate is **−11.0%** on bit-identical output | runs/hp-c2-k-full-pkfinal.json, runs/score-pkfinal-… |
| 2026-08-10 | pkfinal (same tree) | FULL, fresh state, workers 8, diag 8023 | xerox c2-cmy7 | **THE CAMPAIGN'S HEADLINE — the print-frozen NEGATIVE CONTROL CLOSES. 1,559 certificates against the archived 83 (+1,476 / −0, strict superset), 83.3% of the page, and the fountain closes VERIFIED at 686,859 B with the emitted payload's sha — a volume never before recovered from paper on any engine** (e032: FAILED on both). Wrong-cert **0 / 18,595,752**, agreement 1.0; address ledger identical to archived to the digit (7,818 words, 1,120,290,105 hypotheses), so the change is entirely cell-level readout: l00 2 → 751, l01 0 → 587, u03-a3 +15. Standard-lane CPU **−21.5%**; 8,962 s wall / 23,423 s CPU / 41.7 GiB | runs/xerox-c2-cmy7-full-pkfinal.json, runs/score-pkfinal-…, §14.3 |
| 2026-08-09 | pk89 follow-up (`4c3cd668d8ef`, the SHIPPED tree) | replay force-null, workers 4, close, diag | xerox c3-cmy7 | **THE FORCE-NULL INVARIANT, RESTORED AND MEASURED — 720/720, certificate-ID set IDENTICAL to archived and IDENTICAL LANE FOR LANE to the null-tree pin**, with `DEMAP_ITERATIONS = 3` live and the policy id carrying `cmy7-demapiter3`; wrong-cert 0/8,588,160; close VERIFIED 301,600 B; 937 s wall / 2,050 s CPU / 12.9 GiB | runs/xerox-c3-cmy7-replay-pk89shipnull.json, runs/score-pk89shipnull-xerox-c3-cmy7.json |
| 2026-08-09 | pk89 (8872288 tree + PK8/PK9 diff, `4e5b9768eac1`) | sims x9, workers 6 | B7/B8 grids | **`baseline-repro` reproduces `sims-baseline.json` EXACTLY** at all 16 points (the fidelity control); **B7 MET at 3 demap iterations (p\* 0.015 -> 0.0275)**, not met at 2 (0.0225), no tested p regressing at either; **B8 MET by P3 alone** (20/20 all-pass, 480/480 at the bar point) and **P4 NOT MET** (0/20, −36 tiles); joint arms strictly worse than P3 alone; erasure-floor grid collapses to two distinct arms (margins are {0, lambda} in this channel) | runs/sims-pk89-*.json (§13.2/§13.3) |
| 2026-08-09 | pk89 (null constants, `4e5b9768eac1`) | replay force-null, workers 4, close, diag | xerox c3-cmy7 | **THE NULL PIN — 720/720, certificate-ID set IDENTICAL to archived** (missing 0, extra 0); wrong-cert 0/8,588,160, agreement 1.0; re-close VERIFIED 301,600 B (payload sha AND archived `recovered.bin`); 902 s wall / 1,992 s CPU / 13.5 GiB | runs/xerox-c3-cmy7-replay-pk89null.json, runs/score-pk89null-xerox-c3-cmy7.json |
| 2026-08-09 | pk89iter3 (`101cade598e4`) | replay LIVE, workers 4, close, diag | xerox c3-cmy7 | **810 certificates vs PK-CLEAN's 771 — +39 gained / 0 lost, strict SUPERSET**; l00 413 -> 500; uncertified tail 69 -> 30; wrong-cert 0/9,661,680; close VERIFIED 301,600 B; 1,159 s wall / 2,636 s CPU (+45%) / 13.1 GiB | runs/xerox-c3-cmy7-replay-pk89iter3.json, runs/delta-pk89-xerox-c3-cmy7.txt, runs/score-pk89iter3-xerox-c3-cmy7.json |
| 2026-08-09 | pk89iter3 (same tree) | replay LIVE, workers 4, close, diag | hp c3-cmy8 | **STRICT NO-OP ASSERTED — 796 = C 740 / M 56, every lane identical to PK-CLEAN, 0 gained / 0 lost, same certificate set vs archived** (produced 796, missing 0, extra 133, identical list); wrong-cert 0/3,164,896; close still open (dead Y); 4,442 s wall / 9,234 s CPU / 41.6 GiB | runs/hp-c3-cmy8-replay-pk89iter3.json, runs/delta-pk89-hp-c3-cmy8.txt, runs/score-pk89iter3-hp-c3-cmy8.json |
| 2026-08-09 | pk89iter2 (`aa1416b70873`) | replay LIVE, workers 4, close, diag | xerox c3-cmy7 | **the third iteration's price: 795 certs (+24 / −0, superset)**, wrong-cert 0/9,482,760, close VERIFIED; 1,083 s wall / 2,298 s CPU — 19.9 s CPU per certificate against iters 3's marginal 22.5 s, so the cost curve is flat and 3 is the BAR's point, not a knee | runs/xerox-c3-cmy7-replay-pk89iter2.json, runs/delta-pk89iter2-xerox-c3-cmy7.txt |
| 2026-08-09 | pk89iter3 (`ec0b667c451a`, comments only vs `101cade598e4`) | replay LIVE, workers 4, close, diag | xerox c2-cmy8 | **B1/R5 HELD — 5,466 = C 1,802 / M 1,867 / Y 1,797, every lane identical to PK-CLEAN, 0 gained / 0 lost**; wrong-cert 0/21,732,816; close **VERIFIED 718,413 B** (payload sha AND archived `recovered.bin`); 3,345 s wall / 5,013 s CPU / 41.5 GiB, run beside the slow-lane suite | runs/xerox-c2-cmy8-replay-pk89iter3.json, runs/delta-pk89-xerox-c2-cmy8.txt, runs/score-pk89iter3-xerox-c2-cmy8.json |
| 2026-08-09 | pk89iter3 (same tree) | patch compare, 10 specimens | specimen corpus | **all 10 IDENTICAL** — 0 moved, 0 with losses, 0 wrong certificates, `outside_domain` 0, agreement 1.0, every run tree-stable; the re-timing IS visible inside a specimen (l00tax-a l00 24 -> 29 / l01 6 -> 1 for the same 30 certificates). Pin fallback fired loudly (policy key d31096c4b62829ba -> a765f290bce6c978); re-pinning owed at merge | runs/patchcompare-pk89iter3.json |
| 2026-08-07 | baseline (5f2b4b9) | replay force-null | xerox c3-cmy7 | 720/720 identical, re-close byte-exact | runs/xerox-c3-cmy7-replay-baseline-forcenull.json |
| 2026-08-07 | baseline (5f2b4b9) | replay force-null | xerox c2-cmy8 | 5,370/5,370 identical, re-close byte-exact | runs/xerox-c2-cmy8-replay-baseline-forcenull.json |
| 2026-08-07 | baseline (5f2b4b9) | replay force-null | hp c3-cmy8 | 663/663 identical, close open (honest) | runs/hp-c3-cmy8-replay-baseline-forcenull.json (log) |
| 2026-08-07 | baseline (573e8e8) | sims | B7/B8 grids | p*=0.015; erasure cliff f 0.05→0.10 | runs/sims-baseline.json |
| 2026-08-07 | pk2 (0f13972 tree) | replay force-null | xerox c3-cmy7 | 720/720 cert-ID identical (PK2 byte-identity judge); wrong-cert 0/8,588,160; re-close byte-exact; 1,518 s wall (no diag — not CPU-comparable to the diag-attached baseline row) | runs/xerox-c3-cmy7-replay-pk2-forcenull.json |
| 2026-08-07 | control-price (0f13972) | full ×2, queued overnight | hp c2-cmy7, hp c2-cmy8 | B6 control pricing (sequential, workers per stage default) | logs/full-hp-c2-*.log |
| 2026-08-07 | pk3 (2f8d62d tree) | replay force-null, workers 4 | xerox c3-cmy7 | 720/720 cert-ID identical; wrong-cert 0/8,588,160 (agreement 1.0); re-close VERIFIED 301,600 B; wall 1,006 s / CPU 2,183 s / 12.9 GiB | runs/xerox-c3-cmy7-replay-pk3-forcenull.json, runs/score-pk3-xerox-c3-cmy7-forcenull.json |
| 2026-08-07 | pk3 (2f8d62d tree) | replay LIVE, workers 4 | xerox c3-cmy7 | **727 certs (+7 addresses net: 12 gained, 5 lost)**; wrong-cert 0/8,671,656 (agreement 1.0); re-close VERIFIED 301,600 B; head adopted 12/12 lanes, 1/a 1.19–1.58, saturation down in every lane; wall 1,076 s / CPU 2,256 s / 13.1 GiB | runs/xerox-c3-cmy7-replay-pk3.json, runs/score-pk3-xerox-c3-cmy7.json |
| 2026-08-07 | pk3 (2f8d62d tree) | replay LIVE, workers 4 | xerox c2-cmy8, hp c3-cmy8 | **FINISHED — cert-ID sets IDENTICAL (5,370 and 663), wrong-cert 0 on both (agreement 1.0); the §4.6 strict-no-op scope check is CLOSED** | runs/xerox-c2-cmy8-replay-pk3.json, runs/hp-c3-cmy8-replay-pk3.json, runs/score-pk3-xerox-c2-cmy8.json, runs/score-pk3-hp-c3-cmy8.json |
| 2026-08-07 | pk3 (5e51bd8) | replay LIVE, lane l00 only, workers 4, attempts recorded | xerox c3-cmy7 | **295 certs = the full run's l00 exactly**; strict subset of the null arm (0 gained, 38 lost); wall 250 s / CPU 601 s | runs/xerox-c3-cmy7-replay-l00-head.json |
| 2026-08-07 | pk3 (5e51bd8) | replay force-null, lane l00 only, workers 4, attempts recorded | xerox c3-cmy7 | **333 certs = the full run's l00 exactly**; the §4.5.1 margin reference; wall 227 s / CPU 553 s | runs/xerox-c3-cmy7-replay-l00-null-forcenull.json |
| 2026-08-07 | pk31 (4e60e1c tree) | replay LIVE, lane l00 only, workers 4, attempts recorded | xerox c3-cmy7 | **333 certs, address set IDENTICAL to the null arm (0 gained / 0 lost) and all 1,305 attempt records identical**; head refused `saturation_below_floor` on a measured pre-head saturation .131; §4.5.2 acceptance (b). Timings not comparable (two other heavy jobs): wall 319 s / CPU 741 s | runs/xerox-c3-cmy7-replay-pk31-l00.json |
| 2026-08-07 | pk31 (4e60e1c tree) | replay force-null, workers 4 | xerox c2-cmy7 | **LOST — process reaped by the runner's background-task manager at lane 8/12 after ~4 h; no JSON.** Not a decode fault; the intended product (the 12-lane pre-head saturation table) is still owed | logs/pk31-xerox-c2-cmy7-forcenull.log |
| 2026-08-07 | pk31 (4e60e1c tree) | replay LIVE, lane l00 only, workers 4 | xerox c2-cmy7 | **2 certs = the archived l00 exactly**; head fitted, furniture gate PASSED, refused `saturation_below_floor` at a pre-head saturation of **.0497**; §4.5.2 acceptance (c), PARTIAL (1 of 12 lanes). Contended: wall 723 s / CPU 1,876 s / 10.8 GiB | runs/xerox-c2-cmy7-replay-pk31-l00.json |
| 2026-08-08 | pk4 (e4150a9 tree + PK4 diff) | replay force-null, workers 4, lanes l00+l01 | hp c3-cmy8 | **494 certs (C 467 / M 27) = the archived l00+l01 exactly** — the sweep's reference; 500 s wall / 1,177 s CPU / 9.0 GiB | runs/hp-c3-cmy8-l0001-pk4-forcenull.json |
| 2026-08-08 | pk4 (same tree) | replay LIVE ×9, workers 4, lanes l00+l01, `--window-phot` | hp c3-cmy8 | **the A3 constants sweep** (§5.2): nets +17/+15/+12 (halo .25), +9/+11/+7 (halo .5), +4/+6/+7 (halo 1.0); halo axis monotone, l00 an exact null at every point | runs/hp-c3-cmy8-l0001-pk4-h{0.25,0.5,1.0}p{20,40,80}.json |
| 2026-08-08 | pk4 (same tree) | replay LIVE, workers 4, lanes l00+l01, out-of-grid DIAGNOSTIC | hp c3-cmy8 | **halo 0.0 (own window only) = +27**, beyond every pre-registered point — the halo is a net harm on this capture (§5.3); reported, NOT adopted | runs/hp-c3-cmy8-l0001-pk4-h0.0p20.json |
| 2026-08-08 | pk4 (same tree) | replay force-null, workers 4, close | xerox c3-cmy7 | **720/720 cert-ID identical** (missing 0, extra 0); wrong-cert 0/8,588,160 (agreement 1.0); re-close VERIFIED 301,600 B; 1,143 s wall / 2,326 s CPU / 13.0 GiB | runs/xerox-c3-cmy7-replay-pk4-forcenull.json, runs/score-… |
| 2026-08-08 | pk4 (same tree) | replay LIVE, workers 4, close | xerox c3-cmy7 | **736 certs but the BAR FAILS: 5 addresses LOST vs PK3.1's 734** (7 gained, net +2) and 2 lost vs the archived 720, so the set is no longer a superset; l00 **329 vs 333 with the head OFF in both arms** = A3 alone; A3 also lowers pre-head saturation in every lane and flips m01's head to `saturation_below_floor` (§5.6); wrong-cert 0/8,779,008 (agreement 1.0); close VERIFIED 301,600 B | runs/xerox-c3-cmy7-replay-pk4.json, runs/score-… |
| 2026-08-08 | pk4 (same tree) | replay LIVE, workers 4, close | hp c3-cmy8 | **THE B3 DATUM: 709 certs, C 620 → 667 (+47), M 43 → 42, Y 0**; 54 gained / 8 lost = net +46; wrong-cert 0/2,818,984 (agreement 1.0); close still OPEN (dead Y); 2,928 s wall / 6,713 s CPU / **45.6 GiB peak (vs PK3's 34.1)** | runs/hp-c3-cmy8-replay-pk4.json, runs/score-… |
| 2026-08-08 | pk4 (same tree) | replay LIVE, workers 4, close | xerox c2-cmy8 | **B1 HOLDS: close VERIFIED 718,413 B byte-exact** (sha matches emitted payload and archived recovered.bin); 5,366 certs vs 5,370 (22 extra / 26 missing, net −4, all in Y); wrong-cert 0/21,295,456 (agreement 1.0); 2,530 s wall / 4,063 s CPU / **46.2 GiB peak (vs PK3's 33.7)** | runs/xerox-c2-cmy8-replay-pk4.json, runs/score-… |
| 2026-08-07 | pk31 (4e60e1c tree) | replay LIVE, workers 4, close | xerox c3-cmy7 | **734 certs = +14 addresses, ZERO lost** (strict superset of the archived 720: missing 0, extra 14); wrong-cert **0 / 8,755,152 (agreement 1.0)**; re-close **VERIFIED 301,600 B** (sha matches the emitted payload and the archived recovered.bin); head OFF in l00/m00/r00 (`saturation_below_floor` at .131/.225/.141), adopted in the other nine at 1/a 1.20–1.44; §4.5.2 acceptance (a). Timings contended, not a cost measurement: wall 1,321 s / CPU 2,644 s / 13.3 GiB | runs/xerox-c3-cmy7-replay-pk31.json, runs/score-pk31-xerox-c3-cmy7.json |
| 2026-08-08 | pk41 (e4150a9 tree + PK4 diff + PK4.1 diff) | replay LIVE, workers 4, dispersion floor 0.0 | xerox c3-cmy7 | **the HARVEST** (§6.2): 732 certs = 14 gained / 2 lost vs the 720 null and −2 vs PK3.1's 734; per-lane gain dispersion 0.0164–0.0741 with the DAMAGED l00 highest and the two best-gaining lanes lowest; 4 windows pooled a halo (m00, the corpus's first starvation); 1,007 s wall / 2,086 s CPU / 13.0 GiB | runs/xerox-c3-cmy7-replay-pk41-harvest.json |
| 2026-08-08 | pk41 (same tree) | replay LIVE, workers 4, lanes l00+l01, dispersion floor 0.0 | hp c3-cmy8 | **521 certs (C 494 / M 27) = +27 vs the 494 force-null reference** — the adaptive halo reproduces PK4's out-of-grid halo-0 diagnostic exactly and beats the frozen halo-0.25 point's +17; gain dispersion l00 0.0511 / **l01 0.0601**, i.e. BELOW the c3-cmy7 l00 damage lane's 0.0741 ⇒ **no dispersion floor can separate them** (§6.3); 368 s wall / 953 s CPU / 8.7 GiB | runs/hp-c3-cmy8-l0001-pk41-harvest.json |
| 2026-08-08 | pk41 (same tree) | replay LIVE, workers 4, close, dispersion floor 0.0 | xerox c2-cmy8 | **B1 HOLDS under A3-everywhere: close VERIFIED 718,413 B byte-exact**; 5,356 certs vs the archived 5,370 (C 1,775 / M 1,836 / Y 1,745) = −14 (PK4's halo lost 4); wrong-cert 0/21,295,456 (agreement 1.0); per-lane gain dispersion 0.0287–0.0990, i.e. this capture too sits ENTIRELY below the hp uplift lane's requirement; 8 lanes pooled 1–14 halo windows each; 2,609 s wall / 4,167 s CPU / **46.2 GiB peak — unchanged from PK4's 46.2**, because the P6 preview's own cost (2 QDA scorings over 3–4M certified cells per region) replaced the tuple saving; the preview is now bounded (§6.6) and the number is owed a re-measure | runs/xerox-c2-cmy8-replay-pk41-disp0.json |
| 2026-08-08 | pk41 (e4150a9 tree + PK4 + PK4.1 diffs) | replay force-null, workers 4, close | xerox c3-cmy7 | **720/720 cert-ID identical** (missing 0, extra 0); wrong-cert 0/8,588,160 (agreement 1.0); re-close **VERIFIED 301,600 B** vs both the emitted payload and the archived recovered.bin; 924 s wall / 2,035 s CPU / 12.9 GiB | runs/xerox-c3-cmy7-replay-pk41-forcenull.json, runs/score-… |
| 2026-08-08 | pk41 (same tree) | replay LIVE, workers 4, close, PARKED constants | xerox c3-cmy7 | **734 certs = PK3.1's ADDRESS SET EXACTLY (0 gained / 0 lost)** and a strict superset of the archived 720 (+14, 0 lost); every lane refuses A3 `photometric_dispersion_below_floor`; **l00 restored to 333**; wrong-cert 0/8,755,152 (agreement 1.0); close VERIFIED 301,600 B; 941 s wall / 1,976 s CPU / 12.8 GiB | runs/xerox-c3-cmy7-replay-pk41.json, runs/score-… |
| 2026-08-08 | pk41 (same tree) | replay LIVE, workers 4, close, dispersion floor 0.0 | hp c3-cmy8 | **THE PRIZE, MEASURED (not adopted): 725 certs, C 620 → 683, M 42, Y 0**; 73 gained (all C) / 11 lost = **net +62 addresses**, i.e. +35% on PK4's +46; per-lane dispersion **0.0511–0.0855 with the arm gaining across the whole range**, which is why no ceiling separates it from xerox c3-cmy7 l00's damaging 0.0741 either; l00 and r00 refuse at the standing three-way gate; wrong-cert 0/2,882,600 (agreement 1.0); close still OPEN (dead Y); 2,848 s wall / 6,600 s CPU / **45.5 GiB peak vs PK4's 45.6 — the tuple-ownership fix does not move the peak, and this capture has no P6 preview to blame** | runs/hp-c3-cmy8-replay-pk41-disp0.json, runs/score-… |
| 2026-08-08 | pk42 (7706ba7 tree + PK4.2 diff) | replay LIVE, workers 4, BOTH floors 0.0 | xerox c3-cmy7 | **THE NORMALIZED HARVEST** (§7.3): 732 certs, **certificate ADDRESS SET IDENTICAL to PK4.1's floor-0 harvest** — PK4.2 adds a statistic, not a different map. Per-lane normalized dispersion 2.27–37.63 with the damaged l00 at **3.26** (raw put it at the corpus MAXIMUM 0.0741) — the sampling inversion is FIXED within this capture; 1,029 s wall / 2,058 s CPU / 13.0 GiB | runs/xerox-c3-cmy7-replay-pk42-harvest.json |
| 2026-08-08 | pk42 (same tree) | replay LIVE, workers 4, BOTH floors 0.0 | hp c3-cmy8 | **THE COUNTER-EVIDENCE**: 725 certs (C 683 / M 42), address set IDENTICAL to PK4.1's floor-0 run, +73/−11 = **+62**; per-lane normalized dispersion **1.86–3.73 across all fifteen lanes**, i.e. the whole uplift target sits at/below xerox c3-cmy7's DAMAGED lane while gaining the campaign's largest uplift ⇒ **no floor exists** (refuse-all-harm needs >31.1, keep-all-help needs ≤2.09; §7.4). Confound measured: spearman(norm, labelled population) **+0.73** pooled; 2,845 s wall / 6,611 s CPU / 46.9 GiB | runs/hp-c3-cmy8-replay-pk42-harvest.json |
| 2026-08-08 | pk42 (same tree) | memtrace, ONE lane l04-24ppc-4800dpi, workers 4 ×2 | hp c3-cmy8 | **THE MEMORY ANSWER** (§7.7): force-null **41,097 MiB** vs A3-adopting **41,091 MiB** — 0.01% apart, so **A3 does not set the peak**; one lane exceeds PK3's whole-capture 34.1 GiB, and PK3's cmy8 baselines ran inside a concurrent 34 GiB control-price decode. PK4's "+34% from A3" is RETRACTED as a contention artifact | runs/hp-c3-cmy8-memtrace-{null,a3}.json |
| 2026-08-08 | pk42 (same tree) | replay force-null, workers 4, close | xerox c3-cmy7 | **720/720 cert-ID identical** (missing 0, extra 0); wrong-cert 0/8,588,160 (agreement 1.0); re-close **VERIFIED 301,600 B** against both the emitted payload and the archived recovered.bin; 977 s wall | runs/xerox-c3-cmy7-replay-pk42-forcenull.json, runs/score-… |
| 2026-08-08 | pk42 (same tree) | replay LIVE, workers 4, close, PARKED constants | xerox c3-cmy7 | **734 certs = PK4.1's / PK3.1's ADDRESS SET EXACTLY (0 gained / 0 lost)** and a strict superset of the archived 720 (+14, 0 missing); every lane still refuses A3 at the RAW floor, so the normalized statistic is never consulted; wrong-cert 0/8,755,152 (agreement 1.0); close VERIFIED 301,600 B; 1,121 s wall | runs/xerox-c3-cmy7-replay-pk42.json, runs/score-… |
| 2026-08-09 | pk5 (dd37d50 tree + PK5 diff) | library DUMP ×3, workers 4 | hp c3-cmy8 (l00+l01), xerox c3-cmy7 (all 12+2), xerox c2-cmy8 (l00+l01) | re-dumped at the PK5 tree because `color_payload` is a PRODUCER module and P2 edits it — every PK4.3-era library refuses by construction. 679 s / 1,589 s / 838 s wall. First library dump of a u-lane-bearing plan crashed the REPORTER (archived-level index out of range) — fixed, the u-lane's archived count is `null` exactly as `ab_runner` already spelled it | feature-library/*/index.json, runs/*-libdump-pk5dump.json |
| 2026-08-09 | pk5 (same tree) | library ×9, lane l00 only, workers 2 | hp c3-cmy8, xerox c3-cmy7, xerox c2-cmy8 | **THE HEAD-TO-HEAD** (§11.2): the per-plane PORT is bit-identical to the arm OFF on all three (179 / 333 / 3,596), refusing at the region gate on the DUST leg every time; the MATRIX adopts on all three and reads **251 / 413 / 4,006** (+72 / +80 / +410). Wrong certs 0/997,976 on the audited hp unit | runs/*-library-pk5l00-{off,planes,matrix}.json |
| 2026-08-09 | pk5 (same tree) | replay force-null, workers 4, close, diag | xerox c3-cmy7 | **720/720, every lane identical to the archive**; no `color.context.*` key anywhere; u-lanes 0.0 s; wrong-cert 0/8,588,160; close VERIFIED 301,600 B; 893 s wall / 1,973 s CPU / 13.2 GiB | runs/xerox-c3-cmy7-replay-pk5-forcenull-forcenull.json, runs/score-pk5-… |
| 2026-08-09 | pk5 (same tree) | replay LIVE matrix, workers 4, close, diag | xerox c3-cmy7 | **771 certs = +39 / −2 vs PK4.3's 734** (+53 / −2 vs the force-null 720); close VERIFIED; wrong-cert 0/9,196,488; l00 333 → **413**; two lanes refuse on a dust leg moving +.0003/+.0007; 962 s wall / **1,804 s CPU (−8.6% vs its own null)** | runs/xerox-c3-cmy7-replay-pk5-matrix.json, runs/delta-pk5-xerox-c3-cmy7.json |
| 2026-08-09 | pk5 (same tree) | replay LIVE port, workers 4, close, diag | xerox c3-cmy7 | **772 certs = +40 / −3 vs PK4.3** — the two arms land 770 addresses in common, 1 matrix-only, 2 port-only; the port takes NOTHING at l00 (333, `region_gate_failed`) and +88 at l01; close VERIFIED; wrong-cert 0/9,208,416; 1,039 s wall / 1,955 s CPU | runs/xerox-c3-cmy7-replay-pk5-planes.json |
| 2026-08-09 | pk5 (same tree) | replay LIVE matrix, workers 4, close, diag | hp c3-cmy8 | **THE B3 DATUM: 796 certs, C 620 → 740, M 43 → 56, Y 0**; +127 / −1 = **net +126** vs PK4.3's 670; arm adopted in all 17 lanes (14–22 of 24 curves); wrong-cert 0/3,164,896; close still open (dead Y); 3,618 s wall / **7,949 s CPU (−5.3%)** / 42.0 GiB | runs/hp-c3-cmy8-replay-pk5-matrix.json, runs/delta-pk5-hp-c3-cmy8.json |
| 2026-08-09 | pk5 (same tree) | replay LIVE port, workers 4, close, diag | hp c3-cmy8 | **THE HEAD-TO-HEAD'S ANSWER: 670 certs, cert-for-cert PK4.3's, C 626 / M 44 — the port adopted in ZERO of seventeen lanes** and spent 8,648 s CPU (+3%) to refuse.  Contended with the scoring chain, so the CPU is indicative | runs/hp-c3-cmy8-replay-pk5-planes.json |
| 2026-08-09 | pk5 (same tree) | replay LIVE matrix, workers 4, close, diag | xerox c2-cmy8 | **B1 HOLDS: close VERIFIED 718,413 B byte-exact**; 5,465 certs (C 1801 / M 1867 / Y 1797) = +89 / −3 = net +86 vs PK4.3's 5,379; all 24 curves adopted in every lane; wrong-cert 0/21,728,840; 3,094 s wall / **4,608 s CPU (−7.1%)** / 42.2 GiB | runs/xerox-c2-cmy8-replay-pk5-matrix.json, runs/delta-pk5-xerox-c2-cmy8.json |
| 2026-08-09 | pk5 v2 (dd37d50 tree + PK5 diff + the u-off ruling) | replay LIVE matrix ×3, workers 4, close, diag | xerox c3-cmy7, hp c3-cmy8, xerox c2-cmy8 | **the EXTENDED plan** `[U(Ln,off), U(Ln,a3), U(Ln,a4b)]`: 771 / 796 / **5,466** (close VERIFIED 301,600 B and 718,413 B); wrong-cert **0 / 34,094,200** on the three; u-off lanes 0 / 0 / **3 certs (1 new)** at 108 / 686 / 392 s CPU and arms provably ABSENT in their diagnostics; five of six stranded addresses remain, split into a FOOTING mechanism (2, certified at 6 and 4 ppc) and a HISTORY mechanism (3, same footing, larger prior set) — §11.11 | runs/*-replay-pk5v2-matrix.json, runs/delta-pk5v2-*.json, runs/score-pk5v2-*.json |
| 2026-08-08 | pk-l (2d0ebc3 tree) | patch corpus | 10 specimens extracted+pinned | outside_domain 0, wrong 0, negative control 0 certs; l00-tax demo p=2.1e-5 | patch-runs/ |
| 2026-08-08 | pk-l (2d0ebc3 tree) | feature library | c3-cmy7 12 lanes + hp l00+l01 | fidelity EXACT (734 identical; +27 reproduced); RSS 4.5-5.5x down | runs/*library*.json |
| 2026-08-08 | pk10 (78eb0612 tree) | feature library DUMP ×3 | hp c3-cmy8 l00+l01, xerox c3-cmy7 12 lanes, xerox c2-cmy8 l00+l01 | re-dumped because PK10 edits `color_payload.py` and every library refuses on a producer change. 494 / **734** / 4,831 certs; 348.6 / 1358.0 / 1072.8 MiB; 387 / 981 / 605 s wall; all three tree-stable. The c3-cmy7 dump reproduces PK3.1's 734 set exactly = the first cmy7 no-op signal | runs/{hp-c3-cmy8,xerox-c3-cmy7,xerox-c2-cmy8}-libdump-pk10.json |
| 2026-08-08 | pk10 (78eb0612 tree) | library, l00+l01 | hp c3-cmy8 | **494 (C 467 / M 27) = the archived l00+l01 exactly.** l00 `no_conditioned_cells` (structural null); l01 `region_gate_failed` on the DUST leg while total .5030→.4870 and word .5149→.4938 improve; 7/9 strata; 27,681 cert + 15,915 masked cells; 1,914,924 arity-1 and 41,250 arity-2 marginals (§9.3/§9.5) | runs/hp-c3-cmy8-library-pk10sym.json |
| 2026-08-08 | pk10 (78eb0612 tree) | library, l00+l01 | xerox c2-cmy8 | **THE REFERENDUM NUMBER: l01 1,235 vs the archived 1,216 = +19 certified tiles**, region gate ADOPTED on all three legs (total .25182→.24590, word .25278→.24603, dust .24461→.24353), 8/9 strata; cert material hits the 400,000 cap; 7,908,674 arity-1 and 2,559,895 arity-2 marginals; l00 the structural null (3,596 = archived) | runs/xerox-c2-cmy8-library-pk10sym.json |
| 2026-08-08 | pk10 (78eb0612 tree) | library KILL TEST pair, seeded archived frontier, l00+l01 | hp c3-cmy8 | **0 new certificates in BOTH arms** (force-null and live), 5,813 attempts each — and the live arm never applied: `region_gate_failed` at both lanes on the DUST leg with total/word better by .015–.023 nats. Maximal conditioning raises l00's cert material to 89,246 cells and 8/9 strata still pass their own pre-gate (§9.4) | runs/hp-c3-cmy8-library-pk10-kill-{null,live}.json |
| 2026-08-08 | pk10 (78eb0612 tree) | library ×2, three-way PRE-GATE variant | hp c3-cmy8, xerox c2-cmy8 | **BUILT, MEASURED, NOT ADOPTED** (§9.7): hp flips to `adopted` on all three legs but worth 0 certificates (2/9 strata); xerox keeps 2/9 strata and +11 instead of +19. The per-stratum legs it published localise the dust cost to exactly the cert-cross-fed strata (§9.6) — R12 measured | runs/{hp-c3-cmy8,xerox-c2-cmy8}-library-pk10-3way.json |
| 2026-08-08 | pk10 (2da6a817 arm, pre-diagnostic tree) | replay force-null, workers 4, close | xerox c3-cmy7 | **720/720 cert-ID identical** (missing 0, extra 0); wrong-cert 0/8,588,160 (agreement 1.0); re-close **VERIFIED 301,600 B**; 1,170 s wall / 2,450 s CPU / 13.3 GiB | runs/xerox-c3-cmy7-replay-pk10-forcenull.json, runs/score-… |
| 2026-08-08 | pk10 (same) | replay LIVE, workers 4, close | xerox c3-cmy7 | **734 certs, certificate-ID set IDENTICAL to PK4.2's 734** and a strict superset of the archived 720 (+14, 0 missing) — A4b's cmy7 no-op PROVEN on paper, not only by construction; zero `color.conditioning.*` keys on all 12 lanes; wrong-cert 0/8,755,152; close VERIFIED 301,600 B; 1,056 s wall / 2,146 s CPU | runs/xerox-c3-cmy7-replay-pk10.json, runs/score-… |
| 2026-08-08 | pk10 (78eb0612 tree) | patch compare, 10 specimens | specimen corpus | **all 10 IDENTICAL** — 0 moved, 0 with losses, 0 wrong certificates, every run tree-stable. A4b is a no-op at patch scale by construction (a scrap's lane 0 has no priors and its later lanes few certified siblings), which is the correct non-regression outcome; the pin key moved with the policy token and the compare said so loudly. Re-pinning is owed at merge | logs/pk10-patch-compare.log |
| 2026-08-08 | pk10 (78eb0612 tree) | replay LIVE, workers 4, close | hp c3-cmy8 | **THE M NUMBER: 663 certs, C 620 / M 43 — certificate-for-certificate IDENTICAL to the archived set.** Bar M>43 NOT met; A4b refused at the region gate on all fourteen conditioned lanes (7–8 of 9 strata passing their own pre-gate each time, up to 7.2 M conditioned marginals per lane) so the arm is an exact end-to-end null here; wrong-cert 0/2,636,088 (agreement 1.0); close still OPEN (dead Y); 3,120 s wall / 7,046 s CPU / 42.6 GiB (contended) | runs/hp-c3-cmy8-replay-pk10.json, runs/score-pk10-hp-c3-cmy8.json |
| 2026-08-08 | pk10 (78eb0612 tree) | replay LIVE, workers 4, close | xerox c2-cmy8 | **B1 HOLDS but the ARM DOES NOT: close VERIFIED 718,413 B byte-exact**, wrong-cert 0/21,331,240 (agreement 1.0) — and at the ADDRESS level **5 gained / 10 lost = net −5** (losses concentrated at l03-16ppc-4800dpi: 9). The library tier's +19 at l01 is reproduced exactly and decomposes into 1 new address + 18 re-timings; 50 addresses re-timed overall. 2,532 s wall / 4,057 s CPU / 41.1 GiB | runs/xerox-c2-cmy8-replay-pk10.json, runs/score-pk10-xerox-c2-cmy8.json |
| 2026-08-08 | pk10 (78eb0612 tree) | fountain probe over the ARCHIVED frontier | xerox c2-cmy8 | **the capture already closes VERIFIED at l00, its FIRST barrier** (3,596 certs) — and l00 is exactly where A4b is a structural null, so conditioning cannot shorten lanes-to-close on this corpus. Under the 2026-08-08 yield ruling the cost metric is saturated and only certified tiles move | (analysis, §9.5) |
| 2026-08-08 | pk10-parked (a7d347e6 tree) | THE PARK (lead ruling) | — | `CONDITIONING_PARKED = True` short-circuits A4b before the arity census, the gather and every fit; token gains the GENERATED `parked0`; three new pins (parked ≡ arm-never-built byte-for-byte on a capture where the unparked arm adopts; neither census nor fitter called; token digit tracks the constant). Suite **1,133 passed / 37 skipped**, 1,170 collected, backbone 3/3 | src/holo/receive/color_conditioning.py, color_policy.py, tests/holo/test_color_conditioning.py |
| 2026-08-08 | pk43 (73cc0205 tree) | replay force-null, workers 4, close | xerox c3-cmy7 | **720/720 cert-ID identical** (missing 0, extra 0); wrong-cert 0/8,588,160 (agreement 1.0); re-close **VERIFIED 301,600 B** vs both the emitted payload and the archived recovered.bin; **both u-lanes cost 0.0 s wall / 0.0 s CPU and emit not one event** — force-null does not attempt them at all; 876 s wall / 1,957 s CPU / 13.1 GiB | runs/xerox-c3-cmy7-replay-pk43-forcenull.json, runs/score-pk43-… |
| 2026-08-08 | pk43 (same tree) | replay LIVE, workers 4, close | xerox c3-cmy7 | **THE STRUCTURAL-MONOTONICITY PROOF: 734 certs, address set IDENTICAL to PK10's (0 gained / 0 lost)** and a strict superset of the archived 720; **u-a3 ran the arm on the residue — floors 0, 77/137 windows mapped, region gate adopted, 98 blocks / 185 attempts — and added ZERO**, so PK4's "+7" on this capture was re-decodes of tiles the ladder already wins, not residue conversions; u-a4b is the cmy7 no-op (no `color.conditioning.*` key); wrong-cert 0/8,755,152; close VERIFIED 301,600 B; 1,060 s wall / 2,248 s CPU (u-lanes 141 s / 288 s) | runs/xerox-c3-cmy7-replay-pk43.json, runs/delta-pk43-xerox-c3-cmy7.json |
| 2026-08-08 | pk43 (same tree) | replay LIVE, workers 4, close | hp c3-cmy8 | **THE UPLIFT NUMBERS: 670 certs, C 620 → 626, M 43 → 44, Y 0; +7 gained / 0 LOST** (standard lanes reproduce the archived 663 cert-for-cert, so the whole delta is the tail). `u04-a3` +6 C (798 blocks, 3,269 attempts, A3 adopted at floors 0); `u04-a4b` **+1 M under `region_gate_forced`** — 7/9 strata, 6,324,708 arity-1 + 176,666 arity-2 marginals, dust leg still regressing .4487→.4567 = **P9's final answer, M is not conditioning-limited**; wrong-cert 0/2,663,920 (agreement 1.0); close still OPEN (dead Y); 3,714 s wall / 8,396 s CPU / 43.1 GiB (u-lanes 703 s / 1,489 s) | runs/hp-c3-cmy8-replay-pk43.json, runs/delta-pk43-hp-c3-cmy8.json |
| 2026-08-08 | pk43 (same tree) | replay LIVE, workers 4, close | xerox c2-cmy8 | **B1 HOLDS AND THE ARM ADDS: close VERIFIED 718,413 B byte-exact**; 5,379 certs (C 1,777 / M 1,841 / Y 1,761) = **+9 gained / 0 lost** vs the archived 5,370; u-a3 +7 (M 2, Y 5), u-a4b +2 (C 1, Y 1) under `region_gate_forced` with 6/9 strata; every u-lane certificate is a NEW address (`re_timed` 0); wrong-cert 0/21,386,904 (agreement 1.0); 3,101 s wall / 4,959 s CPU / 43.4 GiB (u-lanes 607 s / 924 s) | runs/xerox-c2-cmy8-replay-pk43.json, runs/delta-pk43-xerox-c2-cmy8.json |
| 2026-08-09 | pkclean (2dcec192 tree) | replay force-null, workers 4, close | xerox c3-cmy7 | **720/720 cert-ID identical** (missing 0, extra 0); wrong-cert 0/8,588,160 (agreement 1.0); re-close **VERIFIED 301,600 B** vs both the emitted payload and the archived recovered.bin; **the cmy7 plan now schedules TWO u-lanes, not three** (`u03-off`, `u03-a3`), both at 0.0 s under force-null; 916 s wall / 2,015 s CPU / 13.0 GiB | runs/xerox-c3-cmy7-replay-pkclean-forcenull.json, runs/score-pkclean-… |
| 2026-08-09 | pkclean (same tree) | replay LIVE, workers 4, close | xerox c3-cmy7 | **771 certs, certificate-ID set IDENTICAL to PK5's 771** (0 gained / 0 lost) and every standard lane exact; wrong-cert 0/9,196,488; close VERIFIED 301,600 B; **1,820 s CPU against its own force-null's 2,015 and PK5's 1,908 (−4.6%)** — the standard ladder no longer fits window maps, and the dead cmy7 u-a4b lane (121.9 s CPU for 0 certificates in PK5) is gone; 959 s wall / 13.3 GiB | runs/xerox-c3-cmy7-replay-pkclean.json, runs/delta-…, runs/score-… |
| 2026-08-09 | pkclean (same tree) | replay LIVE, workers 4, close | hp c3-cmy8 | **796 certs = C 740 / M 56, certificate-ID set IDENTICAL to PK5's 796**; every standard lane exact and u-lane certs 0 / 2 / 0 lane for lane; wrong-cert 0/3,164,896 (agreement 1.0); close still open (dead Y); 4,127 s wall / 8,889 s CPU / 41.9 GiB (cross-epoch, shared machine) | runs/hp-c3-cmy8-replay-pkclean.json, runs/score-pkclean-hp-c3-cmy8.json |
| 2026-08-09 | pkclean (same tree) | replay LIVE, workers 4, close, **diag** | xerox c2-cmy8 | **B1 HOLDS: close VERIFIED 718,413 B byte-exact**; **5,466 certs, certificate-ID set IDENTICAL to PK5's 5,466** (C 1,802 / M 1,867 / Y 1,797), every standard lane exact and u-lane certs 3 / 1 / 2 lane for lane; wrong-cert 0/21,732,816 (agreement 1.0); 3,308 s wall / 4,946 s CPU / 41.7 GiB. Ran with the live viewer on localhost:8023 | runs/xerox-c2-cmy8-replay-pkclean.json, runs/score-pkclean-xerox-c2-cmy8.json |
| 2026-08-09 | pkclean (same tree) | patch compare, 10 specimens | specimen corpus | **5 moved, 0 with losses, 0 wrong certificates**, agreement 1.0, tree-stable throughout — and the five movers reproduce PK5's §11.8 table specimen for specimen (+1/+6/+1/+3/+5 = +16), so this tier too shows PK-CLEAN moving nothing. The pin fallback fired loudly on every specimen (policy key 2a350d17bc0b9766 → a765f290bce6c978); **re-pinning owed at merge** | logs/pkclean-tail.log |
| 2026-08-09 | pkclean (attempt 3) | VOID | hp c3-cmy8 | **REAPED by the harness background-task manager at ~50 min**, mid-run at lane m04 — the PK3.1 failure mode again. No number from it is quoted; the run was relaunched detached (`nohup`) and completed. ~35 min lost (§12.5) | logs (superseded) |
| 2026-08-08 | pk43 (same tree) | patch compare, 10 specimens | specimen corpus | **all 10 IDENTICAL** — 0 moved, 0 with losses, 0 wrong certificates, every run tree-stable; both u-lanes ran on every specimen and added 0 (a scrap's finest rung carries almost no prior frontier). The pin key moved with the policy token and the compare said so loudly; re-pinning owed at merge | logs/pk43-patch-compare.log |
| 2026-08-08 | pk43 (same tree) | VOID | xerox c3-cmy7 | **VOIDED BY THE §8.5 LAW, and re-run**: a source edit during the run moved `src/holo`'s content hash between the entry and exit fingerprints and the runner refused the result. Recorded because the law caught its first self-inflicted case; no number from it is quoted | logs (superseded) |
