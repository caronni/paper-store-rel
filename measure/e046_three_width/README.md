# measure/e046_three_width — the e046 run analysis (2026-10-13)

The instruments behind experiments/046-altalink-cmy8-three-width.md §046.2–§046.6.
They read the copied run records under `scratch/e046/runs/` (M1, M2 run dirs;
A1–A4 mints, ledger.md, close.json, ladder logs, export manifests) and the
emission in `build/e046/A/`. They run no decode and no ladder pass. Outputs go
to `scratch/e046/analysis/<name>/` and are never committed. Run every command
from the repo root.

| module | measures | command | output | wall / peak |
|---|---|---|---|---|
| `receiver_run.py` | M1/M2 by row and plane over cumulative cpu, seats and queues, the close replayed through `CloseProgress` (K, count-ready, first verified prefix, the q 0.9 count ESTIMATE), the page field per solve | `PYTHONPATH=src:. env/bin/python -m measure.e046_three_width.receiver_run --run M1=scratch/e046/runs/M1/rundir.40735 --run M2=scratch/e046/runs/M2/rundir.42487 --format c2-cmy8-r0775x0850x0700@53x37 --q09-payload-bytes 2006275 --out scratch/e046/analysis/receiver/receiver_run.json` | `receiver/receiver_run.json` | 12 s / 1.4 GB |
| `analyzer_passes.py` | A1–A4 per pass and per generation, attribution, the re-target replay (`analyzer.fixedpoint._retarget`), cascade and chains, closes, exposure, the final residue | `PYTHONPATH=src:. env/bin/python measure/e046_three_width/analyzer_passes.py --runs scratch/e046/runs --out scratch/e046/analysis/analyzer` | `analyzer/analyzer_passes.json` | 3 s / 1.2 GB |
| `residue_field.py` | the certified set per stage on the tile grid, column and row bands, the final five, the page fields of M1/M2 (periods, pairwise offsets) and their correlation with the residue; the figure | `PYTHONPATH=src:. env/bin/python -m measure.e046_three_width.residue_field --runs scratch/e046/runs --out scratch/e046/analysis/spatial` | `spatial/residue_field.json`, `spatial/residue_field.png` | 5 s / 1.9 GB |
| `truth_check.py` | every certificate of the chain against the emitted user bits, rebuilt through the generator's calls and proven by a byte-identical re-render of `page000_gt.npy`; the analyzer offline GT path's widths | `PYTHONPATH=src:. env/bin/python -m measure.e046_three_width.truth_check` | `truth/truth_check.json` | 6.7 s / 2.1 GB |
