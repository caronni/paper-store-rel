# Why the holo2 worker pool buys no wall time — GIL diagnosis

**Date** 2026-08-16 · **Tree under measurement** `<checkout>`
(pinned worktree, `d23c756`, unmodified) · **Fixture** gen-clean
`scratch/holo2-demo/e028-genclean-c2-r0700.tiff` @1200 dpi ·
**Machine** Apple M1 Max, 10 cores (8P + 2E), CPython **3.14.6 with the GIL
ENABLED** (`sys._is_gil_enabled() → True`, `Py_GIL_DISABLED` unset),
numpy 2.5.0, `sys.getswitchinterval()` 5 ms.

Every run below closed **VERIFIED** and **BYTE-IDENTICAL** to
`w1a-gc-serial.bin` (465,580 B, sha `e5021f8d099587c3`). All clocks are
driver-side (L12); nothing in the worktree was touched. Instruments:
`scratch/holo2-demo/run_decode_gil.py` (new), `gil_kernels.py` (new),
`gil_runs.sh` (new).

---

## (a) THE VERDICT: GIL serialization, essentially total

**Hypothesis confirmed: GIL queuing.** Not memory bandwidth, not the
main-thread commit path. The pool never runs more than ~1.17 cores' worth
of work no matter how many threads it has, and the extra cores it does
acquire are spent entirely on the cost of switching between threads that
are queuing for the same lock.

### Step 0 — the free evidence already proved it

From the operator's existing `w2exit-gc-w{1,2,4,8}.log` (`/usr/bin/time -l`),
before any new run:

| W | wall s | user s | sys s | **CPU s** | **cores used** | par-eff | IPC | involuntary ctx-sw | /s |
|---|-------:|-------:|------:|----------:|---------------:|--------:|----:|-------------------:|---:|
| 1 | 536.9 | 533.0 | 2.4 | **535.4** | **0.997** | 99.7% | 4.81 | 10,109 | 19 |
| 2 | 525.8 | 546.3 | 6.2 | **552.5** | **1.051** | 52.5% | 4.74 | 1,278,072 | 2,431 |
| 4 | 550.3 | 578.1 | 26.2 | **604.3** | **1.098** | 27.5% | 4.50 | 6,362,808 | 11,562 |
| 8 | 591.8 | 613.3 | 81.4 | **694.7** | **1.174** | 14.7% | 4.10 | 11,760,878 | 19,873 |

Total CPU never exceeds **1.174 cores** on a 10-core machine. At W=8 the
process owns 8 runnable threads and executes 1.17 cores of work: **6.8 of
every 8 thread-seconds are spent not executing.** That is GIL
serialization, provable from the free counters alone.

Where the extra 159 CPU-seconds went (w1 → w8): `sys` +79.0 s (0.4% → 11.7%
of CPU — pure kernel switching cost, ~7 µs per involuntary switch),
`user` +80.3 s. Instructions retired grew only **+6.0%** while cycles grew
**+24.2%**, so **IPC fell 4.81 → 4.10 (−14.7%)**: the machine is stalling
more per instruction (cache/TLB churn from 20 k preemptions/second), but
it is not executing meaningfully more work. A memory-bandwidth wall would
have shown the opposite signature — instructions flat, cycles up, *and*
per-thread CPU rising in proportion to wall. It does not (below).

### Step 2 — the discriminator, measured

`run_decode_gil.py` clocks every fire on its own thread with two clocks:
`perf_counter` (elapsed) and `time.thread_time` (on-core). Their
difference is off-core time = GIL queuing + preemption.

| run | W | wall s | **fire CPU s** | **fire wall s** | **lock-wait s** | lock-wait % of fire wall | fire CPU / wall | main CPU s |
|-----|---|-------:|---------------:|----------------:|----------------:|-------------------------:|----------------:|-----------:|
| gil-w1b | 1 | 563.8 | **459.4** | 464.0 | 4.6 | **1.0%** | 0.815 c | 557.0 † |
| gil-w4 | 4 | 581.7 | **531.3** | 2069.2 | 1537.9 | **74.3%** | 0.913 c | 102.0 |
| gil-w8 | 8 | 597.9 | **593.5** | 4282.0 | 3688.5 | **86.1%** | 0.993 c | 96.2 |

