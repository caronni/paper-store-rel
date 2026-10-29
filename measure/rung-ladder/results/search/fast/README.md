# fast/ — a batched, bit-exact decoder for the rung-ladder search

The question: on the free-threaded interpreter, can numpy be made to decode faster for
the overnight search? **Yes, about 1.6x wall at the 10 % point, with every outcome
unchanged. The gain comes from batching the decoder, not from threads.** Processes stay
the right worker mode.

Nothing outside this directory was touched. Nothing is committed.

## API

```python
from fastdecode import decode_batch, selfcheck          # fast/fastdecode.py
ok, hard, n_iters = decode_batch(llrs, code, max_iters=60, alpha=0.8)
#   llrs   (B, n) or (n,) float64, HOUSE convention (+ = bit 1, 0.0 = erasure, +-inf = known)
#   code   construct.Code  (construct.load_code(rid); registered search codes work)
#   ok     (B,) bool   hard (B, n) uint8   n_iters (B,) int64
#   return_extrinsic=True adds (B, n) float64 == production decode_soft()'s 4th output
selfcheck(rid) -> bool     # 24 trials vs production decode(), ~1 s; use it as a start-up guard

from tasks_fast import run_chan_fast, run_task_fast      # fast/tasks_fast.py
run_chan_fast(rid, channel, params, t0, n, batch=64)       == search/common.run_chan(...)   (dict incl. und_w)
run_task_fast(rid, channel, params, t0, n_trials, batch=64) == harness/channels.run_task(...)
```

`decode_batch` uses the same schedule as production `_run`/`_bp_loop`. It clips to ±20,
maps ±inf to ±1e9 and negates. It runs normalized min-sum, which stops early on a zero
syndrome. It then runs ONE sum-product pass from the channel LLRs, but only on the rows
where min-sum failed. `n_iters` counts min-sum iterations plus SP iterations, following
production's break rule, so a trial that is already clean returns 0. A row that converges
is recorded at that iteration and then dropped from the batch, so later iterations only
compute on the rows still active.

`decode_batch_simple` is also in the file: a straight (rows, E) transcription using
reduceat. It serves as a second witness and is not the fast path.

## Why it is exact: every operation is production's, in production's order

- The kernel lays edges out **edge-major, grouped by degree**. A block of checks with
  degree d is a contiguous (d, m_d, rows) array, and slot j holds each check's j-th edge
  in production order. Variables are laid out the same way.
- Min, first-argmin, min-over-the-rest and XOR parity give the same result in any order.
  Min-sum uses a streaming top-2 where a strict `<` keeps the first minimum, which is the
  same as production's `pos_m`/`first`/`mag2[first]=inf`.
- There are two float sums: the SP log-sum per check and the belief sum per variable.
  Both reproduce numpy's reduceat order exactly, which is `x0 + pairwise_sum(x1..)`:
  - with fewer than 8 remaining terms, a sequential sum starting from -0.0;
  - otherwise numpy's 8-accumulator block plus the tail.

  `_seg_sum` implements this. The test checks it against `np.add.reduceat` itself over
  degrees 1..40, signed zeros included: 0 mismatches.

## Bit-exactness evidence (the acceptance gate): PASS

`test_fastdecode.py` covers 9 codes: the six frozen ones plus r0406, r0250 and r0391-h14.
The last one exercises var degree 14; r0850 exercises check degree 27. Each code gets 300
LLR vectors across these settings:
- BSC at five p values, including a clean 1e-4, so the 0-iteration path is covered;
- BIAWGN at three Es/N0 values (the ±20 clip is active);
- two erasure+error mixes;
- ±inf known bits, including confidently wrong ones;
- exact +0.0 / −0.0 zeros.

The comparison covers `(ok, hard, n_iters)` **and the extrinsic array byte for byte**.
Kernels compared: `decode_batch` at B ∈ {1, 8, 64} and `decode_batch_simple` at 64.
There is also a `max_iters` ∈ {0, 1, 5} edge case.

**10,800 decode comparisons, 0 mismatches.** Every code has 14–19 zero-iteration trials
and 131–222 min-sum failures that went to SP. Details are in `bitexact_result.json`.

`test_tasks_fast.py` compares `run_chan_fast` against `common.run_chan` (bsc, awgn, eras,
robust) and `run_task_fast` against `channels.run_task` (every harness channel, including
the accom variants and record). It covers 3 codes at batch 7 and 64: **30 cases, dicts
equal**. One weakness: none of the run_chan cases produced an undetected error, so `und_w`
was only compared as an empty list. The harness path's undetected counter did fire once.

