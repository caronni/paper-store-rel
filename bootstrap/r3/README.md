# bootstrap/r3: the R3 rung, a monolith receiver for the archive's black-only row (2026-10-20, machine 1)

*2026-10-26: "No real paper" below is true of this 10-20 round; its descendant c.py (retargeted to r0547, then repaired) read page 03 on 10-23 and closed the full volume on paper on 10-26 (bootstrap/PAPER-2026-10-26.md). Open threads: docs/TODO.md, Bootstrap.*

`receiver.py` is meant to be the R2 pages' `b.py`: one Python file with no
imports at all. It carries its own SHA-256, AES-128, CRC-32, BCH encoder,
LDPC decoder and fountain. It reads flatbed scans of real archive pages in
the holo format (src/holo is the authority) for one row only, the most robust
black-only one. Everything here has been run in simulation only: nothing was
printed or scanned, and nothing is promoted.

## The row

- **Family:** K (black toner only). Cells are c3, 3×3 printer dots at
  600 dpi; set `CELL_DOTS = 4` for c4.
- **Codes:** LDPC rung r0550 (n 4096, k 2240), 100 address sites per tile
  (p100, no dust, no fillers), metadata version 0.
- **Paper:** A4-6mm. The tile matrix is derived from that bundle: 35×24 for
  c3, 26×18 for c4.
- **Source fraction:** the registry's "resilient" profile prints c3-r0550 at
  0.5. The fraction is not printed and the receiver never needs it: K
  arrives on every tile's metadata bit.
- **Format id:** `FORMAT_ID` is the AES seed and a constant of the program,
  derived from `CELL_DOTS`.
  - c3 (the test row): `holo/v2/1i200-k-r0550-p100-v1@35x24`, display name
    `c3-k-r0550@35x24`.
  - c4: `holo/v2/1i150-k-r0550-p100-v1@26x18`.
  - For the archive itself the id is fixed at print time, like the R2
    constants.

## Files

