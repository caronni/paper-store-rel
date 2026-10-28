# Crop cases — xerox-c2-cmy7 (xerox c2-cmy7 (PK-FINAL))

Format `L:c2-cmy7-p120-v0@3328x2304`, tile matrix 52x36, streams ['main'], 1 capture(s) at [4800.0] dpi. Generated in 23.6 s from tree `88a530c9b270`.

## The gap (recomputed, cross-checked against the record)

holo3 baseline harvest: `post-6` (51052 TileOutcome rows).

| set | addresses | recorded |
|---|---:|---:|
| holo1 certified | 1559 | — |
| holo3 certified | 1564 | — |
| both | 1533 | — |
| **miss** (holo1 only) | 26 | 26 |
| **gain** (holo3 only) | 31 | 31 |
| neither | 282 | — |

Ground truth: golden payload `5963b9d16abc…` (686859 B) re-encoded through holo1 generation, validated against 1559/1559 certificates in the archived holo1 state, zero mismatches.

## Captures and the cell→pixel fit

| # | capture id | shape (y, x) | ch | poses | px/cell | residual med / p99 / max px |
|---:|---|---|---:|---:|---:|---|
| 0 | `01abdd8785c5…` | 56128x40832 | 3 | 1804 | 16.017 | 7.8 / 33.0 / 50.6 |

The pixel bbox is padded by 32 cells' worth of pixels on all sides before clipping, which is the margin the max residual has to fit inside.

## Cases (20) — classes miss, gain, halo 240 cells, merge-gap 2 tiles, max span 768 cells

| case | tiles | targets | controls | cell bbox (x0,y0,x1,y1) | crop px (y, x) | MB/crop |
|---|---:|---:|---:|---|---|---:|
| `xerox-c2-cmy7-c01` | 1 | 1 | 21 | (1040, 0, 1584, 304) | 5905x9741 | 172.6 |
| `xerox-c2-cmy7-c02` | 6 | 6 | 45 | (0, 0, 496, 752) | 13082x8978 | 352.4 |
| `xerox-c2-cmy7-c03` | 6 | 6 | 125 | (1488, 0, 2224, 1008) | 17188x12824 | 661.3 |
| `xerox-c2-cmy7-c04` | 3 | 3 | 39 | (1936, 0, 2304, 752) | 13080x6928 | 271.9 |
| `xerox-c2-cmy7-c05` | 2 | 2 | 41 | (0, 464, 496, 1200) | 12825x8978 | 345.4 |
| `xerox-c2-cmy7-c06` | 4 | 4 | 114 | (784, 784, 1584, 1584) | 13856x13847 | 575.6 |
| `xerox-c2-cmy7-c07` | 2 | 2 | 71 | (1488, 976, 2224, 1584) | 10779x12819 | 414.5 |
| `xerox-c2-cmy7-c08` | 2 | 2 | 33 | (1872, 1104, 2304, 1840) | 12824x7953 | 306.0 |
| `xerox-c2-cmy7-c09` | 1 | 1 | 25 | (0, 1168, 496, 1712) | 9750x8975 | 262.5 |
| `xerox-c2-cmy7-c10` | 2 | 2 | 59 | (784, 1360, 1392, 2032) | 11803x10770 | 381.4 |
| `xerox-c2-cmy7-c11` | 7 | 7 | 59 | (0, 1552, 496, 2672) | 18977x8983 | 511.4 |
| `xerox-c2-cmy7-c12` | 2 | 2 | 29 | (1936, 1552, 2304, 2288) | 12823x6928 | 266.5 |
| `xerox-c2-cmy7-c13` | 1 | 1 | 47 | (1680, 1744, 2224, 2288) | 9751x9744 | 285.0 |
| `xerox-c2-cmy7-c14` | 2 | 2 | 63 | (848, 2128, 1392, 2864) | 12827x9746 | 375.0 |
| `xerox-c2-cmy7-c15` | 1 | 1 | 27 | (0, 2576, 432, 3120) | 9749x7950 | 232.5 |
| `xerox-c2-cmy7-c16` | 9 | 9 | 82 | (1488, 2640, 2224, 3328) | 12060x12820 | 463.8 |
| `xerox-c2-cmy7-c17` | 1 | 1 | 22 | (1936, 2704, 2304, 3248) | 9748x6926 | 202.5 |
| `xerox-c2-cmy7-c18` | 1 | 1 | 39 | (848, 2768, 1392, 3312) | 9751x9744 | 285.0 |
| `xerox-c2-cmy7-c19` | 2 | 2 | 19 | (0, 2896, 432, 3328) | 7954x7949 | 189.7 |
| `xerox-c2-cmy7-c20` | 2 | 2 | 27 | (208, 2960, 752, 3328) | 6931x9741 | 202.5 |

Targets by class: gain 31, miss 26

- `xerox-c2-cmy7-c01`: (0, 20) [miss]
- `xerox-c2-cmy7-c02`: (1, 3) [miss], (2, 3) [miss], (3, 1) [miss], (4, 3) [miss], (5, 3) [miss], (7, 1) [miss]
- `xerox-c2-cmy7-c03`: (2, 30) [gain], (3, 30) [gain], (4, 27) [miss], (7, 30) [gain], (8, 30) [gain], (11, 27) [gain]
- `xerox-c2-cmy7-c04`: (3, 35) [miss], (4, 34) [miss], (7, 35) [miss]
- `xerox-c2-cmy7-c05`: (11, 3) [miss], (14, 2) [gain]
- `xerox-c2-cmy7-c06`: (16, 20) [gain], (19, 17) [miss], (19, 20) [gain], (20, 16) [miss]
- `xerox-c2-cmy7-c07`: (19, 27) [miss], (20, 30) [miss]
- `xerox-c2-cmy7-c08`: (21, 34) [gain], (24, 33) [gain]
- `xerox-c2-cmy7-c09`: (22, 3) [gain]
- `xerox-c2-cmy7-c10`: (25, 16) [gain], (27, 17) [gain]
- `xerox-c2-cmy7-c11`: (28, 2) [miss], (31, 2) [gain], (32, 2) [gain], (34, 3) [miss], (35, 2) [gain], (36, 3) [miss], (37, 3) [miss]
- `xerox-c2-cmy7-c12`: (28, 34) [miss], (31, 34) [gain]
- `xerox-c2-cmy7-c13`: (31, 30) [gain]
- `xerox-c2-cmy7-c14`: (37, 17) [gain], (40, 17) [gain]
- `xerox-c2-cmy7-c15`: (44, 2) [gain]
- `xerox-c2-cmy7-c16`: (45, 28) [miss], (45, 30) [miss], (46, 27) [miss], (49, 30) [gain], (50, 27) [gain], (50, 30) [gain], (51, 27) [gain], (51, 28) [gain], (51, 30) [gain]
- `xerox-c2-cmy7-c17`: (46, 34) [gain]
- `xerox-c2-cmy7-c18`: (47, 17) [gain]
- `xerox-c2-cmy7-c19`: (49, 2) [gain], (50, 1) [gain]
- `xerox-c2-cmy7-c20`: (50, 7) [miss], (51, 7) [miss]

**Colour caveat.** A crop changes the context a colour calibration head pools over, so these cases SCREEN the gap; they do not settle it. A crop verdict that disagrees with the full-sheet record on a colour volume is evidence about the crop, not yet about the receiver.
