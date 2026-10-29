# H4 W2-exit measurement battery — holo2 receiver

Tree under measurement: `<checkout>` (pinned at
commit `d23c756aa4537812a878fc6a47eb8ce310f5e8a4`, verified via
`git rev-parse HEAD` at the start of this session).

Driver: `scratch/holo2-demo/run_decode_ab.py`
(usage `run_decode_ab.py TREE SCAN DPI PORT NAME WORKERS [EXPECTED_BIN]`).
Each invocation wrapped in `/usr/bin/time -l`, stdout+stderr into
`scratch/holo2-demo/<name>.log`, run strictly sequentially (never two
decodes concurrent), polled to completion.

Python: `env/bin/python` (3.14.6). Host: 10 cores,
load average at session start ~3.0/2.25/2.19, 1.2 TiB free on the data
volume. No prior state/logs for these run names existed before this
session; no port conflicts.

## HOLD — chain stopped after run 4 by lead instruction

Runs 5 and 6 (real-sheet serial/w8 on `scratch/in/xerox-canon-c2-bw.tiff`)
were **not launched**. Mid-chain the lead directed: stop after
w2exit-gc-w8 completes, do not run the real-sheet pair — **real-sheet
runs deferred by the lead pending fixes + GIL diagnosis**, to be run
later on a fixed tree. This report therefore covers only the gen-clean
workers curve (runs 1-4). Confirmed no `w2exit-real-*` logs, outputs, or
state directories exist in `scratch/holo2-demo/`.

The real-sheet pair below (runs 5-6) was completed in a follow-up
session once the tree was fixed — see the new section appended at the
end of this report.

All four executed runs used the gen-clean fixture
`scratch/holo2-demo/e028-genclean-c2-r0700.tiff` at DPI 1200, expected
payload `scratch/holo2-demo/w1a-gc-serial.bin`.

## Summary table

| run | workers | port | wall (s) | verified | byte-identical | certified | commits | fires | wakes/commit | stale | utilisation | max RSS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| w2exit-gc-w1 | 1 | 8651 | 536.90 | VERIFIED | BYTE-IDENTICAL | 1357 | 1918 (sched 1919) | 2323 | 0.71 | 0 | 83.5% | 2,721,824,768 B (~2.53 GiB) |
| w2exit-gc-w2 | 2 | 8652 | 525.80 | VERIFIED | BYTE-IDENTICAL | 1356 | 1928 (sched 1929) | 2337 | 0.71 | 12 | 88.1% | 2,716,975,104 B (~2.53 GiB) |
| w2exit-gc-w4 | 4 | 8653 | 550.30 | VERIFIED | BYTE-IDENTICAL | 1359 | 1922 (sched 1923) | 2331 | 0.71 | 17 | 88.6% | 2,722,086,912 B (~2.54 GiB) |
| w2exit-gc-w8 | 8 | 8654 | 591.79 | VERIFIED | BYTE-IDENTICAL | 1360 | 1918 (sched 1919) | 2326 | 0.71 | 14 | 88.2% | 2,722,316,288 B (~2.54 GiB) |

All four PASS (VERIFIED + BYTE-IDENTICAL vs `w1a-gc-serial.bin`,
sha `e5021f8d099587c3…` in every run). "commits" column shows the driver's
`RESULT commits=` value with the `work` line's "commits N (scheduled M)"
value noted for cross-check — the two differ by exactly 1 in every run
(driver's `commits=` reports scheduled-1, `work` line reports both
counters directly).

Certified-tile counts (serial reference = 1357, from w2exit-gc-w1 acting
as the w1 baseline): w2=1356 (-1), w4=1359 (+2), w8=1360 (+3). Recorded
as an observation per the pooled-vs-serial tolerance in the brief — not a
failure; all four closes independently verified byte-exact regardless of
the certified-count delta. `close K X/1356` shows the second number
(1356) constant across all four runs (fixed K target); certified count
exceeds K by 1-4 tiles (surplus) in every run.

Wall times are DATA only, no judgment applied (536.9s / 525.8s / 550.3s /
591.8s for w=1/2/4/8) — comparison to prior columns is the lead's call.

## Timestamps