† W=1 takes `_run_serial` (no pool at all — `_pool_size > 1` gates
`_run_pool`), so at W=1 the fires run **on** the main thread and main CPU
includes them. Main-thread-only CPU at W=1 = 557.0 − 459.4 = **97.6 s**,
matching the 96–102 s measured at W=4/8. This is the serial floor and it
is stable across rungs.

**Read the two middle columns.** From W=1 to W=8 the fires' *wall* inflates
**9.2×** (464 s → 4282 s) while their *thread CPU* inflates only **1.29×**
(459 s → 594 s). That is the pre-registered GIL signature exactly: wall
grows, on-core time does not. Bandwidth contention would have grown the
thread CPU roughly in step with the wall.

Same fact from the pool's side:

```
gil-w4:  pool thread-seconds 2327 · 89% spent inside a fire · only 23% on a core
gil-w8:  pool thread-seconds 4783 · 90% spent inside a fire · only 12% on a core
gil-w1b: main  thread-seconds  564 · 82% spent inside a fire ·      82% on a core
```

The 1.29× thread-CPU inflation is the *secondary* term (cache/TLB
reload after preemption), and it is concentrated in the small fires: the
median place fire's own CPU goes 80 ms → 171 ms → 275 ms (W=1/4/8) while
the p90 (the long word sweeps, which hold the GIL in long uninterrupted
tenures) is flat at 3224 → 3373 → 3405 ms (+5.6%). Long GIL tenure is
cheap; churn is expensive.

**The main thread is not the bottleneck.** At W=4/8 it burns 102 / 96 s of
CPU against a ~590 s wall (17% / 16%), and 76–78% of its samples are
blocked in `threading.wait` inside `_admit_completed`. It is a serial
*floor* (§(c)), not the current wall.

### Step 2b — the switch-interval probe (the clincher)

A GIL-queuing wall moves with `sys.setswitchinterval`; a bandwidth wall is
indifferent to it. A driver-side monitor thread sleeps 5 ms in a loop; the
overshoot past the requested sleep is GIL-acquisition latency.

| W=4 run | switch interval | GIL latency mean / p90 / p99 ms | wall s | sys s | fire CPU s |
|---|---:|---:|---:|---:|---:|
| gil-w4-sw1 | 1 ms | **3.60 / 6.91 / 12.88** | 555.4 | 31.9 | 511.4 |
| gil-w4 | 5 ms (default) | **9.32 / 21.42 / 44.46** | 582.2 | 38.2 | 531.3 |
| gil-w4-sw50 | 50 ms | **36.02 / 91.58 / 211.92** | 540.9 | 24.8 | 503.2 |
| gil-w1b (reference) | 5 ms | 5.98 / 7.56 / 7.60 | 564.4 | 6.0 | 459.4 |

Acquisition latency tracks the switch interval across a **50× sweep**
(10× on the mean, 13× on p90, 16× on p99). Nothing about memory bandwidth
depends on `sys.setswitchinterval`. **This is the GIL.**

Note also what the dial does *not* buy: every W=4 setting lands between
541 s and 582 s — never better than W=1's 537–567 s. The interval only
redistributes the queue; it cannot create parallelism.

---

## (b) WHERE the GIL time goes

**By family: placement, overwhelmingly.** Per-route fire CPU is stable
across all rungs:

```
place/pull (source jobs) : 99.4–99.6% of fire CPU   (622–670 fires)
payload/scan (LDPC tiles):  0.4–0.6% of fire CPU  (1701–1708 fires)
```

The place fires are violently heavy-tailed — CPU p50 80 ms, p90 3.27 s;
**the top 10% of fires hold 44% of place CPU and the top 25% hold 83%**.
The long ones are the Stage-A cold word sweeps.

**By kernel, CPU-weighted** (from `gil-w1b`: at W=1 wall ≈ CPU at 0.995
cores, so main-thread sample shares *are* CPU shares; 44,857 samples):

| kernel group | share of total CPU |
|---|---:|
| **`format/bch.py` — Stage-A word decode** | **65.4%** |
| `solve/words.py:_gather_slot` (same sweep) | 6.4% |
| `scipy.ndimage.map_coordinates` | 5.1% |
| `solve/pose_audit.py` (`evaluate`, `parity_score`) | 4.2% |
| `solve/pose_fit.py:_fit_phase` | 1.4% |
| store keys / journal / blobs (main-thread commit) | 9.8% |
| LDPC `_bp_loop` | <0.5% |

