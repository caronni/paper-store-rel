# e044 — the first cmy format sheets on the M281 (P1)

The record is `../044-m281-cmy-first-print.md`. This folder holds what
regenerates the two printed jobs byte-for-byte:

- `generate_set.py` — the two counting payloads (e039's rule, k = 0 for
  sheet A, 1 for sheet B) and the two `confetti.py generate` runs
  (`--format`, `--paper A4-4mm`, `--printer hp-m281`, `--source-fraction
  0.8`); `--verify` checks against `JOB-SHA256.txt`.
- `JOB-SHA256.txt` — payload and job digests.

Derived files are not committed. Their homes:

- `scratch2/e044/jobs/` — the printed jobs `E044-A-page000.ps` (sheet A,
  `c2-cmy-r0775x0700@53x37`, 15,061,432 B) and `E044-B-page000.ps`
  (sheet B, `c3-cmy-r0850@35x24`, 14,181,472 B) with their manifests and
  ground truth (`*_gt.npy`);
- `scratch2/e044/payloads/` — the two counting payloads;
- `scratch2/e044/previews/` — 40 dpi renders;
- `scratch2/e044/captures/` — the owner's scans (`E044-A-…-scan.tiff`,
  `E044-B-…-scan.tiff`);
- `scratch2/e044/readout/` — the readouts against the GT.

Route: `lpr -o raw` to the CUPS queue of <host> (the `lpr-raw` footing),
pages 3413–3414 on 2026-10-11. The generator is branch `cmy-generator` at
a7846d33; the registry's `hp-m281` row carries the colour values.