| run | date start | date end |
|---|---|---|
| w2exit-gc-w1 | Sun Aug 16 19:08:59 CEST | Sun Aug 16 19:17:56 CEST |
| w2exit-gc-w2 | Sun Aug 16 19:18:08 CEST | Sun Aug 16 19:26:54 CEST |
| w2exit-gc-w4 | Sun Aug 16 19:27:05 CEST | Sun Aug 16 19:36:15 CEST |
| w2exit-gc-w8 | Sun Aug 16 19:36:26 CEST | Sun Aug 16 19:46:18 CEST |

(Runs launched back-to-back, no overlap; each `date end` precedes the
next `date start` by single-digit seconds — driver startup/teardown.)

## Per-run raw tails

### w2exit-gc-w1 (workers=1, port 8651)

```
=== START w2exit-gc-w1 Sun Aug 16 19:08:59 CEST 2026 ===
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 68.9% (5534263/8034771 cells)
queue    ready 175[payload:74,place:101] · running 0 · sleeping 337 · retired 1357 · declined 0 (re-offerable 0) · pool 1/free
work     commits 1919 (scheduled 1918) · fires 2323 · wakes/commit 0.71 · useful 0.68 · peak 0 · stale 0
tiles    UNKNOWN 0 · ADDRESSED 397 · ATTEMPTED 7 · CERTIFIED 1357 · crc exposure 1364 spends/1364 attempts
close    verified · certified 1357 · K 1357/1356 · metadata rank 24/24 · blocks 1/1
[w2exit-gc-w1] RESULT VERIFIED certified=1357 commits=1918 fires=2323 wall=536s workers=1
[w2exit-gc-w1] payload 465580 B sha e5021f8d099587c3
[w2exit-gc-w1] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w2exit-gc-w1] FIRES 2323 busy 447.7s wall*W 536.3s utilisation 83.5% (residual = idle + main-thread phases)
[w2exit-gc-w1]   fire wall: median 0.7ms p90 76.9ms max 3223.8ms
[w2exit-gc-w1] ROUNDS none (continuous admission)
      536.90 real       532.99 user         2.37 sys
          2721824768  maximum resident set size
              177217  page reclaims
               94310  page faults
                   0  swaps
               12921  voluntary context switches
               10109  involuntary context switches
       8269850101971  instructions retired
       1721080297565  cycles elapsed
          1032570944  peak memory footprint
EXIT_CODE=0
=== END w2exit-gc-w1 Sun Aug 16 19:17:56 CEST 2026 ===
```

### w2exit-gc-w2 (workers=2, port 8652)

```
=== START w2exit-gc-w2 Sun Aug 16 19:18:08 CEST 2026 ===
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 68.8% (5530220/8034771 cells)
queue    ready 170[payload:69,place:101] · running 0 · sleeping 343 · retired 1356 · declined 0 (re-offerable 0) · pool 2/free
work     commits 1929 (scheduled 1928) · fires 2337 · wakes/commit 0.71 · useful 0.68 · peak 2 · stale 12
tiles    UNKNOWN 0 · ADDRESSED 398 · ATTEMPTED 7 · CERTIFIED 1356 · crc exposure 1363 spends/1363 attempts
close    verified · certified 1356 · K 1356/1356 · metadata rank 24/24 · blocks 1/1
[w2exit-gc-w2] RESULT VERIFIED certified=1356 commits=1928 fires=2337 wall=525s workers=2
[w2exit-gc-w2] payload 465580 B sha e5021f8d099587c3
[w2exit-gc-w2] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w2exit-gc-w2] FIRES 2350 busy 925.2s wall*W 1050.8s utilisation 88.1% (residual = idle + main-thread phases)
[w2exit-gc-w2]   fire wall: median 15.0ms p90 181.2ms max 7430.5ms
[w2exit-gc-w2] ROUNDS none (continuous admission)
      525.80 real       546.31 user         6.18 sys
          2716975104  maximum resident set size
              182328  page reclaims
               94307  page faults
                   0  swaps
               12824  voluntary context switches
             1278072  involuntary context switches
       8374269935001  instructions retired
       1768064785161  cycles elapsed
          1026082856  peak memory footprint
EXIT_CODE=0
=== END w2exit-gc-w2 Sun Aug 16 19:26:54 CEST 2026 ===
```