So **~72% of the receiver's CPU is the Stage-A BCH word sweep**, and
inside it the two dominant leaves are:

* **`bch._chien_roots` — 30.0%** of all CPU. A Python `for j, cj in
  enumerate(sigma)` loop (≤27 iterations) doing numpy ops on **127-element
  uint8** arrays. At that size numpy is pure dispatch overhead and the GIL
  is effectively never released.
* **`bch._berlekamp_massey` — 25.1%** of all CPU (lines 252/255/265/267/271).
  **100% pure-Python scalar GF(2^7) arithmetic** — list indexing, `%`,
  `^`. GIL-bound by construction.

Both are reached the same way, ~2,000× per sweep:
`place_job.run → placement.decode_word_address → words.stage_a →
words._decode_candidates → bch.decode_many → bch._decode_syndromes`.
`decode_many` vectorizes only the initial syndrome screen; BM, Chien, the
shortened-position refusal and the final re-check stay a Python list
comprehension over every candidate row.

**Where the threads *wait* is a different (and complementary) list.** The
pool-thread stack sampler is wall-weighted, so it shows the code with the
most GIL *handoffs* per unit of work, not the most CPU. At W=8:

```
39.3%  pose_audit:evaluate (lines 504/510/513) < refine_patch_pose < place_addressed
12.1%  scipy ndimage map_coordinates  (9.6% under evaluate, 2.3% under _fit_phase)
16.2%  the bch sweep (chien 5.7, BM 4.4, isin 2.9, gather 2.2, syndromes 1.4)
 4.1%  pose_fit:_fit_phase
 2.6%  ldpc _bp_loop
11.7%  idle pool threads blocked on the executor queue
```

At W=4 the same list is BCH-first (31.6%) and `evaluate` second (20.0%);
the share migrates to `evaluate` as W grows. That migration *is* the
diagnosis: `pose_audit.refine_patch_pose` runs a **triple-nested Python
grid loop — 7 angles × 9 dy × 9 dx = 567 calls** to its `evaluate` closure
per placed window, and each call does ~8 small numpy operations (a 2×2
rotation, an N×2 @ 2×2, one `map_coordinates` over N≈60–500 sites, two
`np.mean` over boolean-masked N-vectors). That is ~4,500 GIL
release/acquire points per window on arrays far too small to amortise
anything — the maximum-contention shape.

---

## (c) THE EXPECTED-PARALLELISM ACCOUNTING

### How much of the work is GIL-free?

Measured directly per kernel (`gil_kernels.py`): run the *same total work*
serially and split across 4 threads; under a GIL a kernel that releases it
for a fraction *f* of its time scales as `S = W / ((1−f)·W + f)`, so
`f = W(1 − 1/S)/(W − 1)`.

| kernel | 4-thread speedup | **GIL-free fraction f** |
|---|---:|---:|
| *control* `np.exp` on 4 M float64 | **3.86×** | **0.99** |
| *control* pure-Python loop | 1.01× | 0.02 |
| *control* `np.dot` 2048² (Accelerate BLAS) | 0.86× | — ‡ |
| **`bch.decode_many`** H=64 / 256 / 1024 | 0.99 / 1.00 / 1.02× | **0.00 / 0.00 / 0.02** |
| **`bch._chien_roots`** | 1.00× | **0.00** |
| **`bch._berlekamp_massey`** | 1.00× | **0.00** |
| `ndimage.map_coordinates` N=64 / 128 / 256 | 0.64 / 0.66 / 0.85× | **0.00** |
| `ndimage.map_coordinates` N=512 / 4096 / 16384 | 1.31 / 1.18 / 1.52× | 0.32 / 0.20 / 0.46 |
| `pose_audit.evaluate`'s numpy lines N=256/1024/4096 | 0.70 / 0.60 / 1.00× | **0.00** |
| **`ldpc.decode_soft` r0700** | **1.88×** | **0.63** |

‡ Accelerate BLAS is already internally threaded, so 4 Python threads
oversubscribe it; the `np.exp` control is the valid positive control and
it proves the harness detects real GIL release (3.86× of a possible 4×).

