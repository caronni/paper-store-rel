# The one instrumented sheet-H run

Written 2026-09-17 on branch `sched-instrumentation`.  Real decodes cost
hours, so this run happens ONCE and must carry everything the five
static-analysis lenses asked for.  The instrument is
`src/holo/receiver/sched_trace.py`, DEFAULT OFF, armed by
`HOLO3_SCHED_TRACE=1`; the reducer is `measure/sched_trace/report.py`.

The trace is MEASUREMENT ONLY.  No scheduling decision reads it back —
the redundancy digest is recorded and never acted on, the job runs
either way — and it appends nothing to the event list, so the run's
`events.jsonl`, `report.json`, panes, snapshot and payload are what an
untraced run would have written.  Verified: colour sim at workers=1,
traced vs untraced, identical payload sha, identical certificate
signature, identical event sequence once `cpu_s` / `consult_cpu_s` (both
thread-time meters, which never repeat between any two runs) are
normalised away — `test_h3_sched_trace.py`, slow lane.

## The command

Run it from the WORKTREE, with the main tree's interpreter (there is no
venv inside the worktree), and tee stderr — the trace prints one arming
line and the engine prints its own progress there.

```sh
cd <repo>

HOLO3_SCHED_TRACE=1 \
HOLO3_SCHED_TRACE_EVERY_S=300 \
PYTHONPATH=src \
env/bin/python -m holo.receiver decode \
  scratch/xerox-canon-18.8-H-c2-cmy8-r850-q90-p120-4mm-2400dpi-a.tiff \
  --dpi 2400 \
  --format L:c2-cmy8-r0850-p120-x1@3392x2368 \
  --max-pages 1 \
  --workers 12 \
  --snapshot-every 20 \
  --run-dir scratch/sched-trace-H-20260917 \
  --out scratch/sched-trace-H-20260917.bin \
  2>&1 | tee scratch/sched-trace-H-20260917.log
```

Notes on the arguments, none of them free to change without changing
what the run measures:

* the CLI appends `.<pid>` to `--run-dir`, so the products land in
  `scratch/sched-trace-H-20260917.<pid>/` and the trace in
  `scratch/sched-trace-H-20260917.<pid>/sched-trace/`.  The log names
  the directory in its first line (`sched-trace: armed, writing …`).
* `--out` must not already exist; the CLI refuses to overwrite it.
* ONE capture, from scratch, no `--resume`.  That is deliberate: it is
  the e037-shaped regime (no place worker ever retires, the ladder
  climbs from zero) and it is the one the lenses' numbers are about.
  The OPPOSITE regime — a resume, where windows are born before the
  placements fold and so DO get popped and retired — is a different
  shape for FM-3 and for the index size, and no single run covers both.
  See "What this cannot tell us" below.
* `HOLO3_SCHED_TRACE_EVERY_S=300` dumps every five minutes.  Lower it
  only if the run may be killed hard; each dump costs one pass over the
  bookmark ledger (order 50k rows), which is seconds, not minutes.

## While it runs

* `SIGUSR1` — dumps the fact snapshot AND the trace, and prints the
  status rows.  Free to send as often as you like.
* `ctrl-T` (SIGINFO) — status rows only, no dump.
* ONE `ctrl-C` (SIGINT or SIGTERM) — orderly stop, and it DRAINS
  (since `80194fac`, 2026-10-03): the loop stops scheduling at the next
  consistent point, merges every job already in flight into the store,
  runs the deciding close consult, and `_finish` writes every product
  the run would have written at exhaustion; the trace takes its final
  dump.  The drain waits for the longest in-flight job.  A SECOND
  signal ABANDONS the drain: the loop leaves at once, the in-flight
  jobs' facts stay out of the snapshot, the process exits when they
  return.  The second ctrl-C also restores the default handler, so a
  THIRD kills the process and you lose everything since the last dump.
  Do not press it twice unless the drain is wedged.  A stopped run
  counts the in-flight jobs' certificates, so "one SIGINT at N s"
  records after `80194fac` do not compare one-to-one with earlier ones.
* The trace dumps on the orderly stop as well, so a stopped run is
  fully reducible.
* All three doors, and the trace's own cadence, are served at the TOP OF
  THE ENGINE LOOP, where the store is consistent.  So a signal is acted
  on at the next merge, not instantly: on a page whose workers are all
  inside one long job, expect a wait.  Measured on the colour sim
  (2 workers, 15 s `place` jobs): a SIGUSR1 sent at 10 s was still
  pending when the SIGINT arrived at 15 s, and both were served
  together at the first merge.  This is the shipped engine's behaviour,
  not the trace's.

## What you get