### w2exit-gc-w4 (workers=4, port 8653)

```
=== START w2exit-gc-w4 Sun Aug 16 19:27:05 CEST 2026 ===
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 69.0% (5542475/8034771 cells)
queue    ready 170[payload:69,place:101] · running 0 · sleeping 340 · retired 1359 · declined 0 (re-offerable 0) · pool 4/free
work     commits 1923 (scheduled 1922) · fires 2331 · wakes/commit 0.71 · useful 0.68 · peak 4 · stale 17
tiles    UNKNOWN 0 · ADDRESSED 395 · ATTEMPTED 7 · CERTIFIED 1359 · crc exposure 1366 spends/1366 attempts
close    verified · certified 1359 · K 1359/1356 · metadata rank 24/24 · blocks 1/1
[w2exit-gc-w4] RESULT VERIFIED certified=1359 commits=1922 fires=2331 wall=550s workers=4
[w2exit-gc-w4] payload 465580 B sha e5021f8d099587c3
[w2exit-gc-w4] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w2exit-gc-w4] FIRES 2350 busy 1948.8s wall*W 2199.5s utilisation 88.6% (residual = idle + main-thread phases)
[w2exit-gc-w4]   fire wall: median 57.0ms p90 474.5ms max 19330.7ms
[w2exit-gc-w4] ROUNDS none (continuous admission)
      550.30 real       578.09 user        26.23 sys
          2722086912  maximum resident set size
              186096  page reclaims
               94307  page faults
                   0  swaps
               13228  voluntary context switches
             6362808  involuntary context switches
       8549023358095  instructions retired
       1898636132250  cycles elapsed
          1046611552  peak memory footprint
EXIT_CODE=0
=== END w2exit-gc-w4 Sun Aug 16 19:36:15 CEST 2026 ===
```

### w2exit-gc-w8 (workers=8, port 8654)

```
=== START w2exit-gc-w8 Sun Aug 16 19:36:26 CEST 2026 ===
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 69.0% (5546480/8034771 cells)
queue    ready 170[payload:69,place:101] · running 0 · sleeping 338 · retired 1360 · declined 0 (re-offerable 0) · pool 8/free
work     commits 1919 (scheduled 1918) · fires 2326 · wakes/commit 0.71 · useful 0.68 · peak 8 · stale 14
tiles    UNKNOWN 0 · ADDRESSED 395 · ATTEMPTED 6 · CERTIFIED 1360 · crc exposure 1366 spends/1366 attempts
close    verified · certified 1360 · K 1360/1356 · metadata rank 24/24 · blocks 1/1
[w2exit-gc-w8] RESULT VERIFIED certified=1360 commits=1918 fires=2326 wall=591s workers=8
[w2exit-gc-w8] payload 465580 B sha e5021f8d099587c3
[w2exit-gc-w8] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w2exit-gc-w8] FIRES 2343 busy 4171.0s wall*W 4730.4s utilisation 88.2% (residual = idle + main-thread phases)
[w2exit-gc-w8]   fire wall: median 98.9ms p90 1675.3ms max 51708.2ms
[w2exit-gc-w8] ROUNDS none (continuous admission)
      591.79 real       613.27 user        81.40 sys
          2722316288  maximum resident set size
              201852  page reclaims
               94307  page faults
                   0  swaps
               13398  voluntary context switches
            11760878  involuntary context switches
       8764159692952  instructions retired
       2138377351586  cycles elapsed
          1080346280  peak memory footprint
EXIT_CODE=0
=== END w2exit-gc-w8 Sun Aug 16 19:46:18 CEST 2026 ===
```

## Anomalies / observations

- **No failures.** All four runs VERIFIED + BYTE-IDENTICAL, exit code 0.
- **Certified-tile count drifts slightly with worker count** on the
  gen-clean fixture: 1357 (w1, serial) -> 1356 (w2) -> 1359 (w4) ->
  1360 (w8). Deltas of -1/+2/+3 tiles vs serial. All closes independently
  byte-exact against the expected payload regardless, so this is a
  pooled-vs-serial tile-selection variance, not a correctness failure.
  Flagged as data for the lead per the recorded-observation rule.