**Weighting those by the CPU shares in (b):** the only kernel with a real
GIL-free fraction is `ldpc.decode_soft` (f = 0.63) and it is **0.4% of fire
CPU**. `map_coordinates` reaches f > 0 only above N ≈ 512 points, above the
sizes these call sites use. Everything else measures f = 0.

> **GIL-free fraction of the receiver's work: well under 1%.**
> **Thread-level Amdahl ceiling: S ≤ 1/(1 − f) ≈ 1.01×.**

Measured speedups: 1.02× (W=2), 0.98× (W=4), 0.91× (W=8). **Theory and
measurement agree exactly.** The pool is not underperforming its ceiling —
its ceiling is 1.0, and past W=2 it pays switching overhead on top.

### What parallelism *would* be worth, if the GIL were gone

Serial decomposition at W=1 (`gil-w1b`, wall 563.8 s):

* **parallelizable fires: 459.4 s CPU** (place 457.3 + payload 2.0)
* **irreducibly serial: 104.5 s** — the main thread's commit path (L11:
  one commit site, `_apply` 81.8 s + dispatch/journal/queue ≈ 16 s) plus
  ~5 s idle

| W | ideal wall (fires perfectly parallel) | ideal speedup | **measured** |
|---|---:|---:|---:|
| 2 | 334 s | 1.69× | **1.02×** |
| 4 | 219 s | 2.57× | **0.98×** |
| 8 | 162 s | 3.48× | **0.91×** |
| 16 | 133 s | 4.23× | — |
| ∞ | 104 s | **5.40×** | — |

So the prize is real but bounded: **~3.5× at 8 workers, 5.4× asymptotically**,
and the ceiling is set by the serial commit path, which is 18.5% of wall.
Beyond ~8 workers the fire tail also starts to bind (the longest single
place fire is 3.3 s of CPU).

---

## (d) REMEDIATION MENU — analysis only, nothing built

Roughly costed, in ascending order of build cost. **Nothing here was
implemented and none of it is recommended without its own measure-first
gate.**

### 1. Free-threaded CPython 3.14t — *the cheapest test of the hypothesis*

**Cost: low (a second venv, zero repo changes).** The env is already
3.14.6; a `python3.14t` build plus free-threaded numpy/scipy wheels would
run the receiver unchanged and settle the ceiling empirically.
Architecturally the receiver is already shaped for it: `_propose` is
*commit-free by construction* ("Commit-free, hence poolable"), the fires
read a generation-pinned view, all mutation happens at one commit site on
the main thread (L11), and `prepared.py`'s planes are read-only memmaps.
That is precisely the invariant free-threading needs.
**Risks:** 3.14t is ~5–10% slower single-threaded, so W=1 regresses;
free-threaded scipy wheel availability needs checking; and the "no data
races" claim would move from *by-design* to *load-bearing*, so it would
want a byte-identical-output gate across rungs (which the current runs
already demonstrate at 6/6).
**Expected payoff: up to the 3.5×/5.4× ceiling above.**

### 2. Vectorize the top GIL-bound kernels — *helps every rung, including W=1*

This does not create parallelism; it removes CPU and GIL handoffs, which
is the only lever that pays off *today* on the serial path.

* **`pose_audit.refine_patch_pose` / `evaluate` (cost: medium).** Batch the
  567-point (angle, dy, dx) grid into **one** `map_coordinates` call over
  567×N stacked points and one `(567, N)` vectorized reduction, replacing
  ~4,500 tiny numpy calls per window with ~5 large ones. This is also the
  #1 *contention* site (39% of pool-thread wall at W=8), and at 567×N ≈
  100 k points `map_coordinates` lands in the f ≈ 0.46 regime — so it
  becomes partly GIL-free as a bonus. Constraint: the refined poses are
  golden-pinned, so the reduction must be bit-exact (float64
  order-of-operations care on the two `np.mean`s).
* **`bch._berlekamp_massey` + `_chien_roots` (cost: medium-high).**
  Together 55% of all CPU. `_chien_roots` is already numpy but at 127
  elements — batch it to `(H, 127)` over all surviving candidates in one
  `decode_many` call. `_berlekamp_massey` is pure Python scalar GF(2^7);
  a batched BM over all candidate rows is a known but fiddly rewrite.
  **Caution: `format/bch.py` is normative format code** (the (127,50,t=13)
  → (100,23) code, d=27 spectrum 27:3/28:8/31:119/32:247 exact). Any
  change must be bit-exact against the frozen goldens — a mismatch is a
  format fork, not an optimization.