| file | what |
|---|---|
| `receiver.py` | The monolith, written to be read: 1,100 lines, of which 64 are the LDPC table. Sections: 1 row constants, 2 SHA-256, 3 AES keystream, 4 sites, 5 BCH word, 6 LDPC + CRC, 7 scan, 8 volume, 9 reader. |
| `pack_ldpc.py` | Packs `src/holo/core/ldpc/data/r0550.json` into the receiver's `LDPC_TABLE`, then checks that the expanded check lists equal holo's 14,611 edges (once the shortened tail is removed). They are identical. |
| `check_parts.py` | Checks each part against holo and the stdlib; `FORMAT_ID` and `SITES_ID` against holo's own resolution of the display name (`resolve_format_ref`; before the fix round it compared the id with itself). Then it runs the code chain on the generator's own cells, with no scan involved: every tile, page 0 alone, and a random 60 % of both pages. `--c4` does the same for c4. |
| `check_volume.py` | The volume logic without scans: read_scan on the true certified tiles of holo-encoded volumes. `cadence`: 40 random K+1..K+3 repair-only sets of a K = 1,519 volume (the refuter's blocker 1); `mixed`: five piles that mix volumes of another size and of the same size; `timing`: the fountain's cost at K = 1,000 … 16,384. |
| `run_mixed.py` | The receiver on the refuter's own simulated scans (`build/r3-refute/`: VA 60,000 B / 1 page, VB 400,000 B / 4 pages, VF the fossil seed) in mixed piles; every payload file written is matched against every truth. |
| `make_test_volume.py` | Generates the test volume with holo's generator and rasterises it with ghostscript's bitcmyk K plane, checked equal to the generator's GT on both pages. Then simulates the scans; truth sidecars go beside them. |
| `run_case.py`, `run_all.py` | Run the receiver the way the finder would: a fresh directory, scan names on stdin, `payload.bin` compared with the truth afterwards. |
| `scan_stats.py` | Per-scan figures over every placed tile: per-stage seconds, raw cell error against truth, wrong certificates. This is the runtime table's source. |
| `measure.py` | All the size figures: the receiver's forms, compressed sizes, R2 pages, the stdlib variant, the section breakdown. |
| `holo3_crosscheck.py` | Optional: runs holo's own receiver on one simulated scan, capped at 15 minutes. |

Outputs go to the gitignored `bootstrap/build/r3/`: the volume, scans,
`runs/`, `stats/`, `forms/`, `holo3/` and `measure.json`.

## How to run

The receiver, as the finder would run it (Python 3, nothing else):

```
python3 receiver.py
scan (PGM file [dpi]; empty line ends): page0.pgm 1200
scan (PGM file [dpi]; empty line ends): page1.pgm 1200
scan (PGM file [dpi]; empty line ends):
```

- **Input:** one line per scan, `FILE [DPI]`; the dpi defaults to 1200. An
  empty line or EOF ends.
- **Scan format:** P5 PGM, 8 or 16 bit. A 16-bit file is read by its high
  byte.
- **What a scan must be:** one whole page, at any quarter turn, tilted up to
  about ±10°.
- **Output:** one line per scan, giving the page, the turn, tiles placed,
  tiles decoded, tiles certified, its volume's number, symbols held /
  needed, and `done` or `more`.
- **When a volume closes:** the fountain's equations are reduced as each
  certified tile arrives, so the volume closes on the tile that brings their
  rank to K. If the envelope's SHA-256 checks, the payload goes to
  `payload.bin` in the current directory (a second volume of the session to
  `payload-2.bin`, and so on) and the program says so.
- **It reads on until the empty line.** A scan of a volume that is already
  complete is recognised from its first 24 certified tiles and skipped.
- **Several volumes in one pile.** Every volume of this row shares the seed
  and counts its tiles from 0. The receiver tells them apart by the
  metadata bits every tile carries (they encode K):
  - a page whose bits fit no known volume opens a new one;
  - a page of another volume of the SAME size cannot be told apart by its
    metadata. It is caught when its tiles contradict the volume's: two
    different symbols for one counter, an inconsistent fountain equation, or
    a wrong SHA-256 at rank K. The scan that shows the contradiction is
    refused whole (its tiles are rolled back), and the message names the
    scans already in the volume, since either may be the foreign one;
  - a scan with fewer than 24 certified tiles cannot name its volume: it is
    set aside, joined to the one volume all its bits agree with (at least 8
    bits), or pooled with other thin scans to solve a metadata word.

The harness, from the worktree root (generation needs ghostscript):

```
PYTHONPATH=src env/bin/python bootstrap/r3/make_test_volume.py volume   # + scans; --c4 for c4
PYTHONPATH=src env/bin/python bootstrap/r3/make_test_volume.py scans
PYTHONPATH=src env/bin/python bootstrap/r3/pack_ldpc.py                 # only if the table changes
PYTHONPATH=src env/bin/python bootstrap/r3/check_parts.py [--c4]
env/bin/python bootstrap/r3/run_all.py                                  # 15 cases, 6 at a time
PYTHONPATH=src env/bin/python bootstrap/r3/scan_stats.py base1200_p0.pgm s2400_p0.pgm:2400 rough_p0.pgm
PYTHONPATH=src env/bin/python bootstrap/r3/measure.py                   # writes build/r3/forms/
env/bin/python bootstrap/r3/run_all.py --receiver bootstrap/build/r3/forms/receiver.ming.py --tag _ming base1200 rough blank40
PYTHONPATH=src env/bin/python bootstrap/r3/check_volume.py [cadence mixed timing]
env/bin/python bootstrap/r3/run_mixed.py                                # needs the refuter's build/r3-refute/ scans
```

## The test volume

**c3 volume:**

- **Payload:** 200,000 B, sha256
  `e4795fa364f8306cbcaf3a6ae998dba0736bec727c715db9f9051aa0ffc781e5`. It is
  the first 200,000 bytes of `bootstrap/*.md` followed by
  `src/holo/format/*.py`, sorted, each prefixed with `==> path <==`.
- **Generator:** `holo generate --format c3-k-r0550@35x24 --source-fraction
  0.5`, A4-6mm, default printer.
- **Shape:** K = 760 symbols of 2,107 bits, 2 pages × 840 tiles = 1,680
  symbols (K/N 0.452).
- **Page faces:** both PostScript pages rasterise to exactly the
  generator's GT (field origin (148, 176) dots), with no ink outside the
  field.

**c4 volume:** 110,000 B, sha256 `26fc9d7f…fa220`, K = 418, 2 pages × 468
tiles.

**Simulated scans:**

- **Rendering:** each page at 1200 dpi, plus an 8 mm white bed margin.
  Bilinear resampling of the 600-dpi dot page, Gaussian blur of 0.35 dot,
  paper 232 and ink 38 grey, noise σ 6.
- **Variants:**
  - `base1200`;
  - `s2400` (2400 dpi);
  - `scale` (+0.4 %);
  - `rot03` (0.3°);
  - `rot15` (1.5°);
  - `seam` (Canon-like: the image shifted +0.84 dot for every sensor column
    past 16.51 + 18.288k mm, cumulative);
  - `combo` (180.3°, +0.4 %, seams);
  - `turn90` / `turn270` (the base scan quarter-turned);
  - `blank40` (40 % of each page's tiles whited out, seeded);
  - `rough` (0.3°, +0.4 %, seams, blur 0.75 dot, toner gain, paper 215 /
    ink 75, noise σ 34, and 3 % of cells inverted at random as print
    defects).
- **Raw cell error** against truth: 0.000 % on every variant except `rough`
  (3.04 %). The light channel does not exercise the LDPC; `rough` is there
  to do that.

## Verification

All results below are byte-exact: the SHA-256 of `payload.bin` equals the
truth. Wall times are for the whole session on machine 1 (Apple M1 Max, CPython
3.14.8 free-threaded).

**Fix round, 2026-10-20.** The refuter found two blockers in the close
logic:

- the close was tried only every 4 new symbols, so a volume whose last 1-3
  symbols completed the rank never closed;
- a page of another volume poisoned the session without a word.

Both are fixed. The fountain is now reduced incrementally (echelon form,
lowest pivot, one row per certified tile), and the close runs exactly when
the rank reaches K, so there is no cadence left to miss. Volumes are
separated by their metadata, and contradictions refuse the scan whole.

Every case below was re-run on the fixed receiver. Since the receiver now
reads on after the close, each session also identifies the second page
(24 tiles decoded), and walls are about 8 s higher than in round 1.

| case | scans fed | result | wall |
|---|---|---|---|
| base1200 | p0, p1 at 1200 | p0: 840/840 placed, 765 decoded, 765 certified → done at rank 760; p1 recognised (24 tiles) | 44.7 s |
| p1first | p1, p0 | p1 alone: 760 certified, all repair rows (pure GF(2) solve) → done | 44.5 s |
| s2400 | p0, p1 at 2400 | 840/840 placed, 765/765 → done | 44.6 s |
| scale +0.4 % | p0, p1 | 840/840, 765/765 → done | 44.6 s |
| rot03 0.3° | p0, p1 | 840/840, 765/765 → done | 44.6 s |
| rot15 1.5° | p0, p1 | 840/840, 765/765 → done | 44.8 s |
| seam | p0, p1 | 840/840, 765/765 → done | 45.0 s |
| combo 180.3° + scale + seams | p0, p1 | turn 180, 840/840, 762/762 → done | 44.6 s |
| turn90 / turn270 | p0, p1 | found at turn 270 / 90, 840/840, 761 / 762 → done | 44.5 / 44.6 s |
| rough (3 % raw) | p0, p1 | 840/840 placed, 767 decoded, 763 certified → done | 66.9 s |
| **blank40 (pooled)** | p0, p1 | p0: 504/840 placed (= every non-blank tile), 504 certified, more; p1: 504 placed, 258 decoded → rank 760 at 762 held, done | 73.8 s |
| c4 base1200 | p0, p1 | 468/468, 423/423 → done | 30.8 s |
| c4 combo | p0, p1 | turn 180, 468/468, 420/420 → done | 30.7 s |
| c4 blank40 (pooled) | p0, p1 | 281/468 + 138 decoded → 419 held, done | 60.4 s |
| **minified-g form** | base1200, s2400, combo, rough, blank40 | all byte-exact | 44.5–73.4 s |
| minified form | base1200, blank40 | byte-exact | 43.9 / 72.4 s |
| stdlib minified-g form | base1200, blank40, rough | byte-exact | 43.9 / 73.0 / 66.3 s |

Round 1 only (the code these exercise was not touched in the fix round):

| case | scans fed | result | wall |
|---|---|---|---|
| 16-bit PGM with a `#` comment | p1 only | 760 certified → done | 35.1 s |
| wrong FORMAT_ID (negative) | base1200 p0 | "no tile address found", nothing written | 3.8 s |
| c4 scan into the c3 receiver (negative) | c4 p0 | "no cell lattice found", nothing written | 10.5 s |

**Mixed piles on scans** (`run_mixed.py`, the refuter's volumes and scanner
model):

| case | scans fed | result | wall |
|---|---|---|---|
| the refuter's blocker 2 | VB p3, VA p0, VB p2, VB p1 | VB opens as volume 1; VA opens volume 2 and closes → `payload.bin` = VA; VB closes on p2 at 1,521 held → `payload-2.bin` = VB; p1 recognised. Round 1: neither closed, no warning, 346 s | 97.5 s |
| VA first | VA (60 % crop), VB p0, VB p1 | VA → `payload.bin`; VB → `payload-2.bin` | 88.2 s |
| VB p3, p2 | repair rows only | VB byte-exact | 73.8 s |
| VB p2 twice, then p0 | | the repeat is recognised (24 tiles) and adds nothing; VB byte-exact | 81.2 s |
| VA mirrored (negative) | | "no tile address found (wrong FORMAT_ID, a mirror-image scan, or not this row?)" | 4.0 s |
| the fossil-seed VF into the v2 receiver (negative) | | the same message, nothing written | 4.0 s |

**The volume logic without scans** (`check_volume.py`, holo's own fountain
encoder):

- **Close cadence** (blocker 1), 40 random repair-only sets of K + 1..3
  symbols, K = 1,519: 28 have rank K and all 28 closed byte-exact in ingest
  order; 12 have rank 1,518 and correctly stay open; 0 missed. Round 1
  missed 3 of 18.
- **Mixed volumes**, five piles, all as expected:
  - B p3, A p0 (another size), B p2, B p1: both close;
  - A p0 with 60 % of its tiles cut, then B p0, B p1: both close;
  - 150 tiles of A, then 200 of A2 (another volume of A's size), then the
    rest of A: A2's scan is refused at its first contradiction (an
    inconsistent equation, before any counter collided), and A closes;
  - 200 tiles of A2 first, then all of A: A's scan is refused (tile 1
    differs), nothing closes. The message names A2's scan as the other
    suspect: a foreign page fed FIRST makes the genuine ones look foreign,
    and only the finder can tell which pile is the right one;
  - a thin scan (20 tiles of B p2) set aside, then joined to volume B when
    B p3 opens it; B closes.
- **What it cannot see:** a page of another volume with the same size whose
  counters do not collide and whose equations are not yet overdetermined
  goes in unnoticed. It shows up at the latest at rank K, as a wrong
  SHA-256. That scan is then refused, and the volume waits for more
  pages.

**Every placed tile, with no early close** (`scan_stats.py`, re-run on the
fixed receiver):

- On every variant measured (base, 2400, combo, rot15, both base pages),
  every placed tile certified.
- `rough` p0: 836/840 certified.
- No wrong certificate anywhere; every certified symbol was checked against
  the true one.
- Each page closes alone, as q 0.5 promises for 2 pages; `blank40` pages
  close only pooled.

**`check_parts.py`, re-run:** every part passes against holo and the stdlib
(FIPS-197, keystream blocks, sites, printed words, slot permutation, payload
scramble, CRC-32, SHA-256). `FORMAT_ID` and `SITES_ID` now match holo's
`resolve_format_ref` seeds. The chain also closes from the GT cells: page 0
alone, and a random 60 % of both pages (430 repair rows used). c4 likewise.

**Cross-check with holo3** (round 1; `python -m holo.receiver decode
--format c3-k-r0550@35x24 --dpi 1200 --workers 4`), on the same simulated
scans:

- base1200_p0: VERIFIED byte-exact, 38.8 s wall, 762 certified.
- rough_p0: VERIFIED byte-exact, 36.6 s wall.

**The refuter's independent runs** (`build/r3-refute/`, round 1 receiver):
fresh volumes from holo's generator through its own scanner model were all
byte-exact. The cases covered −2.3° with anisotropic scale, a 1.2-dot and a
3-dot bow, a transport step, 9.5° plus a quarter turn, a 60 % crop, 16-bit,
3 % inverted cells with noise σ 30, 2400 dpi, and 55 % of tiles blanked. The
fossil seed `holo/v1/c3-r0550/2240x1536` read byte-exact in 19 s with
`FORMAT_ID` changed.

## Sizes

From `measure.py`.

- **Compressors:** cm2 is the bootstrap's own coder (`typed/cm2_enc.py` v2,
  orders read from `cm2_dec.py`). Its primer is the R2 chain's
  `bootstrap/build/loader/r.py` (5,133 B: the loader's definitions plus the
  stage-2 reader), which is what the finder's machine holds when it decodes
  b.py. zlib -9 and lzma (xz, preset 9e) are given for reference.