## Single-thread throughput (quiet host, numpy 2.5.3 on aarch64, `bench_single.py`)

The workload is BIAWGN with the same trials for every column. conv = about the 10 % BLER
point; fail = far below threshold, so every trial runs 60 min-sum + 60 SP iterations.
Figures are decodes/s, with the speedup over production in brackets.

| code | regime | prod | B=1 | B=8 | B=32 | B=64 | B=128 | simple B=64 |
|---|---|---|---|---|---|---|---|---|
| k=1664 r0406 | conv −3.1 dB, 81.5 it | 42.2 | 45.1 (1.07) | 68.1 (1.61) | **72.8 (1.72)** | 71.8 (1.70) | 69.4 (1.64) | 47.4 (1.12) |
| k=1664 r0406 | fail −4.25 dB, 120 it | 26.6 | 27.5 (1.03) | 39.2 (1.47) | **40.5 (1.52)** | 40.4 (1.52) | 40.2 (1.51) | 28.0 (1.05) |
| k=2240 r0550 | conv −1.35 dB, 52.8 it | 68.2 | 58.7 (0.86) | 92.5 (1.36) | **104.0 (1.52)** | 103.8 (1.52) | 101.1 (1.48) | 77.4 (1.14) |
| k=2240 r0550 | fail −2.25 dB, 120 it | 26.5 | 23.5 (0.89) | 35.9 (1.35) | **37.3 (1.41)** | 37.0 (1.40) | 36.9 (1.39) | 28.3 (1.07) |

Per iteration at k=1664 (E = 13,439 edges):
- **min-sum: 264 → 116 µs (2.3x)**;
- **sum-product: 359 → 292 µs (1.23x)**.

SP has a floor that cannot be moved. numpy's `tanh`, `exp`, `log` and `arctanh` together
take about 13.7 ns per edge, roughly 184 µs per iteration. Bit-exactness forbids replacing
them.

Where batching loses:
1. B=1 is no faster than production, and is 0.86x on the k=2240 codes because of the
   per-degree-group Python overhead.
2. Beyond B≈32, larger batches do not help, and B=128 is slightly worse. Its working set
   no longer fits in cache, and the few slow rows at the end iterate with only a handful
   of columns, so there is little to amortize the fixed per-call overhead.
3. The SP phase caps failing points at about 1.4–1.5x.

Compaction means a slow row does not hold back the finished ones; only the fixed per-call
cost stays high while few rows remain.

## Worker modes (the free-threading question): `bench_workers.py`, `run_bench_workers.sh`

The workload is 5,600 decodes of r0406 at −3.1 dB. Each task generates its own trials from
seeds, just as the search does. Each row ran in a fresh interpreter, with pools warmed
before timing. The environment was `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=VECLIB_MAXIMUM_THREADS=1`.
"task CPU" is the thread CPU time inside the tasks.

| decoder | mode | chunk=B | wall s | dec/s | task CPU ms/dec | CPU/wall | peak RSS |
|---|---|---|---|---|---|---|---|
| batch | **14 processes** | 50 | **8.37** | **669** | 18.6 | 12.4 | 158 MB × 14 |
| batch | 14 threads | 50 | 8.98 | 623 | 19.6 | 12.2 | 970 MB (one proc) |
| batch | 7 proc × 2 thr | 50 | 9.28 | 603 | 19.9 | 12.0 | 234 MB × 7 |
| batch | 14 processes | 16 | 8.51 | 658 | 20.1 | 13.3 | 101 MB × 14 |
| batch | 14 threads | 16 | 8.67 | 646 | 20.5 | 13.3 | 489 MB |
| batch | 12 processes | 50 | 9.78 | 573 | 18.6 | 10.7 | 149 MB × 12 |
| batch | 12 threads | 50 | 9.86 | 568 | 18.6 | 10.6 | 848 MB |
| prod | 14 processes | 50 | 13.44 | 417 | 31.9 | 13.3 | 64 MB × 14 |
| prod | 14 threads | 50 | 16.13 | 347 | 38.4 | 13.3 | 140 MB |
| prod | 7 proc × 2 thr | 50 | 14.52 | 386 | 34.2 | 13.2 | 74 MB × 7 |

