# Rung-ladder study — provenance of the data

The measured record is `docs/RUNG-LADDER-STUDY-2026-09-30.md` (Appendix A = `TABLES.md`, Appendix B =
`TABLES-c1.md`, both verbatim; `docs/FEC-DESIGN.md` "2026-09-30 MEASURED" points there); every number it
relies on is written there. This folder keeps what its tables and sections rest on: the sweep results, the
built codes, the verification results and the search tables. The code that made them is beside it in `..`.

Provenance: machine 4's `scratch/rung-ladder-20260930/` of 2026-09-30/10-01 (harness sweep and c1 extension
2026-09-30; the overnight search 2026-09-30 23:21:54 → 2026-10-01 06:04:00), salvaged to machine 1 2026-10-08/09
before machine 4 wipe (`scratch/machine-4-salvage/scratch/rung-ladder-20260930/`), copied here 2026-10-11 byte for byte
under the same relative paths — a path the study names as run (`TABLES.md`, `verify/punct_results.json`,
`search/overnight-ALL/TABLES-search.md`) is that path in this folder. By the owner's ruling the study's data
stays with the study in git, NOT in the evidence archive; its logs were trashed (evidence line,
docs/EVIDENCE-ARCHIVE-2026-10-08.md §8a). Rulings R1–R10 are still owed. `.gitignore` here re-includes
everything that `../.gitignore` ignores.

## What is kept (54 files, 1,893,320 bytes)