- **R2 pages** = ceil(bytes / 5,304).

| form | lines | bytes | cm2 | zlib -9 | lzma | R2 pages (cm2) | R2 pages (uncompressed) |
|---|---|---|---|---|---|---|---|
| raw (readable) | 1,100 | 51,106 | 15,341 | 19,301 | 17,432 | 3 | 10 |
| comments + docstrings stripped (ast.unparse) | 780 | 36,288 | 10,457 | 13,155 | 11,844 | 2 | 7 |
| python-minifier (locals renamed, docstrings removed, literals hoisted …) | 429 | 24,250 | 9,698 | 11,846 | 10,632 | 2 | 5 |
| **minified-g** (also module-level names renamed; safe, b.py is a script) | 446 | 22,011 | **9,415** | 11,480 | 10,324 | **2** | 5 |
| stdlib allowed, stripped | 723 | 34,520 | 10,000 | 12,575 | 11,324 | 2 | 7 |
| stdlib allowed, minified-g | 411 | 21,010 | 9,043 | 10,996 | 9,888 | 2 | 4 |

- **What the fix round cost:** minified-g went from 8,836 to 9,415 B cm2
  (+579 B). Most of that is the volume separation (metadata naming, scan
  rollback, thin scans, the refusal messages). It is still 2 R2 pages, with
  1,193 B to spare of 10,608.
