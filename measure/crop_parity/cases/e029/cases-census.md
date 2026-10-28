# Crop cases — e029 (e029 HP K (c2-r0700))

Format `L:c2-r0700@3392x2368`, tile matrix 53x37, streams ['main'], 1 capture(s) at [4800.0] dpi. Generated in 0.9 s from tree `e3f7640c2635` (dirty).

## The gap (recomputed, cross-checked against the record)

holo3 baseline harvest: `post-2` (17261 TileOutcome rows).

| set | addresses | recorded |
|---|---:|---:|
| holo1 certified | 1940 | — |
| holo3 certified | 1938 | — |
| both | 1938 | — |
| **miss** (holo1 only) | 2 | 2 |
| **gain** (holo3 only) | 0 | 0 |
| neither | 21 | — |

Ground truth: golden payload `e5021f8d0995…` (465580 B) re-encoded through holo1 generation, validated against 1940/1940 certificates in the archived holo1 state, zero mismatches.

## Captures and the cell→pixel fit

| # | capture id | shape (y, x) | ch | poses | px/cell | residual med / p99 / max px |
|---:|---|---|---:|---:|---:|---|
| 0 | `d9c4e932b904…` | 56128x40832 | 1 | 1479 | 15.997 | 5.2 / 30.0 / 40.5 |

The pixel bbox is padded by 32 cells' worth of pixels on all sides before clipping, which is the margin the max residual has to fit inside.

## Cases (1) — classes miss, gain, halo 240 cells, merge-gap 2 tiles, max span 768 cells

| case | tiles | targets | controls | cell bbox (x0,y0,x1,y1) | crop px (y, x) | MB/crop |
|---|---:|---:|---:|---|---|---:|
| `e029-c01` | 2 | 2 | 66 | (528, 2448, 1264, 2992) | 9736x12819 | 124.8 |

Targets by class: miss 2

- `e029-c01`: (42, 12) [miss], (42, 15) [miss]
