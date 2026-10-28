# measure/accel — compute acceleration, measured

Two questions, asked separately, answered with numbers only. Nothing in
this directory is imported by holo3; nothing here proposes adopting
anything.

Host for every number below: Apple M1 Max (8 performance + 2 efficiency
cores, 32-core GPU, 64 GB), macOS 26.5.2.

## Reproducing

```sh
W=<worktree root>
V=$W/scratch/accel/venv          # python3.13 + mlx + numpy + scipy
E=<checkout>/env314t   # the working free-threaded venv

# (a) linkage + per-op costs
$E/bin/python                      $W/measure/accel/blas_probe.py --out OUT
PYTHONPATH=$W $E/bin/python        $W/measure/accel/shapes.py     --out CENSUS
PYTHONPATH=$W VECLIB_MAXIMUM_THREADS=1 $E/bin/python \
                                   $W/measure/accel/op_bench.py   --out OUT

# (b) batched belief propagation on Metal
PYTHONPATH=$W $E/bin/python  $W/measure/accel/corpus.py         --out CORPUS
PYTHONPATH=$W $V/bin/python  $W/measure/accel/bp_equivalence.py \
                                --corpus CORPUS --out OUT
PYTHONPATH=$W $V/bin/python  $W/measure/accel/bp_equivalence.py \
                                --corpus CORPUS --out OUT --mode control --stride 4
PYTHONPATH=$W $V/bin/python  $W/measure/accel/bp_throughput.py \
                                --corpus CORPUS --out OUT --engines gpu
PYTHONPATH=$W $E/bin/python  $W/measure/accel/bp_throughput.py \
                                --corpus CORPUS --out OUT --engines cpu1 cpu8
```

The scratch venv is built under the worktree and never touches
`env314t`. `mlx` is only ever installed there.

## Files

| file | what it does |
| --- | --- |
| `blas_probe.py` | build metadata, `otool -L` linkage, GEMM sweep vs the one-core NEON ceiling |
| `shapes.py` | instruments one colour and one K sim decode; records every call shape the benched kernels see |
| `op_bench.py` | per-op cost at those census shapes, plus the feature-width crossover sweep |
| `corpus.py` | tile attempts through the shipped codec, BI-AWGN ladder straddling every rate's cliff |
| `bp_mlx.py` | `ldpc._bp_loop` ported to a batched mlx implementation |
| `bp_equivalence.py` | gates 1 and 2 — equivalence (incl. the float64 control) and determinism |
| `bp_throughput.py` | gate 3 — tiles/s by engine, batch size and cohort; break-even fit |
| `bp_summary.py` | joins the two throughput runs and reports the break-even |

## Measurement conditions

This machine carries other agents' work. Every driver records
`loadavg` before and after into its JSON, and every reported figure is
the minimum over repeats, which is the least contaminated statistic
available. The numbers below were taken with the one-minute load
average between 11 and 32.

Two earlier passes are not reported. The first used a fresh random draw
per batch size, which measured the luck of the draw rather than the
batching — fixed in the driver. The second used the corrected driver but
began at load 120–148 and would have timed its small batches under
contention and its large ones without; it was stopped and re-run whole
once the host quieted.

## What the census found

One colour sim decode (`c3-cmy8-r0550x0550x0547@10x10`) and one K sim
decode (`c3-k-r0550@7x7`), single worker, every benched kernel wrapped:

| kernel | colour decode | K decode |
| --- | --- | --- |
| belief propagation (min-sum + sum-product) | 244 calls, 11.0 s of 21.5 s wall | 120 calls, 4.4 s of 15.5 s |
| `qda_log_scores` | 22 calls, 0.16 s, rows 150–32,610 at **3 features, 8 states** | — |
| `fit_qda` | 4 calls, 0.002 s, 483 and 745 rows | — |
| PAVA `_pava_nodes` | — | 29 calls, 0.003 s, n ≈ 414–423 |
| cold-placement FFT | **0 calls** | **0 calls** |

Belief propagation is half the colour decode's wall on its own. The
colour head's linear algebra is three-wide. The cold correlation never
fired: both sims present a whole page, so placement never falls back to
correlation — its shapes in `op_bench` are derived from page geometry
and labelled as such.

