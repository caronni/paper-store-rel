# Crop battery — xerox-c2-cmy8 (xerox c2-cmy8)

Manifest `<checkout>/scratch/crop-parity/xerox-c2-cmy8/cases.json`, format `L:c2-cmy8-p120-v0@3328x2304`, classes miss, gain, generated 2026-08-31 00:23:08. holo1 tree `3537128d0084`, holo3 tree `f5d7c0e2efc8`.

Full-sheet record (`run-4`): holo1 5370, holo3 5422, both 5334 — miss 36, gain 88, neither 158.

Ground truth: golden payload `f13c34db6c96…` re-encoded through holo1 generation and validated against 5370 certificates of the archived holo1 state (every certificate in the archived holo1 state matches the re-encoded golden payload exactly).

## WRONG CERTIFICATES (expected: none)

None — every crop-minted certificate whose bits could be read matches the re-encoded golden payload.

## Address-frame check

Every crop certificate on both sides addresses a tile inside its case's cell rectangle: the printed address word carries the absolute tile counter, so a crop decodes into the FULL-SHEET frame with no origin shift applied.

## Per-class outcomes vs the full-sheet record

Counts over TARGET addresses compared this battery (a side counts only where its crop decode was available). `reproduces` = the crop verdict equals the recorded full-sheet verdict for that side — the expectation, not a bar.

| class | targets | crop holo1 cert | reproduces | crop holo3 cert | reproduces |
|---|---:|---:|---:|---:|---:|
| gain | 88 | 74/88 | 14/88 | 55/88 | 55/88 |
| miss | 36 | 20/36 | 20/36 | 19/36 | 17/36 |

## Agreement on targets

- both sides give the same crop verdict: 102
- the two sides disagree on the crop: 22
- undetermined (a side unavailable): 0

## Cases

### case `xerox-c2-cmy8-c01`

Cell bbox (0, 0, 752, 1008), crop sha `24bf9d6930b0…`. Crop certificates: holo1 554, holo3 546 (GT-checked: holo1 554, holo3 546).