- **`stale` count is non-zero and grows roughly with worker count** for
  every pooled run: w2=12, w4=17, w8=14 (not strictly monotonic — w8 is
  slightly below w4). w1 (serial) has stale=0 as expected (no contention
  possible at workers=1).
- **`involoutary context switches` scale sharply with worker count**:
  10,109 (w1) -> 1,278,072 (w2) -> 6,362,808 (w4) -> 11,760,878 (w8) —
  roughly linear-to-superlinear growth, consistent with GIL/scheduler
  contention across the pooled worker pool. Left as raw data; this is
  likely one of the signals motivating the GIL diagnosis the lead
  referenced when deferring runs 5/6.
- **Wall time is non-monotonic** across the workers curve: 536.9s (w1) ->
  525.8s (w2, fastest) -> 550.3s (w4) -> 591.8s (w8, slowest) — worker
  count above 2 does not buy wall-clock speedup on this fixture/tree.
  Recorded as data only, no judgment.
- **Max RSS is flat** across all four runs (~2.52-2.54 GiB), i.e. pooled
  worker count does not materially change peak memory footprint on this
  fixture.
- **Ports/state**: no pre-existing state or output collisions; each run
  used a distinct port (8651-8654) and its own `state-w2exit-gc-w<N>*`
  directories, confirmed clean before launch.

## Chain status

STOPPED after run 4 (w2exit-gc-w8) by lead instruction, mid-session,
change of plan communicated by the user via the lead. Runs 5
(w2exit-real-serial) and 6 (w2exit-real-w8) — the real-sheet
(`scratch/in/xerox-canon-c2-bw.tiff`) serial and workers=8 measurements —
were **not launched** and remain outstanding. Reason recorded verbatim
from the lead: "real-sheet runs deferred by the lead pending fixes + GIL
diagnosis." No failure occurred; this is a scope hold, not a chain abort
on error.

---

# Real-sheet runs (completed on the fixed tree 202618e)

Tree under measurement: `<checkout>`, `HEAD`
detached at `202618e` (verified via `git log --oneline -1` and
`git status` — clean except untracked `env/` — at the start of this
follow-up session). This supersedes the earlier pin
(`d23c756aa4537812a878fc6a47eb8ce310f5e8a4`) recorded above; the lead's
brief for this session names `202618e` as the fixed tree.

Driver: `scratch/holo2-demo/run_decode_ab.py`,
same usage as above. Real-sheet fixture:
`scratch/in/xerox-canon-c2-bw.tiff`, DPI 4800, expected payload
`scratch/holo2-demo/c2bw-waved.bin` (sha256
`e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af`).
Python: `env/bin/python`. Two runs, strictly
sequential — run 2 launched only after run 1's process had exited and
its `EXIT_CODE=0` line was written to its log; no port or state overlap
at any point (`lsof -i`/`ps`/directory listing checked clean before each
launch).

**Operator note (not a measurement failure):** the first two launch
attempts of `w2exit-real-serial` (~21:16-21:20 CEST) were killed by the
harness's 2-minute foreground-command timeout before the decode process
produced any output — the invocation was not backgrounded. Both aborted
attempts left only a stub `state-w2exit-real-serial*` directory pair and
a 1-3 line log; no decode had progressed, no port was bound at the time
of inspection (`lsof -i :8655` empty), and no `ps` entry for
`run_decode_ab.py` survived. Both stubs were deleted before the run
recorded below was launched (correctly backgrounded). This is recorded
for the log's sake; it is a tooling/harness-invocation issue, not a
decode outcome, and is not one of the two required runs.

## Summary table

| run | workers | port | wall (s) | verified | byte-identical | certified | commits (driver / work-line scheduled) | fires | wakes/commit | stale | utilisation | max RSS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| w2exit-real-serial | 1 | 8655 | 290.13 | VERIFIED | BYTE-IDENTICAL | 1358 | 1919 / 1919 | 1930 | 0.82 | 0 | 42.2% | 27,745,976,320 B (~25.85 GiB) |
| w2exit-real-w8 | 8 | 8656 | 287.13 | VERIFIED | BYTE-IDENTICAL | 1356 | 1916 / 1916 | 1927 | 0.82 | 41 | 86.1% | 29,929,193,472 B (~27.87 GiB) |

