# BOOTSTRAP-DESIGN — the deep-time preface (recovery without us)

**v0.1, 2026-07-10. Speculative design, zero print, NO format changes.**
Companion to DESIGN.md (R3 anonymity / R5 registry doctrine, §10.2 trilemma),
PILOTS-DESIGN (window code), FEC-DESIGN, FOUNTAIN-DESIGN. Provenance: a
4-agent design workflow run 2026-07-10 — format-kernel audit of
src/paperholo + docs (verified spot-checks below), hostile red-team
(23 failure modes, 9 circularity findings), independent rung arithmetic,
and a web-verified deep-time-precedent survey. MEASURED/ESTIMATE labels as
usual; everything here is design unless labeled MEASURED.

> **Status 2026-10-18.** The typed rungs (R0–R2) were built in simulation on
> branch `ccr-200d7187-roznny` under `bootstrap/` (specs `bootstrap/R2-FORMAT.md`,
> `bootstrap/TYPED-STREAM.md`; measured record `bootstrap/RECORD.md`, since
> 2026-10-23 `bootstrap/RECORD-2026-10-18.md`, RECORD.md being the index; reviews
> `bootstrap/REVIEW-2026-10-18.md`). Amendments ruled that day and not yet folded
> into this text: a hand-typed stage-0 decompressor (cm2, 25 lines) is the one
> decoder at every rung, so R2 shrinks to one leaf and R3 to ~6; the hand-
> computed per-line sum of R1 is replaced by a typed 12-line checker with
> immediate feedback (MLX done by machine); CRC-32 is printed as its one-line
> definition only (no table); the Plate assumes Python-class computing and
> drops the from-zero primer and ASCII strips ("a different book"); the R2
> page is bullseyes + an alternating timing lattice every 17th row/column +
> 16×16 blocks of 2+26+4 bytes, 12-dot modules, 3 copies. **2026-10-19:** the
> typed rung is one 37-line program typed into a file (base-32 data lines with
> a 4-glyph check, 3,189 characters in all) plus a diet reader; see
> bootstrap/README.md and bootstrap/RECORD-2026-10-19.md. **2026-10-20:**
> R2-FORMAT v1 — the finder photographs the page in pieces: fifteen
> circular-ring bullseyes in the body carry the 68-bit header, every block its
> global chunk index under CRC-32, a designed placement guarantees three copies
> no straight strip under 46 mm can take; the loader is 29 lines with a
> big-integer rANS decoder (the typed data IS the coder state) and writes r.py
> = its definitions + the typed reader, which pools frames and pages and
> decodes the page's content to one file; 3,895 typed characters in all; the
> R2 payload is still a stand-in for the R3 reader (this section's "Payload"
> paragraph), three pages. The same afternoon the R3 rung got a candidate:
> a pure-Python, import-free monolith receiver for the archive's black-only
> c3-r0550 p100 row at source fraction 0.5 with a linear CM decoder and a
> tar unpacker, 2 R2 pages, restoring the 9.3 MB src/holo + docs tree from
> 15 archive pages in simulation (bootstrap/r3/). See
> bootstrap/RECORD-2026-10-20.md. The same evening the typed rung CLOSED
> ON PAPER: the owner typed a.py from the printed listing, entered the data
> lines by phone OCR, photographed the three R2 leaves with a phone (two
> turned, one in halves) and b.py came out byte-identical
> (bootstrap/PAPER-2026-10-20.md, experiments/047). One set; nothing
> promoted; the R3 pages are not printed (as of 2026-10-20; superseded:
> printed 2026-10-23 and closed on paper 2026-10-26, print-2026-10-23.pdf
> 4989446c…, bootstrap/PAPER-2026-10-26.md).

> **Status 2026-10-23.** The rungs carry the stage names of ruling 34
> (bootstrap/RECORD-2026-10-20.md:908), each stage named by the program it
> yields: stage 0 the Plate; stage 1 the typed program a.py, from its
> listing; stage 2 the data sheet typed at a.py's prompt, which yields b.py;
> stage 3 the R2 (bullseye) pages, read from phone photos by b.py, which
> yield c.py; stage 4 the release, which c.py reads from scans of the holo
> archive pages. The R0 to R2 names and "Archive" are their former names.
> The Mid rung (R3 below) was retired by ruling 34 itself. The measured
> standing is the next section; the chain's index is bootstrap/README.md,
> its rulings bootstrap/RECORD.md.

> **Status 2026-10-26.** THE WHOLE CHAIN CLOSED ON PAPER: the owner printed
> the candidate print of record v3 (bootstrap/build/sheets/print-2026-10-23.pdf
> 4989446c…, 19 pages, the HP M281), typed the listing and the data sheet,
> and a.py, b.py and c.py came out sha-equal to the chain; c.py read 600 dpi
> flatbed scans of the archive pages, closed the volume on eight of fifteen
> and unpacked the release's 321 files (bootstrap/PAPER-2026-10-26.md). The
> release as unpacked does not run: its tree selection carries no data
> file and no requirements file (the open item under "R3 payload manifest"
> below). One print, one typist; nothing promoted. Open threads:
> docs/TODO.md, section Bootstrap.

## State 2026-10-26 (measured; added 2026-10-26)

- **On paper, 2026-10-26** (bootstrap/PAPER-2026-10-26.md,
  docs/EXPERIMENT-LOG.md): stages 1 to 4 in one run. a.py 28 lines, 798
  characters (826 B), 39 data lines, 3,289 typed (the build's count);
  b.py 4,487 B; c.py 24,176 B (`b4f7de22…`), all three sha-equal to the
  chain; b.py read the R2 pages from 300 dpi grey scans; c.py closed the
  1,648,660 B volume from eight 600 dpi scans (6,264 symbols of 6,260),
  SHA-256 `78d9a4b4…`, and unpacked 321 files. Ruling 37's 600 dpi holds;
  300 dpi cannot read the c3 row (1.5 px per cell).
- **On paper, 2026-10-23**: the v2 print; stages 1-3 closed byte-exact,
  archive page 03 did not decode, which led to c.py's repair (floor 2.0
  calibrated on the simulator; bootstrap/FINDINGS.md §15).
