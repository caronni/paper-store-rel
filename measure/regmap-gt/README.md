# regmap-gt — supervised per-plane registration (sheet I)

Measures each CMY plane's print registration against the ground-truth bitmap on the e033 sheet I
2400 capture (the AltaLink Y x-offset sinusoid, 0.83 dot, ~100 mm; `per-column.json` is PAGE-FIELD
B3's supervised reference). Retired from scratch/xerox-v1-20260818/regmap-gt/ 2026-10-09.
`_anchor.py --evidence-root DIR` fits the scan←GT affine (its values are frozen in
`measure_plane_offsets.py`); `measure_plane_offsets.py --evidence-root DIR` writes
`build/regmap-gt/{plane-offsets.json,per-column.json,plane-offsets.png}` (runs `report.py`).

2026-10-09: inputs renamed to the published archive paths — the capture is
`paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/I/captures/I-canon-2400rgb.tiff` under
`--evidence-root` (the archive root; published as `.tiff.jxl`, rebuilt by the release's
`tools/unpack.sh`). Sheet I's `page000_gt.npy` is NOT in the published archive (tier delete, the
`*_gt.npy` rule): both entry points read it from `build/regmap-gt/page000_gt.npy` and refuse by
name, with the command, until `util/ps_gt.py <root>/paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/I/jobs/page000.ps --out build/regmap-gt/page000_gt.npy --expect-sha256 26c76ca4e26b0c6558a86fee999add99d7eaaa7ec29469665c78208e441fa134`
(the published `I/emission/manifest.json`'s `gt_sha256`) has written it.
