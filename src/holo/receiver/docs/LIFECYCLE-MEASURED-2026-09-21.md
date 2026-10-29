# LIFECYCLE — the acceptance measurements, in full

Companion to `LIFECYCLE-2026-09-21.md` §5, which carries the findings.
This file carries the numbers they were read off, so the record's own
section can stay short. Base `840a97ca`, branch `sched-lifecycle` at
`4a8fa834`; measured 2026-09-21 on machine 1, free-threaded CPython 3.14.7
(`gil_enabled: false` in every trace), machine idle before every real
run (`ps` clean of `decode`/`analyzer`), never two decodes at once.

The reducer is `measure/sched_trace/report.py` for the narrative tables
and a scratch joiner for the cross-arm ones; every raw trace is under
its run dir's `sched-trace/`.

## 1. The sims — eight decodes, four A/B pairs

`HOLO3_SCHED_TRACE=1`, one capture each, from scratch. Stimuli from the
receiver's own fixture cache (`sim-k-1200dpi.tiff` at
`c3-k-r0550@7x7`, `sim-color-1200dpi.tiff` at
`c3-cmy8-r0550x0550x0547@10x10`). Run dirs:
`<scratchpad>/measure/sims/{base,branch}-{k,color}-w{1,4}`.

| | K w1 | K w4 | colour w1 | colour w4 |
|---|---|---|---|---|
| payload sha, both trees | 59495601… | 59495601… | ddf7aceb… | ddf7aceb… |
| close, both trees | VERIFIED | VERIFIED | VERIFIED | VERIFIED |
| jobs base → branch | 219 → 219 | 146 → 148 | 101 → 101 | 73 → 64 |
| certificates | 48 → 48 | 49 → 49 | 81 → 81 | 81 → 81 |
| job cpu_s | 9.8 → 9.9 | 21.6 → 21.7 | 18.5 → 18.6 | 66.5 → 66.1 |
| wakes | 1,247 → 1,005 | 1,078 → 891 | 2,167 → 1,875 | 936 → 667 |
| subscriptions | 1,240 → 596 | 1,202 → 662 | 4,367 → 2,575 | 1,346 → 1,222 |
| keys | 114 → 96 | 117 → 97 | 213 → 345 | 191 → 232 |
| bookmarks | 159 → 143 | 156 → 141 | 240 → 186 | 144 → 97 |

At one worker the schedule is deterministic and the two trees are
job-for-job identical; at four it differs by the ordinary race. The w1
column reproduces stage 2's recorded table to the unit.

Wakes to the residue rows, colour w1: `tiles.local` 439 → 171,
`tiles.planek` 439 → 420, `tiles.swim` 439 → 420, `revisit` 30 → **0**,
`tiles.retry` 0 → 19 (it has a key of its own now). `lane_poses` wakes
K 64 → 0, colour 42 → 12 (only `tiles.uplift` keeps that read).

**What the sims cannot show.** `tiles.local` fires ZERO times on every
sim arm on both trees, so the sibling fit is not exhibited here at all;
and same-cut repeats are unchanged in count (K w1 28 → 28, colour w1
20 → 20), though the only arm where base decoded a cut CONCURRENTLY
with itself — K w4, 4 such repeats — reads 0 on the branch.

## 2. Sheet H — the bounded A/B

`scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-2400dpi-a.tiff`,
`--dpi 2400 --format L:c2-cmy8-r0850-p120-x1@3392x2368 --max-pages 1
--workers 12 --snapshot-every 0`, `HOLO3_SCHED_TRACE=1
HOLO3_SCHED_TRACE_EVERY_S=120`, ONE SIGINT at 480 s.
Base `scratch/lifecycle-20260921/H-base.50441` (started 00:14:04, stop
at 484.9 s), branch `H-branch.50857` (00:22:22, 485.2 s).

### 2.1 Wakes by key kind

| kind | base | branch |
|---|---|---|
| lane_poses | 4,849,180 | 3,702 |
| tile | 1,017,591 | 703,748 |
| color_row | 133,687 | 22,081 |
| plane_field | 90,990 | 63,616 |
| pose_affine | 31,911 | 27,408 |
| page_certs | 21,420 | 21,180 |
| lattice_seed | 5,940 | 5,260 |
| pose_route | 1,225 | 915 |
| attempt | — | 185,569 |
| place_stage | — | 4,650 |
| **total** | **6,151,946** | **1,038,131** |

