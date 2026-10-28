# Crop battery — xerox-c2-cmy7 (xerox c2-cmy7 (PK-FINAL))

Manifest `<checkout>/scratch/crop-parity/xerox-c2-cmy7/cases.json`, format `L:c2-cmy7-p120-v0@3328x2304`, classes miss, gain, generated 2026-08-30 21:31:22. holo1 tree `3537128d0084`, holo3 tree `f5d7c0e2efc8`.

Full-sheet record (`post-6`): holo1 1559, holo3 1564, both 1533 — miss 26, gain 31, neither 282.

Ground truth: golden payload `5963b9d16abc…` re-encoded through holo1 generation and validated against 1559 certificates of the archived holo1 state (every certificate in the archived holo1 state matches the re-encoded golden payload exactly).

## WRONG CERTIFICATES (expected: none)

None — every crop-minted certificate whose bits could be read matches the re-encoded golden payload.

## Address-frame check

Every crop certificate on both sides addresses a tile inside its case's cell rectangle: the printed address word carries the absolute tile counter, so a crop decodes into the FULL-SHEET frame with no origin shift applied.

## Per-class outcomes vs the full-sheet record

Counts over TARGET addresses compared this battery (a side counts only where its crop decode was available). `reproduces` = the crop verdict equals the recorded full-sheet verdict for that side — the expectation, not a bar.

| class | targets | crop holo1 cert | reproduces | crop holo3 cert | reproduces |
|---|---:|---:|---:|---:|---:|
| gain | 31 | 17/31 | 14/31 | 17/31 | 17/31 |
| miss | 26 | 17/26 | 17/26 | 17/26 | 9/26 |

## Agreement on targets

- both sides give the same crop verdict: 55
- the two sides disagree on the crop: 2
- undetermined (a side unavailable): 0

## Cases

### case `xerox-c2-cmy7-c01`

Cell bbox (1040, 0, 1584, 304), crop sha `64d45db604d5…`. Crop certificates: holo1 37, holo3 36 (GT-checked: holo1 37, holo3 36).

