# Crop battery — xerox-c3-cmy7 (xerox c3-cmy7)

Manifest `<checkout>/scratch/crop-parity/xerox-c3-cmy7/cases.json`, format `L:c3-cmy7-p120-v0@2240x1536`, classes miss, gain, generated 2026-08-30 15:51:09. holo1 tree `3537128d0084`, holo3 tree `a6f43747064e`.

Full-sheet record (`post-3`): holo1 720, holo3 815, both 720 — miss 0, gain 95, neither 25.

Ground truth: golden payload `4f68dbf93232…` re-encoded through holo1 generation and validated against 720 certificates of the archived holo1 state (every certificate in the archived holo1 state matches the re-encoded golden payload exactly).

## WRONG CERTIFICATES (expected: none)

None — every crop-minted certificate whose bits could be read matches the re-encoded golden payload.

## Address-frame check

Every crop certificate on both sides addresses a tile inside its case's cell rectangle: the printed address word carries the absolute tile counter, so a crop decodes into the FULL-SHEET frame with no origin shift applied.

## Per-class outcomes vs the full-sheet record

Counts over TARGET addresses compared this battery (a side counts only where its crop decode was available). `reproduces` = the crop verdict equals the recorded full-sheet verdict for that side — the expectation, not a bar.

| class | targets | crop holo1 cert | reproduces | crop holo3 cert | reproduces |
|---|---:|---:|---:|---:|---:|
| gain | 95 | 86/95 | 9/95 | 88/95 | 88/95 |

## Agreement on targets

- both sides give the same crop verdict: 91
- the two sides disagree on the crop: 4
- undetermined (a side unavailable): 0

## Cases

### case `xerox-c3-cmy7-c01`

Cell bbox (336, 0, 880, 496), crop sha `bd4faf0631ab…`. Crop certificates: holo1 72, holo3 72 (GT-checked: holo1 72, holo3 72).

