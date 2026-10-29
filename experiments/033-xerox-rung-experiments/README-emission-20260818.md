# Xerox AltaLink C8245 candidate set — generated 2026-08-18

Eight one-page volumes, counting payload (bytes 0,1,2,…,255,0,… filling the
page exactly). **Nothing here has been printed.** Printing goes through
`scripts/print_plane.sh` after an explicit go (.claude/rules/hardware.md).

Regenerate byte-identically:

    env/bin/python scratch/xerox-v1-20260818/generate_set.py --out <fresh-dir>

Per-volume files: `page000.ps` (the print job), `page000_gt.npy` (ground-truth
bitmap), `manifest.json` (sidecar; sheets decode with zero out-of-band data),
`payload-counting.bin`. Machine-readable index: `set.json`.

| tag | coding | margin | cells/tile edge | tiles | q | payload (B) | K/N | net b/mm² |
|-----|--------|--------|------|-------|---|-------------|-----|-----------|
| A  | c4-r0550        | 6 mm | c4 | 468  | 0.3 | 32,622    | 0.265 | 4.2   |
| A2 | c3-r0550        | 6 mm | c3 | 840  | 0.3 | 62,120    | 0.281 | 8.0   |
| B  | c2-r0700        | 4 mm | c2 | 1961 | 0.7 | 465,580   | 0.691 | 59.7  |
| C  | c2-r0700        | 4 mm | c2 | 1961 | 0.9 | 600,183   | 0.891 | 77.0  |
| D  | c2-cmy8-p120-v1 | 4 mm | c2 | 1961 | 0.5 | 763,023   | 0.497 | 97.9  |
| E  | c2-cmy8-p120-v1 | 4 mm | c2 | 1961 | 0.9 | 1,376,601 | 0.897 | 176.6 |
| F  | c3-cmy8-p120-v1 | 4 mm | c3 | 840  | 0.9 | 586,932   | 0.893 | 75.3  |
| G  | c3-r0550        | 4 mm | c3 | 840  | 0.9 | 194,861   | 0.881 | 25.0  |

Notes that ride the set:

- **The 4 mm request only moves c2.** The 64-cell field quantum means the
  c3 and c4 fields are identical at 4.0 and 6.0 mm (borders 6.27/7.45 and
  7.62/7.45 mm); only c2 grows, 1872 → 1961 tiles, borders ~4.91/4.74 mm.
  A/A2 therefore carry the plain 6 mm printer row, F/G the 4 mm row with an
  unchanged field.
- **Edge tiles may clip on the c2 sheets.** `xerox-altalink-c8245-ink` is a
  geometry probe: the printable clip radius has never been measured on this
  engine the way e028 measured the M281. The fountain dial is the cushion.
- **D/E/F are colour** → the AltaLink lays yellow MIC tracking dots
  (measured 0.210 dots/mm², e031). K-only sheets (A/A2/B/C/G) stay clean.
- **E and F sit above the pooled dead-plane dial** (needs q ≤ 2/3): at
  q=0.9 a dead plane is no longer a deterministic tier. D (q=0.5) keeps it.
- **A (c4) is a proposed format row**, verified in simulation only — see the
  c4 amendment in docs/HOLO-DESIGN.md §4.1. No c4 sheet has ever been printed.

Decode (every sheet needs its own `--coding`; the c2 sheets also need the
`-ink` printer row for their geometry):

    ./confetti.py decode SCAN.tiff --scan-dpi 4800 \
      --coding <coding> --printer <xerox-altalink-c8245[-ink]> \
      --state <dir>/receive.state --out <dir>/recovered.bin