**Both PASS**: VERIFIED + BYTE-IDENTICAL, exit code 0, both runs. Driver
reports both payload sha `e5021f8d099587c3…` vs `c2bw-waved.bin`
BYTE-IDENTICAL; independently reconfirmed outside the driver via
`shasum -a 256` on the two output files — `w2exit-real-serial.bin` and
`w2exit-real-w8.bin` both hash to
`e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af`,
identical to `c2bw-waved.bin` itself. `close K X/1356` shows K=1356 in
both runs (fixed K target, matching the gen-clean battery's K); certified
exceeds/meets K by 2 (serial) / 0 (w8, certified==K exactly).

**Serial certified count vs the "exact 1357" expectation**: measured
**1358**, i.e. +1 against the pre-registered value. For context (not as
a substitute measurement): an earlier real-sheet serial run recorded in
this same scratch directory from a prior session
(`w1exit-real-serial.log`, tree/commit not verified as `202618e`)
certified exactly 1357 on the identical fixture (same capture hash
`57a261454cc0…`) — but ran wall=632s with wakes/commit=45.25, both far
outside this session's profile (wall=290.13s, wakes/commit=0.82),
indicating that prior run was on a materially different tree state
(consistent with "pending fixes" predating the `202618e` pin). Recorded
as data for the lead; not adjudicated, no retry performed (VERIFIED +
byte-identical + exit 0 held, so the FAILURE RULE was not triggered).

**Wall-clock, workers 1 vs 8**: 290.13s vs 287.13s — a 1.0% difference.
No material wall-clock speedup at workers=8, matching the brief's stated
expectation ("the w8 run is expected to be no faster than serial — that
is the finding"). Recorded as data, no further judgment applied.

**Utilisation / contention signals, serial -> w8**: utilisation 42.2% ->
86.1%; `stale` 0 -> 41; involuntary context switches 95,749 ->
10,165,697 (~106x); max RSS ~25.85 -> ~27.87 GiB. Both runs' RSS is far
above the gen-clean battery's ~2.5 GiB (expected — DPI 4800 real-sheet
capture vs DPI 1200 gen-clean fixture, 8,048,178 vs 8,034,771 total
cells but a much larger source TIFF). The involuntary-context-switch
jump is the same qualitative signature flagged in the earlier gen-clean
section (GIL/scheduler contention across the pooled worker pool) and is
sharper here than in any gen-clean run.

## Timestamps

| run | date start | date end |
|---|---|---|
| w2exit-real-serial | Sun Aug 16 21:23:01 CEST 2026 | Sun Aug 16 21:27:51 CEST 2026 |
| w2exit-real-w8 | Sun Aug 16 21:28:07 CEST 2026 | Sun Aug 16 21:32:54 CEST 2026 |

(Strictly sequential, no overlap; run 2 started 16s after run 1's `END`
line.)

## Per-run raw tails

### w2exit-real-serial (workers=1, port 8655)

```
=== START w2exit-real-serial Sun Aug 16 21:23:01 CEST 2026 ===
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · 57a261454cc0… · done coverage 69.3% (5574371/8048178 cells)
queue    ready 804[payload:801,place:3] · running 0 · sleeping 16 · retired 1358 · declined 0 (re-offerable 0) · pool 1/free
work     commits 1920 (scheduled 1919) · fires 1930 · wakes/commit 0.82 · useful 0.99 · peak 0 · stale 0
tiles    UNKNOWN 0 · ADDRESSED 383 · ATTEMPTED 217 · CERTIFIED 1358 · crc exposure 1575 spends/1575 attempts
close    verified · certified 1358 · K 1358/1356 · metadata rank 24/24 · blocks 1/1
[w2exit-real-serial] RESULT VERIFIED certified=1358 commits=1919 fires=1930 wall=290s workers=1
[w2exit-real-serial] payload 465580 B sha e5021f8d099587c3
[w2exit-real-serial] vs c2bw-waved.bin: BYTE-IDENTICAL
[w2exit-real-serial] FIRES 1930 busy 122.1s wall*W 289.6s utilisation 42.2% (residual = idle + main-thread phases)
[w2exit-real-serial]   fire wall: median 4.2ms p90 166.4ms max 34462.4ms
[w2exit-real-serial] ROUNDS none (continuous admission)
      290.13 real       267.30 user        10.82 sys
         27745976320  maximum resident set size
                   0  average shared memory size
                   0  average unshared data size
                   0  average unshared stack size
             1744836  page reclaims
             1517810  page faults
                   0  swaps
                   0  block input operations
                   0  block output operations
                   4  messages sent
                   4  messages received
                   0  signals received
               54659  voluntary context switches
               95749  involuntary context switches
       3852275418104  instructions retired
        884000871299  cycles elapsed
          4956307104  peak memory footprint
EXIT_CODE=0
=== END w2exit-real-serial Sun Aug 16 21:27:51 CEST 2026 ===
```

### w2exit-real-w8 (workers=8, port 8656)

```
=== START w2exit-real-w8 Sun Aug 16 21:28:07 CEST 2026 ===
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · 57a261454cc0… · done coverage 69.2% (5566067/8048178 cells)
queue    ready 798[payload:795,place:3] · running 0 · sleeping 23 · retired 1356 · declined 0 (re-offerable 0) · pool 8/free
work     commits 1917 (scheduled 1916) · fires 1927 · wakes/commit 0.82 · useful 0.99 · peak 8 · stale 41
tiles    UNKNOWN 0 · ADDRESSED 386 · ATTEMPTED 216 · CERTIFIED 1356 · crc exposure 1572 spends/1572 attempts
close    verified · certified 1356 · K 1356/1356 · metadata rank 24/24 · blocks 1/1
[w2exit-real-w8] RESULT VERIFIED certified=1356 commits=1916 fires=1927 wall=287s workers=8
[w2exit-real-w8] payload 465580 B sha e5021f8d099587c3
[w2exit-real-w8] vs c2bw-waved.bin: BYTE-IDENTICAL
[w2exit-real-w8] FIRES 1975 busy 1974.0s wall*W 2292.7s utilisation 86.1% (residual = idle + main-thread phases)
[w2exit-real-w8]   fire wall: median 336.0ms p90 2184.2ms max 40354.3ms
[w2exit-real-w8] ROUNDS none (continuous admission)
      287.13 real       331.90 user        79.48 sys
         29929193472  maximum resident set size
                   0  average shared memory size
                   0  average unshared data size
                   0  average unshared stack size
             1904881  page reclaims
             1517996  page faults
                   0  swaps
                   0  block input operations
                   0  block output operations
                   4  messages sent
                   4  messages received
                   0  signals received
               44857  voluntary context switches
            10165697  involuntary context switches
       4272619219596  instructions retired
       1221768063339  cycles elapsed
          5502458288  peak memory footprint
EXIT_CODE=0
=== END w2exit-real-w8 Sun Aug 16 21:32:54 CEST 2026 ===
```

## Notes

- **No failures.** Both runs VERIFIED + BYTE-IDENTICAL, exit code 0. The
  FAILURE RULE (stop on not-VERIFIED / not-byte-identical / non-zero
  exit) was not triggered by either run; no retries were performed or
  needed.
- **Byte-identity** independently reconfirmed outside the driver's own
  check via `shasum -a 256` on both `.bin` outputs against
  `c2bw-waved.bin` — exact match, all three files share sha256
  `e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af`.
- **Serial certified = 1358, not the pre-registered exact 1357** — a
  +1 deviation. Flagged above as data for the lead per the recorded-
  observation convention used in the gen-clean section; not treated as
  a failure since PASS was defined as VERIFIED + byte-identical, both of
  which held.
- **w8 wall-clock is not faster than serial** (287.13s vs 290.13s,
  -1.0%) — this is the expected finding per the brief, recorded without
  further judgment.
- **Ports/state**: `8655`/`8656` both confirmed unbound before each
  launch; each run used its own `state-w2exit-real-*` directory,
  confirmed absent before launch and present only after.

## Chain status

Both deferred real-sheet runs (5: `w2exit-real-serial`, 6:
`w2exit-real-w8`) are now complete. H4 W2-exit measurement battery
closed: six runs total across both sessions (four gen-clean + two
real-sheet), all six VERIFIED + BYTE-IDENTICAL, zero failures.