- **Stage 3 now**: c.py through cm2 10,130 / 10,133 B = 2 R2 pages, 478 /
  475 B spare (bootstrap/CONVERGENCE-2026-10-23b.md; ruling 67).
- **Stage 4 now**: c3-k-r0547-p100 at q 0.5, 15 pages for the 9.28 MB tree
  of commit 2115a595 (15 pages hold at most 1,655,012 B, the capacity
  planner). The release as unpacked lacks the LDPC tables and a
  requirements file and has flat names (bootstrap/FINDINGS.md §16).
- **Not done:** the Plate (deferred by ruling 38); a second typist,
  printer or scanner; the release tree's selection law; the promotion of
  v3 to the print of record.

## State 2026-10-23 (measured; added 2026-10-23)

*Superseded by the state of 2026-10-26 above; kept as written.*

Simulation on machine 1 unless it says paper; one set of leaves, one typist who
designed the chain; NO promotion.

- **On paper, 2026-10-20** (bootstrap/PAPER-2026-10-20.md, experiments/047):
  the owner typed the 29-line a.py of that print (826 characters) from the
  listing and its 48 data lines by phone OCR, 3,895 typed characters in
  about 40 minutes of keyboard time, every slip caught by the line checks;
  four phone camera photos of the three R2 leaves (two turned 90°, one in
  halves) gave stage 3's output byte-identical to the bundle. The R2
  content was then a stand-in.
- **Stages 1 and 2 now** (a.py and the data sheet): a.py 28 lines, 807
  characters (bootstrap/stage1/RESULTS.md), 805 with c.py as the content;
  with today's reader (the grey padding of ruling 59 applied,
  bootstrap/r2reader/changeset/RESULTS-2026-10-22.md §20) 3,326 / 3,325
  typed lowercase / uppercase on 40 data lines with the stand-in content
  and 3,319 / 3,318 on 40 data lines with c.py as the content (§20, part
  2); before it 3,335 / 3,335 with the stand-in and the reader of §19, and
  3,465 / 3,463 on 42 lines with c.py and the reader of ruling 52, from an
  export of a9826d37 (bootstrap/stage3/RESULTS-2026-10-22.md §6). Data
  glyphs uppercase in Andale Mono, the listing in Menlo (ruling 51).
- **Stage 3 now** (b.py reading the R2 pages): b.py's typed text 138
  lines, 3,781 characters (§20); its reads identical call for call to the
  ruled text on 129 captures through §19, and with the grey padding on 127
  of 129, the finder's threshold byte-identical and no chunk lost; every
  acceptance set passing, both photo pools of 2026-10-20 closing
  (changeset/RESULTS §17 to §20). The page: R2-FORMAT v1 as amended, 204
  chunks = 5,304 B per page, three copies on different pages.
- **Stage 4 now** (c.py reading the archive pages): c.py 23,793 B, pure
  Python, no import, the receiver of the holo row c3-k-r0547-p100 at source
  fraction 0.5 with a strong2 decoder and a ustar unpacker, kept as built
  (ruling 61); 9,966 / 9,971 B through cm2 under today's b.py = 2 R2 pages,
  642 / 637 B spare (changeset/RESULTS §20, part 2; 9,951 / 9,956 under the
  b.py of a9826d37, stage3 §6); 321 of 321 files of the record's 9.28 MB
  tree byte-exact from 1,200-dpi simulated scans of its 15 archive pages,
  holo's own receiver verifying the same volume
  (bootstrap/stage3/RESULTS-2026-10-22.md §3, §6).
- **Python floor 3.11** (ruling 53).
- **Not done, as of 2026-10-23** (superseded except the Plate and the
  second typist: the convergence was reached (rulings 60, 67), the rebuild
  of record made print-2026-10-23.pdf 4989446c…, and that print closed on
  paper with 600 dpi scans of its archive pages on 2026-10-26,
  bootstrap/PAPER-2026-10-26.md): the full convergence of the three
  searches before the sheets, whose result is the candidate print of
  record v2 pending the c.py review (ruling 60; an interim sheet set of the
  chain after ruling 59 is under bootstrap/build/sheets/, changeset/RESULTS
  §20, part 2); the rebuild of record and the next print (the sheets of
  record and the paper-test set still carry the old reader); the Plate
  (deferred by ruling 38); any print or scan of an archive page at the
  r0547 row; the 600-dpi scan question of ruling 37; a second typist.

## The question

Assume the year ~3026. Finders hold a few bound volumes of our printed
output; the paper survived (or was recopied). They can recreate our
general technology — granted for this exercise: Python-class computing —
but paper-store itself must be rebuilt from the pages alone. What must the
first ~30 leaves of every volume contain so that the dense, anonymous
archive pages open?

The answer is a **four-rung ladder** bound into every volume, governed by
one law and carrying one non-speculative repo finding.

## The finding that is NOT speculative: the keystream liability

Every covert bit on a printed archive sheet flows through ONE function,
`modulation.rng` (src/paperholo/modulation.py:19-26):

    BLAKE2b(seed + label, digest_size=16) -> little-endian int
      -> numpy Philox key (no SeedSequence, counter 0)
      -> Generator.integers(...)

— pilot site offsets, pilot value scramblers, the payload keystream, the
LDPC H-construction, the fountain repair rows: all of it. And the
**normative spec of that stream lives outside the source tree**: it is
numpy's internal bounded-draw consumption pattern, where the `dtype`
kwarg forks the stream (the payload keystream is the one
`dtype=np.uint8` draw, modulation.py:36; everything else is default
int64). We already lived the failure once — the 012.3 phantom-payload
incident (`integers()` without `dtype=np.uint8`, pilots.py comment) *was*
the drifted-reimplementation rehearsal: clean-looking sheet, permanent
noise, no gradient to debug against. A finder holding the complete
printed source plus a semantics-drifted numpy regenerates the wrong
streams; because the PILOTS derive from the same function, acquisition
itself fails (the BCH gate rejects every hypothesis — there is no unkeyed
fallback, by design).

Fixes, in two halves:

