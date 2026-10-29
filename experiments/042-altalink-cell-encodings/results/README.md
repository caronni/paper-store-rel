# e042 — AltaLink density probe X1 and the reference sheets: provenance

Record: `../../042-altalink-cell-encodings.md` (§042.4 X1, §042.5 the 1200×2400 sheet and sheets E, D).
This folder keeps `JOB-SHA256.txt` (the X1 job and bands npz, both regenerable with
`ps_altalink_probe.py --out … --verify`) and `measurements.json` (~45 KB): X1's per-band state errors,
mutual information, per-plane errors and poses, confusion matrices and layout scores, its band-screen
lattice profiles, and sheet E's truth-fitted per-tile error summary and pose/aperture self-check.

| sheet | printed | scan (outside git, `scratch/e041/`) | sha256 |
|---|---|---|---|
| X1 (job `bf4c42d3…`) | AltaLink C8245, `lpr -o raw`, A4, 2026-10-06 | `e041-x01-2400.tiff` (Canon 2400 RGB) | `6e138436846f03474ecf02a5da1678133880c63022c9c5e059c33e4972b798e2` |
| 1200×2400 B/W discovery (e039 bundle) | same day | `e041-altalink-1200x2400bw-2400.tiff` (2400 RGB) | `a78d2f3f6491b388f7413d48f3fb14102f254c32f65f1bf69f9e2128ffe2b19a` |
| e039 sheet E `c1-k-r0700@106x74` | same day | `e041-altalink-e-2400.tiff` (2400 grey) + `-e-4800-{a,b,c,d}.tiff` | `d159f47a9e7ab6bf1be6165870b52acf570a11eefb13dc84ced2a3a9a0850221` (2400) |
| e039 sheet D `c2-k-r0850@53x37` | same day | `e041-altalink-d-2400.tiff` (2400 grey) | see §042.5 |

Reproduce: `PYTHONPATH=src:. env/bin/python -m measure.e041_scale_readout --scan scratch/e041/e041-x01-2400.tiff
--scan-dpi 2400 --manifest <regenerated X1 manifest> --out /tmp/x1`; sheet E's truth fit:
`PYTHONPATH=src:. env/bin/python measure/e042-c1-truth/c1_tile_error.py scratch/e041/e041-altalink-e-2400.tiff
scratch/versalink-20260916/E-c1-k-r0700-at-106x74-q080-A4-4mm/page000_gt.npy --format c1-k-r0700@106x74 --out-dir /tmp/E --probe 200`.
