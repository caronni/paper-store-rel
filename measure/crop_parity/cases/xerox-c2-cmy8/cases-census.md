# Crop cases — xerox-c2-cmy8 (xerox c2-cmy8)

Format `L:c2-cmy8-p120-v0@3328x2304`, tile matrix 52x36, streams ['C', 'M', 'Y'], 1 capture(s) at [4800.0] dpi. Generated in 39.2 s from tree `88a530c9b270`.

## The gap (recomputed, cross-checked against the record)

holo3 baseline harvest: `run-4` (16522 TileOutcome rows).

| set | addresses | recorded |
|---|---:|---:|
| holo1 certified | 5370 | — |
| holo3 certified | 5422 | — |
| both | 5334 | — |
| **miss** (holo1 only) | 36 | 36 |
| **gain** (holo3 only) | 88 | 88 |
| neither | 158 | — |

Ground truth: golden payload `f13c34db6c96…` (718413 B) re-encoded through holo1 generation, validated against 5370/5370 certificates in the archived holo1 state, zero mismatches.

## Captures and the cell→pixel fit

| # | capture id | shape (y, x) | ch | poses | px/cell | residual med / p99 / max px |
|---:|---|---|---:|---:|---:|---|
| 0 | `cf6427d0d66a…` | 56128x40832 | 3 | 1890 | 16.004 | 7.9 / 37.2 / 65.0 |

The pixel bbox is padded by 32 cells' worth of pixels on all sides before clipping, which is the margin the max residual has to fit inside.

## Cases (16) — classes miss, gain, halo 240 cells, merge-gap 2 tiles, max span 768 cells

| case | tiles | targets | controls | cell bbox (x0,y0,x1,y1) | crop px (y, x) | MB/crop |
|---|---:|---:|---:|---|---|---:|
| `xerox-c2-cmy8-c01` | 16 | 18 | 358 | (0, 0, 752, 1008) | 17187x13063 | 673.5 |
| `xerox-c2-cmy8-c02` | 17 | 17 | 376 | (912, 0, 1904, 752) | 13093x16898 | 663.7 |
| `xerox-c2-cmy8-c03` | 7 | 7 | 380 | (1040, 336, 1776, 1328) | 16931x12807 | 650.5 |
| `xerox-c2-cmy8-c04` | 1 | 1 | 61 | (0, 592, 304, 1136) | 9745x5894 | 172.3 |
| `xerox-c2-cmy8-c05` | 3 | 3 | 141 | (1872, 592, 2304, 1328) | 12823x7942 | 305.5 |
| `xerox-c2-cmy8-c06` | 5 | 7 | 247 | (0, 848, 752, 1520) | 11806x13059 | 462.5 |
| `xerox-c2-cmy8-c07` | 8 | 9 | 376 | (1040, 848, 1776, 1840) | 16931x12807 | 650.5 |
| `xerox-c2-cmy8-c08` | 14 | 17 | 376 | (0, 1232, 816, 2160) | 15908x14086 | 672.2 |
| `xerox-c2-cmy8-c09` | 2 | 2 | 72 | (2000, 1488, 2304, 2096) | 10771x5894 | 190.5 |
| `xerox-c2-cmy8-c10` | 4 | 4 | 237 | (1168, 1552, 1776, 2352) | 13853x10758 | 447.1 |
| `xerox-c2-cmy8-c11` | 10 | 13 | 332 | (0, 1680, 816, 2544) | 14883x14085 | 628.9 |
| `xerox-c2-cmy8-c12` | 7 | 12 | 204 | (1872, 1808, 2304, 2800) | 16923x7945 | 403.4 |
| `xerox-c2-cmy8-c13` | 5 | 5 | 197 | (1168, 2640, 1776, 3328) | 12059x10757 | 389.2 |
| `xerox-c2-cmy8-c14` | 6 | 7 | 180 | (16, 2832, 816, 3328) | 8988x13825 | 372.8 |
| `xerox-c2-cmy8-c15` | 1 | 1 | 78 | (656, 2960, 1200, 3328) | 6932x9729 | 202.3 |
| `xerox-c2-cmy8-c16` | 1 | 1 | 81 | (1488, 2960, 2032, 3328) | 6932x9730 | 202.3 |

Targets by class: gain 88, miss 36