Under `<run_dir>/sched-trace/`:

| file | what | written |
|---|---|---|
| `summary.json` | every counter: the wake fan-out matrix (key kind × plugin), the push and pop funnels per plugin, exclusive main-thread seconds by category, per-plugin per-callback time and call counts, the bookmark census, the index census, the heap and RSS peaks, the digest's own cost | atomic at each dump |
| `subscribers.json` | per key kind: keys, subscriptions, max, mean, p99 | atomic at each dump |
| `fires.jsonl` | one row per fire: seq, plugin, subject, stage, cost, attempts, version_at_fire, tried_version_before, wakes_since_last_fire, wake_kinds_since_last_fire, cpu_s, wall_started_s, wall_ended_s, n_certificates/poses/words, n_facts, n_facts_refused, redundant_input, input_digest, input_digest_bare, reason | appended, flushed at each dump |
| `timeline.jsonl` | a sample at most every 2 s: inflight, frontier_len, queued per plugin, wakes, fires, certificates, cumulative main-thread seconds by category, peak RSS | appended, flushed at each dump |
| `place-ladder.jsonl` | per window, one row per seat / fire / retire, with stage, cost and wall — the "36 WindowScheduled for one window" story, reconstructible | appended, flushed at each dump |

A killed run therefore loses at most one dump interval, and never half a
file: the JSON files are written tmp-then-`os.replace`, and the JSONL
files are block-buffered and flushed at every dump (the reducer also
tolerates one torn last line).

Reading caveats from the 2026-09-17 review, so nobody discovers them
after the run: (a) the tracer's own hot-path cost sits INSIDE the
categories it reports — about 0.3 µs per wake and ~1.1 µs per traced
push, so of the order of 6–9 s charged to `touch`/`push` over a 5.9 M-wake
run; (b) `max_index_keys` and `max_subscriptions` in the headline are
per-dump maxima (every five minutes), while `max_frontier_len` is exact
(updated at every seat); (c) `place-ladder.jsonl` is unbounded — one
line per seat, fire and retire — and the reducer loads it whole, so
reduce a very long run on a machine with memory to spare.

## Reducing it

```sh
cd <repo>
PYTHONPATH=src \
env/bin/python measure/sched_trace/report.py \
  scratch/sched-trace-H-20260917.<pid> \
  --out scratch/sched-trace-H-20260917.md
```

It takes either the run dir or the `sched-trace/` dir inside it, is
read-only and stdlib-only, and works on a partial trace.  `--top N`
widens the "most-fired subjects", "fan-out cells" and "transitions"
tables (default 20).

## Reading it: the specific questions this run was built to settle

* **Is the main thread the constraint?**  "Main thread busy share of
  wall" against "worker utilisation" in the headline, then the exclusive
  category table.  e037's 26 % utilisation is consistent with a
  serialised main thread, with GIL contention and with I/O stalls, and
  the archived events cannot separate them.  Here they can: `wait` is
  time the main thread was blocked with work outstanding.  The per-fire
  `wall/cpu` ratio in the cadence table is an UPPER BOUND on a job's own
  stalls, not a measure of them: `wall_ended_s` is stamped at the merge,
  and futures completing in one `wait()` batch are folded serially in
  seat order, so the last of twelve pays for the eleven merges ahead of
  it — the ratio also rises when the main thread is slow, which is the
  hypothesis under test (review 2026-09-17, B-4).  `intake` and
  `snapshot` are their own categories, so `other` is the loop's own
  residue and nothing else.
* **What the 5.9 M wakes cost.**  The `push` category is the whole wake
  path's main-thread bill; the fan-out matrix says who generated it.
* **Where the expensive adjudication is.**  `place/stage`,
  `place/retire` and `tiles.scan/prepare` in the callback table are
  FM-2, FM-4 and FM-5/TILE-7 respectively, per call and in total.
* **The two funnels.**  `stale_seq` and `version_floor` are separated
  here; in the shipped engine they share `_stale_skips` and mean
  opposite things.  `seat_stands` is the user's "keep only the last
  seat" already working, counted.
* **Redundant decoding.**  `redundant_input` is per (plugin, subject):
  this subject decoded this exact input before.  `input_digest_bare` is
  the assembled cut WITHOUT the stage, so the reducer's "Evidence
  decoded more than once" section joins a `tiles.retry` at 150
  iterations to the `tiles.scan` at 60 that armed it — TILE-5's claim,
  measured rather than argued.