### 2.2 Wakes by row

`tiles.swim` 5,231,316 → 384,651 · `tiles.local` 401,341 → 181,431 ·
`tiles.planek` 376,214 → 360,178 · `place` 36,582 → 22,276 ·
`tiles.retry` 27,621 → 27,541 · `tiles.scan` 22,106 → 22,081 ·
`refine.color` 15,855 → 15,062 · `tiles.uplift` 15,352 → 14,556 ·
`revisit` 14,442 → 0 · `color` 7,704 → 7,299 · `fields.collect`
3,411 → 3,054.

### 2.3 Subscriptions (keys, subscriptions, worst fan-out)

| kind | base | branch |
|---|---|---|
| tile | 5,883 / 2,971,896 / 1,080 | 5,883 / 1,774,413 / 657 |
| plane_field | 3 / 90,483 / 30,161 | 3 / 46,893 / 16,670 |
| color_row | 712 / 117,923 / 260 | 712 / 10,973 / 20 |
| lane_poses | 3 / 12,980 / **5,880** | 3 / 12 / 4 |
| pose_affine | 990 / 24,490 / 27 | 990 / 49,838 / 122 |
| lattice_seed | 3 / 990 / 330 | 3 / 278 / 274 |
| live_pages | 1 / 990 / 990 | 1 / 278 / 278 |
| attempt | — | 65,188 / 140,670 / **4** |
| place_stage | — | 278 / 278 / 1 |
| **total** | 8,312 / 3,220,478 | 73,778 / 2,024,359 |

`pose_affine` is the one that grew: `tiles.planek` and `tiles.swim`
sample through those poses and now say so, which is the trade the
`lane_poses` hub was hiding.

### 2.4 Main thread, exclusive categories (seconds)

| category | base | branch |
|---|---|---|
| wait | 279.10 | 275.63 |
| fill | 128.29 | 93.23 |
| push | 22.66 | **67.64** |
| fold | 23.36 | 22.52 |
| intake | 10.01 | 10.20 |
| touch | 9.49 | 1.91 |
| snapshot | 5.22 | 4.96 |
| births | 4.53 | 6.98 |
| merge / operator / stat / close / other | 2.21 | 2.15 |
| **busy** | **195.8** | **199.4** |

### 2.5 Descriptor callbacks (calls / cpu_s)

| row | callback | base | branch |
|---|---|---|---|
| place | stage | 45,358 / 13.81 | 24,316 / 10.31 |
| place | retire | 4,773 / 36.73 | 25,028 / **56.75** |
| place | prepare | 4,773 / 6.05 | 3,939 / 5.24 |
| tiles.swim | stage + cost | 5,244,026 / 0.32 + 5,244,046 / 4.27 | 392,815 / 0.03 + 392,834 / 0.35 |
| tiles.local | reads | 25,380 / 0.48 | 50,535 / 1.02 |
| tiles.local | stage + cost | 414,405 / 0.03 + 414,862 / 0.37 | 185,520 / 0.02 + 185,563 / 0.20 |
| tiles.retry | prepare | 23,343 / 50.05 | 25,106 / 56.34 |
| tiles.scan | prepare | 11,284 / 22.94 | 11,719 / 23.61 |
| revisit | reads | 595,476 / 0.30 | — (deleted) |

### 2.6 Retirement

base: `place-ladder.jsonl` carries **no retire row at all** — 0 windows
retired in 480 s, as the 36-minute trace found — and 2,326 tile rows
retired at the pop (`tiles.retry` 2,037, `tiles.local` 170,
`tiles.scan` 119).
branch: **712 windows**, every one `placed`, all at the PUSH; plus
11,385 tile rows `certified` (planek 4,545 and swim 4,545 at the push,
retry 2,070 and scan 33 at the pop, local 180 at the push). 12,097 in
all, against 2,326. Frontier at the stop 39,069 → 30,793; max frontier
54,733 → 38,258.
NEITHER arm produced a `done_covered` or an `exhausted`, so the
question of whether the non-monotone done projection retires a window
on a transient is UNANSWERED by this run; what it did answer is the
price, `place.retire` 36.7 → 56.8 cpu-s.