- `xerox-c2-cmy8-c01`: (0, 2)/C [gain], (0, 5)/M [gain], (1, 3)/Y [miss], (2, 5)/C [gain], (2, 6)/C [miss], (3, 5)/C [gain], (3, 5)/Y [gain], (4, 3)/C [miss], (5, 5)/Y [gain], (5, 6)/C [gain], (6, 5)/C [miss], (6, 5)/Y [gain], (7, 0)/Y [miss], (7, 5)/Y [gain], (8, 0)/Y [gain], (9, 7)/Y [miss], (10, 4)/C [gain], (11, 6)/Y [miss]
- `xerox-c2-cmy8-c02`: (0, 19)/Y [gain], (0, 20)/C [miss], (0, 21)/C [gain], (0, 22)/C [miss], (0, 23)/M [gain], (0, 24)/Y [miss], (0, 25)/Y [miss], (1, 18)/Y [miss], (1, 23)/Y [miss], (2, 22)/C [gain], (4, 20)/M [gain], (4, 22)/C [miss], (4, 23)/C [miss], (4, 25)/M [gain], (5, 23)/C [miss], (6, 20)/M [gain], (7, 25)/M [gain]
- `xerox-c2-cmy8-c03`: (9, 20)/Y [gain], (9, 23)/C [miss], (10, 23)/C [miss], (13, 23)/Y [miss], (14, 23)/C [miss], (15, 20)/M [gain], (16, 23)/M [gain]
- `xerox-c2-cmy8-c04`: (13, 0)/Y [gain]
- `xerox-c2-cmy8-c05`: (13, 33)/Y [gain], (16, 33)/Y [miss], (16, 35)/C [miss]
- `xerox-c2-cmy8-c06`: (17, 7)/Y [gain], (18, 7)/Y [gain], (19, 3)/C [gain], (19, 4)/C [gain], (19, 4)/Y [gain], (19, 5)/C [gain], (19, 5)/Y [gain]
- `xerox-c2-cmy8-c07`: (17, 23)/C [miss], (17, 23)/Y [miss], (18, 23)/C [miss], (20, 20)/M [gain], (20, 22)/M [gain], (21, 20)/M [gain], (23, 20)/M [gain], (23, 23)/M [gain], (24, 20)/M [gain]
- `xerox-c2-cmy8-c08`: (23, 0)/M [gain], (23, 0)/Y [gain], (23, 3)/C [gain], (23, 5)/C [gain], (24, 0)/C [gain], (24, 0)/M [gain], (24, 8)/Y [gain], (25, 0)/M [gain], (26, 0)/M [gain], (27, 0)/C [gain], (27, 0)/M [gain], (27, 3)/Y [gain], (28, 0)/Y [gain], (28, 6)/Y [miss], (28, 8)/Y [gain], (29, 3)/C [gain], (29, 6)/Y [miss]
- `xerox-c2-cmy8-c09`: (27, 35)/C [gain], (28, 35)/Y [gain]
- `xerox-c2-cmy8-c10`: (28, 22)/C [miss], (30, 22)/C [miss], (30, 23)/C [gain], (32, 23)/Y [miss]
- `xerox-c2-cmy8-c11`: (30, 5)/Y [gain], (30, 8)/Y [miss], (31, 5)/M [gain], (32, 3)/C [gain], (33, 3)/C [gain], (34, 0)/C [gain], (34, 0)/M [gain], (34, 0)/Y [gain], (34, 3)/C [gain], (34, 4)/C [gain], (34, 5)/M [gain], (34, 5)/Y [gain], (35, 4)/Y [gain]
- `xerox-c2-cmy8-c12`: (32, 33)/M [miss], (32, 33)/Y [miss], (33, 33)/M [miss], (33, 33)/Y [miss], (35, 35)/C [gain], (35, 35)/M [gain], (36, 35)/C [gain], (36, 35)/M [gain], (37, 35)/C [gain], (37, 35)/M [gain], (38, 35)/Y [gain], (39, 35)/Y [gain]
- `xerox-c2-cmy8-c13`: (45, 23)/C [gain], (46, 22)/M [gain], (46, 23)/C [gain], (49, 22)/M [gain], (49, 23)/C [gain]
- `xerox-c2-cmy8-c14`: (48, 8)/Y [gain], (49, 4)/C [gain], (49, 5)/C [gain], (49, 7)/Y [gain], (51, 4)/M [gain], (51, 5)/M [gain], (51, 5)/Y [miss]
- `xerox-c2-cmy8-c15`: (50, 14)/C [gain]
- `xerox-c2-cmy8-c16`: (50, 27)/C [gain]

**Colour caveat.** A crop changes the context a colour calibration head pools over, so these cases SCREEN the gap; they do not settle it. A crop verdict that disagrees with the full-sheet record on a colour volume is evidence about the crop, not yet about the receiver.