## (a) The BLAS is Accelerate, and the receiver cannot use it

Build metadata, link-time truth and runtime behaviour all agree. numpy
2.5.2 and scipy 1.18.1 both declare Accelerate; `otool -L` shows every
linear-algebra extension module in both packages resolving against
`/System/Library/Frameworks/Accelerate.framework`, nothing else. Single
-threaded (`VECLIB_MAXIMUM_THREADS=1`) GEMM runs at **290 GFLOP/s FP64**
and **1110 GFLOP/s FP32** at n=512 — 5.6x and 10.8x the arithmetic
ceiling of one Firestorm core's NEON pipes. The matrix coprocessor is
engaged.

It buys the receiver nothing, because nothing the receiver does is
shaped like a matrix multiply:

| op (census shape) | min | achieved |
| --- | --- | --- |
| `qda_log_scores` 32,610 rows, 3 features, 8 states | 9.14 ms | **0.68 GFLOP/s** |
| — its `np.linalg.solve` (3,3) x (3, 32610) | 0.84 ms | 0.70 GFLOP/s |
| — its gram `X.T@X` (32610,3) | 0.22 ms | 2.68 GFLOP/s |
| `fit_qda` 745 rows | 0.35 ms | — |
| PAVA `_pava_nodes` n=417 | 0.086 ms | — |
| ctx `_fit_matrix_curves` 500 rows | 294 ms | — (root finding, no BLAS) |
| `cmy7_soft_demap` 994 packs | 36.4 ms | — |
| — its (994,2048) @ (2048,11) GEMM | 1.29 ms | **34.7 GFLOP/s** |
| cold FFT, sheet-H-class page | 187 ms | — (pocketfft, no BLAS) |

The colour head runs at 0.2% of what this machine's BLAS can deliver.
The feature-width sweep says why: hold the rows at 32,610 and grow the
features, and the achieved rate climbs 0.69 → 3.13 → 6.36 → 14.2 → 34.0
→ 49.3 → 50.2 GFLOP/s at F = 3, 8, 16, 32, 64, 128, 256. Three features
is not near the regime where a matrix engine has anything to bite on.

## (b) Batched belief propagation on Metal

**Equivalence.** 1,728 attempts, six rate ids, both iteration budgets.
Wherever both decoders certify, the user bits are identical — 997/997 at
60 iterations, 1007/1007 at 150 — and there are **zero wrong
certificates on either side**. The GPU certifies 2.7% fewer (997 vs
1025; 1007 vs 1034), all of them at the cliff sigmas, none at either
extreme. The float64 control settles the attribution: the same padded
layout run at float64 on mlx's CPU stream reproduces numpy **exactly**,
251/251 and 255/255, zero divergence in either direction. The gap is
float32, not the port.

**Determinism.** Bit-identical on every question asked: a repeat of the
same batch, the same tiles in batches of 61 instead of 128, and a
different host-sync cadence. Hard bits, accept flags and iteration
counts all identical, at both iteration budgets.

**Throughput** (max_iters 60, tiles/s, min of 5):

| rate / cohort | cpu1 | cpu8 | gpu best | break-even vs cpu1 | vs cpu8 |
| --- | --- | --- | --- | --- | --- |
| r0550 mix | 60.0 | 253.7 | 540 @B=1024 | B=16 | B=256 |
| r0550 close | 223.7 | 1136.8 | 686 @B=1024 | B=32 | never |
| r0550 fail | 16.4 | 95.9 | 331 @B=1024 | B=8 | B=64 |
| r0700 mix | 34.2 | 173.2 | 340 @B=1024 | B=16 | B=256 |
| r0700 close | 234.6 | 1134.7 | 556 @B=1024 | B=256 | never |
| r0700 fail | 16.1 | 93.5 | 299 @B=1024 | B=4 | B=128 |

Transfer is not the overhead that matters: 0.4–0.7 ms of a 1.5–3.4 s
batch at B=1024. The fixed cost is per-batch dispatch and the
once-per-iteration host sync — 98–495 ms per batch against a marginal
1.4–3.0 ms per tile.