All ten rows produce the same outcome digest (`71bd0470da6e0076`, covering per-trial ok,
n_iters and a hash of the hard bits). This is also evidence that the batched decoder is
thread-safe.

The first attempt ran while another agent had 15 niced workers busy. Under that
contention: batch 470 / 481 / 480 dec/s and production 258 / 223 / 269 dec/s
(proc / thr / hyb). The ordering matched but the level did not; the table above is the
quiet rerun. It is one repetition.

What this means:
- **numpy does not get faster from free-threading.** Every call here runs single-threaded
  on 13–17k edges, and BLAS is never touched. Free-threading only lets threads share one
  process.
- **Threads never beat processes.** They were about 7 % slower with the batched kernel
  and about 17 % slower with production, which also used +20 % CPU per decode. Production
  makes about 30 small numpy calls per iteration on shared arrays. My hypothesis (not
  measured) is refcount and allocator contention on objects shared across threads. The
  batched kernel makes about 10x fewer numpy calls per decode-iteration (about 200 per
  iteration, shared by a batch of 50), so it barely notices.
- **Threads do save memory:** 970 MB instead of 14 × 158 MB, but that does not matter on
  this 128 GB host.
- **Parallel efficiency is the same for both decoders.** Relative to one thread, per-decode
  CPU rises about 1.35x at 14 workers (18.6 vs 13.9 ms batched, 31.9 vs 23.7 ms
  production). Likely causes are memory bandwidth and the 12P+4E core mix, so 14 workers
  land on two E-cores.

**Environment variables.** This numpy links **Apple Accelerate** (`np.show_config()`), so
the knob that actually applies is **`VECLIB_MAXIMUM_THREADS=1`**. `OMP_NUM_THREADS` and
`OPENBLAS_NUM_THREADS` do nothing on this build; they are correct if the env is ever
rebuilt against OpenBLAS.

The decoder itself never calls BLAS. The structural audit's `H @ H.T`
(harness/structure.py) goes through scipy.sparse, which is its own single-threaded C++
with no BLAS, so today there is nothing to oversubscribe. The variables are defensive: any
dense `@` or `np.linalg` call in a worker would otherwise start one BLAS thread per core
in each of 14 workers. `common.Runner` already sets OMP and OPENBLAS with setdefault; add
`VECLIB_MAXIMUM_THREADS` there too.

## Recommended settings for the overnight driver (`--decoder fast`)

1. In `task_chan`, call
   `tasks_fast.run_chan_fast(rid, channel, params, t0, n, batch=min(n, 64))` in place of
   `run_chan(...)`. It takes the same arguments and returns the same dict, `und_w`
   included. The fast directory needs to be on sys.path; tasks_fast inserts the harness
   path itself.
2. Keep **ProcessPoolExecutor (spawn), 14 workers**. Use **task chunks of 32–64 trials**
   (50 measured); batch = the chunk. 16 is nearly as good and halves RSS.
3. Set `VECLIB_MAXIMUM_THREADS=1`, `OMP_NUM_THREADS=1` and `OPENBLAS_NUM_THREADS=1` in the
   parent before the pool spawns.
4. At start-up, call `fastdecode.selfcheck("r0406")` (or the first code) and refuse to run
   `--decoder fast` if it returns False.

Expected gain: about 1.6x decodes/s at the 10 % points. Points dominated by SP failures
gain about 1.4x; easy points dominated by min-sum gain up to about 2x.

## Caveats

- **Exactness is a property of this numpy build.** It relies on numpy's float-add reduceat
  order and on elementwise ufunc results not depending on array position (SIMD tails).
  This was verified on numpy 2.5.3 on aarch64. **Re-run `test_fastdecode.py` (about 1 min)
  after any numpy upgrade or on another machine**; `selfcheck` is only a smoke test.
- `tasks_fast.py` **copies** the trial-generation code of `common.run_chan` and
  `channels.run_task`, because neither file is ours to edit. `common.py` changed while
  this was being built: `run_robust` was folded into `run_chan`. Re-run
  `test_tasks_fast.py` whenever either file changes.
- The speedup is capped by SP's transcendental functions. Any further 2x would need
  non-numpy code (numba or C), and those use a different libm, which breaks bit-exactness
  with numpy's `tanh`/`arctanh`. That is not worth it under this contract.
- Memory: a B=50 batch adds about 70 MB per worker; peak RSS is 122 MB against a 52 MB
  baseline.
- Benchmarks come from one quiet window on a shared machine, one repetition each.
