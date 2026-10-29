# e031 — scripts

The log is `experiments/031-xerox-altalink-discovery.md`. `w8_verify_corners.py`,
`w9_capture_forensics.py`, `w10_structured_capture_checks.py` are the W8–W10 checks. Retired from
scratch/e031/ 2026-10-09 (inputs under `--evidence-root`: `in/xerox-canon-cal-{bw,color}.tiff`,
`e028/…`, `e031/reports*/`, `e031/corner_fit.npy`; outputs to `build/`): `diag_mic.py`,
`diag_mic2.py` (MIC yellow dots), `diag_morph.py` + `fig_morph.py`, `fig_morph_raw.py`
(single-dot/hole morphology), `diag_strokes.py`, `diag_strokes2.py` (3-dot stroke continuity).

2026-10-09: inputs renamed to the published archive paths — under `--evidence-root` (the archive
root), the scripts read `paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/`
`discovery/captures/discovery-{bw-canon-4800grey,color-canon-4800rgb}.tiff`,
`discovery/reports/harness/hcal-report-discovery-bw-copy0000-f1e31d2b3944bf66.json`,
`discovery/reports/production/hcal-report-discovery-color-copy0000-82abef068de7c651.json` and
`records/corner_fit.npy`, and the e028 M281 pair
`paper-store-evidence-holo-2026-10/028-discovery-m281/discovery/captures/discovery-bw-canon-4800grey.tiff`
+ `discovery/reports/hcal-report-discovery-bw-copy0000-76d0b6b1161c234e.json`; captures are
published as `.tiff.jxl`, rebuilt by the release's `tools/unpack.sh`. Each script refuses by name
when an input is absent; `fig_morph.py` reads only `build/morph.pkl` (its flag is unused).