| file | bytes | what it is | cited by |
|---|---|---|---|
| `RUNG-LADDER-MAP.md` | 23,507 | the decision map, rev. 2 (after the three-lens refutation: C7 withdrawn, nine claims qualified) | study, sources list |
| `TABLES.md` | 28,808 | the frozen-ladder harness tables (`harness/tables.py`) | study Appendix A |
| `TABLES-c1.md` | 31,238 | the sub-r0300 / c1 extension tables (`c1/tables_c1.py`) | study Appendix B |
| `results.json` | 162,877 | the harness sweep: 16 codes, 717 points, 200 trials/point (`harness/sweep.py --workers 12`, run 2) | Appendix A; Appendix B's continuity rows |
| `build_log.json` | 2,723 | build record of the ten candidate codes (k, kb/mb, heavy rows × degree, restart, edges, seed label) | Appendix A structural rows |
| `data/*.json` (10) | 226,305 | the built candidate codes r0250–r0469 and the h14/f50 variants, holo-style JSON (`harness/build.py`; NOT format rows) | Appendix A; `verify/digest_results.json` |
| `structure.json` | 11,666 | per-code structure: degree histograms, info-free checks, min w1 / w2 with argmin | study §3; map |
| `undetected_diag.txt` | 1,042 | the syndrome-valid wrong decodes traced to their codewords (line 1 = r0550's weight-6 word) | study §3; Appendix A |
| `c1/data/*.json` (10) | 258,844 | the built c1 codes r0203–r0281 and the f50/f70 variants (`c1/build_c1.py`) | Appendix B |
| `c1/build_log.json` | 2,733 | their build record | Appendix B |
| `c1/results-c1.json` | 119,006 | the c1 sweep, 351 points, with structure, frontier, capacity check and channel tables | Appendix B |
| `c1/structure-c1.json` | 7,170 | c1 structure | Appendix B |
| `c1/iters-c1.json` | 35,636 | the 200-iteration supplement (same seeds) | Appendix B; map |
| `c1/floor_diag.json` | 3,382 | the near-1 % failing trials re-decoded at 60/200/500 iterations | Appendix B |
| `verify/digest_results.json` | 8,359 | edge digests: holo reload = paperholo rebuild = harness cache, and structure cross-checks | study header; Appendix A |
| `verify/spot_results.json` | 1,181 | the five spot re-measurements | study header; Appendix A |
| `verify/capacity_results.json` | 3,598 | capacity and interpolation check of the tables | study sources list |
| `verify/punct_results.json` | 3,691 | the puncture runs (last / even positions) at 60/200/400 iterations | study §6; map |
| `search/RUN-PLAN.md` | 16,263 | the overnight plan, calibration and coverage | study §7.1, §7.3 |
| `search/fast/README.md` | 11,910 | the fast decoder record (bit-exactness, speed, threads vs processes) | study §7.1 |
| `search/fast/bitexact_result.json` | 1,823 | the 10,800 decode comparisons, 0 mismatches | `search/fast/README.md` |
| `search/fast/bench_single.json` | 4,026 | the single-thread throughput measurement | `search/fast/README.md` |
| `search/fast/verify/verify_bitexact.json`, `verify_volume.json` | 5,188 | the independent verification (533 comparisons per code; volume run) | study §7.1 |
| `search/feasibility-{frozen,overnight,secondary}-seed0.json` | 57,440 | seed-0 build scans; the overnight `recipe_search.py` skips every config whose seed-0 build failed (the grid holes) | `search/RUN-PLAN.md`; study §7.3 |
| `search/trial-{A,A2,B1,B2}/TABLES-search.md` | 159,167 | the selection trials | study §7.2 |
| `search/overnight-ALL/TABLES-search.md` | 376,941 | the overnight result: the confirmed ranking (its first 185 lines) + the union of every stage, DE and B2 sections | study §7.3, §7.4 |
| `search/overnight-{A,AF,B1,B2}/TABLES-search.md` | 328,796 | the four stage tables (per-stage settings, CPU, screen-1 rankings) | `overnight-ALL`'s "earlier (src)" column |

## Not kept, and why (partly superseded 2026-10-17, below)

- Logs: `run.log`, `run1_aborted.log`, `sweep_progress*.log`, `c1/run.log`, `c1/iters_run.log`,
  `c1/sweep_progress*.log`, `search/logs/`, `search/overnight.log`, `search/feasibility.log`,
  `search/trial-*.log`, `search/fast/verify/verify_bitexact.log` (ruling: logs trashed; Appendix A's run
  record tells run 1's abort).
- Regenerable in seconds from kept files: `tables.json` (`harness/tables.py`), `c1/tables-c1.json`
  (`c1/tables_c1.py`).
- Duplicates: `search/overnight-CONF/TABLES-confirm.md` (= the first 185 lines of `overnight-ALL`),
  `c1/results-c1-raw.json` (its points are `c1/results-c1.json`'s), `c1/headline.md` and `c1/_dump.txt`
  (text inside `TABLES-c1.md`), `search/*/de-candidates.json` (the profile is spelled in each B1 code
  name; `overnight-ALL` tabulates the candidates).
- Smoke and pre-run checks: `results_smoke.json`, `c1/results-c1-smoke.json`, `search/smoke-*/`,
  `search/smoke-run/`, `search/chk/`.
- Not cited anywhere: `search/trial-AB1/`; the one-off probes' outputs `m_*.json` (three empty) and
  `ip_*.json` (`lowrate_measure.py`, `iters_puncture.py`) and `refute_c1/pairs.json` (its two pair
  weights are `structure.json`'s).
- Scripts: the carried ones are in `..`; the one-off probes were not carried (`../README.md`).

## Reproducing

The scripts read and write beside themselves in `..` (`../data/`, `../results.json`, …), not here. To re-run
the tables from this record, copy the inputs up first, e.g. `results.json structure.json build_log.json
undetected_diag.txt` into `..` and run `PYTHONPATH=src:. env/bin/python measure/rung-ladder/harness/tables.py`
from the repo root; `harness/build.py` rebuilds `data/` (0.4 s) and `verify/digest.py` checks a rebuild by
edge digest.

## 2026-10-17 — the non-reproducible remainder, brought in before scratch/ goes

Owner's ruling 2026-10-17: scratch/ will go away; what is relevant, compact and not mechanically reproducible
comes into git. Copied byte for byte from `scratch/rung-ladder-20260930/` under the same relative paths, the
row unions xz'd: 69 files, 2,703,440 bytes. This supersedes the 2026-10-11 "logs trashed" line for the run
logs listed here. Code carried to `..` the same day: `search/chk/{probe,und_identity}.py`,
`search/{feasibility,feasibility2,sizing}.py`, `search/fast/{bench_single,bench_workers}.py` +
`run_bench_workers.sh`, and `../probes/` (lowrate_measure, lowrate_profile, iters_puncture, system_lens,
refute_c1/pairs).

| what | bytes | content | why kept |
|---|---|---|---|
| `search/overnight-CONF/results.jsonl` | 271,130 | the 137 confirm rows (136 codes + meta): per code cfg, seed, tier, source stage, t0 20000, 5000 trials, the points, es1/es10/p1/p10, gap_db/gap_bit, `und` and `und_w` (the traced wrong words), cpu | the winners' identity and every floor in the confirm table; 90 min of 14 workers on the wiped machine 4 |
| `search/overnight-ALL/results.jsonl.xz` | 1,634,252 | the union of every stage's rows — A 23,311, AF 1,559, B1 1,861, B2 2,275, CONF 137 → 28,763 rows, 15,474 distinct codes (checked by rid: no stage row missing) — each with build, struct (degree histogram, edge_sha, min w1/w2) and its screens; 33,962,239 bytes raw, `xz -d` to read | the only record of every built code's identity; 6.7 h of 14 workers |
| `search/trial-{A,A2,B1,B2}/results.jsonl.xz` | 154,748 | the selection-trial rows behind §7.2 (production decoder, 100/500 trials) with their `und_w` traces (finding 3's weight-10 word) | cited; the trial tables are derived from them |
| `search/overnight.log`, `search/overnight-state/*.done`, `search/logs/*.log` | 151,235 | the run record: stage commands, s0/s1/s2 counts, decode counts, wall, `errors 0`, the selfcheck lines | the study's '22,688 codes' check (s0 sums to 15,478); the 'selfcheck passed, no fallback' evidence |
| `search/trial-*.log`, `search/feasibility.log` | 24,189 | the trial and feasibility runs' logs | run record |
| `search/chk/id-smoke-{fast,prod}/` | 178,540 | the fast-vs-production identity smoke: the same 53 codes and seeds through both decoders (results + tables + logs) | RUN-PLAN 'Verified before launch' |
| `search/chk/calib-fast/` | 247,639 | the fast decoder's re-run of the trial grid against the production trial-A2 (473 points / 55,300 decodes, RUN-PLAN:61) | the run-level bit-exactness evidence the study called 'prose only' |
| `search/chk/{feas-*,probe,und_identity,test_*}.log` | 19,511 | preflight logs: the feasibility Counters (build timeouts), the build probe, the `und_w` identity check, the three fast-decoder test logs | what the preflight stage ran |
| `search/fast/bench_workers.jsonl`, `*.load`, `verify/verify_bitexact.log` | 6,332 | the worker-mode benchmark data (fast/README 'Worker modes') and the bit-exact verification log | measured on the wiped machine 4 |
| `probes/` | 15,134 | the one-off probes' outputs: `lowrate_measure` m_*.json (11), the h20/h30 build failures m_*.err (3; §4 'h20 fails within 64 restarts'), `iters_puncture` ip_*.json (4), `refute_c1/pairs.json` | cited by §4 and the structure rows |
| `run.log`, `run1_aborted.log`, `c1/run.log`, `c1/iters_run.log` | 606 | the harness and c1 sweeps' own logs (run 1's abort) | run record |

Still not kept, and why: the stage-level `overnight-{A,AF,B1,B2}/results.jsonl` (subsets of `overnight-ALL`,
verified by rid: 0 missing), `overnight-CONF/TABLES-confirm.md` (= the first 185 lines of `overnight-ALL`),
`trial-AB1/` (cited nowhere), `stale-overnight-B2-2031/`, the smoke and dry runs (`smoke-*`, `smoke-run/`,
`chk/{dry-A,dry-AF,term-test,smoke-*}`), `chk/feas-*.json` (byte-identical to `search/feasibility-*-seed0.json`),
`search/de_phi_table.npz` (a cache `de_engine.py` rebuilds), the progress logs (`sweep_progress*.log`,
`c1/sweep_progress*.log`), `tables.json` / `c1/tables-c1.json` (regenerable), the c1 duplicates (`_dump.txt`,
`headline.md`, `results-c1-raw.json`, `results-c1-smoke.json`) and `results_smoke.json`.

Export note (2026-10-30): the public export rewrote the private paths inside `search/overnight-ALL/results.jsonl.xz` 1,634,376 -> 1,634,252 bytes with its substitution rules (D12) and recompressed them (xz -9, CRC64); the table shows the new sizes.
