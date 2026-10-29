# The cmy score lane on paper — the M1 gate (2026-10-12)

The question (src/holo/receiver/docs/CMY-RECEIVER-PLAN.md A8; docs/CMY-DESIGN.md §2.7, R11): on the clean
offset c3 sim the score lane's per-cell L-infinity divisor (`color_region_head.evidence_with_divisor`,
`CMY7_RELATIVE_SCORE_BOUND = 20`, cmy7's, reused by cmy) squeezes the minor scores (~3e3 against a dominant
~6.6e8) to ~1e-4, so `tile_codec.cmy_soft_demap` gets the hi/lo SIGNS wrong on whole states while the state
argmax stays right; lifting the bound gives 0 flips. Does that happen on PAPER evidence, before M1 (the first
decode of a real cmy page, e044 sheet B)?

**Answer, measured: no.** At truth-fitted poses the bound changes at most 28 label signs per regime, zone and
state, and at most 72 over the whole page in one regime: ≤ 0.004 % of a state's cells, with sign-wrong rates
equal to 0.004 pp. It changes no tile outcome, at any level of the capture's ladder, cold, refit or first fire.
Paper scores are tens (max |s| p99 45–122), not 1e8. The divisor divides 68–100 % of cells, but only by
1.1–6.1, so the true state's emitted margin stays ≥ 0.53 at the 1st percentile. Single sheet, single capture —
NO promotion.

**Provenance.** `measure/cmy_calibration/scorelane.py` (uncommitted when this was written), run on machine 1 on
the `cmy-generator` worktree at 0fe23a33 (the receiver tree clean; the A5 commit touches no file on the score
lane's path). Scan `scratch2/e044/captures/E044-B-c3-cmy-r0850-hp-scan.tiff` (sha256 `aeeca25c…`, 2400 dpi
RGB, 28064 × 20416); GT `build/p1/c3/page000_gt.npy` (`7020b7b2…`) with its manifest
(`1i200-cmy-r0850-p120-v1@35x24`, 2240 × 1536 cells, 840 tiles, origin (148, 176) dots). The artefacts are
NOT committed: `scratch2/e044/scorelane/` holds `poses.json`, `scorelane.json` (the JSON of record),
`tiles.csv` (every tile attempt), `compact.md`, `compact-all-levels.md`, `report.md` and the logs. A second
run (truth and pose arms only, `scorelane-run2-truth-pose.json`) matches the run of record in every shared
entry and every tiles.csv row; the timers differ.

```
cd <repo> && PYTHONPATH=src:. \
    env/bin/python -u -m measure.cmy_calibration.scorelane --stage poses --workers 8
... --stage measure --workers 6        # 1,779 s wall, peak RSS 14.7 GB (poses: 175 s, 2.9 GB)
... --stage report --levels 0 3        # the tables below; --full: every table per level
```

## Method

- **Poses.** measure/e044_cmy_truth/readout.py's own pose fitting is called as is: the seed, the orientation
  (as-is), and two passes of 36-cell windows on the 3 × 3 prior. It reproduces the readout's median offsets
  exactly: M−C (−0.919, +1.230) and Y−C (−0.407, +1.129) dots (dy, dx). Each plane's offset is bilinear between
  the window centres, and the cell centre is page dot origin + 3c + 1.5 − 0.5/sub, the readout's own sampling
  point.
- **The receiver's view.** The capture's ppc ladder is 2, 4, 6 and 12 (`intake.build_levels`). Planes are
  decimated by `lib/decimate` from the native channels, as intake does. Windows are the production 200-cell
  grid (`lib.geometry.window_starts`): 140 windows, each a `Placement` whose native affine is the least-squares
  fit of C's truth points over its cells, composed through `_h3_fixture_geometry.window_pose`. C's residual from
  that affine inside a window has a median rms of 0.434 dots (max 0.991).
- **Arms.** All three reach the colour job through `color_region`'s `offsets_of` seam.
  - **truth:** every plane reads at its own truth point per cell.
  - **rel:** the charter's arm and what a converged page field hands the job under F_C ≡ 0. C reads at the
    window pose; M and Y read at pose + (plane − C). C's in-window residual therefore stays in all three
    planes.
  - **pose:** no offsets, so all three planes read at C's window pose. This is the colour job before any field
    exists.
  - The head's three-way gate picks the arm as in production.