### 2.7 Redundant decoding

Bare input digest joined on the tile-lane (stream aware):

*Dated note 2026-10-18 (SCHED-LIFECYCLE-REVIEW-2026-10-17 §4): the
caption above is WRONG; the numbers below stand. The join is
STREAM-BLIND: `measure/sched_trace/report.py` (`_shared_inputs`)
groups fires on `input_digest_bare`, the assembled cut alone, which
carries no stream. So the `tiles.retry` → `tiles.retry` repeats are
SIBLING-STREAM pairs (two streams of one tile retried on one cut) and
not a stream re-decoding itself: re-joined per subject on 2026-10-17,
0 same-subject pairs of 15,955.*

| | base | branch |
|---|---|---|
| repeat fires | 23,712 | 25,599 |
| cpu in the repeats | 2,418.3 s | 2,768.6 s |
| of them CONCURRENT | 17,239 | 15,515 |
| `tiles.retry` → `tiles.scan` | 4,268 | **442** |
| `tiles.scan` → `tiles.retry` | 4,667 | 9,590 |
| `tiles.retry` → `tiles.retry` | 14,707 | 15,516 |
| `tiles.scan` → `tiles.scan` | 70 | 51 |

The trace's own per-subject `redundant_fires` (this subject decoded
this exact input before): base `tiles.scan` 443 / 54.3 s and nothing
else; branch `tiles.retry` 1,315 / 141.1 s and `tiles.scan` 493 /
62.1 s.

### 2.8 Yield and attribution

certificates by minting row — base `tiles.retry` 2,036, `tiles.scan`
79, `tiles.local` 26, `tiles.swim` 1; branch `tiles.scan` 2,070,
`tiles.retry` 42, `tiles.local` 5, `tiles.swim` 1.
zero-yield fires — `tiles.retry` base 21,307/23,343 (91 %, 2,256 cpu-s)
against branch 25,064/25,106 (99.8 %, 2,705 cpu-s); `tiles.local` base
421/447 against branch 38/43.

The certificate trajectory, from `timeline.jsonl` at matched walls:

| wall | base | branch |
|---|---|---|
| 240 s | 0 | 0 |
| 300 s | 532 | 164 |
| 360 s | 1,894 | 1,780 |
| 420 s | 2,118 | 2,114 |
| 480 s | 2,142 | 2,118 |

Nothing certifies before ~290 s on this capture (the colour head has to
land first), so the bound lands on a steep front: the arms are 4 apart
at 420 s and 24 apart at 480 s. The campaign's run-to-run noise band at
this bound was measured at 5–7 certificates on a FLAT stretch; on this
front it is much wider, and this A/B cannot separate the two trees on
yield. Sheet I is the yield yardstick.

### 2.9 Sibling head fits

base: 447 `tiles.local` fires over 180 (tile, ppc) lanes; **152 lanes
fired for more than one stream**; 219.6 cpu-s went into fires after the
first of their lane.
branch: 43 fires over 29 lanes; **0 lanes with more than one stream** —
the stream is no longer in the subject — and 10.0 cpu-s after the
first. cpu per fire 0.801 → 0.804 s: the head fit costs what it always
did, and it happens a tenth as often.

## 3. Sheet I — the canary to close

