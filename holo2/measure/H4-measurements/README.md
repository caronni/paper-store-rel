# H4-measurements — the H4 wave's benchmark drivers and their outputs

The instruments and raw outputs behind holo2's H4 numbers (W1 exit, W2
exit, the parallelism cards, the GIL diagnosis, the F-16/F-17 cards),
2026-08-09 → 2026-08-18. Preserved from `scratch/holo2-demo/` on
2026-08-23 when that directory (312 GB, of which 300 GB were
`.prepared` raster caches of two captures) was trashed; this folder is
the ~0.7 MB of it that a tracked document cites.

These are **records, not live tooling**. Nothing here is collected by
pytest, nothing is on `test_conventions`' measure-script guard (that
glob is deliberately non-recursive over `holo2/measure/*.py`), and the
scripts are kept byte-for-byte as they ran — including their absolute
paths into worktrees that no longer exist (`paper-h4`, `paper-w2-measure`,
`paper-cards-measure`) and into `scratch/holo2-demo/`. Re-running one
means re-pointing `D=`/`TREE=`/`SCAN=` by hand; the docstrings and the
`.sh` headers say what each run was for and what anchor it was measured
against.

## What cites this folder

- `holo2/docs/MEASUREMENTS.md` — `run_decode_dbg.py` (the w8-anomaly
  discriminators), `run_decode_gil.py` (the GIL-contention diagnosis),
  and the archived real state `state-c2bw-waveb` (the F-16 layout
  re-expression; the state itself was NOT kept — it is regenerable from
  the scan, but its exact commit ordering is not, so that table is now
  historical rather than re-checkable).
- `holo2/measure/bch_equivalence.py` — `run_decode_sweep.py` (the
  driver-side switch-flip trick it inherited).
- `.claude/memories` project-solver-redesign — the four `*-REPORT.md`.

## `drivers/` — 21 Python drivers + 11 zsh run scripts

The Python files are `__main__` drivers run by path against a pinned
worktree: each wraps `cli.main`'s real decode path and adds one kind of
instrumentation (A/B switch flip, cProfile, GIL-release timing, commit
cost counters, fire/round attribution). The `.sh` files are the
strictly-sequential run chains that produced the outputs — one decode
at a time, `/usr/bin/time -l`, a fixed port range per chain, and the
failure rule "a run that is not VERIFIED + BYTE-IDENTICAL stops the
chain".

| driver | measures |
|---|---|
| `run_decode.py` | H3bis demo driver: `cli.main` real path + OR-6 cadence (512) + finalize — the base every other driver wraps |
| `run_decode_timed.py` | + driver-side consult timer (P3-1 measure-first gate) |
| `run_decode_ab.py` / `run_decode_ab2.py` | W-S barrier A/B with fire/round instrumentation; `ab2` adds index-build attribution (the F-17 discriminator) |
| `run_decode_bm.py` / `bm2_bench.py` | lockstep-BM card A/B by swapping `bch_batch` whole; the binary two-step BM card benched (decompose + whole + 4-thread f) |
| `run_decode_sweep.py` | flips `PlacementConfig.batched_word_sweep` ON driver-side |
| `run_decode_refine.py` / `refine_kernels.py` | flips `PlacementConfig.batched_refine` ON; old vs new refine-grid kernel at real shapes + GIL fraction |
| `run_decode_fitphase.py` / `fitphase_bench.py` | `_FIT_PHASE` batching card A/B; the card benched |
| `chien_decompose.py` / `chien_kernels.py` | where Stage-A word-decode time goes; old vs new Stage-A decoder at real shapes + GIL fraction |
| `run_decode_gil.py` / `gil_kernels.py` | GIL-contention diagnosis of the pull-model pool; kernel-level GIL-release measurement of the hot leaves |
| `run_decode_profile.py` / `profile_absorb.py` / `profile_attribute.py` | JOB B: cProfile of one serial gen-clean decode and the main-thread attribution of it |
| `run_decode_commitcost.py` / `price_card.py` | JOB B second pass: profiler-free commit-path accounting; pricing the ENCODE-AT-PROPOSE card from it |
| `run_decode_dbg.py` | w8-anomaly debugging: stale attribution + contention discriminators |

Run chains: `bm_runs.sh`, `bm2_runs.sh`, `chien_runs.sh`,
`refine_runs.sh`, `fitphase_runs.sh`, `gil_runs.sh`, `cards_runs.sh`
(JOB A real-sheet re-measure), `cards_jobb.sh` (JOB B commit-path
profile), `h4card_runs.sh`, `h4card_runs2.sh`, `h4card_real.sh` (F-17).

## `reports/` — the outputs, 85 files

- `holo2-measure-w1exit-REPORT.md`, `holo2-measure-w2exit-REPORT.md`,
  `holo2-cards-measure-REPORT.md`, `holo2-gil-diagnosis-REPORT.md` —
  the four written reports (previously at `scratch/` top level).
- `*.log` / `*.out` — per-run stdout with `/usr/bin/time -l` (wall,
  RSS), one per state the chains produced; `*_runs.out` are whole-chain
  transcripts.
- `*.json` — counter outputs: eleven `*.gil.json` (GIL fractions per
  kernel, the summaries every report number comes from) and
  `cards-commitcost.commitcost.json`.

Not carried into git (trashed with the directory): the five cProfile
`.pstats` dumps (rankings only; their walls were DISQUALIFIED in the
reports — the rankings are quoted there) and the eleven `*.raw.pkl`
per-fire sample pickles the `.gil.json` files summarize. Text only,
so the folder diffs and greps.

## The two captures

Every run decoded one of two captures; neither is in git.

- **gen-clean fixture** `e028-genclean-c2-r0700.tiff` — a SYNTHETIC
  ideal raster (c2-r0700@3392x2368 rendered at 1200 DPI, two grey
  levels 20/235, no margins, no skew; written by tifffile). Trashed with
  the directory; regenerable from the format id. The "e028" in the name
  is the coding, not the e028 print.
- **real sheet** `scratch/in/xerox-canon-c2-bw.tiff` — the e032
  AltaLink `c2-r0700@3392x2368` sheet, Canon 4800 grey; payload
  465,580 B, sha `e5021f8d…`. Still on disk in `scratch/in/`.

Not kept: the 58 `.prepared` caches (rebuildable from the raster at the
next run, DESIGN §"the prepared plane is the durable pixel"), the 102
state directories (bench/A-B/debug runs whose numbers are in the logs;
19 of them pre-schema-7 and unreadable by current holo2), and 78
byte-identical copies of the recovered payload.
