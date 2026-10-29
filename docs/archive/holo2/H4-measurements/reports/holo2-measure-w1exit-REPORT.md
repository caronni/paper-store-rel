# H4 W1-exit measurement chain — holo2 receiver

Operator run, measurement only (no code edits, no test suites, no commits).
Tree under measurement: `<checkout>`, pinned worktree
at commit `90181d2658828687bf001ffc75ab0735f5a2a138` ("W1 exit annotations:
the wave closed …").
Drivers: `scratch/holo2-demo/run_decode_ab.py` and
`run_decode_dbg.py`. Python: `env/bin/python`.
All six runs executed strictly sequentially, one decode at a time.
Chain start: 2026-08-16 00:51:58 CEST. Chain end: 2026-08-16 04:24:55 CEST.
**All six runs: VERIFIED, byte-identical. No FAILURE-RULE trigger occurred.**

## Summary table

| # | run | driver | workers | cap/switch | wall (driver) | wall (`time -l` real) | verified | certified | max RSS |
|---|-----|--------|---------|------------|---------------:|----------------------:|----------|----------:|--------:|
| 1 | w1exit-gc-w1 | ab | 1 | – | 836s (13.9 min) | 837.13s | YES | 1357 | 2,729,754,624 B (2.54 GiB) |
| 2 | w1exit-gc-w2 | ab | 2 | – | 1300s (21.7 min) | 1300.60s | YES | 1357 | 2,724,413,440 B (2.54 GiB) |
| 3 | w1exit-gc-w4 | ab | 4 | – | 2281s (38.0 min) | 2282.01s | YES | 1357 | 2,718,711,808 B (2.53 GiB) |
| 4 | w1exit-gc-w8 | ab | 8 | – | 4667s (77.8 min) | 4667.52s | YES | **1356** | 2,712,354,816 B (2.53 GiB) |
| 5 | w1exit-dbg-w8 | dbg | 8 | cap=8, switch=5ms | 2722s (45.4 min) | 2723.49s | YES | 1356 | 30,389,796,864 B (28.31 GiB) |
| 6 | w1exit-real-serial | ab | 1 | – | 632s (10.5 min) | 633.03s | YES | 1357 | 27,809,972,224 B (25.90 GiB) |

Inputs: runs 1–4 = gen-clean fixture `e028-genclean-c2-r0700.tiff` @1200 DPI,
expected `w1a-gc-serial.bin`. Runs 5–6 = real sheet
`scratch/in/xerox-canon-c2-bw.tiff` (2.29 GB) @4800 DPI, expected
`c2bw-waved.bin`.

Byte-identity: independently re-verified with `shasum -a 256` on every
output `.bin` and both expected files after the chain finished — all seven
files (5 outputs from the `ab` driver + 2 expected files) hash to the
identical `e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af`.
`run_decode_dbg.py` (run 5) does not write an output `.bin`; its printed
payload sha prefix `e5021f8d099587c3` matches this same hash, so run 5 is
counted byte-identical by full-hash match rather than file diff.

## Headline finding — gen-clean workers curve (runs 1–4)

Monotonic, non-trivial worsening as workers increase, all on the identical
fixture/expected pair, all VERIFIED/byte-identical, all closing at the same
certified-tile count (1357, except run 4 at 1356 — see anomaly below):

- w=1: 836s
- w=2: 1300s (+55.5% vs serial)
- w=4: 2281s (+2.73x vs serial)
- w=8: 4667s (+5.58x vs serial)

Utilisation climbs with workers (91.0% -> 94.5% -> 96.3% -> 96.2%) even as
wall time gets worse — the pool is busier, not idler, while producing a
slower result. Per-fire cost grows sharply with worker count: median fire
duration 0.8ms (w1) -> 2.7ms (w2) -> 13.1ms (w4) -> 70.1ms (w8); p90 fire
duration 964ms (w1) -> 21,646ms (w8). This matches the task's framing that
"expect similar or worse for the pool" — recorded here as measured fact,
no diagnosis attempted.

## Headline finding — real-sheet serial anchor ran far faster than expected

Run 6 (w1exit-real-serial, workers=1, the real 2.29 GB sheet @4800 DPI) was
briefed to the operator as a 5–7 hour overnight run. Measured wall was
**632s (~10.5 minutes)** — roughly 30–40x faster than the expected range.
All pass criteria were met (exit 0, RESULT VERIFIED, payload byte-identical
to `c2bw-waved.bin`), so this is not a FAILURE-RULE trigger, but the
magnitude of the deviation from the briefed expectation is the single most
notable result in this chain and is flagged here for the lead's attention.
No cause investigated (out of scope for this measurement pass).

## Per-run detail

### Run 1 — w1exit-gc-w1 (workers=1, gen-clean)
Start: 2026-08-16 00:51:58 CEST · End (process exit detected): 2026-08-16 01:06:18 CEST · Exit code: 0

```
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 68.9% (5534157/8034771 cells)
queue    ready 13[payload:10,place:3] · running 0 · sleeping 381 · retired 1792 · declined 315 (re-offerable 0) · pool 1/free
work     commits 3703 (scheduled 3702) · fires 3701 · wakes/commit 95.57 · useful 0.49 · peak 0 · stale 0
tiles    UNKNOWN 0 · ADDRESSED 375 · ATTEMPTED 8 · CERTIFIED 1357 · crc exposure 1373 spends/1391 attempts
close    verified · certified 1357 · K 1357/1356 · metadata rank 24/24 · blocks 1/1
[w1exit-gc-w1] RESULT VERIFIED certified=1357 commits=3702 fires=3701 wall=836s workers=1
[w1exit-gc-w1] payload 465580 B sha e5021f8d099587c3
[w1exit-gc-w1] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w1exit-gc-w1] FIRES 3701 busy 760.7s wall*W 836.3s utilisation 91.0% (residual = idle + main-thread phases)
[w1exit-gc-w1]   fire wall: median 0.8ms p90 964.0ms max 5079.6ms
[w1exit-gc-w1] ROUNDS none (continuous admission)
      837.13 real       820.80 user         6.31 sys
          2729754624  maximum resident set size
              194916  page reclaims
               94307  page faults
               13653  voluntary context switches
              461570  involuntary context switches
```

### Run 2 — w1exit-gc-w2 (workers=2, gen-clean)
Start: 2026-08-16 01:07:33 CEST (see anomaly note below) · End: 2026-08-16 01:29:46 CEST · Exit code: 0

**Anomaly (operator error, not a decode failure):** the first launch attempt
at 01:06:28 crashed instantly (0.02s wall) with
`can't open file 'run_decode_ab.py': [Errno 2] No
such file or directory`. Cause: the agent thread's working directory resets
to the repo root between Bash calls, and that launch used relative paths for
both the script and the log redirect, which resolved against the wrong cwd.
The stray misplaced log (`w1exit-gc-w2.log`,
outside `scratch/`) was deleted, no state directory or process was created
by the aborted attempt, and the run was relaunched cleanly one minute later
using fully absolute paths. This was **not** a FAILURE-RULE event (the
actual decode driver was never reached), and no repo files or decoder code
were touched.

```
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 68.9% (5534157/8034771 cells)
queue    ready 12[payload:10,place:2] · running 0 · sleeping 382 · retired 1793 · declined 315 (re-offerable 0) · pool 2/free
work     commits 3687 (scheduled 3686) · fires 3685 · wakes/commit 95.87 · useful 0.49 · peak 2 · stale 205
tiles    UNKNOWN 0 · ADDRESSED 375 · ATTEMPTED 8 · CERTIFIED 1357 · crc exposure 1373 spends/1391 attempts
close    verified · certified 1357 · K 1357/1356 · metadata rank 24/24 · blocks 1/1
[w1exit-gc-w2] RESULT VERIFIED certified=1357 commits=3686 fires=3685 wall=1300s workers=2
[w1exit-gc-w2] payload 465580 B sha e5021f8d099587c3
[w1exit-gc-w2] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w1exit-gc-w2] FIRES 3891 busy 2456.9s wall*W 2599.5s utilisation 94.5% (residual = idle + main-thread phases)
[w1exit-gc-w2]   fire wall: median 2.7ms p90 2932.7ms max 7959.4ms
[w1exit-gc-w2] ROUNDS none (continuous admission)
     1300.60 real      1325.20 user        16.19 sys
          2724413440  maximum resident set size
              196724  page reclaims
               94308  page faults
               13583  voluntary context switches
             2160141  involuntary context switches
```

### Run 3 — w1exit-gc-w4 (workers=4, gen-clean)
Start: 2026-08-16 01:29:57 CEST · End: 2026-08-16 02:08:09 CEST · Exit code: 0

```
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 68.9% (5534157/8034771 cells)
queue    ready 8[payload:7,place:1] · running 0 · sleeping 386 · retired 1793 · declined 315 (re-offerable 0) · pool 4/free
work     commits 3658 (scheduled 3657) · fires 3656 · wakes/commit 96.50 · useful 0.49 · peak 4 · stale 655
tiles    UNKNOWN 0 · ADDRESSED 375 · ATTEMPTED 8 · CERTIFIED 1357 · crc exposure 1373 spends/1389 attempts
close    verified · certified 1357 · K 1357/1356 · metadata rank 24/24 · blocks 1/1
[w1exit-gc-w4] RESULT VERIFIED certified=1357 commits=3657 fires=3656 wall=2281s workers=4
[w1exit-gc-w4] payload 465580 B sha e5021f8d099587c3
[w1exit-gc-w4] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w1exit-gc-w4] FIRES 4314 busy 8788.4s wall*W 9124.9s utilisation 96.3% (residual = idle + main-thread phases)
[w1exit-gc-w4]   fire wall: median 13.1ms p90 8693.7ms max 18311.3ms
[w1exit-gc-w4] ROUNDS none (continuous admission)
     2282.01 real      2362.15 user        54.28 sys
          2718711808  maximum resident set size
              360771  page reclaims
               94369  page faults
               13793  voluntary context switches
             9928146  involuntary context switches
```

### Run 4 — w1exit-gc-w8 (workers=8, gen-clean)
Start: 2026-08-16 02:08:20 CEST · End: 2026-08-16 03:26:50 CEST · Exit code: 0

**Anomaly (harness-side, not decode-side):** the operator's own polling
wrapper (the `until kill -0 …` loop, run separately from the decode) was
killed by the environment roughly an hour into the wait, hitting an apparent
runtime cap on backgrounded poll loops. The decode process itself (verified
directly via `ps`: still running, healthy CPU/RSS growth, correct log) was
never touched or interrupted. Polling was resumed against the same PID with
no gap in the actual measurement.

**Anomaly (result-level):** certified=1356 here, one lower than the 1357 seen
in runs 1–3 and run 6 on the same fixture/expected pair (`K 1356/1356` vs
`K 1357/1356` elsewhere). Still VERIFIED and byte-identical — not a
FAILURE-RULE trigger — but the tile count differs from the rest of the
gen-clean sweep and is flagged for the lead.

```
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · cf29e165ebe4… · done coverage 68.8% (5530928/8034771 cells)
queue    ready 0 · running 0 · sleeping 397 · retired 1794 · declined 315 (re-offerable 0) · pool 8/free
work     commits 3648 (scheduled 3647) · fires 3646 · wakes/commit 96.84 · useful 0.49 · peak 8 · stale 1622
tiles    UNKNOWN 0 · ADDRESSED 378 · ATTEMPTED 9 · CERTIFIED 1356 · crc exposure 1374 spends/1392 attempts
close    verified · certified 1356 · K 1356/1356 · metadata rank 24/24 · blocks 1/1
[w1exit-gc-w8] RESULT VERIFIED certified=1356 commits=3647 fires=3646 wall=4667s workers=8
[w1exit-gc-w8] payload 465580 B sha e5021f8d099587c3
[w1exit-gc-w8] vs w1a-gc-serial.bin: BYTE-IDENTICAL
[w1exit-gc-w8] FIRES 5273 busy 35901.1s wall*W 37334.2s utilisation 96.2% (residual = idle + main-thread phases)
[w1exit-gc-w8]   fire wall: median 70.1ms p90 21645.6ms max 39720.7ms
[w1exit-gc-w8] ROUNDS none (continuous admission)
     4667.52 real      4810.74 user       290.08 sys
          2712354816  maximum resident set size
             1220895  page reclaims
               94308  page faults
               13708  voluntary context switches
            37505904  involuntary context switches
```

### Run 5 — w1exit-dbg-w8 (workers=8, cap=8, switch_ms=5, real sheet)
Start: 2026-08-16 03:27:13 CEST · End: 2026-08-16 04:13:27 CEST · Exit code: 0

Driver docstring confirmed exact invocation order
(`TREE SCAN DPI PORT NAME WORKERS CAP SWITCH_MS`) matches the briefed
command with no deviation needed. This driver takes no `EXPECTED_BIN`
argument and does not write an output `.bin`; identity was confirmed by
matching the full printed sha (`e5021f8d099587c3…`) against the known
sha256 of `c2bw-waved.bin` computed independently before the run
(`e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af`).

```
[w1exit-dbg-w8] RESULT VERIFIED certified=1356 commits=4670 fires=4669 wall=2722s workers=8 cap=8 switch_ms=5.0
[w1exit-dbg-w8] payload sha e5021f8d099587c3
[w1exit-dbg-w8] FIRES 6762 busy(wall) 20482.0s busy(cpu) 3363.7s wait-share 83.6% median 495.3ms p90 9186.9ms
[w1exit-dbg-w8] GC 12763 collections, 8.1s inside GC
[w1exit-dbg-w8] MAIN-THREAD is_current 6758 calls 55.3s (8.19ms/call); apply 4669 calls 197.1s (42.23ms/call)
[w1exit-dbg-w8] SEGMENTS ctx.apply 4670 x 8.57ms (total 40.0s); absorb 4669 x 33.23ms (total 155.2s); consult 4669 x 0.36ms (total 1.7s)
[w1exit-dbg-w8] DRIFT kinds: moved:collection=2780, moved:tile=61, moved:seed=17, added:evidence=15
[w1exit-dbg-w8] DRIFT shapes: m1/a0/g0=1319, m2/a0/g0=748, m1/a1/g0=8, m3/a0/g0=7, m2/a1/g0=7
     2723.49 real      3128.90 user       394.87 sys
         30389796864  maximum resident set size
             4451926  page reclaims
             1518058  page faults
               43662  voluntary context switches
            52946463  involuntary context switches
```

Max RSS here (28.31 GiB) is an order of magnitude above the gen-clean runs
(~2.5 GiB) — expected given the much larger real capture (2.29 GB TIFF @4800
DPI vs 134 MB @1200 DPI), but the absolute figure is worth the lead's
awareness for machine-sizing purposes since this is a shared box.

### Run 6 — w1exit-real-serial (workers=1, real sheet, serial anchor)
Start: 2026-08-16 04:13:43 CEST · End: 2026-08-16 04:24:55 CEST · Exit code: 0

See "Headline finding — real-sheet serial anchor ran far faster than
expected" above: measured 632s against a briefed 5–7 hour expectation.

```
format   c2-r0700@3392x2368 · codec k-v1 · 1 page domain · streams main · PROVISIONAL
capture  1 ingested · 57a261454cc0… · done coverage 69.3% (5577215/8048178 cells)
queue    ready 63[payload:4,place:59] · running 0 · sleeping 550 · retired 1704 · declined 990 (re-offerable 0) · pool 1/free
work     commits 4918 (scheduled 4917) · fires 4916 · wakes/commit 45.25 · useful 0.39 · peak 0 · stale 0
tiles    UNKNOWN 0 · ADDRESSED 90 · ATTEMPTED 232 · CERTIFIED 1357 · crc exposure 1894 spends/2824 attempts
close    verified · certified 1357 · K 1357/1356 · metadata rank 24/24 · blocks 1/1
[w1exit-real-serial] RESULT VERIFIED certified=1357 commits=4917 fires=4916 wall=632s workers=1
[w1exit-real-serial] payload 465580 B sha e5021f8d099587c3
[w1exit-real-serial] vs c2bw-waved.bin: BYTE-IDENTICAL
[w1exit-real-serial] FIRES 4916 busy 510.1s wall*W 632.2s utilisation 80.7% (residual = idle + main-thread phases)
[w1exit-real-serial]   fire wall: median 4.1ms p90 146.9ms max 35116.5ms
[w1exit-real-serial] ROUNDS none (continuous admission)
      633.03 real       610.50 user        12.74 sys
         27809972224  maximum resident set size
             1592130  page reclaims
             1517995  page faults
               40893  voluntary context switches
              134535  involuntary context switches
```

Note: this run's capture hash (`57a261454cc0…`) differs from runs 1–5's
gen-clean hash (`cf29e165ebe4…`) as expected — it is the real-sheet TIFF,
a different physical input from the gen-clean fixture.

## Post-chain verification

- Independent `shasum -a 256` re-check of all five `ab`-driver output
  `.bin` files plus both expected `.bin` files: all seven hash identical
  (`e5021f8d099587c3…787af`).
- `git status --short` on the main repo (`<repo>`): clean,
  no changes.
- `git status --short` on the pinned worktree
  (`<checkout>`): only the pre-existing untracked
  `env` symlink (present before this session started, part of the worktree
  setup, not created by this run) — no other changes.
- No test suites were run. No repo files were edited. No commits were made.

## Anomalies summary (for the lead)

1. **Run 6 timing** — measured 632s vs a briefed 5–7 hour expectation for
   the real-sheet serial anchor (~30–40x faster). Largest finding in this
   chain. Not a FAILURE-RULE trigger (VERIFIED, byte-identical, exit 0).
2. **Run 4 tile count** — certified=1356 vs 1357 in the other three
   gen-clean-fixture runs. Not a FAILURE-RULE trigger.
3. **Run 2 launch** — operator path-resolution mistake (cwd resets between
   Bash calls in this agent thread) caused an instant crash on the first
   launch attempt; cleaned up, no state/process created, relaunched
   correctly one minute later with absolute paths. Not a decode failure.
4. **Run 4 poll-wrapper kill** — the operator's own foreground polling loop
   (separate process from the decode) was killed by the harness near the
   ~60-minute mark; the decode process was confirmed still healthy via
   direct `ps` inspection and polling resumed on the same PID with no
   effect on the measurement.
