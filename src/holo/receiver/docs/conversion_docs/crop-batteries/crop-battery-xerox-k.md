# Crop battery — xerox-k (xerox c2-k (c2-r0700))

Manifest `<checkout>/scratch/crop-parity/xerox-k/cases.json`, format `L:c2-r0700@3392x2368`, classes miss, gain, generated 2026-08-30 04:42:25. holo1 tree `3537128d0084`, holo3 tree `e7ad566755e5`.

Full-sheet record (`post-5`): holo1 1930, holo3 1927, both 1925 — miss 5, gain 2, neither 29.

Ground truth: golden payload `e5021f8d0995…` re-encoded through holo1 generation and validated against 1930 certificates of the archived holo1 state (every certificate in the archived holo1 state matches the re-encoded golden payload exactly).

## WRONG CERTIFICATES (expected: none)

None — every crop-minted certificate whose bits could be read matches the re-encoded golden payload.

## Address-frame check

Every crop certificate on both sides addresses a tile inside its case's cell rectangle: the printed address word carries the absolute tile counter, so a crop decodes into the FULL-SHEET frame with no origin shift applied.

## Per-class outcomes vs the full-sheet record

Counts over TARGET addresses compared this battery (a side counts only where its crop decode was available). `reproduces` = the crop verdict equals the recorded full-sheet verdict for that side — the expectation, not a bar.

| class | targets | crop holo1 cert | reproduces | crop holo3 cert | reproduces |
|---|---:|---:|---:|---:|---:|
| gain | 2 | 1/2 | 1/2 | 1/2 | 1/2 |
| miss | 5 | 0/5 | 0/5 | 0/5 | 5/5 |

## Agreement on targets

- both sides give the same crop verdict: 7
- the two sides disagree on the crop: 0
- undetermined (a side unavailable): 0

## Cases

### case `xerox-k-c01`

Cell bbox (0, 16, 304, 752), crop sha `bf6ceb1c642d…`. Crop certificates: holo1 55, holo3 51 (GT-checked: holo1 55, holo3 51).

- **holo1**: ran, exit 2, wall 116.4 s (decoded 2026-08-30 04:33:23, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 36.0 s (decoded 2026-08-30 04:35:20, receiver tree `e7ad566755e5`)
- controls (reported, never gated): holo1: 30/30 reproduced, 0 flipped; holo3: 30/30 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 14/14 | 14/14 |
| 64-127 | 16/16 | 16/16 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (4, 0) | gain | uncertified / certified | no | no | yes |
| (7, 0) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-k-c02`

Cell bbox (2064, 1296, 2368, 1840), crop sha `2785ac249679…`. Crop certificates: holo1 41, holo3 38 (GT-checked: holo1 41, holo3 38).

- **holo1**: ran, exit 2, wall 42.3 s (decoded 2026-08-30 04:35:56, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 24.6 s (decoded 2026-08-30 04:36:38, receiver tree `e7ad566755e5`)
- controls (reported, never gated): holo1: 19/21 reproduced, 2 flipped ((21, 34), (22, 34)); holo3: 18/21 reproduced, 3 flipped ((24, 34), (24, 35), (25, 34))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 10/11 | 11/11 |
| 64-127 | 9/10 | 7/10 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (24, 36) | miss | certified / uncertified | no | no | yes |

### case `xerox-k-c03`

Cell bbox (0, 1552, 304, 2096), crop sha `f22ae7540425…`. Crop certificates: holo1 38, holo3 30 (GT-checked: holo1 38, holo3 30).

- **holo1**: ran, exit 2, wall 79.1 s (decoded 2026-08-30 04:37:03, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 27.0 s (decoded 2026-08-30 04:38:22, receiver tree `e7ad566755e5`)
- controls (reported, never gated): holo1: 21/21 reproduced, 0 flipped; holo3: 16/21 reproduced, 5 flipped ((25, 1), (26, 1), (26, 2), (27, 2), (28, 2))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 11/11 | 10/11 |
| 64-127 | 10/10 | 6/10 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (28, 0) | miss | certified / uncertified | no | no | yes |

### case `xerox-k-c04`

Cell bbox (0, 1936, 304, 2480), crop sha `3152f7ccd6a5…`. Crop certificates: holo1 37, holo3 36 (GT-checked: holo1 37, holo3 36).

- **holo1**: ran, exit 2, wall 47.5 s (decoded 2026-08-30 04:38:49, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 23.1 s (decoded 2026-08-30 04:39:37, receiver tree `e7ad566755e5`)
- controls (reported, never gated): holo1: 21/21 reproduced, 0 flipped; holo3: 21/21 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 11/11 | 11/11 |
| 64-127 | 10/10 | 10/10 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (34, 0) | miss | certified / uncertified | no | no | yes |

### case `xerox-k-c05`

Cell bbox (0, 2832, 304, 3392), crop sha `7b06634cea89…`. Crop certificates: holo1 39, holo3 39 (GT-checked: holo1 39, holo3 39).

- **holo1**: ran, exit 2, wall 110.1 s (decoded 2026-08-30 04:40:00, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 34.6 s (decoded 2026-08-30 04:41:50, receiver tree `e7ad566755e5`)
- controls (reported, never gated): holo1: 21/21 reproduced, 0 flipped; holo3: 21/21 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 9/9 | 9/9 |
| 64-127 | 12/12 | 12/12 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (48, 0) | miss | certified / uncertified | no | no | yes |
| (49, 0) | miss | certified / uncertified | no | no | yes |

## Battery totals

- runs executed this invocation: 10 (holo1 395.4 s, holo3 145.4 s wall)
- runs adopted from sidecars: 0 (0.0 s recorded wall, marked * above)
- wrong certificates: 0; out-of-bbox certificates: 0
