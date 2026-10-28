# Crop cases — sheet-I (sheet I pooled cmy8)

Format `L:c2-cmy8-r0700-p120-x1@3392x2368`, tile matrix 53x37, streams ['C', 'M', 'Y'], 3 capture(s) at [2400.0, 2400.0, 2400.0] dpi. Generated in 29.2 s from tree `88a530c9b270`.

## The gap (recomputed, cross-checked against the record)

holo3 baseline harvest: `post-7` (446525 TileOutcome rows).

| set | addresses | recorded |
|---|---:|---:|
| holo1 certified | 5297 | — |
| holo3 certified | 5439 | — |
| both | 5263 | — |
| **miss** (holo1 only) | 34 | 34 |
| **gain** (holo3 only) | 176 | 176 |
| neither | 410 | — |

Ground truth: golden payload `2445b95db5b4…` (1798761 B) re-encoded through holo1 generation, validated against 5297/5297 certificates in the archived holo1 state, zero mismatches.

## Captures and the cell→pixel fit

| # | capture id | shape (y, x) | ch | poses | px/cell | residual med / p99 / max px |
|---:|---|---|---:|---:|---:|---|
| 0 | `269d81217ec4…` | 28064x20416 | 3 | 1149 | 8.008 | 3.5 / 16.3 / 24.5 |
| 1 | `a410631d6ff6…` | 28064x20416 | 3 | 1695 | 8.008 | 3.6 / 16.9 / 24.4 |
| 2 | `36b90a50f272…` | 28064x20416 | 3 | 1228 | 8.008 | 3.5 / 17.5 / 25.0 |

The pixel bbox is padded by 32 cells' worth of pixels on all sides before clipping, which is the margin the max residual has to fit inside.

## Cases (26) — classes miss, gain, halo 240 cells, merge-gap 2 tiles, max span 768 cells

| case | tiles | targets | controls | cell bbox (x0,y0,x1,y1) | crop px (y, x) | MB/crop |
|---|---:|---:|---:|---|---|---:|
| `sheet-I-c01` | 15 | 15 | 291 | (720, 0, 1520, 816) | 7056x6922 | 146.5 |
| `sheet-I-c02` | 1 | 1 | 57 | (1360, 0, 1904, 304) | 2953x4869 | 43.1 |
| `sheet-I-c03` | 13 | 14 | 360 | (1424, 0, 2288, 880) | 7570x7434 | 168.8 |
| `sheet-I-c04` | 6 | 6 | 212 | (0, 0, 624, 752) | 6543x5512 | 108.2 |
| `sheet-I-c05` | 3 | 3 | 150 | (336, 144, 944, 752) | 5389x5383 | 87.0 |
| `sheet-I-c06` | 13 | 13 | 401 | (720, 336, 1520, 1392) | 8979x6922 | 186.5 |
| `sheet-I-c07` | 8 | 8 | 264 | (0, 464, 624, 1392) | 7953x5513 | 131.5 |
| `sheet-I-c08` | 10 | 10 | 359 | (336, 464, 1008, 1584) | 9491x5898 | 167.9 |
| `sheet-I-c09` | 25 | 25 | 591 | (1360, 464, 2352, 1648) | 10006x8460 | 254.0 |
| `sheet-I-c10` | 6 | 6 | 401 | (848, 912, 1648, 1968) | 8980x6923 | 186.5 |
| `sheet-I-c11` | 5 | 5 | 277 | (0, 976, 624, 1904) | 7953x5513 | 131.5 |
| `sheet-I-c12` | 9 | 9 | 365 | (336, 1168, 1008, 2288) | 9491x5898 | 167.9 |
| `sheet-I-c13` | 15 | 15 | 566 | (1360, 1168, 2352, 2288) | 9493x8459 | 240.9 |
| `sheet-I-c14` | 1 | 1 | 63 | (2064, 1424, 2368, 1968) | 4874x2949 | 43.1 |
| `sheet-I-c15` | 9 | 9 | 224 | (0, 1616, 496, 2608) | 8464x4489 | 114.0 |
| `sheet-I-c16` | 1 | 1 | 112 | (912, 1744, 1456, 2288) | 4875x4871 | 71.2 |
| `sheet-I-c17` | 16 | 17 | 451 | (1488, 1808, 2288, 2992) | 10005x6923 | 207.8 |
| `sheet-I-c18` | 12 | 12 | 412 | (336, 1872, 1200, 2928) | 8980x7435 | 200.3 |
| `sheet-I-c19` | 1 | 1 | 115 | (912, 2000, 1456, 2544) | 4876x4870 | 71.2 |
| `sheet-I-c20` | 1 | 1 | 125 | (720, 2320, 1264, 2864) | 4875x4871 | 71.2 |
| `sheet-I-c21` | 1 | 1 | 129 | (976, 2320, 1520, 2864) | 4875x4871 | 71.2 |
| `sheet-I-c22` | 1 | 1 | 102 | (0, 2448, 432, 2992) | 4875x3974 | 58.1 |
| `sheet-I-c23` | 18 | 22 | 419 | (1296, 2512, 2288, 3392) | 7571x8458 | 192.1 |
| `sheet-I-c24` | 8 | 8 | 210 | (336, 2576, 944, 3392) | 7055x5384 | 114.0 |
| `sheet-I-c25` | 3 | 3 | 194 | (720, 2768, 1392, 3392) | 5517x5896 | 97.6 |
| `sheet-I-c26` | 3 | 3 | 86 | (0, 3024, 624, 3392) | 3466x5510 | 57.3 |

