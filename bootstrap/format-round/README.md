# The format round, 2026-10-22: three bullseye variants x two ring renderings

The owner's go (2026-10-22): "we should indeed measure out all three", and
"the bullseyes are rendered quite coarsely, we could go 600 dpi on them, if
that helps".  Three bullseye variants of R2-FORMAT v1 (bootstrap/R2-FORMAT.md),
each a generator change + a reader change, each reader WITHOUT the ring
check, the ring list and n (the comb alone rejects the timing crossings);
every variant and the format of record in two renderings.  Nothing here
changes the format of record; none of it is ruled.

This section is the generator side (gen/).  The reader side is reader/,
the measurements measure/.

## Files

- `gen/gen_variant.py` -- a copy of `bootstrap/r2/gen.py` with
  `--bullseye record|v1|v2|v3` and `--rings coarse|dot` on `page` / `pages`
  (defaults = the format of record), and `selfcheck [PAYLOAD]`.  Imports
  `bootstrap/r2/placement_stats.py` unchanged.  In-process callers:
  `gen_variant.configure(kind, rings)` before `build_grid` / `write_page`.
- `gen/verify_variant.py` -- a copy of `bootstrap/r2/verify_grid.py` with
  the same two options, the variant's rule re-derived from this text
  (stdlib, no code shared with the generator; the dot rule in float
  arithmetic where the generator uses integers).
- `gen/bullseye_profiles.py` -- centre-row / centre-column run-length
  profiles of a bullseye block per kind and rendering, at 600 dpi and
  through `bootstrap/r2/camera.py` (unchanged) at 2 and 7 samples per module,
  blur 0.30 and 0.45.
- Outputs (gitignored): `bootstrap/build/format-round/pages/<kind>-<rings>/`
  = `payload.bin`, `page_p{0,1,2}.{pbm,png,grid.txt,json}`, `gen.log`,
  `verify.log`; `bootstrap/build/format-round/profiles.txt`.

## Common to every variant

Geometry, timing lattice, placement, data blocks, header bytes (16-bit
length, CRC-32, 20-bit check) and the orientation refusal are the record's.
q = dx^2 + dy^2 from the block's module (0,0) (block-local (r, c) = (8, 8);
dx = c - 8, dy = r - 8, each -8..7; dx = +8 / dy = +8 is the next block's
timing line), n = round(sqrt q) (never a tie).  Quiet ring 43 <= q <= 56
white; q >= 57 the 79 header modules.  The orientation refusal (exit 3)
reads the variant's own header positions.  A variant's sidecar keeps
`"format": "R2v1"` (camera.py and the harnesses read only its geometry) and
adds a `"variant"` entry (kind, rings, rule, ink rings, header bit modules,
axis-white modules); the record / coarse sidecar has none and is gen.py's,
byte for byte.

## Record (the control)