- **Regimes.**
  - **cold:** one region over all windows, no certificates; this is the furniture-only fit.
  - **refit:** GT certificates on one tile parity and the other parity read; both folds. The certificates are
    minted by `tiles.attempt_tile` from a noiseless score-space cut of each GT tile. All 1,680 certify, and
    their projection equals the GT on every tile.
  - **first_fire:** each window is its own region, cold, as the first colour fire of a decode is.
  - Each regime runs per arm; the pose arm runs cold and first_fire only.
- **The lane and the reads.** `color_region.region_job` runs unmodified, with the bound monkeypatched to 20
  or to inf inside the process. The tile cuts come from `tiles.color_candidates` + `assemble_cut` (the owner
  rule). Signs come from `tiles.stream_llrs` with no sibling. Attempts go through `tiles.attempt_tile`: scan,
  then retry150 after a failed scan. A certificate whose user bits differ from the GT's counts as WRONG.
- **Zones.** left = cells at x < 115 mm (e044 §044.2's excess zone, where M sits 1.3–2.8 dots low); right =
  the rest.

## (1) Cells whose hi / lo sign the bound changes (20 vs lifted)

ppc 4 and 6 behave alike (`compact-all-levels.md`). The truth arm's maximum, 28 cells, is at ppc 6, first
fire, left zone, M hi. The context head is re-fitted per bound: its bins come from the bounded evidence. These
counts therefore include that effect.

| ppc | regime | zone | cells | W | C | M | Y |
|---|---|---|---|---|---|---|---|
| 2 | cold | left | 1841595 | 1 / 1 | 0 / 0 | 0 / 0 | 0 / 1 |
| 2 | cold | right | 1498245 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 2 | refit | left | 1841595 | 2 / 1 | 0 / 0 | 0 / 0 | 0 / 2 |
| 2 | refit | right | 1498245 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 2 | first_fire | left | 2845778 | 6 / 3 | 0 / 0 | 10 / 3 | 4 / 5 |
| 2 | first_fire | right | 2590655 | 0 / 0 | 1 / 0 | 1 / 2 | 0 / 4 |
| 2 | cold_rel | left | 1841595 | 1 / 3 | 0 / 1 | 5 / 2 | 1 / 8 |
| 2 | cold_rel | right | 1498245 | 1 / 1 | 0 / 0 | 0 / 3 | 5 / 3 |
| 2 | refit_rel | left | 1841595 | 1 / 1 | 2 / 4 | 3 / 1 | 4 / 5 |
| 2 | refit_rel | right | 1498245 | 1 / 1 | 0 / 2 | 3 / 1 | 3 / 3 |
| 2 | first_fire_rel | left | 2845778 | 5 / 9 | 3 / 1 | 36 / 13 | 14 / 18 |
| 2 | first_fire_rel | right | 2590655 | 1 / 0 | 1 / 1 | 3 / 4 | 3 / 7 |
| 2 | cold_pose | left | 1841595 | 2198 / 1591 | 20 / 35 | 3969 / 1230 | 1282 / 2954 |
| 2 | cold_pose | right | 1498245 | 2272 / 1579 | 9 / 19 | 4674 / 1271 | 1483 / 3337 |
| 2 | first_fire_pose | left | 2845778 | 10886 / 7241 | 43 / 189 | 20147 / 7575 | 7257 / 16770 |
| 2 | first_fire_pose | right | 2590655 | 9076 / 6566 | 51 / 121 | 19331 / 7617 | 7960 / 15355 |
| 12 | cold | left | 1841595 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 1 |
| 12 | cold | right | 1498245 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 12 | refit | left | 1841595 | 0 / 0 | 0 / 0 | 2 / 0 | 0 / 1 |
| 12 | refit | right | 1498245 | 0 / 0 | 0 / 0 | 0 / 1 | 0 / 0 |
| 12 | first_fire | left | 2845778 | 3 / 1 | 1 / 0 | 12 / 5 | 2 / 4 |
| 12 | first_fire | right | 2590655 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 12 | cold_rel | left | 1841595 | 223 / 262 | 275 / 321 | 61 / 129 | 136 / 100 |
| 12 | cold_rel | right | 1498245 | 93 / 101 | 155 / 190 | 26 / 54 | 50 / 52 |
| 12 | refit_rel | left | 1841595 | 4 / 4 | 9 / 6 | 13 / 8 | 9 / 11 |
| 12 | refit_rel | right | 1498245 | 2 / 2 | 2 / 1 | 5 / 5 | 6 / 10 |
| 12 | first_fire_rel | left | 2845778 | 10 / 50 | 1 / 2 | 68 / 42 | 23 / 94 |
| 12 | first_fire_rel | right | 2590655 | 3 / 3 | 0 / 0 | 9 / 4 | 8 / 8 |
| 12 | cold_pose | left | 1841595 | 5696 / 5321 | 48 / 93 | 11005 / 4091 | 3797 / 9511 |
| 12 | cold_pose | right | 1498245 | 5252 / 4734 | 15 / 53 | 11751 / 4153 | 4291 / 10019 |
| 12 | first_fire_pose | left | 2845778 | 19710 / 14488 | 56 / 249 | 38426 / 13369 | 11329 / 32251 |
| 12 | first_fire_pose | right | 2590655 | 16970 / 14363 | 68 / 234 | 36002 / 15112 | 14281 / 30651 |

## (2) % of cells: hi sign wrong / lo sign wrong / state argmax wrong (the hard readout's twin), at 20

"lifted" appears where any of the three values differs by ≥ 0.005 pp. The last column is exact-zero LLRs
(an erased stream).

| ppc | regime | zone | W | C | M | Y | zero hi / lo |
|---|---|---|---|---|---|---|---|
| 2 | cold | left | 0.15 / 0.30 / 0.36 | 0.01 / 0.01 / 0.01 | 0.01 / 0.01 / 0.01 | 0.00 / 0.25 / 0.25 | 0.00 / 0.00 |
| 2 | cold | right | 0.02 / 0.03 / 0.03 | 0.01 / 0.01 / 0.01 | 0.02 / 0.00 / 0.02 | 0.00 / 0.38 / 0.38 | 0.00 / 0.00 |
| 2 | refit | left | 0.08 / 0.27 / 0.32 | 0.02 / 0.03 / 0.04 | 0.01 / 0.01 / 0.01 | 0.00 / 0.24 / 0.24 | 0.00 / 0.00 |
| 2 | refit | right | 0.00 / 0.02 / 0.02 | 0.01 / 0.02 / 0.02 | 0.02 / 0.00 / 0.02 | 0.00 / 0.36 / 0.36 | 0.00 / 0.00 |
| 2 | first_fire | left | 0.57 / 0.70 / 0.90 | 0.03 / 0.04 / 0.04 | 0.05 / 0.09 / 0.13 | 0.11 / 0.39 / 0.49 | 0.00 / 0.00 |
| 2 | first_fire | right | 0.31 / 0.39 / 0.48 | 0.01 / 0.01 / 0.01 | 0.03 / 0.07 / 0.10 | 0.03 / 0.31 / 0.34 | 0.00 / 0.00 |
| 2 | cold_rel | left | 0.98 / 1.26 / 1.71 | 0.56 / 0.64 / 0.79 | 0.73 / 0.48 / 0.88 | 0.28 / 1.00 / 1.14 | 0.00 / 0.00 |
| 2 | cold_rel | right | 0.29 / 0.29 / 0.41 | 0.39 / 0.42 / 0.50 | 0.47 / 0.22 / 0.54 | 0.14 / 0.89 / 0.98 | 0.00 / 0.00 |
| 2 | refit_rel | left | 0.72 / 1.09 / 1.48 | 0.88 / 0.92 / 1.19 | 0.87 / 0.56 / 1.07 | 0.33 / 1.04 / 1.20 | 0.00 / 0.00 |
| 2 | refit_rel | right | 0.18 / 0.21 / 0.30 | 0.56 / 0.60 / 0.71 | 0.55 / 0.24 / 0.63 | 0.14 / 0.89 / 0.97 | 0.00 / 0.00 |
| 2 | first_fire_rel | left | 2.46 / 2.37 / 3.55 | 1.03 / 1.24 / 1.57 | 1.43 / 1.07 / 1.99 | 0.98 / 1.62 / 2.24 | 0.00 / 0.00 |
| 2 | first_fire_rel | right | 1.37 / 1.34 / 1.92 | 0.51 / 0.55 / 0.70 | 0.73 / 0.57 / 1.04 | 0.47 / 0.93 / 1.25 | 0.00 / 0.00 |
| 2 | cold_pose | left | 17.98 / 12.56 / 33.51 (lifted 18.29 / 12.80) | 0.52 / 1.42 / 1.58 | 34.62 / 11.76 / 31.99 (lifted 34.13 / 11.87) | 10.61 / 24.95 / 22.01 (lifted 10.73 / 24.65) | 0.00 / 0.00 |
| 2 | cold_pose | right | 14.45 / 10.84 / 28.69 (lifted 14.83 / 11.15) | 0.27 / 0.69 / 0.76 | 29.55 / 9.16 / 25.37 (lifted 28.87 / 9.28) | 7.41 / 24.05 / 20.16 (lifted 7.57 / 23.57) | 0.00 / 0.00 |
| 2 | first_fire_pose | left | 14.99 / 12.33 / 30.70 (lifted 16.15 / 13.10) | 0.89 / 1.53 / 3.23 (lifted 0.88 / 1.54) | 30.92 / 11.98 / 37.33 (lifted 28.85 / 12.62) | 6.86 / 25.74 / 27.29 (lifted 7.55 / 24.23) | 9.55 / 1.36 |
| 2 | first_fire_pose | right | 14.88 / 11.83 / 28.95 (lifted 15.72 / 12.42) | 0.45 / 0.66 / 0.81 (lifted 0.45 / 0.66) | 26.81 / 9.15 / 24.11 (lifted 25.12 / 9.73) | 8.14 / 21.99 / 19.46 (lifted 8.78 / 20.76) | 0.00 / 0.00 |
| 12 | cold | left | 0.06 / 0.16 / 0.17 | 0.01 / 0.01 / 0.01 | 0.01 / 0.01 / 0.01 | 0.00 / 0.23 / 0.24 | 0.00 / 0.00 |
| 12 | cold | right | 0.00 / 0.01 / 0.01 | 0.00 / 0.00 / 0.00 | 0.01 / 0.00 / 0.01 | 0.00 / 0.29 / 0.29 | 0.00 / 0.00 |
| 12 | refit | left | 0.02 / 0.14 / 0.14 | 0.01 / 0.01 / 0.01 | 0.01 / 0.00 / 0.01 | 0.00 / 0.22 / 0.22 | 0.00 / 0.00 |
| 12 | refit | right | 0.00 / 0.01 / 0.01 | 0.00 / 0.01 / 0.01 | 0.01 / 0.00 / 0.01 | 0.00 / 0.28 / 0.28 | 0.00 / 0.00 |
| 12 | first_fire | left | 0.15 / 0.27 / 0.29 | 0.01 / 0.02 / 0.02 | 0.03 / 0.06 / 0.08 | 0.04 / 0.30 / 0.35 | 0.00 / 0.00 |
| 12 | first_fire | right | 0.06 / 0.10 / 0.10 | 0.00 / 0.00 / 0.00 | 0.00 / 0.04 / 0.04 | 0.00 / 0.23 / 0.23 | 0.00 / 0.00 |
| 12 | cold_rel | left | 0.75 / 0.98 / 1.30 (lifted 0.74 / 0.97) | 0.57 / 0.67 / 0.82 (lifted 0.59 / 0.70) | 0.81 / 0.63 / 0.96 (lifted 0.81 / 0.62) | 0.40 / 1.12 / 1.31 (lifted 0.41 / 1.11) | 0.00 / 0.00 |
| 12 | cold_rel | right | 0.25 / 0.24 / 0.34 (lifted 0.25 / 0.23) | 0.36 / 0.42 / 0.48 (lifted 0.38 / 0.45) | 0.48 / 0.22 / 0.55 (lifted 0.48 / 0.21) | 0.13 / 0.80 / 0.89 | 0.00 / 0.00 |
| 12 | refit_rel | left | 0.55 / 0.85 / 1.12 | 0.76 / 0.82 / 1.05 | 0.86 / 0.65 / 1.07 | 0.41 / 1.08 / 1.27 | 0.00 / 0.00 |
| 12 | refit_rel | right | 0.18 / 0.19 / 0.27 | 0.52 / 0.57 / 0.66 | 0.58 / 0.26 / 0.67 | 0.13 / 0.78 / 0.86 | 0.00 / 0.00 |
| 12 | first_fire_rel | left | 1.79 / 1.89 / 2.67 | 0.95 / 1.09 / 1.41 | 1.42 / 1.15 / 1.92 (lifted 1.41 / 1.16) | 1.09 / 1.67 / 2.24 | 0.00 / 0.00 |
| 12 | first_fire_rel | right | 0.96 / 0.97 / 1.34 | 0.44 / 0.48 / 0.61 | 0.61 / 0.52 / 0.90 | 0.41 / 0.75 / 1.03 | 0.00 / 0.00 |
| 12 | cold_pose | left | 17.58 / 12.52 / 34.91 (lifted 18.64 / 13.57) | 0.45 / 1.35 / 1.42 (lifted 0.45 / 1.35) | 35.77 / 11.22 / 31.38 (lifted 33.79 / 11.90) | 10.03 / 26.62 / 22.16 (lifted 10.62 / 24.96) | 0.00 / 0.00 |
| 12 | cold_pose | right | 15.80 / 12.20 / 32.97 (lifted 17.03 / 13.38) | 0.23 / 0.75 / 0.81 | 35.74 / 10.75 / 29.54 (lifted 33.12 / 11.61) | 8.97 / 30.26 / 24.38 (lifted 9.85 / 28.07) | 0.00 / 0.00 |
| 12 | first_fire_pose | left | 14.24 / 12.06 / 32.08 (lifted 16.66 / 13.88) | 0.75 / 1.27 / 1.53 (lifted 0.75 / 1.28) | 34.70 / 11.00 / 37.17 (lifted 29.84 / 12.56) | 6.65 / 28.82 / 28.07 (lifted 7.95 / 24.88) | 8.19 / 1.36 |
| 12 | first_fire_pose | right | 15.43 / 12.40 / 33.19 (lifted 17.52 / 14.27) | 0.36 / 0.63 / 0.73 | 33.84 / 9.77 / 27.68 (lifted 29.38 / 11.64) | 8.73 / 28.35 / 22.56 (lifted 10.41 / 24.42) | 0.00 / 0.00 |

## (3) The scores against the bound (the lifted run's emitted scores = pre-divisor)

The margin is the true state's W-relative score (for W, minus the best other). "Emitted margin" is what the
bound-20 run emits. The "limit" columns give the sign-wrong % of the infinite-squeeze limit, i.e. the linear
form hi: sC + sM − sY, lo: sC + sY − sM, which is the sim's regime. max/margin is the factor that sets how far a
cell is from that limit. The 1e12 entries are cells of erased windows, where a margin is exactly 0.

| ppc | regime | state | max p50 | max p99 | minor p50 | margin p1 | div p50 | div p99 | emitted margin p1 | max/margin p99 | limit wrong hi / lo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | cold | W | 43.15 | 59.78 | 30.62 | 4.23 | 2.16 | 2.99 | 2.38 | 8.14 | 0.40 / 2.39 |
| 2 | cold | C | 22.55 | 45.14 | 14.00 | 8.34 | 1.13 | 2.26 | 5.40 | 3.69 | 8.08 / 2.09 |
| 2 | cold | M | 35.27 | 55.19 | 13.31 | 6.28 | 1.76 | 2.76 | 2.81 | 7.11 | 74.68 / 0.01 |
| 2 | cold | Y | 35.06 | 54.19 | 16.45 | 3.61 | 1.75 | 2.71 | 1.69 | 10.86 | 0.00 / 4.87 |
| 2 | first_fire | W | 47.72 | 76.33 | 30.71 | 1.11 | 2.39 | 3.82 | 0.53 | 19.45 | 2.52 / 4.27 |
| 2 | first_fire | C | 26.46 | 54.92 | 14.13 | 7.13 | 1.32 | 2.75 | 3.68 | 5.43 | 15.32 / 6.26 |
| 2 | first_fire | M | 36.89 | 71.46 | 13.95 | 4.67 | 1.84 | 3.57 | 2.08 | 9.60 | 65.02 / 0.03 |
| 2 | first_fire | Y | 37.01 | 69.59 | 17.26 | 2.93 | 1.85 | 3.48 | 1.42 | 12.46 | 0.00 / 10.47 |
| 2 | cold_rel | W | 25.48 | 38.58 | 18.31 | -0.27 | 1.27 | 1.93 | -0.25 | 19.56 | 1.78 / 2.44 |
| 2 | cold_rel | C | 15.03 | 24.71 | 7.47 | 2.44 | 1.00 | 1.24 | 2.31 | 5.78 | 4.27 / 3.84 |
| 2 | cold_rel | M | 17.94 | 30.65 | 9.20 | 1.89 | 1.00 | 1.53 | 1.58 | 9.63 | 35.62 / 0.10 |
| 2 | cold_rel | Y | 17.19 | 26.97 | 10.45 | 0.29 | 1.00 | 1.35 | 0.25 | 12.85 | 0.02 / 6.31 |
| 2 | first_fire_rel | W | 30.20 | 64.50 | 18.45 | -2.38 | 1.51 | 3.22 | -2.12 | 40.11 | 5.93 / 4.74 |
| 2 | first_fire_rel | C | 17.95 | 40.03 | 7.97 | 1.01 | 1.00 | 2.00 | 0.93 | 9.14 | 10.79 / 9.45 |
| 2 | first_fire_rel | M | 20.02 | 58.54 | 9.10 | 0.39 | 1.00 | 2.93 | 0.33 | 14.48 | 46.41 / 0.33 |
| 2 | first_fire_rel | Y | 20.57 | 53.25 | 9.99 | -0.32 | 1.03 | 2.66 | -0.28 | 17.48 | 0.21 / 13.23 |
| 2 | cold_pose | W | 22.46 | 35.12 | 2.37 | -3.67 | 1.12 | 1.76 | -3.59 | 540.34 | 0.99 / 0.17 |
| 2 | cold_pose | C | 12.51 | 18.54 | 2.88 | 1.70 | 1.00 | 1.00 | 1.70 | 1.41 | 0.32 / 2.26 |
| 2 | cold_pose | M | 19.56 | 30.59 | 1.54 | -2.77 | 1.00 | 1.53 | -2.19 | 644.76 | 95.95 / 0.58 |
| 2 | cold_pose | Y | 18.72 | 28.69 | 1.52 | -3.24 | 1.00 | 1.43 | -2.62 | 372.06 | 0.52 / 98.97 |
| 12 | cold | W | 63.80 | 89.07 | 45.37 | 8.49 | 3.19 | 4.45 | 3.20 | 6.23 | 0.12 / 3.04 |
| 12 | cold | C | 31.77 | 71.41 | 21.51 | 13.00 | 1.59 | 3.57 | 5.36 | 3.73 | 12.06 / 1.20 |
| 12 | cold | M | 48.58 | 74.23 | 17.25 | 8.63 | 2.43 | 3.71 | 2.90 | 6.90 | 80.50 / 0.00 |
| 12 | cold | Y | 53.80 | 81.58 | 21.89 | 5.87 | 2.69 | 4.08 | 1.82 | 10.39 | 0.00 / 3.63 |
| 12 | first_fire | W | 70.46 | 111.99 | 46.48 | 5.58 | 3.52 | 5.60 | 1.84 | 10.61 | 1.19 / 4.39 |
| 12 | first_fire | C | 37.57 | 82.66 | 21.38 | 11.39 | 1.88 | 4.13 | 4.04 | 4.95 | 16.07 / 6.70 |
| 12 | first_fire | M | 51.37 | 100.81 | 18.92 | 6.86 | 2.57 | 5.04 | 2.22 | 8.99 | 66.49 / 0.02 |
| 12 | first_fire | Y | 57.11 | 122.29 | 24.42 | 4.70 | 2.86 | 6.11 | 1.60 | 11.72 | 0.00 / 12.75 |
| 12 | cold_rel | W | 31.66 | 45.51 | 23.59 | 0.43 | 1.58 | 2.28 | 0.33 | 14.78 | 1.26 / 1.70 |
| 12 | cold_rel | C | 18.22 | 28.88 | 9.34 | 2.99 | 1.00 | 1.44 | 2.83 | 5.29 | 2.84 / 3.21 |
| 12 | cold_rel | M | 21.51 | 35.75 | 11.23 | 2.50 | 1.08 | 1.79 | 1.90 | 8.57 | 34.63 / 0.09 |
| 12 | cold_rel | Y | 20.25 | 30.12 | 12.87 | 0.31 | 1.01 | 1.51 | 0.24 | 11.89 | 0.05 / 7.16 |
| 12 | first_fire_rel | W | 40.10 | 85.05 | 24.60 | -1.93 | 2.01 | 4.25 | -1.65 | 29.62 | 4.20 / 4.14 |
| 12 | first_fire_rel | C | 22.80 | 54.68 | 10.52 | 1.51 | 1.14 | 2.73 | 1.36 | 7.66 | 10.12 / 9.10 |
| 12 | first_fire_rel | M | 25.58 | 73.71 | 11.60 | 0.90 | 1.28 | 3.69 | 0.71 | 12.45 | 47.95 / 0.34 |
| 12 | first_fire_rel | Y | 26.98 | 82.77 | 12.66 | -0.08 | 1.35 | 4.14 | -0.07 | 15.11 | 0.26 / 16.65 |
| 12 | cold_pose | W | 28.93 | 44.49 | 2.29 | -3.59 | 1.45 | 2.22 | -3.22 | 704.47 | 0.81 / 0.14 |
| 12 | cold_pose | C | 15.75 | 22.29 | 3.97 | 1.90 | 1.00 | 1.11 | 1.91 | 1.19 | 0.34 / 2.27 |
| 12 | cold_pose | M | 24.83 | 38.34 | 1.50 | -2.61 | 1.24 | 1.92 | -1.70 | 889.69 | 96.63 / 0.46 |
| 12 | cold_pose | Y | 24.49 | 36.98 | 1.52 | -3.16 | 1.22 | 1.85 | -2.07 | 539.06 | 0.47 / 99.53 |

## (4) Whole-page tile attempts (`tiles.attempt_tile`, scan then retry150), all levels

Each stream column reads certified / failed / below floor / WRONG.

| ppc | regime | tiles | hi @20 | lo @20 | hi lifted | lo lifted | both 20 / lifted |
|---|---|---|---|---|---|---|---|
| 2 | cold | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 2 | refit | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 2 | first_fire | 936 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 936 |
| 2 | cold_rel | 840 | 812 / 28 / 0 / 0 | 794 / 46 / 0 / 0 | 811 / 29 / 0 / 0 | 793 / 47 / 0 / 0 | 794 / 793 |
| 2 | refit_rel | 840 | 802 / 38 / 0 / 0 | 789 / 51 / 0 / 0 | 803 / 37 / 0 / 0 | 789 / 51 / 0 / 0 | 789 / 789 |
| 2 | first_fire_rel | 936 | 883 / 53 / 0 / 0 | 875 / 61 / 0 / 0 | 884 / 52 / 0 / 0 | 875 / 61 / 0 / 0 | 873 / 874 |
| 2 | cold_pose | 840 | 72 / 768 / 0 / 0 | 129 / 711 / 0 / 0 | 71 / 769 / 0 / 0 | 129 / 711 / 0 / 0 | 65 / 64 |
| 2 | first_fire_pose | 936 | 81 / 804 / 51 / 0 | 131 / 796 / 9 / 0 | 87 / 798 / 51 / 0 | 134 / 793 / 9 / 0 | 68 / 75 |
| 4 | cold | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 4 | refit | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 4 | first_fire | 936 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 936 |
| 4 | cold_rel | 840 | 806 / 34 / 0 / 0 | 800 / 40 / 0 / 0 | 807 / 33 / 0 / 0 | 798 / 42 / 0 / 0 | 800 / 798 |
| 4 | refit_rel | 840 | 800 / 40 / 0 / 0 | 794 / 46 / 0 / 0 | 800 / 40 / 0 / 0 | 794 / 46 / 0 / 0 | 794 / 794 |
| 4 | first_fire_rel | 936 | 886 / 50 / 0 / 0 | 880 / 56 / 0 / 0 | 885 / 51 / 0 / 0 | 877 / 59 / 0 / 0 | 880 / 876 |
| 4 | cold_pose | 840 | 71 / 769 / 0 / 0 | 129 / 711 / 0 / 0 | 72 / 768 / 0 / 0 | 130 / 710 / 0 / 0 | 63 / 64 |
| 4 | first_fire_pose | 936 | 79 / 806 / 51 / 0 | 134 / 793 / 9 / 0 | 84 / 801 / 51 / 0 | 141 / 786 / 9 / 0 | 66 / 71 |
| 6 | cold | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 6 | refit | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 6 | first_fire | 936 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 936 |
| 6 | cold_rel | 840 | 775 / 65 / 0 / 0 | 772 / 68 / 0 / 0 | 774 / 66 / 0 / 0 | 771 / 69 / 0 / 0 | 768 / 767 |
| 6 | refit_rel | 840 | 772 / 68 / 0 / 0 | 769 / 71 / 0 / 0 | 772 / 68 / 0 / 0 | 768 / 72 / 0 / 0 | 768 / 767 |
| 6 | first_fire_rel | 936 | 847 / 89 / 0 / 0 | 838 / 98 / 0 / 0 | 847 / 89 / 0 / 0 | 838 / 98 / 0 / 0 | 829 / 829 |
| 6 | cold_pose | 840 | 40 / 800 / 0 / 0 | 67 / 773 / 0 / 0 | 41 / 799 / 0 / 0 | 68 / 772 / 0 / 0 | 30 / 30 |
| 6 | first_fire_pose | 936 | 44 / 871 / 21 / 0 | 66 / 861 / 9 / 0 | 48 / 867 / 21 / 0 | 70 / 857 / 9 / 0 | 26 / 31 |
| 12 | cold | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 12 | refit | 840 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 0 / 0 / 0 | 840 / 840 |
| 12 | first_fire | 936 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 0 / 0 / 0 | 936 / 936 |
| 12 | cold_rel | 840 | 803 / 37 / 0 / 0 | 794 / 46 / 0 / 0 | 803 / 37 / 0 / 0 | 793 / 47 / 0 / 0 | 794 / 793 |
| 12 | refit_rel | 840 | 800 / 40 / 0 / 0 | 790 / 50 / 0 / 0 | 799 / 41 / 0 / 0 | 789 / 51 / 0 / 0 | 789 / 788 |
| 12 | first_fire_rel | 936 | 877 / 59 / 0 / 0 | 868 / 68 / 0 / 0 | 880 / 56 / 0 / 0 | 868 / 68 / 0 / 0 | 866 / 867 |
| 12 | cold_pose | 840 | 55 / 785 / 0 / 0 | 115 / 725 / 0 / 0 | 59 / 781 / 0 / 0 | 114 / 726 / 0 / 0 | 47 / 50 |
| 12 | first_fire_pose | 936 | 65 / 829 / 42 / 0 | 113 / 814 / 9 / 0 | 71 / 823 / 42 / 0 | 121 / 806 / 9 / 0 | 50 / 58 |

## (5) Heads and the erasure trigger

- **truth and rel arms.** Every lane at every level was accepted. Each one adopted the corrected arm and the
  context head, erased nothing (`cmy_unsupported_streams` returned ()) and clipped no stream. The held-out loss
  was 0.008–0.015 (truth) and 0.063–0.091 (rel). Every first-fire window fitted and erased nothing.
- **pose arm.**
  - The whole-page lanes were accepted with no corrected arm, held-out loss 0.45–0.51, nothing erased.
  - First fire erased hi (stream 0) in 6 of 140 windows at ppc 2 and 4, plus both streams in a seventh. Every
    one is at the page's left edge, window x cells 0–200: (y0 0, 160, 480, 960, 1120, 1600, 1760).
  - At ppc 6 hi was erased in 3 windows and lo in 1; at ppc 12, hi in 6 and lo in 1.
  - Effect: the erased stream's LLRs are exactly 0 on those windows, giving 4–10 % zero hi LLRs and 1.4 % zero
    lo LLRs in the left zone, and 21–51 hi tile reads below the floor.

## Reading

1. **The divisor flips no label signs at the truth pose.**
   - At most 28 cells change sign per regime, zone and state at any level (72 per regime), out of 0.37–0.71 M
     cells per state and zone.
   - The sign-wrong rates at 20 and lifted agree to 0.004 pp, and they track the argmax error state by state.
     Cold / refit: W 0.00–0.15 / 0.01–0.30 %, Y lo 0.22–0.38 %, C and M ≤ 0.03 %. First fire: W ≤ 0.57 /
     0.70 %, Y lo ≤ 0.39 %, C and M ≤ 0.09 %.
   - The scores: max |s| p50 23–70 and p99 45–122. The divisor's median is 1.1–3.5 (p99 ≤ 6.1). The margin the
     bound-20 run emits has a p1 of 0.53–5.4, against the sim's ~1e-4.
   - The mechanism's shape is present on paper but out of reach. In the infinite-squeeze limit 58–83 % of M
     cells would lose hi, but max/margin p99 is 3.7–19, against the sim's ~2e5.
2. **The cold furniture-only fit and the GT refit read alike with respect to the bound.**
   - Truth arm: the refit trims W's argmax error slightly, e.g. ppc 12 left 0.17 → 0.14 %.
   - Rel arm: the refit loses 0–6 tiles (794 → 789 at ppc 2 and 12, 800 → 794 at ppc 4).
   - The bound changes neither.
3. **Every tile certifies at 20 and lifted at the truth pose.**
   - 840/840 both streams at all four levels, cold and refit, all by scan (no retry needed); first fire
     936/936.
   - At the charter's rel arm: 768–800 of 840 both streams (cold) and 829–880 of 936 (first fire). The bound
     changes up to 321 cells (0.07 % of a state) and moves the both-streams count by −4 to +1 tiles per row.
   - 0 WRONG certificates anywhere.
4. **The bound matters only in the misregistered pose arm, and little there.**
   - Signs change on up to 5.6 % of a state's cells, and wrong rates move up to 4.9 pp in both directions
     (M hi better lifted, W worse).
   - Lifting it gains +5 to +8 first-fire tiles and −1 to +3 whole-page tiles.
   - That arm is registration-limited, not divisor-limited: argmax wrong 19–37 % on W/M/Y; 30–65 whole-page
     tiles, 26–75 first-fire tile reads.
5. **Registration drives M1's yield.**
   - Whole page, both streams: 30–65 tiles with no field (pose), 768–800 with a converged field (rel), 840 at the
     truth pose.
   - The rel−truth gap (40–72 tiles; argmax error 0.25–2.1 % per state against ≤ 0.38 %, cold and refit) is,
     by construction, C's non-affine residual inside the 200-cell windows (0.43 dots median rms, up to 1 dot).
     That residual sits in all three planes at rel. The e044 page is non-affine by ~2 dots rms (readout).
