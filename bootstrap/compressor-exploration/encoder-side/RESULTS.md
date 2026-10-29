# v2-lab-encoder: levers on the encoder and payload side (model = a.py's d(), unchanged), 2026-10-20

Every number here was MEASURED in this directory unless it is marked otherwise. Ideal bits come from cm2h.c, which matches cm2lab's ideal to 1e-9. Final sizes are exact (cm2lab rANS).

## (1) Typed reader (primer = a.py; currency = typed characters)
| form | glyphs | lines | typed total |
|---|---|---|---|
| record reader_lite_v1 | 2,876 | 48 | 3,894 |
| scope-exact renames only (lowercase pool without l, greedy, 4 sweeps) | 2,832 | 48 | 3,849 (-45) |
| + 48 single-site rewrites and def moves (moves -92 bits, shift-spellings -70, commutations -37, tuple permutations -19, one split -12, one un-augment -10, flips -7, one merge -6) | 2,782 | 47 | 3,795 |
| + a second rename pass, then converged | **2,774** | **47** | **3,788 (-106, -2.7 %)** |
| uppercase in the pool | no gain (-1.3 bits) | | |

The answer to "already name-optimised?" is no. Renames alone save 220 bits; the earlier search used an older primer and a hand-edited text afterwards. a.py changes only in its constants (4565->4556, kw86->1gfm, 49->48), with a character delta of 0.

Verification:
- the full typed chain (a_rw2.py + data_rw2.txt -> r.py) is exact;
- the new reader reads the build's pages identically to the record reader, frame by frame on 11 frames;
- b.py is identical when it is decoded with the record r.py as primer.

Knock-on: b.py is primed by r.py, so a new reader means re-encoding the R2 pages. With the new r.py, b.py costs +7 B and the record monolith +7 B (2 B spare).

## (2) Monolith (minified-g; primer = r.py; 2 pages = 10,608 B)
| step | exact B | spare |
|---|---|---|
| record | 10,599 | 9 |
| undo the minifier's module aliases (28 inlined, e.g. sorted, enumerate, 'big', zip, 20, 3, b'') | 10,523 | 85 |
| local renames, one windowed sweep (346 changed) | 10,049 | 559 |
| own attribute/method names renamed (43) | **9,876** | **732** |
| the same with the rw2 reader's r.py | 9,893 | 715 |

Verification:
- the owner's d() round trip is exact, with both primers;
- the test_arch-style scan-free cases (synthetic, badcrc, plain, T2 38 files) give ALL OK;
- every local rename is proved scope-exact;
- the scan path is not run.

With this spare, `import os` and the long messages fit (ESTIMATE from the RECORDED deltas).

## (3)/(4) Primers and the bundle: primer_ideal.json (ideal B)
- **Typed reader:**
  - a.py: 1,797.2.
  - Doubled: 1,809.1 (+23 typed).
  - Definitions only: 1,834.2 (+63 typed).
  - Main part first: 1,801.8.
- **Monolith:**
  - r.py: 10,598.8.
  - r.py + a.py's main part: 10,589.6 (-9).
  - r.py doubled: 10,660.9.
- **b.py:**
  - r.py: 15,775.4.
  - + leaves 3, 4: 15,649.6.
  - + plate: 15,405.5.
  - + both: 15,361.7. All stay at 3 pages.
- **The parts of b.py, primed by r.py:**
  - R2-FORMAT docstring alone: 8,188.4.
  - readable reader.py alone: 8,325.3.
  - Marginals inside b.py: reader.py after the docstring 7,587.0; the docstring after the reader 7,480.9. Swapping the order costs +31.
