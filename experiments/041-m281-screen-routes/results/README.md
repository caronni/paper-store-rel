# e041 — the M281 colour campaign: provenance of the measurements

The measured record is `../../041-m281-screen-routes.md` (§041.4–041.5p) and the synthesis
`docs/M281-COLOUR-2026-10-05.md`; every number they rely on is written there. This folder keeps
only what is needed to find and reproduce the measurements:

- this table: sheet → job sha → page count → scan sha256;
- `JOB-SHA256.txt`: sha and size of every printer job and bands npz (all regenerate byte-identically
  from the generators in `..`, sha-gated, `--verify` included);
- `measurements.json` (~250 KB): a compact extract of the readouts the record quotes — per sheet and band
  the state errors, mutual information, per-plane errors and poses, the full **confusion matrices**
  (S14 band B3's is the source of the cmy labelling), layout scores, per-x error profiles; the band-screen
  lattice profiles in 5 mm bins; the S11/S12 mixture configs; the S10p2 probe ranking; ground-truth
  comparison medians; the printer back channels (S4's PWG refusal text).

The full outputs (window CSVs, maps, logs, manifests) are NOT kept: they regenerate from the scans with
`measure/e041_*` and the generators. The scans (1.7–6.9 GB each) stay outside git, in the evidence archive
(`e041/`); their sha256 is below.

Printer: HP Color LaserJet Pro M281fdw (`<host>`), fresh toner, raw socket 9100 through
`scripts/print_plane.sh`. Scanner: Canon flatbed, 2400 dpi RGB TIFF (S17 also at 4800).
Page counts are the printer's PJL PAGECOUNT before → after.

## Sheets

| sheet | what it tested | language | generator | job | pages | scan(s) | readout (regenerates from the scan) | one-line verdict |
|---|---|---|---|---|---|---|---|---|

| S1 | F as printed before (PJL bpp 1), the baseline | PostScript, F's DeviceCMYK | make_ps_variants.py | `S1-pjl-bpp1.ps` 31,208,448 B `95f09ab9d1b1b6ab…` | 3391→3392 | `e041-s1-2400.tiff` (1.72 GB) `65cce4550247c6b9…`; turned 180°: `e041-s1-2400-180deg.tiff` (1.72 GB) `bf2a1d91451d7d63…` | logs/gt-compare-S1.log, logs/cell-error-S1.log, logs/maps-S1*.log, maps/, gt-compare/S1.json | screened (164/211 lpi), the 108 mm band |
| S6 | the max-escape variant (every PS door at once) | PostScript | make_maxescape.py | `S6-maxescape.ps` 31,209,216 B `2a3f43d0fc5789a6…` | 3393 | twice: `e041-s6-2400.tiff` (1.72 GB) `268816eebb15f7a2…`, `e041-s6-2400-b.tiff` (1.72 GB) `99158ace39a80619…` | logs/gt-compare-S6.log, logs/cell-error-S6.log, logs/maps-S6.log, maps/S6-witness-*.png, S6-stripe/, gt-compare/S6.json | no change: screened |
| S7a / S7b | F with /MediaType Heavy / Cardstock | PostScript | make_media_variants.py | `S7a-media-heavy.ps` 31,208,323 B `17151c35f0799f91…` / `S7b-media-cardstock.ps` 31,208,327 B `d5f1f817abd0ca25…` | 3394 / 3395 | `e041-s7a-2400.tiff` (1.72 GB) `9025aabd1d49c6db…` / `e041-s7b-2400.tiff` (1.72 GB) `d40ca8f1528f77cb…` | logs/gt-compare-S7*.log, logs/screen-map-S7*.log, logs/fine-screen-S7b-G.log, maps/S7b-*, gt-compare/S7*.json | media profile: no effect |
| S3c | PCL 5c CID device CMY | PCL 5c | pcl_planar.py --mode cid-cmy | `S3c-pcl-cid-cmy.pcl` 11,753,503 B `c523382625a9fbae…` | 3396 | `e041-s3c-2400.tiff` (1.72 GB) `6a603cfda6d9ae3b…` | logs/gt-compare-S3C.log, logs/screen-map-S3C.log, gt-compare/S3C.json | screened like PostScript |
| S9 | PCL XL bilevel, SetHalftoneMethod eHighLPI | PCL XL | pclxl_bilevel.py | `S9-pclxl-bilevel.pclxl` 15,485,388 B `2f34bc008464db4c…` | 3397 (after S3c/S8) | `e041-s9-2400.tiff` (1.72 GB) `7f73adbf4741c40d…` | logs/gt-compare-S9.log, logs/screen-map-S9.log, logs/fine-screen-S9-*.log, logs/spectra-*.log, maps/S9-*, gt-compare/S9.json | a finer 188 lpi screen set; still a screen; the unscreened pieces mapped |
| S8 | F turned 180° on the page | PostScript | make_rotated_sheet.py | `S8-rot180.ps` 31,208,347 B `8d4e2b2b77f73cc6…` | (between S3c and S9) | `e041-s8-2400.tiff` (1.72 GB) `7d393eb85cdeb1ed…` | logs/gt-compare-S8.log, logs/screen-map-S8.log, gt-compare/S8.json | the 108 mm band is fixed to the page raster |
| S9b | S9 with a downloaded 1×1 dither matrix | PCL XL | pclxl_bilevel.py --dither1x1 | `S9b-pclxl-dither1x1.pclxl` 15,485,400 B `fe764ab598809d06…` | 3398 | `e041-s9b-2400.tiff` (1.72 GB) `22ff018fc965d1a9…` | logs/gt-compare-S9b.log, logs/screen-map-S9b.log, logs/fine-screen-S9b-G.log, logs/spectra-S9b.log, maps/S9b-*, gt-compare/S9b.json | matrix ignored; default set back |
| S1dash | F with every payload CMY triple reduced to two inks (the cmy7 question) | PostScript | make_notriple_sheet.py (committed earlier, 85b4e61d) | `S1dash-notriple.ps` 31,208,456 B `2d00b316cff952d3…` | — | `e041-s1dash-notriple-2400.tiff` (1.72 GB) `953e3e474c7a1e2e…` | logs/gt-compare-S1dash.log, logs/screen-map-S1dash.log, logs/fine-screen-S1dash-G.log, logs/spectra-S1dash.log, maps/S1dash-*, gt-compare/S1dash.json | screened exactly like S1: the screen, not the triple |
| S10p | PCL XL RGB probe, per-object | PCL XL | pclxl_probe.py | `S10p-pclxl-rgb-probe.pclxl` 2,092,746 B `0e2f5e5fb1f921ae…` | NOTHING PRINTED, then HP 49 service error | — | manifests/S10p-*.manifest.json | the job structure crashed the formatter → the novelty-budget rule |
| S10p2 | the same probe as 13 band images | PCL XL | pclxl_probe_banded.py + pclxl_probe_sheets.py | `S10p2-pclxl-rgb-probe.pclxl` 23,473,742 B `3bfe4add94c3a493…` | 3397 | `e041-s10p2-2400.tiff` (1.72 GB) `2c4110633e1e6dd7…` | probe/S10p2-*.csv/.json, backchannel/S10p2-backchannel.txt | solid single-toner RGB values found; every two-toner overlap screened |
| S11 | the alphabet-mixture patches (22 arms) | PCL XL | pclxl_mixture.py | `S11-pclxl-mixture.pclxl` 26,455,613 B `b89f6883b942be5c…` | 3398→3399 | `e041-s11-2400.tiff` (1.72 GB) `0e7bea7c9c38f251…` | mixture/S11-*, logs/mixture-readout-S11.log, backchannel/S11-backchannel.txt | cmy4 0.4 %, cmyk5 0.5 %, cmy8 4–8 % at patch scale; dot-mixed overlaps read |
| S4 | PWG raster cmyk_8 (F's page) | PWG | pwg_job.py | `S4-pwg-cmyk8.pjl` 15,103,009 B `d65970ab6927e6e4…` | NOTHING PRINTED | — | backchannel/S4-backchannel.txt | the renderer refuses the page header (InternalError 0xc8) — the last device-CMYK door closed |
| S12 | S11's page as PostScript (indexed DeviceRGB images, HP calls) | PostScript | ps_mixture.py | `S12-ps-mixture.ps` 9,185,360 B `3ec2a2ee040112df…` | 3399→3400 | `e041-s12-2400.tiff` (1.72 GB) `76d6f3c0a34407c7…` | mixture/S12-*, logs/mixture-readout-S12.log, backchannel/S12-backchannel.txt | PostScript ≥ PCL XL; the production footing |
| S14 | full-width noise bands at page scale | PostScript | ps_scale.py | `S14-ps-scale.ps` 32,386,996 B `6081414085e91257…` | 3400→3401 | `e041-s14-2400.tiff` (1.72 GB) `198a252154960966…` | scale/S14-*, band-screen/S14-*, logs/scale-readout-S14.log, logs/band-screen-S14.log, backchannel/S14-backchannel.txt | cmy4 c3 lossless / c2 2.8 %; cmy8 and cmyk5 collapse where screened; the per-region switch |
| S15 | the reset probe (gaps, tiles, offset start) | PostScript | ps_reset.py | `S15-ps-reset.ps` 33,030,058 B `43c195288ab43e98…` | 3401→3402 | `e041-s15-2400.tiff` (1.72 GB) `2f79036a1c7c8935…` | scale/S15-*, band-screen/S15-*, logs/*-S15.log, backchannel/S15-backchannel.txt | nothing resets; regions page-fixed; white before content credits ~1 mm/mm |
| S16 | the trigger probe (colour count vs pixel budget, overlay, amplitude, white block) | PostScript | ps_trigger.py | `S16-ps-trigger.ps` 32,515,467 B `1ccf884a64b13dc5…` | 3402→3403 | `e041-s16-2400.tiff` (1.72 GB) `61a2d2786804169f…` | scale/S16-*, band-screen/S16-*, logs/*-S16.log, backchannel/S16-backchannel.txt | composite-pixel budget 270–660 %·mm; dot-mixed cmy8 c3 unscreened 3.2 % = 172 b/mm² |
| S17 | the layout probe (cmy7, orientation, phase, c2 pairs, c2-K) | PostScript | ps_layouts.py | `S17-ps-layouts.ps` 31,583,218 B `02bea73e842b0d76…` | 3403→3404 | 4800: `e041-s17-4800.tiff` (6.88 GB) `6fd8222b8392806f…`; 2400 rescan: `e041-s17-2400.tiff` (1.72 GB) `f708339b14bcbe56…` | scale/S17-* (4800), scale-2400/S17-* (2400), band-screen/S17-*, band-screen-2400/, logs/*-S17*.log, backchannel/S17-backchannel.txt | cmy7 dot-mixed 0.54 %; orientation reads ~2 % (3.0 b/cell); phase no; c2 dot-mixed closed; 2400 = 4800 for states |

Not in this table: S2/S2b/S3/S3b/S5 (built, verified, never printed), S13 (= S4).

## Reproducing a readout

```bash
PYTHONPATH=src:. env/bin/python experiments/041-m281-screen-routes/ps_layouts.py --out /tmp/S17/S17-ps-layouts.ps --verify
PYTHONPATH=src:. env/bin/python -m measure.e041_scale_readout --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S17/captures/S17-canon-4800rgb.tiff --scan-dpi 4800 --manifest /tmp/S17/S17-ps-layouts.manifest.json --out /tmp/S17/scale
```

The first regenerates the job, manifest and bands npz byte-identically (check against `JOB-SHA256.txt`);
the second is the 4800 readout (~43 min, ~9.4 GB). `measure.e041_band_screen` takes the same scan and
manifest (~16 min at 4800). The mixture readouts need `--patch-ref` only for their S12 comparison lines.

2026-10-09: inputs renamed to the published archive paths. The scans are published as
`paper-store-evidence-holo-2026-10/041-m281-screen-routes/<sheet>/captures/<sheet>-canon-<dpi>rgb[-<take>].tiff`
(as `.tiff.jxl`, rebuilt by the release's `tools/unpack.sh`), each job with its manifest and
bands/patterns npz under `<sheet>/jobs/`; the `measure/e041_*` docstring examples name those paths
(`e041_probe_readout`'s example reads S10p2, the probe that printed — S10p crashed the formatter).
Sheet F's `page000_gt.npy`, which `measure/e041_gt_compare.py --gt` and the `pcl_planar.py` /
`pclxl_bilevel.py` emitters' `--gt` read, is NOT published (tier delete, the `*_gt.npy` rule):
regenerate it with `env/bin/python util/ps_gt.py <root>/paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/F/jobs/page000.ps --out DIR/page000_gt.npy --expect-sha256 a9420188d346c787db829a8d11ea164b17ebdf802e191cfe6e5883177fe899bf`
(the published `F/emission/manifest.json`'s `gt_sha256`); the two emitters also want that
`manifest.json` beside the GT, so copy it into `DIR`.