1. **Non-breaking (spawned as a task 2026-07-10, separate session):**
   a pure-Python, numpy-free bit-exact reference of the whole chain
   (BLAKE2b keying, Philox-4x64-10, the exact bounded-draw rule per
   draw-form used in the codec) + pytest vs numpy byte-for-byte for every
   (seed, label, draw-form) actually used + checked-in golden vectors
   for the e016 volume seed. After this, the repo specifies its own
   scrambling.
2. **Format-axis (OPEN for the v1 src/paperholo stack only, user
   decision, layout_version bump; the holo v2 format that c.py reads
   already keys with AES-128, src/holo/core/keystream_spec.py):** the
   existing TODO at modulation.py:9 — swap BLAKE2b/Philox for per-cell-
   address AES-CTR, a construction whose complete spec fits on one
   printed page and is independently re-implementable from public
   standards. The bootstrap argument upgrades this TODO's priority from
   "standard crypto is nicer" to "the archive's readability by anyone
   who is not us depends on a printable keystream spec."

**Corollary — R3 inverts under deep time.** The seed's absence from the
pages (anonymity, R3/R5) is a feature today and a single point of TOTAL
loss over centuries: an archive designed so pages read as noise without
the seed *is nothing but noise* if the seed dies. The volume descriptor
(seed, rate_id, compose spec, data_len — fountain.py VolumeSpec) must
exist as a designed, replicated, overt PRINTED object — the preface —
not as a registry row in a git repo. The preface is deliberately
non-anonymous; that is R3's bill coming due.

## The ladder (one-page core)

**The monotone law: nothing crosses the channel before its own
specification has crossed.** No seed, no PRNG, no compression, and no
external library (numpy is contraband until rung 3 delivers it) until its
source or spec is already in the finder's hands. Each rung is decodable
using only what lower rungs delivered, plus a stated minimum of
technology; each rung opens with a known-answer block whose expected
output is printed beside it (the "Voyager circle": a decoder that has not
reproduced the golden block does not proceed).

**Amended 2026-10-23** (ruling 34 of 2026-10-21: the stages are named by
the program each one yields, the former R-names in brackets; the Mid rung
retired, "we seem to be doing fine without it"). As built and measured:

| Stage (former name) | Leaves | Carrier | Measured content | Decoder | Gear |
|---|---|---|---|---|---|
| 0 Plate (R0) | 3 in the 10-18 draft, one ruled; deferred | typography | promise, CRC-32, key, conventions | eyes | none |
| 1 the a.py listing (R1 Listing One) | 1 listing | printed text, Menlo | a.py, 28 lines, 798 characters (v3; typed on paper 2026-10-26) | the finder, typing it into a file | any computer; Python 3.11 or later |
| 2 the data sheet (R1 Listing One) | 1 data sheet | printed text, Andale Mono uppercase | b.py, 4,487 B; typed in all, with a.py, 3,289 on 39 data lines (v3, CONVERGENCE-2026-10-23b.md) | a.py, typed at stage 1 | a keyboard |
| 3 the R2 pages (R2 Coarse) | 2 (for c.py) | 0.508 mm modules (12 dots) | 5,304 B/page; c.py 10,133 B through cm2, 475 B spare | b.py, from stage 2 | a phone camera (phone camera, 2026-10-20) or a 300 dpi grey scan (2026-10-23, 10-26) |
| R3 Mid | RETIRED | | | | |
| 4 the archive pages (Archive) | 15 (for the record's tree) | c3-k-r0547-p100, q 0.5 | ~110 KB/page; the release, the 9.28 MB tree as 1,648,648 B | c.py, from stage 3 | flatbed, 600 dpi grey or more (closed on paper from 8 pages at 600 dpi, 2026-10-26; 300 dpi cannot read c3) |
| what stage 4 yields | (the payload) | | the paper-store tree | Python with its imports (ruling 40) | |

Pointers: bootstrap/README.md (per stage), TYPED-STREAM.md v3, R2-FORMAT.md
v1, bootstrap/stage3/RESULTS-2026-10-22.md; ~110 KB/page is ruling 25's
figure, the tree's size ruling 28's. The v0.1 table (then; historical, its
R3 Mid row retired by ruling 34):

| Rung | Leaves | Carrier | Net yield | Decoder | Minimum gear |
|---|---|---|---|---|---|
| R0 Plate | 2 (x2 copies) | typography | ~9 KB prose/tables | eyes | none |
| R1 Listing One | 3 | printed source text | ~8 KB, hand-typed | a keyboard, 4-6 h | any computer |
| R2 Coarse | 5 | 0.508 mm modules (12 dots) | ~7.0 KiB/page | the typed R1 program | any >=0.75 MP camera; or loupe + ~60 h |
| R3 Mid | 16-20 | 0.254 mm cells (c6) | ~37.7 KiB/page (duplicated) | R2's payload | ~300 dpi flatbed-class / 3 MP |
| Archive | the volume | c2/c3, anonymous | ~340 KB/page (MEASURED, e016) | R3's payload | 2400-4800 dpi precision scanner |

~30 leaves total; K-only carbon toner throughout (outlives dyes, carries
no MIC tracking dots — MEASURED 007.7/007.8: AltaLink K-only pages are
clean — and stays legible in IR on browned paper); blank versos (toner
blocking cannot ghost data onto facing pages); >=20 mm gutter and >=10 mm
trim margins (rebinding guillotines eat 5-10 mm/century); every leaf
carries an overt header (volume / rung / leaf n-of-m) because bindings
fail and leaves shuffle. On a 500-leaf volume: ~6% overhead.

*Amended 2026-10-23, the leaf count measured:* the Plate (three draft
leaves, one ruled), one listing leaf, one data sheet and two R2 pages, then
the archive pages, 15 for the record's 9.28 MB tree (ruling 44 of
RECORD-2026-10-20.md for the listing and the data sheet, which it calls
stage 1's leaves; stage3/RESULTS-2026-10-22.md for the rest). The bootstrap
itself is thus the Plate plus four leaves; the archive pages carry the
release.

Hash chain (Merkle, forward): the Plate prints the CRC-32 of Listing
One's text; Listing One's payload ends with the CRC of the coarse
payload; the coarse payload contains the hash of the mid payload; the mid
payload contains the hash of every archive volume. **Hash domains are
declared on the Plate: hashes cover payload bytes only** (a page cannot
contain the hash of itself — the red-team's fixed-point catch). The Plate
is certified by nothing but its worked examples and cross-copy
comparison, and says so. SHA-256 enters only at R3 (as printed reference
code + FIPS vectors); below that, CRC-32 only — corruption down there is
accident, not adversary.

*Amended 2026-10-23, as built:* a.py asserts the 4-glyph Horner code of the
b.py it decodes; b.py asserts a baked CRC-32 (B2) of the c.py it decodes
(ruling 22); c.py checks the release volume's SHA-256 and the archive's
CRC-32. The release's hash is to be printed in stage 0 (ruling 39, a
decision; the Plate is deferred and no leaf carries it yet; the stage-4
pages print `RELEASE <commit>` in their margin, not the hash, 0dfb3fed) and
baked into nothing below it, so the bootstrap stays fixed while the release
moves.

## Stage 0: THE PLATE (formerly R0; 2 leaves, duplicated front + back matter)

*Amended 2026-10-23:* the Plate assumes Python-class computing and is ruled
cut to one leaf, the cut not yet made (rulings of 2026-10-18,
bootstrap/RECORD-2026-10-18.md, "OWED (cut not yet made"); CRC-32 is its
one-line shift register, no table. It is DEFERRED until stages 1 to 3
are fixed (ruling 38); the 10-18 draft is bootstrap/plate/. The from-zero
material below (the counting primer, the dot rows, the binary strips beside
each ASCII glyph, hex as sixteen rows) was ruled out on 2026-10-18 ("a
different book"); the one-leaf target is the promise, the premise, the 8x8
proof, how to type, CRC-32 with its vectors, the R2 paragraph, the key and
care.

Pure typography, ~72 chars x 63 lines/leaf (~4.5 KB text-equivalent
each). Ordered: promise, then proof, then conventions — the red-team's
bluntest finding is that the SOCIAL failure is fatal: a finder who cannot
see within minutes what is inside and that the method works shelves the
book as decoration.

1. **Promise:** what the archive contains and how many bytes; the effort
   ladder stated plainly ("one hour: 64 marks by pencil; one day: a
   200-line program; one week: everything; fragments the size of a
   fingernail carry their own address").
2. **Proof:** an 8x8 golden block at 1 mm modules, decoded step by step
   beside it (marks -> binary -> numbers -> letters). Hand-reproducible
   in minutes; doubles as the imaging self-test ("if this block fails,
   fix the light, not the code" — specular toner gloss under flash reads
   as white).
3. **Grounding, in dependency order:** the 100 mm scale bar defines
   length (print 2362 dots at 600 dpi and STATE the true 99.992 mm —
   the bar is the unit's definition; ratios over absolutes, paper
   breathes +-0.5%). A counting primer grounds numerals — rows of dots
   beside each digit glyph, positional notation by worked grouping, hex
   as sixteen rows — because the bar grounds length and *nothing else
   grounds "7"*. Then the 128-entry ASCII table: glyph, decimal, and an
   8-mark binary strip per row (triple self-stating; slashed zeros,
   distinct case forms), closed by a printed digits-bearing pangram
   whose CRC is given, so glyph->byte is testable end-to-end.
4. **Conventions:** ink=1 (pictogram), raster arrows drawn ALONG the
   golden block's read path, MSB-first bytes — plus the 16-hypothesis
   trial table (8 dihedral orientations x 2 polarities) as pictograms:
   bit-sense and mirror ambiguity resolved by mechanical trial, no
   language needed.
5. **CRC-32, fully specified:** poly 0x04C11DB7 (reflected form
   0xEDB88320), init 0xFFFFFFFF, final xor 0xFFFFFFFF; a complete
   bit-level trace of a 2-byte example (every shift shown), the 256-entry
   table in hex, three vectors including crc32("123456789") = 0xCBF43926.
   Table AND trace: a wrong implementation gets a gradient, not a red
   light.
6. **THE KEY:** the volume seed in hex (e016: 24 bytes,
   `paper-store/exp016-arch3`), on both Plate copies and nowhere else,
   with the sentence explaining that the dense pages are noise without
   it — deliberately — and that this line is the price.
7. **Custodial directive:** dry, dark, cool; no adhesive repairs; COPY
   this volume and verify the copy against the golden block. The book
   crosses ten centuries as ~5 generations of copies, not as one miracle
   of paper. Damage advisory (3 lines): mirror ghosts are facing-page
   transfer — decode the sharp-edged original; browned paper: carbon
   marks reappear under raking/transmitted/IR light; corner targets are
   redundant, any 2 of 4 suffice.

## Stages 1 and 2: the a.py listing and the data sheet (formerly R1, LISTING ONE; 3 leaves in v0.1, now one listing and one data sheet; the program you type)

*Amended 2026-10-23, as built:* one 28-line program a.py, 807 characters,
typed into a file, printed in Menlo with every space a middle dot; it checks
itself by printing a 4-glyph Horner code per line for comparison with the
listing's margin, then takes a data sheet of base-32 lines (60 glyphs + 4
check glyphs, uppercase, Andale Mono) and decodes them with a big-integer
rANS decoder into b.py. No indent digits, no mod-997 sum: the listing's
codes are computed by the program and compared by eye with the margin, and
each data line is checked by the program as it is typed. Spec: bootstrap/TYPED-STREAM.md
v3; numbers: bootstrap/stage1/RESULTS.md and changeset/RESULTS §19.

~200 lines (~8 KB) in OCR-B, one statement per line, in a deliberately
tiny Python subset: NO imports at all, no floats, no negative modulo,
explicit while loops — written so it degrades into executable pseudocode
if Python-the-language is lost (a printed 12-rule semantics annex covers
indent-as-block, integer division, case sensitivity, evaluation order).

The proven channel is COMPUTE!'s MLX (1983-88): humans move kilobytes
through their fingers reliably IFF errors are caught per line. Margin
per line: line number + **hand-computable position-weighted checksum**
(sum of i x codepoint mod 997 — position-weighted because MLX's first,
position-insensitive checksum passed transpositions and had to be
revised), with one line hand-worked on the Plate. This breaks the
circularity the red-team caught: if margin checksums were CRC-32, the
finder would verify their typed CRC implementation with checksums only
that implementation can check. CRC-32 certifies the whole file only
after the CRC routine itself passes the Plate's printed trace. Python's
invisible-whitespace hazard: the **indent depth is printed as a leading
digit on every line** — whitespace transcribed as data. Honest typing
estimate, printed: 4-6 hours.

What it does (~170 lines, budget-audited): read a CONSTRAINED PGM P5
(maxval 255, no comments, single separators; complete 4x4 example
printed as hex beside its picture — constrain, don't describe); find
2-of-4 corner bullseyes; affine from 3 corners (full homography blows
the budget — the coarse pages instead print the requirement "press flat
under glass"); re-center every row between the two vertical perimeter
clock tracks (~20 lines — this is what actually absorbs warp and lens
distortion); global threshold from the bullseyes' own ink/paper
samples; nearest-neighbor sampling; majority-of-3; CRC per block; emit
bytes.

## Stage 3: the R2 pages, read by b.py (formerly R2, COARSE pages; 5 leaves in v0.1, now 2)

*Amended 2026-10-23, as built:* bootstrap/R2-FORMAT.md v1. The module stays
12 dots; the grid is 358 × 511 modules in 21 × 30 blocks; fifteen
circular-ring bullseyes in the body replace the four corner bullseyes and
carry the header; each block has a global chunk index and a CRC-32 bound to
the header; three copies per chunk on a designed placement and on different
pages; 204 chunks = 5,304 B per page. b.py reads phone photos, whole pages
or parts. The payload is c.py, 2 pages, not the ~30 KB mid decoder below.

Module = 12x12 engine dots = 0.508 mm — sized against OUR measured
morphology (the luxury no other deep-time project had): 12x above
isolated-dot death, 4x above the <3-dot white-closure floor, edge gain
at 3% of module width (MEASURED floors, exp 001). Grid 360x520; furniture
= 4 bullseyes (13x13) + perimeter clock track + 1 header row = 2,792
modules; 3x repetition with the three copies in different page thirds
(damage is spatially coherent across neighboring leaves AND page
positions — duplicates get position TRANSPOSITION and maximal leaf
separation); 64-byte blocks + CRC-32. **Net 7,168 B/page ~= 7.0 KiB**
(honest accounting; the first sketch's ~8 was 15% optimistic). At 12-dot
modules the error regime is damage-dominated, not channel-dominated, so
majority+CRC genuinely suffices — no correcting code needed at this rung.

Capture: 2 samples/module = 100 samples/inch = a 0.75-megapixel
photograph of the page — any camera that will ever exist again; a
50-spi-class device shoots 2x2 overlapping quarters. **Advertised
zero-camera floor** (one printed sentence): 0.508 mm sits ~7x above
naked-eye acuity; ruled overlay + ~1.5 bit/s sustained = ~12 h/page,
~55-60 h for the rung (ESTIMATE) — brutal, finite, and its entire job is
to exist. Cross-copy visual comparison stands in for CRC until any
computer exists.

Payload (~30 KB over 5 leaves): `mid_decoder.py` (~25 KB, **pure Python
— numpy has not crossed yet**; the red-team killed "numpy allowed" here
as a monotone-law violation), the mid-format one-page spec, the ASCII
table repeated as bytes (printed self-check), the hash of R3's payload.

## R3: MID pages (16-20 leaves), RETIRED by ruling 34 (2026-10-21)

*Amended 2026-10-23:* retired by ruling 34 of 2026-10-21 (the owner: "we
seem to be doing fine without it"). c.py, the program of stage 3, rides on
the two R2 pages and reads the archive pages of stage 4 directly: the
archive's own black-only row c3-k-r0547-p100 at source fraction 0.5, with
holo's LDPC, BCH addressing and fountain in place of this section's
RS(255,223) and duplication. The text below is kept as the design of
2026-07-10.

Cell = 6x6 dots = 0.254 mm (c6 — 2x the proven c3 cell; design-point raw
BER 0.2-0.5% ESTIMATE, bracketed by MEASURED c4 0.4-1.4% and c6 ~0-0.35%,
exps 007.6/007.1). Grid 720x1040, 8-cell frame -> 704x1024 data cells =
90,112 raw B/page. Overt border + bullseyes + tick marks every 32 cells:
+-0.5% hygroexpansion is 3.6 cells cumulative across 720 — per-tick-span
resampling is MANDATORY, a global affine cannot hold this pitch
(MEASURED distortion class, exp 001/002.0b).

**The forced correction (the one real trap in the first sketch):
CRC-only + duplication is dead on arrival at this pitch.** At 0.2% raw
BER a 128-byte CRC block survives with p = 0.998^1024 ~= 13% -> 87%
per-copy block failure. A correcting code is REQUIRED: interleaved
RS(255,223) t=16 over GF(256), depth-8 byte interleave (foxing bursts),
4-byte CRC inside each codeword (219 user + 4 CRC + 32 parity). At the
design BER: lambda ~= 4.05 byte-errors/codeword, P(>16) ~= 1.3e-6 —
clean. An RS decoder (GF tables + Berlekamp-Massey + Chien + Forney) is
~200 lines inside mid_decoder's 25 KB budget, and stays monotone: it
arrives as printed source, decoded by a rung that needed only majority
votes. 353 codewords/page -> 77,307 user B single-copy; every block on 2
well-separated leaves -> **net 38,653 B/page ~= 37.7 KiB**. Payload
~600-650 KB -> 16-20 leaves (duplicate only the decoder-critical core if
20 offends: ~14 leaves). Each R3 leaf carries a resolution/moire
self-test wedge with a printed pass rule — a photographed (not scanned)
page can sit at a silent alias floor, exactly our pn1200 24-31%
experience (MEASURED, 007.1/007.6).

**R3 payload manifest** (what must cross; sizes MEASURED 2026-07-10):
- the complete src/paperholo tree + DESIGN/PILOTS/FEC/FOUNTAIN/LAYERS
  docs = 535,386 bytes (19 source files + 5 docs, `wc -c`);
- the pure-Python keystream reference + PRINTED golden vectors (first
  256 keystream bits for (volume seed, plane K, page 0); the BLAKE2b
  digest of the seed; one pilot tile's codeword before/after scramble;
  one decoded LDPC tile) — so a rebuilt stack is testable stage by
  stage against ink;
- vendored pure-Python fallbacks for the scipy calls in
  acquire/place/ldpc (fftconvolve, ndimage labeling, sparse matvec —
  ~50 lines each) + an environment dossier (exact versions, IEEE-754
  binary64 stated);
- the format registry WITH seeds (formats.py rows — the seeds' first
  legal machine-readable appearance: the full source has now crossed);
- the measured-channel dossier: what 21st-century laser engines did to
  dots (isolated-dot death, white closure, edge gain, scanner comb,
  hygroexpansion). The finder decodes through OUR channel; our channel
  facts are part of the format.

*Amended 2026-10-26, an OPEN design item: the release tree's selection
law.* What crosses at stage 4 is the tree T1 (bootstrap/r3/arch/trees.py:
`src/holo/**/*.py` + `docs/**/*.md` without docs/archive/ + CLAUDE.md, at
commit 2115a595; 321 files, 9.28 MB, 1,648,648 B by strong2, 15 pages).
On paper (2026-10-26) the release restored byte-exact and DID NOT RUN.
NEW on paper: the selection takes no non-.py file under src/holo, so the
twelve LDPC code tables (JSON, six under src/holo/core/ldpc/data and the
same six under src/holo/receiver/lib/ldpc_data, 161,840 B) are missing
and holo3 dies at import; and c.py writes flat names. KNOWN (ruling 40:
holo3's imports are not in the tree; the release "magically has all
imports") and met in practice on 10-26: nothing names the packages and
versions to install (no requirements file). This manifest's own premise,
an environment dossier with exact versions, was not carried into T1. The
law owed is the owner's ruling; ruling 41 in full
(bootstrap/RECORD-2026-10-20.md:978-982): "The tree is "the paper-store /
holo release", to be ruled eventually; for now think paper/src, "but it
will be more" (the readable sources of stages 1–3 do not travel in T1
today: bootstrap/ is not in it). Speculation recorded as such: a stage 4
in cmy8-r0850x0775x0700 to carry a lot more data." Three choices: every
tracked file under src/holo (+164 files, 9,746,575 B; ESTIMATE ~26
pages), src/holo with its data directories only (+12 files; ESTIMATE 16
pages), or all of src/ (438 files, 15,080,318 B at 2115a595; not sized);
plus requirements.txt
with the venv recipe of its header, and whether the receiver's docs,
bootstrap/'s readable sources and analyzer/ travel. Any choice is a new
container and new stage-4 pages; c.py, being content-independent (ruling
39), and stages 1-3 do not move (bootstrap/FINDINGS.md §16; docs/TODO.md,
Bootstrap).

After R3 the finder runs acquire-v2 blind, the pilots hand them absolute
addresses, the fountain absorbs every leaf the centuries ate, and the
chain closes byte-exact — the same 361,833-byte certification of run
016.2, executed a millennium late.

## The irreducible format kernel (what R3 must convey; audited + spot-verified)

(For holo format v1, `src/holo`, the generator-side statement of this
kernel is `docs/PRINTED-FORMAT.md`, 2026-09-13: its §0 sorts every claim
into convention, math, algorithm, generated-then-pinned or opaque pin, and
its §14 lists what a second generator must not invent. The list below is
paperholo's.)

Facts a from-scratch decoder cannot re-derive (format axis; everything
decoder-axis — orientation search, warp tracking, detection, LLRs — is
re-derivable and needs nothing printed; the BCH gate arbitrates
hypotheses exactly as designed):

- **Master PRNG** (modulation.py:19-26): BLAKE2b-128(seed+label) ->
  LE int -> Philox key -> Generator; PLUS numpy's per-dtype bounded-draw
  consumption (uint8 draws buffered per 64-bit word; int64 not). The
  payload keystream is the one dtype=np.uint8 draw; label =
  bytes([plane]) + page_le32, plane index = 'CMYK'.index -> K=3.
- **Pilot sites p60b6** (pilots.py): label b"pilot-sites-v2" (SHARED by
  v3 — no v3 site label, contract), off = integers(0,6,(10,10,2)) at
  default dtype; site raster s = by*10+bx; period 60, block 6, 100
  sites/tile, density 1/36.
- **Pilot values**: BCH codeword XOR ks_P, label b"pilot-values-v{2,3}"
  + b"/" + plane letter; the v3 label IS the format identity (no
  version/plane fields printed — R5 implicit signaling; wrong hypothesis
  = coin flips, MEASURED 0/200k FA).
- **BCH v3**: GF(2^7) prim poly 0x89, n=127 k=50 t=13, roots
  alpha^1..26, shorten 27 -> (100,23), d>=27, systematic (parity
  x^0..x^76, message x^77..x^99), bit i = coeff of x^i; g(x) DERIVED,
  not stored. v2 = (127,64,t=10) -> (100,37), e011 only (never printed).
- **v3 message**: 23 bits MSB-first = [18-bit flat counter][5 zero pads,
  reject gate]; c = page*tiles_per_page + ty*tiles_x + tx; tile geometry
  (tiles_x, tiles_per_page) is a format-descriptor constant, NOT
  recoverable from a fragment.
- **Composition** (compose.py): cell = cell_dots^2 solid dots (kron),
  ink=1; field top-left (230,178) dots on the A4 600-dpi grid (not
  load-bearing for decode — pilots give absolute addresses); payload bit
  i <-> i-th non-pilot cell in C-order raster, XOR keystream at ABSOLUTE
  cell coords. Formats: kcell-c3 (2220,1500), kcell-c2 (3300,2220).
- **LDPC** (ldpc.py, normative docstring): e-IRA QC, n=4096, Z=64,
  derived deterministically from seed b"ldpc-v1/<rate_id>" + label
  b"eira-H/restart<R>" — volume-seed-INDEPENDENT public constants;
  Fisher-Yates row perm + greedy per-column draw (2 draws/attempt, every
  rejected attempt still consumed its draws), tap-gap/4-cycle/row-load
  rules, heavy columns first (0.30, deg 10/8/6), dual-diagonal
  accumulator, I(s)[a,b]=1 iff b=(a+s)%Z. Ladder k = {2240, 2560, 2880,
  3200, 3520}. Tile framing: 64x64 cells incl. partial edge tiles;
  shortened slot = off-page or pilot site; shorten-map position rule
  (descending {k-1..} for shortened, ascending complement for
  transmitted); CRC-32 = zlib.crc32 over MSB-first packed payload,
  emitted 32 bits MSB-first.
- **Fountain** (fountain.py): symbol = interior tile's first S user
  bits (S = min interior cap); geometric ESI t = page*n_interior +
  local, block = t mod n_blocks, i = t // n_blocks; source rows = unit
  vectors, repair row = integers(0,2,K_b) at default dtype, label
  b"fountain-v1/row/" + block_le32 + i_le32 from the VOLUME seed;
  bytes<->bits via MSB-first unpackbits.
- **Endianness rules**: integers inside PRNG labels LE; bit-packing
  MSB-first; BCH polynomial domain LSB-first (bit i = x^i); LDPC restart
  counter decimal ASCII. A wrong endianness anywhere forks a BLAKE2b
  digest and fails silently and totally.
- **Volume descriptor**: (n_pages, data_len_bytes, seed, ldpc_rate_id,
  compose_spec). Never on the data pages. THE PREFACE IS ITS HOME.

## Deep-time precedents (what each contributes; web-verified 2026-07-10)

- **Long Now Rosetta Disk**: the magnification gradient IS the
  instruction manual — each readability rung physically points at the
  next. Our ladder is its digital descendant.
- **GitHub Arctic Code Vault**: spec + retrieval-software source ride
  every reel in human-readable frames — right idea; thin bridge (no
  graded rung between readable spec and dense frames). Our R1/R2 are
  that bridge.
- **Westinghouse 1939 Book of Record**: replicate the KEY wider than
  the payload (3,000+ library copies); treat natural language as a
  decaying channel. Our Plate duplication + custodial recopy directive.
- **Crypt of Civilization**: shipped physical readers (and a language
  teaching machine) — machines seize; ship the machine as information.
  Our R1 is the reader, as text.
- **Voyager record cover**: units from physical invariants + the
  first-decode-is-a-circle known-answer test. Our scale bar + golden
  blocks at every rung.
- **Sandia/WIPP markers (SAND92-1382)**: graded message levels I-IV,
  each complete at its own complexity — the rhetoric inverted (they
  repel, we invite).
- **Memory of Mankind**: separate the pointer from the payload;
  replicate the pointer cheaply (ceramic tokens). Our Plate = the token.
- **Cauzin Softstrip**: a dead 1980s paper barcode was decoded in 2021
  from flatbed scans BECAUSE the printed format documentation survived —
  the direct existence proof for this whole document.
- **COMPUTE!'s MLX**: kilobytes through human fingers work IFF per-line
  checksums with immediate feedback; first-version checksum passed
  transpositions (fixed) — hence our position-weighted sum.
- **KEO** (never launched): minimize the technology cliff at every rung;
  and deep-time projects die of not shipping far more often than of
  media decay. v0.1 frozen now beats v1.0 never.

## Substrate honesty

The code survives 1000 years; office paper survives ~100-200 (acid
hydrolysis). Our e016 sheet would not make the trip. A real deep-time
volume is ISO 11108 cotton-rag permanent paper (verify toner fusing on
rag stock before trusting it — one-variable hardware probe if ever
needed), and the ACTUAL 1000-year mechanism is the Plate's recopy
directive: ~5 custodial generations of verified copies, not one miracle
of paper. Fused carbon toner outlives the sheet it sits on; the bootstrap
rungs, K-only and coarse, are the most archival objects in the volume.

## Repo residue (action items, all zero-print)

1. **Keystream printable-spec** — reference + tests + golden vectors:
   task spawned 2026-07-10 (running in a separate session). AES-CTR swap
   = format-axis decision, OPEN (modulation.py:9 TODO) for the v1
   src/paperholo stack; the holo v2 format already keys with AES-128
   (src/holo/core/keystream_spec.py).
2. **Volume-descriptor doctrine**: any real archival deployment needs
   the descriptor (seed included) as a designed overt key sheet — a
   DESIGN.md §5/§9 amendment candidate, alongside the R3 deep-time
   inversion note.
3. **scipy imports in acquire/place/ldpc** are quiet bootstrap debt;
   same instinct that kept torch out of the sim. Low priority; note only.
4. **This document is the printable-record skeleton**: if a PREFACE-1
   sheet is ever built, its gen_/analyze_ pair starts from the R0-R3
   specs above (R2/R3 geometries are printable today on the M281 —
   12-dot and 6-dot features are deep inside the measured envelope).

## Appendix A — red-team failure modes (condensed; severity, countermeasure)

| # | Scenario | Sev | Countermeasure |
|---|---|---|---|
| 1 | Acid paper dies in 100-200 y | FATAL | ISO 11108 rag stock + printed recopy directive (LOCKSS by custodians) |
| 2 | Finder shelves the book (no visible promise/proof) | FATAL | Plate p.1 = inventory + 10-minute golden-block demo + effort ladder |
| 3 | Keystream unreproducible on drifted numpy | FATAL | pure-Python reference in R3 payload + printed golden vectors (see finding) |
| 4 | numpy/scipy semantics drift ("they know Python" is approximate) | major | mid_decoder pure-Python (v0.1; the Mid rung is retired, ruling 34, and c.py is pure Python with no import); vendored scipy fallbacks; env dossier; printed intermediate vectors |
| 5 | Language death (1000 y ~= Old English gap) | major | 4-6 parallel languages + pictorial primer carries the load-bearing claims language-free |
| 6 | Nothing grounds numerals (bar grounds length, not "7") | major | counting-dots primer before first numeral use; hex as base-16 extension |
| 7 | CRC-32 variant hell (~16 plausible knob settings) | major | bit-level trace + 256-entry table + 3 vectors incl. 0xCBF43926 + stored-byte-order shown in place |
| 8 | Python semantics unspecified below R3 | major | 12-rule semantics annex at R1; listing avoids every subtle construct; imports BANNED |
| 9 | Per-line CRC = circular; 200 unchecked lines = 4-10 bad | major | hand-computable weighted sum mod 997; indent depth printed as a digit; honest 4-6 h estimate |
| 10 | ASCII table self-confusables (O/0, l/1, case) | major | slashed-zero OCR face; binary strip per glyph; pangram-with-digits + printed CRC |
| 11 | Gutter/rebinding eats margins | major | >=20 mm gutter, >=10 mm trim, nothing load-bearing in outer 10 mm |
| 12 | Water/foxing damage coherent across leaves AND positions | major | duplicate with position transposition + front/back-matter separation |
| 13 | Binding fails, leaves shuffle across volumes | major | overt per-leaf header (volume/rung/n-of-m); block index inside CRC-protected payload |
| 14 | Plate has no FEC | major | print twice per volume + every-volume replication; cross-copy majority |
| 15 | Self-hash fixed point ("rung prints its own hash") | major | hash domains = payload bytes only; Plate certified by worked examples, stated |
| 16 | SHA-256 needed before it can be implemented | major | CRC-32 only through R2; SHA-256 enters at R3 as printed reference + FIPS vectors |
| 17 | Toner blocking/transfer ghosts onto facing pages | major | blank versos; "mirror ghost" advisory line |
| 18 | Photograph (not scan) -> demosaic/JPEG moire alias floor at R3 | major | moire wedge + pass rule on every R3 leaf (our pn1200 24-31% floor is the template) |
| 19 | Bit-sense inversion / mirror scan / RTL reading order | minor | 16-pictogram trial table (8 dihedral x 2 polarity); raster arrows on the golden block |
| 20 | IR-readability overclaim (charring kills carbon contrast) | minor | demote to advisory; raking + transmitted light listed first; no rung BUDGETS on IR |
| 21 | Specular toner gloss under flash reads white | minor | imaging pictogram (diffuse light, no flash); golden block = imaging self-test |
| 22 | PGM P5 edge cases (maxval>255, comments, whitespace) | minor | constrained dialect mandated + 4x4 hex example; listing rejects deviations |
| 23 | Library stamps/tape land on corners and margins | minor | any-2-of-4 bullseye rule; no-marking pictogram; one corner is sacrificial |

## Appendix B — circularity audit (all resolved in v0.1)

1. Self-hash fixed point -> hash domains declared (A15).
2. Numeral grounding -> counting primer inside R0, before first use (A6).
3. Per-line CRC bootstrap -> hand-computable weighted sum; CRC validated
   against the Plate trace first (A9).
4. Python semantics at R1 -> annex + subset discipline + imports banned (A8).
5. numpy at R2 -> mid_decoder pure-Python (v0.1, historical: the Mid rung
   is retired by ruling 34; c.py is pure Python with no import); the
   monotone law extended to "no external library before its spec/source
   has crossed" (A4).
6. scipy at R3 -> vendored pure-Python fallbacks in the payload (A4).
7. Keystream spec outside the tree -> the headline finding; reference +
   printed vectors (A3).
8. IEEE-754/FFT conventions -> stated in the env dossier + printed
   intermediate vectors (soft circularity; threshold-tolerant pipeline).
9. Image acquisition presumed -> the R2 loupe fallback stated in print
   converts a technology dependency into a labor cost.

Monotone law otherwise verified end to end: first seed use is decoding
the archive proper, after the registry crosses; compression is absent
below R3; the forward hash chain is authorable (freeze all payloads
before printing anything).

## Appendix C — rung arithmetic (honest numbers)

Usable area 182x277 mm (A4, 10 mm margins, 18 mm gutter). R2: 360x520 =
187,200 modules - 2,792 furniture = 184,408; /3 = 61,469 bits; blocks
64+4 CRC -> 112 x 64 B = 7,168 B/page. 30 KB payload -> 5 leaves. R3:
704x1024 = 720,896 bits = 90,112 B raw; 353 x RS(255,223) -> 77,307 user
B single-copy; x2 duplication -> 38,653 B/page. 535 KB measured kernel +
~100 KB additions -> 16-20 leaves (14 with core-only duplication).
Capture: R2 = 0.75 MP/page (2 samples/module); R3 = 3.0 MP/page (2
px/cell). Loupe floor: 61,469 bits at 1.5 bit/s ~= 11.4 h/page. Archive
endpoint for contrast: e016 MEASURED 361,833 B certified = 55.1 b/mm2.
All ESTIMATE except where labeled MEASURED.

*Amended 2026-10-23: then and now.* Each line: the v0.1 figure above, then
the measured or specified one with its pointer.

- R2 grid: then 360x520 modules, 7,168 B/page; now 358 x 511 modules, 21 x
  30 blocks, 204 chunks of 26 B = 5,304 B/page (bootstrap/R2-FORMAT.md v1).
- R2 payload: then ~30 KB over 5 leaves; now (2026-10-26) c.py, 10,133 B
  through cm2 under the chain's b.py, 2 pages with 475 B spare
  (bootstrap/CONVERGENCE-2026-10-23b.md; 9,966 B on 2026-10-23 before the
  repair, bootstrap/r2reader/changeset/RESULTS-2026-10-22.md §20).
- R3: then 38,653 B/page over 16-20 leaves; now retired (ruling 34).
- Archive: then e016's c2 page, ~340 KB; now the c3-k-r0547-p100 row at
  q 0.5, ~110 KB of payload per page (ruling 25), the 9.28 MB tree in 15
  pages (ruling 28; stage3 §3), closed on paper from 8 of them at 600 dpi
  (bootstrap/PAPER-2026-10-26.md).
- Typing: then ~8 KB in 4-6 h (ESTIMATE); now 3,289 typed characters (v3,
  bootstrap/CONVERGENCE-2026-10-23b.md), typed on paper 2026-10-26 (time
  not recorded); 3,895 on paper in about 40 minutes on 2026-10-20
  (bootstrap/PAPER-2026-10-20.md).
- Capture: then 0.75 MP/page at 2 samples/module; now phone photos of
  3072 x 4080 at 7.1-11.1 px per module on paper (PAPER-2026-10-20.md;
  RECORD-2026-10-20.md, the axes section); the 10-20 diet reader's floor 2
  samples/module at blur 0.45 module or 1.5 at 0.4 (ruling 15's note).
- Loupe floor: then ~11.4 h/page (ESTIMATE); not measured since.
