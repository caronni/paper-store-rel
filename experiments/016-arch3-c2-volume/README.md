# e016 — scripts

The log is `experiments/016-arch3-c2-volume.md`. Retired from scratch/ 2026-10-09:
`campaign_e016.py` (the M281 twin of the 014.2 ladder, scans A/B/C under `--evidence-root`, →
`build/campaign_e016.json`), `report_e016_state.py` and `alone_certify_e016.py` (read
`build/e016_state.pkl` after `decode_e016.py`).

2026-10-09: inputs renamed to the published archive paths — `campaign_e016.py` reads
`paper-store-evidence-paperholo-era/016-arch3-c2-volume/c2/captures/c2-canon-4800grey-{a,b-displaced,c-displaced}.tiff`
under `--evidence-root` (the archive root; each published as `.tiff.jxl`, rebuilt by the release's
`tools/unpack.sh`) and refuses by name when one is absent.
