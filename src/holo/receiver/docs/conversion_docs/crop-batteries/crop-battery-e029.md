# Crop battery — e029 (e029 HP K (c2-r0700))

Manifest `<checkout>/scratch/crop-parity/e029/cases.json`, format `L:c2-r0700@3392x2368`, classes miss, gain, generated 2026-08-30 04:29:19. holo1 tree `3537128d0084`, holo3 tree `e7ad566755e5`.

Full-sheet record (`post-2`): holo1 1940, holo3 1938, both 1938 — miss 2, gain 0, neither 21.

Ground truth: golden payload `e5021f8d0995…` re-encoded through holo1 generation and validated against 1940 certificates of the archived holo1 state (every certificate in the archived holo1 state matches the re-encoded golden payload exactly).

## WRONG CERTIFICATES (expected: none)

None — every crop-minted certificate whose bits could be read matches the re-encoded golden payload.

## Address-frame check

Every crop certificate on both sides addresses a tile inside its case's cell rectangle: the printed address word carries the absolute tile counter, so a crop decodes into the FULL-SHEET frame with no origin shift applied.

## Per-class outcomes vs the full-sheet record

Counts over TARGET addresses compared this battery (a side counts only where its crop decode was available). `reproduces` = the crop verdict equals the recorded full-sheet verdict for that side — the expectation, not a bar.

| class | targets | crop holo1 cert | reproduces | crop holo3 cert | reproduces |
|---|---:|---:|---:|---:|---:|
| miss | 2 | 1/2 | 1/2 | 1/2 | 1/2 |

## Agreement on targets

- both sides give the same crop verdict: 2
- the two sides disagree on the crop: 0
- undetermined (a side unavailable): 0

## Cases

### case `e029-c01`

Cell bbox (528, 2448, 1264, 2992), crop sha `d0ac94e8c33f…`. Crop certificates: holo1 40, holo3 40 (GT-checked: holo1 40, holo3 40).

- **holo1**: adopted, exit 2, wall 421.2 s* (decoded 2026-08-29 21:42:49, receiver tree `3537128d0084`)
- **holo3**: ran, exit 0, wall 80.6 s (decoded 2026-08-30 04:27:58, receiver tree `e7ad566755e5`)
- controls (reported, never gated): holo1: 32/66 reproduced, 34 flipped ((39, 9), (39, 10), (39, 11), (40, 9), (40, 10), (40, 11), (40, 12), (40, 16), (41, 9), (41, 11), (41, 12), (41, 13)); holo3: 32/66 reproduced, 34 flipped ((39, 9), (39, 10), (39, 11), (40, 9), (40, 10), (40, 11), (40, 12), (41, 9), (41, 10), (41, 11), (41, 13), (41, 14))

| controls by depth inside the crop (cells) | holo1 reproduced | holo3 reproduced |
|---|---:|---:|
| 0-63 | 14/30 | 14/30 |
| 64-127 | 10/21 | 10/21 |
| 128-191 | 6/13 | 6/13 |
| 192-255 | 2/2 | 2/2 |

| target | class | full-sheet holo1 / holo3 | crop holo1 | crop holo3 | agree |
|---|---|---|---|---|---|
| (42, 12) | miss | certified / uncertified | no | no | yes |
| (42, 15) | miss | certified / uncertified | yes | yes | yes |

## Battery totals

- runs executed this invocation: 1 (holo1 0.0 s, holo3 80.6 s wall)
- runs adopted from sidecars: 1 (421.2 s recorded wall, marked * above)
- wrong certificates: 0; out-of-bbox certificates: 0