- **cm2 round trip:** the decoder (`cm2_dec.decode`, the finder's code)
  recovers minified-g in 3.0 s and stdlib minified-g in 2.8 s, both
  byte-identical. Both forms were then run as receivers (table above).
- **The stdlib variant:**
  - It replaces SHA-256 with `hashlib`, CRC-32 with `zlib.crc32`
    (`binascii.crc32` would do too), and cos/sin and gcd with `math`.
  - It saves 1,001 B minified and **372 B (4.0 %) compressed**, and does not
    change the page count.
  - Nothing else in the stdlib replaces own code: AES, the BCH generator,
    LDPC, the fountain and the PGM reader have no stdlib equivalent, and the
    LDPC table is random data.
- **Where the compressed bytes go** (the stripped form; each section's
  marginal cm2 bytes):

  | section | cm2 bytes |
  |---|---|
  | **LDPC table (data)** | **2,713** |
  | scan (PGM, lattice, first tile, placement, LLRs) | 2,051 |
  | reader loop (scan by scan, volume naming, rollback, thin scans) | 1,531 |
  | AES + keystream draws (incl. the optimised scramble) | 1,033 |
  | geometry helpers | 686 |
  | LDPC expand + decode + CRC | 631 |
  | volume (metadata, incremental fountain, envelope) | 614 |
  | SHA-256 | 460 |
  | row constants | 328 |
  | BCH | 241 |
  | sites | 169 |

  These are marginal bytes in file order, so a section's figure depends on
  what precedes it.

- **The LDPC table** is 19,382 bits = 2,423 B of information:
  - the interleaver pi as a Lehmer code, log2(1856!) ≈ 2,180 B;
  - plus the block rows and shifts, 241 B.

## Runtime per c3 page

Pure Python on machine 1 (M1 Max, CPython 3.14.8t), from `scan_stats.py`, with
every placed tile decoded.

| scan | read | lattice | placement | sampling + LLR | payload scramble (AES) | slot map | LDPC + CRC | fountain (page alone) | total |
|---|---|---|---|---|---|---|---|---|---|
| base1200 p0 | 0.0 | 2.9 | 4.2 | 5.0 | 24.8 | 0.5 | 1.0 | 0.4 | 38.9 s |
| base1200 p1 (repair rows only) | 0.0 | 2.8 | 4.1 | 4.9 | 23.9 | 0.5 | 1.0 | 0.5 | 37.8 s |
| s2400 p0 | 0.1 | 2.9 | 4.2 | 4.9 | 24.9 | 0.5 | 1.0 | 0.4 | 38.9 s |
| combo p0 | 0.0 | 2.9 | 4.2 | 5.0 | 24.8 | 0.5 | 1.0 | 0.4 | 38.9 s |
| rough p0 (3 % raw) | 0.0 | 6.3 | 4.2 | 5.0 | 24.7 | 0.5 | 15.8 | 0.4 | 56.9 s |
| blank40 p0 (504 tiles) | 0.0 | 3.7 | 18.0 | 3.0 | 14.9 | 0.3 | 0.6 | – | 40.6 s |

- **The scramble dominates.** It costs one AES block per cell, 3.44 M per
  page.
  - A plain T-table AES ran 32.2 s per page.
  - The receiver's own cut runs it in 24.9 s. Only Y and X vary, so round 1
    is per row plus one term per column, round 2 is per row plus one lookup
    per word, and the last two rounds compute only byte 0.
- **LDPC:**
  - 1 s per page when the reads are clean: the hard-decision syndrome holds
    and no iteration runs.
  - About 19 ms a tile at 3 % raw error (layered min-sum, α 0.75, at most 50
    iterations).
- **The fountain** (incremental elimination plus the one back-substitution
  at rank K) costs 0.4 s for page 0's mostly systematic rows and 0.5 s for
  page 1's 760 repair rows.
- **Large volumes** (`check_volume.py timing`; K + 16 tiles, half source,
  half repair, including the coefficient draws). This is the whole
  session's fountain cost, paid once:

  | K | 1,000 | 2,000 | 4,000 | 16,384 (the single-block limit, 4.3 MB) |
  |---|---|---|---|---|
  | seconds | 0.2 | 0.7 | 3.3 | 108.7 |

  In round 1 every attempt re-solved from scratch, every 4 new symbols. The
  refuter measured 0.3 / 1.3 / 6.4 s per attempt at K = 1,000 / 2,000 /
  4,000, about 2–3 minutes per attempt at 16,384. A 16,384-symbol volume
  is about 22 pages, about 15 minutes of page decoding, so the fountain
  adds about 12 %.
- c4 pages take about 23 s.
- At 2400 dpi the aperture is read on a 4×4 grid, so the cost is the same as
  at 1200. The file itself is 631 MB in memory.

## Deviations from the four maps (and which was right)

- **Lattice:** the acquisition map's FFT seed (A1) was not built. In its
  place:
  - a coarse angle search (±10° in steps of 0.5°) that maximises the
    variance of box reads at cell phases;
  - then the lattice is tracked on rings of doubling radius (8 directions,
    sideways fallbacks), with a least-squares refit at each ring;
  - a guard that refuses a measurement landing near half a cell from its
    prediction (a possible slip);
  - and a final check: at least 12 points, steps within 6 % of the declared
    pitch, square to 2°.

  This needs no FFT code and was measured on every variant. The ≥12-point
  rule exists because a c4 `blank40` page started on a mostly blank patch.
  Its first ring found nothing, and the coarse angle was a 1.5°-rotated
  square lattice that passed the pitch/square check; the rule sends it to
  the next start point.
- **Per-tile pose:** the map proposed a per-tile affine from neighbouring
  origins. Built instead: one global affine plus a per-tile translation
  residual. The residual is found on the 100 sites (a coarse 0.25-cell grid,
  then 1/8 and 1/16, with a wider 0.5-cell net when that fails) and gated at
  ≤ 20/100 mismatches, the map's gate. That was enough for scale, rotation
  and seams in simulation. Real paper with non-affine warps is untested.
- **Placement walk:** the map left failed tiles to be "reached later from
  another neighbour". At 40 % blank tiles that is site percolation at
  threshold, and it measured 419 and 168 of 504 placed. The walk therefore
  goes through failed tiles, predicting each from the nearest ring of placed
  ones, and then places all 504 on both pages.
- **First tile:** the map used a 128×128 block. A 192×192 block puts four
  whole tiles under every phase hypothesis (4 turns × 128²), tried at up to
  9 places. Acceptance needs clean pad bits, the re-encoded word within 13
  errors, and then ≥ 3 tiles placed. As both the layout and codes maps said,
  no BCH decoder is needed.
- **Soft bits:** the acquisition map ported PAVA over 3×3 tiles. Built
  instead: a per-tile Gaussian LLR from the tile's own 100 known sites (the
  class means and pooled variance), clipped at ±20. The codes map's claim
  that "a threshold from the sites is enough at c3" held, including at 3 %
  raw error.