- **holo1**: ran, exit 2, wall 627.3 s (decoded 2026-08-30 21:31:29, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 393.3 s (decoded 2026-08-30 21:41:57, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 355/358 reproduced, 3 flipped ((3, 3)/Y, (3, 6)/C, (3, 6)/Y); holo3: 353/358 reproduced, 5 flipped ((1, 6)/C, (3, 6)/C, (3, 6)/Y, (10, 5)/C, (10, 6)/C)

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 68/68 | 68/68 |
| 64-127 | 113/113 | 112/113 |
| 128-191 | 85/85 | 85/85 |
| 192-255 | 43/46 | 44/46 |
| 256-319 | 40/40 | 38/40 |
| 320-383 | 6/6 | 6/6 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (0, 2)/C | gain | uncertified / certified | yes | no | no |
| (0, 5)/M | gain | uncertified / certified | yes | yes | yes |
| (1, 3)/Y | miss | certified / uncertified | no | no | yes |
| (2, 5)/C | gain | uncertified / certified | yes | yes | yes |
| (2, 6)/C | miss | certified / uncertified | no | no | yes |
| (3, 5)/C | gain | uncertified / certified | yes | yes | yes |
| (3, 5)/Y | gain | uncertified / certified | yes | yes | yes |
| (4, 3)/C | miss | certified / uncertified | yes | yes | yes |
| (5, 5)/Y | gain | uncertified / certified | yes | yes | yes |
| (5, 6)/C | gain | uncertified / certified | yes | yes | yes |
| (6, 5)/C | miss | certified / uncertified | yes | yes | yes |
| (6, 5)/Y | gain | uncertified / certified | yes | yes | yes |
| (7, 0)/Y | miss | certified / uncertified | yes | yes | yes |
| (7, 5)/Y | gain | uncertified / certified | yes | yes | yes |
| (8, 0)/Y | gain | uncertified / certified | yes | yes | yes |
| (9, 7)/Y | miss | certified / uncertified | yes | yes | yes |
| (10, 4)/C | gain | uncertified / certified | yes | yes | yes |
| (11, 6)/Y | miss | certified / uncertified | yes | yes | yes |

### case `xerox-c2-cmy8-c02`

Cell bbox (912, 0, 1904, 752), crop sha `16ee8d1ded90…`. Crop certificates: holo1 553, holo3 559 (GT-checked: holo1 553, holo3 559).

- **holo1**: ran, exit 2, wall 829.3 s (decoded 2026-08-30 21:48:31, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 342.9 s (decoded 2026-08-30 22:02:20, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 369/376 reproduced, 7 flipped ((1, 22)/Y, (3, 23)/Y, (4, 24)/C, (4, 24)/M, (5, 22)/Y, (6, 22)/Y, (8, 23)/M); holo3: 372/376 reproduced, 4 flipped ((3, 22)/C, (3, 22)/Y, (3, 23)/Y, (8, 23)/M)

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 93/93 | 93/93 |
| 64-127 | 101/102 | 102/102 |
| 128-191 | 84/85 | 84/85 |
| 192-255 | 57/58 | 55/58 |
| 256-319 | 26/29 | 29/29 |
| 320-383 | 8/9 | 9/9 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (0, 19)/Y | gain | uncertified / certified | yes | yes | yes |
| (0, 20)/C | miss | certified / uncertified | yes | yes | yes |
| (0, 21)/C | gain | uncertified / certified | yes | yes | yes |
| (0, 22)/C | miss | certified / uncertified | no | no | yes |
| (0, 23)/M | gain | uncertified / certified | no | no | yes |
| (0, 24)/Y | miss | certified / uncertified | no | yes | no |
| (0, 25)/Y | miss | certified / uncertified | yes | yes | yes |
| (1, 18)/Y | miss | certified / uncertified | yes | yes | yes |
| (1, 23)/Y | miss | certified / uncertified | yes | yes | yes |
| (2, 22)/C | gain | uncertified / certified | yes | no | no |
| (4, 20)/M | gain | uncertified / certified | yes | yes | yes |
| (4, 22)/C | miss | certified / uncertified | yes | yes | yes |
| (4, 23)/C | miss | certified / uncertified | no | no | yes |
| (4, 25)/M | gain | uncertified / certified | yes | yes | yes |
| (5, 23)/C | miss | certified / uncertified | no | no | yes |
| (6, 20)/M | gain | uncertified / certified | yes | yes | yes |
| (7, 25)/M | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c03`

Cell bbox (1040, 336, 1776, 1328), crop sha `7adbad2a79ed…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 468.5 s (decoded 2026-08-30 22:08:04, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 203.1 s (decoded 2026-08-30 22:15:52, receiver tree `0e84cab4966c`)
- controls (reported, never gated): holo1: 0/380 reproduced, 380 flipped ((6, 17)/C, (6, 17)/M, (6, 17)/Y, (6, 18)/C, (6, 18)/M, (6, 18)/Y, (6, 19)/C, (6, 19)/M, (6, 19)/Y, (6, 21)/C, (6, 21)/M, (6, 21)/Y); holo3: 0/380 reproduced, 380 flipped ((6, 17)/C, (6, 17)/M, (6, 17)/Y, (6, 18)/C, (6, 18)/M, (6, 18)/Y, (6, 19)/C, (6, 19)/M, (6, 19)/Y, (6, 21)/C, (6, 21)/M, (6, 21)/Y)

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/127 | 0/127 |
| 64-127 | 0/101 | 0/101 |
| 128-191 | 0/80 | 0/80 |
| 192-255 | 0/36 | 0/36 |
| 256-319 | 0/36 | 0/36 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (9, 20)/Y | gain | uncertified / certified | no | no | yes |
| (9, 23)/C | miss | certified / uncertified | no | no | yes |
| (10, 23)/C | miss | certified / uncertified | no | no | yes |
| (13, 23)/Y | miss | certified / uncertified | no | no | yes |
| (14, 23)/C | miss | certified / uncertified | no | no | yes |
| (15, 20)/M | gain | uncertified / certified | no | no | yes |
| (16, 23)/M | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy8-c04`

Cell bbox (0, 592, 304, 1136), crop sha `45e5b5f675f6…`. Crop certificates: holo1 132, holo3 133 (GT-checked: holo1 132, holo3 133).

- **holo1**: ran, exit 2, wall 258.0 s (decoded 2026-08-30 22:19:16, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 95.0 s (decoded 2026-08-30 22:23:34, receiver tree `31d4e8727cc0`)
- controls (reported, never gated): holo1: 61/61 reproduced, 0 flipped; holo3: 61/61 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 31/31 | 31/31 |
| 64-127 | 30/30 | 30/30 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (13, 0)/Y | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c05`

Cell bbox (1872, 592, 2304, 1328), crop sha `8bca8eefb0d3…`. Crop certificates: holo1 252, holo3 252 (GT-checked: holo1 252, holo3 252).

- **holo1**: ran, exit 2, wall 365.7 s (decoded 2026-08-30 22:25:10, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 146.7 s (decoded 2026-08-30 22:31:15, receiver tree `31d4e8727cc0`)
- controls (reported, never gated): holo1: 141/141 reproduced, 0 flipped; holo3: 141/141 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 53/53 | 53/53 |
| 64-127 | 59/59 | 59/59 |
| 128-191 | 29/29 | 29/29 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (13, 33)/Y | gain | uncertified / certified | yes | yes | yes |
| (16, 33)/Y | miss | certified / uncertified | yes | yes | yes |
| (16, 35)/C | miss | certified / uncertified | yes | yes | yes |

### case `xerox-c2-cmy8-c06`

Cell bbox (0, 848, 752, 1520), crop sha `f8bc279ceca0…`. Crop certificates: holo1 389, holo3 395 (GT-checked: holo1 389, holo3 395).

- **holo1**: ran, exit 2, wall 457.1 s (decoded 2026-08-30 22:33:42, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 282.3 s (decoded 2026-08-30 22:41:20, receiver tree `31d4e8727cc0`, dirty)
- controls (reported, never gated): holo1: 247/247 reproduced, 0 flipped; holo3: 247/247 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 79/79 | 79/79 |
| 64-127 | 81/81 | 81/81 |
| 128-191 | 58/58 | 58/58 |
| 192-255 | 20/20 | 20/20 |
| 256-319 | 9/9 | 9/9 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (17, 7)/Y | gain | uncertified / certified | yes | yes | yes |
| (18, 7)/Y | gain | uncertified / certified | yes | yes | yes |
| (19, 3)/C | gain | uncertified / certified | yes | yes | yes |
| (19, 4)/C | gain | uncertified / certified | yes | yes | yes |
| (19, 4)/Y | gain | uncertified / certified | yes | yes | yes |
| (19, 5)/C | gain | uncertified / certified | yes | yes | yes |
| (19, 5)/Y | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c07`

Cell bbox (1040, 848, 1776, 1840), crop sha `9f5d701d29ba…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 665.1 s (decoded 2026-08-30 22:46:02, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 254.6 s (decoded 2026-08-30 22:57:08, receiver tree `1f1dd1a641f8`)
- controls (reported, never gated): holo1: 0/376 reproduced, 376 flipped ((14, 17)/C, (14, 17)/M, (14, 17)/Y, (14, 18)/C, (14, 18)/M, (14, 18)/Y, (14, 19)/C, (14, 19)/M, (14, 19)/Y, (14, 20)/C, (14, 20)/M, (14, 20)/Y); holo3: 0/376 reproduced, 376 flipped ((14, 17)/C, (14, 17)/M, (14, 17)/Y, (14, 18)/C, (14, 18)/M, (14, 18)/Y, (14, 19)/C, (14, 19)/M, (14, 19)/Y, (14, 20)/C, (14, 20)/M, (14, 20)/Y)

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/127 | 0/127 |
| 64-127 | 0/103 | 0/103 |
| 128-191 | 0/80 | 0/80 |
| 192-255 | 0/33 | 0/33 |
| 256-319 | 0/33 | 0/33 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (17, 23)/C | miss | certified / uncertified | no | no | yes |
| (17, 23)/Y | miss | certified / uncertified | no | no | yes |
| (18, 23)/C | miss | certified / uncertified | no | no | yes |
| (20, 20)/M | gain | uncertified / certified | no | no | yes |
| (20, 22)/M | gain | uncertified / certified | no | no | yes |
| (21, 20)/M | gain | uncertified / certified | no | no | yes |
| (23, 20)/M | gain | uncertified / certified | no | no | yes |
| (23, 23)/M | gain | uncertified / certified | no | no | yes |
| (24, 20)/M | gain | uncertified / certified | no | no | yes |

### case `xerox-c2-cmy8-c08`

Cell bbox (0, 1232, 816, 2160), crop sha `1758c59a72d8…`. Crop certificates: holo1 571, holo3 0 (GT-checked: holo1 571, holo3 0).

- **holo1**: ran, exit 2, wall 780.4 s (decoded 2026-08-30 23:01:23, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 10.7 s (decoded 2026-08-30 23:14:23, receiver tree `1d1948e078ce`)
- controls (reported, never gated): holo1: 376/376 reproduced, 0 flipped; holo3: 0/376 reproduced, 376 flipped ((20, 1)/C, (20, 1)/M, (20, 1)/Y, (20, 2)/C, (20, 2)/M, (20, 2)/Y, (20, 3)/C, (20, 3)/M, (20, 3)/Y, (20, 4)/C, (20, 4)/M, (20, 4)/Y)

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 93/93 | 0/93 |
| 64-127 | 109/109 | 0/109 |
| 128-191 | 82/82 | 0/82 |
| 192-255 | 42/42 | 0/42 |
| 256-319 | 33/33 | 0/33 |
| 320-383 | 17/17 | 0/17 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (23, 0)/M | gain | uncertified / certified | yes | no | no |
| (23, 0)/Y | gain | uncertified / certified | yes | no | no |
| (23, 3)/C | gain | uncertified / certified | yes | no | no |
| (23, 5)/C | gain | uncertified / certified | yes | no | no |
| (24, 0)/C | gain | uncertified / certified | yes | no | no |
| (24, 0)/M | gain | uncertified / certified | yes | no | no |
| (24, 8)/Y | gain | uncertified / certified | yes | no | no |
| (25, 0)/M | gain | uncertified / certified | yes | no | no |
| (26, 0)/M | gain | uncertified / certified | yes | no | no |
| (27, 0)/C | gain | uncertified / certified | yes | no | no |
| (27, 0)/M | gain | uncertified / certified | yes | no | no |
| (27, 3)/Y | gain | uncertified / certified | yes | no | no |
| (28, 0)/Y | gain | uncertified / certified | yes | no | no |
| (28, 6)/Y | miss | certified / uncertified | yes | no | no |
| (28, 8)/Y | gain | uncertified / certified | yes | no | no |
| (29, 3)/C | gain | uncertified / certified | yes | no | no |
| (29, 6)/Y | miss | certified / uncertified | yes | no | no |

### case `xerox-c2-cmy8-c09`

Cell bbox (2000, 1488, 2304, 2096), crop sha `5e3b815d3ca6…`. Crop certificates: holo1 150, holo3 150 (GT-checked: holo1 150, holo3 150).

- **holo1**: ran, exit 2, wall 153.0 s (decoded 2026-08-30 23:14:34, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 42.6 s (decoded 2026-08-30 23:17:07, receiver tree `1d1948e078ce`)
- controls (reported, never gated): holo1: 72/72 reproduced, 0 flipped; holo3: 72/72 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 36/36 | 36/36 |
| 64-127 | 36/36 | 36/36 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (27, 35)/C | gain | uncertified / certified | yes | yes | yes |
| (28, 35)/Y | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c10`

Cell bbox (1168, 1552, 1776, 2352), crop sha `499ac5bf0771…`. Crop certificates: holo1 0, holo3 0 (GT-checked: holo1 0, holo3 0).

- **holo1**: ran, exit 2, wall 335.0 s (decoded 2026-08-30 23:17:50, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 95.4 s (decoded 2026-08-30 23:23:25, receiver tree `1d1948e078ce`)
- controls (reported, never gated): holo1: 0/237 reproduced, 237 flipped ((25, 19)/C, (25, 19)/M, (25, 19)/Y, (25, 20)/C, (25, 20)/M, (25, 20)/Y, (25, 21)/C, (25, 21)/M, (25, 21)/Y, (25, 22)/C, (25, 22)/M, (25, 22)/Y); holo3: 0/237 reproduced, 237 flipped ((25, 19)/C, (25, 19)/M, (25, 19)/Y, (25, 20)/C, (25, 20)/M, (25, 20)/Y, (25, 21)/C, (25, 21)/M, (25, 21)/Y, (25, 22)/C, (25, 22)/M, (25, 22)/Y)

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 0/100 | 0/100 |
| 64-127 | 0/74 | 0/74 |
| 128-191 | 0/51 | 0/51 |
| 192-255 | 0/12 | 0/12 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (28, 22)/C | miss | certified / uncertified | no | no | yes |
| (30, 22)/C | miss | certified / uncertified | no | no | yes |
| (30, 23)/C | gain | uncertified / certified | no | no | yes |
| (32, 23)/Y | miss | certified / uncertified | no | no | yes |

### case `xerox-c2-cmy8-c11`

Cell bbox (0, 1680, 816, 2544), crop sha `9a79e304bfe2…`. Crop certificates: holo1 527, holo3 529 (GT-checked: holo1 527, holo3 529).

- **holo1**: ran, exit 2, wall 812.7 s (decoded 2026-08-30 23:25:01, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 281.7 s (decoded 2026-08-30 23:38:34, receiver tree `b19ef0b3d7a9`)
- controls (reported, never gated): holo1: 327/332 reproduced, 5 flipped ((28, 5)/C, (29, 5)/C, (30, 4)/M, (30, 4)/Y, (31, 4)/Y); holo3: 331/332 reproduced, 1 flipped ((30, 4)/M)

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 89/89 | 89/89 |
| 64-127 | 98/99 | 99/99 |
| 128-191 | 73/74 | 74/74 |
| 192-255 | 35/37 | 36/37 |
| 256-319 | 22/23 | 23/23 |
| 320-383 | 10/10 | 10/10 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (30, 5)/Y | gain | uncertified / certified | yes | yes | yes |
| (30, 8)/Y | miss | certified / uncertified | yes | yes | yes |
| (31, 5)/M | gain | uncertified / certified | yes | yes | yes |
| (32, 3)/C | gain | uncertified / certified | yes | yes | yes |
| (33, 3)/C | gain | uncertified / certified | yes | yes | yes |
| (34, 0)/C | gain | uncertified / certified | yes | yes | yes |
| (34, 0)/M | gain | uncertified / certified | yes | yes | yes |
| (34, 0)/Y | gain | uncertified / certified | yes | yes | yes |
| (34, 3)/C | gain | uncertified / certified | yes | yes | yes |
| (34, 4)/C | gain | uncertified / certified | yes | yes | yes |
| (34, 5)/M | gain | uncertified / certified | yes | yes | yes |
| (34, 5)/Y | gain | uncertified / certified | yes | yes | yes |
| (35, 4)/Y | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c12`

Cell bbox (1872, 1808, 2304, 2800), crop sha `d51e1908435e…`. Crop certificates: holo1 331, holo3 327 (GT-checked: holo1 331, holo3 327).

- **holo1**: ran, exit 2, wall 402.6 s (decoded 2026-08-30 23:43:16, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 129.9 s (decoded 2026-08-30 23:49:59, receiver tree `b19ef0b3d7a9`)
- controls (reported, never gated): holo1: 204/204 reproduced, 0 flipped; holo3: 204/204 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 66/66 | 66/66 |
| 64-127 | 84/84 | 84/84 |
| 128-191 | 54/54 | 54/54 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (32, 33)/M | miss | certified / uncertified | yes | yes | yes |
| (32, 33)/Y | miss | certified / uncertified | yes | yes | yes |
| (33, 33)/M | miss | certified / uncertified | yes | yes | yes |
| (33, 33)/Y | miss | certified / uncertified | yes | yes | yes |
| (35, 35)/C | gain | uncertified / certified | yes | yes | yes |
| (35, 35)/M | gain | uncertified / certified | yes | yes | yes |
| (36, 35)/C | gain | uncertified / certified | no | no | yes |
| (36, 35)/M | gain | uncertified / certified | yes | no | no |
| (37, 35)/C | gain | uncertified / certified | no | no | yes |
| (37, 35)/M | gain | uncertified / certified | yes | no | no |
| (38, 35)/Y | gain | uncertified / certified | no | no | yes |
| (39, 35)/Y | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c13`

Cell bbox (1168, 2640, 1776, 3328), crop sha `b8260b39c650…`. Crop certificates: holo1 326, holo3 327 (GT-checked: holo1 326, holo3 327).

- **holo1**: ran, exit 2, wall 369.9 s (decoded 2026-08-30 23:52:09, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 123.7 s (decoded 2026-08-30 23:58:19, receiver tree `b19ef0b3d7a9`)
- controls (reported, never gated): holo1: 197/197 reproduced, 0 flipped; holo3: 197/197 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 71/71 | 71/71 |
| 64-127 | 70/70 | 70/70 |
| 128-191 | 41/41 | 41/41 |
| 192-255 | 15/15 | 15/15 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (45, 23)/C | gain | uncertified / certified | yes | yes | yes |
| (46, 22)/M | gain | uncertified / certified | yes | yes | yes |
| (46, 23)/C | gain | uncertified / certified | yes | yes | yes |
| (49, 22)/M | gain | uncertified / certified | yes | yes | yes |
| (49, 23)/C | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c14`

Cell bbox (16, 2832, 816, 3328), crop sha `64ba05eea400…`. Crop certificates: holo1 306, holo3 306 (GT-checked: holo1 306, holo3 306).

- **holo1**: ran, exit 2, wall 557.1 s (decoded 2026-08-31 00:00:23, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 121.6 s (decoded 2026-08-31 00:09:40, receiver tree `b19ef0b3d7a9`)
- controls (reported, never gated): holo1: 180/180 reproduced, 0 flipped; holo3: 180/180 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 62/62 | 62/62 |
| 64-127 | 70/70 | 70/70 |
| 128-191 | 37/37 | 37/37 |
| 192-255 | 11/11 | 11/11 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (48, 8)/Y | gain | uncertified / certified | yes | yes | yes |
| (49, 4)/C | gain | uncertified / certified | yes | yes | yes |
| (49, 5)/C | gain | uncertified / certified | yes | yes | yes |
| (49, 7)/Y | gain | uncertified / certified | yes | yes | yes |
| (51, 4)/M | gain | uncertified / certified | yes | yes | yes |
| (51, 5)/M | gain | uncertified / certified | yes | yes | yes |
| (51, 5)/Y | miss | certified / uncertified | yes | yes | yes |

### case `xerox-c2-cmy8-c15`

Cell bbox (656, 2960, 1200, 3328), crop sha `dc7d5493a7c4…`. Crop certificates: holo1 161, holo3 162 (GT-checked: holo1 161, holo3 162).

- **holo1**: ran, exit 2, wall 285.7 s (decoded 2026-08-31 00:11:42, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 88.3 s (decoded 2026-08-31 00:16:28, receiver tree `b19ef0b3d7a9`)
- controls (reported, never gated): holo1: 78/78 reproduced, 0 flipped; holo3: 78/78 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 39/39 | 39/39 |
| 64-127 | 31/31 | 31/31 |
| 128-191 | 8/8 | 8/8 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (50, 14)/C | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c2-cmy8-c16`

Cell bbox (1488, 2960, 2032, 3328), crop sha `94f7d8e1dbc7…`. Crop certificates: holo1 158, holo3 161 (GT-checked: holo1 158, holo3 161).

- **holo1**: ran, exit 2, wall 245.8 s (decoded 2026-08-31 00:17:57, receiver tree `b8ff63d85d48`)
- **holo3**: ran, exit 0, wall 65.9 s (decoded 2026-08-31 00:22:03, receiver tree `063e1c34de94`)
- controls (reported, never gated): holo1: 81/81 reproduced, 0 flipped; holo3: 81/81 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 39/39 | 39/39 |
| 64-127 | 33/33 | 33/33 |
| 128-191 | 9/9 | 9/9 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (50, 27)/C | gain | uncertified / certified | yes | yes | yes |

## Battery totals

- runs executed this invocation: 32 (holo1 7613.3 s, holo3 2677.9 s wall)
- runs adopted from sidecars: 0 (0.0 s recorded wall, marked * above)
- wrong certificates: 0; out-of-bbox certificates: 0

**Colour caveat.** A crop changes the context a colour calibration head pools over, so this battery SCREENS the gap rather than settling it: a crop verdict that disagrees with the full-sheet record here is evidence about the crop first, and about the receiver only after a full-sheet confirmation.