Targets by class: gain 176, miss 34

- `sheet-I-c01`: (0, 19)/Y [gain], (1, 17)/Y [gain], (1, 19)/Y [gain], (2, 17)/Y [gain], (2, 18)/Y [gain], (2, 19)/Y [gain], (3, 18)/Y [gain], (4, 17)/Y [gain], (4, 19)/Y [gain], (5, 15)/Y [gain], (6, 17)/Y [gain], (7, 15)/Y [gain], (7, 17)/Y [gain], (8, 17)/Y [gain], (8, 19)/Y [gain]
- `sheet-I-c02`: (0, 25)/Y [gain]
- `sheet-I-c03`: (0, 31)/C [gain], (2, 29)/Y [gain], (2, 30)/Y [miss], (4, 30)/C [gain], (5, 30)/C [miss], (6, 27)/Y [miss], (6, 29)/Y [gain], (7, 29)/Y [gain], (7, 30)/Y [gain], (8, 26)/Y [gain], (8, 29)/Y [gain], (8, 30)/C [gain], (8, 30)/Y [gain], (9, 29)/Y [miss]
- `sheet-I-c04`: (2, 2)/Y [gain], (3, 0)/Y [gain], (3, 5)/C [gain], (4, 5)/C [gain], (7, 0)/Y [gain], (7, 2)/Y [gain]
- `sheet-I-c05`: (6, 10)/Y [gain], (7, 9)/Y [gain], (7, 10)/Y [gain]
- `sheet-I-c06`: (9, 15)/Y [gain], (9, 16)/Y [gain], (10, 19)/Y [gain], (12, 19)/Y [gain], (13, 16)/Y [gain], (13, 17)/Y [gain], (14, 17)/Y [gain], (15, 15)/Y [gain], (15, 17)/Y [gain], (15, 19)/Y [gain], (17, 15)/Y [gain], (17, 17)/Y [gain], (17, 19)/Y [gain]
- `sheet-I-c07`: (11, 1)/Y [gain], (12, 2)/Y [gain], (13, 5)/C [gain], (14, 5)/C [gain], (15, 2)/Y [gain], (15, 5)/C [gain], (16, 2)/Y [gain], (17, 5)/C [gain]
- `sheet-I-c08`: (11, 9)/Y [gain], (11, 10)/Y [gain], (12, 9)/Y [gain], (13, 10)/Y [miss], (13, 11)/Y [miss], (14, 10)/Y [gain], (16, 9)/Y [gain], (19, 10)/Y [gain], (19, 11)/Y [gain], (20, 10)/Y [miss]
- `sheet-I-c09`: (11, 29)/Y [gain], (12, 27)/Y [gain], (12, 29)/Y [gain], (12, 30)/C [miss], (13, 27)/Y [gain], (13, 30)/C [miss], (13, 31)/C [miss], (14, 29)/Y [gain], (14, 30)/C [gain], (15, 28)/Y [miss], (15, 29)/Y [gain], (16, 25)/C [gain], (17, 25)/C [gain], (17, 27)/Y [gain], (18, 27)/Y [gain], (18, 28)/Y [gain], (18, 30)/C [gain], (19, 30)/C [gain], (20, 27)/Y [gain], (20, 28)/Y [gain], (20, 29)/Y [gain], (20, 30)/Y [gain], (20, 32)/M [miss], (21, 30)/C [miss], (21, 31)/C [gain]
- `sheet-I-c10`: (18, 17)/Y [gain], (21, 19)/Y [gain], (22, 21)/C [gain], (24, 18)/Y [gain], (25, 18)/Y [gain], (26, 18)/Y [gain]
- `sheet-I-c11`: (19, 2)/Y [gain], (22, 0)/Y [gain], (22, 3)/Y [gain], (23, 5)/C [miss], (25, 2)/Y [gain]
- `sheet-I-c12`: (22, 11)/Y [miss], (24, 10)/Y [gain], (25, 10)/Y [miss], (28, 10)/Y [gain], (29, 9)/Y [gain], (29, 10)/Y [gain], (30, 9)/Y [gain], (31, 9)/Y [gain], (31, 10)/Y [gain]
- `sheet-I-c13`: (22, 25)/C [miss], (22, 29)/Y [gain], (22, 30)/Y [gain], (23, 30)/C [gain], (23, 32)/Y [gain], (25, 27)/Y [miss], (25, 30)/C [gain], (26, 27)/Y [miss], (26, 28)/Y [gain], (28, 29)/Y [gain], (28, 31)/C [gain], (29, 31)/C [gain], (30, 30)/C [miss], (31, 27)/Y [gain], (31, 31)/C [gain]
- `sheet-I-c14`: (26, 36)/Y [gain]
- `sheet-I-c15`: (29, 0)/Y [gain], (29, 1)/M [gain], (29, 2)/Y [miss], (30, 2)/Y [gain], (32, 3)/Y [gain], (33, 2)/Y [gain], (34, 2)/Y [gain], (35, 2)/Y [gain], (36, 3)/Y [gain]
- `sheet-I-c16`: (31, 18)/Y [miss]
- `sheet-I-c17`: (32, 30)/C [gain], (32, 31)/C [gain], (33, 28)/Y [miss], (34, 30)/C [miss], (35, 29)/C [miss], (35, 29)/Y [miss], (35, 30)/C [miss], (36, 29)/C [gain], (38, 28)/C [gain], (39, 27)/Y [gain], (40, 27)/Y [gain], (40, 28)/C [gain], (40, 29)/Y [gain], (40, 31)/C [gain], (41, 27)/Y [gain], (42, 27)/Y [gain], (42, 31)/C [gain]
- `sheet-I-c18`: (33, 9)/Y [gain], (33, 10)/Y [gain], (34, 9)/Y [gain], (36, 10)/Y [gain], (36, 11)/Y [gain], (36, 14)/C [gain], (37, 11)/Y [gain], (38, 9)/Y [gain], (38, 10)/Y [miss], (39, 9)/Y [gain], (39, 10)/Y [miss], (41, 11)/Y [gain]
- `sheet-I-c19`: (35, 18)/Y [gain]
- `sheet-I-c20`: (40, 15)/Y [gain]
- `sheet-I-c21`: (40, 19)/Y [miss]
- `sheet-I-c22`: (42, 2)/Y [gain]
- `sheet-I-c23`: (43, 30)/C [miss], (44, 27)/Y [gain], (45, 27)/Y [gain], (45, 30)/C [gain], (45, 31)/C [gain], (46, 31)/C [gain], (47, 27)/Y [miss], (47, 30)/C [gain], (47, 30)/Y [gain], (47, 31)/C [gain], (48, 30)/C [gain], (48, 30)/Y [gain], (49, 27)/Y [gain], (49, 30)/C [gain], (49, 30)/Y [gain], (50, 24)/Y [gain], (50, 25)/Y [gain], (50, 27)/Y [gain], (51, 28)/Y [gain], (52, 25)/C [gain], (52, 25)/Y [gain], (52, 29)/Y [gain]
- `sheet-I-c24`: (44, 9)/Y [gain], (46, 9)/Y [gain], (47, 9)/Y [gain], (48, 9)/Y [gain], (49, 9)/Y [gain], (50, 9)/Y [gain], (51, 10)/Y [gain], (52, 9)/Y [gain]
- `sheet-I-c25`: (47, 16)/Y [miss], (47, 17)/Y [miss], (49, 15)/Y [gain]
- `sheet-I-c26`: (51, 5)/C [gain], (52, 1)/M [gain], (52, 2)/Y [gain]

**Colour caveat.** A crop changes the context a colour calibration head pools over, so these cases SCREEN the gap; they do not settle it. A crop verdict that disagrees with the full-sheet record on a colour volume is evidence about the crop, not yet about the receiver.