- **AES cost:** the layout map estimated about 42 s per page for the
  scramble with a T-table AES. Measured: 32 s plain, 25 s cut. The map was
  right on order.
- **LDPC:**
  - The codes map gave 3–5 ms per iteration; measured about 19 ms a tile at
    3 % raw. Both are consistent.
  - The codes map's table floor (log2 1856! ≈ 2,180 B) holds: the packed
    integer reaches 2,423 B with the rows and shifts.
  - Removing the shortened tail (2140..2239) from the check lists is
    equivalent to the maps' "pin to −∞".
- **Fountain:** the fountain map's B = 1 collapse (row = tile counter) and
  its metadata solve were both used as described, and both were confirmed:
  page 1 alone closes from repair rows only.
- **Tile matrix:** none of the maps derived it from the paper; the receiver
  does, as floor((A4 dots − 2 × 6 mm) / (64 × cell dots)). This gives 35×24
  and 26×18, both equal to the generator's (`fit`).

## What the monolith does NOT handle

- **Colour,** other families (cmy, cmy7, cmy8), other rungs, `p` ≠ 100, and
  paper other than A4-6mm (another bundle changes `TILES_Y/X`).
- **Multi-block volumes:** K > 16,384, i.e. payloads over 4,315,100 B. It
  refuses these with a message; the domain-8 block assignment is about 20
  lines more.