- **holo1**: ran, exit 2, wall 484.9 s (decoded 2026-08-30 15:51:12, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 138.3 s (decoded 2026-08-30 15:59:17, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 21/21 reproduced, 0 flipped; holo3: 21/21 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 11/11 | 11/11 |
| 64-127 | 10/10 | 10/10 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (0, 20) | miss | certified / uncertified | no | no | yes |

### case `xerox-c2-cmy7-c02`

Cell bbox (0, 0, 496, 752), crop sha `45327130bc5f…`. Crop certificates: holo1 80, holo3 78 (GT-checked: holo1 80, holo3 78).

- **holo1**: ran, exit 2, wall 1071.8 s (decoded 2026-08-30 16:01:36, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 342.7 s (decoded 2026-08-30 16:19:27, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 45/45 reproduced, 0 flipped; holo3: 45/45 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 12/12 | 12/12 |
| 64-127 | 16/16 | 16/16 |
| 128-191 | 15/15 | 15/15 |
| 192-255 | 2/2 | 2/2 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (1, 3) | miss | certified / uncertified | yes | yes | yes |
| (2, 3) | miss | certified / uncertified | yes | yes | yes |
| (3, 1) | miss | certified / uncertified | yes | yes | yes |
| (4, 3) | miss | certified / uncertified | yes | yes | yes |
| (5, 3) | miss | certified / uncertified | yes | yes | yes |
| (7, 1) | miss | certified / uncertified | yes | yes | yes |

### case `xerox-c2-cmy7-c03`

Cell bbox (1488, 0, 2224, 1008), crop sha `a51d4c3db60b…`. Crop certificates: holo1 179, holo3 179 (GT-checked: holo1 179, holo3 179).

- **holo1**: ran, exit 2, wall 1228.8 s (decoded 2026-08-30 16:25:11, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 230.7 s (decoded 2026-08-30 16:45:40, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 125/125 reproduced, 0 flipped; holo3: 125/125 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 36/36 | 36/36 |
| 64-127 | 36/36 | 36/36 |
| 128-191 | 28/28 | 28/28 |
| 192-255 | 11/11 | 11/11 |
| 256-319 | 14/14 | 14/14 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (2, 30) | gain | uncertified / certified | yes | yes | yes |
| (3, 30) | gain | uncertified / certified | yes | yes | yes |
| (4, 27) | miss | certified / uncertified | yes | yes | yes |
| (7, 30) | gain | uncertified / certified | yes | yes | yes |
| (8, 30) | gain | uncertified / certified | yes | yes | yes |
| (11, 27) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy7-c04`

Cell bbox (1936, 0, 2304, 752), crop sha `ab789e3a64ce…`. Crop certificates: holo1 51, holo3 45 (GT-checked: holo1 51, holo3 45).

- **holo1**: ran, exit 2, wall 965.4 s (decoded 2026-08-30 16:49:31, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 349.7 s (decoded 2026-08-30 17:05:36, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 39/39 reproduced, 0 flipped; holo3: 39/39 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 13/13 | 13/13 |
| 64-127 | 19/19 | 19/19 |
| 128-191 | 7/7 | 7/7 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (3, 35) | miss | certified / uncertified | no | no | yes |
| (4, 34) | miss | certified / uncertified | yes | yes | yes |
| (7, 35) | miss | certified / uncertified | no | no | yes |

### case `xerox-c2-cmy7-c05`

Cell bbox (0, 464, 496, 1200), crop sha `22e04dfbfa5c…`. Crop certificates: holo1 83, holo3 73 (GT-checked: holo1 83, holo3 73).

- **holo1**: ran, exit 2, wall 1188.2 s (decoded 2026-08-30 17:11:27, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 198.9 s (decoded 2026-08-30 17:31:15, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 41/41 reproduced, 0 flipped; holo3: 40/41 reproduced, 1 flipped ((12, 2))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 17/17 | 17/17 |
| 64-127 | 13/13 | 13/13 |
| 128-191 | 10/10 | 9/10 |
| 192-255 | 1/1 | 1/1 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (11, 3) | miss | certified / uncertified | yes | yes | yes |
| (14, 2) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy7-c06`

Cell bbox (784, 784, 1584, 1584), crop sha `800fa27c4692…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 686.2 s (decoded 2026-08-30 17:34:34, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 188.1 s (decoded 2026-08-30 17:46:01, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 0/114 reproduced, 114 flipped ((13, 13), (13, 14), (13, 15), (13, 16), (13, 17), (13, 18), (13, 19), (13, 20), (13, 21), (13, 22), (13, 23), (14, 13)); holo3: 0/114 reproduced, 114 flipped ((13, 13), (13, 14), (13, 15), (13, 16), (13, 17), (13, 18), (13, 19), (13, 20), (13, 21), (13, 22), (13, 23), (14, 13))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/39 | 0/39 |
| 64-127 | 0/31 | 0/31 |
| 128-191 | 0/24 | 0/24 |
| 192-255 | 0/12 | 0/12 |
| 256-319 | 0/7 | 0/7 |
| 320-383 | 0/1 | 0/1 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (16, 20) | gain | uncertified / certified | no | no | yes |
| (19, 17) | miss | certified / uncertified | no | no | yes |
| (19, 20) | gain | uncertified / certified | no | no | yes |
| (20, 16) | miss | certified / uncertified | no | no | yes |

### case `xerox-c2-cmy7-c07`

Cell bbox (1488, 976, 2224, 1584), crop sha `752dbc8f1920…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 536.5 s (decoded 2026-08-30 17:49:09, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 129.0 s (decoded 2026-08-30 17:58:06, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 0/71 reproduced, 71 flipped ((16, 24), (16, 25), (16, 26), (16, 27), (16, 28), (16, 29), (16, 31), (16, 32), (16, 33), (17, 24), (17, 25), (17, 26)); holo3: 0/71 reproduced, 71 flipped ((16, 24), (16, 25), (16, 26), (16, 27), (16, 28), (16, 29), (16, 31), (16, 32), (16, 33), (17, 24), (17, 25), (17, 26))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/29 | 0/29 |
| 64-127 | 0/22 | 0/22 |
| 128-191 | 0/15 | 0/15 |
| 192-255 | 0/5 | 0/5 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (19, 27) | miss | certified / uncertified | no | no | yes |
| (20, 30) | miss | certified / uncertified | no | no | yes |

### case `xerox-c2-cmy7-c08`

Cell bbox (1872, 1104, 2304, 1840), crop sha `d4017fc1390e…`. Crop certificates: holo1 59, holo3 59 (GT-checked: holo1 59, holo3 59).

- **holo1**: ran, exit 2, wall 1060.0 s (decoded 2026-08-30 18:00:15, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 166.9 s (decoded 2026-08-30 18:17:55, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 32/33 reproduced, 1 flipped ((24, 34)); holo3: 32/33 reproduced, 1 flipped ((24, 34))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 12/12 | 12/12 |
| 64-127 | 11/12 | 11/12 |
| 128-191 | 9/9 | 9/9 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (21, 34) | gain | uncertified / certified | no | no | yes |
| (24, 33) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy7-c09`

Cell bbox (0, 1168, 496, 1712), crop sha `7d370324a382…`. Crop certificates: holo1 62, holo3 53 (GT-checked: holo1 62, holo3 53).

- **holo1**: ran, exit 2, wall 732.6 s (decoded 2026-08-30 18:20:42, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 156.7 s (decoded 2026-08-30 18:32:55, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 25/25 reproduced, 0 flipped; holo3: 25/25 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 12/12 | 12/12 |
| 64-127 | 9/9 | 9/9 |
| 128-191 | 4/4 | 4/4 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (22, 3) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy7-c10`

Cell bbox (784, 1360, 1392, 2032), crop sha `165692aba0d4…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 272.5 s (decoded 2026-08-30 18:35:32, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 58.6 s (decoded 2026-08-30 18:40:05, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 0/59 reproduced, 59 flipped ((22, 13), (22, 14), (22, 15), (22, 16), (22, 18), (22, 19), (22, 20), (23, 13), (23, 14), (23, 15), (23, 16), (23, 18)); holo3: 0/59 reproduced, 59 flipped ((22, 13), (22, 14), (22, 15), (22, 16), (22, 18), (22, 19), (22, 20), (23, 13), (23, 14), (23, 15), (23, 16), (23, 18))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/27 | 0/27 |
| 64-127 | 0/19 | 0/19 |
| 128-191 | 0/11 | 0/11 |
| 192-255 | 0/2 | 0/2 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (25, 16) | gain | uncertified / certified | no | no | yes |
| (27, 17) | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy7-c11`

Cell bbox (0, 1552, 496, 2672), crop sha `158c8c5aa901…`. Crop certificates: holo1 126, holo3 111 (GT-checked: holo1 126, holo3 111).

- **holo1**: ran, exit 2, wall 1307.4 s (decoded 2026-08-30 18:41:04, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 523.9 s (decoded 2026-08-30 19:02:51, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 59/59 reproduced, 0 flipped; holo3: 59/59 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 23/23 | 23/23 |
| 64-127 | 18/18 | 18/18 |
| 128-191 | 17/17 | 17/17 |
| 192-255 | 1/1 | 1/1 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (28, 2) | miss | certified / uncertified | yes | yes | yes |
| (31, 2) | gain | uncertified / certified | yes | yes | yes |
| (32, 2) | gain | uncertified / certified | yes | yes | yes |
| (34, 3) | miss | certified / uncertified | yes | yes | yes |
| (35, 2) | gain | uncertified / certified | yes | yes | yes |
| (36, 3) | miss | certified / uncertified | yes | yes | yes |
| (37, 3) | miss | certified / uncertified | yes | yes | yes |

### case `xerox-c2-cmy7-c12`

Cell bbox (1936, 1552, 2304, 2288), crop sha `e45dc91635d8…`. Crop certificates: holo1 42, holo3 44 (GT-checked: holo1 42, holo3 44).

- **holo1**: ran, exit 2, wall 908.6 s (decoded 2026-08-30 19:11:35, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 150.0 s (decoded 2026-08-30 19:26:44, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 25/29 reproduced, 4 flipped ((28, 33), (29, 33), (30, 33), (30, 34)); holo3: 25/29 reproduced, 4 flipped ((28, 33), (29, 33), (30, 33), (30, 34))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 13/13 | 13/13 |
| 64-127 | 9/10 | 9/10 |
| 128-191 | 3/6 | 3/6 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (28, 34) | miss | certified / uncertified | no | no | yes |
| (31, 34) | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy7-c13`

Cell bbox (1680, 1744, 2224, 2288), crop sha `17abcc6ee51d…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 425.6 s (decoded 2026-08-30 19:29:14, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 95.7 s (decoded 2026-08-30 19:36:20, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 0/47 reproduced, 47 flipped ((28, 27), (28, 28), (28, 29), (28, 30), (28, 31), (28, 32), (28, 33), (29, 27), (29, 28), (29, 29), (29, 31), (29, 32)); holo3: 0/47 reproduced, 47 flipped ((28, 27), (28, 28), (28, 29), (28, 30), (28, 31), (28, 32), (28, 33), (29, 27), (29, 28), (29, 29), (29, 31), (29, 32))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/24 | 0/24 |
| 64-127 | 0/15 | 0/15 |
| 128-191 | 0/8 | 0/8 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (31, 30) | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy7-c14`

Cell bbox (848, 2128, 1392, 2864), crop sha `4acd85b97fd3…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 575.5 s (decoded 2026-08-30 19:37:56, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 123.7 s (decoded 2026-08-30 19:47:32, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 0/63 reproduced, 63 flipped ((34, 14), (34, 15), (34, 16), (34, 18), (34, 19), (34, 20), (35, 14), (35, 15), (35, 16), (35, 17), (35, 18), (35, 19)); holo3: 0/63 reproduced, 63 flipped ((34, 14), (34, 15), (34, 16), (34, 18), (34, 19), (34, 20), (35, 14), (35, 15), (35, 16), (35, 17), (35, 18), (35, 19))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/29 | 0/29 |
| 64-127 | 0/22 | 0/22 |
| 128-191 | 0/12 | 0/12 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (37, 17) | gain | uncertified / certified | no | no | yes |
| (40, 17) | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy7-c15`

Cell bbox (0, 2576, 432, 3120), crop sha `3db3064164ff…`. Crop certificates: holo1 45, holo3 46 (GT-checked: holo1 45, holo3 46).

- **holo1**: ran, exit 2, wall 768.0 s (decoded 2026-08-30 19:49:36, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 149.4 s (decoded 2026-08-30 20:02:24, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 27/27 reproduced, 0 flipped; holo3: 27/27 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 13/13 | 13/13 |
| 64-127 | 9/9 | 9/9 |
| 128-191 | 5/5 | 5/5 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (44, 2) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy7-c16`

Cell bbox (1488, 2640, 2224, 3328), crop sha `2699b145b196…`. Crop certificates: holo1 116, holo3 111 (GT-checked: holo1 116, holo3 111).

- **holo1**: ran, exit 2, wall 948.4 s (decoded 2026-08-30 20:04:54, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 177.9 s (decoded 2026-08-30 20:20:42, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 82/82 reproduced, 0 flipped; holo3: 82/82 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 26/26 | 26/26 |
| 64-127 | 26/26 | 26/26 |
| 128-191 | 18/18 | 18/18 |
| 192-255 | 8/8 | 8/8 |
| 256-319 | 4/4 | 4/4 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (45, 28) | miss | certified / uncertified | yes | yes | yes |
| (45, 30) | miss | certified / uncertified | yes | yes | yes |
| (46, 27) | miss | certified / uncertified | yes | yes | yes |
| (49, 30) | gain | uncertified / certified | yes | yes | yes |
| (50, 27) | gain | uncertified / certified | yes | yes | yes |
| (50, 30) | gain | uncertified / certified | no | yes | no |
| (51, 27) | gain | uncertified / certified | no | no | yes |
| (51, 28) | gain | uncertified / certified | yes | no | no |
| (51, 30) | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy7-c17`

Cell bbox (1936, 2704, 2304, 3248), crop sha `d6466bf4adb8…`. Crop certificates: holo1 28, holo3 31 (GT-checked: holo1 28, holo3 31).

- **holo1**: ran, exit 2, wall 1233.2 s (decoded 2026-08-30 20:23:40, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 200.1 s (decoded 2026-08-30 20:44:14, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 21/22 reproduced, 1 flipped ((49, 34)); holo3: 21/22 reproduced, 1 flipped ((49, 34))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 11/12 | 11/12 |
| 64-127 | 7/7 | 7/7 |
| 128-191 | 3/3 | 3/3 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (46, 34) | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy7-c18`

Cell bbox (848, 2768, 1392, 3312), crop sha `067564367167…`. Crop certificates: holo1 73, holo3 72 (GT-checked: holo1 73, holo3 72).

- **holo1**: ran, exit 2, wall 966.8 s (decoded 2026-08-30 20:47:34, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 160.6 s (decoded 2026-08-30 21:03:42, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 39/39 reproduced, 0 flipped; holo3: 39/39 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 22/22 | 22/22 |
| 64-127 | 14/14 | 14/14 |
| 128-191 | 3/3 | 3/3 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (47, 17) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy7-c19`

Cell bbox (0, 2896, 432, 3328), crop sha `ad7b188d5d3e…`. Crop certificates: holo1 34, holo3 31 (GT-checked: holo1 34, holo3 31).

- **holo1**: ran, exit 2, wall 809.0 s (decoded 2026-08-30 21:06:23, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 145.3 s (decoded 2026-08-30 21:19:52, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 19/19 reproduced, 0 flipped; holo3: 19/19 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 8/8 | 8/8 |
| 64-127 | 8/8 | 8/8 |
| 128-191 | 3/3 | 3/3 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (49, 2) | gain | uncertified / certified | yes | yes | yes |
| (50, 1) | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy7-c20`

Cell bbox (208, 2960, 752, 3328), crop sha `29f7323c942a…`. Crop certificates: holo1 46, holo3 45 (GT-checked: holo1 46, holo3 45).

- **holo1**: ran, exit 2, wall 456.3 s (decoded 2026-08-30 21:22:18, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 87.5 s (decoded 2026-08-30 21:29:54, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 25/27 reproduced, 2 flipped ((49, 10), (50, 10)); holo3: 27/27 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 11/13 | 13/13 |
| 64-127 | 11/11 | 11/11 |
| 128-191 | 3/3 | 3/3 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (50, 7) | miss | certified / uncertified | yes | yes | yes |
| (51, 7) | miss | certified / uncertified | no | no | yes |

## Battery totals

- runs executed this invocation: 40 (holo1 16625.6 s, holo3 3773.6 s wall)
- runs adopted from sidecars: 0 (0.0 s recorded wall, marked * above)
- wrong certificates: 0; out-of-bbox certificates: 0

**Colour caveat.** A crop changes the context a colour calibration head pools over, so this battery SCREENS the gap rather than settling it: a crop verdict that disagrees with the full-sheet record here is evidence about the crop first, and about the receiver only after a full-sheet confirmation.