* **Cheaper first cut, same file:** `bch._as_words` currently reaches
  `np.isin` (2.9% of pool-thread wall at W=8) for validation on *every*
  `decode_many` call; and `decode_many` runs BM on rows that could be
  screened earlier. Low-risk, measurable.

### 3. Process pool for the placement fires — *the structurally correct fix*

**Cost: high.** But the pixel problem is already solved: `solve/prepared.py`
builds the three float32 planes **streaming into files** in
`<state-dir>.prepared/`, opened by every fire as a read-only `np.memmap`,
named by a content digest of everything they are a function of. **A child
process can open the identical files with zero copy and zero pickling** —
this is the single biggest reason a process pool is even plausible here.

What would still have to cross the boundary:

* **In (small, cheap):** `WorkDescriptor` / `AttemptIdentity` / read-set
  `ResourceKey`s, `PlacementConfig`, the coding+printer ids. The
  `FormatRowSpec` and `V1ReferenceField` should be **rebuilt in the child**
  rather than pickled — `V1ReferenceField` is a pure function of the
  `TileFormat` spec with a per-page memo, so one warm child amortises it.
* **In (the real work):** the fire's **generation-pinned `PlaneView`**.
  `place_job.run` reads `plane.window_is_done`, `plane.poses_of_window`,
  `consult(view, …)`, the lattice seeds. Today that is a live view over the
  store. A process pool needs either a serializable read-set slice per
  fire or a shared read-only snapshot of the pinned generation. **This is
  the design work**, and it is engine-contract-adjacent (§7 re-derives
  identity at admission; the current `_is_current` staleness check would
  have to survive unchanged).
* **Out:** `WorkResult.writes` (small records, picklable) and
  `WorkResult.blobs`. Blobs are already **content-addressed staged files**
  (`core/blobs.py: StagedBlob` / `store.put_staged`), so a child can stage
  to disk and return a path — no array pickling needed.

**No format change; determinism preserved** (commits already land on one
thread in completion order, and all six runs here are byte-identical
across W ∈ {1,4,8} and three switch intervals).
**Payoff: the same ~3.5× at W=8**, with a real IPC/serialization tax
subtracted — call it 2.5–3× realistic.

### What is NOT worth doing

* **More threads.** W=8 is already 9% *slower* than W=1 and W=16 would be
  worse — the switching cost is superlinear in thread count (sys 2.4 s →
  81.4 s across the rungs).
* **Tuning `sys.setswitchinterval` in production.** The 50× sweep moves
  the wall by ≤7% and never past the W=1 baseline. It is a diagnostic, not
  a fix.
* **Attacking the main-thread commit path first.** It is 17% of wall and
  the 5.4× ceiling's owner, but it is not what is costing time *now*.

---

## Method notes / caveats

* **Instrumentation overhead ≈ 5%**: the instrumented runs are 567/582/598 s
  against the operator's clean 537/550/592 s at W=1/4/8. Internally
  consistent; all comparisons here are within the instrumented set or
  within the clean set, never across.
* **W=1 is a different code path** (`_run_serial`, no `ThreadPoolExecutor`
  at all). W=2 is the first pooled rung. This does not affect the verdict —
  W=2 already burns 1.28 M involuntary switches for a 1.02× "speedup".
* **Stack-sampler semantics**: `sys._current_frames()` shows the *Python*
  frame even when a thread is inside a C call, and samples are
  wall-weighted per thread. The CPU-weighted profile therefore comes from
  the W=1 run (where wall ≈ CPU) and the contention profile from W=4/8.
  Both are reported, and they are meant to be read as different questions.
* **py-spy was not used.** It is not installed, and installing it would put
  a console script into the user's venv against a standing rule; the
  driver-side sampler covers the same ground. (macOS would likely have
  demanded sudo for attach in any case.)
* **Nothing in the worktree or in `src/holo2` was edited**, no tests were
  run, nothing was committed. New files, all in scratch:
  `scratch/holo2-demo/run_decode_gil.py`, `gil_kernels.py`, `gil_runs.sh`,
  the five `gil-*.log` / `gil-*.gil.json` / `gil-*.raw.pkl` sets, and this
  report.