- **Fragments and confetti:**
  - Each scan must hold one page with enough of its lattice: at least 12
    tracking points and one cleanly readable tile near the middle.
  - Several pages in one scan are not supported, and a page torn into
    pieces is not tested.
- **Image geometry:** mirrored scans, and tilts beyond about ±10° from a
  quarter turn.
- **Pose model:** non-affine pages (folds, curl): the per-tile pose is only
  a translation over one global affine.
- **Capture combining:**
  - Two captures of one page are not combined softly: a tile already
    certified is skipped, an uncertified one is tried again.
  - The production receiver's machinery is absent: page field, context
    PAVA, multi-capture sums.
- **Image formats:** anything other than P5 PGM (TIFF and PNG must be
  converted, as for the R2 reader).
- **Damage:** a tile that contradicts its volume (another symbol for a
  counter, an inconsistent equation, a wrong SHA-256 at rank K) refuses the
  SCAN it came from, whole, never repaired. A good page refused because a
  foreign page of the same size came first is not re-tried automatically:
  the finder restarts without the scan the message names.

## Weaknesses (honest)

- **No real paper.** Everything is simulation. The light channel reads at
  0 % raw cell error; only `rough` exercises the decoder (3 %, 836/840).
  Paper c3 measured 0.05–3.5 % raw on the record's engines.