q <= 42 ink iff n in {0, 2, 4, 6} (the spec's q table INK_Q, asserted);
the 68 header bits on the first 68 of the 79 header modules in block raster
order, MSB first, the last 11 white.  Per block 85 ink, 92 white, 79 header.
Centre row: thirteen one-module runs dx = -6..6, ink at dx = 0.  Its reader
is the ruled text, unchanged.

## V3 -- "axis bits moved, one flank" (the owner's preference)

Rings as the record.  The two header modules on the axes, (dx, dy) =
(-8, 0) and (0, -8) = block-local (r, c) = (8, 0) and (0, 8), print WHITE
and carry no bit.  The 68 header bits take the first 68 of the OTHER 77
header modules in block raster order (the last 9 white).  So the left and
top flank of the thirteen-run signature is two modules of white (quiet ring
dx = -7 + the axis module dx = -8) on every page; the right / bottom flank
is the quiet ring + the timing line at +8 (white when bi + bj is even, ink
when odd).  Per block 85 ink, 92 white, 77 header + 2 axis.  Grid
difference to the record: 32 modules per block on this payload (the
shifted bits).  Reader: the header list skips the same two modules; the
comb's flank rule becomes "at least one flanking white run >= 1.5 modules".
The spelling, from sp's own arithmetic: r = z[i]+z[i+1] is TWICE run i's
centre and t = z[i+12]+z[i+13]-z[i]-z[i+1] twice the centre-to-centre span
of twelve one-module runs, so t = 24 modules in pixels (the comb's boundary
test 12*(...) - (y+6)*t confirms the factor).  The record's
`min(z[i]-z[i-1], z[i+14]-z[i+13])*96 >= t` is therefore a quarter module
(the task text's "about 1/8 module" is off by two), and ">= 1.5 modules" is
`max(z[i]-z[i-1], z[i+14]-z[i+13])*16 >= t` (t/16, not t/8; t/8 would be
3 modules).  MEASURED in the profiles below: a ONE-module white flank (the
right flank of the odd-parity block (8, 5), the timing line inking +8) reads
1.5 modules at 2 spm phase 0, blur 0.30 and 0.45 -- exactly that bar -- and
1.0-1.14 elsewhere; V3's two-module flank reads 2.0-2.5 (and 3-4.5 where
the timing line is white too).  A bar between them, e.g. 1.75 modules =
`max(...)*96 >= 7*t`, or the strict `max(...)*16 > t`, separates the two
at these settings; the reader builder's to choose and to measure.

## V1 -- "the 3-wide band"

q <= 42 ink iff n in {0, 2, 4, 5, 6}: the white ring at radius 5 becomes
ink, so radii 4-6 are one three-module ink band.  Quiet ring and header as
the record.  Per block 113 ink, 64 white, 79 header (the 28 modules of
ring 5: q = 25, 26, 29).  Centre row: runs of 3, 1, 1, 1, 1, 1, 1, 1, 3
modules (nine runs over the same thirteen-module span, ink at dx = 0).
Its comb's expected boundaries are this pattern's, not the uniform table;
note that sp's r and t are sums of run boundaries (twice run centres), so
the 3-module end runs move the run-centre arithmetic (first-to-last centre
span 10 modules, not 12) -- the reader builder's derivation.

## V2 -- "inverted"

q <= 42 ink iff n is odd and n <= 5: ink at radii 1, 3, 5; white at 0, 2, 4
and 6 (ring 6 merges with the quiet ring).  Quiet ring and header as the
record.  Per block 52 ink, 125 white, 79 header.  Centre row: eleven
one-module runs dx = -5..5, white at dx = 0, with at least two modules of
white beyond the last ink ring on every side (ring 6 + the quiet ring).
Its comb takes eleven runs and both flanks >= 1.5 modules.  In sp's
arithmetic (see V3) t over eleven one-module runs is twice a 10-module span,
t = 20 modules, so 1.5 modules = 3t/40: `min(...)*40 >= 3*t` (the task
text's t/8 would be 2.5 modules).  MEASURED (profiles, both blocks, both
renderings, every setting): V2's flanks read 2.0-7.5 modules; a one-module
white flank reads up to 1.5 (V3 above), so a bar at 1.5 sits on the
crossings' side at 2 spm phase 0 -- the reader builder's to choose.

## The renderings

- `coarse`: every module solid ink or white on the 600-dpi raster (12
  dots per module) -- the record's rendering.
- `dot`: inside a bullseye block, every dot of a RING module (q <= 42) is
  ink iff round(rho) is an ink ring of the variant (round(rho) >= 7 white),
  rho = the distance in modules from the dot's centre to the centre of the
  block's module (0,0); the quiet-ring and header modules stay
  module-solid; everything outside the bullseye blocks is unchanged.  The
  generator's integer form: in half dots S = u^2 + v^2 with u = 2j + 1 -
  17 md, v = 2i + 1 - 17 md (block-local dot (i, j)), round(rho) = n iff
  ((2n - 1) md)^2 < S < ((2n + 1) md)^2 (no ties at md = 12: S = 2 mod 8).
  The `.grid.txt` is the module pattern (the rule at module centres) and is
  identical to the coarse set's.  MEASURED (verify_variant.py, every page):
  the circle rule at every ring module's centre == its grid value; dots
  changed from module-solid per page (15 blocks): record / V3 59,700, V1
  32,760, V2 46,020; a ring module's dots equal to its grid value: min
  0.521 (the q = 20 modules, whose centre lies 0.028 module inside the
  4.5 boundary), mean 0.798 record / V3, 0.889 V1, 0.844 V2; the central
  2 x 2 dots: 3 of 4 in the 8 q = 20 modules per block (record, V2, V3),
  4 of 4 everywhere in V1.  Consequence of "quiet modules stay solid": where
  ring 6 is ink (record, V1, V3) the true circle would ink 300 dots (2.08
  module areas) per block inside the quiet modules (+-6, +-3), (+-3, +-6),
  (+-5, +-5); they stay white, a dent of up to 0.46 module in ring 6's
  outer edge off the axes; the axes themselves are exact circles.  Ring
  6's dots beyond rho 6.5 inside ring modules (912 per block) are white.

## Verification (run 2026-10-22)

- `gen_variant.py selfcheck` (the stage-1 chain's recipe, `pages
  payload.bin page`, by gen.py and by gen_variant.py --bullseye record
  --rings coarse into fresh directories): all 12 files (.pbm .png
  .grid.txt .json, three pages) byte-identical to gen.py AND to
  `bootstrap/build/stage1/lower/r2/` (payload sha256 15ee6fc2...5f86,
  15,834 B, 3 pages; page_p0.pbm
  ca7421b6f782cb860acfe0dd8a605420c7f039fa17062f88b3be34bae129a14c).
- `verify_variant.py page_p{0,1,2}.grid.txt --payload payload.bin --pbm
  --bullseye K --rings R` in each of the 8 directories: PASS on all 8
  (timing, rings, header, orientation, 615 slots, placement, guarantees,
  sidecar, pbm, assembly); `bootstrap/r2/verify_grid.py` itself PASS on
  record-coarse.  Negative controls: v1-coarse checked as record FAILS (420
  ring modules + the sidecar's variant entry); v3-dot checked as coarse
  FAILS (760 dot rows + the sidecar).
- Grids: coarse == dot for every kind and page; against the record they
  differ only inside the 15 bullseye blocks (V1 28, V2 137, V3 32 modules
  per block).  No variant's header was refused for orientation on this
  payload.

## The profiles (bullseye_profiles.py; first reading, MEASURED)

camera.py's nominal preset with persp 0, rotate 0, illum 0, noise 0 (optics
and sampling only), fixed threshold 114.75 = (paper 0.80 + ink 0.10) / 2 x
255 (`--threshold` to use another; the ruled reader thresholds the whole
frame at (min + max) >> 1 of every 97th pixel, which illumination moves).
Blocks (2, 2) (bi + bj even) and (8, 5) (odd) of page 0.  What the comb
will face, at the centre run (grey value of the centre run's extreme):
- the isolated centre feature does not survive blur 0.45 at 2 spm in ANY
  kind or rendering: record / V1 / V3 centre dot reads white (158-159
  coarse, 153-158 dot), V2's centre hole closes (71-76).  At 7 spm, blur
  0.45: coarse keeps the record's dot at 109 and V2's hole at 121 (both
  within 6 of the threshold); dot rendering loses both (163 / 67).
- blur 0.30: coarse keeps the centre at both 2-spm phases (record dot 75 /
  104, V2 hole 154 / 125); dot rendering loses it at 2 spm phase 0.5
  (record 174, V2 55).  The dot rendering's centre is a disc of diameter
  one module (area pi/4 of the square) -- the 600-dpi circles make the
  centre feature WEAKER, the rings more even (2 spm phase 0: coarse ring
  runs K 0.5 / W 1.5 modules, dot K 1 / W 1).
- V1's band holds at every setting (K 3-3.5 modules, grey 26); its centre
  is the same single dot as the record's, so at blur 0.45 the nine-run
  signature reads seven runs (K3.5 W1 K0.5 W3.5 K0.5 W1 K3.5).
- V3's left / top flank reads 2-4.5 modules at every setting on both
  blocks (row 2-2.5 / 4-4.5, column 2-2.5 / 3-3.5); the record's TOP flank
  reads 1-1.5 on both blocks (this payload's header bit at (0, 8) is ink),
  its left flank 2-2.5 / 4-4.5 (the bit at (8, 0) is white).  The right /
  bottom flank of the odd-parity block reads 1-1.5 in every kind (see V3
  above for what that means for the bar).
The full table: `bootstrap/build/format-round/profiles.txt` (241 lines).

## Not done here

No reader, no capture render beyond the one-block profile crops, no
acceptance set, no stage-1 chain for the variants (the reader builder and
the measurer); the w4 acceptance sets render from the pages `one`,
`two_p0`, `two_p1` (build/w1/pages) -- a variant needs those pages from
`gen_variant.py` with that payload, not the stage-1 lower payload's.
