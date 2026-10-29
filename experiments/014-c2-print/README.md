# e014 — scripts

The log is `experiments/014-c2-print.md`. Retired from scratch/ 2026-10-09 (inputs: the three
Canon 4800 grey captures `scans/xerox-e014-A-canon-4800gray{,-B-displaced,-C-flattened}.tiff`
under `--evidence-root`; outputs to `build/`): `campaign_e014.py` (the 014.2 ladder, global vs ctx
detector × scans × combining), `wired_e014.py` (ctx+PAVA inside acquire, the F6 loop),
`multiscan_e014.py` (multi-scan combining policies), `patches_e014.py` (the error-patch figure),
`handanalyze_e014.py` (by-hand sync-vs-channel attribution), `decode_e014.py` (the blind hardware
decode).

2026-10-09: inputs renamed to the published archive paths — the three captures are
`paper-store-evidence-paperholo-era/014-c2-print/A/captures/A-canon-4800grey-{a,b-displaced,c-flattened}.tiff`
under `--evidence-root` (the archive root; the archive ships each as `.tiff.jxl`, rebuilt to the
`.tiff` by the release's `tools/unpack.sh`); every script refuses by name when one is absent.