- **The receiver's gates are its own, not the production receiver's
  qualified ones:**
  - the tile gate (20/100 mismatches);
  - the first-tile acceptance (13 errors plus pads);
  - the lattice checks (ratio 2, the 0.35 slip guard, 12 points, 6 %, 2°).

  The production receiver itself is PROVISIONAL.
- **Speed is one machine's.** The runtimes are an M1 Max. A deep-time
  "Python-class" machine could be 10–100× slower, which would mean 7–70 min
  a page, mostly AES. The whole PGM is held in memory: 158 MB at 1200,
  631 MB at 2400.
- **Lightly tested paths:**
  - 16-bit PGM was tested once.
  - The fallback start points for the lattice and the first tile were
    exercised only by `blank40`.
  - Volume separation on scans was tested with two volumes of different
    sizes. The same-size case was tested on tiles only (`check_volume.py`),
    not on scans.
- **Volume naming has odds.** A scan joins the one volume all of its first
  24 metadata bits agree with, so a foreign page of another size is
  misnamed with odds 2^-24. A thin scan joins with 8 bits (2^-8). A wrong
  join is caught later as a contradiction, so it costs a refused scan, not
  a wrong payload.
- **A same-size foreign page fed first** makes the genuine pages look
  foreign. The program names the suspects but does not choose between them;
  the finder restarts without one.