`scratch/xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi.tiff`,
`--dpi 2400 --format L:c2-cmy8-r0700-p120-x1@3392x2368 --max-pages 1
--workers 12 --snapshot-every 20`, no trace, each arm launched detached
(fork → `setsid` → `execve`, log to a file) and polled. The yardstick
is main's page-field receiver on this capture: 5,861 certificates,
payload sha `2445b95d…` (e034/e037's emission).

**BOTH ARMS CLOSED, VERIFIED, WITH THE EMISSION'S SHA**
`2445b95db5b49bf3…`, 1,798,761 bytes, on the first pass, no resume.
Base `scratch/lifecycle-20260921/I-base.51123` (00:30:44 → 01:04:09),
branch `I-branch.52339` (01:04:30 → 01:37:32).

| | base | branch |
|---|---|---|
| close | VERIFIED `2445b95d…` | VERIFIED `2445b95d…` |
| certificates (C / M / Y) | 5,279 (1,911 / 1,953 / 1,415) | 5,277 (1,913 / 1,949 / 1,415) |
| wall | 2,005 s | 1,982 s |
| **job cpu** | **22,334.6 s** | **18,980.8 s (−15.0 %)** |
| jobs | 46,044 | 48,091 |
| attempts per subject 1 / 2 / 3-5 / 6-10 / >10 | 10,022 / 7,662 / 2,269 / 878 / 434 | 7,681 / 9,088 / 3,804 / 860 / 236 |

Per row (jobs / cpu_s / certificates):

| row | base | branch |
|---|---|---|
| `tiles.local` | 8,989 / **17,429.8** / 770 | 6,809 / **13,599.8** / 700 |
| `tiles.retry` | 14,529 / 1,730.6 / 727 | 19,220 / 2,438.7 / 110 |
| `tiles.scan` | 12,111 / 836.8 / 3,782 | 13,487 / 1,051.8 / 4,467 |
| `refine.color` | 8,994 / 1,599.8 / 0 | 7,179 / 1,332.2 / 0 |
| `color` | 86 / 301.3 / 0 | 101 / 193.7 / 0 |
| `fields.collect` | 2 / 315.3 / 0 | 2 / 238.5 / 0 |
| `place` | 1,316 / 104.7 / 0 (973 poses) | 1,290 / 108.2 / 0 (973 poses) |
| `fields` | 2 / 7.3 | 2 / 9.2 |
| `revisit` | 14 / 0.3 / 0 | — (deleted) |
| `tiles.planek`, `tiles.swim` | never fired | never fired |

`tiles.local` is 78 % of this decode's CPU on base and 72 % on the
branch, and it is where the saving is: 2,180 fewer fires for 3,830
fewer cpu-s, at an unchanged 1.94 → 2.00 cpu-s per fire, for 70 fewer
certificates of its own — which `tiles.scan` more than returns
(3,782 → 4,467). The same close, 23 s sooner, for 3,354 cpu-s less.

M8's residue comparison is therefore only half available: `tiles.local`
is measured, and `tiles.planek`/`tiles.swim` never fired on either arm
of this capture, so nothing can be said about them from this run.

The place row shows the same NUMBER of poses (973) and word routes (11)
on both. Equal counts do not show identical placements — the windows
or their affines could differ at the same totals — and a pose-by-pose
comparison of the two snapshots was not made (re-review 2026-10-03).

## 4. The amendment's own A/B — pre `677a7171` vs post

§1–§3 above measured the STAGES against base `840a97ca`; those arms
predate §1a and its review, and the record's open item 9 said so. This
section closes it: PRE is `677a7171` (the branch tip the §1–§3 numbers
were read off, code-identical to `4a8fa834` — the two commits between
them touch only these documents), POST is the branch after §1a and §4c.
Measured 2026-09-21 on machine 1, same interpreter, machine `ps`-clean of
`decode`/`analyzer` before every arm, never two decodes at once. PRE
runs from a throwaway worktree (`git worktree add … 677a7171`), removed
after the reduction; the reducer is the stage-3 joiner plus a
certificates-by-minting-row and a fires-by-(row, stage) column.

### 4.1 The sims — eight decodes, four A/B pairs

Same stimuli, run dirs and command as §1, `HOLO3_SCHED_TRACE=1`, from
scratch, one capture.

**Every one of the eight closes VERIFIED with its emission's sha**
(K `59495601…` = `sim-k-payload.bin`, colour `ddf7aceb…` =
`sim-color-payload.bin`), as in §1.

| | K w1 | K w4 | colour w1 | colour w4 |
|---|---|---|---|---|
| payload sha, both trees | 59495601… | 59495601… | ddf7aceb… | ddf7aceb… |
| close, both trees | VERIFIED | VERIFIED | VERIFIED | VERIFIED |
| jobs pre → post | 219 → 219 | 149 → 143 | 101 → 101 | 74 → 80 |
| certificates | 48 → 48 | 49 → 49 | 81 → 81 | 78 → 81 |
| job cpu_s | 9.92 → 9.96 | 21.7 → 21.7 | 18.6 → 18.7 | 66.3 → 66.5 |
| wakes | 1,005 → 1,005 | 933 → 896 | 1,875 → 1,872 | 857 → 916 |
| keys | 96 → **89** | 100 → 73 | 345 → **297** | 234 → 259 |
| subscriptions | 596 → **314** | 682 → 380 | 2,575 → **2,440** | 1,285 → 1,342 |
| bookmarks | 143 → 143 | 141 → 142 | 186 → **174** | 117 → 126 |

**At one worker the two trees do the same work, job for job.** K w1 is
identical in every fire counter — `place` 55, `tiles.scan` 99,
`tiles.retry` 25, `calibrate` 29, `ctx` 10, `survey` 1 — in wakes by
every key kind, in certificates by minting row (`tiles.scan` 45,
`tiles.retry` 3) and in retire causes (`certified` 66, `placed` 10,
`done_covered` 6, `reach_exhausted` 8). Colour w1 is identical in every
fire counter (`place` 27, `tiles.scan` 50, `tiles.retry` 19, `color` 4)
and in certificates (`tiles.scan` 80, `tiles.retry` 1). The four-worker
arms differ by the ordinary race, in both directions — pre's colour w4
closed on the bare 78 symbols it needed, post's on 81.

**What moves at w1 is the READ-SET CENSUS, and it is the amendment.**
K w1 subscriptions halve, 596 → 314, all of it in the refine row's two
kinds: `evidence_fit` 10 keys / 172 subs → 10 / 31, `evidence_read`
10 / 162 → 3 / 21. Those are the keys `rederive_on` grew on every
`pose_affine` wake and that a birth-fixed read set never takes. Colour
w1 loses `place_settled` entirely (12 keys / 12 subscriptions → the
kind no longer exists) and `pose_affine` drops 72 keys / 899 subs →
48 / 812.

**The quartering is now LAZY, and the sims show its one visible
price.** Colour w1's 12 fewer bookmarks are 12 child windows that PRE
minted inside the fold and POST does not mint: three parents are
SEATED at the `subdivide` rung (`place-ladder.jsonl`, 3 rows, against
0 on pre) and the verified close preempts all three, so the children
are never born. No `subdivide` rung FIRES in any of the eight arms, and
the K arms never subdivide at all. The unborn children changed nothing
else: `place` fires 27 → 27, ring 19 → 19, word_centre 8 → 8, and the
close is the same payload.

### 4.2 Sheet H — the bounded A/B, TWO arms per tree

Same command, capture, bound and trace cadence as §2
(`--max-pages 1 --workers 12 --snapshot-every 0`,
`HOLO3_SCHED_TRACE_EVERY_S=120`, ONE SIGINT at 480 s), run dirs
`scratch/lifecycle-20260921/amend-{pre,preb,post,postb}.<pid>`, arms
back to back, 02:52 → 03:27.

A second arm per tree was run because the first pair disagreed by 15
certificates — inside §2.8's own warning that this bound lands on a
steep front — and because §2's branch arm is PRE code and offers a
third pre-tree point.

| | pre-a | pre-b | post-a | post-b |
|---|---|---|---|---|
| certificates | 2,133 | 2,122 | **2,118** | **2,118** |
| C / M / Y | 577/1338/218 | 581/1328/213 | 575/1325/218 | 575/1325/218 |
| jobs | 40,665 | 40,580 | 41,269 | 41,151 |
| job cpu_s | 4,270.7 | 4,270.7 | 4,381.2 | 4,375.0 |
| wakes | 968,125 | 1,038,491 | 1,037,380 | 1,038,710 |
| keys | 73,713 | 73,771 | 73,778 | 73,778 |
| subscriptions | 2,017,902 | 2,022,423 | 2,024,322 | 2,024,322 |
| main thread busy_s | 215.1 | 209.4 | **201.3** | **201.2** |
| max frontier | 36,856 | 38,217 | 38,111 | 38,099 |
| windows retired `placed` | 712 | 712 | 712 | 712 |

**No `place_settled` key is minted on any sheet-H arm and no window
subdivides**, on either tree: 278 `place_stage` keys, 990 place births,
712 windows placed, four times over. This capture does not exercise the
quartering at all, which is why §4.1's sim is the only place it appears.

#### 4.2.1 The bound does not separate the trees on yield

`timeline.jsonl` at matched wall:

| wall | pre-a | pre-b | post-a | post-b |
|---|---|---|---|---|
| 180 s | 249 | 18 | 0 | 0 |
| 240 s | 581 | 18 | 0 | 0 |
| 300 s | 697 | 175 | 165 | 166 |
| 360 s | 1,831 | 1,783 | 1,780 | 1,780 |
| 420 s | 2,133 | 2,122 | 2,114 | 2,117 |
| 480 s | 2,133 | 2,122 | 2,118 | 2,118 |

Three runs of the PRE tree now exist — §2's branch arm (2,118), pre-a
(2,133) and pre-b (2,122) — and **the spread on IDENTICAL code is 15
certificates, which is the whole pre/post gap.** The 5–7 band §2.8
quoted is a flat-stretch band and does not apply here. pre-a is the
outlier of the set and its cause is visible: its `fields` row fired
ONCE where every other arm fired twice, `fields.collect` cost it 109
cpu-s against 27–29 everywhere else, and it began certifying at ~150 s
where the other two began at ~290 s. That race was seen on one PRE arm
in three; it was not looked for on the POST arms, and it is not the
axis under test.

What IS reproducible: post-a and post-b agree to the certificate, to
the plane (575 / 1,325 / 218) and to the minting row (`tiles.scan`
2,070, `tiles.retry` 42, `tiles.local` 5, `tiles.swim` 1) — and so does
§2's pre-code branch arm. Yield: **UNSEPARATED.**

#### 4.2.2 What IS separated, in both arms of both trees

| | pre-a | pre-b | post-a | post-b |
|---|---|---|---|---|
| `place.reads` CALLS | 6,198 | 5,916 | **990** | **990** |
| `place.retire` calls / cpu_s | 27,416 / 72.7 | 26,685 / 67.3 | 24,964 / **57.0** | 25,740 / **58.8** |
| `place.stage` calls / cpu_s | 26,704 / 12.3 | 25,973 / 11.3 | 24,252 / 11.4 | 25,028 / 10.4 |
| `refine.color.reads` calls | 2,128 | 2,054 | 933 | 945 |
| main thread `push` s | 84.1 | 78.8 | **69.0** | **69.8** |
| `pose_affine` wakes | 38,092 | 34,607 | **27,182** | **28,066** |
| `place_stage` wakes | 5,208 | 4,926 | 4,648 | 4,676 |
| `place` fires | 4,496 | 4,214 | 3,936 | 3,964 |
| `refine.color` fires / cpu_s | 497 / 79.4 | 459 / 75.5 | 365 / 59.3 | 384 / 62.8 |

**`place.reads` 5,916–6,198 calls → 990, which is the birth count.**
That single row is the amendment: `rederive_on=(KEY_PLACE_STAGE,)` ran
the derivation on every ladder wake, and a birth-fixed read set runs it
once per birth. `refine.color.reads` follows, 2,054–2,128 → 933–945.

The saving lands in `push`, 78.8–84.1 s → 69.0–69.8 s, almost all of it
`place.retire` (67.3–72.7 → 57.0–58.8 cpu-s): a parent that no longer
subscribes to its children holds a smaller read set and a cheaper
retire consult. Main-thread busy 209.4–215.1 → 201.2–201.3 s.
`pose_affine` wakes fall a fifth, 34.6–38.1 k → 27.2–28.1 k — the
refine rows' unpruned reaches were, on this capture, LARGER than their
birth reaches, not smaller.

Flat, within the pre tree's own spread: total wakes, keys,
subscriptions (0.3 %), job cpu (+2.5 %, and post reaches further down
the residue for it — `tiles.swim` fires 0 → 17–19, `tiles.local`
0–21 → 45–47), the frontier, and every `tile`/`attempt` census.

#### 4.2.3 Retire causes and the residue

| cause | pre-a | pre-b | post-a | post-b |
|---|---|---|---|---|
| `placed` | 712 | 712 | 712 | 712 |
| `certified` | 9,831 | 11,325 | 11,385 | 11,385 |

No `done_covered` and no `exhausted` on any of the four, as in §2.6 —
the transient question stays UNANSWERED by this capture. Same-cut
repeats (stream aware) 24,426 / 24,740 → 25,560 / 25,425, concurrent
14,517 / 14,964 → 15,479 / 15,422; `tiles.retry` stays barren
(23,946 / 24,281 → 25,011 / 24,925 zero-yield fires), exactly §2.8's
finding and untouched by this amendment. *Dated note 2026-10-18: the
"stream aware" here is wrong as in §2.7's note — the join on
`input_digest_bare` is stream-blind, so these repeat counts include
sibling-stream pairs on one cut; the numbers stand.*

### 4.3 What this A/B does not answer

1. **The quartering rung's own price on paper.** It is seated three
   times in one sim and fires in none; sheet H never subdivides. Its
   cost — one extra pop per subdivided window, and the children arriving
   later than the fold would have minted them — is UNMEASURED on a real
   sheet; sheet I's §3 arms pre-date the rung's own tracing. CORRECTED
   2026-10-03: the J run of 2026-09-24 subdivided (§5).
2. **Yield.** The 480 s bound's own spread on identical code is 15
   certificates. Sheet I to close is the yardstick and this amendment
   was not run against it.
3. **The `fields` single-solve race** that made pre-a certify 140 s
   early was seen on one PRE arm in three; it was not looked for on the
   POST arms.
   Noticed here, not chased.

## 5. The J confetti run of 2026-09-24 (de567456) — the first fragment sheet on the branch

`./confetti3.py decode --format L:c2-cmy8-r0547@53x37 --max-pages 2
--workers 12 --complete --diag 8023 --snapshot-every 30`, three of
J's ten captures, trace on, launched by the owner on machine 4; 52 min to
exhaustion, close OPEN at 2,561 certificates (three captures cannot
close J). Run dir `scratch/lifecycle-J-20260924/J3-branch.2110/`
(gitignored, machine 4 only). Single sheet, three captures — NO promotion.

| row | fires | certs | cpu-s | of which woken by verdicts ONLY (fires / certs / cpu-s) |
|---|---:|---:|---:|---|
| tiles.local | 3,533 | 303 (308 in the events report; the trace counts `n_certificates` per fire) | 7,359 | 1,178 / 0 / 2,536 |
| tiles.planek | 3,415 | 88 | 2,249 | 1,183 / 4 / 773 |
| tiles.swim | 4,904 | 11 | 12,216 | 2,725 / 0 / 6,644 |
| tiles.retry | 19,687 | 106 | 2,324 | (reads only its baseline verdict by design) |

Place: `subdivide` fired 325 times — 1,279 children, 216 placed;
afterlife 0 of 319 (structural: LIFECYCLE §8, 1d5f7a81); 44
`done_covered` retirements, 19 of them with an overlapping anchor
refined AFTER the retirement (whether a cell actually re-opened was not
checked; the cause is gone since 56928c45). One tile key had 28
subscribers on average (max 105); one `plane_field` key 1,764.

## 6. The 2026-10-03 wave on the sims (serial decodes, worker-order free)

pre-wave a7e41f2d → after 037440da → HEAD 349eee50:

| sim | calibrate | ctx | retry | scan | place |
|---|---|---|---|---|---|
| k-w1 | 29 → 10 → 10 | 10 → 10 → 10 | 25 → 22 → 22 | 99 → 96 → 96 | 55 → 55 → 55 |
| k-mixed-w1 | 112 → 26 → 26 | 26 → 26 → 26 | 33 → 26 → 26 | 122 → 113 → 113 | 263 → 263 → 263 |
| k-local-patch-w1 | 52 → 14 → 14 | 14 → 14 → 14 | — | — | — |

The whole movement is 037440da's (the fold-head correction kills the
K WindowEvidence ping-pong); 1d5f7a81, 80194fac and 162f1227 move no
serial fire count — the residue rows fire 0 on the clean sims. Every
payload sha and every held certificate count is unchanged (k-mixed-w1
49, k-complete 49, k-w1 48, colour serial 81, k-degraded-w1 4). The
`-n 8` records differ run to run and are scheduling noise, not evidence.

PROTOCOL NOTE (80194fac): a stop now merges the in-flight jobs and
attempts the close. "One SIGINT at 480 s" counts from before that sha
are not comparable one-to-one with counts after it.
