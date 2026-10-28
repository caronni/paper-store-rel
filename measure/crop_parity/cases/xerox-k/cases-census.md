# Crop cases — xerox-k (xerox c2-k (c2-r0700))

Format `L:c2-r0700@3392x2368`, tile matrix 53x37, streams ['main'], 1 capture(s) at [4800.0] dpi. Generated in 2.8 s from tree `88a530c9b270`.

## The gap (recomputed, cross-checked against the record)

holo3 baseline harvest: `post-5` (9900 TileOutcome rows).

| set | addresses | recorded |
|---|---:|---:|
| holo1 certified | 1930 | — |
| holo3 certified | 1927 | — |
| both | 1925 | — |
| **miss** (holo1 only) | 5 | 5 |
| **gain** (holo3 only) | 2 | 2 |
| neither | 29 | — |

Ground truth: golden payload `e5021f8d0995…` (465580 B) re-encoded through holo1 generation, validated against 1930/1930 certificates in the archived holo1 state, zero mismatches.

## Captures and the cell→pixel fit

| # | capture id | shape (y, x) | ch | poses | px/cell | residual med / p99 / max px |
|---:|---|---|---:|---:|---:|---|
| 0 | `57a261454cc0…` | 56128x40832 | 1 | 1497 | 16.016 | 7.7 / 38.6 / 77.5 |

The pixel bbox is padded by 32 cells' worth of pixels on all sides before clipping, which is the margin the max residual has to fit inside.

## Cases (5) — classes miss, gain, halo 240 cells, merge-gap 2 tiles, max span 768 cells

| case | tiles | targets | controls | cell bbox (x0,y0,x1,y1) | crop px (y, x) | MB/crop |
|---|---:|---:|---:|---|---|---:|
| `xerox-k-c01` | 2 | 2 | 30 | (0, 16, 304, 752) | 12821x5910 | 75.8 |
| `xerox-k-c02` | 1 | 1 | 21 | (2064, 1296, 2368, 1840) | 9745x5877 | 57.3 |
| `xerox-k-c03` | 1 | 1 | 21 | (0, 1552, 304, 2096) | 9745x5905 | 57.5 |
| `xerox-k-c04` | 1 | 1 | 21 | (0, 1936, 304, 2480) | 9745x5906 | 57.6 |
| `xerox-k-c05` | 2 | 2 | 21 | (0, 2832, 304, 3392) | 10002x5905 | 59.1 |

Targets by class: gain 2, miss 5

- `xerox-k-c01`: (4, 0) [gain], (7, 0) [gain]
- `xerox-k-c02`: (24, 36) [miss]
- `xerox-k-c03`: (28, 0) [miss]
- `xerox-k-c04`: (34, 0) [miss]
- `xerox-k-c05`: (48, 0) [miss], (49, 0) [miss]