* **What jobs actually said.**  "What the jobs' own facts said" carries
  the attempt outcomes and the refinement rows' adopt/refuse reason,
  which the folds swallow and no event carries (HR-3's open question).
* **Work the folds threw away.**  `n_facts_refused` per fire.
* **Which interpreter.**  `summary["runtime"]` carries
  `sys._is_gil_enabled()`.  A low worker utilisation has two very
  different explanations — a serialised main thread, or GIL contention
  among the workers (holo2 measured a 1.01× thread ceiling with BCH at
  ~72 % of CPU) — and no archived run in this project records which
  interpreter it ran on.  On `env/` this reads `gil_enabled: false`,
  which retires the second explanation outright.

## What this instrumentation CANNOT tell us

Stated plainly, so nobody reads a number it does not contain.

1. **The resumed regime.**  This is a from-scratch run.  e036's idle
   resume retires 18,256 place workers; a from-scratch run retires none,
   because a placed window's `stage` returns None, so it is never pushed
   and never popped and `retire` is never asked.  FM-3, P1, P2, P4 and
   the index-size questions have OPPOSITE answers in the two regimes.
   A second run — `--resume` over the same capture from this run's own
   `facts.npz` — is the only way to get them, and it is cheap compared
   to this one because most of the work is already certified.
2. **The 13-capture scaling.**  One capture.  Every term the lenses
   flagged as O(captures) — `union_rung_ordinal` (0.87 µs at 1 capture,
   8.6 µs at 13), `cover_lanes`, `neighbourhood_tiles`, the
   `lane_poses` hub, `fields.collect`'s whole-capture prepare — is
   measured here at its SMALLEST.  Multiply nothing; re-run with the
   captures if the scaling is the question.
3. **Attribution inside a job.**  `cpu_s` and `wall_s` are per fire.
   Nothing here splits `run_window_pass` into crop / fit / sample /
   seed-search / word / cold (P5 asked for that), and nothing profiles
   the BCH inner loop.  That needs timers inside the plugins, which is
   a separate change.
4. **Why a wake was redundant.**  When a fire's input digest repeats,
   the trace says THAT it repeated, not which of the three causes
   (ownership lost every contested cell, only a fit-diagnostic field
   moved, the colour row's loss moved without its values) produced it.
   TILE-4's per-field fold counters were not built; they would need
   hooks in `store_folds.py` and were judged out of scope for a run
   whose first job is to size the main thread.
5. **Rows with no digest hook.**  `place`, `survey`, `calibrate`, `ctx`,
   `tiles.planek`, `tiles.uplift`, `fields`,
   `fields.collect` and `color.pooled_ctx` record
   `input_digest: null` and `redundant_input: null` — NOT `false`.
   Their repetition must be inferred offline from `wakes_since_last_fire`
   and `version_at_fire`.  `tiles.local`, `tiles.swim` (since
   2026-10-03, kind `swim_inputs`: the covering windows and their poses,
   the field revision and the neighbourhood's certified tile-streams;
   the bare digest drops the stage and the armed streams) and `color`
   carry a documented PROXY (donor set, window poses, lane shape)
   rather than the real decode input,
   because digesting the real one would move the plugin's own work onto
   the engine thread and corrupt the main-thread measurement this run
   exists to make.
6. **The timeline's resolution.**  The sample is taken at the top of the
   engine loop, so its cadence is bounded by how often that loop turns.
   On a real sheet with twelve workers and thousands of short jobs that
   is many times a second; on a page whose workers are all inside one
   long job it can be minutes (measured on the colour sim: four 15 s
   `place` jobs saturating four workers produced two samples in 18 s).
   A sparse stretch in `timeline.jsonl` means the workers were busy, not
   that the instrument stopped.
7. **Any counterfactual.**  Nothing here measures what a FIX would buy.
   Every mitigation the lenses proposed still needs its own A/B, and
   several of them (the colour-refit gate, the field-magnitude gate, the
   done-gate relaxation) are yield questions that a sim cannot answer
   and a single sheet cannot promote.

## The enumerated table this branch amended

By ADDING this module with its reason, not by weakening the law behind
it.

* `test_h3_hygiene.py`'s `WALL_LICENSED` carries `"sched_trace.py": 10`.
  The meter-vs-clock ruling bans wall clocks in production save
  enumerated sites; this module is ten of them and is nothing but
  wall clocks, because it IS the measurement.

The one table it amends is that one. (An earlier text of this page
named a second, a clock-reader list in `test_h3_drift_declared.py`
gaining this module under a renamed test; no such change was ever made,
and that module's clock check is a declared v1 divergence that does
not enumerate modules. Corrected 2026-10-18, SCHED-LIFECYCLE-REVIEW-2026-10-17 §4.)

The ruling's substance is untouched: no scheduling decision reads the
trace back, and with the environment variable unset the module is a
null object holding no clock at all.
