# Rung-ladder study harness (2026-09-30)

The code of docs/RUNG-LADDER-STUDY-2026-09-30.md, retired from scratch/ 2026-10-09 (machine 4's
`scratch/rung-ladder-20260930/`; its data — results.json, TABLES*.md, built codes, the overnight
runs' tables — is in `results/` beside the code, NOT in the evidence archive. Corrected 2026-10-11: this
line said "in the evidence archive under `machine-4-salvage/scratch/rung-ladder-20260930/`"; the owner
ruled the data stays with the study in git (evidence line, docs/EVIDENCE-ARCHIVE-2026-10-08.md §8a);
`results/README.md` says what was kept and why). Rulings R1–R10 are still owed, so this is a live instrument.

- `harness/` — build, codes, channels, structure, sweep, tables: the frozen-ladder sweep (TABLES.md).
- `c1/` — the sub-r0300 extension (TABLES-c1.md).
- `search/` — the overnight construction search (`run_overnight.sh`; DE profiles, variants, confirm);
  `search/fast/` the fast decoder, its tests and bit-exact verification.
- `verify/` — independent checks of the harness's arithmetic and spot re-measurements.
- `probes/` — the one-off probes of 2026-09-30 (lowrate_measure, lowrate_profile, iters_puncture,
  system_lens, refute_c1/pairs); outputs in `results/probes/`.
- `cost_fit.py` — the wall-cost fit.
- `results/` — the study's data, tracked (2026-10-11; its README is the provenance).

Run from the repo root with `PYTHONPATH=src:.`; outputs land beside the scripts as in the original
run and are gitignored here. The one-off probes (search/chk, feasibility, benchmarks, sizing,
system_lens, lowrate_*, iters_puncture, refute_c1) were not carried on 2026-10-09; carried 2026-10-17
with their outputs (`results/README.md` §2026-10-17), because scratch/ is going away:
`search/chk/{probe,und_identity}.py`, `search/{feasibility,feasibility2,sizing}.py`,
`search/fast/{bench_single,bench_workers}.py` + `run_bench_workers.sh`, and `probes/`.
