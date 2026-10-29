# r2gen — R2 page generator, camera simulator, grid self-check

## Built
- `gen.py capacity | page PAYLOAD OUT [--module-dots 12|10] [--copies 3|2]`:
  A4 4960×7016-dot `OUT.pbm` (P4, 1 = ink), `.png`, `.grid.txt`, `.json`
  (W, H, BW, BH, S, T, x0/y0, chunk_count, slot_chunk (65535 unused),
  slot_copy, SHAs). CRC = `zlib.crc32`.
- `camera.py PAGE.pbm OUT.pgm --sidecar PAGE.json --preset P --seed N [--p2]`:
  reflectance (paper .80, ink .10) → Gaussian blur (σ² = blur² +
  1/(12·spm²), pixel aperture) → corners displaced uniformly in a disc of
  radius persp·diagonal → homography, bilinear →
  illumination 1 ± illum along a random direction → noise → 8-bit. Header
  exactly `P5\nW H\n255\n` (P2: one row per line). Truth sidecar holds
  every parameter and the homography. Frame = whole page + background.
  Presets: nominal (2.0 spm, persp .02, blur .6, illum .2, noise 10); hard
  (1.5 spm); flatbed300 (spm = md/2, no perspective, 0.5° rotation, blur
  .10, illum .03, noise 3, lid .93, paper .88, ink .06). Re-runs identical.
- `verify_grid.py GRID [--sidecar] [--pbm] [--payload]`: stdlib,
  independent of gen.py; checks timing, bullseyes, CRCs, header, data CRC,
  placement vs the spec's π map and sidecar, PBM↔grid. Negative tests
  (flipped data bit, flipped timing module, swapped blocks) FAIL, exit 1.

## Capacity (gen.py; matches the spec)
Bytes: 12/3 5,382 (T 208); 12/2 8,112; 10/3 8,164; 10/2 12,272.

## Demo (scratchpad/r2gen/, seed 1; SHA-256 of every file in `SHA256SUMS`)
payload = first 5,000 B of T3_32k.txt (`53b1ce59…`), 194 chunks × 3.
page_12x3 pbm `f5c723a7…`, grid `6b489f25…`; page_10x3 pbm `35c97a03…`,
grid `551c52b2…`; both verify PASS. Captures: 12x3 nominal `0b2d0359…`
947×1290, hard `76677a29…` 710×967, flatbed300 `4dc6fbba…` 2602×3630;
10x3 nominal `2e3f2076…`, hard `b4af4dcc…`, flatbed300 `10c459df…`;
extras at blur 0.3: 12x3 `80210cd2…`, 10x3 `84691d29…`.

## MEASURED: the spec's blur defeats its own decoding rule
Genie (`scratchpad/r2gen/tools/genie.py`: true homography, bilinear centre
sample, per-block timing-median threshold, CRC):
- blur 0.6 (spec preset): 12x3 nominal 10.8 % module error, 0/626 blocks;
  hard 14.2 %; noise-free, flat: 10.2 %. Computed: a lone white module
  keeps erf(0.59)² = 0.35 of the swing; 1-module bullseye rings ~17 %.
- 2.0 spm (seed 2): σ .30 → 0.016 %, data OK; .35 → 0.27 %, 157/194 chunks;
  .40 → 1.1 %. 1.5 spm: σ 0 → 0.05 %, 193/194 chunks (NOT recovered);
  σ .30 → 1.8 %. flatbed300: 0 errors both pages.
Centre sampling + CRC closes at σ ≤ 0.3 module at 2 spm, nowhere at 1.5.

## Spec questions
1. 12 dots: "largest that fit" gives BH 32 (545 rows = 6,540 ≤ 6,543
   dots); the spec states 30. gen.py uses 30 (`--bh` overrides).
2. Is the blur σ = 0.6 meant in modules or in samples? 0.6 samples at 2 spm
   is 0.3 module, which is exactly the measured knee.
3. Bound edge assumed left (x0 = 18 mm + centring).
4. "row/col 16" of a corner block is the timing line; all d ≥ 7 white.
5. 10/3: T = 315 = 7·45, so π₂ = identity (copies 0 and 2 share order).
6. "copies thirds" for copies = 2 read as halves, T = floor(S/2).
7. 0.75 MP = the grid alone; a whole-page frame at 2 spm is 1.0–1.2 MP.
