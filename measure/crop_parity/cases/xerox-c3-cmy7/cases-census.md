# Crop cases — xerox-c3-cmy7 (xerox c3-cmy7)

Format `L:c3-cmy7-p120-v0@2240x1536`, tile matrix 35x24, streams ['main'], 1 capture(s) at [2400.0] dpi. Generated in 3.5 s from tree `88a530c9b270`.

## The gap (recomputed, cross-checked against the record)

holo3 baseline harvest: `post-3` (6534 TileOutcome rows).

| set | addresses | recorded |
|---|---:|---:|
| holo1 certified | 720 | — |
| holo3 certified | 815 | — |
| both | 720 | — |
| **miss** (holo1 only) | 0 | 0 |
| **gain** (holo3 only) | 95 | 95 |
| neither | 25 | — |

Ground truth: golden payload `4f68dbf93232…` (301600 B) re-encoded through holo1 generation, validated against 720/720 certificates in the archived holo1 state, zero mismatches.

## Captures and the cell→pixel fit

| # | capture id | shape (y, x) | ch | poses | px/cell | residual med / p99 / max px |
|---:|---|---|---:|---:|---:|---|
| 0 | `20fc40cd4832…` | 28064x20416 | 3 | 808 | 12.008 | 3.9 / 19.3 / 34.6 |

The pixel bbox is padded by 32 cells' worth of pixels on all sides before clipping, which is the margin the max residual has to fit inside.

## Cases (8) — classes miss, gain, halo 240 cells, merge-gap 2 tiles, max span 768 cells

| case | tiles | targets | controls | cell bbox (x0,y0,x1,y1) | crop px (y, x) | MB/crop |
|---|---:|---:|---:|---|---|---:|
| `xerox-c3-cmy7-c01` | 2 | 2 | 41 | (336, 0, 880, 496) | 6738x7311 | 147.8 |
| `xerox-c3-cmy7-c02` | 20 | 20 | 54 | (1040, 0, 1536, 1008) | 12888x6749 | 260.9 |
| `xerox-c3-cmy7-c03` | 7 | 7 | 42 | (0, 0, 304, 1008) | 12886x4445 | 171.8 |
| `xerox-c3-cmy7-c04` | 7 | 7 | 51 | (0, 528, 304, 1712) | 15000x4450 | 200.2 |
| `xerox-c3-cmy7-c05` | 35 | 35 | 62 | (1040, 528, 1536, 1776) | 15772x6755 | 319.6 |
| `xerox-c3-cmy7-c06` | 20 | 20 | 48 | (1040, 1296, 1536, 2240) | 12120x6748 | 245.4 |
| `xerox-c3-cmy7-c07` | 3 | 3 | 43 | (336, 1808, 1008, 2240) | 5971x8846 | 158.5 |
| `xerox-c3-cmy7-c08` | 1 | 1 | 15 | (0, 1936, 432, 2240) | 4429x5962 | 79.2 |

Targets by class: gain 95

- `xerox-c3-cmy7-c01`: (0, 9) [gain], (3, 9) [gain]
- `xerox-c3-cmy7-c02`: (0, 20) [gain], (0, 21) [gain], (0, 22) [gain], (1, 22) [gain], (3, 20) [gain], (3, 21) [gain], (4, 21) [gain], (5, 21) [gain], (5, 23) [gain], (6, 21) [gain], (7, 20) [gain], (7, 22) [gain], (8, 20) [gain], (8, 22) [gain], (9, 21) [gain], (9, 22) [gain], (10, 21) [gain], (10, 23) [gain], (11, 20) [gain], (11, 21) [gain]
- `xerox-c3-cmy7-c03`: (1, 0) [gain], (3, 0) [gain], (4, 0) [gain], (7, 0) [gain], (8, 0) [gain], (9, 0) [gain], (11, 0) [gain]
- `xerox-c3-cmy7-c04`: (12, 0) [gain], (14, 0) [gain], (16, 0) [gain], (17, 0) [gain], (18, 0) [gain], (19, 0) [gain], (22, 0) [gain]
- `xerox-c3-cmy7-c05`: (12, 20) [gain], (12, 21) [gain], (12, 22) [gain], (12, 23) [gain], (13, 20) [gain], (13, 21) [gain], (13, 23) [gain], (14, 21) [gain], (14, 22) [gain], (14, 23) [gain], (15, 20) [gain], (15, 21) [gain], (15, 22) [gain], (16, 20) [gain], (16, 21) [gain], (16, 22) [gain], (17, 20) [gain], (17, 21) [gain], (17, 22) [gain], (17, 23) [gain], (18, 21) [gain], (18, 22) [gain], (18, 23) [gain], (19, 20) [gain], (19, 21) [gain], (19, 23) [gain], (20, 20) [gain], (20, 22) [gain], (20, 23) [gain], (21, 20) [gain], (21, 22) [gain], (22, 20) [gain], (22, 21) [gain], (23, 21) [gain], (23, 22) [gain]
- `xerox-c3-cmy7-c06`: (24, 20) [gain], (24, 21) [gain], (25, 20) [gain], (25, 21) [gain], (25, 22) [gain], (26, 22) [gain], (27, 21) [gain], (28, 21) [gain], (28, 22) [gain], (29, 20) [gain], (29, 21) [gain], (30, 21) [gain], (30, 22) [gain], (31, 21) [gain], (31, 22) [gain], (32, 21) [gain], (32, 22) [gain], (33, 22) [gain], (34, 22) [gain], (34, 23) [gain]
- `xerox-c3-cmy7-c07`: (32, 9) [gain], (33, 11) [gain], (34, 11) [gain]
- `xerox-c3-cmy7-c08`: (34, 2) [gain]

**Colour caveat.** A crop changes the context a colour calibration head pools over, so these cases SCREEN the gap; they do not settle it. A crop verdict that disagrees with the full-sheet record on a colour volume is evidence about the crop, not yet about the receiver.
