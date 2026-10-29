# e017 probes

The log is `experiments/017-color-channel.md`. The `probe17_canon_*.py` set (017.4, the Canon 4800
RGB re-anchoring of P1/P2/P5 on the e004 finalists sheet) was retired from scratch/ 2026-10-09: run
`probe17_canon_prep.py --evidence-root DIR` first (decimation + registration into `../build/`),
then `_p1`, `_p2`, `_p5`, `_p5_verbatim`, `_artifacts` (→ `../build/probe17_out/canon-*.json`).
Weak-Y-epoch M281 results (ruling 2026-09-14).

2026-10-09: inputs renamed to the published archive paths — the `probe17_canon_*` set reads the e004
finalists sheet's Canon 4800 RGB capture at
`paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-canon-4800rgb.tiff`
under `--evidence-root` (the archive root; published as `.tiff.jxl`, rebuilt by the release's
`tools/unpack.sh`) and refuses by name when it is absent.