- **holo1**: ran, exit 2, wall 205.8 s (decoded 2026-08-30 14:49:38, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 49.8 s (decoded 2026-08-30 14:53:04, receiver tree `a6f43747064e`)
- controls (reported, never gated): holo1: 41/41 reproduced, 0 flipped; holo3: 41/41 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 17/17 | 17/17 |
| 64-127 | 16/16 | 16/16 |
| 128-191 | 8/8 | 8/8 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (0, 9) | gain | uncertified / certified | yes | yes | yes |
| (3, 9) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c3-cmy7-c02`

Cell bbox (1040, 0, 1536, 1008), crop sha `37ff80a02aaf…`. Crop certificates: holo1 110, holo3 112 (GT-checked: holo1 110, holo3 112).

- **holo1**: ran, exit 2, wall 698.1 s (decoded 2026-08-30 14:53:54, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 126.2 s (decoded 2026-08-30 15:05:32, receiver tree `a6f43747064e`)
- controls (reported, never gated): holo1: 54/54 reproduced, 0 flipped; holo3: 54/54 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 17/17 | 17/17 |
| 64-127 | 19/19 | 19/19 |
| 128-191 | 13/13 | 13/13 |
| 192-255 | 5/5 | 5/5 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (0, 20) | gain | uncertified / certified | yes | yes | yes |
| (0, 21) | gain | uncertified / certified | yes | yes | yes |
| (0, 22) | gain | uncertified / certified | no | no | yes |
| (1, 22) | gain | uncertified / certified | no | no | yes |
| (3, 20) | gain | uncertified / certified | yes | yes | yes |
| (3, 21) | gain | uncertified / certified | yes | yes | yes |
| (4, 21) | gain | uncertified / certified | yes | yes | yes |
| (5, 21) | gain | uncertified / certified | yes | yes | yes |
| (5, 23) | gain | uncertified / certified | yes | yes | yes |
| (6, 21) | gain | uncertified / certified | yes | yes | yes |
| (7, 20) | gain | uncertified / certified | yes | yes | yes |
| (7, 22) | gain | uncertified / certified | yes | yes | yes |
| (8, 20) | gain | uncertified / certified | yes | yes | yes |
| (8, 22) | gain | uncertified / certified | yes | yes | yes |
| (9, 21) | gain | uncertified / certified | yes | yes | yes |
| (9, 22) | gain | uncertified / certified | yes | yes | yes |
| (10, 21) | gain | uncertified / certified | no | no | yes |
| (10, 23) | gain | uncertified / certified | no | no | yes |
| (11, 20) | gain | uncertified / certified | yes | yes | yes |
| (11, 21) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c3-cmy7-c03`

Cell bbox (0, 0, 304, 1008), crop sha `d33859731a44…`. Crop certificates: holo1 79, holo3 78 (GT-checked: holo1 79, holo3 78).

- **holo1**: ran, exit 2, wall 194.2 s (decoded 2026-08-30 15:07:38, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 54.5 s (decoded 2026-08-30 15:10:53, receiver tree `a6f43747064e`)
- controls (reported, never gated): holo1: 42/42 reproduced, 0 flipped; holo3: 42/42 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 16/16 | 16/16 |
| 64-127 | 26/26 | 26/26 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (1, 0) | gain | uncertified / certified | yes | yes | yes |
| (3, 0) | gain | uncertified / certified | yes | yes | yes |
| (4, 0) | gain | uncertified / certified | yes | yes | yes |
| (7, 0) | gain | uncertified / certified | yes | yes | yes |
| (8, 0) | gain | uncertified / certified | yes | yes | yes |
| (9, 0) | gain | uncertified / certified | yes | yes | yes |
| (11, 0) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c3-cmy7-c04`

Cell bbox (0, 528, 304, 1712), crop sha `14a7d359f5dc…`. Crop certificates: holo1 95, holo3 94 (GT-checked: holo1 95, holo3 94).

- **holo1**: ran, exit 2, wall 197.1 s (decoded 2026-08-30 15:11:47, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 63.4 s (decoded 2026-08-30 15:15:04, receiver tree `a6f43747064e`)
- controls (reported, never gated): holo1: 51/51 reproduced, 0 flipped; holo3: 51/51 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 21/21 | 21/21 |
| 64-127 | 30/30 | 30/30 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (12, 0) | gain | uncertified / certified | yes | yes | yes |
| (14, 0) | gain | uncertified / certified | yes | yes | yes |
| (16, 0) | gain | uncertified / certified | yes | yes | yes |
| (17, 0) | gain | uncertified / certified | yes | yes | yes |
| (18, 0) | gain | uncertified / certified | yes | yes | yes |
| (19, 0) | gain | uncertified / certified | yes | yes | yes |
| (22, 0) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c3-cmy7-c05`

Cell bbox (1040, 528, 1536, 1776), crop sha `931deb7b5e3b…`. Crop certificates: holo1 151, holo3 153 (GT-checked: holo1 151, holo3 153).

- **holo1**: ran, exit 2, wall 674.4 s (decoded 2026-08-30 15:16:08, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 139.9 s (decoded 2026-08-30 15:27:23, receiver tree `a6f43747064e`)
- controls (reported, never gated): holo1: 62/62 reproduced, 0 flipped; holo3: 62/62 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 25/25 | 25/25 |
| 64-127 | 19/19 | 19/19 |
| 128-191 | 16/16 | 16/16 |
| 192-255 | 2/2 | 2/2 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (12, 20) | gain | uncertified / certified | yes | yes | yes |
| (12, 21) | gain | uncertified / certified | yes | yes | yes |
| (12, 22) | gain | uncertified / certified | no | yes | no |
| (12, 23) | gain | uncertified / certified | no | yes | no |
| (13, 20) | gain | uncertified / certified | yes | yes | yes |
| (13, 21) | gain | uncertified / certified | yes | yes | yes |
| (13, 23) | gain | uncertified / certified | no | no | yes |
| (14, 21) | gain | uncertified / certified | yes | yes | yes |
| (14, 22) | gain | uncertified / certified | no | yes | no |
| (14, 23) | gain | uncertified / certified | yes | yes | yes |
| (15, 20) | gain | uncertified / certified | yes | yes | yes |
| (15, 21) | gain | uncertified / certified | yes | yes | yes |
| (15, 22) | gain | uncertified / certified | yes | yes | yes |
| (16, 20) | gain | uncertified / certified | yes | yes | yes |
| (16, 21) | gain | uncertified / certified | yes | yes | yes |
| (16, 22) | gain | uncertified / certified | yes | yes | yes |
| (17, 20) | gain | uncertified / certified | yes | yes | yes |
| (17, 21) | gain | uncertified / certified | yes | yes | yes |
| (17, 22) | gain | uncertified / certified | yes | yes | yes |
| (17, 23) | gain | uncertified / certified | yes | yes | yes |
| (18, 21) | gain | uncertified / certified | yes | yes | yes |
| (18, 22) | gain | uncertified / certified | yes | yes | yes |
| (18, 23) | gain | uncertified / certified | yes | yes | yes |
| (19, 20) | gain | uncertified / certified | yes | yes | yes |
| (19, 21) | gain | uncertified / certified | yes | yes | yes |
| (19, 23) | gain | uncertified / certified | yes | yes | yes |
| (20, 20) | gain | uncertified / certified | yes | yes | yes |
| (20, 22) | gain | uncertified / certified | yes | yes | yes |
| (20, 23) | gain | uncertified / certified | yes | yes | yes |
| (21, 20) | gain | uncertified / certified | yes | yes | yes |
| (21, 22) | gain | uncertified / certified | yes | yes | yes |
| (22, 20) | gain | uncertified / certified | yes | yes | yes |
| (22, 21) | gain | uncertified / certified | yes | yes | yes |
| (23, 21) | gain | uncertified / certified | yes | yes | yes |
| (23, 22) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c3-cmy7-c06`

Cell bbox (1040, 1296, 1536, 2240), crop sha `764c5df7e8b4…`. Crop certificates: holo1 116, holo3 113 (GT-checked: holo1 116, holo3 113).

- **holo1**: ran, exit 2, wall 480.7 s (decoded 2026-08-30 15:29:43, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 169.9 s (decoded 2026-08-30 15:37:43, receiver tree `a6f43747064e`)
- controls (reported, never gated): holo1: 48/48 reproduced, 0 flipped; holo3: 48/48 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 16/16 | 16/16 |
| 64-127 | 17/17 | 17/17 |
| 128-191 | 12/12 | 12/12 |
| 192-255 | 3/3 | 3/3 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (24, 20) | gain | uncertified / certified | yes | yes | yes |
| (24, 21) | gain | uncertified / certified | yes | yes | yes |
| (25, 20) | gain | uncertified / certified | yes | yes | yes |
| (25, 21) | gain | uncertified / certified | yes | yes | yes |
| (25, 22) | gain | uncertified / certified | yes | yes | yes |
| (26, 22) | gain | uncertified / certified | yes | yes | yes |
| (27, 21) | gain | uncertified / certified | yes | yes | yes |
| (28, 21) | gain | uncertified / certified | yes | yes | yes |
| (28, 22) | gain | uncertified / certified | yes | yes | yes |
| (29, 20) | gain | uncertified / certified | yes | yes | yes |
| (29, 21) | gain | uncertified / certified | yes | yes | yes |
| (30, 21) | gain | uncertified / certified | yes | yes | yes |
| (30, 22) | gain | uncertified / certified | yes | yes | yes |
| (31, 21) | gain | uncertified / certified | yes | yes | yes |
| (31, 22) | gain | uncertified / certified | yes | yes | yes |
| (32, 21) | gain | uncertified / certified | yes | no | no |
| (32, 22) | gain | uncertified / certified | yes | yes | yes |
| (33, 22) | gain | uncertified / certified | yes | yes | yes |
| (34, 22) | gain | uncertified / certified | yes | yes | yes |
| (34, 23) | gain | uncertified / certified | no | no | yes |

### case `xerox-c3-cmy7-c07`

Cell bbox (336, 1808, 1008, 2240), crop sha `129f2f6ccf70…`. Crop certificates: holo1 76, holo3 77 (GT-checked: holo1 76, holo3 77).

- **holo1**: ran, exit 2, wall 365.7 s (decoded 2026-08-30 15:40:34, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 75.8 s (decoded 2026-08-30 15:46:39, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 43/43 reproduced, 0 flipped; holo3: 43/43 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 17/17 | 17/17 |
| 64-127 | 17/17 | 17/17 |
| 128-191 | 9/9 | 9/9 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (32, 9) | gain | uncertified / certified | yes | yes | yes |
| (33, 11) | gain | uncertified / certified | yes | yes | yes |
| (34, 11) | gain | uncertified / certified | yes | yes | yes |

### case `xerox-c3-cmy7-c08`

Cell bbox (0, 1936, 432, 2240), crop sha `277eb27e5b05…`. Crop certificates: holo1 34, holo3 34 (GT-checked: holo1 34, holo3 34).

- **holo1**: ran, exit 2, wall 162.2 s (decoded 2026-08-30 15:47:55, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 31.4 s (decoded 2026-08-30 15:50:38, receiver tree `f5d7c0e2efc8`)
- controls (reported, never gated): holo1: 15/15 reproduced, 0 flipped; holo3: 15/15 reproduced, 0 flipped

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 7/7 | 7/7 |
| 64-127 | 8/8 | 8/8 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (34, 2) | gain | uncertified / certified | yes | yes | yes |

## Battery totals

- runs executed this invocation: 16 (holo1 2978.3 s, holo3 710.8 s wall)
- runs adopted from sidecars: 0 (0.0 s recorded wall, marked * above)
- wrong certificates: 0; out-of-bbox certificates: 0

**Colour caveat.** A crop changes the context a colour calibration head pools over, so this battery SCREENS the gap rather than settling it: a crop verdict that disagrees with the full-sheet record here is evidence about the crop first, and about the receiver only after a full-sheet confirmation.