## Open questions for the owner

1. **Size.** The monolith is **2 R2 pages** as cm2 (9,415 B minified-g, of
   10,608 B; 8,836 B before the fix round). One page (5,304 B) would mean
   cutting 44 %, and the LDPC table
   alone is 2.7 KB of it. Options, none built:
   - accept 2 pages;
   - derive H from paperholo's seeded construction (Philox + BLAKE2b and the
     column rules: more code, and an unmeasured pure-Python search time);
   - a future format with an algebraic code (a format change, not this
     row).
2. **Stdlib.** Allowing it saves 372 B compressed (4.0 %) and no page. The
   recommendation is to stay import-free.
3. **The archive's id and paper.** The receiver assumes A4-6mm and derives
   the id from `CELL_DOTS`. The archive's real id (and paper bundle) is
   fixed at print time. Should `FORMAT_ID` be the one constant edited, with
   TILES_Y/X spelled out beside it rather than derived?
4. **A paper test exists, if you want it.** The e033 AltaLink sheets
   A (c4-r0550), A2 (c3-r0550, q 0.3) and G (c3-r0550, q 0.9) are printed,
   unscanned, and have the same cells and codes under the fossil seeds:
   - `holo/v1/c3-r0550/2240x1536`;
   - `holo/v1/c4-r0550/1664x1152`.

   With `FORMAT_ID` set to the c3 fossil seed, this receiver read a
   simulated fossil sheet byte-exact: the refuter's `vf_fossil` case,
   80,000 B in 19 s. The c4 fossil is untested even in simulation. Scanning
   the printed sheets needs your go (hardware rule).
5. **Runtime target.** Is about 40 s a page on an M1 (25 s of it AES)
   acceptable for the finder? If not, the next cut is algorithmic: bitsliced
   AES on 4096-bit Python ints. It is not obviously faster in CPython; the
   estimate is 15–20 ms a tile against 28.
6. **Should R3 read partial pages and confetti?** That needs per-region
   lattices and a first-tile search per fragment. Today the page must be
   mostly whole.
7. **One volume or many?** If the archive is exactly one volume of this
   row, the volume separation is insurance: it cost most of the fix round's
   +579 B cm2, and the page count did not change. The incremental fountain
   is needed either way: it fixes the missed close and the K^2.2 re-solves.
   Keep the separation, or cut it to a single volume that refuses
   contradicting scans?
8. **Stop at the first close, or read on?** Today the receiver reads on
   until the empty line, so that a mixed pile yields every volume in one
   session. A page of a volume that is already complete costs about 10 s
   (placement plus 24 tiles). The round-1 behaviour was to stop at `done`.
