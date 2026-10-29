# e046 — the cmy8 three-width counting sheet on the AltaLink C8245

The record is `../046-altalink-cmy8-three-width.md`. This folder holds what
regenerates the printed job byte-for-byte:

- `generate_set.py` — the counting payload (e039's rule, k = 2) and the one
  `confetti.py generate` run (`--format c2-cmy8-r0775x0850x0700@53x37`,
  `--paper A4-4mm`, `--printer xerox-altalink-c8245`, `--source-fraction
  0.8`); `--verify` checks against `JOB-SHA256.txt`.
- `JOB-SHA256.txt` — payload and job digests.

Derived files are not committed. Their homes: `scratch/e046/jobs/`
(`E046-A-page000.ps`, 32,380,671 B, its manifest and ground truth
`E046-A-page000_gt.npy`), `scratch/e046/payloads/`, and the owner's scans
under `scratch/e046/captures/` once they exist.
